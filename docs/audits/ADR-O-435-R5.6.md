# ADR-O-435-R5.6 — КОРРЕКТИРОВКИ R5.5 + ОБНОВЛЁННЫЕ КОМАНДЫ АРХЕОЛОГИИ

**Основание:** Вердикт Мастера по R5.5 — APPROVED WITH CORRECTIONS. GO на read-only археологию.
**Статус:** ARCHAEOLOGY SCRIPT v2 — обновлённые команды с учётом корректировок R1-R6
**Сессия:** S404 (Ветвь Б «Мир и платформа»)
**Базлайн:** V.0.5.4.5.0_Спать_хочу, HEAD 755a1c27

**Главный принцип (VERIFIED — утверждён Мастером):**

> Player может управлять телом. Но управление телом не означает владение сознанием Avatar.

**Главное изменение режима (VERIFIED из вердикта):**

> Больше не строим архитектуру вокруг предположений о том, что уже существует в ENIGMA. Сначала выясняем, что реально делает код, затем решаем, что ему нужно добавить.

---

## §1. EXECUTIVE VERDICT

### 1.1. Постановка

Мастер утвердил R5.5 как рабочий план с шестью корректировками R1-R6 и тремя исправлениями плана. Археология разрешена.

R5.6 — обновлённый археологический скрипт, учитывающий корректировки. Готов к запуску на production.

### 1.2. Что утверждено без изменений (VERIFIED)

- Восемь блокаторов и их последовательность.
- Формат причинной цепочки: `источник → вызов → преобразование → состояние → событие → подписчик → память/убеждение`.
- Статусы VERIFIED / PARTIALLY VERIFIED / NEEDS ARCHAEOLOGY.
- Разделение археологии и реализации.
- Этапы MVP 0-6 и их общую зависимость от блокаторов.
- Новую классификацию механизмов.
- Автономию технических решений по EventDTO, AttributionCalculator и Avatar self-awareness.
- Запрет на миграцию `agent_id` до установления принадлежности исторических записей.

### 1.3. Корректировки R1-R6 (VERIFIED — обязательны)

| Корректировка | Что меняется |
|---|---|
| R1 | EventDTO — критерии A/B по семантическому контракту, не по числу обращений |
| R2 | AttributionCalculator — три вопроса, не единообразие чтения |
| R3 | Avatar self-awareness — сначала источник информации, не подписка по source |
| R4 | Windup — сначала семантика отмены и commit points, не CANCELLED автоматически |
| R5 | agent_id — неоднозначность как состояние данных, не просто строка |
| R6 | Python-блок блокатора 8 — НЕ запускать, сначала контракты |

### 1.4. Три исправления плана (VERIFIED)

| Место | Исправление |
|---|---|
| §3.2.2 R5.5 | `head -30` не гарантирует полноту — вывести все регистрации и обработчики отдельно |
| §4.3-4.4 R5.5 | Этапы 0-1 — локальные аудиты существующих контрактов, не ждать всех блокаторов |
| §4.9+§6.1 R5.5 | Stage 6 убрать из MVP closure |

### 1.5. Порядок запуска (VERIFIED)

1. **Блокаторы 1-4** — первыми (BodyArbiter + AvatarInitiativeEngine).
2. **Блокаторы 5-7** — параллельно (не блокируют MVP 0-4).
3. **Блокатор 8** — отдельно: сначала кодовая археология, затем анализ исторических данных. Никакой миграции.
4. **Этапы 0-1** — независимо от блокаторов 1-8, но каждый с локальным аудитом затрагиваемых контрактов.

### 1.6. Технические замечания (VERIFIED)

- Скрипт на Bash: выполнять из Git Bash/WSL в корне репозитория.
- Результаты больших поисков сохранять отдельными текстовыми файлами.
- Regression gate: добавление Avatar-тестов может изменить общее число IPT, но НЕ должно обнулять или пересчитывать существующие регрессии ради зелёного результата.

### 1.7. Формат отчёта (VERIFIED — для каждого блокатора)

```
- Блокатор и команда
- Полный вывод или файл с выводом
- Подтверждённые факты
- Причинная цепочка
- Неустановленные участки
- Архитектурное следствие
```

«Я буду проверять не количество найденных классов, а доказанность связей между ними.»

---

## §2. КОРРЕКТИРОВКИ R1-R6 — ЧТО МЕНЯЕТСЯ

### 2.1. R1 — EventDTO: семантический контракт, не технические факторы

**Проблема R5.5 §3.1.5:** критерии выбора A/B основаны на числе обращений к `event_id` и наличии `EventLog`. Но идентификатор события может использоваться для дедупликации, не являясь носителем канонического факта мира.

**Исправление:** выбирать A/B по семантическому контракту:

| Вопрос | Что устанавливает |
|---|---|
| Кто создаёт канонический факт? | Источник истины |
| Где он сохраняется? | Storage contract |
| Что считается авторитетным при повторном чтении и replay? | Replay authority |
| Может ли транспортный DTO изменяться или терять информацию без изменения факта? | DTO vs SSOT разделение |
| Есть ли уже отдельное состояние, представляющее факт мира? | Existing WorldEvent concept |

`frozen`, количество сравнений, число использований `event_id` — дополнительные технические факторы, но НЕ критерии архитектурного выбора.

### 2.2. R2 — AttributionCalculator: три вопроса, не единообразие

**Проблема R5.5 §3.2.5:** предлагается создавать калькулятор, если подписчики используют `event.source` единообразно. Но единообразное чтение одного поля ещё не означает одинаковую семантику для всех типов событий.

**Исправление:** решение принимать по трём вопросам:

1. **Что `source` означает для каждого типа события?** (NPC_SPOKE vs ACTOR_ATTACKS vs PLAYER_INTERACTS — разные семантики)
2. **Где различаются speaker, actor, intent_owner и социальный субъект?** (для attack intent: speaker=attacker; для accuse: subject=target)
3. **Есть ли реальная повторяющаяся логика, которую калькулятор должен централизовать?** (или каждый subscriber уникален)

Если нет общей семантики и общей операции — НЕ создавать калькулятор только ради абстракции.

### 2.3. R3 — Avatar self-awareness: источник информации, не подписка по source

**Проблема R5.5 §3.3.5:** предложено создать `AvatarSelfAwarenessSubscriber`, подписанный на события с `source=character_id`. Но Avatar должен знать о собственном телесном действии не потому, что событие случайно содержит его ID в `source`.

**Исправление:** установить отдельно:

| Что установить | Зачем |
|---|---|
| Какие действия совершены общим телом | Body action tracking |
| Какие изменения тела произошли | Body state changes |
| Какие последствия Avatar непосредственно воспринимает | Avatar perception |
| Какие сведения о намерениях Player ему недоступны | Граница знания Avatar |

Subscriber — один из вариантов реализации, НЕ заранее утверждённая архитектура. Сначала доказать источник информации и путь её получения Avatar.

### 2.4. R4 — Windup: семантика отмены, не CANCELLED автоматически

