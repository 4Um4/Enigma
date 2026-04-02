# ENIGMA: Полный Контекст Проекта Для Передачи В LLM

Дата формирования: 2026-04-02  
Репозиторий: `c:\DDD\Codex\VSC_Enigma\Enigma`  
Цель: дать следующей LLM максимально полный и практический снимок текущего состояния системы: структура, зависимости, связи, фактическая работоспособность, разрывы и риски.

---

## 1. Критический параметр решения

Критический параметр: **какой runtime-контур считается «истиной» — `game_loop` или legacy-ветки (`orchestrator`, старые скрипты/README)**.

Факт по коду: рабочий backend-контур сегодня построен вокруг `backend/app/services/game_loop.py` + `game_loop_factory.py` + маршрутов `routes.py`/`routes_stream.py`.

Если будущая LLM будет опираться на legacy-описания (старый `backend/README.md`, `run_terminal_dm.py`, старые bat-файлы), она будет предлагать ошибочные правки.

---

## 2. Что и как проверено (фактологическая база)

### 2.1 Прямо проверено командами

1. Полный индекс файлов репозитория (`rg --files`).
2. Стартовые скрипты: `start_enigma.bat`, `backend/start_backend.bat`, `backend/start_llm.bat`, `frontend/run_frontend.bat`, `backend/run_full_error_tests.bat`, `backend/start_dm_terminal_with_server_working.bat`.
3. Runtime-файлы backend: `app/main.py`, `api/routes.py`, `api/routes_stream.py`, `api/routes_debug.py`, `services/game_loop*.py`, `services/model_router.py`, `services/llm/*`, `services/memory/*`, `services/action/*`.
4. Конфигурация: `backend/app/core/config.py`, `backend/app/core/runtime_config.py`, `backend/config.json`, `backend/data/runtime_ports.py`, `backend/data/runtime_ports.json`.
5. Frontend API-связи в `frontend/ui/index.html`.
6. Проверка синтаксиса Python: `python -m compileall backend\app backend\tests`.
7. Проверка окружения: системный Python и импорт критичных пакетов.
8. Фактический запуск legacy-терминала: `python backend/run_terminal_dm.py`.
9. Статический import-граф `backend/app` с оценкой достижимости модулей от `app.main`.

### 2.2 Ограничения проверки

1. Полноценный прогон тестов невалиден в текущем окружении: рабочее `.venv` сломано.
2. `fastapi/uvicorn/pytest/...` отсутствуют в системном Python, значит runtime FastAPI здесь не подтверждался «живым» запуском сервера.
3. Выводы «работает» делятся на:
   - подтверждено исполнением команды,
   - подтверждено статической связностью кода.

---

## 3. Текущая структура проекта

### 3.1 Корень репозитория

Ключевые директории:

1. `backend/` — основной backend (FastAPI, game loop, сервисы, тесты, данные).
2. `frontend/` — статический UI (`frontend/ui/index.html`).
3. `Models LLM/` — GGUF модели и бинарники `llama.cpp`.
4. `pdf drop/` — внешние PDF-материалы (справочники/книги).
5. `Things/` — отдельные материалы.
6. `docs/` — в корне фактически пусто; основная документация лежит в `backend/docs/` и markdown-файлах корня.

Ключевые файлы корня:

1. `start_enigma.bat` — основной интегральный запуск LLM + backend + frontend.
2. `restart_all.bat`, `test_gemma.bat` — вспомогательные скрипты.
3. Стратегические документы: `README.md`, `Now.md`, `Plan.md`, `ENIGMA_ROADMAP_v8.1.md`, `GAP_ANALYSIS.md`, и др.

### 3.2 Backend (рабочее ядро)

`backend/app/`:

1. `main.py` — FastAPI app, роуты, startup-процедуры, debug/logging и health-проверка LLM.
2. `api/`:
   - `routes.py` — REST API, game/action, combat, characters, readiness, interface endpoints.
   - `routes_stream.py` — SSE endpoint `/api/game/action/stream` (транспорт).
   - `routes_debug.py` — debug API (`/api/debug/*`).
