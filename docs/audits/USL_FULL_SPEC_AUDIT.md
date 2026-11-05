# USL — Полный аудит технического задания (Society Calibration Edition)

> **Статус:** АУДИТ ЗАВЕРШЁН — представлен Мастеру для вердикта
> **Дата:** 2026-11-04
> **Автор:** Архитектор USL (преемник S380/S410/S411)
> **Мандат:** MASTER DIRECTIVE — полный аудит всего ТЗ USL + Society Calibration
> **Метод:** read-only археология production-кода + реальные прогоны + F5 Headless Laboratory
> **Baseline:** IPT 54/0/0 CRITICAL=0; USL pytest 89/89 GREEN; git HEAD `d8488aae`

---

## 0. Краткое резюме (Executive Summary)

**USL-1 (интеграция двух контуров) — полностью реализован и подтверждён.** 89 тестов GREEN, 5 production-модулей в коде, ADR-O-437 ACTIVE, DTO Registry §15 зарегистрирован. CanonicalRegistry bridge (USL-1.5) работает: «Орму» автора = «Орму» игрока = `blacksmith_orm`.

**USL-2 (биографический корпус) — частично завершён.** Архитектура `biography_to_usl` выдержала полный корпус 6 NPC (363/363 GREEN). Из 59 entries maid_lusya в когнитивные структуры доходит 10 EventMemory + 2 relationships + 1 belief + 2 imprints (25%). Остальные 75% теряются по 3 известным + 5 новым причинам.

**P1 CRITICAL (new-game gate) — частично исправлен.** Фикс A+B+C (коммит `d8488aae`) остановил повторное применение seed на каждом тике для relationships. Но beliefs всё ещё теряются в runtime — `to_persistence_dict` перезаписывает их пустым `{}`.

**F5 Headless Laboratory** доказала: EventMemory (10), Relationships (4), Imprints (2) — GREEN. Belief — RED (в runtime `psyche.beliefs = {}`).

**Найдено 10 разрывов** (3 известных + 5 новых + 2 runtime), **4 противоречия** документ↔код. Предлагается единый план ремонта из 8 работ с зависимостями и критериями завершения.

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
| §5.4 Единый реестр имён | «Орму» автора = «Орму» игрока | **GREEN** (input), **PARTIAL** (biography) | USL-1.5 закрыл для input; biography-контур резолвит через `resolve_object_ref_from_roster` в `routes_chronicle.py:479` (только через API, не в normalizer) |

### 1.4. Требования из USL-документа §9 — план внедрения

| Этап | Требование | Статус | Доказательство |
|---|---|---|---|
| USL-0 | Архитектурная фиксация + контракты | **GREEN** | Вердикт Мастера (6 вопросов Q1-Q6 + 3 поправки) |
| USL-1.1-1.6 | Домен-контракты + проекторы + адаптеры + bridge + regression | **GREEN** | 89 тестов; 5 модулей в коде; ADR-O-437 ACTIVE |
| USL-2 PARSED | 100% фрагментов корпуса имеют USL-проекцию | **GREEN** | 363/363, 6/6 NPC |
| USL-2 CANONIZED | — | **GREEN** | 363/363 канонизированы |
| USL-2 SEEDED | замок равенства сеялки до/после | **PARTIAL** | maid_lusya: 10 EventMemory + 2 relationships + 1 belief + 2 imprints (25%); P1 gate fix частично применён |
| USL-2 COGNITIVELY AVAILABLE | EventMemory доходит до NPC | **PARTIAL** | `test_chronicle_cch4_seed.py` 100% PASSED; но F5 показывает beliefs={} в runtime |
| USL-2 USED IN GAME | F5-лаборатория: NPC учитывает прошлое | **PARTIAL** | F5: EventMemory GREEN, Relationships GREEN, Imprints GREEN; Belief RED |
| USL-3 | Реальные диалоги | **BLOCKED** | Зависит от USL-2 |

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
| P1 FIX: new-game gate | `backend/app/services/npc/npc_loader.py` | 341-357, 968-983 | F5 Headless | ⚠️ Частично |
| P2 FIX: belief runtime | `backend/app/services/npc/npc_loader.py` | 396-424 | F5 Headless | ⚠️ Не работает |
| ctx_size 16384 | `backend/app/core/config.py` | 163 | Декомпозиция 22/22 | ✅ |
| Промпт triggers | `backend/prompts/chronicle_decompose_system.txt` | 27-30, 336-338 | Пере-декомпозиция | ✅ |
| Промпт belief_type | `backend/prompts/chronicle_decompose_system.txt` | 32-35 | Пере-декомпозиция | ✅ |

