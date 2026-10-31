"""Pet art requests: ask for one of your pets to get its own walking sprite in the Fables Library.

`$petart request <pet>` puts its species in the drawing queue (one every 4 weeks; cancelling or a
turned-down request gives the turn back). When the sprite is live, every pet of that species walks
in the Library, and the reader who asked gets a DM. utils/pet_art.py has the rules.

A request finishes two ways: a GM marks it with `$petart complete`, or the sprite shows up in the
Library's PetSprites.json, which this checks every half hour. Either way the DM goes out once:
whichever cluster flips the row to done is the one that sends it.
"""
from __future__ import annotations

import datetime
import io
import json
import logging

import asyncpg
import discord
from discord.ext import commands, tasks

from utils import pet_art as lib
from utils.checks import has_char, is_gm
from utils.i18n import _, locale_doc

COLOUR = 0xC9A86A
CHECK_MINUTES = 30
QUEUE_SHOWN = 25

log = logging.getLogger(__name__)


def _unix(moment: datetime.datetime) -> int:
    return int(moment.timestamp())


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class PetArt(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        async with self.bot.pool.acquire() as conn:
            await conn.execute(lib.TABLE_SQL)
        self.check_sprites.start()

    async def cog_unload(self):
        self.check_sprites.cancel()

    # ---- the Library's sprite list -------------------------------------------------------------

    async def drawn_keys(self) -> set[str] | None:
        """Species keys the Library already has sprites for, or None if the list can't be read."""
        try:
            async with self.bot.session.get(lib.SPRITES_URL, timeout=15) as resp:
                if resp.status != 200:
                    return None
                return lib.drawn_keys(json.loads(await resp.text()))
        except Exception:   # timeouts, bad JSON, the site being down: try again next time
            return None

    @tasks.loop(minutes=CHECK_MINUTES)
    async def check_sprites(self):
        try:
            keys = await self.drawn_keys()
            if keys:
                await self.finish(keys=sorted(keys), by=None)
        except Exception:
            log.exception("Pet art sprite check failed")

    @check_sprites.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    async def finish(self, *, keys=None, ids=None, by: int | None) -> list:
        """Marks open requests done (by species key or request id) and DMs whoever asked."""
        async with self.bot.pool.acquire() as conn:
            rows = await conn.fetch(
                "UPDATE pet_art_requests SET status = 'done', finished_at = now(), finished_by = $3 "
                "WHERE status IN ('queued', 'drawing') AND (species_key = ANY($1::text[]) OR id = ANY($2::int[])) "
                "RETURNING *",
                list(keys or []), list(ids or []), by,
            )
        for row in rows:
            await self.tell(row["user_id"], _(
                "\U0001F3A8 **Your {pet} has been drawn!**\n"
                "{species} now has its own walking sprite in the Fables Library. Equip it with "
                "`$pets equip {id}` and it walks beside you, and so does every {species} out there.\n"
                "You can request another pet <t:{next}:R>."
            ).format(pet=row["pet_name"], species=row["species"], id=row["pet_id"],
                     next=_unix(lib.next_request_at(row["requested_at"]))))
        return rows

    async def tell(self, user_id: int, text: str) -> None:
        user = await self.bot.get_user_global(user_id)
        if user is None:
            return
        try:
            await user.send(text)
        except (discord.Forbidden, discord.HTTPException):
            pass

    # ---- helpers ----------------------------------------------------------------------------------

    async def last_counted(self, conn, user_id: int):
        return await conn.fetchrow(
            "SELECT * FROM pet_art_requests WHERE user_id = $1 AND status = ANY($2::text[]) AND NOT waived "
            "ORDER BY requested_at DESC LIMIT 1",
            user_id, list(lib.COUNTED),
        )

    async def open_request(self, conn, user_id: int):
        return await conn.fetchrow(
            "SELECT * FROM pet_art_requests WHERE user_id = $1 AND status = ANY($2::text[]) "
            "ORDER BY requested_at DESC LIMIT 1",
            user_id, list(lib.OPEN),
        )

    async def position(self, conn, row) -> int:
        return int(await conn.fetchval(
            "SELECT COUNT(*) FROM pet_art_requests WHERE status = ANY($1::text[]) AND requested_at <= $2",
            list(lib.OPEN), row["requested_at"],
        ))

    def status_line(self, row, position: int | None = None) -> str:
        if row["status"] == "drawing":
            return _("**{pet}** ({species}) is being drawn right now.").format(pet=row["pet_name"], species=row["species"])
        return _("**{pet}** ({species}) is in the queue, number {n}.").format(
            pet=row["pet_name"], species=row["species"], n=position or "?")

    # ---- player commands --------------------------------------------------------------------------

    @commands.group(invoke_without_command=True, aliases=["petsprite"], brief=_("Ask for your pet to be drawn walking in the Library"))
    @has_char()
    @locale_doc
    async def petart(self, ctx):
        _(
            """Every pet you equip follows you through the Fables Library. Ask for one to get its own hand-drawn walking sprite.

            `{prefix}petart request <pet>` puts it in the drawing queue. When it's drawn, every pet of that species walks in the Library, not just yours, and you get a DM.

            One request every 4 weeks. Cancel with `{prefix}petart cancel` and you get your turn back."""
        )
        await self.show_status(ctx)

    @petart.command(brief=_("Where your request is, and when you can ask again"))
    @has_char()
    @locale_doc
    async def status(self, ctx):
        _("""Where your pet art request is in the queue, and when you can make your next one.""")
        await self.show_status(ctx)

    async def show_status(self, ctx):
        async with self.bot.pool.acquire() as conn:
            open_row = await self.open_request(conn, ctx.author.id)
            position = await self.position(conn, open_row) if open_row else None
            last = await self.last_counted(conn, ctx.author.id)
            waiting = await conn.fetchval("SELECT COUNT(*) FROM pet_art_requests WHERE status = ANY($1::text[])", list(lib.OPEN))
        embed = discord.Embed(title=_("Pet art requests"), colour=COLOUR)
        if open_row:
            embed.description = self.status_line(open_row, position)
        else:
            embed.description = _("Every pet you equip already follows you in the Fables Library as its portrait. "
                                  "Request one and it gets its own walking sprite.")
        upcoming = lib.next_request_at(last["requested_at"]) if last else None
        if upcoming and upcoming > _now():
            embed.add_field(name=_("Your next request"), value=f"<t:{_unix(upcoming)}:D> (<t:{_unix(upcoming)}:R>)", inline=False)
        else:
            embed.add_field(name=_("Your next request"), value=_("Ready now: `{prefix}petart request <pet>`").format(prefix=ctx.clean_prefix), inline=False)
        embed.set_footer(text=_("{n} pet(s) waiting to be drawn · one request every 4 weeks").format(n=waiting))
        await ctx.send(embed=embed)

    @petart.command(aliases=["ask"], brief=_("Put one of your pets in the drawing queue"))
    @has_char()
    @locale_doc
    async def request(self, ctx, *, pet: str):
        _(
            """`<pet>` - your pet's ID or alias (see `{prefix}pets`)

            Puts your pet's species in the drawing queue. When its walking sprite is ready, every pet of that species walks in the Fables Library, and you get a DM. One request every 4 weeks."""
        )
        pets_cog = self.bot.get_cog("Pets")
        async with self.bot.pool.acquire() as conn:
            if pets_cog is not None:
                row, _pet_id = await pets_cog.fetch_pet_for_user(conn, ctx.author.id, pet)
            else:
                row = await conn.fetchrow("SELECT * FROM monster_pets WHERE user_id = $1 AND id = $2",
                                          ctx.author.id, int(pet) if pet.strip().isdigit() else -1)
            if row is None:
                return await ctx.send(_("You don't have a pet `{pet}`. Use its ID or alias from `{prefix}pets`.").format(
                    pet=pet, prefix=ctx.clean_prefix))
            details = lib.pet_details(row)

            open_row = await self.open_request(conn, ctx.author.id)
            if open_row:
                return await ctx.send(_("You already have a request in: {line} Cancel it with `{prefix}petart cancel` to swap.").format(
                    line=self.status_line(open_row, await self.position(conn, open_row)), prefix=ctx.clean_prefix))
            last = await self.last_counted(conn, ctx.author.id)
            upcoming = lib.next_request_at(last["requested_at"]) if last else None
            if upcoming and upcoming > _now():
                return await ctx.send(_("Your next request opens <t:{at}:D> (<t:{at}:R>).").format(at=_unix(upcoming)))

            taken = await conn.fetchrow(
                "SELECT * FROM pet_art_requests WHERE species_key = $1 AND status = ANY($2::text[]) LIMIT 1",
                details["species_key"], list(lib.OPEN))
            if taken:
                return await ctx.send(_("**{species}** is already in the queue. When it's drawn, your {pet} walks too. "
                                        "Your turn is still yours: pick another pet.").format(pet=details["pet_name"], species=details["species"]))
        drawn = await self.drawn_keys()
        if drawn and details["species_key"] in drawn:
            return await ctx.send(_("**{species}** is already drawn! Equip {pet} and it walks beside you in the Fables Library.").format(pet=details["pet_name"], species=details["species"]))
        if not details["portrait"]:
            return await ctx.send(_("{pet} doesn't have a picture yet, so there's nothing to draw from. Pick another pet.").format(pet=details["pet_name"], species=details["species"]))

        async with self.bot.pool.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    "INSERT INTO pet_art_requests (user_id, pet_id, pet_name, species, species_key, element, portrait) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *",
                    ctx.author.id, details["pet_id"], details["pet_name"], details["species"], details["species_key"],
                    details["element"], details["portrait"])
            except asyncpg.UniqueViolationError:
                return await ctx.send(_("**{species}** was just put in the queue by someone else. When it's drawn, your {pet} walks too.").format(pet=details["pet_name"], species=details["species"]))
            position = await self.position(conn, row)
        embed = discord.Embed(
            title=_("\U0001F3A8 {pet} is in the queue").format(pet=details["pet_name"]),
            description=_("**{species}** is number {n} in line to be drawn. When its walking sprite is ready, you'll get a DM, "
                          "and every {species} in the Fables Library will walk.").format(species=details["species"], n=position),
            colour=COLOUR)
        if details["portrait"]:
            embed.set_thumbnail(url=details["portrait"])
        embed.set_footer(text=_("Changed your mind? {prefix}petart cancel gives your turn back.").format(prefix=ctx.clean_prefix))
        await ctx.send(embed=embed)

    @petart.command(aliases=["withdraw"], brief=_("Withdraw your request and get your turn back"))
    @has_char()
    @locale_doc
    async def cancel(self, ctx):
        _("""Withdraws your pet art request before it's drawn. Your turn comes back, so you can request another pet straight away.""")
        async with self.bot.pool.acquire() as conn:
            row = await conn.fetchrow(
                "UPDATE pet_art_requests SET status = 'cancelled', finished_at = now() "
                "WHERE id = (SELECT id FROM pet_art_requests WHERE user_id = $1 AND status = 'queued' "
                "ORDER BY requested_at DESC LIMIT 1) RETURNING *",
                ctx.author.id)
            drawing = None if row else await conn.fetchrow(
                "SELECT * FROM pet_art_requests WHERE user_id = $1 AND status = 'drawing' LIMIT 1", ctx.author.id)
        if row:
            return await ctx.send(_("Withdrew **{pet}** ({species}). Your turn is back: `{prefix}petart request <pet>`.").format(
                pet=row["pet_name"], species=row["species"], prefix=ctx.clean_prefix))
        if drawing:
            return await ctx.send(_("**{pet}** is already being drawn, so it can't be withdrawn now.").format(pet=drawing["pet_name"]))
        await ctx.send(_("You don't have a request in."))

    # ---- GM commands ------------------------------------------------------------------------------

    @petart.command(hidden=True, brief=_("The drawing queue (GM)"))
    @is_gm()
    async def queue(self, ctx):
        """Open requests, oldest first: request number, species, who asked."""
        async with self.bot.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM pet_art_requests WHERE status = ANY($1::text[]) ORDER BY requested_at", list(lib.OPEN))
        if not rows:
            return await ctx.send(_("The queue is empty."))
        lines = [
            f"`#{r['id']}` {'✏️' if r['status'] == 'drawing' else '⏳'} **{r['species']}** (`{r['species_key']}`) "
            f"· {r['pet_name']} · <@{r['user_id']}> · <t:{_unix(r['requested_at'])}:R>"
            for r in rows[:QUEUE_SHOWN]
        ]
        drawing = sum(1 for r in rows if r["status"] == "drawing")
        embed = discord.Embed(title=_("Pet art queue"), description="\n".join(lines), colour=COLOUR)
        embed.set_footer(text=_("{n} waiting · {d} being drawn · $petart batch [count] · $petart complete <#id or species>").format(
            n=len(rows) - drawing, d=drawing))
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @petart.command(hidden=True, brief=_("Start a batch and get its requests.json (GM)"))
    @is_gm()
    async def batch(self, ctx, count: int = 40, *, name: str = None):
        """Marks the oldest waiting requests as being drawn and attaches the batch file.

        Save the file as reports/hub-art/pets/<batch>/requests.json, the same shape tools/pets/requests.py writes,
        and import the finished sheets with tools/pets/import_sprites.py as usual. Once they're live in the
        Library, the requests finish by themselves (or use `$petart complete`)."""
        if count < 1 or count > 200:
            return await ctx.send(_("Pick 1 to 200."))
        year, week, _day = _now().isocalendar()
        name = (name or f"{year}-W{week:02d}").strip()[:40]
        async with self.bot.pool.acquire() as conn:
            rows = await conn.fetch(
                "UPDATE pet_art_requests SET status = 'drawing', batch = $2 WHERE id IN ("
                "SELECT id FROM pet_art_requests WHERE status = 'queued' ORDER BY requested_at LIMIT $1) RETURNING *",
                count, name)
            # Anything already being drawn rides along, so the file is the whole batch.
            rows = await conn.fetch(
                "SELECT * FROM pet_art_requests WHERE status = 'drawing' ORDER BY requested_at")
        if not rows:
            return await ctx.send(_("Nothing waiting to be drawn."))
        data = lib.batch_file(rows, name, _now())
        file = discord.File(io.BytesIO(json.dumps(data, indent=1, ensure_ascii=False).encode("utf-8")), filename="requests.json")
        await ctx.send(_("**{n}** pet(s) being drawn in batch `{batch}`. Save this as `reports/hub-art/pets/{batch}/requests.json`.").format(
            n=len(rows), batch=name), file=file)

    @petart.command(hidden=True, aliases=["done"], brief=_("Mark requests drawn and DM whoever asked (GM)"))
    @is_gm()
    async def complete(self, ctx, *, which: str):
        """`$petart complete 12` (a request number), `$petart complete 12 15 19`, or `$petart complete <species name>`."""
        parts = which.replace(",", " ").replace("#", " ").split()
        if parts and all(p.isdigit() for p in parts):
            rows = await self.finish(ids=[int(p) for p in parts], by=ctx.author.id)
        else:
            rows = await self.finish(keys=[lib.species_key(which)], by=ctx.author.id)
        if not rows:
            return await ctx.send(_("No open request matches `{which}`.").format(which=which))
        await ctx.send(_("Marked drawn and told them: {names}").format(
            names=", ".join(f"**{r['species']}** (#{r['id']})" for r in rows)))

    @petart.command(hidden=True, brief=_("Turn down a request and give the turn back (GM)"))
    @is_gm()
    async def reject(self, ctx, request: int, *, reason: str = None):
        """`$petart reject 12 the portrait is too dark to draw from` - the reader gets the reason and their turn back."""
        async with self.bot.pool.acquire() as conn:
            row = await conn.fetchrow(
                "UPDATE pet_art_requests SET status = 'rejected', reason = $2, finished_at = now(), finished_by = $3 "
                "WHERE id = $1 AND status = ANY($4::text[]) RETURNING *",
                request, reason, ctx.author.id, list(lib.OPEN))
        if not row:
            return await ctx.send(_("No open request #{n}.").format(n=request))
        await self.tell(row["user_id"], _(
            "Your pet art request for **{pet}** ({species}) couldn't be drawn this time.{why}\n"
            "Your turn is back, so you can request another pet now."
        ).format(pet=row["pet_name"], species=row["species"], why=f"\n> {reason}" if reason else ""))
        await ctx.send(_("Turned down #{n} ({species}) and gave the turn back.").format(n=row["id"], species=row["species"]))

    @petart.command(hidden=True, brief=_("Let someone request again now (GM)"))
    @is_gm()
    async def reset(self, ctx, user: discord.User):
        """Lets them make their next request straight away. Their open request, if any, stays in the queue."""
        async with self.bot.pool.acquire() as conn:
            changed = await conn.execute(
                "UPDATE pet_art_requests SET waived = TRUE WHERE user_id = $1 AND status IN ('done', 'drawing', 'queued')", user.id)
        await ctx.send(_("{user} can request again now ({changed}).").format(user=user.display_name, changed=changed.split()[-1]))


async def setup(bot):
    await bot.add_cog(PetArt(bot))
