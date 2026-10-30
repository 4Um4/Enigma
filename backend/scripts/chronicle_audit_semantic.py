"""Semantic report generator: строит полный отчёт по 21 пункту Орма.

Читает артефакты audit_live/{npc_id}/ и генерирует:
  08_semantic_report.md — таблица «пункт → LLM items → вердикт → ошибки»
  08_semantic_report.json — машина-читаемая версия
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_AUDIT_DIR = Path(__file__).resolve().parent.parent / "audit_live"


def load_fragments(npc_id: str) -> List[Dict[str, Any]]:
    p = _AUDIT_DIR / npc_id / "01_fragments.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def load_normalized(npc_id: str) -> Dict[int, List[Dict[str, Any]]]:
    """Returns {frag_ord: [items]}."""
    out = {}
    norm_dir = _AUDIT_DIR / npc_id / "03_normalized"
    if not norm_dir.exists():
        return out
    for f in sorted(norm_dir.iterdir()):
        if not f.name.endswith(".json"):
            continue
        # 03_point03.json → frag_ord=3
        parts = f.stem.split("_")
        if len(parts) >= 2 and parts[0].isdigit():
            frag_ord = int(parts[0])
            out[frag_ord] = json.loads(f.read_text(encoding="utf-8"))
    return out


def load_raw(npc_id: str) -> Dict[int, Dict[str, Any]]:
    out = {}
    raw_dir = _AUDIT_DIR / npc_id / "02_raw_llm"
    if not raw_dir.exists():
        return out
    for f in sorted(raw_dir.iterdir()):
        if not f.name.endswith(".json"):
            continue
        parts = f.stem.split("_")
        if len(parts) >= 2 and parts[0].isdigit():
            frag_ord = int(parts[0])
            out[frag_ord] = json.loads(f.read_text(encoding="utf-8"))
    return out


def load_draft(npc_id: str) -> Dict[str, Any]:
    p = _AUDIT_DIR / npc_id / "04_draft_response.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def load_summary(npc_id: str) -> Dict[str, Any]:
    p = _AUDIT_DIR / npc_id / "07_summary.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def semantic_verdict(point_n: int, text: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Базовый автоматический вердикт по пункту."""
    if not items:
        return {
            "verdict": "ZERO_ITEMS",
            "issues": ["пункт дал 0 items (молчание LLM)"],
            "severity": "HIGH" if point_n > 0 else "LOW",
        }

    issues = []
    text_lower = text.lower()

    # Проверка: PORTRET больше 1 на пункт
    portrets = [it for it in items if it.get("kind") == "PORTRET"]
    if len(portrets) > 1:
        issues.append(f"PORTRET × {len(portrets)} — дробление внутреннего монолога (промпт требует один)")

    # Проверка: BELIEF_SEED с бытовой формулировкой (не реактивной)
    beliefs = [it for it in items if it.get("kind") == "BELIEF_SEED"]
    for b in beliefs:
        stmt = b.get("draft_payload", {}).get("statement", "").lower()
        # Реактивные beliefs должны содержать агента/объект/отношение
        reactive_markers = ["враг", "опас", "предатель", "враждебн", "довер", "ненавид", "боя", "боится"]
        if not any(m in stmt for m in reactive_markers):
            issues.append(f"BELIEF_SEED выглядит бытовым: '{stmt[:60]}...'")

    # Проверка: RELATIONSHIP без object_id с question
    rels = [it for it in items if it.get("kind") == "RELATIONSHIP"]
    for r in rels:
        if r.get("question") is not None:
            hint = r.get("draft_payload", {}).get("target_hint", "")
            issues.append(f"RELATIONSHIP target_hint='{hint}' — нужен resolve (placeholder NEW_NPC)")

    # Проверка: EVENT с day=null (нет временного якоря)
    events = [it for it in items if it.get("kind") == "EVENT"]
    for e in events:
        if e.get("draft_payload", {}).get("day") is None:
            # Не всегда ошибка — если в тексте нет возраста
            if "лет" in text_lower or "год" in text_lower:
                issues.append("EVENT без day, но в тексте есть возраст — нужно историзировать")

    # Проверка: EFFECT без triggers (downstream-контракт)
    effects = [it for it in items if it.get("kind") == "EFFECT"]
    for ef in effects:
        ek = ef.get("draft_payload", {}).get("effect_kind", "")
        if ek in ("trauma", "loss") and "triggers" not in ef.get("draft_payload", {}):
            issues.append(f"EFFECT kind={ek} без triggers — seeder skip'нет (imprint не создан)")

    # Проверка: порождение выдуманных фактов
    payload_words = set()
    for it in items:
        for v in it.get("draft_payload", {}).values():
            if isinstance(v, str):
                payload_words.update(v.lower().split())

    text_words = set(text_lower.split())
    # Не делаем жёсткую проверку — она даёт много false positive

    verdict = "OK" if not issues else "ISSUES"
    return {"verdict": verdict, "issues": issues, "severity": "HIGH" if any("ZERO" in i or "выдум" in i for i in issues) else "MID" if issues else "LOW"}


