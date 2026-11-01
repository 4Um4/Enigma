## Phase 2, Этап 3.3 — Финальный архитектурный отчёт

---

### A. R2.1 — Directed Relationship / Epistemic Perspective

#### 1. Доказанные факты

| Факт | Файл:строка | Контракт |
|------|-------------|----------|
| `Predicate` enum: STOLE, ATTACKED, HELPED, ASSERTS, EXITS_TO, NAME | `epistemology.py:17-33` | **6 значений** — нет TOLERATES, BELIEVES, KNOWS, FEARS, TRUSTS |
| `Proposition(subject_id, predicate, object_id, polarity)` | `epistemology.py:76-84` | 3-role: кто/что/над-кем. `subject_id ≠ agent_id` — ToM-capable |
| `EpistemicRecord(agent_id, proposition, confidence, source_id, source_claim_id, first/last_tick)` | `epistemology.py:123-134` | `agent_id` = кто верит; `proposition.subject_id` = о ком утверждение |
| `EpistemicStore` key = `(agent_id, proposition)` | `epistemic_store.py:22` | `agent_id ≠ proposition.subject_id` — позволяет ToM |
| `ClaimEventSubscriber` — единственный writer EpistemicStore | `claim_event_subscriber.py:1-80` | Создаёт EpistemicRecord из runtime NPC_SPOKE / COMMUNICATION_CLAIM |
| `EpistemicContextResolver` — единственный reader → DecisionHub | `epistemic_context_resolver.py:1-80` | `_THREAT_PREDICATES = (STOLE, ATTACKED)` — только 2 из 6 предикатов триггерят threat detection |
| `routes_chronicle.py:433` — `subject_id = EntityRef(RESOLVED, npc_id=req.npc_id)` | routes_chronicle | **Хардкод**: subject всегда = владелец хроники |
| Seeder не заполняет EpistemicStore | `chronicle_seeder.py` | BELIEF_SEED → BeliefState (psyche), не EpistemicStore |

#### 2. Текущий контракт

```
ChronicleEntry:
  subject_id: EntityRef    ← ВСЕГДА = владелец хроники (routes хардкод)
  object_id: EntityRef     ← target_hint → resolve → NPC_id
  payload.nature: str      ← свободный текст
  payload.valence: str     ← positive/negative/neutral
  payload.summary: str     ← авторская фраза

EpistemicRecord:
  agent_id: str            ← кто верит (Орм)
  proposition:
    subject_id: str         ← о ком (Гильдия)
    predicate: Predicate   ← что (TOLERATES — НЕ СУЩЕСТВУЕТ)
    object_id: str         ← над кем (Орм)
  confidence: float
  source_id: str           ← откуда узнал
```

#### 3. Runtime-путь

| Этап | Что происходит | «Гильдия терпит Орма» |
|------|----------------|----------------------|
| Author text | «Гильдия терпит Орма» | ✅ |
| LLM extraction | `target_hint="Орм"` (self-ref, A2 ловит) | 🔴 LLM не инвертирует |
| Normalizer | self_reference question → автор резолвит | ⚠️ Автор должен выбрать правильный target |
| Canon | `subject_id=Орм, object_id=null, target_hint="Орм"` | 🔴 object_id=null |
| Seeder | `build_seed_relationships`: object_id=null → skip | 🔴 Не материализуется |
| relationship_cache | Нет записи | 🔴 0 отношений |
| EpistemicStore | **Не заполняется из канона** | 🔴 Нет пути |
| DecisionHub | Нет данных | 🔴 NPC не знает, что Гильдия его терпит |

#### 4. Контрольный пример: «Гильдия терпит Орма»

Ожидаемый смысл:
- Орм знает утверждение → `EpistemicRecord(agent_id="orm")`
- Гильдия — субъект отношения → `Proposition.subject_id="гильдия"`
- Орм — объект отношения → `Proposition.object_id="orm"`
- Предикат — терпимость → `Predicate.TOLERATES` (НЕ СУЩЕСТВУЕТ)

