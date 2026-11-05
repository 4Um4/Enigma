"""USL-2 / ТЗ АРХИТЕКТОРУ: правки merchant_goran draft Q-M1/Q-M2/Q-M3/Q-M4.

Q-M1 (a): entries #38, #39 SUBJECT_ATTRIBUTION_ERROR «Орм» → «Горан» (фрагмент 13)
Q-M2 (a): entry #22 DIRECTION_INVERSION — Горан подошёл к Орму, не наоборот (фрагмент 9)
Q-M3 (a): entry #12 ENTITY_CONFUSION — гильдия купцов, не воров (фрагмент 5)
Q-M4 (a): удалить entry #1 SPURIOUS_REFERENCE — Люся без источника (entry_id to find)
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

DRAFT_PATH = Path("saves/Open_road/chronicle_drafts/merchant_goran.json")


def main() -> int:
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
    fixed = 0
    deleted = 0

    # Найти entry_id для каждого из 4 проблемных entries (по точным сигнатурам)
    q_m1_e38_id = None  # PORTRET «Орм говорит о пристраивании детей и жены»
    q_m1_e39_id = None  # EVENT «Орм пристрояет детей и жену»
    q_m2_e22_id = None  # RELATIONSHIP «Орм договорился о передаче надёжного оружия Горану»
    q_m3_e12_id = None  # EVENT «не может найти работу из-за подозрений гильдии воров»
    q_m4_e1_id = None   # RELATIONSHIP «Люся терпит его, потому что он их кузнец»

    for e in entries:
        text = json.dumps(e.get("payload", {}), ensure_ascii=False)
        if q_m1_e38_id is None and "Орм говорит о пристраивании" in text:
            q_m1_e38_id = e.get("entry_id")
        if q_m1_e39_id is None and "Орм пристрояет детей" in text:
            q_m1_e39_id = e.get("entry_id")
        if q_m2_e22_id is None and "Орм договорился о передаче" in text:
            q_m2_e22_id = e.get("entry_id")
        if q_m3_e12_id is None and "подозрений гильдии воров" in text and "работ" in text:
            q_m3_e12_id = e.get("entry_id")
        if q_m4_e1_id is None and "Люся терпит его" in text:
            q_m4_e1_id = e.get("entry_id")

    print(f"\n[2] Найдены target entry_ids:")
    print(f"  Q-M1 e38: {q_m1_e38_id}")
    print(f"  Q-M1 e39: {q_m1_e39_id}")
    print(f"  Q-M2 e22: {q_m2_e22_id}")
    print(f"  Q-M3 e12: {q_m3_e12_id}")
    print(f"  Q-M4 e1 (to delete): {q_m4_e1_id}")

    # Q-M1: править entries #38, #39
    print(f"\n[Q-M1] SUBJECT_ATTRIBUTION_ERROR (entries #38, #39):")
    for e in entries:
        if e.get("entry_id") == q_m1_e38_id:
            old_stmt = e.get("payload", {}).get("statement", "")
            new_stmt = old_stmt.replace("Орм говорит о пристраивании детей и жены", "Горан говорит о пристраивании детей и жены")
            e["payload"]["statement"] = new_stmt
            print(f"  e38 OLD: {old_stmt[:80]}...")
            print(f"  e38 NEW: {new_stmt[:80]}...")
            fixed += 1
        if e.get("entry_id") == q_m1_e39_id:
            old_sum = e.get("payload", {}).get("summary", "")
            new_sum = old_sum.replace("Орм пристрояет детей и жену", "Горан пристроил детей и жену")
            e["payload"]["summary"] = new_sum
            print(f"  e39 OLD: {old_sum}")
            print(f"  e39 NEW: {new_sum}")
            fixed += 1

    # Q-M2: править entry #22 (DIRECTION_INVERSION)
    print(f"\n[Q-M2] DIRECTION_INVERSION (entry #22):")
    for e in entries:
        if e.get("entry_id") == q_m2_e22_id:
            old_sum = e.get("payload", {}).get("summary", "")
            new_sum = "Горан подошёл к Орму и договорился с ним о передаче надёжного оружия (для веса в переговорах с разбойниками)"
            e["payload"]["summary"] = new_sum
            print(f"  e22 OLD: {old_sum}")
            print(f"  e22 NEW: {new_sum}")
            # Также проверить target_hint — должен быть Орм (адресат)
            target_hint = e.get("payload", {}).get("target_hint", "")
            if target_hint:
                print(f"  target_hint (сохранён): {target_hint}")
            fixed += 1

    # Q-M3: править entry #12 (ENTITY_CONFUSION)
    print(f"\n[Q-M3] ENTITY_CONFUSION (entry #12):")
    for e in entries:
        if e.get("entry_id") == q_m3_e12_id:
            old_sum = e.get("payload", {}).get("summary", "")
            # Author fragment 5: гильдия купцов подозревает и закрывает перевозки
            new_sum = "Горан не может найти работу и кредиты из-за подозрений гильдии купцов (которая видит его связь с гильдией воров)"
            e["payload"]["summary"] = new_sum
            print(f"  e12 OLD: {old_sum}")
            print(f"  e12 NEW: {new_sum}")
            fixed += 1

    # Q-M4: удалить entry #1 (SPURIOUS_REFERENCE)
    print(f"\n[Q-M4] SPURIOUS_REFERENCE (entry #1 — удалить):")
    new_entries = []
    for e in entries:
        if e.get("entry_id") == q_m4_e1_id:
            print(f"  УДАЛЁН entry_id={q_m4_e1_id}")
            print(f"  summary: {e.get('payload', {}).get('summary', '?')[:120]}")
            deleted += 1
            continue
        new_entries.append(e)
    draft["entries"] = new_entries

    # Сохранение
    tmp_path = DRAFT_PATH.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)
    tmp_path.replace(DRAFT_PATH)
    print(f"\n[3] Draft сохранён: {DRAFT_PATH}")
    print(f"  Fixed: {fixed}, Deleted: {deleted}")

    # Верификация
    with DRAFT_PATH.open("r", encoding="utf-8-sig") as f:
        verify = json.load(f)
    print(f"\n[4] Верификация: {len(verify['entries'])} entries после правок (было {len(entries)})")

    # Проверка Q-M1
    for e in verify["entries"]:
        if e.get("entry_id") == q_m1_e38_id:
            stmt = e.get("payload", {}).get("statement", "")
            if "Горан говорит" in stmt:
                print(f"  ✅ Q-M1 e38: «Горан говорит о пристраивании»")
            else:
                print(f"  ⚠ Q-M1 e38: {stmt[:80]}")
            break
    for e in verify["entries"]:
        if e.get("entry_id") == q_m1_e39_id:
            s = e.get("payload", {}).get("summary", "")
            if "Горан пристроил" in s:
                print(f"  ✅ Q-M1 e39: «Горан пристроил детей и жену»")
            else:
                print(f"  ⚠ Q-M1 e39: {s}")
            break

    # Проверка Q-M2
    for e in verify["entries"]:
        if e.get("entry_id") == q_m2_e22_id:
            s = e.get("payload", {}).get("summary", "")
            if "Горан подошёл" in s:
                print(f"  ✅ Q-M2 e22: «Горан подошёл к Орму»")
            else:
                print(f"  ⚠ Q-M2 e22: {s}")
            break

    # Проверка Q-M3
    for e in verify["entries"]:
        if e.get("entry_id") == q_m3_e12_id:
            s = e.get("payload", {}).get("summary", "")
            if "гильдии купцов" in s:
                print(f"  ✅ Q-M3 e12: «гильдии купцов»")
            else:
                print(f"  ⚠ Q-M3 e12: {s}")
            break

    # Проверка Q-M4 (entry удалена)
    found_qm4 = False
    for e in verify["entries"]:
        if e.get("entry_id") == q_m4_e1_id:
            found_qm4 = True
            break
    if not found_qm4:
        print(f"  ✅ Q-M4: entry #1 удалена (SPURIOUS_REFERENCE)")
    else:
        print(f"  ⚠ Q-M4: entry #1 всё ещё в draft")

    return 0


if __name__ == "__main__":
    sys.exit(main())