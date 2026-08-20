# ADR-DET-02 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-DET-02` [STANDARD] **IMPACT**
# ADR-DET-02_IMPACT
## Changed Domains
- DOM-09 (Social & Affective Architecture): Устранена прямая мутация `trust_delta` из `EMOTION` домена.
- DOM-06 (State Mutation): Восстановлена Domain Boundary Integrity.

## Downstream Consumers
- **StateApplicator**: Теперь `_apply_deltas` строго соблюдает Single Writer Policy для `trust_delta` (SOCIAL only).

## Runtime Impact
- RAM: 0
- Latency: 0
- Инвариант I-CORE-05 восстановлен.

## Sandbox Tests
- `DriftLaboratory` (200 тиков): `comparisons=345 rate=1.725/tick`, 0 крашей.

## Rollback
- Revert changes in `backend/app/services/npc/state_applicator.py` (вернуть `trust_delta *= 2.0` без проверки домена).

---

path: /project/docs/ADR (Architecture Decision Records).md
Назначение: Добавление записи о закрытии DEBT-DET-02.

## DOM-09: SOCIAL & AFFECTIVE ARCHITECTURE (SSOT & Causal Derivation)

---

**DEBT-DET-02 закрыт.** 

Мы стабилизировали SUPERBOX, восстановили трубу CDS (SHI) и закрыли утечку доменов. 
В реестре долгов остались:
- **P2**: DEBT-310.1 (Windup = Hold & Release Gate) и DEBT-310.2 (Stale Intent Validation) — требуют рефакторинга Phase 6/7.
- **P3**: DEBT-S85.1.1, DEBT-DET-01, DEBT-DET-03 — cleanup.
- **Deferred**: DEBT-SEM-01 (Semantic Arbitration Layer).

Какую задачу будем решать следующей?


Files: N/A
