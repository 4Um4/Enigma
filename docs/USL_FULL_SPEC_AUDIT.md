# USL — Полный аудит технического задания

> **Статус:** АУДИТ ЗАВЕРШЁН — представлен Мастеру для вердикта
> **Дата:** 2026-11-04
> **Автор:** Архитектор USL (преемник S380/S410/S411)
> **Мандат:** MASTER DIRECTIVE — полный аудит всего ТЗ USL (не ограничиваясь 3 известными разрывами)
> **Метод:** read-only археология production-кода + реальные прогоны скриптов + анализ 6 NPC канонов
> **Baseline:** IPT 54/0/0 CRITICAL=0; USL pytest 89/89 GREEN; git HEAD `fabd3ebc`

---

## 0. Краткое резюме (Executive Summary)

**USL-1 (интеграция двух контуров) — полностью реализован и подтверждён.** 89 тестов GREEN, 5 production-модулей в коде, ADR-O-437 ACTIVE, DTO Registry §15 зарегистрирован. CanonicalRegistry bridge (USL-1.5) работает: «Орму» автора = «Орму» игрока = `blacksmith_orm`.

**USL-2 (биографический корпус) — заблокирован на этапе SEEDED.** Архитектура `biography_to_usl` выдержала полный корпус 6 NPC (363/363 GREEN), но из 59 entries maid_lusya в когнитивные структуры доходит только 11 EventMemory (19%). Остальные 48 entries (81%) теряются по 3 известным + 5 новым причинам.

**Главный вывод аудита:** USL как общий словарь смысла — работает. USL как инструмент доведения смысла до игрового поведения — заблокирован downstream-разрывами в CCH-контуре (декомпозиция + seeder), не в USL.

**Найдено 8 разрывов** (3 известных + 5 новых), **4 противоречия** документ↔код, **2 устаревших пути**. Предлагается единый план ремонта из 7 работ с зависимостями и критериями завершения.

---

## 1. Полный перечень требований USL с результатами проверки

### 1.1. Требования из USL-документа §3.4 — 6 инвариантов

| Инвариант | Требование | Статус | Доказательство |
|---|---|---|---|
| **USL-1** | Одно представление смысла независимо от источника | **PARTIAL** | events/relations — GREEN; **temporal — RED для input** (`temporal=()` в `intent_to_usl_unit`); causal — RED для biography (0/363) |
| **USL-2** | Источник ≠ истина (source_kind + epistemic_status) | **GREEN** | `USLSourceKind` 9 значений; `test_player_assertion_not_author_canon` GREEN; `PLAYER_ASSERTION → CANON` запрещён |
| **USL-3** | Не пишет мир (read-only проектор) | **GREEN** | USLUnit transient; ни одна USL-функция не пишет в TruthState/канон/EventMemory/EpistemicStore; `test_free_assert_does_not_touch_canon` GREEN |
| **USL-4** | Обратная совместимость | **GREEN** | `IntentSemanticField`, `ChronicleEntry` остаются действующими; USLUnit — проекция поверх; 0 регрессий baseline |
| **USL-5** | Провенанс трассируем (source_span обязателен) | **GREEN** | `make_unit_id` включает span; `test_source_span_always_present` GREEN; 0 units without span в корпусе |
| **USL-6** | Детерминизм | **GREEN** | `make_unit_id` md5; `test_intent_to_usl_is_deterministic` + `test_biography_to_usl_is_deterministic` GREEN; re-run identical=True |

### 1.2. Требования из USL-документа §4-§7 — модель смысла

| Компонент | Требование | Статус | Доказательство |
|---|---|---|---|
| USLUnit (§4.2) | transient frozen DTO, 8 кортежей | **GREEN** | `domain/usl.py`: USLUnit с entities/events/temporal/causal/relations/modality/epistemics/context |
| USLEvent (§4.3) | predicate + subject + object + polarity + completed + negated | **GREEN** | Mapping EntryKind→USLPredicate (10 видов) + Predicate→USLPredicate (6 общих) |
| USLTimeExpression (§6.2) | 6 форм: POINT/DURATION/INTERVAL/ORDER/RELATIVE/UNKNOWN | **GREEN** (тип), **RED** (заполнение) | Тип реализован; biography — 1/363 temporal; input — `temporal=()` |
| USLCausalLink (§6.4) | asserted_by_text; ORDER → CAUSES запрещён | **GREEN** (тип), **RED** (заполнение) | Тип реализован; biography_adapter не строит causal (0/363) |
| USLRelation (§4.5) | без скаляров, только valence | **GREEN** | `_payload_to_relation` извлекает nature/valence |
| USLModal (§4.6) | None = недостаточная информация | **GREEN** | `_act_to_modal` per-act контракт |
| USLEpistemics (§4.7) | source_kind + channel + certainty | **GREEN** | channel реюз KnowledgeChannel |
| USLContext (§4.8) | references/addressee/thread/place | **GREEN** | Собирает из IntentSemanticField |

### 1.3. Требования из USL-документа §5 — два адаптера

| Адаптер | Требование | Статус | Доказательство |
|---|---|---|---|
| BiographyAdapter (§5.1) | ChronicleEntry → USLUnit, pure projector | **GREEN** | `biography_adapter.py:biography_to_usl`; 1:1 mapping; 363/363 корпус |
| InteractiveLanguageAdapter (§5.2) | IntentSemanticField → USLUnit | **GREEN** | `interactive_language_adapter.py:intent_to_usl_unit`; proposition приоритет, semantic_acts fallback |
| §5.3 Инвариант адаптеров | одинаковое содержание ≠ одинаковый эпистемический статус | **GREEN** | `test_player_and_npc_same_structure_different_source` GREEN |
| §5.4 Единый реестр имён | «Орму» автора = «Орму» игрока | **GREEN** (input), **RED** (biography) | USL-1.5 закрыл для input; **biography-контур не резолвит target_hint через CanonicalRegistry** |

