from __future__ import annotations

# backend/app/services/npc/interpretation_engine.py
"""
Единый движок интерпретации: что событие значит для NPC.
Объединяет когнитивные искажения, оценку угрозы и анализ драйвов.

DEPRECATED модули, логика которых перенесена сюда:
- cognitive_distortion.py (bias + score_modifiers)
- threat_assessor.py (threat_level + threat_category)
- npc_cognition.py (normalized_drives + dominant_drive)

Путь: backend/app/services/npc/interpretation_engine.py
Назначение: Консолидированный движок интерпретации NPC-событий
Зависимости: DistortionProfile, InterpretationResult, EventContext, константы из app.core.constants
Основные сущности: InterpretationEngine

- В будущем может включать эмоциональную реакцию, прогнозирование поведения и т.д.
- Важно: InterpretationEngine НЕ мутирует NPCState — он вычисляет интерпретацию на основе текущего стейта и события, но не изменяет его. Все изменения стейта происходят в StateApplicator на основе интерпретации.
- Возможно стоит добавить "contextual modifiers" — дополнительные факторы, влияющие на интерпретацию (например, текущее расположение, время дня, присутствие других NPC).
- Важно: InterpretationEngine — это чистая функция от (NPCState, EventContext) → InterpretationResult. Это облегчает тестирование и отладку, так как можно изолированно проверять логику интерпретации без побочных эффектов.
"""


from typing import Dict, Optional

from app.core.constants import (
    DISTRUST_STRESS_THRESHOLD,
    THREAT_AMPLIFICATION_FACTOR,
)
from app.models.interpretation import InterpretationResult
from app.models.npc_state import NPCState
from app.models.psychological import DistortionProfile
from app.services.npc.decision_hub import EventContext

# ── Константы угроз (перенесены из DEPRECATED threat_assessor) ────────────────

# Маркеры → угроза (видимое снаряжение/поведение)
MARKER_THREAT: Dict[str, int] = {
    "heavy_armor": +20,
    "weapon_melee": +20,
    "weapon_ranged": +15,
    "drawn_weapon": +25,
    "combat_stance": +10,
    "blood_on_clothes": +15,
    "threatening_gesture": +20,
    "friendly_posture": -20,
    "hands_raised": -15,
    "unarmed": -10,
    "robes": -5,
    "guild_badge": +5,
    "slave_collar": -15,
    "chains": -10,
}

# Тип действия → угроза
ACTION_THREAT: Dict[str, int] = {
    "COMBAT": +30,
    "INTIMIDATE": +25,
    "CAPTURE": +35,
    "BRIBERY": -5,
    "PERSUASION": -10,
    "DIPLOMACY": -15,
    "ROMANCE": -10,
    "SOCIAL": -5,
    "EXPLORE": 0,
    "FLEE": 0,
    "UNKNOWN": 0,
}


