# -*- coding: utf-8 -*-
"""scripts/patch_d61_scenario_fix2.py — COV-2/D61: fix2 живого сценария (v3).

Хроника ABORT: v1 — страж считал упоминания в моих же докстрингах (2, не 0);
v2 — тот же класс (упоминаний 3, страж ждал 2). Оба защитили дерево (файл
оставался fix1; прогоны 23:13/23:26/00:12 = идентичный RED g6). v3: стражи-
счётчики упоминаний УДАЛЕНЫ — только точные код-паттерны (вызов со скобкой,
строка импорта, URL). Принцип «стражи матчат КОД» теперь исполняется самим
скриптом, а не только декларируется.

Суть fix2 (4 прогона GREEN=31 RED=1, g6_watcher_live_debounce, unconfirmed=1
за окно): проба health занимает ~7с. Диагноз: резолв localhost — DNS вне
socket-таймаута (getaddrinfo не ограничен urlopen(timeout)); наблюдение
server_lifecycle («резолв localhost добавляет секунды на каждый health-
запрос»). Лечение: проба /health на явном 127.0.0.1:{llama_cpp_port} (без
DNS; сервер слушает localhost при обоих вариантах спавна), таймаут 1с,
без прокси; окно живого дебаунса 8->12с. Env-путь отвергнут (сломал бы g4:
живые генерации ~5с, S342).
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


H1_IMPORT_OLD = (
    '        from app.services.llm.health import check_llm_health\n'
    '        from app.services.llm.provider_manager import get_model_pool'
)
H1_IMPORT_NEW = (
    '        from app.services.llm.provider_manager import get_model_pool'
)
H1_BLOCK_OLD = (
    '        health = check_llm_health(use_cache=False)\n'
    '        if health.get("status") != "online":\n'
    '            return {"status": "unconfirmed",\n'
    '                    "reason": f"health offline: {health.get(\'status\')}"}\n'
    '        return {"status": "online", "reason": ""}'
)
H1_BLOCK_NEW = (
    '        online, why = _health_online_fast()\n'
    '        if not online:\n'
    '            return {"status": "unconfirmed",\n'
    '                    "reason": f"health offline: {why}"}\n'
    '        return {"status": "online", "reason": ""}'
)
H1_FUNC_OLD = 'class _OutageGateway:\n    """Адаптер production-семантики роута /llm/outage (routes.py:380):'
H1_FUNC_NEW = (
    'def _health_online_fast() -> "tuple[bool, str]":\n'
    '    """Быстрая проба живости: /health на явном 127.0.0.1 — без DNS\n'
    '    (резолв localhost вне socket-таймаута: getaddrinfo не ограничен\n'
    '    urlopen(timeout); наблюдение server_lifecycle + живые прогоны —\n'
    '    проба по localhost-URL ~7с). Семантика /health из\n'
    '    server_lifecycle._await_llama_ready. Прод-роут остаётся на\n'
    '    кэшируемом check_llm_health (латентность прод-дебаунса = 1\n'
    '    медленная проба на TTL кэша — наблюдение в артефакте)."""\n'
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
    '        return (False, f"{type(e).__name__}: {str(e)[:60]}")\n'
    '\n'
    '\n'
    'class _OutageGateway:\n'
    '    """Адаптер production-семантики роута /llm/outage (routes.py:380):'
)
H1_DOC_OLD = '    Отличие от роута: use_cache=False — детерминизм живого прогона."""'
H1_DOC_NEW = (
    '    Отличия от роута: быстрая health-проба (127.0.0.1, 1с) вместо\n'
    '    check_llm_health по settings-URL — тайминг дебаунса прогона."""'
)
H2_OLD = '    check("g6_watcher_live_debounce",\n          _wait_pause(ctrl2, 8.0) and ctrl2._unconfirmed >= 2,'
H2_NEW = '    check("g6_watcher_live_debounce",\n          _wait_pause(ctrl2, 12.0) and ctrl2._unconfirmed >= 2,'
H3_OLD = (
    '        "atexit server_lifecycle остановит lifecycle-spawned сервер при выходе",\n'
    '    ],'
)
H3_NEW = (
    '        "atexit server_lifecycle остановит lifecycle-spawned сервер при выходе",\n'
    '        "gateway: health-проба 127.0.0.1:port/health (1с, без DNS) вместо check_llm_health — '
    'тайминг дебаунса; прод-латентность дебаунса = 1 медленная проба на TTL кэша",\n'
    '    ],'
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

    for tag, old in (
        ("H1a import", H1_IMPORT_OLD), ("H1b блок", H1_BLOCK_OLD),
        ("H1c функция", H1_FUNC_OLD), ("H1d докстринг", H1_DOC_OLD),
        ("H2 окно", H2_OLD), ("H3 boundary", H3_OLD),
    ):
        req(text.count(old) == 1,
            f"{tag}: якорь найден {text.count(old)} раз (ожидался 1) — "
            "пришли регион дословно.")

    for old, new in (
        (H1_IMPORT_OLD, H1_IMPORT_NEW), (H1_BLOCK_OLD, H1_BLOCK_NEW),
        (H1_FUNC_OLD, H1_FUNC_NEW), (H1_DOC_OLD, H1_DOC_NEW),
        (H2_OLD, H2_NEW), (H3_OLD, H3_NEW),
    ):
        text = text.replace(old, new, 1)
    print("[ok] хунки H1a-H3 применены")

    # ---------- стражи write-пути (v3: ТОЛЬКО код-паттерны) --------------
    req(text.count("def _health_online_fast(") == 1, "пост: функция != 1")
    req(text.count("check_llm_health(") == 0,
        "пост: вызовы check_llm_health( живы в коде")
    req(text.count("from app.services.llm.health import") == 0,
        "пост: import check_llm_health жив")
    req(text.count("_wait_pause(ctrl2, 12.0)") == 1, "пост: окно 12с != 1")
    req(text.count("_wait_pause(ctrl2, 8.0)") == 0, "пост: старое окно живо")
    req(text.count("127.0.0.1:{settings.llama_cpp_port}") == 1,
        "пост: проба не на 127.0.0.1")
    try:
        compile(text, str(P_SCN), "exec")
    except SyntaxError as e:
        raise Abort(f"компиляция не прошла (запись отменена): {e}")
    print("[ok] компиляция в памяти: GREEN; стражи v3 пройдены")

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
