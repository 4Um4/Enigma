# path: /project/backend/tests/gameplay/test_p2_canon_sync.py
# Назначение: M1/P2 — гейт canon-sync: статическая половина (subprocess
#   чекер) + runtime-половина (harness): holders имеют EventMemory(secret_id);
#   происхождение 16 origin-носителей + 9 seeded (fill-the-gaps); holdout.
# Зависимости: tests.gameplay.harness, scripts/check_canon_sync.py
import copy
import subprocess
import sys
from pathlib import Path

import pytest
from app.services.npc import npc_loader as nl
from app.services.npc.npc_loader import load_l2_state_from_runtime_dict
from tests.gameplay.harness import TavernGameplayHarness

ROOT = Path(__file__).resolve().parents[3]
CHECKER = ROOT / "scripts" / "check_canon_sync.py"

NPCS = (
    "maid_lusya", "guard_borko", "blacksmith_orm",
    "merchant_goran", "tavern_keeper_tornin", "thief_shadow",
)


@pytest.fixture()
def harness():
    _h = TavernGameplayHarness(seed=42)
    _h.new_game()
    _h.advance_ticks(3)  # inspect_npc пуст до первого тика (урок P1)
    yield _h
    _h.dispose()


def test_p2_static_canon_sync():
    """Статика: secret_id у всех is_secret-конфигов; канон-инварианты."""
    r = subprocess.run([sys.executable, str(CHECKER)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, f"check_canon_sync RED:\n{r.stdout}\n{r.stderr}"


def test_p2_runtime_holders_have_memories(harness):
    """Runtime: каждый holder каждого секрета имеет EventMemory(secret_id)."""
    truth = nl._canon_truth_state()
    states = [load_l2_state_from_runtime_dict(
        copy.deepcopy(harness.inspect_npc(n))) for n in NPCS]
    for sec in truth.secrets.values():
        got = sorted(nl.who_knows(sec.secret_id, states))
        assert got == sorted(sec.initial_holders), (
            f"P2: {sec.secret_id}: {got} != {sorted(sec.initial_holders)}"
        )


def test_p2_provenance_origin_vs_seeded(harness):
    """Q1=MAP: 16 фактов несут origin-конфиги (event_type != secret_origin),
    сеялка заполняет ровно 9 пробелов. Дублей нет по построению (дедуп)."""
    origin_carried = 0
    seeded = 0
    for n in NPCS:
        raw = copy.deepcopy(harness.inspect_npc(n))
        st = load_l2_state_from_runtime_dict(raw)
        for m in st.narrative_cache:
            if not m.secret_id:
                continue
            if m.event_type == "secret_origin":
                seeded += 1
            else:
                origin_carried += 1
    assert origin_carried == 16, f"origin-носителей {origin_carried} != 16"
    assert seeded == 9, f"seeded {seeded} != 9"


def test_p2_holdout(harness):
    """Каждая secret_id-память принадлежит canon-holder'у (№1: known_by
    legacy-метадата источником истины НЕ является)."""
    truth = nl._canon_truth_state()
    for n in NPCS:
        raw = copy.deepcopy(harness.inspect_npc(n))
        st = load_l2_state_from_runtime_dict(raw)
        for m in st.narrative_cache:
            if m.secret_id:
                assert n in truth.secrets[m.secret_id].initial_holders, (
                    f"P2 holdout: {n} держит {m.secret_id}"
                )
