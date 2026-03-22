# ENIGMA — Дорожная карта реализации
### Версия 5.0 | Март 2026 | Актуальная

> **Что изменилось vs v4.1:**
> Добавлены четыре новые фазы (SceneState, Model Migration, PyGame UI, ChangeSet)
> на основе анализа реальных проблем в игре. Скорректирован порядок существующих фаз.
> Принцип "Python считает — LLM рассказывает" теперь применён полностью, включая состояние мира.

---

## 📍 РЕАЛЬНОЕ СОСТОЯНИЕ ПРОЕКТА (Март 2026)

```
✅ start_enigma.bat — полный запуск (LLM + Backend + Frontend)
✅ llama-server — Qwen2.5-7B, GPU_LAYERS=33, --n-predict 800
✅ FastAPI — стартует, /api/health отвечает
✅ JSONL логи — структурированы, ротация по дням
✅ VRAM Monitor — baseline fix, get_vram_budget(), is_safe_to_load()
✅ Error Interpreter — singleton, анализ LLM-ошибок, fix-рекомендации
✅ SSE Streaming — stream_tokens(), stream_narrate(), routes_stream.py
✅ Frontend Streaming — getReader(), fallback POST, счётчик tok/s
✅ Action Classifier — все 14 ActionType, приоритеты, get_required_agents()
✅ Physics Validator — правила мира, bypass через заклинания
✅ Combat Math — полный D&D 5e: атака, урон, крит, инициатива, смерть
✅ Sandbox Handler — 23 обработчика + TOP-100 нестандартных действий
✅ orchestrator.py — _run_python_engines() интегрирован
✅ dm_agent.py — читает python_engines контекст, npc_psychology_block
✅ npc_agent.py — все NPC в локации отвечают отдельно (исправлено)
✅ context_builder.py — динамический сборщик контекста для LLM
✅ memory.py — LayeredMemory, JsonMemoryStore, JSONL backend
✅ world_scheduler.py — WorldScheduler.maybe_tick() (базовый)
✅ model_router.py — ModelRouter, ModelPool, lazy loading, VRAM-aware
✅ major_npcs.json — 5 NPC с полной психологией, gender, description
✅ campaign_state.json — current_location исправлен

⚠️  npc_agent.py — JSON из NPC ответа не парсится, trust_change выбрасывается
⚠️  SceneStateManager — НЕ СУЩЕСТВУЕТ (LLM выдумывает объекты сцены)
⚠️  NPC prompt — даёт абстрактные числа вместо конкретных физических фактов
⚠️  Модели — 5-7 слабых 7B вместо одной сильной 12B (архитектурный долг)
⚠️  UI — index.html не разделяет DM нарратив и NPC речь как каналы
⚠️  NPC state changes из LLM ответов не применяются к JSON
⚠️  mass_npc_templates.json — НЕ СУЩЕСТВУЕТ
⚠️  LifeEngine, KarmaEngine, SocialMobility, NPCGenerator — НЕ СУЩЕСТВУЮТ
⚠️  Мультиплеер — НЕ РЕАЛИЗОВАН
⚠️  Создание персонажа через DM-диалог — НЕ РЕАЛИЗОВАНО
⚠️  PyGame UI — НЕ НАЧАТ (замена index.html)
⚠️  RAG по PDF — базовые заготовки, не работает end-to-end
```

---

# ═══════════════════════════════════════════════════════════
# ПОЧЕМУ ИЗМЕНИЛСЯ ПОРЯДОК ФАЗ — ОБЪЯСНЕНИЕ
# ═══════════════════════════════════════════════════════════

Версия 4.1 предполагала линейный порядок: 3A → 3B → 3C → модели → UI.
Это ошибочный порядок по одной причине:

**3B и 3C строятся поверх LLM как источника истины о мире.**
Но LLM — ненадёжный источник. Она придумывает подвалы, связанных NPC,
несуществующие объекты. Добавление LifeEngine и памяти поверх этого
только увеличит контекст и количество галлюцинаций.

**Правильный порядок:**
1. Сначала сделать Python единственным источником истины о мире (SceneState)
2. Потом починить NPC pipeline (ChangeSet — LLM предлагает, Python решает)
3. Потом сменить модель (12B работает лучше когда получает факты а не абстракции)
4. Потом строить живой мир (3B) — он будет наполнять SceneState реальными данными
5. Параллельно — переход на PyGame (правильная архитектура UI)
6. Потом всё остальное

---

# ═══════════════════════════════════════════════════════════
# ФАЗА 0 — СТАБИЛИЗАЦИЯ ✅ ПОЧТИ ГОТОВО
# ═══════════════════════════════════════════════════════════

✅ start_llm.bat — GPU_LAYERS=33, --n-predict 800 — СДЕЛАНО
✅ llama_cpp_provider.py — max_tokens 800 — СДЕЛАНО
✅ dm_agent.py — читает context["python_engines"] — СДЕЛАНО
✅ campaign_state.json — current_location исправлен — СДЕЛАНО

---

# ═══════════════════════════════════════════════════════════
# ФАЗА 1 — STREAMING И UI ✅ ГОТОВО
# ═══════════════════════════════════════════════════════════

Всё реализовано. Будет заменено в Фазе UI (параллельно с 3B).

---

# ═══════════════════════════════════════════════════════════
# ФАЗА 2 — ACTION CLASSIFIER И PYTHON ДВИЖКИ ✅ ГОТОВО
# ═══════════════════════════════════════════════════════════

Всё реализовано. ActionClassifier становится входной точкой для
SceneStateManager в Фазе S.

---

# ═══════════════════════════════════════════════════════════
# ФАЗА 3A — NPC CORE PSYCHOLOGY ⬅️ ТЕКУЩАЯ ЗАДАЧА
# Срок: завершить за 3–5 дней | Приоритет: КРИТИЧЕСКИЙ
# ═══════════════════════════════════════════════════════════

> Большая часть кода написана. Остались критические баги pipeline.

## 3A.HOTFIX — Немедленные исправления (1–2 дня)

Эти баги делают всю 3A нерабочей несмотря на готовый код.

### HF-1: Парсинг JSON из NPC ответа

**Файл:** `backend/app/agents/npc_agent.py` → метод `react()`

Pygmalion возвращает JSON строку вида:
`{"speech": "...", "action": "...", "trust_change": 2, "stress_change": -1}`

Сейчас вся строка идёт в `npc_reactions` и отображается игроку как сырой JSON.
`trust_change` и `stress_change` выбрасываются — это потеря данных каждый ход.

```python
# В цикле по npc_ctx после получения resp от router:
try:
    parsed = json.loads(resp)
    speech       = parsed.get("speech", resp)
    action       = parsed.get("action", "")
    trust_delta  = parsed.get("trust_change", 0)
    stress_delta = parsed.get("stress_change", 0)
except (json.JSONDecodeError, TypeError):
    speech       = resp
    action       = ""
    trust_delta  = 0
    stress_delta = 0

# Применяем дельты к NPC данным через orchestrator
# (передавать через npc_state_updates в возвращаемый dict)
```

