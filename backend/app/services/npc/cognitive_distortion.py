"""
CognitiveDistortionEngine — детерминированные когнитивные искажения NPC.

path: backend/app/services/npc/cognitive_distortion.py
Назначение: Возвращает модификаторы score для DecisionHub + bias для ProjectionLayer
Зависимости: npc_state.py (NPCState), psychological.py (DistortionProfile)
Основные сущности: CognitiveDistortionEngine

Стоит ПОСЛЕ MemoryManager, ПЕРЕД DecisionHub.

ПРИНЦИП (ШАГ C.1):
Distortion НЕ искажает числовые данные NPC.
Вместо этого возвращает score_modifiers для DecisionHub:
- threat_bias > 0 → FLEE +0.3, OBSERVE +0.15
- trust_bias < 0 → TALK -0.25, HELP -0.2
- salience_bias > 0 → OBSERVE +0.1

Реализм сохраняется:
- NPC ВЕДЕТ СЕЯ искажённо (через score modifiers)
- NPC ВЕРБАЛИЗИРУЕТСЯ искажённо (через bias в ProjectionLayer)
- StateApplicator работает с ЧИСТЫМИ данными (нет разрыва)
"""

from dataclasses import replace
from typing import Dict

from app.core.constants import (
    DISTRUST_STRESS_BOOST,
    DISTRUST_STRESS_THRESHOLD,
    MAX_DISTORTION_STRESS,
    RESENTMENT_BIAS_FACTOR,
    THREAT_AMPLIFICATION_FACTOR,
)
from app.models.psychological import DistortionProfile
from app.models.npc_state import NPCState


class CognitiveDistortionEngine:
    """
    Детерминированные когнитивные искажения — фильтр восприятия NPC.
    
    НЕ решает что делает.
    НЕ меняет формулу DecisionHub.
    Меняет то, КАК NPC видит мир перед принятием решения.
    
    Возвращает:
    - distorted_state: искажённый снапшот для DecisionHub (входы)
    - distortion_bias: 3 оси для ProjectionLayer (речевая проекция)
    """

    def apply(
        self,
        state: NPCState,
        actor_is_player: bool = True,
    ) -> tuple:
        """
        Применяет когнитивные искажения к копии state.
        Оригинал НЕ мутируется.
        
        Returns:
            (distorted_state, distortion_bias)
            distortion_bias: {"threat_bias": float, "trust_bias": float, "salience_bias": float}
        """
        threat_bias = 0.0
        trust_bias = 0.0
        salience_bias = 0.0

        fear_value = state.relationship_cache.get("fear", 0.0)
        trust_value = state.relationship_cache.get("trust", 0.0)

        # 1. Threat amplification: страх усиливает воспринимаемую угрозу
        if fear_value > 0:
            threat_bias = fear_value * THREAT_AMPLIFICATION_FACTOR
        # Debug: следим за накоплением — после калибровки удалить
        if fear_value != 0.0 or trust_value != 0.0:
            print(f"[DISTORTION_RAW] fear={fear_value:.4f} trust={trust_value:.4f}")

        # 2. Trust bias: накопленная обида + низкое доверие → подозрительность
        if actor_is_player and trust_value < DISTRUST_STRESS_THRESHOLD:
            trust_bias = -0.2  # фиксированное искажение при недоверии
        if state.resentment > 50.0:
            trust_bias -= (state.resentment - 50.0) * 0.004  # до -0.2 дополнительно

        # 3. Salience bias: высокий стресс → NPC фиксируется на угрозах
        if state.stress > 60.0:
            salience_bias = (state.stress - 60.0) * 0.01  # до +0.4

        # Суммарное искажение для stress (обратная совместимость)
        stress_boost = abs(threat_bias) * 50 + abs(trust_bias) * 20 + salience_bias * 30
        stress_boost = min(stress_boost, MAX_DISTORTION_STRESS)

        # Капы bias
        threat_bias = max(-1.0, min(1.0, threat_bias))
        trust_bias = max(-1.0, min(0.0, trust_bias))   # доверие можно только снизить
        salience_bias = max(0.0, min(1.0, salience_bias))

        # Governor: суммарное искажение не превышает 1.0
        # Предотвращает каскадное усиление при одновременном страхе + обиде + стрессе
        total = abs(threat_bias) + abs(trust_bias) + abs(salience_bias)
        if total > 1.0:
            scale = 1.0 / total
            threat_bias  = round(threat_bias  * scale, 3)
            trust_bias   = round(trust_bias   * scale, 3)
            salience_bias = round(salience_bias * scale, 3)
        else:
            threat_bias  = round(threat_bias, 3)
            trust_bias   = round(trust_bias, 3)
            salience_bias = round(salience_bias, 3)

        bias = DistortionProfile(
            threat_bias=threat_bias,
            trust_bias=trust_bias,
            salience_bias=salience_bias,
        )

        print(f"[DISTORTION] threat={threat_bias} trust={trust_bias} salience={salience_bias} (governor={'scaled' if total > 1.0 else 'ok'})")
        
        # ШАГ C.1: Возвращаем ОРИГИНАЛЬНЫЙ state + bias + модификаторы для DecisionHub
        # Искажение восприятия теперь выражается через score modifiers, не через фальшивые числа
        # Реализм сохраняется: NPC ведёт себя искажённо (через score), вербализируется искажённо (через bias)
        # Но StateApplicator работает с реальными данными (нет разрыва)
        
        # Модификаторы score: threat → FLEE бонус, trust → TALK штраф
        score_modifiers: Dict[str, float] = {}
        if threat_bias > 0.05:
            score_modifiers["flee"] = round(threat_bias * 0.3, 4)       # угроза → побег
            score_modifiers["observe"] = round(threat_bias * 0.15, 4)  # угроза → наблюдение
        if trust_bias < -0.05:
            score_modifiers["talk"] = round(trust_bias * 0.25, 4)       # недоверие → меньше разговора
            score_modifiers["help"] = round(trust_bias * 0.2, 4)       # недоверие → меньше помощи
        if salience_bias > 0.05:
            score_modifiers["observe"] = score_modifiers.get("observe", 0.0) + round(salience_bias * 0.1, 4)

        return state, bias, score_modifiers