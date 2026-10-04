`ADR-O-411` [STANDARD] **IMPACT**
Files: backend/app/services/combat/injury_processor.py, backend/app/services/body/body_engine.py, backend/tests/test_s2b7_injury_chain.py
# ADR-O-411 Impact Audit — S2B.7 Pain/Injury
> Детальный аудит ОДНОГО ADR. Единый атлас: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- physiology (injury/pain/capability-деривация), combat (InjuryProcessor), body (стоимость движения), state-мутация (received_tick)

## Найденный production-баг (ядро аудита)
InjuryProcessor.handle читал `npc.get("body_state")` — ключа НЕ СУЩЕСТВУЕТ в NPCStateSnapshot
(все поля плоские; contract — models/idle_tick.py:22). isinstance-гвард всегда False →
DEAD-check был мёртв → мёртвый NPC с ранами получал blood_loss_delta/pain_delta каждый тик
(нарушение ADR-127 Death Lock). Третий рецидив класса «unit input ≠ production input»:
BodyEngine (S2B.5) → combat-билдеры → InjuryProcessor. Класс закрыт институционально.

## Revert-инструкция для аудита (red-first пруф)
1. Откатить hunk PATCH-1 в injury_processor.py (вернуть блок с `_body = npc.get("body_state")`).
2. Запуск: pytest tests/test_action_commitment.py -k "S2B7"
   → test_dead_npc_produces_no_deltas КРАСНЫЙ (мёртвый NPC получает дельты).
Честная пометка: обе ступени (тест + фикс) применены до первого объединённого прогона —
runtime red-screenshot не снят; баг доказан сопоставлением контракта снапшота и кода чтения,
гвард вечный.

## Downstream Consumers
- is_capable: BodyStateView → AffordanceResolver IS_CAPABLE (W2-предикат всех объектных
  действий) — injury-aware без расширения реестра (мини-ADR ADR-O-372 не потребовался).
- BodyEngine: раненые ноги → energy/fatigue расход ×(1+K·impairment).
- evaluate_vital_state: НЕ тронут (structural/hemorrhagic пути смерти без изменений).
- S2B.8 Recovery (будущее): received_tick = возраст раны (эпизод датирован).
- Запрет соблюдён: injury → emotion НЕ реализован (S2B.7-4); PK/somatic — не тронуты.

## Runtime Impact
- InjuryProcessor: ноль (замена мёртвого чтения живым + гигиена).
- BodyEngine: O(ран) на NPC с ранами; без ран — байт-идентично (множитель 1.0).
- vital_state: O(injuries) чистые функции, только при вызове.
- received_tick: аддитивный ключ в свободном dict-поле; round-trip-safe.

## Sandbox Tests
- tests/test_action_commitment.py: TestS2B7ProjectionContract ×4 (вечный гвард),
  TestS2B7CapabilityDegradation ×6 (деривации + дифференциал + предикат).
- tests/test_s2b7_injury_chain.py: production-гейт §4.4 (живой удар → … → дифференциал).
- Контроль обратной совместимости: TestS2B5Fatigue 0.215 (байт-идентичность без ран).

## Открытые вердикты Мастера
- INJURY_LOCOMOTION_WEAR=1.0 (×2 стоимость при полном разрушении зон) — v1 структурный.
- [S2B7-G-debt]: точная прокидка tick_number через apply_batch (5 call sites; сейчас
  provenance-канон intent_formed_at, может быть 0 для idle-происхождений).
- Wound (physical.py:244) — dormant Multiple Representation (аватарный D&D-путь);
  активация = мини-ADR.
- Калибровочное наблюдение: force=100 слэш в ногу → DEATH bl=1.000 в живом контуре.
- Эскалации (не тронуты, вне сессии): perceptual-ветки DecayHandler (PK не в снапшоте);
  чужие красные сон (coupling_profile, pre-existing S305/S307) и фуд (hunger).

## Rollback
- injury_processor.py: вернуть блок body_state-чтения (гвард станет красным — сигнальная
  целостность). BodyEngine: множитель → константа 1.0 (удалить строки _injury_cost).
- vital_state: деривации аддитивны, is_capable-ветка откатывается удалением блока.
- state_applicator: current_tick kwarg default 0 — удаление = revert одного hunk.
- Тесты не влияют на runtime.