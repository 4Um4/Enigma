# E0-PILOT-4 DecisionHub Runtime Capture Report

Run: e0_pilot_4 | 2026-11-09T21:06:57.542078
Campaign: Open_road | Ticks: 5/5

## DecisionHub.compute signature

```
(self, state: 'NPCState', personality: 'NPCProfileL0', event: 'EventContext', effective_drives: "'EffectiveDrives'", scene_state: 'Optional[Dict[str, Any]]' = None, opportunity_ctx: 'Optional[OpportunityContext]' = None, identity: "Optional['NPCIdentityL1']" = None, eco_modifiers: 'Optional[Dict[str, float]]' = None, social_modifiers: 'Optional[Dict[str, float]]' = None, reputation_modifiers: 'Optional[Dict[str, float]]' = None, drive_modifiers: 'Optional[Dict[str, float]]' = None, contract_modifiers: 'Optional[Dict[str, float]]' = None, npc_memory_modifiers: 'Optional[Dict[str, float]]' = None, epistemic_modifiers: 'Optional[Dict[str, float]]' = None, reflex_constraints: 'Optional[Dict]' = None, topic: 'Optional[str]' = None, decision_ctx: "Optional['DecisionContext']" = None, spatial_query: 'Optional[Any]' = None, all_npc_ids: 'Optional[List[str]]' = None, pending_response_target: 'Optional[str]' = None, relationship_store: 'Optional[Any]' = None, campaign_id: 'str' = '', epistemic_context: 'Optional[Any]' = None, causal_modifiers: 'Optional[Dict[str, float]]' = None, causal_addressee: 'Optional[str]' = None, cognition_modifiers: 'Optional[Dict[str, float]]' = None, need_modifiers: 'Optional[Dict[str, float]]' = None) -> 'AgentAction'
```

## NPC states (via none)

### maid_lusya
- drives: `None`
- psyche: `None`
- will_state: `None`
- stress: `None`
- rel_cache_count: `None`

### tavern_keeper_tornin
- drives: `None`
- psyche: `None`
- will_state: `None`
- stress: `None`
- rel_cache_count: `None`

## Relationships (via _rel_store)

```json
{
  "type": "V2RelationshipBackend",
  "get_pair(maid_lusya,tavern_keeper_tornin)": {
    "trust": -40.0,
    "fear": 60.0
  },
  "get_all_for_source(maid_lusya)": {
    "tavern_keeper_tornin": "{'trust': -40.0, 'fear': 60.0, 'debt': 0.0, 'respe",
    "thief_shadow": "{'trust': 30.0, 'fear': 0.0, 'debt': 0.0, 'respect",
    "guard_borko": "{'trust': 30.0, 'fear': 0.0, 'debt': 0.0, 'respect",
    "blacksmith_orm": "{'trust': 30.0, 'fear': 0.0, 'debt': 0.0, 'respect"
  },
  "get_all_for_source(tavern_keeper_tornin)": {
    "maid_lusya": "{'trust': -40.0, 'fear': 0.0, 'debt': 0.0, 'respec",
    "guard_borko": "{'trust': 20.0, 'fear': 0.0, 'debt': 0.0, 'respect",
    "merchant_goran": "{'trust': 40.0, 'fear': 0.0, 'debt': 0.0, 'respect",
    "thief_shadow": "{'trust': -20.0, 'fear': 0.0, 'debt': 0.0, 'respec"
  }
}
```

## DecisionHub calls summary

- Total compute() calls: **30**
- Calls for Lusya/Tornin: **10**
- _phase_5_decision calls: **5**
- WORLD_TICK events: **30**
- Non-WORLD_TICK events: **0**
- TALK in candidates: **11**
- TALK absent: **19**

### Event types received by DecisionHub

- `EventType.WORLD_TICK`: 30

### Winners

- `Intent.SPREAD_RUMOR`: 3
- `Intent.CHANGE_ROLE`: 7
- `Intent.SEEK_ALLY`: 12
- `Intent.OBSERVE`: 5
- `Intent.REQUEST_SERVICE`: 3

## DecisionHub calls (detail)

