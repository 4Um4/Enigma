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
from app.services.action.commitment_arbiter import CommitmentArbiter
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
                    record, to, tick=99,
                    interrupt_reason="R" if to == "INTERRUPTED" else None,
                    # S203.4 (D-6): FAILED без причины запрещён — симметрия
                    # параметризации INTERRUPTED в этом же вызове.
                    fail_reason="TASK_ERROR" if to == "FAILED" else None,
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
        # S203.4 (D-6): FAILED теперь требует fail_reason (симметрия
        # INTERRUPTED) — терминал-цикл параметризует причину по статусу.
        from app.domain.action_commitment import FAIL_TASK_ERROR

        _fail_reasons = {"FAILED": FAIL_TASK_ERROR}
        for terminal in ("FAILED", "EXPIRED", "CANCELLED"):
            ss = {}
            CommitmentRegistry.commit(ss, tick=1, npc_id="n1", action="MOVE", cause="c")
            CommitmentRegistry.mark_executing(ss, "n1", 2)
            _kwargs = (
                {"fail_reason": _fail_reasons[terminal]} if terminal == "FAILED" else {}
            )
            ok = {"FAILED": CommitmentRegistry.fail,
                  "EXPIRED": CommitmentRegistry.expire,
                  "CANCELLED": CommitmentRegistry.cancel}[terminal](ss, "n1", 3, **_kwargs)
            assert ok is True
            assert ss["commitment_history"]["n1"][-1]["status"] == terminal
            if terminal == "FAILED":
                assert (
                    ss["commitment_history"]["n1"][-1]["fail_reason"]
                    == FAIL_TASK_ERROR
                )

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

    def test_non_traversal_executor_within_grace(self, flag_on):
        """S203.4 (Э5-e): sweep не трогает task/windup/sleep в пределах grace
        (TASK_GRACE_TICKS=25) — даёт время на outbox-дренаж."""
        ss = {}
        CommitmentRegistry.commit(ss, tick=1, npc_id="n1", action="TALK", cause="c", executor="task")
        assert CommitmentRegistry.sweep(ss, tick=2) == 0  # 2-1=1 < 25

    def test_non_traversal_executor_after_grace_swept(self, flag_on):
        """S203.4 (Э5-e): после grace — TASK_VANISHED safety-net (stale=0 гарантия)."""
        from app.domain.action_commitment import INTERRUPT_TASK_VANISHED

        ss = {}
        CommitmentRegistry.commit(ss, tick=1, npc_id="n1", action="TALK", cause="c", executor="task")
        assert CommitmentRegistry.sweep(ss, tick=30) == 1  # 30-1=29 > 25
        assert (
            ss["commitment_history"]["n1"][-1]["interrupt_reason"]
            == INTERRUPT_TASK_VANISHED
        )

    def test_blocked_timeout_to_failed(self, flag_on):
        """S203.4 (Ц5): BLOCKED + blocked_since_tick > 10 → FAILED(BLOCKED_TIMEOUT).
        Dead-but-ready: продюсера BLOCKED нет — создаём вручную для контракта."""
        from app.domain.action_commitment import FAIL_BLOCKED_TIMEOUT, transition_commitment

        ss = {}
        CommitmentRegistry.commit(ss, tick=1, npc_id="n1", action="EAT", cause="c", executor="task")
        CommitmentRegistry.mark_executing(ss, "n1", 2)
        _cm = ss["active_commitments"]["n1"]
        assert transition_commitment(_cm, "BLOCKED", tick=5)  # EXECUTING→BLOCKED
        assert _cm["blocked_since_tick"] == 5
        assert CommitmentRegistry.sweep(ss, tick=10) == 0  # 10-5=5 < 10 (в пределах)
        assert CommitmentRegistry.sweep(ss, tick=20) == 1  # 20-5=15 > 10
        assert ss["commitment_history"]["n1"][-1]["status"] == "FAILED"
        assert ss["commitment_history"]["n1"][-1]["fail_reason"] == FAIL_BLOCKED_TIMEOUT


# ── Нейтральность флага ─────────────────────────────────────────────────────


class TestBehavioralOwnerProjection:
    """S203.2: миграция has_active_commitment (Мастер: сейчас, проекция+fallback)."""

    def test_registry_entry_active_states(self):
        """Каждый ACTIVE-статус занимает владельца; терминалы — нет."""
        from app.domain.action_commitment import (
            ACTIVE_COMMITMENT_STATUSES,
            COMMITMENT_TERMINAL_STATUSES,
        )

        for status in ACTIVE_COMMITMENT_STATUSES:
            ss = {"active_commitments": {"n1": {"status": status}}}
            assert CommitmentRegistry.has_behavioral_owner(ss, "n1") is True, status
        for status in COMMITMENT_TERMINAL_STATUSES:
            ss = {"active_commitments": {"n1": {"status": status}}}  # гипотетически
            assert CommitmentRegistry.has_behavioral_owner(ss, "n1") is False, status

    def test_fallback_traversal_moving(self):
        """Нет записи в реестре → legacy-формула (Н-35): NEW == OLD."""
        ss = {"active_traversals": {"n1": {"status": "MOVING"}}}
        assert CommitmentRegistry.has_behavioral_owner(ss, "n1") is True

    def test_fallback_traversal_not_moving(self):
        ss = {"active_traversals": {"n1": {"status": "PENDING"}}}
        assert CommitmentRegistry.has_behavioral_owner(ss, "n1") is False

    def test_noop_contract_flag_off(self):
        """No-op контракт: пустой реестр (FLAG=OFF) + MOVING traversal →
        fallback=True — поведение идентично старой формуле."""
        ss = {"active_traversals": {"n1": {"status": "MOVING"}}}
        assert CommitmentRegistry.has_behavioral_owner(ss, "n1") is True

    def test_commitment_wins_over_missing_traversal(self):
        """Запись реестра приоритетна: COMMITTED без traversal (окно будущего
        S203.3/4) занимает владельца — commitment race Мастера исключён."""
        ss = {
            "active_commitments": {"n1": {"status": "COMMITTED"}},
            "active_traversals": {},
        }
        assert CommitmentRegistry.has_behavioral_owner(ss, "n1") is True


# ── S203.4: Priority policy + reason-контракты (ADR-O-365) ──────────────────


class TestS2034PriorityPolicy:
    """Шкала v1 + pure-функция приоритета (D-5: результат policy, не онтология)."""

    def test_scale_ordering_v1(self):
        from app.domain.action_priority import (
            PRIORITY_EXPLORATION,
            PRIORITY_ROUTINE,
            PRIORITY_SLEEP,
            PRIORITY_SOCIAL,
            PRIORITY_SURVIVAL,
            PRIORITY_WINDOWED,
        )

        assert PRIORITY_EXPLORATION < PRIORITY_ROUTINE < PRIORITY_SOCIAL
        assert PRIORITY_SOCIAL < PRIORITY_SLEEP == PRIORITY_SURVIVAL
        assert PRIORITY_SURVIVAL < PRIORITY_WINDOWED

    def test_resolve_windowed_actions(self):
        from app.domain.action_priority import (
            PRIORITY_WINDOWED,
            resolve_candidate_priority,
        )

        assert resolve_candidate_priority(intent_type="attack") == PRIORITY_WINDOWED
        assert resolve_candidate_priority(intent_type="steal") == PRIORITY_WINDOWED

    def test_resolve_by_intent_domain(self):
        from app.domain.action_priority import (
            PRIORITY_EXPLORATION,
            PRIORITY_ROUTINE,
            PRIORITY_SOCIAL,
            PRIORITY_SURVIVAL,
            resolve_candidate_priority,
        )

        assert resolve_candidate_priority(intent_domain="SURVIVAL") == PRIORITY_SURVIVAL
        assert resolve_candidate_priority(intent_domain="social") == PRIORITY_SOCIAL
        assert resolve_candidate_priority(intent_domain="Routine") == PRIORITY_ROUTINE
        assert resolve_candidate_priority(intent_domain="EXPLORATION") == PRIORITY_EXPLORATION

    def test_resolve_unknown_defaults_to_routine(self):
        from app.domain.action_priority import (
            PRIORITY_ROUTINE,
            resolve_candidate_priority,
        )

        # Консервативный базовый уровень: неизвестный кандидат не получает
        # права прерывать (2 < любого инкумбента + порог 3).
        assert resolve_candidate_priority() == PRIORITY_ROUTINE
        assert resolve_candidate_priority(intent_domain="UNHEARD_OF") == PRIORITY_ROUTINE

    def test_resolve_deterministic(self):
        from app.domain.action_priority import resolve_candidate_priority

        first = resolve_candidate_priority(intent_type="attack", intent_domain="SOCIAL")
        for _ in range(3):
            assert resolve_candidate_priority(
                intent_type="attack", intent_domain="SOCIAL"
            ) == first


