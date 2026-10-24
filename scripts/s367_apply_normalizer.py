# -*- coding: utf-8 -*-
# S367 patcher 2/3: decomposition_normalizer.py — contract-gated roster backstop.
# RELATIONSHIP/EFFECT target_hint only; type-guarded exact matcher;
# _is_identity_question_for (exact span, stated limitation); roster=None disables.
# CRLF normalization (read raw, detect eol, match on \n, write back eol).
import io
import sys

PATH = "backend/app/services/chronicle/decomposition_normalizer.py"

with io.open(PATH, "r", encoding="utf-8", newline="") as f:
    raw = f.read()

eol = "\r\n" if "\r\n" in raw else "\n"
print("detected eol: %s" % ("CRLF" if eol == "\r\n" else "LF"))
src = raw.replace("\r\n", "\n")

def apply_replace(src, old, new, label):
    n = src.count(old)
    if n == 0:
        anchor = old[:30].replace("\n", "\\n")
        idx = src.find(old[:30])
        if idx >= 0:
            line = src[:idx].count("\n") + 1
            print("  %s: SKIP — anchor found at line %d, full block mismatch" % (label, line))
        else:
            print("  %s: SKIP — anchor '%s' NOT found" % (label, anchor))
        return src
    if n > 1:
        sys.exit("FATAL %s: %d hits, expected 1" % (label, n))
    src = src.replace(old, new, 1)
    print("  %s: OK (%d -> %d chars)" % (label, len(old), len(new)))
    return src

# 1. imports: add Optional
src = apply_replace(src,
    "from typing import Any, Final, List, Mapping",
    "from typing import Any, Final, List, Mapping, Optional",
    "#1 imports")

# 2. helpers after _VAGUE_RELATION_MARKERS, before DecompositionError
src = apply_replace(src,
    '_VAGUE_RELATION_MARKERS: Final[tuple] = (\n'
    '    "дальний родственник",\n'
    '    "дальняя родственница",\n'
    '    "какой-то человек",\n'
    '    "некий человек",\n'
    '    "знакомый семьи",\n'
    '    "знакомая семьи",\n'
    '    "какой-то знакомый",\n'
    '    "человек со стороны",\n'
    ')\n'
    '\n'
    '\n'
    'class DecompositionError(ValueError):',
    '_VAGUE_RELATION_MARKERS: Final[tuple] = (\n'
    '    "дальний родственник",\n'
    '    "дальняя родственница",\n'
    '    "какой-то человек",\n'
    '    "некий человек",\n'
    '    "знакомый семьи",\n'
    '    "знакомая семьи",\n'
    '    "какой-то знакомый",\n'
    '    "человек со стороны",\n'
    ')\n'
    '\n'
    '# S367: identity-resolution options. LEAVE_WHITE_SPOT присутствует в каждом\n'
    '# вопросе (инвариант ClarificationQuestion.__post_init__), поэтому подпроверка\n'
    '# identity-options сейчас вакуумно True — защитная на будущие типы вопросов с\n'
    '# другими опциями. Эффективная логика — exact target_span==hint.\n'
    '_IDENTITY_OPTIONS: Final[frozenset] = frozenset({\n'
    '    ClarificationOption.SELECT_EXISTING_NPC,\n'
    '    ClarificationOption.CREATE_NEW_NPC,\n'
    '    ClarificationOption.UNKNOWN_PERSON,\n'
    '    ClarificationOption.LEAVE_WHITE_SPOT,\n'
    '})\n'
    '\n'
    '\n'
    'def _matches_roster_exact(hint: Any, roster: Mapping[str, str]) -> bool:\n'
    '    """S367: exact case-insensitive match hint против roster display names + ids.\n'
    '    Type-guarded: non-str hint/name/id -> False (НЕ mismatch, а skip).\n'
    '    Exact (не fuzzy, не падежная морфология) — заявленное ограничение."""\n'
    '    if not isinstance(hint, str):\n'
    '        return False\n'
    '    h = hint.strip().lower()\n'
    '    if not h:\n'
    '        return False\n'
    '    for npc_id, name in roster.items():\n'
    '        if isinstance(name, str) and h == name.strip().lower():\n'
    '            return True\n'
    '        if isinstance(npc_id, str) and h == npc_id.strip().lower():\n'
    '            return True\n'
    '    return False\n'
    '\n'
    '\n'
    'def _is_identity_question_for(question: Any, hint: Any) -> bool:\n'
    '    """S367: True если question уже спрашивает об идентичности hint-сущности.\n'
    '    Подпроверка identity-options сейчас вакуумно True (LEAVE_WHITE_SPOT-инвариант);\n'
    '    защитная на будущие не-identity типы. Эффективная логика — exact span==hint.\n'
    '    ОГРАНИЧЕНИЕ: инфлектированный/форматный span от LLM не совпадёт -> возможен\n'
    '    дубль-вопрос (не катастрофично — автор резолвит оба)."""\n'
    '    if question is None:\n'
    '        return False\n'
    '    opts = getattr(question, "options", None) or ()\n'
    '    if not any(o in _IDENTITY_OPTIONS for o in opts):\n'
    '        return False\n'
    '    span = getattr(question, "target_span", None)\n'
    '    if not isinstance(span, str) or not isinstance(hint, str):\n'
    '        return False\n'
    '    return span.strip().lower() == hint.strip().lower()\n'
    '\n'
    '\n'
    'class DecompositionError(ValueError):',
    "#2 helpers")

