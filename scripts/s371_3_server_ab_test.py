"""
S371.3-pre server-side A/B: сравнение ответов llama-server с response_format и без.

Контракт проверки (Мастер, п.6 мандата): убедиться, что используемая версия
llama-server поддерживает response_format в /v1/chat/completions и действительно
применяет JSON-ограничение.

Запуск: python scripts/s371_3_server_ab_test.py
Вывод: WITHOUT / WITH / SAME? + длина каждого ответа.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

URL = "http://localhost:8181/v1/chat/completions"


def _call(opener, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        URL, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    # S97 FIX: обход прокси
    _opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with _opener.open(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    msg = [{"role": "user", "content": 'Return ONLY valid JSON: {"items": [{"x": 1}, {"y": 2}]}. End with closing brace.'}]

    print(f"[S371.3-AB] POST {URL}")
    print(f"[S371.3-AB] prompt: {msg[0]['content'][:120]}...")

    # A: без response_format
    try:
        r1 = _call(None, {"messages": msg, "max_tokens": 100, "temperature": 0})
        c1 = r1["choices"][0]["message"]["content"]
        print(f"\nWITHOUT response_format:")
        print(f"  len={len(c1)}")
        print(f"  content={c1!r}")
    except Exception as e:
        print(f"[S371.3-AB] WITHOUT failed: {e}")
        return 1

    # B: с response_format json_object
    try:
        r2 = _call(
            None,
            {
                "messages": msg,
                "max_tokens": 100,
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
        )
        c2 = r2["choices"][0]["message"]["content"]
        print(f"\nWITH response_format=json_object:")
        print(f"  len={len(c2)}")
        print(f"  content={c2!r}")
    except Exception as e:
        print(f"[S371.3-AB] WITH failed: {e}")
        return 1

    same = c1 == c2
    print(f"\nSAME? {same}")

    if same:
        print("[S371.3-AB] ВЕРДИКТ: сервер ИГНОРИРУЕТ response_format — ответы идентичны")
        return 2
    else:
        print("[S371.3-AB] ВЕРДИКТ: сервер РЕАГИРУЕТ на response_format — ответы различаются")
        return 0


if __name__ == "__main__":
    sys.exit(main())