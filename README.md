# Enigma — Local AI Dungeon Master System

Локальная система ИИ-мастера для D&D 5e с мультиагентной архитектурой, переключением моделей и долговременной памятью.

> **Статус:** GPU **РАБОТАЕТ** ✅ | Multi-model agents **РЕАЛИЗОВАНЫ** ✅

---

## Реализовано

### ✅ Core Infrastructure
- Backend на **FastAPI**
- **Llama.cpp + CUDA** — работает на RTX 3070 Ti (8GB VRAM)
- Модель: `Qwen2.5-7b-instruct-q4_k_m.gguf` (33 слоя на GPU)
- Многопоточная обработка агентных запросов

### ✅ Multi-agent Pipeline
- **DM Agent** — нарратив и взаимодействие с игроками
- **Rules Agent** — проверка правил D&D 5e
- **NPC Agent** — управление NPC и их реакции
- **World Simulation Agent** — симуляция событий мира
- **Memory Manager Agent** — управление контекстом и памятью

Каждый агент использует свою модель через ModelPool с lazy loading.

### ✅ Трёхслойная память кампании
1. `WORLD_CANON` — неизменяемый канон мира, загружается из PDF
2. `CAMPAIGN_MEMORY` — долгосрочная память кампании
3. `SESSION_MEMORY` — краткосрочный контекст сессии

### ✅ Dynamic Context Builder
- Извлечение ключевых слов из запроса игрока
- Семантические связи (леч → клирик, храм; торг → купец, рынок...)
- Взвешивание по категориям и тегам
- Последние 15 сообщений сессии в контексте
- Защита системного промпта через `n_keep`

### ✅ Campaign State System
- Игроки (имя, раса, класс, уровень, заметки)
- Факты мира (категории: location/npc/quest/lore, теги, источник)
- Сводки сессий (дата, summary, локация, ключевые события)

### ✅ Терминальный режим DM
- Работает в VS Code терминале
- Команды: `/ingest`, `/state`, `/campaign`, `/player`, `/fact`, `/session`, `/exit`
- Системный промпт оптимизирован для русского языка
- Пост-процессинг: очистка тегов и мусора из ответов модели
- Переключение моделей: `/model 1-4`

### ✅ Дополнительные фичи
- Combat API (инициатива, ход, атака, урон)
- Импорт знаний из PDF/TXT/MD
- ModelPool с lazy loading (1 модель в VRAM)
- Provider Registry с health checks
- Проверка системных требований

---

## 🚨 Что НЕ хватает

### Frontend / UI
1. ❌ **Полноценный Desktop UI** — нет чата, карты, журнала событий
2. ❌ **Web-интерфейс** — есть базовый, но требует доработки
3. ❌ **Панель игроков** — HP, инвентарь, характеристики
4. ❌ **Debug Console** — для разработки

### Game Mechanics
5. ❌ **Полный Rules Engine D&D 5e** — только базовый combat API
6. ❌ **Система заклинаний** — нет
7. ❌ **Conditions (состояния)** — нет
8. ❌ **Saving throws / Skill checks** — нет

### Infrastructure
9. ❌ **Векторная база данных** — всё на JSONL, нужен Chroma/FAISS/Qdrant
10. ❌ **SQLite** — сейчас JSONL файлы
11. ❌ **Production LLM провайдеры** — только llama.cpp

### Геймплей
12. ❌ **Карта с токенами** — нет визуализации
13. ❌ **Fog of War** — нет
14. ❌ **World Simulation Scheduler** — фоновые события не работают
15. ❌ **Мультиплеер** — только один игрок за терминалом

---

## Доступные модели

| Модель | Для агента | Статус |
|--------|------------|--------|
| qwen2.5-7b-instruct-q4_k_m.gguf | DM (основная) | ✅ Работает |
| Qwen3.5-9B.gguf | World Sim | ✅ Работает |
| saiga_mistral_7b_model-q4_K.gguf | Rules, Memory | ✅ Работает |
| YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf | NPC | ✅ Работает |

**GPU: RTX 3070 Ti (8GB)**
- GPU Layers: 33
- Context: 4096
- Threads: 8

---

## Структура проекта

```text
Enigma/
├── backend/
│   ├── app/
│   │   ├── agents/              # 5 агентов
│   │   │   ├── dm_agent.py
│   │   │   ├── rules_agent.py
│   │   │   ├── npc_agent.py
│   │   │   ├── world_sim_agent.py
│   │   │   └── memory_manager_agent.py
│   │   ├── api/routes.py
│   │   ├── core/config.py
│   │   ├── models/schemas.py
│   │   └── services/
│   │       ├── llm/            # LLM инфраструктура
│   │       │   ├── factory.py
│   │       │   ├── provider_manager.py
│   │       │   ├── llama_cpp_provider.py
│   │       │   └── router.py
│   │       ├── model_pool.py   # Lazy loading
│   │       ├── memory.py
│   │       └── context_builder.py
│   ├── run_terminal_dm.py
│   ├── start_enigma.bat        # ⚡ ГЛАВНЫЙ ЗАПУСК
│   └── start_dev.ps1          # Выбор модели
├── data/
│   ├── campaigns/
│   ├── pdf_drop/               # 7 PDF книг!
│   └── worlds/
├── Models LLM/                 # 4 модели
│   ├── llama/
│   └── *.gguf
└── frontend/ui/index.html
```

