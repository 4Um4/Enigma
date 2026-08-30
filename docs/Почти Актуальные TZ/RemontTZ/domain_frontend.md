# ENIGMA — Frontend/Backend Contract, API Routes, Persistence & World Continuity Audit

**Scope:** `backend/app/api/*`, `backend/app/services/state/*`, `backend/app/services/integration/world_snapshot_builder.py`, `backend/app/services/world/*`, `backend/app/services/game_loop*`, `backend/app/services/{player_avatar,player_session,campaign_state,character}_service.py`, `backend/app/services/dto.py`, `backend/app/models/{world_snapshot,world_state_diff,world_continuity,schemas,npc_state,truth_state,end_screen,scene_mode,front,character}.py`, `backend/app/core/*`, `frontend/{api_client,game_loop_bridge,game_screen,scene_renderer,game_types,constants,world_context,presentation_firewall,perceptual_momentum,narrative_renderer,narrative_beat,end_screen_renderer,display_manager,game_menu,settings_screen,text_input,i18n,ui_theme,campaign_select,character_select,npc_name_resolver,spatial_compilation_gateway,spatial_compilation_orchestrator}.py`.

All line numbers refer to the exact file as imported by the running backend/frontend (after path canonicalisation).

---

## 0. Executive Summary

The codebase shows a clear architectural intent (backend = source of truth, frontend = pure renderer) but suffers from:

1. **stream_turn SSE drops `world_snapshot`** in the final `done` event → in Direct mode the frontend never receives NPC positions or perception.
2. **`skip_time` never calls `unlock_tick()`** → scene_manager stays locked forever after sleep and mutated state is never persisted (NPC teleport-back bug).
3. **Double `/api/api/` prefix** on `/api/debug/llm/restart`.
4. **`BackendContract` missing `set_continuity_mode` / `_base_url`** → frontend gateway methods raise `AttributeError`.
5. **`world_diff_applicator` writes `life_status` at NPC root** instead of `body_state.life_status` → cross-campaign dead NPCs are still treated as alive by combat / decision_hub / life_engine.
6. **`ResponseValidator._get_fallback_text`** unconditionally returns `"Ничего не произошло."` for 8 different violation classes → empty DM responses.
7. **`WorldSnapshotBuilder._empty_snapshot`** omits `player_perception`, `avatar_state`, `ambient_phenomenology`, `active_traversals`, `recent_dialogues` → polling `/api/world_state` returns a snapshot that frontend cannot render perception from.
8. **`world_scheduler.maybe_tick`** uses `datetime.now(timezone.utc)` and `WorldSnapshot.created_at = time.time()` — wall-clock leaks into simulation snapshot.
9. **`SqlitePersistenceAdapter.delete_campaign`** only deletes `scene:{id}` + `runtime:{id}` but leaves orphan per-location rows `scene:{id}:{loc}`.
10. **`routes_debug.reset_campaign_relationships`** imports `from app.core.game_loop import get_game_loop` which does not exist (real path: `app.services.game_loop_accessor`) → route is dead.

---

## BUG LOG

### BUG-FB-001 — `stream_turn` "done" event drops `world_snapshot` (PlayerPerceptionDTO always empty in Direct mode)
- **File:line:** `backend/app/services/game_loop/__init__.py:1424-1435`
- **Symptom:** In Direct mode (`DirectGameGateway` / `game_loop_bridge.py`), the bridge reads `event.get("world_snapshot")` from the SSE `done` event. For normal turns this is always `None`; the bridge then falls back to an empty dict (`game_loop_bridge.py:241-246`). Result: `npc_positions` empty, `player_perception` missing, `avatar_state` missing on every player turn that doesn't end in death.
- **Root cause:** The `done` payload in `stream_turn` only carries `tokens`, `ms`, `tps`, `game_time_seconds`, `will_conflict_data`. Only the death early-exit branch (line 1347-1356) and `run_turn` (REST path) build & pass `world_snapshot`. `run_turn` does this at lines 1200-1245 (`WorldSnapshotBuilder.build(..., player_perception=_pp, all_npcs_raw=_anr, recent_dialogues=_recent_d)`). `stream_turn` skips that block entirely.
- **Severity:** Critical
- **Suggested fix:** Mirror the post-pipeline block from `run_turn` (lines 1200-1271) inside `stream_turn` between the `dm_text_parts` flush and the `yield {"type": "done", ...}`. Add `world_snapshot` and `npc_positions` keys to the done payload:
  ```python
  yield {
      "type": "done",
      "tokens": token_count, "ms": elapsed_ms, "tps": tps,
      "game_time_seconds": _ss_scene.get("game_time_seconds", 0),
      "will_conflict_data": ...,
      "world_snapshot": _ws_dict,           # NEW
      "npc_positions": _npc_pos_dict,       # NEW
  }
  ```

### BUG-FB-002 — `skip_time` never persists mutated state (NPC teleport-back after sleep)
- **File:line:** `backend/app/services/game_loop/__init__.py:743-822`
- **Symptom:** After "sleep" the frontend shows NPCs at the new positions (returned `world_snapshot`), but the next `idle_tick`/`game_action` loads the OLD persisted scene_state and NPCs teleport back. This matches the reported symptom "NPCs at wrong locations after sleep (loc=city_gate, node=exit_west)".
- **Root cause:** `skip_time` calls `self.scene_manager.lock_for_tick(campaign_id, "")` and mutates `_scene` in-place through `_time_skip.skip(...)`, but **never calls `commit_tick_result` or `unlock_tick`**. The threading lock `lock.release()` in the `finally:` block is `_skip_lock`, not the scene_manager lock. Result:
  1. `scene_manager._tick_locked` stays `True` forever after sleep.
  2. `scene_manager._tick_scenes[""]` holds the mutated sleep scene, but persistence still has the pre-sleep state.
  3. The next `idle_tick` calls `lock_all_for_tick` which sees `_tick_locked=True` and **does nothing** (line 243-244 of scene_state_manager.py); `get_scene_state(campaign_id, "tavern")` falls through to `load_scene_at` which returns the OLD persistence row.
  4. After idle_tick, `unlock_tick` saves BOTH `_tick_scenes[""]` (sleep-mutated, stale) AND `_tick_scenes["tavern"]` (fresh) — both write to `scene:{campaign_id}:tavern` because the sleep scene's `location_id` is "tavern". Dict insertion order: `""` first → `"tavern"` second → `"tavern"` wins, but the sleep mutations are silently lost.
- **Severity:** Critical
- **Suggested fix:** In `skip_time` finally block, add `self.scene_manager.commit_tick_result(campaign_id, result.final_state)` followed by `self.scene_manager.unlock_tick(campaign_id)`. Also call `lock_all_for_tick` over `_location_ids` from `SpatialRegistry.get_all_location_ids()` instead of `lock_for_tick(campaign_id, "")` — sleep must process every location.

### BUG-FB-003 — Double `/api/api/` prefix on `/api/debug/llm/restart`
- **File:line:** `backend/app/api/routes.py:160` (`@router.post("/api/debug/llm/restart")`) + `backend/app/main.py:401` (`app.include_router(router, prefix="/api")`)
- **Symptom:** Effective URL becomes `/api/api/debug/llm/restart`. The launcher's recovery path that calls this endpoint will get 404.
- **Root cause:** Route path includes `/api/` but the router is mounted with `prefix="/api"`.
- **Severity:** High
- **Suggested fix:** Change decorator to `@router.post("/debug/llm/restart")` (it will then resolve to `/api/debug/llm/restart`, matching the `/api/debug/*` group exposed by `routes_debug.router`).

