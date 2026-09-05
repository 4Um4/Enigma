# backend/app/services/memory/conclusion_engine.py
"""
Назначение: BC-1/ADR-O-381 — pure-движок EXPERIENCE→CONCLUSION. Вход —
    ТОЛЬКО события EXPERIENCE_DELTA_COMMITTED текущего тика (NO-VACUUM:
    досье §13.1 — «BC-1 не имеет права создавать conclusion из отсутствия
    нового опыта»; пустой вход → пустой выход, состояние не читается).
    Правило v1: авторизованная threat-дельта → вывод IS_DANGEROUS об
    источнике угрозы. Pure: ноль IO/LLM/мутаций/writers.
Зависимости: app.domain.conclusions; logging, typing.
Основные сущности: THREAT_CONCLUSION_THRESHOLD, parse_owner_from_trace_id,
    generate_conclusion_proposals.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

from app.domain.conclusions import (
    CONCLUSION_SOURCE_DIRECT,
    ConclusionPredicate,
    ConclusionProposal,
)

logger = logging.getLogger(__name__)

# Порог пережитой угрозы для формирования вывода (v1, threat-правило).
# Константа модуля = калибруемая policy, не онтология (прецедент
# WEAPON_ARCHETYPES/ADR-O-378: magic numbers запрещены; Lab — потом).
THREAT_CONCLUSION_THRESHOLD = 0.5

# Формат trace_id S115-паттерна (reaction_subscriber:253/:364):
# "{event.id}:{owner}:{channel}" — канал player|witness. Средний сегмент
# = owner пережитого опыта. Неузнаваемый формат → skip + warning (не crash).
_TRACE_CHANNEL_PLAYER = "player"
_TRACE_CHANNEL_WITNESS = "witness"

# Источник угрозы в E2.0-b-проводке (THREATEN/ATTACK) — игрок. Это
# политика правила v1, не npc_id-хардкод affinity (запрет S209 — про
# affinity-таблицы; mechanical-источник задаётся проводкой реакции).
_CONCLUSION_SUBJECT_PLAYER = "player"


def parse_owner_from_trace_id(trace_id: str) -> Optional[str]:
    """Владелец опыта из S115-формата "{event.id}:{owner}:{channel}".

    event.id — UUID (содержит '-', сегмент неразрушим). Неузнаваемое —
    None (вызывающий пропускает трейс; хрупкий парсинг не должен
    убивать фазу).
    """
    parts = trace_id.split(":")
    if len(parts) < 3:
        return None
    owner = parts[1]
    if not owner:
        return None
    return owner


def generate_conclusion_proposals(
    experience_delta_events: Iterable[Any],
) -> List[ConclusionProposal]:
    """Pure: события EXPERIENCE_DELTA_COMMITTED → proposals.

    Правило v1 (threat): event.payload["field"] == "threat_gradient" И
    value >= THREAT_CONCLUSION_THRESHOLD → proposal
    (owner=переживший, subject=player, IS_DANGEROUS, confidence=value,
    evidence=(causal_parent,), trace_id, causal_parent).

    NO-VACUUM: вход пуст → []. Никакого чтения состояния/стора/баз.
    Не-мусорные события без правила → пропускаются молча (не ошибка).
    """
    proposals: List[ConclusionProposal] = []
    for event in experience_delta_events:
        payload: Dict[str, Any] = getattr(event, "payload", None) or {}
        field = payload.get("field")
        if field != "threat_gradient":
            continue
        try:
            value = float(payload.get("value", 0.0))
        except (TypeError, ValueError):
            # L4 (INV-SILENT-FAILURE): отказ наблюдаем; мусорное value —
            # аномалия данных события: skip с диагнозом, не тихий провал
            logger.warning(
                "[CONCLUSION_ENGINE] невалидное value в дельте опыта "
                f"(trace={payload.get('trace_id', '?')}) — skip"
            )
            continue
        if value < THREAT_CONCLUSION_THRESHOLD:
            continue

        trace_id = str(payload.get("trace_id", ""))
        causal_parent = str(payload.get("causal_parent", ""))
        owner_id = parse_owner_from_trace_id(trace_id)
        if owner_id is None:
            logger.warning(
                f"[CONCLUSION_ENGINE] trace_id без owner-сегмента — skip: {trace_id}"
            )
            continue

        proposals.append(
            ConclusionProposal(
                owner_id=owner_id,
                subject=_CONCLUSION_SUBJECT_PLAYER,
                predicate=ConclusionPredicate.IS_DANGEROUS,
                object="",
                confidence=value,
                evidence=(causal_parent,) if causal_parent else (),
                trace_id=trace_id,
                causal_parent=causal_parent,
                source=CONCLUSION_SOURCE_DIRECT,
                rationale="threat_rule_v1",
            )
        )
    return proposals
