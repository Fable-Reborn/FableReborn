import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import random
import asyncio
import math
from decimal import Decimal, ROUND_HALF_UP
from collections import deque

# Replace with your actual IDs
GUILD_ID = 123456789012345678  # Replace with your guild/server ID
ANNOUNCEMENT_CHANNEL_ID = 123456789012345679  # Replace with your announcement channel ID

# Define ranks and their corresponding XP thresholds and abilities
RANKS = {
    "Resistance": [
        {"name": "Recruit", "xp_threshold": 0, "role_color": discord.Color.blue(), "abilities": []},
        {"name": "Soldier", "xp_threshold": 100, "role_color": discord.Color.green(),
         "abilities": ["Defensive Stance"]},
        {"name": "Sergeant", "xp_threshold": 300, "role_color": discord.Color.dark_green(),
         "abilities": ["Command Assault"]},
        {"name": "Lieutenant", "xp_threshold": 600, "role_color": discord.Color.gold(),
         "abilities": ["Strategic Planning"]},
        {"name": "Commander", "xp_threshold": 1000, "role_color": discord.Color.dark_gold(),
         "abilities": ["Inspire Troops"]},
        {"name": "Champion", "xp_threshold": 1500, "role_color": discord.Color.purple(),
         "abilities": ["Heroic Strike"]},
        {"name": "Legend", "xp_threshold": 2000, "role_color": discord.Color.dark_purple(),
         "abilities": ["Battlefield Mastery"]},
        {"name": "Guardian", "xp_threshold": 3000, "role_color": discord.Color.dark_blue(),
         "abilities": ["Ultimate Defense"]},
        {"name": "Warlord", "xp_threshold": 5000, "role_color": discord.Color.dark_orange(),
         "abilities": ["Tactical Genius"]},
        {"name": "Supreme Leader", "xp_threshold": 8000, "role_color": discord.Color.dark_red(),
         "abilities": ["Faction Command"]},
        {"name": "Legendary Champion", "xp_threshold": 12000, "role_color": discord.Color.dark_purple(),
         "abilities": ["Unstoppable Force"]}
    ],
    "Plague": [
        {"name": "Initiate", "xp_threshold": 0, "role_color": discord.Color.dark_purple(), "abilities": []},
        {"name": "Warlock", "xp_threshold": 100, "role_color": discord.Color.purple(), "abilities": ["Corrupted Aura"]},
        {"name": "Necromancer", "xp_threshold": 300, "role_color": discord.Color.dark_magenta(),
         "abilities": ["Raise Undead"]},
        {"name": "Overlord", "xp_threshold": 600, "role_color": discord.Color.red(), "abilities": ["Plague Burst"]},
        {"name": "Lich Lord", "xp_threshold": 1000, "role_color": discord.Color.dark_red(),
         "abilities": ["Soul Drain"]},
        {"name": "Shadow Master", "xp_threshold": 1500, "role_color": discord.Color.from_rgb(0, 0, 0),
         "abilities": ["Shadow Veil"]},
        {"name": "Dread Emperor", "xp_threshold": 2000, "role_color": discord.Color.dark_red(),
         "abilities": ["Doom Storm"]},
        {"name": "Eternal Tyrant", "xp_threshold": 3000, "role_color": discord.Color.dark_purple(),
         "abilities": ["Eternal Domination"]},
        {"name": "Master of Plague", "xp_threshold": 5000, "role_color": discord.Color.dark_gray(),
         "abilities": ["Plague Overload"]},
        {"name": "Supreme Plague Lord", "xp_threshold": 8000, "role_color": discord.Color.dark_red(),
         "abilities": ["Plague Cataclysm"]},
        {"name": "Legendary Lich", "xp_threshold": 12000, "role_color": discord.Color.blurple(),
         "abilities": ["Apocalypse Now"]}
    ]
}

# Define abilities and their effects
ABILITY_EFFECTS = {
    # Resistance Abilities
    "Defensive Stance": {"description": "Reduces incoming damage by 15%.", "damage_reduction": 0.15},
    "Command Assault": {"description": "Increases attack damage by 25% during assaults.", "damage_increase": 0.25},
    "Strategic Planning": {"description": "Boosts XP gain by 25%.", "xp_increase": 0.25},
    "Inspire Troops": {"description": "Increases faction's forces by 100.", "force_increase": 100},
    "Heroic Strike": {"description": "Critical hit chance increased by 20%.", "critical_chance": 0.20},
    "Battlefield Mastery": {"description": "All damage dealt increased by 30%.", "damage_increase": 0.30},
    "Ultimate Defense": {"description": "Reduces all incoming damage by 30%.", "damage_reduction": 0.30},
    "Tactical Genius": {"description": "Manages resources 20% more efficiently.", "resource_efficiency": 0.20},
    "Faction Command": {"description": "Boosts faction's overall XP gain by 50%.", "faction_xp_increase": 0.50},
    "Unstoppable Force": {"description": "Deals double damage once per battle.", "special_attack": "Double Damage"},

    # Plague Abilities
    "Corrupted Aura": {"description": "Reduces enemy's attack damage by 10%.", "enemy_damage_reduction": 0.10},
    "Raise Undead": {"description": "Summons 5 undead warriors to fight alongside you.", "summon": 5},
    "Plague Burst": {"description": "Deals area damage to all enemies.", "area_damage": 50},
    "Soul Drain": {"description": "Leeches 20 HP from the enemy each attack.", "lifesteal": 20},
    "Shadow Veil": {"description": "Becomes invisible for 2 turns, avoiding all damage.", "invisibility_turns": 2},
    "Doom Storm": {"description": "Deals massive damage with a chance to stun enemies.", "damage": 100,
                   "stun_chance": 0.25},
    "Eternal Domination": {"description": "Increases all damage dealt by 40%.", "damage_increase": 0.40},
    "Plague Overload": {"description": "Overloads your abilities, dealing double damage for the next 3 turns.",
                        "damage_increase": 0.50},
    "Plague Cataclysm": {"description": "Unleashes a cataclysmic plague wave, dealing devastating damage.",
                         "damage": 200},
    "Apocalypse Now": {"description": "Triggers an apocalyptic event, instantly defeating all enemies.",
                       "instant_defeat": True}
}


