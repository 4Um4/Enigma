# ADR-043/057 Impact Audit (Bugfix: Service Duty Bridge)
## Changed Domains
- Social (Legitimacy calculation, Key mismatch fix)
## Downstream Consumers
- DecisionHub (receives obedience pressure)
## Rollback
- Remove _service_archetypes check
- Revert n.get npc_id or id