### Call #1: NPC=guard_borko
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.4, 'significance': 0.3, 'fear': 0.2, 'desire': 0.1}`
- Winner: **Intent.SPREAD_RUMOR** score=0.538
- TALK in candidates: `True` talk_score=`0.1946`
- Scores trace: `{'talk': 0.1946, 'warn': 0.1803, 'intimidate': -0.3401, 'flee': 0.093, 'attack': -0.4328, 'help': 0.0015, 'report': 0.1415, 'trade': -0.0668, 'observe': 0.0654, 'approach': -0.0744, 'block_path': 0.5302, 'ambush': 0.37, 'seek_ally': 0.1844, 'offer_job': 0.086, 'request_service': 0.1446, 'spread_rumor': 0.538, 'call_for_help': 0.346, 'change_role': 0.1425, 'idle': 0.0881}`

### Call #2: NPC=merchant_goran
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.2, 'significance': 0.25, 'fear': 0.15, 'desire': 0.4}`
- Winner: **Intent.CHANGE_ROLE** score=0.407
- TALK in candidates: `False` talk_score=`None`
- Scores trace: `{'intimidate': -0.5401, 'flee': 0.0275, 'attack': -0.6089, 'help': 0.0993, 'report': -0.0397, 'trade': -0.0045, 'observe': 0.044, 'seek_ally': 0.285, 'change_role': 0.407, 'idle': 0.0959}`

### Call #3: NPC=maid_lusya
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.15, 'significance': 0.2, 'fear': 0.45, 'desire': 0.2}`
- Winner: **Intent.SEEK_ALLY** score=0.3483
- TALK in candidates: `False` talk_score=`None`
- Scores trace: `{'intimidate': -0.4413, 'flee': 0.1536, 'attack': -0.5173, 'help': -0.0043, 'report': -0.0366, 'trade': 0.0374, 'observe': 0.1621, 'seek_ally': 0.3483, 'change_role': 0.222, 'idle': 0.122}`

### Call #4: NPC=blacksmith_orm
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.35, 'significance': 0.15, 'fear': 0.05, 'desire': 0.45}`
- Winner: **Intent.CHANGE_ROLE** score=0.3867
- TALK in candidates: `False` talk_score=`None`
- Scores trace: `{'intimidate': -0.3523, 'flee': -0.0314, 'attack': -0.5261, 'help': -0.0256, 'report': 0.0351, 'trade': 0.0462, 'observe': -0.0473, 'seek_ally': 0.2296, 'change_role': 0.3867, 'idle': 0.0459}`

### Call #5: NPC=thief_shadow
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.3, 'significance': 0.2, 'fear': 0.1, 'desire': 0.4}`
- Winner: **Intent.OBSERVE** score=0.279
- TALK in candidates: `True` talk_score=`-10.0134`
- Scores trace: `{'talk': -10.0134, 'warn': 0.0076, 'intimidate': -0.3603, 'flee': -9.5885, 'attack': -0.597, 'help': 0.0904, 'report': 0.1517, 'trade': -0.0082, 'observe': 0.279, 'approach': 0.0696, 'block_path': -9.5689, 'ambush': -9.5497, 'seek_ally': -9.8101, 'offer_job': -9.7023, 'request_service': -9.582, 'spread_rumor': -9.5302, 'call_for_help': -9.7469, 'change_role': -9.6118, 'idle': -0.0378}`

### Call #6: NPC=tavern_keeper_tornin
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.5, 'significance': 0.25, 'fear': 0.15, 'desire': 0.1}`
- Winner: **Intent.SEEK_ALLY** score=0.272
- TALK in candidates: `False` talk_score=`None`
- Scores trace: `{'intimidate': -0.4714, 'flee': 0.2569, 'attack': -0.5457, 'help': 0.1254, 'report': 0.0714, 'trade': -0.0547, 'observe': 0.0047, 'seek_ally': 0.272, 'change_role': 0.087, 'idle': -0.06}`

