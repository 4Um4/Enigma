flowchart TD
%% === ADR-0015: IMMUTABLE SNAPSHOT FEED (Temporal Isolation) ===
SNAP_T[world_snapshot t IMMUTABLE ADR-0015] -->|Read-Only Feed| P0
SNAP_T -->|Read-Only Feed| P3
SNAP_T -->|Read-Only Feed| P5
SNAP_T -->|Read-Only Feed| PER

subgraph Spatial_Layer[Spatial Service v1.2: Единый источник пространственных данных]
GC[GraphCompiler compile_graph] -->|graph, connections, alias_map| SS[SpatialService]
SC_T[SceneState t-1] -->|build_overlay| SS
SS -->|DI: set_spatial_service| ME[MovementEngine]
SS -->|get_node with prefix fallback ADR-0009| SSM[SceneStateManager Spatial Reducer ADR-0015]
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
IC -->|IntentSemanticField| TR[Target Reference Resolver String to ID]
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
PKERN[NPCState.perceptual_kernel T-1] -.->|translate_kernel_to_context ADR-053| DCTX[DecisionContext ADR-053]
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

MAT -->|physical_deltas_materialized| RXT[ReactionSubscriber ADR-0016]
P7 -->|drain_events| RXT
P2 -->|drain_events| RXT

MAT -->|physical_deltas_materialized| SOC[SocialSubscriber]
P7 -->|drain_events| SOC
P2 -->|drain_events| SOC

PROP[propagate_social_rumors pure function v2 EMOTION+SOCIAL split]
RXTMOD[_compute_reaction_modifier composure x fear_drive x willpower]
RXT -->|reads shock_impulse from materialized physical layer| SHOCK_CASCADE[Cascade: Force → Pain → Shock → Emotion ADR-0016]
SHOCK_CASCADE -->|shock > 0.5| PANIC[emotion_tag=panic]
SHOCK_CASCADE -->|empathic horror if witness| EMPATHY[stress_delta += shock * 30 * modifier]

RXT -->|uses| RXTMOD
SOC -->|calls| PROP
PROP -->|List StateDeltas domainEMOTION + domainSOCIAL| SOC

%% --- ADR-036: Social Physics (Directive Interpretation) ---
DIS[DirectiveInterpretationSubscriber ADR-036] -->|reads semantic_action + target_id| OBEDIENCE[PsychologicalPressure directive_obedience]
P7 -->|drain_events| DIS
P2 -->|drain_events| DIS
OBEDIENCE -->|StateDeltas EMOTION + SOCIAL + directive_obedience| DBUF2

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
PY -->|will_conflict_data| INFECT[TextInput.infect Resistance Medium ADR-037]
INFECT -->|Моторное сопротивление вводу| PLAYER[Player Input]

PY -->|avatar_state dict| FW[PresentationFirewall sanitize + clamp ADR-037]
FW -->|SanitizedPerceptualVectors| PM[PerceptualMomentum S-curve + inertia + stochasticity ADR-037]
PM -->|ManifestationProfile| REND

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
    WSB[WorldSnapshotBuilder] -->|NPCPositionDTO + initiative_suppression| API[API Route]
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
