# ТЗ: ВОССТАНОВЛЕНИЕ РАБОТОСПОСОБНОСТИ ENIGMA V.0.5.3.7.0

> **Документ:** Техническое задание на исправление дефектов кода
> **Версия проекта:** Enigma V.0.5.3.7.0 (version.txt = 0.5.3.6.10 — рассинхрон)
> **Дата анализа:** 2026-08-05
> **Метод:** Глубокий статический анализ исходников по 5 доменам + трассировка runtime-цепочек + сверка с CAUSAL_CONTRACT v2.0 и ADR Master Index
> **Объём:** 57 активных дефектов (15 Critical, 13 High, 16 Medium, 13 Low)
> **Аудит покрыл:** 5 доменов, ~745 .py файлов, 24 .py файла фронтенда, конфиги, логи сессий
> **Принцип:** Документируются ТОЛЬКО активные дефекты V.0.5.3.7.0. Исправленные в предыдущих итерациях дефекты не упоминаются.

---

## 0. EXECUTIVE SUMMARY

Кодовая база ENIGMA V.0.5.3.7.0 находится в состоянии **«вылеченной核心 с занесённой регрессией»**. Успешно завершена миграция `hub_event` (игрок теперь виден NPC pipeline). Однако параллельно внесена **критическая регрессия** `REGRESSION-CORE-001`: `task_scheduler` перестал передаваться в `tick_orchestrator.execute()` → NPC теряют topic «ответить: …» → NPC молчат в ответ игроку. Это объясняет жалобу «ЛЛм не отвечал мне».

Параллельно пять подсистем игры функционально сломаны, хотя формально компилируются и диагностика DNA показывает SHI/NPI 100% (тихая деградация — метрики врут, потому что считают структурную целостность, а не семантическую).

### Пять ключевых симптомов, которые видит игрок в V.0.5.3.7.0

| # | Симптом | Корневая причина (Top-3 контрибьютора) | Домен |
|---|---------|----------------------------------------|-------|
| **S-1** | LLM не отвечает — игрок видит «Тишина.» / «Ничего не произошло.» на каждый ход | REGRESSION-CORE-001 (`task_scheduler` не передаётся в `execute()` → NPC теряет topic «ответить»), NEW-DLG-004 (worker thread глушит исключение → `""`), runtime: llama-server на `:8181` не запущен → `is_available()=False` | Core + LLM |
| **S-2** | MVP окно не всплывает | NEW-MVP-001 (`game_screen.py:891` silent `except` — `show_end_screen` остаётся `False`), NEW-MVP-002 (Continue-flow не вызывает `init_campaign` → `truth_state=None` → `RuntimeError` в `build_end_screen`) | MVP/Frontend |
| **S-3** | NPC не вертят головами | NEW-ORIENT-003 (нет модели `head_yaw` — тело и голова используют одно поле `body_heading`), NEW-ORIENT-001 (`body_heading` обновляется только при микро-jitter, не при восприятии), NEW-ORIENT-002 (frontend НИКОГДА не вращает NPC-спрайты — только `scale+blit`) | Orientation/Spatial |
| **S-4** | Текстуры не отрисовываются — NPC как plain circles | NEW-MVP-007 (`sprite_registry` указывает на несуществующую папку `2-Bit Pack/Deadbeat/` → `return None` silent), NEW-MVP-008 (персональные спрайты `Детектив.png`/`Трактирщик.png` никогда не загружаются) | MVP/Frontend |
| **S-5** | Не формируются таблицы воспоминаний NPC | NEW-MEM-001 (`EventSemanticTagger` map keys lowercase vs `EventType` values uppercase → `crystallized_beliefs` всегда пустые), NEW-MEM-002 (нет UI/API endpoint для просмотра таблиц), NEW-MEM-003 (`.gitignore` исключает `*.db` и `saves/` → БД невидима в репозитории) | Memory |

### Главный архитектурный диагноз

В проекте V.0.5.3.7.0 выполнена одна ключевая миграция и занесены две критические регрессии + накоплено 12 конструктивных пробелов в новых подсистемах:

1. **Миграция `hub_event` (ADR-TZ09-1) → ЗАВЕРШЕНА.** `hub_event` теперь проходит всю цепочку: `routes → game_loop → npc_orchestration → execute → create_tick_context → _TickContext.hub_event → build_tick_state → TickState.hub_event → NpcTickPipeline.run → state.hub_event`. NPC pipeline видит действия игрока. ✅

2. **Новая регрессия REGRESSION-CORE-001 →** при «починке ядра» вызовы `tick_orchestrator.execute()` в `npc_orchestration.py` и `idle_tick` потеряли параметр `task_scheduler`. Phase 4 `_phase_4_pre_decision` читает `ctx.task_scheduler.get_recent_dialogues(...)` → `None` → `[]`. NPC не получает topic «ответить: …» → fallback на `extract_topic("idle", npc_state)` → NPC не отвечает игроку напрямую. Это прямой объяснение «LLM не отвечал мне».

3. **Новая регрессия REGRESSION-CORE-002 →** `TICK_COMPLETED` event в payload содержит non-serializable `ctx` (`_TickContext` dataclass). При любой попытке сериализации (логирование, persistence, SSE) — `TypeError`. Latent, но взрывается при включении расширенного логирования.

4. **Конструктивный пробел: NPC Orientation →** в модели данных НЕТ отдельного поля `head_yaw`. Только `body_heading` (одно поле для тела и головы), обновляется только при микро-jitter collision-avoidance. Macro relocation НЕ создаёт SceneChange с `field="body_heading"`. Frontend `scene_renderer._draw_npcs` делает `pygame.transform.scale + blit` БЕЗ `rotate`. Плюс `facing_towards_player: True` HARDCODED в `player_target_pipeline.py:199` — DM SceneBuilder видит fake данные (все NPC «смотрят на игрока» со 100% видимостью).

5. **Конструктивный пробел: Textures →** `sprite_registry` указывает на `pixels/2-Bit Pack/Deadbeat/deadbeat_b.png` — такой папки/файла НЕТ. Реальные текстуры лежат в `pixels/Pers/traktir/Детектив.png`, `Трактирщик.png` — но registry их не использует. Все `get_entity_sprite()` возвращают `None` (silent) → fallback на `pygame.draw.circle`. У круга нет ориентации.

6. **Конструктивный пробел: MVP popup →** две независимые причины невсплывания: (а) `game_screen.py:891` ловит `RuntimeError` от `build_end_screen` (truth_state=None) и НЕ устанавливает `show_end_screen=True`; (б) Continue-flow `game_launcher.py:281` не вызывает `new_game()` → `mvp_controller.init_campaign()` не вызывается → `truth_state=None`.

7. **Конструктивный пробел: Memory visibility →** pipeline памяти структурно корректен (L1/L2/L3, SQLite `enigma_memory.db`, lazy loading, idempotency guards). Но: (а) `EventSemanticTagger._EVENT_SEMANTIC_MAP` keys lowercase (`"player_attacks"`) vs `EventType.PLAYER_ATTACKED.value = "PLAYER_ATTACKED"` uppercase — НЕ совпадают → `crystallized_beliefs` всегда пустые; (б) нет ни API endpoint, ни UI для просмотра таблиц; (в) `.gitignore` исключает `*.db` и `saves/` → пользователь видит «пустоту».

---

## 1. КАРТА ДЕФЕКТОВ ПО ДОМЕНАМ

