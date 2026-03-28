# ENIGMA — Дорожная карта реализации
### Версия 5.2 | Март 2026 | Актуальная

> **Что изменилось vs v5.1:**
> Добавлена фаза S.0 (SceneState в промпт) — теперь первый шаг, до S.4.1.
> Добавлена фаза S.4.2 (ReactionPriority Queue) — NPC реагируют сами.
> Скорректирован порядок внутри 3B.
> Зафиксирован главный архитектурный принцип: система должна работать для
> любого количества персонажей, любых действий, любых событий — без хардкода.

---

## ГЛАВНЫЙ АРХИТЕКТУРНЫЙ ПРИНЦИП (новый, v5.2)

```
Персонажей может быть великое множество.
Разнообразие действий — бесконечно.
Случиться может что угодно.

Отсюда следует:
→ Никакого хардкода конкретных имён, ситуаций, реакций в коде.
→ Всё поведение — из данных (JSON) + общих правил (Python).
→ LLM не знает правил — она получает посчитанный контекст и драматизирует.
→ Новый NPC = новый JSON. Новое действие = новый обработчик по паттерну.
→ Система не должна "знать" про Торнина. Она должна знать про "трактирщик,
   у которого есть работница, и кто-то её ударил".
```

---

## РЕАЛЬНОЕ СОСТОЯНИЕ ПРОЕКТА (Март 2026)

```
ЗАВЕРШЕНО:
✅ start_enigma.bat — полный запуск
✅ Gemma-3-12B-IT-Q4_K_M — единственная модель, все агенты, ctx=2048, ngl=33
✅ FastAPI, SSE Streaming, Frontend (index.html)
✅ ActionClassifier — 14 типов действий, приоритеты
✅ PhysicsValidator — правила мира, bypass через заклинания
✅ CombatMath — D&D 5e математика боя
✅ SandboxHandler — 23 обработчика + TOP-100 нестандартных ситуаций
✅ orchestrator.py — NPC блок + SceneState + recent_session
✅ dm_agent.py — SceneState первым блоком, npc_actions, фильтр Gemma токенов
✅ npc_agent.py — _resolve_active_npcs, JSON парсинг, _strip_stop_tokens
✅ npc_cognition.py — _get_physical_state(), физические факты
✅ major_npcs.json — 5 NPC с психологией, gender, description
✅ mass_npc_templates.json — 10 шаблонов
✅ scene_state_manager.py — SceneStateManager, 7 методов
✅ scene_change.py — SceneChange, ChangeType (10 типов), ChangeValidator
✅ location_templates.json — 5 локаций с time_variants
✅ routes_stream.py — SceneState + recent_session
✅ Promt_AI.json — на русском, подключён к dm_agent
✅ config.py, router.py — gemma_12b для всех агентов
✅ world_scheduler.py — базовый тикер (15 мин)
✅ LayeredMemory + JsonMemoryStore — JSONL сессии
✅ error_interpreter.py — 5 типов ошибок, self-debug
✅ vram_monitor.py — мониторинг, ложных утечек нет

НЕ РЕАЛИЗОВАНО:
⚠️  S.0:   SceneState не передаётся в промпт с позициями/расстояниями/target_npc
⚠️  S.4.1: SandboxHandler не генерирует SceneChange (действия не меняют SceneState)
⚠️  S.4.2: ReactionPriority — NPC не реагируют на события сами
⚠️  LifeEngine, KarmaEngine, SocialMobility, NPCAutoGenerator (фаза 3B)
⚠️  MemoryWeighting, RumorNetwork, BeliefSystem (фаза 3C)
⚠️  PyGame UI (фаза UI)
⚠️  Мультиплеер (фаза 5)
⚠️  Создание персонажа через DM (фаза 6)
⚠️  MemoryManager с бюджетом токенов (фаза 7)
⚠️  RAG по PDF (фаза 10)
```

---

## ЗАВЕРШЁННЫЕ ФАЗЫ

| Фаза | Ключевой результат |
|------|-------------------|
| 0    | Стабильный запуск |
| 1    | SSE стриминг токенов |
| 2    | ActionClassifier, PhysicsValidator, CombatMath, SandboxHandler |
| 3A   | NPC психология, физические состояния, JSON парсинг |
| S    | SceneStateManager, SceneChange (10 типов), location_templates |
| M    | Переход на Gemma-3-12B — одна модель вместо пяти |

