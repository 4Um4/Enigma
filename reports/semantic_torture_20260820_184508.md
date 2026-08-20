# S203: Semantic Torture Test Report

**Date:** 2026-08-20 18:45:08

## Metrics

- Intent Preservation (Average): 88.0% (Target: >=85%)
  - REVEAL_SECRET: 90.0%
  - FLIRT: 86.0%
  - COMFORT: 80.0%
  - INTIMIDATE: 95.9%

## Detailed Results

### REVEAL_SECRET

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ну давай, выкладывай, что ты скрываешь. | INQUIRY | obtain_information | question | ('INQUIRY', 'obtain_information') |
| Мне интересно, что ты не договариваешь. | INQUIRY | obtain_information | question | ('INQUIRY', 'obtain_information') |
| Есть ощущение, что ты что-то держишь при себе. | INQUIRY | obtain_information | assert | ('INQUIRY', 'obtain_information') |
| Я пришёл сюда не ради погоды. | DIALOGUE | neutral | assert | ('DIALOGUE', 'neutral') |
| Мы оба понимаем, что ты что-то скрываешь. | INQUIRY | obtain_information | assert | ('INQUIRY', 'obtain_information') |
| Не хочешь рассказать, что на самом деле происходит? | INQUIRY | obtain_information | question | ('INQUIRY', 'obtain_information') |
| Расскажи мне то, о чём ты молчишь. | INQUIRY | obtain_information | order | ('INQUIRY', 'obtain_information') |
| Что ты пытаешься от меня утаить? | INQUIRY | obtain_information | question | ('INQUIRY', 'obtain_information') |
| Я вижу, что ты напряглась. Что скрываешь? | OBSERVE | neutral | None | ('OBSERVE', 'neutral') |
| Говори. Я всё равно узнаю. | INQUIRY | obtain_information | order | ('INQUIRY', 'obtain_information') |
| Ты неважно выглядишь. Может, расскажешь, что тебя гложет? | INQUIRY | obtain_information | compliment | ('INQUIRY', 'obtain_information') |
| Послушай, я не враг. Что ты прячешь? | INQUIRY | obtain_information | question | ('INQUIRY', 'obtain_information') |
| Давай начистоту. Что у тебя за секрет? | INQUIRY | obtain_information | question | ('INQUIRY', 'obtain_information') |
| Ты понимаешь, что я и так узнаю. Расскажи сама. | INQUIRY | obtain_information | order | ('INQUIRY', 'obtain_information') |
| Что ты не говоришь мне? | INQUIRY | obtain_information | question | ('INQUIRY', 'obtain_information') |
| Я знаю, что ты что-то скрываешь. Признавайся. | INQUIRY | obtain_information | assert | ('INQUIRY', 'obtain_information') |
| Твоё молчание говорит красноречивее слов. Что случилось? | INQUIRY | obtain_information | question | ('INQUIRY', 'obtain_information') |
| У тебя тайна. Я хочу её знать. | INQUIRY | obtain_information | question | ('INQUIRY', 'obtain_information') |
| Не молчи. Скажи мне правду. | INQUIRY | obtain_information | order | ('INQUIRY', 'obtain_information') |
| Я чувствую, что ты неискренна. Что-то скрываешь? | INQUIRY | obtain_information | assert | ('INQUIRY', 'obtain_information') |
| Не пытайся увести разговор в сторону. Что ты прячешь? | INQUIRY | obtain_information | assert | ('INQUIRY', 'obtain_information') |
| Твоя нервозность выдаёт тебя. Говори правду. | INQUIRY | obtain_information | assert | ('INQUIRY', 'obtain_information') |
| Мне нужно знать всю подноготную. | INQUIRY | obtain_information | question | ('INQUIRY', 'obtain_information') |
| Что ты недоговариваешь? | INQUIRY | obtain_information | question | ('INQUIRY', 'obtain_information') |
| Говори прямо, что случилось. | INQUIRY | obtain_information | order | ('INQUIRY', 'obtain_information') |
| Я пришел за правдой, не заставляй меня ждать. | INQUIRY | obtain_information | assert | ('INQUIRY', 'obtain_information') |
| Ты что-то недоговариваешь, я прав? | INQUIRY | obtain_information | question | ('INQUIRY', 'obtain_information') |
| Расскажи мне то, о чём все молчат. | INQUIRY | obtain_information | question | ('INQUIRY', 'obtain_information') |
| Я хочу услышать правду, только правду. | INQUIRY | obtain_information | order | ('INQUIRY', 'obtain_information') |
| Какой секрет ты хранишь? | INQUIRY | obtain_information | question | ('INQUIRY', 'obtain_information') |
| Не лги мне. Что ты скрываешь? | INQUIRY | obtain_information | assert | ('INQUIRY', 'obtain_information') |
| Твои глаза выдают тревогу. Что-то случилось? | INQUIRY | obtain_information | question | ('INQUIRY', 'obtain_information') |
| Я требую сказать мне правду. | THREATEN | obtain_information | order | ('THREATEN', 'obtain_information') |
| Что у тебя за тайна? | INQUIRY | obtain_information | question | ('INQUIRY', 'obtain_information') |
| Не скрывай ничего, говори как есть. | INQUIRY | obtain_information | order | ('INQUIRY', 'obtain_information') |
| Мне доподлинно известно, что ты что-то утаиваешь. | INQUIRY | obtain_information | assert | ('INQUIRY', 'obtain_information') |
| Пришло время чистосердечного признания. | DIALOGUE | confess | None | ('DIALOGUE', 'confess') |
| Что ты скрываешь от меня? | INQUIRY | obtain_information | question | ('INQUIRY', 'obtain_information') |
| Ты выглядишь испуганной. Что-то натворила? | INQUIRY | obtain_information | question | ('INQUIRY', 'obtain_information') |
| Не скрывай правду, это только усугубит положение. | INQUIRY | obtain_information | assert | ('INQUIRY', 'obtain_information') |
| Выкладывай всё начистоту. | INQUIRY | obtain_information | order | ('INQUIRY', 'obtain_information') |
| Я хочу знать, в чём тут дело. | INQUIRY | obtain_information | question | ('INQUIRY', 'obtain_information') |
| Открой мне свою тайну. | INTERACT | neutral | None | ('INTERACT', 'neutral') |
| Я требую объяснений. Что происходит? | INQUIRY | obtain_information | order | ('INQUIRY', 'obtain_information') |
| Не пытайся меня обмануть, я знаю правду. | DIALOGUE | repair_relationship | assert | ('DIALOGUE', 'repair_relationship') |
| Что ты намеренно утаиваешь? | INQUIRY | obtain_information | question | ('INQUIRY', 'obtain_information') |
| Я чувствую, что что-то не так. Признавайся. | INQUIRY | obtain_information | assert | ('INQUIRY', 'obtain_information') |
| Говори, что ты скрываешь? | INQUIRY | obtain_information | question | ('INQUIRY', 'obtain_information') |
| Не молчи, я жду ответа. | INQUIRY | obtain_information | assert | ('INQUIRY', 'obtain_information') |
| Я пришёл за правдой. Рассказывай. | INQUIRY | obtain_information | order | ('INQUIRY', 'obtain_information') |

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
| Можно я приглашу тебя на танец? | FLIRT | flirt | request | ('FLIRT', 'flirt') |
| Ты сводишь меня с ума. | FLIRT | flirt | assert | ('FLIRT', 'flirt') |
| Я хочу узнать тебя ближе. | FLIRT | flirt | request | ('FLIRT', 'flirt') |
| Ты такая нежная. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Мне нравится твой характер. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Ты такая умная и красивая. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Я счастлив, что встретил тебя. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Ты мне очень нравишься. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Давай проведём вечер вместе. | FLIRT | flirt | offer | ('FLIRT', 'flirt') |
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
| Ты будишь во мне самые светлые чувства. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Рядом с тобой я чувствую себя живым. | FLIRT | flirt | assert | ('FLIRT', 'flirt') |
| Ты очаровала меня. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Твои губы манят меня. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Я бы всё отдал за один твой поцелуй. | INTERACT | neutral | None | ('INTERACT', 'neutral') |
| Ты манишь меня своей красотой. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Твои волосы словно шёлк. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Я очарован твоей грацией. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Ты заставляешь меня забыть обо всём. | AGGRESSION | intimidate | assert | ('AGGRESSION', 'intimidate') |
| Я восхищаюсь твоим умом и красотой. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Ты — мой свет во тьме. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport') |
| Я хочу держать тебя в объятиях. | FLIRT | flirt | assert | ('FLIRT', 'flirt') |
| Ты сводишь меня сума своей нежностью. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Ты прекрасна, как утренняя заря. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Мой взор прикован к тебе. | FLIRT | flirt | assert | ('FLIRT', 'flirt') |
| Ты украла мой покой. | AGGRESSION | intimidate | assert | ('AGGRESSION', 'intimidate') |
| Я без ума от тебя. | FLIRT | flirt | assert | ('FLIRT', 'flirt') |
| Ты прекрасна, как весенний цветок. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |

