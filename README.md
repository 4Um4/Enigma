# ENIGMA — локальный AI Dungeon Master

Актуализация README: 2026-03-29  
Основано на фактическом коде (`backend/app/*`), актуальном `Now.md`, текущих скриптах запуска и состоянии репозитория.

---

## 1. Что это за проект

Enigma — локальная RPG-система в духе D&D 5e, где:
- игрок пишет действие свободным текстом,
- Python детерминированно считает последствия,
- LLM превращает рассчитанный результат в нарратив.

Это не «чат-бот с фэнтези-обёрткой», а попытка построить симулятор мира с устойчивым состоянием, NPC-поведением и последовательной памятью.

Ключевой принцип (истинный и неизменный):

```text
Игрок пишет действие
        ↓
Python рассчитывает последствия
        ↓
LLM формулирует ответ в художественной форме
        ↓
Состояние мира сохраняется
```

---

## 2. Архитектурные принципы

### 2.1 Python считает — LLM рассказывает
- Проверки, физика, сцена, базовая NPC-психология и обновление состояния делаются в Python.
- LLM получает уже подготовленный контекст и не является источником истины для механики.

### 2.2 SceneState как источник правды
- Состояние сцены, объекты, позиции NPC, эффекты, цель игрока ведутся Python-слоем.
- LLM не пишет в состояние напрямую.

### 2.3 «Нет запрещённых действий», есть последствия
- Sandbox-ветка обрабатывает нестандартные пользовательские действия.
- Невозможное отсекается физическим валидатором, а не «моральной» логикой модели.

### 2.4 Runtime-ядро: `game_loop`, не `orchestrator`
- Исторический `orchestrator` больше не является реальным ядром runtime.
- Текущий центр исполнения: `game_loop.py` + `game_loop_factory.py`.

---

## 3. Текущее состояние проекта (на 2026-03-29)

| Подсистема | Оценка | Комментарий |
|---|---:|---|
| Core runtime (FastAPI + loop) | 85% | Стабильный цикл `run_turn/stream_turn` |
| SceneState / SceneChange | 80% | Изменения объектов и таргетов проходят |
| NPC pipeline | 70% | Рабочая реактивность и расписания |
| Event layer | 60% | Подключён, но campaign-изоляция неполная |
| Memory | 45% | Layered JSONL есть, SQLite/FAISS ещё нет |
| UI/UX | 45% | Рабочий чат + SSE, но не весь planned UI |
| Rules/Combat depth | 35% | Базовые механики есть, полный D&D 5e нет |
| Тестовый контур | 20% | Часть тестов legacy, `pytest` часто не поднят в окружении |

---

## 4. Что уже сделано и подтверждено кодом

### 4.1 Закрытые шаги A/B/C.1
- Фаза A (`A.1`–`A.4`) закрыта:
  - добавлен `ObjectResolver` (`backend/app/services/action/object_resolver.py`),
  - `campaign_id` добавлен в `GameEvent`,
  - событие публикуется из `ActionProcessor`,
  - `PerceptionFilter` встроен в pipeline `game_loop` (шаг `5.5`).
- `B.1` закрыт: `/api/npcs/{campaign_id}` возвращает NPC текущей локации игрока.
- `B.2` закрыт: activity NPC обновляется из schedule по `time_of_day`.
- `C.1` закрыт: prompt NPC берёт activity из `scene_state` как источника правды.

### 4.2 Важные исправления, которые уже не надо чинить повторно
- Старый баг `routes_debug` (`time` без импорта) исправлен.
- `world_state.record_event()` подключён (вызов из `ActionProcessor`).

---

## 5. Реальная runtime-архитектура

### 5.1 Boot chain

```text
start_enigma.bat
  ↓
backend/start_llm.bat
  ↓
backend/start_backend.bat
  ↓
uvicorn app.main:app
  ↓
main.py
  ↓
routes + routes_stream + routes_debug
  ↓
game_loop_factory.game_loop (singleton)
```

### 5.2 Игровой цикл (SSE/REST)

```text
Frontend
  ↓
/api/game/action/stream  (или /api/game/action)
  ↓
GameLoop
  ↓
ActionProcessor (classification + physics + event publish)
  ↓
PythonEngines (sandbox/combat/npc systems/scene updates)
  ↓
RulesAgent
  ↓
NpcAgent
  ↓
DmAgent
  ↓
Ответ + сохранение памяти
```

---

## 6. Ключевые подсистемы

### 6.1 SceneState / SceneChange
- Управление сценой: `backend/app/services/scene_state_manager.py`.
- Атомарные изменения: `backend/app/services/scene_change.py`.
- Объекты, позиции NPC, player target, эффекты — часть scene-контракта.

