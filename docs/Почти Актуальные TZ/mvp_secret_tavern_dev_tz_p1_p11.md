# ТЗ: «ЗАМЫКАНИЕ КОНТУРА» — разработка MVP «Таверна тайн» (P1–P11)

**Объект:** ENIGMA (Bloodloom), версия `0.5.3.9.9`, ветка `V.0.5.3.9.9_Потребности_1`
**Основание:** археологический аудит `download/mvp_secret_tavern_gap_map.md` (16 разделов, вердикт «Вариант B», MVP ~40%) + машиночитаемый `download/secrets_manifest.json`
**Архитектурное решение заказчика:** не строить систему секретов с нуля и не добавлять «17 квестов и 17 триггеров», а замкнуть Truth → Knowledge → Discovery в один причинный контур, соединив существующие органы.
**Статус документа:** проект к исполнению. Все ссылки `файл:строка` верифицированы по распакованному срезу `Enigma-V.0.5.3.9.9_-_1`.
**Правило стиля правок:** каждый P-этап — точечные мосты между существующими узлами; ни один этап не создаёт новой подсистемы уровня «графового движка» или «второй системы знаний».

---

## 0. ФАЗА 0: КОНТРАКТ MVP (инварианты, выше которых нет приоритетов)

Единственный фундаментальный контракт, из которого выводятся все 11 этапов:

> **SECRET ≠ DIALOGUE.** Секрет не «выясняется потому, что LLM произнесла удачную фразу». Он существует как объективный факт мира; NPC знают разные его части; действия игрока порождают наблюдения; система **детерминированно** определяет, какое знание стало доступно игроку; и только затем LLM превращает это знание в человеческую речь.

Целевая цепочка (минимальная версия философии ENIGMA):

```
WORLD TRUTH (TruthState, SSOT)
    ↓  seed (P1)
NPC KNOWLEDGE (EventMemory с secret_id)
    ↓  retrieval (P4)
PLAYER ACTION / OBSERVATION (DialogueQuery, P3)
    ↓  deterministic decision (P5)
DETERMINISTIC KNOWLEDGE TRANSFER (DisclosureOutcome)
    ↓  bridge (P6)
PLAYER EPISTEMIC STATE (0/1/2)
    ↓  event
DISCOVERY
    ↓
JOURNAL / UI (P8)  ←→  PROGRESS API (P9)
    ↓
ENDGAME (P11)
```

### Инварианты I1–I7 (приёмка любого PR = соответствие им)

| # | Инвариант | Следствие для кода |
|---|---|---|
| I1 | **Движок решает — LLM говорит.** Факт открытия секрета может породить только детерминированный Python-код. | Ни один новый call-site `mark_discovered` не может принимать на вход сырой вывод LLM. Аудит (§12 gap map) подтвердил: граница уже соблюдена архитектурно — её нельзя расширить. |
| I2 | **LLM никогда не парсится обратно для discovery.** | PropositionMatcher (`legacy_bridge.py:19-56`) снимается с каузальной дежурства (P6). Парсинг реплик допускается только как телеметрия/compat-путь внутри Bridge. |
| I3 | **TruthState — объективная реальность; знание NPC — субъективное владение; игрок по умолчанию не знает.** Три разных онтологических слоя, связанных идентичностью `secret_id`. | Truth: `tornin_debt` = «долг 1200 золотых». Knowledge: Торнин знает, Тень знает частично. Player: не знает. Машинно различимо (P1). |
| I4 | **Нет «правильных вопросов» и кодовых фраз.** Ни одна конкретная формулировка игрока не является триггером reveal. | Запрещено `if "в чём твой секрет" in text: reveal()`. Только семантический субъект вопроса + состояние NPC (P3→P5). |
| I5 | **Знать ≠ обязан рассказать.** NPC вольны лгать, уходить от темы, давать намёк. | Обязательная ветка решений DENY/REDIRECT/HINT/PARTIAL/REVEAL (P5); knowledge retrieval не равен disclosure. |
| I6 | **Одна поверхность — один мост.** Dialogue, eavesdrop, DM-нарратив, visual_cue — все источники знания проходят через единственный Discovery Bridge. | Запрещено добавлять четвёртый/пятый call-site `mark_discovered` в обход Bridge (сейчас их 3 — `npc_confession_parser.py:109`, `action_consequence_compiler.py:117-129`, `:157-166`). |
| I7 | **Прогресс игрока персистентен и наблюдаем.** UI, фронтенд-тесты и pytest читают одно и то же состояние. | PlayerEpistemicState сериализуется в сейв и экспортируется ровно одним API (P9, P11). |

---

## 1. ЦЕЛЕВОЙ КОНТУР И МАТРИЦА «ФАЗА → ЭТАП»

```
                    ┌─────────────────────────────┐
                    │ TRUTH: truth_state_tavern.json │  🟢 есть (17 секретов, SSOT)
                    └──────────────┬──────────────┘
                                   ↓ P1+P2 (seed + reconciliation)
                    ┌─────────────────────────────┐
                    │ KNOWLEDGE GRAPH (плоский):  │  EventMemory.secret_id +
                    │ SECRET → KNOWS/SAW/HEARD → NPC │  initial_holders оживают
                    └──────────────┬──────────────┘
                                   ↓ P3+P4 (subject + retrieval)
PLAYER ──► SOCIAL ACTION (ASK/ACCUSE/PRESSURE… DialogueQuery)
                                   ↓ P5 (willingness)
                    ┌─────────────────────────────┐
                    │ NPC DECISION: DENY/REDIRECT/ │
                    │ HINT/PARTIAL/REVEAL          │  детерминированный скоринг
                    └──────────────┬──────────────┘
                                   ↓ P6 (Discovery Bridge)
PLAYER EVIDENCE → Observation → CLUE(1) → IDENTIFIED(2)
                                   ↓ P7 (verbalization)
                    LLM получает FACTUAL OUTCOME и пишет реплику
                                   ↓ P8+P9
                    JOURNAL / UI-сигнал / progress API
                                   ↓ P10+P11
                    17/17 TEST → EXIT → ENDGAME
```

### Матрица соответствия (философия заказчика ↔ этапы ТЗ ↔ находки аудита)

| Фаза (видение) | Этап | Закрываемая находка аудита |
|---|---|---|
| 0. Модель MVP | §0 (инварианты) | §12 (LLM-граница подтверждена — сохранить) |
| 1. Секреты как объекты знания | P1 | §2.3 `initial_holders` мёртв; `EventMemory` без `secret_id` (npc_state.py:214-239) |
| 2. Secret Knowledge Graph (минимум) | P2 | §3.4 — 6 рассинхронов канон↔конфиг; секреты вне канона |
| 3. Не «правильные вопросы», а Dialogue Act | P3 | §4.2 — `Ask(NPC, subject)` NOT FOUND; fast path без диалоговых лемм |
| 4. Discovery Bridge | P4, P6, P7 | §4.3 (секреты не в промпте), §6.2 (лотерейный matcher), §13.B.3-B.4 (eavesdrop/RCE в обход) |
| 5. Discovery ≠ полное признание (уровни) | P6 | §6 (сейчас бинарный `mark_discovered`) |
| 6. NPC не обязаны рассказывать | P5 (+T5.0) | §3.3 «трещины под давлением» мертвы (memory_manager.py:451,487); §4.4 author_notes-анти-reveal |
| 7. След знания игрока | P6 (epistemic trace) | §13.C.10 (CONTRADICTS не эмитится), §7.2 (вкладки-заглушки) |
| 8. Журнал — часть ядра | P8 | §7.2 «Гипотезы»/«Факты» — заглушки (analysis_renderer.py:151,154), «Убеждения» получают пустой массив (world_snapshot_builder.py:96-98 → snapshot.py:114-138) |
| 9. UI-сигнал открытия | P8 | §7.1 UI-фидбек NOT FOUND |
| 10. Не делать «тестовый режим» | P10 | §9.3 — MockProvider random (mock_provider.py:144-170), нет прогресс-API, нет оркестратора |
| — (порядок P11) | P11 | §8.1 ExitTrigger мёртв, порог 12.5 продублирован (game_screen.py:946-947); §8.3 прогресс не персистентен; end screen «X / 16» (end_screen_renderer.py:47) |

