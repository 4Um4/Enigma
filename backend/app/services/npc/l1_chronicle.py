"""
path: backend/app/services/npc/l1_chronicle.py
Назначение: Хроника деформаций идентичности (L1). Интерпретатор причинности во времени.
Зависимости: backend/app/domain/identity_events.py
Основные сущности: L1Chronicle
"""

import math
from typing import List, Dict, Tuple
from app.domain.identity_events import TraitDriftEvent

_TAU_DECAY: float = 50.0

class L1Chronicle:
    """
    Append-only causal trace of identity deformation.
    Truth Layer (Ontology): хранит всё, не интерпретирует ничего.
    """
    def __init__(self):
        # L1-T3 Fix: Per-NPC partitioning. Никакого global event soup.
        self._events: Dict[str, List[TraitDriftEvent]] = {}

    def append(self, event: TraitDriftEvent) -> None:
        """Единственная точка записи. Без проверки времени (L1-T2 Fix)."""
        if event.npc_id not in self._events:
            self._events[event.npc_id] = []
        self._events[event.npc_id].append(event)

    def commit_tick_buffer(self, buffer: List[TraitDriftEvent], current_tick: int) -> None:
        """Атомарная фиксация буфера от Оркестратора. Валидация времени — задача Оркестратора."""
        for event in buffer:
            self.append(event)

    def query_raw(self, npc_id: str, t_from: int = 0) -> List[TraitDriftEvent]:
        """Чтение сырой правды без фильтрации весов (Fix 1)."""
        if npc_id not in self._events:
            return []
        return [e for e in self._events[npc_id] if e.tick >= t_from]

    def query_weighted(self, npc_id: str, current_tick: int, t_from: int = 0) -> List[Tuple[TraitDriftEvent, float]]:
        """
        Чтение правды с весами для проекции. 
        Возвращает ВСЕ события (порог убран), Резолвер решит, что важно.
        """
        if npc_id not in self._events:
            return []
        
        result = []
        for e in self._events[npc_id]:
            if e.tick < t_from:
                continue
            
            time_delta = current_tick - e.tick
            weight = math.exp(-time_delta / _TAU_DECAY) if time_delta > 0 else 1.0
            result.append((e, weight))
            
        return result