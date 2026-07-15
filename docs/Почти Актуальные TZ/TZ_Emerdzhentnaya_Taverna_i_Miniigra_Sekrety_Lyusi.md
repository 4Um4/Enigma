# ТЗ: Эмерджентная таверна — финальная интеграция и мини-игра «Секреты Люси»

**Адресат:** LLM-архитектор (преемник проекта)
**Автор:** создатель Enigma (человек-режиссёр, не программист)
**Дата:** 12 июля 2026
**Версия проекта:** Enigma V.0.5.3.4.3
**Документ-источник:** «ТЕХНИЧЕСКОЕ ЗАДАНИЕ Миниигра "Таверна Серебряный Волк".md» (в этой же папке)

---

## 0. ЧТО ЭТОТ ДОКУМЕНТ И ЗАЧЕМ

Этот документ — **единый план** на ближайшие 4-6 недель. Он объединяет три задачи:
1. Починить и соединить существующие файлы (две недели работы уже идут, нужно довести).
2. Достроить эмерджентный цикл «нужда → мысль → диалог → мнение → изменение → видимость».
3. Поверх этого запустить мини-игру «Секреты Люси» (ТЗ уже существует — см. документ-источник).

**Прежде чем начать — прочитай:**
- `docs/00_CAUSAL_CONTRACT_v2.0.md` — каузальный контракт
- `docs/АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md` — устав
- `docs/Tasks/ТЗ/03_KNOWN_ISSUES_AND_BUGS.md` — известные баги
- `docs/Диаграммы игры/ТЕХНИЧЕСКОЕ ЗАДАНИЕ Миниигра "Таверна Серебряный Волк".md` — ТЗ мини-игры
- `reports/history/2026-07-12_10-50.md` — последняя сессия (PFI=150%, CDS слеп)
- Свежий аудит проекта (если есть): `Enigma_V0.5.3.4.3_Audit_Report.docx`

---

## 1. ЖЕЛЕЗНОЕ ПРАВИЛО: НИКАКИХ СКРИПТОВ

Это **архитектурный закон**, а не пожелание.

**Что запрещено:**
- Скриптованные сцены вида «если NPC_A встретил NPC_B в локации X в интервале T → запустить диалог Y».
- Флаги «quest_lusya_met = true», «trigger_tavern_fight = true».
- Хардкоженные реплики NPC, привязанные к событиям.
- `ScriptedSceneRunner` с YAML-последовательностями действий.
- Любые условные конструкции, которые предопределяют **что именно** произойдёт.

**Что разрешено:**
- **Правила** — общие законы, из которых сцены **возникают**, а не задаются.
- **Drives** — внутренние нужды NPC (голод, страх, привязанность, любопытство), которые толкают к действию.
- **Реакции** — ответ PerceptionEngine на воспринятое событие, преобразованный через эмоции в новый intent.
- **Эмерджентные матчи** — детекторы типа «если два NPC в одном кластере и friction > порог → возможность DIALOGUE». Решение принимает DecisionHub через utility-скоринг, а не if-then.

**Тест правила:** если из системы можно удалить **конкретного** NPC или **конкретную** сцену — и она продолжит работать, но с другими драмами — правило соблюдено. Если удаление ломает игру — это скрипт.

---

## 2. КОНТЕКСТ: ЧТО УЖЕ ЕСТЬ

### 2.1. Подсистемы, которые СУЩЕСТВУЮТ и работают

- **TickOrchestrator** — 13 фаз game loop (`backend/app/services/tick_orchestrator.py`).
- **DecisionHub** — utility-скоринг на основе NPCState + Drives + EventContext (`backend/app/services/npc/decision_hub.py`).
- **LifeEngine** — расписания NPC, need-driven движение, random events (`backend/app/services/npc/life_engine.py`).
- **AffectiveIntegrator + EmotionTransition** — эмоции как leaky integrator (`backend/app/services/affective/`).
- **PerceptionEngine + InterpretationEngine** — восприятие событий NPC.
- **BeliefCrystallizationEngine + PatternDetector + CrystallizedBeliefStore** — формирование убеждений.
- **LayeredMemory + L1Chronicle + WorkingMemory** — память NPC (SQLite).
- **SocialEngine + ReputationEngine + RelationshipStore** — слухи, репутация, отношения (SSOT 0-100).
- **DialogueExecutor + TaskScheduler + DialogueMaterializer** — материализация реплик.
- **CombatSubscriber + ImpactEngine + InjuryProcessor** — боёвка.
- **WorldTickEngine.compute_proactive_decisions** — автономные решения NPC.
- **DmAgent + DMOrchestrator + DMRouter + R3 DIRECT MODE** — DM как единственный источник речи.
- **PlayerCognition pipeline** — 9 слоёв восприятия игрока.
- **Frontend**: top-down рендер, speech bubbles, journal (J), console (Ё), time scale (1-4), idle_tick 2-30 сек.

### 2.2. Подсистемы, которые СУЩЕСТВУЮТ, но НЕ ПОДКЛЮЧЕНЫ

Это **низковисящие фрукты** — substantial код уже написан, нужно только его вызвать.

