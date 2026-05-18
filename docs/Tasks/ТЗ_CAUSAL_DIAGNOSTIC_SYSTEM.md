path: /project/docs/Tasks/ТЗ_CAUSAL_DIAGNOSTIC_SYSTEM.md
Назначение: Техническое задание на систему каузальной диагностики (CDS) для обеспечения наблюдаемости LLM-архитекторов.
Зависимости: game_launcher.py, diagnostics/, reports/
Основные сущности: CausalObserver, LAST_SESSION.md, PatternRegistry, CausalChainBuilder

# ТЗ: ENIGMA Causal Diagnostic System (CDS)

**Архитектурное решение:** [ADR-059](../audits/ADR-059_IMPACT.md)
**Статус:** В разработке (Спринт 39).  
**Приоритет:** Параллельная разработка — не блокирует игровые спринты.  
**Принцип:** Встраивается в `game_launcher.py`. Запускается при каждом старте игры. Пишет один markdown-файл с тремя секциями. Читается LLM, не человеком.

---

## 1. Проблема которую решаем

В проекте работают три параллельных LLM-архитектора в разных браузерных окнах:

- **Архитектор #1** — чистит код, патчит файлы, архитектурные фиксы
- **Архитектор #2** — UI/frontend, рендеринг, визуальные элементы
- **Архитектор #3** — симуляция, мозги NPC, каузальные разрывы

Каждый видит только свой кусок реальности. Нет общего источника истины о состоянии системы на момент начала сессии.

**Реальная цена этого:** В Спринте 34 потребовалось 15+ ходов чтобы установить что Тень не идёт к игроку из-за каскада: `load_editor_json` не фильтрует по `location_id` → узел `bed` не найден → SceneChange не создан → traversal нет → координаты None → lerp не работает. Каждый слой открывался отдельно через PowerShell.

**Решение:** Один файл `LAST_SESSION.md` с тремя секциями. Каждый архитектор читает свою секцию и сразу знает состояние системы + что делают два других.

---

## 2. Главный принцип: файл читает LLM, не человек

Формат оптимизирован для LLM-контекста:
- **Конкретные факты** вместо описаний ("узел 'bed' не найден" а не "проблема с пространством")
- **Готовые PowerShell команды** для верификации каждой проблемы
- **Файл + строка** для каждого нарушения — LLM сразу знает куда смотреть
- **Нет лирики** — только структурированные данные
- **Секция идентификации** в начале — LLM сам определяет кто он

---

## 3. Структура LAST_SESSION.md