**Перекрёстная ссылка на старое именование:** в аудите минимальный путь назывался P1–P7. Соответствие: аудит-P1 → P1+P2; аудит-P2 → P7 (инъекция) + P4; аудит-P3 → P6 (matcher выведен из каузальной цепи); аудит-P4 → P8+P9; аудит-P5 (eavesdrop) → P6; аудит-P6 (exit+персистентность) → P11; аудит-P7 (тест) → P10. Новое относительно аудита: P3 (семантический акт), P5 (decision), уровни 0/1/2, журнал как эпистемический интерфейс.

---

## 2. АНТИ-ЦЕЛИ (запрещено данным ТЗ)

Это жёсткие ограничения скоупа, а не пожелания. Ревью каждого PR обязано проверять их нарушение.

1. ❌ **Procedural mystery generation** — генерация новых секретов на лету. 17 секретов канона — фиксированный MVP-полигон.
2. ❌ **Новый огромный graph engine** — P2 формализует то, что уже лежит в каноне (`initial_holders`, `participants`, `origin_events`, `known_by`), плоскими связями. Никаких Neo4j-подобных структур, никакой общей дедукции.
3. ❌ **Отдельный AI detective system / LLM judge** — LLM не оценивает, «понял ли игрок». Оценку делает EvaluationEngine (`evaluation_engine.py:19-76`), детерминированный.
4. ❌ **NLP ради NLP** — P3 не строит синтаксический парсер русского языка. Максимум: леммы fast-path + извлечение субъекта после предлогов + словарь тем.
5. ❌ **17 индивидуальных квестов и 17 триггеров** — discovery решается общей моделью (знание × готовность × контекст), а не per-secret скриптами. Per-secret данные канона — только содержание, темы и чувствительность.
6. ❌ **Scripted dialogue trees** — реплики не ветвятся по деревьям; LLM вербализует outcome.
7. ❌ **Новая память NPC** — используется существующий `EventMemory`/`narrative_cache`; P1 лишь добавляет поле-идентичность.
8. ❌ **Отдельный «тестовый режим»** — тест идёт почти настоящим игровым путём через API (P10). `truth.mark_discovered("secret_1")` в тесте — не тест игры.
9. ❌ **Список правильных вопросов** — см. I4. Словарь тем канона (P3) — это индекс субъектов («караван», «гильдия», «долг»), а не триггерные фразы; совпадение темы даёт retrieval, но не reveal.
10. ❌ **Удаление author_notes / голосовых архетипов** — они остаются материалом вербализации и стилем NPC. Меняется только то, что решение о раскрытии больше не зависит от свободного текста «запретов» (см. P5, обоснование — §4.4 аудита: канон прямо антагонистичен discovery).

---

## 3. ОБЩИЕ ПРАВИЛА РЕАЛИЗАЦИИ

- **SSOT остаётся SSOT.** `config/canon/truth_state_tavern.json` — единственный источник содержания секретов. Новые per-secret поля (`topics`, `sensitivity`, `silhouette`) добавляются в этот же файл, а не в боковые конфиги.
- **Frozen dataclasses.** `Secret` (`models/truth_state.py:26-60`) и `EventMemory` (`models/npc_state.py:214-239`) — frozen; новые поля добавляются с дефолтами, чтобы старые сейвы и конфиги грузились без миграции данных (кроме SQLite-колонки в P1).
- **Каждый этап заканчивается тестом.** Имя теста = `test_p<N>_<название>.py` в `backend/tests/`. Этап без зелёного теста не считается выполненным.
- **Детерминизм проверяется повторным прогоном.** Любая функция с словом `decide/resolve/match` в имени обязана давать одинаковый результат на одинаковых входах (тест-дубль прогона в P10).
- **Никаких новых call-site `mark_discovered`** вне Discovery Bridge (I6). Текущие три (аудит §6.1) переводятся под контроль Bridge в P6.

---

## P1. SECRET IDENTITY — «кто знает что» становится машинно проверяемым

**Фаза:** 1. **Приоритет:** абсолютный; без P1 остальные этапы бессмысленны.

### Текущее состояние (доказано аудитом)

- `EventMemory` (`backend/app/models/npc_state.py:214-239`) содержит `is_secret` (:236), `known_by` (:237), `hidden_from` (:238) — и **не содержит `secret_id`** (grep по файлу = 0). Сериализация `:311-313` и восстановление `:1045-1048` поля тоже не знают.
- В SQLite (`memory/sqlite_store.py:150-174`, таблица `event_memories`) колонки `secret_id` нет — связь «память ↔ канон» невозможна физически.
- `initial_holders` (`models/truth_state.py:33`) парсится (`truth_state_loader.py:35`) и не читается никем — 0 потребителей после загрузчика (аудит §2.3).
- Канон и NPC-конфиги — два параллельных вселенных (аудит §3.1-3.2): NPC «знает» текст секрета из своего `origin_event`, но ни движок, ни LLM не знают, что это секрет канона №X.

### Что делаем

1. **Поле-идентичность.** В `EventMemory` добавить `secret_id: Optional[str] = None`; прокинуть в `to_dict`/`from_dict` (`:311-313`, `:1045-1048`) и в SQLite-схему (`ALTER TABLE event_memories ADD COLUMN secret_id TEXT NULL` + индекс). Дефолт `None` гарантирует обратную совместимость старых сейвов.
2. **Сеялка канона.** Новая функция `seed_canon_knowledge(truth_state, npc_states)` (размещение: `services/npc/npc_loader.py` рядом с `_convert_origin_events:489-526`, вызов — в цепочке инициализации новой игры, точка `:674`):

```python
for secret in truth_state.secrets.values():
    for holder_id in secret.initial_holders:
        npc = npc_states[holder_id]
        # дедуп: если в конфиге уже есть secret-origin_event — пометить, а не дублировать
        if any(m.secret_id == secret.secret_id for m in npc.narrative_cache):
            continue
        npc.narrative_cache += (EventMemory(
            secret_id=secret.secret_id,
            summary=secret.canonical_truth,
            importance=secret.importance,
            is_secret=True,
            known_by=tuple(secret.initial_holders),
            hidden_from=("player",),
        ),)
```

3. **Запрос знаний.** Минимальный детерминированный API над памятью (метод на `MemoryManager` или утилита): `who_knows(secret_id) -> list[npc_id]` и `known_secrets(npc_id) -> list[secret_id]`. Это **не** новая система знаний — это фильтр по полю поверх существующего `narrative_cache`.

### Точки входа

`models/npc_state.py:214-239,311-313,1045-1048` · `memory/sqlite_store.py:150-174` · `services/npc/npc_loader.py:489-526,674` · `services/memory/memory_manager.py` (методы-запросы).

### Не делаем

Вторую Knowledge-систему, belief-пропозиции для NPC, инференс («Тень может вывести коррупцию Борко») — частичное владение знанием выражается уже сейчас через `known_by`/`hidden_from` и круг участников секрета.

### Критерии приёмки

- Тест `test_p1_secret_identity.py`: для каждого из 17 секретов `who_knows(sid)` == `initial_holders` из канона (17 ассертов) — «Борко знает Secret #5» отвечает машиной.
- Старый сейв (без `secret_id`) загружается без ошибок; новая игра сеет ровно 17 holders-памятей (по числу позиций в `initial_holders`, не больше).
- Ни одна реплика LLM не изменилась (P1 не трогает промпты) — smoke-тест диалога идентичен.

