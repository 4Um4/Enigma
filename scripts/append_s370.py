"""GC-01 Block 70 — Append S370 entry to docs/MUTATIONS.md.

Rule §11.1.1: S-number = max(on disk)+1.
Anti-race: assert S370 not already present.
"""
from pathlib import Path
import re

p = Path("docs/MUTATIONS.md")
src = p.read_text(encoding="utf-8")

nums = sorted({int(m.group(1)) for m in re.finditer(r"^- \*\*S(\d+)\*\*", src, re.M)})
mx = max(nums)
new_id = mx + 1
print(f"[INFO] max on disk = S{mx}, new id = S{new_id}")
assert new_id == 370, f"unexpected max: {mx}, expected 369 (S366-S369 TODOs counted)"

assert "**S370**" not in src, "S370 already exists — abort (anti-race §11.1.1)"

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

if not src.endswith("\n"):
    src += "\n"
src += entry
p.write_text(src, encoding="utf-8")
print(f"[OK] S370 appended ({len(entry)} chars)")