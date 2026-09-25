"""
Назначение: Единственный писатель scene_state["event_ordinals"] — порядковый
    компонент identity-контракта EventDTO (тип, источник, тик, ordinal).
Зависимости: typing (domain-нейтрален: работает с dict scene_state)
Основные сущности: next_event_identity
"""

from typing import Any, Dict, Tuple

_KEY_ORDINALS = "event_ordinals"


def next_event_identity(
    scene_state: Dict[str, Any], event_type: str, source: str
) -> Tuple[int, int]:
    """Выделяет (event_tick, ordinal) для нового события.

    Единственная точка инкремента счётчиков identity (Single Writer —
    не DOUBLE TRUTH). Пропуски ordinal легальны: счётчик монотонный,
    не плотный (прецедент commitment_ordinals, ADR-O-363 закон №4).
    Загруженный сейв без контейнера или без конкретного ключа
    самовосстанавливается здесь же — миграция без миграционной системы.
    """
    ordinals = scene_state.setdefault(_KEY_ORDINALS, {})
    key = f"{event_type}:{source}"
    ordinal = int(ordinals.get(key, 0)) + 1
    ordinals[key] = ordinal
    tick = int(scene_state.get("tick", 0) or 0)
    return tick, ordinal