**Проблема R5.5 §3.4.5:** предложено расширить `ActionWindup` с `CANCELLED`, если статус отсутствует. Но отсутствие статуса ещё не означает отсутствия механизма отмены.

**Исправление:** сначала восстановить:

1. **Семантика отмены** — как сегодня отменяется windup? Через INTERRUPTED? Через ActionCommitment? Иной путь?
2. **Точка фиксации физического действия** (commit point) — после какой стадии windup необратим?

Затем определить отображение в ExecutionLifecycleState. Новый статус в существующую FSM добавлять ТОЛЬКО при доказанной необходимости.

### 2.5. R5 — agent_id: неоднозначность как состояние данных

**Проблема R5.5 §3.8.5:** неоднозначные записи представлены строкой `ambiguous:player:{session_marker}`. Это недостаточно для безопасной миграции.

**Исправление:** обязательно сохранить:

| Что сохранить | Зачем |
|---|---|
| Исходный `agent_id` | Provenance |
| Исходный ключ записи | Storage identity |
| Происхождение и контекст | Decision basis |
| Уникальность маркера | No collisions |
| Возможность повторного запуска миграции без повторного изменения данных | Idempotency |
| Обратимость | Rollback |

Неоднозначность должна оставаться **явным состоянием данных**, не просто новым строковым именем.

### 2.6. R6 — Python-блок блокатора 8: НЕ запускать

**Проблема R5.5 §3.8.2:** Python-блок использует `npc_registry` (не определён), путь `backend/data/sessions/<campaign>/scene_state.json` (placeholder), `EpistemicStore.from_dict()` и `_records` (не доказаны).

**Исправление:** эту часть запускать НЕЛЬЗЯ.

Сначала получить:
1. Реальные контракты загрузки `scene_state`.
2. Реестр NPC.
3. Сериализацию `EpistemicStore`.

Затем подготовить отдельный проверяемый read-only скрипт классификации.

### 2.7. Три исправления плана

| Место R5.5 | Исправление R5.6 |
|---|---|
| §3.2.2 `head -30` | Убрать `head -30`. Вывести все регистрации и обработчики отдельно. Не считать результат полным. |
| §4.3-4.4 этапы 0-1 независимы | Разрешить реализацию этапов 0-1 по собственным локальным аудитам существующих контрактов. НЕ ждать всех восьми блокаторов. |
| §4.9+§6.1 Stage 6 в MVP closure | УБРАТЬ Stage 6 из MVP closure. Sleep/death/body-switching — отложенные возможности, не условие закрытия MVP. |

**Regression gate уточнение:** добавление Avatar-тестов может изменить общее число IPT, но НЕ должно позволять обнулить или пересчитать существующие регрессии ради зелёного результата.

---

## §3. ОБНОВЛЁННЫЕ КОМАНДЫ — БЛОКАТОРЫ 1-4 (ПЕРВЫМИ)

Команды готовы к запуску Мастером из Git Bash/WSL в корне репозитория. Результаты сохранять в отдельные текстовые файлы.

### 3.1. Блокатор 1 — EventDTO full contract (с учётом R1)

#### 3.1.1. Команды

```bash
# === BLOCKER 1: EventDTO full contract (R1 corrected) ===
# Запускать из корня репозитория
# Сохранить вывод в: archaeology_reports/blocker_1_eventdto.txt

mkdir -p archaeology_reports

{
echo "=== B1.1: EventDTO class definition ==="
grep -rn "class EventDTO" backend/app/ --include="*.py"

echo ""
echo "=== B1.2: EventDTO all fields and methods ==="
# Найти файл с EventDTO, вывести full class body
EVENTDTO_FILE=$(grep -rln "class EventDTO" backend/app/ --include="*.py" | head -1)
if [ -n "$EVENTDTO_FILE" ]; then
    echo "File: $EVENTDTO_FILE"
    # Вывести 80 строк после class definition
    START_LINE=$(grep -n "class EventDTO" "$EVENTDTO_FILE" | head -1 | cut -d: -f1)
    sed -n "${START_LINE},$((START_LINE + 80))p" "$EVENTDTO_FILE"
fi

echo ""
echo "=== B1.3: EventDTO all creation points ==="
grep -rn "EventDTO.create\|EventDTO(" backend/app/ --include="*.py" | grep -v test | grep -v __pycache__

echo ""
echo "=== B1.4: EventDTO serialization (to_dict/from_dict) ==="
grep -rn "def to_dict\|def from_dict\|def serialize\|def deserialize" backend/app/domain/events.py backend/app/domain/event*.py 2>/dev/null
grep -rn "event.*to_dict\|event.*from_dict\|json.dumps.*event\|json.loads.*event" backend/app/ --include="*.py" | grep -v test | head -20

echo ""
echo "=== B1.5: event_id usage ==="
grep -rn "event.id\|event_id" backend/app/ --include="*.py" | grep -v test | grep -v __pycache__

echo ""
echo "=== B1.6: EventDTO equality usage ==="
grep -rn "event ==\|event !=\|EventDTO ==\|EventDTO !=" backend/app/ --include="*.py" | grep -v test

echo ""
echo "=== B1.7: EventLog / event_log in scene_state ==="
grep -rn "event_log\|events_log\|world_event\|world_events" backend/app/ --include="*.py" | grep -v test

echo ""
echo "=== B1.8: next_event_identity contract ==="
grep -rn "def next_event_identity\|next_event_identity" backend/app/ --include="*.py" | grep -v test
NEXT_ID_FILE=$(grep -rln "def next_event_identity" backend/app/ --include="*.py" | head -1)
if [ -n "$NEXT_ID_FILE" ]; then
    echo "File: $NEXT_ID_FILE"
    START_LINE=$(grep -n "def next_event_identity" "$NEXT_ID_FILE" | head -1 | cut -d: -f1)
    sed -n "${START_LINE},$((START_LINE + 30))p" "$NEXT_ID_FILE"
fi

echo ""
echo "=== B1.9: scene_state persistence contract ==="
grep -rn "scene_state.*save\|save_scene_state\|persist.*scene\|scene.*persist" backend/app/ --include="*.py" | grep -v test | head -10

echo ""
echo "=== B1.10: EventDTO frozen check ==="
grep -rn "@dataclass.*frozen.*\|class EventDTO" backend/app/ --include="*.py"
} > archaeology_reports/blocker_1_eventdto.txt 2>&1

echo "Report saved to: archaeology_reports/blocker_1_eventdto.txt"
wc -l archaeology_reports/blocker_1_eventdto.txt
```

#### 3.1.2. Что искать в выводе (R1 corrected — семантические вопросы)

**Помимо технических фактов, установить:**

| Семантический вопрос | Что искать в выводе |
|---|---|
| Кто создаёт канонический факт? | B1.3 — все точки создания. Различать: IntentEventAdapter (NPC path), publish_player_intent (Player path), dialogue_materializer (LLM materialization), npc_addressing_delivery_subscriber (initiative) |
| Где он сохраняется? | B1.7 — EventLog в scene_state. B1.9 — scene_state persistence contract. |
| Что авторитетно при replay? | B1.5 — event_id usage. B1.8 — next_event_identity (детерминированность). |
| Может ли DTO терять информацию? | B1.2 — все поля EventDTO. B1.4 — serialization (lossy или lossless). |
| Есть ли уже отдельное состояние факта мира? | B1.7 — EventLog / world_event в scene_state. |

