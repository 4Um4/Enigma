# -*- coding: utf-8 -*-
"""
path: /project/backend/tests/test_action_commitment.py
Назначение: S203.1 (Stage 2A) — unit-контракт Commitment Layer: полная FSM-матрица,
    детерминизм ID, монотонный не-переиспользуемый ordinal, bounded history,
    cause-гигиена, parent-цепочка суперсессии, sweep, JSON-сериализуемость
    (persistance-контракт scene_state: atomic commit сериализует реестр),
    нейтральность rollback-флага.
Зависимости: pytest, app.domain.action_commitment, app.services.action.commitment_registry
Основные сущности: TestCommitmentFSM, TestCommitmentId, TestBuildDict,
    TestRegistryLifecycle, TestSweep, TestFlagNeutrality, TestJsonRoundTrip

    Запуск: cd backend; python -m pytest tests/test_action_commitment.py -v; cd ..

"""

import json

import pytest

from app.domain.action_commitment import (
    CAUSE_UNKNOWN_LEGACY_SOURCE,
    COMMITMENT_HISTORY_CAP_PER_NPC,
    COMMITMENT_STATUSES,
    COMMITMENT_TERMINAL_STATUSES,
    COMMITMENT_TRANSITIONS,
    build_commitment_dict,
    build_commitment_id,
    transition_commitment,
)
from app.services.action import commitment_registry as cr_module
from app.services.action.commitment_registry import CommitmentRegistry


@pytest.fixture
def flag_on():
    """Гарантия: тесты не текут состоянием флага друг в друга."""
    old = cr_module.COMMITMENT_REGISTRY_ENABLED
    cr_module.COMMITMENT_REGISTRY_ENABLED = True
    yield old
    cr_module.COMMITMENT_REGISTRY_ENABLED = old


def _mk(initial_status="PROPOSED", npc_id="npc1", tick=1, ordinal=1):
    """Фабрика записи (§13.4: без ручного конструктора-мечты dict'а)."""
    return build_commitment_dict(
        tick=tick,
        npc_id=npc_id,
        action="MOVE",
        ordinal=ordinal,
        cause="test_cause",
        target_id="bar",
        executor="traversal",
        initial_status=initial_status,
    )


# ── FSM-матрица ─────────────────────────────────────────────────────────────


class TestCommitmentFSM:
    def test_matrix_allowed_and_forbidden(self):
        """Каждый разрешённый переход проходит, каждый неразрешённый — отклонён."""
        all_targets = {s for targets in COMMITMENT_TRANSITIONS.values() for s in targets}
        for frm, allowed in COMMITMENT_TRANSITIONS.items():
            for to in COMMITMENT_STATUSES:
                # переходы в несуществующие состояния исключены самой таблицей
                if to not in all_targets and to not in COMMITMENT_STATUSES:
                    continue
                record = _mk(initial_status=frm)
                ok = transition_commitment(
                    record, to, tick=99, interrupt_reason="R" if to == "INTERRUPTED" else None
                )
                assert ok == (to in allowed), f"{frm}->{to}: got {ok}, allowed={to in allowed}"

    def test_terminals_have_no_exits(self):
        assert COMMITMENT_TERMINAL_STATUSES == {
            "COMPLETED", "FAILED", "INTERRUPTED", "EXPIRED", "CANCELLED"
        }

    def test_interrupted_requires_reason(self):
        """INTERRUPTED без причины прекращения = отказ, запись не мутирована."""
        record = _mk(initial_status="EXECUTING")
        assert transition_commitment(record, "INTERRUPTED") is False
        assert record["status"] == "EXECUTING"
        assert record["interrupt_reason"] is None
        # с причиной — проходит и причина записана
        assert transition_commitment(record, "INTERRUPTED", interrupt_reason="THREAT") is True
        assert record["interrupt_reason"] == "THREAT"

    def test_cancel_from_any_active_phase(self):
        """S203.1: CANCELLED доступен из каждого не-терминального статуса —
        сознательное снятие не зависит от фазы исполнения."""
        for phase in ("PROPOSED", "COMMITTED", "EXECUTING", "BLOCKED"):
            record = _mk(initial_status=phase)
            assert transition_commitment(record, "CANCELLED", tick=5) is True, phase

    def test_rejected_transition_does_not_mutate(self):
        record = _mk(initial_status="COMMITTED")
        assert transition_commitment(record, "COMPLETED") is False  # нет пути COMMITTED->COMPLETED
        assert record["status"] == "COMMITTED"


