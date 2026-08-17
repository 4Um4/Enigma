# ТЗ: Semantic Unification — S199…S203

**Проект:** ENIGMA
**Версия:** V.0.5.3.8.1 → V.0.5.4.0
**Эпоха:** 6 (финальная фаза — закрытие центрального архитектурного долга)
**Дата:** 2026-08-17
**Автор концепции:** внешний архитектор (архивный разбор V.0.5.3.8.1)
**Исполнитель:** соло-разработчик ENIGMA

---

## 0. Контекст и главная находка

### 0.1. Что обнаружено в архиве

В проекте **уже существует** почти весь фундамент семантического слоя, который требуется для превращения свободного текста игрока в каузальные события мира:

| Компонент | Файл | Статус |
|---|---|---|
| `IntentCompressor` (Fast Path + LLM Slow Path) | `backend/app/services/input/intent_compressor.py` | ✅ production |
| `IntentSemanticField` (actor_reference, target_reference, target_zone, physical_force, emotional_charge, social_pressure, commitment_level) | `backend/app/models/` | ✅ production |
| `ConfidenceVector`, `EmotionalVector` | `backend/app/models/` | ✅ production |
| Fuzzy target resolution | `backend/app/services/npc/social_target_resolver.py` | ✅ production |
| `DialogueSession` + STM + thread continuity | `backend/app/services/memory/`, `test_dialogue_thread_continuity.py` | ✅ partial |
| `SpeechScheduler`, `TaskScheduler`, `DialogueExecutor`, `DialogueMaterializer` | `backend/app/services/execution/` | ✅ production |
| `COMMUNICATION_CLAIM` event + `ClaimEventSubscriber` + `EpistemicStore` | `backend/app/services/events/`, `backend/app/services/npc/epistemic_store.py` | ✅ production (доказано SUPERBOX-002…014) |
| `EventBus` + observer/subscriber architecture | `backend/app/services/events/event_bus.py` | ✅ production |

### 0.2. Главная проблема — раздвоение semantic authority

В `GameLoop._execute_dm_and_intent_resolution()` одновременно выполняются **две конкурирующие системы** понимания игрока:

```
            PLAYER TEXT
                  │
        ┌─────────┼──────────┐
        ▼         ▼          ▼
   DMRouter   IntentCompressor   ActionSemanticResolver
        │         │              │
        ▼         ▼              ▼
   action_type  IntentField    PlayerAction
        │         │              │
        └────┬────┴──────┬───────┘
             ▼           ▼
         GameLoop    MvpTavernController
                     → ActionConsequenceCompiler
                     → NpcConfessionParser
```

`IntentCompressor` — **уже LLM semantic compiler**. Он различает ATTACK / THREATEN / PERSUADE / FLIRT / MOVE / OBSERVE / INTERACT / STEAL / GIVE через Slow Path LLM и ConfidenceVector для Fast Path. Свободный текст игрока «Если будешь себя хорошо вести, я помогу тебе выбраться отсюда» он классифицирует как PERSUADE, хотя слова «уговорить» в тексте нет.

`ActionSemanticResolver` — **30 строк keyword-matching** (`if "шантаж" in raw_lower: BLACKMAIL`), параллельно маршрутизирующий текст в `MvpTavernController` и `ActionConsequenceCompiler`. Это legacy Эпохи 5, оставшийся после достройки MVP-миниигры «Серебряный Волк».

### 0.3. Вердикт

**Не создавать новый Intent Layer. Ликвидировать раздвоение существующего.**

Это одновременно меньше работы (всё уже есть) и глубже изменение (унификация semantic authority в одной точке входа).

---

## 1. Фундаментальное ограничение текущего IntentSemanticField

`IntentCompressor` сейчас сворачивает текст в **одно действие**. Но игрок говорит:

> «Послушай, если будешь себя хорошо вести, я помогу тебе сбежать отсюда.»

Это **не** просто `PERSUADE`. Это одновременно:

- `speech_act = OFFER`
- `social_intent = PERSUADE`
- `proposition = "I will help you escape"`
- `condition = "if you cooperate"`
- `goal = obtain cooperation`
- `target = Lusya`

Текущий `IntentSemanticField` для этого недостаточно выразителен. Расширять `ActionType` ещё 10–15 значениями — неверный путь: проблема не в количестве действий, а в **семантической многомерности одного высказывания**.

---

## 2. Целевой контракт: расширенный IntentSemanticField

### 2.1. Текущая структура

```
IntentSemanticField
├── action_type
├── actor_reference
├── target_reference
├── physical_force
├── emotional_charge
├── social_pressure
└── commitment_level
```