---

## ФАЗА S.0 — SCENESTATE В ПРОМПТ (ПЕРВЫЙ ШАГ)
### Срок: 2 дня | Приоритет: КРИТИЧЕСКИЙ | Делать до S.4.1

**Проблема:** SceneState существует, но модель его не видит. Она не знает
кто где стоит, к кому обращается игрок, какое расстояние между NPC.
Результат: Люся "протирает столы в 3 метрах" пока игрок стоит перед ней
на коленях.

**Почему это важно:** Без S.0 — S.4.1 бессмысленен. Мы будем обновлять
SceneState, но модель об этом не узнает.

**Почему это системная проблема, а не частный случай:**
Без явного контекста позиций — модель будет галлюцинировать расположение
для ЛЮБОГО персонажа и ЛЮБОЙ сцены. Это не баг с Люсей — это структурный
провал передачи контекста.

### Задачи

**dm_agent.py → _build_prompt() — первый блок:**

```python
scene_block = build_scene_block(context.get("scene_state"))
# Структура scene_block:
# Локация + время + освещение
# Игрок: положение, расстояния до ключевых объектов/NPC, ongoing-действия
# Активные NPC: имя | активность | расстояние от игрока | статус
# Объекты: имя | состояние | позиция
# player_target_npc: "Люся" | None
# player_target_object: "свечи" | None
# ВАЖНО-блок: жёсткие правила о том, кто отвечает и почему
```

- [ ] `build_scene_block(scene_state) -> str` — универсальная функция,
      работает для любого количества NPC и объектов
- [ ] Добавить `scene_block` первым в `_build_prompt` (dm_agent и npc_agent)
- [ ] Тот же блок в npc_agent с фокусом на конкретном NPC:
      "Ты — {npc_name}. Игрок на расстоянии {dist} м. Обращается к тебе."

**orchestrator.py / sandbox_handler.py — парсинг цели:**

- [ ] `extract_player_target(action_text) -> (target_npc, target_object)`
      Паттерн-матчинг без хардкода имён — работает на любых именах:
      "говорю с {именем}", "смотрю на {объект}", "перед {npc}" и т.д.
- [ ] Результат кладётся в SceneState:
      `scene_state["player_target_npc"]` и `["player_target_object"]`

**Promt_AI.json — жёсткие правила реакций:**

- [ ] Если `player_target_npc` задан → только этот NPC отвечает
- [ ] Если игрок физически взаимодействует с NPC → этот NPC не может
      одновременно действовать в другом месте (проверять через SceneState)
- [ ] Все расстояния и положения из SceneState = абсолютная правда

**npc_agent.py — постфильтр:**

- [ ] `_filter_npc_response(response, target_npc) -> response`
      Если speaker ≠ target_npc → вернуть "молчит, не ко мне обратились"
      Грубая защита от галлюцинаций модели

### Критерий готовности S.0

```
Игрок: "Я на коленях перед Люсей"
→ SceneState: player_target_npc="Люся", player_position="на коленях"
→ Промпт: Люся на расстоянии 0.5м, active, player стоит перед ней
→ Люся отвечает. Торнин молчит.
→ Модель НЕ пишет "Люся протирает столы" — в SceneState она занята с игроком.

Тот же тест для любого нового NPC без изменений кода.
```

---

## ФАЗА S.4.1 — SANDBOX → SCENESTATE
### Срок: 2–3 дня | Приоритет: ВЫСОКИЙ | После S.0

SceneStateManager работает, но действия игрока не попадают в SceneState.
Украл свечи? SceneState не знает. Сломал стол? SceneState не знает.

**Файл:** `backend/app/services/game/sandbox_handler.py`

**Принцип:** Каждый `success=True` в SandboxHandler должен порождать
SceneChange. Не для конкретных предметов — для любых объектов/NPC
через обобщённую логику по типу действия.

