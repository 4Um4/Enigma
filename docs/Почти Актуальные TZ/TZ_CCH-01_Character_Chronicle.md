# ТЗ CCH-01 — «Character Chronicle / Хроника персонажа»

**Режиссёрский редактор причинной биографии НПС: от человеческого рассказа — к машинно-исполняемой истории**

| | |
|---|---|
| **Код документа** | CCH-01 (Character Chronicle) |
| **Адресат** | Архитектор ENIGMA |
| **Основание** | Авторское видение «Режиссёрский/нарративный редактор причинной биографии» (Google Docs, исходник ТЗ) |
| **Проект** | ENIGMA (Bloodloom), версия базы `0.5.4.2.7`, ветка `main`, базлайн IPT 49/49 |
| **Тип работ** | Новый центральный инструмент разработки + интеграция с существующим ядром |
| **Связанные документы** | `docs/ENIGMA_ROADMAP_v4_2_NL01_APPROVED.md` (трек AG1 Understanding), `docs/DTO Registry (Реестр контрактов).md` v9.1, `docs/UI_DOCTRINE_v1.0.md`, `docs/АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md`, `docs/Почти Актуальные TZ/ENIGMA_MAP_EDITOR_SMART_VALIDATION.md` |
| **Статус** | К исполнению. Исполненный документ подлежит самоочистке по протоколу §1.3 Устава |

---

## 0. Суть в одном абзаце

Не генератор биографий. Инструмент, в котором **автор пишет историю НПС человеческим языком** («В 8 лет осталась без родителей, переехала к Торнину…»), а ENIGMA **декомпозирует** этот текст в причинно связанное, машинно-исполняемое представление — события, отношения, эффекты, убеждения, время знания — и **задаёт вопросы только там**, где человеческая фраза неоднозначна для причинной модели. Незаполненные места остаются **белыми пятнами** и никогда не заполняются машиной самостоятельно. Канон утверждает только автор («Принять как канон»); LLM — декомпозитор и ассистент редактора, не причинный авторитет. Результат — «личность на начало игры» как сжатый результат прошлого персонажа и многолетняя социальная ткань, которой NPC не хватает перед первым тиком.

---

## 1. Проблема и обоснование

### 1.1. Как устроено сейчас

Сегодня предыстория NPC задаётся **вручную в JSON-конфигах** и запекается при загрузке:

- `config/npc/individuals/lusya.json` — поля `backstory`, `author_notes`, `hidden_truth`, `drives`, `psyche`, и главное — массив **`origin_events`**: пять рукописных записей с `summary`, `importance`, `emotion_tag`, `tags`, `is_secret`, `known_by`, `hidden_from`, `decay_rate` (пример: «Торнин ударил тебя за разбитую кружку… каждый звон кружки — триггер», importance 0.96, decay 0.001).
- `config/npc/social/village_relations.json` — рукописные парные отношения `base_trust` / `base_affection` / `nature` / `notes`.
- `config/canon/truth_state_tavern.json` — рукописный канон секретов мира, засеиваемый через `_seed_canon_secret_memories()`.

При старте новой игры `backend/app/services/npc/npc_loader.py::_convert_origin_events()` (строка 501) конвертирует `origin_events` в кортеж иммутабельных `EventMemory` (`backend/app/models/npc_state.py`) с `day=-1000` и `decay_rate=0.001` («origin забываются медленно»), а `village_relations.json` статично задаёт стартовые скаляры `RelationshipStore` (`backend/app/services/memory/relationship_store.py`).

### 1.2. Почему это перестаёт масштабироваться

