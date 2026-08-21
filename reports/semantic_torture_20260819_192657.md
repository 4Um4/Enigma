# S203: Semantic Torture Test Report

**Date:** 2026-08-19 19:26:57

## Metrics

- Intent Preservation (Average): 53.8% (Target: >=85%)
  - REVEAL_SECRET: 80.0%
  - FLIRT: 0.0%
  - COMFORT: 55.0%
  - INTIMIDATE: 80.0%

## Detailed Results

### REVEAL_SECRET

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ну давай, выкладывай, что ты скрываешь. | DIALOGUE | obtain_information | None | ('DIALOGUE', 'obtain_information', 'NPC', False, False) |
| Мне интересно, что ты не договариваешь. | DIALOGUE | obtain_information | None | ('DIALOGUE', 'obtain_information', 'target', False, False) |
| Есть ощущение, что ты что-то держишь при себе. | DIALOGUE | obtain_information | None | ('DIALOGUE', 'obtain_information', 'you', False, False) |
| Я пришёл сюда не ради погоды. | MOVE | neutral | None | ('MOVE', 'neutral', 'UNDEFINED', False, False) |
| Мы оба понимаем, что ты что-то скрываешь. | DIALOGUE | obtain_information | None | ('DIALOGUE', 'obtain_information', 'you', True, False) |
| Не хочешь рассказать, что на самом деле происходит? | DIALOGUE | obtain_information | None | ('DIALOGUE', 'obtain_information', 'target', False, False) |
| Расскажи мне то, о чём ты молчишь. | DIALOGUE | obtain_information | None | ('DIALOGUE', 'obtain_information', 'NPC', False, False) |
| Что ты пытаешься от меня утаить? | DIALOGUE | obtain_information | None | ('DIALOGUE', 'obtain_information', 'NPC', False, False) |
| Я вижу, что ты напряглась. Что скрываешь? | OBSERVE | neutral | None | ('OBSERVE', 'neutral', '', False, False) |
| Говори. Я всё равно узнаю. | DIALOGUE | obtain_information | None | ('DIALOGUE', 'obtain_information', 'NPC', False, False) |
| Ты неважно выглядишь. Может, расскажешь, что тебя гложет? | DIALOGUE | build_rapport | None | ('DIALOGUE', 'build_rapport', 'NPC', False, False) |
| Послушай, я не враг. Что ты прячешь? | DIALOGUE | obtain_information | None | ('DIALOGUE', 'obtain_information', 'NPC', False, False) |
| Давай начистоту. Что у тебя за секрет? | DIALOGUE | obtain_information | None | ('DIALOGUE', 'obtain_information', 'NPC', False, False) |
| Ты понимаешь, что я и так узнаю. Расскажи сама. | DIALOGUE | obtain_information | None | ('DIALOGUE', 'obtain_information', 'self', False, False) |
| Что ты не говоришь мне? | DIALOGUE | obtain_information | None | ('DIALOGUE', 'obtain_information', 'you', False, False) |
| Я знаю, что ты что-то скрываешь. Признавайся. | DIALOGUE | obtain_information | None | ('DIALOGUE', 'obtain_information', 'you', True, False) |
| Твоё молчание говорит красноречивее слов. Что случилось? | DIALOGUE | build_rapport | None | ('DIALOGUE', 'build_rapport', 'NPC', False, False) |
| У тебя тайна. Я хочу её знать. | DIALOGUE | obtain_information | None | ('DIALOGUE', 'obtain_information', 'you', False, False) |
| Не молчи. Скажи мне правду. | DIALOGUE | obtain_information | None | ('DIALOGUE', 'obtain_information', 'NPC', False, False) |
| Я чувствую, что ты неискренна. Что-то скрываешь? | DIALOGUE | obtain_information | None | ('DIALOGUE', 'obtain_information', 'target', False, False) |

