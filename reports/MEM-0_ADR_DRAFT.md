# ADR MEM-0 — Memory Architecture (Memory Ontology & Causal Ownership)

> **Статус:** PROPOSED (черновик для вердикта Master, 2026-11-13, ветвь А, сессия S425+)
> **Тип:** ADR-O (ONTOLOGY) — затрагивает истину мира, память, убеждения
> **Номер:** `ADR-O-XXX`. `O-442` зарезервирован Master за A3.1 (см. S425-errata); номер MEM-0 назначит Master отдельно после завершения A3.1 и проверки атласа. `O-441` — параллельная Б (S424-2).
> **Место в ROADMAP:** §16.4 MEM-0, §16.6 `MEM-ONT-1`, §16.10 (дополнение 2026-10-23 — 3 запрета)
> **Прецедент формата:** `docs/audits/ADR-O-439_COORD_FRAME_W.md`, `reports/HANDOFF_S337_CCH.md`
> **НЕ КОД:** этот файл — черновик ADR, не реализация. Production-код, флаги, schema не тронуты.

---

## 1. Контекст

Сегодня память NPC — **три расходящихся контура** (§16.0 ROADMAP):
- RAM-окно 20 событий (`WorkingMemory`, deque)
- narrative_cache top-10 (`NPCState.narrative_cache`, Tuple[EventMemory])
- SQLite `event_memories` (вечный)

В них хранится **интерпретированная строка без времени, без перспективы и без связей**. Консолидация разорвана на три механизма: один с латентной деструкцией `seq_0`, другой не переживает рестарт, третий отсутствует. Семантический слой спит (0 писателей). Ожидания удалены (DEEP-015). Реконструкция отсутствует — речь NPC строится из top-3 свежайших записей + статичный backstory, остальное дописывает LLM без барьера (`MEM-D11`).

**Главный критерий успеха (§16.0):** трек достиг цели, когда система порождает «Горан? Да…» — и дальше реконструирует индивидуальную историю NPC с личной перспективой, привязкой к реальному прошлому, устойчивыми и исчезнувшими деталями, возможными ошибками, временной структурой, влиянием на прогноз, отличимостью от WORLD TRUTH, без хранения полного мира внутри памяти NPC.

**MEM-0 — не реализация, а онтология и causal ownership.** Что владеет / пишет / читает на каждом звене. Не новая сущность, а карта.

## 2. Проблема (P0-сводка §7.9 + §16.10)

**P0-дефекты (без них верхние слои стоят на песке):**

| ID | Суть | Владелец |
|---|---|---|
| **MEM-D1** | `day=0` у всех runtime-записей; в схеме нет tick/game_day; `created_at` — wall-clock, в модель не грузится | MEM-1 |
| **MEM-D2** | decay 2.4× ускорен: `DECAY_EVERY=10` при `TICKS_PER_DAY=24`; time_skip 20 лет не влияет | MEM-2 |
| **MEM-D3** | `apply_decay` только в RAM; LTM вечен; «забытое в сессии воскресает» при load | MEM-2 |
| **MEM-D5** | seq_0-коллизия: `sequence_id` никогда не присваивается → `removed_ids=("seq_0",…)` выметает весь кэш при первом сжатии — **латентная деструкция** | MEM-2 |
| **MEM-D7** | Диалоговая память в `except`-ветке (`npc_dialogue_subscriber.py:550-572`) — реплики не попадают в L2 при норме | MEM-1 |
| **MEM-D11** | Grounding-гвард отсутствует: `ResponseValidator` проверяет форму, не факты — LLM сочиняет прошлое | NL-8 |
| **MEM-D15** | Тематическая слепота: `knowledge_retrieval` требует secret_id+is_secret; «расскажи про Горана» → 0 записей | MEM-7 |
| **MEM-D16** | REVEAL без содержимого: NPC под приказом «раскрой» обязан **галлюцинировать** факт канона | MEM-7/NL-7 |
| **MEM-D20** | 5 belief-носителей без арбитра (BeliefState, CrystallizedBelief, ConclusionStore, EpistemicStore, MemoryCrystal) | MEM-3/EPI |
| **MEM-D42** (§16.10) | 4 тихих пути удаления без счётчика: FIFO WM, FORGOTTEN-сброс, seq_0-компрессия, STM-оборот | MEM-2 |
| **MEM-D43** (§16.10) | `PRAGMA foreign_keys=ON`, но ноль FK-деклараций; ссылки переживают удаление референтов | MEM-2 |

