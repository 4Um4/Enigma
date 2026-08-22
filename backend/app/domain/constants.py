# Единый источник истины для базовой интенсивности действий
# TODO v2: context-aware intensity = f(event_type, context, npc_state, personality)
"""
path: backend/app/domain/constants.py
Назначение: Единый источник истины для базовой интенсивности действий (Устав §2, Единый язык)
Зависимости: Нет
Основные сущности: ACTION_INTENSITY

- в будущем можно расширить до более сложной модели, которая учитывает не только тип действия, но и контекст, состояние NPC и его личность. Например, если NPC уже находится в состоянии стресса, даже менее интенсивные действия могут вызвать сильную реакцию. Или если NPC имеет определенные черты личности (например, трусливый или агрессивный), это может влиять на его реакцию на те же действия. Но для начала, базовая модель с фиксированными коэффициентами для каждого типа действия будет хорошим стартом для оценки интенсивности и реакции NPC.
- также можно добавить дополнительные типы действий и соответствующие коэффициенты по мере необходимости, чтобы сделать модель более полной и реалистичной.
"""

ACTION_INTENSITY: dict[str, float] = {
    "player_attacks": 1.0,
    "player_threatens": 0.7,
    "player_threatens_indirect": 0.6,  # ниже чем прямая угроза, выше чем болтовня
    "player_steals": 0.6,
    "player_flees": 0.5,
    "player_insults": 0.65,
    "player_interacts": 0.2,
    "dialogue": 0.2,
    "attack": 1.0,
    "move": 0.1,
    "stealth": 0.1,
}

# S210 (Vertical Slice, слой 2 — Perception Topology): радиус восприятия
# ДЕЙСТВИЙ игрока (мембрана события на шине). SSOT: единая таблица рядом с
# ACTION_INTENSITY — интенсивность и слышимость суть свойства одного действия.
# Семантика симметрична NPC-стороне (ADR-O-362: кража Shadow — whisper):
# кража игрока так же тиха, как кража NPC. Радиусы калибруемы (Calibration
# Laboratory, ADR-O-361 — преcеты).
ACTION_PERCEPTION_RADIUS: dict[str, float] = {
    "player_attacks": 15.0,   # бой слышен (базовый уровень, как и был)
    "attack": 15.0,
    "player_steals": 3.0,     # кража ТИХАЯ: заметить может только тот, кто рядом (LOS решает perception_filter)
    "theft": 3.0,
    "player_threatens": 10.0, # громкая фраза
    "player_insults": 10.0,
    "player_flees": 8.0,      # топот
    "player_interacts": 6.0,
    "dialogue": 6.0,          # разговорная громкость
    "move": 4.0,
    "stealth": 2.0,           # крадущийся игрок почти беззвучен
}

# Потолок для незарегистрированных действий: 999.0 ЗАПРЕЩЁН (ADR-L9.1/ADR-148 —
# пробивает слуховые мембраны). Неизвестное действие слышно как обычное (major).
_DEFAULT_ACTION_RADIUS: float = 15.0


def action_perception_radius(action_type: str) -> float:
    """S210: единая точка резолва радиуса действия. Неизвестное → дефолт."""
    return ACTION_PERCEPTION_RADIUS.get(
        action_type, ACTION_PERCEPTION_RADIUS.get(
            action_type.lower(), _DEFAULT_ACTION_RADIUS
        )
    )