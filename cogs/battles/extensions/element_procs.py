# battles/extensions/element_procs.py
"""Opt-in elemental procs (test feature).

A player's normal attack can proc its weapon element's ability, but only while
that element holds the matchup advantage. Starforge stars on the weapon gate
and scale the chance:

    ★1+   common proc   2% → 3% at ★10
    ★5+   mythic proc   0.05% → 0.10% at ★10
    ★10   Light's mythic, Power Word: Die, at 0.01%

Pets never proc and procs never touch pet or class state - everything lives on
``element_proc_*`` attributes. Bosses ignore mythics. Players opt in; a player
(or their pet) who has not opted in can never be hit by a proc.
"""

import random
from decimal import Decimal

from utils.elements import ELEMENT_STRENGTHS, normalize_element

OPT_IN_TABLE = "element_proc_optin"

COMMON_MIN_STARS = 1
MYTHIC_MIN_STARS = 5
POWER_WORD_MIN_STARS = 10
MAX_STARS = 10

COMMON_CHANCE_MIN = Decimal("0.02")
COMMON_CHANCE_MAX = Decimal("0.03")
MYTHIC_CHANCE_MIN = Decimal("0.0005")
MYTHIC_CHANCE_MAX = Decimal("0.001")
POWER_WORD_CHANCE = Decimal("0.0001")

POWER_WORD_DAMAGE = Decimal("9999999")
JUDGMENT_MISSING_HP_PCT = Decimal("0.05")
DREAD_DAMAGE_MULT = Decimal("0.75")
HEX_ATTACKS = 2
IGNITE_HITS = 2
IGNITE_MAX_HP_PCT = Decimal("0.015")
IGNITE_DAMAGE_CAP_PCT = Decimal("0.50")
OVERGROWTH_HEAL_PCT = Decimal("0.04")
EROSION_ARMOR_PCT = Decimal("0.05")
EROSION_MAX_STACKS = 3
TREMOR_PCT = Decimal("0.40")
ARC_PCT = Decimal("0.30")
ECLIPSE_TURNS = 2
PYRE_MAX_HP_PCT = Decimal("0.15")
TEMPEST_DODGES = 3

COMMON = "common"
MYTHIC = "mythic"

PROC_NAMES = {
    "Light": ("Judgment", "Power Word: Die"),
    "Dark": ("Dread", "Eclipse"),
    "Corrupted": ("Hex", "Unmaking"),
    "Fire": ("Ignite", "Pyre"),
    "Nature": ("Overgrowth", "Bloom"),
    "Water": ("Erosion", "Drown"),
    "Earth": ("Tremor", "Cataclysm"),
    "Electric": ("Arc", "Overload"),
    "Wind": ("Gust", "Tempest"),
}

PROC_DESCRIPTIONS = {
    "Light": (
        "Adds armor-ignoring damage equal to 5% of the target's missing HP before this hit, "
        "capped at 100% of your attack stat. A full-health target gives no bonus.",
        "Raises this hit's damage to at least 9,999,999 before shields and other damage mitigation.",
    ),
    "Dark": (
        "The target's next normal attack deals 25% less damage before armor. Reapplying refreshes the effect.",
        "The target loses its next 2 turns. Reapplying resets the remaining duration to 2 turns.",
    ),
    "Corrupted": (
        "The target's next 2 normal attacks lose their element, removing elemental matchup bonuses "
        "and preventing elemental procs on those attacks. Its defensive element is unchanged.",
        "The target's normal attacks become elementless for the rest of the battle, removing "
        "elemental matchup bonuses and preventing its elemental procs. Its defensive element is unchanged.",
    ),
    "Fire": (
        "The next 2 normal hits that land on the target each add burn damage equal to 1.5% of its max HP, "
        "capped at 50% of your attack stat per burn. Burn bypasses armor; reapplying refreshes it.",
        "Adds armor-ignoring damage equal to 15% of the target's maximum HP to this hit.",
    ),
    "Nature": (
        "Immediately heals you for 4% of your maximum HP, up to full health.",
        "Immediately restores you to full HP. Can trigger only once per battle; common healing can still trigger afterward.",
    ),
    "Water": (
        "Reduces the target's effective armor by 5% per stack for the rest of the battle. "
        "Stacks up to 3 times for 15% total reduction, affecting subsequent hits.",
        "Sets the target's effective armor to zero for the rest of the battle, affecting subsequent hits. Does not remove shields.",
    ),
    "Earth": (
        "Adds 40% of this hit's damage after armor as extra damage. For example, a 100-damage hit becomes 140.",
        "Doubles this hit's damage and also deals that doubled amount to every other living, eligible "
        "enemy. The extra targets' armor is bypassed; bosses and players who opted out are excluded.",
    ),
    "Electric": (
        "Adds 30% of this attack's damage before armor as bonus damage that bypasses armor.",
        "Adds 100% of this attack's damage before armor as an immediate bonus strike that bypasses armor.",
    ),
    "Wind": (
        "Dodge the next incoming normal attack that would deal damage. Reapplying refreshes the charge rather than stacking it.",
        "Dodge the next 3 incoming normal attacks that would deal damage. Reapplying restores the charges to 3.",
    ),
}

