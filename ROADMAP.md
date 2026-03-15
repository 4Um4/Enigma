# ENIGMA — Дорожная карта реализации
### Версия 3.0 | Март 2026 | Полная последовательность

---

## 📍 ТОЧКА ОТСЧЁТА — Что уже работает

```
✅ start_enigma.bat — полный запуск (LLM + Backend + Frontend)
✅ llama-server — Qwen3.5-9B загружается, 65 tok/sec
✅ FastAPI — стартует, /api/health отвечает
✅ Frontend — index.html отображается на :3000
✅ Pre-flight тесты — 4/4 pass
✅ Выбор персонажа — сессия создаётся, heartbeat работает
✅ POST /api/game/action → LLM отвечает (первый ход работает!)
✅ VRAM мониторинг — без ложных утечек
✅ JSONL логи — структурированы, пишутся

⚠️  Ответ обрезается на 512 токенах (stop_type: limit)
⚠️  Локация всегда "unknown"
⚠️  Нет streaming — 8–30 сек тишины
⚠️  NPC/Rules агенты возвращают {} (модели не подключены)
⚠️  Только 1 игрок, смерть = конец
⚠️  Запускается через браузер, нужен .exe
```

---

# ═══════════════════════════════════════════════════
# ФАЗА 0 — СТАБИЛИЗАЦИЯ ТЕКУЩЕГО
# Срок: 2–3 дня | Приоритет: БЛОКИРУЮЩИЙ
# ═══════════════════════════════════════════════════

> Без этого всё остальное бессмысленно. Починить то что есть.

---

## 0.1. Исправить обрезание ответов

**Проблема:** `stop_type: "limit"` — модель упирается в 512 токенов, ответ обрывается на полуслове.

**Файл:** `backend/start_llm.bat`

- [ ] Найти строку `set "GPU_LAYERS=28"` → изменить на `set "GPU_LAYERS=33"` (все 32 слоя Qwen + output в VRAM)
- [ ] Добавить параметр `--n-predict 800` в запуск llama-server
- [ ] Добавить параметр `-b 512` (batch size для скорости prefill)
- [ ] Проверить: в логах должно быть `n_ctx_seq = 4096` вместо 2048

**Файл:** `backend/app/services/llm/llama_cpp_provider.py`

- [ ] Найти `GenerationParams` — изменить дефолт `max_tokens: 512` → `800`
- [ ] Для DM агента: добавить `max_tokens=1000` при создании параметров
- [ ] Для Rules агента: `max_tokens=300` (ему не нужно много)
- [ ] Для NPC агента: `max_tokens=400`

**Проверка:** Запустить игру, написать "подробно осмотрись вокруг и расскажи всё что видишь" — ответ должен не обрываться.

---

## 0.2. Исправить локацию "unknown"

**Проблема:** `campaign_state.json` не содержит `current_location` в `metadata`.

**Файл:** `backend/data/campaigns/demo-campaign/campaign_state.json`

- [ ] Открыть файл
- [ ] В секции `"metadata": {}` добавить:
```json
"metadata": {
  "current_location": "Таверна Серебряный Волк",
  "world_name": "Фандалин",
  "time_of_day": "вечер",
  "day": 1,
  "weather": "тихо, облачно",
  "season": "осень"
}
```

**Файл:** `backend/app/api/routes.py`

- [ ] Найти строку `location = campaign_state.metadata.get("current_location", "unknown")`
- [ ] Убедиться что читается правильно (баг мог быть и здесь)
- [ ] Добавить fallback: если None → `"Таверна Серебряный Волк"`

---

## 0.3. Зафиксировать рабочее состояние в git

- [ ] `git add -A`
- [ ] `git commit -m "feat: first working game loop — baseline"`
- [ ] Создать тег: `git tag v0.1-baseline`

**Зачем:** Это точка возврата. Если что-то сломается в следующих этапах — всегда можно откатиться.

---

## 0.4. Убрать мусорный код из orchestrator.py

**Проблема:** Несколько мест в коде используют несуществующие поля схем (уже исправлены, но нужна ревизия).

**Файл:** `backend/app/services/orchestrator.py`

- [ ] Убедиться что убран `initialize_models_stub()`
- [ ] Убедиться что `_build_shared_context` не обращается к `req.state`, `req.threat` и т.д.
- [ ] Убедиться что `_get_npc_importance` возвращает `{}`
- [ ] Убедиться что `_check_player_precondition` удалён из `run_turn`
- [ ] Прогнать игру — убедиться что `error.log` не создаётся

---

# ═══════════════════════════════════════════════════
# ФАЗА 1 — STREAMING И UI
# Срок: 1–1.5 недели | Приоритет: КРИТИЧЕСКИЙ
# ═══════════════════════════════════════════════════

> Игрок не должен смотреть в пустой экран 30 секунд. Это важнее всего остального.

---

## 1.1. SSE Streaming на бэкенде

### 1.1.1. Обновить llama_cpp_provider.py

**Файл:** `backend/app/services/llm/llama_cpp_provider.py`

- [ ] Добавить метод `stream_complete(prompt, params)`:
  - [ ] Отправить запрос с `"stream": true`
  - [ ] Читать chunked HTTP response построчно
  - [ ] Парсить каждую строку `data: {...}` → `chunk["content"]`
  - [ ] `yield` каждый токен вызывающему коду
  - [ ] Обработать `stop: true` в чанке — это конец стрима
  - [ ] Обработать ошибки соединения — yield сообщение об ошибке

```python
def stream_complete(self, prompt: str, params=None) -> Generator[str, None, None]:
    payload = {**self._build_payload(prompt, params), "stream": True}
    # ... HTTP request с итерацией по строкам ответа
    for line in response:
        if line.startswith(b"data: "):
            chunk = json.loads(line[6:])
            if chunk.get("stop"):
                return
            yield chunk.get("content", "")
```

### 1.1.2. Обновить dm_agent.py

**Файл:** `backend/app/agents/dm_agent.py`

- [ ] Добавить метод `stream_narrate(location, actions, ...)` → Generator
- [ ] Метод строит промпт (как `narrate`) но использует `stream_complete`
- [ ] Возвращает генератор токенов

### 1.1.3. Создать routes_stream.py

**Новый файл:** `backend/app/api/routes_stream.py`

- [ ] Импортировать `StreamingResponse` из fastapi
- [ ] Создать роут `POST /api/game/action/stream`
- [ ] Принимает тот же формат что `/api/game/action`
- [ ] Возвращает `StreamingResponse(generator, media_type="text/event-stream")`
- [ ] Формат SSE событий:
  - `data: {"type":"status", "text":"Мастер думает..."}\n\n`
  - `data: {"type":"token", "text":"Вы ", "n":1}\n\n`
  - `data: {"type":"token", "text":"видите", "n":2}\n\n`
  - `data: {"type":"npc", "data":[...]}\n\n`
  - `data: {"type":"done", "tokens":512, "ms":8200, "tps":65}\n\n`
- [ ] Добавить заголовки: `Cache-Control: no-cache`, `X-Accel-Buffering: no`
- [ ] Зарегистрировать роутер в `main.py`

### 1.1.4. Тест SSE через curl

```bash
curl -X POST http://127.0.0.1:8000/api/game/action/stream \
  -H "Content-Type: application/json" \
  -d '{"player":"Демеург","campaign":"demo-campaign","action":"осмотреться"}' \
  --no-buffer
```
- [ ] Убедиться что токены идут потоком, не одним блоком

---

## 1.2. Обновить index.html для streaming

**Файл:** `frontend/ui/index.html`

### 1.2.1. Заменить sendAction на streaming версию

- [ ] Вместо обычного `fetch` — использовать `fetch` + `response.body.getReader()`
- [ ] Читать стрим побайтово, буферизовать по `\n\n`
- [ ] При `type=token` — добавлять текст в текущее DM сообщение по одному токену
- [ ] Эффект "печатающей машинки" — текст появляется плавно

### 1.2.2. Метрики в реальном времени

- [ ] Добавить элемент `#stream-metrics` в DOM
- [ ] Обновлять каждый токен: `N токенов | X.Xs | NN tok/s`
- [ ] При `type=done` — показать финальную статистику 2 секунды, потом скрыть
- [ ] Добавить прогресс-бар (оценочный, на основе среднего токенов/сек)