def build_report(npc_id: str) -> Dict[str, Any]:
    fragments = load_fragments(npc_id)
    normalized = load_normalized(npc_id)
    raw = load_raw(npc_id)
    draft = load_draft(npc_id)
    summary = load_summary(npc_id)

    # Проход по пунктам
    per_point = []
    for frag in fragments:
        n = frag["n"]
        text = frag["text"]
        frag_ord = n  # совпадает, если нумерация с 0

        items = normalized.get(frag_ord, [])
        raw_resp = raw.get(frag_ord, {})

        # HTTP 500 / NOT_DECOMPOSED?
        if "_http_error" in raw_resp:
            items = []
            failure = f"HTTP {raw_resp['_http_error']}: {raw_resp.get('_body', '')[:80]}"
            verdict_data = {"verdict": "HTTP_FAIL", "issues": [failure], "severity": "HIGH"}
        elif raw_resp.get("status") == "NOT_DECOMPOSED":
            items = []
            failure = f"NOT_DECOMPOSED: {raw_resp.get('error', '')[:80]}"
            verdict_data = {"verdict": "NOT_DECOMPOSED", "issues": [failure], "severity": "HIGH"}
        else:
            verdict_data = semantic_verdict(n, text, items)

        per_point.append({
            "point_n": n,
            "frag_ord": frag_ord,
            "text_preview": text[:200],
            "text_full_chars": len(text),
            "items_count": len(items),
            "items": [
                {
                    "kind": it.get("kind"),
                    "payload_keys": list(it.get("draft_payload", {}).keys()),
                    "confidence": it.get("confidence"),
                    "needs_confirmation": it.get("needs_confirmation"),
                    "has_question": it.get("question") is not None,
                }
                for it in items
            ],
            "verdict": verdict_data["verdict"],
            "issues": verdict_data["issues"],
            "severity": verdict_data["severity"],
        })

    # Анализ draft
    draft_entries = draft.get("document", {}).get("entries", [])
    by_kind = {}
    by_provenance = {}
    object_id_null = 0
    object_id_set = 0
    open_questions_count = 0
    for e in draft_entries:
        k = e.get("kind", "?")
        by_kind[k] = by_kind.get(k, 0) + 1
        p = e.get("provenance", "?")
        by_provenance[p] = by_provenance.get(p, 0) + 1
        if e.get("object_id") is None:
            object_id_null += 1
        else:
            object_id_set += 1
        open_questions_count += len(e.get("open_questions", []))

    # Источник author_text
    draft_author_text = draft.get("document", {}).get("author_text", "")

    report = {
        "npc_id": npc_id,
        "summary": summary,
        "draft_meta": {
            "entries_count": len(draft_entries),
            "by_kind": by_kind,
            "by_provenance": by_provenance,
            "object_id_null": object_id_null,
            "object_id_set": object_id_set,
            "open_questions_count": open_questions_count,
            "draft_author_text_present": bool(draft_author_text),
            "draft_author_text_preview": draft_author_text[:100] if draft_author_text else None,
        },
        "per_point": per_point,
    }

    # Markdown
    md = [
        f"# Semantic audit: {npc_id}",
        f"",
        f"## Draft summary",
        f"",
        f"- Entries: {len(draft_entries)}",
        f"- by_kind: {by_kind}",
        f"- by_provenance: {by_provenance}",
        f"- object_id: null={object_id_null} set={object_id_set}",
        f"- open_questions: {open_questions_count}",
        f"- author_text in draft: {'present' if draft_author_text else 'EMPTY'}",
        f"",
        f"## Per-point semantic verdict",
        f"",
        f"| # | chars | items | verdict | severity | issues |",
        f"|---|-------|-------|---------|----------|--------|",
    ]
    for p in per_point:
        label = "HDR" if p["point_n"] == 0 else f"#{p['point_n']}"
        issues_str = "; ".join(p["issues"][:3]) if p["issues"] else "—"
        md.append(f"| {label} | {p['text_full_chars']} | {p['items_count']} | {p['verdict']} | {p['severity']} | {issues_str} |")

    md.append(f"\n## Detailed issues\n")
    for p in per_point:
        if p["issues"]:
            label = "HDR" if p["point_n"] == 0 else f"#{p['point_n']}"
            md.append(f"### {label} (items={p['items_count']})")
            md.append(f"**Text**: {p['text_preview']}...")
            md.append(f"**Items kinds**: {[it['kind'] for it in p['items']]}")
            for issue in p["issues"]:
                md.append(f"- ⚠️ {issue}")
            md.append("")

    out_md = _AUDIT_DIR / npc_id / "08_semantic_report.md"
    out_json = _AUDIT_DIR / npc_id / "08_semantic_report.json"
    out_md.write_text("\n".join(md), encoding="utf-8")
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return report


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/chronicle_audit_semantic.py <npc_id>")
        sys.exit(1)
    npc_id = sys.argv[1]
    r = build_report(npc_id)
    print(f"=== Semantic report: {npc_id} ===")
    print(f"Draft entries: {r['draft_meta']['entries_count']}")
    print(f"by_kind: {r['draft_meta']['by_kind']}")
    print(f"object_id: null={r['draft_meta']['object_id_null']} set={r['draft_meta']['object_id_set']}")
    print(f"open_questions: {r['draft_meta']['open_questions_count']}")
    print(f"author_text in draft: {'present' if r['draft_meta']['draft_author_text_present'] else 'EMPTY'}")
    print()
    print("Per-point verdicts:")
    for p in r["per_point"]:
        label = "HDR" if p["point_n"] == 0 else f"#{p['point_n']}"
        issues = "; ".join(p["issues"][:2]) if p["issues"] else "—"
        print(f"  {label}: items={p['items_count']} verdict={p['verdict']} sev={p['severity']} | {issues}")
    print(f"\nDetailed: backend/audit_live/{npc_id}/08_semantic_report.md")