---

## P2. CANON RECONCILIATION — одна карта 17 секретов

**Фаза:** 2. **Приоритет:** сразу после P1 (без него чек не формулируем).

### Текущее состояние

Аудит §3.4 зафиксировал **6 рассинхронов** канон↔конфиг (таблица H/E/e):

1. `lusya_basement`: Тень и Торнин знают по конфигу Люси (`known_by`), но не holders канона.
2. `tornin_debt`: Тень — holder канона, но в `shadow.json` нет памяти о долге.
3. `tornin_basement`: Люся — holder, но в `lusya.json` нет своей secret-памяти.
4. `orm_tornin_order`: Торнин — holder, памяти нет.
5. `shadow_guild_membership`: у Тени нет EventMemory-носителя вообще (только backstory).
6. `lusya_orm_borko`: Орм — holder, своей secret-памяти нет.

Плюс: конфиги содержат секреты **вне канона** («командир обещал повышение» — `borko.json:150-161`; «аудит гильдии» — `goran.json:136-147`), невидимые для TruthState; `notes` в `village_relations.json:140` содержат готовые эпистемические факты, которые никто не парсит.

### Что делаем

1. **Правило старшинства:** TruthState — SSOT (I3). Для каждого из 6 рассинхронов — одно из двух решений, фиксируемое в PR-описании:
   - канон прав: дорисовать/убрать знание в NPC-конфиге (например, Тень получает secret-память о долге — это же требуется сюжетом шантажа Горана);
   - конфиг прав: расширить `initial_holders`/`participants` канона (например, знание Тени/Торнина о подвале — сделать их holders с уровнем «слышал»).
2. **Секреты вне канона** не удаляются: им присваиваются `secret_id` вида `out_of_canon_*` и флаг `mvp_relevant: false`, либо они документируются как «цвет, вне MVP-контура». Запрещено молча оставлять их без идентичности — иначе воспроизведём нынешнюю ситуацию.
3. **Автоматический чек** `backend/tests/test_p2_canon_sync.py` (и скрипт `scripts/check_canon_sync.py` для запуска вне pytest):
   - каждый holder каждого секрета существует среди NPC и имеет EventMemory с этим `secret_id` (после P1);
   - каждая EventMemory с `is_secret=True` имеет `secret_id` ∈ канона или `out_of_canon_*` реестра;
   - `participants` ⊆ живые NPC; у каждого секрета непустой `initial_holders`;
   - (опционально, без парсинга семантики) длина `notes`-фактов не проверяется — только их наличие.
4. **Знания-наблюдения чужих секретов** (`e` в таблице аудита — «известно по чужой памяти») помечаются уровнем владения: `holder` (знает сам) vs `aware` (слышал). Для MVP достаточно булева поля в сеялке P1 — без полноценного графа KNOWS/SAW/HEARD (анти-цель №2).

### Критерии приёмки

- Чек зелёный на всех 17: «у каждого секрета есть машина проверки носителей» — карта «Who knows it?» совпадает с каноном на 100%.
- Ни один секрет не потерял носителя; все 6 рассинхронов имеют зафиксированное решение в PR.
- Чек входит в CI (pytest-маркер smoke) — рассинхрон больше не может появиться незаметно.

---

## P3. DIALOGUE SEMANTIC ACT — Ask(NPC, about=subject) вместо Talk(NPC)

**Фаза:** 3. **Принцип:** это **не** «команды игрока» и **не** NLP — это семантический тип социального действия, который позже ляжет в основу любви, лжи, шантажа и политики за пределами таверны.

### Текущее состояние

- `IntentSemanticField` имеет `target` (к кому) и `proposition` (генерируется только для ATTACK/THREATEN — `intent_compressor.py:313-315`); поля «о чём/о ком спрашиваю» нет (аудит §4.2: NOT FOUND).
- Fast-path компрессора не содержит диалоговых лемм («спросить», «расскажи») — любой чистый вопрос уходит в slow path (LLM), при его недоступности — `UNCERTAIN` → деградация в DIALOGUE.
- Косвенные упоминания корректно исключаются из targeting («о/об/про/к» — `player_target_extractor.py:654-672`) — вопрос «Ты слышал о Борко?» не переключает цель. Это правильное поведение — сохранить.
- Тема диалога — keyword-метки плоского словаря (`topic_extractor.py:74-114`), с секретами не связаны.

### Что делаем

1. **Реестр актов** (enum `SocialAct`): базовые `TALK`, `ASK_SELF`, `ASK_OTHER`, `ASK_EVENT`, `ASK_RUMOR`, `ASK_SECRET`, `ACCUSE`, `PRESSURE`, `THREATEN`, `BLACKMAIL`. Расширение существующего intent-слоя (`domain/intent.py`, `intent_profiles.py`), а не новая подсистема.
2. **Структура запроса** — dataclass:

```python
@dataclass(frozen=True)
class SubjectRef:
    type: str            # "npc" | "event" | "topic" | "unknown"
    ref: Optional[str]   # npc_id / secret_id / topic_key

@dataclass(frozen=True)
class DialogueQuery:
    speaker: str         # player
    target: str          # npc_id (уже решает PlayerTargetExtractor)
    act: SocialAct
    subject: Optional[SubjectRef]
```

3. **Извлечение subject (минимальное):**
   - после предлогов `о|об|про|насчёт|зачем|почему` взять следующую NP-группу (2-3 токена) как candidate;
   - матч candidate по `name_forms` NPC-конфигов (механика уже есть — `player_target_extractor.py:645-677`) → `SubjectRef("npc", npc_id)`;
   - иначе — матч по **словарю тем канона**: новое per-secret поле `topics` в `truth_state_tavern.json` (например, `borko_negligence: ["караван", "досмотр", "ворота", "труп"]`). Это **индекс субъектов, а не триггерные фразы** (I4): совпадение темы даёт retrieval-кандидата, но решение о раскрытии принимает P5, а не текст вопроса.
4. **Диалоговые леммы fast-path** (`intent_compressor.py`, словарь `_ACTION_LEMMAS:226-254`): добавить `спросить, расспросить, рассказ|поведать, знаешь, известно, видел, слышал, услышал, почему, зачем, кто такой, что за` → `ACT=ASK`. Цель: чистый вопрос не должен умирать в UNCERTAIN при недоступном LLM.
5. **Роутинг актов:** ASK/ASK_* → диалоговое ядро (как сейчас); ACCUSE/PRESSURE/BLACKMAIL → существующие гейты (`action_consequence_compiler.py:117-129` уже обрабатывает BLACKMAIL+secret_id — сохранить совместимость, но secret_id теперь приходит из P4/P6, а не из лотереи).

### Точки входа

`services/input/intent_compressor.py` (леммы, извлечение) · `domain/intent.py` / `intent_profiles.py` (поля) · `services/spatial/player_target_extractor.py:645-677` (subject) · `services/npc/topic_extractor.py` (связка тем) · `services/game_loop/__init__.py:2132-2171` (передача дальше).

### Не делаем

Синтаксический разбор предложений, семантические эмбеддинги, классификатор на нейросети, «меню вопросов». Вопрос «В чём твой секрет?» получает `act=ASK_SECRET, subject=unknown` — и **этого достаточно**: пустой subject → retrieval пуст → NPC отвечает уклончиво по своему состоянию (P5), а не по кодовой фразе.

### Критерии приёмки

- Тест-таблица `test_p3_dialogue_query.py` — 10 контрольных фраз заказчика дают корректные `(target, act, subject)`:

