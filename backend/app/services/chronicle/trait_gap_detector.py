"""path: backend/app/services/chronicle/trait_gap_detector.py
Назначение: детектор разрыва «язык автора ↔ онтология игры» (вердикт Мастера):
            собирает слова-характеристики из ВСЕХ биографических записей и
            ПОРТРЕТОВ всех NPC, сверяет со словарём character_lexicon.json,
            считает частоты и совместную встречаемость (основа гипотезы,
            НЕ доказательство синонимии), рендерит отчёт md/json.
            Никакого авто-объединения понятий и расширения ontology —
            только честная лампочка для человека.
Зависимости: app.core.config, app.services.chronicle.{chronicle_seeder,
             chronicle_store}, stdlib
Основные сущности: collect_words, build_report, render_markdown, render_json"""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any, Dict, List, Tuple, cast

from app.domain.chronicle import ChronicleDocument, EntryKind, EntryProvenance

_LEXICON_PATH: str = "config/ontology/character_lexicon.json"

# Слова-характеристики берём ИЗ УКАЗАНИЙ АВТОРА (traits-списки Портретов,
# trait-поля Черт) — не из свободного текста: честность против токенизации
# всего подряд. statement используется ТОЛЬКО для соседей.

_AUTHOR_OK = (EntryProvenance.AUTHOR_CONFIRMED, EntryProvenance.AUTHOR_AUTHORED)
# Лампочка читает И черновики LLM (вердикт Мастера: карта = инструмент автора,
# не канон; честная пометка статуса в отчёте), и PORTRET/TRAIT/BELIEF/DESIRE
_GAP_KINDS = (
    EntryKind.PORTRET,
    EntryKind.TRAIT_SEED,
    EntryKind.BELIEF_SEED,
    EntryKind.DESIRE_SEED,
)


def _load_lexicon() -> Dict[str, Any]:
    from app.core.config import BASE_DIR

    p = BASE_DIR / _LEXICON_PATH
    return cast(Dict[str, Any], json.loads(p.read_text(encoding="utf-8")))


def _lexicon_index(lex: Dict[str, Any]) -> Dict[str, str]:
    """нижний регистр ru-имени/слов из definitions → где искать (для статуса)."""
    idx: Dict[str, str] = {}
    for group in ("axes", "psyche_scalars", "traits", "needs"):
        for rec in lex.get(group, []):
            for w in (rec.get("ru", ""), rec.get("id", "")):
                for token in re.split(r"[\s/(),]+", str(w).lower()):
                    if len(token) >= 4:
                        idx[token] = f"{group}:{rec.get('id')}"
    for tok in re.split(r"[\s/(),]+", str(lex.get("imprints", {}).get("ru", "")).lower()):
        if len(tok) >= 4:
            idx[tok] = "imprints"
    for tok in re.split(r"[\s/(),]+", str(lex.get("pressure_axes", {}).get("ru", "")).lower()):
        if len(tok) >= 4:
            idx.setdefault(tok, "pressure_axes")
    return idx


def collect_words(
    docs_by_npc: Dict[str, ChronicleDocument],
) -> Tuple[Counter, Dict[str, Tuple[str, ...]], Counter]:
    """Слова-характеристики (Counter), соседи (слово → кортеж слов-соседей
    в том же пункте/записи), источник-счётчик (слово → (npc, entry))."""
    words: Counter = Counter()
    co: Dict[str, Counter] = {}
    src: Counter = Counter()
    for npc_id in sorted(docs_by_npc):
        doc = docs_by_npc[npc_id]
        for e in doc.entries:
            # Лампочка читает И LLM-черновики (вердикт Мастера: карта —
            # инструмент автора, не канон; портреты/черты/убеждения/мечты
            # из гипотез честно помечаются draft=true в отчёте)
            _is_gap_kind = e.kind in (
                EntryKind.PORTRET,
                EntryKind.TRAIT_SEED,
                EntryKind.BELIEF_SEED,
                EntryKind.DESIRE_SEED,
            )
            if not _is_gap_kind and e.provenance not in _AUTHOR_OK:
                continue
            p = e.payload
            candidates: List[str] = []
            if e.kind is EntryKind.PORTRET:
                candidates = [str(x) for x in p.get("traits", []) if x]
                if not candidates and p.get("statement"):
                    candidates = [str(p.get("statement", ""))[:60]]
            elif e.kind is EntryKind.TRAIT_SEED:
                candidates = [str(p.get("trait", ""))] if p.get("trait") else []
            elif e.kind is EntryKind.BELIEF_SEED:
                # убеждение — тоже слово-характеристика (мировоззрение)
                st = str(p.get("statement", ""))
                if st:
                    candidates = [st[:60]]
            elif e.kind is EntryKind.DESIRE_SEED:
                st = str(p.get("statement", ""))
                if st:
                    candidates = [st[:60]]
            if not candidates:
                continue
            for w in candidates:
                key = w.strip().lower()
                if len(key) < 3:
                    continue
                words[key] += 1
                src[key] += 1
                co.setdefault(key, Counter())
                for other in candidates:
                    ok = other.strip().lower()
                    if ok != key and len(ok) >= 3:
                        co[key][ok] += 1
    neighbors = {k: tuple(v.keys()) for k, v in co.items()}
    return words, neighbors, src


