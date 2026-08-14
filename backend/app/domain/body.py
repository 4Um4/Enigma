"""
path: /project/backend/app/domain/body.py
Назначение: Доменные модели топологии тела и предметов (D&D 5e Realism).
Зависимости: typing, enum
Основные сущности: Item, BodySlot, BodyTopology, EncumbranceLevel
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from enum import Enum

class EncumbranceLevel(Enum):
    """Уровни перегрузки (D&D 5e Variant Encumbrance)."""
    NONE = 0      # Норма
    LIGHT = 1     # encumbered (штраф к скорости)
    MEDIUM = 2    # heavily encumbered (сильный штраф, помеха на атаки/спасброски)
    HEAVY = 3     # overburdened (не может двигаться)

class ItemProperty(str, Enum):
    """Свойства предметов (аналог D&D 5e weapon properties)."""
    FINESSE = "finesse"       # Ловкость или Сила
    TWO_HANDED = "two_handed" # Требует две руки
    HEAVY = "heavy"           # Мелким существам помеха
    LIGHT = "light"           # Легкое, можно брать во вторую руку
    THROWN = "thrown"         # Метательное
    REACH = "reach"           # Увеличенная дистанция
    VERSATILE = "versatile"   # Можно держать одной или двумя руками

@dataclass(frozen=True)
class Item:
    """Физический предмет в мире."""
    item_id: str
    name: str
    weight: float = 0.0           # Вес в фунтах (lbs)
    bulk: int = 1                 # Габаритность (1-10). 1=кольцо, 5=меч, 10=копье
    value: int = 0                # Стоимость в меди
    item_type: str = "misc"       # weapon, armor, potion, misc
    properties: Tuple[ItemProperty, ...] = ()
    requires_attunement: bool = False

@dataclass(frozen=True)
class BodySlot:
    """Физический узел на теле."""
    slot_id: str
    slot_type: str # hand, belt, pocket, backpack, worn, hidden
    body_part: str
    accessibility: float = 1.0
    visibility: float = 1.0
    requires_inspection: bool = False
    capacity: int = 1             # Кол-во предметов
    max_bulk: int = 10            # Максимальная габаритность одного предмета
    item_type_restriction: Optional[str] = None
    is_locked: bool = False
    lock_difficulty: Optional[int] = None
    concealment: float = 0.0      # Насколько скрывает содержимое (плащ)
    don_time_ticks: int = 0       # Сколько тиков занимает надевание (броня = 10-100)
    doff_time_ticks: int = 0      # Сколько тиков занимает снимание

class CouplingMode(str, Enum):
    """Диагностическая метка режима связанности тела (для UI и логов)."""
    FULL_WAKE = "FULL_WAKE"
    DROWSY = "DROWSY"
    SLEEP = "SLEEP"
    DEEP_SLEEP = "DEEP_SLEEP"
    REM = "REM"


@dataclass(frozen=True)
class CouplingProfile:
    """
    Непрерывный профиль связанности тела.
    Вычисляется из BodyState (sleep_pressure, arousal) каждый тик.
    Заменяет хардкод-флаги вроде is_sleeping.
    """
    external_vision_mult: float = 1.0     # 0.0 (слеп) ... 1.0 (полное зрение)
    external_hearing_mult: float = 1.0   # 0.0 (глух) ... 1.0 (идеальный слух)
    motor_output_mult: float = 1.0       # 0.0 (паралич сна) ... 1.0 (полный контроль)
    memory_activation_mult: float = 0.5  # 0.0 (амнезия) ... 1.0 (гипервоспоминания)
    imagination_mult: float = 0.1        # 0.0 (нет снов) ... 1.0 (яркие галлюцинации)
    coupling_mode: CouplingMode = CouplingMode.FULL_WAKE


@dataclass(frozen=True)
class DreamSignal:
    """
    Субъективный сигнал восприятия во сне (Phase E).
    Рождается из внешних стимулов (шум, удар), искажённых через CouplingProfile.
    Epistemic Pipeline обрабатывает его как субъективный опыт (provenance=DREAM).
    """
    target_id: str         # NPC, который видит сон
    tick: int              # Тик симуляции
    raw_stimulus: str      # "noise", "threat", "pain"
    distorted_perception: str  # "thunder", "monster", "falling"
    salience: float = 0.5  # Сила сигнала (0.0 - 1.0)


@dataclass
class BodyTopology:
    """Физическая модель тела для хранения предметов."""
    avatar_id: str
    strength_score: int = 10      # Базовая Сила для расчета перегрузки
    
    hands: Dict[str, BodySlot] = field(default_factory=dict)
    belt: List[BodySlot] = field(default_factory=list)
    pockets: List[BodySlot] = field(default_factory=list)
    backpack: List[BodySlot] = field(default_factory=list)
    worn: Dict[str, BodySlot] = field(default_factory=dict)
    hidden: List[BodySlot] = field(default_factory=list)
    
    # Состояние слотов: slot_id -> Tuple[Item, ...]
    contents: Dict[str, Tuple[Item, ...]] = field(default_factory=dict)

    def all_slots(self) -> List[BodySlot]:
        slots = list(self.hands.values())
        slots.extend(self.belt)
        slots.extend(self.pockets)
        slots.extend(self.backpack)
        slots.extend(self.worn.values())
        slots.extend(self.hidden)
        return slots

    @property
    def hands_occupied(self) -> int:
        return sum(1 for s in self.hands.values() if self.contents.get(s.slot_id))

    @property
    def total_weight(self) -> float:
        return sum(
            item.weight for slot in self.all_slots() 
            for item in self.contents.get(slot.slot_id, ())
        )

    @property
    def total_bulk(self) -> int:
        return sum(
            item.bulk for slot in self.all_slots() 
            for item in self.contents.get(slot.slot_id, ())
        )

    @property
    def visible_items(self) -> List[Item]:
        """Что видно окружающим — в руках, на поясе, надето."""
        items = []
        for slot in list(self.hands.values()) + self.belt + list(self.worn.values()):
            items.extend(self.contents.get(slot.slot_id, ()))
        return items

    @property
    def accessible_in_combat(self) -> List[Item]:
        """Что можно достать за 1 ход — руки + пояс."""
        items = []
        for slot in list(self.hands.values()) + self.belt:
            items.extend(self.contents.get(slot.slot_id, ()))
        return items

    @property
    def carry_capacity(self) -> float:
        """Максимальный вес (STR * 15)."""
        return self.strength_score * 15.0

    @property
    def encumbrance_level(self) -> EncumbranceLevel:
        """Текущий уровень перегрузки."""
        w = self.total_weight
        str_light = self.strength_score * 5.0
        str_med = self.strength_score * 10.0
        str_max = self.strength_score * 15.0
        
        if w > str_max:
            return EncumbranceLevel.HEAVY
        elif w > str_med:
            return EncumbranceLevel.MEDIUM
        elif w > str_light:
            return EncumbranceLevel.LIGHT
        return EncumbranceLevel.NONE