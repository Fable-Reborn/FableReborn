from __future__ import annotations

from dataclasses import dataclass


JURY_TOWER_FLOOR_COUNT = 77
JURY_SEGMENT_LENGTH = 11


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
        judge_name="Aurelia",
        title="Judge of Mercy",
        element="Light",
        color=0xD7C178,
        chamber_prefix="Hall of Mercy",
        minion_one=("Repentant Squire", "Pleading Duelist", "Weeping Standard-Bearer"),
        minion_two=("Ash Bailiff", "Lantern Penitent", "Soft-Voiced Headsman"),
        bosses=("Magister of Clemency", "The Last Pardon", "Absolver Halcyon"),
        trial_type="mercy",
        intro_line="Mercy is not weakness. It is strength disciplined by conscience.",
    ),
    JudgeDefinition(
        key="truth",
        judge_name="Veritus",
        title="Judge of Truth",
        element="Wind",
        color=0x70B4E4,
        chamber_prefix="Gallery of Testimony",
        minion_one=("False Witness", "Paper-Knife Clerk", "Echo Examiner"),
        minion_two=("Veiled Informant", "Court Scribe", "Glass-Eyed Witness"),
        bosses=("Grand Cross-Examiner", "The Perjured Crown", "Archivist Null"),
        trial_type="truth",
        intro_line="Truth is not loud. It survives scrutiny.",
    ),
    JudgeDefinition(
        key="resolve",
        judge_name="Bastion",
        title="Judge of Resolve",
        element="Earth",
        color=0x9C8F73,
        chamber_prefix="Ward of Endurance",
        minion_one=("Stoneworn Guard", "Siege Bailiff", "Unbroken Veteran"),
        minion_two=("Trial Hound", "Iron Sentinel", "Oath-Bound Pike"),
        bosses=("The Long March", "Citadel Warden", "Last Stand of Varr"),
        trial_type="resolve",
        intro_line="Resolve is proven when the verdict takes longer than your patience.",
    ),
    JudgeDefinition(
        key="sacrifice",
        judge_name="Caldris",
        title="Judge of Sacrifice",
        element="Fire",
        color=0xD96B39,
        chamber_prefix="Forge of Oaths",
        minion_one=("Ember Penitent", "Brand Knight", "Ashen Forgebearer"),
        minion_two=("Cinder Collector", "Scorch Bailiff", "Oath Furnace"),
        bosses=("The Tithe Engine", "High Forger Calvein", "Burnished Adjudicator"),
        trial_type="sacrifice",
        intro_line="Every oath costs something. Weak vows are free.",
    ),
    JudgeDefinition(
        key="balance",
        judge_name="Equa",
        title="Judge of Balance",
        element="Water",
        color=0x5EA8D1,
        chamber_prefix="Scales of Accord",
        minion_one=("Chainbearer", "Counterweight Adept", "Measured Spear"),
        minion_two=("Scale Keeper", "Ledger Knight", "Mirror Shield"),
        bosses=("Twin Pan Executor", "The Counterpoise", "Lady Meridian"),
        trial_type="balance",
        intro_line="To lean too far in any direction is to become predictable.",
    ),
    JudgeDefinition(
        key="ambition",
        judge_name="Mordane",
        title="Judge of Ambition",
        element="Dark",
        color=0x9655B6,
        chamber_prefix="Ascendant Tribunal",
        minion_one=("Laureled Reaver", "Greed Knight", "Crown-Thief"),
        minion_two=("Triumph Hound", "Glory Collector", "Vault Breaker"),
        bosses=("The Climbing King", "Vault of Desire", "Sovereign of More"),
        trial_type="ambition",
        intro_line="Ambition is admirable until it becomes appetite.",
    ),
    JudgeDefinition(
        key="sentence",
        judge_name="Septimus",
        title="Judge of Final Sentence",
        element="Corrupted",
        color=0xC0392B,
        chamber_prefix="Seat of Final Sentence",
        minion_one=("Red Clerk", "Final Bailiff", "Sentence Hound"),
        minion_two=("Doom Herald", "Black-Robed Jury", "Gavel Revenant"),
        bosses=("The Sevenfold Bench", "Executor Prime", "High Judge Septimus"),
        trial_type="sentence",
        intro_line="A final sentence remembers every mercy, lie, oath, excess, and compromise before it falls.",
    ),
)


