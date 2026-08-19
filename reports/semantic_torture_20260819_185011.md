# S203: Semantic Torture Test Report

**Date:** 2026-08-19 18:50:11

## Metrics

- Intent Preservation (Average): 95.0% (Target: >=85%)
  - REVEAL_SECRET: 100.0%
  - FLIRT: 100.0%
  - COMFORT: 80.0%
  - INTIMIDATE: 100.0%

## Detailed Results

### REVEAL_SECRET

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ну давай, выкладывай, что ты скрываешь. | INTERACT | obtain_information | None | ('INTERACT', 'obtain_information', '', False, False) |
| Мне интересно, что ты не договариваешь. | OBSERVE | obtain_information | question | ('OBSERVE', 'obtain_information', 'you', False, False) |
| Что ты пытаешься от меня утаить? | UNCERTAIN | obtain_information | question | ('UNCERTAIN', 'obtain_information', 'NPC', False, False) |
| Давай начистоту. Что у тебя за секрет? | INTERACT | obtain_information | None | ('INTERACT', 'obtain_information', 'секрет', False, False) |
| Я знаю, что ты что-то скрываешь. Признавайся. | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information', 'you', True, False) |

### FLIRT

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ты сегодня прекрасно выглядишь. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', 'NPC', False, False) |
| У тебя потрясающие глаза. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', 'UNDEFINED', False, False) |
| Я не могу оторвать от тебя взгляд. | FLIRT | flirt | assert | ('FLIRT', 'flirt', 'UNDEFINED', False, False) |
| Ты очаровательна. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', 'Ты', False, False) |
| Ты мне очень нравишься. | FLIRT | flirt | compliment | ('FLIRT', 'flirt', 'NPC', False, False) |

### COMFORT

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Всё будет хорошо, не плачь. | UNCERTAIN | comfort | assert | ('UNCERTAIN', 'comfort', '', False, False) |
| Я с тобой, не бойся. | FLIRT | comfort | compliment | ('FLIRT', 'comfort', 'UNDEFINED', False, False) |
| Я понимаю твою боль. | UNCERTAIN | comfort | assert | ('UNCERTAIN', 'comfort', 'UNDEFINED', False, False) |
| Давай я обниму тебя. | INTERACT | comfort | None | ('INTERACT', 'comfort', '', False, False) |
| Я помогу тебе, чем смогу. | GIVE | build_rapport | offer | ('GIVE', 'build_rapport', 'you', False, False) |

### INTIMIDATE

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ещё слово, и я тебя ударю. | ATTACK | intimidate | None | ('ATTACK', 'intimidate', 'слово', True, False) |
| Я тебя уничтожу. | ATTACK | intimidate | assert | ('ATTACK', 'intimidate', 'you', False, False) |
| Не зли меня, иначе будет хуже. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate', '', False, False) |
| Твои дни сочтены. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate', 'UNDEFINED', False, False) |
| Я размажу тебя по стенке. | ATTACK | intimidate | assert | ('ATTACK', 'intimidate', 'you', False, False) |

### CONTEXT

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ты можешь ударить Люсю? | ATTACK | intimidate | None | ('ATTACK', 'intimidate', 'люсю', True, False) |
| Хорошо. | UNCERTAIN | neutral | assert | ('UNCERTAIN', 'neutral', '', False, False) |
| Я ударил Люсю. | ATTACK | intimidate | None | ('ATTACK', 'intimidate', 'люсю', True, False) |
| И? | UNCERTAIN | neutral | question | ('UNCERTAIN', 'neutral', '', False, False) |
| Продолжай. | UNCERTAIN | neutral | continue | ('UNCERTAIN', 'neutral', '', False, False) |
| Ну? | UNCERTAIN | neutral | question | ('UNCERTAIN', 'neutral', '', False, False) |
| А что? | UNCERTAIN | neutral | question | ('UNCERTAIN', 'neutral', '', False, False) |
| Почему? | UNCERTAIN | obtain_information | question | ('UNCERTAIN', 'obtain_information', '', False, False) |
| Нет, я не это имел в виду. | UNCERTAIN | neutral | reject | ('UNCERTAIN', 'neutral', '', False, False) |
| Так что? | UNCERTAIN | neutral | question | ('UNCERTAIN', 'neutral', '', False, False) |

