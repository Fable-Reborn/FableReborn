"""
The IdleRPG Discord Bot
Copyright (C) 2018-2021 Diniboy and Gelbpunkt
Copyright (C) 2024 Lunar (discord itslunar.)

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
import datetime
import time
import datetime as dt
import random
import uuid
from contextlib import suppress

import discord

from discord.ext import commands, tasks
from discord.http import handle_message_parameters

from classes.converters import (
    DateNewerThan,
    IntFromTo,
    IntGreaterThan,
    MemberWithCharacter,
)
from classes.errors import NoChoice
from classes.items import ALL_ITEM_TYPES, ItemType
from cogs.shard_communication import user_on_cooldown as user_cooldown
from utils.checks import has_char, has_money, is_gm
from utils.i18n import _, locale_doc


class Trading(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.markdown_escaper = commands.clean_content(escape_markdown=True)

        # Add a list to track sold-out items
        self.sold_out_items = []

        # Global variable to store the last refresh timestamp
        self.last_refresh_time = 0

        self.decrease_hunger_task.start()
        self.decrease_happy_task.start()

        self.player_item_cache = {}



    def get_current_time(self):
        return datetime.datetime.utcnow()

    def is_item_expired(self, timestamp, expiry_duration_hours):
        return (self.get_current_time() - timestamp).total_seconds() > expiry_duration_hours * 3600

    async def generate_items_and_crates(self, ctx):
        # Define stat ranges and price ranges with weights
        stat_ranges = [
            (70, 80, 0.009009, (7000000, 15000000)),
            (60, 70, 0.018018, (5000000, 10000000)),
            (50, 60, 0.099099, (3000000, 5000000)),
            (40, 50, 0.181818, (200000, 1000000)),
            (20, 40, 0.272727, (50000, 200000)),
            (1, 20, 0.418418, (1000, 20000))  # Adjusted normalized weights
        ]

        def choose_stat_range(stat_ranges):
            rand_val = random.random()
            cumulative_weight = 0
            for min_stat, max_stat, weight, price_range in stat_ranges:
                cumulative_weight += weight
                if rand_val < cumulative_weight:
                    return min_stat, max_stat, price_range
            return 1, 20, (1000, 20000)  # Default case (should not be reached)

        items = []
        # Generate 5 random weapons
        for _ in range(5):
            min_stat, max_stat, price_range = choose_stat_range(stat_ranges)
            stat = random.randint(min_stat, max_stat)
            price = random.randint(price_range[0], price_range[1])

            item = await self.bot.create_random_item(
                minstat=min_stat,
                maxstat=max_stat,
                minvalue=1,
                maxvalue=500,
                owner=None,  # Owner is not required here
                insert=False,
            )
            items.append((item, price))

        # Define crate rarity and price ranges
        crate_weights = [
            ("divine", 0.000169, (900000, 2000000)),
            ("legendary", 0.000338, (900000, 1500000)),
            ("magic", 0.001692, (80000, 100000)),
            ("rare", 0.101692, (4000, 8000)),
            ("uncommon", 0.237692, (1000, 4000)),
            ("common", 0.658417, (700, 2000))
        ]

        def choose_crate_rarity(crate_weights):
            total_weight = sum(weight for _, weight, _ in crate_weights)
            normalized_weights = [
                (rarity, weight / total_weight, price_range)
                for rarity, weight, price_range in crate_weights
            ]

            rand_val = random.random()
            cumulative_weight = 0
            for rarity, weight, price_range in normalized_weights:
                cumulative_weight += weight
                if rand_val < cumulative_weight:
                    return rarity, price_range
            return "common", (700, 2000)  # Default case (should not be reached)

        crates = []
        # Generate 3 crates
        for _ in range(3):
            rarity, price_range = choose_crate_rarity(crate_weights)
            price = random.randint(price_range[0], price_range[1])

            crate = await self.bot.create_random_item(
                minstat=1,
                maxstat=1,
                minvalue=1,
                maxvalue=1,
                owner=None,
                insert=False,
            )
            crates.append((crate, price, rarity))

        # Add Weapon Token with a 7% chance
        if random.random() < 0.07:
            token_price = random.randint(250000, 750000)
            token_item = {
                'name': 'Weapontoken',
                'type_': 'Token',
                'armor': 'N/A',
                'damage': 'N/A',
                'value': 'N/A'
            }
            items.append((token_item, token_price))

        # Add Resetpotion with a 1% chance
        # It will only be generated if the shop is "fresh" (cache is empty),
        # so it effectively limits it to one per 12-hour refresh for that user.
        if random.random() < 0.01:
            potion_price = random.randint(1400000, 4300000)
            potion_item = {
                'name': 'Resetpotion',
                'type_': 'Potion',
                'armor': 'N/A',
                'damage': 'N/A',
                'value': 'N/A'
            }
            items.append((potion_item, potion_price))

        return items, crates

    @tasks.loop(minutes=999999)  # Adjust the interval as needed (e.g., minutes=10 means it runs every 10 minutes)
    async def decrease_hunger_task(self):
        try:
            async with self.bot.pool.acquire() as conn:
                # Fetch all pets from the database
                all_pets = await conn.fetch('SELECT * FROM user_pets;')

                for pet in all_pets:
                    hunger = random.randint(1, 5)
                    # Decrease hunger by a certain amount (adjust as needed)
                    new_hunger = max(0, pet['hunger'] - int(hunger))  # Decrease hunger by 5, but not below 0

                    # Update the pet's hunger in the database
                    await conn.execute(
                        'UPDATE user_pets SET hunger=$1 WHERE user_id=$2 AND pet_name=$3;',
                        new_hunger,
                        pet['user_id'],
                        pet['pet_name'],
                    )

        except Exception as e:
            print(f"An error occurred in decrease_hunger_task: {e}")

    @tasks.loop(minutes=999999)
    async def decrease_happy_task(self):
        try:
            async with self.bot.pool.acquire() as conn:
                # Fetch all pets from the database
                all_pets = await conn.fetch('SELECT * FROM user_pets;')

                for pet in all_pets:
                    # Determine the decrease in happiness based on hunger ranges
                    if pet['hunger'] > 80:
                        happiness_decrease = random.randint(1, 3)
                    elif pet['hunger'] > 60:
                        happiness_decrease = random.randint(4, 6)
                    elif pet['hunger'] > 40:
                        happiness_decrease = random.randint(7, 9)
                    elif pet['hunger'] > 20:
                        happiness_decrease = random.randint(10, 12)
                    else:
                        happiness_decrease = random.randint(13, 15)

                    # Calculate the new happiness value
                    new_happiness = max(0, pet['happiness'] - happiness_decrease)

                    # Update the pet's happiness in the database
                    await conn.execute(
                        'UPDATE user_pets SET happiness=$1 WHERE user_id=$2 AND pet_name=$3;',
                        new_happiness,
                        pet['user_id'],
                        pet['pet_name'],
                    )

        except Exception as e:
            print(f"An error occurred in decrease_happy_task: {e}")


        except Exception as e:
            print(f"An error occurred in decrease_hunger_task: {e}")

    @has_char()
    @commands.command(brief=_("Put an item in the market"))
    @locale_doc
    async def sell(self, ctx, itemid: int, price: IntFromTo(1, 100000000)):
        _(
            # xgettext: no-python-format
            """`<itemid>` - The ID of the item to sell
            `<price>` - The price to sell the item for, can be 0 or above

            Puts your item into the market. Tax for selling items is 5% of the price.

            You may not sell modified items, items with a price lower than their value, or items below 4 stat.
            If you are in an alliance with owns a city with a trade building, you do not have to pay the tax.

            Please note that you won't get the money right away, another player has to buy the item first.
            With that being said, please choose a reasonable price.  Acceptable price range is 1 to 100 Million.

            If your item has not been bought for 14 days, it will be removed from the market and put back into your inventory."""
        )
        async with self.bot.pool.acquire() as conn:
            item = await conn.fetchrow(
                "SELECT * FROM inventory i JOIN allitems ai ON (i.item=ai.id) WHERE"
                " ai.id=$1 AND ai.owner=$2;",
                itemid,
                ctx.author.id,
            )
            if not item:
                return await ctx.send(
                    _("You don't own an item with the ID: {itemid}").format(
                        itemid=itemid
                    )
                )
            if item["original_name"] or item["original_type"]:
                return await ctx.send(_("You may not sell donator-modified items."))
            if item["value"] > price:
                return await ctx.send(
                    _(
                        "Selling an item below its value is a bad idea. You can always"
                        " do `{prefix}merchant {itemid}` to get more money."
                    ).format(prefix=ctx.clean_prefix, itemid=itemid)
                )
            elif item["damage"] < 4 and item["armor"] < 4:
                return await ctx.send(
                    _(
                        "Your item is either equal to a Starter Item or worse. Noone"
                        " would buy it."
                    )
                )
            if (
                    builds := await self.bot.get_city_buildings(ctx.character_data["guild"])
            ) and builds["trade_building"] != 0:
                tax = 0
            else:
                tax = round(price * 0.05)
            if ctx.character_data["money"] < tax:
                return await ctx.send(
                    _("You cannot afford the tax of 5% (${amount}).").format(amount=tax)
                )
            if tax:
                await conn.execute(
                    'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                    tax,
                    ctx.author.id,
                )
                await self.bot.log_transaction(
                    ctx,
                    from_=ctx.author.id,
                    to=2,
                    subject="shop tax",
                    data={"Gold": tax},
                    conn=conn,
                )
            await conn.execute(
                "DELETE FROM inventory i USING allitems ai WHERE i.item=ai.id AND"
                " ai.id=$1 AND ai.owner=$2;",
                itemid,
                ctx.author.id,
            )
            await conn.execute(
                "INSERT INTO market (item, price) VALUES ($1, $2);",
                itemid,
                price,
            )
        await ctx.send(
            _(
                "Successfully added your item to the shop! Use `{prefix}shop` to view"
                " it in the market! {additional}"
            ).format(
                prefix=ctx.clean_prefix,
                additional=_("The tax of 5% has been deducted from your account.")
                if not builds or builds["trade_building"] == 0
                else "",
            )
        )

    @has_char()
    @commands.command(brief=_("Buy an item from the shop"))
    @locale_doc
    async def buy(self, ctx, itemid: int):
        _(
            """`<itemid>` - The ID of the item to buy

            Buy an item from the global market. Tax for buying is 5%.

            Buying your own items is impossible. You can find the item's ID in `{prefix}shop`."""
        )
        async with self.bot.pool.acquire() as conn:
            item = await conn.fetchrow(
                'SELECT *, m."id" AS "offer" FROM market m JOIN allitems ai ON'
                ' (m."item"=ai."id") WHERE ai."id"=$1;',
                itemid,
            )
            if not item:
                await ctx.send(
                    _("There is no item in the shop with the ID: {itemid}").format(
                        itemid=itemid
                    )
                )
                return False
            if item["owner"] == ctx.author.id:
                await ctx.send(_("You may not buy your own items."))
                return False
            if await self.bot.get_city_buildings(ctx.character_data["guild"]):
                tax = 0
            else:
                tax = round(item["price"] * 0.05)
            if ctx.character_data["money"] < item["price"] + tax:
                await ctx.send(_("You're too poor to buy this item."))
                return False
            await conn.execute(
                "DELETE FROM market m USING allitems ai WHERE m.item=ai.id AND ai.id=$1"
                " RETURNING *;",
                itemid,
            )
            await conn.execute(
                "UPDATE allitems SET owner=$1 WHERE id=$2;",
                ctx.author.id,
                item["id"],
            )
            await conn.execute(
                'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                item["price"],
                item["owner"],
            )
            await conn.execute(
                'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                item["price"] + tax,
                ctx.author.id,
            )
            await conn.execute(
                "INSERT INTO inventory (item, equipped) VALUES ($1, $2);",
                item["id"],
                False,
            )
            if tax:
                await self.bot.log_transaction(
                    ctx,
                    from_=ctx.author.id,
                    to=2,
                    subject="shop buy - bot give",
                    data={"Gold": item["price"] + tax},
                    conn=conn,
                )
            await self.bot.log_transaction(
                ctx,
                from_=ctx.author.id,
                to=item["owner"],
                subject="shop buy",
                data={"Gold": item["price"]},
                conn=conn,
            )
            await self.bot.log_transaction(
                ctx,
                from_=item["owner"],
                to=ctx.author,
                subject="shop",
                data=item,
                conn=conn,
            )
        await ctx.send(
            _(
                "Successfully bought item `{id}`. Use `{prefix}inventory` to view your"
                " updated inventory."
            ).format(id=item["id"], prefix=ctx.clean_prefix)
        )
        with suppress(discord.Forbidden, discord.HTTPException):
            dm_channel = await self.bot.http.start_private_message(item["owner"])
            with handle_message_parameters(
                    content="A traveler has bought your **{name}** for **${price}** from the market.".format(
                        name=item["name"], price=item["price"]
                    )
            ) as params:
                await self.bot.http.send_message(
                    dm_channel.get("id"),
                    params=params,
                )
        return True

    @has_char()
    @is_gm()
    @commands.command(brief=_("Restock all items from 1144898209144127589 in the market"))
    @locale_doc
    async def restock(self, ctx):
        _(
            """
            This command restocks all the items owned by 1144898209144127589 to the shop based on their stats.
            The pricing will be done based on the item's stats, and rounded to the nearest 1000.
            Note: Bows, maces, and scythes will have their stats halved for pricing.
            """
        )
        async with self.bot.pool.acquire() as conn:
            items = await conn.fetch(
                "SELECT * FROM inventory i JOIN allitems ai ON (i.item=ai.id) WHERE ai.owner=$1;",
                1144898209144127589,
            )

            for item in items:
                price = None
                max_stat = max(item["damage"], item["armor"])

                # Adjust max_stat for bow, mace, and scythe
                if item["type"] in ['Bow', 'Mace', 'Scythe']:
                    max_stat = max_stat // 2

                # Now use the adjusted max_stat for pricing
                if 3 <= max_stat <= 25:
                    price = round(random.randint(1000, 10000), -3)
                elif 26 <= max_stat <= 35:
                    price = round(random.randint(7000, 20000), -3)
                elif 36 <= max_stat <= 39:
                    price = round(random.randint(10000, 20000), -3)
                elif 40 <= max_stat <= 41:
                    price = round(random.randint(70000, 90000), -3)
                elif 41 <= max_stat <= 45:
                    price = round(random.randint(170000, 400000), -3)
                elif 46 <= max_stat <= 48:
                    price = round(random.randint(400000, 900000), -3)
                elif max_stat == 49 or max_stat == 98:
                    price = round(random.randint(1700000, 3000000), -3)
                elif max_stat == 50 or max_stat == 100:
                    price = round(random.randint(2700000, 6000000), -3)

                if price:
                    # Insert item into market
                    await conn.execute(
                        "INSERT INTO market (item, price) VALUES ($1, $2);",
                        item["id"],
                        price,
                    )
                    # Delete the item from inventory
                    await conn.execute(
                        "DELETE FROM inventory i USING allitems ai WHERE i.item=ai.id AND ai.id=$1 AND ai.owner=$2;",
                        item["id"],
                        1144898209144127589,
                    )

        await ctx.send(
            _(
                "Successfully restocked items from 1144898209144127589 to the shop! Use `{prefix}shop` to view them in the market!"
            ).format(prefix=ctx.clean_prefix)
        )

    @has_char()
    @commands.command(brief=_("Remove your item from the shop."))
    @locale_doc
    async def remove(self, ctx, itemid: int):
        _(
            """`<itemid>` - The item to remove from the shop

            Takes an item off the shop. You may only remove your own items from the shop.

            You can check your items on the shop with `{prefix}pending`. Paid tax money will not be returned."""
        )
        async with self.bot.pool.acquire() as conn:
            item = await conn.fetchrow(
                "SELECT * FROM market m JOIN allitems ai ON (m.item=ai.id) WHERE"
                " ai.id=$1 AND ai.owner=$2;",
                itemid,
                ctx.author.id,
            )
            if not item:
                return await ctx.send(
                    _(
                        "You don't have an item of yours in the shop with the ID"
                        " `{itemid}`."
                    ).format(itemid=itemid)
                )
            await conn.execute(
                "DELETE FROM market m USING allitems ai WHERE m.item=ai.id AND ai.id=$1"
                " AND ai.owner=$2;",
                itemid,
                ctx.author.id,
            )
            await conn.execute(
                "INSERT INTO inventory (item, equipped) VALUES ($1, $2);",
                itemid,
                False,
            )
        await ctx.send(
            _(
                "Successfully removed item `{itemid}` from the shop and put it in your"
                " inventory."
            ).format(itemid=itemid)
        )

    @commands.command(
        aliases=["mh", "markethistory"],
        brief=_("View sale history for the item market"),
    )
    @locale_doc
    async def shophistory(
            self,
            ctx,
            itemtype: str.title = "All",
            minstat: float = 0.00,
            after_date: DateNewerThan(
                dt.date(year=2018, month=3, day=17)
            ) = dt.date(year=2018, month=3, day=17),
    ):
        _(
            """`[itemtype]` - The type of item to filter; defaults to all item types
             `[minstat]` - The minimum damage/defense an item has to have to show up; defaults to 0
             `[after_date]` - Show sales only after this date, defaults to bot creation date, which means all

            Lists the past successful sales on the market by criteria and shows average, minimum and highest prices by category."""
        )
        if itemtype != "All" and ItemType.from_string(itemtype) is None:
            return await ctx.send(
                _("Use either {types} or `All` as a type to filter for.").format(
                    types=", ".join(f"`{t.value}`" for t in ALL_ITEM_TYPES)
                )
            )
        if itemtype == "All":
            sales = await self.bot.pool.fetch(
                "SELECT * FROM market_history WHERE"
                ' ("damage">=$1 OR "armor">=$1) AND "timestamp">=$2;',
                minstat,
                after_date,
            )
        elif itemtype == "Shield":
            sales = await self.bot.pool.fetch(
                "SELECT * FROM market_history WHERE"
                ' "armor">=$1 AND "timestamp">=$2 AND "type"=$3;',
                minstat,
                after_date,
                "Shield",
            )
        else:
            sales = await self.bot.pool.fetch(
                "SELECT * FROM market_history WHERE"
                ' "damage">=$1 AND "timestamp">=$2 AND "type"=$3;',
                minstat,
                after_date,
                itemtype,
            )
        if not sales:
            return await ctx.send(_("No results."))

        prices = [i["price"] for i in sales]
        max_price = max(prices)
        min_price = min(prices)
        avg_price = round(sum(prices) / len(prices), 2)

        items = [
            discord.Embed(
                title=_("FableRPG Shop History"),
                colour=discord.Colour.blurple(),
            )
            .add_field(name=_("Name"), value=item["name"])
            .add_field(name=_("Type"), value=item["type"])
            .add_field(name=_("Damage"), value=item["damage"])
            .add_field(name=_("Armor"), value=item["armor"])
            .add_field(name=_("Value"), value=f"${item['value']}")
            .add_field(
                name=_("Price"),
                value=f"${item['price']}",
            )
            .set_footer(
                text=_("Item {num} of {total}").format(num=idx + 1, total=len(sales))
            )
            for idx, item in enumerate(sales)
        ]
        items.insert(
            0,
            discord.Embed(
                title=_("Search results"),
                color=discord.Colour.blurple(),
                description=_(
                    "The search found {amount} sales starting at ${min_price}, ending"
                    " at ${max_price}. The average sale price was"
                    " ${avg_price}.\n\nNavigate to see the sales."
                ).format(
                    amount=len(prices),
                    min_price=min_price,
                    max_price=max_price,
                    avg_price=avg_price,
                ),
            ),
        )

        await self.bot.paginator.Paginator(extras=items).paginate(ctx)

    @has_char()
    @commands.command(aliases=["market", "m"], brief=_("View the global item market"))
    @locale_doc
    async def shop(
            self,
            ctx,
            itemtype: str = "All",
            minstat: float = 0.00,
            highestprice: IntGreaterThan(-1) = 1_000_000_000,
    ):
        _(
            """`[itemtype]` - The type of item to filter; defaults to all item types
            `[minstat]` - The minimum damage/defense an item has to have to show up; defaults to 0
            `[highestprice]` - The highest price an item can have to show up; defaults to $1,000,000

            Lists the buyable items on the market. You can cleverly filter out items you don't want to see with these parameters.

            To quickly buy an item, you can use the 💰 emoji."""
        )

        item_types = []

        if itemtype == "1h":
            item_types.extend(["Sword", "Axe", "Wand", "Dagger", "Knife", "Spear", "Hammer"])
        elif itemtype == "2h":
            item_types.extend(["Bow", "Scythe", "Mace"])
        elif itemtype == "Shield":
            item_types.append("Shield")
        elif itemtype.lower() in [t.value.lower() for t in ALL_ITEM_TYPES]:
            # Allow searching for individual items (case-insensitive comparison)
            item_types.append(itemtype.capitalize())  # Capitalize the itemtype to match the database values


        elif itemtype != "All":
            return await ctx.send(
                _("Use either {types}, `1h`, `2h`, or `Shield` as a type to filter for.").format(
                    types=", ".join(f"`{t.value}`" for t in ALL_ITEM_TYPES)
                )
            )

        if item_types:
            items = await self.bot.pool.fetch(
                "SELECT * FROM allitems ai JOIN market m ON (ai.id=m.item) WHERE"
                ' ai."type"=ANY($1) AND (ai."damage">=$2 OR ai."armor">=$3) AND m."price"<=$4;',
                item_types,
                minstat,
                minstat,
                highestprice,
            )
        else:
            items = await self.bot.pool.fetch(
                "SELECT * FROM allitems ai JOIN market m ON (ai.id=m.item) WHERE"
                ' m."price"<=$1 AND (ai."damage">=$2 OR ai."armor">=$3);',
                highestprice,
                minstat,
                minstat,
            )

        if not items:
            return await ctx.send(_("No results."))

        entries = [
            (
                discord.Embed(
                    title=_("Fable Shop"),
                    description=_("Use `{prefix}buy {item}` to buy this.").format(
                        prefix=ctx.clean_prefix, item=item["item"]
                    ),
                    colour=discord.Colour.blurple(),
                )
                .add_field(name=_("Name"), value=item["name"])
                .add_field(name=_("Type"), value=item["type"])
                .add_field(name=_("Damage"), value=item["damage"])
                .add_field(name=_("Armor"), value=item["armor"])
                .add_field(name=_("Value"), value=f"${item['value']}")
                .add_field(
                    name=_("Price"),
                    value=f"${item['price']} (+${round(item['price'] * 0.05)} (5%) tax)",
                )
                .set_footer(
                    text=_("Item {num} of {total}").format(
                        num=idx + 1, total=len(items)
                    )
                ),
                item["item"],
            )
            for idx, item in enumerate(items)
        ]

        await self.bot.paginator.ShopPaginator(entries=entries).paginate(ctx)

    @has_char()
    @user_cooldown(180)
    @commands.command(brief=_("Offer an item to a user"))
    @locale_doc
    async def offer(
            self,
            ctx,
            itemid: int,
            price: IntFromTo(0, 100_000_000),
            user: MemberWithCharacter,
    ):
        _(
            """`<itemid>` - The ID of the item to offer
            `<price>` - The price the other has to pay, can be a number from 0 to 100,000,000
            `<user>` - The user to offer the item to

            Offer an item to a specific user. You may not offer modified items.
            Once the other user accepts, the item belongs to them."""
        )
        if user == ctx.author:
            return await ctx.send(_("You may not offer items to yourself."))
        item = await self.bot.pool.fetchrow(
            "SELECT * FROM inventory i JOIN allitems ai ON (i.item=ai.id) WHERE"
            " ai.id=$1 AND ai.owner=$2;",
            itemid,
            ctx.author.id,
        )
        if not item:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(
                _("You don't have an item with the ID `{itemid}`.").format(
                    itemid=itemid
                )
            )

        if item["original_name"] or item["original_type"]:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(_("You may not sell donator-modified items."))

        if item["equipped"]:
            if not await ctx.confirm(
                    _("Are you sure you want to sell your equipped {item}?").format(
                        item=item["name"]
                    )
            ):
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_("Item selling cancelled."))


        if not await ctx.confirm(
                _(
                    "{user}, {author} offered a **{stat}** **{itemtype}**! React to buy it!"
                    " The price is **${price}**. You have **2 Minutes** to accept the trade"
                    " or the offer will be canceled."
                ).format(
                    user=user.mention,
                    author=ctx.author.mention,
                    stat=item["damage"] + item["armor"],
                    itemtype=item["type"],
                    price=price,
                ),
                user=user,
                timeout=120,
        ):
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(_("They didn't want it."))

        async with self.bot.pool.acquire() as conn:
            if not await has_money(self.bot, user.id, price, conn=conn):
                return await ctx.send(
                    _("{user}, you're too poor to buy this item!").format(
                        user=user.mention
                    )
                )
            item = await conn.fetchrow(
                "SELECT * FROM inventory i JOIN allitems ai ON (i.item=ai.id) WHERE"
                " ai.id=$1 AND ai.owner=$2;",
                itemid,
                ctx.author.id,
            )
            if not item:
                return await ctx.send(
                    _(
                        "The owner sold the item with the ID `{itemid}` in the"
                        " meantime."
                    ).format(itemid=itemid)
                )
            if item["original_name"] or item["original_type"]:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_("You may not sell donator-modified items."))
            await conn.execute(
                "UPDATE allitems SET owner=$1 WHERE id=$2;", user.id, itemid
            )
            await conn.execute(
                'UPDATE profile SET money=money+$1 WHERE "user"=$2;',
                price,
                ctx.author.id,
            )
            await conn.execute(
                'UPDATE profile SET money=money-$1 WHERE "user"=$2;',
                price,
                user.id,
            )
            await conn.execute(
                'UPDATE inventory SET "equipped"=$1 WHERE "item"=$2;',
                False,
                itemid,
            )
            await self.bot.log_transaction(
                ctx,
                from_=ctx.author.id,
                to=user.id,
                subject="item = OFFER",
                data={"Name": item["name"], "Value": item["value"]},
                conn=conn,
            )
            await self.bot.log_transaction(
                ctx,
                from_=ctx.author,
                to=user,
                subject="offer",
                data=item,
                conn=conn,
            )
        await ctx.send(
            _(
                "Successfully bought item `{itemid}`. Use `{prefix}inventory` to view"
                " your updated inventory."
            ).format(itemid=itemid, prefix=ctx.clean_prefix)
        )

    @has_char()
    @user_cooldown(600)  # prevent too long sale times
    @commands.command(aliases=["merch"], brief=_("Sell items for their value"))
    @locale_doc
    async def merchant(self, ctx, *itemids: int):
        _(
            """`<itemids>` - The IDs of the items to sell, seperated by space

            Sells items for their value. Items that you don't own will be filtered out.

            If you are in an alliance which owns a trade building, your winnings will be multiplied by 1.5 for each level.

            (This command has a cooldown of 10 minutes.)"""
        )
        if not itemids:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(_("You cannot sell nothing."))
        async with self.bot.pool.acquire() as conn:
            allitems = await conn.fetch(
                "SELECT ai.id, value, equipped FROM inventory i JOIN allitems ai ON"
                " (i.item=ai.id) WHERE ai.id=ANY($1) AND ai.owner=$2",
                itemids,
                ctx.author.id,
            )

            value, amount, equipped = (
                sum(i["value"] for i in allitems),
                len(allitems),
                len([i for i in allitems if i["equipped"]]),
            )

            if not amount:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(
                    _("You don't own any items with the IDs: {itemids}").format(
                        itemids=", ".join([str(itemid) for itemid in itemids])
                    )
                )

            if equipped:
                if not await ctx.confirm(
                        _(
                            "You are about to sell {amount} equipped items. Are you sure?"
                        ).format(amount=equipped),
                        timeout=6,
                ):
                    return await ctx.send(_("Cancelled."))
            if buildings := await self.bot.get_city_buildings(
                    ctx.character_data["guild"]
            ):
                value = int(value * (1 + buildings["trade_building"] / 2))
            async with conn.transaction():
                await self.bot.delete_items([i["id"] for i in allitems], conn=conn)
                await conn.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    value,
                    ctx.author.id,
                )
            await self.bot.log_transaction(
                ctx,
                from_=1,
                to=ctx.author.id,
                subject="merch",
                data={"Gold": f"{len(itemids)} items", "Value": value},
                conn=conn,
            )
        await ctx.send(
            _(
                "You received **${money}** when selling item(s) `{itemids}`."
                " {additional}"
            ).format(
                money=value,
                itemids=", ".join([str(itemid) for itemid in itemids]),
                additional=_(
                    "Skipped `{amount}` because they did not belong to you."
                ).format(amount=len(itemids) - amount)
                if len(itemids) > amount
                else "",
            )
        )
        await self.bot.reset_cooldown(ctx)  # we finished

    @has_char()
    @user_cooldown(10)
    @commands.command(brief=_("Lock a weapon so it won't be sold by `merchall`"))
    @locale_doc
    async def weaponlock(self, ctx, itemid: int):
        _(
            # xgettext: no-python-format
            """`[itemid]` - The ID of the weapon you want to lock.

            Locks a specific weapon so that it will be ignored by the `merchall` command.
            Only non-equipped weapons can be locked, and the owner must match the item ID.

            (This command has a cooldown of 2 minutes.)
            """
        )
        try:

            async with self.bot.pool.acquire() as conn:
                # Fetch the item ID from inventory
                inventory_item = await conn.fetchrow(
                    'SELECT "item" FROM inventory WHERE "item" = $1;',
                    itemid
                )

                if not inventory_item:
                    await ctx.send(f"The item with ID {itemid} is not in your inventory.")
                    return

                # Fetch the item details from allitems to check ownership
                item_details = await conn.fetchrow(
                    'SELECT "owner" FROM allitems WHERE "id" = $1;',
                    inventory_item["item"]
                )

                if not item_details:
                    await ctx.send(f"The item with ID {itemid} does not exist or cannot be found.")
                    return

                # Check if the user is the owner
                if item_details["owner"] != ctx.author.id:
                    await ctx.send(f"You do not own the item with ID {itemid}.")
                    return

                # Check if the item is equipped
                inventory_check = await conn.fetchrow(
                    'SELECT "locked", "equipped" FROM inventory WHERE "item" = $1;',
                    itemid
                )

                if inventory_check["equipped"]:
                    await ctx.send(f"The item with ID {itemid} is currently equipped and cannot be locked.")
                    return

                if inventory_check["locked"]:
                    await ctx.send(f"The item with ID {itemid} is already locked.")
                    return

                # Lock the item
                await conn.execute(
                    'UPDATE inventory SET "locked" = TRUE WHERE "item" = $1;',
                    itemid
                )

                await ctx.send(f"Weapon with ID {itemid} has been successfully locked!")
        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n"
            error_message += traceback.format_exc()
            await ctx.send(error_message)
            print(error_message)

    @has_char()
    @user_cooldown(10)
    @commands.command(brief=_("Unlock a weapon so it can be sold by `merchall`"))
    @locale_doc
    async def weaponunlock(self, ctx, itemid: int):
        _(
            # xgettext: no-python-format
            """`[itemid]` - The ID of the weapon you want to unlock.

            Unlocks a specific weapon so that it can be sold by the `merchall` command.
            Only non-equipped weapons can be unlocked, and the owner must match the item ID.

            (This command has a cooldown of 2 minutes.)
            """
        )
        try:

            async with self.bot.pool.acquire() as conn:
                # Fetch the item ID from inventory
                inventory_item = await conn.fetchrow(
                    'SELECT "item" FROM inventory WHERE "item" = $1;',
                    itemid
                )

                if not inventory_item:
                    await ctx.send(f"The item with ID {itemid} is not in your inventory.")
                    return

                # Fetch the item details from allitems to check ownership
                item_details = await conn.fetchrow(
                    'SELECT "owner" FROM allitems WHERE "id" = $1;',
                    inventory_item["item"]
                )

                if not item_details:
                    await ctx.send(f"The item with ID {itemid} does not exist or cannot be found.")
                    return

                # Check if the user is the owner
                if item_details["owner"] != ctx.author.id:
                    await ctx.send(f"You do not own the item with ID {itemid}.")
                    return

                # Check if the item is equipped
                inventory_check = await conn.fetchrow(
                    'SELECT "locked", "equipped" FROM inventory WHERE "item" = $1;',
                    itemid
                )

                if not inventory_check["locked"]:
                    await ctx.send(f"The item with ID {itemid} is not locked.")
                    return

                # Lock the item
                await conn.execute(
                    'UPDATE inventory SET "locked" = FALSE WHERE "item" = $1;',
                    itemid
                )

                await ctx.send(f"Weapon with ID {itemid} has been successfully unlocked!")
        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n"
            error_message += traceback.format_exc()
            await ctx.send(error_message)
            print(error_message)

    @has_char()
    @user_cooldown(120)
    @commands.command(brief=_("Merch all non-equipped items"))
    @locale_doc
    async def merchall(
            self,
            ctx,
            hand_type: str = None,
            maxstat: IntFromTo(0, 200) = 200,
            minstat: IntFromTo(0, 100) = 0,
    ):
        _(
            # xgettext: no-python-format
            """`[hand_type]` - Optional filter for '1h', '2h', or 'all' items; defaults to all
            `[maxstat]` - The highest damage/defense to include; defaults to 100
            `[minstat]` - The lowest damage/defense to include; defaults to 0
            Sells all your non-equipped items for their value. A convenient way to sell a large amount of items at once.
            You can specify '1h' for one-handed items, '2h' for two-handed items, or 'all'/'none' for all items.
            If you are in an alliance which owns a trade building, your earnings will be increased by 50% for each level.
            (This command has a cooldown of 30 minutes.)"""
        )

        # Validate hand_type if provided
        if hand_type and hand_type.lower() not in ['1h', '2h', 'all']:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(
                _("Invalid hand type. Please use '1h', '2h', or 'all' if you want to filter by hands."))

        # Convert 'all' to None to simplify logic
        if hand_type and hand_type.lower() == 'all':
            hand_type = None

        async with self.bot.pool.acquire() as conn:
            # Modified query to include hand filtering
            base_query = """
                SELECT ai.id, value 
                FROM inventory i 
                JOIN allitems ai ON (i.item = ai.id) 
                WHERE ai.owner = $1 
                AND i.equipped IS FALSE 
                AND i.locked IS FALSE 
                AND ai.armor + ai.damage BETWEEN $2 AND $3
            """

            # Add hand type filtering if specified
            if hand_type:
                if hand_type.lower() == '1h':
                    base_query += " AND (ai.hand = 'any' OR ai.hand = 'left' OR ai.hand = 'right')"
                else:  # 2h
                    base_query += " AND ai.hand = 'both'"

            # Fetch items with the constructed query
            query_params = [ctx.author.id, minstat, maxstat]
            allitems = await conn.fetch(base_query, *query_params)

            count, money = len(allitems), sum(i["value"] for i in allitems)
            if count == 0:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_("Nothing to merch."))

            if buildings := await self.bot.get_city_buildings(
                    ctx.character_data["guild"]
            ):
                money = int(money * (1 + buildings["trade_building"] / 2))

            # Format the hand type string for display
            hand_display = ""
            if hand_type:
                hand_display = " 2 handed" if hand_type.lower() == "2h" else " 1 handed"

            if not await ctx.confirm(
                    _(
                        "You are about to sell **{count}**{hand_type} items for **${money}**!\nAre you"
                        " sure you want to do this?"
                    ).format(count=count, hand_type=hand_display, money=money)
            ):
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_("Cancelled selling your items."))

            # Verify count hasn't changed (with same hand type filter)
            check_query = base_query.replace("SELECT ai.id, value", "SELECT count(value)")
            newcount = await conn.fetchval(check_query, *query_params)

            if newcount != count:
                await ctx.send(
                    _(
                        "Looks like you got more or less items in that range in the"
                        " meantime. Please try again."
                    )
                )
                return await self.bot.reset_cooldown(ctx)

            async with conn.transaction():
                await self.bot.delete_items([i["id"] for i in allitems], conn=conn)
                await conn.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    money,
                    ctx.author.id,
                )

            await self.bot.log_transaction(
                ctx,
                from_=1,
                to=ctx.author.id,
                subject="merch",
                data={"Gold": f"{count}{hand_display} items", "Value": money},
                conn=conn,
            )

        await ctx.send(
            _("Merched **{count}**{hand_type} items for **${money}**.").format(
                count=count, hand_type=hand_display, money=money
            )
        )

    @commands.command(brief=_("View your shop offers"))
    @locale_doc
    async def pending(self, ctx):
        _(
            """View your pending shop offers. This is a convenient way to find IDs of items that you put on the market."""
        )
        items = await self.bot.pool.fetch(
            "SELECT * FROM allitems ai JOIN market m ON (m.item=ai.id) WHERE"
            ' ai."owner"=$1;',
            ctx.author.id,
        )
        if not items:
            return await ctx.send(_("You don't have any pending shop offers."))
        items = [
            discord.Embed(
                title=_("Your pending items"),
                description=_("Use `{prefix}buy {item}` to buy this.").format(
                    prefix=ctx.clean_prefix, item=item["item"]
                ),
                colour=discord.Colour.blurple(),
            )
            .add_field(name=_("Name"), value=item["name"])
            .add_field(name=_("Type"), value=item["type"])
            .add_field(name=_("Damage"), value=item["damage"])
            .add_field(name=_("Armor"), value=item["armor"])
            .add_field(name=_("Value"), value=f"${item['value']}")
            .add_field(name=_("Price"), value=f"${item['price']}")
            .set_footer(
                text=_("Item {num} of {total}").format(num=idx + 1, total=len(items))
            )
            for idx, item in enumerate(items)
        ]
        await self.bot.paginator.Paginator(extras=items).paginate(ctx)




    def get_time_until_expiry(self, timestamp, expiry_duration_hours):
        expiry_time = timestamp + datetime.timedelta(hours=expiry_duration_hours)
        time_left = expiry_time - self.get_current_time()

        if time_left.total_seconds() <= 0:
            return "00:00:00"

        # Convert the time left into hours, minutes, and seconds
        hours, remainder = divmod(time_left.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"

    @has_char()
    @commands.cooldown(1, 300, commands.BucketType.user)
    @commands.command(brief=_("Buys an item or crate from the trader"))
    @locale_doc
    async def trader(self, ctx):
        _(
            """Purchase items or crates from the trader.

            Use this command to buy items or crates from the trader's current offers. The trader's offers refresh every 12 hours.

            You will be presented with a list of available items and crates. Select the one you wish to purchase. Ensure you have enough money to make the purchase.

            **Note:** This command has a cooldown of 5 minutes per user.
            """
        )

        try:
            player_id = ctx.author.id

            # Refresh player shop cache
            if player_id not in self.player_item_cache:
                self.player_item_cache[player_id] = {}

            # Remove expired items and crates (older than 12 hours)
            self.player_item_cache[player_id] = {
                name: (item, price, timestamp, rarity)
                for name, (item, price, timestamp, rarity) in self.player_item_cache[player_id].items()
                if not self.is_item_expired(timestamp, 12)
            }

            # Generate new items and crates if cache is empty
            if not self.player_item_cache[player_id]:
                items, crates = await self.generate_items_and_crates(ctx)
                for item, price in items:
                    self.player_item_cache[player_id][item['name']] = (
                        item,
                        price,
                        self.get_current_time(),
                        None
                    )
                for crate, price, rarity in crates:
                    self.player_item_cache[player_id][crate['name']] = (
                        crate,
                        price,
                        self.get_current_time(),
                        rarity
                    )

            # Separate items and crates for offers
            items_offers = [
                (item, price) for item, price, timestamp, rarity
                in self.player_item_cache[player_id].values()
                if rarity is None
            ]
            crates_offers = [
                (item, price, rarity) for item, price, timestamp, rarity
                in self.player_item_cache[player_id].values()
                if rarity
            ]

            if not items_offers and not crates_offers:
                return await ctx.send("There are no items or crates available at the moment.")

            # Get the timestamp of the first item (all items share the same refresh time in this model)
            first_item_timestamp = next(iter(self.player_item_cache[player_id].values()))[2]
            time_left = self.get_time_until_expiry(first_item_timestamp, 12)

            await ctx.send(f"All items will expire in {time_left}.")

            # Combine offers for paginator
            all_offers = items_offers + crates_offers

            # Build display text for paginator
            offer_entries = []
            offer_choices = []
            for offer in all_offers:
                if len(offer) == 2:  # It's an item
                    item, price = offer
                    offer_entries.append(
                        f"**{item['name']}** ({item['type_']}) - "
                        f"{item['armor'] if item['type_'] == 'Shield' else item['damage']} - **${price}**"
                    )
                    offer_choices.append(item['name'])
                else:
                    # It's a crate
                    item, price, rarity = offer
                    offer_entries.append(f"**{rarity.capitalize()} Crate** - **${price}**")
                    offer_choices.append(f"{rarity.capitalize()} Crate")

            try:
                # Use your paginator or any menu system that returns an index (offerid)
                offerid = await self.bot.paginator.Choose(
                    title=("The Trader"),
                    placeholder=("Select an item or crate to purchase"),
                    return_index=True,
                    entries=offer_entries,
                    choices=offer_choices,
                ).paginate(ctx)
            except NoChoice:
                return await ctx.send("You did not choose anything.")

            # Ensure offerid is within the valid range
            if offerid < 0 or offerid >= len(all_offers):
                return await ctx.send("Invalid choice.")

            selected_offer = all_offers[offerid]

            # Check if item or crate
            if len(selected_offer) == 2:
                # It's an item (including possible Weapontoken or Resetpotion)
                item, price = selected_offer
                item_name = item['name']

                # Special case: Weapontoken
                if item_name == 'Weapontoken':
                    embed = discord.Embed(
                        title="Weapontoken Purchased",
                        description=f"**Name:** {item_name}",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="Price", value=f"${price}")

                # Special case: Resetpotion
                elif item_name == 'Resetpotion':
                    embed = discord.Embed(
                        title="Reset Potion Purchased",
                        description=f"**Name:** {item_name}",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="Price", value=f"${price}")

                else:
                    # Normal item
                    embed = discord.Embed(
                        title="Weapon Purchased",
                        description=f"**Name:** {item_name}",
                        color=discord.Color.blue()
                    )
                    embed.add_field(name="Type", value=item['type_'])
                    embed.add_field(
                        name="Stat",
                        value=item['armor'] if item['type_'] == 'Shield' else item['damage']
                    )
                    embed.add_field(name="Price", value=f"${price}")

                rarity = None  # Because it's not a crate
                item_data = item

            else:
                # It's a crate
                item, price, rarity = selected_offer
                item_name = f'{rarity.capitalize()} Crate'
                item_data = None

                embed = discord.Embed(
                    title="Crate Purchased",
                    description=f"**Name:** {item_name}",
                    color=discord.Color.gold()
                )
                embed.add_field(name="Price", value=f"${price}")

            # Debug prints (optional)
            print(f"Embed Title: {embed.title}")
            print(f"Embed Description: {embed.description}")
            print(f"Embed Fields: {embed.fields}")

            # Proceed with the purchase transaction
            async with self.bot.pool.acquire() as conn:
                # Check if user has enough money
                if not await has_money(self.bot, ctx.author.id, price, conn=conn):
                    return await ctx.send("You are too poor to buy this item/crate.")

                # Deduct money
                await conn.execute(
                    'UPDATE profile SET "money" = "money" - $1 WHERE "user" = $2;',
                    price,
                    ctx.author.id,
                )

                # Log transaction (optional, if you have a logging system)
                await self.bot.log_transaction(
                    ctx,
                    from_=1,
                    to=ctx.author.id,
                    subject="trader ITEM/CRATE",
                    data={
                        "Name": item_name,
                        "Value": item_data["value"] if item_data else 'N/A',
                        "Price": price,
                        "Rarity": rarity.capitalize() if rarity else 'Item',
                    },
                    conn=conn,
                )

                expected_price = price

                # If it's a normal weapon-like item (not Weapontoken or Resetpotion), create it in DB
                if item_data and item_name not in ['Weapontoken', 'Resetpotion']:
                    try:
                        # Prepare required arguments
                        name = item_data['name']
                        value = item_data.get('value', 0)
                        type_ = item_data.get('type_', 'Unknown')
                        damage = item_data.get('damage', 0)
                        armor = item_data.get('armor', 0)
                        hand = item_data.get('hand', None)
                        element = item_data.get('element', None)
                        owner = ctx.author.id

                        await self.bot.create_item(
                            name=name,
                            value=value,
                            type_=type_,
                            damage=damage,
                            armor=armor,
                            owner=owner,
                            hand=hand,
                            element=element
                        )
                    except Exception as e:
                        import traceback
                        error_message = f"Error occurred: {e}\n" + traceback.format_exc()
                        await ctx.send(error_message)
                        print(error_message)

                # Handle crates
                if rarity:
                    # Increase crate count for user
                    await conn.execute(
                        f'UPDATE profile SET "crates_{rarity}" = "crates_{rarity}" + 1 WHERE "user" = $1;',
                        ctx.author.id,
                    )

                    # Remove from cache
                    for name, (citem, cprice, ctimestamp, crarity) in list(self.player_item_cache[player_id].items()):
                        if crarity == rarity and cprice == expected_price:
                            del self.player_item_cache[player_id][name]
                            print(f"Removed {name} with rarity {rarity} and price {price} from cache.")
                            break

                # Handle Weapontoken
                elif item_name == 'Weapontoken':
                    new_value = await conn.fetchval(
                        'SELECT weapontoken FROM profile WHERE "user"=$1;',
                        ctx.author.id
                    )
                    new_value = (new_value or 0) + 1
                    await conn.execute(
                        'UPDATE profile SET weapontoken=$1 WHERE "user"=$2;',
                        new_value,
                        ctx.author.id
                    )
                    del self.player_item_cache[player_id][item_name]

                # Handle Resetpotion
                elif item_name == 'Resetpotion':
                    # Example: increase the resetpotion count by 1
                    # (or set it to 1 if you treat it as a boolean)
                    new_value = await conn.fetchval(
                        'SELECT resetpotion FROM profile WHERE "user"=$1;',
                        ctx.author.id
                    )
                    new_value = (new_value or 0) + 1
                    await conn.execute(
                        'UPDATE profile SET resetpotion=$1 WHERE "user"=$2;',
                        new_value,
                        ctx.author.id
                    )
                    del self.player_item_cache[player_id][item_name]

                # If it's a normal item (not Weapontoken/Resetpotion/crate), remove from cache
                elif item_data and item_name in self.player_item_cache[player_id]:
                    del self.player_item_cache[player_id][item_name]

            await ctx.send(embed=embed)

        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n" + traceback.format_exc()
            await ctx.send(error_message)
            print(error_message)

    async def update_user_eggs(self, user_id, egg_name, conn):
        # Update user's eggs in the database
        await conn.execute(
            'INSERT INTO user_eggs (user_id, egg_name) VALUES ($1, $2);',
            user_id,
            egg_name,
        )

    @is_gm()
    @commands.command(brief=_("Buys an egg from the trader"))
    async def petshop(self, ctx):
        try:
            current_time = time.time()

            # Check if 24 hours have passed since the last refresh
            if current_time - self.last_refresh_time >= 24 * 60 * 60:
                self.last_refresh_time = current_time  # Update the last refresh time
                self.sold_out_items = []  # Reset sold-out items

                # Refresh eggs and prices
                egg_rarities = [
                    {"name": "Common Egg", "emoji": "<:common_egg:1200370597239201822>", "weight": 56.5},
                    {"name": "Uncommon Egg", "emoji": "<:uncommon_egg:1200372201359147018>", "weight": 30},
                    {"name": "Rare Egg", "emoji": "<:rare_egg:1200371479490076702>", "weight": 10},
                    {"name": "Very Rare Egg", "emoji": "<:veryrare_egg:1200371709560229979>", "weight": 3},
                    {"name": "Legendary Egg", "emoji": "<:legendary_egg:1200370906552352848>", "weight": 0.5}
                ]

                offers = []
                for i in range(10):  # Display 10 items in the shop
                    egg_rarity = random.choices(
                        egg_rarities,
                        weights=[entry['weight'] / sum(entry['weight'] for entry in egg_rarities) for entry in
                                 egg_rarities]
                    )[0]

                    if egg_rarity['name'] == 'Common Egg':
                        price = random.randint(130000, 180000)
                    # ... (rest of the code remains unchanged)
                    elif egg_rarity['name'] == 'Uncommon Egg':
                        price = random.randint(200000, 300000)
                    elif egg_rarity['name'] == 'Rare Egg':
                        price = random.randint(300000, 750000)
                    elif egg_rarity['name'] == 'Very Rare Egg':
                        price = random.randint(750000, 1250000)
                    elif egg_rarity['name'] == 'Legendary Egg':
                        price = random.randint(2000000, 5000000)
                    else:
                        # Handle the case where the rarity is not recognized
                        price = 0  # You may want to set a default value or handle this differently

                    offers.append((egg_rarity, price))
            else:
                # If not yet 24 hours, use the existing offers
                offers = getattr(self, "offers", [])

            # Save the offers for future use
            self.offers = offers

            entries = [
                f"{index + 1}. {i[0]['emoji']} ({i[0]['name']}) - **${i[1]}{' (Sold Out)' if index in self.sold_out_items else ''}**"
                for index, i in enumerate(offers) if i[0] is not None
            ]

            choices = [egg[0]['name'] for egg in offers]

            try:
                offerid = await self.bot.paginator.Choose(
                    title=_("The Trader"),
                    placeholder=_("Select an egg to purchase"),
                    return_index=True,
                    entries=entries,
                    choices=choices,
                ).paginate(ctx)

                # Check if the selected item is sold out
                if offerid in self.sold_out_items:
                    return await ctx.send(_("This egg is sold out. Please choose another one."))

            except NoChoice:  # prevent cooldown reset
                return await ctx.send(_("You did not choose anything."))

            selected_egg = offers[offerid][0]
            self.sold_out_items.append(offerid)  # Mark the selected item as sold

            async with self.bot.pool.acquire() as conn:
                user_eggs = await conn.fetch(
                    'SELECT * FROM user_eggs WHERE user_id=$1;',
                    ctx.author.id,
                )

                if len(user_eggs) >= 3:
                    return await ctx.send(_("You already have the maximum limit of 3 eggs. You cannot buy more."))

            embed = discord.Embed(
                title=_("Successfully bought egg"),
                description=(
                    f"{selected_egg['emoji']} ({selected_egg['name']}) - **${offers[offerid][1]}**"
                ),
                color=discord.Color.green(),
            )

            async with self.bot.pool.acquire() as conn:
                if not await has_money(self.bot, ctx.author.id, offers[offerid][1], conn=conn):
                    return await ctx.send(_("You are too poor to buy this egg."))

                await conn.execute(
                    'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                    offers[offerid][1],
                    ctx.author.id,
                )

                await self.update_user_eggs(ctx.author.id, selected_egg['name'], conn=conn)

                await self.bot.log_transaction(
                    ctx,
                    from_=1,
                    to=ctx.author.id,
                    subject="trader EGG",
                    data={
                        "Egg": selected_egg['name'],
                        "Price": offers[offerid][1],
                    },
                    conn=conn,
                )

            await ctx.send(embed=embed)

        except Exception as e:
            print(f"An error occurred: {e}")
            await ctx.send(_(f"An error occurred while processing your request. {e}"))

    async def get_incubation_time(self, rarity):
        # Implement the logic to calculate incubation time based on egg rarity
        if rarity == "Common Egg":
            return dt.timedelta(hours=1)
        elif rarity == "Uncommon Egg":
            return dt.timedelta(hours=2)
        elif rarity == "Rare Egg":
            return dt.timedelta(hours=4)
        elif rarity == "Very Rare Egg":
            return dt.timedelta(hours=8)
        elif rarity == "Legendary Egg":
            return dt.timedelta(hours=12)
        else:
            # Default to 1 hour if the rarity is not recognized
            return dt.timedelta(hours=1)

    async def start_incubation(self, user_id, egg_id, egg_name, ctx):
        try:
            async with self.bot.pool.acquire() as conn:
                # Check if the user_id exists in user_eggs
                user_owns_egg = await conn.fetchval(
                    'SELECT COUNT(*) FROM user_eggs WHERE user_id = $1 AND id = $2;',
                    user_id, egg_id
                )

                if not user_owns_egg:
                    return await ctx.send(_("Invalid user ID or egg ID."))

                # Check if the egg is already incubating
                is_incubating = await conn.fetchval(
                    'SELECT COUNT(*) FROM incubating_eggs WHERE user_id = $1 AND egg_id = $2;',
                    user_id, egg_id
                )

                if is_incubating:
                    return await ctx.send(_("This egg is already incubating."))

                # Get incubation time based on egg rarity
                incubation_time = await self.get_incubation_time(egg_name)

                # Insert into incubating_eggs
                await conn.execute(
                    'INSERT INTO incubating_eggs (user_id, egg_id, egg_name, start_time) VALUES ($1, $2, $3, $4);',
                    user_id, egg_id, egg_name, dt.datetime.now(dt.timezone.utc)
                )

                await ctx.send(_("Egg incubated successfully!"))

        except Exception as e:
            print(f"An error occurred: {e}")
            await ctx.send(_(f"An error occurred while processing your request. {e}"))

    async def get_incubation_status(self, user_id, egg_name, unique_identifier, ctx):
        # Get the remaining time and other details from Redis
        incubation_key = f'incubation:{user_id}:{unique_identifier}'
        incubation_details = await self.bot.redis.hgetall(incubation_key)
        await ctx.send("Checking Key..")

        if incubation_details:
            await ctx.send("Found a key!..")
            # Extract remaining time from the hash
            remaining_time = int(incubation_details.get('remaining_time', 0))
            return remaining_time if remaining_time > 0 else None
        else:
            await ctx.send("I did not find a key!..")
            return None

    async def update_incubation_status(self, user_id, egg_name, unique_identifier, time_delta, hp_change):
        # Update remaining time and HP in the Redis hash
        incubation_key = f'incubation:{user_id}:{unique_identifier}'
        self.bot.redis.hincrbyfloat(incubation_key, 'remaining_time', -time_delta.total_seconds())
        self.bot.redis.hincrby(incubation_key, 'hp', hp_change)

        # Update the egg's HP in the database (optional)
        async with self.bot.pool.acquire() as conn:
            await conn.execute(
                'UPDATE user_eggs SET hp=LEAST(100, hp+$1) WHERE user_id=$2 AND egg_name=$3;',
                hp_change,
                user_id,
                egg_name,
            )

    async def start_incubation(self, user_id, egg_id, egg_name, ctx):
        try:
            # Check if the user_id exists in user_eggs
            async with self.bot.pool.acquire() as conn:
                user_exists = await conn.fetchval('SELECT COUNT(*) FROM user_eggs WHERE user_id = $1 AND id = $2;',
                                                  user_id, egg_id)

            if not user_exists:
                return await ctx.send(_("Invalid user ID."))

            # Get incubation time based on egg rarity
            incubation_time = await self.get_incubation_time(egg_name)

            # Set the current time in UTC
            current_time = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)

            # Set the incubation end time as an offset-aware datetime
            incubation_end_time = current_time + incubation_time

            # Use the egg ID for each egg in the incubation key
            incubation_key = f'incubation:{user_id}:{egg_id}'

            # Insert into incubating_eggs with the incubation end time
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    'INSERT INTO incubating_eggs (user_id, egg_id, egg_name, incubation_end_time) VALUES ($1, $2, $3, $4);',
                    user_id,
                    egg_id,
                    egg_name,
                    incubation_end_time,
                )

            await ctx.send(_("Egg incubated successfully!"))

        except Exception as e:
            print(f"An error occurred: {e}")
            await ctx.send(_(f"An error occurred while processing your request. {e}"))

    async def get_incubation_status(self, user_id, egg_name, unique_identifier, ctx):
        # Get the remaining time and other details from the database
        async with self.bot.pool.acquire() as conn:
            incubation_details = await conn.fetchrow(
                'SELECT incubation_end_time FROM incubating_eggs WHERE user_id=$1 AND egg_id=$2 AND egg_name=$3;',
                user_id,
                unique_identifier,
                egg_name,
            )

        if incubation_details:
            incubation_end_time = incubation_details['incubation_end_time']

            # Calculate remaining time
            remaining_time = max(0,
                                 (incubation_end_time - dt.datetime.utcnow().replace(
                                     tzinfo=dt.timezone.utc)).total_seconds())

            # Format remaining time as HH:MM:SS
            hours, remainder = divmod(remaining_time, 3600)
            minutes, seconds = divmod(remainder, 60)
            remaining_time_str = f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"

            return remaining_time_str

        return None

    @is_gm()
    @commands.command(brief=_("Incubates a purchased egg"))
    async def incubate(self, ctx, egg_id: int):
        try:
            async with self.bot.pool.acquire() as conn:
                # Check if the user owns the selected egg
                user_owns_egg = await conn.fetchval(
                    'SELECT COUNT(*) FROM user_eggs WHERE user_id=$1 AND id=$2;',
                    ctx.author.id,
                    egg_id,
                )

                if user_owns_egg:
                    # Retrieve the selected egg's details
                    selected_egg = await conn.fetchrow(
                        'SELECT egg_name FROM user_eggs WHERE id=$1;',
                        egg_id,
                    )

                    if selected_egg:
                        egg_name = selected_egg['egg_name']

                        # Start incubation using the dedicated method
                        await self.start_incubation(ctx.author.id, egg_id, egg_name, ctx)

                        await ctx.send(_("Egg incubated successfully!"))
                    else:
                        await ctx.send(_("Invalid egg ID."))
                else:
                    await ctx.send(_("You don't own the selected egg."))

        except Exception as e:
            print(f"An error occurred: {e}")
            await ctx.send(_(f"An error occurred while processing your request. {e}"))

    async def choose_pet(self, rarity):
        if rarity == "Common Egg":
            pet_chances = {
                "Rock Pup": {"attack": 10, "defense": 5, "hp": 80, "food": 100, "hunger": 0, "happiness": 100,
                             "picture_link": "https://gcdnb.pbrd.co/images/GmulytelU0XB.png"},
            }
        elif rarity == "Uncommon Egg":
            pet_chances = {
                "Pet4": {"attack": 15, "defense": 10, "hp": 85, "food": 100, "hunger": 0, "happiness": 100,
                         "picture_link": "link4"},
            }
        # Add more cases for other rarities

        # Randomly choose a pet with equal weights
        pet_name = random.choice(list(pet_chances.keys()))

        return pet_name, pet_chances[pet_name]

    @is_gm()
    @commands.command(brief=_("Hatch an incubating egg"))
    async def hatch(self, ctx, egg_id: int):
        try:
            async with self.bot.pool.acquire() as conn:
                # Check if the user owns the selected egg
                user_owns_egg = await conn.fetchval(
                    'SELECT COUNT(*) FROM user_eggs WHERE user_id=$1 AND id=$2;',
                    ctx.author.id,
                    egg_id,
                )

                if user_owns_egg:
                    # Check if the egg is currently incubating
                    incubating_egg = await conn.fetchrow(
                        'SELECT egg_name, incubation_end_time FROM incubating_eggs WHERE user_id=$1 AND egg_id=$2;',
                        ctx.author.id,
                        egg_id,
                    )

                    if incubating_egg:
                        egg_name = incubating_egg['egg_name']
                        end_time = incubating_egg['incubation_end_time']

                        # Check if the current time is past the end time
                        if dt.datetime.now(dt.timezone.utc) >= end_time:
                            # Choose a pet based on the rarity
                            pet_name, pet_attributes = await self.choose_pet(egg_name)

                            # Remove the egg from incubating_eggs first
                            await conn.execute(
                                'DELETE FROM incubating_eggs WHERE user_id=$1 AND egg_id=$2;',
                                ctx.author.id,
                                egg_id,
                            )

                            # Insert the pet into user_pets with XP set to 0
                            await conn.execute(
                                'INSERT INTO user_pets (user_id, pet_name, rarity, xp, attack, defense, hp, food, hunger, happiness, picture_link, currentHP) '
                                'VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12);',
                                ctx.author.id,
                                pet_name,
                                egg_name,
                                0,  # XP set to 0
                                pet_attributes["attack"],
                                pet_attributes["defense"],
                                pet_attributes["hp"],
                                pet_attributes["food"],
                                pet_attributes["hunger"],
                                pet_attributes["happiness"],
                                pet_attributes["picture_link"],
                                pet_attributes["hp"],
                            )

                            # Remove the egg from user_eggs
                            await conn.execute(
                                'DELETE FROM user_eggs WHERE user_id=$1 AND id=$2;',
                                ctx.author.id,
                                egg_id,
                            )

                            await ctx.send(_(f"Egg hatched successfully! You obtained a new pet: {pet_name}"))
                        else:
                            await ctx.send(_("The selected egg is still incubating."))
                    else:
                        await ctx.send(_("The selected egg is not currently incubating."))
                else:
                    await ctx.send(_("You don't own the selected egg."))
        except Exception as e:
            print(f"An error occurred: {e}")
            await ctx.send(_(f"An error occurred while processing your request. {e}"))

    async def xp_to_level(self, xp):
        levels = {
            1: 0,
            2: 1500,
            3: 9000,
            4: 22500,
            5: 42000,
            6: 67500,
            7: 99000,
            8: 136500,
            9: 180000,
            10: 229500,
            11: 285000,
            12: 346500,
            13: 414000,
            14: 487500,
            15: 567000,
            16: 697410,
            17: 857814,
            18: 1055112,
            19: 1297787,
            20: 1596278,
        }

        for level, xp_threshold in levels.items():
            if xp < xp_threshold:
                return level - 1
        return len(levels)

    @is_gm()
    @commands.command(brief=_("View your pets"), hidden=True)
    async def petsold(self, ctx):
        try:
            async with self.bot.pool.acquire() as conn:
                # Fetch the user's pets from the database
                user_pets = await conn.fetch(
                    'SELECT * FROM user_pets WHERE user_id=$1;',
                    ctx.author.id,
                )

                if not user_pets:
                    await ctx.send(_("You don't have any pets yet. Hatch an egg to get a pet!"))
                    return

                for pet in user_pets:
                    level = await self.xp_to_level(pet['xp'])

                    embed = discord.Embed(title=f"Your Pet: {pet['pet_name']}", color=discord.Colour.green())
                    embed.set_thumbnail(url=pet['picture_link'])

                    embed.add_field(name=f"", value=f"**🌟 Level:** {level}", inline=False)
                    embed.add_field(name=f"", value=f"**❤️ Health:** {pet['currentHP']}/{pet['hp']}", inline=False)
                    embed.add_field(name=f"", value=f"🥤** Hunger:** {pet['hunger']}/{pet['food']}",
                                    inline=False)  # Assuming 'food' represents thirst
                    embed.add_field(name=f"", value=f"**😊 Happiness:** {pet['happiness']}/100",
                                    inline=False)
                    embed.add_field(name=f"", value=f"=========================",
                                    inline=False)
                    embed.add_field(name=f"", value=f"**⚔️ Attack:** {pet['attack']}", inline=False)
                    embed.add_field(name=f"", value=f"**🛡️ Defense:** {pet['defense']}", inline=False)

                    await ctx.send(embed=embed)

        except Exception as e:
            print(f"An error occurred: {e}")
            await ctx.send(_(f"An error occurred while processing your request. {e}"))

    @is_gm()
    @commands.command()
    async def egglist(self, ctx):
        try:
            async with self.bot.pool.acquire() as conn:
                # Retrieve the user's egg list with incubation status from the database
                user_eggs = await conn.fetch(
                    'SELECT ue.egg_name, ue.id, ie.incubation_end_time '
                    'FROM user_eggs ue '
                    'LEFT JOIN incubating_eggs ie ON ue.id = ie.egg_id '
                    'WHERE ue.user_id = $1;',
                    ctx.author.id,
                )

                if not user_eggs:
                    return await ctx.send(_("You don't own any eggs yet."))

                # Prepare and send a message containing the user's egg list
                embed = discord.Embed(
                    title=_("Your Egg List"),
                    color=discord.Color.blue(),
                )

                egg_rarities = {
                    "Common Egg": "<:common_egg:1200370597239201822>",
                    "Uncommon Egg": "<:uncommon_egg:1200372201359147018>",
                    "Rare Egg": "<:rare_egg:1200371479490076702>",
                    "Very Rare Egg": "<:veryrare_egg:1200371709560229979>",
                    "Legendary Egg": "<:legendary_egg:1200370906552352848>"
                }

                for egg in user_eggs:
                    egg_name = egg['egg_name']
                    egg_id = egg['id']
                    emoji = egg_rarities.get(egg_name, "")
                    end_time = egg['incubation_end_time']

                    if end_time:
                        # Calculate remaining time based on the current time and end_time
                        current_time = dt.datetime.now(dt.timezone.utc)
                        remaining_time = int(max(0, (end_time - current_time).total_seconds()))

                        # Format remaining time as HH:MM:SS
                        hours, remainder = divmod(remaining_time, 3600)
                        minutes, seconds = divmod(remainder, 60)
                        remaining_time_str = f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"

                        embed.add_field(
                            name=f"{emoji} {egg_name} (ID: {egg_id})",
                            value=f"**Incubation Status**: {remaining_time_str}",
                            inline=False
                        )
                    else:
                        embed.add_field(
                            name=f"{emoji} {egg_name} (ID: {egg_id})",
                            value=_("Not incubating"),
                            inline=False
                        )

                await ctx.send(embed=embed)

        except Exception as e:
            print(f"An error occurred: {e}")
            await ctx.send(_(f"An error occurred while processing your request. {e}"))


async def setup(bot):
    await bot.add_cog(Trading(bot))