### 1.2.3. Визуальные состояния

- [ ] `idle` — поле ввода активно, кнопка синяя
- [ ] `thinking` — "Мастер думает...", кнопка заблокирована, анимированные точки
- [ ] `streaming` — текст появляется, виден таймер и счётчик токенов
- [ ] `done` — разблокировать ввод, показать статистику

### 1.2.4. Fallback на обычный POST

- [ ] Если браузер не поддерживает ReadableStream → использовать старый POST
- [ ] Определяется автоматически через `typeof ReadableStream !== 'undefined'`

---

## 1.3. Улучшить UI под игровой опыт

### 1.3.1. Сообщения

- [ ] DM сообщения — разбить на абзацы (по `\n\n`)
- [ ] Добавить плавную анимацию появления каждого сообщения
- [ ] Сообщения с NPC реакциями — отдельный стиль, курсив, другой цвет
- [ ] Системные сообщения (смена модели, время) — мелким серым

### 1.3.2. Информация о персонаже

- [ ] HP бар обновляется после каждого ответа (если в ответе есть данные об уроне)
- [ ] Показывать локацию под именем персонажа
- [ ] Показывать день/время мира (из campaign_state)

### 1.3.3. История чата

- [ ] Прокрутка к последнему сообщению автоматически
- [ ] Кнопка "наверх" если история длинная
- [ ] Максимум 50 сообщений в DOM (старые удаляются чтоб не тормозить)

---

# ═══════════════════════════════════════════════════
# ФАЗА 2 — ACTION CLASSIFIER И PYTHON ДВИЖКИ
# Срок: 1.5–2 недели | Приоритет: ВЫСОКИЙ
# ═══════════════════════════════════════════════════

> Мозг системы — Python решает всё ДО того как LLM получит хоть один токен.

---

## 2.1. Action Classifier

**Новый файл:** `backend/app/services/action_classifier.py`

### 2.1.1. Типы действий

- [ ] Определить enum `ActionType`:
  - `COMBAT` — атакую, ударяю, стреляю, режу, бросаюсь, использую оружие
  - `SOCIAL` — говорю, спрашиваю, убеждаю, торгую, пугаю, соблазняю
  - `SOCIAL_MASS` — обращаюсь к толпе, кричу всем, говорю горожанам
  - `EXPLORE` — осматриваюсь, иду, исследую, ищу, открываю, вхожу
  - `CRAFT_USE` — использую предмет, создаю, применяю заклинание, достаю
  - `LORE_QUERY` — что такое, кто такой, расскажи о, объясни, откуда
  - `SANDBOX_MILD` — нестандартное но безобидное (пою, танцую, сплю)
  - `SANDBOX_SOCIAL` — нестандартное социальное (оскорбляю, провоцирую)
  - `SANDBOX_PHYSICAL` — нестандартное физическое (мочусь, дерусь грязно)
  - `ROMANCE` — ухаживаю, флиртую, влюбляюсь, провожу ночь
  - `CAPTURE` — беру в плен, связываю, захватываю, порабощаю
  - `FLEE` — убегаю, спасаюсь бегством, отступаю, сдаюсь
  - `LIFE_CHOICE` — хочу стать, покупаю дом, строю, женюсь
  - `CHAR_CREATE` — создание персонажа (начало игры)
  - `UNKNOWN` — fallback, передаётся DM с флагом

### 2.1.2. Словари ключевых слов

- [ ] Для каждого `ActionType` — список русских ключевых слов и корней
  - Учесть склонения: "атак" покрывает атакую/атакует/атаковать
  - Учесть синонимы: "ударяю", "бью", "режу" → COMBAT
- [ ] Приоритет типов (если несколько совпадений): COMBAT > CAPTURE > SOCIAL > EXPLORE

### 2.1.3. Метод classify(text) → ActionType

- [ ] Приводим к нижнему регистру
- [ ] Проверяем по словарям последовательно, по приоритету
- [ ] Возвращаем первый совпавший тип
- [ ] Логируем тип для отладки

### 2.1.4. Метод get_required_agents(action_type, npc_present) → list[str]

- [ ] COMBAT → ["rules", "dm"]
- [ ] SOCIAL + major NPC → ["npc_major", "dm"]
- [ ] SOCIAL_MASS или minor NPC → ["npc_mass", "dm"]
- [ ] EXPLORE, LORE_QUERY → ["dm"]
- [ ] CRAFT_USE → ["rules", "dm"] если магия, ["dm"] если физическое
- [ ] SANDBOX_* → ["dm"] с флагом unconventional
- [ ] CAPTURE → ["npc_major"/"npc_mass", "dm"]
- [ ] Все остальные → ["dm"]

### 2.1.5. Тесты

**Файл:** `backend/tests/test_action_classifier.py`

- [ ] Написать 20+ тест-кейсов:
  - "атакую гоблина мечом" → COMBAT
  - "осматриваюсь по сторонам" → EXPLORE
  - "говорю трактирщику привет" → SOCIAL
  - "расстёгиваю ширинку и" → SANDBOX_PHYSICAL
  - "хочу стать фермером" → LIFE_CHOICE
  - "убегаю от дракона" → FLEE

---

## 2.2. Physics Validator

**Новый файл:** `backend/app/services/game/physics_validator.py`

### 2.2.1. Список физических нарушений

- [ ] Определить `VIOLATION_RULES` — список кортежей `(паттерн, условие_обхода, объяснение)`:
  - Полёт без заклинания → проверяем has_spell("полёт")
  - Телепортация без заклинания → проверяем has_spell("перемещение")
  - "убиваю всех в городе одним ударом" → всегда отклонять
  - "поднимаю 500 кг" → проверяем Силу (Сила×15 = максимум в фунтах)
  - "вижу сквозь стену" → проверяем has_ability("темновидение", "истинное зрение")
  - "создаю из воздуха золото" → всегда отклонять (не магия иллюзий)
  - "мгновенно исцеляюсь полностью" → отклонять без заклинания/зелья

### 2.2.2. Метод validate(action, character, game_state) → ValidationResult

- [ ] Проверить все правила последовательно
- [ ] Если нарушение И нет обходного условия → ValidationResult(valid=False, reason=...)
- [ ] Если всё ок → ValidationResult(valid=True)

### 2.2.3. Интеграция в orchestrator

- [ ] Вызывать до Python Engines и LLM
- [ ] При valid=False → DM получает объяснение и говорит игроку почему нельзя
- [ ] Предлагать реалистичную альтернативу ("нельзя летать, но можно залезть")

---

## 2.3. Combat Math Engine

**Новый файл:** `backend/app/services/game/combat_math.py`

### 2.3.1. Броски кубиков

- [ ] `roll(n, sides)` → список бросков и сумма. Например `roll(2, 6)` → [3,5], sum=8
- [ ] `roll_with_advantage(sides)` → бросает два d20, берёт максимум
- [ ] `roll_with_disadvantage(sides)` → бросает два d20, берёт минимум
- [ ] `roll_saving_throw(character, ability)` → d20 + модификатор + мастерство если владение
- [ ] Записывать ВСЕ броски в лог (честность системы)

### 2.3.2. Атака

- [ ] `attack_roll(attacker, target)` → AttackResult:
  - Бросок d20
  - +модификатор_силы или ловкости (в зависимости от оружия)
  - +бонус_мастерства (если владение оружием)
  - Критическое попадание (d20=20) → двойные кубики урона
  - Критический промах (d20=1) → всегда промах
  - Сравнить с КД цели

### 2.3.3. Урон

- [ ] `damage_roll(weapon_dice, str_mod, critical=False)`:
  - Парсить строку кубиков "2d6+3" → кол-во, грани, бонус
  - При критическом — удвоить кубики (не бонус)
  - Вернуть: {dice_result, modifier, total, breakdown}

### 2.3.4. Инициатива

- [ ] `roll_initiative(character)` → d20 + модификатор ловкости
- [ ] `sort_initiative(combatants)` → отсортированный список
- [ ] При равенстве — игроки идут раньше монстров

### 2.3.5. Урон по NPC и HP

