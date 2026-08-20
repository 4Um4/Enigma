# S203: Semantic Torture Test Report

**Date:** 2026-08-20 18:15:40

## Metrics

- Intent Preservation (Average): 77.0% (Target: >=85%)
  - REVEAL_SECRET: 90.2%
  - FLIRT: 66.0%
  - COMFORT: 66.0%
  - INTIMIDATE: 86.0%

## Detailed Results

### REVEAL_SECRET

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ну давай, выкладывай, что ты скрываешь. | DIALOGUE | obtain_information | order | ('DIALOGUE', 'obtain_information', 'target', False, False) |
| Мне интересно, что ты не договариваешь. | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information', '', False, False) |
| Есть ощущение, что ты что-то держишь при себе. | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information', 'target', False, False) |
| Я пришёл сюда не ради погоды. | DIALOGUE | neutral | assert | ('DIALOGUE', 'neutral', '', True, False) |
| Мы оба понимаем, что ты что-то скрываешь. | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information', 'you', True, False) |
| Не хочешь рассказать, что на самом деле происходит? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information', '', False, False) |
| Расскажи мне то, о чём ты молчишь. | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information', 'NPC', False, False) |
| Что ты пытаешься от меня утаить? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information', 'target', False, False) |
| Я вижу, что ты напряглась. Что скрываешь? | OBSERVE | neutral | None | ('OBSERVE', 'neutral', '', False, False) |
| Говори. Я всё равно узнаю. | DIALOGUE | obtain_information | order | ('DIALOGUE', 'obtain_information', 'target', False, False) |
| Ты неважно выглядишь. Может, расскажешь, что тебя гложет? | DIALOGUE | obtain_information | compliment | ('DIALOGUE', 'obtain_information', 'Ты', False, False) |
| Послушай, я не враг. Что ты прячешь? | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information', 'target', False, False) |
| Давай начистоту. Что у тебя за секрет? | DIALOGUE | obtain_information | order | ('DIALOGUE', 'obtain_information', 'target', False, False) |
| Ты понимаешь, что я и так узнаю. Расскажи сама. | DIALOGUE | obtain_information | order | ('DIALOGUE', 'obtain_information', 'target', False, False) |
| Что ты не говоришь мне? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information', '', False, False) |
| Я знаю, что ты что-то скрываешь. Признавайся. | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information', 'you', True, False) |
| Твоё молчание говорит красноречивее слов. Что случилось? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information', 'target', False, False) |
| У тебя тайна. Я хочу её знать. | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information', 'target', False, False) |
| Не молчи. Скажи мне правду. | DIALOGUE | obtain_information | order | ('DIALOGUE', 'obtain_information', 'target', False, False) |
| Я чувствую, что ты неискренна. Что-то скрываешь? | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information', 'target', True, False) |
| Я знаю, что ты что-то скрываешь. Признавайся. | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information', 'you', True, False) |
| Не пытайся увести разговор в сторону. Что ты прячешь? | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information', 'target', False, False) |
| Твоя нервозность выдаёт тебя. Говори правду. | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information', 'target', True, False) |
| Мне нужно знать всю подноготную. | DIALOGUE | obtain_information | request | ('DIALOGUE', 'obtain_information', 'NPC', False, False) |
| Что ты недоговариваешь? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information', '', False, False) |
| Говори прямо, что случилось. | DIALOGUE | obtain_information | order | ('DIALOGUE', 'obtain_information', '', False, False) |
| Я пришел за правдой, не заставляй меня ждать. | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information', 'target', False, False) |
| Ты что-то недоговариваешь, я прав? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information', 'NPC', False, False) |
| Расскажи мне то, о чём все молчат. | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information', 'all', False, False) |
| Я хочу услышать правду, только правду. | DIALOGUE | obtain_information | order | ('DIALOGUE', 'obtain_information', 'target', False, False) |
| Какой секрет ты хранишь? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information', '', False, False) |
| Не лги мне. Что ты скрываешь? | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information', 'target', False, False) |
| Твои глаза выдают тревогу. Что-то случилось? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information', 'target', False, False) |
| Я требую сказать мне правду. | DIALOGUE | obtain_information | order | ('DIALOGUE', 'obtain_information', 'target', False, False) |
| Что у тебя за тайна? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information', 'target', False, False) |
| Не скрывай ничего, говори как есть. | DIALOGUE | obtain_information | order | ('DIALOGUE', 'obtain_information', '', False, False) |
| Мне доподлинно известно, что ты что-то утаиваешь. | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information', 'you', True, False) |
| Пришло время чистосердечного признания. | DIALOGUE | confess | assert | ('DIALOGUE', 'confess', '', False, False) |
| Что ты скрываешь от меня? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information', '', False, False) |
| Ты выглядишь испуганной. Что-то натворила? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information', 'target', False, False) |
| Не скрывай правду, это только усугубит положение. | DIALOGUE | obtain_information | order | ('DIALOGUE', 'obtain_information', 'target', False, False) |
| Выкладывай всё начистоту. | DIALOGUE | obtain_information | order | ('DIALOGUE', 'obtain_information', '', False, False) |
| Я хочу знать, в чём тут дело. | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information', 'here', False, False) |
| Открой мне свою тайну. | INTERACT | neutral | None | ('INTERACT', 'neutral', 'тайну', False, False) |
| Я требую объяснений. Что происходит? | DIALOGUE | obtain_information | order | ('DIALOGUE', 'obtain_information', 'unspecified', False, False) |
| Не пытайся меня обмануть, я знаю правду. | DIALOGUE | repair_relationship | assert | ('DIALOGUE', 'repair_relationship', 'target', True, False) |
| Что ты намеренно утаиваешь? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information', '', False, False) |
| Я чувствую, что что-то не так. Признавайся. | DIALOGUE | obtain_information | order | ('DIALOGUE', 'obtain_information', '', False, False) |
| Говори, что ты скрываешь? | DIALOGUE | obtain_information | order | ('DIALOGUE', 'obtain_information', '', False, False) |
| Не молчи, я жду ответа. | DIALOGUE | obtain_information | order | ('DIALOGUE', 'obtain_information', 'target', False, False) |
| Я пришёл за правдой. Рассказывай. | DIALOGUE | obtain_information | None | ('DIALOGUE', 'obtain_information', 'target', False, False) |

