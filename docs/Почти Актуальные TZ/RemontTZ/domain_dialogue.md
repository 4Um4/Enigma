# ENIGMA — Domain Analysis: Dialogue / LLM / Task Scheduler / DM-Agent

**Scope:** Deep analysis of the dialogue/LLM/task-scheduler/DM-agent domain only.
**Codebase root:** `/home/z/my-project/analysis/Enigma-V.0.5.3.6.7_-_-_-/backend`
**Files reviewed:** 35+ across `agents/`, `services/execution/`, `services/game_loop/`, `services/input/`, `services/llm/`, `services/memory/`, `services/events/`, `services/social/`, `domain/`.

The report covers concrete bugs with file:line references, root-cause analysis, and proposed fixes.
Bug-IDs follow `BUG-DLG-###` namespace. Three production-log bugs from the task description are
triaged at the top; the remainder is sorted by severity.

---

## 0. Triage of the Three Known Production Bugs

### Bug 1 — `"DM: Ничего не произошло"` after `угрожать трактирщику ножом`

This is **multi-causal**; the three contributing bugs must all be fixed:

| Sub-bug | File:line | What happens |
|---|---|---|
| **BUG-DLG-002** (Critical) | `app/agents/dm_agent.py:245-249` | DM agent raises `ValueError` when `_has_target=False AND _has_stm=False AND _is_intro=False`. `run()` swallows it (`dm_agent.py:102`) and returns `_fallback_narrate()` → `MSG_NOTHING_HAPPENED`. This fires when target extraction (PlayerTargetExtractor) fails to resolve "трактирщику" against any NPC's `name_forms`. |
| **BUG-DLG-006** (High) | `app/services/game_loop/__init__.py:1051` | `shared_context.all_npcs_raw_snapshot` is **never assigned**. DM agent reads it via `getattr(context, "all_npcs_raw_snapshot", None)` (`dm_agent.py:451-453`). Result: the LLM gets zero NPC context (no descriptions, no voice_profile, no author_notes) and produces empty/garbage that the validator then rejects as fallback. |
| **BUG-DLG-018** (High) | `app/services/verbalization/response_validator.py:74-75, 270-272` | ResponseValidator returns `"Ничего не произошло."` on **any** violation: empty response, CJK chars, 4th-wall words ("игрок", "симуляция", "система", "механика", "интерфейс"), repeat of last response. With a 7B Qwen model and no NPC context, at least one of these fires most turns. |

### Bug 2 — Dialogue queue spammed with 10+ ambient tasks (priority=5) per tick

| Sub-bug | File:line | What happens |
|---|---|---|
| **BUG-DLG-007** (Critical) | `app/services/game_loop/task_scheduler.py:121` | `execute_pending()` enqueues **all** pending tasks for the tick into `_dialogue_queue`, but only calls `dequeue_next()` **once**. The remaining 9+ tasks stay in the heap forever (or until their speaker cooldown is reset). |
| **BUG-DLG-008** (High) | `app/services/execution/dialogue_queue.py:43-44, 49-50, 70, 93` | Cooldown / rate-limit / `enqueued_at` all use wall-clock `time.time()`, not `game_time_seconds`. Violates "TTL on game_time_seconds, not wall clock" rule. |
| **BUG-DLG-009** (High) | `app/services/execution/dialogue_queue.py:77-78` | `dequeue_next()` returns `None` for both "heap empty" and "rate limit hit" — caller cannot distinguish, so it never backs off enqueue. |

### Bug 3 — Player threats don't trigger any DM or combat response

| Sub-bug | File:line | What happens |
|---|---|---|
| **BUG-DLG-019** (Critical) | `app/services/game_loop/phase_1_input.py:276-283` | `_evt_map` is missing the keys `player_threatens`, `player_steals`, `player_insults`, `player_flees`. The `_IC_PRIORITY_MAP` (line 335-340) overrides `_raw_type` to `"player_threatens"` for THREATEN actions, but then `_evt_map.get("player_threatens", EventType.PLAYER_SPOKE)` falls back to `PLAYER_SPOKE`. |
| **BUG-DLG-020** (Critical) | `app/services/events/reaction_subscriber.py:52-65` | `_REACTION_EVENT_TYPES` contains `PLAYER_THREATENS`, `PLAYER_ATTACKS`, `PLAYER_INSULTS`, etc. — but **not** `PLAYER_SPOKE`. Combined with BUG-DLG-019, threats are published as `PLAYER_SPOKE`, so `ReactionSubscriber` and `CombatSubscriber` never fire. No `stress_delta`, no `fear_delta`, no `threat_gradient_delta` for the threatened NPC. |

---

## 1. Critical Bugs (Blocker Severity)

### BUG-DLG-001 — DM agent fallback swallows all exceptions silently
- **File:** `app/agents/dm_agent.py:91-108`
- **Symptom:** Every error path in `narrate()` → `_build_contract()` collapses to `MSG_NOTHING_HAPPENED` with no actionable trace beyond a `jsonl_log` line.
- **Root cause:** `run()` wraps `narrate()` in `try/except Exception` and unconditionally returns `self._fallback_narrate()`. Even `ValueError` from BUG-DLG-002 (contract violation) is hidden.
- **Severity:** Critical
- **Suggested fix:** Distinguish `DialogueContractViolation` (re-raise / return distinct code) from LLM-failure (fallback OK). At minimum, propagate the violation reason into the returned dict (`{"dm_response": MSG_NOTHING_HAPPENED, "error": "contract_violation", "reason": ...}`) so downstream observability can fire.

### BUG-DLG-002 — DM contract raises on missing target+STM → silent "Ничего не произошло"
- **File:** `app/agents/dm_agent.py:245-249`
- **Symptom:** If `extract_player_target` (in `dm_phase.py:49-95`) fails to resolve `трактирщику`/`трактирщика` against any NPC's `name_forms`, `shared_context.player_target_id` stays `""`. On any non-first tick (`_is_intro=False`) with empty STM, DM raises `ValueError`.
- **Root cause:** The hard contract was meant to prevent LLM hallucination of NPC replies when no NPC is being addressed. But the precondition (`_has_target=False`) is the wrong signal: it conflates "player didn't address anyone" with "target resolver failed". The resolver failing should NOT cause a silent DM blackout.
- **Severity:** Critical
- **Suggested fix:** (a) If `raw_input` contains a known Russian noun/role ("трактирщик", "кузнец", "страж") but resolver returned empty, log a WARN and proceed with a generic narrative instead of raising. (b) Better: relax the gate to "if player addressed nobody AND there's nothing to narrate (no events, no NPC moves)", which is the actual semantic.

