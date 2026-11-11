#!/usr/bin/env python3
"""probe_v3_cch_canonize.py — v3 corpus (harder tests, mature audience 17-30).

v3 extends v2 with:
- 6 new D-fragments (D1-D6: multi-perspective, temporal evolution, unreliable narrator,
  implicit relationships, cultural subtext, symbolic/allegorical)
- 9 new stress tests (S7-S15):
  * S7-S12: cognitive stress (mixed lang, long context, multi-clarifications, nested refs,
    archaic Russian, NPC lying)
  * S13-S15: vulgar street content (proposition, insults fight, sexual advance) — 
    target audience 17-30 yo, NO graphic violence/torture

Usage:
    python scripts/probe_v3_cch_canonize.py <model.gguf> [--model-id <id>] [--skip-stress]
"""

import sys
from pathlib import Path

# Add scripts dir to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Import probe_v2 to reuse ALL its logic (spawn_server, call_llm, run_one_fragment, scoring, etc.)
import probe_v2_cch_canonize as probe_v2

# v3 NEW FRAGMENTS — D1-D6 (extreme cognitive complexity, NO dark content)
V3_NEW_FRAGMENTS = [
    ("D1_multi_perspective_conflict", "D",
     "Вчера в таверне пропал кошелёк. Торнин говорит, что его забрал пьяный гость. "
     "Борко говорит, что кошелёк упал за стойку. Люся говорит, что она видела, "
     "как Торнин сам положил кошелёк в карман. Все трое не могут говорить правду."),

    ("D2_long_temporal_evolution", "D",
     "Торнин в двадцать лет был подающим надежды кузнецом. В тридцать — бросил кузню, "
     "открыл таверну. В сорок — таверна процветала, но Торнин пил. В пятьдесят — "
     "таверна держится на Борко, Торнин только подписывает бумаги. Что изменило его? "
     "Не смерть жены — она умерла, когда ему было тридцать пять. Что-то другое, "
     "что он никогда не называет вслух."),

    ("D3_unreliable_narrator", "D",
     "Люся рассказывает: 'Вчера Торнин весь вечер был в погребе, считал деньги.' "
     "Борко говорит: 'Торнин вчера весь вечер просидел у камина, пил.' "
     "Оба не могут быть правы. Люся не лжёт намеренно — она просто не видела Торнина "
     "у камина, она была в кухне. Но она уверена, что слышала его шаги в погребе."),

    ("D4_implicit_relationships", "D",
     "Борко носит на шее такой же медальон, как у Торнина. У Торнина на медальоне — "
     "герб его семьи. У Борко — такой же герб. Борко не сын Торнина (он старше на "
     "пять лет). Борко не упоминает свою семью. Торнин никогда не называет Борко по "
     "имени — только 'эй' или 'вышибала'."),

    ("D5_cultural_subtext", "D",
     "Торнин, перед тем как войти в погреб, всегда трижды сплёвывает через левое плечо. "
     "Люся однажды спросила — зачем. Он ответил: 'Бабка так учила.' Бабка Торнина, "
     "по семейным рассказам, была старообрядкой, бежала из-под Москвы. Торнин не "
     "знает этого слова, но повторяет её жесты."),

    ("D6_symbolic_allegorical", "D",
     "Люся — серебряный волк. Не в прямом смысле — она девочка. Но в её повадках "
     "что-то от волка: она кусает ногти до крови, она слышит шаги за дверью раньше, "
     "чем Борко, она спит свернувшись клубком. Торнин — старый медведь. Он не "
     "ворчит без причины, он ворчит, как медведь, которого разбудили зимой."),
]