| Фраза | target | act | subject |
|---|---|---|---|
| «Что ты знаешь о Люсе?» | текущий NPC | ASK_OTHER | npc:maid_lusya |
| «Ты видел что-нибудь странное?» | текущий NPC | ASK_EVENT | unknown |
| «Почему Горан нервничает?» | текущий NPC | ASK_OTHER | npc:merchant_goran |
| «Расскажи про тот караван» | текущий NPC | ASK_EVENT | topic:караван → borko_negligence |
| «Кто платит тебе деньги?» | guard_borko | ASK_OTHER | unknown (topic:деньги → borko_bribe кандидат) |

- Фраза без вопроса («наливаю пиво») не порождает ASK.
- При выключенном slow-path LLM вопрос всё равно классифицируется fast-path (леммы).

---

## P4. KNOWLEDGE RETRIEVAL — детерминированный поиск «что NPC знает по теме»

**Фаза:** 4 (первая половина). **Принцип:** retrieval — чистая функция над памятью; он ничего не решает о раскрытии.

### Текущее состояние

Retrieval знаний по предмету отсутствует: вопрос доходит до LLM только сырым текстом в STM-блоке промпта (`dialogue_executor.py:208-225`), знаний о предмете у системы нет (аудит §4.2-4.3).

### Что делаем

```python
@dataclass(frozen=True)
class KnowledgeItem:
    secret_id: str
    possession: str      # "holder" | "aware"   (из P2)
    origin: str          # summary EventMemory — что именно знает
    relevance: float     # 1.0 direct / 0.7 participant / 0.5 topic

def retrieve_knowledge(npc_state, query: DialogueQuery,
                       truth: TruthState) -> list[KnowledgeItem]:
    hits = []
    for m in npc_state.narrative_cache:
        if m.secret_id is None:
            continue
        s = truth.secrets[m.secret_id]
        if query.subject and query.subject.type == "npc" \
           and query.subject.ref in s.participants:
            hits.append(KnowledgeItem(m.secret_id, _possession(m, npc_state),
                                      m.summary, 0.7))
        elif query.subject and _topic_match(query.subject.ref, s, truth):
            hits.append(KnowledgeItem(m.secret_id, ..., 0.5))
    return sorted(hits, key=lambda k: -k.relevance)
```

Иерархия релевантности: точное совпадение secret_id (если subject — секрет) > participant-матч > topic-матч. Несколько секретов на одну тему возвращаются списком — сортировка по `relevance`, затем по `importance`.

### Точки входа

Новый модуль `services/npc/knowledge_retrieval.py` (или метод MemoryManager) · потребители: P5 (decision), P7 (промпт).

### Не делаем

Fuzzy-фантазии над текстом канона: матчинг только по структурным полям (`participants`, `topics`), не по `canonical_truth`. Это принципиально отличает retrieval от старого лотерейного матчера.

### Критерии приёмки

- «Спросить Борко про караван» → `[borko_negligence (1.0)]`; «Спросить Тень про Люсю» → `[shadow_suspects_lusya]`; «Спросить Горан про караван» → `[]` (он не знает) — пустой retrieval честен и не подменяется фасадом.
- Тест `test_p4_retrieval.py`: ≥12 покрытий на выборке «NPC × тема» из матрицы аудита §3.4.

---

## P5. DISCLOSURE DECISION — NPC решает: LIE / HINT / REVEAL

**Фаза:** 6. **Принцип:** знание + мотивация + давление + отношения + риск → детерминированное решение. Секрет — не кнопка «спросил → получил». Для MVP не строим «психологический космос» — используем существующие факторы.

### Текущее состояние

- Механика «секрет трескается под давлением» существует и детерминирована — `memory_manager.py:451` (`discovery_check`), `:487` (`assess_secrets_under_pressure`), 11 юнит-тестов с формулами давления — но **мертва в production**: вызывается только из `backend/tests/test_discovery_mechanics.py` (аудит §3.3, §9.2).
- Факторы готовности уже живут в коде: trust/fear/stress-дельты (`reaction_subscriber.py:71-85`), crystallized beliefs о собеседнике (в промпте — `dialogue_executor.py:187-201`), `base_trust`+`nature` из village_relations (`npc_loader.py:194-261`), voice-архетипы (`config/canon/voice_archetypes/*.yaml`), importance секрета (`truth_state_tavern.json`).
- `author_notes` NPC прямо запрещают признания («если спросить про тот случай — замолчишь» — `borko.json`; «не раскроешь даже под угрозой» — `orm.json`; «переводишь тему» — `tornin.json` — аудит §4.4). Сегодня решение о раскрытии фактически отдано свободному тексту запретов — это и делает 16 секретов недостижимыми.

### Что делаем

1. **T5.0 — ревизия мёртвой механики давления (отдельная задача, заказчик просил проверить).** Вердикт по аудиту: `assess_secrets_under_pressure` имеет годные формулы (давление × чувствительность), но живёт не в том слое (memory) и не имеет входов диалога. Решение: **переиспользовать формулы как один из входов** нового decision (не выбрасывать), вынеся скоринг в новый модуль — memory остаётся хранилищем, решение — в `services/npc/disclosure_decision.py`.
2. **Контракт решения:**

```python
@dataclass(frozen=True)
class DisclosureOutcome:
    secret_id: str
    level: str            # DENY | REDIRECT | HINT | PARTIAL | REVEAL
    stance: str           # "ashamed" / "defensive" / "scared" / "smug" ... — для вербализации
    fraction: float       # 0..1 — глубина раскрытия (PARTIAL), для промпта

def decide_disclosure(npc_state, item: KnowledgeItem,
                      query: DialogueQuery, ctx: DecisionContext) -> DisclosureOutcome
```

3. **Входы (только существующие факторы):** trust к игроку; fear/stress (текущие дельты); pressure от акта (ASK_SECRET > ACCUSE > PRESSURE > ASK); relationship/history встреч (`npc_npc_context`); personality (voice_archetype + nature); чувствительность секрета (новое per-secret поле `sensitivity: 0..1` в каноне, дефолт = `importance`); контекст свидетелей (публичность — стыдливые секреты в толпе дороже).
4. **Скоринг — детерминированный, пороговый:**

```
will = trust*0.3 + (1 - sensitivity)*0.2 + relationship*0.2
       + pressure*0.2 + fear_leverage*0.1 - secrecy_penalty(archetype)
REVEAL  := will >= T_reveal  и pressure достаточен
PARTIAL := will >= T_partial
HINT    := will >= T_hint
REDIRECT:= subject упомянут, но секрета в knowledge нет → разговор о смежном
DENY    := иначе (в т.ч. пустой retrieval при act=ASK_SECRET)
```

Пороги `T_*` — константы модуля (не magic numbers в теле), калибруются плейтестом P10. Результат должен быть **воспроизводим**: одинаковые входы → одинаковый outcome (правило детерминизма §3).
5. **author_notes переводятся в слой вербализации** (P7): они описывают, **как** NPC отказывается/уходит (стиль DENY/REDIRECT), но больше не блокируют REVEAL, когда движок решил. Это снимает конфликт «канон против discovery» (аудит §4.4) без удаления контента.
6. **Ложь (LIE):** в MVP выражается как DENY + stance («уверенно врёт») — без отдельной ветки фабрикации пропозиций (анти-цель: не строим belief-модель лжи).

### Критерии приёмки

- Таблица решений `test_p5_disclosure.py`: фиксированные входы → фиксированный outcome (двойной прогон — идентично).
- REVEAL достижим: high trust + high pressure + низкая sensitivity → REVEAL для любого из 17 секретов (иначе секрет недостижим — провал по определению MVP).
- DENY по умолчанию: нейтральный игрок с нулевым доверием не получает ни одного секрета за один вопрос.
- author_notes больше не appear в decision-логе (grep: decision-модуль не читает `author_notes`).

