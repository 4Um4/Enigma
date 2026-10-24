# -*- coding: utf-8 -*-
# S366 doc-sync: roadmap v4.11 (CCH-S366 -> [x] + status block) and
# MUTATIONS.md (S366 TODO -> DONE + itog). Line-anchored, fail-loud, idempotent.
import io
import sys

DATE = "2026-10-24"

RM_PATH = "docs/ENIGMA_ROADMAP_v4_11_WPS.md"
RM_ANCHOR = "**CCH-S366**"
RM_TOGGLE_FROM = "- [ ] **CCH-S366**"
RM_TOGGLE_TO = "- [x] **CCH-S366**"
RM_APPEND = (
    " ✅ S366 (" + DATE + "): 4-слойная архитектура причинности по ТЗ Архитектора "
    "(мини-ADR v6, APPROVE WITH CHANGES): СЛОЙ 1 факт `ChronicleEntry.causes`; "
    "СЛОЙ 2 убеждение NPC `ChronicleDocument.npc_beliefs` (NpcCausalBelief); "
    "СЛОЙ 3 кандидаты `cause_candidates` (CauseCandidate); СЛОЙ 4 действия автора — "
    "POST link-causes / resolve-cause-candidate / record-npc-belief. "
    "3 enum (BeliefGrounding/CandidateBasis/CandidateStatus) + 2 frozen dataclass, CauseKind не расширен. "
    "Гейт T-CCH-CL-01 («10 готовых пар причина-следствие → ожидаемый набор») официально ЗАМЕНЁН: "
    "автогенерация ожидаемого набора противоречит ТЗ (запрет подмены №1 «хронология → причинность»; решение — за автором); "
    "фактическое покрытие — 17 тестов `backend/tests/micro/test_s366_causal_linker.py`, "
    "детекция на подготовленных парах-фикстурах — тесты 4–6 (прямой наследник «10 пар»). "
    "Прогоны: микро 487/487; IPT 53/0 (2026-10-24; до L4-фикса 52/53 — INV-SILENT-FAILURE на двух except→return "
    "в record-npc-belief, добавлен logger.warning, клиентский контракт не менялся; статический скан и поведенческие "
    "микротесты — разные слои контроля, не дублируют друг друга). "
    "Ограничения: SPAN_OVERLAP не реализован (нет CauseKind.PORTRET — несовместимость EntryKind↔CauseKind; "
    "docstring CandidateBasis + тест 5); TARGET_HINT_MATCH — диагностический признак кандидата для автора, "
    "не игровое правило; NpcCausalBelief хранится, но в игровом мышлении NPC не используется — "
    "отдельный будущий интеграционный рубеж, не блокер S366."
)

MT_PATH = "docs/MUTATIONS.md"
MT_ANCHOR = "- **S366** (TODO)"
MT_TOGGLE_FROM = "- **S366** (TODO)"
MT_TOGGLE_TO = "- **S366** (DONE " + DATE + ")"
MT_APPEND = (
    " Итог (" + DATE + "): реализовано как 4-слойная архитектура (факт → убеждение NPC → кандидаты → действия автора), "
    "а не `Dict[entry_id, List[CauseRef]]` из ранней редакции. Файлы: `domain/chronicle.py` "
    "(+BeliefGrounding/CandidateBasis/CandidateStatus, +NpcCausalBelief/CauseCandidate, "
    "+entry_kind_to_cause_kind: 4 соответствия EVENT/RELATIONSHIP/TRAIT_SEED/OBSERVATION, "
    "+npc_beliefs/cause_candidates в ChronicleDocument); `services/chronicle/causal_linker.py` "
    "(validate/detect_candidates/link; TEMPORAL_ORDER + TARGET_HINT_MATCH, rationale явно «НЕ причина»); "
    "`services/chronicle/chronicle_store.py` (сериализация обоих полей, fail-loud); "
    "`api/routes_chronicle.py` (ACCEPT пишет CauseRef в causes без дублей, REJECT_SILENT закрывает кандидата; "
    "replace-or-append по (believer, effect, cause)). Спорные связи → PENDING-кандидаты автору "
    "(НЕ ClarificationQuestion: ClarificationOption/UNKNOWN_PERSON для причинности запрещены вердиктом). "
    "Гейт T-CCH-CL-01 заменён 17 тестами `backend/tests/micro/test_s366_causal_linker.py` "
    "(подготовленные пары — тесты 4–6; автогенерация «ожидаемого набора» противоречит запрету подмены №1). "
    "Прогоны: 487/487 микро; IPT 53/0 (2026-10-24; до фикса 52/53: INV-SILENT-FAILURE на двух except→return "
    "в record-npc-belief — добавлен logger.warning без изменения контракта ответа). "
    "Ограничения: SPAN_OVERLAP не реализован (нет CauseKind.PORTRET); TARGET_HINT_MATCH — диагностический "
    "признак, не игровое правило; NpcCausalBelief хранится, но игровым мышлением не читается "
    "(будущий интеграционный рубеж); 363 канон-записи не тронуты (audit_causes.py: causes пусты у всех, "
    "ссылочная целостность не нарушена)."
)


def process(path, anchor, toggle_from, toggle_to, append, label):
    with io.open(path, "r", encoding="utf-8", newline="") as f:
        lines = f.readlines()
    hits = [i for i, ln in enumerate(lines) if anchor in ln]
    if len(hits) != 1:
        sys.exit("FATAL %s: expected 1 anchor hit, got %d" % (label, len(hits)))
    i = hits[0]
    line = lines[i]
    if toggle_to in line:
        print("%s: already synced (skip)" % label)
        return
    if toggle_from not in line:
        sys.exit("FATAL %s: anchor found but '%s' missing; head: %r" % (label, toggle_from, line[:120]))
    line = line.replace(toggle_from, toggle_to, 1)
    eol = "\r\n" if line.endswith("\r\n") else ("\n" if line.endswith("\n") else "")
    body = line.rstrip("\r\n")
    lines[i] = body + append + eol
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.writelines(lines)
    print("%s: OK, line %d updated, new length %d chars" % (label, i + 1, len(body) + len(append)))


process(RM_PATH, RM_ANCHOR, RM_TOGGLE_FROM, RM_TOGGLE_TO, RM_APPEND, "roadmap")
process(MT_PATH, MT_ANCHOR, MT_TOGGLE_FROM, MT_TOGGLE_TO, MT_APPEND, "mutations")
print("DONE")
