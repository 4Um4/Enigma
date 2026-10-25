# ENIGMA — Handoff S368 → CCH-6 (закрывающий S368)

**Дата:** 2026-10-25 | **От:** архитектор S368 | **Кому:** архитектор CCH-6 (калибровка needs_confirmation)
**Принцип:** продолжение ветви А (CCH-фронтир). S368 закрыт: диагностика + минимальный фикс + регрессия + IPT + полный прогон 6 NPC.

## 1. Статус ветки А
- **S365** CLOSED (age regex+schema+route+CoT-fix, 7 regression PASS)
- **S366** CLOSED (causal_linker, 4-слойная причинность) — WIP-код, ждёт коммита №1
- **S367** CLOSED (roster-инъекция в build_user_prompt) — WIP-код, ждёт коммита №2
- **S368** CLOSED 2026-10-25 (age extraction fallback) — ждёт коммита №4
- IPT 53/0, 0 CRITICAL — зелёный (после применения патча S368)

## 2. Что сделано в S368

### 2.1 Диагностика
- `WithAge` — docs-only метрика (roadmap:288, MUTATIONS:366); кода-счётчика никогда не было.
- Формула (реконструкция): count(ChronicleEntry in draft where historical_age != null AND provenance == LLM_DRAFT).
- Корень доказан на живой LLM Qwen2.5-7B Q6_K: regex ловит якорь `[8]`, передаёт в user-prompt, но LLM не кладёт `age` в `draft_payload` вопреки инструкции system-prompt:39.
- Гипотеза «LLM не кладёт age» (MUTATIONS:366) — доказана дампом `reports/s368_age_dump.txt`.

### 2.2 Фикс (минимальный, route-fallback)
**Файл:** `backend/app/api/routes_chronicle.py` §S368 (строки 263-285).
**Логика:** если `_age_value is None AND _it.kind is EntryKind.EVENT AND result.age_anchors AND len(result.age_anchors) == 1` и `count(EVENT in result.items) == 1` → `_age_value = result.age_anchors[0]`.

**Семантика (соблюдена):**
- age=атрибут СОБЫТИЯ (контракт system-prompt:39) — fallback только для EVENT;
- не протекает в RELATIONSHIP/EFFECT;
- множественность якорей → None (§ENIGMA-003 «не выдумываем»);
- множественность EVENT → None (неопределённость, какому событию соответствует якорь);
- явный LLM `age` приоритетнее fallback;
- строковый `day` и int `day` НЕ становятся age (route их не читает, только `age`/`historical_age`).

### 2.3 Верификация (R3 — все требования)
1. **10 unit-тестов** (`test_s368_age_route_fallback.py`) — хелпер-реплика логики §S368, все ветки: fallback-срабатывание, LLM-priority, отказ при множественности, отказ для не-EVENT, строковый/int day, пустые якоря.
2. **4 интеграционных теста** (`test_s368_route_integration.py`) — боевой `routes_chronicle.decompose_fragment` + настоящий `ChronicleStore` с tmp_path, полный путь: DecomposeRequest → route → save_draft → load_draft → ChronicleEntry.historical_age.
3. **Регрессия S365/S367**: 15/15 green.
4. **IPT 53/0** (0 CRITICAL) — игра жива.
5. **Дамп** (`reports/s368_age_dump.txt`): живая LLM, фрагмент maid_lusya, `[S368_METRIC] items=3 with_age_int=1` (EVENT → route_age=8, RELATIONSHIP/EFFECT → None).
6. **Полный прогон 6 NPC** (`reports/s368_full_run.txt`): `scripts/redecompose_all_npc.py --no-canonize --no-llm --campaign silver_wolf`, 126 фрагментов, 364 items в draft. WithAge **10/364** против baseline 1/362 в каноне — 10x улучшение. Per-NPC: guard_borko 5, maid_lusya 3, tavern_keeper_tornin 2; NPC без возрастных якорей в author_text (blacksmith_orm, merchant_goran, thief_shadow) → корректно 0.

## 3. Файлы S368 (для коммита №4)
- `backend/app/api/routes_chronicle.py` (+15 строк: импорт EntryKind + блок §S368)
- `backend/tests/micro/test_s368_age_route_fallback.py` (НОВ, 10 unit-тестов)
- `backend/tests/micro/test_s368_route_integration.py` (НОВ, 4 integration-теста)
- `scripts/s368_age_dump.py` (НОВ, runtime-археология age-пути)
- `scripts/s368_apply_route_patch_v2.py` (НОВ, патчер для воспроизводимости)
- `scripts/s368_close_mutations.py` (НОВ, патчер MUTATIONS.md)
- `reports/s368_age_dump.txt` (артефакт дампа)
- `reports/s368_full_run.txt` (артефакт полного прогона 6 NPC)
- `docs/MUTATIONS.md` (S368: TODO → DONE)
- `docs/ENIGMA_ROADMAP_v4_11_WPS.md` (CCH-S368: [ ] → [x])
- `docs/HANDOFF_S367_to_S368.md` (УДАЛИТЬ — закрывающий S368)
- `docs/HANDOFF_S368_to_CCH6.md` (НОВ — этот файл)