- [ ] Парсить JSON из каждого NPC ответа
- [ ] Извлекать только `speech` для `npc_reactions`
- [ ] Собирать `trust_change`/`stress_change` в `npc_state_updates`
- [ ] В orchestrator после npc_agent: применять дельты к NPC JSON через `_save_npcs()`

### HF-2: build_npc_prompt — конкретные факты вместо абстракций

**Файл:** `backend/app/services/npc/npc_cognition.py` → `build_npc_prompt()`

Сейчас промпт даёт: `"Стресс: 40/100 (напряжён)"` → LLM интерпретирует свободно.
Нужно давать: `"Ты сейчас: стоишь с подносом у третьего стола, руки слегка дрожат"`

Принцип: **числа → физическое состояние → конкретная сцена**.

```python
# Добавить в build_npc_prompt() маппинг состояний:
def _state_to_physical(npc: dict) -> str:
    stress   = npc["psyche"]["stress"]
    state    = npc["psyche"]["state"]
    routine  = npc["routine"]["current"]
    mood     = npc["routine"].get("mood", "neutral")
    
    # Физическое положение из рутины
    position_map = {
        "serving_tables":  "обслуживаешь столы, поднос в руках",
        "cleaning_tables": "протираешь столешницы тряпкой",
        "behind_bar":      "стоишь за стойкой",
        "observing":       "сидишь в тёмном углу, почти неподвижно",
        "guarding_gate":   "стоишь у ворот, копьё в руках",
    }
    position = position_map.get(routine, "находишься в локации")
    
    # Физические маркеры стресса
    stress_physical = (
        "руки заметно трясутся, голос срывается" if stress >= 85 else
        "нервно оглядываешься, движения резкие"  if stress >= 60 else
        "немного напряжён, но держишься"          if stress >= 35 else
        "спокоен и собран"
    )
    
    return f"Ты сейчас: {position}. {stress_physical}."
```

- [ ] Добавить `_state_to_physical(npc)` в `npc_cognition.py`
- [ ] Заменить абстрактные числа на физические описания в промпте
- [ ] Добавить текущую рутину NPC в промпт как "что ты сейчас делаешь"
- [ ] Добавить `description` и `gender` из NPC JSON в промпт

### HF-3: Сессионная память внутри хода (минимальная)

Тень меняет роль каждый ход потому что не получает историю сессии.
Пока 3C не реализована — передавать последние 2 хода напрямую.

**Файл:** `backend/app/services/orchestrator.py`

```python
# Перед NPC блоком в _run_python_engines():
recent_session = self.layered_memory.read_campaign_memory(
    req.campaign_id, limit=2
)
session_summary = []
for entry in recent_session:
    for action in entry.get("actions", []):
        session_summary.append(
            f"{action['player_name']}: {action['action']}"
        )
shared_context["recent_session"] = session_summary
```

- [ ] Читать последние 2 записи campaign_memory в `_run_python_engines()`
- [ ] Передавать в `shared_context["recent_session"]`
- [ ] В `build_npc_prompt()` добавлять секцию "Последнее что ты помнишь"

### HF-4: DM не получает NPC речь — только действия

**Файл:** `backend/app/agents/dm_agent.py` → `_build_prompt()`

DM сейчас получает реплики NPC и переформулирует их своими словами.
Должен получать только физические действия — речь рендерится отдельно.

```python
# В npc_agent.react() добавить в возвращаемый dict:
"npc_actions": [f"{name}: {action}" for name, action in npc_actions]

# В dm_agent._build_prompt() заменить npc_str:
npc_actions = npc_result.get("npc_actions", [])
npc_str = "\n".join(f"- {a}" for a in npc_actions) if npc_actions else "NPC не предпринимают видимых действий"
# Метка в промпте: "Физические действия NPC (речь идёт отдельно, не дублируй):"
```

- [ ] В `npc_agent` собирать `npc_actions` отдельно от `npc_reactions` (speech)
- [ ] DM получает `npc_actions` — только физические действия
- [ ] `npc_reactions` (speech) рендерятся в UI отдельным каналом

---

## 3A.0 — Данные NPC ✅ В ОСНОВНОМ ГОТОВО

- [x] `major_npcs.json` — 5 NPC с полной психологией, gender, description
- [ ] `mass_npc_templates.json` — 10 шаблонов (горожанин, стражник, крестьянин, пьяный, монах, торговец, нищий, солдат, служанка, ребёнок)

## 3A.1–3A.4 — NPC Движки ✅ КОД НАПИСАН

- [x] `npc_cognition.py` — 4 драйва, build_npc_prompt, get_inner_thought
- [x] `psyche_engine.py` — стресс, слом воли, состояния
- [x] `threat_assessor.py` — оценка угрозы
- [x] `perception_engine.py` — видимые маркеры, статус

Требуют доработки по HF-2 (физические описания вместо абстрактных чисел).

## 3A.5 — Интеграция в Orchestrator ✅ В ОСНОВНОМ ГОТОВО

- [x] NPC блок в `_run_python_engines()`
- [x] `tier`, `gender`, `description` передаются в npc_contexts
- [ ] Применение `trust_change`/`stress_change` из NPC ответов (HF-1)
- [ ] Передача `npc_state_updates` обратно в orchestrator для сохранения

## ✅ Критерии готовности 3A

```
✅ npc/ папка существует (4 файла + __init__)
✅ major_npcs.json — 5 NPC с gender и description
[ ] mass_npc_templates.json — 10 шаблонов
[ ] trust_change/stress_change из LLM применяются к NPC JSON
[ ] build_npc_prompt даёт физические факты, не абстрактные числа
[ ] DM получает только npc_actions, не speech
[ ] Все 3 NPC в таверне отвечают отдельно именованными репликами
[ ] В логах: threat_score, behavior_hint, npc_name видны
[ ] JSON не торчит в UI
```

---

# ═══════════════════════════════════════════════════════════
# ФАЗА S — SCENESTATE: МИР КАК ОБЪЕКТ ИСТИНЫ  ← НОВАЯ ФАЗА
# Срок: 1.5 недели | Приоритет: КРИТИЧЕСКИЙ
# После 3A. До 3B.
# ═══════════════════════════════════════════════════════════

> **Почему это нужно до 3B:**
> 3B (LifeEngine) создаёт события в мире — NPC меняют локации, предметы появляются и
> исчезают. Без SceneState эти события некуда записывать. LLM продолжает придумывать
> подвалы даже если LifeEngine говорит что Торнин спит. SceneState — фундамент живого мира.

## Диагноз

Сейчас: `Scene = то что LLM придумала`
Должно быть: `Scene = структура Python, LLM только описывает её словами`

Любой объект который LLM упомянула но которого нет в SceneState — **не существует**.
Любое изменение мира которое LLM "описала" но Python не зафиксировал — **не произошло**.

---