**Можно ли представить без инверсии?**

В **EpistemicStore** — **да**: `agent_id="orm"` (кто знает), `proposition.subject_id="гильдия"` (кто субъект), `proposition.object_id="orm"` (над кем). Это **3-role контракт** — три роли разделены.

В **ChronicleEntry** — **нет**: `subject_id=Орм` (хардкод routes). Можно положить `object_id=Гильдия`, но semantic: «Орм → доверяет → Гильдии», не «Гильдия → терпит → Орма».

**Второй случай (Орм ошибочно считает, что Гильдия его терпит):**

EpistemicStore **позволяет**: `EpistemicRecord(agent_id="orm", proposition=Proposition(subject="гильдия", pred=TOLERATES, obj="orm"), confidence=0.8, source_id="author")`. При этом WORLD TRUTH может не содержать такого факта — EpistemicRecord хранит **субъективное убеждение**, не истину (§18, `S188`).

#### 5. Точка потери семантики

| Переход | Что теряется |
|---------|-------------|
| Author → LLM | LLM кладёт target_hint="Орм" (self-ref), не "Гильдия" |
| LLM → Canon | object_id=null (не резолвнут) |
| Canon → Seeder | nature теряется; только trust ± |
| **Seeder → EpistemicStore** | **Нет пути** — seeder не заполняет EpistemicStore |
| EpistemicStore → DecisionHub | Predicate.TOLERATES не существует — threat/allies детектор не сработает |

#### 6. Классификация

- **LLM misclassification**: LLM не инвертирует отношение (кладёт target=сам subject)
- **Отсутствующий seeder**: EpistemicStore не заполняется из канона
- **Недостаточность доменной модели**: Predicate enum не содержит TOLERATES/BELIEVES — нельзя выразить «Гильдия терпит» как эпистемическое утверждение

#### 7. Рекомендация

**Минимальное:** LLM декомпозирует «Гильдия терпит Орма» как RELATIONSHIP с `target_hint="Гильдия"`, `nature="объект_терпимости"`, `valence="positive"`. Seeder: trust=+30 (Гильдия благосклонна к Орму — корректно для gameplay, хотя semantic: «Орм → trust +30 → Гильдия»). **Не идеально, но работает.**

**Полноценное:** EpistemicStore заполняется из BELIEF_SEED канона через seeder. Расширение Predicate enum (TOLERATES, BELIEVES, KNOWS) — отдельный мини-ADR (Two-Domain Rule: ждём второго домена-подтверждения). Но: это уже **SUU** (Semantic Understanding Unification, CCH-D14) — перенос семантических контрактов на runtime.

**Риски:** Минимальное сохраняет semantic inversion (trust ≠ терпимость). Полноценное — большой объём работы, требует ADR.

#### 8. Тестируемость

- Контрактная проверка: RELATIONSHIP с `object_id=null` → seeder skip + лог (уже работает)
- Контрактная проверка: BELIEF_SEED с `belief_type=None` → seeder skip + лог (уже работает)
- Контрактная проверка: self-reference target_hint → normalizer question (A2, уже работает)
- **Отсутствующая проверка:** EpistemicStore заполняется из канона — нет теста, потому что нет реализации

---

### B. R2.2 — Relationship Nature / Scalar Projection

#### 1. Пять скаляров: writers и readers

