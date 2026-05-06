flowchart TD
subgraph Spatial_Layer[Spatial Service v1.2: Единый источник пространственных данных]
GC[GraphCompiler compile_graph] -->|graph, connections, alias_map| SS[SpatialService]
SC[SceneState] -->|build_overlay| SS
SS -->|DI: set_spatial_service| ME[MovementEngine]
end

subgraph Phase_0_2[Фазы 0-2: Input and Simulation]
P0[Phase 0: LifeEngine] -->|scene_changes| P05
P0 -->|scene_changes| P2
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
SDH -->|StateDeltas social_target trust_delta| DBUF2[delta_buffer]
RDH -->|StateDeltas faction_id reputation_delta| DBUF2
end

subgraph Phase_3_7[Фазы 3-7: Memory and Decision]
P2 -->|EventDTO| P3[Phase 3: MemoryProcessor]
P3 -->|Updated NPCState| P4[Phase 4: TopicExtractor]
P4 -->|Topic| P5[Phase 5: DecisionHub]
P5 -->|CommunicationIntent| P6[Phase 6: IntentEventAdapter]
P6 -->|EventDTO| P7[Phase 7: EventBus Secondary]
end

subgraph Phase_8[Фаза 8: Event-driven Handlers]
P7 -->|drain_events| PER[PerceptionSubscriber]
P2 -->|drain_events| PER
P7 -->|drain_events| RXT[ReactionSubscriber]
P2 -->|drain_events| RXT
P7 -->|drain_events| SOC[SocialSubscriber]
P2 -->|drain_events| SOC

PROP[propagate_social_rumors pure function max aggregation]
RXTMOD[_compute_reaction_modifier composure x fear_drive x willpower]

RXT -->|uses| RXTMOD
SOC -->|calls| PROP
PROP -->|List StateDeltas social_target| SOC

PER -->|Phase8Result perceiving_npc_ids| RXT
RXT -->|Phase8Result deltas stress fear trust| ORCH
SOC -->|Phase8Result deltas| ORCH
end

subgraph Phase_9_10[Фазы 9-10: Integration and Persistence]
ORCH[TickOrchestrator] -->|affected_npc_ids| P9[Phase 9: WorldSnapshotBuilder]
ORCH -->|aggregate_deltas Phase 0.5 + Phase 8 merged| AGR[Aggregator group by npc_id+target sum]
AGR -->|List StateDeltas| SA[StateApplicator.apply_batch Single mutation point]
SA -->|_apply_faction_delta| REP[ReputationEngine.apply_deltas]
SA -->|_apply_delta_to_raw dict to NPCState bridge| RAW[all_npcs_raw]
SA -->|atomic commit| P10[(Phase 10: SQLite)]
P9 -->|WorldSnapshotDTO| GL

SSM[SceneStateManager] -->|_enrich_spatial_data walls/obstacles/names| P9
end

subgraph Frontend[Frontend Pygame - Закон 1.1: Нет прямых вызовов Backend]
GL[GameLoop.idle_tick DTO to dict] -->|dict world_snapshot| BRIDGE[GameLoopBridge]
BRIDGE -->|dict scene_state| PY[Pygame UI]
PY -->|_build_perceived_scene локальная сборка| PSC[PerceivedScene]
end

P9 -.->|TickResultDTO| GL
CONSTANTS[domain constants.py ACTION_INTENSITY] -.->|imports| P1
CONSTANTS -.->|imports| P6
P05 -.->|ALWAYS both paths| DBUF
P8FLUSH[Phase 8 delta_buffer flush] -.->|aggregate_deltas apply_batch| AGR

classDef spatial fill:#f9f,stroke:#333,stroke-width:2px;
class SS,GC,SC,ME,TT spatial;
classDef frontend fill:#bbf,stroke:#333,stroke-width:2px;
class GL,BRIDGE,PY,PSC frontend;