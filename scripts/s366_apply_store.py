"""S366 — патчер chronicle_store.py.
5 точечных изменений:
1. 2 новых ключа после _KEY_WHITE_SPOTS.
2. 6 новых констант-ключей для полей beliefs/candidates.
3. 4 функции-сериализатора (_belief_to/from, _candidate_to/from) после _cause_to.
4. 2 строки в _document_to (сериализация).
5. 2 строки в _document_from (десериализация).
6. Валидация dangling для npc_beliefs и cause_candidates.
Backward compat: поля с default=() — старые документы без ключа загружаются как пустой tuple.
"""
from pathlib import Path

STORE_PY = Path("backend/app/services/chronicle/chronicle_store.py")
text = STORE_PY.read_text(encoding="utf-8")
orig_len = len(text)

# === Патч 1: 2 новых ключа + 6 новых под-ключей после _KEY_WHITE_SPOTS ===
MARK1 = '_KEY_WHITE_SPOTS = "white_spots"\n'
assert MARK1 in text, "Маркер 1 (_KEY_WHITE_SPOTS) не найден"

ADD1 = '''_KEY_WHITE_SPOTS = "white_spots"
# S366: ключи сериализации для npc_beliefs и cause_candidates.
_KEY_NPC_BELIEFS = "npc_beliefs"
_KEY_CANDIDATES = "cause_candidates"
# Под-ключи NpcCausalBelief:
_KEY_BELIEVER = "believer_id"
_KEY_EFFECT_ENTRY = "effect_entry_id"
_KEY_ALLEGED_CAUSE = "alleged_cause_entry_id"
_KEY_ALLEGED_KIND = "alleged_cause_kind"
_KEY_GROUNDING = "grounding"
# Под-ключи CauseCandidate:
_KEY_CAND_ID = "candidate_id"
_KEY_CAND_EFFECT = "effect_entry_id"
_KEY_CAND_CAND = "candidate_entry_id"
_KEY_CAND_KIND = "candidate_kind"
_KEY_CAND_BASIS = "basis"
_KEY_CAND_RATIONALE = "rationale"
_KEY_CAND_STATUS = "status"
'''
text = text.replace(MARK1, ADD1, 1)

# === Патч 2: 4 функции-сериализатора после _cause_to ===
# Точный текст _cause_to (по археологии строка 144-145):
MARK2 = 'def _cause_to(cause: CauseRef) -> Dict[str, Any]:\n    return {_KEY_CAUSE_KIND: cause.cause_kind.value, _KEY_ORIGIN_REF: cause.origin_ref}\n'
assert MARK2 in text, "Маркер 2 (_cause_to) не найден"

ADD2 = '''

def _belief_to(b: "NpcCausalBelief") -> Dict[str, Any]:
    """Сериализация NpcCausalBelief. provenance/confidence — по контракту ChronicleEntry."""
    return {
        _KEY_BELIEVER: b.believer_id,
        _KEY_EFFECT_ENTRY: b.effect_entry_id,
        _KEY_ALLEGED_CAUSE: b.alleged_cause_entry_id,
        _KEY_ALLEGED_KIND: b.alleged_cause_kind.value,
        _KEY_GROUNDING: b.grounding.value,
        _KEY_PROVENANCE: b.provenance.value,
        _KEY_CONFIDENCE: b.confidence,
    }


def _belief_from(data: Dict[str, Any]) -> "NpcCausalBelief":
    """Десериализация NpcCausalBelief. fail-loud: обязательные поля — KeyError если нет.
    Backward compat: если grounding/provenance/confidence отсутствуют — используем defaults."""
    return NpcCausalBelief(
        believer_id=data[_KEY_BELIEVER],
        effect_entry_id=data[_KEY_EFFECT_ENTRY],
        alleged_cause_entry_id=data[_KEY_ALLEGED_CAUSE],
        alleged_cause_kind=_enum(CauseKind, data[_KEY_ALLEGED_KIND], _KEY_NPC_BELIEFS),
        grounding=_enum(BeliefGrounding, data.get(_KEY_GROUNDING, "UNVERIFIED"), _KEY_NPC_BELIEFS),
        provenance=_enum(EntryProvenance, data.get(_KEY_PROVENANCE, "LLM_DRAFT"), _KEY_NPC_BELIEFS),
        confidence=data.get(_KEY_CONFIDENCE),
    )


def _candidate_to(c: "CauseCandidate") -> Dict[str, Any]:
    """Сериализация CauseCandidate."""
    return {
        _KEY_CAND_ID: c.candidate_id,
        _KEY_CAND_EFFECT: c.effect_entry_id,
        _KEY_CAND_CAND: c.candidate_entry_id,
        _KEY_CAND_KIND: c.candidate_kind.value,
        _KEY_CAND_BASIS: c.basis.value,
        _KEY_CAND_RATIONALE: c.rationale,
        _KEY_CAND_STATUS: c.status.value,
    }


def _candidate_from(data: Dict[str, Any]) -> "CauseCandidate":
    """Десериализация CauseCandidate. fail-loud на обязательных полях."""
    return CauseCandidate(
        candidate_id=data[_KEY_CAND_ID],
        effect_entry_id=data[_KEY_CAND_EFFECT],
        candidate_entry_id=data[_KEY_CAND_CAND],
        candidate_kind=_enum(CauseKind, data[_KEY_CAND_KIND], _KEY_CANDIDATES),
        basis=_enum(CandidateBasis, data[_KEY_CAND_BASIS], _KEY_CANDIDATES),
        rationale=data[_KEY_CAND_RATIONALE],
        status=_enum(CandidateStatus, data.get(_KEY_CAND_STATUS, "PENDING"), _KEY_CANDIDATES),
    )
'''
text = text.replace(MARK2, MARK2 + ADD2, 1)