---

## P6. DISCOVERY BRIDGE — центральный недостающий орган

**Фаза:** 4+5+7. **Принцип:** PLAYER ACTION + NPC KNOWLEDGE + CONTEXT → DETERMINISTIC KNOWLEDGE OUTCOME. Никакого string-матчинга выводов LLM. Плюс уровни знания: 0 UNKNOWN / 1 CLUE / 2 IDENTIFIED.

### Текущее состояние

- Discovery = «LLM сказал слова → string matcher → может быть Secret»: `PropositionMatcher.match` (`legacy_bridge.py:34-56`) сравнивает **канонический текст секрета с шаблоном предиката** («украл взял кража») при пороге 0.2 — практически лотерея (аудит §6.2); fallback — word-overlap ≥3 (`npc_confession_parser.py:81-87`), keywords у 1/17 (`:77-80`).
- Три call-site `mark_discovered` вне единого контура: `npc_confession_parser.py:109`, `action_consequence_compiler.py:117-129` (BLACKMAIL), `:157-166` (DIALOGUE).
- Eavesdrop пишет подслушанное в журнал и **останавливается** (`npc_dialogue_subscriber.py:105-108`); RCE-извлечённые реплики тоже не проходят парсер (аудит §13.B.3-4).
- Discovery бинарный; журнала уровней нет; CONTRADICTS-evidence не эмитится никем (аудит §13.C.10).

### Что делаем

1. **PlayerEpistemicState** (новый минимальный стейт — не PlayerCausalModel):

```python
class PlayerEpistemicState:
    levels: dict[str, int]          # secret_id -> 0/1/2
    observations: list[Observation] # «Борко резко замолчал...»
    def raise_level(self, sid, to_level, source_event) -> Optional[LevelChangeEvent]
```

2. **Discovery Bridge** — единственная точка превращения игровых событий в знание игрока:

```python
class DiscoveryBridge:
    def process(self, surface: SurfaceEvent) -> list[EpistemicUpdate]:
        # surface.kind: DIALOGUE_OUTCOME | EAVESDROP | DM_NARRATIVE | VISUAL_CUE
        #   DIALOGUE_OUTCOME несёт готовый DisclosureOutcome (P5) — текст реплики НЕ анализируется
        #   EAVESDROP/DM_NARRATIVE несут {speaker, subject_hint, content_class}
        # mapping:
        #   REVEAL          -> level 2 (IDENTIFIED) + observation
        #   PARTIAL         -> level 1 (CLUE, enriched) + observation
        #   HINT            -> level 1 (CLUE) если ещё 0
        #   DENY/REDIRECT   -> observation only
        #   EAVESDROP с secret-меткой (см. ниже) -> level 1..2 по полноте реплики
```

3. **Eavesdrop/RCE через Bridge:** в `npc_dialogue_subscriber.py` после `append_journal` (`:105-108`) вместо вызова парсера признаний — эмит `SurfaceEvent(EAVESDROP, ...)`. Как реплика получает secret-метку без парсинга текста? Через **источник реплики**: NPC-реплики, порождённые из DisclosureOutcome (P7), уже несут `secret_id` в DTO задачи диалога — Bridge доверяет происхождению, а не строкам. Реплики «цвета» (LLM-импровизация без outcome) discovery не порождают — этим закрывается и лотерея, и ложные срабатывания `shadow_first_kill` (аудит §10, досье 14).
4. **Наследование старых путей (compat, без каузальности):**
   - `confession_keywords` остаются **быстрым фильтром телеметрии** (ловим «случайное» произнесение для логов/аналитики), но не источником discovery;
   - `PropositionMatcher` помечается deprecated, из `dialogue_executor.py:142-151` вызов парсера заменяется на эмит SurfaceEvent;
   - BLACKMAIL/DIALOGUE+secret_id в `action_consequence_compiler.py` получают secret_id от P3/P4 (структурно), идут через тот же Bridge.
5. **Событие уровня:** `LevelChangeEvent` (0→1, 1→2) — публикуется в снапшот тика; подписчики: журнал (P8), toast (P8), телеметрия. Обратный уровень (2→1) в MVP не нужен (CONTRADICTS-механика — за пределами контура, помечено «позже»).
6. **Уровень ≠ текст.** Переход 0→1 генерирует автотекст-наблюдение («? Борко замолчал, когда речь зашла о караване») из шаблонов по stance/level — это материал для вкладки «Гипотезы» (P8), не фантазия LLM.

### Точки входа

Новый `services/player_cognition/discovery_bridge.py` · `services/execution/dialogue_executor.py:142-151` (замена вызова) · `services/events/npc_dialogue_subscriber.py:105-108` · `services/player_cognition/action_consequence_compiler.py:117-129,157-166` · `models/truth_state.py` (mark_discovered вызывается ТОЛЬКО из Bridge).

### Не делаем

Inference-модель на 17 загадок, вывод одних секретов из других (relations-граф 20 связей остаётся телеметрией), PlayerCausalModel, обратный Contradicts-пайплайн.

### Критерии приёмки

- Полная цепь «DialogueQuery → retrieval → decision → outcome → уровень» проходит **без единого сравнения текста реплики с каноном** (тест-инвариант: monkeypatch на SequenceMatcher — не вызывается в диалоговом тике).
- Негативный тест: 100 случайных реплик LLM-цвета → 0 ложных discovery (анти-лотерея).
- `shadow_guild_membership` открывается через общий путь (keywords-сценарий переезжает в scripted-verbalizer-тест), а не через особую ветку.
- Уровни живут между тиками; повторный REVEAL того же секрета не меняет уровень (идемпотентность).

---

## P7. LLM VERBALIZATION — «движок решил — LLM сказал»

**Фаза:** 4 (хвост) + контракт вербализации. **Принцип:** LLM получает уже решённый факт и пишет его человеческим языком; LLM не понимает, «что произошло», — он понимает, **что ему сказали произошло**.

### Текущее состояние

- Промпт NPC собирается из 5 полей: name, backstory, voice_profile, author_notes, emotional_nuance (`phases/post_decision.py:137-146`, дубль `dialogue_executor.py:228-241`). Знания/секреты NPC в промпт **не попадают** (аудит §4.3) — LLM импровизирует «на тему», не зная деталей (суммы, имена), поэтому признания случайны.
- `VerbalizationContext.suppressed_secrets` заполняется (`npc_tick_pipeline.py:1104-1106`) и **не читается ни разу** (0 читателей поля).
- `author_notes` большинства NPC — анти-reveal (аудит §4.4).

### Что делаем

1. **Блок FACTUAL OUTCOME в промпте** (сборка в `post_decision.py` / `dialogue_executor.py`):

```
ФАКТИЧЕСКИЙ ИСХОД РЕПЛИКИ (определила система, не ты):
- Ты {не говоришь ничего важного | даёшь туманный намёк | рассказываешь часть | признаёшься} в: {secret_id → канон-текст, УРОВЕНЬ детализации по fraction}
- Твоё состояние при этом: {stance}
- Ты НЕ раскрываешь: остальное содержание твоих секретов
Говори в манере {voice_profile}. {author_notes как стилевые ограничения}
```

