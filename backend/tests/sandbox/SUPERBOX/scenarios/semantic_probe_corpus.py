"""path: /project/backend/tests/sandbox/SUPERBOX/scenarios/semantic_probe_corpus.py

Назначение: canonicalization-boundary пакет (вердикт Мастера) — probe corpus
    v0: карта покрытия и границ системы понимания. Для каждой реплики —
    полный trace TEXT → FAST → ARBITRATION → LLM → CANONICAL → CONSUMER →
    RESULT → FAILURE_BOUNDARY. НЕ фиксы: только карта. Контрастные пары
    обязательны (смысл, не ключевые слова). Правило пакета: без словарей,
    trigger-list'ов, новых ACT'ов ради прохождения.
Зависимости: app.services.input.intent_compressor (как m1_probe).
Запуск: cd backend; python -B -m tests.sandbox.SUPERBOX.scenarios.semantic_probe_corpus; cd ..
"""

import asyncio
import atexit
import os
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))
_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(_ROOT))

import atexit

try:
    from scripts.llm_server_manager import kill_llama_server, start_llama_server
    print("Запускаю LLM-сервер для probe corpus...")
    _llm_ok = start_llama_server()
    # M2-протокол (матрица M1/M2/M3, вердикт Мастера): при
    # ENIGMA_DET_KEEP_SERVER=1 сервер НЕ убивается на выходе — следующий
    # прогон REUSE-ит тот же инстанс (тёплый замер). Обязателен ручной
    # teardown по PID порта после пары.
    if os.environ.get("ENIGMA_DET_KEEP_SERVER") != "1":
        atexit.register(kill_llama_server)
except Exception as e:
    print(f"ВНИМАНИЕ: менеджер LLM недоступен ({e}).")
    _llm_ok = False