---

## Быстрый запуск

### Вариант 1: Один клик (рекомендуется)
```
backend\start_enigma.bat
```
Запускает LLaMA Server + FastAPI Backend.

### Вариант 2: С выбором модели
```
cd backend
powershell -File start_dev.ps1
```
Скрипт спросит какую модель запустить.

### Вариант 3: Терминальный DM
```bash
cd backend
.venv\Scripts\Activate.ps1
python run_terminal_dm.py
```

---

## Команды терминала DM

| Команда | Описание |
|---------|----------|
| `/model 1-4` | Сменить модель (qwen7, qwen9, saiga, yandex) |
| `/ingest` | Загрузить знания из `data/pdf_drop` |
| `/state` | Показать размеры слоёв памяти |
| `/campaign` | Сводка кампании |
| `/campaign set <name>` | Установить название |
| `/player` | Список игроков |
| `/player add <name> <race> <class> <level>` | Добавить игрока |
| `/fact` | Факты мира |
| `/fact add <text>` | Добавить факт |
| `/session` | Сводки сессий |
| `/exit` | Выход |

---

## Загруженные PDF (data/pdf_drop)

1. ✅ 5e Dungeon Masters Guide - Руководство Мастера RUS.pdf
2. ✅ 5e Players Handbook - Книга Игрока RUS.pdf
3. ✅ Elemental Evil Players Companion.pdf
4. ✅ Sword Coast Adventurers Guide RUS.pdf
5. ✅ Tasha's Cauldron of Everything RUS.pdf
6. ✅ Waterdeep Драконий Куш.pdf
7. ✅ Xanathars Guide to Everything RUS.pdf

---

## API Endpoints

- `GET /api/health`
- `GET /api/system/requirements`
- `GET /api/status/readiness`
- `POST /api/campaign/load`
- `POST /api/world/tick/{world_id}`
- `POST /api/characters/upsert`
- `POST /api/combat/start`
- `POST /api/combat/attack`
- `POST /api/knowledge/import`
- `POST /api/game/turn`
- `GET /api/session/state/{campaign_id}`
- `POST /api/import/world`
- `GET /api/interface/players/{campaign_id}`
- `POST /api/interface/players/{campaign_id}`

---

## Прогресс разработки

Текущий прогресс: **~65%**

| Компонент | Статус | Примечание |
|-----------|--------|------------|
| Backend API | ✅ Готов | |
| Llama.cpp + CUDA | ✅ Готов | RTX 3070 Ti работает! |
| Multi-model agents | ✅ Готов | 5 агентов на разных моделях |
| Трёхслойная память | ✅ Готов | |
| Dynamic Context | ✅ Готов | |
| Campaign State | ✅ Готов | |
| Терминальный DM | ✅ Готов | |
| PDF Import | ✅ Готов | 7 книг загружено |
| Web UI | ⚠️ Базовый | Нужен редизайн |
| Полный Rules Engine | ❌ Нет | |
| Векторная БД | ❌ Нет | |
| SQLite | ❌ Нет | JSONL |
| Карта/Токены | ❌ Нет | |
| Fog of War | ❌ Нет | |
| Мультиплеер | ❌ Нет | |

---

## Что дальше (Roadmap)

### Фаза 1: Frontend (приоритет!)
1. Исправить баги в index.html
2. Добавить обработку команд (/roll, /clear, /help)
3. Добавить панель игроков (HP, инвентарь)
4. Добавить Debug Console

### Фаза 2: Game Mechanics
1. Полная система заклинаний
2. Conditions (состояния)
3. Saving throws
4. Skill checks

### Фаза 3: Infrastructure
1. SQLite
2. Векторная база (Qdrant)
3. Ollama/LM Studio адаптеры

### Фаза 4: Multiplayer
1. Множественные подключения
2. Синхронизация состояния

---

## Системные требования

- **CPU:** i7-9700F (8+ ядер)
- **RAM:** 16 GB
- **GPU:** NVIDIA RTX 3070 Ti (8 GB VRAM) ✅
- **OS:** Windows 11

---

## Конфигурация CUDA

```
GPU: NVIDIA GeForce RTX 3070 Ti (8GB)
Compute Capability: 8.6
CUDA Version: 13.1
Model Layers on GPU: 33
```

---

## Тестирование

```bash
# Проверка синтаксиса
python -m compileall backend/app

# Юнит-тесты
PYTHONPATH=backend python -m unittest discover -s backend/tests -p "test_*.py"

# Pytest
cd backend && python -m pytest -q
```

---

## Важные заметки

> **Терминал Windows:** Команда `&&` **НЕ работает**!
> - ✅ `.venv\Scripts\Activate.ps1` — правильно (с точкой!)
> - ❌ Не используй `команда1 && команда2`

> **Запуск игры:** `backend\start_enigma.bat`

