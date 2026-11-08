import pathlib, sys
BASE = pathlib.Path(r"C:\DDD\Codex\VSC_Enigma\Enigma\docs\Тесты причинности ТЗ")
def edit(fn, old, new):
    p = BASE / fn
    if not p.exists(): print(f"FAIL: {fn} not found"); sys.exit(1)
    t = p.read_text(encoding="utf-8")
    if old not in t: print(f"FAIL: old not found in {fn}\n  {old[:120]}"); sys.exit(1)
    p.write_text(t.replace(old, new, 1), encoding="utf-8")
    print(f"OK: {fn}")
def remove_dup(fn, hdr):
    p = BASE / fn
    t = p.read_text(encoding="utf-8")
    f1 = t.find(hdr)
    if f1 == -1: print(f"INFO: {fn} — header not found"); return
    f2 = t.find(hdr, f1 + 1)
    if f2 == -1: print(f"INFO: {fn} — no duplicate"); return
    p.write_text(t[:f2].rstrip() + "\n", encoding="utf-8")
    print(f"OK: {fn} — duplicate removed")

print("=== COGNITIVE-CONTINUITY-01.md ===")
edit("COGNITIVE-CONTINUITY-01.md",
 "| CC-04 | ✅ | CognitionContextResolver читает EpistemicStore + **B4-R13: cog_block доходит до ModelRouter** | применительно к доказанной доставке cog_block в ModelRouter (не к полной когнитивной непрерывности NPC) |",
 "| CC-04 | ✅ | CognitionContextResolver читает EpistemicStore + **B4-R13: cog_block доходит до ModelRouter** + **B4-R14: Knowledge/Communication separation (produces_claim gate, commit b16bb9a7)** | применительно к доказанной доставке cog_block в ModelRouter + развязке знания и коммуникации |")
edit("COGNITIVE-CONTINUITY-01.md",
 "### 9.6. B4-R13: production-path PROMPT_INJECTION verification (2026-11-08)",
 "### 9.6. B4-R13/R14: PROMPT_INJECTION + Knowledge/Communication separation")
edit("COGNITIVE-CONTINUITY-01.md",
 "B4-R14-B: альтернатива Мастера — тестовый адаптер на границе ModelRouter.",
 "B4-R14-B: альтернатива Мастера — тестовый адаптер на границе ModelRouter.\n\n**B4-R14 (2026-11-08): Knowledge/Communication separation — CLOSED**\n**Commit:** `b16bb9a7`\n**Change:** гейт `if produces_claim(intent_value):` вокруг извлечения Proposition в `decision_hub.py` (39 строк). Non-claim интенты не получают Proposition автоматически — NPC знает, но не сообщает. Claim интенты сохраняют.\n**Доказательства:** 7/7 unit test PASS, B5-F1.1 A/B PASS, cold-start 4/4 PASS.\n**Регрессии (pre-existing):** P5A (LLM infra), B4 test (cognition context).\n\nB4-R14-A/B: superseded by B4-R14 gate.")
remove_dup("COGNITIVE-CONTINUITY-01.md", "### 9.6. B4-R13")

print("\n=== BUTTERFLY-01_GUIDE_UPDATE_v3.md ===")
edit("BUTTERFLY-01_GUIDE_UPDATE_v3.md",
 "| CC-04 | ⚠️ | **B4: idle ticks tested (advance_ticks 2+10)** — но cognition context empty for Tornin (confidence < 0.25) |",
 "| CC-04 | ⚠️ → ✅ | **B4: idle ticks tested** + **B4-R14: Knowledge/Communication separation (produces_claim gate, commit b16bb9a7)** — cog_block delivery proven, развязка доказана; cognition context empty (confidence < 0.25) — отдельная calibration проблема |")
edit("BUTTERFLY-01_GUIDE_UPDATE_v3.md",
 "### 8.5. B4-R14-A — аудит изоляции belief",
 "### 8.5. B4-R14-A — аудит изоляции belief (superseded by B4-R14 gate)")
edit("BUTTERFLY-01_GUIDE_UPDATE_v3.md",
 "Вердикт: NO SAFE EXISTING MECHANISM. EpistemicStore не имеет штатного API для удаления/изоляции одной Proposition. PLAYER_INSULTS создаёт 4 побочных эффекта (belief + stress + fear + trust + social), которые нельзя разделить через существующие механизмы.",
 "Вердикт: NO SAFE EXISTING MECHANISM. EpistemicStore не имеет штатного API для удаления/изоляции одной Proposition. PLAYER_INSULTS создаёт 4 побочных эффекта (belief + stress + fear + trust + social), которые нельзя разделить через существующие механизмы.\n\n**Статус:** superseded by B4-R14 gate (commit `b16bb9a7`). Развязка решена через produces_claim гейт — non-claim интенты не получают Proposition, claim интенты сохраняют. 7/7 PASS, A/B PASS.")
edit("BUTTERFLY-01_GUIDE_UPDATE_v3.md",
 "### 8.6. B4-R14-B — альтернатива Мастера",
 "### 8.6. B4-R14-B — альтернатива Мастера (superseded by B4-R14 gate)")
edit("BUTTERFLY-01_GUIDE_UPDATE_v3.md",
 "Условие валидности: claim_block не должен утекать факт оскорбления в Control A.",
 "Условие валидности: claim_block не должен утекать факт оскорбления в Control A.\n\n**Статус:** superseded by B4-R14 gate (commit `b16bb9a7`). Развязка в production code, не через тестовый адаптер.")
remove_dup("BUTTERFLY-01_GUIDE_UPDATE_v3.md", "## 8. B4-R13")
print("\n=== DONE ===")