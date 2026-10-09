# backend/tests/sandbox/probes/llm_down_smoke_probe.py
# COV-2 Фаза 1b: дым мёртвого LLM. Измеряет, не чинит.
# Таргеты: http://127.0.0.1:9 (мгновенный refusal) + blackhole (ephemeral).
# Живой llama-server 8181 НЕ затрагивается ни одним запросом.

import asyncio
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import traceback
import urllib.request
from pathlib import Path

# ── 0. ENV-ИЗОЛЯЦИЯ (СТРОГО до первого импорта app) ──────────────────────
os.environ["AIDM_LLAMA_CPP_SERVER_URL"] = "http://127.0.0.1:9"
os.environ["AIDM_REPLAY_MODE"] = "off"
os.environ["AIDM_LLAMA_CPP_TIMEOUT_SEC"] = "3"
os.environ["D8P_ENABLED"] = "0"
os.environ["ENIGMA_DISABLE_FILE_LOGS"] = "1"
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND))
REPORTS = BACKEND.parent / "reports"

from app.core.config import settings  # noqa: E402

if settings.llama_cpp_server_url != "http://127.0.0.1:9":
    print(f"[PROBE] FATAL: env-изоляция не взялась: {settings.llama_cpp_server_url}")
    sys.exit(2)
if settings.replay_mode != "off":
    print(f"[PROBE] FATAL: replay не выключен: {settings.replay_mode}")
    sys.exit(2)

REPORT: dict = {"started": time.strftime("%H:%M:%S"), "env": settings.llama_cpp_server_url}


def _mark(tag: str, **kv) -> None:
    print(f"[PROBE] {tag} " + " ".join(f"{k}={v}" for k, v in kv.items()))


# ── Blackhole: принимает соединения и никогда не отвечает ────────────────
class Blackhole:
    def __init__(self) -> None:
        self._srv = socket.socket()
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(8)
        self.port = self._srv.getsockname()[1]
        self._conns: list[socket.socket] = []
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._serve, daemon=True)

    def _serve(self) -> None:
        self._srv.settimeout(0.5)
        while not self._stop.is_set():
            try:
                c, _ = self._srv.accept()
                self._conns.append(c)
            except socket.timeout:
                continue

    def start(self) -> None:
        self._t.start()

    def stop(self) -> None:
        self._stop.set()
        self._t.join(timeout=1.5)
        for c in self._conns:
            try:
                c.close()
            except OSError:
                pass
        self._srv.close()


class Heartbeat:
    """Счётчик живости loop: каждые 100мс тик; max_gap = глубина заморозки."""

    def __init__(self, interval: float = 0.1) -> None:
        self.interval = interval
        self.count = 0
        self.max_gap = 0.0
        self._last = time.perf_counter()
        self._stop = asyncio.Event()

    async def run(self) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(self.interval)
            now = time.perf_counter()
            self.max_gap = max(self.max_gap, now - self._last)
            self._last = now
            self.count += 1

    def reset(self) -> None:
        self._last = time.perf_counter()
        self.max_gap = 0.0


# ── П5: статус здоровья при refused-URL ──────────────────────────────────
def p5_status() -> None:
    from app.services.llm.health import check_llm_health

    h = check_llm_health(use_cache=False)
    REPORT["p5_health"] = h
    _mark("P5", status=h.get("status"), details=str(h.get("details"))[:60])


# ── П1: профиль отказа (3 запроса, dead-9) ───────────────────────────────
def p1_refusal(router) -> None:
    rows = []
    for i in range(3):
        t0 = time.perf_counter()
        try:
            out = router.request_for_agent("dm", "[PROBE] ping", None, "probe")
            rows.append({"i": i, "ok": True, "len": len(out or ""), "ms": round((time.perf_counter() - t0) * 1000, 1)})
        except Exception as e:
            rows.append({
                "i": i, "ok": False, "exc": type(e).__name__,
                "msg": str(e)[:140], "ms": round((time.perf_counter() - t0) * 1000, 1),
            })
        rows[-1]["in_progress"] = getattr(router, "_request_in_progress", "n/a")
    REPORT["p1_refusal"] = rows
    for r in rows:
        _mark("P1", **r)