### 1.4. Требования из USL-документа §9 — план внедрения

| Этап | Требование | Статус | Доказательство |
|---|---|---|---|
| USL-0 | Архитектурная фиксация + контракты | **GREEN** | Вердикт Мастера (6 вопросов Q1-Q6 + 3 поправки) |
| USL-1.1-1.6 | Домен-контракты + проекторы + адаптеры + bridge + regression | **GREEN** | 89 тестов; 5 модулей в коде; ADR-O-437 ACTIVE |
| USL-2 PARSED | 100% фрагментов корпуса имеют USL-проекцию | **GREEN** | 363/363, 6/6 NPC |
| USL-2 NORMALIZED | — | **GREEN** | (входит в PARSED — normalizer часть декомпозиции) |
| USL-2 CANONIZED | — | **GREEN** | 363/363 канонизированы |
| USL-2 SEEDED | замок равенства сеялки до/после | **RED** | 11/59 maid_lusya; 3 разрыва блокируют |
| USL-2 COGNITIVELY AVAILABLE | EventMemory доходит до NPC | **UNVERIFIED** | Зависит от USL-2.SEEDED |
| USL-2 USED IN GAME | F5-лаборатория: NPC учитывает прошлое | **UNVERIFIED** | Зависит от USL-2.COGNITIVE |
| USL-3 | Реальные диалоги | **BLOCKED** | Зависит от USL-2 |
| USL-4 | Развитие возможностей | **BLOCKED** | Зависит от USL-2/USL-3 |
| USL-5 | Масштабирование | **BLOCKED** | Зависит от USL-4 |

---

## 2. Таблица соответствия требований → production-коду

| Требование USL | Production-файл | Строки | Тест | Статус |
|---|---|---|---|---|
| USLUnit + 16 типов | `backend/app/domain/usl.py` | весь файл | `test_usl_types.py` (21) | ✅ |
| BiographyAdapter | `backend/app/services/chronicle/biography_adapter.py` | `biography_to_usl`, `entry_to_usl_unit`, `_extract_temporal` | `test_usl_biography_adapter.py` (29) | ✅ |
| InteractiveLanguageAdapter | `backend/app/services/input/interactive_language_adapter.py` | `intent_to_usl_unit`, `_proposition_to_usl_event` | `test_usl_interactive_adapter.py` (22) | ✅ |
| USL-1.4 Free ASSERT path | `backend/app/services/events/claim_event_subscriber.py` | 123-148 | `test_usl_free_assert.py` (10) | ✅ |
| USL-1.5 CanonicalRegistry bridge | `backend/app/services/input/intent_compressor.py` | 432-461 | `test_usl_canonical_bridge.py` (7) | ✅ |
| USL-1.6 DTO Registry §15 | `docs/DTO Registry (Реестр контрактов).md` | 706-725 | documentation closure | ✅ |
| ADR-O-437 | `docs/ADR (Architecture Decision Records).md` | 845-849 | ACTIVE | ✅ |
| IMPACT | `docs/audits/ADR-O-437_IMPACT.md` | весь файл | R3 (S410) | ✅ |

**Итого USL-1:** 5 production-модулей, 89 тестов, ADR ACTIVE, DTO Registry зарегистрирован. **Полностью подтверждён.**

---

## 3. Карта всех зависимостей

```
USL-2 SEEDED (БЛОКИРОВАН)
├── Разрыв 1: RELATIONSHIP → 0 (object_id пуст)
│   ├── Корень: decomposition_normalizer.py НЕ вызывает resolve_object_ref_from_roster
│   ├── resolve_object_ref_from_roster вызывается ТОЛЬКО в routes_chronicle.py:479
│   ├── maid_lusya.json: 0 open_questions, 0 resolved_questions (вопросы не созданы)
│   └── Зависимость: CCH-8 (resolve_object_ref_from_roster) + CCH-3 (/resolve UI)
│
├── Разрыв 2: EFFECT trauma → 0 (triggers отсутствует)
│   ├── Корень: triggers НЕ в промпте (chronicle_decompose_system.txt:27)
│   ├── Корень: triggers НЕ в GBNF (config/chronicle_decompose.gbnf — permissive)
│   ├── Корень: normalizer не извлекает triggers из summary
│   └── Зависимость: CCH-2 (промпт + GBNF) + пере-декомпозиция
│
├── Разрыв 3: BELIEF_SEED → 0 (belief_type отсутствует)
│   ├── Корень: belief_type В промпте (строки 29-31, 362-364), но LLM не извлекает
│   ├── Корень: GBNF не валидирует наличие belief_type
│   ├── Корень: BeliefType реестр узкий (2 значения: danger, player_hostile)
│   └── Зависимость: CCH-2 (промпт few-shot) + возможно расширение BeliefType
│
├── Разрыв A (новый): temporal 1/363 в biography
│   ├── Корень: декомпозиция не заполняет historical_age/duration_years структурированно
│   ├── biography_adapter._extract_temporal зависит от заполненных полей
│   ├── 33 entries имеют возрастной маркер в text_span, но пустой temporal
│   └── Зависимость: USL-1.5+ Temporal Extractor для biography
│
├── Разрыв B (новый): game_start_age 1/6
│   ├── Корень: контент автора (5 NPC без game_start_age)
│   ├── Seeder: _day_from_age возвращает SENTINEL_DAY=-1000 при start_age=None
│   └── Зависимость: автор заполняет 5 полей
│
├── Разрыв C (новый): KNOWLEDGE_LINK = 0 во всём корпусе
│   ├── Корень: декомпозиция не извлекает KNOWLEDGE_LINK entries
│   ├── Промпт описывает KNOWLEDGE_LINK, но LLM не использует
│   └── Зависимость: CCH-2 (промпт + few-shot) + авторская разметка
│
├── Разрыв D (новый): EFFECT non-trauma + DESIRE_SEED не сеются
│   ├── Корень: нет функций build_seed_effects (non-trauma) / build_seed_desires
│   ├── TRAIT_SEED + PORTRET — осознанное решение (Character Calibration)
│   └── Зависимость: решение Мастера — нужны ли эти seeder'ы
│
└── Разрыв E (новый): temporal=() в input
    ├── Корень: сознательное ограничение (вердикт Мастера USL-0 поправка 1)
    ├── Тест test_skvoznoy_test_work_for_duration_biography_vs_input ДОПУСКАЕТ это
    ├── Противоречит USL-документу §6.5 (сквозной пример ожидает DURATION(5))
    └── Зависимость: USL-1.5+ Temporal Extractor для input (future work)
```

