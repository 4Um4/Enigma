# The Fool (ENIGMA Engine)

Локальная narrative-RPG с живым миром, где **Python считает причинность**, а **LLM озвучивает результат**.

Проект в этой ветке (`V.0.5.2.8_Почти_почти_7`) — это рабочее ядро игры **The Fool**: Pygame-клиент, FastAPI backend, тик мира с постоянной time-driven фазой 0.5, память NPC, spatial-контур, cinematic narrative-слой и атомарное сохранение состояния.

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

## Текущий статус ветки V.0.5.2.8

### Уже реализовано

- Единый `GameLoop` для `run_turn` (REST) и `stream_turn` (SSE) без дублирования пайплайна.
- `TickOrchestrator` как единая точка тика мира (idle + player finalize) с phase-цепочкой `0 -> 10`.
- `StateDeltas v2`: введены `DeltaDomain` + typed payloads (`SocialPayload`, `EmotionPayload`, `ReputationPayload`, `IdentityPayload`).
- `_aggregate_deltas()` обновлён до v2-логики: группировка по `(npc_id, domain, target)` и merge payload-объектов.
- `ReactionSubscriber` теперь разделяет реакцию на два канала: `EMOTION` (stress) и `SOCIAL` (fear/trust).
- `SocialDecayHandler` и `ReputationEngine` начали эмитить domain-tagged дельты (с сохранением backward compatibility для legacy-полей).
- Добавлен `_enrich_with_social_relations()` в `npc_loader`: `village_relations.json` реально попадает в runtime `relationship_cache/base_values`.
- В `_build_npc_snapshots()` закрыт критический gap: гарантируется `player` entry даже при наличии NPC->NPC отношений.
- В idle-пути синхронизированы `ctx.npc_states` и `ctx.all_npcs_raw` перед unified mutator (фиксация ADR-004).
- Spatial-контур усилен fallback-логикой: при несовпадении микро- и макро-узлов движок сбрасывается в валидные зоны (`entrance/main_hall`).
- В `scene_init` добавлена инъекция `SpatialService` и для catch-up тиков.
- `WorldSnapshotBuilder` теперь заполняет `display_name` из runtime-данных NPC, а `SceneStateManager` добавляет имя в старые сохранения.
- Frontend получил cinematic narrative-layer: `NarrativeBeat` + `NarrativeRenderer` + пузырь ввода игрока.
- В `TextInput` добавлена физика удержания клавиш (ускоренный repeat), а также предотвращено залипание KEYUP.
- Добавлены новые тесты для NPC social enrichment и full-loop smoke path оркестратора.

### Что важно в проекте The Fool после этого шага

- Мир стал причинно полнее: теперь социальные связи работают не только `NPC -> player`, но и `NPC -> NPC`.
- Phase 8 перестал быть монолитной реакцией: дельты стали типизированными по доменам, что снижает риск конфликтов при дальнейшем расширении (combat/physiology/spatial).
- Уменьшен риск "тихой потери мутаций" в idle-cycle за счет синхронизации источника состояния для `StateApplicator`.
- Пространственный слой стал практичнее в реальных сохранениях: NPC не «застревают» при несовпадении legacy-микрозон и макро-графа.
- Фронтенд ушёл от плоского лога к сценическому представлению реплик; это повышает читаемость диалогов и UX без изменения ядра симуляции.
- Граница backend/frontend остается чистой: truth по миру по-прежнему проходит через snapshot-контракт.

### Внешний референс The Fool (изучено)

Изучен внешний проект **The Fool** (CurseForge modpack, актуальный срез страницы на **7 мая 2026**) как тематический референс по оси «deception/disguise + системный прогресс».
Ссылка: `https://www.curseforge.com/minecraft/modpacks/the-fool`.

Что зафиксировано как полезный вектор для ENIGMA:
- ставка на сильную тематику и узнаваемый tone;
- многослойный прогресс (не только бой, но и социальные/контекстные механики);
- высокая ценность понятного onboarding и play-guide в документации.

Что сознательно не переносится:
- ENIGMA не повторяет modpack-архитектуру и не зависит от Minecraft-экосистемы;
- ядро ENIGMA остается: `LLM = Voice`, `Python = Logic`, с детерминированным state pipeline.

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

Ближайший вектор The Fool:

1. Завершить унификацию phase handlers на `StateDeltas` и убрать финальные legacy-флаги/мосты.
2. Довести `StateApplicator` до полноценной поддержки v2 payload-first пути и снять зависимость от v1 fallback-полей.
3. Закрыть migration gap между `LocationGraph` и `SpatialService` (включая тесты без `skip` и полную нормализацию микрозон).
4. Докрутить эмоциональную модель Phase 8: адаптивные коэффициенты реакций с учётом контекста сцены/отношений.
5. Укрепить player cognition + perception pipeline (меньше legacy `dict`, больше типизированных DTO).
6. Развить cinematic narrative layer: lifetime-эффекты, priority-beats, фильтрация эха на backend-уровне.
7. Расширить системные тесты для end-to-end сценариев «действие игрока -> коммит мира -> восстановление состояния».

---

## Для ветки V.0.5.2.8_Почти_почти_7

Эта ветка фиксирует шаг от «эмоционально реактивного мира» к «типизированному контурy мутаций + NPC->NPC социальным связям + cinematic UI-слою»:
- введен `StateDeltas v2` (domain-tagged payloads) без разрыва совместимости;
- замкнут полный путь NPC->NPC social enrichment (`village_relations.json -> snapshot -> decay`);
- устранены критические точки потери мутаций и spatial-паралича в idle/catch-up путях;
- frontend получил сценический формат реплик (`NarrativeBeat/NarrativeRenderer`) вместо плоского чата;
- тестовый слой усилен новыми инвариантами по social-enrichment и full-loop оркестратора.

Сравнительный отчёт изменений: `COMPARISON_REPORT_V.0.5.2.8_Почти_почти_7.md`.
