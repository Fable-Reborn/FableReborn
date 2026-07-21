"""Long-form Feats for endgame mastery and replay value.

Existing feat keys are permanent: earned deeds are never revoked. New tiers
extend the original foundation goals into multi-month mastery tracks. Feats
pay Legacy Points once and remain bragging rights only — no combat power.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands

from utils.checks import has_char


logger = logging.getLogger(__name__)


TIERS = {
    "bronze": {"pips": "◇", "label": "Bronze", "order": 0},
    "silver": {"pips": "◆", "label": "Silver", "order": 1},
    "gold": {"pips": "✦", "label": "Gold", "order": 2},
    "mythic": {"pips": "✧", "label": "Mythic", "order": 3},
    "legendary": {"pips": "❖", "label": "Legendary", "order": 4},
    "ascendant": {"pips": "⬖", "label": "Ascendant", "order": 5},
}

# key -> feat. Existing keys are kept stable so already-earned rows stay valid.
FEATS = {
    # --- Battle Tower ---------------------------------------------------------
    "tower_regular": {
        "name": "Tower Regular", "category": "Battle Tower", "tier": "bronze", "lp": 20,
        "description": "Clear 25 Battle Tower floors.",
    },
    "tower_conqueror": {
        "name": "Tower Conqueror", "category": "Battle Tower", "tier": "silver", "lp": 30,
        "description": "Clear Battle Tower floor 30.",
    },
    "tower_marathon": {
        "name": "Tower Marathon", "category": "Battle Tower", "tier": "gold", "lp": 90,
        "description": "Clear 250 Battle Tower floors lifetime.",
    },
    "tower_millennium": {
        "name": "Millennium Climber", "category": "Battle Tower", "tier": "gold", "lp": 200,
        "description": "Clear 1,000 Battle Tower floors lifetime.",
    },
    "tower_vanguard_1800": {
        "name": "Tower Vanguard", "category": "Battle Tower", "tier": "mythic", "lp": 225,
        "description": "Clear 1,800 Battle Tower floors lifetime.",
    },
    "tower_paragon_3600": {
        "name": "Endless Paragon", "category": "Battle Tower", "tier": "legendary", "lp": 325,
        "description": "Clear 3,600 Battle Tower floors lifetime.",
    },
    "tower_ascendant_6000": {
        "name": "Above the Summit", "category": "Battle Tower", "tier": "ascendant", "lp": 500,
        "description": "Clear 6,000 Battle Tower floors lifetime.",
    },
    "tower_prestige": {
        "name": "Prestige Climber", "category": "Battle Tower", "tier": "silver", "lp": 35,
        "description": "Prestige the Battle Tower.",
    },
    "tower_dynasty": {
        "name": "Tower Dynasty", "category": "Battle Tower", "tier": "gold", "lp": 100,
        "description": "Prestige the Battle Tower 5 times.",
    },
    "tower_prestige_15": {
        "name": "Tempered Dynasty", "category": "Battle Tower", "tier": "gold", "lp": 125,
        "description": "Prestige the Battle Tower 15 times.",
    },
    "tower_prestige_30": {
        "name": "Thirty Crowns", "category": "Battle Tower", "tier": "mythic", "lp": 200,
        "description": "Prestige the Battle Tower 30 times.",
    },
    "tower_prestige_75": {
        "name": "Sovereign of the Spire", "category": "Battle Tower", "tier": "legendary", "lp": 325,
        "description": "Prestige the Battle Tower 75 times.",
    },
    "tower_prestige_150": {
        "name": "Throne Above Thrones", "category": "Battle Tower", "tier": "ascendant", "lp": 500,
        "description": "Prestige the Battle Tower 150 times.",
    },
    "boss_rush_champion": {
        "name": "Boss Rush Champion", "category": "Battle Tower", "tier": "silver", "lp": 40,
        "description": "Clear a full Boss Rush.",
    },
    "boss_rush_master": {
        "name": "Boss Rush Master", "category": "Battle Tower", "tier": "gold", "lp": 100,
        "description": "Clear 10 full Boss Rushes.",
    },
    "boss_rush_veteran_25": {
        "name": "Crown Breaker", "category": "Battle Tower", "tier": "mythic", "lp": 125,
        "description": "Clear 25 full Boss Rushes.",
    },
    "boss_rush_mythic_75": {
        "name": "Hall of Fallen Kings", "category": "Battle Tower", "tier": "legendary", "lp": 225,
        "description": "Clear 75 full Boss Rushes.",
    },
    "boss_rush_ascendant_150": {
        "name": "The Final Crown", "category": "Battle Tower", "tier": "ascendant", "lp": 450,
        "description": "Clear 150 full Boss Rushes.",
    },
    "ironman_ascendant": {
        "name": "Ironman Ascendant", "category": "Battle Tower", "tier": "silver", "lp": 75,
        "description": "Clear floor 30 in Battle Tower Ironman.",
    },
    "ironman_relentless": {
        "name": "Relentless", "category": "Battle Tower", "tier": "gold", "lp": 200,
        "description": "Complete 3 full Ironman ascents.",
    },
    "ironman_master_10": {
        "name": "Unbroken Ten", "category": "Battle Tower", "tier": "mythic", "lp": 150,
        "description": "Complete 10 full Ironman ascents.",
    },
    "ironman_mythic_25": {
        "name": "Will Without End", "category": "Battle Tower", "tier": "legendary", "lp": 250,
        "description": "Complete 25 full Ironman ascents.",
    },
    "ironman_eternal_50": {
        "name": "One Life, Fifty Legends", "category": "Battle Tower", "tier": "ascendant", "lp": 500,
        "description": "Complete 50 full Ironman ascents.",
    },
    "corruption_cleanser": {
        "name": "Corruption Cleanser", "category": "Battle Tower", "tier": "gold", "lp": 75,
        "description": "Cleanse 20 corrupted floors.",
    },
    "corruption_warden_75": {
        "name": "Warden of the Veil", "category": "Battle Tower", "tier": "gold", "lp": 125,
        "description": "Cleanse 75 corrupted floors.",
    },
    "corruption_bane_200": {
        "name": "Bane of Corruption", "category": "Battle Tower", "tier": "mythic", "lp": 225,
        "description": "Cleanse 200 corrupted floors.",
    },
    "corruption_extinction_500": {
        "name": "The Last Blight", "category": "Battle Tower", "tier": "ascendant", "lp": 450,
        "description": "Cleanse 500 corrupted floors.",
    },
    # --- Ice Dragon -----------------------------------------------------------
    "dragon_slayer": {
        "name": "Dragon Slayer", "category": "Ice Dragon", "tier": "bronze", "lp": 15,
        "description": "Defeat an Ice Dragon.",
    },
    "dragon_veteran": {
        "name": "Dragon Veteran", "category": "Ice Dragon", "tier": "silver", "lp": 30,
        "description": "Defeat 5 Ice Dragons.",
    },
    "dragon_centurion": {
        "name": "Dragon Centurion", "category": "Ice Dragon", "tier": "gold", "lp": 100,
        "description": "Defeat 100 Ice Dragons.",
    },
    "dragon_eternal_foe": {
        "name": "Eternal Foe", "category": "Ice Dragon", "tier": "gold", "lp": 250,
        "description": "Defeat 500 Ice Dragons.",
    },
    "dragon_thousand": {
        "name": "Wyrm's Reckoning", "category": "Ice Dragon", "tier": "mythic", "lp": 250,
        "description": "Defeat 1,000 Ice Dragons.",
    },
    "dragon_3000": {
        "name": "Frostbound Nemesis", "category": "Ice Dragon", "tier": "legendary", "lp": 350,
        "description": "Defeat 3,000 Ice Dragons.",
    },
    "dragon_7500": {
        "name": "End of the Wyrm", "category": "Ice Dragon", "tier": "ascendant", "lp": 500,
        "description": "Defeat 7,500 Ice Dragons.",
    },
    "maw_walker": {
        "name": "Maw Walker", "category": "Ice Dragon", "tier": "gold", "lp": 75,
        "description": "Defeat the Abyssal Maw (dragon level 35+).",
    },
    "maw_diver": {
        "name": "Maw Diver", "category": "Ice Dragon", "tier": "gold", "lp": 100,
        "description": "Defeat the dragon at level 30 or higher.",
    },
    "maw_abyssal": {
        "name": "Voice of the Abyss", "category": "Ice Dragon", "tier": "legendary", "lp": 250,
        "description": "Defeat the dragon at level 40 or higher.",
    },
    "world_record_holder": {
        "name": "World Record Holder", "category": "Ice Dragon", "tier": "legendary", "lp": 150,
        "description": "Be in the party that sets a new all-time dragon record.",
    },
    # --- Raids ----------------------------------------------------------------
    "raid_victor": {
        "name": "Raid Victor", "category": "Raids", "tier": "bronze", "lp": 15,
        "description": "Win a raid.",
    },
    "raid_veteran": {
        "name": "Raid Veteran", "category": "Raids", "tier": "silver", "lp": 40,
        "description": "Win 10 raids.",
    },
    "raid_warlord": {
        "name": "Raid Warlord", "category": "Raids", "tier": "gold", "lp": 90,
        "description": "Win 50 raids.",
    },
    "raid_immortal": {
        "name": "Raid Immortal", "category": "Raids", "tier": "mythic", "lp": 200,
        "description": "Win 200 raids.",
    },
    "raid_mythic_500": {
        "name": "Warhost Eternal", "category": "Raids", "tier": "legendary", "lp": 250,
        "description": "Win 500 raids.",
    },
    "raid_ascendant_1000": {
        "name": "Army of One Thousand", "category": "Raids", "tier": "ascendant", "lp": 450,
        "description": "Win 1,000 raids.",
    },
    # --- The Rift ---------------------------------------------------------------
    "rift_sealer": {
        "name": "Rift Sealer", "category": "The Rift", "tier": "silver", "lp": 50,
        "description": "Clear all 7 rooms in a weekly Rift.",
    },
    "rift_perfectionist": {
        "name": "Rift Perfectionist", "category": "The Rift", "tier": "gold", "lp": 100,
        "description": "Fully clear 10 weekly Rifts.",
    },
    "rift_ace": {
        "name": "Rift Ace", "category": "The Rift", "tier": "legendary", "lp": 150,
        "description": "Full-clear a Heroic or Mythic Rift with a score above 90,000.",
    },
    "rift_veteran_25": {
        "name": "Between Worlds", "category": "The Rift", "tier": "mythic", "lp": 125,
        "description": "Fully clear 25 weekly Rifts.",
    },
    "rift_mythic_52": {
        "name": "A Year in the Rift", "category": "The Rift", "tier": "legendary", "lp": 250,
        "description": "Fully clear 52 weekly Rifts.",
    },
    "rift_ascendant_104": {
        "name": "Beyond the Breach", "category": "The Rift", "tier": "ascendant", "lp": 500,
        "description": "Fully clear 104 weekly Rifts.",
    },
    # --- The Hunt ----------------------------------------------------------------
    "hunt_slayer": {
        "name": "Great Hunt Slayer", "category": "The Hunt", "tier": "silver", "lp": 35,
        "description": "Help slay a Hunt beast.",
    },
    "hunt_apex": {
        "name": "Apex Hunter", "category": "The Hunt", "tier": "gold", "lp": 90,
        "description": "Help slay 5 Hunt beasts.",
    },
    "hunt_pathfinder": {
        "name": "Pathfinder", "category": "The Hunt", "tier": "gold", "lp": 100,
        "description": "Be the top tracker of a slain beast.",
    },
    "hunt_veteran_15": {
        "name": "Beaststalker", "category": "The Hunt", "tier": "mythic", "lp": 125,
        "description": "Help slay 15 Hunt beasts.",
    },
    "hunt_mythic_30": {
        "name": "Keeper of Trophies", "category": "The Hunt", "tier": "legendary", "lp": 225,
        "description": "Help slay 30 Hunt beasts.",
    },
    "hunt_ascendant_75": {
        "name": "Apex of Apexes", "category": "The Hunt", "tier": "ascendant", "lp": 450,
        "description": "Help slay 75 Hunt beasts.",
    },
    # --- Traitor Raids -------------------------------------------------------------
    "traitor_hunter": {
        "name": "Traitor Hunter", "category": "Traitor Raids", "tier": "silver", "lp": 35,
        "description": "Win a Traitor Raid as an innocent.",
        "active": False,
    },
    "traitor_bargain": {
        "name": "Traitor's Bargain", "category": "Traitor Raids", "tier": "gold", "lp": 75,
        "description": "Win a Traitor Raid as the traitor.",
        "active": False,
    },
    "traitor_mastermind": {
        "name": "Mastermind", "category": "Traitor Raids", "tier": "legendary", "lp": 200,
        "description": "Win 3 Traitor Raids as the traitor.",
        "active": False,
    },
    # --- Gauntlet ---------------------------------------------------------------------
    "gauntlet_breaker": {
        "name": "Gauntlet Breaker", "category": "Gauntlet", "tier": "bronze", "lp": 15,
        "description": "Break another player's Defense Gauntlet.",
    },
    "gauntlet_wall": {
        "name": "Living Wall", "category": "Gauntlet", "tier": "bronze", "lp": 15,
        "description": "Have your Defense Gauntlet hold against an attacker.",
    },
    "gauntlet_marauder": {
        "name": "Marauder", "category": "Gauntlet", "tier": "gold", "lp": 75,
        "description": "Break 25 Defense Gauntlets.",
    },
    "gauntlet_bastion": {
        "name": "Bastion", "category": "Gauntlet", "tier": "gold", "lp": 75,
        "description": "Hold your Gauntlet against 25 attackers.",
    },
    "gauntlet_breaker_100": {
        "name": "Siegebreaker", "category": "Gauntlet", "tier": "mythic", "lp": 225,
        "description": "Break 100 Defense Gauntlets.",
    },
    "gauntlet_breaker_250": {
        "name": "No Wall Remains", "category": "Gauntlet", "tier": "ascendant", "lp": 450,
        "description": "Break 250 Defense Gauntlets.",
    },
    "gauntlet_hold_100": {
        "name": "Citadel", "category": "Gauntlet", "tier": "mythic", "lp": 225,
        "description": "Hold your Gauntlet against 100 attackers.",
    },
    "gauntlet_hold_250": {
        "name": "The Unfallen Gate", "category": "Gauntlet", "tier": "ascendant", "lp": 450,
        "description": "Hold your Gauntlet against 250 attackers.",
    },
    # --- Adventuring -----------------------------------------------------------------
    "adventure_veteran": {
        "name": "Roadworn", "category": "Adventuring", "tier": "bronze", "lp": 15,
        "description": "Complete 25 adventures.",
    },
    "adventure_nomad": {
        "name": "Nomad", "category": "Adventuring", "tier": "silver", "lp": 40,
        "description": "Complete 100 adventures.",
    },
    "adventure_odyssey": {
        "name": "Odyssey", "category": "Adventuring", "tier": "gold", "lp": 90,
        "description": "Complete 500 adventures.",
    },
    "adventure_wayfarer_750": {
        "name": "Wayfarer", "category": "Adventuring", "tier": "gold", "lp": 125,
        "description": "Complete 750 adventures.",
    },
    "adventure_mythic_1500": {
        "name": "A Thousand Roads", "category": "Adventuring", "tier": "mythic", "lp": 225,
        "description": "Complete 1,500 adventures.",
    },
    "adventure_worldwalker": {
        "name": "Worldwalker", "category": "Adventuring", "tier": "legendary", "lp": 200,
        "description": "Complete 2,000 adventures.",
    },
    "adventure_legend_2500": {
        "name": "Realmwalker", "category": "Adventuring", "tier": "legendary", "lp": 325,
        "description": "Complete 2,500 adventures.",
    },
    "adventure_ascendant_3500": {
        "name": "Beyond Every Horizon", "category": "Adventuring", "tier": "ascendant", "lp": 500,
        "description": "Complete 3,500 adventures.",
    },
    # --- Economy ------------------------------------------------------------------------
    "wealth_keeper_1m": {
        "name": "Seven-Figure Purse", "category": "Economy", "tier": "silver", "lp": 20,
        "description": "Hold $1,000,000 at one time.",
    },
    "wealth_magnate_10m": {
        "name": "Realm Magnate", "category": "Economy", "tier": "mythic", "lp": 100,
        "description": "Hold $10,000,000 at one time.",
    },
    "wealth_titan_25m": {
        "name": "Treasury Titan", "category": "Economy", "tier": "legendary", "lp": 250,
        "description": "Hold $25,000,000 at one time.",
    },
    "wealth_sovereign_50m": {
        "name": "Golden Sovereign", "category": "Economy", "tier": "ascendant", "lp": 450,
        "description": "Hold $50,000,000 at one time.",
    },
    # --- Collection ---------------------------------------------------------------------
    "egg_types_10": {
        "name": "Curious Clutch", "category": "Collection", "tier": "bronze", "lp": 20,
        "description": "Own eggs from 10 distinct species.",
    },
    "egg_types_25": {
        "name": "Keeper of Nests", "category": "Collection", "tier": "silver", "lp": 40,
        "description": "Own eggs from 25 distinct species.",
    },
    "egg_types_50": {
        "name": "Living Bestiary", "category": "Collection", "tier": "gold", "lp": 90,
        "description": "Own eggs from 50 distinct species.",
    },
    "egg_types_75": {
        "name": "Ark of Wonders", "category": "Collection", "tier": "legendary", "lp": 225,
        "description": "Own eggs from 75 distinct species.",
    },
    "egg_types_100": {
        "name": "Hundredfold Genesis", "category": "Collection", "tier": "ascendant", "lp": 425,
        "description": "Own eggs from 100 distinct species.",
    },
    "perfect_egg_iv": {
        "name": "Perfect Genesis", "category": "Collection", "tier": "ascendant", "lp": 350,
        "description": "Own an egg with a perfect 100% IV.",
    },
    "power_150_first": {
        "name": "Relic-Grade Arsenal", "category": "Collection", "tier": "silver", "lp": 35,
        "description": "Own an item with at least 150 combined power.",
    },
    "power_150_10": {
        "name": "Vault of Might", "category": "Collection", "tier": "gold", "lp": 90,
        "description": "Own 10 items with at least 150 combined power.",
    },
    "power_150_20": {
        "name": "Arsenal Curator", "category": "Collection", "tier": "mythic", "lp": 160,
        "description": "Own 20 items with at least 150 combined power.",
    },
    "power_150_50": {
        "name": "Legendary Armory", "category": "Collection", "tier": "legendary", "lp": 275,
        "description": "Own 50 items with at least 150 combined power.",
    },
    "power_150_100": {
        "name": "Hundred Masterworks", "category": "Collection", "tier": "ascendant", "lp": 475,
        "description": "Own 100 items with at least 150 combined power.",
    },
    # --- Crafting -----------------------------------------------------------------------
    "amulet_tier_1": {
        "name": "First Binding", "category": "Crafting", "tier": "bronze", "lp": 15,
        "description": "Craft or own a Tier 1 amulet.",
    },
    "amulet_tier_3": {
        "name": "Runesmith", "category": "Crafting", "tier": "silver", "lp": 35,
        "description": "Craft or own a Tier 3 amulet.",
    },
    "amulet_tier_5": {
        "name": "Resonant Artisan", "category": "Crafting", "tier": "gold", "lp": 75,
        "description": "Craft or own a Tier 5 amulet.",
    },
    "amulet_tier_7": {
        "name": "Master Binder", "category": "Crafting", "tier": "mythic", "lp": 150,
        "description": "Craft or own a Tier 7 amulet.",
    },
    "amulet_tier_9": {
        "name": "Grand Wyrdsmith", "category": "Crafting", "tier": "legendary", "lp": 250,
        "description": "Craft or own a Tier 9 amulet.",
    },
    "amulet_tier_10": {
        "name": "Perfect Binding", "category": "Crafting", "tier": "ascendant", "lp": 425,
        "description": "Craft or own a Tier 10 amulet.",
    },
    "starforge_1": {
        "name": "First Star", "category": "Crafting", "tier": "gold", "lp": 75,
        "description": "Forge an item to ★1.",
    },
    "starforge_5": {
        "name": "Constellation Smith", "category": "Crafting", "tier": "legendary", "lp": 250,
        "description": "Forge an item to ★5.",
    },
    "starforge_10": {
        "name": "Starforged Perfection", "category": "Crafting", "tier": "ascendant", "lp": 475,
        "description": "Forge an item to ★10.",
    },
    # --- Mastery ------------------------------------------------------------------------
    "relic_curator": {
        "name": "Relic Curator", "category": "Mastery", "tier": "silver", "lp": 75,
        "description": "Complete a full relic set.",
    },
    "relic_attuned": {
        "name": "Codex Attuned", "category": "Mastery", "tier": "gold", "lp": 75,
        "description": "Attune a collection in the Relic Codex.",
    },
    "relic_exalted": {
        "name": "Codex Exalted", "category": "Mastery", "tier": "legendary", "lp": 225,
        "description": "Exalt a collection in the Relic Codex.",
    },
    "relic_ascendant": {
        "name": "Codex Ascendant", "category": "Mastery", "tier": "ascendant", "lp": 450,
        "description": "Ascend a collection in the Relic Codex.",
    },
    "soulbound_eternal": {
        "name": "Eternal Bond", "category": "Mastery", "tier": "legendary", "lp": 200,
        "description": "Raise a soulbound weapon to Eternal (level 50).",
    },
    "god_champion": {
        "name": "Champion of the Gods", "category": "Mastery", "tier": "silver", "lp": 50,
        "description": "Contribute favor in a season your god wins.",
    },
}

CATEGORY_ORDER = [
    "Battle Tower", "Ice Dragon", "Raids", "The Rift", "The Hunt",
    "Traitor Raids", "Gauntlet", "Adventuring", "Economy", "Collection",
    "Crafting", "Mastery",
]

ACTIVE_FEAT_KEYS = tuple(key for key, feat in FEATS.items() if feat.get("active", True))
ARCHIVED_FEAT_KEYS = tuple(key for key, feat in FEATS.items() if not feat.get("active", True))
ACTIVE_CATEGORIES = tuple(
    category
    for category in CATEGORY_ORDER
    if any(FEATS[key]["category"] == category for key in ACTIVE_FEAT_KEYS)
)

# metric -> [(threshold, feat_key), ...] (ascending)
PROGRESS_FEATS = {
    "tower_clears": [
        (25, "tower_regular"), (250, "tower_marathon"), (1000, "tower_millennium"),
        (1800, "tower_vanguard_1800"), (3600, "tower_paragon_3600"),
        (6000, "tower_ascendant_6000"),
    ],
    "tower_prestiges": [
        (5, "tower_dynasty"), (15, "tower_prestige_15"),
        (30, "tower_prestige_30"), (75, "tower_prestige_75"),
        (150, "tower_prestige_150"),
    ],
    "bossrush_wins": [
        (10, "boss_rush_master"), (25, "boss_rush_veteran_25"),
        (75, "boss_rush_mythic_75"), (150, "boss_rush_ascendant_150"),
    ],
    "ironman_wins": [
        (3, "ironman_relentless"), (10, "ironman_master_10"),
        (25, "ironman_mythic_25"), (50, "ironman_eternal_50"),
    ],
    "corrupted_clears": [
        (20, "corruption_cleanser"), (75, "corruption_warden_75"),
        (200, "corruption_bane_200"), (500, "corruption_extinction_500"),
    ],
    "dragon_wins": [
        (5, "dragon_veteran"), (100, "dragon_centurion"),
        (500, "dragon_eternal_foe"), (1000, "dragon_thousand"),
        (3000, "dragon_3000"), (7500, "dragon_7500"),
    ],
    "raid_wins": [
        (10, "raid_veteran"), (50, "raid_warlord"), (200, "raid_immortal"),
        (500, "raid_mythic_500"), (1000, "raid_ascendant_1000"),
    ],
    "rift_full_clears": [
        (10, "rift_perfectionist"), (25, "rift_veteran_25"),
        (52, "rift_mythic_52"), (104, "rift_ascendant_104"),
    ],
    "hunt_kills": [
        (5, "hunt_apex"), (15, "hunt_veteran_15"),
        (30, "hunt_mythic_30"), (75, "hunt_ascendant_75"),
    ],
    "gauntlet_breaks": [
        (25, "gauntlet_marauder"), (100, "gauntlet_breaker_100"),
        (250, "gauntlet_breaker_250"),
    ],
    "gauntlet_holds": [
        (25, "gauntlet_bastion"), (100, "gauntlet_hold_100"),
        (250, "gauntlet_hold_250"),
    ],
    "adventure_completions": [
        (25, "adventure_veteran"), (100, "adventure_nomad"),
        (500, "adventure_odyssey"), (750, "adventure_wayfarer_750"),
        (1500, "adventure_mythic_1500"), (2000, "adventure_worldwalker"),
        (2500, "adventure_legend_2500"), (3500, "adventure_ascendant_3500"),
    ],
    "money_balance": [
        (1_000_000, "wealth_keeper_1m"), (10_000_000, "wealth_magnate_10m"),
        (25_000_000, "wealth_titan_25m"), (50_000_000, "wealth_sovereign_50m"),
    ],
    "egg_types": [
        (10, "egg_types_10"), (25, "egg_types_25"), (50, "egg_types_50"),
        (75, "egg_types_75"), (100, "egg_types_100"),
    ],
    "perfect_egg_iv": [(100, "perfect_egg_iv")],
    "high_power_items": [
        (1, "power_150_first"), (10, "power_150_10"), (20, "power_150_20"),
        (50, "power_150_50"), (100, "power_150_100"),
    ],
    "amulet_tier": [
        (1, "amulet_tier_1"), (3, "amulet_tier_3"), (5, "amulet_tier_5"),
        (7, "amulet_tier_7"), (9, "amulet_tier_9"), (10, "amulet_tier_10"),
    ],
    "starforge_stars": [
        (1, "starforge_1"), (5, "starforge_5"), (10, "starforge_10"),
    ],
}

# feat_key -> (metric, threshold) reverse lookup for progress display
FEAT_THRESHOLDS = {
    feat_key: (metric, threshold)
    for metric, entries in PROGRESS_FEATS.items()
    for threshold, feat_key in entries
}

RIFT_ACE_SCORE = 90_000

# Percentage gates stay meaningful as the active catalog grows.
COMPLETION_RANKS = [
    (0.00, "Unproven", 0x7F8C8D),
    (0.10, "Bronze Renown", 0xB87333),
    (0.25, "Silver Renown", 0xAAB7B8),
    (0.45, "Golden Renown", 0xD4AC0D),
    (0.65, "Mythborn", 0x8E44AD),
    (0.82, "Living Legend", 0xC0392B),
    (1.00, "Ascendant", 0x5DADE2),
]


def completion_rank(unlocked_count: int, total_count: int | None = None):
    """Return ``(rank title, embed color)`` from active completion percentage."""
    total_count = len(ACTIVE_FEAT_KEYS) if total_count is None else max(0, int(total_count))
    ratio = 0.0 if total_count <= 0 else min(1.0, max(0.0, unlocked_count / total_count))
    current = COMPLETION_RANKS[0]
    for threshold_ratio, title, color in COMPLETION_RANKS:
        if ratio >= threshold_ratio:
            current = (threshold_ratio, title, color)
    return current[1], current[2]


def bar(current: int, total: int, width: int = 12) -> str:
    if total <= 0:
        return "▱" * width
    filled = int(width * max(0, min(current, total)) / total)
    return "▰" * filled + "▱" * (width - filled)


def tier_text(feat: dict) -> str:
    tier = TIERS[feat["tier"]]
    return f"{tier['pips']} {tier['label']}"


def pack_embed_lines(lines, limit: int = 950) -> list[str]:
    """Pack complete display entries without cutting Markdown mid-entry."""
    chunks, current = [], []
    size = 0
    for raw in lines:
        entry = str(raw).strip()
        if not entry:
            continue
        if len(entry) > limit:
            entry = entry[: limit - 1].rstrip() + "…"
        added = len(entry) + (1 if current else 0)
        if current and size + added > limit:
            chunks.append("\n".join(current))
            current, size = [], 0
        current.append(entry)
        size += len(entry) + (1 if len(current) > 1 else 0)
    if current:
        chunks.append("\n".join(current))
    return chunks or ["No deeds recorded."]


def _discord_day(value) -> str:
    if not isinstance(value, datetime):
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return f"<t:{int(value.timestamp())}:d>"


def _category_keys(category: str) -> list[str]:
    return [key for key in ACTIVE_FEAT_KEYS if FEATS[key]["category"] == category]


def build_feats_overview_embed(member_name: str, unlocked: dict, progress: dict) -> discord.Embed:
    """Build the compact, full-width Feats overview (safe to snapshot-test)."""
    active_unlocked = {key: ts for key, ts in unlocked.items() if key in ACTIVE_FEAT_KEYS}
    archived_unlocked = {key: ts for key, ts in unlocked.items() if key in ARCHIVED_FEAT_KEYS}
    count, total = len(active_unlocked), len(ACTIVE_FEAT_KEYS)
    percent = 0 if total <= 0 else int((count / total) * 100)
    rank_title, rank_color = completion_rank(count, total)
    lp_total = sum(int(FEATS[key]["lp"]) for key in ACTIVE_FEAT_KEYS)
    lp_earned = sum(int(FEATS[key]["lp"]) for key in active_unlocked)

    embed = discord.Embed(
        title=f"Feats · {member_name}",
        description=(
            f"**{rank_title}** · **{percent}% mastery**\n"
            f"{bar(count, total, 14)}  **{count:,} / {total:,}** active deeds\n"
            f"`{lp_earned:,} / {lp_total:,}` LP claimed from active feats"
        ),
        color=rank_color,
    )

    category_lines = []
    for category in ACTIVE_CATEGORIES:
        keys = _category_keys(category)
        done = sum(key in active_unlocked for key in keys)
        complete = " ✓" if keys and done == len(keys) else ""
        category_lines.append(
            f"{bar(done, len(keys), 6)}  `{done}/{len(keys)}` · **{category}**{complete}"
        )
    embed.add_field(name="Mastery by Path", value="\n".join(category_lines), inline=False)

    candidates = []
    for key in ACTIVE_FEAT_KEYS:
        if key in active_unlocked or key not in FEAT_THRESHOLDS:
            continue
        metric, threshold = FEAT_THRESHOLDS[key]
        current = max(0, int(progress.get(metric, 0)))
        candidates.append((current / threshold, -threshold, current, threshold, key))
    candidates.sort(reverse=True)
    if candidates:
        nearest = []
        for _ratio, _threshold_sort, current, threshold, key in candidates[:3]:
            feat = FEATS[key]
            nearest.append(
                f"○ **{feat['name']}** · {tier_text(feat)}\n"
                f"{bar(current, threshold, 8)}  `{min(current, threshold):,}/{threshold:,}` · "
                f"{feat['description']}"
            )
        embed.add_field(name="Nearest Deeds", value="\n".join(nearest), inline=False)

    if active_unlocked:
        recent = sorted(
            active_unlocked.items(), key=lambda item: item[1] or datetime.min, reverse=True
        )[:3]
        embed.add_field(
            name="Recently Earned",
            value="\n".join(
                f"✓ **{FEATS[key]['name']}** · {tier_text(FEATS[key])} {_discord_day(ts)}"
                for key, ts in recent
            ),
            inline=False,
        )

    if archived_unlocked:
        embed.add_field(
            name="Legacy Deeds",
            value="\n".join(
                f"⌁ **{FEATS[key]['name']}** · archived {_discord_day(ts)}"
                for key, ts in sorted(
                    archived_unlocked.items(), key=lambda item: item[1] or datetime.min, reverse=True
                )
            ),
            inline=False,
        )

    embed.set_footer(text="$feats all · full ledger   •   $feats top · realm standings")
    return embed


def _ledger_entry(key: str, unlocked: dict, progress: dict) -> str:
    feat = FEATS[key]
    earned = key in unlocked
    status = "✓" if earned else "○"
    progress_text = ""
    if key in FEAT_THRESHOLDS:
        metric, threshold = FEAT_THRESHOLDS[key]
        current = min(max(0, int(progress.get(metric, 0))), threshold)
        progress_text = f" · `{current:,}/{threshold:,}`"
    return (
        f"{status} **{feat['name']}** · {tier_text(feat)}{progress_text} · +{int(feat['lp']):,} LP\n"
        f"  {feat['description']}"
    )


def build_feat_ledger_pages(member_name: str, unlocked: dict, progress: dict) -> list[discord.Embed]:
    """Build two-category ledger pages without exceeding field boundaries."""
    active_unlocked = {key: ts for key, ts in unlocked.items() if key in ACTIVE_FEAT_KEYS}
    archived_unlocked = {key: ts for key, ts in unlocked.items() if key in ARCHIVED_FEAT_KEYS}
    count, total = len(active_unlocked), len(ACTIVE_FEAT_KEYS)
    _rank, color = completion_rank(count, total)
    pages = []

    for offset in range(0, len(ACTIVE_CATEGORIES), 2):
        page = discord.Embed(
            title=f"Feat Ledger · {member_name}",
            description=f"{bar(count, total, 14)}  **{count:,} / {total:,}** active deeds",
            color=color,
        )
        for category in ACTIVE_CATEGORIES[offset : offset + 2]:
            keys = _category_keys(category)
            done = sum(key in active_unlocked for key in keys)
            chunks = pack_embed_lines([_ledger_entry(key, active_unlocked, progress) for key in keys])
            for index, chunk in enumerate(chunks):
                name = f"{category} · {done}/{len(keys)}" if index == 0 else f"{category} · continued"
                page.add_field(name=name, value=chunk, inline=False)
        pages.append(page)

    if archived_unlocked:
        page = discord.Embed(
            title=f"Legacy Deeds · {member_name}",
            description="Retired deeds remain part of your history but do not affect active mastery.",
            color=0x626567,
        )
        legacy_lines = [
            f"⌁ **{FEATS[key]['name']}** · {tier_text(FEATS[key])} · {_discord_day(ts)}"
            for key, ts in sorted(
                archived_unlocked.items(), key=lambda item: item[1] or datetime.min, reverse=True
            )
        ]
        for index, chunk in enumerate(pack_embed_lines(legacy_lines)):
            page.add_field(
                name="Archived Feats" if index == 0 else "Archived Feats · continued",
                value=chunk,
                inline=False,
            )
        pages.append(page)

    for index, page in enumerate(pages, start=1):
        page.set_footer(
            text=f"Page {index}/{len(pages)} · ◇ Bronze  ◆ Silver  ✦ Gold  ✧ Mythic  ❖ Legendary  ⬖ Ascendant"
        )
    return pages


class Feats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._tables_ready = False
        self._table_lock = asyncio.Lock()

    async def ensure_tables(self):
        if self._tables_ready:
            return
        async with self._table_lock:
            if self._tables_ready:
                return
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS feats (
                        user_id BIGINT NOT NULL,
                        feat_key TEXT NOT NULL,
                        unlocked_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (user_id, feat_key)
                    );
                    """
                )
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS feat_progress (
                        user_id BIGINT NOT NULL,
                        metric TEXT NOT NULL,
                        amount BIGINT NOT NULL DEFAULT 0,
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (user_id, metric)
                    );
                    """
                )
            self._tables_ready = True

    async def cog_load(self):
        await self.ensure_tables()

    # --- Awarding -------------------------------------------------------------

    async def award_feat(self, user_id: int, feat_key: str, channel=None) -> bool:
        await self.ensure_tables()
        feat = FEATS.get(feat_key)
        if not feat or not feat.get("active", True):
            return False
        reward = int(feat.get("lp") or 0)
        legacy = self.bot.get_cog("Legacy")
        if reward > 0 and legacy is None:
            logger.warning("Deferred feat %s for user %s: Legacy cog unavailable", feat_key, user_id)
            return False

        async with self.bot.pool.acquire() as conn:
            async with conn.transaction():
                inserted = await conn.fetchval(
                    """
                    INSERT INTO feats (user_id, feat_key, unlocked_at)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT DO NOTHING
                    RETURNING TRUE
                    """,
                    int(user_id),
                    feat_key,
                )
                if inserted and reward > 0:
                    await legacy.award_points(int(user_id), reward, conn=conn)
        if not inserted:
            return False

        if channel:
            tier = TIERS[feat["tier"]]
            try:
                await channel.send(
                    f"{tier['pips']} **{tier['label']} feat unlocked** · <@{int(user_id)}>\n"
                    f"**{feat['name']}** · **+{reward:,} LP**"
                )
            except Exception:
                logger.warning("Failed to announce feat %s for user %s", feat_key, user_id, exc_info=True)
        return True

    async def add_progress(self, user_id: int, metric: str, amount: int = 1, channel=None) -> int:
        if int(amount) <= 0:
            raise ValueError("Feat progress amount must be positive")
        await self.ensure_tables()
        async with self.bot.pool.acquire() as conn:
            total = await conn.fetchval(
                """
                INSERT INTO feat_progress (user_id, metric, amount, updated_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (user_id, metric) DO UPDATE
                SET amount = feat_progress.amount + EXCLUDED.amount,
                    updated_at = NOW()
                RETURNING amount
                """,
                int(user_id),
                metric,
                int(amount),
            )
        total = int(total or 0)
        for threshold, feat_key in PROGRESS_FEATS.get(metric, []):
            if total >= threshold:
                await self.award_feat(user_id, feat_key, channel)
        return total

    async def set_progress_max(self, user_id: int, metric: str, amount: int, channel=None) -> int:
        """Raise a snapshot metric without allowing later balance/ownership loss to erase it."""
        await self.ensure_tables()
        amount = max(0, int(amount or 0))
        async with self.bot.pool.acquire() as conn:
            total = await conn.fetchval(
                """
                INSERT INTO feat_progress (user_id, metric, amount, updated_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (user_id, metric) DO UPDATE
                SET amount = GREATEST(feat_progress.amount, EXCLUDED.amount),
                    updated_at = CASE
                        WHEN EXCLUDED.amount > feat_progress.amount THEN NOW()
                        ELSE feat_progress.updated_at
                    END
                RETURNING amount
                """,
                int(user_id),
                metric,
                amount,
            )
        total = int(total or 0)
        for threshold, feat_key in PROGRESS_FEATS.get(metric, []):
            if total >= threshold:
                await self.award_feat(user_id, feat_key, channel)
        return total

    # --- Display ------------------------------------------------------------------

    async def _table_exists(self, conn, table_name: str) -> bool:
        try:
            return bool(await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", table_name))
        except Exception:
            logger.warning("Could not inspect optional table %s", table_name, exc_info=True)
            return False

    async def _native_row(self, conn, label: str, query: str, user_id: int):
        try:
            return await conn.fetchrow(query, int(user_id))
        except Exception:
            logger.warning("Skipped %s Feat reconciliation for user %s", label, user_id, exc_info=True)
            return None

    async def _reconcile_native_progress(self, user_id: int) -> None:
        """Raise persisted progress to conservative values from native game tables."""
        snapshots = {}
        async with self.bot.pool.acquire() as conn:
            if await self._table_exists(conn, "profile"):
                row = await self._native_row(
                    conn,
                    "profile",
                    'SELECT COALESCE(completed, 0) AS completed, COALESCE(money, 0) AS money '
                    'FROM profile WHERE "user" = $1',
                    user_id,
                )
                if row:
                    snapshots["adventure_completions"] = int(row["completed"] or 0)
                    snapshots["money_balance"] = int(row["money"] or 0)

            if await self._table_exists(conn, "battletower"):
                row = await self._native_row(
                    conn,
                    "Battle Tower",
                    """
                    SELECT COALESCE(prestige, 0) AS prestige,
                           COALESCE(prestige, 0) * 30
                           + GREATEST(0, LEAST(30, COALESCE(level, 1) - 1)) AS clears
                    FROM battletower WHERE id = $1
                    """,
                    user_id,
                )
                if row:
                    snapshots["tower_prestiges"] = int(row["prestige"] or 0)
                    snapshots["tower_clears"] = int(row["clears"] or 0)

            if await self._table_exists(conn, "dragon_contributions"):
                row = await self._native_row(
                    conn,
                    "Ice Dragon",
                    "SELECT COALESCE(total_defeats, 0) AS total_defeats "
                    "FROM dragon_contributions WHERE user_id = $1",
                    user_id,
                )
                if row:
                    snapshots["dragon_wins"] = int(row["total_defeats"] or 0)

            if await self._table_exists(conn, "allitems"):
                row = await self._native_row(
                    conn,
                    "high-power collection",
                    """
                    SELECT COUNT(*) FILTER (
                               WHERE COALESCE(damage, 0) + COALESCE(armor, 0) >= 150
                           ) AS power150
                    FROM allitems WHERE owner = $1
                    """,
                    user_id,
                )
                if row:
                    snapshots["high_power_items"] = int(row["power150"] or 0)

            if await self._table_exists(conn, "monster_eggs"):
                row = await self._native_row(
                    conn,
                    "egg collection",
                    'SELECT COUNT(DISTINCT egg_type) AS egg_types, '
                    'COALESCE(MAX("IV"), 0) AS max_iv FROM monster_eggs WHERE user_id = $1',
                    user_id,
                )
                if row:
                    snapshots["egg_types"] = int(row["egg_types"] or 0)
                    snapshots["perfect_egg_iv"] = int(float(row["max_iv"] or 0))

            if await self._table_exists(conn, "amulets"):
                row = await self._native_row(
                    conn,
                    "amulet crafting",
                    "SELECT COALESCE(MAX(tier), 0) AS max_tier "
                    "FROM amulets WHERE user_id = $1",
                    user_id,
                )
                if row:
                    snapshots["amulet_tier"] = int(row["max_tier"] or 0)

            if (
                await self._table_exists(conn, "starforged_items")
                and await self._table_exists(conn, "allitems")
            ):
                row = await self._native_row(
                    conn,
                    "Starforge",
                    """
                    SELECT COALESCE(MAX(sf.stars), 0) AS max_stars
                    FROM starforged_items sf
                    JOIN allitems ai ON ai.id = sf.item_id
                    WHERE ai.owner = $1
                    """,
                    user_id,
                )
                if row:
                    snapshots["starforge_stars"] = int(row["max_stars"] or 0)

            values = [
                (int(user_id), metric, max(0, int(amount or 0)))
                for metric, amount in snapshots.items()
            ]
            if values:
                await conn.executemany(
                    """
                    INSERT INTO feat_progress (user_id, metric, amount, updated_at)
                    VALUES ($1, $2, $3, NOW())
                    ON CONFLICT (user_id, metric) DO UPDATE
                    SET amount = EXCLUDED.amount, updated_at = NOW()
                    WHERE EXCLUDED.amount > feat_progress.amount
                    """,
                    values,
                )

    async def _fetch_feat_state(self, member):
        await self._reconcile_native_progress(member.id)
        async with self.bot.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT feat_key, unlocked_at FROM feats WHERE user_id = $1 ORDER BY unlocked_at DESC",
                member.id,
            )
            progress_rows = await conn.fetch(
                "SELECT metric, amount FROM feat_progress WHERE user_id = $1", member.id
            )
        unlocked = {row["feat_key"]: row["unlocked_at"] for row in rows if row["feat_key"] in FEATS}
        progress = {row["metric"]: int(row["amount"] or 0) for row in progress_rows}

        # Self-heal: progress accrued before a feat existed (or missed events)
        # unlocks silently the next time the ledger is opened.
        for metric, entries in PROGRESS_FEATS.items():
            for threshold, feat_key in entries:
                if feat_key not in unlocked and progress.get(metric, 0) >= threshold:
                    if await self.award_feat(member.id, feat_key, channel=None):
                        unlocked[feat_key] = datetime.utcnow()

        return unlocked, progress

    @commands.group(name="feats", aliases=["achievements", "ach"], invoke_without_command=True)
    @has_char()
    async def feats(self, ctx, member: discord.Member = None):
        """Your deeds, writ large. `$feats all` for the full ledger."""
        await self.ensure_tables()
        member = member or ctx.author
        unlocked, progress = await self._fetch_feat_state(member)
        await ctx.send(embed=build_feats_overview_embed(member.display_name, unlocked, progress))

    @feats.command(name="all", aliases=["list", "ledger"])
    @has_char()
    async def feats_all(self, ctx, member: discord.Member = None):
        """The full feat ledger, category by category."""
        await self.ensure_tables()
        member = member or ctx.author
        unlocked, progress = await self._fetch_feat_state(member)
        pages = build_feat_ledger_pages(member.display_name, unlocked, progress)
        await self.bot.paginator.Paginator(extras=pages, timeout=120).paginate(ctx)

    @feats.command(name="top", aliases=["leaderboard", "lb"])
    async def feats_top(self, ctx):
        """Show the Feats leaderboard."""
        await self.ensure_tables()
        async with self.bot.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT user_id, COUNT(*) AS count
                FROM feats
                WHERE feat_key = ANY($1::TEXT[])
                GROUP BY user_id
                ORDER BY count DESC, MIN(unlocked_at) ASC
                LIMIT 10
                """,
                list(ACTIVE_FEAT_KEYS),
            )
        embed = discord.Embed(
            title="Feats · Realm Standings",
            description="Active deeds only · archived feats never affect rank",
            color=0xB08D2F,
        )
        lines = []
        total = len(ACTIVE_FEAT_KEYS)
        for idx, row in enumerate(rows, start=1):
            count = int(row["count"] or 0)
            title, _color = completion_rank(count, total)
            percent = int((count / total) * 100) if total else 0
            lines.append(
                f"**{idx}.** <@{row['user_id']}> · **{count}/{total}** ({percent}%) · {title}"
            )
        embed.add_field(
            name="Top Featkeepers",
            value="\n".join(lines) or "No active feats have been earned yet.",
            inline=False,
        )
        await ctx.send(embed=embed)

    # --- Listeners ---------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_battletower_completion(
        self, ctx, success, level, level_name, name_value, minion1_name, minion2_name
    ):
        if not success:
            return
        try:
            await self.add_progress(ctx.author.id, "tower_clears", 1, ctx.channel)
            if int(level) == 30:
                await self.award_feat(ctx.author.id, "tower_conqueror", ctx.channel)
        except Exception:
            logger.exception("Feat tracking failed for Battle Tower completion")

    @commands.Cog.listener()
    async def on_battletower_prestige(self, ctx, new_prestige):
        try:
            await self.award_feat(ctx.author.id, "tower_prestige", ctx.channel)
            await self.add_progress(ctx.author.id, "tower_prestiges", 1, ctx.channel)
        except Exception:
            logger.exception("Feat tracking failed for Battle Tower prestige")

    @commands.Cog.listener()
    async def on_bossrush_completion(self, ctx, success):
        if not success:
            return
        try:
            await self.award_feat(ctx.author.id, "boss_rush_champion", ctx.channel)
            await self.add_progress(ctx.author.id, "bossrush_wins", 1, ctx.channel)
        except Exception:
            logger.exception("Feat tracking failed for Boss Rush completion")

    @commands.Cog.listener()
    async def on_ironman_completion(self, ctx, floor, success, completed):
        try:
            if completed:
                await self.award_feat(ctx.author.id, "ironman_ascendant", ctx.channel)
                await self.add_progress(ctx.author.id, "ironman_wins", 1, ctx.channel)
        except Exception:
            logger.exception("Feat tracking failed for Ironman completion")

    @commands.Cog.listener()
    async def on_corrupted_floor_cleansed(self, ctx):
        try:
            await self.add_progress(ctx.author.id, "corrupted_clears", 1, ctx.channel)
        except Exception:
            logger.exception("Feat tracking failed for corrupted floor cleanse")

    @commands.Cog.listener()
    async def on_icedragon_victory(self, ctx, party_members, stage_name, dragon_level):
        try:
            dragon_level = int(dragon_level or 0)
            for member in party_members:
                await self.award_feat(member.id, "dragon_slayer", ctx.channel)
                await self.add_progress(member.id, "dragon_wins", 1, ctx.channel)
                if dragon_level >= 35:
                    await self.award_feat(member.id, "maw_walker", ctx.channel)
                if dragon_level >= 30:
                    await self.award_feat(member.id, "maw_diver", ctx.channel)
                if dragon_level >= 40:
                    await self.award_feat(member.id, "maw_abyssal", ctx.channel)
        except Exception:
            logger.exception("Feat tracking failed for Ice Dragon victory")

    @commands.Cog.listener()
    async def on_dragon_world_record(self, ctx, party_members, new_level):
        try:
            for member in party_members:
                await self.award_feat(member.id, "world_record_holder", ctx.channel)
        except Exception:
            logger.exception("Feat tracking failed for Ice Dragon world record")

    @commands.Cog.listener()
    async def on_raid_favor(self, ctx, participant_ids, success):
        if not success:
            return
        try:
            channel = getattr(ctx, "channel", None)
            for user_id in dict.fromkeys(int(uid) for uid in participant_ids):
                await self.award_feat(user_id, "raid_victor", channel)
                await self.add_progress(user_id, "raid_wins", 1, channel)
        except Exception:
            logger.exception("Feat tracking failed for raid victory")

    @commands.Cog.listener()
    async def on_adventure_completion(self, ctx, iscompleted):
        if not iscompleted:
            return
        try:
            await self.add_progress(ctx.author.id, "adventure_completions", 1, ctx.channel)
        except Exception:
            logger.exception("Feat tracking failed for adventure completion")

    @commands.Cog.listener()
    async def on_rift_completion(self, ctx, rooms_cleared, score, full_clear, difficulty="normal"):
        if not full_clear:
            return
        try:
            await self.award_feat(ctx.author.id, "rift_sealer", ctx.channel)
            await self.add_progress(ctx.author.id, "rift_full_clears", 1, ctx.channel)
            is_ace_tier = str(difficulty or "normal").lower() in {"heroic", "mythic"}
            if is_ace_tier and int(score or 0) >= RIFT_ACE_SCORE:
                await self.award_feat(ctx.author.id, "rift_ace", ctx.channel)
        except Exception:
            logger.exception("Feat tracking failed for Rift completion")

    @commands.Cog.listener()
    async def on_hunt_beast_slain(self, ctx, participant_ids, survivor_ids, top_tracker_id):
        try:
            channel = getattr(ctx, "channel", None)
            for user_id in set(int(uid) for uid in participant_ids):
                await self.award_feat(user_id, "hunt_slayer", channel)
                await self.add_progress(user_id, "hunt_kills", 1, channel)
            if top_tracker_id:
                await self.award_feat(int(top_tracker_id), "hunt_pathfinder", channel)
        except Exception:
            logger.exception("Feat tracking failed for Hunt completion")

    @commands.Cog.listener()
    async def on_traitorraid_completion(self, ctx, innocent_ids, traitor_id, innocents_win):
        # The host-managed Traitor Raid explicitly emits no automatic rewards.
        # Keep the signature for compatibility, but archived feats never advance.
        logger.debug("Ignored Traitor Raid completion because its feats are archived")

    @commands.Cog.listener()
    async def on_gauntlet_completion(self, ctx, attacker_id, defender_id, attacker_won):
        try:
            if attacker_won:
                await self.award_feat(int(attacker_id), "gauntlet_breaker", ctx.channel)
                await self.add_progress(int(attacker_id), "gauntlet_breaks", 1, ctx.channel)
            else:
                await self.award_feat(int(defender_id), "gauntlet_wall", ctx.channel)
                await self.add_progress(int(defender_id), "gauntlet_holds", 1, ctx.channel)
        except Exception:
            logger.exception("Feat tracking failed for Gauntlet completion")

    @commands.Cog.listener()
    async def on_relic_set_completed(self, user_id, set_key, channel):
        try:
            await self.award_feat(int(user_id), "relic_curator", channel)
        except Exception:
            logger.exception("Feat tracking failed for relic set completion")

    @commands.Cog.listener()
    async def on_relic_milestone_completed(
        self, user_id, set_key, milestone_key, channel
    ):
        feat_key = {
            "attuned": "relic_attuned",
            "exalted": "relic_exalted",
            "ascendant": "relic_ascendant",
        }.get(str(milestone_key or "").lower())
        if feat_key is None:
            return
        try:
            await self.award_feat(int(user_id), feat_key, channel)
        except Exception:
            logger.exception(
                "Feat tracking failed for relic milestone %s in set %s",
                milestone_key,
                set_key,
            )

    @commands.Cog.listener()
    async def on_amulet_crafted(self, ctx, type_, tier):
        try:
            await self.set_progress_max(
                ctx.author.id, "amulet_tier", int(tier), getattr(ctx, "channel", None)
            )
        except Exception:
            logger.exception("Feat tracking failed for amulet craft")

    @commands.Cog.listener()
    async def on_starforge_success(self, ctx, item_id, stars):
        try:
            await self.set_progress_max(
                ctx.author.id, "starforge_stars", int(stars), getattr(ctx, "channel", None)
            )
        except Exception:
            logger.exception("Feat tracking failed for Starforge success")

    @commands.Cog.listener()
    async def on_soulbound_awakened(self, user_id, level, channel):
        try:
            if int(level) >= 50:
                await self.award_feat(int(user_id), "soulbound_eternal", channel)
        except Exception:
            logger.exception("Feat tracking failed for soulbound awakening")

    @commands.Cog.listener()
    async def on_favorwar_season_won(self, winning_god, contributor_ids, channel):
        try:
            for user_id in dict.fromkeys(int(uid) for uid in contributor_ids):
                await self.award_feat(user_id, "god_champion", channel)
        except Exception:
            logger.exception("Feat tracking failed for Favor War season")


async def setup(bot):
    await bot.add_cog(Feats(bot))