| Файл | Что делает | Почему не работает | Действие |
|---|---|---|---|
| `backend/app/services/world/world_tick_engine.py` | autonomous NPC decisions | не вызывается в `idle_tick` | вызвать в `GameLoop.idle_tick` |
| `backend/app/services/world_scheduler.py` | world event orchestrator | заглушка `disabled_pending_phase6` | реализовать вызов WorldTickEngine |
| `backend/app/services/economy/transaction_engine.py` | транзакции NPC-NPC | не вызывается | подключить к TRADE intent в WorldTickEngine |
| `backend/app/services/economy/trade_resolver.py` | определение цены/товара | не вызывается | то же |
| `backend/app/services/economy/market_state.py` | динамика цен | не вызывается | то же |
| `backend/app/services/game/combat_math.py` | броски D&D 5e (512 строк!) | не вызывается | подключить к ImpactEngine |
| `backend/app/services/npc/role_transition.py` | смена профессии NPC | не вызывается | подключить к долгосрочной симуляции |
| `backend/app/services/npc/reaction_priority.py` | приоритеты реакций | не вызывается | подключить к PerceptionEngine |
| `backend/app/services/perception/perceptual_attention_service.py` | attention budget | не вызывается | подключить к perception pipeline |
| `backend/app/services/character/front_engine.py` + `front_applicator.py` | маски персонажа | мёртвая цепочка из 2 файлов | подключить или удалить |
| `backend/app/services/game_loop/npc_state_helpers.py` | apply_npc_state_updates | не вызывается | подключить к game_loop |
| `ChangeType.INVENTORY` | инвентарь игрока | заявлен, apply_changes не имеет ветки | реализовать ветку |

### 2.3. Главная боль: «мёртвая» таверна

Игрок заходит в таверну и видит:
- NPC двигаются по локации (LERP-интерполяция по расписанию).
- Время суток обновляется.
- Иногда `idle_pressure` events создают telegraph «Горан warn».

Игрок **не видит**:
- NPC-NPC диалогов (TaskScheduler запускается только при вербальном интенте от DecisionHub в player turn; в idle event_type=WORLD_TICK с intensity=0.3 — порог не проходит).
- NPC-NPC боёв (ATTACK отфильтрован из `proactive_intents`).
- Эмоций NPC (нет визуальных индикаторов).
- Распространения слухов (SocialEngine работает, но видимых последствий почти нет — max trust_delta = 0.05).
- Транзакций (TransactionEngine не вызывается).
- Событий без игрока (WorldScheduler — заглушка).

**Корень проблемы:** подсистемы написаны, но **не соединены в замкнутый цикл**. Цикл должен быть:

```
Нужда NPC → DecisionHub → Intent (DIALOGUE/ATTACK/TRADE/SEEK_COMFORT)
    ↓
DialogueExecutor / CombatSubscriber / TradeResolver
    ↓
Событие «NPC_A сказал/сделал X к NPC_B»
    ↓
PerceptionEngine(NPC_B) воспринимает
    ↓
InterpretationEngine(NPC_B) интерпретирует
    ↓
AffectiveIntegrator(NPC_B) обновляет эмоции
    ↓
WorkingMemory(NPC_B) добавляет эпизод
    ↓
BeliefAggregator(NPC_B) формирует belief о NPC_A
    ↓
RelationshipStore обновляет trust/fear
    ↓
На следующем токе DecisionHub(NPC_B) учитывает новые данные
    ↓  ←──── цикл замкнулся
```

Этот цикл должен работать **без ввода игрока** в `idle_tick`.

---

## 3. ЭТАП 0: КРИТИЧЕСКИЕ БАГИ (1-2 ДНЯ)

Сначала починить то, что **гарантированно крашит runtime**. Все эти баги — NameError, которые убивают целые endpoint-ы или recovery-path-ы.

### 3.1. Баги с указанием файлов и строк

| # | Файл | Строка | Что не так | Как починить |
|---|---|---|---|---|
| C1-C3 | `backend/app/api/routes.py` | 302, 325, 341 | `game_loop` используется, но не параметр функции | добавить `game_loop=Depends(get_game_loop)` |
| C4 | `backend/app/services/affect.py` | 284 | `replace` не импортирован на уровне модуля | `from dataclasses import replace` |
| C5 | `backend/app/services/affect.py` | 346-354 | `_action`, `_target` не определены | `_action = intent.action; _target = intent.target` |
| C6 | `backend/app/services/npc/state_applicator.py` | 599-617 | `npc_id` не параметр | `npc_id = state.npc_id` в начале |
| C7 | `backend/app/services/npc/state_applicator.py` | 210 | `_l1_events` не определён | инициализировать `_l1_events = []` перед циклом |
| C8 | `backend/app/services/game_loop/npc_state_helpers.py` | 112 | `loop` не передан в функцию | добавить параметр `loop` |
| C9 | `backend/app/services/world/time_skip_executor.py` | 353 | `start_tick` не определён | `start_tick = _tick` после строки 328 |
| C10 | `backend/app/services/game_loop/__init__.py` | 896-908 | `GameActionResponse` не импортирован в backend | импортировать или создать backend-аналог |
| C11 | `backend/app/services/game_loop/task_scheduler.py` | 108 | `DialogueRequest` импортирован локально | вынести `import` на module level |
| C12 | `backend/app/services/npc/expectation_store.py` | 79, 91 | `logger` и `math` не импортированы | `import math; logger = logging.getLogger(__name__)` |
| C13 | `backend/app/services/action/dm_router.py` | 258, 264 | `logger` не определён | `logger = logging.getLogger(__name__)` |
| C14 | `backend/app/services/verbalization/state_interpreter.py` | 190 | `logger` в except не определён | `import logging; logger = logging.getLogger(__name__)` |

