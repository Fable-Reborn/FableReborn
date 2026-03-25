from __future__ import annotations

from typing import Any

from .content import (
    CardDef,
    PotionDef,
    RelicDef,
    apply_status,
    attack,
    attack_all,
    block,
    create_cards,
    draw,
    gain_energy,
    x_attack,
)


def summon_osty(value: int) -> dict[str, Any]:
    return {"type": "summon_osty", "value": value}


def summon_osty_next_turn(value: int) -> dict[str, Any]:
    return {"type": "summon_osty_next_turn", "value": value}


def osty_attack(value: int, *, hits: int = 1) -> dict[str, Any]:
    return {"type": "osty_attack", "value": value, "hits": hits}


def osty_attack_random(value: int) -> dict[str, Any]:
    return {"type": "osty_attack_random", "value": value}


def osty_attack_all(value: int) -> dict[str, Any]:
    return {"type": "osty_attack_all", "value": value}


def unleash_attack(value: int) -> dict[str, Any]:
    return {"type": "unleash_attack", "value": value}


def blight_strike(value: int) -> dict[str, Any]:
    return {"type": "blight_strike", "value": value}


def debilitate(value: int, turns: int) -> dict[str, Any]:
    return {"type": "debilitate", "value": value, "turns": turns}


def return_discard_to_hand(count: int = 1) -> dict[str, Any]:
    return {"type": "return_discard_to_hand", "count": count}


def add_retain_to_hand(count: int = 1) -> dict[str, Any]:
    return {"type": "add_retain_to_hand", "count": count}


def add_ethereal_to_hand(count: int = 1) -> dict[str, Any]:
    return {"type": "add_ethereal_to_hand", "count": count}


def exhaust_from_draw(count: int = 1) -> dict[str, Any]:
    return {"type": "exhaust_from_draw", "count": count}


def lose_enemy_hp(value: int) -> dict[str, Any]:
    return {"type": "lose_enemy_hp", "value": value}


def dirge(value: int, *, upgraded_souls: bool = False) -> dict[str, Any]:
    return {"type": "dirge", "value": value, "upgraded_souls": upgraded_souls}


def if_first_play_draw(value: int) -> dict[str, Any]:
    return {"type": "if_first_play_draw", "value": value}


def no_escape(value: int, *, step: int = 5, divisor: int = 10) -> dict[str, Any]:
    return {"type": "no_escape", "value": value, "step": step, "divisor": divisor}


def forbidden_grimoire() -> dict[str, Any]:
    return {"type": "forbidden_grimoire"}


def protector_attack(value: int) -> dict[str, Any]:
    return {"type": "protector_attack", "value": value}


def pull_from_below(value: int) -> dict[str, Any]:
    return {"type": "pull_from_below", "value": value}


def rattle(value: int) -> dict[str, Any]:
    return {"type": "rattle", "value": value}


def hang_attack(value: int) -> dict[str, Any]:
    return {"type": "hang_attack", "value": value}


def misery(value: int) -> dict[str, Any]:
    return {"type": "misery", "value": value}


def sic_em(value: int, summon: int) -> dict[str, Any]:
    return {"type": "sic_em", "value": value, "summon": summon}


def severance(value: int) -> dict[str, Any]:
    return {"type": "severance", "value": value}


def osty_heal(value: int) -> dict[str, Any]:
    return {"type": "osty_heal", "value": value}


def call_of_the_void() -> dict[str, Any]:
    return {"type": "call_of_the_void"}


def exhaust_hand_threshold_intangible(threshold: int, intangible: int) -> dict[str, Any]:
    return {
        "type": "exhaust_hand_threshold_intangible",
        "threshold": threshold,
        "intangible": intangible,
    }


def end_of_days(value: int) -> dict[str, Any]:
    return {"type": "end_of_days", "value": value}


def transform_draw_to_soul(*, upgraded: bool = False) -> dict[str, Any]:
    return {"type": "transform_draw_to_soul", "upgraded": upgraded}


def soul_storm(value: int, *, per_soul: int) -> dict[str, Any]:
    return {"type": "soul_storm", "value": value, "per_soul": per_soul}


def squeeze(value: int, *, per_attack: int) -> dict[str, Any]:
    return {"type": "squeeze", "value": value, "per_attack": per_attack}


def scythe_attack(value: int, *, growth: int) -> dict[str, Any]:
    return {"type": "scythe_attack", "value": value, "growth": growth}


def transfigure(extra_cost: int = 1) -> dict[str, Any]:
    return {"type": "transfigure", "extra_cost": extra_cost}


def create_self_copy(location: str) -> dict[str, Any]:
    return {"type": "create_self_copy", "location": location}


def upgrade_random_discard(count: int) -> dict[str, Any]:
    return {"type": "upgrade_random_discard", "count": count}


