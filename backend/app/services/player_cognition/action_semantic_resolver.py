"""
path: /project/backend/app/services/player_cognition/action_semantic_resolver.py
Назначение: Эвристический резолвер текстового ввода игрока в PlayerAction.
Зависимости: app.models.player_action, app.models.truth_state, app.services.truth_state_loader, app.core.config
Основные сущности: ActionSemanticResolver
"""

import logging
from typing import Optional

from app.core.config import BASE_DIR
from app.models.player_action import ActionType, PlayerAction
from app.models.truth_state import TruthState
from app.services.truth_state_loader import TruthStateLoader

logger = logging.getLogger(__name__)

_DEFAULT_CANON_PATH = BASE_DIR / "config" / "canon" / "truth_state_tavern.json"

class ActionSemanticResolver:
    """Эвристический резолвер для парсинга raw_text в PlayerAction для MVP."""

    def __init__(self, truth_state: Optional[TruthState] = None):
        self._truth = truth_state
        if not self._truth:
            try:
                self._truth = TruthStateLoader.load(_DEFAULT_CANON_PATH)
            except Exception as e:
                logger.error(f"Failed to load default TruthState from {_DEFAULT_CANON_PATH}: {e}")
                self._truth = TruthState(secrets={}, relations=()) # Fallback для изоляции тестов

    def resolve(self, raw_text: str, tick: int, target_id: str) -> PlayerAction:
        """Разбирает текст игрока и возвращает структурированный PlayerAction."""
        text_lower = raw_text.lower()
        
        # 1. Определение ActionType
        # S211: ACCUSE — ПЕРВЫМ (специфичнее шантажа: «обвиняю» не должно
        # проваливаться в blackmail-эвристику «угрожаю»).
        if "обвиняю" in text_lower or "обвин" in text_lower or "accuse" in text_lower:
            _action_type = ActionType.ACCUSE
        elif "шантаж" in text_lower or "знаю про" in text_lower or "угрожаю" in text_lower:
            _action_type = ActionType.BLACKMAIL
        elif "помочь" in text_lower or "помогу" in text_lower:
            _action_type = ActionType.HELP
        else:
            _action_type = ActionType.DIALOGUE
            
        # 2. Поиск secret_id по совпадению корневых слов в каноне
        _secret_id = None
        if self._truth:
            for secret in self._truth.secrets.values():
                if target_id not in secret.participants:
                    continue
                
                canon = secret.canonical_truth.lower()
                sec_id = secret.secret_id.lower()
                
                # Эвристики совпадения
                if "подвал" in text_lower and "подвал" in canon:
                    _secret_id = secret.secret_id
                    break
                if "долг" in text_lower and ("долж" in canon or "debt" in sec_id):
                    _secret_id = secret.secret_id
                    break

        return PlayerAction(
            action_id=f"player_act_{tick}",
            tick=tick,
            actor_id="player",
            action_type=_action_type,
            target_id=target_id,
            secret_id=_secret_id,
            description=raw_text
        )