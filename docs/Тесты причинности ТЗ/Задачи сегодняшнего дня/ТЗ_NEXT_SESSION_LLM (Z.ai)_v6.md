# ТЗ для следующей сессии — RE-D2 deadlock (главный корень тишины NPC) + P4 model migration

> Updated: 2026-11-18 v6
> PREV: v5 (2026-11-15) — P2 deterministic inference + P4 model migration
> CURRENT SESSION: S427 (ветвь Б, 2026-11-18)

## Контекст

S427 закрыл ТЗ-v5 частично + обнаружил ГЛАВНЫЙ корень тишины NPC:

### Что закрыто в S427

**P2 Deterministic inference (infra) — ЧАСТИЧНО:**
- B1-B4: config SSOT-поля детерминизма (`llm_batch_size`, `llm_cont_batching`, `llm_no_mmap`, `llm_seed`, `llm_cpu_fallback`), единый `_build_llama_cmd()` SSOT, mirror в `llm_server_manager.py`, `[DET-ENV]` fingerprint расширен.
- B5-B7: `llm_batch_size: 1→512` (GGML_ASSERT фикс), `model_load_timeout_sec: 120→240`, docstring.
- B9: bare-except парентезация (9 файлов в `backend/app/`) для Python 3.13 совместимости.
- P2 замер: **3/11 PASS (RED)** — ID закрыт (0.137→0.016, главный фронт ТЗ-v5), но SOC/INT/MEM/ATT/BIO/DLG/MUL/CMP persist. CPU mode непрактичен (35+ мин без завершения).
- Эскалация на P4 (Qwen3.5-9B migration) — обязательный следующий шаг.

**Cleanup (ТЗ-v5 P4) — ЗАКРЫТ:**
- A1: `load_npcs_merged` RecursionError — разрыв цикла `registry_builder → load_npcs_merged → chronicle_seeder → intent_compressor → registry_builder`. Прямой glob JSON вместо `load_npcs_merged()` в `registry_builder.py`.
- A2: 3x duplicate `if params.get("grammar")` в benchmark — удалены 2 дубликата.
- A3: Порт benchmark 8183→8181 (SSOT, Устав §19.1.4).

**NPC_SPEECH_SILENCE_ROOT_CAUSE (новый фронт, не из ТЗ-v5):**
- D1 (task_scheduler NPC_SPOKE select) — FIXED. 6/6 regression tests GREEN. Прежний код брал `ev` (loop variable) после цикла — `COMMUNICATION_CLAIM` вместо `NPC_SPOKE` → `text=""` → пузырь не рендерился.
- D-CLASSIFY (dm_router greeting lemmas) — applied. Расширение `_ACTION_LEMMAS` категорией `"dialogue"` (привет, здравствуй, спасибо, извини, прощай).
- D-VERBAL (game_loop verbal-list extension) — applied. Добавлен `"player_interacts"` в verbal-list `game_loop.py:1975`.
- ROOT FIX v2 (PLAYER_SPOKE → response_targets) — UNVERIFIED. Populate `ctx.response_targets[npc_id] = "player"` при PLAYER_SPOKE с `target_id == npc_id`. Оставлен как potential broadcast feature; runtime не подтвердил, что это главный корень.
- SUPERBOX `run_terminal_mvp.py` — production-faithful testbed (S1-S5): player_spawn из tavern.json (58.27, 20.20), NPC speech отображение отдельно от DM narrative, teleport к любому NPC по имени, player_name "Игрок", убран порог Y≥12.5.

### Главная находка S427

**RE-D2 deadlock — ГЛАВНЫЙ корень тишины NPC.**

NPC pipeline работает до последнего шага:
```
Player "Привет Торнин"
  → IntentCompressor → ActionType.DIALOGUE → PLAYER_SPOKE published, target_id=tavern_keeper_tornin ✅
  → DM validator: is_valid=True, LOS populated, nearby_npcs populated ✅
  → TaskScheduler: task-27-tavern_keeper_tornin-4-dlg created ✅
  → DialogueExecutor: запустился ✅
  → router.request_for_agent() ← DEADLOCK (RE-D2)
  → LLM call failed: RE-D2: run_coroutine_threadsafe на собственную петлю
  → NPC_SPOKE не публикуется
  → DM fallback narrative: "Торнин хмурится и утирает стакан, не говоря ни слова"
```

RE-D2 определён в `router.py:911`. `request_for_agent` (sync, L704) использует `run_coroutine_threadsafe` для вызова async LLM из ThreadPool worker. TaskScheduler `_process_tasks_async` запускается через `run_in_executor` — worker блокирует основную петлю, ожидая coroutine, которая должна выполниться в основной петле → deadlock.

## Задачи

### ПРИОРИТЕТ 1 — RE-D2 deadlock (главный корень тишины NPC)

**Файл:** `backend/app/services/llm/router.py:704` (`request_for_agent`), `backend/app/services/execution/dialogue_executor.py:688` (call site), `backend/app/services/game_loop/task_scheduler.py:672` (`_process_tasks_async`).

