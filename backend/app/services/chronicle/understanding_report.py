"""path: backend/app/services/chronicle/understanding_report.py
Назначение: отчёт «поняла / не поняла» по каждому пункту биографии (вердикт
            Мастера: Все.md = канон -> сеялка -> игра показывает понимание).
            Парсит нумерованные пункты из author_text каждого NPC, считает
            покрытие пункта записями хроники по значимым словам (пересечение
            множеств, без морфологии и парафраза) и рендерит отчёт md/json.
            Как и лампочка (trait_gap_detector), это честная первичная
            оценка, не приговор: финальное слово за Мастером. Никаких
            авто-действий по записям.
            Встройка: routes_chronicle GET /{campaign}/understanding —
            по следам trait-gaps (тот же контракт docs_by_npc -> отчёт).
Зависимости: stdlib (вход — ChronicleDocument-подобные документы:
             author_text: str; entries с entry_id/kind/payload)
Основные сущности: parse_items, docs_from_dir, build_report,
                   render_markdown, render_json"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterator, List, Set, Tuple

# ----------------------------- НАСТРОЙКИ ---------------------------------

FULL_T = 0.35   # порог "поняла": доля значимых слов пункта в записи
PART_T = 0.18   # порог "частично"

STATUS_RU = {"OK": "✓ поняла", "PART": "~ частично", "MISS": "✗ не поняла"}

STOPWORDS = {
    "что", "она", "они", "оно", "его", "ее", "ему", "ей", "их", "как", "так",
    "это", "этот", "эта", "эти", "был", "была", "было", "были", "быть",
    "есть", "для", "при", "над", "под", "уже", "еще", "только", "если",
    "чтобы", "там", "тут", "где", "чем", "том", "того", "всех", "весь",
    "вся", "себя", "своей", "своего", "своих", "свою", "когда", "даже",
    "или", "потому", "через", "после", "перед", "без", "между", "один",
    "одна", "одно", "два", "три", "все", "который", "которая",
    "которое", "которые", "просто", "пока", "тоже", "такой", "такая",
    "такое", "такие", "сам", "сама", "сами", "может", "могут", "должен",
}

WORD_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё]+")
ITEM_RE = re.compile(r"^(\d+)\.\s*(.*)$")

# --------------------------- ПАРСИНГ ПУНКТОВ ------------------------------


def parse_items(author_text: str) -> List[Dict[str, Any]]:
    """author_text -> [{'n': int, 'text': str}] — нумерованные пункты.

    Ненумерованные строки до первого пункта (имя, паспорт) пропускаются;
    строки-продолжения присоединяются к предыдущему пункту.
    """
    items: List[Dict[str, Any]] = []
    for raw in (author_text or "").splitlines():
        line = raw.strip()
        m = ITEM_RE.match(line)
        if m:
            items.append({
                "n": int(m.group(1)),
                "text": m.group(2).replace("**", "").strip(),
            })
        elif items and line and line != "---":
            items[-1]["text"] += " " + line.replace("**", "")
    return items


# --------------------- ЧТЕНИЕ ДОКУМЕНТОВ ИЗ КАТАЛОГА ----------------------


def docs_from_dir(base: Any) -> Tuple[Dict[str, Any], List[str]]:
    """Каталог json-документов хроники -> ({npc_id: doc}, [проблемы]).

    Понимает и черновики (saves/<campaign>/chronicle_drafts), и канон
    (config/npc/chronicles) — форма документа одна. Оборонительно:
    utf-8-sig (BOM от PowerShell), битые файлы не роняют отчёт,
    а попадают в проблемы. npc_id: chronicle_id -> npc_ref -> имя файла.
    Записи: ключ entries, иначе llm_draft/draft, иначе самый длинный
    список словарей (прецедент corpus_understanding.load_doc).
    """
    base_path = Path(base)
    docs: Dict[str, Any] = {}
    problems: List[str] = []
    if not base_path.is_dir():
        return docs, [f"каталог не найден: {base_path}"]
    for path in sorted(base_path.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception as exc:  # битый json не должен ронять отчёт
            problems.append(f"{path.name}: не читается ({exc})")
            continue
        if not isinstance(doc, dict):
            problems.append(f"{path.name}: не словарь — пропущен")
            continue
        entries = doc.get("entries")
        if not isinstance(entries, list) or not entries:
            for key in ("llm_draft", "draft"):
                val = doc.get(key)
                if isinstance(val, list) and val:
                    doc = {**doc, "entries": val}
                    break
            else:
                candidates = [
                    v for v in doc.values()
                    if isinstance(v, list) and v
                    and all(isinstance(e, dict) for e in v)
                ]
                if candidates:
                    doc = {**doc, "entries": max(candidates, key=len)}
        npc = doc.get("chronicle_id") or doc.get("npc_ref") or path.stem
        docs[str(npc)] = doc
    return docs, problems


# --------------------------- ТЕКСТ ЗАПИСЕЙ --------------------------------


def _walk_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for sub in value.values():
            yield from _walk_strings(sub)
    elif isinstance(value, (list, tuple)):
        for sub in value:
            yield from _walk_strings(sub)


def _entry_blob(entry: Any) -> str:
    """Все строки записи кроме entry_id (хэш — мусор для покрытия)."""
    if isinstance(entry, dict):
        data: Any = {k: v for k, v in entry.items() if k != "entry_id"}
    elif hasattr(entry, "__dict__"):
        data = {k: v for k, v in vars(entry).items() if k != "entry_id"}
    else:
        data = [str(entry)]
    return " ".join(_walk_strings(data))


def _kind_name(entry: Any) -> str:
    k = getattr(entry, "kind", None)
    if k is None and isinstance(entry, dict):
        k = entry.get("kind")
    if k is None:
        return "?"
    return str(getattr(k, "value", k))


def _entry_id(entry: Any) -> str:
    eid = getattr(entry, "entry_id", None)
    if eid is None and isinstance(entry, dict):
        eid = entry.get("entry_id", "")
    return str(eid or "")


def tokens(text: str) -> Set[str]:
    normalized = text.lower().replace("ё", "е")
    return {
        w for w in WORD_RE.findall(normalized)
        if len(w) >= 3 and w not in STOPWORDS
    }


# ------------------------------- ОТЧЁТ ------------------------------------


def _short(text: str, limit: int = 110) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def build_report(docs_by_npc: Dict[str, Any], campaign: str) -> Dict[str, Any]:
    """Отчёт по каждому NPC и каждому пункту: статус + лучшие записи.

    Контракт входа (как у trait_gap_detector): docs_by_npc[npc_id] =
    документ хроники с author_text и entries (LLM_DRAFT и/или канон).
    Детерминирован (sorted по npc и номеру пункта).
    """
    per_npc: List[Dict[str, Any]] = []
    totals = {"items": 0, "ok": 0, "part": 0, "miss": 0}
    for npc in sorted(docs_by_npc):
        doc = docs_by_npc[npc]
        author_text = getattr(doc, "author_text", None)
        if author_text is None and isinstance(doc, dict):
            author_text = doc.get("author_text", "")
        raw_entries = getattr(doc, "entries", None)
        if raw_entries is None and isinstance(doc, dict):
            raw_entries = doc.get("entries", [])
        entries = list(raw_entries or [])
        items = parse_items(author_text or "")

        etoks = [(tokens(_entry_blob(e)), _kind_name(e), _entry_id(e))
                 for e in entries]
        records: List[Dict[str, Any]] = []
        for it in items:
            itoks = tokens(it["text"])
            best = 0.0
            matched: List[Dict[str, Any]] = []
            for etok, kname, eid in etoks:
                cov = (len(itoks & etok) / len(itoks)) if itoks else 0.0
                best = max(best, cov)
                if cov >= PART_T:
                    matched.append({
                        "entry_id": eid,
                        "kind": kname,
                        "coverage": round(cov, 3),
                    })
            matched.sort(key=lambda m: m["coverage"], reverse=True)
            status = "OK" if best >= FULL_T else ("PART" if best >= PART_T else "MISS")
            records.append({
                "n": it["n"],
                "status": status,
                "best": round(best, 3),
                "matched": matched[:5],
                "text": _short(it["text"]),
            })
        stat = {
            "items": len(items),
            "ok": sum(1 for r in records if r["status"] == "OK"),
            "part": sum(1 for r in records if r["status"] == "PART"),
            "miss": sum(1 for r in records if r["status"] == "MISS"),
            "entries": len(entries),
        }
        for key in ("items", "ok", "part", "miss"):
            totals[key] += stat[key]
        per_npc.append({
            "npc": npc,
            "stats": stat,
            "records": records,
        })

    percent = (
        100 * (totals["ok"] + totals["part"]) / totals["items"]
        if totals["items"] else 0.0
    )
    return {
        "campaign": campaign,
        "thresholds": {"full": FULL_T, "part": PART_T},
        "totals": {**totals, "percent": round(percent, 1)},
        "per_npc": per_npc,
        "note": (
            "Первичная оценка по совпадению значимых слов (без морфологии "
            "и парафраза). Совпадение — основание для проверки глазами, "
            "не приговор: финальное слово за Мастером."
        ),
    }


def render_markdown(rep: Dict[str, Any]) -> str:
    t = rep["totals"]
    lines = [
        f"# Отчёт понимания — кампания «{rep['campaign']}»",
        "",
        f"Пунктов: {t['items']} · ✓ поняла: {t['ok']} · ~ частично: {t['part']}"
        f" · ✗ не поняла: {t['miss']} · **понято {t['percent']}%**",
        "",
        f"Пороги: ✓ ≥{int(rep['thresholds']['full'] * 100)}% значимых слов "
        f"пункта в записи; ~ {int(rep['thresholds']['part'] * 100)}–"
        f"{int(rep['thresholds']['full'] * 100)}%; ✗ ниже.",
        "",
        "| NPC | Пунктов | ✓ | ~ | ✗ | Записей |",
        "|---|---|---|---|---|---|",
    ]
    for block in rep["per_npc"]:
        s = block["stats"]
        lines.append(
            f"| {block['npc']} | {s['items']} | {s['ok']} | {s['part']}"
            f" | {s['miss']} | {s['entries']} |"
        )
    lines.append("")
    for block in rep["per_npc"]:
        lines.append(f"## {block['npc']}")
        lines.append("")
        for status, ru in (("OK", "Поняла"), ("PART", "Частично"), ("MISS", "Не поняла")):
            group = [r for r in block["records"] if r["status"] == status]
            if not group:
                continue
            lines.append(f"### {STATUS_RU[status]} — {len(group)}")
            lines.append("")
            for r in group:
                kinds = ", ".join(
                    f"{m['kind']} {int(m['coverage'] * 100)}%"
                    for m in r["matched"][:3]
                )
                if kinds:
                    lines.append(f"- **п.{r['n']}** {r['text']} → {kinds}")
                else:
                    lines.append(f"- **п.{r['n']}** {r['text']} (0 записей)")
            lines.append("")
    if rep.get("problems"):
        lines.append("## Проблемы чтения")
        lines.append("")
        for p in rep["problems"]:
            lines.append(f"- {p}")
        lines.append("")
    lines.append(f"_{rep['note']}_")
    return "\n".join(lines)


def render_json(rep: Dict[str, Any]) -> str:
    return json.dumps(rep, ensure_ascii=False, indent=2)
