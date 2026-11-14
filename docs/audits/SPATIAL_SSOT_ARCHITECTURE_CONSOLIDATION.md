# ENIGMA — Spatial SSOT Architecture Consolidation

**Status:** architecture proposal; not an implementation authorization
**Evidence snapshot:** repository state inspected 2026-11-14
**Scope:** production code paths for scene spatial state, movement, geometry, objects, persistence and restore. No production code, maps, saves, migrations or tests were changed or executed.

**Workspace note — PARTIALLY VERIFIED:** final verification found an unstaged edit in `frontend/game_screen.py` adding `save_scene_state()` calls on quit, pause and D61 exit. It was not made as part of this task and is excluded from the production-baseline conclusions below. These additional workspace calls route through the existing frontend gateway / scene-state endpoint.

## Evidence labels

- **VERIFIED** — directly established by implementation or a production call path.
- **PARTIALLY VERIFIED** — some paths are established; coverage or consistency is not.
- **PROPOSED** — target contract or implementation recommendation, not current behavior.
- **UNVERIFIED** — repository evidence is insufficient to make a claim.
- **REJECTED** — incompatible with confirmed requirements or existing constraints.

Code locations below link to repository files and relevant line anchors. “Owner” distinguishes an existing storage owner from a proposed authority; names such as “SSOT” in comments are evidence of intent, not proof of end-to-end enforcement.

## 1. Current State

### 1.1 Production entry points and data flow