class TestS2034CommitmentContract:
    """Расширение фабрики (priority/версия/executor_ref) и reason-контракты."""

    def test_factory_default_fields_are_legacy_neutral(self):
        from app.domain.action_commitment import build_commitment_dict

        cm = build_commitment_dict(
            tick=1, npc_id="n1", action="MOVE", ordinal=1, cause="schedule:patrol"
        )
        assert cm["priority"] == 0
        assert cm["priority_policy_version"] is None
        assert cm["executor_ref"] is None
        assert cm["blocked_since_tick"] is None
        assert cm["fail_reason"] is None

    def test_factory_priority_passthrough(self):
        from app.domain.action_commitment import build_commitment_dict
        from app.domain.action_priority import (
            PRIORITY_POLICY_VERSION,
            PRIORITY_SURVIVAL,
        )

        cm = build_commitment_dict(
            tick=1,
            npc_id="n1",
            action="MOVE",
            ordinal=2,
            cause="need:hunger",
            priority=PRIORITY_SURVIVAL,
            priority_policy_version=PRIORITY_POLICY_VERSION,
            executor_ref="task-1-n1-0-dlg",
        )
        assert cm["priority"] == PRIORITY_SURVIVAL
        assert cm["priority_policy_version"] == PRIORITY_POLICY_VERSION
        assert cm["executor_ref"] == "task-1-n1-0-dlg"

    def test_commitment_id_independent_of_priority(self):
        """D-5: приоритет НЕ входит в commitment_id — смена policy-шкалы не
        меняет ретроактивно идентичности (INV-REPLAY-DETERMINISM)."""
        from app.domain.action_commitment import build_commitment_dict

        a = build_commitment_dict(
            tick=1, npc_id="n1", action="MOVE", ordinal=3, cause="c", priority=1
        )
        b = build_commitment_dict(
            tick=1, npc_id="n1", action="MOVE", ordinal=3, cause="c", priority=7
        )
        assert a["commitment_id"] == b["commitment_id"]

    def test_fail_reason_constants_fixed(self):
        """D-6: fail_reason — отдельный контракт; константы реестра (№16)."""
        from app.domain.action_commitment import (
            FAIL_BLOCKED_TIMEOUT,
            FAIL_TASK_CRASH,
            FAIL_TASK_ERROR,
        )

        assert FAIL_BLOCKED_TIMEOUT == "BLOCKED_TIMEOUT"
        assert FAIL_TASK_ERROR == "TASK_ERROR"
        assert FAIL_TASK_CRASH == "TASK_CRASH"

    def test_interrupted_accepts_priority_supersede(self):
        from app.domain.action_commitment import (
            INTERRUPT_PRIORITY_SUPERSEDE,
            build_commitment_dict,
            transition_commitment,
        )

        cm = build_commitment_dict(
            tick=1,
            npc_id="n1",
            action="MOVE",
            ordinal=1,
            cause="schedule:patrol",
            initial_status="COMMITTED",
        )
        ok = transition_commitment(
            cm, "INTERRUPTED", tick=2, interrupt_reason=INTERRUPT_PRIORITY_SUPERSEDE
        )
        assert ok is True
        assert cm["interrupt_reason"] == INTERRUPT_PRIORITY_SUPERSEDE

    def test_interrupt_traversal_atomic_with_priority_supersede(self, flag_on):
        """PRIORITY_SUPERSEDE — легальная причина атомарного interrupt обоих
        рельсов (расширение реестра причин ADR-O-365; закон №16)."""
        from app.domain.traversal_schema import interrupt_traversal

        ss = {"active_traversals": {"n1": {"status": "MOVING"}}}
        CommitmentRegistry.mirror_traversal_materialized(
            ss, tick=5, npc_id="n1", cause="schedule:patrol", target_node="gate"
        )
        assert interrupt_traversal(ss, "n1", "PRIORITY_SUPERSEDE", tick=6) is True
        # Закон №14 — атомарность: ОБА рельса терминальны.
        assert ss["active_traversals"]["n1"]["status"] == "CANCELLED"
        assert ss["commitment_history"]["n1"][-1]["status"] == "INTERRUPTED"
        assert (
            ss["commitment_history"]["n1"][-1]["interrupt_reason"]
            == "PRIORITY_SUPERSEDE"
        )


class TestS2034FailReasonContract:
    """D-6: FAILED обязан нести причину; Ц5: часы BLOCKED-фазы."""

    def test_failed_without_fail_reason_rejected(self):
        from app.domain.action_commitment import build_commitment_dict, transition_commitment

        cm = build_commitment_dict(
            tick=1, npc_id="n1", action="EAT", ordinal=1,
            cause="need:hunger", initial_status="EXECUTING",
        )
        assert transition_commitment(cm, "FAILED", tick=2) is False
        assert cm["status"] == "EXECUTING"  # ничего не мутировано

    def test_failed_with_reason_sets_field(self):
        from app.domain.action_commitment import (
            FAIL_TASK_ERROR,
            build_commitment_dict,
            transition_commitment,
        )

        cm = build_commitment_dict(
            tick=1, npc_id="n1", action="EAT", ordinal=1,
            cause="need:hunger", initial_status="EXECUTING",
        )
        assert transition_commitment(cm, "FAILED", tick=2, fail_reason=FAIL_TASK_ERROR)
        assert cm["fail_reason"] == FAIL_TASK_ERROR

    def test_registry_fail_signature_requires_reason(self, flag_on):
        import pytest as _pytest

        ss = {}
        CommitmentRegistry.commit(ss, tick=1, npc_id="n1", action="EAT", cause="c")
        with _pytest.raises(TypeError):
            CommitmentRegistry.fail(ss, "n1", 2)  # type: ignore[call-arg]

    def test_registry_fail_persists_reason_in_history(self, flag_on):
        from app.domain.action_commitment import FAIL_TASK_CRASH

        ss = {}
        CommitmentRegistry.commit(ss, tick=1, npc_id="n1", action="EAT", cause="c")
        CommitmentRegistry.mark_executing(ss, "n1", 1)
        assert CommitmentRegistry.fail(ss, "n1", 2, FAIL_TASK_CRASH)
        assert ss["commitment_history"]["n1"][-1]["fail_reason"] == FAIL_TASK_CRASH

    def test_blocked_clock_maintenance(self):
        from app.domain.action_commitment import (
            FAIL_BLOCKED_TIMEOUT,
            build_commitment_dict,
            transition_commitment,
        )

        cm = build_commitment_dict(
            tick=1, npc_id="n1", action="EAT", ordinal=1,
            cause="need:hunger", initial_status="COMMITTED",
        )
        assert transition_commitment(cm, "BLOCKED", tick=5)
        assert cm["blocked_since_tick"] == 5
        assert transition_commitment(cm, "EXECUTING", tick=7)
        assert cm["blocked_since_tick"] is None  # выход из BLOCKED — сброс
        assert transition_commitment(cm, "BLOCKED", tick=8)
        assert transition_commitment(
            cm, "FAILED", tick=9, fail_reason=FAIL_BLOCKED_TIMEOUT
        )
        assert cm["fail_reason"] == FAIL_BLOCKED_TIMEOUT

    def test_blocked_entry_without_tick_leaves_clock_unwound(self):
        from app.domain.action_commitment import build_commitment_dict, transition_commitment

        cm = build_commitment_dict(
            tick=1, npc_id="n1", action="EAT", ordinal=1,
            cause="need:hunger", initial_status="COMMITTED",
        )
        assert transition_commitment(cm, "BLOCKED")  # tick=None
        assert cm["blocked_since_tick"] is None  # часы не заведены — Э7-sweep скипает

    def test_preview_parity_failed_contract(self):
        from app.domain.action_commitment import build_commitment_dict
        from app.domain.traversal_schema import transition_commitment_preview

        cm = build_commitment_dict(
            tick=1, npc_id="n1", action="EAT", ordinal=1,
            cause="need:hunger", initial_status="EXECUTING",
        )
        assert transition_commitment_preview(cm, "FAILED") is False
        assert transition_commitment_preview(cm, "FAILED", fail_reason="TASK_ERROR")


