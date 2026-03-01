from __future__ import annotations

"""
NewWerewolf role availability configuration.

How to use:
1) Disable a role globally:
   Add role token(s) to DISABLED_ROLES, e.g. {"witch", "flutist"}.

2) Restrict a role to specific modes:
   Add an entry in ROLE_MODE_ALLOWLIST, e.g.
   {"jailer": {"idlerpg", "custom"}}

Valid mode tokens:
- classic
- imbalanced
- huntergame
- villagergame
- valentines
- idlerpg
- custom

Role tokens are case-insensitive and punctuation-insensitive.
Example tokens:
- "white wolf"
- "White_Wolf"
- "whitewolf"
All normalize to the same role key.

Notes:
- `werewolf` and `villager` are always kept available internally so games remain valid.
"""

DISABLED_ROLES: set[str] = set()

NON_CLASSIC_MODES: set[str] = {
    "imbalanced",
    "huntergame",
    "villagergame",
    "valentines",
    "idlerpg",
    "custom",
}

# Roles in this list are excluded from Classic but still available elsewhere.
CLASSIC_EXCLUDED_ROLES: set[str] = {
    "big_bad_wolf",
    "cursed_wolf_father",
    "wolf_necromancer",
    "alpha_werewolf",
    "pure_soul",
    "amor",
    "hunter",
    "healer",
    "the_old",
    "sister",
    "brother",
    "fox",
    "judge",
    "knight",
    "maid",
    "thief",
    "paragon",
    "ritualist",
    "troublemaker",
    "lawyer",
    "war_veteran",
    "white_wolf",
    "wolfhound",
    "raider",
    "flutist",
    "superspreader",
    "nightmare_werewolf",
    "voodoo_werewolf",
    "wolf_summoner",
}

ROLE_MODE_ALLOWLIST: dict[str, set[str]] = {
    role: set(NON_CLASSIC_MODES) for role in CLASSIC_EXCLUDED_ROLES
}

# Base-role -> unlock tiers mapping for role progression.
# Example:
#   "flower_child": {5: "pacifist", 10: "some_second_advanced_role"}
# Means:
#   - at level 5, player may choose Pacifist instead of Flower Child
#   - at level 10, player may also choose the second advanced role
ADVANCED_ROLE_TIERS: dict[str, dict[int, str]] = {
    "flower_child": {5: "pacifist"},
    "priest": {5: "marksman"},
    "nightmare_werewolf": {5: "voodoo_werewolf"},
    "jailer": {5: "warden"},
    "medium": {5: "ritualist"},
    "detective": {5: "mortician"},
    "bodyguard": {5: "seer_apprentice", 10: "tough_guy"},
    "guardian_wolf": {5: "wolf_pacifist"},
    "wolf_shaman": {5: "wolf_trickster"},
    "wolf_seer": {5: "sorcerer"},
    "red_lady": {5: "ghost_lady"},
    "cursed": {5: "grave_robber"},
    "loudmouth": {5: "fortune_teller"},
    "aura_seer": {5: "gambler"},
    "seer": {5: "analyst"},
    "junior_werewolf": {5: "kitten_wolf"},
    "grumpy_grandma": {5: "preacher"},
    "avenger": {5: "oathkeeper"},
    "alpha_werewolf": {5: "wolf_summoner"},
    "witch": {5: "forger"},
    "doctor": {5: "butcher"},
    "head_hunter": {5: "serial_killer"},
    "jester": {5: "cannibal"},
}

# Role progression tuning:
MAX_ROLE_LEVEL: int = 10
FIRST_ADVANCED_UNLOCK_LEVEL: int = 5
SECOND_ADVANCED_UNLOCK_LEVEL: int = 10
ROLE_XP_PER_LEVEL: int = 100
ROLE_XP_WIN: int = 90
ROLE_XP_WIN_ALIVE: int = 100
ROLE_XP_LOSS: int = 20
ROLE_XP_LONER_WIN: int = 150

# XP grant policy:
# - XP is granted only for GM-started games (if ROLE_XP_REQUIRE_GM_START=True)
# - and only in configured channels. If ROLE_XP_CHANNEL_IDS is empty, NewWerewolf
#   falls back to config.game.official_tournament_channel_id.
ROLE_XP_REQUIRE_GM_START: bool = True
ROLE_XP_CHANNEL_IDS: set[int] = {1458644607893246024}