- [ ] `apply_damage(npc, damage)` → обновить `npc.hp`
- [ ] Если hp <= 0 → `npc.status = "incapacitated"` или `"dead"`
- [ ] `apply_healing(character, amount)` → обновить character.hp (не выше max_hp)
- [ ] Сохранить изменения в characters.json

### 2.3.6. Условия (Conditions D&D 5e)

- [ ] Список условий: отравлен, парализован, оглушён, ослеплён, испуган, схвачен
- [ ] Каждое условие — словарь эффектов:
  - отравлен: disadvantage на атаки и проверки
  - парализован: автокрит если атакуют в упор
- [ ] `apply_condition(character, condition, duration_rounds)`
- [ ] `tick_conditions(character)` — уменьшает длительность каждый ход

### 2.3.7. Формирование боевого контекста для DM

- [ ] После всех расчётов — собрать CombatContext:
  ```
  {
    "attack_roll": 17,
    "hit": true,
    "critical": false,
    "damage": 8,
    "target_hp_before": 15,
    "target_hp_after": 7,
    "breakdown": "d8(5) + Сила(+3) = 8"
  }
  ```
- [ ] DM получает это и только описывает — не считает

---

## 2.4. Sandbox Handler

**Новый файл:** `backend/app/services/game/sandbox_handler.py`

### 2.4.1. Обработка нестандартных действий

- [ ] Создать маппинг ActionType → обработчик:
  - `SANDBOX_PHYSICAL` → `handle_physical_sandbox`
  - `SANDBOX_SOCIAL` → `handle_social_sandbox`
  - `ROMANCE` → `handle_romance`
  - `CAPTURE` → `handle_capture`
  - `FLEE` → `handle_flee`
  - `LIFE_CHOICE` → `handle_life_choice`
  - `UNKNOWN` → `handle_dm_improvise`

### 2.4.2. handle_physical_sandbox (пример: мочится)

- [ ] Определить `social_violation_severity` (mild/medium/severe)
- [ ] `blossom_check` — бросок Харизмы DC 12/15/18 в зависимости от severity
- [ ] Рассчитать `reputation_impact` по формуле:
  - mild: -5...-10 к репутации в текущем месте
  - severe: -20...-50 + возможный бан из заведения
- [ ] Передать DM: тип нарушения + результат броска + последствия

### 2.4.3. handle_flee

- [ ] `flee_difficulty` зависит от:
  - Скорость игрока vs скорость врага
  - Местность (открытое поле / лес / узкий коридор)
  - Количество врагов
- [ ] Бросок Ловкости (Акробатика) DC = 10 + разница скоростей
- [ ] При успехе: combat_state = "fled", враги теряют игрока
- [ ] При провале: враг получает атаку по убегающему (атака возможности)
- [ ] Враги (NPC) НЕ стоят — LifeEngine двигает их независимо

### 2.4.4. handle_capture

- [ ] Проверить Силу игрока vs Силу NPC
- [ ] Бросок Атлетика vs Атлетика/Акробатика (оппозированный бросок)
- [ ] При успехе захвата:
  - NPC получает `chains` в visible_markers
  - npc.psyche.state → "coerced"
  - npc.flags.is_enslaved = true
  - karma["cruel"] += 15
  - Соответствующие фракции получают уведомление (через n тиков — ищут)
- [ ] Передать PsycheEngine для дальнейшего расчёта слома воли

### 2.4.5. handle_life_choice (игрок хочет стать фермером)

- [ ] Создать `LifeChoicePath` — особый режим кампании
- [ ] Переключить WorldScheduler в режим "fast_time" (1 тик = 1 игровой день)
- [ ] DM получает флаг `narrative_mode: "peaceful_life"`
- [ ] Сцены: покупка земли → постройка → посевы → отношения → дети
- [ ] Каждый тик — короткая DM виньетка о жизни персонажа

### 2.4.6. handle_romance

- [ ] Проверить текущий `social_stats.affection` NPC к игроку
- [ ] Бросок Харизма (Убеждение) DC = 20 - (affection / 5)
- [ ] Учесть нормы мира (кто с кем может, статусы)
- [ ] Развитие отношений — долгосрочный процесс:
  - знакомство → симпатия → дружба → любовь → партнёрство
  - Каждый этап требует серии успешных взаимодействий
- [ ] При рождении детей — создать нового minor NPC с relationship=["parent_X"]

---

## 2.5. Death Handler

**Новый файл:** `backend/app/services/game/death_handler.py`

### 2.5.1. Механика смерти персонажа

- [ ] При hp <= 0 → проверить "броски спасения от смерти" (D&D 5e):
  - 3 успеха → стабилизируется (1 hp, без сознания)
  - 3 провала → смерть
  - d20=20 → сразу 1 hp, просыпается
  - d20=1 → два провала сразу
- [ ] Состояния: `alive` / `unconscious` / `stable` / `dead`

### 2.5.2. Варианты после смерти

- [ ] Предложить партии выбор:
  - **Воскрешение:** если есть клирик/жрец/артефакт — возможно
  - **Новый персонаж:** пройти создание персонажа заново
  - **Продолжить без погибшего:** остальные играют дальше
  - **Войти позже:** новый персонаж появится по сюжету (встреча в следующей локации)
- [ ] Мёртвый игрок = наблюдатель (видит чат, не может действовать)

### 2.5.3. Реакция мира на смерть

- [ ] NPC которые знали персонажа — получают событие в `recent_events`
- [ ] Фракции персонажа — уменьшается их активный состав
- [ ] Враги — получают моральный бонус (+1 к броскам в эту битву)
- [ ] Союзники — бросок Мудрости DC 12 (моральный удар → disadvantage)
- [ ] Записать в историю кампании: кто, когда, от чего

---

# ═══════════════════════════════════════════════════
# ФАЗА 3 — NPC ПСИХОЛОГИЯ (Python движки)
# Срок: 2–3 недели | Приоритет: ВЫСОКИЙ
# ═══════════════════════════════════════════════════

> Это сердце проекта. NPC становятся людьми — без единого дополнительного токена от LLM.

---

## 3.1. Схема данных NPC

**Новый файл:** `backend/data/npcs/major_npcs.json`

### 3.1.1. Полная структура NPC JSON

- [ ] Определить JSON схему:

```json
{
  "id": "string — уникальный ID",
  "name": "string — имя",
  "tier": "major | minor | mass",

  "status_profile": {
    "freedom": "0–100 (0=раб, 100=дворянин)",
    "wealth": "0–100",
    "power": "0–100",
    "title": "string — динамически обновляется",
    "faction_rank": {"гильдия_воров": 3, "стража_города": 0}
  },

  "visible_markers": ["heavy_armor", "sword", "rags", "chains"],
  "hidden_truth": ["former_soldier", "spy"],

  "drives": {
    "control": "0.0–1.0",
    "significance": "0.0–1.0",
    "fear": "0.0–1.0",
    "desire": "0.0–1.0"
  },

  "psyche": {
    "willpower": "0–100",
    "stress": "0–100",
    "breakpoint": "0–100",
    "loyalty_true": "-100–+100",
    "loyalty_fake": "-100–+100",
    "state": "free|coerced|broken|loyal|deceptive",
    "trauma_flags": ["threatened", "witnessed_death"]
  },

  "social_stats": {
    "trust": "0.0–1.0",
    "affection": "0.0–1.0",
    "fear_of_player": "0.0–1.0",
    "debt": "integer — сколько должен/должны ему"
  },

  "relationships": {
    "player_name": "-100–+100",
    "other_npc_id": "-100–+100"
  },

  "routine": {
    "current": "string — текущее занятие",
    "mood": "neutral|happy|angry|scared|sad",
    "interrupted": "boolean",
    "next_task": "string",
    "schedule": {
      "06:00-18:00": "working",
      "18:00-22:00": "family_time",
      "22:00-06:00": "sleeping"
    }
  },

  "recent_events": [
    {"tick": 104, "event": "string", "impact": "anger|fear|joy"}
  ],

  "flags": {
    "has_gold": "boolean",
    "knows_secret": "boolean",
    "is_enslaved": "boolean",
    "planning_revenge": "boolean",
    "is_dead": "boolean"
  },

  "memory_trace": ["краткие факты о взаимодействиях с игроком"],
  "location": "string — ID локации",
  "hp": "0–100",
  "max_hp": "0–100",
  "combat_stats": {"ac": 12, "attack_bonus": 3, "damage": "1d6+1"}
}
```

