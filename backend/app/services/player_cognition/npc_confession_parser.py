"""
Файл: backend/app/services/player_cognition/npc_confession_parser.py
Назначение: Парсинг LLM-ответов NPC на предмет признаний секретов.
Зависимости: app.models.truth_state, app.services.player_cognition.observation_log, app.services.player_cognition.player_belief_model
Основные сущности: NpcConfessionParser
"""

import logging
from typing import List, Optional

from app.models.observation import EvidencePolarity, ObservationSourceType
from app.models.truth_state import TruthState
from app.services.player_cognition.observation_log import ObservationLog
from app.services.player_cognition.player_belief_model import PlayerBeliefModel

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

        # Для каждого секрета, где npc_id — participant, проверяем keywords
        for secret_id, secret in self._truth.secrets.items():
            participants = getattr(secret, "participants", [])
            if npc_id not in participants:
                continue

            # Проверяем canonical_truth на совпадение с ответом
            canonical = getattr(secret, "canonical_truth", "").lower()
            confession_keywords = getattr(secret, "confession_keywords", [])

            # Если секрет имеет confession_keywords — используем их
            if confession_keywords:
                if any(kw.lower() in reply_lower for kw in confession_keywords):
                    self._record_confession(npc_id, secret_id, reply_text, tick, target_id)
                    discovered.append(secret_id)
            # Иначе — эвристика: если ответ подтверждает canonical_truth
            elif canonical and len(canonical) > 10:
                # Простая проверка: 3+ слова из canonical в ответе
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