---

## 4. Полная сквозная карта движения информации

### 4.1. Цепочка SOURCE TEXT → USED IN GAME (для maid_lusya, 59 entries)

```
SOURCE TEXT (59 entries: 2 PORTRET + 11 EVENT + 9 RELATIONSHIP + 15 EFFECT + 13 TRAIT_SEED + 1 DESIRE_SEED + 8 BELIEF_SEED)
    │
    ↓ BiographyDecomposer.decompose (LLM + GBNF)
    │
PARSED (DecompositionItem с draft_payload)
    │
    ↓ ChronicleDecompositionNormalizer.normalize
    │  ├── Мембраны: vague-relation, self-ref, roster-mismatch
    │  ├── Создание ClarificationQuestion (но 0 в maid_lusya.json!)
    │  └── НЕ вызывает resolve_object_ref_from_roster ← РАЗРЫВ 1 корень
    │
NORMALIZED (DecompositionItem с payload, но object_id пустой для RELATIONSHIP)
    │
    ↓ routes_chronicle.py:479 (resolve_object_ref_from_roster) — ТОЛЬКО через API
    │  ├── Вызывается при POST /decompose
    │  ├── НЕ вызывается при redecompose_all_npc.py (напрямую через BiographyDecomposer)
    │  └── maid_lusya.json: 0 open_questions → возможно создан до CCH-8 или скриптом
    │
CANONIZED (59 entries в config/npc/chronicles/maid_lusya.json, provenance=AUTHOR_CONFIRMED)
    │
    ↓ biography_to_usl (USL-1.2, pure projector)
    │
USL PROJECTION (59 USLUnit, 363==363 GREEN)
    │  ├── temporal: 1/59 (только 1 entry с historical_age=5)
    │  ├── relations: 9/59 (RELATIONSHIP → USLRelation, но object_id="unknown")
    │  ├── causal: 0/59 (biography_adapter не строит USLCausalLink)
    │  └── USL-2 source_kind: 59 AUTHOR_CANON ✅
    │
    ↓ chronicle_seeder.build_seed_* (npc_loader new-game гейт)
    │
SEEDED (11/59 → EventMemory)
    │  ├── EVENT: 11/11 → EventMemory (10 с SENTINEL_DAY=-1000, 1 с реальным day)
    │  ├── RELATIONSHIP: 0/9 → relationship_cache (РАЗРЫВ 1: object_id пуст)
    │  ├── EFFECT trauma: 0/3 → affective_imprints (РАЗРЫВ 2: triggers отсутствует)
    │  ├── BELIEF_SEED: 0/8 → psyche.beliefs (РАЗРЫВ 3: belief_type отсутствует)
    │  ├── EFFECT non-trauma: 0/12 → нет функции (РАЗРЫВ D)
    │  ├── TRAIT_SEED: 0/13 → осознанное решение (Character Calibration)
    │  ├── PORTRET: 0/2 → future work (агрегация traits)
    │  └── DESIRE_SEED: 0/1 → нет функции (РАЗРЫВ D)
    │
    ↓ MemoryManager.apply / BeliefState / relationship_cache
    │
COGNITIVELY AVAILABLE (UNVERIFIED)
    │  └── Зависит от SEEDED — 11 EventMemory с 10 sentinel-day
    │
    ↓ DecisionHub / VerbalizationContext / DialogueExecutor
    │
USED IN GAME (UNVERIFIED)
    └── Зависит от COGNITIVE — F5-лаборатория не проводилась
```

### 4.2. Итог: 19% entries доходят до когнитивных структур

Из 59 entries maid_lusya:
- **11 EventMemory** (19%) — доходят, но 10 с sentinel-day («когда-то в прошлом»)
- **48 entries (81%)** — теряются по разрывам 1-3 + D

---

## 5. Все обнаруженные разрывы

### 5.1. Разрыв 1 (известный): RELATIONSHIP → 0 (неразрешённые сущности)

**Симптом:** 9/9 RELATIONSHIP entries maid_lusya отклонены seeder'ом («связь на неразрешённую сущность»).

**Корневая причина (расшифрована аудитом):**
- `decomposition_normalizer.py:normalize` (строки 261-420) **НЕ вызывает** `resolve_object_ref_from_roster`
- `resolve_object_ref_from_roster` вызывается ТОЛЬКО в `routes_chronicle.py:479` (API endpoint `POST /decompose`)
- `maid_lusya.json` имеет `open_questions: 0` и `resolved_questions: 0` — normalizer не создал вопросы, и/или канон создан до фикса CCH-8
- Все 9 RELATIONSHIP entries имеют `target_hint` («стражник Борко», «Торнин», «Гильдия воров»), но `object_id` пустой

