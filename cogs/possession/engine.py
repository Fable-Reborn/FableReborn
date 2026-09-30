"""Discord-independent rules for the GM Possession event.

A Game Master drives a possessed vessel while raiders pick one action per
round. Both sides choose simultaneously; spirits and raiders resolve first,
then the vessel. Raiders win by destroying the vessel or completing the
Severance rite; the vessel wins by wiping the raid or outlasting the round
limit.

Raiders can guard or mend an ally, and each has one class signature per
fight. The fallen return as spirits with weak actions of their own. The
vessel's Cataclysm gathers for a turn before it lands, and the vessel grows
more dangerous (and more exposed) as it passes each phase threshold.
"""

import math
import random
from dataclasses import dataclass, field

VESSEL_ARMOR = 200
DEFENSE_SCALE = 1_500
VESSEL_STRIKE_ROUNDS = 8      # Turns an all-Strike raid needs to fell an auto-scaled vessel.
VESSEL_HIT_SHARE = 0.18       # A base hit takes this share of an average raider's health.
MAX_ROUNDS = 15
MIN_RAIDERS = 3
MAX_RAIDERS = 25  # Discord select menus hold 25 options.

DREAD_PER_ROUND = 20
DREAD_PER_KILL = 15
DREAD_MAX = 100

MEND_RATIO = 0.25
GUARD_FACTOR = 0.5
WARD_FACTOR = 0.5
RITE_ROUNDS = 7               # Uninterrupted turns of a full circle needed to exorcise.
RITE_GRIP_MAX = 0.4           # A complete Severance would add +40% strike damage.
FOCUS_PARTY = 6               # Single-target powers scale with party size around this.
FOCUS_BOUNDS = (0.75, 2.5)

INTERRUPT_SHARE = 0.10        # Damage (share of max health) in the release turn that breaks a Cataclysm.
PHASE_THRESHOLDS = (2 / 3, 1 / 3)  # Health shares that begin phases II and III.
PHASE3_ATTACK_BONUS = 0.25
PHASE3_DREAD_PER_ROUND = 30
EXECUTE_THRESHOLD = 0.25

HAUNT_DREAD = 5
ECHOES_PER_RITE = 2

MARK_BONUS = 0.30
MARK_TURNS = 2
SUNDER_BONUS = 0.10
RESURRECT_RATIO = 0.40
BALLAD_RATIO = 0.15
PILFER_DREAD = 40
UNBROKEN_RITE = 2
HARVEST_PER_FALLEN = 0.5
HARVEST_MAX = 3.0

PLAYER_ACTIONS = ("strike", "guard", "mend", "rite", "signature")
SPIRIT_ACTIONS = ("haunt", "echo", "foresee")
DEFAULT_ACTION = "strike"

ABILITIES = {
    "smite": {"target": True, "cooldown": 0, "multiplier": 2.2},
    "sweep": {"target": False, "cooldown": 1, "multiplier": 0.8},
    "siphon": {"target": True, "cooldown": 2, "multiplier": 1.3, "heal_ratio": 1.5},
    "dominate": {"target": True, "cooldown": 3},
    "ward": {"target": False, "cooldown": 3},
    "execute": {"target": True, "cooldown": 3, "multiplier": 1.8, "phase": 3},
    "cataclysm": {"target": False, "cooldown": 0, "multiplier": 1.8, "dread_cost": DREAD_MAX},
}
SINGLE_TARGET_HITS = ("smite", "siphon", "execute")
CIRCLE_BREAKERS = ("smite", "siphon", "execute", "cataclysm")

# Signature moves, once per fight. "target" is None, "ally" (a living raider)
# or "fallen" (a dead one).
SIGNATURES = {
    "rampage": {"target": None, "factor": 2.5},
    "bulwark": {"target": None},
    "pilfer": {"target": None},
    "arcane_surge": {"target": None, "factor": 1.5, "ignore_armor": True, "ignore_ward": True},
    "paragons_will": {"target": None, "factor": 1.0},
    "resurrection": {"target": "fallen"},
    "hunters_mark": {"target": None},
    "sunder": {"target": None, "factor": 1.5},
    "unbroken_circle": {"target": None},
    "harvest": {"target": None},
    "ballad": {"target": None},
    "pack_hunt": {"target": None, "factor": 2.0, "ignore_ward": True},
    "gift": {"target": "ally"},
    "last_stand": {"target": None, "factor": 2.0},
}
CLASS_SIGNATURES = {
    "Warrior": "rampage",
    "Tank": "bulwark",
    "Thief": "pilfer",
    "Mage": "arcane_surge",
    "Paragon": "paragons_will",
    "Paladin": "resurrection",
    "Ranger": "hunters_mark",
    "Raider": "sunder",
    "Ritualist": "unbroken_circle",
    "Reaper": "harvest",
    "Bard": "ballad",
    "Beastmaster": "pack_hunt",
    "SantasHelper": "gift",
}
DEFAULT_SIGNATURE = "last_stand"


