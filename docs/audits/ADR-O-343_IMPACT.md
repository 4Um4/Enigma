# ADR-O-343 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-O-343` [STANDARD] **IMPACT**
# ADR-O-343: Narrative Arbitration Layer / SpeechScheduler v1

> **Статус:** PROPOSED (Requires 2nd Audit before coding)
> **Домен:** DOM-03 (NPC & Cognition), DOM-08 (Observability), DOM-06 (Materialization)
> **Сессия:** S170

## 1. Контекст

Текущая архитектура предполагает, что любой `CommunicationIntent` автоматически конвертируется в `QueuedTask` и падает в `DialogueQueue` для LLM-генерации. Из-за стабильности утилитарных функций и рассинхрона `game_time_seconds` (60 сек/тик) с wall-clock, 6 NPC генерируют 102 LLM-запроса за 5 секунд, уничтожая `llama-server`. 

Корень проблемы: ENIGMA не различает *«NPC захотел говорить»* и *«Существующая в мире причинность заслуживает быть материализованной в речь»*.

## 2. Закон нарративной материализации (Главный принцип)

> **ENIGMA не вызывает LLM потому, что NPC захотел говорить. ENIGMA вызывает LLM тогда, когда существующая в мире причинность заслуживает быть материализованной в речь.**

## 3. Архитектурная модель

Цепочка арбитража проходит через 3 стадии, фильтруя候选атов:

```text
CommunicationIntent (Желание)
   ↓
[Narrative Arbitration] "Что изменится, если он скажет?"
   ↓
SpeechCandidate (Оценка ценности)
   ↓
[Cognitive/Presentation Budget] "Игрок способен это воспринять?"
   ↓
SpeechAdmission (Разрешение на материализацию)
   ↓
[Resource Budget] "GPU может это сейчас выполнить?"
   ↓
SpeechRequest → TaskScheduler → LLM
```

### A. Ownership
- **SpeechScheduler** владеет: `SpeechCandidate`, `ConversationThread`, `ExpectedConsequences`, `NarrativeValue`, `Cognitive Budget`.
- **TaskScheduler** (Resource Scheduler) владеет: GPU concurrency, VRAM budget, queue depth.
- **DecisionHub** владеет: `CommunicationIntent` (дешёвая Python-логика желания).

### B. NarrativeValue & ExpectedConsequences
Речь оценивается по потенциальному каузальному и социальному изменению.
Перед допуском к LLM, Python-логика вычисляет `ExpectedConsequences`:
- Изменит ли это relationship, belief, knowledge, reputation, debt, goal, secret exposure?
Если ответ "нет" для всех полей → `NarrativeValue ≈ 0` → LLM не нужен (используется deterministic utterance).

### C. Conversation Lifecycle (Starvation Protection)
Продолжение активного треда (`ConversationThread`) имеет **очень высокий**, но **не абсолютный** приоритет.
Приоритет:
```text
Crisis Event (Fire, Combat) 
    > Conversation Continuation 
    > Causal Reaction 
    > Player-Relevant 
    > Novel Information 
    > Ambient Initiation
```
Активный разговор может быть вытеснен событием более высокого класса.

### D. IntentSignature (Deduplication)
Сигнатура включает `causal_context_version` (хеш значимого контекста).
- **Duplicate:** Сигнатура совпадает, `causal_context` не изменился → подавить.
- **Persistent/New Intent:** Изменился `causal_context` (долг, расстояние, здоровье) → валиден.

### E. Time Semantics & Minimum Response Latency
- **Simulation Time (`game_time_seconds`):** Каузальный порядок событий.
- **Wall-clock (`time.time()`):** Минимальная задержка ответа (Human Pacing ≥ ~2 sec). NPC не может ответить раньше, чем через 2 реальные секунды после возникновения коммуникативной ситуации.
- **Resource Time:** Управление GPU concurrency.