## S.1 — SceneStateManager

**Создать:** `backend/app/services/scene_state_manager.py`

```
Принцип:
Не предопределённый список объектов — это невозможно для живого мира.
Живой реестр который пополняется автоматически по мере игры.

Начало сессии в локации: SceneState пустой (только NPC из major_npcs.json)
Игрок взаимодействует с объектом → Python добавляет его в реестр
LLM упоминает несуществующий объект → объект не добавляется в реестр
```

**Структура SceneState** (хранится в `campaign_state.json`):

```json
"scene_state": {
  "location_id": "tavern_silver_wolf",
  "snapshot_tick": 42,
  "objects": {
    "candles_main_hall": {
      "name": "свечи в главном зале",
      "state": "lit",
      "count": 6,
      "interactable": true,
      "owner": null
    },
    "bar_counter": {
      "name": "барная стойка",
      "state": "intact",
      "material": "oak",
      "hp": 30,
      "max_hp": 30
    }
  },
  "npc_positions": {
    "tavern_keeper_tornin": {
      "position": "behind_bar",
      "activity": "cleaning_tables",
      "visible": true
    },
    "maid_lusya": {
      "position": "serving_table_3",
      "activity": "serving_tables",
      "visible": true
    },
    "thief_shadow": {
      "position": "corner_table",
      "activity": "observing",
      "visible": false
    }
  },
  "environment": {
    "light_level": "dim",
    "noise_level": "low",
    "time_of_day": "22:00",
    "weather_inside": "warm_smoky"
  },
  "player_inventory_snapshot": {},
  "active_effects": []
}
```

**Методы:**

- [ ] `get_scene_state(campaign_id, location_id) -> dict` — загрузить текущий SceneState
- [ ] `initialize_scene(campaign_id, location_id, time_of_day) -> dict` — создать SceneState для новой локации на основе шаблонов
- [ ] `apply_change(campaign_id, change: SceneChange) -> bool` — применить одно изменение
- [ ] `validate_change(scene_state, change) -> tuple[bool, str]` — проверить допустимость
- [ ] `get_scene_description(scene_state) -> str` — текстовое описание для DM промпта
- [ ] `update_npc_position(campaign_id, npc_id, position, activity) -> None`
- [ ] `save_scene_state(campaign_id, scene_state) -> None`

---

## S.2 — LocationTemplates: начальное состояние локаций

**Создать:** `backend/data/locations/location_templates.json`

```
Принцип: шаблон — это не жёсткое описание, а вероятностный стартовый набор.
При инициализации локации Python генерирует SceneState из шаблона
с учётом времени суток и случайных вариаций.
```

```json
{
  "tavern_silver_wolf": {
    "name": "Таверна «Серебряный Волк»",
    "type": "tavern",
    "default_objects": {
      "bar_counter": {"name": "барная стойка", "state": "intact", "hp": 30},
      "fireplace":   {"name": "очаг", "state": "burning", "light": 40},
      "tables":      {"name": "столы", "count": 6, "state": "intact"}
    },
    "time_variants": {
      "06:00-10:00": {
        "light_level": "dim",
        "noise_level": "silent",
        "candles":     {"state": "unlit"}
      },
      "10:00-22:00": {
        "light_level": "bright",
        "noise_level": "moderate",
        "candles":     {"state": "lit", "count": 12}
      },
      "22:00-02:00": {
        "light_level": "dim",
        "noise_level": "low",
        "candles":     {"state": "lit", "count": 6}
      },
      "02:00-06:00": {
        "light_level": "dark",
        "noise_level": "silent",
        "candles":     {"state": "unlit"}
      }
    },
    "connected_locations": ["city_gate", "market_square", "inn_rooms"]
  }
}
```

- [ ] Создать `location_templates.json` для 5 стартовых локаций
- [ ] `initialize_from_template(template, time_of_day) -> dict` — учитывать время
- [ ] Случайные вариации ±20% для count объектов (не каждый раз одинаково)

---

## S.3 — SceneChange: типы изменений мира

**Создать:** `backend/app/services/scene_change.py`

```python
from dataclasses import dataclass
from enum import Enum

class ChangeType(Enum):
    OBJECT_STATE   = "object_state"    # барная стойка: intact → damaged
    OBJECT_ADD     = "object_add"      # добавить объект (нашли нож на полу)
    OBJECT_REMOVE  = "object_remove"   # убрать объект (украли свечи)
    OBJECT_MOVE    = "object_move"     # переместить объект
    NPC_POSITION   = "npc_position"    # NPC переместился
    NPC_STATE      = "npc_state"       # NPC изменил состояние (связан, свободен)
    ENVIRONMENT    = "environment"     # свет, шум, погода внутри
    INVENTORY      = "inventory"       # игрок взял/положил предмет
    EFFECT_ADD     = "effect_add"      # добавить активный эффект (горит стол)
    EFFECT_REMOVE  = "effect_remove"   # убрать эффект

@dataclass
class SceneChange:
    type:    ChangeType
    target:  str           # id объекта или NPC
    field:   str           # какое поле меняется
    value:   object        # новое значение
    cause:   str           # откуда пришло изменение (player_action, life_engine, etc.)
    tick:    int           # когда произошло
```

- [ ] Создать `SceneChange` dataclass
- [ ] Создать `ChangeValidator` — проверять допустимость каждого изменения
- [ ] Логировать все изменения в JSONL (`scene_changes_YYYYMMDD.jsonl`)

---

## S.4 — Интеграция SceneState в Pipeline

### S.4.1 — SandboxHandler → SceneState

SandboxHandler уже считает успех действия. Теперь он должен
создавать `SceneChange` объект который orchestrator применяет к SceneState.

**Файл:** `backend/app/services/game/sandbox_handler.py`

```python
# sandbox_handler уже возвращает SandboxResult.
# Добавить: SandboxResult.scene_changes: list[SceneChange]

# Пример для кражи свечей:
if action_type == "STEAL" and target == "candles":
    result.scene_changes = [
        SceneChange(
            type=ChangeType.OBJECT_REMOVE,
            target="candles_main_hall",
            field="count",
            value=0,
            cause="player_steal",
            tick=current_tick
        ),
        SceneChange(
            type=ChangeType.INVENTORY,
            target=player_name,
            field="add",
            value={"candles": stolen_count},
            cause="player_steal",
            tick=current_tick
        )
    ]
```

- [ ] Добавить `scene_changes: list` в `SandboxResult`
- [ ] Для 10 основных типов действий добавить генерацию `SceneChange`
- [ ] В orchestrator: после SandboxHandler применять `scene_changes` к SceneState

### S.4.2 — DM получает факты из SceneState

**Файл:** `backend/app/agents/dm_agent.py` → `_build_prompt()`