| Домен | Кол-во багов | Critical | High | Medium | Low | Ключевые файлы |
|-------|--------------|----------|------|--------|-----|----------------|
| DOM-CORE: Core Tick Pipeline | 13 | 2 | 0 | 2 | 2 (+7 still_broken contract) | `tick_orchestrator.py`, `npc_orchestration.py`, `game_launcher.py`, `routes.py`, `life_engine.py` |
| DOM-LLM: Dialogue / LLM / DM-Agent | 12 | 2 | 3 | 2 | 2 (+3 still_broken RNG) | `llm_compressor_client.py`, `router.py`, `openai_compatible_provider.py`, `mock_provider.py`, `rules_agent.py`, `llama_cpp_provider.py`, `dm_agent.py` |
| DOM-MVP: MVP / Frontend / Rendering | 15 | 4 | 2 | 4 | 2 (+3 still_broken) | `game_screen.py`, `game_launcher.py`, `sprite_registry.py`, `scene_renderer.py`, `mvp_tavern_controller.py`, `mock_provider.py` |
| DOM-ORIENT: NPC Orientation / Spatial | 13 | 3 | 1 | 2 | 2 (+4 still_broken) | `movement_engine.py`, `scene_renderer.py`, `snapshot.py`, `game_types.py`, `player_target_pipeline.py`, `traversal_execution_system.py` |
| DOM-MEM: NPC Memory | 12 | 3 | 2 | 3 | 4 (+2 still_broken) | `event_semantic_tagger.py`, `event_types.py`, `tick_orchestrator.py`, `phases/memory.py`, `.gitignore`, `expectation_store.py` |
| DOM-CONTRACT: Wall-clock / RNG / Silent-fail | 9 | 0 | 0 | 0 | 0 (cross-cutting) | cross-domain |
| **ИТОГО (с дедупликацией)** | **~57** | **15** | **13** | **16** | **13** | — |

> **Критические баги (Critical, P0):** блокируют основной игровой цикл. Без их исправления игра нефункциональна.
> **Высокий приоритет (High, P1):** серьёзные архитектурные нарушения или сломанные подсистемы.
> **Средний приоритет (Medium, P2):** снижают качество симуляции, но не блокируют.
> **Низкий приоритет (Low, P3):** code hygiene, мёртвый код, cosmetic.

---

## 2. АРХИТЕКТУРНЫЕ НАРУШЕНИЯ (Контрактные)

Следующие баги прямо нарушают `CAUSAL_CONTRACT v2.0` или `ADR Master Index`.

| Контракт | Нарушение | Bug ID | Файл |
|----------|-----------|--------|------|
| L2 (Runtime Purity) — `random.*` запрещён, только `KernelRNG` | `rules_agent.py` `random.randint(2, 20)` для d20 | BUG-DLG-043 | `rules_agent.py:246-250` |
| L2 — `random.*` запрещён | `llama_cpp_provider.py` `random.randint(0, 2**31-1)` для LLM seed | BUG-DLG-044 | `llama_cpp_provider.py:163` |
| L2 — `random.*` запрещён | `market_state.py` + `traveller.py` `random.Random()` без seed | BUG-CORE-023 | `market_state.py:97-98`, `traveller.py:117-120` |
| L2 — `random.*` запрещён | `npc_conversation.py` `random.choice` для ambient dialogue | BUG-CORE-024 | `npc_conversation.py:222` |
| L2 — `random.*` запрещён | `dm_response_normalizer.py` `random.choice` | BUG-CORE-025 | `dm_response_normalizer.py:71` |
| L2 — `random.*` запрещён | `attention_layer.py` `random.random()` | BUG-CORE-026 | `attention_layer.py:108,110,120` |
| L2 — `random.*` запрещён (partial fix signature) | `impact_engine.py` `random.Random(rng_seed)` с UUID-hash seed | BUG-CORE-021 | `impact_engine.py:131`, `combat_subscriber.py:210-222` |
| L15 — Wall-clock в симуляции запрещён | `world_scheduler.maybe_tick` `datetime.now(timezone.utc)` | BUG-FB-012 | `world_scheduler.py:32` |
| L15 — Wall-clock запрещён | `WorldSnapshot.created_at = time.time()` + `uuid4()` | BUG-FB-029 | `world_snapshot.py:88-89` |
| L15 — Wall-clock запрещён | `EventDTO.create` default `time.time()` + `uuid4()` | BUG-FB-037 | `domain/events.py` |
| L15 — Wall-clock запрещён | `WorldProjectionBuffer.project` `uuid.uuid4()` | BUG-FB-038 | `world_projection_buffer.py` |
| L15 — Wall-clock запрещён | `scene_init._reconcile_elapsed_time` `time.time()` | BUG-FB-039 | `scene_init.py` |
| L15 — Wall-clock запрещён | `SqlitePersistenceAdapter._upsert` `datetime.now()` для `updated_at` | BUG-FB-040 | `sqlite_persistence_adapter.py` |
| L15 (Frontend Authority) — Backend = единственный источник истины | `routes.py:update_scene_state` принимает `scene_state` от фронта (partial fix: protected_keys) | BUG-FB-041 | `routes.py:806-831` |
| L4 (Silent Failure Prohibition) | `npc_orchestration.py:80-84` SpatialFactory crash без try/except (outer) | BUG-CORE-020 | `npc_orchestration.py:80-84` |
| L4 — Silent Failure | `router.py:572-574` worker thread `except Exception → return ""` | NEW-DLG-004 | `router.py:543-576` |
| L4 — Silent Failure | `game_screen.py:891-893` MVP popup `except Exception` без `show_end_screen=True` | NEW-MVP-001 | `game_screen.py:891-893` |
| L4 — Silent Failure | `sprite_registry.py` `return None` при отсутствии текстуры | NEW-MVP-007 | `sprite_registry.py` |
| L4 — Silent Failure | `mock_provider.py` silent `""` в production | BUG-DLG-CAUSAL-4.7.48 | `mock_provider.py:124-138` |
| L9 (Spatial SSOT) — `player_spatial` мёртв | `life_engine.py:861` читает `player_spatial` как fallback (Double Truth) | BUG-SPATIAL-032 | `life_engine.py:861-867` |
| L9 — `player_spatial` мёртв | `scene_init.py:79` читает `player_spatial` как fallback | BUG-SPATIAL-033 | `scene_init.py:79-82` |
| L11 (Spatial Coherence SC-1…SC-8) | Валидация не реализована как coherent gate (только SC-1) | BUG-SPATIAL-036 | `probes/spatial_coherence_probe.py` |
| L14 (Epistemic Memory Law) — L2.5 кристаллизация только при `phase_2_events` | Кристаллизация запускается каждый тик без gate | BUG-PERC-014 | `integration.py:380-422` |
| L17 (Identity Pipeline) — L1Chronicle UNIQUE constraint | `l1_chronicle_events` не имеет UNIQUE → дубликаты при restart | BUG-FB-044 | `l1_chronicle.py:44-54` |
| L21 (Invariant Defense) — `print()` в production запрещён | 1138 `print()` в 136 файлах (регрессия) | BUG-FB-036 | multiple |
| CAUSAL_CONTRACT §4.7.48 — `MockProvider` в production запрещён | `MockProvider._pick_response` проверяет `ENIGMA_ENV` вместо `settings.environment` | BUG-DLG-CAUSAL-4.7.48 | `mock_provider.py:126` |
| CAUSAL_CONTRACT §4.7.49 — Парсинг JSON в DM-агенте запрещён | `dm_agent.py:853-874` CJK retry `json.loads` bypasses DMResponseNormalizer | BUG-DLG-CAUSAL-4.7.49 | `dm_agent.py:853-874` |
| ADR-O-201 (Dual Rail) — Snapshot Kernel determinism | `WorldSnapshot.snapshot_id = uuid4()`, `created_at = time.time()` | BUG-FB-029 | `world_snapshot.py:88-89` |
| Epistemic Boundary (L16) — fake data | `facing_towards_player: True` HARDCODED для всех NPC | NEW-ORIENT-004 | `player_target_pipeline.py:199` |

---

## 3. БАГ-КАТАЛОГ ПО ДОМЕНАМ

Ниже приведены все ~57 активных дефектов с `file:line`, симптомом, корневой причиной, severity и предлагаемым фиксом.

---

### 3.1. DOM-CORE: CORE TICK PIPELINE

