# NPC Speech Silence — Root Cause Investigation

**Status:** `MULTIPLE ROOT CAUSES FOUND` (two source-level defects confirmed); **the complete runtime cause of total silence is not yet established**.  
**Repository:** `4Um4/Enigma`  
**Inspected ref:** `V.0.5.4.6.8_Говори!_3`  
**Investigation mode:** GitHub source inspection only. No production files changed. No game/pygame session or local LLM was run in this investigation.

> Evidence labels: **VERIFIED** = directly supported by source in the inspected ref; **PARTIALLY VERIFIED** = source path is present but end-to-end/runtime behavior is not demonstrated; **UNVERIFIED** = requires runtime evidence; **PROPOSED** = suggested correction/test, not implemented.

---

## 1. Executive summary

Two concrete source-level defects were confirmed.

1. **D1 — dialogue cache reads the last materialized event, not the speech event. VERIFIED.** In `TaskScheduler._process_tasks_async`, all events returned by `DialogueMaterializer` are iterated, but the subsequent `_dlg_entry` is built from the loop variable `ev`. When the materializer returns `NPC_SPOKE` followed by `COMMUNICATION_CLAIM`, `ev` refers to the claim event. That event carries a proposition but no speech `text`. The resulting `recent_dialogues` entry can therefore have an empty text. The frontend only injects a bubble when both speaker ID and visible text are non-empty. This is a confirmed cause of missing bubbles for proposition-bearing speech, **not** a cause of the NPC failing to generate/speak.
2. **D2 — social target selection narrows to high-trust candidates before checking distance. VERIFIED.** `SocialTargetResolver.resolve` builds `_high_trust` and, if it is non-empty, searches only that subset. A distant high-trust NPC can therefore exclude a nearby neutral/trusted-enough NPC before the 5.0 distance and line-of-sight checks. DecisionHub calls this resolver for verbal social intents, subject to earlier target-resolution branches. This can prevent selection of the nearby conversational partner. The exact downstream outcome in the user's live session is **not proven**.

A third important fact limits the scope of both findings: `DialogueMaterializer` deliberately emits `NPC_SPOKE` first for every successful dialogue artifact, and emits `COMMUNICATION_CLAIM` separately only when a proposition is verified. Thus D1 corrupts the bubble cache after speech; it does not retract the speech event. If the observed symptom is total silence in both NPC→player and NPC→NPC, D1 is insufficient as a complete explanation.

The spatial code does use `local_position` for Euclidean distance and returns `999.0` when either local position is absent. This is **VERIFIED**. However, no actual in-game NPC coordinate pair was available, so the hypothesis that visually adjacent NPCs are far apart in the simulation remains **UNVERIFIED**. There is also a structural risk: `SpatialQueryService.distance()` compares local XY values and does not itself check that both entities belong to the same location or coordinate frame.

**Final verdict:** `MULTIPLE ROOT CAUSES FOUND` for specific failure modes (D1 bubble loss; D2 target-selection bias). `NO COMPLETE ROOT CAUSE YET` for the full report of NPCs not speaking to the player or one another. Runtime tracing is still required.

---

## 2. Branch and evidence boundary

- Inspected Git ref: `V.0.5.4.6.8_Говори!_3`.
- GitHub content API returned individual file/blob SHAs, not the branch commit SHA. This report does not misrepresent a blob SHA as the commit SHA.
- The repository path `docs/reports/NPC_SPEECH_SILENCE_ROOT_CAUSE.md` did not exist at the inspected ref before this report was created.
- This was source inspection through GitHub. No local archive, runtime log, live game session, pygame rendering, or production LLM call was available here.
- No source code, tests, configuration, or game data were modified. Only this diagnostic Markdown report is added.

### Source files inspected

