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
import datetime
import re
import traceback

from discord import Embed, File
from decimal import Decimal, ROUND_HALF_UP, getcontext
import utils.misc as rpgtools
import discord

from discord.enums import ButtonStyle
import random as randomm
from discord.ext import commands, tasks
from discord.ui.button import Button
from discord.interactions import Interaction
from discord.ui import Button, View

from classes.classes import Raider
from classes.classes import from_string as class_from_string
from classes.converters import IntGreaterThan
from cogs.shard_communication import user_on_cooldown as user_cooldown
from utils import random
from utils.checks import AlreadyRaiding, has_char, is_gm, is_god
from utils.i18n import _, locale_doc
from utils.joins import JoinView


def raid_channel():
    def predicate(ctx):
        return (
                ctx.bot.config.bot.is_beta
                or ctx.channel.id == ctx.bot.config.game.raid_channel
        )

    return commands.check(predicate)


def raid_free():
    async def predicate(ctx):
        ttl = await ctx.bot.redis.execute_command("TTL", "special:raid")
        if ttl != -2:
            raise AlreadyRaiding("There is already a raid ongoing.")
        return True

    return commands.check(predicate)


def celestial_vault_free():
    async def predicate(ctx):
        # Check if any raid is ongoing
        ttl = await ctx.bot.redis.execute_command("TTL", "special:raid")
        if ttl != -2:
            raise AlreadyRaiding("There is already a raid ongoing.")
            
        # Check if user has used celestial vault today
        user_cooldown = await ctx.bot.redis.execute_command(
            "TTL", f"celestial:vault:{ctx.author.id}"
        )
        if user_cooldown != -2:
            hours, remainder = divmod(user_cooldown, 3600)
            minutes, seconds = divmod(remainder, 60)
            cooldown_str = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
            await ctx.send(f"You've already used the Celestial Vault today! You can use it again in {cooldown_str}.")
            return False
        return True

    return commands.check(predicate)


def is_cm():
    def predicate(ctx) -> bool:
        return (
                ctx.guild.id == ctx.bot.config.game.support_server_id
                and 491353140042530826 in [r.id for r in ctx.author.roles]
        )

    return commands.check(predicate)


def is_donator():
    async def predicate(ctx) -> bool:
        async with ctx.bot.pool.acquire() as conn:
            # Check if user is a donator (tier >= 1)
            user_tier = await conn.fetchval(
                'SELECT tier FROM profile WHERE "user"=$1;', ctx.author.id
            )
            if not user_tier or user_tier < 3:
                await ctx.send("You need to be a Ragnarok donator to use this command!")
                return False
            return True

    return commands.check(predicate)


class DecisionButton(Button):
    def __init__(self, label, *args, **kwargs):
        super().__init__(label=label, *args, **kwargs)

    async def callback(self, interaction: Interaction):
        view: DecisionView = self.view
        view.value = self.custom_id
        await interaction.response.send_message(f"You selected {self.custom_id}. Shortcut back: <#1406638032953671801>",
                                                ephemeral=True)
        view.stop()


class ShadowChampionAI:
    """AI representation of Shadow Champion - manifestation of Sepulchure's will"""
    
    def __init__(self):
        self.name = "Shadow Champion"
        self.mention = "Shadow Champion"
        self.display_name = "Shadow Champion"
        
    async def make_decision(self, champion_stats, guardians_stats, progress, followers_plans):
        """Make strategic decision based on current state and coordination"""
        await asyncio.sleep(2)  # AI "thinking" time
        
        # Analyze guardian capabilities and current state
        guardian_phase = guardians_stats.get("phase", 1)
        guardian_hp_ratio = guardians_stats["hp"] / guardians_stats["max_hp"]
        guardian_enraged = guardians_stats.get("enraged", False)
        guardian_incapacitated = guardians_stats.get("incapacitated_turns", 0) > 0
        
        # Analyze follower coordination
        follower_boost = followers_plans.get("Boost Ritual", 0)
        follower_protect = followers_plans.get("Protect Champion", 0)
        follower_heal = followers_plans.get("Heal Champion", 0)
        
        # Strategic decision making with coordination awareness
        
        # Priority 1: Survival (enhanced with follower coordination)
        if champion_stats["hp"] < champion_stats["max_hp"] * 0.25:
            if "Heal" in self.get_valid_actions(champion_stats):
                return "Heal"
            elif follower_heal > 0:
                # Trust followers to heal, focus on damage
                return "Smite"
        
        # Priority 2: Defend if vulnerable or guardian is enraged
        if (champion_stats.get("vulnerable", False) or guardian_enraged) and "Defend" in self.get_valid_actions(champion_stats):
            return "Defend"
        
        # Priority 3: Exploit guardian incapacitation
        if guardian_incapacitated:
            if progress < 80 and "Haste" in self.get_valid_actions(champion_stats) and champion_stats.get("haste_cooldown", 0) == 0:
                return "Haste"
            elif progress < 70 and "Sacrifice" in self.get_valid_actions(champion_stats) and champion_stats["hp"] > champion_stats["max_hp"] * 0.5:
                return "Sacrifice"
        
        # Priority 4: Coordinate with followers for ritual progress
        if progress < 60 and follower_boost > 0:
            # Followers are boosting ritual, we can focus on damage
            if "Haste" in self.get_valid_actions(champion_stats) and champion_stats.get("haste_cooldown", 0) == 0:
                return "Haste"
        
        # Priority 5: Strategic sacrifice when safe
        if progress < 50 and champion_stats["hp"] > champion_stats["max_hp"] * 0.7 and follower_protect > 0:
            # Followers are protecting, safe to sacrifice
            if "Sacrifice" in self.get_valid_actions(champion_stats):
                return "Sacrifice"
        
        # Priority 6: Damage output (default)
        return "Smite"
    
    def get_valid_actions(self, champion_stats):
        """Get list of valid actions based on current state"""
        actions = ["Smite", "Heal", "Defend", "Sacrifice"]
        if champion_stats.get("haste_cooldown", 0) == 0:
            actions.append("Haste")
        return actions
    
    async def announce_decision(self, ctx, decision, champion_stats, guardians_stats, progress):
        """Announce the AI's decision with strategic coordination messaging"""
        guardian_phase = guardians_stats.get("phase", 1)
        guardian_hp_ratio = guardians_stats["hp"] / guardians_stats["max_hp"]
        
        # Strategic announcements based on context
        if decision == "Smite":
            if guardian_hp_ratio < 0.3:
                announcement = "The Shadow Champion's form crackles with dark energy. 'The Guardian weakens! Now is the time to strike with all our might!'"
            elif guardian_phase > 1:
                announcement = "The Shadow Champion's form crackles with dark energy. 'Even in its evolved form, this Guardian cannot withstand the power of the void!'"
            else:
                announcement = "The Shadow Champion's form crackles with dark energy. 'I shall strike down this Guardian with the power of the void!'"
        
        elif decision == "Heal":
            announcement = "Dark tendrils of shadow wrap around the Shadow Champion. 'The shadows mend my wounds... I must survive to complete the ritual.'"
        
        elif decision == "Haste":
            announcement = "The Shadow Champion's form becomes ethereal. 'I will accelerate the ritual, though it leaves me vulnerable to the Guardian's wrath. Trust in our followers!'"
        
        elif decision == "Defend":
            if guardians_stats.get("enraged", False):
                announcement = "The Shadow Champion raises shadowy barriers. 'The Guardian's rage is palpable. I must brace myself against its fury!'"
            else:
                announcement = "The Shadow Champion raises shadowy barriers. 'I brace myself against the Guardian's assault. The ritual must continue.'"
        
        elif decision == "Sacrifice":
            announcement = "The Shadow Champion's essence flickers as dark energy flows into the ritual. 'I offer my life force to advance our cause. The ancient evil must awaken!'"
        
        else:
            announcement = "The Shadow Champion prepares for action."
        
        await ctx.send(f"👻 **{announcement}**")

class ShadowPriestAI:
    """AI representation of Shadow Priest - manifestation of Sepulchure's will"""
    
    def __init__(self):
        self.name = "Shadow Priest"
        self.mention = "Shadow Priest"
        self.display_name = "Shadow Priest"
        
    async def make_decision(self, priest_stats, champion_stats, guardians_stats, progress, followers_plans):
        """Make strategic decision based on current state and coordination"""
        await asyncio.sleep(2)  # AI "thinking" time
        
        # Analyze guardian capabilities and current state
        guardian_phase = guardians_stats.get("phase", 1)
        guardian_hp_ratio = guardians_stats["hp"] / guardians_stats["max_hp"]
        guardian_enraged = guardians_stats.get("enraged", False)
        guardian_cursed = guardians_stats.get("cursed", False)
        
        # Analyze follower coordination
        follower_empower = followers_plans.get("Empower Priest", 0)
        follower_sabotage = followers_plans.get("Sabotage Guardian", 0)
        follower_protect = followers_plans.get("Protect Champion", 0)
        
        # Strategic decision making with coordination awareness
        
        # Priority 1: Emergency champion healing
        if champion_stats["hp"] < champion_stats["max_hp"] * 0.3 and priest_stats["mana"] >= 20:
            return "Revitalize"
        
        # Priority 2: Guardian control (enhanced with follower coordination)
        if not guardian_cursed and priest_stats["mana"] >= 25:
            if guardian_enraged or guardian_phase > 1:
                # Guardian is dangerous, curse it
                return "Curse"
            elif follower_sabotage > 0:
                # Followers are sabotaging, we can focus on other priorities
                pass
            else:
                return "Curse"
        
        # Priority 3: Champion support (coordinated with followers)
        if champion_stats["hp"] < champion_stats["max_hp"] * 0.6:
            if follower_protect > 0 and priest_stats["mana"] >= 20:
                # Followers are protecting, bless for damage boost
                return "Bless"
            elif priest_stats["mana"] >= 20:
                # No follower protection, heal directly
                return "Revitalize"
        
        # Priority 4: Protection when guardian is dangerous
        if (guardian_enraged or guardian_phase > 1) and priest_stats["mana"] >= 30:
            if not champion_stats.get("barrier_active", False):
                return "Barrier"
        
        # Priority 5: Ritual progress (coordinated with followers)
        if progress < 70 and priest_stats["mana"] >= 15:
            if follower_empower > 0:
                # Followers are empowering us, channel for maximum effect
                return "Channel"
            elif progress < 50:
                # Early ritual, focus on progress
                return "Channel"
        
        # Priority 6: Bless for damage boost when safe
        if champion_stats["hp"] > champion_stats["max_hp"] * 0.7 and priest_stats["mana"] >= 20:
            return "Bless"
        
        # Default: regenerate mana
        return None
    
    def get_valid_actions(self, priest_stats):
        """Get list of valid actions based on current state"""
        actions = []
        if priest_stats["mana"] >= 20:
            actions.extend(["Bless", "Revitalize"])
        if priest_stats["mana"] >= 25:
            actions.append("Curse")
        if priest_stats["mana"] >= 30:
            actions.append("Barrier")
        if priest_stats["mana"] >= 15:
            actions.append("Channel")
        return actions
    
    async def announce_decision(self, ctx, decision, priest_stats, champion_stats, guardians_stats, progress):
        """Announce the AI's decision with strategic coordination messaging"""
        guardian_phase = guardians_stats.get("phase", 1)
        guardian_enraged = guardians_stats.get("enraged", False)
        
        # Strategic announcements based on context
        if decision == "Bless":
            if guardian_phase > 1:
                announcement = "The Shadow Priest's eyes glow with ancient knowledge. 'I channel the dark energies to empower our Champion against this evolved Guardian!'"
            else:
                announcement = "The Shadow Priest's eyes glow with ancient knowledge. 'I channel the dark energies to empower our Champion!'"
        
        elif decision == "Barrier":
            if guardian_enraged:
                announcement = "Mystical runes materialize around the Shadow Priest. 'A barrier of shadow shall protect our Champion from the Guardian's fury!'"
            else:
                announcement = "Mystical runes materialize around the Shadow Priest. 'A barrier of shadow shall protect our Champion from harm.'"
        
        elif decision == "Curse":
            if guardian_phase > 1:
                announcement = "The Shadow Priest's voice echoes with malevolent power. 'I cast a curse upon this evolved Guardian, weakening its resolve!'"
            elif guardian_enraged:
                announcement = "The Shadow Priest's voice echoes with malevolent power. 'I cast a curse upon the enraged Guardian, calming its fury!'"
            else:
                announcement = "The Shadow Priest's voice echoes with malevolent power. 'I cast a curse upon the Guardian, weakening its resolve!'"
        
        elif decision == "Revitalize":
            announcement = "Dark healing energies flow from the Shadow Priest. 'I mend the Champion's wounds with the power of the void.'"
        
        elif decision == "Channel":
            announcement = "The Shadow Priest's form pulses with ritual energy. 'I channel the collective will of the faithful to advance the ritual!'"
        
        else:
            announcement = "The Shadow Priest meditates, gathering mystical energy for the next phase."
        
        await ctx.send(f"🔮 **{announcement}**")


class DecisionView(View):
    def __init__(self, player, options, timeout=60):
        super().__init__(timeout=timeout)
        self.player = player
        self.value = None
        for option in options:
            self.add_item(DecisionButton(style=ButtonStyle.primary, label=option, custom_id=option))

    async def interaction_check(self, interaction: Interaction) -> bool:
        return interaction.user == self.player


