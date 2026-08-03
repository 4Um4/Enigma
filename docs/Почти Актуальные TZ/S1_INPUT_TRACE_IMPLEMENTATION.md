# S1 Implementation Plan — Input Ingress Trace (v1.0, code-verified)

> **Документ:** Точное техническое задание на S1 (Phase A.1) Input Trace
> **Версия проекта:** Enigma V.0.5.3.6.8
> **Дата:** 2026-08-03
> **Статус:** Ready for implementation
> **Принцип:** Observational only. Не чинит pipeline. Не мутирует мир. Только записывает.

---

## 0. Цели и границы (согласованы обоими LLM)

### Что S1 делает
- Создаёт `input_id` как **root correlation ID** — первичный ключ, через который будущие S2/S3/S4 будут связывать интерпретации, события и causal frames с конкретным вводом игрока
- Сохраняет **immutable raw input** (L0) — никогда не перезаписывается, даже если интерпретация изменится
- Фиксирует **context snapshot reference** (snapshot_id, tick, location) — для будущего replay
- Записывает **translation result** (action_type, target_id, translation_status) — без model metadata (это S2)
- Логирует **causal outcome presence** (было ли событие, был ли DM-ответ) — boolean-only, без глубокого instrumentation (это S3)

### Что S1 НЕ делает
- Не добавляет model metadata (model_revision, prompt_version, seed) — это S2
- Не инструментирует CausalFrame в production — это S3
- Не строит ReplayRunner — это S4 (расширение SUPERBOX)
- Не формализует Golden Corpus — это S5
- Не чинит BUG-CORE-003 или любые другие баги — это Repair track, идёт параллельно
- Не меняет `IntentSemanticField` DTO — остаётся domain object без metadata
- Не создаёт `IntentCandidate` — используем существующий `IntentSemanticField`
- Не создаёт `CausalTraceV2` — используем существующий `CausalFrame` из sandbox (в S3 вынесем в production)

### Архитектурные принципы (ADR-O-332 / ADR-O-333, draft)

**ADR-O-332 — Semantic Interpretation Is Non-Authoritative**
> Любая интерпретация внешнего ввода, полученная probabilistic model, является кандидатом семантики и не является фактом мира, командой изменения состояния или causal event до прохождения соответствующих deterministic contracts.

**ADR-O-333 — Input Trace Contract**
> Raw player input (`I_0`) является immutable observation. Все производные стадии (interpretation, classification, resolution, validation, event, projection, manifestation) являются пересчитываемыми. `input_id` — root correlation ID, не смешивается с `causal_parent_id`.

---

## 1. Реальные сигнатуры кода (code-verified)

### 1.1. Ingress point — `routes.py:393`

```python
@router.post("/game/action")
async def game_action(request: dict, game_loop=Depends(get_game_loop)) -> dict:
    try:
        player = request.get("player")
        campaign_id = request.get("campaign")
        action_text = request.get("action")
        is_telegraph = request.get("is_telegraph", False)

        if not player or not campaign_id or not action_text:
            raise HTTPException(status_code=400, detail="...")

        if is_telegraph:
            return {"response": "", ...}  # NPC telegraph — не player input

        # ... spatial oracle ...

        turn_request = ChatTurnRequest(
            world_id=campaign_id,
            campaign_id=campaign_id,
            location=location,
            model=model_selection,
            actions=[PlayerAction(player_name=player, action=action_text)],
            player_position=_player_pos,
        )

        result = await game_loop.run_turn(turn_request)
        # ... build response ...
        return {
            "response": result.dm_response,
            "world_snapshot": _ws_dict,
            "confirmed_location_id": confirmed_location_id,
            # ...
        }
```

**Точка инструментирования:** `routes.py:509` (перед `ChatTurnRequest(...)`构造) — здесь генерируем `input_id` и захватываем pre-tick context. После `game_loop.run_turn()` (строка 518) — здесь фиксируем post-tick snapshot_id и causal outcome.

### 1.2. ChatTurnRequest schema — `schemas.py:51`

```python
class ChatTurnRequest(BaseModel):
    world_id: str
    campaign_id: str
    location: str
    model: Optional[ModelSelection] = None
    actions: List[PlayerAction]
    player_position: Optional[tuple[float, float]] = None
    world_position: Optional[tuple[float, float]] = None
```

**Изменение:** добавить опциональное поле `input_id: Optional[str] = None` — пробрасывается из routes.py в game_loop, чтобы pipeline мог использовать его для trace linkage. Поле опциональное — backward compatible, не ломает существующие callers.

### 1.3. run_turn signature — `game_loop/__init__.py:1026`

