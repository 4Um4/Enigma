"""S366 — патчер domain/chronicle.py.
Применяет 3 точечных изменения через детерминированные маркеры.
Не трогает существующий код — только добавляет.
"""
import sys
from pathlib import Path

CHRONICLE_PY = Path("backend/app/domain/chronicle.py")
text = CHRONICLE_PY.read_text(encoding="utf-8")
orig_len = len(text)

# === Патч 1: entry_kind_to_cause_kind() после CauseKind enum ===
MARK1 = '    UNKNOWN = "UNKNOWN"  # «причина не определена» — легальный ответ автора\n'
assert MARK1 in text, "Маркер 1 (CauseKind.UNKNOWN) не найден"

ADD1 = '''

# S366: явный детерминированный маппер EntryKind → CauseKind.
# Объявлен явно, не угадывается (вердикт Мастера по ADR v4 §3).
# 4 из 10 EntryKind имеют CauseKind. Остальные (LOCATION, EFFECT, BELIEF_SEED,
# KNOWLEDGE_LINK, PORTRET, DESIRE_SEED) не имеют прямого CauseKind — для них
# S366 не генерирует кандидата (зафиксировано как несовместимость контракта).
def entry_kind_to_cause_kind(entry_kind: "EntryKind") -> "Optional[CauseKind]":
    """Явное соответствие типа записи → типу основания (CauseRef.cause_kind).
    Возвращает None для EntryKind без соответствующего CauseKind.
    """
    return {
        EntryKind.EVENT: CauseKind.EVENT,
        EntryKind.RELATIONSHIP: CauseKind.RELATIONSHIP,
        EntryKind.TRAIT_SEED: CauseKind.TRAIT,
        EntryKind.OBSERVATION: CauseKind.OBSERVATION,
    }.get(entry_kind)
'''

text = text.replace(MARK1, MARK1 + ADD1, 1)

# === Патч 2: 3 enum + 2 dataclass + 2 ID-генератора после WhiteSpot ===
MARK2 = '    resolution_ref: Optional[str] = None  # npc_id после RESOLVED_AS_NPC\n    created_from_entry: Optional[str] = None\n'
assert MARK2 in text, "Маркер 2 (WhiteSpot end) не найден"

