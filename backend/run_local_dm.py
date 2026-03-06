import argparse
import os
import sys
from pathlib import Path


def _bootstrap_paths() -> None:
    if getattr(sys, "frozen", False):
        return
    backend_root = Path(__file__).resolve().parent
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))


def main() -> int:
    _bootstrap_paths()

    parser = argparse.ArgumentParser(description="Local AI Dungeon Master backend launcher")
    parser.add_argument("--host", default=os.getenv("AIDM_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("AIDM_PORT", "8000")))
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (dev mode)")
    parser.add_argument("--health-check", action="store_true", help="Only check app import and exit")
    args = parser.parse_args()

    from app.main import app

    if args.health_check:
        print(f"OK: {app.title}")
        return 0

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