```python
# Добавить секцию в промпт (ПЕРЕД всеми другими блоками):
scene_state = context.get("scene_state", {})
if scene_state:
    scene_block = SceneStateManager.get_scene_description(scene_state)
    # Выглядит так:
    # "Текущее состояние сцены (ТОЛЬКО ЭТИ объекты существуют в локации):
    #  - Барная стойка: целая, дубовая
    #  - Свечи: горят (6 штук)
    #  - Очаг: горит
    #  Торнин: за стойкой, протирает стаканы
    #  Люся: у третьего стола, несёт поднос
    #  Тень: в тёмном углу, наблюдает
    #  NPC которых нет в этом списке — в локации отсутствуют."
```

- [ ] `SceneStateManager.get_scene_description()` возвращает текст для промпта
- [ ] Добавить в DM промпт первым блоком с пометкой "только эти объекты существуют"
- [ ] DM system prompt: "Упоминай только объекты из блока 'Текущее состояние сцены'"

### S.4.3 — SceneState в shared_context

**Файл:** `backend/app/services/orchestrator.py`

```python
# В run_turn(), после _build_shared_context():
scene_state = scene_state_manager.get_scene_state(
    req.campaign_id, req.location
)
if not scene_state:
    # Первый визит в локацию — инициализировать из шаблона
    scene_state = scene_state_manager.initialize_scene(
        req.campaign_id, req.location,
        shared_context.get("time_of_day", "12:00")
    )
shared_context["scene_state"] = scene_state
```

- [ ] Инициализировать SceneState при первом входе в локацию
- [ ] Передавать в `shared_context["scene_state"]`
- [ ] После pipeline: сохранять обновлённый SceneState

---

## ✅ Критерии готовности фазы S

```
[ ] SceneStateManager создан (~150 строк)
[ ] location_templates.json для 5 стартовых локаций
[ ] SceneChange dataclass + ChangeValidator
[ ] SandboxHandler генерирует scene_changes для 10 типов действий
[ ] DM получает scene_description первым блоком промпта
[ ] При краже свечей — в следующем ходу DM описывает темноту
[ ] Торнин не появляется в подвале если его location = "behind_bar"
[ ] Все scene_changes логируются в JSONL
[ ] test_scene_state_manager.py — 5 тестов зелёные
```

---

# ═══════════════════════════════════════════════════════════
# ФАЗА M — СМЕНА МОДЕЛИ: ОДНА СИЛЬНАЯ ВМЕСТО ПЯТИ СЛАБЫХ ← НОВАЯ
# Срок: 3–5 дней тестирования | Приоритет: ВЫСОКИЙ
# После S. До 3B.
# ═══════════════════════════════════════════════════════════

> **Почему именно здесь:**
> После SceneState LLM получает конкретные факты вместо абстракций.
> Это максимально раскрывает потенциал 12B модели.
> Делать смену до SceneState — половина эффекта. После 3B — откладывать проблему.

## Диагноз текущих моделей

| Модель | Проблема |
|--------|----------|
| Qwen2.5-7B (DM) | При контексте >3k токенов теряет instruction-following |
| Mistral-Pygmalion-7B (NPC) | Roleplay fine-tune — игнорирует ограничения, выдумывает роли |
| Saiga-7B (Rules/Memory) | Хорош на русском, слаб в логике |
| 5 моделей суммарно | Переключения 3–12 сек, несогласованное поведение |

## Целевая архитектура

```
СЕЙЧАС: 5–7 слабых моделей (7B каждая) — переключение каждый ход
ЦЕЛЬ:   1 сильная модель (12B) — один системный промпт на роль
```

Одна 12B с разными system prompt даёт более согласованный мир чем
пять 7B которые каждая "думает" по-своему.

## M.1 — Выбор и загрузка модели

**Приоритет 1:** `Gemma-3-12B-IT-Q4_K_M.gguf` (~7.0 GB)
- Google Gemma 3 Instruction Tuned
- Лучший instruction-following в классе 12B (2025–2026)
- Хороший русский язык
- Умещается в 8 GB VRAM при ctx=4096

**Приоритет 2:** `Mistral-Nemo-12B-Instruct-Q4_K_M.gguf` (~7.2 GB)
- Mistral AI, специально для диалогов и ролей
- Отличный русский, сильный roleplay
- Немного больше VRAM, ctx нужно ограничить до 3072

**Приоритет 3:** `Qwen2.5-14B-Instruct-Q4_K_M.gguf` (~8.5 GB)
- Не влезает в 8 GB при нормальном ctx — только с ctx=1024 (слишком мало)

- [ ] Скачать Gemma-3-12B-IT-Q4_K_M (первый кандидат)
- [ ] Протестировать: `llama-server -m gemma-3-12b-it-q4_k_m.gguf -ngl 38 -c 4096`
- [ ] Проверить VRAM: должно быть < 7.5 GB с запасом

## M.2 — Изменения в конфиге

**Файл:** `start_enigma.bat` (или `start_llm.bat`)

```bat
REM БЫЛО: Qwen2.5-7B, ctx=2048
llama-server.exe -m qwen2.5-7b-instruct-q4_k_m.gguf -ngl 33 -c 2048

REM СТАНЕТ: Gemma-3-12B, ctx=4096
llama-server.exe -m gemma-3-12b-it-q4_k_m.gguf -ngl 38 -c 4096 --n-predict 1024 --threads 6
```

**Файл:** `backend/app/core/config.py`
```python
# Было: контекст 2048 на всех агентов
# Станет: 4096 общий, распределение по агентам:
CONTEXT_BUDGET = {
    "dm":      2048,   # нарратив + SceneState + python_engines
    "npc":      800,   # один NPC промпт, кратко
    "rules":    600,   # правило + вопрос
    "memory":   400,   # суммаризация
}
```

- [ ] Обновить `start_llm.bat` / `start_enigma.bat` для 12B модели
- [ ] Обновить `config.py` — ctx=4096, новые бюджеты по агентам
- [ ] Убрать Pygmalion и Saiga из активного пула (оставить как fallback в конфиге)

## M.3 — Упрощение ModelPool

**Файл:** `backend/app/services/llm/provider_manager.py`

Сейчас: 5–7 моделей в пуле, сложная логика приоритетов.
После: 1 основная + 1 резервная (старая 7B на случай OOM).

```python
# Новый AGENT_MODEL_MAP:
AGENT_MODEL_MAP = {
    "dm":         "gemma_12b",    # было: "qwen_7b"
    "npc_major":  "gemma_12b",    # было: "npc_major" (Pygmalion)
    "npc_mass":   "gemma_12b",    # было: "npc_mass"  (Pygmalion light)
    "rules":      "gemma_12b",    # было: "saiga_7b"
    "world":      "gemma_12b",    # было: "qwen_7b"
    "memory":     "gemma_12b",    # было: "saiga_7b" / "yandex_7b"
    # Fallback на случай OOM или недоступности 12B:
    "_fallback":  "qwen_7b",
}
```

- [ ] Обновить `AGENT_MODEL_MAP` на одну 12B модель
- [ ] Оставить Qwen2.5-7B как `_fallback` в конфиге
- [ ] Логировать какая модель реально использовалась каждый ход

