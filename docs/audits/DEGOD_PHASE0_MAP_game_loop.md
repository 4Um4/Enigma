# DEGOD PHASE-0 MAP — game_loop/__init__.py

> **Статус:** Phase-0 working map (снимок исходного состояния, НЕ нормативный runtime-контракт).
> **Свежесть:** чтение 2026-09-21/22, файл 2902 строки, все порции прочитаны целиком.
> **Контекст ветки:** V.0.5.4.1.1_дрифтуем_во_сне, HEAD da231859 (S273 WATERMARK).
> **Историческая ветка ТЗ** (V.0.5.4.1.0_КросЛокация) ≠ фактическая — observation.

## BASELINES
- mypy: 76 диагностик в файле (~30 no-untyped-call, ~11 union-attr, ~10 unreachable, ~5 attr-defined, 2 has-type, точечные assignment/return-value/call-arg/var-annotated). Полный список — в досье сессии.
- ruff: 14×F401 (unused-import) + 1×W291.
- DriftLab-паспорт (Mode E replay_determinism, 2×800, DRIFT_TICKS=800, seed 54321): **hash 442346bab1e0c1ae0508599c9469d7286d8df47dbd4c8a8887ac9125361b8887**, MATCH×2, межпроцессная воспроизводимость подтверждена. Досье: DEGOD_S3_ITER1_DOSSIER.md.

## FACT (обнаружено)
### Responsibility clusters (fresh anchors)
| # | Кластер | Anchor | Роль |
|---|---------|---|---|
| G1 | Module surface | :1–138 | импорты, re-exports (run_dm_phase, run_npc_orchestration, phase_1_input, tick_context, _TickContext alias), R3_DIRECT_MODE, _PipelineState, _e1_extract_subject |
| G2 | Constructor wiring | :148–371 | DI 13 зависимостей; M1b.4.2 v2-cutover + late-bind npc_provider; ServiceFactory (_svc :241); TickOrchestrator-DI :243–260; set_epistemic_wiring :272–284; replay :287–305; rel_store/state_applicator :308–332; idle-handlers :349–365; TimeSkipExecutor :368–370 |
| G3 | Subscriber registration | :372–619 | _get_spatial_query_for_subscriber (fallback-конструирование + мутация self._current_spatial_query :399), _on_npc_spoke_economy_tracker, _register_npc_dialogue_subscriber (5 self-capturing лямбд, pool_provider :448–450 → self._get_task_scheduler()._executor_pool), _register_epistemic_core (ClaimEvent/Observation/BC1-restore/ACCUSE-инъекция) |
| G4 | Campaign lifecycle | :621–943 | _get_skip_lock, saves_dir, get_current_tick, diff-to/from-disk (:638–676), new_game (:679–937, 12 шагов сброса), reset_session_flag |
| G5 | NPC resolution helpers | :945–1005, :1020–1122 | _get_life_engine, _resolve_npcs_snapshot/_light (thin wrappers над LifeEngine), _e1_relationship_reader, _project_perception (stateless), _load_npcs_with_runtime (~100 строк: кэш→фильтр→сессия→player_dict ADR-030/035→body_state-страховка) |
| G6 | Time-skip | :1124–1250 | skip_time: lock→SpatialFactory→NpcTickServices→TimeSkipExecutor→snapshot→commit_tick_result; мутит _current_spatial_query :1152/:1160 |
| G7 | E.2-фасад | :1253–1300 | делегаты apply_changes/get_scene_state/find_starting_location/list_characters + B1.4-RECEIVER save_scene_state (:1261–1292, whitelist-контракт) |
| G8 | Idle-контур | :1302–1614 | idle_tick (~313 строк): локационная сборка, FIX-RC1 cross-location ensure (:1374–1393), Spatial Oracle (:1404–1423), fresh _idle_ctx (S259 :1447–1454), execute() (:1475–1495), epistemic-persist (:1501–1503), HOT-кэш (:1505–1516), чтение scene_manager._tick_scenes (:1530), execute_pending + 2×drain (:1554/:1559/:1564), WS-конвертация, unlock (:1604) |
| G9 | Turn REST | :1616–1898 | run_turn: DM-recovery (:1680–1711, содержит вызов несуществующего _run_dm :1689), RCE (:1716–1751), R2.1 (:1754–1775), player_recognition pre-commit (:1781–1788), commit_tick_result (:1793), execute_pending+drain_commitment (:1815–1819), WS+journal, unlock (:1850) |
| G10 | Turn SSE | :1900–2072 | stream_turn — зеркало run_turn |
| G11 | Turn-подсборки | :2074–2716 | _sync_shared_context_with_scene (мутирует self._current_tick :2089), _finalize_pipeline_and_build_dm_frame (:2091–2252: Rules-редьюсер, economic delta через StateApplicator, AvatarStateApplicator S208, R3-frame), _execute_dm_and_intent_resolution (:2254–2410: intent compressor, SOCIAL_ACTION publish, MOVE→MacroMovementGoal, MVP-bridge), _prepare_and_lock_scene (:2412–2451, ПРЯМАЯ ЗАПИСЬ SSM._tick_scenes/_tick_locked/_tick_campaign_id :2439–2441), _load_player_avatar (:2453–2579, DEATH-GATE + BodyTopology-init), _init_pipeline_context (:2581–2623, _background_tasks), _run_pipeline (:2625–2716, склейка фаз) |
| G12 | Lazy-factory + утилиты | :2722–2772 | _get_task_scheduler (lazy, 7 инъекций), _get_character_dict, _build_traces, assert_requirements |
| G13 | Campaign mgmt | :2774–2845 | load_campaign, session_state (мёртвый хвост :2833–2835), _resolve_world_id |
| G14 | Dispose + quiesce | :2847–2902 | dispose: S269-quiesce (stop-produce→drain executor) → persistence.close → memory store.close → spatial release → loader kill |

