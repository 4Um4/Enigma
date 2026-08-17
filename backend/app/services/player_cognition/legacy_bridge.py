# path: /project/backend/app/services/player_cognition/legacy_bridge.py
"""
Назначение: Временный мост между расширенным IntentSemanticField и устаревшим PlayerAction для MvpTavernController.
Зависимости: app.domain.intent_profile, app.domain.epistemology, app.models.player_action, app.models.truth_state
Основные сущности: intent_to_player_action, PropositionMatcher
"""

import logging
from typing import Optional

from app.domain.intent_profile import IntentSemanticField
from app.domain.epistemology import Proposition, Predicate
from app.models.player_action import PlayerAction, ActionType
from app.models.truth_state import TruthState

logger = logging.getLogger(__name__)

class PropositionMatcher:
    """Семантический матч IntentDTO.proposition с TruthState.secrets."""
    def __init__(self, truth_state: Optional[TruthState]):
        self._truth = truth_state

    def match(self, prop: Optional[Proposition], target_id: str) -> Optional[str]:
        if not prop or not self._truth:
            return None
        
        # MVP-матч: если predicate=STOLE и target_id="merchant_goran", ищем секрет о краже
        # В будущем заменяется на embedding similarity (BGE-small-ru)
        for secret_id, secret in self._truth.secrets.items():
            participants = getattr(secret, "participants", [])
            if target_id not in participants:
                continue
            
            canon = getattr(secret, "canonical_truth", "").lower()
            # Базовая эвристика: если в каноне есть упоминание предиката
            if prop.predicate == Predicate.STOLE and ("краж" in canon or "украл" in canon or "взял" in canon):
                return secret_id
            if prop.predicate == Predicate.ATTACKED and ("удар" in canon or "напад" in canon or "убил" in canon):
                return secret_id
            if prop.predicate == Predicate.HELPED and ("помог" in canon or "спас" in canon):
                return secret_id
                
        return None

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