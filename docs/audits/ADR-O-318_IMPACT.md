# ADR-O-318 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-O-318` [STANDARD] **IMPACT**
# ADR-O-318 Impact Audit: Uncertainty as First-Class Citizen & ObservedFacts
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`
## Changed Domains
- Perception (Cognition Layer)
- Verbalization (DM Contract)
## Downstream Consumers
- `PhenomenologyProjectionService` (генерирует данные)
- `WorldSnapshotBuilder` (пробрасывает в API DTO)
- `SceneOutcomeBuilder` (пробрасывает в DMFrame)
- Frontend (рендерит UI на основе confidence)
## Runtime Impact
- RAM: +2 поля на DTO (minimal).
- Latency: Детерминированный маппер в `BehaviorManifestationService` добавляет < 1ms на NPC.
## Sandbox Tests
- IPT (INV-NPC-MOVE, INV-TIME-GROW)
- `test_tick_orchestrator_full_loop.py`
## Rollback
- Удалить поля `confidence`, `possible_causes`, `observed_facts` из DTO и мапперов.


Files: N/A
