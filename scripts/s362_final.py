import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CRLF = chr(13) + chr(10)
LF = chr(10)

def read_norm(p):
    raw = p.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    text_raw = raw.decode("utf-8-sig") if has_bom else raw.decode("utf-8")
    has_crlf = CRLF in text_raw
    text = text_raw.replace(CRLF, LF)
    return text, has_bom, has_crlf

def write_preserve(p, text, has_bom, has_crlf):
    if has_crlf:
        text = text.replace(LF, CRLF)
    out_bytes = text.encode("utf-8-sig") if has_bom else text.encode("utf-8")
    p.write_bytes(out_bytes)

# ── 1. Rename S361 -> S362 в flags.yaml note ──
p = ROOT / "architecture" / "flags.yaml"
text, hb, hc = read_norm(p)
old_note = "S361 PRE-FLIGHT (RECLASSIFY)"
new_note = "S362 PRE-FLIGHT (RECLASSIFY)"
if old_note in text:
    text = text.replace(old_note, new_note)
    write_preserve(p, text, hb, hc)
    print("[OK] flags.yaml: S361 -> S362 in note")
else:
    print("[SKIP] flags.yaml: S361 not in note (already renamed?)")

# ── 2. Rename S361 -> S362 в IMPACT §13 (заголовок + текст) ──
p = ROOT / "docs" / "audits" / "ADR-O-426_IMPACT.md"
text, hb, hc = read_norm(p)
count = text.count("S361")
if count > 0:
    text = text.replace("S361", "S362")
    write_preserve(p, text, hb, hc)
    print("[OK] IMPACT: S361 -> S362 (" + str(count) + " replacements)")
else:
    print("[SKIP] IMPACT: no S361")

# ── 3. Rename S361 -> S362 в ЗАВЕЩАНИЕ Письмо №11 (заголовок + текст) ──
p = ROOT / "docs" / "ЗАВЕЩАНИЕ_АРХИТЕКТОРОВ.md"
text, hb, hc = read_norm(p)
count = text.count("S361")
if count > 0:
    text = text.replace("S361", "S362")
    write_preserve(p, text, hb, hc)
    print("[OK] ЗАВЕЩАНИЕ: S361 -> S362 (" + str(count) + " replacements)")
else:
    print("[SKIP] ЗАВЕЩАНИЕ: no S361")

# ── 4. Patch roadmap (6 якорей) ──
p = ROOT / "docs" / "ENIGMA_ROADMAP_v4_7_EPI-updated.md"
text, hb, hc = read_norm(p)