```python
async def run_turn(self, req: ChatTurnRequest) -> ChatTurnResponse:
    print(f"[ARCHAE_PLAYER_ENTRY] req={req}")  # ← BUG-FB-036: print в production
    """Блокирующий путь (REST). DM-нарратив собирается целиком."""
    self.assert_requirements()
    # ...
    state = await self._run_pipeline(
        req.actions, req.campaign_id, req.world_id, req.location,
        is_session_start=_is_session_start_rest,
        player_position=req.player_position,
    )
    # ...
    dm_result = await run_agent_safe("dm", self.dm_agent, ...)
    # ...
```

**Точки инструментирования:**
- Строка 1027: **удалить `print(f"[ARCHAE_PLAYER_ENTRY] req={req}")`** — это BUG-FB-036 (L21 violation). Заменить на `logger.info(f"[PLAYER_ENTRY] input_id={req.input_id} player={req.actions[0].player_name} action_len={len(req.actions[0].action)}")` — БЕЗ дампа всего req (PII risk, BUG-FB-036 note 4).
- После `_run_pipeline` (строка ~1048): прочитать `state.shared_context.scene_state.get("tick")` и `state.shared_context.scene_state.get("snapshot_id")` для post-tick trace.
- После `dm_result` (строка ~1080): записать `dm_response_present = bool(dm_result.response)`.

### 1.4. IntentCompressor.compress — `intent_compressor.py:205`

```python
async def compress(
    self, raw_text: str, scene_context: Dict[str, Any]
) -> IntentSemanticField:
    fast_result = self._fast_path_parse(raw_text)
    if fast_result is not None:
        return fast_result
    return await self._slow_path_parse(raw_text, scene_context)
```

**Точка инструментирования:** `game_loop/__init__.py:1728` (call site):
```python
_semantic_field = await self._intent_compressor.compress(
    raw_text=_raw_action, scene_context=scene_state
)
```

S1 **не инструментирует** IntentCompressor internals (это S2 — model metadata). S1 только фиксирует результат на call site:
- `fast_path_used: bool` = `fast_result is not None` (нужен return из compress, сейчас не экспонируется — см. §3.4)
- `action_type: str` = `_semantic_field.action_type.value`
- `target_reference: str` = `_semantic_field.target_reference or ""`
- `translation_status: str` = `"accepted" | "rejected" | "uncertain"` (вычисляется из `action_type` и `ambiguity`)

### 1.5. WorldSnapshot — `world_snapshot.py:36`

```python
@dataclass(frozen=True)
class WorldSnapshot:
    snapshot_id: UUID
    created_at: float  # ← BUG-FB-029: time.time() — non-deterministic
    tick: int
    campaign_id: str
    location_id: str
    spatial_service: Any
    npc_positions: Dict[str, Dict[str, Any]]
    active_traversals: Dict[str, Dict[str, Any]]
    spatial_walls: Any
    spatial_obstacles: Any
    rng_seed: int
```

**Важно:** `snapshot_id` сейчас = `uuid4()` (BUG-FB-029) — non-deterministic. Для S1 это **не блокер**: мы записываем `snapshot_id` как identity ("это был тот snapshot"), а не как content hash. Content hash (`snapshot_content_hash`) добавим в S3/S4 после фикса BUG-FB-029. Сейчас в trace пишем `snapshot_id.hex[:8]` — достаточно для correlation.

**Где доступен snapshot_id:** `WorldSnapshot` строится в `build_snapshot()` (`world_snapshot.py:84`) внутри TickOrchestrator. GameLoop читает результат через `TickResultDTO.world_snapshot` (если BUG-FB-031 починен) или через `scene_manager._tick_scenes[loc]["snapshot_id"]` (workaround). В S1 используем **workaround**: после `_run_pipeline` читаем `state.shared_context.scene_state.get("tick")` и `state.shared_context.scene_state.get("snapshot_id")` (если есть), иначе `tick=unknown`, `snapshot_id=unknown`. Это нормально для observational trace.

### 1.6. EventContext (hub_event) — `decision_hub.py:209`

```python
@dataclass
class EventContext:
    event_type: EventType
    actor_id: str
    success: bool = True
    intensity: float = 1.0
    distance: float = 3.0
    witness_count: int = 1
    location: str = ""
    day: int = 0
    target_id: Optional[str] = None
    semantic_action: Optional[str] = None
    visible_threat_markers: List[str] = field(default_factory=list)
    # ...
```

**Важно:** `EventContext` **не имеет** `input_id` поля. S1 **не добавляет** его в EventContext (это загрязнит domain DTO). Вместо этого S1 записывает `hub_event_created: bool` и `hub_event_event_type: str` на call site в game_loop (строка ~1759, после `if _ctx.hub_event and _resolution`). Linkage `input_id → event_id` будет в S3 через CausalFrame, не через EventContext.

