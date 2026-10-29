"""COV-11 Phase 1: chronicle_audit — read-only diagnostic of all 5 звеньев.

Для каждого NPC показывает:
1. Исходный author_text: длина, слова, предложения
2. Канонические entries: kind/provenance/object_id/open_questions/payload
3. SeedReport: что seeder произвёл бы из канона
4. Отсутствующие звенья: drafts, _resolved_questions, white_spots, runtime
5. Источники данных: пути к файлам

Read-only: не запускает LLM, не мутирует NPCState, не пишет в campaign_state.
Детерминизм: entries отсортированы по entry_id; повторный запуск идентичен.

CCH_SEED warning'и seeder'а направляются в stderr; JSON-поток в stdout чист.

Usage:
    python -m scripts.chronicle_audit
    python -m scripts.chronicle_audit --json
    python -m scripts.chronicle_audit blacksmith_orm
    python -m scripts.chronicle_audit blacksmith_orm --json
"""
from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# COV-11: seeder логирует [CCH_SEED] warnings в stdout по умолчанию.
# JSON-режим требует чистый stdout. Перенаправляем root logger в stderr
# ДО импорта seeder, чтобы его logger наследовал конфигурацию.
_logging_handler = logging.StreamHandler(sys.stderr)
_logging_handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
_root_logger = logging.getLogger()
if not _root_logger.handlers:
    _root_logger.addHandler(_logging_handler)
else:
    for h in _root_logger.handlers:
        if isinstance(h, logging.StreamHandler) and h.stream is sys.stdout:
            _root_logger.removeHandler(h)
    _root_logger.addHandler(_logging_handler)

from app.core.config import BASE_DIR
from app.services.chronicle.chronicle_seeder import build_seed_report, canonical_chronicles
from app.services.npc.npc_loader import get_display_names


def _resolved_questions_stats(doc: Any) -> Dict[str, Any]:
    """Подсчёт _resolved_questions с разделением: ключ отсутствует / пуст / непуст.

    resolve_question (routes_chronicle.py L609-615) записывает в payload:
      _resolved_questions = old_list + [{question_id, selected_option, selected_value}]

    Поэтому:
    - ключ отсутствует → resolve_question никогда не вызывался для этой entry
    - ключ есть, список пуст → невозможное состояние (resolve всегда добавляет ≥1)
    - ключ есть, список непуст → есть история резолюций
    """
    entries_with_key = 0
    entries_with_nonempty = 0
    total_resolved_records = 0
    for e in doc.entries:
        payload = e.payload if isinstance(e.payload, dict) else {}
        if "_resolved_questions" not in payload:
            continue
        entries_with_key += 1
        rq = payload.get("_resolved_questions")
        if isinstance(rq, list):
            if len(rq) > 0:
                entries_with_nonempty += 1
                total_resolved_records += len(rq)
        elif rq is not None:
            entries_with_nonempty += 1
            total_resolved_records += 1
    return {
        "entries_with_key": entries_with_key,
        "entries_with_nonempty_history": entries_with_nonempty,
        "total_resolved_records": total_resolved_records,
    }


def _text_stats(text: str) -> Dict[str, Any]:
    if not text:
        return {"chars": 0, "words": 0, "sentences": 0, "preview": ""}
    words = len([w for w in text.split() if w])
    sentences = len(re.findall(r"[.!?]", text))
    preview = text[:200].replace("\n", " ")
    return {
        "chars": len(text),
        "words": words,
        "sentences": sentences,
        "preview": preview,
    }


def _entries_summary(doc: Any) -> Dict[str, Any]:
    by_kind: Dict[str, int] = {}
    by_provenance: Dict[str, int] = {}
    open_questions_count = 0
    object_id_null_count = 0
    object_id_set_count = 0
    samples: List[Dict[str, Any]] = []
    for e in sorted(doc.entries, key=lambda x: x.entry_id):
        kind_str = e.kind.value
        by_kind[kind_str] = by_kind.get(kind_str, 0) + 1
        prov_str = e.provenance.value
        by_provenance[prov_str] = by_provenance.get(prov_str, 0) + 1
        if e.open_questions:
            open_questions_count += len(e.open_questions)
        if e.object_id is None:
            object_id_null_count += 1
        else:
            object_id_set_count += 1
        kind_samples = [s for s in samples if s["kind"] == kind_str]
        if len(kind_samples) < 3:
            obj_str = None
            if e.object_id is not None:
                obj_str = {
                    "ref_kind": e.object_id.ref_kind.value,
                    "npc_id": e.object_id.npc_id,
                    "white_spot_id": e.object_id.white_spot_id,
                    "name_hint": e.object_id.name_hint,
                }
            payload_keys: List[str] = []
            if isinstance(e.payload, dict):
                payload_keys = sorted(e.payload.keys())
            samples.append({
                "entry_id": e.entry_id,
                "kind": kind_str,
                "historical_age": e.historical_age,
                "object_id": obj_str,
                "open_questions_count": len(e.open_questions),
                "payload_keys": payload_keys,
                "provenance": prov_str,
            })
    return {
        "total": len(doc.entries),
        "by_kind": by_kind,
        "by_provenance": by_provenance,
        "open_questions_count": open_questions_count,
        "object_id_null_count": object_id_null_count,
        "object_id_set_count": object_id_set_count,
        "samples": samples,
    }


