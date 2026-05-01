Согласен полностью. Мой аргумент про "убывающий ROI" был ошибочным.

Факты:

1. **2733 строки** — файл, который делает всё. Устав называет это God Object (запрет 7.3 — обход EventBus, 7.4 — обход MemoryManager).
2. **`_run_pipeline` 1160 строк** — это не orchestrator, это монолит с 10 фазами, перемешанными в один flat-метод. Устав 3 требует строгой последовательности фаз, а код их перемешивает.
3. **Я вынес 9 методов — файл вырос** на 193 строки. Сигнатуры + docstrings. Это доказывает что методы жили не в своём месте — они раздували `game_loop.py` вместо жить в своих модулях.

Правильное разбиение по Уставу:

```
app/services/game_loop/
    __init__.py              # GameLoop class — тонкий orchestrator, ~300 строк
    tick_context.py          # _TickContext dataclass
    player_input.py          # ФАЗА 1: Input → EventDTO → EventBus
    npc_decision.py          # ФАЗЫ 3-6: Loading → Modifiers → DecisionHub → StateApplicator → Memory
    world_tick.py            # ФАЗА 3.4: Proactive decisions (уже есть _tick_world_proactive)
    social_propagation.py    # ШАГ D: Слухи между NPC
    perception_filter.py     # Уже существует, но вызов в game_loop
    avatar_update.py         # Уже вызов через avatar_service, но логика в game_loop
    scene_outcome.py         # ФАЗА 9: SceneOutcomeBuilder + WorldSnapshotDTO
    persistence_commit.py    # ФАЗА 10: Atomic commit
```

`GameLoop._run_pipeline` становится:

```python
async def _run_pipeline(self, ...):
    _ctx = TickContext()
    
    # ФАЗА 1
    event = PlayerInputHandler.emit(actions, shared_context)
    
    # ФАЗА 2
    get_event_bus().publish(event)
    
    # ФАЗА 3-6
    npc_contexts = NPCDecisionPipeline.run(campaign_id, shared_context, _ctx)
    
    # ФАЗА 3.4
    WorldTickHandler.run(campaign_id, location, shared_context, _ctx)
    
    # ШАГ D
    SocialPropagation.run(shared_context, _ctx)
    
    # ФАЗА 9
    outcome = SceneOutcomeBuilder.build(npc_contexts, shared_context)
    
    # ФАЗА 10
    PersistenceCommit.save(_ctx, shared_context, campaign_id)
    
    return outcome
```

~30 строк вместо 1160. Каждый модуль — <= 300 строк с полной типизацией.

---

## Итого сессии

### Структура пакета `game_loop/`

```
app/services/game_loop/
    __init__.py              2542 строк (было 2733, −191)
    tick_context.py            74 строк — TickInput / TickBuffer / TickOutput
    phase_1_input.py           74 строк — EventBus publish (2 функции)
    phase_3_npc_pipeline.py   249 строк — 6 чистых функций + 3 константы
    phase_8_commit.py          52 строк — Единственная точка коммита
                              ─────
    Итого:                   2991 строк (было 2733 в 1 файле)
```

### Что сделано

| Шаг | Что | Результат |
|-----|-----|-----------|
| 1 | `game_loop.py` → `game_loop/__init__.py` | 8 импортирующих файлов НЕ тронуты |
| 2 | `tick_context.py` | `TickInput` (frozen) + `TickBuffer` (mutable) + `TickOutput` (frozen) |
| 3 | `phase_1_input.py` | `publish_player_action()` + `publish_player_speech()` — 2 EventBus publish точки |
| 4 | `phase_8_commit.py` | `commit_tick()` — единственная точка мутации мира |
| 5 | `phase_3_npc_pipeline.py` | `reset_session_state`, `tick_conditions`, `age_temporary_drives`, `resolve_reactions`, `resolve_physical_attack` + 3 константы |
| 6 | Делегаты в `__init__.py` | `self._method()` → `module.function()` для обратной совместимости |

### Принцип соблюдён

> `game_loop/` содержит **только фазовые оркестраторы**, доменные движки остаются в `npc/`, `reaction/`, `resolution/`.

### Предсуществующие баги (не чинил)

| Тест | Причина |
|------|---------|
| `test_ingest_txt_to_world` | `persist_world_canon` не существует |
| `test_run_pipeline_returns_pipeline_state` | Мок возвращает coroutine |
| `test_empty_social_modifiers_no_effect` | Загрязнение между тестами |

