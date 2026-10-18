"""The Draslin rebuild: Fable players rebuild Restored Draslin, the town in The Tiamat Sacrament, together.

Players send their character on supply runs (`$gather`), buy materials with Tiamat crowns (`$rebuild donate`) and
vote on what gets built next (`$rebuild vote`). Everything is kept in Postgres (scripts/draslin_rebuild.sql)
and decided by cogs/rebuild/service.py, never by a client. A pinned board (`$rebuild board`, GM) shows the town
as it stands, drawn from the game's own map, and a card is posted whenever a project is finished. The Tiamat
game server will read the same tables to show the town in the game, and later add its own contributions.
"""
from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
import logging

import discord
from discord.ext import commands, tasks

from classes.classes import Breathcaller, Penitent, from_string
from utils import checks, tiamat_unlocks

from . import board, rules, service
from .service import NotBack, RebuildError

log = logging.getLogger(__name__)
BOARD_REFRESH_MINUTES = 2
CREW_SYNC_MINUTES = 10
INBOX_SECONDS = 15   # how often finds from the game are applied
COLOUR = discord.Colour.from_rgb(236, 190, 92)


def class_lines(character) -> list[str]:
    classes = [from_string(name) for name in (character["class"] or [])] if character else []
    return [line.__name__ for line in (Breathcaller, Penitent)
            if any(c and c.in_class_line(line) for c in classes)]


def materials_text(materials: dict) -> str:
    return ", ".join(f"{rules.MATERIAL_EMOJI.get(m, '')} **{n:,}** {rules.MATERIAL_NAMES.get(m, m).lower()}"
                     for m, n in materials.items()) or "nothing"


def delivery_lines(delivery: service.Delivery) -> list[str]:
    lines = []
    if delivery.applied:
        lines.append(f"Delivered to **{board.name_of(delivery.project_id)}**: {materials_text(delivery.applied)}.")
    if delivery.stockpiled:
        lines.append(f"Stockpiled for the next project: {materials_text(delivery.stockpiled)}.")
    if delivery.project_id and delivery.progress_after > delivery.progress_before and not delivery.finished:
        lines.append(f"{board.name_of(delivery.project_id)}: **{delivery.progress_before}% → {delivery.progress_after}%**")
    for done in delivery.finished:
        lines.append(f"🎉 **{board.name_of(done.project_id)}** is finished!"
                     + (f" Next up: **{board.name_of(done.next_id)}**." if done.next_id else " Draslin is whole again."))
        perk = rules.PERKS.get(done.project_id)
        if perk:
            lines.append(f"✨ New perk for everyone, **{perk.name}**: {perk.text}")
    return lines


def haul_time(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}.{int(seconds * 10) % 10}"


MEDALS = {"gold": "🥇", "silver": "🥈", "bronze": "🥉", None: "▫️"}


def event_text(event: dict) -> str | None:
    """A line for Rolan's camp about something that happened in The Tiamat Sacrament."""
    payload, who = event["payload"], f"**{event['payload'].get('name') or 'A builder'}**"
    if event["kind"] == "rescue":
        return f"🏠 **{payload.get('person', 'Someone')}** is home in Draslin again, thanks to {who}."
    if event["kind"] == "haul_gold" and payload.get("seconds"):
        return f"🥇 {who} raced a crate of stone from the Mythra trail to Draslin in **{haul_time(float(payload['seconds']))}**!"
    if event["kind"] == "raid" and payload.get("names"):
        names = [f"**{name}**" for name in payload["names"]]
        party = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"
        return f"⚙️ {party} broke Ry'jin's machines at {payload.get('site', 'the ruins')} and hauled the salvage to Rolan's crews."
    return None


def is_rebuild_owner():
    """Only the owner opens, pauses and resets the rebuild."""
    return commands.check(lambda ctx: ctx.author.id == rules.OWNER_ID)


async def character_for(bot, user_id: int):
    return await bot.pool.fetchrow('SELECT * FROM profile WHERE "user"=$1', user_id)


# ---- buttons and menus -----------------------------------------------------------------------------------
def needed_now(place: rules.Destination, missing: dict) -> str:
    """What a run's materials would do right now, e.g. "iron: 140 still needed · glass: not needed yet"."""
    return " · ".join(f"{rules.MATERIAL_NAMES[m].lower()}: {missing[m]:,} still needed" if missing.get(m, 0) > 0
                      else f"{rules.MATERIAL_NAMES[m].lower()}: not needed yet (stockpiled)" for m in place.yields)


