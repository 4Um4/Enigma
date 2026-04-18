(.venv) PS C:\DDD\Codex\VSC_Enigma\Enigma> .\start_enigma.bat   
[INIT] Cleaning stale processes...
[INIT] Cleaning __pycache__...
[INFO] Root: C:\DDD\Codex\VSC_Enigma\Enigma                                                                                                                                                                                
[INFO] Logs: C:\DDD\Codex\VSC_Enigma\Enigma\backend\logs                                                                                                                                                                   
[INFO] Python: 3.11.9                                                                                                                                                                                                      
                                                                                                                                                                                                                           
[0/5] Checking LLM binary...
[OK] llama-server.exe found

[1/5] Starting LLM server...                                                                                                                                                                                               
[INFO] Waiting for LLM server (max 450 sec)...                                                                                                                                                                             
[INFO] LLM loading... 5/450 sec                                                                                                                                                                                            
[OK] LLM ready (5 sec)                                                                                                                                                                                                     

[1.5/5] Resetting campaign state...
[OK] Deleted: campaign_state.json
[OK] Deleted: session file

[2/5] Starting Backend...
[OK] Backend ready (0 sec)

[3/5] Starting Frontend...
[OK] Frontend started

[4/5] Opening browser...

[5/5] ==================== ENIGMA LIVE ====================
   Frontend:  http://127.0.0.1:3000
   Backend:   http://127.0.0.1:8000
   API Docs:  http://127.0.0.1:8000/docs
   Debug:     http://127.0.0.1:8000/api/debug/vram
   Logs:      C:\DDD\Codex\VSC_Enigma\Enigma\backend\logs
   ====================================================

   Tailing backend log (Ctrl+C to exit)...

INFO:     Started server process [4268]
INFO:     Waiting for application startup.

=== STARTUP: Enigma Backend ===
Router initialized. ModelPool: {'qwen_7b': True}
Lazy loading enabled: only one model in VRAM at a time
✓ LLM Router initialized
✓ ErrorInterpreter + VRAMMonitor initialized
✓ JSONL startup log written
✓ ModelPool.debug = True
✓ GameLoop initialized (app.state)

=== Проверка LLM сервера ===
  ✅ LLM server доступен: http://127.0.0.1:8080

=== Application startup complete ===

  Frontend:  http://127.0.0.1:3001
  Backend:   http://127.0.0.1:8000
  API Docs:  http://127.0.0.1:8000/docs
  VRAM:      http://127.0.0.1:8000/api/debug/vram

INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     127.0.0.1:51334 - "GET /api/health HTTP/1.1" 200 OK
INFO:     127.0.0.1:61748 - "GET /api/health HTTP/1.1" 200 OK
INFO:     127.0.0.1:61748 - "GET /api/characters/demo-campaign HTTP/1.1" 200 OK
[PLAYER_SELECT] Campaign: demo-campaign, Player: Демеург
[PLAYER_SESSION_CREATED] Session ID: 6b9ea6ad-a8d5-4b8c-a721-56e639774c67
[SESSION_SAVED] Campaign: demo-campaign, File: C:\DDD\Codex\VSC_Enigma\Enigma\backend\data\sessions\demo-campaign.json
INFO:     127.0.0.1:61748 - "POST /api/player/session/demo-campaign HTTP/1.1" 200 OK
INFO:     127.0.0.1:61748 - "GET /api/session/state/demo-campaign HTTP/1.1" 200 OK
INFO:     127.0.0.1:61748 - "GET /api/npcs/demo-campaign HTTP/1.1" 200 OK
INFO:     127.0.0.1:61748 - "POST /api/game/action/stream HTTP/1.1" 200 OK
[RECENT_MEM] 3 entries, dm_fields=[True, True, True]
[NPC_LOADER] Пропущен non-physical маркер 'maid_dress' у NPC maid_lusya
[NPC_LOADER] Пропущен non-physical маркер 'tray' у NPC maid_lusya
[LIFE_ENGINE] 4 изменений применено
[TARGET] No target found in: осматриваюсь...
[DEBUG SPATIAL] location=tavern_silver_wolf, npc_positions keys=['tavern_keeper_tornin', 'maid_lusya', 'thief_shadow']
[WM_CHECK_START]
[WM_CHECK] campaign=demo-campaign, wm_keys=[]
[EVENT_TYPE] Router classified as: player_interacts
[EVENT_BUS] Published: PLAYER_SPOKE, target=None
[DEBUG DM] is_valid=True, scene_context=SceneContext(location_id='tavern_silver_wolf', nearby_npcs=[{'npc_id': 'tavern_keeper_tornin', 'location_id': 'tavern_silver_wolf', 'distance_to_player': 4.0, 'facing_towards_player': True}, {'npc_id': 'maid_lusya', 'location_id': 'tavern_silver_wolf', 'distance_to_player': 2.5, 'facing_towards_player': True}, {'npc_id': 'thief_shadow', 'location_id': 'tavern_silver_wolf', 'distance_to_player': 4.61, 'facing_towards_player': True}], visible_objects={'bar_counter': {'name': 'барная стойка', 'state': 'intact', 'material': 'oak', 'hp': 30, 'max_hp': 30, 'interactable': True}, 'tables_1': {'name': 'столы #1', 'state': 'intact', 'interactable': True, 'instance_of': 'tables'}, 'tables_2': {'name': 'столы #2', 'state': 'intact', 'interactable': True, 'instance_of': 'tables'}, 'tables_3': {'name': 'столы #3', 'state': 'intact', 'interactable': True, 'instance_of': 'tables'}, 'tables_4': {'name': 'столы #4', 'state': 'intact', 'interactable': True, 'instance_of': 'tables'}}, environmental_modifiers={'light': 1.0, 'noise': 0.0, 'density': 0.0, 'danger': 0.0}, line_of_sight={'tavern_keeper_tornin': True, 'maid_lusya': True, 'thief_shadow': True}), error=None
[SESSION_RESET] tavern_keeper_tornin: stress=0 emotion=NEUTRAL mask=NONE
[DISTORTION_RAW] fear=0.8384 trust=-0.9147
[DISTORTION] threat=0.126 trust=0.0 salience=0.0 (governor=ok)
[ECO] tavern_keeper_tornin: wealth_stress=+0.020
[DECISION_HUB] tavern_keeper_tornin: intent=Intent.FLEE score=1.09 event=player_interacts

