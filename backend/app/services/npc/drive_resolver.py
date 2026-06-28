"""
Назначение: Он принимает Правду (L1) и Архетип (L0), и превращает их в Эфемерную Проекцию. Он же решает, что ниже порога восприятия, и гарантирует Закон Сохранения Я (sum = 1.0).

"""

from typing import Dict, List, Optional
from app.models.npc_state import NPCPersonality
from app.domain.identity_events import CrystallizedBelief

# Множитель влияния убеждений (L2.5) на проекцию драйвов (L3)
_BELIEF_MODIFIER: float = 0.5

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
        beliefs: Optional[List[CrystallizedBelief]] = None
    ) -> Dict[str, float]:
        """
        Pure function: L0 + L2.5(Beliefs) -> L3 Projection.
        Вызывается каждый тик заново. Результат нигде не сохраняется.
        ADR-O-211: L1 не мутирует скаляры напрямую, только через Belief Layer.
        """
        # 1. Клонируем базовый архетип (L0)
        drives = dict(archetype.drives_base)
        
        # 2. Накладываем деформации (L2.5) через убеждения
        if beliefs:
            for belief in beliefs:
                # Убеждение о страхе (fear) увеличивает драйв fear
                if belief.trait == "fear":
                    drives["fear"] += belief.weight * _BELIEF_MODIFIER
                # Убеждение о доверии (trust) уменьшает драйв fear и повышает desire
                elif belief.trait == "trust":
                    drives["fear"] -= belief.weight * _BELIEF_MODIFIER * 0.5
                    drives["desire"] += belief.weight * _BELIEF_MODIFIER * 0.25
        
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