## M.4 — Тестирование (3–5 дней)

10–15 тестовых игровых ходов. Проверять:

- [ ] DM не придумывает несуществующих локаций (подвалы, другие таверны)
- [ ] NPC остаются в своей роли (Люся — служанка, не пленница)
- [ ] DM держит instruction-following при полном контексте SceneState + python_engines
- [ ] VRAM < 7.5 GB стабильно
- [ ] Время ответа < 15 сек (при 4096 ctx Gemma 12B ~65 tok/sec)
- [ ] Русский язык качественный, нет транслитерации

**Критерий успеха:** "подвал" и "Громовой Молот" не появляются в первых 20 ходах.

## ✅ Критерии готовности фазы M

```
[ ] Gemma-3-12B-IT-Q4_K_M загружена и работает
[ ] VRAM < 7.5 GB с ctx=4096
[ ] Все агенты используют одну модель
[ ] 10 тестовых ходов без галлюцинаций локации
[ ] NPC держат роль 3+ хода подряд
[ ] Время ответа DM < 15 сек
[ ] Pygmalion убран из активного пула (оставлен в конфиге как legacy)
```

---

# ═══════════════════════════════════════════════════════════
# ФАЗА UI — ПЕРЕХОД НА PYGAME ← НОВАЯ ФАЗА
# Срок: 2–3 недели | Приоритет: ВЫСОКИЙ
# Параллельно с 3B (независимые компоненты)
# ═══════════════════════════════════════════════════════════

> **Почему PyGame, не улучшение index.html:**
> index.html — это браузер поверх FastAPI. Всё что там отображается —
> это строки из API. Нет возможности надёжно разделить DM нарратив и NPC речь
> как отдельные каналы без сложного JavaScript парсинга.
> PyGame даёт полный контроль над рендерингом: что где отображается определяет Python,
> а не LLM и не JavaScript.

## UI.1 — Архитектура PyGame приложения

```
Enigma PyGame Client
├── launcher.py          ← точка входа (вместо браузера)
├── ui/
│   ├── game_window.py   ← главное окно, event loop
│   ├── panels/
│   │   ├── narrative_panel.py   ← DM нарратив (левая колонка, большая)
│   │   ├── dialogue_panel.py    ← NPC речь (отдельный канал, именованные реплики)
│   │   ├── status_panel.py      ← локация, время, погода, HP игрока
│   │   ├── input_panel.py       ← ввод действия игрока
│   │   └── debug_panel.py       ← F12: VRAM, NPC состояния, токены, inner_thought
│   ├── renderer.py      ← шрифты, цвета, layout
│   └── api_client.py    ← HTTP клиент к FastAPI (SSE streaming)
```

**Разделение каналов — ключевое:**

```
narrative_panel  ← DM нарратив (курсив, серый, стриминг)
dialogue_panel   ← именованные NPC реплики:
                    [Торнин] "Ты нарушил порядок..."
                    [Люся]   "Я сделаю что скажете..."
                    [Тень]   "Честные сделки..."
status_panel     ← Таверна «Серебряный Волк» | 22:00 | Вечер | ❤ 10/10
input_panel      ← [Введи действие...] [▶ Отправить]
debug_panel      ← (F12) NPC стресс, trust, VRAM, модель, токены/сек
```

## UI.2 — Layout и визуальный стиль

```
┌─────────────────────────────────────────────────────────┐
│ ENIGMA                     Таверна «Серебряный Волк»    │
│                            22:00 | Вечер | ❤ 10/10 ⛨10 │
├──────────────────────────┬──────────────────────────────┤
│                          │                              │
│   DM НАРРАТИВ            │   ДИАЛОГИ NPC               │
│   (основная область)     │                              │
│                          │   [Торнин]                   │
│   Таверна наполнена      │   "Ты нарушил порядок..."   │
│   запахом дыма и         │                              │
│   свежего эля. Торнин    │   [Люся]                    │
│   хмурится за стойкой,   │   "Я сделаю что скажете..."│
│   пока Люся замирает     │                              │
│   у третьего стола...    │   [Тень]                    │
│                          │   "Честные сделки..."       │
│                          │                              │
├──────────────────────────┴──────────────────────────────┤
│ > Я поднимаю руки в знак мира и говорю...    [▶ Ответ] │
└─────────────────────────────────────────────────────────┘
```

- [ ] Основной layout: narrative (60%) | dialogue (40%)
- [ ] Status bar: локация, время, HP, AC
- [ ] Input bar: поле ввода + кнопка или Enter
- [ ] Стриминг токенов в narrative_panel (char by char)
- [ ] NPC реплики появляются после завершения DM нарратива
- [ ] Цветовая кодировка: каждый NPC — свой цвет имени

## UI.3 — API клиент в PyGame

**Файл:** `ui/api_client.py`

```python
import requests, json, threading

class EnigmaAPIClient:
    def __init__(self, base_url="http://127.0.0.1:8000"):
        self.base_url = base_url

    def stream_action(self, campaign_id, player_name, action, on_token, on_npc, on_done):
        """
        SSE стриминг. Вызывает колбэки:
        on_token(str)          — каждый токен DM нарратива
        on_npc(name, speech)   — реплика NPC (имя + текст)
        on_done(scene_state)   — завершение, новый SceneState
        """
        def _stream():
            resp = requests.post(
                f"{self.base_url}/api/game/action/stream",
                json={"campaign_id": campaign_id, "player_name": player_name,
                      "action": action},
                stream=True
            )
            for line in resp.iter_lines():
                if line.startswith(b"data: "):
                    data = json.loads(line[6:])
                    if data["type"] == "token":
                        on_token(data["text"])
                    elif data["type"] == "npc":
                        on_npc(data["npc_name"], data["speech"])
                    elif data["type"] == "done":
                        on_done(data.get("scene_state", {}))

        threading.Thread(target=_stream, daemon=True).start()
```

- [ ] SSE клиент через `requests` (не браузер)
- [ ] Три типа событий: `token`, `npc`, `done`
- [ ] Thread-safe очередь для передачи событий в PyGame event loop

## UI.4 — Изменения в routes_stream.py

**Файл:** `backend/app/api/routes_stream.py`

Сейчас SSE поток отправляет только токены DM нарратива.
Нужно добавить отдельные события для NPC реплик и SceneState.

```python
# Новые типы событий:
yield f"data: {json.dumps({'type': 'token', 'text': tok})}\n\n"

# После DM нарратива — отправить NPC реплики:
for npc_name, speech in npc_speeches.items():
    yield f"data: {json.dumps({'type': 'npc', 'npc_name': npc_name, 'speech': speech})}\n\n"

# В конце — новый SceneState:
yield f"data: {json.dumps({'type': 'done', 'scene_state': updated_scene})}\n\n"
```

- [ ] Добавить `type: "npc"` события в SSE поток
- [ ] Добавить `type: "done"` с обновлённым SceneState
- [ ] index.html сохранить как fallback (не удалять до полного перехода)