3. `agents/`: `dm_agent.py`, `npc_agent.py`, `rules_agent.py`, `world_sim_agent.py`, plus `memory_manager_agent.py` (не интегрирован в runtime).
4. `core/`: `config.py`, `runtime_config.py`, `settings_*.py`, `error_logger.py` (не интегрирован).
5. `models/schemas.py` — Pydantic схемы API и внутренних структур.
6. `services/`:
   - ядро: `game_loop.py`, `game_loop_factory.py`;
   - действие: `action/*`;
   - LLM слой: `llm/*`, `model_router.py`, `llm_service.py`;
   - NPC: `npc/*`;
   - память: `memory.py`, `memory/*`;
   - события: `events/*`;
   - состояние мира/сцены: `simulation/world_state.py`, `scene_state_manager.py`, `scene_change.py`, `world_scheduler.py`;
   - прикладные сервисы: `campaign_state_service.py`, `player_session_service.py`, `character_service.py`, `combat_service.py`, `readiness.py`.

`backend/data/`:

1. Runtime-конфиг портов: `runtime_ports.py`, `runtime_ports.json`.
2. Состояние кампаний/персонажей: `campaigns/*`, `sessions/*`.
3. NPC и локации: `npcs/*`, `locations/*`.
4. Память/логи: `*_memory_*.jsonl`, `logs/*`.

`backend/tests/`:

1. Набор тестов (`test_main.py`, `test_services.py`, `test_provider_manager.py`, и т.д.).
2. Часть тестов отражает уже обновлённый game_loop-контур, часть — исторический контекст.

### 3.3 Frontend

1. Реальный UI: `frontend/ui/index.html` (монолитный файл).
2. `frontend/chat/` и `frontend/map/` — пока заглушки (`.gitkeep`).
3. `frontend/run_frontend.bat` поднимает `http.server` на 8081, что расходится с `start_enigma.bat` (3000).

### 3.4 Внешний AppAgent (внутри backend)

`backend/AppAgent/` — сторонний/вынесенный блок (Android GUI agent), **не подключён к runtime Enigma backend**.

---

## 4. Runtime-связи и реальные контуры исполнения

### 4.1 Главный контур запуска (актуальный)

`start_enigma.bat` -> `backend/start_llm.bat` -> `backend/start_backend.bat` -> `uvicorn app.main:app` -> маршруты `/api/*` -> singleton `game_loop` из `game_loop_factory.py`.

Порты по факту этого контура:

1. LLM server: `127.0.0.1:8080`
2. Backend: `127.0.0.1:8000`
3. Frontend static server: `127.0.0.1:3000`

### 4.2 Игровой путь запроса

1. Frontend отправляет action в `/api/game/action/stream` (SSE) или `/api/game/action` (sync).
2. `routes_stream.py` / `routes.py` валидируют сессию игрока.
3. Вызов `game_loop.stream_turn(...)` / `game_loop.run_turn(...)`.
4. Внутри `game_loop`:
   - ActionProcessor,
   - PythonEngines,
   - Rules/NPC/DM agents,
   - memory/event/scene/world updates,
   - формирование ответа и следов (trace).

### 4.3 Frontend -> Backend endpoint-карта (факт)

Frontend использует:

1. `/api/health` -> есть в `routes.py`.
2. `/api/debug/vram` -> есть в `routes_debug.py`.
3. `/api/game/action/stream` -> есть в `routes_stream.py`.
4. `/api/game/action` -> есть в `routes.py`.
5. `/api/session/state/{campaign}` -> есть в `routes.py`.
6. `/api/npcs/{campaign}` -> есть в `routes.py`.
7. `/api/player/heartbeat` -> есть в `routes.py`.
8. `/api/player/session/{campaign}` -> есть в `routes.py`.
9. `/api/characters/{campaign}` -> есть в `routes.py`.

Вывод: базовая API-связка frontend/backend по основным вызовам присутствует.

---

## 5. Зависимости и инфраструктура

### 5.1 Python зависимости (декларации)

`backend/requirements.txt`:

1. `fastapi==0.115.0`
2. `uvicorn[standard]==0.30.6`
3. `pydantic==2.9.2`
4. `pydantic-settings==2.5.2`
5. `python-multipart==0.0.9`
6. `psutil==6.0.0`
7. `pypdf==5.1.0`
8. `httpx==0.28.1`
9. `aiohttp==3.10.11`
10. `pytest==8.3.3`
11. `pymorphy3`

`backend/pyproject.toml`:

1. Совпадает не полностью с `requirements.txt`.
2. Нет части пакетов (`python-multipart`, `aiohttp`, `pymorphy3` и др.).
3. Это создаёт риск drift между `pip install -r requirements.txt` и `pip install -e .`.

`backend/AppAgent/requirements.txt` (отдельный контур, не runtime Enigma):

1. `argparse`, `colorama`, `dashscope`, `opencv-python`, `pyshine`, `pyyaml`, `requests`.

### 5.2 Non-Python зависимости

1. `Models LLM/llama/llama-server.exe` и сопутствующие DLL/утилиты.
2. GGUF модели.
3. Скрипты рассчитаны на Windows + PowerShell + `http.server`.

### 5.3 Фактическое состояние окружения (на момент проверки)

1. Системный Python: `3.14.3`.
2. Root `.venv` неработоспособен:
   - `.venv\Scripts\python.exe --version` -> `No Python at '...Python311\python.exe'`.
3. Системный Python не содержит критичные пакеты runtime:
   - `fastapi`, `uvicorn`, `psutil`, `pytest`, `httpx` отсутствуют.
4. Значит тестовый/серверный контур в этом окружении не подтверждён живым запуском FastAPI.

---

## 6. Модели и маршрутизация LLM

### 6.1 Что реально есть в `Models LLM/`

Есть:

1. `gemma-3-12b-it-q4_k_m.gguf`
2. `mistral-pygmalion-7b.Q5_K_M.gguf`
3. `Qwen3.5-9B.gguf`
4. `YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf`
5. `llama/llama-server.exe`

Отсутствуют (но фигурируют в конфиге/legacy):

1. `qwen2.5-7b-instruct-q4_k_m.gguf`
2. `saiga_mistral_7b_model-q4_K.gguf`

### 6.2 Логика маппинга агентов

`config.py`:

1. `dm/npc/rules/memory/world -> gemma_12b`
2. `_fallback -> qwen_7b` (файл модели отсутствует)

Следствие: fallback-ветка неустойчива, если Gemma недоступна.

### 6.3 Двойной роутерный слой

Сосуществуют:

1. `app/services/model_router.py` (асинхронное переключение моделей для game_loop).
2. `app/services/llm/router.py` (capability-based роутинг + legacy fallback).

В `game_loop` используется оба слоя в разных местах (основной pipeline и model-info для SSE). Это риск логического drift (разные решения о модели в разных ветках).

---

## 7. Граф связности модулей (backend/app)

Статический импорт-анализ от entrypoint `app.main`:

1. Всего Python-модулей в `backend/app`: `82`.
2. Достижимы из `app.main`: `67`.
3. Недостижимы: `15`.
4. Недостижимые non-`__init__`: `4`.

Недостижимые non-`__init__` модули:

1. `app.agents.memory_manager_agent`
2. `app.core.error_logger`
3. `app.services.llama_cpp`
4. `app.services.pdf_drop_importer`

Интерпретация:

1. Это не «битый код» автоматически, но в основном runtime пути FastAPI они сейчас не участвуют.
2. `pdf_drop_importer` привязан в основном к `run_terminal_dm.py` и тестам.

---

## 8. Что реально работает / частично / не связано / сломано

### 8.1 Работает (подтверждено кодом и/или проверкой)

1. Основная архитектурная связка FastAPI -> routes -> `game_loop` -> сервисы присутствует и связана.
2. Frontend вызывает существующие ключевые backend endpoints.
3. `python -m compileall backend\app backend\tests` проходит (синтаксически валидно).
4. Конфиг видит существующую основную модель Gemma и текущий llama-server binary path.

### 8.2 Частично связано / есть технический долг

