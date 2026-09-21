"""
path: /project/backend/tests/sandbox/probes/scale_instrument.py
Назначение: SCALE LAW instrumentation contour (S272): per-tick ms, EventBus events,
L1-вызовы, recent_dialogues len, WS — поверх живого DriftLab, без его правки.
Опция --population N: подмена населения после _setup() (клоны scale_npc_XX).
Наблюдатель вне канона (CDS). Wall-clock — §15.2-исключение 4 (benchmarks).
Зависимости: drift_laboratory (DriftConfig/DriftLaboratory), event_bus, l1_chronicle
Основные сущности: ScaleInstrument, main
Запуск: cd backend; python tests/sandbox/probes/scale_instrument.py <step> <ticks> [--population N]
"""

import ctypes
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # backend/

from tests.sandbox.SUPERBOX.drift_laboratory import DriftConfig, DriftLaboratory  # noqa: E402
from app.services.events.event_bus import get_event_bus  # noqa: E402
from app.services.npc import l1_chronicle as _l1_mod  # noqa: E402

_L1_METHODS = ("append", "commit_tick_buffer", "archive_old_events", "query_raw", "query_weighted")

# PROVISIONAL-пороги RED ZONES (калибруются по факту ступеней)
_RED_MS_P95 = 200.0
_YELLOW_MS_P95 = 100.0


def _ws_mb() -> float:
    """WorkingSet текущего процесса (MB) — Windows, без psutil."""
    class _PMC(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

    pmc = _PMC()
    pmc.cb = ctypes.sizeof(_PMC)
    k32 = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi
    k32.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(_PMC), ctypes.c_ulong]
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    handle = k32.GetCurrentProcess()
    if psapi.GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.cb):
        return pmc.WorkingSetSize / (1024.0 * 1024.0)
    return -1.0