### 1.7. Existing CausalFrame — `tests/sandbox/runtime/causal_trace.py:24`

```python
@dataclass(frozen=True)
class CausalFrame:
    frame_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    tick: int = 0
    phase: str = ""  # SEMANTIC, PRESSURE, UTILITY, DECISION
    entity_id: str = ""
    event: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    causal_parent_id: Optional[str] = None
```

**S1 НЕ трогает CausalFrame.** Он остаётся в sandbox. Вынос в production — это S3. S1 только готовит `input_id` как будущий `causal_parent_id` для T1 (INTERPRETATION) frame. Когда S3 будет инструментировать pipeline, `input_id` станет `causal_parent_id` для первого frame в цепочке.

---

## 2. Trace DTO — `InputTraceRecord` (новый файл)

### 2.1. Файл: `backend/app/services/input/input_trace.py` (новый)

```python
"""
S1 Input Ingress Trace — observational only.

ADR-O-333: Raw player input (I_0) is immutable observation.
input_id is root correlation ID, NOT mixed with causal_parent_id.

Этот модуль НЕ мутирует pipeline. Только записывает.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Trace file location — append-only, rotation by date
_TRACE_DIR = Path(os.environ.get(
    "ENIGMA_INPUT_TRACE_DIR",
    "backend/data/logs/input_trace"
))


@dataclass
class InputTraceRecord:
    """Одна запись trace. Immutable после создания.

    T0-T4 stages. Некоторые могут отсутствовать (None) на ранних этапах
    или при сбоях pipeline. Это информативнее чем final_action_type.
    """

    # ── Root correlation ──────────────────────────────────────────
    input_id: str  # Первичный ключ. Никогда не None.

    # ── T0: INPUT (immutable observation) ─────────────────────────
    t0_raw_text: str
    t0_player_name: str
    t0_campaign_id: str
    t0_location_id: str
    t0_session_id: Optional[str] = None
    t0_timestamp_iso: str = ""

    # ── T1: CONTEXT SNAPSHOT (what system knew at input time) ─────
    t1_tick_before: Optional[int] = None
    t1_snapshot_id_before: Optional[str] = None  # hex[:8] of WorldSnapshot.snapshot_id
    t1_nearby_npc_ids: list = field(default_factory=list)
    t1_player_position: Optional[tuple] = None

    # ── T2: INTERPRETATION (IntentSemanticField result) ───────────
    t2_fast_path_used: Optional[bool] = None  # True if fast-path matched
    t2_action_type: Optional[str] = None  # ActionType.value
    t2_target_reference: Optional[str] = None  # raw reference, not resolved id
    t2_ambiguity: Optional[str] = None  # SemanticAmbiguity.value
    t2_confidence_parse: Optional[float] = None
    t2_confidence_target: Optional[float] = None
    # S2 добавит: t2_model_run_id, t2_provider, t2_model_revision, t2_prompt_revision

    # ── T3: TRANSLATION STATUS (deterministic contract check) ─────
    # REJECT ≠ UNCERTAIN. Это разные failure modes (per другой LLM §11).
    t3_translation_status: Optional[str] = None  # accepted | rejected | uncertain
    t3_target_resolved_id: Optional[str] = None  # resolved npc_id or None
    t3_target_resolution_path: Optional[str] = None  # "fuzzy" | "exact" | "none"

    # ── T4: CAUSAL OUTCOME (boolean presence, no deep instrumentation) ─
    t4_hub_event_created: Optional[bool] = None
    t4_hub_event_event_type: Optional[str] = None
    t4_tick_after: Optional[int] = None
    t4_snapshot_id_after: Optional[str] = None
    t4_dm_response_present: Optional[bool] = None
    t4_dm_response_length: Optional[int] = None
    # S3 добавит: t4_event_id, t4_causal_frame_ids, t4_delta_batch_id

    # ── ERROR (если pipeline упал) ────────────────────────────────
    error: Optional[str] = None  # short error class name + message[:200]

    # ── METADATA ──────────────────────────────────────────────────
    trace_version: str = "s1.0"
    recorded_at_iso: str = ""

    def to_jsonl(self) -> str:
        """Serialize to JSONL line. tuple → list for JSON."""
        d = asdict(self)
        if d.get("t1_player_position") is not None:
            d["t1_player_position"] = list(d["t1_player_position"])
        return json.dumps(d, ensure_ascii=False, default=str)


def generate_input_id() -> str:
    """Генерация root correlation ID. ULID-like: timestamp + uuid."""
    # Не используем uuid4() — non-deterministic (BUG-FB-029 family).
    # Но для trace ID determinism не требуется (это observation, не world state).
    # Используем time-prefixed для сортируемости.
    _ts = int(time.time() * 1000)
    _rand = uuid.uuid4().hex[:8]
    return f"inp_{_ts:x}_{_rand}"


def record_input_trace(record: InputTraceRecord) -> None:
    """Append-only запись в daily trace file. Никогда не raise.

    Если trace write падает — логируем warning, но не ломаем pipeline.
    Observability не должна влиять на gameplay (CAUSAL_CONTRACT §5).
    """
    try:
        _TRACE_DIR.mkdir(parents=True, exist_ok=True)
        _date = datetime.now(timezone.utc).strftime("%Y%m%d")
        _file = _TRACE_DIR / f"input_trace_{_date}.jsonl"
        record.recorded_at_iso = datetime.now(timezone.utc).isoformat()
        with open(_file, "a", encoding="utf-8") as f:
            f.write(record.to_jsonl() + "\n")
    except Exception as _trace_err:
        logger.warning(
            f"[INPUT_TRACE] write failed (non-fatal): "
            f"{type(_trace_err).__name__}: {_trace_err}"
        )
```

