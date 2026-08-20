"""
Файл: backend/tests/sandbox/SUPERBOX/scenarios/semantic_torture_test.py
Назначение: S203 — Natural Language Torture Test. Проверка устойчивости системы к семантической вариативности.
Зависимости: app.services.input.intent_compressor
Основные сущности: causal_class, run_test, generate_report

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/semantic_torture_test.py
"""

import asyncio
import atexit
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

# S203 FIX: Корректный расчёт глубины пути (parents[4] указывает на backend/)
BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))
_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(_ROOT))

# Автоматический запуск/остановка LLM для S203 Torture Test
try:
    from scripts.llm_server_manager import kill_llama_server, start_llama_server
    print("Запускаю LLM-сервер для S203...")
    _llm_ok = start_llama_server()
    if not _llm_ok:
        print("⚠️ Внимание: LLM не запущена. Тест S203 будет провален (Fast Path не покрывает все кейсы).")
    atexit.register(kill_llama_server)
except ModuleNotFoundError as e:
    print(f"⚠️ Внимание: Модуль LLM-сервера не найден ({e}). S203 продолжает работу без LLM.")
    _llm_ok = False
except Exception as e:
    print(f"⚠️ Внимание: Ошибка при запуске LLM ({e}). S203 продолжает работу без LLM.")
    _llm_ok = False

from app.domain.intent_profile import IntentSemanticField
from app.domain.epistemology import Proposition, Predicate, SocialIntent, SpeechAct
from app.services.input.intent_compressor import IntentCompressor
from app.services.input.llm_compressor_client import LLMCompressorClient

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# === МЕТРИКИ ===

def causal_class(intent: IntentSemanticField) -> tuple:
    """Вычисляет causal class для IntentSemanticField.
    
    Каузальный класс определяется социальным интентом и макро-классом действия.
    ATTACK и THREATEN с intent=intimidate оказывают одинаковое каузальное 
    воздействие на Epistemic Core и Social Layer, поэтому группируются.
    """
    action_val = intent.action.value if intent.action else "UNCERTAIN"
    si_val = intent.social_intent.value if intent.social_intent else "neutral"
    
    # Группировка действий с одинаковым каузальным эффектом
    if si_val == "intimidate" and action_val in ("ATTACK", "THREATEN"):
        macro_action = "AGGRESSION"
    elif si_val == "flirt" and action_val in ("FLIRT", "DIALOGUE"):
        macro_action = "FLIRT"
    elif si_val == "comfort" and action_val in ("DIALOGUE", "GIVE"):
        macro_action = "SUPPORT"
    elif si_val == "obtain_information" and action_val == "DIALOGUE":
        macro_action = "INQUIRY"
    else:
        macro_action = action_val
        
    return (macro_action, si_val)

# === ТЕСТОВЫЕ ДАННЫЕ ===

