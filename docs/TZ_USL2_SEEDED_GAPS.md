# ТЗ: Разрывы SEEDED-фазы — найдены USL-2 корпусным прогоном

**Статус:** OPEN — три системных разрыва, передаются владельцам контуров.
**Источник:** USL-2 корпусный прогон (S411, ветвь А, USL-2 пилот корпуса).
**Дата обнаружения:** 2026-11-03.
**Метод:** `biography_to_usl` + `chronicle_seeder.build_seed_*` на каноне 6 NPC.

---

## 0. Контекст

USL-2 (этап «полная интеграция биографического корпуса», §9 USL-документа) — первый реальный испытательный полигон архитектуры USL. Цель: доказать, что авторские биографии проходят не только USL-проекцию, но и всю статусную цепочку до когнитивных структур NPC.

### Что доказано GREEN (USL-проекция)

| Критерий | Результат |
|---|---|
| Замок равенства (entries → USLUnit) | 363==363 GREEN |
| USL-2 (source kind = AUTHOR_CANON) | 363/363 GREEN |
| USL-6 (детерминизм, повторный прогон) | 6/6 NPC GREEN |
| Temporal match (canon historical_age == USL temporal) | 1==1 GREEN (консервативность) |

Архитектура `biography_to_usl` (`backend/app/services/chronicle/biography_adapter.py`) выдержала полный корпус 6 NPC: 363 entries → 363 USLUnit без потерь, без галлюцинаций, с детерминизмом. **USL-1.2 доказан на реальном корпусе, не на демонстрационных примерах.**

### Что обнаружено RED (SEEDED-фаза)

Прогон `chronicle_seeder.build_seed_*` на maid_lusya (единственный NPC с `game_start_age=14`) показал: из 59 entries канона до когнитивных структур доходит только 11 EventMemory. Остальные 48 entries либо отклонены seeder'ом, либо не проверены.

```
SOURCE TEXT → PARSED → NORMALIZED → CANONIZED → SEEDED → COGNITIVELY AVAILABLE → USED IN GAME
   21 пункт    59       59          59          11/59       ?                      ?
               ✅        ✅          ✅         ⚠️ РАЗРЫВ
```

Три системных разрыва зафиксированы ниже как отдельные задачи.

---

## Разрыв 1: RELATIONSHIP → 0 (неразрешённые сущности)

### Симптом

```
[CCH_SEED] maid_lusya:1df0e95246c841794385f3098924064d: связь на неразрешённую сущность — не сеется
... 9 таких сообщений ...
[SEEDED] relationship_cache entries: 0
```

Все 9 RELATIONSHIP entries maid_lusya отклонены seeder'ом. `relationship_cache` остался пустым. NPC не получает стартовые отношения к Торнину, Орму, Борко, Гильдии воров, Тени.

### Доказательство

Все 9 RELATIONSHIP entries имеют **пустой `object_id`** при наличии `payload.target_hint` с именем:

| entry_id (префикс) | target_hint | summary |
|---|---|---|
| 1df0e95246c8... | Гильдия воров | отношение к ней нельзя назвать доброжелательным |
| 31c416fdc6d4... | она | Торнин относился к ней как к неудобной работнице |
| 864ca8099f73... | стражник Борко | искренняя доброжелательность к себе |
| ac70b9ea90dd... | стражник Борко | относительно молод и красив |
| e9b5f521a413... | стражник Борко | высокое социальное положение |
| 4623c44cdb9d... | возлюбленный стражник Борко | более думает о шансах и меньше о побеге |
| 1f8171d6f8b1... | Торнин | Звон посуды вызывает вздрагивание у Торнина |
| 0ea54c7fdcd7... | Торнин | Звон посуды вызывает вздрагивание у Торнина |
| a8f577d3d568... | (пусто) | Два человека реагируют на один звук |

`object_id` во всех 9 — пустой (не `RESOLVED`). Seeder на `chronicle_seeder.py:284` вызывает `_resolved_npc_id(e.object_id)` → возвращает None → строка 286: warning + continue.

### Корневая причина

Декомпозиция (`BiographyDecomposer`) извлекает `target_hint` (имя в тексте), но **не резолвит его в `npc_id` через `CanonicalRegistry`**. `object_id` остаётся пустым или `WHITE_SPOT` вместо `RESOLVED`.

