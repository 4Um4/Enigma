# ТЗ — АУДИТ ГОТОВНОСТИ К ЭПОХЕ 7 — АДДЕНДУМ 3
## Новые баги и расхождения, не вошедшие в Addendum 2

**Версия:** 1.0 · 2026-08-13
**Назначение:** Дополнение к `TZ_PHASE7_READINESS_AUDIT_ADDENDUM2_SLEEP_AND_DRIFT.md`. Содержит **75 новых багов и расхождений**, обнаруженных в коде, которые не позволяют проекту перейти на Эпоху 7 (Фазу 2→3). Все находки подтверждены чтением исходников и логов `sleep_test_v27.log`.

**Заключение:** Addendum 2 недооценивает технический долг. Помимо «отсутствующих файлов» (cognition/, prophecy_engine, belief_merger и т.д.), в существующем коде есть **минимум 10 критических багов**, каждый из которых независимо блокирует переход: от `NameError` в `pipeline_runner.py:140` до `TOCTOU` race в `game_loop/__init__.py:359` и нулевой работы LLM-кэша.

---

## 0. КРАТКАЯ СВОДКА НОВЫХ НАХОДОК

| Категория | CRITICAL | HIGH | MEDIUM | LOW | Итого |
|-----------|----------|------|--------|-----|------|
| LLM Cache & Provider | 5 | 8 | 5 | 1 | 19 |
| ADR-Net | 3 | 2 | 5 | 1 | 11 |
| Audit Log | 0 | 3 | 2 | 0 | 5 |
| Cognition / Belief / Perception | 4 | 6 | 0 | 5 | 15 |
| Game Loop / Tick Orchestrator | 6 | 9 | 13 | 7 | 35 |
| Replay / Determinism | 0 | 5 | 2 | 0 | 7 |
| **Итого новых багов** | **18** | **33** | **27** | **14** | **92** |

> Фактический счётчик — 92 находки, не 75, т.к. в нескольких пунктах сгруппированы связанные подкатегории.

---

## 1. CRITICAL — независимо блокируют Фазу 7

### C-01. `pipeline_runner.py:140` — `NameError: _l1_events` в каждой боевой ситуации

```python
if mutation.l1_drift_events and _svc and _svc.memory_manager:
    _chronicle = ...
    if _chronicle:
        for _event in _l1_events:    # ← переменная не определена в этом модуле
            _chronicle.append(_event)
```

`_l1_events` локальна для `npc_tick_pipeline.py:150`. На любом тике с TraitDriftEvents (бой, атака, урон) падает `NameError`. L1-хроника **никогда** не получает события дрейфа, что ломает `PatternDetector` и трекинг identity drift — все, кто зависит от L1 chronicle, работают на пустых данных.

**Fix:** `for _event in mutation.l1_drift_events:` — 1-строчный фикс.

---

### C-02. `game_loop/__init__.py:359-363` — TOCTOU race в `_get_skip_lock`

```python
def _get_skip_lock(self, campaign_id: str) -> threading.Lock:
    if campaign_id not in self._skip_locks:
        self._skip_locks[campaign_id] = threading.Lock()
    return self._skip_locks[campaign_id]
```

Классический check-then-act race. Два потока могут одновременно провалить `if`, создать разные `Lock`, и каждый «захватит» свой (бесполезный) лок. Параллельные `skip_time` для одной кампании могут повредить scene_state. Это особенно важно для Phase 7, где multi-location WorldTick становится нормой.

**Fix:** `self._skip_locks.setdefault(campaign_id, threading.Lock())`.

---

### C-03. `commit_phase.py:116-119` — idle-тики стирают всех NPC из persistence

```python
# idle branch (no interventions):
saved = orchestrator._scene_manager.commit(
    campaign_id=ctx.campaign_id,
    scene_state=ctx.scene_state,
    npc_dicts=ctx.npc_states,   # ← пусто при idle, т.к. _phase_1_input_merge ретюрнится раньше
    significant_events=ctx.significant_events or [],
)
```

`ctx.npc_states` заполняется только внутри `_phase_1_input_merge` (строка 935) **после** раннего `return` на строке 930. На idle-тиках (т.е. без player interventions) список NPC пуст, и `commit()` **затирает** всех NPC из сессии. `GameLoop.idle_tick` — это канонический вход, и он никогда не устанавливает `interventions`. Каждый idle-save разрушает кампанию.

**Fix:** использовать `ctx.all_npcs_raw` (заполняется в `_run_core_phases`).

---

### C-04. `commit_phase.py:51-59` — `delta_buffer` не чистится при ошибке агрегации

```python
if ctx.delta_buffer:
    _aggregated = aggregate_deltas(ctx.delta_buffer)
    if _aggregated and orchestrator._state_applicator:
        orchestrator._state_applicator.apply_batch(...)
        ctx.delta_buffer.clear()   # ← только при успехе
```

Если `_aggregated is None` или `_state_applicator is None`, дельты утекают в следующий тик. В комбинации с ленивой инициализацией `_state_applicator` в new-game потоке это даёт эффект «призраков»: stale social/combat дельты повторно применяются через несколько тиков.

**Fix:** `ctx.delta_buffer.clear()` вынести за внутренний `if`.

---

### C-05. `tick_orchestrator.py:628-635` — один сбой локации абортит весь тик кампании

```python
try:
    self._run_core_phases(ctx, tick_fully=_tick_fully)
except Exception as e:
    logger.error(...)
    return TickResultDTO(status="error", error=str(e))   # ← break из цикла по _all_scenes
```

Цикл по `_all_scenes.items()` (строка 531) немедленно возвращается на первом же исключении — все остальные локации кампании остаются необработанными. Phase 7 требует multi-location целостности; текущий код её не обеспечивает.

**Fix:** продолжать цикл, собирать per-location результаты, отмечать только упавшую локацию как `error`.

---

### C-06. `game_loop/__init__.py:2094-2097` — NPC orchestration errors молча проглатываются

```python
except Exception as e:
    logger.error(f"[GAME_LOOP] DM/NPC phase error: {e}", exc_info=True)
    python_engines_result = {"dm_result": None, "npc_contexts": []}
    _player_result = TickPlayerResultDTO()      # ← пустой DTO, без npc_contexts, без observed_facts
```

Пайплайн продолжает работать с пустым NPC-результатом — DM-агент не получает NPC-контекст и генерирует пустую наррацию. Пользователь видит «ничего не произошло» без какого-либо surfaced error. Это худший вид swallow — error логируется на ERROR, но ответ клиенту 200 OK с пустым телом. Любой реальный баг в NPC-фазе маскируется.