### 3.2. Port mismatch — критический инцидент

Llama-server использует **четыре разных порта** в четырёх местах:
- `main.py:290` — стартует на **8181**
- `main.py:80` (`_restart_llama_server`) — перезапускает на **8080**
- `game_launcher.py:114` (`_kill_zombies`) — убивает только **8000** (uvicorn, не llama)
- `game_launcher.py:270` — exit cleanup убивает **8000 и 8080**
- `routes.py:132` — `/system/status` отдаёт `{"llm": 8080}`
- `settings.llama_cpp_server_url` — третий источник истины

**Действие:** ввести единый источник истины `settings.llama_cpp_port` и использовать его во всех 6 местах. При падении llama-server `_restart_llama_server` должен убивать процесс на том же порту, на котором он работал.

### 3.3. Утечки файловых дескрипторов

| Файл | Строка | Что утекает |
|---|---|---|
| `backend/app/main.py` | 93 | `_llama_stderr_file = open(...)` не закрывается в success path `_restart_llama_server` |
| `backend/app/main.py` | 305 | То же в `_background_llm_startup` — закрывается только на error path |
| `game_launcher.py` | 67 | `_subprocess_log = open(...)` не закрывается в `main()` |

**Действие:** обернуть в `with open(...) as f:` или закрыть в `finally:`.

### 3.4. Silent exception suppression — hotspot-файлы

Заменить все `except Exception: pass` на `logger.exception(...)` для сохранения traceback. Особое внимание:
- `backend/app/main.py:383-384`
- `backend/app/services/npc/l1_chronicle.py:71-72`
- `frontend/game_loop_bridge.py:299-300, 332-333`
- `frontend/character_select.py:395`
- `frontend/campaign_select.py:79`
- Все `except Exception as e: logger.warning(f"[B5-FIX] silent failure suppressed: {e}")` — заменить на `logger.exception()`.

### 3.5. Контрольная точка Этапа 0

После завершения:
- `pytest backend/tests/` — число failing должно упасть с 107 до <50.
- Запуск `python game_launcher.py` → New Game → ввести «привет» — игра не падает.
- Перезапуск llama-server (kill процесса вручную) — `_restart_llama_server` поднимает его на правильном порту.

**До прохождения этой контрольной точки — не переходить к Этапу 1.**

---

## 4. ЭТАП 1: СОЕДИНЕНИЕ СУЩЕСТВУЮЩИХ ПОДСИСТЕМ (5-7 ДНЕЙ)

Цель: **мир начинает тикать без игрока**. Все подсистемы из §2.2 вызываются в `idle_tick` и `player_turn`.

### 4.1. Подключить WorldTickEngine в idle_tick

**Файлы:** `backend/app/services/game_loop/__init__.py` (метод `idle_tick`), `backend/app/services/world/world_tick_engine.py`, `backend/app/services/world_scheduler.py`.

**Что сделать:**
1. В `GameLoop.idle_tick` после `phase_0_simulation` добавить вызов `world_tick_engine.compute_proactive_decisions(tick_ctx)`.
2. В `world_scheduler.py` заменить заглушку `disabled_pending_phase6` на реальный вызов `WorldTickEngine` + публикацию событий в EventBus.
3. Расширить `proactive_intents` в `WorldTickEngine` — добавить `ATTACK`, `STEAL`, `FLEE`, `TRADE`, `DIALOGUE`, `APPROACH`, `AVOID`.

**Принцип:** NPC теперь могут **сами** инициировать разговор, атаку, торговлю, бегство — без ввода игрока.

### 4.2. Подключить экономику

**Файлы:** `backend/app/services/economy/transaction_engine.py`, `trade_resolver.py`, `market_state.py`, `economy_tracker.py`, `backend/app/services/world/world_tick_engine.py`.

**Что сделать:**
1. В `WorldTickEngine.compute_proactive_decisions`: если NPC сгенерил intent=TRADE → вызвать `TradeResolver.resolve(npc, location, market_state)` → `TransactionEngine.execute_sale` → `EconomyTracker.record_income` (убрать TODO-заглушку).
2. Раз в TICKS_PER_DAY вызывать `MarketState.update_prices` на основе дневных транзакций.
3. `EconomicProfile` (gold, debt, needs) обновляется через `TransactionEngine`.

### 4.3. Подключить боёвку

**Файлы:** `backend/app/services/game/combat_math.py`, `backend/app/services/combat/impact_engine.py`, `injury_processor.py`, `backend/app/services/world/world_tick_engine.py`.

**Что сделать:**
1. В `ImpactEngine` использовать `combat_math.py` для бросков кубиков D&D 5e (вместо упрощённой математики, если сейчас так).
2. В `WorldTickEngine` убрать фильтр `if result.intent not in proactive_intents: continue` для ATTACK — теперь NPC могут атаковать друг друга без триггера игрока.
3. В `DecisionHub` добавить reactive trigger: если NPC видит врага (через `PerceptualKernel.threat_gradient > threshold`) — генерить ATTACK intent.

