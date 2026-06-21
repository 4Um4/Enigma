# АРХИТЕКТУРНЫЙ УСТАВ ENIGMA

**Статус:** Исполняемый контракт.  
**Нарушение любого пункта = архитектурный баг.**  
**Прочитать перед каждой сессией.**

## §ENIGMA-001: Приоритет Причинной Глубины

Реалистичность не является самостоятельным критерием принятия архитектурных решений.

Основной критерий:
увеличивает ли изменение количество устойчивых причинных структур мира.

Под устойчивыми причинными структурами понимаются:
memory,
trust,
debt,
attachment,
reputation,
belief,
cultural_norm,
collective_memory
и иные механизмы, способные сохранять и переносить последствия во времени.

Вторичный критерий:
увеличивает ли изменение длину или количество долгоживущих причинных цепочек между событием и его историческими последствиями.

ADR считается предпочтительным, если он:
- создаёт новые причинные структуры;
- усиливает существующие причинные структуры;
- увеличивает наблюдаемость или управляемость причинных структур;
- увеличивает длину причинных цепочек.

Повышение реалистичности само по себе не является достаточным основанием для принятия ADR.

---

## §ENIGMA-002: Правило Двух Доменов (The Two-Domain Rule)
Новый фундаментальный примитив (универсальный тип данных, базовый интерфейс) 
не может быть введён в систему, пока не существует доказательств (runtime-багов), 
что минимум два независимых домена страдают от одной и той же онтологической проблемы.

Введение примитива на основе гипотезы (предположения, что "это пригодится позже") 
ЗАПРЕЩЕНО.

Сначала — локальное лекарство для доказанного бага. 
Потом — поиск второго домена. 
Только после второго подтверждения — генерализация в фундаментальный примитив.

---

## §ENIGMA. ЗАКОНЫ ЭПИСТЕМИЧЕСКОЙ И РЕФЕРЕНЦИАЛЬНОЙ ЦЕЛОСТНОСТИ

§ENIGMA-003: Закон Эпистемической Проекции
Любое отсутствие данных в рантайме интерпретируется КАК ОТСУТСТВИЕ 
ВАЛИДНОЙ ПРОЕКЦИИ В ГРАФЕ ПАМЯТИ АГЕНТА, а не как нейтральное или 
нулевое значение объективного мира. UNKNOWN ≠ NEUTRAL(0.0).

§ENIGMA-004: Закон Эпистемического Демпфирования и Изоляции
Неизвестность (Vacuum) — это локальный разрыв вывода, а не глобальное 
свойство мира. ЗАПРЕЩЕНА конвертация Vacuum в глобальные аккумуляторы 
состояния внутри потребителей (напр. PerceptualKernel.uncertainty). 
Vacuum ОБЯЗАН обрабатываться как транзиентный inference pressure.

§ENIGMA-005: Закон Референциального Замыкания
EventContext ОБЯЗАН быть чистой проекцией Intent. Никакой внешней 
системе (shared_context, эвристикам оркестратора) не разрешено 
модифицировать или дополнять Intent после его создания.

§ENIGMA-006: Требование Полноты Намерения
Если Intent недоспецифицирован (отсутствует target_id), система ОБЯЗАНА 
обрабатывать это как "Unresolved Reference" (Неразрешённая ссылка), 
сохраняя target_reference для контекстного вывода или запроса уточнения, 
а не как "Отсутствие цели".

§ENIGMA-S72: Закон Релятивистского Восприятия
Движок производит только сырые сигналы (raw features). Смысл сигнала 
возникает в момент взаимодействия структуры личности (drives_base + 
trauma_markers) и сырого сигнала.

1. CFRM ОБЯЗАН передавать threat_level и anomaly_score как есть (0-1), 
   без фиксированных множителей (×40, ×20). Interpretation делегирована 
   личности.
2. Affective Pipeline ОБЯЗАН вычислять affective_load с весами из 
   drives_base (fear→threat, control→uncertainty, significance→anomaly), 
   а не из хардкода (0.6/0.3/0.1).
3. DecisionHub ОБЯЗАН модулировать _context_relevance через drives_base, 
   а не через фиксированные семантические веса (+0.5/+0.7/+0.2).
