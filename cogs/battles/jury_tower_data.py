from __future__ import annotations

from dataclasses import dataclass
import random


JURY_TOWER_FLOOR_COUNT = 77
JURY_SEGMENT_LENGTH = 11
JURY_COSMETIC_TITLE = "Favored by the Iron Coven"


@dataclass(frozen=True)
class JudgeDefinition:
    key: str
    judge_name: str
    title: str
    element: str
    color: int
    chamber_prefix: str
    minion_one: tuple[str, ...]
    minion_two: tuple[str, ...]
    bosses: tuple[str, ...]
    trial_type: str
    intro_line: str


JUDGES: tuple[JudgeDefinition, ...] = (
    JudgeDefinition(
        key="mercy",
        judge_name="Thane Blackmaul",
        title="Mercy Hammer",
        element="Dark",
        color=0xD7C178,
        chamber_prefix="Anvil Hall of Obedience",
        minion_one=("Kneeling Ironborn", "Ashen Penitent", "Chainbound Squire"),
        minion_two=("Lantern-Helmed Reaver", "Oathbound Ward", "Mercy Hound"),
        bosses=("The Gilded Pardoner", "The Iron Warden", "Thane's Headsman"),
        trial_type="mercy",
        intro_line="Mercy only matters when it costs you the kill.",
    ),
    JudgeDefinition(
        key="truth",
        judge_name="Duskwarden Vehl",
        title="Veil of Deceit",
        element="Wind",
        color=0x70B4E4,
        chamber_prefix="Crypt of Broken Helms",
        minion_one=("Silent Liar", "Tongue-Split Herald", "Rune-Scar Oracle"),
        minion_two=("Ash Scribe", "Blind Warden", "Grave Listener"),
        bosses=("The Perjurer", "Null Inquisitor", "Vehl's Mouthpiece"),
        trial_type="truth",
        intro_line="Truth survives the blade, not the rumor.",
    ),
    JudgeDefinition(
        key="resolve",
        judge_name="Kharvul Stonegrip",
        title="Black Bastion",
        element="Earth",
        color=0x9C8F73,
        chamber_prefix="Gate of the Iron Bastion",
        minion_one=("Stonebound Sentinel", "Siege Hound", "Unbroken Halberd"),
        minion_two=("Iron Guardian", "Gravelord Veteran", "Oath Pike"),
        bosses=("The Wall That Walks", "Citadel Reaver", "Kharvul the Unmoved"),
        trial_type="resolve",
        intro_line="If you cannot endure, you do not advance.",
    ),
    JudgeDefinition(
        key="sacrifice",
        judge_name="Caldrun the Furnace",
        title="Pyre Tithe",
        element="Fire",
        color=0xD96B39,
        chamber_prefix="Forge of Ashen Oaths",
        minion_one=("Ember Penitent", "Brand Reaver", "Ash Forgebearer"),
        minion_two=("Cinder Collector", "Scorch Warden", "Oath Furnace"),
        bosses=("The Tithe Engine", "High Forger Calvein", "Caldrun the Furnace"),
        trial_type="sacrifice",
        intro_line="Nothing passes the forge unpaid.",
    ),
    JudgeDefinition(
        key="balance",
        judge_name="Meridor Ironchain",
        title="Chain Balance",
        element="Water",
        color=0x5EA8D1,
        chamber_prefix="Dais of the Hanging Chain",
        minion_one=("Chainbearer", "Counterweight Spear", "Measured Reaver"),
        minion_two=("Scale Knight", "Weight Warden", "Mirror Shield"),
        bosses=("Twin-Pan Executioner", "The Counterpoise", "Meridor the Leveler"),
        trial_type="balance",
        intro_line="A wild swing is just a confession.",
    ),
    JudgeDefinition(
        key="ambition",
        judge_name="Mordrake the Uncrowned",
        title="Crown Hunger",
        element="Dark",
        color=0x9655B6,
        chamber_prefix="Throne of Want",
        minion_one=("Laureled Reaver", "Crown-Thief", "Gilded Hound"),
        minion_two=("Vault Breaker", "Glory Collector", "Throne Climber"),
        bosses=("The Climbing King", "Vault Tyrant", "Mordrake the Unfilled"),
        trial_type="ambition",
        intro_line="Hunger makes the strong faster and the foolish blind.",
    ),
    JudgeDefinition(
        key="sentence",
        judge_name="Urgrin Blackmaul",
        title="Final Sentence",
        element="Corrupted",
        color=0xC0392B,
        chamber_prefix="Seat of the Black Maul",
        minion_one=("Red Herald", "Sentence Hound", "Gallows Warden"),
        minion_two=("Doom Herald", "Black Jury", "Maul Revenant"),
        bosses=("The Black Jury", "Execution Prime", "Urgrin the Final"),
        trial_type="sentence",
        intro_line="Every choice returns to the maul.",
    ),
)