NECROBINDER_CARD_LIBRARY: dict[str, CardDef] = {
    "bodyguard": CardDef(
        key="bodyguard",
        name="Bodyguard",
        card_type="skill",
        rarity="starter",
        cost=1,
        target="self",
        description="Summon 5.",
        upgraded_description="Summon 7.",
        actions=[summon_osty(5)],
        upgraded_actions=[summon_osty(7)],
    ),
    "unleash": CardDef(
        key="unleash",
        name="Unleash",
        card_type="attack",
        rarity="starter",
        cost=1,
        target="enemy",
        description="Osty deals 6 damage. Deal additional damage equal to Osty's current HP.",
        upgraded_description="Osty deals 9 damage. Deal additional damage equal to Osty's current HP.",
        actions=[unleash_attack(6)],
        upgraded_actions=[unleash_attack(9)],
    ),
    "soul": CardDef(
        key="soul",
        name="Soul",
        card_type="skill",
        rarity="special",
        cost=0,
        target="self",
        description="Draw 2 cards. Exhaust.",
        upgraded_description="Draw 3 cards. Exhaust.",
        actions=[draw(2)],
        upgraded_actions=[draw(3)],
        exhaust=True,
    ),
    "sweeping_gaze": CardDef(
        key="sweeping_gaze",
        name="Sweeping Gaze",
        card_type="attack",
        rarity="special",
        cost=0,
        target="self",
        description="Ethereal. Osty deals 10 damage to a random enemy. Exhaust.",
        upgraded_description="Ethereal. Osty deals 15 damage to a random enemy. Exhaust.",
        actions=[osty_attack_random(10)],
        upgraded_actions=[osty_attack_random(15)],
        exhaust=True,
        ethereal=True,
    ),
    "afterlife": CardDef(
        key="afterlife",
        name="Afterlife",
        card_type="skill",
        rarity="common",
        cost=1,
        target="self",
        description="Summon 6. Exhaust.",
        upgraded_description="Summon 9. Exhaust.",
        actions=[summon_osty(6)],
        upgraded_actions=[summon_osty(9)],
        exhaust=True,
    ),
    "blight_strike": CardDef(
        key="blight_strike",
        name="Blight Strike",
        card_type="attack",
        rarity="common",
        cost=1,
        target="enemy",
        description="Deal 8 damage. Apply Doom equal to damage dealt.",
        upgraded_description="Deal 10 damage. Apply Doom equal to damage dealt.",
        actions=[blight_strike(8)],
        upgraded_actions=[blight_strike(10)],
    ),
    "defile": CardDef(
        key="defile",
        name="Defile",
        card_type="attack",
        rarity="common",
        cost=1,
        target="enemy",
        description="Ethereal. Deal 13 damage.",
        upgraded_description="Ethereal. Deal 17 damage.",
        actions=[attack(13)],
        upgraded_actions=[attack(17)],
        ethereal=True,
    ),
    "fear": CardDef(
        key="fear",
        name="Fear",
        card_type="attack",
        rarity="common",
        cost=1,
        target="enemy",
        description="Ethereal. Deal 7 damage. Apply 1 Vulnerable.",
        upgraded_description="Ethereal. Deal 8 damage. Apply 2 Vulnerable.",
        actions=[attack(7), apply_status("enemy", "vulnerable", 1)],
        upgraded_actions=[attack(8), apply_status("enemy", "vulnerable", 2)],
        ethereal=True,
    ),
    "flatten": CardDef(
        key="flatten",
        name="Flatten",
        card_type="attack",
        rarity="common",
        cost=1,
        target="enemy",
        description="Osty deals 12 damage. Costs 0 if Osty attacked this turn.",
        upgraded_description="Osty deals 16 damage. Costs 0 if Osty attacked this turn.",
        actions=[osty_attack(12)],
        upgraded_actions=[osty_attack(16)],
    ),
    "defy": CardDef(
        key="defy",
        name="Defy",
        card_type="skill",
        rarity="common",
        cost=1,
        target="enemy",
        description="Ethereal. Gain 6 Block. Apply 1 Weak.",
        upgraded_description="Ethereal. Gain 8 Block. Apply 2 Weak.",
        actions=[block(6), apply_status("enemy", "weak", 1)],
        upgraded_actions=[block(8), apply_status("enemy", "weak", 2)],
        ethereal=True,
    ),
    "drain_power": CardDef(
        key="drain_power",
        name="Drain Power",
        card_type="attack",
        rarity="common",
        cost=1,
        target="enemy",
        description="Deal 10 damage. Upgrade 2 random cards in your Discard Pile.",
        upgraded_description="Deal 12 damage. Upgrade 3 random cards in your Discard Pile.",
        actions=[attack(10), upgrade_random_discard(2)],
        upgraded_actions=[attack(12), upgrade_random_discard(3)],
    ),
    "grave_warden": CardDef(
        key="grave_warden",
        name="Grave Warden",
        card_type="skill",
        rarity="common",
        cost=1,
        target="self",
        description="Gain 8 Block. Add a Soul into your Draw Pile.",
        upgraded_description="Gain 10 Block. Add a Soul+ into your Draw Pile.",
        actions=[block(8), create_cards("draw", "soul")],
        upgraded_actions=[block(10), create_cards("draw", "soul", upgraded=True)],
    ),
    "graveblast": CardDef(
        key="graveblast",
        name="Graveblast",
        card_type="attack",
        rarity="common",
        cost=1,
        target="enemy",
        description="Deal 4 damage. Put a card from your Discard Pile into your Hand. Exhaust.",
        upgraded_description="Deal 6 damage. Put a card from your Discard Pile into your Hand.",
        actions=[attack(4), return_discard_to_hand()],
        upgraded_actions=[attack(6), return_discard_to_hand()],
        exhaust=True,
        upgraded_exhaust=False,
    ),
    "invoke": CardDef(
        key="invoke",
        name="Invoke",
        card_type="skill",
        rarity="common",
        cost=1,
        target="self",
        description="Next turn, Summon 2 and gain 2 Energy.",
        upgraded_description="Next turn, Summon 3 and gain 3 Energy.",
        actions=[summon_osty_next_turn(2), apply_status("self", "next_turn_energy", 2)],
        upgraded_actions=[summon_osty_next_turn(3), apply_status("self", "next_turn_energy", 3)],
    ),
    "negative_pulse": CardDef(
        key="negative_pulse",
        name="Negative Pulse",
        card_type="skill",
        rarity="common",
        cost=1,
        target="self",
        description="Gain 5 Block. Apply 7 Doom to ALL enemies.",
        upgraded_description="Gain 6 Block. Apply 11 Doom to ALL enemies.",
        actions=[block(5), apply_status("all_enemies", "doom", 7)],
        upgraded_actions=[block(6), apply_status("all_enemies", "doom", 11)],
    ),
    "poke": CardDef(
        key="poke",
        name="Poke",
        card_type="attack",
        rarity="common",
        cost=1,
        target="enemy",
        description="Osty deals 6 damage.",
        upgraded_description="Osty deals 9 damage.",
        actions=[osty_attack(6)],
        upgraded_actions=[osty_attack(9)],
    ),
    "pull_aggro": CardDef(
        key="pull_aggro",
        name="Pull Aggro",
        card_type="skill",
        rarity="common",
        cost=1,
        target="self",
        description="Summon 4. Gain 7 Block.",
        upgraded_description="Summon 5. Gain 9 Block.",
        actions=[summon_osty(4), block(7)],
        upgraded_actions=[summon_osty(5), block(9)],
    ),
    "reap": CardDef(
        key="reap",
        name="Reap",
        card_type="attack",
        rarity="common",
        cost=3,
        target="enemy",
        description="Retain. Deal 27 damage.",
        upgraded_description="Retain. Deal 33 damage.",
        actions=[attack(27)],
        upgraded_actions=[attack(33)],
        retain=True,
    ),
    "reave": CardDef(
        key="reave",
        name="Reave",
        card_type="attack",
        rarity="common",
        cost=1,
        target="enemy",
        description="Deal 9 damage. Add a Soul into your Draw Pile.",
        upgraded_description="Deal 11 damage. Add a Soul+ into your Draw Pile.",
        actions=[attack(9), create_cards("draw", "soul")],
        upgraded_actions=[attack(11), create_cards("draw", "soul", upgraded=True)],
    ),
    "scourge": CardDef(
        key="scourge",
        name="Scourge",
        card_type="skill",
        rarity="common",
        cost=1,
        target="enemy",
        description="Apply 13 Doom. Draw 1 card.",
        upgraded_description="Apply 16 Doom. Draw 2 cards.",
        actions=[apply_status("enemy", "doom", 13), draw(1)],
        upgraded_actions=[apply_status("enemy", "doom", 16), draw(2)],
    ),
    "sculpting_strike": CardDef(
        key="sculpting_strike",
        name="Sculpting Strike",
        card_type="attack",
        rarity="common",
        cost=1,
        target="enemy",
        description="Deal 8 damage. Add Ethereal to a card in your Hand.",
        upgraded_description="Deal 11 damage. Add Ethereal to a card in your Hand.",
        actions=[attack(8), add_ethereal_to_hand()],
        upgraded_actions=[attack(11), add_ethereal_to_hand()],
    ),
    "snap": CardDef(
        key="snap",
        name="Snap",
        card_type="attack",
        rarity="common",
        cost=1,
        target="enemy",
        description="Osty deals 7 damage. Add Retain to a card in your Hand.",
        upgraded_description="Osty deals 10 damage. Add Retain to a card in your Hand.",
        actions=[osty_attack(7), add_retain_to_hand()],
        upgraded_actions=[osty_attack(10), add_retain_to_hand()],
    ),
    "sow": CardDef(
        key="sow",
        name="Sow",
        card_type="attack",
        rarity="common",
        cost=1,
        target="self",
        description="Retain. Deal 8 damage to ALL enemies.",
        upgraded_description="Retain. Deal 11 damage to ALL enemies.",
        actions=[attack_all(8)],
        upgraded_actions=[attack_all(11)],
        retain=True,
    ),
    "wisp": CardDef(
        key="wisp",
        name="Wisp",
        card_type="skill",
        rarity="common",
        cost=0,
        target="self",
        description="Gain 1 Energy. Exhaust.",
        upgraded_description="Retain. Gain 1 Energy. Exhaust.",
        actions=[gain_energy(1)],
        upgraded_actions=[gain_energy(1)],
        exhaust=True,
        upgraded_retain=True,
    ),
}