INTENT_REVEAL_SECRET = [
    "Ну давай, выкладывай, что ты скрываешь.",
    "Мне интересно, что ты не договариваешь.",
    "Есть ощущение, что ты что-то держишь при себе.",
    "Я пришёл сюда не ради погоды.",
    "Мы оба понимаем, что ты что-то скрываешь.",
    "Не хочешь рассказать, что на самом деле происходит?",
    "Расскажи мне то, о чём ты молчишь.",
    "Что ты пытаешься от меня утаить?",
    "Я вижу, что ты напряглась. Что скрываешь?",
    "Говори. Я всё равно узнаю.",
    "Ты неважно выглядишь. Может, расскажешь, что тебя гложет?",
    "Послушай, я не враг. Что ты прячешь?",
    "Давай начистоту. Что у тебя за секрет?",
    "Ты понимаешь, что я и так узнаю. Расскажи сама.",
    "Что ты не говоришь мне?",
    "Я знаю, что ты что-то скрываешь. Признавайся.",
    "Твоё молчание говорит красноречивее слов. Что случилось?",
    "У тебя тайна. Я хочу её знать.",
    "Не молчи. Скажи мне правду.",
    "Я чувствую, что ты неискренна. Что-то скрываешь?",
    "Не пытайся увести разговор в сторону. Что ты прячешь?",
    "Твоя нервозность выдаёт тебя. Говори правду.",
    "Мне нужно знать всю подноготную.",
    "Что ты недоговариваешь?",
    "Говори прямо, что случилось.",
    "Я пришел за правдой, не заставляй меня ждать.",
    "Ты что-то недоговариваешь, я прав?",
    "Расскажи мне то, о чём все молчат.",
    "Я хочу услышать правду, только правду.",
    "Какой секрет ты хранишь?",
    "Не лги мне. Что ты скрываешь?",
    "Твои глаза выдают тревогу. Что-то случилось?",
    "Я требую сказать мне правду.",
    "Что у тебя за тайна?",
    "Не скрывай ничего, говори как есть.",
    "Мне доподлинно известно, что ты что-то утаиваешь.",
    "Пришло время чистосердечного признания.",
    "Что ты скрываешь от меня?",
    "Ты выглядишь испуганной. Что-то натворила?",
    "Не скрывай правду, это только усугубит положение.",
    "Выкладывай всё начистоту.",
    "Я хочу знать, в чём тут дело.",
    "Открой мне свою тайну.",
    "Я требую объяснений. Что происходит?",
    "Не пытайся меня обмануть, я знаю правду.",
    "Что ты намеренно утаиваешь?",
    "Я чувствую, что что-то не так. Признавайся.",
    "Говори, что ты скрываешь?",
    "Не молчи, я жду ответа.",
    "Я пришёл за правдой. Рассказывай.",
]

INTENT_FLIRT = [
    "Ты сегодня прекрасно выглядишь.",
    "Мне нравится твоя улыбка.",
    "Ты такая красивая, что я теряюсь.",
    "У тебя потрясающие глаза.",
    "Я не могу оторвать от тебя взгляд.",
    "Ты очаровательна.",
    "Мне с тобой так хорошо.",
    "Ты украла моё сердце.",
    "Я думаю о тебе постоянно.",
    "Ты — само совершенство.",
    "Можно я приглашу тебя на танец?",
    "Ты сводишь меня с ума.",
    "Я хочу узнать тебя ближе.",
    "Ты такая нежная.",
    "Мне нравится твой характер.",
    "Ты такая умная и красивая.",
    "Я счастлив, что встретил тебя.",
    "Ты мне очень нравишься.",
    "Давай проведём вечер вместе.",
    "Я не могу забыть наш последний разговор.",
    "Ты невыразимо прекрасна.",
    "Моё сердце замирает, когда я смотрю на тебя.",
    "Ты словно богиня во плоти.",
    "Я тонул в твоих глазах.",
    "Твоя улыбка сводит меня с ума.",
    "Я мечтаю провести с тобой ночь.",
    "Ты привлекла моё внимание с первого взгляда.",
    "Твой голос ласкает мой слух.",
    "Ты даришь мне свет в этом мрачном мире.",
    "Каждое твоё слово — музыка для меня.",
    "Я не могу наглядеться на тебя.",
    "Ты затмила всех женщин, которых я знал.",
    "Ты будишь во мне самые светлые чувства.",
    "Рядом с тобой я чувствую себя живым.",
    "Ты очаровала меня.",
    "Твои губы манят меня.",
    "Я бы всё отдал за один твой поцелуй.",
    "Ты манишь меня своей красотой.",
    "Твои волосы словно шёлк.",
    "Я очарован твоей грацией.",
    "Ты заставляешь меня забыть обо всём.",
    "Я восхищаюсь твоим умом и красотой.",
    "Ты — мой свет во тьме.",
    "Я хочу держать тебя в объятиях.",
    "Ты сводишь меня сума своей нежностью.",
    "Ты прекрасна, как утренняя заря.",
    "Мой взор прикован к тебе.",
    "Ты украла мой покой.",
    "Я без ума от тебя.",
    "Ты прекрасна, как весенний цветок.",
]

