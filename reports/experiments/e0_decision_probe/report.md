# E0-PILOT-3 Decision Probe Report

Run: e0_decision_probe | 2026-11-09T20:51:51.225017
Campaign: Open_road | Ticks: 5/5

## 1. Runtime NPC psychology (initial)

### maid_lusya
- drives: `None`
- psyche: `None`
- will_state: `None`
- stress: `None`
- consciousness: `None`
- emotion: `None`
- affective_load: `None`
- relationship_cache_count: `None`
- relationship_cache: `None`
- activity_state: `None`

### tavern_keeper_tornin
- drives: `None`
- psyche: `None`
- will_state: `None`
- stress: `None`
- consciousness: `None`
- emotion: `None`
- affective_load: `None`
- relationship_cache_count: `None`
- relationship_cache: `None`
- activity_state: `None`

## 2. Positions and distance

| Tick | Lusya | Tornin | Dist | In range (<= 5.0)? |
|------|-------|--------|------|------|
| 0 | fireplace(7.915023148148147,1.8505015432098766) | behind_bar(4.5,2.5) | 3.48 | YES |
| 1 | tavern:node_16(7.915023148148147,1.8505015432098766) | tavern:fireplace(4.5,2.5) | 3.48 | YES |
| 2 | tavern:node_16(9.41326736111111,2.171408564814815) | tavern:fireplace(6.0,2.625) | 3.44 | YES |
| 3 | tavern:node_16(10.911511574074073,2.4923155864197533) | tavern:fireplace(7.5,2.75) | 3.42 | YES |
| 4 | tavern:node_16(12.409755787037035,2.8132226080246916) | tavern:fireplace(9.0,2.875) | 3.41 | YES |
| 5 | tavern:fireplace(10.5,3.0) | tavern:node_16(13.908,3.13412962962963) | 3.41 | YES |

Lost proximity during run: **False**

## 3. DecisionHub

- Found: `False`
- Location: `not found`
- Wrapped (runner-level): `False`
- Restored: `False`
- compute() call count: `0`

### Log traces: **NONE found** — [TRACE][DECISION_SCORE] not printed (gated or DecisionHub not reached)

## 4. TALK analysis

- TALK in wrapper candidates: `False`
- TALK in log traces: `False`
- TALK scores: `[]`
- **TALK status: UNVERIFIED — no DecisionHub data (neither wrapper nor log traces)**

## 5. Verdict per conclusion

| Conclusion | Status |
|---|---|
| Runtime psychology data exists (drives, psyche) | UNVERIFIED |
| Execution reaches DecisionHub.compute | UNVERIFIED |
| TALK appears among candidates | UNVERIFIED |
| TALK blocked before scoring | NOT_APPLICABLE |
| NPCs lose proximity (> 5.0m) | PARTIALLY VERIFIED |

## 6. NPC final state (after 5 ticks)

### maid_lusya
- drives: `None`
- will_state: `None`
- stress: `None`
- relationship_cache_count: `None`

### tavern_keeper_tornin
- drives: `None`
- will_state: `None`
- stress: `None`
- relationship_cache_count: `None`