**Fix:** re-raise, либо вернуть `ChatTurnResponse(dm_response="[SYSTEM: NPC pipeline failed]", status_code=500)`.

---

### C-07. `routes.py:442-455` — `CrystallizedBelief.target_npc`AttributeError в API

```python
result["crystallized_beliefs"] = [
    {
        "target": b.target_npc,                       # ← AttributeError: нет такого поля
        "trust": getattr(b, "trust", 0.0),            # ← всегда 0.0
        "fear":  getattr(b, "fear", 0.0),             # ← всегда 0.0
        "affection": getattr(b, "affection", 0.0),    # ← всегда 0.0
    } for b in _beliefs
]
```

`CrystallizedBelief` (`identity_events.py:62-75`) имеет только `{source_id, trait, weight, last_updated_tick}`. Эндпоинт ожидает поля из фантомной схемы — **крашится при первом непустом beliefs-списке**. Блокирует introspection/debug-тулинг для Phase 7.

**Fix:** использовать `source_id`, `trait`, `weight` напрямую.

---

### C-08. ADR-O-330 number collision — Prophecy Causality Law vs Spatial Agency Law

`docs/audits/ADR-O-330_IMPACT.md` уже занят документом **«Spatial Agency Law»** (заголовок, строка 1). Однако `ENIGMA_ROADMAP.md:309,317` и Addendum 2 §4 используют тот же номер для **«Prophecy Causality Law»** (Phase 7 gate). Гейт «ADR-O-330 green» формально проходит (текущий ADR-O-330 = Accepted), но реально Prophecy Law ADR не существует.

**Fix:** выделить Prophecy Causality Law в новый ADR-O-331+ и обновить roadmap.

---

### C-09. `router.py:501` — LLM-кэш читается только в `replay_playback`, в production hot-path нет

```python
if settings.replay_playback:           # ← False в production
    cached = self._store.get_llm_call(...)
    if cached:
        return cached
```

В обычной игре кэш **никогда не читается**. Каждый запрос идёт напрямую к LLM. Addendum 2 сообщает «0% hit rate» — но это не потому, что кэш hash-only, а потому что **кэш не используется в hot-path вообще**. §1.6 гейт «≥35%» физически недостижим без этого фикса.

---

### C-10. `router.py:569-582` — LLM-кэш-запись недостижим (settings.replay_record всегда False)

```python
if settings.replay_record:                # ← False по умолчанию
    _store.record_llm_call(...)
```

`settings.replay_record` по умолчанию `False` (`config.py:58`) и **нигде** в коде не выставляется в `True`. Даже `replay_player.py:38` ставит его в `False`. Кэш пустой → lookup всегда miss → 0% hit rate. Это **корневая причина** симптома из Addendum 2.

**Fix:** `settings.replay_record = True` в `game_loop/__init__.py:225` блоке, когда `replay_mode != "off"`. 1-строчный фикс разблокирует весь кэш.

---

### C-11. `router.py:516-550` — worker-thread path никогда не пишет в кэш

Worker-thread ветка `return`s на строке 544/548 **до** блока cache-write на строке 569. Все LLM-вызовы из worker-потоков (TELEGRAPH, player-action) не кэшируются. Кэш частичен даже при `replay_record=True`.

---

### C-12. `provider_manager.py:167-172` — sync `get_model()` без потоко-безопасной блокировки

`get_model()` — синхронный метод, вызывает `_load_model` напрямую, **не** захватывая `_pool_lock` (asyncio.Lock) или `_switch_semaphore`. Asyncio-lock защищает только от coroutine races, не от thread races. Router worker-thread (`router.py:516-550`) и main-thread могут одновременно вызвать `pool.get_model()` → race на `_active_model`/`_active_key` → VRAM corruption или double-load на 8GB GPU.

**Fix:** добавить `threading.Lock` в `ModelPool.get_model`/`_load_model`.

---

### C-13. `llama_cpp_provider.py:310` — CLI-режим возвращает stderr как LLM-ответ

```python
return stdout.strip() or stderr.strip()
```

Если stdout пуст (модель ничего не сгенерировала), возвращается **stderr** как LLM-ответ. Сообщения типа `"error: model not found"` или `"llama_model_load: failed"` возвращаются как DM/NPC нарратив. Тихая контентная порча.

Дополнительно `_run_cli_process` (строки 296-315) **не проверяет** `self._cli_process.returncode` — ненулевой exit code (краш, OOM) трактуется как успешный ответ.

**Fix:** проверять returncode; `raise` при пустом stdout; не возвращать stderr как контент.

---

### C-14. `llama_cpp_provider.py:518-519` — `stream_tokens` yieldит ошибку как токен

```python
except urllib.error.URLError as e:
    yield f"\n[Ошибка соединения: {e}]"
```

При обрыве соединения в середине стрима провайдер **yieldит сообщение об ошибке как LLM-токен**. DM/NPC нарратив получает инъекцию `"\n[Ошибка соединения: ...]"`. Должно `raise`, не `yield`.

---

### C-15. `belief_crystallization_engine.py:111` — убегающая положительная обратная связь

```python
decayed_weight = existing.weight - (base_weight * TRAUMA_MULTIPLIER)   # отрицательно
if decayed_weight <= 0.0:
    new_weight = min(abs(decayed_weight), MAX_WEIGHT)   # ← BUG: чем сильнее нарушение, тем больше new_weight
```

При `TRAUMA_MULTIPLIER=6` и `base_weight=0.5`, `existing.weight=0.4` → `decayed_weight = 0.4 - 3.0 = -2.6` → `abs(-2.6) = 2.6` → `min(2.6, 1.0) = 1.0`. Чем сильнее опровергнуто убеждение, тем **сильнее** новое противоположное (сатурируется на MAX_WEIGHT=1.0). Подтверждается логами `sleep_test_v27.log` — почти все `Crystallized:` имеют `weight=1.00`. Создаёт патологический belief flip-flopping.

**Fix:** `min(base_weight, MAX_WEIGHT)` или `min(abs(decayed_weight) * 0.1, MAX_WEIGHT)`.

---

### C-16. `memory_manager.py:300-310` — dead second writer, `assess_beliefs` output discarded

```python
try:
    self.assess_beliefs(...)   # ← return value List[Tuple[BeliefType, BeliefFragment]] DISCARDED
except Exception as e:
    logger.warning(...)
```

`assess_beliefs` (строка 771) вычисляет обновления beliefs через `CoherenceBeliefAggregator`, но результат **никогда** не записывается в `state.beliefs.update()`. Только `BeliefTransitionEngine` (`belief_transition_engine.py:153, 190`) реально пишет. Дока `BeliefState` (`beliefs.py:50-73`) устарела — «два writer'а без merger» уже не существует. Требование Addendum 2 к `belief_merger.py` основано на ложной предпосылке: нет второго writer'а, чтобы мерджить.