**Точная механика:**
- `chronicle_seeder.py:284`: `tgt = _resolved_npc_id(e.object_id)` — возвращает npc_id только если `ref_kind=RESOLVED`
- `object_id` пустой → `_resolved_npc_id` возвращает None → warning + continue

**Доказательство:**
- `maid_lusya.json` E4: все 9 RELATIONSHIP entries имеют пустой `object_id`
- `decomposition_normalizer.py` G1: `resolve_object_ref_from_roster` определена (строка 224), но не вызывается в `normalize`
- H3: единственный production-вызов — `routes_chronicle.py:479`

**Владелец:** CCH (нормализатор + routes_chronicle).

**Предлагаемое решение:**
1. Вызов `resolve_object_ref_from_roster` добавить в `normalize` (после мембран) — чтобы object_id заполнялся при декомпозиции, а не только через API
2. Пере-декомпозиция maid_lusya через `redecompose_all_npc.py` (если скрипт использует normalizer) или через API
3. Альтернатива: `redecompose_all_npc.py` должен вызывать `routes_chronicle.decompose_fragment`, а не `BiographyDecomposer.decompose` напрямую

**Критерий приёмки:**
- maid_lusya.json: ≥4 RELATIONSHIP entries с `object_id.ref_kind=RESOLVED` (Борко, Торнин, Орм)
- `relationship_cache` maid_lusya после seeder: ≥4 записей
- Замок: `seeded relationships > 0`
- Регрессия: IPT зелёный

### 5.2. Разрыв 2 (известный): EFFECT trauma → 0 (нет triggers)

**Симптом:** 3/3 trauma-EFFECT entries maid_lusya отклонены seeder'ом («trauma без triggers»).

**Корневая причина:**
- `chronicle_decompose_system.txt:27` — EFFECT payload schema: `{summary, effect_kind, target_hint}` — **`triggers` не упомянут**
- `config/chronicle_decompose.gbnf` — permissive JSON, не описывает payload структуру
- `decomposition_normalizer.py` — не извлекает `triggers` из summary
- `chronicle_seeder.py:321` — ожидает `payload.get("triggers")` (список)

**Доказательство:**
- D3 (промпт): `triggers` не найден в схеме EFFECT
- D4 (GBNF): `triggers` не найден (GBNF permissive)
- E3 (maid_lusya.json): все 3 trauma-EFFECT имеют payload `{summary, effect_kind, target_hint}` — без `triggers`

**Владелец:** CCH (промпт + GBNF + normalizer).

**Предлагаемое решение:**
1. Добавить `triggers` в промпт: для `effect_kind=trauma` извлекать список тегов (звуки, запахи, ситуации)
2. Добавить `triggers` в GBNF (опциональное поле в EFFECT payload)
3. Добавить few-shot example в промпт: «звон посуды → вздрагивание» → `triggers: ["звон посуды", "гремящие звуки"]`
4. Пере-декомпозиция maid_lusya

**Альтернатива:** Если автор не указал триггеры явно — оставить `triggers=[]` (честный отказ). Но автор должен иметь возможность добавить их через Character Debugger (CCH-4).

**Критерий приёмки:**
- maid_lusya.json: ≥1 trauma-EFFECT с `payload.triggers` (список тегов)
- `affective_imprints` после seeder: ≥1 запись с `decay_rate=0`
- Замок: `seeded imprints > 0`

### 5.3. Разрыв 3 (известный): BELIEF_SEED → 0 (belief_type отсутствует)

**Симптом:** 8/8 BELIEF_SEED entries maid_lusya имеют payload `{statement: "..."}` без `belief_type`.

**Корневая причина:**
- `chronicle_decompose_system.txt:29-31` — промпт требует `belief_type: <danger|player_hostile>`
- `config/chronicle_decompose.gbnf` — не валидирует наличие `belief_type`
- LLM (Hermes-3) игнорирует инструкцию промпта — не извлекает `belief_type`
- `chronicle_seeder.py:357` — ожидает `payload.get("belief_type")` в реестре `BeliefType`

**Доказательство:**
- D1: `BeliefType` реестр = 2 значения (`danger`, `player_hostile`)
- D3: промпт строки 29-31, 362-364 явно требуют `belief_type`
- E2: все 8 BELIEF_SEED maid_lusya имеют `{statement: "..."}` — без `belief_type`

**Владелец:** CCH (промпт + few-shot) + возможно расширение BeliefType.

**Предлагаемое решение:**
1. Добавить few-shot example в промпт: показывать BELIEF_SEED с `belief_type` явно
2. Усилить инструкцию: «ОБЯЗАТЕЛЬНО включай `belief_type` в BELIEF_SEED»
3. В normalizer: fail-loud проверка — BELIEF_SEED без `belief_type` → warning (не error)
4. Пере-декомпозиция maid_lusya
5. Если LLM продолжает игнорировать — ручная правка через Character Debugger (CCH-4)

**Альтернатива:** Расширить `BeliefType` (мини-ADR) — но это требует решения Мастера (какие типы убеждений нужны миру).

**Критерий приёмки:**
- maid_lusya.json: ≥1 BELIEF_SEED с `payload.belief_type` в реестре
- `psyche.beliefs` после seeder: ≥1 запись
- Замок: `seeded beliefs > 0`

### 5.4. Разрыв A (новый): temporal 1/363 в biography

**Симптом:** Только 1/363 entries корпуса имеют structured temporal (maid_lusya, age=5).