### 2.2. Архитектурные гарантии

1. **`input_id` ≠ `causal_parent_id`.** `input_id` — root key для trace. `causal_parent_id` (в CausalFrame) — для causal graph. Они решают разные задачи (per другой LLM §3).
2. **`InputTraceRecord` не наследует `CausalFrame`.** Это observation, не causal entity. CausalFrame остаётся domain object для causal graph.
3. **`InputTraceRecord` не污染 `IntentSemanticField`.** Domain DTO остаётся чистым. Trace — separate dataclass.
4. **Append-only, never raise.** `record_input_trace` ловит все исключения. Observability не ломает gameplay (CAUSAL_CONTRACT §5: "Падение CDS не должно прерывать каузальный поток").
5. **No model metadata in S1.** `t2_model_run_id` etc. — это S2. S1 только фиксирует результат, не процесс.
6. **`translation_status` отличает REJECT от UNCERTAIN** (per другой LLM §11):
   - `uncertain` — `action_type == ActionType.UNCERTAIN` (модель не поняла)
   - `rejected` — `action_type != UNCERTAIN`, но target не зарезолвился или semantic_action не прошёл validation
   - `accepted` — intent прошёл deterministic contracts и дошёл до hub_event

---

## 3. Instrumentation plan (4 точки, ~120 строк)

### 3.1. Point 1: `routes.py:509` — generate input_id + capture T0/T1 (pre-tick)

**Before:**
```python
turn_request = ChatTurnRequest(
    world_id=campaign_id,
    campaign_id=campaign_id,
    location=location,
    model=model_selection,
    actions=[PlayerAction(player_name=player, action=action_text)],
    player_position=_player_pos,
)
result = await game_loop.run_turn(turn_request)
```

**After:**
```python
# S1: Input Ingress Trace — generate root correlation ID
from app.services.input.input_trace import generate_input_id, InputTraceRecord, record_input_trace
from datetime import datetime, timezone

_input_id = generate_input_id()
_trace_rec = InputTraceRecord(
    input_id=_input_id,
    t0_raw_text=action_text,
    t0_player_name=player,
    t0_campaign_id=campaign_id,
    t0_location_id=location,
    t0_timestamp_iso=datetime.now(timezone.utc).isoformat(),
    t1_player_position=_player_pos,
    # t1_tick_before, t1_snapshot_id_before, t1_nearby_npc_ids — fill after scene lookup
)

# Capture pre-tick context (best-effort, non-fatal)
try:
    _pre_scene = game_loop.scene_manager.get_scene_state(campaign_id, location)
    if _pre_scene:
        _trace_rec.t1_tick_before = _pre_scene.get("tick")
        _trace_rec.t1_snapshot_id_before = (
            str(_pre_scene.get("snapshot_id", ""))[:8] or None
        )
        _trace_rec.t1_nearby_npc_ids = list(
            (_pre_scene.get("npc_positions") or {}).keys()
        )[:20]  # cap at 20 for trace size
except Exception as _ctx_err:
    logger.debug(f"[INPUT_TRACE] pre-tick context capture failed: {_ctx_err}")

turn_request = ChatTurnRequest(
    world_id=campaign_id,
    campaign_id=campaign_id,
    location=location,
    model=model_selection,
    actions=[PlayerAction(player_name=player, action=action_text)],
    player_position=_player_pos,
    input_id=_input_id,  # ← NEW FIELD (optional, backward-compatible)
)

try:
    result = await game_loop.run_turn(turn_request)
except Exception as _turn_err:
    _trace_rec.error = f"{type(_turn_err).__name__}: {str(_turn_err)[:200]}"
    record_input_trace(_trace_rec)
    raise
```