1. `runtime_ports.json` и `runtime_config.py` задают `frontend_port=3001`, но фактически используются 3000/8081 в скриптах/UI.
2. `routes_stream.py` комментарии и докстринги говорят про `orchestrator`, хотя фактически вызывается `game_loop`.
3. `routes_debug.py` отдаёт частично mock-like модели агентов (`saiga`, `qwen_9b` hardcoded в dashboard).
4. Dual-router слой (`model_router.py` + `llm/router.py`) создаёт риск рассинхронизации выбора модели.
5. `pyproject.toml` и `requirements.txt` расходятся по наборам зависимостей.

### 8.3 Не связано с runtime (на текущем контуре)

1. `backend/AppAgent/*`.
2. `frontend/chat/*`, `frontend/map/*` (заглушки).
3. Недостижимые модули из раздела 7.

### 8.4 Сломано сейчас (подтверждено прямыми командами)

1. `.venv` неработоспособен (битая ссылка на отсутствующий Python 3.11).
2. `backend/run_terminal_dm.py` падает с `NameError: GameOrchestrator is not defined`.
3. `backend/start_dm_terminal_with_server_working.bat` ссылается на отсутствующую модель `qwen2.5-7b...`.
4. Тестовый скрипт `backend/run_full_error_tests.bat` не является надёжным индикатором прохождения:
   - печатает optimistic сообщения,
   - но фактически получает ошибки `No Python at ...`.

---

## 9. Возможные сценарии при минимальном смещении входных данных

1. Если восстановить валидный Python 3.11 `.venv` + установить зависимости:
   - backend и тесты станут воспроизводимо проверяемыми;
   - многие текущие «неподтвержденные» зоны можно быстро перевести в «подтверждено исполнением».
2. Если оставить dual-router как есть:
   - возможен скрытый drift между моделью фактической генерации и моделью, показываемой в SSE metadata/debug.
3. Если начать рефакторинг, опираясь на старый `backend/README.md`:
   - высокая вероятность восстановить legacy-контур вместо укрепления текущего `game_loop`.
4. Если переключить fallback на отсутствующие файлы моделей:
   - появятся runtime ошибки загрузки модели при деградации/переключении.

---

## 10. Что может перевернуть итоговый вывод

1. Полный живой запуск backend + прогоны тестов в рабочем `.venv` могут изменить статус отдельных подсистем.
2. Наличие локальных незакоммиченных правок (кроме проанализированных) может изменить связность.
3. Если часть скриптов запускается из другого окружения/машины, портовая картина и статус зависимостей могут отличаться.

---

## 11. Альтернативные варианты интерпретации с вероятностью

1. Текущий проект уже достаточно целостен как backend MVP на `game_loop` — `80%`.
2. Проект логически целостен, но эксплуатационно нестабилен из-за окружения и legacy-скриптов — `90%`.
3. Основной риск не в логике игры, а в рассинхроне инфраструктуры (venv/ports/docs/scripts) — `85%`.
4. `run_terminal_dm.py` можно считать полностью legacy и исключить из основного контура — `95%`.

---

## 12. Краткий, но глубокий вывод

Система уже имеет рабочую архитектурную ось (`FastAPI -> game_loop -> services`) и связанный frontend-контур, но текущая эксплуатационная достоверность снижена инфраструктурным drift:

1. broken `.venv`,
2. несовпадающие порты и скрипты,
3. legacy артефакты, которые выглядят «живыми», но фактически ломаются,
4. двойная маршрутизация моделей.

Для следующей LLM правильная стратегия: **держаться `game_loop` как источника истины, отделить legacy, стабилизировать окружение, затем уже оптимизировать механику/память**.

---

## 13. Приоритеты для следующей LLM (операционный список)

1. Восстановить `.venv` под Python 3.11 и единый install-path (`requirements` vs `pyproject` синхронизировать).
2. Починить/удалить legacy `run_terminal_dm.py` и старые bat-скрипты с отсутствующими моделями.
3. Унифицировать портовую модель (`runtime_ports` vs hardcoded `3000/8081/3001`).
4. Убрать dual-router drift (один источник выбора модели + единый metadata канал).
5. Обновить `backend/README.md` под фактический `game_loop` runtime.

---

## Приложение A. Полный Индекс Файлов (snapshot)

