# LLM RUNTIME UNIFICATION PROPOSAL

**ENIGMA — унификация runtime llama-server: архитектурное исследование и проект автоматизации**

| | |
|---|---|
| Путь документа | `docs/architecture/LLM_RUNTIME_UNIFICATION_PROPOSAL.md` |
| База исследования | снапшот `Enigma-V.0.5.4.5.7_-_4` (полная кодовая база, включая backend/, frontend/, scripts/, tests/, reports/, docs/) |
| Статус | ЭТАПЫ 0-3 ЗАВЕРШЕНЫ (2026-11-07). Этап 4 в прогрессе (14/30 consumers migrated). Host broker MVP + SDK + silent_subprocess_kwargs SSOT + 14 legacy consumers migrated. IPT 53/1. |
| Метод | каждое существенное утверждение помечено **[ФАКТ]** (проверено по коду/артефактам, с указанием файла) или **[ПРЕДПОЛОЖЕНИЕ]** / **[ОЦЕНКА]** (требует проверки/измерения). |

---

## 0. Резюме для принимающего решение

1. **llama-server сегодня запускают минимум шесть не согласованных между собой механизмов** (игра, backend, IPT-шапка `scripts/llm_server_manager`, два самодельных спавнера в system-тестах, PowerShell-блоки в phenomenology-тестах, ручные скрипты). Ни один из них не знает о существовании остальных. **[ФАКТ — §1.1]**
2. **Владение сервером определяется родством процессов («кто породил»), а использование — HTTP.** Эти две модели не связаны: любой живой HTTP-клиент невидим для владельца и для «уборщика призраков». Отсюда взаимное разрушение тестов. **[ФАКТ — §2]**
3. **Почему IPT роняет другие тесты** — причина не в одновременных запросах к GPU. IPT — самый агрессивный участник: он (а) спавнит сервер по ослабленной health-only проверке (без второй линии — пробы порта, в отличие от прод-пути), (б) убивает «свой» сервер в atexit, даже если им уже пользуются чужие процессы, (в) дважды за прогон запускает KILLER_SPIRIT, убивающий любой llama-server репозитория с мёртвой цепочкой предков — независимо от того, что им активно пользуются живые тесты. Механизмы подтверждены по коду; полный перечень сценариев — §2. **[ФАКТ + 1 неподтверждённый эпизод — §2.4]**
4. **Рекомендация: вариант B — постоянный локальный LLM Host (брокер) + тонкий клиентский SDK**, с передачей данных напрямую в llama-server (control-plane брокер, data-plane прямой). Вариант A (лок-менеджер в каждом процессе) годится как переходный этап, но не даёт кросс-процессной очереди и приоритетов. Вариант C (llama.cpp внутри Python) отвергнут по VRAM-бюджету 8 ГБ. Обоснование — §3, дизайн — §4.
5. **Железо (RTX 3070 Ti 8 ГБ)** допускает ровно один инстанс модели; параллелизм — только через слоты одного llama-server (`--parallel`), и только после измерений. Стартовая конфигурация и методика определения слотов — §5.
6. План внедрения разбит на 7 независимых этапов с откатом на каждом — §7. Технические решения, требующие вердикта Мастера (не решены за него), перечислены в §9.

---

## 1. Карта текущей инфраструктуры (подтверждённые факты)

### 1.1 Все места запуска llama-server

| № | Точка запуска | Файл / функция | Триггер | Особенности команды |
|---|---|---|---|---|
| S1 | Игровой лаунчер | `game_launcher.py::_ensure_llm_running()` (~стр. 218) | каждый старт игры | через `acquire_llama_server_lock`; лог → `backend/logs/llama_server.log`; exe-фолбэк `main.exe`; модель из `settings.llama_cpp_model_path` |
| S2 | Backend при старте | `backend/app/main.py::_background_llm_startup` (lifespan, ~стр. 230) | каждый старт uvicorn | через `acquire_llama_server_lock` + `server_lifecycle.start_llama_server()`; результат в `app.state.startup_status` |
| S3 | Канонический спавнер backend | `backend/app/services/llm/server_lifecycle.py::_spawn_llama_server()` (стр. 151) | старт/рестарт (`/api/llm/restart`, `/llm/select/{key}`) | `--host 127.0.0.1`, `-ngl settings.effective_gpu_layers`, `-c settings.ctx_size`, `-t 8`, `--jinja`; stderr → `backend/logs/llama_server_stderr.log`; отказ при занятом порте |
| S4 | Тестовый менеджер | `scripts/llm_server_manager.py::start_llama_server()` (стр. 80) | IPT + ~30 тестовых файлов (шапка-копипаста) | **health-only проверка reuse** (без пробы порта); `--host localhost`; `-ngl settings.gpu_layers` (не `effective_gpu_layers`); `--jinja`; guard отсутствия exe (CI-safe) |
| S5 | Собственные спавнеры system-тестов | `backend/tests/sandbox/system/test_homeostatic_dialogue_stability.py::_start_llama_server` (стр. 23), тот же в `test_epistemology_pipeline.py` (стр. 22) | запуск этих сценариев | health-only; `--host localhost`; **без `--jinja`**; порт вырезается из URL строковой операцией |
| S6 | PowerShell-блоки phenomenology-тестов | `backend/tests/sandbox/phenomenology/test_memory_fixation.py` (стр. 10, 37, 47), `test_directive_obedience_pipeline.py` (те же строки) | запуск этих сценариев | **`Get-Process llama-server \| Stop-Process -Force` (убийство ВСЕХ llama-server) → собственный спавн → kill своего PID на выходе** |
| S7 | Ручной прод-спавн | `logs/spawn_prod_llama.py` | вручную, разово | захардкоженные абсолютные пути `C:\DDD\...`; `--ctx-size 8192`, `--n-gpu-layers 99`, `CREATE_NEW_PROCESS_GROUP`; **владение не отслеживается** (родитель умирает → сервер-«сирота») |
| S8 | Dev-лаунчер | `backend/start_dev.ps1` (стр. 64–72) | ручной dev-прогон | **`Stop-Process -Force` по всем llama-server**, спавн на **порт 8080**, флаги из `backend/config.json`. **[ФАКТ]** `backend/config.json` в снапшоте отсутствует (проверено `ls backend/`) → скрипт в текущем виде падает на загрузке конфига, т.е. легаси/мёртвый |
| S9 | «Держатель» для замеров | `scripts/det_holder.py` | вручную (M2-матрица детерминизма) | спавн через S4 и `sleep(7200)`; teardown внешний (`Stop-Process`); см. §1.10 |

Дополнительно, CLI-режим провайдера: `backend/app/services/llm/llama_cpp_provider.py::_run_cli_process` (стр. 396) порождает процесс `llama-cli` **на каждый запрос**, если `server_url` пуст — легаси-путь, сейчас неактивен (в `settings.llama_cpp_server_url` всегда непустая строка). **[ФАКТ]**

### 1.2 Все места завершения и очистки процесса llama-server

| № | Точка остановки | Файл / функция | Что именно убивает |
|---|---|---|---|
| K1 | atexit backend | `server_lifecycle.py::kill_llama_server` (стр. 100, регистрация стр. 338) + дублирующий блок в `main.py` (стр. 337–340) | только `started_by_us` (свой Popen) |
| K2 | рестарт/смена модели | `server_lifecycle.py::_stop_llama_server` (стр. 108) | **владелец порта** (psutil→netstat) с проверкой имени `llama-server.exe`/`main.exe`; произвольный процесс на порту щадится. Вызывается из `/api/llm/restart`, `/llm/select/{model_key}` (`backend/app/api/routes.py`, стр. 332–469) |
| K3 | atexit IPT-шапки | `scripts/llm_server_manager.py::kill_llama_server` (стр. 165) | только собственный ребёнок `_llama_proc` — но регистрируется **во всех ~30 тестовых файлах с копипастой шапки**, а сервер может быть переиспользован чужими процессами (см. §2, сценарий A) |
| K4 | «Очистка зомби» игры | `game_launcher.py::_kill_zombies()` (стр. 547) | (1) любой LISTEN на портах 8000 и 8181 через `taskkill /F /T /PID`; (2) **`taskkill /F /IM llama-server.exe` — дважды, безусловное убийство всех llama-server на машине**. Выполняется на каждом старте игры до `_ensure_llm_running` |
| K5 | KILLER_SPIRIT (IPT) | `scripts/ghost_reaper.py::reap()`; вызовы из `backend/tests/IPT.py` (стр. 47–61 — старт; ~стр. 2528 — финал) и `backend/tests/micro/test_cch8_character_debug_runtime_fields.py` (стр. 104–108) | любой процесс с именем `llama-server` или `python + uvicorn app.main:app`, принадлежащий репозиторию (cwd/cmdline), **чей родитель вне «связки» мёртв**. Три признака одновременно: сигнатура, «наш», сиротство. Opt-out: `IPT_NO_REAPER=1` |
| K6 | phenomenology-тесты | PowerShell `Stop-Process` (см. S6) | все llama-server до старта + свой PID после |
| K7 | d61-доктринальный тест | `backend/tests/sandbox/SUPERBOX/scenarios/d61_llm_outage_doctrine_test.py` (шапка: «Сценарий владеет жизнью llama-server (kill x3 / restart x3…)») | убивает и рестартит сервер трижды за прогон (штатно, но глобально разрушительно при параллельных прогонах) |
| K8 | Dev-скрипт | `backend/start_dev.ps1` (стр. 66, 117) | все llama-server на старте; свой процесс на выходе |