#### REGRESSION-CORE-001 — `task_scheduler` НЕ передаётся в `tick_orchestrator.execute()` (NPC не отвечает игроку)
- **Файл:строка:** `backend/app/services/game_loop/npc_orchestration.py` (оба вызова `tick_orchestrator.execute(...)`) + `backend/app/services/game_loop/phase_2_world_tick.py` (idle path)
- **Severity:** Critical (корневая причина S-1, прямая регрессия от «починки ядра»)
- **Симптом:** NPC не отвечает игроку напрямую. Phase 4 `_phase_4_pre_decision` читает `ctx.task_scheduler.get_recent_dialogues(...)` → `None` → `[]`. NPC не получает topic «ответить: …» → fallback на `extract_topic("idle", npc_state)`. DM-агент получает idle-контекст вместо ответа на реплику игрока. Каскадно: диалоги игрока «тонут» в idle-симуляции.
- **Причина:** После миграции `hub_event` (BUG-CORE-003 fix) вызовы `execute()` были переписаны для проброса `hub_event`, но параметр `task_scheduler` был потерян. `ctx.task_scheduler` в `tick_orchestrator` теперь всегда `None`.
- **Фикс:**
  ```python
  # npc_orchestration.py — оба вызова execute():
  _loc_result = tick_orchestrator.execute(
      ...,
      hub_event=ctx.hub_event if _loc_id == _active_loc else None,
      task_scheduler=ctx.task_scheduler,  # ← ДОБАВИТЬ
  )
  # phase_2_world_tick.py idle path — аналогично:
  _result = tick_orchestrator.execute(
      ...,
      task_scheduler=game_loop._get_task_scheduler(),  # ← ДОБАВИТЬ
  )
  ```
- **Статус:** REGRESSION (введена в V.0.5.3.7.0)

#### REGRESSION-CORE-002 — `TICK_COMPLETED` event содержит non-serializable `ctx` в payload
- **Файл:строка:** `backend/app/services/tick_orchestrator.py:608-617`
- **Severity:** Critical (latent — взрывается при расширенном логировании/persistence)
- **Симптом:** Любая попытка сериализовать `TICK_COMPLETED` event (JSON-лог, SQLite persist, SSE broadcast) падает с `TypeError: Object of type _TickContext is not JSON serializable`.
- **Причина:** `payload={"snapshot": ctx, ...}` — `ctx` это `_TickContext` dataclass с методами и non-serializable полями.
- **Фикс:**
  ```python
  payload = {
      "snapshot": {
          "tick": ctx.tick_number,
          "campaign_id": ctx.campaign_id,
          "active_location": ctx.active_location,
          "npc_count": len(ctx.npcs) if ctx.npcs else 0,
      },
      ...
  }
  ```
- **Статус:** REGRESSION (введена в V.0.5.3.7.0)

#### NEW-CORE-001 — `routes.py:462` теряет позицию игрока при `(0, 0)`
- **Файл:строка:** `backend/app/api/routes.py:462`
- **Severity:** Medium
- **Симптом:** Если игрок находится в координатах `(0.0, 0.0)` (начало локации), `if player_x != 0.0` → `False` → позиция не обновляется. NPC не видят игрока.
- **Причина:** Falsy-проверка `!= 0.0` вместо `is not None`.
- **Фикс:**
  ```python
  if player_x is not None and player_y is not None:
      state.player_position = (player_x, player_y)
  ```
- **Статус:** NEW

#### NEW-CORE-002 — `game_launcher.py` Continue flow race condition
- **Файл:строка:** `game_launcher.py:281` (Continue flow)
- **Severity:** Medium
- **Симптом:** При нажатии «Continue» backend (FastAPI `:8000`) поднимается асинхронно, но фронтенд не ждёт готовности → первый `/api/game/action` падает с `ConnectionRefusedError`.
- **Причина:** Нет wait-loop / health-check перед запуском pygame-loop.
- **Фикс:**
  ```python
  import time, urllib.request
  for _ in range(30):
      try:
          urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=1)
          break
      except Exception:
          time.sleep(0.5)
  ```
- **Статус:** NEW

#### NEW-CORE-003 — `game_launcher.py:70` file handle leak
- **Файл:строка:** `game_launcher.py:70`
- **Severity:** Low
- **Симптом:** `open(...)` без `with` / `close()` → file handle leak при каждом запуске.
- **Фикс:** использовать `with open(...) as f:`.
- **Статус:** NEW

#### NEW-CORE-004 — `npc_orchestration.py:67,75` duplicate `ctx.all_npcs_raw` assignment
- **Файл:строка:** `backend/app/services/game_loop/npc_orchestration.py:67, 75`
- **Severity:** Low
- **Симптом:** Дублирующее присваивание — безобидно, но указывает на незавершённый рефакторинг.
- **Фикс:** удалить дубликат.
- **Статус:** NEW

#### BUG-CORE-013 — `l1_drift_events` всегда пустой в TickMutation
- **Файл:строка:** `backend/app/services/npc/npc_tick_pipeline.py:150` (declaration), `:647` (pass to TickMutation)
- **Severity:** Medium
- **Симптом:** `pipeline_runner.build_npc_contexts_from_intents` содержит мёртвый код: `if mutation.l1_drift_events and _svc: for _event in mutation.l1_drift_events: ...`. Никогда не выполняется. Контракт L3 нарушен.
- **Причина:** `l1_drift_events: List[Any] = []` объявлен на строке 150 и передан в `TickMutation(...)` на строке 647. Между ними НЕТ ни одного `.append(...)`. `StateApplicator.apply()` пишет `TraitDriftEvent` напрямую в `_chronicle.commit_tick_buffer`, минуя список.
- **Фикс:** Собирать `l1_drift_events` из `StateApplicator` (diff до/после apply) либо читать из `chronicle.diff`.
- **Статус:** STILL_BROKEN

#### BUG-CORE-015 — `_apply_drf_scoring_overlay` проверяет `npc_id`, читает `actor_id` (DRF overlay = dead code)
- **Файл:строка:** `backend/app/services/tick_orchestrator.py:1593-1623`
- **Severity:** Medium
- **Симптом:** DRF scoring overlay никогда не применяется к `communication_intents`. NPC решения не получают «causal field bonus» от давления фракций/союзников.
- **Причина:** `hasattr(_intent, "npc_id")` → `False` (у `CommunicationIntent` полей `npc_id`, `actor_id`, `priority` НЕТ). `continue` → overlay пропускается.
- **Фикс:** читать `_intent.speaker`, использовать `dataclasses.replace` для модификации priority.
- **Статус:** STILL_BROKEN

#### BUG-CORE-016 — `LifeEngine.tick_decisions` — мёртвый код ~500 строк
- **Файл:строка:** `backend/app/services/npc/life_engine.py:640-1140`
- **Severity:** Medium
- **Симптом:** Метод `tick_decisions` (500+ строк) не вызывается из production. Нарушает ADR-TZ09 (Pure Reducer).
- **Фикс:** удалить метод целиком; адаптировать 2 теста на `NpcTickPipeline.run`.
- **Статус:** STILL_BROKEN

#### BUG-CORE-017 — Дублированный dead блок после `return` в `tick_decisions`
- **Файл:строка:** `backend/app/services/npc/life_engine.py:687-702`
- **Severity:** Low
- **Фимптом:** Два идентичных блока `if not npcs: ... return ([], [], [])`. Второй недостижим.
- **Фикс:** удалить второй блок (или весь `tick_decisions` — см. BUG-CORE-016).
- **Статус:** STILL_BROKEN

#### BUG-CORE-020 — `npc_orchestration.py` silent `except` для SpatialFactory (outer loop partial fix)
- **Файл:строка:** `backend/app/services/game_loop/npc_orchestration.py:80-84`
- **Severity:** Medium
- **Симптом:** Если `SpatialFactory.build_for_campaign` падает (битый editor JSON, race condition в кэше), весь `npc_orchestration` падает. Inner loop имеет try/except, outer — нет.
- **Фикс:** обернуть outer вызов `SpatialFactory.build_for_campaign(...)` в try/except с `logger.warning(...)`.
- **Статус:** PARTIALLY_FIXED (inner loop only)

