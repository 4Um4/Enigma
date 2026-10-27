ADR-O-430 [STANDARD] **IMPACT**

> Детальный аудит одного ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`.
> Эпоха: CCH-S371 (ветвь А). Основания-вердикты Мастера: S371.3-GBNF-STABILITY (матрица A-E — сервер стабилен под GBNF); S371.3-GBNF-PRODUCTION (7/7 acceptance критерий).

## 1. Changed Domains

- LLM-контур: `GenerationParams` +1 field (`grammar: Optional[str] = None`); `llama_cpp_provider` +1 method (`_complete_via_server_with_grammar`); branching в `complete()` — grammar задан → `/completion`, иначе → `/v1/chat/completions` (existing).
- CCH-контур: `biography_decomposer` +loader (`_load_chronicle_grammar`) + передача grammar в `GenerationParams`.
- Конфигурация: новый файл `config/chronicle_decompose.gbnf` (recursive JSON grammar, root требует `}`).
- Behavioral-neutral для остальных consumers: `grammar=None` default → existing path без изменений.

## 2. Downstream Consumers

- **BiographyDecomposer** — единственный consumer grammar-path. Передаёт `grammar=_load_chronicle_grammar()` в `GenerationParams`. Только `capability=FACT_EXTRACTION`.
- **Остальные consumers** (DM, NPC, rules, memory, world) — `grammar=None` (default), используют `/v1/chat/completions` без изменений.
- **IntentCompressor** — НЕ затронут (отдельный capability `INTENT_COMPRESSION`, не передаёт grammar).
- **Streaming/CLI** — НЕ затронуты (payload 367/479 в llama_cpp_provider не тронуты; мандат §1).

## 3. Runtime Impact

- **Latency:** grammar-path ~2-4.7с на фрагмент (Hermes-3 + GBNF); existing-path ~1-2с. Overhead ~2x — приемлемо для CCH offline-authoring (не tick-critical).
- **VRAM:** без изменений — grammar constraint не требует доп. памяти (sampler overhead в CPU).
- **Server stability:** stability matrix (A-E) + production-тест (7 запросов) — сервер жив. Падения ранее — внешняя нагрузка (вердикт Мастера), не GBNF.
- **Точность:** 7/7 OK (json + items 2-5 + ends_with_brace). Baseline: 3/7 OK @ 2048, 7/7 TRUNCATION.

## 4. Sandbox Tests

- `backend/tests/micro/test_s371_3_gbnf_unit.py` — 9 unit-тестов (mock HTTP): endpoint branching, grammar в payload, response parsing, error handling, grammar static checks.
- `scripts/s371_3_gbnf_production_test.py` — серверный production-тест на 7 фрагментах (reports/s371_3_gbnf_production_20261027_232135.json).
- Регрессия: `test_chronicle_cch2.py` (24) + `test_s371_raw_response_preserved.py` (5) + `test_s371_3_pre_response_format.py` (3) = 41/41 PASS.
- IPT: 54/0/0 (0 CRITICAL).

## 5. Rollback

- Удалить `grammar=_grammar` из `GenerationParams` в `biography_decomposer.py:172` → fallback на `/v1/chat/completions` (existing path).
- Или удалить `config/chronicle_decompose.gbnf` → `_load_chronicle_grammar()` вернёт None → `grammar=None` → existing path.
- Или удалить поле `grammar` из `GenerationParams` → `AttributeError` ловится unit-тестом `test_no_grammar_uses_chat_endpoint` (регрессия).
- Коммиты: `5c84e5fe` (основной код) + `115cd724` (bug-фикс пути) — `git revert` обоих возвращает исходное состояние.

## 6. Риски

1. **GBNF version dependency** — грамматика привязана к текущей версии llama-server. При обновлении синтаксис может измениться. Тесты `test_grammar_file_exists` + `test_grammar_requires_closing_brace` ловят регрессии.
2. **Recursive grammar overhead** — на коротких промптах (stability matrix) latency 300-450ms; на production (1670+ токенов промпта) — 1.8-4.7с. Overhead ~2x vs existing-path.
3. **Только FACT_EXTRACTION** — если другие capabilities потребуют GBNF, нужно отдельное решение (не расширять автоматически).
4. **Hermes-3 migration** — production-тест проведён на Hermes-3-Llama-3.1-8B Q4_K_M. При смене модели грамматика должна пережить (unit-тест `test_grammar_requires_closing_brace` — модель-агностик).