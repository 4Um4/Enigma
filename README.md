# ENIGMA

ENIGMA — причинно-следственный движок симуляции. Мир здесь не загадка для разгадывания — это живой организм, который игрок ранит своим присутствием.

The Fool — первая игра и runtime-полигон движка. Таверна «Серебряный Волк» — первая мини-игра: эпистемическая симуляция с моральным измерением, где шесть NPC живут скрытыми жизнями, а действия игрока расходятся волнами по социальному графу.

README — живой документ. Здесь нет версий, метрик сессий и списков текущих багов — они живут в `reports/LAST_SESSION.md` и `docs/Tasks/ТЗ/03_KNOWN_ISSUES_AND_BUGS.md`. Этот файл даёт карту территории, а не саму территорию.

---

## Что это за игра

В ENIGMA нет NPC в обычном смысле. Есть люди.

Люся — не «квестодатель с секретом». Она девятнадцатилетняя девушка, которую били три года, которой угрожает гильдия воров, которая спит с кузнецом, потому что это единственное тепло в её жизни, и которая влюблена в стражника, подглядывающего за ней.

Если игрок сдаёт Люсю стражнику — она не «проваливает квест». Она умирает, сбегает или её находят в подвале с перерезанными венами. Торнин, молчавший о её шпионаже из-за долга гильдии, тоже сломается. Тень, подозревавший её, получит приказ устранить того, кто сдал её, потому что гильдия не прощает утечек.

Действие игрока — камень, брошенный в пруд. Волны расходятся далеко.

### Принцип «Нет злодеев»

Каждый NPC пришёл к своей жизни через обстоятельства. Люся шпионит, потому что семью убили и гильдия подобрала на улице. Тень убил человека по приказу гильдии в двадцать лет. Борко берёт взятки, потому что пять золотых в месяц при зарплате в двенадцать кормят его семью. Горан возит контрабанду, потому что торговая гильдия душит налогами. Торнин притворяется, что не знает о подвале, потому что должен гильдии тысячу двести золотых — расскажет, умрёт.

Моральной оценки в коде нет. Оценку ставит игрок — своими действиями.

---

## Quick Start

Prerequisite: Python 3.10+ на Windows PowerShell или Linux.

1. Установи зависимости: `python -m pip install -r backend/requirements.txt`.
2. Доустанови `pymorphy3` вручную: `python -m pip install pymorphy3` (используется в action-слое, но не в requirements — известный долг).
3. Запусти игру из корня: `python game_launcher.py`. Backend (FastAPI на :8000) поднимется автоматически.
4. Если работаешь с голым backend: `cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`.
5. Runtime-состояние читай в `reports/LAST_SESSION.md`.
6. Логи backend — в `backend/logs/`.
7. DNA-история сессий — в `reports/dna_history.jsonl`.

Не диагностируй по UI-тексту. Диагностируй по pipeline-traces, session report, logs и source contracts.

---

## Repository Anchors

### Архитектура (закон)
- `docs/00_CAUSAL_CONTRACT_v2.0.md` — текущий каузальный контракт
- `docs/АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md` — навигация по архитектуре
- `docs/ADR (Architecture Decision Records).md` — решения и их обоснования
- `docs/audits/ADR_STATUS_MATRIX.md` — статусы реализации ADR

### Технические задания
- `docs/Диаграммы игры/TZ_Lusya_Tavern_v2.pdf` — ТЗ мини-игры «Таверна Серебряный Волк» v2.0
- `docs/Диаграммы игры/CK_CORE_LAYER_SPEC_Instructions.pdf` — спецификация ядра
- `docs/Tasks/ТЗ/03_KNOWN_ISSUES_AND_BUGS.md` — регистр известных багов
- `docs/Tasks/ТЗ/ТЗ-01 DecisionHub.md` и далее по списку — покомпонентные ТЗ

### Конфигурация NPC и мира
- `config/npc/individuals/{borko,goran,lusya,orm,shadow,tornin}.json` — персональные секреты, backstory, origin_events
- `config/npc/archetypes/*.json` — архетипы (maid, guard, merchant, blacksmith, tavern_keeper, thief)
- `config/npc/social/village_relations.json` — граф NPC-NPC связей (trust, affection, nature)
- `config/world/factions.json` — фракции
- `location_templates/*.json` — графы локаций