### 2.2. Целевая структура (S199)

```
IntentSemanticField
├── action                    # канонический IntentDTO.action
├── actor                     # resolved actor (player / npc_id)
├── target                    # resolved target (npc_id / object_id / zone)
│
├── speech_act                # SpeechAct enum (см. §3)
├── proposition               # Optional[Proposition] — semantic content
├── social_intent             # SocialIntent enum (см. §3)
├── requested_outcome         # что игрок хочет получить
├── offered_outcome           # что игрок предлагает
├── condition                 # Optional — условие («если будешь хорошо вести»)
│
├── references                # анафора, coreference («он», «это», «тот самый»)
├── conversation_continuation # CONTINUE / NEW_TOPIC / RETURN_TO / CLARIFY
├── dialogue_thread           # id активного thread из DialogueSession
│
├── physical_force            # 0.0-1.0 — сохраняется из текущего поля
├── emotional_charge          # 0.0-1.0 — сохраняется
├── social_pressure           # 0.0-1.0 — сохраняется
└── confidence                # ConfidenceVector — сохраняется из Fast/Slow Path
```

### 2.3. Принципы

1. **Один DTO, не двадцать классов.** Всё в одном frozen dataclass.
2. **Обратная совместимость.** Старые поля (`action_type`, `actor_reference`, `target_reference`, `physical_force`, `emotional_charge`, `social_pressure`, `commitment_level`) сохраняются как deprecated aliases на 1 эпоху, потом удаляются.
3. **Optional-семантика.** Все новые поля — `Optional[...] = None`. Fast Path заполняет только базовое; Slow Path LLM заполняет полное.
4. **Frozen.** Dataclass должен быть `frozen=True` — это соответствует архитектурному принципу Pure Reducer (ADR-TZ10-1).

---

## 3. Перечисления: SpeechAct и SocialIntent

### 3.1. SpeechAct (речевой акт)

Основано на Searle's Speech Act Theory, адаптировано под ENIGMA:

```python
class SpeechAct(str, Enum):
    ASSERT       = "assert"        # утверждение
    QUESTION     = "question"      # вопрос
    REQUEST      = "request"       # просьба
    ORDER        = "order"         # приказ
    OFFER        = "offer"         # предложение
    PROMISE      = "promise"       # обещание
    THREAT       = "threat"        # угроза
    APOLOGY      = "apology"       # извинение
    COMPLIMENT   = "compliment"    # комплимент
    INSULT       = "insult"        # оскорбление
    ACCUSATION   = "accusation"    # обвинение
    GREETING     = "greeting"      # приветствие
    FAREWELL     = "farewell"      # прощание
    CONTINUE     = "continue"      # «продолжай», «ну?», «и?»
    CLARIFY      = "clarify"       # «не это я имел в виду»
    REJECT       = "reject"        # отказ
    ACCEPT       = "accept"        # согласие
```

### 3.2. SocialIntent (социальное намерение)

Не путать с `SpeechAct` — это **каузальная цель**, а не лингвистическая форма:

```python
class SocialIntent(str, Enum):
    OBTAIN_INFORMATION   = "obtain_information"
    OBTAIN_COOPERATION   = "obtain_cooperation"
    OBTAIN_COMPLIANCE    = "obtain_compliance"     # через угрозу
    REPAIR_RELATIONSHIP  = "repair_relationship"
    BUILD_RAPPORT        = "build_rapport"
    INTIMIDATE           = "intimidate"
    FLIRT                = "flirt"
    COMFORT              = "comfort"
    DECEIVE              = "deceive"
    CONFESS              = "confess"
    PROVOKE              = "provoke"
    DEFEND               = "defend"
    NEUTRAL              = "neutral"               # бытовая коммуникация
```

### 3.3. Связь между SpeechAct, SocialIntent и Action

Один `Action.ATTACK` может иметь разные `SocialIntent`:

| Action | SpeechAct | SocialIntent | Пример |
|---|---|---|---|
| ATTACK | THREAT | INTIMIDATE | «Ещё слово — и я тебя ударю» |
| ATTACK | ORDER | OBTAIN_COMPLIANCE | «Уйди, или я тебя ударю» |
| ATTACK | ACCUSATION | PROVOKE | «Ты Worthless, ударить тебя — одолжение» |
| DIALOGUE | APOLOGY + COMPLIMENT | REPAIR_RELATIONSHIP + FLIRT | «Прости, не хотел обидеть, ты такая красивая…» |
| DIALOGUE | OFFER + PROMISE | OBTAIN_COOPERATION | «Если будешь хорошо себя вести, я помогу тебе сбежать» |