```markdown
# ENIGMA Session State — {date} {time}

## ИДЕНТИФИКАЦИЯ АРХИТЕКТОРА
Прочитай эту секцию первой. Определи кто ты по задаче сессии:

- Если ты работаешь с Python-кодом, патчами, архитектурой, багами симуляции → ты **Архитектор #1 или #3**
- Если ты работаешь с UI, pygame, рендерингом, визуальными элементами → ты **Архитектор #2**
- Если ты работаешь с NPC-поведением, тиками, давлением, решениями → ты **Архитектор #3**

Прочитай свою секцию (#1, #2 или #3). Секцию других архитекторов читай только строку "Сейчас делает:" — чтобы не конфликтовать по файлам.

---

## #1 — АРХИТЕКТОР КОДА (патчи, файлы, архитектура)

### Сейчас делает:
[последнее зафиксированное действие из MUTATIONS.md]

### Активные баги требующие патча:
- **[КРИТИЧНО]** `backend/app/services/spatial/graph_compiler.py` ~строки 225-240
  load_editor_json не фильтрует по location_id → берёт первый JSON с nodes
  Фикс: добавить `data.get("location_id") == location_id` в условие
  Проверка: `python -c "from app.services.spatial.graph_compiler import load_editor_json; r=load_editor_json('Open_road','inn_rooms'); print(list(r.get('nodes',{}).keys()) if r else None)"`
  Ожидаем: ['bed_1', 'bed_2', 'bed_3', 'bed_4', 'bed', 'room_center', 'door']

- **[СРЕДНИЙ]** `backend/app/services/scene_state_manager.py:1116`
  LOD1 macro-movement: все NPC с target="bed" получают одинаковый центр узла
  Фикс: добавить random.uniform(-0.4, 0.4) offset к to_xy (аналогично LOD0 в movement_engine.py:88-103)

### Последние изменения (из MUTATIONS.md):
[автозаполнение из git log --oneline -5 или MUTATIONS.md]

### Файлы с активными TODO:
[Select-String по всем .py на паттерн "TODO|FIXME|HACK|deprecated"]

### Архитектурные нарушения обнаруженные за сессию:
[паттерны из логов: прямая мутация state, bypass EventBus и т.д.]

---

## #2 — АРХИТЕКТОР UI (pygame, рендеринг, визуал)

### Сейчас делает:
[последнее зафиксированное действие]

### Состояние рендеринга (из последней сессии игры):
- NPC с координатами: {N из 6}
- NPC с активным traversal (lerp работает): {список}
- NPC на нулях (не рендерятся корректно): {список}
- active_traversals в WorldSnapshot: {пусто / N записей}

### Визуальные аномалии обнаруженные за сессию:
- NPC сливаются в одной точке: {да/нет, кто}
- Телепортации (скачок > 3 тайла за тик): {список NPC}
- Спрайты без позиции (x=None): {список}

### Файлы фронтенда (актуальное состояние):
- `frontend/game_screen.py` — последнее изменение: {дата, что}
- `frontend/scene_renderer.py` — последнее изменение: {дата, что}

### Что НЕ трогать (сейчас меняет другой архитектор):
[файлы из секции #1 и #3 которые в работе]

---

## #3 — АРХИТЕКТОР СИМУЛЯЦИИ (NPC, тики, давление, решения)

### Сейчас делает:
[последнее зафиксированное действие]

### Состояние симуляции (последняя сессия игры):

**Tick Pipeline:**
- Тиков за сессию: {N}
- Decisions > 0: {0 из N} ← КРИТИЧНО если всегда 0
- game_time течёт: {да/нет}

**Movement Pipeline (по NPC):**
| NPC | Intent | SceneChange | Traversal | Координаты |
|-----|--------|-------------|-----------|------------|
| guard_borko | ✅ | ✅ | ✅ | x=12.0 y=9.0 |
| maid_lusya | ✅ | ❌ | ❌ | x=None |
| thief_shadow | ✅ | ❌ | ❌ | x=None |

**Directive Pipeline (последний приказ игрока):**
- Приказ: {текст}
- Цель: {npc_id}
- ObediencePressure: {значение} ← 0.00 = разрыв
- CognitiveOverlay применён: {да/нет}
- Результат: {движение / нет движения}

### Каузальные разрывы:

#### [BREAK-1] Название разрыва
**Симптом:** что наблюдается  
**Цепь отказа:**  
  Шаг 1 → ✅  
  Шаг 2 → ❌ (причина из лога)  
**Файл для фикса:** path/to/file.py:строка  
**PowerShell для верификации:** команда  

### Архитектурный долг (не трогать без обсуждения):
- Stale Cognition (ДОЛГ 1): DecisionHub работает на state T-1. Требует ADR-059.
- Cognitive Overlay Layer: отдельный спринт.
- Commitment Pipeline: долгосрочная архитектура (см. ТЗ_CDS).

### Что НЕ трогать (сейчас меняет другой архитектор):
[файлы из секции #1 и #2 которые в работе]
```

---

## 4. Автоидентификация архитектора (ключевая фича)

В начале секции "ИДЕНТИФИКАЦИЯ" — простые правила по которым LLM сам определяет кто он, без вопроса к пользователю. Правила основаны на первом сообщении пользователя в сессии.

Примеры триггеров:
- "починим баг", "патч", "фикс файла" → Архитектор #1 или #3
- "нарратив", "тик", "NPC не", "давление", "решение" → Архитектор #3  
- "рендер", "pygame", "окно", "отображается", "спрайт", "UI" → Архитектор #2

LLM читает секцию "Сейчас делает:" двух других архитекторов → понимает что не трогать.

---

## 5. Что заполняет CDS автоматически

При запуске игры CDS парсит:
1. **stdout/лог игры** → заполняет секции #2 и #3 (координаты, traversal, decisions, разрывы)
2. **git log -5** → заполняет "Последние изменения" в секции #1
3. **MUTATIONS.md** → заполняет "Сейчас делает" (последняя запись)
4. **Select-String по TODO/FIXME** → заполняет "Файлы с активными TODO"

Что заполняет человек вручную:
- "Сейчас делает:" в начале сессии (одна строка в MUTATIONS.md или отдельный STATUS.md)

---

## 6. Паттерны для парсинга логов

