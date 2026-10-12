# -*- coding: utf-8 -*-
"""scripts/patch_d61_scenario_fix1.py — COV-2/D61: fix1 живого сценария.

Прогон 22:56: GREEN=10 RED=1; доктрина ДО точки краша зелёная целиком.
Дефекты HARNESS (не доктрины): F1 Pydantic->json.dumps (TypeError в гейте
g2); F2 превентивный — asyncio.Lock server_lifecycle привязывается к
первому loop, три asyncio.run = 'bound to a different event loop' на g5
(прод живёт в одном loop uvicorn; сценарий — единый фоновый loop);
F3 pool_reset_backoff после успокоения воркеров (окно позднего
record_failure от хвостов run_turn).
В конце — READ-ONLY археология api_client.py (прод-пробел: 30с транспорта
< ~90с загрузки модели для рестарта; фикс по прочитанной сигнатуре отдельно).
Одноразовый; после применения удалить или перенести в reports/.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P_SCN = (ROOT / "backend" / "tests" / "sandbox" / "SUPERBOX" / "scenarios"
         / "d61_llm_outage_doctrine_test.py")
P_API = ROOT / "frontend" / "api_client.py"


class Abort(Exception):
    """Громкий отказ (Law L4): ничего не записано."""


def req(cond, msg):
    if not cond:
        raise Abort(msg)


HUNK_A_OLD = (
    'def _dm_text(resp: Any) -> str:\n'
    '    if isinstance(resp, dict):\n'
    '        v = resp.get("dm_response")\n'
    '        if isinstance(v, str):\n'
    '            return v\n'
    '        if isinstance(v, dict):\n'
    '            return str(v.get("text") or v.get("narrative") or "")\n'
    '    return ""'
)
HUNK_A_NEW = (
    'def _dm_text(resp: Any) -> str:\n'
    '    obj = resp\n'
    '    if obj is not None and hasattr(obj, "model_dump"):\n'
    '        try:\n'
    '            obj = obj.model_dump()  # ChatTurnResponse (Pydantic) -> dict\n'
    '        except Exception:\n'
    '            return ""\n'
    '    if isinstance(obj, dict):\n'
    '        v = obj.get("dm_response")\n'
    '        if isinstance(v, str):\n'
    '            return v\n'
    '        if isinstance(v, dict):\n'
    '            return str(v.get("text") or v.get("narrative") or "")\n'
    '        if v is not None:\n'
    '            return str(v)\n'
    '    return ""\n'
    '\n'
    '\n'
    'def _jsonable(obj: Any) -> Any:\n'
    '    """JSON-safe нормализация: Pydantic -> dict, прочее -> метка типа."""\n'
    '    if obj is None or isinstance(obj, (bool, int, float, str)):\n'
    '        return obj\n'
    '    if isinstance(obj, dict):\n'
    '        return {str(k): _jsonable(v) for k, v in obj.items()}\n'
    '    if isinstance(obj, (list, tuple)):\n'
    '        return [_jsonable(v) for v in obj]\n'
    '    if hasattr(obj, "model_dump"):\n'
    '        try:\n'
    '            return _jsonable(obj.model_dump())\n'
    '        except Exception:\n'
    '            pass\n'
    '    return f"<{type(obj).__name__}>"\n'
    '\n'
    '\n'
    'def _restart_timeout() -> float:\n'
    '    from app.core.config import settings\n'
    '\n'
    '    return float(settings.model_load_timeout_sec) + 120.0\n'
    '\n'
    '\n'
    '_ASYNC_LOOP: Optional["asyncio.AbstractEventLoop"] = None\n'
    '\n'
    '\n'
    'def _ensure_async_loop() -> "asyncio.AbstractEventLoop":\n'
    '    """Единый фоновый loop для всех async-вызовов сценария (fix F2):\n'
    '    asyncio.Lock рестартов привязывается к первому loop; несколько\n'
    '    asyncio.run = RuntimeError. Прод живёт в одном loop (uvicorn)."""\n'
    '    global _ASYNC_LOOP\n'
    '    if _ASYNC_LOOP is None or _ASYNC_LOOP.is_closed():\n'
    '        _ASYNC_LOOP = asyncio.new_event_loop()\n'
    '        threading.Thread(\n'
    '            target=_ASYNC_LOOP.run_forever, daemon=True, name="d61-async-loop"\n'
    '        ).start()\n'
    '    return _ASYNC_LOOP\n'
    '\n'
    '\n'
    'def _call_async(factory, timeout: float) -> Any:\n'
    '    """Корутина в едином loop; factory — zero-arg callable -> coroutine."""\n'
    '    fut = asyncio.run_coroutine_threadsafe(factory(), _ensure_async_loop())\n'
    '    return fut.result(timeout=timeout)'
)
HUNK_B_OLD = (
    '    def restart_llm(self) -> dict:\n'
    '        from app.services.llm.server_lifecycle import restart_llama_server\n'
    '\n'
    '        return asyncio.run(restart_llama_server())'
)
HUNK_B_NEW = (
    '    def restart_llm(self) -> dict:\n'
    '        from app.services.llm.server_lifecycle import restart_llama_server\n'
    '\n'
    '        return _call_async(restart_llama_server, timeout=_restart_timeout())'
)
HUNK_C_OLD = (
    '    rr = _run_turn_boxed(gl, "Спросить у Торнина, как дела.")\n'
    '    if "resp" in rr and isinstance(rr["resp"], dict):\n'
    '        rr["keys"] = sorted(rr["resp"].keys())[:12]\n'
    '        rr["dm"] = _dm_text(rr["resp"])[:200]\n'
    '        del rr["resp"]\n'
    '    _obs("g2_run_turn", rr)\n'
    '    check("g2_run_turn_no_fake_narrative",\n'
    '          "hang" not in rr and "мутнеет" not in json.dumps(rr, ensure_ascii=False).lower(),\n'
    '          f"rr={rr}")\n'
    '    return ctrl'
)
HUNK_C_NEW = (
    '    rr = _run_turn_boxed(gl, "Спросить у Торнина, как дела.")\n'
    '    rr_view = _jsonable(rr)\n'
    '    if isinstance(rr_view, dict) and "resp" in rr_view:\n'
    '        rr_view["dm"] = _dm_text(rr.get("resp"))[:200]\n'
    '        rr_view.pop("resp", None)\n'
    '    _obs("g2_run_turn", rr_view)\n'
    '    check("g2_run_turn_no_fake_narrative",\n'
    '          "hang" not in rr_view\n'
    '          and "мутнеет" not in json.dumps(rr_view, ensure_ascii=False).lower(),\n'
    '          f"rr={rr_view}")\n'
    '    return ctrl'
)
HUNK_D_OLD = (
    '    _obs("g4_run_turn", {k: v for k, v in rr.items() if k != "resp"} | {"dm_len": dm_len})'
)
HUNK_D_NEW = (
    '    _obs("g4_run_turn",\n'
    '         _jsonable({k: v for k, v in rr.items() if k != "resp"})\n'
    '         | {"dm_len": dm_len})'
)
HUNK_E_OLD = (
    '    res = asyncio.run(restart_llama_server())\n'
    '    check("g5_recovery_after_restore", bool(res.get("restarted")), f"res={res}")'
)
HUNK_E_NEW = (
    '    res = _call_async(restart_llama_server, timeout=_restart_timeout())\n'
    '    check("g5_recovery_after_restore", bool(res.get("restarted")), f"res={res}")'
)
HUNK_F_OLD = (
    'def g8_final(gw) -> None:\n'
    '    from app.services.llm.server_lifecycle import restart_llama_server\n'
    '\n'
    '    res = asyncio.run(restart_llama_server())'
)
HUNK_F_NEW = (
    'def g8_final(gw) -> None:\n'
    '    from app.services.llm.server_lifecycle import restart_llama_server\n'
    '\n'
    '    res = _call_async(restart_llama_server, timeout=_restart_timeout())'
)
HUNK_G_OLD = (
    '    _obs("g6_server_stop", _kill_server())\n'
    '    pool = _pool()\n'
    '    if pool:\n'
    '        pool.pool_reset_backoff()  # чистый пул: health-only картина\n'
    '    time.sleep(1.5)  # успокоить фоновые воркеры прошлых тиков'
)
HUNK_G_NEW = (
    '    _obs("g6_server_stop", _kill_server())\n'
    '    time.sleep(1.5)  # успокоить воркеров ДО сброса (fix F3)\n'
    '    pool = _pool()\n'
    '    if pool:\n'
    '        pool.pool_reset_backoff()  # чистый пул: health-only картина'
)