NECROBINDER_CARD_LIBRARY.update(
    {
        "bone_shards": CardDef(
            key="bone_shards",
            name="Bone Shards",
            card_type="attack",
            rarity="uncommon",
            cost=1,
            target="self",
            description="If Osty is alive, he deals 9 damage to ALL enemies and you gain 9 Block. Osty dies.",
            upgraded_description="If Osty is alive, he deals 12 damage to ALL enemies and you gain 12 Block. Osty dies.",
            actions=[osty_attack_all(9), block(9), {"type": "kill_osty"}],
            upgraded_actions=[osty_attack_all(12), block(12), {"type": "kill_osty"}],
        ),
        "borrowed_time": CardDef(
            key="borrowed_time",
            name="Borrowed Time",
            card_type="skill",
            rarity="uncommon",
            cost=0,
            target="self",
            description="Apply 3 Doom to yourself. Gain 1 Energy.",
            upgraded_description="Apply 3 Doom to yourself. Gain 2 Energy.",
            actions=[apply_status("self", "doom", 3), gain_energy(1)],
            upgraded_actions=[apply_status("self", "doom", 3), gain_energy(2)],
        ),
        "bury": CardDef(
            key="bury",
            name="Bury",
            card_type="attack",
            rarity="uncommon",
            cost=4,
            target="enemy",
            description="Deal 52 damage.",
            upgraded_description="Deal 63 damage.",
            actions=[attack(52)],
            upgraded_actions=[attack(63)],
        ),
        "calcify": CardDef(
            key="calcify",
            name="Calcify",
            card_type="power",
            rarity="uncommon",
            cost=1,
            target="self",
            description="Osty's attacks deal 4 additional damage.",
            upgraded_description="Osty's attacks deal 6 additional damage.",
            actions=[apply_status("self", "calcify", 4)],
            upgraded_actions=[apply_status("self", "calcify", 6)],
        ),
        "capture_spirit": CardDef(
            key="capture_spirit",
            name="Capture Spirit",
            card_type="skill",
            rarity="uncommon",
            cost=1,
            target="enemy",
            description="Enemy loses 3 HP. Add 3 Souls into your Draw Pile.",
            upgraded_description="Enemy loses 4 HP. Add 4 Souls into your Draw Pile.",
            actions=[lose_enemy_hp(3), create_cards("draw", "soul", count=3)],
            upgraded_actions=[lose_enemy_hp(4), create_cards("draw", "soul", count=4)],
        ),
        "cleanse": CardDef(
            key="cleanse",
            name="Cleanse",
            card_type="skill",
            rarity="uncommon",
            cost=1,
            target="self",
            description="Summon 3. Exhaust 1 card from your Draw Pile.",
            upgraded_description="Summon 5. Exhaust 1 card from your Draw Pile.",
            actions=[summon_osty(3), exhaust_from_draw()],
            upgraded_actions=[summon_osty(5), exhaust_from_draw()],
        ),
        "countdown": CardDef(
            key="countdown",
            name="Countdown",
            card_type="power",
            rarity="uncommon",
            cost=1,
            target="self",
            description="At the start of your turn, apply 6 Doom to a random enemy.",
            upgraded_description="At the start of your turn, apply 9 Doom to a random enemy.",
            actions=[apply_status("self", "countdown", 6)],
            upgraded_actions=[apply_status("self", "countdown", 9)],
        ),
        "danse_macabre": CardDef(
            key="danse_macabre",
            name="Danse Macabre",
            card_type="power",
            rarity="uncommon",
            cost=1,
            target="self",
            description="Whenever you play a card that costs 2 Energy or more, gain 3 Block.",
            upgraded_description="Whenever you play a card that costs 2 Energy or more, gain 4 Block.",
            actions=[apply_status("self", "danse_macabre", 3)],
            upgraded_actions=[apply_status("self", "danse_macabre", 4)],
        ),
        "death_march": CardDef(
            key="death_march",
            name="Death March",
            card_type="attack",
            rarity="uncommon",
            cost=1,
            target="enemy",
            description="Deal 8 damage. Deal 3 additional damage for each card drawn during your turn.",
            upgraded_description="Deal 9 damage. Deal 4 additional damage for each card drawn during your turn.",
            actions=[{"type": "death_march", "value": 8, "per_draw": 3}],
            upgraded_actions=[{"type": "death_march", "value": 9, "per_draw": 4}],
        ),
        "deathbringer": CardDef(
            key="deathbringer",
            name="Deathbringer",
            card_type="skill",
            rarity="uncommon",
            cost=2,
            target="self",
            description="Apply 21 Doom and 1 Weak to ALL enemies.",
            upgraded_description="Apply 26 Doom and 1 Weak to ALL enemies.",
            actions=[apply_status("all_enemies", "doom", 21), apply_status("all_enemies", "weak", 1)],
            upgraded_actions=[apply_status("all_enemies", "doom", 26), apply_status("all_enemies", "weak", 1)],
        ),
        "debilitate": CardDef(
            key="debilitate",
            name="Debilitate",
            card_type="attack",
            rarity="uncommon",
            cost=1,
            target="enemy",
            description="Deal 7 damage. Vulnerable and Weak are twice as effective against the enemy for the next 3 turns.",
            upgraded_description="Deal 9 damage. Vulnerable and Weak are twice as effective against the enemy for the next 4 turns.",
            actions=[debilitate(7, 3)],
            upgraded_actions=[debilitate(9, 4)],
        ),
        "delay": CardDef(
            key="delay",
            name="Delay",
            card_type="skill",
            rarity="uncommon",
            cost=2,
            target="self",
            description="Gain 11 Block. Next turn, gain 1 Energy.",
            upgraded_description="Gain 13 Block. Next turn, gain 2 Energy.",
            actions=[block(11), apply_status("self", "next_turn_energy", 1)],
            upgraded_actions=[block(13), apply_status("self", "next_turn_energy", 2)],
        ),
        "deaths_door": CardDef(
            key="deaths_door",
            name="Death's Door",
            card_type="skill",
            rarity="uncommon",
            cost=2,
            target="self",
            description="Gain 13 Block. Next turn, gain 2 Energy.",
            upgraded_description="Gain 17 Block. Next turn, gain 2 Energy.",
            actions=[block(13), apply_status("self", "next_turn_energy", 2)],
            upgraded_actions=[block(17), apply_status("self", "next_turn_energy", 2)],
        ),
        "dirge": CardDef(
            key="dirge",
            name="Dirge",
            card_type="skill",
            rarity="uncommon",
            cost=-1,
            target="self",
            description="Summon 3 X times. Add X Souls into your Draw Pile.",
            upgraded_description="Summon 4 X times. Add X Souls+ into your Draw Pile.",
            actions=[dirge(3)],
            upgraded_actions=[dirge(4, upgraded_souls=True)],
        ),
        "dredge": CardDef(
            key="dredge",
            name="Dredge",
            card_type="skill",
            rarity="uncommon",
            cost=2,
            target="self",
            description="Retain. Put 3 cards from your Discard Pile into your Hand. Exhaust.",
            upgraded_description="Retain. Put 3 cards from your Discard Pile into your Hand. Exhaust.",
            actions=[return_discard_to_hand(3)],
            upgraded_actions=[return_discard_to_hand(3)],
            retain=True,
            exhaust=True,
        ),
        "enfeebling_touch": CardDef(
            key="enfeebling_touch",
            name="Enfeebling Touch",
            card_type="skill",
            rarity="uncommon",
            cost=1,
            target="enemy",
            description="Ethereal. Enemy loses 8 Strength this turn.",
            upgraded_description="Ethereal. Enemy loses 11 Strength this turn.",
            actions=[{"type": "modify_status", "target": "enemy", "status": "strength", "value": -8, "temporary": True}],
            upgraded_actions=[{"type": "modify_status", "target": "enemy", "status": "strength", "value": -11, "temporary": True}],
            ethereal=True,
        ),
        "fetch": CardDef(
            key="fetch",
            name="Fetch",
            card_type="attack",
            rarity="uncommon",
            cost=0,
            target="enemy",
            description="Osty deals 3 damage. If this is the first time this card was played this turn, draw 1 card.",
            upgraded_description="Osty deals 6 damage. If this is the first time this card was played this turn, draw 1 card.",
            actions=[osty_attack(3), if_first_play_draw(1)],
            upgraded_actions=[osty_attack(6), if_first_play_draw(1)],
        ),
        "friendship": CardDef(
            key="friendship",
            name="Friendship",
            card_type="power",
            rarity="uncommon",
            cost=1,
            target="self",
            description="Lose 2 Strength. At the start of your turn, gain 1 Energy.",
            upgraded_description="Lose 1 Strength. At the start of your turn, gain 1 Energy.",
            actions=[
                {"type": "modify_status", "target": "self", "status": "strength", "value": -2},
                apply_status("self", "friendship", 1),
            ],
            upgraded_actions=[
                {"type": "modify_status", "target": "self", "status": "strength", "value": -1},
                apply_status("self", "friendship", 1),
            ],
        ),
        "forbidden_grimoire": CardDef(
            key="forbidden_grimoire",
            name="Forbidden Grimoire",
            card_type="power",
            rarity="ancient",
            cost=2,
            target="self",
            description="At the end of combat, you may remove a card from your Deck. Eternal.",
            upgraded_description="At the end of combat, you may remove a card from your Deck. Eternal.",
            actions=[forbidden_grimoire()],
            upgraded_actions=[forbidden_grimoire()],
        ),
        "protector": CardDef(
            key="protector",
            name="Protector",
            card_type="attack",
            rarity="ancient",
            cost=1,
            target="enemy",
            description="Osty deals 10 damage. Deals additional damage equal to Osty's Max HP.",
            upgraded_description="Osty deals 15 damage. Deals additional damage equal to Osty's Max HP.",
            actions=[protector_attack(10)],
            upgraded_actions=[protector_attack(15)],
        ),
        "haunt": CardDef(
            key="haunt",
            name="Haunt",
            card_type="power",
            rarity="uncommon",
            cost=1,
            target="self",
            description="Whenever you play a Soul, a random enemy loses 6 HP.",
            upgraded_description="Whenever you play a Soul, a random enemy loses 8 HP.",
            actions=[apply_status("self", "haunt", 6)],
            upgraded_actions=[apply_status("self", "haunt", 8)],
        ),
        "high_five": CardDef(
            key="high_five",
            name="High Five",
            card_type="attack",
            rarity="uncommon",
            cost=1,
            target="self",
            description="Osty deals 11 damage and applies 2 Vulnerable to ALL enemies.",
            upgraded_description="Osty deals 13 damage and applies 3 Vulnerable to ALL enemies.",
            actions=[osty_attack(11), apply_status("all_enemies", "vulnerable", 2)],
            upgraded_actions=[osty_attack(13), apply_status("all_enemies", "vulnerable", 3)],
        ),
        "legion_of_bone": CardDef(
            key="legion_of_bone",
            name="Legion Of Bone",
            card_type="skill",
            rarity="uncommon",
            cost=1,
            target="self",
            description="Summon 6. Exhaust.",
            upgraded_description="Summon 8. Exhaust.",
            actions=[summon_osty(6)],
            upgraded_actions=[summon_osty(8)],
            exhaust=True,
        ),
        "lethality": CardDef(
            key="lethality",
            name="Lethality",
            card_type="power",
            rarity="uncommon",
            cost=1,
            target="self",
            description="Ethereal. The first Attack you play each turn deals 50% additional damage.",
            upgraded_description="Ethereal. The first Attack you play each turn deals 75% additional damage.",
            actions=[apply_status("self", "lethality", 50)],
            upgraded_actions=[apply_status("self", "lethality", 75)],
            ethereal=True,
        ),
        "melancholy": CardDef(
            key="melancholy",
            name="Melancholy",
            card_type="skill",
            rarity="uncommon",
            cost=3,
            target="self",
            description="Gain 13 Block. Reduce this card's cost by 1 whenever anyone dies.",
            upgraded_description="Gain 17 Block. Reduce this card's cost by 1 whenever anyone dies.",
            actions=[block(13)],
            upgraded_actions=[block(17)],
        ),
        "no_escape": CardDef(
            key="no_escape",
            name="No Escape",
            card_type="skill",
            rarity="uncommon",
            cost=1,
            target="enemy",
            description="Apply 10 Doom, plus an additional 5 Doom for every 10 Doom already on this enemy.",
            upgraded_description="Apply 15 Doom, plus an additional 5 Doom for every 10 Doom already on this enemy.",
            actions=[no_escape(10)],
            upgraded_actions=[no_escape(15)],
        ),
        "pagestorm": CardDef(
            key="pagestorm",
            name="Pagestorm",
            card_type="power",
            rarity="uncommon",
            cost=1,
            target="self",
            description="Whenever you draw an Ethereal card, draw 1 card.",
            upgraded_description="Whenever you draw an Ethereal card, draw 1 card.",
            actions=[apply_status("self", "pagestorm", 1)],
            upgraded_actions=[apply_status("self", "pagestorm", 1)],
        ),
        "parse": CardDef(
            key="parse",
            name="Parse",
            card_type="skill",
            rarity="uncommon",
            cost=1,
            target="self",
            description="Ethereal. Draw 3 cards.",
            upgraded_description="Ethereal. Draw 4 cards.",
            actions=[draw(3)],
            upgraded_actions=[draw(4)],
            ethereal=True,
        ),
        "pull_from_below": CardDef(
            key="pull_from_below",
            name="Pull From Below",
            card_type="attack",
            rarity="uncommon",
            cost=1,
            target="enemy",
            description="Deal 5 damage for each Ethereal card played this combat.",
            upgraded_description="Deal 7 damage for each Ethereal card played this combat.",
            actions=[pull_from_below(5)],
            upgraded_actions=[pull_from_below(7)],
        ),
    }
)