**Технические факторы (дополнительные, НЕ решающие):**
- B1.6 — equality usage (сколько callers сравнивают).
- B1.10 — frozen или mutable.

#### 3.1.3. Решение A/B (после вывода)

| Семантический факт | Решение |
|---|---|
| EventLog exists в scene_state как отдельное состояние | WorldEvent уже де-факто существует. Opция B (отдельный класс) — предпочтительна. |
| EventLog НЕ exists, event_id только для dedup | EventDTO — DTO, не SSOT. Opция A (расширить) или B (создать WorldEvent) — обе возможны. Решение по semantic fit. |
| Serialization lossy (DTO теряет поля) | EventDTO не может быть SSOT. Opция B обязательно. |
| Serialization lossless | Обе опции возможны. |
| Multiple creation points с разной semantic | WorldEvent как canonical, EventDTO как projection. Opция B. |

---

### 3.2. Блокатор 2 — Phase 8 subscribers (с учётом R2 + §3.2.2)

#### 3.2.1. Команды

```bash
# === BLOCKER 2: Phase 8 subscribers (R2 + §3.2.2 corrected) ===
# Сохранить вывод в: archaeology_reports/blocker_2_subscribers.txt

mkdir -p archaeology_reports

{
echo "=== B2.1: All subscriber methods (NO head limit) ==="
grep -rn "def on_event\|def on_npc_spoke\|def on_player_spoke\|def on_claim_event\|def on_actor_attacks\|def on_npc_moved\|def on_npc_interacts\|def on_" backend/app/services/events/ --include="*.py"

echo ""
echo "=== B2.2: All bus.subscribe registrations ==="
grep -rn "bus.subscribe\|event_bus.subscribe\|get_event_bus().subscribe\|_bus.subscribe\|\.subscribe(" backend/app/ --include="*.py" | grep -v test | grep -v __pycache__

echo ""
echo "=== B2.3: Phase 8 handlers ==="
grep -rn "Phase8Handler\|drain_events\|handle_event\|phase_8\|Phase8" backend/app/ --include="*.py" | grep -v test

echo ""
echo "=== B2.4: event.source usage per file ==="
for f in $(find backend/app/services/events -name "*.py" -type f); do
    count=$(grep -c "event.source\|\.source\b" "$f" 2>/dev/null)
    if [ "$count" -gt 0 ]; then
        echo "--- $f ($count matches) ---"
        grep -n "event.source\|\.source\b" "$f"
    fi
done

echo ""
echo "=== B2.5: Subscriber files list (all) ==="
find backend/app/services/events -name "*.py" -type f

echo ""
echo "=== B2.6: perception_filter contract ==="
grep -rn "def filter_perceiving_npcs\|class PerceptionFilter" backend/app/ --include="*.py"
PERCEPTION_FILE=$(grep -rln "def filter_perceiving_npcs" backend/app/ --include="*.py" | head -1)
if [ -n "$PERCEPTION_FILE" ]; then
    echo "File: $PERCEPTION_FILE"
    START_LINE=$(grep -n "def filter_perceiving_npcs" "$PERCEPTION_FILE" | head -1 | cut -d: -f1)
    sed -n "${START_LINE},$((START_LINE + 40))p" "$PERCEPTION_FILE"
fi

echo ""
echo "=== B2.7: propagation.py full logic ==="
PROP_FILE="backend/app/services/social/propagation.py"
if [ -f "$PROP_FILE" ]; then
    cat "$PROP_FILE"
else
    echo "NOT FOUND: $PROP_FILE"
    find backend/app -name "propagation.py" -type f
fi

echo ""
echo "=== B2.8: NPC_SPOKE event_type mapping ==="
grep -rn "NPC_SPOKE\|npc_spoke" backend/app/services/events/ --include="*.py" | head -20

echo ""
echo "=== B2.9: ACTOR_ATTACKS event_type mapping ==="
grep -rn "ACTOR_ATTACKS\|actor_attacks" backend/app/services/events/ --include="*.py" | head -20
} > archaeology_reports/blocker_2_subscribers.txt 2>&1

echo "Report saved to: archaeology_reports/blocker_2_subscribers.txt"
wc -l archaeology_reports/blocker_2_subscribers.txt
```

#### 3.2.2. Что искать в выводе (R2 corrected — три вопроса)

**R2 Question 1: Что `source` означает для каждого типа события?**

Из вывода B2.4 (event.source per file) + B2.8 (NPC_SPOKE) + B2.9 (ACTOR_ATTACKS) — установить:

| Event type | source означает | Семантика |
|---|---|---|
| NPC_SPOKE | ? | speaker (говорящий) |
| ACTOR_ATTACKS | ? | attacker (атакующий) |
| PLAYER_INTERACTS | ? | "player" (literally) |
| COMMUNICATION_CLAIM | ? | ? |
| NPC_MOVED | ? | ? |
| ... | ? | ? |

**R2 Question 2: Где различаются speaker, actor, intent_owner и социальный субъект?**

Из B2.4 + ClaimEventSubscriber.on_npc_spoke logic (если в выводе):
- Для attack intent: `Proposition.subject_id = speaker_id` (атакующий) — speaker = actor.
- Для accuse intent: `Proposition.subject_id = target_id` (обвиняемый) — subject ≠ speaker.
- Это РАЗНЫЕ семантики `subject_id` в зависимости от intent_type.

**R2 Question 3: Есть ли реальная повторяющаяся логика?**

Из B2.4 — если все subscribers делают `event.source → something` одинаково — повторяющаяся логика есть.
Если каждый по-разному — нет.

#### 3.2.3. Решение по AttributionCalculator (после вывода)

| Если факт | Решение |
|---|---|
| source означает разное для разных event types | НЕ создавать AttributionCalculator (нет общей семантики). |
| source означает одинаковое для всех event types | Создавать AttributionCalculator (есть общая операция). |
| Повторяющаяся логика есть | Создавать. |
| Повторяющейся логики нет | НЕ создавать (каждый subscriber уникален). |

---

### 3.3. Блокатор 3 — Avatar self-awareness (с учётом R3)

#### 3.3.1. Команды