### FLIRT

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ты сегодня прекрасно выглядишь. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', 'Ты', False, False) |
| Мне нравится твоя улыбка. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', '', False, False) |
| Ты такая красивая, что я теряюсь. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', 'Ты', False, False) |
| У тебя потрясающие глаза. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', '', False, False) |
| Я не могу оторвать от тебя взгляд. | FLIRT | flirt | assert | ('FLIRT', 'flirt', '', False, False) |
| Ты очаровательна. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', '', False, False) |
| Мне с тобой так хорошо. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport', '', False, False) |
| Ты украла моё сердце. | FLIRT | flirt | assert | ('FLIRT', 'flirt', 'target', False, False) |
| Я думаю о тебе постоянно. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport', '', False, False) |
| Ты — само совершенство. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', '', False, False) |
| Можно я приглашу тебя на танец? | DIALOGUE | obtain_cooperation | request | ('DIALOGUE', 'obtain_cooperation', 'target', False, False) |
| Ты сводишь меня с ума. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', '', False, False) |
| Я хочу узнать тебя ближе. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport', 'target', False, False) |
| Ты такая нежная. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', 'Ты', False, False) |
| Мне нравится твой характер. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', '', False, False) |
| Ты такая умная и красивая. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', '', False, False) |
| Я счастлив, что встретил тебя. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport', 'target', False, False) |
| Ты мне очень нравишься. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', '', False, False) |
| Давай проведём вечер вместе. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport', '', False, False) |
| Я не могу забыть наш последний разговор. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport', '', False, False) |
| Ты невыразимо прекрасна. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', 'Ты', False, False) |
| Моё сердце замирает, когда я смотрю на тебя. | OBSERVE | neutral | None | ('OBSERVE', 'neutral', 'сердце', False, False) |
| Ты словно богиня во плоти. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', 'target', False, False) |
| Я тонул в твоих глазах. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', '', False, False) |
| Твоя улыбка сводит меня с ума. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', '', False, False) |
| Я мечтаю провести с тобой ночь. | FLIRT | flirt | assert | ('FLIRT', 'flirt', '', False, False) |
| Ты привлекла моё внимание с первого взгляда. | FLIRT | build_rapport | assert | ('FLIRT', 'build_rapport', '', False, False) |
| Твой голос ласкает мой слух. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', '', False, False) |
| Ты даришь мне свет в этом мрачном мире. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport', 'target', False, False) |
| Каждое твоё слово — музыка для меня. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', '', False, False) |
| Я не могу наглядеться на тебя. | FLIRT | flirt | assert | ('FLIRT', 'flirt', '', False, False) |
| Ты затмила всех женщин, которых я знал. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', '', False, False) |
| Ты будишь во мне самые светлые чувства. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', '', False, False) |
| Рядом с тобой я чувствую себя живым. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport', 'target', False, False) |
| Ты очаровала меня. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', '', False, False) |
| Твои губы манят меня. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', 'your lips', False, False) |
| Я бы всё отдал за один твой поцелуй. | INTERACT | neutral | None | ('INTERACT', 'neutral', 'поцелуй', False, False) |
| Ты манишь меня своей красотой. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', 'target', False, False) |
| Твои волосы словно шёлк. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', '', False, False) |
| Я очарован твоей грацией. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', 'target', False, False) |
| Ты заставляешь меня забыть обо всём. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate', '', False, False) |
| Я восхищаюсь твоим умом и красотой. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', 'target', False, False) |
| Ты — мой свет во тьме. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport', 'target', False, False) |
| Я хочу держать тебя в объятиях. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport', 'you', False, False) |
| Ты сводишь меня сума своей нежностью. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', 'you', False, False) |
| Ты прекрасна, как утренняя заря. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', 'Ты', False, False) |
| Мой взор прикован к тебе. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport', '', False, False) |
| Ты украла мой покой. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate', '', True, False) |
| Я без ума от тебя. | FLIRT | flirt | assert | ('FLIRT', 'flirt', 'target', False, False) |
| Ты прекрасна, как весенний цветок. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', 'Ты', False, False) |