class GatherSelect(discord.ui.Select):
    def __init__(self, cog: "Rebuild", missing: dict, done=()):
        options = [discord.SelectOption(label=f"{place.name} · {hours}h",
                                        description=f"About {rules.expected_haul(key, hours, done)} · "
                                                    f"{needed_now(place, missing)}"[:100],
                                        value=f"{key}:{hours}",
                                        emoji=rules.MATERIAL_EMOJI[next(iter(place.yields))])
                   for key, place in rules.DESTINATIONS.items() for hours in rules.RUN_HAULS]
        super().__init__(placeholder="Where should your character go?", options=options)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction) -> None:
        destination, hours = self.values[0].split(":")
        text = await self.cog.start_run(interaction.user.id, destination, int(hours))
        await interaction.response.edit_message(content=text, view=None)


class VoteSelect(discord.ui.Select):
    def __init__(self, cog: "Rebuild", ballot: list, mine: str | None):
        def describe(entry):
            perk = rules.PERKS.get(entry["id"])
            votes = f"{entry['votes']} vote{'s' * (entry['votes'] != 1)} so far"
            return f"Perk: {perk.short} · {votes}"[:100] if perk else votes
        options = [discord.SelectOption(label=board.name_of(entry["id"]), value=entry["id"], description=describe(entry),
                                        default=entry["id"] == mine)
                   for entry in ballot]
        super().__init__(placeholder="What should Draslin build next?", options=options)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction) -> None:
        text = await self.cog.vote_for(interaction.user.id, self.values[0])
        await interaction.response.edit_message(content=text, view=None)


class MenuView(discord.ui.View):
    def __init__(self, item: discord.ui.Item):
        super().__init__(timeout=180)
        self.add_item(item)


class BoardView(discord.ui.View):
    """The buttons under the board. Persistent: they keep working after the bot restarts."""

    def __init__(self, cog: "Rebuild"):
        super().__init__(timeout=None)
        self.cog = cog

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await self.cog.may_build(interaction.user, interaction.guild):
            await interaction.response.send_message(rules.NOT_YET, ephemeral=True)
            return False
        if await character_for(self.cog.bot, interaction.user.id):
            return True
        await interaction.response.send_message("Create a Fable character first (`$create`).", ephemeral=True)
        return False

    @discord.ui.button(label="Gather", emoji="🪵", style=discord.ButtonStyle.success, custom_id="rebuild:gather")
    async def gather(self, interaction: discord.Interaction, _button) -> None:
        text, view = await self.cog.gather_reply(interaction.user.id)
        await interaction.response.send_message(text, view=view or discord.utils.MISSING, ephemeral=True)

    @discord.ui.button(label="Vote", emoji="🗳️", style=discord.ButtonStyle.primary, custom_id="rebuild:vote")
    async def vote(self, interaction: discord.Interaction, _button) -> None:
        text, view = await self.cog.vote_reply(interaction.user.id)
        await interaction.response.send_message(text, view=view or discord.utils.MISSING, ephemeral=True)

    @discord.ui.button(label="My help", emoji="🧱", style=discord.ButtonStyle.secondary, custom_id="rebuild:me")
    async def me(self, interaction: discord.Interaction, _button) -> None:
        await interaction.response.send_message(embed=await self.cog.me_embed(interaction.user), ephemeral=True)


