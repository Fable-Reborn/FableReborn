"""Get-well wishes: `$getwell <message>` for the card, `$getwell redeem` for the thank-you.

A sibling of the birthday `$wish` event (cogs/wish), with its own tables, buttons and card. A wish
waits in the review channel until staff approve it (or turn it down, and the player can write
another). An approved wish lets the player pick one reward. A GM opens the event with
`$gmgetwell open 24h`, looks at the card with `$gmgetwell card` and sends it with `$gmgetwell send`.
utils/getwell.py has the rules, cogs/getwell/card.py draws the card.

Players type their wish in any channel of the Fable server; the message is deleted at once and a
confirmation of what they wrote comes back by DM, so nobody (the recipient included) sees it. The
player commands are hidden and do nothing for the recipient, and `$gmgetwell open` refuses to open
while the recipient can see the review channel. Only the review channel can show the card early.
"""
from __future__ import annotations

import asyncio
import datetime
import io
import logging

import asyncpg
import discord
from discord.ext import commands

from utils import elixirs
from utils import getwell as lib
from utils.birthday import parse_birthday_duration
from utils.checks import is_gm
from utils.i18n import _, locale_doc

from . import card

COLOUR = 0xF2B27A
STATUS_COLOURS = {lib.PENDING: 0xF2B27A, lib.APPROVED: 0x57C27A, lib.REJECTED: 0xD9546B, lib.WITHDRAWN: 0x6B6F7A}
VIEW_SECONDS = 180
NO_PINGS = discord.AllowedMentions.none()

log = logging.getLogger(__name__)


class NothingGiven(Exception):
    """Raised inside the reward transaction when not one chosen elixir fits, to roll the claim back."""


# On the group and on every subcommand: discord.py doesn't run a group's checks for its subcommands.
gm_only = commands.check_any(commands.is_owner(), is_gm())


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _unix(moment: datetime.datetime) -> int:
    return int(moment.timestamp())


# ---- staff review ----------------------------------------------------------------------------