### 6.2 NPC системы
Активно задействованы в runtime:
- `threat_assessor.py`
- `perception_engine.py`
- `psyche_engine.py`
- `npc_cognition.py`
- `life_engine.py`

Подключённые частично/погранично:
- `perception_filter.py` (подключён в `game_loop`, нужен дальнейший hardening)
- `reaction_priority.py` (есть код и связи, но требует доинтеграции во всех ветках)

### 6.3 Event + World context
- EventBus: `backend/app/services/events/event_bus.py`
- Типы событий: `backend/app/services/events/event_types.py`
- World slice/token-budget: `backend/app/services/simulation/world_state.py`

Текущий риск: события и recent-log глобальные, а не строго изолированные по campaign.

### 6.4 Память (текущая реализация)
- `JsonMemoryStore` + `LayeredMemory` (`backend/app/services/memory.py`)
- Слои: world canon, campaign memory, session memory, npc memory (JSONL)
- Пока нет SQLite+FAISS слоя как production-default.

### 6.5 LLM слой
- Основная модель: Gemma-3-12B Q4_K_M.
- `ModelPool` работает с ограничением `max_loaded=1` (важно для 8 GB VRAM).
- Есть drift fallback-конфигов: в `config.py` указаны пути к некоторым моделям, которых нет локально.

---

## 7. Структура репозитория

```text
Enigma/
├── start_enigma.bat
├── restart_all.bat
├── Now.md
├── Before.md
├── Plan.md
├── backend/
│   ├── start_backend.bat
│   ├── start_llm.bat
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── routes.py
│   │   │   ├── routes_stream.py
│   │   │   └── routes_debug.py
│   │   ├── agents/
│   │   ├── core/
│   │   ├── models/
│   │   └── services/
│   │       ├── game_loop.py
│   │       ├── game_loop_factory.py
│   │       ├── action/
│   │       ├── npc/
│   │       ├── events/
│   │       ├── simulation/
│   │       ├── game/
│   │       ├── llm/
│   │       └── state/
│   ├── data/
│   └── tests/
├── frontend/
│   └── ui/
│       └── index.html
└── Models LLM/
```

---

## 8. Запуск проекта

### 8.1 Рекомендуемый запуск

```bat
start_enigma.bat
```

Скрипт поднимает:
- LLM сервер (`llama-server` на `127.0.0.1:8080`),
- Backend FastAPI (`127.0.0.1:8000`),
- Frontend static server (`127.0.0.1:3000`, если `frontend/ui/index.html` присутствует).

### 8.2 Ручной запуск по частям
1. LLM: `backend/start_llm.bat`
2. Backend: `backend/start_backend.bat`
3. Frontend (если нужно вручную): `python -m http.server 3000 --directory frontend/ui`

### 8.3 Проверка после старта
- UI: `http://127.0.0.1:3000`
- API docs: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/api/health`
- Debug VRAM: `http://127.0.0.1:8000/api/debug/vram`

---

## 9. Требования к окружению

### 9.1 Минимально ожидаемые ресурсы
- CPU: от 4 физических ядер.
- RAM: от 12 GB (рекомендуется 16 GB).
- GPU: RTX 3070 Ti 8 GB (целевой профиль проекта).

### 9.2 Python и зависимости
- Backend-скрипт жёстко проверяет Python 3.11 в `/.venv`.
- Зависимости ставятся из `backend/requirements.txt` при старте backend-скрипта.

Важно: если запускать команды вне `.venv`, можно получить ошибку вида `No module named pytest` даже при наличии `pytest` в `requirements.txt`.

### 9.3 Модели и бинарники
Обязательные артефакты для штатного запуска:
- `Models LLM/llama/llama-server.exe`
- `Models LLM/gemma-3-12b-it-q4_k_m.gguf`

---

## 10. API-карта (основные эндпоинты)

### 10.1 Игровой цикл
- `POST /api/game/action/stream` — основной SSE канал игры.
- `POST /api/game/action` — sync fallback.
- `POST /api/game/turn` — typed turn API.

### 10.2 Состояние и интерфейс
- `GET /api/session/state/{campaign_id}`
- `GET /api/npcs/{campaign_id}`
- `GET /api/interface/campaign/{campaign_id}`
- `GET/POST /api/interface/players/{campaign_id}`
- `GET/POST /api/interface/facts/{campaign_id}`
- `GET /api/interface/sessions/{campaign_id}`

### 10.3 Player session
- `POST /api/player/heartbeat`
- `GET /api/player/active/{campaign_id}`
- `GET/POST /api/player/session/{campaign_id}`
- `POST /api/player/select`

