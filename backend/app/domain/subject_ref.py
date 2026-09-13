# path: /project/backend/app/domain/subject_ref.py
# Назначение: M1/P3 (ТЗ «Таверна тайн», коррекция Мастера 2026-09-12):
#   семантика ПРЕДМЕТА вопроса — ось, ортогональная SpeechAct (акт).
#   P3-граница: что игрок спрашивает и о чём; НЕ правда/знает/раскроет.
#   Unknown/unresolved — легальное состояние (N2: QUESTION переживает
#   неудачный резолв). ASKING != DISCOVERING (закон P3/P6).
# Зависимости: enum, dataclasses
# Основные сущности: SubjectKind, SubjectRef
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SubjectKind(Enum):
    """Ось предмета. Ортогональна речевому акту: QUESTION+NPC и
    QUESTION+CANON_TOPIC — один акт, разные предметы (коррекция Мастера:
    без ASK_SELF/ASK_OTHER-склейки и её комбинаторного взрыва)."""

    NPC = "npc"                      # резолвнутый субъект: name_forms/NPC-словарь
    CANON_TOPIC = "canon_topic"      # тема канона: topics-словрь секрета
    EVENT = "event"                  # событие (грубое NP; без онтологии событий)
    ENTITY = "entity"                # объект/артефакт быта (не канон)
    UNKNOWN = "unknown"              # легальное состояние: резолв не удался


@dataclass(frozen=True)
class SubjectRef:
    """Предмет вопроса. best-effort, non-authoritative: extractor не
    решает knows/reveals (P4/P5); hint сохраняется при нерезолве (N2)."""

    kind: SubjectKind = SubjectKind.UNKNOWN
    subject_id: str | None = None    # npc_id / topic_key / secret-мёрk; None при нерезолве
    subject_hint: str | None = None  # сырая NP-группа; переживает нерезолв

    @property
    def resolved(self) -> bool:
        return self.kind is not SubjectKind.UNKNOWN and self.subject_id is not None
