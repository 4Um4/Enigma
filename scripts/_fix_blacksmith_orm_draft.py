"""USL-2 P2 §3: правки blacksmith_orm draft после семантической проверки.

Мандат Мастера (MASTER DECISION 2026-11-05):
  Q1: PORTRET #21 -> EVENT (изнасилование Люси - событие, не черта характера)
  Q2: удалить RELATIONSHIP #26 (Торнин-защитник - перепутанная перспектива)
       + восстановить 2 смысловых компонента фрагмента 11:
         - Торнин бьет Люсю (факт из авторского текста)
         - Орм грызет совесть перед Торниным (субъект вины = Орм)
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

DRAFT_PATH = Path("saves/Open_road/chronicle_drafts/blacksmith_orm.json")

Q1_DELETE_ENTRY_ID = "8beed3786281f9961e2890fdc8f45d16"
Q2_DELETE_ENTRY_ID = "6145c048a81be3e12d74fa6469a3c3f2"


def _make_entry_id(*parts: str) -> str:
    raw = ":".join(parts)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _resolved_ref(npc_id: str) -> dict:
    return {"ref_kind": "RESOLVED", "npc_id": npc_id, "white_spot_id": None, "name_hint": ""}


def _white_spot_ref(white_spot_id: str, name_hint: str) -> dict:
    return {"ref_kind": "WHITE_SPOT", "npc_id": None, "white_spot_id": white_spot_id, "name_hint": name_hint}


def main() -> int:
    if not DRAFT_PATH.exists():
        print(f"  Draft не найден: {DRAFT_PATH}", file=sys.stderr)
        return 1

    with DRAFT_PATH.open("r", encoding="utf-8-sig") as f:
        draft = json.load(f)

    entries_before = len(draft["entries"])
    print(f"[1] Загружен draft: {entries_before} entries")

    ids_to_delete = {Q1_DELETE_ENTRY_ID, Q2_DELETE_ENTRY_ID}
    deleted_kinds = []
    new_entries = []
    for e in draft["entries"]:
        if e.get("entry_id") in ids_to_delete:
            deleted_kinds.append(f"{e.get('kind')} ({e.get('entry_id', '?')[:12]}...)")
            continue
        new_entries.append(e)

    draft["entries"] = new_entries
    print(f"[2] Удалено {len(deleted_kinds)} entries: {deleted_kinds}")

    npc_ref = _resolved_ref("blacksmith_orm")

    q1_event = {
        "entry_id": _make_entry_id("blacksmith_orm", "EVENT", "assault_on_lusya"),
        "kind": "EVENT",
        "subject_id": npc_ref,
        "historical_age": None,
        "historical_year": None,
        "object_id": _white_spot_ref("assault_on_lusya_target", "Люся"),
        "payload": {
            "summary": "изнасиловал Люсю (девочку из таверны)",
            "day": None,
            "is_recurring": False,
            "_provenance": {"source": "author_text fragment 9", "note": "мотив неясен"},
        },
        "causes": [],
        "provenance": "AUTHOR_AUTHORED",
        "confidence": None,
        "open_questions": [],
        "ordinal": 0,
    }

    q2_rel_a = {
        "entry_id": _make_entry_id("blacksmith_orm", "RELATIONSHIP", "tornin_beats_lusya"),
        "kind": "RELATIONSHIP",
        "subject_id": npc_ref,
        "historical_age": None,
        "historical_year": None,
        "object_id": _white_spot_ref("tornin_as_subject", "Торнин"),
        "payload": {
            "summary": "Торнин бьет Люсю (наблюдение Орма из фрагмента 11)",
            "nature": "наблюдаемое насилие",
            "valence": "negative",
            "target_hint": "Торнин",
            "_provenance": {"source": "author_text fragment 11", "note": "Торнин бьет, но заботится"},
        },
        "causes": [],
        "provenance": "AUTHOR_AUTHORED",
        "confidence": None,
        "open_questions": [],
        "ordinal": 0,
    }

    q2_rel_b = {
        "entry_id": _make_entry_id("blacksmith_orm", "RELATIONSHIP", "orm_guilt_before_tornin"),
        "kind": "RELATIONSHIP",
        "subject_id": npc_ref,
        "historical_age": None,
        "historical_year": None,
        "object_id": _white_spot_ref("tornin_as_guilt_target", "Торнин"),
        "payload": {
            "summary": "Орм грызет совесть перед Торниным - потому что насилует девочку, которую Торнин по-своему опекает",
            "nature": "вина",
            "valence": "negative",
            "target_hint": "Торнин",
            "_provenance": {"source": "author_text fragment 11", "note": "парадокс вины"},
        },
        "causes": [],
        "provenance": "AUTHOR_AUTHORED",
        "confidence": None,
        "open_questions": [],
        "ordinal": 0,
    }

    draft["entries"].extend([q1_event, q2_rel_a, q2_rel_b])
    entries_final = len(draft["entries"])
    print(f"[3] Добавлено 3 entries. Стало: {entries_final}")

    tmp_path = DRAFT_PATH.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)
    tmp_path.replace(DRAFT_PATH)
    print(f"[4] Draft сохранен: {DRAFT_PATH}")

    with DRAFT_PATH.open("r", encoding="utf-8-sig") as f:
        verify = json.load(f)
    print(f"[5] Верификация: {len(verify['entries'])} entries")

    kinds = {}
    for e in verify["entries"]:
        k = e["kind"]
        kinds[k] = kinds.get(k, 0) + 1
    print(f"    Распределение по kind: {kinds}")

    new_ids = {q1_event["entry_id"], q2_rel_a["entry_id"], q2_rel_b["entry_id"]}
    found_new = [e for e in verify["entries"] if e["entry_id"] in new_ids]
    print(f"    Новых entries найдено: {len(found_new)}/3")
    for e in found_new:
        print(f"      {e['kind']}: {e['payload'].get('summary', '?')[:80]}")

    deleted_found = [e for e in verify["entries"] if e["entry_id"] in ids_to_delete]
    if deleted_found:
        print(f"    УДАЛЕННЫЕ entries всё ещё в draft: {len(deleted_found)}")
        return 2
    print(f"    Удаленные entries отсутствуют - подтверждено")

    print(f"\n=== ПРАВКА blacksmith_orm draft ЗАВЕРШЕНА ===")
    print(f"  Было: {entries_before} -> Удалено: 2 -> Добавлено: 3 -> Стало: {entries_final}")
    return 0


if __name__ == "__main__":
    sys.exit(main())