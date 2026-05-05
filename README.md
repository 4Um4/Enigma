# The Fool (ENIGMA Engine)

Локальная narrative-RPG с живым миром, где **Python считает причинность**, а **LLM озвучивает результат**.

Проект в этой ветке (`V.0.5.2.6_Почти_почти_5`) — это рабочее ядро игры **The Fool**: Pygame-клиент, FastAPI backend, тик мира с постоянной time-driven фазой 0.5, память NPC, spatial-контур и атомарное сохранение состояния.

---

## Что это за игра

**The Fool** — сюжетно-системная RPG в стиле «цифровой DM»:
- игрок действует свободным текстом;
- NPC реагируют из состояния (память, стресс, отношения, контекст), а не из скриптов;
- мир продолжает жить на `idle_tick`, даже когда игрок молчит;
- LLM формирует речь/описание, но не является источником истины для состояния мира.

Ключевой принцип проекта: **LLM = Voice, Python = Logic**.

---

## Текущий статус ветки V.0.5.2.6

### Уже реализовано

- Единый `GameLoop` для `run_turn` (REST) и `stream_turn` (SSE) без дублирования пайплайна.
- `TickOrchestrator` как единая точка тика мира (idle + player finalize).
- Фаза `0.5` выполняется в обоих путях (idle и player finalize): время в мире не останавливается на ходе игрока.
- Добавлен `delta_buffer` + агрегация дельт (`_aggregate_deltas`) перед единым `apply_batch()` в фазе persistence.
- В `TickOrchestrator` введён DI-контур: `set_state_applicator()`, `set_reputation_engine()`, `add_idle_handler()`.
- `SceneStateManager` автоматически обогащает сцену `spatial_walls/spatial_obstacles` из editor JSON при загрузке.
- `MovementEngine` переведён на канонический путь `SpatialService` без fallback на `LocationGraph`.
- `graph_compiler.compile_graph()` теперь возвращает `connections` явно, без глобального hidden-store.
- Константы интенсивности действий вынесены в единый `backend/app/domain/constants.py` (`ACTION_INTENSITY`).
- Граница frontend/backend упрочнена: `GameLoop.idle_tick()` возвращает dict (DTO->dict конверсия внутри backend), bridge больше не знает `app.domain.*`.
- `WorldSnapshotDTO` и `/api/world_state` остаются каноническим источником позиций и состояния для фронтенда.
- Атомарный commit через `PersistencePort` + `SqlitePersistenceAdapter` (`atomic_commit`).

### Что важно в проекте The Fool после этого шага

- Симуляция стала менее эксплуатируемой: игрок больше не может "замораживать" time-driven decay своими действиями.
- Пространственный слой стал строже: поведение NPC больше завязано на реальную геометрию сцены из editor-данных.
- Граница слоёв чище: frontend получает только сериализованный snapshot-контракт, а не backend-DTO напрямую.
- Нормализована единая "семантика силы действия" (`ACTION_INTENSITY`) между разбором input и social propagation.

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
  tests/                 # 46 test files (551 test defs)

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

- Идёт миграция части модулей на единые контракты `EventDTO`/`StateDeltas` (часть legacy-мостов ещё остаётся).
- В frontend остаются временные заглушки по части визуальных ассетов и переходов локаций.
- Миграция legacy `LocationGraph` в `SpatialService` ещё не полностью завершена: часть legacy-тестов удалена/пересобирается под новый контракт.

---

## Куда движется проект (Roadmap)

Ближайший вектор The Fool:

1. Завершить унификацию phase handlers на `StateDeltas` и убрать финальные legacy-флаги/мосты.
2. Закрыть migration gap между `LocationGraph` и `SpatialService` (включая тесты без `skip`).
3. Укрепить player cognition + perception pipeline (меньше legacy `dict`, больше типизированных DTO).
4. Упростить frontend слой: убрать временные заглушки, стабилизировать единый рендер world snapshot.
5. Расширить системные тесты для end-to-end сценариев «действие игрока -> коммит мира -> восстановление состояния».

---

## Для ветки V.0.5.2.6_Почти_почти_5

Эта ветка фиксирует шаг от «phase 0.5 как отдельной идеи» к «непрерывной time-driven механике в обоих путях тика»:
- drift-механики встроены в общий ритм мира (idle + player finalize);
- spatial-контур стал каноническим и менее зависимым от legacy-фолбеков;
- boundary между frontend и backend стал чище на idle-пути.

Сравнительный отчёт изменений: `COMPARISON_REPORT_V.0.5.2.6_Почти_почти_5.md`.