- [ ] Добавить `scene_changes: list[SceneChange] = []` в `SandboxResult`
- [ ] Универсальные генераторы SceneChange по типу действия:

  | Тип действия | SceneChange при success=True |
  |---|---|
  | STEAL | OBJECT_REMOVE(target) + INVENTORY_ADD(player, target) |
  | BREAK / DESTROY | OBJECT_STATE(target, "damaged" / "broken") |
  | LOCKPICK (успех) | OBJECT_STATE(target_door, "open") |
  | CAPTURE | NPC_STATE(target, "captured") |
  | BRIBERY | INVENTORY_REMOVE(player, "gold", amount) |
  | INTIMIDATE | NPC_POSITION(target, activity="retreating") |
  | POISON | NPC_STATE(target, append="poisoned") |
  | ENVIRONMENTAL | EFFECT_ADD("fire_on_{target}") |

  Все target берутся из `player_target_npc` / `player_target_object` SceneState.
  Имена не хардкодятся.

- [ ] В `orchestrator._run_python_engines()`:
      `self.scene_manager.apply_changes(result.scene_changes)`

- [ ] Тест: украсть свечи → SceneState обновлён →
      следующий ход DM описывает "в таверне темно"

---

## ФАЗА S.4.2 — REACTION PRIORITY QUEUE
### Срок: 2–3 дня | Приоритет: ВЫСОКИЙ | После S.4.1

**Проблема:** NPC реагируют только если к ним обратились. Но Торнин
обязан вмешаться, если кто-то бьёт его работницу. Стражник реагирует
на кражу раньше жертвы. Муж защищает жену.

**Ключевой принцип:** Python решает — КТО, КОГДА и ПОЧЕМУ должен среагировать.
LLM только озвучивает. Система не знает "Торнин" — она знает
"npc с should_defend_worker=True и worker_id=жертвы".

**Создать:** `backend/app/services/npc/reaction_priority.py`

```python
class ReactionPriority:
    """
    Считает приоритет реакции NPC на событие.
    Работает для любого NPC и любого SceneChange.
    """
    THRESHOLDS = {
        "must_react":    60,   # NPC обязан вмешаться (Торнин видит избиение)
        "will_react":    30,   # NPC реагирует (сосед слышит крик)
        "may_react":     15,   # NPC замечает (прохожий оглядывается)
    }

    def calculate(self, npc: NPC, scene_state: SceneState,
                  scene_change: SceneChange) -> int:
        score = 0

        # 1. Прямое воздействие на NPC или его "значимого другого"
        if scene_change.directly_affects(npc):
            score += 80
        if scene_change.affects_npc_in_relation(npc, relation="worker"):
            score += 70
        if scene_change.affects_npc_in_relation(npc, relation="friend"):
            score += 50
        if scene_change.affects_npc_in_relation(npc, relation="enemy"):
            score += 20  # может обрадоваться или вмешаться из выгоды

        # 2. Соответствие драйвам NPC
        #    (работает для любого NPC с любыми drives в JSON)
        score += self._drives_score(npc.drives, scene_change)

        # 3. Должностные обязанности (из NPC JSON, не хардкод)
        score += self._duty_score(npc.role, scene_change)

        # 4. Расстояние и видимость
        distance = scene_state.distance_between(npc.id, "player")
        score -= int(distance * 3)
        if not scene_state.has_line_of_sight(npc.id, "player"):
            score -= 20

        # 5. Психологическое состояние
        if npc.psyche["state"] == "broken":
            score -= 30
        if npc.psyche["stress"] > 80:
            score -= 15

        return max(0, score)

    def _drives_score(self, drives: dict, change: SceneChange) -> int:
        score = 0
        if drives.get("control", 0) > 0.6 and change.is_disorder():
            score += 40
        if drives.get("significance", 0) > 0.5 and change.is_disrespect():
            score += 35
        if drives.get("fear", 0) > 0.4 and change.is_danger():
            score += 50
        if drives.get("desire", 0) > 0.6 and change.is_opportunity():
            score += 25
        return score

    def _duty_score(self, role: str, change: SceneChange) -> int:
        # Роли из NPC JSON, не хардкод
        duty_map = {
            "innkeeper":   {"protect_worker": 70, "stop_violence": 60},
            "guard":       {"stop_theft": 80, "stop_violence": 80},
            "merchant":    {"protect_goods": 70},
            "priest":      {"stop_violence": 50, "heal_wounded": 60},
        }
        duties = duty_map.get(role, {})
        for trigger, bonus in duties.items():
            if getattr(change, f"is_{trigger}", lambda: False)():
                return bonus
        return 0
```

**В orchestrator.py — после SandboxHandler:**