### 3.1.2. Создать 5–7 базовых NPC для demo-campaign

- [ ] Торнин Серебряная Луна — хозяин таверны (major)
- [ ] Стражник Борко — стражник у ворот (minor)
- [ ] Лисья (Люся) — служанка в таверне (minor)
- [ ] Купец Горан — торговец на рынке (minor)
- [ ] Гильдийский вор (имя по сюжету) — major, скрытые цели
- [ ] 10 шаблонов для mass (горожанин, пьяный, солдат, крестьянин...)

**Новый файл:** `backend/data/npcs/mass_npc_templates.json`

- [ ] Каждый шаблон — минимальный набор: архетип, drives_preset, stress_baseline

---

## 3.2. NPCCognition

**Новый файл:** `backend/app/services/npc/npc_cognition.py`

### 3.2.1. Нормализация драйвов

- [ ] `normalize_drives(drives)` → сумма = 1.0
- [ ] `get_dominant_drive(drives)` → ключ с максимальным значением
- [ ] `get_speech_style(dominant_drive)` → строка-подсказка для промпта:
  - control: "говорит структурированно, предлагает план, избегает хаоса"
  - significance: "упоминает свой статус, обижается на неуважение"
  - fear: "осторожен, задаёт уточняющие вопросы, ищет выход"
  - desire: "энергичен, любопытен, готов рисковать"

### 3.2.2. process_player_action(npc, action, player, threat_level) → NPCContext

- [ ] Вычислить изменение доверия:
  - угроза → доверие -10...-30 (зависит от severity)
  - помощь → доверие +5...+15
  - взятка → доверие +5 если принял, +0 если отверг
  - агрессия → доверие -20
- [ ] Вычислить изменение страха:
  - угроза + оружие → fear_of_player += 0.1...0.3
  - помощь → fear_of_player -= 0.05
- [ ] Применить влияние репутации игрока:
  - высокая репутация "герой" → все NPC чуть дружелюбнее
  - низкая репутация "жестокий" → все NPC чуть напряжённее

---

## 3.3. PsycheEngine

**Новый файл:** `backend/app/services/npc/psyche_engine.py`

### 3.3.1. apply_stress(npc, amount) → NPCState

- [ ] Прибавить стресс: `npc.psyche.stress = min(100, stress + amount)`
- [ ] Проверить breakpoint:
  - если stress > breakpoint → сменить state на "broken"
  - записать в trauma_flags: "will_broken"
- [ ] Уменьшение стресса:
  - каждый тик в безопасности: -5
  - сон: -15
  - выпивка: -10 (но +риск random_event)

### 3.3.2. check_loyalty_break(npc) → bool

- [ ] Если state="broken" И loyalty_true < -50 → есть шанс предательства
- [ ] Шанс предательства = (abs(loyalty_true) - 50) / 50 * 100 %
- [ ] При предательстве: state="deceptive", флаг planning_revenge=True

### 3.3.3. get_behavior_hint(npc) → str

- [ ] На основе state + stress + dominant_drive → подсказка для промпта:
  - broken + fear → "говорит дрожащим голосом, соглашается на всё"
  - deceptive + control → "спокоен снаружи, ищет возможность предать"
  - loyal + significance → "горд что помогает, называет игрока господином"
  - free + desire → "открыт, любопытен, торгуется"

### 3.3.4. get_inner_thought(npc, context) → str

- [ ] Формирует текст внутренней мысли для Debug Mode:
```
[Внутренняя мысль: {npc.name}]
Доминирующий драйв: {dominant} ({value:.0%})
Стресс: {stress}/100 → {state}
Истинная лояльность: {loyalty_true} | Показная: {loyalty_fake}
Воспринимает игрока как: {perceived_status}
Скрытый план: {plan}
```

---

## 3.4. ThreatAssessor

**Новый файл:** `backend/app/services/npc/threat_assessor.py`

### 3.4.1. Оценка угрозы от игрока

- [ ] `assess_threat(player_markers, action_type, game_state)` → 0–100:
  - heavy_armor: +20
  - weapon_melee: +20
  - weapon_ranged: +15
  - combat_stance: +10
  - threatening_words: +30
  - known_kill (репутация): +20
  - friendly_posture: -20
  - unarmed: -10
- [ ] `get_threat_category(score)` → LOW | MEDIUM | HIGH | CRITICAL

### 3.4.2. Влияние угрозы

- [ ] HIGH угроза:
  - stress += 20...40 (зависит от willpower)
  - fear_of_player += 0.1...0.3
  - NPC с drives.fear > 0.5 → готовы говорить
- [ ] CRITICAL угроза:
  - stress += 40...60
  - проверка breakpoint
  - NPC с drives.survival > 0.5 → сломаются быстрее

---

## 3.5. PerceptionEngine

**Новый файл:** `backend/app/services/npc/perception_engine.py`

### 3.5.1. Определение воспринимаемого статуса игрока

- [ ] `assess_status(visible_markers)` → perceived_status (0–100):
  - royal_crown: +50
  - noble_clothes: +30
  - guild_badge[гильдия]: +20
  - heavy_armor: +10
  - rags: -30
  - chains: -50
  - slave_collar: -60
- [ ] `get_status_label(score)` → "нищий" | "простолюдин" | "уважаемый" | "благородный" | "правитель"

### 3.5.2. Социальные разрешения

- [ ] На основе perceived_status + npc.status_profile.freedom:
  - Раб с низким статусом НЕ может требовать, только просить
  - Дворянин может приказывать простолюдину
  - Простолюдин может торговаться с торговцем
- [ ] `get_social_permissions(player_status, npc)` → list[str]:
  - ["demand", "threaten", "negotiate", "beg", "charm", ...]

---

## 3.6. LifeEngine

**Новый файл:** `backend/app/services/npc/life_engine.py`

### 3.6.1. Расписание NPC

- [ ] `update_routine(npc, current_time)` → обновить npc.routine.current:
  - Сравнить current_time с расписанием
  - Если время изменилось → сменить активность
  - Случайное событие 5% шанс прерывает расписание
- [ ] `get_current_activity_description(npc)` → str для контекста DM:
  - "Торнин протирает кружки за стойкой"
  - "Стражник Борко дремлет у ворот"

### 3.6.2. Случайные события

- [ ] 5% шанс раз в тик:
  - Споры с другим NPC (-доверие между ними)
  - Потеря/находка предмета (меняет wealth)
  - Болезнь (stress +20, несколько тиков)
  - Хорошая новость (stress -15)
- [ ] Записывать в `npc.recent_events`

### 3.6.3. Регенерация стресса

- [ ] Каждый тик в безопасной зоне: stress -= 5
- [ ] Во время сна: stress -= 15
- [ ] При stress < 10 → mood = "happy", улучшается отношение к окружающим

---

## 3.7. KarmaEngine

**Новый файл:** `backend/app/services/npc/karma_engine.py`

### 3.7.1. Репутационные теги игрока

- [ ] Словарь `player.reputation = {"hero": 0, "cruel": 0, "generous": 0, ...}`
- [ ] `update_reputation(player, action_type, outcome)`:
  - убийство мирного → cruel += 10
  - помощь в беде → hero += 5
  - щедрое пожертвование → generous += 10
  - предательство → betrayer += 15
- [ ] `get_reputation_summary(player)` → список топ-3 репутационных тегов

### 3.7.2. Цепные реакции

- [ ] `schedule_delayed_event(trigger, delay_ticks, event_type)`:
  - Пример: угрозой получил информацию → через 5 тиков стражники ищут игрока
  - Пример: сломал NPC → через 10 тиков revenge_attempt
  - Пример: помог деревне → через 3 тика: положительный слух распространился
- [ ] LifeEngine проверяет scheduled_events каждый тик

### 3.7.3. Фракционная репутация

- [ ] `player.faction_rep = {"стража_города": 0, "гильдия_воров": 0}`
- [ ] Действия влияют на соответствующие фракции
- [ ] Фракции влияют на поведение их членов