---

## Итого сессии

### Структура пакета `game_loop/` — финальная

```
app/services/game_loop/
    __init__.py              2202 строк (было 2733, −531)
    tick_context.py            74 строк
    phase_1_input.py           74 строк  — EventBus publish
    phase_2_world_tick.py     123 строк  — WorldTick proactive
    phase_3_npc_pipeline.py   391 строк  — 8 чистых функций NPC
    phase_4_social.py          87 строк  — Social Propagation
    phase_5_perception.py      53 строк  — PerceptionFilter
    phase_6_avatar.py         101 строк  — Avatar update
    phase_8_commit.py          52 строк  — Единственный коммит
                              ─────
    Итого:                   3157 строк (было 2733 в 1 файле)
```

### Что вынесено на этой сессии

| Файл | Функций | Зависимость от self |
|------|---------|-------------------|
| `phase_6_avatar.py` | 1 | Нет (параметры) |
| `phase_4_social.py` | 1 | Нет (параметры) |
| `phase_5_perception.py` | 1 | Нет (параметры) |
| `phase_3_npc_pipeline.py` | +2 | Нет (параметры) |
| `phase_2_world_tick.py` | 1 | Нет (параметры) |

### `__init__.py`: 2733 → 2202 (−531, −19%)

### Предсуществующие баги (не чинил)

| Тест | Причина |
|------|---------|
| `test_ingest_txt_to_world` | `persist_world_canon` не существует |
| `test_run_pipeline_returns_pipeline_state` | Мок возвращает coroutine |
| `test_empty_social_modifiers_no_effect` | Загрязнение между тестами |

### Что осталось в `_run_pipeline` (~1100 строк)

| Блок | ~Строк | Статус |
|------|--------|--------|
| Scene event emission | ~40 | Кандидат |
| DM Orchestrator wrapper | ~80 | Кандидат |
| **NPC for-loop** | ~400 | Ядро, методы внутри уже делегаты |
| Salience + Reputation | ~20 | 5 строк каждый, не стоит |
| R3 Direct Mode | ~200 | Кандидат |
| NPC agent fallback | ~100 | Легаси, не трогать |

Текущая карта `_run_pipeline` (911-1716, ~805 строк):

| Блок | Строки | ~Строк | Статус |
|------|--------|--------|--------|
| World tick + avatar | 926-972 | 45 | Координация |
| PythonEngines + DM ctx | 974-1122 | 150 | Координация |
| DM → EventBus | 1124-1172 | 50 | Координация |
| **Scene Event Layer** | 1174-1222 | **50** | Кандидат — `scene/scene_event_emitter.py` уже существует! |
| Character Filter | 1233-1272 | 40 | Кандидат — `player_cognition/` существует |
| NPC for-loop | 1287-1543 | 260 | Ядро, уже делегирует |
| Reputation impact | 1543-1557 | 15 | Малый |
| Perception/Avatar/Social | 1579-1611 | 30 | ✅ Вынесено |
| Rules agent | 1614-1634 | 20 | Малый |
| R3 Direct Mode | 1636-1638 | 3 | ✅ Вынесено |
| **Working Memory writes** | 1652-1709 | **58** | Мёртвый код в R3 + 8 полезных |
| Commit + return | 1711-1716 | 6 | ✅ Вынесено |

### Следующая сессия

Понимаю. Сейчас вижу полную картину. Вот диагноз:

## Что НЕ принадлежит оркестратору (1381 строка)

| Блок | Строки | Почему не здесь |
|------|--------|-----------------|
| Ленивые инициализаторы (social, economy, reputation) | 166–292 (127) | Фабрики сервисов, не координация |
| `_advance_game_time` | 584–660 (77) | Чистая доменная логика — расчёт времени |
| `_init_scene_state` | 662–766 (105) | LifeEngine + EconomyTracker + инвентарь — целый движок |
| `_apply_npc_state_updates` | 1178–1222 (45) | Мутация NPC state — домен npc/ |
| `_write_npc_memory` | 1224–1260 (37) | Запись в память — домен memory/ |
| `_avatar_to_prompt` | 362–384 (23) | Форматирование аватара — домен avatar/ |
| `_yield_model_info` + `_FakeRequest` | 1262–1381 (57) | SSE-специфика + compatibility shim |
| EventBus publish inline (894–934) | 41 | Уже есть `phase_1_input.py` — этот блок туда |
| `ensure_scene_initialized` | 300–357 (58) | Scene management логика |