## 3. Решение — 9 разделов

### 3.1. MEM-INV-TRIPLE + Causal Ownership

**`WORLD TRUTH ≠ NPC MEMORY ≠ NPC BELIEF`** — три уровня никогда не сливаются. Реконструкция и reconsolidation памяти **не имеют права** менять WORLD TRUTH.

Causal ownership — карта существующей цепочки (звено = causal ownership, не обязательно отдельный storage):

| Звено | Владелец | Писатели | Читатели | Ablation |
|---|---|---|---|---|
| WORLD TRUTH | TruthState / L1Chronicle | world-event продюсеры | perception | — (вне MEM) |
| EVENT/EXPERIENCE | EventBus | EventDTO.create | perception / narrative | — |
| PERCEPTION | perception_filter / PerceptualKernel | pipeline_runner | encoding | снять → NPC «всё знает» |
| ENCODING | `MemoryManager.apply` (единственный законный writer, Закон 4.1.2) | pipeline_runner (Фаза 3) | narrative_cache | снять → записи нет |
| EPISODIC TRACE | EventMemory / SQLite | MemoryManager.apply | recall / promotion | снять → нет прошлого |
| CONSOLIDATION | PromotionEngine (**сегодня RED**) | ? (планируется MEM-2) | LTM | — |
| LTM | SQLite event_memories | apply / batch save | recall / retrieval | — |
| ASSOCIATION | — (нет, MEM-6) | — | — | — |
| RETRIEVAL | `MemoryManager.recall` (чистая функция narrative_cache) | — | decision / verbalization | снять → NPC отвечает без прошлого |
| RECONSTRUCTION | — (нет, MEM-7) | — | verbalization | — |
| BELIEF | 5 носителей (MEM-D20, Arbiter) | каждый свой | DecisionHub / verbalization | снять → belief «с неба» |
| EXPECTATION | expectation_runtime (**сейчас dormant, DEEP-015**) | ? (MEM-8) | DecisionHub | — |
| DECISION | DecisionHub | — | — | — |

### 3.2. MEM-INV-FOUR-STATES (разведение)

`destruction` ≠ `forgetting` ≠ `uncertainty` ≠ `reconstruction` — четыре состояния **не сливаются** (сегодня слиты — MEM-D25):

| Состояние | Контракт |
|---|---|
| **destruction** | физически нет записи **ни в одном предусмотренном тире** (RAM + LTM + SQLite). Зависимые (belief/obligation/investigation) — либо tombstone, либо блокированы. Удаление только из RAM (FIFO WM, STM turnover) — это **retention transition** внутри `forgetting`, **не** destruction. LTM-строка при RAM-удалении жива; запрет воскресения — §16.10-P2 + MEM-D3/D8. Наличие tombstone/архивной записи = исторический факт **не уничтожен**. |
| **forgetting** | запись есть, но accessibility ниже порога; recall её не возвращает; cue может вернуть |
| **uncertainty** | recall возвращает запись с маркером confidence/clarity низким; реконструкция hedges |
| **reconstruction** | запись восстановлена из частей (compressed_from); помечена как reconstruction; не получает статус WORLD TRUTH |

Модель `record exists → NPC can retrieve record` — **запрещённая модель памяти**.

### 3.3. MEM-INV-PERSPECTIVE + EventMemory schema (MEM-1: P0-only; D10 отложено)

Память принадлежит субъекту. Один event → **разные memories** (жертва / актор / свидетель). Роли `actor / witness / hearer` + канал `saw / heard / was_told` — в схеме.

**Решение Master (2026-11-14): вариант C — отложенная активация ExperienceTrace.** D10 — не отсутствие второго хранилища, а потеря перспективы при создании опыта; введение второго durable-носителя до определения его потребителя создаст обязанность синхронизации без устранения первопричины.

**MEM-1 schema delta — только P0 (D1/D4):**

