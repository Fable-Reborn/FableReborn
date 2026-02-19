"""
The IdleRPG Discord Bot
Copyright (C) 2018-2021 Diniboy and Gelbpunkt
Copyright (C) 2023-2024 Lunar (PrototypeX37)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
import asyncio

from collections import defaultdict

import discord

from discord.ext import commands

from classes.converters import CrateRarity, IntGreaterThan, MemberWithCharacter
from utils.i18n import _, locale_doc
# Add this import for deep copy
import copy


def has_no_transaction():
    async def predicate(ctx):
        return not ctx.bot.cogs["Transaction"].get_transaction(ctx.author)

    return commands.check(predicate)


def has_transaction():
    async def predicate(ctx):
        ctx.transaction = ctx.bot.cogs["Transaction"].get_transaction(ctx.author)
        return ctx.transaction

    return commands.check(predicate)


class Transaction(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.transactions = {}

    def get_transaction(self, user, return_id=False):
        id_ = str(user.id)
        if not (key := discord.utils.find(lambda x: id_ in x, self.transactions)):
            return None
        if return_id:
            return key
        return self.transactions[key]["content"][user]

    async def _get_linked_trade_actor_ids(
        self, participant_ids: list[int]
    ) -> dict[int, set[int]]:
        actor_ids_by_participant = {
            int(participant_id): {int(participant_id)}
            for participant_id in participant_ids
        }
        if not participant_ids:
            return actor_ids_by_participant

        try:
            rows = await self.bot.pool.fetch(
                """
                SELECT main, alt
                FROM alt_links
                WHERE main = ANY($1::bigint[]) OR alt = ANY($1::bigint[])
                """,
                participant_ids,
            )
        except Exception:
            return actor_ids_by_participant

        for row in rows:
            main_id = int(row["main"])
            alt_id = int(row["alt"])
            if main_id in actor_ids_by_participant:
                actor_ids_by_participant[main_id].add(alt_id)
            if alt_id in actor_ids_by_participant:
                actor_ids_by_participant[alt_id].add(main_id)

        return actor_ids_by_participant

    async def update(self, ctx):
        id_ = self.get_transaction(ctx.author, return_id=True)
        content = "\n\n".join(
            [
                _(
                    """\