# === Патч 3: 2 строки сериализации в _document_to ===
MARK3 = '        _KEY_WHITE_SPOTS: [_white_spot_to(ws) for ws in doc.white_spots],\n'
assert MARK3 in text, "Маркер 3 (_KEY_WHITE_SPOTS в _document_to) не найден"

ADD3 = '''        _KEY_WHITE_SPOTS: [_white_spot_to(ws) for ws in doc.white_spots],
        # S366: сериализация новых полей (пустой tuple → пустой список в JSON).
        _KEY_NPC_BELIEFS: [_belief_to(b) for b in doc.npc_beliefs],
        _KEY_CANDIDATES: [_candidate_to(c) for c in doc.cause_candidates],
'''
text = text.replace(MARK3, ADD3, 1)

# === Патч 4: 2 строки десериализации в _document_from ===
MARK4 = '        white_spots=tuple(_white_spot_from(ws) for ws in data.get(_KEY_WHITE_SPOTS, ())),\n'
assert MARK4 in text, "Маркер 4 (white_spots в _document_from) не найден"

ADD4 = '''        white_spots=tuple(_white_spot_from(ws) for ws in data.get(_KEY_WHITE_SPOTS, ())),
        # S366: десериализация новых полей. .get(key, ()) → backward compat.
        npc_beliefs=tuple(_belief_from(b) for b in data.get(_KEY_NPC_BELIEFS, ())),
        cause_candidates=tuple(_candidate_from(c) for c in data.get(_KEY_CANDIDATES, ())),
'''
text = text.replace(MARK4, ADD4, 1)

# === Патч 5: валидация dangling для npc_beliefs и cause_candidates ===
# Вставляем ПОСЛЕ валидации causes (dangling cause origin_ref)
MARK5 = '                raise ValueError(f"{e.entry_id}: dangling cause origin_ref \'{c.origin_ref}\'")\n'
assert MARK5 in text, "Маркер 5 (dangling cause origin_ref) не найден"

ADD5 = '''                raise ValueError(f"{e.entry_id}: dangling cause origin_ref '{c.origin_ref}'")
    # S366: валидация dangling для NPC-убеждений и кандидатов.
    # Все ссылки должны указывать на entry_id в пределах ТЕКУЩЕГО документа.
    for b in doc.npc_beliefs:
        if b.effect_entry_id not in entry_ids:
            raise ValueError(f"dangling npc_belief: effect_entry_id '{b.effect_entry_id}' (believer={b.believer_id})")
        if b.alleged_cause_entry_id not in entry_ids:
            raise ValueError(f"dangling npc_belief: alleged_cause_entry_id '{b.alleged_cause_entry_id}' (believer={b.believer_id})")
    for c in doc.cause_candidates:
        if c.effect_entry_id not in entry_ids:
            raise ValueError(f"dangling candidate: effect_entry_id '{c.effect_entry_id}' (id={c.candidate_id})")
        if c.candidate_entry_id not in entry_ids:
            raise ValueError(f"dangling candidate: candidate_entry_id '{c.candidate_entry_id}' (id={c.candidate_id})")
'''
text = text.replace(MARK5, ADD5, 1)

STORE_PY.write_text(text, encoding="utf-8")
print(f"OK chronicle_store.py: 5 patches applied (orig={orig_len}b, new={len(text)}b, delta=+{len(text)-orig_len}b)")
