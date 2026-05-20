# АРХИТЕКТУРНЫЙ УСТАВ ENIGMA

**Статус:** Исполняемый контракт.  
**Нарушение любого пункта = архитектурный баг.**  
**Прочитать перед каждой сессией.**

---

## 1. ИЕРАРХИЯ СЛОЁВ (кто кого знает)

```
frontend/                 ← НЕ ЗНАЁТ backend/app/ вообще
    ↓ HTTP + DTO
backend/app/
    ├── domain/           ← Не знает ни о ком. Чистые dataclass.
    ├── models/           ← Знает domain/. Не знает services/.
    ├── services/         ← Знает models/ и domain/. Не знает frontend/.
    │   ├── events/       ← Шина. Все события = EventDTO.
    │   ├── memory/       ← Только MemoryManager пишет в память.
    │   ├── npc/          ← DecisionHub читает state, создаёт CommunicationIntent.
    │   ├── verbalization/← Читает CommunicationIntent, строит промпт.
    │   ├── llm/          ← Получает промпт, возвращает текст.
    │   └── ...
    └── api/              ← Знает services/. Принимает DTO, выдаёт DTO.
```

**Закон 1.1:** `frontend/` не импортирует `backend/app/` ни под каким предлогом. Даже `constants`. Даже `typing`. Нет.

**Закон 1.2:** `domain/` не импортирует `models/`, `services/`, `api/`. Нарушение = циклическая зависимость.

**Закон 1.3:** `services/` общаются друг с другом через `EventBus` или через явные DTO. Никаких прямых вызовов `service_a.foo()` из `service_b` без DTO.

---

## 2. ПРОТОКОЛЫ ДАННЫХ (единый язык)

### 2.1 EventDTO — паспорт события

Все события в системе = `EventDTO`. Никаких `List[dict]`, `**kwargs`, `Any`.

```python
@dataclass(frozen=True)
class EventDTO:
    id: UUID
    type: str                    # EventType.value
    source: str                  # player_name | npc_id
    timestamp: float
    payload: dict
    visibility: Literal["public", "private", "whisper"]
    radius: float
    persistence_level: Literal["working", "session", "campaign"]
```

**Закон 2.1.1:** `EventBus.publish()` принимает только `EventDTO`. Всё остальное — `TypeError`.

**Закон 2.1.2:** `WorldTickEngine` не возвращает `List[dict]`. Он создаёт `List[EventDTO]` и публикует каждый через `EventBus`.

### 2.2 CommunicationIntent — решение NPC

Создаётся `DecisionHub` ПОСЛЕ `TopicExtractor`. Не допускается пустой `topic`.

```python
@dataclass(frozen=True)
class CommunicationIntent:
    speaker: str
    audience: str
    topic: str                   # из TopicExtractor, не пустой
    intent_type: str
    emotional_state: str
    exposure_level: ExposureLevel
```

**Закон 2.2.1:** `topic` заполняется на фазе Pre-Decision (до DecisionHub). Verbalization не придумывает тему.

**Закон 2.2.2:** `exposure_level.semantic` определяет, кто услышит реплику. `physical_radius` — потолок, не правило.

### 2.3 DTO границы

| Граница | Вход | Выход |
|---------|------|-------|
| Frontend → Backend | `IntentDTO` | — |
| Backend → Frontend | — | `WorldSnapshotDTO` |
| Decision → Event | `CommunicationIntent` | `EventDTO` (через IntentEventAdapter) |
| Event → Memory | `EventDTO` | обновлённый `NPCState` |

**Закон 2.3.1:** На границе слоёв только DTO. Никаких внутренних моделей (`NPCState`, `EventMemory`) не пересекает границу.

---

## 3. ФАЗОВАЯ МОДЕЛЬ (Tick Orchestrator)

Один тик = строгая последовательность. Никаких «свободных вызовов» вне фаз.