| Поле | Сейчас | MEM-1 |
|---|---|---|
| `id` | internal | internal + **`event_id`** (EventBus identity, MEM-D4) |
| `day` | есть, всегда 0 | есть + **`game_tick`** (NL-1 carrier, MEM-D1) |
| `perspective_role` | **нет** | **НЕ вводится** — отложено до MEM-3 (D10, вариант C) |
| `channel` | **нет** | **НЕ вводится** — отложено до MEM-3 (D10, вариант C) |
| остальные (importance, decay_rate, stage, tags_json, is_secret, compressed_from, contract_ref, …) | есть | без изменений |

**D10 — отложено, MEM-3 (условие возврата).** `ExperienceTrace` (`models/npc/experience_trace.py:22`) остаётся **вычисляемой проекцией** над `EventMemory` — его docstring (`:2`) прямо говорит «не SSOT». MEM-1 **не создаёт** durable writer для ExperienceTrace. Возврат к ExperienceTrace — в MEM-3, когда появится реальный потребитель в BeliefCrystallization evidence-цепи (MEM-D17) и ADR Epistemic Arbiter (MEM-D20) зафиксирует контракт владения. `payload`-проводка перспективы — допустимый **экспериментальный** канал, но **НЕ каноническая модель** и **НЕ решение D10**. Второй SSOT для перспективы запрещён (§16.1.12 Anti-Bond).

Миграция: `MigrationRunner` (прецедент S351, ADR-O-426) — не плодить второй механизм. `.bak` побайтово (прецедент S354).

### 3.4. WHAT stable / decays / distorts / uncertain + WHY

По классам значимости (вход NL-INV-SALIENCE, прецедент ADR-O-307):

| Класс | Что стабильно | Что распадается | Что искажается | Что остаётся uncertain | Why |
|---|---|---|---|---|---|
| **Травма (betrayal, death)** | ядро факта (кто/что) | детали обстановки | эмоциональная амплификация | детали свидетелей | salience-пол «шрама», ADR-O-307 |
| **Бытовое (обычная реплика)** | кратко, быстро | почти всё | source-confusion | с высокой вероятностью | decay_rate 0.05; ниже — можно |
| **Ритуал/повтор** | паттерн, не экземпляр | экземпляры | нет | «сколько раз» — uncertain | semanticization (NL-INV-CONSOLIDATION) |
| **Секрет (canon)** | полностью | никогда (doctrine) | никогда | доступность по known_by | disclosure-лестница (P5) |

### 3.5. Вердикт по 5 belief-носителям (MEM-D20)

**Решение Master (2026-11-14): вариант A — мосты с одним writer на trait, с обязательным pre-flight ownership-таблицы.** Полная унификация (вариант B) отвергнута: против §16.1.12 Anti-Bond и §16.9 «не создавать второй store».

**Ключевой принцип:** один trait — один авторитетный владелец, но **не обязательно** один физический Store на всю систему. ENIGMA может иметь несколько представлений памяти — но **не должна иметь несколько независимых авторов одного и того же факта**.

**Обязательная ownership-таблица (pre-flight для MEM-3):**

| Поле таблицы | Требование |
|---|---|
| **Trait** | Каноническое свойство (например, `fear`, `trust`, `loyalty_true`, `trait.*`) |
| **Authoritative owner** | Единственный владелец истины для trait (один из 5 носителей) |
| **Writer** | Единственный разрешённый писатель (модуль + метод) |
| **Readers** | Все потребители (DecisionHub, verbalization, MOT-3, …) |
| **Projection** | Производные представления (read-only) и правила пересчёта |
| **Migration** | Судьба существующих записей в других носителях (backfill / delete / archive) |
| **Conflict policy** | Правило обработки противоречий (не `latest-wins`, не `dominant-take-all`; осознанный конфликт как материал сознания NPC — MEM-INV-CONTRADICTION) |

**Обязательный pre-flight до миграции (не раньше):**

1. **`contradiction_resolver` — отдельный поиск всех вызовов.** Доклад показал `memory_manager.py:772` (`resolve_all` внутри `update_beliefs`), но отдельный grep `update_beliefs(` / `resolve_all(` **не выполнен**. Утверждение §7.9 MEM-D20 «0 вызывающих» **не доказано** этим докладом. До выяснения — resolver считается живым с невыясненным статусом.
2. **`ConclusionStore` остаётся самостоятельным.** Отсутствие потребителя BC-2 сейчас — не основание для объединения с другими носителями; это отдельный когнитивный результат BC-1 (`conclusion_store.py:45`, `apply/get/get_for`).