| Скаляр | Store | WriteGate | StateApplicator (writer) | DecisionHub (reader) | risk.py | interpretation_engine | social_deltas | Seeder |
|--------|-------|-----------|--------------------------|---------------------|---------|----------------------|---------------|--------|
| **trust** | ✅ `_LEGACY_SCALARS` | ✅ whitelist | ✅ `trust_delta` | ✅ `_get_rel_value` + `_relationship_modifier` | ✅ indirect | ✅ distrust bias | ✅ modulation | ✅ ±30/−40 |
| **fear** | ✅ | ✅ | ✅ `fear_delta` | ✅ `_get_rel_value` + `_relationship_modifier` | ❌ | ✅ threat bias | ✅ modulation | ❌ |
| **debt** | ✅ | ✅ | ✅ `debt_delta` (line 118) | ❌ | ❌ | ❌ | ❌ | ❌ |
| **respect** | ✅ | ✅ | ❌ (no param) | ❌ | ❌ | ❌ | ❌ | ❌ |
| **attraction** | ✅ | ✅ | ❌ (no param) | ❌ | ❌ | ❌ | ❌ | ❌ |

#### 2. Доменный смысл каждого скаляра (по ТЗ RE-01)

| Скаляр | Доменный смысл | Writer в runtime | Reader в runtime | Default | Unknown ≠ Zero? |
|--------|----------------|-----------------|-----------------|---------|-----------------|
| trust | Базовое доверие/недоверие к target | ✅ StateApplicator (social events) | ✅ DecisionHub (attack/flee/approach) | 0.0 | ❌ 0 = neutral |
| fear | Страх перед target | ✅ StateApplicator (social events) | ✅ DecisionHub (flee/attack/observe) | 0.0 | ❌ 0 = no fear |
| debt | Долг (моральный/материальный) | ✅ StateApplicator (debt_delta) | ❌ Нет consumer | 0.0 | ❌ 0 = no debt |
| respect | Уважение к target | ❌ Нет writer | ❌ Нет consumer | 0.0 | ❌ 0 = no respect |
| attraction | Привлечение к target | ❌ Нет writer | ❌ Нет consumer | 0.0 | ❌ 0 = no attraction |

**`§ENIGMA-003:` Unknown ≠ Neutral(0.0)** — но в relationship_cache нет sentinel для «unknown». Если scalar отсутствует → `.get("trust", 0.0)` = 0.0 = neutral. **Unknown и Zero неразличимы.**

#### 3. `valence=neutral`

| Слой | Контракт | Что означает |
|------|----------|-------------|
| Промпт | `valence: <negative\|neutral\|positive>` | Оценка знака отношения |
| Seeder | `if valence not in ("positive", "negative") → skip` | **neutral = нет trust-значения = не сеётся** |
| §ENIGMA-003 | `Unknown ≠ Neutral(0.0)` | Unknown = отсутствие оценки |
| Факт (ord=1903) | `valence=neutral`, nature="disengagement" | «выключается из застолья» — не trust/fear, а поведенческая характеристика |

**Вердикт:** `valence=neutral` в seeder = «оценка отсутствует» → skip. Это **не дефект** — neutral правильно означает «не положительный и не отрицательный», а seeder не может присвоить trust для neutral (trust=0 = neutral, но §ENIGMA-003 говорит Unknown ≠ 0). Проблема в том, что **relationship_cache не различает unknown и 0**.

#### 4. Что может сохранять `nature` и `summary`

| Хранилище | Может сохранить nature? | Может сохранить summary? |
|-----------|------------------------|------------------------|
| relationship_cache | ❌ Нет поля (только скаляры) | ❌ Нет поля |
| ChronicleEntry.payload | ✅ Уже сохранено | ✅ Уже сохранено |
| BeliefState | ❌ Только belief_type | ❌ Нет поля |
| EpistemicRecord | ⚠️ Через Proposition (predicate) | ❌ Нет поля |
| EventMemory | ❌ Нет поля | ✅ `summary: str` (есть) |

**`nature` может сохраняться только в ChronicleEntry.payload** — это канонический источник. relationship_cache — числовой SSOT, не хранит семантику. Это **по design** (RE-01: скаляры = проекция, не семантика).

#### 5. Классификация отношений

