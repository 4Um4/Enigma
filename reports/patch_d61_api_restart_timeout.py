# -*- coding: utf-8 -*-
"""scripts/patch_d61_api_restart_timeout.py — COV-2/D61: per-call таймаут
рестарта в HttpClient (v3).

Хроника ABORT: v1 — якорь с угаданной ═-линией (0 совпадений); v2 — страж
считал упоминания константы в докстринге (3, не 2) — тот же класс, что у
fix2 v1/v2. Оба защитили дерево (api_client не тронут, коммит A пуст).
v3: стражи = точные код-паттерны (определение и вызов), якорь-константа =
хвост URLError-хендлера (строки кода).

Пробел: _execute (api_client.py:193) всегда urlopen с self.timeout_sec=30;
прод-роут /api/llm/restart живёт до backend model_load_timeout_sec (~90с).
Итог: на ~30с RESTARTING транспорт рвётся -> ложный FAILED «транспортная
ошибка» при ШТАТНО долгом рестарте. Фикс: post/_execute получают опциональный
timeout_sec (per-call override, дефолт None -> self.timeout_sec — все
существующие вызовы байт-неизменны); restart_llm шлёт
_LLM_RESTART_TIMEOUT_SEC=180 (Закон 6.2: импорт backend-настроек во
frontend запрещён — константа фронта с запасом).
Одноразовый; после применения перенести в reports/ (перезаписью).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P_API = ROOT / "frontend" / "api_client.py"


class Abort(Exception):
    """Громкий отказ (Law L4): ничего не записано."""


def req(cond, msg):
    if not cond:
        raise Abort(msg)


POST_OLD = (
    '    def post(self, path: str, payload: dict | None = None) -> dict:\n'
    '        """POST запрос → распарсенный JSON."""\n'
    '        url = self.base_url + path\n'
    '        data = json.dumps(payload).encode("utf-8") if payload else b"{}"\n'
    '        headers = {"Content-Type": "application/json"}\n'
    '        req = urllib.request.Request(url, data=data, headers=headers, method="POST")\n'
    '        return self._execute(req)'
)
POST_NEW = (
    '    def post(\n'
    '        self, path: str, payload: dict | None = None, timeout_sec: int | None = None\n'
    '    ) -> dict:\n'
    '        """POST запрос → распарсенный JSON (timeout_sec: per-call override)."""\n'
    '        url = self.base_url + path\n'
    '        data = json.dumps(payload).encode("utf-8") if payload else b"{}"\n'
    '        headers = {"Content-Type": "application/json"}\n'
    '        req = urllib.request.Request(url, data=data, headers=headers, method="POST")\n'
    '        return self._execute(req, timeout_sec=timeout_sec)'
)
EXEC_OLD = (
    '    def _execute(self, req: urllib.request.Request) -> dict:\n'
    '        """Выполняет запрос, возвращает dict. При ошибке — BackendError."""\n'
    '        try:\n'
    '            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:'
)
EXEC_NEW = (
    '    def _execute(\n'
    '        self, req: urllib.request.Request, timeout_sec: int | None = None\n'
    '    ) -> dict:\n'
    '        """Выполняет запрос, возвращает dict. При ошибке — BackendError."""\n'
    '        try:\n'
    '            _timeout = timeout_sec if timeout_sec is not None else self.timeout_sec\n'
    '            with urllib.request.urlopen(req, timeout=_timeout) as resp:'
)
CONST_OLD = (
    '        except urllib.error.URLError as e:\n'
    '            raise BackendError(\n'
    '                f"Backend недоступен ({self.base_url}): {e.reason}"\n'
    '            ) from e'
)
CONST_NEW = (
    '        except urllib.error.URLError as e:\n'
    '            raise BackendError(\n'
    '                f"Backend недоступен ({self.base_url}): {e.reason}"\n'
    '            ) from e\n'
    '\n'
    '\n'
    '# COV-2/D61: таймаут HTTP-транспорта для рестарта llama-server.\n'
    '# Авторитет длительности — backend model_load_timeout_sec (загрузка\n'
    '# модели до ~90с); импорт backend-настроек во frontend запрещён\n'
    '# (Закон 6.2), поэтому константа фронта с запасом. Дефолт транспорта\n'
    '# 30с даёт ложный FAILED при штатно долгом рестарте (находка живого\n'
    '# прогона D61, доктрина №4 — только честные причины провала).\n'
    '_LLM_RESTART_TIMEOUT_SEC = 180'
)
RESTART_OLD = (
    '    def restart_llm(self) -> dict:\n'
    '        """COV-2/D61: перезапуск llama-server (прод-роут lifecycle)."""\n'
    '        return self._t.post("/api/llm/restart", {})'
)
RESTART_NEW = (
    '    def restart_llm(self) -> dict:\n'
    '        """COV-2/D61: перезапуск llama-server (прод-роут lifecycle).\n'
    '\n'
    '        Таймаут транспорта — _LLM_RESTART_TIMEOUT_SEC: прод-роут живёт\n'
    '        до model_load_timeout_sec бэкенда; дефолт транспорта 30с давал\n'
    '        ложный FAILED при штатно долгом рестарте (доктрина №4 — только\n'
    '        честные причины провала).\n'
    '        """\n'
    '        return self._t.post(\n'
    '            "/api/llm/restart", {}, timeout_sec=_LLM_RESTART_TIMEOUT_SEC\n'
    '        )'
)


def main() -> int:
    raw = P_API.read_bytes()
    bom = b""
    if raw.startswith(b"\xef\xbb\xbf"):  # урок S317: BOM
        bom, raw = raw[:3], raw[3:]
    text = raw.decode("utf-8")
    crlf = "\r\n" in text
    if crlf:
        text = text.replace("\r\n", "\n")

    for tag, old in (("post", POST_OLD), ("_execute", EXEC_OLD),
                     ("константа", CONST_OLD), ("restart_llm", RESTART_OLD)):
        req(text.count(old) == 1,
            f"{tag}: якорь найден {text.count(old)} раз (ожидался 1) — "
            "пришли регион дословно.")
    for old, new in ((POST_OLD, POST_NEW), (EXEC_OLD, EXEC_NEW),
                     (CONST_OLD, CONST_NEW), (RESTART_OLD, RESTART_NEW)):
        text = text.replace(old, new, 1)
    print("[ok] хунки post/_execute/константа/restart_llm применены")

    # ---------- стражи write-пути (v3: ТОЛЬКО код-паттерны) --------------
    req(text.count("_LLM_RESTART_TIMEOUT_SEC = 180") == 1,
        "пост: определение константы != 1")
    req(text.count("timeout_sec=_LLM_RESTART_TIMEOUT_SEC") == 1,
        "пост: код-использование != 1")
    req(text.count("timeout_sec: int | None = None") == 2,
        "пост: сигнатур с override != 2 (post + _execute)")
    req(text.count('"/api/llm/restart"') == 1, "пост: рестарт-роут != 1")
    req(text.count("def put(self, path: str, payload: dict | None = None) -> dict:") == 1,
        "пост: put затронут (незаконное изменение)")
    try:
        compile(text, str(P_API), "exec")
    except SyntaxError as e:
        raise Abort(f"компиляция не прошла (запись отменена): {e}")
    print("[ok] компиляция в памяти: GREEN; стражи v3 пройдены")

    out = text.replace("\n", "\r\n") if crlf else text
    P_API.write_bytes(bom + out.encode("utf-8"))
    print(f"[ok] записано: {P_API}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Abort as e:
        print(f"\n[ABORT] {e}\nНичего не записано.", file=sys.stderr)
        sys.exit(2)