**Запрет:** не мигрировать пять носителей до завершения ownership-таблицы и проверки downstream. Миграция — отдельный ADR.

Правила конфликта версий (MEM-INV-CONTRADICTION):
- Памяти сосуществуют; авторезолюция `latest wins` / `highest confidence wins` **запрещена**
- Конфликт — материал сознания NPC (сомнение) и NL-6
- `contradiction_resolver` — реанимировать в MEM-3

### 3.6. §16.10 — три запрета (к MEM-0 по явному требованию §16.10:3120)

1. **Silent deletion prohibition.** Молчаливое удаление, делающее убеждение/решение/обязательство/расследование необъяснимым, **запрещено**. Каждый путь удаления либо сохраняет объяснимость зависимых (tombstone / сводка / ссылка на архив), либо **блокирован** при живых ссылках.
2. **Operational ≠ Historical.** Удаление оперативной записи (RAM/STM/WM) ≠ исчезновение исторического факта. LTM-строка жива; обратное направление (запрет воскресения) закрыто MEM-D3/D8.
3. **Consolidation ≠ Fact.** Консолидация не превращает вероятностный вывод NPC в объективный факт. Абстракция наследует `provenance` и `compressed_from`, не получает статус WORLD TRUTH.

### 3.7. GC-инвариант (симметрично CAUSAL_CONTRACT §10.4)

Ни один GC-механизм памяти не создаёт фактов задним числом и не меняет уже записанную историю. Детерминизм всех операций — KernelRNG-salt, replay-канал (MEM-10).

### 3.8. §16.1 запреты → 15 IPT-инвариантов

12 законов §16.1 + 3 запрета §16.10 → IPT-инварианты (AST-линтеры, прецедент `INV-RE-CACHE-ALLOWLIST`):

| # | Инвариант | Источник |
|---|---|---|
| 1 | `INV-MEM-TRIPLE` — нет кода, сливающего WORLD/MEMORY/BELIEF | §16.1.1 |
| 2 | `INV-MEM-PERSPECTIVE` — EventMemory имеет perspective_role и channel; оба не пустые при записи от NPC | §16.1.2 |
| 3 | `INV-MEM-EPISODIC-BASIS` — belief без `evidence[]` не создаётся | §16.1.3 |
| 4 | `INV-MEM-FOUR-STATES` — четыре константы состояния различаются; нет коллапса | §16.1.4 |
| 5 | `INV-MEM-RECONSOLIDATION` — retrieval-мутации детерминированы (KernelRNG salt) | §16.1.5 |
| 6 | `INV-MEM-DETERMINED-DISTORTION` — класс искажения в закрытом реестре | §16.1.6 |
| 7 | `INV-MEM-CONSUMER` — новая memory-сущность с объявленным downstream | §16.1.7 |
| 8 | `INV-MEM-LLM-BOUNDARY` — retrieval packet → LLM → validated; нет LLM→canonical без записи | §16.1.8 |
| 9 | `INV-MEM-ANTI-ARCHIVE` — нет единого JSON / vector DB / embeddings как memory | §16.1.9 |
| 10 | `INV-MEM-CONTRADICTION` — авторезолюция `latest wins` запрещена | §16.1.10 |
| 11 | `INV-MEM-NO-CHEAP-LOSS` — удаление без анализа reconstructability запрещено | §16.1.11 |
| 12 | `INV-MEM-ANTI-BOND` — нет второго MemoryStore / BeliefStore / NarrationStore | §16.1.12 |
| 13 | `INV-MEM-SILENT-DELETE` — пути удаления либо сохраняют объяснимость, либо блокированы | §16.10 |
| 14 | `INV-MEM-OP-NE-HISTORICAL` — удаление RAM-записи не удаляет LTM | §16.10 |
| 15 | `INV-MEM-GC-NO-FACTS` — GC не создаёт задним числом | §16.10 |

### 3.9. Что НЕ входит

