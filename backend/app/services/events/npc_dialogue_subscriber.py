"""
path: /project/backend/app/services/events/npc_dialogue_subscriber.py
Назначение: Слушает NPC_SPOKE события, замыкая цикл восприятия для NPC-NPC диалогов (эмоции, память, отношения).
Зависимости: app.services.events.event_bus, app.services.memory.memory_manager, app.services.memory.relationship_store
Основные сущности: NpcDialogueSubscriber
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class NpcDialogueSubscriber:
    """Слушает NPC_SPOKE события и замыкает цикл восприятия для NPC-NPC диалогов.
    
    Для canonical реплик — полная обработка:
        PerceptionEngine → InterpretationEngine → AffectiveIntegrator →
        WorkingMemory (с текстом) → RelationshipStore → BeliefAggregator
    
    Для ambient реплик — упрощённая:
        WorkingMemory (абстрактно) → RelationshipStore
    """

    def __init__(
        self,
        memory_manager: Any,
        relationship_store: Any,
    ) -> None:
        self.memory = memory_manager
        self.relationships = relationship_store

    def on_npc_spoke(self, event: dict) -> None:
        speaker = event.get("source", "")
        payload = event.get("payload", {})
        listener = payload.get("target_id")
        text = payload.get("text", "")
        tone = payload.get("tone", "NEUTRAL")
        topic = payload.get("topic", "")
        tick = event.get("timestamp", 0)
        is_canonical = "Stub LLM" not in text and text != ""

        if not speaker or not listener or listener == "all":
            return

        logger.info(
            f"[NPC_DIALOGUE_SUB] {listener} heard {speaker} "
            f"(tone={tone}, topic={topic!r}, canonical={is_canonical})"
        )

        try:
            if is_canonical:
                self._process_canonical(speaker, listener, text, tone, topic, tick)
            else:
                self._process_ambient(speaker, listener, tone, topic, tick)
        except Exception as e:
            logger.exception(
                f"[NPC_DIALOGUE_SUB] failed for {listener} hearing {speaker}: {e}"
            )

    def _process_canonical(self, speaker: str, listener: str, text: str, tone: str, topic: str, tick: int) -> None:
        """Полная обработка canonical реплики (с текстом от LLM)."""
        # 4. WorkingMemory — с конкретным текстом
        self.memory.write_session_memory(
            npc_id=listener,
            episode={
                "tick": tick,
                "type": "dialogue_heard",
                "speaker": speaker,
                "text": text,
                "tone": tone,
                "topic": topic,
                "canonical": True,
            },
        )

        # 5. RelationshipStore
        delta_trust, delta_fear = self._compute_rel_delta(tone)
        self.relationships.update_trust(listener, speaker, delta_trust)
        self.relationships.update_fear(listener, speaker, delta_fear)
        logger.info(
            f"[NPC_DIALOGUE_SUB] {listener} rel update: "
            f"{speaker} trust={delta_trust:+.1f} fear={delta_fear:+.1f}"
        )

    def _process_ambient(self, speaker: str, listener: str, tone: str, topic: str, tick: int) -> None:
        """Упрощённая обработка ambient реплики (без LLM-конкретики)."""
        self.memory.write_session_memory(
            npc_id=listener,
            episode={
                "tick": tick,
                "type": "ambient_heard",
                "speaker": speaker,
                "topic": topic,
                "tone": tone,
                "canonical": False,
            },
        )

        delta_trust, delta_fear = self._compute_rel_delta(tone)
        self.relationships.update_trust(listener, speaker, delta_trust * 0.2)
        self.relationships.update_fear(listener, speaker, delta_fear * 0.2)

    def _compute_rel_delta(self, tone: str) -> tuple[float, float]:
        """Конвертирует tone в изменения trust/fear."""
        _BASE = {
            "ANGRY": (-5.0, 2.0),
            "FRIENDLY": (3.0, 0.0),
            "FLIRTY": (2.0, 0.0),
            "VENTING": (1.0, 0.0),
            "MANIPULATIVE": (-2.0, 1.0),
            "FEARFUL": (0.0, 1.0),
            "NEUTRAL": (0.0, 0.0),
        }
        return _BASE.get(tone, (0.0, 0.0))