"""Discord-independent rules for the GM Possession event.

A Game Master drives a possessed vessel while raiders pick one action per
round. Both sides choose simultaneously; raiders resolve first, then the
vessel. Raiders win by destroying the vessel or completing the Severance
rite; the vessel wins by wiping the raid or outlasting the round limit.
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

PLAYER_ACTIONS = ("strike", "guard", "mend", "rite")
DEFAULT_ACTION = "strike"

ABILITIES = {
    "smite": {"target": True, "cooldown": 0, "multiplier": 2.2},
    "sweep": {"target": False, "cooldown": 1, "multiplier": 0.8},
    "siphon": {"target": True, "cooldown": 2, "multiplier": 1.3, "heal_ratio": 1.5},
    "dominate": {"target": True, "cooldown": 3},
    "ward": {"target": False, "cooldown": 3},
    "cataclysm": {"target": False, "cooldown": 0, "multiplier": 1.3, "dread_cost": DREAD_MAX},
}
DAMAGING_ABILITIES = ("smite", "sweep", "siphon", "cataclysm")


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
    dealt: float = 0.0
    healed: float = 0.0
    rites: int = 0

    @property
    def alive(self):
        return self.hp > 0

    def valor(self, vessel_attack):
        return self.dealt + self.healed + self.rites * vessel_attack * 2


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
    strikes: list = field(default_factory=list)       # (user_id, damage)
    guards: list = field(default_factory=list)        # user_id
    mends: list = field(default_factory=list)         # (healer_id, target_id, amount)
    rite_gain: int = 0
    rite_unheard: int = 0
    rite_broken: list = field(default_factory=list)   # chanters whose voice the vessel broke
    dominated: dict | None = None                     # {"target_id", "action", ...}
    ward: bool = False
    hits: list = field(default_factory=list)          # (user_id, damage, guarded)
    vessel_healed: float = 0.0
    deaths: list = field(default_factory=list)        # user_id

    @property
    def total_strike(self):
        return sum(amount for _uid, amount in self.strikes)


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
        self.rite_capacity = rite_capacity(len(raiders))
        self.max_rounds = max_rounds
        self.cataclysm_variance = cataclysm_variance
        self.round_no = 0
        self.outcome = None  # "slain", "exorcised", "wiped", "withdrawn"
        self.last_actions = {}
        self._dead = set()

    # ---- queries -------------------------------------------------------
    def living(self):
        return [raider for raider in self.raiders.values() if raider.alive]

    def weakest(self):
        living = self.living()
        return min(living, key=lambda r: r.hp / r.max_hp) if living else None

    def ability_ready(self, name):
        spec = ABILITIES.get(name)
        if spec is None:
            return False
        if self.vessel.cooldowns.get(name, 0) > 0:
            return False
        return self.vessel.dread >= spec.get("dread_cost", 0)

    def available_abilities(self):
        return [name for name in ABILITIES if self.ability_ready(name)]

    @property
    def grip_bonus(self):
        return RITE_GRIP_MAX * self.rite / self.rite_goal

    def mvp(self):
        return max(self.raiders.values(), key=lambda r: r.valor(self.vessel.attack), default=None)

    @property
    def victorious(self):
        return self.outcome in ("slain", "exorcised")

    def improvise(self):
        """The underling's choice when the Possessor stays silent."""
        if self.ability_ready("cataclysm"):
            return "cataclysm", None
        options = [name for name in ("smite", "sweep", "siphon") if self.ability_ready(name)]
        ability = self.rng.choice(options or ["smite"])
        target = self.rng.choice(self.living()) if ABILITIES[ability]["target"] else None
        return ability, target.user_id if target else None

    # ---- resolution ----------------------------------------------------
    def start_round(self):
        self.round_no += 1
        return self.round_no

    def resolve_round(self, actions, ability, target_id=None):
        if self.outcome:
            raise RuntimeError("The possession has already ended.")
        if not self.ability_ready(ability):
            ability = "smite"
        spec = ABILITIES[ability]
        living = self.living()
        if spec["target"]:
            if target_id not in self.raiders or not self.raiders[target_id].alive:
                weakest = self.weakest()
                target_id = weakest.user_id if weakest else None
        else:
            target_id = None

        report = RoundReport(self.round_no, ability, target_id)
        chosen = {
            raider.user_id: actions.get(raider.user_id) if actions.get(raider.user_id) in PLAYER_ACTIONS
            else DEFAULT_ACTION
            for raider in living
        }
        self.last_actions = dict(chosen)
        report.ward = ability == "ward"
        guarding = {uid for uid, action in chosen.items() if action == "guard"}
        chanting = set()

        if ability == "dominate" and target_id in chosen:
            report.dominated = self._dominate(target_id, chosen, guarding)

        for uid, action in chosen.items():
            raider = self.raiders[uid]
            if not raider.alive:
                continue
            if action == "strike":
                dealt = max(1.0, raider.damage - self.vessel.armor) * self.rng.uniform(0.9, 1.1)
                dealt *= 1 + self.grip_bonus
                if report.ward:
                    dealt *= WARD_FACTOR
                self.vessel.hp -= dealt
                raider.dealt += dealt
                report.strikes.append((uid, dealt))
            elif action == "mend":
                ally = self.weakest()
                amount = min(ally.max_hp - ally.hp, ally.max_hp * MEND_RATIO)
                ally.hp += amount
                raider.healed += amount
                report.mends.append((uid, ally.user_id, amount))
            elif action == "rite":
                raider.rites += 1
                chanting.add(uid)
                if report.rite_gain < self.rite_capacity:
                    report.rite_gain += 1
                else:
                    report.rite_unheard += 1
        report.guards = sorted(guarding)
        self.rite = min(self.rite_goal, self.rite + report.rite_gain)

        if self.vessel.hp <= 0:
            self.vessel.hp = 0.0
            self.outcome = "slain"
        elif self.rite >= self.rite_goal:
            self.outcome = "exorcised"
        else:
            self._vessel_acts(ability, target_id, guarding, report)
            self._break_chants(chanting, report)

        self._record_deaths(report)
        self._tick_cooldowns(ability)
        if not self.outcome:
            if not self.living():
                self.outcome = "wiped"
            elif self.round_no >= self.max_rounds:
                self.outcome = "withdrawn"
        return report

    def _dominate(self, target_id, chosen, guarding):
        action = chosen[target_id]
        chosen[target_id] = None  # The puppet's own action is spent.
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
        elif action == "guard":
            guarding.discard(target_id)
        return result

    def _hit(self, raider, multiplier, guarding, report):
        hit = incoming_damage(self.vessel.attack * multiplier, raider.armor)
        guarded = raider.user_id in guarding
        if guarded:
            hit *= GUARD_FACTOR
        raider.hp = max(0.0, raider.hp - hit)
        report.hits.append((raider.user_id, hit, guarded))
        return hit

    def _vessel_acts(self, ability, target_id, guarding, report):
        spec = ABILITIES[ability]
        living = self.living()
        if not living:
            return
        if ability in ("smite", "siphon"):
            multiplier = spec["multiplier"] * focus_multiplier(self.starting_count)
            dealt = self._hit(self.raiders[target_id], multiplier, guarding, report)
            if ability == "siphon":
                healed = min(self.vessel.max_hp - self.vessel.hp, dealt * spec["heal_ratio"])
                self.vessel.hp += healed
                report.vessel_healed = healed
        elif ability == "sweep":
            for raider in self.rng.sample(living, k=sweep_target_count(len(living))):
                self._hit(raider, spec["multiplier"], guarding, report)
        elif ability == "cataclysm":
            self.vessel.dread -= spec["dread_cost"]
            for raider in living:
                multiplier = spec["multiplier"]
                if self.cataclysm_variance:
                    multiplier *= self.rng.uniform(*self.cataclysm_variance)
                self._hit(raider, multiplier, guarding, report)

    def _break_chants(self, chanting, report):
        """A focused blow (Smite, Siphon, Cataclysm) on any chanter shatters the circle,
        undoing this turn's Severance. Sweep is too scattered to break it."""
        if report.ability == "sweep" or not report.rite_gain:
            return
        struck = [uid for uid, _amount, _guarded in report.hits if uid in chanting]
        if struck:
            self.rite = max(0, self.rite - report.rite_gain)
            report.rite_broken = struck

    def _record_deaths(self, report):
        for raider in self.raiders.values():
            if not raider.alive and raider.user_id not in self._dead:
                self._dead.add(raider.user_id)
                report.deaths.append(raider.user_id)
        gain = DREAD_PER_ROUND + DREAD_PER_KILL * len(report.deaths)
        self.vessel.dread = min(DREAD_MAX, self.vessel.dread + gain)

    def _tick_cooldowns(self, used):
        for name in list(self.vessel.cooldowns):
            self.vessel.cooldowns[name] = max(0, self.vessel.cooldowns[name] - 1)
        if ABILITIES[used]["cooldown"]:
            self.vessel.cooldowns[used] = ABILITIES[used]["cooldown"]


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
