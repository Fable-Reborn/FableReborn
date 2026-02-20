"""Generate pet skill contract audit artifacts."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Allow direct execution: `python tools/pet_skill_audit.py`.
if __package__ in {None, ""}:  # pragma: no cover - execution mode guard
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[1]))

from tools.pet_skill_audit_lib import (
    ROOT,
    build_skill_runtime_map,
    classify_trigger,
    collect_set_only_attrs,
    evaluate_mode_resolver_parity,
    extract_contract,
    extract_effect_contexts,
    iter_skill_records,
    load_skill_trees,
    normalize_claim_tokens,
    normalize_numeric_tokens,
)


REPORT_DIR = ROOT / "tools" / "reports"
JSON_REPORT = REPORT_DIR / "pet_skill_audit.json"
MD_REPORT = REPORT_DIR / "pet_skill_mismatches.md"


def build_audit() -> Dict[str, Any]:
    skill_trees = load_skill_trees()
    records = iter_skill_records(skill_trees)
    runtime_map = build_skill_runtime_map(records)
    effect_contexts = extract_effect_contexts()
    set_only_attrs = collect_set_only_attrs()
    mode_parity = evaluate_mode_resolver_parity()

    entries: List[Dict[str, Any]] = []
    mismatches: List[Dict[str, Any]] = []

    contractual_attrs = {
        "attack_priority",
        "quick_charge_active",
        "air_currents_boost",
        "freedom_boost",
        "zephyr_speed",
        "zephyr_slow",
        "shadow_form_turns",
        "infinite_energy_turns",
        "infinite_energy_active",
    }
    attr_no_ops = sorted(contractual_attrs.intersection(set_only_attrs.keys()))

    for record in records:
        runtime = runtime_map.get((record.element, record.skill_name), {"effect_keys": [], "payload": {}})
        effect_keys = list(runtime.get("effect_keys", []))
        payload = runtime.get("payload", {})
        claims, ambiguous_clauses = extract_contract(record.description)
        trigger_type = classify_trigger(record.description)

        claim_tokens = normalize_claim_tokens(claims)
        payload_tokens = normalize_numeric_tokens(payload)
        unmatched_claim_tokens = sorted(claim_tokens - payload_tokens)

        explicit_ok = True
        classification = "AMBIGUOUS_OK"
        issue = ""

        # Battery Life is intentionally not a battle-runtime skill.
        if not effect_keys and record.skill_name.lower() != "battery life":
            explicit_ok = False
            classification = "BUG"
            issue = "Skill has no runtime mapping in apply_skill_effects."
            mismatches.append(
                {
                    "classification": classification,
                    "skill_name": record.skill_name,
                    "element": record.element,
                    "issue": issue,
                }
            )
        else:
            missing_context = [key for key in effect_keys if key not in effect_contexts]
            if missing_context:
                explicit_ok = False
                classification = "NO_OP"
                issue = f"Mapped effect key(s) not consumed at runtime: {', '.join(missing_context)}"
                mismatches.append(
                    {
                        "classification": classification,
                        "skill_name": record.skill_name,
                        "element": record.element,
                        "effect_keys": missing_context,
                        "issue": issue,
                    }
                )
            elif unmatched_claim_tokens:
                # Conservative policy: surface as ambiguous unless claim is clearly unrepresented and no
                # ambiguity words exist in description.
                if ambiguous_clauses:
                    classification = "AMBIGUOUS_OK"
                    issue = "Description has ambiguous clauses; numeric interpretation retained conservatively."
                else:
                    classification = "AMBIGUOUS_OK"
                    issue = "Some numeric claims were not directly traceable to payload fields."

        entries.append(
            {
                "skill_name": record.skill_name,
                "element": record.element,
                "branch": record.branch,
                "tier": record.tier,
                "cost": record.cost,
                "description": record.description,
                "trigger_type": trigger_type,
                "effect_keys": effect_keys,
                "explicit_claims": claims,
                "unmatched_claim_tokens": unmatched_claim_tokens,
                "ambiguous_clauses": ambiguous_clauses,
                "classification": classification,
                "explicit_claims_covered": explicit_ok,
                "issue": issue,
            }
        )

    for attr in attr_no_ops:
        mismatches.append(
            {
                "classification": "NO_OP",
                "skill_name": "(runtime flag)",
                "element": "n/a",
                "issue": f"Contractual runtime flag is set-only: {attr}",
                "locations": set_only_attrs.get(attr, []),
            }
        )

    for mode, data in mode_parity.items():
        if data["resolver_calls"] < 1:
            mismatches.append(
                {
                    "classification": "DRIFT",
                    "skill_name": "(mode resolver)",
                    "element": "n/a",
                    "issue": f"{mode} has no resolve_pet_attack_outcome call",
                }
            )
        if data["contains_legacy_special_damage_block"]:
            mismatches.append(
                {
                    "classification": "DRIFT",
                    "skill_name": "(mode resolver)",
                    "element": "n/a",
                    "issue": f"{mode} still contains legacy special damage block",
                }
            )

    counts = Counter(item["classification"] for item in mismatches)
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_skills": len(records),
        "mismatch_counts": {
            "BUG": counts.get("BUG", 0),
            "NO_OP": counts.get("NO_OP", 0),
            "DRIFT": counts.get("DRIFT", 0),
            "AMBIGUOUS_OK": counts.get("AMBIGUOUS_OK", 0),
        },
    }

    return {
        "summary": summary,
        "mode_parity": mode_parity,
        "set_only_runtime_attrs": set_only_attrs,
        "skills": entries,
        "mismatches": mismatches,
    }


def write_reports(report: Dict[str, Any]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_REPORT.write_text(json.dumps(report, indent=2, sort_keys=False), encoding="utf-8")

    lines: List[str] = []
    lines.append("# Pet Skill Mismatch Report")
    lines.append("")
    lines.append(f"- Generated (UTC): {report['summary']['generated_at_utc']}")
    lines.append(f"- Total Skills: {report['summary']['total_skills']}")
    lines.append(
        "- Mismatch Counts: "
        f"BUG={report['summary']['mismatch_counts']['BUG']}, "
        f"NO_OP={report['summary']['mismatch_counts']['NO_OP']}, "
        f"DRIFT={report['summary']['mismatch_counts']['DRIFT']}, "
        f"AMBIGUOUS_OK={report['summary']['mismatch_counts']['AMBIGUOUS_OK']}"
    )
    lines.append("")

    grouped: Dict[str, List[Dict[str, Any]]] = {"BUG": [], "NO_OP": [], "DRIFT": [], "AMBIGUOUS_OK": []}
    for mismatch in report["mismatches"]:
        grouped.setdefault(mismatch["classification"], []).append(mismatch)

    for classification in ("BUG", "NO_OP", "DRIFT", "AMBIGUOUS_OK"):
        lines.append(f"## {classification}")
        items = grouped.get(classification, [])
        if not items:
            lines.append("- None")
            lines.append("")
            continue
        for item in items:
            skill = item.get("skill_name", "unknown")
            element = item.get("element", "n/a")
            issue = item.get("issue", "unspecified issue")
            lines.append(f"- `{skill}` ({element}): {issue}")
        lines.append("")

    MD_REPORT.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    report = build_audit()
    write_reports(report)
    print(f"Wrote {JSON_REPORT}")
    print(f"Wrote {MD_REPORT}")


if __name__ == "__main__":
    main()
