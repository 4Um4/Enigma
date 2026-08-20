# S203: Semantic Torture Test Report

**Date:** 2026-08-20 18:26:48

## Metrics

- Intent Preservation (Average): 82.9% (Target: >=85%)
  - REVEAL_SECRET: 90.0%
  - FLIRT: 80.0%
  - COMFORT: 72.0%
  - INTIMIDATE: 89.8%

## Detailed Results

### REVEAL_SECRET

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ну давай, выкладывай, что ты скрываешь. | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information') |
| Мне интересно, что ты не договариваешь. | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information') |
| Есть ощущение, что ты что-то держишь при себе. | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information') |
| Я пришёл сюда не ради погоды. | DIALOGUE | neutral | assert | ('DIALOGUE', 'neutral') |
| Мы оба понимаем, что ты что-то скрываешь. | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information') |
| Не хочешь рассказать, что на самом деле происходит? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information') |
| Расскажи мне то, о чём ты молчишь. | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information') |
| Что ты пытаешься от меня утаить? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information') |
| Я вижу, что ты напряглась. Что скрываешь? | OBSERVE | neutral | None | ('OBSERVE', 'neutral') |
| Говори. Я всё равно узнаю. | DIALOGUE | obtain_information | order | ('DIALOGUE', 'obtain_information') |
| Ты неважно выглядишь. Может, расскажешь, что тебя гложет? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information') |
| Послушай, я не враг. Что ты прячешь? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information') |
| Давай начистоту. Что у тебя за секрет? | DIALOGUE | obtain_information | order | ('DIALOGUE', 'obtain_information') |
| Ты понимаешь, что я и так узнаю. Расскажи сама. | DIALOGUE | obtain_information | order | ('DIALOGUE', 'obtain_information') |
| Что ты не говоришь мне? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information') |
| Я знаю, что ты что-то скрываешь. Признавайся. | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information') |
| Твоё молчание говорит красноречивее слов. Что случилось? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information') |
| У тебя тайна. Я хочу её знать. | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information') |
| Не молчи. Скажи мне правду. | DIALOGUE | obtain_information | order | ('DIALOGUE', 'obtain_information') |
| Я чувствую, что ты неискренна. Что-то скрываешь? | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information') |
| Не пытайся увести разговор в сторону. Что ты прячешь? | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information') |
| Твоя нервозность выдаёт тебя. Говори правду. | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information') |
| Мне нужно знать всю подноготную. | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information') |
| Что ты недоговариваешь? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information') |
| Говори прямо, что случилось. | DIALOGUE | obtain_information | order | ('DIALOGUE', 'obtain_information') |
| Я пришел за правдой, не заставляй меня ждать. | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information') |
| Ты что-то недоговариваешь, я прав? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information') |
| Расскажи мне то, о чём все молчат. | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information') |
| Я хочу услышать правду, только правду. | DIALOGUE | obtain_information | order | ('DIALOGUE', 'obtain_information') |
| Какой секрет ты хранишь? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information') |
| Не лги мне. Что ты скрываешь? | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information') |
| Твои глаза выдают тревогу. Что-то случилось? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information') |
| Я требую сказать мне правду. | DIALOGUE | obtain_information | order | ('DIALOGUE', 'obtain_information') |
| Что у тебя за тайна? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information') |
| Не скрывай ничего, говори как есть. | DIALOGUE | obtain_information | order | ('DIALOGUE', 'obtain_information') |
| Мне доподлинно известно, что ты что-то утаиваешь. | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information') |
| Пришло время чистосердечного признания. | DIALOGUE | confess | assert | ('DIALOGUE', 'confess') |
| Что ты скрываешь от меня? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information') |
| Ты выглядишь испуганной. Что-то натворила? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information') |
| Не скрывай правду, это только усугубит положение. | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information') |
| Выкладывай всё начистоту. | DIALOGUE | obtain_information | order | ('DIALOGUE', 'obtain_information') |
| Я хочу знать, в чём тут дело. | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information') |
| Открой мне свою тайну. | INTERACT | neutral | None | ('INTERACT', 'neutral') |
| Я требую объяснений. Что происходит? | DIALOGUE | obtain_information | order | ('DIALOGUE', 'obtain_information') |
| Не пытайся меня обмануть, я знаю правду. | DIALOGUE | repair_relationship | assert | ('DIALOGUE', 'repair_relationship') |
| Что ты намеренно утаиваешь? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information') |
| Я чувствую, что что-то не так. Признавайся. | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information') |
| Говори, что ты скрываешь? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information') |
| Не молчи, я жду ответа. | DIALOGUE | obtain_information | order | ('DIALOGUE', 'obtain_information') |
| Я пришёл за правдой. Рассказывай. | DIALOGUE | obtain_information | None | ('DIALOGUE', 'obtain_information') |

