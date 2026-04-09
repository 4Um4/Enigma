Итоговая таблица архитектурных решений (финальная):
  #Решение1NPCState — источник истины2Intent хранится в NPCState3Event-trigger + редкий idle тик4Enum + фильтр доступности5RelationshipStore + кэш в NPCState6emotion_base + Σ(delta × decay)7Risk из контекста (свидетели, дистанция, сила)8Радиус → Perception (два фильтра)9DecisionHub = read-only. StateApplicator = write-only10LifeEngine = фоновый тик11intent + emotion + fact-hint ≤ 100 токенов12±10% randomness, seed per-session13Цель: 10–30 NPC, запас до 5014Старт: только R1.1

# ENIGMA — MASTER ROADMAP & ARCHITECTURE (v4.0)
**Тип проекта:** Хардкорная RPG-симуляция (Iron-man)
**Главный принцип:** Недопустимость упрощений. Это не базовая инди-игра, а сложнейший причинно-следственный стек (Causal Stack), где каждая переменная имеет вес, а ошибки архитектуры ведут к каскадному обрушению логики мира. 
LLM — это исключительно голос. Python — это интеллект.

---

## ГЛОБАЛЬНАЯ ЦЕПЬ ПРИЧИННОСТИ (DATA FLOW)
Событие не может перескочить слой. Любое действие в игре проходит строгий конвейер:

1. **Event** (Ввод игрока / Тик мира)
2. **Spatial Filter** [L1] (Кто видит? Геометрия сцены)
3. **DecisionHub** [L0] (Ядро вычислений: профиль + память + эмоции - страх)
4. **Resolution** [L2] (Бросок кубиков и стохастическое смещение)
5. **State Update** [L0 + L5] (Запись дельт, травм, сдвигов памяти)
6. **World Influence** [L6] (Реакция макро-мира, продвижение фронтов)
7. **Verbalization** [L0] (LLM получает `intent` и озвучивает результат)


# Stec_arch — архитектурные стеки и ключевые файлы

> Цель: зафиксировать **главные существующие файлы** по каждому слою системы в текущем состоянии репозитория.
> Если слой реализован частично — отмечено как `PARTIAL`.

---

## L0 — FOUNDATION

### R1 Memory Core (`PARTIAL`) ✔️
- `backend/app/services/memory/memory_manager.py` ✅
- `backend/app/services/memory/layered_memory.py` ✅
- `backend/app/services/memory/working_memory.py` ✅
- `backend/app/services/memory/resonance_engine.py` ✅
- `backend/app/services/memory/importance_engine.py` ✅
- `backend/app/services/memory/relationship_store.py` ✅
- `backend/app/services/memory/contradiction_resolver.py` ✅
- `backend/app/services/memory/__init__.py` ✅
- `backend/app/services/events/event_types.py` ✅
- `backend/app/services/events/event_bus.py` ✅

### R2 Decision Core (`PARTIAL`) ✔️
- `backend/app/services/npc/decision_hub.py` ✅
- `backend/app/services/npc/opportunity_engine.py` ✅
- `backend/app/services/npc/reaction_priority.py` ✅
- `backend/app/services/npc/threat_assessor.py` ✅
- `backend/app/services/npc/npc_cognition.py` ✅
- `backend/app/services/npc/psyche_engine.py` ✅

### R3 Verbalization Layer (`PARTIAL`) ✔️
- `backend/app/services/npc/verbalization_context.py` ✅
- `backend/app/services/prompt_loader.py` ✅
- `backend/app/services/llm/router.py` ✅
- `backend/app/services/llm/provider_manager.py` ✅

---

## L0.5 — ПЕРСИСТЕНТНОСТЬ

### R1.8 Strict Persistence Engine (`PARTIAL`)
- `backend/app/services/scene_state_manager.py`
- `backend/app/services/campaign_state_service.py`
- `backend/app/services/player_session_service.py`
- `backend/app/services/scene_change.py`
- `backend/data/campaigns/` *(runtime storage)*
- `backend/data/logs/` *(change logs)*

### Anti Save-Scumming / rewards (`PARTIAL`)
- `backend/app/services/action/processor.py`
- `backend/app/services/game/combat_math.py`

---

## L1 — ПРОСТРАНСТВО ✔️

### R4 Spatial System (`IMPLEMENTED BASELINE`) ✅
- `backend/app/services/npc/location_graph.py` ✅
- `backend/app/services/npc/spatial_runtime.py` ✅
- `backend/app/services/npc/perception_filter.py` ✅
- `backend/app/services/action/player_target_extractor.py` ✅
- `backend/app/services/scene_state_manager.py` ✅
- `backend/data/locations/location_templates.json` ✅

---

## L2 — МЕХАНИКА ИСХОДОВ

### R5 Resolution Layer (`PARTIAL`) ✔️
- `backend/app/services/game/combat_math.py`
- `backend/app/services/game/physics_validator.py`
- `backend/app/services/action/processor.py`
- `backend/app/services/npc/math_utils.py`

### Gap / Trauma effects (`PARTIAL`)
- `backend/app/services/npc/break_progress_engine.py`
- `backend/app/services/npc/behavior_mask.py`
- `backend/app/services/npc/state_applicator.py`

---

## L3 & L3.5 — АВАТАР И ОГРАНИЧЕНИЯ

