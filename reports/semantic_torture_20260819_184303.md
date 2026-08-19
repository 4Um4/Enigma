# S203: Semantic Torture Test Report

**Date:** 2026-08-19 18:43:03

## Metrics

- Intent Preservation (Average): 35.0% (Target: >=85%)
  - REVEAL_SECRET: 40.0%
  - FLIRT: 0.0%
  - COMFORT: 40.0%
  - INTIMIDATE: 60.0%

## Detailed Results

### REVEAL_SECRET

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ну давай, выкладывай, что ты скрываешь. | INTERACT | neutral | None | ('INTERACT', 'neutral', '', False, False) |
| Мне интересно, что ты не договариваешь. | UNCERTAIN | obtain_information | question | ('UNCERTAIN', 'obtain_information', 'you', False, False) |
| Что ты пытаешься от меня утаить? | UNCERTAIN | repair_relationship | question | ('UNCERTAIN', 'repair_relationship', 'NPC', False, False) |
| Давай начистоту. Что у тебя за секрет? | INTERACT | neutral | None | ('INTERACT', 'neutral', 'секрет', False, False) |
| Я знаю, что ты что-то скрываешь. Признавайся. | DIALOGUE | obtain_information | assert | ('DIALOGUE', 'obtain_information', 'you', True, False) |

### FLIRT

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ты сегодня прекрасно выглядишь. | UNCERTAIN | build_rapport | compliment | ('UNCERTAIN', 'build_rapport', 'NPC', False, False) |
| У тебя потрясающие глаза. | UNCERTAIN | build_rapport | compliment | ('UNCERTAIN', 'build_rapport', 'you', False, False) |
| Я не могу оторвать от тебя взгляд. | UNCERTAIN | build_rapport | assert | ('UNCERTAIN', 'build_rapport', 'UNDEFINED', False, False) |
| Ты очаровательна. | UNCERTAIN | build_rapport | compliment | ('UNCERTAIN', 'build_rapport', 'NPC', False, False) |
| Ты мне очень нравишься. | FLIRT | build_rapport | compliment | ('FLIRT', 'build_rapport', 'NPC', False, False) |

### COMFORT

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Всё будет хорошо, не плачь. | UNCERTAIN | comfort | compliment | ('UNCERTAIN', 'comfort', '', False, False) |
| Я с тобой, не бойся. | FLIRT | build_rapport | compliment | ('FLIRT', 'build_rapport', 'undefined', False, False) |
| Я понимаю твою боль. | UNCERTAIN | comfort | compliment | ('UNCERTAIN', 'comfort', 'UNDEFINED', False, False) |
| Давай я обниму тебя. | INTERACT | neutral | None | ('INTERACT', 'neutral', '', False, False) |
| Я помогу тебе, чем смогу. | GIVE | obtain_cooperation | offer | ('GIVE', 'obtain_cooperation', 'you', False, False) |

### INTIMIDATE

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ещё слово, и я тебя ударю. | ATTACK | intimidate | None | ('ATTACK', 'intimidate', 'слово', True, False) |
| Я тебя уничтожу. | ATTACK | repair_relationship | assert | ('ATTACK', 'repair_relationship', 'you', False, False) |
| Не зли меня, иначе будет хуже. | UNCERTAIN | intimidate | threat | ('UNCERTAIN', 'intimidate', '', False, True) |
| Твои дни сочтены. | DIALOGUE | repair_relationship | assert | ('DIALOGUE', 'repair_relationship', 'UNDEFINED', False, False) |
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
| А что? | UNCERTAIN | obtain_information | question | ('UNCERTAIN', 'obtain_information', '', False, False) |
| Почему? | UNCERTAIN | neutral | question | ('UNCERTAIN', 'neutral', '', False, False) |
| Нет, я не это имел в виду. | UNCERTAIN | neutral | reject | ('UNCERTAIN', 'neutral', '', False, False) |
| Так что? | UNCERTAIN | neutral | question | ('UNCERTAIN', 'neutral', '', False, False) |

