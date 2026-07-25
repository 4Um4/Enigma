"""
Файл: backend/app/services/social/mvp_tavern_controller.py
Назначение: Единая точка доступа к эпистемическим и социальным системам MVP.
Зависимости: Все созданные нами P7-компоненты.
"""

from pathlib import Path
from typing import Optional, Dict, Any
from app.services.truth_state_loader import TruthStateLoader
from app.models.truth_state import TruthState
from app.services.player_cognition.observation_log import ObservationLog
from app.services.player_cognition.player_belief_model import PlayerBeliefModel
from app.services.player_cognition.action_consequence_compiler import ActionConsequenceCompiler
from app.services.player_cognition.cognitive_dissonance_tracker import CognitiveDissonanceTracker
from app.services.social.social_fabric_tracker import SocialFabricTracker
from app.services.social.fate_tracker import FateTracker
from app.services.social.faction_alignment_tracker import FactionAlignmentTracker
from app.services.social.dilemma_engine import DilemmaEngine
from app.services.social.evaluation_engine import EvaluationEngine
from app.services.social.last_words_system import LastWordsSystem
from app.services.social.end_screen_builder import EndScreenDataBuilder
from app.services.social.exit_trigger import ExitTrigger
from app.services.state.world_diff_builder import WorldDiffBuilder

class MvpTavernController:
    """Фасад, объединяющий все системы миниигры для GameLoop."""
    
    def __init__(self, canon_path: Path) -> None:
        self._canon_path = canon_path
        
        # Инициализация базовых трекеров
        self.truth_state: Optional[TruthState] = None
        self.observation_log = ObservationLog()
        self.belief_model = PlayerBeliefModel()
        self.social_fabric = SocialFabricTracker()
        self.fate_tracker = FateTracker()
        self.faction_tracker = FactionAlignmentTracker()
        self.dilemma_engine = DilemmaEngine()
        self.cognitive_dissonance = CognitiveDissonanceTracker()
        
        # Сервисы
        self.evaluation_engine = EvaluationEngine()
        self.last_words_system = LastWordsSystem()
        self.end_screen_builder = EndScreenDataBuilder()
        self.exit_trigger = ExitTrigger()
        self.world_diff_builder = WorldDiffBuilder()
        
        # Компилятор последствий (связывает трекеры вместе)
        self.action_compiler = ActionConsequenceCompiler(
            observation_log=self.observation_log,
            belief_model=self.belief_model,
            social_fabric=self.social_fabric
        )

    def init_campaign(self, campaign_id: str) -> None:
        """Загрузка канона и сброс состояния для новой кампании."""
        # Загружаем каноническую истину
        self.truth_state = TruthStateLoader.load(self._canon_path)
        TruthStateLoader.validate(self.truth_state)
        
        # В реальной игре здесь будет загрузка baseline из village_relations.json
        # Пока мокаем пустымиbaseline для тестов
        # (SocialFabricTracker сам выбрасывает ошибку при повторной установке, так что это безопасно)
        
    def check_exit(self, scene_state: Dict[str, Any]) -> bool:
        """Проверяет, покинул ли игрок локацию."""
        return self.exit_trigger.check_exit(scene_state)

    def build_end_screen(self):
        """Собирает данные для финального экрана."""
        if not self.truth_state:
            raise RuntimeError("TruthState not loaded")
            
        evaluation = self.evaluation_engine.evaluate(
            truth=self.truth_state,
            beliefs=self.belief_model,
            observations=self.observation_log
        )
        
        return self.end_screen_builder.build(
            evaluation=evaluation,
            contradictions=self.cognitive_dissonance.get_all_contradictions(),
            fate_tracker=self.fate_tracker,
            last_words_system=self.last_words_system,
            social_fabric=self.social_fabric
        )