class Raid(commands.Cog):
    """Raids are only available in the support server. Use the support command for an invite link."""

    def __init__(self, bot):
        self.bot = bot
        self.raid = {}
        self.toggle_list = set()  # Use a set for efficient membership checking
        self.chaoslist = []

        self.joined = []
        self.raidactive = False
        self.active_view = None
        self.raid_preparation = False
        self.boss = None
        self.celestial_elements = {}
        self.allow_sending = discord.PermissionOverwrite(
            send_messages=True, read_messages=True
        )
        self.deny_sending = discord.PermissionOverwrite(
            send_messages=False, read_messages=True
        )
        self.read_only = discord.PermissionOverwrite(
            send_messages=False, read_messages=True
        )

        self.auto_raid_check.start()


    def cog_unload(self):

        self.auto_raid_check.cancel()

    def getfinaldmg(self, damage: Decimal, defense):
        return v if (v := damage - defense) > 0 else 0

    async def set_raid_timer(self):
        await self.bot.redis.execute_command(
            "SET",
            "special:raid",
            "running",  # ctx isn't available
            "EX",
            3600,  # signup period + time until timeout
        )

    async def clear_raid_timer(self):
        await self.bot.redis.execute_command("DEL", "special:raid")

    @is_gm()
    @commands.command(hidden=True)
    async def gmclearraid(self, ctx):
        await self.bot.redis.execute_command("DEL", "special:raid")
        await ctx.send("Raid timer cleared!")
        
    @is_gm()
    @commands.command(hidden=True)
    async def reset_celestial_vault(self, ctx, user_id: int = None):
        """[Bot Admin only] Reset the Celestial Vault cooldown for a user."""
        user_id = user_id or ctx.author.id
        await self.bot.redis.execute_command("DEL", f"celestial:vault:{user_id}")
        await ctx.send(f"Celestial Vault cooldown has been reset for user ID: {user_id}!")

    @is_gm()
    @commands.command(hidden=True)
    async def alterraid(self, ctx, newhp: IntGreaterThan(0)):
        """[Bot Admin only] Change a raid boss' HP."""
        if not self.boss:
            return await ctx.send("No Boss active!")
        self.boss.update(hp=newhp, initial_hp=newhp)
        try:
            spawnmsg = await ctx.channel.fetch_message(self.boss["message"])
            edited_embed = spawnmsg.embeds[0]
            edited_embed.description = re.sub(
                r"\d+(,*\d)+ HP", f"{newhp:,.0f} HP", edited_embed.description
            )
            edited_embed.set_image(url="attachment://dragon.webp")
            await spawnmsg.edit(embed=edited_embed)
        except discord.NotFound:
            return await ctx.send("Could not edit Boss HP!")
        await ctx.send("Boss HP updated!")


    @tasks.loop(minutes=30)
    async def auto_raid_check(self):
        """Check if a raid needs to be spawned and spawn it if needed."""
        try:
            await self.bot.wait_until_ready()
            
            # Debug channel for logging
            channeldebug = self.bot.get_channel(1444392570280087755)
            if channeldebug:
                await channeldebug.send("Auto raid check starting...")
            
            # Check if a raid is already active
            if hasattr(self, 'raidactive') and self.raidactive:
                if channeldebug:
                    await channeldebug.send("Raid already active, skipping auto-spawn.")
                return
            
            # Get the target channel
            channel_id = 1406295072332451901
            channel = self.bot.get_channel(channel_id)
            
            if not channel:
                if channeldebug:
                    await channeldebug.send(f"Auto raid check: Channel with ID {channel_id} not found")
                return
            
            # Get the last message in the channel
            last_message = None
            last_spawn_time = None
            async for message in channel.history(limit=1):
                last_message = message
                last_spawn_time = message.created_at
                break
            
            # Use timezone-aware current time (use this method for discord.py)
            from discord.utils import utcnow
            current_time = utcnow()

            channeldebug = self.bot.get_channel(1444392570280087755)
            if channeldebug:
                await channeldebug.send(f"Auto raid check: Checking Channel (last spawn: {last_spawn_time})")
            
            # If no spawn found or it's been 8+ hours since the last spawn
            min_hours = 8
            min_seconds = min_hours * 3600
            
            if not last_spawn_time or (current_time - last_spawn_time).total_seconds() >= min_seconds:
                if channeldebug:
                    await channeldebug.send(f"Auto raid check: Spawning raid (last spawn: {last_spawn_time})")
                
                # Generate random parameters
                random_hp = random.randint(1000000, 2500000)
                crate_choices = ["divine", "fortune", "legendary", "materials"]
                random_crate = random.choice(crate_choices)
                
                # Auto-spawn the raid
                await self.auto_spawn_raid(channel, random_hp, random_crate)
            else:
                time_diff = (current_time - last_spawn_time).total_seconds() / 3600
                if channeldebug:
                    await channeldebug.send(f"Auto raid check: Raid was spawned {time_diff:.1f} hours ago, waiting until at least 8 hours have passed")
        except Exception as e:
            channeldebug = self.bot.get_channel(1444392570280087755)
            await channeldebug.send(e)

    async def auto_spawn_raid(self, channel, hp, rarity="magic", raid_hp=17776):
        """Auto-spawn a raid without decorator checks."""
        try:
            if rarity not in ["magic", "legendary", "rare", "uncommon", "common", "mystery", "fortune", "divine"]:
                raise ValueError("Invalid rarity specified.")
            channeldebug = self.bot.get_channel(1444392570280087755)
            channeldebug.send(f"Auto-spawning Ragnarok raid with {hp:,} HP and {rarity} crate")
            
            # Get guild from channel
            guild = channel.guild
            
            await self.set_raid_timer()
            survival_used = set()

            self.boss = {"hp": hp, "initial_hp": hp, "min_dmg": 50, "max_dmg": 1500}
            self.joined = []

            # Create embed
            fi = discord.File("assets/other/startdragon.webp")
            em = discord.Embed(
                title="Ragnarok Spawned",
                description=(
                    f"This boss has {self.boss['hp']:,.0f} HP and has high-end loot!\nThe"
                    " Ragnarok will be vulnerable in 15 Minutes!"
                    f" Raiders HP: {'Standard' if raid_hp == 17776 else raid_hp}"
                ),
                color=self.bot.config.game.primary_colour,
            )

            em.set_image(url="attachment://startdragon.webp")
            # Use bot avatar instead of author
            em.set_thumbnail(url=self.bot.user.display_avatar.url)
            
            # Create button view
            view = JoinView(
                Button(style=ButtonStyle.primary, label="Join the raid!"),
                message=_("You joined the raid."),
                timeout=60 * 15,
            )
            
            fi_path = "assets/other/startdragon.webp"
            try:
                channels_ids = [1406295072332451901, ]
                message_ids = []
                raid_channel = None  # Store the main channel for permissions later

                for channel_id in channels_ids:
                    try:
                        current_channel = self.bot.get_channel(channel_id)
                        if current_channel:
                            if channel_id == 1406295072332451901:  # Main raid channel
                                raid_channel = current_channel
                                
                            fi = discord.File(fi_path)
                            sent_msg = await current_channel.send(embed=em, file=fi, view=view)
                            message_ids.append(sent_msg.id)
                        else:
                            channeldebug = self.bot.get_channel(1444392570280087755)
                            channeldebug.send(f"Channel with ID {channel_id} not found.")
                    except Exception as e:
                        channeldebug = self.bot.get_channel(1444392570280087755)
                        error_message = f"Error in channel with ID {channel_id}: {e}. continuing.."
                        channeldebug.send(error_message)
                        continue

                self.boss.update(message=message_ids)
                self.raidactive = True
                self.raid_preparation = True

                if self.bot.config.bot.is_beta:
                    summary_channel = self.bot.get_channel(1199299514490683392)

                    message_ids = []  # To store the IDs of the sent messages

                    for channel_id in channels_ids:
                        try:
                            current_channel = self.bot.get_channel(channel_id)
                            if current_channel:
                                role_id = 1404804032643731467 # Replace with the actual role ID
                                role = discord.utils.get(guild.roles, id=role_id)
                                content = f"{role.mention} Ragnarok spawned! 15 Minutes until he is vulnerable..."
                                sent_msg = await current_channel.send(content, allowed_mentions=discord.AllowedMentions(roles=True))
                                message_ids.append(sent_msg.id)
                        except Exception as e:
                            error_message = f"Error in channel with ID {channel_id}: {e}. continuing.."
                            print(error_message)
                            continue

                    self.boss.update(message=message_ids)

                    # Countdown messages
                    time_intervals = [300, 300, 180, 60, 30, 20, 10]
                    #time_intervals = [20, 10]
                    messages = ["**Ragnarok will be vulnerable in 10 minutes**",
                                "**Ragnarok will be vulnerable in 5 minutes**",
                                "**Ragnarok will be vulnerable in 2 minutes**",
                                "**Ragnarok will be vulnerable in 1 minute**",
                                "**Ragnarok will be vulnerable in 30 seconds**",
                                "**Ragnarok will be vulnerable in 20 seconds**",
                                "**Ragnarok will be vulnerable in 10 seconds**"]

                    for interval, message in zip(time_intervals, messages):
                        await asyncio.sleep(interval)
                        for channel_id in channels_ids:
                            try:
                                current_channel = self.bot.get_channel(channel_id)
                                if current_channel:
                                    await current_channel.send(message)
                            except Exception as e:
                                error_message = f"Error in channel with ID {channel_id}: {e}. continuing.."
                                print(error_message)
                                continue
            except Exception as e:
                error_message = f"Unexpected error: {e}"
                print(error_message)
                if channel:
                    await channel.send(error_message)
                self.raidactive = False
                return

            view.stop()

            for channel_id in channels_ids:
                current_channel = self.bot.get_channel(channel_id)
                if current_channel:
                    await current_channel.send("**Ragnarok is vulnerable! Fetching participant data... Hang on!**")

            self.joined.extend(view.joined)
            # Assuming you have the role ID for the server booster role
            BOOSTER_ROLE_ID = 1404858099268849816 # Replace with your actual booster role ID

            # Define the tier threshold and the user ID to exclude
            tier_threshold = 1  # Assuming you want tiers >= 1
            excluded_user_ids = [782017044828782642, 579703576570494976, 761469900853215263, 1322593504098254959, 782017044828782642]

            # Fetch Discord IDs where tier is >= tier_threshold and user is not in excluded_user_ids
            discord_ids = await self.bot.pool.fetch(
                '''
                SELECT "user" 
                FROM profile 
                WHERE "tier" >= $1 
                AND "user" != ALL($2);
                ''',
                tier_threshold,
                excluded_user_ids
            )

            # Extract the IDs from the result and append them to a list
            user_ids_list = [record['user'] for record in discord_ids]

            # Get User objects for each user ID, handling cases where a user may not be found
            users = [self.bot.get_user(user_id) or await self.bot.fetch_user(user_id) for user_id in user_ids_list]

            # Append the User objects to your existing list (e.g., self.joined)
            self.joined.extend(users)

            # Fetch members with the server booster role
            guild = self.bot.get_guild(1402911850802315336)  # Replace YOUR_GUILD_ID with your server's ID
            if guild:
                booster_role = guild.get_role(BOOSTER_ROLE_ID)
                if booster_role:
                    # Fetch all members with the server booster role
                    booster_members = [member for member in guild.members if booster_role in member.roles]
                    # Append these members to self.joined
                    self.joined.extend(booster_members)

            async with self.bot.pool.acquire() as conn:
                for u in self.joined:
                    profile = await conn.fetchrow('SELECT * FROM profile WHERE "user"=$1;', u.id)
                    if not profile:
                        # You might want to send a message or log that the profile wasn't found.
                        continue
                    dmg, deff = await self.bot.get_raidstats(
                        u,
                        atkmultiply=profile["atkmultiply"],
                        defmultiply=profile["defmultiply"],
                        classes=profile["class"],
                        race=profile["race"],
                        guild=profile["guild"],
                        conn=conn,
                    )
                    if raid_hp == 17776:
                        stathp = profile["stathp"] * 50
                        level = rpgtools.xptolevel(profile["xp"])
                        raidhp = profile["health"] + 200 + (level * 15) + stathp
                    else:
                        raidhp = raid_hp
                    self.raid[(u, "user")] = {"hp": raidhp, "armor": deff, "damage": dmg}

            raiders_joined = len(self.raid)  # Replace with your actual channel IDs

            # Final message with gathered data
            for channel_id in channels_ids:
                current_channel = self.bot.get_channel(channel_id)
                if current_channel:
                    await current_channel.send(f"**Done getting data! {raiders_joined} Raiders joined.**")

            start = datetime.datetime.utcnow()

            while (
                    self.boss["hp"] > 0
                    and len(self.raid) > 0
                    and datetime.datetime.utcnow() < start + datetime.timedelta(minutes=60)
            ):
                (target, participant_type) = random.choice(list(self.raid.keys()))
                dmg = random.randint(self.boss["min_dmg"], self.boss["max_dmg"])
                finaldmg = self.getfinaldmg(dmg, self.raid[(target, participant_type)]["armor"])
                self.raid[(target, participant_type)]["hp"] -= finaldmg

                em = discord.Embed(title="Ragnarok attacked!", colour=0xFFB900)

                if self.raid[(target, participant_type)]["hp"] > 0:  # If target is still alive
                    description = f"{target.mention if participant_type == 'user' else target} now has {self.raid[(target, participant_type)]['hp']} HP!"
                    em.description = description
                    em.add_field(name="Theoretical Damage",
                                value=finaldmg + self.raid[(target, participant_type)]["armor"])
                    em.add_field(name="Shield", value=self.raid[(target, participant_type)]["armor"])
                    em.add_field(name="Effective Damage", value=finaldmg)
                else:  # If target has died
                    # Check if target is a Raider and hasn't used their survival
                    if self.raid[(target, participant_type)]["hp"] <= 0:  # Changed from else to explicit check
                        # Check if target is a Raider and hasn't used their survival
                        survived = False  # Add this flag
                        if participant_type == "user" and target.id not in survival_used:
                            # Check if they're a Raider
                            async with self.bot.pool.acquire() as conn:
                                profile = await conn.fetchrow('SELECT class FROM profile WHERE "user"=$1;', target.id)
                                if profile and profile['class']:
                                    raider_classes = {"Adventurer", "Swordsman", "Fighter", "Swashbuckler",
                                                    "Dragonslayer",
                                                    "Raider", "Eternal Hero"}

                                    is_raider = bool(set(profile['class']) & raider_classes)

                                    if is_raider:
                                        self.raid[(target, participant_type)]["hp"] = 1
                                        survival_used.add(target.id)
                                        description = f"💫 {target.mention}'s Raider instincts allowed them to survive with 1 HP!"
                                        em.description = description
                                        em.add_field(name="Theoretical Damage",
                                                    value=finaldmg + self.raid[(target, participant_type)]["armor"])
                                        em.add_field(name="Shield",
                                                    value=self.raid[(target, participant_type)]["armor"])
                                        em.add_field(name="Effective Damage", value=finaldmg)
                                        survived = True  # Set the flag

                        # Only handle death if they didn't survive
                        if not survived:
                            description = f"{target.mention if participant_type == 'user' else target} died!"
                            em.description = description
                            em.add_field(name="Theoretical Damage",
                                        value=finaldmg + self.raid[(target, participant_type)]["armor"])
                            em.add_field(name="Shield", value=self.raid[(target, participant_type)]["armor"])
                            em.add_field(name="Effective Damage", value=finaldmg)
                            del self.raid[(target, participant_type)]

                if participant_type == "user":
                    em.set_author(name=str(target), icon_url=target.display_avatar.url)
                else:  # For bots
                    em.set_author(name=str(target))
                em.set_thumbnail(url=f"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_dragonattack.webp")
                for channel_id in channels_ids:
                    current_channel = self.bot.get_channel(channel_id)
                    if current_channel:
                        await current_channel.send(embed=em)

                dmg_to_take = sum(i["damage"] for i in self.raid.values())
                self.boss["hp"] -= dmg_to_take
                await asyncio.sleep(4)

                em = discord.Embed(title="The raid attacked Ragnarok!", colour=0xFF5C00)
                em.set_thumbnail(url=f"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_attackdragon.webp")
                em.add_field(name="Damage", value=dmg_to_take)

                if self.boss["hp"] > 0:
                    em.add_field(name="HP left", value=self.boss["hp"])
                else:
                    em.add_field(name="HP left", value="Dead!")
                for channel_id in channels_ids:
                    current_channel = self.bot.get_channel(channel_id)
                    if current_channel:
                        await current_channel.send(embed=em)
                await asyncio.sleep(4)

            # Create a mock context for functions requiring it
            class MockContext:
                def __init__(self, bot, channel, guild):
                    self.bot = bot
                    self.channel = channel
                    self.guild = guild
                    self.message = None  # May need to be mocked further if used
                    
            mock_ctx = MockContext(self.bot, raid_channel, guild)

            if len(self.raid) == 0:
                for channel_id in channels_ids:
                    current_channel = self.bot.get_channel(channel_id)
                    if current_channel:
                        m = await current_channel.send("The raid was all wiped!")
                        await m.add_reaction("\U0001F1EB")

                summary_text = (
                    "Emoji_here The raid was all wiped! Ragnarok had"
                    f" **{self.boss['hp']:,.3f}** health remaining. Better luck next time."
                )
                try:
                    summary = (
                        "**Raid result:**\n"
                        f"Emoji_here Health: **{self.boss['initial_hp']:,.0f}**\n"
                        f"{summary_text}\n"
                        f"Emoji_here Raiders joined: **{raiders_joined}**"
                    )
                    summary = summary.replace(
                        "Emoji_here",
                        ":small_blue_diamond:" if self.boss["hp"] < 1 else ":vibration_mode:"
                    )
                    summary_channel = self.bot.get_channel(1408139518585864193)

                    summary_msg = await summary_channel.send(summary)
                    self.raid.clear()
                    await self.clear_raid_timer()

                except Exception as e:
                    print(f"An error has occurred: {e}")
                    if raid_channel:
                        await raid_channel.send(f"An error has occurred: {e}")
            elif self.boss["hp"] < 1:
                raid_duration = datetime.datetime.utcnow() - start
                minutes = (raid_duration.seconds % 3600) // 60
                seconds = raid_duration.seconds % 60
                summary_duration = f"{minutes} minutes, {seconds} seconds"

                # Set permissions for the raid channel
                if raid_channel:
                    try:
                        await raid_channel.set_permissions(
                            guild.default_role,
                            overwrite=self.allow_sending,
                        )
                    except Exception as e:
                        print(f"Error setting permissions: {e}")

                highest_bid = [
                    1403785403651063909,
                    0,
                ]  # userid, amount

                bots = sum(1 for _, p_type in self.raid.keys() if p_type == "bot")

                self.raid = {k: v for k, v in self.raid.items() if k[1] == "user"}

                raid_user_ids = [k[0].id for k, v in self.raid.items() if k[1] == 'user']

                def check(msg):
                    try:
                        val = int(msg.content)
                    except ValueError:
                        return False
                    if not raid_channel or msg.channel.id != raid_channel.id or not any(msg.author == k[0] for k in self.raid.keys()):
                        return False
                    if highest_bid[1] == 0:  # Allow starting bid to be $1
                        if val < 1:
                            return False
                        else:
                            return True
                    if val > highest_bid[1]:
                        if highest_bid[1] < 100:
                            return True
                    if val < int(highest_bid[1] * 1.1):  # Minimum bid is 10% higher than the highest bid
                        return False
                    if (
                            msg.author.id == highest_bid[0]
                    ):  # don't allow a player to outbid themselves
                        return False
                    return True

                # If there are no users left in the raid, skip the bidding
                if not self.raid:
                    for channel_id in channels_ids:
                        current_channel = self.bot.get_channel(channel_id)
                        if current_channel:
                            await current_channel.send(f"No survivors left to bid on the {rarity} Crate!")
                    summary_text = (
                        f"Emoji_here Defeated in: **{summary_duration}**\n"
                        f"Emoji_here Survivors: **0 players and {bots} of Drakath's forces**"
                    )
                else:
                    page = commands.Paginator()
                    for u in self.raid.keys():
                        page.add_line(u[0].mention)

                    emote_for_rarity = getattr(self.bot.cogs['Crates'].emotes, rarity)
                    page.add_line(
                        f"The raid killed the boss!\nHe was guarding a {emote_for_rarity} {rarity.capitalize()} Crate!\n"
                        "The highest bid for it wins <:roopiratef:1146234370827505686>\nSimply type how much you bid!"
                    )

                    # Assuming page.pages is a list of pages
                    for channel_id in channels_ids:
                        current_channel = self.bot.get_channel(channel_id)
                        if current_channel:
                            for p in page.pages:
                                await current_channel.send(p[4:-4])

                    while True:
                        try:
                            msg = await self.bot.wait_for("message", timeout=60, check=check)
                        except asyncio.TimeoutError:
                            break
                        bid = int(msg.content)
                        current_bidder = msg.author.id
                        previous_bidder, previous_amount = highest_bid

                        async with self.bot.pool.acquire() as conn:
                            async with conn.transaction():
                                # Check if current bidder has enough money
                                current_balance = await conn.fetchval(
                                    'SELECT money FROM profile WHERE "user" = $1;', current_bidder
                                )
                                if current_balance < bid:
                                    await msg.channel.send(
                                        f"{msg.author.mention} You don't have enough money to place this bid."
                                    )
                                    continue

                                # Check if current bidder is already the highest bidder
                                if current_bidder == previous_bidder:
                                    await msg.channel.send(
                                        f"{msg.author.mention} You already have the highest bid."
                                    )
                                    continue

                                # Refund previous bidder if exists
                                if previous_amount > 0:
                                    await conn.execute(
                                        'UPDATE profile SET money = money + $1 WHERE "user" = $2;',
                                        previous_amount,
                                        previous_bidder,
                                    )

                                # Deduct new bid from current bidder
                                await conn.execute(
                                    'UPDATE profile SET money = money - $1 WHERE "user" = $2;',
                                    bid,
                                    current_bidder,
                                )

                        # Update highest bid OUTSIDE the database transaction
                        highest_bid = [current_bidder, bid]

                        # Notify all channels
                        next_bid = int(bid * 1.1) if bid >= 100 else None
                        for channel_id in channels_ids:
                            current_channel = self.bot.get_channel(channel_id)
                            if current_channel:
                                if next_bid is not None:
                                    content = f"{msg.author.mention} bids **${bid}**!\nThe minimum next bid is **${next_bid}**."
                                else:
                                    content = f"{msg.author.mention} bids **${bid}**!"
                                await current_channel.send(content)

                    msg_content = (
                        f"Auction done! Winner is <@{highest_bid[0]}> with"
                        f" **${highest_bid[1]}**!\nGiving {rarity.capitalize()} Crate... Done!"
                    )
                    summary_crate = (
                        f"Emoji_here {rarity.capitalize()} crate {emote_for_rarity} "
                        f"sold to: **<@{highest_bid[0]}>** for **${highest_bid[1]:,.0f}**"
                    )

                    # Assign the crate to the winner without deducting money again
                    column_name = f"crates_{rarity}"
                    async with self.bot.pool.acquire() as conn:
                        await conn.execute(
                            f'UPDATE profile SET "{column_name}"="{column_name}"+1 WHERE "user"=$1;',
                            highest_bid[0],
                        )


                    # Send the result to all channels
                    for channel_id in channels_ids:
                        current_channel = self.bot.get_channel(channel_id)
                        if current_channel:
                            await current_channel.send(msg_content)

                    cash_pool = hp * 0.9
                    survivors = len(self.raid)
                    self.raid = {(user, p_type): data for (user, p_type), data in self.raid.items() if
                                p_type == "user" and not user.bot}
                    base_cash = int(cash_pool / survivors)  # This is our base reward

                    # Send the base cash to all survivors first
                    users = [user.id for user, p_type in self.raid.keys() if p_type == "user"]
                    await self.bot.pool.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=ANY($2);',
                        base_cash,
                        users
                    )

                    # Process each survivor for potential Raider bonus
                    for (user, p_type) in list(
                            self.raid.keys()):  # Use list() to avoid runtime changes issues
                        async with self.bot.pool.acquire() as conn:
                            profile = await conn.fetchrow('SELECT class FROM profile WHERE "user"=$1;',
                                                        user.id)
                            bonus_multiplier = 0  # Initialize bonus multiplier

                            if profile and profile['class']:
                                # Define Raider classes and their corresponding bonuses
                                raider_classes = {
                                    "Adventurer": 0.05,  # 5% bonus
                                    "Swordsman": 0.10,  # 10% bonus
                                    "Fighter": 0.15,  # 15% bonus
                                    "Swashbuckler": 0.20,  # 20% bonus
                                    "Dragonslayer": 0.25,  # 25% bonus
                                    "Raider": 0.30,  # 30% bonus
                                    "Eternal Hero": 0.40  # 40% bonus
                                }

                                # Determine the highest applicable bonus
                                for class_name in profile['class']:
                                    if class_name in raider_classes:
                                        class_bonus = raider_classes[class_name]
                                        bonus_multiplier = max(bonus_multiplier, class_bonus)

                                if bonus_multiplier > 0:
                                    bonus_amount = int(base_cash * bonus_multiplier)
                                    await conn.execute(
                                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                                        bonus_amount,
                                        user.id
                                    )
                                    # Announce bonus if there was one
                                    for channel_id in channels_ids:
                                        current_channel = self.bot.get_channel(channel_id)
                                        if current_channel:
                                            await current_channel.send(
                                                f"💰 {user.mention}'s Raider abilities earned them an extra ${bonus_amount:,.0f}!"
                                            )

                    # Send the final message to all channels
                    for channel_id in channels_ids:
                        current_channel = self.bot.get_channel(channel_id)
                        if current_channel:
                            await current_channel.send(
                                f"**Gave ${base_cash:,.0f} of Ragnarok's ${cash_pool:,.0f} drop to all survivors!**")

                        summary_text = (
                            f"Emoji_here Defeated in: **{summary_duration}**\n"
                            f"{summary_crate}\n"
                            f"Emoji_here Payout per survivor: **${base_cash:,.0f}**\n"
                            f"Emoji_here Survivors: **{survivors} and {bots} of placeholders forces**"
                        )

            if self.boss["hp"] > 1:
                for channel_id in channels_ids:
                    current_channel = self.bot.get_channel(channel_id)
                    if current_channel:
                        m = await current_channel.send(
                            "The raid did not manage to kill Ragnarok within an hour... He disappeared!")
                        await m.add_reaction("\U0001F1EB")
                        summary = (
                            f"The raid did not manage to kill Ragnarok within an hour... He disappeared with **{self.boss['hp']:,.0f}** health remaining."
                        )

            if 'users' in locals() and users:  # Check if users list exists and is not empty
                random_user_id = random.choice(users)
                success = True
                self.bot.dispatch("raid_completion", mock_ctx, success, random_user_id)
            
            await asyncio.sleep(30)
            
            # Update permissions on the raid channel
            if raid_channel:
                try:
                    await raid_channel.set_permissions(guild.default_role, overwrite=self.deny_sending)
                except Exception as e:
                    print(f"Error setting permissions: {e}")
                    
            await self.clear_raid_timer()
            try:
                self.raid.clear()
            except Exception as e:
                print(f"An error occurred: {e}")
                if raid_channel:
                    await raid_channel.send(f"An error occurred: {e}")

            if self.boss["hp"] < 1 and self.bot.config.bot.is_beta:
                summary = (
                    "**Raid result:**\n"
                    f"Emoji_here Health: **{self.boss['initial_hp']:,.0f}**\n"
                    f"{summary_text}\n"
                    f"Emoji_here Raiders joined: **{raiders_joined}**"
                )
                summary = summary.replace(
                    "Emoji_here",
                    ":small_blue_diamond:" if self.boss["hp"] < 1 else ":vibration_mode:"
                )
                
            summary_channel = self.bot.get_channel(1408139518585864193)
            if summary_channel and 'summary' in locals():
                await summary_channel.send(summary)

            try:
                self.raid.clear()
            except Exception as e:
                print(f"An error occurred: {e}")
                
            self.raid_preparation = False
            self.raidactive = False
            self.boss = None
        except Exception as e:
            import traceback
            current_channel = self.bot.get_channel(1444392570280087755)
            error_message = f"Error in auto_spawn_raid: {e}\n"
            error_message += traceback.format_exc()
            await current_channel.send(error_message)
            print(error_message)
            if current_channel:
                await current_channel.send(f"Error in auto raid: {e}")




    @is_gm()
    @raid_channel()
    @raid_free()
    @commands.command(hidden=True, brief=_("Start a Ragnorak raid"))
    async def spawn(self, ctx, hp: IntGreaterThan(0), rarity: str = "magic", raid_hp: int = 17776):
        try:
            if rarity not in ["magic", "legendary", "rare", "uncommon", "common", "mystery", "fortune", "divine"]:
                raise ValueError("Invalid rarity specified.")
            # rest of your function

            """[Bot Admin only] Starts a raid."""
            await ctx.message.delete()
            await self.set_raid_timer()
            survival_used = set()

            self.boss = {"hp": hp, "initial_hp": hp, "min_dmg": 50, "max_dmg": 1500}
            self.joined = []

            # await ctx.channel.set_permissions(
            # ctx.guild.default_role,
            # overwrite=self.read_only,
            # )

            fi = discord.File("assets/other/startdragon.webp")
            em = discord.Embed(
                title="Ragnarok Spawned",
                description=(
                    f"This boss has {self.boss['hp']:,.0f} HP and has high-end loot!\nThe"
                    " Ragnarok will be vulnerable in 15 Minutes!"
                    f" Raiders HP: {'Standard' if raid_hp == 17776 else raid_hp}"
                ),
                color=self.bot.config.game.primary_colour,
            )

            em.set_image(url="attachment://startdragon.webp")
            em.set_thumbnail(url=ctx.author.display_avatar.url)

            view = JoinView(
                Button(style=ButtonStyle.primary, label="Join the raid!"),
                message=_("You joined the raid."),
                timeout=60 * 15,
            )
            fi_path = "assets/other/startdragon.webp"
            try:
                channels_ids = [1140211789573935164, 1406295072332451901,
                                1158743317325041754]  # Replace with your actual channel IDs

                message_ids = []  # To store the IDs of the sent messages

                for channel_id in channels_ids:
                    try:
                        channel = self.bot.get_channel(channel_id)  # Assumes ctx.guild is available
                        if channel:
                            fi = File(fi_path)  # Create a new File instance for each channel
                            sent_msg = await channel.send(embed=em, file=fi, view=view)
                            message_ids.append(sent_msg.id)
                        else:
                            await ctx.send(f"Channel with ID {channel_id} not found.")
                    except Exception as e:
                        error_message = f"Error in channel with ID {channel_id}: {e}. continuing.."
                        await ctx.send(error_message)
                        print(error_message)
                        continue

                self.boss.update(message=message_ids)

                if self.bot.config.bot.is_beta:
                    summary_channel = self.bot.get_channel(1408139518585864193)

                    channels_ids = [1406295072332451901]  # Replace with your actual channel IDs
                    message_ids = []  # To store the IDs of the sent messages

                    for channel_id in channels_ids:
                        try:
                            channel = self.bot.get_channel(channel_id)  # Assumes ctx.guild is available
                            if channel:
                                role_id = 1404804032643731467 # Replace with the actual role ID
                                role = discord.utils.get(ctx.guild.roles, id=role_id)
                                content = f"{role.mention} Ragnarok spawned! 15 Minutes until he is vulnerable..."
                                sent_msg = await channel.send(content, allowed_mentions=discord.AllowedMentions(roles=True))
                                message_ids.append(sent_msg.id)
                        except Exception as e:
                            error_message = f"Error in channel with ID {channel_id}: {e}. continuing.."
                            await ctx.send(error_message)
                            print(error_message)
                            continue

                    self.boss.update(message=message_ids)
                    self.raid_preparation = True
                    self.raidactive = True

                    # Countdown messages
                    time_intervals = [300, 300, 180, 60, 30, 20, 10]
                    messages = ["**Ragnarok will be vulnerable in 10 minutes**",
                                "**Ragnarok will be vulnerable in 5 minutes**",
                                "**Ragnarok will be vulnerable in 2 minutes**",
                                "**Ragnarok will be vulnerable in 1 minute**",
                                "**Ragnarok will be vulnerable in 30 seconds**",
                                "**Ragnarok will be vulnerable in 20 seconds**",
                                "**Ragnarok will be vulnerable in 10 seconds**"]

                    for interval, message in zip(time_intervals, messages):
                        await asyncio.sleep(interval)
                        for channel_id in channels_ids:
                            try:
                                channel = self.bot.get_channel(channel_id)
                                if channel:
                                    await channel.send(message)
                            except Exception as e:
                                error_message = f"Error in channel with ID {channel_id}: {e}. continuing.."
                                await ctx.send(error_message)
                                print(error_message)
                                continue
            except Exception as e:
                error_message = f"Unexpected error: {e}"
                await ctx.send(error_message)
                print(error_message)

                self.raidactive = False

            view.stop()

            for channel_id in channels_ids:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    await channel.send("**Ragnarok is vulnerable! Fetching participant data... Hang on!**")

            self.joined.extend(view.joined)
            # Assuming you have the role ID for the server booster role
            BOOSTER_ROLE_ID = 1404858099268849816 # Replace with your actual booster role ID

            # Define the tier threshold and the user ID to exclude
            tier_threshold = 1  # Assuming you want tiers >= 1
            excluded_user_ids = [782017044828782642, 579703576570494976, 761469900853215263, 1322593504098254959, 1139261878065959012]

            # Fetch Discord IDs where tier is >= tier_threshold and user is not in excluded_user_ids
            discord_ids = await self.bot.pool.fetch(
                '''
                SELECT "user" 
                FROM profile 
                WHERE "tier" >= $1 
                  AND "user" != ALL($2);
                ''',
                tier_threshold,
                excluded_user_ids
            )

            # Extract the IDs from the result and append them to a list
            user_ids_list = [record['user'] for record in discord_ids]

            # Get User objects for each user ID, handling cases where a user may not be found
            users = [self.bot.get_user(user_id) or await self.bot.fetch_user(user_id) for user_id in user_ids_list]

            # Append the User objects to your existing list (e.g., self.joined)
            self.joined.extend(users)

            # Fetch members with the server booster role
            guild = self.bot.get_guild(1402911850802315336)  # Replace YOUR_GUILD_ID with your server's ID
            if guild:
                booster_role = guild.get_role(BOOSTER_ROLE_ID)
                if booster_role:
                    # Fetch all members with the server booster role
                    booster_members = [member for member in guild.members if booster_role in member.roles]
                    # Append these members to self.joined
                    self.joined.extend(booster_members)

            async with self.bot.pool.acquire() as conn:
                for u in self.joined:
                    profile = await conn.fetchrow('SELECT * FROM profile WHERE "user"=$1;', u.id)
                    if not profile:
                        # You might want to send a message or log that the profile wasn't found.
                        continue
                    dmg, deff = await self.bot.get_raidstats(
                        u,
                        atkmultiply=profile["atkmultiply"],
                        defmultiply=profile["defmultiply"],
                        classes=profile["class"],
                        race=profile["race"],
                        guild=profile["guild"],
                        conn=conn,
                    )
                    if raid_hp == 17776:
                        stathp = profile["stathp"] * 50
                        level = rpgtools.xptolevel(profile["xp"])
                        raidhp = profile["health"] + 200 + (level * 15) + stathp
                    else:
                        raidhp = raid_hp
                    self.raid[(u, "user")] = {"hp": raidhp, "armor": deff, "damage": dmg}

            raiders_joined = len(self.raid)  # Replace with your actual channel IDs

            # Final message with gathered data
            for channel_id in channels_ids:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    await channel.send(f"**Done getting data! {raiders_joined} Raiders joined.**")

            start = datetime.datetime.utcnow()

            while (
                    self.boss["hp"] > 0
                    and len(self.raid) > 0
                    and datetime.datetime.utcnow() < start + datetime.timedelta(minutes=60)
            ):
                (target, participant_type) = random.choice(list(self.raid.keys()))
                dmg = random.randint(self.boss["min_dmg"], self.boss["max_dmg"])
                finaldmg = self.getfinaldmg(dmg, self.raid[(target, participant_type)]["armor"])
                self.raid[(target, participant_type)]["hp"] -= finaldmg

                em = discord.Embed(title="Ragnarok attacked!", colour=0xFFB900)

                if self.raid[(target, participant_type)]["hp"] > 0:  # If target is still alive
                    description = f"{target.mention if participant_type == 'user' else target} now has {self.raid[(target, participant_type)]['hp']} HP!"
                    em.description = description
                    em.add_field(name="Theoretical Damage",
                                 value=finaldmg + self.raid[(target, participant_type)]["armor"])
                    em.add_field(name="Shield", value=self.raid[(target, participant_type)]["armor"])
                    em.add_field(name="Effective Damage", value=finaldmg)
                else:  # If target has died
                    # Check if target is a Raider and hasn't used their survival
                    if self.raid[(target, participant_type)]["hp"] <= 0:  # Changed from else to explicit check
                        # Check if target is a Raider and hasn't used their survival
                        survived = False  # Add this flag
                        if participant_type == "user" and target.id not in survival_used:
                            # Check if they're a Raider
                            async with self.bot.pool.acquire() as conn:
                                profile = await conn.fetchrow('SELECT class FROM profile WHERE "user"=$1;', target.id)
                                if profile and profile['class']:
                                    raider_classes = {"Adventurer", "Swordsman", "Fighter", "Swashbuckler",
                                                      "Dragonslayer",
                                                      "Raider", "Eternal Hero"}

                                    is_raider = bool(set(profile['class']) & raider_classes)

                                    if is_raider:
                                        self.raid[(target, participant_type)]["hp"] = 1
                                        survival_used.add(target.id)
                                        description = f"💫 {target.mention}'s Raider instincts allowed them to survive with 1 HP!"
                                        em.description = description
                                        em.add_field(name="Theoretical Damage",
                                                     value=finaldmg + self.raid[(target, participant_type)]["armor"])
                                        em.add_field(name="Shield",
                                                     value=self.raid[(target, participant_type)]["armor"])
                                        em.add_field(name="Effective Damage", value=finaldmg)
                                        survived = True  # Set the flag



                        # Only handle death if they didn't survive
                        if not survived:

                            description = f"{target.mention if participant_type == 'user' else target} died!"
                            em.description = description
                            em.add_field(name="Theoretical Damage",
                                         value=finaldmg + self.raid[(target, participant_type)]["armor"])
                            em.add_field(name="Shield", value=self.raid[(target, participant_type)]["armor"])
                            em.add_field(name="Effective Damage", value=finaldmg)
                            del self.raid[(target, participant_type)]


                if participant_type == "user":
                    em.set_author(name=str(target), icon_url=target.display_avatar.url)
                else:  # For bots
                    em.set_author(name=str(target))
                em.set_thumbnail(url=f"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_dragonattack.webp")
                for channel_id in channels_ids:
                    channel = self.bot.get_channel(channel_id)
                    if channel:

                        await channel.send(embed=em)


                dmg_to_take = sum(i["damage"] for i in self.raid.values())
                self.boss["hp"] -= dmg_to_take
                await asyncio.sleep(4)

                em = discord.Embed(title="The raid attacked Ragnarok!", colour=0xFF5C00)
                em.set_thumbnail(url=f"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_attackdragon.webp")
                em.add_field(name="Damage", value=dmg_to_take)

                if self.boss["hp"] > 0:
                    em.add_field(name="HP left", value=self.boss["hp"])
                else:
                    em.add_field(name="HP left", value="Dead!")
                for channel_id in channels_ids:
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        await channel.send(embed=em)
                await asyncio.sleep(4)

            if len(self.raid) == 0:
                for channel_id in channels_ids:
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        m = await channel.send("The raid was all wiped!")
                        await m.add_reaction("\U0001F1EB")

                summary_text = (
                    "Emoji_here The raid was all wiped! Ragnarok had"
                    f" **{self.boss['hp']:,.3f}** health remaining. Better luck next time."
                )
                try:
                    summary = (
                        "**Raid result:**\n"
                        f"Emoji_here Health: **{self.boss['initial_hp']:,.0f}**\n"
                        f"{summary_text}\n"
                        f"Emoji_here Raiders joined: **{raiders_joined}**"
                    )
                    summary = summary.replace(
                        "Emoji_here",
                        ":small_blue_diamond:" if self.boss["hp"] < 1 else ":vibration_mode:"
                    )
                    summary_channel = self.bot.get_channel(1408139518585864193)

                    summary_msg = await summary_channel.send(summary)
                    self.raid.clear()
                    await self.clear_raid_timer()

                except Exception as e:
                    await ctx.send(f"An error has occurred: {e}")
            elif self.boss["hp"] < 1:
                raid_duration = datetime.datetime.utcnow() - start
                minutes = (raid_duration.seconds % 3600) // 60
                seconds = raid_duration.seconds % 60
                summary_duration = f"{minutes} minutes, {seconds} seconds"

                await ctx.channel.set_permissions(
                    ctx.guild.default_role,
                    overwrite=self.allow_sending,
                )

                highest_bid = [
                    1403785403651063909,
                    0,
                ]  # userid, amount

                bots = sum(1 for _, p_type in self.raid.keys() if p_type == "bot")

                self.raid = {k: v for k, v in self.raid.items() if k[1] == "user"}

                raid_user_ids = [k[0].id for k, v in self.raid.items() if k[1] == 'user']

                def check(msg):
                    try:
                        val = int(msg.content)
                    except ValueError:
                        return False
                    if msg.channel.id != ctx.channel.id or not any(msg.author == k[0] for k in self.raid.keys()):
                        return False
                    if highest_bid[1] == 0:  # Allow starting bid to be $1
                        if val < 1:
                            return False
                        else:
                            return True
                    if val > highest_bid[1]:
                        if highest_bid[1] < 100:
                            return True
                    if val < int(highest_bid[1] * 1.1):  # Minimum bid is 10% higher than the highest bid
                        return False
                    if (
                            msg.author.id == highest_bid[0]
                    ):  # don't allow a player to outbid themselves
                        return False
                    return True

                # If there are no users left in the raid, skip the bidding
                if not self.raid:
                    await ctx.send(f"No survivors left to bid on the {rarity} Crate!")
                    summary_text = (
                        f"Emoji_here Defeated in: **{summary_duration}**\n"
                        f"Emoji_here Survivors: **0 players and {bots} of Drakath's forces**"
                    )
                else:
                    page = commands.Paginator()
                    for u in self.raid.keys():
                        page.add_line(u[0].mention)

                    emote_for_rarity = getattr(self.bot.cogs['Crates'].emotes, rarity)
                    page.add_line(
                        f"The raid killed the boss!\nHe was guarding a {emote_for_rarity} {rarity.capitalize()} Crate!\n"
                        "The highest bid for it wins <:roopiratef:1146234370827505686>\nSimply type how much you bid!"
                    )

                    # Assuming page.pages is a list of pages
                    for channel_id in channels_ids:
                        channel = self.bot.get_channel(channel_id)
                        if channel:
                            for p in page.pages:
                                await channel.send(p[4:-4])


                    while True:
                        try:
                            msg = await self.bot.wait_for("message", timeout=60, check=check)
                        except asyncio.TimeoutError:
                            break
                        bid = int(msg.content)
                        current_bidder = msg.author.id
                        previous_bidder, previous_amount = highest_bid

                        async with self.bot.pool.acquire() as conn:
                            async with conn.transaction():
                                # Check if current bidder has enough money
                                current_balance = await conn.fetchval(
                                    'SELECT money FROM profile WHERE "user" = $1;', current_bidder
                                )
                                if current_balance < bid:
                                    await msg.channel.send(
                                        f"{msg.author.mention} You don't have enough money to place this bid."
                                    )
                                    continue

                                # Check if current bidder is already the highest bidder
                                if current_bidder == previous_bidder:
                                    await msg.channel.send(
                                        f"{msg.author.mention} You already have the highest bid."
                                    )
                                    continue

                                # Refund previous bidder if exists
                                if previous_amount > 0:
                                    await conn.execute(
                                        'UPDATE profile SET money = money + $1 WHERE "user" = $2;',
                                        previous_amount,
                                        previous_bidder,
                                    )

                                # Deduct new bid from current bidder
                                await conn.execute(
                                    'UPDATE profile SET money = money - $1 WHERE "user" = $2;',
                                    bid,
                                    current_bidder,
                                )

                                # Update highest bid
                                highest_bid = [current_bidder, bid]

                        # Notify all channels
                        next_bid = int(bid * 1.1) if bid >= 100 else None
                        for channel_id in channels_ids:
                            channel = self.bot.get_channel(channel_id)
                            if channel:
                                if next_bid is not None:
                                    content = f"{msg.author.mention} bids **${bid}**!\nThe minimum next bid is **${next_bid}**."
                                else:
                                    content = f"{msg.author.mention} bids **${bid}**!"
                                await channel.send(content)

                    msg_content = (
                        f"Auction done! Winner is <@{highest_bid[0]}> with"
                        f" **${highest_bid[1]}**!\nGiving {rarity.capitalize()} Crate... Done!"
                    )
                    summary_crate = (
                        f"Emoji_here {rarity.capitalize()} crate {emote_for_rarity} "
                        f"sold to: **<@{highest_bid[0]}>** for **${highest_bid[1]:,.0f}**"
                    )

                    # Assign the crate to the winner without deducting money again
                    column_name = f"crates_{rarity}"
                    async with self.bot.pool.acquire() as conn:
                        await conn.execute(
                            f'UPDATE profile SET "{column_name}"="{column_name}"+1 WHERE "user"=$1;',
                            highest_bid[0],
                        )

                        await self.bot.log_transaction(
                            ctx,
                            from_=highest_bid[0],
                            to=2,
                            subject="raid bid winner",
                            data={"Gold": highest_bid[1]},
                            conn=conn,
                        )

                    # Send the result to all channels
                    for channel_id in channels_ids:
                        channel = self.bot.get_channel(channel_id)
                        if channel:
                            await channel.send(msg_content)


                    cash_pool = hp * 1.3
                    survivors = len(self.raid)
                    self.raid = {(user, p_type): data for (user, p_type), data in self.raid.items() if
                                 p_type == "user" and not user.bot}
                    base_cash = int(cash_pool / survivors)  # This is our base reward

                    # Send the base cash to all survivors first
                    users = [user.id for user, p_type in self.raid.keys() if p_type == "user"]
                    await self.bot.pool.execute(
                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=ANY($2);',
                        base_cash,
                        users
                    )

                    # Process each survivor for potential Raider bonus
                    for (user, p_type) in list(
                            self.raid.keys()):  # Use list() to avoid runtime changes issues
                        async with self.bot.pool.acquire() as conn:
                            profile = await conn.fetchrow('SELECT class FROM profile WHERE "user"=$1;',
                                                          user.id)
                            bonus_multiplier = 0  # Initialize bonus multiplier

                            if profile and profile['class']:
                                # Define Raider classes and their corresponding bonuses
                                raider_classes = {
                                    "Adventurer": 0.05,  # 5% bonus
                                    "Swordsman": 0.10,  # 10% bonus
                                    "Fighter": 0.15,  # 15% bonus
                                    "Swashbuckler": 0.20,  # 20% bonus
                                    "Dragonslayer": 0.25,  # 25% bonus
                                    "Raider": 0.30,  # 30% bonus
                                    "Eternal Hero": 0.40  # 40% bonus
                                }

                                # Determine the highest applicable bonus
                                for class_name in profile['class']:
                                    if class_name in raider_classes:
                                        class_bonus = raider_classes[class_name]
                                        bonus_multiplier = max(bonus_multiplier, class_bonus)

                                if bonus_multiplier > 0:
                                    bonus_amount = int(base_cash * bonus_multiplier)
                                    await conn.execute(
                                        'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                                        bonus_amount,
                                        user.id
                                    )
                                    # Announce bonus if there was one
                                    for channel_id in channels_ids:
                                        channel = self.bot.get_channel(channel_id)
                                        if channel:
                                            await channel.send(
                                                f"💰 {user.mention}'s Raider abilities earned them an extra ${bonus_amount:,.0f}!"
                                            )

                    # Send the final message to all channels
                    for channel_id in channels_ids:
                        channel = self.bot.get_channel(channel_id)
                        if channel:
                            await channel.send(
                                f"**Gave ${base_cash:,.0f} of Ragnarok's ${cash_pool:,.0f} drop to all survivors!**")

                        summary_text = (
                            f"Emoji_here Defeated in: **{summary_duration}**\n"
                            f"{summary_crate}\n"
                            f"Emoji_here Payout per survivor: **${base_cash:,.0f}**\n"
                            f"Emoji_here Survivors: **{survivors} and {bots} of placeholders forces**"
                        )

                    # Assuming channels_ids is a list of channel IDs
            if self.boss["hp"] > 1:
                for channel_id in channels_ids:
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        m = await ctx.send(
                            "The raid did not manage to kill Ragnarok within an hour... He disappeared!")
                        await m.add_reaction("\U0001F1EB")
                        summary = (
                            "The raid did not manage to kill Ragnarok within an hour... He disappeared with **{self.boss['hp']:,.3f}** health remaining."
                        )

            if users:  # Check if the list is not empty
                random_user_id = random.choice(users)
                success = True
                self.bot.dispatch("raid_completion", ctx, success, random_user_id)
                # Now you can use random_user_id for whatever you need
            
            await asyncio.sleep(30)
            await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=self.deny_sending)
            await self.clear_raid_timer()
            try:
                self.raid.clear()
            except Exception as e:
                await ctx.send(f"An error occurred: {e}")

            if self.boss["hp"] < 1:

                if self.bot.config.bot.is_beta:
                    summary = (
                        "**Raid result:**\n"
                        f"Emoji_here Health: **{self.boss['initial_hp']:,.0f}**\n"
                        f"{summary_text}\n"
                        f"Emoji_here Raiders joined: **{raiders_joined}**"
                    )
                    summary = summary.replace(
                        "Emoji_here",
                        ":small_blue_diamond:" if self.boss["hp"] < 1 else ":vibration_mode:"
                    )
            summary_channel = self.bot.get_channel(1408139518585864193)
            summary_msg = await summary_channel.send(summary)

                #await ctx.send("attempting to clear keys...")
            try:
                self.raid.clear()
            except Exception as e:
                await ctx.send(f"An error occurred: {e}")
            self.raid_preparation = False
            self.boss = None
        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n"
            error_message += traceback.format_exc()
            await ctx.send(error_message)
            print(error_message)

    async def get_random_user_info(self, ctx):
        try:
            # Fetch a random user ID and display name from the database
            async with self.bot.pool.acquire() as connection:
                # Modify the query based on your database structure
                result = await connection.fetchrow('SELECT "user" FROM profile ORDER BY RANDOM() LIMIT 1')

                # Get the display name using the Discord API
                user_id = result["user"]
                user = await self.bot.fetch_user(user_id)
                display_name = user.display_name

                # Return user ID and display name
                return {"user_id": user_id, "display_name": display_name}

        except Exception as e:
            # Handle exceptions, you can customize this part based on your needs
            await ctx.send(f"An error occurred in get_random_user_info: {e}")
            return None

    @commands.command()
    @is_gm()
    async def aijoin(self, ctx, quantity: int = 1):
        try:
            if not self.raid_preparation:
                return await ctx.send("You can only add bots during raid preparation!")

            bot_counts = {}  # Keep track of how many bots have been added

            for _ in range(quantity):
                # Fetch a random user ID and display name from the database
                user_info = await self.get_random_user_info(ctx)

                # If a bot has been added before, update its count
                if "bot" in bot_counts:
                    bot_counts["bot"] += 1
                else:
                    bot_counts["bot"] = 1

                # Construct the bot player entry and add it to the raid dictionary

                bot_entry = (user_info["display_name"], "bot")
                self.raid[bot_entry] = {
                    "user": user_info["user_id"],
                    "hp": Decimal(str(round(randomm.uniform(50.0, 400.0), 2))).quantize(Decimal("0.00"),
                                                                                        rounding=ROUND_HALF_UP),
                    "armor": Decimal(str(round(randomm.uniform(50.0, 150.0), 2))).quantize(Decimal("0.00"),
                                                                                           rounding=ROUND_HALF_UP),
                    "damage": Decimal(str(round(randomm.uniform(100.0, 250.0), 2))).quantize(Decimal("0.00"),
                                                                                             rounding=ROUND_HALF_UP),
                }
            # Construct the summary for reinforcements
            reinforcement_summary = ', '.join([f"{count} {bot}" for bot, count in bot_counts.items()])

            random_number = randomm.randint(1, 3)
            if random_number == 1:
                embed = Embed(
                    title="The Shadows Stir...",
                    description=(
                        "As the whispers of Drakath's faithful grew louder, a dark mist enveloped the battlefield. "
                        f"From the heart of this shadow, {quantity} warriors emerged. "
                        "Ragnarok's challenges just became more... sinister."),
                    color=0x8a2be2  # Setting the color to a shade of purple to match the theme
                )
                embed.set_thumbnail(
                    url="https://i.ibb.co/RGXPhCD/several-evil-warriors-purple-corruption-purple-flames.png")

                await ctx.send(embed=embed)

            if random_number == 2:
                embed = Embed(
                    title="Elysia's Grace...",
                    description=(
                        "As the benevolent aura of Goddess Elysia permeates the air, a radiant light bathes the battlefield. "
                        f"From the celestial realm, {quantity} champions descended. "
                        "Ragnarok's challenges now face the divine intervention of Elysia."),
                    color=0xffd700  # Setting the color to gold to match the theme for a benevolent goddess
                )
                embed.set_thumbnail(
                    url="https://i.ibb.co/TTh7rZJ/image.png")  # Replace with an image URL representing Elysia's grace

                await ctx.send(embed=embed)

            if random_number == 3:
                embed = Embed(
                    title="Sepulchure's Malevolence...",
                    description=(
                        "As the malevolent presence of Sepulchure looms over the battlefield, a darkness shrouds the surroundings. "
                        f"From the depths of this abyss, {quantity} dreadknights emerged. "
                        "Ragnarok's challenges now bear the mark of Sepulchure's sinister influence."),
                    color=0x800000  # Setting the color to maroon to match the theme for an evil god
                )
                embed.set_thumbnail(
                    url="https://i.ibb.co/FmdPdV2/2.png")  # Replace with an image URL representing Sepulchure's malevolence

                await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(f"An error occurred: {e}")



    async def get_player_decision(self, player, options, role, prompt=None, embed=None):
        """
        Sends a prompt or embed with options to the player and returns their decision.
        :param player: The player to wait for a response from.
        :param options: The list of available options.
        :param role: The role of the player (follower, champion, or priest).
        :param prompt: (Optional) The message to display.
        :param embed: (Optional) The embed to send.
        :return: The player's chosen option or the default action based on the role if they don't respond in time.
        """

        # Check if player is AI
        if isinstance(player, (ShadowChampionAI, ShadowPriestAI)):
            # AI players don't need DMs, just return a default action
            default_actions = {
                "follower": "Chant",
                "champion": "Smite",
                "priest": "Bless"
            }
            return default_actions[role]

        view = DecisionView(player, options)

        if embed:
            message = await player.send(embed=embed, view=view)
        else:
            message = await player.send(prompt + "\n\n" + "\n".join(options), view=view)

        await view.wait()

        if view.value:
            return view.value
        else:
            # Return default action based on role in case of timeout
            default_actions = {
                "follower": "Chant",
                "champion": "Smite",  # Assuming you want to default to "Smite" for the champion, you can adjust this
                "priest": "Bless"
            }
            await player.send(f"You took too long to decide. Defaulting to '{default_actions[role]}'.")
            return default_actions[role]

    @is_gm()
    @commands.command(hidden=True, brief=_("Start an Infernal Ritual raid"))
    async def evilspawn(self, ctx):
        """[Evil God only] Starts a raid."""

        try:
            # Create single join view with both options
            class DualJoinView(View):
                def __init__(self):
                    super().__init__(timeout=60 * 15)
                    self.follower_joined = []
                    self.leader_joined = []
                    
                @discord.ui.button(label="Join as Follower Only", style=ButtonStyle.secondary)
                async def follower_button(self, interaction: discord.Interaction, button: Button):
                    if interaction.user not in self.follower_joined and interaction.user not in self.leader_joined:
                        self.follower_joined.append(interaction.user)
                        await interaction.response.send_message(_("You have joined as a follower."), ephemeral=True)
                    else:
                        await interaction.response.send_message(_("You have already joined the ritual."), ephemeral=True)
                
                @discord.ui.button(label="Join as Champion/Priest", style=ButtonStyle.primary)
                async def leader_button(self, interaction: discord.Interaction, button: Button):
                    if interaction.user not in self.follower_joined and interaction.user not in self.leader_joined:
                        self.leader_joined.append(interaction.user)
                        await interaction.response.send_message(_("You have joined as a potential leader."), ephemeral=True)
                    else:
                        await interaction.response.send_message(_("You have already joined the ritual."), ephemeral=True)

            dual_view = DualJoinView()

            embed = Embed(
                title="🌑 The Eclipse Begins",
                description="""
            The moon turns blood red as a sacred temple emerges from the shadows, emanating an aura of dread. The dark followers are summoned to perform the Infernal Ritual to awaken an ancient evil.

            **Choose your role in this unholy ceremony:**
            • **Join as Follower Only** - Support the ritual from the shadows
            • **Join as Champion/Priest** - Lead the ritual and face the Guardian directly
            
            **Only the most devoted followers of Sepulchure may partake in this unholy ceremony.**
                """,
                color=0x550000  # Dark red color
            )

            # Use an image URL for dramatic effect
            image_url = "https://i.ibb.co/Yf6q0K4/OIG-15.png"
            embed.set_image(url=image_url)

            await ctx.send(embed=embed, view=dual_view)

            await ctx.send(
                "Prepare yourselves. The ritual will commence soon. This is **BETA** and may require balancing.")


            # Wait for the ritual to start
            await asyncio.sleep(300)
            await ctx.send("**The shadows deepen... The ritual begins in 10 minutes.**")
            await asyncio.sleep(300)
            await ctx.send("**Whispers fill the air... 5 minutes remain.**")
            await asyncio.sleep(180)
            await ctx.send("**Your heart pounds... 2 minutes until the ritual commences.**")
            await asyncio.sleep(60)
            await ctx.send("**A chill runs down your spine... 1 minute left.**")
            await asyncio.sleep(60)
            await ctx.send("**The ground trembles... 30 seconds.**")
            await asyncio.sleep(20)
            await ctx.send("**Darkness engulfs you... 10 seconds.**")
            await asyncio.sleep(10)

            dual_view.stop()

            await ctx.send(
                "**💀 The ritual begins! The Guardian awakens from its slumber... 💀**"
            )

            raid = {}

            def progress_bar(current, total, bar_length=10):
                progress = (current / total)
                arrow = '⬛'
                space = '⬜'
                num_of_arrows = int(progress * bar_length)
                return arrow * num_of_arrows + space * (bar_length - num_of_arrows)
            HowMany = 0

            async with self.bot.pool.acquire() as conn:
                for u in dual_view.follower_joined + dual_view.leader_joined:
                    if (
                            not (
                                    profile := await conn.fetchrow(
                                        'SELECT * FROM profile WHERE "user"=$1;', u.id
                                    )
                            )
                            or profile["god"] != "Sepulchure"
                    ):
                        continue
                    HowMany = HowMany + 1
                    try:
                        dmg, deff = await self.bot.get_raidstats(
                            u,
                            atkmultiply=profile["atkmultiply"],
                            defmultiply=profile["defmultiply"],
                            classes=profile["class"],
                            race=profile["race"],
                            guild=profile["guild"],
                            god=profile["god"],
                            conn=conn,
                        )
                    except ValueError:
                        continue
                    raid[u] = {"hp": 250, "armor": deff, "damage": dmg}

            async def is_valid_participant(user, conn):
                # Check if the user is a follower of "Sepulchure"
                profile = await conn.fetchrow('SELECT * FROM profile WHERE "user"=$1;', user.id)
                if profile and profile["god"] == "Sepulchure":
                    return True
                return False

            await ctx.send("**Gathering the faithful... checking dm eligibility this may take awhile**")
            embed_message_id = None
            async with self.bot.pool.acquire() as conn:
                all_participants = dual_view.follower_joined + dual_view.leader_joined
                participants = [u for u in all_participants if await is_valid_participant(u, conn)]

            if not participants:
                await ctx.send("No valid participants joined the ritual.")
                await self.clear_raid_timer()
                return

            for participant in participants.copy():
                try:
                    await participant.send("You have joined the ritual! Stay tuned for more info.")
                    await asyncio.sleep(1)
                except (discord.Forbidden, discord.HTTPException):
                    # Remove participant if bot cannot DM
                    participants.remove(participant)
                    await ctx.send(
                        f"{participant.mention} was removed because I could not send them a DM. "
                        "Please enable your DMs or unblock the bot to participate."
                    )

                # After removing DM-blocked users, check if anyone remains
            if not participants:
                await ctx.send("All participants have been removed. The ritual is canceled.")
                await self.clear_raid_timer()
                return

            await ctx.send(content=f"**{HowMany} followers joined!**")

            # Separate participants by join type
            leader_participants = [u for u in dual_view.leader_joined if u in participants]
            follower_participants = [u for u in dual_view.follower_joined if u in participants]

            # Role assignment with AI fallback
            if not leader_participants:
                # No leaders volunteered - create Shadow entities
                shadow_champion = ShadowChampionAI()
                shadow_priest = ShadowPriestAI()
                champion = shadow_champion
                priest = shadow_priest
                followers = participants
                
                # Announce Shadow entities
                shadow_announcement = discord.Embed(
                    title="👻 Shadow Entities Manifest 👻",
                    description="""
                No mortals dared to lead the ritual. From the depths of Sepulchure's will, 
                dark entities materialize to guide the faithful through this unholy ceremony.
                
                **The Shadow Champion and Shadow Priest have emerged from the void.**
                    """,
                    color=0x8B0000
                )
                await ctx.send(embed=shadow_announcement)
                
            else:
                # Normal role assignment from leader pool
                champion = random.choice(leader_participants)
                leader_participants.remove(champion)

                priest = random.choice(leader_participants) if leader_participants else None
                if priest:
                    leader_participants.remove(priest)

                # All remaining participants become followers
                followers = follower_participants + leader_participants

            announcement_color = 0x550000
            champion_embed = discord.Embed(
                title="👑 The Chosen Champion 👑",
                description=f"{champion.mention if hasattr(champion, 'mention') else 'Shadow Champion'} has been marked by darkness as the Champion!",
                color=announcement_color
            )
            await ctx.send(embed=champion_embed)
            if priest:
                priest_embed = discord.Embed(
                    title="🔮 The Dark Priest 🔮",
                    description=f"{priest.mention if hasattr(priest, 'mention') else 'Shadow Priest'} has embraced the shadows as the Priest!",
                    color=announcement_color
                )
                await ctx.send(embed=priest_embed)
            else:
                await ctx.send("No Priest was chosen. The ritual will be more perilous without one.")

            # Generate a list of follower mentions
            if followers:
                follower_mentions = "\n".join(f"{follower.mention}" for follower in followers)

                follower_embed = discord.Embed(
                    title="🕯️ The Faithful Followers 🕯️",
                    description=follower_mentions,
                    color=announcement_color
                )
                await ctx.send(embed=follower_embed)
            else:
                await ctx.send("No Followers are participating. The ritual relies solely on the Champion and Priest.")

            # Common Embed Color for the Ritual Theme
            EVIL_RITUAL_COLOR = discord.Color.dark_red()

            # General Ritual Embed
            ritual_embed_help = discord.Embed(
                title="🌑 The Infernal Ritual 🌑",
                description=("The hour is nigh. Unite your efforts to awaken the ancient evil. "
                             "But beware, the Guardian will stop at nothing to prevent the completion of the ritual."),
                color=EVIL_RITUAL_COLOR
            )
            ritual_embed_help.add_field(name="Warning",
                                        value="If the Champion falls, all hope is lost. Protect them with your lives!")

            # Champion Embed
            champion_embed_help = discord.Embed(
                title="🛡️ Role: Champion 🛡️",
                description=("You are the vessel for the ancient evil. Your survival is paramount. "
                             "Lead your followers and withstand the Guardian's assault."),
                color=EVIL_RITUAL_COLOR
            )
            champion_embed_help.add_field(name="⚔️ Smite", value="Unleash dark power upon the Guardian.", inline=False)
            champion_embed_help.add_field(name="❤️ Heal", value="Draw upon shadows to mend your wounds.",
                                          inline=False)
            champion_embed_help.add_field(name="🌀 Haste",
                                          value="Accelerate the ritual's progress. (Cooldown applies; makes you vulnerable)",
                                          inline=False)
            champion_embed_help.add_field(name="🛡️ Defend", value="Brace yourself, reducing incoming damage next turn.",
                                          inline=False)
            champion_embed_help.add_field(name="💔 Sacrifice",
                                          value="Offer your life force to significantly advance the ritual.",
                                          inline=False)

            # Followers Embed
            followers_embed_help = discord.Embed(
                title="🔮 Role: Followers 🔮",
                description="Your devotion fuels the ritual. Support the Champion and Priest through any means necessary.",
                color=EVIL_RITUAL_COLOR
            )
            followers_embed_help.add_field(name="🌌 Boost Ritual", value="Channel your energy to hasten the ritual.",
                                           inline=False)
            followers_embed_help.add_field(name="🛡️ Protect Champion",
                                           value="Use your collective will to shield the Champion.",
                                           inline=False)
            followers_embed_help.add_field(name="💥 Empower Priest",
                                           value="Enhance the Priest's dark incantations.",
                                           inline=False)
            followers_embed_help.add_field(name="🔥 Sabotage Guardian",
                                           value="Undermine the Guardian's strength.",
                                           inline=False)
            followers_embed_help.add_field(name="🎵 Chant",
                                           value="Raise your voices to amplify the ritual's power.",
                                           inline=False)
            followers_embed_help.add_field(name="💉 Heal Champion",
                                           value="Offer some of your vitality to heal the Champion.",
                                           inline=False)

            # Priest Embed
            priest_embed_help = discord.Embed(
                title="🌙 Role: Priest 🌙",
                description="Master the forbidden arts to sway the ritual's outcome. Your spells are pivotal.",
                color=EVIL_RITUAL_COLOR
            )
            priest_embed_help.add_field(name="🔥 Bless", value="Imbue the Champion with dark might.",
                                        inline=False)
            priest_embed_help.add_field(name="🔮 Barrier",
                                        value="Conjure an unholy shield around the Champion.",
                                        inline=False)
            priest_embed_help.add_field(name="😵 Curse", value="Afflict the Guardian with debilitating hexes.",
                                        inline=False)
            priest_embed_help.add_field(name="❤️ Revitalize", value="Invoke dark energies to heal the Champion.",
                                        inline=False)
            priest_embed_help.add_field(name="🌟 Channel",
                                        value="Focus your power to significantly boost ritual progress.",
                                        inline=False)

            # Send these embeds to the main chat or to the respective players.
            await ctx.send(embed=ritual_embed_help)

            # DM the champion the instructions (only if human)
            if not isinstance(champion, ShadowChampionAI):
                await champion.send(embed=champion_embed_help)

            # DM the priest the instructions if they exist (only if human)
            if priest and not isinstance(priest, ShadowPriestAI):
                await priest.send(embed=priest_embed_help)

            # DM the followers the instructions
            for follower in followers:
                await follower.send(embed=followers_embed_help)

            # Turn-based logic
            TOTAL_TURNS = 25

            CHAMPION_ABILITIES = {
                "Smite": "Strike the Guardian with dark power.",
                "Heal": "Heal yourself.",
                "Haste": "Boost the ritual's progress but become vulnerable next turn.",
                "Defend": "Reduce incoming damage next turn.",
                "Sacrifice": "Greatly advance the ritual at the cost of your HP."
            }
            default_champion_damage = 750
            champion_stats = {
                "hp": 1500,
                "damage": default_champion_damage,
                "protection": False,  # No protection at the start
                "shield_points": 0,  # No shield points at the start
                "barrier_active": False,  # Assuming no active barrier at the start
                "max_hp": 1500,  # Maximum allowable HP
                "healing_rate": 200,  # Hypothetical amount champion heals for; adjust as needed
                "haste_cooldown": 0,
                "vulnerable": False,
                "defending": False
            }

            # Guardian Phases based on Ritual Progress
            GUARDIAN_PHASES = {
                1: {
                    "name": "The Sentinel",
                    "description": "A towering figure emerges, cloaked in ancient armor. Its eyes glow with a cold light.",
                    "abilities": ["strike", "shield", "purify"],
                    "progress_threshold": 10  # Ritual progress percentage to move to next phase
                },
                2: {
                    "name": "The Corrupted",
                    "description": "The Guardian's form twists and darkens, tendrils of shadow emanate from its body.",
                    "abilities": ["strike", "corrupting_blast", "shadow_shield", "purify", "fear_aura"],
                    "progress_threshold": 30
                },
                3: {
                    "name": "The Abyssal Horror",
                    "description": "With a deafening roar, the Guardian transforms into a nightmarish entity from the abyss. Its mere presence instills terror.",
                    "abilities": ["obliterate", "dark_aegis", "soul_drain", "apocalyptic_roar"],
                    "progress_threshold": 60  # Final phase; beyond ritual completion
                }
            }

            guardians_stats = {
                "hp": 5000,  # Starting HP
                "max_hp": 5000,
                "cursed": False,
                "damage_multiplier": 1.0,
                "shield_active": False,
                "base_damage": 150,
                "regeneration_rate": 500,
                "enraged": False,
                "phase": 1,
                "incapacitated_turns": 0  # New key to track incapacitation
            }

            TIMEOUT = 90
            priest_stats = {
                "healing_boost": 1.0,
                "mana": 100,
                "max_mana": 100
            }

            def apply_damage_with_protection(target_stats, damage):
                """Apply damage to target taking protection (shield) into consideration."""
                if "protection" in target_stats and target_stats["protection"]:
                    # Calculate remaining damage after shield absorption
                    shield_absorption = min(damage, target_stats.get("shield_points", 0))
                    target_stats["shield_points"] -= shield_absorption
                    damage_after_shield = damage - shield_absorption
                    if target_stats["shield_points"] <= 0:
                        target_stats["protection"] = False
                        target_stats["shield_points"] = 0
                else:
                    damage_after_shield = damage

                # Apply remaining damage to target's HP
                target_stats["hp"] -= damage_after_shield

            progress = 0

            # Initial Guardian appearance
            phase_info = GUARDIAN_PHASES[guardians_stats["phase"]]
            guardian_appearance_embed = discord.Embed(
                title=f"💀 {phase_info['name']} Appears 💀",
                description=phase_info["description"],
                color=0x550000
            )
            await ctx.send(embed=guardian_appearance_embed)

            for turn in range(TOTAL_TURNS):

                if champion_stats["hp"] <= 0:
                    await ctx.send(f"💔 {champion.mention} has fallen. The ritual fails as darkness recedes...")
                    await self.clear_raid_timer()
                    return

                if progress >= 100:
                    break

                # Initialize follower_combined_decision at the start of each turn
                follower_combined_decision = {
                    "Boost Ritual": 0,
                    "Protect Champion": 0,
                    "Empower Priest": 0,
                    "Sabotage Guardian": 0,
                    "Chant": 0,
                    "Heal Champion": 0
                }

                # Priest's turn
                if priest:
                    # Check if priest is AI or human
                    if isinstance(priest, ShadowPriestAI):
                        # AI Priest decision
                        await ctx.send(f"🔮 **{priest.mention} contemplates the mystical energies...**")
                        priest_decision = await priest.make_decision(priest_stats, champion_stats, guardians_stats, progress, follower_combined_decision)
                        await priest.announce_decision(ctx, priest_decision, priest_stats, champion_stats, guardians_stats, progress)
                    else:
                        # Human Priest decision
                        decision_embed = discord.Embed(
                            title="🔮 Priest's Turn 🔮",
                            description=f"{priest.mention}, your arcane knowledge is needed. Choose your action:",
                            color=discord.Color.dark_purple()
                        )

                        # Priest abilities with mana costs
                        priest_abilities = {
                            "Bless": {"description": "Boost the Champion's power", "mana_cost": 20},
                            "Barrier": {"description": "Protect the Champion", "mana_cost": 30},
                            "Curse": {"description": "Weaken the Guardian", "mana_cost": 25},
                            "Revitalize": {"description": "Heal the Champion", "mana_cost": 20},
                            "Channel": {"description": "Significantly increase ritual progress", "mana_cost": 15}
                        }

                        for ability, info in priest_abilities.items():
                            if priest_stats["mana"] >= info["mana_cost"]:
                                decision_embed.add_field(name=f"{ability} (Cost: {info['mana_cost']} Mana)",
                                                         value=info["description"], inline=False)
                        decision_embed.set_footer(
                            text=f"Mana: {priest_stats['mana']}/{priest_stats['max_mana']}")

                        await ctx.send(f"It's {priest.mention}'s turn to make a decision, check DMs!")

                        valid_priest_options = [ability for ability, info in priest_abilities.items()
                                                if priest_stats["mana"] >= info["mana_cost"]]

                        if not valid_priest_options:
                            await ctx.send(f"{priest.mention} has no mana left to perform any action.")
                            priest_decision = None
                        else:
                            try:
                                priest_decision = await asyncio.wait_for(
                                    self.get_player_decision(
                                        player=priest,
                                        options=valid_priest_options,
                                        role="priest",
                                        embed=decision_embed
                                    ),
                                    timeout=TIMEOUT
                                )
                            except asyncio.TimeoutError:
                                await ctx.send(f"{priest.mention} took too long! Moving on...")
                                priest_decision = None

                    # Execute priest decision
                    if priest_decision:
                        # Deduct mana cost
                        priest_abilities = {
                            "Bless": {"mana_cost": 20},
                            "Barrier": {"mana_cost": 30},
                            "Curse": {"mana_cost": 25},
                            "Revitalize": {"mana_cost": 20},
                            "Channel": {"mana_cost": 15}
                        }
                        priest_stats["mana"] -= priest_abilities[priest_decision]["mana_cost"]
                        
                        if priest_decision == "Bless":
                            champion_stats["damage"] += 200 * priest_stats["healing_boost"]
                            await ctx.send(f"✨ The Priest blesses the Champion, increasing their power!")
                        elif priest_decision == "Barrier":
                            champion_stats["barrier_active"] = True
                            await ctx.send(f"🛡️ A mystical barrier surrounds the Champion!")
                        elif priest_decision == "Curse":
                            guardians_stats["cursed"] = True
                            await ctx.send(f"🔒 The Priest casts a curse on the Guardian, weakening it!")
                        elif priest_decision == "Revitalize":
                            heal_amount = 300 * priest_stats["healing_boost"]
                            champion_stats["hp"] = min(
                                champion_stats["hp"] + heal_amount, champion_stats["max_hp"])
                            await ctx.send(f"❤️ The Priest heals the Champion for {int(heal_amount)} HP!")
                        elif priest_decision == "Channel":
                            progress += 5
                            await ctx.send(f"🌟 The Priest channels energy, advancing the ritual!")
                else:
                    priest_decision = None

                # Check if the Guardian's HP is <= 0 and handle incapacitation
                if guardians_stats["hp"] <= 0 and guardians_stats["incapacitated_turns"] == 0:
                    # Guardian is incapacitated for 2 turns
                    guardians_stats["incapacitated_turns"] = 2
                    await ctx.send("💀 The Guardian collapses, giving you a brief respite!")
                    # Optionally, you can allow players to gain extra progress during this time
                    progress += 10  # Bonus progress for defeating the Guardian temporarily

                # Guardian's turn
                if guardians_stats["incapacitated_turns"] > 0:
                    guardians_stats["incapacitated_turns"] -= 1
                    if guardians_stats["incapacitated_turns"] == 0:
                        # Guardian revives with some HP and possibly increased strength
                        guardians_stats["hp"] = int(guardians_stats["max_hp"] * 0.5)
                        guardians_stats["damage_multiplier"] += 0.2
                        await ctx.send("😈 The Guardian rises again, more enraged than ever!")
                        # Announce the new phase if applicable
                        if guardians_stats["phase"] < 3:
                            guardians_stats["phase"] += 1
                            phase_info = GUARDIAN_PHASES[guardians_stats["phase"]]
                            phase_embed = discord.Embed(
                                title=f"😈 The Guardian Transforms into {phase_info['name']}!",
                                description=phase_info["description"],
                                color=0x8B0000  # Dark red color
                            )
                            await ctx.send(embed=phase_embed)
                    else:
                        await ctx.send("💀 The Guardian is incapacitated and cannot act this turn.")
                else:
                    await ctx.send(f"💢 The Guardian takes its turn.")

                    current_phase = guardians_stats["phase"]
                    next_phase = current_phase + 1

                    if next_phase in GUARDIAN_PHASES:
                        phase_info_next = GUARDIAN_PHASES[next_phase]
                        progress_threshold = phase_info_next["progress_threshold"]
                        if progress >= progress_threshold:
                            guardians_stats["phase"] = next_phase
                            guardians_stats["damage_multiplier"] += 0.3  # Increase damage multiplier
                            # Announce the phase change
                            phase_embed = discord.Embed(
                                title=f"😈 The Guardian Transforms into {phase_info_next['name']}!",
                                description=phase_info_next["description"],
                                color=0x8B0000
                            )
                            await ctx.send(embed=phase_embed)
                            # Update phase_info to the new phase
                            phase_info = phase_info_next
                    # Else, phase_info remains as the current phase

                    guardians_decisions = phase_info["abilities"]

                    # Guardian decision logic based on phase
                    if progress >= 80 and "purify" in guardians_decisions:
                        guardian_decision = "purify"
                    elif guardians_stats.get("cursed") and "regenerate" in guardians_decisions:
                        guardian_decision = random.choice(["strike", "purify", "regenerate"])
                    elif champion_stats.get("barrier_active") and "disrupt" in guardians_decisions:
                        guardian_decision = random.choice(["purify", "disrupt"])
                    else:
                        guardian_decision = random.choice(guardians_decisions)

                    # Execute the Guardian's action
                    if guardian_decision == "strike":
                        # Existing strike logic
                        damage = random.randint(100, 250) * guardians_stats["damage_multiplier"]
                        if guardians_stats.get("enraged"):
                            damage *= 1.5
                        if champion_stats.get("barrier_active"):
                            damage *= 0.5
                            champion_stats["barrier_active"] = False
                        if champion_stats.get("defending"):
                            damage *= 0.5
                            champion_stats["defending"] = False
                        if champion_stats.get("vulnerable"):
                            damage *= 1.5
                            champion_stats["vulnerable"] = False
                        apply_damage_with_protection(champion_stats, damage)
                        await ctx.send(f"💥 The Guardian strikes the Champion for **{int(damage)} damage**!")

                    elif guardian_decision == "corrupting_blast":
                        # Phase 2 ability
                        damage = random.randint(150, 250) * guardians_stats["damage_multiplier"]
                        champion_stats["damage"] = max(champion_stats["damage"] - 100, 0)
                        apply_damage_with_protection(champion_stats, damage)
                        await ctx.send(
                            f"⚡ The Guardian unleashes a Corrupting Blast, dealing **{int(damage)} damage** and severely reducing the Champion's damage!")

                    elif guardian_decision == "shadow_shield":
                        guardians_stats["shield_active"] = True
                        guardians_stats["damage_multiplier"] *= 0.8
                        await ctx.send("🛡️ The Guardian casts a Shadow Shield, reducing incoming damage by **20%**!")

                    elif guardian_decision == "obliterate":
                        # Phase 3 ability
                        damage = random.randint(400, 900) * guardians_stats["damage_multiplier"]
                        apply_damage_with_protection(champion_stats, damage)
                        await ctx.send(
                            f"☠️ The Guardian attempts to obliterate the Champion with a devastating attack, dealing **{int(damage)} damage**!")

                    elif guardian_decision == "dark_aegis":
                        guardians_stats["shield_active"] = True
                        guardians_stats["damage_multiplier"] *= 0.5
                        await ctx.send(
                            "🔰 The Guardian envelops itself in a Dark Aegis, greatly reducing incoming damage by **50%**!")

                    elif guardian_decision == "soul_drain":
                        damage = random.randint(200, 300)
                        guardians_stats["hp"] += damage
                        guardians_stats["hp"] = min(guardians_stats["hp"], guardians_stats["max_hp"])
                        apply_damage_with_protection(champion_stats, damage)
                        await ctx.send(
                            f"🩸 The Guardian uses Soul Drain, siphoning **{damage} HP** from the Champion to heal itself, dealing **{int(damage)} damage**!")

                    elif guardian_decision == "purify":
                        progress_before = progress
                        progress = max(0, progress - 20)
                        progress_reduction = progress_before - progress
                        await ctx.send(
                            f"💫 The Guardian attempts to purify the ritual, significantly reducing its progress by **{progress_reduction}%**!")

                    elif guardian_decision == "shield":
                        guardians_stats["shield_active"] = True
                        await ctx.send("🛡️ The Guardian raises a shield, preparing to absorb incoming damage!")

                    elif guardian_decision == "fear_aura":
                        # Phase 2 ability
                        # Potentially reduce followers' actions
                        await ctx.send(
                            "😱 The Guardian emits a Fear Aura, unsettling the followers and reducing their effectiveness!")

                    elif guardian_decision == "apocalyptic_roar":
                        # Phase 3 ability
                        damage = random.randint(150, 250)
                        champion_stats["hp"] -= damage
                        if priest:
                            # Implement priest HP if applicable
                            pass
                        for follower in followers:
                            # Implement followers' HP or effectiveness reduction
                            pass
                        await ctx.send(
                            f"🌋 The Guardian unleashes an Apocalyptic Roar, dealing **{damage} damage** to the Champion and harming all who hear it!")

                # Followers' decisions
                await ctx.send(f"🙏 The Followers are making their decisions.")

                follower_combined_decision = {
                    "Boost Ritual": 0,
                    "Protect Champion": 0,
                    "Empower Priest": 0,
                    "Sabotage Guardian": 0,
                    "Chant": 0,
                    "Heal Champion": 0
                }

                follower_embed = discord.Embed(
                    title="🕯️ Followers' Actions 🕯️",
                    description="Choose your action to support the ritual:",
                    color=discord.Color.purple()
                )

                # Add abilities with emojis
                follower_embed.add_field(name="🔆 Boost Ritual", value="Increase the ritual's progress", inline=True)
                follower_embed.add_field(name="🛡️ Protect Champion", value="Provide a shield to the Champion",
                                         inline=True)
                follower_embed.add_field(name="🌟 Empower Priest", value="Amplify the Priest's next action", inline=True)
                follower_embed.add_field(name="💥 Sabotage Guardian", value="Disrupt the Guardian's next move",
                                         inline=True)
                follower_embed.add_field(name="🎶 Chant", value="Contribute to the ritual's power",
                                         inline=True)
                follower_embed.add_field(name="💉 Heal Champion", value="Heal the Champion a small amount", inline=True)

                # Add a footer to the embed
                follower_embed.set_footer(
                    text="Your collective will shapes the ritual's fate.")

                # Separate function to obtain each follower's decision
                async def get_follower_decision(follower):
                    decision = await self.get_player_decision(
                        player=follower,
                        options=list(follower_combined_decision.keys()),
                        role="follower",
                        embed=follower_embed
                    )
                    return (follower, decision)

                # Prepare a list of tasks to gather
                tasks = [get_follower_decision(follower) for follower in followers]

                # Gather all tasks and wait for their completion
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Process the results
                for result in results:
                    if isinstance(result, Exception):
                        continue
                    follower, decision = result
                    follower_combined_decision[decision] += 1

                # Implement followers' combined actions
                if follower_combined_decision["Boost Ritual"]:
                    progress += min(2 * follower_combined_decision["Boost Ritual"], 8)

                    await ctx.send(
                        f"🔺 Followers boost the ritual by {min(2 * follower_combined_decision['Boost Ritual'], 8)}%!")
                if follower_combined_decision["Protect Champion"] > 0:
                    champion_stats["protection"] = True
                    champion_stats["shield_points"] += 50 * follower_combined_decision["Protect Champion"]
                    await ctx.send(f"🛡️ Followers shield the Champion with {champion_stats['shield_points']} points!")
                if follower_combined_decision["Empower Priest"] > 0 and priest:
                    priest_stats["healing_boost"] += 0.1 * follower_combined_decision["Empower Priest"]
                    await ctx.send(f"✨ Followers empower the Priest!")
                if follower_combined_decision["Sabotage Guardian"] > 0:
                    guardians_stats["damage_multiplier"] -= 0.1 * follower_combined_decision["Sabotage Guardian"]
                    guardians_stats["damage_multiplier"] = max(0.5, guardians_stats["damage_multiplier"])
                    await ctx.send(f"🌀 Followers sabotage the Guardian, reducing its damage!")
                if follower_combined_decision["Chant"]:
                    progress += 1 * follower_combined_decision["Chant"]
                    await ctx.send(
                        f"🎵 Followers chant, increasing the ritual by {1 * follower_combined_decision['Chant']}%!")
                if follower_combined_decision["Heal Champion"]:
                    total_healing = 50 * follower_combined_decision["Heal Champion"]
                    champion_stats["hp"] = min(champion_stats["hp"] + total_healing, champion_stats["max_hp"])
                    await ctx.send(f"💖 Followers heal the Champion for {total_healing} HP!")

                # Champion's decisions
                abilities_msg = "\n".join(f"{k}: {v}" for k, v in CHAMPION_ABILITIES.items())

                # Check if champion is AI or human
                if isinstance(champion, ShadowChampionAI):
                    # AI Champion decision
                    await ctx.send(f"👻 **{champion.mention} analyzes the battlefield...**")
                    champion_decision = await champion.make_decision(champion_stats, guardians_stats, progress, follower_combined_decision)
                    await champion.announce_decision(ctx, champion_decision, champion_stats, guardians_stats, progress)
                else:
                    # Human Champion decision
                    champion_embed = discord.Embed(
                        title="⚔️ Champion's Turn ⚔️",
                        description=f"{champion.mention}, choose your action:",
                        color=discord.Color.red()
                    )

                    # Add abilities with emojis
                    champion_embed.add_field(name="⚡ Smite", value="Deal damage to the Guardian", inline=True)
                    champion_embed.add_field(name="❤️ Heal", value="Recover some of your lost HP", inline=True)
                    haste_description = "Boost the ritual's progress"
                    if champion_stats["haste_cooldown"] > 0:
                        haste_description += f" (Cooldown: {champion_stats['haste_cooldown']} turns)"
                    champion_embed.add_field(name="🌀 Haste", value=haste_description, inline=True)
                    champion_embed.add_field(name="🛡️ Defend", value="Reduce incoming damage next turn", inline=True)
                    champion_embed.add_field(name="💔 Sacrifice", value="Advance the ritual by 20% at the cost of  400 HP",
                                             inline=True)

                    # Add a footer to the embed
                    champion_embed.set_footer(text="The fate of the ritual rests upon you.")

                    await ctx.send(f"It's {champion.mention}'s turn to make a decision, check DMs!")

                    valid_actions = ["Smite", "Heal", "Defend", "Sacrifice"]
                    if champion_stats["haste_cooldown"] == 0:
                        valid_actions.append("Haste")
                    else:
                        if not isinstance(champion, ShadowChampionAI):
                            await champion.send(f"'Haste' is on cooldown for {champion_stats['haste_cooldown']} more turns.")

                    try:
                        champion_decision = await asyncio.wait_for(
                            self.get_player_decision(
                                player=champion,
                                options=valid_actions,
                                role="champion",
                                embed=champion_embed
                            ),
                            timeout=TIMEOUT
                        )
                    except asyncio.TimeoutError:
                        await ctx.send(f"{champion.mention} took too long to decide! Defaulting to 'Smite'.")
                        champion_decision = "Smite"

                # Execute champion decision
                if champion_decision == "Smite":
                    guardians_stats["hp"] -= champion_stats["damage"]
                    if guardians_stats.get("shield_active"):
                        guardians_stats["hp"] += 200  # Guardian's shield absorbs some damage
                        guardians_stats["shield_active"] = False
                    await ctx.send(f"⚔️ The Champion smites the Guardian for {champion_stats['damage']} damage!")
                elif champion_decision == "Heal":
                    heal_amount = 200
                    champion_stats["hp"] = min(champion_stats["hp"] + heal_amount, champion_stats["max_hp"])
                    await ctx.send(f"❤️ The Champion heals for {heal_amount} HP!")
                elif champion_decision == "Haste":
                    progress += 15  # Increase progress
                    champion_stats["haste_cooldown"] = 3  # Haste will be unavailable for the next 3 turns
                    champion_stats["vulnerable"] = True
                    await ctx.send(f"🌀 The Champion uses Haste, advancing the ritual but becoming vulnerable!")
                elif champion_decision == "Defend":
                    champion_stats["defending"] = True
                    await ctx.send(f"🛡️ The Champion braces for the next attack!")
                elif champion_decision == "Sacrifice":
                    damage_to_self = 400
                    champion_stats["hp"] -= damage_to_self
                    progress += 20
                    await ctx.send(f"💔 The Champion sacrifices {damage_to_self} HP to advance the ritual!")

                def format_action(action):
                    """Formats action names by replacing underscores with spaces and capitalizing each word."""
                    return action.replace('_', ' ').title()

                # Reduce cooldowns and reset temporary statuses
                if champion_stats["haste_cooldown"] > 0:
                    champion_stats["haste_cooldown"] -= 1

                # Aesthetic improvements for the Ritual Progress embed
                progress_color = 0x4CAF50 if progress >= 80 else 0xFFC107 if progress >= 50 else 0xFF5722
                if progress >= 100 and champion_stats["hp"] > 0:
                    progress = 100
                em = discord.Embed(
                    title="🌑 Ritual Progress 🌑",
                    description=f"Turn {turn + 1}/{TOTAL_TURNS}",
                    color=progress_color
                )
                ritual_status = f"{progress_bar(progress, 100)} ({int(progress)}%)"
                champion_status = f"❤️ {int(champion_stats['hp'])}/{champion_stats['max_hp']} HP"
                guardians_status = f"😈 {phase_info['name']} ({int(guardians_stats['hp'])}/{guardians_stats['max_hp']} HP)"
                em.add_field(name="🔮 Ritual Completion",
                             value=ritual_status, inline=False)
                em.add_field(name=f"🛡️ {champion.name} (Champion)",
                             value=champion_status, inline=True)
                em.add_field(name="💀 Guardian",
                             value=guardians_status, inline=True)

                # Display priest and guardian buffs
                if champion_stats.get("damage") > default_champion_damage:
                    em.add_field(name="Priest's Blessing", value="🔥 Champion's power boosted", inline=True)
                if champion_stats.get("barrier_active"):
                    em.add_field(name="Priest's Barrier", value="🔰 Champion Protected", inline=True)
                if guardians_stats.get("cursed"):
                    em.add_field(name="Priest's Curse", value="😵 Guardian Weakened", inline=True)
                if guardians_stats.get("shield_active"):
                    em.add_field(name="Guardian's Shield", value="🔰 Active", inline=True)
                if guardians_stats.get("enraged"):
                    em.add_field(name="Guardian Enraged", value="🔥 Increased Damage", inline=True)
                if champion_stats.get("vulnerable"):
                    em.add_field(name="Champion Vulnerable", value="⚠️ Increased Damage Taken", inline=True)
                if guardians_stats.get("incapacitated_turns", 0) > 0:
                    em.add_field(name="Guardian Incapacitated",
                                 value=f"🛌 Incapacitated for {guardians_stats['incapacitated_turns']} more turn(s)",
                                 inline=True)

                if turn != 0 and embed_message_id:
                    old_message = await ctx.channel.fetch_message(embed_message_id)
                    await old_message.delete()

                message = await ctx.send(embed=em)
                embed_message_id = message.id

                # Decision Summary Embed
                decision_embed = discord.Embed(
                    title="🕯️ Actions This Turn 🕯️",
                    description="An overview of this turn's actions.",
                    color=0x8B0000
                )

                # Display Priest's Decision
                if priest:
                    priest_action = priest_decision if priest_decision else "No action"
                    decision_embed.add_field(name=f"🔮 {priest.name} (Priest)", value=priest_action, inline=False)

                # Display Guardian's Decision
                if guardians_stats["incapacitated_turns"] > 0:
                    guardian_action = "Incapacitated"
                else:
                    guardian_action = format_action(guardian_decision)  # Format the action name

                    guardian_action = guardian_decision.capitalize()
                decision_embed.add_field(name="💀 Guardian", value=guardian_action, inline=False)

                # Display Followers' Collective Decision
                followers_decisions = "\n".join(
                    [f"{action}: {count}" for action, count in follower_combined_decision.items() if count > 0])
                if followers_decisions:
                    decision_embed.add_field(name="🕯️ Followers", value=followers_decisions,
                                             inline=False)
                else:
                    decision_embed.add_field(name="🕯️ Followers", value="No actions taken",
                                             inline=False)

                # Display Champion's Decision
                decision_embed.add_field(name=f"🛡️ {champion.name} (Champion)", value=champion_decision, inline=False)

                # Add a footer for added menace
                decision_embed.set_footer(text="The ritual's energy intensifies...")

                # Send the Decision Summary Embed
                await ctx.send(embed=decision_embed)

                # Cleanup: Reset certain states for the next turn
                guardians_stats["damage_multiplier"] = 1.0
                if guardians_stats.get("cursed"):
                    del guardians_stats["cursed"]
                if champion_stats.get("damage") > default_champion_damage:
                    champion_stats["damage"] = default_champion_damage
                if champion_stats.get("protection") and champion_stats["shield_points"] <= 0:
                    champion_stats["protection"] = False

                # Regenerate Priest's mana
                if priest:
                    priest_stats["mana"] = min(priest_stats["mana"] + 10, priest_stats["max_mana"])

                await asyncio.sleep(15)

            # Post-Raid Outcome
            if progress >= 100 and champion_stats["hp"] > 0:
                progress = 100
                # Create an enhanced embed message

                users = [u.id for u in raid]
                random_user = random.choice(users)
                async with self.bot.pool.acquire() as conn:
                    # Fetch the luck value for the specified user (winner)
                    luck_query = await conn.fetchval(
                        'SELECT luck FROM profile WHERE "user" = $1;',
                        random_user,
                    )

                # Convert luck_query to float
                luck_query_float = float(luck_query)

                # Define gods with their boundaries
                gods = {
                    "Elysia": {"boundary_low": 0.9, "boundary_high": 1.1},
                    "Sepulchure": {"boundary_low": 0.75, "boundary_high": 1.5},
                    "Drakath": {"boundary_low": 0.3, "boundary_high": 2.0},
                }

                # Replace 'selected_god' with the actual selected god name (e.g., "Elysia")
                selected_god = "Sepulchure"  # Example, replace dynamically
                god_data = gods.get(selected_god)

                if not god_data:
                    raise ValueError(f"God {selected_god} not found.")

                boundary_low = god_data["boundary_low"]
                boundary_high = god_data["boundary_high"]

                # Normalize the user's luck value
                normalized_luck = (luck_query_float - boundary_low) / (boundary_high - boundary_low)
                normalized_luck = max(0.0, min(1.0, normalized_luck))  # Clamp between 0.0 and 1.0

                # Scale the divine weight
                weightdivine = 0.20 + (0.20 * normalized_luck)  # Example scaling factor
                rounded_weightdivine = round(weightdivine, 3)

                # Define weights for crate selection
                options = ['legendary', 'fortune', 'materials', 'divine']
                weights = [0.30, 0.30, 0.20, rounded_weightdivine]

                # Select a crate based on weights
                crate = randomm.choices(options, weights=weights)[0]

                embed = Embed(
                    title="🔥 The Ritual is Complete 🔥",
                    description=f"With a final surge of power, the ritual reaches its climax. A portal opens, and Sepulchure's presence is felt throughout the realm. As a reward for your unwavering devotion, one among you shall receive a **{crate} crate**. All participants are granted riches beyond measure.",
                    color=0x901C1C  # Dark color
                )

                # Add the image to the embed
                embed.set_image(url="https://i.ibb.co/G09cMBq/OIG-17.png")

                await ctx.send(embed=embed)
                await ctx.send(
                    f"🎉 Congratulations, <@{random_user}>! You have been chosen to receive a **{crate} crate**!")
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        f'UPDATE profile SET "crates_{crate}" = "crates_{crate}" + 1 WHERE "user" = $1;',
                        random_user,
                    )
                # Reward the participants.
                cash_reward = random.randint(20000, 50000)
                await self.bot.pool.execute(
                    'UPDATE profile SET money=money+$1 WHERE "user"=ANY($2);',
                    cash_reward,
                    users,
                )
                await ctx.send(
                    f"💰 All participants receive **${cash_reward}** as a token of Sepulchure's gratitude!"
                )

            else:
                await ctx.send(f"💔 The ritual failed to reach completion. Darkness retreats as the Guardian prevails.")

            await self.clear_raid_timer()
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")
            # Log the error if a logger is set up.

    async def convert_to_display_names(self):
        display_names = []

        for user_id in self.chaoslist:
            # Fetch the user object (if you only have user IDs in self.chaoslist)
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)

            if user:  # Ensure the user exists
                display_names.append(user.display_name)
            else:
                display_names.append(f"Unknown User ({user_id})")  # Fallback for missing users

        return display_names

    @is_gm()
    @commands.command(hidden=True, breif=("See who was in your last raid"))
    async def chaoslistold(self, ctx):
        try:
            if self.chaoslist is None:
                await ctx.send("Data on your most recent raid was not found")
            else:

                display_names = await self.convert_to_display_names()
                await ctx.send(content=f"Participants: {', '.join(display_names)}")
        except Exception as e:
            await ctx.send(e)


    @is_god()
    @raid_free()
    @commands.command(hidden=True, brief=_("Start a Drakath raid"))
    async def chaosspawnold(self, ctx, boss_hp: IntGreaterThan(0)):
        """[Drakath only] Starts a raid."""
        try:
            await self.set_raid_timer()

            # Define the channels where the raid messages will be sent
            channels = [
                self.bot.get_channel(1154244627822551060),  # This is the current channel where the command was invoked
                self.bot.get_channel(1199300319256006746),  # Replace with the actual channel ID
            ]

            async def send_to_channels(embed=None, content=None, view=None):
                """Helper function to send a message to all channels."""
                for channel in channels:
                    await channel.send(embed=embed, content=content, view=view)

            view = JoinView(
                Button(style=ButtonStyle.primary, label="Join the raid!"),
                message=_("You joined the raid."),
                timeout=60 * 15,
            )

            channel1 = self.bot.get_channel(1154244627822551060)
            channel2 = self.bot.get_channel(1199300319256006746)
            role_id1 = 1153880715419717672
            role_id2 = 1199302687083204649

            if channel1:
                role1 = ctx.guild.get_role(role_id1)
                if role1:
                    await channel1.send(content=f"{role1.mention}", allowed_mentions=discord.AllowedMentions(roles=True))

            if channel2:
                role2 = ctx.guild.get_role(role_id2)
                if role2:
                    await channel2.send(content=f"{role2.mention}", allowed_mentions=discord.AllowedMentions(roles=True))

            em = discord.Embed(
                title="Raid the Void",
                description=f"""
        In Drakath's name, unleash the storm,
        Raiders of chaos, in shadows swarm.
        No order, no restraint, just untamed glee,
        Drakath's chaos shall set us free.
    
        Eclipse the Void Conqueror has {boss_hp} HP and will be vulnerable in 15 Minutes
    
        **Only followers of Drakath may join.**""",
                color=0xFFB900,
            )
            em.set_image(url="https://i.imgur.com/YoszTlc.png")

            # Send the initial raid message and join button to both channels
            await send_to_channels(embed=em, view=view)


            if not self.bot.config.bot.is_beta:
                await asyncio.sleep(300)
                await send_to_channels(content="**The raid on the void will start in 10 minutes**")
                await asyncio.sleep(300)
                await send_to_channels(content="**The raid on the void will start in 5 minutes**")
                await asyncio.sleep(180)
                await send_to_channels(content="**The raid on the void will start in 2 minutes**")
                await asyncio.sleep(60)
                await send_to_channels(content="**The raid on the void will start in 1 minute**")
                await asyncio.sleep(30)
                await send_to_channels(content="**The raid on the void will start in 30 seconds**")
                await asyncio.sleep(20)
                await send_to_channels(content="**The raid on the void will start in 10 seconds**")
            else:
                await asyncio.sleep(300)
                await send_to_channels(content="**The raid on the void will start in 10 minutes**")
                await asyncio.sleep(300)
                await send_to_channels(content="**The raid on the void will start in 5 minutes**")
                await asyncio.sleep(180)
                await send_to_channels(content="**The raid on the void will start in 2 minutes**")
                await asyncio.sleep(60)
                await send_to_channels(content="**The raid on the void will start in 1 minute**")
                await asyncio.sleep(30)
                await send_to_channels(content="**The raid on the void will start in 30 seconds**")
                await asyncio.sleep(20)
                await send_to_channels(content="**The raid on the void will start in 10 seconds**")

            view.stop()

            await send_to_channels(content="**The raid on the facility started! Fetching participant data... Hang on!**")
            HowMany = 0

            async with self.bot.pool.acquire() as conn:
                raid = {}
                for u in view.joined:
                    if (
                            not (
                                    profile := await conn.fetchrow(
                                        'SELECT * FROM profile WHERE "user"=$1;', u.id
                                    )
                            )
                            or profile["god"] != "Drakath"
                    ):
                        continue
                    raid[u] = 250
                    HowMany = HowMany + 1

            await send_to_channels(content="**Done getting data!**")
            self.chaoslist = [u.id for u in raid.keys()]
            await send_to_channels(content=f"**{HowMany} followers joined!**")

            start = datetime.datetime.utcnow()

            while (
                    boss_hp > 0
                    and len(raid) > 0
                    and datetime.datetime.utcnow() < start + datetime.timedelta(minutes=45)
            ):
                target = random.choice(list(raid.keys()))

                dmg = random.randint(100, 300)
                raid[target] -= dmg
                if raid[target] > 0:
                    em = discord.Embed(
                        title="Eclipse attacks!",
                        description=f"{target} now has {raid[target]} HP!",
                        colour=0xFFB900,
                    )
                else:
                    em = discord.Embed(
                        title="Eclipse hits critical!",
                        description=f"{target} died!",
                        colour=0xFFB900,
                    )
                em.add_field(name="Damage", value=dmg)
                em.set_author(name=str(target), icon_url=target.display_avatar.url)
                em.set_thumbnail(url="https://i.imgur.com/YS4A6R7.png")
                await send_to_channels(embed=em)
                if raid[target] <= 0:
                    del raid[target]
                    if len(raid) == 0:
                        break

                if random.randint(1, 5) == 1:
                    await asyncio.sleep(4)
                    target = random.choice(list(raid.keys()))
                    raid[target] += 100
                    em = discord.Embed(
                        title=f"{target} uses Chaos Restore!",
                        description=f"It's super effective!\n{target} now has {raid[target]} HP!",
                        colour=0xFFB900,
                    )
                    em.set_author(name=str(target), icon_url=target.display_avatar.url)
                    em.set_thumbnail(url="https://i.imgur.com/md5dWFk.png")
                    await send_to_channels(embed=em)

                if random.randint(1, 5) == 1:
                    await asyncio.sleep(4)
                    if len(raid) >= 3:
                        targets = random.sample(list(raid.keys()), 3)
                    else:
                        targets = list(raid.keys())
                    for target in targets:
                        raid[target] -= 100
                        if raid[target] <= 0:
                            del raid[target]
                    em = discord.Embed(
                        title="Eclipse prepares a void pulse!",
                        description=f"It's super effective!\n{', '.join(str(u) for u in targets)} take 100 damage!",
                        colour=0xFFB900,
                    )
                    em.set_thumbnail(url="https://i.imgur.com/lDqNHua.png")
                    await send_to_channels(embed=em)

                dmg_to_take = sum(
                    25 if random.randint(1, 10) != 10 else random.randint(75, 100)
                    for u in raid
                )
                boss_hp -= dmg_to_take
                await asyncio.sleep(4)
                em = discord.Embed(
                    title="The power of Drakath's Followers attacks Eclipse!", colour=0xFF5C00
                )
                em.set_thumbnail(url="https://i.imgur.com/kf3zcLs.png")
                em.add_field(name="Damage", value=dmg_to_take)
                if boss_hp > 0:
                    em.add_field(name="HP left", value=boss_hp)
                else:
                    em.add_field(name="HP left", value="Dead!")
                await send_to_channels(embed=em)
                await asyncio.sleep(4)

            if boss_hp > 1 and len(raid) > 0:
                em = discord.Embed(
                    title="Defeat",
                    description="As Drakath's malevolent laughter echoes through the shattered realm, his followers stand "
                                "defeated before the overwhelming might of their vanquished foe, a stark reminder of "
                                "chaos's unyielding and capricious nature.",
                    color=0xFFB900,
                )
                em.set_image(url="https://i.imgur.com/s5tvHMd.png")
                await send_to_channels(embed=em)
                await self.clear_raid_timer()
            elif len(raid) == 0:
                em = discord.Embed(
                    title="Defeat",
                    description="Amidst the smoldering ruins and the mocking whispers of the chaotic winds, Drakath's "
                                "followers find themselves humbled by the boss's insurmountable power, their hopes dashed "
                                "like shattered illusions in the wake of their failure.",
                    color=0xFFB900,
                )
                em.set_image(url="https://i.imgur.com/UpWW3fF.png")
                await send_to_channels(embed=em)
                await self.clear_raid_timer()
            else:
                winner = random.choice(list(raid.keys()))
                try:
                    async with self.bot.pool.acquire() as conn:
                        # Fetch the luck value for the specified user (winner)
                        luck_query = await conn.fetchval(
                            'SELECT luck FROM profile WHERE "user" = $1;',
                            winner.id,
                        )

                    # Convert luck_query to float
                    luck_query_float = float(luck_query)

                    # Define gods with their boundaries
                    gods = {
                        "Elysia": {"boundary_low": 0.9, "boundary_high": 1.1},
                        "Sepulchure": {"boundary_low": 0.75, "boundary_high": 1.5},
                        "Drakath": {"boundary_low": 0.3, "boundary_high": 2.0},
                    }

                    # Replace 'selected_god' with the actual selected god name (e.g., "Elysia")
                    selected_god = "Drakath"  # Example, replace dynamically
                    god_data = gods.get(selected_god)

                    if not god_data:
                        raise ValueError(f"God {selected_god} not found.")

                    boundary_low = god_data["boundary_low"]
                    boundary_high = god_data["boundary_high"]

                    # Normalize the user's luck value
                    normalized_luck = (luck_query_float - boundary_low) / (boundary_high - boundary_low)
                    normalized_luck = max(0.0, min(1.0, normalized_luck))  # Clamp between 0.0 and 1.0

                    # Scale the divine weight
                    weightdivine = 0.20 + (0.20 * normalized_luck)  # Example scaling factor
                    rounded_weightdivine = round(weightdivine, 3)

                    # Define weights for crate selection
                    options = ['legendary', 'fortune', 'materials', 'divine']
                    weights = [0.30, 0.30, 0.20, rounded_weightdivine]

                    # Select a crate based on weights
                    crate = randomm.choices(options, weights=weights)[0]

                    try:
                        async with self.bot.pool.acquire() as conn:
                            await conn.execute(
                                f'UPDATE profile SET "crates_{crate}" = "crates_{crate}" + 1 WHERE "user" = $1;',
                                winner.id,
                            )

                    except Exception as e:
                        print(f"An error occurred: {e}")

                    em = discord.Embed(
                        title="Win!",
                        description=f"The forces aligned with Drakath have triumphed over Eclipse, wresting victory from the "
                                    f"clutches of chaos itself!\n{winner.mention} emerges as a true champion of anarchy, "
                                    f"earning a {crate}) crate from Drakath as a token of recognition for their unrivaled "
                                    f"prowess!",
                        color=0xFFB900,
                    )
                    em.set_thumbnail(url="https://i.imgur.com/3pg9Msj.png")
                    em.set_image(url="https://i.imgur.com/s5tvHMd.png")
                    em.add_field(name="Crate Found", value=crate)
                    await send_to_channels(embed=em)
                    await self.clear_raid_timer()
                except Exception:
                    em = discord.Embed(
                        title="Win!",
                        description=f"The forces aligned with Drakath have triumphed over Eclipse, wresting victory from the "
                                    f"clutches of chaos itself!\n{winner.mention} emerges as a true champion of anarchy, "
                                    f"earning a {crate}) crate from Drakath as a token of recognition for their unrivaled "
                                    f"prowess!",
                        color=0xFFB900,
                    )
                    em.set_thumbnail(url="https://i.imgur.com/3pg9Msj.png")
                    em.set_image(url="https://i.imgur.com/s5tvHMd.png")
                    await send_to_channels(embed=em)
                    await self.clear_raid_timer()
        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n"
            error_message += traceback.format_exc()
            await ctx.send(error_message)
            print(error_message)

    @commands.command()
    async def joinraid(self, ctx):
        if not self.raidactive:
            await ctx.send("No active raid to join right now!")
            return

        if ctx.author not in self.joined:
            self.joined.append(ctx.author)
            await ctx.send(f"{ctx.author.mention} has joined the raid!")
        else:
            await ctx.send(f"{ctx.author.mention}, you've already joined the raid!")



    def getpriceto(self, level: float):
        return sum(i * 25000 for i in range(1, int(level * 10) - 9))

    def getpricetohp(self, level: float):
        return 2 * sum(i * 15000 for i in range(1, int(level * 10) - 9))

    @commands.group(invoke_without_command=True, brief=_("Increase your raidstats"))
    @locale_doc
    async def increase(self, ctx):
        _(
            """Upgrade your raid damage or defense multiplier. These will affect your performance in raids and raidbattles."""
        )
        await ctx.send(
            _(
                "Use `{prefix}increase damage/defense` to upgrade your raid"
                " damage/defense multiplier by 10%."
            ).format(prefix=ctx.clean_prefix)
        )

    @user_cooldown(30, identifier="increase")
    @has_char()
    @increase.command(brief=_("Upgrade your raid damage"))
    @locale_doc
    async def damage(self, ctx):
        _("""Increase your raid damage.""")
        newlvl = ctx.character_data["atkmultiply"] + Decimal("0.1")
        price = self.getpriceto(newlvl)
        if ctx.character_data["money"] < price:
            return await ctx.send(
                _(
                    "Upgrading your weapon attack raid multiplier to {newlvl} costs"
                    " **${price}**, you are too poor."
                ).format(newlvl=newlvl, price=price)
            )
        if not await ctx.confirm(
                _(
                    "Upgrading your weapon attack raid multiplier to {newlvl} costs"
                    " **${price}**, proceed?"
                ).format(newlvl=newlvl, price=price)
        ):
            return
        async with self.bot.pool.acquire() as conn:
            if not await self.bot.has_money(ctx.author, price, conn=conn):
                return await ctx.send(
                    _(
                        "Upgrading your weapon attack raid multiplier to {newlvl} costs"
                        " **${price}**, you are too poor."
                    ).format(newlvl=newlvl, price=price)
                )
            await conn.execute(
                'UPDATE profile SET "atkmultiply"=$1, "money"="money"-$2 WHERE'
                ' "user"=$3;',
                newlvl,
                price,
                ctx.author.id,
            )
            await self.bot.log_transaction(
                ctx,
                from_=ctx.author.id,
                to=2,
                subject="Raid Stats Upgrade ATK",
                data={"Gold": price},
                conn=conn,
            )
        await ctx.send(
            _(
                "You upgraded your weapon attack raid multiplier to {newlvl} for"
                " **${price}**."
            ).format(newlvl=newlvl, price=price)
        )

    @user_cooldown(30, identifier="increase")
    @has_char()
    @increase.command(brief=_("Upgrade your raid damage"))
    @locale_doc
    async def health(self, ctx):
        _("""Increase your raid health.""")
        newlvl = ctx.character_data["hplevel"] + Decimal("0.1")
        healthpool = ctx.character_data["health"] + 5
        healthpoolcheck = ctx.character_data["health"] + 5 + 250
        price = self.getpricetohp(newlvl)
        if ctx.character_data["money"] < price:
            return await ctx.send(
                _(
                    "Upgrading your health pool to {healthpoolcheck} costs"
                    " **${price}**, you are too poor."
                ).format(healthpoolcheck=healthpoolcheck, price=price)
            )
        if not await ctx.confirm(
                _(
                    "Upgrading your health pool to {healthpoolcheck} costs"
                    " **${price}**, proceed?"
                ).format(healthpoolcheck=healthpoolcheck, price=price)
        ):
            return
        async with self.bot.pool.acquire() as conn:
            if not await self.bot.has_money(ctx.author, price, conn=conn):
                return await ctx.send(
                    _(
                        "Upgrading your health pool to {healthpoolcheck} costs"
                        " **${price}**, you are too poor."
                    ).format(healthpoolcheck=healthpoolcheck, price=price)
                )
            await conn.execute(
                'UPDATE profile SET "health"=$1, "money"="money"-$2 WHERE'
                ' "user"=$3;',
                healthpool,
                price,
                ctx.author.id,
            )
            await conn.execute(
                'UPDATE profile SET "hplevel"=$1 WHERE "user"=$2;',
                newlvl,
                ctx.author.id,
            )
            await self.bot.log_transaction(
                ctx,
                from_=ctx.author.id,
                to=2,
                subject="Raid Stats Upgrade HEALTH",
                data={"Gold": price},
                conn=conn,
            )
        await ctx.send(
            _(
                "You upgraded your health pool to {healthpoolcheck} for"
                " **${price}**."
            ).format(healthpoolcheck=healthpoolcheck, price=price)
        )

    @user_cooldown(30, identifier="increase")
    @has_char()
    @increase.command(brief=_("Upgrade your raid defense"))
    @locale_doc
    async def defense(self, ctx):
        _("""Increase your raid defense.""")
        newlvl = ctx.character_data["defmultiply"] + Decimal("0.1")
        price = self.getpriceto(newlvl)
        if ctx.character_data["money"] < price:
            return await ctx.send(
                _(
                    "Upgrading your shield defense raid multiplier to {newlvl} costs"
                    " **${price}**, you are too poor."
                ).format(newlvl=newlvl, price=price)
            )
        if not await ctx.confirm(
                _(
                    "Upgrading your shield defense raid multiplier to {newlvl} costs"
                    " **${price}**, proceed?"
                ).format(newlvl=newlvl, price=price)
        ):
            return
        async with self.bot.pool.acquire() as conn:
            if not await self.bot.has_money(ctx.author, price, conn=conn):
                return await ctx.send(
                    _(
                        "Upgrading your shield defense raid multiplier to {newlvl}"
                        " costs **${price}**, you are too poor."
                    ).format(newlvl=newlvl, price=price)
                )
            await conn.execute(
                'UPDATE profile SET "defmultiply"=$1, "money"="money"-$2 WHERE'
                ' "user"=$3;',
                newlvl,
                price,
                ctx.author.id,
            )
            await self.bot.log_transaction(
                ctx,
                from_=ctx.author.id,
                to=2,
                subject="Raid Stats Upgrade DEF",
                data={"Gold": price},
                conn=conn,
            )
        await ctx.send(
            _(
                "You upgraded your shield defense raid multiplier to {newlvl} for"
                " **${price}**."
            ).format(newlvl=newlvl, price=price)
        )

    import discord
    from discord.ext import commands
    from decimal import Decimal, getcontext
    import traceback

    # Set decimal precision high enough for your application's needs
    getcontext().prec = 28

    # Replace this with the actual ID you want to check against
    SPECIAL_USER_ID = 144932915682344960

    import discord
    from discord.ext import commands
    from decimal import Decimal
    import traceback

    import discord
    from discord.ext import commands
    from decimal import Decimal
    import traceback

    @commands.command()
    async def rspref(self, ctx):
        if ctx.author.id in self.toggle_list:
            self.toggle_list.remove(ctx.author.id)
            await ctx.send("You are now using the old raid stats.")
        else:
            self.toggle_list.add(ctx.author.id)
            await ctx.send("You are now using the new raid stats.")
            
    @is_donator()
    @celestial_vault_free()
    @is_gm()
    @commands.command(hidden=True, brief="Start a Celestial Vault raid")
    async def celestialvault(self, ctx):
        """[Donator only] Starts a special Celestial Vault raid that you can use once per day.
        
        The Celestial Guardian has unique elemental mechanics and special rewards for donators.
        Only donators can initiate this raid, but anyone can join and participate.
        """        
        try:
            # Set the cooldown for the user (1 day)
            await ctx.bot.redis.execute_command(
                "SET",
                f"celestial:vault:{ctx.author.id}",
                "used",
                "EX",
                302400,  # 24 hours in seconds
            )
            
            await ctx.message.delete()
            await self.set_raid_timer()
            
            # Dictionary to track who has used their survival ability
            donator_survival_used = set()
            
            # Set up the celestial guardian boss (higher HP and damage than Ragnarok)
            guardian_hp = 100000
            self.boss = {
                "hp": guardian_hp, 
                "initial_hp": guardian_hp, 
                "min_dmg": 2000, 
                "max_dmg": 3500,
                "current_element": "fire",  # Starting element
                "phase": 1,  # Boss starts in phase 1
                "round": 0   # Track rounds for enrage mechanic
            }
            
            # Elements and their strengths/weaknesses
            elements = ["fire", "water", "earth", "air"]
            element_strengths = {
                "fire": "air",    # Fire strong against air
                "water": "fire",  # Water strong against fire
                "earth": "water", # Earth strong against water
                "air": "earth"    # Air strong against earth
            }
            
            self.joined = []
            self.celestial_elements = {}
            
            # Setup raid preparation
            channels_ids = [1313482408242184213, 1232708183835803791]
            
            # Create the embed for raid announcement
            fi = discord.File("assets/other/celestialguardian.webp")
            em = discord.Embed(
                title="Celestial Vault - Ancient Guardian Appeared",
                description=(
                    f"A Celestial Guardian with **{self.boss['hp']:,.0f} HP** has appeared! It guards the sacred Celestial Vault!\n\n"
                    f"**Current Element:** {self.boss['current_element'].capitalize()}\n"
                    f"The guardian will be vulnerable in 5 minutes! Join quickly to prepare for battle!"
                ),
                color=0x7289DA,  # Special blue/purple color for the celestial raid
            )
            
            em.set_image(url="attachment://celestialguardian.webp")
            em.set_thumbnail(url=ctx.author.display_avatar.url)
            em.set_footer(text=f"Raid initiated by {ctx.author.name} | Each player will be assigned a random element")
            
            # Use the JoinView for people to join the raid
            view = JoinView(
                Button(style=ButtonStyle.primary, label="Join the Celestial Raid!"),
                message="You joined the Celestial Vault raid.",
                timeout=60 * 5,  # 5 minutes
            )
            
            # Send announcement to all channels
            message_ids = []
            try:
                for channel_id in channels_ids:
                    try:
                        channel = self.bot.get_channel(channel_id)
                        if channel:
                            fi = File("assets/other/celestialguardian.webp")
                            sent_msg = await channel.send(embed=em, file=fi, view=view)
                            message_ids.append(sent_msg.id)
                    except Exception as e:
                        error_message = f"Error in channel with ID {channel_id}: {e}. continuing.."
                        await ctx.send(error_message)
                        print(error_message)
                        continue
                
                self.boss.update(message=message_ids)
                
                # Mention raid ping role
                if self.bot.config.bot.is_beta:
                    for channel_id in channels_ids:
                        try:
                            channel = self.bot.get_channel(channel_id)
                            if channel:
                                role_id = 1199307259965079552
                                role = discord.utils.get(ctx.guild.roles, id=role_id)
                                content = f"{role.mention} A Celestial Guardian has appeared! 5 minutes until battle begins..."
                                await channel.send(content, allowed_mentions=discord.AllowedMentions(roles=True))
                        except Exception as e:
                            continue
                
                # Set raid flags
                self.raid_preparation = True
                self.raidactive = True
                
                # Countdown messages
                time_intervals = [120, 120, 60, 30, 20, 10]
                messages = [
                    "**The Celestial Guardian will be vulnerable in 3 minutes**",
                    "**The Celestial Guardian will be vulnerable in 1 minute**",
                    "**The Celestial Guardian will be vulnerable in 30 seconds**",
                    "**The Celestial Guardian will be vulnerable in 20 seconds**",
                    "**The Celestial Guardian will be vulnerable in 10 seconds**", 
                    "**The Celestial Guardian is gathering elemental power... Prepare!**"
                ]
                
                for interval, message in zip(time_intervals, messages):
                    await asyncio.sleep(interval)
                    for channel_id in channels_ids:
                        try:
                            channel = self.bot.get_channel(channel_id)
                            if channel:
                                await channel.send(message)
                        except Exception as e:
                            continue
            
            except Exception as e:
                error_message = f"Unexpected error in Celestial Vault: {e}"
                await ctx.send(error_message)
                print(error_message)
                print(traceback.format_exc())
                self.raidactive = False
                return
            
            # Stop the join view
            view.stop()
            
            # Announce the raid is starting
            for channel_id in channels_ids:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    await channel.send("**The Celestial Guardian is now vulnerable! Gathering participant data...**")
            
            # Collect participants
            self.joined.extend(view.joined)
            
            # Add donators who are not already in the raid (as a bonus perk for donators)
            async with self.bot.pool.acquire() as conn:
                # Fetch all donators with tier >= 1
                donator_ids = await conn.fetch(
                    '''SELECT "user" FROM profile WHERE "tier" >= 1'''
                )
                donator_ids = [record['user'] for record in donator_ids]
                
                # Add donators who aren't already in the raid
                for user_id in donator_ids:
                    if any(u.id == user_id for u in self.joined):
                        continue  # Skip if already joined
                        
                    user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                    if user:
                        self.joined.append(user)
            
            # Process participants and assign random elements
            async with self.bot.pool.acquire() as conn:
                for u in self.joined:
                    profile = await conn.fetchrow('SELECT * FROM profile WHERE "user"=$1;', u.id)
                    if not profile:
                        # User doesn't have a profile, skip
                        continue
                    
                    # Get raid stats with potential donator bonus
                    is_donator = profile["tier"] >= 1
                    donator_bonus = 1.2 if is_donator else 1.0  # 20% bonus for donators
                    
                    dmg, deff = await self.bot.get_raidstats(
                        u,
                        atkmultiply=float(profile["atkmultiply"]) * donator_bonus,
                        defmultiply=float(profile["defmultiply"]) * donator_bonus,
                        classes=profile["class"],
                        race=profile["race"],
                        guild=profile["guild"],
                        conn=conn,
                    )
                    
                    # Calculate raid HP - higher than normal
                    stathp = float(profile["stathp"]) * 50 * donator_bonus
                    level = rpgtools.xptolevel(profile["xp"])
                    raidhp = (float(profile["health"]) + 200 + (level * 15) + stathp) * donator_bonus
                    
                    # Assign random element to the player
                    player_element = randomm.choice(elements)
                    self.celestial_elements[u.id] = player_element
                    
                    # Store raid stats - ensure all numeric values are floats
                    self.raid[(u, "user")] = {
                        "hp": float(raidhp), 
                        "armor": float(deff), 
                        "damage": float(dmg),
                        "element": player_element,
                        "is_donator": is_donator
                    }
            
            raiders_joined = len(self.raid)
            
            # Announce the raid is ready to begin
            for channel_id in channels_ids:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    await channel.send(f"**Celestial Vault raid is starting with {raiders_joined} raiders!**")
                    
                    # Send an embed with player element assignments
                    element_embed = discord.Embed(
                        title="Element Assignments",
                        description="Each raider has been assigned an elemental affinity:",
                        color=0x7289DA
                    )
                    
                    # Group users by element for cleaner display
                    element_groups = {element: [] for element in elements}
                    for (user, _), data in self.raid.items():
                        if _ == "user":  # Only process actual users
                            element_groups[data["element"]].append(user.name)
                    
                    # Add fields for each element group
                    for element, users in element_groups.items():
                        if users:  # Only add non-empty element groups
                            user_list = ", ".join(users[:10])
                            if len(users) > 10:
                                user_list += f" and {len(users)-10} more"
                            element_embed.add_field(
                                name=f"{element.capitalize()} Element ({len(users)})", 
                                value=user_list,
                                inline=False
                            )
                    
                    await channel.send(embed=element_embed)
            
            # Start the raid
            start = datetime.datetime.utcnow()
            round_count = 0
            
            # Main raid loop
            while (
                self.boss["hp"] > 0
                and len(self.raid) > 0
                and datetime.datetime.utcnow() < start + datetime.timedelta(minutes=60)
            ):
                round_count += 1
                self.boss["round"] = round_count
                
                # Check if we need to switch to phase 2
                if self.boss["hp"] <= self.boss["initial_hp"] / 2 and self.boss["phase"] == 1:
                    self.boss["phase"] = 2
                    self.boss["min_dmg"] *= 1.5  # Increase damage in phase 2
                    self.boss["max_dmg"] *= 1.5
                    
                    phase_change_embed = discord.Embed(
                        title="The Celestial Guardian enters Phase 2!",
                        description="The guardian channels cosmic energy, growing more powerful!",
                        color=0xFF5C00
                    )
                    for channel_id in channels_ids:
                        channel = self.bot.get_channel(channel_id)
                        if channel:
                            await channel.send(embed=phase_change_embed)
                
                # Change element every 3 rounds
                if round_count % 3 == 0:
                    old_element = self.boss["current_element"]
                    # Choose a different element
                    new_element = old_element
                    while new_element == old_element:
                        new_element = randomm.choice(elements)
                    self.boss["current_element"] = new_element
                    
                    element_change_embed = discord.Embed(
                        title=f"The Guardian's Element Changes!",
                        description=f"The Celestial Guardian shifts from {old_element.capitalize()} to {new_element.capitalize()}!",
                        color=0x7289DA
                    )
                    for channel_id in channels_ids:
                        channel = self.bot.get_channel(channel_id)
                        if channel:
                            await channel.send(embed=element_change_embed)
                
                # Guardian enrages every 10 rounds
                if round_count % 10 == 0:
                    self.boss["min_dmg"] *= 1.2
                    self.boss["max_dmg"] *= 1.2
                    
                    enrage_embed = discord.Embed(
                        title="The Celestial Guardian Enrages!",
                        description="The guardian's attacks become more devastating!",
                        color=0xFF0000
                    )
                    for channel_id in channels_ids:
                        channel = self.bot.get_channel(channel_id)
                        if channel:
                            await channel.send(embed=enrage_embed)
                
                # Guardian attacks a random raider
                (target, participant_type) = random.choice(list(self.raid.keys()))
                base_dmg = random.randint(self.boss["min_dmg"], self.boss["max_dmg"])
                
                # Apply elemental modifiers
                guardian_element = self.boss["current_element"]
                target_element = self.raid[(target, participant_type)].get("element", "none")
                
                # Calculate elemental damage modifier
                elemental_modifier = 1.0
                if element_strengths.get(guardian_element) == target_element:
                    # Guardian's element is strong against target's element
                    elemental_modifier = 1.5
                    damage_type = "super effective"
                elif element_strengths.get(target_element) == guardian_element:
                    # Target's element is strong against guardian's element
                    elemental_modifier = 0.5
                    damage_type = "not very effective"
                else:
                    damage_type = "normal"
                
                # Apply the modifier
                # Convert to float to avoid Decimal * float error
                modified_dmg = float(base_dmg) * elemental_modifier
                
                # Calculate final damage after armor
                armor = float(self.raid[(target, participant_type)]["armor"])
                finaldmg = float(self.getfinaldmg(modified_dmg, armor))
                self.raid[(target, participant_type)]["hp"] = float(self.raid[(target, participant_type)]["hp"]) - finaldmg
                
                # Create attack embed
                em = discord.Embed(
                    title=f"Celestial Guardian used {guardian_element.capitalize()} Attack!", 
                    colour=0xFFB900
                )
                
                # Handle player health/survival
                if self.raid[(target, participant_type)]["hp"] > 0:  # If target is still alive
                    description = f"{target.mention if participant_type == 'user' else target} now has {self.raid[(target, participant_type)]['hp']:.0f} HP!"
                    em.description = description
                    em.add_field(name="Base Damage", value=f"{base_dmg:.0f}")
                    em.add_field(name="Elemental Effect", value=f"{damage_type.capitalize()} ({elemental_modifier:.1f}x)")
                    em.add_field(name="Shield", value=f"{self.raid[(target, participant_type)]['armor']:.0f}")
                    em.add_field(name="Final Damage", value=f"{finaldmg:.0f}")
                else:  # Player at 0 HP
                    survived = False
                    
                    # Check if target is a donator and hasn't used their survival ability
                    if participant_type == "user" and target.id not in donator_survival_used:
                        is_donator = self.raid[(target, participant_type)].get("is_donator", False)
                        
                        if is_donator:
                            # Donator survival mechanic - restore 25% HP
                            max_hp = float(self.raid[(target, participant_type)]["hp"]) + float(finaldmg)  # Original HP
                            restore_amount = max_hp * 0.25
                            self.raid[(target, participant_type)]["hp"] = float(restore_amount)
                            donator_survival_used.add(target.id)
                            
                            description = f"✨ {target.mention}'s donator blessing allowed them to survive with {restore_amount:.0f} HP!"
                            em.description = description
                            em.add_field(name="Base Damage", value=f"{base_dmg:.0f}")
                            em.add_field(name="Elemental Effect", value=f"{damage_type.capitalize()} ({elemental_modifier:.1f}x)")
                            em.add_field(name="Shield", value=f"{self.raid[(target, participant_type)]['armor']:.0f}")
                            em.add_field(name="Final Damage", value=f"{finaldmg:.0f}")
                            survived = True
                    
                    # Handle death if they didn't survive
                    if not survived:
                        description = f"{target.mention if participant_type == 'user' else target} was banished from the Celestial Vault!"
                        em.description = description
                        em.add_field(name="Base Damage", value=f"{base_dmg:.0f}")
                        em.add_field(name="Elemental Effect", value=f"{damage_type.capitalize()} ({elemental_modifier:.1f}x)")
                        em.add_field(name="Shield", value=f"{self.raid[(target, participant_type)]['armor']:.0f}")
                        em.add_field(name="Final Damage", value=f"{finaldmg:.0f}")
                        del self.raid[(target, participant_type)]
                
                # Set author and thumbnail for the message
                if participant_type == "user":
                    em.set_author(name=str(target), icon_url=target.display_avatar.url)
                else:
                    em.set_author(name=str(target))
                
                # Get appropriate element image URL
                element_icon = f"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_{guardian_element}attack.webp"
                em.set_thumbnail(url=element_icon)
                
                # Send attack message to all channels
                for channel_id in channels_ids:
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        await channel.send(embed=em)
                
                # Calculate damage from raiders to the guardian
                total_dmg = 0
                for (raider, raider_type), stats in self.raid.items():
                    base_damage = stats["damage"]
                    raider_element = stats.get("element", "none")
                    
                    # Apply elemental modifiers for raiders too
                    raider_modifier = 1.0
                    if element_strengths.get(raider_element) == guardian_element:
                        # Raider's element is strong against guardian's element
                        raider_modifier = 2.0  # Higher multiplier for players
                    elif element_strengths.get(guardian_element) == raider_element:
                        # Guardian's element is strong against raider's element
                        raider_modifier = 0.5
                    
                    # Add to total damage
                    # Convert to float to avoid Decimal * float error
                    total_dmg += float(base_damage) * raider_modifier
                
                # Update boss HP
                self.boss["hp"] = float(self.boss["hp"]) - float(total_dmg)
                
                # Create progress bar
                hp_percent = max(0, float(self.boss["hp"]) / float(self.boss["initial_hp"]))
                bar_length = 20
                filled_length = int(hp_percent * bar_length)
                bar = '█' * filled_length + '░' * (bar_length - filled_length)
                
                await asyncio.sleep(4)  # Delay between attack messages
                
                # Create raid attack embed
                em = discord.Embed(title="The raid attacked the Celestial Guardian!", colour=0xFF5C00)
                em.set_thumbnail(url=f"https://storage.googleapis.com/fablerpg-f74c2.appspot.com/295173706496475136_attackcelestial.webp")
                em.add_field(name="Combined Damage", value=f"{total_dmg:,.0f}")
                
                if self.boss["hp"] > 0:
                    health_percent = (float(self.boss["hp"]) / float(self.boss["initial_hp"])) * 100
                    em.add_field(name="Guardian HP", value=f"{self.boss['hp']:,.0f} ({health_percent:.1f}%)")
                    em.add_field(name="Health", value=f"`{bar}` {hp_percent:.0%}", inline=False)
                else:
                    em.add_field(name="Guardian HP", value="Defeated!")
                    em.add_field(name="Health", value="`░░░░░░░░░░░░░░░░░░░░` 0%", inline=False)
                
                for channel_id in channels_ids:
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        await channel.send(embed=em)
                
                await asyncio.sleep(4)  # Delay between rounds
            
            # Raid has finished - process results
            raid_duration = datetime.datetime.utcnow() - start
            minutes = (raid_duration.seconds % 3600) // 60
            seconds = raid_duration.seconds % 60
            summary_duration = f"{minutes} minutes, {seconds} seconds"
            
            # Handle failure (all raiders died)
            if len(self.raid) == 0:
                for channel_id in channels_ids:
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        await channel.send("**All raiders have been banished from the Celestial Vault!**")
                
                summary_text = (
                    "The raid was defeated! The Celestial Guardian had "
                    f"**{self.boss['hp']:,.0f}** health remaining. Better luck next time."
                )
                
                try:
                    summary = (
                        "**Celestial Vault Raid Result:**\n"
                        f":small_red_triangle: Initial Health: **{self.boss['initial_hp']:,.0f}**\n"
                        f":small_red_triangle: {summary_text}\n"
                        f":small_red_triangle: Raiders joined: **{raiders_joined}**\n"
                        f":small_red_triangle: Duration: **{summary_duration}**"
                    )
                    
                    summary_channel = self.bot.get_channel(1199299514490683392)
                    await summary_channel.send(summary)
                    
                    self.raid.clear()
                    await self.clear_raid_timer()
                except Exception as e:
                    await ctx.send(f"An error occurred while processing raid results: {e}")
            
            # Handle success (boss defeated)
            elif self.boss["hp"] < 1:
                await ctx.channel.set_permissions(
                    ctx.guild.default_role,
                    overwrite=self.allow_sending,
                )
                
                # Keep only real users for rewards
                self.raid = {k: v for k, v in self.raid.items() if k[1] == "user"}
                survivors = len(self.raid)
                
                # Create reward embed
                reward_embed = discord.Embed(
                    title="The Celestial Vault Reveals Its Treasures!",
                    description=(
                        f"The Celestial Guardian has been defeated in **{summary_duration}**!\n"
                        f"The Celestial Vault opens, revealing treasures for all **{survivors}** survivors!\n\n"
                        "Each survivor receives:"
                    ),
                    color=0xFFD700  # Gold color
                )
                
                # Calculate rewards - higher quality loot based on raid size
                loot_quality = "legendary" if survivors <= 10 else "magic" if survivors <= 25 else "rare"
                reward_embed.add_field(
                    name="Treasure Chest", 
                    value=f"1x {loot_quality.capitalize()} Crate per survivor"
                )
                
                # Add XP boost for all survivors
                reward_embed.add_field(
                    name="Celestial Blessing", 
                    value="+20% XP for 1 hour"
                )
                
                # Add gold for all survivors
                gold_reward = min(100000, 500000 // survivors)
                reward_embed.add_field(
                    name="Gold", 
                    value=f"{gold_reward:,} gold per survivor"
                )
                
                # Send rewards message
                for channel_id in channels_ids:
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        await channel.send(embed=reward_embed)
                
                # Distribute the actual rewards
                async with self.bot.pool.acquire() as conn:
                    for (user, _) in self.raid.keys():
                        # Give crate
                        await conn.execute(
                            f'UPDATE profile SET "crates_{loot_quality}"="crates_{loot_quality}"+1 WHERE "user"=$1;',
                            user.id
                        )
                        
                        # Give gold
                        await conn.execute(
                            'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                            gold_reward,
                            user.id
                        )
                        
                        # Apply XP boost
                        await self.bot.redis.execute_command(
                            "SET",
                            f"celestial:xpboost:{user.id}",
                            "active",
                            "EX",
                            3600  # 1 hour
                        )
                
                # Log the raid result
                try:
                    summary = (
                        "**Celestial Vault Raid Result:**\n"
                        f":tada: Initial Health: **{self.boss['initial_hp']:,.0f}**\n"
                        f":tada: Defeated in: **{summary_duration}**\n"
                        f":tada: Survivors: **{survivors}/{raiders_joined}**\n"
                        f":tada: Rewards: **{loot_quality.capitalize()} Crate, {gold_reward:,} gold, +20% XP boost**"
                    )
                    
                    summary_channel = self.bot.get_channel(1199299514490683392)
                    await summary_channel.send(summary)
                    
                    self.raid.clear()
                    await self.clear_raid_timer()
                except Exception as e:
                    await ctx.send(f"An error occurred while processing raid rewards: {e}")
            
            # Handle timeout
            else:
                for channel_id in channels_ids:
                    channel = self.bot.get_channel(channel_id)
                    if channel:
                        await channel.send("**The raid timed out after 60 minutes!**")
                
                self.raid.clear()
                await self.clear_raid_timer()
        except Exception as e:
            await ctx.send(e)

    @has_char()
    @commands.command(aliases=["rs"], brief=_("View your raid stats or compare two players"))
    @locale_doc
    async def raidstats(self, ctx, player1: discord.Member = None, player2: discord.Member = None):

        if ctx.author.id not in self.toggle_list:

            # Execute code if the ID matches one of the specified IDs
            # Old raidstats implementation
            _(
                """View your raidstats. These will affect your performance in raids and raidbattles."""
            )

            if player1:
                target_player = player1
            else:
                target_player = ctx.author

            try:
                # Fetch class, attack multiplier, defense multiplier, health, and health per level
                query = '''
                                SELECT p."class", p."atkmultiply", p."defmultiply", p."health", p."hplevel", 
                                       p."guild", p."xp", p."statdef", p."statatk", p."stathp",
                                       a."hp" as amulet_hp
                                FROM profile p
                                LEFT JOIN amulets a ON p."user" = a."user_id" AND a."equipped" = TRUE
                                WHERE p."user" = $1;
                            '''
                result = await self.bot.pool.fetch(query, target_player.id)

                if result:
                    player_data = result[0]
                    level = rpgtools.xptolevel(player_data["xp"])
                    statdeff = player_data["statdef"] * Decimal("0.1")
                    statatk = player_data["statatk"] * Decimal("0.1")
                    atk = player_data["atkmultiply"] + statatk
                    deff = player_data["defmultiply"] + statdeff

                    stathp = player_data["stathp"] * 50
                    base = 200 + (level * 15)
                    amulet_hp = player_data["amulet_hp"] or 0  # Handle null case
                    hp = player_data["health"] + stathp + base + amulet_hp
                    hplevel = player_data["hplevel"]
                    guild = player_data["guild"]
                    hpprice = self.getpricetohp(hplevel + Decimal("0.1"))
                    atkp = self.getpriceto(atk + Decimal("0.1") - statatk)
                    deffp = self.getpriceto(deff + Decimal("0.1") - statdeff)
                    classes = [class_from_string(c) for c in player_data["class"]]

                    if buildings := await self.bot.get_city_buildings(player_data["guild"]):
                        atk += Decimal("0.1") * buildings["raid_building"]
                        deff += Decimal("0.1") * buildings["raid_building"]

                    async with self.bot.pool.acquire() as conn:
                        dmg, defff = await self.bot.get_raidstats(target_player, conn=conn)

                    # Sanitize atk and deff to prevent negative multipliers
                    atk = max(float(atk), 0)
                    deff = max(float(deff), 0)


                    embed = discord.Embed(
                        title=f"{target_player.display_name}'s Raid Multipliers",
                        description=(
                            f"**Damage Multiplier:** x{atk}\n"
                            f"**Upgrading:** ${int(atkp)}\n\n"  # Removed decimal
                            f"**Health Multiplier:** x{hplevel}\n"
                            f"**Upgrading:** ${int(hpprice)}\n\n"  # Removed decimal
                            f"**Defense Multiplier:** x{deff}\n"
                            f"**Upgrading:** ${int(deffp)}\n\n"  # Removed decimal
                            f"**Player's Damage:** {dmg}\n"
                            f"**Player's Defense:** {defff}\n"
                            f"**Player's Health:** {hp}"
                        ),
                        color=0x00ff00,  # You can change the color code as needed
                    )
                else:
                    embed = discord.Embed(
                        description="❌ Player's data could not be retrieved.",
                        color=0xFF0000
                    )

            except Exception as e:
                error_message = f"Error occurred: {e}\n{traceback.format_exc()}"
                await ctx.send(error_message)
                print(error_message)
                return

            await ctx.send(embed=embed)

        else:
            # New raidstats implementation
            _(
                """View your raid stats or compare two players' raid stats. These stats will affect performance in raids and raid battles."""
            )

            # Function to fetch and process player data
            async def get_player_data(player):
                try:
                    query = '''
                        SELECT "class", "atkmultiply", "defmultiply", "health", "hplevel", 
                               "guild", "xp", "statdef", "statatk", "stathp" 
                        FROM profile 
                        WHERE "user" = $1;
                    '''
                    result = await self.bot.pool.fetch(query, player.id)

                    if not result:
                        return None

                    player_data = result[0]
                    level = rpgtools.xptolevel(player_data["xp"])
                    statdeff = player_data["statdef"] * Decimal("0.1")
                    statatk = player_data["statatk"] * Decimal("0.1")
                    atk = player_data["atkmultiply"] + statatk
                    deff = player_data["defmultiply"] + statdeff

                    stathp = player_data["stathp"] * 50
                    base = 200 + (level * 15)
                    hp = player_data["health"] + stathp + base
                    hplevel = player_data["hplevel"]
                    guild = player_data["guild"]
                    hpprice = self.getpricetohp(hplevel + Decimal("0.1"))
                    atkp = self.getpriceto(atk + Decimal("0.1") - statatk)
                    deffp = self.getpriceto(deff + Decimal("0.1") - statdeff)
                    classes = [class_from_string(c) for c in player_data["class"]]

                    if buildings := await self.bot.get_city_buildings(player_data["guild"]):
                        atk += Decimal("0.1") * buildings["raid_building"]
                        deff += Decimal("0.1") * buildings["raid_building"]

                    async with self.bot.pool.acquire() as conn:
                        dmg, defff = await self.bot.get_raidstats(player, conn=conn)

                    # Sanitize atk and deff to prevent negative multipliers
                    atk = max(float(atk), 0)
                    deff = max(float(deff), 0)

                    # Format multipliers to one decimal place
                    atk = float(f"{atk:.1f}")
                    deff = float(f"{deff:.1f}")
                    hplevel = float(f"{hplevel:.1f}")

                    # Convert Decimal and integer values to float for consistency
                    dmg = float(dmg)
                    defff = float(defff)
                    hp = float(hp)
                    hpprice = float(hpprice)
                    atkp = float(atkp)
                    deffp = float(deffp)


                    return {
                        "player": player,
                        "atk": atk,
                        "deff": deff,
                        "hp": hp,
                        "hplevel": hplevel,
                        "hpprice": hpprice,
                        "atkp": atkp,
                        "deffp": deffp,
                        "dmg": dmg,
                        "defff": defff,
                    }
                except Exception as e:
                    error_message = f"Error fetching data for {player.display_name}: {e}\n{traceback.format_exc()}"
                    await ctx.send(error_message)
                    print(error_message)
                    return None

            # Function to compare two players
            def compare_players(data1, data2):
                # Define a scoring system with sanitized atk and deff
                power1 = (max(data1["atk"], 0) * data1["dmg"]) + (max(data1["deff"], 0) * data1["defff"]) + data1["hp"]
                power2 = (max(data2["atk"], 0) * data2["dmg"]) + (max(data2["deff"], 0) * data2["defff"]) + data2["hp"]

                # Determine the difference
                difference = power1 - power2
                threshold = max(power1, power2) * 0.10  # 5% threshold for uncertainty

                if abs(difference) < threshold:
                    # Power method is too close; perform combat simulation

                    def simulate_combat(attacker_first=True):
                        # Initialize HPs
                        p1_hp = data1["hp"]
                        p2_hp = data2["hp"]

                        if attacker_first:
                            # Player 1 attacks Player 2
                            damage = data1["dmg"] - data2["defff"]
                            damage = max(damage, 0)
                            p2_hp -= damage

                            # Player 2 retaliates if still alive
                            if p2_hp > 0:
                                damage = data2["dmg"] - data1["defff"]
                                damage = max(damage, 0)
                                p1_hp -= damage

                                # Player 1 attacks again if still alive
                                if p1_hp > 0:
                                    damage = data1["dmg"] - data2["defff"]
                                    damage = max(damage, 0)
                                    p2_hp -= damage
                        else:
                            # Player 2 attacks Player 1
                            damage = data2["dmg"] - data1["defff"]
                            damage = max(damage, 0)
                            p1_hp -= damage

                            # Player 1 retaliates if still alive
                            if p1_hp > 0:
                                damage = data1["dmg"] - data2["defff"]
                                damage = max(damage, 0)
                                p2_hp -= damage

                                # Player 2 attacks again if still alive
                                if p2_hp > 0:
                                    damage = data2["dmg"] - data1["defff"]
                                    damage = max(damage, 0)
                                    p1_hp -= damage

                        # Determine outcome
                        if p1_hp > 0 and p2_hp <= 0:
                            return 'player1'
                        elif p2_hp > 0 and p1_hp <= 0:
                            return 'player2'
                        elif p1_hp > p2_hp:
                            return 'player1'
                        elif p2_hp > p1_hp:
                            return 'player2'
                        else:
                            return 'tie'

                    # Simulate both strike orders
                    outcome_first_p1 = simulate_combat(attacker_first=True)
                    outcome_first_p2 = simulate_combat(attacker_first=False)

                    # Analyze outcomes
                    if outcome_first_p1 == outcome_first_p2:
                        if outcome_first_p1 == 'player1':
                            result = f"🏆 **{data1['player'].display_name}** would win the raid battle against **{data2['player'].display_name}**."
                            method_used = "Combat Simulation (Player 1 strikes first)"
                        elif outcome_first_p1 == 'player2':
                            result = f"🏆 **{data2['player'].display_name}** would win the raid battle against **{data1['player'].display_name}**."
                            method_used = "Combat Simulation (Player 1 strikes first)"
                        else:
                            result = "⚖️ **The outcome is uncertain; the players are too closely matched.**"
                            method_used = "Combat Simulation (Player 1 strikes first)"
                    else:
                        # Outcomes differ based on who strikes first
                        result = (
                            "⚖️ **The outcome depends on who strikes first; it's too close to call definitively.**\n\n"
                            f"🔹 When **{data1['player'].display_name}** strikes first:\n {'🏆 ' + data1['player'].display_name + ' wins.' if outcome_first_p1 == 'player1' else '🏆 ' + data2['player'].display_name + ' wins.' if outcome_first_p1 == 'player2' else '⚖️ Tie.'}\n"
                            f"\n🔹 When **{data2['player'].display_name}** strikes first:\n {'🏆 ' + data1['player'].display_name + ' wins.' if outcome_first_p2 == 'player1' else '🏆 ' + data2['player'].display_name + ' wins.' if outcome_first_p2 == 'player2' else '⚖️ Tie.'}"
                        )
                        method_used = "Combat Simulation (Both strike orders)"

                    return result, method_used
                else:
                    # Use power-based comparison
                    if difference > 0:
                        result = f"🏆 **{data1['player'].display_name}** is more likely to win the raid battle against **{data2['player'].display_name}**."
                    else:
                        result = f"🏆 **{data2['player'].display_name}** is more likely to win the raid battle against **{data1['player'].display_name}**."
                    method_used = "Power-Based Comparison"

                    return result, method_used

            # Function to create a stylish embed for a player
            def create_player_embed(data):
                embed = discord.Embed(
                    title=f"{data['player'].display_name}'s Raid Stats",
                    color=0x1E90FF,  # DodgerBlue
                    timestamp=ctx.message.created_at
                )
                embed.set_thumbnail(
                    url=data['player'].avatar.url if data['player'].avatar else data['player'].default_avatar.url)
                embed.add_field(name="⚔️ **Damage Multiplier**", value=f"x{data['atk']}", inline=True)
                embed.add_field(name="🛡️ **Defense Multiplier**", value=f"x{data['deff']}", inline=True)
                embed.add_field(name="❤️ **Health Multiplier**", value=f"x{data['hplevel']}", inline=True)
                embed.add_field(
                    name="💰 **Upgrade Costs**",
                    value=(
                        f"**Damage:** ${int(data['atkp'])}\n"  # Removed decimal
                        f"**Defense:** ${int(data['deffp'])}\n"  # Removed decimal
                        f"**Health:** ${int(data['hpprice'])}"
                    ),
                    inline=False
                )
                embed.add_field(
                    name="📈 **Player's Stats**",
                    value=(
                        f"**Damage:** {data['dmg']}\n"
                        f"**Defense:** {data['defff']}\n"
                        f"**Health:** {data['hp']}"
                    ),
                    inline=False
                )
                embed.set_footer(
                    text=f"Requested by {ctx.author}",
                    icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                )
                return embed

            # Determine which players to fetch data for
            if player1 and player2:
                # Compare two players
                data1 = await get_player_data(player1)
                data2 = await get_player_data(player2)

                if not data1 or not data2:
                    await ctx.send("❌ One or both players' data could not be retrieved.")
                    return

                # Create embeds for both players
                embed1 = create_player_embed(data1)
                embed2 = create_player_embed(data2)

                # Compare and get the result along with the method used
                comparison_result, method_used = compare_players(data1, data2)

                # Create a final embed to show comparison result
                comparison_embed = discord.Embed(
                    title="🆚 Raid Battle Comparison",
                    description=comparison_result,
                    color=0xFFD700,  # Gold
                    timestamp=ctx.message.created_at
                )
                comparison_embed.set_footer(
                    text=f"Comparison requested by {ctx.author}",
                    icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
                )

                # Send the main comparison embeds
                try:
                    await ctx.send(embeds=[embed1, embed2, comparison_embed])
                except Exception as e:
                    # Fallback for discord.py versions that don't support multiple embeds
                    await ctx.send(embed=embed1)
                    await ctx.send(embed=embed2)
                    await ctx.send(embed=comparison_embed)

            else:
                # Show stats for one player (either specified or the command invoker)
                target_player = player1 if player1 else ctx.author
                data = await get_player_data(target_player)

                if not data:
                    await ctx.send("❌ Player's data could not be retrieved.")
                    return

                embed = create_player_embed(data)

                await ctx.send(embed=embed)

    @commands.command(brief=_("Did somebody say Raid?"))
    @locale_doc
    async def raid(self, ctx):
        _("""Informs you about joining raids.""")
        await ctx.send(
            _(
                "Did you ever want to join together with other players to defeat the"
                " dragon that roams this land? Raids got you covered!\nJoin the support"
                " server (`{prefix}support`) for more information."
            ).format(prefix=ctx.clean_prefix)
        )


async def setup(bot):
    designated_shard_id = 0  # Choose shard 0 as the primary

    # Check if shard 0 is among the bot's shard IDs
    if designated_shard_id in bot.shard_ids:
        await bot.add_cog(Raid(bot))
        print(f"Raid loaded on shard {designated_shard_id}")