#### BUG-CORE-022 — `tick_orchestrator.py` non-serializable `ctx` в TICK_COMPLETED payload
- **Файл:строка:** `backend/app/services/tick_orchestrator.py:608-617`
- **Severity:** Medium (дублирует REGRESSION-CORE-002)
- **Статус:** STILL_BROKEN (см. REGRESSION-CORE-002 для фикса)

#### BUG-CORE-021 — `impact_engine.py` `random.Random(rng_seed)` с UUID-hash seed (partial fix)
- **Файл:строка:** `backend/app/services/combat/impact_engine.py:131`, `backend/app/services/combat/combat_subscriber.py:210-222`
- **Severity:** High
- **Симптом:** Боевые броски d20, выбор зоны попадания — недетерминированы. Replay determinism нарушен.
- **Причина:** `rng_seed=hash((event.id, intent.actor_id, intent.target_id)) & 0xFFFFFFFF`. `event.id = str(uuid.uuid4())` → `hash(...)` различается между запусками.
- **Фикс:** использовать `KernelRNG(tick=tick, npc_id=intent.actor_id, salt=f"combat:{intent.target_id}")`.
- **Статус:** PARTIALLY_FIXED (signature changed, but seed still UUID-based)

#### BUG-CORE-023 — `market_state.py` + `traveller.py` `random.Random()` без seed
- **Файл:строка:** `backend/app/services/economy/market_state.py:97-98`, `backend/app/services/economy/traveller.py:117-120`
- **Severity:** Medium
- **Фикс:** `KernelRNG` с детерминированным seed.
- **Статус:** STILL_BROKEN

#### BUG-CORE-024 — `npc_conversation.py` `random.choice` для ambient dialogue
- **Файл:строка:** `backend/app/services/execution/npc_conversation.py:222`
- **Severity:** Medium
- **Фикс:** `KernelRNG.choice(...)`.
- **Статус:** STILL_BROKEN

#### BUG-CORE-025 — `dm_response_normalizer.py` `random.choice`
- **Файл:строка:** `backend/app/services/verbalization/dm_response_normalizer.py:71`
- **Severity:** Medium
- **Фикс:** `KernelRNG.choice(...)`.
- **Статус:** STILL_BROKEN

#### BUG-CORE-026 — `attention_layer.py` `random.random()`
- **Файл:строка:** `backend/app/services/player_cognition/attention_layer.py:108, 110, 120`
- **Severity:** Medium
- **Фикс:** `KernelRNG.random()`.
- **Статус:** STILL_BROKEN

---

### 3.2. DOM-LLM: DIALOGUE / LLM / DM-AGENT

#### NEW-DLG-001 — `llm_compressor_client.py` `NameError: name 'logger' is not defined`
- **Файл:строка:** `backend/app/services/input/llm_compressor_client.py:73`
- **Severity:** Critical
- **Симптом:** При ошибке LLM-компрессии (URLError / JSONDecodeError / KeyError / IndexError) вместо чистого возврата `None` поднимается `NameError`. Маскирует реальную ошибку LLM. IntentCompressor падает.
- **Причина:** В файле нет `import logging` и нет `logger = logging.getLogger(__name__)`, но в `except` блоке вызывается `logger.debug(...)`.
- **Фикс:**
  ```python
  import logging
  logger = logging.getLogger(__name__)
  # в начале файла после `import json`
  ```
- **Статус:** NEW

#### NEW-DLG-002 — `llm_compressor_client.py` hardcoded `base_url`
- **Файл:строка:** `backend/app/services/input/llm_compressor_client.py:26`
- **Severity:** High
- **Симптом:** LLM-компрессор всегда стучится на `http://127.0.0.1:8181`, игнорируя `settings.llama_cpp_server_url`. Если llama-server на другом порту — компрессор не работает.
- **Фикс:**
  ```python
  def __init__(self, base_url: str | None = None):
      from app.core.config import settings
      self.base_url = base_url or settings.llama_cpp_server_url
  ```
- **Статус:** NEW

#### NEW-DLG-003 — `api_client.py` `AttributeError: 'BackendContract' object has no attribute '_base_url'`
- **Файл:строка:** `frontend/api_client.py:421`
- **Severity:** High
- **Симптом:** `HttpGameGateway.get_world_state()` падает при любом вызове.
- **Причина:** `base_url=self._contract._base_url` — у `BackendContract` нет атрибута `_base_url`. Правильно: `self._contract._t.base_url`.
- **Фикс:** `base_url=self._contract._t.base_url`.
- **Статус:** NEW

#### NEW-DLG-004 — `router.py` worker thread глушит все `Exception` → `""`
- **Файл:строка:** `backend/app/services/llm/router.py:543-576`
- **Severity:** High (усугубляет S-1)
- **Симптом:** DmAgent не может отличить «LLM вернул пустой ответ» от «LLM упал». Root cause скрыт. Игрок видит «Тишина.» без диагностики.
- **Причина:**
  ```python
  except Exception as e:
      _root_logger.error(f"[R4A_WORKER] exception: {e}")
      return ""  # ← теряет информацию об ошибке
  ```
- **Фикс:** Возвращать sentinel-объект `LLMUnavailable` или поднимать специальное исключение, которое DmAgent распознает и залогирует как «LLM broken».
- **Статус:** NEW

#### NEW-DLG-005 — `router.py` replay_playback bypass в worker thread
- **Файл:строка:** `backend/app/services/llm/router.py:528-540, 543-576`
- **Severity:** Medium
- **Симптом:** В режиме `replay_playback=True` cache miss должен возвращать `""` без вызова LLM. Но worker thread path обходит проверку и делает реальный LLM-запрос. Нарушает детерминизм replay.
- **Фикс:** добавить явный `return ""` после `logger.error(...)` в строке 538, ДО проверки worker thread.
- **Статус:** NEW

#### NEW-DLG-006 — `router.py:610-620` мёртвый код после `return`
- **Файл:строка:** `backend/app/services/llm/router.py:610-620`
- **Severity:** Low
- **Фикс:** удалить строки 611-620.
- **Статус:** NEW

#### NEW-DLG-007 — `openai_compatible_provider.py` `params.get()` на `GenerationParams` dataclass
- **Файл:строка:** `backend/app/services/llm/openai_compatible_provider.py:37-58`
- **Severity:** Critical
- **Симптом:** При переключении `provider_type="openai"` первый же LLM-вызов падает с `AttributeError: 'GenerationParams' object has no attribute 'get'`.
- **Причина:** `params: Dict[str, Any]` в сигнатуре, но родительский ABC принимает `params: GenerationParams | None`. Код использует `params.get("temperature", ...)` — работает для dict, не для dataclass.
- **Фикс:**
  ```python
  def complete(self, prompt, params: GenerationParams | None = None, system_prompt=None):
      _temp = params.temperature if params else self._temperature
      _max_tok = params.max_tokens if params else self._max_tokens
      payload = {"model": self._model_name, "messages": messages,
                 "temperature": _temp, "max_tokens": _max_tok}
  ```
- **Статус:** NEW

#### NEW-DLG-008 — `prompt_loader.py` `settings.BASE_DIR` AttributeError
- **Файл:строка:** `backend/app/services/verbalization/prompt_loader.py:33`
- **Severity:** Medium
- **Симптом:** При передаче относительного пути — `AttributeError: 'Settings' object has no attribute 'BASE_DIR'`. `BASE_DIR` — module-level переменная, не поле `Settings`.
- **Фикс:**
  ```python
  from app.core.config import BASE_DIR
  if not path.is_absolute():
      path = BASE_DIR / filename
  ```
- **Статус:** NEW

#### BUG-DLG-043 — `rules_agent.py` `random.randint(2, 20)` для d20
- **Файл:строка:** `backend/app/agents/rules_agent.py:246-250`
- **Severity:** High (L2 RNG violation)
- **Фикс:** `KernelRNG.roll_d20()`.
- **Статус:** STILL_BROKEN

