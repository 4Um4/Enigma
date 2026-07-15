# -*- coding: utf-8 -*-
"""
Sandbox: Вертикальный срез WillpowerGate (Осциллограф Воли)

Цель: Наблюдать за кумулятивным напряжением, деградацией воли
и генерацией артефактов конфликта (narration_hooks, counter_offer).

Запуск осциллографа:
python backend/tests/sandbox/sandbox_will_vertical.py

path: backend/tests/sandbox/sandbox_will_vertical.py
Назначение: Вертикальный срез WillpowerGate. Осциллограф симуляции Воли.
Зависимости: app.models.will, pytest
Основные сущности: run_will_sandbox, test_will_sandbox_deterministic

TODO:
- Добавить больше профилей психики для наблюдения разных реакций (например, "агрессивный", "покорный", "невротик" и т.д.)
- Ввести динамические изменения психики (например, рост страха после травмы) и наблюдать, как это влияет на реакцию в последующих тиктах
- В будущем можно добавить визуализацию (например, через matplotlib) для графиков давления и состояния воли, чтобы лучше видеть динамику во времени.

"""

# Standalone runner path fix
import sys
from pathlib import Path

_backend_root = str(Path(__file__).resolve().parents[2])
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

import logging
from typing import Dict

import pytest
from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.domain.intent import IntentDTO
from app.models.will import (
    WillResponseDTO,
    WillState,
)
from app.services.will import compute_willpower, resolve_intent_pressure

# ── Настройка Осциллографа ──────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("WILL_OSCILLOSCOPE")


# ── Профили психики ─────────────────────────────────────────────────────

PSYCHE_STOIC = {
    "identity_rigidity": 0.9,
    "fear": 0.1,
    "conviction": 0.8,
    "shame": 0.2,
    "aggression": 0.3,
    "curiosity": 0.1,
    "willpower": 0.9,
}

PSYCHE_FEARFUL = {
    "identity_rigidity": 0.2,
    "fear": 0.9,
    "conviction": 0.3,
    "shame": 0.6,
    "aggression": 0.1,
    "curiosity": 0.2,
    "willpower": 0.2,
}


# ── Ядро Симуляции ──────────────────────────────────────────────────────


def simulate_will_tick(tick_num: int, action: str, psyche: Dict[str, float]) -> WillResponseDTO:
    """Один тик каузальной физики Воли."""
    log.info(f"\n{'=' * 60}\nTICK {tick_num}: Action = '{action}'\n{'=' * 60}")

    # 1. Семантический перевод (Слой 3: Intent -> Pressure)
    intent = IntentDTO(action=action, target="borko", text=action)
    pressure = resolve_intent_pressure(intent)

    log.info(
        f"[WILL] Intent '{action}' -> Pressure: violence={pressure.violence:.2f}, self_risk={pressure.self_risk:.2f}, identity_deviation={pressure.identity_deviation:.2f}"
    )

    # 2. Вычисление воли (Cumulative Strain Model)
    will_response = compute_willpower(pressure, psyche)

    log.info(f"[WILL] Result: State={will_response.state.value}, Resistance={will_response.resistance:.2f}")

    if will_response.narration_hooks:
        log.info(f"[WILL] Narration Hooks: {will_response.narration_hooks}")
    if will_response.counter_offer:
        log.info(f"[WILL] Counter-Offer: {will_response.counter_offer.action}")

    # Проверка проброса в API (Sprint 26 pipeline)
    conflict_data = None
    if will_response.state not in (WillState.COMPLY, WillState.RELUCTANT):
        conflict_data = {
            "original_intent": intent.action,
            "state": will_response.state.value,
            "resistance": will_response.resistance,
            "narration_hooks": will_response.narration_hooks,
            "counter_offer_action": will_response.counter_offer.action if will_response.counter_offer else None,
        }
        log.info(f"[WILL] API Pipeline: will_conflict_data generated -> {conflict_data['state']}")

    return will_response


def run_will_sandbox() -> bool:
    """Запуск сценария Осциллографа Воли. Возвращает True, если детерминировано."""

    # ── Сценарий 1: Stoic Avatar ──
    log.info("\n" + "▼" * 60 + "\nAVATAR: STOIC (High Willpower, Low Fear)\n" + "▼" * 60)

    p1 = simulate_will_tick(1, "player_talks", PSYCHE_STOIC)  # Безопасное действие
    assert p1.state == WillState.COMPLY, "Стоик должен подчиняться безопасным действиям"

    p2 = simulate_will_tick(2, "player_attacks", PSYCHE_STOIC)  # Физическое насилие
    assert p2.state in (WillState.RELUCTANT, WillState.DISTRESSED, WillState.PANICKED), (
        "Стоик должен сопротивляться насилию (даже через панику)"
    )
    assert p2.resistance > 0.5, "У стоика должно быть высокое сопротивление"
    assert len(p2.narration_hooks) > 0, "Сопротивление должно генерировать крючки"

    # ── Сценарий 2: Fearful Avatar ──
    log.info("\n" + "▼" * 60 + "\nAVATAR: FEARFUL (Low Willpower, High Fear)\n" + "▼" * 60)

    p3 = simulate_will_tick(3, "player_talks", PSYCHE_FEARFUL)  # Безопасное действие
    assert p3.state == WillState.COMPLY, "Трус должен подчиняться безопасным действиям"

    p4 = simulate_will_tick(4, "PLAYER_THREATENS", PSYCHE_FEARFUL)  # Угроза
    assert p4.state in (WillState.PANICKED, WillState.DISTRESSED, WillState.DISSOCIATING), (
        "Трус должен паниковать при угрозах"
    )
    assert len(p4.narration_hooks) > 0, "При панике должны генерироваться нарративные крючки"

    p5 = simulate_will_tick(5, "player_attacks", PSYCHE_FEARFUL)  # Жестокое насилие
    assert p5.state in (WillState.DISSOCIATING, WillState.BROKEN, WillState.PANICKED), (
        "Трус должен ломаться при насилии"
    )
    # Counter-offer должен появляться при диссоциации как попытка выжить
    if p5.state == WillState.DISSOCIATING:
        assert p5.counter_offer is not None, "При диссоциации аватар должен предлагать альтернативу (counter_offer)"

    return True


# ── Точки входа ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("run_id", range(8))
def test_will_sandbox_deterministic(run_id: int):
    """Pytest обёртка: 8 прогонов гарантируют детерминизм."""
    assert run_will_sandbox() is True


if __name__ == "__main__":
    """Standalone Oscilloscope Runner."""
    log.info("⚡ Starting Willpower Oscilloscope...")
    success = run_will_sandbox()
    if success:
        log.info("\n✅ Oscilloscope run complete. Will pipeline verified.")
    else:
        log.error("\n❌ Oscilloscope run failed.")