4. ЗАПРЕЩЕНА конвертация Vacuum (uncertainty_delta) в глобальные 
   аккумуляторы состояния (stress_delta). Это нарушает §ENIGMA-004.
5. ЗАПРЕЩЕНО назначение dominant_emotion_hint из движка. Эмоция 
   резолвится только через Affective Pipeline → EmotionTransition.
6. Все три порога эмоций (anxious/fearful/panic) ОБЯЗАНЫ быть 
   персонализированы через fear_drive + willpower.
7. Конвертация эмоции в действие ОБЯЗАНА модулироваться через 
   drives_base. Страх не всегда означает бегство: control-heavy 
   перенаправляет страх в превентивную агрессию, significance-heavy 
   — в предупреждение, desire-heavy — в поиск помощи. Эмоция = 
   энергия, личность = направление разрядки.

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
diagnostics/              ← НЕ ЗНАЕТ о рантайме симуляции. Читает stdout, git, файлы. Пишет в reports/.
    └── reports/          ← LLM-oriented Markdown (LAST_SESSION.md). Не импортируется в игру.
    │   └── identity/          ← L1 Chronicle (append-only), DriveResolver (pure projection)
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


python -m pytest backend/tests/sandbox/ -v --tb=short
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

ФАЗА 5: Decision (Каузальная дискретизация T+1)
    DecisionHub.compute(topic=topic, state=fresh_state, decision_ctx=ctx_T-1)
    → создаёт CommunicationIntent
    ЗАПРЕТ: Передавать сырые дельты давления из текущего тика. Хаб работает только на консолидированном восприятии прошлого тика (PerceptualKernel → DecisionContext). Это не задержка, а разделение reactive и deliberative слоев.

ФАЗА 6: Post-Decision
    IntentEventAdapter: CommunicationIntent → EventDTO

ФАЗА 7: EventBus (вторичная волна)
    event_bus.publish(event_from_npc)

ФАЗА 8: Layered Reduction (ADR-016, ADR-027)
    Многоступенчатая редукция реальности: Physical (Combat) → Materialization → Cognitive (Reaction) → Social.
    Порядок строго детерминирован. Прямая мутация состояния ЗАПРЕЩЕНА (только через Phase8Result → delta_buffer).

ФАЗА 9: CFRM Integration & Perception (ADR-040, ADR-050, ADR-052)
    LocalCausalSolver: FieldDisturbance → ProjectionPolicy → PhenomenologicalState → PsychologicalPressure.
    Обновление PerceptualKernel (PerceptionPayload). Проекция ядра в DecisionContext через translate_kernel_to_context() для Фазы 5 следующего тика.
    Сборка WorldSnapshotDTO + AvatarStateDTO.

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
| 7.11 | CausalObserver мутирует state | Нарушение принципа пассивного наблюдателя, недетерминированность симуляции |
| 7.12 | Удаление событий из L1Chronicle | Нарушение append-only истории (ADR-O-208) || 7.13 | Кэширование EffectiveDrives (L3-P1) | Эфемерная проекция, рассинхрон с L1 (ADR-O-208) || 7.14 | Коммит состояния с NaN, sum!=1.0, или bounds violation | Краш тика через OntologyViolationError (ADR-O-207) || 7.15 | Desire в RiskPerceptionProfile | Риск ≠ готовность рисковать (ADR-O-146) || 7.16 | Viability veto через пост-генерационную фильтрацию | ROUTINE уже мутирует state до фильтрации (ADR-O-137) |

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

**Закон 11.4:** Каждое архитектурное изменение должно сопровождаться:
1. Записью в `docs/ADR (Architecture Decision Records).md` — единый атлас всех ADR (секция, домен, статус).
2. Созданием `docs\audits\ADR-0XX_IMPACT.md` — детальный impact audit (downstream, rollback, sandbox tests).
Архитектурная амнезия недопустима.

---

## 12. ЗАКОН СЕРИАЛИЗАЦИОННОЙ ЦЕЛОСТНОСТИ (Round-Trip Integrity Law)

Сериализационные адаптеры (`from_legacy`/`write_to_legacy`, `from_dict`/`to_dict`, `model_validate`/`model_dump`) — **единственная граница между персистентным хранилищем и живым объектом**. Разрыв этой границы = молчаливая потеря данных (DOUBLE TRUTH).