NECROBINDER_CARD_LIBRARY.update(
    {
        "putrefy": CardDef(
            key="putrefy",
            name="Putrefy",
            card_type="skill",
            rarity="uncommon",
            cost=1,
            target="enemy",
            description="Apply 2 Weak. Apply 2 Vulnerable. Exhaust.",
            upgraded_description="Apply 3 Weak. Apply 3 Vulnerable. Exhaust.",
            actions=[apply_status("enemy", "weak", 2), apply_status("enemy", "vulnerable", 2)],
            upgraded_actions=[apply_status("enemy", "weak", 3), apply_status("enemy", "vulnerable", 3)],
            exhaust=True,
        ),
        "rattle": CardDef(
            key="rattle",
            name="Rattle",
            card_type="attack",
            rarity="uncommon",
            cost=1,
            target="enemy",
            description="Osty deals 7 damage. Hits an additional time for each other time he attacked this turn.",
            upgraded_description="Osty deals 9 damage. Hits an additional time for each other time he attacked this turn.",
            actions=[rattle(7)],
            upgraded_actions=[rattle(9)],
        ),
        "right_hand_hand": CardDef(
            key="right_hand_hand",
            name="Right Hand Hand",
            card_type="attack",
            rarity="uncommon",
            cost=1,
            target="enemy",
            description="Osty deals 4 damage. Whenever you play a card that costs 2 Energy or more, return this to your Hand from the Discard Pile.",
            upgraded_description="Osty deals 6 damage. Whenever you play a card that costs 2 Energy or more, return this to your Hand from the Discard Pile.",
            actions=[osty_attack(4)],
            upgraded_actions=[osty_attack(6)],
        ),
        "severance": CardDef(
            key="severance",
            name="Severance",
            card_type="attack",
            rarity="uncommon",
            cost=2,
            target="enemy",
            description="Deal 13 damage. Add a Soul into your Draw Pile, Hand, and Discard Pile.",
            upgraded_description="Deal 18 damage. Add a Soul+ into your Draw Pile, Hand, and Discard Pile.",
            actions=[severance(13)],
            upgraded_actions=[severance(18)],
        ),
        "shroud": CardDef(
            key="shroud",
            name="Shroud",
            card_type="power",
            rarity="uncommon",
            cost=1,
            target="self",
            description="Whenever you apply Doom, gain 2 Block.",
            upgraded_description="Whenever you apply Doom, gain 3 Block.",
            actions=[apply_status("self", "shroud", 2)],
            upgraded_actions=[apply_status("self", "shroud", 3)],
        ),
        "sic_em": CardDef(
            key="sic_em",
            name="Sic 'Em",
            card_type="attack",
            rarity="uncommon",
            cost=1,
            target="enemy",
            description="Osty deals 5 damage. Whenever Osty hits this enemy this turn, Summon 2.",
            upgraded_description="Osty deals 6 damage. Whenever Osty hits this enemy this turn, Summon 3.",
            actions=[sic_em(5, 2)],
            upgraded_actions=[sic_em(6, 3)],
        ),
        "sleight_of_flesh": CardDef(
            key="sleight_of_flesh",
            name="Sleight Of Flesh",
            card_type="power",
            rarity="uncommon",
            cost=2,
            target="self",
            description="Whenever you apply a debuff to an enemy, they take 9 damage.",
            upgraded_description="Whenever you apply a debuff to an enemy, they take 13 damage.",
            actions=[apply_status("self", "sleight_of_flesh", 9)],
            upgraded_actions=[apply_status("self", "sleight_of_flesh", 13)],
        ),
        "spur": CardDef(
            key="spur",
            name="Spur",
            card_type="skill",
            rarity="uncommon",
            cost=1,
            target="self",
            description="Retain. Summon 3. Osty heals 5 HP.",
            upgraded_description="Retain. Summon 5. Osty heals 7 HP.",
            actions=[summon_osty(3), osty_heal(5)],
            upgraded_actions=[summon_osty(5), osty_heal(7)],
            retain=True,
        ),
        "veilpiercer": CardDef(
            key="veilpiercer",
            name="Veilpiercer",
            card_type="attack",
            rarity="uncommon",
            cost=1,
            target="enemy",
            description="Deal 10 damage. The next Ethereal card you play costs 0 this turn.",
            upgraded_description="Deal 13 damage. The next Ethereal card you play costs 0 this turn.",
            actions=[attack(10), apply_status("self", "next_ethereal_free", 1)],
            upgraded_actions=[attack(13), apply_status("self", "next_ethereal_free", 1)],
        ),
        "banshees_cry": CardDef(
            key="banshees_cry",
            name="Banshee's Cry",
            card_type="attack",
            rarity="rare",
            cost=6,
            target="self",
            description="Deal 33 damage to ALL enemies. Costs 2 less for each Ethereal card played this combat.",
            upgraded_description="Deal 39 damage to ALL enemies. Costs 2 less for each Ethereal card played this combat.",
            actions=[attack_all(33)],
            upgraded_actions=[attack_all(39)],
        ),
        "call_of_the_void": CardDef(
            key="call_of_the_void",
            name="Call Of The Void",
            card_type="power",
            rarity="rare",
            cost=1,
            target="self",
            description="At the start of your turn, add 1 random card into your Hand. It gains Ethereal.",
            upgraded_description="Innate. At the start of your turn, add 1 random card into your Hand. It gains Ethereal.",
            actions=[call_of_the_void()],
            upgraded_actions=[call_of_the_void()],
            upgraded_innate=True,
        ),
        "demesne": CardDef(
            key="demesne",
            name="Demesne",
            card_type="power",
            rarity="rare",
            cost=1,
            target="self",
            description="Ethereal. At the start of your turn, gain 1 Energy and draw 1 additional card.",
            upgraded_description="Ethereal. At the start of your turn, gain 1 Energy and draw 1 additional card.",
            actions=[apply_status("self", "demesne", 1)],
            upgraded_actions=[apply_status("self", "demesne", 1)],
            ethereal=True,
        ),
        "devour_life": CardDef(
            key="devour_life",
            name="Devour Life",
            card_type="power",
            rarity="rare",
            cost=1,
            target="self",
            description="Whenever you play a Soul, Summon 1.",
            upgraded_description="Whenever you play a Soul, Summon 2.",
            actions=[apply_status("self", "devour_life", 1)],
            upgraded_actions=[apply_status("self", "devour_life", 2)],
        ),
        "eidolon": CardDef(
            key="eidolon",
            name="Eidolon",
            card_type="skill",
            rarity="rare",
            cost=1,
            target="self",
            description="Exhaust your Hand. If 9 cards were Exhausted this way, gain 1 Intangible.",
            upgraded_description="Exhaust your Hand. If 9 cards were Exhausted this way, gain 2 Intangible.",
            actions=[exhaust_hand_threshold_intangible(9, 1)],
            upgraded_actions=[exhaust_hand_threshold_intangible(9, 2)],
        ),
        "end_of_days": CardDef(
            key="end_of_days",
            name="End Of Days",
            card_type="skill",
            rarity="rare",
            cost=2,
            target="self",
            description="Apply 29 Doom to ALL enemies. Doom immediately defeats doomed enemies.",
            upgraded_description="Apply 37 Doom to ALL enemies. Doom immediately defeats doomed enemies.",
            actions=[end_of_days(29)],
            upgraded_actions=[end_of_days(37)],
            exhaust=True,
        ),
        "eradicate": CardDef(
            key="eradicate",
            name="Eradicate",
            card_type="attack",
            rarity="rare",
            cost=-1,
            target="enemy",
            description="Deal 11 damage X times.",
            upgraded_description="Deal 14 damage X times.",
            actions=[x_attack(11)],
            upgraded_actions=[x_attack(14)],
        ),
        "glimpse_beyond": CardDef(
            key="glimpse_beyond",
            name="Glimpse Beyond",
            card_type="skill",
            rarity="rare",
            cost=1,
            target="self",
            description="Add 3 Souls into your Draw Pile. Exhaust.",
            upgraded_description="Add 4 Souls+ into your Draw Pile. Exhaust.",
            actions=[create_cards("draw", "soul", count=3)],
            upgraded_actions=[create_cards("draw", "soul", count=4, upgraded=True)],
            exhaust=True,
        ),
        "necro_mastery": CardDef(
            key="necro_mastery",
            name="Necro Mastery",
            card_type="power",
            rarity="rare",
            cost=3,
            target="self",
            description="Summon 5. Whenever Osty loses HP, ALL enemies lose that much HP.",
            upgraded_description="Summon 8. Whenever Osty loses HP, ALL enemies lose that much HP.",
            actions=[summon_osty(5), apply_status("self", "necro_mastery", 1)],
            upgraded_actions=[summon_osty(8), apply_status("self", "necro_mastery", 1)],
        ),
        "neurosurge": CardDef(
            key="neurosurge",
            name="Neurosurge",
            card_type="skill",
            rarity="rare",
            cost=0,
            target="self",
            description="Gain 2 Energy. Draw 2 cards. At the start of your turn, apply 3 Doom to yourself.",
            upgraded_description="Gain 3 Energy. Draw 2 cards. At the start of your turn, apply 3 Doom to yourself.",
            actions=[gain_energy(2), draw(2), apply_status("self", "neurosurge", 3)],
            upgraded_actions=[gain_energy(3), draw(2), apply_status("self", "neurosurge", 3)],
        ),
        "hang": CardDef(
            key="hang",
            name="Hang",
            card_type="attack",
            rarity="rare",
            cost=1,
            target="enemy",
            description="Deal 10 damage. Double the damage ALL Hang cards deal to this enemy.",
            upgraded_description="Deal 13 damage. Double the damage ALL Hang cards deal to this enemy.",
            actions=[hang_attack(10)],
            upgraded_actions=[hang_attack(13)],
        ),
        "misery": CardDef(
            key="misery",
            name="Misery",
            card_type="attack",
            rarity="rare",
            cost=0,
            target="enemy",
            description="Deal 7 damage. Apply any debuffs on the enemy to ALL other enemies.",
            upgraded_description="Retain. Deal 9 damage. Apply any debuffs on the enemy to ALL other enemies.",
            actions=[misery(7)],
            upgraded_actions=[misery(9)],
            upgraded_retain=True,
        ),
        "oblivion": CardDef(
            key="oblivion",
            name="Oblivion",
            card_type="skill",
            rarity="rare",
            cost=1,
            target="self",
            description="Whenever you play a card this turn, apply 3 Doom to the enemy.",
            upgraded_description="Whenever you play a card this turn, apply 4 Doom to the enemy.",
            actions=[apply_status("self", "oblivion", 3)],
            upgraded_actions=[apply_status("self", "oblivion", 4)],
        ),
        "reanimate": CardDef(
            key="reanimate",
            name="Reanimate",
            card_type="skill",
            rarity="rare",
            cost=2,
            target="self",
            description="Summon 20. Exhaust.",
            upgraded_description="Summon 25. Exhaust.",
            actions=[summon_osty(20)],
            upgraded_actions=[summon_osty(25)],
            exhaust=True,
        ),
        "reaper_form": CardDef(
            key="reaper_form",
            name="Reaper Form",
            card_type="power",
            rarity="rare",
            cost=3,
            target="self",
            description="Whenever Attacks deal damage, they also apply that much Doom.",
            upgraded_description="Retain. Whenever Attacks deal damage, they also apply that much Doom.",
            actions=[apply_status("self", "reaper_form", 1)],
            upgraded_actions=[apply_status("self", "reaper_form", 1)],
            upgraded_retain=True,
        ),
        "sacrifice": CardDef(
            key="sacrifice",
            name="Sacrifice",
            card_type="skill",
            rarity="rare",
            cost=1,
            target="self",
            description="Retain. If Osty is alive, he dies and you gain Block equal to double his Max HP.",
            upgraded_description="Retain. If Osty is alive, he dies and you gain Block equal to double his Max HP.",
            actions=[{"type": "sacrifice_osty"}],
            upgraded_actions=[{"type": "sacrifice_osty"}],
            retain=True,
        ),
        "seance": CardDef(
            key="seance",
            name="Seance",
            card_type="skill",
            rarity="rare",
            cost=0,
            target="self",
            description="Ethereal. Transform a card in your Draw Pile into Soul.",
            upgraded_description="Ethereal. Transform a card in your Draw Pile into Soul+.",
            actions=[transform_draw_to_soul()],
            upgraded_actions=[transform_draw_to_soul(upgraded=True)],
            ethereal=True,
        ),
        "sentry_mode": CardDef(
            key="sentry_mode",
            name="Sentry Mode",
            card_type="power",
            rarity="rare",
            cost=2,
            target="self",
            description="At the start of your turn, add 1 Sweeping Gaze into your Hand.",
            upgraded_description="At the start of your turn, add 1 Sweeping Gaze+ into your Hand.",
            actions=[apply_status("self", "sentry_mode", 1)],
            upgraded_actions=[apply_status("self", "sentry_mode", 2)],
        ),
        "shared_fate": CardDef(
            key="shared_fate",
            name="Shared Fate",
            card_type="skill",
            rarity="rare",
            cost=0,
            target="enemy",
            description="Lose 2 Strength. Enemy loses 2 Strength. Exhaust.",
            upgraded_description="Lose 2 Strength. Enemy loses 3 Strength. Exhaust.",
            actions=[
                {"type": "modify_status", "target": "self", "status": "strength", "value": -2},
                {"type": "modify_status", "target": "enemy", "status": "strength", "value": -2},
            ],
            upgraded_actions=[
                {"type": "modify_status", "target": "self", "status": "strength", "value": -2},
                {"type": "modify_status", "target": "enemy", "status": "strength", "value": -3},
            ],
            exhaust=True,
        ),
        "soul_storm": CardDef(
            key="soul_storm",
            name="Soul Storm",
            card_type="attack",
            rarity="rare",
            cost=1,
            target="enemy",
            description="Deal 9 damage. Deal 2 additional damage for each Soul in your Exhaust Pile.",
            upgraded_description="Deal 9 damage. Deal 3 additional damage for each Soul in your Exhaust Pile.",
            actions=[soul_storm(9, per_soul=2)],
            upgraded_actions=[soul_storm(9, per_soul=3)],
        ),
        "spirit_of_ash": CardDef(
            key="spirit_of_ash",
            name="Spirit Of Ash",
            card_type="power",
            rarity="rare",
            cost=1,
            target="self",
            description="Whenever you play an Ethereal card, gain 4 Block.",
            upgraded_description="Whenever you play an Ethereal card, gain 5 Block.",
            actions=[apply_status("self", "spirit_of_ash", 4)],
            upgraded_actions=[apply_status("self", "spirit_of_ash", 5)],
        ),
        "squeeze": CardDef(
            key="squeeze",
            name="Squeeze",
            card_type="attack",
            rarity="rare",
            cost=3,
            target="enemy",
            description="Osty deals 25 damage. Deal 5 additional damage for ALL your other Osty Attacks.",
            upgraded_description="Osty deals 30 damage. Deal 6 additional damage for ALL your other Osty Attacks.",
            actions=[squeeze(25, per_attack=5)],
            upgraded_actions=[squeeze(30, per_attack=6)],
        ),
        "the_scythe": CardDef(
            key="the_scythe",
            name="The Scythe",
            card_type="attack",
            rarity="rare",
            cost=1,
            target="enemy",
            description="Deal 13 damage. Permanently increase this card's damage by 3. Exhaust.",
            upgraded_description="Deal 13 damage. Permanently increase this card's damage by 4. Exhaust.",
            actions=[scythe_attack(13, growth=3)],
            upgraded_actions=[scythe_attack(13, growth=4)],
            exhaust=True,
        ),
        "times_up": CardDef(
            key="times_up",
            name="Time's Up",
            card_type="attack",
            rarity="rare",
            cost=2,
            target="enemy",
            description="Deal damage equal to the enemy's Doom. Exhaust.",
            upgraded_description="Retain. Deal damage equal to the enemy's Doom. Exhaust.",
            actions=[{"type": "attack_enemy_doom"}],
            upgraded_actions=[{"type": "attack_enemy_doom"}],
            exhaust=True,
            upgraded_retain=True,
        ),
        "transfigure": CardDef(
            key="transfigure",
            name="Transfigure",
            card_type="skill",
            rarity="rare",
            cost=1,
            target="self",
            description="Add Replay to a card in your Hand. It costs 1 more Energy. Exhaust.",
            upgraded_description="Add Replay to a card in your Hand. It costs 1 more Energy.",
            actions=[transfigure()],
            upgraded_actions=[transfigure()],
            exhaust=True,
            upgraded_exhaust=False,
        ),
        "undeath": CardDef(
            key="undeath",
            name="Undeath",
            card_type="skill",
            rarity="rare",
            cost=0,
            target="self",
            description="Gain 7 Block. Add a copy of this card into your Discard Pile.",
            upgraded_description="Gain 9 Block. Add a copy of this card into your Discard Pile.",
            actions=[block(7), create_self_copy("discard")],
            upgraded_actions=[block(9), create_self_copy("discard")],
        ),
    }
)