PATCHES = [
    {
        "anchor": "Активная приёмка ветви Б — отдельный цикл оживления ROLLOUT-PENDING (PRE-FLIGHT по конкретным флагам; D72 = ROLLOUT-PENDING default OFF по вердикту II.д).",
        "replacement": "**PRE-FLIGHT цикл ROLLOUT-PENDING закрыт S362** (вердикт Мастера от 2026-10-19: 5 rollout-пакетов, 3 доработки разрешены, 3 блокера остаются); COV-2 закрыт (S2-стыковка — публикация за Мастером); далее GC-спринт петли (§9.10) → LC-IMPL-2/3. Rollout-цикл открыт — флаги остаются ROLLOUT-PENDING до завершения каждого пакета (§17.8 Шаг 6).",
        "label": "§0.0 фронтир Б",
    },
    {
        "anchor": "replay-бюджет (default OFF — вердикт II.д, консервативный). **Гейт:** COV-GC-01/02 — закрыт полностью.",
        "replacement": "replay-бюджет (default OFF — вердикт II.д, консервативный). **Гейт:** COV-GC-01/02 — закрыт полностью." + LF + "- [ ] **COV-1.5 — PRE-FLIGHT цикл оживления ROLLOUT-PENDING** (S362, ветка Б; вердикт Мастера 2026-10-19): read-only аудит 16 чужих ROLLOUT-PENDING-флагов + 1 моего (replay_budget_keep_last вне цикла — II.д). 5 rollout-пакетов (§17.8 Шаг 6): техническая надёжность → динамика состояния → воля и объекты → арбитраж → желание-деятельность-исход. 3 доработки разрешены: S203_4_OWNERSHIP_MIRRORS (точный гейт COMMITMENT_REGISTRY_ENABLED AND S203_4_OWNERSHIP_MIRRORS, НЕ каскад); TRAVERSAL_OWNERSHIP_ENFORCEMENT (НЕ поглощён ADR-130.1, отдельная вертикаль с interrupt_traversal); W3_SHADOW_ENABLED → RECLASSIFY в KEEP-LOG (исполнено). 3 блокера остаются: WORK_ENABLED (COV-D1), RELATIONSHIP_EVENTS_ENABLED (RE-D2), BC1_ENABLED (BC-2). **Гейт:** каждый пакет — собственный цикл (HEAD + baseline + ON-тесты + F5 + OFF-rollback + итоговый вердикт); флаги остаются ROLLOUT-PENDING до завершения своего пакета.",
        "label": "§0.2 Ступень COV-1 + COV-1.5",
    },
    {
        "anchor": "| COV-D73 | Реестр флагов отсутствует: 14+ dormant-флагов без rollout-плана",
        "replacement": "| COV-D73 (S362 update) | Реестр флагов отсутствует: 14+ dormant-флагов без rollout-плана — ЗАКРЫТ S343+S344. **S362 PRE-FLIGHT:** 16 чужих ROLLOUT-PENDING-флагов профилированы; W3_SHADOW_ENABLED → RECLASSIFY в KEEP-LOG (исполнено S362, docstring подтверждает чистую наблюдательность); 3 блокера (WORK/RE-EVENTS/BC1) остаются; TRAVERSAL_OWNERSHIP_ENFORCEMENT уточнён — НЕ висячий, отдельная вертикаль с interrupt_traversal (closure S186/S203.3) — вердикт о включении за Мастером | P1 | COV-0 | S343+S344+S362: flags.yaml + lint_flags + INV-FLAG-REGISTRY; W3_SHADOW RECLASSIFY | закрыт (S343+S344+S362) |",
        "label": "§7.10 COV-D73",
    },
    {
        "anchor": "replay-бюджет. **Гейт:** COV-GC-01/02 закрыт полностью (Шаг 1 D58 ✅ → Шаг 2 D59 ✅ → Шаг 3 D60 ✅ → Шаг 4 D70 ✅ → Шаг 5 D72 ✅).",
        "replacement": "replay-бюджет. **Гейт:** COV-GC-01/02 закрыт полностью (Шаг 1 D58 ✅ → Шаг 2 D59 ✅ → Шаг 3 D60 ✅ → Шаг 4 D70 ✅ → Шаг 5 D72 ✅)." + LF + "- [~] **COV-1.5 — PRE-FLIGHT цикл ROLLOUT-PENDING** (S362): аудит 16 флагов; вердикт Мастера — 5 rollout-пакетов с очередностью (§17.8 Шаг 6); 3 доработки разрешены; W3_SHADOW_ENABLED → KEEP-LOG (RECLASSIFY исполнена); флаги Группы A остаются ROLLOUT-PENDING до завершения каждого пакета (запрет Мастера: массовое включение одним изменением конфигурации).",
        "label": "§17.4 COV-1 + COV-1.5",
    },
    {
        "anchor": "Док-закрытие: roadmap (§0.0/§0.2/§7.10/§17.4/§17.8/§9.3f) + IMPACT §12 + атлас Status O-426 + Письмо №10 в ЗАВЕЩАНИЕ (append, после Письма №9 S358 — чужой WIP не тронут).",
        "replacement": "Док-закрытие: roadmap (§0.0/§0.2/§7.10/§17.4/§17.8/§9.3f) + IMPACT §12 + атлас Status O-426 + Письмо №10 в ЗАВЕЩАНИЕ (append, после Письма №9 S358 — чужой WIP не тронут)." + LF + "- [x] **Шаг 6 COV-1.5 / PRE-FLIGHT цикл ROLLOUT-PENDING [закрыт: read-only аудит]** ✅ (S362, ветка Б; вердикт Мастера 2026-10-19). Состав: read-only аудит 16 чужих ROLLOUT-PENDING-флагов (мой replay_budget_keep_last вне цикла — II.д вердикт); профили для каждого (ADR/owner/wiring/зависимости/F5/rollback). Вердикт Мастера: GO-1/GO-2/HOLD/BLOCKED/DEFER/RECLASSIFY/OFF по каждому флагу; 5 rollout-пакетов с очередностью: (1) техническая надёжность — LLM_RESILIENCE_V1 + W3_SHADOW_ENABLED после RECLASSIFY в KEEP-LOG; (2) динамика состояния — RELATIONSHIP_DYNAMICS_ENABLED; (3) воля и объекты — W3_G2_ENABLED → W3_G3_ENABLED после GC-08/spawn_world_object; (4) арбитраж — ARBITER_ENFORCEMENT + S203_4_ARBITER_INTERRUPT + S203_4_OWNERSHIP_MIRRORS (третий с независимым гейтом COMMITMENT_REGISTRY_ENABLED AND S203_4_OWNERSHIP_MIRRORS, НЕ каскад); (5) вертикаль желание→деятельность→исход — DESIRES_ENABLED + ACTIVITY_LIFECYCLE_ENABLED (cross-branch coord A/B). 3 доработки разрешены археологией: (а) S203_4_OWNERSHIP_MIRRORS — точный runtime-гейт commitment_registry.py:334,406,462,484,530 (5 сайтов mirror_task_terminal через drain_commitment_outbox в task_scheduler.py:205); НЕ зависит от ARBITER_ENFORCEMENT; (б) TRAVERSAL_OWNERSHIP_ENFORCEMENT — НЕ поглощён ADR-130.1, отдельная вертикаль с interrupt_traversal (3 сайта: tick_orchestrator:1319 CROSS_LOCATION_TRANSFER, movement_engine:244 INTERRUPT_PRIORITY_SUPERSEDE, movement_engine:523 CROSS_LOCATION_MATERIALIZE) — closure S186/S203.3, следующее поколение после legacy pop+mirror; вердикт о включении — за Мастером в отдельном раунде; (в) W3_SHADOW_ENABLED → RECLASSIFY в KEEP-LOG подтверждена docstring affordance_shadow.py (НОЛЬ decision-input/mutation/writers/events; метрики G1-discovery-тени). Правила приёмки rollout-цикла (вердикт Мастера §4): 1) зафиксировать HEAD + baseline тесты + OFF-поведение; 2) включить только согласованные флаги через предусмотренный конфигурационный механизм; 3) запустить целевые micro-тесты + SUPERBOX + FULL pytest; 4) F5-сценарий: наблюдаемое действие NPC → изменение мира → последствие → сохранение причинной цепочки; 5) OFF-rollback проверка; 6) итоговый вердикт (ROLLOUT-ON / HOLD / возврат в OFF) — только после цикла. ЗАПРЕТ Мастера: НЕ менять default и статус в реестре раньше завершения rollout-цикла; массовое включение флагов одним изменением конфигурации ЗАПРЕЩЕНО. Блокеры (Группа C) остаются: WORK_ENABLED (до COV-3/COV-D1 ConsumptionResolver), RELATIONSHIP_EVENTS_ENABLED (до закрытия RE-D2 behavioral zero), BC1_ENABLED (до готовности BC-2). Группа B HOLD: COGNITION_V0 (coord с активным фронтом А Understanding S342); TRAVERSAL_OWNERSHIP_ENFORCEMENT (PRE-FLIGHT уточнил — НЕ висячий, отдельная вертикаль; вердикт о включении — за Мастером). Группа D DEFER: enforce_system_requirements → COV-9. Группа E RECLASSIFY исполнена: W3_SHADOW_ENABLED → KEEP-LOG (flags.yaml правлен s361_p1_flags.py). Базлайн: IPT 53/0/0 CRITICAL=0 (HEAD 746d55d9); Anti-Race чист (чужой WIP зоны А — chronicle_projections/routes_chronicle/chronicle_editor — не тронут). Гейты док-закрытия: ruff 0 (скрипты); compileall 0; IPT 53/0/0. Док-закрытие: roadmap (§0.0/§0.2/§7.10/§17.4/§17.8/§9.3f) + IMPACT ADR-O-426 §13 + ЗАВЕЩАНИЕ Письмо №11 + flags.yaml (W3_SHADOW_ENABLED RECLASSIFY). Статус: rollout-цикл открыт; флаги Группы A остаются ROLLOUT-PENDING до завершения каждого пакета.",
        "label": "§17.8 Шаг 6 PRE-FLIGHT",
    },
    {
        "anchor": "- [ ] **COV-GC-09 — Реестр полноты живой (мета-гейт).** Каждая новая находка любой сессии попадает в §7.10 (DoD-проверка при записи в MUTATIONS); каждый тронутый сессией модуль имеет якорь (§17.1.1); периодический ре-аудит — §17.7.",
        "replacement": "- [ ] **COV-GC-09 — Реестр полноты живой (мета-гейт).** Каждая новая находка любой сессии попадает в §7.10 (DoD-проверка при записи в MUTATIONS); каждый тронутый сессией модуль имеет якорь (§17.1.1); периодический ре-аудит — §17.7. **S362 PRE-FLIGHT цикл ROLLOUT-PENDING:** 16 флагов профилированы (§17.8 Шаг 6); W3_SHADOW_ENABLED → RECLASSIFY KEEP-LOG (исполнено); 3 блокера остаются (WORK/RE-EVENTS/BC1); rollout-цикл открыт с 5 пакетами и правилами приёмки (вердикт Мастера §4).",
        "label": "§9.3f COV-GC-09",
    },
]