class TestS2034ArbiterInterrupt:
    """Э3: приоритетная политика прерываний (D-4/D-5/D-6; арбитр read-only)."""

    def _policy(self, on: bool):
        import app.services.action.commitment_arbiter as arb

        saved = (arb.ARBITER_ENFORCEMENT, arb.S203_4_ARBITER_INTERRUPT)
        arb.ARBITER_ENFORCEMENT = on
        arb.S203_4_ARBITER_INTERRUPT = on
        return arb, saved

    def test_policy_off_keeps_s2032_behavior(self, flag_on):
        arb, saved = self._policy(False)
        try:
            from app.services.action.commitment_arbiter import (
                REASON_INCUMBENT,
                VERDICT_REJECT,
                CommitmentArbiter,
            )

            ss = {}
            CommitmentRegistry.commit(ss, tick=1, npc_id="n1", action="MOVE", cause="c", target_id="gate")
            r = CommitmentArbiter.arbitrate(ss, "n1", "bar", "src", 2, candidate_priority=99)
            assert r.verdict == VERDICT_REJECT and r.reason == REASON_INCUMBENT
        finally:
            arb.ARBITER_ENFORCEMENT, arb.S203_4_ARBITER_INTERRUPT = saved

    def test_interrupt_on_threshold(self, flag_on):
        arb, saved = self._policy(True)
        try:
            from app.services.action.commitment_arbiter import (
                REASON_PRIORITY_SUPERSEDE,
                VERDICT_INTERRUPT,
                CommitmentArbiter,
            )

            ss = {}
            CommitmentRegistry.commit(ss, tick=1, npc_id="n1", action="MOVE", cause="c", target_id="gate")
            r = CommitmentArbiter.arbitrate(ss, "n1", "bar", "src", 2, candidate_priority=7)
            assert r.verdict == VERDICT_INTERRUPT
            assert r.reason == REASON_PRIORITY_SUPERSEDE
            assert r.incumbent_id is not None
        finally:
            arb.ARBITER_ENFORCEMENT, arb.S203_4_ARBITER_INTERRUPT = saved

    def test_no_interrupt_below_threshold(self, flag_on):
        arb, saved = self._policy(True)
        try:
            from app.services.action.commitment_arbiter import (
                REASON_INCUMBENT,
                VERDICT_REJECT,
                CommitmentArbiter,
            )

            ss = {}
            CommitmentRegistry.commit(ss, tick=1, npc_id="n1", action="MOVE", cause="c", target_id="gate")
            # 3 > 0 + 3 — ложно: SOCIAL не прерывает базового инкумбента.
            r = CommitmentArbiter.arbitrate(ss, "n1", "bar", "src", 2, candidate_priority=3)
            assert r.verdict == VERDICT_REJECT and r.reason == REASON_INCUMBENT
        finally:
            arb.ARBITER_ENFORCEMENT, arb.S203_4_ARBITER_INTERRUPT = saved

    def test_incumbent_protected_executors(self, flag_on):
        arb, saved = self._policy(True)
        try:
            from app.services.action.commitment_arbiter import (
                REASON_INCUMBENT_PROTECTED,
                VERDICT_REJECT,
                CommitmentArbiter,
            )

            for executor in ("task", "windup", "sleep"):
                ss = {}
                CommitmentRegistry.commit(
                    ss, tick=1, npc_id="n1", action="TALK", cause="c", executor=executor
                )
                r = CommitmentArbiter.arbitrate(ss, "n1", "bar", "src", 2, candidate_priority=99)
                assert r.verdict == VERDICT_REJECT, executor
                assert r.reason == REASON_INCUMBENT_PROTECTED, executor
        finally:
            arb.ARBITER_ENFORCEMENT, arb.S203_4_ARBITER_INTERRUPT = saved

    def test_executing_policy_protection(self, flag_on):
        """Вердикт B: EXECUTING-защита СОХРАНЯЕТСЯ для не-traversal
        исполнителей (task/windup/sleep во всех статусах)."""
        arb, saved = self._policy(True)
        try:
            from app.services.action.commitment_arbiter import (
                REASON_INCUMBENT_PROTECTED,
                VERDICT_REJECT,
                CommitmentArbiter,
            )

            ss = {}
            CommitmentRegistry.commit(
                ss, tick=1, npc_id="n1", action="TALK", cause="c", executor="task"
            )
            CommitmentRegistry.mark_executing(ss, "n1", 2)
            r = CommitmentArbiter.arbitrate(ss, "n1", "bar", "src", 3, candidate_priority=99)
            assert r.verdict == VERDICT_REJECT
            assert r.reason == REASON_INCUMBENT_PROTECTED  # POLICY, не онтология
        finally:
            arb.ARBITER_ENFORCEMENT, arb.S203_4_ARBITER_INTERRUPT = saved

    def test_duplicate_never_interrupts(self, flag_on):
        arb, saved = self._policy(True)
        try:
            from app.services.action.commitment_arbiter import (
                REASON_DUPLICATE,
                VERDICT_REJECT,
                CommitmentArbiter,
            )

            ss = {}
            CommitmentRegistry.commit(ss, tick=1, npc_id="n1", action="MOVE", cause="c", target_id="gate")
            r = CommitmentArbiter.arbitrate(ss, "n1", "gate", "src", 2, candidate_priority=99)
            assert r.verdict == VERDICT_REJECT and r.reason == REASON_DUPLICATE
        finally:
            arb.ARBITER_ENFORCEMENT, arb.S203_4_ARBITER_INTERRUPT = saved

    def test_enforce_for_intent_executes_interrupt_atomically(self, flag_on):
        from types import SimpleNamespace

        from app.domain.movement import IntentDomain

        arb, saved = self._policy(True)
        try:
            from app.services.action.commitment_arbiter import CommitmentArbiter

            # Вердикт B: production-реалистичный инкумбент — born-EXECUTING
            # traversal (Н-50, mirror). SURVIVAL(6) > 0 + 3 → INTERRUPT.
            ss = {"active_traversals": {"n1": {"status": "MOVING"}}}
            CommitmentRegistry.mirror_traversal_materialized(
                ss, tick=5, npc_id="n1", cause="schedule:patrol", target_node="gate"
            )
            _intent = SimpleNamespace(
                actor_id="n1", target_node_id="bar", reason="need:flee",
                domain=IntentDomain.SURVIVAL, intent_type="",
            )
            assert CommitmentArbiter.enforce_for_intent(ss, _intent, 6) is True
            # Закон №14: ОБА рельса терминальны одним вызовом.
            assert ss["active_traversals"]["n1"]["status"] == "CANCELLED"
            assert ss["commitment_history"]["n1"][-1]["status"] == "INTERRUPTED"
            assert ss["commitment_history"]["n1"][-1]["interrupt_reason"] == "PRIORITY_SUPERSEDE"
            # владелец освобождён — следующий кандидат PASS
            r2 = CommitmentArbiter.arbitrate(ss, "n1", "bar", "src", 7)
            assert r2.verdict == "PASS"
        finally:
            arb.ARBITER_ENFORCEMENT, arb.S203_4_ARBITER_INTERRUPT = saved

    def test_enforce_for_intent_not_found_fallback(self, flag_on):
        from types import SimpleNamespace

        from app.domain.movement import IntentDomain

        arb, saved = self._policy(True)
        try:
            from app.services.action.commitment_arbiter import CommitmentArbiter

            ss = {}
            CommitmentRegistry.commit(ss, tick=5, npc_id="n1", action="MOVE", cause="c", target_id="gate")
            _intent = SimpleNamespace(
                actor_id="n1", target_node_id="bar", reason="need:flee",
                domain=IntentDomain.SURVIVAL, intent_type="",
            )
            # traversal-записи нет → interrupt_traversal NOT_FOUND → False;
            # инкумбент не тронут (частичный interrupt запрещён, №14).
            assert CommitmentArbiter.enforce_for_intent(ss, _intent, 6) is False
            assert ss["active_commitments"]["n1"]["status"] == "COMMITTED"
        finally:
            arb.ARBITER_ENFORCEMENT, arb.S203_4_ARBITER_INTERRUPT = saved

    def test_executing_traversal_social_does_not_supersede(self, flag_on):
        """Вердикт B, анти-флап грань: born-EXECUTING traversal (Н-50) НЕ
        вытесняется SOCIAL(3): 3 > 0 + 3 — ложно. Болтовня не ломает дорогу;
        выталкивают только SURVIVAL(6)/WINDOWED(7). Оба рельса нетронуты."""
        from types import SimpleNamespace

        from app.domain.action_priority import PRIORITY_SOCIAL
        from app.domain.movement import IntentDomain

        arb, saved = self._policy(True)
        try:
            from app.services.action.commitment_arbiter import (
                REASON_INCUMBENT,
                VERDICT_REJECT,
                CommitmentArbiter,
            )

            ss = {"active_traversals": {"n1": {"status": "MOVING"}}}
            CommitmentRegistry.mirror_traversal_materialized(
                ss, tick=5, npc_id="n1", cause="schedule:patrol", target_node="gate"
            )
            assert ss["active_commitments"]["n1"]["status"] == "EXECUTING"  # Н-50
            _intent = SimpleNamespace(
                actor_id="n1", target_node_id="bar", reason="social:greet",
                domain=IntentDomain.SOCIAL, intent_type="",
            )
            assert CommitmentArbiter.enforce_for_intent(ss, _intent, 6) is False
            # Частичный эффект запрещён (№14): оба рельса нетронуты.
            assert ss["active_traversals"]["n1"]["status"] == "MOVING"
            assert ss["active_commitments"]["n1"]["status"] == "EXECUTING"
            r = CommitmentArbiter.arbitrate(
                ss, "n1", "bar", "src", 6, candidate_priority=PRIORITY_SOCIAL
            )
            assert r.verdict == VERDICT_REJECT and r.reason == REASON_INCUMBENT
        finally:
            arb.ARBITER_ENFORCEMENT, arb.S203_4_ARBITER_INTERRUPT = saved

    def test_resolve_accepts_intent_domain_enum(self):
        from app.domain.action_priority import PRIORITY_SURVIVAL, resolve_candidate_priority
        from app.domain.movement import IntentDomain

        assert resolve_candidate_priority(intent_domain=IntentDomain.SURVIVAL) == PRIORITY_SURVIVAL


class TestS2034OwnershipMirrors:
    """Э5-a: non-supersiding зеркала task (флаг / коллизия / терминалы)."""

    def _mirrors(self, on: bool):
        import app.services.action.commitment_registry as cr

        saved = cr.S203_4_OWNERSHIP_MIRRORS
        cr.S203_4_OWNERSHIP_MIRRORS = on
        return cr, saved

    def test_mirrors_flag_off_noop(self):
        cr, saved = self._mirrors(False)
        try:
            ss = {}
            assert CommitmentRegistry.mirror_task_committed(ss, 1, "n1", "c", "t-1") is None
            assert CommitmentRegistry.mirror_task_terminal(ss, "n1", 2, "COMPLETED") is False
            assert "active_commitments" not in ss
        finally:
            cr.S203_4_OWNERSHIP_MIRRORS = saved

    def test_task_mirror_commit_and_lifecycle(self, flag_on):
        cr, saved = self._mirrors(True)
        try:
            ss = {}
            cm = CommitmentRegistry.mirror_task_committed(
                ss, 1, "n1", "warn:goran", "task-1-n1-0-dlg", priority=2
            )
            assert cm is not None and cm["status"] == "COMMITTED"
            assert cm["executor"] == "task" and cm["executor_ref"] == "task-1-n1-0-dlg"
            assert cm["priority"] == 2
            assert cm["priority_policy_version"] == "s203.4.v1"
            assert CommitmentRegistry.mirror_task_terminal(ss, "n1", 2, "EXECUTING")
            assert CommitmentRegistry.mirror_task_terminal(ss, "n1", 5, "COMPLETED")
            assert ss["commitment_history"]["n1"][-1]["status"] == "COMPLETED"
        finally:
            cr.S203_4_OWNERSHIP_MIRRORS = saved

    def test_task_mirror_collision_never_supersedes(self, flag_on):
        cr, saved = self._mirrors(True)
        try:
            ss = {"active_traversals": {"n1": {"status": "MOVING"}}}
            CommitmentRegistry.mirror_traversal_materialized(
                ss, tick=1, npc_id="n1", cause="schedule:patrol", target_node="gate"
            )
            # Коллизия: traversal-инкумбент жив → task-зеркало НЕ создаётся,
            # инкумбент НЕ прерывается (non-superseding; №14).
            assert CommitmentRegistry.mirror_task_committed(ss, 2, "n1", "c", "t-1") is None
            assert ss["active_commitments"]["n1"]["executor"] == "traversal"
            assert ss["active_traversals"]["n1"]["status"] == "MOVING"
        finally:
            cr.S203_4_OWNERSHIP_MIRRORS = saved

    def test_task_terminal_failed_requires_reason(self, flag_on):
        cr, saved = self._mirrors(True)
        try:
            ss = {}
            CommitmentRegistry.mirror_task_committed(ss, 1, "n1", "c", "t-1")
            CommitmentRegistry.mirror_task_terminal(ss, "n1", 2, "EXECUTING")
            assert CommitmentRegistry.mirror_task_terminal(ss, "n1", 3, "FAILED") is False
            assert ss["active_commitments"]["n1"]["status"] == "EXECUTING"  # не мутировано
            assert CommitmentRegistry.mirror_task_terminal(
                ss, "n1", 3, "FAILED", fail_reason="TASK_CRASH"
            )
            assert ss["commitment_history"]["n1"][-1]["fail_reason"] == "TASK_CRASH"
        finally:
            cr.S203_4_OWNERSHIP_MIRRORS = saved

    def test_task_terminal_stale_executor_rejected(self, flag_on):
        cr, saved = self._mirrors(True)
        try:
            ss = {}
            CommitmentRegistry.mirror_task_committed(ss, 1, "n1", "c", "t-1")
            # симуляция гонки: исполнитель сменился → дренаж обязан отказаться
            ss["active_commitments"]["n1"]["executor"] = "traversal"
            assert CommitmentRegistry.mirror_task_terminal(ss, "n1", 2, "COMPLETED") is False
            assert ss["active_commitments"]["n1"]["status"] == "COMMITTED"
        finally:
            cr.S203_4_OWNERSHIP_MIRRORS = saved

    def test_task_terminal_unknown_outcome_raises(self, flag_on):
        import pytest as _pytest

        cr, saved = self._mirrors(True)
        try:
            ss = {}
            CommitmentRegistry.mirror_task_committed(ss, 1, "n1", "c", "t-1")
            with _pytest.raises(ValueError):
                CommitmentRegistry.mirror_task_terminal(ss, "n1", 2, "BOGUS")
        finally:
            cr.S203_4_OWNERSHIP_MIRRORS = saved