### Контракты и история
- `docs/DTO Registry (Реестр контрактов).md` — реестр DTO
- `docs/MUTATIONS.md` — история изменений
- `docs/ARCHITECTURE_FLOW_GENERATED.md` — топология (генерируется из `architecture/*.yaml`, не редактируется вручную)

---

## Architecture

Core pipeline object: **world tick**.

Pipeline shape: `CREATE → READ → TRANSFORM → APPLY → COMMIT → PROJECT`.

Тик orchestrated в `TickOrchestrator._run_core_phases()`:

| Фаза | Что делает | Owner |
|---|---|---|
| 0 | Simulation — LifeEngine: need-driven, schedule, random events. Чистый Python, без LLM | LifeEngine |
| 0.5 | Time-Driven Decay — idle services, DynamicAffordanceField, PE Decay | IdleTickHandlers |
| 1 | Input Merge — NPIC Normalize, Interventions, WillpowerGate | Phase1Input |
| 2 | EventBus — первичная волна пространственных событий | SpatialEventDetector |
| 3 | Memory — MemoryManager.apply для затронутых NPC | MemoryManager |
| 4 | Pre-Decision — TopicExtractor извлекает тему для каждого NPC | TopicExtractor |
| 5 | Decision — TickState assembly → NpcTickPipeline.run → TickMutation commit | DecisionHub |
| 6 | Post-Decision — IntentEventAdapter → EventDTO, Windup Write Gate | IntentEventAdapter |
| 7 | Windup Resolution — Execution Gate, Stale Intent Validation | ActionWindup registry |
| 8 | Handlers — детерминированный drain: drain_events + handle → Phase8Result | Subscribers (Reaction/Social/Combat) |
| 9 | Integration — CFRM P2, L2.5 Belief Crystallization, WorldSnapshotBuilder | LocalCausalSolver + Snapshot |
| 9.1 | Affective Pipeline — Интеграл аффекта, EmotionTransition | AffectivePipeline |
| 10 | Persistence — atomic commit через PersistencePort | PersistencePort |

### Ownership boundaries

| Area | Owner | Boundary |
|---|---|---|
| phase order | TickOrchestrator | execution follows pipeline |
| state mutation | DeltaBuffer / StateApplicator | no direct state bypass |
| scene commit | SceneStateManager | commit boundary stays explicit |
| NPC decision | DecisionHub and domain resolvers | evaluates, does not govern world |
| spatial truth | SpatialService / spatial runtime | UI and narrative are not spatial SSOT |
| projection | snapshot/projection services | reads committed reality |
| voice | LLM/verbalization | describes, does not decide facts |
| combat | CombatSubscriber + ImpactEngine + InjuryProcessor | transduces events → physical damage |
| social graph | SocialEngine + ReputationEngine | propagates rumors via BFS over relations |
| economy | EconomyTracker + TradeResolver + TransactionEngine | records income/talk, executes trades |
| memory | ExpectationStore + CrystallizedBeliefStore + L1Chronicle | EMA expectations + crystallized beliefs + raw events |

---

## Core Concepts

### Каузальный тик

Тик — атомарная единица времени. Внутри тика выполняется строгая последовательность фаз. Время непрерывно (`game_time_seconds`) и не останавливается между тиками. Каждый тик продвигает часы на `GAME_TICK_INTERVAL_SECONDS` (60 секунд игрового времени).

Тик — чистая функция: на входе frozen snapshot состояния, на выходе TickResultDTO. Все мутации идут через `SceneChange` → `apply_batch()`. Прямая мутация `npc["position"] = ...` запрещена.

### NPC tiers

- **Major** — полная симуляция каждый тик. Живые люди с backstory, origin_events, скрытыми правдами.
- **Minor** — упрощённая симуляция раз в `MINOR_TICK_INTERVAL` тиков. Толпа, фон.

### Социальный граф

NPC-NPC связи хранятся как направленный граф `(source, target) → Relationship{trust, affection, nature}`. События распространяются по графу BFS с `MAX_HOPS=3`, `HOP_DECAY=0.8`, `PROPAGATION_THRESHOLD=0.15`. Искажение доверие-зависимое: низкое доверие к источнику усиливает негатив, высокое — смягчает.

### Кристаллизация убеждений