for patch in PATCHES:
    anchor = patch["anchor"]
    replacement = patch["replacement"]
    label = patch["label"]
    count = text.count(anchor)
    if count != 1:
        print("ANCHOR FAIL [roadmap " + label + "]: found " + str(count) + "x (expected 1)")
        sys.exit(1)
    text = text.replace(anchor, replacement, 1)
    print("[OK] roadmap " + label + ": patched")

write_preserve(p, text, hb, hc)
print("[OK] roadmap: 6 patches applied (has_bom=" + str(hb) + " has_crlf=" + str(hc) + ")")

# ── 5. Append S362 в MUTATIONS.md ──
p = ROOT / "docs" / "MUTATIONS.md"
text, hb, hc = read_norm(p)

ANCHOR = "**S362**"
if ANCHOR in text:
    print("ANCHOR FAIL [MUTATIONS.md S362]: already present (append-only violation)")
    sys.exit(1)

S362 = "- **S362** PRE-FLIGHT цикл оживления ROLLOUT-PENDING-флагов (ветка Б; вердикт Мастера 2026-10-19): read-only аудит 16 чужих ROLLOUT-PENDING-флагов (мой replay_budget_keep_last вне цикла — II.д вердикт). Вердикт Мастера по каждому: GO-1/GO-2/HOLD/BLOCKED/DEFER/RECLASSIFY/OFF. 5 rollout-пакетов с очередностью: (1) техническая надёжность — LLM_RESILIENCE_V1 + W3_SHADOW_ENABLED после RECLASSIFY в KEEP-LOG; (2) динамика состояния — RELATIONSHIP_DYNAMICS_ENABLED; (3) воля и объекты — W3_G2_ENABLED, затем W3_G3_ENABLED после GC-08/spawn_world_object; (4) арбитраж — ARBITER_ENFORCEMENT + S203_4_ARBITER_INTERRUPT + S203_4_OWNERSHIP_MIRRORS (третий с независимым гейтом COMMITMENT_REGISTRY_ENABLED AND S203_4_OWNERSHIP_MIRRORS, НЕ каскад — археология commitment_registry.py:334,406,462,484,530); (5) вертикаль желание-деятельность-исход — DESIRES_ENABLED + ACTIVITY_LIFECYCLE_ENABLED (cross-branch coord A/B). 3 доработки разрешены археологией: (а) S203_4_OWNERSHIP_MIRRORS — точный runtime-гейт НЕ зависит от ARBITER_ENFORCEMENT; (б) TRAVERSAL_OWNERSHIP_ENFORCEMENT — НЕ поглощён ADR-130.1, отдельная вертикаль с interrupt_traversal (3 сайта: tick_orchestrator:1319 CROSS_LOCATION_TRANSFER, movement_engine:244 INTERRUPT_PRIORITY_SUPERSEDE, movement_engine:523 CROSS_LOCATION_MATERIALIZE) — closure S186/S203.3; (в) W3_SHADOW_ENABLED RECLASSIFY в KEEP-LOG подтверждена docstring affordance_shadow.py. Правила приёмки rollout-цикла (вердикт Мастера §4): 1) зафиксировать HEAD + baseline + OFF-поведение; 2) включить только согласованные флаги; 3) micro-тесты + SUPERBOX + FULL pytest; 4) F5-сценарий: наблюдаемое действие NPC, изменение мира, последствие, причинная цепочка; 5) OFF-rollback проверка; 6) итоговый вердикт (ROLLOUT-ON / HOLD / возврат в OFF) — только после цикла. ЗАПРЕТ Мастера: НЕ менять default и статус в реестре раньше завершения rollout-цикла; массовое включение флагов одним изменением конфигурации ЗАПРЕЩЕНО. Блокеры (Группа C) остаются: WORK_ENABLED (до COV-3/COV-D1), RELATIONSHIP_EVENTS_ENABLED (до закрытия RE-D2), BC1_ENABLED (до готовности BC-2). Группа B HOLD: COGNITION_V0 (coord с А Understanding S342); TRAVERSAL_OWNERSHIP_ENFORCEMENT (НЕ висячий, отдельная вертикаль; вердикт о включении — за Мастером). Группа D DEFER: enforce_system_requirements → COV-9. Группа E RECLASSIFY исполнена: W3_SHADOW_ENABLED → KEEP-LOG. Базлайн: IPT 53/0/0 CRITICAL=0 (HEAD 746d55d9); Anti-Race чист. Примечание: нумерация S361 занята параллельной сессией А (UX-CCH-FIX-1) — по канону Устав 11.1.1 моя запись = S362 (max+1). Док-закрытие: flags.yaml (W3_SHADOW RECLASSIFY) + roadmap (§0.0/§0.2/§7.10/§17.4/§17.8/§9.3f) + IMPACT ADR-O-426 §13 + ЗАВЕЩАНИЕ Письмо №11. Статус: rollout-цикл открыт; статус каждого флага — после завершения своего пакета."

if not text.endswith(LF):
    text += LF
text += S362 + LF

write_preserve(p, text, hb, hc)
print("[OK] MUTATIONS.md: S362 appended (has_bom=" + str(hb) + " has_crlf=" + str(hc) + ")")

print()
print("=" * 60)
print("S362 doc-closure COMPLETE")
print("  1 flags.yaml (S361->S362 rename in note)")
print("  2 IMPACT §13 (S361->S362 rename)")
print("  3 ЗАВЕЩАНИЕ Письмо №11 (S361->S362 rename)")
print("  4 roadmap (6 patches with S362)")
print("  5 MUTATIONS.md (S362 appended)")
print("=" * 60)