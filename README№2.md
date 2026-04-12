**ENIGMA — ПЕРЕСОБРАННАЯ ДОРОЖНАЯ КАРТА (v5.3 + актуальное состояние на 11 апреля 2026)**

### ФАЗА 1: Закрытие Контура (MVP) — **ПОЛНОСТЬЮ ЗАВЕРШЕНА**

**Статус:** ✅ 100 %  
**Что закрыто:**  
- DM — единственный LLM-вызов на тик.  
- npc_agent отключён для MAJOR NPC (DecisionResult[] идёт напрямую).  
- TEXT→ENTITY заблокирован (онтология + carried_objects).  
- LifeEngine.tick() подключён.  
- Фантомы при рестарте устранены.  
- Voice Constraints введены (но пока статично).

**Остался терпимый пробой MVP:** Пробой 4 (Intent Pool) — отложен до Фазы 2.

### ФАЗА 1.5: ЗАКРЫТИЕ УТЕЧКИ СМЫСЛА (Психологическая проекция) — **ЕДИНСТВЕННАЯ ТЕКУЩАЯ ПРИОРИТЕТНАЯ ФАЗА**

**Цель одной фразой:**  
Превращать `scores_trace` в одну короткую осмысленную строку (`psychological_projection`) и прокидывать её через всю цепочку до developer message в dm_agent.

**Это минимальное и единственное изменение, которое нужно сделать прямо сейчас.**  
Никаких новых классов, никаких FRAME_MAP, никаких динамических tone-генераторов.  
Просто один слой интерпретации.

**Конкретные шаги (строго по твоему описанию):**

**1.5.1 Добавить поле в SceneOutcomeBuilder**  
В `NpcOutcome` (или соответствующем датаклассе внутри SceneOutcome) добавить:
```python
psychological_state: str = ""   # 1–2 строки на русском
```

**Логика интерпретации (простая функция внутри builder):**
```python
def _build_psychological_projection(scores_trace: dict) -> str:
    # Пример:
    # fear=0.7, trust=-0.3, pride=0.8
    # → "напряжён, защищает территорию, не доверяет игроку"
    top_factors = sorted(scores_trace.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
    # ... простая шаблонная сборка или словарь-маппинг
    return "…одна строка…"
```

**Файл:** `verbalization/scene_outcome_builder.py`

**1.5.2 Прокинуть projection через DMFrame**  
- `SceneOutcome` → `DMFrame` получает это поле (уже существует путь).  
- Никаких изменений в адаптере — он уже умеет работать с новыми полями SceneOutcome.

**Файл:** `verbalization/scene_outcome_builder.py` (расширение DMFrame)

**1.5.3 Передать в dm_agent как developer message**  
В промпте dm_agent добавить блок:
```text
DEVELOPER:
Psychological projection for tavern_keeper_tornin:
напряжён, защищает территорию, не доверяет игроку
```

**Файл:** `agents/dm_agent.py` (только добавление в messages)

**1.5.4 Перехват в game_loop.py (уже почти готов)**  
Строка 606 уже содержит `decision_result`.  
Просто убедиться, что DecisionResult[] → SceneOutcomeBuilder.build() → DMFrame (с новым полем).

**Файл:** `game_loop.py` (минимальный патч, если нужно)

**decision_hub.py** — **не трогать** (уже отдаёт scores_trace).

**Архитектурное древо файлов, которые трогаем (только эти 3–4):**

```markdown
backend/
├── app/
│   ├── agents/
│   │   └── dm_agent.py                  # ← developer message + psychological_projection
│   │
│   └── services/
│       ├── game_loop.py                 # ← минимальный патч перехвата (если требуется)
│       │
│       ├── verbalization/
│       │   └── scene_outcome_builder.py # ← ГЛАВНЫЙ ФАЙЛ:
│       │       ├── NpcOutcome + psychological_state: str
│       │       ├── _build_psychological_projection(scores_trace)
│       │       └── DMFrame получает поле
```

**Чек-лист завершения Фазы 1.5 (выполнить за 1–2 сессии):**

- [ ] В `scene_outcome_builder.py` добавлено поле `psychological_state` и функция `_build_psychological_projection`
- [ ] DMFrame и SceneOutcome передают это поле
- [ ] В `dm_agent.py` projection попадает в developer message
- [ ] В логе появляется `[PROJECTION] напряжён, защищает территорию...`
- [ ] 5–10 реальных тиков → реплики Торнина и Люси перестают быть шаблонными (проверяем влияние на речь)