**Контракт:** после фикса SUPERBOX `Привет Торнин` → `[DIALOGUE_EXEC] LLM call succeeded` → `[NPC Реплики]: [tavern_keeper_tornin → player] (dialogue): <текст>` → NPC_SPOKE published → D1-fixed select NPC_SPOKE → bubble рендерится с NPC speech.

**Варианты фикса (нужен вердикт Мастера по архитектуре LLM routing):**
- **(А)** `DialogueExecutor` → async, `await router.request(...)` напрямую (большой рефакторинг, меняет контракт TaskScheduler).
- **(Б)** `request_for_agent` → использовать `asyncio.to_thread()` для LLM call внутри sync метода (минимальный радиус, но `asyncio.to_thread` требует running loop в том же потоке).
- **(В)** TaskScheduler → запускать `_process_tasks_async` через `asyncio.to_thread()`, не `run_in_executor` (меняет threading модель).

**Археология перед фиксом:** прочитать `router.py:704-920` (полный `request_for_agent` + RE-D2 detection), `dialogue_executor.py:680-730` (LLM call site), `task_scheduler.py:672-760` (`_process_tasks_async` + ThreadPool). Не гадать — только по реальному коду.

### ПРИОРИТЕТ 2 — P4 Model migration (эскалация с P2 RED)

- Qwen3.5-9B: multi-run stddev, scores, VRAM, latency.
- P2 infra уже готов (`_build_llama_cmd()` SSOT) — смена модели = одна строка в `config.py:llama_cpp_model_path`.
- Контракт: 3 прогона benchmark `--runs 3` → stddev <0.02 на ALL 11 модулей.
- Сравнить с S426 baseline + S427 P2 Lumimaid (`benchmark_p2_det_multi.json`).
- Если Qwen3.5-9B GREEN → миграция production.
- Если Qwen3.5-9B тоже RED → inherent non-determinism на all models → пересмотр архитектуры sampling (temperature=0.0 + top-k=1 = greedy).

### ПРИОРИТЕТ 3 — ROOT FIX v2 verification (NPC_SPEECH_SILENCE)

**Файл:** `backend/app/services/tick_orchestrator.py` (L2100+, ROOT FIX v2 block).

ROOT FIX v2 (PLAYER_SPOKE → response_targets populate) оставлен как UNVERIFIED. Runtime показал `pending=0` даже после v2 — но DialogueExecutor всё равно запустился (через `_ensure_direct_player_reply` или другой путь).

**Задача:** после фикса RE-D2 проверить, нужен ли ROOT FIX v2. Если NPC_SPOKE появляется без него — отметить как UNNEEDED, удалить или оставить как broadcast feature. Если NPC_SPOKE появляется только для targeted dialogue, но не для broadcast — ROOT FIX v2 может иметь ценность для broadcast.

**Не удалять без вердикта Мастера** (принцип: «не уничтожать полезную ветку развития из-за ошибочной диагностики»).

### ПРИОРИТЕТ 4 — Foreign IPT violations на _Говори!_1 (из ТЗ-v5, не трогал)

- `decision_hub.py:2031` silent-failure
- `causality_manifest.py` orphan (claim_source_id, trigger_source_id)
- `life_project_resolver.py` setattr_unauthorized (10x)

Эти violations остаются в IPT как TECH_DEBT_NOTE (ТЗ-v5 запрет п.5 «Не трогай foreign WIP»). Не блокируют NPC speech pipeline, но загрязняют IPT baseline.

## TECH_DEBT_NOTE (зафиксировать в MUTATIONS)

1. **§3.12 ОКНО ТИШИНЫ** — пере-широкий протокол `Get-Process python*` блокирует массового пользователя (VS Code Codex/Cline/Qwen). LLM Runtime Unification (S418-420) уже решил port conflict через lease. Нужен smart-вариант: ждать только процессы с ENIGMA-маркерами в command line + слушающие :8181/:8182/:8000.

2. **`ensure_llm` 10s timeout** — недостаточен для холодного старта `--no-mmap` (120-180s). Нужен long-timeout path через прямой broker /ensure (прецедент `e0_t2b2_live_autonomous_dialogue.py:6`).

3. **Python 3.13 SyntaxError** — 9 bare-except `except X, Y:` парентезированы (B9), но PEP 758 работает только на 3.14. Если массовый пользователь на 3.13 — могут быть другие несовместимости. `.venv` = Python 3.13.14, payload = 3.14.3.

4. **`PROBE_FAIL] INV-SC-1-8-SPATIAL-COHERENCE: SC-4 FAIL: NPC 'maid_lusya' pos (57.98, 11.89) too far from node 'kitchen_bed_2' (43.48, 11.28)`** — NPC positions в tavern.json не соответствуют graph nodes. Не блокирует dialogue pipeline (DM validator пропускает), но инвариант SC-4 красный.

5. **CCH_SEED warnings** — десятки «связь на неразрешённую сущность (hint='...')» и «valence='None' без числа». Не блокируют pipeline, но загрязняют лог. CanonicalRegistry bridge (USL-1.5) может часть закрыть.

## Что НЕ делать