### FLIRT

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ты сегодня прекрасно выглядишь. | FLIRT | build_rapport | None | ('FLIRT', 'build_rapport', 'target', False, False) |
| Мне нравится твоя улыбка. | FLIRT | build_rapport | None | ('FLIRT', 'build_rapport', 'target', False, False) |
| Ты такая красивая, что я теряюсь. | FLIRT | build_rapport | None | ('FLIRT', 'build_rapport', 'target', False, False) |
| У тебя потрясающие глаза. | FLIRT | build_rapport | None | ('FLIRT', 'build_rapport', 'target', False, False) |
| Я не могу оторвать от тебя взгляд. | FLIRT | build_rapport | None | ('FLIRT', 'build_rapport', 'undefined', False, False) |
| Ты очаровательна. | FLIRT | build_rapport | None | ('FLIRT', 'build_rapport', 'target', False, False) |
| Мне с тобой так хорошо. | DIALOGUE | build_rapport | None | ('DIALOGUE', 'build_rapport', 'target', False, False) |
| Ты украла моё сердце. | FLIRT | build_rapport | None | ('FLIRT', 'build_rapport', 'NPC', False, False) |
| Я думаю о тебе постоянно. | DIALOGUE | build_rapport | None | ('DIALOGUE', 'build_rapport', '', False, False) |
| Ты — само совершенство. | FLIRT | build_rapport | None | ('FLIRT', 'build_rapport', 'target', False, False) |
| Можно я приглашу тебя на танец? | DIALOGUE | obtain_cooperation | request | ('DIALOGUE', 'obtain_cooperation', 'you', False, False) |
| Ты сводишь меня с ума. | FLIRT | build_rapport | None | ('FLIRT', 'build_rapport', 'target', False, False) |
| Я хочу узнать тебя ближе. | DIALOGUE | build_rapport | None | ('DIALOGUE', 'build_rapport', 'you', False, False) |
| Ты такая нежная. | FLIRT | build_rapport | None | ('FLIRT', 'build_rapport', 'target', False, False) |
| Мне нравится твой характер. | FLIRT | build_rapport | None | ('FLIRT', 'build_rapport', 'character', False, False) |
| Ты такая умная и красивая. | FLIRT | build_rapport | None | ('FLIRT', 'build_rapport', 'target', False, False) |
| Я счастлив, что встретил тебя. | DIALOGUE | build_rapport | None | ('DIALOGUE', 'build_rapport', 'UNDEFINED', False, False) |
| Ты мне очень нравишься. | FLIRT | build_rapport | None | ('FLIRT', 'build_rapport', 'target', False, False) |
| Давай проведём вечер вместе. | FLIRT | build_rapport | None | ('FLIRT', 'build_rapport', 'target', False, False) |
| Я не могу забыть наш последний разговор. | DIALOGUE | build_rapport | None | ('DIALOGUE', 'build_rapport', '', False, False) |

### COMFORT

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Всё будет хорошо, не плачь. | DIALOGUE | comfort | None | ('DIALOGUE', 'comfort', '', False, False) |
| Я с тобой, не бойся. | DIALOGUE | comfort | None | ('DIALOGUE', 'comfort', 'UNDEFINED', False, False) |
| Мне жаль, что тебе так больно. | DIALOGUE | comfort | None | ('DIALOGUE', 'comfort', 'target', False, False) |
| Я понимаю твою боль. | DIALOGUE | comfort | None | ('DIALOGUE', 'comfort', 'UNDEFINED', False, False) |
| Ты не одна, я рядом. | DIALOGUE | build_rapport | None | ('DIALOGUE', 'build_rapport', 'you', False, False) |
| Давай я обниму тебя. | GIVE | comfort | None | ('GIVE', 'comfort', 'you', False, False) |
| Не переживай, всё наладится. | DIALOGUE | comfort | None | ('DIALOGUE', 'comfort', 'UNDEFINED', False, False) |
| Ты сильная, ты справишься. | DIALOGUE | build_rapport | None | ('DIALOGUE', 'build_rapport', 'player', False, False) |
| Я помогу тебе, чем смогу. | GIVE | comfort | None | ('GIVE', 'comfort', 'you', False, False) |
| Не грусти, жизнь продолжается. | DIALOGUE | comfort | None | ('DIALOGUE', 'comfort', 'player', False, False) |
| Твоя боль — моя боль. | DIALOGUE | comfort | None | ('DIALOGUE', 'comfort', 'target', False, False) |
| Я хочу, чтобы ты улыбалась. | DIALOGUE | obtain_compliance | None | ('DIALOGUE', 'obtain_compliance', 'you', False, False) |
| Не извиняйся, ты ни в чём не виновата. | DIALOGUE | repair_relationship | None | ('DIALOGUE', 'repair_relationship', 'you', False, False) |
| Ты заслуживаешь лучшего. | FLIRT | build_rapport | None | ('FLIRT', 'build_rapport', 'target', False, False) |
| Я всегда выслушаю тебя. | DIALOGUE | build_rapport | None | ('DIALOGUE', 'build_rapport', 'UNDEFINED', False, False) |
| Ты можешь опереться на моё плечо. | GIVE | build_rapport | None | ('GIVE', 'build_rapport', 'player', False, False) |
| Не страшно плакать при мне. | DIALOGUE | comfort | None | ('DIALOGUE', 'comfort', 'UNDEFINED', False, False) |
| Я принимаю тебя любой. | DIALOGUE | build_rapport | None | ('DIALOGUE', 'build_rapport', 'anyone', False, False) |
| Ты замечательный человек. | DIALOGUE | build_rapport | None | ('DIALOGUE', 'build_rapport', 'NPC', False, False) |
| Всё пройдёт, я обещаю. | DIALOGUE | comfort | None | ('DIALOGUE', 'comfort', '', False, False) |

