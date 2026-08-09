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
        npc_states_provider: Any = None,
        campaign_id_provider: Any = None,  # NEW — callable() -> str
        avatar_service: Any = None,
        spatial_query_provider: Any = None,
        l1_chronicle: Any = None,
        tick_provider: Any = None,  # H-01 FIX: callable() -> int (симуляционный тик)
        dialogue_update_extractor: Any = None,  # BUG-DL-09: Для извлечения claims/questions
    ) -> None:
        self.memory = memory_manager
        self.relationships = relationship_store
        self._get_npc_state = npc_states_provider
        self._get_campaign_id = campaign_id_provider or (lambda: "Open_road")
        self._avatar_service = avatar_service
        self._get_spatial_query = spatial_query_provider
        self._l1_chronicle = l1_chronicle
        self._get_tick = tick_provider or (lambda: 0)
        self._extractor = dialogue_update_extractor

    def on_npc_spoke(self, event: Any) -> None:
        # Поддержка как EventDTO, так и dict (для тестов)
        if hasattr(event, "payload"):
            speaker = getattr(event, "source", "")
            payload = getattr(event, "payload", {}) or {}
        else:
            speaker = event.get("source", "")
            payload = event.get("payload", {})
        
        # H-01 FIX: Используем каноничный симуляционный тик (ctx.tick_number / scene_state["tick"])
        # вместо event.timestamp (wall-clock time), чтобы удовлетворить контракт L1Chronicle (INTEGER).
        tick = int(self._get_tick())

        listener = payload.get("target_id")
        text = payload.get("text", "")
        tone = payload.get("tone", "NEUTRAL")
        topic = payload.get("topic", "")
        # V8-SOC-11 FIX: Распознаём русскую заглушку "[Заглушка]" как ambient
        is_canonical = "Stub LLM" not in text and "[Заглушка]" not in text and text != ""

        if not speaker or not listener or listener == "all":
            return

        # S128: Eavesdrop — если игрок рядом, он подслушивает реплику
        if self._avatar_service and self._get_spatial_query:
            _campaign_id = self._get_campaign_id()
            _spatial_query = self._get_spatial_query()
            if _spatial_query:
                # P1-07 FIX: Совместимость с SpatialService и SpatialQueryService
                _dist_to_player = 999.0
                if hasattr(_spatial_query, "player_distances"):
                    _dist_to_player = _spatial_query.player_distances([speaker]).get(speaker, 999.0)
                elif hasattr(_spatial_query, "_npc_positions"):
                    _player_pos = _spatial_query._npc_positions.get("player", {}).get("local_position", {})
                    _speaker_pos = _spatial_query._npc_positions.get(speaker, {}).get("local_position", {})
                    if _player_pos and _speaker_pos:
                        import math
                        _dist_to_player = math.hypot(
                            _player_pos.get("x", 0.0) - _speaker_pos.get("x", 0.0),
                            _player_pos.get("y", 0.0) - _speaker_pos.get("y", 0.0)
                        )
                if _dist_to_player < 8.0 and is_canonical:
                    self._avatar_service.append_journal(
                        campaign_id=_campaign_id, speaker=speaker, text=text
                    )

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

        # 1. STM (Short-Term Memory) — добавляем реплику (BUG-DL-05: симметричная запись)
        try:
            # BUG-DL-09: Извлекаем structured update (claims, questions) из реплики
            _stm_before = ""
            _update = None
            if self._extractor:
                _session = self.memory.get_dialogue_session(_campaign_id, listener, partner_id=speaker)
                _stm_before = _session.to_prompt_block()
                _update = self._extractor.extract(_stm_before, text, speaker)
            
            self.memory.add_dialogue_turn(
                campaign_id=_campaign_id,
                npc_id=listener,
                speaker=speaker,
                text=text,
                target_id=listener,
                intent=_update.last_speaker_intent if _update else "dialogue",
                tick=tick,
                partner_id=speaker,  # BUG-DL-05: Per-pair session
            )
            # BUG-DL-09: Применяем обновления темы, claims и open_questions к per-pair сессии
            # (BUG-DLG-007 FIX: симметричный ключ означает, что listener и speaker делят одну сессию)
            if _update:
                _session = self.memory.get_dialogue_session(_campaign_id, listener, partner_id=speaker)
                if _update.topic:
                    _session.topic = _update.topic
                    _session.topic_confidence = _update.topic_confidence
                for claim in _update.new_claims or []:
                    _session.add_claim(
                        text=claim.get("text", ""),
                        speaker=speaker,
                        confidence=claim.get("confidence", 0.5),
                        tick=tick,
                    )
                for q in _update.raised_questions or []:
                    _session.add_open_question(
                        text=q.get("text", ""),
                        asked_by=speaker,
                        addressed_to=q.get("addressed_to", listener),
                        tick=tick,
                    )
                for q_idx in _update.answered_questions or []:
                    _session.answer_question(q_idx, text, speaker, tick)
        except Exception as mem_err:
            logger.warning(f"[NPC_DIALOGUE_SUB] add_dialogue_turn failed for {listener}/{speaker}: {mem_err}")
            
            # BUG-DL-06: Отложенная запись в L2 (narrative_cache) через буфер MemoryManager.
            # Фаза 3 следующего тика применит это событие к свежему NPCState.
            from app.domain.events import EventDTO
            _dialogue_event = EventDTO.create(
                event_type="dialogue_line",
                source=speaker,
                payload={
                    "npc_id": listener,  # Тот, кто слышит (для записи в его narrative_cache)
                    "text": text,
                    "topic": topic,
                    "tone": tone,
                    "speaker_id": speaker,
                    "scene_state": {},  # Пустой контекст, apply() использует дефолты
                    "npc_stress": 0.0,
                },
                visibility="public",
                radius=10.0,
                persistence_level="session",
            )
            self.memory.add_pending_dialogue_memory(_dialogue_event)

        # 3. RelationshipStore
        # NEW-2: Маппим tone на event_type из P2-05 (get_base_delta).
        # Если тон не замапплен (напр. NEUTRAL), дельты равны 0 (предотвращает Double Truth со старой шкалой).
        _TONE_TO_NPC_EVENT = {
            "ANGRY": "npc_insults",
            "MANIPULATIVE": "npc_threatens",
            "FRIENDLY": "npc_helps",
            "FEARFUL": "npc_threatens",
            "FLIRTY": "npc_helps",
        }
        _npc_event_type = _TONE_TO_NPC_EVENT.get(tone)
        if _npc_event_type:
            from app.services.npc.decision.social_deltas import get_base_delta
            delta_trust, delta_fear, _ = get_base_delta(_npc_event_type)
        else:
            delta_trust, delta_fear = 0.0, 0.0
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

            # NEW-3: Bridge 2 — пишем NPC-NPC диалог в L1Chronicle для BeliefCrystallizationEngine
            if self._l1_chronicle:
                from app.domain.identity_events import TraitDriftEvent
                _drift_event = TraitDriftEvent(
                    tick_id=tick,
                    target_id=listener,
                    source_id=speaker,
                    effect_value=delta_trust,
                    observation_weight=1.0,
                    event_type=f"social_dialogue:{tone}",
                )
                self._l1_chronicle.commit_tick_buffer([_drift_event], tick)

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
        # NEW-2: Маппим tone на event_type из P2-05 (get_base_delta) с множителем 0.2 для ambient.
        # Если тон не замапплен, дельты равны 0.
        _TONE_TO_NPC_EVENT = {
            "ANGRY": "npc_insults",
            "MANIPULATIVE": "npc_threatens",
            "FRIENDLY": "npc_helps",
            "FEARFUL": "npc_threatens",
            "FLIRTY": "npc_helps",
        }
        _npc_event_type = _TONE_TO_NPC_EVENT.get(tone)
        if _npc_event_type:
            from app.services.npc.decision.social_deltas import get_base_delta
            _bt, _bf, _ = get_base_delta(_npc_event_type)
            delta_trust, delta_fear = _bt * 0.2, _bf * 0.2
        else:
            delta_trust, delta_fear = 0.0, 0.0

        try:
            self.relationships.update(
                campaign_id=_campaign_id,
                source=listener,
                target=speaker,
                delta={"trust": delta_trust, "fear": delta_fear},
            )
            logger.info(
                f"[NPC_DIALOGUE_SUB] {listener} rel update (ambient): "
                f"{speaker} trust={delta_trust:+.1f} fear={delta_fear:+.1f} (event={_npc_event_type or 'fallback'})"
            )
        except Exception as rel_err:
            logger.warning(f"[NPC_DIALOGUE_SUB] relationship update failed: {rel_err}")

        # NEW-3: Bridge 2 — пишем NPC-NPC диалог в L1Chronicle для BeliefCrystallizationEngine
        try:
            if self._l1_chronicle:
                from app.domain.identity_events import TraitDriftEvent
                _drift_event = TraitDriftEvent(
                    tick_id=tick,
                    target_id=listener,
                    source_id=speaker,
                    effect_value=delta_trust,
                    observation_weight=1.0,
                    event_type=f"social_dialogue:{tone}",
                )
                self._l1_chronicle.commit_tick_buffer([_drift_event], tick)
        except Exception as chron_err:
            logger.warning(f"[NPC_DIALOGUE_SUB] L1Chronicle append failed: {chron_err}")

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