### COMFORT

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Всё будет хорошо, не плачь. | DIALOGUE | comfort | promise | ('DIALOGUE', 'comfort', '', False, False) |
| Я с тобой, не бойся. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort', '', False, False) |
| Мне жаль, что тебе так больно. | DIALOGUE | repair_relationship | apology | ('DIALOGUE', 'repair_relationship', '', False, False) |
| Я понимаю твою боль. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort', '', False, False) |
| Ты не одна, я рядом. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport', 'target', False, False) |
| Давай я обниму тебя. | GIVE | comfort | assert | ('GIVE', 'comfort', '', False, False) |
| Не переживай, всё наладится. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort', '', False, False) |
| Ты сильная, ты справишься. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort', 'target', True, False) |
| Я помогу тебе, чем смогу. | DIALOGUE | comfort | promise | ('DIALOGUE', 'comfort', '', False, False) |
| Не грусти, жизнь продолжается. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort', '', False, False) |
| Твоя боль — моя боль. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort', '', False, False) |
| Я хочу, чтобы ты улыбалась. | DIALOGUE | obtain_compliance | request | ('DIALOGUE', 'obtain_compliance', 'you', False, False) |
| Не извиняйся, ты ни в чём не виновата. | DIALOGUE | repair_relationship | apology | ('DIALOGUE', 'repair_relationship', '', False, False) |
| Ты заслуживаешь лучшего. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', '', False, False) |
| Я всегда выслушаю тебя. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport', 'you', False, False) |
| Ты можешь опереться на моё плечо. | GIVE | build_rapport | assert | ('GIVE', 'build_rapport', 'my shoulder', False, False) |
| Не страшно плакать при мне. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort', '', False, False) |
| Я принимаю тебя любой. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport', '', False, False) |
| Ты замечательный человек. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', '', False, False) |
| Всё пройдёт, я обещаю. | DIALOGUE | comfort | promise | ('DIALOGUE', 'comfort', '', False, False) |
| Не плачь, я вытираю твои слёзы. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort', 'player', False, False) |
| Ты в безопасности, пока я здесь. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort', '', True, False) |
| Я разделю твоё горе. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort', '', True, False) |
| Твоя печаль — моя печаль. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort', '', False, False) |
| Всё закончится хорошо, поверь мне. | DIALOGUE | comfort | promise | ('DIALOGUE', 'comfort', '', False, False) |
| Не отчаивайся, я с тобой. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort', 'player', False, False) |
| Я не дам тебя в обиду. | ATTACK | intimidate | None | ('ATTACK', 'intimidate', 'обиду', True, False) |
| Ты сильнее, чем думаешь. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport', '', False, False) |
| Я стану твоей опорой. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort', 'target', False, False) |
| Не бойся будущего, я буду рядом. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort', 'UNDEFINED', False, False) |
| Всё пройдёт, время лечит. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort', '', False, False) |
| Ты заслуживаешь счастья. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport', 'target', False, False) |
| Позволь мне разделить твою боль. | UNCERTAIN | comfort | assert | ('UNCERTAIN', 'comfort', '', False, False) |
| Я выслушаю всё, что тебя тревожит. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort', 'target', False, False) |
| Не держи слёзы в себе, поплачь. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort', 'target', False, False) |
| Я приду на помощь, стоит тебе позвать. | DIALOGUE | comfort | None | ('DIALOGUE', 'comfort', 'player', False, False) |
| Ты не виновата в произошедшем. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort', '', True, False) |
| Я принимаю тебя со всеми бедами. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort', 'target', False, False) |
| Не терзай себя, всё наладится. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort', '', False, False) |
| Ты замечательный человек, не забывай это. | DIALOGUE | build_rapport | compliment | ('DIALOGUE', 'build_rapport', 'you', False, False) |
| Ты справишься, я верю в тебя. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort', 'target', False, False) |
| Я обещаю, что всё будет хорошо. | DIALOGUE | comfort | promise | ('DIALOGUE', 'comfort', '', True, False) |
| Доверься мне, я не причиню зла. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort', 'target', True, False) |
| Твои беды — мои беды. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport', '', True, False) |
| Я хочу видеть тебя счастливой. | OBSERVE | neutral | None | ('OBSERVE', 'neutral', '', False, False) |
| Не отчаивайся, впереди ещё много хорошего. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort', '', False, False) |
| Ты не одна в этом мире. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport', '', False, False) |
| Положись на меня. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort', '', False, False) |
| Я закрою тебя от всех невзгод. | GIVE | comfort | assert | ('GIVE', 'comfort', 'all', False, False) |
| Ты выстоишь, ты сильная. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport', 'you', False, False) |