[STATE_APPLIED] tavern_keeper_tornin: stress=0.2 intent=Intent.FLEE
[REACTION] tavern_keeper_tornin: composure=1.00 hands=False act='' events=[]
[SESSION_RESET] maid_lusya: stress=0 emotion=NEUTRAL mask=NONE
[DISTORTION_RAW] fear=0.8384 trust=-0.9147
[DISTORTION] threat=0.126 trust=0.0 salience=0.0 (governor=ok)
[ECO] maid_lusya: wealth_stress=+0.020
[DECISION_HUB] maid_lusya: intent=Intent.FLEE score=1.142 event=player_interacts

[STATE_APPLIED] maid_lusya: stress=0.2 intent=Intent.FLEE
[REACTION] maid_lusya: composure=1.00 hands=False act='' events=[]
[SESSION_RESET] thief_shadow: stress=0 emotion=NEUTRAL mask=NONE
[DISTORTION_RAW] fear=0.8384 trust=-0.9147
[DISTORTION] threat=0.126 trust=0.0 salience=0.0 (governor=ok)
[ECO] thief_shadow: wealth_stress=+0.020
[DECISION_HUB] thief_shadow: intent=Intent.FLEE score=1.05 event=player_interacts

[STATE_APPLIED] thief_shadow: stress=0.2 intent=Intent.FLEE
[REACTION] thief_shadow: composure=1.00 hands=False act='' events=[]
[PERCEPTION_FILTER] 3/3 NPC: ['maid_lusya', 'tavern_keeper_tornin', 'thief_shadow']
[RULES] action_type=player_interacts → SANDBOX_MILD
[R5] Physical action: success=True result=успех
[PROJECTION] tavern_keeper_tornin: defensive (int=0.33, stab=1.0)
[PROJECTION] maid_lusya: defensive (int=0.33, stab=1.0)
[PROJECTION] thief_shadow: defensive (int=0.33, stab=1.0)
[DELTA] tavern_keeper_tornin: intent=flee stress_d=0.0 trust_d=0.0 fear_d=0.0
[DELTA] maid_lusya: intent=flee stress_d=0.0 trust_d=0.0 fear_d=0.0
[DELTA] thief_shadow: intent=flee stress_d=0.0 trust_d=0.0 fear_d=0.0
[R3_DIRECT] 3 decisions → DMFrame (focus=2, bg=1)
[WM_WRITE] player_action: осматриваюсь
[PLAYER_HEARTBEIT] Campaign: demo-campaign, Player: Демеург
INFO:     127.0.0.1:51460 - "POST /api/player/heartbeat HTTP/1.1" 200 OK
[DM_MEM_SAVED] 348 chars → campaign memory
INFO:     127.0.0.1:61748 - "GET /api/session/state/demo-campaign HTTP/1.1" 200 OK
INFO:     127.0.0.1:61748 - "GET /api/npcs/demo-campaign HTTP/1.1" 200 OK
[PLAYER_HEARTBEIT] Campaign: demo-campaign, Player: Демеург
INFO:     127.0.0.1:61748 - "POST /api/player/heartbeat HTTP/1.1" 200 OK
INFO:     127.0.0.1:61748 - "POST /api/game/action/stream HTTP/1.1" 200 OK
[RECENT_MEM] 3 entries, dm_fields=[True, True, True]
[S.0 MATCH] name_form 'люсе' at pos 10 → maid_lusya
[TARGET] Selected Люся (maid_lusya) from 1 candidates at pos 10
[TARGET] Extracted: Люся (maid_lusya)
[TARGET] No target found in: Подхожу к Люсе и начинаю ее избивать...
[DEBUG SPATIAL] location=tavern_silver_wolf, npc_positions keys=['tavern_keeper_tornin', 'maid_lusya', 'thief_shadow']
[WM_CHECK_START]
[WM_CHECK] campaign=demo-campaign, wm_keys=['demo-campaign']
[RECENT_ACTIONS] ['Демеург: осматриваюсь']
[EVENT_TYPE] Router classified as: player_attacks
[EVENT_BUS] Published: PLAYER_ATTACKED, target=maid_lusya
[DEBUG DM] is_valid=True, scene_context=SceneContext(location_id='tavern_silver_wolf', nearby_npcs=[{'npc_id': 'tavern_keeper_tornin', 'location_id': 'tavern_silver_wolf', 'distance_to_player': 4.0, 'facing_towards_player': True}, {'npc_id': 'maid_lusya', 'location_id': 'tavern_silver_wolf', 'distance_to_player': 2.5, 'facing_towards_player': True}, {'npc_id': 'thief_shadow', 'location_id': 'tavern_silver_wolf', 'distance_to_player': 4.61, 'facing_towards_player': True}], visible_objects={'bar_counter': {'name': 'барная стойка', 'state': 'intact', 'material': 'oak', 'hp': 30, 'max_hp': 30, 'interactable': True}, 'tables_1': {'name': 'столы #1', 'state': 'intact', 'interactable': True, 'instance_of': 'tables'}}, environmental_modifiers={'light': 1.0, 'noise': 0.0, 'density': 0.0, 'danger': 0.0}, line_of_sight={'tavern_keeper_tornin': True, 'maid_lusya': True, 'thief_shadow': True}), error=None
[DISTORTION_RAW] fear=0.8384 trust=-0.9147
[DISTORTION] threat=0.126 trust=0.0 salience=0.0 (governor=ok)
[ECO] tavern_keeper_tornin: wealth_stress=+0.020
[DECISION_HUB] tavern_keeper_tornin: intent=Intent.FLEE score=1.247 event=player_attacks
[CAUSAL] tavern_keeper_tornin: 3 entries (last: fear=3.97 src=player_attacks)
[STATE_APPLIED] tavern_keeper_tornin: stress=18.3 intent=Intent.FLEE
[REACTION] tavern_keeper_tornin: composure=0.82 hands=False act='' events=[]
[PHYSICAL_DBG] npc=maid_lusya target=maid_lusya physical=True max_hp=15
[PHYSICAL] maid_lusya: hp 15→13 (bludgeoning), threats=1, wounds=0, conditions=['stunned']
[DISTORTION_RAW] fear=0.8384 trust=-0.9147
[DISTORTION] threat=0.126 trust=0.0 salience=0.0 (governor=ok)
[ECO] maid_lusya: wealth_stress=+0.020
[DECISION_HUB] maid_lusya: intent=Intent.IDLE score=0.0 event=player_attacks
[CAUSAL] maid_lusya: 4 entries (last: fear=3.97 src=player_attacks)
[STATE_APPLIED] maid_lusya: stress=18.3 intent=Intent.IDLE
[REACTION] maid_lusya: composure=0.82 hands=False act='' events=[]
[DISTORTION_RAW] fear=0.8384 trust=-0.9147
[DISTORTION] threat=0.126 trust=0.0 salience=0.0 (governor=ok)
[ECO] thief_shadow: wealth_stress=+0.020
[DECISION_HUB] thief_shadow: intent=Intent.FLEE score=1.358 event=player_attacks
[CAUSAL] thief_shadow: 3 entries (last: fear=3.97 src=player_attacks)
[STATE_APPLIED] thief_shadow: stress=18.3 intent=Intent.FLEE
[REACTION] thief_shadow: composure=0.82 hands=False act='' events=[]
[PERCEPTION_FILTER] 3/3 NPC (target=maid_lusya): ['maid_lusya', 'tavern_keeper_tornin', 'thief_shadow']
[RULES] action_type=player_attacks → COMBAT
[R5] Physical action: success=True result=успех
[PROJECTION] tavern_keeper_tornin: defensive (int=0.51, stab=1.0)
[PROJECTION] maid_lusya: defensive (int=0.51, stab=1.0)
[PROJECTION] thief_shadow: defensive (int=0.51, stab=1.0)
[DELTA] tavern_keeper_tornin: intent=flee stress_d=17.928 trust_d=-4.9543 fear_d=3.9665
[DELTA] maid_lusya: intent=idle stress_d=17.928 trust_d=-4.9543 fear_d=3.9665
[DELTA] thief_shadow: intent=flee stress_d=17.928 trust_d=-4.9543 fear_d=3.9665
[R3_DIRECT] 3 decisions → DMFrame (focus=2, bg=1)
[WM_WRITE] player_action: Подхожу к Люсе и начинаю ее избивать
[CONTINUITY_DEBUG] tension=0.538 flags={'combat_started'} events=3 emotion={'trust': -0.09, 'tension': 0.32, 'confusion': 0.15}
[CONTINUITY_FINAL]
СОСТОЯНИЕ СЦЕНЫ:
tension: 0.54
flags: combat_started
event: flinched_maid_lusya
event: cry_of_pain_maid_lusya
event: Началась драка
fact: Игрок ударил maid_lusya: 2 урона (bludgeoning), дрогнул(а), вскрикнул(а) от боли

