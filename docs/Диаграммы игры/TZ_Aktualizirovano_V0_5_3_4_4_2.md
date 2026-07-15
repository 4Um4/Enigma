# ТЗ (актуализировано): Эмерджентная таверна — финальная интеграция, мини-игра «Секреты Люси» и недостающие геймплейные механики

**Адресат:** LLM-архитектор (преемник проекта)
**Автор:** создатель Enigma (человек-режиссёр, не программист)
**Дата оригинала:** 12 июля 2026
**Дата актуализации:** 13 июля 2026 (ревизия 3 — после разбора почему NPC-NPC диалоги не возникают)
**Версия проекта:** Enigma V.0.5.3.4.4
**Документ-источник:** `docs/Диаграммы игры/TZ_Emerdzhentnaya_Taverna_i_Miniigra_Sekrety_Lyusi.md` (оригинал от 12 июля)
**Документ-источник 2:** `docs/Диаграммы игры/ТЕХНИЧЕСКОЕ ЗАДАНИЕ Миниигра «Таверна Серебряный Волк».md`

---

## 0. ЧТО ЭТОТ ДОКУМЕНТ И ЗАЧЕМ

Этот документ — **актуализация** единого плана от 12 июля на основе полного аудита кодовой базы V.0.5.3.4.4, логов runtime (`cds_backend.log`, `enigma_20260713.jsonl`) и сессии создателя от 13 июля 06:52.

**Ревизия 3 (та, что у вас в руках)** добавляет §3.4-3.7 — анализ почему NPC-NPC диалоги **не возникают**, даже если persistence и таймер починены. Логи показывают: DecisionHub генерит ~73 вербальных intent'а за сессию (request_service, offer_job, spread_rumor, talk, и т.д.), но `Фаза 6: 0 intents` каждый тик — `communication_intents` пуст. Без этого фикса NPC будут двигаться (после §3.3) но **молча** — никакой социальной эмерджентности.

Также добавлен §3.7 — **Автономный Мир-Контракт (AWC)**: 8 пунктов (A-H), которые **гарантируют** что мир живёт самостоятельно без ввода игрока. Это спецификация первостепенной задачи создателя.

**Ревизия 2** переписала §3.1 после разбора логов. Оказалось, что DM agent работает (реплики генерируются) — реальный корень проблемы в persistence: каждый idle_tick падает на Phase 10 из-за `TypeError: Type List cannot be instantiated` в `sqlite_persistence_adapter.py:84`. Симуляция проходит фазы 0-9, но не сохраняется — на следующем тике откат, NPC визуально стоят.

Аудит вскрыл **пять** категорий находок:

1. **Корневой баг симуляции** (§3.1) — `TypeError` в persistence-слое. Каждый idle_tick завершается крашем, состояние не сохраняется, NPC стоят как вкопанные.
2. **Архитектурный дефект real-time loop** (§3.2) — idle_tick привязан к UI-таймеру с интервалом 2-30 сек, блокируется `action_queue.pending_count()`, ставится на паузу на 1 сек после DM-ответа. Мир тикает медленно и рывками.
3. **DecisionHub не генерирует движение в idle** (§3.3) — `_MOVE_INTENTS = {"approach", "flee"}` whitelist; все остальные intents (block_path, ambush, seek_ally, offer_job, request_service, call_for_help, spread_rumor) — декоративные, не создают MovementIntent.
4. **★NEW★ NPC-NPC диалоги не возникают** (§3.4) — `communication_intents = 0` в каждом idle_tick, несмотря на вербальные intents от DecisionHub. Цепочка `DecisionHub → CommunicationIntent → pending_tasks → TaskScheduler → DialogueExecutor` обрывается.
5. **★NEW★ Цикл восприятия не замыкается** (§3.6) — даже если диалог возникнет, NPC_B не воспринимает реплику NPC_A: нет подписчика на `NPC_SAID_TO_NPC`, нет `NpcDialogueSubscriber`. Цикл «нужда → диалог → эмоция → belief → новый диалог» разомкнут.

Дополнительно:
6. **17 брошенных .py файлов** (5 упомянуты оригиналом + 12 новых), **3 устаревших wiring-утверждения** оригинала (combat_math, ChangeType.INVENTORY, TaskScheduler threshold).

Кроме актуализации, в документ добавлен **Этап 4: недостающие геймплейные механики** (§7) — 30+ конкретных механик, без которых игра остаётся «болванчиками ходят туда-сюда». Это ответ на прямой запрос создателя: «подумай и ответь каких механик не хватает игре чтобы она ощущалась по настоящему интересной».

**Что удалено как устаревшее:**
- §2.2 строка `combat_math.py` — уже подключён к ImpactEngine (`impact_engine.py:50,53,55-68`)
- §2.2 строка `ChangeType.INVENTORY` — ветка уже реализована в `scene_state_manager.py:1557-1571`
- §3.1 строки C1, C2, C3, C5, C6, C7, C8, C9, C10, C11, C12, C13, C14 оригинала — все починены, остались только `# C{n} FIX` комментарии
- §3.4 silent exception suppression — большинство уже заменено на logger.warning, осталось 1 место

**Что переписано в ревизии 2:**
- §3.1 — старая диагностика (SceneStateManager UnboundLocalError) была неверной. DM agent в реальности работает (реплики генерируются, LLM вызывается). Реальный корень — `TypeError` в persistence-слое, который не даёт симуляции сохранять состояние между idle_tick'ами. Старый патч удалён, вместо него — новый §3.1 с правильной диагностикой.

**Что добавлено:**
- §3.1 — **корневой runtime-баг** `TypeError: Type List cannot be instantiated` в `sqlite_persistence_adapter.py:84` (ревизия 2)
- §3.2 — **архитектурный дефект real-time loop** (idle_tick привязан к DM-ответу) (ревизия 2)
- §3.3 — **DecisionHub idle movement gap** (только approach/flee создают MovementIntent) (ревизия 2)
- §3.4 — **★NEW★ communication_intents=0** — NPC-NPC диалоги не возникают, диагностический план + быстрый фикс (ревизия 3)
- §3.5 — **★NEW★ TaskScheduler + LLM throttle** — DialogueQueue с rate limiting, иначе LLM умрёт от нагрузки (ревизия 3)
- §3.6 — **★NEW★ NpcDialogueSubscriber** — замыкание цикла восприятия (PerceptionEngine → Emotion → Memory → Belief → Relationship) (ревизия 3)
- §3.7 — **★NEW★ Автономный Мир-Контракт (AWC)** — 8 пунктов (A-H), спецификация «мир живёт сам», + `verify_autonomous_world.py` скрипт (ревизия 3)
- §2.2 — полная таблица 17 брошенных .py файлов (а не 5 как в оригинале)
- §3.12 — матрица решений по 5 брошенным модулям из оригинала
- §7 — **новый Этап 4** с 30+ геймплейными механиками
- §9 — обновлённые чек-листы с проверками для новых пунктов (включая AWC)

---

## 1. ЖЕЛЕЗНОЕ ПРАВИЛО: НИКАКИХ СКРИПТОВ

*Перенесено из оригинала без изменений — правило актуально.*

Это **архитектурный закон**, а не пожелание.

**Что запрещено:**
- Скриптованные сцены вида «если NPC_A встретил NPC_B в локации X в интервале T → запустить диалог Y».
- Флаги `quest_lusya_met = true`, `trigger_tavern_fight = true`.
- Хардкоженные реплики NPC, привязанные к событиям.
- `ScriptedSceneRunner` с YAML-последовательностями действий.
- Любые условные конструкции, которые предопределяют **что именно** произойдёт.

**Что разрешено:**
- **Правила** — общие законы, из которых сцены **возникают**, а не задаются.
- **Drives** — внутренние нужды NPC (голод, страх, привязанность, любопытство), которые толкают к действию.
- **Реакции** — ответ PerceptionEngine на воспринятое событие, преобразованный через эмоции в новый intent.
- **Эмерджентные матчи** — детекторы типа «если два NPC в одном кластере и friction > порог → возможность DIALOGUE». Решение принимает DecisionHub через utility-скоринг, а не if-then.

**Тест правила:** если из системы можно удалить **конкретного** NPC или **конкретную** сцену — и она продолжит работать, но с другими драмами — правило соблюдено. Если удаление ломает игру — это скрипт.

---

## 2. КОНТЕКСТ: ЧТО ЕСТЬ НА САМОМ ДЕЛЕ

### 2.1. Подсистемы, которые СУЩЕСТВУЮТ и работают

*Скорректировано против оригинала — добавлены combat_math, ChangeType.INVENTORY, TaskScheduler.*

- **TickOrchestrator** — 11 фаз game loop (`backend/app/services/tick_orchestrator.py:515-532`).
- **DecisionHub** — utility-скоринг на основе NPCState + Drives + EventContext (`backend/app/services/npc/decision_hub.py`).
- **LifeEngine** — расписания NPC, need-driven движение, random events (`backend/app/services/npc/life_engine.py`).
- **AffectiveIntegrator + EmotionTransition** — эмоции как leaky integrator (`backend/app/services/affective/`).
- **PerceptionEngine + InterpretationEngine** — восприятие событий NPC.
- **BeliefCrystallizationEngine + PatternDetector + CrystallizedBeliefStore** — формирование убеждений.
- **LayeredMemory + L1Chronicle + WorkingMemory** — память NPC (SQLite).
- **SocialEngine + ReputationEngine + RelationshipStore** — слухи, репутация, отношения (SSOT 0-100).
- **DialogueExecutor + TaskScheduler + DialogueMaterializer** — материализация реплик. TaskScheduler берёт задачи из `pending_tasks` без intensity-фильтра (оригинальное утверждение про threshold mismatch — устарело).
- **CombatSubscriber + ImpactEngine + InjuryProcessor + combat_math** — боёвка с D&D 5e бросками (`impact_engine.py:50,53` импортирует и вызывает `attack_roll`).
- **WorldTickEngine.compute_proactive_decisions** — вызывается из `phase_2_world_tick.py:82` каждый N-й тик. NPC могут автономно: BLOCK_PATH, AMBUSH, SEEK_ALLY, OFFER_JOB, REQUEST_SERVICE, SPREAD_RUMOR, CALL_FOR_HELP, CHANGE_ROLE.
- **ChangeType.INVENTORY** — ветка apply_changes реализована в `scene_state_manager.py:1557-1571`.
- **DmAgent + DMOrchestrator + DMRouter + R3 DIRECT MODE** — DM как единственный источник речи. **СМ. §3.1 — критический баг в DM agent.**
- **PlayerCognition pipeline** — 9 слоёв восприятия игрока.
- **Frontend**: top-down рендер, speech bubbles, journal (J), console (Ё), time scale (1-4), idle_tick 2-30 сек.

### 2.2. Брошенные .py файлы (17 штук — полный список)

Аудит graf-а импортов выявил 17 `.py` файлов в проекте, которые **не импортируются ни одним другим файлом**. Из них 5 упомянуты в оригинальном ТЗ (§2.2), 12 — не упомянуты. Размер и контекст приведены в таблице.

| # | Файл | Размер | Оригинал ТЗ | Что делать |
|---|---|---|---|---|
| 1 | `backend/app/services/character/front_applicator.py` | 4 220 байт | упомянут | **Удалить** или соединить с `front_engine.py` — последний тоже брошен, цепочка мертва целиком |
| 2 | `backend/app/services/character/front_engine.py` | 9 072 байт | упомянут | То же — entire FrontEngine/FrontApplicator chain не имеет внешних callers |
| 3 | `backend/app/services/game_loop/npc_state_helpers.py` | 7 182 байт | упомянут | **Подключить** — функции `apply_npc_state_updates` и `write_npc_memory` нужны в game_loop Phase 8 |
| 4 | `backend/app/services/npc/reaction_priority.py` | 9 886 байт | упомянут | **Подключить** в `reaction_subscriber.py` — упорядочивание реакций NPC |
| 5 | `backend/app/services/npc/role_transition.py` | 9 740 байт | упомянут | **Подключить** в долгосрочную симуляцию (раз в игровую неделю) |
| 6 | `backend/app/services/perception/perceptual_attention_service.py` | 4 046 байт | упомянут | **Подключить** в `perception_projector.py` — attention budget |
| 7 | `backend/lint_project.py` | 33 092 байт | не упомянут | **Оставить** — это утилита линтера, запускается вручную |
| 8 | `backend/run_terminal_dm.py` | 20 460 байт | не упомянут | **Оставить** — standalone CLI для отладки DM |
| 9 | `backend/pathfinding.py` | 13 856 байт | не упомянут | **Удалить** — дублирует `spatial/movement_engine.py`, не вызывается |
| 10 | `backend/movement_system.py` | 6 511 байт | не упомянут | **Удалить** — дублирует `spatial/`, не вызывается |
| 11 | `backend/intent_parser.py` | 6 058 байт | не упомянут | **Удалить или подключить** — парсер интентов, возможно нужен в `action/dm_router.py` |
| 12 | `backend/app/services/game/physics_validator.py` | 8 363 байт | не упомянут | **Подключить** в `movement_engine.py` для валидации траекторий |
| 13 | `backend/app/core/error_logger.py` | 3 405 байт | не упомянут | **Подключить** — централизованный error logger, сейчас каждый модуль пишет свой |
| 14 | `backend/app/domain/tasks.py` | 3 225 байт | не упомянут | **Удалить или слить** с `app/domain/execution.py` — дублирование |
| 15 | `backend/app/domain/behavior.py` | 3 133 байт | не упомянут | **Подключить** в DecisionHub — там есть полезные enum-ы поведения |
| 16 | `backend/app/models/locomotion.py` | 2 693 байт | не упомянут | **Подключить** в `movement_engine.py` или удалить |
| 17 | `backend/app/models/candidates.py` | **0 байт** | не упомянут | **Удалить** — пустой файл |

**Итог:** 4 удалить, 1 пустой удалить, 6 подключить, 2 оставить как утилиты, 4 требуют решения архитектора.

### 2.3. Главная боль: мёртвая таверна — КОРНЕВАЯ ПРИЧИНА НАЙДЕНА

Создатель 13 июля 06:52 запустил игру и описал симптомы:

