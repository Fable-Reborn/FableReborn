"""Versioned actor, status and condition primitives shared by both editors."""

import copy
import re


def team_default(key="party"):
    return {"id": key, "label": key.replace("_", " ").title()}


def role_default(key="adventurer"):
    return {"id": key, "label": key.replace("_", " ").title(), "team": "party", "hp": 0, "slots": 0}


def status_default(key="burn"):
    return {"id": key, "label": key.replace("_", " ").title(), "duration": 3,
            "max_stacks": 3, "damage_per_round": 5, "heal_per_round": 0,
            "damage_dealt_pct": 100, "damage_taken_pct": 100, "stun": False}


def enemy_default(key="enemy"):
    return {"id": key, "label": key.replace("_", " ").title(), "hp": 100,
            "damage": 10, "target": "random", "on_hit_status": ""}


def upgrade_encounter(spec):
    if not isinstance(spec, dict) or spec.get("version") not in (1, 2):
        raise ValueError("Unsupported encounter version.")
    result = copy.deepcopy(spec)
    result["version"] = 2
    result.setdefault("teams", [team_default()])
    result.setdefault("roles", [role_default()])
    result.setdefault("statuses", [])
    result.setdefault("layout", {})
    return result


def condition_subjects(spec, enemies=()):
    return {"round", "alive", "boss_hp", "boss_hp_percent", "enemies_alive",
            *[r["id"] for r in spec.get("resources", [])],
            *["team_alive:" + t["id"] for t in spec.get("teams", [])],
            *["role_alive:" + r["id"] for r in spec.get("roles", [])],
            *["status_count:" + s["id"] for s in spec.get("statuses", [])],
            *["enemy_hp:" + e["id"] for e in enemies]}


def validate_condition(expression, subjects, *, depth=0, budget=None):
    if budget is None:
        budget = [0]
    budget[0] += 1
    if depth > 8 or budget[0] > 64 or not isinstance(expression, dict):
        raise ValueError("Conditions allow at most 8 levels and 64 parts.")
    groups = [k for k in ("all", "any", "not") if k in expression]
    if groups:
        if len(groups) != 1 or len(expression) != 1:
            raise ValueError("Use one AND, OR or NOT group at each condition level.")
        key = groups[0]
        children = [expression[key]] if key == "not" else expression[key]
        if not isinstance(children, list) or not children:
            raise ValueError("Condition groups need at least one child.")
        for child in children:
            validate_condition(child, subjects, depth=depth + 1, budget=budget)
    else:
        op = expression.get("operator")
        if op not in ("always", "<=", ">=", "==", "!=", "<", ">"):
            raise ValueError("Choose a valid condition comparison.")
        if op != "always":
            if expression.get("subject") not in subjects:
                raise ValueError(f"Unknown condition subject: {expression.get('subject')}.")
            value = expression.get("value")
            if type(value) is not int or not -1_000_000 <= value <= 1_000_000:
                raise ValueError("Condition thresholds must be bounded whole numbers.")


def evaluate_condition(expression, values):
    if "all" in expression:
        return all(evaluate_condition(e, values) for e in expression["all"])
    if "any" in expression:
        return any(evaluate_condition(e, values) for e in expression["any"])
    if "not" in expression:
        return not evaluate_condition(expression["not"], values)
    op = expression.get("operator", "always")
    if op == "always":
        return True
    a, b = values.get(expression["subject"], 0), expression["value"]
    return {"<=": a <= b, ">=": a >= b, "==": a == b, "!=": a != b, "<": a < b, ">": a > b}[op]


def validate_actor_catalogues(spec, integer, unique):
    teams = unique(spec["teams"], "teams", 25)
    roles = unique(spec["roles"], "roles", 25)
    statuses = unique(spec["statuses"], "statuses", 25)
    if not teams or not roles:
        raise ValueError("Keep at least one team and role.")
    for collection in (spec["teams"], spec["roles"], spec["statuses"]):
        for entry in collection:
            if not isinstance(entry.get("label"), str) or not 1 <= len(entry["label"].strip()) <= 100:
                raise ValueError("Team, role and status names must contain 1-100 characters.")
    for role in spec["roles"]:
        if role.get("team") not in teams:
            raise ValueError("Each role needs an existing team.")
        integer(role.get("hp", 0), "Role health (0 uses raid default)")
        integer(role.get("slots", 0), "Role slots (0 is unlimited)", 0, 1000)
    if not any(r.get("slots", 0) == 0 for r in spec["roles"]):
        raise ValueError("Keep an unlimited fallback role for players who do not choose.")
    for status in spec["statuses"]:
        integer(status.get("duration"), "Status duration", 1, 100)
        integer(status.get("max_stacks"), "Maximum status stacks", 1, 25)
        for key in ("damage_per_round", "heal_per_round"):
            integer(status.get(key, 0), key)
        for key in ("damage_dealt_pct", "damage_taken_pct"):
            integer(status.get(key, 100), key, 0, 1000)
        if type(status.get("stun", False)) is not bool:
            raise ValueError("Stun must be enabled or disabled.")
    return teams, roles, statuses


def valid_target(target, teams, roles, enemy_ids):
    if target in {"self", "all", "random", "lowest", "allies", "enemy", "enemies", "enemy_random", "enemy_lowest"}:
        return True
    if not isinstance(target, str) or ":" not in target:
        return False
    kind, key = target.split(":", 1)
    return key in {"team": teams, "role": roles, "enemy": enemy_ids}.get(kind, set())


def safe_id(value):
    return isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", value) is not None
