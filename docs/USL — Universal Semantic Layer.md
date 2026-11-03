# USL — Universal Semantic Layer (Единый семантический слой ENIGMA)

> **Статус: PROPOSED** — архитектурное направление, подготовленное роевой архитектурной сессией (read-only исследование корпуса V.0.5.4.5.2). До вердикта Мастера документ **не** является мандатом, не создаёт production-обязанностей и не меняет статусы задач дорожной карты. Реализация любого пункта — только после отдельного архитектурного утверждения (Этап USL-0, §9).
>
> **Тип сущности:** поперечный архитектурный фундамент (cross-cutting foundation), а не игровая функция. С USL обязаны согласовываться биографический контур (CCH, §13–§14 roadmap) и интерактивный языковой контур (AG1/DLG, §3 roadmap).
>
> **Основание:** роевой спринт «Единый семантический фундамент ENIGMA». Все ссылки на код верифицированы чтением реального корпуса V.0.5.4.5.2; никакой вывод не сделан по названиям файлов — каждый пункт раздела 2 подтверждён телом функции или цепочкой вызовов (метод: файл:строка).
>
> **Связь с дорожной картой:** строка в §1.1 «Карта документов»; зависимости отмечены в §0.2 (Ступень 0, CCH-02), §3 (AG1/DLG), §12 (NL-2), §13 (CCH), §14 (CCH-02) — без изменения статусов существующих задач. Отражение USL как трека и карта зависимостей — §11.
>
> **Ревизия R1 (2026-11-02):** §9 перестроен под обязательную последовательность движения «INTEGRATION → NPC BIOGRAPHIES → REAL DIALOGUES → SEMANTIC DEVELOPMENT → SCALE» (интеграция → биографии всех NPC → реальные диалоги → развитие → масштабирование); задание архитектору (§10) расширено под ту же последовательность; добавлены §11 «Трек USL в дорожной карте» и сквозная система проверок (§9.7). Этапы USL-0…USL-5 перенумерованы — карту соответствия старой и новой нумерации см. в шапке §9. Подтверждённые результаты первоначального исследования (§2 и Приложение §12) сохранены без изменений.
> **Ревизия R2 (S380, 2026-11-02):** USL-0 завершён вердиктом Мастера (6 вопросов Q1-Q6 + 3 поправки). USL-1.1/1.2/1.3 (additive) + USL-1.4 (первая production-интеграция — free ASSERT path) завершены. См. §13 «Статус реализации». 2 коммита: `fe50b3be` (additive) + `8caefebc` (production). 82 теста USL + 16 регрессий claim-контура. ADR-O-437 ACTIVE. USL-1.5 (CanonicalRegistry bridge) / USL-1.6 (Regression + Activation) — pending, следующая сессия.

---

## 0. Резюме

**Проблема одной фразой.** ENIGMA уже умеет разбирать человеческое время, события, отношения и причины из авторских биографий — и при этом **не умеет** распознавать те же конструкции в речи игрока: фраза «Год прошёл с тех пор, как я пять лет работал на тебя» разбирается только как `ASSERT{claim: "…я пять лет работал на тебя…"}` — длительность, завершённость, интервал и адресат остаются несжимаемым текстом внутри строки (`llm_compressor_client.py:357`, few-shot), потому что ни Fast Path, ни промпт, ни `IntentSemanticField` не имеют временных полей. Одновременно биографический контур построил богатую временную онтологию (`AgeAnchor` с шестью типизированными видами якорей, `historical_age`/`learned_age`, инвариант «learned ≥ historical»), которая недоступна остальным контурам.

**Что доказано кодом (раздел 2):**
- биографический контур — сквозная работающая цепочка: `draft → decompose (LLM+GBNF) → нормализация fail-loud → вопросы автору → «Принять как канон» → CCH-7-гейт → сеялка → EventMemory/убеждения/отношения/импринты NPC` — с точными точками вызова;
- игровой контур — работающая цепочка `compress → resolve_player_intent → IntentReadiness → гейты → события шины` — с той же глубиной верификации;
- **асимметрия фундаментальна**: у биографического контура есть типизированное время, типизированные сущности (`EntityRef`), типизированные причины (`CauseRef`), канал знания (`KnowledgeChannel`); у игрового контура из всего этого есть только бинарная `Proposition` (5 предикатов), per-act `negated/modality/quoted` (извлекаются, но enforcement есть только у `negated`), и **ни одного** временного поля;
- ряд механизмов-«мостов» написан, но не подключён: `act_consumer.consume_npc_acts` (0 production-вызовов), `WhiteSpotRegistry.resolve` (writer-guard спит, резолюция дублирована inline в роуте), `origin_projection.origin_events_to_chronicle` (мертвый ход), `temporal_marker_on_action` (существует только в docstring `intent_profile.py:136`).

**Что предлагается (разделы 3–8):** общий контракт смысловой единицы `USLUnit` + два адаптера (`BiographyAdapter`, `InteractiveLanguageAdapter`) + строгая граница трёх операций: **понимание → принятие истины → исполнение**. USL — не хранилище, не шина, не новая память, не вторая хроника и не LLM-сервис. Это **словарь типов и правила проекции**, который делает конструкцию времени/события/отношения/причины переносимой между контурами при сохранении источника и статуса знания. **Порядок движения (§9, ревизия R1 — обязательная логика):** сначала интеграция двух контуров на общем языке, затем проверка на реальном контенте — сначала на всех авторских биографиях NPC, затем на реальных диалогах, и только после этого развитие возможностей по обнаруженным ограничениям.

**Железные инварианты USL (полный текст — §3.4):**
- **USL-1 (одно представление):** одна и та же временная/событийная/причинная конструкция имеет одно представление независимо от источника текста. Различаются адаптеры и статусы, не онтология.
- **USL-2 (источник ≠ истина):** каждая смысловая единица несёт источник и статус достоверности; распознанное утверждение игрока не становится фактом мира (прецеденты: INV-LLM-NOT-SSOT, S188 «ClaimEvent никогда не World Truth»).
- **USL-3 (USL не пишет мир):** USL не получает права записи ни в один store; всё исполнение остаётся в существующих writer-каналах (canonize, seeder, DeltaGate, ClaimEventSubscriber, BeliefRevisionEngine).
- **USL-4 (обратная совместимость):** существующие контракты (`IntentSemanticField`, `ChronicleEntry`, `BiographyDecomposition`) остаются поверхностным API; `USLUnit` — глубинная проекция, а не замена.

**Сквозной пример (используется по всему документу):**

| Источник | Фраза | Что должна увидеть система |
|---|---|---|
| Биография Орма | «Он пять лет работал на Орма» | событие-работа + длительность 5 лет + адресат Орм + источник: авторский канон |
| Игровой ввод | «Я пять лет работал на тебя» | то же событие + длительность 5 лет + адресат = собеседник + источник: утверждение игрока (не канон) |
| Воспоминание NPC | «Он работал на меня пять лет» | то же событие + перспектива наблюдателя + источник: память NPC |
| Хроника мира | «Год прошёл после окончания его службы» | конечная точка события + интервал 1 год после завершения + источник: канон |

Сегодня первые три фразы дают **три несовместимых** представления, и только первая из них разбирается полностью (§6.5 — совместимый разбор всех четырёх).

**Разграничение терминов (обязательное, правило «один факт — одно место»):**
- **USL ≠ «семантический слой» трека MEM.** В §16.0 roadmap «семантический слой спит (писателей 0)» — это про MemoryCrystal/E1.2 (`MemoryCrystal` — семантическое обобщение **памяти**). USL — про **понимание языка** до того, как что-либо попало в память. Граница: USL производит осмысленную единицу → память решает, что с ней делать.
- **USL ≠ Biographical Record (NL-2, §12.1.7).** BR — производная проекция записей **после** понимания; USL — сам этап понимания. USL не становится «BiographicalStore», запрещённым §16.9.
- **USL ≠ новый компрессор.** `IntentCompressor` и `BiographyDecomposer` не переписываются (запреты задания); они становятся движками двух адаптеров (§5).

---

## 1. Проблема

### 1.1. Два контура выросли изолированно

ENIGMA содержит два полноценно развившихся «читателя человеческого языка»:

1. **Биографический контур** (трек CCH, Слой 0): авторский текст биографии → `BiographyDecomposer` → `ChronicleDecompositionNormalizer` → хроника → сеялка → стартовое состояние NPC. Он вырос из задачи «человек описывает NPC естественным языком» и получил собственную онтологию: типы записей `EntryKind`, статусы канона `EntryProvenance`, возрастные якоря `AgeAnchor`, ссылки на сущности `EntityRef`, причинные основания `CauseRef`, канал знания `KnowledgeChannel` (`app/domain/chronicle.py:47-77`).
2. **Игровой языковой контур** (трек AG1/DLG): свободный ввод игрока → `IntentCompressor` (Fast Path + LLM Slow Path) → `IntentSemanticField` → `resolve_player_intent` → исполнение/эпистемика. Его онтология росла от боевых/движковых задач: `ActionType`, `TargetZone`, `SpeechAct`, `SocialIntent`, бинарная `Proposition` (`app/domain/intent_profile.py`, `app/domain/epistemology.py`).

Оба контура обрабатывают человеческий язык и потому **неизбежно** встречают одни и те же смысловые категории: кто действовал, что произошло, когда, как долго, из-за чего, кто что сказал и насколько это достоверно. Но категории эти были определены дважды — по-разному и с разной глубиной.

### 1.2. Измеримая асимметрия

Сравнение по фактическому коду (полная карта — §2, сводная таблица — §2.5):

| Категория | Биографический контур | Игровой контур | Вердикт |
|---|---|---|---|
| Сущности | `EntityRef` с 4 видами (`RESOLVED/NEW_NPC/WHITE_SPOT/UNKNOWN_PERSON`), alias-registry падежных форм (`decomposition_normalizer.py:57-93`) | строка `target/actor/addressee` + резолв по сцене (`phase_1_input.py:176-239`); у хроники и у ввода — разные реестры имён (`registry_builder` vs `_npc_display_names`) | несовместимо |
| Время | `AgeAnchor(kind ∈ 6 видов, source_span)`, `historical_age/historical_year`, `learned_age/learned_year`, инвариант двух времён (`domain/chronicle.py:358-380`) | **нет ни одного поля**; время — только текст внутри `claim/topic` (`llm_compressor_client.py:357`) | критическая асимметрия |
| События | `EntryKind` (10 типов), `payload` со схемой по kind | `semantic_acts` (13 типов) + `ActionType` (11); `Proposition` — 5 предикатов | пересекающиеся, но разные реестры |
| Причинность | `CauseRef` (6 типов оснований), `NpcCausalBelief`, `CauseCandidate` (`domain/chronicle.py:98-106, 262-320`) | нет каузальных полей вовсе; косвенно — DM-вектор ACCUSE/THREATEN/HELP (`claim_event_subscriber.py:111-120`) | несовместимо |
| Отношения | `RELATIONSHIP`-записи с origin_ref, seed в `relationship_cache` | `Proposition(HELPED/ATTACKED)`, дельты RelationshipStore через наблюдение | частично совместимо |
| Модальность | неявно: `DESIRE_SEED`, «мечта/план — ещё не событие» (`chronicle.py:43-44`) | per-act `negated/modality/quoted` (`intent_compressor.py:228-232, 254-266`) — enforcement есть только у `negated` (`phase_1_input.py:165-172`) | игровой контур **впереди** — обратная асимметрия |
| Эпистемика | `EntryProvenance` (3 статуса), `KnowledgeChannel` (5 каналов), `certainty` | `ClaimEvent`/`EpistemicRecord` с provenance (S188); но для свободных ASSERT — разрыв (§2.2.4) | два сильных, несводимых механизма |
| Контекст | roster, фрагмент, ordinal, `author_text` append-only | `dialogue_session`, `references`, `conversation_continuation`, `dialogue_thread` | разные оси, дополняют друг друга |

Вывод: асимметрия не «биографический контур лучше». Она **разнонаправленная**: время и сущности сильнее у хроники, модальность и гейты исполнения сильнее у ввода. Это худший вид асимметрии — копировать нечего, обе онтологии частично верны и частично уникальны.

### 1.3. Почему это фундамент, а не фича (§ENIGMA-002, Правило Двух Доменов)

`АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md` §ENIGMA-002: «Новый фундаментальный примитив не может быть введён, пока не существует доказательств, что минимум два независимых домена страдают от одной и той же онтологической проблемы». Оба домена доказаны кодом:

- **Домен 1 (хроника):** LLM путает «N лет» (возраст) с «N лет назад» (точка прошлого) — для этого написана целая диагностическая функция `validate_age_anchor_coverage` с аномалией `years_ago_equals_current_age` (`biography_decomposer.py:66-156`); детектор тем же недугом болеет и в S368-fallback (`routes_chronicle.py:396-404`).
- **Домен 2 (ввод):** та же категория («пять лет», «год прошёл») не распознаётся вообще — ни одним слоем; в `comprehension_facts` зарезервирован ключ `temporal_marker_on_action` (`intent_profile.py:136`), но его не пишет и не читает ни один модуль (проверено grep по backend: единственные вхождения — docstring и тестовый корпус `ue0_baseline_corpus.py:35`).

Два независимых домена, одна онтологическая проблема — отсутствие общего представления человеческого времени (и, шире, смысла). Требование Устава выполнено.

### 1.4. Цена сохранения статус-кво

1. **Каждый новый языковой контур будет изобретать время заново.** Готовятся: диалоговое состояние (DLG-2/3), автобиографии NPC (CCH-02), перекрёстные расспросы (BC-5), NPC-NPC-коммуникация (ARC-NPC). Каждому нужен разбор «когда/сколько лет/после чего» — и каждый получит его в своём словаре.
2. **Утверждения игрока о прошлом не могут влиять на мир, память или диалог безопасно.** Сегодня свободный `ASSERT` доходит до шины без семантики; подключить его «в лоб» без общей модели означало бы скаляризовать время в строку-claim и потерять статус источника — ровно те два дефекта, против которых стоят INV-LLM-NOT-SSOT и S188.
3. **Несовместимость резервуаров имён.** `registry_builder.alias_to_npc` (name_forms: «орм/орма/орму») используется только нормализатором хроники; `_resolve_npc_by_name` ввода — свой стем-резолв (`intent_compressor.py:432-444`). Игрок, говорящий «Орму», и автор, пишущий «Орму», получают разные механизмы резолва одной сущности.
4. **Тестовые критерии двух контуров несравнимы.** Хроника измеряет понимание покрытием записей (`understanding_report.py`, пороги FULL_T/PART_T), ввод — вообще не измеряет время. Общую шкалу «система поняла/не поняла» построить нельзя.

### 1.5. Формулировка проблемы (для Устава)

Система обрабатывает человеческий язык двумя несовместимыми семантическими онтологиями, в результате чего: (а) смысловые конструкции, разобранные в одном контуре, непереносимы в другой; (б) утверждения игрока о прошлом не имеют безопасного пути к статусу «утверждение с источником» и останавливаются на границе понимания; (в) каждый новый языковой контур воспроизводит асимметрию. Требуется единый семантический фундамент — **представление смысла без права записи в мир** — с двумя адаптерами и строгим разделением понимания, принятия истины и исполнения.

---

## 2. Текущее состояние

Карта подтверждена чтением кода V.0.5.4.5.2 (включая трассировку вызовов; ни один вывод не сделан по названию файла). Обозначения: ✅ работает в production-цепочке; 🟡 написано, но не подключено / частично; 🔴 отсутствует; ⚠️ дублирование/несовместимость.

### 2.1. Биографический контур: фактическая цепочка

