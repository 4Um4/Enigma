Текущее состояние проекта

Сейчас архитектура:

Player
  ↓
GameOrchestrator.run_turn()
  ↓
RulesAgent (future)
NpcAgent (future)
WorldScheduler (tick)
  ↓
DmAgent
  ↓
Memory write

То есть pipeline фактически:

Player → Rules + NPC + World → DM → Memory

Это уже почти правильная мультиагентная система.

В коде видно:

rules_future = self.pool.submit(self.rules_agent.evaluate_actions, req.actions)
npc_future = self.pool.submit(self.npc_agent.react, ...)

И:

dm_result = self.dm_agent.narrate(...)

То есть:

✔ RULES
✔ NPC
✔ WORLD
✔ DM
✔ MEMORY

все агенты уже есть.

2️⃣ Главные проблемы текущей реализации
❌ 1. Используется только одна модель

Это видно из логов:

switch_to_agent(dm) -> model=qwen_7b

Но остальные агенты не переключают модель.

Причина:

active_model = self.llm_manager.switch_model(req.model)

Это один switch на весь ход.

То есть:

rules_agent → DM model
npc_agent → DM model
world_agent → DM model
❌ 2. Нет Lazy Switching между агентами

А должно быть:

rules → saiga
npc → npc_llm
world → qwen9b
dm → qwen7b
memory → saiga
❌ 3. Нет streaming генерации

Ответ приходит одним блоком.

Игрок ждёт 10–20 секунд без обратной связи.

❌ 4. World Simulation почти не используется

Сейчас:

world_tick_meta = self.world_scheduler.maybe_tick(...)

Но LLM world_agent не вызывается.

❌ 5. Нет очереди агентов

Все агенты запускаются одновременно:

ThreadPoolExecutor

Но GPU модель может быть только одна.

3️⃣ Целевая архитектура (как должно работать)

Это финальная архитектура проекта.

PLAYER ACTION
     ↓
RULES AGENT (Saiga)
     ↓
WORLD SIM (CPU logic + Qwen9B when needed)
     ↓
NPC AGENT (NPC LLM)
     ↓
DM AGENT (Qwen7B)
     ↓
MEMORY AGENT (Saiga)
Частоты агентов
Агент	Частота	Модель
DM	каждый ход	Qwen 7B
NPC	каждый ход	NPC LLM
RULES	каждый ход	Saiga
WORLD	иногда	Qwen 9B
MEMORY	каждый ход	Saiga
4️⃣ ТЗ: изменение orchestrator.py

Главная задача:

переключать модель перед каждым агентом.

Сейчас
active_model = self.llm_manager.switch_model(req.model)
Должно быть
self.llm_manager.switch_to_agent("rules")
rules_result = self.rules_agent.evaluate_actions(...)

self.llm_manager.switch_to_agent("npc")
npc_result = self.npc_agent.react(...)

self.llm_manager.switch_to_agent("world")
world_result = self.world_agent.simulate(...)

self.llm_manager.switch_to_agent("dm")
dm_result = self.dm_agent.narrate(...)

self.llm_manager.switch_to_agent("memory")
self.memory_manager.update(...)
5️⃣ ТЗ: LlmManager

Нужно добавить agent → model mapping.

Конфиг моделей
dm → qwen2.5-7b
npc → npc-llm
rules → saiga
memory → saiga
world → qwen3.5-9b
Новый метод
def switch_to_agent(self, agent_name):

Пример:

AGENT_MODEL_MAP = {
    "dm": "qwen_7b",
    "npc": "npc_llm",
    "rules": "saiga",
    "memory": "saiga",
    "world": "qwen_9b",
}
6️⃣ ТЗ: Streaming

FastAPI поддерживает streaming.

Нужно изменить endpoint:

POST /api/game/action
Сейчас
return ChatTurnResponse(...)
Нужно
StreamingResponse(generator())
Генератор
def stream_dm_response(prompt):
    for token in llm.generate_stream(prompt):
        yield token
UI эффект

Игрок видит:

DM:
...
...
...
День проходит под непрекращающимся дождём...
7️⃣ ТЗ: World Simulation

LLM не должен считать мир каждый ход.

WORLD SIM должен быть:

90% алгоритмы
10% LLM
CPU logic
weather
npc travel
event timers
economy
LLM используется для
создание новых событий
описание катастроф
динамические квесты
Snapshot системы

Каждая локация:

world_snapshots/
   frosthill.json
   dungeon_1.json

Пример:

{
 "location": "Frosthill",
 "weather": "rain",
 "npcs": ["alexander", "innkeeper"],
 "events": ["strange lights"]
}
8️⃣ ТЗ: очередь агентов

GPU модель только одна.

Поэтому pipeline должен быть последовательным.

rules
world
npc
dm
memory

ThreadPoolExecutor лучше убрать для LLM.

9️⃣ ТЗ: NPC уровни

Твои модели:

тип	модель
важные NPC	NPC LLM Q4_K_M
массовые NPC	NPC LLM IQ4_XS

NPC agent должен выбирать модель:

if npc.importance == "major":
    model = npc_llm
else:
    model = npc_fast
🔟 Оптимизация VRAM

Lazy loading уже есть.

Но нужно добавить model cache.

last_used_model

Если модель уже в VRAM:

skip reload
11️⃣ Итоговое состояние системы

После исправления:

PLAYER
 ↓
RULES (saiga)
 ↓
WORLD (cpu + qwen9b)
 ↓
NPC (npc llm)
 ↓
DM (qwen7b streaming)
 ↓
MEMORY (saiga)
12️⃣ Roadmap разработки
Шаг 1 (срочно)

Исправить switch_model → switch_to_agent

Шаг 2

Streaming ответа DM.

Шаг 3

Убрать ThreadPool для LLM.

Шаг 4

World snapshot система.

Шаг 5

NPC уровни моделей.