---

## 4. S199 — Semantic Unification

### 4.1. Цель

Уничтожить `ActionSemanticResolver` как самостоятельный semantic authority. Унифицировать путь игрока в мир через `IntentCompressor` → `IntentSemanticField` → `IntentDTO`.

### 4.2. До

```
raw player input
        │
   ┌────┴────┐
   ▼         ▼
IntentCompressor   ActionSemanticResolver
   │         │
   ▼         ▼
IntentField   PlayerAction (action_type + secret_id)
   │         │
   ▼         ▼
GameLoop    MvpTavernController
            → ActionConsequenceCompiler
            → NpcConfessionParser
```

### 4.3. После

```
raw player input
        │
        ▼
IntentCompressor
        │
        ▼
IntentSemanticField (расширенный, §2.2)
        │
        ▼
resolve_player_intent()
        │
        ▼
canonical IntentDTO
        │
        ├──────────────────────┐
        ▼                      ▼
    GameLoop            MvpTavernController
                        → ActionConsequenceCompiler
                          (читает IntentDTO, не PlayerAction)
```

### 4.4. Шаги реализации

1. **Расширить `IntentSemanticField`** полями из §2.2. Старые поля оставить как deprecated aliases (`@property`).
2. **Расширить промпт LLM Slow Path** в `intent_compressor.py` для заполнения новых полей. Schema-valídated JSON output.
3. **Добавить маппинг `IntentDTO → PlayerAction`** для обратной совместимости с `MvpTavernController` (временный bridge на 1 эпоху):
   ```python
   def intent_to_player_action(intent: IntentDTO, truth_state: TruthState) -> PlayerAction:
       # action_type выводится из intent.action + intent.social_intent
       # secret_id — из intent.proposition через PropositionMatcher
       ...
   ```
4. **Удалить `ActionSemanticResolver`** как точку входа для player text. Оставить файл, но переименовать в `legacy_action_semantic_resolver.py` с deprecation warning.
5. **Обновить `NpcConfessionParser`**: вместо `PlayerAction.secret_id` читать `IntentDTO.proposition` и матчить с `TruthState.secrets` через `PropositionMatcher` (семантический матч, не keyword).
6. **Обновить IPT**: добавить `inv_semantic_unification` — проверка, что `ActionSemanticResolver.resolve()` не вызывается из production path.

### 4.5. Критерий готовности S199

- [ ] `IntentSemanticField` содержит все поля из §2.2.
- [ ] `ActionSemanticResolver` не вызывается из `GameLoop._execute_dm_and_intent_resolution()`.
- [ ] `MvpTavernController` принимает `IntentDTO`, не `PlayerAction` (или bridge через `intent_to_player_action`).
- [ ] `NpcConfessionParser` использует `PropositionMatcher`, не keyword overlap.
- [ ] IPT `inv_semantic_unification` проходит.
- [ ] Все 14 SUPERBOX-сценариев проходят без регрессий.

---

## 5. S200 — Dialogue Context Binding

### 5.1. Цель

Связать `IntentCompressor` + `DialogueSession` + STM + target resolution в единую stateful semantic interpretation.

### 5.2. Контекст-зависимые входы, которые должны работать

| Игрок печатает | Без контекста | С контекстом |
|---|---|---|
| «А что?» | бессмысленно | QUESTION о предыдущей реплике NPC |
| «Продолжай» | бессмысленно | CONTINUE текущий thread |
| «А он?» | неопределённо | QUESTION о третьем NPC, упомянутом в thread |
| «Почему?» | неопределённо | QUESTION о причине предыдущего отказа |
| «Нет, я не это имел в виду» | бессмысленно | CLARIFY — откат предыдущего intent |
| «Ну и?» | бессмысленно | CONTINUE — поторопить NPC |

### 5.3. Шаги реализации

1. **Расширить `DialogueSession`** полем `active_thread: Optional[DialogueThread]`:
   ```python
   @dataclass(frozen=True)
   class DialogueThread:
       thread_id: str
       topic: str                           # "secret", "escape", "romance", ...
       pending_question: Optional[str]
       last_player_proposition: Optional[Proposition]
       last_npc_response: Optional[NarrativeBeat]
       opened_at_tick: int
       last_active_tick: int
   ```
2. **Передать `DialogueSession` в `IntentCompressor`** как дополнительный контекст для LLM Slow Path:
   ```
   SYSTEM PROMPT (дополнение):
   Текущий диалог с {target}:
   - Topic: {active_thread.topic}
   - Pending question: {active_thread.pending_question}
   - Last NPC response: {active_thread.last_npc_response.text}
   
   Если игрок пишет "продолжай", "ну?", "и?", "а что?" — интерпретируй как CONTINUE
   относительно последней реплики NPC.
   ```