def main() -> int:
    raw = P_SCN.read_bytes()
    bom = b""
    if raw.startswith(b"\xef\xbb\xbf"):  # урок S317: BOM
        bom, raw = raw[:3], raw[3:]
    text = raw.decode("utf-8")
    crlf = "\r\n" in text
    if crlf:
        text = text.replace("\r\n", "\n")

    for tag, old, _new in (
        ("A _dm_text+loop", HUNK_A_OLD, HUNK_A_NEW),
        ("B gateway", HUNK_B_OLD, HUNK_B_NEW),
        ("C g2", HUNK_C_OLD, HUNK_C_NEW),
        ("D g4-obs", HUNK_D_OLD, HUNK_D_NEW),
        ("E g5", HUNK_E_OLD, HUNK_E_NEW),
        ("F g8", HUNK_F_OLD, HUNK_F_NEW),
        ("G g6", HUNK_G_OLD, HUNK_G_NEW),
    ):
        req(text.count(old) == 1,
            f"Хунк {tag}: якорь найден {text.count(old)} раз (ожидался 1) — "
            "файл дрейфнул, пришли регион дословно.")
    for tag, old, new in (
        ("A", HUNK_A_OLD, HUNK_A_NEW), ("B", HUNK_B_OLD, HUNK_B_NEW),
        ("C", HUNK_C_OLD, HUNK_C_NEW), ("D", HUNK_D_OLD, HUNK_D_NEW),
        ("E", HUNK_E_OLD, HUNK_E_NEW), ("F", HUNK_F_OLD, HUNK_F_NEW),
        ("G", HUNK_G_OLD, HUNK_G_NEW),
    ):
        text = text.replace(old, new, 1)
        print(f"[ok] хунк {tag} применён")

    # ---------- стражи write-пути ----------
    req(text.count("def _jsonable(") == 1, "пост: _jsonable != 1")
    req(text.count("_call_async(") == 4,
        f"пост: _call_async != 4 ({text.count('_call_async(')})")
    req(text.count("asyncio.run(restart_llama_server())") == 0,
        "пост: остались прямые asyncio.run(restart_llama_server())")
    req(text.count("model_dump()") >= 2, "пост: model_dump < 2")
    try:
        compile(text, str(P_SCN), "exec")
    except SyntaxError as e:
        raise Abort(f"компиляция не прошла (запись отменена): {e}")
    print("[ok] компиляция в памяти: GREEN; стражи пройдены")

    out = text.replace("\n", "\r\n") if crlf else text
    P_SCN.write_bytes(bom + out.encode("utf-8"))
    print(f"[ok] записано: {P_SCN}")

    # ---------- READ-ONLY археология api_client (прод-пробел таймаута) ----
    print("\n--- АРХЕОЛОГИЯ (read-only): транспорт api_client.py ---")
    api = P_API.read_text(encoding="utf-8", errors="replace")
    for m in re.finditer(r"def (get|post|put|delete|_request)\(self[^)]*\)", api):
        print("sig:", re.sub(r"\s+", " ", m.group(0)))
    for i, ln in enumerate(api.split("\n")):
        if "urlopen(" in ln:
            print(f"urlopen@{i + 1}: {ln.strip()}")
    print("--- конец археологии ---")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Abort as e:
        print(f"\n[ABORT] {e}\nНичего не записано.", file=sys.stderr)
        sys.exit(2)
