```mermaid
graph TD
    ADR-1["ADR-1: State Mutation Law"]
    FILE_delta_buffer_py(("delta_buffer.py"))
    FILE_state_applicator_py(("state_applicator.py"))
    FILE_npc_state_py(("npc_state.py"))
    LAW_L1{"L1"}
    ADR-13["ADR-13: State Mutation Law"]
    ADR-117["ADR-117: State Mutation Law"]
    ADR-O-302["ADR-O-302: Runtime Purity Law"]
    FILE_tick_orchestrator_py(("tick_orchestrator.py"))
    FILE_npc_tick_pipeline_py(("npc_tick_pipeline.py"))
    FILE_kernel_rng_py(("kernel_rng.py"))
    FILE_contracts_interventions_py(("contracts/interventions.py"))
    LAW_L2{"L2"}
    ADR-TZ09-1["ADR-TZ09-1: Runtime Purity Law"]
    ADR-TZ10-1["ADR-TZ10-1: Runtime Purity Law"]
    ADR-S83_1["ADR-S83.1: Runtime Purity Law"]
    ADR-47["ADR-47: No Retro-Simulation Law"]
    FILE_life_engine_py(("life_engine.py"))
    FILE_game_loop___init___py(("game_loop/__init__.py"))
    LAW_L3{"L3"}
    ADR-311["ADR-311: No Retro-Simulation Law"]
    ADR-O-308["ADR-O-308: Silent Failure Prohibition"]
    FILE_dm_router_py(("dm_router.py"))
    FILE_intent_compressor_py(("intent_compressor.py"))
    FILE_errors_py(("errors.py"))
    LAW_L4{"L4"}
    ADR-159["ADR-159: Async Intent Compression Law"]
    FILE_input_intent_compressor_py(("input/intent_compressor.py"))
    LAW_L4_1{"L4.1"}
    ADR-S118["ADR-S118: Async Intent Compression Law"]
    LAW_L4_2{"L4.2"}
    LAW_L7_1{"L7.1"}
    LAW_L12_1{"L12.1"}
    ADR-161["ADR-161: GameActionResponse Contract Law"]
    FILE_api_routes_py(("api/routes.py"))
    ADR-31["ADR-31: Will & Pressure Law"]
    FILE_will_py(("will.py"))
    FILE_decision_hub_py(("decision_hub.py"))
    FILE_affect_py(("affect.py"))
    LAW_L5{"L5"}
    ADR-36["ADR-36: Will & Pressure Law"]
    ADR-88["ADR-88: Will & Pressure Law"]
    ADR-O-146["ADR-O-146: Will & Pressure Law"]
    ADR-149["ADR-149: Will & Pressure Law"]
    ADR-S93_2["ADR-S93.2: Cognitive Contour Law (PE Active Inference)"]
    FILE_expectation_store_py(("expectation_store.py"))
    FILE_pe_modifier_resolver_py(("pe_modifier_resolver.py"))
    FILE_rules_subscriber_py(("rules_subscriber.py"))
    LAW_L6{"L6"}
    ADR-TZ08-3["ADR-TZ08-3: Cognitive Contour Law (PE Active Inference)"]
    ADR-152["ADR-152: Cognitive Contour Law (PE Active Inference)"]
    ADR-TZ05-1["ADR-TZ05-1: LLM & Narrative Exile Law"]
    FILE_game_loop_task_scheduler_py(("game_loop/task_scheduler.py"))
    FILE_dm_agent_py(("dm_agent.py"))
    FILE_verbal_stance_py(("verbal_stance.py"))
    LAW_L7{"L7"}
    ADR-TZ08-7["ADR-TZ08-7: LLM & Narrative Exile Law"]
    ADR-O-313["ADR-O-313: LLM & Narrative Exile Law"]
    ADR-163["ADR-163: Proactive Intent & Aggression Triggers Law"]
    FILE_services_npc_decision_hub_py(("services/npc/decision_hub.py"))
    ADR-165["ADR-165: Proactive Intent & Aggression Triggers Law"]
    ADR-25["ADR-25: CFRM & Somatic Gate Law"]
    FILE_local_causal_solver_py(("local_causal_solver.py"))
    FILE_perceptual_kernel_py(("perceptual_kernel.py"))
    FILE_behavior_manifestation_service_py(("behavior_manifestation_service.py"))
    LAW_L8{"L8"}
    ADR-O-139["ADR-O-139: CFRM & Somatic Gate Law"]
    ADR-O-143["ADR-O-143: CFRM & Somatic Gate Law"]
    ADR-O-147["ADR-O-147: CFRM & Somatic Gate Law"]
    LAW_L16{"L16"}
    ADR-8["ADR-8: Spatial SSOT & Factory Law"]
    FILE_spatial_factory_py(("spatial_factory.py"))
    FILE_spatial_query_service_py(("spatial_query_service.py"))
    FILE_domain_movement_py(("domain/movement.py"))
    LAW_L9{"L9"}
    ADR-48["ADR-48: Spatial SSOT & Factory Law"]
    ADR-S82_0["ADR-S82.0: Spatial SSOT & Factory Law"]
    ADR-TZ04-4["ADR-TZ04-4: Spatial SSOT & Factory Law"]
    ADR-O-314["ADR-O-314: Spatial SSOT & Factory Law"]
    ADR-TRAV-FSM["ADR-TRAV-FSM: Traversal FSM Law"]
    FILE_scene_state_manager_py(("scene_state_manager.py"))
    FILE_movement_engine_py(("movement_engine.py"))
    FILE_event_compiler_py(("event_compiler.py"))
    LAW_L10{"L10"}
    ADR-130_1_2["ADR-130.1/2: Traversal FSM Law"]
    ADR-S90_4["ADR-S90.4: Traversal FSM Law"]
    ADR-O-330["ADR-O-330: Spatial Agency Law"]
    LAW_L11_1{"L11.1"}
    ADR-S90_1["ADR-S90.1: Hybrid Geometry & Stigmergy Law"]
    FILE_motion_pipeline_py(("motion_pipeline.py"))
    FILE_world_topology_provider_py(("world_topology_provider.py"))
    FILE_motion_core_py(("motion_core.py"))
    LAW_L11{"L11"}
    ADR-S91["ADR-S91: Hybrid Geometry & Stigmergy Law"]
    ADR-O-324["ADR-O-324: Hybrid Geometry & Stigmergy Law"]
    ADR-O-329["ADR-O-329: Hybrid Geometry & Stigmergy Law"]
    ADR-15["ADR-15: Physiology & Death Lock Law"]
    FILE_vital_state_py(("vital_state.py"))
    FILE_impact_engine_py(("impact_engine.py"))
    FILE_combat_math_py(("combat_math.py"))
    LAW_L12{"L12"}
    ADR-123["ADR-123: Physiology & Death Lock Law"]
    ADR-127["ADR-127: Physiology & Death Lock Law"]
    ADR-HP-UNIFICATION["ADR-HP-UNIFICATION: Physiology & Death Lock Law"]
    ADR-164["ADR-164: D&D 5e Combat Math Law"]
    FILE_services_combat_impact_engine_py(("services/combat/impact_engine.py"))
    ADR-121["ADR-121: Relationship SSOT & Affective Hysteresis Law"]
    FILE_relationship_store_py(("relationship_store.py"))
    FILE_affective_integrator_py(("affective_integrator.py"))
    LAW_L13{"L13"}
    ADR-138["ADR-138: Relationship SSOT & Affective Hysteresis Law"]
    ADR-O-206["ADR-O-206: Relationship SSOT & Affective Hysteresis Law"]
    ADR-S96_2["ADR-S96.2: Relationship SSOT & Affective Hysteresis Law"]
    ADR-S86_7["ADR-S86.7: Epistemic Memory Law"]
    FILE_memory_manager_py(("memory_manager.py"))
    FILE_pipeline_runner_py(("pipeline_runner.py"))
    LAW_L14{"L14"}
    ADR-O-325["ADR-O-325: Epistemic Memory Law"]
    ADR-TZ03-1["ADR-TZ03-1: Frontend Authority Law"]
    FILE_frontend_api_client_py(("frontend/api_client.py"))
    FILE_game_screen_py(("game_screen.py"))
    FILE_scene_renderer_py(("scene_renderer.py"))
    LAW_L15{"L15"}
    ADR-156["ADR-156: Frontend Authority Law"]
    ADR-MANIFEST["ADR-MANIFEST: Frontend Authority Law"]
    ADR-TZ08-4_6["ADR-TZ08-4/6: Epistemic Boundary Law"]
    FILE_agents_dm_agent_py(("agents/dm_agent.py"))
    FILE_scene_r3_direct_builder_py(("scene/r3_direct_builder.py"))
    FILE_world_projection_buffer_py(("world_projection_buffer.py"))
    ADR-93["ADR-93: Epistemic Boundary Law"]
    ADR-O-331["ADR-O-331: Three-Channel Presentation & Body Topology Law"]
    FILE_domain_body_py(("domain/body.py"))
    FILE_domain_presentation_py(("domain/presentation.py"))
    FILE_services_body_body_topology_service_py(("services/body/body_topology_service.py"))
    FILE_services_perception_presentation_assembler_py(("services/perception/presentation_assembler.py"))
    LAW_L16_1{"L16.1"}
    ADR-S147["ADR-S147: Three-Channel Presentation & Body Topology Law"]
    ADR-O-208["ADR-O-208: Identity Pipeline Law"]
    FILE_l1_chronicle_py(("l1_chronicle.py"))
    FILE_drive_resolver_py(("drive_resolver.py"))
    FILE_calibration_engine_py(("calibration_engine.py"))
    LAW_L17{"L17"}
    ADR-211["ADR-211: Identity Pipeline Law"]
    ADR-TIFL-001["ADR-TIFL-001: Identity Pipeline Law"]
    ADR-O-305["ADR-O-305: Belief Crystallization Law (L2.5)"]
    FILE_pattern_detector_py(("pattern_detector.py"))
    FILE_belief_crystallization_engine_py(("belief_crystallization_engine.py"))
    FILE_crystallized_belief_store_py(("crystallized_belief_store.py"))
    LAW_L18{"L18"}
    ADR-306["ADR-306: Belief Crystallization Law (L2.5)"]
    ADR-307["ADR-307: Belief Crystallization Law (L2.5)"]
    ADR-O-312["ADR-O-312: Channel Topology & Task Layer Law"]
    FILE_homeostasis_projector_py(("homeostasis_projector.py"))
    FILE_domain_execution_py(("domain/execution.py"))
    FILE_task_scheduler_py(("task_scheduler.py"))
    LAW_L19{"L19"}
    ADR-313["ADR-313: Channel Topology & Task Layer Law"]
    ADR-O-315["ADR-O-315: LifeProject & Agency Model Law"]
    FILE_life_project_resolver_py(("life_project_resolver.py"))
    FILE_break_progress_engine_py(("break_progress_engine.py"))
    FILE_docs_ENTITY_CONTINUITY_CONTRACT_md(("docs/ENTITY_CONTINUITY_CONTRACT.md"))
    LAW_L20{"L20"}
    ADR-316["ADR-316: LifeProject & Agency Model Law"]
    ADR-317["ADR-317: LifeProject & Agency Model Law"]
    ADR-320["ADR-320: LifeProject & Agency Model Law"]
    ADR-321["ADR-321: LifeProject & Agency Model Law"]
    ADR-INV-DEF["ADR-INV-DEF: Invariant Defense Law"]
    FILE_backend_tests_IPT_py(("backend/tests/IPT.py"))
    FILE_diagnostics_invariant_health_py(("diagnostics/invariant_health.py"))
    FILE_ruff_toml(("ruff.toml"))
    LAW_L21{"L21"}
    ADR-IMMUNE-001["ADR-IMMUNE-001: Invariant Defense Law"]
    ADR-1 -->|IMPLEMENTS| FILE_delta_buffer_py
    ADR-1 -->|IMPLEMENTS| FILE_state_applicator_py
    ADR-1 -->|IMPLEMENTS| FILE_npc_state_py
    ADR-1 -->|DEFINES| LAW_L1
    ADR-13 -->|IMPLEMENTS| FILE_delta_buffer_py
    ADR-13 -->|IMPLEMENTS| FILE_state_applicator_py
    ADR-13 -->|IMPLEMENTS| FILE_npc_state_py
    ADR-13 -->|DEFINES| LAW_L1
    ADR-117 -->|IMPLEMENTS| FILE_delta_buffer_py
    ADR-117 -->|IMPLEMENTS| FILE_state_applicator_py
    ADR-117 -->|IMPLEMENTS| FILE_npc_state_py
    ADR-117 -->|DEFINES| LAW_L1
    ADR-O-302 -->|IMPLEMENTS| FILE_tick_orchestrator_py
    ADR-O-302 -->|IMPLEMENTS| FILE_npc_tick_pipeline_py
    ADR-O-302 -->|IMPLEMENTS| FILE_kernel_rng_py
    ADR-O-302 -->|IMPLEMENTS| FILE_contracts_interventions_py
    ADR-O-302 -->|DEFINES| LAW_L2
    ADR-TZ09-1 -->|IMPLEMENTS| FILE_tick_orchestrator_py
    ADR-TZ09-1 -->|IMPLEMENTS| FILE_npc_tick_pipeline_py
    ADR-TZ09-1 -->|IMPLEMENTS| FILE_kernel_rng_py
    ADR-TZ09-1 -->|IMPLEMENTS| FILE_contracts_interventions_py
    ADR-TZ09-1 -->|DEFINES| LAW_L2
    ADR-TZ10-1 -->|IMPLEMENTS| FILE_tick_orchestrator_py
    ADR-TZ10-1 -->|IMPLEMENTS| FILE_npc_tick_pipeline_py
    ADR-TZ10-1 -->|IMPLEMENTS| FILE_kernel_rng_py
    ADR-TZ10-1 -->|IMPLEMENTS| FILE_contracts_interventions_py
    ADR-TZ10-1 -->|DEFINES| LAW_L2
    ADR-S83_1 -->|IMPLEMENTS| FILE_tick_orchestrator_py
    ADR-S83_1 -->|IMPLEMENTS| FILE_npc_tick_pipeline_py
    ADR-S83_1 -->|IMPLEMENTS| FILE_kernel_rng_py
    ADR-S83_1 -->|IMPLEMENTS| FILE_contracts_interventions_py
    ADR-S83_1 -->|DEFINES| LAW_L2
    ADR-47 -->|IMPLEMENTS| FILE_life_engine_py
    ADR-47 -->|IMPLEMENTS| FILE_tick_orchestrator_py
    ADR-47 -->|IMPLEMENTS| FILE_game_loop___init___py
    ADR-47 -->|DEFINES| LAW_L3
    ADR-311 -->|IMPLEMENTS| FILE_life_engine_py
    ADR-311 -->|IMPLEMENTS| FILE_tick_orchestrator_py
    ADR-311 -->|IMPLEMENTS| FILE_game_loop___init___py
    ADR-311 -->|DEFINES| LAW_L3
    ADR-O-308 -->|IMPLEMENTS| FILE_dm_router_py
    ADR-O-308 -->|IMPLEMENTS| FILE_intent_compressor_py
    ADR-O-308 -->|IMPLEMENTS| FILE_errors_py
    ADR-O-308 -->|DEFINES| LAW_L4
    ADR-159 -->|IMPLEMENTS| FILE_game_loop___init___py
    ADR-159 -->|IMPLEMENTS| FILE_input_intent_compressor_py
    ADR-159 -->|DEFINES| LAW_L4_1
    ADR-S118 -->|IMPLEMENTS| FILE_game_loop___init___py
    ADR-S118 -->|IMPLEMENTS| FILE_input_intent_compressor_py
    ADR-S118 -->|DEFINES| LAW_L4_1
    ADR-S118 -->|DEFINES| LAW_L4_2
    ADR-S118 -->|DEFINES| LAW_L7_1
    ADR-S118 -->|DEFINES| LAW_L12_1
    ADR-161 -->|IMPLEMENTS| FILE_game_loop___init___py
    ADR-161 -->|IMPLEMENTS| FILE_api_routes_py
    ADR-161 -->|DEFINES| LAW_L4_2
    ADR-31 -->|IMPLEMENTS| FILE_will_py
    ADR-31 -->|IMPLEMENTS| FILE_decision_hub_py
    ADR-31 -->|IMPLEMENTS| FILE_life_engine_py
    ADR-31 -->|IMPLEMENTS| FILE_affect_py
    ADR-31 -->|DEFINES| LAW_L5
    ADR-36 -->|IMPLEMENTS| FILE_will_py
    ADR-36 -->|IMPLEMENTS| FILE_decision_hub_py
    ADR-36 -->|IMPLEMENTS| FILE_life_engine_py
    ADR-36 -->|IMPLEMENTS| FILE_affect_py
    ADR-36 -->|DEFINES| LAW_L5
    ADR-88 -->|IMPLEMENTS| FILE_will_py
    ADR-88 -->|IMPLEMENTS| FILE_decision_hub_py
    ADR-88 -->|IMPLEMENTS| FILE_life_engine_py
    ADR-88 -->|IMPLEMENTS| FILE_affect_py
    ADR-88 -->|DEFINES| LAW_L5
    ADR-O-146 -->|IMPLEMENTS| FILE_will_py
    ADR-O-146 -->|IMPLEMENTS| FILE_decision_hub_py
    ADR-O-146 -->|IMPLEMENTS| FILE_life_engine_py
    ADR-O-146 -->|IMPLEMENTS| FILE_affect_py
    ADR-O-146 -->|DEFINES| LAW_L5
    ADR-149 -->|IMPLEMENTS| FILE_will_py
    ADR-149 -->|IMPLEMENTS| FILE_decision_hub_py
    ADR-149 -->|IMPLEMENTS| FILE_life_engine_py
    ADR-149 -->|IMPLEMENTS| FILE_affect_py
    ADR-149 -->|DEFINES| LAW_L5
    ADR-S93_2 -->|IMPLEMENTS| FILE_expectation_store_py
    ADR-S93_2 -->|IMPLEMENTS| FILE_pe_modifier_resolver_py
    ADR-S93_2 -->|IMPLEMENTS| FILE_rules_subscriber_py
    ADR-S93_2 -->|DEFINES| LAW_L6
    ADR-TZ08-3 -->|IMPLEMENTS| FILE_expectation_store_py
    ADR-TZ08-3 -->|IMPLEMENTS| FILE_pe_modifier_resolver_py
    ADR-TZ08-3 -->|IMPLEMENTS| FILE_rules_subscriber_py
    ADR-TZ08-3 -->|DEFINES| LAW_L6
    ADR-152 -->|IMPLEMENTS| FILE_expectation_store_py
    ADR-152 -->|IMPLEMENTS| FILE_pe_modifier_resolver_py
    ADR-152 -->|IMPLEMENTS| FILE_rules_subscriber_py
    ADR-152 -->|DEFINES| LAW_L6
    ADR-TZ05-1 -->|IMPLEMENTS| FILE_game_loop_task_scheduler_py
    ADR-TZ05-1 -->|IMPLEMENTS| FILE_dm_agent_py
    ADR-TZ05-1 -->|IMPLEMENTS| FILE_verbal_stance_py
    ADR-TZ05-1 -->|IMPLEMENTS| FILE_npc_tick_pipeline_py
    ADR-TZ05-1 -->|DEFINES| LAW_L7
    ADR-TZ08-7 -->|IMPLEMENTS| FILE_game_loop_task_scheduler_py
    ADR-TZ08-7 -->|IMPLEMENTS| FILE_dm_agent_py
    ADR-TZ08-7 -->|IMPLEMENTS| FILE_verbal_stance_py
    ADR-TZ08-7 -->|IMPLEMENTS| FILE_npc_tick_pipeline_py
    ADR-TZ08-7 -->|DEFINES| LAW_L7
    ADR-O-313 -->|IMPLEMENTS| FILE_game_loop_task_scheduler_py
    ADR-O-313 -->|IMPLEMENTS| FILE_dm_agent_py
    ADR-O-313 -->|IMPLEMENTS| FILE_verbal_stance_py
    ADR-O-313 -->|IMPLEMENTS| FILE_npc_tick_pipeline_py
    ADR-O-313 -->|DEFINES| LAW_L7
    ADR-163 -->|IMPLEMENTS| FILE_services_npc_decision_hub_py
    ADR-163 -->|IMPLEMENTS| FILE_life_engine_py
    ADR-163 -->|DEFINES| LAW_L7_1
    ADR-165 -->|IMPLEMENTS| FILE_services_npc_decision_hub_py
    ADR-165 -->|IMPLEMENTS| FILE_life_engine_py
    ADR-165 -->|DEFINES| LAW_L7_1
    ADR-25 -->|IMPLEMENTS| FILE_local_causal_solver_py
    ADR-25 -->|IMPLEMENTS| FILE_perceptual_kernel_py
    ADR-25 -->|IMPLEMENTS| FILE_behavior_manifestation_service_py
    ADR-25 -->|DEFINES| LAW_L8
    ADR-O-139 -->|IMPLEMENTS| FILE_local_causal_solver_py
    ADR-O-139 -->|IMPLEMENTS| FILE_perceptual_kernel_py
    ADR-O-139 -->|IMPLEMENTS| FILE_behavior_manifestation_service_py
    ADR-O-139 -->|DEFINES| LAW_L8
    ADR-O-143 -->|IMPLEMENTS| FILE_local_causal_solver_py
    ADR-O-143 -->|IMPLEMENTS| FILE_perceptual_kernel_py
    ADR-O-143 -->|IMPLEMENTS| FILE_behavior_manifestation_service_py
    ADR-O-143 -->|DEFINES| LAW_L8
    ADR-O-147 -->|IMPLEMENTS| FILE_local_causal_solver_py
    ADR-O-147 -->|IMPLEMENTS| FILE_perceptual_kernel_py
    ADR-O-147 -->|IMPLEMENTS| FILE_behavior_manifestation_service_py
    ADR-O-147 -->|DEFINES| LAW_L8
    ADR-O-147 -->|DEFINES| LAW_L16
    ADR-8 -->|IMPLEMENTS| FILE_spatial_factory_py
    ADR-8 -->|IMPLEMENTS| FILE_spatial_query_service_py
    ADR-8 -->|IMPLEMENTS| FILE_domain_movement_py
    ADR-8 -->|DEFINES| LAW_L9
    ADR-48 -->|IMPLEMENTS| FILE_spatial_factory_py
    ADR-48 -->|IMPLEMENTS| FILE_spatial_query_service_py
    ADR-48 -->|IMPLEMENTS| FILE_domain_movement_py
    ADR-48 -->|DEFINES| LAW_L9
    ADR-S82_0 -->|IMPLEMENTS| FILE_spatial_factory_py
    ADR-S82_0 -->|IMPLEMENTS| FILE_spatial_query_service_py
    ADR-S82_0 -->|IMPLEMENTS| FILE_domain_movement_py
    ADR-S82_0 -->|DEFINES| LAW_L9
    ADR-TZ04-4 -->|IMPLEMENTS| FILE_spatial_factory_py
    ADR-TZ04-4 -->|IMPLEMENTS| FILE_spatial_query_service_py
    ADR-TZ04-4 -->|IMPLEMENTS| FILE_domain_movement_py
    ADR-TZ04-4 -->|DEFINES| LAW_L9
    ADR-O-314 -->|IMPLEMENTS| FILE_spatial_factory_py
    ADR-O-314 -->|IMPLEMENTS| FILE_spatial_query_service_py
    ADR-O-314 -->|IMPLEMENTS| FILE_domain_movement_py
    ADR-O-314 -->|DEFINES| LAW_L9
    ADR-TRAV-FSM -->|IMPLEMENTS| FILE_scene_state_manager_py
    ADR-TRAV-FSM -->|IMPLEMENTS| FILE_movement_engine_py
    ADR-TRAV-FSM -->|IMPLEMENTS| FILE_event_compiler_py
    ADR-TRAV-FSM -->|DEFINES| LAW_L10
    ADR-130_1_2 -->|IMPLEMENTS| FILE_scene_state_manager_py
    ADR-130_1_2 -->|IMPLEMENTS| FILE_movement_engine_py
    ADR-130_1_2 -->|IMPLEMENTS| FILE_event_compiler_py
    ADR-130_1_2 -->|DEFINES| LAW_L10
    ADR-S90_4 -->|IMPLEMENTS| FILE_scene_state_manager_py
    ADR-S90_4 -->|IMPLEMENTS| FILE_movement_engine_py
    ADR-S90_4 -->|IMPLEMENTS| FILE_event_compiler_py
    ADR-S90_4 -->|DEFINES| LAW_L10
    ADR-O-330 -->|DEFINES| LAW_L11_1
    ADR-S90_1 -->|IMPLEMENTS| FILE_motion_pipeline_py
    ADR-S90_1 -->|IMPLEMENTS| FILE_world_topology_provider_py
    ADR-S90_1 -->|IMPLEMENTS| FILE_motion_core_py
    ADR-S90_1 -->|DEFINES| LAW_L11
    ADR-S91 -->|IMPLEMENTS| FILE_motion_pipeline_py
    ADR-S91 -->|IMPLEMENTS| FILE_world_topology_provider_py
    ADR-S91 -->|IMPLEMENTS| FILE_motion_core_py
    ADR-S91 -->|DEFINES| LAW_L11
    ADR-O-324 -->|IMPLEMENTS| FILE_motion_pipeline_py
    ADR-O-324 -->|IMPLEMENTS| FILE_world_topology_provider_py
    ADR-O-324 -->|IMPLEMENTS| FILE_motion_core_py
    ADR-O-324 -->|DEFINES| LAW_L11
    ADR-O-329 -->|IMPLEMENTS| FILE_motion_pipeline_py
    ADR-O-329 -->|IMPLEMENTS| FILE_world_topology_provider_py
    ADR-O-329 -->|IMPLEMENTS| FILE_motion_core_py
    ADR-O-329 -->|DEFINES| LAW_L11
    ADR-15 -->|IMPLEMENTS| FILE_vital_state_py
    ADR-15 -->|IMPLEMENTS| FILE_impact_engine_py
    ADR-15 -->|IMPLEMENTS| FILE_state_applicator_py
    ADR-15 -->|IMPLEMENTS| FILE_combat_math_py
    ADR-15 -->|DEFINES| LAW_L12
    ADR-123 -->|IMPLEMENTS| FILE_vital_state_py
    ADR-123 -->|IMPLEMENTS| FILE_impact_engine_py
    ADR-123 -->|IMPLEMENTS| FILE_state_applicator_py
    ADR-123 -->|IMPLEMENTS| FILE_combat_math_py
    ADR-123 -->|DEFINES| LAW_L12
    ADR-127 -->|IMPLEMENTS| FILE_vital_state_py
    ADR-127 -->|IMPLEMENTS| FILE_impact_engine_py
    ADR-127 -->|IMPLEMENTS| FILE_state_applicator_py
    ADR-127 -->|IMPLEMENTS| FILE_combat_math_py
    ADR-127 -->|DEFINES| LAW_L12
    ADR-HP-UNIFICATION -->|IMPLEMENTS| FILE_vital_state_py
    ADR-HP-UNIFICATION -->|IMPLEMENTS| FILE_impact_engine_py
    ADR-HP-UNIFICATION -->|IMPLEMENTS| FILE_state_applicator_py
    ADR-HP-UNIFICATION -->|IMPLEMENTS| FILE_combat_math_py
    ADR-HP-UNIFICATION -->|DEFINES| LAW_L12
    ADR-164 -->|IMPLEMENTS| FILE_services_combat_impact_engine_py
    ADR-164 -->|IMPLEMENTS| FILE_combat_math_py
    ADR-164 -->|DEFINES| LAW_L12_1
    ADR-121 -->|IMPLEMENTS| FILE_relationship_store_py
    ADR-121 -->|IMPLEMENTS| FILE_affective_integrator_py
    ADR-121 -->|IMPLEMENTS| FILE_state_applicator_py
    ADR-121 -->|DEFINES| LAW_L13
    ADR-138 -->|IMPLEMENTS| FILE_relationship_store_py
    ADR-138 -->|IMPLEMENTS| FILE_affective_integrator_py
    ADR-138 -->|IMPLEMENTS| FILE_state_applicator_py
    ADR-138 -->|DEFINES| LAW_L13
    ADR-O-206 -->|IMPLEMENTS| FILE_relationship_store_py
    ADR-O-206 -->|IMPLEMENTS| FILE_affective_integrator_py
    ADR-O-206 -->|IMPLEMENTS| FILE_state_applicator_py
    ADR-O-206 -->|DEFINES| LAW_L13
    ADR-S96_2 -->|IMPLEMENTS| FILE_relationship_store_py
    ADR-S96_2 -->|IMPLEMENTS| FILE_affective_integrator_py
    ADR-S96_2 -->|IMPLEMENTS| FILE_state_applicator_py
    ADR-S96_2 -->|DEFINES| LAW_L13
    ADR-S86_7 -->|IMPLEMENTS| FILE_memory_manager_py
    ADR-S86_7 -->|IMPLEMENTS| FILE_state_applicator_py
    ADR-S86_7 -->|IMPLEMENTS| FILE_pipeline_runner_py
    ADR-S86_7 -->|DEFINES| LAW_L14
    ADR-O-325 -->|IMPLEMENTS| FILE_memory_manager_py
    ADR-O-325 -->|IMPLEMENTS| FILE_state_applicator_py
    ADR-O-325 -->|IMPLEMENTS| FILE_pipeline_runner_py
    ADR-O-325 -->|DEFINES| LAW_L14
    ADR-TZ03-1 -->|IMPLEMENTS| FILE_frontend_api_client_py
    ADR-TZ03-1 -->|IMPLEMENTS| FILE_game_screen_py
    ADR-TZ03-1 -->|IMPLEMENTS| FILE_scene_renderer_py
    ADR-TZ03-1 -->|DEFINES| LAW_L15
    ADR-156 -->|IMPLEMENTS| FILE_frontend_api_client_py
    ADR-156 -->|IMPLEMENTS| FILE_game_screen_py
    ADR-156 -->|IMPLEMENTS| FILE_scene_renderer_py
    ADR-156 -->|DEFINES| LAW_L15
    ADR-MANIFEST -->|IMPLEMENTS| FILE_frontend_api_client_py
    ADR-MANIFEST -->|IMPLEMENTS| FILE_game_screen_py
    ADR-MANIFEST -->|IMPLEMENTS| FILE_scene_renderer_py
    ADR-MANIFEST -->|DEFINES| LAW_L15
    ADR-TZ08-4_6 -->|IMPLEMENTS| FILE_agents_dm_agent_py
    ADR-TZ08-4_6 -->|IMPLEMENTS| FILE_scene_r3_direct_builder_py
    ADR-TZ08-4_6 -->|IMPLEMENTS| FILE_world_projection_buffer_py
    ADR-TZ08-4_6 -->|DEFINES| LAW_L16
    ADR-93 -->|IMPLEMENTS| FILE_agents_dm_agent_py
    ADR-93 -->|IMPLEMENTS| FILE_scene_r3_direct_builder_py
    ADR-93 -->|IMPLEMENTS| FILE_world_projection_buffer_py
    ADR-93 -->|DEFINES| LAW_L16
    ADR-O-331 -->|IMPLEMENTS| FILE_domain_body_py
    ADR-O-331 -->|IMPLEMENTS| FILE_domain_presentation_py
    ADR-O-331 -->|IMPLEMENTS| FILE_services_body_body_topology_service_py
    ADR-O-331 -->|IMPLEMENTS| FILE_services_perception_presentation_assembler_py
    ADR-O-331 -->|DEFINES| LAW_L16_1
    ADR-S147 -->|IMPLEMENTS| FILE_domain_body_py
    ADR-S147 -->|IMPLEMENTS| FILE_domain_presentation_py
    ADR-S147 -->|IMPLEMENTS| FILE_services_body_body_topology_service_py
    ADR-S147 -->|IMPLEMENTS| FILE_services_perception_presentation_assembler_py
    ADR-S147 -->|DEFINES| LAW_L16_1
    ADR-O-208 -->|IMPLEMENTS| FILE_l1_chronicle_py
    ADR-O-208 -->|IMPLEMENTS| FILE_drive_resolver_py
    ADR-O-208 -->|IMPLEMENTS| FILE_calibration_engine_py
    ADR-O-208 -->|DEFINES| LAW_L17
    ADR-211 -->|IMPLEMENTS| FILE_l1_chronicle_py
    ADR-211 -->|IMPLEMENTS| FILE_drive_resolver_py
    ADR-211 -->|IMPLEMENTS| FILE_calibration_engine_py
    ADR-211 -->|DEFINES| LAW_L17
    ADR-TIFL-001 -->|IMPLEMENTS| FILE_l1_chronicle_py
    ADR-TIFL-001 -->|IMPLEMENTS| FILE_drive_resolver_py
    ADR-TIFL-001 -->|IMPLEMENTS| FILE_calibration_engine_py
    ADR-TIFL-001 -->|DEFINES| LAW_L17
    ADR-O-305 -->|IMPLEMENTS| FILE_pattern_detector_py
    ADR-O-305 -->|IMPLEMENTS| FILE_belief_crystallization_engine_py
    ADR-O-305 -->|IMPLEMENTS| FILE_crystallized_belief_store_py
    ADR-O-305 -->|DEFINES| LAW_L18
    ADR-306 -->|IMPLEMENTS| FILE_pattern_detector_py
    ADR-306 -->|IMPLEMENTS| FILE_belief_crystallization_engine_py
    ADR-306 -->|IMPLEMENTS| FILE_crystallized_belief_store_py
    ADR-306 -->|DEFINES| LAW_L18
    ADR-307 -->|IMPLEMENTS| FILE_pattern_detector_py
    ADR-307 -->|IMPLEMENTS| FILE_belief_crystallization_engine_py
    ADR-307 -->|IMPLEMENTS| FILE_crystallized_belief_store_py
    ADR-307 -->|DEFINES| LAW_L18
    ADR-O-312 -->|IMPLEMENTS| FILE_homeostasis_projector_py
    ADR-O-312 -->|IMPLEMENTS| FILE_domain_execution_py
    ADR-O-312 -->|IMPLEMENTS| FILE_task_scheduler_py
    ADR-O-312 -->|DEFINES| LAW_L19
    ADR-313 -->|IMPLEMENTS| FILE_homeostasis_projector_py
    ADR-313 -->|IMPLEMENTS| FILE_domain_execution_py
    ADR-313 -->|IMPLEMENTS| FILE_task_scheduler_py
    ADR-313 -->|DEFINES| LAW_L19
    ADR-O-315 -->|IMPLEMENTS| FILE_npc_state_py
    ADR-O-315 -->|IMPLEMENTS| FILE_life_project_resolver_py
    ADR-O-315 -->|IMPLEMENTS| FILE_break_progress_engine_py
    ADR-O-315 -->|IMPLEMENTS| FILE_docs_ENTITY_CONTINUITY_CONTRACT_md
    ADR-O-315 -->|DEFINES| LAW_L20
    ADR-316 -->|IMPLEMENTS| FILE_npc_state_py
    ADR-316 -->|IMPLEMENTS| FILE_life_project_resolver_py
    ADR-316 -->|IMPLEMENTS| FILE_break_progress_engine_py
    ADR-316 -->|IMPLEMENTS| FILE_docs_ENTITY_CONTINUITY_CONTRACT_md
    ADR-316 -->|DEFINES| LAW_L20
    ADR-317 -->|IMPLEMENTS| FILE_npc_state_py
    ADR-317 -->|IMPLEMENTS| FILE_life_project_resolver_py
    ADR-317 -->|IMPLEMENTS| FILE_break_progress_engine_py
    ADR-317 -->|IMPLEMENTS| FILE_docs_ENTITY_CONTINUITY_CONTRACT_md
    ADR-317 -->|DEFINES| LAW_L20
    ADR-320 -->|IMPLEMENTS| FILE_npc_state_py
    ADR-320 -->|IMPLEMENTS| FILE_life_project_resolver_py
    ADR-320 -->|IMPLEMENTS| FILE_break_progress_engine_py
    ADR-320 -->|IMPLEMENTS| FILE_docs_ENTITY_CONTINUITY_CONTRACT_md
    ADR-320 -->|DEFINES| LAW_L20
    ADR-321 -->|IMPLEMENTS| FILE_npc_state_py
    ADR-321 -->|IMPLEMENTS| FILE_life_project_resolver_py
    ADR-321 -->|IMPLEMENTS| FILE_break_progress_engine_py
    ADR-321 -->|IMPLEMENTS| FILE_docs_ENTITY_CONTINUITY_CONTRACT_md
    ADR-321 -->|DEFINES| LAW_L20
    ADR-INV-DEF -->|IMPLEMENTS| FILE_backend_tests_IPT_py
    ADR-INV-DEF -->|IMPLEMENTS| FILE_diagnostics_invariant_health_py
    ADR-INV-DEF -->|IMPLEMENTS| FILE_ruff_toml
    ADR-INV-DEF -->|DEFINES| LAW_L21
    ADR-IMMUNE-001 -->|IMPLEMENTS| FILE_backend_tests_IPT_py
    ADR-IMMUNE-001 -->|IMPLEMENTS| FILE_diagnostics_invariant_health_py
    ADR-IMMUNE-001 -->|IMPLEMENTS| FILE_ruff_toml
    ADR-IMMUNE-001 -->|DEFINES| LAW_L21
```