### Call #7: NPC=guard_borko
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.4, 'significance': 0.3, 'fear': 0.2, 'desire': 0.1}`
- Winner: **Intent.SEEK_ALLY** score=0.2842
- TALK in candidates: `False` talk_score=`None`
- Scores trace: `{'intimidate': -0.5128, 'flee': 0.2287, 'attack': -0.5756, 'help': 0.0281, 'report': 0.248, 'trade': -0.0194, 'observe': 0.1712, 'seek_ally': 0.2842, 'change_role': 0.0443, 'idle': 0.1192}`

### Call #8: NPC=merchant_goran
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.2, 'significance': 0.25, 'fear': 0.15, 'desire': 0.4}`
- Winner: **Intent.CHANGE_ROLE** score=0.3653
- TALK in candidates: `False` talk_score=`None`
- Scores trace: `{'intimidate': -0.5807, 'flee': 0.0171, 'attack': -0.6445, 'help': -0.0661, 'report': -0.0677, 'trade': -0.0368, 'observe': -0.0858, 'seek_ally': 0.0891, 'change_role': 0.3653, 'idle': 0.0069}`

### Call #9: NPC=maid_lusya
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.15, 'significance': 0.2, 'fear': 0.45, 'desire': 0.2}`
- Winner: **Intent.SEEK_ALLY** score=0.2168
- TALK in candidates: `False` talk_score=`None`
- Scores trace: `{'intimidate': -0.5324, 'flee': 0.2464, 'attack': -0.6655, 'help': 0.0367, 'report': 0.0336, 'trade': 0.0533, 'observe': 0.074, 'seek_ally': 0.2168, 'change_role': 0.1925, 'idle': 0.0973}`

### Call #10: NPC=blacksmith_orm
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.35, 'significance': 0.15, 'fear': 0.05, 'desire': 0.45}`
- Winner: **Intent.CHANGE_ROLE** score=0.406
- TALK in candidates: `False` talk_score=`None`
- Scores trace: `{'intimidate': -0.4679, 'flee': -0.1649, 'attack': -0.5218, 'help': 0.0001, 'report': -0.1, 'trade': 0.057, 'observe': -0.1008, 'seek_ally': 0.2442, 'change_role': 0.406, 'idle': -0.135}`

### Call #11: NPC=thief_shadow
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.3, 'significance': 0.2, 'fear': 0.1, 'desire': 0.4}`
- Winner: **Intent.OBSERVE** score=0.2548
- TALK in candidates: `False` talk_score=`None`
- Scores trace: `{'intimidate': -0.3887, 'flee': -9.7608, 'attack': -0.699, 'help': -0.0421, 'report': 0.0445, 'trade': -0.0273, 'observe': 0.2548, 'seek_ally': -9.9649, 'change_role': -9.6362, 'idle': 0.0556}`

### Call #12: NPC=tavern_keeper_tornin
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.5, 'significance': 0.25, 'fear': 0.15, 'desire': 0.1}`
- Winner: **Intent.SEEK_ALLY** score=0.219
- TALK in candidates: `False` talk_score=`None`
- Scores trace: `{'intimidate': -0.5476, 'flee': 0.1639, 'attack': -0.6162, 'help': 0.0717, 'report': -0.0385, 'trade': -0.036, 'observe': 0.0981, 'seek_ally': 0.219, 'change_role': 0.1573, 'idle': -0.0534}`

### Call #13: NPC=guard_borko
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.4, 'significance': 0.3, 'fear': 0.2, 'desire': 0.1}`
- Winner: **Intent.SPREAD_RUMOR** score=0.5199
- TALK in candidates: `True` talk_score=`0.1986`
- Scores trace: `{'talk': 0.1986, 'warn': 0.0866, 'intimidate': -0.4096, 'flee': 0.0686, 'attack': -0.495, 'help': 0.0313, 'report': 0.194, 'trade': 0.0292, 'observe': 0.1072, 'approach': -0.1753, 'block_path': 0.5009, 'ambush': 0.2893, 'seek_ally': 0.1706, 'offer_job': -0.0191, 'request_service': 0.0396, 'spread_rumor': 0.5199, 'call_for_help': 0.3173, 'change_role': 0.0284, 'idle': 0.0487}`

### Call #14: NPC=merchant_goran
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.2, 'significance': 0.25, 'fear': 0.15, 'desire': 0.4}`
- Winner: **Intent.REQUEST_SERVICE** score=0.619
- TALK in candidates: `True` talk_score=`0.0596`
- Scores trace: `{'talk': 0.0596, 'warn': -0.0504, 'intimidate': -0.5773, 'flee': -0.0318, 'attack': -0.7095, 'help': 0.0184, 'report': -0.0516, 'trade': 0.0138, 'observe': -0.0914, 'approach': -0.0394, 'seek_ally': 0.2001, 'offer_job': 0.5565, 'request_service': 0.619, 'spread_rumor': 0.0439, 'call_for_help': 0.0504, 'change_role': 0.4245, 'idle': -0.0058}`

