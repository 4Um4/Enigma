#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
corpus_understanding.py — «поняла / не поняла» по каждому пункту Все.md.

Что делает:
  1) Читает канонический корпус (docs/Прошлое персонажей черновик/Все.md).
  2) Читает LLM-черновики (saves/silver_wolf/chronicle_drafts/*.json)
     и канон (config/npc/chronicles/*.json) — если они есть.
  3) Для каждого пункта биографии считает покрытие записями черновика:
       OK  (✓ поняла)   — лучшая запись покрывает >= 35% значимых слов пункта
       PART(~ частично) — 18–35%
       MISS(✗ не поняла)— < 18%
     Слова нормализуются (регистр, ё→е), стоп-слова отбрасываются.
  4) Пишет отчёт reports/UNDERSTANDING_silver_wolf.md + краткий вывод в консоль.

Важно: это ПЕРВИЧНАЯ ОЦЕНКА по совпадению слов, не приговор —
финальное слово за Мастером (калибровка). Скрипт ничего не меняет в игре:
он только читает файлы и пишет свой отчёт.

Запуск из корня проекта:
    python scripts/corpus_understanding.py
Пороги можно менять ниже (FULL_T / PART_T).
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# ----------------------------- НАСТРОЙКИ ---------------------------------

FULL_T = 0.35   # порог "поняла": доля значимых слов пункта в записи
PART_T = 0.18   # порог "частично"

# Персонаж Все.md -> файл черновика (если файлы переименуют — поправить здесь)
NPC_FILES = {
    "ЛЮСЯ":   "maid_lusya.json",
    "ТОРНИН": "tavern_keeper_tornin.json",
    "БОРКО":  "guard_borko.json",
    "ГОРАН":  "merchant_goran.json",
    "ОРМ":    "blacksmith_orm.json",
    "ТЕНЬ":   "thief_shadow.json",
}

WORLD_SECTIONS = ("КАРТА ПРАВДЫ", "СИММЕТРИИ СЦЕНЫ", "ПРАВДА И ВЕРСИИ")

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

# --------------------------- ПАРСИНГ КОРПУСА -----------------------------

ITEM_RE = re.compile(r"^(\d+)\.\s*(.*)$")
HEAD_RE = re.compile(r"^##\s+(.*)$")


def parse_corpus(text):
    """Все.md -> (персонажи, мировые секции)."""
    chars, world = [], []
    cur = None
    mode = None  # 'npc' | 'world'
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line == "---":
            continue
        if line.startswith("*") and not line.startswith("**"):
            continue  # курсивные подписи
        m = HEAD_RE.match(line)
        if m:
            head = m.group(1).strip()
            base = head.split("(")[0].strip().upper()
            if base.startswith(WORLD_SECTIONS):
                mode, cur = "world", {"title": base, "items": [], "table_rows": 0}
                world.append(cur)
            else:
                mode, cur = "npc", {"name": base, "passport": "", "items": []}
                chars.append(cur)
            continue
        if line.startswith("#") or line.startswith("|"):
            if cur is not None and mode == "world" and line.startswith("|"):
                cur["table_rows"] += 1
            continue
        if cur is None:
            continue  # шапка документа
        m = ITEM_RE.match(line)
        if m:
            body = m.group(2).replace("**", "").strip()
            cur["items"].append({"n": int(m.group(1)), "text": body})
        else:
            if mode == "npc" and not cur["items"]:
                if not cur["passport"]:
                    cur["passport"] = line
            elif cur["items"]:
                cur["items"][-1]["text"] += " " + line.replace("**", "")
            # мировой слой: ненумерованные подписи не считаем пунктами
    return chars, world


# --------------------------- ЧЕРНОВИКИ / КАНОН ----------------------------

def load_doc(path):
    """Читает json-документ, вытаскивает список записей (оборонительно)."""
    try:
        raw = Path(path).read_text(encoding="utf-8-sig")
        doc = json.loads(raw)
    except FileNotFoundError:
        return None, []
    except Exception as exc:  # битый json не должен ронять отчёт
        return {"error": str(exc)}, []
    if isinstance(doc, list):
        return {}, doc
    if not isinstance(doc, dict):
        return {}, []
    entries = None
    for key in ("entries", "llm_draft", "draft"):
        val = doc.get(key)
        if isinstance(val, list) and val:
            entries = val
            break
    if entries is None:
        candidates = [
            v for v in doc.values()
            if isinstance(v, list) and v and all(isinstance(e, dict) for e in v)
        ]
        entries = max(candidates, key=len) if candidates else []
    meta = {k: doc.get(k) for k in
            ("chronicle_id", "npc_ref", "canonical", "game_start_age")
            if k in doc}
    return meta, entries


def entry_text(entry):
    """Все строки записи (summary, payload, всё) в один мешок слов."""
    parts = []

    def walk(value):
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, dict):
            for sub in value.values():
                walk(sub)
        elif isinstance(value, (list, tuple)):
            for sub in value:
                walk(sub)

    walk(entry)
    return " ".join(parts)


def entry_kind(entry):
    for key in ("kind", "entry_kind", "type"):
        val = entry.get(key)
        if isinstance(val, str) and val:
            return val
    return "?"


def tokens(text):
    normalized = text.lower().replace("ё", "е")
    return {w for w in WORD_RE.findall(normalized)
            if len(w) >= 3 and w not in STOPWORDS}


def coverage(item_tokens, entry_tokens):
    if not item_tokens:
        return 0.0
    return len(item_tokens & entry_tokens) / len(item_tokens)


# ------------------------------- ОТЧЁТ ------------------------------------

STATUS_SYM = {"OK": "✓", "PART": "~", "MISS": "✗"}


def classify_items(items, entries):
    """Каждому пункту — статус + лучшие записи."""
    etoks = [tokens(entry_text(e)) for e in entries]
    kinds = [entry_kind(e) for e in entries]
    out = []
    for item in items:
        itoks = tokens(item["text"])
        best, matched = 0.0, []
        for idx, etok in enumerate(etoks):
            cov = coverage(itoks, etok)
            best = max(best, cov)
            if cov >= PART_T:
                matched.append((cov, kinds[idx]))
        matched.sort(key=lambda p: p[0], reverse=True)
        if best >= FULL_T:
            status = "OK"
        elif best >= PART_T:
            status = "PART"
        else:
            status = "MISS"
        out.append({
            "n": item["n"],
            "text": item["text"],
            "status": status,
            "best": best,
            "matched": matched,
        })
    return out


def shorten(text, limit=110):
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def build_report(corpus_path, drafts_dir, canon_dir, chars, world, per_npc):
    lines = []
    add = lines.append
    add("# ОТЧЁТ ПОНИМАНИЯ — «Все.md» → черновики silver_wolf")
    add("")
    add(f"- Корпус: `{corpus_path}`")
    add(f"- Черновики: `{drafts_dir}` · Канон: `{canon_dir}`")
    add(f"- Дата: {datetime.now():%Y-%m-%d %H:%M}")
    add(f"- Пороги: ✓ поняла ≥{int(FULL_T * 100)}% значимых слов пункта в записи;"
        f" ~ частично {int(PART_T * 100)}–{int(FULL_T * 100)}%; ✗ ниже")
    add("- Это первичная оценка по совпадению слов (без морфологии и парафраза).")
    add("  Финальное слово за Мастером — отсюда берутся кандидаты калибровки.")
    add("")
    add("## СВОДКА")
    add("")
    add("| Персонаж | Пунктов | ✓ Поняла | ~ Частично | ✗ Не поняла | Записей (черновик/канон) |")
    add("|---|---|---|---|---|---|")
    tot = {"items": 0, "ok": 0, "part": 0, "miss": 0}
    for name, info in per_npc.items():
        row = info["stats"]
        tot["items"] += row["items"]
        tot["ok"] += row["ok"]
        tot["part"] += row["part"]
        tot["miss"] += row["miss"]
        add(f"| {name} ({info['file']}) | {row['items']} | {row['ok']} | "
            f"{row['part']} | {row['miss']} | {row['draft_n']} / {row['canon_n']} |")
    pct = 100 * (tot["ok"] + tot["part"]) / tot["items"] if tot["items"] else 0.0
    add(f"| **ИТОГО** | **{tot['items']}** | **{tot['ok']}** | **{tot['part']}** | "
        f"**{tot['miss']}** | — |")
    add("")
    add(f"**Понято (полностью + частично): {pct:.0f}% корпуса.**")
    add("")

    for name, info in per_npc.items():
        add(f"## {name} — {info['file']}")
        add("")
        if info["passport"]:
            add(f"Паспорт: {info['passport']}")
            add("")
        if info["error"]:
            add(f"(!) {info['error']}")
            add("")
            continue
        if not info["classified"] or all(c["status"] == "MISS" for c in info["classified"]):
            if info["stats"]["draft_n"] == 0:
                add("(!) Черновик пуст или не найден — все пункты «не поняла».")
                add("")
        for status, title in (("OK", "Поняла"), ("PART", "Частично"), ("MISS", "Не поняла")):
            group = [c for c in info["classified"] if c["status"] == status]
            if not group:
                continue
            add(f"### {STATUS_SYM[status]} {title} — {len(group)}")
            add("")
            for c in group:
                kinds = ", ".join(f"{k} {int(cov * 100)}%" for cov, k in c["matched"][:3])
                if kinds:
                    add(f"- **п.{c['n']}** {shorten(c['text'])} → {kinds}")
                else:
                    add(f"- **п.{c['n']}** {shorten(c['text'])} (0 записей)")
            add("")

    if world:
        add("## АВТОРСКИЙ СЛОЙ (в NPC-черновики не входит)")
        add("")
        for sec in world:
            extra = f" + таблица {sec['table_rows']} строк" if sec["table_rows"] else ""
            add(f"- **{sec['title']}** — {len(sec['items'])} пунктов{extra}: "
                "мировой слой, отдельное решение Мастера (TruthState).")
        add("")
    return "\n".join(lines) + "\n"


# -------------------------------- MAIN ------------------------------------

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Все.md → отчёт «поняла / не поняла»")
    ap.add_argument("--corpus", default="docs/Прошлое персонажей черновик/Все.md")
    ap.add_argument("--drafts", default="saves/silver_wolf/chronicle_drafts")
    ap.add_argument("--canon", default="config/npc/chronicles")
    ap.add_argument("--out", default="reports/UNDERSTANDING_silver_wolf.md")
    args = ap.parse_args()

    corpus_path = Path(args.corpus)
    if not corpus_path.exists():
        print(f"[MISS] corpus not found: {corpus_path}")
        return 1
    chars, world = parse_corpus(corpus_path.read_text(encoding="utf-8-sig"))
    if not chars:
        print("[MISS] no NPC sections found in corpus")
        return 1

    per_npc = {}
    for ch in chars:
        name = ch["name"]
        fname = NPC_FILES.get(name, "")
        draft_meta, draft_entries = load_doc(Path(args.drafts) / fname) if fname else ({}, [])
        canon_meta, canon_entries = load_doc(Path(args.canon) / fname) if fname else ({}, [])
        error = ""
        if fname and draft_meta and "error" in draft_meta:
            error = f"Черновик {fname}: не читается ({draft_meta['error']})"
        if draft_entries:
            classified = classify_items(ch["items"], draft_entries)
        else:
            classified = [
                {"n": it["n"], "text": it["text"], "status": "MISS",
                 "best": 0.0, "matched": []}
                for it in ch["items"]
            ]
        stats = {
            "items": len(ch["items"]),
            "ok": sum(1 for c in classified if c["status"] == "OK"),
            "part": sum(1 for c in classified if c["status"] == "PART"),
            "miss": sum(1 for c in classified if c["status"] == "MISS"),
            "draft_n": len(draft_entries),
            "canon_n": len(canon_entries),
        }
        per_npc[name] = {
            "file": fname or "НЕТ ФАЙЛА",
            "passport": ch["passport"],
            "classified": classified,
            "stats": stats,
            "error": error,
        }
        print(f"{fname or 'NOFILE':<26} items={stats['items']:>2} "
              f"OK={stats['ok']:>2} PART={stats['part']:>2} MISS={stats['miss']:>2} "
              f"draft={stats['draft_n']:>2} canon={stats['canon_n']}")

    report = build_report(corpus_path, args.drafts, args.canon, chars, world, per_npc)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8-sig")
    print(f"[OK] report -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())