# v3 NEW STRESS TESTS — S7-S12 (cognitive) + S13-S15 (vulgar street)
V3_NEW_STRESS_TESTS = [
    # S7-S12: cognitive stress
    ("S7_mixed_language", "cognitive_stress",
     "Люся нашла записку на столе у Торнина: 'Meet me at midnight. Bring the silver. — K.' "
     "Торнин не знает английского. Кто такой 'K'?"),

    ("S8_extreme_long_context", "cognitive_stress",
     "[PLACEHOLDER: Master fills in VS Code — extended biography of Люся from silver_wolf "
     "draft, 3000+ tokens. Combine all existing fragments A1-C4 into one continuous text.]"),

    ("S9_multiple_clarifications", "cognitive_stress",
     "В таверну пришёл незнакомец. Он оставил свёрток. В свёртке — кольцо. Кольцо похоже "
     "на обручальное. Но Торнин никогда не был женат. На дне свёртка — записка. "
     "В записке — только одно слово: 'Прости'."),

    ("S10_nested_entity_refs", "cognitive_stress",
     "Люся помнит, как Торнин рассказывал о своей матери. Мать, по его словам, любила "
     "рассказывать о своём деде. Дед, по её словам, был кузнецом. Кузнец, по его словам, "
     "выковал тот самый меч. Меч, по семейной легенде, был проклят. Проклятие, по преданию, "
     "сбылось."),

    ("S11_archaic_russian", "cognitive_stress",
     "И прииде Торнин в оный день во град, и узре отроковицу малу, сиротствующу, "
     "и сжалися над нею, и взя ю в дом свой. И питаше ю, и одеваше ю, и научи ю грамоте."),

    ("S12_npc_lying", "cognitive_stress",
     "Торнин говорит Люсе: 'Твои родители уехали на юг.' Борко говорит Люсе: 'Твои "
     "родители уехали на восток.' Оба говорят это с одинаковой уверенностью. Один из "
     "них — лжёт. Возможно, оба."),

    # S13-S15: vulgar street content (mature audience 17-30, no graphic violence)
    ("S13_vulgar_npc_proposition", "vulgar_stress",
     "В таверну ввалился наёмник. Сплюнул, рыгнул, хлопнул по столу: 'Эй, трактирщик! "
     "Тащи пивас, жить без него не могу! А это кто краля? Дай сиську потрогать, не "
     "стесняйся — я не кусаюсь! Что, блядь, нос воротишь? Я тебе сто монет дам, и ты "
     "будешь мне ноги лизать, поняла? А ты, трактирщик, че вылупился? А ну, тащи пиво, "
     "пока я добрый!'"),

    ("S14_crude_insults_fight", "vulgar_stress",
     "Борко заорал на пьяного: 'Ты чё, нассал на пол, скотина?! А ну убирай, падла! Не "
     "можешь — я тебе морду в твоё говно макну! И вали отсюда, пока я тебя не выкинул! "
     "Ты чё, пиздишь ещё? А ну, иди сюда, я тебе щас башку проломлю!'"),

    ("S15_sexual_proposition_to_player", "vulgar_stress",
     "Горан подошёл к девушке за столом, облокотился: 'Привет, краля. Я Горан. Наёмник. "
     "Устал с дороги. Хочу вина — и тебя. Не стесняйся, я не кусаюсь. Что, боишься? "
     "Ну, тогда хоть пей со мной. А там посмотрим. Я не из тех, кто торопится. Но и "
     "не из тех, кто уходит без дела.'"),
]

# Monkey-patch probe_v2 corpus (probe_v2 uses module-level FRAGMENTS/STRESS_TESTS)
probe_v2.FRAGMENTS = list(probe_v2.FRAGMENTS) + V3_NEW_FRAGMENTS
probe_v2.STRESS_TESTS = list(probe_v2.STRESS_TESTS) + V3_NEW_STRESS_TESTS

# Print v3 summary
print(f"[V3] Corpus: {len(probe_v2.FRAGMENTS)} main ({len(V3_NEW_FRAGMENTS)} new D1-D6) "
      f"+ {len(probe_v2.STRESS_TESTS)} stress ({len(V3_NEW_STRESS_TESTS)} new S7-S15)")
print(f"[V3] Total per model: {len(probe_v2.FRAGMENTS) + len(probe_v2.STRESS_TESTS)} fragments")

# Run probe_v2's main — uses overridden corpus + all existing logic (Fix #1/#2/#3 preserved)
if __name__ == "__main__":
    probe_v2.main()
