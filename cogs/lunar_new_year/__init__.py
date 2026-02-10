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


class LunarNewYear(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.enabled = False  # Controlled by GM event settings

    def is_enabled(self) -> bool:
        event_flags = getattr(self.bot, "event_flags", None)
        if event_flags is None:
            return bool(self.enabled)
        return bool(event_flags.get("lunar_new_year", self.enabled))

    async def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        event_flags = getattr(self.bot, "event_flags", None)
        if event_flags is not None:
            event_flags["lunar_new_year"] = enabled
        gm_cog = self.bot.get_cog("GameMaster")
        if gm_cog and hasattr(gm_cog, "set_event_enabled"):
            await gm_cog.set_event_enabled("lunar_new_year", enabled)

    @commands.Cog.listener()
    async def on_adventure_completion(self, ctx, iscompleted):
        """
        Listens for adventure completion events and awards lanterns (currency)
        when adventures are completed.
        """
        if not self.is_enabled():
            return

        if not iscompleted:
            return

        lanterns = 0
        try:
            # Get adventure number - try multiple methods
            num = None
            
            # Try to get from ctx.adventure_data (tuple: adventure_number, time, done)
            try:
                if hasattr(ctx, 'adventure_data') and ctx.adventure_data:
                    adventure_tuple = ctx.adventure_data
                    if isinstance(adventure_tuple, (tuple, list)) and len(adventure_tuple) >= 1:
                        num = adventure_tuple[0]
            except (AttributeError, TypeError, IndexError):
                pass  # adventure_data not available or not in expected format
            
            # Fallback: try to get from character data
            if not num or num < 1:
                try:
                    num = ctx.character_data.get("adventure", None)
                except (AttributeError, TypeError):
                    num = None
            
            # Final fallback: use level as approximation
            if not num or num < 1:
                try:
                    import utils.misc as rpgtools
                    level = int(rpgtools.xptolevel(ctx.character_data.get("xp", 0)))
                    num = max(1, min(level, 100))
                except (AttributeError, TypeError, ValueError):
                    num = 1  # Default to level 1 if all else fails
            
            # Ensure num is valid
            try:
                num = max(1, min(int(num) if num else 1, 100))  # Cap at 100 for safety
            except (ValueError, TypeError):
                num = 1
            
            # Calculate lanterns with better scaling (1.5x multiplier):
            # Base formula: (adventure_level * multiplier) + random bonus
            # Level 1: ~7-9 lanterns (7-8 base + random 0-1)
            # Level 10: ~75-90 lanterns (75 base + random 0-15)
            # Level 50: ~375-450 lanterns (375 base + random 0-75)
            # Level 100: ~750-900 lanterns (750 base + random 0-150)
            
            # Base lanterns: adventure_level * 7.5 (1.5x of original 5x)
            base_lanterns = int(num * 7.5)
            
            # Random bonus: increases with level (1.5x of original)
            # Bonus range scales from 0 to (num * 1.5), capped at 150
            bonus_range = min(num * 1.5, 150)  # Cap bonus at 150
            random_bonus = random.randint(0, int(bonus_range))
            
            lanterns = base_lanterns + random_bonus
            
            # Ensure minimum of 4 lanterns even for level 1 adventures (1.5x of 3)
            if lanterns < 4:
                lanterns = 4
            
            # Update lanterns in database
            if lanterns > 0:
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        'UPDATE profile SET "lunar_lanterns"=COALESCE("lunar_lanterns", 0)+$1 WHERE "user"=$2;',
                        lanterns,
                        ctx.author.id,
                    )
                
        except Exception as e:
            # Log error but don't break adventure completion
            try:
                self.bot.logger.error(f"Error calculating/awarding lunar lanterns: {e}")
                import traceback
                self.bot.logger.error(traceback.format_exc())
            except:
                print(f"Error calculating/awarding lunar lanterns: {e}")
                import traceback
                print(traceback.format_exc())
            # If error occurred, don't send message (lanterns is still 0)
            lanterns = 0
        
        # Send a message about earning lanterns (outside main try block to ensure it runs)
        # Only send if we successfully calculated lanterns
        if lanterns > 0:
            try:
                # Try ctx.send first (this is what was working before)
                await ctx.send(
                    _("🏮 You earned **{lanterns}** Lunar Lanterns from completing your adventure!").format(
                        lanterns=lanterns
                    )
                )
            except (discord.Forbidden, discord.HTTPException, AttributeError):
                # If ctx.send fails, try channel.send as fallback
                try:
                    if hasattr(ctx, 'channel') and ctx.channel:
                        await ctx.channel.send(
                            _("🏮 You earned **{lanterns}** Lunar Lanterns from completing your adventure!").format(
                                lanterns=lanterns
                            )
                        )
                except Exception:
                    # Silently fail if we can't send the message
                    pass

    @checks.has_char()
    @commands.group(aliases=["lunar", "lunarshop"], brief=_("Opens Lunar New Year Shop"))
    @locale_doc
    async def lunarnewyear(self, ctx):
        """
        Welcome to the Lunar New Year Celebration Shop!
        Spend your hard-earned Lunar Lanterns on festive treasures and rewards.
        """

        if not self.is_enabled():
            await ctx.send(_("The Lunar New Year event is currently disabled."))
            return

        try:
            if ctx.invoked_subcommand is None:
                # Fetch shop quantities for user
                shop_data = await self.bot.pool.fetchrow(
                    '''
                    SELECT lnyuncommon, lnyrare, lnymagic, lnylegendary, lnyfortune, lnydivine, 
                           lnytoken, lnybag
                    FROM profile WHERE "user"=$1;
                    ''',
                    ctx.author.id
                )

                if not shop_data:
                    await ctx.send(_("Unable to load shop data. Please try again later."))
                    return

                lnyuncommon_value = shop_data.get('lnyuncommon', 0)
                lnyrare_value = shop_data.get('lnyrare', 0)
                lnymagic_value = shop_data.get('lnymagic', 0)
                lnylegendary_value = shop_data.get('lnylegendary', 0)
                lnyfortune_value = shop_data.get('lnyfortune', 0)
                lnydivine_value = shop_data.get('lnydivine', 0)
                lnytoken_value = shop_data.get('lnytoken', 0)
                lnybag_value = shop_data.get('lnybag', 0)

                # Fetch the user's lantern count
                lantern_count = await self.get_lantern_count(ctx.author.id)

                # Create the embed with Lunar New Year theme
                embed = Embed(title=_("🏮 Lunar New Year Shop 🏮"), color=0xFFD700)  # Gold color

                embed.set_thumbnail(url="https://i.ibb.co/NHTgkxG/Shop-LNY.jpg")  # Lunar New Year shop image
                embed.set_author(name=ctx.author.display_name)

                items = [
                    ("<:c_uncommon:1405232629049196686> Uncommon Crate", 30, lnyuncommon_value),
                    ("<:c_rare:1405232627119820964> Rare Crate", 60, lnyrare_value),
                    ("<:c_Magic:1403797589169541330> Magic Crate", 250, lnymagic_value),
                    ("<:c_Legendary:1403797587236225044> Legendary Crate", 1300, lnylegendary_value),
                    ("<:c_money:1403797585411575971> Fortune Crate", 1750, lnyfortune_value),
                    ("<:c_divine:1405232615258198150> Divine Crate", 2900, lnydivine_value),
                    ("🟡 Weapon Type Token", 200, lnytoken_value),
                    ("🎁 3 Lunar New Year Bags", 200, lnybag_value)
                ]

                for idx, (name, cost, quantity) in enumerate(items, 1):
                    embed.add_field(
                        name=f"{idx}:  {name}",
                        value=_("Cost: {} Lanterns - {} available").format(cost, quantity),
                        inline=False
                    )

                embed.set_footer(
                    text=_("You have {} Lanterns 🏮 - $lunar buy <ID> to buy.").format(lantern_count),
                    icon_url="https://ibb.co/NHTgkxG"
                )

                await ctx.send(embed=embed)

        except Exception as e:
            error_embed = Embed(
                title=_("🚫 An error occurred!"),
                description=_("Oh no! Something went wrong. Try again later or contact support. {error}").format(error=str(e)),
                color=0xff0000
            )
            await ctx.send(embed=error_embed)

    @lunarnewyear.command(name="buy")
    @user_cooldown(30)
    async def _buy(self, ctx, item: int, quantity: int = 1):
        _("""
        This subcommand allows the user to buy an item from the Lunar New Year Shop.

        :param item: The ID of the item the user wants to buy (1-8).
        :param quantity: The quantity of the item the user wants to buy. Defaults to 1.
        """)

        if not self.is_enabled():
            await ctx.send(_("The Lunar New Year event is currently disabled."))
            return

        if item < 1 or item > 8:
            await ctx.send(_("Invalid choice. Please select an item ID between 1 and 8."))
            return

        record = await self.bot.pool.fetchrow(
            'SELECT lunar_lanterns FROM profile WHERE "user"=$1;',
            ctx.author.id
        )
        if record:
            lanterns_count = record.get('lunar_lanterns', 0) or 0
        else:
            lanterns_count = 0

        # Item 1: Uncommon Crate
        if item == 1:
            if lanterns_count < 30:
                await ctx.send(_("You cannot afford this. You need 30 Lanterns."))
                return
            item_data = await self.bot.pool.fetchrow(
                'SELECT lnyuncommon FROM profile WHERE "user"=$1;',
                ctx.author.id
            )
            available = item_data.get('lnyuncommon', 0) if item_data else 0
            if available <= 0:
                await ctx.send(_("You cannot purchase this: Sold Out!"))
                return

            await self.bot.pool.execute(
                'UPDATE profile SET lnyuncommon = lnyuncommon - 1 WHERE "user"=$1;',
                ctx.author.id
            )
            await self.bot.pool.execute(
                'UPDATE profile SET lunar_lanterns = COALESCE(lunar_lanterns, 0) - 30 WHERE "user"=$1;',
                ctx.author.id
            )
            await self.bot.pool.execute(
                'UPDATE profile SET crates_uncommon = crates_uncommon + 1 WHERE "user"=$1;',
                ctx.author.id
            )
            await ctx.send(_("You have successfully purchased a <:F_uncommon:1139514875828252702> for 30 Lanterns!"))

        # Item 2: Rare Crate
        elif item == 2:
            if lanterns_count < 60:
                await ctx.send(_("You cannot afford this. You need 60 Lanterns."))
                return
            item_data = await self.bot.pool.fetchrow(
                'SELECT lnyrare FROM profile WHERE "user"=$1;',
                ctx.author.id
            )
            available = item_data.get('lnyrare', 0) if item_data else 0
            if available <= 0:
                await ctx.send(_("You cannot purchase this: Sold Out!"))
                return

            await self.bot.pool.execute(
                'UPDATE profile SET lnyrare = lnyrare - 1 WHERE "user"=$1;',
                ctx.author.id
            )
            await self.bot.pool.execute(
                'UPDATE profile SET lunar_lanterns = COALESCE(lunar_lanterns, 0) - 60 WHERE "user"=$1;',
                ctx.author.id
            )
            await self.bot.pool.execute(
                'UPDATE profile SET crates_rare = crates_rare + 1 WHERE "user"=$1;',
                ctx.author.id
            )
            await ctx.send(_("You have successfully purchased a <:F_rare:1139514880517484666> for 60 Lanterns!"))

        # Item 3: Magic Crate
        elif item == 3:
            if lanterns_count < 250:
                await ctx.send(_("You cannot afford this. You need 250 Lanterns."))
                return
            item_data = await self.bot.pool.fetchrow(
                'SELECT lnymagic FROM profile WHERE "user"=$1;',
                ctx.author.id
            )
            available = item_data.get('lnymagic', 0) if item_data else 0
            if available <= 0:
                await ctx.send(_("You cannot purchase this: Sold Out!"))
                return

            await self.bot.pool.execute(
                'UPDATE profile SET lnymagic = lnymagic - 1 WHERE "user"=$1;',
                ctx.author.id
            )
            await self.bot.pool.execute(
                'UPDATE profile SET lunar_lanterns = COALESCE(lunar_lanterns, 0) - 250 WHERE "user"=$1;',
                ctx.author.id
            )
            await self.bot.pool.execute(
                'UPDATE profile SET crates_magic = crates_magic + 1 WHERE "user"=$1;',
                ctx.author.id
            )
            await ctx.send(_("You have successfully purchased a <:F_Magic:1139514865174720532> for 250 Lanterns!"))

        # Item 4: Legendary Crate
        elif item == 4:
            if lanterns_count < 1300:
                await ctx.send(_("You cannot afford this. You need 1300 Lanterns."))
                return
            item_data = await self.bot.pool.fetchrow(
                'SELECT lnylegendary FROM profile WHERE "user"=$1;',
                ctx.author.id
            )
            available = item_data.get('lnylegendary', 0) if item_data else 0
            if available <= 0:
                await ctx.send(_("You cannot purchase this: Sold Out!"))
                return

            await self.bot.pool.execute(
                'UPDATE profile SET lnylegendary = lnylegendary - 1 WHERE "user"=$1;',
                ctx.author.id
            )
            await self.bot.pool.execute(
                'UPDATE profile SET lunar_lanterns = COALESCE(lunar_lanterns, 0) - 1300 WHERE "user"=$1;',
                ctx.author.id
            )
            await self.bot.pool.execute(
                'UPDATE profile SET crates_legendary = crates_legendary + 1 WHERE "user"=$1;',
                ctx.author.id
            )
            await ctx.send(_("You have successfully purchased a <:F_Legendary:1139514868400132116> for 1300 Lanterns!"))

        # Item 5: Fortune Crate
        elif item == 5:
            if lanterns_count < 1750:
                await ctx.send(_("You cannot afford this. You need 1750 Lanterns."))
                return
            item_data = await self.bot.pool.fetchrow(
                'SELECT lnyfortune FROM profile WHERE "user"=$1;',
                ctx.author.id
            )
            available = item_data.get('lnyfortune', 0) if item_data else 0
            if available <= 0:
                await ctx.send(_("You cannot purchase this: Sold Out!"))
                return

            await self.bot.pool.execute(
                'UPDATE profile SET lnyfortune = lnyfortune - 1 WHERE "user"=$1;',
                ctx.author.id
            )
            await self.bot.pool.execute(
                'UPDATE profile SET lunar_lanterns = COALESCE(lunar_lanterns, 0) - 1750 WHERE "user"=$1;',
                ctx.author.id
            )
            await self.bot.pool.execute(
                'UPDATE profile SET crates_fortune = crates_fortune + 1 WHERE "user"=$1;',
                ctx.author.id
            )
            await ctx.send(_("You have successfully purchased a <:f_money:1146593710516224090> for 1750 Lanterns!"))

        # Item 6: Divine Crate
        elif item == 6:
            if lanterns_count < 2900:
                await ctx.send(_("You cannot afford this. You need 2900 Lanterns."))
                return
            item_data = await self.bot.pool.fetchrow(
                'SELECT lnydivine FROM profile WHERE "user"=$1;',
                ctx.author.id
            )
            available = item_data.get('lnydivine', 0) if item_data else 0
            if available <= 0:
                await ctx.send(_("You cannot purchase this: Sold Out!"))
                return

            await self.bot.pool.execute(
                'UPDATE profile SET lnydivine = lnydivine - 1 WHERE "user"=$1;',
                ctx.author.id
            )
            await self.bot.pool.execute(
                'UPDATE profile SET lunar_lanterns = COALESCE(lunar_lanterns, 0) - 2900 WHERE "user"=$1;',
                ctx.author.id
            )
            await self.bot.pool.execute(
                'UPDATE profile SET crates_divine = crates_divine + 1 WHERE "user"=$1;',
                ctx.author.id
            )
            await ctx.send(_("You have successfully purchased a <:f_divine:1169412814612471869> for 2900 Lanterns!"))

        # Item 7: Weapon Type Token
        elif item == 7:
            if lanterns_count < 200:
                await ctx.send(_("You cannot afford this. You need 200 Lanterns."))
                return
            item_data = await self.bot.pool.fetchrow(
                'SELECT lnytoken FROM profile WHERE "user"=$1;',
                ctx.author.id
            )
            available = item_data.get('lnytoken', 0) if item_data else 0
            if available <= 0:
                await ctx.send(_("You cannot purchase this: Sold Out!"))
                return

            await self.bot.pool.execute(
                'UPDATE profile SET lnytoken = lnytoken - 1 WHERE "user"=$1;',
                ctx.author.id
            )
            await self.bot.pool.execute(
                'UPDATE profile SET lunar_lanterns = COALESCE(lunar_lanterns, 0) - 200 WHERE "user"=$1;',
                ctx.author.id
            )
            await self.bot.pool.execute(
                'UPDATE profile SET weapontoken = weapontoken + 1 WHERE "user"=$1;',
                ctx.author.id
            )
            await ctx.send(_("You have successfully purchased a Weapon Type token for 200 Lanterns!"))

        # Item 8: Lunar New Year Bags
        elif item == 8:
            if lanterns_count < 200:
                await ctx.send(_("You cannot afford this. You need 200 Lanterns."))
                return
            item_data = await self.bot.pool.fetchrow(
                'SELECT lnybag FROM profile WHERE "user"=$1;',
                ctx.author.id
            )
            available = item_data.get('lnybag', 0) if item_data else 0
            if available <= 0:
                await ctx.send(_("You cannot purchase this: Sold Out!"))
                return

            await self.bot.pool.execute(
                'UPDATE profile SET lnybag = lnybag - 1 WHERE "user"=$1;',
                ctx.author.id
            )
            await self.bot.pool.execute(
                'UPDATE profile SET lunar_lanterns = COALESCE(lunar_lanterns, 0) - 200 WHERE "user"=$1;',
                ctx.author.id
            )
            await self.bot.pool.execute(
                'UPDATE profile SET lunar_bags = COALESCE(lunar_bags, 0) + 3 WHERE "user"=$1;',
                ctx.author.id
            )
            await ctx.send(_("You have successfully purchased 3 Lunar New Year bags for 200 Lanterns!"))

    async def get_lantern_count(self, user_id):
        """Get the user's lantern count from the database."""
        record = await self.bot.pool.fetchrow(
            'SELECT lunar_lanterns FROM profile WHERE "user"=$1;',
            user_id
        )
        if record:
            return record.get('lunar_lanterns', 0) or 0
        return 0

    @lunarnewyear.command(name="bal", aliases=["balance"])
    async def _bal(self, ctx):
        """Check your Lunar Lantern balance."""
        if not self.is_enabled():
            await ctx.send(_("The Lunar New Year event is currently disabled."))
            return

        record = await self.bot.pool.fetchrow(
            'SELECT lunar_lanterns FROM profile WHERE "user"=$1;',
            ctx.author.id
        )
        if record:
            lanterns_count = record.get('lunar_lanterns', 0) or 0
        else:
            lanterns_count = 0

        await ctx.send(_("You currently have **{lanterns}** Lunar Lanterns, {author}! 🏮").format(
            lanterns=lanterns_count,
            author=ctx.author.mention
        ))

    @checks.has_char()
    @commands.command(name="openlunar", aliases=["lunaropenbag", "lunaropen"], brief=_("Open a Lunar New Year bag"))
    @locale_doc
    async def openlunar(self, ctx):
        _(
            """Open a Lunar New Year bag, you can get some from the shop or special events.

            Lunar New Year bags contain festive-themed items, ranging from 1 to 50 base stat.
            Their value will be between 1 and 200."""
        )
        
        if not self.is_enabled():
            await ctx.send(_("The Lunar New Year event is currently disabled."))
            return

        # Check if user has lunar_bags column, fallback to checking if they have any
        bag_count = await self.bot.pool.fetchval(
            'SELECT COALESCE(lunar_bags, 0) FROM profile WHERE "user"=$1;',
            ctx.author.id
        ) or 0

        if bag_count < 1:
            return await ctx.send(
                _("Seems you haven't got a Lunar New Year bag yet. Visit the shop to get some!")
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
                "Dragon's",
                "Lunar",
                "Festive",
                "Prosperous",
                "Golden",
                "Jade",
                "Crimson",
                "Auspicious",
                "Blessed",
                "Harmonious",
                "Radiant",
                "Celestial",
                "Imperial",
                "Majestic",
                "Tranquil",
                "Eternal",
                "Sacred",
                "Divine",
                "Enchanted",
                "Mystical",
                "Serene",
                "Brilliant",
                "Glorious",
                "Magnificent",
                "Regal",
                "Splendid",
                "Venerable",
                "Ancient",
                "Legendary",
                "Timeless",
                "Zenith",
                "Peak",
                "Summit",
                "Crown",
                "Phoenix",
                "Tiger's",
                "Rabbit's",
                "Snake's",
                "Horse's",
                "Goat's",
                "Monkey's",
                "Rooster's",
                "Dog's",
                "Pig's",
                "Rat's",
                "Ox's",
            ]
        )

        item["name"] = f"{name} {item['type_']}"
        async with self.bot.pool.acquire() as conn:
            await self.bot.create_item(**item, conn=conn)
            await conn.execute(
                'UPDATE profile SET "lunar_bags"=COALESCE("lunar_bags", 0)-1 WHERE "user"=$1;',
                ctx.author.id,
            )

        embed = discord.Embed(
            title=_("You gained an item!"),
            description=_("You found a new item when opening a Lunar New Year bag!"),
            color=self.bot.config.game.primary_colour,
        )
        embed.add_field(name=_("Name"), value=item["name"], inline=False)
        embed.add_field(name=_("Element"), value=item["element"], inline=False)
        embed.add_field(name=_("Type"), value=item["type_"], inline=False)
        embed.add_field(name=_("Damage"), value=item["damage"], inline=True)
        embed.add_field(name=_("Armor"), value=item["armor"], inline=True)
        embed.add_field(name=_("Value"), value=f"${item['value']}", inline=False)
        embed.set_footer(
            text=_("Remaining Lunar New Year bags: {bags}").format(
                bags=bag_count - 1
            )
        )
        await ctx.send(embed=embed)

    @checks.has_char()
    @commands.command(
        name="lunarbagcount",
        aliases=["lnybagcount"], brief=_("Shows your Lunar New Year bags")
    )
    @locale_doc
    async def lunarbagcount(self, ctx):
        _(
            """Shows the amount of Lunar New Year bags you have. You can get more from the shop."""
        )
        
        if not self.is_enabled():
            await ctx.send(_("The Lunar New Year event is currently disabled."))
            return

        bag_count = await self.bot.pool.fetchval(
            'SELECT COALESCE(lunar_bags, 0) FROM profile WHERE "user"=$1;',
            ctx.author.id
        ) or 0

        await ctx.send(
            _(
                "You currently have **{bags}** Lunar New Year Bags, {author}! 🏮"
            ).format(
                bags=bag_count,
                author=ctx.author.mention,
            )
        )

    @checks.is_gm()
    @commands.command(name="lnyenable", brief=_("Enable/disable Lunar New Year event"))
    async def toggle_event(self, ctx, enabled: bool = None):
        """Toggle the Lunar New Year event on or off."""
        if enabled is None:
            enabled = not self.is_enabled()
        await self.set_enabled(enabled)
        status = "enabled" if enabled else "disabled"
        await ctx.send(_("Lunar New Year event is now **{status}**.").format(status=status))


async def setup(bot):
    await bot.add_cog(LunarNewYear(bot))
