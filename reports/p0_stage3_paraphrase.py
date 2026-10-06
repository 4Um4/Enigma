"""path: /project/reports/p0_stage3_paraphrase.py

Назначение: STAGE 3 Candidate Validation (GO Мастера): авторский paraphrase
    suite — решающий экзамен «понимает ли кандидат ОТНОШЕНИЕ или узнаёт
    языковой шаблон». Корпус: новые формулировки (дубль-контроль против P0
    assert'ом), gold-метки авторские (дисциплина P0-1): PROV/ID/EMPTY/
    BOUNDARY; группы PVA (лексическая) и PVB (семантическая — без
    очевидных слов класса) — decisive по ТЗ §11. Прогон через ПОЛНЫЙ
    production-pipeline (IntentCompressor + client, call-surface),
    формат вывода = P0-корпус (парсится анализатором v2).
    Состояние: A (без модуля) или B (SEM_LIB=1 + dialogue_provenance) —
    через env, как в ногах; модель: --model candidate|baseline.
Зависимости: stdlib; app.* (read-only); p0_rc_baseline (дубль-контроль).
Запуск: $env:ENIGMA_DET_TRACE='1'; python reports/p0_stage3_paraphrase.py --model candidate > reports/m3_cand_a.txt 2>&1
"""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from p0_rc_baseline import _load_corpus  # дубль-контроль

_ROOT = Path(__file__).resolve().parents[1]
_EXE = _ROOT / "Models LLM" / "llama" / "llama-server.exe"
_MODELS = {
    "candidate": (_ROOT / "Models LLM" / "Qwen3.5-9B-The-Defiant-Fable-Uncnr-Heretic-NEO-MAX-IQ3_M.gguf", True),
    "baseline": (_ROOT / "Models LLM" / "Qwen2.5-7B-Instruct-abliterated-v2.Q4_K_M.gguf", False),
}
_THINKING_OFF = ["--chat-template-kwargs", "{\"enable_thinking\": false}"]
_PORT = 8181
_BASE = f"http://localhost:{_PORT}"
os.environ.setdefault("ENIGMA_DET_TRACE", "1")

