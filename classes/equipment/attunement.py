"""Attunement uses the same deeds, and the same point values, as a soulbound weapon.

A finished adventure is 10, a battle-tower floor is 15, a raid victory is 20,
and an ice-dragon kill is 25. A strong turn-based victory is 15. The piece is
fully attuned at 2,500, the same total as the soulbound rank named Attuned.
One award per finished activity, so stalling a fight adds nothing.
"""
from __future__ import annotations

from decimal import Decimal

# Matches classes.endgame.soulbound_xp_for_level(5).
ATTUNEMENT_CAP = 2500
XP_ADVENTURE = 10
XP_TOWER_FLOOR = 15
XP_BATTLE = 15
XP_RAID_WIN = 20
XP_DRAGON_KILL = 25
BASE_REFINEMENT_CAP = 5
ATTUNED_REFINEMENT_CAP = 7
TRIVIAL_HP_RATIO = Decimal("0.50")


def refinement_cap(attunement: int) -> int:
    """Full attunement opens refinement +6 and +7. Before that the cap stays +5."""
    if int(attunement or 0) >= ATTUNEMENT_CAP:
        return ATTUNED_REFINEMENT_CAP
    return BASE_REFINEMENT_CAP


def victory_award(current, foe_hp=None, wearer_hp=None, amount=XP_BATTLE) -> dict:
    """Add one activity's points. A weak foe grants nothing when health is passed in."""
    current = max(0, int(current or 0))
    amount = max(0, int(amount or 0))
    if current >= ATTUNEMENT_CAP or amount <= 0:
        return {"gain": 0, "level": current, "reason": "complete", "binds": False}
    if foe_hp is not None or wearer_hp is not None:
        foe_hp = Decimal(str(foe_hp or 0))
        wearer_hp = Decimal(str(wearer_hp or 0))
        if wearer_hp <= 0 or foe_hp < wearer_hp * TRIVIAL_HP_RATIO:
            return {"gain": 0, "level": current, "reason": "trivial", "binds": False}
    gain = min(amount, ATTUNEMENT_CAP - current)
    return {
        "gain": gain,
        "level": current + gain,
        "reason": "victory",
        "binds": current == 0,
    }


def crossed_milestone(decision: dict) -> bool:
    """True on each 500-point mark and when the piece finishes."""
    level = int(decision.get("level") or 0)
    previous = level - int(decision.get("gain") or 0)
    if decision.get("gain", 0) <= 0:
        return False
    if level >= ATTUNEMENT_CAP and previous < ATTUNEMENT_CAP:
        return True
    return previous // 500 < level // 500


def attunement_message(decision: dict) -> str:
    name = decision.get("name") or "Your armor"
    level = int(decision["level"])
    text = f"**{name}** attunes to {level}/{ATTUNEMENT_CAP}."
    if decision.get("newly_bound"):
        text += " The first attunement binds it."
    if level >= ATTUNEMENT_CAP:
        text += " Tempering can now reach +7."
    return text