```
ФАЗА 1: Input
    Источники: PlayerAction, WorldTick, Combat
    Выход: EventDTO

ФАЗА 2: EventBus (первичная волна)
    event_bus.publish(event)

ФАЗА 3: Memory Phase
    MemoryProcessor.apply(event, npc_state)
    → обновляет NPCState ДО принятия решения

ФАЗА 4: Pre-Decision
    TopicExtractor читает STM + L2
    → формирует topic

ФАЗА 5: Decision
    DecisionHub.compute(topic=topic, state=fresh_state)
    → создаёт CommunicationIntent

ФАЗА 6: Post-Decision
    IntentEventAdapter: CommunicationIntent → EventDTO

ФАЗА 7: EventBus (вторичная волна)
    event_bus.publish(event_from_npc)

ФАЗА 8: Handlers
    Явно подписанные обработчики (memory, social, scene, reaction)

ФАЗА 9: Integration
    WorldSnapshotBuilder: events → state
    → собирает WorldSnapshotDTO

ФАЗА 10: Persistence
    SQLite — atomic commit (runtime truth)
    YAML — snapshot/export (для человека)
```

**Закон 3.1:** `DecisionHub` работает на фазе 5, НЕ на фазе 3. Он читает СВЕЖИЙ state после `MemoryProcessor`. Лаг в 1 тик = баг.

**Закон 3.2:** `TopicExtractor` работает на фазе 4, НЕ в verbalization. `CommunicationIntent.topic` не может быть пустым.

**Закон 3.3:** `IntentEventAdapter` — единственная точка превращения решения в событие. Никаких `List[dict]` больше нигде.

**Закон 3.4:** `WorldSnapshotBuilder` читает только финальное состояние. Не лезет в random сервисы.

---

## 4. ПАМЯТЬ (правила записи и чтения)

### 4.1 Иерархия памяти

```
STM (DialogueSession)        ← RAM, per-NPC, 5 реплик
    ↓ при завершении диалога
L2 (narrative_cache)         ← RAM, per-NPC, Tuple[EventMemory]
    ↓ при promote (importance > threshold)
Campaign (YAML/SQLite)       ← долгосрочная, per-NPC
    ↓ при сжатии
Abstract / Trait             ← identity, черты
```

**Закон 4.1.1:** `WorkingMemory` — per-NPC, НЕ per-campaign. Общий буфер на всех = уничтожение индивидуальности.

**Закон 4.1.2:** Только `MemoryManager` пишет в память. Никаких прямых `write_session_memory()` из `game_loop` или `processor`.

**Закон 4.1.3:** `MemoryPromotionEngine` — отдельный процесс, НЕ метод `LayeredMemory`. Переносит session → campaign по правилам.

### 4.2 Persistence

**Закон 4.2.1:** SQLite = runtime truth. Atomic commit. Всё или ничего.

**Закон 4.2.2:** YAML = snapshot/export для человека. Не пишется напрямую `MemoryProcessor`'ом. Это дамп из SQLite.

**Закон 4.2.3:** Нет транзакции = нет сохранения. Три отдельных JSON-файла = баг рассинхронизации.

---

## 5. EVENTBUS (единая шина)

**Закон 5.1:** `EventBus.publish()` — единственная точка входа событий в систему. Никаких прямых вызовов обработчиков вне шины.

**Закон 5.2:** Обработчики подписаны явно:

```python
event_bus.subscribe(EventType.NPC_SPOKE, memory_manager.handle)
event_bus.subscribe(EventType.NPC_SPOKE, social_engine.handle)
```

**Закон 5.3:** `EventBus` — синхронный. `publish()` вызывает обработчики немедленно. Нет фоновых очередей без явного `enqueue_for_tick`.

---

## 6. FRONTEND / BACKEND (граница)

**Закон 6.1:** Frontend работает только с DTO. Не знает `NPCState`, `EventMemory`, `DecisionHub`.

**Закон 6.2:** `api_client.py` — единственный канал. Никаких прямых импортов `app.services` во frontend.

**Закон 6.3:** `WorldSnapshotDTO` содержит только то, что видит frontend: позиции, видимые NPC, текст событий, доступные действия. Не содержит `trust`, `fear`, `secret_events`.

---

## 7. ЗАПРЕТЫ (категорически)

