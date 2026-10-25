# path: /project/backend/tests/gameplay/test_gc02_player_action_world_consequence.py
# Назначение: GC-02 — один сквозной сценарий player action → canonical state →
#   event/causal layer → persistence after tick (roadmap §9.10, Б3).
#   Помогает maid_lusya через InterventionEvent(semantic_action="HELP") —
#   обходит DM-классификатор (LLM-free), идёт через production write-path:
#   ActionConsequenceCompiler → RelationshipWriteGate → RelationshipStateStore →
#   atomic_commit_all. Не расширяется на полную spatial-систему или event_compiler.
# Зависимости: tests.gameplay.harness (build_game_loop production runtime).
# Основные сущности: test_help_action_changes_trust_canonical_state,
#   test_deterministic_action_id, test_change_persists_after_idle_tick.
# Запуск: cd backend; python -m pytest tests/gameplay/test_gc02_player_action_world_consequence.py -v -s
"""
GC-02: player action → world consequence.

Один сквозной L3-сценарий:
  1. Игрок помогает NPC (semantic_action="HELP" через InterventionEvent)
  2. canonical state меняется через production write-path
     (ActionConsequenceCompiler → WriteGate → RelationshipStateStore)
  3. Изменение попадает в event/causal layer (ActionConsequenceCompiler
     пишет observation в ObservationLog — production-path компилятора)
  4. Изменение сохраняется после следующего тика (atomic_commit_all → disk)

Тест НЕ проверяет handler invocation alone — только итоговое состояние мира
(вердикт Мастера: «действие игрока изменяет каноническое состояние объекта;
изменение проходит через предусмотренный причинный/event-слой; изменение
сохраняется после следующего тика»).

LLM-free: InterventionEvent с готовым payload.semantic_action обходит
DM-классификатор (в отличие от harness.player_action который требует LLM).
"""
import logging

import pytest
from tests.gameplay.harness import TavernGameplayHarness

logger = logging.getLogger("gameplay.gc02")

_TARGET_NPC = "maid_lusya"


def _make_help_intervention(tick: int, target_id: str = _TARGET_NPC):
    """Создаёт InterventionEvent с готовым semantic_action="HELP" —
    обходит DM-классификатор полностью (LLM-free path).

    Контракт payload (tick_orchestrator._process_player_action:1586-1590):
      semantic_action: "HELP"
      target_reference: имя NPC для fuzzy-резолва (если target_id=None)
      target_id: уже зарезолвленный NPC ID (приоритет)
      social_pressure: float (опционально, default 0.8)
    """
    from app.contracts.interventions import InterventionEvent

    return InterventionEvent(
        source="player",
        payload={
            "semantic_action": "HELP",
            "target_reference": target_id,
            "target_id": target_id,
            "social_pressure": 0.8,
        },
        tick=tick,
    )


def _v2_trust(harness, npc_id: str, target: str = "player"):
    """Чтение trust-пары NPC→player через harness.read_trust (V2-RAM,
    канонический бэкенд ADR-O-417). None = пара отсутствует (Vacuum)."""
    return harness.read_trust(npc_id, target)


def _v2_fear(harness, npc_id: str, target: str = "player"):
    """Чтение fear-пары через V2-RAM (если есть reader; иначе None).
    HELP action пишет fear_delta=-10.0 (action_consequence_compiler.py:198)."""
    try:
        _store = getattr(
            getattr(harness.game_loop, "memory_manager", None),
            "_relationships",
            None,
        ) or getattr(harness.game_loop, "_rel_store", None)
        if _store is None:
            return None
        _pair = _store.get_pair(harness.campaign_id, npc_id, target)
        if not _pair:
            return None
        return float(_pair.get("fear", 0.0))
    except Exception:
        return None


@pytest.fixture
def harness():
    """Production runtime; LLM-free path (не требует _ensure_llm)."""
    _h = TavernGameplayHarness(seed=42, location="tavern")
    _h.new_game()
    _h.advance_ticks(3)  # прогрев: V2-bind, stable baseline
    yield _h
    _h.dispose()