class RejectModal(discord.ui.Modal, title="Turn down this wish"):
    reason = discord.ui.TextInput(
        label="Why? (the player sees this)", required=False, max_length=200, style=discord.TextStyle.paragraph,
        placeholder="Optional. They can write a new wish afterwards.")

    def __init__(self, cog: "GetWell"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.review(interaction, approve=False, reason=str(self.reason.value or "").strip() or None)


class ReviewView(discord.ui.View):
    """The Approve / Turn down buttons under a wish in the review channel. The buttons keep working
    after a restart: the wish is found by the message they sit on."""

    def __init__(self, cog: "GetWell"):
        super().__init__(timeout=None)
        self.cog = cog

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only GMs (or the bot owner) can approve or turn down, whoever else can see the channel."""
        if await self.cog.bot.is_owner(interaction.user) or await self.cog.bot.pool.fetchval(
                "SELECT 1 FROM game_masters WHERE user_id = $1", interaction.user.id):
            return True
        await interaction.response.send_message("Only GMs can review wishes.", ephemeral=True)
        return False

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, custom_id=lib.APPROVE_ID)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.review(interaction, approve=True)

    @discord.ui.button(label="Turn down", style=discord.ButtonStyle.danger, custom_id=lib.REJECT_ID)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RejectModal(self.cog))


# ---- choosing a reward -----------------------------------------------------------------------

class RedeemView(discord.ui.View):
    """Pick one of the three rewards, then confirm. The elixir reward opens the shelf, which shows
    what every elixir does: choose a quality, then add up to lib.REWARD_ELIXIRS elixirs, any of
    them, the same one more than once if wanted. Nothing is
    given until Confirm, and the choice can't be changed after it."""

    def __init__(self, cog: "GetWell", ctx, wish_id: int):
        super().__init__(timeout=VIEW_SECONDS)
        self.cog, self.ctx, self.wish_id = cog, ctx, wish_id
        self.choice: str | None = None
        self.picks: list[tuple[str, int]] = []   # (elixir id, quality), in the order they were added
        self.quality = lib.DEFAULT_QUALITY       # the quality the next elixir is added at
        self.message: discord.Message | None = None
        self.build()

    def build(self):
        self.clear_items()
        if self.choice is None:
            self.add(_("3 Divine + 3 Fortune crates"), discord.ButtonStyle.primary, self.pick_crates, emoji="\U0001F381")
            self.add(_("{n} elixirs of your choice").format(n=lib.REWARD_ELIXIRS), discord.ButtonStyle.primary,
                     self.pick_elixirs, emoji="\U0001F9EA")
        elif self.choice == "elixirs":
            if len(self.picks) < lib.REWARD_ELIXIRS:
                shelf = discord.ui.Select(
                    placeholder=_("Add a {quality} elixir ({n} of {most} chosen)").format(
                        quality=elixirs.QUALITY_NAMES[self.quality].lower(), n=len(self.picks), most=lib.REWARD_ELIXIRS),
                    options=self.cog.shelf_options(self.quality), row=0)
                shelf.callback = self.add_elixir
                self.add_item(shelf)
                grade = discord.ui.Select(placeholder=_("Quality"), options=self.cog.quality_options(self.quality), row=1)
                grade.callback = self.set_quality
                self.add_item(grade)
            self.add(_("Confirm"), discord.ButtonStyle.success, self.confirm, disabled=not self.picks, row=2)
            self.add(_("Remove last"), discord.ButtonStyle.secondary, self.remove_last, disabled=not self.picks, row=2)
            self.add(_("Back"), discord.ButtonStyle.secondary, self.back, row=2)
        else:
            self.add(_("Confirm"), discord.ButtonStyle.success, self.confirm)
            self.add(_("Back"), discord.ButtonStyle.secondary, self.back)

    def add(self, label, style, callback, **kwargs):
        button = discord.ui.Button(label=label, style=style, **kwargs)
        button.callback = callback
        self.add_item(button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.ctx.author.id:
            return True
        await interaction.response.send_message(_("This is someone else's reward."), ephemeral=True)
        return False

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass

    async def redraw(self, interaction: discord.Interaction):
        self.build()
        await interaction.response.edit_message(
            embed=self.cog.redeem_embed(self.ctx, self.choice, self.picks, self.quality), view=self)

    async def pick_crates(self, interaction: discord.Interaction):
        self.choice = "crates"
        await self.redraw(interaction)

    async def pick_elixirs(self, interaction: discord.Interaction):
        self.choice = "elixirs"
        await self.redraw(interaction)

    async def back(self, interaction: discord.Interaction):
        self.choice = None
        await self.redraw(interaction)

    async def add_elixir(self, interaction: discord.Interaction):
        chosen = (interaction.data or {}).get("values") or []
        if chosen and chosen[0] in elixirs.ELIXIRS and len(self.picks) < lib.REWARD_ELIXIRS:
            self.picks.append((chosen[0], self.quality))
        await self.redraw(interaction)

    async def set_quality(self, interaction: discord.Interaction):
        chosen = (interaction.data or {}).get("values") or []
        if chosen and chosen[0] in {str(i) for i in range(len(elixirs.QUALITIES))}:
            self.quality = int(chosen[0])
        await self.redraw(interaction)

    async def remove_last(self, interaction: discord.Interaction):
        if self.picks:
            self.picks.pop()
        await self.redraw(interaction)

    async def confirm(self, interaction: discord.Interaction):
        choice, self.choice = self.choice, None
        self.stop()
        await interaction.response.defer()
        text = await self.cog.give_reward(self.ctx, self.wish_id, choice, self.picks)
        await interaction.edit_original_response(
            embed=discord.Embed(title=_("\U0001F490 Thank you for your wish"), description=text, colour=COLOUR), view=None)


# ---- the cog ---------------------------------------------------------------------------------

class GetWell(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.review_view = ReviewView(self)

    async def cog_load(self):
        async with self.bot.pool.acquire() as conn:
            await conn.execute(lib.TABLE_SQL)
        self.bot.add_view(self.review_view)

    async def cog_unload(self):
        self.review_view.stop()

    # ---- helpers ----------------------------------------------------------------------------------

    async def event(self, conn=None):
        """The event row (closes_at, recipient_name, delivered_at), or None before it's ever opened."""
        return await (conn or self.bot.pool).fetchrow("SELECT * FROM getwell_event WHERE id = 1")

    @staticmethod
    def is_open(event) -> bool:
        return bool(event and event["closes_at"] and event["closes_at"] > _now())

    async def member(self, user_id: int) -> dict | None:
        """The user's member object in the Fable server (works from any cluster), or None if they aren't in it."""
        try:
            return await self.bot.http.get_member(lib.GUILD_ID, user_id)
        except discord.NotFound:
            return None

    async def open_wish(self, conn, user_id: int):
        """The user's wish that is waiting or approved, if any. Its "rewarded" says whether they have
        already had their gift, for this wish or an earlier one that was taken off the card."""
        return await conn.fetchrow(
            "SELECT wish.*, EXISTS (SELECT 1 FROM getwell_wishes other WHERE other.user_id = wish.user_id "
            "AND other.reward IS NOT NULL) AS rewarded "
            "FROM getwell_wishes wish WHERE wish.user_id = $1 AND wish.status = ANY($2::text[])",
            user_id, [lib.PENDING, lib.APPROVED])

    def review_channel(self):
        return self.bot.get_partial_messageable(lib.REVIEW_CHANNEL_ID)

    async def recipient_id(self, event=None) -> int:
        """Who the card is for: the player a GM set with `$gmgetwell for`, else the fallback in utils/getwell.py (0 if neither)."""
        event = event or await self.event()
        return int((event["recipient_id"] if event else None) or lib.RECIPIENT_ID or 0)

    def review_embed(self, row) -> discord.Embed:
        status = row["status"]
        embed = discord.Embed(title=f"\U0001F490 Get well wish #{row['id']}", description=f">>> {row['message']}",
                              colour=STATUS_COLOURS.get(status, COLOUR))
        embed.add_field(name="From", value=f"<@{row['user_id']}> (`{row['user_id']}`)")
        embed.add_field(name="Signed as", value=discord.utils.escape_markdown(row["author_name"]))
        if status == lib.PENDING:
            embed.set_footer(text="Approve to put it on the card and let them pick a reward. "
                                  "Turn down anything unkind, and anything that gives away private details.")
        elif status == lib.WITHDRAWN:
            embed.set_footer(text="Withdrawn by the player.")
        else:
            verdict = "Approved" if status == lib.APPROVED else "Turned down"
            embed.add_field(name=verdict, value=f"by <@{row['reviewed_by']}>" + (f"\n{row['reason']}" if row["reason"] else ""), inline=False)
        return embed

    async def tell(self, user_id: int, text: str) -> bool:
        """DMs a player. False if they can't be reached."""
        user = await self.bot.get_user_global(user_id)
        if user is None:
            return False
        try:
            await user.send(embed=discord.Embed(title="\U0001F490 Your get well wish", description=text, colour=COLOUR))
            return True
        except (discord.Forbidden, discord.HTTPException):
            return False

    # ---- keeping it out of sight ------------------------------------------------------------------

    @staticmethod
    async def delete_invoker(ctx):
        """Deletes the command message, if it's in a server. Always done, so a wish that gets turned
        down (or any command) never stays up in a channel for the recipient to come across."""
        if ctx.guild is None:
            return
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            log.warning("Could not delete a get well command message in guild %s (missing Manage Messages?)", ctx.guild.id)

    async def route(self, ctx, *, dm_only: bool = False, in_server: bool = False) -> bool:
        """Whether a player command may go ahead. The command message is always deleted first.

        - The recipient gets nothing at all, not even a reply: any answer could give the game away.
        - in_server (sending a wish): only in the Fable server, so the message can be deleted.
        - dm_only (redeem): only in a DM with the bot, so the menu isn't
          posted in a channel the recipient might be reading.
        Otherwise the author is told, by DM when they're in a server.
        """
        await self.delete_invoker(ctx)
        if ctx.author.id == await self.recipient_id():
            return False
        if in_server and (ctx.guild is None or ctx.guild.id != lib.GUILD_ID):
            await self.private(ctx, _("Send your wish in the Fable server: your message is deleted the moment you send it."))
            return False
        if dm_only and ctx.guild is not None:
            await self.private(ctx, _("Send `{prefix}getwell redeem` here, in this DM.").format(prefix=ctx.clean_prefix))
            return False
        return True

    async def private(self, ctx, content: str | None = None, *, embed: discord.Embed | None = None) -> bool:
        """Says something to the player in a DM, not in the channel where others read. If their DMs
        are closed it goes in the channel for a few seconds instead, with no wish text in it.
        True if it reached them by DM."""
        try:
            await ctx.author.send(content, embed=embed)
            return True
        except (discord.Forbidden, discord.HTTPException):
            if ctx.guild is not None:
                await ctx.send(_("{user}, I couldn't DM you. Open your DMs from server members and try again.").format(
                    user=ctx.author.mention), delete_after=10, allowed_mentions=NO_PINGS)
            return False

    # ---- review -----------------------------------------------------------------------------------

    async def review(self, interaction: discord.Interaction, *, approve: bool, reason: str | None = None):
        """Approve or turn down the wish under the message the button (or its form) belongs to."""
        async with self.bot.pool.acquire() as conn:
            row = await conn.fetchrow(
                "UPDATE getwell_wishes SET status = $2, reviewed_by = $3, reviewed_at = now(), reason = $4 "
                "WHERE review_message_id = $1 AND status = $5 RETURNING *",
                interaction.message.id, lib.APPROVED if approve else lib.REJECTED, interaction.user.id, reason, lib.PENDING)
            current = row or await conn.fetchrow(
                "SELECT * FROM getwell_wishes WHERE review_message_id = $1", interaction.message.id)
        if current is None:
            return await interaction.response.send_message("That wish isn't in the book any more.", ephemeral=True)
        await interaction.response.edit_message(embed=self.review_embed(current), view=None)
        if row is None:   # someone else got there first, or the player withdrew it
            return await interaction.followup.send("That wish was already dealt with.", ephemeral=True)

        prefix = self.bot.config.bot.global_prefix
        if approve:
            rewarded = await self.bot.pool.fetchval(
                "SELECT 1 FROM getwell_wishes WHERE user_id = $1 AND reward IS NOT NULL LIMIT 1", row["user_id"])
            gift = _("You've already had your thank-you gift.") if rewarded else _(
                "Pick your thank-you gift by sending `{prefix}getwell redeem` here, in this DM.").format(prefix=prefix)
            reached = await self.tell(row["user_id"], _(
                "Your wish was approved and is going on the card. Thank you!") + "\n\n" + gift)
        else:
            reached = await self.tell(row["user_id"], _(
                "Your wish wasn't put on the card.{why}\n\n"
                "You can write a new one with `{prefix}getwell <message>` while wishes are open."
            ).format(prefix=prefix, why=f"\n> {reason}" if reason else ""))
        if not reached:
            await interaction.followup.send(
                f"<@{row['user_id']}> has DMs closed, so they weren't told. They can still check with `{prefix}getwell status`.",
                ephemeral=True, allowed_mentions=NO_PINGS)

    # ---- rewards ----------------------------------------------------------------------------------

    def crates_text(self) -> str:
        crates = self.bot.get_cog("Crates")
        parts = []
        for rarity, amount in lib.REWARD_CRATES.items():
            emote = getattr(getattr(crates, "emotes", None), rarity, "")
            parts.append(f"- **{amount}** {emote} {rarity} crates".replace("  ", " "))
        return "\n".join(parts)

    @staticmethod
    def elixirs_line() -> str:
        return _("- **{n}** elixirs of your choice: any of the {kinds}, at any quality").format(
            n=lib.REWARD_ELIXIRS, kinds=len(elixirs.ELIXIRS))

    def rewards_text(self) -> str:
        """The three rewards, for a player to read before choosing."""
        return self.crates_text() + "\n" + _("**or**") + "\n" + self.elixirs_line()

    @staticmethod
    def picks_text(picks) -> str:
        """The chosen elixirs, one line a kind and quality: "Gold Giant's Stew x2"."""
        counts: dict[tuple[str, int], int] = {}
        for pick in picks:
            counts[tuple(pick)] = counts.get(tuple(pick), 0) + 1
        return "\n".join(f"- {elixirs.label(elixir_id, quality)}" + (f" ×{n}" if n > 1 else "")
                         for (elixir_id, quality), n in counts.items())

    @staticmethod
    def shelf_text() -> str:
        """Every elixir and what it does, as plain/silver/gold."""
        return "\n".join(f"**{entry['name']}** · {elixirs.effect_text(elixir_id)}" for elixir_id, entry in elixirs.ELIXIRS.items())

    @staticmethod
    def shelf_options(quality: int) -> list[discord.SelectOption]:
        """The elixirs as menu options, each with what it does at that quality under its name."""
        options = []
        for elixir_id, entry in elixirs.ELIXIRS.items():
            try:
                icon = discord.PartialEmoji.from_str(elixirs.emoji(elixir_id))
            except Exception:
                icon = None
            options.append(discord.SelectOption(label=entry["name"][:100], value=elixir_id, emoji=icon,
                                                description=elixirs.effect_text(elixir_id, quality)[:100]))
        return options

    @staticmethod
    def quality_options(current: int) -> list[discord.SelectOption]:
        notes = (_("The base effect"), _("One and a half times plain"), _("Twice plain: the strongest"))
        return [discord.SelectOption(label=_("{quality} quality").format(quality=name), value=str(i),
                                     description=notes[i], default=i == current)
                for i, name in enumerate(elixirs.QUALITY_NAMES)]

    def redeem_embed(self, ctx, choice: str | None, picks=(), quality: int = lib.DEFAULT_QUALITY) -> discord.Embed:
        final = _("This is your one reward and can't be changed afterwards.")
        if choice == "elixirs":
            left = lib.REWARD_ELIXIRS - len(picks)
            lines = [_(
                "**Choose up to {n} elixirs.** Any you like, the same one more than once if you want. "
                "Set the quality in the second menu, then add elixirs from the first: each is added at the quality showing "
                "(now **{quality}**). Each lasts {minutes} minutes once you drink it."
            ).format(n=lib.REWARD_ELIXIRS, quality=elixirs.QUALITY_NAMES[quality].lower(), minutes=elixirs.ACTIVE_MINUTES), ""]
            lines.append(_("**Your elixirs ({n} of {most})**").format(n=len(picks), most=lib.REWARD_ELIXIRS))
            lines.append(self.picks_text(picks) if picks else _("*None yet. Add them from the menu below.*"))
            if picks and left:
                lines.append(_("*You can still add {left} more. Confirm now and the rest are not given.*").format(left=left))
            lines += ["", _("**What each elixir does** (plain / silver / gold)"), self.shelf_text()]
            embed = discord.Embed(title=_("\U0001F9EA Elixirs of your choice"), colour=COLOUR, description="\n".join(lines)[:4096])
            embed.set_footer(text=_("Confirm gives you the elixirs listed under Your elixirs. ") + final)
            return embed
        if choice == "crates":
            return discord.Embed(title=_("Take the crates?"), colour=COLOUR, description=self.crates_text() + "\n\n" + final)
        embed = discord.Embed(title=_("\U0001F490 Thank you for your wish"), colour=COLOUR,
                              description=_("Your wish is on the card. Pick **one** thank-you gift:"))
        embed.add_field(name=_("\U0001F381 Crates"), value=self.crates_text(), inline=False)
        embed.add_field(name=_("\U0001F9EA Elixirs"), value=self.elixirs_line(), inline=False)
        return embed

    @staticmethod
    async def give_elixir(conn, user_id: int, ctype: str) -> bool:
        """One of an elixir, unless the player's stack of it is full. Call in a transaction."""
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"{user_id}:{ctype}")
        rows = await conn.fetch(
            "SELECT id, quantity FROM user_consumables WHERE user_id = $1 AND consumable_type = $2 ORDER BY id FOR UPDATE",
            user_id, ctype)
        if sum(r["quantity"] for r in rows) + 1 > elixirs.STACK:
            return False
        if rows:
            await conn.execute("UPDATE user_consumables SET quantity = quantity + 1 WHERE id = $1", rows[0]["id"])
        else:
            await conn.execute(
                "INSERT INTO user_consumables (user_id, consumable_type, quantity) VALUES ($1, $2, 1)", user_id, ctype)
        return True

    async def claim(self, conn, wish_id: int, user_id: int, reward: str) -> bool:
        """Marks the wish as rewarded with reward. False if this player has already had a reward.
        Only get-well wishes count: a birthday reward doesn't use this one up."""
        return await conn.fetchval(
            "UPDATE getwell_wishes SET reward = $4, redeemed_at = now() "
            "WHERE id = $1 AND user_id = $2 AND status = $3 AND reward IS NULL AND NOT EXISTS (SELECT 1 FROM "
            "getwell_wishes other WHERE other.user_id = $2 AND other.reward IS NOT NULL) RETURNING id",
            wish_id, user_id, lib.APPROVED, reward) is not None

    async def give_reward(self, ctx, wish_id: int, choice: str, picks=()) -> str:
        """Gives the chosen reward, once: the crates or the elixirs in picks.
        Returns what to tell the player."""
        user_id = ctx.author.id
        taken = _("You've already picked your reward for this wish.")
        again = _("Start again with `{prefix}getwell redeem`.").format(prefix=ctx.clean_prefix)
        if choice == "crates":
            async with self.bot.pool.acquire() as conn:
                async with conn.transaction():
                    if not await self.claim(conn, wish_id, user_id, "crates"):
                        return taken
                    await conn.execute(
                        'UPDATE profile SET crates_divine = crates_divine + $1, crates_fortune = crates_fortune + $2 WHERE "user" = $3',
                        lib.REWARD_CRATES["divine"], lib.REWARD_CRATES["fortune"], user_id)
                    for rarity, amount in lib.REWARD_CRATES.items():
                        await self.bot.log_transaction(ctx, from_=1, to=user_id, subject="crates",
                                                       data={"Rarity": rarity, "Amount": amount}, conn=conn)
            return (_("Added to your character:") + "\n" + self.crates_text() + "\n\n"
                    + _("Open them with `{prefix}crates`.").format(prefix=ctx.clean_prefix))

        if choice != "elixirs":
            return _("That isn't one of the rewards. ") + again
        try:
            picks = lib.check_picks(picks)
        except ValueError:
            return _("That isn't a choice of elixirs I can give. ") + again
        if not picks:
            return _("You didn't choose any elixirs. ") + again
        given, full = [], []
        try:
            async with self.bot.pool.acquire() as conn:
                async with conn.transaction():
                    if not await self.claim(conn, wish_id, user_id, "elixirs"):
                        return taken
                    for elixir_id, quality in picks:
                        fits = await self.give_elixir(conn, user_id, lib.elixir_type(elixir_id, quality))
                        (given if fits else full).append((elixir_id, quality))
                    if not given:
                        raise NothingGiven   # undoes the claim: their reward isn't spent on nothing
        except NothingGiven:
            return _("You already hold {stack} of every elixir you chose, so none could be added and your reward is still yours. ").format(
                stack=elixirs.STACK) + again
        text = _("Added to your character:") + "\n" + self.picks_text(given)
        if full:
            text += "\n\n" + _("Left out, because you already hold {stack} of them:").format(stack=elixirs.STACK) + "\n" + self.picks_text(full)
        return text + "\n\n" + _("See them with `{prefix}elixirs`, drink one with `{prefix}elixir drink`.").format(prefix=ctx.clean_prefix)

    # ---- player commands --------------------------------------------------------------------------

    @commands.group(invoke_without_command=True, hidden=True, aliases=["gw"], brief=_("Write a get well wish for the card"))
    @locale_doc
    async def getwell(self, ctx, *, message: str = None):
        _(
            """`<message>` - your wish, up to 200 characters

            Writes your wish for the card. Staff read every wish before it goes on. Once yours is approved you get a DM, and `{prefix}getwell redeem` lets you pick a thank-you gift: 3 divine and 3 fortune crates, or 8 elixirs of your choice at any quality.

            One wish each. Send it in any channel of the Fable server, on your main account: your message is deleted the moment you send it, and the bot DMs you what you wrote."""
        )
        if not message:
            if await self.route(ctx):
                await self.show_status(ctx)
            return
        if not await self.route(ctx, in_server=True):
            return
        async with self.bot.pool.acquire() as conn:
            event = await self.event(conn)
            mine = await self.open_wish(conn, ctx.author.id)
        if not await self.bot.pool.fetchval('SELECT 1 FROM profile WHERE "user" = $1', ctx.author.id):
            return await self.private(ctx, _("You need a character to send a wish. Make one with `{prefix}create`.").format(
                prefix=ctx.clean_prefix))
        if not self.is_open(event):
            return await self.private(ctx, _("Wishes aren't open right now."))
        if mine and mine["status"] == lib.PENDING:
            return await self.private(ctx, _("Your wish is already waiting to be read. To change it, `{prefix}getwell withdraw` and write it again.").format(
                prefix=ctx.clean_prefix))
        if mine:
            hint = _("Thank you!") if mine["rewarded"] else _("Your reward is waiting: `{prefix}getwell redeem`.").format(prefix=ctx.clean_prefix)
            return await self.private(ctx, _("Your wish is already on the card. ") + hint)

        try:
            member = await self.member(ctx.author.id)
        except discord.HTTPException:
            return await self.private(ctx, _("Discord didn't answer just now. Try again in a moment."))
        problem = lib.not_eligible(member)
        if problem == "not_member":
            return await self.private(ctx, _("Wishes are for members of the Fable server."))
        if problem == "alt":
            return await self.private(ctx, _("Alt accounts can't send a wish. Send it from your main account."))

        try:
            text = lib.check_message(message)
        except lib.WishProblem as bad:
            code = bad.args[0]
            if code == lib.WishProblem.LINK:
                return await self.private(ctx, _("Wishes can't have links in them."))
            if code == lib.WishProblem.LONG:
                return await self.private(ctx, _("That's {over} character(s) over the {limit} that fit on the card. Trim it a little and send it again.").format(
                    over=bad.args[1], limit=lib.MAX_LENGTH))
            return await self.private(ctx, _("Write a few words for your wish: `{prefix}getwell <message>`.").format(
                prefix=ctx.clean_prefix))

        name = lib.display_name(member, ctx.author.display_name)
        async with self.bot.pool.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    "INSERT INTO getwell_wishes (user_id, author_name, message) VALUES ($1, $2, $3) RETURNING *",
                    ctx.author.id, name, text)
            except asyncpg.UniqueViolationError:
                return await self.private(ctx, _("You've already sent a wish."))
        try:
            posted = await self.review_channel().send(embed=self.review_embed(row), view=self.review_view,
                                                      allowed_mentions=NO_PINGS)
        except discord.HTTPException:
            log.exception("Could not post get well wish %s for review", row["id"])
            await self.bot.pool.execute("DELETE FROM getwell_wishes WHERE id = $1", row["id"])
            return await self.private(ctx, _("Your wish couldn't be passed on just now. Please send it again in a moment."))
        await self.bot.pool.execute("UPDATE getwell_wishes SET review_message_id = $2 WHERE id = $1", row["id"], posted.id)
        # The message is already gone from the channel, so the confirmation (with what they wrote) goes by DM.
        confirmation = discord.Embed(
            title=_("\U0001F48C Your wish is in"), colour=COLOUR,
            description=f">>> {text}\n\n" + _(
                "Signed as **{name}**. Staff read every wish before it goes on the card: you'll get a DM when it's approved, "
                "and then you can pick your thank-you gift by sending `{prefix}getwell redeem` here in this DM. "
                "Changed your mind? `{prefix}getwell withdraw` takes it back while it's waiting."
            ).format(name=discord.utils.escape_markdown(name), prefix=ctx.clean_prefix))
        if not await self.private(ctx, embed=confirmation):
            await ctx.send(_("\U0001F48C {user}, your wish was received.").format(user=ctx.author.mention),
                           delete_after=10, allowed_mentions=NO_PINGS)

    async def show_status(self, ctx):
        async with self.bot.pool.acquire() as conn:
            event = await self.event(conn)
            mine = await self.open_wish(conn, ctx.author.id)
        embed = discord.Embed(title=_("\U0001F490 Get well wishes"), colour=COLOUR)
        if self.is_open(event):
            embed.description = _(
                "Write a few words for the card: `{prefix}getwell <message>` (up to {limit} characters, "
                "in any channel of the Fable server; your message is deleted straight away)."
            ).format(prefix=ctx.clean_prefix, limit=lib.MAX_LENGTH)
        else:
            embed.description = _("Wishes aren't open right now.")
        if mine is None:
            state = _("You haven't sent one yet.")
        elif mine["status"] == lib.PENDING:
            state = _("Waiting to be read by staff. You'll get a DM.")
        elif not mine["rewarded"]:
            state = _("On the card! Pick your gift with `{prefix}getwell redeem`.").format(prefix=ctx.clean_prefix)
        else:
            state = _("On the card, and your gift is claimed. Thank you!")
        embed.add_field(name=_("Your wish"), value=state, inline=False)
        embed.add_field(name=_("The thank-you gift (pick one)"), value=self.rewards_text(), inline=False)
        await self.private(ctx, embed=embed)

    @getwell.command(name="status", hidden=True, brief=_("Where your wish is"))
    @locale_doc
    async def getwell_status(self, ctx):
        _("""Whether wishes are open, where your wish is, and what the thank-you gift is.""")
        if await self.route(ctx):
            await self.show_status(ctx)

    @getwell.command(name="withdraw", hidden=True, aliases=["cancel"], brief=_("Take your wish back before it's read"))
    @locale_doc
    async def getwell_withdraw(self, ctx):
        _("""Takes your wish back while it's still waiting to be read, so you can write it again.""")
        if not await self.route(ctx):
            return
        row = await self.bot.pool.fetchrow(
            "UPDATE getwell_wishes SET status = $2 WHERE user_id = $1 AND status = $3 RETURNING *",
            ctx.author.id, lib.WITHDRAWN, lib.PENDING)
        if row is None:
            return await self.private(ctx, _("You don't have a wish waiting to be read."))
        if row["review_message_id"]:
            try:
                await self.review_channel().get_partial_message(row["review_message_id"]).edit(
                    embed=self.review_embed(row), view=None)
            except discord.HTTPException:
                pass
        await self.private(ctx, _("Your wish is withdrawn. Write it again with `{prefix}getwell <message>`.").format(prefix=ctx.clean_prefix))

    @getwell.command(name="redeem", hidden=True, aliases=["claim", "reward"], brief=_("Pick your thank-you gift"))
    @locale_doc
    async def getwell_redeem(self, ctx):
        _(
            """Pick the thank-you gift for your approved wish: 3 divine and 3 fortune crates, or 8 elixirs of your choice at any quality. Send it in a DM with the bot.

            You can see what every elixir does before you choose. One gift, and the choice is final."""
        )
        if not await self.route(ctx, dm_only=True):
            return
        async with self.bot.pool.acquire() as conn:
            mine = await self.open_wish(conn, ctx.author.id)
            rewarded = await conn.fetchval(
                "SELECT 1 FROM getwell_wishes WHERE user_id = $1 AND reward IS NOT NULL LIMIT 1", ctx.author.id)
        if mine is None and rewarded:
            return await self.private(ctx, _("You've already picked your gift. Thank you!"))
        if mine is None:
            return await self.private(ctx, _("You don't have a wish on the card. Write one with `{prefix}getwell <message>`.").format(prefix=ctx.clean_prefix))
        if mine["status"] == lib.PENDING:
            return await self.private(ctx, _("Your wish is still waiting to be read. You'll get a DM when it's approved."))
        if rewarded:
            return await self.private(ctx, _("You've already picked your gift. Thank you!"))
        # Always in a DM (see route), so the menu isn't posted in a channel the recipient might be reading.
        view = RedeemView(self, ctx, mine["id"])
        view.message = await ctx.send(embed=self.redeem_embed(ctx, None), view=view)

    # ---- GM commands ------------------------------------------------------------------------------

    @commands.group(invoke_without_command=True, hidden=True, brief=_("Run the get well wishes (GM)"))
    @gm_only
    async def gmgetwell(self, ctx):
        """Where the get well wishes stand, and the commands that run them."""
        async with self.bot.pool.acquire() as conn:
            event = await self.event(conn)
            counts = dict(await conn.fetch("SELECT status, COUNT(*) FROM getwell_wishes GROUP BY status"))
            # A reward stays with the player even if their wish is later taken off the card.
            rewards = dict(await conn.fetch(
                "SELECT reward, COUNT(*) FROM getwell_wishes WHERE reward IS NOT NULL GROUP BY reward"))
            rewards["unclaimed"] = await conn.fetchval(
                "SELECT COUNT(*) FROM getwell_wishes wish WHERE wish.status = $1 AND NOT EXISTS ("
                "SELECT 1 FROM getwell_wishes other WHERE other.user_id = wish.user_id AND other.reward IS NOT NULL)", lib.APPROVED)
        p = ctx.clean_prefix
        if self.is_open(event):
            state = f"Open, closes <t:{_unix(event['closes_at'])}:R>."
        elif event and event["closes_at"]:
            state = f"Closed <t:{_unix(event['closes_at'])}:R>."
        else:
            state = "Never opened."
        if event and event["delivered_at"]:
            state += f" Card sent <t:{_unix(event['delivered_at'])}:R>."
        missing = lib.unset_ids()
        if missing:
            state += f"\n**Not set up yet** (utils/getwell.py): {', '.join(missing)}."
        recipient_id = await self.recipient_id(event)
        embed = discord.Embed(title="\U0001F490 Get well wishes", description=state, colour=COLOUR)
        embed.add_field(name="Wishes", value=(
            f"{counts.get(lib.APPROVED, 0)} approved · {counts.get(lib.PENDING, 0)} waiting for review · "
            f"{counts.get(lib.REJECTED, 0)} turned down · {counts.get(lib.WITHDRAWN, 0)} withdrawn"), inline=False)
        embed.add_field(name="Rewards picked", value=(
            f"{rewards.get('crates', 0)} crates · {rewards.get('elixirs', 0)} elixirs · "
            f"{rewards.get('unclaimed', 0)} not picked yet"), inline=False)
        embed.add_field(name="Card", value=(
            (f"Goes to <@{recipient_id}>" if recipient_id else f"No recipient yet: `{p}gmgetwell for @player`")
            + (f" as **{event['recipient_name']}**" if event and event["recipient_name"] else "")), inline=False)
        embed.add_field(name="Commands", value=(
            f"`{p}gmgetwell for @player [name]` - who the card is for (and the name on it)\n"
            f"`{p}gmgetwell open [duration]` - start taking wishes; without a length it stays open until you close it\n"
            f"`{p}gmgetwell close` - stop taking wishes\n"
            f"`{p}gmgetwell card` - draw the card, only in <#{lib.REVIEW_CHANNEL_ID}>\n"
            f"`{p}gmgetwell remove <wish #>` - take an approved wish off the card\n"
            f"`{p}gmgetwell send` - send the card to the recipient"), inline=False)
        await ctx.send(embed=embed, allowed_mentions=NO_PINGS)

    async def recipient_can_see(self, ctx, recipient_id: int) -> str | None:
        """What stops the event from opening: a sentence saying the recipient can see the review
        channel (where every wish is posted), or that this can't be checked. None when they can't
        see it, or aren't in the server at all."""
        try:
            member = await ctx.guild.fetch_member(recipient_id)
        except discord.NotFound:
            return None
        except discord.HTTPException:
            return "I couldn't look up the recipient just now, so I can't check what they can see. Try again in a moment."
        channel = ctx.guild.get_channel(lib.REVIEW_CHANNEL_ID)
        if channel is None:
            return f"I can't find the review channel (<#{lib.REVIEW_CHANNEL_ID}>) in this server, so I can't check it."
        if channel.permissions_for(member).view_channel:
            return f"The recipient can see <#{lib.REVIEW_CHANNEL_ID}>, where every wish is posted. Hide it from them first, then open again."
        return None

    @gmgetwell.command(name="for", hidden=True)
    @gm_only
    async def gm_for(self, ctx, player: discord.User, *, name: str = None):
        """`$gmgetwell for @player Sam` - who the card is for, and the name on it (their display name if you leave it out)."""
        name = " ".join(str(name or player.display_name).split())[:40]
        await self.bot.pool.execute(
            "INSERT INTO getwell_event (id, recipient_id, recipient_name) VALUES (1, $1, $2) "
            "ON CONFLICT (id) DO UPDATE SET recipient_id = $1, recipient_name = $2", player.id, name)
        await ctx.send(f"The card is for **{discord.utils.escape_markdown(name)}**. "
                       f"Open wishes with `{ctx.clean_prefix}gmgetwell open`.", allowed_mentions=NO_PINGS)

    @gmgetwell.command(name="open", hidden=True)
    @gm_only
    async def gm_open(self, ctx, duration: str = None):
        """`$gmgetwell open` - players can send wishes until you `close` it. `$gmgetwell open 3d` closes it by itself after that long."""
        if ctx.guild is None or ctx.guild.id != lib.GUILD_ID:
            return await ctx.send("Open this from the Fable server, so I can check who can see the review channel.")
        missing = lib.unset_ids()
        if missing:
            return await ctx.send(f"Not set up yet. Fill in {', '.join(f'`{name}`' for name in missing)} in `utils/getwell.py` and reload.")
        recipient_id = await self.recipient_id()
        if not recipient_id:
            return await ctx.send(f"Say who it's for first: `{ctx.clean_prefix}gmgetwell for @player`.")
        try:
            length = parse_birthday_duration(duration) if duration else datetime.timedelta(days=lib.OPEN_ENDED_DAYS)
        except ValueError as bad:
            return await ctx.send(str(bad))
        # Every wish is posted in the review channel, so it isn't opened while the recipient can see it.
        problem = await self.recipient_can_see(ctx, recipient_id)
        if problem:
            return await ctx.send(problem, allowed_mentions=NO_PINGS)
        closes = _now() + length
        await self.bot.pool.execute(
            "INSERT INTO getwell_event (id, closes_at) VALUES (1, $1) ON CONFLICT (id) DO UPDATE SET closes_at = $1", closes)
        until = f"until <t:{_unix(closes)}:F> (<t:{_unix(closes)}:R>)" if duration else f"until you run `{ctx.clean_prefix}gmgetwell close`"
        await ctx.send(f"Wishes are open {until}. Players use `{ctx.clean_prefix}getwell <message>` in any channel of this server; "
                       f"wishes land in <#{lib.REVIEW_CHANNEL_ID}> for approval.", allowed_mentions=NO_PINGS)

    @gmgetwell.command(name="close", hidden=True)
    @gm_only
    async def gm_close(self, ctx):
        """Stops taking wishes now. Waiting wishes can still be approved, and rewards can still be picked."""
        await self.bot.pool.execute(
            "INSERT INTO getwell_event (id, closes_at) VALUES (1, now()) ON CONFLICT (id) DO UPDATE SET closes_at = now()")
        await ctx.send("Wishes are closed. Waiting wishes can still be approved, and rewards can still be picked.")

    @gmgetwell.command(name="name", hidden=True)
    @gm_only
    async def gm_name(self, ctx, *, name: str = None):
        """`$gmgetwell name Sam` - the name on the card. Without a name it goes back to the usual one."""
        name = " ".join(str(name or "").split())[:40] or None
        await self.bot.pool.execute(
            "INSERT INTO getwell_event (id, recipient_name) VALUES (1, $1) ON CONFLICT (id) DO UPDATE SET recipient_name = $1", name)
        await ctx.send(f"The card will say **Get well soon, {name or await self.recipient_name()}**.")

    @gmgetwell.command(name="remove", hidden=True)
    @gm_only
    async def gm_remove(self, ctx, wish: int, *, reason: str = None):
        """`$gmgetwell remove 12` - takes an approved wish off the card (say, one that gives away private details). A reward already picked stays with the player."""
        row = await self.bot.pool.fetchrow(
            "UPDATE getwell_wishes SET status = $2, reviewed_by = $3, reviewed_at = now(), reason = $4 "
            "WHERE id = $1 AND status = $5 RETURNING *",
            wish, lib.REJECTED, ctx.author.id, reason or "Removed from the card.", lib.APPROVED)
        if row is None:
            return await ctx.send(f"There's no approved wish #{wish}.")
        if row["review_message_id"]:
            try:
                await self.review_channel().get_partial_message(row["review_message_id"]).edit(embed=self.review_embed(row), view=None)
            except discord.HTTPException:
                pass
        await ctx.send(f"Wish #{wish} is off the card.")

    async def recipient_name(self) -> str:
        """The name on the card: the one a GM set with `$gmgetwell name`, else the usual one."""
        event = await self.event()
        return (event["recipient_name"] if event else None) or lib.RECIPIENT_NAME or "Friend"

    async def avatar(self, user_id: int, gate: asyncio.Semaphore) -> bytes | None:
        async with gate:
            try:
                user = await self.bot.get_user_global(user_id)
                if user is None:
                    return None
                return await user.display_avatar.replace(size=128, static_format="png").read()
            except Exception:   # the card still gets drawn, with their initial instead
                return None

    async def draw_pages(self) -> list[tuple[bytes, str]]:
        """The card's pages from every approved wish, oldest first, as (image bytes, filename). Empty when there are none."""
        rows = await self.bot.pool.fetch(
            "SELECT user_id, author_name, message FROM getwell_wishes WHERE status = $1 ORDER BY created_at, id", lib.APPROVED)
        if not rows:
            return []
        gate = asyncio.Semaphore(6)
        avatars = await asyncio.gather(*(self.avatar(r["user_id"], gate) for r in rows))
        wishes = [dict(name=r["author_name"], message=r["message"], avatar=a) for r, a in zip(rows, avatars)]
        return await asyncio.to_thread(card.render_cards, await self.recipient_name(), wishes)

    @staticmethod
    def as_files(pages: list[tuple[bytes, str]]) -> list[discord.File]:
        """Fresh upload objects for the pages (a File can only be sent once)."""
        return [discord.File(io.BytesIO(data), filename=filename) for data, filename in pages]

    @gmgetwell.command(name="card", hidden=True, aliases=["preview"])
    @gm_only
    async def gm_card(self, ctx):
        """Draws the card from the wishes approved so far and posts it here, in the review channel only. Nothing is sent to the recipient."""
        if ctx.channel.id != lib.REVIEW_CHANNEL_ID:
            return await ctx.send(f"The card can only be previewed in <#{lib.REVIEW_CHANNEL_ID}>.")
        async with ctx.typing():
            pages = await self.draw_pages()
        if not pages:
            return await ctx.send("No approved wishes yet, so there's no card to draw.")
        await ctx.send(f"The card as it stands ({len(pages)} page(s)). Not sent to anyone.")
        for file in self.as_files(pages):   # one a message: each can be close to Discord's upload limit
            await ctx.send(file=file)

    @gmgetwell.command(name="send", hidden=True, aliases=["deliver"])
    @gm_only
    async def gm_send(self, ctx):
        """Sends the card to the recipient in a DM. Asks first."""
        async with self.bot.pool.acquire() as conn:
            event = await self.event(conn)
            recipient_id = await self.recipient_id(event)
            if not recipient_id:
                return await ctx.send(f"Say who it's for first: `{ctx.clean_prefix}gmgetwell for @player`.")
            waiting = await conn.fetchval("SELECT COUNT(*) FROM getwell_wishes WHERE status = $1", lib.PENDING)
            approved = await conn.fetchval("SELECT COUNT(*) FROM getwell_wishes WHERE status = $1", lib.APPROVED)
        if not approved:
            return await ctx.send("No approved wishes yet, so there's no card to send.")
        notes = []
        if waiting:
            notes.append(f"**{waiting}** wish(es) are still waiting for review and won't be on it.")
        if self.is_open(event):
            notes.append("Wishes are still open.")
        if event and event["delivered_at"]:
            notes.append(f"The card was already sent <t:{_unix(event['delivered_at'])}:R>; this sends it again.")
        question = f"Send the card with **{approved}** wish(es) to the recipient now?" + "".join(f"\n{n}" for n in notes)
        if not await ctx.confirm(question):
            return
        recipient = await self.bot.get_user_global(recipient_id)
        if recipient is None:
            return await ctx.send("I can't find the recipient on Discord.")
        async with ctx.typing():
            pages = await self.draw_pages()
        try:
            await recipient.send(
                f"\U0001F490 **Get well soon!** {approved} people across Fable wrote you a wish while you rest up. This is from all of them.")
            for file in self.as_files(pages):
                await recipient.send(file=file)
        except discord.Forbidden:
            return await ctx.send("Their DMs are closed, so the card wasn't sent. Use "
                                  f"`{ctx.clean_prefix}gmgetwell card` and pass it on by hand.")
        await self.bot.pool.execute(
            "INSERT INTO getwell_event (id, delivered_at) VALUES (1, now()) ON CONFLICT (id) DO UPDATE SET delivered_at = now()")
        await ctx.send("The card is with the recipient. \U0001F490", allowed_mentions=NO_PINGS)


async def setup(bot):
    await bot.add_cog(GetWell(bot))