3. **Reference resolution**: добавить `ReferenceResolver`, который по `DialogueThread` раскрывает анафоры:
   - «он» → последний упомянутый мужской NPC
   - «она» → последний упомянутый женский NPC
   - «это» → последний упомянутый объект / событие
   - «тот самый» → ранее упомянутый конкретный референт
4. **Thread lifecycle**: открытие нового треда при `conversation_continuation = NEW_TOPIC`, закрытие при `FAREWELL` или timeout (5 тиков без активности).
5. **IPT**: `inv_dialogue_context_binding` — проверка, что `IntentCompressor` имеет доступ к `DialogueSession` при вызове.

### 5.4. Критерий готовности S200

- [ ] `DialogueThread` существует и персистится в `DialogueSession`.
- [ ] «Продолжай» в контексте активного треда интерпретируется как `SpeechAct.CONTINUE`.
- [ ] «А что?» в контексте последней реплики NPC интерпретируется как `SpeechAct.QUESTION` о ней.
- [ ] «Нет, я не это имел в виду» открывает CLARIFY-процедуру.
- [ ] `test_dialogue_thread_continuity.py` расширен этими кейсами и проходит.

---

## 6. S201 — Social Act Materialization

### 6.1. Цель

Ввести `SpeechAct` / `SocialIntent` как первоклассные события в `EventBus`, материализуемые в мире.

### 6.2. Новый EventDTO

```python
class SocialActionEvent(EventDTO):
    event_type: EventType = EventType.SOCIAL_ACTION
    actor: str                       # npc_id или "player"
    target: str                      # npc_id или object_id
    action: Action                   # ATTACK / DIALOGUE / STEAL / ...
    speech_act: SpeechAct
    social_intent: SocialIntent
    proposition: Optional[Proposition]
    physical_force: float            # 0.0-1.0
    emotional_charge: float          # 0.0-1.0
    social_pressure: float           # 0.0-1.0
    visibility: str                  # "public" / "private" / "whisper"
    radius: float                    # 0.0-20.0 — для spatial membrane
```

### 6.3. Подписчики

Расширить существующих подписчиков:

- `NPCDialogueSubscriber` → реагирует на `SOCIAL_ACTION` с `action=DIALOGUE`
- `ClaimEventSubscriber` → реагирует на `SOCIAL_ACTION` с `speech_act=ASSERT` и `proposition is not None` (→ `COMMUNICATION_CLAIM`)
- `CombatSubscriber` → реагирует на `SOCIAL_ACTION` с `action=ATTACK` или `speech_act=THREAT` с `physical_force > 0.5`
- `SocialSubscriber` → реагирует на `SOCIAL_ACTION` с `social_intent in (FLIRT, COMFORT, INSULT, APOLOGY)` для обновления `RelationshipStore`
- `ReactionSubscriber` → формирует `EmbodiedTrace` для наблюдателей

### 6.4. Совместимость с существующими событиями

`SOCIAL_ACTION` не заменяет `COMMUNICATION_CLAIM`, `NPC_SPOKE`, `NPC_ATTACKED`. Он **объединяет** их в один канонический канал. Старые event types остаются как projection для обратной совместимости:

```
SOCIAL_ACTION(action=DIALOGUE, speech_act=ASSERT, proposition=P)
    │
    ├─ projection → COMMUNICATION_CLAIM (если proposition is not None)
    ├─ projection → NPC_SPOKE (для narrative)
    └─ projection → NPC_ATTACKED (если action=ATTACK)
```

### 6.5. Критерий готовности S201

- [ ] `SocialActionEvent` зарегистрирован в `EventType`.
- [ ] Все 5 подписчиков обновлены.
- [ ] Projection-функции (`to_communication_claim`, `to_npc_spoke`, `to_npc_attacked`) реализованы.
- [ ] IPT `inv_social_action_event` проверяет, что `SOCIAL_ACTION` публикуется для любого `action_type in (DIALOGUE, ATTACK, STEAL, GIVE)`.

---

## 7. S202 — Observer Causality

### 7.1. Цель

Сценарий «игрок атакует Люсю → Борко видит → Борко реагирует» должен проходить через обычный GameLoop, без специальных gameplay hack'ов.

### 7.2. Целевой flow