ACT_LABELS = ("Opening Arguments", "Cross Examination", "Chamber Recess", "Final Verdict")
JURY_JUDGE_BASE_SCALES = (0.72, 0.82, 0.92, 1.04, 1.18, 1.32, 1.48)
JURY_ROLE_SCALE_TEMPLATES = {
    "minion1": {
        "hp_multiplier": 1.55,
        "defense_ratio": 0.10,
        "attack_armor_ratio": 1.00,
        "attack_hp_ratio": 0.04,
    },
    "minion2": {
        "hp_multiplier": 2.05,
        "defense_ratio": 0.14,
        "attack_armor_ratio": 1.03,
        "attack_hp_ratio": 0.055,
    },
    "boss": {
        "hp_multiplier": 3.60,
        "defense_ratio": 0.18,
        "attack_armor_ratio": 1.06,
        "attack_hp_ratio": 0.08,
    },
}
JURY_JUDGE_SCALE_BIASES = {
    "mercy": {
        "hp_multiplier": 1.00,
        "defense_ratio": 0.92,
        "attack_armor_ratio": 0.95,
        "attack_hp_ratio": 0.85,
    },
    "truth": {
        "hp_multiplier": 0.96,
        "defense_ratio": 1.00,
        "attack_armor_ratio": 0.98,
        "attack_hp_ratio": 0.95,
    },
    "resolve": {
        "hp_multiplier": 1.25,
        "defense_ratio": 1.18,
        "attack_armor_ratio": 0.97,
        "attack_hp_ratio": 0.95,
    },
    "sacrifice": {
        "hp_multiplier": 0.95,
        "defense_ratio": 0.92,
        "attack_armor_ratio": 1.04,
        "attack_hp_ratio": 1.10,
    },
    "balance": {
        "hp_multiplier": 1.05,
        "defense_ratio": 1.04,
        "attack_armor_ratio": 1.00,
        "attack_hp_ratio": 1.00,
    },
    "ambition": {
        "hp_multiplier": 1.00,
        "defense_ratio": 0.96,
        "attack_armor_ratio": 1.08,
        "attack_hp_ratio": 1.12,
    },
    "sentence": {
        "hp_multiplier": 1.20,
        "defense_ratio": 1.12,
        "attack_armor_ratio": 1.10,
        "attack_hp_ratio": 1.15,
    },
}


