# backend/app/services/perception/fact_extractor.py
"""
Файл: backend/app/services/perception/fact_extractor.py
Назначение: Извлекает атомарные ObservedFact из PerceivedSignal.
Зависимости: backend.app.domain.observed_fact, backend.app.domain.perception_physics
"""

import logging
import uuid
from typing import Any, List

from app.domain.observed_fact import ObservedFact
from app.domain.perception_physics import PerceivedSignal

logger = logging.getLogger(__name__)


class FactExtractor:
    """
    Извлекает атомарные факты из PerceivedSignal (§17.2).
    ЗАПРЕТ: Не делает составных выводов (hand_on_weapon). Только атомарные (weapon_visible, hand_position).
    """

    def extract(
        self, signals: List[PerceivedSignal], current_tick: float
    ) -> List[ObservedFact]:
        facts = []

        for signal in signals:
            # Маршрутизация по каналам
            if signal.channel == "hands":
                facts.extend(self._extract_hands_facts(signal, current_tick))
            elif signal.channel == "body_manifestation":
                facts.extend(self._extract_body_facts(signal, current_tick))
            elif signal.channel == "movement":
                facts.extend(self._extract_movement_facts(signal, current_tick))
            elif signal.channel == "voice_manifestation":
                facts.extend(self._extract_voice_facts(signal, current_tick))
            elif signal.channel == "gaze":
                facts.extend(self._extract_gaze_facts(signal, current_tick))
            elif signal.channel == "micro_expression":
                facts.extend(self._extract_micro_facts(signal, current_tick))

        return facts

    def _extract_gaze_facts(
        self, signal: PerceivedSignal, tick: float
    ) -> List[ObservedFact]:
        facts = []
        if signal.field in ("gaze_direction", "head_orientation"):
            facts.append(
                self._make_fact(
                    signal, "behavior", "gaze_target", signal.perceived_value
                )
            )
        return facts

    def _extract_micro_facts(
        self, signal: PerceivedSignal, tick: float
    ) -> List[ObservedFact]:
        facts = []
        if signal.field == "jaw_clench":
            facts.append(
                self._make_fact(
                    signal, "behavior", "jaw_clench", signal.perceived_value
                )
            )
        elif signal.field == "pupil_dilation":
            facts.append(
                self._make_fact(
                    signal, "behavior", "pupil_dilation", signal.perceived_value
                )
            )
        return facts

    def _make_fact(
        self,
        signal: PerceivedSignal,
        fact_type: str,
        fact_name: str,
        value: Any,
        inaccuracy: List[str] = None,
    ) -> ObservedFact:
        return ObservedFact(
            fact_id=str(uuid.uuid4()),
            target_id=signal.target_id,
            fact_type=fact_type,
            fact_name=fact_name,
            value=value,
            confidence=signal.confidence,
            observed_at=signal.perceived_at,
            observed_via=signal.perceived_via,
            possible_inaccuracy=tuple(inaccuracy) if inaccuracy else (),
        )

    def _extract_hands_facts(
        self, signal: PerceivedSignal, tick: float
    ) -> List[ObservedFact]:
        facts = []
        if signal.field in ("held_object_left", "held_object_right"):
            if signal.perceived_value is not None:
                facts.append(
                    self._make_fact(
                        signal,
                        "body_state",
                        "weapon_visible"
                        if "weapon" in str(signal.perceived_value)
                        else "holding_object",
                        signal.perceived_value,
                        ["hidden_weapon", "small_object_concealed"],
                    )
                )
        elif signal.field == "grip_strength":
            facts.append(
                self._make_fact(
                    signal, "behavior", "grip_strength", signal.perceived_value
                )
            )
        return facts

    def _extract_body_facts(
        self, signal: PerceivedSignal, tick: float
    ) -> List[ObservedFact]:
        facts = []
        if signal.field == "muscle_tension":
            facts.append(
                self._make_fact(
                    signal, "behavior", "muscle_tension_level", signal.perceived_value
                )
            )
        elif signal.field == "tremor":
            facts.append(
                self._make_fact(
                    signal, "behavior", "tremor_amplitude", signal.perceived_value
                )
            )
        elif signal.field == "collapse":
            facts.append(
                self._make_fact(
                    signal, "body_state", "posture_collapse", signal.perceived_value
                )
            )
        return facts

    def _extract_movement_facts(
        self, signal: PerceivedSignal, tick: float
    ) -> List[ObservedFact]:
        facts = []
        if signal.field == "speed":
            facts.append(
                self._make_fact(
                    signal, "movement", "movement_speed", signal.perceived_value
                )
            )
        elif signal.field == "coordination":
            facts.append(
                self._make_fact(
                    signal, "movement", "movement_coordination", signal.perceived_value
                )
            )
        return facts

    def _extract_voice_facts(
        self, signal: PerceivedSignal, tick: float
    ) -> List[ObservedFact]:
        facts = []
        if signal.field == "tempo":
            facts.append(
                self._make_fact(signal, "voice", "voice_tempo", signal.perceived_value)
            )
        elif signal.field == "tremor":
            facts.append(
                self._make_fact(
                    signal, "voice", "voice_tremor_amplitude", signal.perceived_value
                )
            )
        return facts
