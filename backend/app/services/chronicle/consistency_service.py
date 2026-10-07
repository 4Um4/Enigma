"""
Сверка авторского плетения хроник (ADR-O-422, CCH-2.5).

Файл: backend/app/services/chronicle/consistency_service.py
Назначение: трёхуровневый read-only сверщик. Карточки автору — единственный
            исход для склеек/конфликтов; авто-резолюция запрещена.
Зависимости: app.domain.chronicle
Основные сущности: Finding, ConsistencyReport, ConsistencyService

Табу ADR-O-422: без авто-склейки; без записи в truth_state/config (предложения);
второго календарного модуля нет — только age_math-семантика.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

from app.domain.chronicle import (
    ChronicleDocument,
    ChronicleEntry,
    EntityRef,
    EntryKind,
)

# ── Карточки ────────────────────────────────────────────────────────────────
K_CONTRADICTION = "CONTRADICTION"
K_MERGE_CANDIDATE = "MERGE_CANDIDATE"
K_GAP = "GAP"
K_QUESTION = "QUESTION"
K_CANON_SYNC = "CANON_SYNC"
K_INFO = "INFO"


@dataclass(frozen=True)
class Finding:
    kind: str
    level: str  # "intra" | "cross" | "canon"
    message: str
    doc_refs: Tuple[Tuple[str, str], ...] = ()  # (npc_ref, entry_id)
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConsistencyReport:
    findings: Tuple[Finding, ...] = ()

    def by_kind(self, kind: str) -> Tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.kind == kind)


# ── Реестр канона (инъекция; API-слой собирает из файлов) ───────────────────


@dataclass(frozen=True)
class CanonicalRegistry:
    """Снимок канона игры для сверки. Сервис НИКОГДА не пишет в эти источники."""

    alias_to_npc: Dict[str, str] = field(default_factory=dict)   # name_forms → npc_id
    archetype_of: Dict[str, str] = field(default_factory=dict)   # npc_id → archetype
    secret_holders: Dict[str, FrozenSet[str]] = field(default_factory=dict)  # secret_id → holders
    secret_known_by: Dict[str, FrozenSet[str]] = field(default_factory=dict) # secret_id → known_by


# Закрытый словарь роль-хинтов (расширение = ревизия ADR-O-422)
_ROLE_HINTS: Dict[str, str] = {
    "стражник": "guard",
    "стражница": "guard",
    "стража": "guard",
    "кузнец": "blacksmith",
    "кули": "blacksmith",
    "служанка": "maid",
    "служанка-горничная": "maid",
    "трактирщик": "tavern_keeper",
    "хозяин таверны": "tavern_keeper",
    "вор": "thief",
    "гильдия воров": "thief",
    "торговец": "merchant",
    "купец": "merchant",
}


def _role_of_ref(ref: Optional[EntityRef], registry: CanonicalRegistry) -> Optional[str]:
    """Роль участника: archetype известного NPC; для неразрешённых имён —
    сначала канон-алиас (Торнин→tavern_keeper), затем словарь ролей."""
    if ref is None:
        return None
    if ref.ref_kind.value == "RESOLVED" and ref.npc_id:
        return registry.archetype_of.get(ref.npc_id)
    if ref.name_hint:
        alias = registry.alias_to_npc.get(ref.name_hint.lower())
        if alias:
            return registry.archetype_of.get(alias)
        low = ref.name_hint.lower()
        for hint, role in _ROLE_HINTS.items():
            if hint in low:
                return role
    return None


def _participants(entry: ChronicleEntry) -> List[EntityRef]:
    out = [entry.subject_id]
    if entry.object_id is not None:
        out.append(entry.object_id)
    return [r for r in out if r is not None]


class ConsistencyService:
    """Read-only сверщик. Registry инъекцией; документ — только чтение."""

    def check(
        self,
        docs: Sequence[ChronicleDocument],
        registry: CanonicalRegistry,
    ) -> ConsistencyReport:
        findings: List[Finding] = []
        for doc in docs:
            findings.extend(self._intra(doc))
        for i in range(len(docs)):
            for j in range(i + 1, len(docs)):
                findings.extend(self._cross(docs[i], docs[j], registry))
        for doc in docs:
            findings.extend(self._canon(doc, registry))
        return ConsistencyReport(findings=tuple(findings))

    # ── Уровень 1: внутри биографии ─────────────────────────────────────────

    def _intra(self, doc: ChronicleDocument) -> List[Finding]:
        out: List[Finding] = []
        dated = [(e.ordinal, e.historical_age) for e in doc.entries if e.historical_age is not None]
        dated.sort()

        for e in doc.entries:
            # Сбор открытых вопросов в отчёт (карточки UI)
            for q in e.open_questions:
                out.append(
                    Finding(
                        kind=K_QUESTION,
                        level="intra",
                        message=f"{doc.npc_ref}: открытый вопрос '{q.question_id}' ({q.target_span})",
                        doc_refs=((doc.npc_ref, e.entry_id),),
                        payload={"question_id": q.question_id},
                    )
                )
            # Временное окно (единая семантика с _window, ADR-O-422): правая
            # граница без следующего якоря — game_start_age («сейчас»), левая
            # без предыдущего — 0 (рождение).
            if e.historical_age is None and e.kind in (EntryKind.EVENT, EntryKind.EFFECT):
                window = self._window(e, doc)
                if window is not None:
                    lo, hi = window
                    out.append(
                        Finding(
                            kind=K_GAP,
                            level="intra",
                            message=(
                                f"{doc.npc_ref}: событие без даты между якорями "
                                f"{lo} и {hi} лет — предложенное окно [{lo}..{hi}]"
                            ),
                            doc_refs=((doc.npc_ref, e.entry_id),),
                            payload={"window": [lo, hi]},
                        )
                    )

        # Дубли внутри: тот же kind+subject+object и близкий возраст
        for i, a in enumerate(doc.entries):
            for b in doc.entries[i + 1:]:
                if a.kind is not b.kind or a.subject_id != b.subject_id or a.object_id != b.object_id:
                    continue
                if a.historical_age is None or b.historical_age is None:
                    continue
                if abs(a.historical_age - b.historical_age) <= 1:
                    out.append(
                        Finding(
                            kind=K_MERGE_CANDIDATE,
                            level="intra",
                            message=f"{doc.npc_ref}: похожие записи ({a.historical_age}/{b.historical_age})",
                            doc_refs=((doc.npc_ref, a.entry_id), (doc.npc_ref, b.entry_id)),
                        )
                    )
        return out

    # ── Уровень 2: между биографиями ────────────────────────────────────────

    def _cross(self, a: ChronicleDocument, b: ChronicleDocument, registry: CanonicalRegistry) -> List[Finding]:
        out: List[Finding] = []
        if a.game_start_age is None or b.game_start_age is None:
            return out  # без возрастов на старте математика невозможна (Vacuum)
        delta = a.game_start_age - b.game_start_age

        for ea in a.entries:
            if ea.historical_age is None and self._window(ea, a) is None:
                continue
            for eb in b.entries:
                if eb.historical_age is None and self._window(eb, b) is None:
                    continue
                if not self._time_compatible(ea, a, eb, b, delta):
                    continue
                shared = self._shared_roles(ea, eb, registry)
                if not shared:
                    continue
                out.append(
                    Finding(
                        kind=K_MERGE_CANDIDATE,
                        level="cross",
                        message=(
                            f"Кандидат на «одно событие»: {a.npc_ref}:{ea.kind.value} ↔ "
                            f"{b.npc_ref}:{eb.kind.value} (роли: {sorted(shared)})"
                        ),
                        doc_refs=((a.npc_ref, ea.entry_id), (b.npc_ref, eb.entry_id)),
                        payload={"shared_roles": sorted(shared)},
                    )
                )
        return out

    @staticmethod
    def _window(entry: ChronicleEntry, doc: ChronicleDocument) -> Optional[Tuple[int, int]]:
        """Окно недатированного события: между соседними якорями; правая граница
        без следующего якоря — game_start_age («сейчас» — легальный якорь, ADR-O-422);
        левая без предыдущего — 0 (рождение)."""
        dated = sorted((e.ordinal, e.historical_age) for e in doc.entries if e.historical_age is not None)
        prev = [ag for o, ag in dated if o < entry.ordinal]
        nxt = [ag for o, ag in dated if o > entry.ordinal]
        lo = max(prev) if prev else 0
        if nxt:
            hi = min(nxt)
        elif doc.game_start_age is not None:
            hi = doc.game_start_age
        else:
            return None
        if hi < lo:
            return None
        return (lo, hi)

    def _time_compatible(
        self,
        ea: ChronicleEntry,
        da: ChronicleDocument,
        eb: ChronicleEntry,
        db: ChronicleDocument,
        delta: int,
    ) -> bool:
        wa = self._window(ea, da) if ea.historical_age is None else (ea.historical_age, ea.historical_age)
        wb = self._window(eb, db) if eb.historical_age is None else (eb.historical_age, eb.historical_age)
        if wa is None or wb is None:
            return False
        # Окно B в «возрасте A»: сдвиг на delta (возраст A − возраст B на одном моменте)
        wb_in_a = (wb[0] + delta, wb[1] + delta)
        return wa[0] <= wb_in_a[1] and wb_in_a[0] <= wa[1]

    def _shared_roles(self, ea: ChronicleEntry, eb: ChronicleEntry, registry: CanonicalRegistry) -> FrozenSet[str]:
        """Роли ВТОРИЧНЫХ участников (object_id). Субъект-владелец хроники
        исключён: иначе «Люся» в обеих хрониках склеивает любые записи
        (калибровка S336: 34 мусорных кандидата из субъект-матчинга)."""
        def _roles(e: ChronicleEntry) -> FrozenSet[str]:
            roles = set()
            r_subj = _role_of_ref(e.subject_id, registry)
            if r_subj:
                roles.add(r_subj)
            o = e.object_id
            if o is not None:
                # self-reference (объект = владелец своей же хроники) не даёт
                # роли: это мусор LLM, иначе «Люся↔Люся» склеивает всё
                is_self = (
                    o.ref_kind.value == "RESOLVED"
                    and e.subject_id.ref_kind.value == "RESOLVED"
                    and o.npc_id == e.subject_id.npc_id
                )
                if not is_self:
                    r_obj = _role_of_ref(o, registry)
                    if r_obj:
                        roles.add(r_obj)
            return frozenset(roles)

        return _roles(ea) & _roles(eb)

    # ── Уровень 3: с каноном игры ───────────────────────────────────────────

    def _canon(self, doc: ChronicleDocument, registry: CanonicalRegistry) -> List[Finding]:
        out: List[Finding] = []
        for e in doc.entries:
            for ref in _participants(e):
                if ref.name_hint and ref.name_hint.lower() in registry.alias_to_npc:
                    npc_id = registry.alias_to_npc[ref.name_hint.lower()]
                    if ref.ref_kind.value != "RESOLVED":
                        out.append(
                            Finding(
                                kind=K_INFO,
                                level="canon",
                                message=(
                                    f"{doc.npc_ref}: «{ref.name_hint}» резолвится в канонного "
                                    f"NPC '{npc_id}' — предложи резолюцию ссылки"
                                ),
                                doc_refs=((doc.npc_ref, e.entry_id),),
                                payload={"npc_id": npc_id},
                            )
                        )
                elif ref.ref_kind.value == "RESOLVED" and ref.npc_id and ref.npc_id not in registry.archetype_of:
                    out.append(
                        Finding(
                            kind=K_CONTRADICTION,
                            level="canon",
                            message=f"{doc.npc_ref}: ссылка на несуществующего канонного NPC '{ref.npc_id}'",
                            doc_refs=((doc.npc_ref, e.entry_id),),
                        )
                    )
                elif ref.ref_kind.value == "UNKNOWN_PERSON" and ref.name_hint:
                    low = ref.name_hint.lower()
                    if low not in registry.alias_to_npc and not any(h in low for h in _ROLE_HINTS):
                        out.append(
                            Finding(
                                kind=K_QUESTION,
                                level="canon",
                                message=(
                                    f"{doc.npc_ref}: имя «{ref.name_hint}» не резолвится в канон — "
                                    f"создай NPC или оставь белым пятном"
                                ),
                                doc_refs=((doc.npc_ref, e.entry_id),),
                                payload={"name_hint": ref.name_hint},
                            )
                        )
            # Секретность: payload с is_secret/known_by (миграционные записи) vs truth_state
            if e.kind is EntryKind.EVENT and isinstance(e.payload.get("is_secret"), bool) and e.payload.get("is_secret"):
                sid = e.payload.get("secret_id")
                known = set(e.payload.get("known_by") or ())
                holders = registry.secret_known_by.get(str(sid))
                if holders is not None and known != set(holders):
                    out.append(
                        Finding(
                            kind=K_CANON_SYNC,
                            level="canon",
                            message=(
                                f"{doc.npc_ref}: known_by секрета '{sid}' расходится с каноном "
                                f"(хроника={sorted(known)}, канон={sorted(holders)})"
                            ),
                            doc_refs=((doc.npc_ref, e.entry_id),),
                            payload={"secret_id": sid},
                        )
                    )
        return out