**Почему `input_id` в `ChatTurnRequest`** (а не в shared_context):
- `ChatTurnRequest` — API boundary, не domain object. Добавление опционального поля не нарушает domain purity.
- `shared_context` формируется ПОЗЖЕ (внутри `_run_pipeline`), и к моменту trace point 1 его ещё нет.
- `input_id` пробрасывается через request, чтобы game_loop мог использовать его для T2/T3/T4 instrumentation без повторной генерации.

### 3.2. Point 2: `game_loop/__init__.py:1027` — replace print + capture T2/T3

**Before:**
```python
async def run_turn(self, req: ChatTurnRequest) -> ChatTurnResponse:
    print(f"[ARCHAE_PLAYER_ENTRY] req={req}")  # BUG-FB-036
    """Блокирующий путь (REST). DM-нарратив собирается целиком."""
    ...
```

**After:**
```python
async def run_turn(self, req: ChatTurnRequest) -> ChatTurnResponse:
    # BUG-FB-036 FIX: print → logger, без дампа всего req (PII risk)
    _input_id = getattr(req, "input_id", None)
    logger.info(
        f"[PLAYER_ENTRY] input_id={_input_id} player={req.actions[0].player_name} "
        f"action_len={len(req.actions[0].action)}"
    )
    """Блокирующий путь (REST). DM-нарратив собирается целиком."""
    ...
```

### 3.3. Point 3: `game_loop/__init__.py:1728` — capture T2 (interpretation) + T3 (translation status)

**Before:**
```python
_raw_action = actions[0].action if actions else ""
_semantic_field = await self._intent_compressor.compress(
    raw_text=_raw_action, scene_context=scene_state
)

_resolution = resolve_player_intent(
    raw_action=_raw_action,
    action_type=shared_context.action_type or "player_interacts",
    target=shared_context.player_target_id or "",
    player_dict=_player_data_dict,
    scene_context=scene_state,
    semantic_field=_semantic_field,
)
```

**After:**
```python
_raw_action = actions[0].action if actions else ""
_semantic_field = await self._intent_compressor.compress(
    raw_text=_raw_action, scene_context=scene_state
)

_resolution = resolve_player_intent(
    raw_action=_raw_action,
    action_type=shared_context.action_type or "player_interacts",
    target=shared_context.player_target_id or "",
    player_dict=_player_data_dict,
    scene_context=scene_state,
    semantic_field=_semantic_field,
)

# S1: T2/T3 trace capture (observational, non-fatal)
try:
    from app.services.input.input_trace import InputTraceRecord, record_input_trace
    _trace = InputTraceRecord(
        input_id=getattr(req, "input_id", "") or "unknown",
        t0_raw_text=_raw_action,
        t0_player_name=actions[0].player_name if actions else "unknown",
        t0_campaign_id=req.campaign_id,
        t0_location_id=req.location,
    )
    # T2: Interpretation
    _trace.t2_fast_path_used = None  # S2 — needs IntentCompressor to expose this
    _trace.t2_action_type = _semantic_field.action_type.value
    _trace.t2_target_reference = _semantic_field.target_reference
    _trace.t2_ambiguity = _semantic_field.ambiguity.value
    _trace.t2_confidence_parse = _semantic_field.confidence.parse
    _trace.t2_confidence_target = _semantic_field.confidence.target
    # T3: Translation status (REJECT ≠ UNCERTAIN)
    _resolved_target = shared_context.player_target_id or ""
    if _semantic_field.action_type.value == "UNCERTAIN":
        _trace.t3_translation_status = "uncertain"
    elif not _resolved_target and _semantic_field.target_reference:
        _trace.t3_translation_status = "rejected"  # had target ref, but unresolved
    else:
        _trace.t3_translation_status = "accepted"
    _trace.t3_target_resolved_id = _resolved_target or None
    _trace.t3_target_resolution_path = (
        "fuzzy" if _resolved_target and _semantic_field.target_reference
        else ("exact" if _resolved_target else "none")
    )
    # Stash on shared_context for T4 capture later in pipeline
    shared_context._input_trace = _trace  # private attr, not in PipelineContext schema
except Exception as _trace_err:
    logger.debug(f"[INPUT_TRACE] T2/T3 capture failed: {_trace_err}")
```

**Почему `_input_trace` на `shared_context` (private attr):**
- `PipelineContext` — dataclass с типизированными полями. Добавление публичного поля нарушит schema.
- Private attr (`_input_trace`) — workaround для S1. В S3 заменим на proper trace context object.
- `getattr(shared_context, "_input_trace", None)` в Point 4 — safe access.

### 3.4. Point 4: `game_loop/__init__.py` после `dm_result` (~строка 1080) — capture T4 + finalize