**[ФАКТ]** Юнит-тесты уборщика существуют: `backend/tests/sandbox/micro/test_ghost_reaper.py` — 4 канонических случая на моках psutil (живой владелец→spare, сирота→kill, чужой python→не тронут, psutil отсутствует→fault). Прогон-пруф работы: `reports/ipt_s316_final.txt` — `[KILLER_SPIRIT] SPARE pid=2224 llama-server.exe: дерево текущего процесса … убито=0, пощажено=1`, затем `[LLM_MANAGER] llama-server остановлен.` (atexit).

### 1.3 Все проверки готовности сервера

| Проверка | Где | Семантика |
|---|---|---|
| `GET /health` → 200 | `server_lifecycle.py` (`_await_llama_ready`, `restart_llama_server`, `acquire_llama_server_lock`), `scripts/llm_server_manager.py`, `game_launcher.py`, system-тесты | «модель загружена» (готовность), не «процесс жив» |
| Probe bind TCP-сокета на 127.0.0.1:8181 | `server_lifecycle.py::acquire_llama_server_lock` (стр. 341–382) | вторая сигнальная линия: отличает «порт занят — грузится/жив» от «никого нет». **Это проба, а не атомарный захват**: сокет закрывается в `finally` до `Popen` — между пробой и спавном остаётся окно гонки |
| `/health`, `/v1/models`, `""` (три эндпоинта подряд) | `llama_cpp_provider.py::_check_server` (стр. 655) + `check_server_with_retry`, `is_available_with_retry` | провайдерный health |
| Поллинг в `_await_llama_ready` | `server_lifecycle.py` (стр. 227) | 1 с на «живость процесса» (poll), затем `/health` каждые 2 с в бюджете `settings.model_load_timeout_sec` = **120 с** |
| Агрегатор готовности | `backend/app/services/readiness.py` (стр. 133–157) | читает `app.state.startup_status` (`llm_server`, `llm_health`) для `/api/health` |

**[ФАКТ]** Ключевая асимметрия: прод-путь (S1–S3) использует двухлинейный лок (health + bind-probe), тестовый путь S4 и самодельные S5/S6 — **только health**. Инцидент класса «дубль на порту» задокументирован в самом коде: `server_lifecycle.py`, комментарий «ИНЦИДЕНТ 2026-08-30 (двойной llama-server → VRAM 96% → 503 на всех NARRATIVE)… оба стартовых пути проверяли ТОЛЬКО /health — пока первый сервер грузит модель (30–60 сек), health молчит, и второй путь спавнит дубль на тот же порт». Лок был добавлен прод-путям; `llm_server_manager` (путь IPT) лок по-прежнему не применяет. **[ФАКТ]**

### 1.4 Все адреса и порты подключения

| Источник | Значение | Кто использует |
|---|---|---|
| `backend/app/core/config.py` (стр. 96–97, «C2 FIX: Единый источник истины») | `llama_cpp_server_url = http://localhost:8181`, `llama_cpp_port = 8181`; API `127.0.0.1:8000` | весь прод-контур: провайдеры, server_lifecycle, game_launcher, readiness |
| `backend/data/runtime_ports.py` + `backend/data/runtime_ports.json` | `llm_port = 8080`, `api_port = 8000`, `frontend_port = 3001` (в json сейчас 8080) | легаси: `app/core/runtime_config.py::get_llm_url` → `settings.get_llm_server_url()`; напрямую — `backend/tests/test_llm.py` (стр. 33–44). **Второй источник правды о порте, расходящийся с settings (8080 ≠ 8181)** |
| `backend/app/core/config.py::check_llm_servers_health` (стр. 317) | дефолт порта `8080` в примере конфига `llm_servers` | мёртвая ветка (`llm_servers` пуст по умолчанию) |
| `backend/app/services/cognition/direct_llm_client.py` (стр. 18) | дефолт `http://localhost:8181` захардкожен | L4-тесты verifier (P5-B) |
| `scripts/s371_3_server_ab_test.py` (стр. 17) | `http://localhost:8181` захардкожено | A/B-проба response_format |
| `backend/start_dev.ps1` | `http://127.0.0.1:8080` + `--port 8080` | мёртвый dev-скрипт (см. S8) |
| `frontend/api_client.py` (стр. 1379) | backend `http://127.0.0.1:8000` (env `ENIGMA_BACKEND_URL`) | фронтенд к backend API (к llama-server напрямую не ходит) **[ФАКТ по grep]** |

**[ФАКТ]** Таким образом, фактическая топология: один llama-server на 127.0.0.1:8181, один FastAPI backend на 8000, фронтенд ходит только в backend. Риск несут: (а) runtime_ports.json (8080) — им пользуется `test_llm.py`, который при отсутствии сервера на 8080 просто уйдёт в `pytest.skip`, маскируя живой сервер на 8181; (б) локальные хардкоды 8181 в трёх местах.

### 1.5 Конфигурации моделей и контекстов

**[ФАКТ]** Всё из `backend/app/core/config.py`:

- Первичная модель: **Hermes-3-Llama-3.1-8B Q4_K_M** под легаси-ключом **`qwen_7b`** (миграция S374/S380, «non-breaking: model_id stays qwen_7b (17 refs), only file path swapped»). Альтернативы: `qwen_2_5_7b` (Qwen2.5-7B-Instruct-abliterated Q4_K_M), `saiga_llama3_8b` (Saiga-Llama3-8B Q4_K_M). Все три объявлены в `settings.available_models`.
- `agent_model_map`: все агенты (dm, npc, rules, memory, world) → `qwen_7b`. `llm_fallback_enabled = False` («нет fallback — одна модель»).
- Контекст: `settings.ctx_size = 16384` («USL-2: промпт декомпозиции 8284 токена > 8192»), при этом `ModelConfig.context_size = 8192` — в пуле моделей регистрируется 8192, а сервер реально спавнится с 16384 (S3). Метаданные расходятся с фактом.
- Генерация: temp 0.9, top_p 0.9, repeat_penalty 1.12, min_p 0.1, n_keep 800; `llama_cpp_max_tokens 1024`, `dm_max_tokens 220`; `llama_cpp_timeout_sec 30`.
- GPU: `gpu_layers = 99` (фолбэк), `effective_gpu_layers` читает `config/gpu_profile.json` → `n_gpu_layers: 99` (файл существует, проверено). `threads = 8`. Бюджет VRAM из комментариев конфига: модель ~4600 МБ (32 слоя в VRAM), KV ctx=8192 ~600 МБ с flash-attn, ОС+CUDA ~500 МБ, итог ~7192 МБ (88%) — **это проектная оценка из комментариев, не измерение**.
- `MODEL_REGISTRY` в роутере (`router.py::_init_registry`) регистрирует **два** ключа: `qwen_7b` и `saiga_llama3_8b` (третьего ключа пула в реестре роутера нет). Пул (`initialize_model_pool`) регистрирует все три из `settings.available_models`.
- Смена модели в рантайме: `POST /llm/select/{model_key}` (`routes.py` стр. 433–511) — подменяет `settings.llama_cpp_model_path`, `kill_llama_server()` + `restart_llama_server()`.

**[ФАКТ]** Реальная spawn-команда (S3) **не содержит** `--flash-attn`, хотя шапка конфига рекомендует `--flash-attn` в строке запуска, и не содержит `--parallel` (используется дефолт сборки). Расхождение «комментарий-команда» зафиксировано как факт; проверка фактических флагов работающей сборки — пункт испытаний §5.4.