### BUG-FB-004 — `BackendContract` missing `set_continuity_mode` and `_base_url`
- **File:line:** `frontend/api_client.py:376-377` (`HttpGameGateway.set_continuity_mode`) and `frontend/api_client.py:421` (`HttpGameGateway.get_world_state` reads `self._contract._base_url`)
- **Symptom:**
  - `HttpGameGateway.set_continuity_mode(mode)` calls `self._contract.set_continuity_mode(mode)`, but `BackendContract` (lines 210-324) has no such method → `AttributeError`.
  - `HttpGameGateway.get_world_state` reads `self._contract._base_url`, but `BackendContract` only has `self._t` (the `HttpClient`). `_base_url` lives on `HttpClient` → `AttributeError`.
- **Root cause:** Two gateway methods were added to `HttpGameGateway` without implementing the contract side. There is no backend route for `set_continuity_mode` either (only `/api/game/new/{id}` with `continuity_mode` in body).
- **Severity:** High (silent breakage of FallbackGateway path)
- **Suggested fix:** Either:
  - Remove `set_continuity_mode` / fix `get_world_state` to use `self._contract._t.base_url`; OR
  - Add `BackendContract.set_continuity_mode` that POSTs to a new backend endpoint `/api/game/continuity_mode` (does not exist — must be created) and add `_base_url` property on `BackendContract` returning `self._t.base_url`.

### BUG-FB-005 — `WorldSnapshotBuilder._empty_snapshot` omits required perception fields
- **File:line:** `backend/app/services/integration/world_snapshot_builder.py:372-391`
- **Symptom:** When `scene_state` is falsy, the builder returns a `WorldSnapshotDTO` that lacks `player_perception`, `avatar_state`, `ambient_phenomenology`, `active_traversals`, `recent_dialogues`. These all default to `None`/`[]` via dataclass field defaults, but downstream consumers (frontend game_screen.py:1095) do `if "player_perception" in _ws:` — once serialized via `asdict()`, the key IS present but with `None` value, so the branch fires and `scene_state["player_perception"] = None`, overwriting any prior perception.
- **Root cause:** Inconsistency between the populated-snapshot path (line 85-104) which sets every field, and the empty path (line 372-391) which omits them.
- **Severity:** High
- **Suggested fix:** Add the missing fields to `_empty_snapshot`:
  ```python
  active_traversals={},
  avatar_state=None,
  ambient_phenomenology=None,
  player_perception=None,
  recent_dialogues=recent_dialogues or [],
  ```

### BUG-FB-006 — `/api/world_state` endpoint never passes `player_perception` / `avatar_state` / `all_npcs_raw`
- **File:line:** `backend/app/api/world_routes.py:59-60`
- **Symptom:** Polling `GET /api/world_state?campaign_id=...` returns a snapshot whose `player_perception`, `avatar_state`, `ambient_phenomenology`, `recent_dialogues` are always `None`/`[]`. The endpoint calls `builder.build(scene_state=scene_state, tick=current_tick)` and ignores the four optional kwargs that `WorldSnapshotBuilder.build` accepts.
- **Root cause:** Endpoint was wired before perception was added; never updated.
- **Severity:** Medium (the frontend currently relies on action/idle_tick responses, not polling, but the endpoint advertises itself as the canonical snapshot source).
- **Suggested fix:** Either:
  - Pass through perception/avatar/etc. from a cached `last_world_snapshot` on `game_loop` (already kept in idle_tick path); OR
  - Mark the endpoint as deprecated and have frontend use `idle_tick` response.

### BUG-FB-007 — `world_diff_applicator` writes `life_status` at NPC root, not in `body_state`
- **File:line:** `backend/app/services/state/world_diff_applicator.py:40`
- **Symptom:** When `WorldStateApplicator.apply()` is called in CONTINUOUS mode for fates in `_DEAD_FATES = {"killed_by_guild", "death", "suicide"}`, it sets `npc_cache[npc_id]["life_status"] = "DEAD"`. But every consumer of `life_status` in the simulation reads `npc["body_state"]["life_status"]`:
  - `tick_orchestrator.py:1310` — `n.get("body_state", {}).get("life_status") != "DEAD"`
  - `life_engine.py:2154` — `npc.get("body_state", {}).get("life_status") == "DEAD"`
  - `decision_hub.py:408` — reads from `_body` (body_state)
  - `injury_processor.py:246` — `_body.get("life_status") == "DEAD"`
  - `vital_state.py:116` — `body_state.get("life_status")`
  - `dm_agent.py:356,395` — `pdata.get("life_status")` (this one reads root, but pdata is a different projection)
- **Root cause:** Mistake about which dict the field lives on. The test `tests/test_world_continuity.py:54` asserts the wrong location: `assert npc_cache["merchant_goran"]["life_status"] == "DEAD"` — passes against the buggy code, but is itself wrong.
- **Severity:** High (DEATH LOCK invariant ADR-127 is violated for cross-campaign continuity; dead NPCs from previous campaign come back to life and act normally).
- **Suggested fix:** Change line 40 to:
  ```python
  _bs = npc_cache[npc_id].setdefault("body_state", {})
  _bs["life_status"] = "DEAD"
  _bs["current_hp"] = 0
  _bs["consciousness"] = 0.0
  ```
  Also fix `tests/test_world_continuity.py:54` to assert on `npc_cache["merchant_goran"]["body_state"]["life_status"]`.

### BUG-FB-008 — `ResponseValidator._get_fallback_text` always returns "Ничего не произошло."
- **File:line:** `backend/app/services/verbalization/response_validator.py:270-272` and triggers at lines 62, 67, 71, 75, 85, 91, 98, 103
- **Symptom:** DM responses silently replaced by "Ничего не произошло." for any of 8 violation classes: empty, non_russian, repeat, fourth_wall, cannot_speak, cannot_move, unauthorized_movement_only, forbidden action. This is the reported bug #3 (empty DM responses).
- **Root cause:** Universal fallback text is the same regardless of violation type. Triggers are overly broad — e.g. `_breaks_fourth_wall` rejects any text containing the words "игрок", "система", "механика", "интерфейс" (line 115-122) even when used in legitimate Russian narration ("Игрок осматривается" is normal DM text). `_contains_non_russian` (line 140-156) rejects any text with <50% Cyrillic characters — single English loanword can flip it. Combined with `dm_agent._fallback_narrate` (dm_agent.py:1064-1069) which also returns `MSG_NOTHING_HAPPENED` on LLM failure, the fallback chain dominates.
- **Severity:** Critical (visible UX bug)
- **Suggested fix:**
  - Differentiate fallback text per violation class (e.g. repeat → "Мир замирает в ожидании.", fourth_wall → silent drop, empty → "Тишина.").
  - Tighten `_breaks_fourth_wall`: only flag "игрок" when used as direct address ("Ты, игрок"), not in third-person narration.
  - Tighten `_contains_non_russian`: require <30% Cyrillic AND >50 ASCII letters (currently any non-Cyrillic majority triggers).
  - Log every fallback with full LLM output to `enigma_<date>.jsonl` so the trigger is debuggable.