USL-1.5 CanonicalRegistry bridge (S410) реализован **только в input-контуре** (`intent_compressor.py:432-455`, `_ensure_registry_cache()` + `_resolve_npc_by_name canonical-first`). Biography-контур не использует CanonicalRegistry при декомпозиции — это асимметрия §5.4 USL-документа, которую USL-1.5 закрыл наполовину.

### Владелец

Трек CCH (biography-контур). Точка: `BiographyDecomposer.decompose` → `ChronicleDecompositionNormalizer.normalize` → формирование `object_id` в `DecompositionItem`.

### Предлагаемое решение

Пробросить `CanonicalRegistry` в biography-контур аналогично input-контуру:
1. `BiographyDecomposer` получает доступ к `build_canonical_registry()` (read-only, как в `intent_compressor.py:444`).
2. После LLM-декомпозиции, в нормализаторе или post-normalize шаге, `target_hint` резолвится через registry: «стражник Борко» → `guard_borko`, «Торнин» → `tavern_keeper_tornin`, «Орм» → `blacksmith_orm`, «Гильдия воров» → (возможно, WHITE_SPOT — это организация, не NPC).
3. Если резолв успешен — `object_id = EntityRef(ref_kind=RESOLVED, npc_id=...)`. Если нет — остаётся WHITE_SPOT (честно, не угадываем).
4. Не разрушать fallback: если CanonicalRegistry недоступен, поведение не меняется.

### Критерий приёмки

- `maid_lusya.json`: 9 RELATIONSHIP entries имеют `object_id.ref_kind=RESOLVED` для тех target_hint, которые маппятся на канонических NPC (Борко, Торнин, Орм, Тень).
- `relationship_cache` maid_lusya после seeder содержит ≥4 записей (Борко, Торнин, Орм, Гильдия воров как WHITE_SPOT или организация).
- Замок: `seeded relationships > 0` для maid_lusya.
- Регресс: существующие каноны других NPC не сломаны (IPT зелёный).

### Артефакты

- Скрипт проверки: `scripts/usl2_seeded_lusya.py` (секция `build_seed_relationships`).
- Канон: `config/npc/chronicles/maid_lusya.json` (9 RELATIONSHIP entries).
- Код seeder: `backend/app/services/chronicle/chronicle_seeder.py:274-307` (`build_seed_relationships`).
- Код input-bridge (референс): `backend/app/services/input/intent_compressor.py:432-455`.

---

## Разрыв 2: EFFECT trauma → 0 imprints (нет triggers)

### Симптом

```
[CCH_SEED] maid_lusya:033e4db205d7a131a61a7dfc67c5ecbe: trauma без triggers — импринт не создан
... 3 таких сообщения ...
[SEEDED] affective_imprints: 0
```

Все trauma-EFFECT entries maid_lusya отклонены seeder'ом. `affective_imprints` остался пустым. NPC не получает стартовые травматические импринты (избиения, изнасилование, смерть семьи) с `decay_rate=0`.

### Доказательство

EFFECT entries maid_lusya имеют payload:
```json
{
  "summary": "понимает, что Гильдия с её связями быстро найдёт её и «накажет»",
  "effect_kind": "trauma",
  "target_hint": null
}
```

Поле `triggers` **отсутствует** в payload всех EFFECT entries. Payload EFFECT содержит только: `summary`, `effect_kind`, `target_hint` (иногда `_resolved_questions`).

Seeder на `chronicle_seeder.py:321-326`:
```python
triggers = e.payload.get(_PL_TRIGGERS)  # _PL_TRIGGERS = "triggers"
if not triggers or not isinstance(triggers, (list, tuple)):
    logger.warning(f"[CCH_SEED] {doc.chronicle_id}:{e.entry_id}: trauma без triggers — импринт не создан")
    continue
```

Комментарий seeder (строки 315-316): «Триггеры — ТОЛЬКО авторская пометка `payload['triggers']`: нет пометки → импринт не создаётся, громкий лог (ничего не выдумываем)». Это **честный отказ** — seeder не галлюцинирует triggers.

### Корневая причина

Декомпозиция не извлекает `triggers` для trauma-EFFECT. В авторском тексте Люси есть явные триггеры (п.17: «звон бьющейся или гремящей посуды» — триггер для травмы избиений), но декомпозиция не помещает их в `payload.triggers`.

Это **разрыв между авторским замыслом и структурой канона**: автор пишет «звон посуды → вздрагивание», декомпозиция разбирает это как два отдельных entries (EFFECT trauma + RELATIONSHIP synchronization), но не связывает триггер с травмой.