```bash
# === BLOCKER 3: Avatar self-awareness (R3 corrected) ===
# Сохранить вывод в: archaeology_reports/blocker_3_self_awareness.txt

mkdir -p archaeology_reports

{
echo "=== B3.1: Existing self-awareness mechanisms ==="
grep -rn "self_action\|self_awareness\|internal_awareness\|bodily_feedback\|proprioception\|body_awareness" backend/app/ --include="*.py"

echo ""
echo "=== B3.2: Avatar/Player subscriptions ==="
grep -rn "subscribe.*player\|subscribe.*avatar\|subscribe.*character\|subscribe.*self" backend/app/ --include="*.py" | grep -v test

echo ""
echo "=== B3.3: MemoryManager full contract ==="
MEMMGR_FILE=$(grep -rln "class MemoryManager" backend/app/ --include="*.py" | head -1)
if [ -n "$MEMMGR_FILE" ]; then
    echo "File: $MEMMGR_FILE"
    START_LINE=$(grep -n "class MemoryManager" "$MEMMGR_FILE" | head -1 | cut -d: -f1)
    sed -n "${START_LINE},$((START_LINE + 80))p" "$MEMMGR_FILE"
fi

echo ""
echo "=== B3.4: MemoryManager.apply method ==="
grep -rn "def apply" backend/app/services/memory/ --include="*.py"
APPLY_FILE=$(grep -rln "def apply" backend/app/services/memory/ --include="*.py" | head -1)
if [ -n "$APPLY_FILE" ]; then
    START_LINE=$(grep -n "def apply" "$APPLY_FILE" | head -1 | cut -d: -f1)
    sed -n "${START_LINE},$((START_LINE + 40))p" "$APPLY_FILE"
fi

echo ""
echo "=== B3.5: Player skip logic in memory ==="
grep -rn 'npc_id.*==.*"player"\|npc_id.*!=.*"player"\|"player".*skip\|skip.*player\|if.*player.*return' backend/app/services/memory/ --include="*.py"

echo ""
echo "=== B3.6: StateApplicator player handling ==="
grep -rn "StateApplicator\|state_applicator" backend/app/ --include="*.py" | grep -v test | head -20
grep -rn 'npc_id.*==.*"player"\|target.*==.*"player"\|"player".*apply' backend/app/services/npc/state_applicator.py 2>/dev/null

echo ""
echo "=== B3.7: AffectiveIntegrator inputs ==="
grep -rn "class AffectiveIntegrator" backend/app/ --include="*.py"
AFFECT_FILE=$(grep -rln "class AffectiveIntegrator" backend/app/ --include="*.py" | head -1)
if [ -n "$AFFECT_FILE" ]; then
    echo "File: $AFFECT_FILE"
    START_LINE=$(grep -n "class AffectiveIntegrator" "$AFFECT_FILE" | head -1 | cut -d: -f1)
    sed -n "${START_LINE},$((START_LINE + 60))p" "$AFFECT_FILE"
fi

echo ""
echo "=== B3.8: Phase 3 Memory Phase ==="
grep -rn "phase_3_memory\|execute_memory_phase\|Phase 3\|memory_phase" backend/app/services/phases/ --include="*.py"
PHASE3_FILE=$(grep -rln "execute_memory_phase\|phase_3_memory" backend/app/services/phases/ --include="*.py" | head -1)
if [ -n "$PHASE3_FILE" ]; then
    echo "File: $PHASE3_FILE"
    cat "$PHASE3_FILE"
fi

echo ""
echo "=== B3.9: Body state changes tracking ==="
grep -rn "body_state.*change\|body.*delta\|hp_delta\|position_delta" backend/app/ --include="*.py" | grep -v test | head -20

echo ""
echo "=== B3.10: EventMemory contract ==="
grep -rn "class EventMemory\|class NarrativeEntry\|class MemoryEntry" backend/app/ --include="*.py"
EVENTMEM_FILE=$(grep -rln "class EventMemory\|class NarrativeEntry\|class MemoryEntry" backend/app/ --include="*.py" | head -1)
if [ -n "$EVENTMEM_FILE" ]; then
    echo "File: $EVENTMEM_FILE"
    START_LINE=$(grep -n "class EventMemory\|class NarrativeEntry\|class MemoryEntry" "$EVENTMEM_FILE" | head -1 | cut -d: -f1)
    sed -n "${START_LINE},$((START_LINE + 40))p" "$EVENTMEM_FILE"
fi
} > archaeology_reports/blocker_3_self_awareness.txt 2>&1

echo "Report saved to: archaeology_reports/blocker_3_self_awareness.txt"
wc -l archaeology_reports/blocker_3_self_awareness.txt
```

#### 3.3.2. Что искать в выводе (R3 corrected — источник информации)

**R3: установить отдельно (не подписка по source):**

| Что установить | Что искать |
|---|---|
| Какие действия совершены общим телом | B3.6 — StateApplicator player handling. B3.9 — body state changes tracking. |
| Какие изменения тела произошли | B3.6, B3.9 — body_state deltas. |
| Какие последствия Avatar воспринимает | B3.3-B3.5 — MemoryManager.apply для player. B3.7 — AffectiveIntegrator inputs. B3.8 — Phase 3 Memory. |
| Какие сведения о намерениях Player недоступны | анализ — что Avatar НЕ видит (intent_owner Player, control_source PLAYER_INPUT). |
| Существующий self-awareness mechanism | B3.1 — grep self_action etc. |
| EventMemory contract | B3.10 — может ли хранить Avatar memory. |

#### 3.3.3. Решение по Avatar self-awareness (после вывода)

| Если факт | Решение |
|---|---|
| MemoryManager.apply работает для player (без skip) | Расширить для Avatar (subject_id=character_id). |
| MemoryManager.apply skip player | Создать отдельный Avatar memory path (минимальный, не subscriber-by-source). |
| Body state changes tracked через StateApplicator | Avatar может читать эти deltas (через callback или Phase 9.1). |
| AffectiveIntegrator принимает body changes | Переиспользовать для Avatar affective update. |
| EventMemory может хранить Avatar memory | Расширить. |
| Ничего не существует | Создать минимальный Avatar awareness path, но НЕ через subscribe-by-source. Через явный callback из Materialization. |

**Ключевое (R3):** subscriber по source=character_id — НЕ заранее утверждённая архитектура. Сначала доказать источник информации.

---

### 3.4. Блокатор 4 — WindupWriteGate (с учётом R4)

#### 3.4.1. Команды

