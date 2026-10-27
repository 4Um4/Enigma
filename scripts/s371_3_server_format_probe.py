"""
S371.3-pre расширенный probe: какие форматы JSON-ограничения поддерживает llama-server?

Проверяет:
1. response_format: {"type": "json_object"}  (OpenAI basic — уже проверено, игнорируется)
2. response_format: {"type": "json_schema", "json_schema": {"name": "test", "schema": {...}}}
3. response_format: {"type": "json_object", "schema": {...}}  (нестандартный)
4. grammar: "root ::= {...}"  (GBNF, родной llama.cpp /completion endpoint)

Тестовый промпт намеренно провокационный — просит LLM вернуть НЕ валидный JSON
(с пояснением), чтобы увидеть, подавляет ли ограничение свободный текст.

Запуск: python scripts/s371_3_server_format_probe.py
"""
from __future__ import annotations

import json
import sys
import urllib.request

URL = "http://localhost:8181/v1/chat/completions"
URL_COMPLETION = "http://localhost:8181/completion"

# Провокационный промпт: просим свободный текст, не JSON.
# Если ограничение работает — ответ будет JSON несмотря на просьбу.
PROVOCATION = (
    "Explain in plain English what is 2+2. "
    "Write a sentence, not JSON. Do not use curly braces."
)
SIMPLE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": {"type": "object"}}
    },
    "required": ["items"],
}
GBNF_GRAMMAR = r'''root ::= "{" ws "\"items\"" ws ":" ws "[" ws item* ws "]" ws "}"
item ::= "{" ws "\"x\"" ws ":" ws number ws "}" ws?
ws ::= [ \t\n]*
number ::= [0-9]+'''


def _call_chat(payload: dict) -> tuple[str, str]:
    """POST /v1/chat/completions → (content, error_or_empty)."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        URL, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"], ""
    except Exception as e:
        return "", f"{type(e).__name__}: {e}"


def _call_completion(payload: dict) -> tuple[str, str]:
    """POST /completion (native llama.cpp) → (content, error_or_empty)."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        URL_COMPLETION, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body.get("content", ""), ""
    except Exception as e:
        return "", f"{type(e).__name__}: {e}"


def main() -> int:
    msg = [{"role": "user", "content": PROVOCATION}]
    base_chat = {"messages": msg, "max_tokens": 80, "temperature": 0}
    base_completion = {
        "prompt": "User: " + PROVOCATION + "\nAssistant: ",
        "n_predict": 80,
        "temperature": 0,
        "stop": ["</s>", "<|im_end|>"],
    }

    probes = [
        ("1. baseline (no response_format)", "chat", {}),
        ("2. response_format json_object", "chat",
         {"response_format": {"type": "json_object"}}),
        ("3. response_format json_schema (OpenAI)", "chat",
         {"response_format": {"type": "json_schema",
                              "json_schema": {"name": "test", "schema": SIMPLE_JSON_SCHEMA}}}),
        ("4. response_format json_object+schema", "chat",
         {"response_format": {"type": "json_object", "schema": SIMPLE_JSON_SCHEMA}}),
        ("5. grammar GBNF (/completion)", "completion",
         {"grammar": GBNF_GRAMMAR}),
    ]

    print(f"[S371.3-PROBE] Provocation prompt:\n  {PROVOCATION}\n")
    print(f"[S371.3-PROBE] If JSON-constraint works, response will be JSON despite asking for plain text.\n")

    results = []
    for label, kind, extra in probes:
        if kind == "chat":
            content, err = _call_chat({**base_chat, **extra})
        else:
            content, err = _call_completion({**base_completion, **extra})

        if err:
            print(f"{label}\n  ERROR: {err}\n")
            results.append((label, "ERROR", err))
            continue

        is_json = content.strip().startswith("{") and content.strip().endswith("}")
        verdict = "JSON (constraint active?)" if is_json else "PLAIN TEXT (no constraint)"
        print(f"{label}")
        print(f"  content={content!r}")
        print(f"  verdict: {verdict}\n")
        results.append((label, verdict, content))

    # Сводка
    print("[S371.3-PROBE] СВОДКА:")
    for label, verdict, _ in results:
        print(f"  {label}: {verdict}")

    return 0


if __name__ == "__main__":
    sys.exit(main())