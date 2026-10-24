"""S366 — критический фикс validate_document.

ADD5 сломал структуру: оригинальные `if require_canonical_clean:` и
`_validate_knowledge_entry` (отступ 8 — тело for e) после вставки `for b`/`for c`
с отступом 4 стали интерпретироваться как ТЕЛО `for c in doc.cause_candidates:`,
которое НЕ выполняется при пустом cause_candidates → валидация канона
(запрет 1 LLM_DRAFT, открытый вопрос без резолюции) не вызывается.

Фикс: переписать весь блок между `for c in e.causes:` и `_validate_knowledge_entry`
с правильной структурой:
  for e in doc.entries:
      for ref in (...): ...
      for c in e.causes: ...
      if require_canonical_clean: ...     ← ОРИГИНАЛЬНЫЙ отступ 8 внутри for e
      if e.kind is EntryKind.KNOWLEDGE_LINK: _validate_knowledge_entry(...)  ← тоже

  # S366 — блок ПОСЛЕ for e (отступ 4):
  for b in doc.npc_beliefs: ...
  for c in doc.cause_candidates: ...
"""
from pathlib import Path

STORE_PY = Path("backend/app/services/chronicle/chronicle_store.py")
text = STORE_PY.read_text(encoding="utf-8")
orig_len = len(text)

# Точный сломанный блок (из текущего состояния, строки после for c in e.causes)
BROKEN = '''    for e in doc.entries:
        for ref in (e.subject_id, e.object_id):
            if ref is not None and ref.ref_kind.value == "WHITE_SPOT" and ref.white_spot_id not in ws_ids:
                raise ValueError(f"{e.entry_id}: dangling white_spot '{ref.white_spot_id}'")
        for c in e.causes:
            if c.origin_ref is not None and c.origin_ref not in entry_ids and c.origin_ref not in ws_ids:
                raise ValueError(f"{e.entry_id}: dangling cause origin_ref '{c.origin_ref}'")
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
        if require_canonical_clean:
            if e.provenance is EntryProvenance.LLM_DRAFT:
                raise ValueError(f"Запрет 1 (INV-LLM-NOT-SSOT): LLM_DRAFT '{e.entry_id}' в каноне {doc.chronicle_id}")
            for q in e.open_questions:
                if q.selected_option is None:
                    raise ValueError(f"Канон '{e.entry_id}': открытый вопрос '{q.question_id}' без резолюции автора")
        if e.kind is EntryKind.KNOWLEDGE_LINK:
            _validate_knowledge_entry(doc, e, entry_ids)
'''

FIXED = '''    for e in doc.entries:
        for ref in (e.subject_id, e.object_id):
            if ref is not None and ref.ref_kind.value == "WHITE_SPOT" and ref.white_spot_id not in ws_ids:
                raise ValueError(f"{e.entry_id}: dangling white_spot '{ref.white_spot_id}'")
        for c in e.causes:
            if c.origin_ref is not None and c.origin_ref not in entry_ids and c.origin_ref not in ws_ids:
                raise ValueError(f"{e.entry_id}: dangling cause origin_ref '{c.origin_ref}'")
        # S366 восстановлено: require_canonical_clean и _validate_knowledge_entry
        # были сломаны ADD5 (стали телом for c in doc.cause_candidates). Возвращены в for e.
        if require_canonical_clean:
            if e.provenance is EntryProvenance.LLM_DRAFT:
                raise ValueError(f"Запрет 1 (INV-LLM-NOT-SSOT): LLM_DRAFT '{e.entry_id}' в каноне {doc.chronicle_id}")
            for q in e.open_questions:
                if q.selected_option is None:
                    raise ValueError(f"Канон '{e.entry_id}': открытый вопрос '{q.question_id}' без резолюции автора")
        if e.kind is EntryKind.KNOWLEDGE_LINK:
            _validate_knowledge_entry(doc, e, entry_ids)

    # S366: валидация dangling для NPC-убеждений и кандидатов.
    # Все ссылки должны указывать на entry_id в пределах ТЕКУЩЕГО документа.
    # Вне for e — выполняется один раз на документ.
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

assert BROKEN in text, "Сломанный блок не найден — структура отличается от ожидаемой"
text = text.replace(BROKEN, FIXED, 1)

STORE_PY.write_text(text, encoding="utf-8")
print(f"OK: validate_document fixed (orig={orig_len}b, new={len(text)}b, delta={len(text)-orig_len:+d}b)")
