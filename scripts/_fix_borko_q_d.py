"""USL-2 / ТЗ АРХИТЕКТОРУ: правки guard_borko draft Q-D1/Q-D2/Q-D3.

Q-D1 (a): Фрагмент 22 (иллюзия власти) — добавить BELIEF_SEED
Q-D2 (a): SEMANTIC_INVERSION entry #19 — править trait «привык к насилию»
Q-D3 (a): DESIRE_SEED #24 about_hint — добавить «насилие над Люсей»
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

DRAFT_PATH = Path("saves/Open_road/chronicle_drafts/guard_borko.json")

# Q-D2: entry #19 — TRAIT_SEED с инвертированным trait
Q_D2_ENTRY_ID = "5e4a2c26b0f80c4544c9493d2159d52f"  # entry #19
Q_D2_OLD_TRAIT = "привык к насилию"
Q_D2_NEW_TRAIT = "впервые испытал возбуждение от насилия (ранее секс был только добровольным)"
Q_D2_OLD_EVIDENCE = "Обычно девушки и так были не против переспать с ним, так что никогда в жизни ему не представлялся шанс пережить секс, который берут силой"
Q_D2_NEW_EVIDENCE = "никогда в жизни ему не представлялся шанс пережить секс, который берут силой — насилие было для него новым опытом"

# Q-D3: DESIRE_SEED #24 — добавить about_hint
Q_D3_ENTRY_ID = "c5a0511cd1aa062e115a4e62c37ebdcd"
Q_D3_ABOUT_HINT = "насилие над Люсей (наблюдение и мастурбация)"


def _make_entry_id(*parts: str) -> str:
    return hashlib.md5(":".join(parts).encode("utf-8")).hexdigest()


def _resolved_ref(npc_id: str) -> dict:
    return {"ref_kind": "RESOLVED", "npc_id": npc_id, "white_spot_id": None, "name_hint": ""}


def main() -> int:
    if not DRAFT_PATH.exists():
        print(f"Draft не найден: {DRAFT_PATH}", file=sys.stderr)
        return 1

    bak_path = DRAFT_PATH.with_suffix(".json.bak2")
    shutil.copy(DRAFT_PATH, bak_path)
    print(f"[0] Backup: {bak_path}")

    with DRAFT_PATH.open("r", encoding="utf-8-sig") as f:
        draft = json.load(f)

    entries = draft["entries"]
    print(f"[1] Загружен draft: {len(entries)} entries")
    fixed = 0

    # Q-D2: SEMANTIC_INVERSION entry #19
    print(f"\n[Q-D2] Правка SEMANTIC_INVERSION (entry #19):")
    for e in entries:
        if e.get("entry_id") == Q_D2_ENTRY_ID:
            old_trait = e.get("payload", {}).get("trait", "")
            old_evidence = e.get("payload", {}).get("evidence", "")
            print(f"  OLD trait: {old_trait}")
            print(f"  OLD evidence: {old_evidence[:80]}...")
            e["payload"]["trait"] = Q_D2_NEW_TRAIT
            e["payload"]["evidence"] = Q_D2_NEW_EVIDENCE
            print(f"  NEW trait: {Q_D2_NEW_TRAIT}")
            print(f"  NEW evidence: {Q_D2_NEW_EVIDENCE}")
            fixed += 1
            break

    # Q-D3: DESIRE_SEED #24 about_hint
    print(f"\n[Q-D3] Добавление about_hint (entry #24 DESIRE_SEED):")
    for e in entries:
        if e.get("entry_id") == Q_D3_ENTRY_ID:
            old_about = e.get("payload", {}).get("about_hint", "")
            print(f"  OLD about_hint: '{old_about}'")
            e["payload"]["about_hint"] = Q_D3_ABOUT_HINT
            print(f"  NEW about_hint: '{Q_D3_ABOUT_HINT}'")
            fixed += 1
            break

    # Q-D1: добавить BELIEF_SEED про иллюзию власти (фрагмент 22)
    print(f"\n[Q-D1] Добавление BELIEF_SEED (иллюзия власти, фрагмент 22):")
    q_d1_belief = {
        "entry_id": _make_entry_id("guard_borko", "BELIEF_SEED", "illusion_of_power"),
        "kind": "BELIEF_SEED",
        "subject_id": _resolved_ref("guard_borko"),
        "historical_age": None,
        "historical_year": None,
        "object_id": None,
        "payload": {
            "statement": "Борко искренне верит, что имеет власть над Ормом, но ошибается — Орм не боится его и продолжает насиловать Люсю потому, что сам хочет, а Борко для него просто удобный повод не чувствовать себя виноватым",
            "belief_type": "danger",
            "_provenance": {
                "source": "author_text fragment 22",
                "note": "центральный психологический insight — иллюзия власти кукловода",
            },
        },
        "causes": [],
        "provenance": "AUTHOR_AUTHORED",
        "confidence": None,
        "open_questions": [],
        "ordinal": 0,
    }
    entries.append(q_d1_belief)
    print(f"  Добавлено: BELIEF_SEED entry_id={q_d1_belief['entry_id'][:12]}...")
    print(f"  statement: {q_d1_belief['payload']['statement'][:100]}...")
    fixed += 1

    # Сохранение
    tmp_path = DRAFT_PATH.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)
    tmp_path.replace(DRAFT_PATH)
    print(f"\n[2] Draft сохранён: {DRAFT_PATH}")
    print(f"  Всего правок: {fixed}")

    # Верификация
    with DRAFT_PATH.open("r", encoding="utf-8-sig") as f:
        verify = json.load(f)
    print(f"\n[3] Верификация: {len(verify['entries'])} entries после правок")

    # Проверка Q-D2
    for e in verify["entries"]:
        if e.get("entry_id") == Q_D2_ENTRY_ID:
            trait = e.get("payload", {}).get("trait", "")
            if "впервые" in trait:
                print(f"  ✅ Q-D2: trait исправлен на «{trait[:60]}...»")
            else:
                print(f"  ⚠ Q-D2: trait НЕ исправлен: {trait}")
            break

    # Проверка Q-D3
    for e in verify["entries"]:
        if e.get("entry_id") == Q_D3_ENTRY_ID:
            about = e.get("payload", {}).get("about_hint", "")
            if about:
                print(f"  ✅ Q-D3: about_hint добавлен: «{about}»")
            else:
                print(f"  ⚠ Q-D3: about_hint НЕ добавлен")
            break

    # Проверка Q-D1
    found_qd1 = False
    for e in verify["entries"]:
        if e.get("entry_id") == q_d1_belief["entry_id"]:
            found_qd1 = True
            print(f"  ✅ Q-D1: BELIEF_SEED добавлен, kind={e.get('kind')}, provenance={e.get('provenance')}")
            break
    if not found_qd1:
        print(f"  ⚠ Q-D1: BELIEF_SEED НЕ найден")

    # Распределение по kind
    kinds = {}
    for e in verify["entries"]:
        k = e["kind"]
        kinds[k] = kinds.get(k, 0) + 1
    print(f"  Распределение: {kinds}")

    return 0


if __name__ == "__main__":
    sys.exit(main())