| File | Blob SHA returned by GitHub | Relevant area |
|---|---|---|
| `backend/app/services/game_loop/task_scheduler.py` | `dc631b6e3ec3eaf02676e4226f4beb74ee9b6e6c` | `_process_tasks_async`, lines 840–880; queue/outbox path |
| `backend/app/services/execution/dialogue_materializer.py` | `eafa2462093cd4eef592ef8a5465394b1260f960` | `materialize`, lines 62–135 |
| `backend/app/services/npc/social_target_resolver.py` | `c27a1c518ee3798cef82702d3376126b98c12ad7` | `resolve`, lines 22–85 |
| `backend/app/services/npc/decision_hub.py` | `27ed04134d5b34e95f96d895584c27d7413d64a6` | target resolution, lines 2110–2168 |
| `backend/app/services/spatial/spatial_query_service.py` | `3e42bc7d34055c80a1ac4e3431d8377d1b538ddf` | `distance` and `visibility`, lines 40–80 |
| `backend/app/services/spatial/spatial_runtime.py` | `e3f8d712f4e73142ecdcc2068b705e007ad86a13` | `euclidean_distance`, `_local`, LOS |
| `frontend/game_screen.py` | `bee18fc546692aeba236e9f4d52e19d0869e0121` | bubble injection, lines 1308–1324; repeated idle/action paths |
| `backend/app/services/game_loop/game_loop.py` | `3473677f40fd8f42f920da8853b67248e8dc4e72` | recent dialogue projection, lines 1123–1135 and other call sites |

Blob SHAs identify the exact file versions read; they are not branch commit SHAs.

---

## 3. Symptom matrix

| Symptom | Source-level finding | Status |
|---|---|---|
| NPC generated a line but bubble is absent when a proposition is also emitted | D1 can place empty claim text into `recent_dialogues`; frontend rejects empty visible text | **VERIFIED** |
| NPC cannot select a nearby social target when a distant high-trust candidate exists | D2 high-trust pool is selected before distance filtering | **VERIFIED** |
| NPC never forms TALK / another verbal intent | DecisionHub has TALK in proactive intents, but actual selection in the reported session was not observed | **UNVERIFIED** |
| NPC task is never enqueued / is deduplicated / expires | Scheduler contains multiple gates; no live trace was available | **UNVERIFIED** |
| LLM generates an empty/invalid NPC response | Executor runtime was not available | **UNVERIFIED** |
| NPC_SPOKE is published but not perceived by the player | Materializer source path is present; actual perception path was not run | **PARTIALLY VERIFIED** |
| Frontend receives a non-empty perceived narrative but fails to inject bubble | Frontend injection condition and assignment are present; rendering was not run | **PARTIALLY VERIFIED** |
| NPCs are visually close but spatially distant to the backend | Distance uses local XY; no real positions were measured | **UNVERIFIED** |
| DM's answer is actually an NPC utterance | No such equivalence is established by the inspected files | **REJECTED as an assumption** |

---

## 4. Production flow: NPC → player

### 4.1 DecisionHub target resolution

**VERIFIED:** `DecisionHub._resolve_target` contains a dedicated direct-player dialogue branch. It returns `event.actor_id` (the player) only when the verbal intent, event type, actor, target, and semantic action satisfy the explicit conditions.

Relevant source: `backend/app/services/npc/decision_hub.py`, approximately lines 2130–2147 in the inspected file.

The branch requires:
- intent is in `self._VERBAL_INTENTS`;
- event type is one of `player_interacts`, `player_spoke`, `dialogue`;
- `event.actor_id == "player"`;
- `event.target_id == state.npc_id`;
- `event.semantic_action == "DIALOGUE"`.

**Consequence:** the existence of a DM response does not prove that this NPC reply branch ran. The NPC still needs a qualifying event and a verbal intent. The direct reply helper cannot manufacture a reply if the upstream decision did not produce the required intent.

### 4.2 Dialogue task execution

**PARTIALLY VERIFIED:** `TaskScheduler` reconstructs a dialogue task, selects the dialogue executor, executes it, and sends successful artifacts to the materializer. The scheduler logs `[TASK_SCHED] dialogue executed` after a successful artifact.

Relevant source: `backend/app/services/game_loop/task_scheduler.py`, `_process_tasks_async`.

**UNVERIFIED:** no live trace proves that the user's NPC→player interaction reaches this executor, that the configured router returns valid text, or that the artifact is successful.

### 4.3 Materialization

**VERIFIED:** `DialogueMaterializer.materialize()` returns no events for unsuccessful/non-dialogue artifacts. For a successful dialogue artifact it appends an `NPC_SPOKE` event first, containing:
- `source = speaker_id`;
- `payload.text = data["text"]`;
- `payload.target_id`;
- exposure/tone/intent metadata.

If the artifact contains a proposition, the materializer separately verifies it and may append `COMMUNICATION_CLAIM` second. The claim payload contains proposition metadata but no speech text.

Source: `backend/app/services/execution/dialogue_materializer.py:62–135`.

This ordering is central to D1.

---

## 5. Production flow: NPC → NPC

