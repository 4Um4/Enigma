flowchart TD
subgraph Phase_0_2[Фазы 0-2: Input and Simulation]
P0[Phase 0: LifeEngine] -->|scene_changes| P05
P0 -->|scene_changes| P2
P05[Phase 0.5: Idle Services ALWAYS] -->|List StateDeltas| DBUF[delta_buffer]
PI[Player Input] -->|IntentDTO| P1[Phase 1: Input]
P1 -->|EventDTO intensity from ACTION_INTENSITY| P2[Phase 2: EventBus]
P0 -->|SpatialService API| P2
end

subgraph Phase_0_5_Detail[Фаза 0.5: Time-driven decay]
SNAP[_build_npc_snapshots List NPCStateSnapshot] --> SDH[SocialDecayHandler closing drift]
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
P7 -->|drain_events| SOC[SocialSubscriber]
P2 -->|drain_events| SOC

PROP[propagate_social_rumors pure function max aggregation]

SOC -->|calls| PROP
PROP -->|List StateDeltas social_target| SOC

PER -->|Phase8Result perceiving_npc_ids| ORCH
SOC -->|Phase8Result deltas| ORCH
end

subgraph Phase_9_10[Фазы 9-10: Integration and Persistence]
ORCH[TickOrchestrator] -->|affected_npc_ids| P9[Phase 9: WorldSnapshotBuilder]
ORCH -->|aggregate_deltas| AGR[Aggregator group by npc_id+target sum]
AGR -->|List StateDeltas| SA[StateApplicator.apply_batch Single mutation point]
SA -->|_apply_faction_delta| REP[ReputationEngine.apply_deltas]
SA -->|_apply_delta_to_raw dict to NPCState bridge| RAW[all_npcs_raw]
SA -->|atomic commit| P10[(Phase 10: SQLite)]
P9 -->|WorldSnapshotDTO| GL
end

subgraph Frontend[Frontend Pygame]
GL[GameLoop.idle_tick DTO to dict] -->|dict world_snapshot| BRIDGE[GameLoopBridge]
BRIDGE -->|dict| PY[Pygame UI]
end

P9 -.->|TickResultDTO| GL
CONSTANTS[domain constants.py ACTION_INTENSITY] -.->|imports| P1
CONSTANTS -.->|imports| P6
P05 -.->|ALWAYS both paths| DBUF