"""Deterministic, Discord-independent encounter engine. No eval or user code."""

import copy
import random

from dataclasses import dataclass, field
from .mechanics import (upgrade_encounter, team_default, role_default, condition_subjects,
    validate_condition, evaluate_condition, validate_actor_catalogues, valid_target, safe_id)

NODE_KINDS = ("scene", "battle", "choice", "trial", "check", "ending")
TRIGGERS = ("enter", "round_start", "round_end", "choice")
EFFECTS = (
    "damage",
    "heal",
    "shield",
    "resource",
    "boss_damage",
    "boss_heal",
    "announce",
    "transition",
    "apply_status",
    "remove_status",
)
TARGETS = ("self", "all", "random", "lowest", "allies", "enemy", "enemies", "enemy_random", "enemy_lowest")
OPERATORS = ("always", "<=", ">=", "==", "!=", "<", ">")
MAX_NODES = 100
MAX_RULES = 100


def default_node(key, kind="scene"):
    return {
        "id": key,
        "kind": kind,
        "title": key.replace("_", " ").title(),
        "text": "Describe this encounter.",
        "next": "victory",
        "failure": "defeat",
        "boss_hp": 300,
        "boss_damage": 10,
        "max_rounds": 20,
        "chance": 75,
        "subject": "round",
        "operator": ">=",
        "value": 1,
        "enemies": [],
        "choices": [],
        "rules": [],
        "outcome": "victory",
    }


def default_rule(key):
    return {
        "id": key,
        "trigger": "round_end",
        "subject": "round",
        "operator": "always",
        "value": 0,
        "effect": "announce",
        "target": "all",
        "amount": 0,
        "resource": "",
        "status": "",
        "destination": "",
        "limit": 1,
        "text": "Something changes in the encounter.",
    }


def advanced_starter(mode, definition_id):
    intro = default_node("arrival")
    intro.update(
        title="Arrival", text="The party arrives at a sealed gate.", next="guardian"
    )
    battle = default_node("guardian", "battle")
    battle.update(
        title="The Gate Guardian", text="Defeat the guardian to open the gate."
    )
    victory = default_node("victory", "ending")
    victory.update(
        title="Victory", text="The gate opens. Your party prevails.", outcome="victory"
    )
    defeat = default_node("defeat", "ending")
    defeat.update(title="Defeat", text="The expedition retreats.", outcome="defeat")
    return {
        "id": definition_id,
        "mode": mode,
        "skeleton": "encounter",
        "runtime": "native",
        "status": "draft",
        "name": "New Advanced Raid",
        "description": "A branching custom encounter.",
        "config": {
            "join_timeout": 60,
            "decision_timeout": 30,
            "step_delay": 2,
            "announce": {
                "title": "A new expedition",
                "description": "Join this custom raid.",
                "join_label": "Join",
            },
            "eligibility": {"god": None},
            "rewards": {
                "participant_gold": 0,
                "winner_gold_bonus": 0,
                "dragon_coins": 0,
                "crate_pool": [],
            },
            "encounter": {
                "version": 2,
                "teams": [team_default()],
                "roles": [role_default()],
                "statuses": [],
                "layout": {},
                "start": "arrival",
                "player_hp": 100,
                "max_steps": 250,
                "resources": [
                    {
                        "id": "corruption",
                        "label": "Corruption",
                        "initial": 0,
                        "min": 0,
                        "max": 100,
                    }
                ],
                "actions": [
                    {
                        "id": "strike",
                        "label": "Strike",
                        "effect": "boss_damage",
                        "target": "self",
                        "amount": 20,
                        "resource": "",
                        "cost_resource": "",
                        "cost": 0,
                    },
                    {
                        "id": "mend",
                        "label": "Mend",
                        "effect": "heal",
                        "target": "lowest",
                        "amount": 15,
                        "resource": "",
                        "cost_resource": "",
                        "cost": 0,
                    },
                ],
                "nodes": [intro, battle, victory, defeat],
            },
        },
    }


def _integer(value, label, low=0, high=1_000_000):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label} must be a whole number from {low} to {high}.")


def _key(value, label):
    if not safe_id(value):
        raise ValueError(f"{label} IDs must start with a lowercase letter, followed by up to 63 letters, digits, hyphens or underscores.")


