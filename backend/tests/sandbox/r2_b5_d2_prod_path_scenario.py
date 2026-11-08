"""
R2-B5-D2 — B4-R9 Stage 5: Production-path scenario with idle_ticks (read-only).

Цель: воспроизвести условие B4-R8 — belief Торнина существует в EpistemicStore
после PLAYER_INSULTS + idle_ticks — и проверить формирование cognition block
в production-пути.

Этап 5 (резервный) per Master's spec B4-R9: при отсутствии сохранения B4-R8
использовать расширенный production-path сценарий с полноценными idle_tick.

Запреты (per Master's spec):
  - НЕ исправлять код до локализации дефекта
  - НЕ менять пороги и фильтры
  - НЕ менять claim block и cognition block
  - НЕ менять PropositionVerifier
  - НЕ менять scoring и выбор намерений
  - НЕ удалять и не перезаписывать предыдущие артефакты
  - НЕ запускать полный B4-R1 без отдельного согласования
  - НЕ создавать убеждение вручную
  - НЕ принуждать NPC к spread_rumor
  - НЕ менять production-код
  - Фиксировать состояние store на каждом тике

READ-ONLY diagnostic. Production-код не меняется.
"""
from __future__ import annotations

import os
import sys
import io
import json
import traceback
import shutil
import tempfile
import logging
import inspect
from pathlib import Path
from typing import Any, Optional
from datetime import datetime

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
OUT_FILE = OUT_FILE_DIR / "r2_b5_d2_prod_path_scenario.txt"


class LogCapture:
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
                     "app.services.events", "app.services.npc",
                     "app.services.execution"]:
            logging.getLogger(name).addHandler(self.handler)

    def uninstall(self) -> None:
        root = logging.getLogger()
        root.removeHandler(self.handler)
        for name in ["app", "app.services", "app.services.game_loop",
                     "app.services.events", "app.services.npc",
                     "app.services.execution"]:
            logging.getLogger(name).removeHandler(self.handler)

    def find(self, pattern: str) -> list[logging.LogRecord]:
        return [r for r in self.records if pattern.lower() in r.getMessage().lower()]


class TeeStream:
    def __init__(self, *streams):
        self.streams = streams
    def write(self, data):
        for s in self.streams:
            try: s.write(data)
            except Exception: pass
    def flush(self):
        for s in self.streams:
            try: s.flush()
            except Exception: pass


_stdout_buf = io.StringIO()
_orig_stdout = sys.stdout
sys.stdout = TeeStream(_orig_stdout, _stdout_buf)


def _section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def _print_belief_record(r: Any, indent: str = "    ") -> None:
    try:
        if isinstance(r, dict):
            prop = r.get("proposition", {})
            subj = prop.get("subject_id", "?")
            pred = prop.get("predicate", "?")
            obj = prop.get("object_id", "?")
            polarity = prop.get("polarity", "?")
            conf = r.get("confidence", "?")
            source_id = r.get("source_id", "?")
            source_type = r.get("source_type", "?")
            original_source_id = r.get("original_source_id", "?")
            source_claim_id = r.get("source_claim_id", "?")
            first_observed = r.get("first_observed_tick", "?")
            last_updated = r.get("last_updated_tick", "?")
            agent_id = r.get("agent_id", "?")
        else:
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
            agent_id = getattr(r, "agent_id", "?")
        print(f"{indent}agent_id={agent_id}")
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


def _get_store_records(store: Any, agent_id: str) -> list:
    try:
        return store.get_all_for_agent(agent_id)
    except Exception as e:
        print(f"    [ERROR get_all_for_agent({agent_id}): {e}]")
        return []


def _snapshot_all_agents(store: Any, agent_ids: list[str]) -> dict[str, list]:
    snapshot = {}
    for aid in agent_ids:
        records = _get_store_records(store, aid)
        snapshot[aid] = records
    return snapshot