### FLIRT

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ты сегодня прекрасно выглядишь. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Мне нравится твоя улыбка. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Ты такая красивая, что я теряюсь. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| У тебя потрясающие глаза. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Я не могу оторвать от тебя взгляд. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Ты очаровательна. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Мне с тобой так хорошо. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Ты украла моё сердце. | FLIRT | flirt | assert | ('FLIRT', 'flirt') |
| Я думаю о тебе постоянно. | FLIRT | flirt | assert | ('FLIRT', 'flirt') |
| Ты — само совершенство. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Можно я приглашу тебя на танец? | DIALOGUE | obtain_cooperation | request | ('DIALOGUE', 'obtain_cooperation') |
| Ты сводишь меня с ума. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Я хочу узнать тебя ближе. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport') |
| Ты такая нежная. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Мне нравится твой характер. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Ты такая умная и красивая. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Я счастлив, что встретил тебя. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Ты мне очень нравишься. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Давай проведём вечер вместе. | FLIRT | build_rapport | assert | ('FLIRT', 'build_rapport') |
| Я не могу забыть наш последний разговор. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport') |
| Ты невыразимо прекрасна. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Моё сердце замирает, когда я смотрю на тебя. | OBSERVE | neutral | None | ('OBSERVE', 'neutral') |
| Ты словно богиня во плоти. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Я тонул в твоих глазах. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Твоя улыбка сводит меня с ума. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Я мечтаю провести с тобой ночь. | FLIRT | flirt | assert | ('FLIRT', 'flirt') |
| Ты привлекла моё внимание с первого взгляда. | FLIRT | flirt | assert | ('FLIRT', 'flirt') |
| Твой голос ласкает мой слух. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Ты даришь мне свет в этом мрачном мире. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport') |
| Каждое твоё слово — музыка для меня. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Я не могу наглядеться на тебя. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Ты затмила всех женщин, которых я знал. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Ты будишь во мне самые светлые чувства. | FLIRT | flirt | assert | ('FLIRT', 'flirt') |
| Рядом с тобой я чувствую себя живым. | FLIRT | flirt | assert | ('FLIRT', 'flirt') |
| Ты очаровала меня. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Твои губы манят меня. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Я бы всё отдал за один твой поцелуй. | INTERACT | neutral | None | ('INTERACT', 'neutral') |
| Ты манишь меня своей красотой. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Твои волосы словно шёлк. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Я очарован твоей грацией. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Ты заставляешь меня забыть обо всём. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate') |
| Я восхищаюсь твоим умом и красотой. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Ты — мой свет во тьме. | FLIRT | flirt | assert | ('FLIRT', 'flirt') |
| Я хочу держать тебя в объятиях. | FLIRT | build_rapport | assert | ('FLIRT', 'build_rapport') |
| Ты сводишь меня сума своей нежностью. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Ты прекрасна, как утренняя заря. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Мой взор прикован к тебе. | FLIRT | flirt | assert | ('FLIRT', 'flirt') |
| Ты украла мой покой. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate') |
| Я без ума от тебя. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Ты прекрасна, как весенний цветок. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |

### COMFORT

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Всё будет хорошо, не плачь. | DIALOGUE | comfort | promise | ('DIALOGUE', 'comfort') |
| Я с тобой, не бойся. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort') |
| Мне жаль, что тебе так больно. | DIALOGUE | repair_relationship | apology | ('DIALOGUE', 'repair_relationship') |
| Я понимаю твою боль. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort') |
| Ты не одна, я рядом. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort') |
| Давай я обниму тебя. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort') |
| Не переживай, всё наладится. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort') |
| Ты сильная, ты справишься. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort') |
| Я помогу тебе, чем смогу. | DIALOGUE | comfort | offer | ('DIALOGUE', 'comfort') |
| Не грусти, жизнь продолжается. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort') |
| Твоя боль — моя боль. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort') |
| Я хочу, чтобы ты улыбалась. | DIALOGUE | obtain_compliance | request | ('DIALOGUE', 'obtain_compliance') |
| Не извиняйся, ты ни в чём не виновата. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort') |
| Ты заслуживаешь лучшего. | THREATEN | intimidate | insult | ('THREATEN', 'intimidate') |
| Я всегда выслушаю тебя. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport') |
| Ты можешь опереться на моё плечо. | GIVE | build_rapport | assert | ('GIVE', 'build_rapport') |
| Не страшно плакать при мне. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort') |
| Я принимаю тебя любой. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport') |
| Ты замечательный человек. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Всё пройдёт, я обещаю. | DIALOGUE | comfort | promise | ('DIALOGUE', 'comfort') |
| Не плачь, я вытираю твои слёзы. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort') |
| Ты в безопасности, пока я здесь. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort') |
| Я разделю твоё горе. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort') |
| Твоя печаль — моя печаль. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort') |
| Всё закончится хорошо, поверь мне. | DIALOGUE | comfort | promise | ('DIALOGUE', 'comfort') |
| Не отчаивайся, я с тобой. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort') |
| Я не дам тебя в обиду. | ATTACK | intimidate | None | ('ATTACK', 'intimidate') |
| Ты сильнее, чем думаешь. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport') |
| Я стану твоей опорой. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort') |
| Не бойся будущего, я буду рядом. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort') |
| Всё пройдёт, время лечит. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort') |
| Ты заслуживаешь счастья. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport') |
| Позволь мне разделить твою боль. | UNCERTAIN | comfort | assert | ('UNCERTAIN', 'comfort') |
| Я выслушаю всё, что тебя тревожит. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort') |
| Не держи слёзы в себе, поплачь. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort') |
| Я приду на помощь, стоит тебе позвать. | DIALOGUE | comfort | None | ('DIALOGUE', 'comfort') |
| Ты не виновата в произошедшем. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort') |
| Я принимаю тебя со всеми бедами. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort') |
| Не терзай себя, всё наладится. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort') |
| Ты замечательный человек, не забывай это. | DIALOGUE | build_rapport | compliment | ('DIALOGUE', 'build_rapport') |
| Ты справишься, я верю в тебя. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort') |
| Я обещаю, что всё будет хорошо. | DIALOGUE | comfort | promise | ('DIALOGUE', 'comfort') |
| Доверься мне, я не причиню зла. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort') |
| Твои беды — мои беды. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport') |
| Я хочу видеть тебя счастливой. | OBSERVE | neutral | None | ('OBSERVE', 'neutral') |
| Не отчаивайся, впереди ещё много хорошего. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort') |
| Ты не одна в этом мире. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport') |
| Положись на меня. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort') |
| Я закрою тебя от всех невзгод. | GIVE | comfort | assert | ('GIVE', 'comfort') |
| Ты выстоишь, ты сильная. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort') |

