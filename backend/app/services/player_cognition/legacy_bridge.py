# path: /project/backend/app/services/player_cognition/legacy_bridge.py
"""
Назначение: Временный мост между расширенным IntentSemanticField и устаревшим PlayerAction для MvpTavernController.
Зависимости: app.domain.intent_profile, app.domain.epistemology, app.models.player_action, app.models.truth_state
Основные сущности: intent_to_player_action, PropositionMatcher
"""

import logging
from difflib import SequenceMatcher
from typing import Optional

from app.domain.intent_profile import IntentSemanticField
from app.domain.epistemology import Proposition, Predicate
from app.models.player_action import PlayerAction, ActionType
from app.models.truth_state import TruthState

logger = logging.getLogger(__name__)

class PropositionMatcher:
    """Семантический матч IntentDTO.proposition с TruthState.secrets через Embedding Similarity (Stub)."""
    def __init__(self, truth_state: Optional[TruthState]):
        self._truth = truth_state
        # Маппинг предикатов на эталонные фразы для семантического сравнения
        self._predicate_templates = {
            Predicate.STOLE: "украл взял кража",
            Predicate.ATTACKED: "ударил напал убил атака",
            Predicate.HELPED: "помог спас выручил поддержка",
        }

    def _similarity(self, text1: str, text2: str) -> float:
        """Заглушка для BGE-small-ru. Вычисляет семантическую близость через SequenceMatcher."""
        return SequenceMatcher(None, text1, text2).ratio()

    def match(self, prop: Optional[Proposition], target_id: str) -> Optional[str]:
        if not prop or not self._truth:
            return None
        
        best_match_id = None
        best_match_score = 0.0
        threshold = 0.2  # Порог семантической близости
        
        for secret_id, secret in self._truth.secrets.items():
            participants = getattr(secret, "participants", [])
            if target_id not in participants:
                continue
            
            canon = getattr(secret, "canonical_truth", "").lower()
            template = self._predicate_templates.get(prop.predicate, "")
            
            # Вычисляем семантическую близость между канонической правдой и шаблоном предиката
            score = self._similarity(canon, template)
            if score > best_match_score and score > threshold:
                best_match_score = score
                best_match_id = secret_id
                
        return best_match_id

def intent_to_player_action(intent: IntentSemanticField, tick: int, truth_state: Optional[TruthState]) -> PlayerAction:
    """Временный мост: конвертирует расширенный IntentDTO в PlayerAction для MvpTavernController.
    Возвращает PlayerAction с заполненным action_type и secret_id (если найден через PropositionMatcher).
    """
    # Маппинг ActionType (в IntentSemanticField) в ActionType (в PlayerAction)
    # В будущем PlayerAction будет удалён, а MvpTavernController будет принимать IntentDTO напрямую.
    _act_mapping = {
        "MOVE": ActionType.DIALOGUE, # MOVE не имеет эквивалента в MVP PlayerAction
        "OBSERVE": ActionType.DIALOGUE,
        "INTERACT": ActionType.DIALOGUE,
        "ATTACK": ActionType.ATTACK,
        "THREATEN": ActionType.BLACKMAIL, # Угроза = шантаж в MVP
        "PERSUADE": ActionType.DIALOGUE,
        "FLIRT": ActionType.HELP, # Флирт = помощь в MVP (временный костыль)
        "STEAL": ActionType.DIALOGUE,
        "GIVE": ActionType.HELP, # Дать = помочь в MVP
        "UNCERTAIN": ActionType.DIALOGUE,
    }
    
    _action_type_str = intent.action.value if intent.action else "UNCERTAIN"
    _player_action_type = _act_mapping.get(_action_type_str, ActionType.DIALOGUE)
    
    # Если есть social_intent или speech_act, уточняем
    if intent.social_intent:
        _si = intent.social_intent.value
        if _si == "intimidate":
            _player_action_type = ActionType.BLACKMAIL
        elif _si == "obtain_information":
            # Если игрок угрожает, чтобы узнать секрет, это BLACKMAIL
            if intent.speech_act and intent.speech_act.value == "threat":
                _player_action_type = ActionType.BLACKMAIL
                
    # Мост для PropositionMatcher
    _secret_id = None
    if truth_state and intent.proposition:
        matcher = PropositionMatcher(truth_state)
        _secret_id = matcher.match(intent.proposition, intent.target or "")
        
    return PlayerAction(
        action_id=f"player_act_{tick}",
        tick=tick,
        actor_id="player",
        action_type=_player_action_type,
        target_id=intent.target or "",
        secret_id=_secret_id,
        description=intent.raw_text
    )