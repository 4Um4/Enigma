"""path: /project/backend/app/services/npc/cognition_context.py

Назначение: Step 5 (вердикт Мастера) + COGNITIVE-CONTINUITY-01 — CognitionContextResolver:
    чистый READ-ONLY резолвер cognition-блока per-NPC. Единственный источник
    фактуры «что NPC слышал/знает» для ОБЕИХ путей порождения NPC-речи:
    VerbalizationContext (DialogueExecutor) и DMFrame (npc_contexts).
    STOP: не пишет Claims/Memory/TruthState/EpistemicStore; не store;
    не второй канал Claims→DM — один resolver, несколько потребителей.
    COGNITIVE-CONTINUITY-01: расширен чтением EpistemicStore (beliefs с provenance)
    и разрешением ID→имена. Не новый SSOT — read-only проекция существующих систем.
Зависимости: app.services.memory.memory_manager (инъекция, только чтение
    session-API), app.services.npc.epistemic_store (инъекция, только чтение).
Основные сущности: CognitionContextResolver.
"""

import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_PRED_TEXT = {
    "insulted": "оскорбил",
    "stole": "украл у",
    "attacked": "напал на",
    "helped": "помог",
    "asserts": "утверждал:",
    "name": "представился как",
}


class CognitionContextResolver:
    """Read-only проекция услышанного/знаемого NPC для cognition-каналов."""

    def __init__(
        self,
        memory_manager: Any,
        campaign_id_provider: Any = None,
        epistemic_store: Any = None,
        context_provider: Optional[Callable[[str], dict]] = None,
    ) -> None:
        self._memory = memory_manager
        self._get_campaign_id = campaign_id_provider or (lambda: "Open_road")
        # COGNITIVE-CONTINUITY-01: EpistemicStore (beliefs с provenance) + name resolver
        self._epistemic_store = epistemic_store
        self._get_context = context_provider  # Callable[[npc_id], dict] с "name" key

    def resolve_block(self, npc_id: str, partner_id: str = "player") -> str:
        """Компактный текст-блок cognition NPC. Пустая строка = нечего сказать.
        Ошибки чтения — warning + пусто (наблюдаемая деградация, не краш)."""
        lines: list = []

        # --- STM: claims + open_questions (существующее поведение) ---
        try:
            session = self._memory.get_dialogue_session(
                self._get_campaign_id(), npc_id, partner_id=partner_id
            )
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
        except Exception as e:
            logger.warning(f"[COG_CTX] STM resolve failed for {npc_id}: {e}")

        # --- COGNITIVE-CONTINUITY-01: EpistemicStore beliefs с provenance ---
        if self._epistemic_store is not None:
            epistemic_lines = self._format_beliefs(npc_id)
            if epistemic_lines:
                lines.append("Что NPC знает (убеждения с provenance):")
                lines.extend(epistemic_lines)

        return "\n".join(lines)

    def _format_beliefs(self, npc_id: str) -> list:
        """Читает EpistemicStore, форматирует beliefs с provenance и именами."""
        lines: list = []
        try:
            records = self._epistemic_store.get_all_for_agent(npc_id)
            # Фильтр: confidence >= 0.25, skip EXITS_TO (spatial noise)
            relevant = [
                r for r in records
                if r.confidence >= 0.25
                and r.proposition.predicate.value != "exits_to"
            ]
            for r in relevant[:5]:  # Топ-5 наиболее релевантных
                subj_name = self._resolve_name(r.proposition.subject_id)
                obj_name = self._resolve_name(r.proposition.object_id)
                pred_val = r.proposition.predicate.value if hasattr(r.proposition.predicate, "value") else str(r.proposition.predicate)
                pred_text = _PRED_TEXT.get(pred_val, pred_val)

                # ASSERTS — object это содержание (не имя)
                if pred_val == "asserts":
                    line = f"- {subj_name} {pred_text} \"{str(r.proposition.object_id)[:100]}\""
                else:
                    line = f"- {subj_name} {pred_text} {obj_name}"

                line += f" (уверенность: {r.confidence:.2f}"

                # Provenance
                if r.source_type == "direct_observation":
                    line += ", ты видел это сам"
                elif r.source_type == "testimony":
                    src_name = self._resolve_name(r.source_id)
                    line += f", тебе сообщил(а) {src_name}"
                    if r.original_source_id and r.original_source_id != r.source_id:
                        orig_name = self._resolve_name(r.original_source_id)
                        line += f", исходный источник — {orig_name}"

                line += ")"
                lines.append(line)
        except Exception as e:
            logger.warning(f"[COG_CTX] epistemic read failed for {npc_id}: {e}")
        return lines

    def _resolve_name(self, npc_id: str) -> str:
        """Разрешает ID в игровое имя через context_provider."""
        if self._get_context:
            try:
                ctx = self._get_context(npc_id)
                if ctx and ctx.get("name"):
                    return ctx["name"]
            except Exception as e:
                logger.warning(f"[COG_CTX] name resolve failed for {npc_id}: {e}")
        return npc_id