#### BUG-DLG-044 — `llama_cpp_provider.py` `random.randint` для LLM seed
- **Файл:строка:** `backend/app/services/llm/llama_cpp_provider.py:163`
- **Severity:** High (L2 RNG violation)
- **Фикс:** `KernelRNG.next_int(0, 2**31 - 1)`.
- **Статус:** STILL_BROKEN

#### BUG-DLG-CAUSAL-4.7.48 — `MockProvider` проверяет `ENIGMA_ENV` вместо `settings.environment`
- **Файл:строка:** `backend/app/services/llm/mock_provider.py:124-138`
- **Severity:** High
- **Симптом:** MockProvider в production молча возвращает `""`. Игрок видит «Тишина.» — неотличимо от реальной ошибки LLM.
- **Фикс:** `from app.core.config import settings; if settings.environment == "production": ...`.
- **Статус:** STILL_BROKEN

#### BUG-DLG-CAUSAL-4.7.49 — `dm_agent.py` CJK retry `json.loads` bypasses DMResponseNormalizer
- **Файл:строка:** `backend/app/agents/dm_agent.py:853-874`
- **Severity:** Medium
- **Фикс:** `_dm_output_retry = DMResponseNormalizer.normalize(raw_retry); dm_text = _dm_output_retry.dm_text`.
- **Статус:** STILL_BROKEN

---

### 3.3. DOM-MVP: MVP / FRONTEND / RENDERING

#### NEW-MVP-001 — `game_screen.py` silent `except` → MVP popup не показывается
- **Файл:строка:** `frontend/game_screen.py:891-893`
- **Severity:** Critical (корневая причина S-2)
- **Симптом:** MVP окно не всплывает. `except Exception` ловит `RuntimeError("TruthState not loaded")` от `build_end_screen`, печатает в stdout, но НЕ устанавливает `show_end_screen=True`.
- **Фикс:**
  ```python
  except Exception as _mvp_err:
      print(f"[MVP] popup failed: {_mvp_err}")
      self.show_end_screen = True  # ← ПОКАЗАТЬ даже с ошибкой
      self._end_screen_data = {"error": str(_mvp_err)}
  ```
- **Статус:** NEW

#### NEW-MVP-002 — `game_launcher.py` Continue flow не вызывает `init_campaign`
- **Файл:строка:** `game_launcher.py:281` (Continue flow)
- **Severity:** Critical (корневая причина S-2)
- **Симптом:** `mvp_controller.init_campaign()` не вызывается → `truth_state=None` → `build_end_screen()` → `RuntimeError` → NEW-MVP-001 silent fail.
- **Фикс:** в Continue flow вызвать `new_game()` (или явно `mvp_controller.init_campaign(campaign_id)`).
- **Статус:** NEW

#### NEW-MVP-003 — frontend/backend координаты MVP-триггера не согласованы
- **Файл:строка:** `frontend/game_screen.py:884` (`if py >= 12.5` — Y) vs `backend/app/services/social/exit_trigger.py:14` (`_EXIT_X_THRESHOLD = 18.0` — X)
- **Severity:** High
- **Симптом:** `exit_trigger.py` — фактически мёртвый код (используется только в тестах). Frontend триггерит по Y≥12.5, backend по X≥18.0. Никогда не совпадают.
- **Фикс:** унифицировать координаты (выбрать одну ось), либо удалить `exit_trigger.py` и использовать только frontend-триггер + backend `serialize_end_screen`.
- **Статус:** NEW

#### NEW-MVP-004 — Direct gateway возвращает усечённые данные
- **Файл:строка:** `frontend/game_screen.py` (Direct gateway path)
- **Severity:** Medium
- **Симптом:** Direct gateway path возвращает усечённый `end_screen` (6 полей) вместо полного backend DTO (10+ полей).
- **Фикс:** пробросить полный DTO.
- **Статус:** NEW

#### NEW-MVP-005 — `"exited": True` hardcoded
- **Файл:строка:** `frontend/game_screen.py` (end screen data)
- **Severity:** Medium
- **Симптом:** `exited` всегда `True` независимо от реального исхода.
- **Фикс:** читать из backend response.
- **Статус:** NEW

#### NEW-MVP-006 — дублированный рендер-блок end screen
- **Файл:строка:** `frontend/game_screen.py`
- **Severity:** Medium
- **Фикс:** объединить блоки.
- **Статус:** NEW

#### NEW-MVP-007 — `sprite_registry` указывает на несуществующую папку текстур
- **Файл:строка:** `frontend/map_editor/sprite_registry.py:21` (и `:161`)
- **Severity:** Critical (корневая причина S-4)
- **Симптом:** ВСЕ `get_entity_sprite()` возвращают `None` → fallback на `pygame.draw.circle`. Реальные текстуры лежат в `pixels/Pers/traktir/Детектив.png`, `Трактирщик.png` — registry их не использует.
- **Причина:** `path = pixels/2-Bit Pack/Deadbeat/deadbeat_b.png` — такой папки/файла НЕТ.
- **Фикс:**
  ```python
  # sprite_registry.py — заменить путь на реальные текстуры:
  _NPC_SPRITE_MAP = {
      "tavern_keeper_tornin": "Pers/traktir/Трактирщик.png",
      "detective": "Pers/traktir/Детектив.png",
      # ... добавить остальные NPC
  }
  # + убрать silent return None, добавить logger.warning
  ```
- **Статус:** NEW

#### NEW-MVP-008 — NPC персональные спрайты никогда не загружаются
- **Файл:строка:** `frontend/map_editor/sprite_registry.py:161`
- **Severity:** Critical
- **Симптом:** `sprite_registry.get("Deadbeat/deadbeat_b", col, row)` — generic tileset. Персональные спрайты NPC (`Детектив.png`, `Трактирщик.png`) не подключены.
- **Фикс:** добавить NPC-specific sprite lookup по `npc_id` (см. фикс NEW-MVP-007).
- **Статус:** NEW

#### NEW-MVP-009 — `test_mvp_simulation_validation.py` не тестирует MVP popup
- **Файл:строка:** `backend/app/tests/test_mvp_simulation_validation.py`
- **Severity:** High
- **Симптом:** Имя теста вводит в заблуждение — реальный E2E тест MVP popup отсутствует. Тест проверяет только simulation integrity, не popup.
- **Фикс:** добавить E2E тест: trigger exit → assert `show_end_screen=True` → assert `end_screen_data` populated.
- **Статус:** NEW

#### NEW-MVP-010 — `display_manager.py` название вводит в заблуждение
- **Файл:строка:** `frontend/display_manager.py`
- **Severity:** Low
- **Симптом:** Не управляет переключением экранов (game → MVP/end), как ожидается из названия.
- **Фикс:** переименовать или реализовать screen-state-machine.
- **Статус:** NEW

#### NEW-MVP-011 — дублированные константы MVP-триггера
- **Файл:строка:** `frontend/game_screen.py` + `frontend/constants.py`
- **Severity:** Medium
- **Фикс:** вынести в `constants.py` единый источник.
- **Статус:** NEW

#### NEW-MVP-012 — `version.txt` не обновлён
- **Файл:строка:** `version.txt`
- **Severity:** Low
- **Симптом:** `version.txt = 0.5.5.3.6.10`, zip назван `V.0.5.3.7.0`. Рассинхрон.
- **Фикс:** `echo "0.5.3.7.0" > version.txt`.
- **Статус:** NEW

#### BUG-FB-001 — SSE `done` без `world_snapshot`
- **Файл:строка:** `backend/app/services/game_loop/__init__.py:1401-1412`
- **Severity:** High
- **Симптом:** SSE `done` yield не содержит `world_snapshot` (только в death-branch line 1332). Фронтенд не получает финальное состояние мира после хода.
- **Фикс:** добавить `world_snapshot` в `done` yield.
- **Статус:** STILL_BROKEN