| Понятие | Тип | 5 скаляров? | Канон? |
|---------|------|------------|--------|
| Дружба | Отношение (trust +) | ✅ | RELATIONSHIP nature="доверие" |
| Вражда | Отношение (trust −) | ✅ | RELATIONSHIP nature="вражда" |
| Зависимость | Отношение (debt +) | ⚠️ debt не имеет reader | RELATIONSHIP nature="зависимость" |
| Долг | Отношение (debt +) | ⚠️ debt не имеет reader | RELATIONSHIP nature="долг" |
| Уважение | Отношение (respect +) | ❌ respect не имеет writer/reader | RELATIONSHIP nature="уважение" |
| Идеализация | Состояние/интерпретация | ❌ Не отношение, а проекция | RELATIONSHIP nature="идеализация" (semantic mismatch) |
| Перенос | Причинный механизм | ❌ Не отношение, а психологический перенос | RELATIONSHIP nature="перенос" (semantic mismatch) |
| Терпимость | Отношение (отсутствие вражды) | ⚠️ trust=0 ≠ «терпит» | RELATIONSHIP nature="зависимость" |
| Вина | Эмоциональное состояние | ❌ Не отношение | BELIEF_SEED / EFFECT (B1) |

#### 6. Рекомендация

**Минимальное:** Реализовать CCH-6 (nature → скаляры mapping) только для trust и fear (работающие скаляры). Остальные 3 скаляра (debt, respect, attraction) — без consumer, не заполнять. `valence=neutral` → skip (оставить как есть).

**Полноценное:** RE-01 K (removal-test) — убрать debt/respect/attraction если нет consumer, или реализовать consumer для каждого. Добавить `is_unknown: bool` к скалярам для различения unknown ≠ 0.

**Риски:** Минимальное создаёт данные без consumer для debt. Полноценное — большая работа RE-01.

---

### C. R4.1 — EFFECT Domain

#### 1. Полный жизненный цикл EFFECT

| Этап | Файл:строка | Контракт |
|------|-------------|----------|
| Domain | `chronicle.py:53` | `EFFECT = "EFFECT"` — «последствие для личности/тела/статуса» |
| Prompt | `chronicle_decompose_system.txt:21` | `effect_kind: trauma\|loss\|gain\|secret\|skill\|residence\|guardianship\|occupation\|custom` (9 значений) |
| Normalizer | Не валидирует effect_kind | Любое значение проходит |
| Canon | Хранит payload как есть | Любые значения |
| Seeder | `chronicle_seeder.py:558-570` | **Только** `trauma` + `triggers` → AffectiveImprint. Остальные → NOT_APPLICABLE |
| Runtime store | AffectiveImprint (`npc_state.py`) | Только trauma → `decay_rate=0, trigger_tags, pain/fear/humiliation` |
| Runtime consumer | `idle_services → decay_affective_imprints` | Только AffectiveImprint |

#### 2. Для каждого effect_kind

| effect_kind | Доменный смысл | Длительное состояние? | Существующее хранилище | Writer из канона? | Reader в runtime? | Класс |
|-------------|---------------|---------------------|----------------------|-------------------|-------------------|-------|
| **trauma** | Травматический отпечаток (сенсорный триггер → эмоция) | ✅ Вечный (decay=0) | AffectiveImprint | ✅ Seeder (если triggers) | ✅ decay_affective_imprints | ✅ Работает |
| **occupation** | Профессия/род деятельности | ✅ Длительное | ❌ Нет store | ❌ | ❌ | Отсутствует consumer |
| **skill** | Обучение/навык | ✅ Длительное | ❌ Нет store | ❌ | ❌ | Отсутствует consumer |
| **residence** | Жильё/место обитания | ✅ Длительное | ❌ (LOCATION близко, но не consumer EFFECT) | ❌ | ❌ | Отсутствует consumer |
| **guardianship** | Опека/защита | ⚠️ Действие (не состояние) | ❌ | ❌ | ❌ | LLM misclassify (должно быть EVENT) |
| **secret** | Скрытое знание/мотив | ✅ Длительное | ❌ (truth_state рядом, но не EFFECT consumer) | ❌ | ❌ | Отсутствует consumer |
| **gain** | Приобретение/усиление | ⚠️ Действие или состояние | ❌ | ❌ | ❌ | LLM misclassify (часто TRAIT_SEED) |
| **loss** | Утрата/ослабление | ⚠️ Действие или состояние | ❌ | ❌ | ❌ | LLM misclassify (часто TRAIT_SEED или EVENT) |
| **custom** | Произвольное | — | ❌ | ❌ | ❌ | Placeholder без контракта |

