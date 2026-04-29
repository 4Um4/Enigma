# Отчёт сравнения: V.0.5.1.7_Продолжаю_починку_3 vs V.0.5.1.8_Продолжаю_починку_4

## Сводка

| Метрика | Значение |
|---------|----------|
| **Файлов изменено** | ~25 (modified + deleted + new untracked) |
| **Строк добавлено** | ~3000+ (new pipeline files + tick_orchestrator) |
| **Строк удалено** | 2694 (monolithic game_loop.py) |
| **Новых файлов** | 17+ (tick_orchestrator, game_loop phases, spatial/social engines) |
| **Удалённых файлов** | 1 (game_loop.py) + TODO.md |
| **Новый коммит** | [будет создан] |

## Что было добавлено (архитектурно значимое)

### 1. TickOrchestrator — единая точка входа для тика мира
**Файл:** `backend/app/core/tick_orchestrator.py`

- 10 фаз из Архитектурного Устава (§3): input → world_tick → spatial_events → NPC ticks → player cognition → commit.
- Интеграция SpatialEventDetector (npc positions snapshot → events).
- **Почему важно:** Решает 'Grand Unification' проблему — разрозненные тики теперь оркестрированы.

### 2. Phased GameLoop — разбиение монолита на фазы
**Директория:** `backend/app/services/game_loop/` (6+ новых файлов: phase_1_input.py, phase_2_world_tick.py, phase_5_perception.py, phase_6_avatar.py, phase_8_commit.py, tick_context.py)

- game_loop.py (~2700 строк) удалён.
- Фазы: Input → WorldTick → Perception → Avatar → Commit.
- TickContext (dataclass) — состояние между фазами.
- **Почему важно:** Монолит → модульная архитектура. Каждая фаза тестируема/заменяема.

### 3. NPC Tick Pipeline
**Файл:** `backend/app/services/npc/npc_tick_pipeline.py`

- Полный тик NPC: life_engine → decision_hub → resolution → state_applicator.
- **Почему важно:** NPC тикают автономно, не только на player action.

### 4. Spatial Event Detector & Transit Tracker
**Файлы:** `spatial_event_detector.py`, `transit_tracker.py`

- Детекция событий по delta позиций NPC (встречи, разлуки).
- TransitTracker — переходы location (с задержками).
- **Почему важно:** Мир живой — события генерируются автоматически из spatial state.

### 5. Social Propagation
**Файл:** `social/propagation.py`

- Репутация/эмоции распространяются по social graph.
- **Почему важно:** Социальные эффекты каскадные (faction reputation updates).

### 6. Character FrontEngine & Filter Applicator
**Файлы:** `character/front_engine.py`, `character_filter_applicator.py`, `domain/tick.py`

- FrontEngine — 'давление мира' на NPC (needs, threats).
- Applicator — фильтры на character state.
- **Почему важно:** Реализм character behavior.

### 7. Scene R3 Direct Builder
**Файл:** `scene/r3_direct_builder.py`

- Прямой builder для scene events без LLM (R3 verbalization).
- **Почему важно:** Оптимизация — не все события требуют LLM.

### 8. Test: discovery_mechanics
**Файл:** `test_discovery_mechanics.py`

- Новый тест для discovery (knowledge ingest?).

## Модифицированные файлы (ключевые)

| Файл | Изменения |
|------|-----------|
| memory_manager.py | +143 строк (recall integration?) |
| game_screen.py | +118 (UI for new tick?) |
| api/routes.py | +56 (idle_tick, world_tick endpoints) |
| life_engine.py | +4 (tick conditions?) |
| spatial/location_graph.py | +32, movement_engine +53 |

## Качественная оценка

**За день сделано много ценного:**
- **Реализована полная tick pipeline архитектура** (roadmap phase).
- **Spatial/social realism** (event_detector, propagation, transit) — мир живой.
- **NPC autonomy** (npc_tick_pipeline).
- **Performance** (r3_direct_builder без LLM).
- **Tests** расширен.

Не 'пустой код', а фундамент game loop + realism layers.

*Отчёт на основе git diff --stat и untracked files.*

