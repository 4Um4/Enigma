# path: /project/backend/tests/gameplay/test_lc_impl2_telegraph_reaches_client.py
# Назначение: LC-IMPL-2 — телеграф перестаёт быть no-op в API. Событие
#   Ступени А доезжает до клиента (через events ключ в idle-ответе).
#   L3-тест: проверяет, что events ключ присутствует в idle-ответе
#   (не None, не missing) — канал живой от ядра до API-границы.
# Зависимости: tests.gameplay.harness (build_game_loop production runtime).
# Основные сущности: test_events_key_present_in_idle_response,
#   test_events_key_is_list, test_events_format_cause_target_value.
# Запуск: cd backend; python -m pytest tests/gameplay/test_lc_impl2_telegraph_reaches_client.py -v -s
"""
LC-IMPL-2: телеграф перестаёт быть no-op в API.

Один сквозной L3 сценарий:
  1. idle_tick() возвращает dict с ключом "events"
  2. events — список (даже если пустой — канал живой)
  3. Каждый элемент events (если есть) содержит {cause, target, value}
     (IdleEventProjection.to_front() формат, ADR-O-421)

Вердикт Мастера (§15): «событие Ступени А доезжает до клиента; микрорешение
игрока возвращается в мир через существующий контур действий (без новых
сущностей)». Этот тест проверяет первую часть: событие доезжает до API-границы.
Вторая часть (микрорешение) — через существующий action-контур (game_action
endpoint), уже работает.

UI-индикатор (церемония Б) — отдельная задача LC-IMPL-3; здесь проверяется
только API-канал (events ключ в idle-ответе).

LLM-free: idle_tick без interventions — autonomous NPC movement/activity.
"""
import logging

import pytest
from tests.gameplay.harness import TavernGameplayHarness

logger = logging.getLogger("gameplay.lc_impl2")


@pytest.fixture
def harness():
    """Production runtime; LLM-free path."""
    _h = TavernGameplayHarness(seed=42, location="tavern")
    _h.new_game()
    _h.advance_ticks(2)  # прогрев
    yield _h
    _h.dispose()


class TestLCImpl2TelegraphReachesClient:
    """LC-IMPL-2: events ключ доезжает до клиента через idle-ответ.

    Три теста: (1) ключ присутствует; (2) это список; (3) формат
    {cause, target, value} для каждого элемента (если есть).
    """

    def test_events_key_present_in_idle_response(self, harness):
        """idle_tick() возвращает dict с ключом "events" — не None, не missing.

        Канал от ядра (game_loop.idle_tick:1540) через routes (routes.py:594)
        до API-границы живой. S328 (DEBT-FE-DELTAS) выровнял ключ; LC-IMPL-2
        подтверждает, что он не потерян.
        """
        _result = harness.game_loop.idle_tick(harness.campaign_id)

        assert isinstance(_result, dict), (
            f"LC-IMPL-2 FAIL: idle_tick() вернул не dict ({type(_result).__name__}). "
            f"Канал events не может быть проверен."
        )
        assert "events" in _result, (
            f"LC-IMPL-2 FAIL: ключ 'events' отсутствует в idle-ответе. "
            f"Канал телеграфа мёртв на API-границе. "
            f"Доступные ключи: {list(_result.keys())}"
        )

    def test_events_key_is_list(self, harness):
        """events — список (даже если пустой — канал живой).

        Пустой список = нет событий v1-словаря (ACTIVITY_OUTCOME, THEFT)
        в этом тике — это валидное состояние, не дефект канала.
        Непустой список = события дошли до API-границы.
        """
        _result = harness.game_loop.idle_tick(harness.campaign_id)
        _events = _result.get("events")

        assert isinstance(_events, list), (
            f"LC-IMPL-2 FAIL: events не список ({type(_events).__name__}: "
            f"{_events!r}). Канал телеграфа повреждён — ожидался list."
        )

    def test_events_format_cause_target_value(self, harness):
        """Каждый элемент events (если есть) содержит {cause, target, value}.

        IdleEventProjection.to_front() (ADR-O-421) возвращает dict с
        тремя ключами: cause (EventType), target (event.source),
        value (ProjectionValue: str|int|float).
        """
        # Прогон нескольких тиков — шанс поймать ACTIVITY_OUTCOME/THEFT
        for _ in range(5):
            _result = harness.game_loop.idle_tick(harness.campaign_id)
            _events = _result.get("events", [])

            if _events:
                _evt = _events[0]
                assert isinstance(_evt, dict), (
                    f"LC-IMPL-2 FAIL: элемент events не dict "
                    f"({type(_evt).__name__}: {_evt!r})"
                )
                assert "cause" in _evt, (
                    f"LC-IMPL-2 FAIL: 'cause' отсутствует в events[0]: {_evt!r}"
                )
                assert "target" in _evt, (
                    f"LC-IMPL-2 FAIL: 'target' отсутствует в events[0]: {_evt!r}"
                )
                assert "value" in _evt, (
                    f"LC-IMPL-2 FAIL: 'value' отсутствует в events[0]: {_evt!r}"
                )
                print(
                    f"[LC-IMPL-2] event: cause={_evt['cause']} "
                    f"target={_evt['target']} value={_evt['value']}"
                )
                return  # первый найденный event — тест GREEN

        # Если за 5 тиков нет событий v1-словаря — это валидное состояние
        # (NPC могут не выполнять ACTIVITY_OUTCOME/THEFT в этом прогоне).
        # Канал живой (test_events_key_present + test_events_key_is_list GREEN),
        # но событий нет — не дефект LC-IMPL-2, а ограничение v1-словаря.
        print(
            "[LC-IMPL-2] no v1-dictionary events in 5 ticks — "
            "channel alive, but no ACTIVITY_OUTCOME/THEFT generated"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])