NPC формируют убеждения о других на основе наблюдений. Асимметричная травма: опровержение в `TRAUMA_MULTIPLIER=6.0` раз сильнее подтверждения. Убеждения затухают с `BELIEF_DECAY_TAU=100` тиков, забываются при весе < 0.05.

### Ожидания (Active Inference)

NPC хранят EMA ожиданий наград/угроз от источников (игрока). Обновляются через StateApplicator. PE-модификаторы конвертируются в drive_modifiers для DecisionHub.

### Боевка

Боевые события (`PLAYER_ATTACKS`, `ACTOR_ATTACKS`) публикуются в EventBus. `CombatSubscriber` транслирует их в `ImpactIntentDTO` → `ImpactEngine` решает физический урон → `InjuryProcessor` обрабатывает травмы → `PhysiologyDecayHandler` отслеживает распад тела. Windup-фаза (2 тика подготовки) реализована через `ActionWindup` registry — атаку можно прервать, цель может увернуться.

### Экономика

`EconomicProfile` у каждого NPC: золото, товары, потребности (INCOME, SOCIAL, SAFETY). `EconomyTracker` раз в `TICKS_PER_DAY` проверяет удовлетворение потребностей. `TradeResolver` связывает DecisionHub (намерение TRADE) с `TransactionEngine.execute_sale()`. `PsychoEconomy` модулирует поведение экономическими драйвами личности (control, significance, fear, desire).

### Восприятие и embodiment

NPC видят мир через `PerceptualKernel`. Игрок видит мир через `PlayerPerceptionDTO` с двумя слоями:
- **PeripheralCues** — наблюдаемые физические проявления: «Замер на месте», «Напряжённая поза», «Кровь на одежде», «Держится за рану». Цветной текст под именем NPC.
- **ActivePerceptions** — атмосферные восприятия: «Напряжение висит в воздухе», «Обстановка тревожная».

Speech Bubbles — облачка реплик над NPC, с переносом по словам, обрезкой по 3 строки, alpha-fade. Источник — `recent_dialogues` в `WorldSnapshotDTO`.

### Фракции

Четыре фракции в мини-игре: Гильдия Воров, Городская Стража, Торговая Гильдия, Таверна. `alignment ∈ [-100..100]`: отрицательный — враг, положительный — союзник. `known_to_faction` — фракция знает об игроке или ещё нет. Меняется от действий игрока через `FactionAlignmentTracker`.

### Судьбы

Каждый NPC имеет траекторию: Liberation (освобождение) / Stability (стабильность) / Deterioration (ухудшение) / Catastrophe (катастрофа). `FateTracker` пересчитывает `stability` и `threat` каждый тик; при `threat > 0.8 and stability < 0.2` запускает судьбинное событие — необратимое изменение: escape, arrest, death, breakdown, liberation, revenge. Каскадные последствия для связанных NPC.

---

## The Tavern — Six People

| NPC | Архетип | Что скрывает | Чего хочет |
|---|---|---|---|
| **Люся** (maid_lusya) | Служанка | Шпионит для гильдии воров через подвал таверны; спит с кузнецом; влюблена в Борко | Сбежать на юг |
| **Тень** (thief_shadow) | Вор | Лейтенант гильдии; ищет предателя, сдавшего контрабанду Горана; подозревает всех | Найти предателя, не потерять лицо перед гильдмастером |
| **Борко** (guard_borko) | Стражник | Берёт взятки от Горана; подглядывает за Люсей на кухне; однажды пропустил кого-то опасного | Денег на семью, никаких потрясений |
| **Горан** (merchant_goran) | Купец | Возит контрабанду; подкупает Борко; в долгах перед торговой гильдией | Расплатиться с долгами, не попасться |
| **Торнин** (tavern_keeper_tornin) | Трактирщик | Должен гильдии 1200 золотых; знает о шпионаже Люси, молчит; подвал таверны — база гильдии | Избавиться от долга, спать спокойно |
| **Орм** (blacksmith_orm) | Кузнец | Спит с Люсей; знает о подвале; выковал что-то для Торнина | Тепла, покоя, может быть — Люсю |

Полные секреты, backstory, origin_events — в `config/npc/individuals/*.json`. Социальные связи — в `config/npc/social/village_relations.json`.

---

## Causal Diagnostic System (CDS)