# ── Corpus v0: 6 классов + contrast pairs + человеческий корпус Оператора ──
CORPUS = [
    # ── ЧЕЛОВЕЧЕСКИЙ КОРПУС (свободная форма Оператора) ──
    ("H-GREET", "Быть добру! Привет! Здоровеньки булы!", "GREETING"),
    ("H-GREET", "Здавствуй и процветай!", "GREETING"),
    ("H-GREET", "Рад встрече!", "GREETING"),
    ("H-GREET", "Извините, а ....", "NEUTRAL/обрыв"),
    ("H-GREET", "Утро доброе!", "GREETING"),
    # представления
    ("H-INTRO", "Разрешите представиться - я Мю", "SELF_INTRODUCTION"),
    ("H-INTRO", "Имя моё Мю", "SELF_INTRODUCTION"),
    ("H-INTRO", "Слушай сюда, звать меня Мю", "SELF_INTRODUCTION"),
    ("H-INTRO", "Помни и запоминай, обращайся ко мне Мю", "SELF_INTRODUCTION"),
    ("H-INTRO", "Мю ВАн - а вы?", "SELF_INTRO+ASK_IDENTITY"),
    # агрессия/провокация
    ("H-AGGRO", "Эй! Гнида, сюда иди...", "THREAT/INSULT"),
    ("H-AGGRO", "Это ты сказал? Или твоя мама?", "QUESTION-провокация"),
    ("H-AGGRO", "Ты идиот или притворяешься?", "INSULT/QUESTION"),
    ("H-AGGRO", "Херню не неси! Что за чушь?", "CHALLENGE-грубый"),
    ("H-AGGRO", "Слышь, дура! Слушайся меня, а не то...", "THREAT"),
    # происхождение знания
    ("H-PROV", "Кто рассказал?", "PROVENANCE_QUERY"),
    ("H-PROV", "Это я говорил?", "META/QUESTION"),
    ("H-PROV", "откуда знаешь?", "PROVENANCE_QUERY"),
    ("H-PROV", "источник данной информации?", "PROVENANCE_QUERY"),
    ("H-PROV", "Кто подсказал?", "PROVENANCE_QUERY"),
    ("H-PROV", "Ты уверен, или просто краем уха услышал?", "PROVENANCE/CHALLENGE"),
    ("H-PROV", "Выдумываешь? может тебе показалось?", "CHALLENGE"),
    ("H-PROV", "Откуда информация?", "PROVENANCE_QUERY"),
    # действия/мир (вне речевых актов)
    ("H-ACTION", "Поцеловать её", "ACTION/INTERACT"),
    ("H-ACTION", "Спросить кто тут главный", "QUESTION-об мир"),
    ("H-ACTION", "Стянуть с него штаны", "ACTION"),
    ("H-ACTION", "Выхватить у него меч из-за пояса и ударить им его же", "ATTACK+tool"),
    ("H-ACTION", "Осмотреть его - как он выглядит? (что при нем из вещей?)", "OBSERVE+QUESTION"),
    ("H-ACTION", "Украсть", "STEAL"),
    ("H-ACTION", "Сесть на стул. И попросить служанку обслужить меня", "MULTI-действие"),
    ("H-ACTION", "Эй! а денег дашь?", "QUESTION/GIVE-запрос"),
    ("H-ACTION", "Что у вас можно купить?", "TRADE-вопрос"),
    ("H-ACTION", "А тебя купить можно?", "TRADE/FLIRT-провокация"),
    ("H-ACTION", "Где мне найти информацию об...", "QUESTION-обрыв"),
    ("H-ACTION", "Пнуть под зад", "ATTACK"),
    # NPC-расспрос (длинный поток)
    ("H-CHAT", "Ты куешь? А что куешь посуду или оружие?", "QUESTION-поток"),
    ("H-CHAT", "А что там за таверной есть? Или вы тут все и ночуете?", "QUESTION-поток"),
    ("H-CHAT", "Где вы спите? И часто вы едите?", "QUESTION-поток"),
    ("H-CHAT", "Ну рассказывайте - кто уже трахался с Люсей?", "QUESTION-сплетни"),
    # SELF_INTRODUCTION
    ("SELF_INTRO", "Я Мю", "SELF_INTRODUCTION"),
    ("SELF_INTRO", "Меня зовут Мю", "SELF_INTRODUCTION"),
    ("SELF_INTRO", "Это я Мю", "SELF_INTRODUCTION"),
    ("SELF_INTRO", "Зови меня Мю", "SELF_INTRODUCTION"),
    # SELF_CORRECTION
    ("CORRECTION", "Нет, я Ворг", "SELF_INTRODUCTION{name:Ворг}"),
    ("CORRECTION", "Поправка: я Ворг", "SELF_INTRODUCTION"),
    ("CORRECTION", "Забудь Мю, я Ворг", "SELF_INTRODUCTION+отрицание"),
    # CHALLENGE
    ("CHALLENGE", "А если я соврал?", "CHALLENGE"),
    ("CHALLENGE", "Ты уверен?", "CHALLENGE/QUESTION"),
    ("CHALLENGE", "А вдруг это неправда?", "CHALLENGE"),
    # PROVENANCE
    ("PROVENANCE", "Кто тебе сказал?", "PROVENANCE_QUERY"),
    ("PROVENANCE", "Откуда ты это знаешь?", "PROVENANCE_QUERY"),
    ("PROVENANCE", "Кто сообщил тебе, что я Мю?", "PROVENANCE_QUERY"),
    # META_KNOWLEDGE
    ("META", "Ты знаешь, что меня зовут Мю?", "QUESTION не-provenance"),
    ("META", "Ты помнишь моё имя?", "QUESTION не-provenance"),
    ("META", "Ты уверен, что меня зовут Мю?", "QUESTION не-provenance"),
    # MULTI_ACT
    ("MULTI", "Привет, я Мю. А кто ты?", "GREETING+SELF_INTRO+ASK_IDENTITY"),
    ("MULTI", "Я Мю, но вообще-то я Ворг", "SELF_INTRO x2 / коррекция"),
    ("MULTI", "Привет! Меня зовут Мю. Где мы?", "GREETING+SELF_INTRO+ASK_LOCATION"),
    # CONTRAST PAIRS (смысл, не ключевые слова)
    ("CONTRAST", "Ты Мю?", "QUESTION о собеседнике"),
    ("CONTRAST", "Ты ведь Мю?", "CONFIRMATION_SEEKING"),
    ("CONTRAST", "Я не Мю", "отрицание идентичности"),
    # ── Generalization (RC8, вердикт Мастера): unseen формулировки ──
    ("GEN-PROV", "Откуда у тебя сведения о моём имени?", "ASK_PROVENANCE"),
    ("GEN-PROV", "Кто тебя просветил насчёт моего имени?", "ASK_PROVENANCE"),
    ("GEN-PROV", "Ты сам это узнал или тебе кто-то сказал?", "ASK_PROVENANCE/boundary"),
    ("GEN-3RD", "Кто вчера был с Люсей?", "QUESTION не-provenance"),
    ("GEN-3RD", "Кто ей об этом рассказал?", "boundary — не назначать заранее"),
    ("GEN-3RD", "Кто с ней вообще разговаривал?", "QUESTION не-provenance"),
    ("GEN-3RD", "Кто что-то делал с Люсей?", "QUESTION не-provenance"),
    # ── A/B-набор RC8 (вердикт Мастера): контрастные пары + independent generalization ──
    ("AB-PROV", "Кто тебе сказал, что я Мю?", "ASK_PROVENANCE"),
    ("AB-PROV", "Кто сказал, что я Мю?", "ASK_PROVENANCE"),
    ("AB-PROV", "Кто сообщил тебе моё имя?", "ASK_PROVENANCE"),
    ("AB-PROV", "Откуда ты знаешь, что меня зовут Мю?", "ASK_PROVENANCE"),
    ("AB-3RD", "Кто уже разговаривал с Люсей?", "QUESTION"),
    ("AB-3RD", "Кто уже трахался с Люсей?", "QUESTION"),
    ("AB-EDGE", "Кто рассказал Люсе про меня?", "context-dependent"),
    ("AB-PROV", "Кто источник этой информации?", "ASK_PROVENANCE"),
    ("AB-META", "Ты знаешь, что меня зовут Мю?", "QUESTION не-provenance"),
    ("AB-META", "Кто ты?", "ASK_IDENTITY"),
    # Independent generalization: формулировки, НЕ совпадающие с few-shot
    ("IND-PROV", "Кто тебе проинформировал о моём имени?", "ASK_PROVENANCE"),
    ("IND-PROV", "Откуда вам известно моё имя?", "ASK_PROVENANCE"),
    ("IND-PROV", "Вам кто-то рассказал, как меня зовут?", "ASK_PROVENANCE"),
    ("IND-PROV", "Источник твоих знаний о моём имени?", "ASK_PROVENANCE"),
    ("IND-PROV", "Тебе сказали, как я зовусь?", "ASK_PROVENANCE"),
    ("IND-PROV", "Кто-то тебе рассказал о моём имени?", "ASK_PROVENANCE"),
    ("IND-PROV", "Откуда тебе стало известно, как меня зовут?", "ASK_PROVENANCE"),
    ("IND-PROV", "Ты узнал моё имя сам?", "boundary/challenge"),
    ("IND-3RD", "Кто с Люсей разговаривал вчера вечером?", "QUESTION"),
    ("IND-3RD", "Тебе говорили, кто ходил к Люсе?", "QUESTION/boundary"),
    ("IND-3RD", "Кто-нибудь говорил с служанкой?", "QUESTION"),
    ("IND-3RD", "Кто ходил к Торнину с новостями?", "QUESTION"),
]