PROC_EMOJI = {
    "Light": "🌟",
    "Dark": "🌑",
    "Corrupted": "🌀",
    "Fire": "🔥",
    "Nature": "🌿",
    "Water": "💧",
    "Earth": "🌍",
    "Electric": "⚡",
    "Wind": "💨",
}


def _dec(value, default="0"):
    try:
        return Decimal(str(value if value is not None else default))
    except Exception:
        return Decimal(default)


def _fmt(value):
    return f"{int(_dec(value)):,}"


class ElementProcExtension:
    """Rolls and applies element procs. Stateless apart from the injected RNG."""

    def __init__(self, rng=None):
        self.rng = rng or random.random

    # ------------------------------------------------------------------ chances
    @staticmethod
    def common_chance(stars):
        stars = max(0, min(MAX_STARS, int(stars or 0)))
        if stars < COMMON_MIN_STARS:
            return Decimal("0")
        span = MAX_STARS - COMMON_MIN_STARS
        return COMMON_CHANCE_MIN + (COMMON_CHANCE_MAX - COMMON_CHANCE_MIN) * (stars - COMMON_MIN_STARS) / span

    @staticmethod
    def mythic_chance(element, stars):
        element = normalize_element(element)
        stars = max(0, min(MAX_STARS, int(stars or 0)))
        if element == "Light":
            return POWER_WORD_CHANCE if stars >= POWER_WORD_MIN_STARS else Decimal("0")
        if stars < MYTHIC_MIN_STARS:
            return Decimal("0")
        span = MAX_STARS - MYTHIC_MIN_STARS
        return MYTHIC_CHANCE_MIN + (MYTHIC_CHANCE_MAX - MYTHIC_CHANCE_MIN) * (stars - MYTHIC_MIN_STARS) / span

    @staticmethod
    def weapon_stars_by_element(items):
        """Best starforge level per element across equipped non-shield weapons.

        ``items`` rows need ``type``, ``element`` and ``stars``.
        """
        stars_by_element = {}
        for item in items or []:
            try:
                item_type = str(item["type"] or "")
                element = normalize_element(item["element"])
                stars = int(item["stars"] or 0)
            except (KeyError, IndexError, TypeError, ValueError):
                continue
            if item_type.lower() == "shield" or element == "Unknown" or stars <= 0:
                continue
            stars_by_element[element] = max(stars_by_element.get(element, 0), stars)
        return stars_by_element

    # ------------------------------------------------------------- eligibility
    @staticmethod
    def battle_allows_procs(battle):
        config = getattr(battle, "config", None)
        if not isinstance(config, dict):
            return False
        return bool(config.get("element_effects", True)) and bool(config.get("element_procs", True))

    @staticmethod
    def _user_id(value):
        user_id = getattr(value, "id", None)
        return user_id if isinstance(user_id, int) else None

    def _consent_holder(self, battle, defender):
        """Player combatants carry the opt-in flag; a pet answers to its owner."""
        if hasattr(defender, "element_procs_enabled") or not getattr(defender, "is_pet", False):
            return defender
        owner_id = self._user_id(getattr(defender, "owner", None)) or self._user_id(
            getattr(defender, "user", None)
        )
        if owner_id is None:
            return defender
        for team in getattr(battle, "teams", None) or []:
            for combatant in getattr(team, "combatants", []) or []:
                if getattr(combatant, "is_pet", False):
                    continue
                if self._user_id(getattr(combatant, "user", None)) == owner_id:
                    return combatant
        return defender

    def can_be_targeted(self, defender, battle=None):
        """Monsters never carry the flag; players (and their pets) must opt in."""
        holder = self._consent_holder(battle, defender)
        if not hasattr(holder, "element_procs_enabled"):
            return True
        return bool(holder.element_procs_enabled)

    def can_proc(self, battle, attacker, defender):
        if attacker is None or defender is None:
            return False
        if getattr(attacker, "is_pet", False):
            return False
        if not getattr(attacker, "element_procs_enabled", False):
            return False
        if not self.battle_allows_procs(battle):
            return False
        team_of = getattr(battle, "get_team_for_combatant", None)
        if callable(team_of):
            attacker_team = team_of(attacker)
            if attacker_team is not None and attacker_team is team_of(defender):
                return False  # possession, friendly fire
        return self.can_be_targeted(defender, battle)

    def roll(self, battle, attacker, defender, attack_element, defense_element):
        """Return ``(element, tier)`` for a proc this hit, or None."""
        if not self.can_proc(battle, attacker, defender):
            return None
        attack_element = normalize_element(attack_element)
        defense_element = normalize_element(defense_element)
        if ELEMENT_STRENGTHS.get(attack_element) != defense_element or defense_element == "Unknown":
            return None
        stars = int((getattr(attacker, "element_proc_stars", None) or {}).get(attack_element, 0) or 0)
        if stars < COMMON_MIN_STARS:
            return None

        mythic_blocked = bool(getattr(defender, "is_boss", False)) or (
            attack_element == "Nature" and getattr(attacker, "element_proc_bloom_used", False)
        )
        if not mythic_blocked:
            mythic = self.mythic_chance(attack_element, stars)
            if mythic > 0 and Decimal(str(self.rng())) < mythic:
                return attack_element, MYTHIC
        common = self.common_chance(stars)
        if common > 0 and Decimal(str(self.rng())) < common:
            return attack_element, COMMON
        return None

    # ------------------------------------------------------- persistent states
    @staticmethod
    def hexed_attack_element(attacker, element):
        """Corrupted Hex/Unmaking: the hexed combatant attacks without an element."""
        if attacker is None:
            return element
        if getattr(attacker, "element_proc_unmade", False):
            return "Unknown"
        charges = int(getattr(attacker, "element_proc_hex", 0) or 0)
        if charges <= 0:
            return element
        attacker.element_proc_hex = charges - 1
        return "Unknown"

    @staticmethod
    def action_lock_message(combatant):
        """Dark Eclipse: consume one skipped turn, if any."""
        turns = int(getattr(combatant, "element_proc_eclipse", 0) or 0)
        if turns <= 0:
            return None
        combatant.element_proc_eclipse = turns - 1
        return f"🌑 {combatant.name} is lost in the Eclipse and cannot act!"

    def consume_attacker_states(self, attacker, raw_damage):
        """Return ``(raw_damage, messages, nullified)`` before the hit resolves."""
        raw_damage = _dec(raw_damage)
        messages = []
        lock = self.action_lock_message(attacker)
        if lock:
            # Fallback for modes whose turn loop has no action-lock hook.
            return Decimal("0"), [lock], True
        dread = int(getattr(attacker, "element_proc_dread", 0) or 0)
        if dread > 0:
            attacker.element_proc_dread = dread - 1
            raw_damage *= DREAD_DAMAGE_MULT
            messages.append(f"🌑 Dread weakens {attacker.name}'s attack by 25%!")
        return raw_damage, messages, False

    @staticmethod
    def effective_armor(defender, armor=None):
        armor = _dec(getattr(defender, "armor", 0) if armor is None else armor)
        if getattr(defender, "element_proc_drowned", False):
            return Decimal("0")
        stacks = int(getattr(defender, "element_proc_erosion", 0) or 0)
        if stacks > 0:
            armor *= Decimal("1") - EROSION_ARMOR_PCT * min(stacks, EROSION_MAX_STACKS)
        return armor

    @staticmethod
    def consume_dodge(defender):
        charges = int(getattr(defender, "element_proc_dodge", 0) or 0)
        if charges <= 0:
            return None
        defender.element_proc_dodge = charges - 1
        return f"💨 {defender.name} rides the wind and dodges the attack!"

    @staticmethod
    def consume_burn(defender):
        hits = int(getattr(defender, "element_proc_burn_hits", 0) or 0)
        if hits <= 0:
            return Decimal("0"), None
        defender.element_proc_burn_hits = hits - 1
        tick = _dec(getattr(defender, "element_proc_burn_tick", 0))
        if tick <= 0:
            return Decimal("0"), None
        return tick, f"🔥 {defender.name} burns for **{_fmt(tick)} HP**!"

    # ------------------------------------------------------------------- hit
    def resolve_hit(self, battle, attacker, defender, raw_damage, final_damage, attack_element, defense_element):
        """Apply defender states and roll the attacker's proc after armor.

        Returns ``(final_damage, messages, dodged)``.
        """
        final_damage = _dec(final_damage)
        raw_damage = _dec(raw_damage)
        messages = []

        if final_damage > 0:
            dodge_message = self.consume_dodge(defender)
            if dodge_message:
                return Decimal("0"), [dodge_message], True

        burn, burn_message = self.consume_burn(defender)
        if burn > 0:
            final_damage += burn
            messages.append(burn_message)

        proc = self.roll(battle, attacker, defender, attack_element, defense_element)
        if proc:
            element, tier = proc
            final_damage, proc_messages = self.apply_proc(
                battle, attacker, defender, element, tier, raw_damage, final_damage
            )
            messages.extend(proc_messages)
        return final_damage, messages, False

    def apply_proc(self, battle, attacker, defender, element, tier, raw_damage, final_damage):
        name = PROC_NAMES[element][0 if tier == COMMON else 1]
        emoji = PROC_EMOJI[element]
        if tier == MYTHIC:
            header = f"{emoji}✨ **{name.upper()}** ✨"
        else:
            header = f"{emoji} **{name}**"
        handler = getattr(self, f"_{tier}_{element.lower()}")
        final_damage, detail = handler(battle, attacker, defender, raw_damage, final_damage)
        return final_damage, [f"{header} — {detail}"]

    # Common procs ------------------------------------------------------------
    def _common_light(self, battle, attacker, defender, raw_damage, final_damage):
        missing = max(Decimal("0"), _dec(defender.max_hp) - _dec(defender.hp))
        bonus = min(missing * JUDGMENT_MISSING_HP_PCT, _dec(getattr(attacker, "damage", 0)))
        return final_damage + bonus, f"{defender.name} is judged for **{_fmt(bonus)}** true damage!"

    def _common_dark(self, battle, attacker, defender, raw_damage, final_damage):
        defender.element_proc_dread = 1
        return final_damage, f"{defender.name}'s next attack will deal 25% less."

    def _common_corrupted(self, battle, attacker, defender, raw_damage, final_damage):
        defender.element_proc_hex = max(int(getattr(defender, "element_proc_hex", 0) or 0), HEX_ATTACKS)
        return final_damage, f"{defender.name}'s next {HEX_ATTACKS} attacks lose their element."

    def _common_fire(self, battle, attacker, defender, raw_damage, final_damage):
        tick = min(
            _dec(defender.max_hp) * IGNITE_MAX_HP_PCT,
            _dec(getattr(attacker, "damage", 0)) * IGNITE_DAMAGE_CAP_PCT,
        )
        defender.element_proc_burn_hits = IGNITE_HITS
        defender.element_proc_burn_tick = tick
        return final_damage, f"{defender.name} is set ablaze!"

    def _common_nature(self, battle, attacker, defender, raw_damage, final_damage):
        heal = _dec(attacker.max_hp) * OVERGROWTH_HEAL_PCT
        attacker.heal(heal)
        return final_damage, f"{attacker.name} regrows **{_fmt(heal)} HP**."

    def _common_water(self, battle, attacker, defender, raw_damage, final_damage):
        stacks = min(EROSION_MAX_STACKS, int(getattr(defender, "element_proc_erosion", 0) or 0) + 1)
        defender.element_proc_erosion = stacks
        return final_damage, f"{defender.name}'s armor erodes (-{stacks * 5}%)."

    def _common_earth(self, battle, attacker, defender, raw_damage, final_damage):
        bonus = final_damage * TREMOR_PCT
        return final_damage + bonus, f"the ground shakes and hits again for **{_fmt(bonus)}**!"

    def _common_electric(self, battle, attacker, defender, raw_damage, final_damage):
        bonus = raw_damage * ARC_PCT
        return final_damage + bonus, f"an arc jumps through the armor for **{_fmt(bonus)}**!"

    def _common_wind(self, battle, attacker, defender, raw_damage, final_damage):
        attacker.element_proc_dodge = max(int(getattr(attacker, "element_proc_dodge", 0) or 0), 1)
        return final_damage, f"{attacker.name} will dodge the next attack."

    # Mythic procs ------------------------------------------------------------
    def _mythic_light(self, battle, attacker, defender, raw_damage, final_damage):
        return max(final_damage, POWER_WORD_DAMAGE), f"**{defender.name}** is spoken out of existence!"

    def _mythic_dark(self, battle, attacker, defender, raw_damage, final_damage):
        defender.element_proc_eclipse = ECLIPSE_TURNS
        return final_damage, f"darkness swallows {defender.name}; they lose their next {ECLIPSE_TURNS} turns!"

    def _mythic_corrupted(self, battle, attacker, defender, raw_damage, final_damage):
        defender.element_proc_unmade = True
        return final_damage, f"{defender.name}'s element is unmade for the rest of the fight!"

    def _mythic_fire(self, battle, attacker, defender, raw_damage, final_damage):
        bonus = _dec(defender.max_hp) * PYRE_MAX_HP_PCT
        return final_damage + bonus, f"{defender.name} is engulfed for **{_fmt(bonus)}** true damage!"

    def _mythic_nature(self, battle, attacker, defender, raw_damage, final_damage):
        attacker.element_proc_bloom_used = True
        attacker.heal(attacker.max_hp)
        return final_damage, f"{attacker.name} blooms back to full health!"

    def _mythic_water(self, battle, attacker, defender, raw_damage, final_damage):
        defender.element_proc_drowned = True
        return final_damage, f"{defender.name}'s armor is washed away for the rest of the fight!"

    def _mythic_earth(self, battle, attacker, defender, raw_damage, final_damage):
        final_damage *= 2
        hit = 0
        enemy_team = None
        getter = getattr(battle, "get_enemy_team_for_combatant", None)
        if callable(getter):
            enemy_team = getter(attacker)
        for enemy in list(getattr(enemy_team, "combatants", []) or []):
            if enemy is defender or not enemy.is_alive() or getattr(enemy, "is_boss", False):
                continue
            if not self.can_be_targeted(enemy, battle):
                continue
            enemy.take_damage(final_damage)
            hit += 1
        splash = f" and {hit} other enem{'y' if hit == 1 else 'ies'}" if hit else ""
        return final_damage, f"the earth splits beneath {defender.name}{splash} for **{_fmt(final_damage)}**!"

    def _mythic_electric(self, battle, attacker, defender, raw_damage, final_damage):
        return final_damage + raw_damage, f"{attacker.name} overloads and strikes again for **{_fmt(raw_damage)}**!"

    def _mythic_wind(self, battle, attacker, defender, raw_damage, final_damage):
        attacker.element_proc_dodge = max(int(getattr(attacker, "element_proc_dodge", 0) or 0), TEMPEST_DODGES)
        return final_damage, f"{attacker.name} becomes the storm and will dodge the next {TEMPEST_DODGES} attacks!"

    # ---------------------------------------------------------------- storage
    @staticmethod
    async def ensure_table(conn):
        await conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {OPT_IN_TABLE} (
                user_id BIGINT PRIMARY KEY,
                enabled BOOLEAN NOT NULL DEFAULT FALSE,
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
            """
        )

    @staticmethod
    async def is_opted_in(conn, user_id):
        table_exists = await conn.fetchval(f"SELECT to_regclass('public.{OPT_IN_TABLE}') IS NOT NULL;")
        if not table_exists:
            return False
        return bool(
            await conn.fetchval(f"SELECT enabled FROM {OPT_IN_TABLE} WHERE user_id = $1;", user_id)
        )

    @staticmethod
    async def set_opted_in(conn, user_id, enabled):
        await conn.execute(
            f"""
            INSERT INTO {OPT_IN_TABLE} (user_id, enabled, updated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (user_id) DO UPDATE SET enabled = EXCLUDED.enabled, updated_at = NOW();
            """,
            user_id,
            bool(enabled),
        )