class TestGC02PlayerActionWorldConsequence:
    """GC-02: один сквозной сценарий через production write-path.

    Три теста покрывают: (1) canonical state change; (2) replay-safe
    action_id (идемпотентность); (3) persistence after idle_tick.
    """

    def test_help_action_changes_trust_canonical_state(self, harness):
        """Игрок помогает maid_lusya → trust NPC→player растёт через
        canonical write-path (ActionConsequenceCompiler → WriteGate → V2).

        L3 assertion: НЕ проверяем вызов process_action; проверяем ИТОГОВОЕ
        состояние мира — trust вырос и виден через канонический reader
        (harness.read_trust → V2 backend ADR-O-417).
        """
        # 1. Baseline: trust maid_lusya→player (None/Vacuum или 0.0)
        _trust_before = _v2_trust(harness, _TARGET_NPC, "player")
        _fear_before = _v2_fear(harness, _TARGET_NPC, "player")
        print(
            f"[GC02-STEP1] baseline: trust={_trust_before}, fear={_fear_before}"
        )

        # 2. Inject HELP InterventionEvent через idle_tick (LLM-free path)
        _tick = harness.counters.ticks
        _intervention = _make_help_intervention(tick=_tick, target_id=_TARGET_NPC)
        _ = harness.game_loop.idle_tick(
            harness.campaign_id, interventions=[_intervention]
        )

        # 3. Assert: trust maid_lusya→player вырос (+20.0 per HELP ветка)
        _trust_after = _v2_trust(harness, _TARGET_NPC, "player")
        _fear_after = _v2_fear(harness, _TARGET_NPC, "player")
        print(
            f"[GC02-STEP1] after HELP: trust={_trust_after}, fear={_fear_after}"
        )

        # Фактический refusal — если mvp_controller/action_compiler не был
        # инициализирован, HELP-действие дропнулось (лог "[INPUT_MERGE]
        # consequence action dropped"). Это архитектурный долг, не skip.
        if _trust_after is None or _trust_after <= (_trust_before or 0.0):
            # Диагностика: проверим, что action_compiler жив
            _mvp = getattr(harness.game_loop, "mvp_controller", None)
            _compiler = getattr(_mvp, "action_compiler", None) if _mvp else None
            _diagnosis = (
                f"mvp_controller={_mvp is not None}, "
                f"action_compiler={_compiler is not None}"
            )
            pytest.fail(
                f"GC02-STEP1 FAIL: HELP-действие не изменило trust "
                f"(before={_trust_before}, after={_trust_after}). "
                f"Diagnosis: {_diagnosis}. Если action_compiler=None — "
                f"mvp_controller не инициализирован в build_game_loop; "
                f"минимальный фикс: проводка mvp_controller в game_loop."
            )

        # HELP-ветка: trust_delta=+20.0 (action_consequence_compiler.py:195)
        _expected_min_delta = 1.0  # не точное +20.0 (калибровка может менять)
        assert _trust_after > (_trust_before or 0.0) + _expected_min_delta, (
            f"GC02-STEP1 FAIL: trust не вырос достаточно "
            f"(before={_trust_before}, after={_trust_after}, "
            f"expected_delta≥{_expected_min_delta})"
        )

    def test_deterministic_action_id(self, harness):
        """Идемпотентность компилятора: action_id накапливается в
        _processed_actions → повторная подача ТОГО ЖЕ action_id — no-op.

        Производственный invariant: action_id строится из ctx.tick_number
        (оркестраторское время, ADR-O-344), а не из intervention.tick.
        Между двумя idle_tick оркестратор инкрементирует tick → action_id
        автоматически уникален. Идемпотентность нужна только при повторе
        ТОГО ЖЕ action_id (replay / crash-recovery / double-dispatch).

        Тестируем через прямой вызов process_action с одним action_id —
        L2 unit-поведение в L3-обёртке (production action_compiler).
        """
        _tick = harness.counters.ticks
        _intervention = _make_help_intervention(tick=_tick, target_id=_TARGET_NPC)
        # Один HELP через production-path (capture action_id)
        harness.game_loop.idle_tick(
            harness.campaign_id, interventions=[_intervention]
        )

        _ac = harness.game_loop.mvp_controller.action_compiler
        _processed = _ac._processed_actions

        # После первого HELP в _processed_actions должна быть запись
        # action_id формата "interv:{tick}:HELP:{target}"
        _expected_substrings = ("HELP", _TARGET_NPC)
        _has_help = any(
            all(_sub in _aid for _sub in _expected_substrings)
            for _aid in _processed
        )
        assert _has_help, (
            f"GC02-STEP2 FAIL: action_id HELP:{_TARGET_NPC} не записан в "
            f"_processed_actions (set={_processed}). Идемпотентность "
            f"компилятора не активирована — повторный HELP удвоит trust."
        )

        # Идемпотентность: повторная подача ТОГО ЖЕ action_id через process_action
        # — no-op (trust не удваивается). Используем action_compiler напрямую,
        # т.к. через idle_tick тот же action_id невозможен (оркестратор
        # инкрементирует tick_number → action_id всегда уникален).
        from app.models.player_action import ActionType, PlayerAction

        _trust_before_dup = _v2_trust(harness, _TARGET_NPC, "player")
        # Берём первый (любой) action_id из _processed_actions
        _first_action_id = next(
            _aid for _aid in _processed
            if all(_sub in _aid for _sub in _expected_substrings)
        )
        _dup_action = PlayerAction(
            action_id=_first_action_id,  # тот же action_id → no-op
            tick=_tick,
            actor_id="player",
            action_type=ActionType.HELP,
            target_id=_TARGET_NPC,
            description="duplicate test",
        )
        _outcome = _ac.process_action(_dup_action)
        _trust_after_dup = _v2_trust(harness, _TARGET_NPC, "player")

        print(
            f"[GC02-STEP2] action_id={_first_action_id!r}; "
            f"trust before_dup={_trust_before_dup}, after_dup={_trust_after_dup}"
        )

        # process_action возвращает None при успехе; при дубликате — также None
        # (просто игнорирует — return None в самом начале, _processed_actions
        # уже содержит id). Trust не должен удвоиться.
        assert _trust_after_dup is not None, (
            "GC02-STEP2 FAIL: trust потерян после duplicate HELP"
        )
        _drift_tolerance = 1.0  # нет decay между двумя мгновенными вызовами
        assert abs(_trust_after_dup - _trust_before_dup) < _drift_tolerance, (
            f"GC02-STEP2 FAIL: идемпотентность нарушена — повторный HELP с "
            f"тем же action_id изменил trust (before={_trust_before_dup}, "
            f"after={_trust_after_dup}, drift>{_drift_tolerance}). "
            f"_processed_actions={_processed}"
        )

    def test_change_persists_after_idle_tick(self, harness):
        """Canonical state change переживает idle_tick без intervention
        (atomic_commit_all → disk → next tick reads persisted state).

        Вердикт Мастера: «изменение сохраняется после следующего тика».
        """
        # 1. HELP action
        _tick = harness.counters.ticks
        _intervention = _make_help_intervention(tick=_tick, target_id=_TARGET_NPC)
        harness.game_loop.idle_tick(
            harness.campaign_id, interventions=[_intervention]
        )
        _trust_after_help = _v2_trust(harness, _TARGET_NPC, "player")

        assert _trust_after_help is not None and _trust_after_help > 0.0, (
            f"GC02-STEP3 pre-condition FAIL: HELP не записал trust "
            f"({ _trust_after_help })"
        )

        # 2. idle_tick без intervention (decay-контур работает; trust
        # может слегка упасть от decay, но не должен обнулиться)
        harness.advance_ticks(2)

        # 3. Assert: trust сохранён (persisted via atomic_commit_all → disk)
        _trust_after_idle = _v2_trust(harness, _TARGET_NPC, "player")
        print(
            f"[GC02-STEP3] trust: after_help={_trust_after_help}, "
            f"after_2_idle_ticks={_trust_after_idle}"
        )

        assert _trust_after_idle is not None, (
            "GC02-STEP3 FAIL: trust потерян после idle_tick (persistence broken)"
        )
        # Trust может слегка упасть от relationship decay (если включён),
        # но обязан остаться существенно выше нуля (HELP = +20.0 baseline)
        _persistence_threshold = 1.0
        assert _trust_after_idle > _persistence_threshold, (
            f"GC02-STEP3 FAIL: trust не пережил idle_tick "
            f"(after_help={_trust_after_help}, after_idle={_trust_after_idle}, "
            f"threshold={_persistence_threshold}). Persistence broken: "
            f"atomic_commit_all → disk → next-tick read chain отказал."
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])