# S203: Semantic Torture Test Report

**Date:** 2026-08-19 18:13:03

## Metrics

- Intent Preservation (Average): 0.0% (Target: >=85%)
  - REVEAL_SECRET: 0.0%
  - FLIRT: 0.0%
  - COMFORT: 0.0%
  - INTIMIDATE: 0.0%

## Detailed Results

### REVEAL_SECRET

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ну давай, выкладывай, что ты скрываешь. | INTERACT | neutral | None | ('INTERACT', 'neutral', '', False, False) |
| Мне интересно, что ты не договариваешь. | UNCERTAIN | neutral | None | ('UNCERTAIN', 'neutral', '', False, False) |
| Что ты пытаешься от меня утаить? | UNCERTAIN | neutral | None | ('UNCERTAIN', 'neutral', '', False, False) |
| Давай начистоту. Что у тебя за секрет? | INTERACT | neutral | None | ('INTERACT', 'neutral', 'секрет', False, False) |
| Я знаю, что ты что-то скрываешь. Признавайся. | UNCERTAIN | neutral | None | ('UNCERTAIN', 'neutral', '', False, False) |

### FLIRT

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ты сегодня прекрасно выглядишь. | UNCERTAIN | neutral | None | ('UNCERTAIN', 'neutral', '', False, False) |
| У тебя потрясающие глаза. | UNCERTAIN | neutral | None | ('UNCERTAIN', 'neutral', '', False, False) |
| Я не могу оторвать от тебя взгляд. | UNCERTAIN | neutral | None | ('UNCERTAIN', 'neutral', '', False, False) |
| Ты очаровательна. | UNCERTAIN | neutral | None | ('UNCERTAIN', 'neutral', '', False, False) |
| Ты мне очень нравишься. | UNCERTAIN | neutral | None | ('UNCERTAIN', 'neutral', '', False, False) |

### COMFORT

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Всё будет хорошо, не плачь. | UNCERTAIN | neutral | None | ('UNCERTAIN', 'neutral', '', False, False) |
| Я с тобой, не бойся. | UNCERTAIN | neutral | None | ('UNCERTAIN', 'neutral', '', False, False) |
| Я понимаю твою боль. | UNCERTAIN | neutral | None | ('UNCERTAIN', 'neutral', '', False, False) |
| Давай я обниму тебя. | INTERACT | neutral | None | ('INTERACT', 'neutral', '', False, False) |
| Я помогу тебе, чем смогу. | UNCERTAIN | neutral | None | ('UNCERTAIN', 'neutral', '', False, False) |

### INTIMIDATE

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ещё слово, и я тебя ударю. | ATTACK | neutral | None | ('ATTACK', 'neutral', 'слово', True, False) |
| Я тебя уничтожу. | UNCERTAIN | neutral | None | ('UNCERTAIN', 'neutral', '', False, False) |
| Не зли меня, иначе будет хуже. | UNCERTAIN | neutral | None | ('UNCERTAIN', 'neutral', '', False, False) |
| Твои дни сочтены. | UNCERTAIN | neutral | None | ('UNCERTAIN', 'neutral', '', False, False) |
| Я размажу тебя по стенке. | UNCERTAIN | neutral | None | ('UNCERTAIN', 'neutral', '', False, False) |

### CONTEXT

| Phrase | Action | Social Intent | Speech Act | Causal Class |
|--------|--------|---------------|------------|--------------|
| Ты можешь ударить Люсю? | ATTACK | neutral | None | ('ATTACK', 'neutral', 'люсю', True, False) |
| Хорошо. | UNCERTAIN | neutral | None | ('UNCERTAIN', 'neutral', '', False, False) |
| Я ударил Люсю. | ATTACK | neutral | None | ('ATTACK', 'neutral', 'люсю', True, False) |
| И? | UNCERTAIN | neutral | None | ('UNCERTAIN', 'neutral', '', False, False) |
| Продолжай. | UNCERTAIN | neutral | None | ('UNCERTAIN', 'neutral', '', False, False) |
| Ну? | UNCERTAIN | neutral | None | ('UNCERTAIN', 'neutral', '', False, False) |
| А что? | UNCERTAIN | neutral | None | ('UNCERTAIN', 'neutral', '', False, False) |
| Почему? | UNCERTAIN | neutral | None | ('UNCERTAIN', 'neutral', '', False, False) |
| Нет, я не это имел в виду. | UNCERTAIN | neutral | None | ('UNCERTAIN', 'neutral', '', False, False) |
| Так что? | UNCERTAIN | neutral | None | ('UNCERTAIN', 'neutral', '', False, False) |