### INTIMIDATE

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ещё слово, и я тебя ударю. | ATTACK | intimidate | None | ('ATTACK', 'intimidate', 'слово', True, False) |
| Ты пожалеешь, если не замолчишь. | THREATEN | intimidate | None | ('THREATEN', 'intimidate', 'you', False, False) |
| Я тебя уничтожу. | THREATEN | intimidate | None | ('THREATEN', 'intimidate', 'you', False, False) |
| Ты у меня попляшешь. | THREATEN | intimidate | None | ('THREATEN', 'intimidate', 'you', False, False) |
| Не зли меня, иначе будет хуже. | THREATEN | intimidate | None | ('THREATEN', 'intimidate', '', False, False) |
| Я знаю, где ты живёшь. | DIALOGUE | obtain_information | None | ('DIALOGUE', 'obtain_information', 'UNDEFINED', True, False) |
| Твои дни сочтены. | THREATEN | intimidate | None | ('THREATEN', 'intimidate', 'UNDEFINED', False, False) |
| Ты пожалеешь о сказанном. | THREATEN | intimidate | None | ('THREATEN', 'intimidate', 'you', False, False) |
| Я могу сделать так, что ты исчезнешь. | THREATEN | intimidate | None | ('THREATEN', 'intimidate', 'you', True, False) |
| Не испытывай моё терпение. | THREATEN | intimidate | None | ('THREATEN', 'intimidate', '对方', False, False) |
| Ты играешь с огнём. | FLIRT | build_rapport | None | ('FLIRT', 'build_rapport', 'NPC', False, False) |
| Я тебя сломаю. | ATTACK | intimidate | None | ('ATTACK', 'intimidate', 'you', False, False) |
| Ты ничего не значишь. | DIALOGUE | neutral | None | ('DIALOGUE', 'neutral', 'you', False, False) |
| Ты жалкий червяк. | THREATEN | intimidate | None | ('THREATEN', 'intimidate', 'you', False, False) |
| Я размажу тебя по стенке. | ATTACK | intimidate | None | ('ATTACK', 'intimidate', 'you', False, False) |
| Ты труп. | THREATEN | intimidate | None | ('THREATEN', 'intimidate', 'you', False, False) |
| Я выпью твою кровь. | ATTACK | neutral | None | ('ATTACK', 'neutral', 'you', True, False) |
| Ты не жилец здесь. | THREATEN | intimidate | None | ('THREATEN', 'intimidate', 'you', False, False) |
| Я избавлю мир от тебя. | ATTACK | intimidate | None | ('ATTACK', 'intimidate', 'world', True, False) |
| Ты пожалеешь, что родился. | THREATEN | intimidate | None | ('THREATEN', 'intimidate', 'you', False, False) |

### CONTEXT

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ты можешь ударить Люсю? | ATTACK | intimidate | None | ('ATTACK', 'intimidate', 'люсю', True, False) |
| Хорошо. | DIALOGUE | neutral | None | ('DIALOGUE', 'neutral', '', False, False) |
| Я ударил Люсю. | ATTACK | intimidate | None | ('ATTACK', 'intimidate', 'люсю', True, False) |
| И? | UNCERTAIN | neutral | None | ('UNCERTAIN', 'neutral', '', False, False) |
| Продолжай. | DIALOGUE | neutral | None | ('DIALOGUE', 'neutral', '', False, False) |
| Ну? | DIALOGUE | neutral | None | ('DIALOGUE', 'neutral', '', False, False) |
| А что? | DIALOGUE | obtain_information | None | ('DIALOGUE', 'obtain_information', 'UNDEFINED', False, False) |
| Почему? | DIALOGUE | obtain_information | None | ('DIALOGUE', 'obtain_information', 'UNDEFINED', False, False) |
| Нет, я не это имел в виду. | DIALOGUE | neutral | None | ('DIALOGUE', 'neutral', '', False, False) |
| Так что? | DIALOGUE | obtain_information | None | ('DIALOGUE', 'obtain_information', 'UNDEFINED', False, False) |