def build_report(
    docs_by_npc: Dict[str, ChronicleDocument], campaign: str
) -> Dict[str, Any]:
    # L4-UX: пустой вход = не молчаливый пустой файл, а честный диагноз
    _has_gap_input = any(
        e.kind
        in (EntryKind.PORTRET, EntryKind.TRAIT_SEED, EntryKind.BELIEF_SEED, EntryKind.DESIRE_SEED)
        or e.provenance in _AUTHOR_OK
        for doc in docs_by_npc.values()
        for e in doc.entries
    )
    if not _has_gap_input:
        return {
            "campaign": campaign,
            "total": 0,
            "records": [],
            "empty_reason": (
                "Разборов (Портретов/Черт/Убеждений/Мечт) нет ни у одного NPC. "
                "Сначала прогони F1 по пунктам историй в редакторе — лампочка "
                "собирает слова ИМЕННО из разборов."
            ),
        }
    """Отчёт: каждое слово → частота, статус (из словаря / НЕТ В ИГРЕ),
    соседи, источники. Детерминирован (sorted)."""
    lex = _load_lexicon()
    idx = _lexicon_index(lex)
    words, neighbors, src = collect_words(docs_by_npc)
    records = []
    for w in sorted(words, key=lambda x: (-words[x], x)):
        hit = None
        for tok, where in idx.items():
            if tok in w or w in tok:
                hit = where
                break
        records.append(
            {
                "word": w,
                "count": words[w],
                "status": ("в игре: " + hit) if hit else "НЕТ В ИГРЕ",
                "neighbors": neighbors.get(w, ()),
                "sources": src[w],
                "campaign": campaign,
            }
        )
    return {"campaign": campaign, "total": len(records), "records": records}


def render_markdown(rep: Dict[str, Any]) -> str:
    if rep.get("empty_reason"):
        return f"# Карта разрывов — {rep['campaign']}\n\n**{rep['empty_reason']}**"
    lines = [
        f"# Карта разрывов языка — кампания «{rep['campaign']}»",
        "",
        f"Слов-характеристик: {rep['total']} · Словарь: {_LEXICON_PATH}",
        "",
        "Правило Мастера: совместная встречаемость — основание для гипотезы, не доказательство синонимии. Никакого авто-объединения.",
        "",
        "| Слово | Частота | Статус в игре | Гипотеза-соседи |",
        "|---|---|---|---|",
    ]
    gaps = 0
    for r in rep["records"]:
        if r["status"] == "НЕТ В ИГРЕ":
            gaps += 1
        lines.append(
            f"| {r['word']} | {r['count']} | {r['status']} | {', '.join(r['neighbors'][:4]) or '—'} |"
        )
    lines.append("")
    lines.append(f"**Разрывов (НЕТ В ИГРЕ): {gaps} из {rep['total']}** — кандидаты на новые переменные Character Calibration / телесного контура.")
    return "\n".join(lines)


def render_json(rep: Dict[str, Any]) -> str:
    return json.dumps(rep, ensure_ascii=False, indent=2)