### R6 Character Constraint (`PARTIAL`)
- `backend/app/services/character_service.py`
- `backend/app/services/npc/npc_state.py`
- `backend/app/services/npc/behavior_mask.py`
- `backend/app/services/npc/life_engine.py`

### R6.4 Ego Resistance (`PARTIAL`)
- `backend/app/services/npc/behavior_mask.py`
- `backend/app/services/npc/decision_hub.py`
- `backend/app/services/npc/psyche_engine.py`

### R6.5 Hardcore Death (`PARTIAL`)
- `backend/app/services/combat_service.py`
- `backend/app/services/game/combat_math.py`
- `backend/app/services/npc/state_applicator.py`

---

## L4 — СОЦИАЛЬНАЯ СЕТЬ

### R7 Social System (`PARTIAL`)
- `backend/app/services/memory/relationship_store.py`
- `backend/app/services/memory/memory_manager.py`
- `backend/app/services/npc/opportunity_engine.py`
- `backend/app/services/events/event_bus.py`

---

## L5 — СЛОМ

### R8 Break System (`PARTIAL`)
- `backend/app/services/npc/break_progress_engine.py`
- `backend/app/services/npc/behavior_mask.py`
- `backend/app/services/npc/psyche_engine.py`
- `backend/app/services/npc/state_applicator.py`

---

## L6 — МИР

### R9 World Director (`PARTIAL`)
- `backend/app/services/world_scheduler.py`
- `backend/app/services/simulation/world_state.py`
- `backend/app/services/events/event_types.py`
- `backend/app/services/events/event_bus.py`

### R9.8 Economy (`EARLY/PARTIAL`)
- `backend/app/services/simulation/world_state.py`
- `backend/app/services/adventure_loader.py`

---

## L8.5 — GAME LOOP

### R13 Tick-Based Engine (`PARTIAL`)
- `backend/app/services/game_loop.py`
- `backend/app/services/game_loop_factory.py`
- `backend/app/services/world_scheduler.py`
- `backend/app/services/action/processor.py`

### Campaign Manager (`PARTIAL`)
- `backend/app/services/campaign_state_service.py`
- `backend/app/services/player_session_service.py`
- `backend/app/services/scene_state_manager.py`

---

## L9 — FRONTEND & UX

### R14.* UI / FOW (`EARLY`)
- `frontend/ui/index.html`
- `frontend/run_frontend.bat`

---

## L10 — DEVTOOLS

### R15.1 God Mode / diagnostics (`PARTIAL`)
- `backend/app/services/logging_tools.py`
- `backend/app/services/error_interpreter.py`
- `backend/app/services/system_requirements.py`
- `backend/app/services/vram_monitor.py`

### R15.2 Central Math Config (`PARTIAL`)
- `backend/app/core/config.py`
- `backend/app/services/game/combat_math.py`
- `backend/app/services/npc/math_utils.py`

---

## Быстрый индекс «с чего читать в первую очередь»
1. Пространство: `location_graph.py` → `spatial_runtime.py` → `perception_filter.py`
2. Решения NPC: `decision_hub.py` → `opportunity_engine.py` → `reaction_priority.py`
3. Память: `memory_manager.py` → `layered_memory.py` → `resonance_engine.py`
4. Персистентность: `scene_state_manager.py` → `campaign_state_service.py`



## АРХИТЕКТУРНЫЙ СТЕК (СЛОИ СИСТЕМЫ)

### L0 — FOUNDATION (БАЗОВЫЙ ФУНДАМЕНТ)
* **R1 Memory Core (История → Числа):** Перевод фактов в веса. `EventMemory` (сжатие и деградация), `ResonanceEngine` (поиск паттернов). `NarrativeFacts` (замороженные факты). *Критично: Память только формирует веса, решения принимает Хаб.*
* **R2 Decision Core (Причинность):** `DecisionHub` — единственная точка принятия решений. Считает `score(action)` на основе эмоций, отношений, черт (`traits`) и рисков.
* **R3 Verbalization Layer (Речь):** Получает только `intent`, `emotion` и контекст. LLM не видит цифр.

### L0.5 — ПЕРСИСТЕНТНОСТЬ (IRON-MAN БАЗА ДАННЫХ)
* **R1.8 Strict Persistence Engine:** Никаких слотов сохранений. `Auto-save` строго при смене локации или выходе.
* **Защита от Save Scumming:** Игрок не может откатить состояние.
* **Награда (Inspiration):** Токен переброса кубика выдается только за `Critical Success` в сложных заявках.

### L1 — ПРОСТРАНСТВО (ГЕОМЕТРИЯ)
* **R4 Spatial System:** Граф локаций (`LocationGraph`) и координаты (`LocalSpace`). Зона видимости (`Line-of-sight`) и срез доступных действий (`Scene Extraction`).

### L2 — МЕХАНИКА ИСХОДОВ (НЕОПРЕДЕЛЕННОСТЬ)
* **R5 Resolution Layer:** `expected_success` от Хаба смещается броском кубика. 
* **Gap System:** Разница между ожиданием и реальностью (`actual - expected`) порождает травмы и новые черты характера.