class TestS2034TaskOutbox:
    """Э5-b: outbox → drain → реестр (воркер никогда не пишет реестр)."""

    def _mirrors(self, on: bool):
        import app.services.action.commitment_registry as cr

        saved = cr.S203_4_OWNERSHIP_MIRRORS
        cr.S203_4_OWNERSHIP_MIRRORS = on
        return cr, saved

    def test_outbox_drain_applies_terminals(self, flag_on):
        from app.services.game_loop.task_scheduler import TaskScheduler

        cr, saved = self._mirrors(True)
        try:
            sched = TaskScheduler()
            ss = {"tick": 3}
            CommitmentRegistry.mirror_task_committed(ss, 1, "n1", "warn:x", "t-1")
            sched._record_task_outcome("n1", "EXECUTING")
            sched._record_task_outcome("n1", "COMPLETED")
            sched.drain_commitment_outbox(ss)
            assert ss["commitment_history"]["n1"][-1]["status"] == "COMPLETED"
            assert not sched._commitment_outbox  # outbox опустошён
        finally:
            cr.S203_4_OWNERSHIP_MIRRORS = saved

    def test_drain_empty_outbox_noop(self):
        from app.services.game_loop.task_scheduler import TaskScheduler

        sched = TaskScheduler()
        ss = {}
        sched.drain_commitment_outbox(ss)  # тихий тик: no-op, ничего не создаёт
        assert "active_commitments" not in ss

    def test_expired_by_ref_strict(self, flag_on):
        import app.services.action.commitment_registry as cr

        saved = cr.S203_4_OWNERSHIP_MIRRORS
        cr.S203_4_OWNERSHIP_MIRRORS = True
        try:
            ss = {}
            CommitmentRegistry.mirror_task_committed(ss, 1, "n1", "c", "t-1")
            CommitmentRegistry.mirror_task_committed(ss, 2, "n1", "c", "t-2") is None
            # активен t-1-владелец не существует: вторая запись — коллизия,
            # активен t-1. EXPIRED по t-2 (чужой ref) обязан отклонить.
            assert CommitmentRegistry.mirror_task_expired_by_ref(ss, "n1", "t-2", 3) is False
            assert CommitmentRegistry.mirror_task_expired_by_ref(ss, "n1", "t-1", 3) is True
            assert ss["commitment_history"]["n1"][-1]["status"] == "EXPIRED"
        finally:
            cr.S203_4_OWNERSHIP_MIRRORS = saved

    def test_windup_mirror_windowed_priority(self, flag_on):
        import app.services.action.commitment_registry as cr
        from app.domain.action_priority import PRIORITY_WINDOWED

        saved = cr.S203_4_OWNERSHIP_MIRRORS
        cr.S203_4_OWNERSHIP_MIRRORS = True
        try:
            ss = {}
            cm = CommitmentRegistry.mirror_windup_committed(
                ss, 1, "n1", "attack", "t2", "windup:attack"
            )
            assert cm is not None
            assert cm["executor"] == "windup" and cm["priority"] == PRIORITY_WINDOWED
        finally:
            cr.S203_4_OWNERSHIP_MIRRORS = saved

    def test_sleep_reconcile_three_cases(self, flag_on):
        import app.services.action.commitment_registry as cr

        saved = cr.S203_4_OWNERSHIP_MIRRORS
        cr.S203_4_OWNERSHIP_MIRRORS = True
        try:
            ss = {}
            _sleepy = {"npc_id": "n1", "body_state": {
                "life_status": "ALIVE",
                "coupling_profile": {"coupling_mode": "SLEEP"}}}
            CommitmentRegistry.reconcile_sleep_ownership(ss, [_sleepy], 5)
            assert ss["active_commitments"]["n1"]["executor"] == "sleep"  # Y6 закрыт
            _awake = {"npc_id": "n1", "body_state": {
                "life_status": "ALIVE",
                "coupling_profile": {"coupling_mode": "FULL_WAKE"}}}
            CommitmentRegistry.reconcile_sleep_ownership(ss, [_awake], 6)
            assert ss["commitment_history"]["n1"][-1]["status"] == "COMPLETED"
            # исчезнувший спящий: создан и NPC удалён из мира
            CommitmentRegistry.reconcile_sleep_ownership(ss, [_sleepy], 7)
            CommitmentRegistry.reconcile_sleep_ownership(ss, [], 8)
            assert ss["commitment_history"]["n1"][-1]["status"] == "INTERRUPTED"
            assert ss["commitment_history"]["n1"][-1]["interrupt_reason"] == "SLEEP_VANISHED"
        finally:
            cr.S203_4_OWNERSHIP_MIRRORS = saved

    def test_drain_batch_order_preserved(self, flag_on):
        from app.services.game_loop.task_scheduler import TaskScheduler

        cr, saved = self._mirrors(True)
        try:
            sched = TaskScheduler()
            ss = {"tick": 2}
            CommitmentRegistry.mirror_task_committed(ss, 1, "n1", "c", "t-1")
            sched._record_task_outcome("n1", "FAILED", "TASK_ERROR")
            sched.drain_commitment_outbox(ss)
            # EXECUTING не записан — FAILED напрямую из COMMITTED запрещён
            # матрицей → честный отказ без мутации; обязательство живо.
            assert ss["active_commitments"]["n1"]["status"] == "COMMITTED"
        finally:
            cr.S203_4_OWNERSHIP_MIRRORS = saved


class TestS2B6CanonicalCoupling:
    """S2B6-A (вердикт Мастера Q1-B): канонические предикаты coupling-сна.

    Гварды против рецидива string-identity split: фантомные литералы
    ("SLEEPING"/"AWAKE" — doc-drift) не должны возвращаться ни в код,
    ни в фикстуры. Прецедент вечных греп-инвариантов — S231 (M1b.2.7).
    """

    def test_predicate_truth_table(self):
        from app.domain.body import CouplingMode, is_sleep_coupling

        # Реальные сон-режимы (enum и строки)
        for _mode in (CouplingMode.SLEEP, CouplingMode.DEEP_SLEEP, CouplingMode.REM):
            assert is_sleep_coupling(_mode)
        for _lit in ("SLEEP", "DEEP_SLEEP", "REM"):
            assert is_sleep_coupling(_lit)
        # Не-сон
        for _mode in (CouplingMode.DROWSY, CouplingMode.FULL_WAKE):
            assert not is_sleep_coupling(_mode)
        for _lit in ("DROWSY", "FULL_WAKE", "", None):
            assert not is_sleep_coupling(_lit)
        # Фантомные литералы doc-drift'а + case-ловушка поведенческой строки
        for _lit in ("SLEEPING", "AWAKE", "sleeping", "awake"):
            assert not is_sleep_coupling(_lit)

    def test_coupling_enum_membership_pinned(self):
        """Реестр CouplingMode заморожен: новый член = явное решение —
        он обязан пройти через предикат, иначе получит молчаливый
        default-False (класс тихой смерти)."""
        from app.domain.body import CouplingMode

        assert {m.value for m in CouplingMode} == {
            "FULL_WAKE",
            "DROWSY",
            "SLEEP",
            "DEEP_SLEEP",
            "REM",
        }

    def test_no_phantom_coupling_literals_in_app(self):
        """Вечный греп-гвард: tuple-членство/сравнение по фантомным
        coupling-литералам в backend/app запрещено — только канонический
        предикат is_sleep_coupling (domain/body.py)."""
        from pathlib import Path

        _root = Path(__file__).resolve().parents[1] / "app"
        _patterns = (
            'in ("SLEEPING"',
            'in ("AWAKE"',
            'in ("DEEP_SLEEPING"',
            '== "SLEEPING"',
            '== "AWAKE"',
            '== "DEEP_SLEEPING"',
        )
        _violations = []
        for _p in sorted(_root.rglob("*.py")):
            try:
                _src = _p.read_text(encoding="utf-8")
            except OSError:
                continue
            for _pat in _patterns:
                if _pat in _src:
                    _violations.append(f"{_p.relative_to(_root)}: {_pat}")
        assert not _violations, (
            f"Фантомные coupling-литералы в production: {_violations}"
        )


class TestS2B6OnsetGatedCoupling:
    """S2B6-B (вердикт В1): сон-режимы coupling — производное факта onset.

    Двусторонний инвариант: без body_state["sleep_onset_tick"] максимум
    DROWSY; с фактом — сон-семейство, переживающее decay pressure.
    Непрерывные оси (motor/vision) от факта не зависят (поправка Мастера:
    measurable restriction, не иммобилизация).
    """

    def _resolver(self):
        from app.services.npc.coupling_resolver import CouplingResolver

        return CouplingResolver()

    def test_no_onset_caps_sleep_modes(self):
        """Инверсия Phase A закрыта: без факта SLEEP/DEEP/REM недостижимы."""
        _r = self._resolver()
        assert _r.resolve({"sleep_pressure": 0.95, "arousal": 0.0}).coupling_mode.value == "DROWSY"
        assert _r.resolve({"sleep_pressure": 0.8, "arousal": 0.7}).coupling_mode.value == "DROWSY"
        assert _r.resolve({"sleep_pressure": 0.8, "arousal": 0.0}).coupling_mode.value == "DROWSY"

    def test_onset_unlocks_sleep_modes(self):
        _r = self._resolver()
        _on = {"sleep_onset_tick": 42}
        assert _r.resolve({"sleep_pressure": 0.95, "arousal": 0.0, **_on}).coupling_mode.value == "DEEP_SLEEP"
        assert _r.resolve({"sleep_pressure": 0.8, "arousal": 0.7, **_on}).coupling_mode.value == "REM"
        assert _r.resolve({"sleep_pressure": 0.8, "arousal": 0.0, **_on}).coupling_mode.value == "SLEEP"

    def test_onset_survives_pressure_decay(self):
        """Факт сна переживает decay sp: ×3-окно = весь эпизод (класс F2).
        Также пол-инвариант: низкое давление при живом факте — не бодрство."""
        _r = self._resolver()
        assert _r.resolve({"sleep_pressure": 0.05, "arousal": 0.0, "sleep_onset_tick": 42}).coupling_mode.value == "SLEEP"
        assert _r.resolve({"sleep_pressure": 0.05, "arousal": 0.7, "sleep_onset_tick": 42}).coupling_mode.value == "REM"

    def test_onset_tick_zero_is_valid_fact(self):
        """Тик 0 — валидный факт (ловушка falsy: строго is not None)."""
        _r = self._resolver()
        assert _r.resolve({"sleep_pressure": 0.8, "arousal": 0.0, "sleep_onset_tick": 0}).coupling_mode.value == "SLEEP"

    def test_axes_independent_of_onset(self):
        """Оси S189 не зависят от факта: рестрикция без сна-физиологии."""
        _r = self._resolver()
        _no = _r.resolve({"sleep_pressure": 0.95, "arousal": 0.0})
        _yes = _r.resolve({"sleep_pressure": 0.95, "arousal": 0.0, "sleep_onset_tick": 42})
        assert _no.motor_output_mult == _yes.motor_output_mult
        assert _no.external_vision_mult == _yes.external_vision_mult
        assert _no.motor_output_mult < 1.0  # рестрикция есть; не критерий иммобилизации

    def test_bidirectional_invariant_no_awake_label_with_fact(self):
        _r = self._resolver()
        assert _r.resolve({"sleep_pressure": 0.2, "arousal": 0.0}).coupling_mode.value == "FULL_WAKE"
        assert _r.resolve({"sleep_pressure": 0.2, "arousal": 0.0, "sleep_onset_tick": 42}).coupling_mode.value == "SLEEP"


