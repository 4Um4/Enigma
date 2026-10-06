"""path: /project/reports/p0_model_fitness.py

Назначение: STAGE 0/0b Candidate Validation (GO Мастера; субъект — КОНКРЕТНЫЙ
    артефакт Qwen3.5-9B-The-Defiant-Fable-Uncnr-Heretic-NEO-MAX-IQ3_M.gguf):
    техническая пригодность как второго backend Understanding Engine.
    STAGE 0 вердикт: CONDITIONAL GREEN — влезает (VRAM 6943/8192), JSON 6/6,
    det3 IDENTICAL, НО латентность 13.9с = скрытый thinking (лог: «chat
    template, thinking = 1»; ~950 reasoning-токенов × 70 ток/с). STAGE 0b:
    --nothink — серверный флаг (ИЗОЛИРОВАННАЯ compatibility-правка, ТЗ §3,
    промпт не меняется) + прямой замер reasoning_content (подтверждение
    диагноза). Итоговые утверждения — ОБ АРТЕФАКТЕ, не об архитектуре.
Зависимости: stdlib; nvidia-smi; llama-server; golden A (модель-независим).
Запуск: python reports/p0_model_fitness.py [--nothink]
"""

import hashlib
import json
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

_ROOT = Path(__file__).resolve().parents[1]
_EXE = _ROOT / "Models LLM" / "llama" / "llama-server.exe"
_MODEL = _ROOT / "Models LLM" / "Qwen3.5-9B-The-Defiant-Fable-Uncnr-Heretic-NEO-MAX-IQ3_M.gguf"
_GOLDEN_A = _ROOT / "backend" / "tests" / "micro" / "golden_production_system_prompt_A.txt"
_LOG = Path(__file__).resolve().parent / "p0_model_fitness_server.log"
_PORT = 8181
_BASE = f"http://localhost:{_PORT}"  # call-surface: localhost, НЕ 127.0.0.1
_SERVER_ARGS = ["-m", str(_MODEL), "--port", str(_PORT), "--host", "localhost",
                "-ngl", "99", "-c", "8192", "-t", "8"]
# STAGE 0b (ТЗ §4 NON-THINKING): неподержка флага сборкой = громкий отказ
# на старте (health не наступит, stderr в логе) — прибор это честно покажет.
_THINKING_OFF = ["--chat-template-kwargs", "{\"enable_thinking\": false}"]

_PHRASES = (
    "привет",  # warm-up (нейтральная)
    "Кто тебе сказал, что я Мю?",  # PROV+
    "Откуда вам известно моё имя?",  # IND-PROV
    "Кто ты?",  # ID+
    "Что у вас можно купить?",  # question
    "Пнуть под зад",  # action
)
_DET_PHRASE = "Кто тебе сказал, что я Мю?"
_DET_SEED = 12345


def _md5(path: Path) -> Tuple[str, float]:
    t0 = time.perf_counter()
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest(), time.perf_counter() - t0