Путь «автор → JSON → origin_events» работает, но: (а) автор пишет не историю, а структуру — пропадает режиссёрский темп; (б) причинность задаётся имплицитно (только через `tags`), её нельзя редактировать, не сломав формат; (в) «время знания» (`known_by`/`hidden_from`) переплетено с «историческим временем» в одном плоском массиве; (г) не существует места для **белых пятен** — намеренно неопределённых сущностей; (д) возраст персонажей отсутствует в модели данных вовсе (подтверждено аудитом AUD #9: `backend/app/services/phases/integration.py:476`, VERDICT=BLOCKED «age отсутствует в модели NPC вовсе»); (е) связь «вера ← из каких событий родилась» нигде не редактируется автором, хотя ядро уже умеет её считать (`CausalChain` в `backend/app/models/psychological.py`, `ProvenanceEntry` в `backend/app/domain/desire.py`).

### 1.3. Целевое состояние

Хроника становится **источником канона первого класса**: авторский текст — в машинную хронику — в стартовое состояние мира до первого тика. Механизм `origin_events` не ломается, а **поглощается**: JSON-конфиги становятся одной из проекций Хроники (см. §7.4, этап CCH-5).

---

## 2. Видение и непреложные принципы

**П1. Автор — источник канона. LLM — декомпозитор + ассистент редактора.** LLM предлагает декомпозицию (`attraction → стражник X`), но предложение остаётся **гипотезой**, пока автор не нажал «Принять как канон». Это прямое продолжение действующего инварианта проекта **INV-LLM-NOT-SSOT** («LLM — медленный консультант, не SSOT» — `docs/ENIGMA_ROADMAP_v4_2_NL01_APPROVED.md`, §3, трек AG1) и существующей архитектуры DeltaGate (`backend/app/services/memory/delta_gate.py`): интерпретация не мутирует состояние без проводки.

**П2. UI превращает повествование в форму, а не наоборот.** Автор не заполняет поля. Автор рассказывает историю — интерфейс сам выводит структуру (EVENT / RELATIONSHIP / LOCATION / EFFECTS / NEEDS CONFIRMATION).

**П3. Белые пятна — первоклассная сущность.** «В истории есть белые пятна» — и ENIGMA не должна их преждевременно заполнять. Сущность, которую автор пометил «оставить как белое пятно», должна существовать в модели данных, корректно отображаться в каждой проекции и корректно вести себя в симуляции до момента разрешения.

**П4. Два времени — обязательны.** Историческое время ( Люсе 8 / 12 / 14 лет) и **время знания** (факт «Торнин убил человека» произошёл в 11, а Люся узнала в 17) — раздельные оси. «История мира ≠ история знаний персонажей об этом мире» — центральное свойство архитектуры (WORLD TRUTH ≠ AGENT BELIEF, README §1).

**П5. Хроника — не фича, а инструмент разработки.** Редактор входит в основной контур разработки наряду с Map Editor (`frontend/map_editor/`) и F5-лабораторией (`frontend/map_editor/ui/lab_screen.py`): без него невозможна ручная сборка многолетней социальной ткани перед первым тиком.

**П6. Эпистемическая честность и изоляция.** Редактор работает в доверенном контуре (layer 4 UI Doctrine — «метаинформация/отладка», `docs/UI_DOCTRINE_v1.0.md` §IX) и видит каузальный слой. Игровой UI по-прежнему не видит внутренние состояния NPC (Закон IV UI Doctrine; `frontend/presentation_firewall.py`). Character Debugger живёт в layer 4 и недоступен в чистом геймплее как «чит».

**П7. Детерминизм и воспроизводимость.** Всё, что Хроника кладёт в мир, должно попадать в replay-контур: seed-пайплайн обязан работать в режиме record (`backend/app/services/replay/replay_recorder.py`), и никакая генерация не должна опираться на wall-clock или `random.*` (глобальные запреты DTO Registry §0; KernelRNG — `backend/app/core/`, salt-привязка как в `llama_cpp_provider.py`).

---

## 3. Термины и модель данных

Новые DTO регистрируются в `docs/DTO Registry (Реестр контрактов).md` (формат записи: `📦 DTO / 🔗 Поток / 📁 Файл / 🚫 КАУЗАЛЬНЫЕ ЗАПРЕТЫ`; иммутабельные записи — только `@dataclass(frozen=True)`; случайные и wall-clock источники в kernel-слое запрещены).

### 3.1. Хроника и её записи

**`ChronicleDocument`** — документ Хроники одного персонажа: `chronicle_id`, `npc_ref` (ссылка на NPC или white-spot), `author_text` (исходный человеческий текст, append-only по абзацам), `entries`, `white_spots`, `canonical` (флаг/версия канона), `created_by_tick_source` (прологепистический якорь), `schema_version`.

**`ChronicleEntry`** — единица машинной хроники, результат декомпозиции одного повествовательного фрагмента:

| Поле | Тип / допустимые значения | Смысл |
|---|---|---|
| `entry_id` | детерминированный `md5(chronicle_id:fragment_ord:ordinal)` | идентификация, replay-safe |
| `historical_age` | `int \| None` | историческое время («[8 лет]») |
| `historical_year` | `int \| None` | альтернативная ось времени (год мира) |
| `kind` | `EVENT / RELATIONSHIP / LOCATION / EFFECT / BELIEF_SEED / OBSERVATION / KNOWLEDGE_LINK / TRAIT_SEED` | тип декомпозированного факта |
| `subject_id` | `EntityRef` | кто (Люся) |
| `object_id` | `EntityRef \| WhiteSpotRef \| None` | на кого / с кем («Торнин», «стражник ?») |
| `payload` | замороженный dict по схеме `kind` | поля события/отношения/эффекта |
| `causes` | `Tuple[CauseRef, ...]` | авторские основания (см. 3.3) |
| `provenance` | `LLM_DRAFT / AUTHOR_CONFIRMED / AUTHOR_AUTHORED` | статус канона (П1) |
| `confidence` | `float 0..1 \| None` | уверенность LLM-гипотезы; для AUTHOR_* не хранится |
| `open_questions` | `Tuple[ClarificationQuestion, ...]` | вопросы, породившие запись |

**`EntityRef`** — ссылка на сущность: `resolved` (существующий NPC, напр. `tavern_keeper_tornin`) | `new_npc` (создать при канонизации) | `white_spot` | `unknown_person` (фоновая массовка без тик-агента). Резолв имён — через существующие словари имён: `name_forms` в `config/npc/individuals/*.json` и `frontend/npc_name_resolver.py`.

**`WhiteSpot`** — намеренно неопределённая сущность: `white_spot_id`, `label` («стражник»), `context_hint` (из какого фрагмента возникла), `resolution_state ∈ {OPEN, RESOLVED_AS_NPC, RESOLVED_AS_UNKNOWN, RESERVED}`, `resolution_ref`. Белое пятно может участвовать в отношениях и событиях хроники; инвариант преждевременного заполнения — см. §8 (запреты).

**`KnowledgeLink`** — фиксация времени знания: `event_ref` (ChronicleEntry), `knower_id` (EntityRef), `learned_age`/`learned_year` (момент узнавания), `channel ∈ {WITNESSED, TOLD, OVERHEARD, DEDUCED, UNKNOWN}`, `certainty`. Инвариант: `learned_age >= event.historical_age`. Прямой прообраз — поля `is_secret / known_by / hidden_from` в `EventMemory` (`backend/app/models/npc_state.py`, продемонстрированы в `lusya.json::origin_events`) и `EpistemicRecord.first_observed_tick` (`backend/app/domain/epistemology.py`).

### 3.2. Декомпозиция (transient-модель)

**`BiographyDecomposition`** — результат работы декомпозитора над одним фрагментом: список `DecompositionItem(kind, draft_payload, confidence, needs_confirmation: bool, question)` — то, что UI показывает в панели «РАЗБОР ENIGMA». Не канон, не хранится как истина; после подтверждения превращается в `ChronicleEntry(provenance=AUTHOR_CONFIRMED)`.

**`ClarificationQuestion`** — вопрос автору: `question_id`, `target_span` (на какой кусок текста), `options: Tuple[ClarificationOption, ...]`, где `ClarificationOption ∈ {SELECT_EXISTING_NPC(preview), CREATE_NEW_NPC(draft), UNKNOWN_PERSON, LEAVE_WHITE_SPOT}` + свободный ввод. Обязателен вариант «оставить как белое пятно» (П3).

### 3.3. Причины (режим «Причины»)

**`CauseRef`** — ссылка на авторское основание: `cause_kind ∈ {EVENT, RELATIONSHIP, TRAIT, NEED, OBSERVATION, UNKNOWN}` (шесть типов из видения документа) + `origin_ref` (entry_id / white_spot_id / свободный текст, оформленный как entry). 

Каузальная цепочка для отображения собирается из существующих механизмов: `CausalChain` (`backend/app/models/psychological.py`: `source_event → observation → memory → belief → decision → action → state_delta → world_change`), `CausalEntry` (паспорт изменения состояния с `emotional_impact`), `ProvenanceEntry` (`backend/app/domain/desire.py`, L-M1 «множественная причинность», `DesireSource ∈ {NEED, DRIVE, VALUE, RELATIONSHIP, OBLIGATION, LEARNED}`), `TraceSource ∈ {PERCEPTION, TESTIMONY, INTROSPECTION}` (`backend/app/models/npc/experience_trace.py`). Хроника наследует эту семантику, а не изобретает новую.

### 3.4. Возраст

Ввести **`birth_epoch`** (абсолютный `total_seconds` оси `Calendar`, `backend/app/core/calendar.py`) и **`age_at_game_start`** в профиль NPC. Места: `NPCProfileL0` (`backend/app/models/npc_profile.py`, frozen) как источник и, при необходимости, projection в `NPCState`. Снимает блокер аудита #9 (age_factor для `PsycheBase.linguistic_integrity`, `backend/app/services/phases/integration.py:476`). Хроника оперирует возрастом как человекочитаемой проекцией (`[8 лет]` ⇄ `birth_epoch + 8 лет × seconds_per_year`), хранит обе формы.

## 4. Функциональные требования

Требования нумеруются `FR-x.y`; каждый пункт проиллюстрирован эталонным примером «Люся» из исходного видения (совпадает с реальным NPC `maid_lusya` в `config/npc/individuals/lusya.json` — эталонный мир для приёмочных сценариев).

### 4.1. Режим «История» (авторский ввод)

**FR-1.1.** Левая область редактора — свободный текст, разбитый на фрагменты-абзацы. Автор **не** заполняет поля формы; ввод — повествование.

**FR-1.2.** Поддержка человекочитаемых маркеров времени в тексте: `[8 лет]`, «в 14 лет», «с 12 лет», «в сентябре». Парсер выделяет возрастной якорь фрагмента (`historical_age`) и, где возможно, сезонный/календарный хинт. Неоднозначный якорь → вопрос в `ClarificationQuestion`, не ошибка.

**FR-1.3.** Интерфейс отображает ввод как **временную причинную ленту** — хронологический порядок фрагментов (главная сущность интерфейса). Требование не о рендере текстового редактора, а о ленте как оси: `8 лет → 12 лет → 14 лет → …`.

**FR-1.4.** Каждый фрагмент независимо отправляется на декомпозицию (FR-2.x). Обработка асинхронная, UI не блокируется (прецедент неблокирующей очереди ввода: `frontend/api_client.py::ActionQueue`).

**FR-1.5.** Исходный текст фрагмента хранится в `ChronicleDocument.author_text` всегда; декомпозиция обратима и перепроводима (re-decompose) без потери авторского текста.

### 4.2. Режим «Разбор» (ENIGMA Decomposition)

**FR-2.1.** Правая область — панель `ENIGMA DECOMPOSITION`, показывающая для активного фрагмента список `DecompositionItem`: блоки `EVENT` (название события, возраст), `RELATIONSHIP` (Люся → Торнин, relation), `LOCATION` (Трактир Торнина), `EFFECTS` (родители = dead, guardian = Торнин, residence = tavern).

**FR-2.2.** Декомпозитор — LLM-сервис, вызываемый через `ModelRouter.request(capability=...)` (`backend/app/services/llm/router.py`; в реестре уже есть capability `FACT_EXTRACTION`). Выход — строго JSON (JSON Mode `response_format={"type":"json_object"}`, `temperature=0.0`, seed из `KernelRNG(salt=фрагмент)` — точный прецедент: `backend/app/services/input/llm_compressor_client.py::_sync_compress`). Схема ответа валидируется отдельным нормализатором по образцу `DMResponseNormalizer` (`backend/app/services/verbalization/dm_response_normalizer.py`); невалидный ответ → retry → пометка фрагмента «не разобрано», **никаких молчаливых фолбэков** (запрет silent fallback — DTO Registry, поток 1).

**FR-2.3.** Всё, что декомпозитор уверен в пределах порога, показывается как **гипотеза**; ниже порога — как `needs_confirmation` с вопросом. Порог калибруется (см. FR-9.4).

**FR-2.4.** Промпт декомпозитора выносится в файл `backend/prompts/chronicle_decompose_system.txt` (прецедент: `backend/prompts/dm_system.txt`, загрузчик `load_system_prompt` в `backend/app/services/verbalization/prompt_loader.py`). Промпт включает: реестр `kind`, онтологию EntityRef, правило «не выдумывать ID», языковой якорь «только русский».

**FR-2.5.** Декомпозитор обязан **не** создавать NPC сам. Любая новая персона в декомпозиции — кандидат (`CREATE_NEW_NPC`) до явного решения автора (FR-3.1).

### 4.3. Белые пятна

**FR-3.1.** На неопознанную сущность («стражник») редактор показывает диалог `НЕОПРЕДЕЛЁНО` с ровно четырьмя опциями: (а) **уже существующий NPC** — с выбором из резолвера имён (`name_forms` + `frontend/npc_name_resolver.py`); (б) **создать нового NPC** — минимальный драфт (имя, архетип из `config/npc/archetypes/*.json`); (в) **неизвестный человек** — фоновая сущность без тик-агента; (г) **оставить как белое пятно**. Решение фиксируется в `WhiteSpot.resolution_state`.

**FR-3.2.** Белое пятно существует в данных и проекциях: участвует в отношениях (`RelationshipStore`), в событиях хроники, отображается во всех панелях со значком неопределённости. В симуляцию до резолюции не попадает как тик-агент; события с его участием хранятся как факты хроники.

**FR-3.3.** Инвариант «не заполнять преждевременно»: ни декомпозитор, ни сеялка, ни любой другой сервис не имеют права резолвить `WhiteSpot` автоматически. Единственный писатель `resolution_state` — действие автора в UI (writer-guard в стиле `_ALLOWED_WRITERS` из `backend/app/models/npc_state.py`).

**FR-3.4.** Резолюция белого пятна — обратимая проводка: все `entry`, ссылавшиеся на `white_spot_id`, перелинковываются на выбранную сущность; история смены сохраняется.

### 4.4. Машинная хроника

**FR-4.1.** После подтверждения фрагмент превращается в ветку **машинной хроники** — дерево `ChronicleEntry` по возрастам (эталон из документа: `8 лет → родители→смерть / опекун→Торнин / место жительства→трактир / занятие→официантка; 12 лет → abuse→Торнин; 14 лет → attraction→Стражник ? + observation: стражник пришёл с женой, повод→годовщина союза`).

**FR-4.2.** Машинная хроника — **исходный материал для causal engine**: из неё строятся `CauseRef`-связи и seed-структуры §7.4. Дерево отображается в центральной панели (временная лента) и в режиме «⏳ Время».

**FR-4.3.** `ChronicleEntry` с `kind=KNOWLEDGE_LINK` визуализирует разнесение двух времён (FR-6.x): факт → стрелки `knowledge → Люся @17`, `knowledge → Анна @12`, `unknown → Марк`.

### 4.5. Режим «Причины»

**FR-5.1.** Для любого `ChronicleEntry` (пример: «В 14 лет Люся влюбилась в стражника») доступна панель `ПОЧЕМУ?` с авторскими основаниями: шесть типов `cause_kind` — событие / отношение / черта характера / потребность / наблюдение / неизвестно — плюс «[+] добавить». `UNKNOWN` — легальный тип основания (позиция автора «причина не определена»), не заглушка.

**FR-5.2.** Основание может быть человеческой фразой («Она впервые увидела человека, который обращался с женой мягко…»), которая сама проходит декомпозицию и порождает свои записи + связи (пример из видения: `Торнин→Люся abuse → негативная модель отношений`; `Стражник→жена gentle interaction → наблюдение Люси → контраст → идеализация → attraction`).

**FR-5.3.** Запрещено выражать причину скаляром без происхождения («Любовь = 0.8» — явный антипример видения). Панель «Причины» не редактирует числа `RelationshipStore`; она редактирует **происхождение**. Числа, если нужны, вычисляются сеялкой из структуры (§7.4) и помечаются `origin_ref`.

**FR-5.4.** Авторская причинная связь — это `CauseRef` в `ChronicleEntry.causes`; множественные причины допустимы (прообраз — `provenance: Tuple[ProvenanceEntry, ...]` в `backend/app/domain/desire.py`).

### 4.6. Личность на начало игры

**FR-6.1.** Отдельная вкладка «Личность к началу игры» показывает **не скаляры** (`kindness 73` — антипример), а **сформировавшиеся представления** — убеждения в виде человеческих формулировок: «Любовь может быть безопасной, если мужчина уважает женщину», «Слабость нельзя показывать Торнину», «Стражники = люди, которые могут защитить».

**FR-6.2.** Рядом — блок `ПРОИСХОЖДЕНИЕ`: карта «какие события сформировали эту веру» (`[Событие 17] ↓, [Событие 23] → belief ↑, [Событие 31] ↑`). Каждое представление обязано иметь непустое происхождение либо флаг «врождённая склонность» (из `drives_base` / `PsycheBase` профиля L0).

**FR-6.3.** Маппинг в ядро: представления → `BeliefState` (`backend/app/models/npc/beliefs.py`) и/или `CrystallizedBelief` (`backend/app/domain/identity_events.py`, L2.5, асимметричная травма ×6), черты → `NPCIdentityL1.active_traits` (`backend/app/models/npc_state.py`). Решение, какая форма для какого представления, — в §7.4 (этап CCH-4).

**FR-6.4.** Автор может «открыть, почему именно этот NPC такой» из любой проекции (вкладка Хроника ⇄ Личность ⇄ Причины связаны двунаправленной навигацией по `entry_id`).

### 4.7. Два времени: историческое и время знания

**FR-7.1.** Каждое событие хроники имеет историческое время (`historical_age/year`). Каждое `KnowledgeLink` имеет время знания (`learned_age`). Оси независимы; UI обязан уметь показывать событие, произошедшее «в 11 лет», и знание о нём, появившееся «в 17» (эталон: «Торнин убил человека»).

**FR-7.2.** Список знающих о событии — явный и конечный: `knowledge → Люся @17`, `knowledge → Анна @12`, `unknown → Марк`. `unknown` — валидное состояние знания (прообраз «Vacuum»-семантики `RelationshipStore.get_pair()` → `{}`: «нет записи = нет знания»).

**FR-7.3.** Сеялка обязана транслировать `KnowledgeLink` в стартовую эпистемику NPC: `EventMemory.known_by/hidden_from/is_secret` (`backend/app/models/npc_state.py`) для секретов и `EpistemicRecord.first_observed_tick` (`backend/app/domain/epistemology.py`) для пропозиций, с обратной конвертацией `learned_age → тик` относительно `birth_epoch` (см. FR-9.2).

### 4.8. Режим «Связи» и «Знания»

**FR-8.1.** «Связи»: панель отношений персонажа (`Торнин — страх/зависимость; Стражник — идеализация; Люда — доверие`) с переходом в происхождение каждого скаляра. Seed-цель — `RelationshipStore` (`backend/app/services/memory/relationship_store.py`, шкала [−100, 100], ключ `"{source}→{target}"`) и `village_relations.json` как проекция канона.

**FR-8.2.** «Знания»: сводка «кто что знает» по хронике (матрица событие × персонаж: WITNESSED / TOLD @возраст / unknown), собираемая из `KnowledgeLink` без вычислений над ядром.

### 4.9. Character Debugger (в игре)

**FR-9.1.** В игровом режиме доступен инспектор персонажа (эскиз документа: «F12 → Character»): текущие `Emotion` (стрелки динамики), `Desire` (безопасность, признание), `Beliefs`, `RELATIONSHIPS` и блок `ИСТОЧНИКИ → открыть хронику`. Панель живёт в **layer 4** UI Doctrine (метаинформация/отладка) и открывается как окно Workbench, а не HUD.

**FR-9.2.** Клик по элементу («страх Торнина») открывает **дрейл-даун причинности**: `12 лет → рукоприкладство Торнина → эпизодическая память → ожидание повторения → avoidance behaviour`. Данные — из каузального слоя ядра: `causal_ledger` (`NPCState`, endpoint `GET /api/debug/npc/{npc_id}/causal_ledger` в `backend/app/api/routes_debug.py` — «God Mode» уже возвращает psyche.stress, will_state, temporary_drives и полный ledger), память — `GET /api/debug/memories/{campaign_id}/{npc_id}` (`backend/app/api/routes.py`), кристаллизованные убеждения — `CrystallizedBeliefStore`.

**FR-9.3.** Хоткей F12 **занят** Workbench (`frontend/game_screen.py:782`, `frontend/map_editor/core/event_handler.py:69`) — Character Debugger открывается **внутри** Workbench как окно (`WindowManifest`, id `character_debugger`, hotkey `K_c` или через реестр хоткеев `frontend/keybindings.py`), а не отдельным режимом. Финальный хоткей — решение архитектора, конфигурируемый.

**FR-9.4.** Режим автора в игре не обязателен для MVP-редактора; вкладка «СЕЙЧАС» (Emotion/Desire/Beliefs) заполняется из runtime-состояния, вкладка «ИСТОЧНИКИ» — из хроники канона. Расхождение «хроника vs runtime» (игра отклонилась от канона) — легальный результат, показывается как есть, не чинится автоматически.

### 4.10. Канонизация

**FR-10.1.** Кнопка «Принять как канон» — единственный механизм перевода `LLM_DRAFT → AUTHOR_CONFIRMED`. До канонизации декомпозиция — гипотеза; она не попадает ни в одну проекцию на ядро (ни в seed, ни в экспорт).

**FR-10.2.** Канонизация атомарна по фрагменту: подтверждение всего `DecompositionItem`-набора фрагмента либо с частичными исключениями (по-пунктно). Отмена канонизации возможна с явной пометкой версии (`canonical_version++`).

**FR-10.3.** Экспорт канона: `ChronicleDocument` → (а) обновление `config/npc/chronicles/<npc_id>.json` (каноническое хранилище хроник, новое); (б) совместимая проекция `origin_events`-формата для бесшовной работы текущего `npc_loader` (этап CCH-5, §7.4); (в) проекция секретов → `config/canon/truth_state_*.json` (`Secret.secret_id, participants, canonical_truth, initial_holders` — `backend/app/models/truth_state.py`, загрузчик `backend/app/services/truth_state_loader.py`).

### 4.11. Сеялка предыстории (Chronicle → мир)

**FR-11.1.** При создании новой игры сеялка строит стартовое состояние из канонической хроники: имплантация `EventMemory` (по прецеденту `_convert_origin_events`, `backend/app/services/npc/npc_loader.py:501`: `day=-1000`, `decay_rate=0.001`, `importance` из хроники), инициализация `RelationshipStore` из связей хроники, засев секретов в `TruthState`, установка `BeliefState`/`active_traits`/`AffectiveImprint` (`backend/app/models/affect.py`: `pain/fear/humiliation_signature` — для травм вроде «каждый звон кружки — триггер»).

**FR-11.2.** Сеялка работает **вместо** (не поверх) legacy-пути `_convert_origin_events`/`village_relations.json`, когда для NPC существует каноническая хроника; при её отсутствии — legacy-путь сохраняется. Оба пути обязаны быть replay-детерминированы.

**FR-11.3.** Время знания в seed: `learned_age` конвертируется в `known_by`/`hidden_from`; событие с `unknown → Марк` не должно оставить у Марка ни `EventMemory`, ни `EpistemicRecord` (эпистемическая изоляция).

**FR-11.4.** Возраст: `birth_epoch` вычисляется из `age_at_game_start` и стартового `total_seconds` кампании; хроника хранит возрастные якоря, сеялка/календарь конвертируют (FR-9.2 из §3.4).

---

## 5. UI-спецификация

### 5.1. Композиция (5 областей, эталон-эскиз документа)

```
┌────────────────────────────────────────────────────────────┐
│ ЛЮСЯ                                      [Возраст: 27]     │
├──────────────┬──────────────────────────────┬──────────────┤
│ ХРОНИКА      │       ВРЕМЕННАЯ ЛЕНТА        │ РАЗБОР ENIGMA│
│ 8/12/14 лет  │ ● события ленты              │ EVENT/RELATION│
│              │                              │ BELIEF/MEMORY│
│              │                              │ ⚠ 2 вопроса  │
├──────────────┴──────────────────────────────┴──────────────┤
│ ПОСЛЕДСТВИЯ / ПРИЧИНЫ / СВЯЗИ / БЕЛЫЕ ПЯТНА / KNOWLEDGE    │
└────────────────────────────────────────────────────────────┘
```

- Заголовок: имя + текущий расчётный возраст на любой момент оси (из `birth_epoch`, FR-9.2 §3.4).
- Левая колонка — режим «История» (текст фрагментов по возрастам).
- Центр — временная причинная лента (машино-читаемое дерево, FR-4.1).
- Правая — панель декомпозиции с числом открытых вопросов.
- Нижняя лента — переключатель нижних панелей: Последствия / Причины / Связи / Белые пятна / Знания.

### 5.2. Режимы (7, по видению документа)

| Режим | Содержимое | Требования |
|---|---|---|
| ✍ История | авторский ввод | FR-1.x |
| 🧠 Разбор | декомпозиция ENIGMA | FR-2.x |
| 🔗 Причины | авторские основания, каузальные цепочки | FR-5.x |
| 👥 Связи | отношения между персонажами | FR-8.1 |
| 👁 Знания | кто что знает (две оси времени) | FR-7.x, FR-8.2 |
| ⏳ Время | история до начала игры (лента целиком) | FR-4.2 |
| ⚠ Белые пятна | реестр неопределённостей + резолюции | FR-3.x |

### 5.3. Технологический каркас

- Редактор реализуется в **pygame-контуре фронтенда** и открывается **из главного меню** (`frontend/game_menu.py`, `MenuAction` — добавить `CHRONICLE_EDITOR` по прецеденту `EDITOR` → `game_launcher.py::_launch_editor`), с автономной точкой входа по прецеденту `frontend/map_editor/editor_launcher.py`.
- Обязателен режим внутри **Map Editor** (новый `MODE_CHRONICLE` в `frontend/map_editor/tools/constants.py` по прецеденту `MODE_LAB`/`MODE_UIWORKBENCH`): автор, правящий карту локации, должен уметь открыть хронику любого размещённого NPC.
- Панели — в идеологии «окно = данные» (`frontend/ui_workbench/manifests.py`: `WindowManifest(id, hotkey, layer, data_source)`; `layer ∈ {2,3,4}`): каждой панели — свой `data_source` (DTO-канал), никаких прямых импортов backend в окна (Закон 1.1, `scripts/lint_frontend_isolation.py`).
- Тексты интерфейса — через `frontend/i18n.py` (`ui:`-ключи).
- Валидационные сообщения — по-русски, с `fix_hint`, по стандарту Map Editor «Save = Contract» (`docs/Почти Актуальные TZ/ENIGMA_MAP_EDITOR_SMART_VALIDATION.md`): канонизация блокируется при неразрешённых критических вопросах фрагмента (вопрос открыт + автор не выбрал «белое пятно» → блок с подсказкой).

## 6. Карта интеграции с кодовой базой (привязки «что ↔ где»)

Таблица — обязательный навигатор для архитектора: каждый пункт видения → существующие точки опоры → что создать. Все пути от корня репозитория `Enigma-main/`.

### 6.1. Понимание человеческого текста (Understanding-контур)

| Что требует ТЗ | Где опора (существует) | Что сделать |
|---|---|---|
| Разбор свободного текста в структуру | `backend/app/services/input/intent_compressor.py` — Fast Path (pymorphy3-леммы, детерминированный) + Slow Path (LLM); `backend/app/services/input/llm_compressor_client.py` — `LlamaCppCompressorClient.compress_intent()` с JSON Mode; `backend/app/domain/intent_profile.py` — `IntentSemanticField` (semantic_acts, proposition, addressee); инвариант «понятое не умирает на конвертации» (`backend/app/domain/intent.py`) | Новый сервис **`backend/app/services/chronicle/biography_decomposer.py`** по той же двухконтурной схеме: детерминированный препарсинг (возрастные якоря `[8 лет]`, кавычки имён) + LLM-декомпозиция; переиспользовать `LLMCompressorClient`-паттерн |
| LLM-канал и capability | `backend/app/services/llm/router.py` — `ModelRouter.request(capability=...)`, реестр `MODEL_REGISTRY`, capability `FACT_EXTRACTION` уже объявлен; `backend/app/services/llm/provider.py` — `GenerationParams(response_format=...)`; `backend/app/services/llm/llama_cpp_provider.py` — seed через `KernelRNG(tick, npc_id, salt=prompt)`, `_strip_thinking()` | Использовать capability `FACT_EXTRACTION`; убедиться, что Replay-кэш LLM (`backend/app/services/replay/llm_cache.py::compute_prompt_hash`) покрывает вызовы декомпозитора (set_replay_context) |
| Валидация ответа LLM | `backend/app/services/verbalization/dm_response_normalizer.py` (`DMResponseNormalizer.normalize` — снятие ```json, depth-1 decode, fallback-схемы); `backend/app/services/verbalization/response_validator.py` | Новый `ChronicleDecompositionNormalizer` (тот же стиль; запрет silent fallback) |
| Промпт | `backend/prompts/dm_system.txt` (единственный промпт-файл), загрузчик `backend/app/services/verbalization/prompt_loader.py::load_system_prompt` | Новый файл `backend/prompts/chronicle_decompose_system.txt` |
| Прецедент импорта человеческого текста | `backend/app/services/knowledge_ingest.py` (`KnowledgeIngestService.ingest` → `LayeredMemory.write_world_canon/...`), `backend/app/services/pdf_drop_importer.py` (`PdfDropImporter` — батч-импорт PDF/TXT/MD, классификация по имени файла; реализован, но не подключён к API — решение о его судьбе см. §12) | Хроники — **не** в LayeredMemory (это RAG-контекст DM), а в каноническое хранилище §6.4; не путать каналы |

### 6.2. Модель персонажа и психики (куда оседает хроника)

| Что требует ТЗ | Где опора (существует) | Что сделать |
|---|---|---|
| Создание нового NPC из редактора | `backend/app/services/npc/npc_loader.py` (`load_profile_from_legacy_json`, наследование `archetypes/_base_humanoid.json → archetypes/<arch>.json → mixins → individual`); примеры `config/npc/individuals/{lusya,tornin,goran,borko,orm,shadow}.json`; `backend/app/models/npc_profile.py` — `NPCProfileL0` (frozen) | Форма «создать нового NPC» пишет драфт-конфиг individual-JSON; canonical-хроника связывается по `npc_id` |
| Эффекты хроники → стартовое состояние | `EventMemory` (`backend/app/models/npc_state.py`, frozen; поля `day/importance/clarity/decay_rate/is_secret/known_by/hidden_from/secret_id`); `_convert_origin_events()` (`npc_loader.py:501`, `day=-1000`, decay 0.001, «origin — авторитет идентичности факта») | **`backend/app/services/chronicle/chronicle_seeder.py`** — новый писатель seed-состояния (§7.4), потребляемый рядом с `npc_loader` при `new_game` (`POST /api/game/new/{campaign_id}` → `backend/app/api/routes.py`) |
| Убеждения «на начало игры» | `BeliefState/BeliefFragment/BeliefType` (`backend/app/models/npc/beliefs.py`; writer-guard `_UPDATE_ALLOWED_WRITERS`); `CrystallizedBelief` (`backend/app/domain/identity_events.py`; продюсеры `backend/app/services/npc/{pattern_detector,belief_crystallization_engine,crystallized_belief_store}.py`; травма ×6); `NPCIdentityL1.active_traits` (пишет `backend/app/services/memory/resonance_engine.py` через `EventMemory.to_identity_weight()`) | Сеялка расширяет allowlist писателей (только через ADR — инвариант отчёта по моделям); human-формулировки убеждений хранить в хронике, в ядро оседают типизированные формы |
| Травмы и «триггеры» (звон кружки) | `AffectiveImprint` (`backend/app/models/affect.py`: `trigger_tags, pain/fear/humiliation_signature, decay_rate=0` — вечная травма); `backend/app/services/affect.py::apply_conditioning` (создание импринта при identity_damage > 0.2) | Эффект `kind=EFFECT` с тегом травмы → импринт с `decay_rate=0` и `trigger_tags` из текста (детерминированный словарь триггеров — предмет этапа CCH-4) |
| Желания (Desire: безопасность, признание) | `backend/app/domain/desire.py` — `Desire` (frozen; `subject_class, urgency, provenance: Tuple[ProvenanceEntry], born_tick, learned_from`; `DesireSource ∈ {NEED,DRIVE,VALUE,RELATIONSHIP,OBLIGATION,LEARNED}`); `backend/app/services/npc/desire_generator.py` (флаг `DESIRES_ENABLED`, default OFF) | Семя желания из хроники — `kind=EFFECT` с provenance-ссылками на CauseRef; активация канала desires — вне скоупа, но формат совместим |
| Отношения (страх/зависимость/идеализация) | `backend/app/services/memory/relationship_store.py` (`RELATIONSHIP_KEYS = ("trust","fear","debt","respect","attraction")`, [−100,100], насыщение, `saves/<campaign>/npc_relationships.json`); статика `config/npc/social/village_relations.json` (`base_trust/base_affection/nature/notes`); `backend/app/models/social.py::Relationship`; RE-домен `backend/app/domain/relationship_contracts.py` (`NeedSlot`, `PreferenceModel`, `ExclusivityRequirement`) | Связи хроники → seed `RelationshipStore` + проекция в `village_relations.json` (этап CCH-5). `attraction` — существующий ключ: «влюбилась в стражника» кладётся в него с `origin_ref` |
| Возраст | **Поле age в модели отсутствует** (аудит #9: `backend/app/services/phases/integration.py:476` VERDICT=BLOCKED; `PsycheBase.linguistic_integrity=1.0` константа — docstring ожидает `age_factor`) | `birth_epoch` + `age_at_game_start` в `NPCProfileL0` (`backend/app/models/npc_profile.py`); конверсия через `backend/app/core/calendar.py::Calendar.decompose(total_seconds)` (ось `total_seconds`, сейв-совместимая) |
| Время и календарь | `backend/app/core/calendar.py` (stateless от `total_seconds`; `DAYS_PER_YEAR=365`, `MONTH_NAMES_RU`), `backend/app/core/constants.py` (`TICKS_PER_DAY=24`), `backend/app/services/temporal/temporal_engine.py` (`TemporalContext.game_day`), `backend/app/domain/world_epoch.py` (иммутабельные эпохи, `WorldView`/`TickOverlay`) | `historical_age → total_seconds` — чистая функция в сеялке; событие хроники «в 8 лет» → отрицательный сдвиг от `birth_epoch` (сохранять как `day<0` в `EventMemory` — прецедент −1000 уже есть) |

### 6.3. Эпистемика: «кто что знает» (время знания)

| Что требует ТЗ | Где опора (существует) | Что сделать |
|---|---|---|
| Знание о событии per-agent | `EpistemicRecord` (`backend/app/domain/epistemology.py`: `agent_id, proposition, confidence, source_id, first_observed_tick, last_updated_tick`); хранилище `backend/app/services/npc/epistemic_store.py` (`Dict[(agent_id, Proposition)] → EpistemicRecord`); наполнение: `backend/app/services/events/observation_subscriber.py` (прямое наблюдение, LOS, `_OBSERVATION_SIGHT_RADIUS=10.0`) и `claim_event_subscriber.py` (testimony, `TrustBasedReliabilityProvider`) | Сеялка пишет `first_observed_tick` из `learned_age` (отрицательные тики легальны до первого тика, согласовать с `TemporalEngine.reset_campaign()`); канал `TOLD` в хронике → seed как testimony-происхождение |
| Секреты | `backend/app/models/truth_state.py` (`TruthState.secrets: Secret(secret_id, participants, canonical_truth, importance, initial_holders, discovery_surface...)`, `TruthRelation: CAUSES/CONTRADICTS/DEPENDS_ON/REVEALS/CONCEALS/ENABLES/EXPLAINS`); загрузка `backend/app/services/truth_state_loader.py`; канон-пример `config/canon/truth_state_tavern.json`; засев `_seed_canon_secret_memories()` (`npc_loader.py`) | Эффекты с `is_secret` → `Secret` + `TruthRelation` (например «Торнин убил человека» → `initial_holders=[Торнин]`, `knowledge → Люся@17` через `known_by`); `Secret.canonical_truth` = авторская формулировка |
| Запрет телепатии | Инварианты «No Telepathy / Epistemic Isolation» (`observation_subscriber.py`, DTO Registry §7) | Сеялке запрещено создавать знание там, где хроника говорит `unknown → Марк` — плюс тест (§10) |

### 6.4. Хранилище и API редактора

| Что требует ТЗ | Где опора (существует) | Что сделать |
|---|---|---|
| Канонические хроники | Разделение «статический мир vs runtime»: `backend/data/` vs `saves/` (ADR-O-146; `backend/app/core/config.py::saves_dir`); канон NPC — `config/npc/**`; канон секретов — `config/canon/**` | Новое: `config/npc/chronicles/<npc_id>.json` (канон, версионируется) + черновики `saves/<campaign>/chronicle_drafts/<npc_id>.json`. Схема `schema_version=1`, валидатор по образцу `truth_state_loader.py::validate` |
| API редактора | `backend/app/api/routes.py` (~50 эндпоинтов, префикс `/api`; прецеденты: `POST /characters/upsert`, `POST /knowledge/import`, `GET /npcs/{campaign_id}`); `routes_debug.py` (`GET /debug/npc/{npc_id}/causal_ledger`, префикс `/debug`) | Новый роутер **`backend/app/api/routes_chronicle.py`**: `GET /api/chronicle/npcs` (список + статусы хроник), `GET/PUT /api/chronicle/{npc_id}/draft`, `POST /api/chronicle/{npc_id}/decompose` (фрагмент → decomposition), `POST /api/chronicle/{npc_id}/clarify` (ответ на вопрос), `POST /api/chronicle/{npc_id}/canonize`, `GET /api/chronicle/{npc_id}/knowledge-matrix`. Подключить в `backend/app/main.py` |
| Character Debugger (в игре) | `backend/app/api/routes_debug.py::GET /debug/npc/{npc_id}/causal_ledger` — уже возвращает роль, стресс, will_state, temporary_drives, полный ledger; `GET /debug/memories/{campaign_id}/{npc_id}` (`routes.py`); `WorldSnapshotDTO` (`backend/app/domain/snapshot.py`) — граница backend→frontend | Окно Workbench `windows/character_debugger_window.py` с `data_source="character_debugger"`; при необходимости расширить `causal_ledger`-endpoint выборкой `CrystallizedBeliefStore` и `EventMemory.narrative_cache` (только layer-4 канал, в `WorldSnapshotDTO` **не** добавлять) |

### 6.5. UI-контур

| Что требует ТЗ | Где опора (существует) | Что сделать |
|---|---|---|
| Редактор как приложение | `frontend/game_menu.py` (`MenuAction.NEW_GAME/CONTINUE/EDITOR/SETTINGS/EXIT`), `game_launcher.py::_launch_editor()` (запуск `EditorCore`), автономный `frontend/map_editor/editor_launcher.py` | `MenuAction.CHRONICLE_EDITOR` → запуск Chronicle Editor; автономный `frontend/chronicle_editor/editor_launcher.py` |
| Режим в Map Editor | `frontend/map_editor/tools/constants.py` (`MODE_WORLD/MODE_LOCAL/MODE_LAB/MODE_UIWORKBENCH`), `frontend/map_editor/core/event_handler.py` (TAB/F5/F12), `frontend/map_editor/ui/lab_screen.py` (F5-лаборатория — microscope над production) | `MODE_CHRONICLE` + открытие хроники NPC по клику на размещённого NPC (данные из `frontend/map_editor/data/npc_data.py`) |
| Окна/панели | `frontend/ui_workbench/` (`WindowManifest`, `WindowRegistry`, `InputDispatcher`, `WorkbenchScreen`, тема/шрифты `theme.py`/`fonts.py`); окна-прецеденты `windows/journal_window.py`, `windows/board_window.py` (data_source `investigation_board` → `GET /api/board/{campaign}`) | 7 панелей-окон хроники, каждая со своим `data_source`; layer 3 (анализ) для редакторских панелей, layer 4 для Character Debugger |
| Свободный ввод текста | `frontend/text_input.py` (экранный ввод), `frontend/keybindings.py` | Переиспользовать; для длинного авторского текста — вставка из буфера + файловый импорт (по прецеденту `PdfDropImporter`: прием `.txt/.md` перетаскиванием в папку `saves/<campaign>/chronicle_drop/`) |
| Локализация | `frontend/i18n.py` (`L`, `t(key)`, префиксы `ui:`/`act:`/`manifest:`) | Новые ключи `ui:chronicle_*` |
| Эталонные данные | `config/npc/individuals/lusya.json` (Люся — major-tier maid, origin_events с abuse-травмой и секретами), `tavern_keeper_tornin.json`, `config/npc/social/village_relations.json` | Приёмочный сценарий: перенос существующих origin_events Люси в хронику и обратно (§10, T-CCH-01) |

### 6.6. Симуляционный контур (что обязано остаться нетронутым)

- Тик-пайплайн `backend/app/services/tick_orchestrator.py` (фазы 0–10, `backend/app/services/phases/README.md`) — Хроника работает **до** первого тика и **вне** тика; в фазах изменений нет, кроме легального чтения `causal_ledger` отладчиком.
- Каузальное ядро: `SnapshotKernel → EventCompiler → ThickSceneChange → ProjectionEngine` (ADR-O-201, `backend/app/services/event_compiler.py`) — не расширяется хроникой; хроника — поставщик стартовых фактов, не runtime-механизм.
- `EventDTO` (`backend/app/domain/events.py`, детерминированный `UUID(md5(f"{type}:{source}:{tick}:{ordinal}"))`) — сеялка при необходимости создаёт «предысторические» EventDTO только как материал памяти (`EventMemory`), **не** публикуя их в `EventBus` (`backend/app/services/events/event_bus.py`) — публикация сломала бы replay-ординалы.

---

## 7. Архитектурное решение (скелет для детализации)

### 7.1. Компоненты

```
frontend/
  chronicle_editor/           # новое pygame-приложение редактора
    editor_launcher.py
    editor_core.py            # цикл, режимы (7), состояние
    panels/                   # 7 панелей как ui_workbench-окна
  ui_workbench/windows/
    character_debugger_window.py   # FR-9.x (в игре)
backend/app/
  services/chronicle/         # новое домен-сервисное ядро
    biography_decomposer.py   # FR-2.x (LLM-декомпозиция)
    decomposition_normalizer.py
    chronicle_store.py        # канон + черновики (§6.4)
    chronicle_seeder.py       # FR-11.x (seed мира)
    white_spot_registry.py    # FR-3.x, writer-guard
    age_math.py               # birth_epoch ⇄ age ⇄ total_seconds
  api/routes_chronicle.py     # §6.4
  prompts/chronicle_decompose_system.txt
config/npc/chronicles/        # канон хроник (новое)
```

### 7.2. Поток данных (happy path)

Автор пишет фрагмент → `POST /chronicle/{npc}/decompose` → `BiographyDecomposer` (детерминированный препарсинг якорей → LLM JSON Mode → `ChronicleDecompositionNormalizer`) → `BiographyDecomposition` (transient, не сохраняется как истина) → UI «Разбор» → вопросы `ClarificationQuestion` → резолюции автора (в т.ч. `WhiteSpot`) → **«Принять как канон»** → `ChronicleStore` пишет `ChronicleEntry(provenance=AUTHOR_CONFIRMED)` → экспорт-проекции (origin_events-совместимая, secrets, relationships) → при `new_game` `ChronicleSeeder` строит `EventMemory/RelationshipStore/TruthState/BeliefState/AffectiveImprint` до фазы 0 тика.

### 7.3. Место в онтологии L0–L4

Хроника — источник **прологепистического состояния** (до первого тика): она не добавляет уровень онтологии, а поставляет факты в L1 Chronicle (`TraitDriftEvent`-прецеденты), L2 Identity (`CrystallizedBelief`, `NPCIdentityL1`) и память (`EventMemory`) — см. §0 DTO Registry («ENIGMA ONTOLOGY», пятиуровневая архитектура). «Личность = сжатый результат прошлого» уже реализована ядром (`to_identity_weight()`, кристаллизация ×6 травма) — редактор обязан пользоваться этими механизмами, а не дублировать их.

### 7.4. Сеялка: правила трансляции (сводка)

| Хроника | Цель в ядре | Правило |
|---|---|---|
| `EVENT` (исторический возраст A) | `EventMemory(day=-Δ(A), importance, clarity=1.0, decay_rate=0.001, summary=авторская формулировка, tags)` | Δ — возрастные годы в днях; importance из эффекта (по умолчанию 0.6, для травм ≥0.9) |
| `EFFECT` (травма, триггер) | `AffectiveImprint(trigger_tags, decay_rate=0, …)` + `EventMemory` | импринт создаётся только при явном авторском маркере травмы |
| `RELATIONSHIP` (природа, качество) | `RelationshipStore` seed + `village_relations`-проекция | числа вычисляются из структуры (тип связи × знак × интенсивность текста), каждый скаляр помечен `origin_ref` |
| `KNOWLEDGE_LINK` | `EventMemory.known_by/hidden_from`, `Secret.initial_holders`, `EpistemicRecord.first_observed_tick` | `unknown → X` ⇒ отсутствие записей у X (Vacuum) |
| `BELIEF_SEED` (представление) | `BeliefState` (типизированный) + каноническая формулировка в хронике | кристаллизация ×6 не применяется в seed (это runtime-механизм L2.5) |
| `TRAIT_SEED` | `NPCIdentityL1.active_traits` | только черты из белого списка ядра (`resentment`, `dependency` — прецеденты) |

### 7.5. Детерминизм и replay

- Все ID записей — md5-производные (прецедент `EventDTO.create`, BUG-FB-037).
- LLM-вызовы декомпозитора — через `ModelRouter` с `set_replay_context` (кэш `llm_cache.py`); повторный seed при том же каноне обязан давать байт-в-байт то же стартовое состояние (тест в §10).
- Время сеялки — только ось `total_seconds`/`day`, никаких wall-clock (`datetime.now()` запрещён в kernel-слое — DTO Registry §0).

## 8. Запреты (каузальные, в формате DTO Registry)

Каждый запрет обязан получить тест (канон «запрет → тест», хвост DTO Registry).

1. ❌ **LLM-декомпозиция не является каноном.** Запрещено писать `LLM_DRAFT` в канонические хранилища, в seed и в любые проекции на ядро (инвариант INV-LLM-NOT-SSOT). Тест: после `decompose` без `canonize` файлы `config/npc/chronicles/` и seed-состояние неизменны.
2. ❌ **Автоматическая резолюция белых пятен.** Ни один сервис backend не вправе менять `WhiteSpot.resolution_state` вне авторского действия (writer-guard `white_spot_registry.py`). Тест: попытка резолюции из не-UI-модуля → `ArchitecturalViolationError`.
3. ❌ **Причина без происхождения.** Запрещено сеять скаляры `RelationshipStore`/`BeliefState` из хроники без `origin_ref` на `CauseRef`/`entry_id` (антипример «Любовь = 0.8»). Тест: seed без provenance → отказ.
4. ❌ **Смешение двух времён.** Запрещено вычислять «историческое» из «времени знания» и наоборот; `KnowledgeLink.learned_age < event.historical_age` → валидационная ошибка.
5. ❌ **Телепатия в seed.** Запрещено создавать `EventMemory`/`EpistemicRecord` у персонажа, для которого хроника фиксирует `unknown` по данному событию. Тест: T-CCH-06.
6. ❌ **Публикация предысторических событий в EventBus.** Запрещено вызывать `EventBus.publish` для seed-фактов (ломает детерминизм ординалов `event_identity.py`).
7. ❌ **Утечка каузального слоя в игровой HUD.** Данные Character Debugger и редактора не имеют права попадать в `WorldSnapshotDTO`/`player_perception` (Эпистемическая граница; Закон IV UI Doctrine). Тест: grep-страж + контрактный тест DTO (прецедент `INV-RE-CACHE-ALLOWLIST`, ADR-O-415).
8. ❌ **Прямые импорты backend в окнах фронтенда.** Закон 1.1 / `INV-FRONTEND-ISOLATION`; все панели — через `data_source`-каналы.
9. ❌ **Wall-clock / `random.*` в сеялке и декомпозиторе** (вне LLM-канала, где seed детерминирован `KernelRNG`).
10. ❌ **Мутация runtime-состояния из редактора во время игры.** Редактор хроник оперирует каноном и черновиками; `NPCState` (`_ALLOWED_WRITERS`) он не касается. Character Debugger — read-only.

---

## 9. План работ

Этапы нумеруются CCH-0…CCH-6. Правила очереди — §0.2 Roadmap (сверху вниз, инварианты живого IPT-прогона раньше очереди, закрытие через гейт + MUTATIONS). Каждый этап завершается записью ADR (прецедент `docs/audits/ADR-*_IMPACT.md`) и самоочисткой исполнившего ТЗ.

### CCH-0 — Инвентаризация и ADR (оценка 1–2 сессии)
- Зафиксировать ADR-XXX «Character Chronicle»: решить спорные места §12 (хранилище, хоткей, формат `day<0`, судьба `PdfDropImporter`).
- Согласовать схему `ChronicleDocument` (§3) с DTO Registry (регистрация 6 новых DTO: `ChronicleDocument`, `ChronicleEntry`, `WhiteSpot`, `KnowledgeLink`, `BiographyDecomposition`, `ClarificationQuestion`).
- **Зависимости:** нет. **Результат:** ADR + обновлённый DTO Registry + гейт-чеклист.

### CCH-1 — Модель данных и хранилище (2–3 сессии)
- `backend/app/services/chronicle/chronicle_store.py` + валидатор `schema_version=1`; `config/npc/chronicles/` (канон) + `saves/<campaign>/chronicle_drafts/` (черновики); `white_spot_registry.py` с writer-guard; `age_math.py` + `birth_epoch/age_at_game_start` в `NPCProfileL0`.
- Миграция: наоборот-совместимость — существующие `origin_events` читаются как хроника-проекция (read-only), обратная запись не нужна до CCH-5.
- **Зависимости:** CCH-0. **Гейт:** round-trip `config/npc/individuals/lusya.json → chronicle → обратно` без потерь (T-CCH-01).

### CCH-2 — Декомпозитор и режимы «История/Разбор» (3–4 сессии)
- `biography_decomposer.py` (Fast Path якорей + Slow Path LLM через `FACT_EXTRACTION`), `chronicle_decompose_system.txt`, `ChronicleDecompositionNormalizer`; API `routes_chronicle.py` (`decompose`, `clarify`).
- Юзабилити-контракт: обработка фрагмента ≤ фрагмента (асинхронно), вопросы только при неоднозначности, «оставить как белое пятно» доступен всегда.
- **Зависимости:** CCH-1. **Гейт:** сценарий «Люся-введение» (первый абзац видения) декомпозируется в 2 EVENT + 1 RELATIONSHIP + 1 LOCATION + 3 EFFECTS + 1 вопрос (степень родства) — как в эталоне документа.

### CCH-3 — Редактор UI (4–5 сессий)
- `frontend/chronicle_editor/` (автономное приложение + `MenuAction.CHRONICLE_EDITOR`), 5 областей §5.1, режимы §5.2; `MODE_CHRONICLE` в Map Editor; канонизация (FR-10.x) и валидация «Save = Contract».
- **Зависимости:** CCH-2 (API), `ui_workbench` (существует). **Гейт:** полный цикл на эталонной Люсе: написать 4 фрагмента → разрешить 2 вопроса (один — белым пятном) → канонизировать → машинная хроника совпадает с эталоном §4.4.

### CCH-4 — Сеялка и Character Debugger (3–4 сессии)
- `chronicle_seeder.py` по §7.4 (EventMemory/RelationshipStore/TruthState/BeliefState/AffectiveImprint; отрицательные day; расширение allowlist писателей через ADR); интеграция в `new_game` рядом с `npc_loader`.
- `windows/character_debugger_window.py` (layer 4; «СЕЙЧАС» из runtime, «ИСТОЧНИКИ» из хроники, дрейл-даун по `causal_ledger`).
- **Зависимости:** CCH-1, CCH-3. **Гейт:** `goran_vertical_slice_test` (SUPERBOX, 12/12) не деградирует; новая кампания с хроникой Люси показывает: страх к Торнину + avoidance-поведение на звон кружки в первых тиках (T-CCH-07).

### CCH-5 — Экспорт-проекции и двойная запись (2 сессии)
- Экспорт канона → `origin_events`-совместимый JSON, `village_relations`-проекция, `truth_state_*.json`; правило приоритета (хроника есть → сеялка, иначе legacy); решение о судьбе ручных файлов.
- **Зависимости:** CCH-4. **Гейт:** campaign «Open_road» стартует одинаково на legacy-пути и на пути хроники для NPC без хроники (диф-тест состояния).

### CCH-6 — Калибровка порогов и закрытие (1–2 сессии)
- Калибровка порога `needs_confirmation` на корпусе тестовых биографий (3–5 биографий разной сложности, метрика: вопросы только там, где неоднозначность для причинной модели); финализация документа в MUTATIONS; снятие ТЗ с корпуса.
- **Зависимости:** CCH-2…CCH-5. **Гейт:** метрика вопросов ≤ согласованной на корпусе; все тесты §10 зелёные; IPT 49/49.

**Суммарная оценка:** 16–20 сессий. Критический путь: CCH-0 → CCH-1 → CCH-2 → CCH-3 → CCH-4 → CCH-5 → CCH-6. Параллелизуемо: CCH-3 (UI) частично параллелится с CCH-4 (сеялка) после стабилизации API CCH-2 (Anti-Race Protocol §11.1.1 Устава).

---

## 10. Критерии приёмки (испытания)

| ID | Испытание | Проверяет |
|---|---|---|
| T-CCH-01 | Round-trip: `lusya.json::origin_events` → хроника → экспорт → побайтно эквивалентная seed-память (`EventMemory`-кортеж, day<0) | CCH-1, FR-10.3, FR-11.1 |
| T-CCH-02 | Декомпозиция эталонного фрагмента №1 («В 8 лет осталась без родителей…») → ровно ожидаемый набор `DecompositionItem` + вопрос о степени родства | CCH-2, FR-2.x |
| T-CCH-03 | «Стражник» → диалог с 4 опциями; выбор «белое пятно» → `WhiteSpot(OPEN)`, не создан ни один NPC; выбор «создать NPC» → драфт-конфиг | CCH-2/CCH-3, FR-3.x |
| T-CCH-04 | Канонизация без резолюции открытого вопроса — заблокирована с русским `fix_hint` | CCH-3, FR-10.x |
| T-CCH-05 | Детерминизм: два прогона seed на одном каноне → идентичные `saves/…` (сравнение снапшотов `ReplayStore`) | CCH-4, §7.5 |
| T-CCH-06 | `unknown → Марк` по событию «Торнин убил человека» → у `merchant_goran` нет ни `EventMemory`, ни `EpistemicRecord`; у Люси запись с `day`, соответствующим 17 годам | CCH-4, FR-7.x, запрет 5 |
| T-CCH-07 | Вертикальный срез: кампания с хроникой Люси; через N тиков резонанс «звон кружки» → avoidance-поведение (`ResonanceProfile`, `decision_hub._emotion_modifier`) | CCH-4, FR-9.2 |
| T-CCH-08 | Character Debugger: клик «страх Торнина» → цепочка `12 лет → рукоприкладство → эпизодическая память → ожидание повторения → avoidance`; окно не появляется в `WorldSnapshotDTO` | CCH-4, FR-9.x, запрет 7 |
| T-CCH-09 | Replay: прогоны до и после введения хроники для NPC **без** хроники — дрифт состояния = 0 (legacy-путь нетронут) | CCH-5, FR-11.2 |
| T-CCH-10 | Инварианты: IPT 49/49 зелёный; SUPERBOX-контур не затронут; линтеры (`scripts/lint_frontend_isolation.py`, `lint_llm_exile.py`) чистые | все этапы |

---

## 11. Риски и меры

| Риск | Вероятность/влияние | Мера |
|---|---|---|
| LLM-декомпозиция нестабильна на свободном русском тексте (Qwen2.5-7B) | высокая / среднее | Двухконтурность (детерминированный препарсинг якорей); JSON Mode + temperature=0 + KernelRNG-seed; вопросы вместо догадок (§ENIGMA-003: UNKNOWN = None, догадки запрещены); калибровка CCH-6 |
| Двойная запись (хроника vs JSON-конфиги) разъедется | средняя / высокое | Правило приоритета сеялки (FR-11.2) + экспорт-проекции CCH-5 + диф-тест T-CCH-09; в перспективе JSON-конфиги становятся только проекциями |
| VRAM-конфликт LLM (пул на 1 модель, RTX 3070 Ti 8GB) | средняя / среднее | Вызовы декомпозитора идут через `ModelRouter` (семафор `asyncio.Semaphore(1)` уже защищает VRAM); редактор — внеигровой инструмент, конфликт с игровым тиком минимален |
| Склепозность seed-«предыстории» ломает баланс выживания (важности origin уже 0.9+) | низкая / среднее | Важности/сигнатуры травм задаются автором в хронике, но клампятся сеялкой в согласованные диапазоны; калибровка на `calibration/test_presets` |
| Расширение allowlist писателей (`BeliefState`, `NPCIdentityL1`) — архитектурное трение | высокая / низкое | Однократный ADR в CCH-4; сеялка — единственный новый писатель, охраняемый по модулю (прецедент `RelationshipStateStore._ALLOWED_WRITER_MODULES`) |
| Смешение редакторского layer-3/4 контента с игровым восприятием | низкая / высокое | Жёсткий запрет 7 + grep-страж; Character Debugger только внутри Workbench с `workbench_paused=True` |

---

## 12. Открытые вопросы (решает архитектор в CCH-0)

1. **Хоткей Character Debugger**: `K_c` внутри Workbench против отдельного реестрового хоткея (`frontend/keybindings.py`) — конфликтов с занятым F12 не избегать нельзя, выбор за архитектором.
2. **Формат `day` для предыстории**: единый множитель «год = 360 дней» (из `core/constants.py`) против «человеческого года ≈ 365» — влияет на отрицательные day в `EventMemory`; совместимость с существующим −1000.
3. **Судьба `PdfDropImporter`**: подключить как транспорт импорта хроник из файлов (естественная точка применения) или оставить вне скоупа.
4. **Хранение human-формулировок убеждений**: только в хронике (канон автора) с типизированной проекцией в ядро, либо новое поле `label` в `BeliefFragment` (расширение frozen-DTO требует ADR).
5. **`unknown_person` (фоновые личности)**: нужны ли минимальные профи L0 для массовки хроники («жена стражника») или достаточно `WhiteSpot`-подобных структур без NPC-конфига.
6. **Нужно ли авто-дополнение**: «ENIGMA предлагает продолжение хроники» (LLM как соавтор) — видение документа этого не требует; по умолчанию вне скоупа (П1: LLM не автор канона).

---

## Приложение A. Трассировка: видение документа → требования ТЗ

| Пункт исходного видения | Требования |
|---|---|
| «Не генератор биографий; режиссёрский редактор причинной биографии» | §0, П1, FR-1.x |
| «ENIGMA превращает человеческое описание в машинно-исполняемую историю» | §7.2, FR-4.x, CCH-2 |
| «Разобрать текст и спросить только там, где фраза неоднозначна» | FR-2.3, CCH-6 |
| «Хорошо ложится на Understanding Engine» | §6.1 (трек AG1, `intent_compressor`, INV-LLM-NOT-SSOT) |
| «Временная причинная лента как главная сущность UI» | FR-1.3, §5.1 |
| «UI превращает повествование в форму сам» | П2, FR-2.x |
| «Белые пятна: 4 опции, критичность варианта “оставить”» | FR-3.1–3.4, запрет 2 |
| «Машинная хроника — исходник для causal engine» | FR-4.1–4.2, §7.4 |
| «Режим “Причины”: 6 типов оснований; Love ≠ 0.8, мы знаем откуда» | FR-5.1–5.4, запрет 3 |
| «Личность на начало игры: представления + ПРОИСХОЖДЕНИЕ (событие 17/23/31 → belief)» | FR-6.1–6.4, §7.4 |
| «Character Debugger: F12 → Character, СЕЙЧАС, ИСТОЧНИКИ, дрейл-даун страха Торнина» | FR-9.1–9.4, T-CCH-08 |
| «Хроника имеет два времени: историческое и время знания; история мира ≠ история знаний» | FR-7.1–7.3, запрет 4, П4 |
| «UI из 5 основных областей» | §5.1 |
| «7 режимов: История/Разбор/Причины/Связи/Знания/Время/Белые пятна» | §5.2 |
| «LLM не является причинным авторитетом; “Принять как канон”» | П1, FR-10.x, запрет 1 |
| «Характер = сжатый результат прошлого (не character = {...})» | §7.3 (L0–L4 онтология, `to_identity_weight`, кристаллизация) |
| «Центральный инструмент разработки; многолетняя социальная ткань перед первым тиком» | П5, §1.3, CCH-4/CCH-5 |
