import json
import traceback

import discord
from discord.ext import commands, tasks
import random
import asyncio
import datetime
import discord
from discord.ui import Button, View
from typing import Optional

from cogs.shard_communication import user_on_cooldown, next_day_cooldown
from utils.checks import has_char, is_gm
from utils.i18n import _, locale_doc


def user_has_gifted_today():
    async def predicate(ctx):
        async with ctx.bot.pool.acquire() as conn:
            # Check if user has gifted today
            last_gift = await conn.fetchrow("""
                SELECT * FROM gift_history 
                WHERE user_id = $1 
                AND timestamp > (
                    CASE 
                        WHEN CURRENT_TIME >= TIME '12:00:00'
                        THEN CURRENT_DATE + TIME '12:00:00'
                        ELSE CURRENT_DATE + TIME '12:00:00' - INTERVAL '1 day'
                    END
                )
            """, ctx.author.id)

            if last_gift:
                # Calculate time until next distribution
                now = datetime.datetime.utcnow()  # Explicitly use datetime.datetime.utcnow()
                next_distribution = datetime.datetime.combine(
                    now.date() if now.hour < 12 else now.date() + datetime.timedelta(days=1),
                    datetime.time(hour=12)
                )
                time_until = next_distribution - now
                hours = time_until.seconds // 3600
                minutes = (time_until.seconds % 3600) // 60

                # Instead of sending a message and returning False, raise an error with a custom message
                raise commands.CheckFailure(
                    f"You've already sent a gift today! Next gift in {hours} hours and {minutes} minutes (12 PM UTC)!"
                )

            return True

    return commands.check(predicate)