1. Не объявлять модель READY на single-run (ТЗ-v5 запрет п.1 — наследуется).
2. Не сравнивать по single-run (ТЗ-v5 запрет п.2 — наследуется).
3. Не trust ID/CMP без stddev (ТЗ-v5 запрет п.3 — наследуется).
4. Не amend (ТЗ-v5 запрет п.4 — наследуется).
5. Не трогай foreign WIP (ТЗ-v5 запрет п.5 — наследуется). Foreign IPT violations (P4) — только TECH_DEBT_NOTE.
6. Не удалять ROOT FIX v2 без вердикта Мастера (принцип S427: «не уничтожать полезную ветку развития»).
7. Не чинить RE-D2 без археологии `router.py:704-920` — это архитектурный вопрос async/sync, не точечный патч.
8. Не использовать SUPERBOX с хардкодом `(6.5, 5.5)` — только player_spawn из tavern.json (S1 fix).

## Ключевые файлы

### Артефакты сессии S427

- **D1 regression tests:** `backend/tests/micro/test_d1_dialogue_cache_npc_spoke.py` (6 cases, GREEN)
- **ROOT FIX v2 regression tests:** `backend/tests/micro/test_player_spoke_response_targets.py` (6 cases, GREEN, но runtime UNVERIFIED)
- **SUPERBOX testbed:** `backend/tests/sandbox/SUPERBOX/run_terminal_mvp.py` (production-faithful: player_spawn из tavern.json, NPC speech отображение, teleport по имени)
- **P2 benchmark (RED):** `backend/reports/benchmark_p2_det_multi.json` (3/11 PASS, ID закрыт 0.137→0.016, SOC катастрофа 0.0217→0.2009)
- **S426 baselines:** `backend/reports/benchmark_ab_{a_no_grammar,b_grammar}_multi.json`

### Файлы-цели для следующих сессий

- **RE-D2:** `backend/app/services/llm/router.py:704` (`request_for_agent`), `backend/app/services/execution/dialogue_executor.py:688` (call site), `backend/app/services/game_loop/task_scheduler.py:672` (`_process_tasks_async`)
- **P4 migration:** `backend/app/core/config.py:llama_cpp_model_path` (одна строка)
- **Benchmark:** `backend/tests/LLM Benchmark/ENIGMA_LLM_COMPREHENSIVE_BENCHMARK.py`
- **Это ТЗ:** `docs/Почти Актуальные TZ/ТЗ_NEXT_SESSION_LLM_v6.md`

### Археологические находки (для преемника)

- **DM classify_action contract:** `hub_event.event_type` ∈ `{"player_interacts", "player_spoke", "dialogue"}` (DM-classified string), НЕ `EventType.PLAYER_SPOKE` enum value. Контракт из `_ensure_direct_player_reply` (npc_tick_pipeline.py:130).
- **TALK в PROACTIVE_INTENTS:** `decision_hub.py:88` — `Intent.TALK` в PROACTIVE_INTENTS. На player turn (`_is_proactive_tick=False`) TALK отфильтровывается (L1061). Если RE-D2 фикс не даст NPC_SPOKE — копать TALK filter (разрешить TALK при `pending_response_target`).
- **`_ensure_direct_player_reply`** (npc_tick_pipeline.py:116) — upgrade'ит existing CommunicationIntent до `player_reply`, но НЕ создаёт новый. Если NPC не сформировал proactive TALK к player — функция no-op.
- **`response_targets` populated** в ОДНОМ месте: `tick_orchestrator.py:2112` (из `_recent_dialogues` TaskScheduler — только NPC_SPOKE entries). PLAYER_SPOKE не попадает — ROOT FIX v2 пытается это починить, но runtime UNVERIFIED.

## Главная находка S427 (для ЗАВЕЩАНИЯ)

**Корень тишины NPC — не в dialogue pipeline, а в LLM router async/sync boundary.**

Чужой отчёт `NPC_SPEECH_SILENCE_ROOT_CAUSE.md` указал на D1/D2/D3 (bubble cache, target selection, coordinates). D1 — VERIFIED defect, починен. Но главный корень — RE-D2 deadlock в `router.request_for_agent()` — не описан в чужом отчёте.

Pipeline работает до последнего шага: player input → PLAYER_SPOKE → task → executor → **LLM call DEADLOCK**. NPC пытается говорить, но LLM-вызов блокирует event loop. После починки RE-D2 NPC начнёт говорить.

**Урок для преемника:** runtime-trace важнее source-inspection. SUPERBOX с корректным player_spawn показал реальную картину: `pending=0` опроверг ROOT FIX, но `[DIALOGUE_EXEC] LLM call failed: RE-D2` указал на главный корень. Без production-faithful testbed любая диагностика — гадание.

> Преемник. RE-D2 deadlock — главный корень тишины NPC. Pipeline работает до LLM call. P2 infra готов для P4 migration. D1 закрыт. ROOT FIX v2 UNVERIFIED — не удалять без вердикта. SUPERBOX — корректный testbed, использовать для проверки фиксов RE-D2. После RE-D2 — P4 (Qwen3.5-9B) для закрытия non-determinism.