### BUG-FB-009 — `routes_debug.reset_campaign_relationships` imports non-existent module
- **File:line:** `backend/app/api/routes_debug.py:99`
- **Symptom:** Calling `POST /api/debug/reset-relationships/{campaign_id}` raises `ImportError: No module named 'app.core.game_loop'`. The route is effectively dead.
- **Root cause:** Wrong import path. The actual accessor lives at `app.services.game_loop_accessor.get_game_loop` (note: takes a `Request`, not zero args — see `routes_debug.py:76` for correct usage).
- **Severity:** Medium (debug-only route, but documented as migration tool)
- **Suggested fix:** Replace line 99-101 with:
  ```python
  from app.services.game_loop_accessor import get_game_loop
  from fastapi import Request
  loop = get_game_loop(request)
  ```

### BUG-FB-010 — `SqlitePersistenceAdapter.delete_campaign` leaves orphan per-location rows
- **File:line:** `backend/app/services/state/sqlite_persistence_adapter.py:171-187`
- **Symptom:** `delete_campaign(campaign_id)` executes `DELETE FROM state_kv WHERE key = ? OR key = ?` with `f"scene:{campaign_id}"` and `f"runtime:{campaign_id}"`. But `save_scene` writes to `f"scene:{campaign_id}:{location_id}"` (line 122). After New Game, all `scene:{campaign_id}:tavern`, `scene:{campaign_id}:city_gate`, etc. survive in SQLite and are re-loaded on next access, undoing the reset.
- **Root cause:** Mismatch between key formats written by `save_scene` / `save_scene_at` / `atomic_commit` and the keys deleted by `delete_campaign`. `atomic_commit` (line 252) writes to `f"scene:{campaign_id}"` (no location suffix), but `save_scene` writes to `f"scene:{campaign_id}:{loc_id}"`.
- **Severity:** Critical (New Game does not actually reset state — same class of bug as BUG-FB-002)
- **Suggested fix:** Use prefix delete:
  ```python
  conn.execute(
      "DELETE FROM state_kv WHERE key LIKE ?",
      (f"scene:{campaign_id}:%",),
  )
  conn.execute(
      "DELETE FROM state_kv WHERE key LIKE ?",
      (f"runtime:{campaign_id}:%",),
  )
  conn.execute(
      "DELETE FROM state_kv WHERE key IN (?, ?, ?)",
      (f"scene:{campaign_id}", f"runtime:{campaign_id}", f"events_tick:{campaign_id}"),
  )
  ```

### BUG-FB-011 — `atomic_commit` writes to wrong key (no location suffix)
- **File:line:** `backend/app/services/state/sqlite_persistence_adapter.py:252-256`
- **Symptom:** `atomic_commit` calls `self._upsert(f"scene:{campaign_id}", scene_state)` (line 252) — key WITHOUT location suffix. But `save_scene` (line 122) writes to `f"scene:{campaign_id}:{location_id}"`. Result: atomic_commit creates an orphan row that `load_scene_at(campaign_id, location_id)` never reads (it queries `scene:{campaign_id}:{location_id}`). The atomic commit is silently lost for any subsequent `get_scene_state_uncached` call.
- **Root cause:** Inconsistency between the two write paths. `atomic_commit` is supposed to be the canonical write but uses the legacy key format.
- **Severity:** High
- **Suggested fix:** In `atomic_commit`:
  ```python
  _loc_id = scene_state.get("location_id", "default") if isinstance(scene_state, dict) else "default"
  self._upsert(f"scene:{campaign_id}:{_loc_id}", scene_state)
  if npc_states is not None:
      self._upsert(f"runtime:{campaign_id}", npc_states)
  ```

### BUG-FB-012 — `world_scheduler.maybe_tick` uses wall clock (`datetime.now(timezone.utc)`)
- **File:line:** `backend/app/services/world_scheduler.py:32-34`
- **Symptom:** `now = datetime.now(timezone.utc)` decides whether to fire a background world tick based on real elapsed minutes (`settings.world_tick_minutes`). This violates the architecture rule "No wall clock in simulation". Two runs of the same save produce different world events depending on real-world pause duration.
- **Root cause:** The scheduler was designed for real-time cadence, not tick-based cadence.
- **Severity:** Medium
- **Suggested fix:** Drive scheduling off `scene_state["tick"]` modulo `WORLD_TICK_EVERY_TURNS` (already exists in constants.py:306 = 2). Remove `datetime.now()` and `_last_tick_at` wall-clock logic.