class ScaleInstrument:
    """Обёртки-счётчики вокруг живого прогона. Все патчи восстанавливаются в restore()."""

    def __init__(self, lab: DriftLaboratory, step: str, out_path: Path,
                 population: int = 0) -> None:
        self._lab = lab
        self._step = step
        self._out = out_path
        self._population = population
        self._pop_dir: Path | None = None
        self._npc_root_orig: Path | None = None
        self._tick_no = 0
        self._events = 0
        self._l1_calls = 0
        self._l1_by_name: dict = {}  # атрибуция: какой именно метод растёт
        self._qraw_callers: dict = {}  # per-caller attribution query_raw (файл:строка → count)
        self._l1_orig: dict = {}
        self._bus_orig = None
        self._orig_tick = None
        self._orig_setup = None
        self._rows: list = []

    def _apply_population(self) -> None:
        """Подмена населения ПОСЛЕ lab._setup() (temp-кампания скопирована),
        ДО первого тика. Прецедент редиректа: preset_materializer (ADR-O-361)."""
        if self._population <= 0:
            return
        from app.services.npc import npc_loader
        from tests.sandbox.probes.scale_population import build_population

        self._pop_dir = build_population(self._population)
        # Сужение типов: оба пути обязательны к этому моменту (_setup уже отработал)
        _pop = self._pop_dir
        _data_temp = self._lab._data_temp_dir
        if _pop is None or _data_temp is None:
            raise RuntimeError(
                "[SCALE_PROBE] population-дерево или temp-каталог лаборатории отсутствуют — "
                "_apply_population вызван вне _setup-контракта"
            )
        _state_src = _pop / "campaigns" / "Open_road" / "campaign_state.json"
        _state_dst = Path(_data_temp) / "campaigns" / "Open_road" / "campaign_state.json"
        shutil.copy2(_state_src, _state_dst)
        # Редирект корня особей на клонированное дерево (оригинал сохранён)
        self._npc_root_orig = npc_loader._CONFIG_NPC_ROOT
        npc_loader._CONFIG_NPC_ROOT = _pop / "npc"
        # Fail-fast: генератор обязан был создать клонов
        for nid in ("scale_npc_00", "scale_npc_01"):
            if not (_pop / "npc" / "individuals" / f"{nid}.json").exists():
                raise RuntimeError(f"[SCALE_PROBE] клон {nid}.json отсутствует — генератор сломан")
        print(f"[SCALE_PROBE] population={self._population} применена (state + npc_root redirect)")

    def install(self) -> None:
        # Врезка 0: population — обёртка _setup (подмена после оригинала)
        if self._population > 0:
            self._orig_setup = self._lab._setup

            def _setup_patched() -> None:
                assert self._orig_setup is not None
                self._orig_setup()
                self._apply_population()

            self._lab._setup = _setup_patched  # type: ignore[method-assign]

        # Врезка 1: per-tick время вокруг единственной точки всех режимов
        self._orig_tick = self._lab._run_idle_tick_direct

        def _timed() -> None:
            if self._tick_no == 0:
                self._patch_bus()
            assert self._orig_tick is not None
            t0 = time.perf_counter()
            self._orig_tick()
            ms = (time.perf_counter() - t0) * 1000.0
            self._tick_no += 1
            self._emit(ms)

        self._lab._run_idle_tick_direct = _timed  # type: ignore[method-assign]

        # Врезка 2: L1-методы (класс-уровень, probe-процесс, restore в finally)
        cls = _l1_mod.L1Chronicle
        for name in _L1_METHODS:
            orig = getattr(cls, name)
            self._l1_orig[name] = orig

            def _wrap(*a, _name=name, _orig=orig, **kw):  # type: ignore[misc]
                self._l1_calls += 1
                self._l1_by_name[_name] = self._l1_by_name.get(_name, 0) + 1
                if _name == "query_raw":
                    _f = sys._getframe(1)
                    _key = f"{Path(_f.f_code.co_filename).name}:{_f.f_lineno}"
                    self._qraw_callers[_key] = self._qraw_callers.get(_key, 0) + 1
                return _orig(*a, **kw)

            setattr(cls, name, _wrap)  # type: ignore[assignment]

    def _patch_bus(self) -> None:
        bus = get_event_bus()
        self._bus_orig = bus.publish

        def _count(ev):
            self._events += 1
            return self._bus_orig(ev)  # type: ignore[misc]

        bus.publish = _count  # type: ignore[method-assign]

    def _emit(self, ms: float) -> None:
        dlg = -1
        try:
            scene = self._lab._scene_manager.get_scene_state(
                self._lab.config.campaign_id, self._lab.config.location_id
            )
            if scene:
                dlg = len(scene.get("recent_dialogues", []))
        except Exception as exc:  # наблюдатель не роняет тик (Устав §11)
            print(f"  [SCALE_PROBE] scene read failed: {type(exc).__name__}: {exc}")
        row = {
            "step": self._step, "tick": self._tick_no, "ms": round(ms, 3),
            "events": self._events, "l1_calls": self._l1_calls,
            "dialogues": dlg, "ws_mb": round(_ws_mb(), 1),
        }
        self._rows.append(row)
        with self._out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def restore(self) -> None:
        if self._bus_orig is not None:
            get_event_bus().publish = self._bus_orig
        cls = _l1_mod.L1Chronicle
        for name, orig in self._l1_orig.items():
            setattr(cls, name, orig)
        if self._npc_root_orig is not None:
            from app.services.npc import npc_loader
            npc_loader._CONFIG_NPC_ROOT = self._npc_root_orig
        if self._pop_dir is not None:
            shutil.rmtree(self._pop_dir, ignore_errors=True)


def _percentile(sorted_vals: list, q: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, int(q * len(sorted_vals)))
    return sorted_vals[idx]


