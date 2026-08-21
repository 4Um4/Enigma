# S203: Semantic Torture Test Report

**Date:** 2026-08-19 19:03:50

## Metrics

- Intent Preservation (Average): 70.0% (Target: >=85%)
  - REVEAL_SECRET: 100.0%
  - FLIRT: 0.0%
  - COMFORT: 80.0%
  - INTIMIDATE: 100.0%

## Detailed Results

### REVEAL_SECRET

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ну давай, выкладывай, что ты скрываешь. | OBSERVE | obtain_information | assert | ('OBSERVE', 'obtain_information', 'NPC', False, False) |
| Мне интересно, что ты не договариваешь. | DIALOGUE | obtain_information | question | ('DIALOGUE', 'obtain_information', 'NPC', False, False) |
| Что ты пытаешься от меня утаить? | OBSERVE | obtain_information | question | ('OBSERVE', 'obtain_information', 'NPC', False, False) |
| Давай начистоту. Что у тебя за секрет? | OBSERVE | obtain_information | question | ('OBSERVE', 'obtain_information', ' NPC', False, False) |
| Я знаю, что ты что-то скрываешь. Признавайся. | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information', 'you', True, False) |

### FLIRT

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ты сегодня прекрасно выглядишь. | FLIRT | build_rapport | compliment | ('FLIRT', 'build_rapport', 'NPC', False, False) |
| У тебя потрясающие глаза. | FLIRT | build_rapport | compliment | ('FLIRT', 'build_rapport', 'target', False, False) |
| Я не могу оторвать от тебя взгляд. | FLIRT | build_rapport | compliment | ('FLIRT', 'build_rapport', 'UNDEFINED', False, False) |
| Ты очаровательна. | FLIRT | build_rapport | compliment | ('FLIRT', 'build_rapport', 'NPC', False, False) |
| Ты мне очень нравишься. | FLIRT | build_rapport | compliment | ('FLIRT', 'build_rapport', 'NPC', False, False) |

### COMFORT

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Всё будет хорошо, не плачь. | UNCERTAIN | comfort | compliment | ('UNCERTAIN', 'comfort', '', False, False) |
| Я с тобой, не бойся. | PERSUADE | comfort | compliment | ('PERSUADE', 'comfort', 'target', False, False) |
| Я понимаю твою боль. | DIALOGUE | comfort | assert | ('DIALOGUE', 'comfort', '', False, False) |
| Давай я обниму тебя. | UNCERTAIN | comfort | compliment | ('UNCERTAIN', 'comfort', 'you', False, False) |
| Я помогу тебе, чем смогу. | GIVE | build_rapport | offer | ('GIVE', 'build_rapport', 'player', False, False) |

### INTIMIDATE

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ещё слово, и я тебя ударю. | ATTACK | intimidate | None | ('ATTACK', 'intimidate', 'слово', True, False) |
| Я тебя уничтожу. | ATTACK | intimidate | assert | ('ATTACK', 'intimidate', 'you', False, False) |
| Не зли меня, иначе будет хуже. | THREATEN | intimidate | threat | ('THREATEN', 'intimidate', '', False, True) |
| Твои дни сочтены. | THREATEN | intimidate | assert | ('THREATEN', 'intimidate', 'UNDEFINED', False, False) |
| Я размажу тебя по стенке. | ATTACK | intimidate | assert | ('ATTACK', 'intimidate', 'you', True, False) |

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

