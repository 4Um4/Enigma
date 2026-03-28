# ENIGMA — GAP ANALYSIS v8.1
# Дата: 28 марта 2026
# Источник: Now.md + ENIGMA_ROADMAP_v8.1.md

## Официальный пайплайн v8.1 vs Реальность

| Шаг пайплайна | Файл по roadmap | Реальный файл | Статус |
|---|---|---|---|
| keyword classifier | `input/action_classifier.py` | `services/action_classifier.py` | ✅ работает |
| LLM fallback (UNKNOWN) | `input/intent_parser.py` | **ОТСУТСТВУЕТ** | ❌ не создан |
| affordance check | `action/processor.py` | `services/action/processor.py` | ✅ работает |
| perception filter | `action/processor.py` | `services/npc/perception_filter.py` | ⚠️ создан, не подключён |
| SceneChange объект | `action/processor.py` | `services/scene_change.py` | ✅ работает |
| world_state.apply_change | `simulation/world_state.py` | `services/simulation/world_state.py` | ⚠️ WTB работает, record_event() не вызывается |
| World Token Budget | `simulation/world_state.py` | встроен в world_state.py | ✅ работает |
| event_bus.publish() | `events/event_bus.py` | `services/events/event_bus.py` | ❌ создан, не подключён к processor |
| Python движки | `engines/` | `services/action/python_engines.py` | ✅ работает |
| world_tick() async | `core/scheduler.py` | `services/world_scheduler.py` | ✅ в фоне |
| единый контекст | `simulation/context_builder.py` | `services/state/context_builder.py` | ✅ работает |
| npc_agent.run() | `ai/npc_agent.py` | `agents/npc_agent.py` | ✅ работает |
| dm_agent.stream_narrate() | `ai/dm_agent.py` | `agents/dm_agent.py` | ✅ работает |
| narration + SSE | `output/narration.py` + `ui_adapter.py` | `api/routes_stream.py` | ⚠️ объединено, не разделено |

---

## Критические баги (сейчас ломают игру)

### BUG-1: NPC не помнят разговор ★★★
- `memory_trace` в major_npcs.json всегда пустой
- `build_npc_prompt()` читает `memory_trace[-3:]` — но там ничего нет
- Результат: каждый ход Люся не знает что говорила минуту назад
- **Фикс**: писать в `memory_trace` после каждого хода в `game_loop.py`

### BUG-2: Тень отвечает вместо Люси ★★★
- "говорю ей шёпотом" — "ей" не в списке местоимений `_PRONOUNS`
- Тень имеет `"tier": "major"` → получает приоритет
- **Фикс**: добавить "ей/её/с ней" в `_PRONOUNS` + Тень → `"tier": "minor"`

### BUG-3: routes_debug.py — `import time` отсутствует ★
- `time.time()` вызывается без импорта → падение при обращении к `/debug/health/agents`
- **Фикс**: добавить `import time` в начало файла

### BUG-4: stale import в python_engines.py ★
- Остаток от orchestrator: `from app.services.orchestrator import ...` (если есть)
- **Фикс**: удалить строку

---

## Не подключено (реализовано, но orphan)

| Модуль | Что делает | Когда подключать |
|---|---|---|
| `events/event_bus.py` | pub/sub для GameEvent | Phase 3B.1 — нужно подключить в processor.py |
| `events/event_types.py` | EventType enum + GameEvent | вместе с event_bus |
| `npc/perception_filter.py` | кто видит/слышит событие | вместе с event_bus |
| `simulation/world_state.record_event()` | запись событий для WTB | вместе с event_bus |
| `intent_parser.py` | LLM fallback при UNKNOWN | создать отдельно |

---

## Приоритеты (в порядке важности для игры)

### Сегодня — NPC Intelligence
1. **BUG-2**: Тень tier → minor + "ей" в pronouns (5 мин)
2. **BUG-1**: NPC memory_trace — писать после каждого хода (30 мин)
3. **BUG-3**: import time в routes_debug (1 мин)

### Следующий шаг — EventBus подключение
4. Подключить `event_bus.publish()` из `action/processor.py`
5. Подключить `perception_filter` к event_bus
6. Вызывать `world_state.record_event()` при каждом publish

### После — остальные фазы roadmap
7. `intent_parser.py` — LLM fallback
8. `output/narration.py` + `ui_adapter.py` — разделить SSE
9. Тесты под новую архитектуру (game_loop вместо orchestrator)