class TestS2B6OnsetEligibility:
    """S2B6-B (вердикт В2/B2): eligibility = УСЛОВИЕ, не факт.

    Резолвер не пишет body_state; no_bed ≠ resting (вердикт §9 —
    чем заняться при отказе, решает поведение, не физиология).
    """

    def _npc(self, **kw):
        _d = {
            "npc_id": "n1",
            "routine": {"current": "sleeping"},
            "body_state": {"life_status": "ALIVE"},
            "psyche": {"stress": 0.0},
            "perceptual_kernel": {"threat_gradient": 0.0, "initiative_suppression": 0.0},
        }
        _d.update(kw)
        return _d

    def _resolve(self, npc, tick=10, bed_ok=True, settled=True):
        from app.services.npc.sleep_onset_resolver import SleepOnsetResolver

        return SleepOnsetResolver.resolve(npc, tick, bed_ok, settled)

    def test_eligible_when_all_conditions_met(self):
        _e = self._resolve(self._npc())
        assert _e.eligible and _e.reason == "" and _e.tick == 10

    def test_no_intent_blocks(self):
        _e = self._resolve(self._npc(routine={"current": "working"}))
        assert not _e.eligible and _e.reason == "no_intent"

    def test_no_bed_blocks(self):
        _e = self._resolve(self._npc(), bed_ok=False)
        assert not _e.eligible and _e.reason == "no_bed"

    def test_travelling_blocks(self):
        _e = self._resolve(self._npc(), settled=False)
        assert not _e.eligible and _e.reason == "travelling"

    def test_dead_blocks(self):
        _e = self._resolve(self._npc(body_state={"life_status": "DEAD"}))
        assert not _e.eligible and _e.reason == "dead"

    def test_gap9_threat_blocks(self):
        _e = self._resolve(self._npc(perceptual_kernel={
            "threat_gradient": 0.4, "initiative_suppression": 0.0}))
        assert not _e.eligible and _e.reason == "blocked_threat"

    def test_gap9_stress_blocks(self):
        _e = self._resolve(self._npc(psyche={"stress": 60.0}))
        assert not _e.eligible and _e.reason == "blocked_stress"

    def test_paralysis_blocks(self):
        _e = self._resolve(self._npc(perceptual_kernel={
            "threat_gradient": 0.0, "initiative_suppression": 0.8}))
        assert not _e.eligible and _e.reason == "blocked_paralysis"


class TestS2B6OnsetTransition:
    """S2B6-B: eligibility → ФАКТ; обе wake-причины; В3-динамика."""

    class _Bus:
        def __init__(self):
            self.events = []

        def publish(self, e):
            self.events.append(e)

    def _svc(self):
        from app.services.npc.sleep_lifecycle_service import SleepLifecycleService

        return SleepLifecycleService(self._Bus())

    def _awake(self, **kw):
        _d = {
            "npc_id": "n1", "id": "n1",
            "routine": {"current": "sleeping"},
            "body_state": {"life_status": "ALIVE", "sleep_pressure": 0.0, "arousal": 0.0, "fatigue": 0.0},
            "psyche": {"stress": 0.0},
            "perceptual_kernel": {"threat_gradient": 0.0, "initiative_suppression": 0.0, "uncertainty": 0.0, "anomaly_score": 0.0},
        }
        _d.update(kw)
        return _d

    def _elig(self, eligible=True, tick=5):
        from app.domain.body import SleepOnsetEligibility

        return SleepOnsetEligibility(eligible=eligible, tick=tick)

    def test_eligible_onset_writes_fact(self):
        _svc = self._svc()
        _n = self._awake()
        _svc.process_sleep_lifecycle(_n, 7, self._elig(tick=7))
        assert _n["body_state"]["sleep_onset_tick"] == 7
        assert _n["body_state"]["wake_duration"] == 0
        assert _n["body_state"]["coupling_profile"]["coupling_mode"] in ("SLEEP", "DEEP_SLEEP", "REM")

    def test_no_eligibility_no_onset(self):
        _svc = self._svc()
        _n = self._awake()
        _svc.process_sleep_lifecycle(_n, 7)
        assert "sleep_onset_tick" not in _n["body_state"]
        assert _n["body_state"]["wake_duration"] == 1  # wd растёт

    def test_ineligible_blocks_onset(self):
        _svc = self._svc()
        _n = self._awake()
        _svc.process_sleep_lifecycle(_n, 7, self._elig(eligible=False))
        assert "sleep_onset_tick" not in _n["body_state"]

    def test_intent_withdrawal_wakes(self):
        _svc = self._svc()
        _n = self._awake(routine={"current": "working"},
                         body_state={"life_status": "ALIVE", "sleep_pressure": 0.8,
                                     "arousal": 0.0, "fatigue": 50.0, "sleep_onset_tick": 3})
        _res = _svc.process_sleep_lifecycle(_n, 10)
        assert _res == []  # поведение уже у расписания; физиология только чистится
        # Отсутствие факта = отсутствие ключа (pop; None-зомби нет).
        # dict[missing] бросает KeyError ДО or — старое выражение было багом теста.
        assert "sleep_onset_tick" not in _n["body_state"]
        assert _n["body_state"]["wake_duration"] == 0
        assert any(getattr(e, "type", "") == "sleep_end" for e in _svc._event_bus.events)

    def test_arousal_wake_clears_fact(self):
        _svc = self._svc()
        _n = self._awake(body_state={"life_status": "ALIVE", "sleep_pressure": 0.8,
                                     "arousal": 1.0, "fatigue": 50.0, "sleep_onset_tick": 0})
        _n["perceptual_kernel"]["threat_gradient"] = 1.0
        _res = _svc.process_sleep_lifecycle(_n, 10)
        assert _res != []  # SceneChange пробуждения (архаичная ветка жива)
        assert "sleep_onset_tick" not in _n["body_state"]
        assert _n["body_state"]["wake_duration"] == 0
        assert not _n["routine"]["current"]  # routine сброшен гейтом

    def test_fatigue_doubles_pressure_rate(self):
        _svc = self._svc()
        _a = self._awake()
        _b = self._awake()
        _b["body_state"]["fatigue"] = 100.0
        _svc.process_sleep_lifecycle(_a, 1)
        _svc.process_sleep_lifecycle(_b, 1)
        assert _a["body_state"]["sleep_pressure"] == 0.005
        assert _b["body_state"]["sleep_pressure"] == 0.01  # ×2 при coeff=1.0

    def test_wake_duration_accumulates(self):
        _svc = self._svc()
        _n = self._awake()
        _svc.process_sleep_lifecycle(_n, 1)
        _svc.process_sleep_lifecycle(_n, 2)
        assert _n["body_state"]["wake_duration"] == 2

    def test_differential_positive_onset_to_x3_chain(self):
        """S2B6-B: ПОЛОЖИТЕЛЬНАЯ половина дифференциального теста (Мастер,
        §13 вердикта): факт onset → coupling SLEEP → BodyEngine ×3.
        Отрицательная половина доказана production-зондом Wave 5
        (elig=True=0/1200 → фактов 0 → ×3-тиков 0): BED-контекст в
        кампании отсутствует — эскалация данных, не обход в тесте."""
        from app.services.body.body_engine import BodyEngine
        from app.services.npc.coupling_resolver import CouplingResolver

        _mode = CouplingResolver().resolve(
            {"sleep_pressure": 0.8, "arousal": 0.0, "sleep_onset_tick": 5}
        ).coupling_mode
        assert _mode.value == "SLEEP"  # факт → режим (Wave 1)
        _p = BodyEngine().handle(
            [{
                "npc_id": "n1", "life_status": "ALIVE",
                "activity": "sleeping", "velocity": (0.0, 0.0),
                "coupling_mode": _mode.value, "body_mass": 1.0,
            }],
            "t", 6,
        )[0].payload
        assert _p.fatigue_delta == -0.245  # режим → ×3 (Phase A)
        assert _p.energy_delta == 0.76

    def test_wara_body_state_keys_survive_json_roundtrip(self):
        import json

        _bs = {"sleep_onset_tick": 42, "wake_duration": 17.0, "sleep_pressure": 0.5}
        assert json.loads(json.dumps(_bs)) == _bs  # dict-путь персистенции


class TestS2034WindupSerialization:
    """Э6: ActionWindup round-trip (§12 WARA)."""

    def test_windup_roundtrip(self):
        from app.domain.action_windup import ActionWindup, WindupStatus

        _orig = ActionWindup(
            actor_id="n1", target_id="n2", action_type="steal",
            started_tick=5, duration_ticks=2,
            status=WindupStatus.PENDING,
            held_intent_id="cmt-abc123",
        )
        _d = _orig.to_dict()
        _restored = ActionWindup.from_dict(_d)
        assert _restored == _orig

    def test_windup_roundtrip_interrupted(self):
        from app.domain.action_windup import ActionWindup, WindupStatus

        _orig = ActionWindup(
            actor_id="n1", target_id="n2", action_type="attack",
            started_tick=3, duration_ticks=2,
            status=WindupStatus.INTERRUPTED,
        )
        _restored = ActionWindup.from_dict(_orig.to_dict())
        assert _restored == _orig
        assert _restored.status == WindupStatus.INTERRUPTED

    def test_communication_intent_roundtrip(self):
        from app.domain.communication import CommunicationIntent, ExposureLevel
        from app.domain.epistemology import Predicate, Proposition

        _orig = CommunicationIntent(
            speaker="n1", audience="n2", topic="trade",
            intent_type="warn", emotional_state="angry",
            exposure_level=ExposureLevel(semantic="normal"),
            semantic_action="warn", target_id="n2",
            thread_id="t-1", priority=0.7,
            proposition=Proposition(
                subject_id="n1",
                predicate=Predicate.STOLE,
                object_id="gold",
                polarity=True,
            ),
        )
        _restored = CommunicationIntent.from_dict(_orig.to_dict())
        assert _restored == _orig
        assert _restored.exposure_level.semantic == "normal"
        assert _restored.proposition is not None
        assert _restored.proposition.predicate == Predicate.STOLE

    def test_communication_intent_roundtrip_no_proposition(self):
        from app.domain.communication import CommunicationIntent, ExposureLevel

        _orig = CommunicationIntent(
            speaker="n1", audience="all", topic="gossip",
            intent_type="talk", emotional_state="нейтрально",
            exposure_level=ExposureLevel(semantic="whisper"),
        )
        _restored = CommunicationIntent.from_dict(_orig.to_dict())
        assert _restored == _orig
        assert _restored.proposition is None
        assert _restored.exposure_level.physical_radius is not None  # __post_init__


