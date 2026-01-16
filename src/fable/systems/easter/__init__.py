import discord
from discord.ext import commands
from fable.systems.shard_communication import user_on_cooldown as user_cooldown
import asyncio
import random
from .permissions import grant_team_channel_access
import math
from datetime import datetime, timedelta
from collections import deque, Counter
import typing
from typing import Optional, List
import fable.utils.misc as rpgtools

from fable.utils.checks import has_char, is_gm
from fable.systems.help import commands as cmd
from fable.utils.i18n import _, locale_doc

class Easter(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.enabled = False
        self.join_phase = False  # New: Track join phase
        self.customization_phase = False
        self.event_active = False  # New: Track if main event is active
        self.pending_participants = []  # Users who joined event but not yet assigned to teams
        self.per_user_stat_points = {}  # {user_id: {'team': str, 'hp': int, 'attack': int, 'defense': int, 'allocated': int}}
        self.ongoing_team_battles = set()  # Track teams currently in battle formation or battle
        self.teams = {
            "Dawn Protectors": {
                "color": discord.Color.gold(),
                "emoji": "🌅",
                "channel_id": 1361313948091285574,  # Hare channel
                "guardian": {
                    "name": "Solara, The Radiant Hare",
                    "description": "A golden-furred hare radiating sunlight, crowned with brilliant egg-shaped crystals.",
                    "image": "https://i.imgur.com/solara_image.png",
                    "base_hp": 5000000,  # Increased for week-long battles
                    "base_attack": 600,
                    "base_defense": 200,
                    "defeated": False,  # Track if guardian is defeated
                    "abilities": [
                        {"name": "Sunrise Beam", "damage": 1200, "effect": "stun", "chance": 0.3, "unlocked": False,
                         "description": "Focuses the power of dawn into a stunning beam of light"},
                        {"name": "Hopping Burst", "damage": 800, "effect": "aoe", "chance": 0.1, "unlocked": False,
                         "description": "Leaps around the battlefield, dealing damage to all enemies"},
                        {"name": "Golden Egg Barrage", "damage": 600, "effect": "dot", "chance": 0.3, "unlocked": False,
                         "description": "Hurls enchanted eggs that crack and leak damaging golden energy over time"},
                        {"name": "Radiant Surge", "damage": 0, "effect": "self_buff", "chance": 0.2, "unlocked": False,
                         "description": "Floods the battlefield with radiant energy, boosting Solara's attack and defense for 3 turns"},
                        {"name": "Radiant Eruption", "damage": 1800, "effect": "radiant_eruption", "chance": 0.2, "unlocked": False,
                         "description": "Creates a massive explosion of solar energy with chance to blind opponents"},
                        {"name": "Solar Renewal", "damage": 0, "effect": "purge_and_shield", "chance": 0.1, "unlocked": False,
                         "description": "Solara channels sunlight to purge all debuffs and gains a powerful shield for 2 turns"},
                        {"name": "Time Dilation", "damage": 0, "effect": "extra_turn", "chance": 0.15, "unlocked": False,
                         "description": "Solara bends time, granting herself a chance to act twice in the next round"}
                    ]
                },
                "members": [],
                "eggs_collected": 0,
                "victories": 0,
                "defeats": 0,
                "upgrades": {
                    "hp_boost": 0,
                    "attack_boost": 0,
                    "defense_boost": 0,
                    "ability_votes": {}
                },
                "customization": {
                    "votes": {},  # Player votes for stat allocation
                    "ability_votes": {},  # Player votes for starting ability
                    "points_allocated": {
                        "hp": 0,
                        "attack": 0,
                        "defense": 0
                    },
                    "finalized": False  # Whether customization is complete
                }
            },
            "Twilight Keepers": {
                "color": discord.Color.purple(),
                "emoji": "🌙",
                "channel_id": 1361313969117073619,  # Drake channel
                "guardian": {
                    "name": "Umbra, The Shadow Drake",
                    "description": "A sleek, dark-scaled drake with obsidian eggs embedded along its spine.",
                    "image": "https://i.imgur.com/umbra_image.png",
                    "base_hp": 5000000,  # Increased for week-long battles
                    "base_attack": 600,
                    "base_defense": 200,
                    "defeated": False,  # Track if guardian is defeated
                    "abilities": [
                        {"name": "Void Strike", "damage": 1500, "effect": "random_debuff", "chance": 0.3, "unlocked": False,
                         "description": "A strike infused with void energy that applies a random debuff"},
                        {"name": "Shadow Clutch", "damage": 600, "effect": "steal_buffs", "chance": 0.3, "unlocked": False,
                         "description": "Steals beneficial effects from enemies and applies them to Umbra"},
                        {"name": "Twilight Breath", "damage": 1000, "effect": "dot", "chance": 0.4, "unlocked": False,
                         "description": "Breathes a cloud of twilight energy that damages enemies over time"},
                        {"name": "Midnight Veil", "damage": 0, "effect": "self_shadow_shield", "chance": 0.2, "unlocked": False,
                         "description": "Umbra cloaks itself in shadows, reducing incoming damage by 50% for 2 turns"},
                        {"name": "Eclipse Force", "damage": 2000, "effect": "eclipse_force", "chance": 0.2, "unlocked": False,
                         "description": "Charges dark energy that executes enemies below 20% health and heals Umbra"},
                        {"name": "Shadow Realm", "damage": 600, "effect": "shadow_realm", "chance": 0.15, "unlocked": False,
                         "description": "Banishes target to the shadow realm, dealing 600 damage per turn for 3 turns"},
                        {"name": "Nightmare Gaze", "damage": 0, "effect": "nightmare_gaze", "chance": 0.1, "unlocked": False,
                         "description": "Hypnotizes an enemy, causing them to lose a turn and take increased damage for 2 turns"}
                    ]
                },
                "members": [],
                "eggs_collected": 0,
                "victories": 0,
                "defeats": 0,
                "upgrades": {
                    "hp_boost": 0,
                    "attack_boost": 0,
                    "defense_boost": 0,
                    "ability_votes": {}
                },
                "customization": {
                    "votes": {},  # Player votes for stat allocation
                    "ability_votes": {},  # Player votes for starting ability
                    "points_allocated": {
                        "hp": 0,
                        "attack": 0,
                        "defense": 0
                    },
                    "finalized": False  # Whether customization is complete
                }
            },
            "Bloom Wardens": {
                "color": discord.Color.green(),
                "emoji": "🌿",
                "channel_id": 1361313992026624224,  # Serpent channel
                "guardian": {
                    "name": "Thorne, The Floral Serpent",
                    "description": "A serpent covered in vibrant flowers, with pastel eggs growing like fruit on its leafy mane.",
                    "image": "https://i.imgur.com/thorne_image.png",
                    "base_hp": 5000000,  # Increased for week-long battles
                    "base_attack": 600,
                    "base_defense": 200,
                    "defeated": False,  # Track if guardian is defeated
                    "abilities": [
                        {"name": "Pollen Blast", "damage": 1000, "effect": "random_debuff", "chance": 0.3, "unlocked": False,
                         "description": "Releases a cloud of pollen that causes random debuffs"},
                        {"name": "Vine Entanglement", "damage": 400, "effect": "stun", "chance": 0.3, "unlocked": False,
                         "description": "Entangles enemies in vines, stunning them and dealing damage"},
                        {"name": "Bloom Burst", "damage": 1200, "effect": "aoe", "chance": 0.1, "unlocked": False,
                         "description": "Exploding flowers deal damage to all enemies"},
                        {"name": "Spring's Renewal", "damage": 0, "effect": "self_regen", "chance": 0.2, "unlocked": False,
                         "description": "Thorne rapidly regenerates, healing itself over 3 turns"},
                        {"name": "Nature's Wrath", "damage": 1600, "effect": "natures_wrath", "chance": 0.2, "unlocked": False,
                         "description": "Creates hazardous plants that damage enemies each turn and reduce their speed"},
                        {"name": "Entangling Roots", "damage": 400, "effect": "entangling_roots", "chance": 0.15, "unlocked": False,
                         "description": "Roots immobilize target for 2 turns and reduce their defense by 30%"},
                        {"name": "Regenerative Spores", "damage": 0, "effect": "regenerative_spores", "chance": 0.1, "unlocked": False,
                         "description": "Releases spores that grant Thorne a stacking regeneration buff for 3 turns"}
                    ]
                },
                "members": [],
                "eggs_collected": 0,
                "victories": 0,
                "defeats": 0,
                "upgrades": {
                    "hp_boost": 0,
                    "attack_boost": 0,
                    "defense_boost": 0,
                    "ability_votes": {}
                },
                "customization": {
                    "votes": {},  # Player votes for stat allocation
                    "ability_votes": {},  # Player votes for starting ability
                    "points_allocated": {
                        "hp": 0,
                        "attack": 0,
                        "defense": 0
                    },
                    "finalized": False  # Whether customization is complete
                }
            }
        }
        self.boss_battles = {}
        self.current_hp = {}
        self.player_hit_counters = {}  # Tracks how many times each player has been hit
        self.team_battle_cooldowns = {}
        self.player_collect_cooldowns = {}
        self.last_reset = datetime.utcnow()
        self.announcement_channel_id = 1299588921210179737
        self.total_customization_points = 30  # Total points teams can allocate

        # Placement tracking for race-to-kill
        self.placement_order = []  # List of team names in order of defeating their rival's guardian
        self.leaderboard_message_id = None  # Message ID for live leaderboard

        # New tracking systems for cooldowns
        self.player_battle_cooldowns = {}  # {player_id: datetime when cooldown expires}
        self.player_vote_cooldowns = {}  # {player_id: datetime when vote cooldown expires}
        self.team_ability_unlocked = {}  # {team_name: datetime when team can vote again}
        self.players_in_battle_formation = set()  # Set of player IDs currently forming a battle
        
    def ensure_float(self, value):
        """Ensure a value is a float, converting from Decimal if needed"""
        if hasattr(value, 'as_tuple'):  # Check if it's a Decimal
            return float(value)
        return float(value)
        
    @commands.group(invoke_without_command=True, brief=_("Easter Egg Guardian Trials"))
    @locale_doc
    async def easter(self, ctx):
        """Display information about the Easter Egg Guardian Trials event"""
        if not self.enabled:
            return await ctx.send(_("The Easter Egg Guardian Trials have not begun yet! Check back soon."))


    @easter.command(brief="Learn how the Easter Egg Guardian Trials work!")
    async def help(self, ctx):
        embed = discord.Embed(
            title="🥚 Easter Egg Guardian Trials - How To Play! 🥚",
            description=(
                "Welcome to the most egg-citing event of the year! Compete with your team, customize your guardian, and battle for glory!\n\n"
                "**Here's how it works:**"
            ),
            color=discord.Color.gold()
        )
        embed.add_field(
            name="1️⃣ Join the Event",
            value=(
                "Use `$easter join` to sign up for the event. You'll be assigned to a team when the customization phase begins."
            ),
            inline=False
        )
        embed.add_field(
            name="2️⃣ Customize Your Guardian",
            value=(
                "Once the event starts, use `$easter customize stats <hp|attack|defense> <points>` to allocate your personal stat points. "
                "Each point gives a 5% bonus to the chosen stat for your team!"
            ),
            inline=False
        )
        embed.add_field(
            name="3️⃣ Vote for Abilities",
            value=(
                "Use `$easter customize ability <ability_name>` to vote for your team's starting ability. "
                "When enough votes are gathered, the ability is unlocked!"
            ),
            inline=False
        )
        embed.add_field(
            name="4️⃣ Collect Easter Eggs",
            value=(
                "Use `$easter collect` (every 5 minutes) to find eggs for your team. "
                "Eggs are used to upgrade your guardian and unlock new abilities."
            ),
            inline=False
        )
        embed.add_field(
            name="5️⃣ Upgrade Your Guardian",
            value=(
                "Spend eggs with `$easter upgrade <hp|attack|defense>` to make your guardian stronger! Each upgrade boosts your team's stats."
            ),
            inline=False
        )
        embed.add_field(
            name="6️⃣ Battle Rival Guardians!",
            value=(
                "Use `$easter battle` to challenge other teams' guardians! Form a raid party and work together to defeat powerful foes."
            ),
            inline=False
        )
        embed.add_field(
            name="7️⃣ Victory & Leaderboards",
            value=(
                "Win battles to earn eggs and climb the leaderboard. The last team standing (or with the most victories) wins amazing rewards!"
            ),
            inline=False
        )
        embed.add_field(
            name="Other Useful Commands",
            value=(
                "- `$easter stats` — View your guardian's stats.\n"
                "- `$easter abilities` — See all guardian abilities.\n"
                "- `$easter vote` — Vote to unlock new abilities.\n"
                "- `$easter leaderboard` — Check team rankings."
            ),
            inline=False
        )
        embed.set_footer(text="Have fun and work together with your team! If you need help, use $easter help anytime.")
        await ctx.send(embed=embed)

        """Display information about the Easter Egg Guardian Trials event"""
        if not self.enabled:
            return await ctx.send(_("The Easter Egg Guardian Trials have not begun yet! Check back soon."))
        
        # Check if in customization phase
        if self.customization_phase:
            return await self.show_customization_info(ctx)
            
        player_team = self.get_player_team(ctx.author.id)
        
        if not player_team:
            embed = discord.Embed(
                title="🥚 The Great Egg Guardian Trials 🥚",
                description=_(
                    "Ancient egg guardians have awakened across the Fablelands! Three mystical creatures - "
                    "each protecting sacred eggs of tremendous power.\n\n"
                    "Choose your allegiance wisely, for you must strengthen your guardian while defeating the others.\n\n"
                    "Use `{prefix}easter join <team>` to pledge your loyalty:\n"
                    "• 🌅 **Dawn Protectors** - followers of Solara, The Radiant Hare\n"
                    "• 🌙 **Twilight Keepers** - servants of Umbra, The Shadow Drake\n"
                    "• 🌿 **Bloom Wardens** - disciples of Thorne, The Floral Serpent"
                ).format(prefix=ctx.clean_prefix),
                color=discord.Color.gold()
            )
        else:
            # Check if in team channel - if not, just provide basic info
            team_channel_id = self.teams[player_team]["channel_id"]
            
            team_data = self.teams[player_team]
            guardian = team_data["guardian"]
            
            # Calculate guardian's current stats with upgrades and customization
            current_hp = guardian["base_hp"] * (1 + (team_data["upgrades"]["hp_boost"] * 0.05) + 
                                              (team_data["customization"]["points_allocated"]["hp"] * 0.05))
            current_attack = guardian["base_attack"] * (1 + (team_data["upgrades"]["attack_boost"] * 0.05) + 
                                                     (team_data["customization"]["points_allocated"]["attack"] * 0.05))
            current_defense = guardian["base_defense"] * (1 + (team_data["upgrades"]["defense_boost"] * 0.05) + 
                                                       (team_data["customization"]["points_allocated"]["defense"] * 0.05))
            
            # For battles that are active, get the persisted HP
            persisted_hp = {}
            for battle_key, battle_data in self.boss_battles.items():
                if battle_data["defender_team"] == player_team:
                    attacker = battle_data["attacker_team"]
                    persisted_hp[attacker] = self.current_hp.get(f"{attacker}_{player_team}", current_hp)
            
            # Determine which team you battle against
            teams_list = list(self.teams.keys())
            player_index = teams_list.index(player_team)
            battle_team = teams_list[(player_index + 1) % len(teams_list)]
            
            # Check if target guardian is already defeated
            target_guardian_defeated = self.teams[battle_team]["guardian"]["defeated"]
            
            embed = discord.Embed(
                title=f"{team_data['emoji']} {player_team}",
                description=_(
                    f"You've pledged allegiance to the **{player_team}**!\n\n"
                    f"**Your Guardian:** {guardian['name']}\n"
                    f"{guardian['description']}\n\n"
                    f"**Team Eggs Collected:** {team_data['eggs_collected']}\n"
                    f"**Victories/Defeats:** {team_data['victories']}/{team_data['defeats']}\n"
                ),
                color=team_data["color"]
            )
            
            # Add mission info based on whether target guardian is defeated
            if target_guardian_defeated:
                embed.description += _(f"\n**The {battle_team}'s guardian has already been defeated!**")
            else:
                embed.description += _(f"\n**Your Mission:** Defeat the {battle_team}'s guardian!")
            
            # Guardian stats
            embed.add_field(
                name="Guardian Stats",
                value=_(
                    f"**HP:** {current_hp:,.0f}\n"
                    f"**Attack:** {current_attack:,.0f}\n"
                    f"**Defense:** {current_defense:,.0f}\n"
                    f"**Upgrades Available:** {team_data['eggs_collected'] // 100}"
                ),
                inline=True
            )
            
            # Active abilities
            active_abilities = [a["name"] for a in guardian["abilities"] if a["unlocked"]]
            embed.add_field(
                name="Active Abilities",
                value="\n".join([f"• {ability}" for ability in active_abilities]) if active_abilities else "None yet",
                inline=True
            )
            
            # Battle status
            battle_status = []
            for other_team in self.teams:
                if other_team == player_team:
                    continue
                    
                hp_key = f"{player_team}_{other_team}"
                other_guardian_hp = self.current_hp.get(hp_key, self.teams[other_team]["guardian"]["base_hp"])
                other_guardian_max_hp = self.teams[other_team]["guardian"]["base_hp"]
                
                # Check if guardian is already defeated
                if self.teams[other_team]["guardian"]["defeated"]:
                    battle_status.append(f"**{other_team}'s Guardian:** DEFEATED! 🏆")
                else:
                    battle_status.append(f"**{other_team}'s Guardian:** {other_guardian_hp:,.0f}/{other_guardian_max_hp:,.0f} HP")
            
            embed.add_field(
                name="Battle Status",
                value="\n".join(battle_status) if battle_status else "No active battles",
                inline=False
            )
            
            # Main commands and if not in team channel, add a reminder
            if ctx.channel.id != team_channel_id:
                embed.add_field(
                    name="Commands",
                    value=_(f"Please use commands in your team channel: <#{team_channel_id}>"),
                    inline=False
                )
            else:
                embed.add_field(
                    name="Commands",
                    value=_(
                        f"`{ctx.clean_prefix}easter collect` - Gather eggs for your team\n"
                        f"`{ctx.clean_prefix}easter battle` - Battle another guardian\n"
                        f"`{ctx.clean_prefix}easter upgrade` - Strengthen your guardian\n"
                        f"`{ctx.clean_prefix}easter vote` - Vote for new abilities\n"
                        f"`{ctx.clean_prefix}easter stats` - View detailed guardian stats\n"
                        f"`{ctx.clean_prefix}easter leaderboard` - View team rankings"
                    ),
                    inline=False
                )
        
        await ctx.send(embed=embed)
    
    async def show_customization_info(self, ctx):
        """Show customization phase information"""
        user_id = ctx.author.id
        if user_id not in self.per_user_stat_points:
            embed = discord.Embed(
                title="🥚 Guardian Customization Phase 🥚",
                description=_(
                    "The Easter Egg Guardian Trials are in the customization phase!\n\n"
                    "Join the event first with `{prefix}easter join`. Teams will be assigned automatically for balance."
                ).format(prefix=ctx.clean_prefix),
                color=discord.Color.gold()
            )
            return await ctx.send(embed=embed)
        player_team = self.per_user_stat_points[user_id]['team']
        team_data = self.teams[player_team]
        # Calculate points used and remaining for this user
        user_points = self.per_user_stat_points[user_id]
        user_used = user_points['allocated']
        user_max = user_points['max']
        # Team allocations
        stat_points = {"hp": 0, "attack": 0, "defense": 0}
        for uid, upoints in self.per_user_stat_points.items():
            if upoints['team'] == player_team:
                for s in stat_points:
                    stat_points[s] += upoints[s]
        # Ability votes
        ability_votes = team_data["customization"]["ability_votes"]
        ability_vote_counts = {}
        for player_id, ability_name in ability_votes.items():
            ability_vote_counts[ability_name] = ability_vote_counts.get(ability_name, 0) + 1
        top_ability = max(ability_vote_counts.items(), key=lambda x: x[1])[0] if ability_vote_counts else "None selected"
        embed = discord.Embed(
            title=f"🥚 Guardian Customization - {player_team} 🥚",
            description=_(
                f"Help customize your team's guardian before the battles begin!\n\n"
                f"You have **{user_max - user_used}** points remaining to allocate. Each point gives a 5% boost to the chosen stat for the team.\n\n"
                f"Current team allocation (sum of all members):\n"
                f"**HP:** {stat_points['hp']} points (+{stat_points['hp']*5}%)\n"
                f"**Attack:** {stat_points['attack']} points (+{stat_points['attack']*5}%)\n"
                f"**Defense:** {stat_points['defense']} points (+{stat_points['defense']*5}%)\n"
                f"**Leading Ability Choice:** {top_ability}"
            ),
            color=team_data["color"]
        )
        embed.add_field(
            name="Your Allocation",
            value=_(
                f"HP: {user_points['hp']}\nAttack: {user_points['attack']}\nDefense: {user_points['defense']}\nPoints used: {user_used} / {user_max}"
            ),
            inline=False
        )
        embed.add_field(
            name="Customization Commands",
            value=_(
                f"`{ctx.clean_prefix}easter customize stats <hp|attack|defense> <points>` - Allocate your points\n"
                f"`{ctx.clean_prefix}easter customize ability <ability_name>` - Vote for starting ability\n"
                f"`{ctx.clean_prefix}easter abilities` - View all available abilities"
            ),
            inline=False
        )
        await ctx.send(embed=embed)

    @has_char()
    @easter.command(brief=_("Join the Easter event"))
    @locale_doc
    async def join(self, ctx):
        """Join the Easter Egg Guardian Trials event. Teams are assigned automatically for balance."""
        if ctx.guild.id != 1199287508794626078:
            return await ctx.send(_("This command can only be used in the official server."))
        if not self.enabled:
            return await ctx.send(_("The Easter Egg Guardian Trials have not begun yet! Check back soon."))
        if ctx.author.id in self.pending_participants or self.get_player_team(ctx.author.id):
            return await ctx.send(_("You've already joined the event!"))
        self.pending_participants.append(ctx.author.id)
        await ctx.send(embed=discord.Embed(
            title="You have joined the Easter Egg Guardian Trials!",
            description="Teams will be assigned automatically for balance when customization begins.",
            color=discord.Color.gold()
        ))
    
    @has_char()
    @easter.command(brief=_("View all guardian abilities"))
    @locale_doc
    async def abilities(self, ctx, *, guardian_name: str = None):
        """View the abilities of any guardian
        
        You can specify a guardian by name, or leave blank to see your team's guardian."""
        if not self.enabled:
            return await ctx.send(_("The Easter Egg Guardian Trials have not begun yet! Check back soon."))
            
        player_team = self.get_player_team(ctx.author.id)
        if not player_team and not guardian_name:
            return await ctx.send(_("You need to join a team first with `{prefix}easter join` or specify a guardian name").format(prefix=ctx.clean_prefix))
        
        # If no guardian name specified, check if in team channel
        if not guardian_name and player_team:
            team_channel_id = self.teams[player_team]["channel_id"]
            if ctx.channel.id != team_channel_id:
                return await ctx.send(_(f"Please use this command in your team's channel: <#{team_channel_id}>"))
            
        # Determine which guardian to show
        target_team = None
        if guardian_name:
            for team_name, team_data in self.teams.items():
                guardian = team_data["guardian"]["name"]
                if guardian_name.lower() in guardian.lower() or guardian_name.lower() in team_name.lower():
                    target_team = team_name
                    break
                
            if not target_team:
                return await ctx.send(_("Guardian not found. Available guardians: Solara, Umbra, Thorne"))
        else:
            target_team = player_team
            
        team_data = self.teams[target_team]
        guardian = team_data["guardian"]
        
        embed = discord.Embed(
            title=f"{team_data['emoji']} {guardian['name']}'s Abilities",
            description=_(f"These are all the potential abilities for {guardian['name']}:"),
            color=team_data["color"]
        )
        
        # List all abilities with detailed descriptions
        for i, ability in enumerate(guardian["abilities"]):
            status = "✅ Unlocked" if ability["unlocked"] else "🔒 Locked"
            embed.add_field(
                name=f"{i+1}. {ability['name']} ({status})",
                value=_(
                    f"**Description:** {ability['description']}\n"
                    f"**Damage:** {ability['damage']}\n"
                    f"**Chance to Activate:** {ability['chance']*100:.0f}%"
                ),
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @has_char()
    @easter.command(brief=_("Customize your guardian stats before the event"))
    @locale_doc
    async def customize(self, ctx, option: str = None, stat: str = None, value: int = None):
        # Restrict by phase
        if self.join_phase:
            return await ctx.send("The event is currently in the join phase. Customization will begin soon!")
        if not self.customization_phase:
            return await ctx.send("The customization phase is not active.")
        """Customize your guardian stats before the Easter event begins
        
        Options:
        - stats <hp|attack|defense> <points> - Allocate your personal stat points
        - ability <ability_name> - Vote for a starting ability (team-wide)
        
        Each user gets a share of points to distribute, with each point giving +5% to the chosen stat for the team."""
        if not self.enabled:
            return await ctx.send(_("The Easter Egg Guardian Trials have not begun yet! Check back soon."))
        if not self.customization_phase:
            return await ctx.send(_("The customization phase has ended. The Easter Egg Guardian Trials have already begun!"))
        user_id = ctx.author.id
        if user_id not in self.per_user_stat_points:
            return await ctx.send(_("You need to join the event with `{prefix}easter join` and wait for team assignment.").format(prefix=ctx.clean_prefix))
        player_team = self.per_user_stat_points[user_id]['team']
        team_data = self.teams[player_team]
        # Enforce team channel usage
        team_channel_id = self.teams[player_team]["channel_id"]
        if ctx.channel.id != team_channel_id:
            return await ctx.send(_(f"Please use this command in your team's channel: <#{team_channel_id}>"))
        # If customization is already finalized for this team
        if team_data["customization"]["finalized"]:
            return await ctx.send(_("Your team has already finalized their guardian customization!"))
        # Without arguments, show current customization
        if not option:
            return await self.show_customization_info(ctx)
        if option.lower() == "stats":
            if not stat or value is None:
                return await ctx.send(_("Please specify a stat (hp, attack, defense) and the number of points to allocate."))
            valid_stats = ["hp", "attack", "defense"]
            if stat.lower() not in valid_stats:
                return await ctx.send(_("Valid stats are: hp, attack, defense"))
            user_points = self.per_user_stat_points[user_id]
            if value <= 0:
                return await ctx.send(_("You must allocate at least 1 point."))
            if user_points['allocated'] + value > user_points['max']:
                return await ctx.send(_(
                    f"You only have {user_points['max'] - user_points['allocated']} points remaining to allocate."
                ))
            # Allocate the points
            user_points[stat.lower()] += value
            user_points['allocated'] += value
            # Update team stat allocation by summing all users in team
            stat_points = {"hp": 0, "attack": 0, "defense": 0}
            for uid, upoints in self.per_user_stat_points.items():
                if upoints['team'] == player_team:
                    for s in stat_points:
                        stat_points[s] += upoints[s]
            team_data["customization"]["points_allocated"] = stat_points
            current_hp = stat_points["hp"]
            current_attack = stat_points["attack"]
            current_defense = stat_points["defense"]
            total_used = current_hp + current_attack + current_defense
            embed = discord.Embed(
                title="Your Stat Allocation",
                description=_(
                    f"You allocated **{value}** points to **{stat.lower()}**.\n\n"
                    f"Your allocation: HP {user_points['hp']}, ATK {user_points['attack']}, DEF {user_points['defense']} (of {user_points['max']} total)\n\n"
                    f"Current team allocation (sum of all members):\n"
                    f"**HP:** {current_hp} points (+{current_hp*5}%)\n"
                    f"**Attack:** {current_attack} points (+{current_attack*5}%)\n"
                    f"**Defense:** {current_defense} points (+{current_defense*5}%)\n\n"
                    f"**Points used:** {total_used}"
                ),
                color=team_data["color"]
            )
            await ctx.send(embed=embed)
            # Post update in team channel
            try:
                team_channel = self.bot.get_channel(team_data["channel_id"])
                if team_channel:
                    update_embed = discord.Embed(
                        title="Guardian Customization Update",
                        description=_(
                            f"{ctx.author.mention} allocated **{value}** points to **{stat.lower()}**.\n\n"
                            f"Current allocation:\n"
                            f"**HP:** {current_hp} points (+{current_hp*5}%)\n"
                            f"**Attack:** {current_attack} points (+{current_attack*5}%)\n"
                            f"**Defense:** {current_defense} points (+{current_defense*5}%)\n"
                        ),
                        color=team_data["color"]
                    )
                    await team_channel.send(embed=update_embed)
            except Exception as e:
                channel2 = self.bot.get_channel(1362758651047182578)
                await channel2.send(f"Error updating leaderboard embed: {e}")
        elif option.lower() == "ability":
            if not stat:  # Using 'stat' parameter as the ability name
                return await ctx.send(_("Please specify an ability name to vote for."))
                
            # Find the ability
            ability_found = False
            for ability in team_data["guardian"]["abilities"]:
                if stat.lower() in ability["name"].lower():
                    ability_found = True
                    ability_name = ability["name"]
                    break
                    
            if not ability_found:
                return await ctx.send(_("Ability not found. Use `{prefix}easter abilities` to see all options.").format(prefix=ctx.clean_prefix))
                
            # Prevent multiple votes per user during the setup phase
            if ctx.author.id in team_data["customization"]["ability_votes"]:
                return await ctx.send(_("You have already voted for an ability during this phase and cannot change your vote."))
            team_data["customization"]["ability_votes"][ctx.author.id] = ability_name
            
            # Count votes for each ability
            ability_vote_counts = {}
            for player_id, voted_ability in team_data["customization"]["ability_votes"].items():
                ability_vote_counts[voted_ability] = ability_vote_counts.get(voted_ability, 0) + 1
                
            # Determine the current winner
            if ability_vote_counts:
                top_ability = max(ability_vote_counts.items(), key=lambda x: x[1])
                top_name = top_ability[0]
                top_votes = top_ability[1]
            else:
                top_name = "None"
                top_votes = 0
            
            embed = discord.Embed(
                title="Guardian Ability Vote",
                description=_(
                    f"You've voted for the ability **{ability_name}**.\n\n"
                    f"Current leading ability: **{top_name}** with {top_votes} votes."
                ),
                color=team_data["color"]
            )
            
            await ctx.send(embed=embed)
            
            # Post update in team channel
            try:
                team_channel = self.bot.get_channel(team_data["channel_id"])
                if team_channel:
                    update_embed = discord.Embed(
                        title="Guardian Ability Vote Update",
                        description=_(
                            f"{ctx.author.mention} voted for the ability **{ability_name}**.\n\n"
                            f"Current votes:\n"
                        ),
                        color=team_data["color"]
                    )
                    
                    # Add all abilities with vote counts
                    ability_list = ""
                    for ability_name, count in ability_vote_counts.items():
                        ability_list += f"**{ability_name}**: {count} votes\n"
                        
                    update_embed.description += ability_list
                    await team_channel.send(embed=update_embed)
            except Exception as e:
                channel2 = self.bot.get_channel(1362758651047182578)
                await channel2.send(f"Error updating leaderboard embed: {e}")
        else:
            await ctx.send(_("Invalid option. Use `stats` to allocate stat points or `ability` to vote for a starting ability."))
    
    def calculate_team_stat_allocation(self, team_name):
        # Deprecated: per-user stat allocation now used
        pass
    
    @is_gm()
    @easter.command(hidden=True)
    async def start_join_phase(self, ctx):
        """Start the join phase (GM only)"""
        self.enabled = True
        self.join_phase = True
        self.customization_phase = False
        self.event_active = False
        self.pending_participants.clear()
        for team_name in self.teams:
            self.teams[team_name]["members"] = []
        await ctx.send("Join phase has begun! Players can now join teams.")
        # Announce in the announcement channel
        try:
            announcement_channel = self.bot.get_channel(self.announcement_channel_id)
            if announcement_channel:
                embed = discord.Embed(
                    title="🥚 Easter Egg Guardian Trials: Join Phase 🥚",
                    description=(
                        "The join phase has begun! Use `$easter join` to join the event. Teams will be assigned automatically for balance.\n\n"
                        "Once all players have joined, the GM will begin the customization phase."
                    ),
                    color=discord.Color.gold()
                )
                await announcement_channel.send("@everyone", embed=embed)
        except Exception as e:
            channel2 = self.bot.get_channel(1362758651047182578)
            await channel2.send(f"Error updating leaderboard embed: {e}")

    @is_gm()
    @easter.command(hidden=True)
    async def setup_customization(self, ctx):
        """Start the guardian customization phase (GM only). Assigns all players to teams for balance."""
        if not self.join_phase:
            return await ctx.send("You must start the join phase first with `$easter start_join_phase`.")
        self.customization_phase = True
        self.join_phase = False
        self.event_active = False

        # --- ASSIGN PARTICIPANTS TO TEAMS FOR BALANCE ---
        all_participants = self.pending_participants.copy()
        random.shuffle(all_participants)
        team_names = list(self.teams.keys())
        team_count = len(team_names)
        for team_name in self.teams:
            self.teams[team_name]["members"] = []  # Reset members
        # Assign participants to teams for balance
        team_members = {team: [] for team in team_names}
        for i, user_id in enumerate(all_participants):
            team = team_names[i % team_count]
            team_members[team].append(user_id)
            self.teams[team]["members"].append(user_id)
        # Stat allocation per team
        total_points = getattr(self, 'total_customization_points', 30)
        for team, members in team_members.items():
            n = len(members)
            if n == 0:
                continue
            base = total_points // n
            remainder = total_points % n
            extra_points_receivers = random.sample(members, remainder) if remainder > 0 else []
            for user_id in members:
                max_points = base + (1 if user_id in extra_points_receivers else 0)
                self.per_user_stat_points[user_id] = {"team": team, "hp": 0, "attack": 0, "defense": 0, "allocated": 0, "max": max_points}
                # DM the user their team assignment and grant channel access
                user = self.bot.get_user(user_id)
                if user:
                    try:
                        await user.send(f"You have been assigned to the **{team}** team in the Easter Egg Guardian Trials!")
                        await asyncio.sleep(0.7)
                    except Exception as e:
                        print(f"Could not DM user {user_id}: {e}")
                # Grant view access to the team channel (only their own)
                guild = ctx.guild
                channel_id = self.teams[team]["channel_id"]
                try:
                    await grant_team_channel_access(self.bot, guild, user_id, channel_id)
                    await asyncio.sleep(0.7)
                except Exception as e:
                    print(f"Could not grant channel access to user {user_id}: {e}")
            await asyncio.sleep(1)
        self.pending_participants.clear()

        # Reset any previous customization data
        for team_name in self.teams:
            self.teams[team_name]["customization"]["votes"] = {}
            self.teams[team_name]["customization"]["ability_votes"] = {}
            self.teams[team_name]["customization"]["points_allocated"] = {"hp": 0, "attack": 0, "defense": 0}
            self.teams[team_name]["customization"]["finalized"] = False
        
        await ctx.send("Customization phase has begun! Players have been assigned to teams and can now vote on guardian customization.")
        # Announce in the announcement channel
        try:
            announcement_channel = self.bot.get_channel(self.announcement_channel_id)
            if announcement_channel:
                embed = discord.Embed(
                    title="🥚 Easter Egg Guardian Trials: Customization Phase 🥚",
                    description=(
                        "The customization phase has begun!\n\n"
                        "Players can now allocate stat points and vote for abilities for their team's guardian.\n\n"
                        "Use `$easter customize` to participate!"
                    ),
                    color=discord.Color.gold()
                )
                await announcement_channel.send("@everyone", embed=embed)
        except Exception as e:
            print(f"Error sending customization phase announcement: {e}")
        
        # Announce in all team channels
        for team_name, team_data in self.teams.items():
            try:
                channel = self.bot.get_channel(team_data["channel_id"])
                if channel:
                    embed = discord.Embed(
                        title="🥚 Guardian Customization Phase Has Begun! 🥚",
                        description=_(
                            f"The Easter Egg Guardian Trials customization phase has begun!\n\n"
                            f"Your team has **{self.total_customization_points}** points to allocate to your guardian's stats.\n"
                            f"Each point provides a 5% boost to the stat.\n\n"
                            f"You can also vote for your starting ability.\n\n"
                            f"Use `{ctx.clean_prefix}easter customize` to participate!"
                        ),
                        color=team_data["color"]
                    )
                    await channel.send("@everyone", embed=embed)
            except Exception as e:
                print(f"Error sending announcement to team {team_name}: {e}")
    
    @is_gm()
    @easter.command(hidden=True)
    async def finalize_customization(self, ctx, team_name: str = None):
        """Finalize all teams' guardian customization (GM only). Locks in all votes and allocations."""
        if not self.customization_phase:
            return await ctx.send("The customization phase is not active.")
        self.event_active = True  # Main event starts after customization

        # Finalize all teams
        for team_name in self.teams:
            await self.finalize_team_customization(ctx, team_name)
        self.customization_phase = False
        self.join_phase = False
        await ctx.send("All team customizations have been finalized. The main event is now beginning!")

        # Announce in the announcement channel
        try:
            announcement_channel = self.bot.get_channel(self.announcement_channel_id)
            if announcement_channel:
                # Build team matchups
                teams_list = list(self.teams.keys())
                matchups = "\n".join([
                    f"🥚 **{teams_list[i]}**  ➡️  **{teams_list[(i+1)%len(teams_list)]}**'s Guardian"
                    for i in range(len(teams_list))
                ])
                embed = discord.Embed(
                    title="🥚 Easter Egg Guardian Trials: Main Event Started! 🥚",
                    description=(
                        "All guardians have been customized and the battle phase has begun!\n\n"
                        "Start collecting eggs for your team with `$easter collect` and challenge other guardians with `$easter battle`!\n\n"
                        f"__**Team Matchups:**__\n{matchups}"
                    ),
                    color=discord.Color.gold()
                )
                await announcement_channel.send("@everyone", embed=embed)
        except Exception as e:
            print(f"Error sending main event announcement: {e}")

        # Announce in all team channels
        announcement_embed = discord.Embed(
            title="🥚 The Easter Egg Guardian Trials Have Begun! 🥚",
            description=_(
                "All guardians have been customized and the battle phase has begun!\n\n"
                "Start collecting eggs for your team with `$easter collect` and prepare for with `$easter battle`!"
            ),
            color=discord.Color.gold()
        )
        for team_name, team_data in self.teams.items():
            guardian = team_data["guardian"]
            unlocked_ability = "None"
            for ability in guardian["abilities"]:
                if ability["unlocked"]:
                    unlocked_ability = ability["name"]
                    break
            announcement_embed.add_field(
                name=f"{team_data['emoji']} {team_name} - {guardian['name']}",
                value=_(
                    f"**HP:** +{team_data['customization']['points_allocated']['hp']*5}%\n"
                    f"**Attack:** +{team_data['customization']['points_allocated']['attack']*5}%\n"
                    f"**Defense:** +{team_data['customization']['points_allocated']['defense']*5}%\n"
                    f"**Starting Ability:** {unlocked_ability}"
                ),
                inline=True
            )
        try:
            await asyncio.sleep(3)
            for team_name, team_data in self.teams.items():
                channel = self.bot.get_channel(team_data["channel_id"])
                if channel:
                    
                    await channel.send(embed=announcement_embed)
        except Exception as e:
            print(f"Error sending final announcement: {e}")
        try:
            announcement_channel = self.bot.get_channel(self.announcement_channel_id)
            if announcement_channel:
                await announcement_channel.send(embed=announcement_embed)
        except Exception as e:
            print(f"Error sending announcement: {e}")

        # Post the live leaderboard embed after customization is finalized
        await self.update_leaderboard_embed(ctx.guild)

    
    async def finalize_team_customization(self, ctx, team_name):
        """Finalize customization for a specific team"""
        team_data = self.teams[team_name]
        
        # Calculate final stat allocations
        self.calculate_team_stat_allocation(team_name)
        
        # Determine most voted ability
        ability_votes = team_data["customization"]["ability_votes"]
        ability_vote_counts = {}
        
        for player_id, ability_name in ability_votes.items():
            ability_vote_counts[ability_name] = ability_vote_counts.get(ability_name, 0) + 1
            
        # Unlock the winning ability
        if ability_vote_counts:
            top_ability = max(ability_vote_counts.items(), key=lambda x: x[1])[0]
            
            for ability in team_data["guardian"]["abilities"]:
                if ability["name"] == top_ability:
                    ability["unlocked"] = True
                    break
        else:
            # If no votes, unlock the first ability
            team_data["guardian"]["abilities"][0]["unlocked"] = True
            top_ability = team_data["guardian"]["abilities"][0]["name"]
        
        # Mark as finalized
        team_data["customization"]["finalized"] = True
        
        # Create result embed
        hp_points = team_data["customization"]["points_allocated"]["hp"]
        attack_points = team_data["customization"]["points_allocated"]["attack"]
        defense_points = team_data["customization"]["points_allocated"]["defense"]
        
        embed = discord.Embed(
            title=f"{team_name} Guardian Customization Finalized",
            description=_(
                f"The {team_name}'s guardian has been customized with:\n\n"
                f"**HP:** {hp_points} points (+{hp_points*5}%)\n"
                f"**Attack:** {attack_points} points (+{attack_points*5}%)\n"
                f"**Defense:** {defense_points} points (+{defense_points*5}%)\n\n"
                f"**Starting Ability:** {top_ability}"
            ),
            color=team_data["color"]
        )
        
        await ctx.send(embed=embed)
        
        # Also post in team channel
        try:
            team_channel = self.bot.get_channel(team_data["channel_id"])
            if team_channel:
                team_embed = discord.Embed(
                    title="Guardian Customization Complete!",
                    description=_(
                        f"Your guardian customization has been finalized!\n\n"
                        f"**Final Stats:**\n"
                        f"**HP:** +{hp_points*5}% (Base: {team_data['guardian']['base_hp']:,})\n"
                        f"**Attack:** +{attack_points*5}% (Base: {team_data['guardian']['base_attack']:,})\n"
                        f"**Defense:** +{defense_points*5}% (Base: {team_data['guardian']['base_defense']:,})\n\n"
                        f"**Starting Ability:** {top_ability}\n\n"
                    "Start collecting eggs for your team with `$easter collect` and challenge other guardians with `$easter battle`!"
                    ),
                    color=team_data["color"]
                )
                await team_channel.send("@everyone", embed=team_embed)
            await asyncio.sleep(2)
        except Exception as e:
            print(f"Could not send team channel finalization message: {e}")
            
    @has_char()
    @easter.command(brief=_("Collect Easter eggs for your team"))
    @user_cooldown(7200)
    @locale_doc
    async def collect(self, ctx):
        # Restrict by phase
        if self.join_phase:
            return await ctx.send("The event is currently in the join phase. Egg collection will begin after customization!")
        if self.customization_phase:
            return await ctx.send("The Easter event is still in the customization phase. Egg collection will begin once guardians are finalized!")
        """Venture into the Fablelands to collect Easter eggs for your team
        
        Eggs are used to upgrade your guardian and unlock new abilities.
        This command has a 5 minute cooldown."""
        if not self.enabled:
            return await ctx.send(_("The Easter Egg Guardian Trials have not begun yet! Check back soon."))
            
        if self.customization_phase:
            return await ctx.send(_("The Easter event is still in the customization phase. Egg collection will begin once guardians are finalized!"))
        
        player_team = self.get_player_team(ctx.author.id)
        if not player_team:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(_("You need to join a team first with `{prefix}easter join`." ).format(prefix=ctx.clean_prefix))
        
        # Determine which team this player battles against
        teams_list = list(self.teams.keys())
        player_index = teams_list.index(player_team)
        defender_team = teams_list[(player_index + 1) % len(teams_list)]
        # Check if your team is already attacking


        
        # Check if in team channel
        team_channel_id = self.teams[player_team]["channel_id"]
        if ctx.channel.id != team_channel_id:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send(_(f"Please use this command in your team's channel: <#{team_channel_id}>"))
        
        # Set up the egg hunting "game"
        locations = [
            {"name": "Whisperwood Forest", "emoji": "🌲", "min": 5, "max": 15, "special_chance": 0.1},
            {"name": "Misty Meadows", "emoji": "🌫️", "min": 10, "max": 20, "special_chance": 0.05},
            {"name": "Crystal Caverns", "emoji": "💎", "min": 15, "max": 25, "special_chance": 0.2}
        ]
        
        embed = discord.Embed(
            title="🥚 Egg Hunt 🥚",
            description=_(
                "Where would you like to search for eggs? Each location offers different rewards:\n\n"
                "1. 🌲 **Whisperwood Forest** - Safest option with moderate eggs\n"
                "2. 🌫️ **Misty Meadows** - Balanced risk with decent rewards\n"
                "3. 💎 **Crystal Caverns** - Dangerous but potentially more rewarding"
            ),
            color=self.teams[player_team]["color"]
        )
        
        message = await ctx.send(embed=embed)
        for i in range(len(locations)):
            await message.add_reaction(f"{i+1}\u20e3")
        
        def check(reaction, user):
            return (
                user == ctx.author and 
                reaction.message.id == message.id and
                str(reaction.emoji) in [f"{i+1}\u20e3" for i in range(len(locations))]
            )
        
        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
            selected_index = int(str(reaction.emoji)[0]) - 1
            selected_location = locations[selected_index]
            
            # Determine base eggs found
            eggs_found = random.randint(selected_location["min"], selected_location["max"])
            
            # Check for special events
            special_event = random.random() < selected_location["special_chance"]
            event_message = ""
            
            if special_event:
                events = [
                    {"name": "Egg Thief", "emoji": "🦊", "outcome": "negative", "effect": random.randint(-10, -1)},
                    {"name": "Guardian's Blessing", "emoji": "✨", "outcome": "positive", "effect": random.randint(10, 20)},
                    {"name": "Golden Egg", "emoji": "🌟", "outcome": "positive", "effect": random.randint(20, 50)}
                ]
                
                selected_event = random.choice(events)
                
                if selected_event["outcome"] == "positive":
                    eggs_found += selected_event["effect"]
                    event_message = f"\n\n{selected_event['emoji']} You encountered a **{selected_event['name']}** and gained an extra **{selected_event['effect']}** eggs!"
                else:
                    eggs_found += selected_event["effect"]
                    eggs_found = max(1, eggs_found)  # Ensure at least 1 egg found
                    event_message = f"\n\n{selected_event['emoji']} You encountered a **{selected_event['name']}** and lost **{abs(selected_event['effect'])}** eggs!"
            
            # Add eggs to team total
            self.teams[player_team]["eggs_collected"] += eggs_found
            
            result_embed = discord.Embed(
                title=f"🥚 Egg Hunt Results - {selected_location['name']} {selected_location['emoji']}",
                description=_(
                    f"You searched {selected_location['name']} and found **{eggs_found}** Easter eggs!{event_message}\n\n"
                    f"Your team now has **{self.teams[player_team]['eggs_collected']}** eggs in total.\n"
                    f"That's enough for **{self.teams[player_team]['eggs_collected'] // 100}** upgrades!"
                ),
                color=self.teams[player_team]["color"]
            )
            
            await message.edit(embed=result_embed)
            
            # Post update in team channel
            try:
                team_channel = self.bot.get_channel(self.teams[player_team]["channel_id"])
                if team_channel:
                    channel_update = discord.Embed(
                        title="Egg Collection Update",
                        description=_(
                            f"{ctx.author.mention} collected **{eggs_found}** eggs!\n"
                            f"Team total is now **{self.teams[player_team]['eggs_collected']}** eggs."
                        ),
                        color=self.teams[player_team]["color"]
                    )
                    await team_channel.send(embed=channel_update)
            except Exception as e:
                print(f"Error sending team channel update: {e}")
            
        except asyncio.TimeoutError:
            await message.edit(content=_("You took too long to choose a location. The eggs remain hidden!"))
            await self.bot.reset_cooldown(ctx)

    @has_char()
    @easter.command(brief=_("View detailed guardian stats"))
    @locale_doc
    async def stats(self, ctx, *, guardian_name: str = None):
        """View detailed stats for any guardian
        
        You can specify a guardian by name, or leave blank to see your team's guardian."""
        if not self.enabled:
            return await ctx.send(_("The Easter Egg Guardian Trials have not begun yet! Check back soon."))
            
        player_team = self.get_player_team(ctx.author.id)
        if not player_team and not guardian_name:
            return await ctx.send(_("You need to join a team first with `{prefix}easter join <team>` or specify a guardian name").format(prefix=ctx.clean_prefix))
        # Enforce team channel usage for stats if not specifying other guardian
        if not guardian_name and player_team:
            team_channel_id = self.teams[player_team]["channel_id"]
            if ctx.channel.id != team_channel_id:
                return await ctx.send(_(f"Please use this command in your team's channel: <#{team_channel_id}>"))
        
        # Determine which guardian to show
        target_team = None
        if guardian_name:
            for team_name, team_data in self.teams.items():
                guardian = team_data["guardian"]["name"]
                if guardian_name.lower() in guardian.lower() or guardian_name.lower() in team_name.lower():
                    target_team = team_name
                    break
                
            if not target_team:
                return await ctx.send(_("Guardian not found. Available guardians: Solara, Umbra, Thorne"))
        else:
            target_team = player_team
            
        team_data = self.teams[target_team]
        guardian = team_data["guardian"]
        
        # Calculate current stats with upgrades and customization
        current_hp = guardian["base_hp"] * (1 + (team_data["upgrades"]["hp_boost"] * 0.05) + 
                                          (team_data["customization"]["points_allocated"]["hp"] * 0.05))
        current_attack = guardian["base_attack"] * (1 + (team_data["upgrades"]["attack_boost"] * 0.05) + 
                                                 (team_data["customization"]["points_allocated"]["attack"] * 0.05))
        current_defense = guardian["base_defense"] * (1 + (team_data["upgrades"]["defense_boost"] * 0.05) + 
                                                   (team_data["customization"]["points_allocated"]["defense"] * 0.05))
        
        # Create the embed
        embed = discord.Embed(
            title=f"{team_data['emoji']} {guardian['name']} ({target_team})",
            description=guardian["description"],
            color=team_data["color"]
        )
        
        # Add status (defeated or not)
        status = "DEFEATED" if guardian["defeated"] else "ACTIVE"
        embed.add_field(name="Status", value=status, inline=False)
        
        # Add stats with breakdown
        embed.add_field(
            name="Stats",
            value=_(
                f"**Base HP:** {guardian['base_hp']:,.0f}\n"
                f"• +{team_data['customization']['points_allocated']['hp']*10}% (Customization)\n"
                f"• +{team_data['upgrades']['hp_boost']*5}% (Upgrades)\n"
                f"• **Current:** {current_hp:,.0f} HP\n\n"
                f"**Base Attack:** {guardian['base_attack']:,.0f}\n"
                f"• +{team_data['customization']['points_allocated']['attack']*10}% (Customization)\n"
                f"• +{team_data['upgrades']['attack_boost']*5}% (Upgrades)\n"
                f"• **Current:** {current_attack:,.0f} Attack\n\n"
                f"**Base Defense:** {guardian['base_defense']:,.0f}\n"
                f"• +{team_data['customization']['points_allocated']['defense']*10}% (Customization)\n"
                f"• +{team_data['upgrades']['defense_boost']*5}% (Upgrades)\n"
                f"• **Current:** {current_defense:,.0f} Defense"
            ),
            inline=False
        )
        
        # Unlocked abilities
        unlocked = [ability for ability in guardian["abilities"] if ability["unlocked"]]
        unlock_text = ""
        for ability in unlocked:
            unlock_text += f"• **{ability['name']}** - {ability['description']}\n"
            
        embed.add_field(
            name=f"Unlocked Abilities ({len(unlocked)}/{len(guardian['abilities'])})",
            value=unlock_text if unlock_text else "No abilities unlocked yet",
            inline=False
        )
        
        # Locked abilities
        locked = [ability for ability in guardian["abilities"] if not ability["unlocked"]]
        locked_text = ""
        for ability in locked:
            vote_count = team_data["upgrades"]["ability_votes"].get(ability["name"], 0)
            locked_text += f"• **{ability['name']}** - {vote_count}/5 votes\n"
            
        if locked:
            embed.add_field(
                name="Locked Abilities",
                value=locked_text,
                inline=False
            )
            
        # Add battle record
        embed.add_field(
            name="Battle Record",
            value=_(
                f"**Victories:** {team_data['victories']}\n"
                f"**Defeats:** {team_data['defeats']}\n"
                f"**Team Members:** {len(team_data['members'])}\n"
                f"**Eggs Collected:** {team_data['eggs_collected']}"
            ),
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    @has_char()
    @easter.command(brief=_("Battle another team's guardian"))
    @user_cooldown(3600)
    @locale_doc
    async def battle(self, ctx):
        """Challenge another team's guardian to battle

        Your team will face the guardian of the next team in rotation.
        This command has a 1 hour cooldown."""
        try:
            if not self.enabled:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_("The Easter Egg Guardian Trials have not begun yet! Check back soon."))

            if self.customization_phase:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_("The Easter event is still in the customization phase. Battles will begin once guardians are finalized!"))

            player_team = self.get_player_team(ctx.author.id)
            if not player_team:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_("You need to join a team first with `{prefix}easter join`." ).format(prefix=ctx.clean_prefix))


            # Check if in team channel
            team_channel_id = self.teams[player_team]["channel_id"]
            if ctx.channel.id != team_channel_id:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_(f"Please use this command in your team's channel: <#{team_channel_id}>"))

            # Check if player is already in a battle formation
            if ctx.author.id in self.players_in_battle_formation:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_("You are already forming or participating in a battle!"))

            # Check if player is on battle cooldown
            if ctx.author.id in self.player_battle_cooldowns:
                if datetime.utcnow() < self.player_battle_cooldowns[ctx.author.id]:
                    time_left = self.player_battle_cooldowns[ctx.author.id] - datetime.utcnow()
                    hours, remainder = divmod(time_left.total_seconds(), 3600)
                    minutes, seconds = divmod(remainder, 60)
                    await self.bot.reset_cooldown(ctx)
                    return await ctx.send(_(
                        f"You're still exhausted from your last battle! "
                        f"You can battle again in **{int(hours)}h {int(minutes)}m**."
                    ))


            # Determine which team this player battles against
            teams_list = list(self.teams.keys())
            player_index = teams_list.index(player_team)
            defender_team = teams_list[(player_index + 1) % len(teams_list)]
            # Check if your team is already attacking
            if player_team in self.ongoing_team_battles:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_(
                    f"A battle is already ongoing for your team as the attacker. Please wait for your current battle to finish before starting another."
                ))


            # Determine which team this player battles against
            teams_list = list(self.teams.keys())
            player_index = teams_list.index(player_team)
            defender_team = teams_list[(player_index + 1) % len(teams_list)]

            # Check if defender guardian is already defeated
            if self.teams[defender_team]["guardian"]["defeated"]:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_(
                    f"The {defender_team}'s guardian has already been defeated! Their team is out of the competition."
                ))

            # Check team cooldown
            cooldown_key = f"{player_team}_{defender_team}"
            if cooldown_key in self.team_battle_cooldowns:
                if datetime.utcnow() < self.team_battle_cooldowns[cooldown_key]:
                    time_left = self.team_battle_cooldowns[cooldown_key] - datetime.utcnow()
                    minutes_left = int(time_left.total_seconds() / 60)
                    await self.bot.reset_cooldown(ctx)
                    return await ctx.send(_(
                        f"Your team is still recovering from the last battle against the {defender_team}. "
                        f"Try again in **{minutes_left}** minutes."
                    ))
            self.ongoing_team_battles.add(player_team)

            # Add player to battle formation tracking
            self.players_in_battle_formation.add(ctx.author.id)

            # Form a raid party
            embed = discord.Embed(
                title=f"⚔️ Guardian Battle: {player_team} vs {defender_team} ⚔️",
                description=_(
                    f"**{ctx.author.display_name}** is forming a raid party to battle **{self.teams[defender_team]['guardian']['name']}**!\n\n"
                    f"Click ✅ to join the battle! (1-10 members)\n\n"
                    f"**WARNING:** All participants will be on a 4-hour cooldown after the battle."
                ),
                color=self.teams[player_team]["color"]
            )

            embed.add_field(name="Party Members", value=f"1. {ctx.author.mention}", inline=False)

            view = JoinBattleView(ctx, embed, [ctx.author], self, player_team, defender_team)
            message = await ctx.send(embed=embed)
            view.message = message
            await message.edit(view=view)

            # Post battle formation in team channel
            try:
                team_channel = self.bot.get_channel(self.teams[player_team]["channel_id"])
                if team_channel:
                    team_embed = discord.Embed(
                        title="Guardian Battle Formation",
                        description=_(
                            f"{ctx.author.mention} is forming a raid party to battle the {defender_team}'s guardian!\n\n"
                            f"Use the ✅ button on the message above to join!"
                        ),
                        color=self.teams[player_team]["color"]
                    )
                    await team_channel.send(embed=team_embed)
            except Exception as e:
                print(f"Error sending team battle formation message: {e}")
        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n"
            error_message += traceback.format_exc()
            await ctx.send(error_message)
    
    @has_char()
    @easter.command(brief=_("Upgrade your team's guardian"))
    @locale_doc
    async def upgrade(self, ctx, upgrade_type: str = None):
        """Upgrade your team's guardian with collected eggs
        
        Available upgrade types:
        - hp: Increase your guardian's health
        - attack: Increase your guardian's attack power
        - defense: Increase your guardian's defense
        
        Upgrades cost 100 eggs each."""
        if not self.enabled:
            return await ctx.send(_("The Easter Egg Guardian Trials have not begun yet! Check back soon."))
            
        if self.customization_phase:
            return await ctx.send(_("The Easter event is still in the customization phase. Upgrades will begin once guardians are finalized!"))
        
        player_team = self.get_player_team(ctx.author.id)
        if not player_team:
            return await ctx.send(_("You need to join a team first with `{prefix}easter join <team>`").format(prefix=ctx.clean_prefix))
        # Enforce team channel usage for upgrade
        team_channel_id = self.teams[player_team]["channel_id"]
        if ctx.channel.id != team_channel_id:
            return await ctx.send(_(f"Please use this command in your team's channel: <#{team_channel_id}>"))
        
        team_data = self.teams[player_team]
        available_upgrades = team_data["eggs_collected"] // 100
        
        if available_upgrades <= 0:
            return await ctx.send(_(
                f"Your team needs at least 100 eggs to perform an upgrade. "
                f"Current eggs: **{team_data['eggs_collected']}**"
            ))
        
        valid_upgrades = ["hp", "attack", "defense"]
        
        if not upgrade_type or upgrade_type.lower() not in valid_upgrades:
            embed = discord.Embed(
                title=f"{team_data['emoji']} Guardian Upgrades",
                description=_(
                    f"Your team has **{team_data['eggs_collected']}** eggs, enough for **{available_upgrades}** upgrades.\n\n"
                    f"Choose an upgrade type:\n"
                    f"• `{ctx.clean_prefix}easter upgrade hp` - Increase HP (Currently +{team_data['upgrades']['hp_boost']*5}%)\n"
                    f"• `{ctx.clean_prefix}easter upgrade attack` - Increase Attack (Currently +{team_data['upgrades']['attack_boost']*5}%)\n"
                    f"• `{ctx.clean_prefix}easter upgrade defense` - Increase Defense (Currently +{team_data['upgrades']['defense_boost']*5}%)"
                ),
                color=team_data["color"]
            )
            return await ctx.send(embed=embed)
        
        # Process the upgrade
        upgrade_key = f"{upgrade_type.lower()}_boost"
        self.teams[player_team]["upgrades"][upgrade_key] += 1
        self.teams[player_team]["eggs_collected"] -= 100
        
        embed = discord.Embed(
            title="Guardian Upgrade Successful!",
            description=_(
                f"You've strengthened **{team_data['guardian']['name']}**'s {upgrade_type}!\n\n"
                f"New {upgrade_type} bonus: +{team_data['upgrades'][upgrade_key]*5}%\n"
                f"Eggs remaining: {team_data['eggs_collected']}"
            ),
            color=team_data["color"]
        )
        await ctx.send(embed=embed)
        
        # Post upgrade in team channel
        try:
            team_channel = self.bot.get_channel(team_data["channel_id"])
            if team_channel:
                upgrade_embed = discord.Embed(
                    title="Guardian Upgrade",
                    description=_(
                        f"{ctx.author.mention} upgraded our guardian's **{upgrade_type}** by 5%!\n\n"
                        f"New bonuses:\n"
                        f"• HP: +{team_data['upgrades']['hp_boost']*5}%\n"
                        f"• Attack: +{team_data['upgrades']['attack_boost']*5}%\n"
                        f"• Defense: +{team_data['upgrades']['defense_boost']*5}%\n\n"
                        f"Team eggs remaining: {team_data['eggs_collected']}"
                    ),
                    color=team_data["color"]
                )
                await team_channel.send(embed=upgrade_embed)
        except Exception as e:
            print(f"Error sending team channel upgrade message: {e}")
    
    @has_char()
    @easter.command(brief=_("Vote for a new guardian ability"))
    @user_cooldown(86400)  # 24 hour cooldown
    @locale_doc
    async def vote(self, ctx):
        """Vote to unlock a new ability for your guardian
        
        When enough votes are gathered (5), a new ability will be unlocked.
        You can vote once per day."""
        try:
            if not self.enabled:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_("The Easter Egg Guardian Trials have not begun yet! Check back soon."))
                
            if self.customization_phase:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_("The Easter event is still in the customization phase. Use `{prefix}easter customize ability` instead.").format(prefix=ctx.clean_prefix))
            
            player_team = self.get_player_team(ctx.author.id)
            if not player_team:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_("You need to join a team first with `{prefix}easter join`." ).format(prefix=ctx.clean_prefix))
            
            # Determine which team this player battles against
            teams_list = list(self.teams.keys())
            player_index = teams_list.index(player_team)
            defender_team = teams_list[(player_index + 1) % len(teams_list)]


            
            # Check if in team channel
            team_channel_id = self.teams[player_team]["channel_id"]
            if ctx.channel.id != team_channel_id:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_(f"Please use this command in your team's channel: <#{team_channel_id}>"))
            
            # Check if team has recently unlocked an ability
            if player_team in self.team_ability_unlocked:
                if datetime.utcnow() < self.team_ability_unlocked[player_team]:
                    time_left = self.team_ability_unlocked[player_team] - datetime.utcnow()
                    hours, remainder = divmod(time_left.total_seconds(), 3600)
                    minutes, seconds = divmod(remainder, 60)
                    await self.bot.reset_cooldown(ctx)
                    return await ctx.send(_(
                        f"Your team recently unlocked a new ability! "
                        f"You can vote for another in **{int(hours)}h {int(minutes)}m**."
                    ))
            
            team_data = self.teams[player_team]
            guardian = team_data["guardian"]
            
            # Check if all abilities are already unlocked
            unlocked_abilities = sum(1 for ability in guardian["abilities"] if ability["unlocked"])
            if unlocked_abilities >= len(guardian["abilities"]):
                await self.bot.reset_cooldown(ctx)
                return await ctx.send(_("Your guardian has already unlocked all available abilities!"))
            
            # Get locked abilities
            locked_abilities = [ability for ability in guardian["abilities"] if not ability["unlocked"]]
            
            embed = discord.Embed(
                title=f"Vote for {guardian['name']}'s Next Ability",
                description=_(
                    f"Your guardian can learn a new ability with enough team votes.\n\n"
                    f"Choose one of the abilities below to vote for it:"
                ),
                color=team_data["color"]
            )
            
            for i, ability in enumerate(locked_abilities):
                effect_desc = ability["description"]
                embed.add_field(
                    name=f"{i+1}. {ability['name']}",
                    value=_(f"Damage: {ability['damage']}\nEffect: {effect_desc}\nCurrent Votes: {team_data['upgrades']['ability_votes'].get(ability['name'], 0)}/5"),
                    inline=True
                )
            
            # Create a view for ability selection
            view = AbilityVoteView(self, ctx.author.id, player_team, locked_abilities)
            await ctx.send(embed=embed, view=view)
        except Exception as e:
            await ctx.send(e)
    
    @has_char()
    @easter.command(brief=_("View team rankings"))
    @locale_doc
    async def leaderboard(self, ctx):
        """View the current standings of all teams in the Easter Egg Guardian Trials"""
        if not self.enabled:
            return await ctx.send(_("The Easter Egg Guardian Trials have not begun yet! Check back soon."))
            
        if self.customization_phase:
            return await ctx.send(_("The Easter event is still in the customization phase. The competition hasn't started yet!"))
        
        # Calculate team metrics
        team_metrics = []
        for team_name, team_data in self.teams.items():
            # Calculate full guardian power including customization
            guardian_power = (
                team_data["guardian"]["base_hp"] * (1 + (team_data["upgrades"]["hp_boost"] * 0.05) + 
                                                 (team_data["customization"]["points_allocated"]["hp"] * 0.05)) + 
                team_data["guardian"]["base_attack"] * (1 + (team_data["upgrades"]["attack_boost"] * 0.05) + 
                                                     (team_data["customization"]["points_allocated"]["attack"] * 0.05)) + 
                team_data["guardian"]["base_defense"] * (1 + (team_data["upgrades"]["defense_boost"] * 0.05) + 
                                                      (team_data["customization"]["points_allocated"]["defense"] * 0.05))
            )
            
            # Check victory condition
            defeated_teams = sum(1 for other_team, other_data in self.teams.items() 
                                if other_team != team_name and other_data["guardian"]["defeated"] == True)
            
            team_metrics.append({
                "name": team_name,
                "members": len(team_data["members"]),
                "eggs": team_data["eggs_collected"],
                "power": guardian_power,
                "victories": team_data["victories"],
                "defeats": team_data["defeats"],
                "color": team_data["color"],
                "emoji": team_data["emoji"],
                "guardian_defeated": team_data["guardian"]["defeated"],
                "defeated_teams": defeated_teams
            })
        
        # Sort by guardian status (if a team's guardian is defeated, they rank lower)
        # If multiple guardians are defeated, sort by victories and eggs
        team_metrics.sort(key=lambda x: (not x["guardian_defeated"], x["defeated_teams"], x["victories"], x["eggs"]), reverse=True)
        
        embed = discord.Embed(
            title="🏆 Easter Egg Guardian Trials - Team Rankings 🏆",
            description=_("The current standings in the race to victory:"),
            color=discord.Color.gold()
        )
        
        for i, team in enumerate(team_metrics):
            status = "🏆 VICTORY" if team["defeated_teams"] > 0 else "🔴 DEFEATED" if team["guardian_defeated"] else "🟢 ACTIVE"
            embed.add_field(
                name=f"{i+1}. {team['emoji']} {team['name']} ({status})",
                value=_(
                    f"**Members:** {team['members']}\n"
                    f"**Eggs Collected:** {team['eggs']}\n"
                    f"**Guardian Power:** {team['power']:,.0f}\n"
                    f"**Battle Record:** {team['victories']}W - {team['defeats']}L"
                ),
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @is_gm()
    @easter.command(hidden=True)
    async def test(self, ctx, team_name: str = None, player_count: int = 10):
        """Test a guardian battle with specific test users (GM only)"""

        try:
            if not team_name:
                return await ctx.send("You must specify a team name to test battle against.")
                    
            # Find team
            target_team = None
            for team in self.teams:
                if team_name.lower() in team.lower():
                    target_team = team
                    break
                        
            if not target_team:
                return await ctx.send(f"Team '{team_name}' not found. Available: {', '.join(self.teams.keys())}")
                    
            # Check if guardian is already defeated
            if self.teams[target_team]["guardian"]["defeated"]:
                return await ctx.send(f"The {target_team}'s guardian has already been defeated!")
                
            # Create test participants with specified test IDs
            test_ids = [
                708435868842459169, 635319019083137057, 700801066593419335, 384534935068737536, 
                728283563354619945, 245284329582755840, 761469900853215263, 742200394637246526, 
                454853145592463360
            ]
            
            test_participants = [ctx.author]  # Start with command caller
            
            # Add users from the test IDs
            for user_id in test_ids:
                member = ctx.guild.get_member(user_id)
                if member and len(test_participants) < player_count:
                    test_participants.append(member)
            
            # Limit to 10 participants maximum
            test_participants = test_participants[:min(10, player_count)]
                    
            # Assign yourself to a test team temporarily if needed
            original_team = self.get_player_team(ctx.author.id)
            attacker_team = "Test Team"
            
            if not original_team:
                # Get a team for testing
                test_team = list(self.teams.keys())[0]
                self.teams[test_team]["members"].append(ctx.author.id)
                attacker_team = test_team
            else:
                attacker_team = original_team
                    
            # Start test battle
            await ctx.send(f"Starting test battle: {attacker_team} vs {target_team}'s guardian with {len(test_participants)} players.")
            
            try:
                await self.start_guardian_battle(ctx, test_participants, attacker_team, target_team)
            except Exception as e:
                channel2 = self.bot.get_channel(1362758651047182578)
                await channel2.send(f"Error updating leaderboard embed: {e}")
            finally:
                # Clean up temporary team assignment if needed
                if not original_team and ctx.author.id in self.teams[test_team]["members"]:
                    self.teams[test_team]["members"].remove(ctx.author.id)

        except Exception as e:
            await ctx.send(e)
    
    @is_gm()
    @easter.command(hidden=True)
    async def enable(self, ctx):
        """Enable the Easter event (GM only)"""
        self.enabled = True
        await ctx.send("Easter Egg Guardian Trials has been enabled!")
    
    @is_gm()
    @easter.command(hidden=True)
    async def disable(self, ctx):
        """Disable the Easter event (GM only)"""
        self.enabled = False
        await ctx.send("Easter Egg Guardian Trials has been disabled!")
        
    @is_gm()
    @easter.command(hidden=True)
    async def reset(self, ctx, team_name: str = None):
        """Reset a guardian's status (GM only)"""
        if team_name:
            # Find team
            target_team = None
            for team in self.teams:
                if team_name.lower() in team.lower():
                    target_team = team
                    break
                    
            if not target_team:
                return await ctx.send(f"Team '{team_name}' not found. Available: {', '.join(self.teams.keys())}")
                
            # Reset the guardian's status
            self.teams[target_team]["guardian"]["defeated"] = False
            
            # Reset HP for battles against this guardian
            for key in list(self.current_hp.keys()):
                if key.endswith(f"_{target_team}"):
                    del self.current_hp[key]
                    
            await ctx.send(f"Reset {target_team}'s guardian status. It is now available for battles.")
        else:
            # Reset all guardians
            for team_name in self.teams:
                self.teams[team_name]["guardian"]["defeated"] = False
                
            # Clear all persisted HP
            self.current_hp = {}
            
            await ctx.send("Reset all guardians' status. They are now available for battles.")
    
    def get_player_team(self, player_id):
        """Get which team a player belongs to"""
        for team_name, team_data in self.teams.items():
            if player_id in team_data["members"]:
                return team_name
        # Check per-user stat points for team assignment
        if player_id in getattr(self, 'per_user_stat_points', {}):
            return self.per_user_stat_points[player_id]['team']
        return None
    
    async def start_guardian_battle(self, ctx, party_members, attacker_team, defender_team):
        """Start a battle between a player party and a guardian"""
        # Add battle cooldown (4 hours) to all participants
        battle_end_time = datetime.utcnow() + timedelta(hours=1)
        for member in party_members:
            self.player_battle_cooldowns[member.id] = battle_end_time
            
            # Remove from battle formation tracking
            if member.id in self.players_in_battle_formation:
                self.players_in_battle_formation.remove(member.id)
        
        # Initialize attacker party stats
        battle_participants = []
        
        async with self.bot.pool.acquire() as conn:
            # First add all human players
            for member in party_members:
                # Get actual player stats from DB
                player_stats = await self.get_player_stats(member, conn)

                # Get the player's god from profile table
                god_query = 'SELECT god FROM profile WHERE "user" = $1;'


                player_stats["hp"] += 1206
                player_stats["max_hp"] += 1206
                player_stats["damage"] += 1128
                player_stats["armor"] += 848

                battle_participants.append({
                    "user": member,
                    "hp": player_stats["hp"],
                    "max_hp": player_stats["max_hp"],
                    "damage": player_stats["damage"],
                    "armor": player_stats["armor"],
                    "is_pet": False,
                    "buffs": [],
                    "debuffs": []
                })

            # Add pets to reach 10 participants (one pet per member in order)
            pet_index = 0
            while len(battle_participants) < 10 and pet_index < len(party_members):
                member = party_members[pet_index]

                pet = await conn.fetchrow(
                    "SELECT * FROM monster_pets WHERE user_id = $1 AND equipped = TRUE;",
                    member.id
                )



                if pet:
                    hp = pet["hp"] + 1000
                    isnull = pet["id"]

                    if isnull == 675:
                        hp = 8
                    battle_participants.append({
                        "user": member,
                        "owner_id": member.id,
                        "pet_name": pet["name"],
                        "hp": hp,
                        "max_hp": hp,
                        "armor": pet["defense"],
                        "damage": pet["attack"],
                        "is_pet": True,
                        "buffs": [],
                        "debuffs": []
                    })

                pet_index += 1
                
                
        
        # Set up defender guardian with both customization and in-game upgrades
        guardian_data = self.teams[defender_team]["guardian"]
        team_upgrades = self.teams[defender_team]["upgrades"]
        team_customization = self.teams[defender_team]["customization"]["points_allocated"]
        
        # Calculate guardian stats with upgrades
        guardian_hp = guardian_data["base_hp"] * (1 + (team_upgrades["hp_boost"] * 0.05) + (team_customization["hp"] * 0.05))
        guardian_attack = guardian_data["base_attack"] * (1 + (team_upgrades["attack_boost"] * 0.05) + (team_customization["attack"] * 0.05))
        guardian_defense = guardian_data["base_defense"] * (1 + (team_upgrades["defense_boost"] * 0.05) + (team_customization["defense"] * 0.05))
        
        # Get persisted HP if this battle is ongoing
        battle_key = f"{attacker_team}_{defender_team}"
        current_hp_key = f"{attacker_team}_{defender_team}"
        
        if current_hp_key in self.current_hp:
            guardian_hp = self.current_hp[current_hp_key]

        guardian_defense = guardian_defense = 1150

        guardian = {
            "name": guardian_data["name"],
            "team": defender_team,
            "user": None,  # No user for guardian
            "hp": guardian_hp,
            "max_hp": guardian_data["base_hp"] * (1 + (team_upgrades["hp_boost"] * 0.05) + (team_customization["hp"] * 0.05)),
            "damage": guardian_attack,
            "armor": guardian_defense,
            "abilities": [a for a in guardian_data["abilities"] if a["unlocked"]],
            "is_guardian": True,
            "buffs": [],
            "debuffs": [],
            "kills": guardian_data.get("kills", 0)  # Track number of defeated combatants
        }
        
        # Reset hit counters for scaling damage
        self.player_hit_counters = {p["user"].id: 0 for p in battle_participants if not p.get("is_pet")}
        
        # Initialize battle log and action number
        battle_log = deque(maxlen=20)
        action_number = 1
        
        # Create initial battle embed
        battle_log.append(f"**Action #{action_number}**\nThe battle against {guardian['name']} has begun! 🐉")
        action_number += 1
        
        battle_embed = await self.create_battle_embed(guardian, battle_participants, battle_log)
        
        battle_msg = await ctx.send(embed=battle_embed)

        await asyncio.sleep(2)
        
        # Post battle alert in both team channels
        try:
            # Attacker team channel
            attacker_channel = self.bot.get_channel(self.teams[attacker_team]["channel_id"])
            if attacker_channel:
                alert_embed = discord.Embed(
                    title="⚔️ Guardian Battle Started!",
                    description=f"A team from the {attacker_team} is battling {guardian['name']}!",
                    color=self.teams[attacker_team]["color"]
                )
                await attacker_channel.send(embed=alert_embed)
                
            # Defender team channel
            defender_channel = self.bot.get_channel(self.teams[defender_team]["channel_id"])
            if defender_channel:
                alert_embed = discord.Embed(
                    title="⚠️ Guardian Under Attack!",
                    description=f"Our guardian {guardian['name']} is being attacked by the {attacker_team}!",
                    color=self.teams[defender_team]["color"]
                )
                await defender_channel.send(embed=alert_embed)
        except Exception as e:
            print(f"Error sending battle alert: {e}")
        
        # Set up battle data for tracking
        self.boss_battles[battle_key] = {
            "attacker_team": attacker_team,
            "defender_team": defender_team,
            "battle_msg": battle_msg,
            "battle_log": battle_log,
            "action_number": action_number
        }
        
        # Start battle loop
        start_time = datetime.utcnow()
        battle_ongoing = True
        current_round = 1
        
        # Battle turn order - guardian goes first, then players in random order
        battle_turn_order = [guardian] + battle_participants
        random.shuffle(battle_turn_order)
        self.team_battle_cooldowns[f"{attacker_team}_{defender_team}"] = datetime.utcnow() + timedelta(minutes=15)
        
        while battle_ongoing and datetime.utcnow() < start_time + timedelta(minutes=20):
            # Process each participant's turn
            for entity in battle_turn_order:
                if not battle_ongoing:
                    break
                    
                # Skip if entity is dead
                if entity["hp"] <= 0:
                    continue
                    
                # Check battle end conditions
                non_possessed_players_alive = any(p["hp"] > 0 and not p.get("shadow_possessed", False) for p in battle_participants)
                if guardian["hp"] <= 0 or not non_possessed_players_alive:
                    battle_ongoing = False
                    break
                    
                current_action_log = []
                
                # Process buffs/debuffs at start of turn
                if entity.get("buffs") or entity.get("debuffs"):
                    for buff in list(entity.get("buffs", [])):
                        # Process buff effect
                        if buff["type"] == "regeneration":
                            heal_amount = buff["value"]
                            entity["hp"] = min(entity["max_hp"], entity["hp"] + heal_amount)
                            current_action_log.append(f"**{entity.get('pet_name', entity['user'].display_name) if not entity.get('is_guardian') else entity['name']}** regenerates for {heal_amount:,.0f} HP")
                            
                        elif buff["type"] == "increasing_regen":
                            # Special regeneration that increases each turn
                            heal_amount = buff["value"]
                            entity["hp"] = min(entity["max_hp"], entity["hp"] + heal_amount)
                            current_action_log.append(f"**{entity.get('pet_name', entity['user'].display_name) if not entity.get('is_guardian') else entity['name']}** regenerates for {heal_amount:,.0f} HP (increasing)")
                            
                            # Increase the regeneration for next turn
                            buff["value"] += buff["growth"]
                            
                        # Reduce duration
                        buff["duration"] -= 1
                        if buff["duration"] <= 0:
                            entity["buffs"].remove(buff)
                            current_action_log.append(f"**{entity.get('pet_name', entity['user'].display_name) if not entity.get('is_guardian') else entity['name']}**'s {buff['name']} effect has ended")
                            
                    for debuff in list(entity.get("debuffs", [])):
                        # Process debuff effect
                        if debuff["type"] == "dot":
                            damage = debuff["value"]
                            entity["hp"] = max(0, entity["hp"] - damage)
                            current_action_log.append(f"**{entity.get('pet_name', entity['user'].display_name) if not entity.get('is_guardian') else entity['name']}** takes {damage:,.0f} damage from {debuff['name']}")
                            
                            if entity["hp"] <= 0:
                                current_action_log.append(f"**{entity.get('pet_name', entity['user'].display_name) if not entity.get('is_guardian') else entity['name']}** has fallen from {debuff['name']}! ☠️")
                                break
                                
                        # Reduce duration
                        debuff["duration"] -= 1
                        if debuff["duration"] <= 0:
                            entity["debuffs"].remove(debuff)
                            current_action_log.append(f"**{entity.get('pet_name', entity['user'].display_name) if not entity.get('is_guardian') else entity['name']}**'s {debuff['name']} effect has ended")
                
                # Skip turn if stunned
                if any(d["type"] == "stun" for d in entity.get("debuffs", [])):
                    current_action_log.append(f"**{entity.get('pet_name', entity['user'].display_name) if not entity.get('is_guardian') else entity['name']}** is stunned and cannot act!")
                    continue
                    
                # Skip turn if dead
                if entity["hp"] <= 0:
                    continue
                
                if entity.get("is_guardian"):
                    # Guardian's turn
                    valid_targets = [p for p in battle_participants if p["hp"] > 0 and not p.get("shadow_possessed", False)]
                    if not valid_targets:
                        battle_ongoing = False
                        break
                        
                    # Decide whether to use special ability or basic attack
                    use_special = random.random() < 0.2
                    
                    if use_special and entity["abilities"]:
                        # Use a special ability
                        abilities = entity["abilities"]
                        
                        # Create a custom weights list that doesn't modify original data
                        weights = []
                        for ability in abilities:
                            weight = ability["chance"]  # Get original chance
                            if ability["effect"] == "aoe":
                                weight = 0.1  # Override AOE abilities to 0.1 weight
                            if ability["effect"] == "natures_wrath":
                                weight = 0.1
                            weights.append(weight)
                        
                        selected_ability = random.choices(abilities, weights=weights, k=1)[0]
                        
                        effect = selected_ability["effect"]
                        damage = selected_ability["damage"]
                        
                        # Process complex special abilities
                        if effect == "aoe":
                            # AoE damage to all players
                            damage_dealt = []
                            for target in valid_targets:
                                adjusted_damage = max(1, round(damage - self.ensure_float(target["armor"]) + random.randint(0, 100), 2))
                                
                                # Apply damage reduction from buffs
                                for buff in target.get("buffs", []):
                                    if buff["type"] == "damage_reduction":
                                        adjusted_damage *= (1 - buff["value"])
                                
                                target["hp"] = max(0, target["hp"] - adjusted_damage)
                                
                                target_name = target.get("pet_name", target["user"].display_name) if not target.get("is_guardian") else target["name"]
                                damage_dealt.append(f"**{target_name}** ({adjusted_damage:,.2f}HP)")
                                
                                # Track hit counter for scaling
                                if not target.get("is_pet") and target["user"].id in self.player_hit_counters:
                                    self.player_hit_counters[target["user"].id] += 1
                                
                                # Check if target died
                                if target["hp"] <= 0:
                                    damage_dealt[-1] += " ☠️"
                                    # Increment kills if a player (not pet) was defeated
                                    if not target.get("is_pet"):
                                        guardian["kills"] = guardian.get("kills", 0) + 1
                                        self.teams[defender_team]["guardian"]["kills"] = guardian["kills"]
                            
                            current_action_log.append(
                                f"{guardian['name']} unleashes **{selected_ability['name']}**!\n"
                                f"Damage dealt to: {', '.join(damage_dealt)}"
                            )
                            
                        elif effect == "dawn_blessing":
                            # Team-wide heal + damage buff for Dawn Protectors
                            heal_amount = 500
                            duration = 3
                            
                            # Add buff to guardian
                            guardian["hp"] = min(guardian["max_hp"], guardian["hp"] + heal_amount)
                            
                            # Add damage boost buff
                            guardian["buffs"].append({
                                "name": "Dawn's Blessing",
                                "type": "damage_boost",
                                "value": 0.3,  # 30% damage boost
                                "duration": duration
                            })
                            
                            current_action_log.append(
                                f"{guardian['name']} uses **{selected_ability['name']}**!\n"
                                f"Heals for {heal_amount:,.0f} HP and gains 30% increased damage for {duration} turns!"
                            )
                            
                        elif effect == "self_shadow_shield":
                            # Team-wide damage reduction for Twilight Keepers
                            duration = 2
                            
                            # Add damage reduction buff
                            guardian["buffs"].append({
                                "name": "Midnight Veil",
                                "type": "damage_reduction",
                                "value": 0.5,  # 50% damage reduction
                                "duration": duration
                            })
                            
                            current_action_log.append(
                                f"{guardian['name']} casts **{selected_ability['name']}**!\n"
                                f"Gains 50% damage reduction for {duration} turns!"
                            )
                            
                        elif effect == "self_regen":
                            # Team-wide regeneration for Bloom Wardens
                            
                            regen_amount = random.randint(450, 750)
                            duration = 3

                            heal_amount = random.randint(1000, 2500)
                            
                            # Immediate heal
                            guardian["hp"] = min(guardian["max_hp"], guardian["hp"] + heal_amount)
                            
                            # Add regeneration buff
                            guardian["buffs"].append({
                                "name": "Spring's Renewal",
                                "type": "regeneration",
                                "value": regen_amount,
                                "duration": duration
                            })
                            
                            current_action_log.append(
                                f"{guardian['name']} casts **{selected_ability['name']}**!\n"
                                f"Heals for {heal_amount:,.0f} HP and will regenerate {regen_amount:,.0f} HP per turn for {duration} turns!"
                            )
                            
                        elif effect == "radiant_eruption":
                            # Massive damage with chance to blind
                            target = random.choice(valid_targets)
                            adjusted_damage = max(1, round(damage - self.ensure_float(target["armor"]) + random.randint(0, 100), 2))
                            
                            # Apply damage reduction from buffs
                            for buff in target.get("buffs", []):
                                if buff["type"] == "damage_reduction":
                                    adjusted_damage *= (1 - buff["value"])
                            
                            target["hp"] = max(0, target["hp"] - adjusted_damage)
                            
                            target_name = target.get("pet_name", target["user"].display_name) if not target.get("is_guardian") else target["name"]
                            
                            # Track hit counter for scaling
                            if not target.get("is_pet") and target["user"].id in self.player_hit_counters:
                                self.player_hit_counters[target["user"].id] += 1
                                
                            # 50% chance to blind (stun for 1 turn)
                            blinded = random.random() < 0.5
                            blind_text = ""
                            if blinded and target["hp"] > 0:
                                target["debuffs"].append({
                                    "name": "Blinded",
                                    "type": "stun",
                                    "duration": 1
                                })
                                blind_text = f"\n**{target_name}** is blinded for 1 turn! ⚡"
                            
                            current_action_log.append(
                                f"{guardian['name']} unleashes **{selected_ability['name']}** on **{target_name}**!\n"
                                f"Deals **{adjusted_damage:,.2f}HP** damage!{blind_text}"
                            )
                            
                            # Check if target died
                            if target["hp"] <= 0:
                                current_action_log.append(f"**{target_name}** has fallen! ☠️")
                                # Increment kills if a player (not pet) was defeated
                                if not target.get("is_pet"):
                                    guardian["kills"] = guardian.get("kills", 0) + 1
                                    self.teams[defender_team]["guardian"]["kills"] = guardian["kills"]
                            
                        elif effect == "eclipse_force":
                            # Execute low health target and heal
                            valid_targets.sort(key=lambda p: p["hp"] / p["max_hp"])  # Sort by % HP, lowest first
                            target = valid_targets[0]  # Target with lowest % HP
                            
                            target_name = target.get("pet_name", target["user"].display_name) if not target.get("is_guardian") else target["name"]
                            
                            # Track hit counter for scaling
                            if not target.get("is_pet") and target["user"].id in self.player_hit_counters:
                                self.player_hit_counters[target["user"].id] += 1
                            
                            # Check if target is below 20% HP
                            if target["hp"] / target["max_hp"] <= 0.2:
                                # Execute
                                execute_damage = target["hp"]  # Set damage to remaining HP
                                target["hp"] = 0
                                
                                # Heal for 50% of damage done
                                heal_amount = guardian["max_hp"] * 0.001  # 0.1% of max HP
                                guardian["hp"] = min(guardian["max_hp"], guardian["hp"] + heal_amount)
                                
                                current_action_log.append(
                                    f"{guardian['name']} casts **{selected_ability['name']}** on the weakened **{target_name}**!\n"
                                    f"**EXECUTED!** And heals for {heal_amount:,.0f} HP! ⚰️"
                                )
                            else:
                                # Regular damage if not executed
                                adjusted_damage = max(1, round(damage - self.ensure_float(target["armor"]) + random.randint(0, 100), 2))
                                
                                # Apply damage reduction from buffs
                                for buff in target.get("buffs", []):
                                    if buff["type"] == "damage_reduction":
                                        adjusted_damage *= (1 - buff["value"])
                                
                                target["hp"] = max(0, target["hp"] - adjusted_damage)
                                
                                current_action_log.append(
                                    f"{guardian['name']} casts **{selected_ability['name']}** on **{target_name}**!\n"
                                    f"Deals **{adjusted_damage:,.2f}HP** damage!"
                                )
                                
                                # Check if target died
                                if target["hp"] <= 0:
                                    current_action_log.append(f"**{target_name}** has fallen! ☠️")
                                    # Increment kills if a player (not pet) was defeated
                                    if not target.get("is_pet"):
                                        guardian["kills"] = guardian.get("kills", 0) + 1
                                        self.teams[defender_team]["guardian"]["kills"] = guardian["kills"]
                            
                        elif effect == "natures_wrath":
                            # Field of damaging plants
                            hazard_damage = 150
                            duration = 3
                            slow_amount = 0.3  # 30% attack reduction
                            
                            for target in valid_targets:
                                target["debuffs"].append({
                                    "name": "Hazardous Plants",
                                    "type": "dot",
                                    "value": hazard_damage,
                                    "duration": duration
                                })
                                
                                target["debuffs"].append({
                                    "name": "Slowed",
                                    "type": "attack_reduction",
                                    "value": slow_amount,
                                    "duration": duration
                                })
                                
                                # Track hit counter for scaling
                                if not target.get("is_pet") and target["user"].id in self.player_hit_counters:
                                    self.player_hit_counters[target["user"].id] += 1
                            
                            current_action_log.append(
                                f"{guardian['name']} unleashes **{selected_ability['name']}**!\n"
                                f"The arena is filled with hazardous plants! All enemies will take {hazard_damage:,.0f} damage per turn and have 30% reduced attack for {duration} turns!"
                            )
                            
                        elif effect == "shadow_realm":
                            # Enhanced Shadow Realm logic
                            # Track conversions per battle (in guardian dict for this battle)
                            if "shadow_realm_conversions" not in guardian:
                                guardian["shadow_realm_conversions"] = 0
                            
                            # Only consider living, non-pet, non-guardian, non-already-converted targets
                            valid_shadow_targets = [p for p in valid_targets if not p.get("is_pet") and not p.get("is_guardian") and not p.get("shadow_possessed", False) and p["hp"] > 0]
                            
                            if len(valid_shadow_targets) == 1:
                                # Banish (execute) the single opponent
                                target = valid_shadow_targets[0]
                                target_name = target["user"].display_name
                                target["hp"] = 0
                                target["banished"] = True
                                current_action_log.append(f"{guardian['name']} banishes **{target_name}** to the **Shadow Realm**!\n**{target_name}** was instantly banished and removed from the battle.")
                                # Increment kills if a player
                                guardian["kills"] = guardian.get("kills", 0) + 1
                                self.teams[defender_team]["guardian"]["kills"] = guardian["kills"]
                            elif len(valid_shadow_targets) >= 1 and guardian["shadow_realm_conversions"] < 2:
                                # Possess one of the targets, convert to guardian team for battle
                                target = random.choice(valid_shadow_targets)
                                target_name = target["user"].display_name
                                target["shadow_possessed"] = True
                                target["original_team"] = attacker_team
                                target["team"] = defender_team
                                guardian["shadow_realm_conversions"] += 1
                                current_action_log.append(f"{guardian['name']} possesses **{target_name}** with the **Shadow Realm**!\n**{target_name}** is forced to fight for the guardian this battle.")
                            else:
                                # No valid targets or already max conversions, do normal damage
                                if valid_targets:
                                    target = random.choice(valid_targets)
                                    target_name = target.get("pet_name", target["user"].display_name)
                                    adjusted_damage = max(1, round(damage - self.ensure_float(target["armor"]) + random.randint(0, 100), 2))
                                    target["hp"] = max(0, target["hp"] - adjusted_damage)
                                    
                                    current_action_log.append(
                                        f"{guardian['name']} attempts to use **Shadow Realm** but instead deals **{adjusted_damage:,.2f}HP** damage to **{target_name}**!"
                                    )
                                    
                                    if target["hp"] <= 0:
                                        current_action_log.append(f"**{target_name}** has fallen! ☠️")
                                        if not target.get("is_pet"):
                                            guardian["kills"] = guardian.get("kills", 0) + 1
                                            self.teams[defender_team]["guardian"]["kills"] = guardian["kills"]
                                else:
                                    current_action_log.append(f"{guardian['name']} tried to invoke the **Shadow Realm**, but it fizzled.")

                            
                        elif effect == "nightmare_gaze":
                            # Chance to make enemies attack allies
                            target = random.choice(valid_targets)
                            target_name = target.get("pet_name", target["user"].display_name) if not target.get("is_guardian") else target["name"]
                            
                            # Apply hypnotize debuff
                            duration = 2
                            target["debuffs"].append({
                                "name": "Hypnotized",
                                "type": "hypnotize",
                                "value": 0.3,  # 30% chance to attack allies
                                "duration": duration
                            })
                            
                            # Track hit counter for scaling
                            if not target.get("is_pet") and target["user"].id in self.player_hit_counters:
                                self.player_hit_counters[target["user"].id] += 1
                            
                            current_action_log.append(
                                f"{guardian['name']} casts **Nightmare Gaze** on **{target_name}**!\n"
                                f"**{target_name}** has a 30% chance to attack allies for {duration} turns! 👁️"
                            )
                            
                        elif effect == "entangling_roots":
                            # Immobilize and reduce defense
                            target = random.choice(valid_targets)
                            target_name = target.get("pet_name", target["user"].display_name) if not target.get("is_guardian") else target["name"]
                            
                            # Initial damage
                            adjusted_damage = max(1, round(damage - self.ensure_float(target["armor"]) + random.randint(0, 100), 2))
                            
                            # Apply damage reduction from buffs
                            for buff in target.get("buffs", []):
                                if buff["type"] == "damage_reduction":
                                    adjusted_damage *= (1 - buff["value"])
                            
                            target["hp"] = max(0, target["hp"] - adjusted_damage)
                            
                            # Track hit counter for scaling
                            if not target.get("is_pet") and target["user"].id in self.player_hit_counters:
                                self.player_hit_counters[target["user"].id] += 1
                            
                            # Apply root debuffs
                            duration = 2
                            target["debuffs"].append({
                                "name": "Entangled",
                                "type": "stun",
                                "duration": duration
                            })
                            
                            target["debuffs"].append({
                                "name": "Defense Reduced",
                                "type": "defense_reduction",
                                "value": 0.3,  # 30% defense reduction
                                "duration": duration
                            })
                            
                            current_action_log.append(
                                f"{guardian['name']} entangles **{target_name}** in roots!\n"
                                f"Deals **{adjusted_damage:,.2f}HP** damage, immobilizes, and reduces defense by 30% for {duration} turns!"
                            )
                            
                            # Check if target died
                            if target["hp"] <= 0:
                                current_action_log.append(f"**{target_name}** has fallen! ☠️")
                                # Increment kills if a player (not pet) was defeated
                                if not target.get("is_pet"):
                                    guardian["kills"] = guardian.get("kills", 0) + 1
                                    self.teams[defender_team]["guardian"]["kills"] = guardian["kills"]
                            
                        elif effect == "time_dilation":
                            # Extra turn chance buff
                            duration = 3
                            
                            # Add extra turn buff
                            guardian["buffs"].append({
                                "name": "Time Dilation",
                                "type": "extra_turn",
                                "value": 0.3,  # 30% chance for extra turn
                                "duration": duration
                            })
                            
                            current_action_log.append(
                                f"{guardian['name']} manipulates time with **{selected_ability['name']}**!\n"
                                f"Has a 30% chance for extra turns for {duration} turns! ⏱️"
                            )
                            
                        elif effect == "regenerative_spores":
                            # Increasing regeneration
                            base_regen = 200
                            duration = 3
                            
                            # Add special regeneration buff
                            guardian["buffs"].append({
                                "name": "Regenerative Spores",
                                "type": "increasing_regen",
                                "value": base_regen,  # Starts at 200 HP per turn
                                "growth": 100,       # Increases by 100 each turn
                                "duration": duration
                            })
                            
                            current_action_log.append(
                                f"{guardian['name']} releases **Regenerative Spores**!\n"
                                f"Will regenerate increasing health for {duration} turns! 🌱"
                            )
                            
                        elif effect == "resurrection":
                            # Try to find a defeated ally (only applicable if guardian has minions)
                            # In this case, just heal the guardian significantly
                            heal_amount = guardian["max_hp"] * 0.2  # 20% max HP heal
                            guardian["hp"] = min(guardian["max_hp"], guardian["hp"] + heal_amount)
                            
                            # Add shield buff
                            guardian["buffs"].append({
                                "name": "Resurrection Shield",
                                "type": "damage_reduction",
                                "value": 0.3,  # 30% damage reduction
                                "duration": 2
                            })
                            
                            current_action_log.append(
                                f"{guardian['name']} uses **{selected_ability['name']}**!\n"
                                f"Heals for {heal_amount:,.0f} HP and gains a protective shield reducing damage by 30% for 2 turns! ✨"
                            )
                            
                        else:
                            # Default single target ability 
                            target = random.choice(valid_targets)
                            
                            # Apply scaling damage factor based on how many times this player has been hit
                            scaling_factor = 1.0
                            if not target.get("is_pet") and target["user"].id in self.player_hit_counters:
                                hit_count = self.player_hit_counters[target["user"].id]
                                scaling_factor = 1.0 + (hit_count * 0.05)  # +10% damage per previous hit
                                self.player_hit_counters[target["user"].id] += 1
                                
                            adjusted_damage = max(1, round((damage * scaling_factor) - self.ensure_float(target["armor"]) + random.randint(0, 100), 2))
                            
                            # Apply damage reduction from buffs
                            for buff in target.get("buffs", []):
                                if buff["type"] == "damage_reduction":
                                    adjusted_damage *= (1 - buff["value"])
                            
                            target["hp"] = max(0, target["hp"] - adjusted_damage)
                            
                            target_name = target.get("pet_name", target["user"].display_name) if not target.get("is_guardian") else target["name"]
                            
                            current_action_log.append(
                                f"{guardian['name']} uses **{selected_ability['name']}** on **{target_name}**!\n"
                                f"Deals **{adjusted_damage:,.2f}HP** damage!"
                            )
                            
                            # Apply effect
                            effect_applied = False
                            if effect == "stun" and target["hp"] > 0:
                                stun_duration = 2
                                target["debuffs"].append({
                                    "name": "Stunned",
                                    "type": "stun",
                                    "duration": stun_duration
                                })
                                current_action_log.append(f"**{target_name}** is stunned for {stun_duration} turns! ⚡")
                                effect_applied = True
                                
                            elif effect == "dot" and target["hp"] > 0:
                                dot_duration = 3
                                dot_damage = max(50, round(adjusted_damage * 0.25))
                                target["debuffs"].append({
                                    "name": "Bleeding",
                                    "type": "dot",
                                    "value": dot_damage,
                                    "duration": dot_duration
                                })
                                current_action_log.append(f"**{target_name}** is bleeding for {dot_damage} damage per turn for {dot_duration} turns! ☠️")
                                effect_applied = True
                                
                            elif effect == "random_debuff" and target["hp"] > 0:
                                debuff_types = [
                                    {"name": "Weakened", "type": "attack_reduction", "value": 0.3, "duration": 2},
                                    {"name": "Vulnerable", "type": "defense_reduction", "value": 0.3, "duration": 2},
                                    {"name": "Poisoned", "type": "dot", "value": 150, "duration": 3}
                                ]
                                selected_debuff = random.choice(debuff_types)
                                target["debuffs"].append(selected_debuff)
                                
                                effect_desc = ""
                                if selected_debuff["type"] == "attack_reduction":
                                    effect_desc = f"attack reduced by {selected_debuff['value']*100}%"
                                elif selected_debuff["type"] == "defense_reduction":
                                    effect_desc = f"defense reduced by {selected_debuff['value']*100}%"
                                elif selected_debuff["type"] == "dot":
                                    effect_desc = f"taking {selected_debuff['value']} damage per turn"
                                    
                                current_action_log.append(f"**{target_name}** is {selected_debuff['name']} ({effect_desc}) for {selected_debuff['duration']} turns!")
                                effect_applied = True
                                
                            elif effect == "steal_buffs" and target["hp"] > 0:
                                steal_text = ""
                                # Steal a random buff if available
                                if target.get("buffs") and len(target["buffs"]) > 0:
                                    stolen_buff = random.choice(target["buffs"])
                                    target["buffs"].remove(stolen_buff)
                                    guardian["buffs"].append(stolen_buff)
                                    steal_text = f" and steals {stolen_buff['name']}"
                                # Apply attack reduction to target
                                attack_reduction = {"name": "Strength Drained", "type": "attack_reduction", "value": 0.3, "duration": 2}
                                target["debuffs"].append(attack_reduction)
                                # Apply matching attack buff to guardian
                                attack_buff = {"name": "Stolen Strength", "type": "attack_increase", "value": 0.3, "duration": 2}
                                guardian["buffs"].append(attack_buff)
                                current_action_log.append(f"{guardian['name']} drains strength from **{target_name}**{steal_text}! {target_name}'s attack is reduced by 30% for 2 turns, {guardian['name']}'s attack increases by 30% for 2 turns.")
                                effect_applied = True
                            
                            # Check if target died
                            if target["hp"] <= 0:
                                current_action_log.append(f"**{target_name}** has fallen! ☠️")
                                # Increment kills if a player (not pet) was defeated
                                if not target.get("is_pet"):
                                    guardian["kills"] = guardian.get("kills", 0) + 1
                                    self.teams[defender_team]["guardian"]["kills"] = guardian["kills"]
                    else:
                        # Basic attack with scaling damage
                        target = random.choice(valid_targets)
                        
                        # Apply scaling damage factor based on how many times this player has been hit
                        scaling_factor = 1.0
                        if not target.get("is_pet") and target["user"].id in self.player_hit_counters:
                            hit_count = self.player_hit_counters[target["user"].id]
                            scaling_factor = 1.0 + (hit_count * 0.2)  # +10% damage per previous hit
                            self.player_hit_counters[target["user"].id] += 1
                            
                        adjusted_damage = max(1, round((entity["damage"] * scaling_factor) - self.ensure_float(target["armor"]) + random.randint(0, 100), 2))
                        
                        # Apply damage reduction from buffs
                        for buff in target.get("buffs", []):
                            if buff["type"] == "damage_reduction":
                                adjusted_damage *= (1 - buff["value"])
                        
                        target["hp"] = max(0, target["hp"] - adjusted_damage)
                        
                        target_name = target.get("pet_name", target["user"].display_name) if not target.get("is_guardian") else target["name"]
                        
                        # Format message with scaling indicator if applicable
                        scaling_text = ""
                        if scaling_factor > 1.0:
                            scaling_text = f" (Damage +{int((scaling_factor-1)*100)}% from repeated targeting)"
                            
                        current_action_log.append(
                            f"{guardian['name']} attacks **{target_name}** for **{adjusted_damage:,.2f}HP** damage!{scaling_text}"
                        )
                        
                        # Check if target died
                        if target["hp"] <= 0:
                            current_action_log.append(f"**{target_name}** has fallen! ☠️")
                            # Increment kills if a player (not pet) was defeated
                            if not target.get("is_pet"):
                                guardian["kills"] = guardian.get("kills", 0) + 1
                                self.teams[defender_team]["guardian"]["kills"] = guardian["kills"]
                else:
                    # Player or pet turn
                    name = entity.get("pet_name", entity["user"].display_name) if not entity.get("is_guardian") else entity["name"]

                    # Check hypnotize effect (chance to attack allies) - only if not possessed
                    is_hypnotized = False
                    if not entity.get("shadow_possessed", False):
                        for debuff in entity.get("debuffs", []):
                            if debuff["type"] == "hypnotize" and random.random() < debuff["value"]:
                                is_hypnotized = True
                                break

                    # FIXED STRUCTURE: Mutually exclusive conditions
                    if entity.get("shadow_possessed", False):
                        # Possessed players attack their former teammates instead of the guardian
                        valid_targets = [p for p in battle_participants if 
                                        p["hp"] > 0 and 
                                        not p.get("shadow_possessed", False) and
                                        not p.get("is_guardian", False) and  # Never attack the guardian when possessed
                                        p != entity]
                        
                        if valid_targets:
                            target = random.choice(valid_targets)
                            adjusted_damage = max(1, round(entity["damage"] - self.ensure_float(target["armor"]) + random.randint(0, 100), 2))
                            
                            # Apply damage reduction from buffs
                            for buff in target.get("buffs", []):
                                if buff["type"] == "damage_reduction":
                                    adjusted_damage *= (1 - buff["value"])
                            
                            target["hp"] = max(0, target["hp"] - adjusted_damage)
                            
                            target_name = target.get("pet_name", target["user"].display_name) if not target.get("is_guardian") else target["name"]
                            
                            current_action_log.append(
                                f"**{name}** (🕸️ POSSESSED) attacks teammate **{target_name}** for **{adjusted_damage:,.2f}HP** damage!"
                            )
                            
                            # Check if target died
                            if target["hp"] <= 0:
                                current_action_log.append(f"**{target_name}** has fallen! ☠️")
                                # Increment kills if a player (not pet) was defeated
                                if not target.get("is_pet"):
                                    guardian["kills"] = guardian.get("kills", 0) + 1
                                    self.teams[defender_team]["guardian"]["kills"] = guardian["kills"]
                        else:
                            current_action_log.append(f"**{name}** (🕸️ POSSESSED) has no valid targets to attack!")

                    elif is_hypnotized and len(battle_participants) > 1:
                        # Attack a random ally instead of the guardian
                        valid_allies = [p for p in battle_participants if p["hp"] > 0 and p != entity]
                        if valid_allies:
                            target = random.choice(valid_allies)
                            adjusted_damage = max(1, round(entity["damage"] - self.ensure_float(target["armor"]) + random.randint(0, 100), 2))
                            
                            # Apply damage reduction from buffs
                            for buff in target.get("buffs", []):
                                if buff["type"] == "damage_reduction":
                                    adjusted_damage *= (1 - buff["value"])
                            
                            target["hp"] = max(0, target["hp"] - adjusted_damage)
                            
                            target_name = target.get("pet_name", target["user"].display_name) if not target.get("is_guardian") else target["name"]
                            
                            current_action_log.append(
                                f"**{name}** is hypnotized and attacks ally **{target_name}** for **{adjusted_damage:,.2f}HP** damage! 👁️"
                            )
                            
                            # Check if target died
                            if target["hp"] <= 0:
                                current_action_log.append(f"**{target_name}** has fallen! ☠️")
                                # Increment kills if a player (not pet) was defeated
                                if not target.get("is_pet"):
                                    guardian["kills"] = guardian.get("kills", 0) + 1
                                    self.teams[defender_team]["guardian"]["kills"] = guardian["kills"]

                    else:
                        # Normal attack - can target either the guardian or possessed teammates
                        # Create a target list that includes the guardian and any possessed players
                        possible_targets = [guardian]  # Start with the guardian
                        
                        # Add any possessed teammates
                        possessed_teammates = [p for p in battle_participants if 
                                            p["hp"] > 0 and 
                                            p.get("shadow_possessed", False) and
                                            p != entity]
                        possible_targets.extend(possessed_teammates)
                        
                        # Choose a target - 70% chance to target guardian, 30% chance to target a possessed player if any exist
                        if possessed_teammates and random.random() < 0.3:
                            target = random.choice(possessed_teammates)
                            is_guardian_target = False
                        else:
                            target = guardian
                            is_guardian_target = True
                        
                        base_damage = entity["damage"]
                        
                        # Apply debuff effects on damage
                        for debuff in entity.get("debuffs", []):
                            if debuff["type"] == "attack_reduction":
                                base_damage *= (1 - debuff["value"])
                        
                        # Apply buff effects on damage
                        for buff in entity.get("buffs", []):
                            if buff["type"] == "damage_boost":
                                base_damage *= (1 + buff["value"])
                        
                        # Calculate damage based on target's armor
                        adjusted_damage = max(1, round(base_damage - self.ensure_float(target["armor"]) + random.randint(0, 100), 2))
                        
                        # Apply target's damage reduction buffs
                        for buff in target.get("buffs", []):
                            if buff["type"] == "damage_reduction":
                                adjusted_damage *= (1 - buff["value"])
                        
                        # Apply damage
                        target["hp"] = max(0, target["hp"] - adjusted_damage)
                        
                        target_name = target.get("pet_name", target["user"].display_name) if not target.get("is_guardian") else target["name"]
                        if not is_guardian_target:
                            current_action_log.append(
                                f"**{name}** attacks the possessed **{target_name}** for **{adjusted_damage:,.2f}HP** damage!"
                            )
                        else:
                            current_action_log.append(
                                f"**{name}** attacks {target_name} for **{adjusted_damage:,.2f}HP** damage!"
                            )
                        
                        # Check if target died
                        if target["hp"] <= 0:
                            if is_guardian_target:
                                current_action_log.append(f"**{target_name}** has been defeated! 🎉")
                            else:
                                current_action_log.append(f"**{target_name}** has been freed from possession! ✨")
                                # Remove them from battle but don't count as a kill
                                target["freed_from_possession"] = True
                        
                        # Only apply Time Dilation effect if attacking the guardian
                        if is_guardian_target:
                            # Check for extra turn from Time Dilation
                            got_extra_turn = False
                            for buff in entity.get("buffs", []):
                                if buff["type"] == "extra_turn" and random.random() < buff["value"]:
                                    got_extra_turn = True
                                    current_action_log.append(f"**{name}** gets an extra turn from Time Dilation! ⏱️")
                                    
                                    # Apply the extra turn immediately (simplified approach)
                                    extra_damage = max(1, round(base_damage - self.ensure_float(guardian["armor"]) + random.randint(0, 100), 2))
                                    
                                    # Apply guardian's damage reduction buffs again
                                    for buff in guardian.get("buffs", []):
                                        if buff["type"] == "damage_reduction":
                                            extra_damage *= (1 - buff["value"])
                                    
                                    guardian["hp"] = max(0, guardian["hp"] - extra_damage)
                                    current_action_log.append(f"**{name}** attacks again for **{extra_damage:,.2f}HP** damage!")
                                    
                                    # Check if guardian died
                                    if guardian["hp"] <= 0:
                                        current_action_log.append(f"**{guardian['name']}** has been defeated! 🎉")
                
                # Log actions and update display
                if current_action_log:
                    for log_entry in current_action_log:
                        battle_log.append(f"**Action #{action_number}**\n{log_entry}")
                        action_number += 1
                    
                    # Update the current HP for persistence
                    self.current_hp[current_hp_key] = guardian["hp"]
                    
                    # Update battle data
                    self.boss_battles[battle_key]["battle_log"] = battle_log
                    self.boss_battles[battle_key]["action_number"] = action_number
                    
                    # Update the battle embed
                    await self.update_battle_embed(battle_msg, guardian, battle_participants, battle_log)
                    await asyncio.sleep(2)
            
            current_round += 1
        
        # Handle battle end
        if guardian["hp"] <= 0:
            battle_log.append(f"**Action #{action_number}**\n{guardian['name']} has been defeated! Victory! 🎉")
            await self.update_battle_embed(battle_msg, guardian, battle_participants, battle_log)
            await self.handle_victory(ctx, party_members, attacker_team, defender_team)
        elif not any(p["hp"] > 0 and not p.get("shadow_possessed", False) for p in battle_participants):
            battle_log.append(f"**Action #{action_number}**\nThe party has been defeated! 💀")
            await self.update_battle_embed(battle_msg, guardian, battle_participants, battle_log)
            await self.handle_defeat(ctx, party_members, attacker_team, defender_team, battle_participants)
        else:
            battle_log.append(f"**Action #{action_number}**\nTime's up! The battle was lost! ⏰")
            await self.update_battle_embed(battle_msg, guardian, battle_participants, battle_log)
            await self.handle_defeat(ctx, party_members, attacker_team, defender_team, battle_participants)
        
        # Set cooldown for team battles

    
    async def create_battle_embed(self, guardian, battle_participants, battle_log):
        """Create the initial battle embed with stats and log"""
        embed = discord.Embed(
            title=f"🐉 Battle Against {guardian['name']}",
            color=discord.Color.red()
        )
        
        # Guardian HP
        hp_bar = self.create_hp_bar(guardian["hp"], guardian["max_hp"])
        
        # Gather guardian status effects
        status_effects = []
        for buff in guardian.get("buffs", []):
            status_effects.append(f"🟢 {buff['name']}")
        for debuff in guardian.get("debuffs", []):
            status_effects.append(f"🔴 {debuff['name']}")
            
        status_text = ""
        if status_effects:
            status_text = " | " + ", ".join(status_effects)
        
        embed.add_field(
            name=f"**[BOSS] {guardian['name']}**{status_text}",
            value=f"**HP:** {guardian['hp']:,.1f}/{guardian['max_hp']:,.1f}\n{hp_bar}",
            inline=False
        )
        
        # Participants
        for i, combatant in enumerate(battle_participants):
            current_hp = max(0, round(combatant["hp"], 1))
            max_hp = round(combatant["max_hp"], 1)
            hp_bar = self.create_hp_bar(current_hp, max_hp)
            
            # Gather status effects
            status_effects = []
            for buff in combatant.get("buffs", []):
                status_effects.append(f"🟢 {buff['name']}")
            for debuff in combatant.get("debuffs", []):
                status_effects.append(f"🔴 {debuff['name']}")
                
            status_text = ""
            if status_effects:
                status_text = " | " + ", ".join(status_effects)
            
            # FIXED: Display possessed players correctly
            if not combatant.get("is_pet"):
                if combatant.get("shadow_possessed", False):
                    # Special display for possessed players
                    name = f"**[{i+1}] 🕸️ POSSESSED: {combatant['user'].display_name}**{status_text}"
                    embed.add_field(
                        name=name,
                        value=f"**HP:** {current_hp:.1f}/{max_hp:.1f}\n{hp_bar}\n**ALLIED WITH {guardian['name']}**",
                        inline=False
                    )
                else:
                    name = f"**[{i+1}] {combatant['user'].display_name}**{status_text}"
                    embed.add_field(
                        name=name,
                        value=f"**HP:** {current_hp:.1f}/{max_hp:.1f}\n{hp_bar}",
                        inline=False
                    )
            else:
                name = f"**[{i+1}] {combatant['pet_name']} (Pet)**{status_text}"
                embed.add_field(
                    name=name,
                    value=f"**HP:** {current_hp:.1f}/{max_hp:.1f}\n{hp_bar}",
                    inline=False
                )
        
        # Add last 6 battle log entries
        last_logs = list(battle_log)[-6:]
        log_text = "\n\n".join(last_logs)
        embed.add_field(name="**Battle Log**", value=log_text, inline=False)
        
        return embed
    
    async def update_battle_embed(self, battle_msg, guardian, battle_participants, battle_log):
        """Update the battle embed with the latest stats and battle log"""
        embed = await self.create_battle_embed(guardian, battle_participants, battle_log)
        
        try:
            await battle_msg.edit(embed=embed)
        except:
            pass
    
    def create_hp_bar(self, current_hp, max_hp, length=20):
        """Create a visual HP bar"""
        ratio = max(0, min(1, current_hp / max_hp))
        filled = int(length * ratio)
        bar = "█" * filled + "░" * (length - filled)
        return bar
    
    async def get_player_stats(self, player, conn):
        """Get player stats from database"""
        player_id = player.id
        
        try:
            # Get basic stats
            query = 'SELECT class, xp, luck, health, stathp FROM profile WHERE "user" = $1;'
            result = await conn.fetchrow(query, player_id)
            
            if result:
                # Get level from XP
                xp = float(result["xp"])
                level = rpgtools.xptolevel(xp)
                
                # Get base health and stat HP
                base_health = 200
                health = self.ensure_float(result['health']) + base_health
                stathp = self.ensure_float(result['stathp']) * 50
                
                # Get raid stats
                dmg, deff = await self.bot.get_raidstats(player, conn=conn)
                
                # Convert to float if they're Decimal
                if hasattr(dmg, 'as_tuple'):  # Check if it's a Decimal
                    dmg = float(dmg)
                if hasattr(deff, 'as_tuple'):
                    deff = float(deff)
                
                # Calculate total health
                total_health = health + (level * 15) + stathp
                
                # Check for amulet bonus
                amulet_result = await conn.fetchrow(
                    'SELECT * FROM amulets WHERE user_id = $1 AND equipped = true AND type = $2',
                    player_id, 'hp'
                )
                
                if amulet_result and amulet_result["hp"]:
                    total_health += float(amulet_result["hp"])
                
                return {
                    "hp": float(total_health),
                    "max_hp": float(total_health),
                    "damage": float(dmg),
                    "armor": float(deff)
                }
            else:
                # Return default stats
                return {
                    "hp": 500.0,
                    "max_hp": 500.0,
                    "damage": 50.0,
                    "armor": 50.0
                }
        except Exception as e:
            print(f"Error getting player stats: {e}")
            # Return default stats
            return {
                "hp": 500.0,
                "max_hp": 500.0,
                "damage": 50.0,
                "armor": 50.0
            }
    
    async def handle_victory(self, ctx, party_members, attacker_team, defender_team):
        """Handle rewards for winning a guardian battle and update placement/leaderboard"""
        self.ongoing_team_battles.discard(attacker_team)
        team_data = self.teams[attacker_team]
        defender_data = self.teams[defender_team]
        defeated_guardian = defender_data["guardian"]["name"]
        
        # Update team stats
        team_data["victories"] += 1
        defender_data["defeats"] += 1
        
        # Mark guardian as defeated (no respawn)
        defender_data["guardian"]["defeated"] = True

        # Update HP in leaderboard tracking for all guardians
        for tname, tdata in self.teams.items():
            g = tdata["guardian"]
            self.current_hp[f"guardian_{tname}"] = g.get("hp", g["base_hp"])

        # Placement logic: only add attacker if not already placed
        if attacker_team not in self.placement_order:
            self.placement_order.append(attacker_team)
        # If only one team left, add them as last place
        undefeated_teams = [t for t, d in self.teams.items() if not d["guardian"]["defeated"]]
        if len(undefeated_teams) == 1 and undefeated_teams[0] not in self.placement_order:
            self.placement_order.append(undefeated_teams[0])

        # Update the leaderboard embed after every victory
        await self.update_leaderboard_embed(ctx.guild)

        # Check for end of event (all but one guardian defeated)
        undefeated_teams = [team for team, data in self.teams.items() if not data["guardian"]["defeated"]]
        if len(undefeated_teams) == 1:
            # Gather leaderboard order (reuse leaderboard logic)
            team_metrics = []
            for team_name, team_data in self.teams.items():
                guardian_power = (
                    team_data["guardian"]["base_hp"] * (1 + (team_data["upgrades"]["hp_boost"] * 0.05) + (team_data["customization"]["points_allocated"]["hp"] * 0.05)) +
                    team_data["guardian"]["base_attack"] * (1 + (team_data["upgrades"]["attack_boost"] * 0.05) + (team_data["customization"]["points_allocated"]["attack"] * 0.05)) +
                    team_data["guardian"]["base_defense"] * (1 + (team_data["upgrades"]["defense_boost"] * 0.05) + (team_data["customization"]["points_allocated"]["defense"] * 0.05))
                )
                defeated_teams = sum(1 for other_team, other_data in self.teams.items()
                                    if other_team != team_name and other_data["guardian"]["defeated"] == True)
                team_metrics.append({
                    "name": team_name,
                    "members": len(team_data["members"]),
                    "eggs": team_data["eggs_collected"],
                    "power": guardian_power,
                    "victories": team_data["victories"],
                    "defeats": team_data["defeats"],
                    "color": team_data["color"],
                    "emoji": team_data["emoji"],
                    "guardian_defeated": team_data["guardian"]["defeated"],
                    "defeated_teams": defeated_teams
                })
            team_metrics.sort(key=lambda x: (not x["guardian_defeated"], x["defeated_teams"], x["victories"], x["eggs"]), reverse=True)
            # Announce winners
            announcement_channel = getattr(self, "announcement_channel_id", None)
            if announcement_channel:
                channel = self.bot.get_channel(announcement_channel)
                if channel:
                    winner = team_metrics[0]
                    second = team_metrics[1] if len(team_metrics) > 1 else None
                    third = team_metrics[2] if len(team_metrics) > 2 else None
                    winner_mentions = ', '.join(f'<@{uid}>' for uid in self.teams[winner["name"]]["members"])
                    embed = discord.Embed(
                        title="🏆 Easter Egg Guardian Trials - Final Results! 🏆",
                        description=f"The event has ended! Here are the top teams:",
                        color=winner["color"]
                    )
                    embed.add_field(
                        name=f"🥇 1st Place: {winner['emoji']} {winner['name']}",
                        value=f"Members: {winner_mentions}\nEggs: {winner['eggs']}\nVictories: {winner['victories']}\nGuardian Power: {winner['power']:.0f}",
                        inline=False
                    )
                    if second:
                        embed.add_field(
                            name=f"🥈 2nd Place: {second['emoji']} {second['name']}",
                            value=f"Eggs: {second['eggs']}\nVictories: {second['victories']}\nGuardian Power: {second['power']:.0f}",
                            inline=False
                        )
                    if third:
                        embed.add_field(
                            name=f"🥉 3rd Place: {third['emoji']} {third['name']}",
                            value=f"Eggs: {third['eggs']}\nVictories: {third['victories']}\nGuardian Power: {third['power']:.0f}",
                            inline=False
                        )
                    embed.set_footer(text="Congratulations to all participants!")
                    await channel.send("@everyone", embed=embed)
                    # Optionally: Give extra rewards to winner(s) here (custom logic can be added)
        
        # Award gold to participants
        gold_reward = random.randint(5000, 250000)
        
        async with self.bot.pool.acquire() as conn:
            for member in party_members:
                await conn.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    gold_reward, member.id
                )
                
                # Log transaction
                await self.bot.log_transaction(
                    ctx,
                    from_=1,
                    to=member.id,
                    subject="Easter Guardian Victory",
                    data={"Gold": gold_reward},
                    conn=conn
                )
        
        # Award eggs to team
        egg_reward = random.randint(150, 300)
        team_data["eggs_collected"] += egg_reward

        # Chance for special item rewards
        special_rewards = []
        
        # Create egg-themed items for each team
        item_themes = {
            "Dawn Protectors": {
                "prefixes": ["Radiant", "Solar", "Golden", "Sunrise"],
                "names": ["Dawn Scepter", "Solara's Blessing", "Radiant Egg Shield", "Sun Hare's"],
                "types": ["sword", "shield", "bow", "wand"]
            },
            "Twilight Keepers": {
                "prefixes": ["Umbra's", "Twilight", "Umbral", "Midnight"],
                "names": ["Shadow Drake Fang", "Eclipse Shield", "Void Egg", "Umbra's Talon"],
                "types": ["dagger", "shield", "wand", "scythe"]
            },
            "Bloom Wardens": {
                "prefixes": ["Verdant", "Flowering", "Thorned", "Pastel"],
                "names": ["Bloom Serpent Scale", "Floral Aegis", "Spring Egg", "Thorne's Fang"],
                "types": ["sword", "shield", "wand", "spear"]
            }
        }
        
        reward_chance = 0.2  # Default chance
        if attacker_team in self.placement_order:
            place = self.placement_order.index(attacker_team) + 1  # Convert to 1-indexed
            if place == 1:
                reward_chance = 0.8  # 80% chance for 1st place
            elif place == 2:
                reward_chance = 0.8  # 50% chance for 2nd place

        # Find which players get items
        for member_id in self.teams[attacker_team]["members"]:
            if random.random() < reward_chance:  # Adjusted chance based on placement
                special_rewards.append(member_id)
        
        # Create the special items
        async with self.bot.pool.acquire() as conn:
            for player_id in special_rewards:
                # Select random item properties based on team theme
                theme = item_themes.get(attacker_team, item_themes["Dawn Protectors"])
                
                prefix = random.choice(theme["prefixes"])
                name_base = random.choice(theme["names"])
                item_type = random.choice(theme["types"])
                item_name = f"{prefix} {name_base}"
                
                # Determine hand based on item type
                if item_type in ["bow", "staff", "scythe"]:
                    hand = "both"
                elif item_type in ["shield"]:
                    hand = "left"
                else:  # sword, dagger, wand, spear
                    hand = "any"
                
                # Set damage or armor based on item type
                damage = 0.0
                armor = 0.0
                
                min_stat = 70
                max_stat = 101
                
                if item_type == "shield":
                    armor = round(random.uniform(min_stat, max_stat))
                else:
                    damage = round(random.uniform(min_stat, max_stat))
                    
                # Create the item - using your bot's actual item creation method
                try:
                    player = ctx.guild.get_member(player_id)
                    await self.bot.create_item(
                        name=_(item_name),
                        value=10000,
                        type_=item_type.capitalize(),
                        element="light" if attacker_team == "Dawn Protectors" else 
                               "dark" if attacker_team == "Twilight Keepers" else "earth",
                        damage=damage,
                        armor=armor,
                        owner=player,
                        hand=hand,
                        equipped=False,
                        conn=conn,
                    )
                except Exception as e:
                    print(f"Error creating item: {e}")
        
        # Create embed for rewards
        embed = discord.Embed(
            title=f"Victory Against {defeated_guardian}!",
            description=_(
                f"Your team has defeated the {defender_team}'s guardian!\n\n"
                f"**Team Reward:** {egg_reward} eggs added to the {attacker_team}\n"
                f"**Individual Rewards:** {gold_reward} gold for each participant\n\n"
                f"**The {defender_team}'s guardian has been defeated! They are out of the competition!**"
            ),
            color=team_data["color"]
        )
        
        # Add special reward info if any
        if special_rewards:
            spec_rewards_text = "\n".join([f"• {ctx.guild.get_member(player_id).mention}" for player_id in special_rewards])
            embed.add_field(
                name="Special Rewards",
                value=f"The following players found special easter-themed items:\n{spec_rewards_text}",
                inline=False
            )
            
        await ctx.send(embed=embed)
        
        # Post victory announcement in team channels
        try:
            # Attacker team channel (victors)
            victory_channel = self.bot.get_channel(team_data["channel_id"])
            if victory_channel:
                victory_embed = discord.Embed(
                    title="🏆 GUARDIAN VICTORY! 🏆",
                    description=_(
                        f"Our team has defeated the {defender_team}'s guardian **{defeated_guardian}**!\n\n"
                        f"**Team Reward:** {egg_reward} eggs\n"
                        f"**Individual Rewards:** {gold_reward} gold for each participant\n\n"
                        f"The {defender_team} is now out of the competition!"
                    ),
                    color=team_data["color"]
                )
                await victory_channel.send("@everyone", embed=victory_embed)
                
            # Defender team channel (defeated)
            defeated_channel = self.bot.get_channel(defender_data["channel_id"])
            if defeated_channel:
                defeat_embed = discord.Embed(
                    title="⚠️ GUARDIAN DEFEATED! ⚠️",
                    description=_(
                        f"Our guardian **{defeated_guardian}** has been defeated by the {attacker_team}!\n\n"
                        f"Our team is now out of the main competition, but you can still collect eggs and upgrade your guardian for pride and special rewards."
                    ),
                    color=defender_data["color"]
                )
                await defeated_channel.send("@everyone", embed=defeat_embed)
        except Exception as e:
            print(f"Error sending team victory messages: {e}")
        
        # Post in announcement channel
        try:
            announcement_channel = self.bot.get_channel(self.announcement_channel_id)
            if announcement_channel:
                announcement_embed = discord.Embed(
                    title=f"🏆 GUARDIAN DEFEATED! 🏆",
                    description=_(
                        f"The {attacker_team} has defeated the {defender_team}'s guardian **{defeated_guardian}**!\n\n"
                        f"**Team Leader:** {ctx.author.mention}\n"
                        f"**Raid Party Size:** {len(party_members)} champions\n\n"
                        f"The {defender_team} is now out of the competition!"
                    ),
                    color=team_data["color"]
                )
                
                # Add party members
                members_text = ""
                for i, member in enumerate(party_members):
                    members_text += f"{i+1}. {member.mention}\n"
                    
                announcement_embed.add_field(
                    name="Victorious Champions",
                    value=members_text,
                    inline=False
                )
                
                # Add current standings
                team_metrics = []
                for team_name, team_data in self.teams.items():
                    team_metrics.append({
                        "name": team_name,
                        "guardian_defeated": team_data["guardian"]["defeated"]
                    })
                    
                standings_text = ""
                for team in team_metrics:
                    status = "🔴 DEFEATED" if team["guardian_defeated"] else "🟢 ACTIVE"
                    standings_text += f"**{team['name']}**: {status}\n"
                    
                announcement_embed.add_field(
                    name="Current Standings",
                    value=standings_text,
                    inline=False
                )
                
                await announcement_channel.send(embed=announcement_embed)
        except Exception as e:
            channel2 = self.bot.get_channel(1362758651047182578)
            await channel2.send(f"Error updating leaderboard embed: {e}")
    
    async def update_leaderboard_embed(self, guild):
        """Update or create the live leaderboard embed in the announcement channel."""
        channel = self.bot.get_channel(self.announcement_channel_id)
        if channel is None:
            return
        
        debug_channel = self.bot.get_channel(1362758651047182578)  # Keep your debug channel
        
        try:
            # First, sync guardian HP values from battle stats
            for team_name in self.teams:
                # For each defending team, find their current HP in battles
                defending_battles = [k for k in self.current_hp.keys() if '_' in k and k.split('_')[1] == team_name]
                for battle_key in defending_battles:
                    if battle_key in self.current_hp:
                        # Update the guardian HP to match battle HP
                        self.current_hp[f"guardian_{team_name}"] = self.current_hp[battle_key]
                        
                # Debug information
                await debug_channel.send(f"Updated {team_name} guardian HP: {self.current_hp.get(f'guardian_{team_name}', 'Not found')}")
            
            # Build the leaderboard embed
            embed = discord.Embed(
                title="🏆 Guardian Race Leaderboard",
                description="Live standings for the Easter Egg Guardian Trials!",
                color=discord.Color.gold()
            )
            
            placement_emojis = ["🥇", "🥈", "🥉"]
            for idx, team_name in enumerate(self.teams):
                team = self.teams[team_name]
                guardian = team["guardian"]
                
                # Get the current HP (prefer guardian-specific key, fallback to base_hp)
                hp = self.current_hp.get(f"guardian_{team_name}", guardian["base_hp"])
                max_hp = guardian["base_hp"]
                
                # If guardian is defeated, show 0 HP
                if guardian["defeated"]:
                    hp = 0
                    
                hp_bar = self.create_hp_bar(hp, max_hp)
                
                # Determine placement display
                placement = ""
                if team_name in self.placement_order:
                    place_index = self.placement_order.index(team_name)
                    emoji = placement_emojis[place_index] if place_index < len(placement_emojis) else "🏅"
                    placement = f"{emoji} {place_index+1} Place"
                else:
                    placement = "Racing..."
                    
                status = "🔴 Defeated" if guardian["defeated"] else "🟢 Active"
                
                # Format the field with HP and other stats
                embed.add_field(
                    name=f"{team['emoji']} {guardian['name']} ({team_name})",
                    value=(
                        f"HP: {hp_bar} {hp:,.0f}/{max_hp:,.0f}\n"
                        f"Defeated Combatants: {guardian.get('kills', 0)}\n"
                        f"Status: {status}\n"
                        f"Placement: {placement}"
                    ),
                    inline=False
                )
            
            # Update or send the leaderboard message
            if self.leaderboard_message_id:
                try:
                    msg = await channel.fetch_message(self.leaderboard_message_id)
                    await msg.edit(embed=embed)
                    await debug_channel.send("Successfully updated leaderboard message")
                except Exception as e:
                    await debug_channel.send(f"Error updating leaderboard embed: {e}")
                    # Try deleting the old message and posting a new one
                    try:
                        msg = await channel.fetch_message(self.leaderboard_message_id)
                        await msg.delete()
                    except Exception as delete_e:
                        await debug_channel.send(f"Could not delete old leaderboard embed: {delete_e}")
                    
                    # Create a new message
                    msg = await channel.send(embed=embed)
                    self.leaderboard_message_id = msg.id
                    await debug_channel.send(f"Created new leaderboard message ID: {self.leaderboard_message_id}")
            else:
                msg = await channel.send(embed=embed)
                self.leaderboard_message_id = msg.id
                await debug_channel.send(f"Created initial leaderboard message ID: {self.leaderboard_message_id}")
                
        except Exception as e:
            await debug_channel.send(f"Error in update_leaderboard_embed: {e}")
            import traceback
            await debug_channel.send(f"```{traceback.format_exc()}```")
            


    async def announce_final_standings(self, guild):
        channel = self.bot.get_channel(self.announcement_channel_id)
        if channel is None:
            return
        placement_emojis = ["🥇", "🥈", "🥉"]
        embed = discord.Embed(
            title="🏆 Guardian Race Results! 🏆",
            description="The race is over! Here are the final placements:",
            color=discord.Color.gold()
        )
        for idx, team_name in enumerate(self.placement_order):
            team = self.teams[team_name]
            guardian = team["guardian"]
            embed.add_field(
                name=f"{placement_emojis[idx]} {team['emoji']} {guardian['name']} ({team_name})",
                value=(
                    f"W/L: {team['victories']}W - {team['defeats']}L\n"
                    f"Final HP: {self.current_hp.get(f'guardian_{team_name}', guardian['base_hp']):,.0f}\n"
                ),
                inline=False
            )
        await channel.send(embed=embed)

    async def handle_defeat(self, ctx, party_members, attacker_team, defender_team, battle_participants=None):
        """Handle consequences of losing a guardian battle"""
        self.ongoing_team_battles.discard(attacker_team)
        team_data = self.teams[attacker_team]
        guardian = self.teams[defender_team]["guardian"]["name"]
        
        # Update HP in leaderboard tracking for all guardians
        for tname, tdata in self.teams.items():
            g = tdata["guardian"]
            self.current_hp[f"guardian_{tname}"] = g.get("hp", g["base_hp"])

        # Update team stats
        team_data["defeats"] += 1
        
        # Small consolation prize
        egg_reward = random.randint(20, 50)
        team_data["eggs_collected"] += egg_reward
        
        # Small gold consolation
        consolation_gold = random.randint(1000, 2000)
        
        async with self.bot.pool.acquire() as conn:
            for member in party_members:
                await conn.execute(
                    'UPDATE profile SET "money"="money"+$1 WHERE "user"=$2;',
                    consolation_gold, member.id
                )
        
        embed = discord.Embed(
            title=f"Defeat Against {guardian}",
            description=_(
                f"Your team was defeated by the {defender_team}'s guardian!\n\n"
                f"**Consolation Reward:** {egg_reward} eggs added to the {attacker_team}\n"
                f"**Gold Consolation:** {consolation_gold} gold for each participant\n\n"
                f"Better luck next time! Try upgrading your guardian or unlocking more abilities."
            ),
            color=team_data["color"]
        )
        
        # Add mention of possession if any players were possessed
        if battle_participants:
            possessed_count = sum(1 for p in battle_participants if p.get("shadow_possessed", False))
            if possessed_count > 0:
                embed.description += f"\n\n{possessed_count} of your team members were possessed by the Shadow Realm and turned against you!"
        
        # Only send one embed: send to team channel if possible and not duplicate, else to ctx
        sent = False
        try:
            team_channel = self.bot.get_channel(team_data["channel_id"])
            if team_channel and (not hasattr(ctx, 'channel') or ctx.channel.id != team_channel.id):
                await team_channel.send(embed=embed)
                sent = True
        except Exception as e:
            channel2 = self.bot.get_channel(1362758651047182578)
            await channel2.send(f"Error updating leaderboard embed: {e}")
        if not sent:
            await ctx.send(embed=embed)
            await self.update_leaderboard_embed(ctx.guild)