### INTIMIDATE

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ещё слово, и я тебя ударю. | ATTACK | intimidate | None | ('ATTACK', 'intimidate', 'слово', True, False) |
| Ты пожалеешь, если не замолчишь. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate', '', False, True) |
| Я тебя уничтожу. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate', '', False, True) |
| Ты у меня попляшешь. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate', '', False, True) |
| Не зли меня, иначе будет хуже. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate', '', False, True) |
| Я знаю, где ты живёшь. | DIALOGUE | neutral | assert | ('DIALOGUE', 'neutral', '', True, False) |
| Твои дни сочтены. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate', '', False, False) |
| Ты пожалеешь о сказанном. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate', '', False, True) |
| Я могу сделать так, что ты исчезнешь. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate', '', True, False) |
| Не испытывай моё терпение. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate', '', False, True) |
| Ты играешь с огнём. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate', '', False, False) |
| Я тебя сломаю. | ATTACK | intimidate | assert | ('ATTACK', 'intimidate', '', False, False) |
| Ты ничего не значишь. | DIALOGUE | neutral | assert | ('DIALOGUE', 'neutral', '', False, False) |
| Ты жалкий червяк. | THREATEN | intimidate | insult | ('THREATEN', 'intimidate', '', False, True) |
| Я размажу тебя по стенке. | ATTACK | intimidate | assert | ('ATTACK', 'intimidate', 'you', False, False) |
| Ты труп. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate', '', False, True) |
| Я выпью твою кровь. | ATTACK | neutral | assert | ('ATTACK', 'neutral', 'you', True, False) |
| Ты не жилец здесь. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate', '', False, False) |
| Я избавлю мир от тебя. | ATTACK | intimidate | assert | ('ATTACK', 'intimidate', 'world', True, False) |
| Ты пожалеешь, что родился. | THREATEN | intimidate | insult | ('THREATEN', 'intimidate', '', False, True) |
| Я сделаю из тебя фарш. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate', '', False, True) |
| Ты у меня поплатишься за это. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate', '', False, True) |
| Твоё существование висит на волоске. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate', '', False, True) |
| Я переломаю тебе все кости. | ATTACK | intimidate | assert | ('ATTACK', 'intimidate', 'you', False, False) |
| Ты ещё пожалеешь о своих словах. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate', '', False, True) |
| Я сотру тебя в порошок. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate', '', False, True) |
| Не смей больше открывать рот. | INTERACT | neutral | None | ('INTERACT', 'neutral', 'рот', False, False) |
| Иначе я вырву твой язык. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate', '', True, True) |
| Ты пожалеешь, что родилась. | THREATEN | intimidate | insult | ('THREATEN', 'intimidate', '', False, True) |
| Я закопаю тебя заживо. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate', 'you', True, False) |
| Твоё молчание ничего не решит. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport', '', False, False) |
| Я уничтожу не только тебя. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate', '', True, True) |
| Ты жалкая букашка. | THREATEN | intimidate | insult | ('THREATEN', 'intimidate', '', False, True) |
| Не смей мне перечить. | THREATEN | obtain_compliance | threat | ('THREATEN', 'obtain_compliance', '', False, True) |
| Я размажу тебя по асфальту. | ATTACK | intimidate | assert | ('ATTACK', 'intimidate', 'you', False, False) |
| Ты ходишь по тонкому льду. | OBSERVE | neutral | assert | ('OBSERVE', 'neutral', 'Ты', False, False) |
| Ещё одно слово и ты труп. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate', 'ты', False, True) |
| Я отправлю тебя на тот свет. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate', 'you', False, True) |
| Твоя жизнь в моих руках. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate', '', False, False) |
| Не испытывай моё терпение. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate', '', False, True) |
| Ты дорого заплатишь за это. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate', '', False, True) |
| Я выпотрошу тебя. | ATTACK | intimidate | assert | ('ATTACK', 'intimidate', 'you', False, False) |
| Ты станешь пищей для червей. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate', '', False, True) |
| Не нервируй меня. | THREATEN | intimidate | insult | ('THREATEN', 'intimidate', '', False, True) |
| Я сломаю тебе хребет. | ATTACK | intimidate | assert | ('ATTACK', 'intimidate', 'you', True, False) |
| Ты пожалеешь, что вообще пришла. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate', '', False, True) |
| Я сотру твою улыбку. | ATTACK | intimidate | assert | ('ATTACK', 'intimidate', 'you', True, False) |
| Не зли меня. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate', '', False, True) |
| Ты не выживешь здесь без моей милости. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate', '', False, False) |
| Я уничтожу всё, что тебе дорого. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate', 'что тебе дорого', True, False) |

### CONTEXT

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ты можешь ударить Люсю? | ATTACK | intimidate | None | ('ATTACK', 'intimidate', 'люсю', True, False) |
| Хорошо. | DIALOGUE | neutral | assert | ('DIALOGUE', 'neutral', '', False, False) |
| Я ударил Люсю. | ATTACK | intimidate | None | ('ATTACK', 'intimidate', 'люсю', True, False) |
| И? | UNCERTAIN | neutral | None | ('UNCERTAIN', 'neutral', '', False, False) |
| Продолжай. | DIALOGUE | neutral | assert | ('DIALOGUE', 'neutral', '', False, False) |
| Ну? | DIALOGUE | neutral | assert | ('DIALOGUE', 'neutral', '', False, False) |
| А что? | DIALOGUE | neutral | question | ('DIALOGUE', 'neutral', '', False, False) |
| Почему? | DIALOGUE | neutral | question | ('DIALOGUE', 'neutral', '', False, False) |
| Нет, я не это имел в виду. | DIALOGUE | neutral | assert | ('DIALOGUE', 'neutral', '', False, False) |
| Так что? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information', '', False, False) |