> «NPC стоят как вкопанные, время не тикает сколько бы секунд не проходило... При чём тут DM ЛЛМ? Я наоборот описывал что после моего ввода и ответа DM игра сдвигается, но только буквально на один тик... А игра должна быть в реальном времени, всё должно двигаться и жить непрерывно!!! А этого не происходит.»

Аудит `backend/logs/cds_backend.log` (не `enigma_20260713.jsonl` — там только DM agent логи, а полная картина в cds_backend) показал, что **каждый idle_tick падает** с одной и той же ошибкой:

```
2026-07-13 06:52:32,488 ERROR [TICK_CRASH] campaign=Open_road tick=5 
  error=Type List cannot be instantiated; use list() instead

Traceback:
  tick_orchestrator.py:462 → _run_core_phases(ctx)
  tick_orchestrator.py:532 → _phase_10_persistence(ctx)
  commit_phase.py:116 → orchestrator._scene_manager.commit(...)
  scene_state_manager.py:1795 → self._persistence.atomic_commit(...)
  sqlite_persistence_adapter.py:196 → self._upsert(f"runtime:{campaign_id}", npc_states)
  sqlite_persistence_adapter.py:81 → json.dumps(value, default=lambda o: List[Any](o) if isinstance(o, set) else str(o))
  typing.py:1330 → raise TypeError(f"Type {self._name} cannot be instantiated")
```

Эта ошибка повторяется **каждый тик** сессии 13 июля (10+ раз за 40 секунд). Симптомы создателя объясняются полностью:

- **NPC стоят как вкопанные** → Phase 0-9 проходят, LifeEngine создаёт 4-6 spatial changes, DecisionHub принимает решения (видно в логах: `maid_lusya: intent=Intent.seek_ally`, `blacksmith_orm: intent=Intent.request_service` и т.д.), но Phase 10 (persistence) крашится — изменения **не сохраняются в SQLite**, на следующем тике scene_state откатывается к предыдущему состоянию.
- **Время не тикает** → `_advance_idle_time` отрабатывает в Phase 0.5 и обновляет `scene_state["game_time_seconds"]` в памяти, но commit в SQLite падает, и при следующем idle_tick `lock_for_tick` читает **старое** время. Часы стоят.
- **Только DM-ответ сдвигает игру** → игрок вводит текст → POST `/api/game/{id}/input` → DM agent генерирует реплику → фронтенд применяет snapshot из ответа в `game_screen.py:1177-1184` (через `_action_ws = result.response.world_snapshot`). Снапшот из DM-ответа содержит одно обновление состояния, и фронтенд его применяет напрямую — **минуя persistence-слой**. Поэтому «один тик» виден, а autonomous idle-tick — нет.

**Дополнительно** — session report `reports/history/2026-07-13_06-52.md` показывает:
- **PFI (Pre-Bus Failure) = 300%** — 12 пред-шинных отказов за сессию (это и есть Phase 10 crashes).
- **Все 7 NPC имеют `Traversal: ❌`** — `active_traversals` пустые, потому что persistence не сохраняет созданные в Phase 0 traversal states.
- **`player` имеет `coords=None`** — аватар игрока не имеет позиции, потому что при commit-fail `npc_positions` не обновляется.

Подробности фикса — см. §3.1.

### 2.4. Корневая проблема архитектуры

Даже после фикса §3.1 игра останется «болванчиками ходят туда-сюда» по причинам:

1. **`proactive_intents` whitelist** в `world_tick_engine.py:113-122` содержит только `{BLOCK_PATH, AMBUSH, SEEK_ALLY, OFFER_JOB, REQUEST_SERVICE, SPREAD_RUMOR, CALL_FOR_HELP, CHANGE_ROLE}`. **DIALOGUE, ATTACK, TRADE, FLEE, STEAL — отсутствуют.** NPC не могут автономно заговорить, атаковать, торговать, убежать, украсть.
2. **`WorldScheduler` — заглушка** `disabled_pending_phase6`, не вызывает WorldTickEngine.
3. **`TransactionEngine.execute_sale`** не имеет runtime call sites — только в тестах.
4. **5 брошенных модулей** (см. §2.2) — код написан, не подключён.
5. **Нет визуализации NPC-NPC взаимодействий** — даже если бы диалоги возникали, игрок их не видел бы (speech bubbles для NPC-NPC отсутствуют).
6. **Нет пространственных механик** — зоны, линии видимости, акустика, радиусы подслушивания не реализованы.
7. **Нет временных механик** — расписание NPC есть, но события по расписанию (рассвет, обед, закрытие таверны) не генерируются.

Эти 7 пунктов — повестка Этапа 1 + Этапа 4.

---

## 3. ЭТАП 0: КРИТИЧЕСКИЕ БАГИ (1-2 ДНЯ)

### 3.1. ★БЛОКЕР★ Persistence крашит каждый idle_tick — `TypeError: Type List cannot be instantiated`

**Файл:** `backend/app/services/state/sqlite_persistence_adapter.py`
**Строка:** 84 (внутри `_upsert`)
**Функция:** `_upsert` (начинается на строке 72)

**Что происходит:**

На строке 81-85:
```python
conn.execute(
    "INSERT OR REPLACE INTO state_kv (key, value, updated_at) VALUES (?, ?, ?)",
    (
        key,
        json.dumps(
            value,
            ensure_ascii=False,
            default=lambda o: List[Any](o) if isinstance(o, set) else str(o),  # ← BUG
        ),
        datetime.now(timezone.utc).isoformat(),
    ),
)
```

`List[Any]` — это `typing.List[Any]`. В Python 3.13+ (используется в проекте — видно по пути `WindowsApps\PythonSoftwareFoundation.Python.3.13` в трейсбэке) типы из `typing` **нельзя инстанцировать**. Вызов `List[Any](o)` падает с:
```
TypeError: Type List cannot be instantiated; use list() instead
```

Это срабатывает, когда `json.dumps` натыкается на Python `set` внутри `value` (а `value` — это `npc_states`, где много `set` полей: `scene_flags`, `tags`, `traits`, `exposure_set` и т.д.).

**Почему это убивает симуляцию полностью:**

Каждый idle_tick:
1. **Phase 0-9 проходят успешно** — LifeEngine создаёт 4-6 spatial changes (видно в логах: `[TICK_ORCH] Фаза 0: 4 spatial changes from 4 LifeEngine intents`), DecisionHub генерит решения (`[DECISION_HUB] maid_lusya: intent=Intent.seek_ally` и т.д. для всех 7 NPC), `_advance_idle_time` обновляет `game_time_seconds`.
2. **Phase 10 (persistence) вызывает `commit()`** → `atomic_commit()` → `_upsert(f"runtime:{campaign_id}", npc_states)`.
3. `json.dumps` находит `set` внутри NPC state → вызывает `default=lambda o: List[Any](o) if isinstance(o, set) else str(o)` → `List[Any](o)` → **TypeError**.
4. Исключение пробрасывается до `tick_orchestrator.execute()` (строка 462), логируется как `[TICK_CRASH] campaign=Open_road tick=N`.
5. **Ничего не сохраняется** — изменения в `scene_state` (npc_positions, active_traversals, game_time_seconds) остаются только в памяти TickContext, который уничтожается.
6. На следующем idle_tick `lock_for_tick` читает **старое** состояние из SQLite → NPC возвращаются на исходные позиции, время откатывается.

Создатель видит: «NPC стоят как вкопанные, время не тикает». Симуляция работает в памяти, но persistence не даёт ей прогрессировать.

**Патч (минимальный, одна строка):**

```python
# backend/app/services/state/sqlite_persistence_adapter.py
# Строка 84 — заменить List[Any](o) на list(o):

# Было:
default=lambda o: List[Any](o) if isinstance(o, set) else str(o),

# Стало:
default=lambda o: list(o) if isinstance(o, set) else str(o),
```

**Расширенный патч (рекомендуется):**

Лямбда `default` не покрывает другие нередуцируемые типы (`tuple`, `datetime`, `Enum`, dataclass). Лучше — полноценный `default` handler:

```python
# backend/app/services/state/sqlite_persistence_adapter.py

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum

def _json_default(o):
    """JSON-сериализатор для нестандартных типов в NPC state."""
    if isinstance(o, set):
        return list(o)
    if isinstance(o, Enum):
        return o.value
    if isinstance(o, datetime):
        return o.isoformat()
    if is_dataclass(o):
        return asdict(o)
    if hasattr(o, "__dict__"):
        return o.__dict__
    return str(o)  # последний fallback — лучше, чем crash

class SqlitePersistenceAdapter:
    def _upsert(self, key, value):
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO state_kv (key, value, updated_at) VALUES (?, ?, ?)",
            (
                key,
                json.dumps(value, ensure_ascii=False, default=_json_default),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
```

**Тест после фикса:**
1. `python game_launcher.py` → New Game → **ничего не вводить 30 секунд**.
2. В `backend/logs/cds_backend.log` **нет** записей `[TICK_CRASH]`.
3. `game_time_seconds` растёт — часы в HUD обновляются.
4. NPC визуально меняют позиции (хотя бы чуть-чуть, даже если это LifeEngine schedule movement).
5. `active_traversals` в scene_state не пустой (видно через `journal (Ё)` или debug overlay).

**Контрольная точка:** до фикса — 10+ `[TICK_CRASH]` за минуту. После фикса — 0 crashes.

---

### 3.2. ★ВЫСОКИЙ★ Real-time loop дефект — idle_tick привязан к DM-ответу

Даже после фикса §3.1 игра **не будет** «real-time живой», потому что frontend-таймер idle_tick имеет архитектурные дефекты. Аудит `frontend/game_screen.py` показал:

**Проблема 1 — Интервал слишком длинный:**

```python
# frontend/constants.py:19-23
IDLE_TICK_NEAR_MS: int = 2_000   # 2 секунды — если игрок рядом с NPC
IDLE_TICK_MID_MS:  int = 8_000   # 8 секунд — средняя дистанция
IDLE_TICK_FAR_MS:  int = 30_000  # 30 секунд — далеко от NPC
```

`GAME_TICK_INTERVAL_SECONDS = 60` (1 минута игрового времени за тик). Итого: 1 игровая минута проходит за 2-30 секунд реального времени. Это значит, что для прохождения 1 игрового часа нужно 2-30 минут реального времени — **слишком медленно для «живой» игры**.

**Проблема 2 — `action_queue.pending_count() == 0` блокирует idle_tick:**

```python
# frontend/game_screen.py:1138-1140
if (
    _now - _last_idle_tick >= _tick_interval
    and not _idle_tick_running[0]
    and action_queue.pending_count() == 0   # ← блокировка
):
```

`pending_count()` = `self._input.qsize()` (api_client.py:873). Это **очередь ввода**, не очередь обработки. Если игрок отправил действие → оно сразу забирается worker thread → `pending_count()` = 0 → idle_tick **запускается параллельно с LLM-запросом**. Но если в очереди есть ещё действия (игрок быстро нажал Enter несколько раз), idle_tick ждёт.

Хуже: после ответа DM (строка 1169):
```python
_last_idle_tick = pygame.time.get_ticks() + 1000  # +1 секунда вперёд
```

Это означает: после каждого DM-ответа idle_tick **не запустится минимум 1 секунду**. Если игрок часто вводит команды — idle_tick вообще не запустится.

**Проблема 3 — idle_tick ставит DM-ответ в ту же очередь:**

DM-ответ обрабатывается в `action_queue.poll()` (строка 1156). Пока DM не ответит (~2 секунды LLM latency), `pending_count()` может быть 0, но `_idle_tick_running[0]` уже True, и новый idle_tick не запустится. Симуляция ждёт LLM.

**Патч (пошаговый):**

**Шаг 1 — Уменьшить интервал idle_tick:**

```python
# frontend/constants.py
IDLE_TICK_NEAR_MS: int = 500    # 0.5 сек — близко к NPC
IDLE_TICK_MID_MS:  int = 1_500  # 1.5 сек — средняя
IDLE_TICK_FAR_MS:  int = 3_000  # 3 сек — далеко
```

С `GAME_TICK_INTERVAL_SECONDS = 60`: 1 игровая минута = 0.5-3 сек реального времени. Один игровой час = 30 сек — 3 мин. Один игровой день = 12 мин — 1 час 12 мин. Это playable.

**Шаг 2 — Уменьшить `GAME_TICK_INTERVAL_SECONDS`:**

```python
# backend/app/core/constants.py:210-212
GAME_TICK_INTERVAL_SECONDS: int = (
    10  # было 60. 10 секунд = 1 тик. 1 игровая минута = 1 тик = 10 сек real.
)
```

Если хочется ещё быстрее — 5 секунд. Но осторожно: при 5 сек idle_tick может не успевать LLM-запрос (2 сек) — нужно decoupling.

**Шаг 3 — Decouple idle_tick от action_queue:**

```python
# frontend/game_screen.py:1138-1140
# УБРАТЬ: and action_queue.pending_count() == 0
# Заменить на:
if (
    _now - _last_idle_tick >= _tick_interval
    and not _idle_tick_running[0]
):
```

Idle_tick должен работать **параллельно** с LLM-запросом DM. Они не конфликтуют — idle_tick обновляет только NPC positions/time, не DM contract.

**Шаг 4 — Уменьшить post-DM паузу:**

```python
# frontend/game_screen.py:1169
# Было: _last_idle_tick = pygame.time.get_ticks() + 1000
# Стало: _last_idle_tick = pygame.time.get_ticks()  # без +1 сек
# Или: _last_idle_tick = pygame.time.get_ticks() + 200  # 200мс достаточно для UX
```

**Тест после фикса:**
1. Запустить игру → **ничего не вводить 30 секунд**.
2. Часы в HUD должны обновляться **каждые 0.5-3 секунды** (а не раз в 30 сек).
3. NPC визуально меняют позиции.
4. Игрок вводит команду → DM отвечает (~2 сек) → idle_tick **продолжает работать** во время LLM-запроса.

**Контрольная точка:** за 30 секунд без ввода — `game_time_seconds` вырос минимум на 5 минут игрового времени. На экране видно ≥ 2 смены позиций NPC.

---

### 3.3. ★ВЫСОКИЙ★ DecisionHub не генерирует движение в idle — `_MOVE_INTENTS` whitelist слишком узкий

Даже после фиксов §3.1 и §3.2 NPC **не будут двигаться autonomously** (только расписание LifeEngine будет их двигать при смене activity, раз в час). Причина — в `npc_tick_pipeline.py`.