def signature_for(class_lines):
    """The signature of the first class line that has one."""
    for line in class_lines or ():
        if line in CLASS_SIGNATURES:
            return CLASS_SIGNATURES[line]
    return DEFAULT_SIGNATURE


def incoming_damage(attack, armor):
    """Diminishing mitigation: 1,500 armor halves damage, never grants immunity."""
    return max(1.0, float(attack) * DEFENSE_SCALE / (DEFENSE_SCALE + max(0.0, float(armor))))


def rite_goal(raider_count):
    return rite_capacity(raider_count) * RITE_ROUNDS


def rite_capacity(raider_count):
    """Voices the circle can hold per round; forces a mix of rite and steel."""
    return max(1, math.ceil(raider_count / 4))


def focus_multiplier(raider_count):
    """Single-target powers hit harder against larger raids."""
    low, high = FOCUS_BOUNDS
    return min(high, max(low, raider_count / FOCUS_PARTY))


def sweep_target_count(living_count):
    return min(living_count, max(2, math.ceil(living_count / 3)))


@dataclass
class Raider:
    user_id: int
    name: str
    hp: float
    max_hp: float
    damage: float
    armor: float
    signature: str = DEFAULT_SIGNATURE
    signature_used: bool = False
    dealt: float = 0.0
    healed: float = 0.0
    absorbed: float = 0.0
    rites: int = 0
    revives: int = 0
    spirit_acts: int = 0

    @property
    def alive(self):
        return self.hp > 0

    @property
    def hp_ratio(self):
        return self.hp / self.max_hp if self.max_hp else 0.0

    def valor(self, vessel_attack):
        return (
            self.dealt + self.healed + self.absorbed
            + self.rites * vessel_attack * 2
            + self.revives * vessel_attack * 3
            + self.spirit_acts * vessel_attack * 0.5
        )


def scaled_vessel_hp(raiders):
    return VESSEL_STRIKE_ROUNDS * sum(max(1.0, r.damage - VESSEL_ARMOR) for r in raiders)


def scaled_vessel_attack(raiders):
    """Pick an attack that hurts an average raider by VESSEL_HIT_SHARE after armor."""
    avg_hp = sum(r.max_hp for r in raiders) / len(raiders)
    avg_armor = sum(max(0.0, r.armor) for r in raiders) / len(raiders)
    return VESSEL_HIT_SHARE * avg_hp * (DEFENSE_SCALE + avg_armor) / DEFENSE_SCALE


@dataclass
class Vessel:
    hp: float
    max_hp: float
    attack: float
    armor: float = VESSEL_ARMOR
    dread: int = 0
    cooldowns: dict = field(default_factory=dict)


@dataclass
class RoundReport:
    round_no: int
    ability: str
    target_id: int | None = None
    releasing: bool = False                           # A gathered Cataclysm was due this turn.
    charge_started: bool = False                      # The vessel began gathering a Cataclysm.
    interrupted: bool = False                         # The gathered Cataclysm was broken.
    strikes: list = field(default_factory=list)       # (user_id, damage, signature key or None)
    guards: list = field(default_factory=list)        # (guard_id, protected_id)
    mends: list = field(default_factory=list)         # (healer_id, target_id, amount)
    signatures: list = field(default_factory=list)    # (user_id, key, target_id, amount)
    rite_gain: int = 0
    rite_unheard: int = 0
    bonus_rite: int = 0                               # Severance from signatures, beyond the circle.
    echo_gain: int = 0
    rite_broken: list = field(default_factory=list)   # chanters whose voice the vessel broke
    circle_sealed: bool = False
    haunts: int = 0
    haunt_drain: int = 0
    echoes: int = 0
    pilfered: int = 0
    dominated: dict | None = None                     # {"target_id", "action", ...}
    ward: bool = False
    hits: list = field(default_factory=list)          # (user_id, damage, guarded, shielded_id or None)
    executed: list = field(default_factory=list)      # user_id
    vessel_healed: float = 0.0
    deaths: list = field(default_factory=list)        # user_id
    revived: list = field(default_factory=list)       # user_id
    phase_change: int | None = None

    @property
    def total_strike(self):
        return sum(amount for _uid, amount, _tag in self.strikes)

    @property
    def total_rite(self):
        return self.rite_gain + self.bonus_rite + self.echo_gain


