# E0-PILOT-5 Non-Hostile NPC Interaction Report

Run: e0_pilot_5 | 2026-11-10T00:04:28.949188
Campaign: Open_road | Ticks: 10/10

## Pair selection

**Selected: maid_lusya <-> blacksmith_orm**

| Field | Value |
|---|---|
| trust maid_lusya->blacksmith_orm | 30.0 |
| trust blacksmith_orm->maid_lusya | 70.0 |
| fear maid_lusya->blacksmith_orm | 0.0 |
| fear blacksmith_orm->maid_lusya | 0.0 |
| distance | 3.36 |
| in_range (<= 5.0) | True |
| any_hostile | False |

## Result classification

**TALK_CANDIDATE_BUT_LOSES**

## DecisionHub summary

- Total compute() calls: 59
- Pair calls: 20
- TALK in candidates (pair): 6
- TALK won (pair): 0
- TALK won (all NPC): 0

### Pair winners

- `Intent.SEEK_ALLY`: 10
- `Intent.CHANGE_ROLE`: 10

## DecisionHub calls for pair (detail)

### Call #3: maid_lusya
- Event: `EventType.WORLD_TICK` reason=``
- Winner: **Intent.SEEK_ALLY** score=0.3483
- TALK in candidates: `False` talk_score=`None`
- drives_base: `{'control': 0.15, 'significance': 0.2, 'fear': 0.45, 'desire': 0.2}`
- Top 5 scores: [('seek_ally', 0.3483), ('change_role', 0.222), ('observe', 0.1621), ('flee', 0.1536), ('idle', 0.122)]

### Call #4: blacksmith_orm
- Event: `EventType.WORLD_TICK` reason=``
- Winner: **Intent.CHANGE_ROLE** score=0.3867
- TALK in candidates: `False` talk_score=`None`
- drives_base: `{'control': 0.35, 'significance': 0.15, 'fear': 0.05, 'desire': 0.45}`
- Top 5 scores: [('change_role', 0.3867), ('seek_ally', 0.2296), ('trade', 0.0462), ('idle', 0.0459), ('report', 0.0351)]

### Call #9: maid_lusya
- Event: `EventType.WORLD_TICK` reason=``
- Winner: **Intent.SEEK_ALLY** score=0.2168
- TALK in candidates: `False` talk_score=`None`
- drives_base: `{'control': 0.15, 'significance': 0.2, 'fear': 0.45, 'desire': 0.2}`
- Top 5 scores: [('flee', 0.2464), ('seek_ally', 0.2168), ('change_role', 0.1925), ('idle', 0.0973), ('observe', 0.074)]

### Call #10: blacksmith_orm
- Event: `EventType.WORLD_TICK` reason=``
- Winner: **Intent.CHANGE_ROLE** score=0.406
- TALK in candidates: `False` talk_score=`None`
- drives_base: `{'control': 0.35, 'significance': 0.15, 'fear': 0.05, 'desire': 0.45}`
- Top 5 scores: [('change_role', 0.406), ('seek_ally', 0.2442), ('trade', 0.057), ('help', 0.0001), ('report', -0.1)]

### Call #15: maid_lusya
- Event: `EventType.WORLD_TICK` reason=``
- Winner: **Intent.SEEK_ALLY** score=0.2253
- TALK in candidates: `False` talk_score=`None`
- drives_base: `{'control': 0.15, 'significance': 0.2, 'fear': 0.45, 'desire': 0.2}`
- Top 5 scores: [('seek_ally', 0.2253), ('flee', 0.1841), ('idle', 0.1182), ('change_role', 0.0738), ('observe', 0.0724)]

### Call #16: blacksmith_orm
- Event: `EventType.WORLD_TICK` reason=``
- Winner: **Intent.CHANGE_ROLE** score=0.3824
- TALK in candidates: `False` talk_score=`None`
- drives_base: `{'control': 0.35, 'significance': 0.15, 'fear': 0.05, 'desire': 0.45}`
- Top 5 scores: [('change_role', 0.3824), ('seek_ally', 0.053), ('trade', 0.0262), ('flee', -0.0669), ('report', -0.0712)]

### Call #21: maid_lusya
- Event: `EventType.WORLD_TICK` reason=``
- Winner: **Intent.SEEK_ALLY** score=0.4195
- TALK in candidates: `False` talk_score=`None`
- drives_base: `{'control': 0.15, 'significance': 0.2, 'fear': 0.45, 'desire': 0.2}`
- Top 5 scores: [('seek_ally', 0.4195), ('flee', 0.1094), ('change_role', 0.0925), ('observe', 0.0829), ('trade', 0.0561)]

