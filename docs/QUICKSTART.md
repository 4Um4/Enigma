# ENIGMA QUICKSTART (Архитектурный гайд)

> **Назначение:** Этот документ — точка входа для разработчиков и LLM-ассистентов. 
> Он объясняет, как устроен проект, где искать код и как работает один тик симуляции.

## 1. Карта файлов (Что читать первым)

Если ты открыл проект, начни с этих файлов в строгом порядке:

1. **`docs/00_CAUSAL_CONTRACT_v2.0.md`** — Высший закон. Архитектурные запреты и онтология.
2. **`backend/app/services/tick_orchestrator.py`** — Сердце игры. Читает состояние, запускает фазы, пишет результат.
3. **`backend/app/services/npc/life_engine.py`** — Мозг NPC. Генерирует интенты (желания) на основе потребностей и расписания.
4. **`backend/app/services/npc/decision_hub.py`** — Воля NPC. Оценивает интенты через Utility-скоринг.
5. **`backend/app/services/scene_state_manager.py`** — Физика мира. Владеет позициями, транзитами и применяет `SceneChange`.
6. **`frontend/game_screen.py`** — Глаза игрока. Главный цикл Pygame, обработка ввода и рендер.

---

## 2. Один ход игрока (End-to-End Trace)

Что происходит, когда игрок нажимает Enter, введя "подойди ко мне"?

```text
1. Frontend (game_screen.py)
   Игрок вводит текст → api_client.py отправляет POST /action на бэкенд.

2. API (routes.py)
   Бэкенд принимает IntentDTO → вызывает GameLoop.player_action().

3. Ядро (TickOrchestrator.execute())
   - Фаза 1: Текст сжимается в IntentSemanticField (MOVE, target="player").
   - Фаза 3: Давление (IntentPressureResolver) вычисляет нагрузку на психику.
   - Фаза 5: DecisionHub скорит интенты NPC. Если приказ легитимен, NPC выбирает APPROACH.
   - Фаза 8: MovementEngine создает TraversalState (NPC начал идти).
   - Фаза 9: Сборка WorldSnapshotDTO (что видит игрок).
   - Фаза 10: SQLitePersistenceAdapter.atomic_commit() (сохранение мира).

4. Frontend (game_screen.py)
   Получает WorldSnapshotDTO → scene_renderer.py интерполирует позицию NPC (Lerp) → Pygame рисует кадр.
```

---

## 3. Триаж багов (Если что-то сломалось)

| Симптом | Где искать | Что проверять |
|---------|------------|---------------|
| **Время застыло** | `tick_orchestrator.py`, `scene_init.py` | Растет ли `game_time_seconds`? Возвращается ли `final_scene_state` из ядра? |
| **NPC не двигаются** | `life_engine.py`, `movement_engine.py` | Генерируются ли `MovementIntent`? Создается ли `TraversalState`? |
| **NPC телепортируются** | `frontend/scene_renderer.py` | Работает ли LERP-интерполяция? Приходит ли `velocity` от бэкенда? |
| **LLM генерирует мусор** | `response_validator.py`, `dm_agent.py` | Проходит ли текст валидацию? Не обрезает ли валидатор нормальные реплики? |
| **Падает IPT** | `backend/tests/IPT.py` | Какой инвариант упал? Смотреть `suspect_files` в выводе. |

---

## 4. Глоссарий (20 ключевых терминов)

- **Tick (Тик)** — Один дискретный шаг симуляции (1 минута игрового времени).
- **TickOrchestrator** — Оркестратор, управляющий всеми фазами тика.
- **InterventionEvent** — Внешнее событие (действие игрока), нарушающее течение симуляции.
- **TraversalState** — Состояние перемещения NPC (от узла А к узлу Б).
- **SceneChange** — Проекция свершившегося физического изменения (дверь открылась, NPC шагнул).
- **DeltaBuffer** — Буфер дельт. Все изменения состояния сначала падают сюда, затем применяются атомарно.
- **PerceptualKernel** — Субъективная модель восприятия NPC (угрозы, неопределенность).
- **DecisionHub** — Единственное место, где NPC принимает решение (Utility-скоринг).
- **WillpowerGate** — Шлюз проверки конфликта воли (подчинится ли NPC приказу игрока).
- **CFRM (Causal Field Resolution Model)** — Локальная модель причинности NPC.
- **Embodiment** — Воплощение. Игрок подчиняется тем же физическим законам, что и NPC.
- **DOUBLE TRUTH** — Архитектурный баг, когда данные хранятся в двух местах и рассинхронизируются.
- **SSOT (Single Source of Truth)** — Единый источник истины (например, `body_state` для HP).
- **IPT (Invariant Probe Tests)** — Быстрые тесты ядра (`backend/tests/IPT.py`). Запускать перед каждым коммитом.
- **CDS (Causal Drift Scanner)** — Пассивный аудитор симуляции (логи).
- **OntologyViolationError** — Критическая ошибка, убивающая тик, если состояние мира стало невалидным (например, `NaN`).
- **L1Chronicle** — Append-only история деформации личности NPC.
- **ETKE-IK** — Система непрерывной кинематики (микроперемещения внутри узла).
- **Boundary Node** — Граница между локациями (дверь, выход из города).
- **SpatialService** — Единый авторитет по пространственной геометрии графа.