---

## 3.8. SocialMobility

**Новый файл:** `backend/app/services/npc/social_mobility.py`

### 3.8.1. Динамические роли NPC

- [ ] NPC может менять роль на основе событий:
  - Крестьянин победил угрозу → стал "уважаемым"
  - Купец разорился → стал "нищим"
  - Захваченный стал рабом → "невольник"
- [ ] `update_title(npc)` → обновить npc.status_profile.title автоматически

### 3.8.2. Слом воли (Будет использован в capture flow)

- [ ] `apply_coercion_pressure(npc, pressure_type, duration)`:
  - Виды давления: угрозы, пытки, изоляция, голод
  - Каждое применение: stress += pressure_value
  - При stress > breakpoint → state = "broken"
  - Сломанный NPC: loyalty_fake = +50 (притворяется), loyalty_true = -100

---

## 3.9. Интеграция NPC движков в Orchestrator

**Файл:** `backend/app/services/orchestrator.py`

### 3.9.1. Новый метод _run_python_engines(req, action_type) → PythonEnginesResult

- [ ] Запустить ThreatAssessor → threat_level
- [ ] Определить затронутых NPC из локации
- [ ] Для каждого NPC:
  - PerceptionEngine → perceived_status
  - NPCCognition → context (драйвы, trust)
  - PsycheEngine → поведение (state, behavior_hint)
  - KarmaEngine → обновить репутацию
- [ ] CombatMath (если COMBAT) → combat_results
- [ ] SandboxHandler (если SANDBOX/ROMANCE/CAPTURE) → sandbox_result
- [ ] Вернуть структуру со всеми результатами

### 3.9.2. Передача результатов в LLM агентов

- [ ] Rules агент получает: action_type + character_stats + rules_context
- [ ] NPC агент получает: npc_state + behavior_hint + inner_thought + perceived_status
- [ ] DM агент получает: ВСЁ вышесказанное + combat_results + world_events

---

# ═══════════════════════════════════════════════════
# ФАЗА 4 — ПОДКЛЮЧЕНИЕ ВСЕХ 6 МОДЕЛЕЙ
# Срок: 1.5–2 недели | Приоритет: ВЫСОКИЙ
# ═══════════════════════════════════════════════════

> У нас есть все модели. Теперь каждая занимает своё место.

---

## 4.1. Обновить config.py — правильные пути к моделям

**Файл:** `backend/app/core/config.py`

- [ ] Установить правильный `agent_model_map`:
```python
agent_model_map = {
  "dm":        "qwen_9b",      # Qwen3.5-9B — нарратор
  "world":     "qwen_7b",      # Qwen2.5-7B — логика мира
  "npc_major": "npc_major",    # NPC-7B Q4 — важные NPC
  "npc_mass":  "npc_mass",     # NPC-7B IQ4 — толпа
  "rules":     "saiga",        # Saiga — правила D&D
  "memory":    "yandexgpt",    # YandexGPT — русская суммаризация
}
```
- [ ] Установить правильные `available_models` — пути к реальным файлам в `Models LLM/`
- [ ] VRAM бюджеты для каждой:
  - qwen_9b: 5300 MB, ctx=2048
  - qwen_7b: 4100 MB, ctx=2048
  - npc_major: 4000 MB, ctx=1024
  - npc_mass: 2500 MB, ctx=512
  - saiga: 4000 MB, ctx=1024
  - yandexgpt: 4500 MB, ctx=2048

---

## 4.2. Обновить промпты агентов

### 4.2.1. DM Agent промпт (Qwen3.5-9B)

**Файл:** `backend/app/agents/dm_agent.py`

- [ ] Заменить системный промпт на детальный:
```
Ты — Мастер Подземелий D&D 5e. Ведёшь живую, нелинейную историю.
Ты не решаешь механику — она уже посчитана. Ты ОПИСЫВАЕШЬ.
Пиши атмосферно, на русском, от второго лица ("Вы видите...").
Не нарушай физику мира. Не придумывай правила.
Заверши сцену вопросом или ситуацией требующей решения.
Объём ответа: 3–5 абзацев.
```
- [ ] Промпт пользователя — шаблон с плейсхолдерами для всех контекстов
- [ ] Секции: СЦЕНА | ДЕЙСТВИЯ | РЕЗУЛЬТАТЫ | NPC | СОБЫТИЯ МИРА

### 4.2.2. Rules Agent промпт (Saiga)

**Файл:** `backend/app/agents/rules_agent.py`

- [ ] Системный промпт:
```
Ты — движок правил D&D 5e. Отвечай ТОЛЬКО валидным JSON.
Никакого текста кроме JSON. Используй правила строго по книге.
```
- [ ] Промпт пользователя → всегда ожидать JSON ответ
- [ ] Парсить с fallback при json.JSONDecodeError:
  - Попробовать найти JSON в тексте через regex
  - Если не нашли → вернуть `{"roll_needed": false, "note": "parse_error"}`

### 4.2.3. NPC Major Agent промпт (NPC-7B Q4)

**Файл:** `backend/app/agents/npc_agent.py`

- [ ] Системный промпт включает всю психологию NPC (числа):
```
Ты — {npc_name}. {backstory_short}
Твоя психология: stress={stress}, drive={dominant_drive}, state={state}
Доверие к игроку: {trust}/100, Fear: {fear_of_player:.0%}
Видишь игрока как: {perceived_status}
Поведение сейчас: {behavior_hint}
Отвечай в JSON: {speech, inner_thought, action, trust_change, stress_change}
```
- [ ] Реализовать `npc_mass_agent.py` — более простой промпт, короткий ответ

### 4.2.4. Memory Agent промпт (YandexGPT)

**Файл:** `backend/app/agents/memory_manager_agent.py`

- [ ] Задача: суммаризировать сессию в 150–200 слов на русском
- [ ] Системный промпт:
```
Создай краткое резюме игровой сессии D&D.
Укажи: ключевые события, встреченные NPC, принятые решения, изменения в мире.
Максимум 200 слов. Только факты, без оценок. На русском.
```

---

## 4.3. VRAM-Aware Priority Queue

**Файл:** `backend/app/services/llm/provider_manager.py`

### 4.3.1. Приоритет выгрузки

- [ ] При нехватке VRAM — определить какую модель выгружать:
```python
AGENT_PRIORITY = {
  "dm": 1,         # никогда не выгружать раньше других
  "rules": 2,
  "npc_major": 3,
  "npc_mass": 4,
  "world": 5,
  "memory": 6      # выгружается первой
}
```
- [ ] Перед загрузкой — проверить `vram_monitor.is_safe_to_load(model_vram_mb)`
- [ ] Если не хватает → выгрузить модели с низким приоритетом пока не освободится

### 4.3.2. Быстрая проверка перед переключением

- [ ] Если запрошена та же модель что сейчас активна → НЕ переключать
- [ ] Логировать каждое переключение с delta времени

---

## 4.4. LLM Self-Debug Mode

**Файл:** `backend/app/services/error_interpreter.py`

### 4.4.1. Автоисправление JSON ошибок

- [ ] При `json.JSONDecodeError` от любого агента:
  - Сохранить сломанный ответ
  - Запросить Rules агента (Saiga): `"Исправь следующий невалидный JSON: {broken_response}"`
  - Попробовать спарсить исправленный ответ
  - Если снова ошибка → вернуть дефолтный пустой ответ

### 4.4.2. Retry с исправленным промптом

- [ ] При любой ошибке агента — одна повторная попытка с упрощённым промптом
- [ ] При второй ошибке — вернуть {} и продолжить pipeline

---

# ═══════════════════════════════════════════════════
# ФАЗА 5 — МУЛЬТИПЛЕЕР 1–8 ИГРОКОВ
# Срок: 2 недели | Приоритет: СРЕДНИЙ
# ═══════════════════════════════════════════════════

---

## 5.1. Turn Manager

**Новый файл:** `backend/app/services/game/turn_manager.py`

### 5.1.1. Структура данных

- [ ] `PlayerSlot`:
  - name: str
  - character_id: str
  - is_active: bool
  - acted_this_round: bool
  - last_action: str | None
  - last_action_timestamp: datetime | None