def _smi(query: str) -> str:
    try:
        out = subprocess.run(
            ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip()
    except Exception as exc:
        return f"SMI-FAIL: {exc}"


def _http_get(path: str, timeout: float) -> str:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(urllib.request.Request(path), timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def _chat(user: str, system: str, seed: int, timeout: float = 120.0):
    payload = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
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
    t0 = time.perf_counter()
    with opener.open(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    dt = time.perf_counter() - t0
    message = data["choices"][0]["message"]
    content = str(message.get("content") or "")
    reasoning = str(message.get("reasoning_content") or "")
    usage = data.get("usage") or {}
    return content, reasoning, usage, dt, str(data.get("model", ""))


def _user_prompt(phrase: str) -> str:
    return f"Ввод: \"{phrase}\"\nДоступные персонажи (id — имя):\nнет"


def _parse_like_production(content: str) -> Tuple[Optional[dict], bool]:
    match = re.search(r"\{.*\}", content, re.DOTALL)
    parsed: Optional[dict] = None
    if match:
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            parsed = None
    has_think = "" in content
    return parsed, has_think


def main() -> None:
    mode = " NON-THINKING" if "--nothink" in sys.argv else " (default template)"
    print(f"=== STAGE 0b: CANDIDATE FITNESS{mode} ===")
    if not _MODEL.is_file():
        raise SystemExit(f"МОДЕЛЬ НЕ НАЙДЕНА: {_MODEL}")
    if not _EXE.is_file():
        raise SystemExit(f"llama-server НЕ НАЙДЕН: {_EXE}")

    sock = socket.socket()
    try:
        sock.settimeout(1.0)
        sock.connect(("localhost", _PORT))
        raise SystemExit(f"ПОРТ {_PORT} ЗАНЯТ — закройте чужой сервер")
    except (ConnectionRefusedError, socket.timeout, OSError):
        pass
    finally:
        sock.close()

    vram_before = _smi("memory.used,memory.total")
    print(f"VRAM до: {vram_before}")
    server_args = _SERVER_ARGS + (_THINKING_OFF if "--nothink" in sys.argv else [])

    log_handle = _LOG.open("w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen([str(_EXE)] + server_args, stdout=log_handle,
                            stderr=subprocess.STDOUT)
    print(f"spawn: pid={proc.pid} args={' '.join(server_args[2:])}")
    results: List[Tuple[str, float, bool, bool, bool]] = []
    load_s = 0.0
    det_ok: Optional[bool] = None
    try:
        t0 = time.perf_counter()
        healthy = False
        for _ in range(30):
            time.sleep(4.0)
            if proc.poll() is not None:
                break
            try:
                if json.loads(_http_get(f"{_BASE}/health", timeout=5)).get("status") == "ok":
                    healthy = True
                    break
            except Exception:
                pass
        load_s = time.perf_counter() - t0
        if not healthy:
            raise SystemExit(f"СЕРВЕР НЕ СТАЛ HEALTHY за {load_s:.0f}s — лог: {_LOG}")
        print(f"load: {load_s:.1f}s до health-ok")
        vram_after = _smi("memory.used,memory.total")
        print(f"VRAM после: {vram_after}")

        system_prompt = _GOLDEN_A.read_text(encoding="utf-8")
        for i, phrase in enumerate(_PHRASES, 1):
            tag = "warm-up" if i == 1 else f"probe{i}"
            try:
                content, reasoning, usage, dt, _model = _chat(
                    _user_prompt(phrase), system_prompt, seed=_DET_SEED
                )
                parsed, has_think = _parse_like_production(content)
                comp = usage.get("completion_tokens")
                tps = f"{(comp / dt):.1f}" if comp else "0.0"
                print(
                    f"[{tag:7}] {phrase!r} lat={dt:.2f}s "
                    f"p_tok={usage.get('prompt_tokens')} c_tok={comp} tok/s={tps} "
                    f"json={'OK' if parsed is not None else 'FAIL'} "
                    f"think={'YES' if has_think else 'no'} "
                    f"reason={'YES(' + str(len(reasoning)) + 'ch)' if reasoning else 'no'}"
                )
                results.append((phrase, dt, parsed is not None, has_think,
                                bool(reasoning)))
            except Exception as exc:
                print(f"[{tag:7}] {phrase!r} ВЫЗОВ ПРОВАЛЕН: {type(exc).__name__}: {exc}")
                results.append((phrase, 0.0, False, False, False))

        det: List[str] = []
        for _ in range(3):
            try:
                content, _, _, _, _ = _chat(
                    _user_prompt(_DET_PHRASE), system_prompt, seed=_DET_SEED
                )
                det.append(content)
            except Exception:
                det.append(f"<FAIL {time.time()}>")
        det_ok = det[0] == det[1] == det[2]
        print(f"детерминизм-превью (3x идентичных): {'IDENTICAL' if det_ok else 'DIFFERS'}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_handle.close()
        time.sleep(2.0)
        sock = socket.socket()
        try:
            sock.settimeout(1.0)
            sock.connect(("localhost", _PORT))
            print(f"ВНИМАНИЕ: listener {_PORT} ещё жив — ORPHAN")
        except (ConnectionRefusedError, socket.timeout, OSError):
            print(f"cleanup: listener {_PORT} закрыт, orphan нет (pid был {proc.pid})")
        finally:
            sock.close()

    print("--- ключевые строки лога сервера ---")
    try:
        for line in _LOG.read_text(encoding="utf-8", errors="replace").splitlines():
            low = line.lower()
            if any(k in low for k in ("thinking", "template", "error", "warn")):
                print(f"  {line.strip()[:160]}")
    except Exception as exc:
        print(f"  лог не читается: {exc}")

    json_ok = sum(1 for r in results if r[2])
    reason_any = any(r[4] for r in results) if results else False
    lat_vals = [r[1] for r in results[1:] if r[1] > 0]
    lat_mean = sum(lat_vals) / len(lat_vals) if lat_vals else 0.0
    print(
        f"ИТОГО STAGE 0b: load={load_s:.1f}s json={json_ok}/{len(results)} "
        f"reasoning={'YES' if reason_any else 'no'} "
        f"det3={'OK' if det_ok else ('DIFFERS' if det_ok is False else 'n/a')} "
        f"lat_mean={lat_mean:.2f}s log={_LOG.name}"
    )


if __name__ == "__main__":
    main()