**Корневая причина:**
- `biography_adapter._extract_temporal` извлекает время из `historical_age`/`historical_year`/`payload.day`/`payload.duration_years`/`KP_LEARNED_AGE`
- Декомпозиция не заполняет эти поля структурированно (только 1/363 имеет `historical_age`)
- 33 entries имеют возрастной маркер в `text_span` («57 лет», «в 24 застал»), но не в structured полях

**Доказательство:**
- F4: `usl2_corpus_all.py` — `age-marker lost: 33 entries`
- D5: `usl2_pilot_lusya.py` — `units with temporal: 1/59 (1%)`

**Владелец:** CCH (декомпозиция) + USL (Temporal Extractor для biography).

**Предлагаемое решение:**
1. Расширить `extract_age_anchors_typed` (age_anchor.py) или добавить post-normalize шаг
2. Извлекать `duration_years` из текста («пять лет работал» → `duration_years=5`)
3. Заполнять `historical_age` из возрастных якорей

**Критерий приёмки:**
- Корпус: temporal coverage ≥30% (с 1/363 до ~110/363)
- Замок: `units with temporal > 30`

### 5.5. Разрыв B (новый): game_start_age 1/6

**Симптом:** Только maid_lusya имеет `game_start_age=14`. У 5 NPC `game_start_age=null`.

**Корневая причина:** Контент автора — автор не указал возраст 5 NPC на момент игры.

**Доказательство:**
- TZ находка B
- `chronicle_seeder._day_from_age`: при `start_age=None` возвращает `SENTINEL_DAY=-1000`

**Владелец:** Автор (контент).

**Предлагаемое решение:** Автор заполняет `game_start_age` для 5 NPC (blacksmith_orm, guard_borko, merchant_goran, tavern_keeper_tornin, thief_shadow).

**Критерий приёмки:** 6/6 NPC с `game_start_age`.

### 5.6. Разрыв C (новый): KNOWLEDGE_LINK = 0 во всём корпусе

**Симптом:** 0 KNOWLEDGE_LINK entries во всех 6 канонах.

**Корневая причина:**
- Декомпозиция не извлекает KNOWLEDGE_LINK (кто что знает и откуда)
- Промпт описывает KNOWLEDGE_LINK, но LLM не использует
- `build_seed_knowledge` существует, но не вызывается (нет entries для обработки)

**Доказательство:**
- F4: USLPredicate distribution — `knows: 0`
- `chronicle_seeder.build_seed_knowledge` (строки 207-271) — реализован, но 0 entries

**Владелец:** CCH (промпт + few-shot) + автор (разметка).

**Предлагаемое решение:**
1. Добавить few-shot example в промпт для KNOWLEDGE_LINK
2. Автор отмечает в тексте, кто что знает
3. Пере-декомпозиция

**Критерий приёмки:** ≥1 KNOWLEDGE_LINK в корпусе.

### 5.7. Разрыв D (новый): EFFECT non-trauma + DESIRE_SEED не сеются

**Симптом:** 12 EFFECT non-trauma + 1 DESIRE_SEED maid_lusya не имеют seeder-функций.

**Корневая причина:**
- Нет `build_seed_effects` (non-trauma: loss/gain/secret/skill/residence/guardianship/occupation/custom)
- Нет `build_seed_desires`
- TRAIT_SEED + PORTRET — осознанное решение (Character Calibration ADR)

**Владелец:** Решение Мастера — нужны ли эти seeder'ы.

**Предлагаемое решение:** Решение Мастера:
- (a) Добавить `build_seed_effects` для non-trauma (если эффекты должны влиять на стартовое состояние)
- (b) Добавить `build_seed_desires` (если желания должны сеяться)
- (c) Оставить как есть (если эти entries только для контекста)

**Критерий приёмки:** Решение Мастера по каждому виду.

### 5.8. Разрыв E (новый): temporal=() в input

**Симптом:** `intent_to_usl_unit` всегда возвращает `temporal=()`.

**Корневая причина:**
- Сознательное ограничение (вердикт Мастера USL-0 поправка 1)
- `extract_age_anchors_typed` не готов как универсальный экстрактор
- Тест `test_skvoznoy_test_work_for_duration_biography_vs_input` допускает `temporal=()`

**Противоречие:** USL-документ §6.5 сквозной пример ожидает `DURATION(5)` для input.

**Владелец:** USL (Temporal Extractor для input).

**Предлагаемое решение:**
1. Реализовать `extract_temporal_from_text(raw_text)` для input (future work, не блокер USL-2)
2. Применить в `intent_to_usl_unit`

**Критерий приёмки:** `test_skvoznoy_test_work_for_duration_biography_vs_input` — input имеет `DURATION(5)`.

---

## 6. Противоречия между ТЗ, ADR, roadmap и кодом

### 6.1. Противоречие 1: USL-1 инвариант vs temporal=() в input

| Источник | Утверждение |
|---|---|
| USL-документ §3.4 USL-1 | «одна и та же смысловая конструкция даёт совместимые USLUnit» |
| USL-документ §6.5 сквозной пример | input «Я пять лет работал на тебя» → `DURATION(5)` |
| Код `interactive_language_adapter.py` | `temporal=()` (честный empty) |
| Тест `test_skvoznoy_test_work_for_duration_biography_vs_input` | Допускает `temporal=()` с пометкой "USL-1.4 закроет" |

**Вердикт:** USL-1 инвариант **не доказан для времени**. Тест фиксирует текущее ограничение, но противоречит §6.5. Нужно либо реализовать Temporal Extractor (разрыв E), либо явно зафиксировать в USL-документе, что temporal для input — future work.

### 6.2. Противоречие 2: USLPredicate реестр vs Predicate.INSULTED