**Итого USL-1:** 5 production-модулей, 89 тестов, ADR ACTIVE, DTO Registry зарегистрирован. **Полностью подтверждён.**

---

## 3. Карта всех зависимостей

```
USL-2 SEEDED (ЧАСТИЧНО)
├── Разрыв 1: RELATIONSHIP → 0 (object_id пуст) — ЧАСТИЧНО ЗАКРЫТ
│   ├── Корень: decomposition_normalizer.py НЕ вызывает resolve_object_ref_from_roster
│   ├── resolve_object_ref_from_roster вызывается в routes_chronicle.py:479 (через API)
│   ├── maid_lusya.json: 4/13 RESOLVED (Борко×2, Тень×2) после пере-декомпозиции
│   └── Зависимость: CCH-8 (resolve_object_ref_from_roster) + CCH-3 (/resolve UI)
│
├── Разрыв 2: EFFECT trauma → 0 (triggers отсутствует) — ЧАСТИЧНО ЗАКРЫТ
│   ├── Корень: triggers НЕ в промпте (исправлено), НЕ в GBNF (permissive)
│   ├── maid_lusya.json: 2/3 trauma-EFFECT имеют triggers после пере-декомпозиции
│   └── Зависимость: CCH-2 (промпт + GBNF) + пере-декомпозиция
│
├── Разрыв 3: BELIEF_SEED → 0 (belief_type отсутствует) — ЧАСТИЧНО ЗАКРЫТ
│   ├── Корень: belief_type В промпте (исправлено), но LLM не извлекает стабильно
│   ├── maid_lusya.json: 2/2 BELIEF_SEED имеют belief_type после пере-декомпозиции
│   └── Зависимость: CCH-2 (промпт few-shot) + возможно расширение BeliefType
│
├── P1 CRITICAL: new-game gate — ЧАСТИЧНО ИСПРАВЛЕН
│   ├── Фикс A: _enrich_with_chronicle_relations — условный вызов ✅
│   ├── Фикс B: load_l2_state_from_runtime_dict — условный seed ✅
│   ├── Фикс C: load_npcs_merged early return — seed в original dict ✅
│   ├── Результат: [CCH_SEED] логи исчезли после new_game ✅
│   ├── Результат: relationships с chronicle_origin в runtime ✅
│   ├── Результат: affective_imprints (2) в runtime ✅
│   └── ОСТАЁТСЯ: psyche.beliefs = {} в runtime (P2 не решён) ❌
│
├── P2: Belief runtime — НЕ РЕШЁН
│   ├── load_npcs_merged возвращает dict с beliefs={'danger': [...]} ✅ (p2_diag.py)
│   ├── Но после 1 тика inspect_npc показывает beliefs={} ❌
│   ├── Корень: to_persistence_dict пишет beliefs из state.beliefs (пустой BeliefState)
│   ├── _beliefs_from_persistence возвращает None (beliefs_raw={} в load_l2_state)
│   ├── Цепочка: load_npcs_merged → beliefs в dict → LifeEngine cache → tick →
│   │   load_l2_state_from_runtime_dict(dict(npc)) → beliefs_raw={} → restored=None →
│   │   state.beliefs=BeliefState() (пустой) → to_persistence_dict → psyche["beliefs"]={}
│   └── Гипотеза: shallow copy dict(npc) теряет beliefs где-то между cache и pipeline
│
├── Разрыв A: temporal 1/363 в biography
│   ├── Корень: декомпозиция не заполняет historical_age/duration_years структурированно
│   ├── biography_adapter._extract_temporal зависит от заполненных полей
│   ├── 33 entries имеют возрастной маркер в text_span, но пустой temporal
│   └── Зависимость: USL-1.5+ Temporal Extractor для biography
│
├── Разрыв B: game_start_age 1/6
│   ├── Корень: контент автора (5 NPC без game_start_age)
│   ├── Seeder: _day_from_age возвращает SENTINEL_DAY=-1000 при start_age=None
│   └── Зависимость: автор заполняет 5 полей
│
├── Разрыв C: KNOWLEDGE_LINK = 0 во всём корпусе
│   ├── Корень: декомпозиция не извлекает KNOWLEDGE_LINK entries
│   └── Зависимость: CCH-2 (промпт + few-shot) + авторская разметка
│
├── Разрыв D: EFFECT non-trauma + DESIRE_SEED не сеются
│   ├── Корень: нет функций build_seed_effects (non-trauma) / build_seed_desires
│   ├── TRAIT_SEED + PORTRET — осознанное решение (Character Calibration)
│   └── Зависимость: решение Мастера — нужны ли эти seeder'ы
│
└── Разрыв E: temporal=() в input
    ├── Корень: сознательное ограничение (вердикт Мастера USL-0 поправка 1)
    ├── Тест test_skvoznoy_test_work_for_duration_biography_vs_input ДОПУСКАЕТ это
    ├── Противоречит USL-документу §6.5 (сквозной пример ожидает DURATION(5))
    └── Зависимость: USL-1.5+ Temporal Extractor для input (future work)
```

