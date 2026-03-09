# Enigma — AI Dungeon Master System

## Текущее состояние

**Статус:** RTX 3070 Ti работает с CUDA. Система функционирует.

## Аппаратное обеспечение
- GPU: NVIDIA RTX 3070 Ti (8GB VRAM)
- RAM: 16 GB
- CPU: i7-9700F

## Доступные модели (GGUF)

| Модель | Размер | Статус | Назначение |
|--------|--------|--------|------------|
| qwen2.5-7b-instruct-q4_k_m.gguf | 7B | ✅ Используется | Текущая |
| Qwen3.5-9B.gguf | 9B | ❌ Без дела | Потенциал: DM |
| saiga_mistral_7b_model-q4_K.gguf | 7B | ❌ Без дела | Потенциал: NPC |
| YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf | 8B | ❌ Без дела | Потенциал: резерв |

## Реализовано

### Backend
- FastAPI сервер
- Llama.cpp адаптер с CUDA поддержкой
- 5 агентов: DM, Rules, NPC, World Simulation, Memory Manager
- Трёхслойная память: WORLD_CANON → CAMPAIGN_MEMORY → SESSION_MEMORY
- Dynamic Context Builder с RAG-поиском
- Campaign State System
- Combat API (базовый)
- PDF Import (7 книг D&D загружено)

### Терминальный DM
- Работает в VS Code терминале
- Команды: /ingest, /state, /campaign, /player, /fact, /session, /exit
- Системный промпт оптимизирован для русского языка

### API Endpoints
- `/api/health`
- `/api/status/readiness`
- `/api/campaign/load`
- `/api/world/tick/{world_id}`
- `/api/combat/start`
- `/api/combat/attack`
- `/api/game/turn`

## Не реализовано

### Критично
1. ❌ Мультимодельность (все агенты на одной qwen2.5-7b)
2. ❌ Desktop UI (чат, карта, журнал)
3. ❌ Web-интерфейс
4. ❌ Полный Rules Engine (нет заклинаний, conditions, saving throws)

### Инфраструктура
5. ❌ Векторная БД (Chroma/FAISS/Qdrant)
6. ❌ SQLite (сейчас JSONL)
7. ❌ Ollama/LM Studio адаптеры

### Геймплей
8. ❌ Карта с токенами
9. ❌ Fog of War
10. ❌ World Simulation Scheduler
11. ❌ Мультиплеер

## Структура проекта

```
Enigma/
├── backend/
│   ├── app/
│   │   ├── agents/           # dm_agent, rules_agent, npc_agent, world_sim_agent, memory_manager
│   │   ├── api/routes.py
│   │   ├── services/
│   │   │   ├── llama_cpp.py
│   │   │   ├── llm_manager.py
│   │   │   ├── model_router.py
│   │   │   ├── context_builder.py
│   │   │   ├── campaign_state_service.py
│   │   │   └── ...
│   │   └── models/schemas.py
│   ├── run_terminal_dm.py   # Терминальный DM
│   └── config.json
├── data/
│   ├── campaigns/            # demo-campaign, test-campaign
│   ├── pdf_drop/             # 7 PDF книг D&D
│   └── worlds/
├── Models LLM/
│   ├── llama/                # llama-server.exe + CUDA DLLs
│   └── *.gguf               # 4 модели
└── AppAgent/                 # Отдельный проект
```

## Загруженные PDF (data/pdf_drop)

1. 5e Dungeon Masters Guide - Руководство Мастера RUS.pdf
2. 5e Players Handbook - Книга Игрока RUS.pdf
3. Elemental Evil Players Companion.pdf
4. Sword Coast Adventurers Guide RUS.pdf
5. Tasha's Cauldron of Everything RUS.pdf
6. Waterdeep Драконий Куш.pdf
7. Xanathars Guide to Everything RUS.pdf

## Принципы

1. **Dice System:** ИИ никогда не генерирует броски. Игроки используют реальные кубики и сообщают результат.
2. **Memory:** Три слоя памяти работают через Dynamic Context Builder.
3. **Canon Guard:** Без загруженного WORLD_CANON DM не продвигает сюжетные события.

## Запуск

```bash
cd backend
python run_terminal_dm.py
```

Или one-click: `backend\start_dm_terminal_with_server_working.bat`

## Roadmap

### Фаза 1: Мультимодельность
- Назначить разные модели разным агентам
- Оптимизировать GPU memory

### Фаза 2: Desktop UI
- Чат, карта, журнал событий

### Фаза 3: Rules Engine
- Заклинания, conditions, saving throws

### Фаза 4: Инфраструктура
- SQLite, векторная БД, Ollama адаптеры

