"""S366 — патчер routes_chronicle.py.
Добавляет 3 endpoint'а:
1. POST /chronicle/{campaign_id}/{npc_id}/link-causes (детекция + валидация, не пишет в causes).
2. POST /chronicle/{campaign_id}/{npc_id}/resolve-cause-candidate (ACCEPT/REJECT_SILENT).
3. POST /chronicle/{campaign_id}/{npc_id}/record-npc-belief (явная запись NPC-убеждения).

Принципы (вердикт Мастера):
- ACCEPT только добавляет CauseRef в effect.causes — НЕ создаёт NpcCausalBelief.
- REJECT_SILENT только помечает REJECTED — ничего больше.
- MISTAKEN — только явное решение автора в record-npc-belief, не выводится автоматически.
- Idempotency: повторный вызов не создаёт дублей.
"""
from pathlib import Path
from dataclasses import replace

ROUTES_PY = Path("backend/app/api/routes_chronicle.py")
text = ROUTES_PY.read_text(encoding="utf-8")
orig_len = len(text)

# === Патч 1: импорты S366 ===
# Ищем существующий импорт BiographyDecomposer и добавляем S366-импорты
MARK1 = "from app.services.chronicle.biography_decomposer import BiographyDecomposer\n"
assert MARK1 in text, "Маркер 1 (BiographyDecomposer import) не найден"

ADD1 = """from app.services.chronicle.biography_decomposer import BiographyDecomposer
from app.services.chronicle.causal_linker import CausalLinker, LinkResult
from app.domain.chronicle import (
    BeliefGrounding,
    CandidateBasis,
    CandidateStatus,
    CauseCandidate,
    CauseKind,
    CauseRef,
    NpcCausalBelief,
    EntryProvenance,
    make_candidate_id,
    make_belief_id,
)
from dataclasses import replace as _dc_replace
"""
text = text.replace(MARK1, ADD1, 1)

# === Патч 2: 3 endpoint'а в конец файла ===
# Используем последний известный endpoint как маркер (get_current_projection)
MARK2 = 'async def get_current_projection() -> Dict[str, Any]:\n'
assert MARK2 in text, "Маркер 2 (get_current_projection) не найден"

# Найдём конец функции get_current_projection — следующий async def или EOF
end_idx = text.find('\n@', text.find(MARK2))
if end_idx == -1:
    end_idx = len(text)
# Найдём следующую декоратор/функцию после
next_marker = text.find('\n@', end_idx + 1)
if next_marker == -1:
    insert_pos = len(text)
else:
    insert_pos = next_marker

