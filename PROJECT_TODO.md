# 📜 ENIGMA — Единый план разработки

> **Статус проекта:** Активная разработка | GPU **РАБОТАЕТ** ✅

---

## 🖥️ ХАРАКТЕРИСТИКИ ПК

| Компонент | Характеристика |
|-----------|----------------|
| CPU | i7-9700F (8+ ядер) |
| RAM | 16 GB |
| GPU | NVIDIA RTX 3070 Ti (8 GB VRAM) |
| Compute Capability | 8.6 |
| CUDA Version | 13.1 |
| GPU Layers | 33 |
| Context | 4096 |
| OS | Windows 11 |

---

## 🎮 ИДЕЯ ПРОЕКТА

**Enigma** — локальная система ИИ-мастера для D&D 5e с мультиагентной архитектурой, переключением моделей и долговременной памятью.

### Реализованные компоненты:
- ✅ Backend на FastAPI
- ✅ Llama.cpp + CUDA работает на RTX 3070 Ti
- ✅ 5 агентов: DM, Rules, NPC, World Sim, Memory
- ✅ ModelPool с lazy loading (1 модель в VRAM)
- ✅ Multi-model routing
- ✅ 4 GGUF модели доступны

---

## 📁 СТРУКТУРА ПРОЕКТА

```
Enigma/
├── backend/
│   ├── app/
│   │   ├── agents/              # 5 АГЕНТОВ
│   │   │   ├── dm_agent.py      # Dungeon Master
│   │   │   ├── rules_agent.py   # Правила D&D
│   │   │   ├── npc_agent.py     # NPC
│   │   │   ├── world_sim_agent.py  # Симуляция мира
│   │   │   └── memory_manager_agent.py  # Память
│   │   ├── api/routes.py        # API endpoints
│   │   ├── core/config.py       # Конфигурация
│   │   ├── models/schemas.py   # Pydantic схемы
│   │   └── services/
│   │       ├── llm/             # LLM инфраструктура
│   │       │   ├── factory.py        # Фабрика провайдеров
│   │       │   ├── provider_manager.py  # Менеджер провайдеров
│   │       │   ├── provider.py       # Базовый провайдер
│   │       │   ├── llama_cpp_provider.py  # Llama.cpp адаптер
│   │       │   └── router.py         # Роутинг агентов
│   │       ├── model_pool.py     # POOL с lazy loading
│   │       ├── memory.py         # Трёхслойная память
│   │       ├── context_builder.py # Динамический контекст
│   │       ├── campaign_state_service.py # Состояние кампании
│   │       ├── combat_service.py  # Бовая система
│   │       └── character_service.py # Персонажи
│   ├── run_terminal_dm.py       # Терминальный режим DM
│   ├── start_enigma.bat          # ⚡ ГЛАВНЫЙ ЗАПУСК
│   ├── start_dev.ps1             # Выбор модели при запуске
│   └── tests/
├── data/
│   ├── campaigns/                 # Кампании игроков
│   ├── pdf_drop/                 # 7 PDF книг D&D
│   └── worlds/                   # Миры
├── Models LLM/                   # 4 модели GGUF
│   ├── llama/                    # llama.cpp binaries
│   ├── qwen2.5-7b-instruct-q4_k_m.gguf   # DM (основная)
│   ├── Qwen3.5-9B.gguf                      # World Sim
│   ├── saiga_mistral_7b_model-q4_K.gguf   # Rules, Memory
│   └── YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf  # NPC
├── frontend/
│   └── ui/
│       ├── index.html             # Web UI
│       ├── css/                  # Стили
│       ├── js/                   # Скрипты
│       └── assets/               # Изображения и медиа
├── AppAgent/                     # Технологический демо
├── docs/                         # Документация и промты
└── Tasks/                        # История задач
```

---

## ⚡ ВАЖНЫЕ ЗАМЕТКИ

### 🔴 Запуск игры (ОБЯЗАТЕЛЬНО!)

**Один клик — всё готово:**
```
backend\start_enigma.bat
```
Этот файл запускает:
1. LLaMA Server (порт 8080)
2. FastAPI Backend (порт 8000)

**Альтернатива с выбором модели:**
```
cd backend
powershell -File start_dev.ps1
```
Скрипт спросит какую модель запустить.

### 🟡 Терминал

> **ВАЖНО:** В терминале Windows **НЕ работает** команда с `&&`!
> - ❌ `команда1 && команда2` — НЕ РАБОТАЕТ
> - ✅ Используй отдельные команды

> **Активация виртуального окружения:**
```powershell
# Правильно (с точкой и обратным слэшем):
.venv\Scripts\Activate.ps1
```

### 🟢 Рабочие команды терминала

```powershell
# Активация venv
.venv\Scripts\Activate.ps1

# Запуск llama-server отдельно
cd "c:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\llama"
.\llama-server.exe -c 4096 -ngl 33 -cml "путь\к\модели.gguf" --port 8080

# Запуск терминала DM
python backend/run_terminal_dm.py
```