эмоциональный фон: trust=-0.1, tension=+0.3, confusion=+0.1

[/CONTINUITY_FINAL]
[DM_PROMPT_BLOCK]
Ключевые NPC (фокус сцены):
- tavern_keeper_tornin: flee [submit/fearful (urgency=0.2)] (fearful) [defensive, умеренно, стабильно]
- maid_lusya: idle [observe/fearful (urgency=0.1)] (fearful) [defensive, умеренно, стабильно]

Фоновые NPC: thief_shadow

Напряжение: Напряжение растёт быстро — близко к кульминации

Изменения в сцене:
- player_attacks → fearful (важность: 0.77)
[/DM_PROMPT_BLOCK]
[DM_FACTS_INJECTED] 2 items
[PSYCH_ACTIONS] injected 1 actions
[REGIME_BLOCK]
ПСИХОЛОГИЧЕСКИЙ РЕЖИМ NPC (ОБЯЗАТЕЛЬНО учитывай при генерации реплик — это инструкция, не описание):
- tavern_keeper_tornin: режим=defensive, выраженность=51%, стабильность=100%
- maid_lusya: режим=defensive, выраженность=51%, стабильность=100%
Режим определяет тон, длину фраз, уровень агрессии/открытости. НЕ игнорируй.

[/REGIME_BLOCK]
INFO:     127.0.0.1:55587 - "GET /api/health HTTP/1.1" 200 OK
[PLAYER_HEARTBEIT] Campaign: demo-campaign, Player: Демеург
INFO:     127.0.0.1:55587 - "POST /api/player/heartbeat HTTP/1.1" 200 OK
[PLAYER_HEARTBEIT] Campaign: demo-campaign, Player: Демеург
INFO:     127.0.0.1:62043 - "POST /api/player/heartbeat HTTP/1.1" 200 OK
[DM_MEM_SAVED] 282 chars → campaign memory
INFO:     127.0.0.1:61748 - "GET /api/session/state/demo-campaign HTTP/1.1" 200 OK
INFO:     127.0.0.1:61748 - "GET /api/npcs/demo-campaign HTTP/1.1" 200 OK
[PLAYER_HEARTBEIT] Campaign: demo-campaign, Player: Демеург
INFO:     127.0.0.1:60016 - "POST /api/player/heartbeat HTTP/1.1" 200 OK
INFO:     127.0.0.1:57266 - "GET /api/health HTTP/1.1" 200 OK
INFO:     127.0.0.1:54885 - "GET /api/debug/vram HTTP/1.1" 200 OK
[PLAYER_HEARTBEIT] Campaign: demo-campaign, Player: Демеург
INFO:     127.0.0.1:54885 - "POST /api/player/heartbeat HTTP/1.1" 200 OK
[PLAYER_HEARTBEIT] Campaign: demo-campaign, Player: Демеург
INFO:     127.0.0.1:52950 - "POST /api/player/heartbeat HTTP/1.1" 200 OK
INFO:     127.0.0.1:59020 - "POST /api/game/action/stream HTTP/1.1" 200 OK
[RECENT_MEM] 3 entries, dm_fields=[True, True, True]
[LIFE_ENGINE] 16 изменений применено
[S.0 MATCH] name_form 'торнин' at pos 0 → tavern_keeper_tornin
[TARGET] Selected Торнин Серебряная Луна (tavern_keeper_tornin) from 1 candidates at pos 0
[TARGET] Extracted: Торнин Серебряная Луна (tavern_keeper_tornin)
[SPATIAL] 1 transitions: [('thief_shadow', 'proximity_leave')]
[TARGET] No target found in: Торнин, у всех всё хорошо?...
[DEBUG SPATIAL] location=tavern_silver_wolf, npc_positions keys=['tavern_keeper_tornin', 'maid_lusya', 'thief_shadow', 'guard_borko', 'merchant_goran']
[WM_CHECK_START]
[WM_CHECK] campaign=demo-campaign, wm_keys=['demo-campaign', 'demo-campaign:tavern_keeper_tornin', 'demo-campaign:maid_lusya', 'demo-campaign:thief_shadow']
[RECENT_ACTIONS] ['Демеург: осматриваюсь', 'Демеург: Подхожу к Люсе и начинаю ее избивать']
[EVENT_TYPE] Router classified as: player_interacts
[EVENT_BUS] Published: PLAYER_SPOKE, target=tavern_keeper_tornin
[DEBUG DM] is_valid=True, scene_context=SceneContext(location_id='tavern_silver_wolf', nearby_npcs=[{'npc_id': 'tavern_keeper_tornin', 'location_id': 'tavern_silver_wolf', 'distance_to_player': 4.0, 'facing_towards_player': True}, {'npc_id': 'maid_lusya', 'location_id': 'tavern_silver_wolf', 'distance_to_player': 2.5, 'facing_towards_player': True}, {'npc_id': 'thief_shadow', 'location_id': 'tavern_silver_wolf', 'distance_to_player': 5.0, 'facing_towards_player': True}, {'npc_id': 'guard_borko', 'location_id': 'tavern_silver_wolf', 'distance_to_player': 5.0, 'facing_towards_player': True}, {'npc_id': 'merchant_goran', 'location_id': 'tavern_silver_wolf', 'distance_to_player': 5.0, 'facing_towards_player': True}], visible_objects={'bar_counter': {'name': 'барная стойка', 'state': 'intact', 'material': 'oak', 'hp': 30, 'max_hp': 30, 'interactable': True}, 'tables_1': {'name': 'столы #1', 'state': 'intact', 'interactable': True, 'instance_of': 'tables'}, 'tables_2': {'name': 'столы #2', 'state': 'intact', 'interactable': True, 'instance_of': 'tables'}, 'tables_3': {'name': 'столы #3', 'state': 'intact', 'interactable': True, 'instance_of': 'tables'}, 'tables_4': {'name': 'столы #4', 'state': 'intact', 'interactable': True, 'instance_of': 'tables'}}, environmental_modifiers={'light': 1.0, 'noise': 0.0, 'density': 0.0, 'danger': 0.0}, line_of_sight={'tavern_keeper_tornin': True, 'maid_lusya': True, 'thief_shadow': True, 'guard_borko': True, 'merchant_goran': True}), error=None
[PHYSICAL_DBG] npc=tavern_keeper_tornin target=tavern_keeper_tornin physical=False max_hp=40
[DISTORTION_RAW] fear=0.8448 trust=-0.9189
[DISTORTION] threat=0.127 trust=0.0 salience=0.0 (governor=ok)
[ECO] tavern_keeper_tornin: wealth_stress=+0.020
[DECISION_HUB] tavern_keeper_tornin: intent=Intent.FLEE score=1.508 event=player_interacts