### 1.6 ModelRouter и все его провайдеры

**[ФАКТ]** Архитектура (`backend/app/services/llm/`): `Агенты → ModelRouter → ModelPool (lazy, max_loaded=1) → LlmProvider`.

- **ModelRouter** (`router.py`, синглтон `get_router()`, инициализация `initialize_router()` — вызывается из `build_game_loop`):
  - Маршрутизация по способностям (`Capability`: NARRATIVE, DIALOGUE, RULES_REASONING, WORLD_SIMULATION, MEMORY_SUMMARIZATION, …); карта агентов `DEFAULT_AGENT_CAPABILITY_MAP` (dm→NARRATIVE, npc→DIALOGUE, verifier→DIALOGUE и т.д.).
  - **Защита VRAM внутри процесса**: `asyncio.Semaphore(1)` в `request()` (стр. 322–326) — «только один запрос одновременно».
  - **Слот воркера**: `threading.Lock` + флаг `_request_in_progress`; задача `TaskScheduler` исполняет LLM-вызовы в `ThreadPoolExecutor(max_workers=1)` — комментарий: «router.py не поддерживает concurrency > 1» (`task_scheduler.py` стр. 115–118).
  - **Приоритетная очередь D62** (`LLM_RESILIENCE_V1`, **по умолчанию OFF**, env-флаг, стр. 176–186): canonical/ambient; canonical-бюджет ожидания слота 90 с; ambient cap 8, дедлайн 300 с (DROP с причиной); wall-time потолок выполняющегося вызова 120 с → `/abort` (грейс 2 с) → форфейст слота по epoch (поздний результат превращается в исключение). Константы — CALIBRATION, перевод в env запрещён без flags.yaml.
  - Fallback-политика: перебор preferred keys → любая доступная модель → `RuntimeError("Все модели пула недоступны")`; backoff пула 30 с/300 с после отказа, сброс — только после подтверждённого рестарта (`pool_reset_backoff`, вызывается из `server_lifecycle`).
  - Replay-интеграция: `set_replay_context`, кэш LLM-вызовов (record/playback), стрим через `notify_stream_start/end`.
- **ModelPool** (`provider_manager.py`): `max_loaded=1`; «выгрузка» — просто снятие ссылки (**в server-режиме модель не выгружается из VRAM llama-server — это обёртка над HTTP**); server-mode регистрация моделей не требует локального файла GGUF.
- **Провайдеры** (`factory.py` + модули): `LlamaCppProvider` (серверный режим по `settings.llama_cpp_server_url`: `/v1/chat/completions`, `/completion`, стрим `/completion`, `/abort`; CLI-режим `llama-cli` при пустом URL), `OpenAICompatibleProvider`, `MockProvider` (запрещён в production — RuntimeError в `ProviderFactory.create`). Мёртвые провайдеры удалены (C5-FIX).
- **Обходные пути мимо роутера**: `DirectLLMClient` (`cognition/direct_llm_client.py`) — прямой HTTP к 8181 для L4-тестов verifier; `RouterAdapter` (`cognition/router_adapter.py`) — штатный мост verifier→роутер.

### 1.7 Тестовые fixtures и harnesses

- `backend/tests/conftest.py`: `game_loop_factory` (реальный `build_game_loop` + **мок `TaskScheduler._router`**), `initialized_provider_manager`, `initialized_model_pool` (моки провайдеров), `mock_model_router`, autouse `test_environment` (патчит путь модели). Общие тесты LLM-сервер не поднимают. **[ФАКТ]**
- `backend/tests/gameplay/harness.py` — `TavernGameplayHarness`, «канонический harness §5a.2»: единственная входная точка gameplay-тестов в production runtime; тики только `idle_tick()`, действия только `run_turn()`; временные saves; байт-точные снапшоты каталогов; сам LLM не управляет. **[ФАКТ]**
- `backend/tests/sandbox/experiment_runner.py`, `perturbation_harness.py` — песочные harness'ы (файлы существуют; детальный аудит вне рамок).
- **Шапка IPT-паттерна** (копипаста в ~30 файлах): `try: from scripts.llm_server_manager import start_llama_server, kill_llama_server; start_llama_server(); atexit.register(kill_llama_server)`. Полный перечень файлов — §1.9.

### 1.8 Механизм запуска IPT

**[ФАКТ]** `backend/tests/IPT.py` (~2600 строк) — обычный скрипт (не pytest), запуск `python backend/tests/IPT.py`; в CI — job `invariant-probes` (`.github/workflows/ci.yml`, ubuntu-latest, **без LLM** — работает за счёт guard «exe не найден → continue без LLM»).

Порядок работы:
1. **Шапка (время импорта)**: `start_llama_server()` через S4 + `atexit.register(kill_llama_server)`. Docstring при этом утверждает «Не требует LLM-сервера» (стр. 5) — противоречие с кодом шапки и с предупреждением «Тесты диалогов будут падать». Часть инвариантов прогоняет живой `idle_tick` через GameLoop, где LLM-вызовы возможны (TaskScheduler → ModelRouter); точный перечень LLM-зависимых инвариантов в снапшоте не маркирован — **[ПРЕДПОЛОЖЕНИЕ, требует маркировки]**.
2. **KILLER_SPIRIT до прогона**: `ghost_reaper.reap(dry_run=False)` (если не задан `IPT_NO_REAPER=1`).
3. `_bootstrap_minimal_world()`: `build_game_loop()` с изолированной `saves_dir` во временном каталоге + перенаправление `SpatialRegistry.find_artifact` на артефакт Map Editor (in-process).
4. Прогон ~50 инвариантов (в зафиксированном прогоне `reports/ipt_s316_final.txt` — 49 passed / 0 failed; пропуски печатаются поимённо, IPT-1.1).
5. **KILLER_SPIRIT после прогона** (второй `reap`).
6. **atexit**: kill «своего» llama-server.

### 1.9 Реестр тестов, способных менять процессы, порты, файлы или общие ресурсы

**[ФАКТ — составлено grep-ом по `llm_server_manager|_start_llama_server|ghost_reaper|restart_llama_server` в `backend/tests/`]** 32 файла. Категории:

- **Спавн + atexit-kill (шапка IPT)**: `backend/tests/IPT.py`; `backend/tests/gameplay/test_gc11_relationship_causality.py`; `backend/tests/micro/test_cch8_character_debug_runtime_fields.py` (плюс ghost_reaper-гигиена); `backend/tests/sandbox/scenarios/chronicle_weave_probe.py`, `backend/tests/sandbox/scenarios/chronicle_decompose_probe.py`; `backend/tests/sandbox/terminal_cockpit.py`; SUPERBOX (`backend/tests/sandbox/SUPERBOX/`): `cognition_p2_test.py`, `cognition_p2_g3x_test.py`, `cognition_attention_integration_test.py`, `activity_gap_probe.py`, `ue52_probe.py`, `ue0_baseline_probe.py`, `semantic_torture_test.py`, `cognition_p3d_test.py`, `ue5_ab_probe.py`, `m1_self_intro_probe.py`, `cognition_p3e_test.py`, `epistemic_second_order_test.py`, `semantic_probe_corpus.py`, `epistemic_second_order_attribution_test.py`, `ue4_probe.py`, `epistemic_production_test.py`, `drift_laboratory.py`, `run_terminal_mvp.py`; `backend/tests/sandbox/phase_a_xray_test.py`; `backend/tests/micro/test_det_instrumentation.py`.
- **Собственный спавнер (health-only, без jinja)**: `backend/tests/sandbox/system/test_homeostatic_dialogue_stability.py`, `backend/tests/sandbox/system/test_epistemology_pipeline.py`.
- **Kill-ALL + спавн (PowerShell)**: `backend/tests/sandbox/phenomenology/test_memory_fixation.py`, `backend/tests/sandbox/phenomenology/test_directive_obedience_pipeline.py`.
- **Kill/рестарт сервера по сценарию**: `backend/tests/sandbox/SUPERBOX/scenarios/d61_llm_outage_doctrine_test.py` (kill×3/restart×3); `backend/tests/micro/test_llm_resilience_v1.py` (прямые вызовы `server_lifecycle.restart_llama_server/start_llama_server` — реальные спавны в T-тестах, стр. 496–593).
- **Мёртвый импорт**: `backend/tests/sandbox/micro/test_run_turn_e2e.py` (стр. 24) импортирует `from app.main import _kill_llama_server, _restart_llama_server` — **таких функций в `app/main.py` больше нет** (проверено grep по определениям) → тест упадёт ImportError'ом при запуске. **[ФАКТ]**
- **Юнит-тесты уборщика (безопасны)**: `backend/tests/sandbox/micro/test_ghost_reaper.py`.
- **Общие файловые ресурсы**: все sandbox-сценарии пишут отчёты в общий `reports/`; gameplay-harness снапшотит/восстанавливает каталоги; IPT изолирует `saves_dir` во temp. Плюс общий `backend/logs/llama_server_stderr.log` — в него пишут все спавнеры (append) и его же читает диагностика краша. **[ФАКТ]**

