# DEGOD PHASE-0 MAP — scene_state_manager.py

> **Статус:** Phase-0 working map (снимок исходного состояния, НЕ нормативный runtime-контракт).
> **Свежесть:** чтение 2026-09-21/22, файл 2427 строки, все порции прочитаны целиком.

## BASELINES
- mypy: 4 диагностики (:384, :494 unreachable; :1573 no-untyped-def; :1749 assignment).
- ruff: 2×F841 (unused-variable).
- DriftLab-паспорт: общий с game_loop (см. DEGOD_S3_ITER1_DOSSIER.md), hash 442346bab1e0c1ae...

## FACT (обнаружено)
### Responsibility clusters (fresh anchors)
| # | Кластер | Anchor | Роль |
|---|---------|---|---|
| S1 | Module surface + logging | :1–96 | импорты, _DATA_DIR/_LOG_DIR globals, _scene_log_file, _log_change (fsync-журнал, LOG-GATE) |
| S2 | ChangeValidator | :103–142 | чистая валидация SceneChange |
| S3 | Environment derivation | :145–188 | _NOISE_MAP/_LIGHT_MAP/_TYPE_MODIFIERS + _derive_environment_modifiers (pure) |
| S4 | Constructor + tick-scoped identity | :213–235 | _persistence, _life_engine, _templates_cache, _tick_locked/_tick_campaign_id/_tick_scenes |
| S5 | Tick-lock / commit-API | :239–358 | lock_for_tick, lock_all_for_tick, unlock_tick (atomic_commit_all + _sync_relationship_directed + _confirm_v2_migration), commit_tick_result (EPOCH-гейт :337) |
| S6 | Rehydrate (дубль) | :360–527 | get_scene_state_uncached / get_scene_state — почти идентичная сборка + SC-3 reset + caller-inspect (:475–486) |
| S7 | Spatial enrichment вход | :529–540 | _enrich_spatial_data |
| S8 | Strip-гварды | :546–587 | _strip_foreign_npcs, _strip_husk_npcs (static) |
| S9 | Save / tick-cache routing | :589–621 | save_scene_state: locked→кэш, unlocked→atomic_commit_all |
| S10 | Player target / NPC context | :627–767 | update_player_target (ADR-048-гейт), build_npc_context_block (static pure) |
| S11 | Editor-JSON локатор | :788–944 | _find_editor_location, _find_first_editor_location, find_starting_location, _build_spatial_data (делегат graph_compiler), _nearest_node_to_xy; search_dirs дублируется трижды |
| S12 | Scene factory | :949–1215 | initialize_scene (~240 строк: editor/template, детерминированный RNG md5-seed :1065/:1104, каноническая топология ключей :1121–1168, W3-spawn :1170–1180), _select_time_variant (static pure) |
| S13 | Change application | :1221–1542 | validate_change, apply_change (~270 строк: ATOMIC-GUARD :1287–1298, stale-proposal :1374–1381, SLEEP_FIX :1391–1400, S203.1 fallback-зеркало :1409–1416, MISSING_PROPOSAL :1417–1425, INVENTORY/EFFECT), apply_changes + gc (:1537) |
| S14 | Traversal GC | :1544–1567 | gc_traversals — единственный GC-владелец (Ц1, ADR-O-363) |
| S15 | R2.1 narrative | :1573–1652, :1757–1826 | apply_narrative_extractions (TEXT→ENTITY блокирован), get_scene_events_block (static pure), prune_dynamic_objects |
| S16 | EPOCH-FINAL commit | :1658–1750 | commit (EPOCH-гейт :1717–1720, несущий deepcopy S266-ОТКАТ, _last_committed_npcs ленивость S269-C2), get_last_committed_npcs |
| S17 | GAP12 enrichment | :1832–2071 | _enrich_local_positions (S273 root-cause fix, in_transit-only :1951, TES — единственный владелец производной; _spatial_enforcement_logged dedup :2033–2040) |
| S18 | NPC position update | :2073–2121 | update_npc_position + SpatialFactory-синхронизация |
| S19 | DM presentation | :2128–2313 | get_scene_description (~185 строк, static pure) |
| S20 | RE-синхронизация | :2316–2352 | _sync_relationship_directed, _confirm_v2_migration (M1b.4.2) |
| S21 | Module helpers + singleton | :2355–2427 | enrich_scene_spatial, _NPC_NAME_CACHE/_npc_id_to_display, get_scene_state_manager |

### State ownership
- intra: _persistence (DI), _life_engine (DI), _templates_cache, _tick_locked/_tick_campaign_id/_tick_scenes, _last_committed_npcs(_src) (консюмер WorldProjectionBuffer ОТКЛЮЧЁН — VERDICT=OFF), _spatial_enforcement_logged.
- **Скрытая связка:** _spatial_enforcement_logged пишется в S17 (:2033–2040) и сбрасывается в S16.commit (:1667–1668).
- module globals: _NPC_NAME_CACHE (+_NPC_NAME_CACHE_LOADED), _scene_state_manager (singleton), _DATA_DIR/_LOG_DIR.