### L3 & L3.5 — АВАТАР ИГРОКА И ОГРАНИЧЕНИЯ
* **R6 Character Constraint:** Профиль игрока определяет `affinity` к действиям. 
* **R6.4 Ego Resistance:** Персонаж может сопротивляться вводу игрока, если действие противоречит его `traits` (бросок воли персонажа против игрока).
* **R6.5 Hardcore Death:** При 0 HP → `Unconscious`. Три провала Death Saves (<50% или 1 на D20) = `Permadeath`. Конец игры.

### L4 — СОЦИАЛЬНАЯ СЕТЬ
* **R7 Social System:** `RelationshipMatrix` (NPC↔NPC). Распространение слухов по графу связей.

### L5 — СЛОМ (ПОВЕДЕНЧЕСКАЯ ДЕГРАДАЦИЯ)
* **R8 Break System:** Накопление давления (`fear + stress + failures - support`). Приводит к потере `identity_integrity` и переходу к маскам (`FAKE_SUBMISSION`, `BETRAYAL`). 

### L6 — МИР (ДАВЛЕНИЕ СВЕРХУ)
* **R9 World Director:** Глобальное состояние (`danger_level`, `scarcity`). Фракции и фронты развиваются автономно.
* **R9.8 Real Economy:** Цены = `Base * Regional_Scarcity * NPC_Trust`.

### L8.5 — GAME LOOP (ВРЕМЯ И ЦЕЛИ)
* **R13 Tick-Based Engine:** Асинхронное время. Диалог = 1 тик. Перемещение/Отдых = X тиков.
* **Campaign Manager:** Сюжет длится месяцы внутриигрового времени. Мир меняется асинхронно во время длительного отдыха (анимация времени).

### L9 — FRONTEND & UX (ABSOLUTE FOG OF WAR)
* **R14.1 Эволюция UI:** Текст → Диалоговые окна (Persona style) → 2D Карта с фишками → Единый UI.
* **R14.2 Гибридный ввод:** Выбор из списка ИЛИ `free text` (парсер конвертирует в `PlayerIntent`).
* **R14.3 Absolute Fog of War:** Игрок видит только свои статы. Цифры NPC скрыты (заменены дрожанием текста, цветом портрета). Имена скрыты (???), пока NPC не представится. Карта скрыта в темноте/при слепоте.
* **R14.4 Иллюзия D20:** Математика [0..100] выводится в UI как бросок D20 (1-20).
* **R14.5 Latency Masking:** Анимация «NPC думает...» скрывает задержку LLM (2-4 сек).

### L10 — DEVTOOLS (ЦЕНТР УПРАВЛЕНИЯ ПОЛЕТАМИ)
* **R15.1 God Mode Console:** Скрытая консоль (`~`) для разработчика. Показывает сырые веса и матрицу.
* **R15.2 Central Math Config:** Единый файл конфигурации всех формул и весов для защиты от хардкода.