#### 3. 15 EFFECT Орма — разделение ошибки классификации и отсутствия consumer

| ord | effect_kind | Ошибка классификации? | Отсутствует consumer? | Правильный kind? |
|-----|-------------|---------------------|---------------------|------------------|
| 100 | occupation | ❌ (EFFECT правилен — профессия = последствие для статуса) | ✅ Нет consumer для occupation | EFFECT (если consumer будет) |
| 501 | knowledge | ✅ (чужое знание — EVENT, не EFFECT) | — | EVENT |
| 600 | skill | ❌ (EFFECT правилен — навык = последствие для личности) | ✅ Нет consumer для skill | EFFECT (если consumer будет) |
| 1603-1605 | guardianship | ✅ (действие защиты — EVENT, не EFFECT) | — | EVENT |
| 1607 | secret | ❌ (EFFECT правилен — скрытый мотив = последствие для личности) | ✅ Нет consumer для secret | EFFECT (если consumer будет) |
| 1701 | gain | ✅ (психическая реакция — TRAIT_SEED) | — | TRAIT_SEED |
| 1704 | gain | ✅ (стратегия — BELIEF_SEED) | — | BELIEF_SEED |
| 1801 | residence | ❌ (EFFECT правилен — жильё = последствие для статуса) | ✅ Нет consumer для residence | EFFECT (если consumer будет) |
| 1802 | loss | ✅ (уязвимость — TRAIT_SEED) | — | TRAIT_SEED |
| 2100 | trauma | ✅ (физическая характеристика — TRAIT_SEED) | — | TRAIT_SEED |
| 2101 | loss | ✅ (речевая характеристика — TRAIT_SEED) | — | TRAIT_SEED |
| 2102 | trauma | ✅ (речевая характеристика — TRAIT_SEED) | — | TRAIT_SEED |
| 2105 | residence | ❌ (EFFECT правилен — место сна = последствие для статуса) | ✅ Нет consumer | EFFECT (если consumer будет) |

**Итог:** 5 из 15 — **правильный EFFECT** (occupation, skill, secret, residence ×2), но без consumer. 8 — LLM misclassify (должны быть EVENT/TRAIT_SEED/BELIEF_SEED). 2 — trauma misclassify (должны быть TRAIT_SEED).

#### 4. Рекомендация

**Минимальное:** Промпт усилить: EFFECT — только для **длительных последствий** (trauma, occupation, skill, residence, secret). Действия (guardianship, gain, loss) → EVENT. Характеристики → TRAIT_SEED.

**Полноценное:** Определить downstream consumer для occupation/skill/residence/secret. Например: occupation → NPCPersonality.voice_profile или новое поле; skill → active_traits; residence → LOCATION; secret → truth_state.

**Риски:** Не сужать EFFECT до trauma+custom. `occupation`, `skill`, `residence`, `secret` — валидные EFFECT, просто без consumer. Удаление их из промпта = потеря доменной модели.

---

### D. R4.2 — Body / Traits / Behavior

#### 1. Карта существующих контрактов

