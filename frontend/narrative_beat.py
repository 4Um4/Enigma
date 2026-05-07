"""
path: /frontend/narrative_beat.py
Назначение: Сценическое событие Narrative Beat System (по архитектуре Мастера тай).
Заменяет плоский message_log на кинематографичную подачу.
Зависимости: pygame, typing, enum
Основные сущности: DeliveryType, RecognitionLevel, NarrativeBeat

TODO:
- Интеграция с UI: рендеринг пузырей с разными стилями в зависимости от параметров (delivery, recognition, certainty).
- Управление временем жизни и анимацией пузырей (lifetime, certainty).
"""
import pygame
from enum import Enum, auto
from typing import Optional
from dataclasses import dataclass, field

class DeliveryType(Enum):
    """Как реплика подается визуально и аудиально (Пункт 1 Мастера тай)"""
    NORMAL = auto()
    WHISPER = auto()    # Мелкий шрифт, dithering, ближе к центру
    SHOUT = auto()      # Крупный шрифт, shake, ударный звук
    INTERNAL = auto()   # Мысль игрока/NPC, курсив, приглушенный цвет
    PANIC = auto()      # Дрожащий текст, быстрый таймер
    INTERRUPT = auto()  # Обрыв предыдущей реплики, резкий вход

class RecognitionLevel(Enum):
    """Уровень когнитивной идентификации говорящего (Пункт 3 Мастера тай)"""
    UNKNOWN_MALE = auto()      # "Мужчина" (сильный Bayer-шум на имени)
    UNKNOWN_FEMALE = auto()    # "Женщина" (шум)
    STRANGE_FACE = auto()      # "Знакомый мужчина" (легкий шум)
    KNOWN_NAME = auto()        # "Борко" (четкий текст)

class BeatLifetime(Enum):
    """Время жизни пузыря на экране (Пункт 4 Мастера тай)"""
    TRANSIENT = auto()  # Обычная реплика, растворяется со временем
    PINNED = auto()     # Важная информация, остается пока не сменишь
    SLAM = auto()       # Угроза/клятва, "врезается" в экран и держится дольше

@dataclass
class NarrativeBeat:
    """Единица сценического действия (Пункт 2, 5 Мастера тай)"""
    speaker: str
    text: str
    is_player: bool = False
    
    # Нарративные параметры
    delivery: DeliveryType = DeliveryType.NORMAL
    certainty: float = 1.0  # 0.0 - 1.0. Меньше = дрожание/пропуски букв
    recognition: RecognitionLevel = RecognitionLevel.KNOWN_NAME
    lifetime: BeatLifetime = BeatLifetime.TRANSIENT
    
    # Системные поля для UI рендерера
    creation_tick: int = 0
    alpha: float = 255.0
    is_fading: bool = False
    is_active: bool = True  # Участвует ли в текущем кадре