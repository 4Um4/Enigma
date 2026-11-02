# ADR-O-437 Impact Audit — Universal Semantic Layer

> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`
> **Статус:** ACTIVE (USL-1.1/1.2/1.3 GREEN; USL-1.4/1.5/1.6 — pending)
> **Сессия:** USL-S1, ветвь А (номер S## присваивается при завершении, по §11.1.1 Anti-Race)
> **Связанные законы:** §ENIGMA-002 (Правило Двух Доменов — доказано для времени), §13 (Law of Epistemic Grounding), §17 (Epistemic Orthogonality)

## 1. Суть решения

USL — общий словарь смысла для двух языковых контуров ENIGMA:
- **Биографический контур** (CCH, Слой 0): авторский текст → `BiographyDecomposer` → `ChronicleEntry` → `BiographyAdapter` → `USLUnit`
- **Игровой языковой контур** (AG1/DLG): `IntentCompressor` → `IntentSemanticField` → `InteractiveLanguageAdapter` → `USLUnit`

**Главный критерий успеха (вердикт Мастера USL-0):** одинаковый смысл одинаково понимается в биографии NPC и в живом игровом диалоге.

**6 инвариантов USL (USL-документ §3.4):**
- USL-1: одно представление смысла независимо от источника
- USL-2: источник ≠ истина (source_kind + epistemic_status)
- USL-3: не пишет мир (read-only проектор)
- USL-4: обратная совместимость (поверх существующих контрактов)
- USL-5: провенанс трассируем (source_span обязателен)
- USL-6: детерминизм (повторный прогон = идентичный USLUnit)

## 2. Контрактные типы (USL-1.1, домен `app/domain/usl.py`)

| Тип | Назначение | Размер |
|---|---|---|
| `USLSourceKind` (Enum) | Источник смысла (AUTHOR_CANON, PLAYER_ASSERTION, NPC_SPEECH, ...) | 9 значений |
| `USLSourceRef` (frozen) | Ссылка на источник: source_kind + document_ref + span + tick/ordinal | — |
| `USLEpistemics` (frozen) | Эпистемика: source_kind + channel (реюз KnowledgeChannel) + certainty + disputed | — |
| `USLEntityRef` (frozen) | Ссылка на сущность: kind (resolved/new_npc/white_spot/self/addressee/player/unknown) + ref_id | — |
| `USLPredicate` (Enum) | Закрытый реестр предикатов: 6 общих (STOLE/ATTACKED/HELPED/ASSERTS/EXITS_TO/NAME) + 9 биографических | 15 значений |
| `USLEvent` (frozen) | Событие: predicate + subject + object + polarity + completed + negated | — |
| `USLTimeKind` (Enum) | 6 форм времени: POINT/DURATION/INTERVAL/ORDER/RELATIVE/UNKNOWN | 6 значений |
| `USLAnchorKind` (Enum) | 7 якорей: AGE_N/YEARS_AGO/WORLD_YEAR/GAME_TICK/SPEECH_TIME/EVENT_REF/UNKNOWN | 7 значений |
| `USLTimeExpression` (frozen) | Временная конструкция: kind + anchor + value + relative_to + source_span | — |
| `USLCausalRelation` (Enum) | 4 причинных связи: CAUSES/ENABLES/EXPLAINS/CONTRADICTS | 4 значения |
| `USLCausalLink` (frozen) | Причинная связь: relation + cause_ref + effect_ref + asserted_by_text | — |
| `USLRelation` (frozen) | Отношение: relation_type + subject + object + valence (без скаляров) | — |
| `USLModality` (Enum) | 4 модальности: REALIS/HYPOTHETICAL/CONDITIONAL/DESIRED | 4 значения |
| `USLModal` (frozen) | Модальность акта: negated/modality/condition/quoted/quoted_speaker (None = неизвестно) | — |
| `USLContext` (frozen) | Контекст: references/addressee/dialogue_thread/conversation_continuation/place/fragment_ord | — |
| `USLUnit` (frozen) | Минимальная единица смысла: unit_id + source_ref + text_span + 8 кортежей компонент | — |
| `make_unit_id()` | Детерминированный md5(source_kind:document_ref:span:text_span) | — |

## 3. Mapping tables

### 3.1 EntryKind → USLPredicate (Conservative, биографический адаптер)

| EntryKind | USLPredicate | Примечание |
|---|---|---|
| EVENT | ASSERTS | Conservative (BORN/DIED — future work) |
| RELATIONSHIP | ASSERTS | + USLRelation(nature, valence) |
| LOCATION | LIVES_AT | — |
| EFFECT | HAS_EFFECT | — |
| BELIEF_SEED | BELIEVES | — |
| KNOWLEDGE_LINK | KNOWS | KP_* поля из payload |
| TRAIT_SEED | HAS_TRAIT | — |
| PORTRET | HAS_TRAIT | Агрегация traits[] (future work) |
| OBSERVATION | ASSERTS | — |
| DESIRE_SEED | DESIRES | — |

### 3.2 Predicate → USLPredicate (тривиальный mapping, 6 общих)

Значения совпадают: `Predicate.STOLE.value == USLPredicate.STOLE.value == "stole"`.
Маппинг тривиальный: `Predicate(uslpred.value)` работает для общих 6.

### 3.3 act_type → USLPredicate (для ASSERT без proposition)

| act_type | USLPredicate |
|---|---|
| ASSERT | ASSERTS |
| THREAT | ATTACKED |
| COMPLIMENT | HELPED |
| INSULT | ATTACKED |
| ACCUSATION | STOLE |

## 4. Адаптеры (USL-1.2, USL-1.3)

### 4.1 BiographyAdapter (`app/services/chronicle/biography_adapter.py`)

**Вход:** `ChronicleDocument` (уже декомпозированный, канонизированный).
**Выход:** `List[USLUnit]` (1:1 mapping — один entry → один USLUnit).

**Главные функции:**
- `entry_to_usl_unit(entry, doc) → USLUnit` — главный проектор
- `biography_to_usl(doc) → List[USLUnit]` — для всего документа
- `_entityref_to_usl(ref)` — EntityRef → USLEntityRef (4 вида)
- `_provenance_to_usl_source(prov)` — EntryProvenance → USLSourceKind
- `_extract_temporal(entry)` — время из structured полей (не парсинг!)

**Conservative:** EVENT → ASSERTS (без BORN/DIED специализации). Время — только из `historical_age/year` + `payload.day/duration_years` + `KP_LEARNED_AGE`. Если ничего нет → `temporal=()` (§ENIGMA-003 честный empty).

### 4.2 InteractiveLanguageAdapter (`app/services/input/interactive_language_adapter.py`)

**Вход:** `IntentSemanticField` (уже сжатый компрессором).
**Выход:** `USLUnit`.

**Главные функции:**
- `intent_to_usl_unit(field, speaker_id, tick) → USLUnit` — главный проектор
- `intents_to_usl(fields, speaker_id, tick) → List[USLUnit]` — батч
- `predicate_to_usl(pred)` — Predicate → USLPredicate (тривиальный)
- `_proposition_to_usl_event(prop, field)` — Proposition → USLEvent
- `_semantic_acts_to_usl_events(field)` — fallback (когда proposition=None)
- `_act_to_modal(act)` — per-act → USLModal (None = неизвестно, не False)

**Conservative:** время — `temporal=()` (честный empty — input не имеет временных полей, USL §2.2 подтверждено). USL-1.4 (Temporal Extractor) — future work.

## 5. Downstream Consumers

| Потребитель | Статус | Что читает |
|---|---|---|
| `BeliefRevisionEngine` (EpistemicStore) | **не трогается** (USL-3) | — |
| `ChronicleSeeder` (EventMemory, BeliefState) | **не трогается** (USL-3) | — |
| `ClaimEventSubscriber` | **не трогается** в USL-1.1/1.2/1.3 | — |
| `TruthState` / `EvaluationEngine` | **не трогается** (USL-3) | — |
| Будущий USL-1.4 (Epistemic Integration) | pending | USLUnit.epistemics.source_kind=PLAYER_ASSERTION |
| Будущий USL-1.5 (CanonicalRegistry bridge) | pending | USLEntityRef через общий реестр имён |
| Будущий BC-5 (Social testimony) | future | USLEpistemics.channel |

## 6. Runtime Impact

- **RAM:** +4 новых модуля (~30 КБ исходников). USLUnit — transient, не кэшируется. Расчёт: <100 КБ при типичном диалоге.
- **Latency:** 0 (адаптеры не подключены к production-контуру в USL-1.1/1.2/1.3; подключение — USL-1.4+).
- **VRAM:** 0 (USL не вызывает LLM).
- **Детерминизм:** доказан тестами (USL-6 — повторный прогон = идентичный unit_id).

## 7. Sandbox Tests

| Тест-файл | Тестов | Статус |
|---|---|---|
| `tests/micro/test_usl_types.py` | 21 | ✅ GREEN |
| `tests/micro/test_usl_biography_adapter.py` | 29 | ✅ GREEN |
| `tests/micro/test_usl_interactive_adapter.py` | 22 | ✅ GREEN |
| **Итого** | **72** | ✅ all GREEN |

Ключевые тесты:
- `test_orm_canon_projects_without_errors` — реальный канон blacksmith_orm.json (53 entries) проецируется без ошибок
- `test_biography_to_usl_is_deterministic` — USL-6 детерминизм
- `test_player_assertion_not_author_canon` — USL-2 инвариант
- `test_skvoznoy_test_work_for_duration_biography_vs_input` — главный критерий Мастера
- `test_player_and_npc_same_structure_different_source` — DLG-L1 симметрия

## 8. Rollback

USL-1.1/1.2/1.3 — **additive only**: 4 новых файла, 0 правок production-кода.
Rollback = удалить 4 файла (domain/usl.py, biography_adapter.py, interactive_language_adapter.py, 3 тест-файла).
Никаких миграций данных, никаких изменений в канонах, никаких изменений в DTO Registry.

USL-1.4+ (pending) — будут правки production-кода, rollback потребует git revert.

## 9. Открытые вопросы (для USL-1.4+)

1. **Temporal Extractor для input** (USL-1.4): `extract_age_anchors_typed` НЕ готов (вердикт Мастера поправка 1) — нужно проверить на длительностях, относительных конструкциях, временных последовательностях в свободной речи.
2. **Free ASSERT → ClaimEvent** (USL-1.4): правка `claim_event_subscriber.py:104-105`. Сохранить Proposition-guard и can_observe. Не ограничивать ASSERT только временными маркерами (поправка Мастера 2).
3. **CanonicalRegistry bridge** (USL-1.5): прокинуть `registry_builder.CanonicalRegistry` в input-контур как опциональный провайдер. Не разрушать fallback-механизмы.
4. **Флаги включения** (USL-1.6): по вердикту Мастера Q4 — минимально необходимые, после реализации.
5. **красный baseline** (5 нарушений IPT) — отдельный долг, не чинится в рамках USL (INV-RE-CACHE-ALLOWLIST, INV-FLAG-REGISTRY ×2, INV-SILENT-FAILURE ×3).

## 10. Ссылки

- USL-документ (исходный PROPOSED): `docs/USL — Universal Semantic Layer.md`
- Вердикт Мастера USL-0: 6 вопросов Q1-Q6 (этот чат)
- Прецеденты: ADR-O-420 (Character Chronicle), ADR-O-388 (Player Speech Claims), ADR-O-423 (Chronicle Seeder)
- Тест-артефакты: `backend/tests/micro/test_usl_*.py` (3 файла, 72 теста)