### 1.10 Предыдущая реализация harness-owned llama-server и результаты её проверок

**[ФАКТ]** В кодовой базе уже есть два прецедента «harness владеет llama-server»:

1. **IPT-шапка (S4 + K3 + K5)** — это и есть текущая harness-owned реализация: «каждый harness сам поднимает сервер и сам его убивает». Результаты проверок:
   - прогоны зафиксированы: `reports/ipt_s314_final.txt`, `reports/ipt_s316_final.txt` (итог 49 passed / 0 failed, SPARE/kill-счётчики, корректный atexit-kill **в одиночном режиме**);
   - `reports/ue_fix3_ipt.txt`, `reports/ue_fix3_ipt2.txt`, `reports/preflight_ipt.txt`, `reports/preflight_ipt2.txt`;
   - юнит-гейт уборщика: `backend/tests/sandbox/micro/test_ghost_reaper.py` (зелёный на моках).
   - **Вывод по проверкам: механизм верифицирован только в одиночном режиме. Кросс-процессные сценарии (два тестовых процесса, IPT рядом с pytest, игра рядом с тестами) тестами не покрыты** — это и есть дыра, в которой живут конфликты §2. **[ФАКТ по составу артефактов]**
2. **`scripts/det_holder.py` + S4 — «тёплый держатель»** (прототип постоянного хоста): спавн сервера и `sleep(7200)`, чтобы corpus-прогоны REUSE-или инстанс; явная семантика «REUSE — identity NOT verified» в `[DET-ENV]`-отпечатке (`llm_server_manager._llama_env_fingerprint`). Результаты проверок: артефакты `reports/det_m2_holder.txt` (**пуст**), `reports/det_m2_holder_err.txt` (только SyntaxWarning), замеры `reports/det_m2_a.txt`/`reports/det_m2_b.txt` (UTF-16 логи AB-прогонов). Teardown держателя — только вручную. **[ФАКТ]** То есть идея постоянного хоста уже проверялась руками и показала жизнеспособность REUSE-паттерна, но не получила автоматизации, ownership-модели и тестов.

---

## 2. Установленная причина конфликтов

### 2.1 Корневая причина (формулировка)

**[ФАКТ — сводка по коду]** Управляющий контур (кто запускает/останавливает llama-server) фрагментирован между ≥8 механизмами (§1.1–1.2) с **тремя несовместимыми моделями владения**:

| Модель владения | Механизмы | Чего она не видит |
|---|---|---|
| «Я породил Popen» | K1, K3 (atexit-kill своих детей) | что сервером уже пользуются другие процессы по HTTP |
| «Я владею портом» | K2 (kill владельца порта) | кто именно на порту: сервер игры или теста — убивается порт, не владелец |
| «Процесс — сирота репозитория» | K5 (ghost_reaper), K4/K6/K8 (kill по имени) | живых HTTP-клиентов; «сирота» определяется по мёртвой цепочке **предков**, а не по отсутствию пользователей |

Использование же сервера — кооперативное: любой процесс, прочитавший `settings.llama_cpp_server_url`, шлёт HTTP-запросы, нигде не регистрируясь. **Разрыв между «владением по родству/порту/сигнатуре» и «использованием по HTTP» и есть корень взаимного разрушения.**

### 2.2 Почему именно IPT роняет другие тесты (механизмы, все подтверждены кодом)

- **Сценарий A — atexit-kill переиспользованного сервера.** IPT стартует, health молчит (сервер ещё грузится ИЛИ его нет) → IPT спавнит сервер (S4). Параллельно запущенный pytest-процесс B находит сервер по health и спокойно им пользуется, ничего не регистрируя. IPT завершает работу → atexit убивает «своего» ребёнка (K3) → процесс B остаётся без LLM посреди теста. Симптом: «повторный прогон теста падает, потому что IPT закончился». **[ФАКТ — механизм; на реальном прогоне atexit-kill виден в `reports/ipt_s316_final.txt`]**
- **Сценарий B — KILLER_SPIRIT убивает «призрака», которым пользуются.** Сервер, поднятый процессом, который уже завершился (ручной спавн S7, упавший pytest, ланчер без cleanup — долг TZ-GHOST-1, задокументированный в шапке IPT), активно используется живыми тестами. При запуске IPT уборщик K5 видит: сигнатура ✓, «наш» ✓, живых предков нет → сирота → `kill()`. Живые HTTP-клиенты не проверяются вообще. **[ФАКТ — механизм по коду `ghost_reaper.py`; наблюдённый эпизод — §2.4]**
- **Сценарий C — health-only гонка дублей (инцидент 2026-08-30).** S4 проверяет только health: пока другой процесс грузит модель (30–60 с, health молчит), IPT спавнит второй llama-server на тот же порт. Дубль либо умирает на bind (IPT при этом «успешно» дождётся health первого и будет считать сервер своим), либо создаёт окно двойной загрузки → VRAM 96% → 503 на все NARRATIVE (точная формулировка инцидента — в `server_lifecycle.py`, стр. 342–354). Прод-пути этот лок получили; тестовый путь S4 — нет. **[ФАКТ]**
- **Сценарий D — штатное разрушение внутри «владеющих» тестов.** phenomenology-тесты (K6) и d61-доктрина (K7) убивают/рестартят сервер глобально; любой параллельный процесс теряет LLM. **[ФАКТ]**
- **Сценарий E — встречное разрушение «игра ↔ тесты».** Старт игры безусловно делает `taskkill /F /IM llama-server.exe` (K4) — тестовый сервер умирает. Обратно: если игра была закрыта некорректно (ланчер не убил детей — исходный мотив TZ-GHOST-1), следующий запуск IPT убивает её сервер и backend как «призраков». Оба направления — by design сегодняшнего кода. **[ФАКТ]**
- **Сценарий F — мёртвые импорты ломают сбор тестов.** `test_run_turn_e2e.py` импортирует удалённые `app.main._kill_llama_server/_restart_llama_server` → ImportError при запуске/сборе. **[ФАКТ]**

### 2.3 Что причиной НЕ является (проверено, чтобы не чинить не то)

- **Одновременные HTTP-запросы к GPU сами по себе сервер не роняют**: llama-server — многопоточный HTTP-сервер, запросы при одном слоте выстраиваются в его внутреннюю очередь; внутри Python-процесса сериализацию держат `asyncio.Semaphore(1)`/`ThreadPoolExecutor(max_workers=1)`. Параллелизм проявляется как **деградация времени ответа** (а `llama_cpp_timeout_sec = 30` превращает деградацию в таймаут-фейлы тестов) — это отдельный, «мягкий» класс конфликтов. **[ФАКТ — сериализация в коде; поведение очереди llama-server при -np=1 — знание о llama.cpp, подлежит подтверждению на используемой сборке — §5.4]** **[ПРЕДПОЛОЖЕНИЕ]**
- **Недостаток VRAM под одну модель**: одна копия Hermes-3-8B Q4_K_M в 8 ГБ помещается (проектный бюджет §1.5). VRAM-аварии в архиве привязаны к **двойному спавну** (инцидент 2026-08-30), а не к конкурентным запросам. **[ФАКТ по документированному инциденту]**

### 2.4 Статус доказательности

| Утверждение | Статус |
|---|---|
| Существование и поведение механизмов S1–S9, K1–K8 | **ФАКТ** (код + артефакты) |
| Инцидент 2026-08-30 (дубль, VRAM 96%, 503) | **ФАКТ как задокументированный инцидент** (комментарий в `server_lifecycle.py`); независимого лога в снапшоте не искали |
| Сценарии A, C, D, E, F как **механизмы** | **ФАКТ** (кода достаточно для воспроизведения) |
| Конкретный наблюдённый эпизод «IPT убил сервер живого pytest» | **ПРЕДПОЛОЖЕНИЕ** — в снапшоте нет лога с таким эпизодом; требуется воспроизведение по регресс-тесту §7 (этап 2) |
| KILLER_SPIRIT щадит сервер живого родителя | **ФАКТ** (`reports/ipt_s316_final.txt`: SPARE «дерево текущего процесса») |