### 10.4 Characters / Combat / World
- `POST /api/characters/upsert`
- `GET /api/characters/{campaign_id}`
- `POST /api/combat/start`
- `POST /api/combat/attack`
- `POST /api/combat/next-turn/{campaign_id}/{combat_id}`
- `POST /api/world/tick/{world_id}`
- `POST /api/campaign/load`

### 10.5 Ingest / Debug / Health
- `POST /api/knowledge/import`
- `POST /api/import/world`
- `GET /api/health`
- `GET /api/system/status`
- `GET /api/system/requirements`
- `GET /api/status/readiness`
- `GET /api/debug/health/agents`
- `GET /api/debug/vram`
- `GET /api/debug/logs-tail`

---

## 11. Где хранятся данные

Основные рабочие данные лежат в `backend/data/`:
- `campaign_memory_*.jsonl`
- `session_memory_*.jsonl`
- `npc_memory_*.jsonl`
- `world_canon_*.jsonl`
- `campaigns/{campaign_id}/campaign_state.json`
- `campaigns/{campaign_id}/characters.json`
- `logs/` (jsonl логи, scene changes, sandbox logs)
- `npcs/major_npcs.json`

---

## 12. Известные ограничения и риски

### 12.1 Архитектурные
- C.2 (вводное описание старта сессии) ещё не реализован как формальный режим.
- Event/World контекст пока не полностью изолирован по campaign.

### 12.2 Модельные
- Есть drift путей fallback-моделей в `config.py` относительно реального содержимого `Models LLM`.
- При переключении на отсутствующий fallback возможны ошибки загрузки модели.

### 12.3 Тесты и legacy
- `backend/run_terminal_dm.py` и часть тестов всё ещё завязаны на legacy `orchestrator`.
- Тестовый контур требует очистки и миграции к `game_loop`.

---

## 13. Что считать legacy (чтобы не тратить время зря)

- `orchestrator` как runtime-ядро.
- Док-утверждения «streaming отсутствует».
- Старые планы, где current-код не учитывается (`game_loop`/SSE/Event integration).

---

## 14. Roadmap (операционный, актуальный)

### R0 (P0): стабилизация ядра
1. Реализовать C.2 (first-turn/session-start intro).
2. Изолировать EventBus/WorldState по campaign.
3. Финализировать C.3 (single source of addressee).
4. Починить manifest моделей и fallback-валидацию.
5. Восстановить минимальный quality gate (`pytest` + smoke).

### R1 (P1): Memory Core v1
1. Ввести фасад `MemoryManager`.
2. Формализовать working/session/campaign/world слои памяти.
3. Добавить compressor + decay policy.
4. Ввести жёсткий token-budget контекста.

### R2 (P1/P2): persistent storage
1. SQLite для структурных сущностей.
2. Snapshot manager.
3. FAISS для семантического retrieval.
4. Debug/API редактирование фактов памяти.

### R3 (P1): NPC Cognitive Core v1
1. Расширить `mind`-схему NPC (beliefs/goals/plans/theory_of_mind/learning).
2. Полный цикл `Perceive -> Feel -> Think -> Decide -> Act -> Learn`.
3. Tiered autonomy (`mass/minor/major`).
4. Сохранить принцип: решения Python, язык от LLM.

### R4 (P2): gameplay depth
1. Reputation/Faction engine.
2. Углубление D&D 5e механик.
3. Расширение UI (player/debug/history panels).

### R5 (P2/P3): масштабирование
1. Профилирование 500+ NPC сценариев.
2. Перф/смоук-набор для API и latency.
3. Метрики регрессий NPC-консистентности.

---

## 15. Конвенции разработки для этого репозитория

1. Новый runtime-код ориентировать на `game_loop` и текущие сервисы.
2. Не реанимировать `orchestrator`-ветку как основной путь.
3. Логику мира писать в Python-сервисы, не в текстовые промпты.
4. Любой новый функционал проверять на:
   - совместимость со SceneState,
   - влияние на latency,
   - влияние на VRAM budget.

---

## 16. Быстрый FAQ

### Q: Почему backend стартует, но модель «молчит»?
Проверьте наличие `llama-server.exe` и `gemma-3-12b-it-q4_k_m.gguf`, затем `http://127.0.0.1:8080/v1/models`.

### Q: Почему тесты не запускаются, хотя `pytest` в requirements?
Скорее всего запущен не тот Python (вне `/.venv`), либо не выполнена установка зависимостей в этом окружении.

### Q: Почему персонаж не отвечает NPC, хотя обращение есть?
Проверьте `scene_state.player_target_*`, activity NPC (не спит ли), и фильтр perception в текущей локации.

---

## 17. Главный практический вывод

```text
orchestrator -> game_loop
```

Это фундамент текущей системы. Все изменения, документация, тесты и roadmap должны исходить из этой реальности.
