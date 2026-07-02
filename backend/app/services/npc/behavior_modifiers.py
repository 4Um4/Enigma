"""
path: backend/app/services/npc/behavior_modifiers.py
Назначение: Вычисление модификаторов поведения из внутренних состояний NPC.
             Предшественник будущего HomeostasisEngine. Когда появятся
             hunger, thirst, boredom, stress, confidence — эта функция
             станет HomeostasisEngine.
Зависимости: Нет (чистая функция, только math)
Основные сущности: BehaviorModifiers
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BehaviorModifiers:
    """Готовые коэффициенты для DecisionHub.
    
    DecisionHub не знает почему TALK стал привлекательнее.
    Он видит только эти числа.
    """
    social_outgoing: float = 0.0   # TALK, HELP, TRADE, FLIRT, ASK, INVITE
    social_incoming: float = 0.0   # ANSWER, REFUSE, WARN, ACCEPT, REJECT


def compute_behavior_modifiers(
    social_battery: float,
    gregariousness: float,
) -> BehaviorModifiers:
    """Чистая функция: battery + character → модификаторы.
    
    social_battery: 0=истощён, 100=перегружен, 50=середина
    gregariousness: 0=шизоид, 1=болтун
    
    Логика:
    - comfort = зона комфорта (зависит от характера)
    - Если battery ниже comfort → хочется инициировать контакт
    - Если battery выше comfort → хочется реагировать, но не инициировать
    - Внутри зоны → модификаторы = 0
    """
    # Зона комфорта: интроверт комфортён при 30, экстраверт при 70
    comfort = 30.0 + gregariousness * 40.0
    tolerance = 15.0  # ширина зоны комфорта

    # Outgoing: battery низкий → хочет инициировать
    _outgoing_dev = comfort - social_battery
    if _outgoing_dev > tolerance:
        outgoing = min(0.5, (_outgoing_dev - tolerance) / 60.0)
    else:
        outgoing = 0.0

    # Incoming: battery высокий → готов реагировать
    _incoming_dev = social_battery - comfort
    if _incoming_dev > tolerance:
        incoming = min(0.5, (_incoming_dev - tolerance) / 60.0)
    else:
        incoming = 0.0

    return BehaviorModifiers(social_outgoing=outgoing, social_incoming=incoming)