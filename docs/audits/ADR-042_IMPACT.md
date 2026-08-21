# ADR-042 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-042` [STANDARD] **IMPACT**
# ADR-042 Impact Audit (Bugfix: NPC State Injection Wipe)
## Changed Domains
- Spatial/NPC State (all_npcs_raw injection in tick_orchestrator.py)
## Downstream Consumers
- DirectiveInterpretationSubscriber (reads all_npcs_raw)
- DecisionHub
## Runtime Impact
- RAM: 0 (guard prevents list wipe, no extra allocations)
## Sandbox Tests
- Isolated Python tests passed (list guard works, preserves loaded NPCs)
## Rollback
- Revert ctx.all_npcs_raw = ctx.npc_states in tick_orchestrator.py (remove guard)

