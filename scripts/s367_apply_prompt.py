# -*- coding: utf-8 -*-
# S367 patcher 3/3: chronicle_decompose_system.txt — rule 3 + ontology.
# CRLF normalization (read raw, detect eol, match on \n, write back eol).
import io
import sys

PATH = "backend/prompts/chronicle_decompose_system.txt"

with io.open(PATH, "r", encoding="utf-8", newline="") as f:
    raw = f.read()

eol = "\r\n" if "\r\n" in raw else "\n"
print("detected eol: %s" % ("CRLF" if eol == "\r\n" else "LF"))
src = raw.replace("\r\n", "\n")

def apply_replace(src, old, new, label):
    n = src.count(old)
    if n == 0:
        idx = src.find(old[:30])
        if idx >= 0:
            line = src[:idx].count("\n") + 1
            print("  %s: SKIP — anchor at line %d, full block mismatch" % (label, line))
        else:
            print("  %s: SKIP — anchor NOT found" % label)
        return src
    if n > 1:
        sys.exit("FATAL %s: %d hits" % (label, n))
    src = src.replace(old, new, 1)
    print("  %s: OK (%d -> %d chars)" % (label, len(old), len(new)))
    return src

# 1. ontology line 27: extend "Неопознанные"
src = apply_replace(src,
    "- Неопознанные («стражник», «женщина») — помечай в question: предложи SELECT_EXISTING_NPC/CREATE_NEW_NPC/UNKNOWN_PERSON/LEAVE_WHITE_SPOT.",
    "- «Неопознанная сущность» = target_hint не сопоставляется ОДНОЗНАЧНО ни с одним именем из roster известных NPC (блок «ИЗВЕСТНЫЕ NPC» в user-сообщении). Для такой сущности ОБЯЗАТЕЛЬНО создай ClarificationQuestion с опциями SELECT_EXISTING_NPC/CREATE_NEW_NPC/UNKNOWN_PERSON/LEAVE_WHITE_SPOT. НЕ придумывай идентичность и НЕ пропускай сущность молча.",
    "#1 ontology")

# 2. rule 3: add mandatory roster case (first position)
src = apply_replace(src,
    "3. Вопрос задавай ТОЛЬКО при реальной неоднозначности для причинной модели. Обязательные случаи:\n"
    "   - родственная/социальная связь определена неточно («дальний родственник», «знакомый», «какой-то человек») у значимого лица → вопрос о точной связи;\n"
    "   - пол/возраст неспецифицирован у значимого лица;\n"
    "   - неясно, какое именно событие или чей поступок.\n"
    "   При вопросе: needs_confirmation=true, confidence ≤ 0.5.",
    "3. Вопрос задавай ТОЛЬКО при реальной неоднозначности для причинной модели. Обязательные случаи:\n"
    "   - target_hint не сопоставляется ОДНОЗНАЧНО с roster известных NPC (см. user-сообщение) → вопрос о идентичности сущности;\n"
    "   - родственная/социальная связь определена неточно («дальний родственник», «знакомый», «какой-то человек») у значимого лица → вопрос о точной связи;\n"
    "   - пол/возраст неспецифицирован у значимого лица;\n"
    "   - неясно, какое именно событие или чей поступок.\n"
    "   При вопросе: needs_confirmation=true, confidence ≤ 0.5.",
    "#2 rule 3")

out = src.replace("\n", eol)
with io.open(PATH, "w", encoding="utf-8", newline="") as f:
    f.write(out)
print("prompt: DONE (eol preserved: %s)" % ("CRLF" if eol == "\r\n" else "LF"))