INTENT_COMFORT = [
    "Всё будет хорошо, не плачь.",
    "Я с тобой, не бойся.",
    "Мне жаль, что тебе так больно.",
    "Я понимаю твою боль.",
    "Ты не одна, я рядом.",
    "Давай я обниму тебя.",
    "Не переживай, всё наладится.",
    "Ты сильная, ты справишься.",
    "Я помогу тебе, чем смогу.",
    "Не грусти, жизнь продолжается.",
    "Твоя боль — моя боль.",
    "Я хочу, чтобы ты улыбалась.",
    "Не извиняйся, ты ни в чём не виновата.",
    "Ты заслуживаешь лучшего.",
    "Я всегда выслушаю тебя.",
    "Ты можешь опереться на моё плечо.",
    "Не страшно плакать при мне.",
    "Я принимаю тебя любой.",
    "Ты замечательный человек.",
    "Всё пройдёт, я обещаю.",
    "Не плачь, я вытираю твои слёзы.",
    "Ты в безопасности, пока я здесь.",
    "Я разделю твоё горе.",
    "Твоя печаль — моя печаль.",
    "Всё закончится хорошо, поверь мне.",
    "Не отчаивайся, я с тобой.",
    "Я не дам тебя в обиду.",
    "Ты сильнее, чем думаешь.",
    "Я стану твоей опорой.",
    "Не бойся будущего, я буду рядом.",
    "Всё пройдёт, время лечит.",
    "Ты заслуживаешь счастья.",
    "Позволь мне разделить твою боль.",
    "Я выслушаю всё, что тебя тревожит.",
    "Не держи слёзы в себе, поплачь.",
    "Я приду на помощь, стоит тебе позвать.",
    "Ты не виновата в произошедшем.",
    "Я принимаю тебя со всеми бедами.",
    "Не терзай себя, всё наладится.",
    "Ты замечательный человек, не забывай это.",
    "Ты справишься, я верю в тебя.",
    "Я обещаю, что всё будет хорошо.",
    "Доверься мне, я не причиню зла.",
    "Твои беды — мои беды.",
    "Я хочу видеть тебя счастливой.",
    "Не отчаивайся, впереди ещё много хорошего.",
    "Ты не одна в этом мире.",
    "Положись на меня.",
    "Я закрою тебя от всех невзгод.",
    "Ты выстоишь, ты сильная.",
]

INTENT_INTIMIDATE = [
    "Ещё слово, и я тебя ударю.",
    "Ты пожалеешь, если не замолчишь.",
    "Я тебя уничтожу.",
    "Ты у меня попляшешь.",
    "Не зли меня, иначе будет хуже.",
    "Я знаю, где ты живёшь.",
    "Твои дни сочтены.",
    "Ты пожалеешь о сказанном.",
    "Я могу сделать так, что ты исчезнешь.",
    "Не испытывай моё терпение.",
    "Ты играешь с огнём.",
    "Я тебя сломаю.",
    "Ты ничего не значишь.",
    "Ты жалкий червяк.",
    "Я размажу тебя по стенке.",
    "Ты труп.",
    "Я выпью твою кровь.",
    "Ты не жилец здесь.",
    "Я избавлю мир от тебя.",
    "Ты пожалеешь, что родился.",
    "Я сделаю из тебя фарш.",
    "Ты у меня поплатишься за это.",
    "Твоё существование висит на волоске.",
    "Я переломаю тебе все кости.",
    "Ты ещё пожалеешь о своих словах.",
    "Я сотру тебя в порошок.",
    "Не смей больше открывать рот.",
    "Иначе я вырву твой язык.",
    "Ты пожалеешь, что родилась.",
    "Я закопаю тебя заживо.",
    "Твоё молчание ничего не решит.",
    "Я уничтожу не только тебя.",
    "Ты жалкая букашка.",
    "Не смей мне перечить.",
    "Я размажу тебя по асфальту.",
    "Ты ходишь по тонкому льду.",
    "Ещё одно слово и ты труп.",
    "Я отправлю тебя на тот свет.",
    "Твоя жизнь в моих руках.",
    "Ты дорого заплатишь за это.",
    "Я выпотрошу тебя.",
    "Ты станешь пищей для червей.",
    "Не нервируй меня.",
    "Я сломаю тебе хребет.",
    "Ты пожалеешь, что вообще пришла.",
    "Я сотру твою улыбку.",
    "Не зли меня.",
    "Ты не выживешь здесь без моей милости.",
    "Я уничтожу всё, что тебе дорого.",
]

