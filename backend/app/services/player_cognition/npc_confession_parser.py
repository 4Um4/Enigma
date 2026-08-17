"""
Файл: backend/app/services/player_cognition/npc_confession_parser.py
Назначение: Парсинг LLM-ответов NPC на предмет признаний секретов. Использует PropositionMatcher (семантический матч, не keyword overlap).
Зависимости: app.models.truth_state, app.services.player_cognition.observation_log, app.services.player_cognition.player_belief_model, app.services.player_cognition.legacy_bridge
Основные сущности: NpcConfessionParser
"""

import logging
from typing import List, Optional

from app.models.observation import EvidencePolarity, ObservationSourceType
from app.models.truth_state import TruthState
from app.services.player_cognition.observation_log import ObservationLog
from app.services.player_cognition.player_belief_model import PlayerBeliefModel
from app.services.player_cognition.legacy_bridge import PropositionMatcher
from app.domain.epistemology import Proposition, Predicate

logger = logging.getLogger(__name__)


class NpcConfessionParser:
    """Парсит LLM-ответ NPC на предмет признаний секретов."""

    def __init__(
        self,
        truth_state: Optional[TruthState],
        observation_log: ObservationLog,
        belief_model: PlayerBeliefModel,
    ) -> None:
        self._truth = truth_state
        self._log = observation_log
        self._beliefs = belief_model
        self._matcher = PropositionMatcher(truth_state)

    def parse_and_record(
        self,
        npc_id: str,
        reply_text: str,
        tick: int,
        target_id: str = "player"
    ) -> List[str]:
        """Возвращает list of secret_ids, обнаруженных в ответе NPC."""
        if not reply_text or not self._truth:
            return []

        discovered = []
        reply_lower = reply_text.lower()

        # S199: Используем PropositionMatcher вместо keyword overlap.
        # Извлекаем Proposition из ответа (эвристически, пока LLM не возвращает Proposition напрямую).
        # Если LLM-ответ содержит "я украл", "я ударил", "я помог", создаём Proposition.
        _prop = None
        if "украл" in reply_lower or "взял" in reply_lower:
            _prop = Proposition(subject_id=npc_id, predicate=Predicate.STOLE, object_id="unknown", polarity=True)
        elif "ударил" in reply_lower or "напал" in reply_lower:
            _prop = Proposition(subject_id=npc_id, predicate=Predicate.ATTACKED, object_id="unknown", polarity=True)
        elif "помог" in reply_lower or "спас" in reply_lower:
            _prop = Proposition(subject_id=npc_id, predicate=Predicate.HELPED, object_id="unknown", polarity=True)

        # Если Proposition найден, используем PropositionMatcher для поиска секрета
        if _prop:
            secret_id = self._matcher.match(_prop, npc_id)
            if secret_id:
                self._record_confession(npc_id, secret_id, reply_text, tick, target_id)
                discovered.append(secret_id)
                return discovered

        # Fallback на старую логику keyword overlap (если Proposition не найден)
        for secret_id, secret in self._truth.secrets.items():
            participants = getattr(secret, "participants", [])
            if npc_id not in participants:
                continue

            canonical = getattr(secret, "canonical_truth", "").lower()
            confession_keywords = getattr(secret, "confession_keywords", [])

            if confession_keywords:
                if any(kw.lower() in reply_lower for kw in confession_keywords):
                    self._record_confession(npc_id, secret_id, reply_text, tick, target_id)
                    discovered.append(secret_id)
            elif canonical and len(canonical) > 10:
                canon_words = set(canonical.split()) - {"и", "в", "на", "не", "что", "это"}
                reply_words = set(reply_lower.split())
                overlap = len(canon_words & reply_words)
                if overlap >= 3:
                    self._record_confession(npc_id, secret_id, reply_text, tick, target_id)
                    discovered.append(secret_id)

        return discovered

    def _record_confession(self, npc_id: str, secret_id: str, reply_text: str, tick: int, target_id: str) -> None:
        if not self._truth:
            return
            
        obs = self._log.add(
            tick=tick,
            observation_type="npc_confession",
            content=reply_text,
            source_id=npc_id,
            source_type=ObservationSourceType.NPC,
        )
        ev = self._log.add_evidence(
            observation_id=obs.observation_id,
            secret_id=secret_id,
            evidence_strength=1.0,
            polarity=EvidencePolarity.SUPPORTS,
        )
        self._beliefs.update_from_evidence(obs, ev)
        self._truth.mark_discovered(secret_id)
        logger.info(f"[NPC_CONFESSION] npc={npc_id} secret={secret_id} recorded")