# ── П2: жив ли idle-мир без LLM (копия фиксстура как data-root) ──────────
def p2_idle_world(ticks: int = 25) -> None:
    fixture = BACKEND / "tests" / "fixtures" / "campaign_open_road"
    if not fixture.exists():
        REPORT["p2"] = "FIXTURE_MISSING"
        _mark("P2", fixture="MISSING")
        return
    tmp = tempfile.mkdtemp(prefix="llm_probe_")
    try:
        shutil.copytree(fixture, Path(tmp), dirs_exist_ok=True)
        from app.services.game_loop_builder import build_game_loop

        gl = build_game_loop(Path(tmp))
        ok = err = 0
        errors: list[str] = []
        ms: list[float] = []
        for _ in range(ticks):
            t0 = time.perf_counter()
            try:
                gl.idle_tick("Open_road")
                ok += 1
            except Exception as e:
                err += 1
                if len(errors) < 5:
                    errors.append(f"{type(e).__name__}: {str(e)[:90]}")
            ms.append(round((time.perf_counter() - t0) * 1000, 1))
        sched = getattr(gl, "_task_scheduler", None)
        failed = getattr(sched, "failed_tasks", None)
        done = getattr(sched, "completed_tasks", None)
        REPORT["p2"] = {
            "ticks": ticks, "ok": ok, "err": err, "errors": errors,
            "ms_p50": sorted(ms)[len(ms) // 2], "ms_max": max(ms),
            "sched_failed": failed, "sched_completed": done,
        }
        _mark("P2", ticks=ticks, ok=ok, err=err, ms_max=max(ms),
              sched_failed=failed, sched_done=done)
    except Exception as e:
        REPORT["p2"] = f"BUILD_FAIL {type(e).__name__}: {e}"
        _mark("P2", build="FAIL", exc=type(e).__name__, msg=str(e)[:90])
        traceback.print_exc()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── П3/П4: blackhole — отменяемость и заморозка loop ─────────────────────
async def _p3p4(bh: Blackhole, router) -> None:
    hb = Heartbeat(0.1)
    hbt = asyncio.create_task(hb.run())

    def _blocking() -> None:
        req = urllib.request.Request(
            f"http://127.0.0.1:{bh.port}/v1/chat/completions",
            data=b"{}", headers={"Content-Type": "application/json"}, method="POST",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=3.0):
            pass  # blackhole никогда не ответит

    # П3 (Г3): паттерн agent_runner — to_thread + wait_for
    hb.reset()
    t0 = time.perf_counter()
    try:
        await asyncio.wait_for(asyncio.to_thread(_blocking), timeout=1.0)
        p3 = "completed(???)"
    except asyncio.TimeoutError:
        p3 = "cancelled"
    except Exception as e:
        p3 = f"exc:{type(e).__name__}"
    REPORT["p3_to_thread_cancel"] = {"outcome": p3, "ms": round((time.perf_counter() - t0) * 1000, 1)}
    _mark("P3", outcome=p3, ms=REPORT["p3_to_thread_cancel"]["ms"],
          hb_max_gap_s=round(hb.max_gap, 2))

    # П4a (Г4, механика): sync-вызов прямо в async (антипаттерн D66)
    hb.reset()
    t0 = time.perf_counter()
    await asyncio.sleep(0)  # выровнять планировщик
    p4a_outcome = "completed"
    try:
        _blocking()  # 3с заморозка loop намеренно
    except TimeoutError:
        p4a_outcome = "timeout_after_freeze"
    except Exception as e:
        p4a_outcome = f"exc:{type(e).__name__}"
    REPORT["p4a_sync_freeze"] = {"outcome": p4a_outcome,
                                 "ms": round((time.perf_counter() - t0) * 1000, 1),
                                 "hb_max_gap_s": round(hb.max_gap, 2)}
    _mark("P4a", **REPORT["p4a_sync_freeze"])

    # П4b (Г4, реальный роутер): settings -> blackhole, ленивый провайдер
    settings.llama_cpp_server_url = f"http://127.0.0.1:{bh.port}"
    hb.reset()
    t0 = time.perf_counter()
    outcome = "n/a"
    try:
        await asyncio.wait_for(router.request("general", "[PROBE] blackhole", None, "probe"), timeout=1.0)
        outcome = "completed"
    except asyncio.TimeoutError:
        outcome = "cancelled_at_1s"
    except Exception as e:
        outcome = f"exc:{type(e).__name__}"
    REPORT["p4b_real_router"] = {
        "outcome": outcome, "ms": round((time.perf_counter() - t0) * 1000, 1),
        "hb_max_gap_s": round(hb.max_gap, 2),
    }
    _mark("P4b", **REPORT["p4b_real_router"])
    # Интерпретация: exc*за <100мс = провайдер закэширован на dead-9 (находка);
    # cancelled/freeze ~3с+ = real sync-заморозка внутри async (подтверждение D66).

    hb._stop.set()
    await hbt


def main() -> None:
    try:
        _main_inner()
    finally:
        out = REPORTS / "llm_down_smoke_probe.json"
        out.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding="utf-8")
        _mark("DONE", artifact=str(out))


def _main_inner() -> None:
    _mark("START", url=settings.llama_cpp_server_url, timeout=settings.llama_cpp_timeout_sec)
    p5_status()

    try:
        from app.services.llm import initialize_router

        initialize_router()
        REPORT["router_init"] = "ok"
    except Exception as e:
        REPORT["router_init"] = f"FAIL {type(e).__name__}: {str(e)[:90]}"
    _mark("ROUTER_INIT", res=REPORT["router_init"])

    router = None
    try:
        from app.services.llm.router import ModelRouter

        router = ModelRouter()
    except Exception as e:
        REPORT["router_get"] = f"FAIL {type(e).__name__}: {str(e)[:90]}"
        traceback.print_exc()
    if router is not None:
        p1_refusal(router)
    p2_idle_world()

    bh = Blackhole()
    bh.start()
    try:
        if router is not None:
            asyncio.run(_p3p4(bh, router))
    finally:
        bh.stop()

if __name__ == "__main__":
    main()