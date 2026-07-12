from __future__ import annotations

# path: backend/app/services/perception/perceptual_attention_service.py
# Назначение: Фильтрация PerceptionEvent по бюджету и сборка PlayerPerceptionDTO.
# ТЗ EMBODIED UI: Строгий attention_budget = 1.0.
# Зависимости: app.domain.perception, app.domain.snapshot
from typing import List

from app.domain.perception import PerceptionEvent
from app.domain.snapshot import (
    ActivePerception,
    AvatarDesyncDTO,
    AvatarStateDTO,
    PeripheralCueDTO,
    PlayerPerceptionDTO,
)

# Словарь наблюдений (семантические семена -> человекочитаемый текст)
# ЗАПРЕТ: Здесь не может быть слов "Боится", "Злится". Только наблюдения.
OBSERVATION_TEXTS = {
    "замер": "Замер на месте",
    "отворачивается": "Отвел взгляд",
    "напряжение": "Напряжение висит в воздухе",
    "крик": "Раздался крик",
}


class PerceptualAttentionService:
    """Пропускает события через диафрагму внимания.

    1. Сортирует по salience.
    2. Вычитает cost из бюджета.
    3. Преобразует в DTO для фронтенда.
    """

    CATEGORY_COST = {
        "CENTRAL": 0.6,
        "ATMOSPHERE": 0.2,
        "PERIPHERAL": 0.2,
        "RECONSTRUCTION": 0.8,
    }

    def build_perception(
        self,
        events: List[PerceptionEvent],
        avatar_state: AvatarStateDTO,
        current_tick: int,
    ) -> PlayerPerceptionDTO:
        budget = 1.0
        active_perceptions = []
        peripheral_cues = []

        # Сортируем по значимости (самое важное первым)
        sorted_events = sorted(events, key=lambda e: e.salience, reverse=True)

        for event in sorted_events:
            cost = self.CATEGORY_COST.get(event.category, 0.2)
            if budget >= cost:
                budget -= cost

                # Маппинг события в DTO в зависимости от категории
                if event.category == "PERIPHERAL":
                    peripheral_cues.append(
                        PeripheralCueDTO(
                            npc_id=event.source_cluster,
                            cue_key=self._seed_to_cue_key(event.semantic_seed),
                            hover_text=OBSERVATION_TEXTS.get(
                                event.semantic_seed, event.semantic_seed
                            ),
                        )
                    )
                elif event.category in ("ATMOSPHERE", "CENTRAL"):
                    active_perceptions.append(
                        ActivePerception(
                            text=OBSERVATION_TEXTS.get(
                                event.semantic_seed, event.semantic_seed
                            ),
                            intensity=event.salience,
                            decay_rate=-0.05,
                            created_tick=current_tick,
                        )
                    )

        # Слой 0: Подсознание (вычисляется из AvatarStateDTO)
        avatar_desync = AvatarDesyncDTO(
            camera_inertia=1.0 - avatar_state.perceptual_stability,
            motion_trail=avatar_state.motor_disruption * 0.5,
            auditory_muffle=avatar_state.sensory_noise * 0.8,
        )

        return PlayerPerceptionDTO(
            avatar_desync=avatar_desync,
            active_perceptions=active_perceptions,
            peripheral_cues=peripheral_cues,
        )

    def _seed_to_cue_key(self, semantic_seed: str) -> str:
        if "замер" in semantic_seed:
            return "FREEZE"
        if "отворач" in semantic_seed:
            return "AVOID_GAZE"
        if "тороп" in semantic_seed:
            return "HURRY"
        return "GENERIC"