[STATE_APPLIED] tavern_keeper_tornin: stress=18.5 intent=Intent.FLEE
[REACTION] tavern_keeper_tornin: composure=0.82 hands=False act='' events=[]
[DISTORTION_RAW] fear=0.8448 trust=-0.9189
[DISTORTION] threat=0.127 trust=0.0 salience=0.0 (governor=ok)
[ECO] maid_lusya: wealth_stress=+0.020
[DECISION_HUB] maid_lusya: intent=Intent.FLEE score=1.532 event=player_interacts

[STATE_APPLIED] maid_lusya: stress=18.5 intent=Intent.FLEE
[REACTION] maid_lusya: composure=0.82 hands=False act='' events=[]
[DISTORTION_RAW] fear=0.8448 trust=-0.9189
[DISTORTION] threat=0.127 trust=0.0 salience=0.0 (governor=ok)
[ECO] thief_shadow: wealth_stress=+0.020
[DECISION_HUB] thief_shadow: intent=Intent.FLEE score=1.513 event=player_interacts

[STATE_APPLIED] thief_shadow: stress=18.5 intent=Intent.FLEE
[REACTION] thief_shadow: composure=0.82 hands=False act='' events=[]
[DISTORTION_RAW] fear=0.3240 trust=-0.4755
[DISTORTION] threat=0.049 trust=0.0 salience=0.0 (governor=ok)
[ECO] guard_borko: wealth_stress=+0.020
[DECISION_HUB] guard_borko: intent=Intent.FLEE score=0.607 event=player_interacts