#### BUG-FB-036 — 1138 `print()` в 136 файлах (регрессия)
- **Файл:строка:** multiple (cross-domain)
- **Severity:** Medium (L21 violation, регрессия — было 35+ в 11 файлах)
- **Фикс:** заменить на `logger.info/debug/warning`, либо удалить.
- **Статус:** STILL_BROKEN (REGRESSION)

#### BUG-FB-021 — `MockProvider` проверяет `ENIGMA_ENV` (дублирует BUG-DLG-CAUSAL-4.7.48)
- **Статус:** STILL_BROKEN (см. BUG-DLG-CAUSAL-4.7.48)

---

### 3.4. DOM-ORIENT: NPC ORIENTATION / SPATIAL

#### NEW-ORIENT-001 — `body_heading` обновляется только при микро-jitter
- **Файл:строка:** `backend/app/services/spatial/movement_engine.py:432-513`
- **Severity:** Critical (корневая причина S-3)
- **Симптом:** NPC не поворачивается при восприятии игрока или macro relocation. Единственный WRITE в `body_heading` — `_resolve_micro_movement` (LOD0 collision-avoidance). Macro relocation создаёт SceneChange с `field="position"`, но НЕ `field="body_heading"`.
- **Фикс:**
  ```python
  # movement_engine._resolve_macro_relocation — добавить SceneChange для heading:
  _heading = math.atan2(_new_y - _old_y, _new_x - _old_x)
  scene_changes.append(SceneChange(npc_id, "body_heading", _heading))
  # + создать PerceptionOrientationSystem (новая фаза) — при perception event
  #   вычислять heading к игроку
  ```
- **Статус:** NEW

#### NEW-ORIENT-002 — Frontend НИКОГДА не вращает NPC-спрайты
- **Файл:строка:** `frontend/scene_renderer.py:445-458`
- **Severity:** Critical (корневая причина S-3)
- **Симптом:** `pygame.transform.scale + blit` БЕЗ `rotate`. Player рендерится как polygon-стрелка с поворотом (`cos_a/sin_a`, line 729-757). NPC — нет. АСИММЕТРИЯ.
- **Фикс:**
  ```python
  # scene_renderer._draw_npcs — повернуть спрайт:
  if sprite is not None:
      _angle_deg = -math.degrees(entity.body_heading)
      _rotated = pygame.transform.rotate(sprite, _angle_deg)
      _rect = _rotated.get_rect(center=screen_pos)
      surface.blit(_rotated, _rect)
  else:
      # fallback — треугольник вместо круга (есть ориентация)
      _tip = (screen_pos[0] + 12*math.cos(entity.body_heading),
              screen_pos[1] + 12*math.sin(entity.body_heading))
      pygame.draw.polygon(surface, color, [_tip, _left, _right])
  ```
- **Статус:** NEW

#### NEW-ORIENT-003 — Нет модели `head_yaw` (тело и голова — одно поле)
- **Файл:строка:** `backend/app/domain/snapshot.py:71-99` (`NPCPositionDTO`), `frontend/game_types.py:33-107` (`PerceivedEntity`)
- **Severity:** Critical (корневая причина S-3)
- **Симптом:** Греп `head_yaw|head_rotation|neck_yaw|look_at_player|look_target` по всему проекту — 0 совпадений. Невозможно повернуть голову отдельно от тела.
- **Фикс:**
  ```python
  # snapshot.py NPCPositionDTO:
  @dataclass
  class NPCPositionDTO:
      ...
      body_heading: float = 1.5708
      head_yaw: float = 0.0  # ← ДОБАВИТЬ (offset от body_heading, [-pi, pi])

  # game_types.py PerceivedEntity — аналогично
  ```
- **Статус:** NEW

#### NEW-ORIENT-004 — `facing_towards_player: True` HARDCODED (fake data)
- **Файл:строка:** `backend/app/services/spatial/player_target_pipeline.py:199`
- **Severity:** High
- **Симптом:** Все NPC всегда «смотрят на игрока» со 100% видимостью. DM SceneBuilder (`dm_scene_builder.py:124-127`) использует это для visibility calc — fake данные маскируют реальные проблемы ориентации.
- **Фикс:**
  ```python
  _dot = math.cos(entity.body_heading) * (player_x - npc_x) + \
         math.sin(entity.body_heading) * (player_y - npc_y)
  _dist = math.hypot(player_x - npc_x, player_y - npc_y)
  facing_towards_player = _dot > 0 and _dist < FOV_RANGE
  ```
- **Статус:** NEW

#### NEW-ORIENT-005 — `front_engine.py` название вводит в заблуждение
- **Файл:строка:** `backend/app/services/character/front_engine.py` (весь файл)
- **Severity:** Medium
- **Симптом:** «Front» — психологическая маска (HUMBLE/TOUGH/COMPLIANT/GUARDED/DECEPTIVE) для ИГРОКА, не ориентация. Термин перегружён, разработчики путают.
- **Фикс:** переименовать в `persona_mask_engine.py` / `demeanor_engine.py`.
- **Статус:** NEW

#### NEW-SPATIAL-001 — Zombie traversals не удаляются
- **Файл:строка:** `backend/app/services/spatial/traversal_execution_system.py:90, 110-113`
- **Severity:** Medium
- **Симптом:** `completed_npcs` строится, cleanup loop — пустой `pass`. Zombie traversals накапливаются.
- **Фикс:** реализовать cleanup (remove completed traversals from active set).
- **Статус:** NEW

#### NEW-SPATIAL-002 — ProbeRunner не блокирует тик
- **Файл:строка:** `backend/app/services/probes/probe_runner.py:24-25`
- **Severity:** Low
- **Симптом:** ProbeRunner только логирует ERROR, не блокирует тик. Invariant violations проходят.
- **Фикс:** добавить strict mode `if violation and settings.strict_invariants: raise SimulationIntegrityError(...)`.
- **Статус:** NEW

#### NEW-SPATIAL-003 — `perceptual_momentum.py` НЕ сглаживает NPC orientation
- **Файл:строка:** `frontend/perceptual_momentum.py` (весь)
- **Severity:** Low
- **Симптом:** Сглаживает только `ManifestationProfile`, не `body_heading`. NPC heading дёргается.
- **Фикс:** добавить LERP для `body_heading` (как уже сделано для player position в `scene_renderer.py:148-152`).
- **Статус:** NEW

#### NEW-SPATIAL-004 — `world_snapshot_builder.py:253` `print()` в production
- **Файл:строка:** `backend/app/services/integration/world_snapshot_builder.py:253`
- **Severity:** Low (часть BUG-FB-036 регрессии)
- **Фикс:** `logger.info(...)`.
- **Статус:** NEW

#### BUG-SPATIAL-030 — `cluster_relation` всегда «adjacent»
- **Файл:строка:** `backend/app/services/spatial/spatial_query_service.py:81-98`
- **Severity:** Medium
- **Симптом:** `cl_b in cluster_to_entities` всегда `True`. `neighbors` вычисляется, но НЕ используется. ClusterGraph не внедрён.
- **Фикс:** реализовать `ClusterGraph` с реальной топологией кластеров.
- **Статус:** STILL_BROKEN

#### BUG-SPATIAL-032 — `life_engine.py` читает `player_spatial` как fallback (Double Truth)
- **Файл:строка:** `backend/app/services/npc/life_engine.py:861-867`
- **Severity:** High (L9 violation)
- **Симптом:** Comment «FIX», но код всё ещё читает `player_spatial` как fallback. ADR-048 не enforced.
- **Фикс:** удалить `player_spatial` fallback, использовать только `npc_positions.player`.
- **Статус:** STILL_BROKEN (workaround)

#### BUG-SPATIAL-033 — `scene_init.py` читает `player_spatial` как fallback
- **Файл:строка:** `backend/app/services/game_loop/scene_init.py:79-82`
- **Severity:** Medium
- **Фикс:** удалить `player_spatial` fallback.
- **Статус:** STILL_BROKEN