---

### C-17. `belief_crystallization_engine.py:64, 96, 120, 130` — dict key collision по `source_id` только

`updated_beliefs: Dict[str, CrystallizedBelief]` ключится по `source_id` одному. Если NPC имеет и `fear`- и `trust`-убеждение к одному source, второе перезаписывает первое. Phase 7 ToM требует множественные beliefs на (holder, about) — схема должна стать `Dict[Tuple[str, str], CrystallizedBelief]` (ключ `(source_id, trait)`).

---

### C-18. §19 spec PC-19-17 устарел — `NpcTickPipeline.run()` уже не принимает `svc`

`docs/Почти Актуальные TZ/VZ/TZ_§19_Predictive_Perception_Dynamics.md:1896` указывает PC-19-17 как «ЧАСТИЧНО» с формулировкой «`NpcTickPipeline.run()` всё ещё принимает `svc: Any`». Реально `npc_tick_pipeline.py:114-118` уже чистый reducer:

```python
@staticmethod
def run(state: TickState, drf_ctx=None, rng_factory=None) -> TickMutation: ...
```

`svc` параметра нет. PC-19-17 фактически закрыт. Спека раздувает open-precondition счётчик и блокирует активацию §19 по несуществующей причине.

---

## 2. HIGH — silent data loss / determinism breaks

### H-01. `replay_store.py:60-71, 212-218` — нет unique constraint, кросс-сессионная загрязнённость

В таблице `llm_calls` нет unique constraint на `(agent_name, prompt_hash, session_id)`. `get_llm_call` возвращает **latest** match `ORDER BY call_id DESC LIMIT 1` по ВСЕМ сессиям. Cache lookup в сессии B может вернуть response из сессии A — нарушение replay determinism.

### H-02. `replay_store.py:24` — race на shared sqlite-connection

`sqlite3.connect(self.db_path, check_same_thread=False)` разделяет коннекцию между потоками без lock. Concurrent `record_llm_call` из worker + main потоков могут интерливиться. Возможны `"database is locked"` ошибки.

### H-03. `replay_recorder.py:39-45` — `INSERT OR REPLACE` стирает предыдущий tick_state

`record_tick_mutation` передаёт `tick_state=None`, который `INSERT OR REPLACE` затирает ранее записанный tick_state NULL'ом. После Phase 5 у записанного тика **нет input snapshot**, ломает replay (нет input → mutation → output цепочки).

**Fix:** использовать `UPDATE tick_snapshots SET tick_mutation_json=? WHERE session_id=? AND tick_id=?`.

### H-04. `replay_player.py:38 + 79` — асимметричная mutation `settings.replay_record`

```python
settings.replay_playback = True
settings.replay_record = False            # ← никогда не восстанавливается
...
finally:
    settings.replay_playback = False      # ← только это восстанавливается
```

После `ReplayPlayer.play()` `settings.replay_record` остаётся `False`. Последующие game-тики молча прекращают запись LLM-вызовов. Будущие replay сломаны.

### H-05. `replay_player.py:42-45` — регрессия tick counter

```python
_scene["tick"] = start_tick           # например 1
self.game_loop.save_scene_state(...)
```

Если `start_tick=1`, а текущий scene на тике 100, persisted tick отматывается к 1. Replay затем идёт с 1, но LifeEngine-кэш и `world_tick.json` остаются на 100. Внутренняя десинхронизация между scene_state["tick"] и TemporalEngine tick.

### H-06. `router.py:510-513` — cache-miss в playback возвращает `""` вместо `raise`

```python
logger.error(f"[LLM_CACHE] MISS in playback mode! ...")
# Возвращает пустую строку, без exception
```

Replay determinism требует cache-miss = fatal. Возврат `""` молча позволяет симуляции расходиться с записанным трейсом. Именно это должен ловить `ReplayDriftError`, но он никогда не выбрасывается.

### H-07. `router.py:569-582` — пустые LLM-ответы записываются в кэш

Комбинация: worker-thread path → `dialogue_executor.py:235-237` swallow → `return ""` → кэш-запись с `response=""`. Кэш накапливает пустые ответы, которые потом переиспользуются. Replay determinism нарушен: тот же prompt может вернуть разный (непустой) ответ от живого LLM.

### H-08. `router.py:499` — хэш только по `prompt`, без `system_prompt` и `params`

`compute_prompt_hash(prompt)` хэширует только `prompt`. Два вызова с одинаковым prompt, но разными `system_prompt` или `max_tokens`/`temperature`/`stop` — коллидируют. Кэш возвращает ответ от первого system_prompt для другого. Корректностный баг, не только перф.

### H-09. `provider_manager.py` — `record_request` / `record_failure` / `mark_error` мертвы

Router вызывает `pool.record_request(...)` под `hasattr` guard — `ModelPool` не имеет метода `record_request` → `hasattr` всегда `False` → метрики **никогда не записываются**. `record_failure`/`mark_error` определены, но не вызываются нигде → `_failure_cache` остаётся пустым → `is_model_available()` никогда не возвращает `False` из-за failure → **нет backoff**. `error_count` остаётся 0 → status не эскалируется до `ERROR`. Вечно падающая модель ретраится каждый вызов без penalty.

### H-10. `router.py:276-284` — `_abort_generation` только для LlamaCpp

Строка 280 обращается к приватному `pool._active_model` (нужно `pool.active_model` property, строка 348). Строка 281 вызывает `pool._active_model.provider.abort_generation()` — `LlmProvider` base class (`provider.py:58-116`) **не определяет** `abort_generation()`. Только `LlamaCppProvider` имеет его. Если активный провайдер — `OpenAICompatibleProvider`, `AttributeError` → ловится broad `except Exception` (строка 283) → логируется на debug → **silent failure**.

### H-11. `router.py:520-550` — `_request_in_progress` без lock

`self._request_in_progress = True/False` устанавливается без lock. `_worker_lock` (`threading.Lock`) определён на строке 165, но **никогда** не захватывается в `request_for_agent`. Main thread и worker thread могут оба прочитать `False`, оба выставить `True`, оба вызвать `_request_via_pool` → два concurrent LLM-вызова → VRAM OOM риск на 8GB GPU.

### H-12. `router.py:351-370` — fallback loop thrashes VRAM

Fallback loop вызывает `pool.get_model(model_key)` для каждой модели в цепочке. Каждая вызывает `_load_model` → unload + load = полный VRAM swap. Если preferred модель падает, ВСЕ fallback модели загружаются/выгружаются последовательно. Единственный skip — `pool.active_model_key == model_key`, но после первой fallback `active_model_key` меняется и последующие итерации не skip'ают.