---

## 📋 РАЗДЕЛЫ ЗАДАЧ

### 1. CORE INFRASTRUCTURE ✅ ЗАВЕРШЕНО

| Задача | Статус | Примечания |
|--------|--------|------------|
| Backend FastAPI | ✅ Готово | |
| Llama.cpp + CUDA | ✅ Готово | RTX 3070 Ti работает! |
| Модель Qwen2.5-7b | ✅ Готово | 33 слоя на GPU |
| Трёхслойная память | ✅ Готово | World Canon → Campaign → Session |
| Dynamic Context | ✅ Готово | Семантический поиск, n_keep |
| Campaign State | ✅ Готово | Игроки, факты, сводки сессий |
| Терминальный DM | ✅ Готово | Команды: /ingest, /campaign, /player и т.д. |
| PDF Import | ✅ Готово | 7 книг загружено |

---

### 2. MULTI-MODEL AGENTS ✅ ЗАВЕРШЕНО

| Агент | Модель | Статус | Файл |
|-------|--------|--------|------|
| DM Agent | qwen2.5-7b | ✅ Готово | `backend/app/agents/dm_agent.py` |
| Rules Agent | saiga-7b | ✅ Готово | `backend/app/agents/rules_agent.py` |
| NPC Agent | YandexGPT-8B | ✅ Готово | `backend/app/agents/npc_agent.py` |
| World Sim Agent | Qwen3.5-9B | ✅ Готово | `backend/app/agents/world_sim_agent.py` |
| Memory Agent | saiga-7b | ✅ Готово | `backend/app/agents/memory_manager_agent.py` |

**Инфраструктура:**
- ✅ ModelPool с lazy loading (max 1 модель в VRAM)
- ✅ ProviderRegistry для инициализации
- ✅ Router с capability-based routing
- ✅ Fallback логика
- ✅ Health check система

**Команды для работы:**
| Команда | Описание |
|---------|----------|
| `/model 1-4` | Сменить модель на лету |
| `/ingest` | Импортировать PDF |
| `/state` | Состояние памяти |
| `/campaign` | Состояние кампании |

---

### 3. FRONTEND / UI ⚠️ ЧАСТИЧНО

| Задача | Статус | Примечания |
|--------|--------|------------|
| Web UI | ⚠️ Базовый | `frontend/ui/index.html` |
| Чат-интерфейс | ⚠️ Базовый | Есть, но нужен редизайн |
| Карта с токенами | ❌ Нет | |
| Fog of War | ❌ Нет | |
| Журнал событий | ❌ Нет | |
| Debug Console | ❌ Нет | Нужно добавить |
| Панель игроков (HP, инвентарь) | ❌ Нет | |
| Панель мастера | ❌ Нет | |
| Исправление пути к Frontend в main.py | ✅ Исправлено | parents[3] → parents[2] |
| Исправление HTML в index.html | ✅ Исправлено | Тег body перемещён после head |
| Созданы папки css/js/assets | ✅ Готово | Для структурированности |

**Что нужно сделать для Frontend:**
1. Исправить баги в index.html (незакрытые div) ✅ Исправлено
2. Добавить обработку команд (/roll, /clear, /help)
3. Добавить автообновление состояния (setInterval)
4. Сделать структурированный ответ от DM
5. Добавить Debug Console

---

### 4. GAME MECHANICS ⚠️ ЧАСТИЧНО

| Задача | Статус | Примечания |
|--------|--------|------------|
| Combat API | ⚠️ Базовый | Есть start, attack |
| Система заклинаний | ❌ Нет | |
| Conditions (состояния) | ❌ Нет | |
| Saving throws | ❌ Нет | |
| Skill checks | ❌ Нет | |
| Инвентарь | ❌ Нет | |

---

### 5. INFRASTRUCTURE ❌ НЕ РЕАЛИЗОВАНО

| Задача | Статус | Примечания |
|--------|--------|------------|
| Векторная БД | ❌ Нет | Нужен Chroma/FAISS/Qdrant |
| SQLite | ❌ Нет | Сейчас JSONL |
| Production LLM | ❌ Нет | Нет OpenAI, Anthropic, Ollama |

---

### 6. MULTIPLAYER ❌ НЕ РЕАЛИЗОВАНО

| Задача | Статус | Примечания |
|--------|--------|------------|
| Мультиплеер | ❌ Нет | Только один игрок за терминалом |

---

### 7. ДОПОЛНИТЕЛЬНО ✅/❌

| Задача | Статус | Примечания |
|--------|--------|------------|
| Debug Mode в start_enigma.bat | ❌ Нет | Проверка портов 8080, 8000, 8081 |
| Проверка зависимостей при запуске | ❌ Нет | Python, папки, скрипты |
| Создание персонажа с DM | ⚠️ Частично | Есть UI, но есть баги (см. секцию 8) |