### Владелец

Трек CCH (декомпозиция). Точка: `BiographyDecomposer.decompose` → промпт `prompts/chronicle_decompose_system.txt` → GBNF-грамматика `config/chronicle_decompose.gbnf`. Извлечение `triggers` для `effect_kind=trauma` должно быть добавлено в промпт и/или грамматику.

### Предлагаемое решение

Добавить извлечение `triggers` для trauma-EFFECT в декомпозицию:
1. В промпт `chronicle_decompose_system.txt` добавить инструкцию: для trauma-EFFECT извлекать `triggers` — список тегов, которые активируют травму в рантайме (звуки, запахи, визуальные образы, ситуации).
2. В GBNF-грамматику добавить поле `triggers` в payload для EFFECT с `effect_kind=trauma`.
3. В нормализаторе — fail-loud проверка: trauma-EFFECT без `triggers` → warning (не error, потому что автор мог не указать триггер явно).
4. Для существующих канонов — либо пере-декомпозиция через `scripts/redecompose_all_npc.py`, либо ручная правка author'ом через Character Debugger (CCH-4).

### Альтернатива (если автор не указал триггеры)

Если авторский текст не содержит явных триггеров — честно оставить `triggers=[]` и не создавать импринт. Это не баг, это отсутствие данных. Но тогда автор должен иметь возможность добавить триггеры через UI (Character Debugger, CCH-4) — это уже UX-задача, не декомпозиция.

### Критерий приёмки

- Для maid_lusya: ≥1 trauma-EFFECT имеет `payload.triggers` (список тегов).
- `affective_imprints` после seeder содержит ≥1 запись с `decay_rate=0`.
- Замок: `seeded imprints > 0` для maid_lusya.
- Регресс: IPT зелёный, существующие EFFECT entries без trauma не затронуты.

### Артефакты

- Скрипт проверки: `scripts/usl2_seeded_lusya.py` (секция `build_seed_imprints`).
- Канон: `config/npc/chronicles/maid_lusya.json` (EFFECT entries с `effect_kind=trauma`).
- Код seeder: `backend/app/services/chronicle/chronicle_seeder.py:308-343` (`build_seed_imprints`).
- Промпт: `prompts/chronicle_decompose_system.txt`.
- Грамматика: `config/chronicle_decompose.gbnf`.

---

## Разрыв 3: BELIEF_SEED — API drift + возможное отсутствие belief_type

### Симптом

```
[ERROR] build_seed_beliefs: TypeError: build_seed_beliefs() takes 1 positional argument but 2 were given
```

Вызов `build_seed_beliefs(npc_id, doc)` упал — функция принимает только `(doc)`. Это моя ошибка в диагностическом скрипте, но она вскрыла более глубокий вопрос: доходят ли BELIEF_SEED до BeliefState вообще?

### Доказательство

Сигнатура (подтверждена археологией):
```python
def build_seed_beliefs(doc: ChronicleDocument) -> Dict[str, List[Any]]:
    """BELIEF_SEED → формат psyche['beliefs'] {type: [value, conf, src, tick]}.
    Только типы закрытого реестра BeliefType; без типа — остаётся в каноне."""
    from app.models.npc.beliefs import BeliefType
    registry = {t.value for t in BeliefType}
    result: Dict[str, List[Any]] = {}
    for e in _author_entries(doc):
        if e.kind is not EntryKind.BELIEF_SEED:
            continue
        btype = e.payload.get(_PL_BELIEF_TYPE)
        if btype not in registry:
            logger.warning(f"[CCH_SEED] {doc.chronicle_id}:{e.entry_id}: belief_type='{btype}' вне реестра — в каноне")
            continue
        result[str(btype)] = [SEED_BELIEF_VALUE, SEED_BELIEF_CONFIDENCE, "chronicle", 0]
    return result
```

Seeder ожидает `payload['belief_type']` (через `_PL_BELIEF_TYPE`), и это значение должно быть в закрытом реестре `BeliefType`. Если поля нет или тип не в реестре — belief остаётся в каноне, не сеется.

### Что НЕ проверено (требует отдельной археологии)

Из предыдущего вывода BELIEF_SEED entries maid_lusya имели payload вида `{statement: "..."}`. Нужно проверить:
1. Есть ли в payload BELIEF_SEED поле `belief_type`?
2. Если есть — какие значения? Они в реестре `BeliefType`?
3. Если нет — декомпозиция не извлекает `belief_type`, и все 8 BELIEF_SEED maid_lusya молча отклоняются seeder'ом.