### H-13. `openai_compatible_provider.py:70-76` — нет retry, нет backoff

Ловит все исключения, логирует, re-raise. **Нет retry, нет backoff**. Транзитный 429/503 от API сразу фейлит вызов. Сравнить с `LlamaCppProvider`, у которого 3 retry с exponential backoff. Несогласованная устойчивость между провайдерами.

### H-14. `openai_compatible_provider.py:53-60` — игнорирует большинство `GenerationParams`

Только `temperature` и `max_tokens` передаются. Игнорируются `top_p`, `repeat_penalty`, `stop`, `presence_penalty`, `frequency_penalty`, `response_format`. Если router шлёт `stop=["</s>"]`, OpenAI-провайдер его игнорирует → модель генерит после stop-токена.

### H-15. `openai_compatible_provider.py:71` — следует env-прокси

`urllib.request.urlopen(req, timeout=60)` следует `HTTPS_PROXY`/`HTTP_PROXY`. `LlamaCppProvider` явно bypass'ит прокси через `ProxyHandler({})` (строки 197, 389, 493, 558). Несогласованность — OpenAI-вызовы могут пойти через корпоративные прокси, LlamaCpp — нет.

### H-16. `llama_cpp_provider.py:549-567` — `_check_server` false negative без `/health`

Пробует `/health`, потом `""` (root URL). Если llama-server не имеет `/health` и возвращает non-200 на `/` (например 404), провайдер помечается недоступным — **даже если `/v1/chat/completions` работает**. False negative на availability.

### H-17. `llama_cpp_provider.py:544-547, router.py:317, 359` — `is_available()` делает HTTP каждый запрос

`is_available()` вызывает `_check_server()` (HTTP `/health`, 2s timeout). Router вызывает `model_provider.is_available()` на строках 317 и 359 — значит, **каждый LLM-запрос** триггерит `/health` roundtrip. +50-200ms latency за звонок без пользы, когда модель уже загружена и READY.

### H-18. `adr_conflict_detector.py:25` vs `adr_graph.py:56,63` — детектор циклов структурно сломан

`detect_cycles()` фильтрует edge types `["SUPERSEDES", "DEPENDS_ON", "CONFLICTS_WITH"]`, но `ADRGraphBuilder.build()` **только** добавляет `IMPLEMENTS` и `DEFINES` edges. Парсер никогда не извлекает inter-ADR relationship маркеры (нет парсинга "Supersedes:", "Depends on:", "Conflicts with:"). Детектор циклов **всегда возвращает `[]`** — гарантированный false negative.

### H-19. `adr_conflict_detector.py:33-40` — детектор file-ownership — заглушка

```python
def detect_file_ownership_conflicts(self):
    return []   # "пока заглушка"
```

Даже базовый «тот же файл IMPLEMENTS двумя+ ADR» (Double Truth) не детектируется, хотя граф содержит данные (множественные `IMPLEMENTS` edges в один FILE node). Граф строитель данные собирает, детектор их не использует.

### H-20. `adr_parser.py:43` — regex отвергает валидные ADR-ID

```python
_ADR_LINE_REGEX = re.compile(r"`(ADR-[O0-9\-]+)`\s*\[(\w+)\]\s*\*\*(.+?)\*\*")
```

`[O0-9\-]` отвергает буквы T, Z и т.д. ADR-ID типа `ADR-TZ08-1` (упомянутый в докстринге `normalize_adr_id` на строке 17!) **не сматчится**. Парсер их молча пропускает. Также `(\w+)` для type отвергает `[STD-ONT]` (с дефисом).

### H-21. ADR-Net — zero game-loop integration

`ADRConflictDetector`, `ADRGraphBuilder`, `ADRVisualizer` **никогда** не импортируются вне своего пакета. Конфликт-детектор — dead code в runtime — ни tick-orchestrator hook, ни probe integration, ни CI gate. Только `run_parser` импортируется (через `tests/IPT.py:700`).

### H-22. `reputation_engine.py:344` — `List[Any](...)` вызывается как конструктор

```python
"members": List[Any](self._factions[fid].npc_members),
```

`List[Any]` — typing alias, не callable. Вызов `get_all_faction_states()` (debug/UI) кидает `TypeError: 'type' object is not callable`. Должно быть `list(...)`.

### H-23. `reputation_engine.py:192-208` — rivals никогда не обрабатываются

`Faction.rivals` грузится из JSON (`frozenset(fdata.get("rivals", []))` строка 127), но никогда не используется. При `PLAYER_ATTACKS` по guard (law_enforcement) rival `criminal` фракция должна получить +5 репутации, но engine применяет только +2.5 к law_enforcement allies. Faction dynamics сломаны.

### H-24. `reputation_engine.py:165` — `target_npc_id` параметр принят, но не используется

```python
def apply_event_impact(self, event_type, actor_npc_id=None, target_npc_id=None):
    # target_npc_id НИКОГДА не используется в теле функции
```

При атаке игрока на NPC X, фракция X должна пострадать (negative), но вычисляется только actor (player). Репутация фракции target не меняется. Мёртвый параметр / отсутствующая логика.

### H-25. `reputation_engine.py:255-300` — нет mutex на `apply_deltas`

ReputationEngine вызывается из ReputationDecayHandler (idle) и из event subscribers (concurrent). `state.reputation = round(new_rep, 2)` — non-atomic read-modify-write. Concurrent вызовы могут потерять дельты.

### H-26. `kernel_rng.py:42-50` — salt optional, default `""` → stream collisions

```python
def __init__(self, tick: int, npc_id: str, salt: str = ""):
    seed_raw = f"{tick}:{npc_id}:{salt}".encode("utf-8")
```

Два вызывающих `KernelRNG(tick=N, npc_id="X")` для разных целей (decision vs perception vs behavior) получают **одинаковый seed** → одинаковое первое случайное число. В `npc_tick_pipeline.py:507` DecisionHub RNG создаётся без salt — любой другой RNG-consumer в том же тике для того же NPC коррелирует с decision stream.

**Fix:** сделать `salt` обязательным или ввести per-consumer salt convention.

### H-27. `dto.py:128-147` — `rng_for()` возвращает свежий RNG каждый вызов (no caching)

```python
def rng_for(self, npc_id: str) -> KernelRNG:
    return self.rng_factory(npc_id)   # ← создаёт новый инстанс каждый раз
```

Два последовательных `ctx.rng_for("X").random()` возвращают **одинаковое** значение (оба конструируют свежий RNG с тем же seed). Determinism технически сохранён, но второе случайное число в последовательности теряется. Фазы, потребляющие несколько random'ов на NPC за тик, получают коррелированные draws.

