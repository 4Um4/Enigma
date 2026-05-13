# The Fool (ENIGMA Engine)

Локальная narrative-RPG с живым миром, где **Python считает причинность**, а **LLM озвучивает результат**.

Проект в этой ветке (`V.0.5.3.0.2_НОВАЯ_РЕАЛЬНОСТЬ_2`) — это рабочее ядро игры **The Fool**: Pygame-клиент, FastAPI backend, тик мира с постоянной time-driven фазой 0.5, память NPC, spatial-контур, слой физиологии/impact, а также закреплённый CFRM Layer 1 (причинное буферирование/классификация событий) как фундамент следующей реальности.

---

## Что это за игра

**The Fool** — сюжетно-системная RPG в стиле «цифровой DM»:
- игрок действует свободным текстом;
- NPC реагируют из состояния (память, стресс, отношения, контекст), а не из скриптов;
- мир продолжает жить на `idle_tick`, даже когда игрок молчит;
- LLM формирует речь/описание, но не является источником истины для состояния мира.

Ключевой принцип проекта: **LLM = Voice, Python = Logic**.

---

## Системная модель The Fool (из проектной концепции)

- **Zero Scripts**: ключевое поведение NPC не скриптуется вручную, а вычисляется из state + событий.
- **Layered Memory**:
  - L1 Numerical (веса для DecisionHub),
  - L2 Event (история для нарратива),
  - L3 Identity (долгие изменения личности).
- **Break System**: "слом" NPC трактуется как деградация согласованности личности, а не как бинарный флаг.
- **Управляемая стохастика**: Dice-слой добавляет вариативность к expected_success, но не заменяет причинную модель.
- **Tabletop UX-вектор**: карта + фишки + карточки NPC, где визуал служит симуляции, а не подменяет её.

---

## Текущий статус ветки V.0.5.3.0.2

### Уже реализовано

- Единый `GameLoop` для `run_turn` (REST) и `stream_turn` (SSE) без дублирования пайплайна.
- `TickOrchestrator` как единая точка тика мира (idle + player finalize) с phase-цепочкой `0 -> 10`.
- `StateDeltas v2` закреплен как основной контракт мутаций: `domain + target + payload`, с валидацией типов payload.
- Введён `Physiology`-домен: `InjuryDTO`, `PhysiologyPayload`, маршрутизация в `StateApplicator` и отдельная политика редукции `PHYSICS_COMPOSITE`.
- Добавлен `Impact Propagation Engine` (`backend/app/services/combat/impact_engine.py`) как pure function `Force -> Tissue -> Pain -> Shock`.
- Добавлен `CombatSubscriber` (Фаза 8): мост `EventDTO -> ImpactIntentDTO -> Physiology deltas` без domain leakage в эмоции.
- Добавлен `PhysiologyDecayHandler` (Фаза 0.5): leaky integrator для боли/усталости/кровопотери + фазовые статусы (`stagger`, `unconscious`).
- Зафиксированы заготовки CFRM: `ClusterGraph`, `EventBuffer`, `ClusterOccupancy`, `classify_event` (`backend/app/models/cfrm.py`).
- В spatial-контуре сохранена LOD-граница: макро-relocation стабилен, микро-движение выделено в отдельный будущий слой (`LocalSteering/Traversal`).
- Frontend дополнен визуальным сглаживанием поворота игрока (lerp), индикаторами внимания NPC, улучшенными narrative-bubbles и корректным отображением системного лога.
- Добавлены целевые тесты для новой архитектуры: `test_impact_engine.py`, `test_combat_subscriber.py`, `test_physiology_decay_handler.py`, `test_combat_pipeline_e2e.py`, `test_cfrm_models.py`.

### Что важно в проекте The Fool после этого шага

- Бой перестал быть «режимом отдельно от мира»: насилие встроено в общий причинный цикл (физика -> шок -> эмоции -> социальные последствия).
- Появилось онтологическое разделение редукций: алгебраические домены агрегируются, физиология интегрируется как инерционный процесс.
- Архитектура готовится к CFRM: от императивных «дельта-команд» к локальным причинным полям и событийной редукции.
- UI перешел от чистого текстового фида к слоистому восприятию сцены: лог/нарратив/визуальное внимание разделены.

