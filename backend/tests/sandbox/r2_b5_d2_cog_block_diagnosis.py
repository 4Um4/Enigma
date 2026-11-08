"""
R2-B5-D2 — Cognition Block Diagnosis (B4-R8 read-only diagnostic).

Цель: доказать, что тот же экземпляр EpistemicStore, содержащий убеждение
Торнина, реально доступен DialogueExecutor во время формирования cognition block.

Запреты (per Master's spec B4-R8 дополнение):
  - НЕ менять production-код
  - НЕ создавать второй EpistemicStore
  - НЕ внедрять убеждение вручную (только через PLAYER_INSULTS)
  - НЕ менять confidence thresholds
  - НЕ принуждать NPC к spread_rumor
  - НЕ менять PropositionVerifier
  - НЕ менять claim block, polarity, topic, scoring, prompt composition
  - НЕ запускать повторный B4-R1
  - НЕ удалять существующие артефакты (пишем в новый файл)

READ-ONLY diagnostic. Production-код не меняется.
"""
from __future__ import annotations

import os
import sys
import io
import traceback
import shutil
import tempfile
import logging
import inspect
from pathlib import Path
from typing import Any, Optional

_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

try:
    from app.core.config import settings
except Exception as e:
    print(f"[FATAL] Cannot import app.core.config: {e}")
    sys.exit(2)

OUT_FILE_DIR = _BACKEND / "tests" / "sandbox"
OUT_FILE_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE = OUT_FILE_DIR / "r2_b5_d2_cog_block_diagnosis.txt"


# ============================================================================
# LogCapture — ловим все логи во время build_game_loop
# ============================================================================
class LogCapture:
    """Capture all log records during a code block."""
    def __init__(self):
        self.records: list[logging.LogRecord] = []
        self.handler = logging.Handler()
        self.handler.emit = self._emit

    def _emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def install(self) -> None:
        root = logging.getLogger()
        root.addHandler(self.handler)
        for name in ["app", "app.services", "app.services.game_loop",
                     "app.services.events", "app.services.npc"]:
            logging.getLogger(name).addHandler(self.handler)

    def uninstall(self) -> None:
        root = logging.getLogger()
        root.removeHandler(self.handler)
        for name in ["app", "app.services", "app.services.game_loop",
                     "app.services.events", "app.services.npc"]:
            logging.getLogger(name).removeHandler(self.handler)

    def find(self, pattern: str) -> list[logging.LogRecord]:
        return [r for r in self.records if pattern.lower() in r.getMessage().lower()]


# ============================================================================
# TeeStream for stdout capture
# ============================================================================
class TeeStream:
    def __init__(self, *streams):
        self.streams = streams
    def write(self, data):
        for s in self.streams:
            try:
                s.write(data)
            except Exception:
                pass
    def flush(self):
        for s in self.streams:
            try:
                s.flush()
            except Exception:
                pass


_stdout_buf = io.StringIO()
_orig_stdout = sys.stdout
sys.stdout = TeeStream(_orig_stdout, _stdout_buf)


def _section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def _print_belief_record(r: Any, indent: str = "    ") -> None:
    """Pretty-print EpistemicRecord."""
    try:
        prop = r.proposition
        subj = getattr(prop, "subject_id", "?")
        pred = getattr(prop, "predicate", "?")
        if hasattr(pred, "value"):
            pred = pred.value
        obj = getattr(prop, "object_id", "?")
        polarity = getattr(prop, "polarity", "?")
        conf = getattr(r, "confidence", "?")
        source_id = getattr(r, "source_id", "?")
        source_type = getattr(r, "source_type", "?")
        original_source_id = getattr(r, "original_source_id", "?")
        source_claim_id = getattr(r, "source_claim_id", "?")
        first_observed = getattr(r, "first_observed_tick", "?")
        last_updated = getattr(r, "last_updated_tick", "?")
        print(f"{indent}prop=({subj}, {pred}, {obj}, polarity={polarity})")
        print(f"{indent}  confidence={conf}")
        print(f"{indent}  source_id={source_id}")
        print(f"{indent}  source_type={source_type}")
        print(f"{indent}  original_source_id={original_source_id}")
        print(f"{indent}  source_claim_id={source_claim_id}")
        print(f"{indent}  first_observed_tick={first_observed}")
        print(f"{indent}  last_updated_tick={last_updated}")
    except Exception as e:
        print(f"{indent}<ERROR printing record: {e}>")