### H-28. `tick_orchestrator.py:1996-2000` — DRF overlay мёртв для CommunicationIntent

```python
# BUG-CORE-015 FIX: CommunicationIntent не имеет поля priority,
# DRF overlay применяется только к интентам с этим полем.
if not hasattr(_intent, "priority"):
    continue
```

Коммент сам признаёт: CommunicationIntent (основной тип intent из Phase 5) не имеет `priority`, весь DRF scoring overlay loop — no-op для диалога. DRF field pressures никогда не модулируют NPC speech priority. Phase 7 DRF verification не может пройти.

### H-29. `state_applicator.py:259-266, 394-397, 493-496` — три "return original on error" swallow

"Commit Kernel" на строке 1332 явно комментирует: «try/except УНИЧТОЖЕН. Если _apply_deltas падает — падает весь тик». Но **внешние** `apply()`, `apply_physical()`, `apply_deltas_only()` всё ещё оборачивают тела в `except Exception: return state` (возвращают unmutated original). Ошибки мутации молча теряют дельты для одного NPC, тик продолжается. Несогласованный контракт — Phase 5 думает, что ошибки крашат тик, applicator их прячет.

### H-30. `pipeline_runner.py:113-130` — sleep guard использует substring match

```python
if "schedule" not in _reason:
    continue   # drop intent
```

- `"schedule:sleeping"` → сохранён (верно).
- `"scheduled_wakeup"` → сохранён (слово "schedule" — подстрока "scheduled", неверно, это не schedule-driven intent).
- `"sleep:wake_up"` → отброшен (неверно, это schedule-driven intent без слова "schedule").

И false positives (пропуск не-schedule intent будит спящего NPC), и false negatives (дроп schedule intent).

### H-31. `pipeline_runner.py:269` — intent-type-mapping swallow

```python
except Exception as e:
    logger.warning(f"[B5-FIX] silent failure suppressed: {e}")
```

Сломанные `intent_type` строки молча падают в `NpcIntent.TALK`. NPC говорит «привет» вместо атаки. Тег "B5-FIX", но само suppression и есть баг.

### H-32. `game_loop/__init__.py:1747` — `_match` всегда None

```python
_match = None                                            # строка 1738
...
_player_data_dict = _match.dict() if _match else None    # строка 1747
```

`_match` никогда не переприсваивается в этой функции. `resolve_player_intent` вызывается с `player_dict=None` на каждом player turn — профиль/character sheet никогда не доходит до intent resolution.

### H-33. `game_loop/__init__.py:1818-1820` → 2094 — raise в `_execute_dm_and_intent_resolution` ловится молча

Строка 1820 корректно `raise`, но caller на 2094 ловит и проглатывает (см. C-06). Эффективно swallow по индирекции.

### H-34. `game_loop/__init__.py:1703-1708` — finalize pipeline error swallowed, `npc_result = {}`

```python
except Exception as _fin_err:
    logger.error(f"[GAME_LOOP] Finalize error: {_fin_err}", exc_info=True)
    npc_result = {}   # ← пусто
    shared_context.npc_contexts = (...)
```

DM-агент получает `npc_result={}` и генерирует пустую наррацию. Игрок не видит NPC-реакций, хотя NPC могли говорить в течение тика.

### H-35. `game_loop/__init__.py:1997-2003` — fire-and-forget `asyncio.create_task` без ref holder

```python
asyncio.create_task(
    asyncio.to_thread(self.world_scheduler.maybe_tick, world_id, settings.world_tick_minutes)
)
```

Per Python docs: "Save a reference to the result of this function, to avoid a task disappearing mid-execution." Task также unguarded — исключения молча умирают. World-tick background updates могут быть GC'ны до завершения или падать невидимо.

### H-36. `phases/memory.py:50-53, 74-77, 120-121` — три дополнительных swallow-and-log

- Строка 50: `compress_narrative_cache` failure → narrative_cache stale.
- Строка 74: `check_identity_promotion` failure → identity traits не продвигаются.
- Строка 120: `run_decay_and_resonance` failure → identity weights не применяются.

Все три — `except Exception as e: logger.warning(...)` + continue. Addendum 2 пропустил (только `reduction.py:206, 216` отмечены).

### H-37. `phases/post_decision.py:354-356` — windup history молча дропается

```python
orchestrator._windup_registry[_reg_key] = [
    w for w in updated_windups if w.status == WindupStatus.PENDING
]
```

`updated_windups` уже отфильтрован до PENDING (строки 351-352), фильтр избыточен. Хуже: COMPLETED и INTERRUPTED windups дропаются из registry — нет audit trail, probe не может определить «NPC имел N прерванных атак за сессию».

### H-38. `BeliefFragment` schema fails PC-3 (§18)

**File:** `backend/app/models/npc/beliefs.py:24-31`
**Текущая:** `{value, confidence, source, timestamp}`
**Требуется (PC-3, §18):** `{proposition, confidence, source, timestamp, evidence, decay}`
**Missing:** `proposition` (утверждение), `evidence` (chain), `decay` (causal decay rate). Блокирует §18 активацию и 4D + BELIEVES.

### H-39. No unified belief schema между NPC и Player — блокирует ToM 4D

- `CrystallizedBelief` (`identity_events.py:62-75`): `{source_id, trait, weight, last_updated_tick}`
- `PlayerBelief` (`player_belief.py:19-26`): `{proposition_id, belief_value, support_mass, contradiction_mass, supporting_observations, contradicting_observations}`

Phase 7 ToM требует «NPC models beliefs of 2+ others» — нужно `holder_id`, `about_id`, `temporal_index`, `evidence_chain`. Ни одна из схем не имеет. Нет общего Protocol/ABC, объединяющего их. `player_belief_model.py:14` пишет «Строится неведомо для него» без NPC-side mirror. ToM невозможен без unified `Belief[Holder, About]` интерфейса.

### H-40. `CrystallizedBeliefStore` SQL schema missing 4D + BELIEVES columns

**File:** `crystallized_belief_store.py:42-55`
**Текущая:** `(id, campaign_id, npc_id, source_id, trait, weight, last_updated_tick)` + unique `(campaign_id, npc_id, source_id, trait)`
**Missing для Phase 7:** `holder_id`, `about_id`, `temporal_index`, `evidence_chain` (JSON), `proposition`, `decay_rate`. Нет schema migration path. Нет поддержки second-order beliefs (BELIEVES: NPC-A believes that NPC-B believes X). Roundtrip test `test_crystallized_belief_persistence.py` валидирует только 4 поля — не поймает регрессию при добавлении новых полей без миграции.