def _missing_links(npc_id: str, doc: Any) -> List[Dict[str, str]]:
    """Наблюдаемые факты отсутствия данных. Без причинных утверждений.

    Каждая запись — наблюдаемый факт (файл/данных нет), а не вывод о причине.
    """
    missing: List[Dict[str, str]] = []
    canon_dir = BASE_DIR / "config" / "npc" / "chronicles"
    drafts_dir = BASE_DIR / "saves"
    draft_paths = list(drafts_dir.rglob(f"chronicle_drafts/{npc_id}.json"))
    if not draft_paths:
        missing.append({
            "link": "draft",
            "status": "absent",
            "fact": f"no chronicle_drafts/{npc_id}.json under {drafts_dir}",
            "file": str(drafts_dir / "**" / "chronicle_drafts" / f"{npc_id}.json"),
        })
    else:
        for p in draft_paths:
            missing.append({
                "link": "draft",
                "status": "present",
                "fact": f"draft file exists ({p.stat().st_size} bytes)",
                "file": str(p),
            })
    has_open_q = any(e.open_questions for e in doc.entries)
    if not has_open_q:
        missing.append({
            "link": "open_questions",
            "status": "absent",
            "fact": "0 entries with non-empty open_questions in canonical doc",
            "file": str(canon_dir / f"{npc_id}.json"),
        })
    rq_stats = _resolved_questions_stats(doc)
    if rq_stats["entries_with_nonempty_history"] == 0:
        missing.append({
            "link": "resolved_history",
            "status": "absent",
            "fact": "0 entries with non-empty _resolved_questions in payload",
            "file": str(canon_dir / f"{npc_id}.json"),
        })
    else:
        missing.append({
            "link": "resolved_history",
            "status": "present",
            "fact": f"{rq_stats['entries_with_nonempty_history']} entries with "
                    f"{rq_stats['total_resolved_records']} resolved records",
            "file": str(canon_dir / f"{npc_id}.json"),
        })
    if not doc.white_spots:
        missing.append({
            "link": "white_spots",
            "status": "absent",
            "fact": "0 white_spots in canonical doc",
            "file": str(canon_dir / f"{npc_id}.json"),
        })
    has_llm_draft = any(e.provenance.value == "LLM_DRAFT" for e in doc.entries)
    if not has_llm_draft:
        missing.append({
            "link": "llm_draft_provenance",
            "status": "absent",
            "fact": "0 entries with provenance=LLM_DRAFT in canonical doc",
            "file": str(canon_dir / f"{npc_id}.json"),
        })
    if doc.canonical_version <= 1:
        missing.append({
            "link": "canonical_version_increment",
            "status": "absent",
            "fact": f"canonical_version={doc.canonical_version} (no re-canonization)",
            "file": str(canon_dir / f"{npc_id}.json"),
        })
    missing.append({
        "link": "runtime_npcstate",
        "status": "not_observable_in_cli",
        "fact": "CLI cannot probe NPCState.episodic_memory/relationship_cache/"
                "affective_imprints/psyche.beliefs without running GameLoop",
        "file": "character_debug endpoint (requires HTTP server + GameLoop)",
    })
    return missing


def _audit_npc(npc_id: str, roster: Dict[str, str]) -> Optional[Dict[str, Any]]:
    docs = canonical_chronicles()
    doc = docs.get(npc_id)
    if doc is None:
        return None
    seed_report = build_seed_report(npc_id)
    es = _entries_summary(doc)
    rq = _resolved_questions_stats(doc)
    ml = _missing_links(npc_id, doc)
    canon_dir = BASE_DIR / "config" / "npc" / "chronicles"
    drafts_dir = BASE_DIR / "saves"
    canon_path = canon_dir / f"{npc_id}.json"
    return {
        "npc_id": npc_id,
        "sources": {
            "canon_file": str(canon_path),
            "canon_file_exists": canon_path.exists(),
            "drafts_dir": str(drafts_dir),
            "drafts_dir_exists": drafts_dir.exists(),
            "roster_source": "config/npc/individuals/*.json",
        },
        "link_1_author_text": _text_stats(doc.author_text),
        "link_1_game_start_age": doc.game_start_age,
        "link_2_canonical_version": doc.canonical_version,
        "link_2_entries_summary": es,
        "link_2_resolved_questions": rq,
        "link_3_roster": dict(sorted(roster.items())),
        "link_4_seed_report": seed_report.to_dict() if seed_report else None,
        "link_5_runtime": {
            "status": "not_observable_in_cli",
            "consumers": [
                "social_deltas.py:76 — relationship_cache.get → DecisionHub",
                "belief_modifier_resolver.py:60 — BeliefState → DecisionHub modifiers",
                "affect.py:271 — decay_affective_imprints",
                "affect.py:299 — apply_conditioning (runtime producer of AffectiveImprint)",
                "social_target_resolver.py:52 — relationship_cache.get('trust')",
            ],
            "note": "requires running GameLoop + HTTP server + character_debug endpoint",
        },
        "missing_links": ml,
    }