### §12.1 Ключи — константы, не строки

Все ключи словаря, используемые в сериализационных адаптерах, ОБЯЗАНЫ быть объявлены как модульные константы:

```python
_KEY_NPC_ID = "npc_id"    # авторитетный ключ в рантайме
_KEY_PSYCHE = "psyche"
_KEY_BODY_STATE = "body_state"
```

Использование inline-строк (`npc_dict.get("id")`) в адаптерах ЗАПРЕЩЕНО.
Исключение: чтение legacy-алиасов с явным fallback (`npc_dict.get(_KEY_NPC_ID, npc_dict.get("id", _UNKNOWN))`).

### §12.2 Write-All-Read-All (WARA)

`write_to_legacy` ОБЯЗАН записывать КАЖДОЕ поле, которое `from_legacy` читает.
Если `from_legacy` читает `npc_dict.get("npc_id")` — `write_to_legacy` ОБЯЗАН писать `npc_dict["npc_id"]`.

Нарушение = DOUBLE TRUTH (поле теряется между тиками).

**Проверка:** `from_legacy(data) → write_to_legacy(obj, data) → from_legacy(data)` — все ключевые поля должны совпадать.

### §12.3 Тест через from_legacy, не через конструктор

Тест сериализационного адаптера ОБЯЗАН создавать объект через `from_legacy(real_dict)`, а НЕ через прямой конструктор `NPCState(npc_id=..., stress=...)`.

Прямой конструктор в тесте — это тест предположений LLM, а не тест реального потока данных. LLM угадывает дефолты — и угадывает неправильно (will_state=None, npc_id="unknown").

**Единственный допустимый путь создания объекта в тесте адаптера:**
```python
obj = Adapter.from_legacy(real_runtime_dict)
```

Если нужно проверить конкретное значение — мутация ПОСЛЕ `from_legacy`:
```python
obj = Adapter.from_legacy(real_dict)
obj = dataclasses.replace(obj, npc_id="test_override")
```

### §12.4 Real Data First

Первый тест сериализационного адаптера ОБЯЗАН использовать структуру реальных рантайм-данных (ключи из `all_npcs_raw`), а не предполагаемую структуру.

**Протокол:**
1. Внедрить `print(list(npc_dict.keys())[:15])` в `from_legacy` на один запуск
2. Увидеть РЕАЛЬНЫЕ ключи
3. Построить тест на основе реальных данных
4. Только после этого писать фикс

### §12.5 Реестр сериализационных адаптеров

Каждый адаптер `from_legacy`/`write_to_legacy` должен быть перечислен в реестре:

| Адаптер | Файл | Round-trip тест | Последняя проверка |
|---------|------|-----------------|-------------------|
| NPCState | `npc_state.py` | `test_npc_state_roundtrip` | S63 |
| NPCPersonality | `npc_state.py` | `test_personality_roundtrip` | S63 |
| PerceptualKernel | `npc_state.py` | `_pk_from_dict` | S62 (ADR-115) |

Добавление нового адаптера без записи в реестр = нарушение.

---

## 13. LAW OF EPISTEMIC GROUNDING (Закон Познавательного Обоснования)

**Статус:** Генеральный закон. Применяется ко ВСЕМ доменам без исключения.
**Проблема:** LLM принимает предположения за факты. Не знает структуру → достраивает. Не знает ключ → угадывает. Не знает инвариант → придумывает наиболее вероятный. Результат: молчаливые баги, DOUBLE TRUTH, разорванные pipeline.
**Решение:** Запрет на немотивированные действия. Знание первично, код вторичен.

---

### §13.1 Запрещено предполагать структуру

Если изменение касается:
- dataclass / pydantic model
- serializer / adapter / from_legacy / write_to_legacy
- persistence / event payload / DTO
- любой функции, читающей или пишущей структуру данных

LLM **НЕ ИМЕЕТ ПРАВА** создавать код на основании предположений о структуре.

Сначала — получение структуры через археологию (PowerShell / print-диагностика).
Потом — код.

**Запрещено:**
```python
# LLM не читала сигнатуру → угадала will_state=None → краш
NPCState(npc_id="player", will_state=None, ...)
```