[STATE_APPLIED] guard_borko: stress=0.2 intent=Intent.FLEE
[REACTION] guard_borko: composure=1.00 hands=False act='' events=[]
[DISTORTION_RAW] fear=0.3240 trust=-0.4755
[DISTORTION] threat=0.049 trust=0.0 salience=0.0 (governor=ok)
[ECO] merchant_goran: wealth_stress=+0.020
[DECISION_HUB] merchant_goran: intent=Intent.FLEE score=0.528 event=player_interacts

[STATE_APPLIED] merchant_goran: stress=0.2 intent=Intent.FLEE
[REACTION] merchant_goran: composure=1.00 hands=False act='' events=[]
[PERCEPTION_SKIP] thief_shadow: dist=5.0m (not visible)
[PERCEPTION_FILTER] 4/5 NPC (target=tavern_keeper_tornin): ['maid_lusya', 'tavern_keeper_tornin', 'merchant_goran', 'guard_borko']
[RULES] action_type=player_interacts → SANDBOX_MILD
[R5] Physical action: success=False result=провал
[PROJECTION] tavern_keeper_tornin: defensive (int=0.51, stab=1.0)
[PROJECTION] maid_lusya: defensive (int=0.51, stab=1.0)
[PROJECTION] guard_borko: defensive (int=0.39, stab=1.0)
[PROJECTION] merchant_goran: defensive (int=0.39, stab=1.0)
[DELTA] tavern_keeper_tornin: intent=flee stress_d=0.0 trust_d=0.0 fear_d=0.0
[DELTA] maid_lusya: intent=flee stress_d=0.0 trust_d=0.0 fear_d=0.0
[DELTA] guard_borko: intent=flee stress_d=0.0 trust_d=0.0 fear_d=0.0
[DELTA] merchant_goran: intent=flee stress_d=0.0 trust_d=0.0 fear_d=0.0
[R3_DIRECT] 4 decisions → DMFrame (focus=2, bg=2)
[WM_WRITE] player_action: Торнин, у всех всё хорошо?
[CONTINUITY_DEBUG] tension=0.538 flags={'proximity_leave_thief_shadow', 'combat_started'} events=4 emotion={'trust': -0.06, 'tension': 0.22, 'confusion': 0.2}
[CONTINUITY_FINAL]
СОСТОЯНИЕ СЦЕНЫ:
tension: 0.54
flags: combat_started, proximity_leave_thief_shadow
event: flinched_maid_lusya
event: cry_of_pain_maid_lusya
event: Началась драка
event: Игрок отошёл от thief_shadow
fact: Игрок ударил maid_lusya: 2 урона (bludgeoning), дрогнул(а), вскрикнул(а) от боли

эмоциональный фон: trust=-0.1, tension=+0.2, confusion=+0.2

[/CONTINUITY_FINAL]
[DM_PROMPT_BLOCK]
Ключевые NPC (фокус сцены):
- tavern_keeper_tornin: flee [submit/fearful (urgency=0.2)] (neutral) [defensive, умеренно, стабильно]
- maid_lusya: flee [submit/fearful (urgency=0.2)] (neutral) [defensive, умеренно, стабильно]

Фоновые NPC: guard_borko, merchant_goran
[/DM_PROMPT_BLOCK]
[DM_FACTS_INJECTED] 2 items
[PSYCH_ACTIONS] injected 2 actions
[REGIME_BLOCK]
ПСИХОЛОГИЧЕСКИЙ РЕЖИМ NPC (ОБЯЗАТЕЛЬНО учитывай при генерации реплик — это инструкция, не описание):
- tavern_keeper_tornin: режим=defensive, выраженность=51%, стабильность=100%
- maid_lusya: режим=defensive, выраженность=51%, стабильность=100%
Режим определяет тон, длину фраз, уровень агрессии/открытости. НЕ игнорируй.