```bash
# === BLOCKER 4: WindupWriteGate (R4 corrected) ===
# Сохранить вывод в: archaeology_reports/blocker_4_windup.txt

mkdir -p archaeology_reports

{
echo "=== B4.1: ActionWindup full class ==="
WINDUP_FILE="backend/app/domain/action_windup.py"
if [ -f "$WINDUP_FILE" ]; then
    cat "$WINDUP_FILE"
else
    echo "NOT FOUND: $WINDUP_FILE"
    find backend/app -name "action_windup.py" -type f
fi

echo ""
echo "=== B4.2: WindupStatus enum ==="
grep -rn "class WindupStatus\|WindupStatus" backend/app/ --include="*.py" | grep -v test

echo ""
echo "=== B4.3: Windup cancel support ==="
grep -rn "windup.*cancel\|cancel.*windup\|WindupStatus.CANCELLED\|CANCELLED.*windup\|cancel_windup" backend/app/ --include="*.py"

echo ""
echo "=== B4.4: Windup interrupt conditions (G3 ADR-O-410) ==="
grep -rn "INTERRUPTED\|interrupt_reason\|G3\|interrupt_windup\|_g3_interrupt" backend/app/domain/action_windup.py backend/app/services/phases/post_decision.py 2>/dev/null

echo ""
echo "=== B4.5: Held intent contract ==="
grep -rn "held_intent_id\|_held_store\|held_intent\|hold_intent" backend/app/ --include="*.py" | grep -v test

echo ""
echo "=== B4.6: WindupWriteGate full logic ==="
POSTDEC_FILE="backend/app/services/phases/post_decision.py"
if [ -f "$POSTDEC_FILE" ]; then
    echo "File: $POSTDEC_FILE"
    # Вывести WindupWriteGate section
    START_LINE=$(grep -n "WindupWriteGate\|windup_write_gate\|_gate_type_is_object_action" "$POSTDEC_FILE" | head -1 | cut -d: -f1)
    if [ -n "$START_LINE" ]; then
        sed -n "${START_LINE},$((START_LINE + 100))p" "$POSTDEC_FILE"
    fi
fi

echo ""
echo "=== B4.7: Phase 7 Windup Resolution ==="
grep -rn "def run_phase_7_windup_resolution\|windup_resolution" backend/app/ --include="*.py"
PHASE7_FILE=$(grep -rln "def run_phase_7_windup_resolution" backend/app/ --include="*.py" | head -1)
if [ -n "$PHASE7_FILE" ]; then
    START_LINE=$(grep -n "def run_phase_7_windup_resolution" "$PHASE7_FILE" | head -1 | cut -d: -f1)
    sed -n "${START_LINE},$((START_LINE + 80))p" "$PHASE7_FILE"
fi

echo ""
echo "=== B4.8: ActionCommitment FSM full transitions ==="
COMMIT_FILE="backend/app/domain/action_commitment.py"
if [ -f "$COMMIT_FILE" ]; then
    cat "$COMMIT_FILE"
fi

echo ""
echo "=== B4.9: Commit points / irreversibility ==="
grep -rn "commit_point\|irreversible\|point_of_no_return\|cannot_cancel\|cannot_interrupt" backend/app/ --include="*.py" | grep -v test

echo ""
echo "=== B4.10: Multiple ATTACK intents same NPC ==="
grep -rn "windup.*attack\|ATTACK.*windup\|multiple.*windup\|windups.*same" backend/app/ --include="*.py" | grep -v test
} > archaeology_reports/blocker_4_windup.txt 2>&1

echo "Report saved to: archaeology_reports/blocker_4_windup.txt"
wc -l archaeology_reports/blocker_4_windup.txt
```

#### 3.4.2. Что искать в выводе (R4 corrected — семантика отмены)

**R4: сначала восстановить:**

| Что восстановить | Что искать |
|---|---|
| Семантика отмены windup | B4.3 — cancel support. B4.4 — interrupt conditions (G3). B4.5 — held_intent может быть отменён. |
| Точка фиксации физического действия (commit point) | B4.9 — commit points / irreversibility. |
| WindupStatus FSM | B4.2 — все статусы. |
| ActionCommitment FSM | B4.8 — full transitions (включая CANCELLED). |
| WindupWriteGate logic | B4.6 — как создаёт windups. |
| Phase 7 Resolution | B4.7 — как завершает windups. |
| Multiple windups | B4.10 — несколько от одного NPC. |

#### 3.4.3. Решение по CANCELLED (после вывода)

| Если факт | Решение |
|---|---|
| Windup имеет INTERRUPTED (через G3) — отмена через interrupt | INTERRUPTED = cancel mechanism. НЕ добавлять CANCELLED. ExecutionLifecycleState mapping: WINDUP_PENDING → INTERRUPTED. |
| ActionCommitment имеет CANCELLED — windup отменяется через commitment | Использовать ActionCommitment CANCELLED. НЕ добавлять в WindupStatus. |
| Никакого cancel mechanism нет | Добавить CANCELLED в WindupStatus (последнее средство, при доказанной необходимости). |
| Commit points существуют | Использовать их для ExecutionLifecycleState mapping. |
| Commit points НЕ существуют | Ввести (после анализа физики действий). |

**Ключевое (R4):** НЕ добавлять CANCELLED автоматически. Сначала семантика отмены.

---

## §4. БЛОКАТОРЫ 5-7 — ПАРАЛЛЕЛЬНО (НЕ БЛОКИРУЮТ MVP 0-4)

### 4.1. Блокатор 5 — AffectiveIntegrator inputs

```bash
# === BLOCKER 5: AffectiveIntegrator inputs ===
# Сохранить: archaeology_reports/blocker_5_affective.txt

mkdir -p archaeology_reports

{
echo "=== B5.1: AffectiveIntegrator class ==="
grep -rln "class AffectiveIntegrator" backend/app/ --include="*.py"
AFFECT_FILE=$(grep -rln "class AffectiveIntegrator" backend/app/ --include="*.py" | head -1)
if [ -n "$AFFECT_FILE" ]; then
    echo "File: $AFFECT_FILE"
    cat "$AFFECT_FILE"
fi

echo ""
echo "=== B5.2: integrate_affective_pressure signature ==="
grep -B5 -A30 "def integrate_affective_pressure" backend/app/ -r --include="*.py"

echo ""
echo "=== B5.3: All integrate_affective_pressure calls ==="
grep -rn "integrate_affective_pressure\|affective_integrator\." backend/app/ --include="*.py" | grep -v test

echo ""
echo "=== B5.4: AffectiveImprint contract ==="
grep -rln "class AffectiveImprint" backend/app/ --include="*.py"
AIMPRINT_FILE=$(grep -rln "class AffectiveImprint" backend/app/ --include="*.py" | head -1)
if [ -n "$AIMPRINT_FILE" ]; then
    echo "File: $AIMPRINT_FILE"
    START_LINE=$(grep -n "class AffectiveImprint" "$AIMPRINT_FILE" | head -1 | cut -d: -f1)
    sed -n "${START_LINE},$((START_LINE + 30))p" "$AIMPRINT_FILE"
fi

echo ""
echo "=== B5.5: Phase 9.1 Affective Pipeline ==="
grep -rn "phase_9_1\|affective_pipeline\|run_affective\|Phase9Deps" backend/app/ --include="*.py" | grep -v test
} > archaeology_reports/blocker_5_affective.txt 2>&1

echo "Report saved: archaeology_reports/blocker_5_affective.txt"
wc -l archaeology_reports/blocker_5_affective.txt
```

### 4.2. Блокатор 6 — scan_affective_resonance interface