ADD2 = '''

# ===== S366: Причинные кандидаты и NPC-убеждения =====
# ТРИ ЗАПРЕТА (вердикт Мастера §1):
# 1. TEMPORAL_ORDER — детекция, не проставление.
# 2. ACCEPT — НЕ создаёт NpcCausalBelief.
# 3. MISTAKEN — НЕ выводится из отсутствия CauseRef.


class LinkCausesResponse(BaseModel):
    status: str
    validation_errors: list
    new_candidates: list
    existing_candidates: list
    truncated: bool
    truncation_reason: str
    stats: dict


class ResolveCandidateRequest(BaseModel):
    candidate_id: str
    resolution: str  # "ACCEPT" | "REJECT_SILENT"


class RecordBeliefRequest(BaseModel):
    believer_id: str
    effect_entry_id: str
    alleged_cause_entry_id: str
    alleged_cause_kind: str  # CauseKind value
    grounding: str = "UNVERIFIED"  # BeliefGrounding value
    provenance: str = "LLM_DRAFT"  # EntryProvenance value
    confidence: float | None = None


@chronicle_router.post("/chronicle/{campaign_id}/{npc_id}/link-causes")
async def link_causes(campaign_id: str, npc_id: str) -> Dict[str, Any]:
    """S366: детекция причинных кандидатов + валидация существующих causes.
    НЕ проставляет causes. НЕ создаёт NpcCausalBelief. Idempotent.

    Возвращает:
    - validation_errors: список нарушений (INV-CANON-CAUSE-REF, VALIDATION_WARNING для white_spot_id).
    - new_candidates: новые CauseCandidate для рассмотрения автором (PENDING).
    - existing_candidates: уже существующие кандидаты в документе.
    - truncated: всегда False (лимит 5 на entry обрабатывается внутри detect_candidates).
    """
    store = _get_store()
    doc = store.load_canonical(npc_id) or store.load_draft(campaign_id, npc_id)
    if doc is None:
        return {"status": "NOT_FOUND", "error": f"chronicle {npc_id} not found"}

    linker = CausalLinker()
    result: LinkResult = linker.link(doc)

    # Сохраняем новых PENDING-кандидатов в документ (не в causes!)
    if result.new_candidates:
        updated_candidates = tuple(doc.cause_candidates) + result.new_candidates
        doc = _dc_replace(doc, cause_candidates=updated_candidates)
        store.save_canonical(doc) if doc.canonical else store.save_draft(doc, campaign_id)

    return {
        "status": "OK",
        "validation_errors": [
            {"entry_id": ve.entry_id, "error_code": ve.error_code, "message": ve.message}
            for ve in result.validation_errors
        ],
        "new_candidates": [
            {
                "candidate_id": c.candidate_id,
                "effect_entry_id": c.effect_entry_id,
                "candidate_entry_id": c.candidate_entry_id,
                "candidate_kind": c.candidate_kind.value,
                "basis": c.basis.value,
                "rationale": c.rationale,
                "status": c.status.value,
            }
            for c in result.new_candidates
        ],
        "existing_candidates": [
            {
                "candidate_id": c.candidate_id,
                "effect_entry_id": c.effect_entry_id,
                "candidate_entry_id": c.candidate_entry_id,
                "candidate_kind": c.candidate_kind.value,
                "basis": c.basis.value,
                "rationale": c.rationale,
                "status": c.status.value,
            }
            for c in result.existing_candidates
        ],
        "truncated": result.truncated,
        "truncation_reason": result.truncation_reason,
        "stats": result.stats,
    }


@chronicle_router.post("/chronicle/{campaign_id}/{npc_id}/resolve-cause-candidate")
async def resolve_cause_candidate(
    campaign_id: str, npc_id: str, req: ResolveCandidateRequest
) -> Dict[str, Any]:
    """S366: явное решение автора по кандидату.
    - ACCEPT → добавляет CauseRef(cause_kind, origin_ref=candidate_entry_id) в effect.causes.
    - REJECT_SILENT → кандидат → REJECTED, ничего больше.
    НЕ создаёт NpcCausalBelief (запрет 2, §1 Мастера).
    Idempotent: повторный вызов с тем же candidate_id и resolution — no-op.
    Ошибка 400 если кандидат уже разрешён с другим resolution.
    """
    if req.resolution not in ("ACCEPT", "REJECT_SILENT"):
        return {"status": "BAD_REQUEST", "error": f"resolution must be ACCEPT or REJECT_SILENT, got {req.resolution!r}"}

    store = _get_store()
    doc = store.load_canonical(npc_id) or store.load_draft(campaign_id, npc_id)
    if doc is None:
        return {"status": "NOT_FOUND", "error": f"chronicle {npc_id} not found"}

    # Найти кандидатa
    cand = None
    for c in doc.cause_candidates:
        if c.candidate_id == req.candidate_id:
            cand = c
            break
    if cand is None:
        return {"status": "NOT_FOUND", "error": f"candidate {req.candidate_id} not found"}

    # Idempotency: уже разрешён?
    if cand.status is CandidateStatus.ACCEPTED:
        if req.resolution == "ACCEPT":
            return {"status": "OK", "already": "ACCEPTED", "updated_entry_id": cand.effect_entry_id}
        else:
            return {"status": "BAD_REQUEST", "error": f"candidate {req.candidate_id} already ACCEPTED, cannot REJECT_SILENT"}
    if cand.status is CandidateStatus.REJECTED:
        if req.resolution == "REJECT_SILENT":
            return {"status": "OK", "already": "REJECTED"}
        else:
            return {"status": "BAD_REQUEST", "error": f"candidate {req.candidate_id} already REJECTED, cannot ACCEPT"}

    # Найти effect entry
    effect = None
    for e in doc.entries:
        if e.entry_id == cand.effect_entry_id:
            effect = e
            break
    if effect is None:
        return {"status": "BAD_REQUEST", "error": f"effect_entry_id {cand.effect_entry_id} not found in document"}

    if req.resolution == "ACCEPT":
        # Добавить CauseRef в effect.causes (без дублей)
        new_cause = CauseRef(cause_kind=cand.candidate_kind, origin_ref=cand.candidate_entry_id)
        existing_refs = {(c.cause_kind, c.origin_ref) for c in effect.causes}
        if (new_cause.cause_kind, new_cause.origin_ref) in existing_refs:
            # CauseRef уже есть (например, проставлен вручную) — просто пометить ACCEPTED
            new_causes = effect.causes
        else:
            new_causes = effect.causes + (new_cause,)
        # Заменить entry в документе
        new_entries = tuple(
            _dc_replace(e, causes=new_causes) if e.entry_id == effect.entry_id else e
            for e in doc.entries
        )
        # Пометить кандидатa ACCEPTED
        new_cands = tuple(
            _dc_replace(c, status=CandidateStatus.ACCEPTED) if c.candidate_id == cand.candidate_id else c
            for c in doc.cause_candidates
        )
        doc = _dc_replace(doc, entries=new_entries, cause_candidates=new_cands)
    else:  # REJECT_SILENT
        new_cands = tuple(
            _dc_replace(c, status=CandidateStatus.REJECTED) if c.candidate_id == cand.candidate_id else c
            for c in doc.cause_candidates
        )
        doc = _dc_replace(doc, cause_candidates=new_cands)

    # Сохранить
    store.save_canonical(doc) if doc.canonical else store.save_draft(doc, campaign_id)

    return {
        "status": "OK",
        "resolution": req.resolution,
        "candidate_id": req.candidate_id,
        "updated_entry_id": cand.effect_entry_id if req.resolution == "ACCEPT" else None,
    }


@chronicle_router.post("/chronicle/{campaign_id}/{npc_id}/record-npc-belief")
async def record_npc_belief(
    campaign_id: str, npc_id: str, req: RecordBeliefRequest
) -> Dict[str, Any]:
    """S366: явная запись NPC-убеждения о причинной связи.
    НЕ мутирует ChronicleEntry.causes (СЛОЙ 1). Записывает в doc.npc_beliefs (СЛОЙ 2).
    MISTAKEN — только явное решение автора (запрет 3: не выводится автоматически из отсутствия CauseRef).

    Валидация:
    - believer_id не пустой.
    - effect_entry_id и alleged_cause_entry_id существуют в doc.entries.
    - alleged_cause_kind ∈ CauseKind.
    - grounding ∈ BeliefGrounding.
    - provenance/confidence — по контракту ChronicleEntry (LLM_DRAFT → confidence обязателен).
    """
    try:
        cause_kind = CauseKind(req.alleged_cause_kind)
        grounding = BeliefGrounding(req.grounding)
        provenance = EntryProvenance(req.provenance)
    except ValueError as e:
        return {"status": "BAD_REQUEST", "error": f"invalid enum value: {e}"}

    store = _get_store()
    doc = store.load_canonical(npc_id) or store.load_draft(campaign_id, npc_id)
    if doc is None:
        return {"status": "NOT_FOUND", "error": f"chronicle {npc_id} not found"}

    entry_ids = {e.entry_id for e in doc.entries}
    if req.effect_entry_id not in entry_ids:
        return {"status": "BAD_REQUEST", "error": f"effect_entry_id {req.effect_entry_id} not in document"}
    if req.alleged_cause_entry_id not in entry_ids:
        return {"status": "BAD_REQUEST", "error": f"alleged_cause_entry_id {req.alleged_cause_entry_id} not in document"}

    # Минимальная believer-валидация: believer_id не пустой (full roster-check — за пределами S366)
    if not req.believer_id:
        return {"status": "BAD_REQUEST", "error": "believer_id must not be empty"}

    # Idempotency: если уже есть belief с тем же (believer, effect, alleged_cause) — обновляем
    belief_id = make_belief_id(req.believer_id, req.effect_entry_id, req.alleged_cause_entry_id)
    try:
        new_belief = NpcCausalBelief(
            believer_id=req.believer_id,
            effect_entry_id=req.effect_entry_id,
            alleged_cause_entry_id=req.alleged_cause_entry_id,
            alleged_cause_kind=cause_kind,
            grounding=grounding,
            provenance=provenance,
            confidence=req.confidence,
        )
    except ValueError as e:
        return {"status": "BAD_REQUEST", "error": f"belief validation failed: {e}"}

    # Replace existing or append
    existing_beliefs = list(doc.npc_beliefs)
    replaced = False
    for i, b in enumerate(existing_beliefs):
        if (b.believer_id == req.believer_id
                and b.effect_entry_id == req.effect_entry_id
                and b.alleged_cause_entry_id == req.alleged_cause_entry_id):
            existing_beliefs[i] = new_belief
            replaced = True
            break
    if not replaced:
        existing_beliefs.append(new_belief)
    doc = _dc_replace(doc, npc_beliefs=tuple(existing_beliefs))

    store.save_canonical(doc) if doc.canonical else store.save_draft(doc, campaign_id)

    return {
        "status": "OK",
        "belief_id": belief_id,
        "action": "UPDATED" if replaced else "CREATED",
        "believer_id": req.believer_id,
        "effect_entry_id": req.effect_entry_id,
        "alleged_cause_entry_id": req.alleged_cause_entry_id,
        "grounding": grounding.value,
    }
'''
text = text[:insert_pos] + ADD2 + text[insert_pos:]

ROUTES_PY.write_text(text, encoding="utf-8")
print(f"OK routes_chronicle.py: 2 patches applied (orig={orig_len}b, new={len(text)}b, delta=+{len(text)-orig_len}b)")