- [ ] `TurnManagerState`:
  - players: list[PlayerSlot]
  - current_player_idx: int
  - round_number: int
  - turn_number: int
  - phase: "player_input" | "dm_responding" | "combat_waiting_dice"
  - mode: "normal" | "combat" | "social" | "peaceful"

### 5.1.2. Логика очередей

- [ ] `add_player(name, character)` → добавить до 8 игроков
- [ ] `remove_player(name)` → удалить (если ушёл или умер)
- [ ] `current_player()` → PlayerSlot текущего
- [ ] `next_turn()` → переход к следующему, возврат нового текущего
- [ ] `all_players_acted()` → все ли походили в раунде
- [ ] `start_new_round()` → сбросить acted_this_round всем

### 5.1.3. Боевой режим (инициатива)

- [ ] `start_combat(participants)` → переключить mode="combat"
- [ ] Бросить инициативу всем (Python: d20 + ловкость)
- [ ] Отсортировать по инициативе (убывание)
- [ ] NPC тоже в очереди — их "ход" = автоматическое действие через PsycheEngine

### 5.1.4. Групповой ход (конец раунда)

- [ ] Когда все игроки подали действие → собрать `RoundActions`
- [ ] Передать DM агенту: все действия + все результаты
- [ ] DM описывает ВСЁ что произошло в раунде одним ответом

---

## 5.2. API для мультиплеера

**Файл:** `backend/app/api/routes.py`

### 5.2.1. Новые endpoints

- [ ] `POST /api/session/setup` — настройка сессии перед игрой:
  - Количество игроков
  - Имена и персонажи каждого
  - Режим очередей
- [ ] `GET /api/session/turn` — кто сейчас ходит:
  - `{current_player: "Арагорн", round: 2, all_players: [...]}`
- [ ] `POST /api/session/player/join` — присоединить нового игрока к существующей сессии
- [ ] `POST /api/session/player/leave` — игрок вышел

### 5.2.2. Обновить game/action

- [ ] Добавить проверку: действие принимается ТОЛЬКО от текущего игрока
- [ ] После успешного хода — автоматически вызвать `next_turn()`
- [ ] Отдавать в ответе `next_player_name` — чья теперь очередь

---

## 5.3. UI для мультиплеера

**Файл:** `frontend/ui/index.html`

### 5.3.1. Экран настройки сессии (перед игрой)

- [ ] Добавить начальный экран "Setup":
  - Выбор количества игроков (1–8)
  - Для каждого: ввод имени + выбор персонажа
  - Кнопка "Начать приключение"
- [ ] Или "Быстрый старт" — 1 игрок с Демеургом

### 5.3.2. Боковая панель с игроками

- [ ] Список всех игроков с HP барами
- [ ] Текущий ход — подсветка
- [ ] При не своём ходе — поле ввода заблокировано
- [ ] Статус: "Ваш ход!" | "Ход: Леголас" | "Мастер отвечает..."

### 5.3.3. Polling для синхронизации (раз в 2 сек)

- [ ] `GET /api/session/turn` — проверить кто сейчас ходит
- [ ] Обновить UI если изменилось
- [ ] (Позже заменить на WebSocket, пока достаточно polling)

---

# ═══════════════════════════════════════════════════
# ФАЗА 6 — СОЗДАНИЕ ПЕРСОНАЖА
# Срок: 1–1.5 недели | Приоритет: СРЕДНИЙ
# ═══════════════════════════════════════════════════

---

## 6.1. CharacterCreationWizard

**Новый файл:** `backend/app/services/game/character_creation.py`

### 6.1.1. Данные D&D 5e (константы)

- [ ] `HIT_DICE = {"воин": 10, "варвар": 12, "маг": 6, "жрец": 8, "плут": 8, ...}`
- [ ] `RACIAL_BONUSES = {"горный дварф": {"str":2,"con":2}, "высший эльф": {"dex":2,"int":1}, ...}`
- [ ] `CLASS_SAVING_THROWS = {"воин": ["str","con"], "маг": ["int","wis"], ...}`
- [ ] `CLASS_STARTING_EQUIPMENT = {"воин": ["chain_mail", "shield", "longsword"], ...}`
- [ ] `BACKGROUNDS = {"солдат": {...}, "преступник": {...}, "мудрец": {...}, ...}`
- [ ] `ALL_RACES` список из 9+ рас (PHB + Xanathar)
- [ ] `ALL_CLASSES` список из 12 классов

### 6.1.2. Методы генерации

- [ ] `roll_ability_scores()` → список из 6 чисел (4d6 drop lowest)
- [ ] `get_standard_array()` → [15, 14, 13, 12, 10, 8]
- [ ] `point_buy_calculator(assignments)` → проверить не превышен ли бюджет 27
- [ ] `apply_racial_bonuses(scores, race)` → scores + бонусы расы
- [ ] `calculate_all_stats(character)` → вычислить ВСЁ производное:
  - модификаторы всех 6 характеристик
  - HP первого уровня (max hit_die + con_mod)
  - КД без доспехов (10 + dex_mod)
  - бонус мастерства (+2 на 1–4 уровне)
  - спасброски класса
  - инициатива (dex_mod)
  - скорость (30 фут, дварфы 25)

### 6.1.3. Состояние мастера создания

- [ ] `CreationState`: шаг + уже введённые данные
  - Шаги: race → class → ability_scores → method → distribute → background → equipment → confirm
- [ ] `CreationState.to_character()` → преобразовать в полный `CharacterSheet`

### 6.1.4. API endpoint

- [ ] `POST /api/character/create/start` → начать сессию создания
- [ ] `POST /api/character/create/step` → следующий шаг:
  - Принимает: `{step_id, data}`
  - Возвращает: `{next_step, prompt_for_dm, computed_values}`
- [ ] `POST /api/character/create/finish` → сохранить персонажа

---

## 6.2. DM ведёт создание через диалог

**Файл:** `backend/app/agents/dm_agent.py`

### 6.2.1. Режим создания персонажа

- [ ] Специальный системный промпт для char_create:
```
Ты ведёшь создание персонажа D&D 5e. Задавай вопросы по шагам.
После каждого ответа игрока показывай что это означает механически.
Будь тёплым и интересным — это первое впечатление игрока от игры.
Python уже посчитал все числа — ты только рассказываешь их красиво.
```
- [ ] DM получает от wizard: какой шаг + что уже выбрано + подсказки
- [ ] DM задаёт следующий вопрос и объясняет предыдущий выбор

### 6.2.2. Обработка нестандартного создания

- [ ] Если игрок хочет нестандартную расу (не из списка) → DM объясняет доступные
- [ ] Если игрок хочет нестандартный класс → подбирает ближайший
- [ ] Если игрок просит "самый сильный персонаж" → DM объясняет что "силы" бывают разные

---

# ═══════════════════════════════════════════════════
# ФАЗА 7 — СИСТЕМА ПАМЯТИ (4 УРОВНЯ)
# Срок: 2 недели | Приоритет: СРЕДНИЙ-ВЫСОКИЙ
# ═══════════════════════════════════════════════════

---

## 7.1. Memory Manager

**Новый файл:** `backend/app/services/memory/memory_manager.py`

### 7.1.1. Бюджет токенов

- [ ] Константы для каждого агента:
  - dm_context_budget: 1200 токенов
  - rules_context_budget: 400 токенов
  - npc_context_budget: 600 токенов
  - memory_summarize_budget: 3000 токенов (YandexGPT суммаризирует много)
- [ ] `estimate_tokens(text)` → грубая оценка: len(text) / 4 (примерно для русского)

### 7.1.2. build_context(campaign_id, agent_type, location) → str

Алгоритм:
- [ ] 1. Добавить локацию + время + погоду (~100 токенов)
- [ ] 2. Добавить кто присутствует в локации (~80 токенов)
- [ ] 3. Если DM → добавить краткое резюме кампании (~250 токенов)
- [ ] 4. Добавить недавние события (last N пока не достигнем бюджета):
  - Начать с самых свежих
  - Каждое событие ~50–100 токенов
  - Стоп если бюджет исчерпан
- [ ] 5. Если запрос lore → добавить RAG результат (~200 токенов)
- [ ] 6. Вернуть собранный контекст