```bash
# === BLOCKER 6: scan_affective_resonance ===
# Сохранить: archaeology_reports/blocker_6_resonance.txt

mkdir -p archaeology_reports

{
echo "=== B6.1: scan_affective_resonance definition ==="
grep -rln "def scan_affective_resonance" backend/app/ --include="*.py"
RESONANCE_FILE=$(grep -rln "def scan_affective_resonance" backend/app/ --include="*.py" | head -1)
if [ -n "$RESONANCE_FILE" ]; then
    echo "File: $RESONANCE_FILE"
    grep -B5 -A30 "def scan_affective_resonance" "$RESONANCE_FILE"
fi

echo ""
echo "=== B6.2: All scan_affective_resonance calls ==="
grep -rn "scan_affective_resonance" backend/app/ --include="*.py" | grep -v test

echo ""
echo "=== B6.3: AffectiveResonance contract ==="
grep -rln "class AffectiveResonance" backend/app/ --include="*.py"
if [ -n "$RESONANCE_FILE" ]; then
    grep -B2 -A20 "class AffectiveResonance" "$RESONANCE_FILE"
fi

echo ""
echo "=== B6.4: distort_pressure ==="
grep -B5 -A15 "def distort_pressure" backend/app/ -r --include="*.py"

echo ""
echo "=== B6.5: affect.py full contract ==="
AFFECT_PY=$(find backend/app -name "affect.py" -path "*/services/*" | head -1)
if [ -n "$AFFECT_PY" ]; then
    echo "File: $AFFECT_PY"
    cat "$AFFECT_PY"
fi
} > archaeology_reports/blocker_6_resonance.txt 2>&1

echo "Report saved: archaeology_reports/blocker_6_resonance.txt"
wc -l archaeology_reports/blocker_6_resonance.txt
```

### 4.3. Блокатор 7 — BeliefCrystallizationEngine interface

```bash
# === BLOCKER 7: BeliefCrystallizationEngine ===
# Сохранить: archaeology_reports/blocker_7_belief.txt

mkdir -p archaeology_reports

{
echo "=== B7.1: BeliefCrystallizationEngine class ==="
grep -rln "class BeliefCrystallizationEngine" backend/app/ --include="*.py"
BCE_FILE=$(grep -rln "class BeliefCrystallizationEngine" backend/app/ --include="*.py" | head -1)
if [ -n "$BCE_FILE" ]; then
    echo "File: $BCE_FILE"
    cat "$BCE_FILE"
fi

echo ""
echo "=== B7.2: crystallize method ==="
grep -B5 -A30 "def crystallize" backend/app/ -r --include="*.py"

echo ""
echo "=== B7.3: All crystallize calls ==="
grep -rn "\.crystallize\(\|BeliefCrystallizationEngine" backend/app/ --include="*.py" | grep -v test

echo ""
echo "=== B7.4: CrystallizedBelief ==="
grep -rn "CrystallizedBelief\|crystallized_belief" backend/app/ --include="*.py" | grep -v test

echo ""
echo "=== B7.5: Phase 9 Belief Crystallization ==="
grep -rn "belief_crystallization\|crystallize\|L2.5" backend/app/services/phases/ --include="*.py"
} > archaeology_reports/blocker_7_belief.txt 2>&1

echo "Report saved: archaeology_reports/blocker_7_belief.txt"
wc -l archaeology_reports/blocker_7_belief.txt
```

---

## §5. БЛОКАТОР 8 — КОДОВАЯ АРХЕОЛОГИЯ ОТДЕЛЬНО (с учётом R5+R6)

### 5.1. Этап 1 — Кодовая археология (БЕЗ Python-блока, R6 corrected)

```bash
# === BLOCKER 8 (Stage 1): agent_id code archaeology ===
# Сохранить: archaeology_reports/blocker_8a_agent_id_code.txt
# R6: NO Python execution — code grep only

mkdir -p archaeology_reports

{
echo "=== B8.1: All agent_id occurrences (NO head limit) ==="
grep -rn "agent_id" backend/app/ --include="*.py" | grep -v test | grep -v __pycache__

echo ""
echo "=== B8.2: All listener_id occurrences ==="
grep -rn "listener_id" backend/app/ --include="*.py" | grep -v test | grep -v __pycache__

echo ""
echo "=== B8.3: All BeliefRevisionEngine.revise calls ==="
grep -rn "BeliefRevisionEngine.*revise\|\.revise(" backend/app/ --include="*.py" | grep -v test

echo ""
echo "=== B8.4: All EpistemicContextResolver.resolve calls ==="
grep -rn "EpistemicContextResolver.*resolve\|\.resolve(agent_id" backend/app/ --include="*.py" | grep -v test

echo ""
echo "=== B8.5: All hardcoded 'player' in agent_id/listener_id context ==="
grep -rn 'agent_id.*=.*"player"\|agent_id.*==.*"player"\|listener_id.*=.*"player"\|listener_id.*==.*"player"' backend/app/ --include="*.py" | grep -v test

echo ""
echo "=== B8.6: EpistemicRecord class ==="
EPI_FILE=$(grep -rln "class EpistemicRecord" backend/app/ --include="*.py" | head -1)
if [ -n "$EPI_FILE" ]; then
    echo "File: $EPI_FILE"
    START_LINE=$(grep -n "class EpistemicRecord" "$EPI_FILE" | head -1 | cut -d: -f1)
    sed -n "${START_LINE},$((START_LINE + 40))p" "$EPI_FILE"
fi

echo ""
echo "=== B8.7: EpistemicStore class ==="
EPISTORE_FILE=$(grep -rln "class EpistemicStore" backend/app/ --include="*.py" | head -1)
if [ -n "$EPISTORE_FILE" ]; then
    echo "File: $EPISTORE_FILE"
    START_LINE=$(grep -n "class EpistemicStore" "$EPISTORE_FILE" | head -1 | cut -d: -f1)
    sed -n "${START_LINE},$((START_LINE + 60))p" "$EPISTORE_FILE"
fi

echo ""
echo "=== B8.8: EpistemicStore.from_dict contract ==="
grep -B5 -A30 "def from_dict" backend/app/ -r --include="*.py" | grep -A30 -B5 "EpistemicStore"

echo ""
echo "=== B8.9: scene_state loading contract ==="
grep -rn "load_scene_state\|save_scene_state\|load_scene_at\|scene_state.*load\|scene_state.*save" backend/app/ --include="*.py" | grep -v test | head -20

echo ""
echo "=== B8.10: NPC registry / npc_ids ==="
grep -rn "npc_registry\|all_npc_ids\|npc_ids\|get_all_npcs\|npc_list" backend/app/ --include="*.py" | grep -v test | head -20

echo ""
echo "=== B8.11: ClaimEventSubscriber.on_npc_spoke full logic ==="
CLAIM_FILE=$(grep -rln "class ClaimEventSubscriber" backend/app/ --include="*.py" | head -1)
if [ -n "$CLAIM_FILE" ]; then
    echo "File: $CLAIM_FILE"
    START_LINE=$(grep -n "def on_npc_spoke" "$CLAIM_FILE" | head -1 | cut -d: -f1)
    if [ -n "$START_LINE" ]; then
        sed -n "${START_LINE},$((START_LINE + 60))p" "$CLAIM_FILE"
    fi
fi

echo ""
echo "=== B8.12: dialogue_memory_subscriber full logic ==="
DM_FILE=$(grep -rln "class.*Memory.*Subscriber\|class.*DialogueMemory" backend/app/ --include="*.py" | head -1)
if [ -n "$DM_FILE" ]; then
    echo "File: $DM_FILE"
    cat "$DM_FILE"
fi
} > archaeology_reports/blocker_8a_agent_id_code.txt 2>&1

echo "Report saved: archaeology_reports/blocker_8a_agent_id_code.txt"
wc -l archaeology_reports/blocker_8a_agent_id_code.txt
```

