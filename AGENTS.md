# ENIGMA Rules

Never:

- create fallback
- bypass pipeline
- bypass DTO
- create second source of truth
- mutate snapshots
- modify DecisionHub ownership

Always:

1. Find pipeline object
2. Restore causal topology
3. Check ownership
4. Check contracts
5. Local fix first