# path: /project/backend/tests/gameplay/test_p1_secret_identity.py
# Назначение: M1/P1 (ТЗ «Таверна тайн») — формальный гейт «впервые замкнут
#   Truth -> NPC Knowledge»: секрет канона = EventMemory у каждого
#   initial_holder. Критерии ТЗ-P1 + гейт Мастера после M1 (RELOAD:
#   SQLITE -> load -> SAME KNOWLEDGE; A/A-контроль — метод S254).
# Зависимости: tests.gameplay.harness, app.services.npc.npc_loader
# Основные сущности: test_p1_*, NPCS, CANON
import copy

import pytest
from app.services.npc import npc_loader as nl
from app.services.npc.npc_loader import load_l2_state_from_runtime_dict
from tests.gameplay.harness import TavernGameplayHarness

NPCS = (
    "maid_lusya", "guard_borko", "blacksmith_orm",
    "merchant_goran", "tavern_keeper_tornin", "thief_shadow",
)


def _states(h):
    raw = [copy.deepcopy(h.inspect_npc(n)) for n in NPCS]
    return [load_l2_state_from_runtime_dict(r) for r in raw]


@pytest.fixture()
def harness():
    _h = TavernGameplayHarness(seed=42)
    _h.new_game()
    # Прогрев: inspect_npc читает LifeEngine-кэш — он пуст до первого тика
    # (мои %TEMP%-зонды гнали advance_ticks(3) до инспекта; без прогрева
    # inspect_npc -> None -> raw_data.get падает). Гейт Мастера после M1
    # требует живую production-гидратацию — прогрев это обеспечивает.
    _h.advance_ticks(3)
    yield _h
    _h.dispose()


def test_p1_every_holder_knows(harness):
    """ТЗ-P1.1: для каждого из 17 секретов who_knows == initial_holders."""
    truth = nl._canon_truth_state()
    assert truth and len(truth.secrets) == 17
    states = _states(harness)
    for sec in truth.secrets.values():
        got = sorted(nl.who_knows(sec.secret_id, states))
        exp = sorted(sec.initial_holders)
        assert got == exp, (
            f"P1: {sec.secret_id}: who_knows {got} != canon {exp}"
        )


def test_p1_holdout_and_cardinality(harness):
    """ТЗ-P1.1: не-holder не знает; карта 25 holder-памятей."""
    states = _states(harness)
    for st in states:
        for m in st.narrative_cache:
            sid = m.secret_id
            if sid is None:
                continue
            truth = nl._canon_truth_state()
            sec = truth.secrets[sid]
            assert st.npc_id in sec.initial_holders, (
                f"P1: {st.npc_id} держит {sid}, не будучи holder'ом"
            )
    total = sum(
        1 for st in states for m in st.narrative_cache if m.secret_id
    )
    assert total == 25, f"P1: holder-памятей {total} != 25"


def test_p1_aa_control(harness):
    """A/A (метод S254): повторная гидратация тех же диктов — та же карта."""
    raw = [copy.deepcopy(harness.inspect_npc(n)) for n in NPCS]
    s1 = [load_l2_state_from_runtime_dict(copy.deepcopy(r)) for r in raw]
    s2 = [load_l2_state_from_runtime_dict(copy.deepcopy(r)) for r in raw]
    for a, b in zip(s1, s2):
        assert a.npc_id == b.npc_id
        assert {m.secret_id for m in a.narrative_cache} == {
            m.secret_id for m in b.narrative_cache
        }, f"P1 A/A: дрейф карты у {a.npc_id}"


def test_p1_reload_sqlite_same_knowledge(harness):
    """Гейт Мастера после M1: RELOAD — SQLITE -> load -> SAME KNOWLEDGE.
    Канон-памяти проходят полный production round-trip (save_event_
    memories_batch -> load_event_memories -> EventMemory(**row)) без
    потери secret_id; карта знаний идентична до/после."""
    from app.services.memory.sqlite_store import SqliteMemoryStore

    harness.advance_ticks(1)  # прогрев SQLite-writers если подключены
    states = _states(harness)
    before = {
        st.npc_id: sorted(
            m.secret_id for m in st.narrative_cache if m.secret_id
        )
        for st in states
    }
    assert sum(len(v) for v in before.values()) == 25

    import dataclasses
    import os
    import tempfile

    db = os.path.join(tempfile.mkdtemp(prefix="p1_reload_"), "rt.db")
    store = SqliteMemoryStore(db)
    try:
        for st in states:
            # Гейт Мастера — про канон-знание: round-trip канон-памятей
            mems = [dataclasses.asdict(m) for m in st.narrative_cache
                    if m.secret_id]
            store.save_event_memories_batch("Open_road", st.npc_id, mems)
        after = {}
        for st in states:
            rows = store.load_event_memories("Open_road", st.npc_id)
            ids = sorted(
                r["secret_id"] for r in rows if r.get("secret_id")
            )
            after[st.npc_id] = ids
        assert after == before, (
            f"P1 RELOAD: SQLITE round-trip изменил карту знаний:\n"
            f"до={before}\nпосле={after}"
        )
    finally:
        store.close()


def test_p1_old_save_loads(harness):
    """ТЗ-P1: старый сейв (без secret_id) грузится без ошибок (None-дефолт)."""
    raw = copy.deepcopy(harness.inspect_npc("maid_lusya"))
    for _m in raw.get("narrative_cache", []):
        _m.pop("secret_id", None)
    st = load_l2_state_from_runtime_dict(raw)
    assert st.narrative_cache, "P1: старый формат дал пустой кэш"
    # сеялка восполняет канон поверх старого формата
    ids = {m.secret_id for m in st.narrative_cache}
    assert "lusya_basement" in ids, "P1: сеялка не восполнила канон"