def _boss_reward_for_judge(judge_index: int) -> dict:
    crate_cycle = ("common", "uncommon", "rare", "rare", "magic", "fortune", "legendary")
    money_base = (12000, 18000, 25000, 35000, 45000, 65000, 90000)
    writs_base = (24, 30, 38, 48, 60, 75, 100)
    return {
        "crate_type": crate_cycle[judge_index],
        "money": money_base[judge_index],
        "appeals": 1,
        "writs": writs_base[judge_index],
        "reset_potion": 1 if judge_index == len(JUDGES) - 1 else 0,
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
        * (1 + ((local_floor - 1) * 0.035))
        * (1.08 if role == "boss" else 1.03 if role == "minion2" else 1.0)
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
            "prompt_text": "Will you spare the weak when they yield, or condemn every foe who kneels?",
            "options": [
                {
                    "key": "pardon",
                    "label": "Pardon",
                    "description": "Raise surrender chances and turn mercy into favor.",
                },
                {
                    "key": "condemn",
                    "label": "Condemn",
                    "description": "Hit harder, but every ruthless finish adds contempt.",
                },
            ],
        }

    if judge.trial_type == "truth":
        liar_target = ("minion1", "minion2", "boss")[floor % 3]
        witness_target = ("minion2", "boss", "minion1")[floor % 3]
        options = [
            {
                "key": target_key,
                "label": names[target_key],
                "description": "Accuse this combatant before testimony begins.",
            }
            for target_key in ("minion1", "minion2", "boss")
        ]
        return {
            "prompt": True,
            "default": liar_target,
            "prompt_text": "One foe lies, one conceals the truth, and one profits from both. Whom do you accuse?",
            "options": options,
            "liar_target": liar_target,
            "witness_target": witness_target,
        }

    if judge.trial_type == "resolve":
        goal = 3 + (local_floor // 3)
        return {
            "prompt": prompt,
            "default": "stand",
            "prompt_text": "Will you stand and weather the case, or try to break it before it breaks you?",
            "options": [
                {
                    "key": "stand",
                    "label": "Stand Firm",
                    "description": "Gain protection and healing while surviving the trial.",
                },
                {
                    "key": "rush",
                    "label": "Press Attack",
                    "description": "Gain damage and shorten the trial at the cost of safety.",
                },
            ],
            "round_goal": goal,
        }

    if judge.trial_type == "sacrifice":
        return {
            "prompt": True,
            "default": "steel",
            "prompt_text": "Choose the oath you will give up before the forge opens.",
            "options": [
                {
                    "key": "blood",
                    "label": "Blood Oath",
                    "description": "Lose max HP for a heavy damage bonus.",
                },
                {
                    "key": "steel",
                    "label": "Steel Oath",
                    "description": "Lose armor for better luck and reflected punishment.",
                },
                {
                    "key": "beast",
                    "label": "Beast Oath",
                    "description": "Empower your companion, or gain a lighter solo bonus.",
                },
            ],
        }

    if judge.trial_type == "balance":
        return {
            "prompt": prompt,
            "default": "shield",
            "prompt_text": "Which side of the scale will you favor when the chamber tips?",
            "options": [
                {
                    "key": "shield",
                    "label": "Shield",
                    "description": "Begin guarded and pull the scale toward restraint.",
                },
                {
                    "key": "blade",
                    "label": "Blade",
                    "description": "Begin aggressive and chase a faster clear.",
                },
            ],
        }

    if judge.trial_type == "ambition":
        return {
            "prompt": True,
            "default": "measured",
            "prompt_text": "How hungry will you allow yourself to become?",
            "options": [
                {
                    "key": "measured",
                    "label": "Measured",
                    "description": "Keep ambition contained and earn cleaner verdicts.",
                },
                {
                    "key": "allin",
                    "label": "All-In",
                    "description": "Gain larger kill spikes and payouts, but risk contempt.",
                },
            ],
        }

    return {
        "prompt": True,
        "default": "mercy",
        "prompt_text": "The final bench offers no innocence, only philosophy. Which principle guides your sentence?",
        "options": [
            {
                "key": "mercy",
                "label": "Mercy",
                "description": "Favor pardons, stability, and clean verdicts.",
            },
            {
                "key": "truth",
                "label": "Truth",
                "description": "Expose the right target and punish deception.",
            },
            {
                "key": "power",
                "label": "Power",
                "description": "Claim raw force and accept harsher scrutiny.",
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
        if local_floor >= 8:
            return "Pardoned defendants still count as wins. The court cares about how the case ends, not how loudly it ends."
        return "Under Pardon, wounded defendants can yield instead of dying. Condemn gives speed but every ruthless finish is remembered."
    if judge.trial_type == "truth":
        return "Accusing the liar weakens the case against you. Letting the witness escape alive earns additional favor."
    if judge.trial_type == "resolve":
        return "You can win this case by surviving the required number of enemy turns. Fast clears are not always the cleanest clears."
    if judge.trial_type == "sacrifice":
        return "Pick the oath that best fits your build. The safest-looking oath is not always the most efficient."
    if judge.trial_type == "balance":
        return "The Scale Meter rewards measured play. If you go too hard in one direction, the bench calls it imbalance."
    if judge.trial_type == "ambition":
        return "All-In scales harder with each kill, but unchecked momentum turns into contempt."
    return "Your chosen principle is judged against everything you do afterward. Consistency matters more than raw speed."


def _enemy_openings(judge: JudgeDefinition, names: dict[str, str]) -> dict[str, str]:
    if judge.key == "mercy":
        return {
            "minion1": f"{names['minion1']} drops to one knee. 'Will the court hear me before the blade?'",
            "minion2": f"{names['minion2']} lifts a lantern. 'Mercy for me, punishment for you. That is how these halls work.'",
            "boss": f"{names['boss']} smiles thinly. 'Mercy is a privilege I issue, not a law I obey.'",
        }
    if judge.key == "truth":
        return {
            "minion1": f"{names['minion1']} spreads their hands. 'I only repeat what benefits the room.'",
            "minion2": f"{names['minion2']} whispers behind a veil. 'Truth survives only if someone bothers to protect it.'",
            "boss": f"{names['boss']} taps the witness rail. 'Facts are fragile. Let us see whether you can keep them alive.'",
        }
    if judge.key == "resolve":
        return {
            "minion1": f"{names['minion1']} plants a spear. 'This hall does not break quickly, and neither do I.'",
            "minion2": f"{names['minion2']} circles slowly. 'Endurance is a sentence, not a virtue, until you survive it.'",
            "boss": f"{names['boss']} braces behind stone. 'If you want victory, prove you can outlast the room itself.'",
        }
    if judge.key == "sacrifice":
        return {
            "minion1": f"{names['minion1']} drags a heated chain. 'Everything valuable burns before it shines.'",
            "minion2": f"{names['minion2']} fans the forge. 'The oath you keep is weaker than the one you surrendered.'",
            "boss": f"{names['boss']} raises a hammer. 'Offer something real, or leave with nothing.'",
        }
    if judge.key == "balance":
        return {
            "minion1": f"{names['minion1']} adjusts a hanging weight. 'One wrong lean and the room chooses for you.'",
            "minion2": f"{names['minion2']} studies your stance. 'Excess is merely imbalance wearing confidence.'",
            "boss": f"{names['boss']} extends both hands. 'The scale records every overreach.'",
        }
    if judge.key == "ambition":
        return {
            "minion1": f"{names['minion1']} grins. 'Climb faster. The fall is better from higher up.'",
            "minion2": f"{names['minion2']} points upward. 'There is always one more prize if you are willing to deserve less.'",
            "boss": f"{names['boss']} opens the vault doors. 'Want more? Then prove you can stop wanting.'",
        }
    return {
        "minion1": f"{names['minion1']} sharpens a seal-stamped blade. 'Every prior choice is evidence now.'",
        "minion2": f"{names['minion2']} bows to the bench. 'The final sentence was written before you reached this hall.'",
        "boss": f"{names['boss']} lifts the gavel. 'Bring every principle you claimed. I will weigh them all.'",
    }


def _build_story_fields(judge: JudgeDefinition, local_floor: int, names: dict[str, str]) -> dict[str, str]:
    phase = _phase_index(local_floor)
    act_label = ACT_LABELS[phase]
    seal_name = f"Seal of {judge.title.replace('Judge of ', '')}"

    if judge.key == "mercy":
        summaries = (
            "Aurelia begins with defendants who know how to sound pitiful. The room is built to make cruelty feel efficient.",
            "The pleas turn manipulative. Surrender, guilt, and cowardice begin wearing the same face.",
            "Recess opens with pardons sold like bribes. The chamber wants you to confuse kindness with weakness.",
            "Aurelia now asks the only question left: can you spare the innocent without letting the cruel hide behind them?",
        )
        testimony = (
            f"{names['minion1']} claims they were ordered here and only want to survive the hearing.",
            f"{names['minion2']} insists mercy should belong to those strong enough to seize it.",
            f"The gallery murmurs that {names['boss']} has never once offered the pardon they demand from others.",
            f"Even the candles dim when {names['boss']} speaks, as if the hall itself expects a false mercy.",
        )
        charges = f"{names['boss']} presides over a circle of defendants who weaponize surrender and dare you to become judge, executioner, and fool at once."
        commentary = "Aurelia's scales glow warm, but they do not forgive thoughtlessness."
        victory = (
            "You leave the first mercy cases with your conscience intact, and the chamber hates you for it.",
            "The false penitents break, and the judge's lanterns burn steadier in your wake.",
            "Mercy survives recess. That alone is enough to unsettle the entire gallery.",
            "Aurelia lowers her gaze. 'Compassion with teeth. Acceptable.'",
        )
    elif judge.key == "truth":
        summaries = (
            "Veritus opens with contradictory statements, forged records, and witnesses who know exactly how much truth the room can survive.",
            "The testimony sharpens. Every wrong accusation now strengthens the liar and endangers the quiet witness.",
            "During recess the chamber floods with evidence, most of it beautifully fabricated.",
            "By the final hearing, truth is no longer hidden. It is simply expensive to preserve.",
        )
        testimony = (
            f"{names['minion1']} speaks first, too quickly, with details nobody asked for.",
            f"{names['minion2']} avoids your eye line, guarding something more valuable than their life.",
            f"The clerk rails fill with forged affidavits implicating everyone except {names['boss']}.",
            f"When {names['boss']} laughs, half the archive rearranges itself to support them.",
        )
        charges = f"{names['boss']} has built a profitable courtroom where lies hire guards and witnesses die of administrative error."
        commentary = "Veritus never raises his voice. In this hall, silence does more damage than shouting."
        victory = (
            "Your accusation lands cleanly and the record finally stops shifting under your feet.",
            "A few surviving truths escape the chamber, which is more than most advocates manage.",
            "By recess the paper storm tears itself apart around the facts you kept alive.",
            "Veritus closes the archive. 'You did not merely find truth. You paid to keep it breathing.'",
        )
    elif judge.key == "resolve":
        summaries = (
            "Bastion's ward begins as a siege. The room cares nothing for flair and everything for what remains standing after impact.",
            "Every hallway narrows. Attrition becomes the argument and exhaustion becomes the prosecutor.",
            "Recess arrives without comfort. It is only a longer stretch of pressure wearing a different name.",
            "The final ward is not trying to kill you quickly. It is trying to convince you that continuing is irrational.",
        )
        testimony = (
            f"{names['minion1']} strikes a shield wall and waits for you to tire yourself out on it.",
            f"{names['minion2']} paces in perfect rhythm, counting breaths instead of wounds.",
            f"The stones themselves pulse with the confidence of structures that have buried stronger challengers.",
            f"{names['boss']} steps forward like a fortress deciding to walk.",
        )
        charges = f"{names['boss']} commands a defensive machine designed to make surrender look practical."
        commentary = "Bastion respects persistence more than brilliance. The chamber knows it."
        victory = (
            "You outlast the first press of the ward and the silence afterward feels earned.",
            "The hall fails to crack you, which in Bastion's court is louder than any triumph.",
            "Recess does not refresh you, but it does prove you are still here.",
            "Bastion nods once. 'Endurance is proof. Continue.'",
        )
    elif judge.key == "sacrifice":
        summaries = (
            "Caldris opens the forge with easy bargains. The first floors tempt you to sacrifice what you can already afford to lose.",
            "Soon the room starts asking for meaningful pieces of your comfort, defense, and certainty.",
            "Recess here is only time enough for metal to cool before it is reheated.",
            "The final forge stops pretending to be ceremonial. It wants tribute, not symbolism.",
        )
        testimony = (
            f"{names['minion1']} wears fresh brands like medals and stares at what you have not surrendered yet.",
            f"{names['minion2']} feeds your hesitation to the furnace and watches it burn brighter.",
            f"The anvils ring with the names of champions who tried to win without paying anything real.",
            f"{names['boss']} sets a hammer on the bench as though inviting you to strike your own bargain.",
        )
        charges = f"{names['boss']} oversees a court where every advantage is taxed and every victory receipt is written in ash."
        commentary = "Caldris does not hate greed. He only hates unpaid greed."
        victory = (
            "Your first oath leaves a mark, but the forge recognizes that you actually meant it.",
            "The chamber cools around you for a moment, annoyed that sacrifice made you sharper instead of smaller.",
            "Even during recess the anvils keep singing, but none of them sing your failure.",
            "Caldris turns the hammer face down. 'A meaningful cost. Finally.'",
        )
    elif judge.key == "balance":
        summaries = (
            "Equa begins with symmetrical rooms and asymmetrical consequences. Every strong choice here tries to become an overcorrection.",
            "Soon the scale starts recording not just damage dealt, but appetite, panic, and overconfidence.",
            "Recess brings mirrored chambers where every efficient plan risks becoming excess.",
            "The final scales demand discipline under pressure, not merely caution or aggression in isolation.",
        )
        testimony = (
            f"{names['minion1']} studies your footing as though they can see the direction of your next mistake.",
            f"{names['minion2']} smiles when you lean too far, because the scale always collects interest.",
            f"The chains above the chamber ring differently depending on how greedy your last turn was.",
            f"{names['boss']} waits for imbalance the way sharks wait for blood.",
        )
        charges = f"{names['boss']} guards a living balance that punishes excess more consistently than failure."
        commentary = "Equa is patient. She never hurries imbalance because she knows it volunteers."
        victory = (
            "You keep the scales from tilting hard enough to own you, and that alone feels like stealing.",
            "The chamber resents how calmly you corrected your own momentum.",
            "Recess ends with the chains still swaying, but not in your favor or against it.",
            "Equa taps the beam level. 'Acceptable. You were neither timid nor gluttonous for too long.'",
        )
    elif judge.key == "ambition":
        summaries = (
            "Mordane opens with rewards in plain sight. Every floor after the first teaches that appetite can look exactly like confidence.",
            "The climb grows richer and louder. The tower wants you to mistake acceleration for mastery.",
            "Recess is a marketplace of trophies where every shortcut is offered with a smile and a hidden invoice.",
            "The last ascent is pure temptation: faster kills, bigger payouts, and a judge who wants to see whether you can stop.",
        )
        testimony = (
            f"{names['minion1']} laughs as if losing to them would hurt your pride more than your body.",
            f"{names['minion2']} points to a higher balcony. 'There is always one more room worth betraying yourself for.'",
            f"The vault doors keep opening just enough to show you prizes, never enough to let you rest.",
            f"{names['boss']} applauds every reckless success like a patron funding your eventual collapse.",
        )
        charges = f"{names['boss']} runs a tribunal where greed is not hidden. It is celebrated until it becomes legally inconvenient."
        commentary = "Mordane does not need you to fail. He only needs you to enjoy the slide."
        victory = (
            "You leave the early climbs with your hunger intact, which is not the same thing as letting it drive.",
            "The brighter the rewards become, the more impressive restraint starts to look.",
            "Recess fails to buy you. Mordane notices and hates that he notices.",
            "The vault seals behind you. 'Ambition contained,' the judge says, sounding almost offended.",
        )
    else:
        summaries = (
            "Septimus begins with an impossible promise: every prior principle will be remembered and none of them will be allowed to contradict each other for free.",
            "The chamber now mixes mercy with deceit, sacrifice with greed, and balance with attrition until your earlier claims start colliding.",
            "Recess becomes deliberation. The hall is no longer testing one virtue at a time, only your coherence under all of them.",
            "The final sentence is not a single fight. It is the total weight of every philosophy you brought this far.",
        )
        testimony = (
            f"{names['minion1']} presents a red-sealed ledger full of your prior rulings and waits for inconsistency.",
            f"{names['minion2']} calls each old verdict into evidence, line by line.",
            f"The black-robed jury behind the rail murmurs whenever your present stance disagrees with your earlier courage.",
            f"{names['boss']} lifts the gavel and the whole tower goes silent enough to hear your mistakes breathing.",
        )
        charges = f"{names['boss']} prosecutes you with your own history and intends to prove that your principles only lasted while they were convenient."
        commentary = "Septimus does not ask who you are. He compares your answer against seventy-six floors of evidence."
        victory = (
            "The final bench hears your first argument and sharpens its knives on it.",
            "Contradictions start collapsing under their own weight, leaving only the positions you can actually defend.",
            "Deliberation turns vicious. The room is no longer debating your strength, only your consistency.",
            "When the final blow lands, the entire bench sounds less angry than disappointed you survived it.",
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
                "seal_name": f"Seal of {judge.title.replace('Judge of ', '')}",
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
                "boss_reward": _boss_reward_for_judge(judge_index) if boss_floor else None,
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

    return {
        "floor_count": JURY_TOWER_FLOOR_COUNT,
        "segment_length": JURY_SEGMENT_LENGTH,
        "judges": judge_summary,
        "floors": floors,
    }