def _render_human(audit: Dict[str, Any]) -> str:
    npc_id = audit["npc_id"]
    src = audit["sources"]
    at = audit["link_1_author_text"]
    es = audit["link_2_entries_summary"]
    rq = audit["link_2_resolved_questions"]
    sr = audit["link_4_seed_report"]
    roster = audit["link_3_roster"]
    lines: List[str] = []
    lines.append(f"=== chronicle_audit: {npc_id} ===")
    lines.append("  [sources]")
    lines.append(f"    canon_file: {src['canon_file']} (exists={src['canon_file_exists']})")
    lines.append(f"    drafts_dir: {src['drafts_dir']} (exists={src['drafts_dir_exists']})")
    lines.append(f"    roster_source: {src['roster_source']} (entries: {len(roster)})")
    lines.append("  [1] AUTHOR_TEXT")
    lines.append(f"    chars={at['chars']} words={at['words']} sentences={at['sentences']}")
    lines.append(f"    game_start_age={audit['link_1_game_start_age']}")
    lines.append(f"    preview: {at['preview']}")
    lines.append("  [2] CANONICAL ENTRIES (existing canon; drafts not probed here)")
    lines.append(f"    canonical_version={audit['link_2_canonical_version']}")
    lines.append(f"    entries_total={es['total']}")
    lines.append(f"    by_kind={es['by_kind']}")
    lines.append(f"    by_provenance={es['by_provenance']}")
    lines.append(f"    open_questions_count={es['open_questions_count']}")
    lines.append(f"    object_id: null={es['object_id_null_count']} set={es['object_id_set_count']}")
    lines.append(
        f"    _resolved_questions: entries_with_key={rq['entries_with_key']} "
        f"entries_with_history={rq['entries_with_nonempty_history']} "
        f"total_records={rq['total_resolved_records']}"
    )
    lines.append("    samples (first 9):")
    for s in es["samples"][:9]:
        lines.append(
            f"      {s['entry_id'][:12]} [{s['kind']}] age={s['historical_age']} "
            f"obj={s['object_id']} oq={s['open_questions_count']} keys={s['payload_keys']}"
        )
    lines.append("  [3] ENTITY RESOLUTION (roster snapshot)")
    for nid, name in roster.items():
        lines.append(f"    {nid}: '{name}'")
    lines.append("  [4] SEED REPORT (CCH-8 P3 — what seeder would produce from canon)")
    if sr is None:
        lines.append("    canon_loaded: False")
    else:
        lines.append(
            f"    memories={sr['memories_count']} knowledge={sr['knowledge_count']} "
            f"relationships={sr['relationships_count']} imprints={sr['imprints_count']} "
            f"beliefs={sr['beliefs_count']} white_spots={sr['white_spots_count']}"
        )
        seeded = sum(1 for e in sr["entries"] if e["seed_result"] == "SEEDED")
        skipped = sum(1 for e in sr["entries"] if e["seed_result"] == "SKIPPED")
        na = sum(1 for e in sr["entries"] if e["seed_result"] == "NOT_APPLICABLE")
        lines.append(f"    seed_result: SEEDED={seeded} SKIPPED={skipped} NOT_APPLICABLE={na}")
        if skipped:
            lines.append("    skipped (first 5):")
            for e in [x for x in sr["entries"] if x["seed_result"] == "SKIPPED"][:5]:
                lines.append(
                    f"      {e['entry_id'][:12]} [{e['source_kind']}] reason={e['skip_reason']}"
                )
    lines.append("  [5] RUNTIME CONSUMER (not observable in CLI; requires GameLoop)")
    lines.append(f"    status: {audit['link_5_runtime']['status']}")
    for c in audit["link_5_runtime"]["consumers"]:
        lines.append(f"      {c}")
    lines.append("  [MISSING LINKS] (observed facts; no causal claims)")
    for m in audit["missing_links"]:
        lines.append(f"    {m['link']}: {m['status']} — {m['fact']}")
        lines.append(f"      file: {m['file']}")
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    json_mode = "--json" in argv
    positional = [a for a in argv if not a.startswith("--")]
    roster = get_display_names()
    docs = canonical_chronicles()
    targets = positional if positional else sorted(docs.keys())

    audits: List[Optional[Dict[str, Any]]] = []
    for npc_id in targets:
        audits.append(_audit_npc(npc_id, roster))

    if json_mode:
        print(json.dumps(audits, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    else:
        for idx, a in enumerate(audits):
            if a is None:
                print(f"=== {targets[idx]} ===")
                print("  canon_loaded: False")
            else:
                print(_render_human(a))
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