### H-41. `BeliefType.ALLY_NEARBY` — orphan, определён, но не используется нигде

`grep -rn "ALLY_NEARBY" backend/` → единственный hit — само определение (`beliefs.py:42`). `BeliefTransitionEngine` пишет только `DANGER` и `PLAYER_HOSTILE`. `BeliefModifierResolver` хендлит только эти два. Phase 7 ToM требует «NPC B allied with NPC C» — `ALLY_NEARBY` был бы естественным якорем, но он мёртв.

### H-42. `DopaminePayload` dead code — определён, не инстанцируется

`backend/app/models/delta_payloads.py:52-61`. `grep -rn "DopaminePayload" backend/app/` → единственный hit — определение класса. Утверждается как FEP infrastructure, но никогда не эмиттится, не потребляется. Сбивает Phase 7 разработчиков с мысли, что predictive-coding plumbing существует.

### H-43. `PEModifierResolver` dead code — Active Inference loop не подключён

`backend/app/services/npc/pe_modifier_resolver.py`. `grep -rn "PEModifierResolver" backend/` → только класс + коммент `npc_tick_pipeline.py:363` «TODO (Фаза 2 / Эпоха 7): ... Здесь должен вызываться PEModifierResolver().resolve(expectation)». ExpectationStore тоже полумёртв: `state_applicator.py:605` говорит «DEEP-015 FIX: Мёртвый код ExpectationStore (Reward Prediction Error) удалён», но `expectation_store.py` всё ещё существует и `idle_services.py:54` повторяет коммент удаления.

### H-44. ADR-059 (Phase 3→5 lag) статус неясен — возможно уже закрыт

`tick_orchestrator.py:754-756` вызывает Phase 3, 4, 5 в одном тике. `phases/memory.py:99-104` пишет `NPCState.write_to_legacy(npc_state, npc_dict)`. Phase 5 читает `npc_states`, который включает только что записанный `npc_dict`. Lag Phase 3→5 = 0 в текущем коде. Но §18 PC-16 и §19 PC-19-13 утверждают, что ADR-059 OPEN. Либо спеки устарели (тогда нужно закрыть PC-16/PC-19-13), либо есть тонкий lag (например, narrative_cache tick T влияет только на tick T+1).

### H-45. `test_p7_13_world_diff.py:75` — silently skipped contract test

```python
pytest.skip("P7-13: Отношения не переносятся между кампаниями")
```

Контракт-тест для `WorldDiffBuilder.relationship_changes` skipped, не failed. CI показывает `73 passed, 1 skipped` (выглядит здорово), но контракт relationship_changes не enforced. Addendum 2 говорит «все Phase 7 тесты проходят» — скрывает этот gap.

---

## 3. MEDIUM — блокируют §18/§19 pre-conditions

### M-01..M-24 (выборка наиболее критичных)