```python
# Собираем реакции для всех активных NPC (любое их количество)
reactions = []
for npc in scene_state.active_npcs:
    priority = ReactionPriority().calculate(npc, scene_state, scene_change)
    if priority >= ReactionPriority.THRESHOLDS["will_react"]:
        reactions.append((npc, priority))

reactions.sort(key=lambda x: x[1], reverse=True)
context["forced_first_speaker"] = reactions[0][0].id if reactions else None
context["npc_reaction_order"] = [npc.id for npc, _ in reactions[:3]]
```

**Задачи:**

- [ ] Создать `reaction_priority.py` с полным классом
- [ ] Добавить в SceneChange методы: `directly_affects()`,
      `affects_npc_in_relation()`, `is_disorder()`, `is_violence()` и др.
- [ ] Интегрировать в orchestrator после SandboxHandler
- [ ] Добавить в промпт DM/NPC блок правил:
      "ПРАВИЛО РЕАКЦИЙ: forced_first_speaker говорит первым.
       NPC с приоритетом > 60 МОЖЕТ перебить. Максимум 3 реплики за ход."
- [ ] Тест: удар любого NPC → хозяин (роль innkeeper) вмешивается автоматически

### Критерий готовности S.4.2

```
Для ЛЮБОЙ пары NPC, где один является "работником" другого:
→ Удар по работнику → хозяин вмешивается (python посчитал priority=85)
→ Кража в таверне → стражник реагирует первым (priority=80)
→ Случайный прохожий молчит (priority=12, ниже порога)

Добавление нового NPC с role="guard" в JSON →
поведение работает автоматически, без изменений кода.
```

---

## ФАЗА 3B — ЖИВОЙ МИР
### Срок: 2 недели | Приоритет: ВЫСОКИЙ | После S.4.2

LifeEngine двигает NPC по расписанию и пишет SceneChange в SceneState.
Мир живёт без участия игрока — каждые 15 минут (WorldScheduler тик).

**Принцип:** Ни один NPC не хардкодится в движках. Расписание, рутина,
случайные события — всё из JSON. Добавить нового NPC = добавить JSON.

### 3B.0 — NPCAutoGenerator (ПЕРВЫМ в 3B)

**Создать:** `backend/app/services/npc/npc_generator.py`

LifeEngine должен двигать NPC — значит NPC должны существовать
до первого контакта. Lazy generation из mass_npc_templates.json.

- [ ] `generate_on_demand(template_id, location) -> NPC`
      При первом контакте — создаём, сохраняем в `data/npcs/generated/`
- [ ] `generate_batch(location) -> list[NPC]`
      При входе в локацию — пре-генерируем mass NPC фоново
- [ ] Уникальные имена из пула (не "NPC_1", "NPC_2")
- [ ] Случайная вариация параметров в пределах шаблона (±15%)

### 3B.1 — LifeEngine

**Создать:** `backend/app/services/npc/life_engine.py`

```
Tier:
Major → полная симуляция каждый тик (расписание + события + стресс)
Minor → расписание + случайные события раз в 3 тика
Mass  → только флаги присутствия (<1ms)
```

- [ ] `tick(campaign_id) -> list[SceneChange]` — основной цикл
- [ ] `update_routine(npc, current_time) -> SceneChange`
      Позиция из `npc.routine.schedule` — работает для любого расписания
- [ ] `get_activity_description(npc) -> str` — текст для промпта DM
- [ ] `check_random_events(npc) -> list[SceneChange]` — 5% шанс/тик
- [ ] `recover_stress_tick(npc) -> None` — -5/тик безопасности, -15 сон
- [ ] Интеграция: `world_scheduler.maybe_tick()` → `life_engine.tick()`
      → `scene_manager.apply_changes()`

### 3B.2 — KarmaEngine

**Создать:** `backend/app/services/npc/karma_engine.py`

- [ ] `update_reputation(player, action_type, outcome)`
      Репутационные теги: "hero", "cruel", "thief", "peacemaker" и др.
- [ ] Цепные эффекты: reputation_tag → delta для ВСЕХ NPC по формуле
      (не хардкод конкретных NPC — формула по tier и faction)
- [ ] `schedule_delayed_event(trigger, delay_ticks, event_type)`
      "Торнин запомнит это" → через 3 тика SceneChange с последствием