```
Player
  │
  ▼ SOCIAL_ACTION(action=ATTACK, target=lusya, force=0.8)
  │
EventBus
  │
  ├─→ CombatSubscriber → PhysiologyPayload(lusya)
  ├─→ ClaimEventSubscriber → EpistemicStore (если был proposition)
  ├─→ SpatialEventDetector → распространение observable
  │
  ▼ SpatialQueryService.get_observers(location, radius=8.0)
  │
  ▼ [borko, orm, tornin] — кто в радиусе
  │
  ▼ PerceptualKernel для каждого наблюдателя
  │
  ▼ EmbodiedTrace (что именно увидел Борко: «удар», «крик», «кровь»)
  │
  ▼ ClaimEventSubscriber (если наблюдающий NPC осознал proposition)
  │
  ▼ EpistemicStore.upsert(borko, belief_about_player)
  │
  ▼ EpistemicContextResolver.resolve(borko)
  │
  ▼ DecisionHub.compute(borko, epistemic_modifiers)
  │
  ▼ DecisionResult.intent = INTERVENE / WARN / ATTACK / FLEE
  │
  ▼ ActionWindup (2 тика подготовки, ADR-O-310)
  │
  ▼ SOCIAL_ACTION(actor=borko, target=player, action=ATTACK/WARN)
```

### 7.3. Шаги реализации

1. **`SpatialQueryService.get_observers(location_id, point, radius)`** — уже существует, проверить API.
2. **`PerceptualKernel` для каждого NPC-наблюдателя** должен генерировать `EmbodiedTrace` с `confidence` в зависимости от:
   - расстояния до события
   - LoS (line of sight)
   - времени суток (ночью хуже видит)
   - текущего `arousal` (спящий NPC не видит)
3. **`EpistemicContextResolver`** для Борко должен сформировать `perceived_threats = ("player",)` если он увидел атаку.
4. **`DecisionHub`** через `epistemic_modifiers` повышает score интента `INTERVENE` / `WARN` / `ATTACK` для Борко.
5. **`ActionWindup`** (ADR-O-310) — Борко не атакует мгновенно, а 2 тика «подходит + замахивается», давая игроку возможность отреагировать.

### 7.4. Критерий готовности S202

- [ ] Сценарий «player attacks Lusya → Borko observes (in radius) → Borko intervenes» работает end-to-end.
- [ ] Если Борко спит или вне радиуса — он **не** реагирует.
- [ ] Если Борко видел только часть (например, слышал крик из-за стены, но не видел удара) — его `EpistemicRecord` о игроке имеет `confidence < 0.5` и не попадает в `perceived_threats`.
- [ ] Сценарий воспроизводим в SUPERBOX-стиле: `test_observer_causality.py` с Control (Борко далеко) vs Treatment (Борко рядом).

---

## 8. S203 — Natural Language Torture Test

### 8.1. Цель

Доказать, что система устойчива к семантической вариативности свободного текста.

### 8.2. Тестовый сет

Не 20 заранее подготовленных фраз. **100–300 перефразировок одного намерения.**

#### 8.2.1. Намерение: «Я хочу узнать её секрет»

Минимум 50 перефразировок, например:

1. «Ну давай, выкладывай, что ты скрываешь.»
2. «Мне интересно, что ты не договариваешь.»
3. «Есть ощущение, что ты что-то держишь при себе.»
4. «Я пришёл сюда не ради погоды.»
5. «Мы оба понимаем, что ты что-то скрываешь.»
6. «Не хочешь рассказать, что на самом деле происходит?»
7. «Расскажи мне то, о чём ты молчишь.»
8. «Что ты пытаешься от меня утаить?»
9. «Я вижу, что ты напряглась. Что скрываешь?»
10. «Говори. Я всё равно узнаю.»
11. «Ты неважно выглядишь. Может, расскажешь, что тебя гложет?»
12. «Послушай, я не враг. Что ты прячешь?»
13. «Давай начистоту. Что у тебя за секрет?»
14. «Ты понимаешь, что я и так узнаю. Расскажи сама.»
15. «Что ты не говоришь мне?»
16. ... и ещё 35+ вариантов

#### 8.2.2. Намерение: «Я хочу её подразнить / флиртовать»

50 перефразировок: комплименты, шутки, поддразнивания, прямые предложения.

#### 8.2.3. Намерение: «Я хочу её утешить»

50 перефразировок: сочувствие, поддержка, объятия (вербально).

#### 8.2.4. Намерение: «Я хочу её запугать»

50 перефразировок: угрозы, шантаж, демонстрация силы.

#### 8.2.5. Контекстно-зависимые кейсы

50 кейсов с одним и тем же текстом, но разным контекстом:

