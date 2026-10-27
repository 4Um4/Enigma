"""
S371.3-GBNF-STABILITY: матрица экспериментов A-E для установления причины
деградации сервера при GBNF (мандат S371.3-GBNF-STABILITY §3).

Принципы:
- диагностический spike, без production-изменений
- STOP при первом падении сервера (мандат §3)
- проверка GPU/RAM перед/после каждого запроса
- один запрос за тест, пауза между тестами
- фиксация: latency, tokens, HTTP status, error type, процесс жив/мёртв

Матрица:
  A: /v1/chat/completions без GBNF (контрольная стабильность)
  B: /completion с минимальной фиксированной грамматикой
  C: /completion с текущей рекурсивной грамматикой (config/chronicle_decompose.gbnf)
  D: /completion с грамматикой ограниченной глубины (string|number|bool|null, БЕЗ nested)
  E: повторный запрос с той же грамматикой C (накопительная деградация, prompt cache)

Запуск: python scripts/s371_3_stability_matrix.py
Артефакт: reports/s371_3_stability_matrix_{timestamp}.json
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parents[1]
URL_CHAT = "http://localhost:8181/v1/chat/completions"
URL_COMPLETION = "http://localhost:8181/completion"
URL_HEALTH = "http://localhost:8181/health"
GBNF_PATH = _ROOT / "config" / "chronicle_decompose.gbnf"

# Минимальная фиксированная грамматика (B): {"x": N}
GBNF_MINIMAL = 'root ::= "{\\"x\\": " [0-9]+ "}"'

# Грамматика ограниченной глубины (D): root + array + object, value = scalar только (БЕЗ nested object/array в payload)
GBNF_DEPTH_LIMITED = r'''root ::= "{" ws "\"items\"" ws ":" ws array ws "}"
array ::= "[" ws (item (ws "," ws item)*)? ws "]"
item ::= "{" ws "\"kind\"" ws ":" ws string ws "," ws "\"draft_payload\"" ws ":" ws payload_object ws "," ws "\"confidence\"" ws ":" ws number ws "," ws "\"needs_confirmation\"" ws ":" ws bool ws "," ws "\"question\"" ws ":" ws "null" ws "}"
payload_object ::= "{" ws (payload_member (ws "," ws payload_member)*)? ws "}"
payload_member ::= string ws ":" ws scalar
scalar ::= string | number | bool | "null"
string ::= "\"" char* "\""
char ::= [^"\\] | "\\" ["\\/bfnrtu]
number ::= "-"? ([0-9]+) ("." [0-9]+)? ([eE] [-+]? [0-9]+)?
bool ::= "true" | "false"
ws ::= [ \t\n]*
'''

# Простой промпт для A/B (минимальная нагрузка)
SIMPLE_PROMPT = "Return the number 42 as JSON: {\"x\": 42}"

# Промпт для C/D/E — один из 7 проблемных фрагментов (goran/13 — самый короткий)
CHRONICLE_PROMPT = (
    "<|im_start|>system\nYou are a chronicle decomposer. Return ONLY valid JSON.\n<|im_end|>\n"
    "<|im_start|>user\nДекомпозируй фрагмент. Верни JSON {\"items\": [...]}.\n<|im_end|>\n"
    "<|im_start|>assistant\n"
)


@dataclass
class ResourceSnapshot:
    gpu_total_mb: Optional[int] = None
    gpu_used_mb: Optional[int] = None
    gpu_free_mb: Optional[int] = None
    gpu_util_pct: Optional[int] = None
    ram_total_mb: Optional[int] = None
    ram_free_mb: Optional[int] = None


@dataclass
class TestResult:
    test_id: str
    description: str
    endpoint: str
    grammar_used: bool
    pre_resources: ResourceSnapshot = field(default_factory=ResourceSnapshot)
    request_start: float = 0.0
    request_end: float = 0.0
    latency_ms: float = 0.0
    http_status: Optional[int] = None
    error_type: Optional[str] = None
    content: str = ""
    tokens_predicted: Optional[int] = None
    tokens_per_sec: Optional[float] = None
    json_parsed: bool = False
    json_error: Optional[str] = None
    post_resources: ResourceSnapshot = field(default_factory=ResourceSnapshot)
    server_alive_post: bool = True
    server_logs_tail: str = ""


def _probe_gpu_ram() -> ResourceSnapshot:
    snap = ResourceSnapshot()
    # GPU via nvidia-smi
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total,memory.used,memory.free,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if out.returncode == 0:
            parts = out.stdout.strip().split(", ")
            snap.gpu_total_mb = int(parts[0])
            snap.gpu_used_mb = int(parts[1])
            snap.gpu_free_mb = int(parts[2])
            snap.gpu_util_pct = int(parts[3])
    except Exception:
        pass
    # RAM via WMI
    try:
        import ctypes
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MEMORYSTATUSEX()
        m.dwLength = ctypes.sizeof(m)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        snap.ram_total_mb = m.ullTotalPhys // (1024 * 1024)
        snap.ram_free_mb = m.ullAvailPhys // (1024 * 1024)
    except Exception:
        pass
    return snap


def _probe_health() -> bool:
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        opener.open(URL_HEALTH, timeout=3).read()
        return True
    except Exception:
        return False


def _call_chat(prompt: str, max_tokens: int = 50) -> Tuple[Optional[Dict], Optional[str]]:
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(URL_CHAT, data=data, headers={"Content-Type": "application/json"}, method="POST")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _call_completion(prompt: str, grammar: str, max_tokens: int = 2048) -> Tuple[Optional[Dict], Optional[str]]:
    payload = {
        "prompt": prompt,
        "n_predict": max_tokens,
        "stream": False,
        "temperature": 0,
        "top_p": 0.9,
        "repeat_penalty": 1.12,
        "min_p": 0.1,
        "top_k": 40,
        "n_keep": 800,
        "stop": ["<|im_end|>", "</s>"],
        "grammar": grammar,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(URL_COMPLETION, data=data, headers={"Content-Type": "application/json"}, method="POST")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=180) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _get_logs_tail(n: int = 5) -> str:
    log_path = _ROOT / "backend" / "logs" / "llama_server_stderr.log"
    if not log_path.exists():
        return ""
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except Exception:
        return ""


def run_test(test_id: str, description: str, endpoint: str, grammar_used: bool,
             prompt: str, grammar: Optional[str] = None, max_tokens: int = 50) -> TestResult:
    result = TestResult(test_id=test_id, description=description, endpoint=endpoint, grammar_used=grammar_used)

    print(f"\n[{test_id}] {description}")
    print(f"  endpoint={endpoint}, grammar={grammar_used}, max_tokens={max_tokens}")

    # Pre: resources + health
    result.pre_resources = _probe_gpu_ram()
    print(f"  PRE: GPU used={result.pre_resources.gpu_used_mb}MB free={result.pre_resources.gpu_free_mb}MB util={result.pre_resources.gpu_util_pct}% | RAM free={result.pre_resources.ram_free_mb}MB")
    if not _probe_health():
        print(f"  PRE: SERVER DEAD — пропуск теста")
        result.error_type = "PRE: server dead"
        result.server_alive_post = False
        return result

    # Request
    result.request_start = time.time()
    if endpoint == "chat":
        body, err = _call_chat(prompt, max_tokens)
    else:
        body, err = _call_completion(prompt, grammar or "", max_tokens)
    result.request_end = time.time()
    result.latency_ms = (result.request_end - result.request_start) * 1000

    if err:
        result.error_type = err
        print(f"  ERROR: {err}")
        print(f"  latency={result.latency_ms:.0f}ms")
    else:
        result.http_status = 200
        if endpoint == "chat":
            result.content = body["choices"][0]["message"]["content"]
            result.tokens_predicted = body.get("usage", {}).get("completion_tokens")
        else:
            result.content = body.get("content", "")
            result.tokens_predicted = body.get("tokens_predicted")
            timings = body.get("timings", {})
            if timings.get("predicted_n", 0) > 0:
                result.tokens_per_sec = timings["predicted_n"] / max(timings.get("predicted_ms", 1) / 1000, 0.001)
        print(f"  OK: tokens={result.tokens_predicted}, latency={result.latency_ms:.0f}ms, tok/s={result.tokens_per_sec}")
        print(f"  content[:120]={result.content[:120]!r}")

        # JSON check
        try:
            json.loads(result.content.strip())
            result.json_parsed = True
            print(f"  JSON: parsed OK")
        except json.JSONDecodeError as e:
            result.json_error = str(e)
            print(f"  JSON: FAIL ({e})")

    # Post: resources + health + logs
    time.sleep(2)  # пауза для стабилизации
    result.post_resources = _probe_gpu_ram()
    result.server_alive_post = _probe_health()
    result.server_logs_tail = _get_logs_tail(5)
    print(f"  POST: GPU used={result.post_resources.gpu_used_mb}MB free={result.post_resources.gpu_free_mb}MB util={result.post_resources.gpu_util_pct}% | RAM free={result.post_resources.ram_free_mb}MB | server_alive={result.server_alive_post}")

    return result


def main() -> int:
    print("[S371.3-STABILITY] Матрица экспериментов A-E")
    print(f"  GPU baseline: {_probe_gpu_ram()}")
    print(f"  Server alive: {_probe_health()}")

    if not _probe_health():
        print("[S371.3-STABILITY] Сервер мёртв — подними сначала")
        return 1

    # Загрузить текущую рекурсивную грамматику (C, E)
    if not GBNF_PATH.exists():
        print(f"[S371.3-STABILITY] Грамматика не найдена: {GBNF_PATH}")
        return 1
    gbnf_recursive = GBNF_PATH.read_text(encoding="utf-8")

    results: List[TestResult] = []

    # A: /v1/chat/completions без GBNF (контроль)
    r = run_test("A", "Chat completions без GBNF (контроль)", "chat", False, SIMPLE_PROMPT, max_tokens=50)
    results.append(r)
    if not r.server_alive_post:
        print("\n[A] СЕРВЕР УПАЛ — STOP (мандат §3)")
        _save_artifact(results)
        return 1

    time.sleep(5)

    # B: /completion с минимальной грамматикой
    r = run_test("B", "/completion минимальная грамматика (fixed {\"x\": N})", "completion", True,
                 SIMPLE_PROMPT, grammar=GBNF_MINIMAL, max_tokens=50)
    results.append(r)
    if not r.server_alive_post:
        print("\n[B] СЕРВЕР УПАЛ — STOP (мандат §3)")
        _save_artifact(results)
        return 1

    time.sleep(5)

    # C: /completion с рекурсивной грамматикой
    r = run_test("C", "/completion рекурсивная грамматика (config/chronicle_decompose.gbnf)", "completion", True,
                 CHRONICLE_PROMPT, grammar=gbnf_recursive, max_tokens=2048)
    results.append(r)
    if not r.server_alive_post:
        print("\n[C] СЕРВЕР УПАЛ — STOP (мандат §3)")
        _save_artifact(results)
        return 1

    time.sleep(5)

    # D: /completion с грамматикой ограниченной глубины
    r = run_test("D", "/completion грамматика ограниченной глубины (scalar payload only)", "completion", True,
                 CHRONICLE_PROMPT, grammar=GBNF_DEPTH_LIMITED, max_tokens=2048)
    results.append(r)
    if not r.server_alive_post:
        print("\n[D] СЕРВЕР УПАЛ — STOP (мандат §3)")
        _save_artifact(results)
        return 1

    time.sleep(5)

    # E: повторный запрос с грамматикой C (накопительная деградация)
    r = run_test("E", "/completion повторный запрос с грамматикой C (prompt cache, накопительная деградация)", "completion", True,
                 CHRONICLE_PROMPT, grammar=gbnf_recursive, max_tokens=2048)
    results.append(r)

    _save_artifact(results)
    print("\n[S371.3-STABILITY] Матрица завершена.")
    return 0


def _save_artifact(results: List[TestResult]) -> None:
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    artifact_path = _ROOT / "reports" / f"s371_3_stability_matrix_{timestamp}.json"
    artifact = {
        "timestamp": timestamp,
        "tests": [asdict(r) for r in results],
        "summary": {
            "tests_completed": len(results),
            "server_alive_at_end": results[-1].server_alive_post if results else False,
        },
    }
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[S371.3-STABILITY] Артефакт: {artifact_path}")


if __name__ == "__main__":
    sys.exit(main())