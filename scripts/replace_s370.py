"""GC-01 Block 71 — Replace S370 entry in docs/MUTATIONS.md (idempotent, typo-fixed).

Idempotent: removes any existing S370 line, appends corrected version.
Works on: clean HEAD (append), working tree with typos (replace), already-correct (no-op).

Typo fixes vs Block 70:
  - "prematuregate" → "premature gate"
  - "кроме тоготолько" → "кроме того только"
"""
from pathlib import Path
import re

p = Path("docs/MUTATIONS.md")
src = p.read_text(encoding="utf-8")

entry = (
    "- **S370** GC-01 vertical slice (Блоки №55-№69): отрицательные пути — "
    "5 xfail сняты (Блок №58), 5 дефектов D1-D5 локализованы и обработаны. "
    "D1 (c4) game_loop.py:1930 — persist_dm_response безусловно в degraded-пути "
    "→ journal получал UUID при отсутствии LLM; fix: journal_entry_id = "
    "`\"\" if _dm_degraded else persist_dm_response(...)` (Блок №64). "
    "D2 (c6) NPC-тик во время player_action — первичный production-gate "
    "(Блоки №65-67) ОТКАТАН (Блок №68): ADR-O-407 (APPROVED-BY-MASTER) "
    "«реализация — отдельная сессия», premature gate ломал d2 (world_snapshot "
    "dependency) и противоречил ADR-O-377(3) «деградация без интеллекта не "
    "останавливает быстрые следствия»; c6 РЕВИЗОВАН (Блок №68): абсолютная "
    "стабильность позиций → identity+location инварианты (ADR-O-201 E18 — "
    "межлокационный переход требует boundary traversal); внутрилокационные "
    "смены graph-узла легальны (MovementEngine — единственный writer, E10 "
    "teleport check). D3 (d1-d3) fixture controlled_mock_provider: MOCK "
    "ставился ДО h.new_game() → initialize_router() перезаписывал cfg; кроме "
    "того только qwen_7b вместо yandexgpt_8b/qwen_3_5_9b — fix: Controller-"
    "pattern, activate() ПОСЛЕ new_game(), MOCK на ВСЕ pool._model_configs."
    "values() (Блоки №64-65). D4 (e1-e3) gl.idle_tick(interventions=...) без "
    "campaign_id — fix: сигнатура @1123, тесты вызывают gl.idle_tick(h."
    "campaign_id, interventions=[...]) (Блок №64). D5 stale ref "
    "_XFAIL_DM_AGENT_CRASH в class docstring удалён (Блок №64). Гейты: "
    "merged 24 теста (12 negative + 12 vertical slice) одной сессией 24 "
    "passed (264.8s); d2 isolated 1 passed (2.5s) post-revert; c6 isolated "
    "1 passed (22.0s) с новыми инвариантами; xfail-маркеры 0 (возврата нет); "
    "staged diff 6 файлов (3 code/test + MUTATIONS + 2 reports) — S366 WIP "
    "(chronicle.py/routes_chronicle.py/chronicle_store.py/causal_linker.py/"
    "test_s366_causal_linker.py/scripts/s366_*.py) исключён pathspec'ом. "
    "Артефакты: reports/gc01_baseline_final.txt, gc01_merged_v1.txt, "
    "gc01_c6_v3.txt, gc01_full_v3.txt, gc01_AB_v2.txt. Открытые риски (вне "
    "скоупа GC-01, после commit): R1 SeederError maid_lusya; R2 RE-D2 "
    "deadlock; R3 await restart_llama_server; R4 ADR-O-407 time-gate — "
    "корневой фикс D2, отдельная сессия. · ✅ · без ADR (test-contract "
    "revision + 1-line prod guard); ADR-O-377/407/201 cited in docstrings\n"
)

new_src, n = re.subn(r"^- \*\*S370\*\*[^\n]*\n", "", src, flags=re.M)
print(f"[INFO] removed {n} existing S370 line(s)")

if not new_src.endswith("\n"):
    new_src += "\n"
new_src += entry

p.write_text(new_src, encoding="utf-8")
print(f"[OK] S370 entry written ({len(entry)} chars)")

content = p.read_text(encoding="utf-8")
assert "prematuregate" not in content, "FAIL: 'prematuregate' typo still present"
assert "тоготолько" not in content, "FAIL: 'тоготолько' typo still present"
assert "premature gate ломал" in content, "FAIL: 'premature gate' not found"
assert "кроме того только qwen_7b" in content, "FAIL: 'кроме того только' not found"
print("[OK] typo check passed")