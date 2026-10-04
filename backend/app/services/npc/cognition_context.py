"""path: /project/backend/app/services/npc/cognition_context.py

Назначение: Step 5 (вердикт Мастера) — CognitionContextResolver: чистый
    READ-ONLY резолвер cognition-блока per-NPC. Единственный источник
    фактуры «что NPC слышал/знает» для ОБЕИХ путей порождения NPC-речи:
    VerbalizationContext (DialogueExecutor) и DMFrame (npc_contexts).
    STOP: не пишет Claims/Memory/TruthState/EpistemicStore; не store;
    не второй канал Claims→DM — один resolver, несколько потребителей.
    Граница формулировки: «представился как X» — НЕ «знает имя»
    (Consumption v0: claim = cognition-вход, не permanent memory).
Зависимости: app.services.memory.memory_manager (инъекция, только чтение
    session-API).
Основные сущности: CognitionContextResolver.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CognitionContextResolver:
    """Read-only проекция услышанного/знаемого NPC для cognition-каналов."""

    def __init__(self, memory_manager: Any, campaign_id_provider: Any = None) -> None:
        self._memory = memory_manager
        self._get_campaign_id = campaign_id_provider or (lambda: "Open_road")

    def resolve_block(self, npc_id: str, partner_id: str = "player") -> str:
        """Компактный текст-блок cognition NPC. Пустая строка = нечего сказать.
        Ошибки чтения — warning + пусто (наблюдаемая деградация, не краш)."""
        try:
            session = self._memory.get_dialogue_session(
                self._get_campaign_id(), npc_id, partner_id=partner_id
            )
        except Exception as e:
            logger.warning(f"[COG_CTX] resolve failed for {npc_id}: {e}")
            return ""
        lines: list = []
        open_claims = [
            c for c in getattr(session, "claims", []) if getattr(c, "status", "") == "open"  # noqa: ENIGMA002
        ]
        if open_claims:
            lines.append("Что NPC слышал в разговоре (утверждения собеседника):")
            for c in open_claims[-5:]:
                lines.append(f"- {c.speaker} {c.text}")
        open_q = [
            q for q in getattr(session, "open_questions", []) if not getattr(q, "answered", True)  # noqa: ENIGMA002
        ]
        if open_q:
            lines.append("Открытые вопросы без ответа:")
            for q in open_q[-3:]:
                lines.append(f"- {q.text} (спросил {q.asked_by})")
        return "\n".join(lines)