**Файл:** `backend/app/services/npc/npc_tick_pipeline.py`
**Строка:** 401

```python
_MOVE_INTENTS = {"approach", "flee"}
if _intent_value in _MOVE_INTENTS:
    _movement = _resolve_reactive_movement(...)
    if _movement:
        movement_intents.append(_movement)
elif _intent_value == "attack":
    # создает CommunicationIntent (attack), но не MovementIntent
    ...
# остальные intents — вообще не создают movement
```

DecisionHub генерит intents: `block_path`, `ambush`, `seek_ally`, `offer_job`, `request_service`, `call_for_help`, `spread_rumor`, `change_role`, `talk` (видно в логах сессии). Из них:

| Intent | Создаёт движение? | Что должно происходить |
|---|---|---|
| `block_path` | ❌ | NPC должен идти к дверному проёму / проходу |
| `ambush` | ❌ | NPC должен прятаться за объектом |
| `seek_ally` | ❌ | NPC должен идти к союзнику |
| `offer_job` | ❌ | NPC должен идти к target_npc |
| `request_service` | ❌ | NPC должен идти к bar_counter / workbench |
| `call_for_help` | ❌ | NPC должен идти к ближайшему ally |
| `spread_rumor` | ❌ | NPC должен идти к группе NPC |
| `change_role` | ❌ | NPC должен идти к месту новой роли |
| `talk` | ❌ | NPC должен идти к собеседнику |
| `approach` | ✅ | Работает |
| `flee` | ✅ | Работает |

**Влияние:** Все proactive decisions DecisionHub'а — **декоративные**. NPC "решает" `request_service` (id=blacksmith_orm, score=0.736 — высокий!), но стоит на месте. Игрок видит: NPC «думают», но ничего не делают.

**Патч (расширить `_MOVE_INTENTS` + добавить target resolution):**

```python
# backend/app/services/npc/npc_tick_pipeline.py
# Строка 401 — заменить:

# Было:
_MOVE_INTENTS = {"approach", "flee"}

# Стало:
# Все intents, которые требуют физического перемещения к target
_MOVE_INTENTS = {
    "approach",         # к игроку (существующий)
    "flee",             # от угрозы (существующий)
    "seek_ally",        # к NPC с max trust
    "offer_job",        # к target NPC
    "request_service",  # к NODE_ROLE.BAR / WORKBENCH / MERCHANT
    "call_for_help",    # к ближайшему ally
    "spread_rumor",     # к ближайшему cluster NPC
    "block_path",       # к NODE_ROLE.ENTRANCE
    "ambush",           # к NODE_ROLE behind cover
    "talk",             # к target NPC (NPC-NPC диалог)
    "change_role",      # к месту новой роли
}
```

**Дополнительно — для каждого intent нужен target resolver:**

```python
# Добавить функцию рядом с _resolve_reactive_movement:
def _resolve_proactive_target(
    intent_value: str,
    npc_id: str,
    intent_target: str | None,
    scene_state: dict,
    spatial_query,
) -> str | None:
    """Возвращает target_node для proactive movement intent."""
    if not spatial_query:
        return None
    
    # Если есть явный target_id — резолвим его позицию
    if intent_target and intent_target != "player":
        target_pos = scene_state.get("npc_positions", {}).get(intent_target, {})
        lp = target_pos.get("local_position")
        if lp:
            return spatial_query.find_nearest_node(lp.get("x", 0), lp.get("y", 0))
    
    # Иначе — резолвим по intent type
    if intent_value in ("request_service", "offer_job"):
        # Идём к BAR / WORKBENCH / MERCHANT узлу
        return spatial_query.resolve_node(NodeRole.BAR)
    elif intent_value == "block_path":
        return spatial_query.resolve_node(NodeRole.ENTRANCE)
    elif intent_value in ("seek_ally", "call_for_help", "spread_rumor", "talk"):
        # Идём к ближайшему NPC в кластере
        cluster = spatial_query.find_nearest_cluster(exclude_npc=npc_id)
        if cluster:
            return spatial_query.find_nearest_node(*cluster.centroid())
    
    return None
```

И в основной цикл (после строки 401):

```python
if _intent_value in _MOVE_INTENTS:
    # Сначала пробуем reactive movement (для approach/flee с target=player)
    _movement = _resolve_reactive_movement(...)
    
    # Если не вышло и это proactive intent — резолвим target через spatial_query
    if not _movement and state.spatial_query:
        _target_node = _resolve_proactive_target(
            intent_value=_intent_value,
            npc_id=npc_id,
            intent_target=decision.intent_target,
            scene_state=dict(state.scene_state),
            spatial_query=state.spatial_query,
        )
        if _target_node:
            # Создаём MacroMovementGoal к _target_node
            _movement = MacroMovementGoal(
                npc_id=npc_id,
                target_node=_target_node,
                reason=f"proactive_{_intent_value}",
                ...
            )
    
    if _movement:
        movement_intents.append(_movement)
```

**Тест после фикса:**
1. Запустить игру → ничего не вводить 30 секунд.
2. В логах: `[MOTION_ROUTER] SEEK_ALLY→MovementIntent: npc=maid_lusya → target=merchant_goran`.
3. На экране: NPC визуально двигаются к target-ам (не стоят на месте).
4. В `active_traversals` появляются новые entries.

**Контрольная точка:** за 30 секунд без ввода — ≥ 3 NPC начали movement (статус `active_traversals[*].status = "MOVING"`).

---

### 3.4. ★БЛОКЕР для социального взаимодействия★ `communication_intents = 0` в каждом idle_tick — NPC-NPC диалоги не возникают

**Файлы:** `backend/app/services/npc/npc_tick_pipeline.py`, `backend/app/services/npc/decision_hub.py`, `backend/app/services/phases/post_decision.py`

**Что наблюдается в логах:**

За сессию 13 июля 06:52 (10+ idle_ticks) логи показывают:
- DecisionHub сгенерил решения для всех 7 NPC каждый тик — итого ~73 вербальных intent'а (30×`request_service`, 20×`offer_job`, 8×`change_role`, 7×`spread_rumor`, 6×`talk`, 2×`call_for_help`).
- Все эти intents ∈ `_VERBAL_INTENTS` DecisionHub → `_build_communication()` должен вернуть `CommunicationIntent`.
- **НО** логи `[TICK_ORCH] Фаза 6: 0 intents → EventDTO, 0 windups created` — каждый тик. `communication_intents = []`.
- Лог `[TRACE][DECISION_SCORE]` (пишется на строке 336 `_build_communication`) — **0 раз** за сессию.
- Логи от модуля `app.services.npc.decision_hub` — **0 строк** за сессию (хотя `app.services.npc.npc_tick_pipeline` — 123 строки).

**Вывод:** Либо `compute()` не доходит до строки 793 (`_communication = self._build_communication(...)`), либо `_build_communication` возвращает None по неочевидной причине. Pipeline.py:391 проверяет `if decision.communication is not None` — и communication всегда None.

**Без этого фикса:** NPC-NPC диалоги **не возникают никогда**, даже после §3.1-3.3. Симуляция будет «движущиеся болванчики» — NPC ходят к target'ам, но молчат. Никаких слухов, конфликтов, романсов, шантажа — ничего из §5 (Эмерджентный цикл) и §7.3 (социальные механики).

**Диагностический план (LLM-архитектор должен выполнить шаги по порядку):**

**Шаг 1 — Проверить, доходит ли compute() до строки 793:**

В `decision_hub.py:777` есть `logger.info("[DECISION_HUB] {state.npc_id}: intent={best_intent}...")`. Если этого лога **нет** в cds_backend.log, значит compute() вышел раньше:
- Строка 384 (early return для мёртвых) — `intent=IDLE`, но в логах intent=offer_job, значит не этот путь.
- Строка 657 (early return для `not scores`) — `intent=IDLE`, тоже не наш случай.

**Гипотеза А (наиболее вероятная):** `compute()` падает с исключением где-то между строками 657 и 777, и исключение проглатывается. Добавить отладочный лог:

```python
# decision_hub.py, перед строкой 657 (после "if not scores: ..."):
logger.info(f"[DECISION_HUB_ENTER] npc={state.npc_id} scores_count={len(scores) if scores else 0}")

# И на строке 777:
logger.info(f"[DECISION_HUB_RETURN] npc={state.npc_id} intent={best_intent} score={best_score}")
```

Запустить игру, подождать 30 сек, проверить `grep "DECISION_HUB_RETURN" backend/logs/cds_backend.log`. Если логов 0 — compute() падает. Если логи есть — проблема в `_build_communication`.

**Шаг 2 — Если compute() доходит — проверить `_build_communication`:**

В `_build_communication` (строка 313-348):
```python
def _build_communication(self, npc_id, intent_value, intent_target, topic, emotion_value, scores=None):
    if intent_value not in self._VERBAL_INTENTS:
        return None  # ← возврат без лога
    ...
    logger.info(f"[TRACE][DECISION_SCORE] npc={npc_id} winner={intent_value} ...")  # ← этого лога нет
    return CommunicationIntent(...)
```

Если `intent_value` не в `_VERBAL_INTENTS` — return None без лога. Но мы проверили: `request_service`, `offer_job`, `spread_rumor`, `call_for_help`, `change_role`, `talk` — все в списке. Значит должно дойти до лога.

**Гипотеза Б:** `intent_value` передаётся как `Intent` объект, а не строка. На строке 795-797:
```python
intent_value=best_intent
if isinstance(best_intent, str)
else best_intent.value,
```

`best_intent` всегда `Intent` (строка 740: `best_intent = Intent(best_candidate_str)`). Значит `intent_value = best_intent.value` = строка. Это корректно.

**Гипотеза В:** `_build_communication` падает с исключением после строки 326 (между `if intent_value not in self._VERBAL_INTENTS` и `logger.info` на 336). Например, `topic = topic or intent_value` падает если topic — None. Или `sorted(scores.items()...)` падает если scores — None (это возможно, если в вызове на строке 793 передаётся `scores=None`).

Проверить: добавить try/except вокруг `_build_communication` в compute():

```python
# decision_hub.py:793
try:
    _communication = self._build_communication(...)
except Exception as _comm_err:
    logger.exception(f"[BUILD_COMM_FAILED] npc={state.npc_id} intent={best_intent}: {_comm_err}")
    _communication = None
```

Запустить, проверить логи. Если `[BUILD_COMM_FAILED]` появится — исключение поймано, видна причина.

**Шаг 3 — Если исключение в `_build_communication` — исправить.**

Наиболее вероятные причины:
1. `scores` параметр — None, а в `_build_communication` на строке 332 делается `sorted(scores.items()...)` — упадёт с `AttributeError: 'NoneType' object has no attribute 'items'`.
2. `intent_target` — None, и в `CommunicationIntent(audience=intent_target or "all", ...)` всё ок, но если `intent_target` это не str, а какой-то объект — может упасть.
3. `state.emotion` — None или не enum, и `state.emotion.value` падает.

**Быстрый фикс (обёртка с fallback):**

```python
# decision_hub.py, заменить строки 793-805:
try:
    _communication = self._build_communication(
        npc_id=state.npc_id,
        intent_value=best_intent.value if hasattr(best_intent, 'value') else str(best_intent),
        intent_target=intent_target,
        topic=topic,
        emotion_value=state.emotion.value if hasattr(state.emotion, 'value') else str(state.emotion),
        scores=scores if scores is not None else {},
    )
except Exception as _comm_err:
    logger.exception(f"[BUILD_COMM_FAILED] npc={state.npc_id} intent={best_intent}: {_comm_err}")
    _communication = None

return AgentAction(decision=_decision, communication=_communication)
```

**Тест после фикса:**
1. Запустить игру → ничего не вводить 30 секунд.
2. В логах: `[TICK_ORCH] Фаза 6: N intents → EventDTO` где N > 0.
3. В логах: `[TRACE][DECISION_SCORE]` хотя бы 1 раз.
4. `pending_tasks` в scene_state не пустой.

**Контрольная точка:** за 30 секунд без ввода — `communication_intents ≥ 1` (видно в логах Phase 6).

---

### 3.5. ★ВЫСОКИЙ★ TaskScheduler + LLM throttle для автономных диалогов

Даже после §3.4 (communication_intents > 0) цепочка может оборваться на TaskScheduler. Нужно проверить и подготовить throttling, иначе LLM умрёт от нагрузки.

**Файлы:** `backend/app/services/game_loop/task_scheduler.py`, `backend/app/services/execution/dialogue_executor.py`, `backend/app/services/game_loop/__init__.py` (idle_tick).

**Что проверить:**

**Шаг 1 — TaskScheduler вызывается в idle_tick?**

`task_scheduler.py:65-77` читает `scene_state.get("pending_tasks", [])` и исполняет их через `DialogueExecutor`. Но **где** TaskScheduler вызывается?

```bash
grep -rn "task_scheduler\|TaskScheduler" backend/app/services/game_loop/__init__.py
grep -rn "task_scheduler\.execute\|task_scheduler\.run\|task_scheduler\.process" backend/app/services/
```

Если TaskScheduler **не вызывается** в `_run_core_phases` (или вызывается только в player_turn path) — диалоги из `pending_tasks` никогда не исполнятся.

**Шаг 2 — Если не вызывается — добавить вызов в Phase 8 или 9:**

```python
# tick_orchestrator.py — добавить новую фазу _phase_8_5_task_execution
def _phase_8_5_task_execution(self, ctx: _TickContext) -> None:
    """Исполняет pending_tasks (NPC-NPC диалоги) через TaskScheduler."""
    from app.services.game_loop.task_scheduler import TaskScheduler
    _scheduler = self._get_task_scheduler()
    if _scheduler:
        _scheduler.execute_pending(ctx.scene_state, ctx.campaign_id)
```

И добавить в `_run_core_phases`:
```python
self._phase_8_drain_secondary(ctx)
self._phase_8_5_task_execution(ctx)  # ← NEW
self._phase_9_integration(ctx)
```

**Шаг 3 — LLM throttling (критично):**

Если каждый idle_tick (3 сек после §3.2) порождает 2-3 CommunicationIntent → TaskScheduler вызывает `DialogueExecutor` → LLM генерит реплику (1-2 сек на CPU для qwen_7b).