[/REGIME_BLOCK]
[PLAYER_HEARTBEIT] Campaign: demo-campaign, Player: Демеург
INFO:     127.0.0.1:65245 - "POST /api/player/heartbeat HTTP/1.1" 200 OK
INFO:     127.0.0.1:50331 - "GET /api/health HTTP/1.1" 200 OK
[PLAYER_HEARTBEIT] Campaign: demo-campaign, Player: Демеург
INFO:     127.0.0.1:50331 - "POST /api/player/heartbeat HTTP/1.1" 200 OK
[DM_MEM_SAVED] 292 chars → campaign memory
INFO:     127.0.0.1:59020 - "GET /api/session/state/demo-campaign HTTP/1.1" 200 OK
INFO:     127.0.0.1:59020 - "GET /api/npcs/demo-campaign HTTP/1.1" 200 OK
[PLAYER_HEARTBEIT] Campaign: demo-campaign, Player: Демеург
INFO:     127.0.0.1:49182 - "POST /api/player/heartbeat HTTP/1.1" 200 OK
[PLAYER_HEARTBEIT] Campaign: demo-campaign, Player: Демеург
INFO:     127.0.0.1:51817 - "POST /api/player/heartbeat HTTP/1.1" 200 OK
INFO:     127.0.0.1:51377 - "GET /api/debug/vram HTTP/1.1" 200 OK
INFO:     127.0.0.1:56586 - "GET /api/health HTTP/1.1" 200 OK
[PLAYER_HEARTBEIT] Campaign: demo-campaign, Player: Демеург
INFO:     127.0.0.1:56586 - "POST /api/player/heartbeat HTTP/1.1" 200 OK
[PLAYER_HEARTBEIT] Campaign: demo-campaign, Player: Демеург
INFO:     127.0.0.1:51966 - "POST /api/player/heartbeat HTTP/1.1" 200 OK
INFO:     127.0.0.1:51966 - "POST /api/game/action/stream HTTP/1.1" 200 OK
[RECENT_MEM] 3 entries, dm_fields=[True, True, True]
[LIFE_ENGINE] 1 изменений применено
[TARGET] No target found in: Что прекратить?...
[DEBUG SPATIAL] location=tavern_silver_wolf, npc_positions keys=['tavern_keeper_tornin', 'maid_lusya', 'thief_shadow', 'guard_borko', 'merchant_goran']
[WM_CHECK_START]
[WM_CHECK] campaign=demo-campaign, wm_keys=['demo-campaign', 'demo-campaign:tavern_keeper_tornin', 'demo-campaign:maid_lusya', 'demo-campaign:thief_shadow']
[RECENT_ACTIONS] ['Демеург: осматриваюсь', 'Демеург: Подхожу к Люсе и начинаю ее избивать', 'Демеург: Торнин, у всех всё хорошо?']
[EVENT_TYPE] Router classified as: player_interacts
[EVENT_BUS] Published: PLAYER_SPOKE, target=None
[DEBUG DM] is_valid=True, scene_context=SceneContext(location_id='tavern_silver_wolf', nearby_npcs=[{'npc_id': 'tavern_keeper_tornin', 'location_id': 'tavern_silver_wolf', 'distance_to_player': 4.0, 'facing_towards_player': True}, {'npc_id': 'maid_lusya', 'location_id': 'tavern_silver_wolf', 'distance_to_player': 2.5, 'facing_towards_player': True}, {'npc_id': 'thief_shadow', 'location_id': 'tavern_silver_wolf', 'distance_to_player': 5.0, 'facing_towards_player': True}, {'npc_id': 'guard_borko', 'location_id': 'tavern_silver_wolf', 'distance_to_player': 5.0, 'facing_towards_player': True}, {'npc_id': 'merchant_goran', 'location_id': 'tavern_silver_wolf', 'distance_to_player': 5.0, 'facing_towards_player': True}], visible_objects={'bar_counter': {'name': 'барная стойка', 'state': 'intact', 'material': 'oak', 'hp': 30, 'max_hp': 30, 'interactable': True}, 'tables_1': {'name': 'столы #1', 'state': 'intact', 'interactable': True, 'instance_of': 'tables'}, 'tables_2': {'name': 'столы #2', 'state': 'intact', 'interactable': True, 'instance_of': 'tables'}, 'tables_3': {'name': 'столы #3', 'state': 'intact', 'interactable': True, 'instance_of': 'tables'}, 'tables_4': {'name': 'столы #4', 'state': 'intact', 'interactable': True, 'instance_of': 'tables'}}, environmental_modifiers={'light': 1.0, 'noise': 0.0, 'density': 0.0, 'danger': 0.0}, line_of_sight={'tavern_keeper_tornin': True, 'maid_lusya': True, 'thief_shadow': True, 'guard_borko': True, 'merchant_goran': True}), error=None
[DISTORTION_RAW] fear=0.8448 trust=-0.9189
[DISTORTION] threat=0.127 trust=0.0 salience=0.0 (governor=ok)
[ECO] tavern_keeper_tornin: wealth_stress=+0.020
[DECISION_HUB] tavern_keeper_tornin: intent=Intent.FLEE score=1.495 event=player_interacts

[STATE_APPLIED] tavern_keeper_tornin: stress=18.7 intent=Intent.FLEE
[REACTION] tavern_keeper_tornin: composure=0.81 hands=False act='' events=[]
[DISTORTION_RAW] fear=0.8448 trust=-0.9189
[DISTORTION] threat=0.127 trust=0.0 salience=0.0 (governor=ok)
[ECO] maid_lusya: wealth_stress=+0.020
[DECISION_HUB] maid_lusya: intent=Intent.FLEE score=1.546 event=player_interacts

[STATE_APPLIED] maid_lusya: stress=18.7 intent=Intent.FLEE
[REACTION] maid_lusya: composure=0.81 hands=False act='' events=[]
[DISTORTION_RAW] fear=0.8448 trust=-0.9189
[DISTORTION] threat=0.127 trust=0.0 salience=0.0 (governor=ok)
[ECO] thief_shadow: wealth_stress=+0.020
[DECISION_HUB] thief_shadow: intent=Intent.FLEE score=1.556 event=player_interacts

[STATE_APPLIED] thief_shadow: stress=18.7 intent=Intent.FLEE
[REACTION] thief_shadow: composure=0.81 hands=False act='' events=[]
[DISTORTION_RAW] fear=0.3240 trust=-0.4755
[DISTORTION] threat=0.049 trust=0.0 salience=0.0 (governor=ok)
[ECO] guard_borko: wealth_stress=+0.020
[DECISION_HUB] guard_borko: intent=Intent.FLEE score=0.605 event=player_interacts

[STATE_APPLIED] guard_borko: stress=0.4 intent=Intent.FLEE
[REACTION] guard_borko: composure=1.00 hands=False act='' events=[]
[DISTORTION_RAW] fear=0.3240 trust=-0.4755
[DISTORTION] threat=0.049 trust=0.0 salience=0.0 (governor=ok)
[ECO] merchant_goran: wealth_stress=+0.020
[DECISION_HUB] merchant_goran: intent=Intent.FLEE score=0.619 event=player_interacts