# 3. normalize signature + roster kwarg
src = apply_replace(src,
    '    @staticmethod\n'
    '    def normalize(raw: Any, *, chronicle_id: str, fragment_ord: int) -> List[DecompositionItem]:',
    '    @staticmethod\n'
    '    def normalize(\n'
    '        raw: Any,\n'
    '        *,\n'
    '        chronicle_id: str,\n'
    '        fragment_ord: int,\n'
    '        roster: Optional[Mapping[str, str]] = None,\n'
    '    ) -> List[DecompositionItem]:',
    "#3 normalize signature")

# 4. roster backstop block after vague_relation, before needs_conf
src = apply_replace(src,
    '            if not question and any(m in blob for m in _VAGUE_RELATION_MARKERS):\n'
    '                conf = min(float(conf), 0.4)\n'
    '                question = ClarificationQuestion(\n'
    '                    question_id=f"vague_relation_{idx}",\n'
    '                    target_span=payload.get("target_hint") or payload.get("summary") or "",\n'
    '                    options=(\n'
    '                        ClarificationOption.SELECT_EXISTING_NPC,\n'
    '                        ClarificationOption.CREATE_NEW_NPC,\n'
    '                        ClarificationOption.UNKNOWN_PERSON,\n'
    '                        ClarificationOption.LEAVE_WHITE_SPOT,\n'
    '                    ),\n'
    '                )\n'
    '            needs_conf = bool(it.get("needs_confirmation") or question is not None)',
    '            if not question and any(m in blob for m in _VAGUE_RELATION_MARKERS):\n'
    '                conf = min(float(conf), 0.4)\n'
    '                question = ClarificationQuestion(\n'
    '                    question_id=f"vague_relation_{idx}",\n'
    '                    target_span=payload.get("target_hint") or payload.get("summary") or "",\n'
    '                    options=(\n'
    '                        ClarificationOption.SELECT_EXISTING_NPC,\n'
    '                        ClarificationOption.CREATE_NEW_NPC,\n'
    '                        ClarificationOption.UNKNOWN_PERSON,\n'
    '                        ClarificationOption.LEAVE_WHITE_SPOT,\n'
    '                    ),\n'
    '                )\n'
    '            # S367: roster backstop — contract-gated, type-guarded.\n'
    '            # Только RELATIONSHIP.target_hint (всегда NPC) и EFFECT.target_hint\n'
    '            # при non-null (контракт "null|<имя>"). name_hint=place, observed_hint=\n'
    '            # "имя/явление", about_hint=тема — НЕ обрабатываются (LLM rule 3).\n'
    '            # roster=None -> backstop отключён (backward-compat).\n'
    '            # Exact target_span==hint — ЗАЯВЛЕННОЕ ОГРАНИЧЕНИЕ (не fuzzy):\n'
    '            # инфлектированный span от LLM может дать дубль-вопрос — не катастрофично.\n'
    '            if roster is not None:\n'
    '                hint = None\n'
    '                if kind is EntryKind.RELATIONSHIP:\n'
    '                    hint = payload.get("target_hint")\n'
    '                elif kind is EntryKind.EFFECT:\n'
    '                    h = payload.get("target_hint")\n'
    '                    if isinstance(h, str) and h.strip():\n'
    '                        hint = h\n'
    '                if (\n'
    '                    isinstance(hint, str)\n'
    '                    and hint.strip()\n'
    '                    and not _matches_roster_exact(hint, roster)\n'
    '                    and not _is_identity_question_for(question, hint)\n'
    '                ):\n'
    '                    conf = min(float(conf), 0.4)\n'
    '                    question = ClarificationQuestion(\n'
    '                        question_id=f"roster_mismatch_{idx}",\n'
    '                        target_span=hint,\n'
    '                        options=(\n'
    '                            ClarificationOption.SELECT_EXISTING_NPC,\n'
    '                            ClarificationOption.CREATE_NEW_NPC,\n'
    '                            ClarificationOption.UNKNOWN_PERSON,\n'
    '                            ClarificationOption.LEAVE_WHITE_SPOT,\n'
    '                        ),\n'
    '                    )\n'
    '            needs_conf = bool(it.get("needs_confirmation") or question is not None)',
    "#4 roster backstop")

out = src.replace("\n", eol)
with io.open(PATH, "w", encoding="utf-8", newline="") as f:
    f.write(out)
print("normalizer: DONE (eol preserved: %s)" % ("CRLF" if eol == "\r\n" else "LF"))