За минуту: 20 тиков × 2 диалога × 1.5 сек LLM = **60 секунд LLM-вызовов в минуту** = 100% CPU. Симуляция задохнётся.

**Решение — queue + rate limit:**

```python
# backend/app/services/execution/dialogue_executor.py или новый dialogue_queue.py

class DialogueQueue:
    """Очередь NPC-NPC диалогов с rate limiting."""
    
    MAX_DIALOGUES_PER_TICK = 1  # Максимум 1 LLM-вызов за idle_tick
    MAX_DIALOGUES_PER_MINUTE = 5  # Максимум 5 диалогов в минуту
    COOLDOWN_PER_NPC_SEC = 30  # Один NPC говорит раз в 30 сек
    
    def __init__(self):
        self._queue: list[QueuedTask] = []
        self._recent: dict[str, float] = {}  # npc_id → last_speak_timestamp
        self._minute_count: int = 0
        self._minute_start: float = time.time()
    
    def enqueue(self, task: QueuedTask) -> None:
        self._queue.append(task)
    
    def dequeue_eligible(self, now: float) -> list[QueuedTask]:
        """Возвращает задачи, которые можно исполнить сейчас с учётом rate limit."""
        # 1. Сброс минутного счётчика
        if now - self._minute_start > 60:
            self._minute_count = 0
            self._minute_start = now
        
        if self._minute_count >= self.MAX_DIALOGUES_PER_MINUTE:
            return []
        
        result = []
        remaining = []
        for task in self._queue:
            if len(result) >= self.MAX_DIALOGUES_PER_TICK:
                remaining.append(task)
                continue
            
            speaker = task.owner_id
            last_speak = self._recent.get(speaker, 0)
            if now - last_speak < self.COOLDOWN_PER_NPC_SEC:
                remaining.append(task)  # NPC на cooldown'е
                continue
            
            result.append(task)
            self._recent[speaker] = now
            self._minute_count += 1
        
        self._queue = remaining
        return result
```

В TaskScheduler:
```python
def execute_pending(self, scene_state, campaign_id):
    pending = scene_state.get("pending_tasks", [])
    if not pending:
        return
    
    import time
    _now = time.time()
    _eligible = self._dialogue_queue.dequeue_eligible(_now)
    
    for task_dict in _eligible:
        task = self._reconstruct_task(task_dict)
        if task.kind == TaskKind.DIALOGUE:
            executor = self._executors[TaskKind.DIALOGUE]
            try:
                executor.execute(task)
            except Exception as e:
                logger.exception(f"[TASK_SCHED] dialogue failed: {e}")
    
    # Убираем исполненные из pending_tasks
    scene_state["pending_tasks"] = [t for t in pending if t not in _eligible]
```

**Тест после фикса:**
1. Запустить игру → ничего не вводить 2 минуты.
2. В логах: `[TASK_SCHED] dialogue executed: speaker=maid_lusya target=merchant_goran` — **минимум 2-3 записи**.
3. CPU usage не превышает 70%.
4. Никаких `[TASK_SCHED] dialogue failed` кроме ожидаемых (LLM timeout).
5. Каждый NPC говорит не чаще раза в 30 сек.

**Контрольная точка:** за 2 минуты без ввода — ≥ 5 NPC-NPC диалогов исполнено, CPU ≤ 70%, ни один NPC не говорит чаще раза в 30 сек.

---

### 3.6. ★ВЫСОКИЙ★ PerceptionEngine замыкается на NPC-NPC события

Даже после §3.4 и §3.5 — диалог возникает, но NPC_B **не воспринимает** реплику NPC_A. Цикл из §2.3 оригинального ТЗ (Нужда → DecisionHub → Dialogue → PerceptionEngine(NPC_B) → Interpretation → AffectiveIntegrator → Memory → Belief → Relationship → DecisionHub(NPC_B)) **не замыкается**.

**Файлы:** `backend/app/services/perception/`, `backend/app/services/events/event_bus.py`, `backend/app/services/execution/dialogue_executor.py`.

**Что проверить:**

**Шаг 1 — DialogueExecutor публикует `NPC_SAID_TO_NPC` event?**

```bash
grep -n "NPC_SAID_TO_NPC\|publish.*dialogue\|publish.*said" backend/app/services/execution/dialogue_executor.py
```

Если event не публикуется — PerceptionEngine не получит вход. Цикл разомкнут.

**Шаг 2 — Есть ли subscriber на `NPC_SAID_TO_NPC`?**

В оригинальном ТЗ §5.3 описан `NpcDialogueSubscriber`. Проверить существует ли он:

```bash
grep -rn "NpcDialogueSubscriber\|on_npc_said_to_npc\|NPC_SAID_TO_NPC" backend/app/
```

Если подписчика нет — создать:

```python
# backend/app/services/events/npc_dialogue_subscriber.py

class NpcDialogueSubscriber:
    """Слушает NPC_SAID_TO_NPC события и запускает perception pipeline для listener."""
    
    def __init__(self, perception_engine, interpretation_engine, 
                 affective_integrator, working_memory, 
                 relationship_store, belief_aggregator):
        self.perception = perception_engine
        self.interpretation = interpretation_engine
        self.affective = affective_integrator
        self.memory = working_memory
        self.relationships = relationship_store
        self.beliefs = belief_aggregator
    
    def on_npc_said_to_npc(self, event):
        speaker = event.speaker
        listener = event.listener
        text = event.text
        tone = event.tone
        
        # 1. PerceptionEngine воспринимает событие
        perceived = self.perception.perceive(listener, event)
        
        # 2. InterpretationEngine интерпретирует
        interpretation = self.interpretation.interpret(listener, perceived)
        
        # 3. AffectiveIntegrator обновляет эмоции listener'а
        self.affective.apply(listener, interpretation)
        
        # 4. WorkingMemory добавляет эпизод
        self.memory.append(listener, {
            "tick": event.tick,
            "type": "dialogue_heard",
            "speaker": speaker,
            "text": text,
            "tone": tone,
            "interpretation": interpretation,
        })
        
        # 5. RelationshipStore обновляет trust/fear
        delta_trust, delta_fear = self._compute_rel_delta(tone, interpretation)
        self.relationships.update(listener, speaker, delta_trust, delta_fear)
        
        # 6. BeliefAggregator формирует belief
        self.beliefs.aggregate(listener, {
            "speaker": speaker,
            "topic": event.topic,
            "tone": tone,
            "tick": event.tick,
        })
    
    def _compute_rel_delta(self, tone, interpretation):
        """Конвертирует tone реплики в изменения trust/fear."""
        if tone == "ANGRY":
            return -5.0, +2.0
        elif tone == "FRIENDLY":
            return +3.0, 0.0
        elif tone == "FLIRTY":
            return +2.0, 0.0  # зависит от existing relationship
        elif tone == "VENTING":
            return +1.0, 0.0  # эмпатия
        elif tone == "MANIPULATIVE":
            return -2.0, +1.0  # заметили манипуляцию
        elif tone == "FEARFUL":
            return 0.0, +1.0
        return 0.0, 0.0
```

И подписать его в `event_bus`:

```python
# backend/app/services/events/event_bus.py или в инициализации GameLoop

def _register_subscribers(event_bus, services):
    subscriber = NpcDialogueSubscriber(
        perception_engine=services.perception,
        interpretation_engine=services.interpretation,
        affective_integrator=services.affective,
        working_memory=services.memory,
        relationship_store=services.relationships,
        belief_aggregator=services.beliefs,
    )
    event_bus.subscribe("NPC_SAID_TO_NPC", subscriber.on_npc_said_to_npc)
```

**Шаг 3 — Убедиться что listener = NPC_B, не player.**

`DialogueExecutor` сейчас скорее всего создаёт событие с listener=player. Нужно расширить:

```python
# dialogue_executor.py — в методе execute()
event = {
    "type": "NPC_SAID_TO_NPC",
    "speaker": task.owner_id,         # NPC_A
    "listener": task.target_ids[0],   # NPC_B (не player!)
    "text": generated_text,
    "tone": task.payload.tone,
    "topic": task.payload.topic,
    "tick": current_tick,
}
event_bus.publish(event)
```

**Тест после фикса:**
1. Запустить игру → ничего не вводить 2 минуты.
2. В логах: `[NPC_DIALOGUE_SUB] maid_lusya heard merchant_goran (tone=FRIENDLY)` — ≥ 3 записи.
3. В NPC state: `maid_lusya.emotional_state.joy += 0.2` после дружелюбной реплики.
4. `maid_lusya.relationships[goran].trust += 3` — видно через debug overlay.
5. После 3+ реплик — в `CrystallizedBeliefStore` появляется belief о goran.

**Контрольная точка:** за 2 минуты без ввода — ≥ 3 записи `[NPC_DIALOGUE_SUB]`, эмоции listener'а меняются, trust/fear обновляются.

---

### 3.7. ★КРИТИЧНО★ Автономный мир-контракт — что именно должно происходить без игрока

Это не баг, это **спецификация**. Создатель прямо требует: «Мир меняется самостоятельно так как и задумано было изначально». До прохождения этого контракта — Этап 0 не пройден.

**Автономный мир-контракт (AWC):**

Игрок запускает игру, **ничего не вводит 5 минут**, только наблюдает. За эти 5 минут **обязательно** должны произойти:

**A. Время идёт:**
- [ ] `game_time_seconds` растёт каждые ~3 сек на 60 сек игрового времени.
- [ ] За 5 минут реальных — 1 час 40 мин игровых (или больше, если time_scale > 1).
- [ ] Часы в HUD обновляются (видно "07:00" → "07:30" → "08:00" → ... → "08:40").

**B. NPC двигаются:**
- [ ] За 5 минут **каждый** из 7 NPC хотя бы 1 раз сменил позицию (visible в scene_renderer).
- [ ] ≥ 3 NPC одновременно имеют `active_traversals[*].status = "MOVING"`.
- [ ] NPC не «телепортируются» — видна LERP-интерполяция между узлами.

**C. NPC-NPC диалоги:**
- [ ] За 5 минут ≥ 5 NPC-NPC диалогов (видно по speech bubbles с цветным краем).
- [ ] Диалоги разные по тону (≥ 2 разных тонов: NEUTRAL, FRIENDLY, ANGRY, и т.д.).
- [ ] LLM CPU не превышает 70% (throttling работает).

**D. Эмоции меняются:**
- [ ] ≥ 3 NPC показали смену mood-иконки за 5 минут (например, neutral → happy → neutral).
- [ ] После ANGRY реплики — listener получает sadness/anger bump.

**E. Отношения меняются:**
- [ ] ≥ 2 пары NPC показали изменение trust (видно через debug overlay или journal).
- [ ] Если был конфликт (tone=ANGRY) — trust между сторонами упал.

**F. Журнал наблюдений (Ё):**
- [ ] В журнале ≥ 10 записей за 5 минут (movement, dialogue, mood_change, transaction, и т.д.).
- [ ] Записи разные по типу — не только "NPC перешёл в зону X".

**G. Persistence:**
- [ ] После рестарта игры (kill + restart) — `game_time_seconds` не сбросился, а продолжил расти.
- [ ] NPC positions восстановились из SQLite (видны на тех же местах, где были перед рестартом).
- [ ] `active_traversals` восстановились.

**H. Реакция на длительное бездействие:**
- [ ] Через 30 игровых минут (≈ 1 мин реального) — `tavern_keeper_tornin` начинает routine transition (уборка/обслуживание).
- [ ] Через 1 игровой час — смена activity у ≥ 3 NPC (по расписанию).

**Контрольная точка AWC:** Если **любой** из пунктов A-H не выполняется — мир **не автономен**. Этап 0 не пройден, нельзя переходить к Этапу 1.

**Скрипт автоматической проверки AWC:**

```python
# backend/scripts/verify_autonomous_world.py

import requests
import time
import json

BACKEND = "http://localhost:8000"
CAMPAIGN = "Open_road"

def test_autonomous_world():
    """Запускать при работающем game_launcher.py. Создаёт сессию, ждёт 5 минут, проверяет AWC."""
    
    # 1. Создать сессию
    r = requests.post(f"{BACKEND}/api/game/{CAMPAIGN}/start", json={})
    assert r.status_code == 200
    
    # 2. Получить начальное состояние
    initial = requests.get(f"{BACKEND}/api/game/{CAMPAIGN}/state").json()
    initial_time = initial.get("game_time_seconds", 0)
    initial_positions = {n["npc_id"]: n["position"] for n in initial.get("npcs", [])}
    
    # 3. Ждать 5 минут, ничего не отправляя
    print("Waiting 5 minutes (autonomous observation)...")
    time.sleep(300)
    
    # 4. Проверить AWC
    final = requests.get(f"{BACKEND}/api/game/{CAMPAIGN}/state").json()
    final_time = final.get("game_time_seconds", 0)
    
    # A. Время идёт
    time_delta = final_time - initial_time
    assert time_delta > 3000, f"AWC-A FAILED: time only advanced {time_delta}s (expected >3000)"
    
    # B. NPC двигаются
    moved = 0
    for npc_id, initial_pos in initial_positions.items():
        final_pos = next((n["position"] for n in final["npcs"] if n["npc_id"] == npc_id), None)
        if final_pos and (final_pos["x"] != initial_pos["x"] or final_pos["y"] != initial_pos["y"]):
            moved += 1
    assert moved >= 5, f"AWC-B FAILED: only {moved}/7 NPCs moved"
    
    # C. Диалоги (читаем из логов)
    import subprocess
    logs = subprocess.check_output(
        ["grep", "-c", "TASK_SCHED.*dialogue executed", "backend/logs/cds_backend.log"],
        text=True
    ).strip()
    dialogue_count = int(logs) if logs else 0
    assert dialogue_count >= 5, f"AWC-C FAILED: only {dialogue_count} dialogues in 5 min"
    
    # D, E, F, G, H — аналогично через log parsing + state inspection
    
    print("✅ AWC PASSED — мир автономен")

if __name__ == "__main__":
    test_autonomous_world()
```

Запускать после каждого изменения Этапа 0. Если AWC не проходит — отладить конкретный пункт.

---

### 3.8. C4 NameError в `affect.py:284` — `replace` не в module scope

**Файл:** `backend/app/services/affect.py`
**Строки:** 284 (использование), 306 (импорт)

**Что происходит:**