class InterpretationEngine:
    """
    Консолидированный движок: EventContext + NPCState → InterpretationResult.
    Вызывается на Фазе 3 (после памяти, до DecisionHub).
    """

    def compute(
        self,
        state: NPCState,
        event: EventContext,
        player_reputation: Optional[Dict[str, int]] = None,
        drives_base: Dict[str, float] = None,
    ) -> InterpretationResult:
        """
        Вычисляет как NPC воспринимает событие: искажения, угроза, драйвы.
        Оригинальный state НЕ мутируется.
        """
        actor_is_player = event.actor_id == "player"

        # ── 1. Когнитивные искажения (из cognitive_distortion.py) ──────────
        bias = self._compute_bias(state, actor_is_player)
        score_modifiers = self._compute_score_modifiers(bias)

        # ── 2. Оценка угрозы (из threat_assessor.py) ───────────────────────
        threat_level, threat_category = self._compute_threat(
            event,
            player_reputation,
        )

        # ── 3. Драйвы (из npc_cognition.py) ───────────────────────────────
        normalized_drives = self._normalize_drives(drives_base)
        dominant_drive = self._get_dominant_drive(normalized_drives)

        return InterpretationResult(
            bias=bias,
            score_modifiers=score_modifiers,
            threat_level=threat_level,
            threat_category=threat_category,
            normalized_drives=normalized_drives,
            dominant_drive=dominant_drive,
        )

    # ── Приватные методы (логика из DEPRECATED модулей) ────────────────────

    def _compute_bias(
        self,
        state: NPCState,
        actor_is_player: bool,
    ) -> DistortionProfile:
        """
        Детерминированные когнитивные искажения — фильтр восприятия NPC.
        Меняет то, КАК NPC видит мир (bias для ProjectionLayer).
        """
        threat_bias = 0.0
        trust_bias = 0.0
        salience_bias = 0.0

        fear_value = state.relationship_cache.get("fear", 0.0)
        trust_value = state.relationship_cache.get("trust", 0.0)

        # Страх усиливает воспринимаемую угрозу
        if fear_value > 0:
            threat_bias = fear_value * THREAT_AMPLIFICATION_FACTOR

        # Накопленная обида + низкое доверие → подозрительность
        if actor_is_player and trust_value < DISTRUST_STRESS_THRESHOLD:
            trust_bias = -0.2
        if state.resentment > 50.0:
            trust_bias -= (state.resentment - 50.0) * 0.004

        # Высокий стресс → фиксация на угрозах
        if state.stress > 60.0:
            salience_bias = (state.stress - 60.0) * 0.01

        # Капы bias
        threat_bias = max(-1.0, min(1.0, threat_bias))
        trust_bias = max(-1.0, min(0.0, trust_bias))
        salience_bias = max(0.0, min(1.0, salience_bias))

        # Governor: суммарное искажение ≤ 1.0 — предотвращает каскадное усиление
        total = abs(threat_bias) + abs(trust_bias) + abs(salience_bias)
        if total > 1.0:
            scale = 1.0 / total
            threat_bias = round(threat_bias * scale, 3)
            trust_bias = round(trust_bias * scale, 3)
            salience_bias = round(salience_bias * scale, 3)
        else:
            threat_bias = round(threat_bias, 3)
            trust_bias = round(trust_bias, 3)
            salience_bias = round(salience_bias, 3)

        return DistortionProfile(
            threat_bias=threat_bias,
            trust_bias=trust_bias,
            salience_bias=salience_bias,
        )

    def _compute_score_modifiers(
        self,
        bias: DistortionProfile,
    ) -> Dict[str, float]:
        """
        Искажение восприятия → модификаторы score для DecisionHub.
        NPC ведёт себя искажённо (через score), но StateApplicator работает
        с реальными данными (нет разрыва между стейтом и поведением).
        """
        modifiers: Dict[str, float] = {}

        if bias.threat_bias > 0.05:
            modifiers["flee"] = round(bias.threat_bias * 0.3, 4)
            modifiers["observe"] = round(bias.threat_bias * 0.15, 4)

        if bias.trust_bias < -0.05:
            modifiers["talk"] = round(bias.trust_bias * 0.25, 4)
            modifiers["help"] = round(bias.trust_bias * 0.2, 4)

        if bias.salience_bias > 0.05:
            modifiers["observe"] = modifiers.get("observe", 0.0) + round(
                bias.salience_bias * 0.1, 4
            )

        return modifiers

    def _compute_threat(
        self,
        event: EventContext,
        player_reputation: Optional[Dict[str, int]] = None,
    ) -> tuple[int, str]:
        """
        Вычисляет уровень угрозы (0–100) и категорию.
        Учитывает видимые маркеры, тип действия и репутацию.
        """
        score = 0

        # Видимые маркеры угрозы
        for marker in event.visible_threat_markers:
            score += MARKER_THREAT.get(marker, 0)

        # Тип действия
        action_type = (
            event.event_type.value
            if hasattr(event.event_type, "value")
            else str(event.event_type)
        )
        score += ACTION_THREAT.get(action_type, 0)

        # Репутация игрока
        rep = player_reputation or {}
        if rep.get("cruel", 0) > 20:
            score += 10
        if rep.get("hero", 0) > 20:
            score -= 5
        if rep.get("betrayer", 0) > 10:
            score += 8

        threat_level = max(0, min(100, score))

        if threat_level >= 70:
            category = "CRITICAL"
        elif threat_level >= 45:
            category = "HIGH"
        elif threat_level >= 20:
            category = "MEDIUM"
        else:
            category = "LOW"

        return threat_level, category

    def _normalize_drives(self, drives: Dict[str, float]) -> Dict[str, float]:
        """Нормализует драйвы к сумме 1.0."""
        total = sum(drives.values())
        if total <= 0:
            return {"control": 0.25, "significance": 0.25, "fear": 0.25, "desire": 0.25}
        return {k: round(v / total, 4) for k, v in drives.items()}

    def _get_dominant_drive(self, drives: Dict[str, float]) -> str:
        """Возвращает ключ с максимальным значением."""
        return max(drives, key=drives.get)