def _has_tornin_insulted(records: list) -> tuple[bool, Optional[Any]]:
    for r in records:
        try:
            if isinstance(r, dict):
                prop = r.get("proposition", {})
                if (prop.get("subject_id") == "player"
                    and prop.get("predicate") == "insulted"
                    and prop.get("object_id") == "tavern_keeper_tornin"):
                    return True, r
            else:
                prop = r.proposition
                pred = getattr(prop, "predicate", None)
                if hasattr(pred, "value"):
                    pred = pred.value
                if (getattr(prop, "subject_id", None) == "player"
                    and pred == "insulted"
                    and getattr(prop, "object_id", None) == "tavern_keeper_tornin"):
                    return True, r
        except Exception:
            continue
    return False, None


def _print_production_code_reference() -> None:
    de_path = _BACKEND / "app" / "services" / "execution" / "dialogue_executor.py"
    if not de_path.exists():
        print(f"  [file not found: {de_path}]")
        return
    lines = de_path.read_text(encoding="utf-8", errors="replace").split("\n")
    print(f"  Source: {de_path}")
    print(f"  Lines 599-611 (cognition block construction in _generate_with_router):")
    for i in range(598, min(611, len(lines))):
        print(f"  L{i+1:4d}: {lines[i]}")


def main() -> int:
    print("=" * 78)
    print("R2-B5-D2 — B4-R9 Stage 5: Production-path scenario with idle_ticks")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)
    print()
    print("Цель: воспроизвести условие B4-R8 — belief Торнина существует в")
    print("EpistemicStore после PLAYER_INSULTS + idle_ticks — и проверить")
    print("формирование cognition block в production-пути.")
    print()
    print("Этап 5 (резервный): при отсутствии сохранения B4-R8 использовать")
    print("расширенный production-path сценарий с полноценными idle_tick.")
    print()
    print("Запреты соблюдены:")
    print("  - production-код не меняется")
    print("  - пороги и фильтры не меняются")
    print("  - claim block и cognition block не меняются")
    print("  - PropositionVerifier не меняется")
    print("  - scoring и выбор намерений не меняются")
    print("  - убеждение не создаётся вручную (только через PLAYER_INSULTS)")
    print("  - NPC не принуждается к spread_rumor")
    print("  - состояние store фиксируется на каждом тике")
    print()

    NPC_IDS = [
        "tavern_keeper_tornin",
        "maid_lusya",
        "blacksmith_orm",
        "guard_borko",
        "merchant_goran",
        "thief_shadow",
    ]

    _section("PHASE 1: Build game loop with log capture")

    orig_saves_dir = settings.saves_dir
    orig_env = settings.environment
    temp_dir = Path(tempfile.mkdtemp(prefix="r2_b5_d2_prod_path_"))

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

    _section("PHASE 2: Post-build wiring confirmation")

    tick_orch = getattr(loop, "_tick_orch", None)
    tick_orch_store = getattr(tick_orch, "_epistemic_store", None) if tick_orch else None

    ts = loop._get_task_scheduler()
    executors = getattr(ts, "_executors", None)
    try:
        from app.domain.execution import TaskKind
        dialogue_executor = executors.get(TaskKind.DIALOGUE) if executors else None
    except Exception as e:
        print(f"  Failed to import TaskKind: {e}")
        dialogue_executor = None

    de_store = getattr(dialogue_executor, "_epistemic_store", None) if dialogue_executor else None
    de_mem = getattr(dialogue_executor, "_memory_manager", None) if dialogue_executor else None

    print(f"  tick_orch._epistemic_store: {tick_orch_store}")
    print(f"    id: {id(tick_orch_store) if tick_orch_store else 'N/A'}")
    print(f"  dialogue_executor._epistemic_store: {de_store}")
    print(f"    id: {id(de_store) if de_store else 'N/A'}")
    print(f"  dialogue_executor._memory_manager: {de_mem}")
    print(f"    id: {id(de_mem) if de_mem else 'N/A'}")
    print()

    if tick_orch_store and de_store:
        same = tick_orch_store is de_store
        print(f"  SAME INSTANCE (is operator): {same}")
        if not same:
            print("  >>> WIRING BROKEN — tick_orch and DE have different stores")
            print("  >>> Cannot continue — would not test production-path")
            _write_output()
            return 1
    else:
        print("  >>> STORE MISSING — cannot continue")
        _write_output()
        return 1
    print()

    _section("PHASE 3: Setup scene — load NPCs, initialize scene")

    print("  Loading NPCs and initializing scene for 'Open_road' / 'tavern'...")
    scene = None
    loaded_npcs = 0
    try:
        scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
        if scene is None:
            print("  Scene not initialized — calling initialize_scene...")
            scene = loop.scene_manager.initialize_scene("Open_road", "tavern", "12:00")
            print(f"  Scene initialized: {scene is not None}")
        else:
            print(f"  Scene already initialized: {scene is not None}")

        if hasattr(loop, "_load_npcs_with_runtime"):
            print("  Calling loop._load_npcs_with_runtime('Open_road')...")
            loaded = loop._load_npcs_with_runtime("Open_road")
            loaded_npcs = len(loaded) if loaded else 0
            print(f"  Loaded {loaded_npcs} NPCs")
            if loaded:
                for npc in loaded[:10]:
                    npc_id = npc.get("npc_id") or npc.get("id") if isinstance(npc, dict) else getattr(npc, "npc_id", "?")
                    name = npc.get("name") if isinstance(npc, dict) else getattr(npc, "name", "")
                    print(f"    {npc_id}: {name}")
        else:
            print("  loop._load_npcs_with_runtime not found — trying alternative")
            if hasattr(loop, "new_game"):
                print("  Calling loop.new_game('Open_road')...")
                try:
                    loop.new_game("Open_road")
                    print("  new_game returned")
                except Exception as e:
                    print(f"  new_game EXCEPTION: {e}")
    except Exception as e:
        print(f"  EXCEPTION during setup: {type(e).__name__}: {e}")
        traceback.print_exc()
    print()

    _section("PHASE 4: Snapshot pre-PLAYER_INSULTS state")

    print("  EpistemicStore state per agent (before PLAYER_INSULTS):")
    pre_snapshot = _snapshot_all_agents(tick_orch_store, NPC_IDS)
    for aid, records in pre_snapshot.items():
        count = len(records)
        has_target, _ = _has_tornin_insulted(records)
        marker = " <<<" if has_target else ""
        print(f"    {aid}: {count} records{marker}")
        for r in records[:3]:
            _print_belief_record(r, indent="      ")
    print()

    _section("PHASE 5: Publish PLAYER_INSULTS (production event path)")

    print("  This is the production event path for creating Tornin's belief.")
    print("  Uses real EventBus + ClaimEventSubscriber.")
    print()

    publish_success = False
    try:
        from app.services.events.event_bus import get_event_bus
        from app.services.events.event_types import EventType
        from app.domain.events import EventDTO

        bus = get_event_bus()
        print(f"  EventBus: {bus}")

        import time as _time
        import uuid as _uuid

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
        print(f"  Event: type={getattr(event, 'type', '?')}, source={getattr(event, 'source', '?')}")
        print(f"    payload={getattr(event, 'payload', '?')}")

        print()
        print("  Publishing to EventBus...")
        bus.publish(event)
        publish_success = True
        print("  Publish returned.")
    except Exception as e:
        print(f"  EXCEPTION publishing PLAYER_INSULTS: {type(e).__name__}: {e}")
        traceback.print_exc()
    print()

    _section("PHASE 6: Snapshot immediately after publish (before any idle_tick)")

    print("  EpistemicStore state per agent (after publish, before idle_tick):")
    post_pub_snapshot = _snapshot_all_agents(tick_orch_store, NPC_IDS)
    for aid, records in post_pub_snapshot.items():
        count = len(records)
        has_target, target_rec = _has_tornin_insulted(records)
        marker = " <<<" if has_target else ""
        print(f"    {aid}: {count} records{marker}")
        if has_target and target_rec:
            _print_belief_record(target_rec, indent="      ")
    print()

    _section("PHASE 7: idle_ticks with per-tick EpistemicStore snapshots")
    print("  Up to 15 idle_ticks — looking for belief spread to Tornin")
    print("  Each tick: snapshot all agents, check for Tornin INSULTED belief")
    print()

    target_belief_appeared_at_tick: Optional[int] = None
    target_belief_record: Optional[Any] = None

    capture.install()
    MAX_TICKS = 15
    try:
        for tick_num in range(1, MAX_TICKS + 1):
            print(f"\n  --- idle_tick #{tick_num} ---")
            try:
                result = loop.idle_tick("Open_road")
                status = result.get("status") if isinstance(result, dict) else getattr(result, "status", "?")
                print(f"    idle_tick returned: status={status}")
            except Exception as e:
                print(f"    idle_tick EXCEPTION: {type(e).__name__}: {e}")
                traceback.print_exc()
                break

            print(f"    Store state after tick #{tick_num}:")
            for aid in NPC_IDS:
                records = _get_store_records(tick_orch_store, aid)
                count = len(records)
                has_target, target_rec = _has_tornin_insulted(records)
                marker = " <<<" if has_target else ""
                print(f"      {aid}: {count} records{marker}")
                if has_target and target_rec:
                    print(f"      >>> TORNIN INSULTED BELIEF FOUND at tick #{tick_num}!")
                    _print_belief_record(target_rec, indent="        ")
                    if target_belief_appeared_at_tick is None:
                        target_belief_appeared_at_tick = tick_num
                        target_belief_record = target_rec

            if target_belief_appeared_at_tick == tick_num:
                print()
                print(f"    --- Testing CognitionContextResolver.resolve_block at tick #{tick_num} ---")
                if de_store and de_mem and dialogue_executor:
                    try:
                        from app.services.npc.cognition_context import CognitionContextResolver
                        cog = CognitionContextResolver(
                            de_mem,
                            epistemic_store=de_store,
                            context_provider=lambda npc_id: dialogue_executor._get_context("Open_road", npc_id),
                        )
                        block = cog.resolve_block("tavern_keeper_tornin", "maid_lusya")
                        print(f"    resolve_block returned:")
                        print(f"      type: {type(block).__name__}")
                        print(f"      length: {len(block) if isinstance(block, str) else 'N/A'}")
                        print(f"      is empty: {block == '' if isinstance(block, str) else 'N/A'}")
                        if isinstance(block, str) and block:
                            print(f"      content:")
                            print("      " + "-" * 70)
                            for line in block.split("\n"):
                                print(f"      {line}")
                            print("      " + "-" * 70)
                        else:
                            print(f"      >>> BLOCK IS EMPTY — even with belief present!")
                    except Exception as e:
                        print(f"    EXCEPTION in resolve_block: {type(e).__name__}: {e}")
                        traceback.print_exc()

                    print()
                    print(f"    --- Testing _format_beliefs (internal method) ---")
                    try:
                        beliefs_lines = cog._format_beliefs("tavern_keeper_tornin")
                        print(f"    _format_beliefs returned: list of {len(beliefs_lines)} lines")
                        for i, line in enumerate(beliefs_lines):
                            print(f"      [{i}] {line}")
                    except Exception as e:
                        print(f"    EXCEPTION in _format_beliefs: {type(e).__name__}: {e}")
                        traceback.print_exc()

                    print()
                    print(f"    --- Direct store query (bypass resolver) ---")
                    direct_records = _get_store_records(tick_orch_store, "tavern_keeper_tornin")
                    print(f"    Direct query: {len(direct_records)} records")
                    for r in direct_records:
                        _print_belief_record(r, indent="      ")
    finally:
        capture.uninstall()
    print()

    _section("PHASE 8: Final state + resolve_block on final state")

    print(f"  Target belief appeared at tick: {target_belief_appeared_at_tick}")
    print()

    print("  Final EpistemicStore state per agent:")
    final_snapshot = _snapshot_all_agents(tick_orch_store, NPC_IDS)
    for aid, records in final_snapshot.items():
        count = len(records)
        has_target, target_rec = _has_tornin_insulted(records)
        marker = " <<<" if has_target else ""
        print(f"    {aid}: {count} records{marker}")
        if has_target and target_rec:
            _print_belief_record(target_rec, indent="      ")
        elif count > 0:
            for r in records[:2]:
                _print_belief_record(r, indent="      ")
    print()

    if target_belief_appeared_at_tick is not None and de_store and de_mem and dialogue_executor:
        print("  --- Final CognitionContextResolver.resolve_block check ---")
        try:
            from app.services.npc.cognition_context import CognitionContextResolver
            cog = CognitionContextResolver(
                de_mem,
                epistemic_store=de_store,
                context_provider=lambda npc_id: dialogue_executor._get_context("Open_road", npc_id),
            )

            for partner in ["maid_lusya", "blacksmith_orm", "guard_borko", "player"]:
                print(f"\n  resolve_block('tavern_keeper_tornin', '{partner}'):")
                block = cog.resolve_block("tavern_keeper_tornin", partner)
                print(f"    length: {len(block) if isinstance(block, str) else 'N/A'}")
                if isinstance(block, str) and block:
                    print(f"    content:")
                    print("    " + "-" * 70)
                    for line in block.split("\n"):
                        print(f"    {line}")
                    print("    " + "-" * 70)
                else:
                    print(f"    >>> EMPTY")
        except Exception as e:
            print(f"  EXCEPTION: {type(e).__name__}: {e}")
            traceback.print_exc()
    print()

    _section("PHASE 9: Production code reference (dialogue_executor.py:599-611)")
    _print_production_code_reference()
    print()

    _section("PHASE 10: Summary — answer to main question")

    print(f"""
  MAIN QUESTION: Если убеждение Торнина с правильным provenance существует
  в EpistemicStore в момент LLM-запроса, на каком конкретно участке оно
  перестаёт попадать в cognition block?

  FINDINGS:
  - Wiring: tick_orch store id={id(tick_orch_store)} == DE store id={id(de_store)} (SAME INSTANCE: {tick_orch_store is de_store})
  - publish(PLAYER_INSULTS): {'SUCCESS' if publish_success else 'FAILED'}
  - Tornin belief appeared at tick: {target_belief_appeared_at_tick if target_belief_appeared_at_tick else 'NOT FOUND'}
""")

    if target_belief_appeared_at_tick is not None:
        print(f"  - Belief record at appearance:")
        _print_belief_record(target_belief_record, indent="    ")
        print()
        print(f"  - resolve_block at appearance tick #{target_belief_appeared_at_tick}:")
        print(f"    (See Phase 7 output above)")
        print()
        print(f"  - resolve_block on final state:")
        print(f"    (See Phase 8 output above)")
    else:
        print(f"  - Belief did NOT appear in {MAX_TICKS} idle_ticks")
        print(f"  - Cannot answer main question — belief never reached Tornin")
        print(f"  - Possible causes:")
        print(f"    a) NPC not in hearing range when PLAYER_INSULTS published")
        print(f"    b) NPC didn't choose spread_rumor in their decision")
        print(f"    c) Hearing membrane (radius/LOS) blocked the spread")
        print(f"    d) PLAYER_INSULTS event type doesn't trigger ClaimEventSubscriber")
        print(f"    e) {MAX_TICKS} ticks insufficient for full rumor propagation")
    print()

    print("  --- Log records during idle_ticks matching 'cognition' / 'epistemic' / 'DIALOGUE_EXEC' ---")
    cog_logs = (capture.find("cognition block")
                + capture.find("[dialogue_exec]")
                + capture.find("cog_ctx")
                + capture.find("epistemic read failed"))
    if cog_logs:
        seen = set()
        unique = []
        for r in cog_logs:
            key = (r.name, r.levelname, r.getMessage())
            if key not in seen:
                seen.add(key)
                unique.append(r)
        print(f"  Found {len(cog_logs)} matching records ({len(unique)} unique)")
        for r in unique[:30]:
            print(f"    [{r.levelname}] {r.name}: {r.getMessage()}")
            if r.exc_info:
                tb_lines = traceback.format_exception(*r.exc_info)
                for tb_line in tb_lines:
                    for line in tb_line.rstrip().split("\n"):
                        print(f"      {line}")
    else:
        print(f"  No log records matching 'cognition block' / '[DIALOGUE_EXEC]' / 'cog_ctx' / 'epistemic read failed'")
    print()

    _section("PHASE 11: Cleanup")

    try:
        ts_obj = loop._get_task_scheduler()
        if hasattr(ts_obj, "_executor_pool"):
            print("  Shutting down executor pool...")
            ts_obj._executor_pool.shutdown(wait=False, cancel_futures=True)
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