def _print_production_code_reference() -> None:
    """Print dialogue_executor.py:599-611 source — confirm what code runs."""
    de_path = _BACKEND / "app" / "services" / "execution" / "dialogue_executor.py"
    if not de_path.exists():
        print(f"  [file not found: {de_path}]")
        return
    lines = de_path.read_text(encoding="utf-8", errors="replace").split("\n")
    print(f"  Source: {de_path}")
    print(f"  Lines 599-611 (cognition block construction in _generate_with_router):")
    for i in range(598, min(611, len(lines))):
        print(f"  L{i+1:4d}: {lines[i]}")


# ============================================================================
# MAIN
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-B5-D2 — Cognition Block Diagnosis (B4-R8 read-only diagnostic)")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)
    print()
    print("Цель: доказать, что тот же экземпляр EpistemicStore, содержащий")
    print("убеждение Торнина, реально доступен DialogueExecutor во время")
    print("формирования cognition block.")
    print()
    print("Запреты соблюдены:")
    print("  - production-код не меняется")
    print("  - второй EpistemicStore не создаётся")
    print("  - убеждение не внедряется вручную (только через PLAYER_INSULTS)")
    print("  - confidence thresholds не меняются")
    print("  - NPC не принуждается к spread_rumor")
    print("  - PropositionVerifier не меняется")
    print("  - claim block / polarity / topic / scoring / prompt — не тронуты")
    print("  - B4-R1 не запускается")
    print("  - существующие артефакты не удаляются (новый файл)")
    print()

    # =====================================================================
    # PHASE 1: Build game loop with log capture
    # =====================================================================
    _section("PHASE 1: Build game loop with log capture")

    orig_saves_dir = settings.saves_dir
    orig_env = settings.environment
    temp_dir = Path(tempfile.mkdtemp(prefix="r2_b5_d2_cog_block_"))

    capture = LogCapture()
    loop = None

    try:
        from app.services.game_loop_builder import build_game_loop
        settings.saves_dir = str(temp_dir)
        settings.environment = "development"

        print(f"  temp_dir: {temp_dir}")
        print(f"  settings.data_dir: {settings.data_dir}")
        print(f"  settings.saves_dir: {settings.saves_dir}")
        print()

        capture.install()
        try:
            print("  Calling build_game_loop(settings.data_dir)...")
            loop = build_game_loop(data_dir=Path(settings.data_dir))
            print(f"  build_game_loop returned: {type(loop).__name__}")
        except Exception as e:
            print(f"  build_game_loop EXCEPTION: {type(e).__name__}: {e}")
            traceback.print_exc()
        finally:
            capture.uninstall()
    except Exception as e:
        print(f"  OUTER EXCEPTION: {type(e).__name__}: {e}")
        traceback.print_exc()

    if loop is None:
        print()
        print(">>> FATAL: build_game_loop failed; cannot continue diagnosis.")
        _write_output()
        return 1

    # =====================================================================
    # PHASE 2: Inspect post-build state — registration result
    # =====================================================================
    _section("PHASE 2: Inspect post-build state")

    # 2.1: Check log records for registration errors
    print("--- 2.1: Log records during build (Epistemic Core registration) ---")
    epistemic_logs = (capture.find("epistemic core")
                      + capture.find("failed to register")
                      + capture.find("[game_loop]")
                      + capture.find("epistemic"))
    if epistemic_logs:
        seen_msgs = set()
        unique_logs = []
        for r in epistemic_logs:
            msg_key = (r.name, r.levelname, r.getMessage())
            if msg_key not in seen_msgs:
                seen_msgs.add(msg_key)
                unique_logs.append(r)
        print(f"  Found {len(epistemic_logs)} matching records ({len(unique_logs)} unique)")
        for r in unique_logs[:50]:
            print(f"  [{r.levelname}] {r.name}: {r.getMessage()}")
            if r.exc_info:
                print("    --- exception info ---")
                tb_lines = traceback.format_exception(*r.exc_info)
                for tb_line in tb_lines:
                    for line in tb_line.rstrip().split("\n"):
                        print(f"    {line}")
    else:
        print("  No log records matching 'epistemic core' / 'failed to register' / '[game_loop]' / 'epistemic'")
    print()

    # 2.2: Check tick_orch._epistemic_store
    print("--- 2.2: tick_orch._epistemic_store ---")
    tick_orch = getattr(loop, "_tick_orch", None)
    print(f"  loop._tick_orch: {tick_orch}")
    tick_orch_store: Optional[Any] = None
    if tick_orch is None:
        print("  >>> FATAL: _tick_orch is None")
    else:
        tick_orch_store = getattr(tick_orch, "_epistemic_store", None)
        print(f"  tick_orch._epistemic_store: {tick_orch_store}")
        print(f"    type: {type(tick_orch_store).__name__ if tick_orch_store is not None else 'NoneType'}")
        print(f"    id: {id(tick_orch_store) if tick_orch_store is not None else 'N/A'}")
        print(f"    is None: {tick_orch_store is None}")
        if tick_orch_store is not None:
            try:
                module = type(tick_orch_store).__module__
                cls = type(tick_orch_store).__name__
                print(f"    class: {module}.{cls}")
            except Exception:
                pass
    print()

    # 2.3: Check DialogueExecutor
    print("--- 2.3: Production DialogueExecutor._epistemic_store ---")
    dialogue_executor: Optional[Any] = None
    de_store: Optional[Any] = None
    de_mem: Optional[Any] = None
    try:
        ts = loop._get_task_scheduler()
        print(f"  task_scheduler: {ts}")
        executors = getattr(ts, "_executors", None)
        print(f"  task_scheduler._executors: {executors}")
        if executors is None:
            print("  >>> FATAL: _executors is None")
        else:
            try:
                from app.domain.execution import TaskKind
                dialogue_executor = executors.get(TaskKind.DIALOGUE)
            except Exception as e:
                print(f"  Failed to import TaskKind: {e}")
                # Try direct access by string key
                try:
                    dialogue_executor = executors.get("DIALOGUE")
                except Exception:
                    dialogue_executor = None
            print(f"  DialogueExecutor: {dialogue_executor}")
            if dialogue_executor is None:
                print("  >>> FATAL: DialogueExecutor not found in _executors")
            else:
                de_store = getattr(dialogue_executor, "_epistemic_store", None)
                print(f"  dialogue_executor._epistemic_store: {de_store}")
                print(f"    type: {type(de_store).__name__ if de_store is not None else 'NoneType'}")
                print(f"    id: {id(de_store) if de_store is not None else 'N/A'}")
                print(f"    is None: {de_store is None}")
                if de_store is not None:
                    try:
                        module = type(de_store).__module__
                        cls = type(de_store).__name__
                        print(f"    class: {module}.{cls}")
                    except Exception:
                        pass
                de_mem = getattr(dialogue_executor, "_memory_manager", None)
                print(f"  dialogue_executor._memory_manager: {de_mem}")
                print(f"    is None: {de_mem is None}")
                if de_mem is not None:
                    print(f"    type: {type(de_mem).__name__}")
    except Exception as e:
        print(f"  EXCEPTION inspecting DialogueExecutor: {type(e).__name__}: {e}")
        traceback.print_exc()
    print()

    # 2.4: Print production code reference
    print("--- 2.4: Production code reference (dialogue_executor.py:599-611) ---")
    _print_production_code_reference()
    print()

    # =====================================================================
    # PHASE 3: Instance identity check
    # =====================================================================
    _section("PHASE 3: Instance identity check (tick_orch vs DialogueExecutor)")

    if tick_orch_store is None and de_store is None:
        print("  >>> BOTH None — registration almost certainly failed silently")
        print("  >>> Hypothesis H1 CONFIRMED: late wiring passes None")
    elif tick_orch_store is None and de_store is not None:
        print("  >>> ANOMALY: tick_orch is None but DE has store — unexpected")
    elif tick_orch_store is not None and de_store is None:
        print("  >>> H1 CONFIRMED: tick_orch has store, but DE has None")
        print("  >>> Late wiring did NOT propagate store to DialogueExecutor")
        print("  >>> Possible causes:")
        print("      - set_epistemic_wiring on task_scheduler wasn't called")
        print("      - set_epistemic_wiring on DialogueExecutor wasn't called")
        print("      - 'if epistemic_store is not None:' guard skipped assignment")
    else:
        print("  Both stores present. Checking identity...")
        print(f"    tick_orch store id: {id(tick_orch_store)}")
        print(f"    DE store id:        {id(de_store)}")
        same_by_is = tick_orch_store is de_store
        same_by_id = id(tick_orch_store) == id(de_store)
        print(f"    'is' operator: {same_by_is}")
        print(f"    id() equality: {same_by_id}")
        if same_by_is:
            print("  >>> SAME INSTANCE — wiring is correct (H1 REFUTED)")
        else:
            print("  >>> DIFFERENT INSTANCES — anomaly (two stores exist)")
    print()

    # =====================================================================
    # PHASE 4: Publish PLAYER_INSULTS (production event path)
    # =====================================================================
    _section("PHASE 4: Publish PLAYER_INSULTS (production event path)")

    print("  This is the production event path for creating Tornin's belief.")
    print("  Not manual injection — uses real EventBus + ClaimEventSubscriber.")
    print()

    publish_success = False
    try:
        from app.services.events.event_bus import get_event_bus

        bus = get_event_bus()
        print(f"  EventBus: {bus}")

        # Find EventType and EventDTO
        try:
            from app.services.events.event_types import EventType
            print(f"  EventType imported from app.services.events.event_types")
        except Exception as e:
            print(f"  Cannot import EventType: {e}")
            EventType = None

        EventDTO = None
        for mod_path in ["app.domain.events", "app.services.events.event_types",
                         "app.services.events.event_bus"]:
            try:
                mod = __import__(mod_path, fromlist=["EventDTO"])
                if hasattr(mod, "EventDTO"):
                    EventDTO = mod.EventDTO
                    print(f"  EventDTO imported from: {mod_path}")
                    break
            except Exception:
                continue

        if EventType is None or EventDTO is None:
            print("  >>> CANNOT import EventType/EventDTO — skipping PLAYER_INSULTS publish")
        else:
            # Inspect EventDTO constructor
            try:
                sig = inspect.signature(EventDTO.__init__)
                print(f"  EventDTO.__init__ signature: {sig}")
            except Exception as e:
                print(f"  Cannot inspect EventDTO signature: {e}")

            # Check if EventDTO has a `create` classmethod (per ADR-O-148)
            if hasattr(EventDTO, "create"):
                print(f"  EventDTO.create signature: {inspect.signature(EventDTO.create)}")

            # Try constructing the event
            import time as _time
            import uuid as _uuid

            event = None
            construction_errors = []

            # Attempt 1: keyword args (standard dataclass)
            try:
                event = EventDTO(
                    id=_uuid.uuid4(),
                    type=EventType.PLAYER_INSULTS.value if hasattr(EventType.PLAYER_INSULTS, "value") else EventType.PLAYER_INSULTS,
                    source="player",
                    timestamp=_time.time(),
                    payload={
                        "victim": "tavern_keeper_tornin",
                        "insult_text": "Торнин, ты жалкий трус!",
                        "severity": 0.8,
                    },
                    visibility="public",
                    radius=10.0,
                    persistence_level="working",
                )
                print(f"  Event constructed via kwargs")
            except Exception as e:
                construction_errors.append(f"kwargs: {type(e).__name__}: {e}")

            # Attempt 2: EventDTO.create classmethod
            if event is None and hasattr(EventDTO, "create"):
                try:
                    event = EventDTO.create(
                        event_type=EventType.PLAYER_INSULTS,
                        source="player",
                        payload={
                            "victim": "tavern_keeper_tornin",
                            "insult_text": "Торнин, ты жалкий трус!",
                            "severity": 0.8,
                        },
                        target_id="tavern_keeper_tornin",
                    )
                    print(f"  Event constructed via EventDTO.create")
                except Exception as e:
                    construction_errors.append(f"create: {type(e).__name__}: {e}")

            if event is None:
                print(f"  >>> CANNOT construct EventDTO. Errors:")
                for err in construction_errors:
                    print(f"    - {err}")
            else:
                print(f"  Event: type={getattr(event, 'type', '?')}, source={getattr(event, 'source', '?')}")
                print(f"    payload={getattr(event, 'payload', '?')}")
                print()
                print("  Publishing to EventBus (synchronous, subscribers process immediately)...")
                bus.publish(event)
                publish_success = True
                print("  Publish returned.")
    except Exception as e:
        print(f"  EXCEPTION publishing PLAYER_INSULTS: {type(e).__name__}: {e}")
        traceback.print_exc()
    print()

    # =====================================================================
    # PHASE 5: Inspect Tornin's belief in tick_orch store
    # =====================================================================
    _section("PHASE 5: Tornin's belief in tick_orch._epistemic_store")

    if tick_orch_store is None:
        print("  >>> SKIP: tick_orch._epistemic_store is None — no belief can be stored")
        print("  >>> Hypothesis: PLAYER_INSULTS could not be processed because store is missing")
    else:
        try:
            records = tick_orch_store.get_all_for_agent("tavern_keeper_tornin")
            print(f"  tick_orch_store.get_all_for_agent('tavern_keeper_tornin'):")
            print(f"    count: {len(records)}")
            for i, r in enumerate(records):
                print(f"  Record #{i+1}:")
                _print_belief_record(r, indent="    ")
        except Exception as e:
            print(f"  EXCEPTION reading tick_orch_store: {type(e).__name__}: {e}")
            traceback.print_exc()
    print()

    # =====================================================================
    # PHASE 6: Inspect Tornin's belief in DialogueExecutor store
    # =====================================================================
    _section("PHASE 6: Tornin's belief in DialogueExecutor._epistemic_store")

    if de_store is None:
        print("  >>> SKIP: dialogue_executor._epistemic_store is None")
        print("  >>> This is the production state during _generate_with_router.")
        print("  >>> Cognition block cannot form because condition at L599 fails:")
        print("  >>>   if self._epistemic_store is not None and self._memory_manager is not None:")
        print("  >>> PRODUCTION DEFECT CONFIRMED.")
    else:
        try:
            records_de = de_store.get_all_for_agent("tavern_keeper_tornin")
            print(f"  de_store.get_all_for_agent('tavern_keeper_tornin'):")
            print(f"    count: {len(records_de)}")
            for i, r in enumerate(records_de):
                print(f"  Record #{i+1}:")
                _print_belief_record(r, indent="    ")
        except Exception as e:
            print(f"  EXCEPTION reading de_store: {type(e).__name__}: {e}")
            traceback.print_exc()
    print()

    # =====================================================================
    # PHASE 7: Manual invocation of production cognition block method
    # =====================================================================
    _section("PHASE 7: Manual invocation of CognitionContextResolver.resolve_block")
    print("  (Same construction as dialogue_executor.py:599-611)")
    print("  (ADDITIONAL check per Master's spec — does NOT replace production-path verification)")
    print()

    if de_store is None:
        print("  >>> SKIP: dialogue_executor._epistemic_store is None")
        print("  >>> Cannot invoke resolve_block — would replicate production failure")
        print("  >>> (production code at L599 also skips this branch when store is None)")
    elif dialogue_executor is None:
        print("  >>> SKIP: dialogue_executor is None")
    elif de_mem is None:
        print("  >>> SKIP: dialogue_executor._memory_manager is None")
        print("  >>> Both conditions of L599 required: _epistemic_store AND _memory_manager")
    else:
        try:
            from app.services.npc.cognition_context import CognitionContextResolver

            # SAME construction as dialogue_executor.py:601-606
            cog = CognitionContextResolver(
                de_mem,
                epistemic_store=de_store,
                context_provider=lambda npc_id: dialogue_executor._get_context("Open_road", npc_id),
            )
            print(f"  CognitionContextResolver constructed: {cog}")
            print(f"    using store id: {id(de_store)}")
            print(f"    using memory_manager id: {id(de_mem)}")
            print()

            # SAME call as dialogue_executor.py:607
            print("  Calling cog.resolve_block('tavern_keeper_tornin', 'maid_lusya')...")
            block = cog.resolve_block("tavern_keeper_tornin", "maid_lusya")
            print(f"  resolve_block returned:")
            print(f"    type: {type(block).__name__}")
            print(f"    length: {len(block) if isinstance(block, str) else 'N/A'}")
            print(f"    is empty: {block == '' if isinstance(block, str) else 'N/A'}")
            print(f"    content:")
            print("    " + "-" * 70)
            if isinstance(block, str):
                for line in block.split("\n"):
                    print(f"    {line}")
            else:
                print(f"    {block!r}")
            print("    " + "-" * 70)
        except Exception as e:
            print(f"  EXCEPTION in resolve_block: {type(e).__name__}: {e}")
            print()
            print("  --- Full traceback ---")
            tb_lines = traceback.format_exc().split("\n")
            for line in tb_lines:
                print(f"    {line}")
    print()

    # =====================================================================
    # PHASE 8: Manual invocation of _format_beliefs (internal method)
    # =====================================================================
    _section("PHASE 8: Manual invocation of CognitionContextResolver._format_beliefs")
    print("  (Internal method — to identify exact failure point if resolve_block fails)")
    print()

    if de_store is not None and dialogue_executor is not None and de_mem is not None:
        try:
            from app.services.npc.cognition_context import CognitionContextResolver

            cog = CognitionContextResolver(
                de_mem,
                epistemic_store=de_store,
                context_provider=lambda npc_id: dialogue_executor._get_context("Open_road", npc_id),
            )

            print("  Calling cog._format_beliefs('tavern_keeper_tornin')...")
            beliefs_lines = cog._format_beliefs("tavern_keeper_tornin")
            print(f"  _format_beliefs returned:")
            print(f"    type: {type(beliefs_lines).__name__}")
            print(f"    length: {len(beliefs_lines) if isinstance(beliefs_lines, list) else 'N/A'}")
            if isinstance(beliefs_lines, list):
                for i, line in enumerate(beliefs_lines):
                    print(f"    [{i}] {line}")
        except Exception as e:
            print(f"  EXCEPTION in _format_beliefs: {type(e).__name__}: {e}")
            print()
            print("  --- Full traceback ---")
            tb_lines = traceback.format_exc().split("\n")
            for line in tb_lines:
                print(f"    {line}")
    else:
        print("  >>> SKIP: prerequisites not met (de_store / dialogue_executor / de_mem)")
    print()

    # =====================================================================
    # PHASE 9: Direct store query (bypass resolver)
    # =====================================================================
    _section("PHASE 9: Direct EpistemicStore.get_all_for_agent (bypass resolver)")

    if de_store is not None:
        try:
            print("  Calling de_store.get_all_for_agent('tavern_keeper_tornin') directly...")
            direct_records = de_store.get_all_for_agent("tavern_keeper_tornin")
            print(f"  Direct query returned {len(direct_records)} records")
            for i, r in enumerate(direct_records):
                print(f"  Record #{i+1}:")
                _print_belief_record(r, indent="    ")
        except Exception as e:
            print(f"  EXCEPTION in direct query: {type(e).__name__}: {e}")
            traceback.print_exc()
    else:
        print("  >>> SKIP: de_store is None")
    print()

    # =====================================================================
    # PHASE 10: Summary — answers to Master's questions
    # =====================================================================
    _section("PHASE 10: Summary — answers to Master's questions")

    tick_orch_store_final = getattr(getattr(loop, "_tick_orch", None), "_epistemic_store", None) if loop._tick_orch else None
    de_store_final = getattr(dialogue_executor, "_epistemic_store", None) if dialogue_executor else None

    # Count records (best-effort)
    tick_orch_records_count = "N/A"
    de_records_count = "N/A"
    if tick_orch_store_final is not None:
        try:
            tick_orch_records_count = len(tick_orch_store_final.get_all_for_agent("tavern_keeper_tornin"))
        except Exception as e:
            tick_orch_records_count = f"<ERROR: {e}>"
    if de_store_final is not None:
        try:
            de_records_count = len(de_store_final.get_all_for_agent("tavern_keeper_tornin"))
        except Exception as e:
            de_records_count = f"<ERROR: {e}>"

    print(f"""
  Q1: Результат регистрации Epistemic Core
  >>> tick_orch._epistemic_store is None: {tick_orch_store_final is None}
  >>> (If True — registration failed silently; check Phase 2.1 logs)
  >>> (If False — registration succeeded)

  Q2: Наличие EpistemicStore в TickOrchestrator
  >>> present: {tick_orch_store_final is not None}
  >>> id: {id(tick_orch_store_final) if tick_orch_store_final is not None else 'N/A'}
  >>> Tornin records count: {tick_orch_records_count}

  Q3: Наличие EpistemicStore в production DialogueExecutor
  >>> present: {de_store_final is not None}
  >>> id: {id(de_store_final) if de_store_final is not None else 'N/A'}
  >>> Tornin records count: {de_records_count}

  Q4: Идентичность экземпляров
  >>> tick_orch store is None: {tick_orch_store_final is None}
  >>> DE store is None: {de_store_final is None}
  >>> same instance: {tick_orch_store_final is de_store_final if (tick_orch_store_final is not None and de_store_final is not None) else 'N/A — at least one is None'}

  Q5: Наличие убеждения Торнина в том же экземпляре
  >>> tick_orch records: {tick_orch_records_count}
  >>> DE records: {de_records_count}
  >>> (See Phase 5 and Phase 6 above for record details)
  >>> (Direct query in Phase 9 bypasses resolver to confirm store contents)

  Q6: Реальное выполнение production-метода формирования cognition block
  >>> (See Phase 7 — manual invocation replicates dialogue_executor.py:599-611)
  >>> (If Phase 7 returned non-empty block — production method WORKS)
  >>> (If Phase 7 returned empty or raised — production method BROKEN)

  Q7: Причина отсутствия блока, если он не формируется
  >>> (See Phase 8 — _format_beliefs internal method)
  >>> (See Phase 9 — direct store query bypassing resolver)
  >>> (If Phase 9 returns records but Phase 7 returns empty — RESOLVER bug)
  >>> (If Phase 9 returns 0 records — STORE bug or WIRING bug)
  >>> (If Phase 7 raised exception — see traceback)
""")

    # =====================================================================
    # PHASE 11: Cleanup
    # =====================================================================
    _section("PHASE 11: Cleanup")

    try:
        ts = loop._get_task_scheduler()
        if hasattr(ts, "_executor_pool"):
            print("  Shutting down executor pool...")
            ts._executor_pool.shutdown(wait=False, cancel_futures=True)
    except Exception as e:
        print(f"  Cleanup exception (ignored): {e}")

    try:
        if hasattr(loop, "dispose"):
            print("  Calling loop.dispose()...")
            loop.dispose()
    except Exception as e:
        print(f"  Dispose exception (ignored): {e}")

    del loop
    import gc
    gc.collect()

    settings.saves_dir = orig_saves_dir
    settings.environment = orig_env
    shutil.rmtree(temp_dir, ignore_errors=True)
    print("  Cleanup complete.")
    print()

    # Write output file
    _write_output()
    return 0


def _write_output() -> None:
    try:
        OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            f.write(_stdout_buf.getvalue())
        size = OUT_FILE.stat().st_size
        print(f">>> Output written to: {OUT_FILE}")
        print(f">>> File size: {size} bytes ({size / 1024:.1f} KB)")
    except Exception as e:
        print(f">>> [ERROR writing output file: {e}]")
        traceback.print_exc()


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as e:
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        rc = 1
    finally:
        sys.stdout = _orig_stdout
    sys.exit(rc)