| Контракт | Что хранит | Writer | Reader | Из канона? | Персистентно? |
|----------|-----------|--------|--------|-----------|---------------|
| **BodyState** | pain, fatigue, energy, hydration, nutrition, sleep_pressure, injuries[], shock, coupling_mode | BodyEngine (runtime) | DecisionHub (availability), PerceptualKernel (somatic_urgency) | ❌ | ✅ (scene_state) |
| **Wound** (physical.py) | zone, type, depth, functional_loss, blood_loss_rate | InjuryProcessor (combat) | InjuryProcessor (locomotion/manipulation impairment) | ❌ | ✅ (in BodyState.injuries) |
| **NPCPersonality** | voice_profile, drives_base, identity_rigidity, breakpoint, loyalty_true | Конфиг JSON (load) | DecisionHub (drive_weights), Verbalization | ❌ | ✅ (NPC config) |
| **active_traits** | Dict[str, float] — накопленные черты | ❌ Нет writer (CCH-D7) | DecisionHub (effective_drives overlay) | ❌ | ✅ (NPCState) |
| **AffectiveImprint** | trigger_tags, pain/fear/humiliation/fear signatures, decay_rate=0 | Seeder (trauma EFFECT + triggers) | idle_services (decay_affective_imprints) | ✅ (только trauma) | ✅ (NPCState.affective_imprints) |
| **TRAIT_SEED** | trait, evidence, qualifiers | LLM → canon | ❌ (NOT_APPLICABLE в seeder) | ✅ (в каноне) | ✅ (в каноне) |

#### 2. Контрольные примеры

| Пример | Что это? | Правильный контракт | Заполняется из канона? |
|--------|---------|---------------------|----------------------|
| Обожжённые руки | Постоянная физическая особенность | TRAIT_SEED → active_traits (CCH-D7) | ❌ |
| Старые шрамы | Последствие старого повреждения | TRAIT_SEED → active_traits | ❌ |
| Односложная речь | Речевая характеристика | TRAIT_SEED → active_traits или NPCPersonality.voice_profile | ❌ |
| Привычка спать у горна | Поведенческая привычка | TRAIT_SEED → active_traits | ❌ |
| Ожог как последствие события | Травматический отпечаток от конкретного события | EFFECT trauma + triggers → AffectiveImprint | ✅ (если triggers) |
| Текущая боль от свежей раны | Текущее физическое состояние | BodyState.pain + Wound (InjuryProcessor) | ❌ (только runtime) |

#### 3. `active_traits: Dict[str, float]` — полноценный контракт?

**Нет.** `active_traits` — числовой механизм интенсивности (`weight: float`), не семантический контракт. Он хранит `{"подавленная злость": 0.7}`, но:
- Нет типизации (любая строка = ключ)
- Нет provenance (откуда черта)
- Нет связи с событием-причиной
- Нет consumer (CCH-D7 не реализован — `effective_drives` overlay не работает)

**Минимальное решение для CCH-D7:** seeder заполняет `active_traits` из TRAIT_SEED (trait → ключ, evidence → provenance). Но без consumer это мёртвые данные.

#### 4. Рекомендация

**Минимальное:** Не смешивать AffectiveImprint (сенсорный триггер → эмоция) с physical characteristics (постоянная особенность тела). TRAIT_SEED → active_traits — правильный путь, но требует CCH-D7 (consumer).

**Полноценное:** `active_traits` с provenance + типизацией (physical/speech/habit/personality). Отдельный ADR для Character Calibration.

---

### E. R3.1 — ToM / Self-knowledge / Author Knowledge / Desire

#### 1. ToM

| Вопрос | Ответ | Доказательство |
|--------|-------|---------------|
| Существует ли predicate BELIEVES? | **❌ Нет** | `Predicate` enum: STOLE, ATTACKED, HELPED, ASSERTS, EXITS_TO, NAME |
| Допускает ли Proposition утверждение о чужом убеждении? | ✅ Да (structurally) | `subject_id` ≠ `agent_id` в EpistemicRecord |
| Может ли EpistemicStore хранить `agent=Орм, subject=Борко`? | ✅ Да | Key = `(agent_id, proposition)` — agent_id ≠ proposition.subject_id |
| Как отличить убеждение Орма о Борко от убеждения самого Борко? | ✅ `agent_id` различает | `EpistemicRecord(agent_id="orm", prop=(subject="борко", ...))` vs `EpistemicRecord(agent_id="борко", prop=(subject="борко", ...))` |
| Как загружается в runtime? | **Только через ClaimEvent** | `ClaimEventSubscriber` — единственный writer EpistemicStore |
| Загружается ли из канона? | **❌ Нет** | Seeder не заполняет EpistemicStore |