| Текст | Контекст A | Контекст B |
|---|---|---|
| «Ты можешь ударить Люсю?» | игрок спрашивает Борко о его возможности | игрок приказывает Борко атаковать |
| «Хорошо.» | согласие с предложением NPC | закрытие разговора |
| «Я ударил Люсю.» | признание в уже совершённом действии | приказ NPC атаковать (мета-команда) |
| «И?» | поторопить NPC | уточнить у NPC «и что дальше?» |

### 8.3. Что проверяется

**Не** `ActionType accuracy = 97%`. Это почти бесполезно, потому что ActionType — грубая метка.

Проверяется:

#### 8.3.1. Intent Preservation (forward)

```
разные человеческие формулировки
              ↓
       один семантический intent
              ↓
      одинаковый causal class
```

Метрика: для всех 50 перефразировок «узнать секрет» — `social_intent == OBTAIN_INFORMATION` AND `target == Lusya`. Допускается вариация `speech_act` (REQUEST / QUESTION / THREAT с условием), но `social_intent` должен быть один.

#### 8.3.2. Context Sensitivity (inverse)

```
одинаковые слова
       ↓
разный context
       ↓
разный intent
```

Метрика: для кейсов из §8.2.5 — `IntentDTO` в контексте A ≠ `IntentDTO` в контексте B хотя бы в одном из полей `(action, speech_act, social_intent, proposition, target)`.

#### 8.3.3. Causal Class Equivalence

Две формулировки эквивалентны, если порождают одинаковый каузальный класс событий:

```python
def causal_class(intent: IntentDTO) -> tuple:
    return (
        intent.action,
        intent.social_intent,
        intent.target,
        bool(intent.proposition),
        intent.speech_act in THREATENING_ACTS,  # THREAT / ACCUSATION / INSULT
    )
```

Метрика: для всех 50 перефразировок одного намерения — `causal_class(intent_i) == causal_class(intent_j)` для всех i, j.

### 8.4. Формат теста

```python
# backend/tests/sandbox/SUPERBOX/scenarios/semantic_torture_test.py

INTENT_REVEAL_SECRET = [
    "Ну давай, выкладывай, что ты скрываешь.",
    "Мне интересно, что ты не договариваешь.",
    # ... 50+ фраз
]

INTENT_FLIRT = [...]
INTENT_COMFORT = [...]
INTENT_INTIMIDATE = [...]
CONTEXT_DEPENDENT = [
    ("Ты можешь ударить Люсю?", CONTEXT_A, CONTEXT_B),
    ...
]

@pytest.mark.parametrize("text", INTENT_REVEAL_SECRET)
def test_intent_preservation_reveal_secret(text):
    """Все 50 формулировок должны попадать в один causal class."""
    intent = intent_compressor.compress(text, target="maid_lusya", context=...)
    assert intent.social_intent == SocialIntent.OBTAIN_INFORMATION
    assert intent.target == "maid_lusya"
    assert causal_class(intent) == EXPECTED_REVEAL_SECRET_CLASS
```

### 8.5. Критерий готовности S203

- [ ] 200+ перефразировок в 4 категориях намерений.
- [ ] 50+ контекстно-зависимых кейсов.
- [ ] Intent Preservation ≥ 85% (допускается 15% LLM-вариативности, но не ниже).
- [ ] Context Sensitivity ≥ 90% (контекст должен менять intent в 9 из 10 случаев).
- [ ] Causal Class Equivalence ≥ 90%.
- [ ] Тест запускается через `python backend/tests/sandbox/SUPERBOX/scenarios/semantic_torture_test.py`.
- [ ] Отчёт о неудачах (какие фразы не попали в ожидаемый класс) сохраняется в `reports/semantic_torture_<date>.md`.

---

## 9. Архитектурный итог: что появится после S199-S203

### 9.1. Замкнутый human ↔ simulation loop

```
человеческое высказывание
          ↓
    восстановление смысла       ← IntentCompressor + DialogueSession (S199, S200)
          ↓
контекст + намерение + референты
          ↓
     canonical IntentDTO         ← расширенный IntentSemanticField (S199)
          ↓
      ENIGMA world               ← SOCIAL_ACTION event (S201)
          ↓
   NPC beliefs update             ← EpistemicStore (S201, S202)
          ↓
      NPC decision                ← DecisionHub + EpistemicContextResolver (S202)
          ↓
     social action                ← SOCIAL_ACTION event (S201)
          ↓
        speech                    ← DialogueExecutor + Materializer
          ↓
        player                    ← NarrativeRenderer
```

### 9.2. Что НЕ делается в этом ТЗ