| Источник | Утверждение |
|---|---|
| USL-документ §4.3 | «закрытый реестр USLPredicate, расширение = мини-ADR» |
| `domain/usl.py` USLPredicate | 15 значений, **нет INSULTED** |
| `domain/epistemology.py:37` Predicate | **INSULTED = "insulted"** (добавлен COGNITIVE-CONTINUITY-01) |
| `interactive_language_adapter.py:38` _ACT_TYPE_TO_USL | `"INSULT": USLPredicate.ATTACKED` (fallback) |
| `claim_event_subscriber.py:103-122` | Ветка PLAYER_INSULTS → `Predicate.INSULTED` |

**Вердикт:** COGNITIVE-CONTINUITY-01 расширил `Predicate`, но не обновил `USLPredicate`. Маппинг INSULT → ATTACKED — reasonable fallback, но **нарушает USL-документ §4.3** (закрытый реестр). Нужно мини-ADR: добавить `USLPredicate.INSULTED` или явно зафиксировать fallback.

### 6.3. Противоречие 3: resolve_object_ref_from_roster — где должен вызываться?

| Источник | Утверждение |
|---|---|
| `decomposition_normalizer.py:224` | Функция определена, docstring: «COV-10.4» |
| `decomposition_normalizer.py:normalize` | **НЕ вызывает** `resolve_object_ref_from_roster` |
| `routes_chronicle.py:479` | Единственный production-вызов |
| `test_cch8_object_id_resolution.py` | Тестирует функцию, но не её вызов в normalizer |

**Вердикт:** `resolve_object_ref_from_roster` — **полумёртвый код** (вызывается только через API, не в normalizer). Это причина разрыва 1: каноны, созданные через `redecompose_all_npc.py` (напрямую через BiographyDecomposer), не получают резолв `object_id`.

### 6.4. Противоречие 4: USL-2 source_kind check в usl2_pilot_lusya.py

| Источник | Утверждение |
|---|---|
| `usl2_pilot_lusya.py` вывод D5 | `USL-2 (source kind): 59 non-AUTHOR_CANON (expected 0)` |
| `usl2_pilot_lusya.py` вывод D5 | `author_canon: 59` (выше в выводе) |
| `usl2_corpus_all.py` вывод F4 | `USL-2 source kind: GREEN (0 non-author)` |

**Вердикт:** `usl2_pilot_lusya.py` имеет баг в проверке USL-2 (показывает 59 non-AUTHOR_CANON при 59 AUTHOR_CANON). `usl2_corpus_all.py` проверяет корректно. Это **баг в пилотном скрипте**, не в USL.

---

## 7. Реальные результаты тестов и прогонов

### 7.1. USL pytest (5 файлов, 89 тестов)

```
tests/micro/test_usl_types.py                    — 21 PASSED
tests/micro/test_usl_biography_adapter.py        — 29 PASSED
tests/micro/test_usl_interactive_adapter.py      — 22 PASSED
tests/micro/test_usl_free_assert.py              — 10 PASSED
tests/micro/test_usl_canonical_bridge.py         —  7 PASSED
=================================================
ИТОГО: 89 passed, 2 warnings in 0.63s
```

### 7.2. usl2_pilot_lusya.py (maid_lusya, 59 entries)

```
author_canon: 59
units with temporal:  1/59 (1%)
units with relations: 9/59 (15%)
units with causal:    0/59 (0%)
USL-2 (source kind): 59 non-AUTHOR_CANON (expected 0)  ← баг скрипта
USL-5 (text_span):   0 units without span
USL-6 (determinism): re-run identical = True
canon entries with historical_age: 1/59
usl units with temporal:           1/59
match: True
```

### 7.3. usl2_corpus_all.py (6 NPC, 363 entries)

```
Замок равенства:    GREEN (363==363)
USL-2 source kind:  GREEN (0 non-author)
USL-6 determinism:  GREEN
Temporal match:     GREEN (canon 1 == usl 1)
age-marker lost:    33 entries
USLPredicate distribution:
  asserts: 112, has_effect: 110, has_trait: 98, believes: 34, lives_at: 8, desires: 1
  (knows: 0 — KNOWLEDGE_LINK отсутствует)
```

### 7.4. usl2_seeded_lusya.py (SEEDED-фаза maid_lusya)

```
build_seed_memories:    EventMemory count: 11 (10 SENTINEL_DAY=-1000, 1 реальный)
build_seed_relationships: 0 entries  ← РАЗРЫВ 1
build_seed_beliefs:     ERROR (API drift в скрипте: build_seed_beliefs(doc), не (npc_id, doc))  ← РАЗРЫВ 3
build_seed_imprints:    0 entries  ← РАЗРЫВ 2

[DOC] maid_lusya: 59 entries, game_start_age=14
```

### 7.5. maid_lusya.json статистика

```
Total entries: 59
  PORTRET: 2      ← не сеётся (агрегация traits — future work)
  EVENT: 11       ← сеётся (11/11, но 10 с SENTINEL_DAY)
  RELATIONSHIP: 9 ← НЕ сеётся (разрыв 1)
  EFFECT: 15      ← trauma (3) не сеются (разрыв 2); non-trauma (12) нет функции (разрыв D)
  TRAIT_SEED: 13  ← осознанное решение (Character Calibration)
  DESIRE_SEED: 1  ← нет функции (разрыв D)
  BELIEF_SEED: 8  ← НЕ сеются (разрыв 3)
game_start_age: 14  ← единственный NPC с game_start_age (разрыв B)
open_questions: 0   ← критическая находка (вопросы не созданы)
resolved_questions: 0
```

### 7.6. IPT baseline

```
ИТОГО: 54 passed / 0 skipped / 0 failed (0 CRITICAL) | [KILLER_SPIRIT] убито=0, пощажено=2
✅ ВСЕ ИНВАРИАНТЫ ПРОЙДЕНЫ — игра жива.
```