### State ownership
- intra-класс: _svc, _tick_orch, _rel_store, _skip_locks, _task_scheduler (lazy), _session_started_campaigns, _campaign_diffs/_diffs_path, _background_tasks (lazy :2596), _preserved_tick (lazy, читается scene_init вне файла), _narrative_projector, _intent_compressor, _world_tick_engine, _time_skip, _campaign_world_index, mvp_controller.
- **SHARED MUTABLE (3 контура):** _current_spatial_query — пишется в _get_spatial_query_for_subscriber :399, skip_time :1152/:1160, idle :1432/:1435; читается NpcTickServices :1174/:1468.
- **SHARED MUTABLE (через замыкания):** _current_campaign_id, _current_tick — пишутся new_game :700 / _sync_shared_context_with_scene :2089; читаются 6 wiring-лямбд (tick_provider, npc_states_provider, campaign_id_provider).
- возможно мёртвое: _scene_continuities (:224, записи в файле не найдены).

### Call-site surface (grep-верифицировано, 2026-09-22)
- 22 внешних файла ссылаются на GameLoop (main.py, api/routes*.py, game_loop_builder/accessor, tick_orchestrator, calibration/experiment_runner, time_skip_executor, phases/simulation и др.).
- Публичные методы: idle_tick — routes.py, experiment_runner.py, replay_player.py; run_turn — routes.py; stream_turn — routes_stream.py; new_game — routes.py + life_engine.py (обратная связь соседа); load_campaign/skip_time — routes.py; dispose — experiment_runner.py.
- Тестовые поверхности: smoke_goran_beta, social_vertical, spatial_knowledge_divergence, work_vertical, test_epistemology_pipeline, test_homeostatic_dialogue_stability.
- **_load_npcs_with_runtime — 13 внешних точек:** routes_debug:80, npc_orchestration:83/89/91 (производственный путь), npc_loader:386, harness:168, causal_validation:79, тесты ×7. Метод = часть публичной полуповерхности фасада.