ACT_LABELS = ("Outer Gate", "Black Hall", "Inner Vault", "Final Reckoning")
JURY_BRACKET_BASE_SNAPSHOT = {
    "attack_base": 3200,
    "hp_base": 12000,
    "defense_base": 2200,
}
JURY_POWER_BRACKETS = (
    {"key": "court_tier_i", "label": "Maul Ring I", "max_score": 2000, "multiplier": 0.78, "writ_multiplier": 1.00},
    {"key": "court_tier_ii", "label": "Maul Ring II", "max_score": 4000, "multiplier": 0.92, "writ_multiplier": 1.15},
    {"key": "court_tier_iii", "label": "Maul Ring III", "max_score": 6000, "multiplier": 1.06, "writ_multiplier": 1.30},
    {"key": "court_tier_iv", "label": "Maul Ring IV", "max_score": 8000, "multiplier": 1.20, "writ_multiplier": 1.45},
    {"key": "court_tier_v", "label": "Maul Ring V", "max_score": 10000, "multiplier": 1.36, "writ_multiplier": 1.60},
    {"key": "court_tier_vi", "label": "Maul Ring VI", "max_score": 12000, "multiplier": 1.54, "writ_multiplier": 1.80},
    {"key": "court_tier_vii", "label": "Maul Ring VII", "max_score": 14000, "multiplier": 1.74, "writ_multiplier": 2.00},
    {"key": "court_tier_viii", "label": "Maul Ring VIII", "max_score": 16000, "multiplier": 1.88, "writ_multiplier": 2.15},
    {"key": "court_tier_ix", "label": "Maul Ring IX", "max_score": 18000, "multiplier": 2.02, "writ_multiplier": 2.30},
    {"key": "court_tier_x", "label": "Maul Ring X", "max_score": None, "multiplier": 2.18, "writ_multiplier": 2.50},
)
JURY_JUDGE_BASE_SCALES = (0.68, 0.78, 0.88, 0.98, 1.08, 1.18, 1.28)
JURY_ROLE_SCALE_TEMPLATES = {
    "minion1": {
        "hp_multiplier": 1.48,
        "defense_ratio": 0.095,
        "attack_armor_ratio": 0.98,
        "attack_hp_ratio": 0.036,
    },
    "minion2": {
        "hp_multiplier": 1.95,
        "defense_ratio": 0.132,
        "attack_armor_ratio": 1.00,
        "attack_hp_ratio": 0.049,
    },
    "boss": {
        "hp_multiplier": 3.25,
        "defense_ratio": 0.165,
        "attack_armor_ratio": 1.01,
        "attack_hp_ratio": 0.068,
    },
}
JURY_JUDGE_SCALE_BIASES = {
    "mercy": {
        "hp_multiplier": 1.00,
        "defense_ratio": 0.90,
        "attack_armor_ratio": 0.94,
        "attack_hp_ratio": 0.82,
    },
    "truth": {
        "hp_multiplier": 0.96,
        "defense_ratio": 0.98,
        "attack_armor_ratio": 0.97,
        "attack_hp_ratio": 0.92,
    },
    "resolve": {
        "hp_multiplier": 1.18,
        "defense_ratio": 1.12,
        "attack_armor_ratio": 0.96,
        "attack_hp_ratio": 0.93,
    },
    "sacrifice": {
        "hp_multiplier": 0.94,
        "defense_ratio": 0.90,
        "attack_armor_ratio": 1.02,
        "attack_hp_ratio": 1.06,
    },
    "balance": {
        "hp_multiplier": 1.03,
        "defense_ratio": 1.02,
        "attack_armor_ratio": 0.99,
        "attack_hp_ratio": 0.98,
    },
    "ambition": {
        "hp_multiplier": 0.99,
        "defense_ratio": 0.94,
        "attack_armor_ratio": 1.05,
        "attack_hp_ratio": 1.08,
    },
    "sentence": {
        "hp_multiplier": 1.12,
        "defense_ratio": 1.06,
        "attack_armor_ratio": 1.04,
        "attack_hp_ratio": 1.08,
    },
}


