# Enigma — Local AI Dungeon Master System

Локальная система ИИ-мастера для D&D 5e с мультиагентной архитектурой, переключением моделей и долговременной памятью.

## Реализовано в MVP

- Backend на **FastAPI**.
- Multi-agent pipeline:
  - DM Agent
  - Rules Agent
  - NPC Agent
  - World Simulation Agent
  - Memory Manager Agent
- **Трёхслойная память кампании**:
  1. `WORLD_CANON` (неизменяемый канон мира)
  2. `CAMPAIGN_MEMORY` (долгосрочная память кампании)
  3. `SESSION_MEMORY` (краткосрочный контекст сессии)
- Dynamic context builder перед ходом (`world_canon + campaign_memory + session_memory`).
- Adventure loader для загрузки локальных кампаний из `data/campaigns/<campaign_id>/`.
- Runtime переключение LLM-модели через `model` в запросе (`SWITCH MODEL` основа для UI) через `LlmManager`/`ModelRouter`.
- Добавлен локальный адаптер `llama_cpp` для запуска `llama.cpp` бинарника и GGUF-модели через subprocess.
- Canon-guard для DM: без загруженного `WORLD_CANON` мастер просит уточнение и не продвигает сюжетные world-change события.
- Локальное JSONL хранение (с дальнейшей заменой на SQLite/vector DB).

## Производительность и системные требования

- Минимальный профиль хоста: **CPU уровня i7-9700F** (8+ физических ядер) и **16 ГБ RAM**.
- Добавлен runtime-check требований перед игровым ходом (можно отключить через `AIDM_ENFORCE_SYSTEM_REQUIREMENTS=false`).
- Агентные вычисления (Rules/NPC/WorldSimulation) выполняются параллельно через `ThreadPoolExecutor`.
- Добавлен cache для чтения последних записей памяти и оптимизировано чтение JSONL через tail-подход.

## Структура

```text
backend/
  app/
    agents/
    api/
    core/
    models/
    services/
data/
  campaigns/
  worlds/
  assets/
frontend/
  ui/
  map/
  chat/
```

## Быстрый запуск

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```


## Проверки

```bash
python -m compileall backend/app
PYTHONPATH=backend python -m unittest discover -s backend/tests -p "test_*.py"
cd backend && python -m pytest -q
```

Для запуска тестов из корня можно использовать:

```bash
PYTHONPATH=backend python -m pytest backend/tests -q
```


## Готовность игры сейчас

Коротко: **нет, пока не всё в порядке и не всё присутствует** — это MVP backend.

Уже есть:
- базовый цикл хода игры и журналы
- layered memory
- проверка минимального железа
- базовый импорт мира

Пока отсутствует/частично:
- полноценный D&D 5e rules engine
- desktop UI (chat/map/player/event log)
- карта с токенами/fog of war
- фоновый world simulation scheduler
- production-интеграции LLM провайдеров

Для быстрой проверки добавлен endpoint:
- `GET /api/status/readiness`


## Прогресс разработки

Сейчас прогресс по продуктовой цели ориентировочно **50%**:
- ✅ есть backend, многослойная память, базовая оркестрация, импорт мира
- ✅ добавлены персонажи кампании (сохранение/список)
- ✅ добавлен принудительный world tick и скрытый журнал событий мира
- ✅ добавлен импорт знаний из PDF/TXT/MD для world/rules/characters/npc/campaign
- ✅ добавлен базовый combat API (инициатива/ход/атака/урон)
- ⚠️ нет полноценного desktop UI
- ⚠️ нет полного rules engine D&D 5e
- ⚠️ нет production-интеграций LLM провайдеров

## API

- `GET /api/health`
- `GET /api/system/requirements`
- `GET /api/status/readiness`
- `POST /api/campaign/load`
- `POST /api/world/tick/{world_id}`
- `POST /api/characters/upsert`
- `GET /api/characters/{campaign_id}`
- `POST /api/combat/start`
- `POST /api/combat/attack`
- `POST /api/combat/next-turn/{campaign_id}/{combat_id}`
- `POST /api/knowledge/import`
- `POST /api/game/turn`
- `GET /api/session/state/{campaign_id}` (возвращает `world_id`, актуальный лог и срез memory layers)
- `POST /api/import/world`

### Принцип по кубикам

Если игрок не передал `dice_result`, Rules Agent вернёт: **«Сделайте бросок d20»**.
AI не бросает кубики сам.

## Что дальше

1. Подключить реальные LLM adapters (OpenAI/Anthropic/Gemini/Ollama/LM Studio/llama.cpp/KoboldCPP).
2. Заменить JSONL memory на SQLite + векторную базу (Chroma/FAISS/Qdrant).
3. Добавить полную боёвку D&D 5e (атаки, saving throws, состояния, эффекты заклинаний).
4. Сделать desktop UI с картой, токенами и журналом сессии.


## Рекомендованный локальный стек моделей

Для Windows + NVIDIA GeForce RTX 3070 Ti (8 GB VRAM) в MVP рекомендован профиль:
- `llama.cpp`
- `Qwen3.5-9B` в формате GGUF
- запуск через локальный игровой backend (FastAPI orchestrator)

Это даёт лучший баланс качества/скорости и сохраняет портативный формат «одна папка».

### Локальный запуск llama.cpp + model.gguf (Windows)

Если у вас уже есть файлы (как в примере):

- `C:\Users\lipir\OneDrive\Документы\Codex\VSC_Enigma\Models LLM\model.gguf`
- `C:\Users\lipir\OneDrive\Документы\Codex\VSC_Enigma\Models LLM\llama-b8224-bin-win-cuda-12.4-x64\llama.exe`

задайте переменные окружения перед запуском backend:

```powershell
$env:LLAMA_CPP_EXECUTABLE = "C:\Users\lipir\OneDrive\Документы\Codex\VSC_Enigma\Models LLM\llama-b8224-bin-win-cuda-12.4-x64\llama.exe"
$env:LLAMA_CPP_MODEL = "C:\Users\lipir\OneDrive\Документы\Codex\VSC_Enigma\Models LLM\model.gguf"
```

`LlmManager.run()` для `provider=llama_cpp` автоматически вызовет бинарник командой вида:

```text
llama.exe -m <path-to-model.gguf> -p "<prompt>" -n 128
```

Для локального интеграционного теста используйте:

```powershell
$env:LLAMA_TEST_MODEL = "C:\Users\lipir\OneDrive\Документы\Codex\VSC_Enigma\Models LLM\model.gguf"
```

Тест пропускается автоматически, если бинарник llama.cpp не найден или `LLAMA_TEST_MODEL` не задан.