### F. Cognitive / Presentation Budget
Отдельный бюджет от LLM. Ограничивает количество `VISIBLE_SPEECH` beats (1-3 одновременно). 
Иерархия состояний мира:
```text
BACKGROUND (200 NPC, нет речи)
   ↓
CANDIDATE (25 NPC, генерация кандидатов)
   ↓
NARRATIVE_ACTIVE (5 NPC, арбитраж)
   ↓
VISIBLE_SPEECH (1-3 NPC, LLM + UI)
```

### G. Lazy-World Compatibility
Удалённость (distant) снижает детализацию симуляции, но **не уничтожает каузально значимые события**. 
Если два distant NPC создают событие огромной важности (убийство короля), оно может пройти арбитраж и стать `NARRATIVE_ACTIVE`.

## 4. Taboo (Запреты)
- ❌ Использование `max_n_llm_admissions_per_tick` как основного лимитера.
- ❌ Создание `QueuedTask` для LLM в обход `SpeechScheduler` и `NarrativeValue`.
- ❌ Абсолютный приоритет `Conversation Continuation` над кризисными событиями.
- ❌ Игнорирование `causal_context_version` при дедупликации.
- ❌ Назначение `wall-clock cooldown` как архитектурного паттерна (только `Minimum Response Latency` и `Resource Budget`).

## 5. Acceptance Tests
1. **No Intent Spam:** Одинаковый `causal_context` не порождает несколько независимых LLM-вызовов.
2. **Narrative Value Filter:** Реплики с нулевым `ExpectedConsequences` не доходят до LLM.
3. **Starvation Protection:** Активный разговор может быть прерван кризисным событием.
4. **Minimum Latency:** NPC не отвечает быстрее ~2 секунд wall-clock, независимо от скорости `idle_tick`.
5. **Resource Isolation:** TaskScheduler не решает "что говорить", он только защищает GPU.

## 6. Rollback
Удалить `SpeechScheduler`, вернуть прямую маршрутизацию. Восстановить `DialogueQueue`.
```

---

### Файл 2: `docs/ADR (Architecture Decision Records).md`

Найди блок `## ADR-O-343: ...` (который мы добавили ранее) и **замени его целиком** на этот обновлённый:

```markdown
## ADR-O-343: Narrative Arbitration Layer / SpeechScheduler v1 [ONTO]
> **Статус:** PROPOSED (Requires 2nd Audit)
> **Домен:** DOM-03 (NPC & Cognition), DOM-08 (Observability), DOM-06 (Materialization)
> **Сессия:** S170

**Контекст:** 
Текущая архитектура автоматически конвертирует любой `CommunicationIntent` в `QueuedTask` для LLM. Из-за рассинхрона `game_time_seconds` с wall-clock, 6 NPC генерируют 102 LLM-запроса за 5 секунд, уничтожая `llama-server`. Корень проблемы: желание NPC говорить приравнено к праву на LLM-генерацию.

**Решение (Закон нарративной материализации):**
1. Вводится слой **Narrative Arbitration Layer (SpeechScheduler)**.
2. Речь оценивается через `NarrativeValue` и `ExpectedConsequences`. Если речь ничего не меняет в мире (relationship, belief, etc.) — LLM не вызывается.
3. `ConversationThread` имеет высокий приоритет продолжения, но **не абсолютный** (Starvation Protection).
4. В `IntentSignature` добавляется `causal_context_version` для дедупликации.
5. Вводится `Minimum Response Latency` (~2 sec wall-clock) для эмуляции темпа мышления.
6. TaskScheduler становится чисто ресурсным планировщиком (GPU concurrency).

**Taboo:**
- ❌ Использование `max_n_llm_admissions_per_tick` как главного лимитера.
- ❌ Создание `QueuedTask` в обход `SpeechScheduler`.
- ❌ Абсолютный приоритет продолжения разговора над кризисными событиями.
- ❌ Использование `wall-clock cooldown` как архитектурного паттерна (только Resource Budget).



Files: N/A
