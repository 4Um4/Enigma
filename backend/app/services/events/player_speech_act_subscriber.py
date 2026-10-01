"""path: /project/backend/app/services/events/player_speech_act_subscriber.py

Назначение: Consumption v0 (вердикт Мастера, α-вариант): PLAYER_SPOKE →
    semantic_acts → SELF_INTRODUCTION{name} → Claim в существующую
    DialogueSession (v0-хранилище, DialogueSession.add_claim).
    ГРАНИЦА: Claim = «игрок представился как X» — кратковременный вход
    в cognition NPC, НЕ permanent memory. Запрещено вердиктом:
    TruthState, глобальный player_name, NameKnowledge-persistence,
    запись памяти LLM (детерминированная конвертация акт→claim).
    Идемпотентность по event_id (прецедент Q5/ADR-O-382).
Зависимости: app.services.memory.memory_manager (инъекция).
Основные сущности: PlayerSpeechActSubscriber.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

_MAX_NAME_LEN = 64
_INTRO_CONFIDENCE = 0.9


class PlayerSpeechActSubscriber:
    """Детерминированный потребитель речевых актов игрока (v0: только
    SELF_INTRODUCTION). Без LLM: Python — хозяин причинной записи."""

    def __init__(
        self,
        memory_manager: Any,
        campaign_id_provider: Any = None,
        tick_provider: Any = None,
    ) -> None:
        self._memory = memory_manager
        self._get_campaign_id = campaign_id_provider or (lambda: "Open_road")
        self._get_tick = tick_provider or (lambda: 0)

    def on_player_spoke(self, event: Any) -> None:
        try:
            payload = getattr(event, "payload", {}) or {}  # noqa: ENIGMA002
            acts = payload.get("semantic_acts") or []
            if not acts:
                return
            event_id = str(getattr(event, "id", "") or "")
            campaign_id = self._get_campaign_id()
            tick = int(self._get_tick())

            for act in acts:
                if not isinstance(act, dict) or act.get("type") != "SELF_INTRODUCTION":
                    continue
                params = act.get("params") or {}
                name = str(params.get("name") or "").strip()
                if not name or len(name) > _MAX_NAME_LEN:
                    logger.warning(
                        f"[SPEECH_ACT] SELF_INTRODUCTION с невалидным name — пропущен "
                        f"(len={len(name)})"
                    )
                    continue
                npc_id = self._resolve_listener(payload)
                if not npc_id:
                    logger.info(
                        "[SPEECH_ACT] SELF_INTRODUCTION без адресата-актора — claim не пишется"
                    )
                    continue
                session = self._memory.get_dialogue_session(
                    campaign_id, npc_id, partner_id="player"
                )
                # Идемпотентность: дубль event_id → 1 claim (Q5-прецедент).
                if event_id and any(
                    c.event_id == event_id
                    for c in getattr(session, "claims", [])
                ):
                    logger.debug(f"[SPEECH_ACT] дубль event_id={event_id[:8]} — skip")
                    continue
                session.add_claim(
                    text=f"представился как «{name}»",
                    speaker="player",
                    confidence=_INTRO_CONFIDENCE,
                    tick=tick,
                    event_id=event_id,
                )
                logger.info(
                    f"[SPEECH_ACT] SELF_INTRODUCTION → claim в сессию {npc_id} "
                    f"(event={event_id[:8]}, name-len={len(name)})"
                )
        except Exception as e:
            # Подписчик не роняет тик (прецедент per-listener изоляции S208).
            logger.warning(f"[SPEECH_ACT] on_player_spoke failed: {e}")

    def _resolve_listener(self, payload: dict) -> str:
        """Адресат = реальный актор мира (F2-гард прецедента
        npc_dialogue_subscriber: узлы графа/объекты не заводят сессий)."""
        npc_id = str(payload.get("target_id") or payload.get("target") or "")
        if not npc_id or npc_id in ("player", "all"):
            return ""
        return npc_id
