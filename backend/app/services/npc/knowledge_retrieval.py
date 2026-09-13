# path: /project/backend/app/services/npc/knowledge_retrieval.py
# Назначение: M1/P4 (ТЗ «Таверна тайн», вердикт Мастера 2026-09-12) —
#   чистый reader над narrative_cache: по SubjectRef вопроса находит
#   знание, которым NPC УЖЕ обладает. Не создаёт, не мутирует, не
#   инферит possession (L-P4: Retrieval Is Observation). TruthState
#   НЕ участвует (TRUTH ≠ KNOWLEDGE). Пустой кортеж = честное отсутствие.
# Зависимости: app.models.npc_state (EventMemory, NPCState),
#   app.domain.subject_ref (SubjectRef, SubjectKind)
# Основные сущности: MatchReason, KnowledgeItem, retrieve_knowledge
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple

from app.domain.subject_ref import SubjectKind, SubjectRef
from app.models.npc_state import NPCState


class MatchReason(Enum):
    """Закрытый реестр причин выбора кандидата. Каждая — объяснимая
    связь между SubjectRef и уже имеющимся знанием NPC. Не свободный
    текст (Мастер: семантическая грязь «related/maybe» запрещена).
    EVENT_NP — отложен до production-доказательства необходимости."""

    EXACT_SECRET = "exact_secret"  # subject_id напрямую указывает на этот факт
    PARTICIPANT = "participant"    # subject — NPC, участвующий в этом факте
    CANON_TOPIC = "canon_topic"    # subject — канон-тема этого факта


@dataclass(frozen=True)
class KnowledgeItem:
    """Boundary DTO (Мастер: P4 наблюдает SSOT, P5 работает с результатом
    наблюдения). Извлечённые immutable поля — НЕ ручка к EventMemory.
    Живёт только в стеке вызова P4→P5; не хранится, не персистится,
    не является possession-записью."""

    secret_id: str         # идентичность ФАКТА канона
    summary: str           # что NPC знает (канон-текст или origin-текст)
    importance: float      # текущая важность (для P5-приоритизации)
    match_reason: MatchReason


def retrieve_knowledge(
    npc_state: NPCState,
    subject: SubjectRef,
) -> Tuple[KnowledgeItem, ...]:
    """L-P4: Retrieval Is Observation. Чистая функция: по SubjectRef
    вопроса возвращает знание, УЖЕ существующее в narrative_cache
    данного NPC. Не создаёт знание из тематического совпадения,
    не читает TruthState, не мутирует вход. Пустой кортеж = честное
    «NPC не обладает релевантным знанием».

    Правила (категорийная лестница, детерминированная; без
    магических весов):
    1. EXACT_SECRET: subject_id == m.secret_id
    2. PARTICIPANT: subject (NPC) ∈ known_by этой памяти
    3. CANON_TOPIC: subject_id указывает на секрет, чья topics-тема
       совпала при P3-резолве — уже материализована в m.secret_id

    Фильтры:
    - m.secret_id is None → пропустить (не канон-знание)
    - m.stage == FORGOTTEN → пропустить (не помнит сейчас)
    - m.is_secret is False → пропустить (не секретное знание)
    """
    from app.models.npc_state import MemoryStage

    items: list[KnowledgeItem] = []
    for m in npc_state.narrative_cache:
        # Базовые фильтры: только живое секретное канон-знание
        if not m.secret_id:
            continue
        if m.stage == MemoryStage.FORGOTTEN:
            continue
        if not m.is_secret:
            continue

        reason = _match(m, subject)
        if reason is not None:
            items.append(
                KnowledgeItem(
                    secret_id=m.secret_id,
                    summary=m.summary,
                    importance=m.importance,
                    match_reason=reason,
                )
            )
    return tuple(items)


def _match(m, subject: SubjectRef) -> MatchReason | None:
    """Детерминированная категорийная лестница. Первое совпадение —
    итог. Порядок: EXACT_SECRET > PARTICIPANT > CANON_TOPIC."""

    # 1. EXACT_SECRET: subject_id прямо указывает на этот факт
    #    (P3 уже резолвнул тему в secret_id)
    if subject.subject_id and subject.subject_id == m.secret_id:
        return MatchReason.EXACT_SECRET

    # 2. PARTICIPANT: subject — NPC; этот NPC в known_by памяти
    #    (круг осведомлённых данным знанием)
    if subject.kind is SubjectKind.NPC and subject.subject_id:
        if subject.subject_id in m.known_by:
            return MatchReason.PARTICIPANT

    # 3. CANON_TOPIC: subject резолвнулся в секрет (P3); эта память
    #    несёт тот же secret_id (тематическая связь уже материализована)
    if subject.kind is SubjectKind.CANON_TOPIC and subject.subject_id:
        if subject.subject_id == m.secret_id:
            return MatchReason.CANON_TOPIC

    return None