### BUG-DLG-003 — `all_npcs_raw_snapshot` is never assigned to shared_context
- **File:** `app/services/game_loop/__init__.py:1051` (only `all_npcs_raw` is set, not `all_npcs_raw_snapshot`)
- **Symptom:** DM agent reads `getattr(context, "all_npcs_raw_snapshot", None)` (`dm_agent.py:451-453`) → always `None`. The entire "Контекст NPC (кто они и как говорят)" prompt block (`dm_agent.py:449-485`) is skipped, so the 7B model has no idea who the NPCs are (no description, no title, no voice_profile, no author_notes).
- **Root cause:** Field is declared in `PipelineContext` (`app/models/pipeline_context.py:43-45`) and read in two places, but no code path ever assigns it.
- **Severity:** Critical (this is a major contributor to Bug 1)
- **Suggested fix:** After `state.shared_context.all_npcs_raw = self._resolve_npcs_snapshot(req.campaign_id)` (line 1051), also set `state.shared_context.all_npcs_raw_snapshot = state.shared_context.all_npcs_raw`.

### BUG-DLG-004 — Player threats published as PLAYER_SPOKE, bypassing all reaction subscribers
- **File:** `app/services/game_loop/phase_1_input.py:276-283, 335-348`
- **Symptom:** Player types `угрожать трактирщику ножом`. IntentCompressor correctly classifies as `THREATEN`. The override at line 346 sets `_raw_type = "player_threatens"`. But `_evt_map.get("player_threatens", EventType.PLAYER_SPOKE)` falls back to `PLAYER_SPOKE`. Result: `ReactionSubscriber`, `CombatSubscriber` never receive the event.
- **Root cause:** `_evt_map` only covers `dialogue`, `player_interacts`, `attack`, `player_attacks`, `move`, `stealth`. The override map (`_IC_PRIORITY_MAP` line 335-340) emits keys that have no matching entry in `_evt_map`.
- **Severity:** Critical (root cause of Bug 3)
- **Suggested fix:** Add missing entries to `_evt_map`:
  ```python
  "player_threatens": EventType.PLAYER_THREATENS,
  "player_steals":    EventType.THEFT,
  "player_insults":   EventType.PLAYER_INSULTS,
  "player_flees":     EventType.PLAYER_MOVED,
  "intimidation":     EventType.INTIMIDATION,
  ```

### BUG-DLG-005 — Dialogue queue drains only 1 task per tick while enqueuing all
- **File:** `app/services/game_loop/task_scheduler.py:92-138`
- **Symptom:** `execute_pending()` iterates `pending` and pushes **every** task into `_dialogue_queue` (line 112-119). Then it calls `dequeue_next()` exactly once (line 121) and runs **only that one** (line 136-138). If `post_decision.py:164` appended 10 ambient tasks this tick (because 10 NPCs had COMMUNICATE intents), 9 of them are left in the heap. Next tick adds 10 more. Heap grows unboundedly.
- **Root cause:** Drain loop is missing. The function name `execute_pending` implies it processes all pending tasks, but the implementation processes at most 1.
- **Severity:** Critical (root cause of Bug 2)
- **Suggested fix:** Wrap dequeue in a `while` loop bounded by `max_tasks_per_tick` (e.g., 3) AND by `MAX_RATE_PER_MINUTE` (already enforced inside `dequeue_next`):
  ```python
  processed = 0
  while processed < self._max_tasks_per_tick:
      _eligible = self._dialogue_queue.dequeue_next()
      if not _eligible:
          break
      ...
      processed += 1
  ```
  Also add a hard cap on heap size in `enqueue()` (drop lowest-priority task when heap > 50).

### BUG-DLG-006 — DialogueQueue uses wall-clock time for cooldown / rate-limit
- **File:** `app/services/execution/dialogue_queue.py:43-44, 49-50, 57, 70, 73, 93`
- **Symptom:** `COOLDOWN_PER_NPC_SEC = 30` (real seconds), `MAX_RATE_PER_MINUTE = 20`, `enqueued_at = time.time()`. If the game is paused (idle_tick not running) or the player AFKs for 5 minutes, the queue "thinks" 5 minutes have passed and resets all cooldowns.
- **Root cause:** TTL is bound to wall clock, violating the "TTL on game_time_seconds, not wall clock" architectural rule.
- **Severity:** High
- **Suggested fix:** Pass `game_time_seconds` from `scene_state` into `enqueue()` / `dequeue_next()`. Replace `time.time()` with `game_time_seconds`. The `_minute_count`/`_minute_start` window also needs to be a sliding window over game_time, not wall clock.

### BUG-DLG-007 — `clear_dialogue_session` uses non-sorted key, breaks per-pair semantics
- **File:** `app/services/memory/memory_manager.py:100`
- **Symptom:** `get_dialogue_session` (line 76-77) builds the key from `tuple(sorted((npc_id, partner_id)))` — symmetric. But `clear_dialogue_session` uses `f"{campaign_id}:{npc_id}:{partner_id}"` (line 100) — **non-symmetric**. If the caller invokes `clear_dialogue_session(campaign, "player", "maid_lusya")`, the lookup key becomes `campaign:player:maid_lusya` while the stored key is `campaign:maid_lusya:player` → session is NOT cleared, leaks memory.
- **Root cause:** Key construction was unified in `get_dialogue_session` (V8-DLG-13 FIX) but the corresponding change in `clear_dialogue_session` was missed.
- **Severity:** High
- **Suggested fix:** Use the same sorted-pair logic:
  ```python
  pair_key = tuple(sorted((npc_id, partner_id)))
  key = f"{campaign_id}:{pair_key[0]}:{pair_key[1]}"
  ```

### BUG-DLG-008 — `clear_all_dialogue_sessions` parses the wrong field as `npc_id`
- **File:** `app/services/memory/memory_manager.py:127-139`
- **Symptom:** Iterates stored keys (format `campaign:npc_a:npc_b` from sorted pair), then `parts = key.split(":")` and `npc_id = parts[1]`. Then calls `clear_dialogue_session(campaign_id, npc_id)` with default `partner_id="player"`. This only works if `parts[1]` happens to be the NPC and `parts[2]` happens to be "player". For NPC-NPC sessions (e.g. `campaign:maid_lusya:tornin`), `clear_dialogue_session(campaign, "maid_lusya", "player")` looks up `campaign:maid_lusya:player` which doesn't exist → silent no-op.
- **Root cause:** `parts[2]` (the actual partner) is dropped on the floor.
- **Severity:** High
- **Suggested fix:** Parse both IDs from the key:
  ```python
  parts = key.split(":")
  if len(parts) >= 3:
      _, npc_a, npc_b = parts[0], parts[1], parts[2]
      self.clear_dialogue_session(campaign_id, npc_a, npc_b)
  ```
  (After fixing BUG-DLG-007, this will work correctly because `clear_dialogue_session` will use the sorted key.)

