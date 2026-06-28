"""
path: backend/app/services/npc/pattern_detector.py
Назначение: Статистический слой (L1.5). Преобразует поток L1 событий в EvidenceOfPersistence.
Зависимости: backend/app/domain/identity_events.py
Основные сущности: PatternDetector, EvidenceOfPersistence
"""

"""
path: backend/app/services/npc/pattern_detector.py
Назначение: Статистический слой (L1.5). Преобразует поток L1 событий в EvidenceOfPersistence.
Зависимости: backend/app/domain/identity_events.py
Основные сущности: PatternDetector, EvidenceOfPersistence
"""

import statistics
import math
from typing import List, Optional, Iterable

from app.domain.identity_events import TraitDriftEvent, EvidenceOfPersistence

# ADR-O-305A: Абсолютный порог минимума событий. 
# Не зависит от размера окна, только от абсолютного количества наблюдений.
# S-93 FIX: Понижен до 3 для обеспечения быстрой кристаллизации убеждений в боевых условиях.
MIN_EVENTS_FOR_PERSISTENCE: int = 3

# Запрещённые source_id (защита от скалярного страха без привязки к источнику)
_INVALID_SOURCES = {"unknown", "", None}

class PatternDetector:
    """
    L1.5: Чистая статистика. Группирует L1Chronicle по source_id и 
    генерирует EvidenceOfPersistence при превышении порога шума.
    
    ADR-O-306: Не имеет права читать эмоции, драйвы или убеждения.
    ADR-O-305A: event_type является provenance only и физически отсекается на входе.
    """

    def __init__(self, chronicle: Optional[object] = None):
        self._chronicle = chronicle

    def query_evidence(self, npc_id: str, source_id: str = "") -> List[EvidenceOfPersistence]:
        """S-93: Возвращает evidence для NPC из L1Chronicle.
        Читает L1, передаёт в detect().
        """
        if not self._chronicle or not hasattr(self._chronicle, 'query_raw'):
            return []
            
        events = self._chronicle.query_raw(npc_id)
        if source_id:
            events = [e for e in events if e.source_id == source_id]
            
        return self.detect(events)

    def detect(self, events: Iterable[TraitDriftEvent], chronicle: Optional[object] = None) -> List[EvidenceOfPersistence]:
        """
        Анализирует поток событий и возвращает доказательства устойчивости.
        
        Args:
            events: Итерируемый поток TraitDriftEvent (L1).
            chronicle: Опциональная ссылка на L1Chronicle (для тестов архитектурной чистоты).
            
        Returns:
            Список EvidenceOfPersistence. Пустой, если событий меньше MIN_EVENTS_FOR_PERSISTENCE.
            
        Raises:
            ValueError: Если в потоке есть события с source_id="unknown" (скалярный страх).
        """
        grouped_events: dict[str, List[TraitDriftEvent]] = {}
        
        for event in events:
            # ADR-O-305: Защита от скалярного страха
            if event.source_id in _INVALID_SOURCES:
                raise ValueError(f"Нарушение ADR-O-305: Событие с невалидным source_id='{event.source_id}'")
            
            # ADR-O-305A: Hard Guard. event_type - это provenance. 
            # Мы намеренно игнорируем это поле, чтобы предотвратить будущий backdoor.
            # Никаких условных ветвлений на основе event_type.
            
            if event.source_id not in grouped_events:
                grouped_events[event.source_id] = []
            grouped_events[event.source_id].append(event)
            
        evidence_list: List[EvidenceOfPersistence] = []
        
        for source_id, source_events in grouped_events.items():
            # ADR-O-305A: Фильтрация шума. Меньше MIN_EVENTS = не доказано.
            if len(source_events) < MIN_EVENTS_FOR_PERSISTENCE:
                continue
                
            # Математика L1.5 (без event_type)
            # 1. cumulative_effect с учётом observation_weight
            cumulative_effect = sum(
                e.effect_value * e.observation_weight for e in source_events
            )
            
            # 2. behavior_variance (комбинированная метрика: дисперсия + временная осцилляция)
            effects = [e.effect_value for e in source_events]
            statistical_variance = statistics.variance(effects) if len(effects) > 1 else 0.0
            
            # Временная осцилляция: подсчёт смен знака (sign-flips)
            sign_flips = 0
            if len(effects) > 1:
                for i in range(1, len(effects)):
                    prev_sign = math.copysign(1, effects[i-1])
                    curr_sign = math.copysign(1, effects[i])
                    if prev_sign != curr_sign:
                        sign_flips += 1
            
            # Нормализация осцилляций к доле (0.0 - 1.0)
            temporal_instability = sign_flips / (len(effects) - 1) if len(effects) > 1 else 0.0
            
            # Комбинированная variance: произведение стат. разброса и временной нестабильности.
            # Если поток стабилен (temporal_instability = 0), variance = 0.
            # Если разброса нет (variance = 0), variance = 0.
            behavior_variance = statistical_variance * temporal_instability
                
            evidence_list.append(
                EvidenceOfPersistence(
                    source_id=source_id,
                    cumulative_effect=cumulative_effect,
                    behavior_variance=behavior_variance
                )
            )
            
        return evidence_list