class TestS2B1BodyEngine:
    """S2B.1: BodyEngine pipeline proof (energy as artificial variable)."""

    def test_expenditure_when_active(self):
        from app.services.body.body_engine import BodyEngine

        _engine = BodyEngine()
        _npc = {"npc_id": "n1", "life_status": "ALIVE",
                "activity": "working", "body_mass": 1.0}
        _deltas = _engine.handle([_npc], "test", 1)
        assert len(_deltas) == 1
        assert _deltas[0].payload.energy_delta == -0.1  # S2B.2: load=0.5 → exp=0.25 rec=0.15 → -0.10

    def test_recovery_when_idle(self):
        from app.services.body.body_engine import BodyEngine

        _engine = BodyEngine()
        _npc = {"npc_id": "n1", "life_status": "ALIVE",
                "activity": "", "body_mass": 1.0}
        _deltas = _engine.handle([_npc], "test", 1)
        assert len(_deltas) == 1
        assert _deltas[0].payload.energy_delta == 0.3  # S2B.2: load=0.0 → rec=0.30 exp=0 → +0.30

    def test_skip_dead(self):
        from app.services.body.body_engine import BodyEngine

        _engine = BodyEngine()
        _npc = {"npc_id": "n1", "life_status": "DEAD"}
        assert _engine.handle([_npc], "test", 1) == []

    def test_pipeline_through_applicator(self):
        """Full: BodyEngine → StateDeltas → StateApplicator → body_state."""
        from app.services.body.body_engine import BodyEngine
        from app.services.npc.state_applicator import StateApplicator

        _engine = BodyEngine()
        _npc = {"npc_id": "n1", "life_status": "ALIVE",
                "activity": "working", "body_mass": 1.0}
        _deltas = _engine.handle([_npc], "test", 1)
        assert _deltas[0].payload.energy_delta == -0.1  # S2B.2: working load=0.5

        # Apply: mock state (only body_state needed by _apply_physiology_deltas)
        class _MockState:
            pass
        _state = _MockState()
        _state.body_state = {"energy": 100.0, "current_hp": 100,
                             "pain": 0.0, "fatigue": 0.0,
                             "blood_loss": 0.0, "shock_impulse": 0.0,
                             "injuries": [], "modifiers": {}, "statuses": []}
        _applicator = object.__new__(StateApplicator)
        _applicator._apply_physiology_deltas(
            _state, 0, 0, 0, 0, [], [], [], 0,
            energy_delta=_deltas[0].payload.energy_delta,
        )
        assert _state.body_state["energy"] == 99.9  # 100 - 0.1

    def test_energy_clamp_to_zero(self):
        """Boundary: energy can't go below 0 (valid range semantics)."""
        from app.services.npc.state_applicator import StateApplicator

        class _MockState:
            pass
        _state = _MockState()
        _state.body_state = {"energy": 0.5, "current_hp": 100, "pain": 0.0,
                             "fatigue": 0.0, "blood_loss": 0.0,
                             "shock_impulse": 0.0, "injuries": [],
                             "modifiers": {}, "statuses": []}
        _applicator = object.__new__(StateApplicator)
        _applicator._apply_physiology_deltas(
            _state, 0, 0, 0, 0, [], [], [], 0, energy_delta=-1.0,
        )
        assert _state.body_state["energy"] == 0.0  # clamped, not -0.5


class TestS2B2EnergyDynamics:
    """S2B.2: energy dynamics — 5 experiments (determinism, monotonicity, recovery, replay, body)."""

    def _engine(self):
        from app.services.body.body_engine import BodyEngine
        return BodyEngine()

    def _npc(self, **kw):
        # ADR-O-373: вход BodyEngine — ПЛОСКИЙ NPCStateSnapshot (Phase 0.5)
        _d = {"npc_id": "n1", "life_status": "ALIVE", "stress": 0.0,
              "velocity": (0.0, 0.0), "activity": "", "coupling_mode": "",
              "body_mass": 1.0}
        _d.update(kw)
        return _d

    # A: determinism — same input → same output
    def test_a_determinism(self):
        _e = self._engine()
        _npc = self._npc(activity="working")
        _d1 = _e.handle([_npc], "t", 1)
        _d2 = _e.handle([_npc], "t", 1)
        assert _d1[0].payload.energy_delta == _d2[0].payload.energy_delta

    # B: monotonicity — IDLE < WALK < RUN
    def test_b_monotonicity(self):
        _e = self._engine()
        _idle = self._engine().handle([self._npc(activity="")], "t", 1)[0].payload.energy_delta
        _walk = _e.handle([self._npc(velocity=(0.3, 0.0))], "t", 1)[0].payload.energy_delta
        _run = _e.handle([self._npc(velocity=(0.8, 0.0))], "t", 1)[0].payload.energy_delta
        # expenditure increases → delta decreases (more negative)
        assert _idle > _walk > _run

    # C: recovery — rest/sleep → positive delta
    def test_c_recovery(self):
        _e = self._engine()
        _idle_delta = _e.handle([self._npc(activity="")], "t", 1)[0].payload.energy_delta
        assert _idle_delta > 0  # recovery exceeds expenditure at idle

    def test_c_sleep_recovery_bonus(self):
        _e = self._engine()
        _awake_idle = _e.handle([self._npc(activity="")], "t", 1)[0].payload.energy_delta
        _sleeping = _e.handle([self._npc(
            activity="sleeping", coupling_mode="SLEEP"
        )], "t", 1)[0].payload.energy_delta
        assert _sleeping > _awake_idle  # sleep bonus

    # D: replay — pure function → same inputs → same outputs (replay by construction)
    def test_d_replay_determinism(self):
        _e = self._engine()
        _npc = self._npc(activity="guarding_gate", body_mass=1.2)
        _d1 = _e.handle([_npc], "t", 10)[0].payload.energy_delta
        _d2 = _e.handle([_npc], "t", 10)[0].payload.energy_delta
        _d3 = _e.handle([_npc], "t", 10)[0].payload.energy_delta
        assert _d1 == _d2 == _d3  # no hidden state, no wall-clock → replay-safe

    # E: body sensitivity — same activity, different body_mass → different cost
    def test_e_body_sensitivity(self):
        _e = self._engine()
        _light = _e.handle([self._npc(
            activity="working", body_mass=0.8
        )], "t", 1)[0].payload.energy_delta
        _heavy = _e.handle([self._npc(
            activity="working", body_mass=1.2
        )], "t", 1)[0].payload.energy_delta
        # heavier body → more expenditure → lower (more negative) delta
        assert _heavy < _light


class TestS2B3Hydration:
    """S2B.3: hydration dynamics — one-way loss (no passive recovery)."""

    def _engine(self):
        from app.services.body.body_engine import BodyEngine
        return BodyEngine()

    def _npc(self, **kw):
        # ADR-O-373: вход BodyEngine — ПЛОСКИЙ NPCStateSnapshot (Phase 0.5)
        _d = {"npc_id": "n1", "life_status": "ALIVE",
              "activity": "", "velocity": (0.0, 0.0),
              "coupling_mode": "", "body_mass": 1.0}
        _d.update(kw)
        return _d

    def test_baseline_loss_at_idle(self):
        """Even at rest, hydration decreases (respiration, basal loss)."""
        _e = self._engine()
        _d = _e.handle([self._npc(activity="")], "t", 1)[0].payload
        assert _d.hydration_delta < 0  # always negative (one-way drain)

    def test_monotonicity_load(self):
        """IDLE < WALK < RUN → hydration loss increases."""
        _e = self._engine()
        _idle = _e.handle([self._npc(activity="")], "t", 1)[0].payload.hydration_delta
        _walk = _e.handle([self._npc(velocity=(0.3, 0.0))], "t", 1)[0].payload.hydration_delta
        _run = _e.handle([self._npc(velocity=(0.8, 0.0))], "t", 1)[0].payload.hydration_delta
        assert _idle > _walk > _run  # more negative = more loss

    def test_determinism(self):
        _e = self._engine()
        _npc = self._npc(activity="working")
        _d1 = _e.handle([_npc], "t", 1)[0].payload.hydration_delta
        _d2 = _e.handle([_npc], "t", 1)[0].payload.hydration_delta
        assert _d1 == _d2

    def test_body_sensitivity(self):
        """Heavier body → more hydration loss."""
        _e = self._engine()
        _light = _e.handle([self._npc(
            activity="working", body_mass=0.8
        )], "t", 1)[0].payload.hydration_delta
        _heavy = _e.handle([self._npc(
            activity="working", body_mass=1.2
        )], "t", 1)[0].payload.hydration_delta
        assert _heavy < _light  # more negative


class TestS2B4Nutrition:
    """S2B.4: nutrition — one-way loss; медленнее hydration (иерархия кризисов).
    nutrition = STOCK (запас), НЕ hunger: производное давление — S2B.10."""

    def _engine(self):
        from app.services.body.body_engine import BodyEngine
        return BodyEngine()

    def _npc(self, **kw):
        # ADR-O-373: вход BodyEngine — ПЛОСКИЙ NPCStateSnapshot (Phase 0.5)
        _d = {"npc_id": "n1", "life_status": "ALIVE",
              "activity": "", "velocity": (0.0, 0.0),
              "coupling_mode": "", "body_mass": 1.0}
        _d.update(kw)
        return _d

    def test_baseline_loss_at_idle(self):
        """Покой: delta == -BASE_NUTRITION_LOSS (load=0, body_mass=1.0)."""
        _e = self._engine()
        _d = _e.handle([self._npc(activity="")], "t", 1)[0].payload
        assert _d.nutrition_delta == round(-_e.BASE_NUTRITION_LOSS, 4)

    def test_monotonicity_load(self):
        """IDLE < WALK < RUN → потеря питания строго растёт."""
        _e = self._engine()
        _idle = _e.handle([self._npc(activity="")], "t", 1)[0].payload.nutrition_delta
        _walk = _e.handle([self._npc(velocity=(0.3, 0.0))], "t", 1)[0].payload.nutrition_delta
        _run = _e.handle([self._npc(velocity=(0.8, 0.0))], "t", 1)[0].payload.nutrition_delta
        assert _idle > _walk > _run  # more negative = more loss

    def test_determinism(self):
        """Pure function: same inputs → same outputs (replay by construction)."""
        _e = self._engine()
        _npc = self._npc(activity="working")
        _d1 = _e.handle([_npc], "t", 1)[0].payload.nutrition_delta
        _d2 = _e.handle([_npc], "t", 1)[0].payload.nutrition_delta
        assert _d1 == _d2

    def test_body_sensitivity(self):
        """Тяжелее тело (body_mass) → больше расход питания."""
        _e = self._engine()
        _light = _e.handle([self._npc(
            activity="working", body_mass=0.8
        )], "t", 1)[0].payload.nutrition_delta
        _heavy = _e.handle([self._npc(
            activity="working", body_mass=1.2
        )], "t", 1)[0].payload.nutrition_delta
        assert _heavy < _light  # more negative

    def test_slower_than_hydration_invariant(self):
        """Инвариант Мастера (S2B.4 v1 calibration): питание истощается
        МЕДЛЕННЕЕ воды при ЛЮБЫХ (load, body_mass) — по базовой ставке И по
        load-коэффициенту ОТДЕЛЬНО. Калибровка не может инвертировать
        иерархию кризисов молча."""
        _e = self._engine()
        assert _e.BASE_NUTRITION_LOSS < _e.BASE_HYDRATION_LOSS  # 0.05 < 0.2
        assert _e.NUTRITION_LOAD_COEFF < 1.0  # hydration-коэф. в формуле = 1.0
        for _kw in (
            {"activity": ""},            # load=0.0
            {"activity": "working"},     # load=0.5
            {"velocity": (0.8, 0.0)},    # load=0.9 (RUN)
        ):
            _p = _e.handle([self._npc(**_kw)], "t", 1)[0].payload
            assert _p.nutrition_delta > _p.hydration_delta  # менее отрицательный


    def test_nutrition_clamp_to_zero(self):
        """Boundary (зеркало S2B.1 test_energy_clamp_to_zero): nutrition
        не уходит ниже 0 — семантика валидного диапазона 0-100, не -0.5."""
        from app.services.npc.state_applicator import StateApplicator

        class _MockState:
            pass
        _state = _MockState()
        _state.body_state = {"nutrition": 0.5, "current_hp": 100, "pain": 0.0,
                             "fatigue": 0.0, "blood_loss": 0.0,
                             "shock_impulse": 0.0, "injuries": [],
                             "modifiers": {}, "statuses": []}
        _applicator = object.__new__(StateApplicator)
        _applicator._apply_physiology_deltas(
            _state, 0, 0, 0, 0, [], [], [], 0, nutrition_delta=-1.0,
        )
        assert _state.body_state["nutrition"] == 0.0  # clamped, not -0.5