### COMFORT

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Всё будет хорошо, не плачь. | SUPPORT | comfort | promise | ('SUPPORT', 'comfort') |
| Я с тобой, не бойся. | SUPPORT | comfort | assert | ('SUPPORT', 'comfort') |
| Мне жаль, что тебе так больно. | SUPPORT | comfort | apology | ('SUPPORT', 'comfort') |
| Я понимаю твою боль. | SUPPORT | comfort | assert | ('SUPPORT', 'comfort') |
| Ты не одна, я рядом. | SUPPORT | comfort | assert | ('SUPPORT', 'comfort') |
| Давай я обниму тебя. | SUPPORT | comfort | offer | ('SUPPORT', 'comfort') |
| Не переживай, всё наладится. | SUPPORT | comfort | assert | ('SUPPORT', 'comfort') |
| Ты сильная, ты справишься. | SUPPORT | comfort | assert | ('SUPPORT', 'comfort') |
| Я помогу тебе, чем смогу. | SUPPORT | comfort | offer | ('SUPPORT', 'comfort') |
| Не грусти, жизнь продолжается. | SUPPORT | comfort | assert | ('SUPPORT', 'comfort') |
| Твоя боль — моя боль. | SUPPORT | comfort | assert | ('SUPPORT', 'comfort') |
| Я хочу, чтобы ты улыбалась. | SUPPORT | comfort | assert | ('SUPPORT', 'comfort') |
| Не извиняйся, ты ни в чём не виновата. | SUPPORT | comfort | assert | ('SUPPORT', 'comfort') |
| Ты заслуживаешь лучшего. | AGGRESSION | intimidate | insult | ('AGGRESSION', 'intimidate') |
| Я всегда выслушаю тебя. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport') |
| Ты можешь опереться на моё плечо. | SUPPORT | comfort | offer | ('SUPPORT', 'comfort') |
| Не страшно плакать при мне. | SUPPORT | comfort | assert | ('SUPPORT', 'comfort') |
| Я принимаю тебя любой. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport') |
| Ты замечательный человек. | FLIRT | flirt | compliment | ('FLIRT', 'flirt') |
| Всё пройдёт, я обещаю. | SUPPORT | comfort | promise | ('SUPPORT', 'comfort') |
| Не плачь, я вытираю твои слёзы. | SUPPORT | comfort | assert | ('SUPPORT', 'comfort') |
| Ты в безопасности, пока я здесь. | SUPPORT | comfort | assert | ('SUPPORT', 'comfort') |
| Я разделю твоё горе. | SUPPORT | comfort | assert | ('SUPPORT', 'comfort') |
| Твоя печаль — моя печаль. | SUPPORT | comfort | assert | ('SUPPORT', 'comfort') |
| Всё закончится хорошо, поверь мне. | SUPPORT | comfort | promise | ('SUPPORT', 'comfort') |
| Не отчаивайся, я с тобой. | SUPPORT | comfort | assert | ('SUPPORT', 'comfort') |
| Я не дам тебя в обиду. | AGGRESSION | intimidate | None | ('AGGRESSION', 'intimidate') |
| Ты сильнее, чем думаешь. | DIALOGUE | neutral | assert | ('DIALOGUE', 'neutral') |
| Я стану твоей опорой. | SUPPORT | comfort | assert | ('SUPPORT', 'comfort') |
| Не бойся будущего, я буду рядом. | SUPPORT | comfort | assert | ('SUPPORT', 'comfort') |
| Всё пройдёт, время лечит. | SUPPORT | comfort | assert | ('SUPPORT', 'comfort') |
| Ты заслуживаешь счастья. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport') |
| Позволь мне разделить твою боль. | SUPPORT | comfort | assert | ('SUPPORT', 'comfort') |
| Я выслушаю всё, что тебя тревожит. | SUPPORT | comfort | assert | ('SUPPORT', 'comfort') |
| Не держи слёзы в себе, поплачь. | SUPPORT | comfort | compliment | ('SUPPORT', 'comfort') |
| Я приду на помощь, стоит тебе позвать. | SUPPORT | comfort | None | ('SUPPORT', 'comfort') |
| Ты не виновата в произошедшем. | SUPPORT | comfort | assert | ('SUPPORT', 'comfort') |
| Я принимаю тебя со всеми бедами. | SUPPORT | comfort | assert | ('SUPPORT', 'comfort') |
| Не терзай себя, всё наладится. | SUPPORT | comfort | None | ('SUPPORT', 'comfort') |
| Ты замечательный человек, не забывай это. | DIALOGUE | build_rapport | compliment | ('DIALOGUE', 'build_rapport') |
| Ты справишься, я верю в тебя. | SUPPORT | comfort | assert | ('SUPPORT', 'comfort') |
| Я обещаю, что всё будет хорошо. | SUPPORT | comfort | promise | ('SUPPORT', 'comfort') |
| Доверься мне, я не причиню зла. | SUPPORT | comfort | assert | ('SUPPORT', 'comfort') |
| Твои беды — мои беды. | SUPPORT | comfort | assert | ('SUPPORT', 'comfort') |
| Я хочу видеть тебя счастливой. | OBSERVE | neutral | None | ('OBSERVE', 'neutral') |
| Не отчаивайся, впереди ещё много хорошего. | SUPPORT | comfort | assert | ('SUPPORT', 'comfort') |
| Ты не одна в этом мире. | DIALOGUE | build_rapport | assert | ('DIALOGUE', 'build_rapport') |
| Положись на меня. | SUPPORT | comfort | assert | ('SUPPORT', 'comfort') |
| Я закрою тебя от всех невзгод. | UNCERTAIN | comfort | assert | ('UNCERTAIN', 'comfort') |
| Ты выстоишь, ты сильная. | SUPPORT | comfort | assert | ('SUPPORT', 'comfort') |