`decay_affective_imprints` (строка 284) вызывает `replace(imp, ...)`. Импорт `from dataclasses import replace` находится **внутри** функции `apply_conditioning` на строке 306 — недоступен из `decay_affective_imprints`.

В runtime это `NameError`, который **молча проглатывается** в `phases/idle_services.py:88-90`. Эффект: affective decay в idle tick не работает → эмоции NPC никогда не затухают → за час сессии все NPC в «перенапряжении».

**Патч:**

```python
# backend/app/services/affect.py
# Самый верх файла, после существующих import:
from dataclasses import replace

# Удалить локальный импорт на строке 306 (внутри apply_conditioning):
#   - from dataclasses import replace  # УДАЛИТЬ — теперь module-level
```

**Тест:** `pytest backend/tests/sandbox/affective/ -k decay` — должен проходить без `NameError`.

### 3.9. Port mismatch — 8080 / 8181 / 8000 в шести местах

**Проблема:** llama-server использует три разных порта в четырёх файлах. Нет единого источника истины.

| Файл | Строка | Порт | Назначение |
|---|---|---|---|
| `backend/app/main.py` | 80 | `8080` | hardcoded `--port` для запуска llama-server |
| `backend/app/main.py` | 110 | `8181` | health-check `http://localhost:8181` |
| `backend/app/core/config.py` | 199 | `8080` | legacy default `llama_cpp_server_url` |
| `backend/app/core/settings_*.py` | (5 файлов) | `8181` | `llama_cpp_port` setting |
| `backend/app/api/routes.py` | 132 | `8181` | `/system/status` отдаёт `{"llm": 8181}` |
| `game_launcher.py` | 271 | `8000, 8181` | exit cleanup kill — **не убивает 8080** |

**Симптом:** llama-server стартует на 8080, health-check смотрит на 8181 → всегда возвращает «llm dead». `_restart_llama_server` убивает не тот процесс. После ручного kill 8080 — cleanup не уберёт зомби-процесс.

**Патч:**

```python
# 1. backend/app/core/config.py — единый источник истины
class Settings:
    llama_cpp_port: int = 8181  # ЕДИНЫЙ порт
    llama_cpp_server_url: str = "http://localhost:8181"  # вычисляется из port
    backend_port: int = 8000

# 2. backend/app/main.py:80 — использовать settings
# Было:
"-port", "8080",
# Стало:
"-port", str(settings.llama_cpp_port),

# 3. backend/app/main.py:110 — health-check на тот же порт
# Было:
"http://localhost:8181"
# Стало:
f"http://localhost:{settings.llama_cpp_port}"

# 4. backend/app/api/routes.py:132 — /system/status
# Было:
{"llm": 8181, "backend": 8000}
# Стало:
{"llm": settings.llama_cpp_port, "backend": settings.backend_port}

# 5. game_launcher.py:271 — cleanup убивает все три
# Было:
for port in [8000, 8181]:
# Стало:
for port in [settings.backend_port, settings.llama_cpp_port, 8080]:  # 8080 — legacy, для старых процессов
```

**Тест:**
1. Запустить `python game_launcher.py` → `/system/status` отдаёт согласованные порты.
2. `kill <pid_llama>` → `_restart_llama_server` поднимает на том же порту.
3. Exit cleanup убивает все процессы.

### 3.10. Утечка файлового дескриптора в `game_launcher.py:67`

**Файл:** `game_launcher.py`
**Строка:** 67

```python
_subprocess_log = open(LOG_DIR / "subprocess.log", "a", encoding="utf-8")  # никогда не закрывается
```

**Патч:**

```python
# Вариант 1 — with-block (если Popen не держит fd долго):
with open(LOG_DIR / "subprocess.log", "a", encoding="utf-8") as _subprocess_log:
    subprocess.Popen(..., stdout=_subprocess_log, stderr=_subprocess_log)
    # ... остальной main()

# Вариант 2 — явно закрыть в finally:
_subprocess_log = open(LOG_DIR / "subprocess.log", "a", encoding="utf-8")
try:
    subprocess.Popen(..., stdout=_subprocess_log, stderr=_subprocess_log)
    # ... остальной main()
finally:
    _subprocess_log.close()
```

**Примечание:** `backend/app/main.py:93, 308` уже корректно закрыты через `try/finally` — оригинальное ТЗ ошибочно считало их утечками.

### 3.11. Silent exception suppression — актуальный список

Оригинальное ТЗ перечисляло 6 мест. Аудит показал что 5 уже исправлены (используют `logger.warning` или возвращают fallback). Осталось **одно**:

| Файл | Строка | Состояние |
|---|---|---|
| `backend/app/services/npc/l1_chronicle.py` | 71-72 | **ОСТАЛОСЬ** `except Exception: pass` |
| `backend/app/main.py` | 383-384 | исправлено — `logger.warning` (pass на 389-390 в другом блоке) |
| `frontend/game_loop_bridge.py` | 299-300 | исправлено — `return []` |
| `frontend/game_loop_bridge.py` | 332-333 | исправлено — `return None` |
| `frontend/character_select.py` | 395 | исправлено — `chars = []` |
| `frontend/campaign_select.py` | 79 | исправлено — appends fallback |

**Патч для `l1_chronicle.py:71-72`:**

```python
# Было:
except Exception:
    pass

# Стало:
except Exception:
    logger.exception("[L1_CHRONICLE] silent failure — see traceback")
```

### 3.12. 5 брошенных модулей — матрица решений

| Модуль | Решение | Обоснование | Трудозатраты |
|---|---|---|---|
| `character/front_applicator.py` + `front_engine.py` | **Удалить** | Zero external callers, дублирует character_filter | 30 мин |
| `game_loop/npc_state_helpers.py` | **Подключить** | Функции `apply_npc_state_updates` и `write_npc_memory` нужны в Phase 8 (persistence) | 2 часа |
| `npc/role_transition.py` | **Подключить** | Смена профессии NPC — недостающая механика долгосрочной симуляции | 4 часа |
| `npc/reaction_priority.py` | **Подключить** | Упорядочивание реакций в `reaction_subscriber` — улучшает качество NPC реакций | 3 часа |
| `perception/perceptual_attention_service.py` | **Подключить** | Attention budget — NPC не может воспринять всё одновременно, критично для реализма | 4 часа |

### 3.13. Контрольная точка Этапа 0 (актуализировано)

После завершения:
- [ ] **§3.1 fixed:** В `backend/logs/cds_backend.log` **нет** записей `[TICK_CRASH]` после 30-секундного idle (контроль: `grep -c "TICK_CRASH" backend/logs/cds_backend.log`)
- [ ] **§3.1 fixed:** За 30 секунд без ввода игрока `game_time_seconds` вырос минимум на 5 минут игрового времени (часы в HUD обновились)
- [ ] **§3.1 fixed:** `active_traversals` не пустой после 30 сек idle
- [ ] **§3.2 fixed:** Интервал idle_tick ≤ 3 секунды (видно по логам: `game_screen INFO: [IDLE_TICK] fired at ...` каждые 0.5-3 сек)
- [ ] **§3.2 fixed:** Во время LLM-запроса DM idle_tick не блокирован (в логах видны `[IDLE_TICK]` между `dm.status=load_start` и `dm.status=complete`)
- [ ] **§3.3 fixed:** В логах видны `[MOTION_ROUTER] SEEK_ALLY→MovementIntent` или аналогичные для других proactive intents
- [ ] **§3.3 fixed:** За 30 секунд без ввода ≥ 3 NPC начали `active_traversals[*].status = "MOVING"`
- [ ] **§3.4 fixed:** В логах `[TICK_ORCH] Фаза 6: N intents → EventDTO` где N > 0
- [ ] **§3.4 fixed:** В логах виден `[TRACE][DECISION_SCORE]` хотя бы 1 раз за 30 сек
- [ ] **§3.5 fixed:** `pending_tasks` в scene_state не пустой
- [ ] **§3.5 fixed:** В логах `[TASK_SCHED] dialogue executed: speaker=... target=...` ≥ 2 записи за 30 сек
- [ ] **§3.5 fixed:** CPU usage ≤ 70% при автономной работе 5 минут
- [ ] **§3.6 fixed:** В логах `[NPC_DIALOGUE_SUB] ... heard ... (tone=...)` ≥ 3 записи за 2 минуты
- [ ] **§3.6 fixed:** После ANGRY реплики — listener получает sadness/anger bump (видно в NPC state)
- [ ] **§3.6 fixed:** `maid_lusya.relationships[goran].trust` изменился за 2 минуты (видно через debug overlay)
- [ ] **§3.7 AWC PASSED:** Все 8 пунктов (A-H) Автономного Мир-Контракта выполняются
- [ ] `python game_launcher.py` запускается без крача
- [ ] POST `/api/game/{id}/input` возвращает 200, а не 500
- [ ] `pytest backend/tests/` — failing < 50
- [ ] Llama-server на правильном порту (одном во всех 6 местах)
- [ ] `game_launcher.py` не оставляет открытых fd
- [ ] C4 NameError в `affect.py` пофиксен
- [ ] `l1_chronicle.py:71-72` — `except Exception: pass` заменён на `logger.exception`
- [ ] 5 брошенных модулей: 4 подключены, 1 удалён (front_applicator)

**КРИТИЧНО — порядок фикса (зависимости):**

```
§3.1 (persistence) ──► §3.2 (real-time loop) ──► §3.3 (proactive movement)
                                    │
                                    └──► §3.4 (communication_intents>0) ──► §3.5 (TaskScheduler+LLM throttle) ──► §3.6 (PerceptionEngine замыкается)
                                                                                                                          │
                                                                                                                          ▼
                                                                                                          §3.7 AWC (финальная проверка)
```

**Без §3.1** — игра мертва (симуляция не сохраняется).
**Без §3.2** — игра тикает слишком медленно (1 тик в 30 сек).
**Без §3.3** — NPC «решают» но не двигаются.
**Без §3.4** — NPC двигаются но молчат (нет communication_intents).
**Без §3.5** — communication_intents есть, но DialogueExecutor не запускается (или LLM умирает от нагрузки).
**Без §3.6** — диалоги возникают, но NPC_B не реагирует на NPC_A (цикл не замыкается).
**Без §3.7 AWC** — нельзя переходить к Этапу 1 (мир не автономен).

**Минимальный сценарий «мир автономен»:**
1. Применить §3.1 (1 строка) → проверить, что idle_tick не падает
2. Применить §3.2 (3 константы + 1 строка) → проверить, что часы тикают
3. Применить §3.3 (расширить whitelist + target resolver) → проверить, что NPC двигаются
4. Применить §3.4 (диагностика + быстрый фикс) → проверить, что communication_intents > 0
5. Применить §3.5 (TaskScheduler в idle + DialogueQueue) → проверить, что диалоги исполняются
6. Применить §3.6 (NpcDialogueSubscriber) → проверить, что эмоции/отношения меняются
7. Запустить `verify_autonomous_world.py` — AWC должен пройти

После этого можно переходить к Этапу 1 (брошенные модули) и Этапу 4 (недостающие механики).

---

## 4. ЭТАП 1: СОЕДИНЕНИЕ СУЩЕСТВУЮЩИХ ПОДСИСТЕМ (5-7 ДНЕЙ)

*Актуализировано — удалены пункты которые уже сделаны (combat_math, ChangeType.INVENTORY, TaskScheduler threshold).*

Цель: **мир начинает тикать без игрока**. Все ещё-не-подключённые подсистемы из §2.2 вызываются в `idle_tick` и `player_turn`.

### 4.1. Заменить заглушку `WorldScheduler` на реальный вызов

**Файлы:** `backend/app/services/world_scheduler.py`, `backend/app/services/world/world_tick_engine.py`.

**Что сделать:**
1. В `world_scheduler.py:38` заменить `return {"world_events": [], "simulation_log": "disabled_pending_phase6"}` на реальный вызов `WorldTickEngine.compute_proactive_decisions` + публикацию событий в EventBus.
2. WorldScheduler должен стать тонкой обёрткой: orchestrate WorldTickEngine + republish events, не дублировать логику.
3. Расширить `proactive_intents` whitelist (см. §4.2).

### 4.2. Расширить `proactive_intents` whitelist

**Файл:** `backend/app/services/world/world_tick_engine.py:113-122`

**Текущее состояние:**
```python
proactive_intents: set = {
    Intent.BLOCK_PATH, Intent.AMBUSH, Intent.SEEK_ALLY,
    Intent.OFFER_JOB, Intent.REQUEST_SERVICE, Intent.SPREAD_RUMOR,
    Intent.CALL_FOR_HELP, Intent.CHANGE_ROLE,
}
```

**Что добавить (с гвардами безопасности):**

```python
proactive_intents: set = {
    # Существующие (мирные)
    Intent.BLOCK_PATH, Intent.AMBUSH, Intent.SEEK_ALLY,
    Intent.OFFER_JOB, Intent.REQUEST_SERVICE, Intent.SPREAD_RUMOR,
    Intent.CALL_FOR_HELP, Intent.CHANGE_ROLE,
    # ★ Новые ★
    Intent.DIALOGUE,    # NPC-NPC диалоги — главный канал эмерджентности
    Intent.APPROACH,    # Подойти к тому, к кому trust > 60 (SEEK_AFFINITY)
    Intent.AVOID,       # Избегать того, к кому fear > 0.5
    Intent.TRADE,       # Торговля — ведёт к TransactionEngine.execute_sale
    Intent.FLEE,        # Бегство от угрозы (fear > 0.7)
    # Опасные — с гвардами
    Intent.ATTACK,      # Только если anger > 0.7 И есть враг в зоне видимости
    Intent.STEAL,       # Только если NPC имеет черту "thief" И econ_need > 0.8
}
```

**Гварды для ATTACK и STEAL** (в `compute_proactive_decisions`, после строки 190):

```python
if result.intent == Intent.ATTACK:
    # Guard: только если anger > 0.7 И есть враг в радиусе 5м
    if state_l2.affective_state.anger < 0.7:
        continue
    if not _has_enemy_in_range(state_l2, scene_state, range_m=5.0):
        continue

if result.intent == Intent.STEAL:
    # Guard: только NPC с чертой "thief" И голоден
    if "thief" not in profile_l0.traits:
        continue
    if state_l2.economic_profile.hunger < 0.8:
        continue
```

### 4.3. Подключить экономику