enigma/
├── start_enigma.bat                 # ЕДИНАЯ ТОЧКА ВХОДА
├── launcher.py                      # (Будущее) Нативное окно
│
├── docs/                            # Концептуальная документация
│   ├── architecture_v2.md           # Принцип "Python=Mind, LLM=Voice"
│   ├── break_system.md              # Механика деградации
│   └── memory_tiers.md              # Спецификации слоев L1-L3
│
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI + startup (запускает GameLoop)
│   │   │
│   │   ├── api/                     # ТРАНСПОРТНЫЙ СЛОЙ (Только передача данных)
│   │   │   ├── routes.py            # REST (run_turn)
│   │   │   ├── routes_stream.py     # SSE (stream_turn)
│   │   │   └── routes_debug.py      # R15 DevTools (God Mode)
│   │   │
│   │   ├── core/                    # L0.5 — БАЗОВЫЕ МЕХАНИЗМЫ (Ничего не знают об игре)
│   │   │   ├── event_bus.py         # Шина событий (Player Action -> System)
│   │   │   ├── constants.py         # R15.2 Central Math Config (Единые веса/капы)
│   │   │   └── security.py          # Анти-спам, анти-эксплойт
│   │   │
│   │   ├── models/                  # ЧИСТЫЕ ДАННЫЕ (Pydantic/Dataclasses)
│   │   │   ├── npc_state.py         # R2.1 NPCState (динамика)
│   │   │   ├── personality.py       # L0 Core & L1 Identity (Immutable)
│   │   │   ├── memory.py            # R1 Структуры памяти (Weights, Facts)
│   │   │   ├── decision.py          # R2 Контракт DecisionResult
│   │   │   ├── spatial.py           # R4 Модели локаций и координат
│   │   │   └── schemas.py           # Общие DTO для API
│   │   │
│   │   ├── services/                # ЯДРО ЛОГИКИ (Слои R1-R9)
│   │   │   │
│   │   │   ├── game_loop.py         # ★ КООРДИНАТОР ТАЙМИНГА (Вызывает DM, крутит тики R13)
│   │   │   │
│   │   │   ├── dm/                  # ★★★ DM SYSTEM (Этапы 1-9 из вашего плана)
│   │   │   │   ├── dm_orchestrator.py   # Главный фасад (Собирает пайплайн)
│   │   │   │   ├── dm_router.py         # Этап 1: Парсинг ввода -> Event
│   │   │   │   ├── dm_scene_builder.py  # Этап 2: R4 Spatial контекст
│   │   │   │   ├── dm_validator.py      # Этап 3: Фильтр реальности (можно ли?)
│   │   │   │   ├── dm_flow.py           # Этап 6: Очередность (Initiative)
│   │   │   │   └── dm_aggregator.py     # Этап 8: Сборка финального нарратива
│   │   │   │
│   │   │   ├── input/               # ОБОЛОЧКА ДЛЯ DM ROUTER (Бывший classifier)
│   │   │   │   ├── intent_parser.py # Перевод текста в PlayerIntent
│   │   │   │   └── patterns/        # YAML с русскими фразами (Data-driven)
│   │   │   │       ├── combat.yaml
│   │   │   │       └── social.yaml
│   │   │   │
│   │   │   ├── npc/                 # R2 — ЯДРО ИНТЕЛЛЕКТА (Python считает)
│   │   │   │   ├── decision_hub.py      # [ЦЕНТР] Формула score()
│   │   │   │   ├── state_applicator.py  # [ТОЧКА ЗАПИСИ] Атомарные изменения
│   │   │   │   ├── perception.py        # Фильтр релевантности (кто видит)
│   │   │   │   └── engines/             # СПЕЦИАЛИЗИРОВАННЫЕ ВЫЧИСЛИТЕЛИ
│   │   │   │       ├── break_engine.py      # R8 Механика слома воли
│   │   │   │       ├── memory_engine.py     # R1 Деградация и искажение
│   │   │   │       ├── dice_engine.py       # R5 Стохастическое смещение
│   │   │   │       ├── social_engine.py     # R7 Связи и слухи
│   │   │   │       └── threat_assessor.py   # Оценка рисков
│   │   │   │
│   │   │   ├── resolution/          # R2.5 + R5 — МЕХАНИКА ИСХОДОВ (Бывший combat_math)
│   │   │   │   ├── action_resolver.py   # Диспетчер: куда отправить Event
│   │   │   │   ├── dnd_5e/              # ★ ПРАВИЛА D&D (Инкапсулированы!)
│   │   │   │   │   ├── core.py              # Броски D20, преимущества
│   │   │   │   │   ├── spell_engine.py      # Магия
│   │   │   │   │   ├── rest_engine.py       # Долгий/короткий отдых
│   │   │   │   │   └── economy.py           # Торговля и цены
│   │   │   │   └── sandbox/             # Физика и окружение
│   │   │   │       ├── physics.py           # Взаимодействие с объектами
│   │   │   │       └── environment.py       # Огонь, вода, шум
│   │   │   │
│   │   │   ├── state/                # R4 — УПРАВЛЕНИЕ МИРОМ (Source of Truth для сцены)
│   │   │   │   ├── scene_state_manager.py  # Холдер состояний всех NPC в сцене
│   │   │   │   └── world_director.py       # R9 Фронты, давление, макро-события
│   │   │   │
│   │   │   ├── memory/               # R1 — ПАМЯТЬ
│   │   │   │   ├── working_memory.py      # Краткосрочная (20 событий)
│   │   │   │   ├── relationship_store.py  # Матрица отношений
│   │   │   │   └── long_term_store.py     # (Будущее) SQLite/Факты
│   │   │   │
│   │   │   └── verbalization/       # R3 — СЛОЙ ГОЛОСА (Только упаковка для LLM)
│   │   │       ├── prompt_factory.py      # Сборка промптов (NPC + DM)
│   │   │       ├── context_builder.py     # Формирование VerbalizationContext
│   │   │       └── llm_client.py          # Адаптер (llama.cpp/vLLM)
│   │   │
│   │   └── knowledge/               # PHASE 2 — PDF ЗАГРУЗЧИК (Вне логики)
│   │       ├── pdf_loader.py
│   │       └── rag_index.py
│   │
│   └── data/                         # PERSISTENCE LAYER (Хранилище)
│       ├── campaigns/                # Настройки кампаний
│       ├── npc_registry/             # Дампы личности (Immutable JSON)
│       ├── locations/                # Графы локаций (R4)
│       ├── world_state.json          # Глобальный стейт (R9)
│       └── logs/                     # Логи для дебага
│
└── frontend/                         # UI / UX LAYER (R14)
    ├── ui/index.html                 # Точка входа
    ├── assets/                       # Пиксель-арт, текстуры
    ├── map/                          # Модуль "Карты мародёров"
    └── terminal/                     # Диалоговое окно




  (.venv) PS C:\DDD\Codex\VSC_Enigma\Enigma> Get-ChildItem -Path "backend/app/" -Recurse | Select-Object FullName