> {user} gives:
{money}{crates}{items}{resources}{consumables}"""
                ).format(
                    user=user.mention,
                    money=f"- **${m}**\n" if (m := cont["money"]) else "",
                    crates="".join(
                        [
                            f"- **{i}** {getattr(self.bot.cogs['Crates'].emotes, j)}\n"
                            for j, i in cont["crates"].items()
                        ]
                    ),
                    items="".join(
                        [
                            f"- {i['name']} ({i['type']}, {i['damage'] + i['armor']})\n"
                            for i in cont["items"]
                        ]
                    ),
                    resources="".join(
                        [
                            f"- **{amount}x** {resource.replace('_', ' ').title()}\n"
                            for resource, amount in cont["resources"].items()
                        ]
                    ),
                    consumables="".join(
                        [
                            f"- **{amount}x** {ctype.replace('_', ' ').title()} (Premium)\n"
                            for ctype, amount in cont.get("consumables", {}).items() if amount > 0
                        ]
                    ),
                )
                for user, cont in self.transactions[id_]["content"].items()
            ]
        )
        content = (
            content
            + "\n\n"
            + _(
                "Use `{prefix}trade [add/set/remove] [money/crates/item/resources/consumable]"
                " [amount/itemid/resource_name/consumable_type] [crate rarity]`"
            ).format(prefix=ctx.clean_prefix)
        )
        if (base := self.transactions[id_]["base"]) is not None:
            await base.delete()
        self.transactions[id_]["base"] = await ctx.send(content)
        if (task := self.transactions[id_]["task"]) is not None:
            task.cancel()
        self.transactions[id_]["task"] = asyncio.create_task(
            self.task(self.transactions[id_])
        )

    async def task(self, trans):
        msg = trans["base"]
        users = list(trans["content"].keys())
        key = "-".join([str(u.id) for u in users])
        participant_ids = [int(user.id) for user in users]
        participant_actor_ids = await self._get_linked_trade_actor_ids(
            participant_ids
        )

        for participant_id, extra_actor_ids in (
            trans.get("participant_actor_ids", {}) or {}
        ).items():
            normalized_participant_id = int(participant_id)
            if normalized_participant_id not in participant_actor_ids:
                participant_actor_ids[normalized_participant_id] = {
                    normalized_participant_id
                }
            participant_actor_ids[normalized_participant_id].update(
                int(actor_id) for actor_id in extra_actor_ids
            )

        def resolve_participant_id(user_id: int) -> int | None:
            normalized_user_id = int(user_id)
            for participant_id, actor_ids in participant_actor_ids.items():
                if normalized_user_id in actor_ids:
                    return participant_id
            return None

        acc = set()
        reacts = ["\U0000274e", "\U00002705"]
        for r in reacts:
            await msg.add_reaction(r)

        def check(r, u):
            participant_id = resolve_participant_id(u.id)
            return (
                participant_id is not None
                and r.emoji in reacts
                and r.message.id == msg.id
                and participant_id not in acc
            )

        while len(acc) < 2:
            try:
                r, u = await self.bot.wait_for("reaction_add", check=check, timeout=60)
            except asyncio.TimeoutError:
                await msg.delete()
                del self.transactions[key]
                return await msg.channel.send(_("Trade timed out."))
            participant_id = resolve_participant_id(u.id)
            if participant_id is None:
                continue
            if reacts.index(r.emoji):
                acc.add(participant_id)
            else:
                await msg.delete()
                del self.transactions[key]
                return await msg.channel.send(
                    _("{user} stopped the trade.").format(user=u.mention)
                )
        del self.transactions[key]
        await self.transact(trans)

    async def transact(self, trans):
        chan = (base := trans["base"]).channel
        await base.delete()
        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                # Lock both users for now
                (user1, user1_gives), (user2, user2_gives) = trans["content"].items()
                user1_item_ids = [i["id"] for i in user1_gives["items"]]
                user2_item_ids = [i["id"] for i in user2_gives["items"]]
                user1_row = await conn.fetchrow(
                    'SELECT * FROM profile WHERE "user"=$1 FOR UPDATE;', user1.id
                )
                user2_row = await conn.fetchrow(
                    'SELECT * FROM profile WHERE "user"=$1 FOR UPDATE;', user2.id
                )
                # Lock their traded items
                user1_items = (
                    await conn.fetch(
                        "SELECT * FROM allitems ai JOIN inventory i ON"
                        ' (ai."id"=i."item") WHERE ai."id"=ANY($1) AND ai."owner"=$2'
                        " FOR UPDATE;",
                        user1_item_ids,
                        user1.id,
                    )
                    or []
                )
                user2_items = (
                    await conn.fetch(
                        "SELECT * FROM allitems ai JOIN inventory i ON"
                        ' (ai."id"=i."item") WHERE ai."id"=ANY($1) AND ai."owner"=$2'
                        " FOR UPDATE;",
                        user2_item_ids,
                        user2.id,
                    )
                    or []
                )
                relative_money_difference_user1 = user2_gives.get(
                    "money", 0
                ) - user1_gives.get("money", 0)
                relative_money_difference_user2 = user1_gives.get(
                    "money", 0
                ) - user2_gives.get("money", 0)
                # Just to normalize
                all_crate_rarities = {
                    "common": 0,
                    "uncommon": 0,
                    "rare": 0,
                    "magic": 0,
                    "legendary": 0,
                    "mystery": 0,
                    "fortune": 0,
                    "divine": 0,
                    "materials": 0,
                }
                normalized_crates_user1 = all_crate_rarities | user1_gives["crates"]
                normalized_crates_user2 = all_crate_rarities | user2_gives["crates"]
                relative_crate_difference_user1 = {
                    r: a - normalized_crates_user1[r]
                    for r, a in normalized_crates_user2.items()
                }
                relative_crate_difference_user2 = {
                    r: a - normalized_crates_user2[r]
                    for r, a in normalized_crates_user1.items()
                }
                profile_cols_to_change_user1 = {
                    f"crates_{col}": val
                    for col, val in relative_crate_difference_user1.items()
                    if val
                }
                if relative_money_difference_user1:
                    profile_cols_to_change_user1[
                        "money"
                    ] = relative_money_difference_user1
                profile_cols_to_change_user2 = {
                    f"crates_{col}": val
                    for col, val in relative_crate_difference_user2.items()
                    if val
                }
                if relative_money_difference_user2:
                    profile_cols_to_change_user2[
                        "money"
                    ] = relative_money_difference_user2
                # Now, verify nothing has been traded away
                # Items are most obvious
                if len(user1_items) < len(user1_gives["items"]) or len(
                    user2_items
                ) < len(user2_gives["items"]):
                    return await chan.send(
                        _("Trade cancelled. Things were traded away in the meantime.")
                    )
                if any(
                    [
                        (item["original_name"] or item["original_type"])
                        for item in user1_items
                    ]
                ) or any(
                    [
                        (item["original_name"] or item["original_type"])
                        for item in user2_items
                    ]
                ):
                    return await chan.send(
                        _("Some item was modified in the meanwhile.")
                    )
                # Profile columns need to be checked if they are negative and substracting would be negative
                for col, val in profile_cols_to_change_user1.items():
                    if (
                        val < 0 and user1_row[col] + val < 0
                    ):  # substracting is smaller 0
                        return await chan.send(
                            _(
                                "Trade cancelled. Things were traded away in the"
                                " meantime."
                            )
                        )
                for col, val in profile_cols_to_change_user2.items():
                    if val < 0 and user2_row[col] + val < 0:
                        return await chan.send(
                            _(
                                "Trade cancelled. Things were traded away in the"
                                " meantime."
                            )
                        )

                # Validate crafting resources
                user1_resources = await self.get_player_resources(user1.id)
                user2_resources = await self.get_player_resources(user2.id)
                
                # Check if users have enough resources to trade
                for resource, amount in user1_gives.get("resources", {}).items():
                    if user1_resources.get(resource, 0) < amount:
                        return await chan.send(
                            f"Trade cancelled. {user1.display_name} doesn't have enough {resource.replace('_', ' ').title()}."
                        )
                
                for resource, amount in user2_gives.get("resources", {}).items():
                    if user2_resources.get(resource, 0) < amount:
                        return await chan.send(
                            f"Trade cancelled. {user2.display_name} doesn't have enough {resource.replace('_', ' ').title()}."
                        )

                # Double-check validation: Lock and verify resources again to prevent exploitation
                # This prevents race conditions where users might craft/sell/trade simultaneously
                for resource, amount in user1_gives.get("resources", {}).items():
                    current_amount = await conn.fetchval(
                        'SELECT amount FROM crafting_resources WHERE user_id=$1 AND resource_type=$2 FOR UPDATE',
                        user1.id, resource
                    )
                    if not current_amount or current_amount < amount:
                        return await chan.send(
                            f"Trade cancelled. {user1.display_name} no longer has enough {resource.replace('_', ' ').title()} "
                            f"(has {current_amount or 0}, needs {amount})."
                        )
                
                for resource, amount in user2_gives.get("resources", {}).items():
                    current_amount = await conn.fetchval(
                        'SELECT amount FROM crafting_resources WHERE user_id=$1 AND resource_type=$2 FOR UPDATE',
                        user2.id, resource
                    )
                    if not current_amount or current_amount < amount:
                        return await chan.send(
                            f"Trade cancelled. {user2.display_name} no longer has enough {resource.replace('_', ' ').title()} "
                            f"(has {current_amount or 0}, needs {amount})."
                        )

                # Everything OK, do transaction
                if user1_items:
                    await conn.execute(
                        'UPDATE allitems SET "owner"=$1 WHERE "id"=ANY($2);',
                        user2.id,
                        user1_item_ids,
                    )
                    await conn.execute(
                        'UPDATE inventory SET "equipped"=$1 WHERE "item"=ANY($2);',
                        False,
                        user1_item_ids,
                    )
                if user2_items:
                    await conn.execute(
                        'UPDATE allitems SET "owner"=$1 WHERE "id"=ANY($2);',
                        user1.id,
                        user2_item_ids,
                    )
                    await conn.execute(
                        'UPDATE inventory SET "equipped"=$1 WHERE "item"=ANY($2);',
                        False,
                        user2_item_ids,
                    )

                row_string_user1 = ", ".join(
                    [
                        f'"{col}"="{col}"+${n + 1}'
                        if val > 0
                        else f'"{col}"="{col}"-${n + 1}'
                        for n, (col, val) in enumerate(
                            profile_cols_to_change_user1.items()
                        )
                    ]
                )
                row_string_user2 = ", ".join(
                    [
                        f'"{col}"="{col}"+${n + 1}'
                        if val > 0
                        else f'"{col}"="{col}"-${n + 1}'
                        for n, (col, val) in enumerate(
                            profile_cols_to_change_user2.items()
                        )
                    ]
                )
                query_args_user_1 = [
                    abs(i) for i in profile_cols_to_change_user1.values()
                ]
                query_args_user_1.append(user1.id)
                query_args_user_2 = [
                    abs(i) for i in profile_cols_to_change_user2.values()
                ]
                query_args_user_2.append(user2.id)

                n_1 = len(profile_cols_to_change_user1) + 1
                n_2 = len(profile_cols_to_change_user2) + 1

                if profile_cols_to_change_user1:
                    await conn.execute(
                        f'UPDATE profile SET {row_string_user1} WHERE "user"=${n_1};',
                        *query_args_user_1,
                    )
                if profile_cols_to_change_user2:
                    await conn.execute(
                        f'UPDATE profile SET {row_string_user2} WHERE "user"=${n_2};',
                        *query_args_user_2,
                    )

                # Handle crafting resources transfer
                await self.transfer_crafting_resources(conn, user1, user2, user1_gives.get("resources", {}), user2_gives.get("resources", {}))

                # Transfer premium consumables
                for ctype in ["pet_age_potion", "pet_speed_growth_potion", "splice_final_potion", "weapon_element_scroll"]:
                    qty1 = user1_gives.get("consumables", {}).get(ctype, 0)
                    qty2 = user2_gives.get("consumables", {}).get(ctype, 0)
                    if qty1 > 0:
                        # Remove from user1, add to user2
                        row = await conn.fetchrow('SELECT id, quantity FROM user_consumables WHERE user_id = $1 AND consumable_type = $2;', user1.id, ctype)
                        if row and row["quantity"] >= qty1:
                            await conn.execute('UPDATE user_consumables SET quantity = quantity - $1 WHERE id = $2;', qty1, row["id"])
                            # Add to user2
                            row2 = await conn.fetchrow('SELECT id FROM user_consumables WHERE user_id = $1 AND consumable_type = $2;', user2.id, ctype)
                            if row2:
                                await conn.execute('UPDATE user_consumables SET quantity = quantity + $1 WHERE id = $2;', qty1, row2["id"])
                            else:
                                await conn.execute('INSERT INTO user_consumables (user_id, consumable_type, quantity) VALUES ($1, $2, $3);', user2.id, ctype, qty1)
                    if qty2 > 0:
                        # Remove from user2, add to user1
                        row = await conn.fetchrow('SELECT id, quantity FROM user_consumables WHERE user_id = $1 AND consumable_type = $2;', user2.id, ctype)
                        if row and row["quantity"] >= qty2:
                            await conn.execute('UPDATE user_consumables SET quantity = quantity - $1 WHERE id = $2;', qty2, row["id"])
                            # Add to user1
                            row1 = await conn.fetchrow('SELECT id FROM user_consumables WHERE user_id = $1 AND consumable_type = $2;', user1.id, ctype)
                            if row1:
                                await conn.execute('UPDATE user_consumables SET quantity = quantity + $1 WHERE id = $2;', qty2, row1["id"])
                            else:
                                await conn.execute('INSERT INTO user_consumables (user_id, consumable_type, quantity) VALUES ($1, $2, $3);', user1.id, ctype, qty2)

            await chan.send(_("Trade successful."))

    @has_no_transaction()
    @commands.group(
        invoke_without_command=True, brief=_("Opens a trading session with a user.")
    )
    @locale_doc
    async def trade(self, ctx, user: MemberWithCharacter):
        _(
            """Opens a trading session for you and another player.
            Using `{prefix}trade <user>`, then the user accepting the checkbox will start the trading session.

            While the trading session is open, you and the other player can add or remove items, money, crates, and crafting resources as you choose.

            Here are some examples to familiarize you with the concept:
             - {prefix}trade add crates 10 common
             - {prefix}trade set money 1000
             - {prefix}trade remove item 13377331 (this only works if you added this item before)
             - {prefix}trade add items 1234 2345 3456
             - {prefix}trade add resources dragon_scales 5
             - {prefix}trade add resources fire gems 3
             - {prefix}trade set resources mystic_dust 10

            **Crafting Resources Trading:**
            - Resource names can use underscores (dragon_scales, fire_gems) or spaces (fire gems, dragon scale)
            - Level restrictions apply: higher-level players cannot trade resources that lower-level players cannot obtain
            - Use `{prefix}amulet resources` to see your available resources

            To accept the trade, both players need to react with the ✅ emoji.
            Accepting the trade will transfer all items in the trade session to the other player.

            You cannot trade with yourself, or have more than one trade session open at once.
            Giving away any items, crates, money, or resources during the trade will render it invalid and it will not complete."""
        )
        if user == ctx.author:
            return await ctx.send(_("You cannot trade with yourself."))
        if not await ctx.confirm(
            _("{user} has requested a trade, {user2}.").format(
                user=ctx.author.mention, user2=user.mention
            ),
            user=user,
        ):
            return
        if any([str(user.id) in key for key in self.transactions]) or any(
            [str(ctx.author.id) in key for key in self.transactions]
        ):
            return await ctx.send(_("Someone is already in a trade."))
        identifier = f"{ctx.author.id}-{user.id}"
        participant_actor_ids: dict[int, set[int]] = {
            int(ctx.author.id): {int(ctx.author.id)}
        }
        alt_invoker_id = getattr(ctx, "alt_invoker_id", None)
        if alt_invoker_id is not None:
            participant_actor_ids[int(ctx.author.id)].add(int(alt_invoker_id))

        self.transactions[identifier] = {
            "content": {
                ctx.author: {"crates": defaultdict(lambda: 0), "money": 0, "items": [], "resources": defaultdict(lambda: 0), "consumables": defaultdict(lambda: 0)},
                user: {"crates": defaultdict(lambda: 0), "money": 0, "items": [], "resources": defaultdict(lambda: 0), "consumables": defaultdict(lambda: 0)},
            },
            "base": None,
            "task": None,
            "participant_actor_ids": participant_actor_ids,
        }
        await self.update(ctx)

    @has_transaction()
    @trade.group(invoke_without_command=True, brief=_("Adds something to a trade."))
    @locale_doc
    async def add(self, ctx):
        _(
            """Adds something to trade session.
            You can specifiy what item you want to add to the trade by using one of the subcommands below.

            You need to have an open trading session to use this command."""
        )
        await ctx.send(
            _(
                "Please select something to add. Example: `{prefix}trade add money"
                " 1337`\nYou can also use `consumable` for premium potions."
            ).format(prefix=ctx.clean_prefix)
        )

    @has_transaction()
    @add.command(name="money", brief=_("Adds money to a trade."))
    @locale_doc
    async def add_money(self, ctx, amount: IntGreaterThan(0)):
        _(
            """`<amount>` - The amount of money to add, must be greater than 0

            Adds money to the trading session. You cannot add more money than you have.
            To remove money, consider `{prefix}trade remove money`.

            You need to have an open trading session to use this command."""
        )
        if await self.bot.has_money(ctx.author.id, ctx.transaction["money"] + amount):
            ctx.transaction["money"] += amount
            await ctx.message.add_reaction("<:blackcheck:441826948919066625>")
        else:
            await ctx.send(_("You are too poor."))

    @has_transaction()
    @add.command(name="crates", brief=_("Adds crates to a trade."))
    @locale_doc
    async def add_crates(self, ctx, amount: IntGreaterThan(0), rarity: CrateRarity):
        _(
            """`<amount>` - The amount of crates to add, must be greater than 0
            `<rarity>` - The crate rarity to add, can be common, uncommon, rare, magic or legendary

            Adds crate to the trading session. You cannot add more crates than you have.
            To remove crates, consider `{prefix}trade remove crates`.

            You need to have an open trading session to use this command."""
        )
        if await self.bot.has_crates(
            ctx.author.id, ctx.transaction["crates"][rarity] + amount, rarity
        ):
            ctx.transaction["crates"][rarity] += amount
            await ctx.message.add_reaction("<:blackcheck:441826948919066625>")
        else:
            await ctx.send(_("You do not have enough crates."))

    @has_transaction()
    @add.command(name="item", brief=_("Adds items to a trade."))
    @locale_doc
    async def add_item(self, ctx, itemid: int):
        _(
            """`<itemid>` - The ID of the item to add

            Add an item to the trading session. The item needs to be in your inventory.
            To remove an item, consider `{prefix}trade remove item`.

            You need to have an open trading session to use this command."""
        )
        # Check if the user already has 15 items in the transaction
        if len(ctx.transaction["items"]) >= 15:
            return await ctx.send(_("You can only add up to 15 items to the trade."))

        if itemid in [x["id"] for x in ctx.transaction["items"]]:
            return await ctx.send(_("You already added this item!"))

        if item := await self.bot.pool.fetchrow(
                'SELECT ai.* FROM allitems ai JOIN inventory i ON (ai."id"=i."item") WHERE'
                ' ai."id"=$1 AND ai."owner"=$2;',
                itemid,
                ctx.author.id,
        ):
            if item["original_name"] or item["original_type"]:
                return await ctx.send(_("You may not sell modified items."))

            ctx.transaction["items"].append(item)
            await ctx.message.add_reaction("<:blackcheck:441826948919066625>")
        else:
            await ctx.send(_("You do not own this item."))

    @has_transaction()
    @add.command(name="items", brief=_("Adds multiple items to a trade."))
    @locale_doc
    async def add_items(self, ctx, *itemids: int):
        _(
            """`<itemids...>` - The IDs of the item to add, separated by space

            Adds multiple items to the trading session. The items cannot already be in the trading session.
            Items that are not in your inventory will be automatically filtered out.
            To remove an item, consider `{prefix}trade remove item`.

            You need to have an open trading session to use this command."""
        )
        if any([(x in [x["id"] for x in ctx.transaction["items"]]) for x in itemids]):
            return await ctx.send(_("You already added one or more of these items!"))
        items = await self.bot.pool.fetch(
            'SELECT ai.* FROM allitems ai JOIN inventory i ON (ai."id"=i."item") WHERE'
            ' ai."id"=ANY($1) AND ai."owner"=$2;',
            itemids,
            ctx.author.id,
        )
        for item in items:
            if item["original_name"] or item["original_type"]:
                return await ctx.send(_("You may not sell modified items."))
            ctx.transaction["items"].append(item)
        await ctx.message.add_reaction("<:blackcheck:441826948919066625>")

    @has_transaction()
    @add.command(name="resources", brief=_("Adds crafting resources to a trade."))
    @locale_doc
    async def add_resources(self, ctx, *args):
        _(
            """`<resource_name>` - The name of the crafting resource to add (e.g., dragon_scales, mystic_dust, "fire gem")
            `<amount>` - The amount of resources to add, must be greater than 0

            Adds crafting resources to the trading session. You cannot add more resources than you have.
            Resource names can use underscores (e.g., dragon_scales, fire_gems) or spaces (e.g., "fire gem", "dragon scale").
            To remove resources, consider `{prefix}trade remove resources`.

            You need to have an open trading session to use this command."""
        )
        if len(args) < 2:
            return await ctx.send(f"❌ **Usage**: `{ctx.clean_prefix}trade add resources <resource_name> <amount>`\n\nExamples:\n- `{ctx.clean_prefix}trade add resources fire_gems 5`\n- `{ctx.clean_prefix}trade add resources \"fire gem\" 3`")
        
        # Parse the arguments - last argument is amount, everything else is resource name
        amount = args[-1]
        resource_name_parts = args[:-1]
        
        try:
            amount = int(amount)
            if amount <= 0:
                return await ctx.send("❌ **Error**: Amount must be greater than 0.")
        except ValueError:
            return await ctx.send("❌ **Error**: Amount must be a valid number.")
        
        # Join the resource name parts back together
        resource_name = " ".join(resource_name_parts)
        
        # Normalize the resource name
        normalized_resource = self.normalize_resource_name(resource_name)
        
        # Validate that this is a known resource
        amulet_cog = self.bot.get_cog("AmuletCrafting")
        if amulet_cog and normalized_resource not in amulet_cog.ALL_RESOURCES:
            # Try to suggest similar resources
            suggestions = []
            for resource in amulet_cog.ALL_RESOURCES.keys():
                if resource_name.lower() in resource.lower() or resource.lower() in resource_name.lower():
                    suggestions.append(resource.replace('_', ' ').title())
            
            if suggestions:
                suggestion_text = ", ".join(suggestions[:3])  # Limit to 3 suggestions
                return await ctx.send(f"❌ **Unknown Resource**: '{resource_name}' is not a valid crafting resource.\n\nDid you mean: {suggestion_text}?")
            else:
                return await ctx.send(f"❌ **Unknown Resource**: '{resource_name}' is not a valid crafting resource.\n\nUse `{ctx.clean_prefix}amulet resources` to see your available resources.")
        
        # Check if the other player can receive this resource based on level restrictions
        other_user = None
        for user in self.transactions[self.get_transaction(ctx.author, return_id=True)]["content"].keys():
            if user != ctx.author:
                other_user = user
                break
        
        if other_user:
            # Get other player's level
            other_level = await self.get_player_level(other_user.id)
            if other_level:
                # Check if resource is available for their level
                if amulet_cog:
                    available_resources = amulet_cog.get_available_resources_for_level(other_level)
                    if normalized_resource not in available_resources:
                        return await ctx.send(
                            f"❌ **Level Restriction**: {other_user.display_name} (Level {other_level}) cannot receive {normalized_resource.replace('_', ' ').title()} "
                            f"as it requires a higher level. They need to be level {amulet_cog.get_minimum_level_for_resource(normalized_resource)}+ to trade this resource."
                        )
        
        # Check if user has enough resources
        current_amount = ctx.transaction["resources"].get(normalized_resource, 0)
        user_resources = await self.get_player_resources(ctx.author.id)
        user_amount = user_resources.get(normalized_resource, 0)
        
        if user_amount >= current_amount + amount:
            ctx.transaction["resources"][normalized_resource] = current_amount + amount
            await ctx.message.add_reaction("<:blackcheck:441826948919066625>")
            await self.update(ctx)  # Update the trade display
        else:
            await ctx.send(f"You don't have enough {normalized_resource.replace('_', ' ').title()}. You have {user_amount}.")

    @has_transaction()
    @add.command(name="consumable", brief=_("Adds premium consumables to a trade."))
    @locale_doc
    async def add_consumable(self, ctx, ctype: str, amount: IntGreaterThan(0)):
        """
        `<ctype>` - The type of premium consumable (pet_age_potion, pet_speed_growth_potion, splice_final_potion, weapon_element_scroll)
        `<amount>` - The amount to add
        """
        valid_types = ["pet_age_potion", "pet_speed_growth_potion", "splice_final_potion", "weapon_element_scroll"]
        ctype = ctype.lower()
        if ctype not in valid_types:
            return await ctx.send(f"❌ Invalid consumable type. Valid types: {', '.join(valid_types)}")
        # Check user inventory
        async with self.bot.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT quantity FROM user_consumables WHERE user_id = $1 AND consumable_type = $2;', ctx.author.id, ctype)
            owned = row["quantity"] if row else 0
        in_trade = ctx.transaction["consumables"].get(ctype, 0)
        if owned < in_trade + amount:
            return await ctx.send(f"❌ You do not have enough {ctype.replace('_', ' ').title()}. You have {owned}.")
        ctx.transaction["consumables"][ctype] = in_trade + amount
        await ctx.message.add_reaction("<:blackcheck:441826948919066625>")
        await self.update(ctx)

    @has_transaction()
    @add.command(name="consumables", brief=_("Adds multiple premium consumables to a trade."))
    @locale_doc
    async def add_consumables(self, ctx, *args):
        """
        `<ctype> <amount>` pairs, e.g. `pet_age_potion 2 petspeed 1`
        """
        valid_types = ["pet_age_potion", "pet_speed_growth_potion", "splice_final_potion", "weapon_element_scroll"]
        if len(args) % 2 != 0:
            return await ctx.send("❌ Usage: trade add consumables <type> <amount> ...")
        async with self.bot.pool.acquire() as conn:
            for i in range(0, len(args), 2):
                ctype = args[i].lower()
                if ctype not in valid_types:
                    return await ctx.send(f"❌ Invalid consumable type: {ctype}")
                try:
                    amount = int(args[i+1])
                except Exception:
                    return await ctx.send(f"❌ Invalid amount for {ctype}.")
                if amount <= 0:
                    return await ctx.send(f"❌ Amount must be positive for {ctype}.")
                row = await conn.fetchrow('SELECT quantity FROM user_consumables WHERE user_id = $1 AND consumable_type = $2;', ctx.author.id, ctype)
                owned = row["quantity"] if row else 0
                in_trade = ctx.transaction["consumables"].get(ctype, 0)
                if owned < in_trade + amount:
                    return await ctx.send(f"❌ You do not have enough {ctype.replace('_', ' ').title()}. You have {owned}.")
                ctx.transaction["consumables"][ctype] = in_trade + amount
        await ctx.message.add_reaction("<:blackcheck:441826948919066625>")
        await self.update(ctx)

    @has_transaction()
    @trade.group(
        invoke_without_command=True,
        name="set",
        brief=_("Sets a value to a trade instead of adding onto it."),
    )
    @locale_doc
    async def set_(self, ctx):
        _(
            """Sets a sepcific value in the trade session.
            You can specifiy what item you want to set in the trade by using one of the subcommands below.

            You need to have an open trading session to use this command."""
        )
        await ctx.send(
            _(
                "Please select something to set. Example: `{prefix}trade set money"
                " 1337`\nYou can also use `consumable` for premium potions."
            ).format(prefix=ctx.clean_prefix)
        )

    @has_transaction()
    @set_.command(name="money", brief=_("Sets money in a trade."))
    @locale_doc
    async def set_money(self, ctx, amount: IntGreaterThan(-1)):
        _(
            """`<amount>` - The amount of money to set, must be greater than -1

            Sets an amount of money in the trading session. You cannot set more money than you have.
            To add or remove money, consider `{prefix}trade add/remove money`.

            You need to have an open trading session to use this command."""
        )
        if await self.bot.has_money(ctx.author.id, amount):
            ctx.transaction["money"] = amount
            await ctx.message.add_reaction("<:blackcheck:441826948919066625>")
        else:
            await ctx.send(_("You are too poor."))

    @has_transaction()
    @set_.command(name="crates", brief=_("Sets crates in a trade."))
    @locale_doc
    async def set_crates(self, ctx, amount: IntGreaterThan(-1), rarity: CrateRarity):
        _(
            """`<amount>` - The amount of crates to set, must be greater than -1
            `<rarity>` - The crate rarity to set, can be common, uncommon, rare, magic or legendary

            Sets an amount of crates in the trading session. You cannot set more crates than you have.
            To add or remove crates, consider `{prefix}trade add/remove crates`.

            You need to have an open trading session to use this command."""
        )
        if await self.bot.has_crates(ctx.author.id, amount, rarity):
            ctx.transaction["crates"][rarity] = amount
            await ctx.message.add_reaction("<:blackcheck:441826948919066625>")
        else:
            await ctx.send(_("You do not have enough crates."))

    @has_transaction()
    @set_.command(name="resources", brief=_("Sets crafting resources in a trade."))
    @locale_doc
    async def set_resources(self, ctx, *args):
        _(
            """`<resource_name>` - The name of the crafting resource to set (e.g., dragon_scales, mystic_dust, "fire gem")
            `<amount>` - The amount of resources to set, must be greater than -1

            Sets an amount of crafting resources in the trading session. You cannot set more resources than you have.
            Resource names can use underscores (e.g., dragon_scales, fire_gems) or spaces (e.g., "fire gem", "dragon scale").
            To add or remove resources, consider `{prefix}trade add/remove resources`.

            You need to have an open trading session to use this command."""
        )
        if len(args) < 2:
            return await ctx.send(f"❌ **Usage**: `{ctx.clean_prefix}trade set resources <resource_name> <amount>`\n\nExamples:\n- `{ctx.clean_prefix}trade set resources fire_gems 5`\n- `{ctx.clean_prefix}trade set resources \"fire gem\" 3`")
        
        # Parse the arguments - last argument is amount, everything else is resource name
        amount = args[-1]
        resource_name_parts = args[:-1]
        
        try:
            amount = int(amount)
            if amount < 0:
                return await ctx.send("❌ **Error**: Amount must be 0 or greater.")
        except ValueError:
            return await ctx.send("❌ **Error**: Amount must be a valid number.")
        
        # Join the resource name parts back together
        resource_name = " ".join(resource_name_parts)
        
        # Normalize the resource name
        normalized_resource = self.normalize_resource_name(resource_name)
        
        # Validate that this is a known resource
        amulet_cog = self.bot.get_cog("AmuletCrafting")
        if amulet_cog and normalized_resource not in amulet_cog.ALL_RESOURCES:
            # Try to suggest similar resources
            suggestions = []
            for resource in amulet_cog.ALL_RESOURCES.keys():
                if resource_name.lower() in resource.lower() or resource.lower() in resource_name.lower():
                    suggestions.append(resource.replace('_', ' ').title())
            
            if suggestions:
                suggestion_text = ", ".join(suggestions[:3])  # Limit to 3 suggestions
                return await ctx.send(f"❌ **Unknown Resource**: '{resource_name}' is not a valid crafting resource.\n\nDid you mean: {suggestion_text}?")
            else:
                return await ctx.send(f"❌ **Unknown Resource**: '{resource_name}' is not a valid crafting resource.\n\nUse `{ctx.clean_prefix}amulet resources` to see your available resources.")
        
        # Check if the other player can receive this resource based on level restrictions
        other_user = None
        for user in self.transactions[self.get_transaction(ctx.author, return_id=True)]["content"].keys():
            if user != ctx.author:
                other_user = user
                break
        
        if other_user and amount > 0:
            # Get other player's level
            other_level = await self.get_player_level(other_user.id)
            if other_level:
                # Check if resource is available for their level
                if amulet_cog:
                    available_resources = amulet_cog.get_available_resources_for_level(other_level)
                    if normalized_resource not in available_resources:
                        return await ctx.send(
                            f"❌ **Level Restriction**: {other_user.display_name} (Level {other_level}) cannot receive {normalized_resource.replace('_', ' ').title()} "
                            f"as it requires a higher level. They need to be level {amulet_cog.get_minimum_level_for_resource(normalized_resource)}+ to trade this resource."
                        )
        
        # Check if user has enough resources
        user_resources = await self.get_player_resources(ctx.author.id)
        user_amount = user_resources.get(normalized_resource, 0)
        
        if user_amount >= amount:
            ctx.transaction["resources"][normalized_resource] = amount
            await ctx.message.add_reaction("<:blackcheck:441826948919066625>")
            await self.update(ctx)  # Update the trade display
        else:
            await ctx.send(f"You don't have enough {normalized_resource.replace('_', ' ').title()}. You have {user_amount}.")

    @has_transaction()
    @set_.command(name="consumable", brief=_("Sets premium consumables in a trade."))
    @locale_doc
    async def set_consumable(self, ctx, ctype: str, amount: IntGreaterThan(0)):
        valid_types = ["pet_age_potion", "pet_speed_growth_potion", "splice_final_potion", "weapon_element_scroll"]
        ctype = ctype.lower()
        if ctype not in valid_types:
            return await ctx.send(f"❌ Invalid consumable type. Valid types: {', '.join(valid_types)}")
        async with self.bot.pool.acquire() as conn:
            row = await conn.fetchrow('SELECT quantity FROM user_consumables WHERE user_id = $1 AND consumable_type = $2;', ctx.author.id, ctype)
            owned = row["quantity"] if row else 0
        if owned < amount:
            return await ctx.send(f"❌ You do not have enough {ctype.replace('_', ' ').title()}. You have {owned}.")
        ctx.transaction["consumables"][ctype] = amount
        await ctx.message.add_reaction("<:blackcheck:441826948919066625>")
        await self.update(ctx)

    @has_transaction()
    @trade.group(
        invoke_without_command=True,
        aliases=["del", "rem", "delete"],
        brief=_("Removes something from a trade."),
    )
    @locale_doc
    async def remove(self, ctx):
        _(
            """Removes something from a trade session.
            You can remove something of your choice by using one of the subcommands below.

            You need to have an open trading session to use this command."""
        )
        await ctx.send(
            _(
                "Please select something to remove. Example: `{prefix}trade remove"
                " money 1337`\nYou can also use `consumable` for premium potions."
            ).format(prefix=ctx.clean_prefix)
        )

    @has_transaction()
    @remove.command(name="money", brief=_("Removes money from a trade."))
    @locale_doc
    async def remove_money(self, ctx, amount: IntGreaterThan(0)):
        _(
            """`<amount>` - The amount of money to remove, must be greater than 0

            Removes money from the trading session. You cannot remove more money than you added.
            To add money, consider `{prefix}trade add money`.

            You need to have an open trading session to use this command."""
        )
        if ctx.transaction["money"] - amount >= 0:
            ctx.transaction["money"] -= amount
            await ctx.message.add_reaction("<:blackcheck:441826948919066625>")
        else:
            await ctx.send(_("Resulting amount is negative."))

    @has_transaction()
    @remove.command(name="crates", brief=_("Removes crates from a trade."))
    @locale_doc
    async def remove_crates(self, ctx, amount: IntGreaterThan(0), rarity: CrateRarity):
        _(
            """`<amount>` - The amount of crates to remove, must be greater than 0
            `<rarity>` - The crate rarity to remove, can be common, uncommon, rare, magic or legendary

            Removes crates from the trading session. You cannot remove more crates than you added.
            To add crates, consider `{prefix}trade add crates`.

            You need to have an open trading session to use this command."""
        )
        if (res := ctx.transaction["crates"][rarity] - amount) >= 0:
            if res == 0:
                del ctx.transaction["crates"][rarity]
            else:
                ctx.transaction["crates"][rarity] -= amount
            await ctx.message.add_reaction("<:blackcheck:441826948919066625>")
        else:
            await ctx.send(_("The resulting amount would be negative."))

    @has_transaction()
    @remove.command(name="item", brief=_("Removes items from a trade."))
    @locale_doc
    async def remove_item(self, ctx, itemid: int):
        _(
            """`<itemid>` - The ID of the item to remove

            Remove an item from the trading session. The item needs to be in the trade to remove it.
            To add an item, consider `{prefix}trade add item`.

            You need to have an open trading session to use this command."""
        )
        item = discord.utils.find(lambda x: x["id"] == itemid, ctx.transaction["items"])
        if item:
            ctx.transaction["items"].remove(item)
            await ctx.message.add_reaction("<:blackcheck:441826948919066625>")
        else:
            await ctx.send(_("This item is not in the trade."))

    @has_transaction()
    @remove.command(name="items", brief=_("Removes multiple items to a trade."))
    @locale_doc
    async def remove_items(self, ctx, *itemids: int):
        _(
            """`<itemids...>` - The IDs of the item to remove, separated by space

            Remove multiple items from the trading session. The items must be in the trading session already.
            Items that are not in the trade will be automatically filtered out.
            To remove an item, consider `{prefix}trade remove item`.

            You need to have an open trading session to use this command."""
        )
        for itemid in itemids:
            item = discord.utils.find(
                lambda x: x["id"] == itemid, ctx.transaction["items"]
            )
            if item:
                ctx.transaction["items"].remove(item)
        await ctx.message.add_reaction("<:blackcheck:441826948919066625>")

    @has_transaction()
    @remove.command(name="resources", brief=_("Removes crafting resources from a trade."))
    @locale_doc
    async def remove_resources(self, ctx, *args):
        _(
            """`<resource_name>` - The name of the crafting resource to remove (e.g., dragon_scales, mystic_dust, "fire gem")
            `<amount>` - The amount of resources to remove, must be greater than 0

            Removes crafting resources from the trading session. You cannot remove more resources than you added.
            Resource names can use underscores (e.g., dragon_scales, fire_gems) or spaces (e.g., "fire gem", "dragon scale").
            To add resources, consider `{prefix}trade add resources`.

            You need to have an open trading session to use this command."""
        )
        if len(args) < 2:
            return await ctx.send(f"❌ **Usage**: `{ctx.clean_prefix}trade remove resources <resource_name> <amount>`\n\nExamples:\n- `{ctx.clean_prefix}trade remove resources fire_gems 5`\n- `{ctx.clean_prefix}trade remove resources \"fire gem\" 3`")
        
        # Parse the arguments - last argument is amount, everything else is resource name
        amount = args[-1]
        resource_name_parts = args[:-1]
        
        try:
            amount = int(amount)
            if amount <= 0:
                return await ctx.send("❌ **Error**: Amount must be greater than 0.")
        except ValueError:
            return await ctx.send("❌ **Error**: Amount must be a valid number.")
        
        # Join the resource name parts back together
        resource_name = " ".join(resource_name_parts)
        
        # Normalize the resource name
        normalized_resource = self.normalize_resource_name(resource_name)
        
        current_amount = ctx.transaction["resources"].get(normalized_resource, 0)
        if current_amount - amount >= 0:
            if current_amount - amount == 0:
                del ctx.transaction["resources"][normalized_resource]
            else:
                ctx.transaction["resources"][normalized_resource] = current_amount - amount
            await ctx.message.add_reaction("<:blackcheck:441826948919066625>")
            await self.update(ctx)  # Update the trade display
        else:
            await ctx.send(f"You only have {current_amount} {normalized_resource.replace('_', ' ').title()} in the trade.")

    @has_transaction()
    @remove.command(name="consumable", brief=_("Removes premium consumables from a trade."))
    @locale_doc
    async def remove_consumable(self, ctx, ctype: str, amount: IntGreaterThan(0)):
        valid_types = ["pet_age_potion", "pet_speed_growth_potion", "splice_final_potion", "weapon_element_scroll"]
        ctype = ctype.lower()
        if ctype not in valid_types:
            return await ctx.send(f"❌ Invalid consumable type. Valid types: {', '.join(valid_types)}")
        in_trade = ctx.transaction["consumables"].get(ctype, 0)
        if in_trade < amount:
            return await ctx.send(f"❌ You only have {in_trade} {ctype.replace('_', ' ').title()} in the trade.")
        if in_trade - amount == 0:
            del ctx.transaction["consumables"][ctype]
        else:
            ctx.transaction["consumables"][ctype] = in_trade - amount
        await ctx.message.add_reaction("<:blackcheck:441826948919066625>")
        await self.update(ctx)

    async def transfer_crafting_resources(self, conn, user1, user2, user1_resources, user2_resources):
        """Transfer crafting resources between users during a trade."""
        # Calculate the net transfer for each user
        all_resources = set(user1_resources.keys()) | set(user2_resources.keys())
        
        for resource in all_resources:
            user1_amount = user1_resources.get(resource, 0)
            user2_amount = user2_resources.get(resource, 0)
            
            # Net transfer: positive means user1 gives to user2, negative means user2 gives to user1
            net_transfer = user1_amount - user2_amount
            
            if net_transfer > 0:
                # User1 gives to user2
                await self.transfer_resource(conn, user1.id, user2.id, resource, net_transfer)
            elif net_transfer < 0:
                # User2 gives to user1
                await self.transfer_resource(conn, user2.id, user1.id, resource, abs(net_transfer))

    async def transfer_resource(self, conn, from_user_id, to_user_id, resource_name, amount):
        """Transfer a specific resource from one user to another."""
        # Remove from sender
        await conn.execute(
            'UPDATE crafting_resources SET amount = amount - $1 WHERE user_id=$2 AND resource_type=$3',
            amount, from_user_id, resource_name
        )
        
        # Add to receiver
        existing = await conn.fetchrow(
            'SELECT amount FROM crafting_resources WHERE user_id=$1 AND resource_type=$2',
            to_user_id, resource_name
        )
        
        if existing:
            await conn.execute(
                'UPDATE crafting_resources SET amount = amount + $1 WHERE user_id=$2 AND resource_type=$3',
                amount, to_user_id, resource_name
            )
        else:
            await conn.execute(
                'INSERT INTO crafting_resources (user_id, resource_type, amount) VALUES ($1, $2, $3)',
                to_user_id, resource_name, amount
            )

    async def get_player_resources(self, user_id: int):
        """Get all crafting resources for a player."""
        try:
            async with self.bot.pool.acquire() as conn:
                resources = await conn.fetch(
                    'SELECT resource_type, amount FROM crafting_resources WHERE user_id=$1 AND amount > 0',
                    user_id
                )
                return {r['resource_type']: r['amount'] for r in resources}
        except Exception:
            return {}

    async def get_player_level(self, user_id: int):
        """Get the player's level from their XP."""
        try:
            async with self.bot.pool.acquire() as conn:
                player = await conn.fetchrow('SELECT xp FROM profile WHERE "user"=$1;', user_id)
                if player:
                    from utils import misc as rpgtools
                    return rpgtools.xptolevel(player['xp'])
                return 0
        except Exception:
            return 0

    def normalize_resource_name(self, resource_name: str):
        """
        Normalize resource names to handle various input formats.
        Converts "fire gem" -> "fire_gems", "dragon scale" -> "dragon_scales", etc.
        """
        # Remove quotes and extra whitespace
        resource_name = resource_name.strip().strip('"\'')
        
        # Common mappings for user-friendly names to database names
        resource_mappings = {
            # Attack resources
            "demon claw": "demon_claws",
            "demon claws": "demon_claws",
            "fire gem": "fire_gems",
            "fire gems": "fire_gems",
            "warrior essence": "warrior_essence",
            "blood crystal": "blood_crystals",
            "blood crystals": "blood_crystals",
            "storm shard": "storm_shards",
            "storm shards": "storm_shards",
            "berserker tear": "berserker_tears",
            "berserker tears": "berserker_tears",
            "phoenix feather": "phoenix_feathers",
            "phoenix feathers": "phoenix_feathers",
            
            # Defense resources
            "steel ingot": "steel_ingots",
            "steel ingots": "steel_ingots",
            "guardian stone": "guardian_stones",
            "guardian stones": "guardian_stones",
            "protective rune": "protective_runes",
            "protective runes": "protective_runes",
            "mountain heart": "mountain_hearts",
            "mountain hearts": "mountain_hearts",
            "titan shell": "titan_shells",
            "titan shells": "titan_shells",
            "ward crystal": "ward_crystals",
            "ward crystals": "ward_crystals",
            "sentinel core": "sentinel_cores",
            "sentinel cores": "sentinel_cores",
            
            # Health resources
            "life crystal": "life_crystals",
            "life crystals": "life_crystals",
            "healing herb": "healing_herbs",
            "healing herbs": "healing_herbs",
            "vitality essence": "vitality_essence",
            "phoenix blood": "phoenix_blood",
            "world tree sap": "world_tree_sap",
            "unicorn tear": "unicorn_tears",
            "unicorn tears": "unicorn_tears",
            "rejuvenation orb": "rejuvenation_orbs",
            "rejuvenation orbs": "rejuvenation_orbs",
            
            # Balance resources
            "harmony stone": "harmony_stones",
            "harmony stones": "harmony_stones",
            "balance orb": "balance_orbs",
            "balance orbs": "balance_orbs",
            "equilibrium dust": "equilibrium_dust",
            "yin yang crystal": "yin_yang_crystals",
            "yin yang crystals": "yin_yang_crystals",
            "neutral essence": "neutral_essence",
            "cosmic fragment": "cosmic_fragments",
            "cosmic fragments": "cosmic_fragments",
            "void pearl": "void_pearls",
            "void pearls": "void_pearls",
            
            # Shared resources
            "dragon scale": "dragon_scales",
            "dragon scales": "dragon_scales",
            "mystic dust": "mystic_dust",
            "refined ore": "refined_ore",
        }
        
        # Check if it's already in the correct format
        if resource_name in resource_mappings:
            return resource_mappings[resource_name]
        
        # If it's already in underscore format, return as is
        if '_' in resource_name:
            return resource_name
        
        # Try to convert space-separated to underscore format
        normalized = resource_name.replace(' ', '_')
        
        # Check if the normalized version exists in our mappings
        for key, value in resource_mappings.items():
            if key.replace(' ', '_') == normalized:
                return value
        
        # If all else fails, return the original (might be a valid underscore format)
        return resource_name

    async def cog_after_invoke(self, ctx):
        if hasattr(ctx, "transaction"):
            await self.update(ctx)


async def setup(bot):
    await bot.add_cog(Transaction(bot))

