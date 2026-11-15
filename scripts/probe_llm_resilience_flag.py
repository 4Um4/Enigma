"""S-probe: фактический LLM_RESILIENCE_V1 в живом backend. ТЗ LLM_RESILIENCE_V1 §4.1."""
import json
import sys

import psutil

FLAG = "LLM_RESILIENCE_V1"
MARKERS = ("main.py", "uvicorn", "backend", "pipeline_runner", "game_loop")


def _iter_backend() -> list[dict]:
    hits = []
    for p in psutil.process_iter(["pid", "ppid", "name", "cmdline"]):
        try:
            name = (p.info.get("name") or "").lower()
            cmd = " ".join(p.info.get("cmdline") or [])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if "python" not in name:
            continue
        low = cmd.lower()
        if any(m in low for m in MARKERS):
            hits.append({"proc": p, "pid": p.pid, "ppid": p.info.get("ppid"), "cmdline": cmd})
    return hits


def main() -> int:
    procs = _iter_backend()
    if not procs:
        print("NO_BACKEND_FOUND")
        return 1
    report = []
    for rec in procs:
        p = rec["proc"]
        item = {"pid": rec["pid"], "ppid": rec["ppid"], "cmdline": rec["cmdline"]}
        try:
            env = p.environ()
            item["flag_present"] = FLAG in env
            item["flag_value"] = env.get(FLAG, "<ABSENT>")
        except psutil.AccessDenied:
            item["error"] = "ACCESS_DENIED (запуск от того же пользователя / elevated)"
        except Exception as exc:  # noqa: BLE001 — диагностика, fail-loud по выводу
            item["error"] = repr(exc)
        report.append(item)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())