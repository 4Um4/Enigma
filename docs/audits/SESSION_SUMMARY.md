# Сессия 23.05.2026: Pipeline Resurrection & Spatial Ontology Merger
## Статус: Pipeline Resurrected. Spatial Targeting Fixed.

### Fixed Issues:
1. all_npcs_raw guard (LifeEngine empty cache wipe)
2. Semantic Black Hole (ActionType.UNCERTAIN -> None)
3. Key Mismatch (id vs npc_id)
4. Service Duty Bridge (Maid/TavernKeeper obedience)
5. Phantom import app.domain.decision
6. AgentAction immutable mutation (dataclasses.replace)
7. Archetype field in NPCProfileL0
8. _archetype survives _deep_merge
9. EventContext.get guard (isinstance dict)
10. UnboundLocalError dm (variable order)
11. local_position priority over macro position (entrance bug)
12. Player position sync (bar_area vs entrance)

### Architectural Limits (Next Sprint):
- TraversalState for smooth movement (ADR-019)
- Spatial Alias Map for Editor->Runtime node resolution
- DecisionHub natural communication on directive pressure