ADD2 = '''

# ===== S366: Причинные кандидаты и NPC-убеждения =====
# АРХИТЕКТУРНОЕ РАЗДЕЛЕНИЕ (мини-ADR v6, вердикт Мастера):
# СЛОЙ 1 — объективная причинность: ChronicleEntry.causes (существующий)
# СЛОЙ 2 — субъективное убеждение NPC: ChronicleDocument.npc_beliefs (новое)
# СЛОЙ 3 — кандидат-вопрос автору: ChronicleDocument.cause_candidates (новое)
# СЛОЙ 4 — действие автора: отдельные endpoint'ы (link-causes, resolve, record-belief)
#
# ТРИ ЗАПРЕТА (вердикт Мастера §1):
# 1. хронологический порядок → причинность — запрещён (TEMPORAL_ORDER только детекция)
# 2. автор подтвердил факт → NPC об этом знает — запрещён (ACCEPT не создаёт belief)
# 3. факт не записан → убеждение NPC ошибочно — запрещён (MISTAKEN не выводится автоматически)


class BeliefGrounding(str, Enum):
    """Обоснованность NPC-убеждения о причинной связи (СЛОЙ 2).
    MISTAKEN — только явное решение автора при наличии основания;
    НЕ выводится автоматически из отсутствия CauseRef в effect.causes."""
    GROUNDED = "GROUNDED"      # совпадает с объективной причиной (есть CauseRef в effect.causes)
    MISTAKEN = "MISTAKEN"      # противоречит известным фактам (явное решение автора)
    UNVERIFIED = "UNVERIFIED"  # факт не подтверждён, но и не противоречит


class CandidateBasis(str, Enum):
    """Детерминированные признаки детекции кандидатов (СЛОЙ 3).
    НИ ОДИН из них НЕ доказывает причинность — только основание для вопроса автору.

    SPAN_OVERLAP — не реализован: нет CauseKind.PORTRET (зафиксировано как
    несовместимость контракта — ver. 1)."""
    TEMPORAL_ORDER = "TEMPORAL_ORDER"        # EVENT M<N (хронология — НЕ причина)
    TARGET_HINT_MATCH = "TARGET_HINT_MATCH"  # EFFECT.target_hint == RELATIONSHIP.target_hint


class CandidateStatus(str, Enum):
    """Жизненный цикл кандидата. Переходы: PENDING → ACCEPTED | REJECTED."""
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class NpcCausalBelief:
    """СЛОЙ 2: NPC считает entry → entry причинной связью. Может быть ошибочным.

    Не мутирует ChronicleEntry.causes (СЛОЙ 1). Записывается отдельным действием автора
    (POST /record-npc-belief), НЕ выводится автоматически из ACCEPT причинного кандидата.

    Применяет ТЕ ЖЕ правила provenance/confidence, что и ChronicleEntry
    (валидатор :227-231): LLM_DRAFT обязан нести confidence; AUTHOR_* не хранят.
    """
    believer_id: str                            # NPC, держащий убеждение
    effect_entry_id: str                        # entry_id следствия (в текущем документе)
    alleged_cause_entry_id: str                 # entry_id предполагаемой причины (в текущем документе)
    alleged_cause_kind: CauseKind               # из существующего enum, без расширения
    grounding: BeliefGrounding = BeliefGrounding.UNVERIFIED
    provenance: EntryProvenance = EntryProvenance.LLM_DRAFT
    confidence: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.believer_id:
            raise ValueError("NpcCausalBelief: believer_id пуст")
        if self.effect_entry_id == self.alleged_cause_entry_id:
            raise ValueError("NpcCausalBelief: effect и alleged_cause — одна запись")
        if self.provenance is EntryProvenance.LLM_DRAFT and self.confidence is None:
            raise ValueError("NpcCausalBelief LLM_DRAFT обязан нести confidence (гипотеза)")
        if self.provenance in (EntryProvenance.AUTHOR_CONFIRMED, EntryProvenance.AUTHOR_AUTHORED):
            if self.confidence is not None:
                raise ValueError("NpcCausalBelief AUTHOR_* не хранит confidence — канон не гипотеза")
        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            raise ValueError("NpcCausalBelief confidence вне [0, 1]")


@dataclass(frozen=True)
class CauseCandidate:
    """СЛОЙ 3: детекция возможной причинной связи. НЕ проставляет causes. Ждёт явного решения автора.

    Idempotency: candidate_id детерминирован (effect+candidate+basis), повторная детекция
    не создаёт дубликат. REJECTED не возобновляется без изменения данных.
    """
    candidate_id: str
    effect_entry_id: str                        # entry, в causes[] которого идёт запись (при ACCEPT)
    candidate_entry_id: str                     # существующая запись-кандидат (основание)
    candidate_kind: CauseKind                   # из существующего enum, без расширения
    basis: CandidateBasis
    rationale: str                              # объяснение для автора (детерминированное)
    status: CandidateStatus = CandidateStatus.PENDING

    def __post_init__(self) -> None:
        if not self.candidate_id:
            raise ValueError("CauseCandidate: candidate_id пуст")
        if self.effect_entry_id == self.candidate_entry_id:
            raise ValueError("CauseCandidate: effect и candidate — одна запись")
        if not self.rationale:
            raise ValueError("CauseCandidate: rationale пуст")


def make_candidate_id(effect_entry_id: str, candidate_entry_id: str, basis: CandidateBasis) -> str:
    """Детерминированный id кандидата → idempotency: повторная детекция не создаёт дубль."""
    return f"{effect_entry_id}#cand-{basis.value}-{candidate_entry_id}"


def make_belief_id(believer_id: str, effect_entry_id: str, alleged_cause_entry_id: str) -> str:
    """Детерминированный id NPC-убеждения → idempotency при повторной записи."""
    return f"{believer_id}#belief-{effect_entry_id}-{alleged_cause_entry_id}"
'''

text = text.replace(MARK2, MARK2 + ADD2, 1)

# === Патч 3: 2 новых поля в ChronicleDocument после event_groups ===
MARK3 = '    event_groups: Tuple[Tuple[str, ...], ...] = ()\n'
assert MARK3 in text, "Маркер 3 (event_groups) не найден"

ADD3 = '''    event_groups: Tuple[Tuple[str, ...], ...] = ()
    # S366: субъективные причинные убеждения NPC (СЛОЙ 2). Не мутирует causes.
    # Пусто по умолчанию → backward compat со старыми документами без этого поля.
    npc_beliefs: Tuple["NpcCausalBelief", ...] = ()
    # S366: причинные кандидаты для проверки автором (СЛОЙ 3). Не проставляет causes.
    # PENDING → ACCEPTED | REJECTED через POST /resolve-cause-candidate.
    cause_candidates: Tuple["CauseCandidate", ...] = ()
'''

text = text.replace(MARK3, ADD3, 1)

CHRONICLE_PY.write_text(text, encoding="utf-8")
print(f"OK chronicle.py: 3 patch applied (orig={orig_len}b, new={len(text)}b, delta=+{len(text)-orig_len}b)")
