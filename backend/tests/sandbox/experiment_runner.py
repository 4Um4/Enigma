"""NPC_LONGFORM E0 — ExperimentRunner: диагностический harness для длительного
автономного взаимодействия NPC.

Composition over TavernGameplayHarness (не наследует, не дублирует).
Production lifecycle не подменяется. Observation taps — read-only.

Архитектурная схема:
  ExperimentRunner
    ├── TavernGameplayHarness (composition, production path)
    ├── ExperimentTrace (diagnostic data collector)
    │   ├── pre_flight: NPC snapshots (static load_npcs_merged + runtime inspect_npc)
    │   ├── ticks: List[TickTrace]
    │   │   ├── tick_id, game_time
    │   │   ├── recent_dialogues (speaker, target, text, timestamp)
    │   │   ├── movement_intents (npc_id, intent, target)
    │   │   ├── scene_changes (target, field, new_value, cause)
    │   │   └── errors
    │   └── post_flight: NPC snapshots
    └── save_report(path) — JSON

Production-компоненты (переиспользуются, не дублируются):
  - TavernGameplayHarness.new_game / advance_ticks / inspect_npc / dispose
  - GameLoop.idle_tick (единая точка входа)
  - TaskScheduler._recent_dialogues / get_recent_dialogues
  - ReplayRecorder (record_tick_state / record_tick_mutation) — опционально

Новые компоненты:
  - ExperimentRunner (этот файл)
  - ExperimentTrace / TickTrace (dataclasses)
  - test_experiment_runner.py (7 сценариев)
"""
import json
import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))


# ── Trace dataclasses ───────────────────────────────────────────────────────

@dataclass
class TickTrace:
    """Diagnostic snapshot of a single tick."""
    tick_id: int = 0
    game_time: float = 0.0
    recent_dialogues: List[Dict] = field(default_factory=list)
    movement_intents: List[Dict] = field(default_factory=list)
    scene_changes: List[Dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    npc_positions: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExperimentTrace:
    """Full diagnostic trace of an experiment run."""
    experiment_id: str = ""
    config: Dict[str, Any] = field(default_factory=dict)
    pre_flight_static: Dict[str, Any] = field(default_factory=dict)
    pre_flight_runtime: Dict[str, Any] = field(default_factory=dict)
    ticks: List[TickTrace] = field(default_factory=list)
    post_flight_runtime: Dict[str, Any] = field(default_factory=dict)
    elapsed_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "config": self.config,
            "pre_flight_static": self.pre_flight_static,
            "pre_flight_runtime": self.pre_flight_runtime,
            "ticks": [
                {
                    "tick_id": t.tick_id,
                    "game_time": t.game_time,
                    "recent_dialogues": t.recent_dialogues,
                    "movement_intents": t.movement_intents,
                    "scene_changes": t.scene_changes,
                    "errors": t.errors,
                    "npc_positions": {k: str(v)[:100] for k, v in t.npc_positions.items()},
                }
                for t in self.ticks
            ],
            "post_flight_runtime": self.post_flight_runtime,
            "elapsed_seconds": self.elapsed_seconds,
            "errors": self.errors,
        }


# ── ExperimentRunner ────────────────────────────────────────────────────────