---

## 3. Сравнение архитектурных вариантов

Критерии — из ТЗ. Оценки: **[ФАКТ]** опирается на код; **[ОЦЕНКА]** — инженерное суждение.

| Критерий | A. LLMRuntimeManager в каждом процессе + межпроцессный лок | B. Постоянный локальный LLM Host (брокер) | C. llama.cpp внутри Python (без HTTP-сервера) |
|---|---|---|---|
| Сложность реализации | Низкая: единый модуль лока+спавна, делегирование всех спавнеров | Средняя: новый процесс-супервизор + SDK, но без проксирования данных (control-plane only) | Формально низкая (библиотека `llama-cpp-python`), фактически высокая: замена всего серверного стека |
| Совместимость с ModelRouter | Полная: ModelRouter не меняется (HTTP-провайдер остаётся) | Полная: endpoint тот же 8181; меняется только «кто спавнит» | **Ломается**: провайдер должен стать in-process; контракт `llama_cpp_server_url`, `/abort`, grammar, стрим — всё переизобретать |
| Совместимость с build_game_loop | Полная (build_game_loop только инициализирует роутер) | Полная | Требует ветвления провайдера по окружению |
| Несколько Python-процессов | Лок решает только spawn/kill; **очереди и приоритетов между процессами нет**; деградация latency при совместном использовании — на совести llama-server | Да: единый владелец, admission/очередь на брокере, идентификация клиентов | **Нет**: каждая модель в каждом процессе — своя копия весов |
| Жизненный цикл | Сложный: каждый процесс должен корректно играть роль владельца (сегодняшние баги — именно здесь) | Простой: один супервизор с lease/heartbeat, idle-stop, watchdog | Н/п — жизненный цикл привязан к процессу-клиенту (тест упал — модель «умерла» с ним) |
| Безопасность параллельных тестов | Средняя: ликвидирует дубли и kill-по-имени, но atexit-семантика «последний выключает свет» остаётся ручной | Высокая: kill по lease, сирот нет по построению | Низкая |
| RAM/VRAM | 1 инстанс (ОК) | 1 инстанс + ~30–60 МБ на брокер **[ОЦЕНКА]** | N инстансов по ~4.6 ГБ — **невозможно на 8 ГБ**; либо перезагрузка весов на каждый процесс (минуты) |
| Устойчивость к аварии | Средняя: кто восстановит сервер, если владелец умер? (сегодня: никто — ждём IPT) | Высокая: watchdog брокера перезапускает сервер независимо от клиентов | Низкая: краш процесса = краш модели |
| Удобство разработчика | Среднее: по-прежнему «каждый сам себе ланчер» | Высокое: `ensure_llm()` из одной строки в любой точке; ручной запуск не нужен | Низкое для текущего стека |

**[ФАКТ-аргументы против C]**: бюджет VRAM §5 (одна копия — предел); провайдер и роутер построены вокруг HTTP-контракта llama-server (`/v1/chat/completions`, `/completion`, `/abort`, grammar, стрим) — `llama_cpp_provider.py` ~700 строк; отказ от llama-server ломает заодно DET-инфраструктуру (`[DET-ENV]`-отпечатки, серверные A/B `s371_3_*`).

**Рекомендация: B**, причём поэтапно через A: этапы 1–2 плана (§7) фактически реализуют «A с правильным ownership-контрактом» и уже сами по себе устраняют классы сценариев A/C/D/E/F §2.2; этап 3 достраивает брокера там, где A принципиально недостаточен (кросс-процессная очередь, watchdog, lease).

### 3.1 Почему «обычная очередь внутри одного Python-процесса недостаточна» (подтверждение ТЗ)

**[ФАКТ]** Сегодняшние очереди — `asyncio.Semaphore(1)` и D62-очередь `ModelRouter`, `DialogueQueue`/`ThreadPoolExecutor(1)` в `TaskScheduler` — живут внутри одного процесса и защищают VRAM **внутри** процесса. Между процессами (IPT vs pytest vs игра) единственная «очередь» — внутренний слот llama-server: без приоритетов, без отмены, без наблюдаемости; а управляющий контур (spawn/kill) межпроцессной координации не имеет вовсе (§2.1). Требованию удовлетворяет только уровень брокера (B) либо распределённый лок с приоритетами (A+, что и есть B с меньшей функциональностью).

---

## 4. Рекомендуемая архитектура: LLM Host (брокер) + клиентский SDK

### 4.1 Схема взаимодействия компонентов

```text
                         ┌──────────────────────────────────────────────┐
                         │  LLM Host (брокер, фоновый процесс)          │
                         │  backend/app/services/llm/runtime/host.py    │
                         │  HTTP 127.0.0.1:8182 (management-only)       │
                         │  ── spawn-lock: bind :8182 = атомарный захват│
                         │  ── leases/heartbeat, реестр клиентов        │
                         │  ── watchdog: /health llama-server, restart  │
                         │  ── admission: слоты/приоритеты (опция)      │
                         └──────┬───────────────────────────┬───────────┘
              ensure/status/    │                           │  Popen/terminate
              release/cancel    │                           │  (каноническая команда из settings)
        ┌───────────────────────┴───────┐          ┌────────┴─────────┐
        │  Клиенты (тонкий SDK)         │          │   llama-server   │
        │  llm/runtime/client.py        │          │   127.0.0.1:8181 │
        │  ensure_llm() -> url          │── HTTP ──▶  (единственный    │
        │  pytest fixtures / IPT /      │  данные   инстанс модели)   │
        │  harnesses / build_game_loop /│  напрямую                    │
        │  game_launcher / main.py      │          └────────┬─────────┘
        └───────────────────────────────┘                   │ /metrics
                                     наблюдаемость ◀────────┘
```

Принципиальные решения:
1. **Control-plane и data-plane разделены.** Брокер управляет жизненным циклом и владением; генерация идёт напрямую клиент→llama-server (без прокси — без лишней latency и единой точки отказа трафика). Кросс-процессная очередь реализуется выдачей **слот-токенов** брокером (семафор на `-np` слотов), а не проксированием запросов. **[ОЦЕНКА — дизайн]**
2. **Брокер — единственный, кто делает Popen/kill llama-server.** Все сегодняшние спавнеры (S1–S6) становятся клиентами `ensure_llm()`. Kill — только по PID, записанному брокером (никаких kill по имени/порту).
3. **Единственный источник конфигурации — `app.core.config.settings`** (та же каноническая spawn-команда, что сегодня в `server_lifecycle._spawn_llama_server`; брокер импортирует её, а не копирует). Второй источник правды о порте (`runtime_ports`) выводится из эксплуатации (этап 6).
4. Брокер переживает клиентов: стартует отсоединённым (`DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP` на Windows), пишет pid-файл и лог; останавливается по `--stop`, по отсутствию lease и idle-таймауту, или вручную.

### 4.2 Дизайн диспетчера (обязательный список из ТЗ)

