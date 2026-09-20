# path: backend/tests/sandbox/probes/o399_worker_boundary_probe.py
# Назначение: ADR-O-399 structural proof — воркер _process_tasks_async не имеет
# права observable-эффектов (bus.publish / scene_state мутации / dialogue RAM /
# economy observable / speech admission). Падает при возврате эффекта в воркер.
# Зависимости: чтение исходника task_scheduler.py (без импорта рантайма)
# Основные сущности: probe_main()
"""
Запуск: 
"""

from pathlib import Path

_SOURCE = Path(__file__).resolve().parents[3] / "app" / "services" / "game_loop" / "task_scheduler.py"

_FORBIDDEN_IN_WORKER = (
    "bus.publish",
    "scene_state[",
    ".setdefault(",
    "_recent_dialogues.append",
    "_recent_dialogues =",
    "record_talk(",
    "reset_context(",
    "_last_talk_tick",
)


def _worker_body(src: str) -> str:
    start = src.index("def _process_tasks_async(")
    nxt = src.index("\n    def ", start + 10)
    return src[start:nxt]


def probe_main() -> None:
    body = _worker_body(_SOURCE.read_text(encoding="utf-8"))
    violations = [p for p in _FORBIDDEN_IN_WORKER if p in body]
    print(f"[PROBE-O399] worker body lines={len(body.splitlines())}")
    if violations:
        for v in violations:
            print(f"[PROBE-O399] 🔴 worker observable effect: '{v}'")
        raise SystemExit(1)
    print("[PROBE-O399] ✅ worker produces DATA only — boundary intact")


if __name__ == "__main__":
    probe_main()