class ExperimentRunner:
    """Diagnostic harness for autonomous NPC interaction experiments.

    Composition over TavernGameplayHarness — does NOT inherit, does NOT
    duplicate. Wraps production harness with observation taps.

    Observation taps are read-only — they do NOT change return values,
    arguments, or behavior of production functions (Закон XI).
    """

    def __init__(
        self,
        seed: int = 42,
        campaign: str = "Open_road",
        target_npcs: Optional[List[str]] = None,
    ) -> None:
        self.seed = seed
        self.campaign = campaign
        self.target_npcs = target_npcs or [
            "maid_lusya",
            "tavern_keeper_tornin",
            "blacksmith_orm",
        ]
        self._harness: Optional[Any] = None
        self._trace: ExperimentTrace = ExperimentTrace()
        self._restore_hooks: List[Callable] = []
        self._tick_counter: int = 0

    # ── Lifecycle ───────────────────────────────────────────────────────────

    def setup(self, n_ticks: int = 10, experiment_id: str = "") -> None:
        """Configure experiment (does NOT start simulation)."""
        self._trace.experiment_id = experiment_id or f"exp_{int(time.time())}"
        self._trace.config = {
            "seed": self.seed,
            "campaign": self.campaign,
            "target_npcs": self.target_npcs,
            "n_ticks": n_ticks,
        }

    def run(self, n_ticks: int = 10) -> ExperimentTrace:
        """Run experiment: new_game + n_ticks + dispose. Returns full trace."""
        from tests.gameplay.harness import TavernGameplayHarness

        t0 = time.time()
        try:
            # 1. Create harness + new_game
            self._harness = TavernGameplayHarness(seed=self.seed)
            self._harness.new_game()

            # 2. Install observation taps
            self._install_observation_taps()

            # 3. Pre-flight snapshots
            self._trace.pre_flight_static = self._snapshot_static()
            self._trace.pre_flight_runtime = self._snapshot_runtime()

            # 4. Run ticks
            for i in range(n_ticks):
                self._tick_counter = i + 1
                self._run_one_tick()

            # 5. Post-flight snapshot
            self._trace.post_flight_runtime = self._snapshot_runtime()

        except Exception as e:
            self._trace.errors.append(f"run: {type(e).__name__}: {e}")
        finally:
            # 6. Restore hooks + dispose
            self._restore_observation_taps()
            if self._harness:
                try:
                    self._harness.dispose()
                except Exception as e:
                    self._trace.errors.append(f"dispose: {e}")

        self._trace.elapsed_seconds = round(time.time() - t0, 2)
        return self._trace

    # ── Observation taps (read-only hooks) ──────────────────────────────────

    def _install_observation_taps(self) -> None:
        """Install read-only hooks on NpcTickPipeline.run and MovementEngine.

        Hooks do NOT change return values or behavior — only observe.
        """
        # Hook 1: NpcTickPipeline.run (staticmethod — no self)
        try:
            from app.services.npc.npc_tick_pipeline import NpcTickPipeline
            _orig_run = NpcTickPipeline.run

            def _tap_run(*args, **kwargs):
                _mutation = _orig_run(*args, **kwargs)
                try:
                    self._capture_mutation(_mutation)
                except Exception as _e:
                    self._trace.errors.append(f"tap_run: {_e}")
                return _mutation

            NpcTickPipeline.run = staticmethod(_tap_run)
            self._restore_hooks.append(
                lambda: setattr(NpcTickPipeline, "run", staticmethod(_orig_run))
            )
        except Exception as e:
            self._trace.errors.append(f"install_tap_run: {e}")

        # Hook 2: MovementEngine.process_intents (instance method — self)
        try:
            from app.services.spatial.movement_engine import MovementEngine
            _orig_pi = MovementEngine.process_intents

            def _tap_pi(self_engine, *args, **kwargs):
                _changes = _orig_pi(self_engine, *args, **kwargs)
                try:
                    self._capture_scene_changes(_changes)
                except Exception as _e:
                    self._trace.errors.append(f"tap_pi: {_e}")
                return _changes

            MovementEngine.process_intents = _tap_pi
            self._restore_hooks.append(
                lambda: setattr(MovementEngine, "process_intents", _orig_pi)
            )
        except Exception as e:
            self._trace.errors.append(f"install_tap_pi: {e}")

    def _restore_observation_taps(self) -> None:
        """Restore all observation hooks."""
        for restore in self._restore_hooks:
            try:
                restore()
            except Exception:
                pass
        self._restore_hooks.clear()

    # ── Capture (observation, read-only) ────────────────────────────────────

    def _capture_mutation(self, mutation: Any) -> None:
        """Capture movement_intents + npc_deltas from NpcTickPipeline.run output."""
        if not self._trace.ticks:
            return
        _tick = self._trace.ticks[-1]

        _ints = getattr(mutation, "movement_intents", []) or []
        for _mi in _ints:
            _tick.movement_intents.append({
                "tick": self._tick_counter,
                "npc_id": getattr(_mi, "npc_id", "?"),
                "intent": str(getattr(_mi, "intent", "?")),
                "target": str(getattr(_mi, "target_id", "") or getattr(_mi, "target_node_id", "")),
            })

    def _capture_scene_changes(self, changes: Any) -> None:
        """Capture SceneChange from MovementEngine.process_intents."""
        if not self._trace.ticks:
            return
        _tick = self._trace.ticks[-1]
        for _ch in (changes or []):
            _tick.scene_changes.append({
                "tick": self._tick_counter,
                "target": str(getattr(_ch, "target", "")),
                "field": str(getattr(_ch, "field", "")),
                "new_value": str(getattr(_ch, "new_value", ""))[:100],
                "cause": str(getattr(_ch, "cause", "")),
            })

    # ── Tick execution ──────────────────────────────────────────────────────

    def _run_one_tick(self) -> None:
        """Run one idle_tick + capture trace."""
        _tick_trace = TickTrace(tick_id=self._tick_counter)
        self._trace.ticks.append(_tick_trace)

        try:
            _result = self._harness.game_loop.idle_tick(self._harness.campaign_id)

            # Capture game_time + positions from tick result
            _scene = self._harness._scene_after_tick(_result)
            if _scene:
                _tick_trace.game_time = _scene.get("game_time_seconds", 0.0)
                _tick_trace.npc_positions = {
                    _id: _n.get("local_position", (0, 0))
                    for _id, _n in (_scene.get("npc_positions", {}) or {}).items()
                    if isinstance(_n, dict)
                }

            # Capture recent_dialogues
            _ts = self._harness.game_loop._get_task_scheduler()
            _recent = _ts.get_recent_dialogues(_tick_trace.game_time)
            _tick_trace.recent_dialogues = [
                {
                    "speaker_id": d.get("speaker_id", ""),
                    "target_id": d.get("target_id", ""),
                    "text": str(d.get("text", ""))[:200],
                    "timestamp": d.get("timestamp", 0.0),
                    "thread_id": d.get("thread_id", d.get("session_id", "")),
                    "intent": d.get("intent", ""),
                }
                for d in (_recent or [])
            ]

        except Exception as e:
            _tick_trace.errors.append(f"{type(e).__name__}: {e}")

    # ── Snapshots (read-only) ───────────────────────────────────────────────

    def _snapshot_npc_dict(self, npc: Optional[dict]) -> Dict[str, Any]:
        """Read-only snapshot of NPC dict."""
        if not npc:
            return {"present": False}
        _cache = npc.get("narrative_cache", []) or []
        _psyche = npc.get("psyche", {}) or {}
        _rc = npc.get("relationship_cache", {}) or {}
        return {
            "present": True,
            "narrative_cache_count": len(_cache),
            "narrative_cache_target_ids": [
                (m.get("target_id", "") if isinstance(m, dict) else getattr(m, "target_id", ""))
                for m in _cache
            ],
            "psyche_beliefs_keys": list((_psyche.get("beliefs", {}) or {}).keys())
                if isinstance(_psyche.get("beliefs"), dict) else [],
            "affective_imprints_count": len(npc.get("affective_imprints", []) or []),
            "relationship_cache": {
                k: {"trust": v.get("trust"), "fear": v.get("fear")}
                for k, v in _rc.items() if isinstance(v, dict)
            },
        }

    def _snapshot_static(self) -> Dict[str, Any]:
        """Static path snapshot via load_npcs_merged — НЕ runtime."""
        from app.services.npc.npc_loader import load_npcs_merged
        npcs = load_npcs_merged()
        _by_id = {(n.get("id") or n.get("npc_id")): n for n in npcs}
        return {
            _id: self._snapshot_npc_dict(_by_id.get(_id))
            for _id in self.target_npcs
        }

    def _snapshot_runtime(self) -> Dict[str, Any]:
        """Runtime snapshot via harness.inspect_npc."""
        return {
            _id: self._snapshot_npc_dict(self._harness.inspect_npc(_id))
            for _id in self.target_npcs
        }

    # ── Report ──────────────────────────────────────────────────────────────

    def save_report(self, path: Optional[Path] = None) -> Path:
        """Save trace as JSON report."""
        if path is None:
            _reports_dir = ROOT / "reports" / "experiments"
            _reports_dir.mkdir(parents=True, exist_ok=True)
            path = _reports_dir / f"{self._trace.experiment_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._trace.to_dict(), f, ensure_ascii=False, indent=2, default=str)
        return path

    # ── Convenience ─────────────────────────────────────────────────────────

    def get_trace(self) -> ExperimentTrace:
        return self._trace

    def get_dialogues(self) -> List[Dict]:
        """All dialogues across all ticks (flattened)."""
        _all = []
        for t in self._trace.ticks:
            _all.extend(t.recent_dialogues)
        return _all

    def get_movement_intents(self) -> List[Dict]:
        """All movement_intents across all ticks (flattened)."""
        _all = []
        for t in self._trace.ticks:
            _all.extend(t.movement_intents)
        return _all