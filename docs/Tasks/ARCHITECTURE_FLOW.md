flowchart TD
%% === ADR-0015: IMMUTABLE SNAPSHOT FEED (Temporal Isolation) ===
SNAP_T[world_snapshot t IMMUTABLE ADR-0015] -->|Read-Only Feed| P0
SNAP_T -->|Read-Only Feed| P3
SNAP_T -->|Read-Only Feed| P5
SNAP_T -->|Read-Only Feed| PER

subgraph Spatial_Layer[Spatial Service v1.2: Единый источник пространственных данных]
LOC_DATA[location_templates.json / editor JSON] -->|positions + connections ADR-060| GC[GraphCompiler compile_graph]
GC -->|graph, connections, alias_map| SS[SpatialService]
SC_T[SceneState t-1] -->|build_overlay| SS
SS -->|DI: set_spatial_service| ME[MovementEngine]
SS -->|get_node with prefix fallback ADR-0009| SSM[SceneStateManager Spatial Reducer ADR-0015]
SSM -->|current_tick >= started_tick + duration_ticks| SSM_FINAL[_enrich_local_positions Finalize Traversals & Set local_position ADR-059]
SSM_FINAL -->|Immutable Source| WSB_IMMUT[WorldSnapshotBuilder Pure Projection]
SS -->|build_cluster_graph ADR-0029| CG[ClusterGraph]
end

subgraph Phase_0_2[Фазы 0-2: Input and Simulation]
P0[Phase 0: LifeEngine ADR-056 Attention Capture] -->|check recent_directive.interrupts_routine| P0_SKIP[SCHEDULE_BYPASSED Routine Freeze]
P0 -->|scene_changes| P05
P0 -->|scene_changes| P2
P0 -->|life_intents ADR-051| ME
P0 -->|ctx.npc_states = ctx.all_npcs_raw| SA_SYNC[State Sync ADR-004]
P05[Phase 0.5: Idle Services ALWAYS] -->|List StateDeltas| DBUF[delta_buffer]
PI[Player Input] -->|Raw Text| IC[IntentCompressor pymorphy3 Fast Path + LLM Slow Path ADR-035]
IC[IntentCompressor pymorphy3 Fast Path + LLM Slow Path ADR-035] -->|IntentSemanticField| TR[Target Reference Resolver String to ID ADR-060 Fuzzy Matching]
SC_T[SceneState t-1] -.->|npc_positions with name| TR
TR -->|IntentParametersDTO strict payload ADR-035| IPR[IntentPressureResolver Semantic Translation ADR-031]
IPR -->|IntentPressureProfile| WPG[WillpowerGate Cumulative Strain Model + EmbodiedVector ADR-040]
WPG -->|WillResponseDTO origin_layer + embodied_vector| P1[Phase 1: Input]
P1 -->|EventDTO or WILL_CONFLICT| P2[Phase 2: EventBus]
P2 -->|attach_cfrm_buffer + classify_event -> ClassificationResult ADR-038| EB[EventBuffer CausalAxis]
SS -.->|DI: set_spatial_service| P0
ME -->|find_path canonical IDs| TT[TransitTracker]
TT -->|advance_all SceneChange| P0
TA[advance_game_time Player Action] -->|TemporalEvent game_time_seconds + delta ADR-0015| DBUF2[Event Buffer Aggregator ADR-0015]
end

subgraph Phase_0_5_Detail[Фаза 0.5: Time-driven decay]
SNAP[_build_npc_snapshots social_stats + body mapping + statuses ADR-0010] --> SDH[SocialDecayHandler closing drift]
SNAP --> RDH[ReputationDecayHandler]
RDH -->|calls| RE[ReputationEngine.compute_decay pure]
SDH -->|StateDeltas domainSOCIAL payloadSocialPayload| DBUF2
RDH -->|StateDeltas domainREPUTATION payloadReputationPayload| DBUF2
ADV[_advance_idle_time +GAME_TICK_INTERVAL_SECONDS] -->|TemporalEvent game_time_seconds + time_of_day ADR-0015| DBUF2
SNAP --> PDS[PhysiologyDecayHandler leaky integrator ADR-0013]
PDS -->|StateDeltas domainPHYSIOLOGY payloadPhysiologyPayload pain fatigue blood_loss stagger unconscious| DBUF2
end