### Владелец

Трек CCH (декомпозиция + реестр BeliefType). Точка: `BiographyDecomposer.decompose` → формирование `payload.belief_type` для BELIEF_SEED. Также: `app/models/npc/beliefs.py` — реестр `BeliefType` (закрытый, расширение через ADR).

### Предлагаемое решение

1. **Археология**: проверить структуру payload BELIEF_SEED в maid_lusya.json — есть ли `belief_type`.
2. Если `belief_type` отсутствует — добавить извлечение в декомпозицию (промпт + GBNF).
3. Если `belief_type` есть, но не в реестре — либо расширить реестр `BeliefType` (мини-ADR), либо согласовать с автором переформулировку.
4. Если `belief_type` есть и в реестре — разрыв не подтверждён, BELIEF_SEED сеется корректно.

### Критерий приёмки

- Подтверждена структура payload BELIEF_SEED (есть/нет `belief_type`).
- Если `belief_type` отсутствует: добавлено извлечение в декомпозицию, ≥1 BELIEF_SEED maid_lusya сеется в BeliefState.
- Если `belief_type` есть, но не в реестре: либо реестр расширен (ADR), либо автор переформулировал.
- Замок: `seeded beliefs > 0` для maid_lusya.
- Регресс: IPT зелёный.

### Артефакты

- Скрипт проверки: `scripts/usl2_seeded_lusya.py` (секция `build_seed_beliefs` — исправить вызов на `build_seed_beliefs(doc)`).
- Канон: `config/npc/chronicles/maid_lusya.json` (8 BELIEF_SEED entries).
- Код seeder: `backend/app/services/chronicle/chronicle_seeder.py:346-364` (`build_seed_beliefs`).
- Реестр: `backend/app/models/npc/beliefs.py` (`BeliefType`).
- Промпт: `prompts/chronicle_decompose_system.txt`.

---

## Дополнительные находки USL-2 (не блокеры, но зафиксировать)

### Находка A: temporal слой системно пуст — 1/363 (0%)

Только 1 из 363 entries корпуса имеет structured `historical_age` (maid_lusya, age=5, «семья убита бандитами»). Остальные 362 — `historical_age=null`.

При этом **33 entries** имеют возрастной маркер в `text_span`, но пустой temporal. Конкретные конструкции:

| NPC | Примеры age-marker в text_span |
|---|---|
| blacksmith_orm | «57 лет», «70 лет назад», «второй десяток лет», «146 лет», «за 57 лет» |
| guard_borko | «с 22 лет», «в молодости», «в 24 застал изнасилование Люси» |
| maid_lusya | «ещё 4 года», «деньги Орма» (искажённые маркеры) |
| merchant_goran | «40 лет», «годы», «всегда считает выгоду» |
| tavern_keeper_tornin | «45 лет», «в 40 лет», «неделю», «за годы алкоголизма», «на день» |
| thief_shadow | «60 лет», «шестидесяти», «долги гильдии» |

Это **главный материал для USL-1.5+ (Temporal Extractor для biography-контура)** — отдельная задача, не блокер USL-2. USL-2 зафиксировал разрыв; чинит его расширение `extract_age_anchors_typed` или новый post-normalize шаг в декомпозиции.

### Находка B: game_start_age есть только у maid_lusya (1/6)

§2.1 USL-документа подтверждён: только `maid_lusya=14`. У 5 NPC `game_start_age=null`.

Это **блокер для SEEDED-фазы 5/6 NPC**: seeder использует `day=(age−game_start_age)×365` (§2.1). Без `game_start_age` все events идут в `SENTINEL_DAY=-1000` («при неизвестном возрасте»). NPC «не помнит, когда это было».

Это **контентная работа автора**, не кодовая: автор должен указать возраст каждого NPC на момент игры. USL только делает пустоту видимой.

### Находка C: KNOWLEDGE_LINK = 0 во всём корпусе

USLPredicate distribution корпуса: `asserts: 112, has_effect: 110, has_trait: 98, believes: 34, lives_at: 8, desires: 1`. Нет `knows` — значит, KNOWLEDGE_LINK entries отсутствуют во всех 6 канонах.