class GiftForward(commands.Cog):
    """A sophisticated gift forwarding system for the community!"""



    CRATE_VALUES = {
        "common": 700,
        "uncommon": 1200,
        "rare": 3000,
        "mystery": 2000,
        "magic": 30000,
        "legendary": 300000,
        "fortune": 1000000,
        "divine": 3500000
    }

    GIFT_TIERS = {
        "beginner": {
            "range": (1_000, 9_999),
            "color": discord.Color.light_grey(),
            "icon": "🎋",
            "title": "Beginner Gift",
            "patterns": ["classic", "garden"]
        },
        "starter": {
            "range": (10_000, 49_999),
            "color": discord.Color.greyple(),
            "icon": "🎀",
            "title": "Starter Gift",
            "patterns": ["classic", "candy", "kawaii"]
        },
        "amateur": {
            "range": (50_000, 99_999),
            "color": discord.Color.dark_grey(),
            "icon": "🎭",
            "title": "Amateur Gift",
            "patterns": ["classic", "starry", "cat"]
        },
        "novice": {
            "range": (100_000, 499_999),
            "color": discord.Color.green(),
            "icon": "🎁",
            "title": "Novice Gift",
            "patterns": ["classic", "garden", "candy"]
        },
        "nice": {
            "range": (500_000, 1_000_000),
            "color": discord.Color.blue(),
            "icon": "🎄",
            "title": "Generous Gift",
            "patterns": ["starry", "magic", "rainbow", "cloud"]
        },
        "generous": {
            "range": (1_000_001, 2_000_000),
            "color": discord.Color.blue(),
            "icon": "🎀",
            "title": "Generous Gift",
            "patterns": ["starry", "magic", "rainbow", "cloud"]
        },
        "magnificent": {
            "range": (2_000_001, 5_000_000),
            "color": discord.Color.purple(),
            "icon": "👑",
            "title": "Magnificent Gift",
            "patterns": ["royal", "dragon", "space", "moon"]
        },
        "legendary": {
            "range": (5_000_001, float('inf')),
            "color": discord.Color.gold(),
            "icon": "🌟",
            "title": "Legendary Gift",
            "patterns": ["legendary", "divine", "pixel", "magic"]
        }
    }

    WRAP_PATTERNS = {
        "classic": {
            "title": "🎁 A Gift Has Arrived!",
            "color": discord.Color.gold(),
            "border": "・゜・。。・゜゜・。。・゜",
            "emojis": ["🎁", "✨"]
        },
        "starry": {
            "title": "⭐ A Starlit Gift Appears! ⭐",
            "color": discord.Color.blue(),
            "border": "｡･:*:･ﾟ★,｡･:*:･ﾟ☆",
            "emojis": ["⭐", "✨", "💫"]
        },
        "kawaii": {
            "title": "🌸 Kawaii Gift Desu! 🌸",
            "color": discord.Color.fuchsia(),
            "border": "ᓚᘏᗢ★ᓚᘏᗢ★ᓚᘏᗢ",
            "emojis": ["🌸", "✿", "💮"]
        },
        "cat": {
            "title": "😺 Nya! A Gift For You! 😺",
            "color": discord.Color.orange(),
            "border": "ฅ^•ﻌ•^ฅ♥ฅ^•ﻌ•^ฅ",
            "emojis": ["😺", "🐱", "🐾"]
        },
        "space": {
            "title": "🚀 Intergalactic Gift Incoming! 🛸",
            "color": discord.Color.dark_blue(),
            "border": "🌠·˚✧₊⁎⁺˳✧༚·˚✧₊",
            "emojis": ["🚀", "👾", "🛸"]
        },
        "garden": {
            "title": "🌺 A Blooming Gift! 🌺",
            "color": discord.Color.green(),
            "border": "❀❁❀❁❀❁❀❁",
            "emojis": ["🌺", "🌸", "🌷"]
        },
        "candy": {
            "title": "🍬 Sweet Surprise! 🍭",
            "color": discord.Color.magenta(),
            "border": "🍬｡˚🍭｡˚🍬｡˚🍭",
            "emojis": ["🍬", "🍭", "🍡"]
        },
        "dragon": {
            "title": "🐲 Dragon's Treasure! 🐉",
            "color": discord.Color.dark_gold(),
            "border": "∴≋∴≋∴≋∴≋∴≋∴≋",
            "emojis": ["🐲", "🐉", "💎"]
        }
    }

    def __init__(self, bot):
        self.bot = bot
        self.min_donation = 1000
        self.gift_distribution_task.start()  # Start the daily task

    async def distribute_gift_by_tier(self, conn, gift):
        tier = gift['tier']
        log_channel = self.bot.get_channel(1313482408242184213)

        # Find users who have given gifts in this tier but haven't received equal number back
        potential_recipients = await conn.fetch("""
            SELECT 
                gh.user_id,
                (SELECT COUNT(*) FROM gift_history WHERE user_id = gh.user_id AND tier = $1) as gifts_given,
                (SELECT COUNT(*) FROM gift_history WHERE claimed_by = gh.user_id AND tier = $1) as gifts_received
            FROM gift_history gh
            WHERE gh.tier = $1  -- Same tier
            AND gh.user_id != $2  -- Not the gift donor
            GROUP BY gh.user_id
            HAVING (SELECT COUNT(*) FROM gift_history WHERE user_id = gh.user_id AND tier = $1) >
                   (SELECT COUNT(*) FROM gift_history WHERE claimed_by = gh.user_id AND tier = $1)
        """, tier, gift['user_id'])

        await log_channel.send(f"Gift {gift['id']} ({tier} tier)\nPotential Recipients:")
        for user in potential_recipients:
            await log_channel.send(
                f"User {user['user_id']}: Given {user['gifts_given']}, Received {user['gifts_received']}")

        if not potential_recipients:
            await log_channel.send(f"❌ No eligible recipients for {tier} tier gift {gift['id']}")
            return False

        # Select random recipient
        chosen_recipient = random.choice(potential_recipients)
        recipient_id = chosen_recipient['user_id']

        await log_channel.send(f"✅ Selected recipient {recipient_id}")
        await log_channel.send(f"- Given: {chosen_recipient['gifts_given']}")
        await log_channel.send(f"- Received: {chosen_recipient['gifts_received']}")

        try:
            # Process gift transfer
            await self.process_gift_transfer(conn, gift, recipient_id)
            await log_channel.send(f"✅ Transferred {tier} tier gift {gift['id']} to {recipient_id}")

            # Send notification
            recipient = self.bot.get_user(recipient_id)
            if recipient:
                await self.send_patterned_gift_notification(recipient, gift)
                await log_channel.send(f"✅ Sent notification to {recipient_id}")

            return True

        except Exception as e:
            await log_channel.send(f"❌ Error processing gift: {str(e)}")
            traceback_str = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
            await log_channel.send(f"```\n{traceback_str}\n```")
            raise

    @is_gm()
    @commands.command()
    async def forcegift(self, ctx):
        """Distribute gifts daily at 12 PM UTC ensuring 1:1 gift ratio"""
        async with self.bot.pool.acquire() as conn:
            # Get all unclaimed gifts
            unclaimed_gifts = await conn.fetch("""
                SELECT * FROM gift_history 
                WHERE claimed = false 
                ORDER BY timestamp ASC
            """)

            if not unclaimed_gifts:
                return await ctx.send("No unclaimed gifts found.")

            for gift in unclaimed_gifts:
                try:
                    distributed = await self.distribute_gift_by_tier(conn, gift)
                    # 'distributed' is True if gift was successfully delivered, False if not.
                except Exception as e:
                    # Format the full traceback
                    tb_str = ''.join(traceback.format_exception(None, e, e.__traceback__))

                    # Send the traceback to the channel
                    # Be cautious with this in a production environment.
                    await ctx.send(f"Error processing gift {gift['id']}:\n```\n{tb_str}\n```")

                    # Also print it to console for your reference
                    print(tb_str)
                    continue

    @tasks.loop(time=datetime.time(hour=12))  # Run at 12 PM UTC
    async def gift_distribution_task(self):
        """Distribute gifts daily at 12 PM UTC ensuring tier-for-tier gift ratio"""
        async with self.bot.pool.acquire() as conn:
            # Get all unclaimed gifts
            unclaimed_gifts = await conn.fetch("""
                SELECT * FROM gift_history 
                WHERE claimed = false 
                ORDER BY timestamp ASC
            """)

            if not unclaimed_gifts:
                return

            for gift in unclaimed_gifts:
                try:
                    await self.distribute_gift_by_tier(conn, gift)
                except Exception as e:
                    print(f"Error processing gift {gift['id']}: {str(e)}")
                    continue

    @commands.command()
    async def giftbalance(self, ctx, user: discord.Member = None):
        """Check gift giving/receiving balance"""
        user = user or ctx.author

        async with self.bot.pool.acquire() as conn:
            stats = await conn.fetchrow("""
                SELECT 
                    COUNT(*) FILTER (WHERE user_id = $1) as gifts_given,
                    COUNT(*) FILTER (WHERE claimed_by = $1) as gifts_received
                FROM gift_history
                WHERE user_id = $1 OR claimed_by = $1
            """, user.id)

            embed = discord.Embed(
                title=f"🎁 Gift Balance for {user.name}",
                color=discord.Color.blue()
            )

            embed.add_field(
                name="Gift Statistics",
                value=(
                    f"Gifts Given: {stats['gifts_given']}\n"
                    f"Gifts Received: {stats['gifts_received']}\n"
                    f"Balance: {stats['gifts_given'] - stats['gifts_received']} gift(s) can be received"
                ),
                inline=False
            )

            await ctx.send(embed=embed)

    async def process_gift_transfer(self, conn, gift, recipient_id):
        """Process the transfer of a gift to a recipient"""
        await conn.execute('BEGIN')
        try:
            if gift['gift_type'] == 'mystery_box':
                # Parse box contents from JSONB
                box_contents = gift['box_contents']
                if isinstance(box_contents, str):
                    # Parse if it's a string (some DBs might return it as string)
                    box_contents = json.loads(box_contents)

                for item in box_contents:
                    if item["type"] == "gold":
                        await conn.execute(
                            'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                            item["amount"],
                            recipient_id
                        )
                    else:
                        await conn.execute(
                            f'UPDATE profile SET "crates_{item["type"]}"='
                            f'"crates_{item["type"]}"+$1 WHERE "user"=$2;',
                            item["amount"],
                            recipient_id
                        )
            else:
                if gift['gift_type'] == "gold":
                    await conn.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                        gift['amount'],
                        recipient_id
                    )
                else:
                    await conn.execute(
                        f'UPDATE profile SET "crates_{gift["gift_type"]}"='
                        f'"crates_{gift["gift_type"]}"+$1 WHERE "user"=$2;',
                        gift['amount'],
                        recipient_id
                    )

            # Mark gift as claimed
            await conn.execute("""
                UPDATE gift_history 
                SET claimed = true, 
                    claimed_by = $1, 
                    claimed_at = NOW()
                WHERE id = $2
            """, recipient_id, gift['id'])

            await conn.execute('COMMIT')
        except:
            await conn.execute('ROLLBACK')
            raise

    async def send_patterned_gift_notification(self, recipient, gift):
        """Send a notification to the recipient with the specified pattern"""
        pattern_name = gift.get('pattern', 'classic')
        pattern = self.WRAP_PATTERNS.get(pattern_name, self.WRAP_PATTERNS["classic"])
        tier = await self._get_gift_tier(gift['value'])
        tier_data = self.GIFT_TIERS[tier]

        # Create initial mystery box embed
        embed = discord.Embed(
            title=f"📦 {tier_data['icon']} Mystery Gift Received!" if gift['gift_type'] == 'mystery_box' else pattern[
                "title"],
            color=pattern["color"]
        )

        # Add pattern border
        embed.description = f"{pattern['border']}\n"

        # Add gift details depending on type
        if gift['gift_type'] == 'mystery_box':
            box_contents = gift['box_contents']
            if isinstance(box_contents, str):
                box_contents = json.loads(box_contents)

            # Send initial mystery box message
            embed.add_field(
                name=f"{tier_data['icon']} Mystery Box!",
                value="A special gift box has arrived! React with 📦 to open it!",
                inline=False
            )
        else:
            value_text = (f"{gift['amount']:,} gold" if gift['gift_type'] == "gold"
                          else f"{gift['amount']} {gift['gift_type']} crates")
            embed.add_field(
                name=f"{tier_data['icon']} Gift Contents",
                value=value_text,
                inline=False
            )

        # Add message if present
        if gift.get('message'):
            embed.add_field(
                name="📝 Message",
                value=f"\"{gift['message']}\"\n\n- Anonymous",
                inline=False
            )

        # Add pattern border to footer
        embed.set_footer(text=f"{pattern['border']}")

        try:
            # Send the gift message
            gift_msg = await recipient.send(embed=embed)

            # Add appropriate reaction
            reaction_emoji = "📦" if gift['gift_type'] == 'mystery_box' else pattern["emojis"][0]
            await gift_msg.add_reaction(reaction_emoji)

            # Set up reaction collector for gift opening
            def check(reaction, user):
                return (
                        user.id == recipient.id and
                        str(reaction.emoji) == reaction_emoji
                )

            try:
                await self.bot.wait_for('reaction_add', timeout=86400.0, check=check)

                # Create reveal embed
                if gift['gift_type'] == 'mystery_box':
                    contents = "\n".join([
                        f"• {item['amount']:,} {item['type']}"
                        for item in box_contents
                    ])
                    reveal_embed = discord.Embed(
                        title=f"📦 Mystery Box Opened! {tier_data['icon']}",
                        description=f"The box contained:\n{contents}",
                        color=tier_data['color']
                    )
                else:
                    value_text = (f"{gift['amount']:,} gold" if gift['gift_type'] == "gold"
                                  else f"{gift['amount']} {gift['gift_type']} crates")
                    reveal_embed = discord.Embed(
                        title=f"{tier_data['icon']} Gift Revealed! {tier_data['icon']}",
                        description=f"You received {value_text}!",
                        color=tier_data['color']
                    )

                if gift.get('message'):
                    reveal_embed.add_field(
                        name="📝 Message",
                        value=f"\"{gift['message']}\"\n- Anonymous",
                        inline=False
                    )

                await gift_msg.edit(embed=reveal_embed)

            except asyncio.TimeoutError:
                # Auto-reveal after 24 hours
                pass

        except discord.HTTPException:
            print(f"Failed to send gift notification to user {recipient.id}")

    async def send_gift_notification(self, recipient, gift):
        """Send notification to recipient about their gift"""
        tier = await self._get_gift_tier(gift['value'])
        tier_data = self.GIFT_TIERS[tier]

        embed = discord.Embed(
            title=f"{tier_data['icon']} You Received a Gift!",
            description="A generous donor has sent you something special!",
            color=tier_data['color']
        )

        value = (f"{gift['amount']:,} gold" if gift['gift_type'] == "gold"
                 else f"{gift['amount']} {gift['gift_type']} crates")

        embed.add_field(
            name="Gift Contents",
            value=value,
            inline=False
        )

        if gift['message']:
            embed.add_field(
                name="Message",
                value=f"\"{gift['message']}\"\n- Anonymous",
                inline=False
            )

        try:
            await recipient.send(embed=embed)
        except discord.HTTPException:
            pass


    async def _create_gift_embed(self, pattern_name, message=None):
        """Create a decorated embed for a gift."""
        pattern = self.WRAP_PATTERNS.get(pattern_name, self.WRAP_PATTERNS["classic"])
        embed = discord.Embed(
            title=pattern["title"],
            color=pattern["color"]
        )
        embed.description = f"{pattern['border']}\n"
        if message:
            embed.add_field(
                name="📝 Message",
                value=f"\"{message}\"\n- Anonymous",
                inline=False
            )
        embed.set_footer(text=f"{pattern['border']}")
        return embed

    async def _get_gift_tier(self, value: int) -> str:
        """Determine the tier of a gift based on its value."""
        for tier, data in self.GIFT_TIERS.items():
            if data["range"][0] <= value <= data["range"][1]:
                return tier
        return "legendary" if value > self.GIFT_TIERS["legendary"]["range"][0] else "novice"

    async def _calculate_gift_value(self, gift_type: str, amount: int) -> int:
        """Calculate the total value of a gift."""
        if gift_type == "gold":
            return amount
        return self.CRATE_VALUES.get(gift_type, 0) * amount

    @commands.command()
    @locale_doc
    @has_char()
    async def giftforward(
            self,
            ctx,
            amount: str,
            gift_type: str = "gold",
            pattern: str = "classic",
            *,
            message: str = None
    ):
        _("""Gift something to a random donor with custom wrapping!
            Pattern options: classic, starry, hearts, winter, party, royal
            Add a message to make it special!""")

        # Check if user has already gifted today
        async with ctx.bot.pool.acquire() as conn:
            last_gift = await conn.fetchrow("""
                SELECT * FROM gift_history 
                WHERE user_id = $1 
                AND timestamp > (
                    CASE 
                        WHEN CURRENT_TIME >= TIME '12:00:00'
                        THEN CURRENT_DATE + TIME '12:00:00'
                        ELSE CURRENT_DATE + TIME '12:00:00' - INTERVAL '1 day'
                    END
                )
            """, ctx.author.id)

            if last_gift:
                # Calculate time until next distribution
                now = datetime.datetime.utcnow()
                next_distribution = datetime.datetime.combine(
                    now.date() if now.hour < 12 else now.date() + datetime.timedelta(days=1),
                    datetime.time(hour=12)
                )
                time_until = next_distribution - now
                hours = time_until.seconds // 3600
                minutes = (time_until.seconds % 3600) // 60

                return await ctx.send(
                    f"You've already sent a gift today! "
                    f"Next gift in {hours} hours and {minutes} minutes "
                    f"(12 PM UTC)!"
                )

        if pattern not in self.WRAP_PATTERNS:
            pattern = "classic"

        if message and len(message) > 100:
            return await ctx.send(_("Message must be 100 characters or less!"))

        # Calculate gift value
        if gift_type == "gold":
            try:
                value = int(amount) if amount != "all" else ctx.character_data["money"]
            except ValueError:
                return await ctx.send(_("Invalid amount!"))
        else:
            try:
                value = self.CRATE_VALUES[gift_type.lower()] * int(amount)
            except (KeyError, ValueError):
                return await ctx.send(_("Invalid gift type or amount!"))

        if value < self.min_donation:
            return await ctx.send(
                _("Minimum donation is {} gold!").format(
                    self.min_donation
                )
            )

        # Get gift tier
        tier = await self._get_gift_tier(value)
        tier_data = self.GIFT_TIERS[tier]

        async with ctx.bot.pool.acquire() as conn:
            # Verify user has the resources
            if gift_type.lower() == "gold":
                if ctx.character_data["money"] < value:
                    return await ctx.send(_("You don't have enough gold!"))
            else:
                if ctx.character_data[f"crates_{gift_type.lower()}"] < int(amount):
                    return await ctx.send(f"Not enough {gift_type} crates!")

            try:
                await conn.execute('BEGIN')

                # Deduct resources from donor
                if gift_type.lower() == "gold":
                    await conn.execute(
                        'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                        value,
                        ctx.author.id
                    )
                else:
                    await conn.execute(
                        f'UPDATE profile SET "crates_{gift_type.lower()}"="crates_{gift_type.lower()}"-$1 WHERE "user"=$2;',
                        int(amount),
                        ctx.author.id
                    )

                # Store the gift for later distribution
                gift_data = {
                    'user_id': ctx.author.id,
                    'gift_type': gift_type.lower(),
                    'amount': int(amount),
                    'value': value,
                    'tier': tier,
                    'message': message,
                    'pattern': pattern,
                    'claimed': False
                }

                gift_id = await conn.fetchval("""
                    INSERT INTO gift_history 
                    (user_id, gift_type, amount, value, tier, message, pattern, claimed)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    RETURNING id
                """, *gift_data.values())

                await conn.execute('COMMIT')

                # Create confirmation embed
                confirm_embed = discord.Embed(
                    title=f"{tier_data['icon']} Gift Scheduled!",
                    description="Your gift has been stored for distribution!",
                    color=tier_data['color']
                )

                confirm_embed.add_field(
                    name="Gift Details",
                    value=(
                        f"Type: {gift_type.capitalize()}\n"
                        f"Amount: {int(amount)}\n"
                        f"Value: {value} gold\n"
                        f"Tier: {tier.capitalize()}\n"
                        f"Pattern: {pattern.capitalize()}"
                    ),
                    inline=False
                )

                if message:
                    confirm_embed.add_field(
                        name="Message",
                        value=message,
                        inline=False
                    )

                confirm_embed.add_field(
                    name="Distribution",
                    value=(
                        "Your gift will be distributed at the next gift distribution time (12 PM UTC).\n"
                        "The recipient will be randomly selected from eligible gifters."
                    ),
                    inline=False
                )

                confirm_embed.set_footer(text=f"Gift ID: {gift_id} | Pattern: {pattern}")

                await ctx.send(embed=confirm_embed)

            except Exception as e:
                await conn.execute('ROLLBACK')
                await ctx.send(f"Error processing gift: {str(e)}")
                return

        # Add gift to distribution queue
        try:
            # Notify in logs
            log_channel = self.bot.fetch_channel(1313482408242184213)
            if log_channel:
                log_embed = discord.Embed(
                    title="🎁 New Gift Queued",
                    description=f"Gift from {ctx.author.name} ({ctx.author.id})",
                    color=discord.Color.green(),
                    timestamp=datetime.datetime.utcnow()
                )
                log_embed.add_field(
                    name="Details",
                    value=(
                        f"ID: {gift_id}\n"
                        f"Type: {gift_type}\n"
                        f"Amount: {int(amount)}\n"
                        f"Value: {value} gold\n"
                        f"Tier: {tier}"
                    ),
                    inline=False
                )
                await log_channel.send(embed=log_embed)
        except Exception as e:
            print(f"Failed to send gift log: {e}")

    @commands.command()
    @locale_doc
    @has_char()
    async def mysterybox(self, ctx, *items: str):
        """Create a mystery box for the gift pool"""

        # Check if user has already gifted today
        async with ctx.bot.pool.acquire() as conn:
            last_gift = await conn.fetchrow("""
                        SELECT * FROM gift_history 
                        WHERE user_id = $1 
                        AND timestamp > (
                            CASE 
                                WHEN CURRENT_TIME >= TIME '12:00:00'
                                THEN CURRENT_DATE + TIME '12:00:00'
                                ELSE CURRENT_DATE + TIME '12:00:00' - INTERVAL '1 day'
                            END
                        )
                    """, ctx.author.id)

            if last_gift:
                # Calculate time until next distribution
                now = datetime.datetime.utcnow()
                next_distribution = datetime.datetime.combine(
                    now.date() if now.hour < 12 else now.date() + datetime.timedelta(days=1),
                    datetime.time(hour=12)
                )
                time_until = next_distribution - now
                hours = time_until.seconds // 3600
                minutes = (time_until.seconds % 3600) // 60

                return await ctx.send(
                    f"You've already sent a gift today! "
                    f"Next gift in {hours} hours and {minutes} minutes "
                    f"(12 PM UTC)!"
                )

        if len(items) % 2 != 0:
            return await ctx.send(_("Invalid format! Use: $mysterybox amount1 type1 amount2 type2..."))

        async with self.bot.pool.acquire() as conn:
            # Verify user has all items and calculate total value
            box_contents = []
            total_value = 0

            for i in range(0, len(items), 2):
                try:
                    amount = int(items[i])
                    item_type = items[i + 1].lower()
                except (ValueError, IndexError):
                    return await ctx.send(_("Invalid amount or type!"))

                if item_type == "gold":
                    if ctx.character_data["money"] < amount:
                        return await ctx.send(_("Not enough gold!"))
                    total_value += amount
                    box_contents.append({"type": "gold", "amount": amount})
                elif item_type in self.CRATE_VALUES:
                    if ctx.character_data[f"crates_{item_type}"] < amount:
                        return await ctx.send(f"Not enough {item_type} crates!")
                    total_value += self.CRATE_VALUES[item_type] * amount
                    box_contents.append({"type": item_type, "amount": amount})
                else:
                    return await ctx.send(f"Invalid item type: {item_type}")

            if total_value < self.min_donation:
                return await ctx.send(
                    _("Box total value must be at least {} gold!").format(
                        self.min_donation
                    )
                )

            # Get gift tier based on total value
            tier = await self._get_gift_tier(total_value)
            tier_data = self.GIFT_TIERS[tier]

            try:
                await conn.execute('BEGIN')

                # Remove items from donor
                for item in box_contents:
                    if item["type"] == "gold":
                        await conn.execute(
                            'UPDATE profile SET "money"="money"-$1 WHERE "user"=$2;',
                            item["amount"],
                            ctx.author.id
                        )
                    else:
                        await conn.execute(
                            f'UPDATE profile SET "crates_{item["type"]}"="crates_{item["type"]}"-$1 WHERE "user"=$2;',
                            item["amount"],
                            ctx.author.id
                        )

                # Add mystery box to pool
                box_contents_json = json.dumps(box_contents)  # Convert to JSON string
                gift_id = await conn.fetchval("""
                                INSERT INTO gift_history 
                                (user_id, gift_type, amount, value, tier, claimed, is_mystery_box, box_contents)
                                VALUES ($1, 'mystery_box', 1, $2, $3, false, true, $4::jsonb)
                                RETURNING id
                            """,
                                              ctx.author.id,
                                              total_value,
                                              tier,
                                              box_contents_json
                                              )

                await conn.execute('COMMIT')

                # Create confirmation embed
                confirm_embed = discord.Embed(
                    title=f"📦 {tier_data['icon']} Mystery Box Added to Pool!",
                    description=(
                        f"Your {tier_data['title']} mystery box has been added to the gift pool!\n"
                        f"Total Value: {total_value:,} gold"
                    ),
                    color=tier_data['color']
                )

                contents_text = "\n".join([
                    f"• {item['amount']} {item['type']}"
                    for item in box_contents
                ])
                confirm_embed.add_field(
                    name="Box Contents",
                    value=contents_text,
                    inline=False
                )

                await ctx.send(embed=confirm_embed)

            except Exception as e:
                await conn.execute('ROLLBACK')
                await ctx.send(f"Error processing mystery box: {str(e)}")
                return

    # Admin Commands Group
    @commands.group(invoke_without_command=True)
    @is_gm()
    async def giftpool(self, ctx):
        """Admin commands for monitoring the gift pool"""
        await ctx.send(_(
            "Available commands:\n"
            "`$giftpool view` - View all gifts in pool\n"
            "`$giftpool stuck` - View gifts waiting >24h\n"
            "`$giftpool tier <tier>` - View specific tier\n"
            "`$giftpool match <gift_id> <recipient_id>` - Manually match a gift\n"
            "`$giftpool matchsearch <gift_id>` - Find potential matches"
        ))

    @giftpool.command(name="view")
    @is_gm()
    async def giftpool_view(self, ctx):
        """View all gifts currently in the pool"""
        async with self.bot.pool.acquire() as conn:
            gifts = await conn.fetch("""
                    SELECT 
                        gh.id,
                        gh.user_id,
                        gh.gift_type,
                        gh.amount,
                        gh.value,
                        gh.tier,
                        gh.timestamp,
                        COUNT(DISTINCT eligible.user_id) as eligible_recipients
                    FROM gift_history gh
                    LEFT JOIN gift_history eligible ON 
                        eligible.tier = gh.tier
                        AND eligible.user_id != gh.user_id
                    WHERE gh.claimed = false
                    GROUP BY gh.id, gh.user_id, gh.gift_type, gh.amount, gh.value, gh.tier, gh.timestamp
                    ORDER BY gh.timestamp ASC
                """)

            if not gifts:
                return await ctx.send("No gifts currently in pool!")

            pages = []
            for i in range(0, len(gifts), 5):
                embed = discord.Embed(
                    title="🎁 Gift Pool Status",
                    description="Currently unclaimed gifts",
                    color=discord.Color.blue()
                )

                for gift in gifts[i:i + 5]:
                    donor = self.bot.get_user(gift['user_id'])
                    donor_name = donor.name if donor else f"User {gift['user_id']}"
                    wait_time = datetime.utcnow() - gift['timestamp']

                    if gift['gift_type'] == 'mystery_box':
                        value = f"Mystery Box worth {gift['value']:,} gold"
                    else:
                        value = (f"{gift['amount']:,} gold" if gift['gift_type'] == "gold"
                                 else f"{gift['amount']} {gift['gift_type']} crates")

                    embed.add_field(
                        name=f"{self.GIFT_TIERS[gift['tier']]['icon']} {gift['tier'].title()} Gift",
                        value=f"From: {donor_name}\n"
                              f"Value: {value}\n"
                              f"Waiting: {wait_time.days}d {wait_time.seconds // 3600}h\n"
                              f"Eligible Recipients: {gift['eligible_recipients']}\n"
                              f"ID: {gift['id']}",
                        inline=False
                    )

                pages.append(embed)

            if len(pages) == 1:
                await ctx.send(embed=pages[0])
            else:
                # Simple pagination
                current_page = 0
                message = await ctx.send(embed=pages[current_page])

                await message.add_reaction("⬅️")
                await message.add_reaction("➡️")

                def check(reaction, user):
                    return user == ctx.author and str(reaction.emoji) in ["⬅️", "➡️"]

                while True:
                    try:
                        reaction, user = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)

                        if str(reaction.emoji) == "➡️" and current_page < len(pages) - 1:
                            current_page += 1
                            await message.edit(embed=pages[current_page])
                        elif str(reaction.emoji) == "⬅️" and current_page > 0:
                            current_page -= 1
                            await message.edit(embed=pages[current_page])

                        await message.remove_reaction(reaction, user)
                    except asyncio.TimeoutError:
                        break

    @giftpool.command(name="stuck")
    @is_gm()
    async def giftpool_stuck(self, ctx, hours: int = 24):
        """View gifts that have been waiting longer than specified hours"""
        async with self.bot.pool.acquire() as conn:
            stuck_gifts = await conn.fetch("""
                    SELECT 
                        gh.id,
                        gh.user_id,
                        gh.gift_type,
                        gh.amount,
                        gh.value,
                        gh.tier,
                        gh.timestamp,
                        COUNT(DISTINCT eligible.user_id) as eligible_recipients
                    FROM gift_history gh
                    LEFT JOIN gift_history eligible ON 
                        eligible.tier = gh.tier
                        AND eligible.user_id != gh.user_id
                    WHERE gh.claimed = false
                    AND gh.timestamp < NOW() - INTERVAL '$1 hours'
                    GROUP BY gh.id, gh.user_id, gh.gift_type, gh.amount, gh.value, gh.tier, gh.timestamp
                    ORDER BY gh.timestamp ASC
                """, hours)

            if not stuck_gifts:
                return await ctx.send(f"No gifts stuck for more than {hours} hours!")

            embed = discord.Embed(
                title="⚠️ Stuck Gifts",
                description=f"Gifts waiting longer than {hours} hours",
                color=discord.Color.orange()
            )

            for gift in stuck_gifts:
                donor = self.bot.get_user(gift['user_id'])
                donor_name = donor.name if donor else f"User {gift['user_id']}"
                wait_time = datetime.utcnow() - gift['timestamp']

                if gift['gift_type'] == 'mystery_box':
                    value = f"Mystery Box worth {gift['value']:,} gold"
                else:
                    value = (f"{gift['amount']:,} gold" if gift['gift_type'] == "gold"
                             else f"{gift['amount']} {gift['gift_type']} crates")

                embed.add_field(
                    name=f"{self.GIFT_TIERS[gift['tier']]['icon']} {gift['tier'].title()} Gift",
                    value=f"From: {donor_name}\n"
                          f"Value: {value}\n"
                          f"Waiting: {wait_time.days}d {wait_time.seconds // 3600}h\n"
                          f"Eligible Recipients: {gift['eligible_recipients']}\n"
                          f"ID: {gift['id']}",
                    inline=False
                )

            await ctx.send(embed=embed)

    # Continuation of manual_match command
    @giftpool.command(name="match")
    @is_gm()
    async def manual_match(self, ctx, gift_id: int, recipient_id: int):
        """Manually match a gift to a specific recipient"""
        async with self.bot.pool.acquire() as conn:
            # Verify gift exists and is unclaimed
            gift = await conn.fetchrow("""
                SELECT *
                FROM gift_history
                WHERE id = $1 AND claimed = false
            """, gift_id)

            if not gift:
                return await ctx.send("❌ Gift not found or already claimed!")

            # Verify recipient exists
            recipient_profile = await conn.fetchrow(
                'SELECT * FROM profile WHERE "user"=$1',
                recipient_id
            )

            if not recipient_profile:
                return await ctx.send("❌ Recipient not found!")

            if gift['user_id'] == recipient_id:
                return await ctx.send("❌ Cannot give gift to the original donor!")

            # Create confirmation embed
            recipient = self.bot.get_user(recipient_id)
            donor = self.bot.get_user(gift['user_id'])

            confirm_embed = discord.Embed(
                title="🎁 Confirm Manual Gift Match",
                description="Please confirm this gift matching:",
                color=discord.Color.yellow()
            )

            # Display gift details based on type
            if gift['gift_type'] == 'mystery_box':
                value = f"Mystery Box worth {gift['value']:,} gold"
                contents = "\n".join([
                    f"• {item['amount']:,} {item['type']}"
                    for item in gift['box_contents']
                ])
                confirm_embed.add_field(name="Box Contents", value=contents)
            else:
                value = (f"{gift['amount']:,} gold" if gift['gift_type'] == "gold"
                         else f"{gift['amount']} {gift['gift_type']} crates")

            confirm_embed.add_field(
                name="Gift Details",
                value=f"ID: {gift['id']}\n"
                      f"Type: {gift['gift_type']}\n"
                      f"Value: {value}\n"
                      f"Tier: {gift['tier']}",
                inline=False
            )

            confirm_embed.add_field(
                name="From",
                value=f"{donor.name if donor else 'Unknown'} (ID: {gift['user_id']})",
                inline=True
            )

            confirm_embed.add_field(
                name="To",
                value=f"{recipient.name if recipient else 'Unknown'} (ID: {recipient_id})",
                inline=True
            )

            # Add confirmation buttons
            confirm_msg = await ctx.send(
                embed=confirm_embed,
                components=[
                    Button(style=discord.ButtonStyle.green, label="Confirm", custom_id="confirm"),
                    Button(style=discord.ButtonStyle.red, label="Cancel", custom_id="cancel")
                ]
            )

            try:
                interaction = await self.bot.wait_for(
                    "button_click",
                    timeout=30.0,
                    check=lambda i: i.user.id == ctx.author.id
                )

                if interaction.custom_id == "cancel":
                    await confirm_msg.edit(content="❌ Match cancelled!", embed=None, components=[])
                    return

                # Process the gift transfer
                await conn.execute('BEGIN')
                try:
                    if gift['gift_type'] == 'mystery_box':
                        for item in gift['box_contents']:
                            if item['type'] == "gold":
                                await conn.execute(
                                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                                    item['amount'],
                                    recipient_id
                                )
                            else:
                                await conn.execute(
                                    f'UPDATE profile SET "crates_{item["type"]}"='
                                    f'"crates_{item["type"]}"+$1 WHERE "user"=$2;',
                                    item['amount'],
                                    recipient_id
                                )
                    else:
                        if gift['gift_type'] == "gold":
                            await conn.execute(
                                'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                                gift['amount'],
                                recipient_id
                            )
                        else:
                            await conn.execute(
                                f'UPDATE profile SET "crates_{gift["gift_type"]}"='
                                f'"crates_{gift["gift_type"]}"+$1 WHERE "user"=$2;',
                                gift['amount'],
                                recipient_id
                            )

                    # Mark gift as claimed
                    await conn.execute("""
                        UPDATE gift_history 
                        SET claimed = true, 
                            claimed_by = $1, 
                            claimed_at = NOW(),
                            matched_by = $2
                        WHERE id = $3
                    """, recipient_id, ctx.author.id, gift_id)

                    await conn.execute('COMMIT')

                    # Send notifications
                    success_embed = discord.Embed(
                        title="✅ Gift Manually Matched!",
                        description="The gift has been successfully transferred.",
                        color=discord.Color.green()
                    )
                    success_embed.add_field(
                        name="Gift Details",
                        value=value,
                        inline=False
                    )

                    await confirm_msg.edit(
                        embed=success_embed,
                        components=[]
                    )

                    # Notify recipient
                    if recipient:
                        recipient_embed = discord.Embed(
                            title=f"{self.GIFT_TIERS[gift['tier']]['icon']} You Received a Gift!",
                            description=f"You received: {value}",
                            color=self.GIFT_TIERS[gift['tier']]['color']
                        )
                        try:
                            await recipient.send(embed=recipient_embed)
                        except discord.HTTPException:
                            pass

                except Exception as e:
                    await conn.execute('ROLLBACK')
                    await ctx.send(f"❌ Error processing gift: {str(e)}")
                    return

            except asyncio.TimeoutError:
                await confirm_msg.edit(
                    content="⏱️ Confirmation timed out!",
                    embed=None,
                    components=[]
                )

    @commands.command(name="gifthelp")
    async def gift_help(self, ctx):
        """Display help information about the gift system"""
        embed = discord.Embed(
            title="🎁 Gift Forward System Guide",
            description=(
                "Share gifts with other gifters in the community! Your gifts go into a pool "
                "and are distributed daily at 12 PM UTC to other gifters who have given gifts before."
            ),
            color=discord.Color.gold()
        )

        # Basic Commands
        embed.add_field(
            name="📜 Basic Commands",
            value=(
                "`$giftforward <amount> <type> [pattern] [message]`\n"
                "- Give gold or crates to the gift pool\n"
                "`$mysterybox <amount1> <type1> <amount2> <type2>...`\n"
                "- Create a special box with multiple items\n"
                "`$patterns`\n"
                "- View available gift wrapping patterns\n"
                "`$tiers`\n"
                "- View gift tier ranges and rewards"
            ),
            inline=False
        )

        # Gift Types
        embed.add_field(
            name="🎁 Gift Types",
            value=(
                "**Gold**: 1,000 min up to amount of gold\n"
                "**Crates**: Any type of crate\n"
                f"Minimum gift value: {self.min_donation:,} gold"
            ),
            inline=False
        )

        # Mystery Boxes
        embed.add_field(
            name="📦 Mystery Boxes",
            value=(
                "Combine multiple items into one special gift!\n"
                "Example: `$mysterybox 100000 gold 2 legendary`\n"
                "This creates a box with both gold and crates."
            ),
            inline=False
        )

        # Patterns
        embed.add_field(
            name="🎨 Gift Patterns",
            value=(
                "Make your gift special with custom patterns!\n"
                "Example: `$giftforward 150000 gold kawaii \"Good luck!\"`\n"
                "Use `$patterns` to see all available styles."
            ),
            inline=False
        )

        # How It Works
        embed.add_field(
            name="⚙️ How It Works",
            value=(
                "1. Give a gift using `$giftforward` or `$mysterybox`\n"
                "2. Your gift enters the pool\n"
                "3. At 12 PM UTC daily, gifts are distributed\n"
                "4. Recipients must be previous gifters\n"
                "5. Gifts match similar value tiers"
            ),
            inline=False
        )

        # Gift Tiers
        tiers_text = ""
        for tier, data in self.GIFT_TIERS.items():
            min_val, max_val = data["range"]
            max_display = f"{max_val:,}" if max_val != float('inf') else "∞"
            tiers_text += f"{data['icon']} **{tier.title()}**: {min_val:,} - {max_display} gold\n"

        embed.add_field(
            name="🏆 Gift Tiers",
            value=tiers_text,
            inline=False
        )

        # Tips
        embed.add_field(
            name="💡 Tips",
            value=(
                "• Higher value gifts match with higher value gifters\n"
                "• Add a message to make your gift special\n"
                "• Mystery boxes can contain multiple types of items\n"
                "• Use patterns to make your gift unique\n"
                "• Recipients must be previous gifters"
            ),
            inline=False
        )

        await ctx.send(embed=embed)

    # Helper Commands
    @commands.command()
    async def patterns(self, ctx):
        """View available gift wrapping patterns"""

        # Create initial embed with title and description
        embed = discord.Embed(
            title="🎨 Available Gift Patterns",
            description="Use these pattern names when gifting:\n`$giftforward <amount> <type> <pattern_name>`",
            color=discord.Color.blue()
        )

        # Add each pattern with its name and details
        for pattern_name, pattern in self.WRAP_PATTERNS.items():
            embed.add_field(
                name=f"{pattern['title']} (`{pattern_name}`)",  # Added pattern name in command format
                value=f"Pattern Name: `{pattern_name}`\n"  # Explicitly show the name to use
                      f"Border Style: {pattern['border']}\n"
                      f"Emojis: {''.join(pattern['emojis'])}",
                inline=False
            )

        # Add example usage footer
        embed.set_footer(text="Example: $giftforward 150000 gold kawaii")

        await ctx.send(embed=embed)

    @commands.command()
    async def tiers(self, ctx):
        """View all gift tiers and their ranges"""
        embed = discord.Embed(
            title="🎁 Gift Tiers",
            description="Different tiers of gifting generosity!",
            color=discord.Color.gold()
        )

        for tier, data in self.GIFT_TIERS.items():
            min_val, max_val = data["range"]
            max_display = f"{max_val:,}" if max_val != float('inf') else "∞"

            embed.add_field(
                name=f"{data['icon']} {data['title']}",
                value=f"Range: {min_val:,} - {max_display} gold\n"
                      f"Available Patterns: {', '.join(data['patterns'])}",
                inline=False
            )

        await ctx.send(embed=embed)


    @commands.command()
    @is_gm()
    async def giftconfig(self, ctx, setting: str, value: str):
        """Configure gift system settings (Admin only)"""
        valid_settings = ["min_donation", "tier_ranges"]

        if setting not in valid_settings:
            return await ctx.send(f"Invalid setting. Valid settings: {', '.join(valid_settings)}")

        async with self.bot.pool.acquire() as conn:
            if setting == "min_donation":
                try:
                    new_value = int(value)
                    if new_value < 0:
                        return await ctx.send("Minimum donation must be positive!")

                    await conn.execute(
                        "UPDATE gift_config SET min_donation = $1",
                        new_value
                    )
                    self.min_donation = new_value
                    await ctx.send(f"Minimum donation updated to {new_value:,} gold")
                except ValueError:
                    await ctx.send("Invalid value for minimum donation!")




    @is_gm()
    @commands.command()
    async def giftstats(self, ctx, user: discord.Member = None):
        """View gift statistics for a user"""
        user = user or ctx.author

        async with self.bot.pool.acquire() as conn:
            stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total_gifts,
                        SUM(value) as total_value,
                        COUNT(CASE WHEN is_mystery_box THEN 1 END) as mystery_boxes,
                        MAX(value) as highest_value,
                        MIN(value) as lowest_value,
                        COUNT(DISTINCT tier) as unique_tiers
                    FROM gift_history
                    WHERE user_id = $1
                """, user.id)

            recent_gifts = await conn.fetch("""
                    SELECT gift_type, amount, value, tier, timestamp
                    FROM gift_history
                    WHERE user_id = $1
                    ORDER BY timestamp DESC
                    LIMIT 5
                """, user.id)

            embed = discord.Embed(
                title=f"🎁 Gift Statistics for {user.name}",
                color=discord.Color.blue()
            )

            embed.add_field(
                name="Overall Stats",
                value=f"Total Gifts: {stats['total_gifts']}\n"
                      f"Total Value: {stats['total_value']:,} gold\n"
                      f"Mystery Boxes: {stats['mystery_boxes']}\n"
                      f"Unique Tiers: {stats['unique_tiers']}",
                inline=False
            )

            if stats['highest_value']:
                embed.add_field(
                    name="Gift Range",
                    value=f"Highest: {stats['highest_value']:,} gold\n"
                          f"Lowest: {stats['lowest_value']:,} gold",
                    inline=False
                )

            if recent_gifts:
                recent = "\n".join([
                    f"{gift['timestamp'].strftime('%Y-%m-%d')}: "
                    f"{gift['amount']} {gift['gift_type']} "
                    f"({self.GIFT_TIERS[gift['tier']]['icon']})"
                    for gift in recent_gifts
                ])
                embed.add_field(
                    name="Recent Gifts",
                    value=recent,
                    inline=False
                )

            await ctx.send(embed=embed)

@commands.Cog.listener()
async def on_ready(self):
    """Ensure the gift distribution task is running"""
    if not self.gift_distribution_task.is_running():
        self.gift_distribution_task.start()

def cog_unload(self):
    """Clean up when cog is unloaded"""
    self.gift_distribution_task.cancel()


async def setup(bot):
    """Add the cog to the bot"""
    await bot.add_cog(GiftForward(bot))

