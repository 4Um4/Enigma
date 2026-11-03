# ADR-O-437 Impact Audit — Universal Semantic Layer

> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`
> **Статус:** ACTIVE (USL-1.1–1.5 GREEN; USL-1.6 CLOSED — documentation-only closure, S410)
> **Сессия:** S380, ветвь А (номер по ЗАВЕЩАНИЕ max+1; MUTATIONS.md max=S341 — расхождение зафиксировано)
> **Связанные законы:** §ENIGMA-002 (Правило Двух Доменов — доказано для времени), §13 (Law of Epistemic Grounding), §17 (Epistemic Orthogonality)

## 1. Суть решения

USL — общий словарь смысла для двух языковых контуров ENIGMA:
- **Биографический контур** (CCH, Слой 0): авторский текст → `BiographyDecomposer` → `ChronicleEntry` → `BiographyAdapter` → `USLUnit`
- **Игровой языковой контур** (AG1/DLG): `IntentCompressor` → `IntentSemanticField` → `InteractiveLanguageAdapter` → `USLUnit`

**Главный критерий успеха (вердикт Мастера USL-0):** одинаковый смысл одинаково понимается в биографии NPC и в живом игровом диалоге.

**6 инвариантов USL (USL-документ §3.4) — проверены на конкретных тестовых данных:**
- USL-1: одно представление смысла независимо от источника
- USL-2: источник ≠ истина (source_kind + epistemic_status)
- USL-3: не пишет мир (read-only проектор)
- USL-4: обратная совместимость (поверх существующих контрактов)
- USL-5: провенанс трассируем (source_span обязателен)
- USL-6: детерминизм (повторный прогон = идентичный USLUnit)

**Оговорка (вердикт Мастера):** тесты доказывают свойства реализации на проверенных данных (orm.json 53 entries, конкретные фразы ввода). Полная семантическая эквивалентность всех возможных биографий и пользовательских высказываний требует корпусной проверки USL-2/USL-3 (следующие этапы).

## 2. Контрактные типы (USL-1.1, домен `app/domain/usl.py`)

| Тип | Назначение | Размер |
|---|---|---|
| `USLSourceKind` (Enum) | Источник смысла (AUTHOR_CANON, PLAYER_ASSERTION, NPC_SPEECH, ...) | 9 значений |
| `USLSourceRef` (frozen) | Ссылка на источник: source_kind + document_ref + span + tick/ordinal | — |
| `USLEpistemics` (frozen) | Эпистемика: source_kind + channel (реюз KnowledgeChannel) + certainty + disputed | — |
| `USLEntityRef` (frozen) | Ссылка на сущность: kind (resolved/new_npc/white_spot/self/addressee/player/unknown) + ref_id | — |
| `USLPredicate` (Enum) | Закрытый реестр предикатов: 6 общих + 9 биографических | 15 значений |
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

Conservative: EVENT → ASSERTS (без BORN/DIED специализации). Время — только из structured полей. Реальный канон blacksmith_orm.json (53 entries) проецируется без ошибок.

### 4.2 InteractiveLanguageAdapter (`app/services/input/interactive_language_adapter.py`)

**Вход:** `IntentSemanticField` (уже сжатый компрессором).
**Выход:** `USLUnit`.

Conservative: время — `temporal=()` (честный empty — input не имеет временных полей). USL-1.4 (Temporal Extractor) — future work.

### 4.3 Epistemic Integration — USL-1.4 (первая production-интеграция)

**Файл:** `app/services/events/claim_event_subscriber.py:104-105` (патч, не новый файл)
**SHA:** `8caefebc`

**Что изменилось:** `on_player_spoke` — вместо `return` (no-op при отсутствии DM-вектора) теперь строит `proposition(speaker, ASSERTS, content)` и делегирует `on_claim_event`.

**Что НЕ изменилось (сохранено):**
- Proposition-guard (reject'ит empty subject/object/polarity)
- can_observe мембрана (LOS + radius фильтрация слушателей)
- BeliefRevisionEngine (trust/reliability работает как прежде)
- TruthState/канон: on_claim_event не пишет (USL-2: PLAYER_ASSERTION → CANON запрещён)
- DM-vector path (ACCUSE→STOLE, THREATEN→ATTACKED, HELP→HELPED — ADR-O-388 регрессия зелёная)

**Вердикт Мастера (поправка 2):** не ограничивать ASSERT временными маркерами — пусть все свободные утверждения проходят через гейты. Proposition-guard — единственный фильтр.

## 5. Downstream Consumers

| Потребитель | Статус | Что читает |
|---|---|---|
| `BeliefRevisionEngine` (EpistemicStore) | **трогается в USL-1.4** (через on_claim_event) | proposition из PLAYER_SPOKE payload |
| `ChronicleSeeder` (EventMemory, BeliefState) | **не трогается** (USL-3) | — |
| `ClaimEventSubscriber` | **патч в USL-1.4** (free ASSERT path) | proposition(ASSERTS, content) |
| `TruthState` / `EvaluationEngine` | **не трогается** (USL-3) | — |
| USL-1.5 (CanonicalRegistry bridge) | **CLOSED (S410)** | intent_compressor._resolve_npc_by_name canonical-first via _ensure_registry_cache(); «Орму» автора = «Орму» игрока (§5.4) |
| USL-1.6 (Regression + Activation) | **CLOSED (S410)** | IPT 54/0/0 + USL pytest 96/96; 0 feature flags; DTO Registry §15; MUTATIONS S410 |
| Будущий BC-5 (Social testimony) | future | USLEpistemics.channel |

## 6. Runtime Impact

- **RAM:** +5 новых модулей (~35 КБ исходников). USLUnit — transient, не кэшируется.
- **Latency:** USL-1.4 добавляет ~7 строк в `on_player_spoke` — наносекунды (dataclasses.replace + dict copy).
- **VRAM:** 0 (USL не вызывает LLM).
- **Детерминизм:** доказан тестами (USL-6 — повторный прогон = идентичный unit_id и claim_id).

## 7. Sandbox Tests

| Тест-файл | Тестов | Статус |
|---|---|---|
| `tests/micro/test_usl_types.py` | 21 | ✅ GREEN |
| `tests/micro/test_usl_biography_adapter.py` | 29 | ✅ GREEN |
| `tests/micro/test_usl_interactive_adapter.py` | 22 | ✅ GREEN |
| `tests/micro/test_usl_free_assert.py` | 10 | ✅ GREEN (USL-1.4) |
| `tests/micro/test_usl_canonical_bridge.py` | 7 | ✅ GREEN (USL-1.5) |
| **Регрессия claim-контура** | 16 | ✅ GREEN |
| **Итого** | **105** | ✅ all GREEN |

Ключевые тесты:
- `test_orm_canon_projects_without_errors` — реальный канон blacksmith_orm.json (53 entries)
- `test_biography_to_usl_is_deterministic` — USL-6 детерминизм
- `test_player_assertion_not_author_canon` — USL-2 инвариант
- `test_skvoznoy_test_work_for_duration_biography_vs_input` — главный критерий Мастера
- `test_player_and_npc_same_structure_different_source` — DLG-L1 симметрия
- `test_free_assert_builds_correct_proposition` — USL-1.4 free ASSERT path
- `test_dm_vector_accuse_still_works` — ADR-O-388 регрессия

## 8. Rollback

**USL-1.1/1.2/1.3 (additive):** rollback = удалить 4 файла (domain/usl.py, biography_adapter.py, interactive_language_adapter.py, 3 тест-файла). Никаких миграций данных. SHA: `fe50b3be`.

**USL-1.4 (production patch):** rollback = `git revert 8caefebc` (возвращает `claim_event_subscriber.py:104-105` к `return` no-op). Не затрагивает каноны, EpistemicStore (записи через BeliefRevisionEngine остаются — это веры, не баг).

## 9. Открытые вопросы (для USL-1.5+)

1. **Temporal Extractor для input** (USL-1.5+): `extract_age_anchors_typed` НЕ готов (вердикт Мастера поправка 1) — нужно проверить на длительностях, относительных конструкциях, временных последовательностях в свободной речи.
2. ~~**CanonicalRegistry bridge** (USL-1.5)~~ ✅ CLOSED (S410): intent_compressor._ensure_registry_cache() + canonical-first _resolve_npc_by_name. §5.4 доказан.
3. ~~**Флаги включения** (USL-1.6)~~ ✅ CLOSED (S410): 0 feature flags (additive, always active — вердикт Мастера Q4).
4. ~~**красный baseline** (5 нарушений IPT)~~ ✅ CLOSED (S410): IPT-clearing — 11 fixes → IPT 54/0/0 CRITICAL. INV-SILENT-FAILURE ×3 + INV-RE-CACHE-ALLOWLIST + INV-FLAG-REGISTRY полностью закрыты.
5. **MUTATIONS ↔ ЗАВЕЩАНИЕ расхождение:** MUTATIONS.md max=S341, ЗАВЕЩАНИЕ ссылается на S348-S379. Сессия зафиксирована как S380 (max ЗАВЕЩАНИЕ + 1). Мастеру рекомендуется синхронизировать MUTATIONS с ЗАВЕЩАНИЕ при слиянии параллельных ветвей.

## 10. Commit History

| SHA | Тип | Содержание |
|---|---|---|
| `fe50b3be` | additive | USL-1.1/1.2/1.3 + ADR-O-437: domain/usl.py + 2 адаптера + 3 тест-файла + ADR entry + IMPACT. 72 теста. |
| `8caefebc` | production | USL-1.4: Free ASSERT path — claim_event_subscriber.py:104-105. 10 новых тестов + 16 регрессий. |
| `<SHA-IPT>` | infrastructure | IPT-clearing: 11 fixes (INV-SILENT-FAILURE ×3 + INV-RE-CACHE-ALLOWLIST + INV-FLAG-REGISTRY). IPT 51→54 passed, 3→0 CRITICAL. |
| `<SHA-USL-1.5>` | production | USL-1.5: CanonicalRegistry bridge — intent_compressor.py _ensure_registry_cache() + canonical-first _resolve_npc_by_name. 7 новых тестов. |
| `<SHA-USL-1.6>` | documentation | USL-1.6: IMPACT R3 + DTO Registry §15 + MUTATIONS S410. Documentation-only closure. |

## 11. Ссылки

- USL-документ (исходный PROPOSED): `docs/USL — Universal Semantic Layer.md`
- Вердикт Мастера USL-0: 6 вопросов Q1-Q6 + 3 поправки к анализу архитектора
- Прецеденты: ADR-O-420 (Character Chronicle), ADR-O-388 (Player Speech Claims), ADR-O-423 (Chronicle Seeder)
- Тест-артефакты: `backend/tests/micro/test_usl_*.py` (4 файла, 82 теста)
- ЗАВЕЩАНИЕ: Письмо №14 (S380, эта серия)
## 12. CanonicalRegistry Bridge (USL-1.5, S410)

### Architecture

**Bridge site:** `intent_compressor._resolve_npc_by_name`
**Pattern:** module-level cache (chronicle `decomposition_normalizer.py:73-75`)

Fallback order: canonical exact match -> stem-based iteration (preserved).
0 feature flags (additive, always active — Master verdict Q4).

### Cache lifecycle

| Parameter | Value |
|---|---|
| Registry source | `config/npc/individuals/*.json` (static config) |
| Builder | `build_canonical_registry()` -> `load_npcs_merged()` -> JSON read |
| Mutability | NPC roster + name_forms = config-sourced, NOT runtime-mutable |
| Cache lifecycle | lazy build at first call -> process lifetime |
| Invalidation | NOT NEEDED — registry immutable during game session |
| Precedent | chronicle `decomposition_normalizer.py:73-75` — same pattern |

Verdict: current implementation acceptable (Master: no code change without proof).

### USL-1 Section 5.4 proven

`test_player_and_author_same_resolution`: GREEN.