class Encounter:
    def __init__(self, raiders, hp_per_raider=None, *,
                 max_rounds=MAX_ROUNDS, cataclysm_variance=None, rng=None):
        """Vessel health scales to the raid's damage unless hp_per_raider is given."""
        if not raiders:
            raise ValueError("A possession needs at least one raider.")
        self.rng = rng or random.Random()
        self.raiders = {raider.user_id: raider for raider in raiders}
        hp = float(hp_per_raider * len(raiders)) if hp_per_raider else scaled_vessel_hp(raiders)
        self.vessel = Vessel(hp=hp, max_hp=hp, attack=scaled_vessel_attack(raiders))
        self.starting_count = len(raiders)
        self.rite = 0
        self.rite_goal = rite_goal(len(raiders))
        self.base_capacity = rite_capacity(len(raiders))
        self.max_rounds = max_rounds
        self.cataclysm_variance = cataclysm_variance
        self.round_no = 0
        self.outcome = None  # "slain", "exorcised", "wiped", "withdrawn"
        self.last_actions = {}
        self.phase = 1
        self.charging = False
        self.mark_turns = 0
        self.vulnerability = 0.0
        self.echo_carry = 0
        self._dead = set()

    # ---- queries -------------------------------------------------------
    def living(self):
        return [raider for raider in self.raiders.values() if raider.alive]

    def fallen(self):
        return [raider for raider in self.raiders.values() if not raider.alive]

    def weakest(self):
        living = self.living()
        return min(living, key=lambda r: r.hp_ratio) if living else None

    @property
    def rite_capacity(self):
        """The circle widens by one voice per phase."""
        return self.base_capacity + self.phase - 1

    @property
    def interrupt_threshold(self):
        return self.vessel.max_hp * INTERRUPT_SHARE

    @property
    def vessel_attack(self):
        return self.vessel.attack * (1 + PHASE3_ATTACK_BONUS if self.phase >= 3 else 1)

    def ability_ready(self, name):
        spec = ABILITIES.get(name)
        if spec is None or self.charging:
            return False
        if self.phase < spec.get("phase", 1):
            return False
        if self.vessel.cooldowns.get(name, 0) > 0:
            return False
        return self.vessel.dread >= spec.get("dread_cost", 0)

    def available_abilities(self):
        return [name for name in ABILITIES if self.ability_ready(name)]

    def signature_ready(self, raider):
        if not raider.alive or raider.signature_used:
            return False
        if SIGNATURES[raider.signature]["target"] == "fallen":
            return bool(self.fallen())
        return True

    @property
    def grip_bonus(self):
        return RITE_GRIP_MAX * self.rite / self.rite_goal

    @property
    def strike_bonus(self):
        """Everything that makes raider strikes land harder right now."""
        return self.grip_bonus + self.vulnerability + (MARK_BONUS if self.mark_turns else 0.0)

    def mvp(self):
        return max(self.raiders.values(), key=lambda r: r.valor(self.vessel.attack), default=None)

    @property
    def victorious(self):
        return self.outcome in ("slain", "exorcised")

    def improvise(self):
        """The underling's choice when the Possessor stays silent."""
        if self.charging or self.ability_ready("cataclysm"):
            return "cataclysm", None
        if self.ability_ready("execute"):
            doomed = [r for r in self.living() if r.hp_ratio <= EXECUTE_THRESHOLD]
            if doomed:
                return "execute", self.rng.choice(doomed).user_id
        options = [name for name in ("smite", "sweep", "siphon") if self.ability_ready(name)]
        ability = self.rng.choice(options or ["smite"])
        target = self.rng.choice(self.living()) if ABILITIES[ability]["target"] else None
        return ability, target.user_id if target else None

    # ---- resolution ----------------------------------------------------
    def start_round(self):
        self.round_no += 1
        return self.round_no

    def _choices(self, actions, living):
        """Normalise raw choices to {user_id: (action, target_id)}; illegal ones become Strike."""
        chosen = {}
        for raider in living:
            raw = actions.get(raider.user_id)
            action, target = raw if isinstance(raw, tuple) else (raw, None)
            if action not in PLAYER_ACTIONS or (action == "signature" and not self.signature_ready(raider)):
                action, target = DEFAULT_ACTION, None
            chosen[raider.user_id] = (action, target)
        return chosen

    def resolve_round(self, actions, ability, target_id=None, spirits=None):
        if self.outcome:
            raise RuntimeError("The possession has already ended.")
        living = self.living()
        releasing = self.charging
        if releasing:
            ability, target_id = "cataclysm", None
        elif not self.ability_ready(ability):
            ability = "smite"
        spec = ABILITIES[ability]
        if spec["target"]:
            if target_id not in self.raiders or not self.raiders[target_id].alive:
                weakest = self.weakest()
                target_id = weakest.user_id if weakest else None
        else:
            target_id = None

        report = RoundReport(self.round_no, ability, target_id, releasing=releasing)
        report.ward = ability == "ward"
        chosen = self._choices(actions, living)
        self.last_actions = {uid: action for uid, (action, _target) in chosen.items()}

        self._spirits(spirits or {}, report)
        if ability == "dominate" and target_id in chosen:
            report.dominated = self._dominate(target_id, chosen)

        guarded, protectors = self._stances(chosen, report)
        chanting = self._raid_acts(chosen, report)
        self.rite = min(self.rite_goal, self.rite + report.total_rite)
        self._advance_phase(report)

        if self.vessel.hp <= 0:
            self.vessel.hp = 0.0
            self.outcome = "slain"
        elif self.rite >= self.rite_goal:
            self.outcome = "exorcised"
        elif releasing:
            self.charging = False
            if report.pilfered or report.total_strike >= self.interrupt_threshold:
                report.interrupted = True
            else:
                self._cataclysm(guarded, protectors, report)
        elif ability == "cataclysm":
            self.vessel.dread -= spec["dread_cost"]
            self.charging = True
            report.charge_started = True
        else:
            self._vessel_acts(ability, target_id, guarded, protectors, report)
        if not self.outcome:
            self._break_chants(chanting, report)

        self._record_deaths(report)
        self._tick_cooldowns(ability, releasing)
        if not self.outcome:
            if not self.living():
                self.outcome = "wiped"
            elif self.round_no >= self.max_rounds:
                self.outcome = "withdrawn"
        return report

    def _spirits(self, spirits, report):
        for uid, action in spirits.items():
            raider = self.raiders.get(uid)
            if raider is None or raider.alive or action not in SPIRIT_ACTIONS:
                continue
            raider.spirit_acts += 1
            if action == "haunt":
                report.haunts += 1
            elif action == "echo":
                report.echoes += 1
        report.haunt_drain = min(self.vessel.dread, report.haunts * HAUNT_DREAD)
        self.vessel.dread -= report.haunt_drain
        self.echo_carry += report.echoes
        report.echo_gain, self.echo_carry = divmod(self.echo_carry, ECHOES_PER_RITE)

    def _dominate(self, target_id, chosen):
        action, _target = chosen[target_id]
        chosen[target_id] = (None, None)  # The puppet's own action is spent.
        puppet = self.raiders[target_id]
        result = {"target_id": target_id, "action": action}
        if action == "strike":
            allies = [r for r in self.living() if r.user_id != target_id] or [puppet]
            victim = self.rng.choice(allies)
            hit = incoming_damage(puppet.damage, victim.armor)
            victim.hp = max(0.0, victim.hp - hit)
            result.update(victim_id=victim.user_id, amount=hit)
        elif action == "mend":
            amount = min(self.vessel.max_hp - self.vessel.hp, puppet.max_hp * MEND_RATIO)
            self.vessel.hp += amount
            result.update(amount=amount)
        elif action == "rite":
            lost = min(1, self.rite)
            self.rite -= lost
            result.update(amount=lost)
        elif action == "signature":
            puppet.signature_used = True
        return result

    def _stances(self, chosen, report):
        """Resolve guards and the signatures that must land before any blow does."""
        guarded, protectors = set(), {}
        for uid, (action, target) in chosen.items():
            if action == "guard":
                ally = self.raiders.get(target)
                if ally is None or not ally.alive or ally.user_id == uid:
                    guarded.add(uid)
                    report.guards.append((uid, uid))
                else:
                    protectors.setdefault(ally.user_id, uid)
                    report.guards.append((uid, ally.user_id))
            elif action == "signature":
                key = self.raiders[uid].signature
                if key == "bulwark":
                    guarded.update(r.user_id for r in self.living())
                elif key == "hunters_mark":
                    self.mark_turns = MARK_TURNS
                elif key == "unbroken_circle":
                    report.circle_sealed = True
        return guarded, protectors

    def _strike(self, raider, report, factor=1.0, *, tag=None, ignore_armor=False, ignore_ward=False):
        base = raider.damage if ignore_armor else max(1.0, raider.damage - self.vessel.armor)
        dealt = base * self.rng.uniform(0.9, 1.1) * factor * (1 + self.strike_bonus)
        if report.ward and not ignore_ward:
            dealt *= WARD_FACTOR
        self.vessel.hp -= dealt
        raider.dealt += dealt
        report.strikes.append((raider.user_id, dealt, tag))
        return dealt

    def _heal(self, healer, ally, ratio):
        amount = min(ally.max_hp - ally.hp, ally.max_hp * ratio)
        ally.hp += amount
        healer.healed += amount
        return amount

    def _raid_acts(self, chosen, report):
        chanting = set()
        for uid, (action, target) in chosen.items():
            raider = self.raiders[uid]
            if not raider.alive:
                continue
            if action == "strike":
                self._strike(raider, report)
            elif action == "mend":
                ally = self.raiders.get(target)
                if ally is None or not ally.alive:
                    ally = self.weakest()
                report.mends.append((uid, ally.user_id, self._heal(raider, ally, MEND_RATIO)))
            elif action == "rite":
                raider.rites += 1
                chanting.add(uid)
                if report.rite_gain < self.rite_capacity:
                    report.rite_gain += 1
                else:
                    report.rite_unheard += 1
            elif action == "signature":
                self._signature(raider, target, report, chanting)
        return chanting

    def _signature(self, raider, target, report, chanting):
        key = raider.signature
        spec = SIGNATURES[key]
        if spec["target"] == "fallen" and not self.fallen():
            self._strike(raider, report)  # Someone else raised the last of the fallen first.
            return
        raider.signature_used = True
        amount, target_id = 0.0, None
        if "factor" in spec:
            factor = spec["factor"]
            amount = self._strike(
                raider, report, factor, tag=key,
                ignore_armor=spec.get("ignore_armor", False), ignore_ward=spec.get("ignore_ward", False),
            )
        if key == "harvest":
            factor = min(HARVEST_MAX, 1 + HARVEST_PER_FALLEN * len(self.fallen()))
            amount = self._strike(raider, report, factor, tag=key)
        elif key == "sunder":
            self.vulnerability += SUNDER_BONUS
        elif key == "paragons_will":
            ally = self.weakest()
            report.mends.append((raider.user_id, ally.user_id, self._heal(raider, ally, MEND_RATIO)))
            raider.rites += 1
            chanting.add(raider.user_id)
            report.bonus_rite += 1
        elif key == "unbroken_circle":
            raider.rites += UNBROKEN_RITE
            report.bonus_rite += UNBROKEN_RITE
        elif key == "pilfer":
            amount = min(self.vessel.dread, PILFER_DREAD)
            self.vessel.dread -= amount
            report.pilfered = max(1, amount) if self.charging else amount
        elif key == "ballad":
            amount = sum(self._heal(raider, ally, BALLAD_RATIO) for ally in self.living())
        elif key == "gift":
            ally = self.raiders.get(target)
            if ally is None or not ally.alive:
                ally = self.weakest()
            target_id = ally.user_id
            amount = self._heal(raider, ally, 1.0)
        elif key == "resurrection":
            fallen = self.raiders.get(target)
            if fallen is None or fallen.alive:
                fallen = self.rng.choice(self.fallen())
            target_id = fallen.user_id
            fallen.hp = fallen.max_hp * RESURRECT_RATIO
            self._dead.discard(fallen.user_id)
            raider.revives += 1
            report.revived.append(fallen.user_id)
            amount = fallen.hp
        report.signatures.append((raider.user_id, key, target_id, amount))

    def _advance_phase(self, report):
        share = self.vessel.hp / self.vessel.max_hp
        phase = 1 + sum(1 for threshold in PHASE_THRESHOLDS if share <= threshold)
        if phase > self.phase and self.vessel.hp > 0:
            self.phase = phase
            self.vessel.armor = 0
            report.phase_change = phase

    def _hit(self, raider, multiplier, guarded, protectors, report, *, single=False):
        """Hit a raider; a single-target blow on a protected raider lands on the protector."""
        victim, shielded = raider, None
        protector = self.raiders.get(protectors.get(raider.user_id))
        if single and protector is not None and protector.alive:
            victim, shielded = protector, raider.user_id
        halved = shielded is not None or victim.user_id in guarded or (
            not single and raider.user_id in protectors
        )
        hit = incoming_damage(self.vessel_attack * multiplier, victim.armor)
        if halved:
            hit *= GUARD_FACTOR
        victim.hp = max(0.0, victim.hp - hit)
        if shielded is not None:
            victim.absorbed += hit
        report.hits.append((victim.user_id, hit, halved, shielded))
        return victim, hit, halved

    def _vessel_acts(self, ability, target_id, guarded, protectors, report):
        spec = ABILITIES[ability]
        living = self.living()
        if not living:
            return
        if ability in SINGLE_TARGET_HITS:
            target = self.raiders[target_id]
            if not target.alive:
                return
            multiplier = spec["multiplier"] * focus_multiplier(self.starting_count)
            doomed = ability == "execute" and target.hp_ratio <= EXECUTE_THRESHOLD
            victim, dealt, halved = self._hit(target, multiplier, guarded, protectors, report, single=True)
            if doomed and victim is target and not halved and victim.alive:
                victim.hp = 0.0
                report.executed.append(victim.user_id)
            if ability == "siphon":
                healed = min(self.vessel.max_hp - self.vessel.hp, dealt * spec["heal_ratio"])
                self.vessel.hp += healed
                report.vessel_healed = healed
        elif ability == "sweep":
            for raider in self.rng.sample(living, k=sweep_target_count(len(living))):
                self._hit(raider, spec["multiplier"], guarded, protectors, report)

    def _cataclysm(self, guarded, protectors, report):
        for raider in self.living():
            multiplier = ABILITIES["cataclysm"]["multiplier"]
            if self.cataclysm_variance:
                multiplier *= self.rng.uniform(*self.cataclysm_variance)
            self._hit(raider, multiplier, guarded, protectors, report)

    def _break_chants(self, chanting, report):
        """A focused blow on any chanter shatters the circle, undoing this turn's
        Severance. Sweep is too scattered to break it, and a sealed circle holds."""
        if report.ability not in CIRCLE_BREAKERS or report.circle_sealed or not report.total_rite:
            return
        struck = [uid for uid, _amount, _halved, _shielded in report.hits if uid in chanting]
        if struck:
            self.rite = max(0, self.rite - report.total_rite)
            report.rite_broken = struck

    def _record_deaths(self, report):
        for raider in self.raiders.values():
            if not raider.alive and raider.user_id not in self._dead:
                self._dead.add(raider.user_id)
                report.deaths.append(raider.user_id)
        per_round = PHASE3_DREAD_PER_ROUND if self.phase >= 3 else DREAD_PER_ROUND
        gain = per_round + DREAD_PER_KILL * len(report.deaths)
        self.vessel.dread = min(DREAD_MAX, self.vessel.dread + gain)

    def _tick_cooldowns(self, used, releasing):
        for name in list(self.vessel.cooldowns):
            self.vessel.cooldowns[name] = max(0, self.vessel.cooldowns[name] - 1)
        if not releasing and ABILITIES[used]["cooldown"]:
            self.vessel.cooldowns[used] = ABILITIES[used]["cooldown"]
        if self.mark_turns:
            self.mark_turns -= 1


def split_gold(pool, participant_ids, survivor_ids):
    """Half the pool to everyone who stood against the vessel, half to survivors."""
    participant_ids = list(dict.fromkeys(participant_ids))
    survivor_ids = [uid for uid in dict.fromkeys(survivor_ids) if uid in participant_ids]
    if pool <= 0 or not participant_ids:
        return {}
    share_pool = pool // 2 if survivor_ids else pool
    base = share_pool // len(participant_ids)
    payouts = {uid: base for uid in participant_ids}
    if survivor_ids:
        bonus = (pool - share_pool) // len(survivor_ids)
        for uid in survivor_ids:
            payouts[uid] += bonus
    return {uid: amount for uid, amount in payouts.items() if amount > 0}