# ── Детерминизм идентичности ────────────────────────────────────────────────


class TestCommitmentId:
    def test_deterministic(self):
        assert build_commitment_id(100, "n", "MOVE", 1) == build_commitment_id(100, "n", "MOVE", 1)

    def test_unique_across_inputs(self):
        ids = {
            build_commitment_id(t, "n", "MOVE", o)
            for t in range(3)
            for o in range(3)
        }
        assert len(ids) == 9


class TestBuildDict:
    def test_empty_cause_forbidden(self):
        with pytest.raises(ValueError):
            build_commitment_dict(tick=1, npc_id="n", action="MOVE", ordinal=1, cause="")

    def test_unknown_status_forbidden(self):
        with pytest.raises(ValueError):
            build_commitment_dict(tick=1, npc_id="n", action="MOVE", ordinal=1, cause="c", initial_status="MOVING")

    def test_id_matches_formula(self):
        record = _mk(tick=7, npc_id="npcX", ordinal=3)
        assert record["commitment_id"] == build_commitment_id(7, "npcX", "MOVE", 3)


# ── Реестр: lifecycle ───────────────────────────────────────────────────────


class TestRegistryLifecycle:
    def test_commit_creates_committed_and_projection(self, flag_on):
        ss = {}
        cm = CommitmentRegistry.commit(ss, tick=10, npc_id="n1", action="MOVE", cause="schedule:work")
        assert cm["status"] == "COMMITTED"
        assert CommitmentRegistry.has_active_commitment(ss, "n1") is True
        assert CommitmentRegistry.get_active(ss, "n1")["commitment_id"] == cm["commitment_id"]

    def test_empty_cause_becomes_unknown_legacy(self, flag_on):
        """№8: реестр не выдумывает семантику — честный маркер вместо пустоты."""
        ss = {}
        cm = CommitmentRegistry.commit(ss, tick=1, npc_id="n1", action="MOVE", cause="")
        assert cm["cause"] == CAUSE_UNKNOWN_LEGACY_SOURCE

    def test_supersession_parent_chain_and_ordinal(self, flag_on):
        """№3a: C2 каузально произошёл из C1; №4: ordinal монотонен и не переиспользуется."""
        ss = {}
        c1 = CommitmentRegistry.commit(ss, tick=10, npc_id="n1", action="MOVE", cause="schedule:work")
        CommitmentRegistry.mark_executing(ss, "n1", 11)
        c2 = CommitmentRegistry.commit(ss, tick=12, npc_id="n1", action="MOVE", cause="need:hunger")
        assert c2["parent_commitment_id"] == c1["commitment_id"]
        assert ss["commitment_history"]["n1"][-1]["status"] == "INTERRUPTED"
        assert ss["commitment_ordinals"]["n1"] == 2
        assert c1["commitment_id"] != c2["commitment_id"]

    def test_full_lifecycle_to_history(self, flag_on):
        ss = {}
        CommitmentRegistry.commit(ss, tick=1, npc_id="n1", action="MOVE", cause="c")
        assert CommitmentRegistry.mark_executing(ss, "n1", 2) is True
        assert CommitmentRegistry.complete(ss, "n1", 5) is True
        assert CommitmentRegistry.has_active_commitment(ss, "n1") is False
        assert ss["commitment_history"]["n1"][-1]["status"] == "COMPLETED"
        # повторный complete по пустому активу — отказ, не исключение
        assert CommitmentRegistry.complete(ss, "n1", 6) is False

    def test_terminal_variants(self, flag_on):
        for terminal in ("FAILED", "EXPIRED", "CANCELLED"):
            ss = {}
            CommitmentRegistry.commit(ss, tick=1, npc_id="n1", action="MOVE", cause="c")
            CommitmentRegistry.mark_executing(ss, "n1", 2)
            ok = {"FAILED": CommitmentRegistry.fail,
                  "EXPIRED": CommitmentRegistry.expire,
                  "CANCELLED": CommitmentRegistry.cancel}[terminal](ss, "n1", 3)
            assert ok is True
            assert ss["commitment_history"]["n1"][-1]["status"] == terminal

    def test_history_cap_bounded(self, flag_on):
        """№1: retained history ограничена cap — реестр не растёт бесконечно."""
        ss = {}
        for i in range(COMMITMENT_HISTORY_CAP_PER_NPC + 5):
            CommitmentRegistry.commit(ss, tick=i, npc_id="n1", action="MOVE", cause="c")
            CommitmentRegistry.complete(ss, "n1", i)
        assert len(ss["commitment_history"]["n1"]) == COMMITMENT_HISTORY_CAP_PER_NPC

    def test_mirror_materialized_marks_executing(self, flag_on):
        """Зеркало SSM: материализация = born-COMMITTED -> EXECUTING (Н-50 симметрия)."""
        ss = {}
        CommitmentRegistry.mirror_traversal_materialized(
            ss, tick=3, npc_id="n1", cause="life_engine_schedule", target_node="bar"
        )
        assert ss["active_commitments"]["n1"]["status"] == "EXECUTING"