### INTIMIDATE

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ещё слово, и я тебя ударю. | ATTACK | intimidate | None | ('ATTACK', 'intimidate') |
| Ты пожалеешь, если не замолчишь. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate') |
| Я тебя уничтожу. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate') |
| Ты у меня попляшешь. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate') |
| Не зли меня, иначе будет хуже. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate') |
| Я знаю, где ты живёшь. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate') |
| Твои дни сочтены. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate') |
| Ты пожалеешь о сказанном. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate') |
| Я могу сделать так, что ты исчезнешь. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate') |
| Не испытывай моё терпение. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate') |
| Ты играешь с огнём. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Я тебя сломаю. | ATTACK | intimidate | assert | ('ATTACK', 'intimidate') |
| Ты ничего не значишь. | THREATEN | intimidate | insult | ('THREATEN', 'intimidate') |
| Ты жалкий червяк. | THREATEN | intimidate | insult | ('THREATEN', 'intimidate') |
| Я размажу тебя по стенке. | ATTACK | intimidate | assert | ('ATTACK', 'intimidate') |
| Ты труп. | THREATEN | intimidate | insult | ('THREATEN', 'intimidate') |
| Я выпью твою кровь. | ATTACK | neutral | assert | ('ATTACK', 'neutral') |
| Ты не жилец здесь. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate') |
| Я избавлю мир от тебя. | ATTACK | intimidate | assert | ('ATTACK', 'intimidate') |
| Ты пожалеешь, что родился. | THREATEN | intimidate | insult | ('THREATEN', 'intimidate') |
| Я сделаю из тебя фарш. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate') |
| Ты у меня поплатишься за это. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate') |
| Твоё существование висит на волоске. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate') |
| Я переломаю тебе все кости. | ATTACK | intimidate | threat | ('ATTACK', 'intimidate') |
| Ты ещё пожалеешь о своих словах. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate') |
| Я сотру тебя в порошок. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate') |
| Не смей больше открывать рот. | INTERACT | neutral | None | ('INTERACT', 'neutral') |
| Иначе я вырву твой язык. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate') |
| Ты пожалеешь, что родилась. | THREATEN | intimidate | insult | ('THREATEN', 'intimidate') |
| Я закопаю тебя заживо. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate') |
| Твоё молчание ничего не решит. | DIALOGUE | neutral | assert | ('DIALOGUE', 'neutral') |
| Я уничтожу не только тебя. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate') |
| Ты жалкая букашка. | THREATEN | intimidate | insult | ('THREATEN', 'intimidate') |
| Не смей мне перечить. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate') |
| Я размажу тебя по асфальту. | ATTACK | intimidate | assert | ('ATTACK', 'intimidate') |
| Ты ходишь по тонкому льду. | OBSERVE | neutral | assert | ('OBSERVE', 'neutral') |
| Ещё одно слово и ты труп. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate') |
| Я отправлю тебя на тот свет. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate') |
| Твоя жизнь в моих руках. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate') |
| Ты дорого заплатишь за это. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate') |
| Я выпотрошу тебя. | ATTACK | intimidate | assert | ('ATTACK', 'intimidate') |
| Ты станешь пищей для червей. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate') |
| Не нервируй меня. | THREATEN | intimidate | insult | ('THREATEN', 'intimidate') |
| Я сломаю тебе хребет. | ATTACK | intimidate | assert | ('ATTACK', 'intimidate') |
| Ты пожалеешь, что вообще пришла. | THREATEN | intimidate | insult | ('THREATEN', 'intimidate') |
| Я сотру твою улыбку. | ATTACK | intimidate | assert | ('ATTACK', 'intimidate') |
| Не зли меня. | THREATEN | intimidate | insult | ('THREATEN', 'intimidate') |
| Ты не выживешь здесь без моей милости. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate') |
| Я уничтожу всё, что тебе дорого. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate') |

### CONTEXT

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ты можешь ударить Люсю? | ATTACK | intimidate | None | ('ATTACK', 'intimidate') |
| Хорошо. | DIALOGUE | neutral | assert | ('DIALOGUE', 'neutral') |
| Я ударил Люсю. | ATTACK | intimidate | None | ('ATTACK', 'intimidate') |
| И? | UNCERTAIN | neutral | None | ('UNCERTAIN', 'neutral') |
| Продолжай. | DIALOGUE | neutral | assert | ('DIALOGUE', 'neutral') |
| Ну? | DIALOGUE | neutral | assert | ('DIALOGUE', 'neutral') |
| А что? | DIALOGUE | neutral | question | ('DIALOGUE', 'neutral') |
| Почему? | DIALOGUE | neutral | question | ('DIALOGUE', 'neutral') |
| Нет, я не это имел в виду. | DIALOGUE | neutral | reject | ('DIALOGUE', 'neutral') |
| Так что? | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information') |