class JoinBattleView(discord.ui.View):
    def __init__(self, ctx, embed, party_members, cog, attacker_team, defender_team):
        super().__init__(timeout=60.0)
        self.ctx = ctx
        self.embed = embed
        self.party_members = party_members
        self.leader = ctx.author
        self.message = None
        self.cog = cog
        self.attacker_team = attacker_team
        self.defender_team = defender_team
        self.battle_started = False
    
    async def on_timeout(self):
        if not self.battle_started:
            for child in self.children:
                child.disabled = True
            # Clean up ongoing battle lock for this team
            self.cog.ongoing_team_battles.discard(self.attacker_team)
            try:
                await self.message.edit(content="Party formation timed out!", view=self)
                await self.cog.bot.reset_cooldown(self.ctx)
                
                # Remove players from battle formation tracking
                for member in self.party_members:
                    if member.id in self.cog.players_in_battle_formation:
                        self.cog.players_in_battle_formation.remove(member.id)
                        
            except:
                pass
    
    async def update_embed(self):
        member_count = len(self.party_members)
        members_text = "\n".join([f"{i+1}. {member.mention}" for i, member in enumerate(self.party_members)])
        self.embed.clear_fields()
        self.embed.add_field(name="Party Members", value=members_text, inline=False)
        await self.message.edit(embed=self.embed, view=self)
    
    @discord.ui.button(emoji="✅", style=discord.ButtonStyle.success, label="Join")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in self.party_members:
            await interaction.response.send_message("You are already in the party!", ephemeral=True)
            return
        
        # Check if player is already in another battle formation
        if interaction.user.id in self.cog.players_in_battle_formation:
            await interaction.response.send_message("You are already forming or participating in another battle!", ephemeral=True)
            return
        
        # Check if player is on the same team
        player_team = self.cog.get_player_team(interaction.user.id)
        if player_team != self.attacker_team:
            await interaction.response.send_message(f"You must be a member of the {self.attacker_team} to join this battle!", ephemeral=True)
            return
        
        # Check if player is on battle cooldown
        if interaction.user.id in self.cog.player_battle_cooldowns:
            if datetime.utcnow() < self.cog.player_battle_cooldowns[interaction.user.id]:
                time_left = self.cog.player_battle_cooldowns[interaction.user.id] - datetime.utcnow()
                hours, remainder = divmod(time_left.total_seconds(), 3600)
                minutes, seconds = divmod(remainder, 60)
                await interaction.response.send_message(
                    f"You're still exhausted from your last battle! You can battle again in **{int(hours)}h {int(minutes)}m**.",
                    ephemeral=True
                )
                return
        
        if len(self.party_members) >= 10:
            await interaction.response.send_message("The party is already full!", ephemeral=True)
            return
        
        # Add player to battle formation tracking
        self.cog.players_in_battle_formation.add(interaction.user.id)
        
        self.party_members.append(interaction.user)
        await self.update_embed()
        await interaction.response.send_message(f"You joined the battle party!", ephemeral=True)


    @discord.ui.button(emoji="❌", style=discord.ButtonStyle.danger, label="Leave")
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user not in self.party_members:
            await interaction.response.send_message("You are not in the party!", ephemeral=True)
            return
        
        
        # Check if player is on the same team
        player_team = self.cog.get_player_team(interaction.user.id)


        # Add player to battle formation tracking
        try:
            self.cog.players_in_battle_formation.discard(interaction.user.id)
        except Exception as e:
         print(e)
        self.party_members.remove(interaction.user)
        await self.update_embed()
        await interaction.response.send_message(f"You have left the battle party!", ephemeral=True)
    
    @discord.ui.button(emoji="⚔️", style=discord.ButtonStyle.primary, label="Start Battle")
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.leader:
            await interaction.response.send_message("Only the party leader can start the battle!", ephemeral=True)
            return
        
        if len(self.party_members) < 1:
            await interaction.response.send_message("You need at least one person to start the battle!", ephemeral=True)
            return
        
        # Set flag and disable buttons
        self.battle_started = True
        for child in self.children:
            child.disabled = True
        
        await interaction.response.edit_message(view=self)
        
        try:
            # Start the battle
            await self.cog.start_guardian_battle(self.ctx, self.party_members, self.attacker_team, self.defender_team)
        except Exception as e:
            import traceback
            error_message = f"Error while starting the battle: {e}\n{traceback.format_exc()}"
            await self.ctx.send(error_message)
            
            # Clean up battle formation tracking on error
            for member in self.party_members:
                if member.id in self.cog.players_in_battle_formation:
                    self.cog.players_in_battle_formation.remove(member.id)

