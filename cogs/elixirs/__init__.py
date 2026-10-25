"""Battle elixirs from the Fables Library: the shelf, drinking them, and the elixir market.

Elixirs are brewed in a cauldron in the reader's Library home and arrive here as consumables
(utils/elixirs.py has the catalogue and the battle effects). `$elixirs` shows the shelf and
what's working; `$elixir drink` starts one for 2 hours (two at once, never two of
the same). They trade with `$trade` like any consumable, and sell on the elixir market.
"""
from __future__ import annotations

import datetime
import typing

import discord
from discord.ext import commands

from utils import elixirs as lib
from utils.checks import has_char, is_gm
from utils.i18n import _, locale_doc

MAX_LISTINGS = 10
MAX_PRICE = 1_000_000_000
COLOUR = 0x6FBF5A


def _unix(moment: datetime.datetime) -> int:
    return int(moment.timestamp())


class Elixirs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._ready = False

    # The elixirs' icons: emotes named elixir_<id> in any server the bot is in. A cluster only sees
    # its own shards' servers, so whichever sees them writes them to elixir_emojis for the rest.
    async def learn_emojis(self) -> None:
        lib.learn_emojis(self.bot.emojis)
        found = dict(lib.ELIXIR_EMOJI)
        try:
            async with self.bot.pool.acquire() as conn:
                await conn.execute(lib.EMOJI_SQL)
                for elixir_id, markup in found.items():
                    await conn.execute(
                        "INSERT INTO elixir_emojis (elixir, markup) VALUES ($1, $2) "
                        "ON CONFLICT (elixir) DO UPDATE SET markup = EXCLUDED.markup", elixir_id, markup)
                rows = await conn.fetch("SELECT elixir, markup FROM elixir_emojis")
        except Exception:
            return
        for row in rows:
            if row["elixir"] in lib.ELIXIRS and row["elixir"] not in found:
                lib.ELIXIR_EMOJI[row["elixir"]] = row["markup"]

    async def cog_load(self):
        if self.bot.is_ready():
            await self.learn_emojis()

    @commands.Cog.listener()
    async def on_ready(self):
        await self.learn_emojis()

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild, before, after):
        await self.learn_emojis()

    async def ensure_tables(self, conn) -> None:
        if self._ready:
            return
        # A cluster that started before the emotes were found elsewhere picks them up here.
        if not lib.ELIXIR_EMOJI:
            await self.learn_emojis()
        await conn.execute(lib.ACTIVE_SQL)
        await conn.execute(lib.MARKET_SQL)
        self._ready = True

    # ---- helpers ------------------------------------------------------------------------------

    async def shelf(self, conn, user_id: int) -> dict[tuple[str, int], int]:
        rows = await conn.fetch(
            "SELECT consumable_type, SUM(quantity)::int AS quantity FROM user_consumables "
            "WHERE user_id = $1 AND consumable_type LIKE 'elixir\\_%' AND quantity > 0 GROUP BY consumable_type",
            user_id,
        )
        out = {}
        for row in rows:
            parsed = lib.parse_type(row["consumable_type"])
            if parsed:
                out[parsed] = row["quantity"]
        return out

    @staticmethod
    async def take(conn, user_id: int, ctype: str, amount: int) -> bool:
        """Takes amount of a consumable from a player (False if they don't have it). Call in a transaction."""
        rows = await conn.fetch(
            "SELECT id, quantity FROM user_consumables WHERE user_id = $1 AND consumable_type = $2 ORDER BY id FOR UPDATE",
            user_id, ctype,
        )
        if sum(r["quantity"] for r in rows) < amount:
            return False
        left = amount
        for row in rows:
            if left <= 0:
                break
            used = min(left, row["quantity"])
            await conn.execute("UPDATE user_consumables SET quantity = quantity - $1 WHERE id = $2", used, row["id"])
            left -= used
        return True

    @staticmethod
    async def give(conn, user_id: int, ctype: str, amount: int) -> bool:
        """Gives amount of an elixir, up to the stack (False, and nothing given, if it wouldn't fit)."""
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"{user_id}:{ctype}")
        rows = await conn.fetch(
            "SELECT id, quantity FROM user_consumables WHERE user_id = $1 AND consumable_type = $2 ORDER BY id FOR UPDATE",
            user_id, ctype,
        )
        if sum(r["quantity"] for r in rows) + amount > lib.STACK:
            return False
        if rows:
            await conn.execute("UPDATE user_consumables SET quantity = quantity + $1 WHERE id = $2", amount, rows[0]["id"])
        else:
            await conn.execute(
                "INSERT INTO user_consumables (user_id, consumable_type, quantity) VALUES ($1, $2, $3)", user_id, ctype, amount
            )
        return True

    async def resolve(self, ctx, query: str, *, owned: dict | None = None):
        """The elixir and quality a player meant, or None after telling them what went wrong."""
        try:
            elixir_id, quality = lib.find(query)
        except LookupError as many:
            await ctx.send(_("Which one? {names}").format(names=", ".join(many.args[0])))
            return None
        if not elixir_id:
            await ctx.send(_("There's no elixir called `{query}`. See your shelf with `{prefix}elixirs`.").format(
                query=query, prefix=ctx.clean_prefix))
            return None
        if quality is None and owned is not None:
            mine = [q for (e, q), n in owned.items() if e == elixir_id and n > 0]
            if len(mine) == 1:
                quality = mine[0]
            elif len(mine) > 1:
                have = ", ".join(f"{lib.QUALITY_NAMES[q]} ×{owned[(elixir_id, q)]}" for q in sorted(mine))
                await ctx.send(_("You have {have}. Say which: `{prefix}elixir drink gold {name}`.").format(
                    have=have, prefix=ctx.clean_prefix, name=lib.ELIXIRS[elixir_id]["name"].lower()))
                return None
        if quality is None:
            quality = 0 if owned is None else None
        if quality is None:
            await ctx.send(_("You don't have any {name}. Brew it in a cauldron in your Fables Library home.").format(
                name=lib.ELIXIRS[elixir_id]["name"]))
            return None
        return elixir_id, quality

    def name_of(self, user_id: int) -> str:
        user = self.bot.get_user(int(user_id))
        return user.display_name if user else str(user_id)

    # ---- the shelf ----------------------------------------------------------------------------

    @commands.group(invoke_without_command=True, aliases=["elixir"], brief=_("Your Library elixirs and what's working"))
    @has_char()
    @locale_doc
    async def elixirs(self, ctx):
        _(
            """Your battle elixirs, brewed in the Fables Library.

            Brew them in a cauldron in your Library home from crops you grow and fish you catch. Drink one with `{prefix}elixir drink <name>`: it works in every battle for 2 hours. Two can work at once, never two of the same. Gold crops make gold elixirs, twice as strong as plain.

            Trade them with `{prefix}trade`, or sell them on `{prefix}elixir market`."""
        )
        async with self.bot.pool.acquire() as conn:
            await self.ensure_tables(conn)
            owned = await self.shelf(conn, ctx.author.id)
            working = await lib.active(conn, ctx.author.id)
        embed = discord.Embed(title=_("{name}'s elixirs").format(name=ctx.author.display_name), colour=COLOUR)
        if working:
            embed.add_field(
                name=_("Working now ({n} of {max})").format(n=len(working), max=lib.ACTIVE_MAX),
                value="\n".join(
                    f"{lib.label(r['elixir'], r['quality'])}: {lib.effect_text(r['elixir'], r['quality'])} · ends <t:{_unix(r['expires_at'])}:R>"
                    for r in working
                ),
                inline=False,
            )
        if owned:
            lines = [
                f"{lib.label(e, q)} ×{n}: {lib.effect_text(e, q)}"
                for (e, q), n in sorted(owned.items(), key=lambda kv: (lib.ELIXIRS[kv[0][0]]["name"], kv[0][1]))
            ]
            chunk, chunks = [], []
            for line in lines:
                if sum(len(x) + 1 for x in chunk) + len(line) > 1000:
                    chunks.append(chunk)
                    chunk = []
                chunk.append(line)
            chunks.append(chunk)
            for i, part in enumerate(chunks):
                embed.add_field(name=_("On your shelf") if i == 0 else "​", value="\n".join(part), inline=False)
        else:
            embed.description = _("Your shelf is empty. Brew elixirs in a cauldron in your Fables Library home: they arrive here.")
        embed.set_footer(text=_("{prefix}elixir drink <name> · lasts 2 hours · {max} at once · up to {stack} of each").format(
            prefix=ctx.clean_prefix, max=lib.ACTIVE_MAX, stack=lib.STACK))
        await ctx.send(embed=embed)

    @elixirs.command(aliases=["use", "uncork"], brief=_("Drink an elixir: it works in every battle for 2 hours"))
    @has_char()
    @locale_doc
    async def drink(self, ctx, *, elixir: str):
        _(
            """`<elixir>` - the elixir, with its quality if you have more than one: `gold giants stew`, `fire ward`

            Drink an elixir from your shelf. It works in every battle you fight for the next 2 hours, PvE and PvP. Two elixirs can work at once, but never two of the same."""
        )
        async with self.bot.pool.acquire() as conn:
            await self.ensure_tables(conn)
            owned = await self.shelf(conn, ctx.author.id)
            picked = await self.resolve(ctx, elixir, owned=owned)
            if not picked:
                return
            elixir_id, quality = picked
            ctype = lib.type_for(elixir_id, quality)
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"elixir_active:{ctx.author.id}")
                working = await lib.active(conn, ctx.author.id)
                same = next((r for r in working if r["elixir"] == elixir_id), None)
                if same:
                    return await ctx.send(_("{name} is already working for you (ends <t:{t}:R>). Two of the same never stack.").format(
                        name=lib.label(same["elixir"], same["quality"]), t=_unix(same["expires_at"])))
                if len(working) >= lib.ACTIVE_MAX:
                    ends = ", ".join(f"{lib.label(r['elixir'], r['quality'])} (ends <t:{_unix(r['expires_at'])}:R>)" for r in working)
                    return await ctx.send(_("Two elixirs are already working: {ends}. Wait for one to wear off.").format(ends=ends))
                if not await self.take(conn, ctx.author.id, ctype, 1):
                    return await ctx.send(_("You don't have a {name}.").format(name=lib.label(elixir_id, quality, with_emoji=False)))
                expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=lib.ACTIVE_MINUTES)
                await conn.execute(
                    "INSERT INTO elixir_active (user_id, elixir, quality, expires_at) VALUES ($1, $2, $3, $4)",
                    ctx.author.id, elixir_id, quality, expires,
                )
        await ctx.send(_("{label} uncorked! {effect} in every battle until <t:{t}:t> (<t:{t}:R>).").format(
            label=lib.label(elixir_id, quality), effect=lib.effect_text(elixir_id, quality), t=_unix(expires)))

    @elixirs.command(brief=_("What an elixir does at each quality"))
    @locale_doc
    async def info(self, ctx, *, elixir: str):
        _("""`<elixir>` - the elixir's name

            What an elixir does, plain, silver and gold.""")
        picked = await self.resolve(ctx, elixir)
        if not picked:
            return
        elixir_id = picked[0]
        e = lib.ELIXIRS[elixir_id]
        embed = discord.Embed(title=f"{lib.emoji(elixir_id)} {e['name']}", colour=COLOUR)
        for q, name in enumerate(lib.QUALITY_NAMES):
            embed.add_field(name=name, value=lib.effect_text(elixir_id, q), inline=False)
        embed.set_footer(text=_("Brewed in a Fables Library cauldron · lasts 2 hours"))
        await ctx.send(embed=embed)

    # ---- the elixir market ----------------------------------------------------------------------

    @elixirs.command(brief=_("Put elixirs up for sale"))
    @has_char()
    @locale_doc
    async def sell(self, ctx, *, offer: str):
        _(
            """`<elixir> <amount> <price each>` - e.g. `gold giants stew 3 2500`

            List elixirs on the elixir market. They leave your shelf until they sell or you take them back with `{prefix}elixir unlist <id>`."""
        )
        words = offer.split()
        try:
            amount, price = int(words[-2]), int(words[-1])
            query = " ".join(words[:-2])
        except (ValueError, IndexError):
            return await ctx.send(_("Use `{prefix}elixir sell <elixir> <amount> <price each>`, e.g. `gold giants stew 3 2500`.").format(prefix=ctx.clean_prefix))
        if amount < 1 or amount > lib.STACK or price < 1 or price > MAX_PRICE:
            return await ctx.send(_("Amount 1 to {stack}, price 1 to {max:,}.").format(stack=lib.STACK, max=MAX_PRICE))
        async with self.bot.pool.acquire() as conn:
            await self.ensure_tables(conn)
            owned = await self.shelf(conn, ctx.author.id)
            picked = await self.resolve(ctx, query, owned=owned)
            if not picked:
                return
            ctype = lib.type_for(*picked)
            async with conn.transaction():
                listed = await conn.fetchval("SELECT count(*) FROM elixir_market WHERE seller = $1 AND quantity > 0", ctx.author.id)
                if listed >= MAX_LISTINGS:
                    return await ctx.send(_("You already have {n} listings up. Take one down first.").format(n=listed))
                if not await self.take(conn, ctx.author.id, ctype, amount):
                    return await ctx.send(_("You don't have {amount} of those.").format(amount=amount))
                listing = await conn.fetchval(
                    "INSERT INTO elixir_market (seller, consumable_type, quantity, price) VALUES ($1, $2, $3, $4) RETURNING id",
                    ctx.author.id, ctype, amount, price,
                )
        await ctx.send(_("Listed {amount}× {label} at **${price:,}** each (listing #{id}).").format(
            amount=amount, label=lib.label(*picked), price=price, id=listing))

    @elixirs.command(brief=_("Browse elixirs for sale"))
    @locale_doc
    async def market(self, ctx, *, elixir: str = None):
        _("""`[elixir]` - only this elixir (any quality, or name one)

            The elixir market, cheapest first. Buy with `{prefix}elixir buy <id> [amount]`.""")
        async with self.bot.pool.acquire() as conn:
            await self.ensure_tables(conn)
            if elixir:
                try:
                    elixir_id, quality = lib.find(elixir)
                except LookupError as many:
                    return await ctx.send(_("Which one? {names}").format(names=", ".join(many.args[0])))
                if not elixir_id:
                    return await ctx.send(_("There's no elixir called `{query}`.").format(query=elixir))
                pattern = lib.type_for(elixir_id, quality) if quality is not None else f"elixir\\_{elixir_id}\\_%"
                rows = await conn.fetch(
                    "SELECT * FROM elixir_market WHERE quantity > 0 AND consumable_type LIKE $1 ORDER BY price, id LIMIT 20", pattern)
            else:
                rows = await conn.fetch("SELECT * FROM elixir_market WHERE quantity > 0 ORDER BY consumable_type, price, id LIMIT 25")
        embed = discord.Embed(title=_("Elixir market"), colour=COLOUR)
        if not rows:
            embed.description = _("Nothing for sale right now.")
        else:
            lines = []
            for r in rows:
                parsed = lib.parse_type(r["consumable_type"])
                if not parsed:
                    continue
                lines.append(_("`#{id}` {label} ×{n} · **${price:,}** each · {seller}").format(
                    id=r["id"], label=lib.label(*parsed), n=r["quantity"], price=r["price"], seller=self.name_of(r["seller"])))
            embed.description = "\n".join(lines)
        embed.set_footer(text=_("{prefix}elixir buy <id> [amount] · {prefix}elixir sell <elixir> <amount> <price>").format(prefix=ctx.clean_prefix))
        await ctx.send(embed=embed)

    @elixirs.command(brief=_("Buy elixirs from the market"))
    @has_char()
    @locale_doc
    async def buy(self, ctx, listing: int, amount: int = 1):
        _("""`<listing>` - the listing's number, from `{prefix}elixir market`
            `[amount]` - how many (default 1)

            Buy elixirs from the elixir market.""")
        if amount < 1:
            return await ctx.send(_("Buy at least one."))
        async with self.bot.pool.acquire() as conn:
            await self.ensure_tables(conn)
            async with conn.transaction():
                row = await conn.fetchrow("SELECT * FROM elixir_market WHERE id = $1 FOR UPDATE", listing)
                if not row or row["quantity"] <= 0:
                    return await ctx.send(_("That listing is gone."))
                if row["seller"] == ctx.author.id:
                    return await ctx.send(_("That's your own listing. Take it down with `{prefix}elixir unlist {id}`.").format(
                        prefix=ctx.clean_prefix, id=listing))
                if amount > row["quantity"]:
                    return await ctx.send(_("Only {n} left in that listing.").format(n=row["quantity"]))
                parsed = lib.parse_type(row["consumable_type"])
                if not parsed:
                    return await ctx.send(_("That listing is gone."))
                cost = row["price"] * amount
                money = await conn.fetchval('SELECT money FROM profile WHERE "user" = $1 FOR UPDATE', ctx.author.id)
                if money is None or money < cost:
                    return await ctx.send(_("That costs **${cost:,}** and you have **${money:,}**.").format(cost=cost, money=money or 0))
                if not await self.give(conn, ctx.author.id, row["consumable_type"], amount):
                    return await ctx.send(_("That wouldn't fit: you can hold up to {stack} of each elixir.").format(stack=lib.STACK))
                await conn.execute('UPDATE profile SET money = money - $1 WHERE "user" = $2', cost, ctx.author.id)
                await conn.execute('UPDATE profile SET money = money + $1 WHERE "user" = $2', cost, row["seller"])
                await conn.execute("UPDATE elixir_market SET quantity = quantity - $1 WHERE id = $2", amount, listing)
                await conn.execute("DELETE FROM elixir_market WHERE id = $1 AND quantity <= 0", listing)
                await self.bot.log_transaction(
                    ctx, from_=ctx.author.id, to=row["seller"], subject="Elixir Market",
                    data={"Gold": cost, "Elixir": row["consumable_type"], "Amount": amount}, conn=conn,
                )
        await ctx.send(_("You bought {amount}× {label} for **${cost:,}**.").format(amount=amount, label=lib.label(*parsed), cost=cost))
        seller = self.bot.get_user(row["seller"])
        if seller:
            try:
                await seller.send(_("{buyer} bought {amount}× {label} from your elixir listing for **${cost:,}**.").format(
                    buyer=ctx.author.display_name, amount=amount, label=lib.label(*parsed), cost=cost))
            except (discord.Forbidden, discord.HTTPException):
                pass

    @elixirs.command(aliases=["delist", "cancel"], brief=_("Take an elixir listing down"))
    @has_char()
    @locale_doc
    async def unlist(self, ctx, listing: int):
        _("""`<listing>` - your listing's number

            Takes your listing off the elixir market; the elixirs go back on your shelf.""")
        async with self.bot.pool.acquire() as conn:
            await self.ensure_tables(conn)
            async with conn.transaction():
                row = await conn.fetchrow("SELECT * FROM elixir_market WHERE id = $1 AND seller = $2 FOR UPDATE", listing, ctx.author.id)
                if not row or row["quantity"] <= 0:
                    return await ctx.send(_("You have no listing #{id}.").format(id=listing))
                if not await self.give(conn, ctx.author.id, row["consumable_type"], row["quantity"]):
                    return await ctx.send(_("Your shelf can't hold them all (up to {stack} of each). Drink or sell some first.").format(stack=lib.STACK))
                await conn.execute("DELETE FROM elixir_market WHERE id = $1", listing)
        parsed = lib.parse_type(row["consumable_type"])
        await ctx.send(_("Listing #{id} taken down: {n}× {label} back on your shelf.").format(
            id=listing, n=row["quantity"], label=lib.label(*parsed) if parsed else row["consumable_type"]))

    @elixirs.command(aliases=["mylistings"], brief=_("Your elixir listings"))
    @has_char()
    @locale_doc
    async def listings(self, ctx):
        _("""Your elixirs up for sale on the elixir market.""")
        async with self.bot.pool.acquire() as conn:
            await self.ensure_tables(conn)
            rows = await conn.fetch("SELECT * FROM elixir_market WHERE seller = $1 AND quantity > 0 ORDER BY id", ctx.author.id)
        if not rows:
            return await ctx.send(_("You have nothing listed."))
        lines = []
        for r in rows:
            parsed = lib.parse_type(r["consumable_type"])
            if parsed:
                lines.append(f"`#{r['id']}` {lib.label(*parsed)} ×{r['quantity']} · **${r['price']:,}** each")
        await ctx.send(embed=discord.Embed(title=_("Your elixir listings"), description="\n".join(lines), colour=COLOUR))

    @elixirs.command(hidden=True, aliases=["give"], brief=_("Give elixirs (GM)"))
    @is_gm()
    async def grant(self, ctx, user: typing.Optional[discord.User] = None, amount: int = 5, *, elixir: str = "all"):
        """Give elixirs for testing or support. You by default; name someone first for them.

        `$elixir grant` - 5 gold of every elixir to you
        `$elixir grant 3 silver giants stew` - 3 Silver Giant's Stew to you
        `$elixir grant @user 10 all plain` - 10 plain of every elixir to them
        Without a quality it's gold. Anyone already near 99 gets what fits."""
        user = user or ctx.author
        if amount < 1 or amount > lib.STACK:
            return await ctx.send(_("Give 1 to {stack}.").format(stack=lib.STACK))
        words = elixir.casefold().split()
        quality = next((lib.QUALITIES.index(w) for w in words if w in lib.QUALITIES), 2)
        if "all" in words:
            wanted = [(elixir_id, quality) for elixir_id in lib.ELIXIRS]
        else:
            try:
                elixir_id, named = lib.find(elixir)
            except LookupError as many:
                return await ctx.send(_("Which one? {names}").format(names=", ".join(many.args[0])))
            if not elixir_id:
                return await ctx.send(_("There's no elixir called `{query}`.").format(query=elixir))
            wanted = [(elixir_id, quality if named is None else named)]
        given = []
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                for elixir_id, q in wanted:
                    ctype = lib.type_for(elixir_id, q)
                    have = int(await conn.fetchval(
                        "SELECT COALESCE(SUM(quantity), 0) FROM user_consumables WHERE user_id = $1 AND consumable_type = $2",
                        user.id, ctype))
                    n = min(amount, lib.STACK - have)
                    if n > 0 and await self.give(conn, user.id, ctype, n):
                        given.append((elixir_id, q, n))
        if not given:
            return await ctx.send(_("{user} already has {stack} of those.").format(user=user.display_name, stack=lib.STACK))
        if len(given) == 1:
            elixir_id, q, n = given[0]
            return await ctx.send(_("Gave {user} {n}× {label}.").format(user=user.display_name, n=n, label=lib.label(elixir_id, q)))
        await ctx.send(_("Gave {user} {quality} elixirs: {count} kinds, up to {amount} each. See `{prefix}elixirs`.").format(
            user=user.display_name, quality=lib.QUALITY_NAMES[quality].lower(), count=len(given), amount=amount, prefix=ctx.clean_prefix))

    @elixirs.command(hidden=True, aliases=["clearactive"], brief=_("End active elixirs early (GM)"))
    @is_gm()
    async def wearoff(self, ctx, user: discord.User = None):
        """End your (or someone's) active elixirs now, to test again without waiting for them to wear off."""
        user = user or ctx.author
        async with self.bot.pool.acquire() as conn:
            await self.ensure_tables(conn)
            ended = await conn.fetchval(
                "WITH gone AS (UPDATE elixir_active SET expires_at = now() WHERE user_id = $1 AND expires_at > now() RETURNING 1) "
                "SELECT count(*) FROM gone", user.id)
        await ctx.send(_("{n} active elixir(s) on {user} wore off.").format(n=ended, user=user.display_name))


async def setup(bot):
    await bot.add_cog(Elixirs(bot))