### Call #15: NPC=maid_lusya
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.15, 'significance': 0.2, 'fear': 0.45, 'desire': 0.2}`
- Winner: **Intent.SEEK_ALLY** score=0.2253
- TALK in candidates: `False` talk_score=`None`
- Scores trace: `{'intimidate': -0.6279, 'flee': 0.1841, 'attack': -0.5342, 'help': -0.0694, 'report': -0.1119, 'trade': -0.0238, 'observe': 0.0724, 'seek_ally': 0.2253, 'change_role': 0.0738, 'idle': 0.1182}`

### Call #16: NPC=blacksmith_orm
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.35, 'significance': 0.15, 'fear': 0.05, 'desire': 0.45}`
- Winner: **Intent.CHANGE_ROLE** score=0.3824
- TALK in candidates: `False` talk_score=`None`
- Scores trace: `{'intimidate': -0.5312, 'flee': -0.0669, 'attack': -0.6929, 'help': -0.1643, 'report': -0.0712, 'trade': 0.0262, 'observe': -0.1193, 'seek_ally': 0.053, 'change_role': 0.3824, 'idle': -0.1285}`

### Call #17: NPC=thief_shadow
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.3, 'significance': 0.2, 'fear': 0.1, 'desire': 0.4}`
- Winner: **Intent.OBSERVE** score=0.4192
- TALK in candidates: `False` talk_score=`None`
- Scores trace: `{'intimidate': -0.477, 'flee': -9.7328, 'attack': -0.7375, 'help': 0.0169, 'report': -0.022, 'trade': 0.0994, 'observe': 0.4192, 'seek_ally': -9.8936, 'change_role': -9.63, 'idle': -0.1063}`

### Call #18: NPC=tavern_keeper_tornin
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.5, 'significance': 0.25, 'fear': 0.15, 'desire': 0.1}`
- Winner: **Intent.SEEK_ALLY** score=0.3013
- TALK in candidates: `False` talk_score=`None`
- Scores trace: `{'intimidate': -0.5277, 'flee': 0.0497, 'attack': -0.5669, 'help': -0.0619, 'report': 0.0868, 'trade': 0.0058, 'observe': 0.0461, 'seek_ally': 0.3013, 'change_role': 0.1037, 'idle': 0.0373}`

### Call #19: NPC=guard_borko
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.4, 'significance': 0.3, 'fear': 0.2, 'desire': 0.1}`
- Winner: **Intent.SEEK_ALLY** score=0.3305
- TALK in candidates: `False` talk_score=`None`
- Scores trace: `{'intimidate': -0.4867, 'flee': 0.1279, 'attack': -0.5983, 'help': 0.0721, 'report': 0.2833, 'trade': 0.0873, 'observe': 0.0309, 'seek_ally': 0.3305, 'change_role': 0.046, 'idle': -0.0403}`

### Call #20: NPC=merchant_goran
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.2, 'significance': 0.25, 'fear': 0.15, 'desire': 0.4}`
- Winner: **Intent.REQUEST_SERVICE** score=0.6255
- TALK in candidates: `True` talk_score=`0.2206`
- Scores trace: `{'talk': 0.2206, 'warn': -0.1108, 'intimidate': -0.6174, 'flee': -0.0739, 'attack': -0.6645, 'help': 0.0431, 'report': 0.0053, 'trade': 0.0588, 'observe': -0.0171, 'approach': -0.0108, 'seek_ally': 0.1736, 'offer_job': 0.5629, 'request_service': 0.6255, 'spread_rumor': 0.1725, 'call_for_help': 0.0704, 'change_role': 0.2557, 'idle': -0.0709}`

