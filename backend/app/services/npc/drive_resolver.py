"""
Назначение: Он принимает Правду (L1) и Архетип (L0), и превращает их в Эфемерную Проекцию. Он же решает, что ниже порога восприятия, и гарантирует Закон Сохранения Я (sum = 1.0).

"""

from typing import Dict, List, Tuple
from app.models.npc_state import NPCPersonality
from app.domain.identity_events import TraitDriftEvent

# Порог восприятия. События с весом ниже этого NPC "не чувствует" в проекции.
_PERCEPTION_THRESHOLD: float = 1e-4

class DriveResolver:
    """
    Epistemology Layer: вычисляет эфемерную проекцию личности.
    Инварианты:
    - L3-CP: No Projection Persistence (без кэша, без состояния).
    - Conservation of Identity: сумма драйвов всегда 1.0.
    - Feedback Loop Protection: проекция read-only для текущего тика.
    """
    
    def resolve_drives(
        self,
        archetype: NPCPersonality,
        l1_events_weighted: List[Tuple[TraitDriftEvent, float]]
    ) -> Dict[str, float]:
        """
        Pure function: L0 + L1(Weighted) -> Projection.
        Вызывается каждый тик заново. Результат нигде не сохраняется.
        """
        # 1. Клонируем базовый архетип (L0)
        drives = dict(archetype.drives_base)
        
        # 2. Накладываем деформации (L1) с учётом весов
        for event, weight in l1_events_weighted:
            # Интерпретация: если вес ниже порога, личность не чувствует эту травму сейчас
            if weight < _PERCEPTION_THRESHOLD:
                continue
                
            # ADR-O-208: TraitDriftEvent больше не содержит поля 'trait' или 'delta'.
            # L1 Chronicle хранит сырую статистику (effect_value, source_id).
            # Модуляция drives_base через L1 временно отключена (до интеграции Belief Layer).
            # L3 Projection = L0 Archetype (safe fallback).
            pass
        
        # 3. Закон Сохранения Я (Нормализация mass=1.0)
        for trait in drives:
            drives[trait] = max(0.01, drives[trait])  # Энтропийный пол
            
        total_mass = sum(drives.values())
        if total_mass > 0:
            for trait in drives:
                drives[trait] /= total_mass
                
        # L3-P1: Возвращаем неизменяемую проекцию.
        from app.domain.identity_events import EffectiveDrives
        return EffectiveDrives.from_dict(drives)