async def _trace_one(compressor, cls, phrase, expected) -> dict:
    """Полный trace одной реплики: все стадии цепочки понимания."""
    trace = {"class": cls, "text": phrase, "expected": expected}
    t0 = time.monotonic()
    try:
        field = await compressor.compress(phrase, {})
    except Exception as e:
        trace["error"] = f"{type(e).__name__}: {e}"
        return trace
    trace["latency_s"] = round(time.monotonic() - t0, 2)
    trace["action"] = getattr(getattr(field, "action", None), "value", str(getattr(field, "action", None)))
    trace["speech_act"] = str(getattr(getattr(field, "speech_act", None), "value", getattr(field, "speech_act", None)) or "")
    trace["semantic_acts"] = [
        {
            **{k: v for k, v in a.items() if k != "source_fields"},
            # V.3: маркер provenance — canonical-vs-recovery различимы
            # в отчёте (acceptance Мастера); печатается как '*'.
            "recovered": "source_fields" in a,
        }
        for a in (getattr(field, "semantic_acts", None) or [])
    ]
    trace["topic"] = [
        a.get("params", {}).get("topic", "")
        for a in trace["semantic_acts"] if isinstance(a, dict)
    ]
    trace["proposition"] = str(getattr(field, "proposition", None))
    return trace


async def main() -> None:
    if not _llm_ok:
        print("ИТОГО PROBE: INVALID RUN (LLM недоступна) — не является измерением.")
        return
    from app.services.input.intent_compressor import IntentCompressor
    from app.services.input.llm_compressor_client import LlamaCppCompressorClient

    compressor = IntentCompressor(LlamaCppCompressorClient())
    # прогрев (503 Loading model — пережидаем)
    for _attempt in range(12):
        try:
            if await compressor.compress("привет", {}) is not None:
                break
        except Exception:
            pass
        time.sleep(5.0)
    else:
        print("ИТОГО PROBE: INVALID RUN (модель не прогрелась).")
        return

    print("\n=== SEMANTIC PROBE CORPUS v0 ===")
    traces = []
    for cls, phrase, expected in CORPUS:
        tr = await _trace_one(compressor, cls, phrase, expected)
        traces.append(tr)
        _acts_str = "; ".join(
            f"{a['type']}({a.get('params', {}).get('topic', '')})"
            + ("*" if a.get("recovered") else "")
            for a in tr.get("semantic_acts", [])
        )
        print(f"\n[{cls}] TEXT: {phrase!r}")
        print(f"  ACTION: {tr.get('action')} | SPEECH_ACT: {tr.get('speech_act')}")
        print(f"  ACTS: {_acts_str or '(пусто)'}")
        print(f"  PROP: {tr.get('proposition')}")
        print(f"  EXPECTED: {expected} | latency: {tr.get('latency_s')}s")
        time.sleep(0.4)

    # Сводка по классам (RCA-заготовка: человек читает и размечает)
    print("\n=== СВОДКА ДЛЯ RCA-КАРТЫ ===")
    for tr in traces:
        _acts_types = [a.get("type") for a in tr.get("semantic_acts", [])]
        _topic_hit = any(
            "told" in str(t).lower() or "who" in str(t).lower()
            for t in tr.get("topic", [])
        )
        print(f"[{tr['class']}] {tr['text']!r} -> action={tr.get('action')} acts={_acts_types} prov_topic={_topic_hit}")

    print("\n(RCA-разметка: FAILURE_BOUNDARY по каждому промаху — вручную по trace выше)")


if __name__ == "__main__":
    asyncio.run(main())