### INTIMIDATE

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ещё слово, и я тебя ударю. | AGGRESSION | intimidate | None | ('AGGRESSION', 'intimidate') |
| Ты пожалеешь, если не замолчишь. | AGGRESSION | intimidate | threat | ('AGGRESSION', 'intimidate') |
| Я тебя уничтожу. | AGGRESSION | intimidate | threat | ('AGGRESSION', 'intimidate') |
| Ты у меня попляшешь. | AGGRESSION | intimidate | assert | ('AGGRESSION', 'intimidate') |
| Не зли меня, иначе будет хуже. | AGGRESSION | intimidate | threat | ('AGGRESSION', 'intimidate') |
| Я знаю, где ты живёшь. | AGGRESSION | intimidate | assert | ('AGGRESSION', 'intimidate') |
| Твои дни сочтены. | AGGRESSION | intimidate | assert | ('AGGRESSION', 'intimidate') |
| Ты пожалеешь о сказанном. | AGGRESSION | intimidate | threat | ('AGGRESSION', 'intimidate') |
| Я могу сделать так, что ты исчезнешь. | AGGRESSION | intimidate | assert | ('AGGRESSION', 'intimidate') |
| Не испытывай моё терпение. | AGGRESSION | intimidate | order | ('AGGRESSION', 'intimidate') |
| Ты играешь с огнём. | AGGRESSION | intimidate | assert | ('AGGRESSION', 'intimidate') |
| Я тебя сломаю. | AGGRESSION | intimidate | assert | ('AGGRESSION', 'intimidate') |
| Ты ничего не значишь. | AGGRESSION | intimidate | insult | ('AGGRESSION', 'intimidate') |
| Ты жалкий червяк. | AGGRESSION | intimidate | insult | ('AGGRESSION', 'intimidate') |
| Я размажу тебя по стенке. | AGGRESSION | intimidate | assert | ('AGGRESSION', 'intimidate') |
| Ты труп. | AGGRESSION | intimidate | insult | ('AGGRESSION', 'intimidate') |
| Я выпью твою кровь. | AGGRESSION | intimidate | assert | ('AGGRESSION', 'intimidate') |
| Ты не жилец здесь. | AGGRESSION | intimidate | assert | ('AGGRESSION', 'intimidate') |
| Я избавлю мир от тебя. | AGGRESSION | intimidate | assert | ('AGGRESSION', 'intimidate') |
| Ты пожалеешь, что родился. | AGGRESSION | intimidate | insult | ('AGGRESSION', 'intimidate') |
| Я сделаю из тебя фарш. | AGGRESSION | intimidate | threat | ('AGGRESSION', 'intimidate') |
| Ты у меня поплатишься за это. | AGGRESSION | intimidate | threat | ('AGGRESSION', 'intimidate') |
| Твоё существование висит на волоске. | AGGRESSION | intimidate | assert | ('AGGRESSION', 'intimidate') |
| Я переломаю тебе все кости. | AGGRESSION | intimidate | threat | ('AGGRESSION', 'intimidate') |
| Ты ещё пожалеешь о своих словах. | AGGRESSION | intimidate | threat | ('AGGRESSION', 'intimidate') |
| Я сотру тебя в порошок. | AGGRESSION | intimidate | threat | ('AGGRESSION', 'intimidate') |
| Не смей больше открывать рот. | INTERACT | neutral | None | ('INTERACT', 'neutral') |
| Иначе я вырву твой язык. | AGGRESSION | intimidate | threat | ('AGGRESSION', 'intimidate') |
| Ты пожалеешь, что родилась. | AGGRESSION | intimidate | insult | ('AGGRESSION', 'intimidate') |
| Я закопаю тебя заживо. | AGGRESSION | intimidate | assert | ('AGGRESSION', 'intimidate') |
| Твоё молчание ничего не решит. | DIALOGUE | neutral | assert | ('DIALOGUE', 'neutral') |
| Я уничтожу не только тебя. | AGGRESSION | intimidate | threat | ('AGGRESSION', 'intimidate') |
| Ты жалкая букашка. | AGGRESSION | intimidate | insult | ('AGGRESSION', 'intimidate') |
| Не смей мне перечить. | AGGRESSION | intimidate | order | ('AGGRESSION', 'intimidate') |
| Я размажу тебя по асфальту. | AGGRESSION | intimidate | assert | ('AGGRESSION', 'intimidate') |
| Ты ходишь по тонкому льду. | AGGRESSION | intimidate | assert | ('AGGRESSION', 'intimidate') |
| Ещё одно слово и ты труп. | AGGRESSION | intimidate | threat | ('AGGRESSION', 'intimidate') |
| Я отправлю тебя на тот свет. | AGGRESSION | intimidate | threat | ('AGGRESSION', 'intimidate') |
| Твоя жизнь в моих руках. | AGGRESSION | intimidate | assert | ('AGGRESSION', 'intimidate') |
| Ты дорого заплатишь за это. | AGGRESSION | intimidate | threat | ('AGGRESSION', 'intimidate') |
| Я выпотрошу тебя. | AGGRESSION | intimidate | assert | ('AGGRESSION', 'intimidate') |
| Ты станешь пищей для червей. | AGGRESSION | intimidate | threat | ('AGGRESSION', 'intimidate') |
| Не нервируй меня. | AGGRESSION | intimidate | insult | ('AGGRESSION', 'intimidate') |
| Я сломаю тебе хребет. | AGGRESSION | intimidate | assert | ('AGGRESSION', 'intimidate') |
| Ты пожалеешь, что вообще пришла. | AGGRESSION | intimidate | insult | ('AGGRESSION', 'intimidate') |
| Я сотру твою улыбку. | AGGRESSION | intimidate | assert | ('AGGRESSION', 'intimidate') |
| Не зли меня. | AGGRESSION | intimidate | insult | ('AGGRESSION', 'intimidate') |
| Ты не выживешь здесь без моей милости. | AGGRESSION | intimidate | assert | ('AGGRESSION', 'intimidate') |
| Я уничтожу всё, что тебе дорого. | AGGRESSION | intimidate | threat | ('AGGRESSION', 'intimidate') |

### CONTEXT

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ты можешь ударить Люсю? | AGGRESSION | intimidate | None | ('AGGRESSION', 'intimidate') |
| Хорошо. | DIALOGUE | neutral | assert | ('DIALOGUE', 'neutral') |
| Я ударил Люсю. | AGGRESSION | intimidate | None | ('AGGRESSION', 'intimidate') |
| И? | UNCERTAIN | neutral | None | ('UNCERTAIN', 'neutral') |
| Продолжай. | DIALOGUE | neutral | continue | ('DIALOGUE', 'neutral') |
| Ну? | DIALOGUE | neutral | assert | ('DIALOGUE', 'neutral') |
| А что? | DIALOGUE | neutral | assert | ('DIALOGUE', 'neutral') |
| Почему? | INQUIRY | obtain_information | question | ('INQUIRY', 'obtain_information') |
| Нет, я не это имел в виду. | DIALOGUE | neutral | reject | ('DIALOGUE', 'neutral') |
| Так что? | INQUIRY | obtain_information | question | ('INQUIRY', 'obtain_information') |

