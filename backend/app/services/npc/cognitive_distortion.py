"""
CognitiveDistortionEngine — детерминированные когнитивные искажения NPC.

path: backend/app/services/npc/cognitive_distortion.py
Назначение: Детерминированные когнитивные искажения NPC — меняют восприятие перед DecisionHub, не трогая формулу
Зависимости: npc_state.py (NPCState), dataclasses.replace
Основные сущности: CognitiveDistortionEngine

Стоит ПОСЛЕ MemoryManager, ПЕРЕД DecisionHub.
Меняет ВХОДЫ DecisionHub (восприятие), не формулу.

Принцип: NPC не видит мир напрямую — видит через призму своего состояния.
Параноик усиливает угрозы. Обиженный видит враждебность там, где её нет.

ВАЖНО: Искажение НЕ сохраняется в состояние.
DecisionHub получает искажённый снапшот → решение искажено.
StateApplicator получает оригинал → реальность не меняется от галлюцинаций NPC.
"""

from dataclasses import replace

from app.models.psychological import DistortionProfile
from app.services.npc.npc_state import NPCState


# ─────────────────────────────────────────────────────────────────────────────
# Константы искажений (калибровочные коэффициенты, не магические значения)
# ─────────────────────────────────────────────────────────────────────────────

# threat_amplification: fear → стресс усиливается перед решением
# fear=100 → +15 stress (NPC воспринимает ситуацию как более опасную)
THREAT_AMPLIFICATION_FACTOR: float = 0.15

# memory_bias: накопленная обида → дополнительный стресс
# resentment > 50 → каждый пункт обиды добавляет 0.2 стресса
RESENTMENT_BIAS_FACTOR: float = 0.20

# intent_projection: низкое доверие к игроку → ожидание угрозы
# trust < -30 → +8 stress при любом взаимодействии с игроком
DISTRUST_STRESS_THRESHOLD: float = -30.0
DISTRUST_STRESS_BOOST: float = 8.0

# Жёсткий кап: искажение не может добавить больше этого значения
MAX_DISTORTION_STRESS: float = 30.0


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

        # Если искажение незначимо — возвращаем оригинал
        if stress_boost < 0.1 and all(abs(v) < 0.05 for v in bias.to_dict().values()):
            return state, bias

        # Искажённая копия: stress + trust/fear в relationship_cache
        new_rel = dict(state.relationship_cache)
        if threat_bias > 0:
            new_rel["fear"] = min(100.0, fear_value + threat_bias * 20)
        if trust_bias < 0:
            new_rel["trust"] = max(-100.0, trust_value + trust_bias * 30)

        distorted = replace(
            state,
            stress=min(state.stress + stress_boost, 100.0),
            relationship_cache=new_rel,
        )

        return distorted, bias