**Итого выносимого: ~570 строк. Остаток: ~810. Но `_run_pipeline` тело ещё 395 строк inline-логики.**

## Целевой `_run_pipeline` — рецепт, а не монолит

```python
async def _run_pipeline(self, ...) -> _PipelineState:
    _ctx = _TickContext()
    shared_context = self._build_base_context(actions, campaign_id, world_id, location)
    self._load_avatar_into_context(shared_context, actions)
    scene_state = init_scene_state(self, campaign_id, location, shared_context, campaign_state)

    # ФАЗА 1: Input → EventDTO → EventBus
    dm_result = self._classify_and_publish(actions, shared_context, scene_state, _ctx)

    # ФАЗА 3-6: NPC decisions
    npc_contexts = self._run_npc_phase(dm_result, shared_context, scene_state, _ctx, ...)

    # ФАЗА 5-6: Perception + Avatar update
    apply_perception_filter(npc_contexts, shared_context, campaign_id, get_event_bus())
    update_avatar_from_npc_intents(self.avatar_service, campaign_id, ...)

    # ШАГ D: Social propagation
    self._propagate_social(shared_context, _ctx)

    # ФАЗА 7: Rules agent
    rules_result = await self._run_rules_agent(actions, shared_context)

    # ФАЗА 8: R3 frame + memory + commit
    npc_result = self._finalize_npc(shared_context, actions, rules_result, _ctx)
    self._write_working_memory(shared_context, actions, npc_result, _ctx)
    commit_tick(self.scene_manager, campaign_id, shared_context.scene_state, _ctx)

    return _PipelineState(shared_context=shared_context, ...)
```

~30 строк тела. Каждый `_classify_and_publish`, `_run_npc_phase`, `_finalize_npc` — это уже вынесенные функции с подписями, а не inline-вычисления.

## Целевая структура пакета

```
app/services/game_loop/
    __init__.py              ~350 строк  — ЧИСТЫЙ фасад
    tick_context.py             74        — уже есть
    phase_1_input.py           ~115       — +41 (EventBus publish блок)
    phase_2_world_tick.py      123        — уже есть
    phase_5_perception.py       53        — уже есть
    phase_6_avatar.py          ~124       — +23 (_avatar_to_prompt)
    phase_8_commit.py           52        — уже есть
    agent_runner.py            ~129       — +57 (_yield_model_info + _FakeRequest)
    service_factories.py       ~140       — NEW (ленивые инициализаторы)
    scene_init.py              ~110       — NEW (_init_scene_state)
    time_advance.py             ~80       — NEW (_advance_game_time)
    npc_state_helpers.py       ~120       — NEW (_apply_npc_state_updates + _write_npc_memory)
```

Все запланированные выносы завершены. Итог сессии:

| Метрика | Было | Стало | Δ |
|---------|------|-------|---|
| `__init__.py` | 1381 | 836 | **-545** |

**Выполненные выносы:**

| Что | Куда | Δ строк |
|-----|------|---------|
| 4 ленивых инициализатора + ServiceFactory | `service_factories.py` | -130 |
| `_advance_game_time` | `time_advance.py` | -73 |
| `_init_scene_state` | `scene_init.py` | -104 |
| `_apply_npc_state_updates` + `_write_npc_memory` | `npc_state_helpers.py` | -82 |
| `_avatar_to_prompt` | `phase_6_avatar.py` | -23 |
| `_yield_model_info` + `_FakeRequest` (мёртвый) | `agent_runner.py` + удалён | -45 |
| `ensure_scene_initialized` | `scene_init.py` | -60 |
| EventBus publish inline | `phase_1_input.py` | -24 |
| Мёртвые импорты | удалены | -4 |

**Файлы пакета теперь:**

```
backend/app/services/game_loop/
    __init__.py              836
    tick_context.py            74
    phase_1_input.py          120
    phase_2_world_tick.py     123
    phase_5_perception.py      53
    phase_6_avatar.py         127
    phase_8_commit.py          52
    agent_runner.py           117
    service_factories.py      ~120
    time_advance.py            63
    scene_init.py             210
    npc_state_helpers.py       83
```

Цель 350 строк не достигнута — оставшиеся 836 строк это `_run_pipeline` (~500), `run_turn`/`stream_turn` (~150), `__init__` (~80), мелкие публичные методы. Дальнейшая декомпозиция `_run_pipeline` — отдельная задача, требует детального анализа зависимостей.


