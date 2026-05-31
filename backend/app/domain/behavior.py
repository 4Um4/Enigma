# path: backend/app/domain/behavior.py
# Назначение: Контракты наблюдаемого поведения NPC (The Fool Epistemic Boundary).
# Запрет: Содержит только внешние проявления, доступные сенсорам игрока.
# Никаких эмоций, интентов или внутренних мотивов.

"""
TODO:

"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ObservableBehavior:
    """Наблюдаемое поведение NPC в пространстве и времени.
    
    Игрок не знает "почему" NPC так себя ведет.
    Игрок видит паттерн и сам делает вывод.
    """
    entity_id: str
    
    # Локомоция: как он двигается
    locomotion: Literal[
        "retreating",      # Отступает (сокращает дистанцию до выходов/укрытий)
        "flinching",       # Отшатнулся (резкий шаг назад при приближении угрозы)
        "frozen",          # Замер (моторный ступор)
        "approaching",     # Приближается
        "loitering"        # Слоухозит (бессмысленное перемещение)
    ] = "loitering"
    
    # Взгляд: куда направлено внимание
    gaze: Literal[
        "avoidant",        # Отводит взгляд
        "fixed_on_threat", # Неотрывно смотрит на источник угрозы
        "scanning_exits",  # Ищет пути отхода
        "downcast"         # Опустил глаза
    ] = "downcast"
    
    # Пространственное позиционирование: как использует окружение
    spacing: Literal[
        "shielded_by_crowd", # Прячется за чужими спинами
        "isolated",          # Отошел от всех
        "blocking_path",     # Перекрывает путь
        "open"               # Стоит открыто
    ] = "open"
    
    # Срочность: скорость и резкость движений
    urgency: float = 0.0    # 0.0 - вялое, 1.0 - паническая спешка


# Словарь перевода Наблюдения -> Человекочитаемый текст (для PhenomenologyProjection)
# Строго описательный, без телепатии
MANIFESTATION_TEXTS = {
    ("retreating", "shielded_by_crowd"): "Отступает за чужие спины",
    ("retreating", "scanning_exits"): "Ищет путь к отступлению",
    ("flinching", "avoidant"): "Отшатывается и отводит взгляд",
    ("frozen", "avoidant"): "Замер, не глядя на тебя",
    ("frozen", "fixed_on_threat"): "Замер, не сводя глаз с происходящего",
    ("approaching", "open"): "Направляется к тебе",
    ("retreating", "isolated"): "Отошел в сторону один",
}