---

### 8. ИСПРАВЛЕНИЕ БАГОВ СОЗДАНИЯ ПЕРСОНАЖА (Tasks3.2)

> Критические проблемы цикла создания персонажа

| Задача | Статус | Примечания |
|--------|--------|------------|
| Повторное появление окна "Выберите персонажа" | ✅ Исправлено | Автоматически выбирается первый персонаж |
| Блокировка LLM до active персонажа | ✅ Частично | Добавлена проверка при отправке |
| Дублирование "Персонаж создан!" | ✅ Исправлено | Флаг characterCreated, умные сообщения |
| 412 Precondition Failed не обрабатывается | ⚠️ Требует backend | Нужна доработка API |
| Стартовая инициализация непредсказуема | ✅ Исправлено | Автоматический выбор первого персонажа |

**Выполненные исправления:**
1. ✅ При инициализации: если игроки есть → выбираем первого автоматически
2. ✅ Если игроков нет → показываем модальное окно создания
3. ✅ После создания персонажа → обновляем селектор, выбираем нового персонажа
4. ✅ Добавлены флаги characterCreated и isInitialized
5. ✅ Умные сообщения о создании персонажа

---

## 📊 ПРОГРЕСС

```
Текущий прогресс: ~65%

[████████████████████] Core            100%
[████████████████████] Multi-model      100%
[████████░░░░░░░░░░░░] Frontend        30%
[████░░░░░░░░░░░░░░░░░] Game Mechanics  20%
[░░░░░░░░░░░░░░░░░░░░░] Infrastructure   0%
[░░░░░░░░░░░░░░░░░░░░░] Multiplayer      0%
```

---

## 🔧 ЧТО ДЕЛАТЬ (ROADMAP)

### Приоритет 1: Frontend (сейчас)
1. Исправить баги в index.html
2. Добавить обработку команд
3. Добавить автообновление
4. Панель игроков (HP)
5. Debug Console

### Приоритет 2: Game Mechanics
1. Полная система заклинаний
2. Conditions (состояния)
3. Saving throws
4. Skill checks

### Приоритет 3: Infrastructure
1. SQLite
2. Векторная база (Qdrant)
3. Ollama/LM Studio адаптеры

### Приоритет 4: Multiplayer
1. Множественные подключения
2. Синхронизация состояния

---

## 📚 ЗАГРУЖЕННЫЕ PDF

| # | Книга | Статус |
|---|------|--------|
| 1 | 5e Dungeon Masters Guide - Руководство Мастера RUS | ✅ |
| 2 | 5e Players Handbook - Книга Игрока RUS | ✅ |
| 3 | Elemental Evil Players Companion | ✅ |
| 4 | Sword Coast Adventurers Guide RUS | ✅ |
| 5 | Tasha's Cauldron of Everything RUS | ✅ |
| 6 | Waterdeep Драконий Куш | ✅ |
| 7 | Xanathars Guide to Everything RUS | ✅ |

---

## 🔧 API ENDPOINTS

```
GET  /api/health
GET  /api/system/requirements
GET  /api/status/readiness
POST /api/campaign/load
POST /api/world/tick/{world_id}
POST /api/characters/upsert
POST /api/combat/start
POST /api/combat/attack
POST /api/knowledge/import
POST /api/game/turn
GET  /api/session/state/{campaign_id}
POST /api/import/world
GET  /api/interface/players/{campaign_id}
POST /api/interface/players/{campaign_id}
```

---

## 📝 КОМАНДЫ ТЕРМИНАЛА DM

| Команда | Описание |
|---------|----------|
| `/model 1-4` | Сменить модель (qwen7, qwen9, saiga, yandex) |
| `/ingest` | Загрузить знания из pdf_drop |
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

## 📂 АРХИВ СТАРЫХ TODO ФАЙЛОВ

> Эти файлы можно удалить после проверки:

```
TODO.md                         → Перенесено в секцию Core
TODO_CHARACTER_CREATION.md      → Перенесено в Frontend
TODO_FIX_LLM_DM_ROLE.md         → ЗАВЕРШЕНО (исправлено)
TODO_FRONTEND.md                → Перенесено в Frontend
TODO_LAZY_MODEL_LOADING.md      → ЗАВЕРШЕНО (ModelPool готов)
TODO_LLM_INTEGRATION.md         → ЗАВЕРШЕНО (CUDA работает)
TODO_MULTIMODEL.md              → ЗАВЕРШЕНО (агенты готовы)
TODO_PROMPT_INTEGRATION.md      → ЗАВЕРШЕНо
TODO_REFACTOR_MODEL_ROUTER.md   → ЗАВЕРШЕНО (Router готов)
TODOW_INTERFACE.md              → Неизвестно
```

---

*Обновлено: 2025 | Enigma Project*

