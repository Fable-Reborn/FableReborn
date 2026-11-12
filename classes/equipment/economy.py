"""Craft prices, salvage yields, and the tradable check.

Salvage is always a loss against crafting the same piece. These prices are
the Phase 3 baseline for the development bot.
"""
from __future__ import annotations

from decimal import Decimal

from classes.equipment.definitions import (
    ARCHETYPES,
    DRAGON_MATERIAL_TIERS,
    MATERIAL_LINES,
    INSCRIBE_COST,
    REFINE_QUALITY_BANDS,
    TEMPER_STAR_CHANCE,
    TEMPER_STAR_GOLD,
    TEMPER_STAR_PITY,
    TRADE_RATIO,
    OPEN_SLOTS,
    MATERIALS,
    MAX_BREAKTHROUGH_BYPASS,
    MAX_BREAKTHROUGH_CHANCE,
    MAX_PENETRATION,
    MODIFIERS,
    RARITIES,
    material_dot,
)

# Amounts are in tier order: rough, worked, relic. Zero means that tier is unused.


def recipe_key(archetype: str, rarity: str, slot: str = "chest") -> str:
    return f"{slot}:{str(archetype).lower()}:{str(rarity).lower()}"


# Common pattern of every open slot. Stronger pieces are learned by finding one.
STARTER_RECIPES = tuple(
    recipe_key(archetype, "common", slot)
    for slot in OPEN_SLOTS
    for archetype in ARCHETYPES
)


def parse_recipe_key(key: str) -> tuple[str, str, str]:
    slot, archetype, rarity = str(key).split(":")
    return slot, archetype, rarity


def all_recipe_keys() -> list[str]:
    """Every armor pattern that can exist, for the GM interface preview."""
    return known_recipe_keys(
        {
            recipe_key(archetype, rarity, slot)
            for slot in OPEN_SLOTS
            for archetype in ARCHETYPES
            for rarity in RARITIES
        }
    )


def preview_balances() -> dict[str, int]:
    """Sample wallet used by the GM preview.

    Each line has 20 rough, 4 worked, and no relic. That makes common ready,
    uncommon and rare close, and magic and legendary short.
    """
    balances = {}
    for rough, worked, relic in MATERIAL_LINES.values():
        balances[rough] = 20
        balances[worked] = 4
        balances[relic] = 0
    return balances


def known_recipe_keys(discovered: set[str] | None = None) -> list[str]:
    """Starter patterns plus anything the character has found."""
    keys = set(STARTER_RECIPES)
    keys.update(discovered or ())
    slot_order = {name: index for index, name in enumerate(OPEN_SLOTS)}

    def sort_key(key: str):
        slot, archetype, rarity = parse_recipe_key(key)
        return (archetype, slot_order.get(slot, 99), RARITIES.index(rarity))

    return sorted(keys, key=sort_key)


def recipe_progress(cost: dict[str, int], balances: dict[str, int]) -> dict:
    """Compare one recipe with a material wallet.

    `state` is ready, close, or short. Close means two or fewer missing stacks,
    matching the amulet crafting screen.
    """
    lines = []
    missing = []
    for material_id, needed in cost.items():
        owned = int(balances.get(material_id, 0))
        label = f"{material_dot(material_id)} {MATERIALS[material_id]}"
        if owned >= needed:
            lines.append(f"✅ {needed}x {label}")
        else:
            lines.append(f"❌ {needed}x {label} *({owned} owned)*")
            missing.append(f"{needed - owned}x {MATERIALS[material_id]}")
    if not missing:
        state = "ready"
    elif len(missing) <= 2:
        state = "close"
    else:
        state = "short"
    return {"state": state, "lines": lines, "missing": missing}


# Materials for each temper star, in rough, worked, relic amounts. Every
# attempt pays this whether it succeeds or not.
TEMPER_STAR_COSTS = {
    1: (8, 0, 0),
    2: (12, 2, 0),
    3: (16, 4, 0),
    4: (20, 8, 1),
    5: (24, 12, 3),
    6: (28, 16, 5),
    7: (32, 20, 8),
}


def _line_cost(archetype: str, amounts) -> dict[str, int]:
    archetype = str(archetype).lower()
    if archetype not in ARCHETYPES:
        raise ValueError(f"unsupported equipment archetype: {archetype}")
    cost = {}
    for material_id, amount in zip(MATERIAL_LINES[archetype], amounts):
        if amount > 0:
            cost[material_id] = int(amount)
    return cost


def temper_cost(archetype: str, next_star: int) -> dict[str, int]:
    next_star = int(next_star)
    if next_star not in TEMPER_STAR_COSTS:
        raise ValueError(f"temper +{next_star} is not available")
    return _line_cost(archetype, TEMPER_STAR_COSTS[next_star])


def temper_step(archetype: str, next_star: int) -> dict:
    """Materials, gold, success chance, and pity for one temper attempt."""
    next_star = int(next_star)
    return {
        "cost": temper_cost(archetype, next_star),
        "gold": int(TEMPER_STAR_GOLD[next_star]),
        "chance": float(TEMPER_STAR_CHANCE[next_star]),
        "pity": int(TEMPER_STAR_PITY[next_star]),
    }


def refine_step(archetype: str, quality: int) -> dict | None:
    """One quality refine attempt, or None at quality 100."""
    quality = int(quality)
    if quality >= 100:
        return None
    for ceiling, rough, worked, relic, gold, chance, pity in REFINE_QUALITY_BANDS:
        if quality <= ceiling:
            return {
                "cost": _line_cost(archetype, (rough, worked, relic)),
                "gold": int(gold),
                "chance": float(chance),
                "pity": int(pity),
            }
    return None