NECROBINDER_RELIC_LIBRARY: dict[str, RelicDef] = {
    "bound_phylactery": RelicDef(
        key="bound_phylactery",
        name="Bound Phylactery",
        rarity="starter",
        description="At the start of your turn, Summon 1.",
        shop_cost=0,
    ),
    "phylactery_unbound": RelicDef(
        key="phylactery_unbound",
        name="Phylactery Unbound",
        rarity="boss",
        description="Replaces Bound Phylactery. At the start of each combat, Summon 5. At the start of your turn, Summon 2.",
        shop_cost=0,
    ),
    "bone_flute": RelicDef(
        key="bone_flute",
        name="Bone Flute",
        rarity="common",
        description="Whenever Osty attacks, gain 2 Block.",
    ),
    "book_repair_knife": RelicDef(
        key="book_repair_knife",
        name="Book Repair Knife",
        rarity="uncommon",
        description="Whenever a non-Minion enemy dies to Doom, heal 3 HP.",
    ),
    "funerary_mask": RelicDef(
        key="funerary_mask",
        name="Funerary Mask",
        rarity="uncommon",
        description="At the start of each combat, add 3 Souls into your Draw Pile.",
    ),
    "big_hat": RelicDef(
        key="big_hat",
        name="Big Hat",
        rarity="rare",
        description="At the start of each combat, add 2 random Ethereal cards into your Hand.",
        shop_cost=250,
    ),
    "bookmark": RelicDef(
        key="bookmark",
        name="Bookmark",
        rarity="rare",
        description="At the end of each turn, lower the cost of a random Retained card by 1 until played.",
        shop_cost=250,
    ),
    "ivory_tile": RelicDef(
        key="ivory_tile",
        name="Ivory Tile",
        rarity="rare",
        description="Whenever you play a card that costs 3 Energy or more, gain 1 Energy.",
        shop_cost=250,
    ),
    "undying_sigil": RelicDef(
        key="undying_sigil",
        name="Undying Sigil",
        rarity="shop",
        description="Enemies with at least as much Doom as HP deal 50% less damage.",
        shop_cost=180,
    ),
}