- ❌ Не создаётся новый Intent Layer.
- ❌ Не добавляется 15 новых `ActionType`.
- ❌ Не создаётся новый `ConversationManager` — используется существующий `DialogueSession`.
- ❌ Не переписывается `MvpTavernController` — только bridge через `intent_to_player_action`.
- ❌ Не трогается `EpistemicStore` / `BeliefRevisionEngine` / `ClaimEventSubscriber` — они уже работают (доказано SUPERBOX-002…014).
- ❌ Не достраиваются Эпохи 7-11 (Prophecy, Generations, Society, §18) — они остаются замороженными.

### 9.3. Связь с существующими ADR

| S-номер | Новый ADR | Связанные существующие ADR |
|---|---|---|
| S199 | ADR-S199 Semantic Unification | ADR-TZ08-1 (InterventionEvent), ADR-TZ09-1 (TickState/TickMutation), ADR-O-313 (Universal Task Layer) |
| S200 | ADR-S200 Dialogue Context Binding | ADR-O-208 (L1Chronicle), существующий `test_dialogue_thread_continuity.py` |
| S201 | ADR-S201 Social Act Materialization | ADR-TZ08-1 (Event-Driven Kernel), ADR-O-306 (Epistemic Heterogeneity) |
| S202 | ADR-S202 Observer Causality | ADR-TZ08-4/6 (Epistemic Boundary), ADR-O-306 (Triple Membrane) |
| S203 | ADR-S203 Semantic Torture Test | существующие SUPERBOX-001…014 как методологический прецедент |

---

## 10. KPI успеха Эпохи 6.1 (S199-S203)

### 10.1. Количественные

| KPI | Целевое значение | Метрика |
|---|---|---|
| Intent Preservation (S203) | ≥ 85% | 50 перефразировок → один causal class |
| Context Sensitivity (S203) | ≥ 90% | 50 кейсов → контекст меняет intent |
| Causal Class Equivalence (S203) | ≥ 90% | все 200+ перефразировок попадают в ожидаемый класс |
| Observer Causality end-to-end (S202) | 100% | `test_observer_causality.py` проходит |
| ActionSemanticResolver в production path | 0 вызовов | `inv_semantic_unification` IPT passes |
| SUPERBOX-001…014 регрессий | 0 | все 14 сценариев проходят |
| IPT регрессий | 0 | все 39 инвариантов проходят |

### 10.2. Качественные

- [ ] Игрок может напечатать «Если будешь хорошо себя вести, я помогу тебе сбежать» — и система понимает это как OFFER + PROMISE + PERSUADE с proposition «I will help you escape» под условием «if you cooperate».
- [ ] Игрок может напечатать «Продолжай» — и система понимает это как CONTINUE в контексте активного thread.
- [ ] Игрок атакует Люсю — Борко (если в радиусе и не спит) подходит и вмешивается через 2 тика ActionWindup, без специальных if'ов.
- [ ] Игрок может напечатать «Я знаю про подвал» БЕЗ слова «шантаж» — и система понимает это как ACCUSATION / THREAT (из контекста), а не DIALOGUE.
- [ ] 50 различных формулировок «узнать секрет Люси» — все приводят к `social_intent=OBTAIN_INFORMATION, target=maid_lusya` и в конечном итоге к попытке `NpcConfessionParser` найти соответствующий секрет в ответе.

---

## 11. План реализации

### 11.1. Очерёдность

```
S199 (1-2 недели)  ──→  S200 (1 неделя)  ──→  S201 (1 неделя)
                                                  ↓
                              S202 (1 неделя)  ──→  S203 (2 недели)
```

**Итого: 6-7 недель соло-разработки.**

### 11.2. Контрольные точки

| Неделя | Что готово | Тест |
|---|---|---|
| 1 | `IntentSemanticField` расширен, `ActionSemanticResolver` deprecated | `inv_semantic_unification` IPT |
| 2 | `intent_to_player_action` bridge, `NpcConfessionParser` использует `PropositionMatcher` | SUPERBOX-001…014 без регрессий |
| 3 | `DialogueThread` в `DialogueSession`, «Продолжай» работает | `test_dialogue_thread_continuity.py` расширен |
| 4 | `SocialActionEvent` + 5 подписчиков + projection | `inv_social_action_event` IPT |
| 5 | `test_observer_causality.py` Control/Treatment | end-to-end сценарий |
| 6-7 | 200+ перефразировок, метрики Intent Preservation / Context Sensitivity | `semantic_torture_test.py` |

### 11.3. Риски

