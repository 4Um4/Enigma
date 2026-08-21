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