### 3B.3 — SocialMobility

**Создать:** `backend/app/services/npc/social_mobility.py`

- [ ] Захват → NPC state="coerced", SceneChange добавляет "chains"
      в visible_markers (влияет на perceived_status других NPC)
- [ ] Освобождение → убирает "chains"
- [ ] Слом воли → state="broken", SceneChange обновляет loyalty_true
- [ ] Все переходы — через SceneChange, не прямая мутация JSON

### Критерии готовности 3B

```
[ ] Любой NPC с заполненным schedule.json уходит/приходит по расписанию
[ ] Игрок приходит в локацию ночью → NPC помечен как "sleeping", DM сообщает
[ ] Mass NPC создаются при первом контакте из шаблона
[ ] Репутация "cruel" → все NPC с faction != "player" получают fear_delta
[ ] test_life_engine.py, test_karma_engine.py — зелёные
```

---

## ФАЗА UI — ПЕРЕХОД НА PYGAME
### Срок: 2–3 недели | Параллельно с 3B

index.html не разделяет каналы — JSON торчит в нарративе.
PyGame: DM нарратив и NPC речь в отдельных панелях.

### Архитектура

```
Enigma/ui/
├── launcher.py       ← точка входа
├── game_window.py    ← главное окно
├── api_client.py     ← SSE клиент (Python, не браузер)
└── panels/
    ├── narrative.py  ← DM нарратив (стриминг токенов)
    ├── dialogue.py   ← NPC [Имя] "речь" — динамически, любое кол-во NPC
    ├── status.py     ← локация | время | HP | условия
    ├── input.py      ← ввод + Enter
    └── debug.py      ← F12: NPC trust/stress/inner_thought + SceneState
```

### Layout

```
┌─────────────────────────────────────────────────────┐
│ ENIGMA          Таверна «Серебряный Волк» | 22:00   │
├──────────────────────────┬──────────────────────────┤
│  DM НАРРАТИВ             │  ДИАЛОГИ NPC             │
│  (стриминг)              │  [Торнин] "Деньги..."    │
│                          │  [Люся]   "Что угодно?"  │
│                          │  (любое кол-во NPC)      │
├──────────────────────────┴──────────────────────────┤
│  > Ваше действие...                      [▶ Ответ] │
└─────────────────────────────────────────────────────┘
```

### Шаги

- [ ] `pip install pygame`
- [ ] `ui/launcher.py`, `ui/api_client.py` — SSE клиент без браузера
- [ ] 5 панелей (narrative, dialogue, status, input, debug)
- [ ] `routes_stream.py`: добавить события `type: "npc"` и
      `type: "scene_state"` в `done`-событие
- [ ] `start_enigma.bat` → launcher.py вместо браузера
- [ ] index.html оставить как fallback

---

## ФАЗА 3C — СОЦИАЛЬНАЯ СЕТЬ И ПАМЯТЬ NPC
### Срок: 2 недели | После 3B

- [ ] `memory_weight.py` — MemoryWeighting, decay, relevance
      События теряют вес со временем, но сильные — остаются навсегда
- [ ] `rumor_network.py` — слухи по радиусу, искажение при передаче
      "Игрок убил торговца" → за 3 тика доходит до стражника, искажается
- [ ] BeliefSystem — убеждения NPC, триггеры манипуляции через drives
- [ ] InconsistencyDetector — NPC не может быть в двух местах

---

## ФАЗА 3D — ПРОДВИНУТЫЕ ВЗАИМОДЕЙСТВИЯ
### Срок: 2–3 недели | После 3A–3C

- [ ] ActionLayerEngine — 4 уровня (PHYSICAL / SOCIAL / LOGICAL / METAPHYSICAL)
      Одно действие может затронуть несколько уровней одновременно
- [ ] ShockEngine — когнитивный диссонанс NPC при противоречии убеждениям
- [ ] DriveMatcher — триггеры манипуляции через соответствие drives игрока
      и NPC (работает для любых drives, не хардкод)

---

## ФАЗА 5 — МУЛЬТИПЛЕЕР
### Срок: 2 недели

- [ ] `turn_manager.py` — очередь 1–8 игроков
- [ ] ReactionPriority учитывает всех игроков сразу при расчёте
- [ ] В PyGame: панель "чья очередь", кнопка "передать ход"
- [ ] DM получает действия всего раунда и отвечает на все сразу

