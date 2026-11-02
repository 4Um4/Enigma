#!/usr/bin/env python3
"""CCH-12 audit: семантический crosswalk старого канона vs нового draft'а.

Сравнивает 63 записи старого канона (config/npc/chronicles/blacksmith_orm.json)
с 57 записями нового draft'а (backend/audit_live/blacksmith_orm/04_draft_response.json).

Для каждой старой записи определяет статус:
  PRESERVED    — найдена соответствующая новая запись (тот же смысл)
  RECLASSIFIED — найдена новая запись с тем же смыслом, но другим kind
  MERGED       — смысл распределён между несколькими новыми записями
  DUPLICATED   — найдено >1 новых записей с тем же смыслом
  LOST         — соответствующая новая запись не найдена
  AMBIGUOUS    — найдено несколько кандидатов, неоднозначно

Особое внимание: 15 EFFECT, 3 LOCATION, 7 BELIEF_SEED.

Входные файлы НЕ изменяются.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
# CCH-12: параметризованный npc_id (по умолчанию blacksmith_orm для обратной совместимости)
_NPC_ID = sys.argv[1] if len(sys.argv) > 1 else "blacksmith_orm"
OLD_CANON = ROOT / "config" / "npc" / "chronicles" / f"{_NPC_ID}.json"
NEW_DRAFT = ROOT / "backend" / "audit_live" / _NPC_ID / "04_draft_response.json"
OUT_DIR = ROOT / "download"
OUT_JSON = OUT_DIR / f"crosswalk_{_NPC_ID}.json"
OUT_MD = OUT_DIR / f"crosswalk_{_NPC_ID}.md"


# ── Семантические маркеры для matching ──────────────────────────────────────

# Маркеры EFFECT (occupation, trauma, gain, loss)
EFFECT_MARKERS = [
    "обожжён", "ожог", "травма", "потерял", "потеряла", "умер", "убил",
    "стал кузнецом", "занятие", "професси", "навык", "умение",
    "из которых", "кузнец в городе", "кузнец уже",
]

# Маркеры LOCATION
LOCATION_MARKERS = [
    "кузня", "кузница", "таверн", "пристройк", "город", "улиц", "дом",
    "горн", "лежанк", "стойк", "зал", "кухн",
]

# Маркеры BELIEF_SEED
BELIEF_MARKERS = [
    "верит", "знает", "понимает", "думает", "считает",
    "правил", "закон", "вывод", "истина", "опыт",
]


@dataclass
class EntryView:
    """Нормализованное представление entry для сравнения."""

    ordinal: int
    kind: str
    payload: Dict[str, Any]
    raw: Dict[str, Any]
    text_blobs: List[str]  # все текстовые поля для matching
    provenance: str = ""

    @classmethod
    def from_entry(cls, e: Dict[str, Any]) -> "EntryView":
        payload = e.get("payload", {}) or {}
        blobs: List[str] = []
        # CCH-12: приоритет statement (PORTRET/BELIEF_SEED/DESIRE_SEED) —
        # именно он несёт смысл, не summary/trait.
        _PRIORITY_BLOB_KEYS = (
            "statement", "summary", "trait", "about_hint",
            "target_hint", "name_hint", "observed_hint",
        )
        for key in _PRIORITY_BLOB_KEYS:
            v = payload.get(key)
            if isinstance(v, str) and v.strip():
                blobs.append(v.strip())
        # Дополнительные строковые поля payload (не дублируя приоритетные)
        for k, v in payload.items():
            if k in _PRIORITY_BLOB_KEYS:
                continue
            if isinstance(v, str) and v.strip():
                blobs.append(v.strip())
            elif isinstance(v, dict):
                for vv in v.values():
                    if isinstance(vv, str) and vv.strip():
                        blobs.append(vv.strip())
        prov = e.get("provenance", "")
        return cls(
            ordinal=e.get("ordinal", 0),
            kind=e.get("kind", ""),
            payload=payload,
            raw=e,
            text_blobs=blobs,
            provenance=prov,
        )

    @property
    def combined_text(self) -> str:
        return " ".join(self.text_blobs).lower()


@dataclass
class Match:
    """Сопоставление старой и новой записи."""

    old_ordinal: int
    old_kind: str
    old_text: str
    new_ordinal: int
    new_kind: str
    new_text: str
    score: float
    reason: str  # основание сопоставления


@dataclass
class CrosswalkRow:
    """Строка crosswalk: одна старая запись + её статус."""

    old_ordinal: int
    old_kind: str
    old_summary: str
    status: str  # PRESERVED/RECLASSIFIED/MERGED/DUPLICATED/LOST/AMBIGUOUS
    matches: List[Match] = field(default_factory=list)
    rationale: str = ""


# ── Загрузка ────────────────────────────────────────────────────────────────

def load_old_canon() -> List[EntryView]:
    data = json.loads(OLD_CANON.read_text(encoding="utf-8-sig"))
    entries = data.get("entries", [])
    return [EntryView.from_entry(e) for e in entries]


def load_new_draft() -> List[EntryView]:
    # CCH-12: utf-8-sig — устойчив к BOM (PowerShell Set-Content -Encoding UTF8)
    data = json.loads(NEW_DRAFT.read_text(encoding="utf-8-sig"))
    doc = data.get("document", {})
    entries = doc.get("entries", [])
    return [EntryView.from_entry(e) for e in entries]


# ── Сходство ─────────────────────────────────────────────────────────────────

_WORD_RE = re.compile(r"[а-яёa-z]+", re.IGNORECASE)


def _tokenize(text: str) -> set:
    return {w.lower() for w in _WORD_RE.findall(text) if len(w) >= 3}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = a & b
    union = a | b
    return len(inter) / len(union) if union else 0.0


def _contains_marker(text: str, markers: List[str]) -> List[str]:
    found = []
    t = text.lower()
    for m in markers:
        if m in t:
            found.append(m)
    return found


def similarity(old: EntryView, new: EntryView) -> Tuple[float, str]:
    """Оценка семантического сходства. Возвращает (score, reason)."""
    old_text = old.combined_text
    new_text = new.combined_text

    if not old_text or not new_text:
        return 0.0, "empty_text"

    # Токенное сходство
    tok_score = _jaccard(_tokenize(old_text), _tokenize(new_text))

    # Маркерный бонус: если в old есть EFFECT-маркер и в new — тоже
    old_eff = _contains_marker(old_text, EFFECT_MARKERS)
    new_eff = _contains_marker(new_text, EFFECT_MARKERS)
    eff_bonus = 0.15 if (old_eff and new_eff and set(old_eff) & set(new_eff)) else 0.0

    old_loc = _contains_marker(old_text, LOCATION_MARKERS)
    new_loc = _contains_marker(new_text, LOCATION_MARKERS)
    loc_bonus = 0.15 if (old_loc and new_loc and set(old_loc) & set(new_loc)) else 0.0

    old_bel = _contains_marker(old_text, BELIEF_MARKERS)
    new_bel = _contains_marker(new_text, BELIEF_MARKERS)
    bel_bonus = 0.15 if (old_bel and new_bel and set(old_bel) & set(new_bel)) else 0.0

    # Substring bonus: если одна запись содержит почти всю другую
    substr_bonus = 0.0
    if len(old_text) > 20 and len(new_text) > 20:
        if old_text[:50] in new_text or new_text[:50] in old_text:
            substr_bonus = 0.3

    score = tok_score + eff_bonus + loc_bonus + bel_bonus + substr_bonus
    score = min(score, 1.0)

    reasons = []
    if tok_score > 0:
        reasons.append(f"tok={tok_score:.2f}")
    if eff_bonus:
        reasons.append(f"effect_markers={old_eff}")
    if loc_bonus:
        reasons.append(f"loc_markers={old_loc}")
    if bel_bonus:
        reasons.append(f"belief_markers={old_bel}")
    if substr_bonus:
        reasons.append("substring_match")

    return score, "; ".join(reasons) if reasons else "no_match"


# ── Crosswalk ───────────────────────────────────────────────────────────────

def crosswalk(old_entries: List[EntryView], new_entries: List[EntryView]) -> List[CrosswalkRow]:
    rows: List[CrosswalkRow] = []
    for old in old_entries:
        candidates: List[Match] = []
        for new in new_entries:
            score, reason = similarity(old, new)
            if score >= 0.2:
                candidates.append(
                    Match(
                        old_ordinal=old.ordinal,
                        old_kind=old.kind,
                        old_text=" | ".join(old.text_blobs)[:200],
                        new_ordinal=new.ordinal,
                        new_kind=new.kind,
                        new_text=" | ".join(new.text_blobs)[:200],
                        score=score,
                        reason=reason,
                    )
                )
        candidates.sort(key=lambda m: m.score, reverse=True)

        # Определение статуса
        if not candidates:
            status = "LOST"
            rationale = "no semantic match (score < 0.2)"
        elif len(candidates) == 1:
            if candidates[0].old_kind == candidates[0].new_kind:
                status = "PRESERVED"
                rationale = f"1 match, same kind ({candidates[0].old_kind})"
            else:
                status = "RECLASSIFIED"
                rationale = (
                    f"1 match, kind changed: "
                    f"{candidates[0].old_kind} → {candidates[0].new_kind}"
                )
        else:
            top_score = candidates[0].score
            second_score = candidates[1].score
            if top_score - second_score < 0.1:
                status = "AMBIGUOUS"
                rationale = (
                    f"multiple candidates with close scores "
                    f"(top={top_score:.2f}, 2nd={second_score:.2f})"
                )
            elif top_score > 0.5 and candidates[0].old_kind == candidates[0].new_kind:
                status = "DUPLICATED"
                rationale = (
                    f">1 matches with same kind (top={top_score:.2f}, "
                    f"2nd={second_score:.2f})"
                )
            else:
                status = "MERGED"
                rationale = (
                    f"meaning distributed across {len(candidates)} new entries "
                    f"(top={top_score:.2f}, 2nd={second_score:.2f})"
                )

        rows.append(
            CrosswalkRow(
                old_ordinal=old.ordinal,
                old_kind=old.kind,
                old_summary=" | ".join(old.text_blobs)[:200],
                status=status,
                matches=candidates[:3],
                rationale=rationale,
            )
        )
    return rows


# ── Вывод ───────────────────────────────────────────────────────────────────

def write_outputs(rows: List[CrosswalkRow], old_entries: List[EntryView],
                  new_entries: List[EntryView]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # JSON
    out_json: Dict[str, Any] = {
        "summary": {
            "old_count": len(old_entries),
            "new_count": len(new_entries),
            "rows": len(rows),
            "by_status": {},
            "by_old_kind": {},
        },
        "rows": [],
        "lost": [],
        "ambiguous": [],
    }

    for r in rows:
        out_json["rows"].append({
            "old_ordinal": r.old_ordinal,
            "old_kind": r.old_kind,
            "old_summary": r.old_summary,
            "status": r.status,
            "rationale": r.rationale,
            "matches": [
                {
                    "new_ordinal": m.new_ordinal,
                    "new_kind": m.new_kind,
                    "new_text": m.new_text,
                    "score": round(m.score, 3),
                    "reason": m.reason,
                }
                for m in r.matches
            ],
        })

    # Сводки
    by_status: Dict[str, int] = {}
    by_kind: Dict[str, Dict[str, int]] = {}
    for r in rows:
        by_status[r.status] = by_status.get(r.status, 0) + 1
        by_kind.setdefault(r.old_kind, {})
        by_kind[r.old_kind][r.status] = by_kind[r.old_kind].get(r.status, 0) + 1
        if r.status == "LOST":
            out_json["lost"].append({
                "ordinal": r.old_ordinal,
                "kind": r.old_kind,
                "summary": r.old_summary,
            })
        elif r.status == "AMBIGUOUS":
            out_json["ambiguous"].append({
                "ordinal": r.old_ordinal,
                "kind": r.old_kind,
                "summary": r.old_summary,
                "candidates_count": len(r.matches),
            })

    out_json["summary"]["by_status"] = by_status
    out_json["summary"]["by_old_kind"] = by_kind

    OUT_JSON.write_text(
        json.dumps(out_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Markdown
    md = ["# Crosswalk: старый канон vs новый draft", ""]
    md.append(f"- Старый канон: {len(old_entries)} записей")
    md.append(f"- Новый draft: {len(new_entries)} записей")
    md.append(f"- Строк crosswalk: {len(rows)}")
    md.append("")
    md.append("## Сводка по статусам")
    md.append("")
    md.append("| Статус | Кол-во |")
    md.append("|--------|--------|")
    for status in ["PRESERVED", "RECLASSIFIED", "MERGED", "DUPLICATED",
                   "LOST", "AMBIGUOUS"]:
        md.append(f"| {status} | {by_status.get(status, 0)} |")
    md.append("")
    md.append("## Сводка по kind (только критичные: EFFECT, LOCATION, BELIEF_SEED)")
    md.append("")
    for kind in ["EFFECT", "LOCATION", "BELIEF_SEED"]:
        if kind in by_kind:
            md.append(f"### {kind}")
            md.append("")
            md.append("| Статус | Кол-во |")
            md.append("|--------|--------|")
            for status, cnt in sorted(by_kind[kind].items()):
                md.append(f"| {status} | {cnt} |")
            md.append("")

    md.append("## LOST (полная потеря)")
    md.append("")
    md.append("| ordinal | kind | summary |")
    md.append("|---------|------|---------|")
    for r in rows:
        if r.status == "LOST":
            md.append(
                f"| {r.old_ordinal} | {r.old_kind} | "
                f"{r.old_summary[:80]} |"
            )
    md.append("")

    md.append("## AMBIGUOUS (неоднозначно)")
    md.append("")
    md.append("| ordinal | kind | summary | candidates |")
    md.append("|---------|------|---------|-----------|")
    for r in rows:
        if r.status == "AMBIGUOUS":
            md.append(
                f"| {r.old_ordinal} | {r.old_kind} | "
                f"{r.old_summary[:80]} | {len(r.matches)} |"
            )
    md.append("")

    md.append("## RECLASSIFIED (kind изменился)")
    md.append("")
    md.append("| ordinal | old_kind | new_kind | old_summary | new_text |")
    md.append("|---------|----------|----------|-------------|----------|")
    for r in rows:
        if r.status == "RECLASSIFIED" and r.matches:
            m = r.matches[0]
            md.append(
                f"| {r.old_ordinal} | {r.old_kind} | {m.new_kind} | "
                f"{r.old_summary[:60]} | {m.new_text[:60]} |"
            )
    md.append("")

    md.append("## Полная таблица")
    md.append("")
    md.append("| ordinal | kind | status | rationale |")
    md.append("|---------|------|--------|-----------|")
    for r in rows:
        md.append(
            f"| {r.old_ordinal} | {r.old_kind} | {r.status} | "
            f"{r.rationale} |"
        )

    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"[ok] crosswalk written:")
    print(f"  JSON: {OUT_JSON}")
    print(f"  MD:   {OUT_MD}")


def main() -> int:
    if not OLD_CANON.exists():
        print(f"ERROR: old canon not found: {OLD_CANON}", file=sys.stderr)
        return 2
    if not NEW_DRAFT.exists():
        print(f"ERROR: new draft not found: {NEW_DRAFT}", file=sys.stderr)
        return 2

    old = load_old_canon()
    new = load_new_draft()
    print(f"Old canon: {len(old)} entries")
    print(f"New draft: {len(new)} entries")

    rows = crosswalk(old, new)
    write_outputs(rows, old, new)

    # Печать сводки в stdout
    by_status: Dict[str, int] = {}
    for r in rows:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    print("\n=== Сводка по статусам ===")
    for status in ["PRESERVED", "RECLASSIFIED", "MERGED", "DUPLICATED",
                   "LOST", "AMBIGUOUS"]:
        print(f"  {status:15s}: {by_status.get(status, 0)}")

    print("\n=== По kind (критичные) ===")
    by_kind: Dict[str, Dict[str, int]] = {}
    for r in rows:
        by_kind.setdefault(r.old_kind, {})
        by_kind[r.old_kind][r.status] = by_kind[r.old_kind].get(r.status, 0) + 1
    for kind in ["EFFECT", "LOCATION", "BELIEF_SEED"]:
        if kind in by_kind:
            print(f"  {kind}:")
            for status, cnt in sorted(by_kind[kind].items()):
                print(f"    {status:15s}: {cnt}")

    return 0


if __name__ == "__main__":
    sys.exit(main())