`diagnostics/causal_observer.py` пишет `reports/LAST_SESSION.md` каждый выход из сессии. Инварианты проверяются runtime:

- **INV-TIME-FREEZE** — `game_time_seconds` должен расти монотонно.
- **INV-DIALOGUE-PIPELINE** — если Phase 5 вернула вербальные решения, Phase 6 должна опубликовать `CommunicationIntent`.
- **INV-TRAV-DICT** — `active_traversals` в WorldSnapshot должен быть dict, не list.
- **INV-NPC-NAME** — каждый NPC в snapshot должен иметь `name`, иначе fuzzy matching слепнет.

DNA-метрики (SHI, NPI, OBI, SCF, CVS, PFI) — в `reports/LAST_SESSION.md`. История — `reports/dna_history.jsonl`.

---

## Architectural Prohibitions

- Execution must not make architectural decisions.
- Projection must not change reality.
- DecisionHub evaluates options; it does not manage world state.
- LLM is voice, not source of truth. WorldScheduler не должен делегировать генерацию world events в LLM.
- Frontend displays snapshots and sends intents; it does not own state.
- New DTOs, services, states, ADRs, or layers require evidence that existing structures are insufficient.
- Fallback without root cause is forbidden.
- Mermaid in `docs/ARCHITECTURE_FLOW_GENERATED.md` is generated output; edit `architecture/*.yaml` and regenerate instead.
- Minimal local fix has priority over broad refactor.
- NPC-to-NPC отношения меняются только через SocialEngine + StateApplicator. Прямая мутация `npc["relationships"]` запрещена.
- Боевые события публикуются только через EventBus. CombatSubscriber не создаёт Physiology напрямую — только через ImpactEngine.
- Speech Bubbles читаются только из `world_snapshot.recent_dialogues`. Прямой парсинг DM-текста запрещён.
- Время — `game_time_seconds`. Не `time.time()`, не `time_of_day`-строка. Один источник.

---

## Change Workflow

1. Define PIPELINE_OBJECT.
2. Define OWNER.
3. Reconstruct CREATE → READ → TRANSFORM → APPLY → COMMIT → PROJECT.
4. Check Single Source of Truth.
5. Check ownership boundaries.
6. Check DTO and runtime contracts.
7. Identify FAIL_STAGE before proposing a fix.
8. Build H1/H2/H3 with confidence.
9. Choose minimal FIX_SCOPE.
10. Update docs required by the sprint close instruction.
11. Run the most local meaningful tests or sandbox checks.
12. Commit and push a named branch.

Required session-close documents are described in `docs/ИНСТРУКЦИЯ ПО ОКОНЧАНИЮ СЕССИИ.md`.

---

## What Not To Do

- Do not treat a symptom as root cause.
- Do not introduce a fallback to hide an unknown failure.
- Do not move responsibility between layers without evidence.
- Do not make projection, UI, or LLM mutate committed state.
- Do not create a second source of truth for spatial, memory, body, or scene state.
- Do not edit generated architecture maps by hand.
- Do not add new abstractions for aesthetic symmetry.
- Do not promise future features in README.
- Do not добавлять `print()` в production-код — только `logger.debug/info/warning/error`.
- Do not использовать `time.time()` и `game_time_seconds` взаимозаменяемо.
- Do not диагностировать по UI-тексту. Только pipeline-traces, session report, logs, source contracts.

---

## External Auditor Contract

README даёт точки входа и текущие границы. Final authority — в исходном коде, ADR, DTO registry, architecture YAML и текущих session reports.

| Field | Value |
|---|---|
| audit_entry | README.md |
| session_state | `reports/LAST_SESSION.md` |
| architectural_index | `docs/ADR (Architecture Decision Records).md` |
| contract_index | `docs/DTO Registry (Реестр контрактов).md` |
| bug_register | `docs/Tasks/ТЗ/03_KNOWN_ISSUES_AND_BUGS.md` |
| tz_minigame | `docs/Диаграммы игры/TZ_Lusya_Tavern_v2.pdf` |
| expected_reader | external architect / LLM auditor |

---

## Contact

Repository owner: `4Um4`.

Primary project address: `https://github.com/4Um4/Enigma`.

---

*Мир — это не загадка для разгадывания. Мир — это живой организм, который вы ранили своим присутствием.*
```