#### BUG-SPATIAL-036 — L11 Spatial Coherence SC-2…SC-8 не реализованы
- **Файл:строка:** `backend/app/services/probes/probes/spatial_coherence_probe.py`
- **Severity:** Medium
- **Симптом:** Только SC-1 реализован. SC-2…SC-8 не существуют. ProbeRunner не блокирует тик.
- **Фикс:** реализовать SC-2…SC-8 probes.
- **Статус:** STILL_BROKEN

---

### 3.5. DOM-MEM: NPC MEMORY

#### NEW-MEM-001 — `EventSemanticTagger` map keys не совпадают с `EventType` values
- **Файл:строка:** `backend/app/services/memory/event_semantic_tagger.py:26-45` vs `backend/app/services/events/event_types.py:31-80`
- **Severity:** Critical (корневая причина S-5)
- **Симптом:** `_EVENT_SEMANTIC_MAP` keys = `"player_attacks"`, `"player_threatens"` (lowercase). `EventType.PLAYER_ATTACKED.value = "PLAYER_ATTACKED"` (uppercase). НЕ совпадают. `EvidenceMapper` возвращает `[]` → `BeliefAggregator.assess([])` → `[]` → **`crystallized_beliefs` table остаётся ПУСТОЙ**.
- **Фикс:**
  ```python
  # event_semantic_tagger.py — использовать .value enum:
  _EVENT_SEMANTIC_MAP = {
      EventType.PLAYER_ATTACKED.value: "aggression",
      EventType.PLAYER_SPOKE.value: "communication",
      # ... привести к единому регистру
  }
  ```
- **Статус:** NEW

#### NEW-MEM-002 — Нет UI/API endpoint для просмотра таблиц воспоминаний
- **Файл:строка:** `backend/app/api/` (отсутствует endpoint)
- **Severity:** Critical (корневая причина S-5)
- **Симптом:** `rg` по `backend/app/api/` → 0 совпадений для `memories|narrative_cache|event_memor`. `yaml_export.py` функции вызываются ТОЛЬКО из тестов. Пользователь не может увидеть содержимое `enigma_memory.db`.
- **Фикс:**
  ```python
  # routes.py — добавить:
  @router.get("/api/debug/memories/{npc_id}")
  def get_npc_memories(npc_id: str, campaign_id: str):
      return memory_manager.dump_npc_memories(npc_id, campaign_id)

  @router.get("/api/debug/memories/export/{npc_id}")
  def export_npc_memories_yaml(npc_id: str, campaign_id: str):
      return YAMLResponse(memory_manager.export_yaml(npc_id, campaign_id))
  ```
- **Статус:** NEW

#### NEW-MEM-003 — `.gitignore` исключает `*.db` и `saves/`
- **Файл:строка:** `.gitignore:6-9`
- **Severity:** Critical (корневая причина S-5)
- **Симптом:** В репозитории НЕТ файла `enigma_memory.db` и НЕТ папки `saves/`. Пользователь видит «пустоту» — думает, что таблицы не формируются, хотя в runtime БД создаётся и заполняется.
- **Фикс:** добавить `saves/enigma_memory.db.example` (empty schema dump), либо README с инструкцией «БД создаётся в runtime в `saves/`».
- **Статус:** NEW

#### NEW-MEM-004 — `CrystallizedBeliefStore._campaign_id` прямая мутация без reset
- **Файл:строка:** `backend/app/services/tick_orchestrator.py:384`
- **Severity:** High
- **Симптом:** `self.crystallized_belief_store._campaign_id = campaign_id` — прямая мутация без reset `_loaded`. При смене кампании beliefs новой кампании НИКОГДА не загружаются. В отличие от `L1Chronicle.bind_campaign` (правильный reset).
- **Фикс:** реализовать `CrystallizedBeliefStore.bind_campaign(campaign_id)` по образцу `L1Chronicle`.
- **Статус:** NEW

#### NEW-MEM-005 — `expectation_store.py` `_logger` NameError
- **Файл:строка:** `backend/app/services/npc/expectation_store.py:53, 137`
- **Severity:** Medium
- **Симптом:** `_logger.error()` — defined `logger`, not `_logger`. Dead code, latent bug.
- **Фикс:** `logger.error(...)` или `self._logger = logger`.
- **Статус:** NEW

#### NEW-MEM-006 — `ExpectationStore` relative path `db_path="memory.db"`
- **Файл:строка:** `backend/app/services/npc/expectation_store.py` (`__init__`)
- **Severity:** Medium
- **Симптом:** Default `db_path="memory.db"` (relative → CWD). Dead code, но latent.
- **Фикс:** `db_path = BASE_DIR / "saves" / "enigma_memory.db"`.
- **Статус:** NEW

#### NEW-MEM-007 — Spatial events не сохраняются в event_memories в idle тиках
- **Файл:строка:** `backend/app/services/phases/memory.py:57`
- **Severity:** High
- **Симптом:** GREEN GATE `if not ctx.phase_2_events: return processed` блокирует `memory_manager.apply()` Block 3 в idle тиках. Spatial events (NPC_MOVED) добавляются в phase_2_events, но если NPC неподвижны — Block 3 пропускается.
- **Фикс:** ослабить gate — Block 3 должен выполняться если есть ANY events (включая spatial), либо убрать gate для spatial-only events.
- **Статус:** NEW

#### NEW-MEM-008 — `RelationshipStore` использует JSON (не SQLite)
- **Файл:строка:** `backend/app/services/memory/relationship_store.py`
- **Severity:** Medium
- **Симптом:** `saves/<campaign_id>/npc_relationships.json` — фрагментированная persistence. Не входит в `enigma_memory.db`.
- **Фикс:** мигрировать в SQLite table `npc_relationships`.
- **Статус:** NEW

#### NEW-MEM-009 — `DialogueUpdateExtractor` не имеет keyword fallback при LLM failure
- **Файл:строка:** `backend/app/services/memory/dialogue_update_extractor.py`
- **Severity:** Low
- **Фикс:** добавить regex/keyword fallback extraction.
- **Статус:** NEW

#### NEW-MEM-010 — `JsonMemoryStore._recent_cache` stale cache
- **Файл:строка:** `backend/app/services/memory/` (JsonMemoryStore)
- **Severity:** Low
- **Симптом:** Stale cache (не в production, но latent).
- **Статус:** NEW

#### NEW-MEM-011 — `memory_manager.apply()` silent skip sqlite save
- **Файл:строка:** `backend/app/services/memory/memory_manager.py` (apply)
- **Severity:** Low
- **Симптом:** Silent skip если store не имеет `save_event_memory`.
- **Статус:** NEW

#### NEW-MEM-012 — `working_memory.apply_decay` O(N) full scan
- **Файл:строка:** `backend/app/services/memory/working_memory.py` (apply_decay)
- **Severity:** Low (N=20, не критично)
- **Статус:** NEW

#### BUG-PERC-014 — L2.5 кристаллизация запускается каждый тик без gate
- **Файл:строка:** `backend/app/services/phases/integration.py:380-422`
- **Severity:** High (L14 violation)
- **Симптом:** GREEN GATE применён только в `phases/memory.py:57`, НО НЕ в `integration.py` для belief crystallization. Кристаллизация запускается каждый тик.
- **Фикс:** добавить `if not ctx.phase_2_events: return` gate в integration.py crystallization block.
- **Статус:** STILL_BROKEN

#### BUG-FB-044 — `l1_chronicle_events` не имеет UNIQUE constraint
- **Файл:строка:** `backend/app/services/npc/l1_chronicle.py:44-54`
- **Severity:** Medium
- **Симптом:** In-memory idempotency guard есть, но БД не защищена — дубликаты возможны при restart.
- **Фикс:** `UNIQUE(campaign_id, target_id, tick_id, event_type)` constraint.
- **Статус:** STILL_BROKEN

---

## 4. ПРИОРИТЕТНЫЙ ПЛАН ФИКСОВ

### Фаза 1 — Восстановление играбельности (Critical, P0)

