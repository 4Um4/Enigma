"""DLG-1 Speaker Symmetry — NpcSpeechActSubscriber (§3.6 DLG-L1).

Симметричный PlayerSpeechActSubscriber для NPC-пути: обрабатывает
semantic_acts из NPC_SPOKE payload. Только SELF_INTRODUCTION —
минимальный контракт, как у PLAYER-пути.

Границы:
- NpcDialogueSubscriber НЕ трогается (параллельный контур через _extractor);
- ClaimEventSubscriber НЕ трогается (его on_npc_spoke для Proposition-фолбэка);
- dialogue_materializer НЕ трогается (semantic_acts опциональны в payload);
- DialogueSession — существующий SSOT.

Дедупликация: event_id (Claim Bridge, ADR-O-404). Если NpcDialogueSubscriber
уже написал Claim с тем же event_id в той же сессии — дубль не пройдёт
(any(c.event_id == event_id for c in session.claims)).

Без LLM. Идемпотентность по event_id.
"""
from __future__ import annotations

import logging
from typing import Any

from app.domain.communication import SELF_TALK_SENTINEL

logger = logging.getLogger(__name__)

_MAX_NAME_LEN = 64
_INTRO_CONFIDENCE = 0.9


class NpcSpeechActSubscriber:
    """DLG-1: Симметричный PlayerSpeechActSubscriber для NPC-пути.

    Обрабатывает semantic_acts из NPC_SPOKE — детерминированно, без LLM.
    Поддерживает только SELF_INTRODUCTION (минимальный контракт DLG-1).
    Пишет Claim в cognition-контекст listener (не speaker).
    """

    def __init__(
        self,
        memory_manager: Any,
        campaign_id_provider: Any = None,
        tick_provider: Any = None,
    ) -> None:
        self._memory = memory_manager
        self._get_campaign_id = campaign_id_provider or (lambda: "Open_road")
        self._get_tick = tick_provider or (lambda: 0)

    def on_npc_spoke(self, event: Any) -> None:
        try:
            payload = getattr(event, "payload", {}) or {}
            acts = payload.get("semantic_acts") or []
            if not acts:
                return  # no semantic_acts → no-op (существующий NPC path не трогаем)

            event_id = str(getattr(event, "id", "") or "")
            speaker = str(getattr(event, "source", "") or "")
            listener = str(payload.get("target_id") or "")
            campaign_id = self._get_campaign_id()
            tick = int(self._get_tick())

            # Guards (симметрия с NpcDialogueSubscriber.on_npc_spoke:210)
            if not speaker or not listener or listener == "all":
                return
            if listener == SELF_TALK_SENTINEL:
                return  # soliloquy — нет cognition-получателя

            for act in acts:
                if not isinstance(act, dict) or act.get("type") != "SELF_INTRODUCTION":
                    continue
                params = act.get("params") or {}
                name = str(params.get("name") or "").strip()
                if not name or len(name) > _MAX_NAME_LEN:
                    logger.warning(
                        f"[NPC_SPEECH_ACT] SELF_INTRODUCTION с невалидным name — пропущен "
                        f"(len={len(name)}, speaker={speaker})"
                    )
                    continue

                session = self._memory.get_dialogue_session(
                    campaign_id, listener, partner_id=speaker
                )
                # Идемпотентность по event_id (Claim Bridge, ADR-O-404):
                # работает между контурами — если NpcDialogueSubscriber._process_canonical
                # уже написал Claim с тем же event_id, дубль не пройдёт.
                if event_id and any(
                    c.event_id == event_id
                    for c in getattr(session, "claims", [])
                ):
                    logger.debug(f"[NPC_SPEECH_ACT] дубль event_id={event_id[:8]} — skip")
                    continue

                session.add_claim(
                    text=f"представился как «{name}»",
                    speaker=speaker,
                    confidence=_INTRO_CONFIDENCE,
                    tick=tick,
                    event_id=event_id,
                )
                logger.info(
                    f"[NPC_SPEECH_ACT] SELF_INTRODUCTION → claim в сессию "
                    f"listener={listener}, partner={speaker} "
                    f"(event={event_id[:8]}, name-len={len(name)})"
                )
        except Exception as e:
            logger.warning(f"[NPC_SPEECH_ACT] processing failed: {e}", exc_info=True)