# ---- the cog -----------------------------------------------------------------------------------------------
class Rebuild(commands.Cog):
    """Rebuild Draslin together, for The Tiamat Sacrament."""

    def __init__(self, bot):
        self.bot = bot
        self.board_signature = None
        self.board_view = BoardView(self)
        self.refresh_lock = asyncio.Lock()
        self.pending_refresh = None
        self.crew_done: set[int] = set()   # finishers already holding the role (skipped by the sync)
        self.crew_absent: dict[int, datetime.datetime] = {}   # finishers not in the server: when to look again

    async def cog_load(self):
        async with self.bot.pool.acquire() as conn:
            await service.ensure_schema(conn)
            await service.ensure_town(conn, rules.load_projects())
        self.bot.add_view(self.board_view)
        self.refresh_board.start()
        self.sync_crew.start()
        self.game_inbox.start()

    async def cog_unload(self):
        self.refresh_board.cancel()
        self.sync_crew.cancel()
        self.game_inbox.cancel()
        if self.pending_refresh:
            self.pending_refresh.cancel()

    # ---- who may build, and where ---------------------------------------------------------------------------
    async def may_build(self, user, guild) -> bool:
        """Finished the story (the same proof as the Clutch badge and Dragonkin), or holds Rolan's Crew."""
        member = guild.get_member(user.id) if guild else None
        if member and any(role.id == rules.CREW_ROLE_ID for role in member.roles):
            return True
        async with self.bot.pool.acquire() as conn:
            return await tiamat_unlocks.has_unlock(conn, user.id, tiamat_unlocks.DRAGONKIN)

    async def gate(self, ctx) -> bool:
        """Player commands: only for finishers, and only in the rebuild channel, so nothing spills into other chats."""
        if not await self.may_build(ctx.author, ctx.guild):
            await ctx.send(rules.NOT_YET, delete_after=20)
            return False
        channel_id, _message = await service.board_location(self.bot.pool)
        if not channel_id:
            await ctx.send("Rolan's camp isn't set up yet.", delete_after=20)
            return False
        if ctx.channel.id != channel_id:
            channel = self.bot.get_channel(channel_id)
            await ctx.send(f"That works in {channel.mention}." if channel else "That works in Rolan's camp.",
                           delete_after=20)
            return False
        return True

    # ---- shared by commands and buttons -------------------------------------------------------------------
    async def gather_reply(self, user_id: int):
        """Collect a run that's back, say when one is due, or offer the places to go."""
        character = await character_for(self.bot, user_id)
        try:
            haul = await service.collect_expedition(self.bot.pool, user_id, race=character["race"] if character else None,
                                                    class_lines=class_lines(character))
        except NotBack as waiting:
            run = waiting.run
            place = rules.DESTINATIONS[run["destination"]].name
            return f"Your character is still at **{place}**. Back <t:{int(run['returns_at'].timestamp())}:R>.", None
        except RebuildError as error:   # back, but the rebuild is paused
            return str(error), None
        if haul:
            self.kick()
            return self.haul_text(haul), None
        try:
            async with self.bot.pool.acquire() as conn:
                await service.require_open(conn)
                if await service.is_declared_alt(conn, user_id):
                    return "Alt accounts can't haul for Draslin. Your main account builds for you.", None
                done = await service.done_projects(conn)
                room = await service.run_room(conn, user_id, "discord", done=done)
                tiamat_left = await service.run_room(conn, user_id, "tiamat", done=done)
                current = await service.building(conn)
                missing = {r["material"]: r["needed"] - r["delivered"] for r in await conn.fetch(
                    "SELECT material, needed, delivered FROM rebuild_needs WHERE town=$1 AND project_id=$2",
                    rules.TOWN, current["id"])} if current else {}
        except RebuildError as error:
            return str(error), None
        if room <= 0:
            return service.full_message(tiamat_left), None
        building = board.name_of(current["id"]) if current else "the town"
        return (f"Rolan needs hands for **{building}**. Pick a supply run. The carts have room for "
                f"**{room}** more from you today. Anything the build doesn't need yet "
                f"is stockpiled for the next one, and still counts for you.", MenuView(GatherSelect(self, missing, done)))

    def haul_text(self, haul: service.Haul) -> str:
        place = rules.DESTINATIONS[haul.destination].name
        lines = [f"Your character is back from **{place}**" + (" with a lucky find!" if haul.lucky else ".")]
        if not haul.haul:
            lines.append("Rolan's carts were already full today, so there was no room for this load.")
        else:
            if haul.capped:
                lines.append(f"Rolan's carts only had room for {sum(haul.haul.values())} of the "
                             f"{sum(haul.rolled.values())} you brought back.")
            lines += delivery_lines(haul.delivery)
        if haul.perks:
            lines.append(f"Helped by {' and '.join(f'**{name}**' for name in dict.fromkeys(haul.perks))}.")
        lines.append("Send them out again with `$gather`.")
        return "\n".join(lines)

    async def start_run(self, user_id: int, destination: str, hours: int) -> str:
        try:
            run = await service.start_expedition(self.bot.pool, user_id, destination, hours)
        except RebuildError as error:
            return str(error)
        place = rules.DESTINATIONS[destination].name
        return (f"Your character sets out for **{place}**. Back <t:{int(run['returns_at'].timestamp())}:R>; "
                f"then `$gather` to bring the haul home.")

    async def vote_reply(self, user_id: int):
        snap = await service.snapshot(self.bot.pool)
        if not snap["active"]:
            return ("Voting opens when the rebuild does." if not snap["opened"]
                    else "The rebuild is paused, and so is the vote."), None
        if not snap["ballot"]:
            return "There's nothing to vote on right now.", None
        mine = (await service.personal(self.bot.pool, user_id))["vote"]
        note = f" You voted for **{board.name_of(mine)}**; pick again to change it." if mine else ""
        return f"What should Draslin build next?{note}", MenuView(VoteSelect(self, snap["ballot"], mine))

    async def vote_for(self, user_id: int, project_id: str) -> str:
        try:
            await service.cast_vote(self.bot.pool, user_id, project_id)
        except RebuildError as error:
            return str(error)
        self.kick()
        return f"Your vote for **{board.name_of(project_id)}** is in. You can change it until the current project is done."

    async def me_embed(self, user) -> discord.Embed:
        mine = await service.personal(self.bot.pool, user.id)
        embed = discord.Embed(title="Your help rebuilding Draslin", colour=COLOUR)
        embed.add_field(name="All time", value=f"**{mine['total']:,}** materials" + (f" · rank #{mine['rank']}" if mine["rank"] else ""))
        embed.add_field(name="This week", value=f"**{mine['week']:,}**")
        embed.add_field(name="Cart space today", value=f"Supply runs **{mine['gathered_discord_today']}/{mine['discord_cap']}** · "
                                            f"with Tiamat **{mine['gathered_today']}/{mine['cap']}** · "
                                            f"bought **{mine['donated_today']}/{rules.DAILY_DONATE_CAP}**", inline=False)
        run = mine["run"]
        if run:
            back = int(run["returns_at"].timestamp())
            embed.add_field(name="Supply run", value=f"{rules.DESTINATIONS[run['destination']].name}, back <t:{back}:R>",
                            inline=False)
        else:
            embed.add_field(name="Supply run", value="None out. `$gather` to send one.", inline=False)
        embed.add_field(name="Your vote", value=board.name_of(mine["vote"]) if mine["vote"] else "Not cast (`$rebuild vote`)",
                        inline=False)
        home = (await service.homecomings(self.bot.pool, [user.id])).get(user.id, [])
        embed.add_field(name=f"Brought home ({len(home)} of {len(rules.MISSING_NAMES)})", inline=False,
                        value=" · ".join(f"{rules.MISSING_NAMES.get(p, p)}{' ★' if first else ''}" for p, first in home)
                        or "Nobody yet. Follow the calls for help in The Tiamat Sacrament.")
        if any(first for _, first in home):
            embed.set_footer(text="★ You found them first: they're home in Draslin for everyone.")
        return embed

    # ---- commands -----------------------------------------------------------------------------------------
    @checks.has_char()
    @commands.group(name="rebuild", aliases=["draslin"], invoke_without_command=True, hidden=True,
                    brief="Rolan's camp")
    async def rebuild(self, ctx) -> None:
        """Show the rebuild board: the town as it stands, what's being built, the vote and the top builders."""
        if not await self.gate(ctx):
            return
        snap = await service.snapshot(self.bot.pool)
        async with ctx.typing():
            image = await asyncio.to_thread(board.render_board, snap)
        await ctx.send(file=discord.File(image, filename="draslin.png"), view=BoardView(self))

    @checks.has_char()
    @commands.command(name="gather", hidden=True, brief="Send your character on a supply run")
    async def gather(self, ctx, destination: str | None = None, hours: int | None = None) -> None:
        """Collect a finished supply run, or send a new one.

        With no arguments you get a menu. Or name it: `$gather quarry 4`.
        Places: logging (timber), quarry (stone), labs (iron and glass), weavers (cloth). Runs take 1, 4 or 8 hours."""
        if not await self.gate(ctx):
            return
        if destination:
            key = destination.lower()
            key = next((k for k, place in rules.DESTINATIONS.items() if key in (k, place.name.lower())), key)
            # A run that's back is brought home first.
            text, _view = await self.gather_reply(ctx.author.id)
            if _view is None:
                return await ctx.send(text)
            return await ctx.send(await self.start_run(ctx.author.id, key, hours or 1))
        text, view = await self.gather_reply(ctx.author.id)
        await ctx.send(text, view=view or discord.utils.MISSING)

    @checks.has_char()
    @rebuild.command(name="gather", brief="Send your character on a supply run")
    async def rebuild_gather(self, ctx, destination: str | None = None, hours: int | None = None) -> None:
        await ctx.invoke(self.gather, destination, hours)

    @checks.has_char()
    @rebuild.command(name="donate", brief="Buy materials for Draslin with Tiamat crowns")
    async def donate(self, ctx, crowns: int) -> None:
        """Spend Tiamat crowns on materials for the project being built: 1 crown a unit, up to 25 units a day.
        The camp buys what's missing most. Needs a linked Tiamat account; Fable gold becomes crowns in `$rpg`."""
        if not await self.gate(ctx):
            return
        units = crowns // rules.CROWNS_PER_UNIT
        if units <= 0:
            return await ctx.send(f"One unit of materials costs **{rules.CROWNS_PER_UNIT}** crown.")
        if not await ctx.confirm(f"Spend up to 👑 **{units * rules.CROWNS_PER_UNIT:,}** crowns on {units} units of "
                                 f"materials for Draslin?"):
            return
        try:
            delivery, cost = await service.donate(self.bot.pool, ctx.author.id, crowns)
        except RebuildError as error:
            return await ctx.send(str(error))
        self.kick()
        await ctx.send("\n".join([f"You spent 👑 **{cost:,}** crowns on materials for Draslin."] + delivery_lines(delivery)))

    @checks.has_char()
    @rebuild.command(name="vote", brief="Vote on what Draslin builds next")
    async def vote(self, ctx, *, place: str | None = None) -> None:
        """Pick the next project from the ballot. `$rebuild vote 2` or `$rebuild vote library` works too."""
        if not await self.gate(ctx):
            return
        if place:
            snap = await service.snapshot(self.bot.pool)
            ballot = [entry["id"] for entry in snap["ballot"]]
            wanted = place.strip().lower()
            pick = ballot[int(wanted) - 1] if wanted.isdigit() and 0 < int(wanted) <= len(ballot) else next(
                (pid for pid in ballot if wanted in (pid, board.name_of(pid).lower()) or wanted in board.name_of(pid).lower()), None)
            if not pick:
                return await ctx.send("That isn't on the ballot. Run `$rebuild vote` to see it.")
            return await ctx.send(await self.vote_for(ctx.author.id, pick))
        text, view = await self.vote_reply(ctx.author.id)
        await ctx.send(text, view=view or discord.utils.MISSING)

    @checks.has_char()
    @rebuild.command(name="me", aliases=["mine"], brief="Your part in the rebuild")
    async def me(self, ctx) -> None:
        if not await self.gate(ctx):
            return
        await ctx.send(embed=await self.me_embed(ctx.author))

    @rebuild.command(name="perks", brief="What each finished building does for every builder")
    async def perks(self, ctx) -> None:
        """Every building helps the whole town once it's finished. This lists the ones working now and the ones
        still to come, so you can vote for the help you want first."""
        if not await self.gate(ctx):
            return
        async with self.bot.pool.acquire() as conn:
            done = await service.done_projects(conn)
            ballot = [r["id"] for r in await conn.fetch(
                "SELECT id FROM rebuild_projects WHERE town=$1 AND status='ballot' ORDER BY ord", rules.TOWN)]
        working = [f"✨ **{perk.name}** ({board.name_of(pid)}): {perk.text}" for pid, perk in rules.perks_for(done)]
        coming = [f"🗳️ **{board.name_of(pid)}** → {perk.name}: {perk.short}" for pid, perk in rules.perks_for(ballot)]
        later = [f"• {board.name_of(pid)} → {perk.short}" for pid, perk in rules.PERKS.items()
                 if pid not in done and pid not in ballot]
        embed = discord.Embed(title="Perks for every builder", colour=COLOUR)
        embed.add_field(name="Working now", value="\n".join(working) or "None yet. Finish a building!", inline=False)
        if coming:
            embed.add_field(name="On the ballot", value="\n".join(coming), inline=False)
        if later:
            embed.add_field(name="Still to come", value="\n".join(later)[:1024], inline=False)
        embed.set_footer(text=f"Cart space per builder each day: {rules.daily_cap(done)} ({rules.discord_cap(done)} "
                              f"from supply runs; the rest only by playing The Tiamat Sacrament)")
        await ctx.send(embed=embed)

    @rebuild.command(name="haulers", aliases=["races", "hauls"], brief="This week's fastest haul runs in Tiamat")
    async def haulers(self, ctx) -> None:
        """The week's fastest crate of stone from the top of the Mythra trail to Draslin's fountain, raced in
        The Tiamat Sacrament. The game server times every run itself."""
        if not await self.gate(ctx):
            return
        rows = await service.haulers(self.bot.pool)
        lines = [f"{MEDALS.get(r['medal'], '▫️')} **{n}.** {board._who(r)}: {haul_time(r['seconds'])}" for n, r in enumerate(rows, 1)]
        embed = discord.Embed(title="Fastest haulers this week", colour=COLOUR,
                              description="\n".join(lines) or "Nobody's raced a crate down the Mythra trail yet this week.")
        embed.set_footer(text="Race a crate of stone from the top of the Mythra trail to the fountain in Draslin")
        await ctx.send(embed=embed)

    @rebuild.command(name="builders", aliases=["top", "wall"], brief="Everyone who has helped, most first")
    async def builders(self, ctx) -> None:
        if not await self.gate(ctx):
            return
        async with self.bot.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT c.discord_id, p.name, sum(c.amount) AS amount FROM rebuild_contributions c
                   LEFT JOIN profile p ON p."user"=c.discord_id WHERE c.town=$1 AND c.kind <> 'grant'
                   GROUP BY c.discord_id, p.name ORDER BY amount DESC LIMIT 15""", rules.TOWN)
        home = await service.homecomings(self.bot.pool, [r["discord_id"] for r in rows])
        lines = [f"**{n}.** {board._who(dict(r))}: {int(r['amount']):,}"
                 + (f" · 🏠 {len(home[r['discord_id']])}" if home.get(r["discord_id"]) else "") for n, r in enumerate(rows, 1)]
        embed = discord.Embed(title="The Wall of Builders", colour=COLOUR,
                              description="\n".join(lines) or "Nobody yet. Be the first: `$gather`")
        await ctx.send(embed=embed)

    @checks.is_gm()
    @rebuild.command(name="board", brief="GM: post the live rebuild board in this channel")
    async def post_board(self, ctx) -> None:
        """Post the board here (it replaces any old board). It refreshes every couple of minutes, and a card is
        posted here whenever a project is finished. Refused in channels everyone can see (it's a spoiler)."""
        if ctx.guild and ctx.channel.permissions_for(ctx.guild.default_role).view_channel:
            return await ctx.send("Everyone can see this channel, and the rebuild spoils the ending. "
                                  "Use `$rebuild setup` to make Rolan's camp.")
        await self.post_board_in(ctx.channel)

    async def post_board_in(self, channel) -> None:
        snap = await service.snapshot(self.bot.pool)
        image = await asyncio.to_thread(board.render_board, snap)
        async with self.refresh_lock:
            message = await channel.send(file=discord.File(image, filename="draslin.png"), view=self.board_view)
            await service.set_board(self.bot.pool, channel.id, message.id)
            self.board_signature = None
        try:
            await message.pin()
        except discord.HTTPException:
            pass

    @checks.is_gm()
    @rebuild.command(name="scale", brief="GM: more or less material per project, on top of the pacing")
    async def scale(self, ctx, scale: float) -> None:
        """Projects already size themselves so the town takes about five weeks; this multiplies that."""
        try:
            await service.set_scale(self.bot.pool, scale)
        except RebuildError as error:
            return await ctx.send(str(error))
        await ctx.send(f"Projects that start from now on need **×{scale:g}** what the pacing asks for.")

    # ---- the owner opens, pauses and resets ------------------------------------------------------------------
    @is_rebuild_owner()
    @rebuild.command(name="open", brief="Owner: open the rebuild (gathering, donating and the vote)")
    async def open_rebuild(self, ctx) -> None:
        """Open Draslin's rebuild. The first time, this is Day 1. Also reopens it after a pause."""
        if not await ctx.confirm("Open Draslin's rebuild to everyone now?"):
            return
        try:
            first = await service.open_town(self.bot.pool)
        except RebuildError as error:
            return await ctx.send(str(error))
        self.kick()
        await self.announce(ctx, "🔨 **Draslin's rebuild is open!** Day 1 starts now. The vote is open too."
                            if first else "🔨 **The rebuild is open again!** Rolan's crews are back at work.")

    async def announce(self, ctx, text: str) -> None:
        """Tell Rolan's Crew in Rolan's camp, with a ping. The owner gets a short note if they ran it elsewhere."""
        channel_id, _ = await service.board_location(self.bot.pool)
        channel = self.bot.get_channel(channel_id) if channel_id else None
        role = channel.guild.get_role(rules.CREW_ROLE_ID) if channel else None
        if channel is None or role is None:   # no camp yet: say it here, without a ping
            return await ctx.send(text)
        await channel.send(f"{role.mention} {text}", allowed_mentions=discord.AllowedMentions(roles=[role]))
        if ctx.channel.id != channel.id:
            await ctx.send(f"Done. Rolan's Crew has been told in {channel.mention}.")

    @is_rebuild_owner()
    @rebuild.command(name="pause", brief="Owner: pause the rebuild")
    async def pause_rebuild(self, ctx) -> None:
        """Stop gathering, donating and voting until `$rebuild open`. Runs out in the world wait at the camp."""
        try:
            await service.pause_town(self.bot.pool)
        except RebuildError as error:
            return await ctx.send(str(error))
        self.kick()
        await ctx.send("The rebuild is paused.")

    @is_rebuild_owner()
    @rebuild.command(name="reset", brief="Owner: back to the ruins (only before it opens)")
    async def reset_rebuild(self, ctx) -> None:
        """Clear every contribution, vote and run and start from the ruins. Only before the rebuild first opens,
        for setting up and testing. The board stays where it is."""
        if not await ctx.confirm("Clear everything and go back to the ruins?"):
            return
        try:
            await service.reset_town(self.bot.pool, rules.load_projects())
        except RebuildError as error:
            return await ctx.send(str(error))
        self.board_signature = None
        self.kick()
        await ctx.send("Back to the ruins. Everything is cleared.")

    @is_rebuild_owner()
    @rebuild.command(name="setup", brief="Owner: make Rolan's camp channel, lock it to Rolan's Crew, post the board")
    async def setup_rebuild(self, ctx, name: str = rules.CHANNEL_NAME) -> None:
        """Make (or fix) the rebuild channel in this server.

        Only Rolan's Crew can see it: everyone else is shut out, the role can read, talk and use the buttons, and the
        bot can post and pin. An existing channel with that name (or the board's channel) is reused and its
        permissions put right. Then the board is posted and pinned there, and every story finisher gets the role.
        The rebuild stays closed until `$rebuild open`."""
        guild = ctx.guild
        if guild is None:
            return await ctx.send("Run this in the server.")
        role = guild.get_role(rules.CREW_ROLE_ID)
        if role is None:
            return await ctx.send(f"I can't find the Rolan's Crew role (`{rules.CREW_ROLE_ID}`) in this server.")
        me = guild.me
        missing = [label for label, ok in (("Manage Channels", me.guild_permissions.manage_channels),
                                           ("Manage Roles", me.guild_permissions.manage_roles)) if not ok]
        if missing:
            return await ctx.send(f"I need **{' and '.join(missing)}** to set this up.")
        if role >= me.top_role:
            return await ctx.send(f"Move my role above **{role.name}** so I can give it out.",
                                  allowed_mentions=discord.AllowedMentions.none())
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            role: discord.PermissionOverwrite(view_channel=True, read_message_history=True, send_messages=True,
                                              add_reactions=True, use_application_commands=True),
            me: discord.PermissionOverwrite(view_channel=True, read_message_history=True, send_messages=True,
                                            embed_links=True, attach_files=True, manage_messages=True,
                                            add_reactions=True, mention_everyone=True),
        }
        old_channel_id, old_message_id = await service.board_location(self.bot.pool)
        channel = guild.get_channel(old_channel_id) if old_channel_id else None
        channel = channel or discord.utils.get(guild.text_channels, name=name)
        reason = f"Rebuild setup by {ctx.author}"
        try:
            if channel is None:
                channel = await guild.create_text_channel(
                    name, overwrites=overwrites, category=ctx.channel.category, reason=reason,
                    topic="Rolan's camp. Rebuild Draslin together: $gather · $rebuild vote · $rebuild donate · $rebuild me")
                made = "Made"
            else:
                for target, overwrite in overwrites.items():
                    await channel.set_permissions(target, overwrite=overwrite, reason=reason)
                made = "Fixed up"
        except discord.Forbidden:
            return await ctx.send("Discord refused: check my permissions in that category.")
        if old_message_id and old_channel_id:   # one board only
            old = self.bot.get_channel(old_channel_id)
            if old is not None:
                try:
                    await old.get_partial_message(old_message_id).delete()
                except discord.HTTPException:
                    pass
        await self.post_board_in(channel)
        given = await self.sync_crew_role()
        snap = await service.snapshot(self.bot.pool)
        state = "open" if snap["active"] else "paused" if snap["opened"] else "closed until you run `$rebuild open`"
        await ctx.send(f"{made} {channel.mention}: only {role.mention} can see it, and the board is pinned there.\n"
                       f"Gave {role.mention} to **{given}** story finisher{'s' * (given != 1)}. The rebuild is {state}.",
                       allowed_mentions=discord.AllowedMentions.none())

    @checks.is_gm()
    @rebuild.command(name="grant", brief="GM: deliver materials for testing or events")
    async def grant(self, ctx, member: discord.Member, material: str, amount: int) -> None:
        try:
            delivery = await service.grant(self.bot.pool, member.id, material.lower(), amount, by=ctx.author.id)
        except RebuildError as error:
            return await ctx.send(str(error))
        self.kick()
        await ctx.send("\n".join([f"Granted to {member.display_name} (not counted on the Wall)."] + delivery_lines(delivery)))

    # ---- finds from The Tiamat Sacrament --------------------------------------------------------------------
    @tasks.loop(seconds=INBOX_SECONDS)
    async def game_inbox(self) -> None:
        try:
            applied = await service.apply_inbox(self.bot.pool)
        except Exception:
            log.exception("Applying Tiamat finds failed")
            return
        if any(item.delivery for item in applied):
            self.kick()

    @game_inbox.before_loop
    async def before_game_inbox(self) -> None:
        await self.bot.wait_until_ready()

    # ---- Rolan's Crew: the role every story finisher gets --------------------------------------------------
    async def sync_crew_role(self) -> int:
        """Give the role to every finisher in the server that has it. Returns how many got it now."""
        guild = next((g for g in self.bot.guilds if g.get_role(rules.CREW_ROLE_ID)), None)
        if guild is None:
            return 0
        role = guild.get_role(rules.CREW_ROLE_ID)
        async with self.bot.pool.acquire() as conn:
            finishers = await tiamat_unlocks.users_with(conn, tiamat_unlocks.DRAGONKIN)
        given = 0
        for user_id in finishers:
            if user_id in self.crew_done:
                continue
            member = guild.get_member(user_id)
            now = datetime.datetime.now(datetime.timezone.utc)
            if member is None:
                if self.crew_absent.get(user_id, now) > now:
                    continue
                try:
                    member = await guild.fetch_member(user_id)
                except discord.HTTPException:   # not in the server (yet): they get it on joining, or in 6 hours
                    self.crew_absent[user_id] = now + datetime.timedelta(hours=6)
                    continue
            if role not in member.roles:
                try:
                    await member.add_roles(role, reason="Finished The Tiamat Sacrament")
                    given += 1
                except discord.HTTPException:
                    log.warning("Couldn't give Rolan's Crew to %s", user_id)
                    continue
            self.crew_done.add(user_id)
        if given:
            log.info("Gave Rolan's Crew to %s story finisher(s)", given)
        return given

    @commands.Cog.listener()
    async def on_member_join(self, member) -> None:
        role = member.guild.get_role(rules.CREW_ROLE_ID)
        if role is None:
            return
        try:
            async with self.bot.pool.acquire() as conn:
                finished = await tiamat_unlocks.has_unlock(conn, member.id, tiamat_unlocks.DRAGONKIN)
            if finished:
                await member.add_roles(role, reason="Finished The Tiamat Sacrament")
                self.crew_done.add(member.id)
                self.crew_absent.pop(member.id, None)
        except Exception:
            log.exception("Couldn't check Rolan's Crew for a new member")

    @tasks.loop(minutes=CREW_SYNC_MINUTES)
    async def sync_crew(self) -> None:
        try:
            await self.sync_crew_role()
        except Exception:
            log.exception("Rolan's Crew sync failed")

    @sync_crew.before_loop
    async def before_sync_crew(self) -> None:
        await self.bot.wait_until_ready()

    # ---- the live board ---------------------------------------------------------------------------------------
    def kick(self) -> None:
        """Refresh the board soon instead of waiting for the next loop (several kicks make one refresh)."""
        if self.pending_refresh is None or self.pending_refresh.done():
            self.pending_refresh = asyncio.create_task(self.refresh_soon())

    async def refresh_soon(self) -> None:
        await asyncio.sleep(5)
        await self.refresh_now()

    @tasks.loop(minutes=BOARD_REFRESH_MINUTES)
    async def refresh_board(self) -> None:
        await self.refresh_now()

    async def refresh_now(self) -> None:
        async with self.refresh_lock:
            await self._refresh()

    async def _refresh(self) -> None:
        try:
            snap = await service.snapshot(self.bot.pool)
            channel_id, message_id = snap["board"]
            channel = self.bot.get_channel(channel_id) if channel_id else None
            if channel is None:
                return
            for event in await service.pending_events(self.bot.pool):
                text = event_text(event)
                if text:
                    await channel.send(text, allowed_mentions=discord.AllowedMentions.none())
                await service.mark_event_posted(self.bot.pool, event["id"])
            for pid in await service.unannounced(self.bot.pool):
                stats = await service.finish_stats(self.bot.pool, pid)
                progress = {p["id"]: p["progress"] for p in snap["projects"]}
                image = await asyncio.to_thread(board.render_finished, pid, progress, stats)
                await channel.send(file=discord.File(image, filename=f"{pid}-finished.png"))
                await service.mark_announced(self.bot.pool, pid)
            signature = hashlib.sha1(json.dumps({k: snap[k] for k in ("projects", "needs", "ballot", "top", "day",
                                                                       "builders_week", "active", "opened")},
                                                default=str).encode()).hexdigest()
            if signature == self.board_signature:
                return
            image = await asyncio.to_thread(board.render_board, snap)
            try:
                message = channel.get_partial_message(message_id)
                await message.edit(attachments=[discord.File(image, filename="draslin.png")], view=self.board_view)
            except discord.NotFound:
                log.warning("Rebuild board message %s is gone; post a new one with $rebuild board", message_id)
                await service.set_board(self.bot.pool, channel_id, None)
                return
            self.board_signature = signature
        except Exception:
            log.exception("Rebuild board refresh failed")

    @refresh_board.before_loop
    async def before_refresh(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Rebuild(bot))