### Внешний референс The Fool (изучено)

Изучен внешний проект **The Fool** (CurseForge modpack) как тематический референс по оси deception/disguise + системный прогресс.
Ссылка: `https://www.curseforge.com/minecraft/modpacks/the-fool`.

Что взято как полезный вектор:
- сильная тематическая идентичность;
- многослойный прогресс (социальный, контекстный, не только «урон»);
- явный onboarding и документированный путь входа.

Что сознательно не переносится:
- ENIGMA не копирует modpack-архитектуру;
- ядро ENIGMA остается: `LLM = Voice`, `Python = Logic`, с детерминированной причинной моделью.

---

## Архитектура

```text
Pygame UI (frontend)
  -> GameGateway / ActionQueue
  -> FastAPI routes (/api)
  -> GameLoop
  -> TickOrchestrator
  -> EventBus + Memory + NPC Decision + Spatial
  -> SceneStateManager
  -> SQLite Persistence (runtime truth)
  -> WorldSnapshotDTO
  -> обратно во frontend
```

### Фазовая модель тика (idle)

- `Phase 0` Simulation (LifeEngine)
- `Phase 0.5` Time-driven handlers (social/reputation decay)
- `Phase 1` Input
- `Phase 2` EventBus primary
- `Phase 3` Memory apply
- `Phase 4` Pre-Decision (topic/context)
- `Phase 5` Decision (CommunicationIntent)
- `Phase 6` Post-Decision (Intent -> Event)
- `Phase 8` Handlers drain (deterministic)
- `Phase 9` WorldSnapshot integration
- `Phase 10` Atomic persistence commit

---

## Структура репозитория

```text
backend/
  app/
    api/                 # REST + SSE + debug + world routes
    services/
      game_loop/         # единый ход игрока
      tick_orchestrator.py
      npc/               # decision/state/perception
      memory/            # layered memory
      spatial/           # Spatial Core v1.2
      state/             # persistence adapters
    models/              # DTO/контракты (в т.ч. phase8, spatial_contracts)
  tests/                 # unit/integration набор для runtime, spatial, npc, phase handlers

frontend/
  game_screen.py         # основной игровой экран
  api_client.py          # transport layer + fallback + action queue
  game_loop_bridge.py    # bridge к backend game loop
  map_editor/            # редактор карт/локаций

data/, saves/, config/   # кампании, runtime, NPC-конфиги
```

---

## Технологический стек

- Python 3.11
- FastAPI + Uvicorn
- Pydantic v2
- Pygame
- SQLite (runtime state)
- llama.cpp (server/CLI)

---

## Требования

- Windows (основной target).
- Python 3.11+.
- CUDA GPU желательна для локального LLM (конфиг ориентирован на RTX 3070 Ti 8GB).
- Наличие `llama-server.exe` и `.gguf` модели по путям из `backend/app/core/config.py`.

---

## Установка

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r backend\requirements.txt
pip install pygame
```

Если `pytest`/зависимости уже стоят в окружении, второй шаг достаточно повторять только при обновлениях.

---

## Запуск

### 1. Полный запуск игры (рекомендуется)

```powershell
python game_launcher.py
```

Что делает launcher:
- поднимает backend (`uvicorn app.main:app`), если он ещё не запущен;
- открывает главное меню Pygame;
- позволяет перейти в игру, выбор кампании/персонажа и редактор карты.

### 2. Только backend (API режим)

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Проверка:
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/api/health`

### 3. LLM сервер

- Backend умеет автостартовать `llama-server` через lifecycle, если URL задан.
- Дополнительно есть `backend/start_llm.bat` (legacy script; проверьте путь модели внутри файла).

---

## Основные API точки

- `POST /api/game/action` — игровой ход (frontend sync path).
- `POST /api/game/action/stream` — SSE стрим токенов DM.
- `POST /api/game/idle_tick/{campaign_id}` — фоновый тик мира.
- `GET /api/world_state?campaign_id=...` — снимок мира для рендера.
- `POST /api/player/session/{campaign_id}` — активация сессии игрока.
- `GET /api/health` — health backend + LLM status.
- `GET /api/debug/vram` — монитор VRAM/debug.