**ord=1705 «Борко думает, что он хозяин»**:
- EpistemicStore может: `agent_id="orm", proposition=Proposition(subject="борко", predicate=ASSERTS, object="is_master")`
- Но: `predicate=ASSERTS` существует (S199: Second-Order ToM). Однако «Борко думает, что он хозяин» — это `BELIEVES`, не `ASSERTS`. ASSERTS = «утверждает» (высказал), BELIEVES = «думает» (внутреннее убеждение).
- Seeder не заполняет EpistemicStore из BELIEF_SEED → **нет пути из канона**

#### 2. Self-knowledge

| Механизм | Что выражает | Для ord=804 | Для ord=1600 |
|---------|-------------|-------------|-------------|
| PORTRET | Авторский монолог о характере | ✅ «не разглядел перенос» | ✅ «знает разницу» |
| BeliefState | Числовое убеждение о мире (danger/player_hostile) | ❌ Не убеждение о мире | ❌ Не убеждение о мире |
| EpistemicStore | Субъективное убеждение агента | ⚠️ `agent=orm, prop=(subject=orm, pred=UNAWARE, obj="перенос")` — нужен UNAVERSE | ⚠️ `agent=orm, prop=(subject=orm, pred=KNOWS, obj="diff")` — нужен KNOWS |
| active_traits | Числовая черта | ❌ Не черта | ❌ Не черта |

**NL-11:** `WHAT HAPPENED ≠ WHAT REMEMBERS ≠ WHAT BELIEVES ≠ HOW EXPLAINS HIMSELF`. PORTRET — правильный kind для self-interpretation. LLM должна использовать PORTRET, не BELIEF_SEED.

#### 3. Author knowledge

PORTRET хранит **авторское** утверждение о неосознанном мотиве NPC. Это **не** знание NPC (NPC не осознаёт перенос). PORTRET — **текст в каноне**, не влияет на интерпретацию/поведение runtime (пока NL-11 не реализован).

NL-11 (§12.1.11) определяет: NPC может не понимать собственные мотивы. Но runtime-механизм для этого (self-model → self-interpretation → answer) — **NL-11 не реализован** (Ступень 10 §0.2).

#### 4. Desire

| Этап | Файл:строка | Контракт | Статус |
|------|-------------|----------|--------|
| EntryKind | `chronicle.py:59` | `DESIRE_SEED = "DESIRE_SEED"` | ✅ Существует |
| Prompt | `chronicle_decompose_system.txt` | `DESIRE_SEED: мечта/желание/фантазия/план` | ✅ Определён |
| Seeder | `chronicle_seeder.py` | NOT_APPLICABLE (не seedable) | ❌ Не обрабатывается |
| Runtime Desire | `domain/desire.py:94` | `Desire(about_hint, provenance, born_tick, last_fulfilled)` | ✅ Контракт существует |
| DESIRES_ENABLED | flags.yaml | ROLLOUT-PENDING (default OFF) | ❌ Не активирован |
| Consumer | `activity_lifecycle_service` | Living Activity (ADR-O-384) | ⚠️ За флагом |

**Полный путь DESIRE_SEED → Desire → NPC state → Decision:**
1. LLM создаёт DESIRE_SEED в каноне ✅
2. Seeder → NOT_APPLICABLE (не обрабатывает) ❌
3. Desire (domain) существует, но не заполняется из канона ❌
4. DESIRES_ENABLED default OFF — Desire не активен в runtime ❌
5. Activity Lifecycle (consumer) — за флагом, не работает ❌