def _boss_reward_for_judge(judge_index: int, clear_cycle: int) -> dict:
    crate_cycle = ("common", "uncommon", "rare", "materials", "magic", "fortune", "legendary")
    money_base = (12000, 18000, 25000, 35000, 45000, 65000, 90000)
    writs_base = (24, 30, 38, 48, 60, 75, 100)
    clear_number = max(1, int(clear_cycle))
    is_reset_turn = (clear_number % 2 == 1)
    return {
        "crate_type": crate_cycle[judge_index] if is_reset_turn else "fortune",
        "money": money_base[judge_index],
        "appeals": 1,
        "writs": writs_base[judge_index],
        "reset_fragment": 1 if judge_index in {1, 3, 5} else 0,
        "reset_potion": 1 if is_reset_turn else 0,
    }


def _build_enemy_scale_profile(
    judge: JudgeDefinition,
    judge_index: int,
    local_floor: int,
    role: str,
) -> dict[str, float]:
    role_template = JURY_ROLE_SCALE_TEMPLATES[role]
    judge_bias = JURY_JUDGE_SCALE_BIASES[judge.key]
    floor_scale = (
        JURY_JUDGE_BASE_SCALES[judge_index]
        * (1 + ((local_floor - 1) * 0.03))
        * (1.05 if role == "boss" else 1.02 if role == "minion2" else 1.0)
    )
    return {
        "floor_scale": round(floor_scale, 4),
        "hp_multiplier": round(role_template["hp_multiplier"] * judge_bias["hp_multiplier"], 4),
        "defense_ratio": round(role_template["defense_ratio"] * judge_bias["defense_ratio"], 4),
        "attack_armor_ratio": round(role_template["attack_armor_ratio"] * judge_bias["attack_armor_ratio"], 4),
        "attack_hp_ratio": round(role_template["attack_hp_ratio"] * judge_bias["attack_hp_ratio"], 4),
    }