### 5.1 DecisionHub and social target selection

**VERIFIED:** `DecisionHub._resolve_target` imports and calls `SocialTargetResolver.resolve()` for verbal intents and `APPROACH`, after higher-priority explicit/causal/pending-response target branches. If the resolver returns no target, DecisionHub falls back to `event.actor_id` when that actor is not the NPC itself.

Source: `backend/app/services/npc/decision_hub.py:2110–2168`.

This nuance matters: a resolver miss does **not** universally mean `None`; the fallback may still assign the event actor. Therefore D2 is a target-selection defect, but its exact gameplay effect depends on the triggering event and actor.

### 5.2 D2 — trust-first pool excludes nearby candidates

**VERIFIED.** In `backend/app/services/npc/social_target_resolver.py:51–83`:

1. Candidate NPCs are filtered only for hostile trust below `SOCIAL_TRUST_HOSTILE_THRESHOLD`.
2. The resolver builds `_high_trust` from candidates whose trust exceeds `SOCIAL_TRUST_HIGH_THRESHOLD`.
3. If at least one high-trust candidate exists, `_search_pool = _high_trust`; otherwise it uses all filtered candidates.
4. Only after that does it calculate distance and check the 5.0 radius and line of sight.

Therefore a far high-trust candidate can exclude a near neutral candidate before spatial eligibility is checked.

Illustrative counterexample (logic illustration, not measured game data):
- NPC H: high trust, distance 11 m;
- NPC N: neutral trust, distance 2 m;
- high-trust subset contains H only;
- H fails the 5 m gate;
- N is never examined;
- resolver returns `None`.

**PROPOSED correction:** apply physical eligibility (same relevant spatial frame, within hearing/speech radius, LOS) before preference ranking. Then rank the physically eligible set by trust/relevance. Do not simply remove trust semantics or choose a candidate outside the allowed range.

**Required regression test:** high-trust NPC outside radius + neutral NPC inside radius must select the nearby eligible NPC. Also test: no eligible candidates; all hostile candidates; blocked LOS; one eligible high-trust candidate; multiple eligible candidates.

### 5.3 Scheduler fallback is a separate target path

**VERIFIED:** if a reconstructed `DialogueRequest` has no `target_id`, `TaskScheduler._process_tasks_async` builds a `SpatialQueryService` from `scene_state["npc_positions"]`, checks other NPCs at distance `<= 5.0`, and chooses one deterministically using `KernelRNG`. If none qualifies, it retains `SELF_TALK_SENTINEL`.

Source: `backend/app/services/game_loop/task_scheduler.py:767–808`.

This is a second target-selection path and should not be conflated with D2. It can be reached when a task arrives without a target; it does not prove the main DecisionHub resolver is bypassed in every case.

---

## 6. D1 — wrong event used to populate speech-bubble cache

**Status: VERIFIED source defect.**

### 6.1 Materializer's event contract

Source: `backend/app/services/execution/dialogue_materializer.py:90–135`.

For a successful dialogue:
1. `NPC_SPOKE` is appended with the actual text.
2. If a proposition is present and verified, `COMMUNICATION_CLAIM` is appended afterwards.
3. The `COMMUNICATION_CLAIM` payload contains `target_id`, `proposition`, `speech_act`, `tick`, `verified_by`; it does not contain `text`.

### 6.2 Scheduler's faulty selection

Source: `backend/app/services/game_loop/task_scheduler.py:840–880`.

The code iterates:

```python
for ev in events:
    _events_collected.append(ev)
```

Then it builds `_dlg_entry` from `ev.source` and `ev.payload.get("text", "")`.

In Python, after the loop, `ev` refers to the last event. When the event list is:
`[NPC_SPOKE, COMMUNICATION_CLAIM]`,
the cache entry is built from `COMMUNICATION_CLAIM`, not `NPC_SPOKE`.

The text becomes `""`.

### 6.3 Frontend suppression

Source: `frontend/game_screen.py:1308–1324` (and parallel injection blocks around lines 1482–1496 and 1705–1720).

The frontend reads:
- `speaker_id = _narr.get("speaker_id", "")`;
- `visible_text = _narr.get("visible_text", "")`.

It injects a bubble only under:
`if _spk_id and _dlg_text:`.

Thus an empty dialogue text is intentionally not rendered.

### 6.4 Minimal proposed fix

Do not read speech fields from the loop's last `ev`. Select the actual speech event explicitly:

