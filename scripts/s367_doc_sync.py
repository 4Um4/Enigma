# -*- coding: utf-8 -*-
# S367 doc-sync: roadmap v4.11 (CCH-S367 -> [x] + status) + MUTATIONS.md (TODO -> DONE + итог).
# Line-anchored, fail-loud, idempotent. CRLF normalization.
import io
import sys

DATE = "2026-10-25"

def process(path, anchor, toggle_from, toggle_to, append, label):
    with io.open(path, "r", encoding="utf-8", newline="") as f:
        raw = f.read()
    eol = "\r\n" if "\r\n" in raw else "\n"
    src = raw.replace("\r\n", "\n")
    hits = [i for i, ln in enumerate(src.split("\n")) if anchor in ln]
    if len(hits) != 1:
        print("FATAL %s: %d anchor hits, expected 1" % (label, len(hits)))
        return
    lines = src.split("\n")
    i = hits[0]
    line = lines[i]
    if toggle_to in line:
        print("%s: already synced (skip)" % label)
        return
    if toggle_from not in line:
        print("FATAL %s: anchor found but '%s' missing" % (label, toggle_from))
        return
    line = line.replace(toggle_from, toggle_to, 1) + append
    lines[i] = line
    out = eol.join(lines)
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(out)
    print("%s: OK, line %d, new length %d" % (label, i + 1, len(lines[i])))

RM_APPEND = (
    " ✅ S367 (" + DATE + "): roster-инъекция — `BiographyDecomposer(roster_provider=None)` lazy default "
    "`get_display_names`; `build_user_prompt` + roster-блок «ИЗВЕСТНЫЕ NPC»; "
    "`decomposition_normalizer.normalize(..., roster=None)` — contract-gated backstop (только "
    "RELATIONSHIP/EFFECT target_hint; type-guarded exact matcher; `_is_identity_question_for` exact "
    "span, заявленное ограничение; `roster=None` отключает). Промпт: ontology line 27 + rule 3 — "
    "«неопознанная сущность = target_hint не сопоставляется ОДНОЗНАЧНО с roster». Гейт guard_borko: "
    "≥2 валидных вопроса (Гильдия + старый пьянчужка) детерминированно; Тень (Nominative, shadow NPC) "
    "корректно silent (exact-match). Прогоны: 8/8 new test_s367_roster_injection.py; 109/109 backward-compat "
    "(cch1/cch2/s365/cch4/consistency/roster/cch5/s366); smoke PASS (det); IPT 53/0. Ограничения: exact match "
    "(не fuzzy/морфология) — inflected forms → form-mismatch noise (не засчитывается); identity-options-подпроверка "
    "сейчас вакуумно True (LEAVE_WHITE_SPOT-инвариант); LLM-часть smoke не проверена (llama-server недоступен "
    "standalone). `routes_chronicle.py` НЕ ИЗМЕНЁН; схема канона/MODEL_REGISTRY/_VAGUE_RELATION_MARKERS НЕ ТРОНУТЫ."
)

MT_APPEND = (
    " Итог (" + DATE + "): contract-gated roster backstop. Файлы: `biography_decomposer.py` (+`_default_roster_provider` "
    "lazy `get_display_names`; `__init__+roster_provider`; `build_user_prompt+roster` param + roster-блок; "
    "`decompose` fetch+pass; `normalize` call +roster=roster); `decomposition_normalizer.py` (+`_IDENTITY_OPTIONS`/"
    "`_matches_roster_exact`/`_is_identity_question_for` helpers; `normalize+roster` kwarg; roster backstop после "
    "vague_relation — только RELATIONSHIP/EFFECT target_hint, type-guarded, chained `not _matches_roster_exact "
    "AND not _is_identity_question_for`); `chronicle_decompose_system.txt` (ontology line 27 + rule 3 mandatory case). "
    "Smoke `s367_smoke_guard_borko.py`: hybrid (det + LLM); Гильдия + старый пьянчужка → roster_mismatch (valid); "
    "Тень Nominative → exact-match shadow → silent (корректно). Прогоны: 8/8 new; 109/109 backward-compat; IPT 53/0; "
    "L4 ✅. Ограничения: exact match (не fuzzy); LLM-часть smoke SKIP (llama-server недоступен standalone); "
    "NpcCausalBelief (S366) по-прежнему не в мышлении NPC. Handoff: `docs/HANDOFF_S367_to_S368.md`."
)

process("docs/ENIGMA_ROADMAP_v4_11_WPS.md",
        "**CCH-S367**", "- [ ] **CCH-S367**", "- [x] **CCH-S367**", RM_APPEND, "roadmap")
process("docs/MUTATIONS.md",
        "- **S367** (TODO)", "- **S367** (TODO)",
        "- **S367** (DONE " + DATE + ")", MT_APPEND, "mutations")
print("doc-sync: DONE")
