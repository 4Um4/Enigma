# backend/app/services/perception/presentation_assembler.py
"""
Файл: backend/app/services/perception/presentation_assembler.py
Назначение: Собирает ObservedFactsBundle из ObservedFact для DMContractBuilder.
Зависимости: backend.app.domain.observed_facts, backend.app.domain.observed_fact
"""

import logging
from typing import Dict, List, Optional, Tuple

from app.domain.observed_fact import ObservedFact
from app.domain.observed_facts import ObservedFactEntry, ObservedFactsBundle
from app.domain.presentation import (
    AudibleDTO,
    BreathingAudio,
    GazeArrow,
    NPCVisualState,
    PoseOverlay,
    VisualDTO,
    VoiceAudio,
)

logger = logging.getLogger(__name__)


class PresentationAssembler:
    """
    Собирает данные из Эпистемологии для потребителей (Frontend, DM).
    ЗАПРЕТ: Не читает Reality, ManifestationState напрямую (Инвариант 3).
    """

    def assemble_facts_bundle(self, facts: List[ObservedFact]) -> ObservedFactsBundle:
        entries = []
        by_target = {}

        for fact in facts:
            entry = ObservedFactEntry(
                target_id=fact.target_id,
                fact_name=fact.fact_name,
                value=fact.perceived_value
                if hasattr(fact, "perceived_value")
                else fact.value,
                confidence=fact.confidence,
                via=fact.observed_via,
            )
            entries.append(entry)

            if fact.target_id not in by_target:
                by_target[fact.target_id] = []
            by_target[fact.target_id].append(entry)

        return ObservedFactsBundle(facts=entries, by_target=by_target)

    def assemble_visual_dto(
        self,
        perceived_signals: List,
        recognition_map: Dict[str, dict]
    ) -> VisualDTO:
        """Собирает VisualDTO для рендера сцены."""
        npc_states: List[NPCVisualState] = []
        
        # Группируем сигналы по NPC
        signals_by_npc: Dict[str, List] = {}
        for sig in perceived_signals:
            # Регресс BUG-PERC-001 FIX: PerceivedSignal использует target_id, не npc_id.
            _sig_target = sig.target_id
            if _sig_target not in signals_by_npc:
                signals_by_npc[_sig_target] = []
            signals_by_npc[_sig_target].append(sig)
            
        for npc_id, sigs in signals_by_npc.items():
            recog = recognition_map.get(npc_id, {})
            display_name = "Незнакомец"
            if recog.get("knows_name"):
                display_name = recog.get("display_name", "Незнакомец")
            elif recog.get("confidence", 0.0) > 0.6:
                display_name = recog.get("display_name", "Незнакомец") + " (?)"

            pose = PoseOverlay()
            gaze = None
            
            for s in sigs:
                if s.channel == "body_manifestation":
                    if s.field == "muscle_tension":
                        pose = PoseOverlay(tense_contour=s.perceived_value, frozen_overlay=pose.frozen_overlay, tremor_animation=pose.tremor_animation, collapse_posture=pose.collapse_posture)
                    elif s.field == "tremor":
                        pose = PoseOverlay(tense_contour=pose.tense_contour, frozen_overlay=pose.frozen_overlay, tremor_animation=s.perceived_value, collapse_posture=pose.collapse_posture)
                elif s.channel == "gaze":
                    if s.field == "avoidance":
                        gaze = GazeArrow(avoidance=s.perceived_value)
                        
            # Размытие при низкой уверенности
            min_conf = min((s.confidence for s in sigs), default=0.5)
            blur = max(0.0, 0.5 - min_conf) if min_conf < 0.5 else 0.0
            
            npc_states.append(NPCVisualState(
                npc_id=npc_id,
                display_name=display_name,
                name_certainty=recog.get("confidence", 0.0),
                pose_overlay=pose,
                gaze_arrow=gaze,
                blur_intensity=blur
            ))
            
        return VisualDTO(npcs=tuple(npc_states))

    def assemble_audible_dto(self, perceived_signals: List) -> AudibleDTO:
        """Собирает AudibleDTO для аудио-движка."""
        voices: List[VoiceAudio] = []
        breathing: List[BreathingAudio] = []
        
        signals_by_npc: Dict[str, List] = {}
        for sig in perceived_signals:
            # Регресс BUG-PERC-001 FIX: PerceivedSignal использует target_id, не npc_id.
            _sig_target = sig.target_id
            if _sig_target not in signals_by_npc:
                signals_by_npc[_sig_target] = []
            signals_by_npc[_sig_target].append(sig)
            
        for npc_id, sigs in signals_by_npc.items():
            v_tempo, v_pitch, v_loud, v_tremor = 120.0, 130.0, 55.0, 0.0
            b_rate, b_depth, b_irreg = 14.0, 0.5, 0.0
            
            has_voice = False
            has_breath = False
            
            for s in sigs:
                if s.channel == "voice_manifestation":
                    has_voice = True
                    if s.field == "tempo": v_tempo = s.perceived_value
                    elif s.field == "pitch": v_pitch = s.perceived_value
                    elif s.field == "loudness": v_loud = s.perceived_value
                    elif s.field == "tremor": v_tremor = s.perceived_value
                elif s.channel == "breathing":
                    has_breath = True
                    if s.field == "rate": b_rate = s.perceived_value
                    elif s.field == "depth": b_depth = s.perceived_value
                    elif s.field == "irregularity": b_irreg = s.perceived_value
                    
            if has_voice:
                voices.append(VoiceAudio(npc_id=npc_id, tempo=v_tempo, pitch=v_pitch, loudness=v_loud, tremor=v_tremor))
            if has_breath:
                breathing.append(BreathingAudio(npc_id=npc_id, rate=b_rate, depth=b_depth, irregularity=b_irreg))
                
        return AudibleDTO(voices=tuple(voices), breathing_sounds=tuple(breathing))
