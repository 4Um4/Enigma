"""S366 — починка fixture _make_event.
Добавляет параметр causes (default=()) и пробрасывает в ChronicleEntry.
Правит 5 упавших тестов: test_1, test_2, test_3, test_13, test_15.
"""
from pathlib import Path

TEST_PY = Path("backend/tests/micro/test_s366_causal_linker.py")
text = TEST_PY.read_text(encoding="utf-8")

# Старая сигнатура без causes
OLD = '''def _make_event(chronicle_id: str, fragment_ord: int, ordinal: int,
                historical_age: int | None = None,
                summary: str = "test event") -> ChronicleEntry:
    """Сборка synthetic EVENT entry для тестов."""
    return ChronicleEntry(
        entry_id=make_entry_id(chronicle_id, fragment_ord, ordinal),
        kind=EntryKind.EVENT,
        subject_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id=chronicle_id),
        historical_age=historical_age,
        payload={"summary": summary},
        provenance=EntryProvenance.AUTHOR_CONFIRMED,
        confidence=None,
        ordinal=ordinal,
    )'''

# Новая с causes
NEW = '''def _make_event(chronicle_id: str, fragment_ord: int, ordinal: int,
                historical_age: int | None = None,
                summary: str = "test event",
                causes: tuple = ()) -> ChronicleEntry:
    """Сборка synthetic EVENT entry для тестов.
    causes — опциональный tuple CauseRef (для тестов валидации/ACCEPT)."""
    return ChronicleEntry(
        entry_id=make_entry_id(chronicle_id, fragment_ord, ordinal),
        kind=EntryKind.EVENT,
        subject_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id=chronicle_id),
        historical_age=historical_age,
        payload={"summary": summary},
        causes=causes,
        provenance=EntryProvenance.AUTHOR_CONFIRMED,
        confidence=None,
        ordinal=ordinal,
    )'''

assert OLD in text, "Старая сигнатура _make_event не найдена"
text = text.replace(OLD, NEW, 1)

# Также: test_15 имеет синтаксис `e1 = _make_event("c1", 1, 100, historical_age=5, )` — trailing comma не ломается,
# но чтобы быть безопасным, оставим как есть (Python 3.11+ допускает).

TEST_PY.write_text(text, encoding="utf-8")
print(f"OK: fixture patched (new size: {len(text)}b)")
