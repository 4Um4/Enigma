"""
path: /project/backend/app/services/events/npc_dialogue_subscriber.py
Назначение: Слушает NPC_SPOKE события, замыкая цикл восприятия для NPC-NPC диалогов
    (эмоции, память, отношения).
Зависимости: app.services.events.event_bus, app.services.memory.memory_manager,
    app.services.memory.relationship_store, app.services.affective.affective_integrator
Основные сущности: NpcDialogueSubscriber
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class NpcDialogueSubscriber:
    """Слушает NPC_SPOKE события и замыкает цикл восприятия для NPC-NPC диалогов.

    Для canonical реплик — полная обработка:
        AffectiveIntegrator → WorkingMemory (с текстом) → RelationshipStore

    Для ambient реплик — упрощённая:
        WorkingMemory (абстрактно) → RelationshipStore
    """

    def __init__(
        self,
        memory_manager: Any,
        relationship_store: Any,
        affective_integrator: Any = None,
        npc_states_provider: Any = None,
        campaign_id_provider: Any = None,  # NEW — callable() -> str
    ) -> None:
        self.memory = memory_manager
        self.relationships = relationship_store
        self.affective = affective_integrator
        self._get_npc_state = npc_states_provider
        self._get_campaign_id = campaign_id_provider or (lambda: "Open_road")

    def on_npc_spoke(self, event: Any) -> None:
        # Поддержка как EventDTO, так и dict (для тестов)
        if hasattr(event, "payload"):
            speaker = getattr(event, "source", "")
            payload = getattr(event, "payload", {}) or {}
            tick = getattr(event, "timestamp", 0)
        else:
            speaker = event.get("source", "")
            payload = event.get("payload", {})
            tick = event.get("timestamp", 0)
            
        listener = payload.get("target_id")
        text = payload.get("text", "")
        tone = payload.get("tone", "NEUTRAL")
        topic = payload.get("topic", "")
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

    def _process_canonical(
        self,
        speaker: str,
        listener: str,
        text: str,
        tone: str,
        topic: str,
        tick: int,
    ) -> None:
        """Полная обработка canonical реплики (с текстом от LLM)."""
        _campaign_id = self._get_campaign_id()

        # 1. STM (Short-Term Memory) — добавляем реплику
        try:
            self.memory.add_dialogue_turn(
                campaign_id=_campaign_id,
                npc_id=listener,
                speaker=speaker,
                text=text,
            )
        except Exception as mem_err:
            logger.warning(f"[NPC_DIALOGUE_SUB] add_dialogue_turn failed for {listener}: {mem_err}")

        # 2. AffectiveIntegrator — обновить эмоции listener'а (NEW)
        if self.affective is not None and self._get_npc_state is not None:
            try:
                listener_state = self._get_npc_state(listener)
                if listener_state is not None:
                    interpretation = self._build_interpretation(tone, text, topic)
                    self.affective.apply(listener, interpretation)
                    logger.info(
                        f"[NPC_DIALOGUE_SUB] {listener} affective updated "
                        f"after {speaker} (tone={tone})"
                    )
            except Exception as aff_err:
                logger.warning(
                    f"[NPC_DIALOGUE_SUB] affective update failed for "
                    f"{listener}: {aff_err}"
                )

        # 3. RelationshipStore
        delta_trust, delta_fear = self._compute_rel_delta(tone)
        try:
            self.relationships.update(
                campaign_id=_campaign_id,
                source=listener,
                target=speaker,
                delta={"trust": delta_trust, "fear": delta_fear},
            )
            logger.info(
                f"[NPC_DIALOGUE_SUB] {listener} rel update: "
                f"{speaker} trust={delta_trust:+.1f} fear={delta_fear:+.1f}"
            )
        except Exception as rel_err:
            logger.warning(f"[NPC_DIALOGUE_SUB] relationship update failed: {rel_err}")

    def _process_ambient(
        self,
        speaker: str,
        listener: str,
        tone: str,
        topic: str,
        tick: int,
    ) -> None:
        """Упрощённая обработка ambient реплики (без LLM-конкретики)."""
        _campaign_id = self._get_campaign_id()

        # Ambient — дельты в 5 раз меньше, без записи в STM
        delta_trust, delta_fear = self._compute_rel_delta(tone)
        try:
            self.relationships.update(
                campaign_id=_campaign_id,
                source=listener,
                target=speaker,
                delta={"trust": delta_trust * 0.2, "fear": delta_fear * 0.2},
            )
        except Exception as rel_err:
            logger.warning(f"[NPC_DIALOGUE_SUB] ambient relationship update failed: {rel_err}")

    def _build_interpretation(self, tone: str, text: str, topic: str) -> dict:
        """Строит упрощённую интерпретацию реплики для AffectiveIntegrator.

        AffectiveIntegrator обычно получает интерпретацию из InterpretationEngine,
        но для NPC-NPC диалогов мы строим её напрямую из tone — без отдельного
        LLM-вызова для интерпретации.
        """
        _TONE_TO_AFFECT = {
            "ANGRY": {"anger": 0.3, "fear": 0.1, "sadness": 0.0},
            "FRIENDLY": {"joy": 0.2, "trust": 0.1},
            "FLIRTY": {"joy": 0.15, "embarrassment": 0.2},
            "VENTING": {"sadness": 0.2, "empathy": 0.2},
            "MANIPULATIVE": {"suspicion": 0.2, "fear": 0.1},
            "FEARFUL": {"fear": 0.2, "sympathy": 0.1},
            "NEUTRAL": {},
        }
        return {
            "affect_deltas": _TONE_TO_AFFECT.get(tone, {}),
            "source": f"dialogue:{tone}",
            "text": text,
            "topic": topic,
        }

    def _compute_rel_delta(self, tone: str) -> tuple[float, float]:
        """Конвертирует tone в изменения trust/fear."""
        _BASE = {
            "ANGRY": (-0.10, 0.05),
            "FRIENDLY": (0.05, 0.0),
            "FLIRTY": (0.03, 0.0),
            "VENTING": (0.02, 0.0),
            "MANIPULATIVE": (-0.05, 0.02),
            "FEARFUL": (0.0, 0.03),
            "NEUTRAL": (0.005, 0.0),  # Шкала 0..1: привыкание очень медленное
            "PANIC": (-0.02, 0.08),
            "CURIOUS": (0.01, 0.0),
            "SAD": (-0.01, 0.01),
            "SUSPICIOUS": (-0.03, 0.01),
        }
        return _BASE.get(tone, (0.0, 0.0))