def _unique(items, label, maximum):
    if not isinstance(items, list) or len(items) > maximum:
        raise ValueError(f"{label}: at most {maximum} entries are supported.")
    keys = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"Invalid {label} entry.")
        _key(item.get("id"), label)
        if item["id"] in keys:
            raise ValueError(f"Duplicate {label} ID: {item['id']}.")
        keys.add(item["id"])
    return keys


def validate_encounter(spec):
    """Validate all references before publishing or running, including fail paths."""
    spec = upgrade_encounter(spec)
    teams, roles, statuses = validate_actor_catalogues(spec, _integer, _unique)
    nodes = spec.get("nodes", [])
    keys = _unique(nodes, "steps", MAX_NODES)
    resources = spec.get("resources", [])
    resource_keys = _unique(resources, "resources", 25)
    if resource_keys & {"round", "alive", "boss_hp", "boss_hp_percent", "enemies_alive"}:
        raise ValueError("Resource IDs cannot replace built-in condition subjects.")
    actions = spec.get("actions", [])
    _unique(actions, "actions", 25)
    _integer(spec.get("player_hp"), "Player health", 1)
    _integer(spec.get("max_steps"), "Maximum engine steps", 1, 1000)
    if spec.get("start") not in keys:
        raise ValueError("Choose a valid starting step.")
    for resource in resources:
        _integer(resource.get("min"), "Resource minimum", -1_000_000)
        _integer(resource.get("max"), "Resource maximum", resource["min"])
        _integer(
            resource.get("initial"),
            "Resource initial value",
            resource["min"],
            resource["max"],
        )

    enemy_ids = set()
    for node in nodes:
        entries = node.get("enemies", [])
        enemy_ids |= _unique(entries, "enemies", 25)
        for enemy in entries:
            if not isinstance(enemy.get("label"), str) or not 1 <= len(enemy["label"].strip()) <= 100:
                raise ValueError("Enemy names must contain 1-100 characters.")
            _integer(enemy.get("hp"), "Enemy health", 1)
            _integer(enemy.get("damage"), "Enemy damage")
            if not valid_target(enemy.get("target", "random"), teams, roles, set()) or str(enemy.get("target", "")).startswith("enem"):
                raise ValueError("Enemy attacks must target players, roles or teams.")
            if enemy.get("on_hit_status") and enemy["on_hit_status"] not in statuses:
                raise ValueError("Enemy on-hit status does not exist.")
    enemy_ids.add("boss")

    def condition(rule, node):
        enemies = node.get("enemies") or [{"id": "boss"}]
        validate_condition(rule["condition"] if rule.get("condition") is not None else rule, condition_subjects(spec, enemies))

    def effect(rule):
        if rule.get("effect") not in EFFECTS or not valid_target(rule.get("target"), teams, roles, enemy_ids):
            raise ValueError("Choose a supported effect and target.")
        _integer(
            rule.get("amount"),
            "Effect amount",
            -1_000_000 if rule["effect"] == "resource" else 0,
        )
        if rule["effect"] == "resource" and rule.get("resource") not in resource_keys:
            raise ValueError("Resource effects need an existing resource.")
        if rule["effect"] in {"apply_status", "remove_status"} and rule.get("status") not in statuses:
            raise ValueError("Status effects need an existing status.")
        if rule["effect"] == "apply_status":
            _integer(rule.get("amount"), "Status stacks", 1, 25)
        if rule["effect"] == "transition" and rule.get("destination") not in keys:
            raise ValueError("Transition rules need an existing destination step.")

    for action in actions:
        effect(action)
        allowed_roles = action.get("roles", [])
        if not isinstance(allowed_roles, list) or any(r not in roles for r in allowed_roles):
            raise ValueError("Action role restrictions must use existing roles.")
        if action["effect"] == "transition":
            raise ValueError(
                "Transitions belong in encounter rules, not player actions."
            )
        if (
            not isinstance(action.get("label"), str)
            or not 1 <= len(action["label"].strip()) <= 100
        ):
            raise ValueError("Action labels must contain 1-100 characters.")
        _integer(action.get("cost", 0), "Action cost")
        if action.get("cost", 0) and action.get("cost_resource") not in resource_keys:
            raise ValueError("Action costs need an existing resource.")
    graph = {}
    endings = set()
    for node in nodes:
        kind = node.get("kind")
        if kind not in NODE_KINDS:
            raise ValueError(f"Unknown step type: {kind}.")
        if not isinstance(node.get("title"), str) or not node["title"].strip():
            raise ValueError("Each step needs a title.")
        if (
            len(node["title"]) > 256
            or not isinstance(node.get("text", ""), str)
            or len(node.get("text", "")) > 3500
        ):
            raise ValueError(
                "Step titles must fit 256 characters and text 3500 characters."
            )
        rules = node.get("rules", [])
        _unique(rules, "rules", MAX_RULES)
        for rule in rules:
            if kind == "ending" and rule["effect"] == "transition":
                raise ValueError("Ending steps cannot transition to another step.")
            if rule.get("trigger") not in TRIGGERS:
                raise ValueError("Choose a supported rule trigger.")
            if rule["trigger"] in {"round_start", "round_end"} and kind != "battle":
                raise ValueError("Round rules belong on battle steps.")
            if rule["trigger"] == "choice" and kind != "choice":
                raise ValueError("Choice rules belong on choice steps.")
            condition(rule, node)
            effect(rule)
            _integer(rule.get("limit"), "Rule repeat limit", 1, 100)
        if kind == "ending":
            if node.get("outcome") not in {"victory", "defeat"}:
                raise ValueError("Endings must be victory or defeat.")
            endings.add(node["id"])
            targets = []
        elif kind == "choice":
            choices = node.get("choices", [])
            _unique(choices, "choices", 25)
            if len(choices) < 2:
                raise ValueError("Choice steps need at least two options.")
            if any(
                not isinstance(c.get("label"), str)
                or not c["label"].strip()
                or len(c["label"]) > 100
                for c in choices
            ):
                raise ValueError("Choice labels must contain 1-100 characters.")
            targets = [c.get("next") for c in choices] + [node.get("failure")]
        else:
            targets = [node.get("next")]
            if kind in {"battle", "trial", "check"}:
                targets.append(node.get("failure"))
        if any(target not in keys for target in targets):
            raise ValueError(
                f"Step {node['id']} has a missing destination; set its success/failure links."
            )
        graph[node["id"]] = targets + [
            r["destination"] for r in rules if r["effect"] == "transition"
        ]
        if kind == "battle":
            if not actions:
                raise ValueError("Battles require at least one player action.")
            if not any(a.get("cost", 0) == 0 for a in actions):
                raise ValueError("Provide at least one free fallback action.")
            for role in roles:
                if not any(a.get("cost", 0) == 0 and (not a.get("roles") or role in a["roles"]) for a in actions):
                    raise ValueError(f"Role {role} needs a free fallback action.")
            _integer(node.get("boss_hp"), "Boss health", 1)
            _integer(node.get("boss_damage"), "Boss damage")
            _integer(node.get("max_rounds"), "Battle round limit", 1, 100)
        elif kind == "trial":
            _integer(node.get("chance"), "Trial success chance", 0, 100)
        elif kind == "check":
            condition(node, node)
    reachable = set()
    pending = [spec["start"]]
    while pending:
        key = pending.pop()
        if key not in reachable:
            reachable.add(key)
            pending.extend(graph[key])
    can_end = set(endings)
    while True:
        expanded = can_end | {
            key for key, edges in graph.items() if any(e in can_end for e in edges)
        }
        if expanded == can_end:
            break
        can_end = expanded
    if not reachable <= can_end:
        raise ValueError("Every reachable step needs a path to an ending.")
    return {"steps": len(nodes), "unreachable": sorted(keys - reachable)}