## UI.5 — Debug Panel (F12)

```
┌─ DEBUG MODE ──────────────────────────────────────────┐
│ VRAM: 6.8/8.0 GB | Модель: Gemma-3-12B | 67 tok/sec  │
│                                                        │
│ ACTION: SOCIAL | Threat: LOW | Scene tick: 47         │
│                                                        │
│ NPC СОСТОЯНИЯ:                                         │
│  Торнин: trust=0.66 stress=20 state=free               │
│    💭 "Этот новичок нарушает мой порядок. Слежу."     │
│  Люся:   trust=0.41 stress=42 state=coerced            │
│    💭 "Хочу уйти. Но некуда."                         │
│  Тень:   trust=0.31 stress=15 state=deceptive          │
│    💭 "Интересно. Посмотрю как это разыграть."        │
│                                                        │
│ SCENE OBJECTS: свечи(6,lit) | стойка(intact) | очаг   │
└───────────────────────────────────────────────────────┘
```

- [ ] F12 — toggle debug panel
- [ ] Показывать: VRAM, модель, tok/sec, action_type
- [ ] NPC: trust, stress, state, inner_thought (только в debug)
- [ ] SceneState objects: короткий список

## ✅ Критерии готовности фазы UI

```
[ ] PyGame окно запускается через launcher.py
[ ] narrative_panel получает стриминг токенов
[ ] dialogue_panel показывает именованные NPC реплики отдельно
[ ] status_panel: локация, время, HP, AC
[ ] input_panel: ввод + Enter/кнопка
[ ] debug_panel (F12): NPC состояния, inner_thoughts, VRAM
[ ] index.html работает параллельно как fallback
[ ] Запуск: start_enigma.bat открывает PyGame окно, не браузер
```

---

# ═══════════════════════════════════════════════════════════
# ФАЗА 3B — ЖИВОЙ МИР
# Срок: 2 недели | Приоритет: ВЫСОКИЙ
# После S и M. Параллельно с UI.
# ═══════════════════════════════════════════════════════════

> После SceneState и 12B модели. LifeEngine теперь записывает события
> в SceneState напрямую — мир меняется по расписанию без участия LLM.

## Изменения vs v4.1

В v4.1 LifeEngine просто обновлял поля в NPC JSON.
Теперь LifeEngine также создаёт `SceneChange` объекты которые
обновляют `scene_state` при каждом тике мира.

Пример: Торнин идёт спать в 22:00 → LifeEngine создаёт:
- `SceneChange(NPC_POSITION, "tavern_keeper_tornin", "position", "bedroom")`
- `SceneChange(ENVIRONMENT, "tavern_main_hall", "noise_level", "silent")`
- `SceneChange(OBJECT_STATE, "bar_counter", "accessible", False)`

Когда игрок приходит в таверну в 23:00 — Торнина нет, стойка закрыта.
DM описывает это потому что SceneState говорит факты.

## 3B.1 — LifeEngine (обновлённый)

**Создать:** `backend/app/services/npc/life_engine.py`

```
Tier симуляции:
Major  → полная симуляция каждый тик (позиция, активность, настроение)
Minor  → расписание + случайные события раз в 3 тика
Mass   → только флаги присутствия в локации (0 VRAM, 0ms)
```

- [ ] `tick(world_state, campaign_id) -> list[SceneChange]` — обновить NPC, вернуть изменения
- [ ] `update_routine(npc, current_time) -> SceneChange` — позиция по расписанию
- [ ] `get_activity_description(npc) -> str` — "Торнин протирает кружки за стойкой"
- [ ] `check_random_events(npc) -> list[SceneChange]` — 5% шанс:
  - Спор с другим NPC → noise_level += 1 в локации
  - Разлитый эль → объект "лужа_эля" добавляется в SceneState
  - Сломанный стул → объект "стул" меняет state="broken"
- [ ] Хранить `recent_events` в NPC JSON — последние 10
- [ ] `recover_stress_tick(npc) -> None` — -5/тик в безопасности

**Интеграция:** `world_scheduler.py` → `maybe_tick()` вызывает `LifeEngine.tick()`
и применяет возвращённые `SceneChange` через `SceneStateManager.apply_change()`

---

## 3B.2 — KarmaEngine ← без изменений vs v4.1

**Создать:** `backend/app/services/npc/karma_engine.py`

- [ ] `update_reputation(player, action_type, outcome) -> None`
- [ ] `get_reputation_summary(player) -> list[str]` — топ-3 тега
- [ ] Глобальные модификаторы: "hero" → trust +0.05 для всех NPC
- [ ] "cruel" → fear_of_player +0.10 для всех NPC
- [ ] `schedule_delayed_event(trigger, delay_ticks, event_type) -> None`
- [ ] Пример: угроза → через 5 тиков стражники ищут игрока

---

## 3B.3 — SocialMobility (обновлённый)

**Создать:** `backend/app/services/npc/social_mobility.py`

Теперь `check_role_change()` создаёт `SceneChange` для обновления
видимых маркеров NPC — что видит игрок.

- [ ] Захваченный: `state="coerced"`, SceneChange добавляет `"chains"` в visible_markers
- [ ] Освобождённый: убирает `"chains"` из SceneState NPC
- [ ] Разорился: `wealth → 5`, SceneChange меняет одежду (visible_markers)
- [ ] `apply_coercion_pressure(npc, pressure_type) -> SceneChange`

---

## 3B.4 — NPCAutoGenerator ← без изменений vs v4.1

**Создать:** `backend/app/services/npc/npc_generator.py`

- [ ] Шаблоны ролей из `mass_npc_templates.json`
- [ ] Lazy генерация: игрок взаимодействует → создаётся полный NPC JSON
- [ ] Сохранение в `data/npcs/generated/`

---

# ═══════════════════════════════════════════════════════════
# ФАЗА 3C — СОЦИАЛЬНАЯ СЕТЬ И ПАМЯТЬ ← без изменений vs v4.1
# Срок: 2 недели | Приоритет: СРЕДНИЙ
# После 3B.
# ═══════════════════════════════════════════════════════════

## 3C.1 — MemoryWeighting
## 3C.2 — RumorNetwork
## 3C.3 — BeliefSystem
## 3C.4 — InconsistencyDetector

> Содержание без изменений vs v4.1. Теперь `InconsistencyDetector`
> также проверяет SceneState — NPC не может стоять за стойкой
> если SceneState говорит что он в тюрьме.

---

# ═══════════════════════════════════════════════════════════
# ФАЗА 3D — ПРОДВИНУТЫЕ ВЗАИМОДЕЙСТВИЯ ← без изменений vs v4.1
# Срок: 2–3 недели | Приоритет: СРЕДНИЙ
# После 3A–3C.
# ═══════════════════════════════════════════════════════════

## 3D.1 — ActionLayerEngine (4 уровня реальности)
## 3D.2 — ShockEngine (когнитивный диссонанс)
## 3D.3 — DriveMatcher (триггеры манипуляции)

