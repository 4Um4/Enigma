"""path: /project/reports/p0_model_determinism.py

Назначение: STAGE 1 Candidate Validation: детерминизм кандидата и
    baseline-контроля на одном приборе. Фазы: W (warm A/A, 10 повторов
    фразы), I (interleave: P1 повторяется среди чужих входов — детект
    state/slot-загрязнения гибридной SSM), C (cold: рестарт сервера).
    Раздельно: byte-determinism (сырой content) и semantic-determinism
    (production-JSON: полный dict + acts-отпечаток action|speech_act|acts)
    — по определению Мастера, оба фиксируются. Seeds = production-контракт
    (KernelRNG tick=0 npc_id=intent_compressor salt=user_prompt); промпт =
    golden A + production-форма user. Кандидат стартует с
    --chat-template-kwargs enable_thinking=false (изолированная
    compatibility-правка STAGE 0b; think-тег-остаток в content —
    задокументирован, production-регекс справляется).
Зависимости: stdlib; app.services.npc.kernel_rng (read-only); golden A.
Запуск: python reports/p0_model_determinism.py --model candidate|baseline
"""

import json
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.services.npc.kernel_rng import KernelRNG

_ROOT = Path(__file__).resolve().parents[1]
_EXE = _ROOT / "Models LLM" / "llama" / "llama-server.exe"
_GOLDEN_A = _ROOT / "backend" / "tests" / "micro" / "golden_production_system_prompt_A.txt"
_MODELS = {
    "candidate": (
        _ROOT / "Models LLM" / "Qwen3.5-9B-The-Defiant-Fable-Uncnr-Heretic-NEO-MAX-IQ3_M.gguf",
        True,
    ),
    "baseline": (
        _ROOT / "Models LLM" / "Qwen2.5-7B-Instruct-abliterated-v2.Q4_K_M.gguf",
        False,
    ),
}
_THINKING_OFF = ["--chat-template-kwargs", "{\"enable_thinking\": false}"]
_PORT = 8181
_BASE = f"http://localhost:{_PORT}"

_PHRASES = (
    "Кто тебе сказал, что я Мю?",  # PROV+
    "Кто ты?",                      # ID+
    "Что у вас можно купить?",      # question
    "Пнуть под зад",                # action
)
_WARM_N = 10
_INTERLEAVE = (0, 1, 0, 2, 0, 3, 0, 1, 0)  # P1 пять раз среди чужих