### Call-site surface (grep-верифицировано, 2026-09-22)
- singleton get_scene_state_manager: world_routes.py, event_compiler.py.
- _npc_id_to_display: dm_agent.py:264/278/280, recognition_layer.py:13/21/170, diagnose_spatial.py:50/53/54 — ТРИ внешних домена.
- _derive_environment_modifiers: внешний test-import test_spatial_runtime_r4.py:10 (+тесты :82/:172, позиционная сигнатура (tv, "dungeon")).
- GameLoop мутирует internals: _tick_scenes/_tick_locked/_tick_campaign_id (game_loop :2439–2441), читает _tick_scenes (:1530, :1809), _persistence (:710, :2560, :2878).

## CONTRACT (обязано сохраниться)
1. TICK-SCOPED IDENTITY: lock → один dict для всех читателей; unlock persist 1 раз (INV-COMMIT-CARDINALITY); кэш не очищается до следующего lock (SSE-bridge).
2. EPOCH-гейты (:337, :1717): env OFF = несущий deepcopy (Temporal Isolation L4) — deepcopy не удалять до PR-5.
3. ATOMIC-GUARD (:1287): torn-write отказ.
4. Зеркало материализации — ровно 2 точки (ADR-O-363): ProjectionEngine primary / SSM fallback :1409. Не создавать/не удалять третью.
5. GAP12: xy при MOVING не пишется; TES — единственный владелец производной; in_transit — живой потребитель behavior_manifestation_service:154.
6. GC-владелец единственный (Ц1): SSM.gc_traversals.
7. RNG-детерминизм initialize_scene: md5-seed строка (location_id:obj_id) не менять.
8. Каноническая топология ключей scene_state (:1121–1168) — Foundation Freeze.
9. M1b.4.2: directed-синхронизация ДО транзакции, маркер ПОСЛЕ успешного коммита.
10. _log_change: fsync + LOG-GATE.
11. _last_committed_npcs: ленивость геттера — перф-контракт S269-C2, не «упрощать» до eager.
12. _derive_environment_modifiers: re-export при любом переносе; позиционная сигнатура (tv, "dungeon") не меняется; call-site initialize_scene :1138 не меняется.

## CANDIDATE (не решения)
- S3 environment derivation → candidate `scene_state/environment_modifiers.py` — **ПЕРВЫЙ EXTRACTION (утверждён Мастером)**.
- S2 ChangeValidator → второй leaf (после S3; внешних импортов нет — проверено grep).
- S10+S15-блок+S19 pure presentation → candidate `scene_state/dm_presentation.py` — требует решения: проекция SSM или будущий Verbalization-слой (преждевременная граница недопустима).
- S11 editor-locator → candidate, требует проверки дублирования с SpatialFactory/GraphCompiler.
- S12 initialize_scene → candidate `scene_state/scene_factory.py` — спорный, только после межфайлового вердикта.
- S21 _npc_id_to_display → cross-file helper (dm_agent/recognition_layer/diagnose_spatial); естественный владелец ВНЕ SSM, но перенос = отдельный ownership-рефакторинг вне этой ветки; SSM — временный хозяин; при любом будущем переносе — только re-export.

## STOP (запрещено трогать)
- S4/S5 (tick-identity + lock API), S9 (write-path), S13 (causal authority: ATOMIC-GUARD/stale/SLEEP_FIX/зеркало/MISSING_PROPOSAL), S14 (Ц1), **S16 EPOCH-FINAL (:1658/:1717–1720/:1725 — табу ТЗ)**, **S17 GAP12 (S273-операция соседа + dedup↔commit связка)**, **S20 RE-зона (M1b.4.2)**, singleton.
- S6 rehydrate: DRY-унификация ЗАПРЕЩЕНА (различия не доказаны несущественными; observation).

## OBSERVATION
1. Rehydrate-дубль S6 (различия не каталогизированы).
2. Caller-inspect диагностика :475–486.
3. Двойной setattr :1748–1749 в get_last_committed_npcs (mypy :1749 assignment; SceneStateManager без __slots__).
4. enrich_scene_spatial :2355 создаёт голый SSM без persistence.
5. Трижды дублированный search_dirs в S11.
6. position_map хардкод-лейблы в get_scene_description (:2230–2240) — вопрос контент-канона.
7. Мёртвый консюмер _last_committed_npcs (VERDICT=OFF, _SHADOW_CAUSALITY_DISABLED).

## МЕЖФАЙЛОВОЙ OWNERSHIP BRIDGE (приоритет выше карт отдельных файлов)
**_tick_scenes / _tick_locked / _tick_campaign_id / _persistence — CROSS-FILE OWNERSHIP BRIDGE / RED.**
SSM формально владеет структурой; GameLoop пишет/читает напрямую (3 контура: G11 _prepare_and_lock_scene, G8 idle, G9 run_turn, G4 new_game, G14 dispose).
Следствие (вердикт Мастера §2/§5): GameLoop и SSM нельзя дегодифицировать независимо; extraction идёт от доказанной границы владельца, не от списка модулей; отсутствие extraction вокруг этого состояния — корректный результат Phase-0, не долг.
