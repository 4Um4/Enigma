"""CCH-8 P4: CLI seed-report для канонических NPC.

Read-only: вызывает build_seed_report (pure function). Не запускает GameLoop,
не мутирует NpcState, не пишет в campaign_state.

Usage:
    python -m scripts.seed_report                       # все 6 NPC, human-readable
    python -m scripts.seed_report --json                # все 6 NPC, JSON
    python -m scripts.seed_report blacksmith_orm        # один NPC, human-readable
    python -m scripts.seed_report blacksmith_orm --json # один NPC, JSON

Детерминизм: entries отсортированы по entry_id. Повторный запуск на одинаковом
входе даёт идентичный отчёт.
"""
from __future__ import annotations

import json
import sys
from typing import Any, Dict, List

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from app.services.chronicle.chronicle_seeder import build_seed_report, canonical_chronicles


def _render_npc(report_dict: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"=== {report_dict['npc_id']} ===")
    lines.append(f"  chronicle_id: {report_dict['chronicle_id']}")
    lines.append(f"  canon_loaded: {report_dict['canon_loaded']}")
    lines.append(f"  game_start_age: {report_dict['game_start_age']}")
    lines.append(f"  entries: total={report_dict['entries_total']} author={report_dict['entries_author']}")
    lines.append(f"  entries_by_kind: {report_dict['entries_by_kind']}")
    lines.append(
        f"  aggregates: memories={report_dict['memories_count']} "
        f"knowledge={report_dict['knowledge_count']} "
        f"relationships={report_dict['relationships_count']} "
        f"imprints={report_dict['imprints_count']} "
        f"beliefs={report_dict['beliefs_count']} "
        f"white_spots={report_dict['white_spots_count']}"
    )
    seeded = sum(1 for e in report_dict["entries"] if e["seed_result"] == "SEEDED")
    skipped = sum(1 for e in report_dict["entries"] if e["seed_result"] == "SKIPPED")
    na = sum(1 for e in report_dict["entries"] if e["seed_result"] == "NOT_APPLICABLE")
    lines.append(f"  seed_result: SEEDED={seeded} SKIPPED={skipped} NOT_APPLICABLE={na}")
    if skipped:
        lines.append("  skipped entries:")
        for e in report_dict["entries"]:
            if e["seed_result"] != "SKIPPED":
                continue
            lines.append(
                f"    {e['entry_id']} [{e['source_kind']}] reason={e['skip_reason']} "
                f"struct={e['structural_check']} sem={e['semantic_check']}"
            )
    if report_dict["entries"]:
        day_anomalies: Dict[str, int] = {}
        for e in report_dict["entries"]:
            if e["day_anomaly"]:
                day_anomalies[e["day_anomaly"]] = day_anomalies.get(e["day_anomaly"], 0) + 1
        if day_anomalies:
            lines.append(f"  day_anomalies: {day_anomalies}")
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    json_mode = "--json" in argv
    positional = [a for a in argv if not a.startswith("--")]
    docs = canonical_chronicles()
    if positional:
        targets = positional
    else:
        targets = sorted(docs.keys())

    out: List[Dict[str, Any]] = []
    for npc_id in targets:
        report = build_seed_report(npc_id)
        if report is None:
            out.append({"npc_id": npc_id, "canon_loaded": False})
        else:
            out.append(report.to_dict())

    if json_mode:
        print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for chunk in out:
            if chunk is None:
                continue
            if chunk.get("canon_loaded") is False:
                print(f"=== {chunk['npc_id']} ===")
                print("  canon_loaded: False")
            else:
                print(_render_npc(chunk))
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