### Call #21: NPC=maid_lusya
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.15, 'significance': 0.2, 'fear': 0.45, 'desire': 0.2}`
- Winner: **Intent.SEEK_ALLY** score=0.4195
- TALK in candidates: `False` talk_score=`None`
- Scores trace: `{'intimidate': -0.5026, 'flee': 0.1094, 'attack': -0.693, 'help': 0.0335, 'report': -0.0211, 'trade': 0.0561, 'observe': 0.0829, 'seek_ally': 0.4195, 'change_role': 0.0925, 'idle': 0.0542}`

### Call #22: NPC=blacksmith_orm
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.35, 'significance': 0.15, 'fear': 0.05, 'desire': 0.45}`
- Winner: **Intent.CHANGE_ROLE** score=0.5403
- TALK in candidates: `True` talk_score=`0.0849`
- Scores trace: `{'talk': 0.0849, 'warn': 0.0062, 'intimidate': -0.5679, 'flee': -0.1561, 'attack': -0.6104, 'help': -0.1051, 'report': -0.0665, 'trade': -0.1056, 'observe': -0.0576, 'approach': 0.0416, 'seek_ally': 0.2381, 'offer_job': 0.3986, 'request_service': 0.5837, 'spread_rumor': 0.4008, 'call_for_help': 0.0785, 'change_role': 0.5403, 'idle': -0.1176}`

### Call #23: NPC=thief_shadow
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.3, 'significance': 0.2, 'fear': 0.1, 'desire': 0.4}`
- Winner: **Intent.OBSERVE** score=0.4514
- TALK in candidates: `True` talk_score=`-10.0076`
- Scores trace: `{'talk': -10.0076, 'warn': 0.0833, 'intimidate': -0.3074, 'flee': -9.6956, 'attack': -0.6671, 'help': -0.0974, 'report': 0.0796, 'trade': -0.0693, 'observe': 0.4514, 'approach': -0.0375, 'block_path': -9.5056, 'ambush': -9.6709, 'seek_ally': -9.844, 'offer_job': -9.7773, 'request_service': -9.7803, 'spread_rumor': -9.6354, 'call_for_help': -9.7409, 'change_role': -9.6822, 'idle': 0.0077}`

### Call #24: NPC=tavern_keeper_tornin
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.5, 'significance': 0.25, 'fear': 0.15, 'desire': 0.1}`
- Winner: **Intent.SEEK_ALLY** score=0.2323
- TALK in candidates: `False` talk_score=`None`
- Scores trace: `{'intimidate': -0.4398, 'flee': 0.0583, 'attack': -0.5065, 'help': 0.0209, 'report': 0.0923, 'trade': 0.0285, 'observe': -0.066, 'seek_ally': 0.2323, 'change_role': 0.0305, 'idle': -0.125}`

### Call #25: NPC=guard_borko
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.4, 'significance': 0.3, 'fear': 0.2, 'desire': 0.1}`
- Winner: **Intent.SEEK_ALLY** score=0.3504
- TALK in candidates: `False` talk_score=`None`
- Scores trace: `{'intimidate': -0.4852, 'flee': 0.0997, 'attack': -0.485, 'help': 0.1033, 'report': 0.2072, 'trade': 0.0218, 'observe': 0.0614, 'seek_ally': 0.3504, 'change_role': 0.1119, 'idle': -0.0893}`

### Call #26: NPC=merchant_goran
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.2, 'significance': 0.25, 'fear': 0.15, 'desire': 0.4}`
- Winner: **Intent.REQUEST_SERVICE** score=0.6114
- TALK in candidates: `True` talk_score=`0.2042`
- Scores trace: `{'talk': 0.2042, 'warn': -0.0696, 'intimidate': -0.6706, 'flee': -0.1301, 'attack': -0.7331, 'help': 0.001, 'report': -0.0723, 'trade': 0.0788, 'observe': -0.0933, 'approach': 0.0314, 'seek_ally': 0.2067, 'offer_job': 0.5401, 'request_service': 0.6114, 'spread_rumor': 0.0828, 'call_for_help': 0.1807, 'change_role': 0.3263, 'idle': -0.0582}`