### 5.2. Этап 2 — Анализ исторических данных (после этапа 1, отдельный проверяемый скрипт)

**R6: НЕ запускать до завершения этапа 1 и подготовки отдельного скрипта.**

После этапа 1 (B8.1-B8.12) — на основе установленных контрактов:
1. `EpistemicStore.from_dict()` контракт — verified.
2. `scene_state` loading contract — verified.
3. NPC registry — verified.

Затем подготовить отдельный read-only скрипт `classify_agent_id_records.py`:

```python
# classify_agent_id_records.py — R5+R6 compliant
# Read-only classification script
# Сохраняет исходные данные, НЕ мигрирует

import json
from pathlib import Path

# Загрузить контракты (после этапа 1)
# EpistemicStore.from_dict — verified contract
# scene_state path — verified contract
# NPC registry — verified contract

def classify_agent_id_record(record, npc_registry, player_session_id):
    """Классификация записи agent_id (R5 corrected).
    
    Возвращает ClassificationResult с:
    - original_agent_id (сохранён)
    - original_key (сохранён)
    - classification (A/B/C/D/E)
    - migration_target (если однозначная)
    - ambiguity_context (если D — полный контекст)
    - reversible (True всегда)
    """
    original = record.agent_id
    original_key = (record.agent_id, record.proposition)
    
    # Класс A: NPC
    if original in npc_registry:
        return ClassificationResult(
            original_agent_id=original,
            original_key=original_key,
            classification="A_NPC",
            migration_target=original,  # без изменений
            ambiguity_context=None,
            reversible=True,
        )
    
    # Класс B: Player (explicit, однозначный)
    if original == "player" and is_player_path_context(record):
        return ClassificationResult(
            original_agent_id=original,
            original_key=original_key,
            classification="B_PLAYER_EXPLICIT",
            migration_target=f"player:{player_session_id}",  # session_id, не name
            ambiguity_context=None,
            reversible=True,
        )
    
    # Класс C: Avatar (новые записи, post-R5.4)
    if original.startswith("avatar:"):
        return ClassificationResult(
            original_agent_id=original,
            original_key=original_key,
            classification="C_AVATAR",
            migration_target=original,
            ambiguity_context=None,
            reversible=True,
        )
    
    # Класс D: Ambiguous — СОХРАНИТЬ СОСТОЯНИЕ ДАННЫХ
    if original == "player" and not is_player_path_context(record):
        return ClassificationResult(
            original_agent_id=original,
            original_key=original_key,
            classification="D_AMBIGUOUS",
            migration_target=None,  # НЕ мигрировать автоматически
            ambiguity_context={
                "original_agent_id": original,
                "original_key": str(original_key),
                "context": get_record_context(record),
                "source_file": get_record_source(record),
                "tick": get_record_tick(record),
                "session_marker": get_session_marker(),
            },
            reversible=True,
        )
    
    # Класс E: System
    if is_system_agent_id(original):
        return ClassificationResult(
            original_agent_id=original,
            original_key=original_key,
            classification="E_SYSTEM",
            migration_target=original,
            ambiguity_context=None,
            reversible=True,
        )
    
    # Неизвестный — НЕ превращать в Avatar или Player
    return ClassificationResult(
        original_agent_id=original,
        original_key=original_key,
        classification="X_UNKNOWN",
        migration_target=None,
        ambiguity_context={
            "original_agent_id": original,
            "original_key": str(original_key),
            "reason": "no_classification_matched",
        },
        reversible=True,
    )


@dataclass(frozen=True)
class ClassificationResult:
    """Результат классификации — R5 corrected.
    
    Неоднозначность — явное состояние данных, не просто новое имя.
    """
    original_agent_id: str
    original_key: tuple
    classification: str
    migration_target: Optional[str]
    ambiguity_context: Optional[Dict[str, Any]]
    reversible: bool
```

**R5 garanties:**
- `original_agent_id` сохранён.
- `original_key` сохранён.
- `ambiguity_context` — полный контекст для D класса.
- `reversible=True` всегда.
- Idempotency: повторный запуск не меняет уже классифицированные записи.
- Никакой миграции — только классификация.

**Представить Мастеру:**
1. Таблица «класс — количество записей».
2. Список неоднозначных записей (D) с полным контекстом.
3. Решение по каждой D записи — оставить или resolver вручную.

**Миграция ТОЛЬКО после утверждения Мастером.**

---

## §6. ЭТАПЫ 0-1 — ЛОКАЛЬНЫЕ АУДИТЫ (НЕ ЗАВИСЯТ ОТ БЛОКАТОРОВ)

### 6.1. Этап 0 — Identity contract — локальный аудит

**Затрагиваемые существующие контракты:**
- `backend/app/domain/control_source.py` — ControlSource enum, _PLAYER_ACTORS, resolve_control_source.
- `backend/app/services/player_avatar_service.py` — value coupling (line 138).
- `backend/app/models/schemas.py` — PlayerSession (player_name vs session_id).

**Локальный аудит (выполнить перед реализацией этапа 0):**

```bash
# === STAGE 0 LOCAL AUDIT ===
mkdir -p archaeology_reports

{
echo "=== S0.1: ControlSource full contract ==="
cat backend/app/domain/control_source.py

echo ""
echo "=== S0.2: player_avatar_service value coupling ==="
grep -n "npc_id.*!=.*player_name\|npc_id.*==.*player_name" backend/app/services/player_avatar_service.py

echo ""
echo "=== S0.3: PlayerSession contract ==="
grep -B2 -A20 "class PlayerSession" backend/app/models/schemas.py

echo ""
echo "=== S0.4: player_name vs session_id usage ==="
grep -rn "player_name\|session_id\|player_session" backend/app/ --include="*.py" | grep -v test | head -30

echo ""
echo "=== S0.5: CharacterProfile character_id ==="
grep -B2 -A30 "class CharacterProfile" backend/app/models/character.py

echo ""
echo "=== S0.6: InterventionEvent contract ==="
grep -B2 -A30 "class InterventionEvent" backend/app/contracts/interventions.py 2>/dev/null
} > archaeology_reports/stage_0_local_audit.txt 2>&1

echo "Report saved: archaeology_reports/stage_0_local_audit.txt"
wc -l archaeology_reports/stage_0_local_audit.txt
```

**Что проверить перед реализацией этапа 0:**
- `ControlSource` — добавить AVATAR_INITIATIVE, UNKNOWN. Не ломает существующие values.
- `_PLAYER_ACTORS = frozenset({"player"})` — оставить.
- `resolve_control_source` — добавить ветки AVATAR_INITIATIVE (через AvatarCharacterRegistry) и UNKNOWN (default).
- `player_avatar_service.py:138` — убрать `npc_id != player_name: return None`. Использовать AvatarCharacterRegistry lookup.
- `PlayerSession.player_name` — НЕ использовать как stable ID. Использовать `session_id` (если есть) или другой stable identifier.

**Гейт этапа 0:** локальный аудит green, regression IPT 54/0/0 сохранён.

### 6.2. Этап 1 — Intention contract — локальный аудит

