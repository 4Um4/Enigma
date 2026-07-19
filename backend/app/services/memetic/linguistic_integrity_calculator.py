# backend/app/services/memetic/linguistic_integrity_calculator.py
"""
Вычисляет linguistic_integrity для NPC (L2.5 проекция).
Формула: willpower * class_factor * age_factor * identity_attachment
"""
from __future__ import annotations

from app.domain.memetic.voice_archetype import VoiceArchetype
from app.models.npc_profile import PsycheBase

class LinguisticIntegrityCalculator:
    """Вычисляет linguistic_integrity для NPC.
    
    Формула: willpower * class_factor * age_factor * identity_attachment
    """
    
    def compute(
        self,
        psyche: PsycheBase,
        voice_archetype: VoiceArchetype,
        npc_age: int,
        identity_attachment: float,  # 0..1, насколько NPC дорожит своей речью
    ) -> float:
        willpower_norm = psyche.willpower / 100.0  # 0..1
        class_factor = voice_archetype.class_factor  # 0..1, из архетипа
        age_factor = self._age_factor(npc_age)
        
        integrity = (
            willpower_norm 
            * class_factor 
            * age_factor 
            * identity_attachment
        )
        
        return max(0.0, min(1.0, integrity))
    
    def _age_factor(self, age: int) -> float:
        """Критический период по Леннбергу + подростковый пик по Лабову.
        
        0-2:    0.05 (не говорит)
        2-7:    0.1  (критический период, всё впитывает)
        7-12:   0.3  (раннее детство)
        12-15:  0.2  (подростковый пик — язык сверстников, 
                      НО absorption_x1.5, не integrity)
        15-25:  0.5  (молодой взрослый)
        25-50:  0.8  (устойчивый взрослый)
        50+:    0.95 (язык застыл)
        
        ВАЖНО: age_factor для INTEGRITY (сопротивление) — обратно
        пропорционален пластичности. Чем младше, тем ниже integrity.
        """
        if age < 2: return 0.05
        if age < 7: return 0.1
        if age < 12: return 0.3
        if age < 15: return 0.2
        if age < 25: return 0.5
        if age < 50: return 0.8
        return 0.95