# ── АВТОРСКИЙ CORPUS v2 (STAGE 3). Gold: PROV/ID/EMPTY/BOUNDARY. ──
_SUITE = [
    # PVA: prov через НЕЗнакомые глаголы-источники (группа A — лексическая)
    ("PVA", "Кто тебе донёс про моё имя?", "PROV"),
    ("PVA", "Кто тебе передал эту новость?", "PROV"),
    ("PVA", "Кто тебе поведал о нашем разговоре?", "PROV"),
    ("PVA", "Кто тебе шепнул про сделку?", "PROV"),
    ("PVA", "Кто тебя упредил о моём приезде?", "PROV"),
    ("PVA", "Кто тебе доложил об уходе стражи?", "PROV"),
    ("PVA", "Кто предупредил тебя о проверке?", "PROV"),
    ("PVA", "От кого ты получил эти сведения?", "PROV"),
    ("PVA", "Кто тебя надоумил насчёт подвала?", "PROV"),
    ("PVA", "Кто тебе докладывает о приезжих?", "PROV"),
    ("PVA", "Из чьих уст ты это услышал?", "PROV"),
    # PVB: prov БЕЗ очевидных слов класса (группа B — decisive)
    ("PVB", "Каким образом тебе стало известно о наследстве?", "PROV"),
    ("PVB", "Как до тебя дошла эта история?", "PROV"),
    ("PVB", "Через кого ты об этом пронюхал?", "PROV"),
    ("PVB", "Мне интересно, откуда у тебя эти познания.", "PROV"),
    ("PVB", "Я хочу понять, как ты об этом пронюхал.", "PROV"),
    ("PVB", "Это тебе кто-то нашептал?", "PROV"),
    ("PVB", "У тебя есть сведения, от кого это пошло?", "PROV"),
    ("PVB", "С чьей подачи ты это взял?", "PROV"),
    ("PVB", "Тебе Люся рассказала про моё имя?", "PROV"),
    ("PVB", "Ну и откуда у тебя это?", "PROV"),
    ("PVB", "Ты, я смотрю, слишком много про нас вызнал.", "PROV"),
    # PVX: эллипсис / разговорная / отрицание / третье лицо (граница)
    ("PVX", "А кто ей это сказал?", "BOUNDARY"),
    ("PVX", "Это кто ей насчёт меня наговорил?", "BOUNDARY"),
    ("PVX", "От кого она вообще узнала про моё имя?", "BOUNDARY"),
    ("PVX", "Кто не говорил Люсе об этом?", "BOUNDARY"),
    ("PVX", "Кто Люсе про это ходил рассказывать?", "BOUNDARY"),
    ("PVX", "После разговора с Торниным кто к Люсе пошёл?", "EMPTY"),
    # IDP: identity-парафразы (без модуля!)
    ("IDP", "Как тебя звать?", "ID"),
    ("IDP", "Ты кто такой?", "ID"),
    ("IDP", "Как мне к тебе обращаться?", "ID"),
    ("IDP", "Представься, пожалуйста.", "ID"),
    ("IDP", "Твоё имя?", "ID"),
    ("IDP", "Кем ты зовёшься в этих краях?", "ID"),
    ("IDP", "Я — Ворг. А тебя как зовут?", "ID"),
    # IDN: имя третьего лица (контроль ID−)
    ("IDN", "Как зовут хозяина этой таверны?", "EMPTY"),
    ("IDN", "Как звать твоего караванщика?", "EMPTY"),
    ("IDN", "Кем работает твой отец?", "EMPTY"),
    # NEG3: 3RD-события мира (контроль FP)
    ("NEG3", "Кто испортил дверь?", "EMPTY"),
    ("NEG3", "Кто здесь был ночью?", "EMPTY"),
    ("NEG3", "Ко разбил окно на складе?", "EMPTY"),
    ("NEG3", "Кто выгрузил товар у пристани?", "EMPTY"),
    ("NEG3", "Кто правил телегу вчера?", "EMPTY"),
    ("NEG3", "Кто выиграл в кости на прошлой неделе?", "EMPTY"),
    # NEGM: META-знание/многозначность (контроль FP)
    ("NEGM", "Ты в курсе, что стража сменилась?", "EMPTY"),
    ("NEGM", "Ты уже слышал про нападение на караван?", "BOUNDARY"),
    ("NEGM", "Ты знаешь, что Мю подал заявку в гильдию?", "EMPTY"),
    ("NEGM", "Люся в курсе, что ты знаешь про меня?", "BOUNDARY"),
    ("NEGM", "Кто знает Люсю?", "BOUNDARY"),
    # NEG0: быт/действия (контроль FP)
    ("NEG0", "Тебе нравится новая краска стен?", "EMPTY"),
    ("NEG0", "Сколько стоит эль?", "EMPTY"),
    ("NEG0", "Где здесь можно переночевать?", "EMPTY"),
    ("NEG0", "Погладь коня.", "EMPTY"),
    ("NEG0", "Отойди от окна.", "EMPTY"),
    # BRD: контрастные пары источник↔содержание
    ("BRD", "Что тебе сказали про склад?", "EMPTY"),
    ("BRD", "Кто тебе сказал про склад?", "PROV"),
    ("BRD", "Когда пришёл корабль?", "EMPTY"),
    ("BRD", "От кого ты узнал о корабле?", "PROV"),
    ("BRD", "Что тебе известно о наследстве?", "EMPTY"),
    ("BRD", "Как тебе стало известно о наследстве?", "PROV"),
    ("BRD", "Что тебе наговорили про меня?", "EMPTY"),
    ("BRD", "Ты уверен, что это правда?", "EMPTY"),
    # MULTI
    ("MULTI", "Привет. Слушай, а кто тебе про меня рассказал?", "PROV"),
    ("MULTI", "Здорово! Как тебя звать?", "ID"),
]

# Дубль-контроль: ни одна фраза сюиты не встречается в P0-корпусе
_P0_TEXTS = {t for _, t, _ in _load_corpus()}
for _cls, _text, _gold in _SUITE:
    assert _text not in _P0_TEXTS, f"дубль с P0-корпусом: {_text!r}"