### BUG-FB-013 — `WorldSnapshot.created_at = time.time()` (wall clock inside frozen snapshot)
- **File:line:** `backend/app/models/world_snapshot.py:89`
- **Symptom:** `build_snapshot` writes `created_at=time.time()` into the `WorldSnapshot` dataclass. The class docstring claims "Первый закон причинности ENIGMA: Одинаковый Snapshot + Одинаковый Event = Одинаковый Result" — but `time.time()` is non-deterministic, so two snapshots built from the same scene_state get different `created_at` and are not equal.
- **Root cause:** Field was added for diagnostics without considering the determinism invariant.
- **Severity:** Medium
- **Suggested fix:** Replace with `created_at=tick` (or remove the field entirely if it's only used for logging).

### BUG-FB-014 — `scene_state["last_save_real_time"] = time.time()` (wall clock leaks into scene_state)
- **File:line:** `backend/app/services/scene_state_manager.py:1489-1491`
- **Symptom:** Every `commit()` writes wall-clock `time.time()` into `scene_state["last_save_real_time"]`. This field is then persisted via `atomic_commit` and survives save/load. Two save/load cycles produce different `last_save_real_time` values for the "same" game state, breaking replay determinism.
- **Root cause:** ADR-047 explicitly allows this as "REAL_TIME_BRIDGE", but it conflicts with the "no wall clock in simulation" rule.
- **Severity:** Low (only used for diagnostics, not for simulation decisions)
- **Suggested fix:** Move `last_save_real_time` out of `scene_state` into a separate diagnostic log file (e.g. `saves/<campaign_id>/save_audit.jsonl`).

### BUG-FB-015 — `game_action` route does not return `scene_state` or `metadata` that frontend expects
- **File:line:** `backend/app/api/routes.py:569-595` (response dict) vs `frontend/api_client.py:320-321` (reads `raw.get("scene_state", {})`, `raw.get("metadata", {})`)
- **Symptom:** `BackendContract._map_action_response` populates `GameActionResponse.scene_state` and `GameActionResponse.metadata` from the action response, but `routes.py:game_action` returns a dict that has neither key. The fields are silently `{}` on every HTTP-mode action. The Direct path (`DirectGameGateway.send_action`, api_client.py:481-496) reads `result.scene_state` / `result.metadata` from `TurnResult` — but the bridge never sets these either (`game_loop_bridge.py:179-251`). So the fields are always `{}`/`None` regardless of transport.
- **Root cause:** Frontend expects fields the backend never sends. The fields appear to have been added for an aborted "S85" feature.
- **Severity:** Medium (frontend has dead code that pretends to consume these; UI initialisation that depends on them silently no-ops)
- **Suggested fix:** Either:
  - Add `"scene_state": state.shared_context.scene_state` and `"metadata": ...` to the response dict in routes.py:569-595; OR
  - Remove `scene_state`/`metadata` from `GameActionResponse` and `_map_action_response` and `TurnResult`.

### BUG-FB-016 — `DirectGameGateway.send_action` has dead code after `return`
- **File:line:** `frontend/api_client.py:497-503`
- **Symptom:** The diagnostic block:
  ```python
  if hasattr(result, "will_conflict_data"):
      logger.debug(...)
  else:
      logger.debug("[EMBODIMENT_PIPELINE] field missing on result")
  ```
  is unreachable — it sits after `return GameActionResponse(...)` at line 481-496. The diagnostic never fires, so embodiment pipeline tracing is broken in Direct mode.
- **Root cause:** Code was added below the return by mistake.
- **Severity:** Low
- **Suggested fix:** Move the diagnostic above the `return` or delete it.

### BUG-FB-017 — `game_loop_bridge.turn()` hardcodes `location = "tavern_silver_wolf"` as fallback
- **File:line:** `frontend/game_loop_bridge.py:127`
- **Symptom:** The line `location = "tavern_silver_wolf"  # Оставлено как last-resort fallback` substitutes a campaign-specific location_id from the tavern mini-game for any campaign where `scene_manager.find_starting_location` fails. This violates the rule "campaign_id != location_id (cannot substitute)". For the "Open_road" campaign, if `find_starting_location` raises, the bridge silently uses tavern_silver_wolf and the spatial oracle / NPC loading will be wrong.
- **Root cause:** Leftover from the MVP mini-game. Comment claims it's "last-resort" but there's no proper fallback chain.
- **Severity:** Medium
- **Suggested fix:** If `find_starting_location` fails, return `TurnResult(error="No starting location for campaign")` and let the frontend surface it. Do not substitute a hardcoded foreign location_id.

### BUG-FB-018 — `game_loop_bridge.turn()` does not pass `world_x`/`world_y` to `stream_turn`
- **File:line:** `frontend/game_loop_bridge.py:179-189`
- **Symptom:** The bridge computes `confirmed_location_id` via Spatial Oracle using `world_x`/`world_y` (lines 140-178), but the actual `stream_turn` call at line 180-189 only passes `player_position=(player_x, player_y)` — `world_x`/`world_y` are dropped. So in Direct mode the backend never receives world coordinates and cannot run its own Spatial Oracle. This causes divergence between HTTP path (which DOES send `world_x`/`world_y` via `routes.py:454-461`) and Direct path.
- **Root cause:** `stream_turn` signature in `game_loop/__init__.py:1298-1306` does not accept `world_x`/`world_y`. The bridge has nowhere to pass them.
- **Severity:** Medium
- **Suggested fix:** Extend `stream_turn` signature to accept `world_x: float | None = None, world_y: float | None = None`. Inside `_run_pipeline`, run Spatial Oracle on these coordinates (mirroring `routes.py:474-490`) so Direct and HTTP paths produce identical location resolution.

### BUG-FB-019 — `TruthState.discovered_secrets` is a mutable `Set` inside a `frozen=True` dataclass
- **File:line:** `backend/app/models/truth_state.py:44-57`
- **Symptom:** `@dataclass(frozen=True)` only prevents reassigning the field; the set itself is mutable and `mark_discovered` mutates it in place (line 54-57). The `secrets: Mapping[str, Secret]` field uses `default_factory=dict` — also mutable. Frozen contract is broken.
- **Root cause:** Misunderstanding of `frozen=True` semantics.
- **Severity:** Low (functional correctness is fine, but invariant is misleading)
- **Suggested fix:** Either:
  - Remove `frozen=True` and document that the class is mutable but the schema is fixed; OR
  - Use `frozenset` for `discovered_secrets` and return a new `TruthState` from `mark_discovered` (proper immutability).

### BUG-FB-020 — `L1Chronicle.archive_old_events` deletes from the active events table
- **File:line:** `backend/app/services/npc/l1_chronicle.py:258-261`
- **Symptom:** `DELETE FROM l1_chronicle_events WHERE campaign_id = ? AND tick_id < ?` removes rows from the supposedly "append-only" active table. Although events are first copied to `l1_chronicle_archive` (line 249-256), the rule "L1Chronicle is append-only SQLite" is violated for the active table — a DELETE statement runs.
- **Root cause:** The "append-only" contract is interpreted at the logical level (events are never lost — they go to archive) but the physical table does see DELETEs.
- **Severity:** Low (data is preserved in archive; logical contract intact)
- **Suggested fix:** If the rule is strict, never DELETE — instead mark rows as `archived=1` and have `query_raw` filter. If the rule is logical, document the archive-then-delete pattern explicitly and adjust the architecture rule wording.

### BUG-FB-021 — `MockProvider._pick_response` reads `ENIGMA_ENV` env var instead of `settings.environment`
- **File:line:** `backend/app/services/llm/mock_provider.py:126-138`
- **Symptom:** MockProvider gates its response on `os.getenv("ENIGMA_ENV", "production")`, but `ProviderFactory.create` (factory.py:78) gates on `settings.environment`. The two sources of truth disagree:
  - `AIDM_ENVIRONMENT=development` (read by `Settings`) → `ProviderFactory.create(MOCK)` succeeds.
  - But if `ENIGMA_ENV` is unset (defaults to "production"), `MockProvider._pick_response` returns `""` → `ResponseValidator._fallback("empty")` → "Ничего не произошло."
- **Root cause:** Two independent environment checks. The factory trusts `settings.environment`, the provider trusts `os.getenv("ENIGMA_ENV")`.
- **Severity:** Medium (the ProviderFactory guard is correct, but if anyone instantiates MockProvider directly — e.g. via DI in tests that run alongside production code — the env var check silently degrades responses).
- **Suggested fix:** Have MockProvider accept `environment: str` in its constructor (passed from `settings.environment` by the factory) and use that single source of truth. Remove `os.getenv("ENIGMA_ENV")`.

### BUG-FB-022 — `frontend/constants.py` defines `RENDER_COLORS`, `COLOR_TEXT_*`, `AGGRESSION_COLORS` TWICE
- **File:line:** `frontend/constants.py:88-136` (first block) and `frontend/constants.py:154-201` (second block)
- **Symptom:** The second block silently overwrites the first. The first block's `RENDER_COLORS` includes `"attention_glow": (70, 170, 255, 40)` (line 123); the second block does not. If any consumer reads `_COLORS["attention_glow"]`, they get `KeyError` after the second block overwrites. Currently no consumer reads it (verified via grep), so this is dormant.
- **Root cause:** Copy-paste duplication.
- **Severity:** Low
- **Suggested fix:** Delete the second block (lines 150-201).

### BUG-FB-023 — `frontend/i18n.py` defines `ui:death_title`, `ui:death_subtitle`, `ui:journal_title`, `ui:narrator` TWICE
- **File:line:** `frontend/i18n.py:63-66` and `frontend/i18n.py:108-112`
- **Symptom:** Second definition wins. The first uses `── Журнал Диалогов (J) ──` (Unicode box-drawing), the second uses `--- Журнал Диалогов (J) ---` (ASCII). UI appearance changes silently based on which block Python evaluates last.
- **Root cause:** Copy-paste duplication.
- **Severity:** Low (cosmetic)
- **Suggested fix:** Delete the duplicate block at lines 108-112.

### BUG-FB-024 — `player_session_service.is_player_active` uses wall clock (`datetime.now()`)
- **File:line:** `backend/app/services/player_session_service.py:174, 186, 137, 147` and `backend/app/models/schemas.py:284` (`PlayerSession.is_active` calls `datetime.now()`)
- **Symptom:** Activity check is based on real elapsed seconds since `last_heartbeat`. If the OS clock jumps (NTP sync, suspend/resume), sessions can be wrongly invalidated or wrongly kept alive. This is not a direct violation of "no wall clock in simulation" because session lifetime is real-time, but the `is_active(timeout_seconds=120)` decision affects whether `game_action` returns 412 — which is a simulation-affecting gate.
- **Root cause:** Standard heartbeat pattern, but mixed with simulation flow.
- **Severity:** Low
- **Suggested fix:** This is acceptable for session management. Just document that `is_player_active` is real-time, not simulation-time. No code change needed if the rule is interpreted strictly about simulation advancement.

### BUG-FB-025 — `game_screen.py` reads `game_time_seconds` from `scene_state` and `world_snapshot`
- **File:line:** `frontend/game_screen.py:553, 1001-1004, 1078-1081, 1213-1218`
- **Symptom:** The architecture rule says "game_time_seconds forbidden in frontend". The frontend reads this field for HUD display (`format_world_date(self.game_time_seconds)` at line 1952) and writes it back into `scene_state["game_time_seconds"]` at lines 1004, 1080. The frontend does NOT compute it (no `+= 60` — that was removed at line 983 with the comment "Раньше: self.game_time_seconds += ... → dual truth."). So this is a soft violation: the field name is "forbidden" but is used purely as a display conduit.
- **Root cause:** The rule is ambiguous between "don't compute" (satisfied) and "don't reference at all" (violated).
- **Severity:** Low
- **Suggested fix:** If the rule means "don't reference": rename the field to `display_time_seconds` in `WorldSnapshotDTO` and have the backend compute the display value. If the rule means "don't compute": no change needed, current behaviour is correct.

### BUG-FB-026 — `BackendContract.send_action_stream` does not exist; SSE path is dead
- **File:line:** `frontend/api_client.py:389-412` (`HttpGameGateway.send_action_stream`) — checks `hasattr(self._contract, "send_action_stream")` which is always `False` because `BackendContract` (lines 210-324) does not define it.
- **Symptom:** Any caller of `gateway.send_action_stream(...)` over HTTP gets `NotImplementedError("SSE streaming is not supported by this contract.")`. The backend SSE endpoint `POST /api/game/action/stream` (routes_stream.py:44) exists and works, but the frontend cannot reach it.
- **Root cause:** The contract method was never implemented.
- **Severity:** Medium (SSE feature is advertised but unreachable from frontend)
- **Suggested fix:** Implement `BackendContract.send_action_stream` using `urllib.request` with streaming response, OR explicitly remove the SSE route and the gateway method until a streaming HTTP client is added.

### BUG-FB-027 — `frontend/api_client.py:get_world_state` is dead code
- **File:line:** `frontend/api_client.py:1120-1137` (module-level `get_world_state` function)
- **Symptom:** Defined but never called from anywhere in `frontend/` (verified via grep — only references are the definition itself and the `HttpGameGateway.get_world_state` wrapper which calls it). The `/api/world_state` endpoint is therefore never polled.
- **Root cause:** Leftover from B3-FIX scaffolding.
- **Severity:** Low
- **Suggested fix:** Either wire it into `game_screen.py` as a periodic polling fallback, or delete it and remove the `get_world_state` method from `GameGateway` protocol.

### BUG-FB-028 — `game_loop.session_state` has unreachable code after `return`
- **File:line:** `backend/app/services/game_loop/__init__.py:2095-2098`
- **Symptom:**
  ```python
  return state              # line 2095 — returns
  state.layers = {"scene_state": scene} if scene else {}   # line 2096 — UNREACHABLE
  return state              # line 2098 — UNREACHABLE
  ```
  The `state.layers` assignment is dead. `SessionInterfaceState` (schemas.py:138-145) does have a `layers` field? No — checking schemas.py, `SessionInterfaceState` does NOT have a `layers` field. So even if the code ran it would `AttributeError`.
- **Root cause:** Refactoring leftover.
- **Severity:** Low
- **Suggested fix:** Delete lines 2096-2098.

### BUG-FB-029 — `_run_pipeline` builds `shared_context` with empty `scene_state` and `python_engines`
- **File:line:** `backend/app/services/game_loop/__init__.py:1502-1511`
- **Symptom:** `build_context(..., scene_state={}, python_engines={}, ...)` is called BEFORE `lock_for_tick` (line 1632) populates the real scene_state. The shared_context's `scene_state` is later overwritten at line 1656 (`shared_context.scene_state = scene_state`), but `world_context_slice` (line 56 of context_builder.py: `get_world_state().build_context_slice(scene_state)`) was already computed against the empty dict and is never refreshed.
- **Root cause:** Pipeline ordering — context is built before the scene is locked.
- **Severity:** Medium (DM agent receives an empty `world_context_slice` for the first turn after a fresh boot; subsequent turns re-use the same stale slice because `shared_context` is mutated, not rebuilt).
- **Suggested fix:** Move `build_context` call to AFTER `lock_for_tick` and `shared_context.scene_state = scene_state` assignment. Re-build `world_context_slice` from the real scene_state.

### BUG-FB-030 — `WorldSnapshotDTO.player_perception` is `Optional` but frontend treats presence as truthy
- **File:line:** `backend/app/domain/snapshot.py:244-246` (DTO field) vs `frontend/game_screen.py:1095-1096, 1403-1406`
- **Symptom:** Frontend code:
  ```python
  if "player_perception" in _ws:
      scene_state["player_perception"] = _ws["player_perception"]
  ```
  When the backend serialises `WorldSnapshotDTO` via `asdict()`, `player_perception=None` becomes a key with `None` value — the `in` check passes but the assignment overwrites prior perception with `None`. So if a previous tick had perception and the current tick's snapshot has `player_perception=None` (e.g. from `_empty_snapshot` or from `/api/world_state`), the frontend loses the previously rendered manifestations.
- **Root cause:** Frontend logic assumes key presence ⇒ value present.
- **Severity:** Medium
- **Suggested fix:** Change frontend check to `if _ws.get("player_perception") is not None:`.

### BUG-FB-031 — `game_action` route allows `is_telegraph=True` to bypass pipeline entirely
- **File:line:** `backend/app/api/routes.py:407-414`
- **Symptom:** When `is_telegraph=True`, the route returns a hardcoded empty response:
  ```python
  return {
      "response": "",
      "npc_reactions": [],
      "world_changes": {},
      "journal_entry_id": None,
  }
  ```
  No `world_snapshot`, no `npc_positions`, no `confirmed_location_id`, no `will_conflict_data`. The frontend's `_map_action_response` (api_client.py:302-324) reads `world_snapshot = raw.get("world_snapshot") or {}` → empty dict. NPC positions on screen freeze.
- **Root cause:** Telegraph was designed to "not pollute player history" but the implementation drops the entire response shape, breaking the frontend contract.
- **Severity:** Medium
- **Suggested fix:** Run a lightweight `idle_tick` instead of returning an empty stub, and return the full action response shape with `world_snapshot` populated. Or, if telegraph is truly a no-op, return `{"world_snapshot": <current cached snapshot>, "confirmed_location_id": <current>, ...}` so the frontend can reconcile.

### BUG-FB-032 — `routes.py:idle_tick` does not include `confirmed_location_id` in response
- **File:line:** `backend/app/api/routes.py:247-252`
- **Symptom:** Response dict has `status`, `npc_positions`, `events`, `world_snapshot` but NOT `confirmed_location_id`. The frontend's `_map_action_response` reads it (line 323), but only for action responses, not idle_tick. Still, the spatial oracle correction that happens in `idle_tick` (game_loop/__init__.py:896-917) updates the scene_state's `location_id` but the API consumer has no way to know that the location changed during idle.
- **Root cause:** Incomplete response shape.
- **Severity:** Low
- **Suggested fix:** Add `"confirmed_location_id": _scene.get("location_id")` to the idle_tick response dict.

### BUG-FB-033 — `routes.py:game_action` constructs `turn_request` with `world_id=campaign_id`
- **File:line:** `backend/app/api/routes.py:509-516`
- **Symptom:**
  ```python
  turn_request = ChatTurnRequest(
      world_id=campaign_id,    # ← campaign_id used as world_id
      campaign_id=campaign_id,
      ...
  )
  ```
  The architecture rule says "campaign_id != location_id (cannot substitute)". The same applies to `world_id` vs `campaign_id` — they are distinct namespaces (world = static canon, campaign = runtime instance). Substituting them means `memory_manager.read_campaign_history(campaign_id)` and `persist_world_canon(world_id, ...)` end up keyed by the same string, conflating static lore with runtime state.
- **Root cause:** Shortcut taken during refactoring.
- **Severity:** Medium
- **Suggested fix:** Resolve `world_id` from `campaign_state.metadata.get("world_id", "manual")` (as `stream_turn` does at game_loop/__init__.py:1307-1309) and pass that.

### BUG-FB-034 — `routes.py:game_action` force-activates session if player is inactive
- **File:line:** `backend/app/api/routes.py:423-429`
- **Symptom:**
  ```python
  if not player_session_service.is_player_active(campaign_id, player):
      session.active = True
      session.last_heartbeat = datetime.now()
      if not player_session_service.is_player_active(campaign_id, player):
          raise HTTPException(status_code=412, ...)
  ```
  This is a "force-activate" hack that bypasses the heartbeat mechanism. If a player's session expired (no heartbeat for 120s), the next action silently re-activates it without going through `/api/player/session/{id}`. This breaks the session lifecycle invariant — `select_player` is supposed to be the only entry point.
- **Root cause:** Workaround for 412 errors during LLM latency.
- **Severity:** Medium
- **Suggested fix:** Remove the force-activate block. If 412 is too aggressive, increase `ttl_seconds` (currently 120) or have the frontend heartbeat on a timer.

### BUG-FB-035 — `scene_state_manager._scene_log_file` uses `datetime.now()` for filename
- **File:line:** `backend/app/services/scene_state_manager.py:65-68`
- **Symptom:** Log filename `scene_changes_{datetime.now().strftime('%Y%m%d')}.jsonl` is wall-clock derived. Two ticks on different real-world days write to different files even if they're in the same simulation day. This is a logging concern, not a simulation concern, but it complicates replay.
- **Root cause:** Standard daily log rotation.
- **Severity:** Low
- **Suggested fix:** Acceptable for logging. Document that `scene_changes_*.jsonl` follows real-world dates, not simulation dates.

### BUG-FB-036 — `world_diff_builder` declares `rel_changes` but never uses it
- **File:line:** `backend/app/services/state/world_diff_builder.py:45`
- **Symptom:** `rel_changes: Dict[str, Any] = {}  # P7-13: Изоляция отношений` is declared and commented "P7-13: Изоляция отношений" but never passed to `WorldStateDiff(...)` constructor at line 69-75. The `WorldStateDiff` dataclass (world_state_diff.py:12-21) has no `relationship_changes` field. So either:
  - The field was removed from `WorldStateDiff` but the builder still computes (and discards) it; OR
  - The field was supposed to be in `WorldStateDiff` but was never added.
- **Root cause:** P7-13 refactor left a dangling local variable.
- **Severity:** Low
- **Suggested fix:** Delete the `rel_changes` line in `world_diff_builder.py:45`. If relationships are supposed to transfer, add `relationship_changes: Dict[str, Any]` to `WorldStateDiff` and pass it.

### BUG-FB-037 — `phases/integration.py:578` builds snapshot with `player_perception` but the value comes from `deps.project_svc.project()` which returns the **domain** DTO, not the API DTO
- **File:line:** `backend/app/services/phases/integration.py:567-579`
- **Symptom:** `_player_perception = deps.project_svc.project(...)` returns `embodied_trace.PlayerPerceptionDTO` (domain DTO with `manifestations: dict[str, list[str]]`). This is passed to `builder.build(..., player_perception=_player_perception)`. Inside `WorldSnapshotBuilder.build` (line 94), `self._convert_perception(player_perception, tick=tick)` is called — which DOES convert domain → API DTO. So the conversion happens, but only if `_convert_perception` correctly identifies the input as domain DTO. It checks `hasattr(domain_perception, "peripheral_cues")` (line 160) — domain DTO does NOT have `peripheral_cues` (it has `active_perceptions` as list of dicts), so the check returns False and conversion proceeds. OK — this path works.
- **Root cause:** None — false alarm after deeper inspection. Documenting for completeness.
- **Severity:** None (no bug)
- **Suggested fix:** None needed. Consider adding an isinstance check for clarity.

### BUG-FB-038 — `scene_state_manager.save_scene_state` writes JSON mirror unconditionally
- **File:line:** `backend/app/services/scene_state_manager.py:519-523`
- **Symptom:** After the persistence port write (line 513), the method ALSO writes to `campaign_state.json` via `_read_campaign_json` + `_write_campaign_json` (lines 520-523). This is dual-write: SQLite (authoritative) + JSON (mirror). Comment says "TODO-A1: JSON mirror — game_screen ещё читает файлы, не API. Удалить после A1." but the mirror is still active. If SQLite and JSON drift, the frontend (which still reads JSON in some legacy paths) shows stale data.
- **Root cause:** A1 migration incomplete.
- **Severity:** Medium
- **Suggested fix:** Complete the A1 migration: have the frontend read scene_state only via API, then delete the JSON mirror write.

### BUG-FB-039 — `routes.py:npcs/{campaign_id}` reads campaign_state.json directly from disk
- **File:line:** `backend/app/api/routes.py:633-661`
- **Symptom:** The `get_npcs` endpoint opens `game_loop.saves_dir / campaign_id / "campaign_state.json"` and reads `scene_state.location_id` from it (line 649-651). This bypasses `scene_manager` and `persistence_port` — the canonical sources. If the JSON mirror is stale (see BUG-FB-038) or out of sync with SQLite, the endpoint returns wrong NPC list.
- **Root cause:** Direct file access instead of going through the service layer.
- **Severity:** Medium
- **Suggested fix:** Replace with `game_loop.scene_manager.get_scene_state(campaign_id, location_id="")` and read `npc_positions` from the returned dict.

### BUG-FB-040 — `world_routes.get_world_state` returns HTTP 304 with `HTTPException` (wrong status semantics)
- **File:line:** `backend/app/api/world_routes.py:55-57`
- **Symptom:** `raise HTTPException(status_code=304, detail="Not modified")`. FastAPI's `HTTPException` is designed for error responses (4xx/5xx). 304 is a redirect-class status that should be returned via `Response(status_code=304)` without a body. Using `HTTPException` for 304 produces a JSON body `{"detail": "Not modified"}` which is non-standard and may confuse HTTP clients.
- **Root cause:** Misuse of HTTPException for non-error status.
- **Severity:** Low
- **Suggested fix:** Return `from fastapi import Response; return Response(status_code=304)`.

### BUG-FB-041 — `routes.py:update_scene_state` does not validate protected keys against a schema
- **File:line:** `backend/app/api/routes.py:806-831`
- **Symptom:** The endpoint receives an arbitrary `scene_state: dict` from the frontend and merges it into the existing scene_state, skipping only a hardcoded `_protected_keys = {"game_time_seconds", "tick", "player_recognition", "active_traversals", "pending_tasks", "spatial_walls", "spatial_obstacles"}`. Any other key (e.g. `npc_positions`, `objects`, `environment`) can be overwritten by the frontend — violating "backend is the only source of truth". A malicious or buggy frontend can set `npc_positions["maid_lusya"]["local_position"]["x"] = 9999` and the backend will accept it.
- **Root cause:** Allow-list approach (block known-protected) instead of deny-list (allow known-writable).
- **Severity:** High (architecture violation — frontend can mutate simulation state)
- **Suggested fix:** Switch to allow-list: only accept frontend writes for `player_position` (and even that should be derived from `npc_positions["player"]`). Reject all other keys with 403.

### BUG-FB-042 — `player_session_service` only supports ONE active player per campaign
- **File:line:** `backend/app/services/player_session_service.py:30` (`self._sessions: Dict[str, PlayerSession]`) and line 195-213 (`is_player_active`)
- **Symptom:** The data structure is `{campaign_id: PlayerSession}` — only one session per campaign. Multi-player campaigns (advertised in `campaign_state_service` which has `state.players: List[PlayerInfo]`) cannot have more than one active player. `is_player_active(campaign_id, player_name)` returns False if the active session's `player_name` differs from the requested one — even if both players are legitimately active.
- **Root cause:** Single-player assumption baked into the data structure.
- **Severity:** Medium (multi-player is architecturally supported but operationally broken)
- **Suggested fix:** Change to `Dict[str, Dict[str, PlayerSession]]` (campaign_id → player_name → session). Update `select_player` to not delete existing sessions. Update `is_player_active` to look up by both keys.

### BUG-FB-043 — `campaign_state_service.get_campaign_state` silently creates empty state if file is corrupt
- **File:line:** `backend/app/services/campaign_state_service.py:65-72`
- **Symptom:** If `campaign_meta.json` exists but contains invalid JSON, the method catches `json.JSONDecodeError, ValueError` and returns a fresh empty `CampaignState(campaign_id=campaign_id)`, overwriting the file with the empty state at line 71. Real corruption (e.g. partial write due to crash) is silently swallowed and the previous state is lost.
- **Root cause:** Defensive error handling that destroys evidence.
- **Severity:** Medium
- **Suggested fix:** On JSON decode error, rename the corrupt file to `campaign_meta.json.corrupt-{timestamp}` and THEN create a fresh state. Log the corruption.

### BUG-FB-044 — `game_loop.idle_tick` increments `game_time_seconds` by hardcoded `60.0`
- **File:line:** `backend/app/services/game_loop/__init__.py:893`
- **Symptom:** `_scene["game_time_seconds"] = _scene.get("game_time_seconds", 0) + 60.0`. The 60.0 magic number is hardcoded, not derived from `constants.GAME_TICK_INTERVAL_SECONDS` (which is 10) or `TICKS_PER_DAY * SECONDS_PER_DAY`. Inconsistent with `time_advance.py` which uses `Calendar.advance(total_seconds, delta_seconds)`.
- **Root cause:** Quick hack instead of using the calendar utilities.
- **Severity:** Low
- **Suggested fix:** Use `from app.core.constants import GAME_TICK_INTERVAL_SECONDS` (or whatever the canonical "seconds per idle tick" is) and add via `Calendar.advance`.

### BUG-FB-045 — `frontend/game_screen.py` line 983 documents removed `game_time_seconds +=` but the file still has `self.game_time_seconds: int = _gts` assignments
- **File:line:** `frontend/game_screen.py:555, 1003, 1081, 1218`
- **Symptom:** The frontend stores `game_time_seconds` as instance state (`self.game_time_seconds`) and updates it from backend responses. This is display state, not simulation state — but the field name collides with the backend's simulation field, creating conceptual coupling. If the backend ever renames `game_time_seconds` to `simulation_time_seconds`, the frontend breaks.
- **Root cause:** Field name leak across the boundary.
- **Severity:** Low
- **Suggested fix:** Rename the frontend instance variable to `display_time_seconds` (or `_hud_time_seconds`) to make the boundary explicit.

### BUG-FB-046 — `scene_state_manager.commit` writes `last_save_real_time` but no consumer reads it
- **File:line:** `backend/app/services/scene_state_manager.py:1489-1491`
- **Symptom:** `scene_state["last_save_real_time"] = time.time()` is written on every commit but no code in the backend or frontend reads this field (verified via grep — only the write site matches). It's pure pollution of scene_state with wall-clock data.
- **Root cause:** ADR-047 diagnostic that was never wired to a consumer.
- **Severity:** Low
- **Suggested fix:** Delete the line, or move to a separate audit log.

### BUG-FB-047 — `WorldSnapshotDTO` is `@dataclass(frozen=True)` but `routes.py:game_action` builds the response via `asdict(ws)` and then mutates the resulting dict
- **File:line:** `backend/app/api/routes.py:540-548` and `backend/app/services/game_loop/__init__.py:1267-1271`
- **Symptom:** The frozen dataclass is converted to a dict via `asdict()` (which is fine), then the dict is mutated: `_ws_dict["dialog_journal"] = self.avatar_service.get_journal(req.campaign_id)` (line 1269). The frozen invariant is preserved on the dataclass but lost on the dict projection. Not a bug per se, but the "frozen" annotation is misleading.
- **Root cause:** asdict creates a mutable copy.
- **Severity:** Low
- **Suggested fix:** Document that `WorldSnapshotDTO` is frozen at the dataclass level but its dict projection (used for API responses) is mutable. Or build the response via `dataclasses.replace` followed by `asdict`.

### BUG-FB-048 — `routes_debug.agent_health_dashboard` returns mock agent statuses
- **File:line:** `backend/app/api/routes_debug.py:23-32`
- **Symptom:** The "Agent Health Dashboard" endpoint returns hardcoded identical status for all 5 agents (`dm`, `rules`, `npc`, `world`, `memory`):
  ```python
  agents_status = {
      "dm": {"model": active_model, "ready": has_model},
      "rules": {"model": active_model, "ready": has_model},
      ...
  }
  ```
  Comment says "mock for now, extend from orchestrator/agents". The dashboard is non-functional — it cannot distinguish per-agent health.
- **Root cause:** Unfinished feature.
- **Severity:** Low
- **Suggested fix:** Either remove the endpoint (it's misleading) or wire it to actual per-agent model pool lookups via `router.get_model_for_agent(agent_name)`.

### BUG-FB-049 — `frontend/api_client.py:BackendContract` does not include `observed_facts` in `_map_action_response`
- **File:line:** `frontend/api_client.py:302-324` vs `backend/app/models/schemas.py:80` (`ChatTurnResponse.observed_facts: List[Any]`)
- **Symptom:** Backend `ChatTurnResponse` has `observed_facts` field (Sprint P9), and `routes.py:game_action` returns it as part of the dict (because `result.observed_facts` is on the Pydantic model). But `GameActionResponse` dataclass in the frontend (api_client.py:53-72) has no `observed_facts` field, and `_map_action_response` does not extract it. So observed facts are silently dropped at the frontend boundary.
- **Root cause:** Frontend dataclass not updated when backend added the field.
- **Severity:** Low (the field is documented as "for UI and DM" but no UI consumer exists)
- **Suggested fix:** Add `observed_facts: list = field(default_factory=list)` to `GameActionResponse` and `observed_facts=raw.get("observed_facts", [])` to `_map_action_response`.

### BUG-FB-050 — `game_loop_bridge.py` does not pass `recent_dialogues` from idle_tick into TurnResult
- **File:line:** `frontend/game_loop_bridge.py:179-223` (the `_collect` coroutine only handles `done` event)
- **Symptom:** When the bridge collects SSE events from `stream_turn`, it only reads `world_snapshot` from the `done` event (line 208-220). But `idle_tick` (called separately via `_bridge.idle_tick(campaign_id)`) returns a dict that includes `world_snapshot.recent_dialogues` — the bridge passes this through unchanged. So speech bubbles work for idle_tick but not for player actions in Direct mode (because `stream_turn`'s done event has no `world_snapshot` — see BUG-FB-001).
- **Root cause:** Consequence of BUG-FB-001.
- **Severity:** Medium (covered by BUG-FB-001 fix)
- **Suggested fix:** Resolved by fixing BUG-FB-001.

---

## Summary of Cross-Cutting Themes

### A. SSE / Direct mode is structurally broken
- `stream_turn` does not yield `world_snapshot` (BUG-FB-001)
- `game_loop_bridge` does not pass `world_x`/`world_y` (BUG-FB-018)
- `BackendContract.send_action_stream` does not exist (BUG-FB-026)
- `DirectGameGateway.send_action` has dead diagnostic code (BUG-FB-016)

Net effect: the FallbackGateway's Direct path produces degraded responses (no perception, no NPC positions, no spatial oracle) whenever HTTP is unavailable. The HTTP path works, but the architecture advertises Direct mode as a first-class fallback.

### B. Persistence layer has key-format inconsistency
- `save_scene` writes `scene:{campaign_id}:{location_id}`
- `atomic_commit` writes `scene:{campaign_id}` (no location) — BUG-FB-011
- `delete_campaign` deletes `scene:{campaign_id}` + `runtime:{campaign_id}` but not `scene:{campaign_id}:{loc}` — BUG-FB-010
- `load_scene` returns "default" or first-found — ignores location suffix

Net effect: atomic_commit is silently lost; New Game does not actually reset state; cross-location NPC movement during sleep is not persisted (BUG-FB-002).

### C. DM response fallback chain is too aggressive
- `ResponseValidator` returns "Ничего не произошло." for 8 violation classes (BUG-FB-008)
- `dm_agent._fallback_narrate` returns `MSG_NOTHING_HAPPENED` on LLM failure (dm_agent.py:1064-1069)
- `MockProvider._pick_response` returns `""` in production (BUG-FB-021), triggering the empty fallback
- Fourth-wall regex rejects "игрок", "система" in any context

Net effect: any LLM response containing an English loanword, the word "игрок", or <50% Cyrillic gets replaced with the same generic fallback. The user sees "Ничего не произошло." far more often than the actual LLM failure rate.

### D. Wall clock leaks into simulation artifacts
- `WorldSnapshot.created_at = time.time()` (BUG-FB-013)
- `world_scheduler.maybe_tick` uses `datetime.now(timezone.utc)` (BUG-FB-012)
- `scene_state["last_save_real_time"] = time.time()` (BUG-FB-014, BUG-FB-046)
- `player_session_service.is_player_active` uses `datetime.now()` (BUG-FB-024 — acceptable for session lifetime)

Net effect: snapshots are non-deterministic across runs with the same input; replays produce different `created_at` and `last_save_real_time` fields.

### E. Frontend/backend DTO contract drift
- `GameActionResponse.scene_state`/`metadata` always empty (BUG-FB-015)
- `GameActionResponse.observed_facts` not extracted (BUG-FB-049)
- `BackendContract.set_continuity_mode` / `_base_url` missing (BUG-FB-004)
- `player_perception` key-present-but-None confusion (BUG-FB-030)
- `idle_tick` response missing `confirmed_location_id` (BUG-FB-032)
- `is_telegraph` returns truncated response (BUG-FB-031)

Net effect: the frontend has multiple fields that look wired but are silently always empty, making debugging difficult.

---

## Recommended Fix Order

1. **BUG-FB-002** (skip_time persistence) — fixes the reported sleep bug.
2. **BUG-FB-010, BUG-FB-011** (SQLite key format) — fixes New Game reset and atomic commit.
3. **BUG-FB-001** (stream_turn world_snapshot) — fixes Direct mode perception/NPC positions.
4. **BUG-FB-007** (world_diff_applicator life_status) — fixes cross-campaign death lock.
5. **BUG-FB-008** (ResponseValidator fallback) — fixes empty DM responses.
6. **BUG-FB-003** (double /api/api/ prefix) — unblocks launcher recovery.
7. **BUG-FB-004** (BackendContract missing methods) — unblocks frontend gateway.
8. **BUG-FB-005, BUG-FB-006** (empty snapshot fields) — completes the snapshot contract.
9. **BUG-FB-041** (scene_state frontend mutation) — closes the source-of-truth hole.
10. The remaining bugs are either low-severity or follow-on fixes from the above.

---

## Files Touched (Read Completely)

Backend: `app/api/routes.py`, `app/api/routes_stream.py`, `app/api/routes_debug.py`, `app/api/world_routes.py`, `app/main.py`, `app/services/state/{sqlite_persistence_adapter,json_persistence_adapter,persistence_port,save_format_detector,context_builder,world_diff_builder,world_diff_applicator}.py`, `app/services/integration/world_snapshot_builder.py`, `app/services/simulation/world_state.py`, `app/services/world/{time_skip_executor,world_ontology,world_tick_engine}.py`, `app/services/world_scheduler.py`, `app/services/player_avatar_service.py`, `app/services/player_session_service.py`, `app/services/game_loop_builder/accessor`, `app/services/game_loop/__init__.py` (partial — 2143 lines, focused on `run_turn`, `stream_turn`, `idle_tick`, `skip_time`, `new_game`, `_run_pipeline`, `_project_perception`), `app/services/campaign_state_service.py`, `app/services/character_service.py`, `app/services/adaptive_tick_loader.py`, `app/services/pdf_drop_importer.py`, `app/services/knowledge_ingest.py`, `app/services/dto.py`, `app/services/projection_engine.py`, `app/services/readiness.py`, `app/services/equivalence_validator.py`, `app/services/event_compiler.py`, `app/services/vram_monitor.py`, `app/services/scene_state_manager.py` (partial), `app/services/perception/perception_projector.py`, `app/services/perception/phenomenology_projection_service.py`, `app/services/llm/mock_provider.py`, `app/services/llm/factory.py`, `app/services/verbalization/response_validator.py`, `app/services/npc/l1_chronicle.py`, `app/services/combat/physiology_decay_handler.py`, `app/agents/dm_agent.py` (partial), `app/models/{world_snapshot,world_state_diff,world_continuity,schemas,npc_state,truth_state,end_screen,scene_mode,front,character}.py`, `app/core/{config,constants,runtime_config,calendar,error_logger,content_policy}.py`, `app/domain/{snapshot,embodied_trace}.py`.

Frontend: `game_screen.py` (partial — 2259 lines, focused on perception/manifestation/time/scene_state handling), `api_client.py`, `game_loop_bridge.py`, `scene_renderer.py` (partial), `game_types.py`, `constants.py`, `world_context.py` (partial), `presentation_firewall.py`, `perceptual_momentum.py` (partial), `narrative_renderer.py` (partial), `narrative_beat.py`, `end_screen_renderer.py`, `display_manager.py`, `game_menu.py` (not read in detail — 300 lines), `settings_screen.py` (not read in detail — 206 lines), `text_input.py` (not read in detail — 589 lines), `i18n.py`, `ui_theme.py`, `campaign_select.py`, `character_select.py` (not read in detail — 688 lines), `npc_name_resolver.py`, `spatial_compilation_gateway.py`, `spatial_compilation_orchestrator.py` (not read in detail — 191 lines).