**Разрешено:**
```python
# LLM прочитала сигнатуру через PowerShell → знает реальные поля
# Или использует фабрику: from_legacy(), from_dict(), load_state()
```

---

### §13.2 Read Before Write

Перед изменением любого кода LLM обязана найти:

| Что найти | Как |
|-----------|-----|
| Определение класса | `Select-String -Pattern "class ClassName"` |
| Сигнатуру конструктора | `Select-Object -Index (N..M)` на строки после class |
| Владельца данных | `Select-String -Pattern "field_name"` по проекту |
| Все точки чтения | `Select-String -Pattern "\.field_name"` |
| Все точки записи | `Select-String -Pattern "field_name\s*="` |

Минимальный результат археологии:
```
Definition:  файл:строка
Readers:     список файлов
Writers:     список файлов
Owner:       модуль-владелец
```

Без этого фикс **запрещён** (ROOT_CAUSE_CONFIDENCE < 40, см. Правила Фикса Багов Часть X).

---

### §13.3 Owner Discovery First

Перед исправлением любого бага сначала определить:

> Кто владелец истины для этого поля?

Если владелец не найден:
```
STOP
ARCHAEOLOGY REQUIRED
```

Пример конфликта:
```
HP найден в:
  NPCState.hp
  body_state.current_hp
  AvatarState.hp
```

Сначала — определить единственного владельца.
Только потом — писать код.

Множественные писатели в одно поле = DOUBLE TRUTH = архитектурный баг.

---

### §13.4 No Constructor Synthesis (Фабрика вместо Мечты)

Запрещено создавать объекты вручную через конструктор, если существует фабрика:

```python
from_legacy()
from_dict()
load_state()
factory()
builder()
model_validate()
```

**Причина:** Конструктор создаёт **объект мечты** (с полями, которые LLM угадала).
Фабрика создаёт **объект реальности** (с полями, которые реально существуют в данных).

**Исключение:** Если фабрики нет — сначала написать фабрику, потом писать тест.

---

### §13.5 Иерархия Истины

Если документация говорит одно, а код говорит другое — **прав код**.
Если код говорит одно, а реальные данные говорят другое — **правы реальные данные**.

```
Runtime Data     ← высший авторитет
     ↓
Code             ← реализация
     ↓
ADR              ← архитектурное решение
     ↓
Documentation    ← описание
     ↓
Assumptions      ← НИЗШИЙ авторитет, запрещено как основание
```

Следствие: если ADR противоречит рантайму — ADR устарел, не рантайм сломан.

---

### §13.6 Археологический Цикл (Archaeology Loop)

Любой архитектурный фикс проходит цикл:

```
Hypothesis        → предположение о причине
     ↓
Archaeology       → PowerShell / print-диагностика / чтение кода
     ↓
Ownership Map     → кто владеет, кто читает, кто пишет
     ↓
Causal Map        → CREATE → READ → TRANSFORM → MATERIALIZE → APPLY → COMMIT → PROJECT → PRESENT
     ↓
Fix               → минимальное изменение
     ↓
Validation        → smoke-test / round-trip / runtime проверка
```

**Запрещённый путь:**
```
Hypothesis → Fix
```

Любой фикс без промежуточных шагов = нарушение §13.

---

### §13.7 Исчерпывающий Домен

§13 применяется ко ВСЕМ доменам ENIGMA без исключения:

- Бой (CombatSubscriber, ImpactEngine, PhysiologyPayload)
- Перемещение (MovementEngine, SpatialService, TraversalState)
- Физиология (BodyState, DecayHandler, Somatic Veto)
- Сериализация (from_legacy, write_to_legacy, StateApplicator)
- Эмоции (EmotionResolution, AffectiveIntegrator, PerceptualKernel)
- Воля (WillpowerGate, IntentPressureResolver, Affect)
- Память (MemoryManager, NarrativeCache, L2)
- Пространство (SpatialRuntime, GraphCompiler, ClusterOccupancy)

Ни один домен не является исключением из Закона Познавательного Обоснования.

---

*Версия: 1.8*  
*Дата: 2026-05-27*  
*Следующая проверка: каждые 5 шагов разработки*