**Эффект после фикса:**  
DecisionHub влияет на речь NPC не на 35 %, а на ~85 %.  
NPC перестают быть функциями. Всё остальное (Gap System, Pressure, Memory) уже работает — просто теперь LLM видит причины, а не только результат.


### Технический долг (низкий приоритет, параллельно)
- Пробой 4 (Intent Pool)
- Центральный Math Config
- Локализация объектов



У тебя уже есть:

EmotionTag (8 состояний)
WillState (5 состояний)
intent
latent_signals
identity_integrity, resentment, dependency

Это уже сжатая психология.

Ты сейчас пытаешься поверх этого снова декодировать числа → текст.
Это дублирование слоя.

3. Правильная архитектура (проекция, а не генерация)

Тебе не нужен “генератор описаний”.
Тебе нужен projection layer:

continuous space (scores)
→ semantic axes
→ composition
→ короткая строка
4. Минимальная модель (реально достаточная)

Вместо 10000 описаний тебе нужно 4 оси:

1. Напряжение (arousal)
low / medium / high

Из:

stress
fear_delta
2. Вектор отношения к игроку
hostile
defensive
neutral
cooperative

Из:

trust
fear
intent_target
3. Контроль / стабильность
stable
pressured
unstable
breaking

Из:

identity_integrity
will_state
pressure_resistance
4. Поведенческий режим
passive
reactive
aggressive
deceptive

Из:

intent
behavior_mask
5. Теперь магия: композиция

Ты не пишешь 10000 строк.

Ты делаешь сборку из 4 компонентов:

[напряжение] + [отношение] + [контроль] + [режим]

Пример:

high + defensive + unstable + reactive
→ "напряжён, защищается, поведение нестабильно"

Другой:

medium + hostile + stable + aggressive
→ "раздражён, открыт к конфликту"
6. Сколько реально нужно описаний
Напряжение: 3 варианта
Отношение: 4
Контроль: 4
Режим: 4

Комбинаций: 3×4×4×4 = 192

НО
Ты не пишешь 192 строки.

Ты пишешь:

3 фразы напряжения
4 фразы отношения
4 фразы контроля
4 фразы поведения

И комбинируешь их.

Итого: ~15–20 атомов.

7. Почему это сильнее, чем LLM

Если ты отдашь это LLM:

он будет плавать
будет давать нестабильные формулировки
сломает повторяемость

А тебе нужно:

детерминированное семантическое ядро сцены

8. Где это должно жить

Не в DM. Не в промпте.

👉 В SceneOutcomeBuilder._build_npc_outcome()

Добавляешь:

psychological_state: str

И считаешь его через:

self._project_psych_state(decision, context)
9. Ключевой инсайт

Ты строишь не текст.

Ты строишь:

lossy compression психики → вектор для нарратива

DM потом не думает:

“что он чувствует?”

Он уже знает:

“он напряжён и защищается”

10. Альтернатива (если пойти глубже)

Можно вообще отказаться от строки и передавать:

psych_profile = {
    "arousal": "high",
    "stance": "defensive",
    "stability": "unstable",
    "mode": "reactive"
}

А текст собирать уже в DM prompt.

Правильная модель: не “описания”, а “векторы смыслов”
Вместо:
fear=0.7, trust=-0.3, pride=0.8
→ строка: "напряжён, защищает территорию, не доверяет"
Правильно:
vector state
   ↓
projection function (deterministic + weighted heuristics)
   ↓
semantic tags (3–7 штук максимум)
   ↓
LLM verbalization

Projection layer = разложение по осям

Например:

fear → threat sensitivity
trust → openness / hostility filter
pride → dominance / self-preservation bias

И дальше:

psychological_state = weighted_summary(axes)
5.2 Output не строка, а структура
psychological_state:
  - defensive_posture
  - low_trust
  - territorial_assertion

  Вариант B (правильный)
psychological_state: List[StateTag]

или ещё лучше:

projection_vector: Dict[str, float]
→ downstream: tag selector

Что действительно нужно добавить

Не psychological_state: str

А:

✔ Projection layer (минимальный контракт)
@dataclass
class PsychologicalProjection:
    threat_level: float
    openness: float
    dominance: float
    instability: float
    trust_bias: float
И функция:
NPCState → PsychologicalProjection → tags → LLM