Это подтверждает §2.1: «KNOWLEDGE_LINK=0 в 6 канонах». Канал знания (`KnowledgeChannel`: WITNESSED/TOLD/OVERHEARD/DEDUCED/UNKNOWN) не используется. NPC не имеют типизированного знания о том, **откуда они знают** то, что знают.

Это **контентная + кодовая работа**: декомпозиция должна извлекать KNOWLEDGE_LINK entries (кто что знает и откуда), автор должен отметить это в тексте. Не блокер USL-2, но материал для будущего развития CCH.

### Находка D: TRAIT_SEED и PORTRET не сеются

`build_full_seed` (строка 367) явно пропускает TRAIT_SEED: «черты ждут Character Calibration (отдельный ADR, вердикт владельца) — в каноне не теряются». Это **осознанное решение**, не разрыв. TRAIT_SEED остаётся в каноне до отдельного ADR по Character Calibration.

---

## Что НЕ входит в scope этого ТЗ

Согласно вердикту Мастера USL-0 (поправка 3): «`act_consumer` и `WhiteSpotRegistry` не трогать — out of scope USL-1». Это же распространяется на USL-2: данные разрывы — работа владельцев CCH (декомпозиция, seeder, реестр), не USL.

USL-2 **только фиксирует разрывы** — он не чинит BiographyDecomposer, не расширяет BeliefType, не добавляет triggers в промпт. Это соответствует §9 этапа USL-2: «USL только делает её измеримой».

---

## Артефакты USL-2 корпусного прогона

| Файл | Назначение |
|---|---|
| `scripts/usl2_pilot_lusya.py` | Пилот — maid_lusya через biography_to_usl (59 entries → 59 USLUnit) |
| `scripts/usl2_corpus_all.py` | Корпус — 6 NPC через biography_to_usl (363==363 GREEN) |
| `scripts/usl2_seeded_lusya.py` | SEEDED-фаза — maid_lusya через chronicle_seeder (11/59, 3 разрыва) |

Все скрипты — read-only над канонами, не персистят, не запускают игру. Можно перепрогонять для верификации фиксов.

---

## Итоговая статусная цепочка USL-2

```
SOURCE TEXT → PARSED → NORMALIZED → CANONIZED → SEEDED → COGNITIVELY AVAILABLE → USED IN GAME
   6 NPC        363      363          363         11/59*     ?                      ?
   ✅           ✅        ✅           ✅         ⚠️ РАЗРЫВ   ⏳                     ⏳
```

\* 11/59 — только для maid_lusya (единственный NPC с game_start_age). Для остальных 5 NPC SEEDED-фаза не проверена из-за блокера game_start_age.

**USL-2 доказал:** архитектура USL (biography_to_usl) выдерживает полный корпус. Разрывы обнаружены не в USL, а в downstream-контурах (декомпозиция, seeder, реестр). Это и есть ценность USL-2 как измерителя: он сделал видимыми три системных разрыва, которые ранее были скрыты за «декомпозиция успешна».

---

## Приоритизация (предложение)

| Разрыв | Блокер для USL-2 закрытия | Сложность | Владелец |
|---|---|---|---|
| 1. RELATIONSHIP → 0 (неразрешённые сущности) | ДА | Средняя (проброс CanonicalRegistry в biography) | CCH |
| 2. EFFECT trauma → 0 imprints (нет triggers) | ДА | Средняя (промпт + GBNF + пере-декомпозиция) | CCH |
| 3. BELIEF_SEED — API drift + belief_type | ДА | Низкая (археология + возможно промпт) | CCH |
| A. temporal 1/363 (USL-1.5+ Temporal Extractor) | НЕТ (отдельная задача) | Высокая | USL/CCH |
| B. game_start_age 1/6 | НЕТ (контент автора) | Низкая (заполнить 5 полей) | Автор |
| C. KNOWLEDGE_LINK = 0 | НЕТ (будущее развитие) | Высокая | CCH |

Разрывы 1-3 — **блокеры для закрытия USL-2**: без них SEEDED-фаза не проходит, статусная цепочка разорвана. Фикс разрывов 1-3 — условие перехода к COGNITIVELY AVAILABLE → USED IN GAME (следующие звенья).

---

## Вердикт Мастера (запрашивается)

1. Утвердить три разрыва как задачи трека CCH.
2. Назначить владельца (ветвь А или Б).
3. Приоритет относительно других задач §0.2.
4. Решение по находке B (game_start_age): заполнить автору или отложить.
5. Решение по находке A (temporal): включить в USL-1.5+ или отдельный трек.
