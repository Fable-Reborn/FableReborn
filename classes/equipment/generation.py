"""Crate rolls for chest armor and armory materials.

The roller takes an explicit random stream so it does not consume the
global random sequence used by weapon and shield generation.
"""
from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field

from classes.equipment.definitions import (
    ARCHETYPES,
    ELIGIBLE_CRATE_RARITIES,
    OPEN_SLOTS,
    FULLY_ROLLED_CHANCE,
    GEAR_CHANCE,
    MATERIAL_LINES,
    MATERIAL_ORDER,
    MATERIALS,
    MODIFIER_LINES,
    QUALITY_MODE,
    material_dot,
    quality_band,
)


@dataclass(frozen=True)
class RolledPiece:
    rarity: str
    archetype: str
    quality: int
    fully_rolled: bool
    slot: str = "chest"
    modifier_ids: tuple[str, ...] = ()


@dataclass
class CrateRoll:
    rarity: str
    piece: RolledPiece | None = None
    materials: dict[str, int] = field(default_factory=dict)


def roll_quality(rng: random.Random, rarity: str, *, fully_rolled: bool = False) -> int:
    if fully_rolled:
        value = rng.triangular(70, 100, 88)
    else:
        value = rng.triangular(1, 100, QUALITY_MODE[rarity])
    return min(100, max(1, int(round(value))))


def roll_natural_modifiers(rng: random.Random, archetype: str, *, fully_rolled: bool) -> tuple[str, ...]:
    """Fully rolled pieces take both allowed affixes. Ordinary pieces sometimes take one."""
    pool = MODIFIER_LINES[archetype]
    if fully_rolled:
        if len(pool) <= 2:
            return tuple(pool)
        return tuple(rng.sample(pool, 2))
    if rng.random() < 0.25:
        return (rng.choice(pool),)
    return ()


def roll_crate(rarity: str, rng: random.Random) -> CrateRoll | None:
    """Return one crate's armory reward, or None when the rarity is excluded."""
    rarity = str(rarity).lower()
    if rarity not in ELIGIBLE_CRATE_RARITIES:
        return None

    line = rng.choice(ARCHETYPES)
    fully_rolled = rarity == "legendary" and rng.random() < FULLY_ROLLED_CHANCE
    piece = None
    if fully_rolled or rng.random() < GEAR_CHANCE[rarity]:
        piece = RolledPiece(
            rarity=rarity,
            archetype=line,
            slot=rng.choice(OPEN_SLOTS),
            quality=roll_quality(rng, rarity, fully_rolled=fully_rolled),
            fully_rolled=fully_rolled,
            modifier_ids=roll_natural_modifiers(rng, line, fully_rolled=fully_rolled),
        )
    return CrateRoll(
        rarity=rarity,
        piece=piece,
        materials=_roll_materials(rarity, rng, line),
    )


def _roll_materials(rarity: str, rng: random.Random, line: str) -> dict[str, int]:
    rough, worked, relic = MATERIAL_LINES[line]
    if rarity == "common":
        return {rough: rng.randint(1, 2)}
    if rarity == "uncommon":
        materials = {rough: rng.randint(2, 3)}
        if rng.random() < 0.10:
            materials[worked] = 1
        return materials
    if rarity == "rare":
        materials = {rough: rng.randint(2, 3)}
        if rng.random() < 0.50:
            materials[worked] = 1
        if rng.random() < 0.03:
            materials[relic] = 1
        return materials
    if rarity == "magic":
        materials = {rough: 3, worked: rng.randint(1, 2)}
        if rng.random() < 0.35:
            materials[relic] = 1
        return materials
    materials = {rough: 4, worked: 2, relic: 1}
    if rng.random() < 0.30:
        materials[relic] = 2
    return materials


def summarize_rewards(rewards: list[dict]) -> str:
    """One compact line for a bulk opening."""
    if not rewards:
        return ""
    pieces = [reward["item"] for reward in rewards if reward.get("item")]
    discoveries = sum(1 for item in pieces if item.get("fully_rolled"))
    totals: dict[str, int] = {}
    for reward in rewards:
        for material_id, amount in reward.get("materials", {}).items():
            totals[material_id] = totals.get(material_id, 0) + int(amount)
    parts = [f"{len(pieces)} piece(s)"]
    if discoveries:
        label = "bound discovery" if discoveries == 1 else "bound discoveries"
        parts.append(f"including {discoveries} {label}")
    lines = ["Armory: " + ", ".join(parts)]
    if pieces:
        qualities = [int(item["quality"]) for item in pieces]
        counts = Counter(qualities)
        kinds = Counter(str(item.get("archetype") or "unknown").title() for item in pieces)
        common = "\n".join(f"- {stat} (x{count})" for stat, count in counts.most_common(5))
        best = "\n".join(f"- {stat}" for stat in sorted(counts, reverse=True)[:5])
        kinds_text = "\n".join(f"- {name} (x{count})" for name, count in kinds.most_common())
        lines.append(
            f"Most common stats:\n```\n{common}\n```\n"
            f"Best stats:\n```\n{best}\n```\n"
            f"Types:\n```\n{kinds_text}\n```"
        )
    material_text = ", ".join(
        f"{material_dot(material_id)} {MATERIALS[material_id]} x{totals[material_id]}"
        for material_id in MATERIAL_ORDER
        if totals.get(material_id)
    )
    if material_text:
        lines.append(f"Materials: {material_text}")
    return "\n".join(lines)


def describe_reward(reward: dict) -> str:
    item = reward.get("item")
    lines = []
    if item:
        band = quality_band(int(item["quality"]))
        if item.get("fully_rolled"):
            lines.append(
                f"**Bound discovery:** {item['name']} · {band} {item['quality']} · "
                f"{item['archetype'].title()}"
            )
        else:
            lines.append(
                f"**{item['name']}** · {band} {item['quality']} · "
                f"{item['archetype'].title()} · tradable"
            )
    material_text = ", ".join(
        f"{material_dot(material_id)} {MATERIALS[material_id]} x{int(amount)}"
        for material_id, amount in reward.get("materials", {}).items()
        if int(amount) > 0 and material_id in MATERIALS
    )
    if material_text:
        lines.append(material_text)
    return "\n".join(lines)


def simulate(rarity: str, count: int, rng: random.Random | None = None) -> dict:
    rng = rng or random.Random()
    pieces = 0
    discoveries = 0
    bound = 0
    qualities = []
    archetypes = {name: 0 for name in ARCHETYPES}
    materials = {name: 0 for name in MATERIAL_ORDER}
    for _ in range(count):
        roll = roll_crate(rarity, rng)
        if roll is None:
            continue
        for material_id, amount in roll.materials.items():
            materials[material_id] += amount
        if roll.piece is None:
            continue
        pieces += 1
        qualities.append(roll.piece.quality)
        archetypes[roll.piece.archetype] += 1
        if roll.piece.fully_rolled:
            discoveries += 1
            bound += 1
    return {
        "opened": count,
        "pieces": pieces,
        "discoveries": discoveries,
        "bound": bound,
        "quality_mean": (sum(qualities) / len(qualities)) if qualities else 0,
        "masterwork": sum(1 for quality in qualities if quality >= 95),
        "archetypes": archetypes,
        "materials": materials,
    }