### Call #22: blacksmith_orm
- Event: `EventType.WORLD_TICK` reason=``
- Winner: **Intent.CHANGE_ROLE** score=0.5403
- TALK in candidates: `True` talk_score=`0.0789`
- drives_base: `{'control': 0.35, 'significance': 0.15, 'fear': 0.05, 'desire': 0.45}`
- Top 5 scores: [('request_service', 0.5777), ('change_role', 0.5403), ('spread_rumor', 0.3948), ('offer_job', 0.3926), ('seek_ally', 0.2321)]

### Call #27: maid_lusya
- Event: `EventType.WORLD_TICK` reason=``
- Winner: **Intent.SEEK_ALLY** score=0.2866
- TALK in candidates: `True` talk_score=`0.1243`
- drives_base: `{'control': 0.15, 'significance': 0.2, 'fear': 0.45, 'desire': 0.2}`
- Top 5 scores: [('spread_rumor', 0.3617), ('seek_ally', 0.2866), ('offer_job', 0.1857), ('flee', 0.1752), ('request_service', 0.1447)]

### Call #28: blacksmith_orm
- Event: `EventType.WORLD_TICK` reason=``
- Winner: **Intent.CHANGE_ROLE** score=0.5166
- TALK in candidates: `False` talk_score=`None`
- drives_base: `{'control': 0.35, 'significance': 0.15, 'fear': 0.05, 'desire': 0.45}`
- Top 5 scores: [('change_role', 0.5166), ('seek_ally', 0.0472), ('trade', 0.0216), ('help', -0.0039), ('observe', -0.0201)]

### Call #33: maid_lusya
- Event: `EventType.WORLD_TICK` reason=``
- Winner: **Intent.SEEK_ALLY** score=0.3926
- TALK in candidates: `False` talk_score=`None`
- drives_base: `{'control': 0.15, 'significance': 0.2, 'fear': 0.45, 'desire': 0.2}`
- Top 5 scores: [('seek_ally', 0.3926), ('flee', 0.2397), ('change_role', 0.1452), ('observe', 0.1381), ('idle', 0.0554)]

### Call #34: blacksmith_orm
- Event: `EventType.WORLD_TICK` reason=``
- Winner: **Intent.CHANGE_ROLE** score=0.5832
- TALK in candidates: `False` talk_score=`None`
- drives_base: `{'control': 0.35, 'significance': 0.15, 'fear': 0.05, 'desire': 0.45}`
- Top 5 scores: [('change_role', 0.5832), ('seek_ally', 0.1145), ('report', 0.0124), ('trade', -0.0054), ('idle', -0.0762)]

### Call #39: maid_lusya
- Event: `EventType.WORLD_TICK` reason=``
- Winner: **Intent.SEEK_ALLY** score=0.3234
- TALK in candidates: `True` talk_score=`0.1598`
- drives_base: `{'control': 0.15, 'significance': 0.2, 'fear': 0.45, 'desire': 0.2}`
- Top 5 scores: [('seek_ally', 0.3234), ('flee', 0.1874), ('trade', 0.1795), ('call_for_help', 0.1722), ('talk', 0.1598)]

### Call #40: blacksmith_orm
- Event: `EventType.WORLD_TICK` reason=``
- Winner: **Intent.CHANGE_ROLE** score=0.5681
- TALK in candidates: `True` talk_score=`0.0062`
- drives_base: `{'control': 0.35, 'significance': 0.15, 'fear': 0.05, 'desire': 0.45}`
- Top 5 scores: [('request_service', 0.6782), ('change_role', 0.5681), ('offer_job', 0.3398), ('spread_rumor', 0.2153), ('seek_ally', 0.1642)]

### Call #44: maid_lusya
- Event: `EventType.WORLD_TICK` reason=``
- Winner: **Intent.SEEK_ALLY** score=0.5085
- TALK in candidates: `False` talk_score=`None`
- drives_base: `{'control': 0.15, 'significance': 0.2, 'fear': 0.45, 'desire': 0.2}`
- Top 5 scores: [('seek_ally', 0.5085), ('flee', 0.189), ('change_role', 0.1138), ('observe', 0.099), ('idle', 0.0326)]

### Call #45: blacksmith_orm
- Event: `EventType.WORLD_TICK` reason=``
- Winner: **Intent.CHANGE_ROLE** score=0.6137
- TALK in candidates: `False` talk_score=`None`
- drives_base: `{'control': 0.35, 'significance': 0.15, 'fear': 0.05, 'desire': 0.45}`
- Top 5 scores: [('change_role', 0.6137), ('seek_ally', 0.0588), ('help', -0.0945), ('trade', -0.1339), ('flee', -0.1491)]

### Call #50: maid_lusya
- Event: `EventType.WORLD_TICK` reason=``
- Winner: **Intent.SEEK_ALLY** score=0.3744
- TALK in candidates: `True` talk_score=`0.0538`
- drives_base: `{'control': 0.15, 'significance': 0.2, 'fear': 0.45, 'desire': 0.2}`
- Top 5 scores: [('seek_ally', 0.3744), ('spread_rumor', 0.2909), ('change_role', 0.1696), ('flee', 0.1382), ('offer_job', 0.1332)]