```text
backend\__init__.py
backend\app\__init__.py
backend\app\agents\__init__.py
backend\app\agents\dm_agent.py
backend\app\agents\memory_manager_agent.py
backend\app\agents\npc_agent.py
backend\app\agents\rules_agent.py
backend\app\agents\world_sim_agent.py
backend\app\api\__init__.py
backend\app\api\routes.py
backend\app\api\routes_debug.py
backend\app\api\routes_stream.py
backend\app\core\__init__.py
backend\app\core\config.py
backend\app\core\error_logger.py
backend\app\core\runtime_config.py
backend\app\core\settings_dm.py
backend\app\core\settings_npc.py
backend\app\core\settings_rules.py
backend\app\core\settings_world.py
backend\app\main.py
backend\app\models\__init__.py
backend\app\models\schemas.py
backend\app\services\__init__.py
backend\app\services\action\object_resolver.py
backend\app\services\action\player_target_extractor.py
backend\app\services\action\processor.py
backend\app\services\action\python_engines.py
backend\app\services\action_classifier.py
backend\app\services\adventure_loader.py
backend\app\services\campaign_state_service.py
backend\app\services\character_service.py
backend\app\services\combat_service.py
backend\app\services\error_interpreter.py
backend\app\services\events\__init__.py
backend\app\services\events\event_bus.py
backend\app\services\events\event_types.py
backend\app\services\game\__init__.py
backend\app\services\game\combat_math.py
backend\app\services\game\physics_validator.py
backend\app\services\game\sandbox_handler.py
backend\app\services\game_loop.py
backend\app\services\game_loop_factory.py
backend\app\services\knowledge_ingest.py
backend\app\services\llama_cpp.py
backend\app\services\llm\__init__.py
backend\app\services\llm\factory.py
backend\app\services\llm\llama_cpp_provider.py
backend\app\services\llm\provider.py
backend\app\services\llm\provider_manager.py
backend\app\services\llm\router.py
backend\app\services\llm_service.py
backend\app\services\logging_tools.py
backend\app\services\memory.py
backend\app\services\memory\__init__.py
backend\app\services\memory\contradiction_resolver.py
backend\app\services\memory\importance_engine.py
backend\app\services\memory\layered_memory.py
backend\app\services\memory\memory_manager.py
backend\app\services\memory\relationship_store.py
backend\app\services\memory\working_memory.py
backend\app\services\model_router.py
backend\app\services\npc\__init__.py
backend\app\services\npc\life_engine.py
backend\app\services\npc\npc_cognition.py
backend\app\services\npc\perception_engine.py
backend\app\services\npc\perception_filter.py
backend\app\services\npc\psyche_engine.py
backend\app\services\npc\reaction_priority.py
backend\app\services\npc\threat_assessor.py
backend\app\services\pdf_drop_importer.py
backend\app\services\player_session_service.py
backend\app\services\prompt_loader.py
backend\app\services\readiness.py
backend\app\services\scene\__init__.py
backend\app\services\scene\narrative_extractor.py
backend\app\services\scene_change.py
backend\app\services\scene_state_manager.py
backend\app\services\simulation\__init__.py
backend\app\services\simulation\world_state.py
backend\app\services\state\context_builder.py
backend\app\services\system_requirements.py
backend\app\services\vram_monitor.py
backend\app\services\world_scheduler.py
backend\AppAgent\assets\license.txt
backend\AppAgent\assets\testset.md
backend\AppAgent\config.yaml
backend\AppAgent\learn.py
backend\AppAgent\LICENSE
backend\AppAgent\README.md
backend\AppAgent\requirements.txt
backend\AppAgent\run.py
backend\AppAgent\scripts\__init__.py
backend\AppAgent\scripts\and_controller.py
backend\AppAgent\scripts\config.py
backend\AppAgent\scripts\document_generation.py
backend\AppAgent\scripts\model.py
backend\AppAgent\scripts\prompts.py
backend\AppAgent\scripts\self_explorer.py
backend\AppAgent\scripts\step_recorder.py
backend\AppAgent\scripts\task_executor.py
backend\AppAgent\scripts\utils.py
backend\cleanup_bat.py
backend\config.json
backend\data\__init__.py
backend\data\campaign_demo-campaign\npc_relationships.json
backend\data\campaigns\demo-campaign\campaign_state.json
backend\data\campaigns\demo-campaign\characters.json
backend\data\locations\location_templates.json
backend\data\npc_major.gguf
backend\data\npc_mass.gguf
backend\data\npcs\major_npcs.json
backend\data\npcs\mass_npc_templates.json
backend\data\runtime_ports.json
backend\data\runtime_ports.py
backend\data\sessions\demo-campaign.json
backend\data\TODO.md
backend\delete_bat.py
backend\docs\ARCHITECTURE_MODEL_ROUTER.md
backend\docs\Plan.md
backend\docs\README2.md
backend\docs\Tasks\Tasks.md
backend\docs\Tasks\Tasks2.2.md
backend\docs\Tasks\Tasks2.md
backend\docs\Tasks\Tasks3.1.md
backend\docs\Tasks\Tasks3.2.md
backend\docs\Tasks\Tasks3.md
backend\docs\Tasks\Tasks4.md
backend\docs\TODO.md
backend\docs\TODO_dynamic_ports.md
backend\docs\TODO_fix_tests.md
backend\docs\TODO_startup.md
backend\docs\TODO_startup_fix.md
backend\docs\TODO_traceback_logging.md
backend\docs\Промт создание персонажа.txt
backend\Promt_AI.json
backend\pyproject.toml
backend\pytest.ini
backend\README.md
backend\requirements.txt
backend\run_cleanup.bat
backend\run_full_error_tests.bat
backend\run_llama_server_multi.bat
backend\run_terminal_dm.py
backend\run_test_llm.bat
backend\start_backend.bat
backend\start_dev.ps1
backend\start_dm_terminal_with_server_working.bat
backend\start_llm.bat
backend\Test_server.ps1
backend\tests\conftest.py
backend\tests\test_error_interpreter.py
backend\tests\test_full_error_logging.py
backend\tests\test_life_engine.py
backend\tests\test_llm.py
backend\tests\test_main.py
backend\tests\test_npc_cognition.py
backend\tests\test_package.py
backend\tests\test_provider_manager.py
backend\tests\test_psyche_engine.py
backend\tests\test_run_terminal_dm.py
backend\tests\test_services.py
backend\tests\test_startup_checks.py
Before.md
Enigma.zip
ENIGMA_ROADMAP_v8.1.md
frontend\run_frontend.bat
frontend\ui\index.html
GAP_ANALYSIS.md
mermaid-diagram.svg
Now.md
NPC_DIALOGS.md
pdf drop\5e Dungeon Masters Guide - Руководство Мастера RUS.pdf
pdf drop\5e_Players_Handbook_-_Kniga_Igroka_RUS.pdf
pdf drop\Elemental_Evil_Players_Companion.pdf
pdf drop\README.md
pdf drop\Sword Coast Adventurers Guide RUS.pdf
pdf drop\Tasha's Cauldron of Everything RUS.pdf
pdf drop\Waterdeep_Drakoniy_Kush.pdf
pdf drop\Xanathars_Guide_to_Everything_RUS.pdf
Plan.md
PROJECT_FULL_CONTEXT_FOR_LLM.md
README.md
restart_all.bat
ROADMAP_v5.2.md
start_enigma.bat
test_gemma.bat
Things\NPC когда он обязан вмешаться или, наоборот, промолчать .pdf
TODO1.md
Игра.md
Логи.md
План реструктрозации.pdf
```

## Приложение B. Ключевые Факты-Подтверждения (командные результаты)

```text
1) .venv\Scripts\python.exe --version
   -> No Python at '"C:\Users\lipir\AppData\Local\Programs\Python\Python311\python.exe"'

2) python -c "import fastapi"
   -> ModuleNotFoundError: No module named 'fastapi'

3) python backend\run_terminal_dm.py
   -> NameError: name 'GameOrchestrator' is not defined

4) python -m compileall backend\app backend\tests
   -> completed (syntax compile success)
```

## Приложение C. Неподключенные Non-Init Модули (import reachability от app.main)

```text
app.agents.memory_manager_agent
app.core.error_logger
app.services.llama_cpp
app.services.pdf_drop_importer
```