```python
speech_event = next(
    (event for event in events if event.type == EventType.NPC_SPOKE.value),
    None,
)
if speech_event is not None:
    payload = speech_event.payload
    _dlg_entry = {
        "speaker_id": speech_event.source,
        "target_id": payload.get("target_id", ""),
        "text": payload.get("text", ""),
        "exposure": payload.get("exposure", "normal"),
        # preserve existing timestamp / real_ts / game_time fields
    }
```

Adapt enum/string comparison to the actual `EventDTO.type` contract in the file; do not blindly paste if its type representation differs.

### 6.5 Required tests

1. Materializer returns `NPC_SPOKE` only: cache contains the speech text.
2. Materializer returns `NPC_SPOKE` then `COMMUNICATION_CLAIM`: cache still contains the speech text.
3. Proposition rejected: `NPC_SPOKE` still populates cache.
4. No `NPC_SPOKE` event: no dialogue cache entry is created.
5. Outbox drain copies the same non-empty text into `_recent_dialogues` and `scene_state["recent_dialogues"]`.
6. Frontend projection receives non-empty `visible_text` and injects one bubble.

Do not change the event ordering or suppress `NPC_SPOKE` to hide this defect.

---

## 7. Coordinate and hearing audit

### 7.1 What the code actually measures

**VERIFIED:** `SpatialQueryService.distance(a, b)` delegates to `euclidean_distance(pos_a, pos_b)`.

Source: `backend/app/services/spatial/spatial_query_service.py:40–48`.

**VERIFIED:** `euclidean_distance` uses `local_position.x/y` only. If either entity lacks `local_position`, it returns `999.0`.

Source: `backend/app/services/spatial/spatial_runtime.py`, function `euclidean_distance`.

**VERIFIED:** `SpatialQueryService.visibility` also reads each entity's `local_position` and tests LOS in the provided scene state.

Source: `backend/app/services/spatial/spatial_query_service.py:71–80`.

**VERIFIED:** `SocialTargetResolver` uses a hard-coded `_SPEAK_RADIUS = 5.0` and requires both distance within radius and LOS.

Source: `backend/app/services/npc/social_target_resolver.py:75–80`.

### 7.2 What is not proven

- No actual NPC pair from the user's affected game session was measured.
- No proof that their visual positions and backend `local_position` values diverged.
- No proof that a missing `local_position` is the active cause in the user's session.
- No proof that the NPC→player direct reply path is blocked by the same 5 m resolver; direct-player dialogue has an earlier explicit target branch.
- No runtime proof that all NPCs in `all_npc_ids` belong to one location/coordinate frame.

### 7.3 Spatial architecture risk

`SpatialQueryService.distance()` calls `euclidean_distance` directly. That function compares local XY and does not validate `location_id`, graph node, scene identity, or coordinate-frame identity. The separate `resolve_distance_between_entities()` function in `spatial_runtime.py` does check location and graph nodes before combining graph distance with local offsets, but the inspected `SpatialQueryService.distance()` path does not call it.

This is a **VERIFIED structural inconsistency**, but whether it causes incorrect distances in the affected scene is **UNVERIFIED**.

### 7.4 Required runtime probe

For two NPCs visibly close together, and separately for NPC↔player, log one snapshot containing:
- entity IDs;
- `location_id` for both;
- scene/campaign ID;
- `position` / `node_id`;
- raw `local_position.x/y`;
- coordinate-frame identifier if one exists;
- `SpatialQueryService.distance()` result;
- graph-aware `resolve_distance_between_entities()` result where applicable;
- configured speech/hearing radius;
- LOS result;
- final target-resolver result.

Run the same probe for a known far pair as a control. Do not change the radius until these measurements identify the source of divergence.

---

## 8. DM response versus NPC speech

**PARTIALLY VERIFIED.**

The inspected source establishes distinct responsibilities:
- DM-facing response/reaction presentation can exist independently of the NPC speech artifact pipeline.
- Actual NPC speech in the examined backend path is represented by a successful dialogue artifact, materialized as `NPC_SPOKE`, collected into the task worker outbox, drained into recent-dialogue state, projected into `perceived_narratives`, and then consumed by the frontend bubble injector.

A DM response is therefore not evidence that an NPC utterance occurred. To establish the exact route used in the affected session, runtime logs must identify whether a `DialogueRequest` was created and whether the corresponding `DialogueExecutor` ran.