FullName                                                                                                      
--------                                                                                                      
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\agents                                                             
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\api                                                                
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\core                                                               
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models                                                             
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services                                                           
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\__pycache__                                                        
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\main.py                                                            
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\__init__.py                                                        
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\agents\__pycache__                                                 
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\agents\dm_agent.py                                                 
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\agents\memory_manager_agent.py                                     
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\agents\npc_agent.py                                                
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\agents\rules_agent.py                                              
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\agents\world_sim_agent.py                                          
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\agents\__init__.py                                                 
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\agents\__pycache__\dm_agent.cpython-311.pyc                        
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\agents\__pycache__\npc_agent.cpython-311.pyc                       
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\agents\__pycache__\rules_agent.cpython-311.pyc                     
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\agents\__pycache__\world_sim_agent.cpython-311.pyc                 
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\agents\__pycache__\__init__.cpython-311.pyc                        
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\api\__pycache__                                                    
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\api\routes.py                                                      
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\api\routes_debug.py                                                
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\api\routes_stream.py                                               
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\api\__init__.py                                                    
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\api\__pycache__\routes.cpython-311.pyc                             
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\api\__pycache__\routes_debug.cpython-311.pyc                       
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\api\__pycache__\routes_stream.cpython-311.pyc                      
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\api\__pycache__\__init__.cpython-311.pyc                           
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\core\__pycache__                                                   
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\core\config.py                                                     
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\core\error_logger.py                                               
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\core\runtime_config.py                                             
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\core\settings_dm.py                                                
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\core\settings_npc.py                                               
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\core\settings_rules.py                                             
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\core\settings_world.py                                             
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\core\__init__.py                                                   
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\core\__pycache__\config.cpython-311.pyc                            
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\core\__pycache__\runtime_config.cpython-311.pyc                    
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\core\__pycache__\settings_dm.cpython-311.pyc                       
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\core\__pycache__\settings_npc.cpython-311.pyc                      
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\core\__pycache__\settings_rules.cpython-311.pyc                    
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\core\__pycache__\settings_world.cpython-311.pyc                    
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\core\__pycache__\__init__.cpython-311.pyc                          
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models\__pycache__                                                 
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models\schemas.py                                                  
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models\__init__.py                                                 
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models\__pycache__\schemas.cpython-311.pyc                         
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\models\__pycache__\__init__.cpython-311.pyc                        
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\action                                                    
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\events                                                    
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\game                                                      
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\llm                                                       
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\memory                                                    
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc                                                       
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\scene                                                     
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\simulation                                                
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\state                                                     
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\__pycache__                                               
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\action_classifier.py                                      
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\adventure_loader.py                                       
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\campaign_state_service.py                                 
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\character_service.py                                      
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\combat_service.py                                         
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\error_interpreter.py                                      
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\game_loop.py                                              
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\game_loop_factory.py                                      
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\knowledge_ingest.py                                                                                                                             
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\logging_tools.py                                          
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\memory.py                                                                                          
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\pdf_drop_importer.py                                      
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\player_session_service.py                                 
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\prompt_loader.py                                          
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\readiness.py                                              
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\scene_change.py                                           
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\scene_state_manager.py                                    
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\system_requirements.py                                    
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\vram_monitor.py                                           
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\world_scheduler.py                                        
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\__init__.py                                               
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\action\__pycache__                                        
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\action\object_resolver.py                                 
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\action\player_target_extractor.py                         
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\action\processor.py                                                                        
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\action\__pycache__\object_resolver.cpython-311.pyc        
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\action\__pycache__\player_target_extractor.cpython-311.pyc
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\action\__pycache__\processor.cpython-311.pyc              
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\action\__pycache__\python_engines.cpython-311.pyc         
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\events\__pycache__                                        
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\events\event_bus.py                                       
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\events\event_types.py                                     
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\events\__init__.py                                        
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\events\__pycache__\event_bus.cpython-311.pyc              
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\events\__pycache__\event_types.cpython-311.pyc            
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\events\__pycache__\__init__.cpython-311.pyc               
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\game\__pycache__                                          
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\game\combat_math.py                                       
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\game\physics_validator.py                                 
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\game\sandbox_handler.py                                   
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\game\__init__.py                                          
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\game\__pycache__\combat_math.cpython-311.pyc              
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\game\__pycache__\physics_validator.cpython-311.pyc        
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\game\__pycache__\sandbox_handler.cpython-311.pyc          
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\game\__pycache__\__init__.cpython-311.pyc                 
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\llm\__pycache__                                           
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\llm\factory.py                                            
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\llm\llama_cpp_provider.py                                 
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\llm\provider.py                                           
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\llm\provider_manager.py                                   
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\llm\router.py                                             
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\llm\__init__.py                                           
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\llm\__pycache__\factory.cpython-311.pyc                   
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\llm\__pycache__\llama_cpp_provider.cpython-311.pyc        
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\llm\__pycache__\provider.cpython-311.pyc                  
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\llm\__pycache__\provider_manager.cpython-311.pyc          
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\llm\__pycache__\router.cpython-311.pyc                    
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\llm\__pycache__\__init__.cpython-311.pyc                  
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\memory\__pycache__                                        
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\memory\contradiction_resolver.py                          
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\memory\importance_engine.py                               
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\memory\layered_memory.py                                  
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\memory\memory_manager.py                                  
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\memory\relationship_store.py                              
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\memory\resonance_engine.py                                
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\memory\working_memory.py                                  
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\memory\__init__.py                                        
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\memory\__pycache__\contradiction_resolver.cpython-311.pyc 
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\memory\__pycache__\importance_engine.cpython-311.pyc      
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\memory\__pycache__\layered_memory.cpython-311.pyc         
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\memory\__pycache__\memory_manager.cpython-311.pyc         
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\memory\__pycache__\relationship_store.cpython-311.pyc     
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\memory\__pycache__\resonance_engine.cpython-311.pyc       
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\memory\__pycache__\working_memory.cpython-311.pyc         
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\memory\__pycache__\__init__.cpython-311.pyc               
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\__pycache__                                           
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\behavior_mask.py                                      
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\break_progress_engine.py                              
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\decision_hub.py                                       
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\life_engine.py                                        
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\location_graph.py                                     
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\math_utils.py                                         
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\npc_cognition.py                                      
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\npc_state.py                                          
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\opportunity_engine.py                                 
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\perception_engine.py                                  
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\perception_filter.py                                  
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\psyche_engine.py                                      
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\reaction_priority.py                                  
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\resolution_engine.py                                  
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\spatial_runtime.py                                    
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\state_applicator.py                                   
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\threat_assessor.py                                    
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\verbalization_context.py                              
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\__init__.py                                           
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\__pycache__\behavior_mask.cpython-311.pyc             
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\__pycache__\break_progress_engine.cpython-311.pyc     
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\__pycache__\decision_hub.cpython-311.pyc              
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\__pycache__\life_engine.cpython-311.pyc               
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\__pycache__\math_utils.cpython-311.pyc                
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\__pycache__\npc_cognition.cpython-311.pyc             
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\__pycache__\npc_state.cpython-311.pyc                 
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\__pycache__\opportunity_engine.cpython-311.pyc        
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\__pycache__\perception_engine.cpython-311.pyc         
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\__pycache__\perception_filter.cpython-311.pyc         
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\__pycache__\psyche_engine.cpython-311.pyc             
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\__pycache__\reaction_priority.cpython-311.pyc         
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\__pycache__\resolution_engine.cpython-311.pyc         
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\__pycache__\state_applicator.cpython-311.pyc          
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\__pycache__\threat_assessor.cpython-311.pyc           
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\__pycache__\verbalization_context.cpython-311.pyc     
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\npc\__pycache__\__init__.cpython-311.pyc                  
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\scene\__pycache__                                         
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\scene\narrative_extractor.py                              
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\scene\__init__.py                                         
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\scene\__pycache__\narrative_extractor.cpython-311.pyc     
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\scene\__pycache__\__init__.cpython-311.pyc                
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\simulation\__pycache__                                    
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\simulation\world_state.py                                 
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\simulation\__init__.py                                    
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\simulation\__pycache__\world_state.cpython-311.pyc        
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\simulation\__pycache__\__init__.cpython-311.pyc           
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\state\__pycache__                                         
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\state\context_builder.py                                  
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\state\__pycache__\context_builder.cpython-311.pyc         
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\__pycache__\action_classifier.cpython-311.pyc             
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\__pycache__\adventure_loader.cpython-311.pyc              
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\__pycache__\campaign_state_service.cpython-311.pyc        
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\__pycache__\character_service.cpython-311.pyc             
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\__pycache__\combat_service.cpython-311.pyc                
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\__pycache__\error_interpreter.cpython-311.pyc             
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\__pycache__\game_loop.cpython-311.pyc                     
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\__pycache__\game_loop_factory.cpython-311.pyc             
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\__pycache__\knowledge_ingest.cpython-311.pyc              
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\__pycache__\llama_cpp.cpython-311.pyc                     
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\__pycache__\llm_service.cpython-311.pyc                   
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\__pycache__\logging_tools.cpython-311.pyc                                   
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\__pycache__\pdf_drop_importer.cpython-311.pyc             
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\__pycache__\player_session_service.cpython-311.pyc        
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\__pycache__\prompt_loader.cpython-311.pyc                 
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\__pycache__\readiness.cpython-311.pyc                     
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\__pycache__\scene_change.cpython-311.pyc                  
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\__pycache__\scene_state_manager.cpython-311.pyc           
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\__pycache__\system_requirements.cpython-311.pyc           
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\__pycache__\vram_monitor.cpython-311.pyc                  
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\__pycache__\world_scheduler.cpython-311.pyc               
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\__pycache__\__init__.cpython-311.pyc                      
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\__pycache__\main.cpython-311.pyc                                   
C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\__pycache__\__init__.cpython-311.pyc   