def inscribe_step(archetype: str) -> dict:
    rough, worked, relic, gold, chance, pity = INSCRIBE_COST
    return {
        "cost": _line_cost(archetype, (rough, worked, relic)),
        "gold": int(gold),
        "chance": float(chance),
        "pity": int(pity),
    }


def trade_result(material_id: str, target_line: str, amount: int) -> tuple[str, int, int] | None:
    """Garron's trade: (material received, amount received, amount spent) at the fixed ratio."""
    target_line = str(target_line).lower()
    if target_line not in ARCHETYPES or material_id not in MATERIALS:
        return None
    source_line = next(line for line, ids in MATERIAL_LINES.items() if material_id in ids)
    if source_line == target_line:
        return None
    tier = MATERIAL_LINES[source_line].index(material_id)
    received = int(amount) // TRADE_RATIO
    if received <= 0:
        return None
    return MATERIAL_LINES[target_line][tier], received, received * TRADE_RATIO


def modifier_adjustments(defense_value, modifier_ids) -> tuple[Decimal, Decimal, int]:
    """Extra weapon fraction, extra armor, and flat health from one piece's affixes."""
    weapon_pct = Decimal("0")
    armor = Decimal("0")
    health = 0
    defense = Decimal(str(defense_value or 0))
    for modifier_id in modifier_ids:
        spec = MODIFIERS.get(str(modifier_id))
        if not spec:
            continue
        weapon_pct += Decimal(str(spec.get("weapon_pct") or 0))
        armor += defense * Decimal(str(spec.get("armor_pct") or 0))
        health += int(spec.get("health") or 0)
    return weapon_pct, armor, health


def offensive_properties(modifier_ids) -> tuple[Decimal, Decimal, Decimal]:
    """Capped penetration, breakthrough chance, and one-hit bypass.

    A repeated affix on the same piece counts once. Later slots can add more,
    and the totals still stop at the Phase 5 caps.
    """
    penetration = Decimal("0")
    chance = Decimal("0")
    bypass = Decimal("0")
    seen = set()
    for modifier_id in modifier_ids:
        modifier_id = str(modifier_id)
        if modifier_id in seen:
            continue
        seen.add(modifier_id)
        spec = MODIFIERS.get(modifier_id)
        if not spec:
            continue
        penetration += Decimal(str(spec.get("penetration") or 0))
        chance += Decimal(str(spec.get("breakthrough_chance") or 0))
        bypass = max(bypass, Decimal(str(spec.get("breakthrough_bypass") or 0)))
    return (
        min(MAX_PENETRATION, penetration),
        min(MAX_BREAKTHROUGH_CHANCE, chance),
        min(MAX_BREAKTHROUGH_BYPASS, bypass),
    )


def dragon_tier(level: int) -> tuple:
    for tier in DRAGON_MATERIAL_TIERS:
        if tier[0] is None or int(level or 1) <= tier[0]:
            return tier
    return DRAGON_MATERIAL_TIERS[-1]


def roll_dragon_materials(level: int, archetype: str, rng) -> dict[str, int]:
    """Smithing goods for one party dragon kill at this dragon level."""
    _ceiling, _stage, low, high, worked_chance, worked_amount, relic_chance = dragon_tier(level)
    rough, worked, relic = MATERIAL_LINES[str(archetype).lower()]
    materials = {rough: rng.randint(low, high)}
    if worked_amount and rng.random() < worked_chance:
        materials[worked] = int(worked_amount)
    if relic_chance and rng.random() < relic_chance:
        materials[relic] = 1
    return materials


CRAFT_COSTS = {
    "common": (12, 0, 0),
    "uncommon": (24, 0, 0),
    "rare": (20, 8, 0),
    "magic": (30, 16, 2),
    "legendary": (40, 24, 10),
}


def is_tradable(item) -> bool:
    """Equipping does not bind. Enhancement, a bound flag, or a discovery does."""
    if item.get("bound") or item.get("fully_rolled"):
        return False
    if int(item.get("refinement") or 0) > 0:
        return False
    if str(item.get("modification_state") or "pristine") != "pristine":
        return False
    return True


def craft_cost(rarity: str, archetype: str) -> dict[str, int]:
    rarity = str(rarity).lower()
    archetype = str(archetype).lower()
    if rarity not in RARITIES:
        raise ValueError(f"unsupported equipment rarity: {rarity}")
    if archetype not in ARCHETYPES:
        raise ValueError(f"unsupported equipment archetype: {archetype}")
    rough, worked, relic = MATERIAL_LINES[archetype]
    amounts = CRAFT_COSTS[rarity]
    cost = {}
    for material_id, amount in zip((rough, worked, relic), amounts):
        if amount > 0:
            cost[material_id] = int(amount)
    return cost


def salvage_yield(rarity: str, archetype: str, quality: int) -> dict[str, int]:
    """Return materials for breaking a piece down.

    The rate grows a little with quality and stops at 40 percent. Every
    returned stack is smaller than the craft cost of that same material.
    """
    quality = min(100, max(1, int(quality)))
    rate = min(0.40, 0.25 + (quality // 10) * 0.01)
    yielded = {}
    for material_id, amount in craft_cost(rarity, archetype).items():
        gained = int(amount * rate)
        if gained >= amount:
            gained = amount - 1
        if gained > 0:
            yielded[material_id] = gained
    return yielded