| # | Bug ID | Описание | Сложность | Файл |
|---|--------|----------|-----------|------|
| 1 | **REGRESSION-CORE-001** | Передать `task_scheduler` в `execute()` (2 вызова) | 2 строки | `npc_orchestration.py`, `phase_2_world_tick.py` |
| 2 | **NEW-MVP-001** | `show_end_screen=True` в except | 3 строки | `game_screen.py:891` |
| 3 | **NEW-MVP-002** | Continue flow вызывает `init_campaign` | 5 строк | `game_launcher.py:281` |
| 4 | **NEW-MVP-007** | Исправить путь текстур в `sprite_registry` | 15 строк | `sprite_registry.py` |
| 5 | **NEW-MVP-008** | Подключить персональные NPC-спрайты | 20 строк | `sprite_registry.py` |
| 6 | **NEW-MEM-001** | Синхронизировать EventSemanticTagger keys с EventType values | 10 строк | `event_semantic_tagger.py` |
| 7 | **NEW-DLG-001** | Добавить `import logging` + `logger` в llm_compressor_client | 2 строки | `llm_compressor_client.py` |
| 8 | **NEW-DLG-007** | Fix OpenAI provider `params` typing | 8 строк | `openai_compatible_provider.py` |
| 9 | **REGRESSION-CORE-002** | Заменить non-serializable `ctx` на dict в TICK_COMPLETED | 5 строк | `tick_orchestrator.py:608-617` |

**Ожидаемый эффект после Фазы 1:** NPC отвечает игроку (topic «ответить»), MVP popup появляется, текстуры загружаются, crystallized_beliefs заполняются, LLM-компрессор не падает с NameError.

### Фаза 2 — Восстановление ориентации NPC (Critical, P0)

| # | Bug ID | Описание | Сложность |
|---|--------|----------|-----------|
| 10 | **NEW-ORIENT-003** | Добавить `head_yaw` в `NPCPositionDTO` + `PerceivedEntity` | 10 строк |
| 11 | **NEW-ORIENT-001** | `body_heading` SceneChange при macro relocation + PerceptionOrientationSystem | 60 строк |
| 12 | **NEW-ORIENT-002** | Frontend `pygame.transform.rotate` для NPC-спрайтов | 25 строк |
| 13 | **NEW-ORIENT-004** | Вычислять `facing_towards_player` из `body_heading` | 15 строк |

**Ожидаемый эффект:** NPC поворачивают головы к игроку, спрайты вращаются.

### Фаза 3 — Видимость памяти + LLM диагностика (High, P1)

| # | Bug ID | Описание | Сложность |
|---|--------|----------|-----------|
| 14 | **NEW-MEM-002** | API endpoints `/api/debug/memories/{npc_id}` + YAML export | 40 строк |
| 15 | **NEW-MEM-003** | README про `saves/enigma_memory.db` (или example dump) | doc |
| 16 | **NEW-DLG-004** | Worker thread: sentinel `LLMUnavailable` вместо `""` | 20 строк |
| 17 | **NEW-MVP-009** | E2E тест MVP popup | 50 строк |
| 18 | **NEW-MVP-003** | Унифицировать координаты MVP-триггера | 10 строк |

### Фаза 4 — Контрактные нарушения (Medium, P2)

| # | Bug ID | Описание |
|---|--------|----------|
| 19 | **BUG-CORE-024/025/026** | `KernelRNG.choice/random` в npc_conversation, dm_response_normalizer, attention_layer |
| 20 | **BUG-DLG-043/044** | `KernelRNG` в rules_agent d20, llama_cpp_provider seed |
| 21 | **BUG-FB-037** | `EventDTO.create_deterministic` с `uuid5` + game_time |
| 22 | **BUG-FB-029/038/039/040/012** | Wall-clock → game_time migration |
| 23 | **BUG-CORE-021** | `KernelRNG` в impact_engine (заменить UUID-seed) |
| 24 | **BUG-PERC-014** | Crystallization gate в integration.py |
| 25 | **BUG-FB-044** | UNIQUE constraint в l1_chronicle_events |
| 26 | **BUG-CORE-013/015/016** | Dead code cleanup (l1_drift_events, DRF overlay, tick_decisions) |
| 27 | **BUG-SPATIAL-032/033** | Удалить `player_spatial` fallback |
| 28 | **BUG-FB-036** | 1138 `print()` → `logger` |

### Фаза 5 — Конструктивные улучшения (Low, P3)

NEW-CORE-002/003/004, NEW-DLG-002/003/005/006/008, NEW-MVP-004/005/006/010/011/012, NEW-ORIENT-005, NEW-SPATIAL-001/002/003/004, NEW-MEM-005/006/008/009/010/011/012, BUG-SPATIAL-030/036.

---

## 5. ДИАГНОСТИЧЕСКИЕ ТАБЛИЦЫ (для верификации фиксов)

### 5.1. Runtime-проверка LLM-цепочки
После фикса REGRESSION-CORE-001 + NEW-DLG-001/004:
1. Запустить `python game_launcher.py`
2. Ввести действие игрока (например, «сказать трактирщику: привет»)
3. Проверить логи: `tail -f backend/logs/enigma_*.jsonl | grep "topic"`
4. Ожидаемый topic: `ответить: привет` (НЕ `idle`)
5. Ожидаемый DM-ответ: осмысленный текст (НЕ «Тишина.»)

### 5.2. Runtime-проверка MVP popup
После фикса NEW-MVP-001/002:
1. Запустить игру, дойти до координат Y≥12.5
2. Ожидаемый результат: `show_end_screen=True`, окно MVP появляется
3. Если `truth_state=None` → окно показывает error-сообщение (НЕ молчит)

### 5.3. Runtime-проверка текстур
После фикса NEW-MVP-007/008:
1. Запустить игру
2. Ожидаемый результат: NPC рендерятся как спрайты (НЕ circles)
3. Проверить логи: `grep "sprite_registry" backend/logs/` — нет `return None` warnings

### 5.4. Runtime-проверка памяти
После фикса NEW-MEM-001/002/003:
1. `GET /api/debug/memories/tavern_keeper_tornin?campaign_id=Open_road`
2. Ожидаемый результат: JSON с `event_memories` + `crystallized_beliefs` (НЕ пустой)
3. `sqlite3 saves/enigma_memory.db "SELECT COUNT(*) FROM crystallized_beliefs"` → > 0 после 5+ тиков с действиями игрока

### 5.5. Runtime-проверка ориентации NPC
После фикса NEW-ORIENT-001/002/003:
1. Запустить игру, подойти к NPC
2. Ожидаемый результат: NPC-спрайт поворачивается к игроку (видно вращение)
3. Проверить DTO: `GET /api/game/state` → `npc_positions[0].body_heading` изменяется при движении игрока

---

## 6. ЗАКЛЮЧЕНИЕ

ENIGMA V.0.5.3.7.0 — **не «изначально невозможная» игра**, а проект с накопленным техническим долгом и одной занесённой регрессией. Архитектура каузального движка структурно здравая: `hub_event` propagation работает, memory pipeline корректен, LLM-router имеет правильную fallback-логику. Проблема — в 15 Critical-багах, которые каскадно блокируют 5 игроко-видимых симптомов.

**Положительная новость:** 9 из 15 Critical-багов (Фаза 1) исправляются ~70 строками кода. После Фазы 1 игра становится играбельной. После Фазы 2 NPC оживают. После Фазы 3 память видима.

**Главный риск:** без REGRESSION-CORE-001 fix любая другая работа бессмысленна — NPC продолжит молчать. Этот фикс должен быть первым.

**Методический вывод:** DNA-метрики (SHI/NPI 100%) врут, потому что измеряют структурную целостность, а не семантическую. Нужно добавить метрику `DRI` (Dialogue Response Integrity) — доля ходов игрока, на которые NPC ответил осмысленно (НЕ «Тишина.» / «Ничего не произошло.»). Без DRI≥80% игра считается нерабочей.

---

*Конец документа. Объём: 57 активных дефектов, 15 Critical, 5 фаз фиксов.*