### 7.1.3. summarize_session(campaign_id) → str

- [ ] Читаем session_memory — последние 50 событий
- [ ] Форматируем как "текст сессии"
- [ ] Отправляем YandexGPT: "Создай резюме в 200 слов"
- [ ] Сохраняем резюме в `campaign_memory_{id}.jsonl` с тегом `type=summary`
- [ ] Вызывать автоматически в конце каждой сессии (при закрытии)

---

## 7.2. Улучшить LayeredMemory

**Файл:** `backend/app/services/memory/memory.py`

### 7.2.1. Новые методы

- [ ] `read_npc_importance(campaign_id, location)` → словарь {npc_id: важность}
  - Читать из npc_memory + campaign_memory
  - Возвращать NPC которые часто упоминаются в локации
- [ ] `write_npc_interaction(campaign_id, npc_id, interaction)` → сохранить взаимодействие
- [ ] `get_recent_npc_memory(npc_id, limit)` → последние взаимодействия с конкретным NPC
- [ ] `write_world_event(world_id, event)` → записать мировое событие
- [ ] `get_location_events(location, limit)` → события в конкретной локации

### 7.2.2. Оптимизация чтения

- [ ] Кэшировать последнее чтение на 30 сек (file не меняется так часто)
- [ ] При записи — инвалидировать кэш
- [ ] Ограничить размер файлов: при > 1000 записей → архивировать старые

---

## 7.3. NPC memory_trace

- [ ] Каждый major NPC имеет `memory_trace: []` в JSON
- [ ] После каждого взаимодействия — добавить запись:
  ```json
  {"tick": 110, "player": "Арагорн", "action": "threatened", "outcome": "told secret"}
  ```
- [ ] Максимум 20 записей на NPC — старые удаляются
- [ ] `memory_trace` передаётся в NPC промпт как "помнит про игрока"

---

# ═══════════════════════════════════════════════════
# ФАЗА 8 — АНАЛИТИКА И СТАТИСТИКА
# Срок: 1 неделя | Приоритет: НИЗКИЙ-СРЕДНИЙ
# ═══════════════════════════════════════════════════

---

## 8.1. PlayerAnalytics

**Новый файл:** `backend/app/services/analytics/player_stats.py`

### 8.1.1. Что записываем

- [ ] Для каждого action записать:
  - timestamp, player_name, action_type, action_text[:50]
  - outcome: {hit, damage, result, npc_killed}
  - gold_delta, hp_delta
  - was_unconventional: bool

### 8.1.2. Агрегированная статистика

- [ ] `total_actions` — общее число действий
- [ ] `actions_by_type` — разбивка по типам
- [ ] `kills_total` — убито существ
- [ ] `kills_by_type` — разбивка (гоблины, стражники, боссы...)
- [ ] `damage_dealt_total`, `damage_taken_total`
- [ ] `gold_earned`, `gold_spent`, `gold_net`
- [ ] `persuasions_success`, `persuasions_failed`
- [ ] `deaths` — сколько раз умирал
- [ ] `unconventional_actions_count` + список самых странных
- [ ] `avg_reputation_all_factions`
- [ ] `npc_relationships` — с кем подружился/поссорился
- [ ] `session_count`, `total_playtime_minutes`
- [ ] `favorite_location` — где проводит больше всего времени
- [ ] `quests_completed`, `quests_failed`, `quests_abandoned`

### 8.1.3. API

- [ ] `GET /api/analytics/{campaign_id}/{player_name}` → полная статистика
- [ ] `GET /api/analytics/{campaign_id}/leaderboard` → сравнение игроков (мультиплеер)

### 8.1.4. UI — итоги сессии

- [ ] Автоматически показывать после каждой сессии
- [ ] Карточка с топ-5 фактами о сессии
- [ ] Самое странное действие — выделить особо

---

# ═══════════════════════════════════════════════════
# ФАЗА 9 — МИРОВОЙ СИМУЛЯТОР
# Срок: 1.5 недели | Приоритет: СРЕДНИЙ
# ═══════════════════════════════════════════════════

---

## 9.1. WorldScheduler

**Файл:** `backend/app/services/world_scheduler.py` (уже частично есть)

### 9.1.1. World tick каждые 15 минут реального времени

- [ ] Фоновая задача `asyncio` — проверять раз в минуту реального времени
- [ ] Если прошло 15 минут → запустить world_tick()
- [ ] `world_tick(world_id)`:
  - Обновить время дня (15 мин реал = 1 час игровой)
  - Обновить расписания всех NPC через LifeEngine
  - Проверить scheduled_events → выполнить те что наступили
  - Проверить random_events (5% на каждый NPC)
  - Обновить погоду (небольшой рандом)
  - Запустить WorldSimAgent (Qwen2.5-7B) → получить описание событий мира

### 9.1.2. World Sim Agent (Qwen2.5-7B)

**Файл:** `backend/app/agents/world_sim_agent.py`

- [ ] Системный промпт: "Ты симулятор мира D&D. Ты НЕ ведёшь диалог. Ты описываешь события фона."
- [ ] Промпт пользователя: текущее состояние мира + что изменилось за тик
- [ ] Ожидает JSON: `{events: [...], npc_movements: [...], rumors: [...]}`
- [ ] Результат сохраняется в world_hidden_events → DM видит при следующем запросе

### 9.1.3. Слухи и информация

- [ ] Слухи = события которые игрок МОЖЕТ узнать у NPC
- [ ] NPC знают слухи из своего круга общения
- [ ] При SOCIAL действии с NPC → есть шанс услышать слух
- [ ] Слухи хранятся в `world_rumors_{world_id}.jsonl`

---

# ═══════════════════════════════════════════════════
# ФАЗА 10 — RAG ПО PDF КНИГАМ
# Срок: 2 недели | Приоритет: СРЕДНИЙ
# ═══════════════════════════════════════════════════

---

## 10.1. Индексация PDF при первом запуске

**Новый файл:** `backend/app/services/memory/knowledge_base.py`

### 10.1.1. Первый запуск — индексация

- [ ] Проверить: существует ли `data/knowledge_db/` с индексом
- [ ] Если нет → начать индексацию (занимает 5–15 минут при первом запуске)
- [ ] Показывать прогресс в UI: "Индексирую книги D&D... 3/7"
- [ ] После окончания → готово, сохранено

### 10.1.2. Индексация PDF

- [ ] `index_pdf(pdf_path)`:
  - Читать через `pypdf.PdfReader`
  - Разбить текст на чанки по ~300 слов с перекрытием 50 слов
  - Добавить метаданные: источник PDF, страница, номер чанка
- [ ] Выбор векторной базы:
  - **ChromaDB** — проще, подходит для 1–10 PDF
  - **FAISS** — быстрее при поиске, сложнее настройка
  - Рекомендация: ChromaDB на первом этапе

### 10.1.3. Поиск по запросу

- [ ] `search(query, n_results=3)` → список релевантных фрагментов
- [ ] Вызывать при LORE_QUERY action_type
- [ ] Добавлять в контекст DM: "Из книги: ..."

### 10.1.4. Без LLM эмбеддингов (на первом этапе)

- [ ] ChromaDB поддерживает встроенный эмбеддер (all-MiniLM-L6-v2)
- [ ] Он маленький (~90 MB) и работает на CPU
- [ ] Не требует GPU, не занимает VRAM

---

# ═══════════════════════════════════════════════════
# ФАЗА 11 — ОТВЯЗКА ОТ БРАУЗЕРА (.EXE)
# Срок: 2 недели | Приоритет: СРЕДНИЙ
# ═══════════════════════════════════════════════════

---

## 11.1. Launcher

**Новый файл:** `launcher.py`

### 11.1.1. Структура

- [ ] Запустить llama-server subprocess с правильными параметрами
- [ ] Запустить FastAPI в daemon thread
- [ ] Дождаться готовности портов 8080 и 8000
- [ ] Создать webview окно: `webview.create_window(...)`
- [ ] Запустить `webview.start()`
- [ ] При закрытии окна — `sys.exit(0)` (subprocess daemon завершится сам)

### 11.1.2. Зависимости

