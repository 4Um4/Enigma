"""
path: backend/app/services/npc/pe_modifier_resolver.py
Назначение: Конвертация ожиданий (ExpectationStore) в drive_modifiers для DecisionHub.
Зависимости: app.services.npc.expectation_store
Основные сущности: PEModifierResolver
"""
import math
from typing import Dict
from app.services.npc.expectation_store import Expectation

class PEModifierResolver:
    """
    S-93: Active Inference Loop.
    Преобразует ожидания NPC (T-1) в модификаторы utility (T0).
    Использует tanh для плавного роста и clamp (MAX_PE_INF) для защиты от доминирования.
    """
    MAX_PE_INF = 0.25  # PE не может добавить больше ±0.25 к score

    def resolve(self, expectation: Expectation) -> Dict[str, float]:
        mods: Dict[str, float] = {}
        
        # Нормализуем через tanh: плавный рост от 0 до 1, без резких скачков.
        _threat_mod = math.tanh(expectation.expected_threat * 2.0)
        _reward_mod = math.tanh(abs(expectation.expected_reward) * 2.0) * math.copysign(1, expectation.expected_reward)
        
        # Угроза бустит FLEE и штрафует APPROACH (пропорционально)
        if _threat_mod > 0:
            mods["FLEE"] = min(self.MAX_PE_INF, _threat_mod * 0.5)
            mods["APPROACH"] = max(-self.MAX_PE_INF, -_threat_mod * 0.5)
            mods["ATTACK"] = min(self.MAX_PE_INF, _threat_mod * 0.2) # Лёгкая превентивная агрессия
            
        # Разочарование (отрицательный reward) штрафует TALK/TRADE
        if _reward_mod < 0:
            mods["TALK"] = max(-self.MAX_PE_INF, _reward_mod * 0.6)
            mods["TRADE"] = max(-self.MAX_PE_INF, _reward_mod * 0.6)
            
        return mods