**Что происходит после перезагрузки NPC:** Desire не загружается (seeder не заполняет). `active_traits` и `desires` не персистятся из канона.

#### 5. Рекомендация

**ToM:** EpistemicStore структурно поддерживает ToM (agent ≠ subject). Но: (1) нет predicate BELIEVES, (2) seeder не заполняет из канона. Расширение Predicate — мини-ADR (Two-Domain Rule). Заполнение из канона — SUU (CCH-D14).

**Self-knowledge:** PORTRET — правильный kind. Промпт должен направлять LLM использовать PORTRET для самонаблюдения, не BELIEF_SEED.

**Author knowledge:** PORTRET хранит авторское знание. NL-11 (runtime self-interpretation) — отдельная ступень (§0.2 Ступень 10), не реализована.

**Desire:** DESIRE_SEED → Desire — полный контракт существует, но seeder не обрабатывает. Нужен CCH-D7 (Character Calibration) или отдельный ADR для desire-seeding.

---

### Единая карта ENIGMA

| Что умеет | Выразить в домене | Материализовать в runtime | Использовать в поведении |
|-----------|------------------|------------------------|------------------------|
| **EVENT (происшествие)** | ✅ ChronicleEntry + historical_age | ✅ EventMemory (SENTINEL_DAY если без age) | ✅ recall() по importance/tags |
| **RELATIONSHIP (trust ±)** | ✅ ChronicleEntry + valence | ✅ relationship_cache (только trust, если object_id resolved) | ✅ DecisionHub _relationship_modifier (trust/fear) |
| **RELATIONSHIP (fear)** | ✅ ChronicleEntry + valence | ❌ Seeder не пишет fear | ✅ DecisionHub (если бы писался) |
| **RELATIONSHIP (debt/respect/attraction)** | ✅ Store + WriteGate | ❌ Нет writer из канона | ❌ Нет reader |
| **BELIEF_SEED (danger/player_hostile)** | ✅ ChronicleEntry + belief_type | ✅ BeliefState (если type валиден) | ✅ DecisionHub (belief_modifiers) |
| **BELIEF_SEED (другие типы)** | ✅ В каноне | ❌ Skip (belief_type=None) | ❌ |
| **EFFECT trauma + triggers** | ✅ ChronicleEntry | ✅ AffectiveImprint | ✅ decay_affective_imprints |
| **EFFECT non-trauma** | ✅ В каноне | ❌ NOT_APPLICABLE | ❌ Нет consumer |
| **TRAIT_SEED** | ✅ В каноне | ❌ NOT_APPLICABLE (CCH-D7) | ❌ active_traits не заполняется |
| **PORTRET** | ✅ В каноне | ❌ NOT_APPLICABLE | ❌ NL-11 не реализован |
| **DESIRE_SEED** | ✅ EntryKind + Desire domain | ❌ NOT_APPLICABLE | ❌ DESIRES_ENABLED OFF |
| **KNOWLEDGE_LINK** | ✅ EntryKind | ✅ EventMemory (если knower resolved) | ✅ recall() |
| **LOCATION** | ✅ EntryKind | ❌ NOT_APPLICABLE | ❌ |
| **ToM (чужое убеждение)** | ✅ EpistemicStore (structural) | ❌ Не из канона | ⚠️ EpistemicContextResolver (runtime only) |
| **Self-interpretation** | ✅ PORTRET | ❌ | ❌ NL-11 не реализован |
| **Self-knowledge** | ✅ PORTRET | ❌ | ❌ NL-11 не реализован |
| **Author knowledge о неосознанном** | ✅ PORTRET (текст) | ❌ (текст только) | ❌ |

**Главный вывод:** ENIGMA умеет **выразить** значительно больше, чем **материализовать**, и материализовать больше, чем **использовать в поведении**. Разрыв между «выразить» и «материализовать» — это отсутствие seeder-путей; между «материализовать» и «использовать» — отсутствие consumers.

**Отчёт готов. Мастер принимает архитектурные решения.**