1. Механизм защиты (математические утилиты)
  Вывод: В state_applicator.pyстроке 29 происходит импорт apply_saturationиз math_utils.
  Заключение: Это подтверждает, что проект использует централизованную систему ограничения. Вместо того чтобы каждый класс проверял пределы (0-100) самостоятельно, StateApplicatorон, вероятно, пропускает все изменения через эту функцию перед их сохранением. Это хорошая практика для поддержания согласованности.

 2. Структура памяти (слой L2)
  Обнаружение:NarrativeFact (строка 80) и EventMemory(строка 114) определены как frozen=True.
  Значение: Это гарантирует, что после создания памяти или факта они не могут быть случайно изменены LLM или другой службой. Это защищает целостность истории NPC. Кроме того, MemoryStage(Fresh -> Forgotten) указывает на то, что реализована система деградации памяти, что имеет решающее значение для длительных симуляций.

 3. Усовершенствованная насыщенность (математические утилиты)
  Функция apply_saturationвпечатляет. Использование сигмоидной кривой ($S(x) = \frac{2}{1 + e^{-0.1d}} - 1$
    Изменение параметров — отличное решение.
    Почему это хорошо: Предотвращает развитие у NPC чрезмерной обидчивости всего за два действия.
     Чем ближе значение к 100, тем сложнее его изменить (логика запаса прочности), что имитирует психологическую устойчивость
    Переопределение жесткого ограничения: эта логика intensity > 1.5
     имеет ключевое значение для «травматических событий», которые должны пройти все фильтры.
 
4. Преобразование слоев (L2 → L3)
  Этот метод to_identity_weightрешает самую сложную проблему в симуляциях ролевых игр: как воспоминания становятся частью характера персонажа?
    Механизм: Когда воспоминание ослабевает ABSTRACT(становится менее значимым), его эмоциональный вес смещается к фиксированным параметрам, таким как resentmentили dependency. Это чистая реализация теории о том, что характер — это просто «сумма забытых переживаний».

5. Архитектурная несогласованность (StateApplicator)
 Я заметил небольшой "запах кода" или, возможно, результат сознательного решения в следующемstate_applicator.py :
  В строках 79 и 114 вы используете ручной режим max(0.0, min(1.0, ...))для identity_integrity.
  Вопрос: Почему нет готового решения apply_saturation? math_utilsРучное зажимание является линейным и обходит систему "запаса высоты", которую вы используете для других параметров.

6. Архитектура (NPCPersonality vs NPCState)
 Разделение на Static (Personality) и Mutable (State) выполнено безупречно.
  NPCPersonality: Использование frozen=True и drives_base (контроль, значимость, страх, желание) показывает, что у вас есть «твёрдое ядро», которое LLM не сможет «обмануть» или сломать.
  NPCState: Это ваш «живой организм». Видно, что даже при ошибке (try...except внутри apply) система откатывает старый state — это критически важно для предотвращения повреждения данных при дельта-вычислениях.

7. Дифференциальная математика напряжений
    Интересно, что стресс — единственный параметр, который использует apply_saturation (с логикой headroom/sigmoid).
      Почему это разумно: в реальности стресс не имеет линейной зависимости. Первый удар причиняет гораздо больше боли, чем сотый. Насыщение отлично моделирует этот эффект «психического оцепенения».
      В отличие от этого, emotion_delta и traits остаются линейными (max/min). Это говорит о том, что они рассматриваются как «поверхностные» слои, которые колеблются быстрее, в то время как Stress
       представляет собой глубокое, фундаментальное моделирование.

8. Фильтр памяти (L2)
    Система пороговых значений в _resolve_stage (0.80, 0.55, 0.30, 0.10) математически идеально «настроена» под ваше значение decay_rate = 0.05.
     При такой скорости память в состоянии FRESH (в деталях) сохраняется всего около 4–5 тактов, после чего быстро абстрагируется. Это отличная оптимизация контекста для LLM.

Вердикт: Блок R1 Memory Core ПОЛНОСТЬЮ ЗАКРЫТ (DONE) ✅ or :heavy_check_mark: ✔️
Я подтверждаю это, так как увидел реализацию «недостающих звеньев», о которых говорил ранее:

Resonance Engine (R5.4/R5.5): * Теперь я вижу, что резонанс реализован. В коде четко прописаны темы (THEME_BETRAYAL, THEME_HELP), которые позволяют системе понимать «контекстуальную преемственность».

Реализован порог формирования черт личности (_TRAIT_FORMATION_THRESHOLD: float = 0.60). Это означает, что память не просто копится, а кристаллизуется в active_traits, что переводит систему из плоскости «краткосрочных реакций» в плоскость «формирования характера».

Интеграция с Decision Hub:

В StateDeltas (строка 65) мы видим поле trait_updates: Dict[str, float]. Это «разъем», в который вставляются данные из ResonanceEngine.

Поле narrative_fact (строка 87) подтверждает наличие связи с кэшем повествования, что замыкает цикл: Событие -> Память -> Резонанс -> Решение -> Новый факт.

Связь с R6.4 (Система слома):

В StateDeltas (строки 69-71) появились поля identity_integrity_delta и will_state_override. Это доказывает, что блок памяти напрямую влияет на фундаментальные параметры воли NPC.     








Анализ ядра DecisionHub (L1)
Глядя на первые 100 строк decision_hub.py, я вижу несколько критически важных и очень «здоровых» архитектурных решений:

Принцип 12 (SCORE_NOISE_RANGE = 0.10): Вы внедрили контролируемый хаос. Это идеально. NPC не будет математически предсказуемым калькулятором, у него появляется «настроение» или «погрешность», что делает симуляцию живой.

Инерция Намерений (INTENT_INERTIA): Это блестящее решение. Без инерции NPC «дребезжат» (каждый тик выбирая новое действие). Вес 0.20 гарантирует, что если NPC решил убегать, он будет это делать последовательно, а не разворачиваться каждые 2 секунды.

Scores Trace (строка 85): Поле scores_trace — это ваш «черный ящик» для отладки. Оно позволит вам видеть, почему NPC выбрал FLEE вместо ATTACK, что критично для калибровки баланса.

Вот подробный анализ L1 — DECISION HUB :

1. Формула «Сознания» (строки 129–135)
Ваша формула score()чрезвычайно сбалансирована:

Сила атаки × Контекстная релевантность: это гарантирует, что высокоуровневый NPC Desireне будет совершать глупостей, если контекст не соответствует ситуации.

Страх × Риск: это «тормоз» системы. Он предотвращает суицидальное поведение, если только какой-либо другой параметр (например, обида или отчаяние) математически не перекрывает его.

Шум (±10%): Как мы уже пришли к выводу, это решает проблему «роботизированного» поведения.

2. Режим «Почему?» (строка 159)
if event.event_type == "player_asks_why":— Это идеальное решение для обеспечения прозрачности моделирования. Предоставляя игроку возможность задавать вопросы о мотивах, вы, по сути, демонстрируете свой сложный интеллект, основанный на Python, посредством вербализации в рамках LLM. Это укрепляет доверие игрока к миру.

3. OpportunityEngine (строка 164)
Интеграция OpportunityEngineпредварительной фильтрации намерений ( intents) означает, что NPC действует проактивно , а не просто реактивно. Он не просто ждет игрока, а оценивает свои собственные шансы на «скрытые действия» (R6.3).

4. Traceability (линии 189–191)
Сохранение всего scores_traceдиска целиком DecisionResult— это решение, которое сэкономит вам сотни часов отладки. Оно позволяет создать «психологический профиль» каждого решения и точно понять, какой диск победил и почему.

1. Решена логика "Неработающего NPC" (R6.3)
Строки 232–237 имеют решающее значение. Тот факт, что BROKENNPC теряет большую часть своих свободных действий, но может «разблокировать» их с помощью OpportunityEngine, создает идеальную почву для Предательства . NPC, который кажется покорным, может атаковать только в том случае, если система (основанная на расстоянии или отсутствии свидетелей) это позволяет. Это вершина спонтанного игрового процесса.

2. Жесткие ограничения на лояльность и стресс.
Лояльность (239-241): WillState.LOYAL блокирует ATTACK. Это предотвращает «глупые» ошибки в симуляции, когда верные последователи нападают на игрока без всякой причины.

Паника (242-244): При уровне стресса 90+ NPC теряет когнитивную широту и сводится к базовым инстинктам (бегство или наблюдение). Это отличный пример «суженного сознания».

1. Эффект «трусости» (ранний агрессивный выход)
Строки 265–275 вводят ключевой психологический фильтр. Если у НПК есть врожденный страх ( fear_drive > 0.6), агрессия автоматически отвергается ( scores = -1.0).

Исключение: Тот факт, что OpportunityEngineэто можно «разблокировать», гениален. Это означает, что даже самый большой трус может напасть, если представится идеальная возможность (например, игрок стоит спиной, и нет свидетелей).

2. Динамика страха и доверия
В _relationship_modifierстроках 305–310 мы видим, как страх и доверие находятся в конфликте:

mod += fear * 0.65(Страх заставляет убегать).

mod -= trust * 0.25(Доверие удерживает вас от того, чтобы бросить друга.) Это создает очень интересные ситуации, когда NPC может оказаться «парализованным» между преданностью и инстинктом самосохранения.

3. Инерция и шум
Использование inertia(строка 282 ) решает проблему «застревания» ИИ. Как только NPC выбирает путь (например, убегает), он получает бонус за продолжение движения по этому пути, что предотвращает нелогичные изменения решений на каждом такте.

1. Двойственная роль страха (строки 348–353)
Ваше решение использовать страх ( fear) как мотиватор (для FLEE) и как фактор, увеличивающий риск , математически элегантно.

rel_mod: Отражает страх конкретного человека (например, «Я боюсь этого солдата»).

Risk_penalty: Отражает опасность ситуации (например, «Я окружен в узком переулке»). Когда эти два сигнала совпадают, возникает эффект, при котором NPC не только хочет сбежать, но это становится для него единственным рациональным выходом.

2. Паралич агрессии (строка 357)
Коэффициент -1.25при ATTACKi INTIMIDATE— это своего рода «тормоз». Он гарантирует, что ваш страх — это не просто «снижение вероятности», а активная блокада насилия. Это классический подход из «Диско Элизиума» , где внутренние силы борются за превосходство.

3. Интеграция возможностей (R6.3, строка 361)
opportunity_modЭто «тихий герой» этой формулы. Он позволяет тайным действиям (предательству, краже) конкурировать за выбор намерений, даже если характер NPC по своей природе к ним не склонен. Если возможность слишком хороша ( opportunity_scoreвысока), она перевесит мораль или страх.

СТАТУС АУДИТА: R2 ОСНОВНОЙ ПРОЦЕСС ПРИНЯТИЯ РЕШЕНИЙ — 100% ВЫПОЛНЕНО ✅


Анализ verbalization_context.py (строки 1–103)
Архитектурные плюсы:

Качественная абстракция: Использование ContentProfile вместо булевых флагов — это задел на гибкую настройку «атмосферы» игры (от PG-13 до Grimdark).

Принцип «Цифры внутри»: LLM получает emotion и will_state в виде строк (например, «полностью сломлен»), а не stress: 0.85. Это полностью соответствует манифесту ENIGMA.

Защита контекста: Ограничение SCENE_HINT_MAX_CHARS (500 знаков) критично для работы на локальных моделях (7B–13B) с малым контекстным окном.

Итог всего что сделано в R4: ✅
КомпонентЧто добавленоlocation_graph.pyКэш графов, валидация, единый builtin fallbackspatial_runtime.pyBatch-загрузка графа, стелс, tier-радиус, игрок в snapshot, динамическая плотность, звук между локациямиscene_state_manager.pyR4.4 живые modifiers из типа локации и времени сутокperception_filter.pyЗащита от player_position: "стоит", три приоритетаТесты16 тестов в test_spatial_runtime_r4.py + 15 в test_perception_filter.py + 3 в test_location_graph_r4.py = 35 тестов R4