# ── Sweep: консистентность реестра ──────────────────────────────────────────


class TestSweep:
    def test_vanished_traversal_interrupted(self, flag_on):
        ss = {}
        CommitmentRegistry.mirror_traversal_materialized(
            ss, tick=3, npc_id="n1", cause="c", target_node="bar"
        )
        # traversal отсутствует в active_traversals (обход Н-46-класса)
        assert CommitmentRegistry.sweep(ss, tick=4) == 1
        assert ss["commitment_history"]["n1"][-1]["interrupt_reason"] == "TRAVERSAL_VANISHED"

    def test_alive_traversal_untouched(self, flag_on):
        ss = {"active_traversals": {"n1": {"status": "MOVING"}}}
        CommitmentRegistry.mirror_traversal_materialized(
            ss, tick=3, npc_id="n1", cause="c", target_node="bar"
        )
        assert CommitmentRegistry.sweep(ss, tick=4) == 0
        assert CommitmentRegistry.has_active_commitment(ss, "n1") is True

    def test_non_traversal_executor_untouched(self, flag_on):
        """Контракт: sweep чистит только traversal-executor (windup/task — S203.3/4)."""
        ss = {}
        CommitmentRegistry.commit(ss, tick=1, npc_id="n1", action="TALK", cause="c", executor="task")
        assert CommitmentRegistry.sweep(ss, tick=2) == 0


# ── Нейтральность флага ─────────────────────────────────────────────────────


class TestFlagNeutrality:
    def test_disabled_flag_full_noop(self):
        """Rollback-контракт S203.1: флаг OFF = реестр не пишет, поведение байтово прежнее."""
        cr_module.COMMITMENT_REGISTRY_ENABLED = False
        try:
            ss = {}
            CommitmentRegistry.mirror_traversal_materialized(ss, tick=1, npc_id="n1", cause="c", target_node="b")
            CommitmentRegistry.mirror_traversal_completed(ss, "n1", 2)
            CommitmentRegistry.mirror_traversal_interrupted(ss, "n1", 2, "R")
            assert CommitmentRegistry.sweep(ss, tick=3) == 0
            # Реестр не оставил НИ ОДНОГО ключа в scene_state
            assert "active_commitments" not in ss
            assert "commitment_history" not in ss
            assert "commitment_ordinals" not in ss
        finally:
            cr_module.COMMITMENT_REGISTRY_ENABLED = True


# ── Persistance-контракт: JSON round-trip ───────────────────────────────────


class TestJsonRoundTrip:
    def test_scene_state_registry_survives_serialization(self, flag_on):
        """WARA (§12.2): atomic commit сериализует scene_state в JSON —
        реестр обязан переживать round-trip без потерь."""
        ss = {}
        CommitmentRegistry.commit(ss, tick=10, npc_id="n1", action="MOVE", cause="schedule:work")
        CommitmentRegistry.commit(ss, tick=12, npc_id="n1", action="MOVE", cause="need:hunger")
        CommitmentRegistry.complete(ss, "n1", 15)
        CommitmentRegistry.commit(ss, tick=20, npc_id="n2", action="MOVE", cause="random:wanders_to_bar")

        restored = json.loads(json.dumps(ss))
        assert restored["active_commitments"]["n2"]["commitment_id"] == ss["active_commitments"]["n2"]["commitment_id"]
        assert len(restored["commitment_history"]["n1"]) == len(ss["commitment_history"]["n1"])
        assert restored["commitment_ordinals"] == ss["commitment_ordinals"]