NECROBINDER_POTION_LIBRARY: dict[str, PotionDef] = {
    "potion_of_doom": PotionDef(
        key="potion_of_doom",
        name="Potion Of Doom",
        rarity="common",
        description="Apply 33 Doom.",
        target="enemy",
        actions=[apply_status("enemy", "doom", 33)],
        shop_cost=55,
    ),
    "bone_brew": PotionDef(
        key="bone_brew",
        name="Bone Brew",
        rarity="uncommon",
        description="Summon 15.",
        target="self",
        actions=[summon_osty(15)],
        shop_cost=75,
    ),
    "pot_of_ghouls": PotionDef(
        key="pot_of_ghouls",
        name="Pot Of Ghouls",
        rarity="rare",
        description="Add 2 Souls into your Hand.",
        target="self",
        actions=[create_cards("hand", "soul", count=2)],
        shop_cost=110,
    ),
}

NECROBINDER_CHARACTER_DEF: dict[str, Any] = {
    "name": "Necrobinder",
    "max_hp": 66,
    "starter_relic": "bound_phylactery",
    "starting_deck": [
        "strike",
        "strike",
        "strike",
        "strike",
        "strike",
        "defend",
        "defend",
        "defend",
        "defend",
        "defend",
        "bodyguard",
        "unleash",
    ],
    "card_pool": sorted(
        key
        for key, card in NECROBINDER_CARD_LIBRARY.items()
        if card.rarity not in {"starter", "special", "ancient"}
    ),
}