**Затрагиваемые существующие контракты:**
- `backend/app/domain/action_commitment.py` — FSM transitions (для pattern reference).
- `backend/app/domain/action_windup.py` — WindupStatus (для pattern reference).
- `backend/app/models/npc_state.py:133` — WillState (не путать с IntentionLifecycleState).
- `backend/app/models/npc_state.py:105` — Intent enum.

**Локальный аудит (выполнить перед реализацией этапа 1):**

```bash
# === STAGE 1 LOCAL AUDIT ===
mkdir -p archaeology_reports

{
echo "=== S1.1: ActionCommitment FSM (для pattern reference) ==="
cat backend/app/domain/action_commitment.py

echo ""
echo "=== S1.2: ActionWindup + WindupStatus ==="
cat backend/app/domain/action_windup.py

echo ""
echo "=== S1.3: WillState enum (НЕ путать с IntentionLifecycleState) ==="
grep -B2 -A30 "class WillState" backend/app/models/npc_state.py

echo ""
echo "=== S1.4: Intent enum ==="
grep -B2 -A30 "class Intent" backend/app/models/npc_state.py

echo ""
echo "=== S1.5: NPCState intent fields (intent_formed_at etc) ==="
grep -n "intent_formed_at\|intent_target\|intent_duration\|intent_progress\|last_intent_change" backend/app/models/npc_state.py

echo ""
echo "=== S1.6: DecisionResult contract ==="
grep -B2 -A30 "class DecisionResult" backend/app/services/npc/decision_hub.py 2>/dev/null
} > archaeology_reports/stage_1_local_audit.txt 2>&1

echo "Report saved: archaeology_reports/stage_1_local_audit.txt"
wc -l archaeology_reports/stage_1_local_audit.txt
```

**Что проверить перед реализацией этапа 1:**
- `ActionCommitment` FSM — transitions для pattern reference (не storage).
- `WindupStatus` — для ExecutionLifecycleState pattern.
- `WillState` — НЕ путать с IntentionLifecycleState (разные семантики).
- `Intent` enum — не путать с ActionClass.
- `intent_formed_at` — существующий continuity mechanism для NPC.
- `DecisionResult` — может ли служить model для AvatarIntention content fields.

**Гейт этапа 1:** локальный аудит green, IntentionRelevanceChecker без scene_state, continuity test green, regression IPT сохранён.

### 6.3. Этапы 0-1 не ждут блокаторов 1-8

Мастер: «Разрешить их реализацию по собственным локальным аудитам, не ждать всех восьми блокаторов.»

**Stage 0 и Stage 1 могут идти параллельно с археологией блокаторов 1-8.**

Но: каждый файл, который затрагивается в этапе 0-1, должен быть проверен локальным аудитом (S0.* и S1.* команды).

---

## §7. ФОРМАТ ОТЧЁТА (VERIFIED из вердикта)

### 7.1. Формат для каждого блокатора

Для каждого блокатора (после запуска команд и возврата вывода Мастером):

```markdown
## Блокатор N — [название]

### Команда
[команда из §3 или §4 или §5]

### Вывод
[полный вывод или ссылка на файл archaeology_reports/blocker_N_*.txt]

### Подтверждённые факты
- Факт 1 (VERIFIED): ...
- Факт 2 (VERIFIED): ...
- Факт 3 (PARTIALLY VERIFIED): ...

### Причинная цепочка
Источник → вызов → преобразование → состояние → событие → подписчик → память/убеждение

[заполненная цепочка]

### Неустановленные участки
- Участок 1 (NEEDS ARCHAEOLOGY): ...
- Участок 2 (NEEDS ARCHAEOLOGY): ...

### Архитектурное следствие
[какой контракт R5.4 затронут, какое решение принято]
```

### 7.2. Проверка Мастером

Мастер: «Я буду проверять не количество найденных классов, а доказанность связей между ними.»

**Критерии проверки:**
- Причинная цепочка заполнена полностью (или явно отмечены неустановленные участки).
- Каждый факт имеет статус VERIFIED / PARTIALLY VERIFIED / NEEDS ARCHAEOLOGY.
- Архитектурное следствие следует из фактов, не из предположений.
- Решение A/B (для блокатора 1) — по семантическому контракту (R1), не по числу обращений.
- Решение по AttributionCalculator (для блокатора 2) — по трём вопросам R2.
- Решение по Avatar self-awareness (для блокатора 3) — по источнику информации R3.
- Решение по Windup CANCELLED (для блокатора 4) — по семантике отмены R4.
- agent_id классификация (для блокатора 8) — с сохранением неоднозначности как состояния данных R5.

---

## §8. ССЫЛКИ

### 8.1. Вердикт Мастера по R5.5

- R5.5 APPROVED WITH CORRECTIONS.
- GO на read-only археологию.
- 6 корректировок R1-R6.
- 3 исправления плана.
- Порядок запуска: 1-4 первыми, 5-7 параллельно, 8 отдельно, этапы 0-1 независимо.
- Формат отчёта: блокатор + команда + вывод + факты + цепочка + неустановленные + следствие.
- «Я буду проверять не количество найденных классов, а доказанность связей между ними.»
- Главное: сначала выясняем, что реально делает код, затем решаем, что ему нужно добавить.
- Граница: «Player может управлять телом. Но управление телом не означает владение сознанием Avatar.»

### 8.2. ADR atlas references
- ADR-O-344, ADR-O-407, ADR-O-310, ADR-O-313, ADR-O-349, ADR-O-351, ADR-O-365, ADR-O-399, ADR-O-410, ADR-O-421, ADR-O-432, ADR-O-433, ADR-O-435, ADR-O-436, DLG-1 (S388)

### 8.3. R5.1-R5.5 references
- ADR-O-435-R5.1.md — architectural design
- ADR-O-435-R5.2.md — Implementation Readiness
- ADR-O-435-R5.3.md — Пять работ к MVP
- ADR-O-435-R5.4.md — Архитектурная корректировка + археология
- ADR-O-435-R5.5.md — Археологический скрипт + план реализации MVP

### 8.4. Code archaeology source
- `/home/z/my-project/scripts/archaeology_digest.md` (6378 строк)

### 8.5. Session history
- S399 — R5.1 architectural design
- S400 — R5.2 Implementation Readiness
- S401 — R5.3 Пять работ к MVP
- S402 — R5.4 Архитектурная корректировка + археология
- S403 — R5.5 Археологический скрипт + план реализации MVP
- S404 — R5.6 Корректировки R5.5 + обновлённые команды археологии (этот документ)

---

**Document end.** ADR-O-435-R5.6 — КОРРЕКТИРОВКИ R5.5 + ОБНОВЛЁННЫЕ КОМАНДЫ АРХЕОЛОГИИ, статус: готов к запуску arch археологии на production. Код не менялся. Дождаться вывода команд от Мастера.

**Финальный принцип (VERIFIED — утверждён Мастером):**

> Player может управлять телом. Но управление телом не означает владение сознанием Avatar.

R5.6 готовит доказательные команды для установления фактов существующего кода. Археология → факты → архитектурные решения → реализация.