**UNVERIFIED:** the precise DM response call site and UI reaction path were not exhaustively traced in this source-only pass. This report does not claim that the DM and NPC routes are fully mapped.

---

## 9. Hypothesis matrix H1–H8

| Hypothesis | Status | Evidence / conclusion |
|---|---|---|
| H1. DM and NPC use different speech channels | **PARTIALLY VERIFIED** | NPC speech requires dialogue artifact → `NPC_SPOKE` → recent dialogue projection → perceived narrative → bubble injection. DM text alone does not prove that path. Exact DM route needs runtime/source follow-up. |
| H2. TALK intent is never formed | **UNVERIFIED** | TALK is included in `PROACTIVE_INTENTS`; this does not prove that it wins scoring in the affected session. Need scores trace and intent per NPC/tick. |
| H3. Intent/task is lost in queue or execution | **UNVERIFIED** | Scheduler has enqueue/dedup/dispatch/reconstruction/executor paths. No session trace was available. |
| H4. Validators or fail-closed gates suppress speech | **PARTIALLY VERIFIED** | Materializer's no-verifier fail-closed branch suppresses only `COMMUNICATION_CLAIM`; source explicitly says `NPC_SPOKE` remains published. A broader executor/response validator failure remains untested. |
| H5. Coordinates/hearing prevent interaction | **PARTIALLY VERIFIED** | Local XY-only distance, 999 fallback, 5 m resolver radius and LOS are confirmed. Actual affected entity positions and cross-frame mismatch are not measured. |
| H6. NPC_SPOKE is created but UI does not show bubble | **PARTIALLY VERIFIED / D1 VERIFIED for one case** | D1 creates empty cache text for proposition-bearing speech; frontend skips empty visible text. Other UI/render failures are untested. |
| H7. DM response is mistaken for NPC speech | **PARTIALLY VERIFIED** | DM answer is not proof of NPC_SPOKE. Full DM response route not exhaustively mapped. |
| H8. Production wiring differs from tests | **UNVERIFIED** | TaskScheduler source supports router injection and warns if router is absent, but the active live instance, router health, LLM connection and frontend bridge were not observed. |

---

## 10. Existing tests and evidence limits

The prior investigator's supplied summary says three speech test files passed 26 tests under Python 3.12 with a stub router, while the project expects Python 3.14. That is user-provided investigation evidence, not a result independently rerun or verified in this GitHub-only pass.

The test names and counts alone do not prove the full runtime path. The following distinctions must be preserved:
- unit/component tests can prove local target selection or event materialization;
- mocked router tests cannot prove live local LLM connectivity;
- manually constructed events cannot prove perception or autonomous intent formation;
- backend tests cannot prove pygame bubble rendering;
- a successful `NPC_SPOKE` event cannot prove the UI received a non-empty perceived narrative.

No test suite was executed in this investigation. A Python 3.14 environment, the correct project dependencies, and a runtime harness are needed to reproduce the relevant tests.

---

## 11. Root causes and confidence

### D1 — bubble text sourced from wrong event
- **Status:** VERIFIED.
- **Scope:** proposition-bearing dialogue where the materializer emits `NPC_SPOKE` followed by `COMMUNICATION_CLAIM`.
- **Effect:** `recent_dialogues` may contain empty text; frontend refuses to create a bubble.
- **Does not explain:** absence of generated NPC speech or missing `NPC_SPOKE` event.

### D2 — trust-first target pool
- **Status:** VERIFIED.
- **Scope:** verbal social intents that reach `SocialTargetResolver`, when at least one high-trust candidate exists but is outside the 5 m/LOS eligible set while a lower-trust candidate is physically eligible.
- **Effect:** nearby candidate is ignored; resolver can return no target. DecisionHub may still fall back to event actor.
- **Does not explain:** direct NPC→player replies with an explicit player target; does not prove total silence.

### D3 — local-coordinate distance lacks frame/location validation
- **Status:** VERIFIED structural risk; actual symptom impact UNVERIFIED.
- **Scope:** callers of `SpatialQueryService.distance()` when entities can come from different locations or coordinate frames.
- **Effect:** mathematically valid XY distance can be semantically invalid if frames differ; absent local position yields 999.0.
- **Does not explain:** speech bubble loss after a speech event has already been generated.

### Full silence
- **Status:** NOT YET EXPLAINED.
- The confirmed defects can explain missing bubbles for a subset of generated speech and failed target selection in a subset of NPC-NPC interactions. They do not establish why no NPC speaks to the player at all, or why all NPC-NPC dialogue is absent.

