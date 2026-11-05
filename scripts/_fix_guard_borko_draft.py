"""USL-2 P2 §3: правки guard_borko draft после семантической проверки.

Мандат Мастера (MASTER DECISION 2026-11-05):
  G1 (a): SUBJECT_ATTRIBUTION_ERROR — LLM перепутала Борко <-> Орм
    Список: 8 entries (#13, #23, #32, #33 x2, #37, #55, #56, #57)
    Не делать глобальную замену "Орм" -> "Борко" (Орм - отдельный персонаж)
    Заменять только там, где контекст однозначно указывает на Борко
  G2 (a): SEMANTIC_OMISSION — entry #24 (DESIRE_SEED) опущено "мастурбировать"
    Нормализация: "Хочет снова наблюдать за этим зрелищем и мастурбировать, не участвуя непосредственно в насилии"

Дополнительно (зафиксировано, НЕ исправлено — для решения Мастера):
  SEMANTIC_INVERSION — entry #19 (TRAIT_SEED "привык к насилию")
    LLM инвертировала смысл фрагмента 12: автор писал "никогда в жизни
    ему не представлялся шанс пережить секс, который берут силой"
    (Борко НЕ привык к насилию), а LLM сделала trait "привык к насилию"
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

DRAFT_PATH = Path("saves/Open_road/chronicle_drafts/guard_borko.json")

# SUBJECT_ATTRIBUTION_ERROR fixes: replace "Орм" with "Борко" in specific entries
SUBJECT_FIXES = [
    # entry #13 (RELATIONSHIP, fragment 9): "Гильдия воров прекрасно понимает, что Орм..."
    ("Гильдия воров прекрасно понимает, что Орм", "summary",
     "Орм ничего собой не представляет",
     "Борко ничего собой не представляет",
     "entry #13 (fragment 9)"),
    # entry #23 (PORTRET, fragment 14): "Орм не женился"
    ("Орм не женился", "statement",
     "Орм не женился",
     "Борко не женился",
     "entry #23 (fragment 14)"),
    # entry #32 (PORTRET, fragment 18): "Орм мечтает стать хозяином"
    ("Орм мечтает стать хозяином", "statement",
     "Орм мечтает",
     "Борко мечтает",
     "entry #32 (fragment 18)"),
    # entry #33 (RELATIONSHIP, fragment 18): "Орм не любит Торнина"
    ("Орм не любит Торнина", "summary",
     "Орм не любит Торнина",
     "Борко не любит Торнина",
     "entry #33 (fragment 18, first Орм)"),
    # entry #33 (RELATIONSHIP, fragment 18): "Орм хочет завладеть трактиром"
    ("Орм хочет завладеть трактиром", "summary",
     "Орм хочет завладеть трактиром",
     "Борко хочет завладеть трактиром",
     "entry #33 (fragment 18, second Орм)"),
    # entry #37 (RELATIONSHIP, fragment 20): "Орм не знаком с Тенью"
    ("Орм не знаком с Тенью", "summary",
     "Орм не знаком с Тенью",
     "Борко не знаком с Тенью",
     "entry #37 (fragment 20)"),
    # entry #55 (PORTRET, fragment 26): "Орм садится за угловой стол"
    ("Орм садится за угловой стол", "statement",
     "Орм садится за угловой стол",
     "Борко садится за угловой стол",
     "entry #55 (fragment 26)"),
    # entry #56 (EVENT, fragment 26): "Орм садится за стол" (summary - short)
    ("Орм садится за стол", "summary",
     "Орм садится за стол",
     "Борко садится за стол",
     "entry #56 (fragment 26)"),
    # entry #57 (PORTRET, fragment 27): "Орм говорит с Люсей"
    ("Орм говорит с Люсей", "statement",
     "Орм говорит с Люсей",
     "Борко говорит с Люсей",
     "entry #57 (fragment 27)"),
]

# SEMANTIC_OMISSION fix
OMISSION_FIX = [
    # entry #24 (DESIRE_SEED, fragment 13): restore "мастурбировать"
    ("хочет наблюдать за насилием без участия в нём", "statement",
     "хочет наблюдать за насилием без участия в нём",
     "хочет снова наблюдать за этим зрелищем и мастурбировать, не участвуя непосредственно в насилии",
     "entry #24 (fragment 13)"),
]

# SEMANTIC_INVERSION (flag only, don't auto-fix — needs Master decision)
INVERSION_FLAG = [
    # entry #19 (TRAIT_SEED): trait "привык к насилию" inverts author's fragment 12
    ("привык к насилию", "trait",
     "автор fragment 12: 'никогда в жизни ему не представлялся шанс пережить секс, который берут силой'",
     "entry #19"),
]


def main():
    if not DRAFT_PATH.exists():
        print(f"Draft не найден: {DRAFT_PATH}", file=sys.stderr)
        return 1

    bak_path = DRAFT_PATH.with_suffix(".json.bak")
    shutil.copy(DRAFT_PATH, bak_path)
    print(f"[0] Backup: {bak_path}")

    with DRAFT_PATH.open("r", encoding="utf-8-sig") as f:
        draft = json.load(f)

    entries = draft["entries"]
    print(f"[1] Загружен draft: {len(entries)} entries")

    fixed_count = 0
    flagged_count = 0

    print(f"\n[2] SUBJECT_ATTRIBUTION_ERROR fixes (8 expected):")
    for search_str, field, old, new, desc in SUBJECT_FIXES:
        found = False
        for e in entries:
            payload = e.get("payload", {})
            val = str(payload.get(field, ""))
            if search_str in val:
                if old in val:
                    new_val = val.replace(old, new)
                    payload[field] = new_val
                    print(f"  FIXED {desc}: '{old}' -> '{new[:40]}...'")
                    fixed_count += 1
                    found = True
                    break
                else:
                    print(f"  WARN {desc}: entry found, but '{old}' not in '{field}'")
                    found = True
                    break
        if not found:
            print(f"  WARN {desc}: entry not found by '{search_str}'")

    print(f"\n[3] SEMANTIC_OMISSION fixes (1 expected):")
    for search_str, field, old, new, desc in OMISSION_FIX:
        found = False
        for e in entries:
            payload = e.get("payload", {})
            val = str(payload.get(field, ""))
            if search_str in val:
                payload[field] = new
                print(f"  FIXED {desc}: restored both components")
                print(f"    Old: '{old}'")
                print(f"    New: '{new}'")
                fixed_count += 1
                found = True
                break
        if not found:
            print(f"  WARN {desc}: entry not found")

    print(f"\n[4] SEMANTIC_INVERSION (flagged for Master, NOT auto-fixed):")
    for search_str, field, evidence, desc in INVERSION_FLAG:
        for e in entries:
            payload = e.get("payload", {})
            val = str(payload.get(field, ""))
            if search_str in val:
                print(f"  FLAGGED {desc}")
                print(f"    Current: trait='{val}'")
                print(f"    Evidence: {evidence}")
                print(f"    Suggested trait: 'впервые испытал возбуждение от насилия (ранее секс был только добровольным)'")
                print(f"    Action needed: Master decision (trait inverts author's meaning)")
                flagged_count += 1
                break

    tmp_path = DRAFT_PATH.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)
    tmp_path.replace(DRAFT_PATH)
    print(f"\n[5] Draft сохранён: {DRAFT_PATH}")
    print(f"  Fixed: {fixed_count}")
    print(f"  Flagged for Master: {flagged_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())