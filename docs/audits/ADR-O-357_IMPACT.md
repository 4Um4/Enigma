# ADR-O-357 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-O-357` [STANDARD] **IMPACT**
# ADR-O-357 Impact Audit: Trust-Anchored Belief Revision & Social Semantics Law
> Этот файл — детальный аудит ADR-O-357. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`
> Сессия: S199 (Фаза 8.2)

## Changed Domains
- **DOM-EPISTEMIC:** `BeliefRevisionEngine` теперь использует `TrustBasedReliabilityProvider`, который читает `trust` из `RelationshipStore`. Если `trust < -30`, `reliability` становится отрицательной (игрок не верит врагу, `confidence` падает).
- **DOM-SOCIAL:** В `SocialSubscriber` добавлены детерминированные fallback'и для `intent_type` (`gossip`, `accuse`, `praise`), начисляющие `trust` и `fear` к спикеру и таргету без LLM-анализа.
- **DOM-FATE:** В `FateTracker` добавлен счётчик `_critical_ticks`. Если NPC находится в траектории `CRITICAL` 5 тиков подряд, он получает `FateOutcome.BROKEN`.
- **DOM-UI:** В `WorldSnapshotDTO` добавлено поле `player_beliefs`, которое пробрасывает убеждения игрока (`EpistemicStore`) во фронтенд. В `AnalysisRenderer` добавлена вкладка "Убеждения".

## Downstream Consumers
- **DecisionHub:** Читает `crystallized_beliefs` (не затронуты напрямую, но базируются на обновляемых `EpistemicRecord`).
- **MvpTavernController:** Читает `break_progress` и вызывает `trigger_fate(BROKEN)` при превышении порога `_critical_ticks`.
- **Frontend (AnalysisRenderer):** Читает `player_beliefs` из `WorldSnapshotDTO` и рендерит полоски `confidence`.

## Runtime Impact
- **RAM:** +1-2 KB на `player_beliefs` в `WorldSnapshotDTO` (пренебрежимо).
- **Latency:** +0.1-0.3 ms на вызов `RelationshipStore.get_pair()` внутри `TrustBasedReliabilityProvider` (использует in-memory LRU кэш).
- **VRAM:** 0

## Sandbox Tests
- `backend/tests/IPT.py` (39/39 passed) — подтверждает отсутствие регрессий (включая архитектурные инварианты).

## Rollback
1. В `BeliefRevisionEngine` вернуть `ConstantReliabilityProvider` (или инъекцию по умолчанию).
2. В `SocialSubscriber` вернуть плоский `trust_delta = 0.5` для всех `intent_type`.
3. В `FateTracker` удалить `_critical_ticks` и вернуть мгновенный `BROKEN` при `CRITICAL`.
4. В `WorldSnapshotBuilder` убрать передачу `epistemic_store` и поля `player_beliefs`.
5. Во фронтенде удалить вкладку `"beliefs"`.


# Гейт [2]/[6] ЗАКРЫТ: обе трассы совпали с предсказаниями на 100%, ноль необъяснённых отклонений

## 1. Сверка BEFORE с прогнозной таблицей §3 — полное совпадение

| Сценарий | Прогноз | Факт | |
|---|---|---|---|
| A t=-100/-50/-31 (rel) | -0.5 | -0.5 | ✅ |
| A t=-30/-10/0 (rel, create, repeat) | 0.0 / 0.0 / 0.0 | 0.0 / 0.0 / 0.0 | ✅ |
| A t=50 | 0.5 / 0.5 / 0.6 | 0.5 / 0.5 / 0.6 | ✅ |
| A t=100 | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 | ✅ |
| B (все три врага) | friend=0.8, cross=0.30, repeat=0.20 | 0.8 / 0.3 / 0.2 — **три строки идентичны** | ✅ |
| EDGE store_missing | 0.5 / 0.5 | 0.5 / 0.5 | ✅ |
| EDGE unknown_pair | эмпирика | 0.5 / 0.5 | ✅ |

**Ключевой факт BEFORE подтверждён:** инлайн не различает степень вражды — строки B для врагов -31, -50 и -100 байт-в-байт одинаковы. Это зафиксированное нарушение табу ADR-O-357 («фиксированная reliability») в живом измерении.

## 2. Сверка AFTER с предрегистрированной delta-матрицей — полное совпадение

| Дельта | Прогноз | Факт | Класс |
|---|---|---|---|
| H1 store_missing | 0.5 → 0.5 | 0.5 → 0.5 | паритет ✅ |
| H2 unknown_pair | 0.5 → 0.5 | 0.5 → 0.5 | паритет ✅ |
| H3a create, враг | 0.0 → 0.0 | 0.0 → 0.0 | паритет ✅ |
| H3b cross-confirm t=-50 | 0.30 → 0.5143 | 0.30 → 0.5143 | предсказанная ✅ |
| H3b cross-confirm t=-31 | 0.30 → 0.7857 | 0.30 → 0.7857 | предсказанная ✅ |
| H3c cross-confirm t=-100 | 0.30 → 0.0 | 0.30 → **0.0** | предсказанная ✅ |
| H4 t ∈ [-30, 100] | без дельты | без дельты | паритет ✅ |

Математика движка проверена до третьего знака: `repeat t=-50`: 0.5143 − 0.2857×0.2 = 0.4571 ✅; `repeat t=-31`: 0.7857 − 0.0143×0.2 = 0.7829 ✅. **Модель трубы верна, semantic delta полностью предсказана и измерена.** Гейт [7] выполнен до переключения — переключение теперь не может принести сюрпризов.

**Семантический итог для ADR (теперь это факты, не гипотезы):**
- Нейтральный диапазон и положительный trust: поведение не меняется вообще.
- Враг теперь **градуирован**: лёгкий недоброжелатель (-31) почти не разрушает убеждение (0.786 vs 0.30), заклятый враг (-100) разрушает полностью (0.0). Инлайн давал всем одну цену — 0.30.
- H2 закрыт эмпирически: незнакомая пара → 0.5 в обоих режимах (дефолты выровнены, контракт get_pair для этого случая больше не белое пятно).

**Попутное наблюдение (в досье, не дельта):** в обоих режимах trust ∈ [-30, 0] создаёт «мёртвые» убеждения (confidence=0.0). Существующее поведение, не трогаем — кандидат на Phase D-обсуждение (creation threshold).

Ещё один важный статус-факт: AFTER-измерение прошло **без переключения** — harness инъектирует провайдер изолированно, значит измерение и живой рантайм разделены. Ожидаемо: режим `before` после удаления инлайна умрёт ImportError'ом — так и задокументировано в harness.

---

## Addendum S20x (Enforcement): Canonical Testimony Reliability

**Статус:** ENFORCEMENT (восстановление задокументированного контракта, не новая онтология)
**Причина:** археология выявила расхождение кода с данным ADR — `game_loop:407` вживлял
инлайновый `RelationshipReliabilityProvider` (claim_event_subscriber.py), тогда как
настоящий аудит назначает `TrustBasedReliabilityProvider` реализацией закона.

### Контракт (канонический, после enforcement)
1. Единственный путь reliability для testimony:
   `ClaimEvent → ClaimEventSubscriber → TrustBasedReliabilityProvider → BeliefRevisionEngine`.
2. Формула: `trust ∈ [-30, 100] → clamp(trust/100)`; `trust < -30 → -(|trust|-30)/70`;
   отсутствие данных (нет store / нет пары / нет ключа) → `_UNKNOWN_SOURCE_TRUST = 50` (явный prior, смена — отдельным ADR).
3. Плоское значение для любого trust ниже порога ЗАПРЕЩЕНО (табу «фиксированная
   reliability» данного ADR; подтверждено измерением: инлайн не различал врагов -31/-50/-100).

### Измеренная semantic delta (SUPERBOX-RELIABILITY-BASELINE, до/после)
Паритет: нейтральный/положительный trust, unknown-prior, create-ветка врага.
Предсказанные и подтверждённые изменения (cross-source confirm, база 0.8 от друга):
`enemy=-31: 0.30→0.786; enemy=-50: 0.30→0.514; enemy=-100: 0.30→0.0 (полное опровержение)`.
Артефакты: `reports/reliability_baseline_{before,after}.json`.

### Downstream (атомарный коммит)
- `game_loop/__init__.py` (конструкция провайдера);
- `claim_event_subscriber.py` (удаление инлайн-класса);
- `tests/IPT.py` (`INV-EPISTEMIC-TRUST-MONOTONICITY`: импорт);
- `SUPERBOX/epistemic_player_belief_test.py` (импорт + комментарий).

### Rollback
git revert атомарного коммита (все 4 файла вместе). Доказательство живой регистрации
после переключения: IPT `INV-PLAYER-EPISTEMIC-CLOSURE` (падает, если
`_register_epistemic_core` не поднялся — он в try/except, DEBT-R5).

## Addendum S205 (Enforcement): Canonical Testimony Reliability

**Статус:** APPLIED | **Тип:** ENFORCEMENT (восстановление контракта, не новая онтология)

**Причина:** археология выявила расхождение кода с данным ADR — `game_loop:407`
вживлял инлайновый `RelationshipReliabilityProvider` (claim_event_subscriber.py),
тогда как настоящий аудит назначает `TrustBasedReliabilityProvider` реализацией закона.

### Контракт (канонический)
1. Единственный путь: `ClaimEvent → ClaimEventSubscriber → TrustBasedReliabilityProvider → BeliefRevisionEngine`.
2. Формула: `trust ∈ [-30,100] → clamp(trust/100)`; `trust < -30 → −(|trust|−30)/70`;
   отсутствие данных → `_UNKNOWN_SOURCE_TRUST = 50` (явный prior; смена — отдельным ADR).
3. Плоское значение ниже порога ЗАПРЕЩЕНО (табу «фиксированная reliability»;
   измерено: инлайн не различал врагов −31/−50/−100).

### Измеренная semantic delta (SUPERBOX-RELIABILITY-BASELINE, гейт до/после)
Паритет: нейтральный/положительный trust, unknown-prior, create-ветка врага.
Подтверждённые изменения (cross-source confirm, база 0.8 от друга):
`enemy=-31: 0.30→0.786 | enemy=-50: 0.30→0.514 | enemy=-100: 0.30→0.0 (опровержение)`.
Артефакты: `reports/reliability_baseline_{before,after}.json`.

### Downstream (атомарный коммит, 7 патчей)
game_loop/__init__.py; claim_event_subscriber.py (удалён инлайн); tests/IPT.py
(INV-EPISTEMIC-TRUST-MONOTONICITY); SUPERBOX-014/015/016 (импорты);
baseline harness (docstring).

### Верификация
IPT 44/44; SUPERBOX-014/015/016 зелёные; harness AFTER == предрегистрация.

### Rollback
git revert атомарного коммита.

### Известные долги (не в рамках enforcement)
- DEBT-R1: `radius=999.0` для THEFT (phase_1_input:311) — табу ADR-148.
- DEBT-R4: `except Exception` в on_claim_event (ARCH-017).
- DEBT-R6: персистентная saves/test_sandbox в SUPERBOX → дрейф trust между прогонами.
