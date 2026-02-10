# battles/factory.py
import random
from decimal import Decimal
import asyncio

from .core.battle import Battle
from .core.combatant import Combatant
from .core.team import Team
from .types.pve import PvEBattle
from .types.pvp import PvPBattle
from .types.raid import RaidBattle
from .types.tower import TowerBattle
from .types.team_battle import TeamBattle
from .types.dragon import DragonBattle
from .types.couples_tower import CouplesTowerBattle
from .types.brawl import BrawlBattle
from .extensions.elements import ElementExtension
from .extensions.classes import ClassBuffExtension
from .extensions.pets import PetExtension
from .extensions.dragon import DragonExtension
from .settings import BattleSettings

class BattleFactory:
    """Factory for creating various battle types"""
    
    def __init__(self, bot):
        self.bot = bot
        self.element_ext = ElementExtension()
        self.class_ext = ClassBuffExtension()
        self.pet_ext = PetExtension()
        self.dragon_ext = DragonExtension()
        self.settings = BattleSettings(bot)
        
    async def initialize(self):
        """Initialize the battle factory and its components"""
        await self.settings.initialize()
    
    async def create_battle(self, battle_type, ctx, **kwargs):
        """Create a battle of specified type with given parameters"""
        # Apply battle settings to kwargs
        settings_kwargs = await self.settings.apply_settings_to_battle(battle_type, kwargs)
        
        if battle_type == "pvp":
            return await self.create_pvp_battle(ctx, **settings_kwargs)
        elif battle_type == "pve":
            return await self.create_pve_battle(ctx, **settings_kwargs)
        elif battle_type == "raid":
            return await self.create_raid_battle(ctx, **settings_kwargs)
        elif battle_type == "tower":
            return await self.create_tower_battle(ctx, **settings_kwargs)
        elif battle_type == "team":
            return await self.create_team_battle(ctx, **settings_kwargs)
        elif battle_type == "dragon":
            return await self.create_dragon_battle(ctx, **settings_kwargs)
        elif battle_type == "couples_tower":
            return await self.create_couples_tower_battle(ctx, **settings_kwargs)
        elif battle_type == "brawl":
            return await self.create_brawl_battle(ctx, **settings_kwargs)
        else:
            raise ValueError(f"Unknown battle type: {battle_type}")
    
    async def create_pvp_battle(self, ctx, **kwargs):
        """Create a standard PvP battle"""
        player1 = kwargs.get("player1", ctx.author)
        player2 = kwargs.get("player2")
        money = kwargs.get("money", 0)
        simple = kwargs.get("simple", False)
        
        if not player2:
            raise ValueError("PvP battle requires two players")
        
        # Create combatants for both players
        p1_combatant = await self.create_player_combatant(ctx, player1)
        p2_combatant = await self.create_player_combatant(ctx, player2)
        
        # Create teams
        team1 = Team("A", [p1_combatant])
        team2 = Team("B", [p2_combatant])
        
        # For simple battles, get damage/armor stats
        if simple:
            player1_stats = await self.bot.get_damage_armor_for(player1)
            player2_stats = await self.bot.get_damage_armor_for(player2)
            kwargs["player1_stats"] = player1_stats
            kwargs["player2_stats"] = player2_stats
        
        # Create and return the battle
        return PvPBattle(ctx, [team1, team2], money=money, **kwargs)
    
    async def create_pve_battle(self, ctx, **kwargs):
        """Create a PvE battle against a monster"""
        player = kwargs.get("player", ctx.author)
        monster_level = kwargs.get("monster_level")
        monster_data = kwargs.get("monster_data")
        monster_override = kwargs.get("monster_override")
        levelchoice_override = kwargs.get("levelchoice_override")
        macro_penalty_level = kwargs.get("macro_penalty_level", 0)
        allow_pets = kwargs.get("allow_pets")  # Get allow_pets from settings system
        
        # Handle overrides
        if monster_override:
            monster_data = monster_override
            monster_level = levelchoice_override or 1
        
        # Create player combatant - only include_pet when allow_pets is true
        player_combatant = await self.create_player_combatant(ctx, player, include_pet=allow_pets)
        
        # Only get pet combatant if pets are allowed
        pet_combatant = None
        if allow_pets:
            pet_combatant = await self.pet_ext.get_pet_combatant(ctx, player)
        
        # Create monster combatant
        if monster_data:
            monster_combatant = await self.create_monster_combatant(monster_data, level=monster_level)
        else:
            # Generate random monster based on level
            from utils import misc as rpgtools
            player_xp = ctx.character_data.get("xp", 0)
            player_level = rpgtools.xptolevel(player_xp)
            
            if monster_level is None:
                # Determine monster level based on player level
                if player_level <= 4:
                    monster_level = random.randint(1, 2)
                elif player_level <= 8:
                    monster_level = random.randint(1, 3)
                elif player_level <= 12:
                    monster_level = random.randint(1, 4)
                elif player_level <= 15:
                    monster_level = random.randint(1, 5)
                elif player_level <= 20:
                    monster_level = random.randint(1, 6)
                elif player_level <= 25:
                    monster_level = random.randint(1, 7)
                elif player_level <= 30:
                    monster_level = random.randint(1, 8)
                elif player_level <= 35:
                    monster_level = random.randint(1, 9)
                elif player_level <= 40:
                    monster_level = random.randint(1, 10)
                else:  # player_level > 40
                    monster_level = random.randint(1, 10)
            
            monster_data = await self.generate_monster(ctx, monster_level)
            monster_combatant = await self.create_monster_combatant(monster_data, level=monster_level)
        
        # Create teams
        player_team = Team("Player", [player_combatant])
        if pet_combatant and allow_pets:
            player_team.add_combatant(pet_combatant)
            
        monster_team = Team("Monster", [monster_combatant])
        
        # Create and return the battle
        kwargs_copy = kwargs.copy()
        if 'monster_level' in kwargs_copy:
            del kwargs_copy['monster_level']
        if 'macro_penalty_level' in kwargs_copy:
            del kwargs_copy['macro_penalty_level']
        return PvEBattle(ctx, [player_team, monster_team], monster_level=monster_level, macro_penalty_level=macro_penalty_level, **kwargs_copy)
    
    async def create_raid_battle(self, ctx, **kwargs):
        """Create a raid battle with player and pet vs enemy and pet"""
        player1 = kwargs.get("player1", ctx.author)
        player2 = kwargs.get("player2")
        money = kwargs.get("money", 0)
        
        # Get allow_pets setting
        allow_pets = kwargs.get("allow_pets")
        
        # Create player combatant - only include_pet when allow_pets is true
        player1_combatant = await self.create_player_combatant(ctx, player1, include_pet=allow_pets)
        
        # Only get pet combatant if pets are allowed
        player1_pet = None
        if allow_pets:
            player1_pet = await self.pet_ext.get_pet_combatant(ctx, player1)
        
        # Create enemy combatant and pet if specified, or random opponent
        if player2:
            player2_combatant = await self.create_player_combatant(ctx, player2, include_pet=allow_pets)
            player2_pet = None
            if allow_pets:
                player2_pet = await self.pet_ext.get_pet_combatant(ctx, player2)
        else:
            # For random opponents, respect the allow_pets setting
            player2_combatant, player2_pet = await self.find_random_opponent(ctx, player1)
            if not allow_pets:
                player2_pet = None
        
        # Create teams
        player1_team = Team("A", [player1_combatant])
        if player1_pet:
            player1_team.add_combatant(player1_pet)
            
        player2_team = Team("B", [player2_combatant])
        if player2_pet:
            player2_team.add_combatant(player2_pet)
        
        # Create and return the battle
        battle_kwargs = kwargs.copy()
        battle_kwargs.pop('money', None)  # Remove money if it exists
        return RaidBattle(ctx, [player1_team, player2_team], money=money, **battle_kwargs)
    
    async def create_tower_battle(self, ctx, **kwargs):
        """Create a battle tower battle for a specific level"""
        player = kwargs.get("player", ctx.author)
        level = kwargs.get("level", 1)
        level_data = kwargs.get("level_data", {})
        
        # Get allow_pets setting
        allow_pets = kwargs.get("allow_pets")
        
        # Create player combatant - only include_pet when allow_pets is true
        player_combatant = await self.create_player_combatant(ctx, player, include_pet=allow_pets)
        
        # Only get pet combatant if pets are allowed
        pet_combatant = None
        if allow_pets:
            pet_combatant = await self.pet_ext.get_pet_combatant(ctx, player)
        
        # Apply prestige multipliers if any
        async with ctx.bot.pool.acquire() as conn:
            prestige_level = await conn.fetchval('SELECT prestige FROM battletower WHERE id = $1', player.id) or 0
        
        prestige_multiplier = 1 + (0.25 * prestige_level)
        prestige_hp_multiplier = 1 + (0.20 * prestige_level)
        
        # Create boss and minion combatants
        boss_data = level_data.get("boss", {})
        minion1_data = level_data.get("minion1", {})
        minion2_data = level_data.get("minion2", {})
        
        boss = await self.create_monster_combatant(
            {
                "name": level_data.get("boss_name", "Boss"),
                "hp": int(round(float(boss_data.get("hp", 100)) * prestige_hp_multiplier)),
                "attack": int(round(float(boss_data.get("damage", 20)) * prestige_multiplier)),
                "defense": int(round(float(boss_data.get("armor", 10)) * prestige_multiplier)),
                "element": boss_data.get("element", "Unknown")
            }
        )
        
        # For level 16, don't apply prestige multipliers to minions since they use real player stats
        minion_prestige_multiplier = 1 if level == 16 else prestige_multiplier
        minion_prestige_hp_multiplier = 1 if level == 16 else prestige_hp_multiplier
        
        minion1 = await self.create_monster_combatant(
            {
                "name": level_data.get("minion1_name", "Minion 1"),
                "hp": int(round(float(minion1_data.get("hp", 100)) * minion_prestige_hp_multiplier)),
                "attack": int(round(float(minion1_data.get("damage", 20)) * minion_prestige_multiplier)),
                "defense": int(round(float(minion1_data.get("armor", 10)) * minion_prestige_multiplier)),
                "element": minion1_data.get("element", "Unknown")
            }
        )
        
        minion2 = await self.create_monster_combatant(
            {
                "name": level_data.get("minion2_name", "Minion 2"),
                "hp": int(round(float(minion2_data.get("hp", 100)) * minion_prestige_hp_multiplier)),
                "attack": int(round(float(minion2_data.get("damage", 20)) * minion_prestige_multiplier)),
                "defense": int(round(float(minion2_data.get("armor", 10)) * minion_prestige_multiplier)),
                "element": minion2_data.get("element", "Unknown")
            }
        )
        
        # Create teams
        player_team = Team("Player", [player_combatant])
        if pet_combatant:
            player_team.add_combatant(pet_combatant)
            
        enemy_team = Team("Enemy", [minion1, minion2, boss])
        
        # Create and return the battle
        battle_kwargs = kwargs.copy()
        battle_kwargs.pop('level', None)  # Remove level if it exists
        battle_kwargs.pop('level_data', None)  # Remove level_data if it exists
        return TowerBattle(ctx, [player_team, enemy_team], level=level, level_data=level_data, **battle_kwargs)
    
    async def create_team_battle(self, ctx, **kwargs):
        """Create a battle with two teams of players"""
        teams = kwargs.get("teams", [])
        money = kwargs.get("money", 0)
        
        if not teams or len(teams) != 2:
            raise ValueError("Team battle requires exactly two teams")
        
        # Create the battle
        return TeamBattle(ctx, teams, money=money, **kwargs)
        
    async def create_dragon_battle(self, ctx, **kwargs):
        """Create an Ice Dragon challenge battle"""
        dragon_level = kwargs.get("dragon_level", None)
        party_members = kwargs.get("party_members", [ctx.author])
        
        # Get current dragon stats from database if level not specified
        if dragon_level is None:
            dragon_stats = await self.dragon_ext.get_dragon_stats_from_database(self.bot)
            dragon_level = dragon_stats.get("level", 1)
            weekly_defeats = dragon_stats.get("weekly_defeats", 0)
            kwargs["weekly_defeats"] = weekly_defeats
        
        # Create dragon team
        dragon_team = await self.dragon_ext.create_dragon_team(self.bot, dragon_level)
        
        # Create player team
        player_combatants = []
        async with self.bot.pool.acquire() as conn:
            for member in party_members:
                # Create player combatant
                player_combatant = await self.create_player_combatant(ctx, member, include_pet=True)
                player_combatants.append(player_combatant)
                
                # Add pet if available and enabled
                if kwargs.get("allow_pets"):
                    pet_combatant = await self.pet_ext.get_pet_combatant(ctx, member)
                    if pet_combatant:
                        player_combatants.append(pet_combatant)
        
        player_team = Team("Players", player_combatants)
        
        # Create and return the battle
        return DragonBattle(ctx, [dragon_team, player_team], dragon_level=dragon_level, **kwargs)
    
    async def create_couples_tower_battle(self, ctx, **kwargs):
        """Create a couples battle tower battle for a specific level"""
        try:
            player = kwargs.get("player", ctx.author)
            level = kwargs.pop("level", 1)
            game_levels = kwargs.get("game_levels")
            level_data = game_levels["levels"][level - 1] # -1 for 0-based index

            # Create player combatants
            player_team = Team("Player")
            partner1 = player
            query = "SELECT marriage FROM profile WHERE profile.user = $1"
            result = await self.bot.pool.fetchval(query, player.id)
            partner2_id = result  # This will be the marriage partner's ID, or None if not married
            partner2_user = await self.bot.fetch_user(partner2_id)

            p1_combatant = await self.create_player_combatant(ctx, partner1, include_pet=True)
            p2_combatant = await self.create_player_combatant(ctx, partner2_user, include_pet=True)
            player_team.add_combatant(p1_combatant)
            player_team.add_combatant(p2_combatant)

            # Apply prestige multipliers if any
            async with self.bot.pool.acquire() as conn:
                prestige_level = await conn.fetchval(
                    'SELECT prestige FROM couples_battle_tower WHERE (partner1_id = $1 AND partner2_id = $2) OR (partner1_id = $2 AND partner2_id = $1)', 
                    partner1.id, partner2_id
                ) or 0
            
            prestige_multiplier = 1 + (0.25 * prestige_level)
            prestige_hp_multiplier = 1 + (0.20 * prestige_level)

            # Create enemy combatants - Level 30 is a special reward level with no enemies
            enemy_team = Team("Enemies")
            if level != 30 and "enemies" in level_data:
                for enemy_info in level_data["enemies"]:
                    # Apply prestige scaling to enemy stats
                    scaled_enemy_info = {
                        "name": enemy_info.get("name"),
                        "hp": int(round(float(enemy_info.get("hp", 100)) * prestige_hp_multiplier)),
                        "attack": int(round(float(enemy_info.get("attack", 20)) * prestige_multiplier)),
                        "defense": int(round(float(enemy_info.get("defense", 10)) * prestige_multiplier)),
                        "element": enemy_info.get("element", "Unknown")
                    }
                    
                    enemy_combatant = await self.create_monster_combatant(
                        scaled_enemy_info,
                        level=level,
                        name=enemy_info.get("name")
                    )
                    enemy_team.add_combatant(enemy_combatant)
            
            return CouplesTowerBattle(ctx, [player_team, enemy_team], level=level, **kwargs)
        except Exception as e:
            import traceback
            error_msg = f"🚨 **FACTORY ERROR for Level {level}**:\n```\n{traceback.format_exc()}\n```"
            await ctx.send(error_msg[:2000])  # Discord limit
            raise e

    async def create_brawl_battle(self, ctx, **kwargs):
        """Create a 1v1 bar brawl battle with fixed stats and flavor weapons."""
        player1 = kwargs.get("player1")
        player2 = kwargs.get("player2")
        if not player1 or not player2:
            raise ValueError("Brawl battle requires two players")

        hp = int(kwargs.get("hp", 500))
        armor = int(kwargs.get("armor", 100))
        p1_weapon = kwargs.get("player1_weapon", "bar stool")
        p2_weapon = kwargs.get("player2_weapon", "pool cue")
        p1_damage = int(kwargs.get("player1_damage", 200))
        p2_damage = int(kwargs.get("player2_damage", 200))
        luck = int(kwargs.get("luck", 75))

        p1_combatant = Combatant(
            user=player1,
            hp=hp,
            max_hp=hp,
            damage=p1_damage,
            armor=armor,
            element="None",
            luck=luck,
            name=player1.display_name,
            weapon_name=p1_weapon,
        )
        p2_combatant = Combatant(
            user=player2,
            hp=hp,
            max_hp=hp,
            damage=p2_damage,
            armor=armor,
            element="None",
            luck=luck,
            name=player2.display_name,
            weapon_name=p2_weapon,
        )

        team1 = Team("A", [p1_combatant])
        team2 = Team("B", [p2_combatant])
        return BrawlBattle(ctx, [team1, team2], **kwargs)

    async def create_player_combatant(self, ctx, player, include_pet=False):
        """Create a combatant object for a player with full stats"""
        if not player:
            raise ValueError("Player cannot be None")
            
        async with ctx.bot.pool.acquire() as conn:
            # Get basic stats
            query = 'SELECT "luck", "health", "stathp", "xp", "class" FROM profile WHERE "user" = $1;'
            result = await conn.fetchrow(query, player.id)
            
            if not result:
                # Create default combatant if player not found
                return Combatant(
                    user=player,
                    hp=500,
                    max_hp=500,
                    damage=50,
                    armor=50,
                    element="Unknown",
                    luck=50
                )
            
            # Calculate level
            from utils import misc as rpgtools
            level = rpgtools.xptolevel(result["xp"])
            
            # Calculate luck
            luck_value = float(result['luck'])
            luck = 20 if luck_value <= 0.3 else ((luck_value - 0.3) / (1.5 - 0.3)) * 80 + 20
            luck = round(luck, 2)
            
            # Apply luck booster
            luck_booster = await ctx.bot.get_booster(player, "luck")
            if luck_booster:
                luck += luck * 0.25
                luck = min(luck, 100.0)
            
            # Calculate health
            base_health = 200
            health = result['health'] + base_health
            stathp = result['stathp'] * 50
            total_health = health + (level * 15) + stathp
            print(f"[DEBUG] Pre-Amulet Health for {player.display_name}: {total_health}")

            # Add equipped amulet HP
            amulet = await conn.fetchrow('SELECT hp FROM amulets WHERE user_id=$1 AND equipped=true', player.id)
            if amulet:
                print(f"[DEBUG] Amulet HP Bonus for {player.display_name}: {amulet['hp']}")
                total_health += amulet['hp']
            print(f"[DEBUG] Final Health for {player.display_name}: {total_health}")
            
            # Get damage and armor
            dmg, deff = await ctx.bot.get_raidstats(player, conn=conn)
            
            # Get element
            element = await self.element_ext.get_player_element(ctx, player.id)
            
            # Get class buffs
            classes = result['class'] if isinstance(result['class'], list) else [result['class']]
            buffs = await self.class_ext.get_class_buffs(classes)
            
            # Check for shield
            shield_data = await conn.fetchrow(
                "SELECT 1 FROM profile p JOIN allitems ai ON (p.user=ai.owner) JOIN inventory i ON (ai.id=i.item) " 
                "WHERE p.user=$1 AND i.equipped IS TRUE AND ai.type='Shield'", 
                player.id
            )
            has_shield = bool(shield_data)
            
            # Apply tank buffs if applicable
            tank_evolution = buffs.get("tank_evolution")
            total_health, damage_reflection = self.class_ext.apply_tank_buffs(total_health, tank_evolution, has_shield)
            
            # Create the combatant
            return Combatant(
                user=player,
                hp=total_health,
                max_hp=total_health,
                damage=dmg,
                armor=deff,
                element=element,
                luck=luck,
                lifesteal_percent=buffs.get("lifesteal_percent", 0),
                death_cheat_chance=buffs.get("death_cheat_chance", 0),
                mage_evolution=buffs.get("mage_evolution"),
                tank_evolution=tank_evolution,
                damage_reflection=damage_reflection,
                has_shield=has_shield
            )

    async def create_monster_combatant(self, monster_data, level=1, name=None):
        """Create a combatant object for a monster or boss"""
        # Get monster stats directly from json without scaling
        hp = monster_data.get("hp", 100)
        damage = monster_data.get("attack", 20)
        armor = monster_data.get("defense", 10)
        element = monster_data.get("element", "Unknown")
        
        # No level scaling - use exact values from monsters.json
        
        # Create the monster combatant
        return Combatant(
            user=name or monster_data.get("name", "Monster"),
            hp=hp,
            max_hp=hp,
            damage=damage,
            armor=armor,
            element=element,
            luck=70,  # Monsters have high base luck
            name=name or monster_data.get("name", "Monster")
        )

    async def find_random_opponent(self, ctx, player):
        """Find a random opponent for raid battles"""
        async with ctx.bot.pool.acquire() as conn:
            # Find a random player that isn't the specified player
            query = 'SELECT "user" FROM profile WHERE "user" != $1 ORDER BY RANDOM() LIMIT 1'
            random_opponent_id = await conn.fetchval(query, player.id)

            if not random_opponent_id:
                # Create a default NPC opponent if no players found
                enemy_combatant = await self.create_monster_combatant({
                    "name": "Mystery Opponent",
                    "hp": 300,
                    "attack": 50,
                    "defense": 30,
                    "element": "Unknown"
                })
                return enemy_combatant, None

            # Fetch the opponent user
            enemy = await ctx.bot.fetch_user(random_opponent_id)

            # Create enemy combatant
            enemy_combatant = await self.create_player_combatant(ctx, enemy)

            # Get enemy pet if any
            enemy_pet = await self.pet_ext.get_pet_combatant(ctx, enemy)

            return enemy_combatant, enemy_pet

    async def generate_monster(self, ctx, level):
        """Generate a random monster for the given level"""
        # Try to load from monsters.json through the Battles cog
        try:
            battle_cog = ctx.bot.cogs["Battles"]
            monsters_data = battle_cog.monsters_data

            # Convert keys from strings to integers and filter out non-public monsters
            monsters = {}
            for level_str, monster_list in monsters_data.items():
                monster_level = int(level_str)
                # Only keep monsters where ispublic is True (defaulting to True if key is missing)
                public_monsters = [monster for monster in monster_list if monster.get("ispublic", True)]
                monsters[monster_level] = public_monsters

            # Return a random monster of the appropriate level
            if level in monsters and monsters[level]:
                return random.choice(monsters[level])
        except (KeyError, AttributeError, Exception):
            pass

        # Fallback monster generation
        elements = ["Fire", "Water", "Earth", "Wind", "Light", "Dark"]
        return {
            "name": f"Level {level} Monster",
            "hp": 100 + (level * 30),
            "attack": 15 + (level * 3),
            "defense": 10 + (level * 2),
            "element": random.choice(elements)
        }
