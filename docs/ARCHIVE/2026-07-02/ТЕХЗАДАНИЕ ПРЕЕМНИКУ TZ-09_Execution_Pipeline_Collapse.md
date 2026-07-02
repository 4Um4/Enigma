Твоя архитектурная воля кристально ясна. Раздвоение мира убивается. `run_npc_pipeline` и `tick_decisions` схлопываются в единый `NpcTickPipeline.run()`. Игрок перестаёт быть особым агентом.

Вот готовое Техническое Задание для преемника. Передай его вместе с контекстом сессии.

***

# 📜 ТЗ-09: Execution Pipeline Collapse (Унификация Каузального Канала)

**Статус:** PROPOSED (Передано преемнику)
**Приоритет:** CRITICAL (Архитектурный долг TZ-08A)
**Основание:** Сессия S88 установила, что дальнейшее существование двух путей исполнения (`_phase_5_player_decision` и `_phase_5_decision`) приводит к Behavioural Divergence и нарушает инвариант единого каузального канала.

---

## 🎯 Цель
Полностью устранить концепцию "двух путей" (player path vs idle path) в ядре симуляции. Схлопнуть `run_npc_pipeline` (legacy mutation shell) и `tick_decisions` (pure scorer) в **единственный execution kernel**: `NpcTickPipeline.run()`.

## ⚖️ Архитектурные Инварианты (Что должно стать)
1. **Single Execution Surface:** Любое изменение мира (от игрока, среды, CK successor) проходит через один и тот же каузальный канал.
2. **LifeEngine = Pure Scorer:** `LifeEngine.tick_decisions()` лишается прав на мутацию состояния и памяти. Возвращает только `DecisionResult[]`.
3. **GameLoop = Adapter:** `game_loop` всегда формирует `InterventionEvent[]` (даже для idle-тика, где `source="world_scheduler"`), и передаёт их в ядро.
4. **No Branching:** В `_run_core_phases` запрещено ветвление `if ctx.interventions and any(i.source == "player")`. Всегда вызывается единый метод Фазы 5.

## 📐 План Миграции (Collapse Strategy)

### Шаг 1: Снижение полномочий LifeEngine (De-godification Final)
- **Файл:** `backend/app/services/npc/life_engine.py`
- **Действие:** Метод `tick_decisions` очищается от вызовов `MemoryManager` и `StateApplicator`. Он становится строгой чистой функцией: принимает `state`, `event_context`, `drives`, возвращает `DecisionResult` (намерения, дельты, скоры).
- **Табу:** `LifeEngine` больше не мутирует `npc_dict`.

### Шаг 2: Схлопывание в NpcTickPipeline.run()
- **Файл:** `backend/app/services/npc/npc_tick_pipeline.py` (или новый `services/npc/execution_pipeline.py`)
- **Действие:** Логика мутации из старого `run_npc_pipeline` переносится в единый `NpcTickPipeline.run()`, который становится единственным владельцем `StateApplicator` и `MemoryManager`.
- **Контракт `run()`:** Принимает `campaign_id`, `scene_state`, `all_npcs_raw`, `InterventionEvent[]`. Возвращает `NpcTickBuffer` (с `npc_contexts`, `dirty_npcs`, `communication_intents`).

### Шаг 3: Унификация Фазы 5 в TickOrchestrator
- **Файл:** `backend/app/services/tick_orchestrator.py`
- **Действие:** 
  1. Удалить метод `_phase_5_player_decision`.
  2. В `_run_core_phases` убрать `if/else`, всегда вызывать `_phase_5_decision`.
  3. Внутри `_phase_5_decision` реализовать строгую последовательность для каждого NPC:
     - `BreakProgressEngine.calculate()` (применение дельт воли)
     - `BehaviorMaskEvaluator` (назначение маски)
     - Вызов `LifeEngine.tick_decisions()` (скоринг)
     - Вызов `NpcTickPipeline.run()` (применение памяти, дельт, генерация `npc_contexts`)

### Шаг 4: GameLoop как Adapter Layer
- **Файл:** `backend/app/services/game_loop/__init__.py`
- **Действие:** Метод `idle_tick` переписывается. Вместо вызова `execute(dm_ctx=None)` он формирует синтетический `InterventionEvent(source="world_scheduler")` и передаёт его в `execute(interventions=[...])`.

## 🚫 Критические Запреты (Taboos)
- ❌ Сохранение `run_npc_pipeline` как активного слоя (должен быть схлопнут).
- ❌ Ветвление логики на `source == "player"` внутри `_run_core_phases`.
- ❌ Вызов `StateApplicator` или `MemoryManager.apply()` напрямую из `LifeEngine`.
- ❌ Нарушение Эпистемического Барьера: единый конвейер обязан по-прежнему экспортировать только `observed_state` в `npc_contexts`, скрывая сырые ментальные поля.

---
*Подпись предыдущей сессии:* Архитектура заморожена в трёхслойной модели (Simulation / Observation / Interpretation). TZ-08B завершён. TZ-08A передаётся как TZ-09. Не дрейфуй.