### 4.4. Подключить npc_state_helpers

**Файлы:** `backend/app/services/game_loop/npc_state_helpers.py`, `backend/app/services/game_loop/__init__.py`.

**Что сделать:** вызвать `apply_npc_state_updates` и `write_npc_memory` в соответствующей фазе game_loop. Сейчас функции есть, но не вызываются.

### 4.5. Подключить reaction_priority и perceptual_attention_service

**Файлы:** `backend/app/services/npc/reaction_priority.py`, `backend/app/services/perception/perceptual_attention_service.py`, `backend/app/services/perception/perception_projector.py`.

**Что сделать:**
1. `ReactionPriority` — использовать в `reaction_subscriber` для упорядочивания реакций NPC на события.
2. `PerceptualAttentionService` — использовать в `perception_projector` для attention budget (ограничение: NPC не может воспринять всё одновременно).

### 4.6. Контрольная точка Этапа 1

После завершения:
- Запустить игру, **ничего не вводить** 5 минут.
- **Ожидаемо:** за это время в таверне происходит хотя бы одно событие — NPC-NPC диалог, смена позиции, начало транзакции, или (реже) стычка.
- В `journal` (J) появляются записи.
- В логах `cds_backend.log` видны маркеры `DRF_EMIT`, `IDLE_TRACE`, `TRAV_CREATE_PRE`.
- `pytest` — число failing не растёт (должно даже падать).

**Если за 5 минут без ввода ничего не происходит — Этап 1 не пройден.**

---

## 5. ЭТАП 2: ЭМЕРДЖЕНТНЫЙ ЦИКЛ «НУЖДА → МНЕНИЕ» (10-14 ДНЕЙ)

Это **сердце всего проекта**. Цель: реализовать замкнутый цикл из §2.3, чтобы драма возникала из системы, а не из скриптов.

### 5.1. Шаг 2.1 — Мысли формируются из нужды (2-3 дня)

**Цель:** каждый NPC на каждом тике имеет **актуальный набор нужд**, и эти нужды **толкают** к intents.

**Что сделать:**

1. **Унифицировать нужды** в `DecisionHub`. Сейчас есть `NeedDrive` (hunger, shelter, social, income, security, cleanliness). Добавить:
   - `SEEK_COMFORT` — потребность в утешении при высокой `sadness` (>0.5) или `fear` (>0.6).
   - `SEEK_VENGEANCE` — потребность в мести при `anger` > 0.7 и наличии обидчика.
   - `SEEK_AFFINITY` — потребность в общении с тем, к кому `trust` > 60.
   - `AVOID_THREAT` — избегание того, к кому `fear` > 0.5.

2. **В `DecisionHub.compute`** добавить utility-функции для каждого нового drive. Например, для `SEEK_COMFORT`:
   ```
   utility_seek_comfort = sadness * 0.7 + fear * 0.5 + (1 - has_companion) * 0.3
   if utility_seek_comfort > SEEK_COMFORT_THRESHOLD:
       intent = APPROACH + DIALOGUE(tone=VENTING)
       target = argmax(relationship.trust for npcs_in_same_cluster)
   ```

3. **Тон реплик** — добавить в `DialogueRequest` поле `tone: enum(NEUTRAL, FRIENDLY, ANGRY, FLIRTY, VENTING, FEARFUL, MANIPULATIVE)`. В `prompt_loader` подставлять tone в системный промпт DM: «Ты {npc_name}. Ты чувствуешь {tone}. Говори соответственно».

4. **Тест:** запустить idle_tick 10 раз. В логах видно, что хотя бы один NPC сгенерил intent с `tone != NEUTRAL` на основе своего emotional_state.

### 5.2. Шаг 2.2 — Диалоги инициируются NPC-NPC (2-3 дня)

**Цель:** когда NPC_A хочет поговорить с NPC_B, **реально** происходит диалог — LLM генерирует реплику, она материализуется в сцене.

**Что сделать:**

1. В `DialogueExecutor` (или в новом `NpcDialogueService`) реализовать **полный цикл NPC-NPC диалога**:
   - NPC_A инициирует (через DecisionHub → `QueuedTask(DIALOGUE, owner=A, target=B, topic, tone)`)
   - `DialogueExecutor.execute(task)` — вызывает LLM с контекстом: profile_A, profile_B, current relationship, current emotion_A, topic, tone
   - LLM возвращает реплику A → публикуется в `EventBus` как `NPC_SAID_TO_NPC(speaker=A, listener=B, text, tone, topic)`
   - `DialogueMaterializer` создаёт `recent_dialogues` entry для фронтенда
   - **Цикл:** тот же процесс для B как ответ (с собственным tone, основанным на эмоциях B после восприятия реплики A)
   - Диалог может быть 2-4 реплики, потом `DialogueExecutor` завершает сессию

2. В `WorldTickEngine.compute_proactive_decisions` добавить детектор возможности диалога:
   - Для каждой пары NPC в одном кластере
   - Вычислить `dialogue_opportunity` = f(social_urge обоих, distance, relationship, recent_interaction_count)
   - Если `dialogue_opportunity > threshold` → `QueuedTask(DIALOGUE)`