subgraph NPC_Loading[NPC Loading Pipeline]
NPS[config/npc/individuals/*.json + body_profile ADR-0017] -->|load_archetype_chain| MERG[static NPC dicts]
MERG -->|+ runtime overlay| RUNTIME[npc_runtime.json]
RUNTIME --> ENRICH[_enrich_with_social_relations village_relations.json]
ENRICH -->|relationship_cache NPC-to-NPC + base_values| BODY_INIT[_init_body_state body_profile + body_state ADR-0010]
BODY_INIT --> LOADED[Loaded NPC dicts with body_state]
VR[config/npc/social/village_relations.json] -->|load_social_base| ENRICH
PCHAR[CharacterService Player Avatar ADR-030] -->|inject npc_id=player vector| LOADED
end

LOADED -.->|all_npcs_raw| SNAP

subgraph Phase_3_7[Фазы 3-7: Memory and Decision]
P2 -->|EventDTO| P3[Phase 3: MemoryProcessor]
P3 -->|Updated NPCState| P4[Phase 4: TopicExtractor]
P4 -->|Topic| P5[Phase 5: DecisionHub v2 ADR-032 ADR-049]
PKERN[NPCState.perceptual_kernel T-1] -.->|translate_kernel_to_context ADR-049| DCTX[DecisionContext ADR-049]
PRESSURE[PsychologicalPressure] -.->|translate_pressure_to_context| DCTX
DCTX -->|decision_ctx T+1 Cognitive Discretization| P5
P5 -->|CommunicationIntent| P6[Phase 6: IntentEventAdapter]
P5 -->|List StateDeltas v2 domain-tagged| LDA[LegacyStateDeltaAdapter v2-v1 Collapse ADR-032]
P6 -->|EventDTO| P7[Phase 7: EventBus Secondary]
end

subgraph Reactive_Movement[Реактивное движение: LOD1 Macro & LOD0 Micro ADR-052]
P5 -->|approach/flee intent| RRM[_resolve_reactive_movement]
RRM -->|Macro: different zone| MI[MovementIntent LOD1 target_node_id]
RRM -->|Micro: same zone base match ADR-052| MI_L0[MovementIntent LOD0 local_target_xy]
MI --> ME[MovementEngine]
MI_L0 --> ME
ME -->|LOD0: local_target_xy set| SPATIAL_BUF[SceneChange field=local_position + jitter ADR-0015]
ME -->|LOD1: from_node != target_node| SPATIAL_BUF2[SceneChange field=position ADR-0015]
ME -->|LOD1: from_node == target_node & no local_xy| SKIP[Guard: preserve micro-position ADR-0012]
end

subgraph Physiology_Layer[Physiology Domain: Impact Propagation Engine ADR-0010]
IE[ImpactEngine Pure Function] -->|Contact Resolution| CL[ContactLevel MISS GLANCING SOLID PERFECT]
CL -->|Energy Transfer| PP[PhysiologyPayload hp pain blood_loss shock_impulse]
PP --> DBUF_P[delta_buffer]
end

subgraph Phase_8[Фаза 8: Layered Reduction ADR-0016]
P7 -.->|cfrm_bridge capture| EB
P2 -.->|cfrm_bridge capture| EB

LAYER_SEP{Layer Separator}

LAYER_SEP -->|1. Physical Layer| CSUB[CombatSubscriber ADR-0012 Fuzzy Target Resolve]
P7 -->|drain_events| CSUB
P2 -->|drain_events| CSUB

CSUB -->|extract ImpactIntentDTO| IE
IE -->|List StateDeltas PHYSIOLOGY| CSUB
CSUB -->|Phase8Result deltas| MAT[Materialization Tuple StateDeltas ADR-0016]

MAT -->|ctx.physical_deltas_materialized| RXT[reaction_subscriber.ReactionSubscriber ADR-0016]
P7 -->|drain_events| RXT
P2 -->|drain_events| RXT

MAT -->|physical_deltas_materialized| SOC[social_subscriber.SocialSubscriber]
P7 -->|drain_events| SOC
P2 -->|drain_events| SOC

PROP[propagate_social_rumors pure function v2 EMOTION+SOCIAL split]
RXTMOD[_compute_reaction_modifier composure x fear_drive x willpower]
RXT -->|reads shock_impulse from ctx.physical_deltas_materialized| SHOCK_CASCADE[Cascade: Force → Pain → Shock → Emotion ADR-0016]
SHOCK_CASCADE -->|shock > 0.5| PANIC[emotion_tag=panic]
SHOCK_CASCADE -->|empathic horror if witness| EMPATHY[stress_delta += shock * 30 * modifier]

RXT -->|uses| RXTMOD
SOC -->|calls| PROP
PROP -->|List StateDeltas domainEMOTION + domainSOCIAL| SOC

%% --- ADR-036: Social Physics (Directive Interpretation) ---
DIS[DirectiveInterpretationSubscriber ADR-036] -->|calculates legitimacy = maxfear_trust/100| LEGIT{legitimacy > 0.3 Internal Check ADR-057}
P7 -->|drain_events| DIS
P2 -->|drain_events| DIS
LEGIT -->|Has Legitimacy| OBEY_INT[obedience_intensity > 0 StateDeltas EMOTION+SOCIAL+directive_obedience]
LEGIT -->|No Legitimacy| IRR_INT[irritation_intensity > 0 StateDeltas EMOTION+SOCIAL+stress]
OBEY_INT -->|submissive_fear / unease| DBUF2
IRR_INT -->|aggression_inhibition unlock| DBUF2

%% Bug #6 Fix: Fallback injection
LE_COLD[LifeEngine Cold Cache] -.->|Empty State| DIS
DM_CTX[TickContext.all_npcs_raw via DMContextDTO Fallback ADR-064] -.->|Inject if Cold| DIS

RXT -->|Phase8Result deltas| ORCH
SOC -->|Phase8Result deltas| ORCH
CSUB -->|Phase8Result deltas| ORCH
end

subgraph Phase_9_10[Фазы 9-10: CFRM P2 Phenomenology & Persistence ADR-0033]
ORCH[TickOrchestrator] -.->|_rebuild_cluster_occupancy| CO[ClusterOccupancy ADR-0029]
ORCH -->|_deobjectify_event + classify_event ADR-038| EB
ORCH -->|will_conflict_data -> shared_context ADR-039| P9
EB -->|drain disturbances| LCS[LocalCausalSolver P2 Neighbor Propagation]
CG -.->|topology| LCS
CO -.->|spatial index O1| LCS
LCS -->|PerceivedPhenomenon per observer| PROJ[ProjectionPolicy Physical Cognitive Social]
PROJ -->|aggregate per entity| PHEN[PhenomenologicalState Local Truth]
PHEN -->|convert| PRESSURE[PsychologicalPressure fear uncertainty directive_obedience ADR-036]
PRESSURE -->|generate StateDeltas PERCEPTION ADR-040| DBUF2

LCS -->|Patches| SA[StateApplicator.apply_batch v2]
LDA -.->|collapsed v1 StateDeltas for legacy| SA
DBUF2 --> CFRM
SPATIAL_BUF --> CFRM
DBUF_P --> CFRM

SA -->|_apply_faction_delta| REP[ReputationEngine.apply_deltas]
SA -->|_apply_body_delta| BSMUT[NPCState.body_state mutation]
SA -->|_apply_perception_delta| PKERN[NPCState.perceptual_kernel mutation ADR-040]
SA -->|_apply_delta_to_raw dict to NPCState bridge| RAW[all_npcs_raw]

LCS -->|apply_spatial_events| SSM
SSM -->|resolve x,y via SpatialService| SC_T1[world_snapshot t+1 PROJECTION ADR-0016]

RAW -.->|player_dict| APA[AvatarPresentationAssembler Translation Layer ADR-035]
APA -->|AvatarStateDTO| P9

SC_T1 -->|WorldSnapshotDTO + ambient_phenomenology ADR-040| P9[Phase 9: WorldSnapshotBuilder]
SC_T1 -->|atomic commit| P10[(Phase 10: SQLite)]
P9 -->|WorldSnapshotDTO + AvatarStateDTO| GL
end

subgraph Frontend[Frontend Pygame - Cinematic Presentation Layer]
GL[GameLoop.idle_tick DTO to dict] -->|dict world_snapshot| BRIDGE[GameLoopBridge]
BRIDGE -->|dict scene_state + game_time_seconds| PY[Pygame UI Screen]
PY -->|_build_perceived_scene + spatial_obstacles| PSC[PerceivedScene]

PY -->|npc_positions| KNOWN[known_names dict npc_name.lower: name]

KEYB[TextInput Widget Shift+Enter NoPaste KeyRepeat] -->|On Enter| P_BEAT[Player NarrativeBeat creation_tick]
P_BEAT -->|append| MLOG[message_log NarrativeBeat list]

POLL[ActionQueue poll Backend Result] -->|dm_response| DM_PARSE[Split Lines + known_names Speaker Extraction + DeliveryType/Recognition Parse]
POLL -->|npc_reactions| NPC_PARSE[Echo Filter is_short_input + DeliveryType/Recognition Parse]
POLL -->|errors/movement/doors| SLOG[system_log list str]

DM_PARSE -->|NarrativeBeat creation_tick| MLOG
NPC_PARSE -->|NarrativeBeat creation_tick| MLOG

MLOG -->|TRANSIENT age > 5s| FADE[alpha fade 5s-7s via BLEND_RGBA_MULT]
FADE -->|alpha <= 0| REMOVE[Delete beat from MLOG]

MLOG --> NR[NarrativeRenderer]
SLOG --> LOG_DRAW[Log Layer Renderer]

NR -->|Left Bubble DeliveryType styles + RecognitionLevel dithering + alpha| CIN_LAYER[Cinematic Layer Center/Bottom]
NR -->|Right Bubble Player| CIN_LAYER
LOG_DRAW -->|Top Right Semi-transparent| LOG_LAYER[Log Layer System/Move/Errors]

PY -.->|ActionQueue submit IntentDTO| P1

TC[Time Scale Keys 1-4 _time_scale 1 4 10 50] -->|interval / _time_scale| PY

DGW[DirectGameGateway] -->|send_action| BRIDGE_TURN[GameLoopBridge.turn]
BRIDGE_TURN -->|_collect stream_turn| TURN_RESULT[TurnResult + world_snapshot + npc_positions ADR-0011]
TURN_RESULT -->|result.world_snapshot + result.npc_positions| DGW
DGW -->|GameActionResponse world_snapshot=... npc_positions=...| PY

PY -->|game_time_seconds| CAL[format_world_date Year Day HH:MM Priority 2]
CAL -->|HUD Render Top Right| CIN_LAYER

MOVE[_MoveState Navigation Kinetics Embodiment ADR-0011] -->|facing_angle + facing_mode| REND[SceneRenderer.render Lerp via dt]
PY -->|avatar_state from world_snapshot| REND
REND --> EPI[_apply_avatar_perception_overlay Motion Bias Temporal Delay Contrast ADR-040]
EPI -.->|final screen blit| PY
end

P9 -.->|TickResultDTO + will_conflict_data ADR-039| GL
CONSTANTS[domain constants.py ACTION_INTENSITY] -.->|imports| P1
CONSTANTS -.->|imports| P6
P05 -.->|ALWAYS both paths| DBUF
P8FLUSH[Phase 8 delta_buffer flush] -.->|aggregate_deltas apply_batch| AGR

%% --- PLANNED: Continuous Spatial Simulation (ADR-0013) ---
TRAV -.->|Phase 0.75 MovementStepper| ME
TRAV[TraversalState PLANNED ADR-0013] -->|speed * delta_time integration| MSTEP[MovementStep PLANNED]
MSTEP -->|continuous position update| SPATIAL_BUF

classDef spatial fill:#f9f,stroke:#333,stroke-width:2px;
class SS,GC,ME,TT,SPATIAL_BUF spatial;
classDef temporal fill:#dfd,stroke:#333,stroke-width:2px;
class SNAP_T,SC_T1,SSM temporal;
classDef frontend fill:#bbf,stroke:#333,stroke-width:2px;
class GL,BRIDGE,PY,PSC,TC,DGW,BRIDGE_TURN,TURN_RESULT,CAL,MOVE,REND frontend;
classDef lod fill:#f96,stroke:#333,stroke-width:2px;
class RRM,MI,LSI,SKIP lod;
classDef physiology fill:#f55,stroke:#333,stroke-width:2px;
class IE,CL,PP,BSMUT,BODY_INIT,PDS,CSUB physiology;
classDef time fill:#ff9,stroke:#333,stroke-width:2px;
class ADV,TA time;
classDef future fill:#ff0,stroke:#333,stroke-width:2px,stroke-dasharray: 5 5;
class TRAV,MSTEP future;
classDef layered fill:#ccf,stroke:#333,stroke-width:3px;
class MAT,SHOCK_CASCADE,PANIC,EMPATHY,LAYER_SEP layered;
classDef cfrm fill:#dfd,stroke:#333,stroke-width:2px;
class CFRM,PROJ,ATTEN,LCS,SA,REP,BSMUT,RAW,EB,CG,CO cfrm;

classDef adapter fill:#f88,stroke:#333,stroke-width:2px,stroke-dasharray: 5 5;
class LDA adapter;
%% --- ADR-037: Phenomenological Presentation & Resistance Medium ---
DGW -->|GameActionResponse + will_conflict_data| PY
PY -.->|will_conflict_data ADR-041 UNWIRED| INFECT[text_input.TextInput.infect Resistance Medium ADR-039]
INFECT -.->|Моторное сопротивление вводу| PLAYER[Player Input]

PY -->|avatar_state dict DIRECT PASS| REND[scene_renderer.SceneRenderer render]
PY -.->|avatar_state dict UNWIRED| FW[presentation_firewall.PresentationFirewall sanitize + clamp ADR-037]
FW -.->|SanitizedPerceptualVectors| PM[perceptual_momentum.PerceptualMomentum S-curve + inertia ADR-037]
PM -.->|ManifestationProfile| REND

classDef firewall fill:#f66,stroke:#333,stroke-width:2px;
classDef momentum fill:#ff9,stroke:#333,stroke-width:2px;
classDef resistance fill:#f9f,stroke:#333,stroke-width:2px;
class FW firewall;
class PM momentum;
class INFECT resistance;

subgraph Causal_Sandbox[Каузальная Обсерватория ADR-050]
    direction TB
    CLOCK[DeterministicClock delta=10s] --> TRACE[CausalTrace parent_id linkage]
    
    subgraph Phenomenology_Lab[Феноменологическая Лаборатория]
        TRACE --> PHYSICS_TEST[test_balance_scales Physical exponential loss]
        TRACE --> COG_TEST[test_balance_scales Cognitive inference stress]
        TRACE --> SOC_TEST[test_balance_scales Social dramatization]
        TRACE --> RUMOR_TEST[test_rumor_mutation Epistemic divergence]
    end
    
    subgraph System_Closure[Системный Контур]
        TRACE --> FULL_OB[test_causal_closure Full obedience closure]
        TRACE --> BRAVE_RES[test_causal_closure Brave resistance closure]
    end
    
    subgraph Stress_Degradation[Стресс-Деградация]
        TRACE --> EROSION[test_authority_erosion Cumulative strain]
        TRACE --> RECOVERY[test_authority_erosion Resistance recovery]
    end
end

classDef sandbox fill:#ff9,stroke:#333,stroke-width:2px,stroke-dasharray: 5 5;
class CLOCK,TRACE,PHYSICS_TEST,COG_TEST,SOC_TEST,RUMOR_TEST,FULL_OB,BRAVE_RES,EROSION,RECOVERY sandbox;

%% --- ADR-048: Authoritative Spatial Spine ---
subgraph Spatial_Authority[Spatial Authority ADR-048]
    direction TB
    ORCH[npc_orchestration] -->|инстанцирует| SQS[SpatialQueryService]
    SQS -->|spatial_query| NTS[NpcTickServices]
    NTS -->|spatial_query| NTP[npc_tick_pipeline]
    
    NTP -.->|ЗАПРЕЩЕНО| SS[scene_state spatial reads]
    
    SS -->|write-only projection| WSB[WorldSnapshotBuilder]
    WSB -->|npc_positions player_spatial| FE[Frontend]
end

classDef spatial fill:#9cf,stroke:#333,stroke-width:2px;
class ORCH,SQS,NTS,NTP spatial;
classDef forbidden fill:#f66,stroke:#333,stroke-width:2px,stroke-dasharray: 5 5;
class SS forbidden;

%% --- ADR-058: Frontend Dual-Time Ontology ---
subgraph Dual_Time_Ontology[Dual-Time Ontology ADR-058]
    direction TB
    WSB[WorldSnapshotBuilder] -->|NPCPositionDTO + initiative_suppression| API[API Route Universal Serializer ADR-060]
    WSB -->|active_traversals| API
    
    API -->|WorldSnapshotDTO| GS[GameScreen]
    
    subgraph Frontend_Interpolator[Frontend: Elastic Presentation Layer]
        GS -->|extract traversals| PE[PerceivedEntity]
        GS -->|extract initiative_suppression| PE
        
        PE -->|waypoints + progress + speed * dt| SR[SceneRenderer Continuous Lerp]
        PE -->|initiative_suppression > 0.7| SR_TREMOR[SceneRenderer Motor Tremor]
    end
    
    GS -.->|ЗАПРЕЩЕНО| PF[find_path / Client Prediction]
end

classDef dualtime fill:#9f9,stroke:#333,stroke-width:2px;
class WSB,API,GS,PE,SR,SR_TREMOR dualtime;
class PF forbidden;

%% --- ADR-059: Causal Diagnostic System (CDS) ---
subgraph Diagnostic_Layer[Observability Layer: CDS ADR-059]
    direction TB
    LAUNCHER[game_launcher.py] -->|DIAGNOSTICS_ENABLED=True start background thread| COBS[CausalObserver]
    
    STDOUT[Game stdout/log] -->|pipe/file read| COBS
    GIT[git log -5 & MUTATIONS.md] -->|read| COBS
    TODO[Select-String TODO/FIXME] -->|read| COBS
    
    COBS -->|parse patterns| PR[PatternRegistry]
    COBS -->|build chains| CCB[CausalChainBuilder]
    COBS -->|check health| HC[HealthCheckers tick/movement/spatial]
    
    COBS -->|render 3 sections| REND_CDS[ReportRenderer]
    REND_CDS -->|overwrite| REPORT[reports/LAST_SESSION.md LLM Context]
end

classDef diagnostic fill:#fcf,stroke:#333,stroke-width:2px,stroke-dasharray: 5 5;
class LAUNCHER,COBS,STDOUT,GIT,TODO,PR,CCB,HC,REND_CDS,REPORT diagnostic;

%% --- ADR-059: Temporal Authority Separation & SnapshotBuilder Immutability ---
subgraph Temporal_Authority[Temporal Authority Separation ADR-059]
    direction TB
    GL_TICK[GameLoop idle_tick & _run_pipeline] -->|tick += 1| SS_TICK[scene_state.tick Monotonic Causal]
    
    SS_TICK -->|started_tick + duration_ticks| TRAVERSAL[TraversalState Tick-based]
    SS_TICK -->|read current_tick| FE_TICK[Frontend scene_state.tick]
    FE_TICK -->|current_tick| PROGRESS[progress = current - started / duration]
    TRAVERSAL -->|started_tick, duration_ticks| PROGRESS
    
    SS_TICK -->|tick >= completed| SSM_FINAL[SceneStateManager Finalize Traversals & Enrich local_position]
    SSM_FINAL -->|Immutable Source| WSB_IMMUT[WorldSnapshotBuilder Pure Projection]
    
    WSB_IMMUT -.->|ЗАПРЕЩЕНО: delete/mutate traversals| SSM_FINAL
    CALC_TIME[game_time_seconds // 60] -.->|ЗАПРЕЩЕНО: Circular Dependency| SS_TICK
    REAL_TIME[time.time / pygame.get_ticks] -.->|ЗАПРЕЩЕНО: Second Clock| PROGRESS
end

classDef temporalAuth fill:#ccf,stroke:#333,stroke-width:2px;
class GL_TICK,SS_TICK,TRAVERSAL,FE_TICK,PROGRESS,SSM_FINAL,WSB_IMMUT temporalAuth;
classDef forbiddenTime fill:#f66,stroke:#333,stroke-width:2px,stroke-dasharray: 5 5;
class CALC_TIME,REAL_TIME forbiddenTime;

%% --- ADR-061 & ADR-062: Causal Memory & LOD Arbitration ---
subgraph Sprint36[Сессия 42: Каузальная Память и Арбитраж Движения]
    direction TB
    
    %% Memory Flow
    EB_P2[EventBus Primary] -->|spatial| P2E[phase_2_events]
    EB_COG[EventBus Cognitive PLAYER_SPOKE] -->|get_recent_events| ETR[events_to_remember]
    P2E --> ETR
    
    ETR -->|apply| MM[MemoryManager]
    MM -->|summary = raw_input| EM[EventMemory L2 Cache]
    EM -->|recall| VC[VerbalizationContext recalled_facts]
    VC -->|add_npc_l2_memory| LLM[LLM Prompt]
    
    %% Movement Arbitration Flow
    LE[LifeEngine tick_decisions] -->|winner-takes-all| CAND[Mixed Intent List]
    CAND -->|ADR-060.1 Arbitration| MERGED[merged_intents: Macro first, Micro second]
    MERGED -->|process_intents| ME[MovementEngine]
    
    %% Forbidden
    EB_COG -.->|ЗАПРЕЩЕНО: Игнорировать когнитивные события| P2E
    CAND -.->|ЗАПРЕЩЕНО: Прямая передача без арбитража| ME
end

classDef sprint36 fill:#ffd700,stroke:#333,stroke-width:2px;
class EB_P2,EB_COG,P2E,ETR,MM,EM,VC,LLM,LE,CAND,MERGED,ME sprint36;


%% --- ADR-064: Schema Enforcement & Will Deafness Fix ---
subgraph Sprint45[Сессия 45: Оживление Графа и Трубы Воли]
    direction TB
    
    %% Spatial Graph Flow (SCF=0 Fix)
    EDIT_JSON[Map Editor JSON] -->|save| DM[data_manager]
    DM -->|inject location_id| EDIT_JSON
    EDIT_JSON -->|load_editor_json| GC[graph_compiler]
    GC -->|Strict Match or Valid Inferred| SS[SpatialService]
    GC -.->|DEPRECATION: Fallback by prefix| SS
    GC -.->|REJECT: Collision / No ID| X[Dead Graph SCF=0]
    
    %% Will Pipeline Flow (SHI=0% Fix)
    SOCIAL[player_social / player_moves] -->|action| RIP[resolve_intent_pressure]
    RIP -->|identity_deviation > 0.3| IPP[IntentPressureProfile]
    IPP -->|input| WG[WillpowerGate]
    
    %% Forbidden
    DM -.->|ЗАПРЕЩЕНО: Сохранять без location_id| EDIT_JSON
    SOCIAL -.->|ЗАПРЕЩЕНО: Возвращать нулевое давление| RIP
end

classDef sprint45 fill:#b30059,stroke:#333,stroke-width:2px;
class EDIT_JSON,DM,GC,SS,X,SOCIAL,RIP,IPP,WG sprint45;


%% --- ADR-061/066: Player Position Authority & llama-server Guard ---
subgraph Sprint46[Сессия 46: Player Position Authority]
    direction TB
    
    %% Player Position Authority (ADR-061)
    FE[Frontend player_x/y HTTP POST] -->|player_position| SI[scene_init._update_player_position ADR-061]
    SI -->|ЕДИНСТВЕННЫЙ ПИСАТЕЛЬ| NP[npc_positions.player.local_position]
    NO[npc_orchestration] -->|reads NP directly| SSS[SpatialService.get_nearest]
    SSS -->|resolved_node| PIPE[npc_tick_pipeline APPROACH_NAV]
    
    %% player_spatial = DEAD source
    PS[player_spatial DEAD SOURCE] -.->|ЗАПРЕЩЕНО: запись ADR-048 Phase 3| NP
    NO -.->|ЗАПРЕЩЕНО: читать из player_spatial| PS
    
    %% llama-server double-launch guard (ADR-066)
    MAIN2[main.py lifespan] -->|pre-check health| LLAMA[llama-server :8080]
    MAIN2 -->|_llama_started_by_us=True| GUARD[shutdown guard]
    GUARD -->|kill only if ours| LLAMA
    ATX[atexit._kill_llama_server] -->|kill only if ours| LLAMA
end

classDef sprint46 fill:#0066cc,stroke:#333,stroke-width:2px;
class FE,SI,NP,NO,SSS,PIPE,PS,MAIN2,LLAMA,GUARD,ATX sprint46;


%% --- ADR-064/065: Directive Continuity & Spatial Authority Consolidation ---
subgraph Sprint47[Сессия 47: Труба Воли и Spatial Authority]
    direction TB
    
    %% Will Pipeline Continuity - Bug 6 Fix
    LE2[LifeEngine Cache] -->|Cold Cache returns empty| DIS[DirectiveInterpretationSubscriber]
    DM_CTX[DMContextDTO.all_npcs_raw] -->|Fallback injected by TickOrchestrator| DIS
    DIS -->|ObediencePressure greater 0| OBEY[Social Physics Engine]
    
    %% Spatial Authority Consolidation
    GL[GameLoop] -->|Inject via NpcTickServices| SS2[SpatialService]
    TO[TickOrchestrator] -->|resolves spatial service| SS2
    TO -.->|FORBIDDEN manual build| SS2
end

classDef sprint47 fill:#0066cc,stroke:#333,stroke-width:2px;