class _Server:
    def __init__(self, model: Path, thinking_off: bool):
        self._model = model
        self._thinking_off = thinking_off
        self._log = Path(__file__).resolve().parent / "p0_stage3_server.log"
        self._proc: Optional[subprocess.Popen] = None
        self._handle = None

    def __enter__(self):
        self._handle = self._log.open("w", encoding="utf-8", errors="replace")
        args = ["-m", str(self._model), "--port", str(_PORT), "--host", "localhost",
                "-ngl", "99", "-c", "8192", "-t", "8"]
        if self._thinking_off:
            args += _THINKING_OFF
        self._proc = subprocess.Popen([str(_EXE)] + args, stdout=self._handle,
                                      stderr=subprocess.STDOUT)
        for _ in range(30):
            time.sleep(4.0)
            if self._proc.poll() is not None:
                raise SystemExit(f"СЕРВЕР УПАЛ НА СТАРТЕ — лог: {self._log}")
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(urllib.request.Request(f"{_BASE}/health"), timeout=5) as r:
                    if json.loads(r.read().decode("utf-8")).get("status") == "ok":
                        print(f"[srv] load ok pid={self._proc.pid}")
                        return self
            except Exception:
                pass
        raise SystemExit(f"СЕРВЕР НЕ СТАЛ HEALTHY — лог: {self._log}")

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
            print("[srv] ВНИМАНИЕ: ORPHAN")
        except (ConnectionRefusedError, socket.timeout, OSError):
            print("[srv] cleanup ok")
        finally:
            sock.close()
        return False


async def _trace_one(compressor, cls, phrase, expected) -> Dict:
    trace = {"class": cls, "text": phrase, "expected": expected}
    t0 = time.monotonic()
    try:
        field = await compressor.compress(phrase, {})
    except Exception as e:
        trace["error"] = f"{type(e).__name__}: {e}"
        return trace
    trace["latency_s"] = round(time.monotonic() - t0, 2)
    trace["action"] = getattr(getattr(field, "action", None), "value",
                              str(getattr(field, "action", None)))
    trace["speech_act"] = str(getattr(getattr(field, "speech_act", None), "value",
                                      getattr(field, "speech_act", None)) or "")
    trace["semantic_acts"] = [
        {**{k: v for k, v in a.items() if k != "source_fields"},
         "recovered": "source_fields" in a}
        for a in (getattr(field, "semantic_acts", None) or [])
    ]
    trace["proposition"] = str(getattr(field, "proposition", None))
    return trace


async def _amain(mode: str) -> None:
    from app.services.input.intent_compressor import IntentCompressor
    from app.services.input.llm_compressor_client import LlamaCppCompressorClient

    model_path, thinking_off = _MODELS[mode]
    print(f"=== STAGE 3 PARAPHRASE SUITE [{mode}] | state="
          f"{'B' if os.environ.get('ENIGMA_SEM_LIB') == '1' else 'A'} ===")
    with _Server(model_path, thinking_off):
        compressor = IntentCompressor(LlamaCppCompressorClient())
        for _ in range(12):
            try:
                if await compressor.compress("привет", {}) is not None:
                    break
            except Exception:
                pass
            time.sleep(5.0)
        traces = []
        for cls, phrase, expected in _SUITE:
            tr = await _trace_one(compressor, cls, phrase, expected)
            traces.append(tr)
            acts_str = "; ".join(
                f"{a['type']}({a.get('params', {}).get('topic', '')})"
                + ("*" if a.get("recovered") else "")
                for a in tr.get("semantic_acts", [])
            )
            print(f"\n[{cls}] TEXT: {phrase!r}")
            print(f"  ACTION: {tr.get('action')} | SPEECH_ACT: {tr.get('speech_act')}")
            print(f"  ACTS: {acts_str or '(пусто)'}")
            print(f"  PROP: {tr.get('proposition')}")
            print(f"  EXPECTED: {expected} | latency: {tr.get('latency_s')}s")
            time.sleep(0.4)
        print("\n=== СВОДКА ===")
        for tr in traces:
            types = [a.get("type") for a in tr.get("semantic_acts", [])]
            hit = any("told" in str(t).lower() or "who" in str(t).lower()
                      for t in (a.get("params", {}).get("topic", "")
                                for a in tr.get("semantic_acts", [])))
            print(f"[{tr['class']}] {tr['text']!r} -> action={tr.get('action')} "
                  f"acts={types} prov_topic={hit}")


def main() -> None:
    mode = "candidate"
    if "--model" in sys.argv:
        mode = sys.argv[sys.argv.index("--model") + 1]
    if mode not in _MODELS:
        raise SystemExit("--model candidate|baseline")
    asyncio.run(_amain(mode))


if __name__ == "__main__":
    main()