```python
PATTERNS = {
    # Tick health
    "decisions_zero":     r"\[TICK_DECISIONS\] end: 0 decisions",
    "decisions_nonzero":  r"\[TICK_DECISIONS\] end: (\d+) decisions",
    "idle_tick":          r"\[IDLE_TICK\] fired at (\d+)ms",
    
    # Movement pipeline
    "intent_received":    r"\[TRACE\]\[ENGINE_RECEIVED\] npc=(\w+)",
    "scene_change":       r"\[TRACE\]\[SCENE_CHANGE_CREATED\] npc=(\w+) x=([\d.]+) y=([\d.]+)",
    "traversal_start":    r"\[TRAVERSAL\] Start: npc=(\w+) to_node=(\w+)",
    "npc_snapshot":       r"\[TRACE\]\[SNAPSHOT\] npc=(\w+) x=([\w.]+) y=([\w.]+)",
    "node_not_found":     r"\[MOVEMENT_ENGINE\] Узел '(\w+)' не найден для (\w+) в (\w+)",
    
    # Spatial health
    "spatial_fallback":   r"\[SCENE\] location_templates\.json недоступен",
    "editor_not_found":   r"\[SPATIAL\] editor JSON не найден для (.+)/(.+)",
    
    # Directive pipeline
    "directive_detected": r"\[CAUSALITY\] Semantic action MOVE detected for NPC '(\w+)'",
    "obedience_pressure": r"\[DIRECTIVE_INTERPRET\] Target=(\w+), Action=(\w+), ObediencePressure=([\d.]+)",
    "cognitive_overlay":  r"\[COGNITIVE_OVERLAY\] Applied (\d+) directive deltas",
    
    # LLM health
    "llm_nothing":        r"dm_resp='Ничего не произошло\.'",
    "llm_cjk":            r"[\u4e00-\u9fff]{3,}",  # 3+ китайских символа подряд
    "llm_call":           r"\[R4A_POOL\] calling complete\(\)",
    "llm_response":       r"\[R4A_POOL\] complete\(\) returned (\d+) chars",
}
```

---

## 7. Архитектура модуля

```
Enigma/
├── diagnostics/
│   ├── __init__.py
│   ├── causal_observer.py       ← читает лог-поток в фоне
│   ├── pattern_registry.py      ← паттерны из секции 6
│   ├── causal_chain_builder.py  ← связывает события в цепи по NPC
│   ├── report_renderer.py       ← рендерит три секции в markdown
│   ├── git_reader.py            ← git log, MUTATIONS.md
│   └── health_checkers/
│       ├── tick_health.py
│       ├── movement_health.py   ← таблица по каждому NPC
│       ├── spatial_health.py
│       ├── directive_health.py
│       └── llm_health.py
├── reports/
│   ├── LAST_SESSION.md          ← перезаписывается каждый запуск
│   └── history/
│       └── 2026-05-18_14-32.md  ← архив
```

---

## 8. Встраивание в game_launcher.py

```python
# После запуска backend, до pygame loop
DIAGNOSTICS_ENABLED = True  # вынести в settings

if DIAGNOSTICS_ENABLED:
    from diagnostics.causal_observer import CausalObserver
    _observer = CausalObserver()
    _observer.start()  # фоновый поток

# ... pygame loop ...

# При завершении (finally блок)
if DIAGNOSTICS_ENABLED and _observer:
    _observer.stop()
    _observer.export("reports/LAST_SESSION.md")
    print("[CDS] Отчёт: reports/LAST_SESSION.md")
```

**Принципы:**
- Crash в CDS не роняет игру (всё в try/except)
- Нулевое влияние на VRAM и игровой loop
- Работает в отдельном потоке

---

## 9. Этапы реализации

### Этап 1 (MVP) — Log Parser + три секции
**Цель:** Рабочий `LAST_SESSION.md` с реальными данными из логов.  
**Критерий готовности:** LLM получает файл и без PowerShell-команд знает состояние 6 NPC, количество decisions, последние изменения файлов.

Порядок:
1. `pattern_registry.py` — паттерны из секции 6
2. `causal_observer.py` — читает stdout игры через pipe или лог-файл
3. `health_checkers/movement_health.py` — таблица NPC
4. `health_checkers/tick_health.py` — decisions, время
5. `report_renderer.py` — три секции в markdown
6. Хук в `game_launcher.py`

### Этап 2 — Causal Chain Builder
Связывает паттерны в цепи: "node_not_found" + "npc_zero_coords" для одного NPC = одна цепь, не два предупреждения.

### Этап 3 — Git Reader + MUTATIONS.md Parser
Автозаполнение секции #1: последние изменения, TODO/FIXME по файлам.

### Этап 4 — DNA Metrics (не раньше Этапа 2)
RPI, CD, EG по истории сессий.

---

## 10. Первый шаг реализации

Перед кодингом запросить:

```powershell
# Где пишутся логи и как их читать из Python
Select-String -Path "C:\DDD\Codex\VSC_Enigma\Enigma\game_launcher.py" -Pattern "log|stdout|stderr|subprocess|Popen" | Select-Object LineNumber, Line

# Структура game_launcher — где finally/cleanup
Get-Content "C:\DDD\Codex\VSC_Enigma\Enigma\game_launcher.py" | Select-Object -Index (100..160) | ForEach-Object -Begin {$i=101} -Process {"$i`: $_"; $i++}
```
