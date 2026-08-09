"""
Назначение: Сервис для интерпретации моторных следов NPC в субъективный опыт Игрока.
Переводит физические следы в восприятие. Читает только тело, не читает эмоции.
Зависимости: logging, app.domain.embodied_trace

Путь: backend/app/services/perception/phenomenology_projection_service.py
"""

import logging
from typing import Any, Dict, List, Optional

from app.domain.embodied_trace import EmbodiedTraceDTO, PlayerPerceptionDTO
from app.domain.snapshot import AvatarStateDTO

logger = logging.getLogger(__name__)


class PhenomenologyProjectionService:
    """
    ФАЗА 9: Интерпретация моторных следов в субъективные семантические ключи.
    Возвращает доменный DTO, который _convert_perception переводит в каноничный API-формат.
    """

    def project(
        self, traces: list[EmbodiedTraceDTO], scene_state: dict, tick: int, observed_facts: list[str] = None,
        avatar_state: Optional[AvatarStateDTO] = None
    ) -> PlayerPerceptionDTO:
        cues = []

        # Периферические сигналы от моторных следов (семантические ключи для i18n)
        for trace in traces:
            if getattr(trace, "is_frozen", False):
                cues.append({"npc_id": trace.npc_id, "cue_key": "FROZEN"})
            elif getattr(trace, "posture_rigidity", 0.0) > 0.4:
                cues.append({"npc_id": trace.npc_id, "cue_key": "TENSE_POSTURE"})

            # P5.2: Upper Limb Constraint -> Observable Arm Guarding
            if getattr(trace, "arm_restriction", 0.0) > 0.4:
                cues.append({"npc_id": trace.npc_id, "cue_key": "ARM_GUARDING"})
            # P5.1: Lower Limb Constraint -> Observable Limp
            if getattr(trace, "gait_asymmetry", 0.0) > 0.3:
                cues.append({"npc_id": trace.npc_id, "cue_key": "LIMPING"})
            elif getattr(trace, "is_shaking", False):
                cues.append({"npc_id": trace.npc_id, "cue_key": "SWAYING"})
            elif getattr(trace, "locomotion_instability", 0.0) > 0.3:
                cues.append({"npc_id": trace.npc_id, "cue_key": "UNEVEN_STANCE"})

            if getattr(trace, "action_interruption", 0.0) > 0.6:
                cues.append({"npc_id": trace.npc_id, "cue_key": "ABRUPT_STOP"})

            if getattr(trace, "micro_pause_density", 0.0) > 0.5:
                cues.append({"npc_id": trace.npc_id, "cue_key": "FREQUENT_PAUSES"})

            # Правило X: видимые следы физического повреждения (читаем тело, не эмоции)
            _instab = getattr(trace, "locomotion_instability", 0.0)
            _rigid = getattr(trace, "posture_rigidity", 0.0)
            _mpd = getattr(trace, "micro_pause_density", 0.0)
            _act_int = getattr(trace, "action_interruption", 0.0)

            if _rigid > 0.5 and _instab > 0.4:
                cues.append({"npc_id": trace.npc_id, "cue_key": "WINCING"})
            if _mpd > 0.5 and _rigid > 0.4:
                cues.append({"npc_id": trace.npc_id, "cue_key": "HOLDING_SIDE"})
            if _mpd > 0.3 and _instab > 0.5:
                cues.append({"npc_id": trace.npc_id, "cue_key": "BLEEDING"})
            if _act_int > 0.6:
                cues.append({"npc_id": trace.npc_id, "cue_key": "STAGGERED"})

        # ADR-MANIFEST: Наблюдаемые физические проявления (НЕ эмоции!)
        # Multi-manifest: NPC может быть одновременно напряжён И неуверен
        # Цвет = тип физики, не значение
        manifestations = {}
        for trace in traces:
            _nid = trace.npc_id
            _rigid = getattr(trace, "posture_rigidity", 0.0)
            _instab = getattr(trace, "locomotion_instability", 0.0)
            _mpd = getattr(trace, "micro_pause_density", 0.0)
            _act_int = getattr(trace, "action_interruption", 0.0)
            _frozen = getattr(trace, "is_frozen", False)

            _tags = []
            if _frozen or _rigid > 0.7:
                _tags.append("MANIFEST_RIGID")  # оцепенение — застывание тела
            if _rigid > 0.4 and not (_frozen or _rigid > 0.7):
                _tags.append("MANIFEST_TENSE")  # напряжение — мышечный тонус
            if _instab > 0.5:
                _tags.append("MANIFEST_UNSTABLE")  # неуверенность — потеря координации
            if _mpd > 0.5:
                _tags.append("MANIFEST_RESTLESS")  # суетливость — избыточная моторика
            if _act_int > 0.6:
                _tags.append("MANIFEST_ALERT")  # реактивность — резкая смена действия
            if _rigid > 0.4 and _instab > 0.4:
                _tags.append("MANIFEST_SUFFERING")  # деградация — боль+шаткость

            if _tags:
                manifestations[_nid] = _tags

        # Атмосфера локации (Rule X: из наблюдаемых моторных следов, НЕ из эмоций)
        # Считаем долю NPC с видимыми моторными симптомами
        npc_positions = scene_state.get("npc_positions", {})
        total_npcs = len([k for k in npc_positions.keys() if k != "player"])
        tense_count = sum(1 for t in traces if t.posture_rigidity > 0.4 or t.is_frozen)
        shake_count = sum(
            1 for t in traces if t.locomotion_instability > 0.3 or t.is_shaking
        )

        atm_key = None
        atm_intensity = 0.0
        if total_npcs > 0:
            tension_ratio = (tense_count + shake_count) / total_npcs
            if tension_ratio > 0.6:
                atm_key = "ATMOSPHERE_THICK_TENSION"
                atm_intensity = min(1.0, tension_ratio)
            elif tension_ratio > 0.3:
                atm_key = "ATMOSPHERE_UNEASY"
                atm_intensity = min(1.0, tension_ratio * 0.7)

        logger.info(f"[PERCEPTION_PROJECTOR] Traces={len(traces)} Cues={len(cues)}")

        # Cognitive Distortion: влияние состояния аватара на восприятие
        _threat_bias = 0.0
        _trust_bias = 0.0
        _salience_bias = 0.0
        if avatar_state:
            # Высокий сенсорный шум (стресс/боль) -> угроза кажется сильнее
            if avatar_state.sensory_noise > 0.4:
                _threat_bias = min(1.0, avatar_state.sensory_noise)
            # Низкая когнитивная связность -> паранойя (снижение доверия)
            if avatar_state.cognitive_coherence < 0.6:
                _trust_bias = max(-1.0, avatar_state.cognitive_coherence - 1.0)
            # Низкая стабильность восприятия -> туннельное зрение
            if avatar_state.perceptual_stability < 0.5:
                _salience_bias = min(1.0, 1.0 - avatar_state.perceptual_stability)

        return PlayerPerceptionDTO(
            active_perceptions=cues,
            atmosphere_key=atm_key,
            atmosphere_intensity=atm_intensity,
            embodied_traces=[
                t.__dict__ if hasattr(t, "__dict__") else dict(t) for t in traces
            ],
            manifestations=manifestations,
            observed_facts=observed_facts or [],
            threat_bias=_threat_bias,
            trust_bias=_trust_bias,
            salience_bias=_salience_bias,
        )
