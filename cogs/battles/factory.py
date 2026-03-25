# battles/factory.py
import json
import random
from decimal import Decimal
import asyncio

from classes.ascension import ASCENSION_TABLE_NAME
from .core.battle import Battle
from .core.combatant import Combatant
from .core.team import Team
from .types.pve import PvEBattle
from .types.pvp import PvPBattle
from .types.raid import RaidBattle
from .types.tower import TowerBattle
from .types.jury_tower import JuryTowerBattle
from .types.team_battle import TeamBattle
from .types.city_war import CityWarBattle
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
    PVE_LEVEL_BRACKET_SIZE = 10
    PVE_MAX_TIER = 10
    PVE_GOD_TIER = 11
    PVE_GOD_ENCOUNTER_LEVEL = 100
    PVE_PER_LEVEL_STAT_SCALE = Decimal("0.02")
    PVE_LEGENDARY_SPAWN_CHANCE = 0.01
    JURY_PRIMARY_COMBATANT_SCALE_WEIGHT = Decimal("0.40")
    JURY_SECONDARY_COMBATANT_SCALE_WEIGHT = Decimal("0.60")
    JURY_PRESTIGE_ATTACK_DEFENSE_STEP = Decimal("0.02")
    JURY_PRESTIGE_HP_STEP = Decimal("0.04")
    
    def __init__(self, bot):
        self.bot = bot
        self.element_ext = ElementExtension()
        self.class_ext = ClassBuffExtension()
        self.pet_ext = PetExtension()
        self.dragon_ext = DragonExtension()
        self.settings = BattleSettings(bot)
        self._ascension_tables_ready = False
        self._ascension_table_lock = asyncio.Lock()
        
    async def initialize(self):
        """Initialize the battle factory and its components"""
        await self._ensure_ascension_tables()
        await self.settings.initialize()

    async def _ensure_ascension_tables(self):
        if self._ascension_tables_ready:
            return
        async with self._ascension_table_lock:
            if self._ascension_tables_ready:
                return
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {ASCENSION_TABLE_NAME} (
                        user_id bigint PRIMARY KEY,
                        mantle text NOT NULL,
                        enabled boolean NOT NULL DEFAULT true,
                        chosen_at timestamp with time zone NOT NULL DEFAULT now()
                    );
                    """
                )
                await conn.execute(
                    f"""
                    ALTER TABLE {ASCENSION_TABLE_NAME}
                    ADD COLUMN IF NOT EXISTS enabled boolean NOT NULL DEFAULT true;
                    """
                )
            self._ascension_tables_ready = True

    def _get_pve_tier_for_player_level(self, player_level: int) -> int:
        normalized_level = max(1, int(player_level))
        return min(
            self.PVE_MAX_TIER,
            ((normalized_level - 1) // self.PVE_LEVEL_BRACKET_SIZE) + 1,
        )

    def _get_encounter_level_range_for_tier(self, tier: int) -> tuple[int, int]:
        normalized_tier = int(tier)
        if normalized_tier >= self.PVE_GOD_TIER:
            return self.PVE_GOD_ENCOUNTER_LEVEL, self.PVE_GOD_ENCOUNTER_LEVEL
        normalized_tier = max(1, min(self.PVE_MAX_TIER, normalized_tier))
        range_min = (normalized_tier - 1) * self.PVE_LEVEL_BRACKET_SIZE
        range_max = normalized_tier * self.PVE_LEVEL_BRACKET_SIZE
        return range_min, range_max

    def _scale_monster_for_encounter(
        self, monster_data: dict, tier: int, encounter_level: int | None = None
    ) -> dict:
        range_min, range_max = self._get_encounter_level_range_for_tier(tier)
        if encounter_level is None:
            encounter_level = random.randint(range_min, range_max)
        encounter_level = max(range_min, min(range_max, int(encounter_level)))

        scale_steps = max(0, encounter_level - range_min)
        scale_multiplier = Decimal("1") + (
            self.PVE_PER_LEVEL_STAT_SCALE * Decimal(scale_steps)
        )

        scaled_monster = dict(monster_data)
        for stat_key in ("hp", "attack", "defense"):
            base_value = Decimal(str(monster_data.get(stat_key, 0)))
            scaled_value = int(round(float(base_value * scale_multiplier)))
            scaled_monster[stat_key] = max(1, scaled_value)

        scaled_monster["encounter_level"] = encounter_level
        scaled_monster["pve_tier"] = int(tier)
        scaled_monster["pve_stat_multiplier"] = float(scale_multiplier)
        return scaled_monster

    def _get_monsters_data(self, ctx):
        battle_cog = ctx.bot.cogs.get("Battles") if hasattr(ctx.bot, "cogs") else None
        monsters_data = getattr(battle_cog, "monsters_data", None) if battle_cog else None
        if isinstance(monsters_data, dict) and monsters_data:
            return monsters_data

        try:
            with open("monsters.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def _get_monster_data_by_name(self, ctx, monster_name):
        target_name = str(monster_name or "").strip().lower()
        if not target_name:
            return None

        monsters_data = self._get_monsters_data(ctx)
        if not isinstance(monsters_data, dict):
            return None

        for monster_list in monsters_data.values():
            if not isinstance(monster_list, list):
                continue
            for monster in monster_list:
                if str(monster.get("name", "")).strip().lower() == target_name:
                    return dict(monster)
        return None

    def _build_jury_scale_snapshot_from_combatants(self, player_combatant, pet_combatant=None):
        player_hp = Decimal(str(getattr(player_combatant, "max_hp", getattr(player_combatant, "hp", 0)) or 0))
        player_attack = Decimal(str(getattr(player_combatant, "damage", 0) or 0))
        player_defense = Decimal(str(getattr(player_combatant, "armor", 0) or 0))

        pet_hp = Decimal("0")
        pet_attack = Decimal("0")
        pet_defense = Decimal("0")
        if pet_combatant:
            pet_hp = Decimal(str(getattr(pet_combatant, "max_hp", getattr(pet_combatant, "hp", 0)) or 0))
            pet_attack = Decimal(str(getattr(pet_combatant, "damage", 0) or 0))
            pet_defense = Decimal(str(getattr(pet_combatant, "armor", 0) or 0))

        attack_base = player_attack
        hp_base = player_hp
        defense_base = player_defense
        if pet_combatant:
            attack_base = self._build_jury_scale_stat_base(player_attack, pet_attack)
            hp_base = self._build_jury_scale_stat_base(player_hp, pet_hp)
            defense_base = self._build_jury_scale_stat_base(player_defense, pet_defense)

        return {
            "attack_base": max(1, int(round(float(attack_base)))),
            "hp_base": max(1, int(round(float(hp_base)))),
            "defense_base": max(1, int(round(float(defense_base)))),
        }

    def _build_jury_scale_stat_base(self, player_value: Decimal, pet_value: Decimal) -> Decimal:
        stronger_value = max(player_value, pet_value)
        weaker_value = min(player_value, pet_value)
        if stronger_value <= 0:
            return Decimal("0")

        # Jury Tower difficulty should balance both combatants, weighting the weaker
        # slot 60% while still giving 40% credit to the stronger slot.
        return (
            (stronger_value * self.JURY_PRIMARY_COMBATANT_SCALE_WEIGHT)
            + (weaker_value * self.JURY_SECONDARY_COMBATANT_SCALE_WEIGHT)
        )

    async def build_jury_tower_scale_snapshot(self, ctx, player, allow_pets):
        player_combatant = await self.create_player_combatant(ctx, player, include_pet=allow_pets)
        pet_combatant = None
        if allow_pets:
            pet_combatant = await self.pet_ext.get_pet_combatant(ctx, player)
        return self._build_jury_scale_snapshot_from_combatants(player_combatant, pet_combatant)

    def _build_jury_scaled_enemy_info(self, enemy_info, scale_snapshot, prestige_level=0):
        scale_profile = enemy_info.get("scale") or {}
        if not scale_profile:
            return {
                "name": enemy_info.get("name", "Defendant"),
                "hp": int(enemy_info.get("hp", 100)),
                "attack": int(enemy_info.get("attack", 20)),
                "defense": int(enemy_info.get("defense", 10)),
                "element": enemy_info.get("element", "Unknown"),
            }

        attack_base = Decimal(str(scale_snapshot.get("attack_base", 1) or 1))
        hp_base = Decimal(str(scale_snapshot.get("hp_base", 1) or 1))
        defense_base = Decimal(str(scale_snapshot.get("defense_base", 1) or 1))

        floor_scale = Decimal(str(scale_profile.get("floor_scale", 1)))
        hp_multiplier = Decimal(str(scale_profile.get("hp_multiplier", 1)))
        defense_ratio = Decimal(str(scale_profile.get("defense_ratio", 0.1)))
        attack_armor_ratio = Decimal(str(scale_profile.get("attack_armor_ratio", 1.0)))
        attack_hp_ratio = Decimal(str(scale_profile.get("attack_hp_ratio", 0.05)))

        scaled_hp = max(100, int(round(float(attack_base * hp_multiplier * floor_scale))))
        scaled_attack = max(
            10,
            int(
                round(
                    float(
                        (defense_base * attack_armor_ratio)
                        + (hp_base * attack_hp_ratio * floor_scale)
                    )
                )
            ),
        )
        scaled_defense = max(
            1,
            int(round(float(attack_base * defense_ratio * floor_scale))),
        )
        prestige_level = max(0, int(prestige_level or 0))
        if prestige_level > 0:
            attack_defense_multiplier = Decimal("1") + (
                self.JURY_PRESTIGE_ATTACK_DEFENSE_STEP * Decimal(prestige_level)
            )
            hp_multiplier = Decimal("1") + (
                self.JURY_PRESTIGE_HP_STEP * Decimal(prestige_level)
            )
            scaled_hp = int(round(float(Decimal(str(scaled_hp)) * hp_multiplier)))
            scaled_attack = int(
                round(float(Decimal(str(scaled_attack)) * attack_defense_multiplier))
            )
            scaled_defense = int(
                round(float(Decimal(str(scaled_defense)) * attack_defense_multiplier))
            )

        return {
            "name": enemy_info.get("name", "Defendant"),
            "hp": scaled_hp,
            "attack": scaled_attack,
            "defense": scaled_defense,
            "element": enemy_info.get("element", "Unknown"),
        }

    def build_jury_tower_enemy_specs(self, floor_data, scale_snapshot, prestige_level=0):
        enemy_specs = []
        for enemy_info in floor_data.get("enemies", []):
            scaled_enemy_info = self._build_jury_scaled_enemy_info(
                enemy_info,
                scale_snapshot,
                prestige_level=prestige_level,
            )
            enemy_specs.append(
                {
                    "key": enemy_info.get("key", "boss"),
                    "name": enemy_info.get("name", scaled_enemy_info.get("name", "Defendant")),
                    "hp": int(scaled_enemy_info.get("hp", 100)),
                    "attack": int(scaled_enemy_info.get("attack", 20)),
                    "defense": int(scaled_enemy_info.get("defense", 10)),
                    "element": scaled_enemy_info.get("element", "Unknown"),
                }
            )
        return enemy_specs
    
    async def create_battle(self, battle_type, ctx, **kwargs):
        """Create a battle of specified type with given parameters"""
        # Apply battle settings to kwargs
        settings_kwargs = await self.settings.apply_settings_to_battle(battle_type, kwargs)

        if "hp_bar_style" not in settings_kwargs:
            battles_cog = self.bot.get_cog("Battles")
            user_id = None
            player = settings_kwargs.get("player")
            if player is not None and hasattr(player, "id"):
                user_id = player.id
            elif hasattr(ctx, "author") and hasattr(ctx.author, "id"):
                user_id = ctx.author.id

            if "emoji_hp_bars" in settings_kwargs:
                settings_kwargs["hp_bar_style"] = (
                    Battle.HP_BAR_STYLE_COLORFUL
                    if settings_kwargs["emoji_hp_bars"]
                    else Battle.HP_BAR_STYLE_NORMAL
                )
            elif battles_cog and user_id is not None:
                settings_kwargs["hp_bar_style"] = await battles_cog._get_user_hp_bar_style(user_id)

        settings_kwargs["hp_bar_style"] = Battle.normalize_hp_bar_style(
            settings_kwargs.get("hp_bar_style")
        )
        settings_kwargs["emoji_hp_bars"] = (
            settings_kwargs["hp_bar_style"] != Battle.HP_BAR_STYLE_NORMAL
        )

        if battle_type == "pvp":
            return await self.create_pvp_battle(ctx, **settings_kwargs)
        elif battle_type == "pve":
            return await self.create_pve_battle(ctx, **settings_kwargs)
        elif battle_type == "raid":
            return await self.create_raid_battle(ctx, **settings_kwargs)
        elif battle_type == "tower":
            return await self.create_tower_battle(ctx, **settings_kwargs)
        elif battle_type == "jurytower":
            return await self.create_jury_tower_battle(ctx, **settings_kwargs)
        elif battle_type == "team":
            return await self.create_team_battle(ctx, **settings_kwargs)
        elif battle_type == "citywar":
            return await self.create_city_war_battle(ctx, **settings_kwargs)
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
        battle_kwargs = kwargs.copy()
        battle_kwargs.pop("money", None)
        return PvPBattle(ctx, [team1, team2], money=money, **battle_kwargs)
    
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
            if "encounter_level" not in monster_data or "pve_tier" not in monster_data:
                tier_for_scaling = int(monster_level or monster_data.get("pve_tier") or 1)
                monster_data = self._scale_monster_for_encounter(
                    monster_data,
                    tier_for_scaling,
                    encounter_level=monster_data.get("encounter_level"),
                )
                monster_level = tier_for_scaling
            else:
                monster_level = int(monster_level or monster_data.get("pve_tier") or 1)
            monster_combatant = await self.create_monster_combatant(monster_data, level=monster_level)
        else:
            # Generate random monster based on level
            from utils import misc as rpgtools
            player_xp = ctx.character_data.get("xp", 0)
            player_level = rpgtools.xptolevel(player_xp)
            
            if monster_level is None:
                if (
                    player_level >= 5
                    and random.random() < self.PVE_LEGENDARY_SPAWN_CHANCE
                ):
                    monster_level = self.PVE_GOD_TIER
                else:
                    monster_level = self._get_pve_tier_for_player_level(player_level)
            
            monster_data = await self.generate_monster(ctx, monster_level)
            forced_level = (
                self.PVE_GOD_ENCOUNTER_LEVEL
                if monster_level == self.PVE_GOD_TIER
                else None
            )
            monster_data = self._scale_monster_for_encounter(
                monster_data,
                monster_level,
                encounter_level=forced_level,
            )
            monster_combatant = await self.create_monster_combatant(monster_data, level=monster_level)
        
        # Create teams
        player_team = Team("Player", [player_combatant])
        if pet_combatant and allow_pets:
            player_team.add_combatant(pet_combatant)

        if int(monster_level or 0) == PvEBattle.GOD_OF_GODS_TIER:
            for god_name in ("Elysia", "Sepulchure", "Drakath"):
                god_data = self._get_monster_data_by_name(ctx, god_name)
                if not god_data:
                    continue
                god_combatant = await self.create_monster_combatant(
                    god_data,
                    level=self.PVE_GOD_TIER,
                    name=god_name,
                )
                god_combatant.is_omnithrone_ally = True
                player_team.add_combatant(god_combatant)
            
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
        money = kwargs.get("money", 0)

        # Get allow_pets setting
        allow_pets = kwargs.get("allow_pets")

        team_a_members = kwargs.get("team_a")
        team_b_members = kwargs.get("team_b")

        if team_a_members or team_b_members:
            if not team_a_members or not team_b_members:
                raise ValueError("Raid battle team mode requires both team_a and team_b")

            player1_team = await self._create_player_team(ctx, "A", team_a_members, allow_pets)
            player2_team = await self._create_player_team(ctx, "B", team_b_members, allow_pets)
        else:
            player1 = kwargs.get("player1", ctx.author)
            player2 = kwargs.get("player2")

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
        battle_kwargs.pop('team_a', None)
        battle_kwargs.pop('team_b', None)
        return RaidBattle(ctx, [player1_team, player2_team], money=money, **battle_kwargs)

    async def _create_player_team(self, ctx, team_name, members, allow_pets):
        """Build a player team from one or more player members."""
        normalized_members = [member for member in members if member is not None]
        if not normalized_members:
            raise ValueError("Team requires at least one member")

        combatants = []
        for member in normalized_members:
            player_combatant = await self.create_player_combatant(ctx, member, include_pet=allow_pets)
            combatants.append(player_combatant)

            if allow_pets:
                pet_combatant = await self.pet_ext.get_pet_combatant(ctx, member)
                if pet_combatant:
                    combatants.append(pet_combatant)

        return Team(team_name, combatants)
    
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

        if not teams:
            team_a_members = kwargs.get("team_a")
            team_b_members = kwargs.get("team_b")
            allow_pets = kwargs.get("allow_pets")

            if team_a_members and team_b_members:
                teams = [
                    await self._create_player_team(ctx, "A", team_a_members, allow_pets),
                    await self._create_player_team(ctx, "B", team_b_members, allow_pets),
                ]

        if not teams or len(teams) != 2:
            raise ValueError("Team battle requires exactly two teams")

        # Create the battle
        battle_kwargs = kwargs.copy()
        battle_kwargs.pop("money", None)
        battle_kwargs.pop("teams", None)
        battle_kwargs.pop("team_a", None)
        battle_kwargs.pop("team_b", None)
        return TeamBattle(ctx, teams, money=money, **battle_kwargs)

    async def create_city_war_battle(self, ctx, **kwargs):
        """Create a city-war battle with prebuilt teams."""
        teams = kwargs.get("teams", [])
        if not teams or len(teams) != 2:
            raise ValueError("City war requires exactly two teams")

        battle_kwargs = kwargs.copy()
        battle_kwargs.pop("teams", None)
        return CityWarBattle(ctx, teams, **battle_kwargs)

    async def create_jury_tower_battle(self, ctx, **kwargs):
        """Create a jury tower battle for a specific floor."""
        player = kwargs.get("player", ctx.author)
        floor_number = kwargs.get("floor_number", kwargs.get("level", 1))
        floor_data = kwargs.get("floor_data", {})
        allow_pets = kwargs.get("allow_pets")
        choice_key = kwargs.get("choice_key")
        scale_snapshot = kwargs.get("jury_scale_snapshot")
        prestige_level = kwargs.get("jury_prestige_level", 0)
        player_combatant = kwargs.get("jury_player_combatant")
        pet_combatant = kwargs.get("jury_pet_combatant")

        if player_combatant is None:
            player_combatant = await self.create_player_combatant(ctx, player, include_pet=allow_pets)
        if pet_combatant is None and allow_pets:
            pet_combatant = await self.pet_ext.get_pet_combatant(ctx, player)

        if not scale_snapshot:
            scale_snapshot = self._build_jury_scale_snapshot_from_combatants(player_combatant, pet_combatant)

        player_team = Team("Player", [player_combatant])
        if pet_combatant:
            player_team.add_combatant(pet_combatant)

        enemy_team = Team("Defendants", [])
        for scaled_enemy_info in self.build_jury_tower_enemy_specs(
            floor_data,
            scale_snapshot,
            prestige_level=prestige_level,
        ):
            enemy_combatant = await self.create_monster_combatant(
                scaled_enemy_info,
                name=scaled_enemy_info.get("name"),
            )
            setattr(enemy_combatant, "jury_key", scaled_enemy_info.get("key", "boss"))
            enemy_team.add_combatant(enemy_combatant)

        battle_kwargs = kwargs.copy()
        battle_kwargs.pop("level", None)
        battle_kwargs.pop("floor_number", None)
        battle_kwargs.pop("floor_data", None)
        battle_kwargs.pop("choice_key", None)
        battle_kwargs.pop("jury_player_combatant", None)
        battle_kwargs.pop("jury_pet_combatant", None)

        return JuryTowerBattle(
            ctx,
            [player_team, enemy_team],
            level=floor_number,
            floor_number=floor_number,
            floor_data=floor_data,
            choice_key=choice_key,
            **battle_kwargs,
        )
        
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
        battle_kwargs = kwargs.copy()
        battle_kwargs.pop("dragon_level", None)
        return DragonBattle(ctx, [dragon_team, player_team], dragon_level=dragon_level, **battle_kwargs)
    
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
            
            equipped_items = await conn.fetch(
                "SELECT ai.type, ai.damage, ai.armor, ai.element FROM profile p "
                "JOIN allitems ai ON (p.user=ai.owner) JOIN inventory i ON (ai.id=i.item) "
                "WHERE i.equipped IS TRUE AND p.user=$1;",
                player.id,
            )
            element_data = self.element_ext.resolve_player_combat_elements(equipped_items)
            attack_element = element_data.get("attack_element", "Unknown")
            defense_element = element_data.get("defense_element", attack_element)
            dual_attack_elements = element_data.get("dual_attack_elements")
            
            # Get class buffs
            classes = result['class'] if isinstance(result['class'], list) else [result['class']]
            buffs = await self.class_ext.get_class_buffs(classes)
            try:
                ascension_record = await conn.fetchrow(
                    f'SELECT mantle, enabled FROM {ASCENSION_TABLE_NAME} WHERE user_id = $1;',
                    player.id,
                )
            except Exception:
                ascension_record = None
            ascension_mantle = None if ascension_record is None else ascension_record["mantle"]
            ascension_enabled = True if ascension_record is None else bool(ascension_record["enabled"])
            
            has_shield = element_data.get("has_shield", False)
            
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
                element=attack_element,
                attack_element=attack_element,
                defense_element=defense_element,
                dual_attack_elements=dual_attack_elements,
                luck=luck,
                lifesteal_percent=buffs.get("lifesteal_percent", 0),
                death_cheat_chance=buffs.get("death_cheat_chance", 0),
                mage_evolution=buffs.get("mage_evolution"),
                tank_evolution=tank_evolution,
                damage_reflection=damage_reflection,
                has_shield=has_shield,
                ascension_mantle=ascension_mantle,
                ascension_enabled=ascension_enabled,
                ascension_signature_used=False,
                ascension_opening_used=False,
                ascension_survival_used=False,
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
            if hasattr(battle_cog, "_get_public_monsters_by_level"):
                monsters = await battle_cog._get_public_monsters_by_level()
            else:
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