**Before:**
```python
dm_result = await run_agent_safe("dm", self.dm_agent, ...)
# ... build response ...
return ChatTurnResponse(dm_response=dm_result.response, ...)
```

**After:**
```python
dm_result = await run_agent_safe("dm", self.dm_agent, ...)

# S1: T4 trace capture + finalize (observational, non-fatal)
try:
    _trace = getattr(shared_context, "_input_trace", None)
    if _trace:
        # T4: Causal outcome (boolean presence only)
        _trace.t4_hub_event_created = bool(getattr(_ctx, "hub_event", None))
        _trace.t4_hub_event_event_type = (
            _ctx.hub_event.event_type.value if _ctx.hub_event else None
        )
        _post_scene = shared_context.scene_state or {}
        _trace.t4_tick_after = _post_scene.get("tick")
        _trace.t4_snapshot_id_after = (
            str(_post_scene.get("snapshot_id", ""))[:8] or None
        )
        _trace.t4_dm_response_present = bool(dm_result.response)
        _trace.t4_dm_response_length = len(dm_result.response) if dm_result.response else 0
        record_input_trace(_trace)
except Exception as _trace_err:
    logger.debug(f"[INPUT_TRACE] T4 finalize failed: {_trace_err}")

# ... build response ...
return ChatTurnResponse(dm_response=dm_result.response, ...)
```

### 3.5. ChatTurnRequest schema change — `schemas.py:51`

**Before:**
```python
class ChatTurnRequest(BaseModel):
    world_id: str
    campaign_id: str
    location: str
    model: Optional[ModelSelection] = None
    actions: List[PlayerAction]
    player_position: Optional[tuple[float, float]] = None
    world_position: Optional[tuple[float, float]] = None
```

**After:**
```python
class ChatTurnRequest(BaseModel):
    world_id: str
    campaign_id: str
    location: str
    model: Optional[ModelSelection] = None
    actions: List[PlayerAction]
    player_position: Optional[tuple[float, float]] = None
    world_position: Optional[tuple[float, float]] = None
    # S1: Input Ingress Trace root correlation ID (ADR-O-333)
    # Optional for backward compat. None = trace not tracked (legacy callers).
    input_id: Optional[str] = None
```

---

## 4. Что НЕ трогаем (architectural safety)

| Файл / DTO | Почему не трогаем в S1 |
|-----------|----------------------|
| `IntentSemanticField` (domain DTO) | Остаётся pure domain. Trace metadata — в `InputTraceRecord`, не в domain. |
| `EventContext` / `HubEventContext` | Не добавляем `input_id`. Linkage через CausalFrame в S3, не через domain event. |
| `CausalFrame` / `CausalTrace` | Остаётся в `tests/sandbox/`. Вынос в production — S3. |
| `WorldSnapshot` | Не меняем `snapshot_id` generation (BUG-FB-029 — отдельный фикс). S1 только читает. |
| `TickOrchestrator` | S1 не инструментирует ядро. Только game_loop layer. |
| `IntentCompressor` internals | S1 не добавляет model metadata (это S2). Только call site capture. |
| `EventDTO.create` | Не добавляем `input_id` в payload. Linkage через CausalFrame в S3. |
| `StateApplicator` / `DeltaBuffer` | S1 не трогает. T4 — только boolean presence. |

---

## 5. Trace file format (example output)

`backend/data/logs/input_trace/input_trace_20260803.jsonl`:

```json
{"input_id":"inp_18f3a2b4c1d_7e3f9a1b","t0_raw_text":"привет Торнин","t0_player_name":"Михаил","t0_campaign_id":"Open_road","t0_location_id":"tavern","t0_session_id":null,"t0_timestamp_iso":"2026-08-03T14:23:11.234+00:00","t1_tick_before":1831,"t1_snapshot_id_before":"a3f2c1d4","t1_nearby_npc_ids":["maid_lusya","tavern_keeper_tornin","guard_borko"],"t1_player_position":[8.14,13.02],"t2_fast_path_used":null,"t2_action_type":"UNCERTAIN","t2_target_reference":null,"t2_ambiguity":"AMBIGUOUS","t2_confidence_parse":0.3,"t2_confidence_target":0.1,"t3_translation_status":"uncertain","t3_target_resolved_id":null,"t3_target_resolution_path":"none","t4_hub_event_created":true,"t4_hub_event_event_type":"PLAYER_SPOKE","t4_tick_after":1832,"t4_snapshot_id_after":"b4e3d2c5","t4_dm_response_present":false,"t4_dm_response_length":0,"error":null,"trace_version":"s1.0","recorded_at_iso":"2026-08-03T14:23:14.891+00:00"}
{"input_id":"inp_18f3a2b4c2e_8f4a1b2c","t0_raw_text":"где Люся?","t0_player_name":"Михаил","t0_campaign_id":"Open_road","t0_location_id":"tavern","t0_session_id":null,"t0_timestamp_iso":"2026-08-03T14:24:02.123+00:00","t1_tick_before":1835,"t1_snapshot_id_before":"c5f4e3d6","t1_nearby_npc_ids":["maid_lusya","tavern_keeper_tornin"],"t1_player_position":[9.5,12.8],"t2_fast_path_used":null,"t2_action_type":"INTERACT","t2_target_reference":"люся","t2_ambiguity":"CLEAR","t2_confidence_parse":0.8,"t2_confidence_target":0.6,"t3_translation_status":"accepted","t3_target_resolved_id":"maid_lusya","t3_target_resolution_path":"fuzzy","t4_hub_event_created":true,"t4_hub_event_event_type":"PLAYER_SPOKE","t4_tick_after":1836,"t4_snapshot_id_after":"d6f5e4c7","t4_dm_response_present":false,"t4_dm_response_length":0,"error":null,"trace_version":"s1.0","recorded_at_iso":"2026-08-03T14:24:05.412+00:00"}
```