| Элемент | Решение |
|---|---|
| **Единая очередь запросов** | На брокере — admission-семафор на N слотов (N = измеренное `-np`, стартово 1). Клиент запрашивает токен (`POST /acquire`), получает его с учётом класса, выполняет запрос напрямую в llama-server, возвращает токен (`POST /release`). Данные через брокер не идут. |
| **FIFO и приоритеты** | Внутри класса — FIFO по времени прибытия (seq), между классами — canonical раньше ambient (перенос семантики D62 `router.py` на кросс-процессный уровень: canonical 90 с бюджет ожидания, ambient cap 8, дедлайн 300 с, DROP с причиной). Константы — те же CALIBRATION-имена, чтобы не плодить второй источник настроек. |
| **Идентификация тестов и клиентов** | SDK при `ensure_llm()` передаёт `client_id = os.getpid()` + `label` (pytest: `nodeid`; IPT: `"IPT"`; игра: `"game"`; harness: имя сценария) из переменной окружения `ENIGMA_LLM_CLIENT` с фолбэком. Реестр клиентов с heartbeat виден в `GET /status`. |
| **Таймауты** | Ожидание слота: canonical 90 с / ambient 300 с (как D62). Генерация: клиентский `llama_cpp_timeout_sec=30` остаётся у провайдера; wall-time потолок 120 с с `/abort` + форфейтом токена (epoch-защита от позднего результата — как `_wall_time_watchdog`). |
| **Отмена запросов** | `POST /cancel/{req_id}` → брокер помечает токен отменённым и шлёт `/abort` в llama-server (прецеденты: `LlamaCppProvider.abort_generation`, `_abort_generation` роутера). Отмена ожидания = dead-токен (как `_QueueWaiter.dead`). |
| **Поведение при падении сервера** | Watchdog брокера опрашивает `/health` каждые 2 с. Падение → рестарт по канонической команде с backoff (2/5/10 с, максимум 3 попытки) → клиенты получают `503 {reason, retry_after}`; proof-failure backoff пула сбрасывается только после подтверждённого `/health 200` (сохранение контракта `pool_reset_backoff`). После исчерпания попыток — статус `degraded`, тики/тесты получают громкий отказ (семантика D61 сохраняется). |
| **Повторное подключение** | SDK без состояния: любой `ensure_llm()`/запрос после аварии проходит `ensure` заново; повторный `ensure` идемпотентен (критерий 2 ТЗ). Ретраи запросов — существующие `max_retries` провайдера, без изменений. |
| **Защита от двух одновременных запусков** | (1) Брокер: bind 127.0.0.1:8182 — атомарный межпроцессный мьютекс («кто занял порт, тот и хост»); второй запускающийся брокер становится клиентом первого. (2) llama-server спавнится только брокером и только при свободном порту 8181 (проба bind + health, как в `acquire_llama_server_lock`). Окно гонки «проба→Popen» закрывается тем, что спавнит один процесс (брокер), а не каждый клиент. |
| **Корректное завершение процессов** | Стоп llama-server: `terminate()` → 5 с → `kill()` по записанному PID + проверка имени процесса (перенос проверки из `_stop_llama_server`). Стоп брокера: сначала дренаж активных токенов, потом сервер, потом pid-файл удаляется. Windows: `CREATE_NEW_PROCESS_GROUP` у брокера, дети в его job-объекте (psutil `children(recursive=True)` как фолбэк). |
| **Владение сервером, lease/heartbeat** | Сервером владеет **брокер**, не клиенты. Клиент держит lease (TTL 30 с, heartbeat фоновым потоком SDK); lease истёк → клиент исключается из реестра. Сервер останавливается брокером только когда: нет ни одного живого lease И прошло `idle_timeout` (стартово 10 мин **[ОЦЕНКА, см. §9-В2]**), И режим не `pinned` (игра пинает сервер на время сессии). Никаких atexit-kill серверов клиентами — atexit клиента делает только `release_lease()`. Ghost-сценарии исчезают по построению: «сирота» невозможна, потому что владелец (брокер) бессмертен относительно клиентов. |

**Совместимость**: ModelRouter, ModelPool, провайдеры, D62/D61, replay — не меняются (меняется только то, кто поднимает процесс, и где клиенты берут гарантию его существования). Это ключ к выполнению запрета «не создавать дублирующий ModelRouter и вторую конфигурацию».

---

## 5. Аппаратные ограничения и стартовая конфигурация

Исходные данные ТЗ: RTX 3070 Ti 8 ГБ, i7-9700F (8C/8T, без iGPU — «F»), 16 ГБ RAM, локальная GGUF-модель. Совпадает с конфигом проекта. **[ФАКТ]**

### 5.1 VRAM-бюджет (стартовая конфигурация)

**[ОЦЕНКА, на основе проектных чисел конфига §1.5]**

| Статья | Оценка |
|---|---|
| Hermes-3-Llama-3.1-8B Q4_K_M, все 32 слоя (`-ngl 99`) | ~4600 МБ |
| KV-cache ctx=16384 (текущий `ctx_size`), flash-attn | ~1000–1200 МБ (проект оценивал 8192 в ~600 МБ) |
| CUDA-контекст + десктоп (у 3070 Ti дисплей на этой же карте) | ~500–800 МБ |
| **Итого** | **~6.1–6.6 ГБ из 8.0** |

Выводы:
- **Второй инстанс той же модели невозможен** (+4.6 ГБ) — запрет ТЗ «не поднимать несколько копий ради параллельного тестирования» подтверждается и бюджетом. Параллелизм — только слоты одного сервера.
- Целевой потолок при замерах: **≤ 7200 МБ занятой VRAM** (90%); регистрация OOM — по `llama_server_stderr.log`.
- Стартовая spawn-команда (каноническая, отличается от текущей S3 только явным `--parallel` и фиксацией `--flash-attn` после проверки сборки):

```text
llama-server.exe -m "Models LLM/Hermes-3-Llama-3.1-8B.Q4_K_M.gguf" \
  --host 127.0.0.1 --port 8181 \
  -ngl 99 -c 16384 -t 8 --jinja \
  --flash-attn        ← проверить поддержку в используемой сборке (шапка конфига требует, спавнер не передаёт)
  --parallel 1        ← стартово 1; подъём только по §5.3
```

RAM (16 ГБ): веса mmap ~4.6–4.9 ГБ + backend+фронтенд+тесты ~2–3 ГБ + ОС — помещается; следить, чтобы `det_holder`/вторые серверы не плодились (после внедрения брокера — исключены by design).

### 5.2 Параллельные слоты: что говорит конфигурация

`--parallel N` в llama.cpp делит `-c` между слотами: `-c 16384 --parallel 2` → по 8192 на слот (совпадает с проектными бюджетами агентов: dm 3072, npc 1536 и т.д. — `config.get_context_for_agent`). KV-cache суммарно растёт слабо; основная плата — возможная деградация per-request latency при cont-batching. Поведение очереди слотов и фактические флаги сборки — **подтвердить измерением (§5.4)**. **[ОЦЕНКА + знание llama.cpp]**

### 5.3 Методика экспериментального определения числа слотов

Новый скрипт `scripts/llm_slot_bench.py` (план, этап 4):
1. Фиксированная смешанная нагрузка, отражающая игру: 30 запросов — 60% «DM-нарратив» (~2500 ток. промпт / ~220 ток. ответ), 30% «NPC-диалог» (~1000/150), 10% «memory-суммаризация» (~1500/300); режимы 1 и 4 параллельных клиента.
2. Лестница `--parallel ∈ {1, 2, 4}` при фиксированном `-c 16384`; между прогонами полный рестарт сервера.
3. Метрики: p50/p95 latency на класс запроса, суммарный tokens/s (`/metrics` llama-server, если сборка экспортирует; иначе замер по клиенту), пиковая VRAM (`nvidia-smi --query-gpu=memory.used`), факты OOM в stderr-логе.
4. Критерий выбора: максимум N, при котором (а) VRAM ≤ 7200 МБ, (б) p95 canonical ≤ 1.5× базлайна N=1, (в) ноль OOM. Пока измерений нет — **N=1** (очередь, не параллелизм).
5. Результат фиксируется в `config/gpu_profile.json` рядом с `n_gpu_layers` (например, `parallel_slots: N`) — один источник правды, без env-джунглей.

**Не увеличивать параллелизм без измерений — ограничение ТЗ соблюдено по построению (старт N=1).**

### 5.4 Пункты верификации по железу/сборке (отдельно помечены как неподтверждённые)

- поддержка `--flash-attn`, `/metrics`, `--parallel` в используемой сборке llama-server (сборка в `Models LLM/` в снапшот не входит — gitignored);
- фактическое время холодной загрузки модели (проект закладывает до 90–120 с: `model_load_timeout_sec=120`);
- фактический расход KV при ctx=16384.

---

## 6. Интеграция: один механизм для всех потребителей

Все потребители переходят на один вход — SDK `ensure_llm()` (этапы 3–5 §7):

