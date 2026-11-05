"""USL-2 / ТЗ АРХИТЕКТОРУ: правки thief_shadow draft Q-S1 + Q-S2.

Q-S1: ENTITY_CONFUSION entry #14 — «Красный Гросбух» = книга, не таверна.
  Author fragment 5: «через подвал таверны — «Красный Гросбух» — книгу»
  Author fragment 15: «Красный «Гросбух» сейчас в руках у Тени»
  Фикс: переформулировать summary, не смешивать название книги с таверной.

Q-S2: PROVENANCE_NOTE entry #39 — авторская мета-заметка «Для автора:».
  Author fragment 13: «Для автора: счастье Борко — вуайеризм...»
  Master: «авторское сообщение об отсутствии знания у персонажа
           само по себе не является игровым знанием».
  Фикс: удалить из активного draft.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

DRAFT_PATH = Path("saves/Open_road/chronicle_drafts/thief_shadow.json")


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

    # Q-S1: найти entry с «Гросбух» + «таверны» — переформулировать
    print(f"\n[Q-S1] ENTITY_CONFUSION (entry #14 — книга vs таверна):")
    for e in entries:
        text = json.dumps(e.get("payload", {}), ensure_ascii=False)
        if "Гросбух" in text and "таверн" in text:
            old_sum = e.get("payload", {}).get("summary", "")
            print(f"  OLD: {old_sum}")
            new_sum = "гильдия выносит книгу «Красный Гросбух» (с информацией и казной) через подвал таверны «Серебряный волк»"
            e["payload"]["summary"] = new_sum
            print(f"  NEW: {new_sum}")
            fixed += 1
            break

    # Q-S2: найти entry с «вуайеризм» (author meta note) — удалить
    print(f"\n[Q-S2] PROVENANCE_NOTE (entry #39 — авторская мета «Для автора:»):")
    new_entries = []
    for e in entries:
        text = json.dumps(e.get("payload", {}), ensure_ascii=False)
        if "вуайеризм" in text:
            print(f"  УДАЛЁН entry_id={e.get('entry_id', '?')[:12]}...")
            stmt = e.get("payload", {}).get("statement", "")
            print(f"  statement: {stmt[:120]}...")
            print(f"  Причина: AUTHOR_META_NOTE — excluded from NPC semantic chronicle")
            deleted += 1
            continue
        new_entries.append(e)
    draft["entries"] = new_entries

    # Доп. проверка: другие entries с маркерами «Для автора»/«заметка автору»
    print(f"\n[ДОП] Проверка других author meta notes:")
    meta_markers = ["Для автора", "заметка автору", "для мастера", "для дизайнера", "для разработчика"]
    found_meta = 0
    for e in new_entries:
        text = json.dumps(e.get("payload", {}), ensure_ascii=False)
        for marker in meta_markers:
            if marker.lower() in text.lower():
                found_meta += 1
                print(f"  НАЙДЕН author meta в entry_id={e.get('entry_id', '?')[:12]}...")
                s = e.get("payload", {}).get("summary", "") or e.get("payload", {}).get("statement", "")
                print(f"    content: {s[:100]}...")
                print(f"    marker: {marker}")
                break
    if found_meta == 0:
        print(f"  ✅ Других author meta notes не найдено")

    # Сохранение
    tmp_path = DRAFT_PATH.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)
    tmp_path.replace(DRAFT_PATH)
    print(f"\n[2] Draft сохранён: {DRAFT_PATH}")
    print(f"  Fixed: {fixed}, Deleted: {deleted}")

    # Верификация
    with DRAFT_PATH.open("r", encoding="utf-8-sig") as f:
        verify = json.load(f)
    print(f"\n[3] Верификация: {len(verify['entries'])} entries (было {len(entries)})")

    # Проверка Q-S1
    for e in verify["entries"]:
        text = json.dumps(e.get("payload", {}), ensure_ascii=False)
        if "Гросбух" in text and "Серебряный" in text:
            print(f"  ✅ Q-S1: «книга «Красный Гросбух» через подвал таверны «Серебряный волк»»")
            break

    # Проверка Q-S2
    found_voyeur = False
    for e in verify["entries"]:
        text = json.dumps(e.get("payload", {}), ensure_ascii=False)
        if "вуайеризм" in text:
            found_voyeur = True
            break
    if not found_voyeur:
        print(f"  ✅ Q-S2: AUTHOR_META_NOTE удалена")
    else:
        print(f"  ⚠ Q-S2: AUTHOR_META_NOTE всё ещё в draft")

    return 0


if __name__ == "__main__":
    sys.exit(main())