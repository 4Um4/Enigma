Ты подошёл к точке, где проект уже не нужно чинить кусками — его нужно зафиксировать архитектурно.
Сейчас у тебя работает много правильных компонентов, но между ними нет инженерного каркаса. Поэтому появляются симптомы:

PowerShell ломает запросы

API иногда не совпадает со схемами

агенты могут падать

orchestrator перегружен

порты/сессии/кампании не имеют единого жизненного цикла

LLM может блокировать поток

Это не баги.
Это отсутствие системной спецификации проекта.

Поэтому ниже — реальное техническое задание на стабилизацию системы.

ТЗ: Стабилизация архитектуры AI-DM Engine
1. Зафиксировать топологию системы

Сейчас логика расползлась.

Нужно зафиксировать единственную схему:

Client
   │
   │ HTTP
   ▼
FastAPI
   │
   ▼
GameOrchestrator
   │
   ├── RulesAgent
   ├── NPCAgent
   ├── WorldSimulationAgent
   ├── MemoryManagerAgent
   └── DMAgent
            │
            ▼
        LlmManager
            │
            ▼
        llama.cpp

Важно

LLM не должен вызываться напрямую нигде кроме:

LlmManager
2. Жизненный цикл игры (Game Loop)

Сейчас он размазан.

Нужно зафиксировать pipeline:

TURN PIPELINE

1 игрок → action
2 rules_agent → проверка правил
3 npc_agent → реакция NPC
4 world_scheduler → события мира
5 dm_agent → финальная наррация
6 memory_manager → запись

Это у тебя уже почти реализовано.

Ключевой принцип:

DM = финальный синтез

DM не должен зависеть от стабильности других агентов
поэтому твой safe_future_result — правильный шаг.

3. Исправить LlmManager (критический дефект)

В текущем коде есть скрытая проблема.

Ты переключаешь модель каждый раз:

model_selection = self.switch_for_agent(agent_name)

Это может:

перезагружать модель

блокировать поток

ломать кэш

Нужно изменить
router.switch_to_agent → только если модель не активна

Иначе:

return cached_model
4. Предзагрузка моделей

Сейчас ты делаешь:

DM preload

Но остальные агенты нет.

Нужно:

PRELOAD:
DM
RULES
NPC
WORLD

в orchestrator init.

for agent in ["dm","rules","npc","world"]:
    self.llm_manager.get_default_model_for_agent(agent)
5. Ограничение потоков

Сейчас:

ThreadPoolExecutor(max_workers=max(2, settings.orchestrator_workers))

Но LLM нельзя запускать параллельно бесконтрольно.

Поэтому:

rules_agent → thread
npc_agent → thread
world → scheduler
dm_agent → single

DM не должен быть параллельным.

6. Убрать системную проверку железа

Ты спрашивал ранее.

В settings:

enforce_system_requirements = false

или просто удалить вызов:

self._assert_requirements()

в run_turn.

7. Порты (правильная инженерная схема)

Не нужно:

искать редкие порты

перебирать их

Это антипаттерн.

Используется фиксированная топология:

FastAPI        8000
Ollama         11434
llama.cpp      8080
Frontend       3000

Если только локально:

8000 достаточно
8. Стабилизация API

Нужно зафиксировать 3 эндпоинта:

создание кампании
POST /api/campaign/load
действие игрока
POST /api/game/turn
состояние игры
GET /api/session/state

Это весь API.

9. Минимальный тестовый сценарий

Чтобы система считалась рабочей:

шаг 1
load_campaign
шаг 2
create_character
шаг 3
run_turn
10. Минимальный action

Пример запроса:

$body = @{
  campaign_id = "demo"
  world_id = "world1"
  location = "tavern"
  actions = @(
    @{
      player_name = "Arin"
      action = "look around"
      dice_result = $null
    }
  )
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/game/turn" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body
11. Критическая архитектурная проблема проекта

Она одна.

orchestrator стал слишком умным

Он:

проверяет систему

управляет памятью

управляет агентами

запускает world tick

пишет журнал

Это 5 ролей.

Правильно:

GameEngine
 ├ Orchestrator
 ├ MemoryService
 ├ WorldScheduler
 └ AgentManager

Но это второй этап рефакторинга.

12. План действий (пошаговый)
Шаг 1

убрать system_requirements

Шаг 2

зафиксировать API

Шаг 3

предзагрузить модели

Шаг 4

проверить run_turn pipeline

Шаг 5

написать 3 PowerShell теста

load_campaign
create_character
run_turn
Шаг 6

проверить стабильность 10 ходов подряд