class AbilityVoteView(discord.ui.View):
    def __init__(self, cog, player_id, team, abilities):
        super().__init__(timeout=30.0)
        self.cog = cog
        self.player_id = player_id
        self.team = team
        self.abilities = abilities
        
        # Add buttons for each ability
        for i, ability in enumerate(abilities):
            button = discord.ui.Button(
                label=f"{i+1}. {ability['name']}", 
                style=discord.ButtonStyle.primary,
                custom_id=f"ability_{i}"
            )
            button.callback = self.make_callback(ability["name"])
            self.add_item(button)
    
    def make_callback(self, ability_name):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.player_id:
                return await interaction.response.send_message("This is not your vote selection!", ephemeral=True)
            
            # Check if team has recently unlocked an ability
            if self.team in self.cog.team_ability_unlocked:
                if datetime.utcnow() < self.cog.team_ability_unlocked[self.team]:
                    time_left = self.cog.team_ability_unlocked[self.team] - datetime.utcnow()
                    hours, remainder = divmod(time_left.total_seconds(), 3600)
                    minutes, seconds = divmod(remainder, 60)
                    return await interaction.response.send_message(
                        f"Your team recently unlocked a new ability! "
                        f"You can vote for another in **{int(hours)}h {int(minutes)}m**.",
                        ephemeral=True
                    )
            
            # Add vote to the ability
            team_data = self.cog.teams[self.team]
            if ability_name not in team_data["upgrades"]["ability_votes"]:
                team_data["upgrades"]["ability_votes"][ability_name] = 0
            
            team_data["upgrades"]["ability_votes"][ability_name] += 1
            
            # Check if ability reached 5 votes to unlock
            if team_data["upgrades"]["ability_votes"][ability_name] >= 5:
                # Unlock the ability
                for ability in team_data["guardian"]["abilities"]:
                    if ability["name"] == ability_name:
                        ability["unlocked"] = True
                        break
                
                # Reset votes for this ability
                team_data["upgrades"]["ability_votes"][ability_name] = 0
                
                # Set 24 hour cooldown for team ability voting
                self.cog.team_ability_unlocked[self.team] = datetime.utcnow() + timedelta(hours=24)
                
                await interaction.response.send_message(
                    f"🎉 Your vote was the 5th vote needed to unlock **{ability_name}**!\n"
                    f"This ability has been added to your guardian's arsenal!\n\n"
                    f"Your team will need to wait 24 hours before voting for another ability."
                )
                
                # Post in team channel
                try:
                    team_channel = self.cog.bot.get_channel(team_data["channel_id"])
                    if team_channel:
                        ability_embed = discord.Embed(
                            title="New Guardian Ability Unlocked!",
                            description=_(
                                f"Our guardian has learned a new ability: **{ability_name}**!\n\n"
                                f"This ability is now available in guardian battles.\n\n"
                                f"There is a 24-hour cooldown before we can vote for another ability."
                            ),
                            color=team_data["color"]
                        )
                        await team_channel.send("@everyone", embed=ability_embed)
                except Exception as e:
                    print(f"Error sending ability unlock message: {e}")
            else:
                votes_needed = 5 - team_data["upgrades"]["ability_votes"][ability_name]
                await interaction.response.send_message(
                    f"You voted for **{ability_name}**!\n"
                    f"This ability now has {team_data['upgrades']['ability_votes'][ability_name]} votes. "
                    f"{votes_needed} more needed to unlock it."
                )
                
                # Post vote update in team channel
                try:
                    team_channel = self.cog.bot.get_channel(team_data["channel_id"])
                    if team_channel:
                        vote_embed = discord.Embed(
                            title="Ability Vote Update",
                            description=_(
                                f"{interaction.user.mention} voted for **{ability_name}**\n\n"
                                f"Current votes: {team_data['upgrades']['ability_votes'][ability_name]}/5\n"
                                f"Votes needed: {votes_needed}"
                            ),
                            color=team_data["color"]
                        )
                        await team_channel.send(embed=vote_embed)
                except Exception as e:
                    print(f"Error sending vote update: {e}")
            
            # Set player vote cooldown (1 day)
            self.cog.player_vote_cooldowns[interaction.user.id] = datetime.utcnow() + timedelta(days=1)
            
            # Disable all buttons after voting
            for child in self.children:
                child.disabled = True
            
            await interaction.message.edit(view=self)
        
        return callback

async def setup(bot):
    await bot.add_cog(Easter(bot))