| Потребитель | Сегодня | После |
|---|---|---|
| Обычные pytest-тесты | моки в conftest (сервер не нужен); LLM-live тесты — шапка IPT с atexit-kill | фикстура `llm_runtime` (session-scoped): `url = ensure_llm(label="pytest:<nodeid>")`; atexit → `release_lease()`; сервер переживает тест |
| IPT | спавн S4 + двойной reap + atexit-kill | шапка → `ensure_llm(label="IPT")`; KILLER_SPIRIT сохраняется **только** для уборки осиротевших связок игры (uvicorn+llama с мёртвыми предками и нулём активных соединений на 8181); atexit-kill удалён |
| Экспериментальные harnesses (SUPERBOX, drift_laboratory, chronicle probes) | каждый со своей шапкой | тот же `ensure_llm()`; kill/restart-сценарии (d61) — через API брокера (`/restart`), а не самовольный kill |
| `build_game_loop` | `initialize_router()` — роутеру нужен живой URL | подпись без изменений; гарантию даёт клиент: `build_game_loop` вызывает `ensure_llm(label="gameloop")` (неблокирующе, как сегодня `_background_llm_startup`) |
| Запущенная игра (`game_launcher`) | `_kill_zombies()` (kill-ALL) + `_ensure_llm_running()` (свой Popen) | `_kill_zombies()` сокращается до уборки **своих** pid-файлов; старт → `ensure_llm(label="game", pinned=True)`; экран загрузки читает статус брокера |
| Backend (`main.py` lifespan) | `_background_llm_startup` (свой спавн) + atexit | `_background_llm_startup` → `ensure_llm(label="backend")`; shutdown → `release_lease()` (не kill) |
| Ручные инструменты (`det_holder`, `spawn_prod_llama`, `start_dev.ps1`) | ручные спавны | выводятся из эксплуатации; заменяются `python -m app.services.llm.runtime.host --stop|--status` и pinned-режимом брокера |

Запреты из ТЗ соблюдаются: конкурирующих механизмов управления больше нет (все — клиенты одного брокера), второй конфигурации модели нет (settings — SSOT, этап 6 уничтожает runtime_ports-дубль порта).

---

## Статус реализации (обновлено 2026-11-07)

| Этап | Статус | Коммиты | Impact Log |
|---|---|---|---|
| 0 | ✅ ЗАВЕРШЕН | 01a18c1f/88dab765/be03ac85/28540912 | LLM_RUNTIME_ЭТАП0_IMPACT.md |
| 1 | ✅ ЗАВЕРШЕН | fb738628 | LLM_RUNTIME_ЭТАП1_IMPACT.md |
| 2 | ✅ ЗАВЕРШЕН | 351a5e02 | LLM_RUNTIME_ЭТАП2_IMPACT.md |
| 3 | ✅ ЗАВЕРШЕН | c01799ca+0ed3d8aa+95fe4ec2+53f7c2d4+19664c9a+c560623c+3281ead3+96fd9047 | LLM_RUNTIME_ЭТАП3_IMPACT.md |
| 4 | ✅ ЗАВЕРШЕН (30/30) | S417: baeb2548→246eed16; S418: 9c85d436→36563594 | — |
| 5 | ⏳ PENDING | — | — |
| 6 | ⏳ PENDING | — | — |

**Milestone (Этапы 0-3):** Two-client crash isolation test S1-S8 PASS. IPT migrated to Host broker SDK (Step 6A). silent_subprocess_kwargs SSOT. IPT 53/1 (vs baseline 52/2).

**Этап 4 (S417):** 14 consumers migrated. 16 remaining (batches 4.1.6-4.1.13). 2 deferred (d61 + client.py).

## 7. План внедрения (малые независимые этапы)

Каждый этап: файлы → изменения → что не трогаем → тесты до/после → критерий → откат. Порядок — по убыванию разрушительности: сначала перестаём убивать, потом строим брокера.

### Этап 0. Кровоостанавливающий (только удаление разрушительных практик)
- **Файлы**: `backend/tests/sandbox/phenomenology/test_memory_fixation.py`, `test_directive_obedience_pipeline.py`; `game_launcher.py::_kill_zombies`; `backend/start_dev.ps1`; `backend/tests/sandbox/micro/test_run_turn_e2e.py`.
- **Изменения**: убрать `Stop-Process -Name llama-server` и `taskkill /F /IM llama-server.exe`; kill только по PID с проверкой имени/пути (перенос семантики `_stop_llama_server`); phenomenology-тесты переходят на `scripts.llm_server_manager`; `test_run_turn_e2e` — заменить мёртвый импорт `app.main._kill_*` на `server_lifecycle.restart_llama_server/kill_llama_server`.
- **Не трогаем**: IPT-шапку, server_lifecycle, ModelRouter.
- **Тесты до/после**: до — зафиксировать падение пары «phenomenology-тест + живой внешний сервер» (воспроизведение сценария D); после — пара проходит, внешний сервер жив.
- **Критерий завершения**: ни один тест/скрипт в репозитории не убивает процессы по имени/порту без PID-проверки.
- **Откат**: git revert этапа (изменения локальны).

### Этап 1. Единый spawn-lock для тестового пути
- **Файлы**: `scripts/llm_server_manager.py` (делегирование в `acquire_llama_server_lock` + канонический спавн из `server_lifecycle`); опционально вынести лок в `backend/app/services/llm/runtime/spawn_lock.py`.
- **Изменения**: health-only проверка S4 заменяется двухлинейной (health + bind-probe); флаги S4 выравниваются с S3 (`--host 127.0.0.1`, `effective_gpu_layers`).
- **Не трогаем**: публичный контракт `server_lifecycle.py`, логику IPT, всех потребителей импорта (`from scripts.llm_server_manager import ...` сохраняется).
- **Тесты**: юнит «два процесса стартуют одновременно → ровно один Popen» (моки + реальный парный прогон); регресс инцидента 2026-08-30 на уровне S4.
- **Критерий**: повторение сценария `reports/ipt_*` + параллельный прогон IPT и pytest без дублей (проверка по логу `[DET-ENV]` и по числу процессов).
- **Откат**: revert (модуль сохраняет сигнатуры `start/kill_llama_server`).

### Этап 2. Ownership-контракт «владение = использование»
- **Файлы**: `scripts/llm_server_manager.py::kill_llama_server` (atexit-kill только если нет живых HTTP-клиентов), `scripts/ghost_reaper.py` (признак «есть ESTABLISHED-соединения на :8181 → щадить», psutil `net_connections`), все ~30 шапок — без правки (импортируют те же функции).
- **Изменения**: atexit не убивает сервер, которым пользуются; reaper щадит «сироту с клиентами», помечая его `orphan-but-in-use` в отчёте.
- **Не трогаем**: вердикты против uvicorn-призраков игры (TZ-GHOST-1 сохраняется — связка backend+llama без клиентов и с мёртвыми предками по-прежнему убирается).
- **Тесты**: расширение `backend/tests/sandbox/micro/test_ghost_reaper.py` (кейс «сирота + живой клиент → spare»); парный регресс-тест `backend/tests/runtime/test_llm_parallel_two_processes.py` (новый): процесс A спавнит, процесс B пользуется, A завершается → сервер жив, B дорабатывает.
- **Критерий**: критерии 2, 5, 6 ТЗ выполняются уже без брокера.
- **Откат**: revert; поведение возвращается к текущему (известные риски возвращаются — этап обязателен).

### Этап 3. LLM Host MVP (control-plane)
- **Файлы (новые)**: `backend/app/services/llm/runtime/__init__.py`, `host.py` (FastAPI: `/ensure`, `/status`, `/release`, `/health`), `client.py` (`ensure_llm(label, pinned)`, heartbeat-поток, `release_lease`), pid-файл и лог под `backend/logs/llm_host/`. **Потребители первой волны**: `backend/tests/conftest.py` (фикстура `llm_runtime`), `backend/tests/IPT.py` (шапка), `chronicle_weave_probe.py`, `chronicle_decompose_probe.py`, `test_gc11_relationship_causality.py`.
- **Изменения**: перечисленные потребители переходят с `llm_server_manager` на SDK; брокер спавнит сервер канонической командой S3 (импорт из `server_lifecycle`, без копирования команды).
- **Не трогаем**: ModelRouter/пул/провайдеры, game_launcher, main.py (этап 5), D62-очередь.
- **Тесты до**: регресс этапа 2; **после**: `backend/tests/runtime/test_host_single_instance.py` (двойной запуск брокера → один процесс), `backend/tests/runtime/test_host_survives_client_crash.py` (kill клиента → сервер жив), `backend/tests/runtime/test_ipt_no_kill.py` (IPT при живом внешнем сервере не завершает его).
- **Критерий**: два независимых pytest-процесса работают с одной моделью через брокера; после аварийного завершения любого из них сервер и второй процесс не страдают (критерии 1–3, 5, 6 ТЗ).
- **Откат**: env `ENIGMA_LLM_HOST=off` → SDK падает обратно в `llm_server_manager` (этап 1); код брокера изолирован в новом пакете.

