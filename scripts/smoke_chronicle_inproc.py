# path: /project/scripts/smoke_chronicle_inproc.py
# Назначение: BLOCK 5 — smoke эндпоинтов хроники БЕЗ запущенного сервера
# (BLOCK 4: 127.0.0.1:8000 не отвечает — smoke не прошёл именно из-за этого).
# TestClient поднимает app в процессе и дёргает те же URL, что редактор:
# roster + understanding (source=drafts/canon) для silver_wolf.
# Побочная ценность: если backend падает на ИМПОРТЕ (ImportError/NameError
# невидимы для py_compile) — трейсбек будет напечатан прямо здесь.
# Выход: 0=OK, 1=есть 4xx/5xx, 2=app не найден, 3=нет httpx, 4=startup упал.
# Печать намеренно ASCII (консоль Мастера: риск-зона кодировок).
import importlib
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "backend"), str(ROOT / "backend" / "app")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_CAND = ("app.main", "main", "app", "app.application", "app.asgi", "app.server")


def find_app():
    _errs = []
    _tb = ""
    for _n in _CAND:
        try:
            _m = importlib.import_module(_n)
        except Exception as _e:
            _errs.append(_n + " -> " + repr(_e))
            if not _tb:
                _tb = traceback.format_exc()[-1500:]
            continue
        _a = getattr(_m, "app", None)
        if _a is not None and hasattr(_a, "routes"):
            return _n, _a
    if _errs:
        print("--- IMPORT TRACEBACK (first failed candidate) ---")
        print(_tb)
        print("all failed:", "; ".join(_errs))
    return None, None


_mod, app = find_app()
if app is None:
    print("APP NOT FOUND: tried", ", ".join(_CAND))
    sys.exit(2)
print("app imported from:", _mod)

try:
    from fastapi.testclient import TestClient
except Exception as _e:
    print("TestClient unavailable (pip install httpx?):", repr(_e)[:200])
    sys.exit(3)


def check(client, label, url, **kw):
    try:
        r = client.get(url, **kw)
    except Exception as e:
        print(label + ": EXCEPTION")
        print("   " + repr(e)[:300])
        return 1
    print(label + ":", r.status_code)
    if r.status_code != 200:
        print("   body:", r.text[:300])
        return 1
    try:
        d = r.json()
    except Exception:
        d = None
    if isinstance(d, dict):
        print("   status:", d.get("status"),
              "| count:", d.get("count", "-"),
              "| keys:", ", ".join(list(d)[:12]))
    elif isinstance(d, list):
        print("   list len:", len(d), "| first:", str(d[:2])[:200])
    else:
        print("   body:", r.text[:200])
    return 0


_fail = 0
try:
    with TestClient(app) as _client:
        _fail += check(_client, "roster", "/api/chronicle/roster/silver_wolf")
        for _src in ("drafts", "canon"):
            _fail += check(_client, "understanding[" + _src + "]",
                           "/api/chronicle/silver_wolf/understanding",
                           params={"source": _src, "format": "json"})
except Exception:
    print("APP STARTUP FAILED:")
    print(traceback.format_exc()[-1500:])
    sys.exit(4)

print("SMOKE:", "FAIL" if _fail else "OK")
sys.exit(1 if _fail else 0)