class PlagueOfTheUndying(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.event_active = False
        self.factions = {
            "Resistance": {
                "forces": 1000,
                "resources": {"gold": 1000, "materials": 1000},
                "members": set()
            },
            "Plague": {
                "forces": 1000,
                "resources": {"gold": 1000, "materials": 1000},
                "members": set()
            }
        }
        self.player_factions = {}  # Key: user_id, Value: faction name
        self.player_forces = {}  # Key: user_id, Value: number of forces
        self.player_xp = {}  # Key: user_id, Value: XP
        self.daily_events = deque(maxlen=20)
        self.player_narratives = {}
        self.regions = self.initialize_regions()
        self.action_cooldowns = {}  # Key: user_id, Value: {action: last_time}
        self.event_start_time = None
        self.event_duration = timedelta(days=7)  # Maximum duration
        self.victory_threshold = 0.8  # 80%

        # Start background tasks
        self.conclude_event_task = self.bot.loop.create_task(self.check_event_end())
        self.hourly_update_task = self.bot.loop.create_task(self.hourly_update())
        self.region_battles_task = self.bot.loop.create_task(self.region_battles())

    def initialize_regions(self):
        """Initialize the regions and their control status."""
        regions = {
            "Northwatch": {"controlled_by": None, "forces": {"Resistance": 0, "Plague": 0}},
            "Eastvale": {"controlled_by": None, "forces": {"Resistance": 0, "Plague": 0}},
            "Southport": {"controlled_by": None, "forces": {"Resistance": 0, "Plague": 0}},
            "Westwood": {"controlled_by": None, "forces": {"Resistance": 0, "Plague": 0}},
            "Central City": {"controlled_by": None, "forces": {"Resistance": 0, "Plague": 0}},
        }
        return regions

    # Utility functions
    async def update_player_stat(self, user_id, column, value):
        """Update a player's stat in the profile table."""
        # Placeholder for database update
        # Replace with actual database interaction
        pass

    async def get_player_stat(self, user_id, column):
        """Retrieve a player's stat from the profile table."""
        # Placeholder for database retrieval
        # Replace with actual database interaction
        return self.player_xp.get(user_id, 0)

    async def get_player_rank(self, user_id):
        """Determine the player's rank based on XP."""
        faction = self.player_factions.get(user_id)
        if not faction:
            return None, None  # Player not in any faction

        xp = self.player_xp.get(user_id, 0)
        ranks = RANKS[faction]
        current_rank = ranks[0]  # Default to first rank
        for rank in ranks:
            if xp >= rank["xp_threshold"]:
                current_rank = rank
            else:
                break
        return current_rank, ranks.index(current_rank)

    async def promote_player(self, user_id):
        """Promote the player to the next rank if XP threshold is met."""
        faction = self.player_factions.get(user_id)
        if not faction:
            return

        current_rank, rank_index = await self.get_player_rank(user_id)
        ranks = RANKS[faction]
        if rank_index + 1 < len(ranks):
            next_rank = ranks[rank_index + 1]
            xp = self.player_xp.get(user_id, 0)
            if xp >= next_rank["xp_threshold"]:
                # Assign new Discord role
                guild = self.bot.get_guild(GUILD_ID)
                role_name = f"{faction} - {next_rank['name']}"
                role = discord.utils.get(guild.roles, name=role_name)
                if not role:
                    # Create the role if it doesn't exist
                    role = await guild.create_role(name=role_name, color=next_rank["role_color"])
                user = guild.get_member(user_id)
                if user:
                    # Remove previous rank roles
                    for rank in ranks:
                        existing_role = discord.utils.get(guild.roles, name=f"{faction} - {rank['name']}")
                        if existing_role and existing_role in user.roles:
                            await user.remove_roles(existing_role)
                    # Assign new rank role
                    await user.add_roles(role)
                    # Notify the user
                    try:
                        await user.send(
                            f"🎉 Congratulations! You have been promoted to **{next_rank['name']}** in the **{faction}**.")
                    except:
                        pass  # Can't send DM
                    # Log the promotion
                    promotion_message = f"🎖️ {user.display_name} has been promoted to **{next_rank['name']}** in the **{faction}**."
                    self.daily_events.append(promotion_message)

    async def assign_rank_role(self, user, faction, rank_name):
        """Assign a rank role to the user."""
        guild = self.bot.get_guild(GUILD_ID)
        role_name = f"{faction} - {rank_name}"
        role = discord.utils.get(guild.roles, name=role_name)
        if not role:
            # Create the role if it doesn't exist
            rank_info = next((rank for rank in RANKS[faction] if rank["name"] == rank_name), None)
            if rank_info:
                role = await guild.create_role(name=role_name, color=rank_info["role_color"])
        if role:
            await user.add_roles(role)

    async def update_user_roles(self, user, old_faction, new_faction):
        """Update the user's roles when switching factions."""
        guild = self.bot.get_guild(GUILD_ID)
        # Remove old faction roles
        for rank in RANKS[old_faction]:
            role = discord.utils.get(guild.roles, name=f"{old_faction} - {rank['name']}")
            if role and role in user.roles:
                await user.remove_roles(role)
        # Assign new faction's initial rank role
        await self.assign_rank_role(user, new_faction, RANKS[new_faction][0]["name"])

    # Event Control
    async def send_event_start(self):
        if self.event_active:
            return
        guild = self.bot.get_guild(GUILD_ID)
        announcement_channel = guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)

        prologue = (
            "**📜 Plague of the Undying: Apocalypse Begins**\n\n"
            "A mysterious and deadly plague has swept across the land, plunging the world into chaos and despair.\n\n"
            "Citizens are organizing into factions to either combat the spread of the plague or harness its dark powers.\n\n"
            "**Your Role:**\n"
            "Choose your side in this battle for survival. Will you join the **Resistance** to fight back against the plague, or align with the **Plague** to embrace its dark potential?\n\n"
            "Use `$plague join <faction>` to select your allegiance."
        )

        embed = discord.Embed(
            title="🌍 Plague of the Undying: Apocalypse Begins",
            description=prologue,
            color=discord.Color.dark_red(),
            timestamp=datetime.utcnow()
        )
        embed.set_thumbnail(url="https://i.imgur.com/Apocalypse.png")  # Replace with an actual image URL
        await announcement_channel.send(embed=embed)
        self.event_active = True

    # Hybrid Event Conclusion
    async def check_event_end(self):
        """Checks for event conclusion based on time or victory conditions."""
        await self.bot.wait_until_ready()
        while True:
            if self.event_active and self.event_start_time:
                current_time = datetime.utcnow()
                elapsed_time = current_time - self.event_start_time

                # Time-based conclusion
                if elapsed_time >= self.event_duration:
                    await self.conclude_event_time_based()
                    continue

                # Victory-based conclusion
                total_forces = self.factions["Resistance"]["forces"] + self.factions["Plague"]["forces"]
                if total_forces == 0:
                    await asyncio.sleep(300)  # Avoid division by zero
                    continue  # No forces left, continue monitoring

                resistance_ratio = self.factions["Resistance"]["forces"] / total_forces
                plague_ratio = self.factions["Plague"]["forces"] / total_forces

                if resistance_ratio >= self.victory_threshold:
                    await self.conclude_event(winning_faction="Resistance")
                elif plague_ratio >= self.victory_threshold:
                    await self.conclude_event(winning_faction="Plague")

            await asyncio.sleep(300)  # Check every 5 minutes

    async def conclude_event(self, winning_faction):
        """Concludes the event with a winning faction."""
        self.event_active = False
        guild = self.bot.get_guild(GUILD_ID)
        announcement_channel = guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)

        if winning_faction != "No one. It's a tie!":
            description = f"🏆 **{winning_faction}** has achieved a decisive victory in the **Plague of the Undying** event! Their unwavering determination has tilted the balance of power, ensuring a brighter future for their cause.\n\n**Rewards:** All members of the **{winning_faction}** have been awarded a special badge and bonus XP!"
        else:
            description = f"⚖️ The **Plague of the Undying** event has concluded in a **tie**. Both factions have shown incredible resilience and strength.\n\n**Rewards:** All participants receive commendations and modest XP gains."

        embed = discord.Embed(
            title="🛑 Plague of the Undying: Event Concluded",
            description=description,
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        embed.set_thumbnail(url="https://i.imgur.com/EventConclusion.png")  # Replace with actual image URL

        # Add Rewards Information
        if winning_faction != "No one. It's a tie!":
            embed.add_field(
                name="🎁 Rewards",
                value=(
                    f"Members of the **{winning_faction}** have received exclusive roles and bonus XP!\n"
                    f"All participants are awarded a participation badge."
                ),
                inline=False
            )
        else:
            embed.add_field(
                name="🎁 Rewards",
                value=(
                    f"All participants receive commendations and a modest XP boost."
                ),
                inline=False
            )

        await announcement_channel.send(embed=embed)

        # Reward Distribution Logic
        await self.distribute_rewards(winning_faction)

        # Optionally reset the event for future cycles
        # await self.reset_event()

    async def conclude_event_time_based(self):
        """Concludes the event based on time elapsed."""
        self.event_active = False
        guild = self.bot.get_guild(GUILD_ID)
        announcement_channel = guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)

        # Determine winning faction based on current forces
        resistance_forces = self.factions["Resistance"]["forces"]
        plague_forces = self.factions["Plague"]["forces"]
        if resistance_forces > plague_forces:
            winning_faction = "Resistance"
        elif plague_forces > resistance_forces:
            winning_faction = "Plague"
        else:
            winning_faction = "No one. It's a tie!"

        # Create conclusion message
        if winning_faction != "No one. It's a tie!":
            description = f"🏆 **{winning_faction}** emerges as the leading faction in the **Plague of the Undying** event! Their strategic prowess has secured their dominance.\n\n**Rewards:** Members of **{winning_faction}** receive exclusive titles and significant XP boosts!"
        else:
            description = f"⚖️ The **Plague of the Undying** event concludes in a **tie**. Both factions have demonstrated incredible resilience and strength.\n\n**Rewards:** All participants receive commendations and modest XP gains."

        embed = discord.Embed(
            title="🛑 Plague of the Undying: Event Concluded",
            description=description,
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        embed.set_thumbnail(url="https://i.imgur.com/EventConclusion.png")  # Replace with actual image URL

        # Add Rewards Information
        if winning_faction != "No one. It's a tie!":
            embed.add_field(
                name="🎁 Rewards",
                value=(
                    f"Members of the **{winning_faction}** have received exclusive roles and bonus XP!\n"
                    f"All participants are awarded a participation badge."
                ),
                inline=False
            )
        else:
            embed.add_field(
                name="🎁 Rewards",
                value=(
                    f"All participants receive commendations and a modest XP boost."
                ),
                inline=False
            )

        await announcement_channel.send(embed=embed)

        # Reward Distribution Logic
        await self.distribute_rewards(winning_faction)

        # Optionally reset the event for future cycles
        # await self.reset_event()

    async def distribute_rewards(self, winning_faction):
        """Distributes rewards to players based on the event outcome."""
        guild = self.bot.get_guild(GUILD_ID)
        announcement_channel = guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)

        if winning_faction in self.factions:
            for member_id in self.factions[winning_faction]["members"]:
                member = guild.get_member(member_id)
                if member:
                    # Assign special role
                    reward_role = discord.utils.get(guild.roles, name=f"{winning_faction} Champion")
                    if not reward_role:
                        # Create the role if it doesn't exist
                        reward_role = await guild.create_role(name=f"{winning_faction} Champion",
                                                              color=discord.Color.gold())
                    await member.add_roles(reward_role)

                    # Award bonus XP
                    bonus_xp = 500  # Example bonus XP
                    self.player_xp[member_id] = self.player_xp.get(member_id, 0) + bonus_xp
                    await self.promote_player(member_id)

                    # Send DM notification
                    try:
                        await member.send(
                            f"🎉 Congratulations! You have been awarded the **{winning_faction} Champion** role and **{bonus_xp} XP** for your contributions to the **Plague of the Undying** event.")
                    except:
                        pass  # Can't send DM

        # Award participation badges and modest XP
        participation_bonus = 100  # Example participation XP
        for user_id in self.player_factions:
            member = guild.get_member(user_id)
            if member:
                # Assign participation role
                participation_role = discord.utils.get(guild.roles, name="Participant")
                if not participation_role:
                    participation_role = await guild.create_role(name="Participant", color=discord.Color.light_gray())
                await member.add_roles(participation_role)

                # Award XP
                self.player_xp[user_id] = self.player_xp.get(user_id, 0) + participation_bonus
                await self.promote_player(user_id)

                # Send DM notification
                try:
                    await member.send(
                        f"✨ Thank you for participating in the **Plague of the Undying** event! You have been awarded the **Participant** role and **{participation_bonus} XP**.")
                except:
                    pass  # Can't send DM

    async def reset_event(self):
        """Resets all event-related data."""
        self.event_active = False
        self.factions = {
            "Resistance": {
                "forces": 1000,
                "resources": {"gold": 1000, "materials": 1000},
                "members": set()
            },
            "Plague": {
                "forces": 1000,
                "resources": {"gold": 1000, "materials": 1000},
                "members": set()
            }
        }
        self.player_factions.clear()
        self.player_forces.clear()
        self.player_xp.clear()
        self.daily_events.clear()
        self.player_narratives.clear()
        self.regions = self.initialize_regions()
        self.action_cooldowns.clear()
        self.event_start_time = None

        # Reset roles for all members
        guild = self.bot.get_guild(GUILD_ID)
        for member in guild.members:
            # Remove faction roles
            for faction in self.factions:
                for rank in RANKS[faction]:
                    role = discord.utils.get(guild.roles, name=f"{faction} - {rank['name']}")
                    if role and role in member.roles:
                        await member.remove_roles(role)
            # Remove participation and reward roles
            participation_role = discord.utils.get(guild.roles, name="Participant")
            if participation_role and participation_role in member.roles:
                await member.remove_roles(participation_role)
            reward_role = discord.utils.get(guild.roles, name="Champion")
            if reward_role and reward_role in member.roles:
                await member.remove_roles(reward_role)

        # Notify admins
        announcement_channel = guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)
        embed = discord.Embed(
            title="🔄 Plague of the Undying: Event Reset",
            description="All event-related data has been reset. You can start a new event using `$plague start_event`.",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.set_thumbnail(url="https://i.imgur.com/ResetEvent.png")  # Replace with actual image URL
        await announcement_channel.send(embed=embed)

    # Faction Selection
    @commands.group(name="plague", invoke_without_command=True)
    async def plague_group(self, ctx):
        """Plague of the Undying event commands."""
        if ctx.invoked_subcommand is None:
            embed = discord.Embed(
                title="🛡️ Plague of the Undying Commands",
                description=(
                    "Use the following commands to participate in the Plague of the Undying event:\n\n"
                    "`$plague join <faction>` - Join a faction (`Resistance` or `Plague`).\n"
                    "`$plague status` - View your faction status and rank.\n"
                    "`$plague gather` - Gather resources for your faction.\n"
                    "`$plague recruit <number>` - Recruit forces for your faction.\n"
                    "`$plague battle` - Engage in battles to gain XP.\n"
                    "`$plague view` - View the overall status of factions and regions.\n"
                    "`$plague abilities` - View your current abilities.\n"
                    "`$plague quests` - View available quests.\n"
                    "`$plague claim <quest>` - Claim rewards from completed quests.\n"
                    "`$plague profile` - View your complete profile.\n"
                    "`$plague lore` - Dive into the lore of the Plague of the Undying."
                ),
                color=discord.Color.blue()
            )
            embed.set_footer(text="Choose your side and fight for survival in the apocalypse!")
            await ctx.send(embed=embed)

    @plague_group.command(name="join")
    async def join_faction(self, ctx, faction: str):
        """Join a faction: Resistance or Plague."""
        if not self.event_active:
            await ctx.send("❌ The Plague of the Undying event is not currently active.")
            return

        faction = faction.capitalize()
        if faction not in self.factions:
            await ctx.send("❌ Invalid faction. Choose either `Resistance` or `Plague`.")
            return

        user_id = ctx.author.id
        previous_faction = self.player_factions.get(user_id)

        if previous_faction:
            if previous_faction == faction:
                await ctx.send(f"ℹ️ You are already part of the **{faction}**.")
                return
            else:
                # Transfer forces if switching factions
                forces = self.player_forces.get(user_id, 0)
                self.factions[previous_faction]["forces"] -= forces
                self.factions[faction]["forces"] += forces
                self.player_factions[user_id] = faction
                self.factions[previous_faction]["members"].discard(user_id)
                self.factions[faction]["members"].add(user_id)
                # Update Discord roles
                await self.update_user_roles(ctx.author, previous_faction, faction)
                await ctx.send(f"🔄 You have switched from **{previous_faction}** to **{faction}**.")
                # Add narrative
                narrative = random.choice([
                    f"{ctx.author.display_name} changes allegiance, now fighting for the **{faction}**.",
                    f"{ctx.author.display_name} shifts their loyalties to the **{faction}**, altering the balance of power.",
                    f"{ctx.author.display_name} redeems themselves by joining the **{faction}**."
                ])
                self.daily_events.append(narrative)
        else:
            self.player_factions[user_id] = faction
            self.factions[faction]["forces"] += 10  # Initial forces
            self.player_forces[user_id] = 10
            self.player_xp[user_id] = 0
            self.factions[faction]["members"].add(user_id)
            # Assign initial rank role
            await self.assign_rank_role(ctx.author, faction, "Recruit")
            await ctx.send(f"✅ You have joined the **{faction}**! Welcome to the fight.")
            # Add narrative
            narrative = random.choice([
                f"{ctx.author.display_name} pledges allegiance to the **{faction}**, marking the beginning of their journey.",
                f"{ctx.author.display_name} stands tall, joining the ranks of the **{faction}** to combat the plague.",
                f"{ctx.author.display_name} declares their support for the **{faction}**, ready to face the apocalypse."
            ])
            self.daily_events.append(narrative)

    @plague_group.command(name="status")
    async def faction_status(self, ctx):
        """View your faction status and rank."""
        if not self.event_active:
            await ctx.send("❌ The Plague of the Undying event is not currently active.")
            return

        user_id = ctx.author.id
        faction = self.player_factions.get(user_id)

        if not faction:
            await ctx.send("ℹ️ You have not joined any faction yet. Use `$plague join <faction>` to join a side.")
            return

        # Fetch player's rank
        current_rank, rank_index = await self.get_player_rank(user_id)
        rank_name = current_rank["name"] if current_rank else "Unknown"

        forces = self.player_forces.get(user_id, 0)
        xp = self.player_xp.get(user_id, 0)
        next_rank = RANKS[faction][rank_index + 1] if rank_index + 1 < len(RANKS[faction]) else None
        xp_to_next = next_rank["xp_threshold"] - xp if next_rank else "Max Rank"

        embed = discord.Embed(
            title=f"🛡️ {faction} - {rank_name} Status",
            color=discord.Color.green() if faction == "Resistance" else discord.Color.purple(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="🏰 Faction", value=f"**{faction}**", inline=False)
        embed.add_field(name="🛡️ Your Forces", value=f"{forces}", inline=True)
        embed.add_field(name="📈 Your XP", value=f"{xp} XP", inline=True)
        embed.add_field(name="🎖️ Current Rank", value=f"**{rank_name}**", inline=True)
        embed.add_field(name="📈 Next Rank", value=f"**{next_rank['name']}**" if next_rank else "N/A", inline=True)
        embed.add_field(name="🔺 XP to Next Rank", value=f"{xp_to_next}" if next_rank else "N/A", inline=True)
        embed.add_field(name="✨ Current Abilities",
                        value=", ".join(current_rank["abilities"]) if current_rank and current_rank[
                            "abilities"] else "None", inline=False)
        embed.set_footer(text="Climb the ranks to gain new abilities and lead your faction to victory!")
        await ctx.send(embed=embed)

    # Abilities Command
    @plague_group.command(name="abilities")
    async def view_abilities(self, ctx):
        """View your current abilities based on your rank."""
        user_id = ctx.author.id
        faction = self.player_factions.get(user_id)

        if not faction:
            await ctx.send("ℹ️ You have not joined any faction yet. Use `$plague join <faction>` to join a side.")
            return

        current_rank, _ = await self.get_player_rank(user_id)
        if not current_rank:
            await ctx.send("❌ Unable to determine your rank.")
            return

        abilities = current_rank["abilities"] if current_rank["abilities"] else ["None"]
        ability_descriptions = [ABILITY_EFFECTS[ability]["description"] for ability in abilities] if abilities != [
            "None"] else ["No abilities at your current rank."]

        embed = discord.Embed(
            title=f"🛡️ {faction} - {current_rank['name']} Abilities",
            description="Here are your current abilities:",
            color=discord.Color.green() if faction == "Resistance" else discord.Color.purple(),
            timestamp=datetime.utcnow()
        )
        for ability, desc in zip(abilities, ability_descriptions):
            embed.add_field(name=ability, value=desc, inline=False)

        await ctx.send(embed=embed)

    # Quests Command
    @plague_group.command(name="quests")
    async def view_quests(self, ctx):
        """View available quests."""
        if not self.event_active:
            await ctx.send("❌ The Plague of the Undying event is not currently active.")
            return

        # Define available quests
        quests = [
            {"name": "Eliminate the Rotting Beast", "description": "Defeat 5 Rotting Beasts in battle.",
             "reward": "200 XP"},
            {"name": "Gather Critical Supplies", "description": "Collect 500 materials for your faction.",
             "reward": "150 XP"},
            {"name": "Raise the Undead Legion", "description": "Successfully use your 'Raise Undead' ability 3 times.",
             "reward": "250 XP"},
            {"name": "Protect the Central City", "description": "Defend Central City from Plague forces for 24 hours.",
             "reward": "300 XP"},
            {"name": "Conquer Northwatch", "description": "Achieve control over the Northwatch region.",
             "reward": "500 XP"},
        ]

        embed = discord.Embed(
            title="📜 Available Quests",
            description="Complete these quests to earn valuable rewards and boost your faction's efforts!",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        for quest in quests:
            embed.add_field(name=quest["name"], value=f"{quest['description']}\n**Reward:** {quest['reward']}",
                            inline=False)

        embed.set_footer(text="Complete quests using `$plague claim <quest name>` once fulfilled.")
        await ctx.send(embed=embed)

    # Claim Quests Command
    @plague_group.command(name="claim")
    async def claim_quest(self, ctx, *, quest_name: str):
        """Claim rewards from completed quests."""
        if not self.event_active:
            await ctx.send("❌ The Plague of the Undying event is not currently active.")
            return

        user_id = ctx.author.id
        faction = self.player_factions.get(user_id)

        if not faction:
            await ctx.send("ℹ️ You have not joined any faction yet. Use `$plague join <faction>` to join a side.")
            return

        # Define quests and their requirements
        quests = {
            "eliminate the rotting beast": {"description": "Defeat 5 Rotting Beasts in battle.", "reward": "200 XP",
                                            "completed": False},
            "gather critical supplies": {"description": "Collect 500 materials for your faction.", "reward": "150 XP",
                                         "completed": False},
            "raise the undead legion": {"description": "Successfully use your 'Raise Undead' ability 3 times.",
                                        "reward": "250 XP", "completed": False},
            "protect the central city": {"description": "Defend Central City from Plague forces for 24 hours.",
                                         "reward": "300 XP", "completed": False},
            "conquer northwatch": {"description": "Achieve control over the Northwatch region.", "reward": "500 XP",
                                   "completed": False},
        }

        quest_key = quest_name.lower()
        if quest_key not in quests:
            await ctx.send("❌ Invalid quest name. Use `$plague quests` to view available quests.")
            return

        # Placeholder for quest completion logic
        # Implement actual checks based on player actions and event state
        # For demonstration, we'll randomly decide if the quest is completed
        completed = random.choice([True, False])

        if completed:
            reward = quests[quest_key]["reward"]
            # Parse XP from reward
            xp_gain = int(reward.split()[0])
            self.player_xp[user_id] = self.player_xp.get(user_id, 0) + xp_gain
            await self.promote_player(user_id)
            await ctx.send(f"✅ You have completed the quest **{quest_name.title()}** and earned **{xp_gain} XP**!")

            # Log the completion
            self.daily_events.append(
                f"🎉 {ctx.author.display_name} has completed the quest **{quest_name.title()}** and earned {xp_gain} XP.")

            # Remove or mark the quest as completed
            # For simplicity, quests are repeatable in this example
        else:
            await ctx.send(f"❌ You have not yet completed the quest **{quest_name.title()}**. Keep trying!")

    # Profile Command
    @plague_group.command(name="profile")
    async def view_profile(self, ctx):
        """View your complete profile."""
        user_id = ctx.author.id
        faction = self.player_factions.get(user_id)

        if not faction:
            await ctx.send("ℹ️ You have not joined any faction yet. Use `$plague join <faction>` to join a side.")
            return

        current_rank, _ = await self.get_player_rank(user_id)
        rank_name = current_rank["name"] if current_rank else "Unknown"

        forces = self.player_forces.get(user_id, 0)
        xp = self.player_xp.get(user_id, 0)

        embed = discord.Embed(
            title=f"👤 {ctx.author.display_name}'s Profile",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="🏰 Faction", value=f"**{faction}**", inline=False)
        embed.add_field(name="🎖️ Current Rank", value=f"**{rank_name}**", inline=True)
        embed.add_field(name="🛡️ Your Forces", value=f"{forces}", inline=True)
        embed.add_field(name="📈 Your XP", value=f"{xp} XP", inline=True)
        embed.add_field(name="✨ Abilities", value=", ".join(current_rank["abilities"]) if current_rank and current_rank[
            "abilities"] else "None", inline=False)
        embed.add_field(name="📜 Quests Completed", value="Coming Soon!", inline=False)
        embed.add_field(name="🗺️ Regions Controlled", value="Coming Soon!", inline=False)
        embed.set_thumbnail(url="https://i.imgur.com/Profile.png")  # Replace with actual image URL
        embed.set_footer(text="Keep contributing to your faction to climb the ranks and earn rewards!")
        await ctx.send(embed=embed)

    # Lore Command
    @plague_group.command(name="lore")
    async def view_lore(self, ctx):
        """Dive into the lore of the Plague of the Undying."""
        lore = (
            "**📖 Plague of the Undying: The Dark Chronicles**\n\n"
            "In an age long forgotten, a mysterious plague emerged from the shadows, bearing the curse of eternal decay. "
            "As the world grappled with the devastation, factions arose from the ashes of society, each with their own vision for the future.\n\n"
            "**🛡️ Resistance:**\n"
            "Comprising warriors, healers, and strategists, the Resistance stands as humanity's last bastion against the relentless spread of the plague. "
            "Their mission: to eradicate the source of the corruption and restore balance to the world.\n\n"
            "**☠️ Plague:**\n"
            "Embracing the dark energies of the plague, the Plague faction seeks to harness its power to reshape the world according to their own twisted ideals. "
            "They believe that through decay, new life can emerge stronger and more resilient.\n\n"
            "As a member of one of these factions, your choices will shape the outcome of this apocalyptic struggle. Will you fight to preserve humanity, or succumb to the allure of dark power?\n\n"
            "Embark on quests, engage in battles, and rise through the ranks to leave your mark on this ravaged world."
        )

        embed = discord.Embed(
            title="📖 Lore of the Plague of the Undying",
            description=lore,
            color=discord.Color.dark_purple(),
            timestamp=datetime.utcnow()
        )
        embed.set_thumbnail(url="https://i.imgur.com/Lore.png")  # Replace with actual image URL
        await ctx.send(embed=embed)

    # Resource Management
    @plague_group.command(name="gather")
    async def gather_resources(self, ctx):
        """Gather resources to aid your faction."""
        if not self.event_active:
            await ctx.send("❌ The Plague of the Undying event is not currently active.")
            return

        user_id = ctx.author.id
        faction = self.player_factions.get(user_id)

        if not faction:
            await ctx.send("ℹ️ You have not joined any faction yet. Use `$plague join <faction>` to join a side.")
            return

        if self.has_acted_recently(user_id, 'gather_resources'):
            remaining = self.get_cooldown_remaining(user_id, 'gather_resources')
            await ctx.send(
                f"⏰ You have already gathered resources recently. Please wait {remaining} before gathering again.")
            return

        # Gather resources
        materials = random.randint(50, 100)
        gold = random.randint(20, 50)

        # Apply resource efficiency ability
        current_rank, _ = await self.get_player_rank(user_id)
        resource_efficiency = 0
        if current_rank and "resource_efficiency" in ABILITY_EFFECTS.get(current_rank["abilities"][0], {}):
            for ability in current_rank["abilities"]:
                effects = ABILITY_EFFECTS.get(ability, {})
                resource_efficiency += effects.get("resource_efficiency", 0)

        materials = int(materials * (1 + resource_efficiency))
        gold = int(gold * (1 + resource_efficiency))

        self.factions[faction]["resources"]["materials"] += materials
        self.factions[faction]["resources"]["gold"] += gold

        # Award XP for gathering, considering abilities
        base_xp_gain = random.randint(10, 20)
        xp_multiplier = 1.0
        if current_rank and current_rank["abilities"]:
            for ability in current_rank["abilities"]:
                if ability in ABILITY_EFFECTS and "xp_increase" in ABILITY_EFFECTS[ability]:
                    xp_multiplier += ABILITY_EFFECTS[ability]["xp_increase"]
        xp_gain = int(base_xp_gain * xp_multiplier)
        self.player_xp[user_id] = self.player_xp.get(user_id, 0) + xp_gain
        await self.promote_player(user_id)

        # Log the action
        self.daily_events.append(
            f"📦 {ctx.author.display_name} gathered {materials} materials and {gold} gold for the **{faction}**.")
        self.player_narratives[user_id] = self.player_narratives.get(user_id,
                                                                     "") + f"\n**Gathered Resources:** {materials} materials and {gold} gold."

        # Set cooldown
        self.set_player_action(user_id, 'gather_resources')

        # Send narrative message
        narrative = random.choice([
            f"{ctx.author.display_name} scours the area, collecting essential materials to bolster the **{faction}**.",
            f"{ctx.author.display_name} expertly gathers resources, contributing to the **{faction}**'s efforts.",
            f"{ctx.author.display_name} undertakes a meticulous resource collection mission for the **{faction}**."
        ])

        embed = discord.Embed(
            title="🔍 Resource Gathering",
            description=(
                f"{narrative}\n\n"
                f"You have gathered **{materials}** materials and **{gold}** gold for the **{faction}**.\n"
                f"**XP Gained:** {xp_gain} XP"
            ),
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.set_thumbnail(url="https://i.imgur.com/Gather.png")  # Replace with actual image URL
        await ctx.send(embed=embed)

    @plague_group.command(name="recruit")
    async def recruit_forces(self, ctx, number: int):
        """Recruit forces for your faction."""
        if not self.event_active:
            await ctx.send("❌ The Plague of the Undying event is not currently active.")
            return

        user_id = ctx.author.id
        faction = self.player_factions.get(user_id)

        if not faction:
            await ctx.send("ℹ️ You have not joined any faction yet. Use `$plague join <faction>` to join a side.")
            return

        if self.has_acted_recently(user_id, 'recruit'):
            remaining = self.get_cooldown_remaining(user_id, 'recruit')
            await ctx.send(
                f"⏰ You have already recruited forces recently. Please wait {remaining} before recruiting again.")
            return

        if number <= 0:
            await ctx.send("❌ Please enter a valid number of forces to recruit.")
            return

        # Check if the faction has enough resources
        cost_per_unit = 10  # Example cost per force
        total_cost = cost_per_unit * number

        if self.factions[faction]["resources"]["gold"] >= total_cost:
            self.factions[faction]["resources"]["gold"] -= total_cost
            self.factions[faction]["forces"] += number
            self.player_forces[user_id] = self.player_forces.get(user_id, 0) + number

            # Award XP for recruiting, considering abilities
            base_xp_gain = random.randint(20, 30)
            xp_multiplier = 1.0
            current_rank, _ = await self.get_player_rank(user_id)
            if current_rank and current_rank["abilities"]:
                for ability in current_rank["abilities"]:
                    if ability in ABILITY_EFFECTS and "xp_increase" in ABILITY_EFFECTS[ability]:
                        xp_multiplier += ABILITY_EFFECTS[ability]["xp_increase"]
            xp_gain = int(base_xp_gain * xp_multiplier)
            self.player_xp[user_id] = self.player_xp.get(user_id, 0) + xp_gain
            await self.promote_player(user_id)

            # Log the action
            self.daily_events.append(f"🛡️ {ctx.author.display_name} recruited {number} forces for the **{faction}**.")
            self.player_narratives[user_id] = self.player_narratives.get(user_id,
                                                                         "") + f"\n**Recruited Forces:** {number} forces."

            # Set cooldown
            self.set_player_action(user_id, 'recruit')

            # Send narrative message
            narrative = random.choice([
                f"{ctx.author.display_name} rallies the troops, recruiting additional forces for the **{faction}**.",
                f"{ctx.author.display_name} successfully recruits **{number}** new forces to strengthen the **{faction}**.",
                f"{ctx.author.display_name} leads a recruitment drive, adding **{number}** forces to the **{faction}**."
            ])

            embed = discord.Embed(
                title="🛡️ Force Recruitment",
                description=(
                    f"{narrative}\n\n"
                    f"You have successfully recruited **{number}** forces for the **{faction}**.\n"
                    f"**XP Gained:** {xp_gain} XP"
                ),
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            embed.set_thumbnail(url="https://i.imgur.com/Recruit.png")  # Replace with actual image URL
            await ctx.send(embed=embed)
        else:
            await ctx.send("❌ Your faction does not have enough gold to recruit that many forces.")

    # Battle Commands
    @plague_group.command(name="battle", brief="Engage in a battle to gain XP.")
    async def battle(self, ctx):
        """Battle against a monster and gain experience points."""
        user_id = ctx.author.id
        faction = self.player_factions.get(user_id)

        if not self.event_active:
            await ctx.send("❌ The Plague of the Undying event is not currently active.")
            return

        if not faction:
            await ctx.send("ℹ️ You have not joined any faction yet. Use `$plague join <faction>` to join a side.")
            return

        # Define the elements and their strengths
        elements = ['Fire', 'Water', 'Earth', 'Wind', 'Light', 'Dark', 'Electric', 'Nature', 'Corrupted']

        # Define element strengths for damage modifiers
        element_strengths = {
            "Light": "Corrupted",
            "Dark": "Light",
            "Corrupted": "Dark",
            "Nature": "Electric",
            "Electric": "Water",
            "Water": "Fire",
            "Fire": "Nature",
            "Wind": "Electric",
            "Earth": "Wind"  # Added Earth to have a strength
        }

        # Define element to emoji mapping
        element_to_emoji = {
            "Light": "🌟",
            "Dark": "🌑",
            "Corrupted": "🌀",
            "Nature": "🌿",
            "Electric": "⚡",
            "Water": "💧",
            "Fire": "🔥",
            "Wind": "💨",
            "Earth": "🌍",
        }

        # Define the monsters per faction
        monsters = {
            "Resistance": {  # Monsters that Resistance can battle (Plague-based)
                1: [
                    {"name": "Plague Brute", "hp": Decimal('120'), "attack": Decimal('100'), "defense": Decimal('90'),
                     "element": "Dark"},
                    {"name": "Rotting Beast", "hp": Decimal('150'), "attack": Decimal('110'), "defense": Decimal('100'),
                     "element": "Corrupted"},
                    {"name": "Festered Ghoul", "hp": Decimal('100'), "attack": Decimal('90'), "defense": Decimal('80'),
                     "element": "Dark"},
                    {"name": "Moldering Lich", "hp": Decimal('200'), "attack": Decimal('150'),
                     "defense": Decimal('140'), "element": "Corrupted"},
                    {"name": "Plague Sovereign", "hp": Decimal('400'), "attack": Decimal('250'),
                     "defense": Decimal('240'), "element": "Dark"},
                ],
                2: [
                    {"name": "Necrotic Overlord", "hp": Decimal('250'), "attack": Decimal('200'),
                     "defense": Decimal('180'), "element": "Corrupted"},
                    {"name": "Dark Reaper", "hp": Decimal('300'), "attack": Decimal('220'), "defense": Decimal('200'),
                     "element": "Dark"},
                    {"name": "Plague Herald", "hp": Decimal('350'), "attack": Decimal('250'), "defense": Decimal('230'),
                     "element": "Corrupted"},
                    {"name": "Rotting Titan", "hp": Decimal('500'), "attack": Decimal('300'), "defense": Decimal('280'),
                     "element": "Dark"},
                    {"name": "Plague Emissary", "hp": Decimal('450'), "attack": Decimal('270'),
                     "defense": Decimal('250'), "element": "Corrupted"},
                ],
                11: [  # Legendary monsters for Resistance to battle
                    {"name": "Plague Titan", "hp": Decimal('1000'), "attack": Decimal('500'), "defense": Decimal('400'),
                     "element": "Corrupted"},
                    {"name": "Dark Sovereign", "hp": Decimal('1200'), "attack": Decimal('550'),
                     "defense": Decimal('450'), "element": "Dark"},
                    {"name": "Necrotic Overlord", "hp": Decimal('1500'), "attack": Decimal('600'),
                     "defense": Decimal('500'), "element": "Corrupted"},
                ]
            },
            "Plague": {  # Monsters that Plague can battle (Resistance-based)
                1: [
                    {"name": "Resistance Knight", "hp": Decimal('100'), "attack": Decimal('90'),
                     "defense": Decimal('80'), "element": "Light"},
                    {"name": "Paladin", "hp": Decimal('120'), "attack": Decimal('110'), "defense": Decimal('100'),
                     "element": "Light"},
                    {"name": "Templar", "hp": Decimal('150'), "attack": Decimal('130'), "defense": Decimal('120'),
                     "element": "Light"},
                    {"name": "Arcane Wizard", "hp": Decimal('180'), "attack": Decimal('150'), "defense": Decimal('140'),
                     "element": "Light"},
                    {"name": "Champion of Light", "hp": Decimal('300'), "attack": Decimal('220'),
                     "defense": Decimal('220'), "element": "Light"},
                ],
                2: [
                    {"name": "Holy Avenger", "hp": Decimal('200'), "attack": Decimal('180'), "defense": Decimal('170'),
                     "element": "Light"},
                    {"name": "Divine Sentinel", "hp": Decimal('250'), "attack": Decimal('200'),
                     "defense": Decimal('190'), "element": "Light"},
                    {"name": "Guardian Angel", "hp": Decimal('300'), "attack": Decimal('220'),
                     "defense": Decimal('210'), "element": "Light"},
                    {"name": "Radiant Knight", "hp": Decimal('400'), "attack": Decimal('250'),
                     "defense": Decimal('240'), "element": "Light"},
                    {"name": "Holy Crusader", "hp": Decimal('500'), "attack": Decimal('300'), "defense": Decimal('280'),
                     "element": "Light"},
                ],
                11: [  # Legendary monsters for Plague to battle
                    {"name": "Light Titan", "hp": Decimal('1000'), "attack": Decimal('500'), "defense": Decimal('400'),
                     "element": "Light"},
                    {"name": "Divine Sovereign", "hp": Decimal('1200'), "attack": Decimal('550'),
                     "defense": Decimal('450'), "element": "Light"},
                    {"name": "Radiant Overlord", "hp": Decimal('1500'), "attack": Decimal('600'),
                     "defense": Decimal('500'), "element": "Light"},
                ]
            }
        }

        try:
            # Define class-specific values
            specified_words_values = {
                "Deathshroud": Decimal('20'),
                "Soul Warden": Decimal('30'),
                "Reaper": Decimal('40'),
                "Phantom Scythe": Decimal('50'),
                "Soul Snatcher": Decimal('60'),
                "Deathbringer": Decimal('70'),
                "Grim Reaper": Decimal('80'),
            }

            life_steal_values = {
                "Little Helper": Decimal('7'),
                "Gift Gatherer": Decimal('14'),
                "Holiday Aide": Decimal('21'),
                "Joyful Jester": Decimal('28'),
                "Yuletide Guardian": Decimal('35'),
                "Festive Enforcer": Decimal('40'),
                "Festive Champion": Decimal('60'),
            }

            mage_evolution_levels = {
                "Witcher": 1,
                "Enchanter": 2,
                "Mage": 3,
                "Warlock": 4,
                "Dark Caster": 5,
                "White Sorcerer": 6,
            }

            evolution_damage_multiplier = {
                1: Decimal('1.10'),  # 110%
                2: Decimal('1.20'),  # 120%
                3: Decimal('1.30'),  # 130%
                4: Decimal('1.50'),  # 150%
                5: Decimal('1.75'),  # 175%
                6: Decimal('2.00'),  # 200%
            }

            # Check if the faction has its monster pool defined
            if faction not in monsters:
                await ctx.send("❌ No monsters defined for your faction. Please contact the admin.")
                return

            # Define a mapping for which faction's monsters to battle
            target_faction = "Plague" if faction == "Resistance" else "Resistance"
            target_monsters = monsters[target_faction]

            # Fetch the player's XP and level
            xp = self.player_xp.get(user_id, Decimal('0'))
            player_level = math.floor(math.sqrt(xp / Decimal('100')))  # Simple XP to level formula

            # Send an embed indicating that the player is searching for a monster
            searching_embed = discord.Embed(
                title="🔍 Searching for a Monster...",
                description="Your journey begins as you venture into the unknown to find a worthy foe.",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            searching_embed.set_thumbnail(url="https://i.imgur.com/Search.png")  # Replace with actual image
            searching_message = await ctx.send(embed=searching_embed)

            # Simulate searching time
            await asyncio.sleep(random.randint(3, 7))  # Adjust the sleep time as desired

            # Determine if a legendary monster (level 11) should spawn
            legendary_spawn_chance = Decimal('0.05')  # 5% chance
            spawn_legendary = False
            if player_level >= 5:
                if Decimal(str(random.random())) < legendary_spawn_chance:
                    spawn_legendary = True

            if spawn_legendary:
                # Select one of the legendary monsters (ensure they are defined)
                if 11 not in target_monsters or not target_monsters[11]:
                    await ctx.send("❌ No legendary monsters are available at this time.")
                    return
                monster = random.choice(target_monsters[11])
                # Send a dramatic announcement
                legendary_embed = discord.Embed(
                    title="👑 A Legendary God Appears!",
                    description=f"Behold! **{monster['name']}** has descended to challenge you! Prepare for an epic battle!",
                    color=discord.Color.gold(),
                    timestamp=datetime.utcnow()
                )
                legendary_embed.set_thumbnail(
                    url="https://i.imgur.com/LegendaryMonster.png")  # Replace with actual image
                await ctx.send(embed=legendary_embed)
                levelchoice = Decimal('11')
                await asyncio.sleep(4)
            else:
                # Determine monster level based on player level
                base_monster_level = math.ceil((player_level - 10) / 10) + 3
                base_monster_level = max(1, min(10, base_monster_level))  # Clamp between 1 and 10

                # Add some randomness: monster level can vary by ±1
                monster_level_variation = random.choice([-1, 0, 1])
                levelchoice = base_monster_level + monster_level_variation
                levelchoice = max(1, min(10, levelchoice))  # Ensure level is between 1 and 10
                levelchoice = Decimal(str(levelchoice))

                # Select a random monster from the chosen level
                if int(levelchoice) not in target_monsters or not target_monsters[int(levelchoice)]:
                    await ctx.send(f"❌ No monsters available at level {int(levelchoice)}.")
                    return
                monster = random.choice(target_monsters[int(levelchoice)])

                # Edit the searching message to indicate that a monster has been found
                found_embed = discord.Embed(
                    title="🐉 Monster Found!",
                    description=f"A Level {int(levelchoice)} **{monster['name']}** has appeared! Prepare to fight..",
                    color=discord.Color.red(),
                    timestamp=datetime.utcnow()
                )
                found_embed.set_thumbnail(url="https://i.imgur.com/MonsterFound.png")  # Replace with actual image
                await searching_message.edit(embed=found_embed)
                await asyncio.sleep(4)

            async with self.bot.pool.acquire() as conn:
                luck_booster = await self.bot.get_booster(ctx.author, "luck")

                # Fetch luck, health, stathp, and class
                query = 'SELECT "luck", "health", "stathp", "class" FROM profile WHERE "user" = $1;'
                result = await conn.fetchrow(query, user_id)
                if result:
                    luck_value = Decimal(str(result['luck']))
                    if luck_value <= Decimal('0.3'):
                        Luck = Decimal('20.0')
                    else:
                        Luck = ((luck_value - Decimal('0.3')) / (Decimal('1.5') - Decimal('0.3'))) * Decimal(
                            '80') + Decimal('20')
                    Luck = Luck.quantize(Decimal('0.01'))

                    if luck_booster:
                        Luck += Luck * Decimal('0.25')
                        Luck = min(Luck, Decimal('100.00'))

                    base_health = Decimal('250')
                    health = Decimal(str(result['health'])) + base_health
                    stathp = Decimal(str(result['stathp'])) * Decimal('50')
                    dmg, deff = await self.bot.get_raidstats(ctx.author, conn=conn)

                    total_health = health + (Decimal(str(player_level)) * Decimal('5')) + stathp

                    # Fetch classes
                    player_classes = result['class']
                    if isinstance(player_classes, list):
                        player_classes = player_classes
                    else:
                        player_classes = [player_classes]

                    # Calculate class-based chances
                    author_chance = Decimal('0.0')
                    lifestealauth = Decimal('0.0')

                    # Function to get Mage evolution level
                    def get_mage_evolution(classes):
                        max_evolution = None
                        for class_name in classes:
                            if class_name in mage_evolution_levels:
                                level = mage_evolution_levels[class_name]
                                if max_evolution is None or level > max_evolution:
                                    max_evolution = level
                        return max_evolution

                    author_mage_evolution = get_mage_evolution(player_classes)
                    for class_name in player_classes:
                        if class_name in specified_words_values:
                            author_chance += specified_words_values[class_name]
                        if class_name in life_steal_values:
                            lifestealauth += life_steal_values[class_name]

                    # Initialize player stats
                    player_stats = {
                        "user": ctx.author,
                        "hp": total_health.quantize(Decimal('0.001')),
                        "max_hp": total_health.quantize(Decimal('0.001')),
                        "armor": Decimal(str(deff)),
                        "damage": Decimal(str(dmg)),
                        "luck": Luck,
                        "mage_evolution": author_mage_evolution,
                        "lifesteal": lifestealauth,
                        "element": None  # Will be set below
                    }

                    # Fetch player's equipped items to determine element
                    highest_element = None
                    try:
                        highest_items = await conn.fetch(
                            "SELECT ai.element FROM profile p JOIN allitems ai ON (p.user=ai.owner) JOIN"
                            " inventory i ON (ai.id=i.item) WHERE i.equipped IS TRUE AND p.user=$1"
                            " ORDER BY GREATEST(ai.damage, ai.armor) DESC;",
                            user_id,
                        )

                        if highest_items:
                            elements = [item["element"].capitalize() for item in highest_items]
                            highest_element = elements[0]  # Choose the highest priority element
                            player_stats["element"] = highest_element
                    except Exception as e:
                        await ctx.send(f"An error occurred while fetching player's element: {e}")

                else:
                    await ctx.send("❌ Your profile could not be found.")
                    return

            # Initialize monster stats
            monster_stats = {
                "name": monster["name"],
                "hp": monster["hp"],
                "max_hp": monster["hp"],
                "armor": monster["defense"],
                "damage": monster["attack"],
                "element": monster["element"]
            }

            # Function to calculate damage modifier based on elements
            def calculate_damage_modifier(attacker_element, defender_element):
                if attacker_element in element_strengths and element_strengths[attacker_element] == defender_element:
                    return Decimal(str(round(random.uniform(0.1, 0.3), 3)))  # Increase damage by 10-30%
                elif defender_element in element_strengths and element_strengths[defender_element] == attacker_element:
                    return Decimal(str(round(random.uniform(-0.3, -0.1), 3)))  # Decrease damage by 10-30%
                return Decimal('0.000')

            # Calculate damage modifiers
            damage_modifier_player = Decimal('0.000')
            if player_stats["element"]:
                damage_modifier_player = calculate_damage_modifier(player_stats["element"], monster_stats["element"])

            # Function to create HP bar
            def create_hp_bar(current_hp, max_hp, length=20):
                ratio = current_hp / max_hp if max_hp > Decimal('0') else Decimal('0')
                ratio = max(Decimal('0'), min(Decimal('1'), ratio))  # Ensure ratio is between 0 and 1
                filled_length = int(ratio * Decimal(str(length)))
                bar = '█' * filled_length + '░' * (length - filled_length)
                return bar

            # Initialize ability effects
            ability_effects = {
                "damage_increase": Decimal('0.0'),
                "damage_reduction": Decimal('0.0'),
                "lifesteal": Decimal('0.0'),
                "critical_chance": Decimal('0.0'),
                "summon": Decimal('0'),
                "area_damage": Decimal('0.0'),
                "stun_chance": Decimal('0.0'),
                "instant_defeat": False,
                "enemy_damage_reduction": Decimal('0.0'),
                "resource_efficiency": Decimal('0.0')
            }
            current_rank, _ = await self.get_player_rank(user_id)
            # Apply abilities
            if current_rank and current_rank["abilities"]:
                for ability in current_rank["abilities"]:
                    effects = ABILITY_EFFECTS.get(ability, {})
                    for key, value in effects.items():
                        if key in ability_effects:
                            if isinstance(value, (int, float, Decimal)):
                                ability_effects[key] += Decimal(str(value))
                            elif isinstance(value, str):
                                ability_effects[key] = value

            # Begin the battle
            battle_log = deque(
                [
                    (
                        0,
                        f"You have encountered a Level {int(levelchoice)} **{monster_stats['name']}**!"
                    )
                ],
                maxlen=10,
            )

            # Create initial embed
            embed = discord.Embed(
                title="⚔️ Raid Battle PvE",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )

            # Initialize player stats in the embed
            current_hp = player_stats["hp"].quantize(Decimal('0.001'))
            max_hp = player_stats["max_hp"].quantize(Decimal('0.001'))
            hp_bar = create_hp_bar(current_hp, max_hp)
            element_emoji = element_to_emoji.get(player_stats["element"], "❌") if player_stats["element"] else "❌"
            field_name = f"{player_stats['user'].display_name} {element_emoji}"
            field_value = f"**HP:** {current_hp}/{max_hp}\n{hp_bar}"
            embed.add_field(name=field_name, value=field_value, inline=False)

            # Initialize monster stats in the embed
            monster_current_hp = monster_stats["hp"].quantize(Decimal('0.001'))
            monster_max_hp = monster_stats["max_hp"].quantize(Decimal('0.001'))
            monster_hp_bar = create_hp_bar(monster_current_hp, monster_max_hp)
            monster_element_emoji = element_to_emoji.get(monster_stats["element"], "❌")
            monster_field_name = f"{monster_stats['name']} {monster_element_emoji}"
            monster_field_value = f"**HP:** {monster_current_hp}/{monster_max_hp}\n{monster_hp_bar}"
            embed.add_field(name=monster_field_name, value=monster_field_value, inline=False)

            # Add initial battle log
            embed.add_field(name="📝 Battle Log", value=battle_log[0][1], inline=False)

            log_message = await ctx.send(embed=embed)
            await asyncio.sleep(4)

            start = datetime.utcnow()
            player_turn = random.choice([True, False])

            # Main battle loop
            while (
                    player_stats["hp"] > Decimal('0')
                    and monster_stats["hp"] > Decimal('0')
                    and datetime.utcnow() < start + timedelta(minutes=10)
            ):
                if player_turn:
                    attacker = player_stats
                    defender = monster_stats
                    attacker_type = "player"
                    defender_type = "monster"
                else:
                    attacker = monster_stats
                    defender = player_stats
                    attacker_type = "monster"
                    defender_type = "player"

                trickluck = Decimal(str(random.randint(1, 100)))

                if player_turn:
                    attacker_luck = attacker["luck"]
                else:
                    attacker_luck = Decimal('80')  # Monsters have a fixed luck of 80

                if trickluck < attacker_luck:
                    # Attack hits
                    if player_turn:
                        # Player's turn
                        # Calculate base damage
                        dmg = attacker["damage"] + Decimal(str(random.randint(0, 50))) - defender["armor"]
                        dmg = max(dmg, Decimal('1.0'))
                        dmg = dmg.quantize(Decimal('0.001'))
                        # Apply damage modifiers for player attacks
                        if damage_modifier_player != Decimal('0.000'):
                            dmg = dmg * (Decimal('1.0') + damage_modifier_player)
                            dmg = dmg.quantize(Decimal('0.001'))
                        # Apply abilities that increase damage
                        dmg = dmg * (Decimal('1.0') + ability_effects.get("damage_increase", Decimal('0.0')))
                        dmg = dmg.quantize(Decimal('0.001'))
                        # Apply lifesteal
                        lifesteal = ability_effects.get("lifesteal", Decimal('0.0'))
                        if lifesteal > Decimal('0.0'):
                            stolen = min(lifesteal, dmg)
                            attacker["hp"] += stolen
                            attacker["hp"] = min(attacker["hp"], attacker["max_hp"])
                            stolen = stolen.quantize(Decimal('0.001'))
                            message = f"⚔️ You attack! **{monster_stats['name']}** takes **{dmg} HP** damage and you steal **{stolen} HP**."
                        else:
                            message = f"⚔️ You attack! **{monster_stats['name']}** takes **{dmg} HP** damage."
                        # Apply area damage if applicable
                        if ability_effects.get("area_damage", Decimal('0.0')) > Decimal('0.0'):
                            area_dmg = ability_effects["area_damage"]
                            monster_stats["hp"] -= area_dmg
                            monster_stats["hp"] = max(monster_stats["hp"], Decimal('0.0'))
                            area_dmg = area_dmg.quantize(Decimal('0.001'))
                            message += f"\n🌐 Area Damage: **{area_dmg} HP** dealt to all enemies."
                        # Apply special attacks
                        if ability_effects.get("special_attack") == "Double Damage":
                            extra_dmg = dmg * Decimal('2.0')
                            monster_stats["hp"] -= extra_dmg
                            monster_stats["hp"] = max(monster_stats["hp"], Decimal('0.0'))
                            extra_dmg = extra_dmg.quantize(Decimal('0.001'))
                            message += f"\n💥 **Double Damage** activated! **{monster_stats['name']}** takes an additional **{extra_dmg} HP** damage."
                    else:
                        # Monster's turn
                        # Calculate base damage
                        dmg = attacker["damage"] + Decimal(str(random.randint(0, 50))) - defender["armor"]
                        dmg = max(dmg, Decimal('1.0'))
                        dmg = dmg.quantize(Decimal('0.001'))
                        # Apply abilities that decrease player's damage
                        dmg = dmg * (Decimal('1.0') - ability_effects.get("enemy_damage_reduction", Decimal('0.0')))
                        dmg = dmg.quantize(Decimal('0.001'))
                        # Apply abilities like instant defeat
                        if ability_effects.get("instant_defeat", False):
                            defender["hp"] = Decimal('0.0')
                            message = f"🦴 **{monster_stats['name']}** uses **Instant Defeat**! You are defeated instantly."
                        else:
                            # Apply area damage if applicable
                            if ability_effects.get("area_damage", Decimal('0.0')) > Decimal('0.0'):
                                area_dmg = ability_effects["area_damage"]
                                defender["hp"] -= area_dmg
                                defender["hp"] = max(defender["hp"], Decimal('0.0'))
                                area_dmg = area_dmg.quantize(Decimal('0.001'))
                                message = f"🦴 **{monster_stats['name']}** attacks! You take **{dmg} HP** damage.\n🌐 Area Damage: **{area_dmg} HP** dealt to all enemies."
                            else:
                                message = f"🦴 **{monster_stats['name']}** attacks! You take **{dmg} HP** damage."
                            # Apply lifesteal or other effects if applicable
                            if ability_effects.get("lifesteal", Decimal('0.0')) > Decimal('0.0'):
                                stolen = min(ability_effects["lifesteal"], dmg)
                                attacker["hp"] += stolen
                                attacker["hp"] = min(attacker["hp"], attacker["max_hp"])
                                stolen = stolen.quantize(Decimal('0.001'))
                                message += f"\n🔄 **Lifesteal:** **{stolen} HP** stolen by **{monster_stats['name']}**."
                else:
                    # Attack misses or attacker trips
                    if player_turn:
                        message = f"😵 You attempt to attack but miss! **{monster_stats['name']}** evades your strike."
                    else:
                        message = f"🦴 **{monster_stats['name']}** attempts to attack but misses! You dodge the strike."

                # Append message to battle log
                battle_log.append(
                    (
                        battle_log[-1][0] + 1,
                        message,
                    )
                )

                # Update the embed
                embed = discord.Embed(
                    title="⚔️ Raid Battle PvE",
                    color=discord.Color.blue(),
                    timestamp=datetime.utcnow()
                )

                # Update player stats in the embed
                current_hp = player_stats["hp"].quantize(Decimal('0.001'))
                hp_bar = create_hp_bar(current_hp, player_stats["max_hp"])
                embed.add_field(name=field_name, value=f"**HP:** {current_hp}/{player_stats['max_hp']}\n{hp_bar}",
                                inline=False)

                # Update monster stats in the embed
                monster_current_hp = monster_stats["hp"].quantize(Decimal('0.001'))
                monster_hp_bar = create_hp_bar(monster_current_hp, monster_stats["max_hp"])
                embed.add_field(name=monster_field_name,
                                value=f"**HP:** {monster_current_hp}/{monster_stats['max_hp']}\n{monster_hp_bar}",
                                inline=False)

                # Update battle log in the embed
                battle_log_text = ''
                for line in battle_log:
                    battle_log_text += f"**Action #{line[0]}**\n{line[1]}\n"

                embed.add_field(name="📝 Battle Log", value=battle_log_text, inline=False)

                await log_message.edit(embed=embed)
                await asyncio.sleep(4)

                # Check if battle has ended
                if player_stats["hp"] <= Decimal('0') or monster_stats["hp"] <= Decimal('0'):
                    break  # Battle ends

                # Swap turn for the next round
                player_turn = not player_turn

            # Determine the outcome
            if player_stats["hp"] > Decimal('0') and monster_stats["hp"] <= Decimal('0'):
                # Player wins
                if levelchoice == Decimal('11'):
                    base_xp_gain = Decimal(str(random.randint(75000, 125000)))  # Higher XP for legendary monsters
                else:
                    base_xp_gain = Decimal(str(random.randint(int(levelchoice) * 300,
                                                              int(levelchoice) * 1000)))  # XP based on monster level

                # Award XP considering abilities
                xp_multiplier = Decimal('1.0')
                if current_rank and current_rank["abilities"]:
                    for ability in current_rank["abilities"]:
                        if ability in ABILITY_EFFECTS and "xp_increase" in ABILITY_EFFECTS[ability]:
                            xp_multiplier += Decimal(str(ABILITY_EFFECTS[ability]["xp_increase"]))
                total_xp_gain = (base_xp_gain * xp_multiplier).to_integral_value()

                # Update player's XP
                self.player_xp[user_id] = self.player_xp.get(user_id, Decimal('0')) + total_xp_gain
                await self.promote_player(user_id)

                # Handle egg drop chance
                egg_drop_chance = Decimal('0.05')  # 5% chance
                egg_found = False
                if Decimal(str(random.random())) < egg_drop_chance:
                    egg_found = True
                    egg_hatch_time = datetime.utcnow() + timedelta(
                        hours=int(12 * levelchoice))  # Hatches in 12*level hours
                    # Placeholder for egg storage logic
                    # Implement database storage or in-memory storage as needed

                # Send victory embed with narrative
                narrative = random.choice([
                    f"🔥 After a fierce battle, **{ctx.author.display_name}** triumphs over **{monster_stats['name']}**!",
                    f"🏆 **{ctx.author.display_name}** successfully defeats **{monster_stats['name']}**, earning valuable XP!",
                    f"⚔️ The battle is won! **{ctx.author.display_name}** slays **{monster_stats['name']}** with valor!",
                    f"🌟 **{ctx.author.display_name}** stands victorious against **{monster_stats['name']}**!",
                    f"💪 **{ctx.author.display_name}** overcomes **{monster_stats['name']}**, showcasing unmatched strength!"
                ])

                embed = discord.Embed(
                    title="🏆 Victory!",
                    description=f"{narrative}\n\nYou defeated the **{monster_stats['name']}** and gained **{total_xp_gain} XP**!",
                    color=discord.Color.green(),
                    timestamp=datetime.utcnow()
                )
                embed.set_thumbnail(url="https://i.imgur.com/Victory.png")  # Replace with actual image

                if egg_found:
                    embed.add_field(
                        name="🥚 Egg Found!",
                        value=f"You found a **{monster_stats['name']} Egg**! It will hatch in {int(12 * levelchoice)} hours.",
                        inline=False
                    )

                await ctx.send(embed=embed)

            elif monster_stats["hp"] > Decimal('0') and player_stats["hp"] <= Decimal('0'):
                # Player loses
                narrative = random.choice([
                    f"💀 **{ctx.author.display_name}** has fallen in battle against **{monster_stats['name']}**.",
                    f"😔 Despite the fight, **{ctx.author.display_name}** is defeated by **{monster_stats['name']}**.",
                    f"⚰️ **{ctx.author.display_name}** succumbs to the might of **{monster_stats['name']}**.",
                    f"🔥 **{ctx.author.display_name}** is overwhelmed by **{monster_stats['name']}**.",
                    f"🌑 **{ctx.author.display_name}** meets a grim fate at the hands of **{monster_stats['name']}**."
                ])

                embed = discord.Embed(
                    title="💀 Defeat",
                    description=f"{narrative}\n\nYou were defeated by the **{monster_stats['name']}**. Better luck next time!",
                    color=discord.Color.red(),
                    timestamp=datetime.utcnow()
                )
                embed.set_thumbnail(url="https://i.imgur.com/Defeat.png")  # Replace with actual image
                await ctx.send(embed=embed)

            else:
                # Tie
                narrative = random.choice([
                    f"⚖️ The battle between **{ctx.author.display_name}** and **{monster_stats['name']}** ends in a stalemate.",
                    f"🌓 Both **{ctx.author.display_name}** and **{monster_stats['name']}** fall back, neither claiming victory.",
                    f"🌗 The confrontation results in a tie. Both sides retreat to recover.",
                    f"🌪️ The clash between **{ctx.author.display_name}** and **{monster_stats['name']}** is evenly matched, leading to a draw.",
                    f"🔄 The duel between **{ctx.author.display_name}** and **{monster_stats['name']}** concludes without a clear winner."
                ])

                embed = discord.Embed(
                    title="⚖️ Tie",
                    description=f"{narrative}\n\nThe battle ended in a tie. No XP gained.",
                    color=discord.Color.gray(),
                    timestamp=datetime.utcnow()
                )
                embed.set_thumbnail(url="https://i.imgur.com/Tie.png")  # Replace with actual image
                await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"An unexpected error occurred: {e}")

    # View Faction Status
    @plague_group.command(name="view")
    async def view_status(self, ctx):
        """View the current state of factions and regions."""
        if not self.event_active:
            await ctx.send("❌ The Plague of the Undying event is not currently active.")
            return

        embed = discord.Embed(
            title="🗺️ Current State of Factions and Regions",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        # Faction statuses with emojis
        faction_emojis = {
            "Resistance": "🛡️",
            "Plague": "☠️"
        }

        for faction_name, data in self.factions.items():
            embed.add_field(
                name=f"{faction_emojis.get(faction_name, '')} {faction_name} Forces",
                value=(
                    f"**Total Forces:** {data['forces']}\n"
                    f"**Gold:** {data['resources']['gold']} 🪙\n"
                    f"**Materials:** {data['resources']['materials']} 🪓"
                ),
                inline=False
            )

        # Region statuses with emojis
        region_emojis = {
            "Northwatch": "🏰",
            "Eastvale": "🌲",
            "Southport": "⚓",
            "Westwood": "🌳",
            "Central City": "🏙️",
        }

        for region_name, data in self.regions.items():
            controlled_by = data["controlled_by"] if data["controlled_by"] else "🟢 Neutral"
            resistance_forces = data["forces"]["Resistance"]
            plague_forces = data["forces"]["Plague"]
            embed.add_field(
                name=f"{region_emojis.get(region_name, '')} {region_name}",
                value=(
                    f"**Controlled by:** {controlled_by}\n"
                    f"**🛡️ Resistance Forces:** {resistance_forces}\n"
                    f"**☠️ Plague Forces:** {plague_forces}"
                ),
                inline=False
            )

        # Overall Event Status with a progress bar
        total_forces = self.factions["Resistance"]["forces"] + self.factions["Plague"]["forces"]
        resistance_percentage = (self.factions["Resistance"]["forces"] / total_forces) * 100 if total_forces > 0 else 0
        plague_percentage = (self.factions["Plague"]["forces"] / total_forces) * 100 if total_forces > 0 else 0
        progress_bar = "█" * int(resistance_percentage / 10) + "░" * (10 - int(resistance_percentage / 10))
        embed.add_field(
            name="📊 Overall Faction Dominance",
            value=(
                f"**🛡️ Resistance:** {resistance_percentage:.1f}%\n"
                f"{progress_bar}\n"
                f"**☠️ Plague:** {plague_percentage:.1f}%"
            ),
            inline=False
        )

        # Add a summary of recent events
        if self.daily_events:
            recent_events = "\n".join(list(self.daily_events)[-5:])
            embed.add_field(
                name="📰 Recent Events",
                value=recent_events,
                inline=False
            )

        embed.set_footer(text="Keep contributing to your faction to dominate the apocalypse!")
        await ctx.send(embed=embed)

    # Hourly Update Task
    async def hourly_update(self):
        """Updates the forces count every hour and narrates random events."""
        await self.bot.wait_until_ready()
        while True:
            await asyncio.sleep(3600)  # Wait for one hour
            if not self.event_active:
                continue
            # Adjust forces based on events
            for faction in self.factions:
                self.factions[faction]["forces"] += random.randint(5, 15)
            self.daily_events.append("📈 Forces have been updated due to hourly changes.")

            # Narrate random events
            event = random.choice([
                "🌟 A wandering healer boosts the morale of the Resistance forces.",
                "💀 The Plague Lord raises more undead to bolster his army.",
                "⚔️ A skirmish results in losses on both sides.",
                "🔥 A supply line is disrupted, causing resource shortages.",
                "🚩 Reinforcements arrive for the Resistance."
            ])
            self.daily_events.append(event)
            # Send update to announcement channel
            guild = self.bot.get_guild(GUILD_ID)
            announcement_channel = guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)
            embed = discord.Embed(
                title="🕒 Hourly Update",
                description=event,
                color=discord.Color.orange(),
                timestamp=datetime.utcnow()
            )
            embed.set_thumbnail(url="https://i.imgur.com/HourlyUpdate.png")  # Replace with actual image
            await announcement_channel.send(embed=embed)

    # Region Battles Task
    async def region_battles(self):
        """Handle battles over regions between factions."""
        await self.bot.wait_until_ready()
        while True:
            await asyncio.sleep(1800)  # Adjust timing as needed (e.g., every 30 minutes)
            if not self.event_active:
                continue
            for region_name, data in self.regions.items():
                resistance_forces = data["forces"]["Resistance"]
                plague_forces = data["forces"]["Plague"]

                if resistance_forces > plague_forces:
                    data["controlled_by"] = "Resistance"
                elif plague_forces > resistance_forces:
                    data["controlled_by"] = "Plague"
                else:
                    data["controlled_by"] = "🟢 Neutral"

                # Adjust forces due to battles
                battle_loss = random.randint(0, min(resistance_forces, plague_forces))
                self.factions["Resistance"]["forces"] -= battle_loss
                self.factions["Plague"]["forces"] -= battle_loss

                if battle_loss > 0:
                    self.daily_events.append(f"⚔️ Battle in {region_name}: Both factions lost {battle_loss} forces.")

            # Announce region battle outcomes
            await self.announce_daily_events()

    # Announce Daily Events
    async def announce_daily_events(self):
        """Announce the major events of the hour."""
        if not self.daily_events:
            return
        guild = self.bot.get_guild(GUILD_ID)
        announcement_channel = guild.get_channel(ANNOUNCEMENT_CHANNEL_ID)
        events = "\n".join(self.daily_events)
        embed = discord.Embed(
            title="📢 Event Summary",
            description=events,
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.set_thumbnail(url="https://i.imgur.com/EventSummary.png")  # Replace with actual image
        await announcement_channel.send(embed=embed)
        # Clear the events for the next cycle
        self.daily_events.clear()

    # Custom Cooldown Helper Functions
    def has_acted_recently(self, user_id, action):
        """Check if the player has performed a specific action recently."""
        if user_id not in self.action_cooldowns:
            return False
        if action not in self.action_cooldowns[user_id]:
            return False
        last_act_time = self.action_cooldowns[user_id][action]
        cooldown_periods = {
            'gather_resources': 3600,  # 1 hour
            'recruit': 3600  # 1 hour
        }
        cooldown = cooldown_periods.get(action, 3600)
        if (datetime.utcnow() - last_act_time).total_seconds() < cooldown:
            return True
        return False

    def get_cooldown_remaining(self, user_id, action):
        """Get the remaining cooldown time in minutes and seconds."""
        if user_id not in self.action_cooldowns or action not in self.action_cooldowns[user_id]:
            return "0s"
        last_act_time = self.action_cooldowns[user_id][action]
        cooldown_periods = {
            'gather_resources': 3600,  # 1 hour
            'recruit': 3600  # 1 hour
        }
        cooldown = cooldown_periods.get(action, 3600)
        elapsed = (datetime.utcnow() - last_act_time).total_seconds()
        remaining = cooldown - elapsed
        if remaining <= 0:
            return "0s"
        minutes, seconds = divmod(int(remaining), 60)
        return f"{minutes}m {seconds}s"

    def set_player_action(self, user_id, action):
        """Set that the player has performed a specific action recently."""
        if user_id not in self.action_cooldowns:
            self.action_cooldowns[user_id] = {}
        self.action_cooldowns[user_id][action] = datetime.utcnow()

    # Lore Command already implemented above

    # Cog unload to cancel tasks
    def cog_unload(self):
        if self.conclude_event_task:
            self.conclude_event_task.cancel()
        if self.hourly_update_task:
            self.hourly_update_task.cancel()
        if self.region_battles_task:
            self.region_battles_task.cancel()

    # Admin Commands for Testing and Control
    @plague_group.command(name="start_event")
    @commands.has_permissions(administrator=True)
    async def start_event_command(self, ctx):
        """Admin command to start the event."""
        if self.event_active:
            await ctx.send("❌ The Plague of the Undying event is already active.")
            return
        self.event_active = True
        self.event_start_time = datetime.utcnow()
        await self.send_event_start()
        await ctx.send("✅ Plague of the Undying event has started!")
        # Add narrative
        narrative = random.choice([
            "🔥 The fires of the apocalypse begin to burn as the Plague of the Undying takes hold.",
            "🌪️ Chaos ensues as the Plague of the Undying spreads across the land.",
            "🌑 Darkness falls as the Plague of the Undying corrupts everything in its path."
        ])
        self.daily_events.append(narrative)

    @plague_group.command(name="stop_event")
    @commands.has_permissions(administrator=True)
    async def stop_event_command(self, ctx):
        """Admin command to stop the event."""
        if not self.event_active:
            await ctx.send("❌ The Plague of the Undying event is not currently active.")
            return
        self.event_active = False
        self.conclude_event_task.cancel()
        self.hourly_update_task.cancel()
        self.region_battles_task.cancel()
        await ctx.send("🛑 Plague of the Undying event has been stopped.")
        # Add narrative
        narrative = random.choice([
            "⚰️ The Plague of the Undying recedes, leaving behind a trail of devastation.",
            "🌤️ Calm returns as the Plague of the Undying is quelled.",
            "🌅 The sun rises over a land scarred by the Plague of the Undying."
        ])
        self.daily_events.append(narrative)

    @plague_group.command(name="reset_event")
    @commands.has_permissions(administrator=True)
    async def reset_event_command(self, ctx):
        """Admin command to reset the event."""
        await self.reset_event()
        await ctx.send("🔄 Plague of the Undying event has been reset.")
        # Add narrative
        narrative = random.choice([
            "🔄 The Plague of the Undying has been reset, ready to commence anew.",
            "🌀 A fresh cycle begins as the Plague of the Undying is reset.",
            "✨ Reset complete! The Plague of the Undying stands ready to erupt once more."
        ])
        self.daily_events.append(narrative)

    @plague_group.command(name="advance_faction")
    @commands.has_permissions(administrator=True)
    async def advance_faction_command(self, ctx, faction: str, amount: int):
        """Admin command to adjust faction forces."""
        faction = faction.capitalize()
        if faction not in self.factions:
            await ctx.send("❌ Invalid faction. Choose either `Resistance` or `Plague`.")
            return
        if amount < 0 and self.factions[faction]["forces"] + amount < 0:
            await ctx.send("❌ Cannot reduce forces below zero.")
            return
        self.factions[faction]["forces"] += amount
        await ctx.send(
            f"📈 **{faction}** forces have been adjusted by {amount}. Total forces: {self.factions[faction]['forces']}.")

        # Add narrative for admin action
        narrative = f"🔧 Admin adjusted **{faction}** forces by {amount}. Total forces: {self.factions[faction]['forces']}."
        self.daily_events.append(narrative)

    @plague_group.command(name="force_transfer")
    @commands.has_permissions(administrator=True)
    async def force_transfer_command(self, ctx, from_faction: str, to_faction: str, amount: int):
        """Admin command to transfer forces between factions."""
        from_faction = from_faction.capitalize()
        to_faction = to_faction.capitalize()
        if from_faction not in self.factions or to_faction not in self.factions:
            await ctx.send("❌ Invalid factions. Choose either `Resistance` or `Plague`.")
            return
        if self.factions[from_faction]["forces"] < amount:
            await ctx.send(f"❌ **{from_faction}** does not have enough forces to transfer.")
            return
        self.factions[from_faction]["forces"] -= amount
        self.factions[to_faction]["forces"] += amount
        await ctx.send(f"🔄 Transferred {amount} forces from **{from_faction}** to **{to_faction}**.")

        # Add narrative for admin action
        narrative = f"🔄 Admin transferred {amount} forces from **{from_faction}** to **{to_faction}**."
        self.daily_events.append(narrative)

    @plague_group.command(name="set_xp")
    @commands.has_permissions(administrator=True)
    async def set_xp_command(self, ctx, member: discord.Member, xp: int):
        """Admin command to set a member's XP."""
        user_id = member.id
        if user_id not in self.player_factions:
            await ctx.send(f"❌ {member.display_name} is not part of any faction.")
            return
        self.player_xp[user_id] = xp
        await self.promote_player(user_id)
        await ctx.send(f"✅ Set {member.display_name}'s XP to {xp}.")
        # Add narrative
        narrative = f"📊 Admin set **{member.display_name}**'s XP to {xp}."
        self.daily_events.append(narrative)

    @plague_group.command(name="rank_up")
    @commands.has_permissions(administrator=True)
    async def rank_up_command(self, ctx, member: discord.Member):
        """Admin command to manually promote a member."""
        user_id = member.id
        if user_id not in self.player_factions:
            await ctx.send(f"❌ {member.display_name} is not part of any faction.")
            return
        await self.promote_player(user_id)
        await ctx.send(f"🎉 Promoted {member.display_name} if eligible.")
        # Add narrative
        narrative = f"🎉 Admin promoted **{member.display_name}** if eligible."
        self.daily_events.append(narrative)

    # Additional Commands (e.g., Quests, Profile) can be implemented similarly


# Setup function to add the Cog to the bot
async def setup(bot):
    await bot.add_cog(PlagueOfTheUndying(bot))