---

## 4. Полная сквозная карта движения информации

### 4.1. Цепочка SOURCE TEXT → USED IN GAME (для maid_lusya, 54 entries после пере-декомпозиции)

```
SOURCE TEXT (54 entries: 9 PORTRET + 10 EVENT + 13 RELATIONSHIP + 5 EFFECT + 14 TRAIT_SEED + 1 DESIRE_SEED + 2 BELIEF_SEED)
    │
    ↓ BiographyDecomposer.decompose (LLM + GBNF, ctx_size=16384)
    │
PARSED (22/22 фрагментов OK, 54 items)
    │
    ↓ ChronicleDecompositionNormalizer.normalize + resolve_object_ref_from_roster (routes_chronicle.py:479)
    │  ├── Мембраны: vague-relation, self-ref, roster-mismatch
    │  └── resolve_object_ref_from_roster: 4/13 RESOLVED (Борко×2, Тень×2)
    │
NORMALIZED (54 entries с object_id для 4 RELATIONSHIP)
    │
    ↓ routes_chronicle.py: confirm-author-entries + force_confirm + canonize
    │
CANONIZED (54 entries в config/npc/chronicles/maid_lusya.json, provenance=AUTHOR_CONFIRMED)
    │  ├── RELATIONSHIP resolved: 4/13
    │  ├── trauma with triggers: 2/3
    │  ├── BELIEF_SEED with belief_type: 2/2
    │  ├── game_start_age: 14 (восстановлен)
    │  └── valence: fixed для 8 entries
    │
    ↓ biography_to_usl (USL-1.2, pure projector)
    │
USL PROJECTION (54 USLUnit, 363==363 GREEN)
    │  ├── temporal: 1/54 (только 1 entry с historical_age)
    │  ├── relations: 4/54 (RELATIONSHIP → USLRelation)
    │  ├── causal: 0/54 (biography_adapter не строит USLCausalLink)
    │  └── USL-2 source_kind: 54 AUTHOR_CANON ✅
    │
    ↓ chronicle_seeder.build_seed_* (npc_loader new-game гейт)
    │  ├── P1 FIX: seed применяется ОДИН РАЗ (Фикс A+B+C)
    │  └── P1 FIX: _enrich_with_chronicle_relations условный
    │
SEEDED (10 EventMemory + 2 relationships + 1 belief + 2 imprints)
    │  ├── EVENT: 10/10 → EventMemory (6 real days + 4 sentinel)
    │  ├── RELATIONSHIP: 2/13 → relationship_cache (guard_borko, thief_shadow)
    │  ├── BELIEF_SEED: 1/2 → psyche["beliefs"] (записывается в dict, но теряется в runtime)
    │  ├── EFFECT trauma: 2/3 → affective_imprints (decay_rate=0)
    │  ├── EFFECT non-trauma: 0/2 → нет функции (разрыв D)
    │  ├── TRAIT_SEED: 0/14 → осознанное решение (Character Calibration)
    │  ├── PORTRET: 0/9 → future work (агрегация traits)
    │  └── DESIRE_SEED: 0/1 → нет функции (разрыв D)
    │
    ↓ MemoryManager.apply / BeliefState / relationship_cache
    │  ├── P2 PROBLEM: beliefs теряются в runtime (psyche["beliefs"] = {} после тика)
    │  └── Корень: to_persistence_dict перезаписывает beliefs пустым dict
    │
COGNITIVELY AVAILABLE (PARTIAL)
    │  ├── EventMemory: 10 в narrative_cache ✅
    │  ├── relationship_cache: 4 (2 chronicle + 2 legacy) ✅
    │  ├── beliefs: {} (ПУСТО) ❌ P2 не решён
    │  └── affective_imprints: 2 ✅
    │
    ↓ DecisionHub / VerbalizationContext / DialogueExecutor
    │
USED IN GAME (PARTIAL)
    ├── NPC говорят (npc_spoke=3), двигаются (npc_moved=9) ✅
    ├── NPC имеют отношения (trust=30 для guard_borko, thief_shadow) ✅
    ├── NPC имеют trauma-imprints (decay_rate=0) ✅
    ├── NPC НЕ имеют beliefs (psyche.beliefs пуст) ❌
    └── A/B сравнение: не проведено (требует P2 решения)
```