3. **Тест:** запустить idle_tick 30 раз. В `recent_dialogues` видно хотя бы один NPC-NPC диалог с указанием tone.

### 5.3. Шаг 2.3 — Восприятие замыкается (2-3 дня)

**Цель:** когда NPC_A говорит NPC_B, **NPC_B реально это воспринимает** — эмоции меняются, memory обновляется, belief формируется.

**Что сделать:**

1. Создать подписчика `NpcDialogueSubscriber` на событие `NPC_SAID_TO_NPC`:
   ```
   on NPC_SAID_TO_NPC(speaker, listener, text, tone, topic):
       # Запустить perception pipeline для listener
       perceived = PerceptionEngine.perceive(listener, event)
       interpretation = InterpretationEngine.interpret(listener, perceived)
       AffectiveIntegrator.apply(listener, interpretation)  # обновляет эмоции
       WorkingMemory.append(listener, episode)
       RelationshipStore.update(listener, speaker, delta_trust, delta_fear)
       BeliefAggregator.aggregate(listener, episode)  # см. шаг 2.4
   ```

2. **Убедиться**, что `PerceptionEngine` уже работает на событиях NPC-NPC (не только player→NPC). Если нет — расширить.

3. **Проверить**, что `AffectiveIntegrator.apply` действительно меняет `emotional_state.sadness/anger/fear/joy` на основе `tone` реплики. Например:
   - tone=ANGRY от NPC_A к NPC_B → listener.sadness += 0.3, listener.anger += 0.2, trust[A→B] -= 5
   - tone=FLIRTY → listener.joy += 0.2, listener.embarrassment += 0.3, trust зависит от relationship
   - tone=VENTING → listener.empathy += 0.2, trust зависит от relationship

4. **Тест:** вручную вызвать `NPC_SAID_TO_NPC(speaker=Торнин, listener=Люся, tone=ANGRY, text="убери стол!")`. Проверить, что в следующем тике `Люся.emotional_state.sadness` выросла, `Люся.relationships[Торнин].trust` упал.

### 5.4. Шаг 2.4 — Мнения и убеждения формируются (2-3 дня)

**Цель:** после нескольких взаимодействий NPC **кристаллизует** мнение о другом NPC, и это мнение влияет на будущие решения.

**Что сделать:**

1. В `BeliefAggregator` (или новый `NpcBeliefAggregator`) реализовать формирование belief на основе эпизодов:
   - После каждого воспринятого эпизода проверять: образует ли он паттерн?
   - Паттерн = 3+ похожих эпизода за последние N тиков.
   - Пример: Люся 3 раза слышала, как Горан жалуется на Торнина → belief «Горан недоволен Торнином» (confidence=0.7).
   - Пример: Горан 3 раза видел, как Люся подходит к нему после ссоры с Торниным → belief «Люся ищет во мне утешение» (confidence=0.7).

2. В `PatternDetector` добавить детекторы:
   - `RepetitionDetector` — повтор одного и того же поведения N раз
   - `SequenceDetector` — A→B→C последовательность (например: «после ссоры с X, Y идёт к Z»)
   - `ContradictionDetector` — поведение противоречит заявленному отношению

3. В `CrystallizedBeliefStore` сохранять кристаллизованные beliefs. Они persistent (выдерживают save/load).

4. В `DecisionHub.compute` **обязательно** использовать кристаллизованные beliefs:
   - `decision_context.beliefs_about_target` — список beliefs о целевом NPC
   - Эти beliefs влияют на utility-функции (например, если belief «Люся влюблена в меня» и intent=DIALOGUE с Люсей → utility_tone_flirty += 0.3)

5. **Тест:** в одной сессии Luzя три раза обижается на Торнина и три раза идёт к Горану. Проверить, что в `CrystallizedBeliefStore` у Горана появилось belief «Люся ищет во мне утешение». На 4-й раз Горан сам инициирует разговор с Люсей.

### 5.5. Шаг 2.5 — Изменения видны игроку (2-3 дня)

**Цель:** игрок **видит** эмерджентную драму, а не угадывает её по логам.

**Что сделать (фронтенд):**

1. **Speech bubbles для NPC-NPC диалогов** — в `scene_renderer.py` рисовать speech bubble над говорящим NPC, когда `recent_dialogues` содержит NPC-NPC запись. Цвет края bubble зависит от tone:
   - NEUTRAL — серый
   - FRIENDLY — зелёный
   - ANGRY — красный
   - FLIRTY — розовый
   - VENTING — фиолетовый
   - FEARFUL — бледно-голубой
   - MANIPULATIVE — тёмно-фиолетовый

2. **Mood indicators** — маленькая иконка над головой NPC (20x20 px):
   - 😢 грусть (sadness > 0.5)
   - 😡 гнев (anger > 0.5)
   - 💗 влюблённость (joy + attraction)
   - 😨 страх (fear > 0.5)
   - 😴 усталость (fatigue > 0.7)
   - 💢 раздражение (annoyance > 0.6)
   - Если эмоция слабая — иконка полупрозрачная.

