# The Fool (ENIGMA Engine)

Локальная narrative-RPG с живым миром, где **Python считает причинность**, а **LLM озвучивает результат**.

Проект в этой ветке (`V.0.5.2.9_СМЕНИЛ_подход`) — это рабочее ядро игры **The Fool**: Pygame-клиент, FastAPI backend, тик мира с постоянной time-driven фазой 0.5, память NPC, spatial-контур, cinematic narrative-слой и атомарное сохранение состояния.

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

## Текущий статус ветки V.0.5.2.9

### Уже реализовано

- Единый `GameLoop` для `run_turn` (REST) и `stream_turn` (SSE) без дублирования пайплайна.
- `TickOrchestrator` как единая точка тика мира (idle + player finalize) с phase-цепочкой `0 -> 10`.
- `StateDeltas v2`: введены `DeltaDomain` + typed payloads (`SocialPayload`, `EmotionPayload`, `ReputationPayload`, `IdentityPayload`) с контрактной валидацией.
- `_aggregate_deltas()` работает в v2-режиме: группировка по `(npc_id, domain, target)` и merge payload-объектов.
- `StateApplicator` переведен на payload-first чтение с v1 fallback: маршрутизация по доменам стала явной (`EMOTION`, `SOCIAL`, `REPUTATION`, `IDENTITY`).
- `ReactionSubscriber` и `propagate_social_rumors` разделяют изменения на независимые домены (`EMOTION` и `SOCIAL`), без смешанных дельт.
- Добавлен `_enrich_with_social_relations()` в `npc_loader`: `village_relations.json` реально попадает в runtime `relationship_cache/base_values`.
- В `_build_npc_snapshots()` закрыт критический gap: гарантируется `player` entry даже при наличии NPC->NPC отношений.
- В idle-пути синхронизированы `ctx.npc_states` и `ctx.all_npcs_raw` перед unified mutator (фиксация ADR-004).
- В spatial-контуре выполнен переход на **Semantic Relocation**: макро-движение теперь атомарно меняет `position`, а `SceneStateManager` сразу резолвит `local_position (x,y)` через `SpatialService`.
- Удален `TransitTracker` из макро-цепочки: path-переходы ампутированы, выделена чистая LOD-граница (`Macro Traversal` сейчас, `LocalSteering` запланирован отдельно).
- Spatial-фоллбэки усилены поиском узлов и в формате `location_id:node_id`, и в сокращенном формате.
- В `scene_init` добавлена инъекция `SpatialService` и для catch-up тиков.
- `WorldSnapshotBuilder` теперь заполняет `display_name` из runtime-данных NPC, а `SceneStateManager` добавляет имя в старые сохранения.
- Frontend перешел на двухслойный вывод: `message_log` (NarrativeBeat-пузыри) и `system_log` (системные статусы/ошибки/перемещение).
- В `TextInput` добавлен `Shift+Enter` для многострочного ввода без отправки.
- В `NarrativeRenderer` добавлены корректный перенос с сохранением `\n`, улучшенные стили подачи (`SHOUT`, `WHISPER`, `INTERNAL`) и устойчивый рендер курсора.
- В `game_screen` добавлена анти-эхо фильтрация ответа LLM/NPC через `SequenceMatcher` + разбор многострочного `dm_response` + попытка детекции спикера по известным NPC.
- Добавлены контрактные тесты `backend/tests/test_state_delta_v2.py` для валидации v1/v2 сосуществования и payload type-safety.

### Что важно в проекте The Fool после этого шага

- Закрыт критический class багов «сломанный movement pipeline»: теперь `MovementIntent -> SceneChange(position) -> Spatial resolve (x,y)` работает как единый контракт.
- Появилась устойчивая граница макро/микро движения: макро-узлы больше не маскируют локальное steering-поведение; архитектурный долг выделен явно, а не скрыт в хаках.
- `StateDeltas v2` стал реальным протоколом изменений, а не декларацией: дельты доменно изолированы, агрегируются детерминированно и применяются единым мутатором.
- Фронтенд ушел от «плоского чата»: ввод игрока и реплики сцены разделены по роли, что повышает читаемость и снижает когнитивный шум.
- Заложен практичный контур для боёвки/физиологии: через новые домены можно расширять симуляцию без раздувания `StateDeltas` в god-object.

### Внешний референс The Fool (изучено)

Изучен внешний проект **The Fool** (CurseForge modpack, актуальный срез страницы на **8 мая 2026**) как тематический референс по оси «deception/disguise + системный прогресс».
Ссылка: `https://www.curseforge.com/minecraft/modpacks/the-fool`.

Короткая фактология среза:
- около `28k+` загрузок (на момент среза: `28,189`);
- версия `Minecraft 1.20.1`, загрузчик `Forge`;
- последняя публичная сборка: `TheFool-Client-0.0.1-fix3` (дата релиза `15 мая 2025`);
- выраженный фокус на deception-нарративе, фракционном прогрессе и высоком контентном объёме.

Что зафиксировано как полезный вектор для ENIGMA:
- ставка на сильную тематику и узнаваемый tone;
- многослойный прогресс (не только бой, но и социальные/контекстные механики);
- высокая ценность понятного onboarding и play-guide в документации;
- явное разделение «core loop» и «операционного onboarding» (у modpack отдельно проговорены ограничения установки и обязательные шаги).

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

## Для ветки V.0.5.2.9_СМЕНИЛ_подход

Эта ветка фиксирует переход от «частично рабочей миграции» к «контрактно закреплённому ядру»:
- закреплен протокол `StateDeltas v2` в runtime-применении (`StateApplicator`, `propagation`, тесты контракта);
- устранен архитектурный клин в movement pipeline через переход на `Semantic Relocation` и атомарный `position -> local_position` resolve;
- явно отделены уровни пространства: `Macro Traversal` в production, `LocalSteering` вынесен в планируемый слой;
- усилен cinematic UI-контур: многострочный ввод, фильтрация эха, расширенные стили подачи реплик;
- обновлена документация ADR/DTO/flow, чтобы архитектурные решения были воспроизводимы для следующей итерации.

Сравнительный отчёт изменений: `COMPARISON_REPORT_V.0.5.2.9_СМЕНИЛ_подход.md`.