### BUG-DLG-009 — `dequeue_next` swallows rate-limit returns as "empty queue"
- **File:** `app/services/execution/dialogue_queue.py:77-78`
- **Symptom:** Returns `None` both when heap is empty AND when minute rate limit is hit. Caller (`task_scheduler.py:121-123`) treats both as "nothing to do" and stops. Combined with BUG-DLG-005, the queue can never recover from a rate-limit spike.
- **Root cause:** Conflated return codes.
- **Severity:** High
- **Suggested fix:** Either raise a custom `RateLimited` exception, or return a `dequeue_status` enum (`EMPTY`/`RATE_LIMITED`/`OK`). Caller should log when rate-limited so the operator sees the queue backing up.

### BUG-DLG-010 — DM agent reads L2 narrative_cache (recalled_facts)
- **File:** `app/services/game_loop/dm_phase.py:65-82`; consumed at `app/agents/dm_agent.py:233-236`
- **Symptom:** `dm_phase` extracts `narrative_cache` for the target NPC, runs `memory_manager.recall(...)`, and injects the resulting memory lines into `shared_context.npc_l2_memory_block`. DM agent then writes them into the LLM prompt as `"L2 Memory block"`. This violates the rule: **"DM-agent reads ONLY observed_state and embodied_traces (no real_state, stress_delta, recalled_facts)"**.
- **Root cause:** The "BUG-DL-11 FIX" comment claims to inject L2 memory, but the architectural rule explicitly forbids recalled_facts to DM-agent.
- **Severity:** High (architectural violation)
- **Suggested fix:** Remove the L2 memory block from DM agent's prompt. If the design intent is to let the DM narrate continuity, the NPC's `narrative_cache` should instead manifest through NPC speech (which is already in STM) — not by giving DM direct access to NPC memories.

### BUG-DLG-011 — `DialogueUpdateExtractor` silently fails on every call
- **File:** `app/services/memory/dialogue_update_extractor.py:38-49`
- **Symptom:** Three independent bugs in `extract()`:
  1. `agent_name="dialogue_extractor"` is **not** in `DEFAULT_AGENT_CAPABILITY_MAP` (`router.py:133-140`) → falls back to `Capability.GENERAL`, which is not the intent.
  2. `params={"max_tokens": 200, "temperature": 0.1, "response_format": {"type": "json_object"}}` — a `dict`, not a `GenerationParams` instance. Provider code expects `GenerationParams` and will fail attribute access.
  3. `response.text` — `request_for_agent` returns a `str`, not an object. `AttributeError` is raised, caught by the bare `except Exception`, and the function returns an empty `DialogueUpdate()`. **No claims, no questions, no topic updates are ever extracted.**
