from decimal import Decimal

import discord
from discord.ext import commands
import asyncio
import random
from datetime import datetime, timedelta
from collections import deque

from cogs.shard_communication import user_on_cooldown
from utils.checks import has_char, is_gm, is_patreon
from utils.i18n import _
from utils import misc as rpgtools
from classes.warrior import (
    WARRIOR_EVOLUTION_LEVELS,
    WARRIOR_MOMENTUM_CAP,
    resolve_warrior_attack,
    warrior_damage_reduction_pct,
)

class IceDragonChallenge(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        ids_section = getattr(self.bot.config, "ids", None)
        dragon_ids = getattr(ids_section, "icedragonchallenge", {}) if ids_section else {}
        if not isinstance(dragon_ids, dict):
            dragon_ids = {}
        self.allowed_guild_id = dragon_ids.get(
            "allowed_guild_id", self.bot.config.game.support_server_id
        )
        self.reset_channel_id = dragon_ids.get("reset_channel_id")
        self.party_category_id = dragon_ids.get("party_category_id")
        self.party_deny_role_id = dragon_ids.get("party_deny_role_id")
        self.dragon_level = 1
        self.weekly_defeats = 0
        self.current_parties = {}
        self.unlocked = True
        self.last_reset = datetime.utcnow()

        # Dragon evolution stages
        self.DRAGON_STAGES = {
            "Frostbite Wyrm": {
                "level_range": (1, 5),
                "moves": {
                    "Ice Breath": {"dmg": 600, "effect": "freeze", "chance": 0.3},
                    "Tail Sweep": {"dmg": 400, "effect": "aoe", "chance": 0.4},
                    "Frost Bite": {"dmg": 300, "effect": "dot", "chance": 0.3}
                },
                "passives": ["Ice Armor"],
                "base_multiplier": 1.0
            },
            "Corrupted Ice Dragon": {
                "level_range": (6, 10),
                "moves": {
                    "Frosty Ice Burst": {"dmg": 800, "effect": "random_debuff", "chance": 0.3},
                    "Minion Army": {"dmg": 200, "effect": "summon_adds", "chance": 0.3},
                    "Frost Spears": {"dmg": 500, "effect": "dot", "chance": 0.4}
                },
                "passives": ["Corruption"],
                "base_multiplier": 1.15
            },
            "Permafrost": {
                "level_range": (11, 15),
                "moves": {
                    "Soul Reaver": {"dmg": 1000, "effect": "stun", "chance": 0.3},
                    "Death Note": {"dmg": 700, "effect": "curse", "chance": 0.3},
                    "Dark Shadows": {"dmg": 900, "effect": "aoe_dot", "chance": 0.4}
                },
                "passives": ["Void Fear"],
                "base_multiplier": 1.35
            },
            "Deathwing": {
                "level_range": (16, 24),
                "moves": {
                    "Spirit Drain": {"dmg": 1200, "effect": "steal_buffs", "chance": 0.3},
                    "Reaper's Verdic": {"dmg": 1500, "effect": "execute", "chance": 0.3},
                    "Voidrend Annihilation": {"dmg": 1000, "effect": "arena_hazard", "chance": 0.4}
                },
                "passives": ["Aspect of death"],
                "base_multiplier": 1.75
            },
            "The Abyssal Maw": {
                # Endless stage: never evolves again, just keeps scaling with level
                "level_range": (25, 9999),
                "moves": {
                    "Abyssal Devour": {"dmg": 1800, "effect": "execute", "chance": 0.25},
                    "Maw of the Void": {"dmg": 1200, "effect": "aoe_dot", "chance": 0.35},
                    "Frozen Oblivion": {"dmg": 1400, "effect": "freeze", "chance": 0.25},
                    "Endless Hunger": {"dmg": 900, "effect": "steal_buffs", "chance": 0.15}
                },
                "passives": ["Abyssal Presence"],
                "base_multiplier": 2.2
            }
        }

        # Stage-specific rewards
        self.STAGE_REWARDS = {
            "Frostbite Wyrm": {
                "items": [
                    ("Frozen Blade", "sword", 60, 80, 10000),
                    ("Ice Scale Shield", "shield", 60, 80, 10000),
                    ("Frost Warhammer", "hammer", 60, 80, 1000)
                ],
                "snowflakes": 175
            },
            "Corrupted Ice Dragon": {
                "items": [
                    ("Corrupted Present Sword", "sword", 65, 80, 10000),
                    ("Evil Toy Shield", "shield", 70, 80, 10000),
                    ("Dark Gift Bow", "bow", 170, 185, 10000)
                ],
                "snowflakes": 300
            },
            "Permafrost": {
                "items": [
                    ("Krampus Chain scythe", "scythe", 180, 185, 10000),
                    ("Punishment Plate", "shield", 80, 85, 10000),
                    ("fortune", "crate", 700)
                ],
                "snowflakes": 600
            },
            "Deathwing": {
                "items": [
                    ("World Ender", "wand", 80, 100, 10000),
                    ("Void Christmas shield", "shield", 80, 100, 10000),
                    ("Crown of Winter's Death", "axe", 80, 100, 10000)
                ],
                "snowflakes": 900
            },
            "The Abyssal Maw": {
                "items": [
                    ("Maw of Endless Winter", "scythe", 190, 200, 10000),
                    ("Abyssal Bulwark", "shield", 90, 110, 10000),
                    ("Voidglass Fang", "sword", 90, 110, 10000),
                    ("divine", "crate", 800)
                ],
                "snowflakes": 1500
            }
        }

        # Weekly mutators: 2 are active each weekly cycle, seeded by the cycle's
        # reset date so every party fights the same modifiers until the next reset.
        self.MUTATORS = {
            "reflective_scales": {
                "name": "Reflective Scales",
                "emoji": "🪞",
                "description": "10% of the damage you deal to the dragon is reflected back at you.",
                "effects": {"reflect_pct": 0.10},
            },
            "frenzied": {
                "name": "Frenzied",
                "emoji": "🔥",
                "description": "The dragon deals 25% more damage, but has 15% less HP.",
                "effects": {"dragon_damage_mult": 1.25, "dragon_hp_mult": 0.85},
            },
            "glacial_bulwark": {
                "name": "Glacial Bulwark",
                "emoji": "🧊",
                "description": "The dragon has 30% more HP, but deals 10% less damage.",
                "effects": {"dragon_hp_mult": 1.30, "dragon_damage_mult": 0.90},
            },
            "razor_winds": {
                "name": "Razor Winds",
                "emoji": "🌪️",
                "description": "The dragon's attacks ignore 30% of your armor.",
                "effects": {"armor_pierce": 0.30},
            },
            "volatile_magic": {
                "name": "Volatile Magic",
                "emoji": "⚡",
                "description": "The dragon uses its special moves far more often.",
                "effects": {"special_chance": 0.65},
            },
            "hoard_fever": {
                "name": "Hoard Fever",
                "emoji": "💰",
                "description": "The dragon's hoard spills over: loot drop chance is quadrupled.",
                "effects": {"loot_mult": 4.0},
            },
            "thin_ice": {
                "name": "Thin Ice",
                "emoji": "🕳️",
                "description": "Everyone fights on thin ice: the dragon and all players take 15% more damage.",
                "effects": {"mutual_damage_mult": 1.15},
            },
            "enduring_frost": {
                "name": "Enduring Frost",
                "emoji": "❄️",
                "description": "Freezes and stuns last one extra round.",
                "effects": {"status_duration_bonus": 1},
            },
        }

    async def get_current_stage(self, dragon_level=None):
        """Get current dragon stage based on level"""
        if dragon_level is None:
            async with self.bot.pool.acquire() as conn:
                result = await conn.fetchval(
                    'SELECT current_level FROM dragon_progress WHERE id = 1'
                )
                dragon_level = result if result else 1

        for stage, data in self.DRAGON_STAGES.items():
            min_level, max_level = data["level_range"]
            if min_level <= dragon_level <= max_level:
                return stage, data
        return list(self.DRAGON_STAGES.items())[-1]  # Return final stage if above all ranges

    def get_weekly_mutators(self, last_reset=None):
        """Pick this cycle's 2 mutators, seeded by the weekly reset date.

        Deterministic: same result across restarts and for every party in the
        same cycle, and it rerolls exactly when the dragon resets.
        """
        if last_reset:
            seed_token = last_reset.strftime("%Y-%m-%d")
        else:
            iso = datetime.utcnow().isocalendar()
            seed_token = f"{iso[0]}-W{iso[1]}"
        rng = random.Random(f"idc-mutators-{seed_token}")
        return rng.sample(sorted(self.MUTATORS), 2)

    def compute_mutator_effects(self, mutator_keys):
        """Flatten the active mutators into a single effects dict used in combat."""
        effects = {
            "dragon_damage_mult": 1.0,
            "dragon_hp_mult": 1.0,
            "mutual_damage_mult": 1.0,
            "loot_mult": 1.0,
            "reflect_pct": 0.0,
            "armor_pierce": 0.0,
            "special_chance": 0.4,
            "status_duration_bonus": 0,
        }
        for key in mutator_keys:
            for stat, value in self.MUTATORS[key]["effects"].items():
                if stat in ("dragon_damage_mult", "dragon_hp_mult", "mutual_damage_mult", "loot_mult"):
                    effects[stat] *= value
                elif stat == "special_chance":
                    effects[stat] = max(effects[stat], value)
                else:  # reflect_pct, armor_pierce, status_duration_bonus
                    effects[stat] += value
        return effects

    def describe_mutators(self, mutator_keys):
        """Display lines for the active mutators."""
        return [
            f"{self.MUTATORS[key]['emoji']} **{self.MUTATORS[key]['name']}** — {self.MUTATORS[key]['description']}"
            for key in mutator_keys
            if key in self.MUTATORS
        ]

    # --- Class specialization support (simple-engine subset) ---------------------
    # Combatants here are dicts, not Combatant objects, so the spec effects are
    # resolved locally instead of via cogs/battles/extensions/specs.py.

    BARD_EVOLUTION_LEVELS = {
        "Busker": 1,
        "Minstrel": 2,
        "Skald": 3,
        "Troubadour": 4,
        "Songweaver": 5,
        "Virtuoso": 6,
        "Maestro": 7,
    }
    BEASTMASTER_EVOLUTION_LEVELS = {
        "Wrangler": 1,
        "Beast Kin": 2,
        "Packmate": 3,
        "Wildcaller": 4,
        "Alphabond": 5,
        "Feralheart": 6,
        "Beastlord": 7,
    }
    REAPER_EVOLUTION_LEVELS = {
        "Deathshroud": 1, "Soul Warden": 2, "Reaper": 3,
        "Phantom Scythe": 4, "Soul Snatcher": 5,
        "Deathbringer": 6, "Grim Reaper": 7,
    }
    SANTA_EVOLUTION_LEVELS = {
        "Little Helper": 1, "Gift Gatherer": 2, "Holiday Aide": 3,
        "Joyful Jester": 4, "Yuletide Guardian": 5,
        "Festive Enforcer": 6, "Festive Champion": 7,
    }
    SANTA_LIFESTEAL_PCT = {1: 5, 2: 7, 3: 10, 4: 12, 5: 15, 6: 18, 7: 20}
    REAPER_DEATH_CHANCE = {1: 10, 2: 15, 3: 20, 4: 25, 5: 30, 6: 35, 7: 40}
    # Mage Fireball in the Ice Dragon loop mirrors the modern engine: a charge
    # builds each turn and, when full, that attack casts a boosted Fireball
    # (which also detonates any Overload/Arcane Surge charges).
    MAGE_EVOLUTION_LEVELS = {
        "Juggler": 1,
        "Witcher": 2,
        "Enchanter": 3,
        "Mage": 4,
        "Warlock": 5,
        "Dark Caster": 6,
        "White Sorcerer": 7,
    }
    MAGE_FIREBALL_MULTIPLIER = {
        1: 1.10, 2: 1.20, 3: 1.30, 4: 1.50, 5: 1.75, 6: 2.00, 7: 2.10,
    }
    MAGE_FIREBALL_CHARGE_PER_TURN = 0.34  # ≈ one Fireball every three turns

    def _bard_grade(self, classes):
        return max((self.BARD_EVOLUTION_LEVELS.get(class_name, 0) for class_name in classes or []), default=0)

    def _beastmaster_grade(self, classes):
        return max((self.BEASTMASTER_EVOLUTION_LEVELS.get(class_name, 0) for class_name in classes or []), default=0)

    def _reaper_grade(self, classes):
        return max((self.REAPER_EVOLUTION_LEVELS.get(class_name, 0) for class_name in classes or []), default=0)

    def _santa_grade(self, classes):
        return max((self.SANTA_EVOLUTION_LEVELS.get(class_name, 0) for class_name in classes or []), default=0)

    def _warrior_grade(self, classes):
        return max((WARRIOR_EVOLUTION_LEVELS.get(class_name, 0) for class_name in classes or []), default=0)

    @staticmethod
    def get_spec_fx(entity):
        if entity.get("is_pet"):
            return {}
        return entity.get("spec_effects") or {}

    @staticmethod
    def _ice_name(entity):
        return entity["user"].display_name if not entity.get("is_pet") else entity.get("pet_name", "Pet")

    def _ice_class_status(self, entity):
        if entity.get("is_pet"):
            return ""
        lines = []
        if entity.get("reaper_evolution"):
            avatar = int(entity.get("reaper_avatar_hits", 0) or 0)
            lines.append(
                f"☠️ Avatar of Death: {avatar}/3"
                if avatar
                else f"☠️ Souls: {int(entity.get('reaper_souls', 0) or 0)}/5"
            )
            ward_fx = self.get_spec_fx(entity).get("soul_ward_lifesteal_pct")
            if ward_fx:
                ward_cap = float(entity.get("soul_ward_cap", 0) or 0)
                if ward_cap <= 0:
                    ward_cap = float(entity.get("max_hp", 0) or 0) * float(ward_fx.get("ward_value", 0)) / 100
                lines.append(
                    f"🌑 Soul Ward: {float(entity.get('soul_ward', 0) or 0):,.1f}/"
                    f"{ward_cap:,.1f}"
                )
        if entity.get("santa_evolution"):
            lines.append(
                f"🎁 Cheer: {int(entity.get('santa_cheer', 0) or 0)}/3 · "
                f"Golden Gift: {int(entity.get('santa_gifts_opened', 0) or 0) % 3}/3"
            )
            if "christmas_miracle_pct" in self.get_spec_fx(entity):
                state = "Spent" if entity.get("winterlight_miracle_used") else "Ready"
                lines.append(f"🕊️ Christmas Miracle: {state}")
        if entity.get("warrior_evolution"):
            momentum = int(entity.get("warrior_momentum", 0) or 0)
            state = "Crushing Blow ready" if momentum >= WARRIOR_MOMENTUM_CAP else f"{momentum}/{WARRIOR_MOMENTUM_CAP}"
            lines.append(f"⚔️ Momentum: {state}")
        return "\n".join(lines)

    def apply_ice_warrior_attack(self, entity, damage, *, is_fireball=False):
        if is_fireball or entity.get("is_pet") or not entity.get("warrior_evolution"):
            return float(damage), []
        effects = self.get_spec_fx(entity)
        roll = random.random() if "warrior_relentless_pct" in effects else None
        state = resolve_warrior_attack(
            entity["warrior_evolution"],
            entity.get("warrior_momentum", 0),
            effects,
            roll=roll,
        )
        entity["warrior_momentum"] = int(state["next_momentum"])
        entity["warrior_last_crushing"] = bool(state["crushing_blow"])
        if state.get("brace_stacks"):
            entity["warrior_brace_stacks"] = int(state["brace_stacks"])
        modified = float(Decimal(str(damage)) * Decimal(str(state["multiplier"])))
        name = self._ice_name(entity)
        if state["crushing_blow"]:
            return round(modified, 2), [
                f"⚔️ **{name}** unleashes **Crushing Blow** for +{state['bonus_pct']}% damage!"
            ]
        if state["extra_stack"]:
            return round(modified, 2), [
                f"⚔️ **{name}**'s Relentless Assault surges to "
                f"**{entity['warrior_momentum']}/{WARRIOR_MOMENTUM_CAP} Momentum**!"
            ]
        return round(modified, 2), [
            f"⚔️ **{name}** builds Momentum "
            f"(**{entity['warrior_momentum']}/{WARRIOR_MOMENTUM_CAP}**)."
        ]

    @staticmethod
    def _tick_ice_krampus_weakness(dragon, action_log=None):
        hits = int(dragon.get("krampus_weakness_hits", 0) or 0)
        if hits <= 0:
            return
        hits -= 1
        dragon["krampus_weakness_hits"] = hits
        if hits <= 0:
            dragon["krampus_weakness_pct"] = 0.0
            if action_log is not None:
                action_log.append("⛓️ Krampus's chains release the Ice Dragon.")

    def _ice_heal_with_ward(self, entity, amount, effect=None):
        amount = max(0.0, float(amount or 0))
        before = float(entity["hp"])
        entity["hp"] = min(float(entity["max_hp"]), before + amount)
        healed = max(0.0, float(entity["hp"]) - before)
        overflow = max(0.0, amount - healed)
        ward_gain = 0.0
        if effect and overflow > 0:
            cap = float(entity["max_hp"]) * float(effect.get("ward_value", 0)) / 100
            current = float(entity.get("soul_ward", 0) or 0)
            ward_gain = max(0.0, min(overflow, cap - current))
            entity["soul_ward"] = current + ward_gain
            entity["soul_ward_cap"] = cap
        return healed, ward_gain

    def apply_ice_seasonal_attack(self, entity, dragon, battle_participants, damage):
        if entity.get("is_pet"):
            return 0.0, []
        name = self._ice_name(entity)
        messages = []
        extra_damage = 0.0
        effects = self.get_spec_fx(entity)
        reaper_level = int(entity.get("reaper_evolution", 0) or 0)

        avatar_hits = int(entity.get("reaper_avatar_hits", 0) or 0)
        if reaper_level and avatar_hits > 0 and float(dragon["hp"]) > 0:
            damage_pct = {1: 15, 2: 18, 3: 21, 4: 24, 5: 28, 6: 31, 7: 35}[reaper_level]
            avatar_damage = float(entity["damage"]) * damage_pct / 100
            extra_damage += avatar_damage
            drain_pct = {1: 8, 2: 10, 3: 12, 4: 14, 5: 16, 6: 18, 7: 20}[reaper_level]
            healed, _ward = self._ice_heal_with_ward(
                entity,
                float(entity["damage"]) * drain_pct / 100,
                effects.get("soul_ward_lifesteal_pct"),
            )
            entity["reaper_avatar_hits"] = avatar_hits - 1
            messages.append(
                f"☠️ **{name}**, Avatar of Death, reaps for **{avatar_damage:,.1f}HP** "
                f"and drains **{healed:,.1f}HP**!"
            )
            if entity["reaper_avatar_hits"] <= 0:
                messages.append(f"☠️ **{name}**'s Avatar of Death fades.")

        verdict = effects.get("death_verdict_pct")
        if (
            verdict
            and not entity.get("death_verdict_used")
            and float(dragon["hp"]) > 0
            and float(dragon["hp"]) / max(1.0, float(dragon["max_hp"])) <= float(verdict.get("threshold", 0.20))
        ):
            weapon = float(entity["damage"]) * float(verdict["value"]) / 100
            vitality = min(
                float(dragon["max_hp"]) * float(verdict.get("hp_value", 0)) / 100,
                float(entity["damage"]) * float(verdict.get("hp_damage_cap", 1.0)),
            )
            verdict_damage = weapon + vitality
            extra_damage += verdict_damage
            entity["death_verdict_used"] = True
            messages.append(f"⚰️ **DEATH'S VERDICT!** **{name}** condemns the dragon for **{verdict_damage:,.1f}HP**!")

        soulbinder = effects.get("soul_ward_lifesteal_pct")
        if soulbinder:
            healed, ward = self._ice_heal_with_ward(
                entity,
                float(entity["damage"]) * float(soulbinder["value"]) / 100,
                soulbinder,
            )
            if healed > 0 or ward > 0:
                messages.append(
                    f"🌑 Dominion of Souls restores **{healed:,.1f}HP** and binds **{ward:,.1f}HP** into Soul Ward."
                )

        if reaper_level and avatar_hits <= 0:
            souls = min(5, int(entity.get("reaper_souls", 0) or 0) + 1)
            entity["reaper_souls"] = souls
            if souls >= 5:
                entity["reaper_souls"] = 0
                entity["reaper_avatar_hits"] = 3
                messages.append(f"☠️ **{name}** becomes the **AVATAR OF DEATH** for three attacks!")
            else:
                messages.append(f"☠️ **{name}** harvests a soul (**{souls}/5**).")

        santa_level = int(entity.get("santa_evolution", 0) or 0)
        krampus = effects.get("naughty_chain_pct")
        if santa_level and krampus:
            stacks = int(entity.get("krampus_naughty_stacks", 0) or 0) + 1
            threshold = int(krampus.get("stacks", 3))
            if stacks >= threshold:
                entity["krampus_naughty_stacks"] = 0
                chain_damage = float(entity["damage"]) * float(krampus["value"]) / 100
                extra_damage += chain_damage
                entity["santa_force_crimson"] = True
                dragon["krampus_weakness_pct"] = max(
                    float(dragon.get("krampus_weakness_pct", 0) or 0),
                    float(krampus.get("reduction_value", 0)) / 100,
                )
                dragon["krampus_weakness_hits"] = max(
                    int(dragon.get("krampus_weakness_hits", 0) or 0),
                    int(krampus.get("duration", 2)),
                )
                messages.append(f"⛓️ **CHAINS OF THE NAUGHTY!** Krampus strikes for **{chain_damage:,.1f}HP**!")
            else:
                entity["krampus_naughty_stacks"] = stacks
                messages.append(f"😈 The dragon joins **{name}**'s Naughty List (**{stacks}/{threshold}**).")

        if santa_level:
            santa_drain = float(damage) * self.SANTA_LIFESTEAL_PCT[santa_level] / 100
            healed, _ward = self._ice_heal_with_ward(entity, santa_drain)
            if healed > 0:
                messages.append(f"🍬 Peppermint Drain restores **{healed:,.1f}HP**.")

            cheer = int(entity.get("santa_cheer", 0) or 0) + 1
            if cheer < 3:
                entity["santa_cheer"] = cheer
                messages.append(f"🎁 **{name}** gathers Cheer (**{cheer}/3**).")
            else:
                entity["santa_cheer"] = 0
                opened = int(entity.get("santa_gifts_opened", 0) or 0) + 1
                entity["santa_gifts_opened"] = opened
                golden = opened % 3 == 0
                winterlight = effects.get("christmas_miracle_pct")
                support_mult = float(winterlight.get("gift_multiplier", 1.0)) if winterlight else 1.0
                golden_mult = 1.5 if golden else 1.0
                living = [ally for ally in battle_participants if float(ally.get("hp", 0)) > 0]
                if golden:
                    gifts = ["crimson", "evergreen", "starlight"]
                    entity["santa_force_crimson"] = False
                    messages.append(f"🌟 **GOLDEN GIFT!** **{name}** unleashes every wonder at once!")
                elif entity.pop("santa_force_crimson", False):
                    gifts = ["crimson"]
                elif winterlight and any(float(ally["hp"]) < float(ally["max_hp"]) for ally in living):
                    gifts = [random.choice(["evergreen"] * 5 + ["starlight"] * 3 + ["crimson"] * 2)]
                else:
                    gifts = [random.choice(["crimson", "evergreen", "starlight"])]

                if "crimson" in gifts:
                    crimson_pct = {1: 15, 2: 20, 3: 25, 4: 28, 5: 30, 6: 33, 7: 35}[santa_level]
                    gift_damage = float(entity["damage"]) * crimson_pct / 100 * golden_mult
                    extra_damage += gift_damage
                    messages.append(f"🎁 Crimson Present bursts for **{gift_damage:,.1f}HP**!")
                if living and "evergreen" in gifts:
                    recipient = min(living, key=lambda ally: float(ally["hp"]) / max(1.0, float(ally["max_hp"])))
                    heal_pct = {1: 2.5, 2: 3, 3: 3.5, 4: 4, 5: 4.5, 6: 5.2, 7: 6}[santa_level]
                    before = float(recipient["hp"])
                    recipient["hp"] = min(
                        float(recipient["max_hp"]),
                        before + float(recipient["max_hp"]) * heal_pct / 100 * support_mult * golden_mult,
                    )
                    messages.append(f"🎁 Evergreen Present restores **{float(recipient['hp']) - before:,.1f}HP** to **{self._ice_name(recipient)}**!")
                if living and "starlight" in gifts:
                    shield_pct = {1: 1.5, 2: 2, 3: 2.4, 4: 2.8, 5: 3.2, 6: 3.6, 7: 4}[santa_level]
                    total_shield = 0.0
                    for ally in living:
                        cap = float(ally["max_hp"]) * 0.25
                        current = float(ally.get("gift_shield", 0) or 0)
                        gain = min(
                            float(ally["max_hp"]) * shield_pct / 100 * support_mult * golden_mult,
                            max(0.0, cap - current),
                        )
                        ally["gift_shield"] = current + gain
                        total_shield += gain
                    messages.append(f"🎁 Starlight Present wraps the party in **{total_shield:,.1f}HP** of shields!")

        if extra_damage > 0:
            dragon["hp"] = round(max(0, float(dragon["hp"]) - extra_damage), 2)
        return extra_damage, messages

    def apply_offensive_specs(self, entity, dragon, damage, is_fireball=False):
        """Attacker-side spec bonuses on a player's dragon hit. Returns (damage, messages).

        On a Fireball turn (``is_fireball``) Overload detonates its banked charges
        instead of building one — mirroring the modern engine.
        """
        fx = self.get_spec_fx(entity)
        messages = []
        if not fx:
            return damage, messages
        name = entity["user"].display_name
        damage = float(damage)

        eff = fx.get("unbroken_will_pct")
        unbroken_hits = int(entity.get("spec_unbroken_damage_hits", 0) or 0)
        if eff and unbroken_hits > 0:
            damage = round(damage * (1 + eff["value"] / 100), 2)
            entity["spec_unbroken_damage_hits"] = unbroken_hits - 1
            messages.append(f"🛡️ **{name}** fights with Unbroken Will!")

        eff = fx.get("first_strike_bonus_pct")
        if eff and not entity.get("spec_first_strike_used"):
            entity["spec_first_strike_used"] = True
            damage = round(damage * (1 + eff["value"] / 100), 2)
            messages.append(f"🗡️ **{name}** strikes from the shadows — Ambush!")

        eff = fx.get("proc_bonus_damage_pct")
        if eff and random.random() < eff.get("chance", 0.20):
            damage = round(damage * (1 + eff["value"] / 100), 2)
            messages.append(f"⚔️ **{name}**'s Onslaught surges!")

        max_hp = float(dragon.get("max_hp", 0) or 0)
        hp_ratio = float(dragon["hp"]) / max_hp if max_hp else 0.0

        eff = fx.get("high_hp_bonus_pct")
        if eff and hp_ratio >= eff.get("threshold", 0.70):
            damage = round(damage * (1 + eff["value"] / 100), 2)
            messages.append(f"⚖️ **{name}** passes Judgement on the unbowed!")

        eff = fx.get("execute_bonus_pct")
        if eff and hp_ratio <= eff.get("threshold", 0.25):
            damage = round(damage * (1 + eff["value"] / 100), 2)
            messages.append(f"☠️ **{name}** moves in for the Execution!")

        # Dragonheart: the Ice Dragon is always a dragon boss
        eff = fx.get("boss_damage_pct")
        if eff:
            damage = round(damage * (1 + eff["value"] / 100), 2)
            if not entity.get("spec_dragonheart_shown"):
                entity["spec_dragonheart_shown"] = True
                messages.append(f"🐉 **{name}**'s Slayer instincts ignite against the dragon!")

        eff = fx.get("perfect_form_pct")
        if eff:
            hp_ratio = hp_ratio if max_hp else 1.0
            if hp_ratio <= eff.get("threshold", 0.25):
                execute_value = eff.get("execute_value", eff["value"] + eff.get("execute_bonus", 6))
                damage = round(damage * (1 + execute_value / 100), 2)
                messages.append(f"✨ **{name}** assumes Perfect Form — execution stance!")
            else:
                damage = round(damage * (1 + eff["value"] / 100), 2)
                messages.append(f"✨ **{name}** assumes Perfect Form — boss stance!")

        # Overload (Arcane Surge): normal hits ramp and build a charge; a Fireball
        # spends every charge for a burst, then resets (matches the modern engine).
        eff = fx.get("arcane_ramp_pct")
        if eff:
            stacks = int(entity.get("spec_arcane_stacks", 0) or 0)
            if is_fireball:
                if stacks > 0:
                    bonus = eff.get("detonate_per_stack", 20) * stacks / 100
                    damage = round(damage * (1 + bonus), 2)
                    entity["spec_arcane_stacks"] = 0
                    messages.append(
                        f"⚡ **{name}** unleashes an Overloaded Fireball — "
                        f"{stacks} charge{'s' if stacks != 1 else ''} detonate for "
                        f"+{int(bonus * 100)}%!"
                    )
            else:
                max_stacks = int(eff.get("max_stacks", 5))
                if stacks > 0:
                    damage = round(damage * (1 + eff["value"] * stacks / 100), 2)
                if stacks < max_stacks:
                    stacks += 1
                    entity["spec_arcane_stacks"] = stacks
                    if stacks == max_stacks:
                        messages.append(f"⚡ **{name}**'s Arcane Surge peaks — fully Overloaded!")

        eff = fx.get("doom_circle_pct")
        if eff:
            threshold = int(eff.get("threshold", 3) or 3)
            sigils = int(entity.get("spec_doom_circle_sigils", 0) or 0) + 1
            if sigils < threshold:
                entity["spec_doom_circle_sigils"] = sigils
                messages.append(f"🔮 Doom Sigils circle the dragon (**{sigils}/{threshold}**).")
            else:
                entity["spec_doom_circle_sigils"] = 0
                attacker_damage = float(entity.get("damage", 0) or 0)
                hp_pct = float(eff.get("hp_value", 0) or 0) / 100
                hp_damage = min(
                    float(dragon.get("max_hp", 0) or 0) * hp_pct,
                    attacker_damage * float(eff.get("hp_damage_cap", 0.75)),
                )
                bonus = max(10.0, attacker_damage * eff["value"] / 100 + hp_damage)
                damage = round(damage + bonus, 2)
                messages.append(f"🔮 **{name}**'s Doom Circle detonates for **{bonus:,.1f}HP**!")

        eff = fx.get("armor_ignore_chance_pct")
        if eff and random.random() < eff["value"] / 100:
            # Armor was already subtracted upstream; a Deadeye hit adds it back
            damage = round(damage + float(dragon.get("armor", 0)), 2)
            messages.append(f"🎯 **{name}**'s Deadeye finds a gap in the dragon's scales!")

        return damage, messages

    def apply_defensive_specs(self, target, damage, battle_participants, dragon=None):
        """Defender-side spec mitigation on dragon damage. Returns (damage, messages).

        Retaliation reflects onto the dragon only when the dragon dict is passed
        (basic attacks); special moves don't carry it.
        """
        messages = []
        damage = float(damage)
        fx = self.get_spec_fx(target)
        name = target["user"].display_name if not target.get("is_pet") else target.get("pet_name", "Pet")

        shroud_hits = int(target.get("reaper_death_shroud_hits", 0) or 0)
        if shroud_hits > 0:
            damage = round(damage * 0.5, 2)
            target["reaper_death_shroud_hits"] = shroud_hits - 1
            messages.append(f"☠️ **{name}**'s Death Shroud halves the blow!")

        eff = fx.get("dodge_pct")
        if eff and random.random() < eff["value"] / 100:
            messages.append(f"💨 **{name}** vanishes in a Smoke Step — dodged!")
            return 0.0, messages

        eff = fx.get("foresight_chance_pct")
        if eff and random.random() < eff["value"] / 100:
            damage = round(damage / 2, 2)
            messages.append(f"👁️ **{name}** foresaw the blow — damage halved!")

        eff = fx.get("damage_taken_reduction_pct")
        if eff:
            damage = round(damage * (1 - eff["value"] / 100), 2)

        brace_stacks = int(target.get("warrior_brace_stacks", 0) or 0)
        warrior_reduction = warrior_damage_reduction_pct(
            fx,
            target.get("warrior_momentum", 0),
            brace_stacks,
        )
        if warrior_reduction > 0:
            damage = round(
                float(Decimal(str(damage)) * (Decimal("1") - warrior_reduction / Decimal("100"))),
                2,
            )
            messages.append(
                f"🪖 **{name}**'s Combat Discipline reduces the blow by "
                f"**{warrior_reduction}%**!"
            )
        if brace_stacks > 0:
            target["warrior_brace_stacks"] = 0

        # Sanctuary: strongest living ally instance protects everyone else
        best = 0.0
        for ally in battle_participants:
            if ally is target or ally["hp"] <= 0:
                continue
            ally_eff = self.get_spec_fx(ally).get("party_damage_reduction_pct")
            if ally_eff:
                best = max(best, ally_eff["value"])
        if best > 0:
            damage = round(damage * (1 - best / 100), 2)

        for shield_key, shield_name in (("soul_ward", "Soul Ward"), ("gift_shield", "Starlight shield")):
            shield = float(target.get(shield_key, 0) or 0)
            if shield <= 0 or damage <= 0:
                continue
            absorbed = min(shield, damage)
            target[shield_key] = round(shield - absorbed, 2)
            damage = round(damage - absorbed, 2)
            messages.append(f"🛡️ **{name}**'s {shield_name} absorbs **{absorbed:,.1f}HP**!")

        eff = fx.get("unbroken_will_pct")
        if eff and not target.get("spec_unbroken_used") and float(target.get("max_hp", 0) or 0) > 0:
            projected_ratio = (float(target["hp"]) - damage) / float(target["max_hp"])
            if projected_ratio < eff.get("threshold", 0.40):
                target["spec_unbroken_used"] = True
                shield_pct = eff.get("shield_value", eff["value"] + eff.get("shield_bonus", 4))
                shield = float(target["max_hp"]) * shield_pct / 100
                prevented = min(damage, shield)
                damage = round(max(0.0, damage - prevented), 2)
                target["spec_unbroken_damage_hits"] = int(eff.get("duration", 3))
                messages.append(
                    f"🛡️ **{name}**'s Unbroken Will prevents **{prevented:,.1f}HP** damage!"
                )

        soul_owner = target
        soul_fx = fx.get("soulkeeper_store_pct")
        if target.get("is_pet"):
            owner_id = target.get("owner_id")
            for ally in battle_participants:
                if ally.get("is_pet"):
                    continue
                if getattr(ally.get("user"), "id", None) == owner_id:
                    owner_fx = self.get_spec_fx(ally).get("soulkeeper_store_pct")
                    if owner_fx:
                        soul_owner = ally
                        soul_fx = owner_fx
                    break
        if soul_fx and damage > 0 and not soul_owner.get("is_pet"):
            release_at = float(soul_owner["max_hp"]) * soul_fx.get("release_pct", 20) / 100
            stored = float(soul_owner.get("spec_soulkeeper_reservoir", 0.0))
            stored += damage * soul_fx["value"] / 100
            if stored < release_at:
                soul_owner["spec_soulkeeper_reservoir"] = stored
            else:
                soul_owner["spec_soulkeeper_reservoir"] = 0.0
                prevented = min(damage, release_at)
                damage = round(max(0.0, damage - prevented), 2)
                for ally in battle_participants:
                    if ally is soul_owner or (
                        ally.get("is_pet") and ally.get("owner_id") == getattr(soul_owner.get("user"), "id", None)
                    ):
                        heal = min(
                            float(ally["max_hp"]) - float(ally["hp"]),
                            release_at / 2,
                        )
                        if heal > 0:
                            ally["hp"] = round(float(ally["hp"]) + heal, 2)
                messages.append(
                    f"🕯️ **{soul_owner['user'].display_name}** releases Sacred Offering, "
                    f"preventing **{prevented:,.1f}HP** damage!"
                )

        # Retaliation: reflect part of the hit back at the dragon
        eff = fx.get("reflect_pct")
        if eff and dragon is not None and damage > 0:
            reflected = round(damage * eff["value"] / 100, 2)
            if reflected > 0:
                dragon["hp"] = round(max(0, float(dragon["hp"]) - reflected), 2)
                messages.append(
                    f"💢 **{name}**'s Retaliation reflects **{reflected:,.1f}HP** back at the dragon!"
                )

        # Bloodweaver (Blood Pact): bank a share of damage taken; a lethal blow
        # shatters the pact instead — survive at 1 HP and drain the reservoir.
        # Returning an "effective damage" here means all four dragon damage paths
        # (which do hp = max(0, hp - damage)) honor the save with no extra edits.
        bp = fx.get("bloodpact_reservoir_pct")
        if bp and not target.get("is_pet"):
            cur_hp = float(target["hp"])
            if damage < cur_hp:
                if not target.get("bloodpact_used"):
                    cap = float(target["max_hp"]) * bp["value"] / 100
                    reservoir = float(target.get("bloodpact_reservoir", 0.0))
                    if reservoir < cap:
                        target["bloodpact_reservoir"] = min(
                            cap, reservoir + damage * bp.get("bank_pct", 25) / 100
                        )
            elif not target.get("bloodpact_used"):
                target["bloodpact_used"] = True
                reservoir = float(target.get("bloodpact_reservoir", 0.0))
                target["bloodpact_reservoir"] = 0.0
                survive_hp = min(float(target["max_hp"]), 1.0 + reservoir)
                drain = f" and drains **{reservoir:,.0f}HP**" if reservoir > 0 else ""
                messages.append(f"🩸 **{name}**'s Blood Pact shatters — clinging to life{drain}!")
                return round(cur_hp - survive_hp, 2), messages

        cur_hp = float(target["hp"])
        if damage >= cur_hp and cur_hp > 0:
            reaper_level = int(target.get("reaper_evolution", 0) or 0)
            if reaper_level and not target.get("reaper_death_used"):
                avatar_hits = int(target.get("reaper_avatar_hits", 0) or 0)
                guaranteed = avatar_hits > 0
                chance = self.REAPER_DEATH_CHANCE[reaper_level]
                if guaranteed or random.randint(1, 100) <= chance:
                    target["reaper_death_used"] = True
                    target["reaper_avatar_hits"] = 0
                    target["reaper_souls"] = 0
                    target["reaper_death_shroud_hits"] = 1
                    survive_ratio = 0.12 + 0.025 * reaper_level
                    survive_hp = max(1.0, float(target["max_hp"]) * survive_ratio)
                    source = "Avatar of Death" if guaranteed else "Undying Loyalty"
                    messages.append(
                        f"☠️ **{name}** invokes {source}, returns with **{survive_hp:,.1f}HP**, "
                        "and enters Death Shroud!"
                    )
                    return round(cur_hp - survive_hp, 2), messages

            if not any(ally.get("winterlight_team_miracle_used") for ally in battle_participants):
                candidates = []
                for ally in battle_participants:
                    miracle = self.get_spec_fx(ally).get("christmas_miracle_pct")
                    if miracle and (float(ally.get("hp", 0)) > 0 or ally is target):
                        candidates.append((float(miracle["value"]), ally, miracle))
                if candidates:
                    _value, owner, miracle = max(candidates, key=lambda item: item[0])
                    for ally in battle_participants:
                        ally["winterlight_team_miracle_used"] = True
                    owner["winterlight_miracle_used"] = True
                    survive_hp = max(1.0, float(target["max_hp"]) * float(miracle["value"]) / 100)
                    shield = float(target["max_hp"]) * float(miracle.get("miracle_shield_value", 0)) / 100
                    target["gift_shield"] = float(target.get("gift_shield", 0) or 0) + shield
                    messages.append(
                        f"🕊️ **{self._ice_name(owner)}** invokes **Christmas Miracle**! "
                        f"**{name}** returns with **{survive_hp:,.1f}HP** and a **{shield:,.1f}HP** shield!"
                    )
                    return round(cur_hp - survive_hp, 2), messages

        return max(0.0, damage), messages

    def maybe_second_wind(self, entity):
        """Legacy low-HP heal fallback, checked at the start of their turn."""
        eff = self.get_spec_fx(entity).get("second_wind_heal_pct")
        if (
            eff
            and entity["hp"] > 0
            and not entity.get("spec_second_wind_used")
            and float(entity["hp"]) / float(entity["max_hp"]) < eff.get("threshold", 0.30)
        ):
            entity["spec_second_wind_used"] = True
            heal = round(float(entity["max_hp"]) * eff["value"] / 100, 2)
            entity["hp"] = min(float(entity["max_hp"]), round(float(entity["hp"]) + heal, 2))
            return [
                f"🌅 **{entity['user'].display_name}** finds a Second Wind and recovers **{heal:,.1f}HP**!"
            ]
        return []

    async def get_world_record(self, conn):
        """All-time highest dragon level, creating the records table if needed."""
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS dragon_records (
                id INT PRIMARY KEY,
                record_level INT NOT NULL DEFAULT 0,
                record_holder BIGINT,
                achieved_at TIMESTAMP
            )
        ''')
        return await conn.fetchrow(
            'SELECT record_level, record_holder, achieved_at FROM dragon_records WHERE id = 1'
        )

    async def check_world_record(self, ctx, party_members, new_level):
        """Announce a community world-first when the dragon hits a record level."""
        async with self.bot.pool.acquire() as conn:
            record = await self.get_world_record(conn)
            old_record = record["record_level"] if record else 0
            if new_level <= old_record:
                return
            await conn.execute('''
                INSERT INTO dragon_records (id, record_level, record_holder, achieved_at)
                VALUES (1, $1, $2, $3)
                ON CONFLICT (id) DO UPDATE
                SET record_level = EXCLUDED.record_level,
                    record_holder = EXCLUDED.record_holder,
                    achieved_at = EXCLUDED.achieved_at
            ''', new_level, ctx.author.id, datetime.utcnow())

        party_mentions = ", ".join(m.mention for m in party_members)
        announcement = (
            f"🌌 **WORLD FIRST!** The community has pushed the dragon to level **{new_level}** — "
            f"a new all-time record! The decisive blow was struck by {party_mentions}!"
        )
        await ctx.send(announcement)
        # Let other systems (feats, ...) react to the record
        self.bot.dispatch("dragon_world_record", ctx, party_members, new_level)
        if self.reset_channel_id:
            channel = self.bot.get_channel(self.reset_channel_id)
            if channel and channel.id != ctx.channel.id:
                try:
                    await channel.send(announcement)
                except Exception:
                    pass

    async def calculate_dragon_stats(self):
        """Calculate dragon stats based on current level and stage"""
        async with self.bot.pool.acquire() as conn:
            result = await conn.fetchrow(
                'SELECT current_level, weekly_defeats, last_reset FROM dragon_progress WHERE id = 1'
            )
            if not result:
                # Initialize if not exists
                now = datetime.utcnow()
                await conn.execute(
                    'INSERT INTO dragon_progress (id, current_level, weekly_defeats, last_reset) VALUES (1, 1, 0, $1)',
                    now
                )
                dragon_level = 1
                last_reset = now
            else:
                dragon_level = result['current_level']
                last_reset = result['last_reset']

        stage_name, stage_data = await self.get_current_stage(dragon_level)
        base_multiplier = stage_data["base_multiplier"]
        level_multiplier = 1 + (dragon_level * 0.15)  # 20% stronger each level

        # Add passive effects to dragon's stats
        passives = stage_data["passives"]
        passive_effects = {}
        if "Ice Armor" in passives:
            passive_effects["damage_reduction"] = 0.20
        if "Corruption" in passives:
            passive_effects["shield_reduction"] = 0.20
        if "Void Fear" in passives:
            passive_effects["attack_reduction"] = 0.20
        if "Aspect of death" in passives:
            passive_effects["attack_reduction"] = 0.30
            passive_effects["defense_reduction"] = 0.30
        if "Abyssal Presence" in passives:
            passive_effects["attack_reduction"] = 0.35
            passive_effects["defense_reduction"] = 0.35

        mutator_keys = self.get_weekly_mutators(last_reset)
        mutator_effects = self.compute_mutator_effects(mutator_keys)

        return {
            "name": f"Level {dragon_level} {stage_name}",
            "hp": 3500 * base_multiplier * level_multiplier * mutator_effects["dragon_hp_mult"],
            "damage": 290 * level_multiplier * mutator_effects["dragon_damage_mult"],
            "armor": 220 * level_multiplier,
            "moves": stage_data["moves"],
            "passives": stage_data["passives"],
            "passive_effects": passive_effects,
            "stage": stage_name,
            "mutators": mutator_keys,
            "mutator_effects": mutator_effects
        }

    async def check_weekly_reset(self):
        """Check and perform weekly reset if needed"""
        async with self.bot.pool.acquire() as conn:
            result = await conn.fetchrow(
                'SELECT last_reset FROM dragon_progress WHERE id = 1'
            )

            if not result:
                return False

            now = datetime.utcnow()
            last_reset = result['last_reset']

            if now - last_reset >= timedelta(days=7):
                # Perform reset
                await conn.execute('''
                    UPDATE dragon_progress 
                    SET current_level = 1, 
                        weekly_defeats = 0, 
                        last_reset = $1 
                    WHERE id = 1
                ''', now)

                # Reset all players' weekly contributions
                await conn.execute('''
                    UPDATE dragon_contributions 
                    SET weekly_defeats = 0
                ''')

                # Send reset message
                reset_channel = (
                    self.bot.get_channel(self.reset_channel_id)
                    if self.reset_channel_id
                    else None
                )
                if reset_channel:
                    await reset_channel.send("❄️ **Weekly reset!** The Ice Dragon has been reset to level 1.")
                return True
            return False

    @is_gm()
    @commands.command()
    @has_char()
    async def unlockidc(self, ctx):
        if self.unlocked == True:
            await ctx.send("locked")
            self.unlocked = False
        else:
            self.unlocked = True
            await ctx.send("Ice Dragon Challenged has been successfully unlocked")

    @commands.group(invoke_without_command=True)
    @has_char()
    async def dragon(self, ctx):
        """Display current Ice Dragon status"""

        if self.unlocked == False:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send("This command is not ready yet.")
        await self.check_weekly_reset()

        dragon_stats = await self.calculate_dragon_stats()
        stage_name = dragon_stats["stage"]

        # Get current stats from DB
        async with self.bot.pool.acquire() as conn:
            result = await conn.fetchrow(
                'SELECT current_level, weekly_defeats, last_reset FROM dragon_progress WHERE id = 1'
            )
            if not result:
                weekly_defeats = 0
                last_reset = datetime.utcnow()
            else:
                weekly_defeats = result['weekly_defeats']
                last_reset = result['last_reset']

        embed = discord.Embed(
            title=f"❄️ {dragon_stats['name']} ❄️",
            description=f"The **{stage_name}** awaits challengers...",
            color=0x87CEEB
        )

        # Add stats
        embed.add_field(
            name="**Dragon Stats**",
            value=f"**HP:** {dragon_stats['hp']:,.0f}\n"
                  f"**Damage:** {dragon_stats['damage']:,.0f}\n"
                  f"**Armor:** {dragon_stats['armor']:,.0f}"
        )

        # Add special moves
        moves_text = "\n".join([f"• {move}" for move in dragon_stats['moves'].keys()])
        embed.add_field(name="**Special Moves**", value=moves_text, inline=False)

        # Add this week's mutators
        mutator_lines = self.describe_mutators(dragon_stats.get("mutators", []))
        if mutator_lines:
            embed.add_field(
                name="**This Week's Mutators**",
                value="\n".join(mutator_lines),
                inline=False
            )

        # Endless stage banner + all-time community record
        if stage_name == "The Abyssal Maw":
            embed.add_field(
                name="🌌 ENDLESS STAGE",
                value="The Abyssal Maw scales forever. Every level from here is a community record attempt.",
                inline=False
            )
        try:
            async with self.bot.pool.acquire() as conn:
                record = await self.get_world_record(conn)
            if record and record["record_level"] > 24:
                embed.add_field(
                    name="🏆 All-Time Record",
                    value=(
                        f"Level **{record['record_level']}** — decisive blow by "
                        f"<@{record['record_holder']}>"
                    ),
                    inline=False
                )
        except Exception:
            pass

        # Add progress
        next_level = 40 - (weekly_defeats % 40)
        embed.add_field(
            name="**Weekly Progress**",
            value=f"**Defeats:** {weekly_defeats}\n"
                  f"**Next Level:** {next_level} defeats\n"
                  f"**Weekly Reset:** {(last_reset + timedelta(days=7)).strftime('%Y-%m-%d')}",
            inline=False
        )

        await ctx.send(embed=embed)

    import asyncio
    import discord
    from discord.ext import commands

    @user_on_cooldown(7200)
    @is_patreon(min_tier=1)
    @dragon.command()
    async def channel(self, ctx, *members: discord.Member):
        """Creates a private channel for the specified members (1-3) and self-destructs after 20 minutes."""
        # Check guild ID
        if not self.allowed_guild_id or ctx.guild.id != self.allowed_guild_id:
            await ctx.send("This command can only be used in the specified guild.")
            self.bot.reset_cooldown(ctx)
            return


        # Define category and channel details
        category_id = self.party_category_id
        deny_role_id = self.party_deny_role_id

        # Fetch category
        category = discord.utils.get(ctx.guild.categories, id=category_id)
        if not category:
            await ctx.send("Category not found.")
            self.bot.reset_cooldown(ctx)
            return

        # Filter out the author and the bot if included
        valid_members = []
        for member in members:
            if member == ctx.author or member == ctx.guild.me:
                await ctx.send(f"You cannot add {member.mention} to the channel.")
                self.bot.reset_cooldown(ctx)
            else:
                valid_members.append(member)
        members = valid_members

        # Ensure at least one member and no more than 3 are specified
        if len(members) < 1:
            await ctx.send("You must specify at least one other user.")
            self.bot.reset_cooldown(ctx)
            return
        if len(members) > 6:
            await ctx.send("You can only specify up to 3 members.")
            self.bot.reset_cooldown(ctx)
            return

        # Create channel overwrites
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            ctx.author: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }

        # Ensure the bot can manage the channel
        overwrites[ctx.guild.me] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            manage_channels=True,
            manage_messages=True
        )

        # Add specified members to overwrites
        for member in members:
            overwrites[member] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        # Deny view permissions for specific role
        deny_role = ctx.guild.get_role(deny_role_id)
        if deny_role:
            overwrites[deny_role] = discord.PermissionOverwrite(view_channel=False)

        # Create channel
        channel_name = ctx.author.name.lower()
        channel = await category.create_text_channel(name=channel_name, overwrites=overwrites)

        # Send message in the newly created channel, mentioning the invited members
        member_mentions = ', '.join([m.mention for m in members])
        await channel.send(
            f"Private channel {channel.mention} created for {ctx.author.mention} "
            f"and {member_mentions}. It will self-destruct in 20 minutes."
        )

        # Wait 20 minutes and delete the channel
        await asyncio.sleep(20 * 60)

        for member in members:
            try:
                del self.current_parties[member.id]
            except KeyError:
                pass

            # If you also store the command author under self.current_parties,
            # delete them as well:
        try:
            del self.current_parties[ctx.author.id]
        except KeyError:
            pass

        await channel.delete(reason="Self-destruct timer expired")

    @is_patreon(min_tier=1)
    @user_on_cooldown(7200)
    @has_char()
    @dragon.command(name="party")
    async def create_party(self, ctx):
        """Create a dragon hunting party"""

        if not self.unlocked:
            await self.bot.reset_cooldown(ctx)
            return await ctx.send("This command is not ready yet.")

        try:
            if isinstance(ctx.channel, discord.DMChannel) or ctx.guild.id != self.allowed_guild_id:
                #await self.bot.reset_cooldown(ctx)
                return await ctx.send("Dragon battles can only be started in the Fable server!")

            if ctx.author.id in self.current_parties:
                await self.bot.reset_cooldown(ctx)
                return await ctx.send("You're already in a dragon hunting party!")

            party_members = [ctx.author]
            self.current_parties[ctx.author.id] = party_members
            embed = discord.Embed(title="🐉 Dragon Hunting Party", color=0x87CEEB)
            embed.description = f"Click ✅ to join the hunt! ({len(party_members)}/4 members)\n**Party Members:**"
            embed.add_field(name="1.", value=ctx.author.display_name, inline=False)

            # Define a custom View that accepts the cog instance
            class PartyView(discord.ui.View):
                def __init__(self, ctx, embed, party_members, cog):
                    super().__init__(timeout=60.0)
                    self.ctx = ctx
                    self.embed = embed
                    self.party_members = party_members
                    self.leader = ctx.author
                    self.msg = None
                    self.cog = cog  # store reference to the cog
                    self.battle_started = False  # new flag

                async def update_embed(self):
                    member_count = len(self.party_members)
                    self.embed.description = f"Click ✅ to join the hunt! ({member_count}/4 members)\n**Party Members:**"
                    self.embed.clear_fields()
                    for idx, member in enumerate(self.party_members, start=1):
                        self.embed.add_field(name=f"{idx}.", value=member.display_name, inline=False)
                    await self.msg.edit(embed=self.embed, view=self)

                @discord.ui.button(emoji="✅", style=discord.ButtonStyle.success, label="Join")
                async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
                    if interaction.user in self.party_members:
                        await interaction.response.send_message("You are already in the party!", ephemeral=True)
                        return
                    if len(self.party_members) >= 4:
                        await interaction.response.send_message("The party is already full!", ephemeral=True)
                        return
                    self.party_members.append(interaction.user)
                    await self.update_embed()
                    await interaction.response.send_message(f"{interaction.user.mention} joined the party!",
                                                            ephemeral=True)

                @discord.ui.button(emoji="❌", style=discord.ButtonStyle.danger, label="Leave")
                async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
                    if interaction.user == self.leader:
                        await interaction.response.send_message("You cannot leave your own party!", ephemeral=True)
                        return
                    if interaction.user not in self.party_members:
                        await interaction.response.send_message("You're not in the party!", ephemeral=True)
                        return
                    self.party_members.remove(interaction.user)
                    await self.update_embed()
                    await interaction.response.send_message(f"{interaction.user.mention} left the party.",
                                                            ephemeral=True)

                @discord.ui.button(emoji="⚔️", style=discord.ButtonStyle.primary, label="Start Battle")
                async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
                    if interaction.user != self.leader:
                        await interaction.response.send_message("Only the party leader can start the battle!",
                                                                ephemeral=True)
                        return

                    # Set flag and immediately stop the view so that its timeout is cancelled
                    self.battle_started = True
                    self.stop()

                    for child in self.children:
                        child.disabled = True
                    await interaction.response.edit_message(view=self)
                    await self.ctx.send("The battle is starting!")
                    try:
                        await self.cog.start_dragon_fight(self.ctx, self.party_members)
                    except Exception as e:
                        import traceback
                        error_message = f"Error while starting the battle: {e}\n" + traceback.format_exc()
                        await self.ctx.send(error_message)
                    finally:
                        try:
                            del self.cog.current_parties[self.leader.id]
                        except Exception:
                            pass

                async def on_timeout(self):
                    # Only run timeout code if the battle was never started
                    if self.battle_started:
                        return
                    try:
                        await self.ctx.send(f"{self.leader.mention}, party formation timed out!")
                        del self.cog.current_parties[self.leader.id]
                        await self.cog.bot.reset_cooldown(self.ctx)
                    except Exception:
                        pass


            # Instantiate view with the cog instance (self)
            view = PartyView(ctx, embed, party_members, cog=self)
            msg = await ctx.send(embed=embed, view=view)
            view.msg = msg

        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n" + traceback.format_exc()
            await ctx.send(error_message)

    async def apply_effect(self, target, effect, damage, action_log, mutator_effects=None):
        """Apply special effects from dragon moves"""
        effect_duration = 2  # rounds
        if mutator_effects and effect in ("freeze", "stun"):
            # Enduring Frost mutator: crowd control lasts longer
            effect_duration += mutator_effects.get("status_duration_bonus", 0)

        if effect == "freeze":
            target["frozen"] = effect_duration
            action_log.append(
                f"{target['user'].display_name if not target.get('is_pet') else target['pet_name']} is frozen solid! ❄️"
            )
        elif effect == "dot":
            dot_damage = round(float(damage) * 0.2, 2)
            target["dot"] = {"damage": dot_damage, "duration": effect_duration}
            action_log.append(
                f"{target['user'].display_name if not target.get('is_pet') else target['pet_name']} is taking frost damage over time! ☠️"
            )
        elif effect == "random_debuff":
            debuffs = ["damage_down", "armor_down"]
            debuff = random.choice(debuffs)

            # Store original stats before debuff
            if debuff == "damage_down":
                target["original_damage"] = target["damage"]  # Store original damage
                target["damage"] = round(float(target["damage"]) * 0.7, 2)  # Reduce damage by 30%
                debuff_text = "Damage heavily reduced%"
            elif debuff == "armor_down":
                target["original_armor"] = target["armor"]  # Store original armor
                target["armor"] = round(float(target["armor"]) * 0.7, 2)  # Reduce armor by 30%
                debuff_text = "Armor heavily reduced"

            # Store debuff info with duration
            target[debuff] = {
                "duration": effect_duration,
                "type": debuff
            }

            action_log.append(
                f"{target['user'].display_name if not target.get('is_pet') else target['pet_name']} is debuffed: {debuff_text}! ⚡"
            )
        elif effect == "summon_adds":
            num_soldiers = random.randint(1, 3)
            soldier_damage = round(float(damage) * 0.7 + 150, 2)  # Each soldier deals 70% of original damage
            total_soldier_damage = round(float(soldier_damage * num_soldiers), 2)
            target["hp"] = round(max(0, float(target["hp"]) - total_soldier_damage), 2)
            action_log.append(
                f"{num_soldiers} Minions appear and attack {target['user'].display_name if not target.get('is_pet') else target['pet_name']} for **{total_soldier_damage:,.2f}HP**!"
            )
        elif effect == "stun":
            target["stunned"] = effect_duration
            action_log.append(
                f"{target['user'].display_name if not target.get('is_pet') else target['pet_name']} is stunned! ⚡"
            )
        elif effect == "curse":
            target["cursed"] = effect_duration
            action_log.append(
                f"{target['user'].display_name if not target.get('is_pet') else target['pet_name']} is cursed! Defense is slightly reduced! 👻"
            )
        elif effect == "aoe_dot":
            dot_damage = round(float(damage) * 0.15, 2)  # 15% damage per turn
            target["dot"] = {"damage": dot_damage, "duration": effect_duration}
            action_log.append(
                f"🌀 Dark energy swirls around {target['user'].display_name if not target.get('is_pet') else target['pet_name']}, dealing damage over time!"
            )
        elif effect == "steal_buffs":
            target["buffs_stolen"] = effect_duration
            action_log.append(
                f"{target['user'].display_name if not target.get('is_pet') else target['pet_name']} had their buffs stolen! 💫"
            )
        elif effect == "aoe":
            # Don't log AOE message, it's handled in execute_dragon_move
            pass
        elif effect == "execute":
            if target["hp"] / target["max_hp"] <= 1.0:  # If target is below 20% HP
                damage = round(float(target["hp"]), 2)  # Instant kill
                target["hp"] = 0
                action_log.append(
                    f"{target['user'].display_name if not target.get('is_pet') else target['pet_name']} is executed! ⚰️"
                )
        elif effect == "arena_hazard":
            hazard_damage = round(float(damage) * 0.1, 2)
            target["arena_hazard"] = {"damage": hazard_damage, "duration": effect_duration}
            action_log.append(
                f"The arena is filled with deadly ice shards! ❄️"
            )

    async def execute_dragon_move(self, dragon_stats, targets, action_log):
        """Execute a special dragon move with clear damage messages"""
        stage_name, stage_data = await self.get_current_stage()
        moves = stage_data["moves"]

        # Weekly mutator effects (special move damage isn't pre-multiplied like
        # the dragon's basic damage stat, so apply the multipliers here)
        mut_fx = dragon_stats.get("mutator_effects", {})
        dmg_mult = mut_fx.get("dragon_damage_mult", 1.0) * mut_fx.get("mutual_damage_mult", 1.0)
        dmg_mult *= 1 - float(dragon_stats.get("krampus_weakness_pct", 0) or 0)
        armor_pierce = mut_fx.get("armor_pierce", 0.0)

        selected_move = random.choices(
            list(moves.keys()),
            weights=[move["chance"] for move in moves.values()]
        )[0]
        move_data = moves[selected_move]

        if move_data["effect"] == "aoe":
            total_damage = []
            spec_msgs = []
            for target in targets:
                if target["hp"] <= 0:
                    continue
                bonus = Decimal(random.randint(0, 100))
                effective_armor = float(target["armor"]) * (1 - armor_pierce)
                # Calculate damage and round to two decimal places
                damage = max(1, round(float(move_data["dmg"]) * dmg_mult - effective_armor + float(bonus), 2))
                if target.get("damage_reduction"):
                    damage *= (1 - target["damage_reduction"])
                    damage = round(damage, 2)  # Round again after applying damage reduction
                damage, target_spec_msgs = self.apply_defensive_specs(target, damage, targets, dragon_stats)
                spec_msgs.extend(target_spec_msgs)
                target["hp"] = max(0, round(float(target["hp"]) - damage, 2))
                name = target['user'].display_name if not target.get('is_pet') else target['pet_name']
                total_damage.append(f"**{name}** ({damage:,.2f}HP)")
                # Apply effect without adding to action log
                await self.apply_effect(target, move_data["effect"], damage, [], mutator_effects=mut_fx)

            action_log.append(f"Dragon unleashes **{selected_move}**!\nDamage dealt to: {' | '.join(total_damage)}")
            action_log.extend(spec_msgs)


        elif move_data["effect"] == "multihit":

            valid_targets = [t for t in targets if t["hp"] > 0]

            if valid_targets:

                target = random.choice(valid_targets)

                name = target['user'].display_name if not target.get('is_pet') else target['pet_name']

                hits = random.randint(2, 4)

                total_damage = 0

                for _ in range(hits):

                    base_damage = round(move_data["dmg"] * dmg_mult / hits, 2)  # Ensure base damage is rounded

                    damage = max(1, round(base_damage - float(target["armor"]) * (1 - armor_pierce), 2))

                    if target.get("damage_reduction"):
                        damage *= (1 - target["damage_reduction"])

                        damage = round(damage, 2)  # Round after applying damage reduction

                    total_damage += damage

                # Class specialization defenses apply once to the whole flurry
                total_damage, spec_msgs = self.apply_defensive_specs(target, total_damage, targets, dragon_stats)
                target["hp"] = max(0, round(float(target["hp"]) - total_damage, 2))

                action_log.append(f"Dragon unleashes **{selected_move}** on **{name}**!\n"

                                  f"Strikes {hits} times for **{total_damage:,.2f}HP** total damage!")
                action_log.extend(spec_msgs)

                # Apply effect after damage

                effect_log = []

                await self.apply_effect(target, move_data["effect"], total_damage, effect_log, mutator_effects=mut_fx)

                # Add any effect messages to the action log

                action_log.extend(effect_log)



        else:  # Single target attacks

            valid_targets = [t for t in targets if t["hp"] > 0]

            if valid_targets:

                target = random.choice(valid_targets)

                name = target['user'].display_name if not target.get('is_pet') else target['pet_name']

                damage = max(1, round(float(move_data["dmg"]) * dmg_mult - float(target["armor"]) * (1 - armor_pierce), 2))

                if target.get("damage_reduction"):
                    damage *= (1 - target["damage_reduction"])

                    damage = round(damage, 2)  # Round after applying damage reduction

                # Class specialization defenses
                damage, spec_msgs = self.apply_defensive_specs(target, damage, targets, dragon_stats)

                target["hp"] = max(0, round(float(target["hp"]) - damage, 2))

                action_log.append(f"Dragon unleashes **{selected_move}** on **{name}**!\n"

                                  f"Deals **{damage:,.2f}HP** damage!")
                action_log.extend(spec_msgs)

                # Apply effect and collect any effect messages

                effect_log = []

                await self.apply_effect(target, move_data["effect"], damage, effect_log, mutator_effects=mut_fx)

                # Add any effect messages to the action log

                action_log.extend(effect_log)

        self._tick_ice_krampus_weakness(dragon_stats, action_log)

    def get_effect_text(self, effect):
        """Get descriptive text for effects"""
        effect_descriptions = {
            "freeze": " and is frozen",
            "dot": " and is bleeding",
            "random_debuff": " and is debuffed",
            "stun": " and is stunned",
            "curse": " and is cursed",
            "steal_buffs": " and loses buffs",
            "bleed": " and is bleeding",
            "arena_hazard": " from ice shards"
        }
        return effect_descriptions.get(effect, "")

    async def get_party_stats(self, ctx, party_members, conn):
        """Get raid stats for all party members"""
        party_combatants = []
        strongest_bard = 0
        for member in party_members:
            row = await conn.fetchrow('SELECT class FROM profile WHERE "user" = $1;', member.id)
            if row and row["class"]:
                classes = row["class"] if isinstance(row["class"], list) else [row["class"]]
                strongest_bard = max(strongest_bard, self._bard_grade(classes))
        bard_damage_mult = 1 + 0.015 * strongest_bard if strongest_bard else 1.0

        for member in party_members:
            try:
                # Get element first
                highest_element = await self.fetch_highest_element(member.id)

                # Get player's base stats and level
                query = 'SELECT class, xp, luck, health, stathp FROM profile WHERE "user" = $1;'
                result = await conn.fetchrow(query, member.id)

                if result:
                    # Get level from XP
                    xp = result["xp"]
                    level = rpgtools.xptolevel(xp)

                    # Get classes for special bonuses
                    classes = result["class"] if result["class"] else []

                    # Get luck
                    luck_value = float(result['luck'])
                    if luck_value <= 0.3:
                        Luck = 20.0
                    else:
                        Luck = ((luck_value - 0.3) / (1.5 - 0.3)) * 80 + 20
                    Luck = round(Luck, 2)

                    # Add luck booster if any
                    luck_booster = await self.bot.get_booster(member, "luck")
                    if luck_booster:
                        Luck += Luck * 0.25
                        Luck = min(Luck, 100.0)

                    # Get base health and stat HP
                    base_health = 200.0
                    health = float(result['health']) + base_health
                    stathp = float(result['stathp']) * 50.0

                    amulet_query = '''
                                        SELECT * 
                                        FROM amulets 
                                        WHERE user_id = $1 
                                        AND equipped = true 
                                        AND type = 'hp'
                                    '''
                    amulet_result = await conn.fetchrow(amulet_query, member.id)

                    # Add amulet HP bonus if equipped (implement your specific HP bonus logic here)
                    amulet_bonus = amulet_result["hp"] if amulet_result else 0  # bonus for HP amulet

                    # Get raid stats
                    dmg, deff = await self.bot.get_raidstats(member, conn=conn)

                    total_health = health + level * 15.0 + stathp + float(amulet_bonus)



                    # Calculate total health


                    # Create combatant
                    combatant = {
                        "user": member,
                        "hp": total_health,
                        "max_hp": total_health,
                        "armor": float(deff),
                        "damage": float(dmg) * bard_damage_mult,
                        "luck": Luck,
                        "level": level,
                        "element": highest_element,
                        "classes": classes,
                        "is_pet": False
                    }

                    # Get equipped pet if any
                    pet = await conn.fetchrow(
                        "SELECT * FROM monster_pets WHERE user_id = $1 AND equipped = TRUE;",
                        member.id
                    )

                    if pet:
                        pet_element = pet["element"].capitalize() if pet["element"] else "Unknown"
                        pet_combatant = {
                            "user": member,
                            "owner_id": member.id,
                            "pet_name": pet["name"],
                            "hp": float(pet["hp"]),
                            "max_hp": float(pet["hp"]),
                            "armor": float(pet["defense"]),
                            "damage": float(pet["attack"]),
                            "luck": 50.0,
                            "element": pet_element,
                            "is_pet": True
                        }
                        party_combatants.append((combatant, pet_combatant))
                    else:
                        party_combatants.append((combatant, None))

                else:
                    # Add default stats if no profile found
                    combatant = {
                        "user": member,
                        "hp": 500.0,
                        "max_hp": 500.0,
                        "armor": 50.0,
                        "damage": 50.0,
                        "luck": 50.0,
                        "level": 1,
                        "element": "Unknown",
                        "classes": [],
                        "is_pet": False
                    }
                    party_combatants.append((combatant, None))

            except Exception as e:
                await ctx.send(f"Error getting stats for {member.display_name}: {e}")
                # Add default stats in case of error
                combatant = {
                    "user": member,
                    "hp": 500.0,
                    "max_hp": 500.0,
                    "armor": 50.0,
                    "damage": 50.0,
                    "luck": 50.0,
                    "level": 1,
                    "element": "Unknown",
                    "classes": [],
                    "is_pet": False
                }
                party_combatants.append((combatant, None))

        return party_combatants

    async def update_battle_embed(self, battle_msg, dragon, battle_participants, battle_log):
        """Update the battle embed with the latest stats and battle log"""
        embed = discord.Embed(
            title=f"🐉 {dragon['name']} Battle",
            color=0x87CEEB
        )

        # Dragon HP
        hp_bar = self.create_hp_bar(dragon["hp"], dragon["max_hp"])
        embed.add_field(
            name=f"**[BOSS] {dragon['name']}**",
            value=f"**HP:** {dragon['hp']:,.1f}/{dragon['max_hp']:,.1f}\n{hp_bar}",
            inline=False
        )

        # Track which player each pet belongs to
        player_pets = {}
        for combatant in battle_participants:
            if combatant.get("is_pet"):
                player_pets[combatant["owner_id"]] = combatant

        # Track players in order of appearance to assign teams
        player_teams = {}  # Map player IDs to team letters
        team_letters = ['A', 'B', 'C', 'D']
        current_team = 0

        # First pass to assign teams to players
        for combatant in battle_participants:
            if not combatant.get("is_pet"):
                if combatant["user"].id not in player_teams and current_team < 4:
                    player_teams[combatant["user"].id] = team_letters[current_team]
                    current_team += 1

        # Display participants with proper team labels
        for combatant in battle_participants:
            current_hp = max(0, round(combatant["hp"], 1))
            max_hp = round(combatant["max_hp"], 1)
            hp_bar = self.create_hp_bar(current_hp, max_hp)

            # Gather status effects
            status_effects = []
            if combatant.get("frozen"): status_effects.append("❄️")
            if combatant.get("stunned"): status_effects.append("⚡")
            if combatant.get("dot"): status_effects.append("☠️")
            if combatant.get("cursed"): status_effects.append("👻")
            if combatant.get("damage_down"): status_effects.append("⬇️")
            if combatant.get("armor_down"): status_effects.append("🛡️")
            if combatant.get("buffs_stolen"): status_effects.append("💫")
            if combatant.get("healing_corrupted"): status_effects.append("🔻")
            if combatant.get("damage_reduction"): status_effects.append("🛡️")

            status = " ".join(status_effects)

            if not combatant.get("is_pet"):
                # For players, get their assigned team
                team = player_teams.get(combatant["user"].id, "?")
                name = f"**[TEAM {team}] {combatant['user'].display_name}** {status}"
            else:
                # For pets, use same team as their owner
                owner_id = combatant["owner_id"]
                team = player_teams.get(owner_id, "?")
                name = f"**[TEAM {team}] {combatant['pet_name']}** {status}"

            embed.add_field(
                name=name,
                value=(
                    f"**HP:** {current_hp:.1f}/{max_hp:.1f}\n{hp_bar}"
                    + (f"\n{self._ice_class_status(combatant)}" if self._ice_class_status(combatant) else "")
                ),
                inline=False
            )

        # Add last 6 battle log entries
        last_logs = list(battle_log)[-6:]
        log_text = "\n\n".join(last_logs)
        embed.add_field(name="**Battle Log**", value=log_text, inline=False)

        await battle_msg.edit(embed=embed)


    async def fetch_highest_element(self, user_id):
        """Fetch highest element for a user"""
        try:
            highest_items = await self.bot.pool.fetch(
                "SELECT ai.element FROM profile p JOIN allitems ai ON (p.user=ai.owner) JOIN "
                "inventory i ON (ai.id=i.item) WHERE i.equipped IS TRUE AND p.user=$1 "
                "ORDER BY GREATEST(ai.damage, ai.armor) DESC;",
                user_id,
            )
            highest_element = highest_items[0]["element"].capitalize() if highest_items and highest_items[0][
                "element"] else "Unknown"
            return highest_element
        except Exception as e:
            return "Unknown"

    async def create_battle_embed(self, dragon, battle_participants, battle_log):
        """Create the initial battle embed with stats and log"""
        embed = discord.Embed(
            title=f"🐉 {dragon['name']} Battle",
            color=0x87CEEB
        )

        # Dragon HP
        hp_bar = self.create_hp_bar(dragon["hp"], dragon["max_hp"])
        embed.add_field(
            name=f"**[BOSS] {dragon['name']}**",
            value=f"**HP:** {dragon['hp']:,.1f}/{dragon['max_hp']:,.1f}\n{hp_bar}",
            inline=False
        )

        # Track which player each pet belongs to
        player_pets = {}
        for combatant in battle_participants:
            if combatant.get("is_pet"):
                player_pets[combatant["owner_id"]] = combatant

        # Track players in order of appearance to assign teams
        player_teams = {}  # Map player IDs to team letters
        team_letters = ['A', 'B', 'C', 'D']
        current_team = 0

        # First pass to assign teams to players
        for combatant in battle_participants:
            if not combatant.get("is_pet"):
                if combatant["user"].id not in player_teams and current_team < 4:
                    player_teams[combatant["user"].id] = team_letters[current_team]
                    current_team += 1

        # Participants
        for combatant in battle_participants:
            current_hp = max(0, round(combatant["hp"], 1))
            max_hp = round(combatant["max_hp"], 1)
            hp_bar = self.create_hp_bar(current_hp, max_hp)

            # Gather all status effects
            status_effects = []
            if combatant.get("frozen"): status_effects.append("❄️")
            if combatant.get("stunned"): status_effects.append("⚡")
            if combatant.get("dot"): status_effects.append("☠️")
            if combatant.get("cursed"): status_effects.append("👻")
            if combatant.get("damage_down"): status_effects.append("⬇️")
            if combatant.get("armor_down"): status_effects.append("🛡️")
            if combatant.get("buffs_stolen"): status_effects.append("💫")
            if combatant.get("healing_corrupted"): status_effects.append("🔻")
            if combatant.get("damage_reduction"): status_effects.append("🛡️")

            status = " ".join(status_effects)

            if not combatant.get("is_pet"):
                # For players, get their assigned team
                team = player_teams.get(combatant["user"].id, "?")
                name = f"**[TEAM {team}] {combatant['user'].display_name}** {status}"
            else:
                # For pets, use same team as their owner
                owner_id = combatant["owner_id"]
                team = player_teams.get(owner_id, "?")
                name = f"**[TEAM {team}] {combatant['pet_name']}** {status}"

            embed.add_field(
                name=name,
                value=(
                    f"**HP:** {current_hp:.1f}/{max_hp:.1f}\n{hp_bar}"
                    + (f"\n{self._ice_class_status(combatant)}" if self._ice_class_status(combatant) else "")
                ),
                inline=False
            )

        # Add battle log (initial log will only have the start message)
        embed.add_field(name="**Battle Log**", value="\n".join(list(battle_log)[-6:]), inline=False)

        return embed

    async def get_player_stats(self, playername, player_id):
        """Fetch player stats from the database."""

        async with self.bot.pool.acquire() as conn:


            query = 'SELECT "luck", "xp", "health", "stathp" FROM profile WHERE "user" = $1;'
            result = await conn.fetchrow(query, player_id)
            xp = result["xp"]
            base_health = 250
            health = result['health'] + base_health
            stathp = result['stathp'] * 50
            dmg, deff = await self.bot.get_raidstats(playername, conn=conn)
            player_level = rpgtools.xptolevel(xp)
            total_health = health + (player_level * 5)
            total_health += stathp

            amulet_query = '''
                                SELECT * 
                                FROM amulets 
                                WHERE user_id = $1 
                                AND equipped = true 
                                AND type = 'hp'
                            '''
            amulet_result = await conn.fetchrow(amulet_query, player_id)

            # Add amulet HP bonus if equipped
            amulet_bonus = amulet_result["hp"] if amulet_result else 0  # bonus for HP amulet

            total_health = amulet_bonus + total_health

            if query:
                return {
                    "hp": total_health,
                    "max_hp": total_health,
                    "damage": dmg,
                    "armor": deff
                }
            else:
                # Return default stats or handle as needed
                return {
                    "hp": 100,
                    "max_hp": 100,
                    "damage": 10,
                    "armor": 5
                }

    async def get_pet_stats(self, pet_id):
        """Fetch pet stats from the database."""
        async with self.bot.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT hp, attack, defense FROM monster_pets WHERE user_id = $1 AND equipped = true", pet_id)
            if row:
                return {
                    "hp": row["hp"],
                    "max_hp": row["hp"],
                    "damage": row["attack"],
                    "armor": row["defense"]
                }
            else:
                # Return default stats or handle as needed
                return {
                    "hp": 50,
                    "max_hp": 50,
                    "damage": 5,
                    "armor": 2
                }


    async def start_dragon_fight(self, ctx, party_members):
        """Start a fight with the Ice Dragon"""
        await self.check_weekly_reset()

        # Initialize dragon
        dragon_stats = await self.calculate_dragon_stats()
        dragon = {
            "name": dragon_stats["name"],
            "hp": dragon_stats["hp"],
            "max_hp": dragon_stats["hp"],
            "damage": dragon_stats["damage"],
            "armor": dragon_stats["armor"],
            "stage": dragon_stats["stage"],
            "passive_effects": dragon_stats["passive_effects"],
            "mutator_effects": dragon_stats.get("mutator_effects", {}),
            "is_dragon": True
        }

        async with self.bot.pool.acquire() as conn:
            result = await conn.fetchrow(
                'SELECT current_level, weekly_defeats, last_reset FROM dragon_progress WHERE id = 1'
            )
            if not result:
                weekly_defeats = 0
                current_level = 0
            else:
                current_level = result['current_level']
                weekly_defeats = result['weekly_defeats']
                last_reset = result['last_reset']
        #await ctx.send(f"Dragon initialized: {dragon['name']} with HP: {dragon['hp']}")

        # Get party stats
        async with self.bot.pool.acquire() as conn:
            party_stats = await self.get_party_stats(ctx, party_members, conn)

        # Debug: await ctx.send party_stats
        await ctx.send("Party Stats:")
        for idx, (player, pet) in enumerate(party_stats, start=1):
            player_name = player["user"].display_name if not player.get("is_pet", False) else player.get("pet_name",
                                                                                                         "Unknown Pet")
            pet_name = pet["pet_name"] if pet else "No Pet"
            #await ctx.send(f"  Member {idx}: Player: {player_name}, Pet: {pet_name}")




        # Ensure uniqueness in party members by converting to dictionaries
        strongest_bard_grade = max(
            (
                self._bard_grade(player.get("classes", []))
                for player, _pet in party_stats
                if not player.get("is_pet", False)
            ),
            default=0,
        )
        bard_damage_mult = 1 + 0.015 * strongest_bard_grade if strongest_bard_grade else 1.0
        unique_participants = {}
        battle_participants = []
        for player, pet in party_stats:
            # Handle player
            if not player.get("is_pet", False):
                player_id = player["user"].id
                playername = player["user"]
                if player_id not in unique_participants:
                    player_stats = await self.get_player_stats(playername, player_id)
                    # Get tank evolution level if any
                    tank_evolution = None
                    beastmaster_evolution = None
                    mage_evolution = None
                    reaper_evolution = None
                    santa_evolution = None
                    warrior_evolution = None
                    async with self.bot.pool.acquire() as conn:
                        result = await conn.fetchrow('SELECT class FROM profile WHERE "user" = $1', player_id)
                        if result and result['class']:
                            classes = result['class'] if isinstance(result['class'], list) else [result['class']]

                            # Check for tank class
                            tank_evolution_levels = {
                                "Protector": 1,
                                "Guardian": 2,
                                "Bulwark": 3,
                                "Defender": 4,
                                "Vanguard": 5,
                                "Fortress": 6,
                                "Titan": 7,
                            }

                            for class_name in classes:
                                if class_name in tank_evolution_levels:
                                    level = tank_evolution_levels[class_name]
                                    if tank_evolution is None or level > tank_evolution:
                                        tank_evolution = level
                                if class_name in self.BEASTMASTER_EVOLUTION_LEVELS:
                                    level = self.BEASTMASTER_EVOLUTION_LEVELS[class_name]
                                    if beastmaster_evolution is None or level > beastmaster_evolution:
                                        beastmaster_evolution = level
                                if class_name in self.MAGE_EVOLUTION_LEVELS:
                                    level = self.MAGE_EVOLUTION_LEVELS[class_name]
                                    if mage_evolution is None or level > mage_evolution:
                                        mage_evolution = level
                                if class_name in self.REAPER_EVOLUTION_LEVELS:
                                    level = self.REAPER_EVOLUTION_LEVELS[class_name]
                                    if reaper_evolution is None or level > reaper_evolution:
                                        reaper_evolution = level
                                if class_name in self.SANTA_EVOLUTION_LEVELS:
                                    level = self.SANTA_EVOLUTION_LEVELS[class_name]
                                    if santa_evolution is None or level > santa_evolution:
                                        santa_evolution = level
                                if class_name in WARRIOR_EVOLUTION_LEVELS:
                                    level = WARRIOR_EVOLUTION_LEVELS[class_name]
                                    if warrior_evolution is None or level > warrior_evolution:
                                        warrior_evolution = level

                            # Apply tank HP bonus if tank class found
                            if tank_evolution:
                                health_multiplier = 1 + (0.04 * tank_evolution)  # 5% per level
                                player_stats["hp"] *= health_multiplier
                                player_stats["max_hp"] *= health_multiplier

                    # Class specialization effects that apply at stat build.
                    spec_effects = {}
                    spec_cog = self.bot.get_cog("Specializations")
                    if spec_cog:
                        try:
                            spec_effects = await spec_cog.get_user_spec_effects(player_id)
                        except Exception:
                            spec_effects = {}
                    if "dual_stat_pct" in spec_effects:
                        dual_mult = 1 + spec_effects["dual_stat_pct"]["value"] / 100
                        player_stats["damage"] = float(player_stats["damage"]) * dual_mult
                        player_stats["armor"] = float(player_stats["armor"]) * dual_mult
                    player_stats["damage"] = float(player_stats["damage"]) * bard_damage_mult

                    player_dict = {
                        "user": player["user"],
                        "hp": player_stats["hp"],
                        "max_hp": player_stats["max_hp"],
                        "damage": player_stats["damage"],
                        "armor": player_stats["armor"],
                        "is_dragon": False,
                        "is_pet": False,
                        "tank_evolution": tank_evolution if tank_evolution else None,
                        "beastmaster_evolution": beastmaster_evolution if beastmaster_evolution else None,
                        "mage_evolution": mage_evolution if mage_evolution else None,
                        "reaper_evolution": reaper_evolution if reaper_evolution else None,
                        "santa_evolution": santa_evolution if santa_evolution else None,
                        "warrior_evolution": warrior_evolution if warrior_evolution else None,
                        "warrior_momentum": 0,
                        "fireball_charge": 0.0,
                        "spec_effects": spec_effects,
                    }
                    unique_participants[player_id] = player_dict
                    battle_participants.append(player_dict)

            else:
                # If player is already a pet or another type
                battle_participants.append(player)
                #await ctx.send(f"Added player (non-Member type) to battle: {player}")

            # Handle pet
            if pet:
                if pet.get("is_pet", False):
                    owner_id = pet.get("owner_id", "unknown_owner")
                    pet_name = pet.get("pet_name", "unknown_pet")
                    pet_unique_id = f"pet_{owner_id}_{pet_name}"
                    if pet_unique_id not in unique_participants:
                        pet_stats = await self.get_pet_stats(pet["user"].id)
                        # Beastcaller/Packleader specs and Beastmaster class boost the owner's pet.
                        owner_dict = unique_participants.get(owner_id)
                        pet_mult = 1.0
                        pack_bond = (owner_dict or {}).get("spec_effects", {}).get("pet_stat_pct")
                        if pack_bond:
                            pet_mult += pack_bond["value"] / 100
                        beastmaster_grade = (owner_dict or {}).get("beastmaster_evolution")
                        if beastmaster_grade:
                            pet_mult += 0.03 * int(beastmaster_grade)
                        if pet_mult != 1.0:
                            for stat_key in ("hp", "max_hp", "damage", "armor"):
                                pet_stats[stat_key] = float(pet_stats[stat_key]) * pet_mult
                        pet_dict = {
                            "user": pet["user"],
                            "owner_id": owner_id,
                            "pet_name": pet_name,
                            "hp": pet_stats["hp"],
                            "max_hp": pet_stats["max_hp"],
                            "damage": pet_stats["damage"],
                            "armor": pet_stats["armor"],
                            "is_dragon": False,
                            "is_pet": True,
                            # Add other necessary attributes
                        }
                        unique_participants[pet_unique_id] = pet_dict
                        battle_participants.append(pet_dict)
                else:
                    # If pet is already a dictionary or another type
                    battle_participants.append(pet)
                    #await ctx.send(f"Added pet (non-Member type) to battle: {pet}")
            else:
                player_name = player["user"].display_name if not player.get("is_pet", False) else player.get("pet_name",
                                                                                                             "Unknown Pet")
                #await ctx.send(f"No pet for player: {player_name}")

        # Initialize battle turn order
        initial_turn_order = [dragon] + battle_participants
        random.shuffle(initial_turn_order)

        # Remove duplicates based on unique identifiers
        seen_ids = set()
        unique_turn_order = []
        for entity in initial_turn_order:
            if entity.get("is_dragon", False):
                entity_id = "dragon"
            elif entity.get("is_pet", False):
                owner_id = entity.get("owner_id", "unknown_owner")
                pet_name = entity.get("pet_name", "unknown_pet")
                entity_id = f"pet_{owner_id}_{pet_name}"
            else:
                entity_id = entity["user"].id

            if entity_id not in seen_ids:
                seen_ids.add(entity_id)
                unique_turn_order.append(entity)
                name = "Dragon" if entity.get("is_dragon", False) else (
                    entity["user"].display_name if not entity.get("is_pet", False) else entity["pet_name"]
                )
                #await ctx.send(f"Added to turn order: {name}")
        random.shuffle(unique_turn_order)

        battle_turn_order = unique_turn_order

        # Debug: await ctx.send final turn order
        #await ctx.send("Final battle turn order:")
        for entity in battle_turn_order:
            if entity.get("is_dragon", False):
                name = "Dragon"
            elif entity.get("is_pet", False):
                name = entity.get("pet_name", "Unknown Pet")
            else:
                name = entity["user"].display_name
            #await ctx.send(f"- {name}")

        # Initialize battle log and message
        battle_log = deque(maxlen=20)
        battle_log.append(f"**Action #1**\nThe battle against the Dragon has begun! 🐉")

        # Add passive effect descriptions
        passive_descriptions = []
        for passive in dragon_stats.get("passives", []):
            if passive == "Ice Armor":
                passive_descriptions.append("❄️ Ice Armor reduces all damage by 20%")
            elif passive == "Corruption":
                passive_descriptions.append("Corruption reduces shields/armor by 20%")
            elif passive == "Void Fear":
                passive_descriptions.append("😱 Void Fear reduces attack power by 20%")
            elif passive == "Aspect of death":
                passive_descriptions.append("💀 Aspect of death reduces attack and defense by 30%")
            elif passive == "Abyssal Presence":
                passive_descriptions.append("🌌 Abyssal Presence reduces attack and defense by 35%")

        if passive_descriptions:
            battle_log.append("**Dragon's Passive Effects:**\n" + "\n".join(passive_descriptions))

        # Announce this week's mutators
        mutator_lines = self.describe_mutators(dragon_stats.get("mutators", []))
        if mutator_lines:
            battle_log.append("**This Week's Mutators:**\n" + "\n".join(mutator_lines))

        # Create initial embed
        battle_msg = await ctx.send(embed=await self.create_battle_embed(dragon, battle_participants, battle_log))
        await asyncio.sleep(2)

        try:
            start_time = datetime.utcnow()
            action_number = 2
            battle_ongoing = True
            current_round = 1
            last_stand_used = False

            while battle_ongoing and datetime.utcnow() < start_time + timedelta(minutes=15):
                try:
                    #await ctx.send(f"--- Starting Round {current_round} ---")

                    # Reset turn order at start of each round to match initial order
                    active_turn_order = battle_turn_order.copy()
                    round_order_names = [
                        "Dragon" if entity.get("is_dragon", False) else (
                            entity["user"].display_name if not entity.get("is_pet", False) else entity["pet_name"]
                        )
                        for entity in active_turn_order
                    ]
                    #await ctx.send(f"Round {current_round} order: {round_order_names}")

                    # Process each participant's turn in the fixed order
                    for entity in active_turn_order:
                        if not battle_ongoing:
                            break

                        # Skip if entity died
                        if entity["hp"] <= 0:
                            name = "Dragon" if entity.get("is_dragon", False) else (
                                entity["user"].display_name if not entity.get("is_pet", False) else entity["pet_name"]
                            )
                            #await ctx.send(f"Skipping dead entity: {name}")
                            continue

                        # Check battle end conditions
                        if dragon["hp"] <= 0:
                            battle_ongoing = False
                            break
                        if all(p["hp"] <= 0 for p in battle_participants):
                            # Last Stand: once per battle, one fallen hero rises for a final blow
                            if not last_stand_used:
                                last_stand_used = True
                                fallen_players = [p for p in battle_participants if not p.get("is_pet")]
                                if fallen_players:
                                    hero = random.choice(fallen_players)
                                    hero["hp"] = 1.0
                                    hero["defiance"] = True
                                    # Death purged their ailments; they rise clean
                                    for status in ("frozen", "stunned", "dot", "arena_hazard", "cursed"):
                                        hero.pop(status, None)
                                    battle_log.append(
                                        f"**Action #{action_number}**\n💢 **{hero['user'].display_name}** refuses to fall! "
                                        "They rise with one final breath — their next strike deals **double damage**!"
                                    )
                                    action_number += 1
                                    await self.update_battle_embed(battle_msg, dragon, battle_participants, battle_log)
                                    await asyncio.sleep(2)
                                    continue
                            battle_ongoing = False
                            break

                        # Rest of your turn processing code
                        current_action_log = []

                        if entity.get("is_dragon"):
                            # Dragon's turn (a hero mid-Last-Stand can't be targeted)
                            valid_targets = [
                                p for p in battle_participants
                                if p["hp"] > 0 and not p.get("defiance")
                            ]
                            if not valid_targets:
                                if any(p.get("defiance") for p in battle_participants):
                                    # Only the risen hero remains — the dragon can't touch them
                                    current_action_log.append(
                                        "🐉 The dragon rears back, stunned by this act of defiance!"
                                    )
                                    if current_action_log:
                                        for log_entry in current_action_log:
                                            battle_log.append(f"**Action #{action_number}**\n{log_entry}")
                                            action_number += 1
                                        await self.update_battle_embed(battle_msg, dragon, battle_participants, battle_log)
                                        await asyncio.sleep(2)
                                    continue
                                battle_ongoing = False
                                break

                            mut_fx = dragon.get("mutator_effects", {})
                            use_special = random.random() < mut_fx.get("special_chance", 0.4)
                            if use_special:
                                await self.execute_dragon_move(dragon_stats, valid_targets, current_action_log)
                            else:
                                # Identify tanks among valid targets
                                tanks = [p for p in valid_targets if p.get("tank_evolution") is not None]

                                # 60% chance to target a tank if any exist
                                if tanks and random.random() < 0.85:
                                    target = random.choice(tanks)
                                else:
                                    target = random.choice(valid_targets)

                                bonus = Decimal(random.randint(0, 100))
                                # Razor Winds mutator: dragon ignores part of the target's armor
                                effective_armor = float(target["armor"]) * (1 - mut_fx.get("armor_pierce", 0.0))
                                # Calculate damage and round to two decimal places
                                damage = round(
                                    max(1.0, float(dragon["damage"]) - effective_armor + float(bonus)), 2)
                                # Thin Ice mutator: everyone takes extra damage
                                damage = round(damage * mut_fx.get("mutual_damage_mult", 1.0), 2)
                                damage = round(
                                    damage * (1 - float(dragon.get("krampus_weakness_pct", 0) or 0)),
                                    2,
                                )
                                if target.get("damage_reduction"):
                                    damage *= (1 - target["damage_reduction"])

                                # Class specialization defenses (may reflect onto the dragon)
                                damage, spec_def_msgs = self.apply_defensive_specs(
                                    target, damage, battle_participants, dragon
                                )

                                target["hp"] = max(0, target["hp"] - damage)
                                name = target["user"].display_name if not target.get("is_pet", False) else target[
                                    "pet_name"]
                                message = f"Dragon attacks **{name}** for **{damage:,.1f}HP** damage"

                                if target["hp"] <= 0:
                                    message += f"\n**{name}** has fallen! ☠️"
                                message += "!"
                                current_action_log.append(message)
                                current_action_log.extend(spec_def_msgs)
                                self._tick_ice_krampus_weakness(dragon, current_action_log)

                        else:
                            # Player/Pet turn
                            name = entity["user"].display_name if not entity.get("is_pet", False) else entity[
                                "pet_name"]

                            # Legacy low-HP recovery fallback.
                            current_action_log.extend(self.maybe_second_wind(entity))

                            # Process status effects
                            can_attack = True
                            if entity.get("frozen") or entity.get("stunned"):
                                status = "frozen" if entity.get("frozen") else "stunned"
                                current_action_log.append(f"**{name}** is {status} and cannot move!")
                                can_attack = False

                                for status_effect in ["frozen", "stunned"]:
                                    if entity.get(status_effect):
                                        entity[status_effect] -= 1
                                        if entity[status_effect] <= 0:
                                            del entity[status_effect]

                            for debuff in ["damage_down", "armor_down"]:
                                if entity.get(debuff):
                                    entity[debuff]["duration"] -= 1
                                    if entity[debuff]["duration"] <= 0:
                                        # Restore original stats
                                        if debuff == "damage_down":
                                            entity["damage"] = entity["original_damage"]
                                            del entity["original_damage"]
                                        elif debuff == "armor_down":
                                            entity["armor"] = entity["original_armor"]
                                            del entity["original_armor"]
                                        del entity[debuff]
                                        current_action_log.append(
                                            f"**{name}**'s {debuff.replace('_', ' ')} effect has worn off!")

                            # Process DoTs
                            dot_damage = 0
                            for effect in ["dot", "arena_hazard"]:
                                if entity.get(effect):
                                    effect_data = entity[effect]
                                    damage = effect_data["damage"]
                                    entity["hp"] = max(0, entity["hp"] - damage)
                                    dot_damage += damage

                                    effect_data["duration"] -= 1
                                    if effect_data["duration"] <= 0:
                                        del entity[effect]

                            if can_attack and entity["hp"] > 0:
                                mut_fx = dragon.get("mutator_effects", {})
                                bonus = Decimal(random.randint(0, 100))
                                damage = max(1,
                                             round(float(entity["damage"]) - float(dragon["armor"]) + float(bonus), 2))

                                if entity.get("damage_down"):
                                    damage *= 0.7
                                # Thin Ice mutator: the dragon takes extra damage too
                                damage = round(float(damage) * mut_fx.get("mutual_damage_mult", 1.0), 2)

                                # Mage Fireball: a charge builds each turn; when full,
                                # this attack casts a boosted Fireball (and lets Overload
                                # detonate its banked Arcane charges).
                                is_fireball = False
                                fireball_msg = None
                                if entity.get("mage_evolution") and not entity.get("is_pet", False):
                                    charge = float(entity.get("fireball_charge", 0.0)) + self.MAGE_FIREBALL_CHARGE_PER_TURN
                                    if charge >= 1.0:
                                        entity["fireball_charge"] = charge - 1.0
                                        mult = self.MAGE_FIREBALL_MULTIPLIER.get(entity["mage_evolution"], 1.0)
                                        damage = round(float(damage) * mult, 2)
                                        is_fireball = True
                                        fireball_msg = f"🔥 **{name}** channels a Fireball!"
                                    else:
                                        entity["fireball_charge"] = charge

                                # Class specialization bonuses (offense)
                                damage, warrior_atk_msgs = self.apply_ice_warrior_attack(
                                    entity, damage, is_fireball=is_fireball
                                )
                                damage, spec_atk_msgs = self.apply_offensive_specs(
                                    entity, dragon, damage, is_fireball=is_fireball
                                )
                                spec_atk_msgs = warrior_atk_msgs + spec_atk_msgs
                                if fireball_msg:
                                    spec_atk_msgs.insert(0, fireball_msg)

                                # Last Stand: the risen hero's final strike deals double damage
                                defiance_strike = entity.pop("defiance", False)
                                if defiance_strike:
                                    damage = round(float(damage) * 2, 2)

                                dragon["hp"] = round(max(0, float(dragon["hp"]) - float(damage)), 2)
                                seasonal_damage, seasonal_msgs = self.apply_ice_seasonal_attack(
                                    entity,
                                    dragon,
                                    battle_participants,
                                    damage,
                                )
                                total_attack_damage = float(damage) + float(seasonal_damage)

                                # Track stats for the battle recap
                                entity["stat_damage_dealt"] = entity.get("stat_damage_dealt", 0.0) + total_attack_damage
                                if total_attack_damage > entity.get("stat_biggest_hit", 0.0):
                                    entity["stat_biggest_hit"] = total_attack_damage

                                # Reflective Scales mutator: part of the damage bounces back
                                reflected = 0.0
                                if mut_fx.get("reflect_pct"):
                                    reflected = round(total_attack_damage * mut_fx["reflect_pct"], 2)
                                    entity["hp"] = max(0, round(float(entity["hp"]) - reflected, 2))

                                if defiance_strike:
                                    message = f"💢 **{name}** puts everything into one final strike for **{damage:,.1f}HP** damage"
                                else:
                                    message = f"**{name}** attacks dragon for **{damage:,.1f}HP** damage"
                                if reflected > 0:
                                    message += f", but the dragon's scales reflect **{reflected:,.1f}HP** back 🪞"
                                if dot_damage > 0:
                                    message += f" and takes **{dot_damage:,.1f}HP** damage from bleeding"
                                if defiance_strike:
                                    if dragon["hp"] <= 0:
                                        message += f"\n⚡ **{name}**'s final blow FELLS THE DRAGON!"
                                    else:
                                        entity["hp"] = 0
                                        message += f"\n**{name}** collapses, their defiance spent... ☠️"
                                elif entity["hp"] <= 0:
                                    message += f"\n**{name}** has fallen! ☠️"
                                message += "!"
                                current_action_log.append(message)
                                current_action_log.extend(spec_atk_msgs)
                                current_action_log.extend(seasonal_msgs)
                            elif dot_damage > 0:
                                message = f"**{name}** takes **{dot_damage:,.1f}HP** damage from bleeding"
                                if entity["hp"] <= 0:
                                    message += f"\n**{name}** has fallen! ☠️"
                                message += "!"
                                current_action_log.append(message)

                        # Log actions and update display
                        if current_action_log:
                            for log_entry in current_action_log:
                                battle_log.append(f"**Action #{action_number}**\n{log_entry}")
                                action_number += 1
                            await self.update_battle_embed(battle_msg, dragon, battle_participants, battle_log)
                            await asyncio.sleep(2)

                    #await ctx.send(f"--- End of Round {current_round} ---")
                    current_round += 1

                except Exception as e:
                    import traceback
                    error_message = f"Error occurred: {e}\n"
                    error_message += traceback.format_exc()
                    await ctx.send(error_message)
                    print(error_message)
                    continue

            # Handle battle end
            if dragon["hp"] <= 0:
                battle_log.append(f"**Action #{action_number}**\nThe dragon has been defeated! Victory! 🎉")
                await self.update_battle_embed(battle_msg, dragon, battle_participants, battle_log)
                await self.handle_victory(ctx, party_members, dragon, current_level, weekly_defeats)
            elif not any(p["hp"] > 0 for p in battle_participants):
                battle_log.append(f"**Action #{action_number}**\nThe party has been defeated! 💀")
                await self.update_battle_embed(battle_msg, dragon, battle_participants, battle_log)
                await self.handle_defeat(ctx, party_members)
            else:
                battle_log.append(f"**Action #{action_number}**\nTime's up! The battle was inconclusive! ⏰")
                await self.update_battle_embed(battle_msg, dragon, battle_participants, battle_log)
                await ctx.send("Time's up! The battle was inconclusive!")

            # Post-fight MVP recap
            try:
                await ctx.send(
                    embed=self.build_recap_embed(battle_participants, victory=dragon["hp"] <= 0)
                )
            except Exception:
                pass

        except Exception as e:
            import traceback
            error_message = f"Error occurred: {e}\n"
            error_message += traceback.format_exc()
            await ctx.send(error_message)
            print(error_message)


    def create_battle_log_entry(self, action_number, message):
        """Helper function to create properly formatted log entries"""
        return f"**Action #{action_number}**{message}"

    def create_hp_bar(self, current_hp, max_hp, length=20):
        """Create a visual HP bar"""
        ratio = max(0, min(1, current_hp / max_hp))
        filled = int(length * ratio)
        bar = "█" * filled + "░" * (length - filled)
        return bar

    def build_recap_embed(self, battle_participants, victory):
        """Post-fight MVP recap: top damage, biggest hit, most damage soaked, fallen."""
        def display(c):
            return c["user"].display_name if not c.get("is_pet") else c.get("pet_name", "Pet")

        def damage_taken(c):
            return float(c["max_hp"]) - max(0.0, float(c["hp"]))

        embed = discord.Embed(
            title="📊 Battle Recap" + (" — Victory! 🎉" if victory else " — Defeat 💀"),
            color=0x2ECC71 if victory else 0xE74C3C,
        )

        top_dmg = max(battle_participants, key=lambda c: c.get("stat_damage_dealt", 0.0), default=None)
        if top_dmg and top_dmg.get("stat_damage_dealt", 0.0) > 0:
            embed.add_field(
                name="🥇 MVP — Top Damage",
                value=f"**{display(top_dmg)}** — {top_dmg['stat_damage_dealt']:,.1f} total damage",
                inline=False,
            )

        big_hit = max(battle_participants, key=lambda c: c.get("stat_biggest_hit", 0.0), default=None)
        if big_hit and big_hit.get("stat_biggest_hit", 0.0) > 0:
            embed.add_field(
                name="💥 Biggest Hit",
                value=f"**{display(big_hit)}** — {big_hit['stat_biggest_hit']:,.1f} in one strike",
                inline=False,
            )

        tankiest = max(battle_participants, key=damage_taken, default=None)
        if tankiest and damage_taken(tankiest) > 0:
            embed.add_field(
                name="🛡️ Drew the Dragon's Ire",
                value=f"**{display(tankiest)}** — soaked {damage_taken(tankiest):,.1f} damage",
                inline=False,
            )

        fallen = [display(c) for c in battle_participants if c["hp"] <= 0]
        embed.add_field(
            name="☠️ Fallen",
            value=", ".join(fallen) if fallen else "No one — a flawless hunt!",
            inline=False,
        )
        return embed

    @commands.hybrid_command(name="totalboard", description="Shows the top 10 dragon slayers and your rank")
    async def totalboard(self, ctx: commands.Context):
        async with self.bot.pool.acquire() as conn:
            # Get top 10
            top_10 = await conn.fetch('''
                SELECT user_id, total_defeats, 
                       RANK() OVER (ORDER BY total_defeats DESC) as rank
                FROM dragon_contributions 
                ORDER BY total_defeats DESC 
                LIMIT 10
            ''')
            # Get user's rank if not in top 10
            user_rank = await conn.fetchrow('''
                WITH rankings AS (
                    SELECT user_id, total_defeats,
                           RANK() OVER (ORDER BY total_defeats DESC) as rank
                    FROM dragon_contributions
                )
                SELECT * FROM rankings WHERE user_id = $1
            ''', ctx.author.id)

            embed = discord.Embed(title="🏆 Total Dragon Defeats Leaderboard", color=discord.Color.gold())
            # Format top 10
            leaderboard_text = ""
            for entry in top_10:
                leaderboard_text += f"{entry['rank']}. <@{entry['user_id']}> - {entry['total_defeats']} defeats\n"
            embed.description = leaderboard_text
            # Add user's rank if not in top 10
            if user_rank and not any(entry['user_id'] == ctx.author.id for entry in top_10):
                embed.add_field(
                    name="Your Rank",
                    value=f"#{user_rank['rank']} - {user_rank['total_defeats']} defeats",
                    inline=False
                )
            await ctx.send(embed=embed)

    @is_gm()
    @commands.hybrid_command()
    async def resetdragon(self, ctx, channel_id: int = None):
        """
        Reset the dragon progress and weekly contributions.
        Usage: $resetdragon [channel_id]
        """
        try:
            async with self.bot.pool.acquire() as conn:
                # Delete all rows from dragon_progress
                await conn.execute('DELETE FROM dragon_progress')

                # Insert fresh dragon_progress row
                await conn.execute('''
                    INSERT INTO dragon_progress (id, current_level, weekly_defeats, last_reset) 
                    VALUES (1, 1, 0, $1)
                ''', datetime.utcnow())

                # Reset weekly_defeats in dragon_contributions
                await conn.execute('''
                    UPDATE dragon_contributions 
                    SET weekly_defeats = 0
                ''')

                # Send confirmation to command user
                await ctx.send("✅ Dragon has been reset successfully!")

                # If channel_id is provided, send announcement
                if channel_id:
                    try:
                        channel = self.bot.get_channel(channel_id)
                        if channel:
                            embed = discord.Embed(
                                title="🐉 Dragon Reset",
                                description="The Ice Dragon has been reset to level 1!\nAll weekly progress has been cleared.",
                                color=0x87CEEB
                            )
                            embed.add_field(
                                name="New Challenge Awaits!",
                                value="The Frostbite Wyrm awaits new challengers... Will you face the dragon?",
                                inline=False
                            )
                            await channel.send(embed=embed)
                        else:
                            await ctx.send("⚠️ Warning: Could not find the specified channel.")
                    except Exception as e:
                        await ctx.send(f"⚠️ Error sending announcement: {str(e)}")

        except Exception as e:
            await ctx.send(f"❌ Error resetting dragon: {str(e)}")

    @commands.hybrid_command(name="weeklyboard", description="Shows the top 10 weekly dragon slayers and your rank")
    async def weeklyboard(self, ctx: commands.Context):
        async with self.bot.pool.acquire() as conn:
            # Get top 10
            top_10 = await conn.fetch('''
                SELECT user_id, weekly_defeats,
                       RANK() OVER (ORDER BY weekly_defeats DESC) as rank
                FROM dragon_contributions 
                ORDER BY weekly_defeats DESC 
                LIMIT 10
            ''')
            # Get user's rank if not in top 10
            user_rank = await conn.fetchrow('''
                WITH rankings AS (
                    SELECT user_id, weekly_defeats,
                           RANK() OVER (ORDER BY weekly_defeats DESC) as rank
                    FROM dragon_contributions
                )
                SELECT * FROM rankings WHERE user_id = $1
            ''', ctx.author.id)


            reset_data = await conn.fetchrow('SELECT last_reset FROM dragon_progress WHERE id = 1')
            footer_text = "Reset time unavailable"
            if reset_data:
                last_reset = reset_data['last_reset']
                next_reset = last_reset + timedelta(days=7)
                now = datetime.utcnow()
                remaining = next_reset - now
                
                # Handle negative time (reset overdue)
                if remaining < timedelta(0):
                    remaining = timedelta(0)
                
                days = remaining.days
                seconds = remaining.seconds
                hours = seconds // 3600
                minutes = (seconds % 3600) // 60
                footer_text = f"Time until next reset: {days}d {hours}h {minutes}m"


            embed = discord.Embed(title="🐉 Weekly Dragon Defeats Leaderboard", color=discord.Color.green())
            # Format top 10
            leaderboard_text = ""
            for entry in top_10:
                leaderboard_text += f"{entry['rank']}. <@{entry['user_id']}> - {entry['weekly_defeats']} defeats\n"
            embed.description = leaderboard_text
            # Add user's rank if not in top 10
            if user_rank and not any(entry['user_id'] == ctx.author.id for entry in top_10):
                embed.add_field(
                    name="Your Rank",
                    value=f"#{user_rank['rank']} - {user_rank['weekly_defeats']} defeats",
                    inline=False
                )
            embed.set_footer(text=footer_text)
            await ctx.send(embed=embed)

    async def handle_victory(self, ctx, party_members, dragon, old_level, weekly_defeats):
        """Handle victory rewards and progression"""
        dragon_stats = await self.calculate_dragon_stats()
        stage_name = dragon_stats["stage"]

        async with self.bot.pool.acquire() as conn:
            # Get the current timestamp
            current_time = datetime.now()

            # Iterate over party members
            for member in party_members:
                # Upsert query to update or insert a row
                await conn.execute(
                    '''
                    INSERT INTO dragon_contributions (user_id, weekly_defeats, total_defeats, last_defeat)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (user_id) DO UPDATE
                    SET 
                        weekly_defeats = dragon_contributions.weekly_defeats + EXCLUDED.weekly_defeats,
                        total_defeats = dragon_contributions.total_defeats + EXCLUDED.total_defeats,
                        last_defeat = EXCLUDED.last_defeat
                    ''',
                    member.id,  # $1 - user_id
                    1,  # $2 - weekly_defeats
                    1,  # $3 - total_defeats
                    current_time  # $4 - last_defeat
                )

        async with self.bot.pool.acquire() as conn:
            result = await conn.fetchrow(
                'SELECT current_level, weekly_defeats, last_reset FROM dragon_progress WHERE id = 1'
            )
            if not result:
                weekly_defeats = 0
                current_level = result['current_level']
            else:
                current_level = result['current_level']
                weekly_defeats = result['weekly_defeats']
                last_reset = result['last_reset']

        if old_level == current_level:
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    '''
                    UPDATE dragon_progress
                    SET weekly_defeats = weekly_defeats + 1
                    '''
                )
            weekly_defeats = weekly_defeats + 1

            if weekly_defeats > 0 and weekly_defeats % 40 == 0:
                async with self.bot.pool.acquire() as conn:
                    await conn.execute('''
                        UPDATE dragon_progress
                        SET current_level = current_level + 1
                    ''')
                new_level = current_level + 1
                await ctx.send(f"🐉 The dragon grows stronger! Now level **{new_level}**! ⚔️")
                if new_level == 25:
                    await ctx.send(
                        "🌌 **The dragon sheds its final skin... The Abyssal Maw awakens!**\n"
                        "It will never evolve again — it will only grow stronger. Forever. "
                        "How far can the server push it?"
                    )
                if new_level > 24:
                    try:
                        await self.check_world_record(ctx, party_members, new_level)
                    except Exception:
                        pass
        else:
            await ctx.send(
                "Someone beat the dragon and evolved it before you could kill it! You'll still receive your reward, but this fight will **not** count towards the weekly defeat.")

        rewards = self.STAGE_REWARDS[stage_name]

        async with self.bot.pool.acquire() as conn:
            for member in party_members:


                # Chance for special loot (base 1%, Hoard Fever mutator can boost it)
                loot_chance = 0.01 * dragon_stats.get("mutator_effects", {}).get("loot_mult", 1.0)
                if random.random() < loot_chance:
                    item = random.choice(rewards["items"])
                    item_name, item_type, *stats = item

                    # Handle crate rewards
                    if item_type == "crate":
                        crate_type = item_name.lower()  # fortune or divine
                        await conn.execute(
                            f'UPDATE profile SET crates_{crate_type} = crates_{crate_type} + 1 WHERE "user"=$1;',
                            member.id
                        )
                        await ctx.send(f"{member.mention} found a **{item_name} crate**! 🎁")
                        continue

                    # Handle equipment rewards
                    item_type = item_type.capitalize()  # Capitalize first letter
                    element = random.choice(["water", "dark", "corrupted"])

                    # Determine hand based on item type
                    if item_type in ["Bow", "Scythe"]:
                        hand = "both"
                    elif item_type in ["Shield"]:
                        hand = "left"
                    else:  # Sword, Hammer, Axe, Wand <- Updated 2/2
                        hand = "any"

                    # Set damage or armor based on item type
                    damage = 0.0
                    armor = 0.0
                    if item_type == "Shield":
                        armor = round(random.uniform(stats[0], stats[1]))
                    else:
                        damage = round(random.uniform(stats[0], stats[1]))

                    # Create the item
                    await self.bot.create_item(
                        name=_(item_name),
                        value=stats[-1],  # Last number in tuple is value
                        type_=item_type,
                        element=element,
                        damage=damage,
                        armor=armor,
                        owner=member,
                        hand=hand,
                        equipped=False,
                        conn=conn,
                    )
                    await ctx.send(f"{member.mention} found a **{item_name}**! 🎁")

        victory_text = (
            f"🎉 **Victory!** The **{stage_name}** has been defeated!\n"
            #f"Each party member receives **{snowflakes_per_member:,} snowflakes**! ❄️"
        )
        await ctx.send(victory_text)

        # Let other systems (Legacy Points, bounties, ...) react to the kill
        self.bot.dispatch("icedragon_victory", ctx, party_members, stage_name, current_level)

    async def handle_defeat(self, ctx, party_members):
        """Handle party defeat"""
        await ctx.send(
            f"💀 The **Dragon** was too powerful! "
            "The party has been defeated!"
        )

async def setup(bot):
    await bot.add_cog(IceDragonChallenge(bot))
    await bot.tree.sync()
