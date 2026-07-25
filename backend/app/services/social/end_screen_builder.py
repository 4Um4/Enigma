"""
Файл: backend/app/services/social/end_screen_builder.py
Назначение: Сборка данных для финального экрана.
Зависимости: typing, app.models., app.services.
"""

from typing import List, Optional
from app.models.end_screen import EndScreenData, NpcFateScreenData
from app.models.evaluation import EvaluationResult
from app.models.cognitive_dissonance import Contradiction
from app.models.last_words import LastWord
from app.services.social.fate_tracker import FateTracker
from app.services.social.last_words_system import LastWordsSystem
from app.services.social.social_fabric_tracker import SocialFabricTracker

class EndScreenDataBuilder:
    def build(
        self,
        evaluation: EvaluationResult,
        contradictions: List[Contradiction],
        fate_tracker: FateTracker,
        last_words_system: LastWordsSystem,
        social_fabric: SocialFabricTracker
    ) -> EndScreenData:
        
        npc_fates_data: List[NpcFateScreenData] = []
        
        for fate_state in fate_tracker.get_all_states():
            if fate_state.resolved_fate:
                last_word = last_words_system.get_last_word(
                    npc_id=fate_state.npc_id,
                    fate=fate_state.resolved_fate,
                    social_fabric=social_fabric
                )
                npc_fates_data.append(NpcFateScreenData(
                    npc_id=fate_state.npc_id,
                    fate_outcome=fate_state.resolved_fate.value,
                    last_word=last_word
                ))
                
        return EndScreenData(
            evaluation=evaluation,
            npc_fates=npc_fates_data,
            contradictions=contradictions
        )