@dataclass
class Player:
    hp: int
    max_hp: int
    shield: int = 0
    role: str = "adventurer"
    team: str = "party"
    label: str = "Player"
    damage: int = 0
    target: str = "random"
    on_hit_status: str = ""
    statuses: dict = field(default_factory=dict)


@dataclass
class Frame:
    node_id: str
    title: str
    text: str
    events: list[str] = field(default_factory=list)
    choices: list[tuple[str, str]] = field(default_factory=list)
    outcome: str | None = None


class EncounterEngine:
    def __init__(self, spec, player_ids, *, seed=None, role_choices=None):
        validate_encounter(spec)
        self.spec = upgrade_encounter(spec)
        spec = self.spec
        self.nodes = {n["id"]: n for n in spec["nodes"]}
        self.roles = {r["id"]: r for r in spec["roles"]}
        self.status_specs = {r["id"]: r for r in spec["statuses"]}
        self.players = {}
        choices = {str(k): v for k, v in (role_choices or {}).items()}
        counts = {key: 0 for key in self.roles}
        for user in dict.fromkeys(str(p) for p in player_ids):
            role = self.roles.get(choices.get(user))
            if not role or (role.get("slots", 0) and counts[role["id"]] >= role["slots"]):
                role = next(r for r in self.roles.values() if not r.get("slots", 0))
            counts[role["id"]] += 1
            hp = role.get("hp") or spec["player_hp"]
            self.players[user] = Player(hp, hp, role=role["id"], team=role["team"], label=user)
        if not self.players:
            raise ValueError("At least one player is required.")
        self.enemies = {}
        self.resources = {r["id"]: r["initial"] for r in spec["resources"]}
        self.resource_specs = {r["id"]: r for r in spec["resources"]}
        self.rng = random.Random(seed)
        self.node_id = spec["start"]
        self.entered = False
        self.round = 0
        self.steps = 0
        self.rule_counts = {}
        self.outcome = None
        self.pending_transition = None

    @property
    def alive(self):
        return [key for key, p in self.players.items() if p.hp > 0]

    @property
    def living_enemies(self):
        return [key for key, p in self.enemies.items() if p.hp > 0]

    @property
    def boss_hp(self):
        return sum(e.hp for e in self.enemies.values())

    @property
    def boss_max_hp(self):
        return sum(e.max_hp for e in self.enemies.values())

    def enemy_options(self):
        if self.entered:
            return [(key, e.label) for key, e in self.enemies.items() if e.hp > 0]
        node = self.nodes[self.node_id]
        if node["kind"] != "battle":
            return []
        return [(e["id"], e["label"]) for e in node.get("enemies", [])] or [("boss", node["title"])]

    def _condition(self, rule):
        values = {**self.resources, "round": self.round, "alive": len(self.alive),
                  "boss_hp": self.boss_hp, "boss_hp_percent": self.boss_hp * 100 // max(1, self.boss_max_hp),
                  "enemies_alive": len(self.living_enemies)}
        values.update({"team_alive:" + t["id"]: sum(p.hp > 0 and p.team == t["id"] for p in self.players.values()) for t in self.spec["teams"]})
        values.update({"role_alive:" + r: sum(p.hp > 0 and p.role == r for p in self.players.values()) for r in self.roles})
        values.update({"enemy_hp:" + key: e.hp for key, e in self.enemies.items()})
        values.update({"status_count:" + key: sum(p.hp > 0 and key in p.statuses for p in [*self.players.values(), *self.enemies.values()]) for key in self.status_specs})
        return evaluate_condition(rule["condition"] if rule.get("condition") is not None else rule, values)

    def _targets(self, target, actor=None, chosen=None, force_enemy=False):
        if force_enemy and not target.startswith("enem"):
            target = "enemy"
        if target.startswith("enem"):
            pool = {key: e for key, e in self.enemies.items() if e.hp > 0}
            if target.startswith("enemy:"):
                key = target.split(":", 1)[1]
                return [pool[key]] if key in pool else []
            if not pool:
                return []
            if target == "enemies":
                return list(pool.values())
            if target == "enemy_random":
                return [self.rng.choice(list(pool.values()))]
            if target == "enemy_lowest":
                return [min(pool.values(), key=lambda e: e.hp)]
            return [pool.get(chosen, next(iter(pool.values())))]
        pool = {key: p for key, p in self.players.items() if p.hp > 0}
        if target == "self":
            return [pool[actor]] if actor in pool else list(pool.values())[:1]
        if target.startswith("team:"):
            return [p for p in pool.values() if p.team == target.split(":", 1)[1]]
        if target.startswith("role:"):
            return [p for p in pool.values() if p.role == target.split(":", 1)[1]]
        if target == "allies" and actor in self.players:
            return [p for p in pool.values() if p.team == self.players[actor].team]
        if target == "random" and pool:
            return [self.rng.choice(list(pool.values()))]
        if target == "lowest" and pool:
            return [min(pool.values(), key=lambda p: p.hp)]
        return list(pool.values())

    def _multiplier(self, combatant, field):
        value = 100
        if combatant:
            for key, instance in combatant.statuses.items():
                modifier = self.status_specs[key].get(field, 100)
                value += (modifier - 100) * instance["stacks"]
        return max(0, min(1000, value))

    def _damage(self, victim, amount, source=None):
        amount = amount * self._multiplier(source, "damage_dealt_pct") // 100
        amount = amount * self._multiplier(victim, "damage_taken_pct") // 100
        absorbed = min(victim.shield, amount)
        victim.shield -= absorbed
        victim.hp = max(0, victim.hp - amount + absorbed)

    def _stunned(self, actor):
        return any(self.status_specs[key].get("stun") for key in actor.statuses)

    def _apply_status(self, actor, key, stacks):
        spec = self.status_specs[key]
        current = actor.statuses.get(key, {"stacks": 0})
        actor.statuses[key] = {"stacks": min(spec["max_stacks"], current["stacks"] + stacks), "remaining": spec["duration"], "applied_step": self.steps}

    def _tick_statuses(self, events):
        for actor in [*self.players.values(), *self.enemies.values()]:
            if actor.hp <= 0:
                continue
            for key, instance in list(actor.statuses.items()):
                # A newly applied effect starts counting down next combat round.
                # In particular, an enemy's one-round stun must survive until
                # the affected player's next opportunity to act.
                if instance["applied_step"] == self.steps:
                    continue
                spec = self.status_specs[key]
                if actor.hp > 0:
                    damage = spec.get("damage_per_round", 0) * instance["stacks"]
                    self._damage(actor, damage)
                    if actor.hp > 0:
                        actor.hp = min(actor.max_hp, actor.hp + spec.get("heal_per_round", 0) * instance["stacks"])
                    events.append(f"{spec['label']} ticks on {actor.label} ({instance['remaining']} rounds left).")
                instance["remaining"] -= 1
                if instance["remaining"] <= 0:
                    del actor.statuses[key]

    def _effect(self, rule, events, actor=None, chosen=None):
        effect, amount = rule["effect"], rule["amount"]
        if effect == "resource":
            key = rule["resource"]
            bounds = self.resource_specs[key]
            self.resources[key] = max(bounds["min"], min(bounds["max"], self.resources[key] + amount))
            events.append(f"{bounds.get('label', key)}: {self.resources[key]}")
        elif effect == "announce":
            events.append(str(rule.get("text") or "The encounter changes.")[:500])
        elif effect == "transition":
            self.pending_transition = rule["destination"]
            events.append(f"Transition to {self.nodes[self.pending_transition]['title']}.")
        else:
            targets = self._targets(rule.get("target", "all"), actor, chosen, force_enemy=effect in {"boss_damage", "boss_heal"})
            for victim in targets:
                if effect in {"damage", "boss_damage"}:
                    self._damage(victim, amount, self.players.get(actor))
                elif effect in {"heal", "boss_heal"}:
                    victim.hp = min(victim.max_hp, victim.hp + amount)
                elif effect == "shield":
                    victim.shield = min(1_000_000, victim.shield + amount)
                elif effect == "apply_status":
                    self._apply_status(victim, rule["status"], amount)
                elif effect == "remove_status":
                    victim.statuses.pop(rule["status"], None)
            events.append(f"{effect.replace('_', ' ').title()} {amount} applied to {len(targets)} target(s).")

    def _rules(self, trigger, events):
        for rule in self.nodes[self.node_id].get("rules", []):
            key = (self.node_id, rule["id"])
            if rule["trigger"] == trigger and self.rule_counts.get(key, 0) < rule["limit"] and self._condition(rule):
                self.rule_counts[key] = self.rule_counts.get(key, 0) + 1
                events.append(f"Rule: {rule['id']}")
                self._effect(rule, events)
                if self.pending_transition:
                    break

    def _goto(self, key):
        self.node_id = key
        self.entered = False
        self.pending_transition = None

    def available_actions(self, actor):
        role = self.players[str(actor)].role
        return [a for a in self.spec["actions"] if not a.get("roles") or role in a["roles"]]

    def advance(self, decisions=None):
        node = self.nodes[self.node_id]
        frame = Frame(node["id"], node["title"], node.get("text", ""))
        if self.outcome:
            frame.outcome = self.outcome
            return frame
        self.steps += 1
        if self.steps > self.spec["max_steps"]:
            self.outcome = frame.outcome = "defeat"
            frame.events.append("Encounter step limit reached.")
            return frame
        decisions = {str(k): v for k, v in (decisions or {}).items() if str(k) in self.alive}
        if not self.entered:
            self.entered = True
            self.round = 0
            self.enemies = {}
            if node["kind"] == "battle":
                entries = node.get("enemies") or [{"id": "boss", "label": node["title"], "hp": node["boss_hp"], "damage": node["boss_damage"]}]
                for entry in entries:
                    self.enemies[entry["id"]] = Player(entry["hp"], entry["hp"], label=entry["label"], team="hostile", damage=entry["damage"],
                        target=entry.get("target", "random"), on_hit_status=entry.get("on_hit_status", ""))
            self._rules("enter", frame.events)
        kind = node["kind"]
        if not self.alive:
            self.outcome = frame.outcome = "defeat"
        elif self.pending_transition:
            self._goto(self.pending_transition)
        elif kind == "ending":
            self.outcome = frame.outcome = node["outcome"]
        elif kind == "scene":
            self._goto(node["next"])
        elif kind == "check":
            self._goto(node["next"] if self._condition(node) else node["failure"])
        elif kind == "trial":
            success = self.rng.randint(1, 100) <= node["chance"]
            frame.events.append("The trial succeeds." if success else "The trial fails.")
            self._goto(node["next"] if success else node["failure"])
        elif kind == "choice":
            options = {c["id"]: c for c in node["choices"]}
            votes = {key: sum(v == key for actor, v in decisions.items() if actor in self.alive) for key in options}
            winners = [key for key, count in votes.items() if count and count == max(votes.values())]
            self._rules("choice", frame.events)
            if not self.alive:
                self.outcome = frame.outcome = "defeat"
            elif self.pending_transition:
                self._goto(self.pending_transition)
            elif len(winners) == 1:
                frame.events.append(f"Party chose: {options[winners[0]]['label']}")
                self._goto(options[winners[0]]["next"])
            else:
                frame.events.append("No winning vote: following the configured timeout/tie route.")
                self._goto(node["failure"])
        elif kind == "battle":
            self.round += 1
            self._rules("round_start", frame.events)
            if not self.alive:
                self.outcome = frame.outcome = "defeat"
                return frame
            if self.pending_transition:
                self._goto(self.pending_transition)
                return frame
            for actor in list(self.alive):
                if self.boss_hp <= 0:
                    break
                player = self.players[actor]
                if player.hp <= 0 or self._stunned(player):
                    continue
                actions = {a["id"]: a for a in self.available_actions(actor)}
                fallback = next(a for a in actions.values() if a.get("cost", 0) == 0)
                decision = decisions.get(actor)
                action_key = decision.get("action") if isinstance(decision, dict) else decision
                chosen = decision.get("target") if isinstance(decision, dict) else None
                action = actions.get(action_key, fallback)
                cost, key = action.get("cost", 0), action.get("cost_resource")
                if cost and self.resources.get(key, 0) - cost < self.resource_specs[key]["min"]:
                    action, cost = fallback, 0
                    frame.events.append("Insufficient resource: using the free fallback action.")
                if cost:
                    self.resources[key] -= cost
                self._effect(action, frame.events, actor, chosen)
            for enemy in self.enemies.values():
                if enemy.hp <= 0 or self._stunned(enemy) or not self.alive:
                    continue
                for victim in self._targets(enemy.target):
                    self._damage(victim, enemy.damage, enemy)
                    if victim.hp > 0 and enemy.on_hit_status:
                        self._apply_status(victim, enemy.on_hit_status, 1)
                frame.events.append(f"{enemy.label} attacks for {enemy.damage}.")
            self._rules("round_end", frame.events)
            self._tick_statuses(frame.events)
            if not self.alive:
                self.outcome = frame.outcome = "defeat"
            elif self.pending_transition:
                self._goto(self.pending_transition)
            elif self.boss_hp <= 0:
                self._goto(node["next"])
            elif self.round >= node["max_rounds"]:
                frame.events.append("Battle round limit reached.")
                self._goto(node["failure"])
        return frame

    def prompt(self, actor=None):
        node = self.nodes[self.node_id]
        if self.outcome:
            return []
        if node["kind"] == "choice":
            return [(c["id"], c["label"]) for c in node["choices"]]
        if node["kind"] == "battle":
            actions = self.available_actions(actor) if actor is not None else self.spec["actions"]
            return [(a["id"], a["label"]) for a in actions]
        return []

    def simulate(self):
        frames = []
        while self.outcome is None:
            decisions = {}
            for key in self.alive:
                options = self.prompt(key)
                if options:
                    decisions[key] = self.rng.choice(options)[0]
            frames.append(self.advance(decisions))
        return frames