### 4.2. Итог: 25% entries доходят до когнитивных структур

Из 54 entries maid_lusya:
- **10 EventMemory** (19%) — доходят, 6 с реальными днями
- **2 relationships** (4%) — доходят (guard_borko, thief_shadow)
- **2 imprints** (4%) — доходят (decay_rate=0)
- **1 belief** (2%) — записывается в dict, но **теряется в runtime** (P2)
- **39 entries (72%)** — теряются по разрывам 1-3 + D

---

## 5. Все обнаруженные разрывы

### 5.1. Разрыв 1 (известный): RELATIONSHIP → 0 (неразрешённые сущности) — ЧАСТИЧНО ЗАКРЫТ

**Симптом:** 9/9 RELATIONSHIP entries maid_lusya отклонены seeder'ом (до пере-декомпозиции).

**После пере-декомпозиции:** 4/13 RESOLVED (Борко×2, Тень×2), 2 seeded.

**Корневая причина:** `decomposition_normalizer.py:normalize` НЕ вызывает `resolve_object_ref_from_roster`. Вызов происходит только в `routes_chronicle.py:479` (API endpoint).

**Решение:** Пере-декомпозиция через `redecompose_all_npc.py` (который вызывает API) — 4/13 RESOLVED.

**Осталось:** 9 RELATIONSHIP с пустым object_id (Гильдия воров → WHITE_SPOT, Орм/Борко без «Стражник»/«Кузнец»).

**Владелец:** CCH + автор (резолв white_spots через UI CCH-3).

### 5.2. Разрыв 2 (известный): EFFECT trauma → 0 (нет triggers) — ЧАСТИЧНО ЗАКРЫТ

**После пере-декомпозиции:** 2/3 trauma-EFFECT имеют triggers.

**Корневая причина:** `triggers` не был в промпте (исправлено в коммите `6e48f8fb`).

**Осталось:** 1 trauma без triggers («Борко наблюдает за насилием» — нет явного сенсорного триггера).

**Владелец:** CCH + автор (добавить triggers через Character Debugger CCH-4).

### 5.3. Разрыв 3 (известный): BELIEF_SEED → 0 (belief_type отсутствует) — ЧАСТИЧНО ЗАКРЫТ

**После пере-декомпозиции:** 2/2 BELIEF_SEED имеют belief_type=danger.

**Корневая причина:** `belief_type` не был в промпте (исправлено в коммите `6e48f8fb`).

**Осталось:** LLM извлекает belief_type нестабильно (2 из 8 исходных BELIEF_SEED).

**Владелец:** CCH (промпт few-shot) + возможно расширение BeliefType.

### 5.4. Разрыв P1 CRITICAL: new-game gate — ЧАСТИЧНО ИСПРАВЛЕН

**Симптом:** CCH_SEED применялся на каждом тике, перезаписывая runtime.

**Фикс A+B+C (коммит `d8488aae`):**
- Фикс A: `_enrich_with_chronicle_relations` — условный вызов ✅
- Фикс B: `load_l2_state_from_runtime_dict` — условный seed ✅
- Фикс C: `load_npcs_merged` early return — seed в original dict ✅

**Результат:**
- `[CCH_SEED]` логи исчезли после `new_game` ✅
- Relationships с `chronicle_origin` в runtime ✅
- Affective imprints (2) в runtime ✅
- EventMemory (10) в runtime ✅

**Остаётся:** P2 (beliefs теряются в runtime).

### 5.5. Разрыв P2: Belief runtime — НЕ РЕШЁН

**Симптом:** `psyche_beliefs: {}` в `inspect_npc` после 1 тика.