2. **Инъекция знаний — дозированная:** секреты NPC попадают в промпт только когда retrieval дал hit и decision принял outcome ≥ HINT (не вываливать весь список секретов при каждом «как дела» — иначе LLM сольёт всё в первой реплике). Пассивный минимум: одна строка «Помни: ты скрываешь {N} вещей, не упоминай их без причины» — читает наконец `suppressed_secrets`.
3. **Дозирование PARTIAL:** `fraction` из DisclosureOutcome ограничивает, какая часть канон-текста доступна вербализации (первые предложения summary / без имён и сумм). Реализация — простое усечение канон-текста по fraction, без семантики.
4. **Гарантия I1/I2:** вывод LLM уходит игроку через `ResponseValidator` (`dialogue_executor.py:261-267`) и **не анализируется** на предмет discovery (P6 уже обеспечил). Даже если LLM «сболтнёт» канон дословно вне outcome — discovery не засчитается (это деградация вербализации, а не механизм).
5. **author_notes — только стиль:** переформулировать их роль в промпте: «Как ты говоришь», а не «Что ты решаешь». Содержимое конфигов не переписывается (анти-цель №10) — меняется инструкция-обёртка.

### Точки входа

`services/phases/post_decision.py:137-146` · `services/execution/dialogue_executor.py:169-258` · `services/verbalization/verbalization_context.py:83` (поля уже есть) · `services/npc/npc_tick_pipeline.py:1104-1106` (поставщик).

### Критерии приёмки

- Тест `test_p7_verbalization.py`: промпт при REVEAL-outcome содержит канон-текст секрета и stance; при DENY — не содержит содержания секрета.
- Инвариант: удаление LLM из цепи (подмена заглушкой) **не меняет** эпистемическое состояние игрока — меняется только текст реплики. Это и есть формулировка «LLM только превращает знание в речь».
- Smoke: у 17/17 секретов REVEAL-промпт собирается без KeyError (все secret_id разрешимы).

---

## P8. JOURNAL + UI — журнал как интерфейс эпистемического состояния

**Фаза:** 8+9. **Принцип:** журнал — не лог реплик, а интерфейс того, что игрок заметил / предполагает / установил. Игрок обязан видеть факт зачёта.

### Текущее состояние

- Серверный журнал — FIFO 100 реплик `{speaker, text}` (`player_avatar_service.py:400-415`), инъекция в снапшот `game_loop/__init__.py:1390-1391,1639-1663`.
- Фронт: вкладки по J (`analysis_renderer.py:31-154`): «Наблюдения» — живая; «Гипотезы» — заглушка «У вас пока нет гипотез.» (`:151`); «Факты» — заглушка (`:154`); «Убеждения» — рендерит `player_beliefs`, но backend вычисляет (`world_snapshot_builder.py:96-98`) и **не передаёт** в `WorldSnapshotDTO` (`domain/snapshot.py:114-138,249`) — вкладка мертва.
- UI-фидбек открытия NOT FOUND (аудит §7.1); чеклиста «СЕКРЕТЫ ТАВЕРНЫ [✓]/[?]» нет.

### Что делаем

1. **Серверные payload'ы** (в `world_snapshot_builder.py` + `domain/snapshot.py`):
   - `secrets_progress: {identified: int, total: 17, silhouettes: [{key, label}]}` — silhouettes только для undiscovered;
   - `facts: [entries]` — level 2 (автотекст канона-факта по шаблону «✓ …»);
   - `hypotheses: [entries]` — level 1 (автотекст наблюдений «? Возможно, …» из Bridge);
   - `player_beliefs` — починить передачу уже вычисленного поля (одна строка в конструктор DTO).
2. **Канон-поле `silhouette`** per secret (например, `tornin_debt: "Кто-то задолжал опасным людям"`; `borko_negligence: "Кто-то скрывает вину за гибель"`). Не раскрывает владельца и содержание — это UX-подача, вопрос отдан на усмотрение реализации, но правило одно: **названия и канон-текст undiscovered секретов игроку не показываются**.
3. **UI-сигнал перехода** (Фаза 9): при `LevelChangeEvent` в снапшоте тика появляется флаг `new_fact: {secret_silhouette, level}`; фронт (`game_screen.py`) показывает стилистически подходящий сигнал — «НОВЫЙ ФАКТ УСТАНОВЛЕН» (баннер/toast; toast-механика в редакторе уже есть как референс — `map_editor/editor_core.py:954`). Одноразовость: флаг гасится после показа.
4. **Вкладка «Секреты»**: «✓ Выяснено: N · ? Неизвестно: M» + список силуэтов и установленных фактов. Это единственное место, где игрок видит счёт 17.

### Точки входа

`services/integration/world_snapshot_builder.py:96-98` · `domain/snapshot.py:114-138,249` · `frontend/analysis_renderer.py:31-154` · `frontend/game_screen.py` (toast) · `config/canon/truth_state_tavern.json` (silhouette).

### Критерии приёмки

- Тест контракта снапшота: после REVEAL-тика `facts` содержит новую запись, `secrets_progress.identified` +1, `new_fact` установлен однократно.
- Фронт-тест: вкладки «Гипотезы»/«Факты»/«Секреты» рендерят непустые данные; silhouette не содержит подстрок канон-текста секретов (тест-утечка).
- Прогресс виден **в той же сессии** (не только на end screen).

---

## P9. PROGRESS API — один источник для фронта и тестов

**Текущее состояние.** `discovered_secrets` наружу отдаёт только телеметрия `GET /api/health` → `mvp_health.discovered_secrets_count` (`routes.py:236`) — её потребляет HTML-дашборд, не игрок и не тесты. Игровые каналы (`world_snapshot`, `GET /world_state`, idle_tick) per-secret прогресса не содержат (аудит §7.3).

### Что делаем

```python
# api/routes.py — рядом с /game/end_screen:663 и /game/finalize:673
@router.get("/game/progress/{campaign_id}")
def secret_progress(campaign_id: str) -> dict:
    st = _epistemic_state(campaign_id)          # P6
    return {
        "total": 17,
        "identified": [sid for sid, lv in st.levels.items() if lv == 2],
        "clues":      [sid for sid, lv in st.levels.items() if lv == 1],
        "levels": st.levels,
    }
```

- Источник — ровно один: PlayerEpistemicState (I7). `TruthState.discovered_secrets` синхронизируется Bridge'ом (level 2 ⇒ mark_discovered) и остаётся счётчиком для EvaluationEngine — два списка не могут разойтись, потому что пишет их один код.
- Потребители: вкладка «Секреты» (P8, может читать снапшот), pytest-оркестратор (P10), отладочный рентген.

**Критерии приёмки:** тест читает прогресс после каждого scripted-действия (P10 зависит от этого эндпоинта); `levels` согласован с `end_screen.secrets_identified` для той же сессии.

---

## P10. 17/17 DETERMINISTIC PLAYTHROUGH — главный гейт

**Фаза:** 10. **Принцип:** тест идёт почти настоящим игровым путём: NEW GAME → ACTION → GAME LOOP → NPC RESPONSE → DISCOVERY → JOURNAL → EXIT → ENDGAME. Никаких `truth.mark_discovered("secret_1")` — это не тест игры.

### Текущее состояние

- `MockProvider` (`llm/mock_provider.py`) использует `random.choice` (`:144,153,161,170`) и keyword-эвристики — **не детерминирован** и не умеет признаний; в production заблокирован (`factory.py:74-84` RuntimeError).
- Тестовый harness жив: 118 тестов, fixture `mock_model_router` (`conftest.py:122-133`); инъекция действий через `POST /api/game/action` (`routes.py:824`), тики (`:499`), смена сцены с позицией (`:1243-1255`) — движение к двери инъекцией возможно.
- Существующие «сквозные» тесты либо без тиков (`canary/test_full_playthrough.py:35`), либо с ручной инжекцией секрета (`scripts/test_full_playthrough_end_screen_non_empty.py:67-71`) — 17/17 сегодня невозможен (аудит §9.3).

### Что делаем

1. **ScriptedLlmProvider** (не «отдельный тестовый режим» — тот же интерфейс Provider, подмена в fixture роутера):