1. **LLM Slow Path latency** — расширение IntentSemanticField потребует более длинного LLM-вызова. Mitigation: Fast Path для очевидных случаев (короткий текст + известное ключевое слово → Fast Path с ConfidenceVector.high_confidence).
2. **PropositionMatcher точность** — семантический матч IntentDTO.proposition с TruthState.secrets может быть неточным. Mitigation: использовать embedding similarity (BGE-small-ru) + fallback на keyword overlap (как сейчас).
3. **DialogueThread lifecycle complexity** — авто-открытие / закрытие тредов может привести к гонкам. Mitigation: явная FSM для thread states (NEW → ACTIVE → STALE → CLOSED).
4. **S203 false negatives** — LLM может классифицировать редкие формулировки неожиданно. Mitigation: допускать 15% failure rate, но записывать все неудачи в `reports/semantic_torture_<date>.md` для ручного анализа.

---

## 12. Финальное замечание

Это ТЗ **не добавляет новую систему**. Оно **ликвидирует раздвоение** в существующей.

Архитектурно это означает:

> Один semantic authority (`IntentCompressor` + расширенный `IntentSemanticField`) → один canonical `IntentDTO` → один `SOCIAL_ACTION` event → существующая машина мира (`EventBus` + `EpistemicStore` + `DecisionHub`) → одно каноническое действие NPC.

После S199-S203 ENIGMA перестанет быть «двумя конкурирующими системами понимания игрока плюс старый MVP-парсер» и станет **одной системой с замкнутым human ↔ simulation loop**.

Это и есть та ENIGMA, которую мы обсуждали.

---

## Приложение A. Файлы, которые будут изменены

| Файл | Изменение | S-номер |
|---|---|---|
| `backend/app/models/` (IntentSemanticField) | расширение полей | S199 |
| `backend/app/services/input/intent_compressor.py` | расширение LLM-промпта | S199 |
| `backend/app/services/input/llm_compressor_client.py` | schema for new fields | S199 |
| `backend/app/services/player_cognition/action_semantic_resolver.py` | deprecate, переименовать в `legacy_` | S199 |
| `backend/app/services/player_cognition/npc_confession_parser.py` | использовать `PropositionMatcher` | S199 |
| `backend/app/services/memory/dialogue_session.py` (или новый) | добавить `DialogueThread` | S200 |
| `backend/app/services/player_cognition/reference_resolver.py` (новый) | анафора resolution | S200 |
| `backend/app/domain/events.py` | добавить `SocialActionEvent` | S201 |
| `backend/app/services/events/event_types.py` | `EventType.SOCIAL_ACTION` | S201 |
| `backend/app/services/events/social_action_subscriber.py` (новый) | маршрутизация | S201 |
| `backend/app/services/events/npc_dialogue_subscriber.py` | обновить для SOCIAL_ACTION | S201 |
| `backend/app/services/events/claim_event_subscriber.py` | обновить для SOCIAL_ACTION | S201 |
| `backend/app/services/combat/combat_subscriber.py` | обновить для SOCIAL_ACTION | S201 |
| `backend/app/services/events/social_subscriber.py` | обновить для SOCIAL_ACTION | S201 |
| `backend/app/services/spatial/spatial_query_service.py` | `get_observers()` | S202 |
| `backend/app/services/npc/perceptual_kernel.py` | генерация EmbodiedTrace для наблюдателей | S202 |
| `backend/app/services/npc/epistemic_context_resolver.py` | поддержка observer beliefs | S202 |
| `backend/tests/IPT.py` | `inv_semantic_unification`, `inv_social_action_event` | S199, S201 |
| `backend/tests/sandbox/SUPERBOX/scenarios/semantic_torture_test.py` (новый) | 200+ перефразировок | S203 |
| `backend/tests/sandbox/SUPERBOX/scenarios/test_observer_causality.py` (новый) | end-to-end | S202 |
| `docs/audits/ADR-S199_IMPACT.md` … `ADR-S203_IMPACT.md` (новые) | формализация | все |

## Приложение B. Файлы, которые НЕ изменяются

- `backend/app/services/npc/belief_crystallization_engine.py`
- `backend/app/services/npc/epistemic_store.py`
- `backend/app/services/npc/belief_revision_engine.py`
- `backend/app/services/events/claim_event_subscriber.py` (только расширение, не переписывание)
- `backend/app/domain/epistemology.py` (Proposition, Predicate, ClaimEvent, EpistemicRecord, EpistemicContext)
- `backend/app/services/tick_orchestrator.py` (только добавление SOCIAL_ACTION в Фазу 6)
- `backend/app/services/social/mvp_tavern_controller.py` (только bridge через `intent_to_player_action`)
- Все 14 SUPERBOX-сценариев `epistemic_*` (только расширение, не переписывание)

---

*Конец ТЗ.*