**Файлы:** `backend/app/services/economy/transaction_engine.py`, `trade_resolver.py`, `market_state.py`, `economy_tracker.py`, `world_tick_engine.py`.

**Что сделать:**
1. В `WorldTickEngine.compute_proactive_decisions`: если NPC сгенерил intent=TRADE → вызвать `TradeResolver.resolve(npc, location, market_state)` → `TransactionEngine.execute_sale` → `EconomyTracker.record_income`.
2. Раз в `TICKS_PER_DAY` вызывать `MarketState.update_prices` на основе дневных транзакций.
3. `EconomicProfile` (gold, debt, needs) обновляется через `TransactionEngine`.

**Тест:** за игровой день в `economy_tracker.py` видим ≥ 3 транзакции между NPC.

### 4.4. Подключить брошенные модули (из §3.6)

1. **npc_state_helpers** — вызвать `apply_npc_state_updates` и `write_npc_memory` в Phase 8 (`_phase_8_drain_secondary`).
2. **reaction_priority** — использовать в `reaction_subscriber.py` для упорядочивания.
3. **perceptual_attention_service** — использовать в `perception_projector.py` для attention budget.
4. **role_transition** — вызывать раз в `TICKS_PER_WEEK` для всех major NPC.

### 4.5. Контрольная точка Этапа 1

- [ ] За 5 минут без ввода игрока в таверне происходит хотя бы одно видимое событие (запись в journal или movement на экране)
- [ ] В `proactive_intents` есть ATTACK, STEAL, FLEE, TRADE, **DIALOGUE**, APPROACH, AVOID
- [ ] `TransactionEngine.execute_sale` вызывается хотя бы раз за игровой день (видно в `economy_tracker`)
- [ ] `npc_state_helpers.apply_npc_state_updates` вызывается в каждом тике (видно в логах)
- [ ] `reaction_priority` используется в `reaction_subscriber` (видно в trace)
- [ ] `perceptual_attention_service` ограничивает восприятие NPC (видно по `perception_events` count)

**Если за 5 минут без ввода ничего не происходит — Этап 1 не пройден.**

---

## 5. ЭТАП 2: ЭМЕРДЖЕНТНЫЙ ЦИКЛ «НУЖДА → МНЕНИЕ» (10-14 ДНЕЙ)

*Перенесено из оригинала. Шаги 2.1-2.5 актуальны. Контрольная точка 2.6 — без изменений.*

### 5.1. Шаг 2.1 — Мысли формируются из нужды

Цель: каждый NPC имеет актуальный набор нужд, толкающих к intents. Добавить drives: SEEK_COMFORT, SEEK_VENGEANCE, SEEK_AFFINITY, AVOID_THREAT. В `DialogueRequest` добавить поле `tone: enum(NEUTRAL, FRIENDLY, ANGRY, FLIRTY, VENTING, FEARFUL, MANIPULATIVE)`.

### 5.2. Шаг 2.2 — Диалоги NPC-NPC

Реализовать полный цикл: NPC_A → QueuedTask(DIALOGUE) → DialogueExecutor → LLM → реплика A → `NPC_SAID_TO_NPC` event → PerceptionEngine(NPC_B) → ответ B.

### 5.3. Шаг 2.3 — Восприятие замыкается

Подписчик `NpcDialogueSubscriber` на `NPC_SAID_TO_NPC`: PerceptionEngine → InterpretationEngine → AffectiveIntegrator → WorkingMemory → RelationshipStore → BeliefAggregator.

### 5.4. Шаг 2.4 — Мнения кристаллизуются

`BeliefAggregator` + `PatternDetector` (Repetition, Sequence, Contradiction) + `CrystallizedBeliefStore`. DecisionHub использует кристаллизованные beliefs.

### 5.5. Шаг 2.5 — Изменения видны игроку

Speech bubbles с цветным краем по tone, mood-иконки над NPC, мягкая камера, журнал наблюдений (Ё).

### 5.6. Контрольная точка — тестовая сцена «Торнин → Люся → Горан»

Возникает без ввода игрока. В `cds_backend.log` цепочка `DRF_EMIT → PERCEIVE → DRF_EMIT → BELIEF_CRYSTALLIZED → DRF_EMIT`.

---

## 6. ЭТАП 3: МИНИ-ИГРА «СЕКРЕТЫ ЛЮСИ» (5-7 ДНЕЙ)

*Перенесено из оригинала. Все 11 разделов документа-источника остаются в силе.*

**Важное уточнение:** Этап 3 невозможен, пока не пройден §3.1 (persistence TypeError). Mini-game опирается на стабильную симуляцию, а каждый idle_tick сейчас падает на Phase 10. Сначала починить persistence, потом строить мини-игру.

Компоненты для создания (`backend/app/services/minigame/`):
- `TruthStateLoader` — 16 секретов из `config/npc/individuals/*.json`
- `ObservationLog` + EventBus subscriber
- `PlayerBeliefModel`
- `EvaluationEngine`
- `ExitTrigger`
- `EndScreenRenderer` (frontend/minigame_end_screen.py)

---

## 7. ★НОВЫЙ ЭТАП 4★ НЕДОСТАЮЩИЕ ГЕЙМПЛЕЙНЫЕ МЕХАНИКИ (10-14 ДНЕЙ)

### 7.0. Контекст: почему этот раздел нужен

Создатель прямо спросил: «каких механик не хватает игре чтобы она ощущалась по настоящему интересной а не просто болванчики ходят туда сюда и ничего не происходит пока игрок не введёт что-то в окно».

Ответ аудита: **текущая архитектура моделирует внутренний мир NPC (нужды, эмоции, beliefs) но не моделирует внешний мир, в котором они живут.** NPC получают intents от DecisionHub, но эти intents абстрактны («seek_ally», «spread_rumor») — они не привязаны к конкретным объектам, местам, времени. Результат: NPC «думают», но это мышление не превращается в видимое действие.

Ниже — 30+ конкретных механик, разбитых по приоритетам создателя: пространственные, временные, социальные (приоритет 1), плюс экономические, боевые, эпистемические (приоритет 2). Для каждой механики: **проблема**, **дизайн**, **метрика успеха**.

### 7.1. ПРОСТРАНСТВЕННЫЕ МЕХАНИКИ (приоритет 1)

#### 7.1.1. Зоны и их функциональность

**Проблема:** Сейчас локация — это плоский граф узлов. Нет разницы между «стойка трактирщика», «угол у камина», «дверь в подвал». NPC ходят по узлам, но зоны не имеют смысла.

**Дизайн:**
- Каждая локация имеет 5-10 **зон** (прямоугольники или полигоны): `bar_counter`, ` dining_area`, `dark_corner`, `fireplace`, `basement_door`, `entrance`, `kitchen`, `stage`.
- Каждая зона имеет `affordances: List[str]` — что в ней можно делать: `["drink", "sit", "talk_loudly", "hide", "sleep"]`.
- Каждая зона имеет `social_norms: Dict[intent, float]` — модификатор utility для интентов: `DIALOGUE` в `dark_corner` +0.2 (приватность), `DIALOGUE` в `bar_counter` -0.1 (шумно).
- NPC выбирает зону на основе своего intent: хочет поговорить приватно → идёт в `dark_corner`.

**Метрика:** За 10 минут idle в журнале игрока ≥ 3 записи вида «Люся перешла в зону камина», «Торнин стоит у стойки».

#### 7.1.2. Линии видимости и туман войны

**Проблема:** NPC «видят» всё в локации. Игрок тоже. Нет тёмных углов, нет возможности подслушать из-за угла.

**Дизайн:**
- Для каждой пары (NPC_A, NPC_B) вычисляется `line_of_sight: bool` через raycasting по стенам.
- `PerceptionEngine` получает только события из видимых зон + `acoustic_radius` (3м для разговора, 10м для крика).
- Игрок видит NPC только в своей линии видимости. NPC в `dark_corner` за стеной — невидим.
- `PeripheralCue` срабатывает только если NPC в зоне периферического зрения игрока.

**Метрика:** Игрок может стоять за углом и **не видеть** что происходит в соседней зоне. В `ObservationLog` появляются записи только о видимых событиях.

#### 7.1.3. Акустические радиусы

**Проблема:** Сейчас или NPC «слышит» всё, или ничего. Нет разницы между шёпотом и криком.

**Дизайн:**
- Каждое событие имеет `acoustic_level: enum(WHISPER=1m, NORMAL=3m, LOUD=10m, SHOUT=30m)`.
- `tone=ANGRY` → acoustic_level=LOUD. `tone=FLIRTY` → WHISPER. `tone=MANIPULATIVE` → WHISPER.
- NPC в радиусе acoustic_level слышит полное содержание. NPC в радиусе 2× acoustic_level слышит обрывки («голоса, но не разобрать»).
- Игрок в радиусе слышит → `ObservationLog: eavesdrop`. Игрок в радиусе 2× → `ObservationLog: muffled_voices` (confidence=0.1).

**Метрика:** Игрок может стоять в 4м от-dialogue пары и **не слышать** их (если они шепчут). Может подойти на 2м и услышать.

#### 7.1.4. Объекты-предметы с состоянием

**Проблема:** Объекты в сцене — декорации. Стол нельзя перевернуть, кружку нельзя разбить, дверь нельзя запереть.

**Дизайн:**
- Каждый объект имеет `state: dict` (open/closed, broken/intact, locked/unlocked, full/empty).
- NPC может `INTERACT(object, action)` — например, `INTERACT(basement_door, open)`.
- Состояние объектов сохраняется в `scene_state.objects` между тиками.
- Некоторые объекты — триггеры секретов: `basement_door` открыт → `ObservationLog: environmental, secret_hint="lusya_basement"`.

**Метрика:** Игрок видит «Люся открыла дверь подвала и вола» в журнале. Состояние `basement_door.state=open` сохраняется.

#### 7.1.5. Пути и блокировки

**Проблема:** NPC идут по графу, но не могут «заблокировать путь» друг другу. Нет очередей, нет давки.

**Дизайн:**
- Узел графа может быть `occupied` (NPC стоит) → другие NPC ищут обход.
- `Intent.BLOCK_PATH` (уже в whitelist!) → NPC стоит в дверном проёме, другие не могут пройти.
- Игрок может попросить «извини, можно пройти?» → `DIALOGUE(tone=FRIENDLY, target=blocking_npc)` → NPC отступает.

**Метрика:** В сессии хотя бы раз NPC блокирует путь игрока. Игрок должен использовать DIALOGUE чтобы пройти.

#### 7.1.6. Группы и кластеры

**Проблема:** NPC располагаются случайно. Нет понятия «они сидят за одним столом».

**Дизайн:**
- SpatialQueryService вычисляет `clusters: List[List[npc_id]]` — группы NPC в радиусе 2м друг от друга.
- NPC в одном кластере имеют повышенный `dialogue_opportunity` (см. §5.2).
- Игрок подходит к кластеру → может адресоваться всем сразу (`audience="all"`).
- Кластер визуально подсвечивается тонкой линией между NPC.

**Метрика:** За 10 минут видно ≥ 2 устойчивых кластера (NPC стоят рядом > 30 сек).

#### 7.1.7. Приватные vs публичные пространства

**Проблема:** NPC говорят «публично» — все слышат. Нет возможности отвести в сторону.

**Дизайн:**
- Зоны помечены `privacy: enum(PUBLIC, SEMI_PRIVATE, PRIVATE)`.
- `dark_corner` = PRIVATE, `bar_counter` = PUBLIC.
- NPC с intent=DIALOGUE(tone=MANIPULATIVE) предпочитает PRIVATE зону → подходит к цели и ведёт в `dark_corner`.
- Игрок следующий за ними теряет линию видимости (см. §7.1.2).

**Метрика:** Игрок видит «Тень и Люся перешли в тёмный угол» в журнале, после чего не видит их реплик (только если подойдёт ближе).

#### 7.1.8. Эвакуационные маршруты и паника

**Проблема:** При боёвке NPC стоят. Нет бегства, нет давки.

**Дизайн:**
- При `combat_event` все NPC в радиусе 10м с `fear > 0.5` генерируют `Intent.FLEE`.
- SpatialQueryService вычисляет ближайший `exit` узел для каждого NPC.
- MovementEngine строит путь к exit, NPC бегут (увеличенная скорость).
- Некоторые NPC с `traits: ["brave"]` или `anger > 0.7` вместо FLEE генерируют ATTACK.

**Метрика:** При драке в таверне ≥ 3 NPC убегают к выходу за 30 секунд.

#### 7.1.9. Скрытые ходы и проходы

**Проблема:** Граф公開. Нет секретных путей.

**Дизайн:**
- Некоторые рёбра графа помечены `hidden: true` + `requires_skill: "thieves_guild_map"`.
- NPC с `traits: ["thieves_guild"]` видят эти рёбра и могут использовать.
- Игрок не видит скрытые ходы, пока не `INTERACT(bookshelf, search)` с нужным skill check.
- `lusya_basement` secret → hidden edge `bar_counter ↔ basement`.

**Метрика:** Люся может исчезнуть через hidden door, а игрок не понимает куда она ушла.

#### 7.1.10. Высота и вертикальность

**Проблема:** Все на одной плоскости. Нет балконов, чердаков, лестниц.

**Дизайн:** (опционально для таверны, но важно для расширения)
- Узлы графа имеют `z: float` (0 — пол, 1 — балкон, -1 — подвал).
- Линия видимости учитывает z: NPC на балконе видит всю комнату, NPC внизу не видит NPC за перилами.
- Дальность атаки учитывает z (бонус от высоты).

**Метрика:** На балконе можно подслушивать без риска быть замеченным.

### 7.2. ВРЕМЕННЫЕ МЕХАНИКИ (приоритет 1)

#### 7.2.1. Расписание событий локации

**Проблема:** Время суток обновляется, но ничего не происходит по расписанию. Таверна «открыта» всегда.

**Дизайн:**
- Локация имеет `schedule: List[ScheduledEvent]`:
  - 06:00 — открывается кухня, пахнет хлебом
  - 12:00 — обеденный пик, приходят 3-5 случайных посетителей
  - 18:00 — музыкальный вечер (NPC `bard` играет на сцене, все слушают)
  - 22:00 — закрывается кухня, Торнин убирает столы
  - 02:00 — закрытие, все visitors уходят, остаются только residents