```python
class ScriptedLlmProvider(Provider):
    """Детерминированный вербализатор: DisclosureOutcome -> реплика."""
    def get_response(self, prompt: PromptEnvelope) -> str:
        outcome = prompt.metadata["disclosure_outcome"]   # кладёт P7-сборка
        return self.TEMPLATES[outcome.level].format(
            stance=outcome.stance,
            content=truncate(outcome.canonical_text, outcome.fraction))
    TEMPLATES = {
        "REVEAL":  "Ладно... {content} Да, это я. Доволен?",
        "PARTIAL": "Хорошо, часть правды: {content} Но остальное — не твоё дело.",
        "HINT":    "Ты всё правильно понимаешь... (взгляд в сторону)",
        "DENY":    "Не знаю, о чём ты. ({stance})",
        "REDIRECT":"Пиво остынет. Потом поговорим.",
    }
```

Тестируется каузальность, а не температура LLM. Существующий `mock_model_router` fixture — точка подмены.
2. **Оркестратор 17 сценариев** `backend/tests/e2e/test_17_of_17_playthrough.py`:

```python
client.post(f"/api/game/new/{camp}")
for s in canon.secrets:                                  # 17 сценариев
    r = client.post("/api/game/action", json=scripted_action_for(s))
    client.post(f"/api/game/idle_tick/{camp}")
    prog = client.get(f"/api/game/progress/{camp}").json()
    assert s.secret_id in prog["identified"]             # level 2 через реальный путь
client.post(f"/api/game/{camp}/scene_state", json={"y": 15})   # выход (backend-детект из P11)
end = client.get(f"/api/game/end_screen/{camp}").json()
assert end["secrets_identified"] == 17 and end["score"] == 170
```

`scripted_action_for(s)` строит фразу по `topics` секрета («Расскажи про тот караван» для borko_negligence) + прогрев-действия для trust/pressure (угощение, N реплик) — путь **социальный**, не магический вызов.
3. **Негативные гейты:**
   - `test_negative_wrong_subject.py`: 17 «мимо-вопросов» (тема другого NPC) → 0 discovery;
   - `test_negative_random_chat.py`: 100 нейтральных реплик → 0 ложных discovery (регрессия лотереи);
   - `test_determinism.py`: полный прогон дважды → идентичные `levels` и score.
4. **Калибровка порогов P5** вписывается сюда: если сценарий не доезжает до REVEAL — правятся `T_*`, не тест.

**Критерии приёмки:** тест зелёный без seed-настроек; время прогона разумное (без real-LLM); CI-статус обязателен.

---

## P11. EXIT → EVALUATION — выход из таверны и честный финал

**Текущее состояние.**
- `ExitTrigger.check_exit` (`social/exit_trigger.py:16-27`, `_EXIT_Y_THRESHOLD = 12.5` на `:14`) в production **не вызывается никем** — только тесты. Реальный выход детектит фронтенд дубль-константой `if py >= 12.5` (`game_screen.py:946-947`) → `finalize_campaign` + `get_end_screen` (`:950-953`).
- `TruthState.discovered_secrets` — in-memory set; сериализация отсутствует; при рестарте процесса прогресс теряется (аудит §8.3).
- End screen показывает «X / **16**» при пустом ответе (`end_screen_renderer.py:47`) — рассинхрон с каноном 17; `secrets_total=16` и в моках `test_p7_10_end_screen.py`.

### Что делаем

1. **Backend — владелец выхода (SSOT):** вызов `mvp_controller.check_exit(scene_state)` в `game_loop` после хода/тика (точка: `game_loop/__init__.py`, рядом с инъекцией снапшота `:1639-1663`). Фронт дубликат `game_screen.py:946-952` сохраняет как UX-реакцию (показ end screen сразу), но финализация инициируется сервером.
2. **Персистентность:** `PlayerEpistemicState.levels` + `TruthState.discovered_secrets` сериализуются в сейв кампании (player_avatar_service / scene snapshot): `save: {"epistemic": {...}}`, `load:` восстановление. Требование I7.
3. **Endgame потребляет Bridge:** `EvaluationEngine.evaluate` (`evaluation_engine.py:19-76`) продолжает зачитывать `secret_id in discovered_secrets` — теперь туда пишут уровни 2 от Bridge. Belief-путь (TRUE ≥ 0.8, `:49-51`) остаётся совместимым (регистрирует `register_direct_evidence` путь).
4. **Косметика-рассинхроны:** дефолт 16 → 17 в `end_screen_renderer.py:47`; моки `test_p7_10_end_screen.py` 16 → 17; судьбы/последние слова 3/6 NPC (`last_words_system.py:18-35`) — дозаполнить для borko/lusya/tornin-группы по канону (S-размер, вне критического пути).

**Критерии приёмки:** полный цикл «17/17 → выход → end_screen score 170» в тесте P10; рестарт процесса и загрузка сейва сохраняют `levels`; `grep -r "16"` по end-screen коду не находит рассинхрона.

---

## 4. ПОРЯДОК РЕАЛИЗАЦИИ И ВЕХИ

```
M1 «Кто знает что»      = P1 + P2          (идентичность + reconciliation)
M2 «Вопрос находит»     = P3 + P4          (DialogueQuery + retrieval)
M3 «Движок решает —      = P5 + P6 + P7    (decision → bridge → verbalization)  ← СЕРДЦЕ
    LLM говорит»
M4 «Игрок видит знание» = P8 + P9          (журнал + UI + API)
M5 «Гейт и выход»       = P10 + P11        (17/17 + exit/endgame)
```

| Веха | Демонстрация без UI | Измеримый результат |
|---|---|---|
| M1 | debug-dump `who_knows(sid)` × 17 | карта знаний == канон, 100% |
| M2 | лог `DialogueQuery` → `KnowledgeItem` | 10/10 контрольных фраз |
| M3 | сквозной диалог: вопрос → outcome → уровень | discovery без string-матча; false positives = 0 |
| M4 | снапшот с `facts`/`hypotheses`/`secrets_progress` | вкладки живые, счёт N/17 |
| M5 | e2e 17/17 + рестарт с сохранением | score 170; перезапуск не теряет прогресс |

Зависимости жёсткие: M2 не начинается без M1 (retrieval ищет по secret_id), M3 без M2 (decision consumes KnowledgeItem), M5 без M3/M4 (тест ассертит и уровни, и API). Внутри вех P-этапы можно параллелить (P8 ∥ P9; P1 ∥ P3-леммы — независимо).

---

## 5. ТЕСТОВАЯ СТРАТЕГИЯ (сводно)

1. **Юнит-слой:** test_p1…test_p9 по критериям приёмки каждого этапа (см. выше). Именование единое, маркер `smoke` для canon-sync.
2. **Инварианты (pytest, автозапуск):**
   - INV-BRIDGE-ONLY: `mark_discovered` вызывается только из `discovery_bridge.py` (grep-инвариант, аналог существующего IPT.py:593-604);
   - INV-NO-STRING-MATCH: в диалоговом тике SequenceMatcher не вызывается;
   - INV-DETERMINISM: двойной прогон decision — идентичность.
3. **E2E-гейт:** `e2e/test_17_of_17_playthrough.py` + два негативных теста (P10.3).
4. **Наблюдаемость:** `/debug/memories` рентген (`routes.py:777`) расширяется выводом `secret_id` — живая отладка «кто знает что» без пересборки.

---

## 6. РИСКИ И ПРОТИВОЯДИЯ