| № | Запрет | Последствие нарушения |
|---|--------|----------------------|
| 7.1 | Frontend импортирует `app/` | Разрушение границы, невозможность замены frontend |
| 7.2 | `topic` пустой в `CommunicationIntent` | LLM плывёт по ассоциациям, галлюцинации |
| 7.3 | `EventBus` обходится прямым вызовом | Двойной путь данных, race condition |
| 7.4 | `MemoryManager` обходится прямой записью | Дубли записей, рассинхрон слоёв |
| 7.5 | `LayeredMemory` без `promote` | Память = лог, не система. NPC забывают всё |
| 7.6 | `save_scene` + `save_npcs` без транзакции | Разорванная реальность при краше |
| 7.7 | `DecisionHub` до `MemoryProcessor` | Решение на устаревшем state, лаг 1 тик |
| 7.8 | `WorldTick` возвращает `List[dict]` | События NPC = сироты, никто не обрабатывает |
| 7.9 | `ResonanceEngine` / `ContradictionResolver` без lifecycle hooks | Мёртвый код, никто не вызывает |
| 7.10 | YAML как runtime truth | Race conditions, нет транзакций, повреждение данных |

---

## 8. ДОБАВЛЕНИЕ НОВОГО МОДУЛЯ

Шаг 1: Определить, в каком слое живёт (domain / models / services / api).  
Шаг 2: Проверить, не нарушает ли законы 1–7.  
Шаг 3: Определить DTO на входе и выходе.  
Шаг 4: Определить фазу в Tick Orchestrator (если применимо).  
Шаг 5: Явно подписать на EventBus (если применимо).  
Шаг 6: Зафиксировать в этом документе, если меняет архитектуру.

---

## 9. РЕДАКЦИЯ ЭТОГО ДОКУМЕНТА

Изменение любого пункта требует:  
1. Обоснования (какой баг лечит).  
2. Проверки на нарушение других пунктов.  
3. Обновления всех зависимых диаграмм.  
4. Фиксации в `docs/АРХИТЕКТУРНЫЙ_УСТАВ_изменения.md`.



---

## 10. Визуальная Доктрина ENIGMA: Импрессионизм и Двойная Истина
Разделение слоев:
SurfaceLogic (NumPy: .npy) — честная физика (шум, трение, коллизия). Генерируется процедурно из TileDTO.
SurfaceVisual (PNG) — намеренная ложь (стиль, свет, грязь). Генерируется ИИ/художником в стиле Disco Elysium.
Параметры Pseudo-Albedo:
Контраст: 0.45 – 0.6
Насыщенность: -20% от нейтрали
Micro AO: 5–10% (след кисти, не свет)
Свет = Маска внимания. Никакого реал-тайм освещения. Только аддитивные радиальные градиенты (BLEND_ADD).
LUT = Центр управления. Глобальный фильтр (Color Grading) определяет психологию локации. Минимум 3 профиля: Таверна (тепло), Улица (нейтрально), Подземелье (холод/зелень).
Dithering: Bayer 8x8 после LUT, до UI. Квантование градиента, а не шум.
Порядок рендера: База -> Персонажи -> LUT -> Локальный свет -> Dithering.

---

*Версия: 1.5*  
*Дата: 2026-05-05*  
*Следующая проверка: каждые 5 шагов разработки*

---

## 11. АРХИТЕКТУРНОЕ ПРИНУЖДЕНИЕ (Enforcement Layer)

**Закон 11.1:** Устав определяет онтологию. Контракты определяют разрешения. Врата определяют физическую возможность. Нарушение любого слоя = остановка разработки.

**Закон 11.2:** Любое изменение, затрагивающее домены (fear, trust, pain, will, memory, intent) или добавляющее новые DTO/фазы, требует заполнения ADR-PRE-FLIGHT CHECKLIST (см. РЕЖИМ РАБОТЫ.md, Секция 12) перед написанием кода.

**Закон 11.3:** Слияние кода запрещено без прохождения PowerShell Gates (См. РЕЖИМ РАБОТЫ.md, Секция 12). Скрытые связи (Hidden Coupling) должны быть переведены в поисково-наблюдаемые.

**Закон 11.4:** Каждое архитектурное изменение должно сопровождаться созданием `docs\Tasks\ADR-000_IMPACT_TEMPLATE.md`. Архитектурная амнезия недопустима.

---

*Версия: 1.6*  
*Дата: 2026-05-11*  
*Следующая проверка: каждые 5 шагов разработки*
```