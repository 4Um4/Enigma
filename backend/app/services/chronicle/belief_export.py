"""path: backend/app/services/chronicle/belief_export.py
Назначение: CCH-4/C2 — сборщик сводки убеждений («Сохранить как…»):
            BELIEF_SEED из канонов + черновиков кампании → один файл
            для анализа человеком/LLM. НЕ runtime SSOT, НЕ слияние;
            статусы честные (канон+реестр → runtime-compatible; канон без
            типа → unknown-type; черновик LLM → needs-confirmation —
            INV-LLM-NOT-SSOT). Порядок детерминирован (npc_id, ordinal).
Зависимости: app.domain.chronicle, app.models.npc.beliefs, stdlib
Основные сущности: STATUS_*, collect_belief_seeds, render_markdown, render_json"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from app.domain.chronicle import ChronicleDocument, EntryKind, EntryProvenance

_PL_STATEMENT = "statement"
_PL_BELIEF_TYPE = "belief_type"

STATUS_RUNTIME = "runtime-compatible"
STATUS_UNKNOWN = "unknown-type"
STATUS_NEEDS = "needs-confirmation"

_AUTHOR_OK = (EntryProvenance.AUTHOR_CONFIRMED, EntryProvenance.AUTHOR_AUTHORED)


def collect_belief_seeds(docs_by_npc: Dict[str, ChronicleDocument]) -> List[Dict[str, Any]]:
    """BELIEF_SEED всех документов → записи сводки. Порядок: (npc_id, ordinal).
    Черновик (doc.canonical=False) всегда needs-confirmation: канон = снимок
    (вердикт S336) — без канонизации рантайм-сеять нельзя."""
    from app.models.npc.beliefs import BeliefType

    registry = {t.value for t in BeliefType}
    out: List[Dict[str, Any]] = []
    for npc_id in sorted(docs_by_npc):
        doc = docs_by_npc[npc_id]
        for e in sorted(doc.entries, key=lambda x: x.ordinal):
            if e.kind is not EntryKind.BELIEF_SEED:
                continue
            btype = e.payload.get(_PL_BELIEF_TYPE)
            if doc.canonical and e.provenance in _AUTHOR_OK:
                status = STATUS_RUNTIME if btype in registry else STATUS_UNKNOWN
            else:
                status = STATUS_NEEDS
            out.append(
                {
                    "npc_id": npc_id,
                    "statement": str(e.payload.get(_PL_STATEMENT, "")),
                    "belief_type": btype,
                    "status": status,
                    "source": f"{doc.chronicle_id}:{e.entry_id}",
                    "canonical": doc.canonical,
                    "historical_age": e.historical_age,
                }
            )
    return out


def render_json(records: List[Dict[str, Any]], campaign: str) -> str:
    payload = {"campaign": campaign, "kind": "belief_seeds_export", "records": records}
    return json.dumps(payload, ensure_ascii=False, indent=2)


def render_markdown(records: List[Dict[str, Any]], campaign: str) -> str:
    lines: List[str] = [
        f"# Сводка убеждений — кампания «{campaign}»",
        "",
        f"Записей: {len(records)} · Источник: Character Chronicle (каноны + черновики)",
        "",
        "| NPC | Формулировка | Тип | Статус | Источник | Возраст |",
        "|---|---|---|---|---|---|",
    ]
    for r in records:
        age = "—" if r["historical_age"] is None else str(r["historical_age"])
        lines.append(
            f"| {r['npc_id']} | {r['statement']} | {r['belief_type'] or '—'} "
            f"| {r['status']} | {r['source']} | {age} |"
        )
    lines.append("")
    lines.append(
        "Статусы: runtime-compatible — тип из реестра, сеется при новой игре; "
        "unknown-type — тип не определён/вне реестра (кандидат в онтологию); "
        "needs-confirmation — черновик LLM, не канон."
    )
    return "\n".join(lines)