## 4. План коммитов (R2: изоляция сохранена)
| # | Содержание | Верификация |
|---|---|---|
| №1 | G1: S366 (chronicle.py +128, routes_chronicle.py S366-часть, chronicle_store.py +92, causal_linker.py НОВ, test_s366_causal_linker.py НОВ, scripts/s366_*.py 11 шт) | test_s366 + IPT |
| №2 | G2: S367 (biography_decomposer.py +49, decomposition_normalizer.py +87, prompt +3, test_s367_roster_injection.py НОВ, scripts/s367_*.py 5 шт) | test_s367 + test_s365 + IPT |
| №3 | G3: docs (MUTATIONS S366/S367, roadmap, HANDOFF) | — |
| №4 | G4+S368: routes_chronicle.py §S368, test_s368_*.py, scripts/s368_*.py, reports/s368_*.txt, docs-правки S368 (MUTATIONS/roadmap/HANDOFF) | test_s368 + test_s365 + test_s367 + IPT + дамп |
| №5 | G5: GC01/S370 (26 файлов reports/gc01_*.txt + 8 скриптов append_s370/replace_s370/apply_d1_d5_fixes/d2_root_fix(_v2)/retry_d2_d3/revise_c6/xfail_removal/audit_causes) | tests/gameplay (12+12) |

## 5. CCH-6 — следующая задача (R4)
**Тема:** калибровка `needs_confirmation` (гейт T-CCH-10).
**Вход:** draft 6 NPC из `saves/silver_wolf/chronicle_drafts/` — 10 WithAge, 354 null. Статистика для калибровки.
**Вопросы для отдельного сообщения Мастеру:**
- Должен ли EVENT с `age_anchors` (fallback) получать повышенный `needs_confirmation`? Аргумент pro: age присвоен детерминированно, не LLM; contra: regex надёжнее LLM.
- Порог confidence для LLM_DRAFT → AUTHOR_CONFIRMED в `confirm-author-entries`?

## 6. §7-хвосты (отдельные задачи, вне S368)
1. **Модельный рассинхрон** (Ф17): `default_model = qwen_3_5_9b`, GGUF отсутствует, fallback на Qwen2.5-7B Q6_K. HANDOFF_S367:22 уже отмечал. Не блокирует S368.
2. **roster_mismatch 404** в auto-resolve (`redecompose_all_npc.py`): pre-existing, не S368. Эндпоинт `/resolve` не находит question_id после `save_draft` (вопрос не persistится в open_questions текущего draft?). Отдельная задача — диагностика персистенции вопросов.
3. **JSON-парсинг LLM** (6 NOT_DECOMPOSED в прогоне 6 NPC, "Expecting ',' delimiter"): LLM reliability issue. Возможное направление: усиление system-prompt с примером JSON-схемы; либо retry с temperature=0.0 → 0.1. Не S368.

## 7. Границы (актуальны для CCH-6)
- `routes_chronicle.py` — минимально; схема канона/MODEL_REGISTRY/`_VAGUE_RELATION_MARKERS` — не трогать без ADR.
- `_VAGUE_RELATION_MARKERS` — закрытый реестр (ADR-O-420), расширение = ревизия ADR.
- Источник истины — данные + контракт, не предположение о модели.

## 7b. S371 — LLM JSON Robustness (PLANNED, awaiting decision)

**Статус:** ⏳ PLANNED — ROADMAP ONLY. Записан в roadmap:291 и MUTATIONS:369 (коммит `ac066549`). Не реализован.

**Контекст для приёмника:** обнаружено в полном прогоне S368 (`reports/s368_full_run.txt`) — 6 из 126 фрагментов (4.76%) упали с `DecompositionError: Expecting ',' delimiter` в `decomposition_normalizer.normalize()`. Это ~5% потерь декомпозиции — накопительный технический долг.

**Этапы (записаны в roadmap, не реализованы):**
- S371.0 — воспроизводимая диагностика (blocker для остальных)
- S371.1 — проверка лимита `max_tokens` (2048 vs 4096, один фактор)
- S371.2 — безопасный JSON repair (запрет наивной коррекции скобок/кавычек)
- S371.3 — `json_schema`/GBNF constrained generation (gated by live-server probe)
- S371.4 — `partial_errors` контракт (критерий WhiteSpot vs отклонение)
- S371.5 — prompt/retry (после установления причин)

**Вход в S371.0 (для приёмника):**
- Корпус: `reports/s368_full_run.txt` (126 фрагментов, 6 failures)
- 6 failed fragments: goran[1,9,14], lusya[8], orm[19], shadow[8,10], tornin[13]
- Модель: Qwen2.5-7B Q6_K (fallback, не qwen_3_5_9b — см. §7-хвост 1)
- Параметры: temperature=0.0, max_tokens=2048, response_format=json_object
- Каждую из 6 ошибок классифицировать: truncation? trailing comma? escape? Unicode? unknown?

**Принципы (из задания Мастера):** один фактор за эксперимент · фиксированный корпус · никакого regex-парсинга JSON · не менять каноническую схему · не менять модель · не объединять интервенции.

**Зависимости:** dep: CCH-S368 (baseline-корпус готов); dep: ADR-O-420 (контракт CCH-2 — не трогать без ADR-ревизии). rel: S365, S367, S368, S369.

**Вопрос для отдельного сообщения Мастеру (по правилу развилок):** стартовать S371.0 сейчас (вариант α — не инвазивно, только чтение + классификация 6 ошибок), держать PLANNED (β — приоритет CCH-6), или параллельно с CCH-6 (γ). Моя рекомендация — α.

---

## 8. IPT baseline
53 passed / 0 failed / 0 CRITICAL — зелёный (после применения патча S368).