1. **New scene:** `GameLoop.new_game()` delegates to `CampaignLifecycle.reset_campaign()`; that calls `SceneStateManager.reinit_campaign()` and `initialize_scene()`. `SceneFactory.build_initial_scene()` reads editor objects, NPCs and `player_spawn`, creates `npc_positions`, geometry fields and `world_objects`, then calls `WorldObjectSpawner` for the supported object subset. The initialized scene is saved. **VERIFIED** ([game_loop.py](../../backend/app/services/game_loop/game_loop.py#L760), [campaign_lifecycle.py](../../backend/app/services/game_loop/campaign_lifecycle.py#L341), [scene_state_manager.py](../../backend/app/services/scene_state_manager.py#L826), [scene_factory.py](../../backend/app/services/scene_state/scene_factory.py#L55), [world_object_spawner.py](../../backend/app/services/world/world_object_spawner.py#L126)).
2. **Per-location graph and geometry:** `SpatialFactory`/`SpatialService.build_for_location()` loads editor JSON and compiles navigation graph, boundary map, room geometry, walls, obstacles and affordance objects via `GraphCompiler`; scene state contributes a spatial overlay. This is a different projection from `world_objects`. **VERIFIED** ([spatial_service.py](../../backend/app/services/spatial/spatial_service.py#L50), [graph_compiler.py](../../backend/app/services/spatial/graph_compiler.py#L193)).
3. **NPC queries:** production call sites construct `SpatialQueryService` over a scene’s `npc_positions`; decision, perception, movement and event paths consume it. The class reads the supplied dictionary and geometry from its scene reference. It is not a universal spatial database and does not resolve coordinate frames. **VERIFIED** ([spatial_query_service.py](../../backend/app/services/spatial/spatial_query_service.py#L20), [npc_orchestration.py](../../backend/app/services/game_loop/npc_orchestration.py#L153), [turn_pipeline.py](../../backend/app/services/game_loop/turn_pipeline.py#L118)).
4. **Chunk lookup:** `SpatialRegistry` is a read-only projection of compiled chunk bounds and adjacency. Routes/bridge and idle processing use it to pick a chunk from world XY. It neither owns an entity’s XY nor transfers an entity between scenes. **VERIFIED** ([spatial_registry.py](../../backend/app/services/spatial/spatial_registry.py#L65), [routes.py](../../backend/app/api/routes.py#L1026), [game_loop.py](../../backend/app/services/game_loop/game_loop.py#L1337)).
5. **Continuous NPC movement:** `TickOrchestrator` owns a `WorldTopologyProvider` and `DynamicAffordanceField`. Motion phase injects the active `SpatialService`, queries room affordances, applies collision avoidance against NPC positions and emits SceneChanges. `SpatialService` supplies room geometry; WorldTopologyProvider is not wired to moving-object collision geometry. **VERIFIED** ([tick_orchestrator.py](../../backend/app/services/tick_orchestrator.py#L129), [phases/motion.py](../../backend/app/services/phases/motion.py#L19), [motion_pipeline.py](../../backend/app/services/motion/motion_pipeline.py#L20), [world_topology_provider.py](../../backend/app/services/spatial/world_topology_provider.py#L105)).
6. **Persistence:** `SceneStateManager.save_scene_state()` calls `SpatialPersistenceAdapter`, then either updates tick cache or commits a single scene. Tick completion (`unlock_tick`) commits tick scenes directly with `atomic_commit_all`; it bypasses the adapter. W5 also commits directly. Thus no single spatial normalization hook covers every write. **VERIFIED** ([scene_state_manager.py](../../backend/app/services/scene_state_manager.py#L657), [scene_state_manager.py](../../backend/app/services/scene_state_manager.py#L298), [scene_state_manager.py](../../backend/app/services/scene_state_manager.py#L1535)).
7. **Frontend movement and transition:** frontend stores player XY in `npc_positions.player.local_position`; WASD movement transforms to world coordinates, applies collision against geometry, transforms back, and sends world XY to an oracle. Confirmed chunk changes update scene location and recompute local XY. For `global_coords=true`, ContextResolver conversions are identity; legacy maps use origin translation. **VERIFIED** ([game_screen.py](../../frontend/game_screen.py#L297), [game_screen.py](../../frontend/game_screen.py#L1245), [game_screen.py](../../frontend/game_screen.py#L1740), [world_context.py](../../frontend/world_context.py#L345)). **PARTIALLY VERIFIED:** the unstaged workspace edit also saves on quit/pause/D61 exit; the edit is outside the committed baseline and was not reviewed or changed.
8. **WorldTopologyProvider scope:** it combines `SpatialService` room-zone affordances with transient/dynamic affordance overlays; it does not compile/update graph nodes, walls, object positions, render assets or object interaction projections. **VERIFIED** ([world_topology_provider.py](../../backend/app/services/spatial/world_topology_provider.py#L105)).

### 1.2 Component responsibility and participation

| Component | Facts read / held / changed | Production participation and limit |
|---|---|---|
| `SceneStateManager` | Reads/writes per-location scene payloads, `npc_positions`, `objects`, traversal and geometry fields; runs enrichment and W5. | **VERIFIED:** common scene load/save façade. Not every commit path goes through its save adapter; `unlock_tick` and W5 call persistence directly. ([source](../../backend/app/services/scene_state_manager.py#L397)) |
| `SpatialPersistenceAdapter` | Mutates `location_id`, may create `npc_positions`, warns on zero XY. | **VERIFIED:** one static call from `save_scene_state`; bypassed by tick commit and W5. It does not convert frames or clear legacy fields despite its docstring. ([source](../../backend/app/services/spatial/spatial_persistence_adapter.py#L14)) |
| `SpatialService` | Compiled graph, connections, alias/boundary maps, room geometry, walls, obstacles, affordance objects and scene overlay. | **VERIFIED:** used by movement, navigation and geometry queries. Does not own entity positions or persist them. ([source](../../backend/app/services/spatial/spatial_service.py#L50)) |
| `SpatialQueryService` | Read-only access to the supplied NPC position mapping, distances, visibility and clusters. | **VERIFIED:** instantiated at many production call sites. Its “authoritative” comment is not enforced globally: direct scene reads also exist, and it has no frame metadata. ([source](../../backend/app/services/spatial/spatial_query_service.py#L20)) |
| `SpatialRegistry` | Compiled chunk descriptors, bounds, adjacency and `global_coords`. | **VERIFIED:** read-only oracle/lookup; does not mutate entity state or perform scene transfer. ([source](../../backend/app/services/spatial/spatial_registry.py#L18)) |
| `WorldTopologyProvider` | Scene geometry affordances plus dynamic deformations/traces. | **VERIFIED:** used in continuous NPC motion; not a dynamic-object topology provider. ([source](../../backend/app/services/spatial/world_topology_provider.py#L105)) |
| `WorldObject` / `WorldObjectStore` | Per-object position, state, ownership and topology relations; store exposes typed reads and mutations. | **VERIFIED:** stored under `scene_state["world_objects"]`; production spawn and G3 semantic transition paths exist. Relocation has no production call site found; visual/physical projections are not synchronized by the store. ([domain](../../backend/app/domain/world_object.py#L98), [store](../../backend/app/services/world/world_object_store.py#L230)) |
| `WorldObjectSpawner` | Reads editor object type/id/position/state and spawns mapped archetypes. | **VERIFIED:** called only during construction of a new scene; it handles a subset (e.g. doors, chairs, food portions), not all editor objects. ([spawner](../../backend/app/services/world/world_object_spawner.py#L126)) |
| `SceneFactory` | Creates `objects`, `npc_positions`, geometry, initial scene fields and empty `world_objects`. | **VERIFIED:** input is editor JSON/template; new player coordinates are copied directly from authored spawn, without a coordinate-frame marker. ([factory](../../backend/app/services/scene_state/scene_factory.py#L55)) |
| `GraphCompiler` | Reads editor nodes, rooms, boundaries and geometry; compiles navigation/spatial projections. | **VERIFIED:** graph and physical geometry derive from authored maps, not current `WorldObject` positions. ([compiler](../../backend/app/services/spatial/graph_compiler.py#L193)) |
| W5 migration | Reads `location_id`, `npc_positions`, editor `global_coords`/origin; shifts XY and adds `coord_frame_version`. | **VERIFIED:** ordinary `get_scene_state()` only. Uncached tick load does not call W5. ([SSM](../../backend/app/services/scene_state_manager.py#L565), [migration](../../backend/app/services/scene_state_manager.py#L1456)) |
| Campaign metadata | `current_location`, `player_world_x/y` read by route, bridge, idle and resume logic. | **PARTIALLY VERIFIED:** writers/readers exist, but `CampaignStateService.save()` reloads the file instead of saving the previously modified model, so several “mutate returned state, then save(id)” paths can discard the mutation. ([service](../../backend/app/services/campaign_state_service.py#L50), [route](../../backend/app/api/routes.py#L1051)) |

## 2. Ownership Matrix

“Existing owner” is what currently holds or computes the fact. “Target owner” is a proposal for a single logical source, not a claim that code already enforces it.

| Spatial fact | Existing owner and writers | Readers / derived representations | Target authority |
|---|---|---|---|
| Player and NPC position | **VERIFIED:** `SceneState.npc_positions[id].local_position`; player authored at SceneFactory spawn, frontend WASD, turn initialization from request, traversal execution and SceneChanges update entries. | SnapshotBuilder, frontend renderer, spatial queries, motion, target selection, persistence. `position` node ID is a parallel navigation locator. | **PROPOSED:** one per-entity world-space pose in scene runtime state, written only by simulation/authorized input reconciliation; scene-local coordinates are derived at boundaries. Keep node identity as a derived/reconciled graph reference, not a second XY authority. |
| Entity spatial membership / current player location | **VERIFIED:** `scene_state.location_id`, per-entry `location_id`, `campaign_meta.current_location`, plus oracle result from `player_world_x/y` or request coordinates. | Scene selection, filtering, idle tick, route responses and rendering. Values can conflict; metadata persistence is suspect. | **PROPOSED:** membership belongs to the entity/scene world-state transaction; campaign current-location is a projection for resume/indexing, not a separately edited fact. Oracle proposes/validates membership from world position; transition executor commits both together. |
| World-object position and identity | **VERIFIED:** `WorldObjectStore` owns serialized `world_objects`; `WorldObject.position` is authoritative only in `FREE` carrier mode. Spawn writer is `WorldObjectSpawner`; G3 changes semantic state. | Snapshot projections feed targeting/affordances; editor `objects`/JSON feed rendering and collision. | **PROPOSED:** retain `WorldObjectStore` as object-state authority. No parallel object store. Derived render/collision/navigation/perception views consume a versioned projection of object state plus static map data. |
| Ownership | **VERIFIED:** `WorldObject.ownership` field, distinct from `holder`, `container_id`, `supported_by`, `location_id`. | Object DTO and serialized scene. Current writers/allowed independent operations are not fully demonstrated in production. | **PROPOSED:** ownership is an independent relation/value changed only by ownership operations/events; never infer or overwrite it from holder/container/location. |
| Physical containment / support / carrier | **VERIFIED:** `container_id`, `supported_by`, `holder`, `attachment`, `occupancy`, `used_by`; carrier mode selects position authority. | Store queries, relation projections and semantic object affordance/target consumers. | **PROPOSED:** maintain typed topology in the existing store. Container/support determines a dependent pose where physics requires it; spatial membership remains a separate fact and is validated by an explicit rule, not silently rewritten. |
| Static authored geometry | **VERIFIED:** Editor JSON for walls, rooms, map objects, portals and graph nodes. | GraphCompiler, frontend renderer/collision, SpatialService, registry compiler. | **PROPOSED:** Editor asset is authority for static authored geometry. Runtime edits are explicit world events that create a dynamic override/instance rather than silently mutating the authored map. |
| Dynamic object physical geometry | **PARTIALLY VERIFIED:** no general owner/writer path found. `world_objects` stores object position/state, but graph/collision/render paths read authored geometry and `scene_state.objects`. | Movement collision, navigation, rendering, affordances and interaction may each use different projections. | **PROPOSED:** object state remains authority; derive dynamic collision/occlusion/interactable/navigation overlays from it. |
| Entity motion | **VERIFIED:** `active_traversals` holds route/process; `TraversalExecutionSystem` writes interpolated `local_position`, node ID at completion. ETKE continuous motion emits changes. | Renderer can interpolate traversals; snapshots expose traversal and positions. Frontend player movement is separately predicted. | **PROPOSED:** backend simulation pose is authoritative at committed tick boundaries; traversal is motion process/intent, not a competing final pose. Frontend prediction is ephemeral and reconciled. |
| Chunk topology and adjacency | **VERIFIED:** compiled spatial registry derived from authored map compilation. | Spatial oracle, transitions and navigation. | **PROPOSED:** registry is authoritative read-only topology projection; transition system consumes explicit endpoints and updates entity membership/pose in one world transaction. |
| Physical state / affordance | **PARTIALLY VERIFIED:** object state lives in WorldObject; walls/rooms in editor-derived SpatialService; DynamicAffordanceField has runtime state. No common fold across these domains. | WorldTopologyProvider, collision, navigation and interaction each have distinct paths. | **PROPOSED:** keep domain state in existing domain owners; publish a consistent tick snapshot from their versioned projections. Do not make affordance output an authority for object position or ownership. |

## 3. Lifecycle Map

| Stage | Current verified path | Current limitation / target contract |
|---|---|---|
| Create | Editor JSON → `SceneFactory.build_initial_scene()` → `npc_positions`, `objects`, geometry fields → `WorldObjectSpawner` → `world_objects` → save. | **VERIFIED:** scene NPC/player coordinates and object positions are copied from editor data. **PROPOSED:** stamp the frame/version at creation; separate immutable map geometry from dynamic object instances; establish semantic-object ID provenance. |
| Movement intent | NPC intent/traversal pipeline creates paths; player frontend predicts WASD coordinates and sends XY/world XY on actions/bridge. | **VERIFIED:** NPC intent and frontend prediction are distinct flows. **PROPOSED:** explicit command/intent → backend validation → committed pose; UI prediction remains non-persistent and tagged by tick/revision. |
| Simulation | NPC traversal execution and ETKE motion update `npc_positions`; `SpatialQueryService` and services read NPC positions. WorldTopologyProvider queries room affordance and NPC avoidance. | **VERIFIED:** object relocation is not part of this shared movement execution. **PROPOSED:** all position and topology mutations emit domain changes applied within the tick’s world-state transaction. |
| Object interaction / physical move | `WorldObjectStore.apply_transition()` has G3 executor wiring; store exposes `relocate()`. | **VERIFIED:** relocation production call site not found, and current G3 actions principally change object state. **PROPOSED:** object mobility evaluates object capabilities, subject capabilities, load/attachment/support/obstruction and event context, then commits a typed object mutation. |
| Transition | Frontend/route/bridge obtains chunk from SpatialRegistry; NPC transfer executor handles NPC cross-location transfer; scene and metadata location fields are independently manipulated. | **PARTIALLY VERIFIED:** no single player transition transaction synchronizing scene selection, entity membership, coordinates, metadata, renderer and collision. **PROPOSED:** one transition executor commits destination, coordinate transform, entity membership and event/revision atomically. |
| Save | Direct saves go via `save_scene_state()` + adapter; tick commits and W5 use `atomic_commit_all` directly. Metadata uses separate service/file. | **VERIFIED:** multiple write routes. **PARTIALLY VERIFIED:** unstaged workspace calls add gateway saves on quit/pause/D61 exit; excluded from production baseline. **PROPOSED:** persistence serializes a validated canonical world snapshot; no save-time synthesis of absent coordinates and no frame guessing. |
| Restore | Ordinary scene read applies W5 and enrichment; uncached load applies enrichment but omits W5; session-state chooses location from metadata then loads a scene. | **VERIFIED:** divergent load behavior. **PROPOSED:** one shared, idempotent decode/validate/migrate function for every load entry point, with explicit legacy classification and no destructive conversion on ambiguity. |
| Render / perception | Frontend builds scene from snapshots and local state; NPC/object perception consumes spatial services/snapshots; dynamic object projection is not unified with static geometry. | **PARTIALLY VERIFIED:** no demonstrated object relocation → all-consumer refresh path. **PROPOSED:** projections keyed by world-state revision, invalidated/rebuilt from canonical committed state. |

## 4. Spatial Relations Model

### Current model

- **VERIFIED:** `WorldObject` stores `ownership` separately from `location_id`, `container_id`, `holder`, `supported_by`, `attachment`, `occupancy` and `used_by`. Carrier exclusivity is validated, and carrier mode controls whether the object's stored position is authoritative. `project_relations()` includes `LOCATED_AT` independently. ([WorldObject](../../backend/app/domain/world_object.py#L98), [relation projection](../../backend/app/domain/world_object.py#L190))
- **PARTIALLY VERIFIED:** the store checks cycles and some cross-location constraints (notably `SUPPORTED_BY`), but not every containment/membership combination or all gameplay relation writers. Ownership is stored separately, but complete production mutation paths for all relations are not established. ([WorldObjectStore](../../backend/app/services/world/world_object_store.py#L337))
- **VERIFIED:** `WorldObjectStore` comment establishes the no-parallel-store constraint and it persists as part of SceneState. No separate spatial-entity store is needed to represent object relations. ([store](../../backend/app/services/world/world_object_store.py#L1))

### Target relation semantics

| Relation | Meaning | Mutation boundary | Consistency rules |
|---|---|---|---|
| `Ownership` | Legal/social attribution: who owns the object. | **PROPOSED:** typed ownership operation/event using existing WorldObjectStore. | Independent from possession, containment, support and membership. Changing ownership does not teleport or uncontain. |
| `Physical containment / carrier` | Holder, container, support surface or attachment; controls pose derivation only when the relation physically constrains it. | **PROPOSED:** existing typed relation methods plus explicit physics consequences. | Enforce acyclic relations, valid target, capacities/slots and compatible carrier modes. Cross-location rules must be explicit per relation. |
| `Spatial membership` | World/region/scene/chunk in which an object exists. | **PROPOSED:** explicit membership/relocation mutation in WorldObjectStore/world transaction. | Independent from ownership. A contained object's membership follows its container only if an explicit physical rule says so; otherwise reject inconsistent membership rather than silently rewrite it. |
| `Pose` | World position/orientation of an uncarried/uncontained object; derived pose for carrier relationships. | **PROPOSED:** object mobility operation or relation-derived transform. | Never treat stale cached position of HELD/CONTAINED/ATTACHED object as authoritative. |

**REJECTED:** making `ownership` an alias for `holder`, or treating `location_id` as proof of ownership/containment. These collapse independent relationships prohibited by the accepted D2 requirement.

## 5. Object Mobility Model

- **VERIFIED:** `WorldObject` already includes `archetype`, `state`, `damage`, `position`, ownership and topological relations; `CarrierMode` distinguishes FREE/HELD/CONTAINED/ATTACHED. This is a useful object ontology, not an entity-wide pose model. ([WorldObject](../../backend/app/domain/world_object.py#L98))
- **VERIFIED:** `WorldObjectStore.relocate()` validates existing object and blocks relocation while supported dependents remain; the repository search found test calls, but no production caller. ([relocate](../../backend/app/services/world/world_object_store.py#L401), [tests](../../backend/tests/test_world_object_topology.py#L201))
- **VERIFIED:** `WorldObjectSpawner` projects only a mapped subset of editor objects and copies initial position. Static editor JSON still feeds map rendering, geometry, collision and graph compilation. ([spawner](../../backend/app/services/world/world_object_spawner.py#L126), [geometry compiler](../../backend/app/services/spatial/graph_compiler.py#L585), [frontend object rendering](../../frontend/game_screen.py#L502))
- **VERIFIED:** object target/affordance paths project `WorldSnapshot.world_objects`; they do not prove that an updated WorldObject position alters collision, navigation, map rendering or all NPC observations. ([object targeting](../../backend/app/services/world/object_target_facts.py#L20), [snapshot field](../../backend/app/models/world_snapshot.py#L81))
- **UNVERIFIED:** runtime writer guard allows the store/spawner/G3 executor, but whether each future interaction pathway can cause relocation and publish all projections is outside current wired behavior.

### Target mobility contract

**PROPOSED:** extend the existing `WorldObject` data and typed mutations, not a second object store. Mobility is a policy/capability vector evaluated against both object and actor: movable/portable/holdable/placeable/attachable; mass and shape; damage/lock/fixed foundation; current carrier/support/occupancy; actor force/capacity/tools; and local physical constraints. Do not reduce this to `static/dynamic`.

**PROPOSED:** each accepted physical move is one state transition in the tick transaction:

1. Validate actor authority/capability, object capability, current relations, destination membership and collision constraints.
2. Mutate canonical WorldObject pose and/or relation through `WorldObjectStore`.
3. Emit a world-change record with object ID, old/new pose and relation, tick, cause, and new state revision.
4. Rebuild/invalidate relevant dynamic collision, navigation, render, interaction and perception projections from that committed state revision.
5. Persist canonical object state and relation changes with the scene/tick commit.
6. Publish the same revision to frontend/NPC consumers; stale projections must not be mixed with the new revision.

**PROPOSED:** keep authored walls/rooms as static topology; use a dynamic overlay for movable objects that can block, open, occlude, support or afford interaction. A door state transition must update graph/collision connectivity via its existing semantic event path, not modify the authored map in place.

**REJECTED:** allowing `WorldObjectStore.relocate()` to be treated as complete merely because it updates `world_objects`. Today it cannot guarantee visual/physical/navigational/perceptual synchronization.

## 6. Coordinate Contract

### Existing evidence

- **VERIFIED:** spatial quantities are treated as metres by renderer and physics/movement interfaces. Game rendering uses 40 px/m; Map Editor canvas uses 20 px/m. These are presentation scales, not persistence conversion factors. ([constants.py](../../frontend/constants.py#L153), [scene_renderer.py](../../frontend/scene_renderer.py#L5), [editor_core.py](../../frontend/map_editor/editor_core.py#L46), [map_renderer.py](../../frontend/map_editor/render/map_renderer.py#L23))
- **VERIFIED:** editor's 20 px/m history and `editor_core` value are distinct from the game's 40 px/m constant; scale is not multiplied into backend graph, movement or persisted XY. The validator's comment claiming current editor_core uses 40 is stale. ([validator](../../frontend/map_editor/schema_validator.py#L426))
- **VERIFIED:** ContextResolver uses identity for `global_coords=true`; legacy frame conversion adds/subtracts map origin. Open_road maps are marked global. ([world_context.py](../../frontend/world_context.py#L345), [tavern map](../../frontend/map_editor/campaigns/Open_road/locations/tavern.json#L1470))
- **VERIFIED:** graph compilation has local-coordinate boundary fallback offsets based on map size; authored entrance preference may override that fallback. Mixed frame assumptions must be validated for each map. ([GraphCompiler](../../backend/app/services/spatial/graph_compiler.py#L876))
- **VERIFIED:** `npc_positions.*.local_position` has no explicit per-entry frame field; frame interpretation depends on scene/map context and W5 marker. `WorldObject.position` is described as world metres. ([NPC scene factory](../../backend/app/services/scene_state/scene_factory.py#L90), [WorldObject](../../backend/app/domain/world_object.py#L110))

### Target coordinate contract

| Term | Target definition |
|---|---|
| World coordinates | **PROPOSED:** canonical continuous XY in metres, with +X east and +Y south matching the screen/map convention. Runtime values are not rounded; pixel scaling stays in render adapters. Direction/axis convention must be captured in the accepted contract. |
| Scene coordinates | **PROPOSED:** coordinates in an explicitly named frame, never inferred from `local_position`. Store frame ID/version alongside serialized coordinate data or encode frame in a versioned pose type. |
| Graph node identity | **PROPOSED:** graph node ID is a topological locator, not a coordinate or coordinate source. Resolve node to world XY through its compiled frame; reconcile explicitly when geometry/version changes. |
| Transform | **PROPOSED:** define `scene_to_world` and `world_to_scene` for every frame; current W behavior is translation by origin or identity. Compose parent/container transforms only for relations with physical pose inheritance. |
| Frame version | **PROPOSED:** coordinate-frame version on each persisted scene (or typed payload) indicates the exact frame contract, not simply “migration completed”. New scenes must be stamped at creation. |
| `global_coords` | **VERIFIED:** currently a map-level legacy/world discriminator; **PROPOSED:** preserve it as authoring compatibility input but compile it to explicit frame metadata. It must not be used to guess an unmarked save's coordinate provenance. |
| Legacy saves | **PROPOSED:** classify only where provenance is conclusive (stored marker or known save/map version plus verified transform). Ambiguous scenes are left unchanged and surfaced for explicit repair; no origin addition based only on current map flag. |

**REJECTED:** interpreting `local_position` as necessarily local, or multiplying persisted/gameplay coordinates by 20 or 40.

## 7. Defect Register

| ID / status | Evidence and impact | Minimal direction |
|---|---|---|
| D-01 **VERIFIED** — W5 can double-shift new scene coordinates | New SceneFactory copies already-world editor coordinates for global maps; it does not set `coord_frame_version`. `save_scene_state()` does not set it. First ordinary `get_scene_state()` applies origin to unmarked XY. ([factory](../../backend/app/services/scene_state/scene_factory.py#L107), [save](../../backend/app/services/scene_state_manager.py#L657), [W5](../../backend/app/services/scene_state_manager.py#L1456)) | Stamp frame provenance at scene creation; migrate only conclusively classified legacy data. |
| D-02 **VERIFIED** — ordinary and uncached loads diverge | Ordinary getter runs W5; uncached getter does only enrichment. Tick lock and bulk tick acquisition use uncached reads. ([ordinary load](../../backend/app/services/scene_state_manager.py#L565), [uncached load](../../backend/app/services/scene_state_manager.py#L397), [lock](../../backend/app/services/scene_state_manager.py#L184)) | Share one decode/classify/migrate path across both loaders. |
| D-03 **VERIFIED** — no reliable discriminator for unmarked scenes | W5 uses marker then current editor's `global_coords`/origin; it does not know whether persisted coordinates were already global. New scenes and older saves can both be unmarked. | Introduce explicit provenance for future scenes; treat ambiguous legacy as no-auto-write. |
| D-04 **VERIFIED** — `(0,0)` conflates value and validity | W5 skips `(0,0)` as broken, while action/oracle path documents it as valid. Adapter only warns and may synthesize it. | Represent absence separately (`None`/validity state); preserve numeric zero. |
| D-05 **VERIFIED** — adapter synthesizes player at `(0,0)` | Any `save_scene_state()` without player inserts `{x:0,y:0, position:unknown_node}`. | No fake coordinates; validation should report missing player explicitly, with caller-appropriate save policy. |
| D-06 **VERIFIED** — adapter is not a universal persistence boundary | `unlock_tick` and W5 call `atomic_commit_all` directly. | Put frame validation/serialization in the shared persistence boundary or enforce one validated commit preparation used by all writers. |
| D-07 **VERIFIED** — metadata writes are discarded on the affected call path | `CampaignStateService.save(campaign_id)` reloads metadata from disk before writing; callers mutate a separately returned model then call save. Those mutations are not present in the reloaded object. New Game seed also mutates a model without saving it. ([service](../../backend/app/services/campaign_state_service.py#L50), [service save](../../backend/app/services/campaign_state_service.py#L81), [new game](../../backend/app/services/game_loop/campaign_lifecycle.py#L341)) | Add/use an explicit update API that persists the modified state; verify with round-trip tests. |
| D-08 **VERIFIED** — current location has competing writers/read priorities | Scene location, player entry location, metadata and spatial oracle may differ. `resolve_current_location` prefers scene; `session_state` selects metadata first; route action persists snapshot fact; idle uses metadata. | Define one transactional membership fact and derive all indexes/projections from it. |
| D-09 **VERIFIED** — bridge rejects all-zero coordinate pair | Bridge passes `player_position` only if `(player_x or player_y)`, so `(0,0)` becomes None. ([bridge](../../frontend/game_loop_bridge.py#L230)) | Use explicit presence/optional semantics. |
| D-10 **VERIFIED** — object relocation does not update all projections | Relocate has no production caller; renderer and geometry/collision compile from editor data or `objects`, while object targeting reads `world_objects`. | Introduce revisioned derived projections before enabling production relocation. |
| D-11 **PARTIALLY VERIFIED** — dynamic obstacle representation is split | `WorldTopologyProvider` uses rooms and affordance traces; it does not read WorldObject positions. Static geometry is separately compiled. Full collision consumers vary by movement path. | One physics projection layer combines static geometry and dynamic object state; verify consumers individually. |
| D-12 **VERIFIED** — W5 backup is external, not guaranteed by call path | W5 comments cite external pre-migration backup. Runtime migration mutates and commits through persistence; no in-function backup/read-back. | Copy-based dry-run, durable backup, transaction/read-back verification, rollback gate. |
| D-13 **UNVERIFIED** — exact transition correctness across all campaigns | Existing audited Open_road data has no second separate building, and no tested full transition/save/continue route was found. Other campaigns/data may provide one. | Select a fixture with authored endpoints and verify end-to-end after contract is approved. |
| D-14 **VERIFIED** — player has separate frontend prediction and backend committed position | WASD mutates frontend scene; idle snapshots intentionally omit/avoid overwriting player; pushes are periodic; action turns can pass coordinates. | Separate predicted pose from authoritative committed pose and identify revision/tick reconciliation explicitly. |
| D-15 **PARTIALLY VERIFIED** — WorldObject containment/membership consistency incomplete | Store enforces cycle prevention and same-location support, but independent containment/membership behavior and production writer coverage are not complete. | Add relation-level invariant tests and define explicit event policy for cross-location containment. |

## 8. Target Architecture

### 8.1 Retained components and boundaries

1. **PROPOSED — `SceneStateManager` remains the scene lifecycle/persistence façade.** It owns loading scene state, cache/tick-scoped scenes, and delegation to the persistence port. It should not be the semantic authority for every spatial rule.
2. **PROPOSED — `npc_positions` remains the existing entity pose storage during migration.** Formalize its schema/frame and authorized writers first; do not introduce `SpatialEntity` in this task. A later storage move requires measured need and a separate migration case.
3. **PROPOSED — `WorldObject`/`WorldObjectStore` remains the only semantic object store.** Evolve it to carry individual mobility/physical properties and independent relations. Store writes occur through typed operations, not dictionary mutation.
4. **PROPOSED — `SpatialService` stays a compiled per-location navigation/static geometry service.** Do not make it own runtime positions or persistence. It consumes editor-compiled static geometry plus a revisioned dynamic overlay.
5. **PROPOSED — `SpatialQueryService` stays the read/query façade for entity spatial facts.** Expand or adapt its input contract to explicit frames/revisions; route decision-capable readers through it. It must not become a hidden second state store.
6. **PROPOSED — `SpatialRegistry` remains read-only world chunk/topology index.** Oracle decisions return candidates/result; a transition transaction applies entity membership and transforms. Registry never teleports.
7. **PROPOSED — `WorldTopologyProvider` stays affordance query façade for continuous motion.** Its base topology input should combine static SpatialService geometry and dynamic-object collision/affordance projection at a defined tick revision. Dynamic traces remain separate state with explicit persistence policy.
8. **PROPOSED — `GraphCompiler` compiles authored/static data.** Dynamic graph changes (doors, movable blockers) become runtime overlays keyed by WorldObject state/revision; don't mutate or recompile editor JSON per move.
9. **PROPOSED — `SceneFactory` stamps coordinate frame and initializes canonical entity/object facts.** New SceneFactory output must never be treated as legacy.
10. **PROPOSED — frontend renderer/collision prediction is a view.** It may predict, but only sends movement input/intent or acknowledged pose; it may not independently persist a competing canonical player pose.

### 8.2 Authority and synchronization rules

- **PROPOSED:** one world-state revision per committed simulation tick. Entity poses, memberships, object state/relations and event causes are committed together; snapshot consumers read the same revision.
- **PROPOSED:** typed mutation APIs define authorized writers: movement executor for entity pose; transition executor for membership/frame conversion; WorldObjectStore operations for object state, relations and relocation; SceneFactory for creation; migration service only for classified legacy payloads.
- **PROPOSED:** each derived projection (render, collision, nav, targeting, visibility/perception) records source revision. A stale/missing projection is rebuilt or explicitly rejected, never silently combined with a newer canonical object pose.
- **PROPOSED:** validation catches world position outside membership, invalid relation target/frame, node/pose mismatch beyond configured tolerance, overlapping immovable geometry, duplicate identity, and unsupported cross-location carrier relation.
- **PROPOSED:** consistency failure blocks the mutation/commit or yields a clearly classified repair result; no “success-shaped” fallback to `(0,0)`/`unknown_node`.

## 9. Migration Strategy

### 9.1 W5 compatibility and safety

1. **PROPOSED:** do not disable W5. First add a no-write classifier that reports each scene as `already_world`, `legacy_local`, `known_local_frame`, `unknown/ambiguous`, or `invalid`; classification must use saved provenance/version and known historical map facts, not current `global_coords` alone.
2. **PROPOSED:** stamp all newly created scenes with an explicit frame/version before any save. This prevents W5 from treating new global coordinates as legacy.
3. **PROPOSED:** route ordinary and uncached loads through the same shared migration/decode path. W5 remains idempotent on a durable per-scene marker.
4. **PROPOSED:** auto-migrate only scenes conclusively identified as legacy-local. Unknown/ambiguous scenes remain unchanged, are reported with IDs/counts and require a separately approved repair decision.
5. **PROPOSED:** before any write, preserve byte-identical copies of saves in a separate test/backup location; compute source hashes; run dry-run; write to disposable copies; verify expected coordinates and all non-coordinate fields; test second load/save/continue; verify idempotence; test rollback and read-back.
6. **PROPOSED:** production rollout requires explicit backup existence, migration report review, transaction success and post-write validation. If any gate fails, do not persist converted data.
7. **PROPOSED:** define `(0,0)` as valid numeric data; missing/invalid coordinates use explicit nullable/validity state. Preserve compatibility by interpreting old absence separately from numeric zero.

### 9.2 Persistence unification

- **PROPOSED:** preserve the existing persistence port and atomic tick commit. Introduce a shared validation/serialization boundary invoked for direct scene saves, tick `atomic_commit_all`, W5 migration and any bulk commit. It validates but does not invent positions or transform unclassified coordinates.
- **PROPOSED:** eliminate `SpatialPersistenceAdapter`'s authority to create synthetic position; before changing/removing its behavior, add call-path tests for save with/without player and tick/direct parity. No removal or edit is performed in this architecture task.
- **PROPOSED:** give CampaignStateService a real update/commit operation for metadata changes. Add tests proving `current_location` and world XY survive process-level reload and scene-state restore.
- **PROPOSED:** keep `current_location` as a derived campaign index/cache; canonical membership comes from the committed player's world-state entry. On restore, validate index against scene/entity state and repair only through a logged reconciliation policy.

### 9.3 Object projection migration

- **PROPOSED:** initially preserve static editor geometry and existing renderer data. Add a revisioned dynamic object projection from WorldObjectStore and compare it against existing collision/render/interactions in shadow mode.
- **PROPOSED:** migrate one supported object archetype at a time (e.g. movable chair), with projection parity tests. Leave unsupported editor objects as static authored geometry until explicitly mapped.
- **PROPOSED:** only after consumer parity is verified, enable production relocation; no bulk map rewrite is necessary for the first runtime proof.

## 10. Implementation Sequence

All steps are proposed, isolated, and gated. No production edits are part of this document.

| Step | Scope | Depends on | Acceptance evidence |
|---|---|---|---|
| 0. Ratify contract | Approve owner matrix, coordinate frame/units, invalid data policy, event/transaction semantics, relation rules and backup policy in final ADR. | This architecture review; accepted D1/D2 retained. | ADR accepted and indexed; each rule has a testable invariant. |
| 1. Characterization locks | Add focused tests for adapter synthetic position, direct-vs-tick persistence, W5 ordinary-vs-uncached load, new-scene frame, metadata write/read, zero coordinates. | Step 0, without changing production behavior. | Tests reproduce documented behavior and guard expected compatibility. |
| 2. Frame provenance | Stamp new scenes; add legacy classifier and explicit coordinate contract; unify load decode/migration entry. | Step 1. | New scenes never shift; confirmed legacy shifts exactly once; ambiguous payload is untouched; both loaders return identical canonical scene. |
| 3. Persistence and location consistency | Shared validation at every commit path; explicit metadata update API; transition membership transaction. | Step 2. | Save/continue and transition round-trip preserve XY, frame, location and marker; no fabricated state. |
| 4. Dynamic object projection (shadow) | Build dynamic collision/nav/render/interaction/perception views from WorldObject state and revision without enabling moves. | Steps 0 and 1; relation semantics accepted. | Fixture tests show each consumer projection matches one source revision; static assets unaffected. |
| 5. Mobility vertical slice | Enable one object archetype with actor/object capabilities, typed move/relation operations and event journal. | Step 4. | Move/hold/place/contain scenario updates canonical state, all projections, NPC perception and persistence; rejection leaves state unchanged. |
| 6. Expand & retire duplicate projections | Migrate additional archetypes and deprecate duplicated dynamic `objects` data where safe. | Step 5 with per-archetype proof. | No consumer reads stale coordinates; backward save compatibility verified; performance measured. |

## Main criterion response

**VERIFIED:** Today, if an NPC moves a `WorldObject`, there is no production relocation caller, and the exposed `WorldObjectStore.relocate()` method alone does not update editor-derived rendering, collision, navigation or all perception paths. Therefore the architecture **does not currently guarantee** that the entire world uses one object-movement fact.

**PROPOSED:** retain WorldObject as the sole semantic object store, add explicit mobility and relation transitions, and make every dynamic projection derive from the same committed state revision. For entities, first formalize `npc_positions` frame and writers rather than introducing a new store. Unify restore/migration/persistence around explicit provenance. Only then can a vertical test establish the desired guarantee.

## Evidence references

- [ADR-O-439 coordinate frame contract](ADR-O-439_COORD_FRAME_W.md)
- [SceneStateManager](../../backend/app/services/scene_state_manager.py)
- [Spatial persistence adapter](../../backend/app/services/spatial/spatial_persistence_adapter.py)
- [SpatialService](../../backend/app/services/spatial/spatial_service.py), [SpatialQueryService](../../backend/app/services/spatial/spatial_query_service.py), [SpatialRegistry](../../backend/app/services/spatial/spatial_registry.py)
- [WorldTopologyProvider](../../backend/app/services/spatial/world_topology_provider.py), [GraphCompiler](../../backend/app/services/spatial/graph_compiler.py)
- [WorldObject domain](../../backend/app/domain/world_object.py), [WorldObjectStore](../../backend/app/services/world/world_object_store.py), [WorldObjectSpawner](../../backend/app/services/world/world_object_spawner.py)
- [SceneFactory](../../backend/app/services/scene_state/scene_factory.py), [World snapshot builder](../../backend/app/services/integration/world_snapshot_builder.py)
- [Frontend game screen](../../frontend/game_screen.py), [ContextResolver](../../frontend/world_context.py), [game renderer](../../frontend/scene_renderer.py)
- [W5 characterization tests](../../backend/tests/test_p1_04_save_migration_w5.py), [WorldObject topology tests](../../backend/tests/test_world_object_topology.py)