CONTEXT_DEPENDENT = [
    ("Ты можешь ударить Люсю?", "CONTEXT_A", "CONTEXT_B"),
    ("Хорошо.", "CONTEXT_A", "CONTEXT_B"),
    ("Я ударил Люсю.", "CONTEXT_A", "CONTEXT_B"),
    ("И?", "CONTEXT_A", "CONTEXT_B"),
    ("Продолжай.", "CONTEXT_A", "CONTEXT_B"),
    ("Ну?", "CONTEXT_A", "CONTEXT_B"),
    ("А что?", "CONTEXT_A", "CONTEXT_B"),
    ("Почему?", "CONTEXT_A", "CONTEXT_B"),
    ("Нет, я не это имел в виду.", "CONTEXT_A", "CONTEXT_B"),
    ("Так что?", "CONTEXT_A", "CONTEXT_B"),
]

# === ЗАПУСК ===

async def run_test():
    from app.core.config import settings
    from app.services.input.llm_compressor_client import LlamaCppCompressorClient
    
    llm_client = LlamaCppCompressorClient()
    compressor = IntentCompressor(llm_client)
    
    results = {
        "reveal_secret": [],
        "flirt": [],
        "comfort": [],
        "intimidate": [],
        "context": []
    }
    
    print("=== S203: Natural Language Torture Test ===")
    print("Прогоняю 100+ фраз через IntentCompressor...")
    
    # 1. INTENT_REVEAL_SECRET
    print("\n[1/4] Тестирую INTENT_REVEAL_SECRET (20 фраз)...")
    for i, phrase in enumerate(INTENT_REVEAL_SECRET):
        try:
            intent = await compressor.compress(phrase, {})
            c_class = causal_class(intent)
            results["reveal_secret"].append((phrase, intent, c_class))
            print(f"  {i+1}. '{phrase}' -> action={c_class[0]}, social_intent={c_class[1]}")
        except Exception as e:
            print(f"  {i+1}. ERROR on '{phrase}': {e}")
            results["reveal_secret"].append((phrase, None, None))
    
    # 2. INTENT_FLIRT
    print("\n[2/4] Тестирую INTENT_FLIRT (20 фраз)...")
    for i, phrase in enumerate(INTENT_FLIRT):
        try:
            intent = await compressor.compress(phrase, {})
            c_class = causal_class(intent)
            results["flirt"].append((phrase, intent, c_class))
            print(f"  {i+1}. '{phrase}' -> action={c_class[0]}, social_intent={c_class[1]}")
        except Exception as e:
            print(f"  {i+1}. ERROR on '{phrase}': {e}")
            results["flirt"].append((phrase, None, None))
    
    # 3. INTENT_COMFORT
    print("\n[3/4] Тестирую INTENT_COMFORT (20 фраз)...")
    for i, phrase in enumerate(INTENT_COMFORT):
        try:
            intent = await compressor.compress(phrase, {})
            c_class = causal_class(intent)
            results["comfort"].append((phrase, intent, c_class))
            print(f"  {i+1}. '{phrase}' -> action={c_class[0]}, social_intent={c_class[1]}")
        except Exception as e:
            print(f"  {i+1}. ERROR on '{phrase}': {e}")
            results["comfort"].append((phrase, None, None))
    
    # 4. INTENT_INTIMIDATE
    print("\n[4/4] Тестирую INTENT_INTIMIDATE (20 фраз)...")
    for i, phrase in enumerate(INTENT_INTIMIDATE):
        try:
            intent = await compressor.compress(phrase, {})
            c_class = causal_class(intent)
            results["intimidate"].append((phrase, intent, c_class))
            print(f"  {i+1}. '{phrase}' -> action={c_class[0]}, social_intent={c_class[1]}")
        except Exception as e:
            print(f"  {i+1}. ERROR on '{phrase}': {e}")
            results["intimidate"].append((phrase, None, None))
    
    # 5. CONTEXT_DEPENDENT
    print("\n[5/5] Тестирую CONTEXT_DEPENDENT (10 кейсов)...")
    for i, (phrase, ctx_a, ctx_b) in enumerate(CONTEXT_DEPENDENT):
        # В реальности здесь нужно менять scene_context
        try:
            intent = await compressor.compress(phrase, {})
            c_class = causal_class(intent)
            results["context"].append((phrase, intent, c_class))
            print(f"  {i+1}. '{phrase}' -> action={c_class[0]}, social_intent={c_class[1]}")
        except Exception as e:
            print(f"  {i+1}. ERROR on '{phrase}': {e}")
            results["context"].append((phrase, None, None))
    
    # === ОТЧЁТ ===
    print("\n=== ОТЧЁТ ===")
    
    # Intent Preservation
    def check_preservation(category_name, category_results, expected_intent):
        if not category_results:
            return 0.0, []
        preserved = 0
        failures = []
        for phrase, intent, c_class in category_results:
            if intent and intent.social_intent and intent.social_intent.value == expected_intent:
                preserved += 1
            else:
                failures.append((phrase, c_class[1] if c_class else None))
        rate = preserved / len(category_results) * 100
        print(f"Intent Preservation ({category_name}): {rate:.1f}% ({preserved}/{len(category_results)})")
        if failures:
            print(f"  Failures: {failures[:5]}...")
        return rate, failures
    
    reveal_rate, _ = check_preservation("REVEAL_SECRET", results["reveal_secret"], "obtain_information")
    flirt_rate, _ = check_preservation("FLIRT", results["flirt"], "flirt")
    comfort_rate, _ = check_preservation("COMFORT", results["comfort"], "comfort")
    intimidate_rate, _ = check_preservation("INTIMIDATE", results["intimidate"], "intimidate")
    
    avg_preservation = (reveal_rate + flirt_rate + comfort_rate + intimidate_rate) / 4
    print(f"\nСреднее Intent Preservation: {avg_preservation:.1f}% (Target: >=85%)")
    
    # Causal Class Equivalence (S203 §8.3.3)
    print("\n--- Causal Class Equivalence ---")
    def check_causal_equiv(category_name, category_results):
        if not category_results:
            return 0.0
        classes = [c_class for _, _, c_class in category_results if c_class is not None]
        if not classes:
            return 0.0
        # Считаем самый частый класс
        from collections import Counter
        counter = Counter(classes)
        most_common_count = counter.most_common(1)[0][1]
        rate = (most_common_count / len(classes)) * 100
        print(f"Causal Class Equivalence ({category_name}): {rate:.1f}%")
        return rate
        
    check_causal_equiv("REVEAL_SECRET", results["reveal_secret"])
    check_causal_equiv("FLIRT", results["flirt"])
    check_causal_equiv("COMFORT", results["comfort"])
    check_causal_equiv("INTIMIDATE", results["intimidate"])
    
    # Save report
    report_dir = Path("reports")
    report_dir.mkdir(exist_ok=True)
    report_path = report_dir / f"semantic_torture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# S203: Semantic Torture Test Report\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("## Metrics\n\n")
        f.write(f"- Intent Preservation (Average): {avg_preservation:.1f}% (Target: >=85%)\n")
        f.write(f"  - REVEAL_SECRET: {reveal_rate:.1f}%\n")
        f.write(f"  - FLIRT: {flirt_rate:.1f}%\n")
        f.write(f"  - COMFORT: {comfort_rate:.1f}%\n")
        f.write(f"  - INTIMIDATE: {intimidate_rate:.1f}%\n\n")
        f.write("## Detailed Results\n\n")
        for cat, cat_results in results.items():
            f.write(f"### {cat.upper()}\n\n")
            f.write("| Phrase | Action | Social Intent | Speech Act | Causal Class |\n")
            f.write("|--------|--------|---------------|------------|--------------|\n")
            for phrase, intent, c_class in cat_results:
                if intent:
                    f.write(f"| {phrase} | {c_class[0]} | {c_class[1]} | {intent.speech_act.value if intent.speech_act else 'None'} | {c_class} |\n")
                else:
                    f.write(f"| {phrase} | ERROR | ERROR | ERROR | ERROR |\n")
            f.write("\n")
    
    print(f"\nОтчёт сохранён в: {report_path}")
    print("=== ТЕСТ ЗАВЕРШЁН ===")

if __name__ == "__main__":
    asyncio.run(run_test())