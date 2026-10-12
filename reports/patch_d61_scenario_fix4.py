# -*- coding: utf-8 -*-
"""scripts/patch_d61_scenario_fix4.py — COV-2/D61: dual-stack проба живости.

Полная матрица наблюдений (5 прогонов): /health на 127.0.0.1 отвечает
ТОЛЬКО на lifecycle-spawn (--host 127.0.0.1, g4/g8 GREEN x4); на
менеджер-spawn (--host localhost) — не отвечает никогда (p0 RED x3,
включая 120с стабилизации 18:40), при этом settings-URL (localhost)
отвечает всегда (p0_llm_online GREEN x5). Вывод: сервера живут на разных
loopback-стеках; проба не должна выбирать адрес. Лечение: TCP-connect на
ОБА стека (127.0.0.1 + ::1, 0.5с каждый) — без DNS, без HTTP-слоя; любой
живой стек = online, мёртвый порт = refused мгновенно (тайминг g6
сохраняется). Третье документированное отклонение gateway-адаптера от
роута (прод остаётся на check_llm_health).
Одноразовый; после применения перенести в reports/.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P_SCN = (ROOT / "backend" / "tests" / "sandbox" / "SUPERBOX" / "scenarios"
         / "d61_llm_outage_doctrine_test.py")


class Abort(Exception):
    """Громкий отказ (Law L4): ничего не записано."""


def req(cond, msg):
    if not cond:
        raise Abort(msg)


OLD = (
    '    import urllib.request\n'
    '\n'
    '    from app.core.config import settings\n'
    '\n'
    '    url = f"http://127.0.0.1:{settings.llama_cpp_port}/health"\n'
    '    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))\n'
    '    try:\n'
    '        with opener.open(url, timeout=1.0) as resp:\n'
    '            return (resp.status == 200, f"http={resp.status}")\n'
    '    except Exception as e:\n'
    '        return (False, f"{type(e).__name__}: {str(e)[:60]}")'
)
NEW = (
    '    import socket\n'
    '\n'
    '    from app.core.config import settings\n'
    '\n'
    '    # Dual-stack (матрица 5 прогонов): менеджер поднимает --host localhost\n'
    '    # (стек ::1 — HTTP-проба на 127.0.0.1 не отвечает никогда, стабилизация\n'
    '    # 120с не помогла), lifecycle — --host 127.0.0.1 (g4/g8 GREEN).\n'
    '    # TCP-connect на оба стека: любой живой = online; мёртвый порт =\n'
    '    # refused мгновенно (тайминг g6-дебаунса сохраняется).\n'
    '    _port = int(settings.llama_cpp_port)\n'
    '    _last = "no-attempt"\n'
    '    for _host in ("127.0.0.1", "::1"):\n'
    '        _s = socket.socket(\n'
    '            socket.AF_INET6 if ":" in _host else socket.AF_INET,\n'
    '            socket.SOCK_STREAM,\n'
    '        )\n'
    '        _s.settimeout(0.5)\n'
    '        try:\n'
    '            _s.connect((_host, _port))\n'
    '            return (True, f"tcp:{_host}:{_port}")\n'
    '        except Exception as e:\n'
    '            _last = f"{_host}: {type(e).__name__}"\n'
    '        finally:\n'
    '            _s.close()\n'
    '    return (False, _last)'
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

    req(text.count(OLD) == 1,
        f"якорь найден {text.count(OLD)} раз (ожидался 1) — пришли регион дословно.")
    checks_before = text.count("check(")
    text = text.replace(OLD, NEW, 1)
    print("[ok] хунк dual-stack пробы применён")

    # ---------- стражи (только полные строки + относительные) ------------
    req(text.count("check(") == checks_before,
        f"пост: число check( изменилось {checks_before} -> {text.count('check(')}")
    req(text.count('    for _host in ("127.0.0.1", "::1"):') == 1,
        "пост: строка dual-loop != 1")
    req(text.count('            return (True, f"tcp:{_host}:{_port}")') == 1,
        "пост: строка успеха != 1")
    req(text.count('    return (False, _last)') == 1, "пост: строка отказа != 1")
    req(text.count('url = f"http://127.0.0.1:{settings.llama_cpp_port}/health"') == 0,
        "пост: старая HTTP-проба жива")
    try:
        compile(text, str(P_SCN), "exec")
    except SyntaxError as e:
        raise Abort(f"компиляция не прошла (запись отменена): {e}")
    print("[ok] компиляция в памяти: GREEN; стражи пройдены")

    out = text.replace("\n", "\r\n") if crlf else text
    P_SCN.write_bytes(bom + out.encode("utf-8"))
    print(f"[ok] записано: {P_SCN}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Abort as e:
        print(f"\n[ABORT] {e}\nНичего не записано.", file=sys.stderr)
        sys.exit(2)