- **Root cause:** Three independent typos / mismatches.
- **Severity:** High
- **Suggested fix:**
  - Add `"dialogue_extractor": Capability.FACT_EXTRACTION` to `DEFAULT_AGENT_CAPABILITY_MAP` in `router.py`.
  - Use `GenerationParams(max_tokens=200, temperature=0.1, response_format={"type": "json_object"})`.
  - Replace `response.text` with `response` (it's already a string).
  - Or remove the call site entirely if the LLM cost is not justified.

### BUG-DLG-012 — `NpcDialogueSubscriber._process_canonical` has duplicate `except` block (dead code)
- **File:** `app/services/events/npc_dialogue_subscriber.py:178, 201`
- **Symptom:** The try block (starting at line 124) has two `except Exception as mem_err:` handlers — the second one is unreachable. The first one (line 178-200) swallows the original error and instead schedules an L2 deferred write. The actual error (e.g. `add_dialogue_turn` KeyError) is logged only as a generic warning, and the L2 deferred write fires even when it shouldn't (e.g. for legitimate non-memory errors).
- **Root cause:** Looks like a copy-paste merge artifact — the second `except` was meant to be removed when the L2 deferred write logic was added.
- **Severity:** High
- **Suggested fix:** Delete the duplicate `except` block (lines 201-202). Restructure: log the failure, then EITHER schedule L2 deferred write OR re-raise, not both. The current behaviour (always scheduling L2 write on any error) is suspect.

### BUG-DLG-013 — `DialogueExecutor._generate_with_router` swallows `DialogueContractViolation`
- **File:** `app/services/execution/dialogue_executor.py:213-230`
- **Symptom:** `execute()` declares a specific handler for `DialogueContractViolation` (line 92-101) returning a proper error `Artifact`. But `_generate_with_router` has its own broad `except Exception` (line 228-230) that returns `""` on **any** error — including `DialogueContractViolation`. So the contract violation is converted to an empty string, then `execute()` (line 103-104) replaces empty text with `[Заглушка] {task.owner_id} молчит.` and emits a successful `dialogue_line` artifact. The contract violation is invisible to the caller.
- **Root cause:** Nested exception handler shadows the outer one.
- **Severity:** High
- **Suggested fix:** Re-raise `DialogueContractViolation` from `_generate_with_router`:
  ```python
  except DialogueContractViolation:
      raise  # propagate to execute()
  except Exception as e:
      logger.error(...)
      return ""
  ```

### BUG-DLG-014 — `thread_id` is generated but never used
- **File:** `app/services/phases/post_decision.py:67-69, 122, 159`; declared in `app/domain/communication.py:64, 89` and `app/services/memory/dialogue_session.py:55`
- **Symptom:** `thread_id` is generated in `post_decision.py`, passed through `DialogueRequest`, reconstructed in `task_scheduler._reconstruct_task` (line 272), stored in `DialogueRequest` and `DialogueSession`. But **no code ever reads it**. `MemoryManager.get_dialogue_session` keys sessions by `(campaign_id, sorted_pair)` — `thread_id` is ignored. The "per-pair sessions keyed `campaign:npc:partner`" rule is satisfied by the sorted pair, not by `thread_id`.
- **Root cause:** Half-implemented feature. The intent was probably to support multi-thread dialogues between the same pair (e.g. two parallel topics), but the lookup logic was never wired.
- **Severity:** Medium (false sense of isolation; if a real second thread is needed, it will silently collide)
- **Suggested fix:** Either (a) delete the field and all code that sets it, or (b) incorporate `thread_id` into `get_dialogue_session`'s key:
  ```python
  key = f"{campaign_id}:{pair_key[0]}:{pair_key[1]}:{thread_id}"
  ```
  Default `thread_id=""` keeps backward compatibility.

### BUG-DLG-015 — `_is_light_dialog` references non-existent `SANDBOX_MEDIUM` ActionType
- **File:** `app/agents/dm_agent.py:162-165`
- **Symptom:** `_is_light_dialog = _action_type in ("SANDBOX_MILD", "SANDBOX_MEDIUM") and not self._has_real_check_flag(rules_result)`. `ActionType` enum (`app/agents/rules_agent.py:23-33`) has `SANDBOX_MILD`, `SANDBOX_SOCIAL`, `SANDBOX_PHYSICAL` — **no `SANDBOX_MEDIUM`**. So `_is_light_dialog` only fires for `SANDBOX_MILD`, never for "medium" actions. The check is dead for the second case.
- **Root cause:** Either typo (`MEDIUM` vs `SOCIAL`/`PHYSICAL`) or stale enum value.
- **Severity:** Low
- **Suggested fix:** Replace `"SANDBOX_MEDIUM"` with `"SANDBOX_SOCIAL"` (or remove it if only `SANDBOX_MILD` was intended).

### BUG-DLG-016 — `ReputationEngine.get_all_faction_states` calls `List[Any](...)` (TypeError)
- **File:** `app/services/social/reputation_engine.py:344`
- **Symptom:** `List[Any](self._factions[fid].npc_members)` — `List[Any]` is a generic type alias, not callable. Calling this method raises `TypeError: 'types.GenericAlias' object is not callable`.
- **Root cause:** Confused `list(...)` with the typing alias.
- **Severity:** Medium (only triggers when API/UI calls `get_all_faction_states`)
- **Suggested fix:** `list(self._factions[fid].npc_members)`.

### BUG-DLG-017 — `dialogue_materializer` always emits `listener_ids=[]` (SocialInputProjector must recompute)
- **File:** `app/services/execution/dialogue_materializer.py:48-50`
- **Symptom:** Materializer hard-codes `"listener_ids": []`. Comment says "SocialInputProjector заполнит его на основе радиуса и LoS". But `SocialInputProjector._on_event` (`social_input_projector.py:55-56`) just appends to `_pending_events` — it does NOT mutate the event's payload. When `handle()` runs in Phase 8, it does call `filter_perceiving_npcs` (line 86-95) to recompute listeners — but only if `_sq is not None`. If `spatial_query` is missing (e.g. test/sandbox), `_listeners` stays `[]` and **nobody** hears the line.
- **Root cause:** Materializer delegates listener computation, but the hand-off is implicit.
- **Severity:** Medium
- **Suggested fix:** Either compute listeners in the materializer (preferred, since it has `event.radius`), or document that `social_input_projector.handle()` MUST be called even when `spatial_query` is None (fallback: all NPCs in scene).

### BUG-DLG-018 — `ResponseValidator._breaks_fourth_wall` over-triggers on DM narrative
- **File:** `app/services/verbalization/response_validator.py:115-138, 74-75`
- **Symptom:** Forbids words `игрок`, `игроки`, `симуляция`, `система`, `механика`, `интерфейс`. The DM agent's prompt itself contains these words (e.g. `dm_agent.py:284` "Игрок обращается напрямую..."). If the 7B LLM echoes any of them in its response, validator returns fallback `"Ничего не произошло."`. Especially likely when DM is asked to describe what the player is doing.
- **Root cause:** Word-list is too aggressive for a narrative DM (vs an NPC line). DM legitimately needs to refer to "the player" sometimes.
- **Severity:** High (significant contributor to Bug 1)
- **Suggested fix:** Either (a) use a separate, looser word-list for DM narrative (only forbid `симуляция`, `интерфейс`, `механика`); or (b) require the forbidden word to appear in direct speech quotes (e.g. `«игрок»`) rather than narrative.

### BUG-DLG-019 — Player threat events route to PLAYER_SPOKE (see Bug 3 above)
See §0.Bug 3.

### BUG-DLG-020 — ReactionSubscriber doesn't subscribe to PLAYER_SPOKE (see Bug 3 above)
See §0.Bug 3.

### BUG-DLG-021 — `DirectiveInterpretationSubscriber` not on EventBus; called inline with mock event
- **File:** `app/services/social/directive_interpretation_subscriber.py:21-24`; called at `app/services/tick_orchestrator.py:726-741, 899-912`
- **Symptom:** Despite its name, this "subscriber" is **not subscribed to EventBus**. It's invoked synchronously in two places in `tick_orchestrator._process_player_dm_action` / `_process_player_action`, with a hand-crafted `types.SimpleNamespace(payload=...)` mock event. The architectural rule says: "DirectiveInterpretationSubscriber MUST receive all_npcs_raw injection" — this is satisfied (line 738/911 passes `ctx.all_npcs_raw`). But the design bypasses the EventBus entirely, so other systems cannot observe the directive interpretation event.
- **Root cause:** Tight coupling for synchronous delta application.
- **Severity:** Medium (architectural concern, not a functional bug)
- **Suggested fix:** Either rename the class (e.g. `DirectiveInterpreter`) to reflect that it's not a subscriber, or refactor to a true subscriber that emits deltas via Phase 8 buffer.

### BUG-DLG-022 — `task_scheduler.process_tasks` is dead code with wrong signature
- **File:** `app/services/game_loop/task_scheduler.py:71-90`
- **Symptom:** `process_tasks(self, scene_state, max_tasks_per_tick=2)` is never called from anywhere (`grep` finds only the definition + comment in `task_scheduler.py:2`). It also calls `self._process_tasks_async(scene_state, tasks_to_process)` (line 87) without `campaign_id` or `_task_type`, so even if invoked, ambient tasks would be routed to the canonical (LLM) executor.
- **Root cause:** Legacy method kept as "convenience API" but never wired.
- **Severity:** Low
- **Suggested fix:** Delete `process_tasks`. If kept, fix the call to `_process_tasks_async(scene_state, tasks_to_process, campaign_id=scene_state.get('campaign_id', ''), _task_type='canonical')` and add a unit test.

### BUG-DLG-023 — `IntentEventAdapter.to_event` mapping for non-attack intents is dead code
- **File:** `app/services/events/intent_event_adapter.py:38-46`; consumer at `app/services/phases/post_decision.py:34-217`
- **Symptom:** `IntentEventAdapter.to_event` maps `intent_type` → `event_type`: `attack → actor_attacks`, `help → help`, `theft/steal/rob → theft`, `intimidate → intimidation`. But in `post_decision.py:38-165`, **all non-attack intents** are routed to `pending_tasks` (`continue` at line 165) and never reach `adapter.to_event(intent)` (line 167). So the mappings for `help`, `theft`, `intimidate` are dead code. Only `attack` ever passes through.
- **Root cause:** The `to_event` mapping was written before the universal-task-layer refactor; the dialogue task path was supposed to call `to_event` for the published `NPC_SPOKE` event, but `dialogue_materializer` does that itself (with a different mapping).
- **Severity:** Medium (dead code masks intent)
- **Suggested fix:** Either delete the unused branches in `to_event`, or refactor post_decision to call `to_event` for ALL intents and then either publish (for `attack`) or queue (for others).

### BUG-DLG-024 — `NpcDialogueSubscriber._process_canonical` records `target_id=listener` (semantically inverted)
- **File:** `app/services/events/npc_dialogue_subscriber.py:138`
- **Symptom:** When NPC_A speaks to NPC_B, the listener's session gets `add_dialogue_turn(speaker=A, text=..., target_id=B, partner_id=A)`. The `target_id=listener` (B) is set instead of the actual addressee. Then `DialogueSession.to_prompt_block` (`dialogue_session.py:154-158`) renders `speaker → target_id: text` — for the listener's own session, this becomes `A → B: text` which is technically correct (A addressed B). But the speaker's own session (line 144-153) gets `target_id=listener` (B) — so the speaker's session shows `A → B: text` as well, which is also correct. So this is **semantically OK** but confusingly named.
- **Severity:** Low (cosmetic)
- **Suggested fix:** Rename the parameter `target_id` to `addressee_id` for clarity. No functional change.

### BUG-DLG-025 — `NpcDialogueSubscriber` drops ambient lines with no listener
- **File:** `app/services/events/npc_dialogue_subscriber.py:70-71`
- **Symptom:** `if not speaker or not listener or listener == "all": return`. If a speaker soliloquizes (`target_id="soliloquy"` set in `task_scheduler._process_tasks_async:174`) or ambient line has no target, the subscriber does nothing — no STM write, no relationship update, no L1 chronicle. The line is published to EventBus but disappears from memory.
- **Root cause:** The guard was meant to skip malformed events, but it also skips legitimate soliloquies.
- **Severity:** Medium
- **Suggested fix:** Allow `listener="soliloquy"` or `listener=""` to pass through, but skip the relationship update (since there's no listener to update). STM write should still happen so the speaker remembers their own words.

### BUG-DLG-026 — `dialogue_executor.execute` doesn't pass `thread_id` to memory_manager
- **File:** `app/services/execution/dialogue_executor.py:171-187`
- **Symptom:** `_stm_text = self._memory_manager.get_stm_prompt_block_pair(campaign_id, owner, target)` — uses only the pair, ignoring `req.thread_id`. Combined with BUG-DLG-014, this means STM is shared across all threads between the same pair.
- **Root cause:** Same as BUG-DLG-014 — `thread_id` was planned but never wired.
- **Severity:** Medium
- **Suggested fix:** Wire `thread_id` through `MemoryManager.get_stm_prompt_block_pair` to `get_dialogue_session` (requires BUG-DLG-014 fix first).

### BUG-DLG-027 — `task_scheduler._reconstruct_task` catches only `ValueError` for TaskKind
- **File:** `app/services/game_loop/task_scheduler.py:282-285`
- **Symptom:** `try: kind = TaskKind(kind_str) except ValueError: kind = TaskKind.DIALOGUE`. This swallows any unknown `kind_str` (e.g. "trade", "craft") as DIALOGUE — silent misrouting. Trade/Craft tasks would be sent to DialogueExecutor, which would fail with "Invalid payload for DialogueExecutor" (line 70-78).
- **Root cause:** Defensive coding without logging.
- **Severity:** Low
- **Suggested fix:** Log a WARN when falling back: `logger.warning(f"[SCHEDULER] Unknown TaskKind '{kind_str}', defaulting to DIALOGUE")`.

### BUG-DLG-028 — `WorldSimulationAgent.tick()` calls LLM with no context
- **File:** `app/agents/world_sim_agent.py:135-149`
- **Symptom:** `tick(world_id)` calls `self.simulate(location="unknown", actions=[], current_events=[])`. The LLM is invoked with literally `location="unknown"` and empty context. The agent is invoked from `world_scheduler` (outside TickOrchestrator), so it doesn't violate the "no LLM in core" rule, but it produces useless output.
- **Root cause:** Backward-compat shim that has no real caller.
- **Severity:** Low
- **Suggested fix:** Either remove `tick()` or have it pull recent events from MemoryManager before calling `simulate()`.

### BUG-DLG-029 — `dm_phase.py` silently swallows STM and L2 memory extraction errors
- **File:** `app/services/game_loop/dm_phase.py:62, 81`
- **Symptom:** Both `try` blocks have `except Exception:` with no logging. If `memory_manager.get_stm_prompt_block` raises (e.g. sqlite locked), `shared_context.npc_stm_block_targeted` stays `""` and DM has no STM context. No log entry is written.
- **Root cause:** Lazy `except Exception:` without `logger.debug`.
- **Severity:** Medium
- **Suggested fix:** Replace `except Exception:` with `except Exception as e: logger.warning(f"[STM_EXTRACT] failed: {e}"); shared_context.npc_stm_block_targeted = ""`.

### BUG-DLG-030 — `IntentEventAdapter.to_event` inconsistent threat mapping
- **File:** `app/services/events/intent_event_adapter.py:38-46`
- **Symptom:** Maps `intent_type == "intimidate"` → `event_type="intimidation"`. But DMRouter classifies "угрожать" as `"player_threatens"`, not `"intimidate"`. So a threat never matches the `intimidate` branch.
- **Root cause:** Two different vocabularies for the same concept.
- **Severity:** Low (dead code, see BUG-DLG-023)
- **Suggested fix:** Standardize on one vocabulary. Either rename DMRouter's `player_threatens` to `intimidate`, or rename the IntentEventAdapter mapping.

### BUG-DLG-031 — `dm_phase.py` writes player's input to STM as `intent="dialogue"` regardless of actual intent
- **File:** `app/services/game_loop/dm_phase.py:160-169`
- **Symptom:** `game_loop.memory_manager.add_dialogue_turn(... intent="dialogue", tone="" ...)` with TODO comments "LLM-classify". So a threat ("угрожать") gets stored in STM as `intent="dialogue"`. When NPC later recalls this STM, the intent metadata is wrong.
- **Root cause:** TODO not implemented.
- **Severity:** Low
- **Suggested fix:** Pass `intent=shared_context.action_type` (already classified by DMRouter).

### BUG-DLG-032 — `dialogue_executor.execute` invokes `confession_parser.parse_and_record` synchronously
- **File:** `app/services/execution/dialogue_executor.py:107-116`
- **Symptom:** After the LLM call, `parse_and_record` is invoked synchronously. If `NpcConfessionParser` itself uses LLM (it does — `mvp_tavern_controller.py:65-70` wires `NpcConfessionParser`), this doubles LLM calls per dialogue line. The second LLM call also blocks the executor thread pool.
- **Root cause:** Synchronous call inside the dialogue artifact generation.
- **Severity:** Medium
- **Suggested fix:** Defer confession parsing to a separate background task / next-tick processing. The dialogue artifact should be returned as soon as the line is generated.

### BUG-DLG-033 — `task_scheduler._process_tasks_async` writes `recent_dialogues` with both wall-clock `timestamp` and `game_time`
- **File:** `app/services/game_loop/task_scheduler.py:236-237`
- **Symptom:** `_dlg_entry = {"timestamp": time.time(), "game_time": scene_state.get("game_time_seconds", 0.0)}`. The `timestamp` field is described as "для UI staleness", but `get_recent_dialogues` (line 61-69) filters by `game_time`, never by `timestamp`. So `timestamp` is dead data.
- **Root cause:** Two competing time fields, only one is used.
- **Severity:** Low
- **Suggested fix:** Remove the `timestamp` field (UI should use `game_time` for staleness too).

### BUG-DLG-034 — `dialogue_queue` doesn't enforce priority inversion for stale low-priority tasks
- **File:** `app/services/execution/dialogue_queue.py:84-105`
- **Symptom:** `dequeue_next` pops from the heap (highest priority first), but if the highest-priority speaker is on cooldown, the task is pushed back (`temp_skipped.append(candidate)`, line 95). After the loop, all skipped tasks are pushed back (line 104-105). If a high-priority speaker is on cooldown for 30 seconds, the queue keeps re-iterating them every tick, blocking lower-priority speakers.
- **Root cause:** No aging / priority boost for skipped tasks.
- **Severity:** Medium
- **Suggested fix:** Either (a) skip to the next-available speaker (don't push back), or (b) age priority by `(now - enqueued_at) / 60` to gradually promote stale tasks.

### BUG-DLG-035 — `social_engine.propagate` skips witnesses from results, but `propagation.py` re-checks
- **File:** `app/services/social/propagation.py:101-103`
- **Symptom:** `if pr.npc_id in _witness_ids: continue` — drops propagation results for witnesses, because witnesses "already got direct deltas". But `_witness_ids` is built from `shared_context.npc_contexts` (line 84-86) — i.e. NPCs with a context entry. If an NPC witnessed the event but wasn't included in `npc_contexts` (e.g. spatial filter excluded them), they're dropped from both direct deltas AND propagation. Net result: the NPC learns nothing.
- **Root cause:** Assumes `npc_contexts` is the same set as direct witnesses, but `npc_contexts` is built earlier in the pipeline and may be filtered.
- **Severity:** Medium
- **Suggested fix:** Either use `ctx.shared_context.perceiving_npcs` (post Phase 8 filter) as the witness set, or remove the deduplication (SocialEngine already starts BFS from hop=1, skipping witnesses).

### BUG-DLG-036 — `fate_tracker.update_state` raises on out-of-range values, crashing TICK_COMPLETED
- **File:** `app/services/social/fate_tracker.py:22-25`
- **Symptom:** `if not (0.0 <= stability <= 1.0): raise ValueError(...)`. Caller (`mvp_tavern_controller.py:130-132`) computes `stability = 1.0 - stress/100` which is correctly clamped via `max(0.0, min(1.0, ...))`. But `threat = max(0.0, min(1.0, float(...threat_gradient...)))` — if `threat_gradient` is missing from `perceptual_kernel`, `.get(..., 0.0)` returns 0.0, OK. But if it's a string ("0.5") or None, `float(None)` raises TypeError. The `try/except` in `on_tick_completed` (not shown) catches and logs, but TICK_COMPLETED event still fails for that NPC.
- **Root cause:** Defensive type check missing.
- **Severity:** Low
- **Suggested fix:** Wrap in `try: stability = float(...) except (TypeError, ValueError): stability = 0.0`.

### BUG-DLG-037 — `mvp_tavern_controller.on_tick_completed` uses `npc.get("id", npc.get("npc_id"))` — wrong key priority
- **File:** `app/services/social/mvp_tavern_controller.py:125`
- **Symptom:** `npc_id = npc.get("id", npc.get("npc_id"))`. Most NPC dicts in this codebase use `"npc_id"` as the primary key (see `_process_tasks_async:191` which uses `nid = ... if nid != "player" and nid != task.owner_id` — implies `nid` comes from `.keys()` of `npc_positions`, which is `npc_id`). Using `"id"` first means if a dict has both `"id"` (legacy) and `"npc_id"` (canonical), it picks `"id"`. If only `"npc_id"` exists, the fallback works. Inconsistent with the rest of the codebase.
- **Root cause:** Inconsistent key preference.
- **Severity:** Low
- **Suggested fix:** `npc_id = npc.get("npc_id") or npc.get("id")`.

### BUG-DLG-038 — `_recent_dialogues` list grows unbounded between ticks
- **File:** `app/services/game_loop/task_scheduler.py:48, 239-243`
- **Symptom:** `self._recent_dialogues.append(_dlg_entry)` (line 239). The only cleanup is in `get_recent_dialogues` (line 64-68), which filters by TTL. But `get_recent_dialogues` is only called from `idle_tick` (line 1002) and `_run_pipeline` (line 1235) — if neither is called for a long time (e.g. server idle), the list grows. Also, `scene_state.setdefault("recent_dialogues", []).append(_dlg_entry)` (line 241-243) duplicates the entry into `scene_state` — but `scene_state` is reset between sessions, so this list is bounded by scene lifetime. The `self._recent_dialogues` list is per-TaskScheduler instance (singleton), so it accumulates across all scenes.
- **Root cause:** No max-length cap.
- **Severity:** Low
- **Suggested fix:** Add `self._recent_dialogues = self._recent_dialogues[-100:]` after append.

### BUG-DLG-039 — `dialogue_materializer` returns `Iterable[Any]` but is consumed as list
- **File:** `app/services/execution/dialogue_materializer.py:18, 39-56`
- **Symptom:** Method signature returns `Iterable[Any]`, implementation returns `[event]` (list). Caller `task_scheduler._process_tasks_async:216-218`:
  ```python
  events = materializer.materialize(artifact)
  for ev in events:
      bus.publish(ev)
  ```
  Works for lists. But if a future materializer returns a generator, the second iteration (e.g. `if artifact.result_type == "dialogue_line" and events:` at line 227) would consume it.
- **Root cause:** Loose typing.
- **Severity:** Low
- **Suggested fix:** Either declare return type as `List[Any]` and `return [event]`, or have caller materialize the iterable into a list once: `events = list(materializer.materialize(artifact))`.

### BUG-DLG-040 — `task_scheduler` doesn't track failed tasks for retry
- **File:** `app/services/game_loop/task_scheduler.py:244-248`
- **Symptom:** `task.state = TaskState.FINISHED  # Пока без сложного ретрая` — failed tasks are marked FINISHED and silently dropped. No retry, no DLQ, no observability beyond a single `logger.error`.
- **Root cause:** Comment acknowledges the limitation.
- **Severity:** Low
- **Suggested fix:** Implement a simple retry: if `retry_count < 2`, re-enqueue with reduced priority. Otherwise push to a dead-letter list for inspection.

---

## 2. Architectural Rule Compliance Audit

| Rule | Status | Notes |
|---|---|---|
| LLM forbidden inside TickOrchestrator/DecisionHub | ✅ Pass | `tick_orchestrator.py` has zero LLM imports. `decision_hub.py` only mentions LLM in docstrings. LLM is invoked from `GameLoop._run_pipeline` (line 1698 `_intent_compressor.compress`) which is outside TickOrchestrator. |
| DM-agent reads ONLY observed_state and embodied_traces | ❌ **FAIL** | BUG-DLG-010: DM agent reads `npc_l2_memory_block` (recalled_facts from narrative_cache) via `context.npc_l2_memory_block` (set in `dm_phase.py:65-82`). Also reads `combat_data` (line 600), `python_engines` (line 564), `reaction_order` (line 648) — these are observable facts, OK. |
| Dialogues flow: Need → Intent → Task → Materializer → Event | ✅ Pass | `post_decision.py` builds `DialogueRequest` → `QueuedTask` → `pending_tasks` → `TaskScheduler.execute_pending` → `DialogueExecutor.execute` → `Artifact` → `DialogueMaterializer.materialize` → `EventDTO` → `EventBus.publish`. |
| TaskScheduler executes Tasks via TaskExecutor, returns Artifact | ✅ Pass | `task_scheduler._process_tasks_async:206` calls `executor.execute(task)` returning `Iterable[Artifact]`. |
| Materializer publishes WorldEvent to EventBus | ✅ Pass | `task_scheduler.py:218` `bus.publish(ev)`. |
| DialogueExecutor must inject STM-block for NPC<->NPC | ✅ Pass | `dialogue_executor.py:171-187` calls `memory_manager.get_stm_prompt_block_pair`. |
| Per-pair sessions keyed `campaign:npc:partner` | ⚠️ Partial | BUG-DLG-007: `get_dialogue_session` uses sorted pair (correct), `clear_dialogue_session` doesn't (broken). BUG-DLG-008: `clear_all_dialogue_sessions` parses wrong field. |
| `thread_id` required for dialogue continuity | ❌ **FAIL** | BUG-DLG-014: `thread_id` is generated and passed through DTOs but never used in lookup logic. |
| LLM cannot be called without STM (except greeting/approach) | ✅ Pass | `dialogue_executor.py:180-184` raises `DialogueContractViolation` if `_stm_text` is empty and `intent_type` not in `("greeting", "approach")`. (But see BUG-DLG-013 — the violation is then swallowed.) |
| TTL on `game_time_seconds`, not wall clock | ❌ **FAIL** | BUG-DLG-006: `DialogueQueue` uses `time.time()` for cooldown, rate-limit, and `enqueued_at`. |
| DirectiveInterpretationSubscriber MUST receive all_npcs_raw injection | ✅ Pass | `tick_orchestrator.py:738, 911` passes `ctx.all_npcs_raw`. (But subscriber is not on EventBus — see BUG-DLG-021.) |
| WillpowerGate ONE invocation per cycle | ✅ Pass | `tick_orchestrator.py:614` calls `_apply_willpower_gate` once in `_run_core_phases`. `run_phase_1_input` (`phases/input.py:58`) is the single entry point. |
| ActionWindup: ATTACK has 2-tick preparation | ✅ Pass | `app/core/constants.py:186`: `ATTACK_WINDUP_DURATION_TICKS = 2`. `post_decision.py:205` uses it. |
| DIALOGUE goes to `scene_state["pending_tasks"]` | ✅ Pass | `post_decision.py:164` `ctx.scene_state["pending_tasks"].append(_task_dict)`. |
| Subscribers subscribed to EventBus | ⚠️ Partial | NpcDialogueSubscriber, DialogueMemorySubscriber, SocialInputProjector, SocialSubscriber, PerceptionSubscriber, ReactionSubscriber, CombatSubscriber — all subscribed. DirectiveInterpretationSubscriber is NOT (BUG-DLG-021). |

---

## 3. TODO / FIXME / Silent-Failure Inventory

| File:line | Marker | Note |
|---|---|---|
| `dm_phase.py:166-167` | `TODO: LLM-classify` | `intent` and `tone` hardcoded to "dialogue"/"" when writing to STM. See BUG-DLG-031. |
| `intent_compressor.py:7` | `TODO` | Mentions future extensions for multi-model, adaptive prompting. Not a bug. |
| `llm_compressor_client.py:7` | `TODO` | Same as above. |
| `mvp_tavern_controller.py:101` | `V8-MVP-18 TODO` | Dilemmas should load from separate canon. Not a bug. |
| `propagation.py:12` | `TODO` | Migrate SocialEngine out of game_loop. Not a bug. |
| `dm_agent.py:102-108` | `except Exception` | Swallows all DM errors → fallback. BUG-DLG-001. |
| `dm_agent.py:300-307` | `except Exception` | Scene description build error silently logged. |
| `dm_agent.py:637-644` | `except Exception` | Scene events block error silently logged. |
| `dm_agent.py:726-727` | `except Exception` | System prompt load failure logged as warning, fallback used. OK. |
| `dm_agent.py:866` | `except Exception` | CJK retry JSON parse failure → fallback to raw text. OK. |
| `dm_agent.py:1028-1029` | `except Exception` | Router stream-end notification failure silenced with "B5-FIX" comment. |
| `dm_phase.py:62, 81` | `except Exception` | STM and L2 memory extraction silently fail. BUG-DLG-029. |
| `dialogue_update_extractor.py:47-49` | `except Exception` | All extractor failures silently return empty `DialogueUpdate`. BUG-DLG-011. |
| `dialogue_memory_subscriber.py:68` | `except Exception` | All dialogue memory writes silently fail. |
| `npc_dialogue_subscriber.py:178, 201` | duplicate `except` | BUG-DLG-012. |
| `task_scheduler.py:150` | `except Exception` | Task reconstruction failure silently `continue`s. |
| `task_scheduler.py:219` | `except Exception` | Materializer failure silently logged. |
| `memory_manager.py:304` | `except Exception` | `assess_beliefs` failure logged as warning. OK. |
| `memory_manager.py:348` | `except Exception` | EventMemory restoration failure logged as warning. OK. |
| `agent_runner.py:82` | `except Exception` | "B5-FIX silent failure suppressed" — abort_generation failure silenced. |
| `game_loop/__init__.py:1572` | `except Exception` | "B5-FIX silent failure suppressed" — Death Guard NPC positions fetch. |

---

## 4. Disconnected Code / Wiring Gaps

1. **`all_npcs_raw_snapshot`** is read by DM agent but never assigned (BUG-DLG-003).
2. **`thread_id`** flows through `DialogueRequest` → `QueuedTask` → `_reconstruct_task` → `DialogueRequest` but is never used in `MemoryManager` lookups (BUG-DLG-014, BUG-DLG-026).
3. **`task_scheduler.process_tasks`** is dead code (BUG-DLG-022).
4. **`IntentEventAdapter.to_event`** branches for `help`/`theft`/`intimidate` are dead code (BUG-DLG-023).
5. **`DialogueUpdateExtractor`** is wired (`npc_dialogue_subscriber.py:128-131`) but always fails silently (BUG-DLG-011). Effective behaviour: zero structured updates to STM (claims, questions, topics).
6. **`WorldSimulationAgent.tick()`** is invoked from `world_scheduler` but produces no useful output (BUG-DLG-028).
7. **`reaction_subscriber._REACTION_RULES`** has entries for `player_threatens`, `player_steals`, `player_insults` — but those events are never published (routed to `PLAYER_SPOKE` by BUG-DLG-019). The rules are dead code in practice.
8. **`_evt_map`** in `phase_1_input.py:276-283` has only 6 entries; the `_IC_PRIORITY_MAP` (line 335-340) emits 5 different keys (`attack`, `player_threatens`, `player_steals`, `move`, ...) — only 2 of which (`attack`, `move`) are in `_evt_map`. The other 3 fall back to `PLAYER_SPOKE`.

---

## 5. Recommended Fix Priority

| Priority | Bug IDs | Impact |
|---|---|---|
| **P0 — Critical (fix today)** | BUG-DLG-002, BUG-DLG-003, BUG-DLG-004, BUG-DLG-005, BUG-DLG-018, BUG-DLG-019, BUG-DLG-020 | Directly cause Bug 1, Bug 2, Bug 3 from production logs. |
| **P1 — High (fix this sprint)** | BUG-DLG-001, BUG-DLG-006, BUG-DLG-007, BUG-DLG-008, BUG-DLG-009, BUG-DLG-010, BUG-DLG-011, BUG-DLG-012, BUG-DLG-013 | Silent failures, memory leaks, architectural violations. |
| **P2 — Medium (fix next sprint)** | BUG-DLG-014, BUG-DLG-016, BUG-DLG-017, BUG-DLG-021, BUG-DLG-023, BUG-DLG-025, BUG-DLG-026, BUG-DLG-029, BUG-DLG-032, BUG-DLG-034, BUG-DLG-035 | Code quality, observability, edge cases. |
| **P3 — Low (cleanup)** | BUG-DLG-015, BUG-DLG-022, BUG-DLG-024, BUG-DLG-027, BUG-DLG-028, BUG-DLG-030, BUG-DLG-031, BUG-DLG-033, BUG-DLG-036, BUG-DLG-037, BUG-DLG-038, BUG-DLG-039, BUG-DLG-040 | Dead code, cosmetic, defensive hardening. |

---

## 6. Summary

The dialogue/LLM/task-scheduler/DM-agent domain has **40 tracked bugs**, of which **7 are critical** and **9 are high severity**. The three production-reported bugs (silent DM fallback, queue spam, ignored threats) are all explained by concrete code-level defects:

- **Bug 1 (silent DM)**: tri-causal — DM contract raises on missing target (BUG-DLG-002), `all_npcs_raw_snapshot` is never wired (BUG-DLG-003), and `ResponseValidator` over-triggers on 4th-wall words (BUG-DLG-018).
- **Bug 2 (queue spam)**: `execute_pending` enqueues all but drains only one (BUG-DLG-005), compounded by wall-clock TTL (BUG-DLG-006) and indistinguishable "empty vs rate-limited" return (BUG-DLG-009).
- **Bug 3 (threats ignored)**: `_evt_map` missing `player_threatens` key (BUG-DLG-019) routes threats to `PLAYER_SPOKE`, which `ReactionSubscriber` doesn't subscribe to (BUG-DLG-020).

The architectural rule audit reveals **2 hard violations**:
- DM agent reads `npc_l2_memory_block` (recalled_facts) — BUG-DLG-010.
- `DialogueQueue` uses wall-clock time for TTL — BUG-DLG-006.

Plus **1 missing wiring** (`thread_id` never used — BUG-DLG-014) and **1 dead subscriber pattern** (`DirectiveInterpretationSubscriber` not on EventBus — BUG-DLG-021).

Fixing the P0 bugs (7 items) should resolve all three production-reported issues. P1 bugs address silent failures that mask future regressions.