class TestS2B5ProjectionContract:
    """ADR-O-373: регрессионный тест класса FLAT — снапшот Phase 0.5 обязан
    нести плоские поля BodyEngine. До S2B.5 S2B.1–2B.4 были production-мёртвыми
    (unit-фикстуры кормили raw-формой, которой рантайм не существует)."""

    RAW = {
        "id": "n1",  # билдер читает npc.get("id") (tick_utils:70), не npc_id
        "npc_id": "n1",
        "life_status": "ALIVE",
        "body_state": {
            "current_hp": 100, "energy": 100.0, "hydration": 100.0,
            "nutrition": 100.0, "fatigue": 0.0, "body_mass": 1.1,
            "coupling_profile": {"coupling_mode": "FULL_WAKE"},
        },
        "routine": {"current": "working"},
    }

    def test_snapshot_carries_flat_body_fields(self):
        from app.services.tick_utils import build_npc_snapshots

        _snap = build_npc_snapshots([dict(self.RAW)])[0]
        assert _snap["npc_id"] == "n1"  # источник id пиннится: билдер берёт "id"
        assert _snap["activity"] == "working"  # routine-резолв — в билдере
        assert _snap["body_mass"] == 1.1
        assert _snap["coupling_mode"] == "FULL_WAKE"
        assert _snap["velocity"] == (0.0, 0.0)
        assert _snap["fatigue"] == 0.0  # flat SSOT-проекция читается

    def test_engine_emits_on_real_projection(self):
        """THE FLAT-regression: снапшот → BodyEngine → дельты ЕСТЬ."""
        from app.services.body.body_engine import BodyEngine
        from app.services.tick_utils import build_npc_snapshots

        _snaps = build_npc_snapshots([dict(self.RAW)])
        _deltas = BodyEngine().handle(_snaps, "t", 1)
        assert len(_deltas) == 1
        assert _deltas[0].payload.energy_delta != 0.0


class TestS2B5Fatigue:
    """S2B.5 (ADR-O-373): fatigue — two-way износ, единственная per-tick
    проекция. Шкала: 0=свеж, 100=истощён («плохо вверх», инверсия energy).
    Фикстуры — ПЛОСКИЙ снапшот (миграция S2B.1–2B.4 тем же ADR)."""

    def _engine(self):
        from app.services.body.body_engine import BodyEngine
        return BodyEngine()

    def _snap(self, **kw):
        _d = {"npc_id": "n1", "life_status": "ALIVE", "stress": 0.0,
              "velocity": (0.0, 0.0), "activity": "", "coupling_mode": "",
              "body_mass": 1.0}
        _d.update(kw)
        return _d

    def test_run_accumulates_wear(self):
        """RUN (load 0.9): wear 0.225 − recovery 0.01 = +0.215/тик."""
        _p = self._engine().handle([self._snap(velocity=(0.8, 0.0))], "t", 1)[0].payload
        assert _p.fatigue_delta == 0.215

    def test_idle_recovery_strictly_negative(self):
        """Пассивный отдых слабый: idle → −0.1 (~1000 тиков без сна)."""
        _p = self._engine().handle([self._snap()], "t", 1)[0].payload
        assert _p.fatigue_delta == -0.1

    def test_sleep_recovery_beats_idle(self):
        """Сон (load 0.1, ×3): −0.245; строго глубже idle-восстановления."""
        _e = self._engine()
        _idle = _e.handle([self._snap()], "t", 1)[0].payload.fatigue_delta
        _sleep = _e.handle(
            [self._snap(coupling_mode="SLEEP")], "t", 1
        )[0].payload.fatigue_delta
        assert _sleep == -0.245
        assert _sleep < _idle

    def test_monotonicity_load_inverted_sign(self):
        """Знак ОБРАТЕН energy-тестам: износ растёт с нагрузкой —
        delta(RUN) > delta(WALK) > delta(IDLE) (кодирование по формуле §4.2)."""
        _e = self._engine()
        _idle = _e.handle([self._snap()], "t", 1)[0].payload.fatigue_delta
        _walk = _e.handle(
            [self._snap(velocity=(0.3, 0.0))], "t", 1
        )[0].payload.fatigue_delta
        _run = _e.handle(
            [self._snap(velocity=(0.8, 0.0))], "t", 1
        )[0].payload.fatigue_delta
        assert _run > _walk > _idle

    def test_wear_slower_than_fuel_invariant(self):
        """Инвариант Мастера (закон №11-аналог): износ медленнее топлива —
        0.25 < 0.5. Отдельный тест: калибровка не инвертирует иерархию молча."""
        _e = self._engine()
        assert _e.BASE_FATIGUE_RATE < _e.BASE_EXPENDITURE_RATE

    def test_body_sensitivity(self):
        """Тяжелее тело → больше износ → delta более положительный."""
        _e = self._engine()
        _light = _e.handle(
            [self._snap(activity="working", body_mass=0.8)], "t", 1
        )[0].payload.fatigue_delta
        _heavy = _e.handle(
            [self._snap(activity="working", body_mass=1.2)], "t", 1
        )[0].payload.fatigue_delta
        assert _heavy > _light

    def test_determinism(self):
        _e = self._engine()
        _npc = self._snap(activity="guarding_gate")
        _d1 = _e.handle([_npc], "t", 7)[0].payload.fatigue_delta
        _d2 = _e.handle([_npc], "t", 7)[0].payload.fatigue_delta
        assert _d1 == _d2

    def test_composition_with_combat_producer(self):
        """Двух-продюсерная модель (вердикт Мастера: два producer'а допустимы,
        два per-tick physiological engines — нет). PHYSICS_COMPOSITE =
        PASS-THROUGH на агрегации (не «складывает»): дельты сохраняются как
        отдельные StateDeltas, аддитивность возникает при последовательном
        применении единым StateApplicator. Ассерты: структура/сохранность/порядок."""
        from app.models.delta_payloads import PhysiologyPayload
        from app.models.state_delta import DeltaDomain, StateDeltas
        from app.services.npc.state_applicator import StateApplicator
        from app.services.tick_utils import aggregate_deltas

        _combat = StateDeltas(
            npc_id="n1", domain=DeltaDomain.PHYSIOLOGY,
            payload=PhysiologyPayload(fatigue_delta=5.0),
            source="impact_resolution",
        )
        _engine_d = StateDeltas(
            npc_id="n1", domain=DeltaDomain.PHYSIOLOGY,
            payload=PhysiologyPayload(fatigue_delta=0.215),
            source="body_engine",
        )

        # (i) СТРУКТУРА: PHYSICS_COMPOSITE = pass-through — обе дельты
        # переживают агрегацию как отдельные StateDeltas (split давал 1)
        _agg = aggregate_deltas([_combat, _engine_d])
        _phys = [d for d in _agg if d.domain == DeltaDomain.PHYSIOLOGY]
        assert len(_phys) == 2

        # (ii) СОХРАННОСТЬ: вклад combat'а не теряется (при split было 0.215)
        _sum = sum(d.payload.fatigue_delta for d in _phys)
        assert abs(_sum - 5.215) < 1e-9

        # (iii) ПОРЯДОК: correctness не зависит от порядка продюсеров
        _agg_rev = aggregate_deltas([_engine_d, _combat])
        _phys_rev = [d for d in _agg_rev if d.domain == DeltaDomain.PHYSIOLOGY]
        assert len(_phys_rev) == 2
        assert abs(sum(d.payload.fatigue_delta for d in _phys_rev) - 5.215) < 1e-9

        # (iv) single-writer применяет обе последовательно; clamp 0–100 держит
        class _MockState:
            pass

        _state = _MockState()
        _state.body_state = {"fatigue": 98.0, "current_hp": 100, "pain": 0.0,
                             "blood_loss": 0.0, "shock_impulse": 0.0,
                             "injuries": [], "modifiers": {}, "statuses": []}
        _applicator = object.__new__(StateApplicator)
        # слоты: (state, hp, pain, fatigue, blood, inj, add_st, rm_st, shock)
        _applicator._apply_physiology_deltas(_state, 0, 0, 5.0, 0, [], [], [], 0)
        _applicator._apply_physiology_deltas(_state, 0, 0, 0.215, 0, [], [], [], 0)
        assert _state.body_state["fatigue"] == 100.0  # 103.215 → clamp

        _state2 = _MockState()
        _state2.body_state = {"fatigue": 0.1, "current_hp": 100, "pain": 0.0,
                              "blood_loss": 0.0, "shock_impulse": 0.0,
                              "injuries": [], "modifiers": {}, "statuses": []}
        _applicator._apply_physiology_deltas(_state2, 0, 0, -0.245, 0, [], [], [], 0)
        assert _state2.body_state["fatigue"] == 0.0  # −0.145 → clamp