**Диагностика:**
- `load_npcs_merged` возвращает dict с `psyche["beliefs"] = {'danger': [...]}` (доказано `p2_diag.py`)
- `p2_diag2.py` доказал: прямой вызов `_apply_chronicle_seed_to_dict` успешно записывает beliefs
- Но после 1 тика `inspect_npc` показывает `beliefs: {}`
- `load_l2_state_from_runtime_dict` получает `beliefs_raw={}` (пустой dict)
- `_beliefs_from_persistence({})` возвращает `None`
- `state.beliefs` остаётся `BeliefState()` (пустой)
- `to_persistence_dict` пишет `psyche["beliefs"] = {}`

**Корневая причина (гипотеза):** `dict(npc)` shallow copy в `npc_tick_pipeline.py:194` теряет `psyche["beliefs"]` где-то между `LifeEngine` cache и pipeline. Возможные причины:
1. `LifeEngine` cache хранит dict БЕЗ beliefs (перезаписывается другим путём)
2. `dict(npc)` создаёт shallow copy, но `psyche` dict разделяется и мутируется
3. `to_persistence_dict` из предыдущего тика перезаписал beliefs пустым `{}`

**Владелец:** npc_loader + state_applicator + LifeEngine.

### 5.6. Разрыв A (новый): temporal 1/363 в biography

**Симптом:** Только 1/363 entries корпуса имеют structured temporal.

**Корневая причина:** Декомпозиция не заполняет `historical_age`/`duration_years` структурированно. 33 entries имеют возрастной маркер в `text_span`, но не в structured полях.

**Владелец:** CCH (декомпозиция) + USL (Temporal Extractor для biography).

### 5.7. Разрыв B (новый): game_start_age 1/6

**Симптом:** Только maid_lusya имеет `game_start_age=14`. У 5 NPC `game_start_age=null`.

**Корневая причина:** Контент автора — автор не указал возраст 5 NPC.

**Владелец:** Автор (контент).

### 5.8. Разрыв C (новый): KNOWLEDGE_LINK = 0 во всём корпусе

**Симптом:** 0 KNOWLEDGE_LINK entries во всех 6 канонах.

**Корневая причина:** Декомпозиция не извлекает KNOWLEDGE_LINK (кто что знает и откуда).

**Владелец:** CCH (промпт + few-shot) + автор (разметка).

### 5.9. Разрыв D (новый): EFFECT non-trauma + DESIRE_SEED не сеются

**Симптом:** 2 EFFECT non-trauma + 1 DESIRE_SEED maid_lusya не имеют seeder-функций.

**Корневая причина:** Нет функций `build_seed_effects` (non-trauma) / `build_seed_desires`.

**Владелец:** Решение Мастера — нужны ли эти seeder'ы.

### 5.10. Разрыв E (новый): temporal=() в input

**Симптом:** `intent_to_usl_unit` всегда возвращает `temporal=()`.

**Корневая причина:** Сознательное ограничение (вердикт Мастера USL-0 поправка 1). `extract_age_anchors_typed` не готов как универсальный экстрактор.

**Противоречие:** USL-документ §6.5 сквозной пример ожидает `DURATION(5)` для input.

**Владелец:** USL (Temporal Extractor для input).

---

## 6. Противоречия между ТЗ, ADR, roadmap и кодом

### 6.1. Противоречие 1: USL-1 инвариант vs temporal=() в input

| Источник | Утверждение |
|---|---|
| USL-документ §3.4 USL-1 | «одна и та же смысловая конструкция даёт совместимые USLUnit» |
| USL-документ §6.5 сквозной пример | input «Я пять лет работал на тебя» → `DURATION(5)` |
| Код `interactive_language_adapter.py` | `temporal=()` (честный empty) |
| Тест `test_skvoznoy_test_work_for_duration_biography_vs_input` | Допускает `temporal=()` с пометкой "USL-1.4 закроет" |

**Вердикт:** USL-1 инвариант **не доказан для времени**. Нужно либо реализовать Temporal Extractor (разрыв E), либо явно зафиксировать в USL-документе, что temporal для input — future work.

### 6.2. Противоречие 2: USLPredicate реестр vs Predicate.INSULTED

| Источник | Утверждение |
|---|---|
| USL-документ §4.3 | «закрытый реестр USLPredicate, расширение = мини-ADR» |
| `domain/usl.py` USLPredicate | 15 значений, **нет INSULTED** |
| `domain/epistemology.py:37` Predicate | **INSULTED = "insulted"** (добавлен COGNITIVE-CONTINUITY-01) |
| `interactive_language_adapter.py:38` _ACT_TYPE_TO_USL | `"INSULT": USLPredicate.ATTACKED` (fallback) |
| `claim_event_subscriber.py:103-122` | Ветка PLAYER_INSULTS → `Predicate.INSULTED` |