- ScheduledEvent → `EventBus.publish(WorldEvent)` → NPC реагируют через PerceptionEngine.

**Метрика:** За игровой день игрок видит ≥ 4 различных scheduled events в журнале.

#### 7.2.2. Циклы NPC (сон, еда, работа)

**Проблема:** У NPC есть `routine` в конфиге, но он не работает как цикл — NPC не «устают», не «голодны» в привязке ко времени.

**Дизайн:**
- Каждый NPC имеет `daily_cycle: List[(hour, activity)]`:
  - 23:00-06:00 — sleep (в своей комнате)
  - 07:00-08:00 — breakfast
  - 08:00-12:00 — work
  - 12:00-13:00 — lunch
  - 13:00-18:00 — work
  - 18:00-22:00 — free time (таверна)
  - 22:00-23:00 — bedtime routine
- NeedEngine обновляет `fatigue`, `hunger` по часам, не по тикам.
- В 23:00 NPC с fatigue > 0.7 идёт спать — покидает локацию (transition в `bedroom`).

**Метрика:** В 02:00 в таверне остаются только NPC с `traits: ["insomniac", "thief"]` или с высоким stress.

#### 7.2.3. Сезоны и погода

**Проблема:** Вечно одинаковая погода. Нет дождя, зимы, жары.

**Дизайн:**
- `WorldState` имеет `season: enum(SPRING, SUMMER, AUTUMN, WINTER)` и `weather: enum(CLEAR, RAIN, STORM, SNOW)`.
- Сезон меняется каждые 30 игровых дней.
- Погода — случайная с вероятностями по сезону.
- Влияние: дождь → visitors_count -50%, STORM → никто не приходит, SNOW → +20% на горячие напитки (TRADE hot_drink).
- Игрок видит погоду через окно (визуальный эффект).

**Метрика:** В дождливый день в таверне 2-3 посетителя вместо обычных 5-7.

#### 7.2.4. Дедлайны и срочность

**Проблема:** У NPC нет срочных дел. Торнин должен гильдии 1200 золотых — но нет срока.

**Дизайн:**
- Каждое `origin_event` имеет опциональное `deadline: int` (тики до дедлайна).
- `tornin_debt.deadline = 30 * 24 * 60` (30 дней) — через 30 дней гильдия «присылает людей».
- За 5 дней до дедлайна `stress` Торнина растёт +0.1/час.
- В день дедлайна — `WorldEvent: GUILD_ENFORCERS_ARRIVE` → 3 враждебных NPC входят в таверну.
- Игрок может: заплатить долг за Торнина, предупредить Торнина, предложить помощь в побеге.

**Метрика:** Игрок видит изменения в поведении Торнина (психике) по мере приближения дедлайна.

#### 7.2.5. Долгосрочные тренды

**Проблема:** Мир не развивается. Отношения static, экономика static.

**Дизайн:**
- Каждые 7 игровых дней: `EconomicTrend.update` — цены на хлеб растут если был неурожай, падают если караван пришёл.
- Каждые 30 дней: `ReputationTrend.update` — NPC с `trust_avg < 30` уезжает из деревни.
- Каждые 90 дней: `SocialTrend.update` — новые NPC приезжают, старые могут умереть (естественные причины).

**Метрика:** В новой игре (через 3 месяца игрового времени) состав NPC отличается от стартового.

#### 7.2.6. Воспоминания и годовщины

**Проблема:** NPC не помнят важные даты. Тень убил человека 3 года назад — но это статичный факт, не годовщина.

**Дизайн:**
- `origin_events` имеют `anniversary_date: str` (игровой календарь).
- В годовщину `shadow_first_kill` Тень получает `stress +0.3` на 24 часа, идёт в `dark_corner`, пьёт.
- Игрок в этот день видит `PeripheralCue: "Тень мрачнее обычного, смотрит в кружку"`.

**Метрика:** В годовщину `shadow_first_kill` поведение Тени заметно отличается.

#### 7.2.7. Фестивали и события деревни

**Проблема:** Деревня мертва вне таверны.

**Дизайн:**
- Раз в 30 дней — `VillageFestival` → все NPC идут на площадь, таверна пустая.
- Игрок может пойти на фестиваль, встретить всех NPC в другом контексте.
- На фестивале другие `social_norms` (громче, дружелюбнее), другие `affordances`.

**Метрика:** В день фестиваля таверна пустая, на площади — все NPC.

#### 7.2.8. Ночные события

**Проблема:** Ночью ничего не происходит. Хотя именно ночью должны быть воровство, любовные встречи, тайные собрания.

**Дизайн:**
- С 22:00 до 06:00 — `time_of_day: NIGHT`.
- NPC с `traits: ["thief"]` активируются: `STEAL` intent повышается на 0.3.
- `Lovers` (Lusya+Orm) встречаются в `dark_corner` → `ObservationLog: eavesdrop` если игрок подслушивает.
- `shadow_investigation` прогрессирует: Тень обыскивает комнаты посетителей.

**Метрика:** Ночью в логах видно ≥ 2 скрытых события (STEAL, secret meeting, investigation).

#### 7.2.9. Время как ресурс для игрока

**Проблема:** Игрок может торчать в таверне бесконечно. Нет давления времени.

**Дизайн:**
- Каждая сессия имеет `soft_time_limit: 4 hours` игрового времени.
- После 4 часов: `WorldEvent: TORNNIN_HINTS_PLAYER_LEAVE` — Торнин вежливо намекает.
- После 6 часов: `WorldEvent: BORKO_ASKS_PLAYER_LEAVE` — Борко менее вежливо.
- После 8 часов: `ExitTrigger` срабатывает принудительно.

**Метрика:** Сессия длится 30-90 минут реального времени, не более.

#### 7.2.10. Календарь и сезоны секретов

**Проблема:** Все 16 секретов доступны всегда. Нет временных окон.

**Дизайн:**
- `lusya_orm_borko` встречаются только ночью (см. §7.2.8).
- `borko_voyeur` — только когда Люся и Орм вместе.
- `shadow_first_kill` годовщина — раз в год (см. §7.2.6).
- `goran_contraband` — только в дни прибытия караванов (раз в 14 дней).

**Метрика:** В одной сессии игрок может раскрыть 5-8 секретов из 16, остальные требуют другого временного слота.

### 7.3. СОЦИАЛЬНЫЕ МЕХАНИКИ (приоритет 1)

#### 7.3.1. Тон реплик и его визуализация

**Проблема:** Все реплики выглядят одинаково. Игрок не видит эмоциональной окраски.

**Дизайн:** (из оригинала §5.5, но расширенно)
- Speech bubble с цветным краем по tone:
  - NEUTRAL — серый
  - FRIENDLY — зелёный
  - ANGRY — красный
  - FLIRTY — розовый
  - VENTING — фиолетовый
  - FEARFUL — бледно-голубой
  - MANIPULATIVE — тёмно-фиолетовый
- Шрифт bubble меняется: ANGRY — bold, FLIRTY — italic, WHISPER — мелкий.
- Длительность показа: WHISPER — 2 сек, SHOUT — 6 сек.

**Метрика:** За 5 минут idle видно ≥ 3 bubble с разными цветами.

#### 7.3.2. Mood-иконки над NPC

**Проблема:** Эмоции NPC невидимы. Игрок не знает, что Люся расстроена.

**Дизайн:** (из оригинала §5.5)
- Иконка 20×20 px над головой NPC:
  - 😢 грусть (sadness > 0.5)
  - 😡 гнев (anger > 0.5)
  - 💗 влюблённость (joy + attraction)
  - 😨 страх (fear > 0.5)
  - 😴 усталость (fatigue > 0.7)
  - 💢 раздражение (annoyance > 0.6)
- Если эмоция слабая — иконка полупрозрачная.
- NPC может «скрывать» эмоцию (черта `stoic`) — иконка не показывается.

**Метрика:** Игрок видит смену иконок у одного NPC за сессию ≥ 4 раза.

#### 7.3.3. Romantic relationships arc

**Проблема:** Любовные отношения — статичные факты. Нет развития: знакомство → флирт → свидание → отношения → разрыв.

**Дизайн:**
- `relationship_stage: enum(STRANGER, ACQUAINTANCE, FRIEND, FLIRTING, DATING, COUPLE, BROKEN_UP)`.
- Каждая стадия имеет порог `trust + attraction`.
- На каждой стадии доступны разные `tone`: STRANGER → NEUTRAL только, FLIRTING → +FLIRTY, COUPLE → +VENTING+FRIENDLY.
- Progression требует N успешных DIALOGUE с правильным tone.
- Regression: DIALOGUE(ANGRY) -5 progress, длительное отсутствие -1/day.

**Метрика:** За 10 игровых дней видна хотя бы одна пара в стадии FLIRTING, переходящая в DATING.

#### 7.3.4. Слухи и их распространение

**Проблема:** `SocialEngine` есть, но `trust_delta = 0.05` — слухи не работают.

**Дизайн:**
- Слух = `Rumor(source, target, content, spread_radius, decay_rate)`.
- NPC с `gossip_trait` распространяет слухи в `DIALOGUE(tone=FRIENDLY)` → все слушатели получают `belief(content, confidence=0.3)`.
- Через 3 передачи слух достигает `confidence=0.7` (но может искажаться — `content_mutator`).
- Игрок может быть источником слуха: «Я слышал, что Люся...» → `Rumor(player, all, ...)`.

**Метрика:** За 30 минут игрок слышит ≥ 2 слуха от разных NPC.

#### 7.3.5. Конфликты и их эскалация

**Проблема:** NPC могут поссориться, но конфликт не развивается — либо затухает, либо резко.

**Дизайн:**
- `Conflict(actor_a, actor_b, severity: float, history: List[Episode])`.
- Severity растёт от 0 до 1. При `severity > 0.5` — `tone=ANGRY` по умолчанию между ними.
- При `severity > 0.8` — один из них генерит `Intent.ATTACK`.
- При `severity > 0.9` — `WorldEvent: VENDETTA_DECLARED` → долгосрочная вражда.
- Снижение severity: `DIALOGUE(tone=FRIENDLY, target=enemy)` от третьего лица (посредник).

**Метрика:** За игровую неделю хотя бы один конфликт доходит до severity=0.7 и mediator вмешивается.

#### 7.3.6. Альянсы и фракции

**Проблема:** Фракции в конфиге есть, но не работают. NPC не действуют «как фракция».

**Дизайн:**
- NPC во фракции имеют `faction_loyalty: float` (0-1).
- При конфликте NPC_A vs NPC_B, NPC_C той же фракции что и A получает `Intent.APPROACH + DIALOGUE(tone=ANGRY, target=B)`.
- `faction_event` (плата Борко от Горана) → все члены `merchants_guild` узнают → доверие к Борко падает на 5.
- Игрок может «стать» членом фракции через квест → получает allies.

**Метрика:** При Attack на NPC из `thieves_guild` остальные члены гильдии реагируют в течение 3 тиков.

#### 7.3.7. Социальный статус и иерархия

**Проблема:** Все NPC равны. Трактирщик не имеет власти над посетителями.

**Дизайн:**
- NPC имеет `social_rank: enum(VAGRANT, COMMONER, CRAFTSMAN, MERCHANT, NOBLE, AUTHORITY)`.
- В диалоге lower rank → higher rank: `tone=FRIENDLY` по умолчанию, `-anger_modifier`.
- Higher rank может приказать (`directive`) → lower rank с `loyalty > 0.5` подчиняется.
- Игрок с low rank: NPC могут отказать в разговоре, прогнать.

**Метрика:** Торнин (AUTHORITY в таверне) может приказать Люсе (COMMONER) убрать стол — Люся подчиняется без отказа.

#### 7.3.8. Долг и благодарность

**Проблема:** NPC не помнят услуг. Помог Люсе — она не благодарна.

**Дизайн:**
- `debt_graph: Dict[npc_a, Dict[npc_b, debt_value]]` — кто кому должен.
- Игрок помогает NPC → `debt_graph[npc][player] += 1`.
- NPC с `debt > 3` к игроку → `Intent.APPROACH + DIALOGUE(tone=FRIENDLY)`, предлагает помощь.
- NPC с `debt < -3` (игрок должен) → `Intent.AVOID`, при встрече требует вернуть долг.

**Метрика:** Если игрок 3 раза помог Люсе, на 4-й раз она сама подходит и предлагает помощь.

#### 7.3.9. Манипуляции и обман

**Проблема:** NPC честны. Нет манипуляций, лжи, обмана.

**Дизайн:**
- NPC с `traits: ["manipulative"]` могут генерировать `tone=MANIPULATIVE`.
- `Intent.SPREAD_RUMOR` с `is_false: true` → spread ложного слуха.
- Цель манипуляции: повысить свой `trust` у цели, понизить `trust` цели к кому-то другому.
- Игрок может заметить манипуляцию через `PerceptionLayer` если у NPC высокая `deception_skill` vs игрока `insight_skill`.

**Метрика:** Тень манипулирует Люсей (убеждает, что Горан враг) → Люся начинает избегать Горана.

#### 7.3.10. Семья и кровные узы

**Проблема:** Все NPC «одинокие». Нет семей, братьев, детей.

**Дизайн:**
- NPC configs имеют `family: Dict[relation_type, List[npc_id]]` (parent, child, sibling, spouse).
- При Attack на NPC_A его `family["child"]` NPC_C генерирует `Intent.ATTACK` на обидчика.
- Family members имеют +30 к базовому `trust` друг к другу.
- Семейные ссоры: `DIALOGUE(tone=ANGRY)` между family members → `severity` растёт быстрее, но и прощение быстрее.

**Метрика:** Если у Орма есть брат, при конфликте Орма с Борко брат вмешивается.

#### 7.3.11. Микромимика и micro-expressions

**Проблема:** NPC либо показывают эмоцию (иконка), либо нет. Нет тонких сигналов.

**Дизайн:**
- `MicroExpression(npc_id, type: enum(FLINCH, SMILE, FROWN, LOOK_AWAY, PRACTICAL_TOUCH), duration_frames)`.
- Срабатывает на низких значениях эмоций (0.2-0.5), когда mood-иконка ещё не показывается.
- Игрок с высоким `perception_skill` видит micro-expressions → `ObservationLog: visual_cue` с confidence=0.4.
- NPC с `traits: ["stoic"]` подавляют micro-expressions.

