# -*- coding: utf-8 -*-
"""S368: закрытие — заменить строку S368 в MUTATIONS.md (TODO → DONE)."""
from pathlib import Path
import re

p = Path("docs/MUTATIONS.md")
src = p.read_text(encoding="utf-8", newline="")

# Найти строку S368 (TODO) и заменить целиком
pattern = re.compile(
    r'^- \*\*S368\*\* \(TODO\).*?$',
    re.MULTILINE | re.DOTALL
)
new_line = (
    '- **S368** (DONE 2026-10-25) CCH: age extraction fallback — диагностика локализовала корень (LLM Qwen2.5-7B Q6_K не кладёт `age` в `draft_payload` вопреки якорю в prompt и инструкции system-prompt:39, хотя regex-якорь извлечён и передан). Минимальный фикс: детерминированный route-fallback в `routes_chronicle.py` §S368 (строки 263-285) — если `_age_value is None and _it.kind is EntryKind.EVENT and len(result.age_anchors) == 1` и в `result.items` ровно одно EVENT, берётся `result.age_anchors[0]`. Контрактная семантика соблюдена: age=атрибут события (system-prompt:39), не протекает в RELATIONSHIP/EFFECT; множественность якорей или событий → None (§ENIGMA-003 «не выдумываем»); явный LLM `age` приоритетнее fallback. Регрессия: 10 unit-тестов (`test_s368_age_route_fallback.py` — хелпер-реплика) + 4 интеграционных (`test_s368_route_integration.py` — боевой `routes_chronicle.decompose_fragment` + настоящий `ChronicleStore` с tmp_path, полный путь DecomposeRequest → route → save_draft → load_draft → ChronicleEntry.historical_age); S365/S367 15/15 green; IPT 53/0 (0 CRITICAL). Дамп `scripts/s368_age_dump.py` (живая LLM, Qwen2.5-7B Q6_K, фрагмент maid_lusya): `[S368_METRIC] items=3 with_age_int=1` (EVENT получил route_age=8, RELATIONSHIP/EFFECT → None). Полный прогон 6 NPC через `scripts/redecompose_all_npc.py --no-canonize --no-llm --campaign silver_wolf` (126 фрагментов, 364 items в draft): WithAge **10/364** против baseline 1/362 в каноне — 10x улучшение; per-NPC: guard_borko 5, maid_lusya 3, tavern_keeper_tornin 2 (NPC без возрастных якорей в author_text: blacksmith_orm, merchant_goran, thief_shadow → корректно 0). Артефакты: `reports/s368_age_dump.txt`, `reports/s368_full_run.txt`. · ✅ · без ADR (минимальный детерминированный fallback в существующем route-контракте, BE-контракт не изменён)'
)

if '(DONE 2026-10-25) CCH: age extraction fallback' in src:
    print("MUTATIONS: ALREADY APPLIED")
elif pattern.search(src):
    src = pattern.sub(lambda m: new_line, src, count=1)
    p.write_text(src, encoding="utf-8", newline="")
    print("MUTATIONS: replaced via regex")
else:
    print("MUTATIONS: NOT FOUND")
    raise SystemExit(1)