| Риск | Симптом | Противоядие |
|---|---|---|
| Извлечение subject слишком узкое (парафразы мимо словаря тем) | вопросы «не находят» знание | `topics` расширять синонимами по данным реальных сессий; fallback: пустой subject честен (DENY/REDIRECT), не фейк-hit; словарь — данные, не код |
| Пороги P5 либо пусты (никогда не REVEAL), либо дырявы (reveal с первого вопроса) | M3-демо качается | калибровка скриптом P10 (матрица входов×порогов); REVEAL обязан требовать ≥2-3 социальных шагов (предварительный trust/pressure) |
| LLM вне outcome всё же произносит канон дословно | визуальный «слив» без зачёта | это деградация вербализации, не механизм (I2); телеметрия keywords ловит и показывает частоту; при необходимости — пост-фильтр ResponseValidator |
| Слипание уровней: CLUE-наблюдения заспамляют «Гипотезы» | журнал-мусор | шаблоны автотекста только на переход уровня (не на каждый тик); лимит записей как в журнале (FIFO 100) |
| Scope creep до PlayerCausalModel / inference | срыв сроков | анти-цели §2 — часть код-ревью; relations-граф остаётся счётчиком (аудит §13.B.8) |
| Рассинхрон канона вернётся | чек красный | INV из P2 в CI; правки канона без синк-конфигов ломают билд |

---

## 7. DEFINITION OF DONE (MVP-контур)

1. Для каждого из 17 секретов существует воспроизводимая **социальная** цепочка игровых действий, заканчивающаяся уровнем 2 в PlayerEpistemicState — и она проходит через один Discovery Bridge.
2. Ни одно открытие секрета не зависит от строкового совпадения вывода LLM; LLM не имеет каузальной власти (I1-I2 подтверждены инвариант-тестами).
3. Игрок видит зачёт: сигнал перехода + вкладки «Гипотезы/Факты/Секреты» + счёт N/17.
4. `GET /game/progress` отдаёт уровни; фронту и тестам хватает одного источника.
5. Выход из таверны детектит backend; endgame считает по реальным данным; «X / 16» исправлен.
6. Прогресс переживает перезапуск процесса.
7. `e2e/test_17_of_17_playthrough.py` зелёный в CI; негативные тесты зелёные.
8. Ни одна анти-цель §2 не нарушена (чек-лист в PR-шаблоне).

---

## 8. ТРАССИРОВКА: НАХОДКА АУДИТА → ЭТАП ТЗ

| Находка аудита (gap map) | Этап |
|---|---|
| §2.3 `initial_holders`/`discovery_surface` — мёртвые поля | P1 (оживление holders), P6 (discovery_surface — семантика поверхностей Bridge) |
| §3.1-3.2 EventMemory без secret_id, SQLite без колонки | P1 |
| §3.4 шесть рассинхронов канон↔конфиг | P2 |
| §4.2 Ask(NPC, subject) NOT FOUND; вопросы → UNCERTAIN | P3 |
| §4.3 секреты не в промпте; suppressed_secrets без читателей | P7 |
| §4.4 author_notes — анти-reveal, вариант D (вопрос не подключён) | P5 (решение забирает движок) + P7 (notes → стиль) |
| §6.1 три call-site mark_discovered вне единого контура | P6 (сведение под Bridge) |
| §6.2 PropositionMatcher — лотерея (порог 0.2, канон↔шаблон) | P6 (deprecate из каузальной цепи) |
| §6.3 secret_id в PlayerAction от лотерейных propositions | P3/P4 (структурный secret_id) |
| §7.1 UI-фидбек открытия NOT FOUND | P8 |
| §7.2 вкладки-заглушки; beliefs пустой массив | P8 |
| §7.3 per-secret прогресс наружу не выходит | P9 |
| §8.1 ExitTrigger мёртв; порог 12.5 продублирован | P11 |
| §8.2 endgame работает, но получает пустые входы | P6→P11 (топливо из Bridge) |
| §8.3 discovered_secrets не персистентны | P11 |
| §9.1-9.3 MockProvider random; нет progress API; нет оркестратора | P10 |
| §10 досье: 0/17 гарантированно достижимы; 1/17 partial | весь контур; гейт P10 |
| §13.B.3-4 eavesdrop/DM-нарратив в обход парсера | P6 |
| §13.B.5 «трещины под давлением» мертвы | P5 (T5.0 — переиспользование формул) |
| §13.Е «X/16» на фронте; моки 16 | P11 |

---

## 9. ПРИНЯТЫЕ ДОПУЩЕНИЯ (зафиксировано вместо открытых вопросов)

1. **visual_cue (4 секрета) — за пределами первого контура.** Поверхность декларируется в Bridge (`VISUAL_CUE` enum-значение есть), но эмиттеры визуальных подсказок — отдельная задача после M5. Это не влияет на 17/17: все секреты должны достигаться через dialogue/eavesdrop (у каждого секрета в `discovery_surface` есть хотя бы одна из них — проверено аудитом §2.2).
2. **`confession_keywords` остаются** в каноне и в Bridge — как телеметрический фильтр и быстрый compat-путь тестов; каузальным источником их делает только связка с DisclosureOutcome.
3. **Поле `topics` — минимальное** (3-6 тем на секрет, составляется вручную из канон-текста за один проход); расширение — по данным плейтестов, это контент, не архитектура.
4. **Уровни 0/1/2 без обогащённых градаций** (CLUE++ из видения Фазы 5 реализуется как PARTIAL→level 1 с большим fraction, а не как отдельный уровень) — чтобы не плодить состояния до появления inference.
5. **Ложь** = DENY со stance, без модели fabricated-belief.
6. **Оценка масштаба этапов:** P1 — S/M, P2 — S, P3 — M, P4 — S/M, P5 — M, P6 — M/L (сердце), P7 — M, P8 — M, P9 — S, P10 — M, P11 — S/M. Ни один этап не требует новой подсистемы — только мостов (согласуется с аудитом §15: P1-P3 точечные правки существующих файлов).

---

## ПРИЛОЖЕНИЕ А. Реестр 17 секретов (машинная сверка с каноном)

`lusya_basement` · `lusya_shadow_orders` · `lusya_orm_borko` · `lusya_borko_crush` · `borko_bribe` · `borko_voyeur` · `borko_negligence` · `goran_contraband` · `goran_bribe` · `orm_craft` · `orm_tornin_order` · `shadow_investigation` · `shadow_suspects_lusya` · `shadow_first_kill` · `shadow_guild_membership` · `tornin_debt` · `tornin_basement`

Полные досье (владельцы, участники, поверхности, пути) — `mvp_secret_tavern_gap_map.md` §10 и `secrets_manifest.json` `secrets[0..16]`.

## ПРИЛОЖЕНИЕ Б. Поверхности discovery и их статус в контуре

| Поверхность | Секретов (канон) | Сейчас | После контура |
|---|---|---|---|
| dialogue | 9 | overlap-лотерея | DialogueQuery → retrieval → decision → Bridge (основной путь) |
| eavesdrop | 9 | журнал, discovery нет | SurfaceEvent(EAVESDROP) → Bridge (метка по происхождению) |
| visual_cue | 4 | ничего | enum готов в Bridge; эмиттеры — пост-M5 (допущение 1) |
| dm_narrative (RCE) | — | в обход парсера | SurfaceEvent(DM_NARRATIVE) → Bridge |

## ПРИЛОЖЕНИЕ В. Инварианты для PR-шаблона (чек-лист ревью)

- [ ] Нет нового call-site `mark_discovered` вне `discovery_bridge.py`
- [ ] Решения (decide/resolve/match) детерминированы; тест двойного прогона добавлен
- [ ] Ни одна строка игрока не является триггером reveal
- [ ] author_notes не читаются decision-слоем
- [ ] Новые поля канона (`topics`, `sensitivity`, `silhouette`) — в `truth_state_tavern.json`, SSOT не разветвлён
- [ ] Canon-sync чек зелёный
- [ ] Вывод LLM не анализируется для discovery
- [ ] Названия/канон-текст undiscovered секретов не утекают в снапшот