> Содержание без изменений vs v4.1.

---

# ═══════════════════════════════════════════════════════════
# ФАЗА 4 — МОДЕЛИ: УПРОЩЕНИЕ ПУЛА ← существенно изменена
# Срок: выполняется в Фазе M | Приоритет: ЗАВЕРШЕНО В M
# ═══════════════════════════════════════════════════════════

После Фазы M (переход на Gemma-3-12B) эта фаза в основном выполнена.

Остаток:
- [ ] Убедиться что fallback на Qwen-7B работает при OOM
- [ ] Логировать каждое переключение в JSONL
- [ ] VRAM приоритет при давлении: основная 12B > fallback 7B

---

# ═══════════════════════════════════════════════════════════
# ФАЗА 5 — МУЛЬТИПЛЕЕР ← без изменений vs v4.1
# Срок: 2 недели | Приоритет: СРЕДНИЙ
# ═══════════════════════════════════════════════════════════

- [ ] `turn_manager.py` — очередь ходов 1–8 игроков
- [ ] Агрегация заявок → один групповой ход
- [ ] В PyGame: поддержка нескольких окон или передача по очереди

---

# ═══════════════════════════════════════════════════════════
# ФАЗА 6 — СОЗДАНИЕ ПЕРСОНАЖА ← без изменений vs v4.1
# Срок: 1 неделя | Приоритет: СРЕДНИЙ
# ═══════════════════════════════════════════════════════════

- [ ] `character_creation.py` — диалог DM: раса → класс → предыстория → характеристики
- [ ] Начальный SceneState создаётся после выбора стартовой локации

---

# ═══════════════════════════════════════════════════════════
# ФАЗА 7 — СИСТЕМА ПАМЯТИ ← без изменений vs v4.1
# Срок: 2 недели | Приоритет: ВЫСОКИЙ
# ═══════════════════════════════════════════════════════════

> `memory.py` с LayeredMemory и JsonMemoryStore уже есть.

- [ ] `memory_manager.py` — бюджет токенов (< 4096 всегда)
- [ ] Суммаризация через 12B модель (вместо отдельного Saiga/YandexGPT)
- [ ] `knowledge_base.py` — ChromaDB / FAISS для PDF

---

# ═══════════════════════════════════════════════════════════
# ФАЗА 4.5 — ЭПИЗОДИЧЕСКАЯ КАМПАНИЯ ← без изменений vs v4.1
# Срок: 3 недели | Приоритет: СРЕДНИЙ
# После 3A–3C и 7
# ═══════════════════════════════════════════════════════════

- [ ] `mission_state_manager.py`
- [ ] `context_archiver.py`
- [ ] `downtime_engine.py` — использует LifeEngine между сессиями
- [ ] `foreshadowing_system.py`

---

# ═══════════════════════════════════════════════════════════
# ФАЗА 8 — АНАЛИТИКА ← обновлена под PyGame
# Срок: 1 неделя | Приоритет: НИЗКИЙ
# ═══════════════════════════════════════════════════════════

- [ ] `player_stats.py` — kills, gold, урон, репутация, нестандартные действия
- [ ] `session_summary() -> dict` — итоги сессии
- [ ] Экран итогов в PyGame (вместо index.html)

---

# ═══════════════════════════════════════════════════════════
# ФАЗА 9 — WORLD SIMULATOR ← без изменений vs v4.1
# Срок: 1.5 недели | Приоритет: СРЕДНИЙ
# ═══════════════════════════════════════════════════════════

- [ ] Расширить `WorldScheduler.maybe_tick()` — вызывать `LifeEngine.tick()` + `RumorNetwork.spread()`
- [ ] Политические события → SceneChange на уровне фракций
- [ ] Природные явления → SceneChange для уличных локаций

---

# ═══════════════════════════════════════════════════════════
# ФАЗА 10 — RAG ПО PDF ← без изменений vs v4.1
# Срок: 2 недели | Приоритет: СРЕДНИЙ
# ═══════════════════════════════════════════════════════════

- [ ] ChromaDB / FAISS для D&D 5e книг
- [ ] `knowledge_base.py` — поиск правил < 200ms

---

# ═══════════════════════════════════════════════════════════
# ФАЗА 11 — ДИСТРИБУЦИЯ ← обновлена под PyGame
# Срок: 2 недели | Приоритет: НИЗКИЙ
# ═══════════════════════════════════════════════════════════

После перехода на PyGame — дистрибуция меняется.

**Было:** PyInstaller + pywebview (браузер внутри)
**Станет:** PyInstaller + PyGame (нативное приложение)

```
Enigma.exe
├── llama-server.exe  (bundled, запускается автоматически)
├── python312.dll     (embedded)
├── ui/               (PyGame код)
├── backend/          (FastAPI)
└── Models LLM/       (НЕ в bundle — слишком большие, рядом с exe)
```

- [ ] `launcher.py` — PyInstaller entry point
- [ ] Экран загрузки (PyGame splash) пока llama-server стартует
- [ ] `enigma.spec` — включает PyGame, исключает модели

---

# ═══════════════════════════════════════════════════════════
# ФАЗА 12 — ПОЛНЫЕ ПРАВИЛА D&D 5e ← без изменений vs v4.1
# Срок: 3–4 недели | Приоритет: НИЗКИЙ
# ═══════════════════════════════════════════════════════════

- [ ] `spell_system.py` — все заклинания PHB
- [ ] Условия (stunned, paralyzed, poisoned) — влияние на SceneState
- [ ] Отдых — восстановление ресурсов

---

# ═══════════════════════════════════════════════════════════
# ВНУТРЕННИЕ СТАНДАРТЫ (параллельно)
# ═══════════════════════════════════════════════════════════

## A. Кодировка и Windows
- [x] `chcp 65001` в BAT файлах
- [ ] Все новые файлы — `# -*- coding: utf-8 -*-` первой строкой
- [ ] Пути через `Path`, не конкатенацию строк

## B. Логирование
- [x] JSONL с timestamp — реализовано
- [x] Error Interpreter — реализован
- [ ] NPC state changes → JSONL
- [ ] Scene changes → отдельный `scene_changes_YYYYMMDD.jsonl`
- [ ] Rotation: старые > 7 дней → удалять

## C. Тестирование

| Тест | После фазы | Статус |
|------|-----------|--------|
| `test_action_classifier.py` | 2 | ❌ нет |
| `test_combat_math.py` | 2 | ❌ нет |
| `test_npc_cognition.py` | 3A | ❌ нет |
| `test_psyche_engine.py` | 3A | ❌ нет |
| `test_scene_state_manager.py` | S | ❌ нет |
| `test_scene_change_validator.py` | S | ❌ нет |
| `test_life_engine.py` | 3B | ❌ нет |
| `test_karma_engine.py` | 3B | ❌ нет |
| `test_rumor_network.py` | 3C | ❌ нет |
| `test_memory_weight.py` | 3C | ❌ нет |
| `test_turn_manager.py` | 5 | ❌ нет |
| `test_memory_manager.py` | 7 | ❌ нет |
| `test_pygame_api_client.py` | UI | ❌ нет |