### Call #51: blacksmith_orm
- Event: `EventType.WORLD_TICK` reason=``
- Winner: **Intent.CHANGE_ROLE** score=0.5944
- TALK in candidates: `True` talk_score=`-0.0865`
- drives_base: `{'control': 0.35, 'significance': 0.15, 'fear': 0.05, 'desire': 0.45}`
- Top 5 scores: [('change_role', 0.5944), ('request_service', 0.5609), ('offer_job', 0.3267), ('spread_rumor', 0.1651), ('seek_ally', 0.0466)]

### Call #56: maid_lusya
- Event: `EventType.WORLD_TICK` reason=``
- Winner: **Intent.SEEK_ALLY** score=0.4337
- TALK in candidates: `False` talk_score=`None`
- drives_base: `{'control': 0.15, 'significance': 0.2, 'fear': 0.45, 'desire': 0.2}`
- Top 5 scores: [('seek_ally', 0.4337), ('change_role', 0.1021), ('idle', 0.0689), ('flee', 0.0559), ('observe', -0.047)]

### Call #57: blacksmith_orm
- Event: `EventType.WORLD_TICK` reason=``
- Winner: **Intent.CHANGE_ROLE** score=0.7212
- TALK in candidates: `False` talk_score=`None`
- drives_base: `{'control': 0.35, 'significance': 0.15, 'fear': 0.05, 'desire': 0.45}`
- Top 5 scores: [('change_role', 0.7212), ('seek_ally', 0.1555), ('observe', -0.0772), ('flee', -0.0782), ('report', -0.1171)]

## Dialogue detection

### Recent dialogues per tick

- T1: count=0 source=`get_recent_dialogues returned empty or not found`
- T2: count=0 source=`error: TaskScheduler.get_recent_dialogues() missing 1 required positional argument: 'current_time'`
- T3: count=0 source=`error: TaskScheduler.get_recent_dialogues() missing 1 required positional argument: 'current_time'`
- T4: count=0 source=`error: TaskScheduler.get_recent_dialogues() missing 1 required positional argument: 'current_time'`
- T5: count=0 source=`error: TaskScheduler.get_recent_dialogues() missing 1 required positional argument: 'current_time'`
- T6: count=0 source=`error: TaskScheduler.get_recent_dialogues() missing 1 required positional argument: 'current_time'`
- T7: count=0 source=`error: TaskScheduler.get_recent_dialogues() missing 1 required positional argument: 'current_time'`
- T8: count=0 source=`error: TaskScheduler.get_recent_dialogues() missing 1 required positional argument: 'current_time'`
- T9: count=0 source=`error: TaskScheduler.get_recent_dialogues() missing 1 required positional argument: 'current_time'`
- T10: count=0 source=`error: TaskScheduler.get_recent_dialogues() missing 1 required positional argument: 'current_time'`

### LLM calls (from JSONL log)

Total LLM calls during run: **0**


## Positions and distance

| Tick | maid_lusya pos | blacksmith_orm pos | Dist | In range? |
|------|-------|--------|------|------|
| 1 | tavern:node_16(32.94835648148147,6.8685015432098835) | tavern:main_hall(35.53333333333332,9.018000000000008) | 3.36 | YES |
| 2 | tavern:node_16(34.44660069444443,7.189408564814822) | tavern:main_hall(34.19999999999999,9.518000000000008) | 2.34 | YES |
| 3 | tavern:node_16(35.94484490740739,7.510315586419761) | tavern:main_hall(32.86666666666665,10.018000000000008) | 3.97 | YES |
| 4 | tavern:node_16(37.44308912037035,7.831222608024699) | tavern:fireplace(35.53333333333332,8.018000000000008) | 1.92 | YES |
| 5 | tavern:fireplace(35.53333333333332,8.018000000000008) | tavern:fireplace(32.86666666666665,9.684666666666674) | 3.14 | YES |
| 6 | tavern:fireplace(37.23733333333332,8.085064814814823) | tavern:fireplace(34.19999999999999,8.851333333333342) | 3.13 | YES |
| 7 | tavern:node_16(38.94133333333332,8.152129629629638) | tavern:node_16(38.94133333333332,8.152129629629638) | 0.0 | NO |
| 8 | tavern:node_16(37.23733333333332,8.085064814814823) | tavern:node_16(37.23733333333332,8.085064814814823) | 0.0 | NO |
| 9 | tavern:fireplace(35.53333333333332,8.018000000000008) | tavern:fireplace(35.53333333333332,8.018000000000008) | 0.0 | NO |
| 10 | tavern:fireplace(37.23733333333332,8.085064814814823) | tavern:fireplace(37.23733333333332,8.085064814814823) | 0.0 | NO |

## Classification criteria (per TZ §4)

- TALK is in candidates but loses to other intents.

