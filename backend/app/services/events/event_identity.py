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


_KEY_INTENT_ORDINALS = "intent_ordinals"


def next_intent_identity(
    scene_state: Dict[str, Any], owner: str, action: str
) -> Tuple[int, int]:
    """Выделяет (tick, ordinal) для нового намерения (Player или Avatar).

    Единственный писатель scene_state["intent_ordinals"] (Single Writer —
    не DOUBLE TRUTH, прецедент next_event_identity).

    Ключ счётчика — стабильный owner ID (character_id, "player", npc_id),
    НЕ player_name. Action участвует в идентификаторе (intent_id_str),
    но НЕ создаёт отдельную последовательность счётчиков для каждого
    типа действия — ordinal сквозной по всем намерениям владельца
    (вердикт Мастера №1, уточнения 1-2).

    Пропуски ordinal легальны: счётчик монотонный, не плотный.
    Загруженный сейв без контейнера или без конкретного ключа
    самовосстанавливается здесь же — миграция без миграционной системы
    (прецедент next_event_identity, Foundation Freeze).
    """
    ordinals = scene_state.setdefault(_KEY_INTENT_ORDINALS, {})
    ordinal = int(ordinals.get(owner, 0)) + 1
    ordinals[owner] = ordinal
    tick = int(scene_state.get("tick", 0) or 0)
    return tick, ordinal


def intent_id_str(
    tick: int, owner: str, action: str, ordinal: int
) -> str:
    """Детерминированная строка-идентификатор для intent_lifecycle.

    Формат: intent:{tick}:{owner}:{action}:{ordinal}
    Replay-safe: одинаковая последовательность → одинаковые ID.
    Никаких UUID, временных меток, hash() (вердикт Мастера №1, уточнение 3).
    """
    return f"intent:{tick}:{owner}:{action}:{ordinal}"
