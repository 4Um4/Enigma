# ADR-053 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-053` [STANDARD] **IMPACT**
# ADR-053 Impact Audit: LifeEngine Intent Pipeline Restoration
## Changed Domains
- npc (life_engine), spatial (tick_orchestrator)

## Downstream Consumers
- TickOrchestrator (теперь получает реальные life_intents)
- MovementEngine (теперь обрабатывает запросы на перемещение от расписания)

## Runtime Impact
- Устранение Silent Pipeline Corruption: намерения больше не теряются на границе LifeEngine -> TickOrchestrator.
- CPU нейтрально, но Latency движения NPC снижается (намерения обрабатываются в тот же тик).

## Sandbox Tests
- backend/tests/sandbox/test_schedule_locomotion.py (2 passed)

## Rollback
- Вернуть `changes = self._simulate_minor(...)` и `all_changes.extend(changes)` в LifeEngine.tick().



Files: N/A