3. **Кинокамера** — мягкое приближение камеры (zoom 1.2x) к зоне конфликта. Триггер: `tone == ANGRY` или `tone == FLIRTY` в NPC-NPC диалоге. Возврат камеры через 5 секунд после конца диалога.

4. **Журнал наблюдений (клавиша Ё)** — в `player_perception.peripheral_cues` добавлять записи о видимых NPC-NPC взаимодействиях: «Торнин повысил голос на Люсю», «Люся подошла к Горану». Текст генерируется на основе `tone` и `topic` (НЕ раскрывает секреты — только наблюдаемые факты).

5. **Тест:** запустить игру, наблюдать 5 минут. Игрок должен увидеть:
   - Хотя бы один speech bubble с цветным краем (NPC-NPC диалог)
   - Хотя бы одну mood-иконку над NPC
   - Хотя бы одну запись в журнале наблюдений

### 5.6. Контрольная точка Этапа 2 — ТЕСТОВАЯ СЦЕНА «ТОРНИН → ЛЮСЯ → ГОРАН»

**Это главный тест всего проекта.**

Сценарий: запустить игру в 9:00 игрового времени. Торнин за стойкой, Люся убирает столы, Горан сидит с кружкой. Игрок **ничего не вводит**, только наблюдает.

**Ожидаемая эмерджентная драма (одна из возможных):**
1. Торнин (фрустрирован долгом перед гильдией, +need income, +stress) → DecisionHub генерит `DIALOGUE(tone=ANGRY, target=Люся, topic="уборка")`.
2. Торнин кричит на Люсю → `NPC_SAID_TO_NPC` event.
3. PerceptionEngine Люси → sadness += 0.4, anger += 0.2, trust[Торнин] -= 5.
4. На следующем тике DecisionHub Люси: `SEEK_COMFORT` utility > threshold (sadness высокая) → `APPROACH + DIALOGUE(tone=VENTING, target=Горан)`.
5. Люся идёт к Горану, жалуется.
6. PerceptionEngine Горана → формирует belief «Люся ищет во мне утешение».
7. На следующем тике DecisionHub Горана: `SEEK_AFFINITY` к Люсе повышен → `DIALOGUE(tone=FRIENDLY)`.
8. Игрок **видит**: speech bubbles с разными цветами, mood-иконки (😢 над Люсей сначала, потом 💗 над Гораном), камера подъезжает к сцене.

**Критерии успеха:**
- Все шаги 1-7 происходят **без ввода игрока**.
- В `cds_backend.log` видна цепочка: `DRF_EMIT(Торнин ANGRY)` → `PERCEIVE(Люся)` → `DRF_EMIT(Люся VENTING)` → `PERCEIVE(Горан)` → `BELIEF_CRYSTALLIZED` → `DRF_EMIT(Горан FRIENDLY)`.
- В журнале игрока (Ё) есть соответствующие записи.
- В `reports/history/<fresh>.md` записана эта сцена.

**Если сцена не возникает — Этап 2 не пройден.** Отладить: какой шаг не сработал? (использовать `causal_oscilloscope.py` для трассировки).

---

## 6. ЭТАП 3: МИНИ-ИГРА «СЕКРЕТЫ ЛЮСИ» (5-7 ДНЕЙ)

**ТЗ мини-игры уже существует** — см. документ-источник. Цель этого этапа — реализовать мини-игру **поверх** эмерджентной таверны из Этапа 2.

### 6.1. Что взять из существующего ТЗ

Все 11 разделов документа-источника остаются в силе:
- §2 TruthStateLayer — `TruthStateLoader`, `TruthSecret`, `TruthRelationship` (загрузка из `config/npc/individuals/*.json` + `village_relations.json`).
- §3 ExposureLayer — `ObservationLog`, `Observation` (5 типов наблюдений).
- §4 InferenceLayer — `PlayerBeliefModel`, `PlayerBelief` (строится неведомо для игрока).
- §5 BlackBoxPrinciple — никаких UI-проверок правильности.
- §6 EvaluationEngine — `EvaluationResult`, `SecretEvaluation`, `NpcEvaluation`.
- §7 EndScreen — таблица результата.
- §8 Интеграция с существующей архитектурой — таблица «что уже есть и используется».
- §9-11 — принципы, success metric, пример цикла.

### 6.2. Что нужно добавить к существующему ТЗ

1. **TruthStateLoader должен загрузить `origin_events` с `is_secret=True`** из конфигов NPC. Сейчас в `lusya.json` уже есть `origin_events` (lusya_basement, lusya_shadow_orders, lusya_orm_borko, lusya_borko_crush) — нужно их распарсить в `TruthSecret`.

2. **Каузальный граф строится из `tags` overlap** — `TruthStateLoader` автоматически создаёт `causal_links` на основе совпадения тегов между секретами разных NPC. Например, `lusya_basement.tags = ["basement", "thieves_guild"]` и `tornin_basement.tags = ["basement", "thieves_guild"]` → link.

3. **ObservationLog.feed_from(EventBus)** — подписаться на события:
   - `NPC_SAID_TO_NPC` → observation_type=dialogue или eavesdrop (если игрок в радиусе 3м)
   - `PLAYER_SAID_TO_NPC` → observation_type=dialogue
   - `PeripheralCue` → observation_type=visual_cue
   - `PLAYER_BLACKMAIL` (новый event) → observation_type=action_reaction + confidence=1.0
   - `WorldProjectionBuffer` rumor → observation_type=overheard_rumor

