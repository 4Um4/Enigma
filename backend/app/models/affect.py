# path: backend/app/models/affect.py
# Назначение: Контракты Аффективной Памяти (Affective Imprints). Этап 3 Roadmap.
# Зависимости: dataclasses
# Основные сущности: AffectiveImprint
# Принцип: Avatar = NPC with dual consciousness ownership. Модель универсальна для всех агентов.
"""
TODO: Временный контракт для разработки и тестирования Аффективной Памяти.
В будущем может быть расширен или переработан в зависимости от потребностей ADR-031 и взаимодействия с другими системами (воля, эмоции, идентичность).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class AffectiveImprint:
    """Единица аффективной памяти — остаточное давление опыта.
    
    Не хранит нарратив ("Бандит избил меня у моста").
    Хранит векторы давления и триггеры, чтобы LLM мог озвучить это как травму.
    Интегрируется перед WillpowerGate (Affect Resonance Scan).
    """
    # Источник возмущения (кто нанес травму / оказал давление)
    source_entity_id: str
    
    # Семантические теги события (для резонанса с IntentPressureProfile)
    trigger_tags: tuple[str, ...] # например: ("violence", "public", "betrayal")

    # Сигнатуры давления (осколки пережитого)
    pain_signature: float        # 0.0-1.0, остаточная физическая боль
    fear_signature: float        # 0.0-1.0, остаточный страх
    humiliation_signature: float # 0.0-1.0, остаточный стыд/унижение

    # Социальный сдвиг (как изменилось доверие к источнику)
    trust_shift: float           # дельта доверия (-1.0 ... +1.0)

    # Параметры инерции и затухания
    reinforcement: float         # 0.0-1.0, насколько травма укрепилась при повторном воздействии
    decay_rate: float            # 0.0-1.0, скорость затухания (0 = вечная травма, 1 = мгновенно забывается)

    # Временные метки (в game_time_seconds)
    created_at: int              # Когда произошло событие
    last_triggered_at: int       # Когда травма последний раз резонировала с новым действием


class ResponseBias(Enum):
    """Спектр реакций на травматический резонанс. Травма ≠ страх."""
    FEAR = "fear"                # Бегство, избегание
    AGGRESSION = "aggression"    # Ярость, нападение (конвертация страха в гнев)
    FREEZE = "freeze"            # Оцепенение, ступор
    SUBMISSION = "submission"    # Подчинение, гиперкомплаенс
    DISSOCIATION = "dissociation" # Отчуждение, "это происходит не со мной"


@dataclass(frozen=True)
class ResonanceProfile:
    """Результат сканирования аффективной памяти. Искажение интерпретации, а не бафф.
    
    Создаётся AffectResonanceScanner (Pure Function).
    """
    triggered_imprints: tuple[str, ...] # ID сработавших травм

    # Оси резонанса (как травма откликается текущему контексту)
    fear_resonance: float = 0.0
    humiliation_resonance: float = 0.0
    domination_resonance: float = 0.0
    violence_resonance: float = 0.0
    abandonment_resonance: float = 0.0

    # Модификаторы когнитивного состояния
    certainty_modifier: float = 0.0     # Искажение уверенности в происходящем
    dissociation_risk: float = 0.0      # Риск отключения от реальности

    # Интегральная сила триггера и доминирующий bias личности
    trigger_strength: float = 0.0
    dominant_bias: ResponseBias = ResponseBias.FEAR