def _build_choice(judge: JudgeDefinition, local_floor: int, names: dict[str, str], floor: int) -> dict:
    prompt_floors = {1, 5, 8, 11}
    prompt = local_floor in prompt_floors

    if judge.trial_type == "mercy":
        return {
            "prompt": prompt,
            "default": "pardon",
            "prompt_text": "Will you stay the blow, or bury everything before it kneels?",
            "options": [
                {
                    "key": "pardon",
                    "label": "Pardon",
                    "description": "Spare the broken and force the strong to reveal themselves.",
                    "effect": "-5% damage. Enemies can kneel below 30% HP for extra favor.",
                    "quote": "Mercy is steel with the swing held back.",
                },
                {
                    "key": "condemn",
                    "label": "Condemn",
                    "description": "Break the floor fast and wear the stain.",
                    "effect": "+15% damage. No surrender. Each execution adds contempt.",
                    "quote": "Then let the dead speak for you.",
                },
            ],
        }

    if judge.trial_type == "truth":
        role_options = ("minion1", "minion2", "boss")
        liar_target = random.choice(role_options)
        witness_target = random.choice([role for role in role_options if role != liar_target])
        options = [
            {
                "key": target_key,
                "label": names[target_key],
                "description": "Mark this combatant as the liar before steel is drawn.",
                "effect": "Correct mark weakens the liar and grants favor. Wrong mark strengthens them and adds contempt.",
                "quote": "Mark carefully. The hall remembers mistakes.",
            }
            for target_key in ("minion1", "minion2", "boss")
        ]
        return {
            "prompt": True,
            "default": liar_target,
            "prompt_text": "One lies. One carries the truth. Mark the liar.",
            "options": options,
            "liar_target": liar_target,
            "witness_target": witness_target,
        }

    if judge.trial_type == "resolve":
        goal = 3 + (local_floor // 3)
        return {
            "prompt": prompt,
            "default": "stand",
            "prompt_text": "Will you endure the gate, or break it before it breaks you?",
            "options": [
                {
                    "key": "stand",
                    "label": "Stand Firm",
                    "description": "Take the weight and outlast the hall.",
                    "effect": "-10% enemy damage. Team sustain while enduring. Survive the required enemy turns to win cleanly.",
                    "quote": "Let the hall spend itself against you.",
                },
                {
                    "key": "rush",
                    "label": "Press Attack",
                    "description": "Crack the line before the pressure settles in.",
                    "effect": "+12% damage. Survival goal is shorter, but enemies hit +8% harder.",
                    "quote": "Then kill fast enough that endurance never matters.",
                },
            ],
            "round_goal": goal,
        }

    if judge.trial_type == "sacrifice":
        return {
            "prompt": True,
            "default": "steel",
            "prompt_text": "Choose what the forge will take from you.",
            "options": [
                {
                    "key": "blood",
                    "label": "Blood Oath",
                    "description": "Trade your life for force.",
                    "effect": "-25% max HP, +25% damage.",
                    "quote": "Bleed first, then swing.",
                },
                {
                    "key": "steel",
                    "label": "Steel Oath",
                    "description": "Shed your guard and punish what touches you.",
                    "effect": "-35% armor, +10 luck, minimum 12% reflection.",
                    "quote": "A missing plate is still a weapon if used well.",
                },
                {
                    "key": "beast",
                    "label": "Beast Oath",
                    "description": "Bind the oath to fang and instinct.",
                    "effect": "Pet: +25% damage and +15% max HP. No pet: +8% damage and +5% armor. All climbers lose 10% armor and 6% max HP.",
                    "quote": "Trust the beast beside you more than the fear behind you.",
                },
            ],
        }

    if judge.trial_type == "balance":
        return {
            "prompt": prompt,
            "default": "shield",
            "prompt_text": "When the chains swing, which side do you feed?",
            "options": [
                {
                    "key": "shield",
                    "label": "Shield",
                    "description": "Open steady and keep the chain from running wild.",
                    "effect": "+10% armor and starts the meter toward restraint. Staying near center earns favor.",
                    "quote": "Stand still enough to choose your violence.",
                },
                {
                    "key": "blade",
                    "label": "Blade",
                    "description": "Lean hard into aggression and master the recoil.",
                    "effect": "+10% damage and starts the meter toward aggression. Overcommitting earns contempt.",
                    "quote": "If you swing wide, the chains will answer.",
                },
            ],
        }

    if judge.trial_type == "ambition":
        return {
            "prompt": True,
            "default": "measured",
            "prompt_text": "How much hunger will you let into the climb?",
            "options": [
                {
                    "key": "measured",
                    "label": "Measured",
                    "description": "Climb without letting hunger take the reins.",
                    "effect": "Kills heal your team. Lower momentum, cleaner verdicts, less contempt risk.",
                    "quote": "Keep the crown in sight. Do not let it into your skull.",
                },
                {
                    "key": "allin",
                    "label": "All-In",
                    "description": "Take the fast path and dare the tower to answer.",
                    "effect": "+5% damage. Kills ramp momentum and extra sigils, but also scrutiny and armor loss.",
                    "quote": "Climb so hard the fall has a price tag.",
                },
            ],
        }

    return {
        "prompt": True,
        "default": "mercy",
        "prompt_text": "The black maul falls soon. Which law do you carry into the last hall?",
        "options": [
            {
                "key": "mercy",
                "label": "Mercy",
                "description": "Carry restraint into the last kill.",
                "effect": "Allows surrender below 22% HP and reduces enemy damage by 5%.",
                "quote": "Do not name yourself merciful unless it costs you blood.",
            },
            {
                "key": "truth",
                "label": "Truth",
                "description": "Anchor the last climb on consistency and exposed lies.",
                "effect": "Weakens boss armor and rewards consistent, accurate play.",
                "quote": "Hold one truth when the floor starts to move.",
            },
            {
                "key": "power",
                "label": "Power",
                "description": "Take raw force and pay for it later.",
                "effect": "+15% damage and extra sigils, but harsher scrutiny as momentum climbs.",
                "quote": "If force is your law, live under it.",
            },
        ],
    }


def _phase_index(local_floor: int) -> int:
    if local_floor <= 4:
        return 0
    if local_floor <= 7:
        return 1
    if local_floor <= 10:
        return 2
    return 3


def _trial_hint(judge: JudgeDefinition, local_floor: int) -> str:
    if judge.trial_type == "mercy":
        return "Pardon lets broken foes kneel. Condemn kills faster but stains the climb."
    if judge.trial_type == "truth":
        return "Mark the liar. Keep the witness alive."
    if judge.trial_type == "resolve":
        return "Some floors are won by surviving, not rushing."
    if judge.trial_type == "sacrifice":
        return "Pick the loss your build can actually afford."
    if judge.trial_type == "balance":
        return "Stay near center. Extremes are punished."
    if judge.trial_type == "ambition":
        return "All-In pays more, but greed strips your guard."
    return "The last hall rewards consistency more than panic."


def _enemy_openings(judge: JudgeDefinition, names: dict[str, str]) -> dict[str, str]:
    if judge.key == "mercy":
        return {
            "minion1": f"{names['minion1']} drops to one knee. 'Will you swing, or stay your hand?'",
            "minion2": f"{names['minion2']} raises a lantern. 'Mercy without strength is begging.'",
            "boss": f"{names['boss']} drags a greatblade. 'Only the strong are allowed to spare.'",
        }
    if judge.key == "truth":
        return {
            "minion1": f"{names['minion1']} tilts a cracked mask. 'Mark wrong and I become truth.'",
            "minion2": f"{names['minion2']} whispers. 'Truth dies if nobody carries it out.'",
            "boss": f"{names['boss']} lowers a spear. 'Find the lie before it finds you.'",
        }
    if judge.key == "resolve":
        return {
            "minion1": f"{names['minion1']} plants a spear. 'You will tire before the gate does.'",
            "minion2": f"{names['minion2']} keeps marching. 'Endurance is paid one hit at a time.'",
            "boss": f"{names['boss']} braces behind stone. 'Outlast the wall, or die against it.'",
        }
    if judge.key == "sacrifice":
        return {
            "minion1": f"{names['minion1']} drags a hot chain. 'Everything worth keeping burns first.'",
            "minion2": f"{names['minion2']} fans the forge. 'Cheap vows make weak steel.'",
            "boss": f"{names['boss']} lifts a hammer. 'Pay, or be broken.'",
        }
    if judge.key == "balance":
        return {
            "minion1": f"{names['minion1']} pulls a chain taut. 'Lean too far and the hall leans back.'",
            "minion2": f"{names['minion2']} studies your footing. 'Excess always rings louder than skill.'",
            "boss": f"{names['boss']} spreads both arms. 'Every overreach has a counterweight.'",
        }
    if judge.key == "ambition":
        return {
            "minion1": f"{names['minion1']} grins. 'Climb harder. The fall is worth seeing.'",
            "minion2": f"{names['minion2']} points upward. 'There is always one more door for the greedy.'",
            "boss": f"{names['boss']} opens the vault. 'Want more? Then survive wanting it.'",
        }
    return {
        "minion1": f"{names['minion1']} sharpens a red blade. 'Every old choice walks with you now.'",
        "minion2": f"{names['minion2']} bows its helm. 'The last law was waiting for you.'",
        "boss": f"{names['boss']} raises the black maul. 'Bring every law you claimed. I will break the false ones.'",
    }


def _build_story_fields(judge: JudgeDefinition, local_floor: int, names: dict[str, str]) -> dict[str, str]:
    phase = _phase_index(local_floor)
    act_label = ACT_LABELS[phase]
    seal_name = f"Seal of {judge.title}"

    if judge.key == "mercy":
        summaries = (
            "Morvane fills the hall with kneeling killers and asks if you know when to stop swinging.",
            "The pleas get uglier here. Some are fear. Some are bait.",
            "Blood darkens the iron floor and every spared life starts to matter more.",
            "Only the strong can spare without being fooled.",
        )
        testimony = (
            f"{names['minion1']} kneels, but keeps one hand near the blade.",
            f"{names['minion2']} watches to see whether mercy makes you soft.",
            f"{names['boss']} has never spared anyone weaker than them.",
            f"The hall wants you cruel or naive. Nothing between.",
        )
        charges = f"{names['boss']} commands the kneeling dead and turns hesitation into a trap."
        commentary = "Thane Blackmaul does not reward softness. Only control."
        victory = (
            "The hall expected slaughter. It got discipline.",
            "The false kneelers fall and the iron lamps burn colder.",
            "Mercy survives deeper into the climb than the hall wanted.",
            "Thane Blackmaul lowers the blade. 'Mercy with teeth. Good.'",
        )
    elif judge.key == "truth":
        summaries = (
            "Duskwarden Vehl floods the crypt with masks, lies, and one truth worth carrying out alive.",
            "A wrong mark feeds the liar. A dead witness feeds the dark.",
            "The deeper vaults echo with half-truths strong enough to kill the careless.",
            "By the end, the truth is visible. Keeping it alive is the hard part.",
        )
        testimony = (
            f"{names['minion1']} speaks too fast and smiles too easily.",
            f"{names['minion2']} guards something more valuable than their life.",
            f"{names['boss']} lets the lies fight for them.",
            f"The crypt echoes with voices that should not agree this well.",
        )
        charges = f"{names['boss']} buries truth beneath masks and dares you to pick wrong."
        commentary = "Vehl never shouts. The crypt does the work for him."
        victory = (
            "The lie breaks first, then the room around it.",
            "A surviving witness slips into the dark with the truth intact.",
            "The echoing lies start tearing each other apart.",
            "Vehl closes his helm. 'You kept the truth alive. Rare.'",
        )
    elif judge.key == "resolve":
        summaries = (
            "Varkhul's gate is a siege with a heartbeat.",
            "Every chamber narrows until only endurance matters.",
            "There is no rest here, only longer pressure.",
            "The last gate is built to make quitting sound smart.",
        )
        testimony = (
            f"{names['minion1']} waits for you to waste yourself on the shield.",
            f"{names['minion2']} counts breaths instead of wounds.",
            f"The stone here remembers stronger climbers breaking.",
            f"{names['boss']} moves like a wall learning how to walk.",
        )
        charges = f"{names['boss']} holds the gate through brute patience and dead weight."
        commentary = "Varkhul respects endurance more than brilliance."
        victory = (
            "The gate spends itself and still you remain.",
            "The hall fails to break you. That is enough here.",
            "You leave the pressure alive, not comfortable.",
            "Varkhul nods once. 'Still standing. Continue.'",
        )
    elif judge.key == "sacrifice":
        summaries = (
            "Caldris begins with easy costs, then asks for something real.",
            "The forge grows hotter and your comfortable options disappear.",
            "There is no rest here. Only time for the metal to glow again.",
            "The last forge wants payment, not symbolism.",
        )
        testimony = (
            f"{names['minion1']} wears fresh brands like honors.",
            f"{names['minion2']} feeds hesitation to the furnace.",
            f"The anvils sing for every climber who tried to leave the forge owing it.",
            f"{names['boss']} waits beside a hammer the size of a coffin lid.",
        )
        charges = f"{names['boss']} taxes every advantage in heat, blood, or iron."
        commentary = "Caldris hates only one thing: unpaid power."
        victory = (
            "The forge takes its due and leaves you sharper.",
            "Sacrifice did not weaken you. The fire hates that.",
            "The anvils ring, but not with your failure.",
            "Caldris turns the hammer. 'A real cost. Good.'",
        )
    elif judge.key == "balance":
        summaries = (
            "Meridrax hangs the hall on chains and punishes every wild correction.",
            "Soon the chains measure greed, panic, and overreach as much as damage.",
            "Each deeper room tempts efficiency into excess.",
            "The last chain wants discipline, not fear or frenzy.",
        )
        testimony = (
            f"{names['minion1']} watches your footing more than your blade.",
            f"{names['minion2']} waits for you to lean too hard.",
            f"The hanging chains sing every time you overcommit.",
            f"{names['boss']} lives for the moment the swing goes too wide.",
        )
        charges = f"{names['boss']} guards a living chain-scale that punishes excess harder than failure."
        commentary = "Meridrax never rushes imbalance. It volunteers."
        victory = (
            "You keep the chains from owning the fight.",
            "The hall hates how cleanly you corrected yourself.",
            "The chains still sway, but they do not drag you with them.",
            "Meridrax levels the beam. 'Controlled. Continue.'",
        )
    elif judge.key == "ambition":
        summaries = (
            "Mordane puts prizes in view and dares you to lose yourself chasing them.",
            "The climb gets louder, richer, and uglier the faster you move.",
            "Every deeper room offers speed and sends the bill later.",
            "The last ascent is pure temptation with teeth.",
        )
        testimony = (
            f"{names['minion1']} laughs like pride hurts more than steel.",
            f"{names['minion2']} points upward and never stops climbing.",
            f"The vault doors keep opening just enough to keep you hungry.",
            f"{names['boss']} celebrates reckless success like a trap already sprung.",
        )
        charges = f"{names['boss']} feeds greed until it starts eating the climber."
        commentary = "Mordane does not need you to fail. He only needs you hungry."
        victory = (
            "You climb higher without letting hunger drive the blade.",
            "The louder the prizes get, the more valuable restraint becomes.",
            "The deeper vaults fail to buy you outright.",
            "Mordane seals the vault. 'Hunger contained. Barely.'",
        )
    else:
        summaries = (
            "Urgrin drags every prior law back into the room with you.",
            "Mercy, lies, hunger, endurance, and sacrifice start colliding.",
            "The inner vault stops testing one thing at a time. It tests whether you were ever consistent.",
            "The final reckoning is the whole climb swinging back at once.",
        )
        testimony = (
            f"{names['minion1']} carries your old choices like trophies.",
            f"{names['minion2']} drags every past mistake back into the dark.",
            f"The black hall listens for contradiction more than fear.",
            f"{names['boss']} lifts the maul and the tower goes dead silent.",
        )
        charges = f"{names['boss']} means to break you with the weight of your own climb."
        commentary = "Urgrin does not care what you claimed. Only what held."
        victory = (
            "The black hall hears your answer and sharpens around it.",
            "Your contradictions begin to die before you do.",
            "The reckoning turns vicious, then simple.",
            "When the maul falls, the tower finally goes quiet.",
        )

    return {
        "act_label": act_label,
        "case_summary": summaries[phase],
        "charges": charges,
        "testimony": testimony[phase],
        "judge_commentary": commentary,
        "mechanic_hint": _trial_hint(judge, local_floor),
        "victory_text": victory[phase],
        "seal_name": seal_name,
        "enemy_openings": _enemy_openings(judge, names),
    }


def build_jury_tower_data() -> dict:
    floors: dict[str, dict] = {}
    judge_summary = []

    for judge_index, judge in enumerate(JUDGES):
        judge_summary.append(
            {
                "key": judge.key,
                "judge_name": judge.judge_name,
                "title": judge.title,
                "seal_name": f"Seal of {judge.title}",
                "start_floor": (judge_index * JURY_SEGMENT_LENGTH) + 1,
                "end_floor": (judge_index + 1) * JURY_SEGMENT_LENGTH,
                "color": judge.color,
            }
        )

        for local_floor in range(1, JURY_SEGMENT_LENGTH + 1):
            floor = (judge_index * JURY_SEGMENT_LENGTH) + local_floor
            minion1_name = judge.minion_one[(local_floor - 1) % len(judge.minion_one)]
            minion2_name = judge.minion_two[(local_floor - 1) % len(judge.minion_two)]
            if local_floor == JURY_SEGMENT_LENGTH:
                boss_name = judge.bosses[-1]
            elif local_floor >= 8:
                boss_name = judge.bosses[1]
            else:
                boss_name = judge.bosses[0]

            names = {
                "minion1": minion1_name,
                "minion2": minion2_name,
                "boss": boss_name,
            }

            choice = _build_choice(judge, local_floor, names, floor)
            story = _build_story_fields(judge, local_floor, names)
            boss_floor = local_floor == JURY_SEGMENT_LENGTH
            checkpoint = boss_floor
            title = f"{judge.chamber_prefix} {local_floor}"
            reward_writs = 8 + (judge_index * 2) + local_floor
            enemy_scale_profiles = {
                "minion1": _build_enemy_scale_profile(judge, judge_index, local_floor, "minion1"),
                "minion2": _build_enemy_scale_profile(judge, judge_index, local_floor, "minion2"),
                "boss": _build_enemy_scale_profile(judge, judge_index, local_floor, "boss"),
            }

            floors[str(floor)] = {
                "floor": floor,
                "judge_index": judge_index,
                "judge_key": judge.key,
                "judge_name": judge.judge_name,
                "judge_title": judge.title,
                "trial_type": judge.trial_type,
                "title": title,
                "intro": judge.intro_line,
                "color": judge.color,
                "element": judge.element,
                "choice": choice,
                "checkpoint": checkpoint,
                "boss_floor": boss_floor,
                "writs_reward": reward_writs,
                "boss_reward": None,
                "enemy_names": names,
                **story,
                "enemies": [
                    {
                        "key": "minion1",
                        "name": minion1_name,
                        "element": judge.element,
                        "scale": enemy_scale_profiles["minion1"],
                    },
                    {
                        "key": "minion2",
                        "name": minion2_name,
                        "element": judge.element,
                        "scale": enemy_scale_profiles["minion2"],
                    },
                    {
                        "key": "boss",
                        "name": boss_name,
                        "element": judge.element,
                        "scale": enemy_scale_profiles["boss"],
                    },
                ],
            }
            if boss_floor:
                boss_reward = _boss_reward_for_judge(judge_index, 1)
                if floor != JURY_TOWER_FLOOR_COUNT:
                    boss_reward["reset_potion"] = 0
                floors[str(floor)]["boss_reward"] = boss_reward

    return {
        "floor_count": JURY_TOWER_FLOOR_COUNT,
        "segment_length": JURY_SEGMENT_LENGTH,
        "judges": judge_summary,
        "floors": floors,
    }