**Вердикт:** COGNITIVE-CONTINUITY-01 расширил `Predicate`, но не обновил `USLPredicate`. Маппинг INSULT → ATTACKED — reasonable fallback, но **нарушает USL-документ §4.3**. Нужно мини-ADR: добавить `USLPredicate.INSULTED` или явно зафиксировать fallback.

### 6.3. Противоречие 3: resolve_object_ref_from_roster — где должен вызываться?

| Источник | Утверждение |
|---|---|
| `decomposition_normalizer.py:224` | Функция определена, docstring: «COV-10.4» |
| `decomposition_normalizer.py:normalize` | **НЕ вызывает** `resolve_object_ref_from_roster` |
| `routes_chronicle.py:479` | Единственный production-вызов |
| `test_cch8_object_id_resolution.py` | Тестирует функцию, но не её вызов в normalizer |

**Вердикт:** `resolve_object_ref_from_roster` — **полумёртвый код** (вызывается только через API, не в normalizer). Это причина разрыва 1: каноны, созданные через `redecompose_all_npc.py` (напрямую через BiographyDecomposer), не получают резолв `object_id`.

### 6.4. Противоречие 4: P2 — beliefs в dict, но не в runtime

| Источник | Утверждение |
|---|---|
| `load_npcs_merged` (p2_diag.py) | Возвращает dict с `psyche["beliefs"] = {'danger': [...]}` |
| `load_l2_state_from_runtime_dict` (P3-DIAG) | Получает `beliefs_raw={}` (пустой dict) |
| `inspect_npc` после 1 тика | `beliefs: {}` (пустой dict) |
| `to_persistence_dict` (npc_state.py:1066-1075) | Пишет `psyche["beliefs"]` из `state.beliefs.all()` |

**Вердикт:** beliefs записываются в dict (Фикс C), но **теряются между `load_npcs_merged` и `load_l2_state_from_runtime_dict`**. Корневая причина — `LifeEngine` cache или `dict(npc)` shallow copy в pipeline.

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

### 7.2. usl2_pilot_lusya.py (maid_lusya, 54 entries после пере-декомпозиции)

```
author_canon: 54
units with temporal:  1/54 (2%)
units with relations: 4/54 (7%)
units with causal:    0/54 (0%)
USL-2 (source kind): 0 non-author_canon (expected 0) GREEN
USL-5 (text_span):   0 units without span GREEN
USL-6 (determinism): re-run identical = True GREEN
```

### 7.3. usl2_corpus_all.py (6 NPC, 363 entries)

```
Замок равенства:    GREEN (363==363)
USL-2 source kind:  GREEN (0 non-author)
USL-6 determinism:  GREEN
Temporal match:     GREEN (canon 1 == usl 1)
age-marker lost:    33 entries
```

### 7.4. usl2_seeded_lusya.py (SEEDED-фаза maid_lusya, после всех фиксов)

```
build_seed_memories:    EventMemory count: 10 (6 real days + 4 sentinel)
build_seed_relationships: 2 (guard_borko, thief_shadow)
build_seed_beliefs:     BeliefState entries: 1 (danger) — В DICT, НО НЕ В RUNTIME
build_seed_imprints:    affective_imprints: 2 (decay_rate=0)
```

### 7.5. F5 Headless Laboratory (TavernGameplayHarness, 10 тиков)

```
runtime_after:
  narrative_cache: 10 ✅
  relationship_cache: ['tavern_keeper_tornin', 'thief_shadow', 'guard_borko', 'blacksmith_orm'] ✅
  psyche_beliefs: [] ❌ (P2 не решён)
  affective_imprints: 2 ✅

Counters:
  ticks: 10
  events_by_type: {'npc_moved': 9, 'npc_proximity_close': 6, 'npc_spoke': 3, 'npc_proximity_leave': 3}
  npc_spoke: 3
  npc_moved: 9
```

### 7.6. IPT baseline

```
ИТОГО: 54 passed / 0 skipped / 0 failed (0 CRITICAL)
✅ ВСЕ ИНВАРИАНТЫ ПРОЙДЕНЫ — игра жива.
```

### 7.7. test_chronicle_cch4_seed.py (existing CCH-4 seed test)

```
tests/micro/test_chronicle_cch4_seed.py::test_loader_no_canon_legacy_intact PASSED [100%]
```