## CONTRACT (обязано сохраниться)
1. Порядок wiring __init__: M1b.4.2 v2-cutover ДО захватов подписчиков; форс _get_task_scheduler() ДО set_epistemic_wiring (:263→:272); epistemic store на оркестраторе ДО relocation-тиков (:342–347).
2. Identity замыканий: все provider-лямбды захватывают self (late-binding); pool_provider возвращает ТОТ ЖЕ executor-пул TaskScheduler (второй execution domain запрещён).
3. Lazy-init _get_task_scheduler: единственный экземпляр, 7 инъекций; INV-DIALOGUE-INIT/SCHEDULER-FAIL зависит от форс-инициализации.
4. O-399 drain-контракт: execute_pending → drain_commitment_outbox → drain_task_worker_outbox, безусловный sync-дренаж ДО unlock_tick (idle :1553–1564; run_turn :1815–1819).
5. Tick-кардианальность: execute() 1 раз; unlock_tick — единственная точка persist; commit_tick_result до дренажа.
6. _current_spatial_query fresh-per-tick: перезапись каждым контуром на входе тика; смерть объекта в конце тика (S259).
7. Exception-поверхность: H-33/H-34 (не маскировать), DEATH-GATE возвращает ранний ChatTurnResponse, INV-SPATIAL-QUERY RuntimeError.
8. Public import surface G1: re-exports run_dm_phase, run_npc_orchestration, publish_classified_player_event, resolve_player_intent, init_scene_state, TickBuffer/TickInput/TickOutput/_TickContext.
9. new_game atomicity: scene+npc в одном commit() (:819–830); порядок сброса 1→12; канон переживает new_game.
10. dispose-порядок: quiesce → persistence.close → memory store.close → spatial release → loader kill; повторный quiesce = no-op.
11. **_run_dm :1689 — мёртвая recovery-ветка (метод не существует нигде). Extraction не имеет права её оживить или изменить.**

## CANDIDATE (потенциально выносимо; имена — candidate target modules, НЕ решения)
- _PipelineState → candidate `pipeline_state.py` (~20 строк, leaf).
- E1-функции (_e1_extract_subject, _e1_relationship_reader) + _project_perception + _build_traces + _get_character_dict + diff-утилиты → candidate leaf-группа.
- load_campaign/_resolve_world_id/session_state/assert_requirements → candidate `campaign_mgmt.py`.
- new_game + diff-утилиты → candidate `campaign_reset.py` — **НЕ УТВЕРЖДЁН** (вердикт Мастера §6: прямой доступ GameLoop к SSM._persistence :710 — отдельный ownership refactor; atomicity-контракт).
- _load_npcs_with_runtime → **DEFERRED** (13 внешних точек; trio GameLoop/npc_orchestration/npc_loader требует отдельного ownership-анализа; предпочтение — параметризованная pure composition, а не новый сервис).
- turn-подсборки (G11) → **turn_subphases.py ЗАПРЕЩЁН** (вердикт Мастера §4): _prepare_and_lock_scene — межфайловой ownership bridge (прямая запись SSM._tick_scenes :2439–2441); остальные четыре метода не связывать автоматически; каждый требует индивидуальной ownership-карты.

## STOP (запрещено трогать в этой ветке)
- __init__ (порядок wiring), G3-регистрации (self-capturing, порядок), idle_tick, run_turn, stream_turn, _run_pipeline (spine), _get_task_scheduler (identity), skip_time, _sync_shared_context_with_scene, _get_spatial_query_for_subscriber, dispose, E.2-делегаты, module re-exports.
- O-399 drain-точки; PATTERN_WATERMARK; Cross-File Ownership Bridge вокруг SSM._tick_scenes/_persistence (см. карту SSM, межфайловый раздел).
- _resolve_npcs_snapshot/light_snapshot — НЕ ВЫНОСИТЬ (вердикт Мастера §3; 11 внешних/тестовых точек — поверхность фасада).

## OBSERVATION (не задачи этой ветки)
1. _run_dm :1689 — вызов несуществующего метода (recovery-ветка run_turn мертва).
2. Дубль R2.1-блока run_turn (:1754–1775) / stream_turn (:2042–2072).
3. Дубль блока «=== 12» в new_game (:840–865 vs :897–924).
4. Мёртвый код после return в session_state (:2833–2835; mypy unreachable).
5. _scene_continuities — возможно мёртвое состояние.
6. tavern-хардкод в _register_epistemic_core (:529/:576; известен по ADR-O-381 оговорке №11).