---

## 8. Разделение проблем по критичности

### 🔴 CRITICAL (блокеры USL-2.SEEDED)

| Разрыв | Влияние | Сложность |
|---|---|---|
| 1. RELATIONSHIP → 0 | NPC не получает стартовые отношения (9/9 теряются) | Средняя (вызов resolve_object_ref_from_roster в normalizer) |
| 2. EFFECT trauma → 0 | NPC не получает травматические импринты (3/3 теряются) | Средняя (промпт + GBNF + пере-декомпозиция) |
| 3. BELIEF_SEED → 0 | NPC не получает убеждения (8/8 теряются) | Низкая (few-shot в промпт + пере-декомпозиция) |

### 🟡 HIGH (снижают качество USL-2, но не блокируют)

| Разрыв | Влияние | Сложность |
|---|---|---|
| A. temporal 1/363 | 33 entries теряют временные конструкции | Высокая (Temporal Extractor для biography) |
| B. game_start_age 1/6 | 5 NPC получают SENTINEL_DAY для всех events | Низкая (контент автора) |
| D. EFFECT non-trauma + DESIRE_SEED | 13 entries не сеются | Решение Мастера |

### 🟢 MEDIUM (противоречия, не блокирующие)

| Разрыв | Влияние | Сложность |
|---|---|---|
| E. temporal=() в input | USL-1 инвариант не доказан для времени | Высокая (Temporal Extractor для input) |
| C. KNOWLEDGE_LINK = 0 | Канал знания не используется | Высокая (промпт + автор) |
| Противоречие 2 (INSULTED) | USLPredicate отстаёт от Predicate | Низкая (мини-ADR) |
| Противоречие 4 (баг скрипта) | Неверная статистика USL-2 в пилоте | Низкая (фикс скрипта) |

---

## 9. Предлагаемый единый план устранения проблем

### 9.1. Фаза 1: Фиксы разрывов 1-3 (блокеры USL-2.SEEDED)

**Работа 1.1: resolve_object_ref_from_roster в normalizer (Разрыв 1)**
- Файл: `backend/app/services/chronicle/decomposition_normalizer.py`
- Изменение: в `normalize` после мембран (строка ~416) вызвать `resolve_object_ref_from_roster(hint, roster)` для RELATIONSHIP/EFFECT и заполнить `object_id`
- Зависимость: нет
- Критерий: `test_cch8_object_id_resolution.py` расширенный; пере-декомпозиция maid_lusya → ≥4 RELATIONSHIP с RESOLVED object_id

**Работа 1.2: triggers в промпт + GBNF (Разрыв 2)**
- Файлы: `backend/prompts/chronicle_decompose_system.txt`, `config/chronicle_decompose.gbnf`
- Изменение: добавить `triggers` в EFFECT payload schema (для `effect_kind=trauma`); few-shot example
- Зависимость: нет
- Критерий: пере-декомпозиция maid_lusya → ≥1 trauma-EFFECT с `triggers`

**Работа 1.3: belief_type few-shot в промпт (Разрыв 3)**
- Файл: `backend/prompts/chronicle_decompose_system.txt`
- Изменение: усилить инструкцию + few-shot example с явным `belief_type`
- Зависимость: нет
- Критерий: пере-декомпозиция maid_lusya → ≥1 BELIEF_SEED с `belief_type` в реестре

**Работа 1.4: Пере-декомпозиция корпуса**
- Скрипт: `scripts/redecompose_all_npc.py` (проверить, использует ли normalizer)
- Зависимость: работы 1.1-1.3
- Критерий: 6 NPC канонов обновлены; maid_lusya имеет RESOLVED object_id + triggers + belief_type

**Работа 1.5: Фикс usl2_seeded_lusya.py (API drift)**
- Файл: `scripts/usl2_seeded_lusya.py`
- Изменение: `build_seed_beliefs(doc)` вместо `build_seed_beliefs(npc_id, doc)`
- Зависимость: нет
- Критерий: скрипт работает без TypeError

### 9.2. Фаза 2: Замок SEEDED GREEN

**Работа 2.1: Перепрогон usl2_seeded_lusya.py**
- Зависимость: Фаза 1 (работы 1.1-1.5)
- Критерий:
  - `seeded EventMemory ≥ 11`
  - `seeded relationships > 0`
  - `seeded beliefs > 0`
  - `seeded imprints > 0`

### 9.3. Фаза 3: COGNITIVELY AVAILABLE

**Работа 3.1: Проверка MemoryManager.apply**
- Зависимость: Фаза 2
- Критерий: EventMemory с честным `day` доходит до `WorkingMemory`

**Работа 3.2: Заполнение game_start_age (Разрыв B)**
- Владелец: автор
- Критерий: 6/6 NPC с `game_start_age`

### 9.4. Фаза 4: USED IN GAME (F5-лаборатория)

**Работа 4.1: F5-сценарии**
- Сценарии:
  - NPC реагирует на Орма иначе (relationship_cache заполнен)
  - Люся знает про тайный ход (KNOWLEDGE_LINK — после разрыва C)
  - NPC не знает того, чего не мог знать (изоляция knowledge)
- Зависимость: Фаза 3
- Критерий: F5-сценарии GREEN

### 9.5. Фаза 5: Закрытие USL-2

**Работа 5.1: Отчёт покрытия корпуса**
- Зависимость: Фаза 4
- Критерий: отчёт с счётчиками по звеньям статусной цепочки

**Работа 5.2: Замок равенства сеялки до/после**
- Зависимость: Фаза 4
- Критерий: seed до/после USL — идентичный

