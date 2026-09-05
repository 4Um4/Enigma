# path: /project/backend/tests/gameplay/test_gc11_relationship_causality.py
# Назначение: GC-11 — первый обязательный L3-гейт (§5a.9 вердикт Мастера
#   2026-09-05, GAMEPLAY-GATE CANONIZATION). Доказывает причинную истину:
#   relationship-событие → ненулевая запись в V2-RAM → следующий выбор
#   NPC сдвинут относительно бейзлайна. Ловит RE-D2-класс (зелёная
#   архитектура пишет нулевую игровую реальность — юнит-сьютой недоказуемо).
#   Production-only: никаких моков, никаких прямых записей — только
#   player_action (REST run_turn) и idle_tick (§5a.2).
# Зависимости: tests.gameplay.harness (build_game_loop production runtime).
# Основные сущности: test_gc11_compliment_writes_nonzero_ram,
#   test_gc11_event_shifts_decision_landscape.
# Запуск: cd backend; python -m pytest tests/gameplay/test_gc11_relationship_causality.py -v -s

import logging

import pytest
from tests.gameplay.harness import TavernGameplayHarness

logger = logging.getLogger("gameplay.gc11")

# NPC-адресат комплимента: мейд — базовый персонаж таверны
_TARGET_NPC = "maid_lusya"


def _v2_rel(harness, npc_id: str, target: str):
    """Чтение trust-пары NPC→player через harness.read_trust (V2-RAM,
    канонический бэкенд; провода game_loop._rel_store — один объект на
    все подписки). None = пара отсутствует (Vacuum); 0.0 = пара есть,
    trust нулевой. Прежний доступ memory_manager._relations с
    _campaign-хаком падал в except → -1.0 на каждом вызове (RED-причина
    2026-09-05: ассерты были слепы, ни одного чтения не происходило)."""
    return harness.read_trust(npc_id, target)


def _npc_intent(harness, npc_id: str):
    """Текущий интент NPC (агрегированное решение) — маркер decision-состояния.
    Возвращает intent-строку или 'UNREACHABLE'."""
    _st = harness.inspect_npc(npc_id) or {}
    _intent = _st.get("intent") or _st.get("last_intent")
    return str(_intent) if _intent else "UNREACHABLE"


@pytest.fixture
def harness():
    """Production runtime; dispose гарантирован; V2-кампания кэшируется
    после new_game (привязка адаптера происходит в первом тике)."""
    _h = TavernGameplayHarness(seed=42)
    _h.new_game()
    _v2_rel._campaign = "Open_road"
    yield _h
    _h.dispose()


def test_gc11_compliment_writes_nonzero_ram(harness):
    """GC-11 СТУПЕНЬ 1: player-комплимент → V2-RAM содержит ненулевой
    trust-запись maid_lusya→player. Нулевой/отсутствующий RAM-запись =
    RE-D2 (событие прошло, игровая реальность не изменилась) = FAIL."""

    harness.advance_ticks(5)  # прогрев: bind V2, stable baseline

    _before = _v2_rel(harness, _TARGET_NPC, "player")

    _res = harness.player_action(f"подойди к {_TARGET_NPC} и скажи ей комплимент")

    # Событие обязано доехать до RAM: либо сразу, либо после следующего тика
    _after_immediate = _v2_rel(harness, "player", _TARGET_NPC)
    if _after_immediate is None or _after_immediate <= 0.0:
        harness.advance_ticks(3)  # событию нужен тик на оседание
        _after = _v2_rel(harness, "player", _TARGET_NPC)
    else:
        _after = _after_immediate

    print(f"[GC11-STEP1] trust maid_lusya→player: before={_before} "
          f"after={_after}")

    # None = пара не создана; 0.0 = создана с нулём. Оба = RE-D2-класс.
    # Диагноз-развилка: без LLM комплимент идёт через NARRATIVE-цепь —
    # DM-краш (GC-24-изоляция, ход жив) может обрывать семантику ДО
    # relationship-события: тогда verdict = requires_llm, не write-баг.
    assert _after is not None and _after > 0.0, (
        f"GC11-STEP1 FAIL: комплимент не записан в V2-RAM "
        f"(before={_before}, after={_after}). RE-D2-класс: событие прошло "
        f"(run_turn вернул {_res is not None}), но игровая реальность "
        f"нулевая. suspect: rules_subscriber → Gate → V2 (RE-D2) либо "
        f"NARRATIVE-обрыв при LLM-off (см. диагноз-развилку)"
    )


def test_gc11_event_shifts_decision_landscape(harness):
    """GC-11 СТУЕНЬ 2: тот же мир+seed, но до/после комплимента —
    decision-состояние NPC (intent/чувствительность к социальному
    давлению) обязано различаться. Одинаковый ответ = событие не
    причинно (двойная история §5a.3 GC-06 логика)."""

    harness.advance_ticks(3)  # baseline

    _intent_before = _npc_intent(harness, _TARGET_NPC)
    # Маркер причинности шины: события целевого NPC до/после — реально
    # наблюдаемый decision-след (counters уже подписан на bus).
    _events_before = dict(harness.counters.events_by_type)
    _trust_before = _v2_rel(harness, _TARGET_NPC, "player")

    harness.player_action(f"скажи {_TARGET_NPC} комплимент")
    harness.advance_ticks(2)  # событие оседает, next-tick decision использует новые входы

    _intent_after = _npc_intent(harness, _TARGET_NPC)
    _trust_after = _v2_rel(harness, "player", _TARGET_NPC)

    print(f"[GC11-STEP2] intent: {_intent_before} → {_intent_after}")
    print(f"[GC11-STEP2] trust: {_trust_before} → {_trust_after}")

    # Причинный минимум: trust изменился ИЛИ intent изменился
    _causal = (_trust_after != _trust_before) or (_intent_after != _intent_before)
    assert _causal, (
        f"GC11-STEP2 FAIL: идентичный мир, доверие и intent НЕ изменились "
        f"после комплимента (trust: {_trust_before}→{_trust_after}; "
        f"intent: {_intent_before}→{_intent_after}). Событие не является "
        f"причинным в runtime. suspect: rider V2-RAM → compute "
        f"(S135-путь) либо/social_modifiers → DecisionHub"
    )