def _report(rows: list, step: str, l1_by_name: dict, qraw_callers: dict) -> str:
    ms = sorted(r["ms"] for r in rows)
    # events в jsonl кумулятивен — для per-tick метрики берём дельты
    _ev_deltas = [rows[0]["events"]] + [
        rows[i]["events"] - rows[i - 1]["events"] for i in range(1, len(rows))
    ]
    events = sorted(_ev_deltas)
    dlg_last = rows[-1]["dialogues"] if rows else -1
    p95 = _percentile(ms, 0.95)
    zone = "RED" if p95 > _RED_MS_P95 else ("YELLOW" if p95 > _YELLOW_MS_P95 else "GREEN")
    # Экспериментальный манифест: воспроизводимость через полгода (решение Мастера)
    import platform
    import subprocess as _sp
    try:
        _commit = _sp.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        _commit = "unknown"
    lines = [
        f"# SCALE MAP — {step}", "",
        f"- manifest: python={platform.python_version()} os={platform.system()} "
        f"commit={_commit} stamp={time.strftime('%Y-%m-%d %H:%M')}",
        f"- ticks: {len(rows)}",
        f"- ms/tick: mean={sum(ms)/max(1, len(ms)):.2f} p50={_percentile(ms, 0.5):.2f} "
        f"p95={p95:.2f} max={ms[-1] if ms else 0:.2f}",
        f"- EventBus events/tick: mean={sum(events)/max(1, len(events)):.1f} max={events[-1] if events else 0}",
        f"- L1 calls (total): {rows[-1]['l1_calls'] if rows else 0}",
        f"- L1 attribution: " + ", ".join(
            f"{k}={v}" for k, v in sorted(l1_by_name.items(), key=lambda kv: -kv[1])
        ),
        "- query_raw callers (top-5): " + ", ".join(
            f"{k}={v}" for k, v in sorted(qraw_callers.items(), key=lambda kv: -kv[1])[:5]
        ),
        f"- recent_dialogues (final len): {dlg_last}",
        f"- WS MB (final): {rows[-1]['ws_mb'] if rows else -1}",
        f"- RED ZONE (p95: yellow>{_YELLOW_MS_P95}, red>{_RED_MS_P95}): **{zone}**",
        "",
        "## HISTORY MAP",
        "| tick | ms | events | dialogues | ws_mb |",
        "|---|---|---|---|---|",
    ]
    for r in rows[:: max(1, len(rows) // 20)]:
        lines.append(f"| {r['tick']} | {r['ms']} | {r['events']} | {r['dialogues']} | {r['ws_mb']} |")
    lines += [
        "", "## TOP MULTIPLIERS",
        "Сравни с предыдущей ступенью вручную или через diff jsonl (>=2 ступени).",
        "", "## RED ZONES", f"- ms/tick p95: {zone}",
    ]
    return "\n".join(lines)


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--population"]
    if len(args) < 2:
        print("Использование: python scale_instrument.py <step_label> <ticks> [--population N]")
        sys.exit(1)
    step, ticks = args[0], int(args[1])
    population = 0
    if "--population" in sys.argv:
        population = int(sys.argv[sys.argv.index("--population") + 1])

    out_dir = Path(__file__).parent / "scale_reports"
    out_dir.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    jsonl = out_dir / f"scale_{step}_{stamp}.jsonl"

    lab = DriftLaboratory(DriftConfig())
    lab.config.mass_traversal_ticks = ticks  # длина ступени = запрос (DriftConfig:90)
    inst = ScaleInstrument(lab, step, jsonl, population=population)
    inst.install()
    try:
        lab.run("mass_traversal")
    finally:
        inst.restore()

    report = _report(inst._rows, step, inst._l1_by_name, inst._qraw_callers)
    md_path = out_dir / f"scale_{step}_{stamp}.md"
    md_path.write_text(report, encoding="utf-8")
    print(f"\n[SCALE_PROBE] jsonl: {jsonl}")
    print(f"[SCALE_PROBE] отчёт: {md_path}")


if __name__ == "__main__":
    main()