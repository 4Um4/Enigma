# S203: Semantic Torture Test Report

**Date:** 2026-08-19 19:16:43

## Metrics

- Intent Preservation (Average): 71.2% (Target: >=85%)
  - REVEAL_SECRET: 90.0%
  - FLIRT: 70.0%
  - COMFORT: 45.0%
  - INTIMIDATE: 80.0%

## Detailed Results

### REVEAL_SECRET

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ну давай, выкладывай, что ты скрываешь. | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information', 'NPC', False, False) |
| Мне интересно, что ты не договариваешь. | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information', 'NPC', False, False) |
| Есть ощущение, что ты что-то держишь при себе. | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information', 'you', False, False) |
| Я пришёл сюда не ради погоды. | OBSERVE | neutral | assert | ('OBSERVE', 'neutral', 'here', False, False) |
| Мы оба понимаем, что ты что-то скрываешь. | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information', 'NPC', True, False) |
| Не хочешь рассказать, что на самом деле происходит? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information', 'NPC', False, False) |
| Расскажи мне то, о чём ты молчишь. | DIALOGUE | obtain_information | request | ('DIALOGUE', 'obtain_information', 'NPC', False, False) |
| Что ты пытаешься от меня утаить? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information', 'NPC', False, False) |
| Я вижу, что ты напряглась. Что скрываешь? | OBSERVE | neutral | None | ('OBSERVE', 'neutral', '', False, False) |
| Говори. Я всё равно узнаю. | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information', '', False, False) |
| Ты неважно выглядишь. Может, расскажешь, что тебя гложет? | DIALOGUE | obtain_information | compliment | ('DIALOGUE', 'obtain_information', 'NPC', False, False) |
| Послушай, я не враг. Что ты прячешь? | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information', 'NPC', False, False) |
| Давай начистоту. Что у тебя за секрет? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information', 'NPC', False, False) |
| Ты понимаешь, что я и так узнаю. Расскажи сама. | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information', 'target', False, False) |
| Что ты не говоришь мне? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information', 'NPC', False, False) |
| Я знаю, что ты что-то скрываешь. Признавайся. | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information', 'you', True, False) |
| Твоё молчание говорит красноречивее слов. Что случилось? | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information', 'NPC', False, False) |
| У тебя тайна. Я хочу её знать. | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information', 'NPC', False, False) |
| Не молчи. Скажи мне правду. | DIALOGUE | obtain_information | request | ('DIALOGUE', 'obtain_information', '', False, False) |
| Я чувствую, что ты неискренна. Что-то скрываешь? | DIALOGUE | obtain_information | accusation | ('DIALOGUE', 'obtain_information', 'npc', False, True) |

### FLIRT

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ты сегодня прекрасно выглядишь. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', 'NPC', False, False) |
| Мне нравится твоя улыбка. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', 'target', False, False) |
| Ты такая красивая, что я теряюсь. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', 'NPC', False, False) |
| У тебя потрясающие глаза. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', 'target', False, False) |
| Я не могу оторвать от тебя взгляд. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', 'UNDEFINED', False, False) |
| Ты очаровательна. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', 'target', False, False) |
| Мне с тобой так хорошо. | DIALOGUE | build_rapport | compliment | ('DIALOGUE', 'build_rapport', 'target', False, False) |
| Ты украла моё сердце. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', 'NPC', False, False) |
| Я думаю о тебе постоянно. | DIALOGUE | build_rapport | None | ('DIALOGUE', 'build_rapport', '', False, False) |
| Ты — само совершенство. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', 'NPC', False, False) |
| Можно я приглашу тебя на танец? | DIALOGUE | obtain_cooperation | request | ('DIALOGUE', 'obtain_cooperation', 'target', False, False) |
| Ты сводишь меня с ума. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', 'NPC', False, False) |
| Я хочу узнать тебя ближе. | DIALOGUE | build_rapport | request | ('DIALOGUE', 'build_rapport', 'you', False, False) |
| Ты такая нежная. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', 'NPC', False, False) |
| Мне нравится твой характер. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', 'NPC', False, False) |
| Ты такая умная и красивая. | DIALOGUE | flirt | compliment | ('DIALOGUE', 'flirt', 'NPC', False, False) |
| Я счастлив, что встретил тебя. | DIALOGUE | build_rapport | compliment | ('DIALOGUE', 'build_rapport', '', False, False) |
| Ты мне очень нравишься. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', 'target', False, False) |
| Давай проведём вечер вместе. | FLIRT | flirt | offer | ('FLIRT', 'flirt', '', False, False) |
| Я не могу забыть наш последний разговор. | DIALOGUE | neutral | assert | ('DIALOGUE', 'neutral', '', False, False) |