### Call #27: NPC=maid_lusya
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.15, 'significance': 0.2, 'fear': 0.45, 'desire': 0.2}`
- Winner: **Intent.SEEK_ALLY** score=0.2866
- TALK in candidates: `True` talk_score=`0.1243`
- Scores trace: `{'talk': 0.1243, 'warn': -0.0232, 'intimidate': -0.6377, 'flee': 0.1752, 'attack': -0.6565, 'help': -0.0506, 'report': 0.0166, 'trade': -0.0184, 'observe': 0.0269, 'approach': -0.097, 'seek_ally': 0.2866, 'offer_job': 0.1857, 'request_service': 0.1447, 'spread_rumor': 0.3617, 'call_for_help': 0.1253, 'change_role': 0.021, 'idle': 0.1151}`

### Call #28: NPC=blacksmith_orm
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.35, 'significance': 0.15, 'fear': 0.05, 'desire': 0.45}`
- Winner: **Intent.CHANGE_ROLE** score=0.5166
- TALK in candidates: `False` talk_score=`None`
- Scores trace: `{'intimidate': -0.513, 'flee': -0.1245, 'attack': -0.7359, 'help': 0.0081, 'report': -0.0356, 'trade': 0.0336, 'observe': -0.0081, 'seek_ally': 0.0592, 'change_role': 0.5166, 'idle': -0.098}`

### Call #29: NPC=thief_shadow
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.3, 'significance': 0.2, 'fear': 0.1, 'desire': 0.4}`
- Winner: **Intent.OBSERVE** score=0.4947
- TALK in candidates: `True` talk_score=`-9.9533`
- Scores trace: `{'talk': -9.9533, 'warn': -0.0633, 'intimidate': -0.4379, 'flee': -9.6733, 'attack': -0.7277, 'help': -0.0743, 'report': -0.0667, 'trade': -0.0575, 'observe': 0.4947, 'approach': -0.0988, 'block_path': -9.5553, 'ambush': -9.659, 'seek_ally': -9.9069, 'offer_job': -9.7813, 'request_service': -9.6206, 'spread_rumor': -9.557, 'call_for_help': -9.7313, 'change_role': -9.7768, 'idle': -0.075}`

### Call #30: NPC=tavern_keeper_tornin
- Event: `EventType.WORLD_TICK` reason=`` is_world_tick=`True`
- State: drives=`None` will=`WillState.FREE` consciousness=`None`
- Personality: drives_base=`{'control': 0.5, 'significance': 0.25, 'fear': 0.15, 'desire': 0.1}`
- Winner: **Intent.SPREAD_RUMOR** score=0.4985
- TALK in candidates: `True` talk_score=`0.1947`
- Scores trace: `{'talk': 0.1947, 'warn': 0.093, 'intimidate': -0.4199, 'flee': 0.0714, 'attack': -0.6414, 'help': -0.0881, 'report': 0.124, 'trade': 0.0401, 'observe': -0.0199, 'approach': -0.2208, 'seek_ally': 0.2679, 'offer_job': 0.0746, 'request_service': 0.0251, 'spread_rumor': 0.4985, 'call_for_help': 0.3091, 'change_role': 0.0719, 'idle': -0.1313}`

## _phase_5_decision calls

- #1: args=1 returned=True error=
- #2: args=1 returned=True error=
- #3: args=1 returned=True error=
- #4: args=1 returned=True error=
- #5: args=1 returned=True error=

## Answers to 7 questions

**Q1. Is DecisionHub called for Lusya and Tornin?**
→ **YES**
   Evidence: 30 total calls, 10 for pair NPCs.

**Q2. (N/A — compute() is called)**

**Q3. Is TALK among candidates?**
→ **YES**
   Evidence: 11 calls with TALK, 19 without.

**Q4. Why does TALK lose?**
→ See scores_trace in call details above.

**Q5. (N/A)**

**Q6. What event type does DecisionHub receive?**
→ **See event_types above**
   WORLD_TICK events: 30, Non-WORLD_TICK: 0

**Q7. Does WORLD_TICK absence affect result?**
→ **TALK is in candidates — WORLD_TICK question is moot**

## Positions and distance

- T1: dist=3.48 dh_calls=6 phase5=1
- T2: dist=3.44 dh_calls=12 phase5=2
- T3: dist=3.42 dh_calls=18 phase5=3
- T4: dist=3.41 dh_calls=24 phase5=4
- T5: dist=3.41 dh_calls=30 phase5=5