---

## ФАЗА 6 — СОЗДАНИЕ ПЕРСОНАЖА
### Срок: 1 неделя

- [ ] `character_creation.py` — диалог DM: раса → класс → предыстория
      → характеристики (4d6 / стандартный массив / point buy)
- [ ] SceneState создаётся после выбора стартовой локации
- [ ] Начальные visible_markers из снаряжения класса

---

## ФАЗА 7 — СИСТЕМА ПАМЯТИ
### Срок: 2 недели

- [ ] `memory_manager.py` — бюджет токенов < 4096 всегда
      4 уровня: оперативная (500 tok) → сессия (1000) → кампания (300) → мир (300)
- [ ] Суммаризация через Gemma-12B (та же модель, economy mode)
- [ ] `knowledge_base.py` — ChromaDB / FAISS для PDF
- [ ] RAG-запрос только если action содержит lore-паттерн

---

## ФАЗА 4.5 — ЭПИЗОДИЧЕСКАЯ КАМПАНИЯ
### Срок: 3 недели | После 3A–3C и 7

- [ ] mission_state_manager, context_archiver
- [ ] downtime_engine — события между сессиями
- [ ] foreshadowing_system — DM сеет подсказки заранее

---

## ФАЗЫ 8–12 (низкий приоритет)

| Фаза | Название | Срок |
|------|----------|------|
| 8    | Аналитика (PlayerStats, итоги сессии) | 1 нед |
| 9    | World Simulator расширение | 1.5 нед |
| 10   | RAG по PDF (ChromaDB/FAISS) | 2 нед |
| 11   | Дистрибуция (.exe / PyInstaller) | 2 нед |
| 12   | Полные правила D&D 5e | 3–4 нед |

---

## ИТОГОВЫЙ ПЛАН

| Фаза | Срок | Статус |
|------|------|--------|
| 0–M | — | ✅ ГОТОВО |
| **S.0** | **2 дня** | **⬅️ ПЕРВЫЙ** |
| S.4.1 | 2–3 дня | ❌ |
| S.4.2 | 2–3 дня | ❌ |
| 3B | 2 нед | ❌ |
| UI | 2–3 нед (параллельно 3B) | ❌ |
| 3C | 2 нед | ❌ |
| 3D | 2–3 нед | ❌ |
| 5 | 2 нед | ❌ |
| 6 | 1 нед | ❌ |
| 7 | 2 нед | ⚠️ частично |
| 4.5 | 3 нед | ❌ |
| 8–12 | — | ❌/⚠️ |

**До играбельной v1.0 (S.0 + S.4.1 + S.4.2 + 3B + UI):** ~6–7 недель
**До v1.0 полной (3A–3C + UI + 5 + 6 + 7):** ~3.5 месяца
**До релиза:** ~7 месяцев

---

## ПРИНЦИПЫ (финальные, v5.2)

1. **Python считает — LLM рассказывает**
2. **Python — единственный источник истины о мире**
3. **LLM предлагает изменения (SceneChange), Python утверждает**
4. **max_loaded = 1** — одна модель в VRAM (Gemma-3-12B, ~7.5 GB)
5. **Нет запрещённых действий** — есть последствия в SceneState
6. **JSON файлы = источник истины** — никаких хардкодов имён в коде
7. **Мир живёт** — LifeEngine меняет SceneState без LLM
8. **Честность бросков** — все кубики в JSONL
9. **Windows 11 + русский** — тестировать на железе
10. **Контекст < 4096 токенов всегда**
11. **Система generic** — новый NPC = новый JSON, новое поведение = новое правило,
    никакой логики "только для Торнина" или "только для таверны"
12. С "claude.ai" работаем так: Либо: "Покажи мне файл X" — я вставляю содержимое, ты говоришь что куда. Либо: "Вставь вот этот код в файл X, между строкой ... и строкой ..." — я иду и делаю. Либо: "В файле X найди функцию def handle_intimidate и замени её целиком вот на это." Никаких "вот общая идея" — только точные хирургические инструкции. 

---

**Документ:** ENIGMA ROADMAP v5.2
**Обновлено:** Март 2026
**Следующий шаг:** Фаза S.0 — SceneState в промпт DM и NPC