---

## 12. Minimal fix plan (not implemented)

### Priority 0 — fix D1
1. Build `_dlg_entry` from the `NPC_SPOKE` event, not the last event in the materializer output.
2. Keep claim publication and verification independent of speech caching.
3. Add the six regression cases in §6.5.
4. Verify non-empty text reaches both `_recent_dialogues` and `scene_state["recent_dialogues"]`.

### Priority 1 — fix D2 without changing social design
1. Build a set of physically eligible candidates first (distance + LOS + valid same spatial frame).
2. Apply trust preference only within that eligible set.
3. Preserve hostile-exclusion semantics.
4. Add the regression matrix in §5.2.
5. Do not increase the 5 m radius as a workaround.

### Priority 2 — close spatial frame uncertainty
1. Determine whether all entities passed to each `SpatialQueryService` instance are guaranteed to share one local coordinate frame.
2. If not guaranteed, add an explicit same-location/frame gate or use the canonical graph-aware distance contract.
3. Add tests for same local XY in different locations, missing local positions, valid origin (0,0), and same-location pairs.
4. Do not modify world/editor coordinate semantics without game-designer approval.

### Priority 3 — diagnose total silence
Instrument one trace ID across:
- NPC tick / event perception;
- DecisionHub intent and `scores_trace`;
- resolved target;
- enqueue and dedup outcome;
- task dequeue/reconstruction;
- executor start/end;
- LLM request/result;
- materializer output event types;
- outbox push/drain;
- `recent_dialogues` count;
- `perceived_narratives` count;
- frontend bubble injection and renderer draw.

For NPC→player and NPC→NPC, run separate scenarios. Record the **first missing transition**, not just the final absence of a bubble.

---

## 13. Runtime log checklist

Capture the following tags for the same campaign/tick/NPC/task:
- `[SOCIAL_TARGET]`
- `[DLG_ENQ_DEDUP]`
- `[TASK_SCHED]`
- `[SCHEDULER]`
- executor/LLM request and response logs
- `NPC_SPOKE` event publication
- `[IDLE_TICK_WS] recent_dialogues_count`
- perceived narrative count
- `[BUBBLE_INJECT]`

Interpretation:
- No verbal intent → inspect DecisionHub scores and upstream event/context.
- Intent but no target → inspect explicit target, causal addressee, pending response target, SocialTargetResolver and spatial measurements.
- Target but no enqueue → inspect enqueue/dedup/admission.
- Enqueued but no executor → inspect task reconstruction, task state, TTL, interruption and dispatch.
- Executor fails or empty text → inspect router/LLM, timeout, response contract and validation.
- `NPC_SPOKE` exists but no recent dialogue → inspect D1 and worker outbox/drain.
- Recent dialogue exists but no perceived narrative → inspect NarrativeProjector/perception filtering and player coordinates.
- Perceived narrative has non-empty visible text but no bubble → inspect frontend update path, speaker ID lookup, bubble lifetime and renderer.
- Bubble injection log exists but nothing visible → inspect screen-coordinate conversion, viewport/camera, clipping, draw order and expiry.

---

## 14. Remaining unknowns / next probe

The following evidence is still required before claiming the whole silence defect is solved:

1. Backend log from one affected session, including a single NPC→player attempt and a single NPC→NPC attempt.
2. Frontend log from the same session.
3. Runtime snapshot of `npc_positions` for player and the two NPCs, including `location_id`, node and local XY.
4. Runtime `DecisionHub` scores and chosen intent/target for those NPCs.
5. Confirmation that the active production `TaskScheduler` has a functioning router and executor.
6. Proof that a non-empty `NPC_SPOKE` payload reaches the game loop and `perceived_narratives`.
7. Actual pygame rendering check.

Do not infer that the 5 m threshold is the root cause until a logged distance and the exact rejecting gate are observed.

---

## 15. Final verdict

`MULTIPLE ROOT CAUSES FOUND` — D1 and D2 are confirmed source defects; D3 is a confirmed spatial-contract risk.

`NO COMPLETE ROOT CAUSE YET — MORE RUNTIME EVIDENCE REQUIRED` for the full symptom in which all NPCs remain silent to the player and to each other.

**Recommended order:** correct D1 (bubble data integrity), correct D2 (target selection after physical eligibility), then capture a correlated runtime trace to identify the first failure responsible for total silence. No production code was changed by this investigation.