4. **PlayerBeliefModel.update_from_observation** — реализовать логику:
   - 3+ visual_cue о одном NPC → belief_type=character_assessment, confidence=0.4
   - 1 eavesdrop event → belief_type=relationship_suspected, confidence=0.5
   - NPC проговаривается в диалоге (LLM с намёком) → belief_type=secret_suspected, confidence=0.6
   - Игрок упоминает секрет в диалоге → confidence=0.9
   - Игрок шантажирует → confidence=1.0

5. **EndScreenRenderer** — фронтенд-экран на pygame после `ExitTrigger`. Таблица из §7.1 документа-источника.

### 6.3. Что нужно создать (новое)

| Компонент | Файл | Время |
|---|---|---|
| `TruthStateLoader` | `backend/app/services/minigame/truth_state_loader.py` | 2 часа |
| `ObservationLog` + EventBus subscriber | `backend/app/services/minigame/observation_log.py` | 2 часа |
| `PlayerBeliefModel` | `backend/app/services/minigame/player_belief_model.py` | 3 часа |
| `EvaluationEngine` | `backend/app/services/minigame/evaluation_engine.py` | 3 часа |
| `ExitTrigger` | `backend/app/services/minigame/exit_trigger.py` | 30 мин |
| `EndScreenRenderer` | `frontend/minigame_end_screen.py` | 3 часа |
| Клик-таргетинг NPC (для диалога) | `frontend/game_screen.py` | 2 часа |
| Eavesdrop mechanic (радиус подслушивания) | `frontend/game_screen.py` + `backend/app/services/spatial/spatial_query_service.py` | 2 часа |
| Blackmail action (через текстовый ввод «я знаю про X») | `backend/app/services/action/dm_router.py` | 2 часа |

### 6.4. Принципы мини-игры (повтор из документа-источника)

1. Игрок = наблюдатель системы, а не решатель квеста.
2. No real-time correctness feedback — игрок никогда не знает, прав ли он.
3. Truth ≠ Observed ≠ Inferred — три слоя строго разделены.
4. Evaluation is post-hoc only — сравнение с TruthState только при выходе.
5. NPCs operate independently — NPC не знает, что его оценивают.
6. **Causal continuity preserved** — NPC-NPC взаимодействия продолжаются, даже если игрок не наблюдает. Это критично: эмерджентная драма из Этапа 2 продолжается **параллельно** с мини-игрой.
7. Replay incentive = epistemic error — игрок возвращается за более точной моделью мира.

### 6.5. Контрольная точка Этапа 3

После завершения:
- Игрок заходит в таверну, проводит 30-60 минут, выходит.
- На экране результата — таблица с §7.1 документа-источника.
- Игрок раскрывает 5-10 секретов из 16 (при первой попытке).
- В логах `cds_backend.log` видно, что `PlayerBeliefModel` корректно обновлялся на основе действий игрока.
- При повторном заходе в таверну (новая игра) — отношения NPC и связи между секретами **другие** (из-за эмерджентности), игрок не может использовать прошлый опыт «напрямую».

---

## 7. ПРАВИЛА ДЛЯ LLM-АРХИТЕКТОРА

### 7.1. Дисциплина

1. **Не создавай новые подсистемы**, пока не подключены существующие. Сначала Этап 1, потом Этап 2, потом Этап 3.
2. **Не нарушай принцип «без скриптов»** (§1). Если хочется написать if-then для конкретной сцены — остановись и подумай, какое **правило** её заменит.
3. **Не удаляй существующие тесты**, даже failing. Сначала почини, потом удали если устарели.
4. **Не добавляй новые TODO** без оценки времени. Каждый TODO — это технический долг.
5. **После каждого этапа** — писать отчёт в `reports/history/<date>.md` (по существующему шаблону).

### 7.2. Работа с кодом

1. **Перед любым изменением** — читать `worklog.md` (если есть) и последние 2-3 отчёта из `reports/history/`.
2. **После любого изменения** — добавлять запись в `worklog.md` (см. шаблон в `АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md`).
3. **Не делать больших рефакторингов** без явного разрешения. Если хочется переименовать модуль — оставить старый как deprecated alias.
4. **Сохранять совместимость** с существующими конфигами (`config/npc/individuals/*.json`, `village_relations.json`, `factions.json`). Если нужна новая схема — расширять, не ломать.
5. **Все новые поля в DTO** — optional с дефолтом, чтобы старые сохранения грузились.

### 7.3. Принципы эмерджентности

1. **Правила, не сценарии.** Если можно описать поведение как `if X then Y` для конкретного X — это скрипт. Опиши как `utility = f(X)` для общего случая.
2. **Drives, not commands.** NPC не «идёт к Горану», а «чувствует SEEK_COMFORT, который повышает utility подхода к тому, у кого trust высокий».
3. **Reactions, not triggers.** NPC не «реагирует на ссору», а «воспринимает событие, интерпретирует его, обновляет эмоции, на следующем тике принимает решение с учётом новых эмоций».
4. **Beliefs, not flags.** Вместо `quest_lusya_met = true` — `belief(«я встречал Люсю», confidence=0.9, supporting_observations=[5,12,18])`.
5. **Patterns, not sequences.** Вместо «сначала A, потом B, потом C» — детектор паттернов, который кристаллизует belief после N повторений.

