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

from contextlib import suppress
from datetime import datetime

import discord
from discord import Embed

from discord.ext import commands

from cogs.shard_communication import user_on_cooldown as user_cooldown
from utils import checks as checks
from utils import random
from utils.i18n import _, locale_doc


class Halloween(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.waiting = None

    def _is_event_enabled(self) -> bool:
        event_flags = getattr(self.bot, "event_flags", None)
        if event_flags is None:
            return False
        return bool(event_flags.get("halloween", False))

    async def _ensure_event_enabled(self, ctx) -> bool:
        if self._is_event_enabled():
            return True
        await ctx.send(_("The Halloween event is currently disabled."))
        return False

    @checks.has_char()
    @user_cooldown(3600)
    @commands.command(aliases=["tot"], brief=_("Trick or treat!"))
    @locale_doc
    async def trickortreat(self, ctx):
        _(
            # xgettext: no-python-format
            """Walk around the houses and scare the residents! Maybe they have a gift for you?

            This command requires two players, one that is waiting and one that rings at the door.
            If you are the one waiting, you will get a direct message from the bot later, otherwise you will get a reply immediately.

            There is a 50% chance you will receive a halloween bag from the other person.

            (This command has a cooldown of 3h)"""
        )
        if not await self._ensure_event_enabled(ctx):
            return

        waiting = self.waiting
        if not waiting:
            self.waiting = ctx.author
            return await ctx.send(
                _("You walk around the houses... Noone is there... *yet*")
            )
        self.waiting = None
        async with self.bot.pool.acquire() as conn:
            if random.randint(0, 2) <= 1:
                await ctx.send(
                    _(
                        "You walk around the houses and ring at {waiting}'s house!"
                        " That's a trick or treat bag for you, yay!"
                    ).format(waiting=waiting)
                )
                await conn.execute(
                    'UPDATE profile SET "trickortreat"="trickortreat"+1 WHERE'
                    ' "user"=$1;',
                    ctx.author.id,
                )
            else:
                await ctx.send(
                    _(
                        "You walk around the houses and ring at {waiting}'s house!"
                        " Sadly they don't have anything for you..."
                    ).format(waiting=waiting)
                )
            with suppress(discord.Forbidden):
                if random.randint(0, 1) == 1:
                    await waiting.send(
                        "The waiting was worth it: {author} rang! That's a trick or"
                        " treat bag for you, yay!".format(author=ctx.author)
                    )
                    await conn.execute(
                        'UPDATE profile SET "trickortreat"="trickortreat"+1 WHERE'
                        ' "user"=$1;',
                        waiting.id,
                    )
                else:
                    await waiting.send(
                        "{author} rings at your house, but... Nothing for you! 👻".format(
                            author=ctx.author
                        )
                    )

            if random.randint(1, 100) < 5:
                backgrounds = [
                    "https://i.ibb.co/wJ43ybH/totbg.png",
                ]
                background = random.choice(backgrounds)
                current_backgrounds = await conn.fetchval(
                    'SELECT "backgrounds" FROM profile WHERE "user"=$1;', ctx.author.id
                )
                if current_backgrounds is None or background not in current_backgrounds:
                    await conn.execute(
                        'UPDATE profile SET "backgrounds"=array_append("backgrounds", $1) WHERE "user"=$2;',
                        background,
                        ctx.author.id,
                    )
                    await ctx.send(
                        _(
                            "🎃 As you step out of the door, you open your candy and plastic reveals an ancient image on top of a chocolate bar, passed along for generations. You decide to keep it in your `{prefix}eventbackgrounds`."
                        ).format(
                            prefix=ctx.clean_prefix,
                        )
                    )

    @checks.has_char()
    @commands.group(aliases=["ss"], brief=_("Opens Special Halloween Shop"))
    @locale_doc
    async def spookyshop(self, ctx):
        """
        Dive into the spectral realm with our limited-time Spooky Season Shop.
        Unearth rare treasures using bones you've collected from various eerie events.
        """

        if not await self._ensure_event_enabled(ctx):
            return

        try:
            if ctx.invoked_subcommand is None:
                qualtity_shop = await self.bot.pool.fetchrow(
                    '''
                    SELECT ssuncommon, sstot, sstoken, ssmagic, ssrare, sslegendary, ssclass, ssbg, ssfortune, ssdivine 
                    FROM profile WHERE "user"=$1;
                    ''',
                    ctx.author.id
                )

                ssuncommon_value = qualtity_shop['ssuncommon']
                sstot_value = qualtity_shop['sstot']
                sstoken_value = qualtity_shop['sstoken']
                ssmagic_value = qualtity_shop['ssmagic']
                ssrare_value = qualtity_shop['ssrare']
                sslegendary_value = qualtity_shop['sslegendary']
                ssfortune_value = qualtity_shop['ssfortune']
                ssdivine_value = qualtity_shop['ssdivine']
                ssclass_value = qualtity_shop['ssclass']
                ssbg_value = qualtity_shop['ssbg']


                # Fetch the user's bone count
                bone_count = await self.get_bone_count(ctx.author.id)

                # Create the embed with various enhancements
                embed = Embed(title=_("👻 Halloween Shop 👻"), color=0xff4500)  # Dark orange color

                embed.set_thumbnail(url="https://i.ibb.co/sqWxZ6F/shop.jpg")
                embed.set_author(name=ctx.author.display_name)

                items = [
                    ("<:F_uncommon:1139514875828252702> Uncommon Crate", 30, ssuncommon_value),
                    ("<:F_rare:1139514880517484666> Rare Crate", 60, ssrare_value),
                    ("<:F_Magic:1139514865174720532> Magic Crate", 250, ssmagic_value),
                    ("<:F_Legendary:1139514868400132116> Legendary Crate", 1300, sslegendary_value),
                    ("<:f_money:1146593710516224090> Fortune Crate", 1750, ssfortune_value),
                    ("<:f_divine:1169412814612471869> Divine Crate", 2900, ssdivine_value),
                    ("🖼️ Seasonal Background", 650, ssbg_value),
                    ("🧙 Seasonal Class", 1000, ssclass_value),
                    ("🟡 Weapon Type Token", 200, sstoken_value),
                    ("🛍️ 3 Trick or Treat Bags", 200, sstot_value)
                ]

                for idx, (name, cost, quantity) in enumerate(items, 1):
                    if ctx.author.id == 7084358645919:
                        embed.add_field(name=f"{idx}:  {name}",
                                        value=_("Cost: {} Boners - {} available").format(cost, quantity), inline=False)

                        embed.set_footer(text=_("You have {} boners 💀 - $ss buy <ID> to buy.").format(bone_count),
                                         icon_url="https://i.ibb.co/5GK1Ry0/vecteezy-skeleton-halloween-cartoon-colored-clipart-8823016-removebg-preview.png")

                    else:
                        embed.add_field(name=f"{idx}:  {name}",
                                        value=_("Cost: {} Bones - {} available").format(cost, quantity), inline=False)

                        embed.set_footer(text=_("You have {} bones 💀 - $ss buy <ID> to buy.").format(bone_count),
                                         icon_url="https://i.ibb.co/5GK1Ry0/vecteezy-skeleton-halloween-cartoon-colored-clipart-8823016-removebg-preview.png")

                await ctx.send(embed=embed)

        except Exception as e:
            error_embed = Embed(title=_("🚫 An error occurred!"), description=_(
                f"Oh no! Something spooky happened. Try again later or contact our wizard for help. {e}"),
                                color=0xff0000)  # Red color for errors
            await ctx.send(embed=error_embed)

    @spookyshop.command(name="buy")
    @user_cooldown(30)
    async def _buy(self, ctx, item: int, quantity: int = 1):
        _("""
        This subcommand allows the user to buy an item from the Spooky Shop.

        :param item_name: The name of the item the user wants to buy.
        :param quantity: The quantity of the item the user wants to buy. Defaults to 1.
        """)

        if not await self._ensure_event_enabled(ctx):
            return

        if item < 0 and item > 10:
            await ctx.send("Invalid choice")
            return

        record = await self.bot.pool.fetchrow(
            'SELECT bones FROM profile WHERE "user"=$1;',
            ctx.author.id
        )
        if record:
            bones_count = record['bones']
        else:
            bones_count = 0

        if item == 1:
            if bones_count < 30:
                await ctx.send("You cannot afford this")
                return
            item1 = await self.bot.pool.fetchrow(
                'SELECT ssuncommon FROM profile WHERE "user"=$1;',
                ctx.author.id
            )
            quantity = item1['ssuncommon']
            if quantity <= 0:
                await ctx.send("You cannot purchase this: Sold Out!")
                return

            await self.bot.pool.execute(
                'UPDATE profile SET ssuncommon = ssuncommon - 1 WHERE "user"=$1;',
                ctx.author.id
            )

            await self.bot.pool.execute(
                'UPDATE profile SET bones = bones - 30 WHERE "user"=$1;',
                ctx.author.id
            )

            await self.bot.pool.execute(
                'UPDATE profile SET crates_uncommon = crates_uncommon + 1 WHERE "user"=$1;',
                ctx.author.id
            )
            await ctx.send("You have successfully purchased a <:F_uncommon:1139514875828252702> for 30 Bones!")

        if item == 2:
            if bones_count < 50:
                await ctx.send("You cannot afford this")
                return
            item1 = await self.bot.pool.fetchrow(
                'SELECT ssrare FROM profile WHERE "user"=$1;',
                ctx.author.id
            )
            quantity = item1['ssrare']
            if quantity <= 0:
                await ctx.send("You cannot purchase this: Sold Out!")
                return

            await self.bot.pool.execute(
                'UPDATE profile SET ssrare = ssrare - 1 WHERE "user"=$1;',
                ctx.author.id
            )

            await self.bot.pool.execute(
                'UPDATE profile SET bones = bones - 50 WHERE "user"=$1;',
                ctx.author.id
            )

            await self.bot.pool.execute(
                'UPDATE profile SET crates_rare = crates_rare + 1 WHERE "user"=$1;',
                ctx.author.id
            )
            await ctx.send("You have successfully purchased a <:F_rare:1139514880517484666> for 50 Bones!")

        if item == 3:
            if bones_count < 250:
                await ctx.send("You cannot afford this")
                return
            item1 = await self.bot.pool.fetchrow(
                'SELECT ssmagic FROM profile WHERE "user"=$1;',
                ctx.author.id
            )
            quantity = item1['ssmagic']
            if quantity <= 0:
                await ctx.send("You cannot purchase this: Sold Out!")
                return

            await self.bot.pool.execute(
                'UPDATE profile SET ssmagic = ssmagic - 1 WHERE "user"=$1;',
                ctx.author.id
            )

            await self.bot.pool.execute(
                'UPDATE profile SET bones = bones - 250 WHERE "user"=$1;',
                ctx.author.id
            )

            await self.bot.pool.execute(
                'UPDATE profile SET crates_magic = crates_magic + 1 WHERE "user"=$1;',
                ctx.author.id
            )
            await ctx.send("You have successfully purchased a <:F_Magic:1139514865174720532> for 500 Bones!")

        if item == 4:
            if bones_count < 1300:
                await ctx.send("You cannot afford this")
                return
            item1 = await self.bot.pool.fetchrow(
                'SELECT sslegendary FROM profile WHERE "user"=$1;',
                ctx.author.id
            )
            quantity = item1['sslegendary']
            if quantity <= 0:
                await ctx.send("You cannot purchase this: Sold Out!")
                return

            await self.bot.pool.execute(
                'UPDATE profile SET sslegendary = sslegendary - 1 WHERE "user"=$1;',
                ctx.author.id
            )

            await self.bot.pool.execute(
                'UPDATE profile SET bones = bones - 1300 WHERE "user"=$1;',
                ctx.author.id
            )

            await self.bot.pool.execute(
                'UPDATE profile SET crates_legendary = crates_legendary + 1 WHERE "user"=$1;',
                ctx.author.id
            )
            await ctx.send("You have successfully purchased a <:F_Legendary:1139514868400132116> for 1300 Bones!")




        if item == 5:
            if bones_count < 1750:
                await ctx.send("You cannot afford this")
                return
            item1 = await self.bot.pool.fetchrow(
                'SELECT ssfortune FROM profile WHERE "user"=$1;',
                ctx.author.id
            )
            quantity = item1['ssfortune']
            if quantity <= 0:
                await ctx.send("You cannot purchase this: Sold Out!")
                return

            await self.bot.pool.execute(
                'UPDATE profile SET ssfortune = ssfortune - 1 WHERE "user"=$1;',
                ctx.author.id
            )

            await self.bot.pool.execute(
                'UPDATE profile SET bones = bones - 1750 WHERE "user"=$1;',
                ctx.author.id
            )

            await self.bot.pool.execute(
                'UPDATE profile SET crates_fortune = crates_fortune + 1 WHERE "user"=$1;',
                ctx.author.id
            )
            await ctx.send("You have successfully purchased a <:f_money:1146593710516224090> for 1750 Bones!")




        if item == 6:
            if bones_count < 2900:
                await ctx.send("You cannot afford this")
                return
            item1 = await self.bot.pool.fetchrow(
                'SELECT ssdivine FROM profile WHERE "user"=$1;',
                ctx.author.id
            )
            quantity = item1['ssdivine']
            if quantity <= 0:
                await ctx.send("You cannot purchase this: Sold Out!")
                return

            await self.bot.pool.execute(
                'UPDATE profile SET ssdivine = ssdivine - 1 WHERE "user"=$1;',
                ctx.author.id
            )

            await self.bot.pool.execute(
                'UPDATE profile SET bones = bones - 2900 WHERE "user"=$1;',
                ctx.author.id
            )

            await self.bot.pool.execute(
                'UPDATE profile SET crates_divine= crates_divine + 1 WHERE "user"=$1;',
                ctx.author.id
            )
            await ctx.send("You have successfully purchased a <:f_divine:1169412814612471869>for 2900 Bones!")


        if item == 7:
            if bones_count < 650:
                await ctx.send("You cannot afford this")
                return
            item1 = await self.bot.pool.fetchrow(
                'SELECT ssbg FROM profile WHERE "user"=$1;',
                ctx.author.id
            )
            quantity = item1['ssbg']
            if quantity <= 0:
                await ctx.send("You cannot purchase this: Sold Out!")
                return

            await self.bot.pool.execute(
                'UPDATE profile SET ssbg = ssbg - 1 WHERE "user"=$1;',
                ctx.author.id
            )

            await self.bot.pool.execute(
                'UPDATE profile SET bones = bones - 650 WHERE "user"=$1;',
                ctx.author.id
            )

            await self.bot.pool.execute(
                'UPDATE profile SET ssbg1 = true WHERE "user"=$1;',
                ctx.author.id
            )

            backgrounds = [
                "https://i.ibb.co/FmwWpF4/ssbg.png",
            ]
            async with self.bot.pool.acquire() as conn:
                background = random.choice(backgrounds)
                current_backgrounds = await conn.fetchval(
                    'SELECT "backgrounds" FROM profile WHERE "user"=$1;', ctx.author.id
                )
                if current_backgrounds is None or background not in current_backgrounds:
                    await conn.execute(
                        'UPDATE profile SET "backgrounds"=array_append("backgrounds", $1) WHERE "user"=$2;',
                        background,
                        ctx.author.id,
                    )

            await ctx.send("You have successfully purchased a Seasonal Background for 650 Bones!")
            await ctx.send("You can find it in $eventbackgrounds")

        if item == 8:
            if bones_count < 1000:
                await ctx.send("You cannot afford this")
                return
            item1 = await self.bot.pool.fetchrow(
                'SELECT ssclass FROM profile WHERE "user"=$1;',
                ctx.author.id
            )
            quantity = item1['ssclass']
            if quantity <= 0:
                await ctx.send("You cannot purchase this: Sold Out!")
                return

            await self.bot.pool.execute(
                'UPDATE profile SET ssclass = ssclass - 1 WHERE "user"=$1;',
                ctx.author.id
            )

            await self.bot.pool.execute(
                'UPDATE profile SET bones = bones - 1000 WHERE "user"=$1;',
                ctx.author.id
            )

            await self.bot.pool.execute(
                'UPDATE profile SET spookyclass = true WHERE "user"=$1;',
                ctx.author.id
            )
            await ctx.send("You have successfully purchased the Seasonal Class for 1000 Bones!")
            await ctx.send("You can find it in $class")

        if item == 9:
            if bones_count < 200:
                await ctx.send("You cannot afford this")
                return
            item1 = await self.bot.pool.fetchrow(
                'SELECT sstoken FROM profile WHERE "user"=$1;',
                ctx.author.id
            )
            quantity = item1['sstoken']
            if quantity <= 0:
                await ctx.send("You cannot purchase this: Sold Out!")
                return

            await self.bot.pool.execute(
                'UPDATE profile SET sstoken = sstoken - 1 WHERE "user"=$1;',
                ctx.author.id
            )

            await self.bot.pool.execute(
                'UPDATE profile SET bones = bones - 200 WHERE "user"=$1;',
                ctx.author.id
            )

            await self.bot.pool.execute(
                'UPDATE profile SET weapontoken = weapontoken + 1 WHERE "user"=$1;',
                ctx.author.id
            )
            await ctx.send("You have successfully purchased a Weapon Type token for 200 Bones!")

        if item == 10:
            if bones_count < 200:
                await ctx.send("You cannot afford this")
                return
            item1 = await self.bot.pool.fetchrow(
                'SELECT sstot FROM profile WHERE "user"=$1;',
                ctx.author.id
            )
            quantity = item1['sstot']
            if quantity <= 0:
                await ctx.send("You cannot purchase this: Sold Out!")
                return

            await self.bot.pool.execute(
                'UPDATE profile SET sstot = sstot - 1 WHERE "user"=$1;',
                ctx.author.id
            )

            await self.bot.pool.execute(
                'UPDATE profile SET bones = bones - 200 WHERE "user"=$1;',
                ctx.author.id
            )

            await self.bot.pool.execute(
                'UPDATE profile SET trickortreat = trickortreat + 3 WHERE "user"=$1;',
                ctx.author.id
            )
            await ctx.send("You have successfully purchased 3 Trick or Treat bags for 200 Bones!")

    async def get_bone_count(self, user_id):
        """Get the user's bone count from the database."""
        record = await self.bot.pool.fetchrow(
            'SELECT bones FROM profile WHERE "user"=$1;',
            user_id
        )
        if record:
            return record['bones']
        return 0

    @spookyshop.command(name="bal")
    async def _bal(self, ctx):

        if not await self._ensure_event_enabled(ctx):
            return

        record = await self.bot.pool.fetchrow(
            'SELECT bones FROM profile WHERE "user"=$1;',
            ctx.author.id
        )
        if record:
            bones_count = record['bones']
        else:
            bones_count = 0

        await ctx.send(f"You currently have **{bones_count}** Bones, {ctx.author.mention}!")

    @checks.has_char()
    @commands.command(brief=_("Open a trick or treat bag"))
    @locale_doc
    async def yummy(self, ctx):
        _(
            """Open a trick or treat bag, you can get some with `{prefix}trickortreat`.

            Trick or treat bags contain halloween-themed items, ranging from 1 to 50 base stat.
            Their value will be between 1 and 200."""
        )
        if not await self._ensure_event_enabled(ctx):
            return

        # better name?
        if ctx.character_data["trickortreat"] < 1:
            return await ctx.send(
                _("Seems you haven't got a trick or treat bag yet. Go get some!")
            )
        mytry = random.randint(1, 100)
        if mytry == 1:
            minstat, maxstat = 55, 75
        elif mytry < 10:
            minstat, maxstat = 42, 55
        elif mytry < 30:
            minstat, maxstat = 38, 42
        elif mytry < 50:
            minstat, maxstat = 25, 38
        else:
            minstat, maxstat = 10, 25
        item = await self.bot.create_random_item(
            minstat=minstat,
            maxstat=maxstat,
            minvalue=1,
            maxvalue=200,
            owner=ctx.author,
            insert=False,
        )
        name = random.choice(
            [
                "Jack's",
                "Spooky",
                "Ghostly",
                "Skeletal",
                "Glowing",
                "Moonlight",
                "Greg's really awesome",
                "Ghost Buster's",
                "Ghoulish",
                "Vampiric",
                "Living",
                "Undead",
                "Glooming",
                "Witching",
                "Haunted",
                "Mystical",
                "Eerie",
                "Shadowy",
                "Graveyard",
                "Midnight",
                "Cursed",
                "Phantom",
                "Cobwebbed",
                "Hallowed",
                "Mournful",
                "Wicked",
                "Foggy",
                "Cryptic",
                "Petrifying",
                "Twilight",
                "Dreadful",
                "Bat's",
                "Zombie's",
                "Lurking",
                "Banshee's",
                "Ominous",
                "Spectral",
                "Webbed",
                "Lycanthropic",
                "Decaying",
                "Silent",
                "Darkness",
                "Bloodmoon",
                "Chilling",
                "Shrieking",
                "Possessed",
                "Enchanted",
                "Deathly",
                "Nocturnal",
                "Ritualistic",
                "Howling",
                "Black Cat's"
            ]
        )

        item["name"] = f"{name} {item['type_']}"
        async with self.bot.pool.acquire() as conn:
            await self.bot.create_item(**item, conn=conn)
            await conn.execute(
                'UPDATE profile SET "trickortreat"="trickortreat"-1 WHERE "user"=$1;',
                ctx.author.id,
            )
        embed = discord.Embed(
            title=_("You gained an item!"),
            description=_("You found a new item when opening a trick-or-treat bag!"),
            color=self.bot.config.game.primary_colour,
        )
        embed.add_field(name=_("Name"), value=item["name"], inline=False)
        embed.add_field(name=_("Element"), value=item["element"], inline=False)
        embed.add_field(name=_("Type"), value=item["type_"], inline=False)
        embed.add_field(name=_("Damage"), value=item["damage"], inline=True)
        embed.add_field(name=_("Armor"), value=item["armor"], inline=True)
        embed.add_field(name=_("Value"), value=f"${item['value']}", inline=False)
        embed.set_footer(
            text=_("Remaining trick-or-treat bags: {bags}").format(
                bags=ctx.character_data["trickortreat"] - 1
            )
        )
        await ctx.send(embed=embed)

    @checks.has_char()
    @commands.command(
        aliases=["totbags", "halloweenbags"], brief=_("Shows your trick or treat bags")
    )
    @locale_doc
    async def bags(self, ctx):
        _(
            """Shows the amount of trick or treat bags you have. You can get more by using `{prefix}trickortreat`."""
        )
        if not await self._ensure_event_enabled(ctx):
            return
        await ctx.send(
            _(
                "You currently have **{trickortreat}** Trick or Treat Bags, {author}!"
            ).format(
                trickortreat=ctx.character_data["trickortreat"],
                author=ctx.author.mention,
            )
        )


async def setup(bot):
    await bot.add_cog(Halloween(bot))