class TestDeltaPolicyIdentity:
    """ADR-O-373 (вердикт Мастера): ONE POLICY TYPE / ONE POLICY REGISTRY /
    ONE ENUM IDENTITY. Enum Identity Split (дубль в dto.py) ломал сравнение
    policy == ReductionPolicy.PHYSICS_COMPOSITE в aggregate_deltas: PHYSIOLOGY
    молча падала в algebraic-группировку, вклад одного из продюсеров терялся
    (last-wins). Пиннится IDENTITY объектов (is), не равенство значений:
    два одинаковых enum'а — разные классы — снова дадут тихий split."""

    def test_single_policy_and_registry_identity(self):
        from app.models.state_delta import (
            DELTA_POLICY_REGISTRY as CanonicalRegistry,
        )
        from app.models.state_delta import (
            ReductionPolicy as CanonicalPolicy,
        )
        from app.services.dto import DELTA_POLICY_REGISTRY as DtoRegistry
        from app.services.dto import ReductionPolicy as DtoPolicy

        assert DtoPolicy is CanonicalPolicy  # identity, не ==
        assert DtoRegistry is CanonicalRegistry

    def test_physiology_policy_is_physics_composite(self):
        from app.models.state_delta import (
            DELTA_POLICY_REGISTRY,
            DeltaDomain,
            ReductionPolicy,
        )

        assert (
            DELTA_POLICY_REGISTRY[DeltaDomain.PHYSIOLOGY]
            is ReductionPolicy.PHYSICS_COMPOSITE
        )


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

# ── S203.2: Arbiter ─────────────────────────────────────────────────────────


class TestCommitmentArbiter:
    def test_pass_when_no_incumbent(self):
        from app.services.action.commitment_arbiter import (
            VERDICT_PASS,
        )

        ss = {}
        r = CommitmentArbiter.arbitrate(ss, "n1", "bar", "schedule:eating", 5)
        assert r.verdict == VERDICT_PASS and r.reason is None

    def test_reject_duplicate_same_target(self):
        from app.services.action.commitment_arbiter import (
            REASON_DUPLICATE,
            VERDICT_REJECT,
        )

        ss = {}
        CommitmentRegistry.commit(ss, tick=1, npc_id="n1", action="MOVE", cause="c", target_id="bar")
        CommitmentRegistry.mark_executing(ss, "n1", 1)
        r = CommitmentArbiter.arbitrate(ss, "n1", "bar", "need:hunger", 2)
        assert r.verdict == VERDICT_REJECT and r.reason == REASON_DUPLICATE
        assert r.incumbent_target == "bar"

    def test_reject_incumbent_different_target(self):
        from app.services.action.commitment_arbiter import (
            REASON_INCUMBENT,
            VERDICT_REJECT,
        )

        ss = {}
        CommitmentRegistry.commit(ss, tick=1, npc_id="n1", action="MOVE", cause="c", target_id="bar")
        CommitmentRegistry.mark_executing(ss, "n1", 1)
        r = CommitmentArbiter.arbitrate(ss, "n1", "kitchen", "proactive_offer_job", 2)
        assert r.verdict == VERDICT_REJECT and r.reason == REASON_INCUMBENT

    def test_committed_counts_as_occupied(self):
        """Мастер, критическое: COMMITTED без traversal — кандидат отвергнут
        (commitment race исключён), даже если traversal ещё не материализован."""
        from app.services.action.commitment_arbiter import (
            REASON_INCUMBENT,
            VERDICT_REJECT,
        )

        ss = {}
        CommitmentRegistry.commit(ss, tick=1, npc_id="n1", action="MOVE", cause="c", target_id="bar")
        # статус COMMITTED — mark_executing НЕ вызван (окно между COMMIT и
        # материализацией, которое S203.2 не создаёт, но обязана защищать)
        r = CommitmentArbiter.arbitrate(ss, "n1", "kitchen", "any", 1)
        assert r.verdict == VERDICT_REJECT and r.reason == REASON_INCUMBENT

    def test_orphaned_terminal_incumbent_passes(self):
        """Осиротевший терминальный инкумбент (sweep не прошёл) — PASS:
        суперсессию выполнит mirror; арбитр не создаёт starvation."""
        from app.services.action.commitment_arbiter import (
            VERDICT_PASS,
        )

        ss = {"active_commitments": {"n1": {"status": "INTERRUPTED", "commitment_id": "x", "target_id": "bar"}}}
        r = CommitmentArbiter.arbitrate(ss, "n1", "kitchen", "any", 3)
        assert r.verdict == VERDICT_PASS

    def test_log_only_always_permits_enforcement_blocks(self):
        """Режимы: LOG_ONLY — True всегда; ENFORCEMENT — True только при PASS."""
        import app.services.action.commitment_arbiter as ca

        ss = {}
        CommitmentRegistry.commit(ss, tick=1, npc_id="n1", action="MOVE", cause="c", target_id="bar")
        CommitmentRegistry.mark_executing(ss, "n1", 1)

        old = ca.ARBITER_ENFORCEMENT
        try:
            ca.ARBITER_ENFORCEMENT = False
            assert ca.CommitmentArbiter.enforce(ss, "n1", "kitchen", "s", 2) is True
            ca.ARBITER_ENFORCEMENT = True
            assert ca.CommitmentArbiter.enforce(ss, "n1", "kitchen", "s", 2) is False
            assert ca.CommitmentArbiter.enforce(ss, "n1", "door", "s", 2) is False  # DUPLICATE тоже
            assert ca.CommitmentArbiter.enforce(ss, "free_npc", "door", "s", 2) is True
        finally:
            ca.ARBITER_ENFORCEMENT = old

# ── S203.3: interrupt_traversal (атомарность, idempotency, GC-подхват) ─────


class TestInterruptTraversal:
    """Закон Мастера: INTERRUPT не успешен, пока traversal и commitment
    не достигли согласованного terminal. Частичное прерывание запрещено."""

    @staticmethod
    def _world(commitment=True):
        ss = {
            "active_traversals": {
                "n1": {"npc_id": "n1", "status": "MOVING", "target_node": "bar",
                       "started_tick": 1, "duration_ticks": 3,
                       "path_waypoints": [[0, 0], [1, 1]],
                       "segment_modes": ["WALK"], "segment_arc_heights": [0.0],
                       "current_waypoint_idx": 0, "from_node": "a"},
            }
        }
        if commitment:
            CommitmentRegistry.commit(ss, tick=1, npc_id="n1", action="MOVE",
                                      cause="c", target_id="bar")
            CommitmentRegistry.mark_executing(ss, "n1", 1)
        return ss

    def test_atomic_success_both_rails(self):
        """True → ОБА рельса terminal; запись живёт до GC (не pop)."""
        from app.domain.traversal_schema import interrupt_traversal

        ss = self._world()
        ok = interrupt_traversal(ss, "n1", "CROSS_LOCATION_TRANSFER", 5)
        assert ok is True
        assert ss["active_traversals"]["n1"]["status"] == "CANCELLED"  # живёт
        hist = ss["commitment_history"]["n1"]
        assert hist[-1]["status"] == "INTERRUPTED"
        assert hist[-1]["interrupt_reason"] == "CROSS_LOCATION_TRANSFER"
        assert "n1" not in ss["active_commitments"]  # ownership released

    def test_already_terminal_noop(self):
        """CANCELLED traversal → False, БЕЗ мутаций (ALREADY_TERMINAL)."""
        from app.domain.traversal_schema import interrupt_traversal

        ss = self._world()
        interrupt_traversal(ss, "n1", "CROSS_LOCATION_TRANSFER", 5)
        hist_len = len(ss["commitment_history"]["n1"])
        ok2 = interrupt_traversal(ss, "n1", "CROSS_LOCATION_TRANSFER", 6)
        assert ok2 is False
        assert len(ss["commitment_history"]["n1"]) == hist_len  # ни одной новой записи

    def test_not_found_distinct_from_already(self):
        """NOT_FOUND (записи нет) — отдельная семантика: ни ошибок, ни мутаций."""
        from app.domain.traversal_schema import interrupt_traversal

        ss = self._world(commitment=False)
        ss["active_traversals"] = {}
        assert interrupt_traversal(ss, "n1", "CROSS_LOCATION_TRANSFER", 5) is False

    def test_rejected_invalid_no_mutation(self):
        """Commitment в не-прерываемом статусе (COMPLETED-осиротевший в active —
        гипотетически) → False; НИ ОДИН слой не мутирован."""
        from app.domain.traversal_schema import interrupt_traversal

        ss = self._world()
        # terminal commitment в active (G4-нарушение симулируем для проверки
        # атомарности): preview обязан отклонить — traversal остаётся MOVING.
        ss["active_commitments"]["n1"]["status"] = "COMPLETED"
        ok = interrupt_traversal(ss, "n1", "CROSS_LOCATION_TRANSFER", 5)
        assert ok is False
        assert ss["active_traversals"]["n1"]["status"] == "MOVING"  # не тронут

    def test_unknown_reason_raises(self):
        """Причина вне реестра → ValueError (расширение = мини-ADR)."""
        from app.domain.traversal_schema import interrupt_traversal

        ss = self._world()
        try:
            interrupt_traversal(ss, "n1", "RANDOM_REASON", 5)
            raise AssertionError("expected ValueError")
        except ValueError:
            pass

    def test_executor_stopped_by_status(self):
        """Гарантия executor stopped: CANCELLED-запись не двигается TES
        (advance пропускает не-MOVING) — физика остановлена статусом."""
        from app.services.spatial.traversal_execution_system import (
            TraversalExecutionSystem,
        )

        ss = self._world()
        from app.domain.traversal_schema import interrupt_traversal

        interrupt_traversal(ss, "n1", "CROSS_LOCATION_TRANSFER", 5)
        TraversalExecutionSystem.advance(ss, 6)
        # запись всё ещё CANCELLED (GC не запускался — advance не удаляет)
        assert ss["active_traversals"]["n1"]["status"] == "CANCELLED"

    def test_g6_cross_scene_continuity(self):
        """G6 (Мастер): старая сцена — terminal до GC; новая — новая собственность.
        Инвариант: не существует old MOVING при новом MOVING (эмуляция границы
        сцен в одном dict — контракт идентичен, т.к. сцены разделяют только
        пространство ключей, не механику)."""
        from app.domain.traversal_schema import interrupt_traversal

        scene_a = self._world()  # MOVING + EXECUTING
        # Transfer: прерываем владение в A
        assert interrupt_traversal(scene_a, "n1", "CROSS_LOCATION_TRANSFER", 5) is True
        # A: terminal до GC
        assert scene_a["active_traversals"]["n1"]["status"] == "CANCELLED"
        assert scene_a["commitment_history"]["n1"][-1]["status"] == "INTERRUPTED"
        # «Материализация в B»: новый traversal+commitment (другие id)
        scene_b = self._world()
        scene_b["active_commitments"]["n1"]["cause"] = "transfer_rebuild"
        assert scene_b["active_traversals"]["n1"]["status"] == "MOVING"
        # old ≠ new (id и история независимы; parent-цепочка восстановления —
        # через parent_commitment_id в реальном контуре)
        assert scene_a["active_traversals"]["n1"]["status"] == "CANCELLED"  # A не ожил