```
авторский текст (docs/Прошлое персонажей черновик/Все.md; UI-вставка или scripts/redecompose_all_npc.py)
 → PUT /api/chronicle/{campaign}/{npc}/draft            [routes_chronicle.py:511-519; saves/<c>/chronicle_drafts/]
 → POST .../decompose                                    [routes_chronicle.py:240-251 → BiographyDecomposer.decompose]
      детерминированный препарсинг: extract_age_anchors_typed [age_anchor.py:87-118]
      LLM: router.request("fact_extraction", temperature=0, GBNF-грамматика) [biography_decomposer.py:311-323]
 → ChronicleDecompositionNormalizer.normalize            [decomposition_normalizer.py:260-427; fail-loud ×6]
      мембраны: vague-relation, self-ref, roster-mismatch → ClarificationQuestion
 → DecompositionItem → ChronicleEntry(LLM_DRAFT)         [routes_chronicle.py:342-455; ordinal=F*100+i; make_entry_id=md5]
      derived time: YEARS_AGO → game_start_age − years_ago [routes_chronicle.py:361-364]
 → POST .../resolve (вопросы → EntityRef/WhiteSpot)      [routes_chronicle.py:662-808]
 → POST .../confirm-author-entries (LLM_DRAFT→AUTHOR_CONFIRMED) [routes_chronicle.py:522-563]
 → POST .../canonize + CCH-7 ConsistencyService-гейт     [routes_chronicle.py:615-651, 569-606]
 → канон: config/npc/chronicles/<npc_id>.json            [chronicle_store.py:411-458; атомарная запись]
 → new-game гейт в npc_loader                            [npc_loader.py:963-997]
 → chronicle_seeder.build_seed_*                         [chronicle_seeder.py]
      EVENT → EventMemory(day<0) → NPCState.narrative_cache
      RELATIONSHIP → relationship_cache (trust±, chronicle_origin) [npc_loader.py:673-700]
      BELIEF_SEED → psyche["beliefs"] → BeliefState      [seeder:361; npc_loader.py:819-832]
      EFFECT-травма → affective_imprints (decay_rate=0)
 → тик-контур: phases/memory.py, npc_tick_pipeline.py:484 (BeliefModifierResolver), dialogue_executor.py:286
```

**Что подтверждено как работающее (✅):**

| Механизм | Контракт/факты | Ссылка |
|---|---|---|
| LLM-декомпозиция с детерминизмом | `temperature=0.0`, `max_tokens=2048`, GBNF `config/chronicle_decompose.gbnf` через `/completion`, один retry (FR-2.2), `DecomposeResult.failure` без молчаливых фолбэков | `biography_decomposer.py:276-354` |
| Типизированные возрастные якоря | `AgeAnchorKind ∈ {CURRENT_AGE, AT_AGE, SINCE_AGE, DURATION, YEARS_AGO, AMBIGUOUS}` + `source_span`; упорядоченные regex-паттерны, «каждое число потребляется один раз» | `age_anchor.py:22-118` |
| Нормализатор fail-loud | неизвестные ключи/пустой items/kind вне реестра/confidence вне [0,1] → `DecompositionError`; мусорная опция вопроса отбрасывается поимённо; пустой items легален (COV-12) | `decomposition_normalizer.py:260-333, 446-459` |
| Мембраны неточной сущности | vague-relation маркеры → conf≤0.4 + вопрос; self-ref через alias-registry; roster-mismatch → вопрос; faction-реестр | `decomposition_normalizer.py:40-49, 378-416` |
| Два времени + инвариант | `KnowledgeLink.validate_against`: `learned_age < historical_age → ValueError`; «вычислять одно из другого запрещено» | `domain/chronicle.py:358-380` |
| INV-LLM-NOT-SSOT | `ChronicleEntry.__post_init__`: LLM_DRAFT обязан нести confidence; AUTHOR_* не хранит confidence; `validate_document` запрещает LLM_DRAFT в каноне | `domain/chronicle.py:348-355`; `chronicle_store.py:369-370` |
| Причинные 4 слоя (S366) | СЛОЙ 1 `ChronicleEntry.causes`; СЛОЙ 2 `NpcCausalBelief` (GROUNDING: GROUNDED/MISTAKEN/UNVERIFIED); СЛОЙ 3 `CauseCandidate` (TEMPORAL_ORDER/TARGET_HINT_MATCH; «хронология ≠ причина»); СЛОЙ 4 — действия автора через endpoints | `domain/chronicle.py:223-325`; `causal_linker.py` |
| Сеялка стартового состояния | `build_seed_memories/knowledge/relationships/imprints/beliefs`; `day=(age−game_start_age)×365`, `day>0 → SeederError` («память о будущем»); `SENTINEL_DAY=-1000` при неизвестном возрасте | `chronicle_seeder.py:125-142, 361` |
| Белые пятна | `ClarificationOption` — ровно 4 опции, LEAVE_WHITE_SPOT обязателен (инвариант `__post_init__`); пятна не становятся тик-агентами | `domain/chronicle.py:80-95, 203-205` |
| Экспорт/диагностика | belief-export (md/json для автора), seed-report, understanding-report (FULL_T=0.35/PART_T=0.18), projections (origin_events/village_relations/truth_state) | `belief_export.py:28-86`; `understanding_report.py` |

**Написано, но не подключено / дублируется (🟡/⚠️):**

| Находка | Доказательство | Значение |
|---|---|---|
| `WhiteSpotRegistry.resolve` — спящий writer-guard | `_ALLOWED_WRITER_MODULES = {сам модуль}` (`white_spot_registry.py:41-45`); production-резолюция дублирована inline в `/resolve` (`routes_chronicle.py:662-808`); guard вызывается только тестами | архитектурный запрет «единственный канал» де-факто не соблюдается; ⚠️ дублирование |
| `origin_projection.origin_events_to_chronicle` | 0 production-вызовов (только тесты); обратное направление (`chronicle_to_origin_events`) живо через CCH-5 | миграция legacy хода полутонная |
| `age_math.birth_epoch_from_age` / `age_at` | 0 callers; сеялка использует трюк `historical_event_seconds(age, 0)` (`chronicle_seeder.py:125-142`) | мёртвый API, дубль формулы |
| `historical_year`/`learned_year` (ось года мира) | round-trip в store, 0 производственных потребителей | мировая ось года не связана с хроникой |
| `build_full_seed` (агрегатор) | вызывается только seed-report'ом и тестами; production применяет отдельные `build_seed_*` из `npc_loader` | риск расхождения «отчёт ≠ факт» |
| Данные не заполняют контур | в 6 канонах: BELIEF_SEED=0, KNOWLEDGE_LINK=0, `game_start_age` только у maid_lusya=14; `age_at_game_start` в профилях только у orm=146 | посев знаний/убеждений фактически пуст; возможное несоответствие «канон vs профиль» не персистится (fallback транзитный, `routes_chronicle.py:332-341`) |
| `DURATION` не выводится в historical_age | S368-фоллбэк обрабатывает только единственный EVENT с одним якорем; «работал пять лет» → исторический возраст события не вычисляется (`routes_chronicle.py:374-386`) | **биографический контур сам не умеет резолвить длительность в координату** — важно для §6 |

### 2.2. Игровой языковой контур: фактическая цепочка

```
ввод игрока
 → GameLoop._intent_compressor = IntentCompressor(LlamaCppCompressorClient())   [game_loop.py:180-184]
 → TurnPipeline._execute_dm_and_intent_resolution                               [turn_pipeline.py:311-527]
      run_dm_phase → compress(raw, scene_context, dialogue_session)              [turn_pipeline.py:363-367]
        Fast Path: леммы pymorphy3 (_ACTION_LEMMAS), question-детектор, SubjectRef, intensity
        Slow Path: LLM (JSON mode, temp=0, KernelRNG-seed=salt(prompt))          [llm_compressor_client.py:42-143]
        единая граница ACT RECOVERY (_recover_acts) + comprehension_facts        [intent_compressor.py:474-534]
      SOCIAL_ACTION при ATTACK/THREATEN/DIALOGUE/STEAL/GIVE                      [turn_pipeline.py:369-403]
      resolve_player_intent (резолв target/actor; БЕЗ LLM — ADR-031)             [phase_1_input.py:276-388]
      compute_intent_readiness: FAILED/REFERENCE_AMBIGUOUS/SEMANTIC_AMBIGUOUS/PARTIAL/RESOLVED
                                                                               [phase_1_input.py:125-173]
      WV-2/3 физический гейт (tool-check, дистанция) → action_rejected           [turn_pipeline.py:415-463]
      MOVE → MacroMovementGoal → Phase 5 → MovementEngine                        [turn_pipeline.py:465-485; tick_orchestrator.py:2437-2440]
      ATTACK → (публикация подавлена, владелец INPUT_MERGE) → PLAYER_ATTACKED → CombatSubscriber [tick_orchestrator.py:1694-1735]
      не-RESOLVED → деградация до PLAYER_SPOKE («исполнение закрыто, наблюдение живо») [phase_1_input.py:613-630]
 → PLAYER_SPOKE подписчики                                                       [game_loop.py:554-627]
      PlayerSpeechActSubscriber: ТОЛЬКО SELF_INTRODUCTION → claim + player.name=X [player_speech_act_subscriber.py:42-119]
      ClaimEventSubscriber.on_player_spoke: proposition ТОЛЬКО из DM-вектора ACCUSE/THREATEN/HELP
                                                      свободный dialogue без вектора = no-op [claim_event_subscriber.py:89-133]
      on_claim_event: guards → ClaimEvent → BeliefRevisionEngine.revise → EpistemicStore.upsert (S188: ни одной записи в TruthState)
                                                                               [claim_event_subscriber.py:135-268]
      DialogueMemorySubscriber → L2 narrative_cache
 → NPC-тик: TickOrchestrator фазы 0-10 → world consequences (StateDeltas, SceneChange, commit)
```

**Что подтверждено как работающее (✅):**

| Механизм | Контракт/факты | Ссылка |
|---|---|---|
| Двухконтурное сжатие | `compress()`: FAST-ONLY / FAST-INCOMPLETE (+LLM enrich, перезапись запрещена) / SLOW-ONLY; единая граница `_recover_acts` для всех путей | `intent_compressor.py:474-534, 697-801` |
| Машинные факты полноты | `comprehension_facts = {has_acts, action_class, llm_status: OK/UNAVAILABLE/FAST_ONLY/SLOW_ONLY, ambiguity_flag, act_completeness}` — «НЕ самооценка LLM» (U-9) | `intent_compressor.py:527-533` |
| per-act контракт | `semantic_acts[{type, params, negated, modality, quoted, quoted_speaker_hint}]`; белый фильтр `_validate_acts` (мусор = ключ отброшен = честное «не знаю») | `intent_compressor.py:213-268` |
| Гейт готовности | 5 значений `IntentReadiness`; fail-closed: world-changing без target → PARTIAL; неразобранная негация (частица в raw ∧ negated=None) → PARTIAL для world-changing и ORDER; готовность вычисляется ПОСЛЕ резолва ссылок | `phase_1_input.py:125-173`; `intent_profile.py:46-60` |
| Разделение понимание/исполнение | не-RESOLVED → исполнение закрыто, `PLAYER_SPOKE` живёт (наблюдение); UE-GATE-KERNEL не диспетчеризует intervention; UE-GATE-RULES подавляет Rules/экономику | `phase_1_input.py:613-630`; `tick_orchestrator.py:1402-1471`; `turn_pipeline.py:169-194` |
| Claim ≠ Belief ≠ Truth (S188) | ClaimEvent → per-listener `EpistemicRecord` (confidence = reliability источника); ни одной записи в TruthState; proposition-guard против галлюцинаций LLM | `claim_event_subscriber.py:135-268`; `domain/epistemology.py:8-9` |
| Резолв сущностей без LLM | `resolve_target_with_candidates`: full/partial-матч по именам сцены; >1 → неоднозначность (молчаливый автопик запрещён); «Python владеет идентификацией сущностей» | `phase_1_input.py:176-239` |
| Детерминизм comprehension | `temperature=0`, `seed=KernelRNG(salt=prompt)`, отключён thinking-блок; DET-TRACE-наблюдаемость | `llm_compressor_client.py:52-110` |
| Модульная семантика (зачаток) | `semantic_library/dialogue_provenance*.md` + `semantic_router.select_modules` — модульные блоки промпта; env-gated (`ENIGMA_SEM_LIB`), OFF по умолчанию | `semantic_router.py`; `llm_compressor_client.py:267-292` |

**Разрывы (🔴/🟡):**

