# ADR-O-367 Impact Audit
> Детальный аудит одного ADR. Единый атлас: docs/ADR (Architecture Decision Records).md

## Changed Domains
- trust, fear (дельты RelationshipStore), faction reputation (побочно, ветки M-12), social

## Downstream Consumers
- RelationshipStore (SSOT) → DecisionHub (get_weights_for_decision), FateTracker, EndScreenDataBuilder
- ObservabilityTap / metrics M0 (rel_captures), LabScreen (UI-полоса Trust)
- WillpowerGate (конвертер tick_utils потребляет ту же семантику)

## Runtime Impact
- O(1) на вмешательство (lookup + вызов компилятора). RAM/latency незначимы.
- S116-фоллбэк: scene_state-биндинг — no-op для run()-прогонов (доказано изолированными повторами).

## Sandbox Tests
- backend/tests/calibration_lab/test_m1_trust_intervention.py (дельта trust + статусы тиков без error)
- Полный M0-suite: 52 passed / 1 skipped (pre-existing SUPERBOX-014)
- Runtime SMOKE: 14 тиков, инъекция на 11-м, statuses 14×ok

## Rollback
- Ветвь аддитивна за скобкой semantic_action ∈ {HELP, BLACKMAIL, ACCUSE} — удаление ветви + инъекции возвращает предыдущее поведение.
- init_campaign-вызов в start() автономен. S116-патч автономен (вернуть пустой SimpleNamespace — ценой возврата латентного краша player-ветки).