### 9.6. Фаза 6: Противоречия и не-блокеры

**Работа 6.1: Мини-ADR USLPredicate.INSULTED (Противоречие 2)**
- Зависимость: нет
- Критерий: либо INSULTED добавлен в USLPredicate, либо fallback зафиксирован

**Работа 6.2: Фикс usl2_pilot_lusya.py USL-2 check (Противоречие 4)**
- Зависимость: нет
- Критерий: корректная статистика USL-2

**Работа 6.3: Temporal Extractor для biography (Разрыв A) — future work**
- Зависимость: USL-2 закрыт
- Критерий: temporal coverage ≥30%

**Работа 6.4: Temporal Extractor для input (Разрыв E) — future work**
- Зависимость: USL-3
- Критерий: `test_skvoznoy_test_work_for_duration_biography_vs_input` — input имеет DURATION(5)

**Работа 6.5: KNOWLEDGE_LINK извлечение (Разрыв C) — future work**
- Зависимость: USL-2 закрыт
- Критерий: ≥1 KNOWLEDGE_LINK в корпусе

---

## 10. Последовательность работ с зависимостями и критериями завершения

```
Фаза 1 (блокеры USL-2.SEEDED):
  1.1 resolve_object_ref_from_roster в normalizer ─┐
  1.2 triggers в промпт + GBNF                     │ параллельно
  1.3 belief_type few-shot в промпт                │
  1.5 фикс usl2_seeded_lusya.py API drift          ─┘
                          │
                          ↓
  1.4 Пере-декомпозиция корпуса (зависит от 1.1-1.3)
                          │
                          ↓
Фаза 2: Замок SEEDED GREEN
  2.1 Перепрогон usl2_seeded_lusya.py
     Критерий: relationships>0, beliefs>0, imprints>0
                          │
                          ↓
Фаза 3: COGNITIVELY AVAILABLE
  3.1 Проверка MemoryManager.apply
  3.2 Заполнение game_start_age (автор) — параллельно
                          │
                          ↓
Фаза 4: USED IN GAME (F5-лаборатория)
  4.1 F5-сценарии
     Критерий: NPC учитывает прошлое в поведении
                          │
                          ↓
Фаза 5: Закрытие USL-2
  5.1 Отчёт покрытия корпуса
  5.2 Замок равенства сеялки до/после
     Критерий: USL-2 CLOSED
                          │
                          ↓
Фаза 6 (параллельно, не блокируют USL-2):
  6.1 Мини-ADR USLPredicate.INSULTED
  6.2 Фикс usl2_pilot_lusya.py
  6.3 Temporal Extractor для biography (future)
  6.4 Temporal Extractor для input (future)
  6.5 KNOWLEDGE_LINK извлечение (future)
```

### Критерии завершения USL-2

1. ✅ 100% фрагментов корпуса имеют USL-проекцию (GREEN — 363/363)
2. ✅ USL-2 source_kind = AUTHOR_CANON (GREEN — 363/363)
3. ✅ USL-6 детерминизм (GREEN)
4. ✅ USL-5 text_span провенанс (GREEN — 0 without span)
5. ⏳ Замок равенства сеялки до/после (зависит от Фазы 2)
6. ⏳ Каждая биография имеет заполненную статусную цепочку без разрывов (зависит от Фаз 1-4)
7. ⏳ Игровые проверки в F5-лаборатории (зависит от Фазы 4)

---

## 11. Вердикты Мастера (запрашиваются)

1. **Утвердить 8 разрывов** (3 известных + 5 новых) как единый реестр.
2. **Назначить владельца** для Фазы 1 (фиксы разрывов 1-3 в CCH-контуре) — архитектор USL с расширенным мандатом или владелец CCH.
3. **Приоритет Фазы 1** относительно других задач §0.2.
4. **Решение по разрыву D** (EFFECT non-trauma + DESIRE_SEED): нужны ли seeder-функции.
5. **Решение по разрыву B** (game_start_age): автор заполняет или отложить.
6. **Решение по разрыву A** (temporal 1/363): включить в USL-1.5+ или отдельный трек.
7. **Решение по противоречию 2** (USLPredicate.INSULTED): мини-ADR или fallback зафиксировать.
8. **Расширение BeliefType** (разрыв 3): если LLM не извлекает `danger`/`player_hostile` — расширять реестр или усиливать промпт.

---

## 12. Заключение

**USL как архитектурный фундамент — работает.** 89 тестов GREEN, 6 инвариантов USL-1…USL-6 подтверждены (с оговоркой для temporal), ADR-O-437 ACTIVE, DTO Registry зарегистрирован.

**USL как инструмент доведения смысла до игрового поведения — заблокирован downstream-разрывами в CCH.** Это не дефект USL — это ценность USL-2 как измерителя: он сделал видимыми 3 системных разрыва (RELATIONSHIP/EFFECT-trauma/BELIEF_SEED), которые ранее были скрыты за «декомпозиция успешна».

**Предлагаемый план** (7 работ в Фазе 1 + замок SEEDED в Фазе 2) — устраняет блокеры и разблокирует USL-2.COGNITIVE → USL-2.USED IN GAME. После закрытия USL-2 — переход к USL-3 (реальные диалоги).

**Главный критерий Мастера:** USL должен работать в настоящей игре, а не только проходить тесты. На сегодня USL проходит тесты (89/89), но не работает в игре (11/59 entries доходят до когнитивных структур, 0 игровых проверок проведено). План устраняет этот разрыв.

---

*Документ подготовлен по мандату MASTER DIRECTIVE от 2026-11-04. Археология выполнена read-only, без правок production-кода. Все выводы подтверждены конкретными файлами, строками, тестами и результатами прогонов.*