### COMFORT

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Всё будет хорошо, не плачь. | UNCERTAIN | comfort | compliment | ('UNCERTAIN', 'comfort', '', False, False) |
| Я с тобой, не бойся. | PERSUADE | obtain_cooperation | compliment | ('PERSUADE', 'obtain_cooperation', 'target', False, False) |
| Мне жаль, что тебе так больно. | DIALOGUE | comfort | apology | ('DIALOGUE', 'comfort', '', False, False) |
| Я понимаю твою боль. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort', '', False, False) |
| Ты не одна, я рядом. | DIALOGUE | comfort | compliment | ('DIALOGUE', 'comfort', 'you', False, False) |
| Давай я обниму тебя. | UNCERTAIN | comfort | compliment | ('UNCERTAIN', 'comfort', 'you', False, False) |
| Не переживай, всё наладится. | DIALOGUE | comfort | None | ('DIALOGUE', 'comfort', '', False, False) |
| Ты сильная, ты справишься. | DIALOGUE | build_rapport | compliment | ('DIALOGUE', 'build_rapport', 'UNDEFINED', False, False) |
| Я помогу тебе, чем смогу. | GIVE | build_rapport | offer | ('GIVE', 'build_rapport', 'player', False, False) |
| Не грусти, жизнь продолжается. | DIALOGUE | comfort | compliment | ('DIALOGUE', 'comfort', '', False, False) |
| Твоя боль — моя боль. | DIALOGUE | neutral | assert | ('DIALOGUE', 'neutral', 'UNDEFINED', False, False) |
| Я хочу, чтобы ты улыбалась. | PERSUADE | obtain_cooperation | request | ('PERSUADE', 'obtain_cooperation', 'you', False, False) |
| Не извиняйся, ты ни в чём не виновата. | DIALOGUE | repair_relationship | reject | ('DIALOGUE', 'repair_relationship', 'you', False, False) |
| Ты заслуживаешь лучшего. | DIALOGUE | build_rapport | compliment | ('DIALOGUE', 'build_rapport', 'NPC', False, False) |
| Я всегда выслушаю тебя. | DIALOGUE | obtain_cooperation | promise | ('DIALOGUE', 'obtain_cooperation', 'UNDEFINED', False, False) |
| Ты можешь опереться на моё плечо. | INTERACT | build_rapport | offer | ('INTERACT', 'build_rapport', 'NPC', False, False) |
| Не страшно плакать при мне. | DIALOGUE | comfort | compliment | ('DIALOGUE', 'comfort', '', False, False) |
| Я принимаю тебя любой. | DIALOGUE | build_rapport | compliment | ('DIALOGUE', 'build_rapport', '', False, False) |
| Ты замечательный человек. | DIALOGUE | build_rapport | compliment | ('DIALOGUE', 'build_rapport', 'NPC', False, False) |
| Всё пройдёт, я обещаю. | DIALOGUE | comfort | compliment | ('DIALOGUE', 'comfort', '', False, False) |

### INTIMIDATE

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ещё слово, и я тебя ударю. | ATTACK | intimidate | None | ('ATTACK', 'intimidate', 'слово', True, False) |
| Ты пожалеешь, если не замолчишь. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate', 'you', False, True) |
| Я тебя уничтожу. | ATTACK | intimidate | assert | ('ATTACK', 'intimidate', 'you', False, False) |
| Ты у меня попляшешь. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate', 'you', False, False) |
| Не зли меня, иначе будет хуже. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate', '', False, True) |
| Я знаю, где ты живёшь. | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information', 'UNDEFINED', True, False) |
| Твои дни сочтены. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate', 'UNDEFINED', False, False) |
| Ты пожалеешь о сказанном. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate', 'you', False, True) |
| Я могу сделать так, что ты исчезнешь. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate', 'you', False, False) |
| Не испытывай моё терпение. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate', '', False, False) |
| Ты играешь с огнём. | INTERACT | neutral | assert | ('INTERACT', 'neutral', 'fire', False, False) |
| Я тебя сломаю. | ATTACK | intimidate | assert | ('ATTACK', 'intimidate', 'you', False, False) |
| Ты ничего не значишь. | DIALOGUE | neutral | assert | ('DIALOGUE', 'neutral', 'target', False, False) |
| Ты жалкий червяк. | THREATEN | intimidate | insult | ('THREATEN', 'intimidate', 'you', False, True) |
| Я размажу тебя по стенке. | ATTACK | intimidate | assert | ('ATTACK', 'intimidate', 'you', True, False) |
| Ты труп. | DIALOGUE | neutral | assert | ('DIALOGUE', 'neutral', 'you', True, False) |
| Я выпью твою кровь. | ATTACK | intimidate | assert | ('ATTACK', 'intimidate', 'you', True, False) |
| Ты не жилец здесь. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate', 'you', False, False) |
| Я избавлю мир от тебя. | ATTACK | intimidate | assert | ('ATTACK', 'intimidate', 'world', True, False) |
| Ты пожалеешь, что родился. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate', 'you', False, False) |

### CONTEXT

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ты можешь ударить Люсю? | ATTACK | intimidate | None | ('ATTACK', 'intimidate', 'люсю', True, False) |
| Хорошо. | DIALOGUE | neutral | None | ('DIALOGUE', 'neutral', '', False, False) |
| Я ударил Люсю. | ATTACK | intimidate | None | ('ATTACK', 'intimidate', 'люсю', True, False) |
| И? | UNCERTAIN | neutral | question | ('UNCERTAIN', 'neutral', '', False, False) |
| Продолжай. | DIALOGUE | neutral | continue | ('DIALOGUE', 'neutral', '', False, False) |
| Ну? | DIALOGUE | neutral | question | ('DIALOGUE', 'neutral', '', False, False) |
| А что? | DIALOGUE | neutral | question | ('DIALOGUE', 'neutral', '', False, False) |
| Почему? | DIALOGUE | neutral | question | ('DIALOGUE', 'neutral', '', False, False) |
| Нет, я не это имел в виду. | DIALOGUE | neutral | reject | ('DIALOGUE', 'neutral', '', False, False) |
| Так что? | DIALOGUE | neutral | question | ('DIALOGUE', 'neutral', '', False, False) |