**Что мы видим из этого trace через неделю:**
- `t2_action_type: UNCERTAIN` в 83% записей → IntentCompressor не понимает свободный ввод
- `t3_translation_status: rejected` в 12% → target_reference есть, но не резолвится
- `t4_dm_response_present: false` в 95% → DM не отвечает (подтверждает BUG-CORE-003 + BUG-DLG-002)
- `t4_hub_event_created: true` но `t4_dm_response_present: false` → hub_event создаётся, но не доходит до DM (BUG-CORE-003 подтверждён trace-данными)

---

## 6. Acceptance criteria для S1

| # | Критерий | Verification |
|---|----------|-------------|
| 1 | Каждый player input (не telegraph) получает `input_id` | `grep -c "input_id" input_trace_YYYYMMDD.jsonl` == число POST `/api/game/action` |
| 2 | `t0_raw_text` сохраняется для 100% inputs | `jq -r '.t0_raw_text' input_trace_*.jsonl \| sort -u \| wc -l` > 0 |
| 3 | Trace write failure НЕ ломает gameplay | `error` field в trace != "TraceError", gameplay continues |
| 4 | `print(f"[ARCHAE_PLAYER_ENTRY] req={req}")` удалён | `grep "ARCHAE_PLAYER_ENTRY" backend/app/` == 0 |
| 5 | `ChatTurnRequest.input_id` опциональный | Legacy callers (без input_id) не падают |
| 6 | Trace file append-only, daily rotation | `ls backend/data/logs/input_trace/` показывает файлы по дате |
| 7 | `t3_translation_status` различает uncertain/rejected/accepted | `jq -r '.t3_translation_status' \| sort \| uniq -c` показывает 3 категории |
| 8 | T4 capture работает даже если pipeline упал | trace record имеет `error` field, не пустой |

---

## 7. Roadmap после S1

| Phase | Что добавляет | Когда |
|-------|--------------|-------|
| **S1** (этот план) | input_id, T0-T4 boolean trace | Сейчас, ~2-3 дня |
| **S2** | model metadata (T2): model_run_id, provider, model_revision, prompt_revision, seed, temperature | После S1, ~1 неделя |
| **S3** | CausalFrame в production: вынести из sandbox, instrument pipeline, link input_id → causal_parent_id | Параллельно с Critical bug fixes, ~2 недели |
| **S4** | Replay: расширить SUPERBOX для input replay (frozen context + frozen snapshot + model swap) | После Phase 1-2 bug fixes, ~2 недели |
| **S5** | Golden Corpus: curate из trace data, добавить expected_semantics / allowed / forbidden | После 2-3 недель сбора trace, ~1 неделя |
| **S6** | Model Benchmark: A/B comparison на Golden Corpus | После S5, ~1 неделя |

**Параллельный Repair track (не зависит от S1-S6):**
- BUG-CORE-003 (hub_event → TickState) — Critical, 2ч
- BUG-DLG-005 (DialogueQueue drain) — Critical, 2ч
- BUG-DLG-002 (DM ValueError) — Critical, 2ч
- BUG-FB-001/030/031 (world_snapshot в SSE/run_turn) — Critical, 4ч
- BUG-PERC-030/031/032 (affective decay) — Critical, 3ч

Repair track и Diagnostic track (S1-S6) **идут параллельно**. Без S1 Repair track будет диагностироваться субъективно. Без Repair track S1 будет записывать traces сломанного pipeline. Оба нужны.

---

## 8. ADR drafts (для записи в docs/audits/)