---

## Данные и сохранения

Runtime truth хранится в `saves/`:
- `saves/enigma_runtime.db` — сцены/runtime/events.
- `saves/enigma_memory.db` — память/долгие контексты.

Контент/шаблоны:
- `backend/data/campaigns/` — исходные кампании.
- `backend/data/locations/` — шаблоны локаций.
- `config/npc/individuals/` — профили NPC.

---

## Тестирование

Базовый запуск:

```powershell
cd backend
$env:PYTHONPATH='.'
..\.venv\Scripts\python.exe -m pytest tests -v --tb=short
```

Точечные smoke-проверки:

```powershell
..\.venv\Scripts\python.exe -m pytest backend\tests\test_persistence_port.py -q
cd backend
..\.venv\Scripts\python.exe tests\test_spatial_service.py
```

---

## Ограничения текущей версии

- Идёт миграция части модулей на единые контракты `EventDTO`/`StateDeltas v2` (часть legacy-мостов и v1-полей ещё остаётся).
- В frontend остаются временные заглушки по части визуальных ассетов и переходов локаций.
- Миграция legacy `LocationGraph` в `SpatialService` ещё не полностью завершена: fallback добавлен, но требуется полное выравнивание всех archetype/scene позиций.
- `ReactionSubscriber` и decay-handlers пока используют эвристические коэффициенты (MVP): калибровка на длинных кампаниях обязательна.
- `NarrativeRenderer` пока без продвинутой анимации жизненного цикла beat'ов (fade/pin/slam в полном объеме).

---

## Куда движется проект (Roadmap)

Вектор **The Fool** сегодня читается как переход от “механик” к **наблюдаемой причинности** (каузальная песочница + феноменология + pressure→decision замыкание). Это будущее прослеживается напрямую из `docs/Tasks/*`.

1. **CFRM/DTO как runtime-контракт:** усилить связку `EventBuffer + ClusterGraph + MembraneField + LocalCausalSolver` и сделать DTO Registry единственным транспортом между фазами.
2. **Наблюдаемость причинности:** реорганизовать песочницы в классы (micro/system/stress/phenomenology) и ввести обязательный `CausalTraceLogger` (Field → Membrane → Phenomenon → Pressure → Decision → Commit).
3. **Pressure → Decision замыкание:** подтвердить, что `PsychologicalPressure(directive_obedience/fear/uncertainty)` напрямую модулирует utility/goal через DecisionHub и фиксируется в causal trace.
4. **Phenomenology → Presentation:** довести поток “восприятие/феноменология” до `ManifestationProfile/PresentationFirewall`, чтобы фронт отражал субъективные градиенты (а не сырые метрики).
5. **PerceptionMode/DebugSurface:** добавить переключатели режимов восприятия и слой среды `DebugSurface` для инженерной проверки “что видит NPC”.
6. **Spatial gap (macro ↔ micro):** закрыть разрыв между перемещением по узлам и локальным steering через `TraversalState/MovementStep` (планируется как непрерывная интеграция).

---

## Для ветки V.0.5.3.0.1_НОВАЯ_РЕАЛЬНОСТЬ_1


Эта ветка фиксирует переход от «контрактной миграции» к «физико-каузальной модели мира»:
- слой `Physiology + Impact` встроен в основной тик (`phase 0.5` и `phase 8`) без выделения отдельного режима боя;
- введён DRSL (`ReductionPolicy`), который разделяет бухгалтерские и инерционные домены;
- начата формализация CFRM-сущностей (`EventBuffer`, `ClusterGraph`, `ClusterOccupancy`) как базы следующего архитектурного шага;
- фронтенд подготовлен к режимам восприятия: внимание NPC и визуальная подача уже разделены по слоям;
- документация `docs/Tasks` синхронизирована с новой причинной моделью и ТЗ преемнику.

Сравнительный отчёт изменений: `COMPARISON_REPORT_V.0.5.3.0.1_НОВАЯ_РЕАЛЬНОСТЬ_1.md`.