| Находка | Доказательство | Значение |
|---|---|---|
| Свободный ASSERT не порождает ClaimEvent | `on_player_spoke`: без DM-вектора — no-op («Stage-1.5 не „понимает" речь»); `ASSERT` обрабатывается только DM-канонизацией («утверждение о себе/мире» без содержания) | центральный разрыв для интеграции (Этап USL-1 §9): утверждение игрока не имеет пути к статусу «утверждение с источником» |
| `act_consumer.consume_npc_acts` — мёртвый код | 0 production-вызовов (только `test_act_consumer.py`); внутри — готовые cognition-line FRESH/CONFLICTING/PROVENANCE_QUERY/DOUBT_REGISTERED | готовый потребитель актов, не подключён |
| `quoted`/`modality` извлекаются, но не enforced | docstring обещает «quoted=True запрещает материализацию» (`intent_profile.py:53, 131`); в runtime читается только `negated` (`phase_1_input.py:165-172`) | гейтируемая долга — прецедент Блока 3 (негация) показывает, как закрыть |
| Временная семантика = 0 | Fast-лексиконы без временных токенов; промпт без временных полей (время — только текст в `claim/topic`); в `IntentSemanticField`/`IntentParametersDTO` нет временных атрибутов; `temporal_marker_on_action` не пишется и не читается | полная асимметрия с §2.1; главный материал для USL |
| `ASK_PROVENANCE`/`CONFIRMATION_SEEKING` без консьюмера | распознаются промптом и recovery, consumer отсутствует | канал «откуда ты знаешь?» готов на 2/3 |

### 2.3. Механизмы памяти, убеждений и эпистемики, готовые к переиспользованию

Карта (полная — в отчёте исследования; здесь — только контракты, релевантные USL):

| Контейнер | Назначение | Writer-канал (единственный легальный) | Связь с USL |
|---|---|---|---|
| `EventMemory` (frozen; `npc_state.py:214+`) | эпизодическое воспоминание NPC: `day, importance, clarity, confidence, tags, is_secret/known_by/hidden_from, is_compressed` | `MemoryManager.apply` (Закон 4.1.2) | потребитель семантики: события с временем/важностью |
| `WorkingMemory` (deque 20) | RAM-окно per-NPC, decay по game_days | `memory_manager.apply` | — |
| `BeliefState` / `BeliefFragment` | убеждения NPC с цензусом писателей (`_UPDATE_ALLOWED_WRITERS` + `ArchitecturalViolationError`) | belief_transition_engine, CoherenceBeliefAggregator | принимает результат эпистемической резолюции |
| `EpistemicStore` / `EpistemicRecord` | per-agent веры с provenance (`source_id, source_claim_id, тики`) | `BeliefRevisionEngine.revise` через ClaimEventSubscriber | готовый приёмник утверждений с источником |
| `CrystallizedBeliefStore` (L2.5) | кристаллизация (травма ×6) | отдельный ADR-O-305 (защита DOUBLE TRUTH) | — |
| `ClaimEvent` | событие передачи информации (speaker/listener/proposition/tick) | ClaimEventSubscriber (мембрана can_observe) | **натуральный транспорт для USLEpistemics** |
| `TruthState` (Secret/TruthRelation: CAUSES/CONTRADICTS/DEPENDS_ON/REVEALS/CONCEALS/ENABLES/EXPLAINS) | мировая истина, «доступна ТОЛЬКО EvaluationEngine» | нет writer'ов runtime (статичный канон-JSON) | эталонный адресат проверки, не запись |
| `KnowledgeChannel` (WITNESSED/TOLD/OVERHEARD/DEDUCED/UNKNOWN) | канал знания — **только в хронике** (`chronicle.py:70-77`) | хроника | должен быть поднят до общего контракта (§7) |
| Conclusion Layer (BC-1, dormant `BC1_ENABLED`) | выводы из опыта: закрытый predicate-реестр, `source ∈ {direct_experience, testimony(BC-5, не реализован)}` | `ConclusionGate` → `ConclusionStore.apply` | будущий приёмник выводов; гейт уже фильтрует testimony |
| `LayeredMemory` (4 scope-слоя) | world_canon/campaign/playthrough/npc-журнал | свои write-методы | контекст-семантика, не трогаем |

**Ключевой факт для USL:** runtime-память не хранит **канал получения знания** (только clarity/confidence и точку времени); полный канал живёт только в хронике. Это второй «двухдоменный» аргумент после времени: одна и та же категория («откуда известно») реализована в одном контуре и отсутствует во втором.

### 2.4. Точки фактического взаимодействия контуров (что уже связывает)

1. **Прецедент схемы:** трек CCH намеренно скопировал двухконтурность компрессора — «двухконтурная схема по прецеденту intent-компрессора» (roadmap §0.2, CCH-2). То есть кросс-контурное заимствование архитектурных решений уже легитимная практика.
2. **Общая LLM-инфраструктура:** `ModelRouter` + capability `FACT_EXTRACTION` (хроника) и прямой `LlamaCppCompressorClient` (ввод); `KernelRNG(salt=prompt)` — одинаковый детерминизм в обоих (`biography_decomposer.py:10-14`; `llm_compressor_client.py:52-61`).
3. **Общие доменные типы:** `Proposition` и `SpeechAct` из `epistemology.py` используются обоими контурами (хроника — косвенно через `IntentSemanticField`; ввод — напрямую). Это готовое ядро общего словаря.
4. **Player vs NPC симметрия (DLG-L1):** «Любая реплика — игрока, NPC, аватара — проходит один конвейер интерпретации; классы спикеров различаются только provenance-метаданными, не глубиной разбора» (roadmap §3.6:707) — **это и есть закон USL-1, сформулированный для одного измерения**. USL обобщает его на все источники (включая автора).
5. **Единственная точка встречи сегодня:** `SubjectKind.CANON_TOPIC` — предмет вопроса игрока резолвится по канону секретов TruthState (`intent_compressor.py:447-465`) — первый (и единственный) мост «ввод → канон».

### 2.5. Сводка по разделу 2 (обязательные строки отчёта)

**Работает (можно переиспользовать без изменения):** полный авторский конвейер хроники до канона и сеялки; двухконтурное сжатие ввода с единой границей recovery; гейты готовности и физика; ClaimEvent→EpistemicStore как эпистемический транспорт; TruthState/Secret; возрастная математика сеялки.

**Только в документации (не подтверждено кодом):** запрет материализации `quoted`-актов; `temporal_marker_on_action`; BC-5 (testimony-выводы); канал `DEDUCED` в runtime; «энтузиазм» docstring'ов о richer semantic fields (TODO-строки `intent_profile.py:7`, `intent_compressor.py:7`).

**Отсутствует:** временные поля ввода; каузальные поля ввода; консьюмер свободных ASSERT; подключение act_consumer; соединение исторической оси с тиковой; сравнимые метрики понимания.

**Дублируется:** резолюция белых пятен (registry vs inline-роут); резолв имён (registry_builder vs стем-резолв ввода vs roster); возрастная математика (age_math vs трюк сеялки); сборка seed (build_full_seed vs отдельные build_seed_*).

**Несовместимости двух контуров (итог §1.2):** время; сущности/резолв имён; причинность; канал знания; модальность (в обратную сторону); реестры событий (EntryKind vs semantic_acts vs Predicate).

---

## 3. Целевое направление

### 3.1. Определение

**USL (Universal Semantic Layer)** — общий семантический фундамент ENIGMA: закрытый словарь типов, описывающих смысл человеческого текста (сущности, события, время, причинность, отношения, модальность, источник знания, контекст), плюс два контурных адаптера, переводящих текст в эти типы, плюс обязательная граница трёх операций: **понимание → принятие истины → исполнение**.

Что USL **есть**:
1. **Контракт типов** (домен-уровень, прецедент `domain/chronicle.py` и `domain/epistemology.py` — stdlib, без зависимостей от services/models, Закон 1.2 Устава).
2. **Проекционный слой**: чистые функции `ChronicleEntry → USLUnit` и `IntentSemanticField → USLUnit` (и обратно — только там, где это безопасно).
3. **Граница ответственности**: место, где «что означает текст» окончательно отделено от «чему верить» и «что исполнять».

Что USL **не есть** (анти-Bond-протокол):
- ❌ не хранилище (никакого `USLStore`, никакого JSON-дампа смысла — прецедент запрета NarrationStore/BiographicalStore, §12.1.7 и §16.9);
- ❌ не шина и не посредник событий (EventBus остаётся единственным транспортом);
- ❌ не новая память, не новый belief store, не вторая хроника, не второй источник истины;
- ❌ не LLM-сервис и не «одна огромная нейросеть для всех операций» (§8);
- ❌ не замена `IntentCompressor`, `BiographyDecomposer`, нормализатора и гейтов — они продолжают работать, USL лишь фиксирует их общий язык (запреты задания, раздел 6).

### 3.2. Ответственности USL

| № | Ответственность | Обоснование из §2 |
|---|---|---|
| 1 | Единое представление времени: точка/длительность/интервал/порядок с якорем и span'ом | время живо в хронике и отсутствует во вводе |
| 2 | Единое представление события: участники, предикат, полярность, статус завершённости | EntryKind/semantic_acts/Predicate — три несовместимых реестра |
| 3 | Единое представление источника и статуса знания | KnowledgeChannel только в хронике; runtime не хранит канал |
| 4 | Типизированные ссылки на сущности с процессом резолюции | три разных резолвера имён |
| 5 | Типизированная модальность (negation/modality/conditionality) как первоклассное поле | per-act контракт ввода — лучший механизм, поднять до общего |
| 6 | Транспортная форма между пониманием и потребителями (память/убеждения/исполнение) | сегодня транспортом служит payload-словарь PLAYER_SPOKE |

### 3.3. Не-ответственности USL (столько же, сколько ответственностей)

1. USL **не решает**, истинно ли утверждение (это Truth/Epistemic Resolution — §7; владельцы: canonize для канона, BeliefRevisionEngine для веры, EvaluationEngine для проверки против TruthState).
2. USL **не исполняет** намерения (владельцы: гейты `compute_intent_readiness`, физический гейт WV, CombatSubscriber, MovementEngine).
3. USL **не пишет** ни в один store (USL-3).
4. USL **не задает игровую политику** (что считать оскорблением, сколько весит угроза — владельцы: EvidenceMapper, BeliefModifierResolver).
5. USL **не заменяет гейты**: если IntentReadiness = PARTIAL, никакая семантическая красота не разблокирует исполнение.

### 3.4. Инварианты (несущие, не сжимать)

1. **USL-1 (одно представление):** одна и та же смысловая конструкция, поступившая из биографии, речи игрока, реплики NPC, воспоминания или хроники мира, даёт совместимые `USLUnit` — одинаковые поля заполнены одинаково, различаются только источником и статусом. Различаются адаптеры, не онтология. (Обобщение DLG-L1 «ИГРОК=НПС» на все источники, включая автора.)
2. **USL-2 (источник ≠ истина):** каждая единица несёт `source` и `epistemic_status`; понимание никогда не повышает статус. Утверждение игрока «я работал на тебя пять лет» и авторское «он пять лет работал на Орма» структурно идентичны и эпистемически различны.
3. **USL-3 (не пишет мир):** ни одна функция USL не имеет права записи в TruthState, канон хроники, EventMemory, BeliefState, EpistemicStore, RelationshipStore. USL — read-only проектор и типовой словарь; писатели — существующие (canonize, seeder, DeltaGate, ClaimEventSubscriber, BeliefRevisionEngine).
4. **USL-4 (обратная совместимость):** `IntentSemanticField`, `IntentParametersDTO`, `IntentDTO`, `BiographyDecomposition`, `ChronicleEntry` остаются действующими контрактами (зарегистрированы в DTO Registry §1/§14); USLUnit добавляется как проекция поверх, поверхностные API не ломаются.
5. **USL-5 (провенанс трассируем):** каждое поле USLUnit восходит к span'у исходного текста (прецедент `AgeAnchor.source_span`, `age_anchor.py:39`) — «число без происхождения запрещено» в расширенной формулировке: **поле без происхождения запрещено**.
6. **USL-6 (детерминизм):** все детерминированные операции над USLUnit воспроизводимы; LLM-участие — только через существующие каналы с temperature=0 и KernelRNG-seed (прецеденты обоих контуров).

### 3.5. Ответы на шесть обязательных вопросов (для каждой новой сущности USL)

| Сущность | 1. Какую проблему решает | 2. Почему существующий механизм не подходит | 3. Владелец | 4. Потребитель | 5. Дублирует ли данные | 6. Как проверяется |
|---|---|---|---|---|---|---|
| `USLUnit` (+ вложенные) | переносимость смысла между контурами | `IntentSemanticField` не содержит времени/причин; `ChronicleEntry` привязан к канонизации и авторству; общего контракта нет | трек USL (Ветвь А), домен `app/domain/usl.py` | seeder (косвенно), ClaimEventSubscriber (косвенно), тесты совместимости, будущие потребители BC/DLG | нет: transient-DTO, не персистится ни в каком store | round-trip-тесты проекции из обоих контуров; сквозная матрица §10 (Этап USL-3) |
| `USLTimeExpression` | время, общее для биографии и ввода | `AgeAnchor` — только возрастные якоря и только в хронике; у ввода нет ничего | трек USL | оба адаптера; резолвер в координаты (age/game_day) | нет: агрегирует существующие `AgeAnchor`-семантики | пара-тесты «одна фраза → одна структура» на 4 источниках |
| `USLEpistemics` (source/status/channel) | утверждение игрока должно сохранять источник | `EntryProvenance` — про канонизацию; `EpistemicRecord` — про уже принятую веру; промежуточного контракта нет | трек USL | ClaimEventSubscriber, будущий BC-5, conclusion_gate | нет: маппинг на существующие enum'ы | тест-маппинг: каждый source/status → легальный приёмник или отказ |
| `BiographyAdapter` / `InteractiveLanguageAdapter` | единая граница понимания | оба контура существуют, но их общие свойства не зафиксированы контрактом | трек USL + владельцы контуров (CCH/AG1) | все, кто сегодня потребляет IntentSemanticField/DecompositionItem | нет: обёртки над существующими движками | контрактные тесты: адаптер не меняет поведение существующих путей (замки на текущие golden-выходы) |

### 3.6. Эволюция, а не революция

USL не требует одновременного переписывания контуров. Порядок жизни: (1) домен-типы появляются без единого изменения production-кода; (2) проекторы пишутся рядом с существующими преобразованиями и покрываются тестами-замками; (3) адаптеры включаются за флагом-вердиктом (прецедент env-гейтов `ENIGMA_SEM_LIB`, `BC1_ENABLED`); (4) потребители подключаются по одному с собственными гейтами. Каждый шаг — отдельная сессия с ADR-пометкой и возвратом к зелёному IPT.

---

## 4. Общая модель смысла

### 4.1. Что уже существует (реюз) — база модели

Словарь USL собирается в основном из существующих типов; новое — только то, чего нет ни в одном контуре.

| Категория | Существующий носитель | Статус в USL |
|---|---|---|
| Пропозиция | `Proposition(subject_id, predicate, object_id, polarity)` — `epistemology.py:75-104` | **реюз как есть**; закрытый `Predicate` расширяется ревизией (уже расширялся: ASSERTS, EXITS_TO, NAME — `epistemology.py:20-33`) |
| Речевой акт | `SpeechAct` (18 значений) | реюз |
| Социальная цель | `SocialIntent` (13 значений) | реюз (ортогональная ось, не USLUnit) |
| Возрастные якоря | `AgeAnchorKind` (6 видов) + `source_span` | **ядро для USLTimeExpression**; обобщение см. §6 |
| Ссылки на сущности | `EntityRef` (4 вида) + alias-registry | **ядро для USLEntityRef**; распространить резолв на ввод |
| Типы записей | `EntryKind` (10) | остаётся внутренним реестром хроники; маппинг в USL-события через явную таблицу (прецедент `entry_kind_to_cause_kind`, `chronicle.py:114-123`) |
| Причинные основания | `CauseKind` (6), `CauseRef`, `CauseCandidate`, `NpcCausalBelief` | реюз полностью; USL не изобретает новую причинность (§6.5) |
| Канал знания | `KnowledgeChannel` (5) | реюз; подъём до общего контракта (§7.3) |
| Модальность акта | per-act `negated/modality/quoted` + `_VALID_ACT_MODALITIES` | **ядро для USLModal**; поднять с per-act до уровня контракта |
| Эпистемический транспорт | `ClaimEvent`, `EpistemicRecord`, `BeliefRevisionEngine` | реюз; USLUnit не заменяет ClaimEvent, а обогащает его источник данных |
| Мировые отношения | `TruthRelation` (7 типов) | реюз как реестр типов отношений |

### 4.2. USLUnit — минимальная единица смысла

```python
@dataclass(frozen=True)
class USLUnit:                    # домен: app/domain/usl.py; stdlib only
    unit_id: str                  # детерминированный md5(source_ref + span) — прецедент make_entry_id
    source_ref: USLSourceRef      # КТО и ОТКУДА: {source_kind, document_ref, span, tick/ordinal}
    text_span: str                # исходная подстрока (USL-5: поле без происхождения запрещено)

    entities: tuple["USLEntityRef", ...]    # участники и упомянутые сущности
    events: tuple["USLEvent", ...]          # события и действия (включая нулевую арность)
    temporal: tuple["USLTimeExpression", ...]   # ВСЕ временные конструкции span'а
    causal: tuple["USLCausalLink", ...]     # заявленные в тексте причины/следствия (см. §6.5 — статус!)
    relations: tuple["USLRelation", ...]    # отношения между участниками
    modality: "USLModal"                    # negation / modality / conditionality
    epistemics: "USLEpistemics"             # источник, канал, статус достоверности (НЕ решает истинность)
    context: "USLContext"                   # анафора, addressee, thread, place
```

Принципы:
- **transient-контракт**: USLUnit не персистится нигде (прецедент `BiographyDecomposition` — «transient: не канон, не персистится как истина», `chronicle.py:404-410`). Он существует в момент передачи между пониманием и потребителем.
- **frozen**: неизменяемость — прецедент `IntentSemanticField.Config.frozen` («Pure Reducer, ADR-TZ10-1») и всех домен-DTO хроники.
- **полнота > глубина**: USLUnit фиксирует, что текст **говорит**, а не что он **означает миру**. Утверждение «Орм предатель» — это USLEvent(assert) с epistemics.status=PLAYER_CLAIM, а не запись о предательстве.

### 4.3. USLEvent и предикаты

```python
@dataclass(frozen=True)
class USLEvent:
    predicate: str                      # закрытый реестр USLPredicate (см. ниже)
    subject: Optional[str]              # unit_id/номер entity или маркер (PLAYER/SELF/UNKNOWN)
    object: Optional[str] = None
    polarity: bool = True               # прецедент Proposition.polarity
    completed: Optional[bool] = None    # завершённость («проработал пять лет» → True; «работаю» → False; None = не сказано)
    negated: bool = False
```

**USLPredicate — стратегия реюза:** базовый реестр = `Predicate` (STOLE/ATTACKED/HELPED/ASSERTS/EXITS_TO/NAME) + семантические типы, необходимые биографиям, для которых в `EntryKind`/payload уже есть поля (WORK_RELATION, INHERIT, MOVE_LOCATION, DEATH...). Расширение реестра — ревизия ADR (прецедент: закрытый реестр vague-markers, «Расширение реестра = ревизия ADR (не молча)», `decomposition_normalizer.py:37-39`). USL не заменяет `EntryKind` и `semantic_acts` — они маппируются явно:

| Источник | Пример | Маппинг в USLEvent |
|---|---|---|
| `EntryKind.EVENT` payload (age, summary) | «в 8 лет осталась без родителей» | predicate=LOSS, subject=SELF, temporal=[POINT(AT_AGE,8)] |
| `EntryKind.RELATIONSHIP` | «пять лет работал на Орма» | predicate=WORK_FOR, object=Orm, temporal=[DURATION(5)] |
| `semantic_acts[].type=ASSERT` | «Я слуга этого дома десять лет» | predicate=ASSERT, object=claim, temporal=[DURATION(10)] |
| DM-вектор ACCUSE | «Игрок обвиняет target» | predicate=ASSERTS_ACCUSATION (уже покрыто парой ASSERTS+STOLE в существующем фоллбеке `claim_event_subscriber.py:111-114`) |

### 4.4. USLTemporal — вынесено в §6 (временная и причинная модель)

Время — самая важная и самая проработанная часть модели, выделена в отдельный раздел вместе с причинностью.

### 4.5. USLRelation

Типы отношений = реюз `TruthRelation` (CAUSES/CONTRADICTS/DEPENDS_ON/REVEALS/CONCEALS/ENABLES/EXPLAINS) как минимальный общий набор + биографические пары «subject→object с valence» из RELATIONSHIP-payload. Скаляры (trust=0.8) в USL запрещены — «числа без происхождения запрещены» (`chronicle.py:154-168`); скаляры вычисляются потребителями (сеялкой, RelationshipStore) из структуры.

### 4.6. USLModal — модальность, отрицание, условность

Поднимаем лучший механизм системы с per-act уровня до контракта единицы:

```python
@dataclass(frozen=True)
class USLModal:
    negated: Optional[bool] = None          # None = НЕИЗВЕСТНО (fail-closed, U-9); не трактуется как False
    modality: Optional[str] = None          # REALIS | HYPOTHETICAL | CONDITIONAL | DESIRED (прецедент _VALID_ACT_MODALITIES)
    condition: Optional[str] = None         # «если будешь хорошо вести» — поле уже есть в IntentSemanticField
    quoted: Optional[bool] = None           # акт внутри чужой речи
    quoted_speaker: Optional[str] = None
```

Ключевой перенос практик: правило Блока 1 «None = недостаточная информация, не False» (`intent_profile.py:53-55`) становится общим законом модальности USL. Гейт-прецедент Блока 3 (негация → PARTIAL, `phase_1_input.py:165-172`) остаётся у потребителя — USL лишь гарантирует, что модальность **дошла** до гейта.

### 4.7. USLEpistemics — источник и статус

```python
@dataclass(frozen=True)
class USLEpistemics:
    source_kind: USLSourceKind    # AUTHOR_CANON | PLAYER_ASSERTION | NPC_SPEECH | NPC_MEMORY |
                                  # WORLD_CHRONICLE | RUMOR | INFERENCE | HYPOTHESIS
    channel: Optional[KnowledgeChannel]  # WITNESSED/TOLD/OVERHEARD/DEDUCED/UNKNOWN — реюз
    certainty: Optional[float] = None    # 0..1, None = не оценено; НЕ равно вероятности истинности
    disputed: bool = False               # противоречие уже известно в данных (прецедент BeliefGrounding.MISTAKEN)
```

Полная семантика статусов и правила эскалации к приёмникам — §7.

### 4.8. USLContext — контекст разговора

Собирает существующее: `references` (анафора, coreference — `intent_profile.py:144`), `addressee` (≠ target, доктрина телесной семантики §12-1 — `intent_profile.py:120`), `dialogue_thread`, `conversation_continuation`, место (scene location). В биографическом контексте: fragment_ord, author_text-абзац, roster. Требование «производительные местоимения резолвятся контекстом беседы, а не угадыванием LLM» (DLG-L2, roadmap §3.6:708) — потребление, не обязанность USL: USL сохраняет отсылку, резолв — за адаптером/потребителем.

### 4.9. Чего модель не делает

- не вводит онтологию мировых объектов (прецедент ItemDTO и scene-слоёв не трогается);
- не нормализует эмоции (EmotionalVector остаётся у ввода, важность — у памяти);
- не решает coreference-цепочки (фиксирует ссылки);
- не хранит эмбеддинги/векторы (запрещено §16.9).

---

## 5. Два адаптера

### 5.1. BiographyAdapter

**Обёртка над существующим конвейером** (ничего из §2.1 не удаляется):

```
author_text фрагмент
 → [существующее] extract_age_anchors_typed + BiographyDecomposer.decompose + Normalizer   ← движок не трогается
 → [новое] BiographyAdapter.to_usl(items, fragment, anchors) → tuple[USLUnit, ...]          ← чистая проекция
      source_kind = AUTHOR_CANON (черновик: AUTHOR_HYPOTHESIS — статусы §7.2)
      ClarificationQuestion-мембраны сохраняются БЕЗ ИЗМЕНЕНИЙ (вопросы живут в хронике, не в USL)
 → [существующее] routes_chronicle: entries, resolve, confirm, canonize (writer-каналы прежние)
```

Ответственность адаптера: (а) полнота проекции — каждое поле payload-а имеет USL-проекцию (покрывается таблицей маппинга §4.3); (б) честность времени — `DURATION`/`YEARS_AGO` проектируются как конструкции, даже когда хроника не может вычислить `historical_age` (сейчас теряется, §2.1); (в) span-провенанс каждого поля.

### 5.2. InteractiveLanguageAdapter

```
raw_text игрока / реплики NPC
 → [существующее] IntentCompressor.compress (fast/slow/recovery) + resolve_player_intent  ← движки не трогаются
 → [новое] InteractiveLanguageAdapter.to_usl(field, intent_resolution, scene) → tuple[USLUnit, ...]
      source_kind = PLAYER_ASSERTION / NPC_SPEECH (DLG-L1: классы спикеров различаются только provenance)
      сцена-резолв сущностей переиспользуется (resolve_target_with_candidates + alias-registry общий §5.4)
 → потребители БЕЗ ИЗМЕНЕНИЙ: IntentReadiness-гейт, физический гейт, публикация событий
 → НОВЫЕ потребители подключаются поэтапно: сначала claim-каналы существующие (SELF_INTRODUCTION, DM-вектор),
    затем свободный ASSERT → ClaimEvent (закрытие разрыва §2.2.4 — Этап USL-1 §9)
```

Ответственность адаптера: (а) не ухудшить исполнение — физические/движковые ветки читают `IntentSemanticField` как прежде; (б) сохранить гейты — readiness вычисляется до адаптера и не пересчитывается; (в) проекция модальности — per-act признаки всех актов попадают в USLModal.

### 5.3. Что одинаково / что различается

| Аспект | BiographyAdapter | InteractiveLanguageAdapter |
|---|---|---|
| Движок понимания | BiographyDecomposer + Normalizer | IntentCompressor (fast/slow) |
| Временной препарсинг | `extract_age_anchors_typed` (6 видов) | **тот же модуль, тот же вызов** (новый общий шаг; сейчас отсутствует) |
| Резолв сущностей | alias-registry + roster + вопросы автору | сцена + alias-registry (единый реестр имён) |
| Схема | свободный `draft_payload` по kind | белый список актов + плоские поля |
| Гейты качества | fail-loud нормализатор, мембраны, needs_confirmation | comprehension_facts, IntentReadiness, физика |
| Статус по умолчанию | AUTHOR_HYPOTHESIS → AUTHOR_CANON (после канонизации) | PLAYER_ASSERTION / NPC_SPEECH — канонизироваться не может |
| Приёмники | хроника → сеялка → память/убеждения/отношения | гейты → исполнение; ASSERT → ClaimEvent → EpistemicStore |
| Персистенция смысла | в хронике (после канонизации) | нигде (transient); в памяти — только через существующие writer'ы |

**Инвариант адаптеров:** разность между адаптерами ограничена этой таблицей. Любое поле, присутствующее в обоих столбцах, обязано заполняться из одного и того же общего типа (USL-1). Проверка — контрактный тест §9 (Этап USL-1): одна и та же конструкция, поданная в оба адаптера, даёт одинаковые `events/temporal/relations` и различные только `epistemics/context`.

### 5.4. Единый реестр имён (обязательный побочный продукт)

Три текущих резолвера (`registry_builder.alias_to_npc`, `_resolve_npc_by_name` со стеммингом, roster exact-match) сводятся на общий `CanonicalRegistry` (уже production-модуль, `registry_builder.py:23-72`, CCH-7). Хроника уже использует его через нормализатор; ввод получает доступ без изменения своих гейтов. Это закрывает ⚠️-дублирование §2.5 и делает резолв «Орму» одинаковым для автора и игрока. Владелец реестра не меняется.

---

## 6. Временная и причинная модель

Раздел фиксирует, как одна и та же конструкция времени представляется независимо от источника (USL-1), и как причинность остаётся за существующими четырьмя слоями S366.

### 6.1. Четыре формы времени в человеческом тексте

| Форма | Примеры (биография) | Примеры (игровой ввод) | Существующий носитель |
|---|---|---|---|
| **Точка в прошлом/будущем** | «в 8 лет осталась без родителей»; «пять лет назад» | «Год прошёл с тех пор, как…» (конечная точка) | `AgeAnchor(AT_AGE / SINCE_AGE / YEARS_AGO)` — `age_anchor.py:22-31` |
| **Длительность** | «уже 57 лет», «из которых 12 лет» | «я пять лет работал на тебя» | `AgeAnchor(DURATION)` — распознаётся, но **не резолвится в координату** (`routes_chronicle.py:374-386`); у ввода отсутствует |
| **Интервал между событиями** | «после смерти отца», «год прошёл с тех пор» | «с тех пор, как я закончил работу» | 🔴 нет нигде |
| **Порядок/одновременность** | «за двадцать лет до этого он уже знал Орма» | «до того, как ты пришёл» | частично: `CauseCandidate(TEMPORAL_ORDER)` — но только как детекция-кандидат, «хронология ≠ причина» (`chronicle.py:251-252`) |

### 6.2. USLTimeExpression

```python
class USLTimeKind(str, Enum):
    POINT = "point"              # точка (якорная или вычислимая)
    DURATION = "duration"        # длительность («пять лет», «десять лет службы»)
    INTERVAL = "interval"        # интервал между событиями («год прошёл после…»)
    ORDER = "order"              # относительный порядок («до», «после», «за N лет до»)

@dataclass(frozen=True)
class USLTimeExpression:
    kind: USLTimeKind
    anchor: Optional[USLAnchor] = None
    # USLAnchor = обобщение AgeAnchorKind: AGE_N | YEARS_AGO | WORLD_YEAR | GAME_TICK |
    #             EVENT_REF(id) | SPEECH_TIME | UNKNOWN
    value: Optional[int] = None          # количество (лет/дней/тиков) — семантика задаётся kind+anchor
    relative_to: Optional[str] = None    # unit_id/event, к которому относится INTERVAL/ORDER
    source_span: str = ""                # USL-5
```

Правила проектирования:
1. **Каждая конструкция → отдельное выражение.** Фраза «Год прошёл с тех пор, как я пять лет работал на тебя» даёт `USLEvent(WORK_FOR)` + `USLTimeExpression(DURATION, value=5, relative_to=событие)` + `USLTimeExpression(INTERVAL, value=1, relative_to=конец события)`. Связь «интервал после завершения» выражается через `relative_to` + `USLEvent.completed=True`, а не склеенной строкой.
2. **UNKNOWN — легальное значение якоря** (прецедент `AgeAnchorKind.AMBIGUOUS`: «нельзя классифицировать — нельзя выдумывать», `age_anchor.py:30`).
3. **«N лет» без маркера остаётся AMBIGUOUS→UNKNOWN** — та же честность, что и в хронике; диагностическая аномалия `years_ago_equals_current_age` (`biography_decomposer.py:142-154`) переносится на общий слой (проверка «подозрительного равенства»).

### 6.3. Резолюция в координаты — два чистых этапа

**Этап R1 (язык → выражение):** детерминированный препарсинг. Хроника уже имеет его (`extract_age_anchors_typed`); для ввода — тот же модуль, расширенный паттернами интервала/порядка. Расширение паттернов — не новое правило понимания, а расширение реестра (прецедент CCH-S365: «regex возрастных якорей расширен до 6 форм» — roadmap §0.2:300).

**Этап R2 (выражение → координата):** чистая функция, разные оси для разных контекстов:

| Якорь | Оси координат | Формула/владелец |
|---|---|---|
| `AGE_N` | historical_age | как есть |
| `AGE_N` + game_start_age | game_day (отрицательный) | `day=(age−start)×365` — `chronicle_seeder.py:125-142` |
| `YEARS_AGO` + game_start_age | historical_age = start − N | `routes_chronicle.py:361-364` (уже реализовано для хроники) |
| `WORLD_YEAR` | historical_year | поле есть (`chronicle.py:339`), потребителя нет — пробуждение, не новая ось |
| `GAME_TICK` | tick | `TemporalContext.current_tick` (`temporal_engine.py:58-95`) |
| `SPEECH_TIME` | tick произнесения | `ClaimEvent.tick` (`epistemology.py:119`) |
| `EVENT_REF` | координата события-референта | резолв по существующим записям (chronicle entry / EventMemory / ClaimEvent) |

**Запрет смешения осей сохраняется в общем виде:** «время события» и «время узнавания» остаются двумя осями для всех источников (П4 roadmap §13.0, инвариант `KnowledgeLink.validate_against`). Утверждение игрока имеет `SPEECH_TIME` как время узнавания (NPC услышал сейчас) и, опционально, `POINT/DURATION` как время события (если игрок о прошлом).

### 6.4. Причинность: четыре существующих слоя, ноль новых

USL не создаёт новую причинность. `USLCausalLink` в USLUnit — это **заявление текста** со статусом:

```python
@dataclass(frozen=True)
class USLCausalLink:
    relation: str                 # CAUSES | ENABLES | EXPLAINS | ... — реестр TruthRelation
    cause_ref: str                # unit_id/entry_id/event_id
    effect_ref: str
    asserted_by_text: bool        # True = текст прямо говорит («после смерти отца он унаследовал дом»)
```

`asserted_by_text=True` означает только то, что сказал текст. Статус истины связи решается существующими механизмами: в хронике — автор через `CauseRef`/`CauseCandidate` (ACCEPT/REJECT, СЛОИ 1-4 S366, `chronicle.py:223-325`); в мире — `TruthRelation.CAUSES`; в убеждениях — `NpcCausalBelief` + `BeliefGrounding` (MISTAKEN — «только явное решение автора», `chronicle.py:236-243`). Запрет «хронологический порядок → причинность» распространяется на USL: `USLTimeExpression(ORDER)` никогда не конвертируется в `USLCausalLink` автоматически.

### 6.5. Сквозной разбор §0 (совместимость по USL-1)

Одна конструкция — четыре источника — одна структура:

| Поле | Биография: «Он пять лет работал на Орма» | Игрок: «Я пять лет работал на тебя» | Воспоминание NPC: «Он работал на меня пять лет» | Хроника: «Год прошёл после окончания его службы» |
|---|---|---|---|---|
| events | `WORK_FOR(subject=Он→npc, object=Orm, completed=True)` | `WORK_FOR(subject=PLAYER, object=ADDRESSEE, completed=True)` | `WORK_FOR(subject=Он→npc, object=ME, completed=True)` | `SERVICE_END(subject=npc, completed=True)` |
| temporal | `DURATION(5, rel=event)` | `DURATION(5, rel=event)` | `DURATION(5, rel=event)` | `INTERVAL(1, rel=SERVICE_END)` |
| relations | `WORK_RELATION(npc→Orm)` | `WORK_RELATION(PLAYER→ADDRESSEE)` | `WORK_RELATION(npc→ME)` | — |
| epistemics.source_kind | AUTHOR_CANON | PLAYER_ASSERTION | NPC_MEMORY | WORLD_CHRONICLE |
| epistemics.channel | — (канон) | UNKNOWN (сам-отчёт) | WITNESSED (если был участником) | — |
| **Различия только в** | **participants-ref, epistemics, context** | | | |

Структурная идентичность первых трёх столбцов и есть формулируемый тест сквозной матрицы (§10, Этап USL-3): **одинаковое содержание ≠ одинаковый эпистемический статус** — статус различен в точности из-за `epistemics`, и никак иначе.

### 6.6. Границы модели времени (честные ограничения)

1. Длительности без привязки («пять лет») не становятся координатой — только в паре с якорем/событием. Это следствие §ENIGMA-003 (сырой текст ≠ факт) и записи §ENIGMA-003 в компрессоре (V.3: «честное UNKNOWN»).
2. Приблизительные конструкции («лет десять», «около года») — `value + approximation` (расширение реестра), вербализация допускает нечётность (прецедент NL-INV-SSOT: «Мне кажется, это было лет десять назад» — валидная речь, roadmap §12.1.1).
3. Календарь мира (12×30+5) остаётся в `core/constants.py` — USL не дублирует константы, R2 использует `age_math`-функции.

---

## 7. Источники знания и истина

### 7.1. Разделение трёх операций (обязательное архитектурное требование)

```
ОПЕРАЦИЯ 1: SEMANTIC UNDERSTANDING                 ОПЕРАЦИЯ 2: TRUTH / EPISTEMIC RESOLUTION
  «Что именно означает текст?»                        «Каков статус информации?»
  владелец: адаптеры USL (§5)                          владельцы: canonize (канон), BeliefRevisionEngine (вера),
  выход: USLUnit — события/время/сущности                        EvaluationEngine (проверка), автор (канонизация)
  НИКАКИХ записей в мир                                  выход: место единицы в существующих контейнерах
                                                       ↓
                                            ОПЕРАЦИЯ 3: OPERATIONAL EXECUTION
                                              «Какие изменения мира разрешены?»
                                              владельцы: IntentReadiness+физика (ввод), сеялка (канон),
                                                         DeltaGate/ConclusionGate (дельты), ActionCompiler
```

Инвариант границы (продолжение S188 и INV-LLM-NOT-SSOT на новый уровень): **результат операции 1 — не факт мира; результат операции 2 — всегда в существующем контейнере с существующим writer'ом; операция 3 — всегда за существующим гейтом.** USL добавляет только язык для операций 1→2, не трогая права записи.

### 7.2. Статусы источников и их приёмники (карта разрешённых путей)

| `USLSourceKind` | Что это | Может стать каноном? | Легальные приёмники | Существующие защита/гейт |
|---|---|---|---|---|
| `AUTHOR_CANON` | канонизированная хроника | уже канон | сеялка → EventMemory/BeliefState/relationships | INV-LLM-NOT-SSOT, `validate_document`, CCH-7 |
| `AUTHOR_HYPOTHESIS` (LLM_DRAFT) | гипотеза декомпозитора | только решением автора («Принять как канон») | ничего до канонизации | флаг needs_confirmation, вопрос-мембраны |
| `PLAYER_ASSERTION` | утверждение игрока | **никогда** | ClaimEvent → EpistemicStore (вера слушателя); память беседы; будущий BC-5 (выводы NPC об игроке) | S188; proposition-guard; мембрана can_observe |
| `NPC_SPEECH` | реплика NPC (включая самоотчёт и ложь) | никогда | как у PLAYER_ASSERTION (DLG-L1 симметрия) | S188; NpcSpeechActSubscriber |
| `NPC_MEMORY` | воспоминание NPC о прошлой реплике/событии | никогда | перерасказ через существующий testimony-канал | decay/distortion механизмы памяти |
| `WORLD_CHRONICLE` | хроника мира (проекции CCH-5) | уже канон | TruthState-проверки, EvaluationEngine | projection-гейты |
| `RUMOR` | слух | никогда | EpistemicRecord с низкой certainty | intelligence_queue (слухи, D8P) |
| `INFERENCE` | вывод (BC-1 dormant) | никогда | ConclusionStore (закрытый predicate-реестр) | ConclusionGate: только direct_experience до BC-5 |
| `HYPOTHESIS` | модель-гипотеза (галлюцинация LLM, не разобрано) | никогда | отбрасывается или нуждается в подтверждении | fail-loud DecompositionError / UNCERTAIN |

Ключевая строка таблицы: `PLAYER_ASSERTION → канон: никогда`. Утверждение игрока о прошлом не проходит ни одним путём в TruthState, канон хроники или стартовое состояние. Оно может породить только **веру слушателя** (с source_id игрока) и — после BC-5 — **вывод NPC** (с provenance testimony). Это полностью соответствует требованию задания «распознанное утверждение не становится автоматически объективной истиной».

### 7.3. Единый канал знания (подъём KnowledgeChannel)

`KnowledgeChannel` (WITNESSED/TOLD/OVERHEARD/DEDUCED/UNKNOWN) сегодня живёт только в `KnowledgeLink` хроники. USL поднимает его в `USLEpistemics.channel` как общий контракт; приёмники, у которых канала нет (`EventMemory`, `EpistemicRecord`), получают его как опциональное поле **только через своих существующих writer'ов** (запись EventMemory остаётся у `MemoryManager.apply`; расширение frozen-DTO — отдельная ревизия по Уставу, не USL-полномочие). До такой ревизии канал транспортируется в tags-строке события (прецедент `tags=("chronicle:<entry_id>",)` — `npc_loader.py:982-997`).

### 7.4. Противоречия и неопределённость

- Противоречие «утверждение игрока ↔ канон» **не разрешается автоматически** — ошибка пути. Игрок, говорящий «я работал на Орма», создаёт веру; сверка с каноном — задача потребителей (EvaluationEngine/сверщики CCH-7-класса), а не понимания.
- Внутри единицы противоречие фиксируется как `disputed=True` + ссылки на конкурирующие unit_id (прецедент: `BeliefGrounding.MISTAKEN`, `NpcCausalBelief` — «может быть ошибочным»).
- Неопределённость — градуальная (`certainty`) и категориальная (None-поля модальности); обе честно проходят до потребителя, гейт решает (прецедент fail-closed Блока 3).

### 7.5. Запрет второго источника истины (перечень запрещённых USL-действий)

1. ❌ USL-функция пишет в TruthState / канон хроники / любой store (нарушение USL-3).
2. ❌ USL-проектор «подтверждает» утверждение игрока против канона (кросс-чек может выполняться только read-only и выдавать Finding, прецедент ConsistencyService, `consistency_service.py`).
3. ❌ USL-Unit материализуется как EventMemory/Conclusion/BeliefFragment минуя их writer'ов.
4. ❌ USL-Unit становится ещё одной персистентной формой биографии (анти-архив NL-2, §12.1.7).
5. ❌ Повышение статуса через повтор (пять раз «я работал на тебя» ≠ канон; прецедент: «Припоминание растит доступность, не истинность», §3.1 roadmap:641).

---

## 8. Вычислительная архитектура

### 8.1. Принцип: конвейер разных исполнителей, не одна нейросеть

Мандат задания: «Не проектировать одну огромную нейросеть для всех операций». Архитектура USL распределяет операции между уже существующими классами исполнителей — ровно в той пропорции, которая уже оплачена кодом обоих контуров:

1. **Детерминированный Python — скелет.** Типы, проекции, резолюция времени R2, валидация, идемпотентные id (md5-прецедент `make_entry_id`). Ноль LLM, ноль недетерминизма.
2. **Детерминированный препарсинг — Fast Path.** `extract_age_anchors_typed` (6 форм якорей) и леммы pymorphy3 ввода. Простые конструкции не должны требовать LLM: «пять лет назад» разбирается regex'ом уже сегодня.
3. **LLM — структуратор сложного, не авторитет.** Оба контура уже вызывают LLM с temperature=0 и KernelRNG-seed; USL не добавляет нового вызова LLM, а фиксирует, что его вывод попадает в общий контракт. Грамматика GBNF — прецедент принудительной структуры (S371).
4. **Кэширование и replay** — прецеденты: `DEBT-CHRONICLE-REPLAY` (рекордер привязан к тик-сессии), DET-TRACE-наблюдаемость компрессора. Кэш промптов USL-операций — наследование существующих механизмов, не новая система.
5. **Резолв сущностей — детерминированный** (U-2 «Python владеет идентификацией сущностей», `phase_1_input.py:179-185`): alias-registry + сцена; LLM предлагает hint, не решает.
6. **Когнитивные системы — потребители** с их собственными гейтами (память, убеждения, выводы). USL ничего не «включает» в них сам.

### 8.2. Карта «операция → исполнитель»

| Операция | Детерминированный код | Fast Path (preparsing) | LLM | Кэш/Replay | Резолв сущностей | Когнитивные системы |
|---|---|---|---|---|---|---|
| Извлечение якорей времени | ✅ R2-резолюция | ✅ оба контура (единый модуль) | только подтверждение структуры (GBNF) | ✅ прецеденты | — | — |
| Разбор сложной временной конструкции (интервал/порядок) | валидация структуры | первичная детекция маркеров («прошёл с тех пор как», «за N лет до») | ✅ проекция в `USLTimeExpression` | ✅ по span'у | привязка `relative_to` к событию | — |
| События/предикаты | маппинг-таблицы | леммы действий (существующие) | ✅ (существующие вызовы) | — | ✅ существующие | — |
| Модальность/отрицание | белые фильтры (существующие) | частицы-эскалация (существующие) | per-act признаки (существующие) | — | — | гейт потребителя (Блок 3-прецедент) |
| Источник/статус | ✅ полностью (это данные вызова, не текст) | — | ❌ LLM не решает статус | — | — | приёмники по §7.2 |
| Резолв имён | ✅ полностью | — | hint-only | ✅ registry-кэш | ✅ | — |
| Проверка совместимости источников | ✅ (тесты, сверщики) | — | ❌ | — | — | EvaluationEngine/ConsistencyService |

### 8.3. Границы LLM-участия

1. LLM не присваивает `source_kind`, `certainty` канона, статус истины — это данные вызова.
2. LLM-вывод всегда за белым фильтром (прецеденты `_validate_acts`, normalizer fail-loud).
3. Один вызов LLM на фрагмент/реплику, как сегодня; USL не умножает вызовы. Каскады — только через существующие mechanism'ы эскалации (fast-incomplete → slow).
4. Модульность промпта — прецедент semantic_library (модульные блоки, «Router отсутствует by design (Э0-Э2)» — `llm_compressor_client.py:259-266`): будущий общий модуль «temporal» встраивается в оба промпта как модуль библиотеки, не fork промптов.

### 8.4. Стоимость и детерминизм

- Каждый LLM-вызов воспроизводим: `temperature=0`, `seed=KernelRNG(salt=prompt)` — одинаково в обоих контурах (`biography_decomposer.py:9-15`; `llm_compressor_client.py:52-61`).
- USL-проекции — чистые функции: повторный прогон = идентичный USLUnit (критерий приёмки Этапа USL-1).
- VRAM-конфликты — общий семафор ModelRouter (мера рисков CCH, roadmap §13.5).

---

## 9. План внедрения (ревизия R1 — обязательная последовательность движения)

**Утверждённое направление: СНАЧАЛА ИНТЕГРАЦИЯ → ЗАТЕМ ПРОВЕРКА НА РЕАЛЬНОМ КОНТЕНТЕ → ЗАТЕМ РАЗВИТИЕ ВОЗМОЖНОСТЕЙ.**

```
INTEGRATION → NPC BIOGRAPHIES → REAL DIALOGUES → SEMANTIC DEVELOPMENT → SCALE
USL-0/USL-1     USL-2             USL-3           USL-4                USL-5
```

Мы не должны сначала создавать всё более сложную систему понимания языка, а потом выяснять, как подключить её к игре. Сначала необходимо объединить уже существующие механизмы биографического и игрового контуров (USL-1), затем проверить их на реальных биографиях NPC, написанных автором ENIGMA (USL-2), затем на реальных диалогах (USL-3) — и только после этого расширять возможности системы на основании обнаруженных ограничений (USL-4) и проверять масштабирование (USL-5). Результат — рабочий архитектурный трек ENIGMA, а не описание будущей технологии.

**Карта соответствия нумерации (старая → новая).** Прежний план §9 состоял из этапов: USL-1 «Домен-контракты и проекторы», USL-2 «Временной слой», USL-3 «BiographyAdapter + корпус», USL-4 «InteractiveLanguageAdapter + разрыв утверждений», USL-5 «Сквозная проверка». В ревизии R1: старые USL-1 + USL-2 + USL-4 объединены в **новый USL-1 (интеграция контуров)**; старый USL-3 расширен в **новый USL-2 (полный биографический корпус)**; старый USL-5 разделён между критериями завершения USL-2/USL-3 и сквозной системой проверок §9.7; **новые USL-3 (реальные диалоги), USL-4 (развитие), USL-5 (масштабирование) добавлены**. Инварианты USL-1…USL-6 (§3.4) не менялись; Этап USL-0 — гейт в обеих нумерациях. Ссылки дорожной карты на старую нумерацию синхронизированы (§11.5).

Правила всех этапов (несущие, не сжимать):
- без изменения production-поведения до соответствующего GO; каждый этап = отдельные сессии, ADR-пометка, зелёные линтеры/IPT, запись в MUTATIONS; статусы задач треков не меняются (см. §10 и примечания в roadmap);
- никаких новых параллельных хранилищ истины на любом этапе (инвариант USL-3);
- переход к следующему этапу — только через критерий завершения предыдущего; успех одного уровня проверки не означает успех следующего: «PARSED» ≠ «SEEDED» ≠ «USED IN GAME» (статусная цепочка этапа USL-2);
- успешный ответ LLM не считается достаточным доказательством корректности — тест обязан проверять весь путь до игрового потребителя (§9.7);
- LLM может ошибаться: неопределённость сохраняется (None/UNKNOWN — легальные значения, §4.6/§6.2), а не маскируется принудительным заполнением всех полей.

### Этап USL-0. Архитектурная фиксация и контракты (гейт всего направления)

**Цель:** подготовить безопасную основу интеграции. **Выход: утверждённый технический проект интеграции** — не код.

Задачи:
1. Определить владельцев существующих семантических данных (хроника — CCH; ввод/эпистемика — AG1/DLG и S188-контур; память — MEM; реестр имён — `registry_builder`, CCH-7).
2. Установить, какие контракты уже являются общими для обоих контуров (`Proposition`/`SpeechAct` из `epistemology.py`; `CanonicalRegistry`; GBNF/KernelRNG-детерминизм — §2.4).
3. Определить минимальные изменения для совместимости двух контуров (состав соединяемых механизмов — этап USL-1; конкретный перечень фиксируется техпроектом по результатам аудита).
4. Установить границы между пониманием смысла, принятием утверждения за знание и исполнением игровых действий (три операции — §7.1).
5. Определить необходимые изменения DTO и существующих интерфейсов (`USLUnit` — проекция поверх действующих контрактов, инвариант USL-4; любые изменения frozen-DTO — только отдельной ревизией по Уставу, §7.3).
6. Проверить влияние на действующие треки дорожной карты (CCH-02, DLG-2/3, BC-5, NL-1/NL-2, ARC-NPC — §9.8, §11.3).
7. Подготовить IMPACT, ADR и необходимые записи в DTO Registry согласно правилам проекта: мини-ADR «Universal Semantic Layer» (номер по атласу max+1) + IMPACT-файл в `docs/audits/` + секция реестра по прецеденту §14 «CHARACTER CHRONICLE»; вердикт Мастера: владелец (Ветвь А), границы с MEM/NL/CCH/AG1, приоритет против §0.2.

**Критерий приёмки:** ADR + IMPACT + секция реестра + утверждённый техпроект + вердикт Мастера; ни одного изменённого py-файла. Никаких новых параллельных хранилищ истины.

### Этап USL-1. Интеграция биографического и игрового языковых контуров (первый основной этап реализации)

**Цель:** соединить существующие механизмы двух контуров на совместимой семантической основе. Задача — **не переписать два контура в один класс**, а обеспечить использование совместимых семантических представлений.

Соединяемые механизмы (конкретный перечень определяется по результатам аудита и утверждённого технического проекта USL-0): `BiographyDecomposer`; `ChronicleDecompositionNormalizer`; `IntentCompressor` (Fast Path + LLM fallback); `IntentSemanticField`; существующие семантические типы (`Proposition`/`SpeechAct`/`SocialIntent`); `AgeAnchor` (+ `extract_age_anchors_typed`); `EntityRef` (+ единый реестр имён §5.4); `ClaimEvent`/`EpistemicRecord`; `CauseRef` и существующие механизмы причинности (четыре слоя S366 — §6.4, ноль новых).

Состав работ (вобрал прежние этапы USL-1/USL-2/USL-4 — карта соответствия в шапке §9):
1. **Домен-контракты и проекторы:** `app/domain/usl.py` (`USLUnit, USLEvent, USLTimeExpression, USLEntityRef, USLRelation, USLModal, USLEpistemics, USLContext, USLSourceKind`; stdlib only, Закон 1.2); чистые проекторы `chronicle_to_usl.py` (ChronicleEntry/DecompositionItem → USLUnit) и `intent_to_usl.py` (IntentSemanticField → USLUnit); тесты-замки: проекция детерминирована на 6 существующих канонах, golden-выходы обоих контуров не меняются.
2. **Общий временной слой:** обобщение `AgeAnchorKind → USLAnchor`; паттерны INTERVAL/ORDER (расширение реестра по прецеденту S365); `USLTimeResolver` — этап R2 с таблицей §6.3 (реюз `age_math`-функций; оживление `historical_year`-оси не входит в минимум); единый препарсинг в обоих контурах — за env-флагом (прецедент `ENIGMA_SEM_LIB`); временные конструкции входят в `comprehension_facts` (реализация зарезервированного ключа `temporal_marker_on_action` — теперь уже честная).
3. **Адаптеры:** `BiographyAdapter` (в контуре хроники, вне тика, layer 4 — П6 roadmap §13.0) и `InteractiveLanguageAdapter` (в тик-пайплайне, после `resolve_player_intent`, до потребителей — за флагом).
4. **Закрытие разрыва утверждений:** свободный `ASSERT` → ClaimEvent через существующего подписчика (разрыв §2.2.4) — **только вера слушателя**, гейты S188/membrane/proposition-guard полностью сохраняются; enforcement `quoted`/`modality` — по прецеденту Блока 3 (гейт потребителя; quoted=True → запрет материализации world-changing акта); подключение `act_consumer.consume_npc_acts` или его осознанное удаление (решение архитектора, оба варианта легальны — мёртвый код не сохраняется молча).

Обязательно обеспечить (8 несущих требований):
1. **Совместимое представление событий** (§4.3 — маппинг EntryKind/semantic_acts → USLEvent).
2. **Совместимое понимание времени и длительности** (§6 — USLTimeExpression, этапы R1/R2).
3. **Совместимое представление участников и отношений** (§4.5; §5.4 — единый реестр имён: «Орму» автора и «Орму» игрока резолвятся одинаково).
4. **Совместимое представление причинности** (§6.4 — USLCausalLink со статусом `asserted_by_text`; автоматическое «хронологический порядок → причина» запрещено).
5. **Сохранение источника информации** (§4.7 — USLEpistemics; провенанс каждого поля — инвариант USL-5).
6. **Разделение авторского канона и пользовательских утверждений** (§7.2 — `PLAYER_ASSERTION → канон: никогда`).
7. **Передача результата в существующие игровые когнитивные механизмы** (сеялка, MemoryManager, BeliefRevisionEngine, гейты — писатели прежние, инвариант USL-3).
8. **Отсутствие дублирующих путей записи истины** (инвариант USL-3 + тест-запреты).

Отдельно устранить или обосновать существующий разрыв между свободными утверждениями игрока и эпистемическим контуром (§2.2.4): минимальное закрытие — путь «свободный ASSERT → ClaimEvent → EpistemicRecord с source_id игрока»; альтернатива «обоснованная несоединимость» требует отдельного вердикта Мастера.

**Критерий завершения:** оба языковых контура используют согласованную семантическую основу, а полученные данные проходят по реальным игровым цепочкам (трассировка вызовов, не схема). Проверки:
- контрактный тест: одинаковая конструкция из двух контуров даёт одинаковые `events/temporal/relations` и различающиеся `epistemics`;
- пара-тесты §6.5: «я пять лет работал на тебя» даёт `DURATION(5)` на вводе **точно так же**, как биография; «Год прошёл с тех пор, как…» даёт `INTERVAL(1)`; «N лет» без маркера остаётся UNKNOWN;
- фраза «Я пять лет работал на тебя» порождает у собеседника `EpistemicRecord` с source_id игрока и **не** меняет ни канон, ни TruthState; `PLAYER_ASSERTION → канон` — невозможно (тест-запрет);
- регресс fast-пути нулевой: IntentReadiness-поведение существующих корпусов (`backend/tests/sandbox/scenarios/dlg0_golden_corpus.py`, `backend/tests/sandbox/SUPERBOX/scenarios/ue0_baseline_corpus.py`) не изменилось; все существующие тесты компрессора зелёные; IPT зелёный; ноль production-поведенческих изменений вне флагов.

### Этап USL-2. Полная интеграция биографического корпуса (первый реальный корпус)

После интеграции общего фундамента — реальные биографии NPC, написанные автором ENIGMA. **Это не демонстрационный этап на нескольких искусственных предложениях.**

Задачи:
1. Найти полный перечень существующих авторских биографий NPC (`docs/Прошлое персонажей черновик/Все.md`, `Люся.md`; каноны `config/npc/chronicles/*.json` — 6 NPC на момент исследования).
2. Установить, какие биографии реально подключены к действующему игровому процессу (канон → new-game гейт `npc_loader.py:963-997` → сеялка).
3. Проверить полноту, структуру и сложность исходных текстов.
4. Прогнать весь доступный корпус через общий семантический механизм (полнопроходной прогон через `scripts/redecompose_all_npc.py` + USL-проекция).
5. Выявить конструкции, которые система понимает неправильно или не понимает вовсе (отчёт покрытия: какие конструкции покрыты, какие честно UNKNOWN).
6. Проверить временные, причинные и реляционные связи.
7. Проверить корректность формирования хроники.
8. Проверить перенос полученной информации в когнитивные структуры NPC (фактическая цепочка §2.1: canonize `routes_chronicle.py` → `chronicle_store.py:411-458` → `npc_loader.py:963-997` → `chronicle_seeder.py` → `phases/memory.py:43,94`, `npc_tick_pipeline.py:484`).
9. Проверить использование этих данных в игровом процессе.

Особое внимание:
- возраст и жизненные периоды;
- длительность событий;
- события до и после других событий;
- родственные и социальные отношения;
- служба, работа, обязательства;
- причины поступков;
- изменения отношений;
- события, повлиявшие на характер и убеждения;
- неполные сведения и противоречия.

**Статусная цепочка каждой биографии (несущая):**

```
SOURCE TEXT → PARSED → NORMALIZED → CANONIZED → SEEDED → COGNITIVELY AVAILABLE → USED IN GAME
```

Успех на одном этапе не означает успех на последующих. Если биография успешно разобрана, но её сведения не попали в память, убеждения или другие игровые механизмы — интеграция не считается завершённой. Отчёт этапа обязан показывать счётчики по каждому звену цепочки, а не только «декомпозиция успешна».

Игровые проверки (F5-лаборатория + живые сценарии):
- NPC должен учитывать события собственного прошлого;
- NPC должен знать соответствующие факты в пределах предусмотренного ему канала знания;
- NPC должен правильно соотносить события по времени;
- NPC не должен знать того, чего он не мог знать;
- биографические обстоятельства должны иметь возможность влиять на его решения и отношения;
- разные NPC не должны автоматически получать одинаковое знание о событии только потому, что оно присутствует в общей хронике.

Данные корпуса: заполнение `game_start_age` канонов, первые BELIEF_SEED/KNOWLEDGE_LINK (устранение пустоты §2.1) — это контентная работа автора; USL только делает её измеримой. Известные дефекты корпуса (guard_borko SeederError, orm-несоответствие профиль/канон) либо устраняются, либо оформляются вопросами автору. Оценить стоимость обработки корпуса (LLM-вызовы, время, объём) — материал для USL-5.

**Критерий завершения:** авторские биографии не просто преобразуются в структуру, а становятся действующей частью игрового мира. Дополнительно: (а) 100% фрагментов корпуса имеют USL-проекцию со span-провенансом; (б) сеялка получает те же структуры, что и до USL (диф-тест seed до/после — «замок равенства»); (в) каждая биография имеет заполненную статусную цепочку без разрывов (либо оформленный вопрос/белое пятно); (г) игровые проверки пройдены в F5-лаборатории.

### Этап USL-3. Реальные диалоги (второй реальный корпус)

После успешной проверки биографического корпуса — реальные диалоги ENIGMA: существующие диалоговые сценарии, записи тестовых взаимодействий или специально подготовленные разговоры с NPC (кандидаты: `backend/tests/sandbox/scenarios/dlg0_golden_corpus.py` — 20 сценариев DLG-0; `backend/tests/sandbox/SUPERBOX/scenarios/ue0_baseline_corpus.py`; новые разговорные последовательности). **Не ограничиваться короткими командами:** система должна получать полноценные разговорные последовательности, в которых смысл зависит от предыдущих реплик.

Проверить:
- местоимения и отсылки к предыдущим репликам;
- смену субъектов;
- временные конструкции;
- длительность событий;
- прошлое и будущее;
- отрицание;
- условные конструкции;
- обещания и обязательства;
- угрозы и предупреждения;
- просьбы и приказы;
- утверждения о прошлом;
- ложные сведения;
- противоречия;
- слухи и чужие рассказы;
- неоднозначные выражения;
- эмоционально окрашенную речь, если она меняет смысл речевого акта.

Эталонные фразы (проверяются в связке, не поодиночке):
- «Я уже говорил тебе об этом вчера».
- «Ты обещал мне помочь, когда мы встретились в прошлом году».
- «Если бы твой отец не вмешался, я бы никогда не покинул этот город».
- «Я пять лет служил твоему дому, но уже год как ушёл».
- «Ты думаешь, что я лгу, потому что тебе рассказал об этом Орм?»

Проверить, понимает ли система не только отдельную фразу, но и смысл разговора как последовательности взаимосвязанных речевых актов (USLContext — §4.8; состояние беседы — DLG-L2).

Игровая проверка — только через реальные игровые механизмы, не через изолированный тест модели:

```
PLAYER INPUT → SEMANTIC UNDERSTANDING → EPISTEMIC RESOLUTION → NPC COGNITION → RESPONSE / ACTION → WORLD CONSEQUENCES
```

Проверить:
1. Правильно ли NPC понял сказанное.
2. Сохранился ли источник информации.
3. Попало ли сообщение в соответствующую память.
4. Изменились ли убеждения, если для этого были основания.
5. Не произошло ли необоснованного изменения истины мира.
6. Повлияло ли сообщение на последующие решения NPC.
7. Сохранилась ли причинная цепочка между репликой и последствиями.

**Критерий завершения:** реальные диалоги проходят через общую семантическую систему и дают проверяемые последствия в игровом мире. Дополнительно: сквозная матрица §10 (Этап USL-3) — 4 формулировки одной конструкции × 2+ контура — GREEN по структурной идентичности и эпистемическому различию; повторные реплики не повышают статус утверждения (§7.5 п.5); воспроизводимость — replay-прогон детерминирован; оценена стоимость обработки диалогового корпуса.

### Этап USL-4. Расширение семантических возможностей (только после интеграции)

Переход к развитию того, что оказалось недостаточно развитым **по реальным ошибкам и ограничениям, выявленным на биографиях (USL-2) и диалогах (USL-3)**. Не вводить сложную функциональность только потому, что она теоретически интересна.

Направления-кандидаты (список уточняется отчётами USL-2/USL-3):
- сложная временная логика;
- многоуровневая причинность;
- разрешение неоднозначности;
- сложная кореференция (стык с DLG-2);
- контекст нескольких разговоров;
- длительные обязательства;
- сложные отношения;
- противоречивые свидетельства (стык с BC-5/EPI);
- различение намерения и фактического действия;
- реконструкция событий из неполных сведений;
- согласование разных перспектив NPC;
- понимание длительных исторических процессов.

Каждое расширение обязано иметь: подтверждённую проблему; владельца; потребителя; сценарий использования; тесты; критерий приёмки; оценку вычислительной стоимости. Оформление — собственный ADR (прецедент: закрытый реестр vague-markers — «расширение реестра = ревизия ADR, не молча», `decomposition_normalizer.py:37-39`).

### Этап USL-5. Масштабирование и устойчивость

Проверить работу системы при увеличении:
- количества NPC (6 → 22+ по ростеру roadmap);
- количества биографических событий;
- объёма памяти;
- длины разговоров;
- количества связанных событий;
- количества одновременных игровых процессов.

Определить стоимость обработки и хранения. Использовать существующие механизмы: детерминированную обработку, Fast Path, LLM fallback и кэширование там, где это оправдано (карта «операция → исполнитель» — §8.2). **Не допускать повторного полного анализа всей истории NPC при каждом новом сообщении** (прецеденты: кэш промптов DEBT-CHRONICLE-REPLAY, извлечение якорей regex'ом без LLM, KernelRNG-детерминизм — §8.4).

**Критерий приёмки:** стоимость обработки и хранения измерена на репрезентативном масштабе; детерминизм сохранён (повторный прогон = идентичный результат); LLM-вызовы на реплику не выросли относительно текущей нормы (§8.3 п.3).

### 9.7. Сквозная система проверок (обязательная для всех этапов)

Минимальные группы тестов:

| Группа | Что проверяется |
|---|---|
| Semantic correctness | Правильно ли извлечён смысл |
| Temporal correctness | Правильно ли определены время и длительность |
| Causal correctness | Сохранены ли причины и последствия |
| Entity correctness | Правильно ли определены участники |
| Epistemic correctness | Сохранён ли источник и статус знания |
| Integration correctness | Проходит ли результат по реальным игровым цепочкам |
| Behavioral correctness | Влияет ли информация на последующее поведение |
| Determinism | Воспроизводится ли результат там, где это требуется |
| Performance | Какова стоимость обработки и масштабирования |

Правила (несущие):
- не считать успешный ответ LLM достаточным доказательством корректности; тест должен проверять весь путь до игрового потребителя;
- каждая группа привязывается к существующим гейтам там, где они есть (IPT, T-CCH-*, DLG-GC-*, F5-лаборатория, replay-прогоны) — без создания параллельной системы контроля;
- отчёты USL-2/USL-3 обязаны содержать счётчики по группам (сколько конструкций GREEN / честно UNKNOWN по каждой);
- группы Integration correctness и Behavioral correctness — обязательные для закрытия этапов USL-2 и USL-3 (остальные — по профилю этапа).

### 9.8. Зависимости и согласования с треками (не меняет их статусы)

| Трек/задача | Связь с USL | Точка синхронизации |
|---|---|---|
| CCH-02 (§14, открыт) | автобиографии пойдут через ту же модель смысла; старт — после USL-1/USL-2 (требование: полный корпус как исходный материал) | примечание §0.2; §14 |
| DLG-2/3 (§3.6, открыты) | DLG-L3 «составной вход — полный граф» и DLG-L2 «анафора из контекста беседы» потребляют USLContext/semantic_acts-полноту; DLG-L1 (закрыт) — готовый закон инварианта USL-1 | сверка до закрытия пакетов |
| BC-5 (§3.5, открыт) | Social testimony — приёмник PLAYER_ASSERTION/NPC_SPEECH по §7.2; без общего статуса источника BC-5 не может отличить «вывод из опыта» от «пересказ утверждения» | после фиксации статусов §7.2 (USL-1) |
| NL-1/NL-2 (§12, открыты) | время/identity в записи памяти (NL-1) и BR-конспект (NL-2) читают те же временные структуры; USL не создаёт второй хронологии | сверка до закрытия |
| ARC-NPC (§30, PROPOSED) | NPC-NPC коммуникация — третий потребитель того же фундамента (задел архитектуры) | собственный ADR при подключении |
| MEM (§16) | «семантический слой» памяти (MemoryCrystal, NL-D4) — **после** понимания; граница зафиксирована в §0 | без изменений |

Полная карта отражения USL в дорожной карте — §11.

### 9.9. Риски и меры

| Риск | Мера |
|---|---|
| Второй источник истины | инвариант USL-3 + тест-запреты (USL-1/USL-3) + writer-гарды, уже существующие |
| Регрессия ввода | env-флаг включения адаптера; замки golden-корпусов; быстрый откат (прецеденты RC8/X2-гейтов) |
| Регрессия хроники | «замок равенства» seed до/после (USL-2); нормализатор не трогается |
| LLM не осилит новые конструкции времени | fail-open в честный UNKNOWN (прецедент V.3); детерминированный препарсинг покрывает базовые формы без LLM; неопределённость сохраняется, не маскируется |
| Расползание скоупа (USL «съедает» треки) | таблица §5.3 — различия адаптеров закрыты; новые потребители — только через собственные ADR; развитие — только после корпусов (USL-4) |
| Двойная поддержка маппингов (EntryKind↔USL) | одна таблица маппинга в домене, тест полноты для всех 10 EntryKind |
| «Декоративная интеграция» (схема есть — данных в игре нет) | статусная цепочка со счётчиками по звеньям; игровые проверки USL-2/USL-3 обязательны для закрытия |
| Стоимость корпусных прогонов | батчевые прогоны существующими скриптами; измерение стоимости — часть критериев USL-2/USL-3; кэш промптов (прецедент DEBT-CHRONICLE-REPLAY) |

---

## 10. Задание архитектору (расширено ревизией R1)

### 10.1. Миссия

Обеспечить единое семантическое понимание человеческого языка во всех основных языковых контурах игры и связать смысл с реальным состоянием игрового мира. Идти не через бесконечное наращивание абстрактных возможностей, а через обязательную последовательность: **сначала научить существующие механизмы работать совместно, затем доказать это на реальных биографиях всех NPC, написанных автором ENIGMA, затем доказать на реальных разговорах с NPC, и только после этого расширять возможности системы на основании обнаруженных ограничений.** Не ограничиваться схемой или дополнительным JSON: доказывать интеграцию реальными цепочками вызовов, тестами и игровыми сценариями.

Этапы задания соответствуют этапам плана §9 один к одному (USL-0…USL-5); содержание каждого этапа — §9, ниже — обязанности архитектора и сдаточные артефакты.

### 10.2. Этап USL-0 — архитектурная фиксация и контракты

1. Провести аудит владельцев семантических данных и уже общих контрактов (задачи 1–6 этапа USL-0, §9), сверив с картой §2 — она подтверждена чтением кода, но архитектор обязан перепроверить якоря при касании.
2. Подготовить технический проект интеграции: точный перечень соединяемых механизмов, необходимые изменения DTO/интерфейсов, стратегия включения за флагами, план тестов §9.7, оценка стоимости.
3. Оформить мини-ADR + IMPACT + секцию DTO Registry; получить вердикт Мастера (владелец, границы с MEM/NL/CCH/AG1, приоритет против §0.2).
4. Ограничение этапа: ни одного изменённого py-файла.

### 10.3. Этап USL-1 — интеграция двух языковых контуров

1. Реализовать состав работ этапа USL-1 (домен-контракты + проекторы + общий временной слой + адаптеры + закрытие разрыва утверждений, §9) — только после GO по утверждённому техпроекту.
2. `BiographyDecomposer` и `IntentCompressor` не переписываются (прецедент их детерминизма сохраняется); биографии и ввод обрабатываются через общую семантическую модель, а не через отдельные наборы правил.
3. Доказать контрактный тест совместимости и прохождение данных по реальным цепочкам вызовов (критерий завершения этапа USL-1); сохранить авторский канон и существующие контракты до доказательства безопасности изменений.
4. Отдельно устранить или обосновать разрыв свободных утверждений игрока с эпистемическим контуром (§2.2.4) — решение о минимальном пути (ClaimEvent → EpistemicRecord) или об обоснованной несоединимости подлежит вердикту Мастера.

### 10.4. Этап USL-2 — биографии всех NPC (реальный корпус №1)

1. Взять полный авторский корпус (`docs/Прошлое персонажей черновик/Все.md` + каноны `config/npc/chronicles/*.json` — 6 NPC на момент исследования) как материал проверки общей модели. Не ограничиваться искусственными примерами.
2. Прогнать через модель: сложные временные конструкции (точки, длительности, интервалы, порядок); события и последовательности; возраст и временные якоря; отношения; причинные связи; изменения жизненного положения; намерения и мотивы, если явно есть; отрицания и противоречия; неполные и неоднозначные сведения (белые пятна).
3. Установить фактическую цепочку (архитектор обязан проверить её сам — она может отличаться): `BIOGRAPHY → SEMANTIC REPRESENTATION → CHRONICLE / CANON → NPC COGNITION → MEMORY / BELIEF / PERCEPTION`. Входные точки для проверки: `routes_chronicle.py` (canonize), `chronicle_store.py:411-458`, `npc_loader.py:963-997` (new-game гейт), `chronicle_seeder.py`, `phases/memory.py:43,94`, `npc_tick_pipeline.py:484`.
4. Цель — не структурированный JSON, а реальное использование: память (`EventMemory` с честным `day`), убеждения (`BeliefState`), отношения (`relationship_cache`), знания (`KnowledgeLink`-список знающих — сегодня 0 записей).
5. Отчитаться по статусной цепочке этапа USL-2 для каждой биографии (`SOURCE TEXT → PARSED → NORMALIZED → CANONIZED → SEEDED → COGNITIVELY AVAILABLE → USED IN GAME`) со счётчиками по звеньям; провести игровые проверки этапа USL-2 в F5-лаборатории (включая «NPC не должен знать того, чего он не мог знать» и «разные NPC не получают одинаковое знание автоматически»).
6. Запрет телепатии seed и INV-LLM-NOT-SSOT сохраняются (запреты 4-5 roadmap §13.4); данные корпуса (game_start_age, BELIEF_SEED, KNOWLEDGE_LINK) восполняются как контент автора, не как вывод LLM.
7. Сдать: отчёт покрытия корпуса (какие конструкции модель покрывает, какие честно UNKNOWN), диф-тест сеялки до/после («замок равенства»), оценку стоимости прогона корпуса.

### 10.5. Этап USL-3 — реальные диалоги (реальный корпус №2)

1. Цепочка: `PLAYER INPUT → SEMANTIC UNDERSTANDING → EPISTEMIC RESOLUTION → INTENT / ACTION → WORLD CONSEQUENCES`. Входные точки: `turn_pipeline.py:363-412`, `phase_1_input.py:125-388`, `claim_event_subscriber.py:89-268`, гейты readiness/физики.
2. Согласовать материал с владельцем DLG/Мастером: существующие корпусы (`dlg0_golden_corpus.py`, `ue0_baseline_corpus.py`), записи тестовых взаимодействий или специально подготовленные разговоры; включить разговорные последовательности, в которых смысл зависит от предыдущих реплик — не только короткие команды.
3. Прогнать проверки этапа USL-3 (§9): 16 категорий речи, 5 эталонных фраз в связке, 7 игровых проверок по полному конвейеру до WORLD CONSEQUENCES.
4. Биография и игровой ввод не имеют независимых определений времени, событий, причинности и отношений при одинаковом смысле. Различаются: адаптеры, источники, контракты принятия истины, последующие потребители.
5. Свободный `ASSERT` игрока имеет путь к статусу «утверждение с источником» (ClaimEvent → EpistemicStore), но не к канону (§7.2 — тест-запрет); реплики NPC — симметрично (DLG-L1).
6. Сдать: сквозную матрицу (4 формулировки §6.5 × 2+ контура — структурная идентичность + эпистемическое различие), отчёт по 7 игровым проверкам, replay-прогон (детерминизм), оценку стоимости диалогового корпуса.

### 10.6. Этап USL-4 — развитие возможностей

1. Собрать реестр реальных ошибок и ограничений из отчётов USL-2/USL-3; приоритизировать направления этапа USL-4 (§9) по нему, а не по теоретической интересности.
2. Каждое расширение — с подтверждённой проблемой, владельцем, потребителем, сценарием использования, тестами, критерием приёмки и оценкой вычислительной стоимости; оформление — отдельный ADR.
3. Утверждение приоритетов — вердикт Мастера (точка архитектурного утверждения §11.4).

### 10.7. Этап USL-5 — масштабирование и устойчивость

1. Спроектировать и измерить поведение при росте: количества NPC, биографических событий, объёма памяти, длины разговоров, связанных событий, одновременных игровых процессов (перечень этапа USL-5, §9).
2. Разделить исполнителей по карте §8.2: детерминированное извлечение известных конструкций; сложное семантическое понимание через LLM; формализацию результатов обычным кодом; проверку контрактов; применение результатов существующими игровыми механизмами. Не создавать предположения, что вся речь каждого NPC постоянно обрабатывается большой нейросетью.
3. Доказать отсутствие повторного полного анализа всей истории NPC при каждом новом сообщении (замок на стоимость повторного сообщения).
4. Сдать: отчёт стоимости обработки/хранения на репрезентативном масштабе + замки детерминизма.

### 10.8. Ограничения (запреты, несжимаемы)

1. Не изменять production-код до USL-0; не переписывать `BiographyDecomposer` и `IntentCompressor`; не создавать параллельные хранилища истины и новую систему памяти; не предлагать замену существующих механизмов без доказательства необходимости; не считать, что LLM обязана обрабатывать каждую фразу; не считать успешную декомпозицию признаком корректной интеграции; не объявлять механизмы работающими без тестов или трассировки; не пропускать этапы последовательности (USL-3 не начинается до критерия завершения USL-2; USL-4/USL-5 — до завершения корпусных проверок).
2. Каждое предложение новой сущности — с ответами на шесть вопросов (§3.5 — образец заполнения).
3. Один факт — одно место: изменения статусов задач треков — вне мандата USL.

### 10.9. Артефакты, которые архитектор обязан сдать

ADR + IMPACT + утверждённый техпроект (USL-0); `app/domain/usl.py` + проекторы + резолвер времени + адаптеры + тест-запрет канонизации утверждения игрока + замки корпусов ввода (USL-1); отчёт покрытия корпуса + диф-тест сеялки + статусные цепочки биографий (USL-2); сквозная матрица + отчёт диалоговых проверок + replay-прогон (USL-3); реестр ограничений + ADR по каждому расширению (USL-4); отчёт масштабирования + замки детерминизма (USL-5); обновление DTO Registry; строка в MUTATIONS на каждую сессию.

---

## 11. Трек USL в дорожной карте ENIGMA (добавлено ревизией R1)

### 11.1. Место среди треков

USL — поперечный архитектурный фундамент (cross-cutting), не игровая функция и не вертикальный слой канонического порядка (§0.1 roadmap). В дорожной карте он отражён как «смежный фундамент» при треках-потребителях (§3 AG1, §3.6 DLG, §12 NL, §13 CCH, §14 CCH-02) и строкой в карте документов (§1.1) — это соответствует существующим прецедентам горизонтальных контуров (COV §17, EPI §19): они не являются ступенями очереди §0.2, а обслуживают её ступени. Включение USL в очередь §0.2 отдельной ступенью — не полномочие этого документа; решение — за Мастером (USL-0). Предлагаемая формулировка для того решения: USL-0/USL-1 как гейт-условие старта CCH-02 (вместо примечания-зависимости) и как обязательная сверка для закрытия DLG-2/3, NL-1/NL-2 и BC-5; работающие задачи других треков при этом не останавливаются.

### 11.2. Статус

PROPOSED до вердикта Мастера по Этапу USL-0 (все существующие ссылки roadmap это фиксируют). После вердикта этапы USL-1…USL-5 исполняются по общим правилам ступеней §0.2 (контрактный гейт + линтеры + IPT + запись в MUTATIONS) с собственными ADR-пометками; владелец — Ветвь А (вердикт USL-0).

### 11.3. Зависимые треки (карта зависимостей)

| Трек/задача | Тип зависимости | Точка синхронизации |
|---|---|---|
| CCH-02 (§14; §0.2) | последовательность: автобиографии — второй контур той же семантической модели | старт извлечения — после USL-1/USL-2 |
| DLG-2/3 (§3.6, открыты) | контрактная сверка: анафора/составной вход затрагивают те же категории смысла (USLContext/USLEvent/USLTimeExpression) | не создавать независимых определений; сверка до закрытия пакетов |
| BC-5 (§3.5, открыт) | приёмник: Social testimony требует общего статуса источника | после фиксации карты статусов §7.2 (USL-1) |
| NL-1/NL-2 (§12, открыты) | потребление: временные структуры и события USL; BR остаётся derived-проекцией §12.1.7 | сверка с USL-моделью времени до закрытия |
| ARC-NPC (§30, PROPOSED) | третий потребитель того же фундамента | собственный ADR при подключении |
| MEM (§16) | граница: «семантический слой» памяти — после понимания (§0 документа) | без изменений |
| CCH (§13) | базовый контур: канонизация и сеялка — единственные writer-каналы; трек не переписывается | инвариант USL-3 |

**Анти-фрагментация (несущее требование):** ни один трек не развивает временные, причинные или контекстные механизмы независимо от общего семантического фундамента. Действующие формулировки ссылок roadmap («обязаны сверяться с инвариантами USL-1…USL-6», «не создавать независимых определений этих категорий») это покрывают; при пересмотре перечисленных треков сверка повторяется. Одновременно ни одна работающая задача других треков не останавливается без доказанной необходимости (решение — за Мастером).

### 11.4. Этапы, последовательность выполнения, критерии закрытия

| Этап | Содержание | Критерий закрытия | Точка архитектурного утверждения |
|---|---|---|---|
| USL-0 | архитектурная фиксация и контракты | ADR + IMPACT + DTO Registry + утверждённый техпроект | вердикт Мастера (гейт всего направления) |
| USL-1 | интеграция двух языковых контуров | контрактный тест совместимости + данные в реальных цепочках + 0 регрессий | GO по техпроекту; приёмка владельцем (Ветвь А) |
| USL-2 | биографии всех NPC (корпус №1) | статусная цепочка до USED IN GAME + игровые проверки + «замок равенства» сеялки | отчёт покрытия → вердикт о переходе к USL-3 |
| USL-3 | реальные диалоги (корпус №2) | полный конвейер до WORLD CONSEQUENCES + 7 игровых проверок + сквозная матрица | отчёт → вердикт по приоритетам USL-4 |
| USL-4 | развитие возможностей | по каждому расширению: проблема/владелец/потребитель/сценарий/тесты/критерий/стоимость | отдельный ADR на каждое расширение |
| USL-5 | масштабирование и устойчивость | измеренная стоимость + сохранённый детерминизм | отчёт → решение Мастера о включении в очередь §0.2 |

Последовательность выполнения корпусов — строго линейная (USL-2 после USL-1; USL-3 после USL-2); USL-4/USL-5 не начинаются до завершения корпусных проверок. Параллельность с другими треками — по Anti-Race Protocol (§11.1.1 Устава).

### 11.5. Согласованность существующих ссылок roadmap (проверено ревизией R1)

| Место roadmap | Содержание ссылки | Вердикт R1 |
|---|---|---|
| §0.2 (примечание CCH-02) | полный корпус — исходный материал модели (USL-3); старт после USL-1/USL-3 | **исправлено аддитивно**: «(USL-3)»→«(USL-2)», «USL-1/USL-3»→«USL-1/USL-2» — синхронизация с нумерацией этапов R1 |
| §1.1 (карта документов) | строка USL-документа | согласовано; описание уточнено аддитивно (последовательность R1, трек §11) |
| §3 (AG1) | сверка задач трека с инвариантами USL-1…USL-6; BC-5 | согласовано, без изменений |
| §3.6 (DLG) | DLG-L1 — частный случай инварианта USL-1; сверка DLG-2/3 до закрытия | согласовано, без изменений |
| §12 (NL) | NL-1/NL-2 потребляют временные структуры USL; вторая хронология запрещена | согласовано, без изменений |
| §13 (CCH) | трек не переписывается; гейт USL-0 | согласовано, без изменений |
| §13.6 (таблица направлений) | «(USL-4)» после «временная модель … без замены контрактов» | **уточнено аддитивно**: «(инвариант USL-4)» — развод нумерации этапов USL-0…USL-5 и инвариантов USL-1…USL-6 |
| §14 (CCH-02) | старт извлечения после этапов USL-1/USL-3 | **исправлено аддитивно**: «USL-1/USL-3»→«USL-1/USL-2» — синхронизация с нумерацией этапов R1 |

Противоречий новой последовательности, кроме нумерации этапов, не обнаружено: ни одна ссылка не требовала остановки работающих задач и не навязывала другим трекам иную очередность; ситуации независимого развития временных/причинных/контекстных механизмов действующие ссылки не создают (см. §11.3).

### 11.6. Границы изменений roadmap этой ревизией

Статусы задач, чекбоксы, версия документа (v4.12-draft) и формулировки существующих ступеней не менялись. Изменения дорожной карты ограничены аддитивными: (а) синхронизация нумерации этапов в двух USL-примечаниях (§0.2 CCH-02, §14 CCH-02); (б) уточнение «(USL-4)» → «(инвариант USL-4)» в §13.6; (в) уточнение описания строки §1.1. Детали — §11.5.

---

## 12. Приложение: сводка роевого исследования (требования финального отчёта)

**Подтверждено кодом (ключевое):** обе цепочки §2.1/§2.2 целиком; все строки таблиц §2.1–§2.2; разрыв свободного ASSERT (`claim_event_subscriber.py:104-105` — «обычный dialogue без вектора — no-op»); отсутствие временных полей ввода (проверено по лексиконам, промпту, DTO и grep `temporal_marker_on_action`); dormant-состояние act_consumer/white_spot_registry/origin_projection(обратный ход)/age_math API; пустота BELIEF_SEED/KNOWLEDGE_LINK в 6 канонах.

**Архитектурные предложения (не подтверждены, требуют утверждения):** все контракты §4–§6 (USLUnit и вложенные), оба адаптера §5, карта статусов §7.2, план §9 в последовательности ревизии R1 (интеграция → биографии всех NPC → реальные диалоги → развитие → масштабирование) со сквозной системой проверок §9.7, задание архитектору §10, трек и карта зависимостей §11. Ничего из этого не существует в коде.

**Существующие механизмы, переиспользуемые без изменения:** `AgeAnchor`/`extract_age_anchors_typed`; `EntityRef` + `registry_builder`; `Proposition/SpeechAct/SocialIntent`; `ClaimEvent`/`EpistemicRecord`/`BeliefRevisionEngine`; `KnowledgeChannel`; `CauseRef/CauseCandidate/NpcCausalBelief`; `KnowledgeLink`-инвариант; `age_math`-формулы; GBNF-детерминизм; семантическая библиотека (прецедент модульности); гейты readiness/физики; канализация хроники (canonize+ConsistencyService).

**Проблемы, которые USL не решает (честный список):** coreference-резолв в диалогах (DLG-2; развитие — направление USL-4); отключённые `quoted`-гейты (подключаются в USL-1, но политика — за владельцем AG1); мёртвые NL-D1/D3/D5-каналы наррации; пустой корпус BELIEF_SEED (нужен авторский контент — USL-2 делает его измеримым); связь «historical day ↔ runtime tick» (только R2-основа); BC-2…BC-13 (отдельный трек); memory-хранение канала знания (ревизия EventMemory — вне USL).

**Решения, требующие вердикта Мастера:** утверждение направления и владельца (USL-0); место USL в §0.2 (новая ступень или гейт-условие — формулировка предложена §11.1); судьба `act_consumer` (подключить/удалить — решение внутри USL-1); подъём `KnowledgeChannel` в runtime-DTO (ревизия frozen-моделей); расширение реестра `USLPredicate`; доступ ввода к `CanonicalRegistry`; приоритет USL относительно Ступеней §0.2; закрытие или обоснованная несоединимость разрыва свободных утверждений (USL-1, §10.3 п.4); критерий полноты биографического корпуса USL-2 (6 канонов хроник vs будущий комплект автобиографий CCH-02); состав канонических источников диалогового корпуса USL-3; приоритеты направлений USL-4 (после отчётов корпусов); вердикт по точке версии roadmap (в этом документе статусы и версия не менялись).

**Статус утверждённости этапов (ревизия R1):** утверждённое направление — сама последовательность «INTEGRATION → NPC BIOGRAPHIES → REAL DIALOGUES → SEMANTIC DEVELOPMENT → SCALE», статусная цепочка биографий (этап USL-2), система проверок §9.7 и вычислительные ограничения §8; содержание этапов USL-1…USL-5 в production — требует дополнительного технического проектирования (техпроект USL-0) и отдельного GO по каждому этапу.

---

## 13. Статус реализации (S380, 2026-11-02)

### 13.1. Что реализовано

| Этап | Артефакт | SHA | Тесты | Статус |
|---|---|---|---|---|
| USL-1.1 | `backend/app/domain/usl.py` + `test_usl_types.py` | `fe50b3be` | 21 | ✅ GREEN |
| USL-1.2 | `backend/app/services/chronicle/biography_adapter.py` + `test_usl_biography_adapter.py` | `fe50b3be` | 29 | ✅ GREEN |
| USL-1.3 | `backend/app/services/input/interactive_language_adapter.py` + `test_usl_interactive_adapter.py` | `fe50b3be` | 22 | ✅ GREEN |
| USL-1.4 | `backend/app/services/events/claim_event_subscriber.py:104-105` (патч) + `test_usl_free_assert.py` | `8caefebc` | 10 + 16 регрессий | ✅ GREEN |
| **Итого** | 5 новых файлов + 1 патч production | 2 коммита | **98 тестов** | ✅ 0 регрессий baseline |

### 13.2. Что доказано (с оговоркой)

**На конкретных тестовых данных:**
- USL-1: одинаковый смысл из биографии и ввода даёт совместимые `events` и различные `epistemics.source_kind` (сквозной тест §6.5 GREEN)
- USL-2: PLAYER_ASSERTION ≠ AUTHOR_CANON (тест-запрет GREEN)
- USL-3: 0 правок TruthState/канона/EventMemory writes (архитектурно — USLUnit transient, subscriber не имеет ref на TruthState)
- USL-6: повторный прогон = идентичный `unit_id` и `claim_id` (детерминизм GREEN)

**Оговорка (вердикт Мастера, уточнение 2):** тесты доказывают свойства на проверенных данных (orm.json 53 entries, конкретные фразы ввода). Полная семантическая эквивалентность всех возможных биографий и пользовательских высказываний требует корпусной проверки USL-2/USL-3 (следующие этапы).

### 13.3. Что осталось (pending)

USL-1 целиком закрыт. Следующий этап — USL-2 (см. §14).

| Этап | Содержание | Статус |
|---|---|---|
| USL-1.5 | CanonicalRegistry bridge — прокинуть `registry_builder.CanonicalRegistry` в input-контур. Не разрушать fallback. | ✅ CLOSED (S410) — `intent_compressor.py:432-455`, `_ensure_registry_cache()` + `_resolve_npc_by_name canonical-first`; `test_usl_canonical_bridge.py` (7 tests); §5.4 «Орму» автора = «Орму» игрока доказан |
| USL-1.6 | Regression + Activation — финальные тесты, решение по флагам, DTO Registry, MUTATIONS | ✅ CLOSED (S410) — IMPACT R3 + DTO Registry §15 + MUTATIONS S410; 0 флагов (additive); IPT 54/0/0 |
| **USL-1 итого** | 6 подэтапов (1.1–1.6), 2 коммита S380 + 1 коммит S410 | ✅ ALL GREEN |

### 13.4. Вердикт Мастера USL-0 (6 вопросов Q1-Q6 + 3 поправки)

| Вопрос | Вердикт | Реализация |
|---|---|---|
| Q1 USLUnit — новый домен-тип | GO | ✅ `domain/usl.py`, frozen, stdlib only |
| Q2 USLTimeExpression — 6 форм | GO (поправка: 6 форм, не расширять AgeAnchorKind) | ✅ POINT/DURATION/INTERVAL/ORDER/RELATIVE/UNKNOWN |
| Q3 Адаптеры раздельные, не парсеры | GO | ✅ BiographyAdapter + InteractiveLanguageAdapter |
| Q4 Флаги — минимально необходимые | Изменить (не вводить заранее) | ✅ 0 флагов (additive + 1 правка без флага) |
| Q5 Тесты (5 направлений + уточнения) | GO (замок равенства на реальных данных; PLAYER_ASSERTION→EpistemicStore разрешён) | ✅ 98 тестов |
| Q6 Переход к USL-1 — итеративно | GO (без повторного GO) | ✅ USL-1.1→1.4 итеративно |

**Поправки к анализу архитектора:**
1. `extract_age_anchors_typed` НЕ считать готовым универсальным экстрактором — проверить на длительностях/относительных конструкциях (USL-1.5+)
2. Не ограничивать ASSERT временными маркерами — исследовать полноценный путь свободных утверждений (USL-1.4 — выполнено: все free ASSERT через гейты)
3. `act_consumer` и `WhiteSpotRegistry` не трогать — out of scope USL-1 (выполнено: не тронуты)

### 13.5. ADR и IMPACT

- **ADR-O-437** в атласе: `docs/ADR (Architecture Decision Records).md` (строка 845)
- **IMPACT:** `docs/audits/ADR-O-437_IMPACT.md` (обновлён R2 — USL-1.5/1.6; R3 — DTO Registry §15)
- **ЗАВЕЩАНИЕ:** Письмо №14 (S380)

---

## 14. Статус USL-2 — корпусный прогон (S411, 2026-11-03)

> **Статус этапа:** USL-2 IN PROGRESS — PARSED→CANONIZED доказаны на корпусе; SEEDED-фаза обнаружила 3 системных разрыва; переход к COGNITIVELY AVAILABLE → USED IN GAME передан преемнику.

### 14.1. Что доказано GREEN (USL-проекция на корпусе)

Корпус: 6 NPC (`config/npc/chronicles/*.json`), 363 entries суммарно. Прогон через `biography_to_usl` (`backend/app/services/chronicle/biography_adapter.py:318`).

| Критерий | Результат | Статус |
|---|---|---|
| Замок равенства (entries → USLUnit) | 363==363, 6/6 NPC | ✅ GREEN |
| USL-2 (source kind = AUTHOR_CANON) | 363/363, 0 non-author | ✅ GREEN |
| USL-6 (детерминизм, повторный прогон) | 6/6 NPC, идентичные `unit_id` | ✅ GREEN |
| Temporal match (canon `historical_age` == USL `temporal`) | 1==1 | ✅ GREEN (консервативность) |
| USL-5 (text_span провенанс) | 0 units without span | ✅ GREEN |

**Архитектурный вывод:** `biography_to_usl` — pure function, 1:1 mapping. Ни одна entry не потеряна, ни одна не добавлена, ни одна не повысилась в статусе. **USL-1.2 доказан на реальном корпусе, не на демонстрационных примерах.** Условие «оговарки» §13.2 (вердикт Мастера уточнение 2) — корпусная проверка — выполнено и дала GREEN.

Карта покрытия по NPC:

| NPC | entries | gs_age | canon_age | usl_temp | rel | caus | age_lost |
|---|---|---|---|---|---|---|---|
| blacksmith_orm | 63 | – | 0 | 0 | 10 | 0 | 6 |
| guard_borko | 66 | – | 0 | 0 | 12 | 0 | 7 |
| maid_lusya | 59 | **14** | **1** | **1** | 9 | 0 | 4 |
| merchant_goran | 58 | – | 0 | 0 | 10 | 0 | 7 |
| tavern_keeper_tornin | 78 | – | 0 | 0 | 9 | 0 | 7 |
| thief_shadow | 39 | – | 0 | 0 | 5 | 0 | 2 |
| **TOTAL** | **363** | 1/6 | 1/363 | 1/363 | 55 | 0 | **33** |

USLPredicate distribution корпуса: `asserts: 112, has_effect: 110, has_trait: 98, believes: 34, lives_at: 8, desires: 1`. Все 6 EntryKind доменов покрыты.

### 14.2. Что обнаружено RED (SEEDED-фаза)

Прогон `chronicle_seeder.build_seed_*` на maid_lusya (единственный NPC с `game_start_age=14`): из 59 entries до когнитивных структур дошло только 11 EventMemory. Остальные 48 entries либо отклонены seeder'ом, либо не проверены.

```
SOURCE TEXT → PARSED → NORMALIZED → CANONIZED → SEEDED → COGNITIVELY AVAILABLE → USED IN GAME
   21 пункт    59       59          59          11/59       ?                      ?
               ✅        ✅          ✅         ⚠️ РАЗРЫВ   ⏳ (преемник)          ⏳ (преемник)
```

**Три системных разрыва** зафиксированы в ТЗ `docs/TZ_USL2_SEEDED_GAPS.md` и переданы владельцам CCH:

| № | Разрыв | Симптом | Корневая причина |
|---|---|---|---|
| 1 | RELATIONSHIP → 0 | 9/9 RELATIONSHIP maid_lusya отклонены: «связь на неразрешённую сущность» | `object_id` пустой; декомпозиция не резолвит `target_hint` через CanonicalRegistry (USL-1.5 закрыт только для input-контура) |
| 2 | EFFECT trauma → 0 imprints | 3/3 trauma-EFFECT отклонены: «без triggers» | payload не содержит `triggers`; декомпозиция не извлекает их (промпт + GBNF) |
| 3 | BELIEF_SEED — API drift + belief_type | `build_seed_beliefs(doc)`, не `(npc_id, doc)`; seeder ожидает `payload['belief_type']` в реестре `BeliefType` | нужна археология payload BELIEF_SEED — есть ли `belief_type` |

Разрывы 1-3 — **блокеры для закрытия USL-2**: без них SEEDED-фаза не проходит. Фикс — работа владельцев CCH (декомпозиция, seeder, реестр), не USL (вердикт Мастера Q3: «адаптеры не парсеры»).

### 14.3. Дополнительные находки (не блокеры)

| Находка | Описание | Материал для |
|---|---|---|
| A. temporal 1/363 (0%) | Только 1 entry имеет structured `historical_age`; 33 entries имеют возрастной маркер в `text_span`, но пустой temporal | USL-1.5+ (Temporal Extractor для biography-контура) — отдельная задача |
| B. game_start_age 1/6 | Только `maid_lusya=14`; у 5 NPC `game_start_age=null` → seeder даёт `SENTINEL_DAY=-1000` | Контентная работа автора (заполнить 5 полей) |
| C. KNOWLEDGE_LINK = 0 | Во всём корпусе нет `knows` predicate; `KnowledgeChannel` (WITNESSED/TOLD/OVERHEARD/DEDUCED) не используется | Будущее развитие CCH |
| D. TRAIT_SEED не сеется | `build_full_seed` осознанно пропускает TRAIT_SEED — ждёт Character Calibration ADR | Не разрыв, осознанное решение |

### 14.4. Статусная цепочка USL-2

```
SOURCE TEXT → PARSED → NORMALIZED → CANONIZED → SEEDED → COGNITIVELY AVAILABLE → USED IN GAME
   6 NPC        363      363          363         11/59*     ⏳ (преемник)          ⏳ (преемник)
   ✅           ✅        ✅           ✅         ⚠️ РАЗРЫВ
```

\* 11/59 — только для maid_lusya. Для остальных 5 NPC SEEDED-фаза не проверена из-за блокера `game_start_age` (находка B).

**USL-2 доказал:** архитектура USL (`biography_to_usl`) выдерживает полный корпус. Разрывы обнаружены **не в USL**, а в downstream-контурах (декомпозиция, seeder, реестр). Это и есть ценность USL-2 как измерителя: он сделал видимыми три системных разрыва, которые ранее были скрыты за «декомпозиция успешна».

### 14.5. Что осталось (pending — преемнику)

| Этап | Содержание | Зависимость |
|---|---|---|
| USL-2.SEEDED | После фиксов разрывов 1-3 (TZ_USL2_SEEDED_GAPS.md) — перепрогон `scripts/usl2_seeded_lusya.py`, замок SEEDED GREEN | Фиксы CCH (разрывы 1-3) |
| USL-2.COGNITIVE | Проверить, что EventMemory с честным `day` доходит до NPC (`MemoryManager.apply`, `WorkingMemory`) | USL-2.SEEDED GREEN |
| USL-2.USED | F5-лаборатория: «NPC реагирует на Орма иначе», «Люся знает про тайный ход», «NPC не знает того, чего не мог знать» | USL-2.COGNITIVE GREEN |
| USL-2 закрытие | Отчёт покрытия корпуса + замок равенства сеялки до/после + оценка стоимости прогона | USL-2.USED GREEN |
| USL-3 | Реальные диалоги — следующий этап §9 | USL-2 закрыт |

### 14.6. Артефакты USL-2 (S411)

| Файл | Назначение | Статус |
|---|---|---|
| `scripts/usl2_pilot_lusya.py` | Пилот — maid_lusya через `biography_to_usl` (59→59 GREEN) | read-only, можно перепрогонять |
| `scripts/usl2_corpus_all.py` | Корпус — 6 NPC через `biography_to_usl` (363==363 GREEN) | read-only, можно перепрогонять |
| `scripts/usl2_seeded_lusya.py` | SEEDED-фаза — maid_lusya через `chronicle_seeder` (11/59, 3 разрыва) | read-only; перепрогон после фиксов разрывов |
| `docs/TZ_USL2_SEEDED_GAPS.md` | ТЗ на 3 разрыва SEEDED-фазы (передано CCH) | OPEN — ждёт вердикта Мастера |

### 14.7. ADR и IMPACT (без изменений)

- **ADR-O-437** — ACTIVE (USL-1 целиком закрыт; USL-2 IN PROGRESS)
- **IMPACT:** `docs/audits/ADR-O-437_IMPACT.md` — ожидает обновления R4 после закрытия USL-2
- **ЗАВЕЩАНИЕ:** Письмо №14 (S380); Письмо №15 (S411) — будет написано при закрытии серии
- **MUTATIONS:** S411 — ожидает записи при закрытии серии (max перепроверить перед записью)