### 7.4. Что делать, если что-то не работает

1. **Сначала отладка** — `causal_oscilloscope.py`, `diagnostics/causal_observer.py`, `cds_backend.log`. Понять, на каком шаге цикл разорвался.
2. **Потом минимальный фикс** — изменить одну строку, проверить.
3. **Не переписывать модуль целиком**, если не работает одна функция.
4. **Если уверен, что нужен рефакторинг** — описать в `worklog.md`, ждать ревью.

---

## 8. КОНТРОЛЬНЫЕ ВОПРОСЫ ДЛЯ САМОПРОВЕРКИ

После каждого этапа ответь на эти вопросы. Если хотя бы на один ответ «нет» — этап не пройден.

### После Этапа 0:
- [ ] `python game_launcher.py` запускается без краша?
- [ ] POST `/api/game/{id}/input` возвращает 200, а не 500?
- [ ] `pytest backend/tests/` — failing < 50?
- [ ] Llama-server перезапускается на правильном порту после kill?

### После Этапа 1:
- [ ] За 5 минут без ввода игрока в таверне происходит хотя бы одно событие (видимое в логах или на экране)?
- [ ] `WorldTickEngine.compute_proactive_decisions` вызывается в `idle_tick`?
- [ ] В `proactive_intents` есть ATTACK, STEAL, FLEE, TRADE, DIALOGUE?
- [ ] `TransactionEngine.execute_sale` вызывается хотя бы раз за игровой день?

### После Этапа 2:
- [ ] **Тестовая сцена «Торнин → Люся → Горан»** возникает без ввода игрока?
- [ ] В `cds_backend.log` видна цепочка `DRF_EMIT → PERCEIVE → DRF_EMIT → BELIEF_CRYSTALLIZED → DRF_EMIT`?
- [ ] На фронтенде видны speech bubbles с цветными краями для NPC-NPC диалогов?
- [ ] Mood-иконки над NPC обновляются при изменении эмоций?
- [ ] В журнале (Ё) есть записи о видимых NPC-NPC взаимодействиях?
- [ ] В `CrystallizedBeliefStore` после 30 тиков есть хотя бы одно belief, возникшее из паттерна?

### После Этапа 3:
- [ ] `TruthStateLoader` загружает 16 секретов из конфигов NPC?
- [ ] Каузальный граф строится из `tags` overlap (20 связей)?
- [ ] `ObservationLog` заполняется из EventBus-событий?
- [ ] `PlayerBeliefModel` обновляется на основе наблюдений и действий игрока?
- [ ] `ExitTrigger` срабатывает при выходе из `location_id='tavern_silver_wolf'`?
- [ ] `EndScreenRenderer` показывает таблицу из §7.1 документа-источника?
- [ ] При повторной игре отношения NPC и связи между секретами **другие** (из-за эмерджентности)?

---

## 9. ОЖИДАЕМЫЙ РЕЗУЛЬТАТ ЧЕРЕЗ 4-6 НЕДЕЛЬ

Если все этапы пройдены:

1. **Игрок заходит в таверну** и видит живой мир: NPC разговаривают друг с другом (speech bubbles с разными цветами), у них меняются эмоции (mood-иконки), возникают конфликты и примирения.

2. **Игрок наблюдает** за Торнином, который сам, без скрипта, накричал на Люсю из-за стресса. Видит, как Люся с грустной иконкой над головой идёт к Горану. Видит, как Горан отвечает ей дружелюбно, и у него над головой появляется 💗.

3. **Игрок пытается разгадать** отношения: подслушивает, наблюдает за micro-expressions, пытается шантажировать Люсю. Система запоминает каждое его действие и обновляет `PlayerBeliefModel` неведомо для него.

4. **Игрок выходит из таверны** — и видит экран результата: «7 из 16 секретов раскрыто, 2 ошибочных вывода, каузальный граф 40%, методы: 12 наблюдений + 8 диалогов + 3 подслушивания + 1 шантаж».

5. **Игрок хочет переиграть** — потому что понимает, что в новой сессии драма будет **другой**: у Люси может быть другой любимый, у Торнина — другая фрустрация, у Горана — другое отношение к Люсе. И он хочет построить более точную модель мира.

**Это и есть «живая игра».**

---

## 10. ФИНАЛЬНАЯ МЫСЛЬ

Этот проект — не «игра с NPC». Это **эмерджентная симуляция социальной драмы**, замаскированная под игру. NPC не «выполняют роли» — они **живут**. Игрок не «решает квесты» — он **наблюдает и реконструирует**.

Если ты, LLM-архитектор, сделаешь всё по этому ТЗ — у тебя будет нечто, чего не сделал никто в инди-RPG. Если соблазнишься скриптами — получится очередная «Skyrim с AI-диалогами», и игрок пройдёт её за вечер.

**Выбирай первое.**

---

**Конец документа.**

*Документ создан 12 июля 2026 г. как обобщение аудита проекта, ТЗ мини-игры «Секреты Люси» и видения создателя. Все ссылки на файлы актуальны на момент создания.*