### ADR-O-332 — Semantic Interpretation Is Non-Authoritative

> **Статус:** DRAFT (принять после S1)
> **Домен:** DOM-02 (Dialogue / LLM), DOM-10 (Identity & Ontology)

**Контекст:** IntentCompressor (LLM) классифицирует player input. Результат классификации используется как semantic_action в hub_event.但目前 нет контракта, разделяющего "интерпретацию модели" и "факт мира".

**Решение:** Любая интерпретация внешнего ввода, полученная probabilistic model (LLM, classifier, embedding retrieval, vision model), является **кандидатом семантики** (IntentSemanticField), а не фактом мира, командой изменения состояния, или causal event. Кандидат становится фактом только после прохождения deterministic contracts (validation, target resolution, causal acceptance).

**Taboo:**
- ❌ Запись `action_type` из LLM напрямую в `EventDTO.payload` как факт
- ❌ Использование LLM confidence как causal weight без deterministic gate
- ❌ Treat `IntentSemanticField` как command (это поле, не команда)

**Files:** `intent_compressor.py`, `phase_1_input.py`, `intent_profile.py`

### ADR-O-333 — Input Trace Contract

> **Статус:** DRAFT (принять после S1)
> **Домен:** DOM-08 (Observability)

**Контекст:** Player input проходит через 5 стадий: T0 INPUT → T1 CONTEXT → T2 INTERPRETATION → T3 TRANSLATION → T4 CAUSAL OUTCOME. Без trace невозможно диагностировать, где именно рвётся pipeline.

**Решение:**
1. Raw player input (`t0_raw_text`) — **immutable observation**. Никогда не перезаписывается, не удаляется (retention policy separate).
2. `input_id` — **root correlation ID**. Проходит через все стадии. Не смешивается с `causal_parent_id` (causal graph linkage).
3. Все производные стадии (T1-T4) — **пересчитываемые**. При смене модели можно переинтерпретировать T0 заново.
4. Trace write — **observational only**. Никогда не мутирует pipeline, никогда не блокирует gameplay.
5. `translation_status` различает `uncertain` (модель не поняла) и `rejected` (поняла, но мир не принял) — это разные failure modes.

**Taboo:**
- ❌ Использование `input_id` как `causal_parent_id` напрямую (разные ответственности)
- ❌ Запись model metadata в `InputTraceRecord.t0` (T0 — immutable observation, model не участвует)
- ❌ Trace write failure, ломающая gameplay (CAUSAL_CONTRACT §5)
- ❌ Смешивание `snapshot_id` (identity) и `snapshot_content_hash` (deterministic fingerprint) — последнее в S3/S4

**Files:** `input_trace.py` (новый), `routes.py`, `game_loop/__init__.py`, `schemas.py`

---

## 9. Итог

**S1 — это ~120 строк кода в 4 файлах:**
1. `backend/app/services/input/input_trace.py` (новый, ~80 строк) — DTO + writer
2. `backend/app/api/routes.py` (~25 строк) — Point 1: generate input_id, capture T0/T1
3. `backend/app/services/game_loop/__init__.py` (~30 строк) — Point 2 (replace print) + Point 3 (T2/T3) + Point 4 (T4)
4. `backend/app/models/schemas.py` (~2 строки) — добавить `input_id: Optional[str] = None`

**Принципы (согласованы обоими LLM):**
- ✅ `input_id` как root correlation ID (не causal_parent_id)
- ✅ `IntentSemanticField` остаётся domain object (не загрязняем)
- ✅ `CausalFrame` остаётся в sandbox (выносим в S3, не дублируем)
- ✅ `WorldSnapshot.snapshot_id` используется как identity (content hash — в S3/S4)
- ✅ `translation_status` различает uncertain/rejected/accepted
- ✅ Trace observational only (не чинит pipeline, не мутирует мир)
- ✅ Append-only, never raise (CAUSAL_CONTRACT §5)
- ✅ Backward compatible (ChatTurnRequest.input_id optional)
- ✅ Не трогает domain DTOs (IntentSemanticField, EventContext, EventDTO)
- ✅ Parallel to Repair track (BUG-CORE-003 etc.)

**После S1 (через 2-3 дня + 1 неделя плейтестов):**
- У нас будет corpus из ~50-200 реальных вводов
- Мы увидим % UNCERTAIN / rejected / accepted
- Мы увидим, где именно рвётся pipeline (T2→T3 vs T3→T4)
- Мы сможем приоритизировать S2 (model metadata) vs Repair track (BUG-CORE-003)

**Главное:** S1 — это не "логирование". Это **архитектурный фундамент** для будущих S2-S6 и для Repair track verification. Без него любой фикс будет невидимым.