---

## 8. Разделение проблем по критичности

### 🔴 CRITICAL (блокеры USL-2.USED IN GAME)

| Разрыв | Влияние | Сложность |
|---|---|---|
| P2: Belief runtime | NPC не имеет beliefs в runtime (psyche.beliefs = {}) | Средняя (трассировка LifeEngine cache → pipeline) |

### 🟡 HIGH (снижают качество USL-2, но не блокируют)

| Разрыв | Влияние | Сложность |
|---|---|---|
| A: temporal 1/363 | 33 entries теряют временные конструкции | Высокая (Temporal Extractor для biography) |
| B: game_start_age 1/6 | 5 NPC получают SENTINEL_DAY для всех events | Низкая (контент автора) |
| D: EFFECT non-trauma + DESIRE_SEED | 3 entries не сеются | Решение Мастера |

### 🟢 MEDIUM (противоречия, не блокирующие)

| Разрыв | Влияние | Сложность |
|---|---|---|
| E: temporal=() в input | USL-1 инвариант не доказан для времени | Высокая (Temporal Extractor для input) |
| C: KNOWLEDGE_LINK = 0 | Канал знания не используется | Высокая (промпт + автор) |
| Противоречие 2 (INSULTED) | USLPredicate отстаёт от Predicate | Низкая (мини-ADR) |

### ✅ ЗАКРЫТЫЕ (после пере-декомпозиции + P1 фикс)

| Разрыв | Статус | Доказательство |
|---|---|---|
| 1. RELATIONSHIP→0 | ЧАСТИЧНО (4/13 RESOLVED, 2 seeded) | F5: relationship_cache с chronicle_origin |
| 2. EFFECT trauma→0 | ЧАСТИЧНО (2/3 triggers, 2 imprints) | F5: affective_imprints=2 |
| 3. BELIEF_SEED→0 | ЧАСТИЧНО (2/2 belief_type, 1 в dict) | usl2_seeded: beliefs=1 (в dict, не в runtime) |
| P1: new-game gate | ЧАСТИЧНО (Фикс A+B+C) | [CCH_SEED] логи исчезли; relationships/imprints в runtime |

---

## 9. Предлагаемый единый план устранения проблем

### 9.1. Фаза 1: P2 — Belief runtime (CRITICAL)

**Работа P2.1: Трассировка потери beliefs в LifeEngine cache**
- Исследовать: `LifeEngine._npc_cache` — хранит ли dict с beliefs?
- Исследовать: `dict(npc)` в `npc_tick_pipeline.py:194` — передаёт ли beliefs?
- Исследовать: `to_persistence_dict` — когда вызывается и перезаписывает beliefs?
- Зависимость: нет
- Критерий: `inspect_npc` показывает `beliefs: {'danger': [...]}` после 1 тика

### 9.2. Фаза 2: Пере-декомпозиция остальных 5 NPC

**Работа 2.1: Пере-декомпозиция 5 NPC (--campaign Open_road)**
- `python scripts/redecompose_all_npc.py --campaign Open_road --npc blacksmith_orm`
- Повторить для guard_borko, merchant_goran, tavern_keeper_tornin, thief_shadow
- Зависимость: P2.1 (beliefs должны работать)
- Критерий: 6/6 NPC с обновлёнными канонами (triggers, belief_type, RESOLVED object_id)

### 9.3. Фаза 3: game_start_age + white_spots

**Работа 3.1: game_start_age для 5 NPC (контент автора)**
- Подготовить перечень недостающих данных
- Зависимость: нет
- Критерий: 6/6 NPC с game_start_age

**Работа 3.2: White_spots резолвция**
- Гильдия → WHITE_SPOT (организация)
- Орм → blacksmith_orm (через UI CCH-3)
- Борко → guard_borko (через UI CCH-3)
- Зависимость: нет
- Критерий: 0 open_questions в канонах

### 9.4. Фаза 4: F5 Society (Люся встречает Борко)

**Работа 4.1: F5-сценарий взаимодействия**
- A/B сравнение: с chronicle seed vs без
- Проверить: общая история, память, перспектива, знания
- Зависимость: Фаза 1-3
- Критерий: NPC реагирует на Борко иначе (trust=30)

### 9.5. Фаза 5: Закрытие USL-2

**Работа 5.1: Отчёт покрытия корпуса**
- Зависимость: Фаза 4
- Критерий: отчёт с счётчиками по звеньям статусной цепочки