[STATE_APPLIED] merchant_goran: stress=0.4 intent=Intent.FLEE
[REACTION] merchant_goran: composure=1.00 hands=False act='' events=[]
[PERCEPTION_SKIP] thief_shadow: dist=5.0m (not visible)
[PERCEPTION_FILTER] 4/5 NPC: ['maid_lusya', 'tavern_keeper_tornin', 'merchant_goran', 'guard_borko']
[RULES] action_type=player_interacts → SANDBOX_MILD
[R5] Physical action: success=True result=успех
[PROJECTION] tavern_keeper_tornin: defensive (int=0.51, stab=1.0)
[PROJECTION] maid_lusya: defensive (int=0.51, stab=1.0)
[PROJECTION] guard_borko: defensive (int=0.39, stab=1.0)
[PROJECTION] merchant_goran: defensive (int=0.39, stab=1.0)
[DELTA] tavern_keeper_tornin: intent=flee stress_d=0.0 trust_d=0.0 fear_d=0.0
[DELTA] maid_lusya: intent=flee stress_d=0.0 trust_d=0.0 fear_d=0.0
[DELTA] guard_borko: intent=flee stress_d=0.0 trust_d=0.0 fear_d=0.0
[DELTA] merchant_goran: intent=flee stress_d=0.0 trust_d=0.0 fear_d=0.0
[R3_DIRECT] 4 decisions → DMFrame (focus=2, bg=2)
[WM_WRITE] player_action: Что прекратить?
[CONTINUITY_DEBUG] tension=0.538 flags={'proximity_leave_thief_shadow', 'combat_started'} events=4 emotion={'trust': -0.04, 'tension': 0.15, 'confusion': 0.23}
[CONTINUITY_FINAL]
СОСТОЯНИЕ СЦЕНЫ:
tension: 0.54
flags: combat_started, proximity_leave_thief_shadow
event: flinched_maid_lusya
event: cry_of_pain_maid_lusya
event: Началась драка
event: Игрок отошёл от thief_shadow
fact: Игрок ударил maid_lusya: 2 урона (bludgeoning), дрогнул(а), вскрикнул(а) от боли

эмоциональный фон: tension=+0.1, confusion=+0.2

[/CONTINUITY_FINAL]
[DM_PROMPT_BLOCK]
Ключевые NPC (фокус сцены):
- tavern_keeper_tornin: flee [submit/fearful (urgency=0.2)] (neutral) [defensive, умеренно, стабильно]
- maid_lusya: flee [submit/fearful (urgency=0.2)] (neutral) [defensive, умеренно, стабильно]

Фоновые NPC: guard_borko, merchant_goran
[/DM_PROMPT_BLOCK]
[DM_FACTS_INJECTED] 2 items
[PSYCH_ACTIONS] injected 3 actions
[REGIME_BLOCK]
ПСИХОЛОГИЧЕСКИЙ РЕЖИМ NPC (ОБЯЗАТЕЛЬНО учитывай при генерации реплик — это инструкция, не описание):
- tavern_keeper_tornin: режим=defensive, выраженность=51%, стабильность=100%
- maid_lusya: режим=defensive, выраженность=51%, стабильность=100%
Режим определяет тон, длину фраз, уровень агрессии/открытости. НЕ игнорируй.

[/REGIME_BLOCK]
[PLAYER_HEARTBEIT] Campaign: demo-campaign, Player: Демеург
INFO:     127.0.0.1:62589 - "POST /api/player/heartbeat HTTP/1.1" 200 OK
INFO:     127.0.0.1:55081 - "GET /api/health HTTP/1.1" 200 OK


Критическая точка
Самое важное место всей архитектуры:
НЕ DecisionHub
НЕ LLM
А:
→ SceneEvent → Perception → Distribution
Если это слабое — вся система фейковая.

Почему сейчас поведение выглядит “тупым”

Сценарий:

Ты орёшь → NPC A реагирует
Ты спрашиваешь NPC B → он “чистый”

Почему:

1. Событие не записано как shared
2. NPC B не получил perception
3. NPC B не обновил state
4. DM не получил контекст
5. Что должно быть (ядро системы)

Тебе не нужна «память NPC».

Тебе нужен:

👉 SCENE EVENT LAYER
Event:
  type: "violence"
  actor: player
  target: lusya
  intensity: 0.8
  visibility_radius: 5m
  timestamp: tick
6. Правильный поток
PhysicalOutcome
    ↓
ReflexResolver (локально)
    ↓
StateApplicator (target NPC)
    ↓
SceneEventEmitter  ← НОВОЕ
    ↓
SceneEventLog (shared)
    ↓
PerceptionFilter (для КАЖДОГО NPC)
    ↓
DecisionHub
7. Что это меняет
Было:
NPC реагирует на player_action
Станет:
NPC реагирует на МИР
8. Пример (твой кейс)
Сейчас:
Ты ударил Люсю

Люся:
  stress=18 → реакция

Торнин:
  видит только event_type
  → слабая реакция

Другие:
  могут вообще не увидеть
После фикса:
SceneEvent:
  "player ударил Люсю"
  intensity=0.9
  visible_radius=5m

Perception:

Люся (distance 2m):
  perception=1.0 → panic

Торнин (4m):
  perception=0.8 → fear + flee

Стражник (5m):
  perception=0.6 → investigate / attack

Пьяный воин (traits: fearless):
  perception=0.5 → ignore
9. Память — теперь становится тривиальной

После этого:

if perception_strength > 0.5:
    memory.add(event, importance)
10. Почему твой текущий подход не взлетит

Ты пытаешься:

улучшить LLM
добавить флаги
подкрутить intent

Но у тебя нет:

общей причинности между NPC

Это как пытаться обучить актёров играть сцену,
не сказав им, что произошло на сцене.

[DM_FACTS_INJECTED] 1 items — работает. Флаг "В сцене идёт бой" доходит до DM.

Сравни прогресс:

Проблема
Было
Стало
Удар опубликован как речь	PLAYER_SPOKE	PLAYER_ATTACKED ✓
Свидетелей выкидывали	1/3 NPC	3/3 NPC ✓
Торнин на тике 2 забывал удар	score=0.82 "чистый"	score=1.37 через risk×fear ✓
DM не знал о бое	"Она обслуживает гостей"	"Полиция! Сейчас же!" ✓

Осталось две отдельные задачи:

Физический блок нестабилен — [PHYSICAL_DBG] есть, [PHYSICAL] maid_lusya: hp 15→14 пропадает. Факт об уроне не создаётся. Это баг в physical resolver — отдельное расследование.
Память NPC с контекстом — create_event_memory() мёртвый код. Нужно оживить чтобы "спасение в детстве" запоминалось с текстом. Это большая задача из твоего документа.

Инфраструктура мощная — но сломана в трёх местах. Диагноз:

EventMemory — есть decay, stages, clarity — но нет поля summary (текст "игрок избил Люсю")
create_event_memory() — правильно считает importance — но никогда не вызывается
record_event() — вызывается — но пишет бедный dict без NPC-specific данных
WorkingMemory — RAM только, сбрасывается при перезапуске
npc_memory_{campaign}.jsonl — общий на всех NPC, не разделён


DecisionHub читает только числа, не текст. Вот что он видит:

text

rel = state.relationship_cache  # trust=−4.96, fear=18.3, recent_pressure=0.85
Вот что он НЕ видит:

"Демеург: Торнин, ты не знаешь что случилось с Люсей?"
"Торнин: Что здесь происходит?"
"Демеург: Торнин, как пройти в библиотеку?"
NPC принимает решение как будто каждый вопрос — первый в его жизни. Он не знает что уже спрашивали это.

Но мы уже создали инфраструктуру. narrative_cache есть в NPCState:

python

narrative_cache: Tuple[Union[NarrativeFact, "EventMemory"], ...]
DecisionHub получает state: NPCStateL2 — но _score_components читает только state.relationship_cache.

Следующий шаг: подключить narrative_cache к DecisionHub. Минимально — передать summaries в EventContext и модифицировать scorы когда текущее действие похоже на прошлые.

Сделать это сейчас? Или сначала починим что DM видит физическое состояние NPC (hp, stunned, wounds)?


DecisionHub — не помнит что NPC уже ответил на похожий вопрос
DM prompt — не видит что NPC уже говорил


Нужно чтобы:

Тик 3 (Торнин, что случилось с Люсей?):

DecisionHub: NPC помнит насилие → risk_penalty += 0.15 → меньше болтает
DM видит: "Недавние реакции NPC: - Торнин: Я не знаю, что здесь происходит\n- Люся: П-пожалуйста, не надо..."
Тик 4 (как пройти в библиотеку?):

DecisionHub: NPC помнит насилие, но 3+ тика назад → decay снизил importance → risk почти 0 → отвечает нормально
DM видит прошлую речь NPC → не пишет "я не знаю" из пустого

Нет [PSYCH_DEBUG] — значит _build_dm_prompt не вызывается для R3 Direct. Ищу где формируется промпт в стриме:
Теперь вижу - есть два вызова _build_prompt. Нужно посмотреть где вызывается для R3 Direct (строка 697) и посмотреть передаётся ли context

Теперь вижу корень проблемы. В R3 Direct:

npc_reactions = [] (пусто — DM генерирует сам)
Строка 1440: цикл по пустому списку → ничего не записывается в Working Memory
DM получает recent_memory из Working Memory → пустой
DM не знает что NPC уже говорили в прошлых ходах
Вижу: recent_memory берётся из layered_memory.read_campaign_memory() — поле dm. Нужно проверить, сохраняется ли DM-ответ (включая NPC речь из R3) обратно в layered_memory:

Нашёл критический баг. В REST-пути (строка 289) write_campaign_memory вызывается с DM-ответом. В SSE-пути (stream_turn) — отсутствует. DM-ответ никогда не сохраняется, поэтому recent_memory всегда пустой.

КРИТИЧЕСКИЙ БАГ НАЙДЕН

write_to_legacy() (строка 481) — НЕ сохраняет narrative_cache в JSON. Значит:

Тик N: create_event_memory() кладёт в narrative_cache
Тик N: write_to_legacy() — narrative_cache не записан
Тик N+1: NPC загружается из JSON → narrative_cache = пустой кортеж

ПОЛНАЯ КАРТИНА УТЕЧКИ ПАМЯТИ:

load_l2_state_from_runtime_dict() (строка 359) — НЕ читает narrative_cache
write_to_legacy() (строка 481) — НЕ пишет narrative_cache
R3 Direct: npc_reactions = [] → _write_npc_memory ничего не пишет
Результат: каждый тик narrative_cache = пустой кортеж. Память NPC — иллюзия.

Нужно проверить структуру NPCStateL2:
NPCStateL2 = алиас для NPCState. Значит narrative_cache есть в структуре, но не проходит сериализацию.

ДИАГНОЗ ЗАВЕРШЁН

narrative_cache существует в NPCState, но:

write_to_legacy() — не пишет
load_l2_state_from_runtime_dict() — не читает
Память NPC создана каждый тик и сбрасывается при сохранении. Это "дырявой бублик".
WorkingMemory.apply_decay() затухает RAM-буферы. Но narrative_cache в NPCState — отдельная копия, которая никогда не вызывает decayed().

Результат: narrative_cache копится с первоначальным importance, события не переходят FRESH→FORGOTTEN.

Нужно применить decay к narrative_cache при загрузке NPC.
Вижу: load_l2_state_from_runtime_dict() не получает current_tick. Но это не баг, а фича — если NPC не в сцене, его память не затухает (время для него стоит). При загрузке (раз в тик) применяем decay=1.

ИТОГ ИСПРАВЛЕНИЙ:

Проблема
Было
Стало
DM забывает за 1 тик	SSE не сохранял ответ	write_campaign_memory() после стрима
narrative_cache дырявый	Не сериализовался	write_to_legacy() + load_l2_state_from_runtime_dict()
Забывание не работает	decayed() никогда не вызывался	Decay при загрузке + удаление FORGOTTEN

Система страдает от двух архитектурных дефектов, которые лишают LLM памяти:

Конкуренция в deque(maxlen=20): Реплики NPC (dict) лежат в общем буфере вместе с боевыми событиями (EventMemory). При активной сцене за 3-5 тиков реплики вытесняются новым мусором и навсегда удаляются.
O(N) перебор на чтение: На строке 626 game_loop перебирает весь буфер, фильтруя по type == "npc_speech", что неэффективно.
Решение: Изолировать реплики NPC в отдельный именованный буфер campaign_id:dialogue внутри WorkingMemory. Механика deque сохранится, но теперь лимит в 20 элементов будет относиться только к репликам, а не ко всей кампании. Медленный фильтр уйдёт.