def _http_get(path: str, timeout: float) -> str:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(urllib.request.Request(path), timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def _call(user_prompt: str, system: str) -> str:
    seed = KernelRNG(tick=0, npc_id="intent_compressor", salt=user_prompt).randint(
        0, 2**31 - 1
    )
    payload = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.0,
        "seed": seed,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        f"{_BASE}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=120.0) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return str(data["choices"][0]["message"].get("content") or "")


def _user_prompt(phrase: str) -> str:
    return f"Ввод: \"{phrase}\"\nДоступные персонажи (id — имя):\nнет"


def _parse(content: str) -> Optional[dict]:
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _fingerprint(parsed: Optional[dict]) -> str:
    if parsed is None:
        return "<parse-fail>"
    acts = parsed.get("semantic_acts") or []
    types = ";".join(
        str(a.get("type", "")) for a in acts if isinstance(a, dict)
    )
    return f"{parsed.get('action')}|{parsed.get('speech_act')}|{types}"


def _uniq(samples: List[str]):
    byte_uniq = len(set(samples))
    parseds = [_parse(s) for s in samples]
    json_uniq = len(
        {json.dumps(d, sort_keys=True, ensure_ascii=False) if d is not None else None
         for d in parseds}
    )
    fp_uniq = len({_fingerprint(d) for d in parseds})
    return byte_uniq, json_uniq, fp_uniq


class _Server:
    def __init__(self, model: Path, thinking_off: bool, log_path: Path):
        self._model = model
        self._thinking_off = thinking_off
        self._log_path = log_path
        self._proc: Optional[subprocess.Popen] = None
        self._handle = None

    def __enter__(self):
        self._handle = self._log_path.open("w", encoding="utf-8", errors="replace")
        args = ["-m", str(self._model), "--port", str(_PORT), "--host", "localhost",
                "-ngl", "99", "-c", "8192", "-t", "8"]
        if self._thinking_off:
            args += _THINKING_OFF
        self._proc = subprocess.Popen([str(_EXE)] + args, stdout=self._handle,
                                      stderr=subprocess.STDOUT)
        t0 = time.perf_counter()
        for _ in range(30):
            time.sleep(4.0)
            if self._proc.poll() is not None:
                raise SystemExit(f"СЕРВЕР УПАЛ НА СТАРТЕ — лог: {self._log_path}")
            try:
                if json.loads(_http_get(f"{_BASE}/health", 5)).get("status") == "ok":
                    print(f"  [srv] load {time.perf_counter() - t0:.1f}s pid={self._proc.pid}")
                    return self
            except Exception:
                pass
        raise SystemExit(f"СЕРВЕР НЕ СТАЛ HEALTHY — лог: {self._log_path}")

    def __exit__(self, *exc):
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        if self._handle:
            self._handle.close()
        time.sleep(2.0)
        sock = socket.socket()
        try:
            sock.settimeout(1.0)
            sock.connect(("localhost", _PORT))
            print("  [srv] ВНИМАНИЕ: listener жив — ORPHAN")
        except (ConnectionRefusedError, socket.timeout, OSError):
            print("  [srv] cleanup ok (listener закрыт)")
        finally:
            sock.close()
        return False


def main() -> None:
    mode = "candidate"
    if "--model" in sys.argv:
        mode = sys.argv[sys.argv.index("--model") + 1]
    if mode not in _MODELS:
        raise SystemExit("--model candidate|baseline")
    model_path, thinking_off = _MODELS[mode]
    log_path = Path(__file__).resolve().parent / f"p0_model_det_{mode}.log"
    system_prompt = _GOLDEN_A.read_text(encoding="utf-8")
    print(f"=== STAGE 1: DETERMINISM [{mode}] (W x{_WARM_N}, I=interleave, C=cold) ===")

    warm: Dict[str, List[str]] = {}
    inter: Dict[str, List[str]] = {p: [] for p in _PHRASES}
    cold: Dict[str, str] = {}

    with _Server(model_path, thinking_off, log_path):
        _call(_user_prompt("привет"), system_prompt)  # warm-up
        t0 = time.perf_counter()
        for p in _PHRASES:
            warm[p] = [_call(_user_prompt(p), system_prompt) for _ in range(_WARM_N)]
        for idx in _INTERLEAVE:
            p = _PHRASES[idx]
            inter[p].append(_call(_user_prompt(p), system_prompt))
        print(f"  W+I: {(_WARM_N + 1) * len(_PHRASES) + len(_INTERLEAVE) - 4} вызовов "
              f"за {time.perf_counter() - t0:.0f}s")

    with _Server(model_path, thinking_off, log_path):
        _call(_user_prompt("привет"), system_prompt)
        for p in _PHRASES:
            cold[p] = _call(_user_prompt(p), system_prompt)
        print("  C: cold-restart выполнен (те же фразы)")

    print("--- РЕЗУЛЬТАТЫ (uniq-счёт: 1 = полный детерминизм) ---")
    w_byte = w_json = w_fp = 0
    for p in _PHRASES:
        b, j, f = _uniq(warm[p])
        w_byte += b == 1
        w_json += j == 1
        w_fp += f == 1
        print(f"W {p!r}: bytes={b} json={j} acts={f}")
        if b > 1:
            print(f"    DIFF-A: {warm[p][0][:130]!r}")
            print(f"    DIFF-B: {warm[p][-1][:130]!r}")

    p1 = _PHRASES[0]
    b, j, f = _uniq(inter[p1])
    print(f"I {p1!r} (x{len(inter[p1])} среди чужих): bytes={b} json={j} acts={f}")
    cross = inter[p1][0] == warm[p1][0]
    print(f"I-vs-W (первый warm): {'IDENTICAL' if cross else 'DIFFERS'}")
    if b > 1:
        print(f"    DIFF-A: {inter[p1][0][:130]!r}")
        print(f"    DIFF-B: {inter[p1][-1][:130]!r}")

    c_byte = c_json = c_fp = 0
    for p in _PHRASES:
        b, j, f = _uniq([cold[p], warm[p][0]])
        c_byte += b == 1
        c_json += j == 1
        c_fp += f == 1
        print(f"C {p!r}: bytes={b} json={j} acts={f}")
        if b > 1:
            print(f"    WARM: {warm[p][0][:130]!r}")
            print(f"    COLD: {cold[p][:130]!r}")

    print(
        f"ИТОГО STAGE 1 [{mode}]: W bytes={w_byte}/4 json={w_json}/4 acts={w_fp}/4 | "
        f"I bytes={'OK' if b == 1 and len(set(inter[p1])) == 1 else 'CHECK'} | "
        f"C bytes={c_byte}/4 json={c_json}/4 acts={c_fp}/4"
    )


if __name__ == "__main__":
    main()