| # | ID | Файл:строка | Описание |
|---|-----|-------------|----------|
| M-01 | PC-6 (§18) | `layered_memory.py:128-168` | `read_by_topic` / `read_by_actor` отсутствуют — MemoryRetriever не реализован |
| M-02 | PC-7 (§18) | `npc_state.py:200-237` | `EventMemory` нет полей `topic`, `contradictions` |
| M-03 | PC-19-12 | `interpretation_engine.py:78-84` | `compute()` нет параметра `prediction_error` |
| M-04 | PC-19-7 | `state_applicator.py` | Нет метода `apply_delta_to_kernel(state, PerceptualKernelDelta)` |
| M-05 | PC-19-3 | `npc_state.py:531-554` | `PerceptualKernel` нет prediction_error/surprise/confidence полей |
| M-06 | PC-17 (§18) | `beliefs.py:46-93` | `BeliefState` нет в serialization adapter registry — нет `from_legacy`/`write_to_legacy` |
| M-07 | PC-19-5 | `inference_engine.py` | `InferenceEngine` не подключён к `npc_tick_pipeline` |
| M-08 | AUDITLOG | `router.py:235-243` | Логируется только 2 из 9 §2.6 полей (`prompt_preview`, `capability`, `system_prompt`) — missing `tick_id`, `npc_id`, `prompt_hash`, `response_hash`, `model`, `latency`, `cache_hit`, `intent_before`, `intent_after` |
| M-09 | AUDITLOG | `replay_store.py:174-179` | `response_hash` никогда не вычисляется |
| M-10 | AUDITLOG | (whole codebase) | Поле `cache_hit` не существует нигде — нельзя измерить cache effectiveness |
| M-11 | AUDITLOG | `logging_tools.py:9` | Daily rotation вместо append-only provenance chain |
| M-12 | ADRNET | `adr_parser.py:56` | `re.search` picks wrong ADR ID (берёт первое совпадение в любом месте файла) |
| M-13 | ADRNET | `adr_parser.py:99` | `re.match` anchored, пропускает indented laws под list bullets |
| M-14 | ADRNET | `adr_parser.py:106-130` | `current_files` один на law, назначается всем ADR из этого law (неверное file→ADR mapping) |
| M-15 | ADRNET | `adr_parser.py:96` | `line.replace("##", "")` mangлит domain headers с `##` внутри |
| M-16 | ADRNET | `adr_visualizer.py:44` | `str.format` ломается на title с `{`/`}` (KeyError/IndexError) |
| M-17 | ADRNET | `adr_visualizer.py:43 vs 48-49` | Node ID escaping заменяет `.`, ` `, `:`, `/`, `\`; Edge ID — только `:`, `/`, `\` → нерабочие edge refs |
| M-18 | TICK | `time_advance.py:60` | Regex `r"жд[уаю]\s+(\d+)..."` — только русские «жду/ждал/ждая»; пропускает «подожди», «wait», «pause», «спать» |
| M-19 | TICK | `time_advance.py:76` | `int()` truncates float `game_time_seconds` — потеря точности каждый turn |
| M-20 | TICK | `time_skip_executor.py:289, 334, 395` | Tick counter продвигается до kernel_execute — при exception остаётся неправильным |
| M-21 | TICK | `time_skip_executor.py:298, 343, 404` | `result.significant_events` может быть None → `TypeError` на `extend` |
| M-22 | TICK | `time_skip_executor.py:291-297` | Не проверяет `result.status` — silent skip с ошибочными результатами |
| M-23 | TICK | `tick_orchestrator.py:1601-1605` | Фильтрует только `DEAD`, не `UNCONSCIOUS`/`COMA` → бессознательные NPC проходят DecisionHub |
| M-24 | TICK | `tick_orchestrator.py:640-643` | AdaptiveTickLoader.get_duration всегда 0.0 — LOD throttling дизейблен |

### M-25..M-27 — Affective integrator

- **M-25:** `affective_integrator.py:51` — нет NaN/Inf guard. Если `pk_load` NaN (из corruption), NaN распространяется в `new_memory`, `new_load`, emotion tag, персистится между тиками → корраптит весь affective state.
- **M-26:** `affective_integrator.py:38-39` — willpower scale assumption. `_w_somatic = 1.0 - willpower * 0.5` ожидает [0,1]. `decision.py:61` дефолт `willpower=50.0` (0-100 scale). При 50.0 → `_w_somatic = -24.0` → негативный somatic urgency доминирует load.
- **M-27:** `affective_integrator.py:17` — `_TRAUMA_SCAR_RATE` defined, never used (Addendum 2 уже отметил, но это часть более широкой pattern).

### M-28..M-31 — Reputation / Phase 5/6

- **M-28:** `reputation_engine.py:96-117` — silent empty engine при misconfig. Три early-return на misconfig (no path, file missing, JSON malformed), без `RuntimeError`, без probe alert. Engine молча имеет zero factions.
- **M-29:** `phases/post_decision.py:154-180` — `pending_tasks` растёт без bound. Нет trimming. 1000 dialogue intents → scene_state разбухает, commit/serialize cost растёт линейно.
- **M-30:** `phases/post_decision.py:142-152` — `task_id` collision. `f"task-{tick}-{speaker}-dlg"` — если один NPC генерит 2 dialogue intents в тике (multi-target speech), оба получают тот же task_id. DialogueQueue dedup может дропнуть второй.
- **M-31:** `commit_phase.py:62-71` — `semantic_buffer` reconciliation пропускает falsy values. Если `emotion_tag=""` (из malformed frame), пишется пустая строка, перетирая валидный tag.

---

## 4. LOW (код-смелл, минорные баги, cleanup)

### L-01..L-14

| # | Файл:строка | Описание |
|---|-------------|----------|
| L-01 | `game_loop/__init__.py:1475` | TPS inflation на fast ticks: `1 token / 1ms = 1000 TPS` |
| L-02 | `tick_orchestrator.py:375-378` | Misleading log "0.00ms" (elapsed_ms = 0.0) |
| L-03 | `kernel_rng.py:50` | Reduced RNG entropy: `sha256(...).hexdigest()[:16]` — 64 bits из 256 |
| L-04 | `game_loop/__init__.py:543` | Conditional `_preserved_tick` reset: `if hasattr(self, ...)` — только если уже существует |
| L-05 | `game_loop/__init__.py:537-541` | Ternary-as-statement: `self._load_npcs.cache_clear() if hasattr(...) else None` |
| L-06 | `reputation_engine.py:277-278, 296-297` | Inefficient list slicing: `state.recent_actions = state.recent_actions[-50:]` — лучше `deque(maxlen=50)` |
| L-07 | `tick_orchestrator.py:1414` | `settings.data_dir` read inside hot loop |
| L-08 | `sleep_states.py` | Sleep state machine — только enum (18 строк). Реальная логика размазана по `pipeline_runner.py:113-130`, `life_engine.py`, `time_advance.py`. Нет central state machine, нет transition validation, нет probe для «NPC stuck in DROWSY forever» |
| L-09 | `phases/post_decision.py:84` | `import uuid` inside loop body — должен быть на module top |
| L-10 | `game_loop/__init__.py:470` | Direct `fpath.unlink()` без backup — interrupted new_game оставляет inconsistent state |
| L-11 | `crystallized_belief_store.py:30-37` | Lazy load footgun: `_ensure_loaded()` до `bind_campaign` ставит `_loaded=True` с пустым `_campaign_id` |
| L-12 | `crystallized_belief_modifier_resolver.py:31-42` | Только `"fear"` и `"trust"` string traits — нет type safety |
| L-13 | `belief_transition_engine.py:67-73` | Stale docstring «READ: BeliefModifierResolver (следующий шаг, День 3)» — sprint-plan ссылка устарела |
| L-14 | `belief_aggregator.py:79` | `actor_id` — comment «для будущей адресации (R9+)» никогда не materialized; dead field |

---

## 5. ТЕСТ-ПОКРЫТИЕ — пробелы

### 5.1 `test_tick_orchestrator_full_loop.py` (1 тест, 141 строка)

**Тестирует:** `test_tick_orchestrator_full_loop_player_attacks` — один сценарий, игрок атакует NPC, assert stress увеличился.

**Не тестирует:**
- Idle tick (без interventions) — поймал бы C-03 (commit empty npc_states).
- Multi-location tick — поймал бы C-05.
- Phase 7 windup resolution (interrupted windups).
- Phase 8 handler crashes (M-swallow'ы).
- Replay recording/playback round-trip.
- Time-skip через `TimeSkipExecutor` — поймал бы M-20/M-21/M-22.
- DRF scoring overlay — поймал бы H-28.
- Affective integrator NaN propagation — M-25.
- Reputation engine with rivals — H-23.
- Cross-location NPC transfers (S186 logic).

### 5.2 `tests/system/test_sleep_routing.py` (1 тест, 96 строк)

**Тестирует:** 5 NPC оказываются на правильных кроватях после 120 тиков на 02:00.

**Не тестирует:**
- Sleep→wake transition (06:00 должно разбудить).
- Sleep interruption by combat/threat (SLEEP_GUARD logic).
- Sleep during cross-location traversal — именно баг из `sleep_test_v26.log`: `blacksmith_orm` застрял на `tavern:node_16`.
- Multiple NPC bedtime collisions (два NPC на одну кровать).
- SC-4 probe failure during transit — именно warning из `sleep_test_v27.log`: `guard_borko pos (16.79, 8.99) too far from city_gate:guard_bed`.

### 5.3 Sleep logs — фактический статус

- **`sleep_test_v26.log`** — FAILED. `guard_borko` застрял на `city_gate:exit_west`, `blacksmith_orm` на `tavern:node_16`, `merchant_goran` на `city_gate:entrance`. NPC routing к кроватям сломан.
- **`sleep_test_v27.log`** — PASSED (final state). Все 5 NPC на кроватях. **НО:** во время transit многократно срабатывает `INV-SC-1-8-SPATIAL-COHERENCE: SC-4 FAIL: NPC 'guard_borko' pos (16.79, 8.99) too far from node 'city_gate:guard_bed' (31.73, 1.87)`. Probe слишком строг во время traversal — local_position интерполируется к target_node, но probe ожидает snap-to-node. **Не пофикшено**, только final-state assertion проходит.

Также в v27: `[SHADOW_COMPILER] Node not found: city_gate:gate_road loc=city_gate` — shadow compiler ссылается на несуществующий в графе node. Traversal для `thief_shadow` молча дропнут.

### 5.4 Phase 7 integration TODO markers, не отражённые в Addendum 2

5 явных «TODO (Фаза 2 / Эпоха 7)»:
- `npc_tick_pipeline.py:362-365` — ExpectationStore / PEModifierResolver integration
- `npc_tick_pipeline.py:367-370` — PerceptionEngine (social status) integration
- `npc_tick_pipeline.py:665-667` — ResolutionEngine integration
- `tick_orchestrator.py:766` — FrontEngine integration
- `events/reaction_subscriber.py:261` — ReactionPriority integration
- `perception/perceptual_attention_service.py:48` — `player_l1_chronicle` parameter

Ни один из этих integration points не указан в Addendum 2. Каждый — отдельная wiring-задача, не входящая в оценку «192 ч P2 work».

---

## 6. РЕКОМЕНДУЕМЫЙ ПОРЯДОК ФИКСОВ

### 6.1 Quick wins (<5 ч каждый, мгновенно разблокируют гейты)

| # | Bug | Effort | Что разблокирует |
|---|-----|--------|------------------|
| 1 | C-10 (LLM cache never written) | 0.5 ч | LLM cache hit gate |
| 2 | C-01 (`_l1_events` NameError) | 0.5 ч | L1 chronicle для боя |
| 3 | C-03 (idle commit wipes NPCs) | 1 ч | GameLoop.idle_tick стабильность |
| 4 | C-04 (delta_buffer leak) | 1 ч | Test isolation |
| 5 | C-07 (routes.py AttributeError) | 0.5 ч | Phase 7 debug endpoint |
| 6 | C-15 (runaway belief feedback) | 1 ч | Belief stability |
| 7 | C-13 (CLI returns stderr) | 1 ч | LLM correctness |
| 8 | C-14 (yield error as token) | 0.5 ч | Streaming correctness |
| 9 | H-22 (`List[Any]()` TypeError) | 0.2 ч | Faction debug UI |
| 10 | H-26 (KernelRNG salt) | 1 ч | Replay determinism |
| 11 | H-04 (replay_record never restored) | 0.5 ч | Replay system |
| 12 | H-08 (hash only prompt) | 1 ч | LLM cache correctness |
| 13 | H-31 (B5-FIX swallow) | 0.5 ч | Intent mapping |

**Сумма quick wins:** ~9 ч. Закрывает 13 багов.

### 6.2 Средние фиксы (5-20 ч каждый)

| # | Bug | Effort | Что разблокирует |
|---|-----|--------|------------------|
| 14 | C-09 + C-11 (hot-path cache) | 6 ч | Production cache ≥35% gate |
| 15 | C-12 + H-11 + H-12 (thread safety) | 8 ч | Provider concurrency safety |
| 16 | C-02 + C-05 + C-06 (game_loop races + swallow) | 6 ч | Multi-location Phase 7 |
| 17 | H-01 + H-02 + H-03 (replay store) | 6 ч | Replay determinism gate |
| 18 | H-18 + H-19 + H-21 (ADR-Net) | 10 ч | ADR-Net functional |
| 19 | H-20 (ADR parser regex) | 3 ч | ADR-Net parsing correctness |
| 20 | H-23 + H-24 + H-25 (reputation rivals/target) | 6 ч | Faction dynamics для end-screen |
| 21 | H-28 (DRF overlay dead) | 4 ч | Phase 7 DRF verification |
| 22 | H-29 (state_applicator swallow inconsistency) | 4 ч | Phase 5 contract consistency |
| 23 | H-38 + H-39 + H-40 (belief schema 4D) | 16 ч | ToM 4D + BELIEVES pre-condition |
| 24 | M-08..M-11 (audit_log) | 8 ч | §2.6 audit log |

**Сумма средних:** ~77 ч. Закрывает ~25 багов.

### 6.3 Большие фиксы (20+ ч, в Addendum 2 уже оценены)

- BeliefMerger (32 ч)
- §19 PerceptualKernel (48 ч)
- ProphecyEngine (40 ч)
- ToM 4D + BELIEVES (48 ч)
- Vertical Slice campaign (24 ч)

**Сумма больших:** ~192 ч (совпадает с Addendum 2 P2).

### 6.4 Итоговая скорректированная оценка до Phase 7

| Слагаемое | Часы |
|-----------|------|
| Addendum 2 P0 (Critical) | 17 |
| Addendum 2 P1 (High) | 116 |
| Addendum 2 P2 (Medium, Phase 7) | 192 |
| Addendum 2 P3 (Low) | 36 |
| **Addendum 3 Quick wins (13 багов)** | **9** |
| **Addendum 3 Средние (25 багов)** | **77** |
| **Addendum 3 LOW cleanup (14 багов)** | **18** |
| **ИТОГО до Эпохи 7:** | **~465 ч** |

(Addendum 2 оценивал ~325 ч; с учётом новых багов — ~465 ч, рост на ~43%.)

---

## 7. ВЕРДИКТ

❌ **Код НЕ ГОТОВ к переходу на Эпоху 7.** Addendum 2 правильно идентифицировал «отсутствующие файлы», но недооценил количество багов в **существующем** коде:

- **18 CRITICAL багов**, каждый из которых независимо блокирует переход:
  - 10 LLM/cache/provider багов объясняют «0% cache hit» и «LLM failures silent»
  - 6 game_loop/commit_phase/tick_orchestrator багов ломают multi-location integrity
  - 2 belief/cognition бага создают патологическое поведение убеждений
- **33 HIGH бага**, в т.ч.:
  - 5 replay/determinism багов ломают replay gate
  - 8 ADR-Net багов делают ADR-Net dead code
  - 6 reputation/kernel_rng/state_applicator багов ломают faction dynamics и determinism
- **27 MEDIUM** — блокируют §18/§19 pre-conditions (PC-3, PC-6, PC-7, PC-17, PC-19-3, PC-19-5, PC-19-7, PC-19-12)
- **14 LOW** — cleanup, не блокируют, но мешают Phase 7 работе

**Главный вывод:** Прежде чем строить новые модули (BeliefMerger, ProphecyEngine, PerceptualKernel §19), нужно починить инфраструктуру — иначе новые модули будут построены на сломанном фундаменте. **Quick wins (~9 ч) — наивысший приоритет**.

---

*Аудит завершён. Все находки подтверждены чтением исходного кода и/или анализом логов `sleep_test_v27.log`, `replay_compare*.log`. Рекомендуется обновить Addendum 2 интеграцией этих 92 находок либо выпустить Addendum 3 как самостоятельный документ.*