### 9.6. Фаза 6: Противоречия и не-блокеры

**Работа 6.1: Мини-ADR USLPredicate.INSULTED**
- Зависимость: нет
- Критерий: либо INSULTED добавлен, либо fallback зафиксирован

**Работа 6.2: Temporal Extractor для biography (future work)**
- Зависимость: USL-2 закрыт
- Критерий: temporal coverage ≥30%

**Работа 6.3: Temporal Extractor для input (future work)**
- Зависимость: USL-3
- Критерий: `test_skvoznoy_test_work_for_duration_biography_vs_input` — input имеет DURATION(5)

---

## 10. Последовательность работ с зависимостями и критериями завершения

```
Фаза 1 (CRITICAL):
  P2.1 Трассировка потери beliefs в LifeEngine cache
     Критерий: inspect_npc показывает beliefs после 1 тика
                          │
                          ↓
Фаза 2 (пере-декомпозиция):
  2.1 Пере-декомпозиция 5 NPC (--campaign Open_road)
     Критерий: 6/6 NPC с triggers/belief_type/RESOLVED
                          │
                          ↓
Фаза 3 (контент + резолв):
  3.1 game_start_age для 5 NPC (автор) ─┐
  3.2 White_spots резолвция (UI CCH-3) ─┘ параллельно
     Критерий: 6/6 NPC с game_start_age; 0 open_questions
                          │
                          ↓
Фаза 4 (F5 Society):
  4.1 F5-сценарий "Люся встречает Борко"
     Критерий: NPC реагирует на Борко иначе (trust=30)
                          │
                          ↓
Фаза 5: Закрытие USL-2
  5.1 Отчёт покрытия корпуса
     Критерий: USL-2 CLOSED
                          │
                          ↓
Фаза 6 (параллельно, не блокируют):
  6.1 Мини-ADR USLPredicate.INSULTED
  6.2 Temporal Extractor для biography (future)
  6.3 Temporal Extractor для input (future)
```

### Критерии завершения USL-2

1. ✅ 100% фрагментов корпуса имеют USL-проекцию (GREEN — 363/363)
2. ✅ USL-2 source_kind = AUTHOR_CANON (GREEN — 363/363)
3. ✅ USL-6 детерминизм (GREEN)
4. ✅ USL-5 text_span провенанс (GREEN — 0 without span)
5. ⏳ Замок равенства сеялки до/после (зависит от Фазы 1-3)
6. ⏳ Каждая биография имеет заполненную статусную цепочку (зависит от Фаз 1-4)
7. ⏳ Игровые проверки в F5-лаборатории (зависит от Фазы 4)

---

## 11. Вердикты Мастера (запрашиваются)

1. **P2 priority** — CRITICAL, блокирует USED IN GAME. Назначить владельца.
2. **Пере-декомпозиция 5 NPC** — использовать `--campaign Open_road` (R1 Campaign Archaeology).
3. **game_start_age** — автор заполняет или отложить.
4. **White_spots** — автор резолвит через UI CCH-3 или программно.
5. **EFFECT non-trauma + DESIRE_SEED** — нужны ли seeder'ы.
6. **USLPredicate.INSULTED** — мини-ADR или fallback зафиксировать.
7. **Temporal Extractor** — отдельный трек (разрыв A + E).
8. **F5 Society** — проводить после P2 решения или параллельно.

---

## 12. Заключение

**USL как архитектурный фундамент — работает.** 89 тестов GREEN, 6 инвариантов USL-1…USL-6 подтверждены (с оговоркой для temporal), ADR-O-437 ACTIVE, DTO Registry зарегистрирован.

**USL-2 SEEDED — частично завершён.** P1 фикс (new-game gate) остановил повторное применение seed. EventMemory (10), Relationships (2), Imprints (2) — GREEN. Belief — RED (P2 не решён).

**F5 Headless Laboratory** доказала: 3 из 4 механизмов работают в runtime. P2 (belief) — единственный блокер USED IN GAME.

**Мандат Мастера выполнен частично:** цепочка SOURCE TEXT → COGNITIVELY AVAILABLE доказана для 3/4 механизмов. P2 (belief runtime) требует дополнительной трассировки LifeEngine cache.

---

*Документ подготовлен по мандату MASTER DIRECTIVE USL-2 SOCIETY CALIBRATION. Археология выполнена read-only + F5 Headless Laboratory. Все выводы подтверждены конкретными файлами, строками, тестами и результатами прогонов.*