**Метрика:** Игрок видит «Люся отвела взгляд, когда Тень вошёл» — это micro-expression, не mood-иконка.

### 7.4. ЭКОНОМИЧЕСКИЕ МЕХАНИКИ (приоритет 2)

#### 7.4.1. Видимые транзакции

NPC-NPC транзакции должны быть **видимы** игроку: «Горан дал Борко 5 золотых» в журнале. Сейчас TransactionEngine не вызывается — см. §4.3.

#### 7.4.2. Динамика цен

`MarketState.update_prices` раз в день. Игрок видит цены на товары (через DM запрос: «сколько стоит эль?»).

#### 7.4.3. Контрабанда и дефицит

`goran_contraband` secret → при провале каравана цена на шёлк ×3. Игрок может купить дёшево и продать дорого в другой деревне.

#### 7.4.4. Долги и банкротство

NPC с `debt > income * 3` → банкрот, продаёт имущество, снижает `social_rank`.

#### 7.4.5. Найм и оплата услуг

Игрок может нанять NPC (`OFFER_JOB` intent): «Борко, присмотри за Люсей tonight, заплачу 10 золотых» → `QueuedTask(WATCH, owner=Borko, target=Lusya, duration=8h, reward=10g)`.

### 7.5. БОЕВЫЕ МЕХАНИКИ (приоритет 2)

#### 7.5.1. Видимые бои NPC-NPC

После §4.2 (ATTACK в proactive_intents) — бои должны быть видны: эффекты (кровь, удары), injury_state, fugitive_runs.

#### 7.5.2. Травмы и восстановление

`InjuryProcessor` есть, но травмы не видны. NPC с `injury_state: BROKEN_ARM` — анимация другая, не может `ATTACK`, медленнее ходит.

#### 7.5.3. Оружие и экипировка

У каждого NPC `equipment: Dict[slot, item_id]`. Влияет на combat_math. Видно визуально ( Борко с мечом vs Борко без меча).

#### 7.5.4. Страх и бегство

`fear > 0.7` → `Intent.FLEE`. NPC бежит к exit, выходит из локации, возвращается через 30-60 минут игрового времени с `fear` ниже.

#### 7.5.5. Смерть и её последствия

NPC с `effective_hp <= 0` → `life_status: DEAD`. Body остаётся в локации 10 минут, потом `WorldEvent: BODY_REMOVED`. Investigation event — стража приходит, опрашивает свидетелей.

### 7.6. ЭПИСТЕМИЧЕСКИЕ МЕХАНИКИ (приоритет 2 — для мини-игры)

#### 7.6.1. Клик-таргетинг NPC

Игрок кликает на NPC на карте → открывается диалоговое окно. Сейчас этого нет.

#### 7.6.2. Eavesdrop радиус

Игрок стоит в 3м от NPC-NPC диалога → `ObservationLog: eavesdrop`. См. §7.1.3.

#### 7.6.3. Blackmail action

Игрок печатает «я знаю про подвал» → `DirectiveSubscriber: social_pressure=0.8`. NPC реагирует через BehaviorMask (FAKE_SUBMISSION).

#### 7.6.4. Environmental investigation

Игрок кликает на `basement_door` → `INTERACT` → `ObservationLog: environmental` с `secret_hint`.

#### 7.6.5. Overheard rumors

`WorldProjectionBuffer` генерирует слухи → игрок иногда видит их в чате «Слыхали? ...».

#### 7.6.6. End-screen

После `ExitTrigger` → экран результата с таблицей (см. §7.1 документа-источника).

---

## 8. ПРАВИЛА ДЛЯ LLM-АРХИТЕКТОРА

*Перенесено из оригинала без изменений — правила актуальны.*

### 8.1. Дисциплина
1. Не создавай новые подсистемы, пока не подключены существующие. Сначала Этап 1, потом 2, потом 3, потом 4.
2. Не нарушай принцип «без скриптов» (§1).
3. Не удаляй существующие тесты, даже failing.
4. Не добавляй новые TODO без оценки времени.
5. После каждого этапа — отчёт в `reports/history/<date>.md`.

### 8.2. Работа с кодом
1. Перед любым изменением — читать `worklog.md` и последние 2-3 отчёта.
2. После любого изменения — запись в `worklog.md`.
3. Не делать больших рефакторингов без разрешения.
4. Сохранять совместимость с конфигами.
5. Новые поля в DTO — optional с дефолтом.

### 8.3. Принципы эмерджентности
1. Правила, не сценарии.
2. Drives, not commands.
3. Reactions, not triggers.
4. Beliefs, not flags.
5. Patterns, not sequences.

### 8.4. Что делать, если что-то не работает
1. Сначала отладка — `causal_oscilloscope.py`, `cds_backend.log`, `enigma_<date>.jsonl`.
2. Потом минимальный фикс.
3. Не переписывать модуль целиком.
4. Если нужен рефакторинг — описать в `worklog.md`.

---

## 9. КОНТРОЛЬНЫЕ ВОПРОСЫ ДЛЯ САМОПРОВЕРКИ

### После Этапа 0:
- [ ] **§3.1:** В `cds_backend.log` нет `[TICK_CRASH]` после 30-секундного idle?
- [ ] **§3.1:** `game_time_seconds` растёт без ввода игрока (часы в HUD обновляются)?
- [ ] **§3.1:** `active_traversals` не пустой после 30 сек idle?
- [ ] **§3.2:** idle_tick запускается каждые 0.5-3 секунды (а не каждые 2-30 сек)?
- [ ] **§3.2:** idle_tick не блокируется во время LLM-запроса DM?
- [ ] **§3.3:** NPC с intent=seek_ally/request_service/etc. создают MovementIntent?
- [ ] **§3.3:** За 30 секунд без ввода ≥ 3 NPC начали движение (status=MOVING)?
- [ ] **§3.4:** `[TICK_ORCH] Фаза 6: N intents → EventDTO` где N > 0 (а не 0)?
- [ ] **§3.4:** `[TRACE][DECISION_SCORE]` виден в логах хотя бы 1 раз за 30 сек?
- [ ] **§3.5:** `pending_tasks` в scene_state не пустой?
- [ ] **§3.5:** `[TASK_SCHED] dialogue executed` виден в логах ≥ 2 за 30 сек?
- [ ] **§3.5:** CPU ≤ 70% при автономной работе 5 минут?
- [ ] **§3.6:** `[NPC_DIALOGUE_SUB] ... heard ...` виден в логах ≥ 3 за 2 минуты?
- [ ] **§3.6:** Эмоции listener'а меняются после реплики speaker'а?
- [ ] **§3.6:** `trust` между парами NPC меняется (видно через debug overlay)?
- [ ] **§3.7 AWC:** Все 8 пунктов (A-H) Автономного Мир-Контракта выполняются?
- [ ] **§3.7 AWC:** `verify_autonomous_world.py` проходит без ошибок?
- [ ] `python game_launcher.py` запускается без крача?
- [ ] POST `/api/game/{id}/input` возвращает 200, а не 500?
- [ ] `pytest backend/tests/` — failing < 50?
- [ ] Llama-server на правильном порту (одном во всех 6 местах)?
- [ ] `game_launcher.py` не оставляет открытых fd?
- [ ] C4 NameError в `affect.py` пофиксен?
- [ ] `l1_chronicle.py:71-72` — `except Exception: pass` заменён на `logger.exception`?
- [ ] 5 брошенных модулей: 4 подключены, 1 удалён (front_applicator)?

### После Этапа 1:
- [ ] За 5 минут без ввода игрока в таверне происходит видимое событие?
- [ ] `proactive_intents` содержит ATTACK, STEAL, FLEE, TRADE, **DIALOGUE**, APPROACH, AVOID?
- [ ] `TransactionEngine.execute_sale` вызывается хотя бы раз за игровой день?
- [ ] `npc_state_helpers`, `reaction_priority`, `perceptual_attention_service`, `role_transition` подключены?
- [ ] `WorldScheduler.disabled_pending_phase6` заглушка заменена на реальный вызов?

### После Этапа 2:
- [ ] Тестовая сцена «Торнин → Люся → Горан» возникает без ввода игрока?
- [ ] В `cds_backend.log` цепочка `DRF_EMIT → PERCEIVE → DRF_EMIT → BELIEF_CRYSTALLIZED → DRF_EMIT`?
- [ ] Speech bubbles с цветными краями для NPC-NPC диалогов?
- [ ] Mood-иконки над NPC обновляются?
- [ ] В журнале (Ё) записи о видимых NPC-NPC взаимодействиях?
- [ ] В `CrystallizedBeliefStore` после 30 тиков есть belief из паттерна?

### После Этапа 3:
- [ ] `TruthStateLoader` загружает 16 секретов?
- [ ] Каузальный граф 20 связей?
- [ ] `ObservationLog` заполняется из EventBus?
- [ ] `PlayerBeliefModel` обновляется?
- [ ] `ExitTrigger` срабатывает при выходе из `tavern_silver_wolf`?
- [ ] `EndScreenRenderer` показывает таблицу?
- [ ] При повторной игре отношения и связи другие?

### После Этапа 4 (новое):
- [ ] **Пространственные:** есть зоны с affordances, линии видимости, акустические радиусы?
- [ ] **Временные:** есть расписание локации, циклы NPC, сезоны?
- [ ] **Социальные:** есть tone в speech bubbles, mood-иконки, слухи, конфликты, фракции?
- [ ] За 10 минут idle в журнале игрока ≥ 5 разных типов событий (movement, dialogue, transaction, mood_change, rumor)?
- [ ] NPC разных фракций реагируют на конфликт с членом своей фракции?
- [ ] Ночью в таверне происходят скрытые события (STEAL, secret meeting)?

---

## 10. ОЖИДАННЫЙ РЕЗУЛЬТАТ ЧЕРЕЗ 6-8 НЕДЕЛЬ

Если все 4 этапа пройдены:

1. **Игрок заходит в таверну** и видит живой мир: NPC разговаривают друг с другом (speech bubbles с разными цветами и шрифтами), у них меняются эмоции (mood-иконки + micro-expressions), возникают конфликты и примирения, альянсы и предательства.

2. **Игрок наблюдает** за Торниным, который сам, без скрипта, накричал на Люсю из-за стресса (deadline приближается). Видит, как Люся с грустной иконкой над головой идёт к Горану. Видит, как Горан отвечает ей дружелюбно, и у него над головой появляется 💗.

3. **Пространство живое**: Люся и Тень уходят в тёмный угол, игрок теряет линию видимости и не слышит их шёпота. Игрок может подойти ближе, чтобы подслушать, но рискует быть замеченным.

4. **Время живое**: в 22:00 таверна пустеет, остаётся Тень, который обыскивает комнаты. В 02:00 приходит Борко на смену. В день фестиваля все уходят на площадь.

5. **Игрок пытается разгадать** отношения: подслушивает, наблюдает за micro-expressions, пытается шантажировать Люсю. Система запоминает каждое его действие и обновляет `PlayerBeliefModel` неведомо для него.

6. **Игрок выходит из таверны** — и видит экран результата: «7 из 16 секретов раскрыто, 2 ошибочных вывода, каузальный граф 40%, методы: 12 наблюдений + 8 диалогов + 3 подслушивания + 1 шантаж».

7. **Игрок хочет переиграть** — потому что понимает, что в новой сессии драма будет **другой**: у Люси может быть другой любимый (romantic arc ушёл в другую сторону), у Торнина — другая фрустрация (другой deadline), у Горана — другое отношение к Люсе. И он хочет построить более точную модель мира.

**Это и есть «живая игра».**

---

## 11. ФИНАЛЬНАЯ МЫСЛЬ

Этот проект — не «игра с NPC». Это **эмерджентная симуляция социальной драмы**, замаскированная под игру. NPC не «выполняют роли» — они **живут**. Игрок не «решает квесты» — он **наблюдает и реконструирует**.

Однако проект был парализован тривиальной Python-ошибкой — `TypeError: Type List cannot be instantiated` в `sqlite_persistence_adapter.py:84`. Это не архитектурная проблема, не сложная deadlock-ситуация, не противоречие в ТЗ. Это **один вызов `List[Any](o)` вместо `list(o)`** в JSON-сериализаторе. Из-за неё:
- 227 `TICK_CRASH` за сессию 4 июля
- 11 `TICK_CRASH` за 40-секундную сессию создателя 13 июля
- Симуляция работала в памяти, но не сохранялась — каждый idle_tick откатывался
- Создатель видел «игра сломана полностью» и не имел возможности проверить архитектуру в действии.

**Урок для LLM-архитектора:** прежде чем добавлять новые подсистемы, расширять whitelists, строить эмерджентные циклы — убедись, что **существующий код запускается и сохраняет состояние**. Один `TypeError` в persistence стоит дороже, чем 1000 строк новых механик, потому что он делает невидимым всё, что ты напишешь поверх. Каждый idle_tick проходит Phase 0-9, LifeEngine создаёт spatial changes, DecisionHub принимает решения — и всё это **выбрасывается** на Phase 10.

Если ты, LLM-архитектор, сделаешь всё по этому ТЗ — у тебя будет нечто, чего не сделал никто в инди-RPG. Если соблазнишься скриптами — получится очередная «Skyrim с AI-диалогами», и игрок пройдёт её за вечер.

**Выбирай первое. Но сначала — почини persistence (одна строка).**

---

*Документ актуализирован 13 июля 2026 г. (ревизия 3) на основе полного аудита кода V.0.5.3.4.4 (581 .py файл), логов runtime `cds_backend.log` за 12 дней (2-13 июля) и репортажа сессии создателя от 13 июля 06:52. Все ссылки на файлы и номера строк актуальны на момент создания.*

*Ревизия 2 переписала §3.1 после разбора `cds_backend.log` — изначальная диагностика (SceneStateManager UnboundLocalError) была неверной: DM agent в реальности работает, реальная проблема в persistence-слое (`TypeError` в `sqlite_persistence_adapter.py:84`).*

*Ревизия 3 добавила §3.4-3.7: анализ почему NPC-NPC диалоги не возникают (`communication_intents=0`), TaskScheduler+LLM throttling, NpcDialogueSubscriber для замыкания цикла восприятия, и Автономный Мир-Контракт (AWC) как финальную спецификацию «мир живёт сам». Без AWC — Этап 0 не пройден, нельзя переходить к Этапу 1.*