MEM-1..MEM-10 — отдельные пакеты/ADR (MEM-DOM-1..3, MEM-INT-1..3, MEM-PERF-1, MEM-TST-1 по §16.6). MEM-0 — **онтология и ownership**, не реализация.

## 4. Downstream (что зависит от MEM-0)

DecisionHub (npc_memory_modifiers) · BC-2…BC-7 · NL-1/NL-2/NL-3/NL-10 · CCH-02 RP-1 · RE-01 M2/D · LC-IMPL-4/5 · Body/EM · MATH-3/4 · HUM-09 · P14/P15/SCALE-03…07 · EPI-VER.

## 5. Бюджет

- **MEM-0 ADR:** 0 (docs-only)
- **MEM-1** (следующий шаг, не в этом ADR): EventMemory v2 +4 колонки; оценка +~100 байт/запись × 10⁵ = ~10 MB RAM-пик; SQLite-миграция через MigrationRunner; tick-latency нейтрально. VRAM не затрагивается.

## 6. Откат

- ADR: `git revert` (docs-only).
- IPT-инварианты: отдельный коммит с PR-откатом.
- Схема v2: обратима через `.bak` (прецедент S354).

## 7. Регресс-тесты

- **MEM-GC-01** (хронология различима — самый узкий гейт) — первый обязательный.
- **15 IPT-инвариантов** — AST-линтеры, тестируются на старом и новом коде.
- Stop-rule §0.2(5) дословно: закрытие MEM-0 — только когда ADR утверждён Master **и** 15 инвариантов живут в IPT.

## 8. Решения Master и открытые технические вопросы

**Закрыто вердиктом Master (2026-11-14):**

1. **MEM-D10** — вариант **C** (отложенная активация ExperienceTrace; MEM-1 = только `event_id` + `game_tick`; возврат в MEM-3). См. §3.3.
2. **MEM-D20** — вариант **A** (мосты, 1 writer на trait) + обязательная ownership-таблица (7 полей). См. §3.5.
3. **§16.10** — 3 запрета (P1/P2/P3) + GC-инвариант (I4) включены в MEM-0. См. §3.6, §3.7, §3.8.
4. **Номер ADR** — `ADR-O-XXX`. `O-442` зарезервирован Master за A3.1. См. шапку.
5. **§3.2 destruction** — двухтировая семантика (destruction vs retention transition). См. §3.2.
6. **Запись в атлас + IMPACT** — только после утверждения Master и завершения A3.1; текущий черновик остаётся untracked.

**Открытые технические вопросы (для MEM-1 / MEM-3, не блокируют MEM-0):**

1. **Ownership-таблица (D20):** точный набор traits, authoritative owner per trait, writers, readers, projections, conflict policies. Составить до первой миграции.
2. **`contradiction_resolver`:** отдельный grep `update_beliefs(` / `resolve_all(` по всем слоям — статус «мёртв / жив / dormanт» доказать кодом (не докладом).
3. **Migration существующих записей per trait** — backfill / delete / archive; миграция через `MigrationRunner` (прецедент S351).
4. **MEM-3 возврат к ExperienceTrace** — точная точка в BeliefCrystallization evidence-цепи (MEM-D17) и контракт в ADR Epistemic Arbiter (MEM-D20).
5. **Порядок MEM-1 / MEM-3:** MEM-1 (P0: D1/D4) запускается сейчас; MEM-3 — после BC-1 ON + Epistemic Arbiter + ownership-таблица.

## 9. Что дальше (после вердикта)

- Если MEM-0 утверждён → ADR-запись в `docs/ADR (Architecture Decision Records).md` + IMPACT; 15 инвариантов в `IPT.py` (отдельный коммит); baseline IPT ×2 в окне тишины.
- MEM-1 (EventMemory v2) — следующий пакет, требует `MigrationRunner` (прецедент S351) и `.bak` (прецедент S354).

---

**Источники:** ROADMAP §16.0-16.10 · §7.9 MEM-D1…D43 · §9.3e MEM-GC-01…09 · §16.6 ADR-кандидаты · §16.4 MEM-0 (6 подпунктов) · §16.10 (3 запрета + 1 инвариант) · АДР-O-307 (травма) · CAUSAL_CONTRACT §10.4 · Завещание №1/№16 · РЕЖИМ §13 (ADR-PRE-FLIGHT).
