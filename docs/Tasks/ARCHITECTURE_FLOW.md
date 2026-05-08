flowchart TD
subgraph Spatial_Layer[Spatial Service v1.2: Единый источник пространственных данных]
GC[GraphCompiler compile_graph] -->|graph, connections, alias_map| SS[SpatialService]
SC[SceneState] -->|build_overlay| SS
SS -->|DI: set_spatial_service| ME[MovementEngine]
SS -->|get_node with prefix fallback ADR-0009| SSM[SceneStateManager]
end

subgraph Phase_0_2[Фазы 0-2: Input and Simulation]
P0[Phase 0: LifeEngine] -->|scene_changes| P05
P0 -->|scene_changes| P2
P0 -->|ctx.npc_states = ctx.all_npcs_raw| SA_SYNC[State Sync ADR-004]
P05[Phase 0.5: Idle Services ALWAYS] -->|List StateDeltas| DBUF[delta_buffer]
PI[Player Input] -->|IntentDTO| P1[Phase 1: Input]
P1 -->|EventDTO intensity from ACTION_INTENSITY| P2[Phase 2: EventBus]
SS -.->|DI: set_spatial_service| P0
ME -->|find_path canonical IDs| TT[TransitTracker]
TT -->|advance_all SceneChange| P0
end

subgraph Phase_0_5_Detail[Фаза 0.5: Time-driven decay]
SNAP[_build_npc_snapshots social_stats to relationship_cache mapping] --> SDH[SocialDecayHandler closing drift]
SNAP --> RDH[ReputationDecayHandler]
RDH -->|calls| RE[ReputationEngine.compute_decay pure]
SDH -->|StateDeltas domainSOCIAL payloadSocialPayload| DBUF2[delta_buffer]
RDH -->|StateDeltas domainREPUTATION payloadReputationPayload| DBUF2
end

subgraph NPC_Loading[NPC Loading Pipeline]
NPS[config/npc/individuals/*.json] -->|load_archetype_chain| MERG[static NPC dicts]
MERG -->|+ runtime overlay| RUNTIME[npc_runtime.json]
RUNTIME --> ENRICH[_enrich_with_social_relations village_relations.json]
ENRICH -->|relationship_cache NPC-to-NPC + base_values| LOADED[Loaded NPC dicts]
VR[config/npc/social/village_relations.json] -->|load_social_base| ENRICH
end

LOADED -.->|all_npcs_raw| SNAP

subgraph Phase_3_7[Фазы 3-7: Memory and Decision]
P2 -->|EventDTO| P3[Phase 3: MemoryProcessor]
P3 -->|Updated NPCState| P4[Phase 4: TopicExtractor]
P4 -->|Topic| P5[Phase 5: DecisionHub]
P5 -->|CommunicationIntent| P6[Phase 6: IntentEventAdapter]
P6 -->|EventDTO| P7[Phase 7: EventBus Secondary]
end

subgraph Reactive_Movement[Реактивное движение: LOD1 Macro vs LOD0 Micro]
P5 -->|approach/flee intent| RRM[_resolve_reactive_movement]
RRM -->|Macro: different zone| MI[MovementIntent LOD1 Traversal]
MI --> ME
RRM -->|Micro: same zone| LSI[LocalSteeringIntent LOD0 PLANNED]
LSR -.->|Direct x,y update| SSM
end

subgraph Phase_8[Фаза 8: Event-driven Handlers]
P7 -->|drain_events| PER[PerceptionSubscriber]
P2 -->|drain_events| PER
P7 -->|drain_events| SOC[SocialSubscriber]
P2 -->|drain_events| SOC
P7 -->|drain_events| RXT[ReactionSubscriber]
P2 -->|drain_events| RXT
P7 -->|drain_events| SOC[SocialSubscriber]
P2 -->|drain_events| SOC

PROP[propagate_social_rumors pure function v2 EMOTION+SOCIAL split]
RXTMOD[_compute_reaction_modifier composure x fear_drive x willpower]

RXT -->|uses| RXTMOD
SOC -->|calls| PROP
PROP -->|List StateDeltas domainEMOTION + domainSOCIAL| SOC

PER -->|Phase8Result perceiving_npc_ids| RXT
RXT -->|Phase8Result 2 deltas per NPC EMOTION+SOCIAL| ORCH
SOC -->|Phase8Result deltas| ORCH
end

subgraph Phase_9_10[Фазы 9-10: Integration and Persistence]
ORCH[TickOrchestrator] -->|affected_npc_ids| P9[Phase 9: WorldSnapshotBuilder]
ORCH -->|aggregate_deltas group by npc_id+domain+target sum payloads| AGR[Aggregator v2]
AGR -->|List StateDeltas| SA[StateApplicator.apply_batch v2 extract with v1 fallback]
SA -->|_apply_faction_delta| REP[ReputationEngine.apply_deltas]
SA -->|_apply_delta_to_raw dict to NPCState bridge| RAW[all_npcs_raw]
SA -->|atomic commit| P10[(Phase 10: SQLite)]
P9 -->|WorldSnapshotDTO| GL

SSM[SceneStateManager] -->|_enrich_spatial_data walls/obstacles/names| P9
SSM -->|ADR-0009: field=position allowed| POS_RESOLVE[Resolve position to x,y via SpatialService]
POS_RESOLVE -->|local_position| SC
end

subgraph Frontend[Frontend Pygame - Cinematic Presentation Layer]
GL[GameLoop.idle_tick DTO to dict] -->|dict world_snapshot| BRIDGE[GameLoopBridge]
BRIDGE -->|dict scene_state| PY[Pygame UI Screen]
PY -->|_build_perceived_scene локальная сборка| PSC[PerceivedScene]

KEYB[TextInput Widget] -->|On Enter| P_BEAT[Player NarrativeBeat]
P_BEAT -->|append| MLOG[message_log]

POLL[ActionQueue poll] -->|dm_response| ECHO[Echo Filter]
ECHO -->|Create NPC/System Beat| MLOG

MLOG --> NR[NarrativeRenderer]
NR --> CIN_LAYER[Cinematic Layer]
NR --> LOG_LAYER[Log Layer]

PY -.->|ActionQueue submit IntentDTO| P1
end

P9 -.->|TickResultDTO| GL
CONSTANTS[domain constants.py ACTION_INTENSITY] -.->|imports| P1
CONSTANTS -.->|imports| P6
P05 -.->|ALWAYS both paths| DBUF
P8FLUSH[Phase 8 delta_buffer flush] -.->|aggregate_deltas apply_batch| AGR

classDef spatial fill:#f9f,stroke:#333,stroke-width:2px;
class SS,GC,SC,ME,TT,SSM,POS_RESOLVE spatial;
classDef frontend fill:#bbf,stroke:#333,stroke-width:2px;
class GL,BRIDGE,PY,PSC frontend;
classDef lod fill:#f96,stroke:#333,stroke-width:2px;
class RRM,MI,LSI lod;