### Этап 4. Очередь, приоритеты, отмена, watchdog, слоты
- **Файлы**: `runtime/host.py` (+`/acquire`, `/release-token`, `/cancel`, `/restart`), `runtime/queue.py` (перенос D62-констант), `scripts/llm_slot_bench.py` (§5.3), `config/gpu_profile.json` (+`parallel_slots`).
- **Не трогаем**: D62-очередь внутри роутера (продолжает работать для внутрипроцессных вызовов; брокерская — надстройка между процессами).
- **Тесты**: `backend/tests/runtime/test_queue_cross_process_fifo.py` (два процесса, приоритет canonical над ambient), `backend/tests/runtime/test_watchdog_restart.py` (kill -9 llama-server → восстановление в пределах бюджета), `backend/tests/runtime/test_cancel_propagates_abort.py`.
- **Критерий**: критерий 4 ТЗ (конкурирующие запросы обслуживаются общей очередью) и 7 (автовосстановление после аварии сервера); число слотов выбрано по §5.3 и записано в gpu_profile.json.
- **Откат**: слоты → 1; брокерская очередь off (запросы идут напрямую, как в этапе 3).

### Этап 5. Интеграция игры и backend
- **Файлы**: `game_launcher.py` (`_kill_zombies` → уборка только своих pid-файлов; `_ensure_llm_running` → `ensure_llm(label="game", pinned=True)`), `backend/app/main.py` (`_background_llm_startup` → SDK; shutdown → release), `backend/app/services/readiness.py` (статус из брокера), `d61_llm_outage_doctrine_test.py` (kill/restart через `/restart` брокера), обновление `docs/РЕЖИМ РАБОТЫ.md`.
- **Не трогаем**: игровой замысел, D61-доктрину пауз (только транспорт рестарта).
- **Тесты**: e2e «старт игры при уже работающем тестовом сервере → игра переиспользует, тест не замечает»; повторный прогон d61 (G0–G8) против брокера.
- **Критерий**: критерии 8 и 9 ТЗ.
- **Откат**: точечный revert (launcher/main), брокер продолжает обслуживать тесты.

### Этап 6. SSOT порта и чистка легаси
- **Файлы**: `backend/tests/test_llm.py` (на `settings.llama_cpp_port`), `backend/app/core/runtime_config.py` + `data/runtime_ports.py` (deprecation: `get_llm_url` → settings), `cognition/direct_llm_client.py` (URL из settings), удаление дублей `_start_llama_server` в system-тестах (→ SDK), удаление/архивация `logs/spawn_prod_llama.py`, `det_holder.py`, `start_dev.ps1` (заменены брокером), маркировка LLM-live тестов (pytest-маркер `llm_live`).
- **Критерий**: grep по репозиторию даёт единственный источник `8181` (`settings`) и ни одного `taskkill /IM llama-server` / `Stop-Process -Name llama-server`.
- **Откат**: revert по файлам независимо.

### Зависимости этапов
0 → 1 → 2 → (3 → 4) → 5 → 6; этапы 0–2 самодостаточны и уже дают 5 из 9 критериев на прежней архитектуре.

---

## 8. Критерии конечного результата и план испытаний

| № | Критерий ТЗ | Проверка | Этап |
|---|---|---|---|
| 1 | Тест сам обеспечивает запуск LLM | `pytest backend/tests/runtime/test_ensure_starts.py` (фикстура `llm_runtime` поднимает сервер на пустом окружении) | 3 |
| 2 | Повторный запуск использует работающий сервер | второй `ensure_llm()` в новом процессе → `reason=reuse`, время < 1 с (без загрузки модели) | 1→3 |
| 3 | Два независимых тестовых процесса — одна модель | `backend/tests/runtime/test_llm_parallel_two_processes.py` (этап 2), затем через брокера (этап 3) | 2–3 |
| 4 | Конкурирующие запросы — общая очередь | `test_queue_cross_process_fifo.py`; llm_slot_bench фиксирует N слотов | 4 |
| 5 | IPT не завершает и не повреждает чужие процессы | прогон IPT при живом внешнем сервере + чужом pytest: сервер жив, чужой тест доведён; `IPT_NO_REAPER` остаётся opt-out | 2–3 |
| 6 | Падение одного теста не роняет сервер и другие тесты | kill теста-клиента посреди генерации → сервер жив, второй клиент не видит ошибок | 3 |
| 7 | Инфраструктура восстанавливает LLM после аварии сервера | kill -9 llama-server → watchdog брокера; `/health` 200 в пределах бюджета; `pool_reset_backoff` вызван | 4 |
| 8 | Игра использует тот же механизм | e2e старт игры (launcher) при работающем брокере: в логе `ensure_llm(label="game")`, процессов llama-server — 1 | 5 |
| 9 | Ручной запуск llama-server не нужен | сценарий «чистая машина → `pytest` LLM-live → зелёный» без ручных действий | 3, 5 |

Регрессионный контур: пара «IPT ∥ pytest», пара «игра ∥ pytest», CI-джоба `invariant-probes` (продолжает работать без LLM), `test_ghost_reaper.py` (расширенный), d61-доктрина (G0–G8).

---

## 9. Открытые вопросы, требующие вердикта Мастера (решения не приняты за пользователя)

- **В1. Судьба KILLER_SPIRIT.** Reaper решает реальную проблему TZ-GHOST-1 (ланчер не убивает детей). Предложение сохраняет его как уборщика «связок без клиентов», но критерий «наши/чужие» (cwd-принадлежность) при установленном брокере можно сузить до pid-файлов. Сузить или оставить — на усмотрение.
- **В2. Idle-таймаут сервера** (через сколько минут без клиентов брокеру гасить llama-server: 10 мин? не гасить вовсе?) — компромисс «VRAM для десктопа vs время холодного старта 30–90 с».
- **В3. Management-порт брокера (8182)** — подтвердить/сменить; разрешить ли брокеру автостарт при загрузке ОС (сервис/задача планировщика) как альтернативу ленивому старту.
- **В4. Судьба `--flash-attn`** — включать ли в каноническую команду после проверки сборки (меняет поведение генерации — за пределами чистой инфраструктуры).
- **В5. Приоритеты «игра > тесты»** — должен ли брокер при конфликте игры и тестового прогона отдавать слот игре (сейчас предложен нейтральный FIFO + canonical/ambient; «игра главнее» — изменение игрового замысла, не решаю).
- **В6. CI**: оставить ubuntu-job без LLM как есть (рекомендую да) или добавить опциональный GPU-runner для LLM-live набора.

---

## 10. Приложение: реестр источников фактов

Код: `backend/app/services/llm/{server_lifecycle,router,provider_manager,llama_cpp_provider,factory,__init__}.py`; `backend/app/core/config.py`; `backend/app/core/runtime_config.py`; `backend/data/runtime_ports.py` (+ `backend/data/runtime_ports.json`); `backend/app/main.py`; `backend/app/api/routes.py`; `backend/app/services/readiness.py`; `backend/app/services/game_loop_builder.py`; `backend/app/services/game_loop/task_scheduler.py`; `backend/app/services/cognition/{direct_llm_client,router_adapter}.py`; `game_launcher.py`; `backend/start_dev.ps1`; `scripts/{llm_server_manager,ghost_reaper,det_holder,s371_3_server_ab_test}.py`; `logs/spawn_prod_llama.py`. Тесты: `backend/tests/{IPT,conftest,test_llm}.py`; `backend/tests/micro/{test_llm_resilience_v1,test_cch8_character_debug_runtime_fields,test_det_instrumentation}.py`; `backend/tests/sandbox/micro/{test_run_turn_e2e,test_ghost_reaper}.py`; `backend/tests/sandbox/system/{test_homeostatic_dialogue_stability,test_epistemology_pipeline}.py`; `backend/tests/sandbox/phenomenology/{test_memory_fixation,test_directive_obedience_pipeline}.py`; `backend/tests/sandbox/SUPERBOX/scenarios/d61_llm_outage_doctrine_test.py` (+18 файлов SUPERBOX с шапкой); `backend/tests/gameplay/harness.py`; `backend/tests/gameplay/test_gc11_relationship_causality.py`; `backend/tests/sandbox/{experiment_runner}.py`; `backend/tests/gameplay/{perturbation_harness}.py`. Конфиги: `config/gpu_profile.json`, `backend/pytest.ini`, `backend/pyproject.toml`, `.github/workflows/{ci,superbox,test}.yml`. Артефакты: `reports/{ipt_s314_final,ipt_s316_final,preflight_ipt2,det_m2_holder,det_m2_holder_err,det_m2_a,d61_llm_outage_doctrine.md}`. Все проверки выполнены чтением файлов снапшота `Enigma-V.0.5.4.5.7_-_4`; ссылки на строки — по этому снапшоту.