- [ ] Добавить в requirements.txt: `pywebview>=4.0`
- [ ] pywebview использует WebView2 (встроен в Windows 11) — не нужно устанавливать

### 11.1.3. Экран загрузки

- [ ] Пока backend не готов — показать заглушку в webview:
  - "Загрузка модели... (это займёт 10–30 секунд)"
  - Анимированный прогресс (без реального числа, просто видно что работает)
- [ ] После готовности — redirect на основной UI

### 11.1.4. Упаковка в .exe

- [ ] Создать `enigma.spec` для PyInstaller:
  - Включить все Python файлы backend
  - Включить frontend/ui/
  - НЕ включать модели и llama-server (они слишком большие)
  - llama-server и модели — рядом с .exe в папке
- [ ] Сборка: `pyinstaller enigma.spec`
- [ ] Финальная структура дистрибутива:
```
Enigma/
├── Enigma.exe              ← запускать сюда
├── Models LLM/             ← модели (устанавливаются отдельно)
│   ├── llama/
│   │   └── llama-server.exe
│   └── *.gguf
└── data/                   ← сохранения игры
```

---

## 11.2. Debug Panel в UI

**Файл:** `frontend/ui/index.html`

### 11.2.1. Добавить Debug Mode (F12)

- [ ] Кнопка или F12 → переключает режим
- [ ] Debug панель справа/снизу:
  - Текущая активная модель
  - VRAM usage (обновляется каждые 5 сек через `/api/debug/vram`)
  - Последний агент + время ответа
  - Тип последнего действия (COMBAT / SOCIAL / ...)
  - Состояние активных NPC (stress, state)
  - Количество токенов в последнем ответе
- [ ] В нормальном режиме — панель скрыта

### 11.2.2. Inner Thought toggle для NPC

- [ ] Кнопка "Показать мысли NPC" (только в Debug Mode)
- [ ] При включении — показывать inner_thought под репликой NPC
- [ ] Отображать числа: stress, state, dominant_drive

---

# ═══════════════════════════════════════════════════
# ФАЗА 12 — ПОЛНЫЕ ПРАВИЛА D&D 5e
# Срок: 3–4 недели | Приоритет: НИЗКИЙ-СРЕДНИЙ
# ═══════════════════════════════════════════════════

---

## 12.1. Spell System

**Новый файл:** `backend/app/services/game/spell_system.py`

### 12.1.1. Базы данных заклинаний

- [ ] Словарь `SPELLS` — все заклинания PHB:
  - name, level, school, casting_time, range, components
  - effect (описание), damage_dice (если есть), save_ability (если есть)
  - concentration: bool

### 12.1.2. Ячейки заклинаний

- [ ] В CharacterSheet добавить `spell_slots: {1: 4, 2: 3, ...}`
- [ ] `use_spell_slot(character, level)` → уменьшить ячейку
- [ ] `check_has_slot(character, level)` → есть ли ячейка
- [ ] При длинном отдыхе → восстановить все ячейки

### 12.1.3. Разрешение заклинания

- [ ] При `CRAFT_USE` с упоминанием заклинания:
  - Найти заклинание в базе
  - Проверить есть ли у персонажа (известные заклинания)
  - Проверить наличие ячейки нужного уровня
  - Рассчитать эффект (урон/исцеление/эффект)
  - Передать DM: название + механический результат

---

## 12.2. Saving Throws и Skill Checks

- [ ] `skill_check(character, skill, dc)` → бросок характеристики + мастерство:
  - Список навыков и их характеристик: Атлетика→Сила, Скрытность→Ловкость...
  - d20 + модификатор + (бонус мастерства если есть владение)
  - Сравнить с DC → успех или провал
- [ ] `saving_throw(character, ability, dc)`:
  - d20 + модификатор + (бонус мастерства если spellcasting class)
  - Передать DM: результат + последствия

---

# ═══════════════════════════════════════════════════
# ВНУТРЕННИЕ УЛУЧШЕНИЯ (параллельно со всеми фазами)
# ═══════════════════════════════════════════════════

---

## A. Кодировка и Windows совместимость

- [ ] Все новые файлы — `# -*- coding: utf-8 -*-` в начале
- [ ] `chcp 65001` во всех BAT файлах (уже есть, проверить)
- [ ] Пути к файлам — через `Path` не через конкатенацию строк
- [ ] Тестировать запуск с русскими именами пользователей Windows

---

## B. Логирование

- [ ] Каждое действие Python движков — в JSONL с timestamp
- [ ] Каждое переключение модели — в JSONL
- [ ] Каждый NPC state change — в JSONL
- [ ] Каждый бросок кубика — в JSONL (честность системы)
- [ ] Rotation логов: раз в день новый файл, старые > 7 дней — удалять

---

## C. Тестирование

- [ ] После каждой фазы — добавить тесты:
  - `test_action_classifier.py` — после Фазы 2
  - `test_combat_math.py` — после Фазы 2
  - `test_npc_psyche.py` — после Фазы 3
  - `test_turn_manager.py` — после Фазы 5
  - `test_character_creation.py` — после Фазы 6
  - `test_memory_manager.py` — после Фазы 7
- [ ] `test_startup_checks.py` обновлять при каждом новом сервисе

---

## D. Оптимизация производительности

- [ ] Кэширование NPC состояний в RAM (не читать JSON каждый ход)
- [ ] Кэширование world_state в RAM
- [ ] Предзагрузка DM модели при старте (она используется каждый ход)
- [ ] Профилирование: замерять время каждого Python движка
- [ ] Цель: Python engines < 50ms суммарно

---

# ═══════════════════════════════════════════════════
# ИТОГОВЫЙ ПЛАН ПО СРОКАМ
# ═══════════════════════════════════════════════════

| Фаза | Название | Срок | Результат для игрока |
|---|---|---|---|
| **0** | Стабилизация | **2 дня** | Ответ не обрезается, локация не "unknown" |
| **1** | Streaming + UI | **1.5 нед** | Текст появляется плавно, таймер, метрики |
| **2** | Action Classifier + Python движки | **2 нед** | Физика мира, бой считается правильно |
| **3** | NPC психология | **2–3 нед** | NPC реагируют как люди |
| **4** | Все 6 моделей | **1.5 нед** | Saiga проверяет правила, NPC-7B говорит за NPC |
| **5** | Мультиплеер | **2 нед** | До 8 игроков за одним ПК по очереди |
| **6** | Создание персонажа | **1 нед** | DM ведёт диалог, Python считает |
| **7** | Система памяти | **2 нед** | История помнится, используется правильно |
| **8** | Аналитика | **1 нед** | Статистика и итоги сессии |
| **9** | World Simulator | **1.5 нед** | Мир живёт независимо |
| **10** | RAG по PDF | **2 нед** | Знает содержимое книг D&D |
| **11** | .EXE файл | **2 нед** | Запускается как приложение, без браузера |
| **12** | Полные правила D&D | **3 нед** | Заклинания, сохранения, все механики |

**До минимально играбельной версии (Фазы 0–4):** ~2 месяца

**До полноценного релиза (все фазы):** ~5–6 месяцев

---

## 🏆 Определение "готово к первой реальной сессии"

Версия `v1.0-playable` достигается после Фаз 0–5:

```
✅ Игра запускается одним .bat без ошибок
✅ 1–4 игрока могут играть по очереди
✅ LLM отвечает стримингом, первый токен < 1 сек
✅ Бой считается математически верно
✅ NPC помнят и реагируют психологически
✅ Любое (даже странное) действие обрабатывается
✅ Смерть не конец игры
✅ Мир хотя бы немного живёт между ходами
✅ Локация и время мира работают корректно
✅ Персонаж можно создать через диалог с DM
```

---

## 📌 Принципы которые никогда не нарушаем

1. **Python считает, LLM рассказывает** — ни один LLM не принимает игровых решений
2. **max_loaded = 1** — одна модель в VRAM, строго
3. **Нет запрещённых действий** — есть последствия
4. **characters.json = источник истины** — LLM не меняет напрямую
5. **Мир живёт** — NPC движутся, события происходят без игрока
6. **Честность бросков** — все кубики логируются, никакого "подкручивания"
7. **Windows 11 + русский** — тестировать каждую фичу на реальном железе