## D. Оптимизация

- [ ] SceneState: чтение из RAM кэша, запись только при изменениях
- [ ] Все Python engines < 50ms суммарно
- [ ] VRAM leak < 100MB за 10 часов
- [ ] SceneState snapshot раз в 10 тиков (не каждый ход)

---

# ═══════════════════════════════════════════════════════════
# ИТОГОВЫЙ ПЛАН ПО СРОКАМ v5.0
# ═══════════════════════════════════════════════════════════

| Фаза | Название | Срок | Статус |
|------|----------|------|--------|
| **0** | Стабилизация | — | ✅ ГОТОВО |
| **1** | Streaming + UI | — | ✅ ГОТОВО |
| **2** | Action Classifier + Python движки | — | ✅ ГОТОВО |
| **3A** | NPC Core Psychology + HOTFIX | **3–5 дней** | ⬅️ ЗАВЕРШИТЬ |
| **S** | SceneState: Мир как объект истины | **1.5 нед** | ❌ НОВАЯ |
| **M** | Смена модели: Gemma-3-12B | **3–5 дней** | ❌ НОВАЯ |
| **UI** | PyGame переход | **2–3 нед** | ❌ НОВАЯ |
| **3B** | Living World (параллельно с UI) | **2 нед** | ❌ |
| **3C** | Социальная сеть + память | **2 нед** | ❌ |
| **3D** | Продвинутые взаимодействия | **2–3 нед** | ❌ |
| **5** | Мультиплеер | **2 нед** | ❌ |
| **6** | Создание персонажа | **1 нед** | ❌ |
| **7** | Система памяти | **2 нед** | ⚠️ Частично |
| **4.5** | Эпизодическая кампания | **3 нед** | ❌ |
| **8** | Аналитика | **1 нед** | ❌ |
| **9** | World Simulator (расширение) | **1.5 нед** | ⚠️ Базово |
| **10** | RAG по PDF | **2 нед** | ⚠️ Заготовки |
| **11** | Дистрибуция (.exe) | **2 нед** | ❌ |
| **12** | Полные правила D&D | **3–4 нед** | ⚠️ Частично |

**До первой играбельной версии (3A + S + M + UI + 3B):** ~6–7 недель
**До v1.0 (3A–3C + M + UI + 5 + 6 + 7):** ~4 месяца
**До полного релиза:** ~7–8 месяцев

---

## 🏆 v1.0-playable — обновлённые критерии

```
✅ Игра запускается одним .bat без ошибок
✅ LLM отвечает стримингом, первый токен < 1 сек
✅ Бой считается математически верно (D&D 5e)
✅ Любое действие обрабатывается (SandboxHandler)
[ ] SceneState: мир не придумывается LLM (Фаза S)
[ ] DM нарратив и NPC речь разделены в UI (Фаза UI)
[ ] Одна 12B модель вместо пяти 7B (Фаза M)
[ ] NPC имеют психологию: drives, stress, states (Фаза 3A)
[ ] trust_change/stress_change из NPC ответов применяются
[ ] NPC живут по расписанию, меняют SceneState (Фаза 3B)
[ ] Репутация имеет последствия (KarmaEngine)
[ ] NPC помнят действия игрока (Фаза 3C)
[ ] 1–4 игрока могут играть по очереди (Фаза 5)
[ ] Персонаж создаётся через диалог с DM (Фаза 6)
[ ] Смерть не конец игры (DeathHandler)
```

---

## 📌 Принципы которые никогда не нарушаем (обновлено)

1. **Python считает, LLM рассказывает** — ни один LLM не принимает игровых решений
2. **Python — единственный источник истины о мире** — SceneState нельзя изменить текстом
3. **LLM предлагает изменения, Python утверждает** — ChangeSet через SceneChange
4. **max_loaded = 1** — одна модель в VRAM, строго (8GB аксиома)
5. **Нет запрещённых действий** — есть последствия зафиксированные в SceneState
6. **JSON файлы = источник истины** — LLM не меняет напрямую
7. **Мир живёт** — LifeEngine меняет SceneState без участия игрока и LLM
8. **Честность бросков** — все кубики логируются в JSONL
9. **Windows 11 + русский** — тестировать каждую фичу на реальном железе
10. **Контекст < 4096 токенов** — всегда (SceneState + NPC + python_engines + история)

---

## 🗺️ Обновлённая схема зависимостей

```
                    ┌─────────────────────────────────────────────────────────┐
                    │              PYTHON = ИСТОЧНИК ИСТИНЫ                    │
                    │                                                          │
  ActionClassifier  │  SceneStateManager ──────────────────────────────────── │
  PhysicsValidator  │       ↑    ↑    ↑                                       │
  SandboxHandler ───┼── SceneChange  SceneChange  SceneChange                 │
  CombatMath        │       │           │              │                       │
                    │  SandboxHandler  LifeEngine  NPCSocialMobility          │
                    │                                                          │
                    │  major_npcs.json ──→ NPCCognition ──→ build_npc_prompt  │
                    │                      PsycheEngine                       │
                    │                      ThreatAssessor                     │
                    │                      PerceptionEngine                   │
                    └──────────────────────────────────────┬──────────────────┘
                                                           │
                                                     (факты, не абстракции)
                                                           │
                    ┌──────────────────────────────────────▼──────────────────┐
                    │              LLM = ТОЛЬКО ОПИСАНИЕ                      │
                    │                                                          │
                    │  Gemma-3-12B ─────→ DM нарратив (факты → текст)        │
                    │  Gemma-3-12B ─────→ NPC speech   (психология → речь)   │
                    │  Gemma-3-12B ─────→ Rules check  (механика → ответ)    │
                    └──────────────────────────────────────┬──────────────────┘
                                                           │
                    ┌──────────────────────────────────────▼──────────────────┐
                    │              PyGame UI = РАЗДЕЛЁННЫЕ КАНАЛЫ             │
                    │                                                          │
                    │  narrative_panel ← DM нарратив (атмосфера, последствия) │
                    │  dialogue_panel  ← [NPC имя] "речь NPC"                 │
                    │  status_panel    ← локация | время | SceneState краткий  │
                    │  debug_panel(F12)← NPC состояния, inner_thoughts, VRAM  │
                    └──────────────────────────────────────────────────────────┘
```

---

**Документ:** ENIGMA ROADMAP v5.0
**Обновлено:** Март 2026
**Изменения vs v4.1:** Добавлены фазы S (SceneState), M (Model Migration), UI (PyGame).
Скорректирован порядок: 3A → S → M → UI‖3B → 3C → далее.
Принцип "Python = источник истины" расширен на состояние мира и объекты сцены.

> **Следующий шаг:** Завершить 3A HOTFIX (1–2 дня), затем начать Фазу S.
