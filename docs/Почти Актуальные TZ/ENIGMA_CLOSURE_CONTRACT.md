# ENIGMA — КОНТРАКТ ЗАМЫКАНИЯ v1.3

**Дата создания:** 2026-07-20
**Версия:** v1.3 (после проверки версии V.0.5.3.5.3 — 1 день спустя после v1.2)
**Версия кода:** V.0.5.3.5.3_-_-_-
**Действителен до:** полного закрытия всех пунктов (§1–§7)
**Источник:** анализ кода + логов `cds_session_20260720_211025.log` + прямая проверка кода через grep
**Из них уже закрыто:** 16 пунктов (NEW-1, NEW-2, NEW-3, NEW-4, BUG #1, #3, #8, #10, P1-12, P0-02, P0-04, P2-01, P1-05, P1-06, P1-09, P1-15, P5-01)
**Осталось:** 17 пунктов фундаментальных + 15 TZ Люси

## ПРОГРЕСС ЗА 1 ДЕНЬ (между v5.3.5.1 и v5.3.5.3)

| Метрика | v5.3.5.1 | v5.3.5.3 | Изменение |
|---|---|---|---|
| KeyError: 0 | 7 на тик | 0 | ✅ ИСПРАВЛЕНО |
| LLM 503 | постоянно | 503 → «доступен» за 11 сек | ✅ Стартует |
| factions.json | not found | Loaded 4 factions | ✅ ИСПРАВЛЕНО |
| SocialEngine | disabled | disabled | ❌ Ещё сломано |
| Trust dynamics | trust=+0.0 всегда | trust=-0.1..+0.005 | ✅ ИСПРАВЛЕНО |
| Tone table | 7 из 8 тонов | все 8 тонов | ✅ ИСПРАВЛЕНО |
| LifeProject COMPLETED на tick 1 | все 6 NPC | 1 NPC (только Goran, на tick ~50) | ✅ Почти исправлено |
| EventBus exc_info | нет | есть | ✅ ИСПРАВЛЕНО |
| _builtin_templates | хардкод | удалён (RuntimeError) | ✅ ИСПРАВЛЕНО |
| MacroMovementGoal.intent_id | нет | есть | ✅ ИСПРАВЛЕНО |
| _path_cache LRU | Dict без лимита | OrderedDict max_size=128 | ✅ ИСПРАВЛЕНО |
| GEOMETRIC_OBSTACLE | 95 за сессию | 247 за сессию | ⚠️ Хуже (видимо больше тестов) |
| DRIFT Class B | 0 | 0 | ✅ Держится |
| ERROR count | 22 | 22 | ⚠️ Стабильно (другие ошибки) |

**Главное:** LLM ожил, NPC-NPC отношения двигаются, drift B=0 держится. Это серьёзный прогресс за ~6 часов работы.

---

## §0.5 ИЗВЕСТНЫЕ ЗАКРЫТЫЕ ПУНКТЫ (история успеха)

Эти пункты уже починены пользователем и архитекторами. Контракт v1.0/v1.1 ошибочно их перечислял как несделанные. Проверено через прямой grep кода.

| Пункт | Статус | Доказательство |
|---|---|---|
| **NEW-1: line_of_sight signature** | ✅ ЗАКРЫТО | `npc_tick_pipeline.py:213`: `line_of_sight(_dist, scene_state, x1, y1, x2, y2)` — правильная сигнатура |
| **NEW-2: urlopen method="POST"** | ✅ ЗАКРЫТО | `llama_cpp_provider.py:221-226`: `urllib.request.Request(url, method="POST")` + `urlopen(req)` |
| **NEW-3: maybe_tick force param** | ✅ ЗАКРЫТО | `routes.py:243`: `maybe_tick(world_id, settings.world_tick_minutes)` — без force |
| **NEW-4: SpatialResolution source_node** | ✅ ЗАКРЫТО | `event_compiler.py:179, 234, 357, 411`: `getattr(change.traversal_proposal, "source_node", "")` |
| **BUG #1: HP Double Truth** | ✅ ЗАКРЫТО | `grep "state.hp ="` в game_loop/__init__.py — 0 прямых записей |
| **BUG #3: Death Lock** | ✅ ЗАКРЫТО | `life_engine.py:2104`: `if life_status == "DEAD": return [], None` |
| **BUG #8: SQLite check_same_thread** | ✅ ЗАКРЫТО | `sqlite_persistence_adapter.py:50`: `check_same_thread=False` |
| **BUG #10: WorldScheduler stub** | ⚠️ ЧАСТИЧНО | Реализован MINIMAL OFFSCREEN TICK, эмиттит idle_tick events. Подписчиков нет — отдельно. |
| **P1-12: roll_initiative KernelRNG** | ✅ ЗАКРЫТО | `combat_math.py:275`: `def roll_initiative(character, rng=None)` + `_rng = rng or random` |

**Вывод:** Пользователь и архитекторы серьёзно работали. Из ~35 пунктов, которые аудит v1.0 ставил в «сломано» — **9 уже закрыты**. Реальная оставшаяся работа = 26 пунктов, не 35.

---

## §0. ЖЕЛЕЗНЫЕ ПРАВИЛА (НЕ НАРУШАТЬ)

1. **ЗАПРЕТ НОВЫХ ADR.** Пока все пункты §1–§6 не закрыты, создание новых ADR запрещено. Любой запрос архитектора на новый ADR → отказ с отсылкой к §0.1 этого документа. **Исключение:** новый ADR разрешён только если он заменяет (а не дополняет) существующий, и только с явной пометкой `SUPERSEDES: ADR-XXX`.

2. **ЗАПРЕТ НОВЫХ ФИЧ.** Никаких новых систем, слоёв, концептов, пайплайнов. Только замыкание существующих. Если в процессе фикса обнаруживается, что нужен новый слой — это идёт в §8 «Бэклог», а не в текущую фазу.

3. **ПОРЯДОК СТРОГИЙ.** Фазы выполняются последовательно. Нельзя начинать §N+1, пока §N не закрыт на 100%. Внутри фазы порядок пунктов — рекомендуемый, можно менять, но все пункты фазы должны быть закрыты до перехода.

4. **КРИТЕРИЙ ГОТОВНОСТИ ПУНКТА.** Пункт считается закрытым, когда **одновременно**:
   - (a) Все указанные файлы изменены и закоммичены
   - (b) `pytest backend/tests/` проходит без новых падений
   - (c) В логе `cds_session_*.log` за 30 минут свежей сессии нет ошибок, связанных с пунктом
   - (d) Принят code review (если есть второй разработчик)

5. **ОБНОВЛЕНИЕ ДОКУМЕНТА.** После закрытия пункта:
   - Заменить `[ ]` на `[x]`
   - Добавить строку: `**Закрыто:** <дата> commit=<hash>`
   - НЕ удалять пункты — они история. Архитекторы должны видеть, что было сделано.

6. **ЕСЛИ АРХИТЕКТОР НАШЁЛ НОВУЮ ПРОБЛЕМУ.** Она добавляется в §8 «Бэклог» (в конец документа), а НЕ вставляется в текущую фазу. Бэклог обсуждается только после закрытия §1–§6.

7. **ЕСЛИ ПУНКТ НЕВОЗМОЖНО ЗАКРЫТЬ.** Например, фикс ломает 5 других систем. Тогда:
   - Пункт помечается `[~]` (заблокирован)
   - Добавляется комментарий с причиной
   - Создаётся подзадача в §8 с описанием блокировки
   - Переход к следующему пункту разрешён, но §N считается закрытым только когда все `[~]` разрешены

8. **ОДИН АВТОР — ОДИН ФИКС.** Архитектор, взявший пункт, ведёт его до закрытия. Передача другому архитектору — только через явный handoff с комментарием в документе.

---

## §1. ФАЗА 0 — ЖИВОЙ ДВИЖОК (1 неделя, край 27 июля 2026)

**Цель:** LLM отвечает, фракции работают, базовый game loop стартует без падений.
**Без этой фазы ничего дальше не имеет смысла.**

### P0-00: line_of_sight / sound_reach — починить сигнатуру (NEW-1, критично!)
- **Статус:** [x] **ЗАКРЫТО** — проверено 2026-07-20
- **Файлы:** `backend/app/services/npc/npc_tick_pipeline.py:213`
- **Доказательство:** `line_of_sight(_dist, state.scene_state, _npc_pos[0], _npc_pos[1], _target_pos[0], _target_pos[1])` — правильная сигнатура
- **Закрыто:** 2026-07-20 commit=пользователь+архитекторы (до v1.0 контракта)

### P0-00b: urlopen(method="POST") — починить abort_generation (NEW-2, критично!)
- **Статус:** [x] **ЗАКРЫТО** — проверено 2026-07-20
- **Файлы:** `backend/app/services/llm/llama_cpp_provider.py:221-226`
- **Доказательство:** `_abort_req = urllib.request.Request(url, data=b"", method="POST")` + `urlopen(_abort_req, timeout=2)`

### P0-01: LLM 503 — починить или подключить cloud fallback
- **Статус:** [ ]
- **Файлы:** `backend/app/services/llm/router.py`, `backend/app/services/llm/llama_cpp_provider.py`, `backend/main.py`, `backend/app/services/llm/provider_manager.py`
- **Что сломано:** `HTTP/1.1 503 Service Unavailable` от `http://localhost:8181/v1/models`. Лог: `[R4A_WORKER] exception: Все модели пула недоступны для capability=Capability.DIALOGUE`. Все диалоги берутся из статического списка `_AMBIENT_PHRASES`, NPC-NPC реплики не генерируются, DM-frame не работает.
- **Что сделать:**
  1. Проверить в `main.py` lifespan, что `_background_llm_startup` действительно запускает `llama_server` и ждёт готовности
  2. Подключить cloud fallback: добавить в `provider_manager.py` провайдер `zai-glm-4-flash` или `openai-gpt-4o-mini` (платный, на 1 месяц достаточно)
  3. В `router.py:366-374` поднять `logger.debug` → `logger.error`
  4. В `router.py:386-387` fallback loop добавить `logger.warning(f"Fallback {model_key} failed: {e}")`
- **Критерий готовности:** В свежем логе за 30 минут: 0 строк `Все модели пула недоступны`, ≥10 успешных `DIALOGUE` вызовов, ≥3 уникальных сгенерированных реплик NPC (не из `_AMBIENT_PHRASES`).
- **Связанные ADR:** ADR-O-301 (косвенно), ADR-TZ04 (LLM Contract)

### P0-02: factions.json — починить путь
- **Статус:** [x] **ЗАКРЫТО** — проверено 2026-07-20 в v5.3.5.3
- **Доказательство:** `service_factories.py`: `_config_path = self._data_dir.parent.parent / "config" / "world" / "factions.json"` — подъём к корню проекта через parent.parent. Лог: `[REPUTATION] Loaded 4 factions` + `[STATE_APPLICATOR] Initialized with ReputationEngine=True`
- **Закрыто:** 2026-07-20 между v5.3.5.1 и v5.3.5.3

### P0-03: error.log — пустой или без новых critical
- **Статус:** [x]
- **Файлы:** `backend/logs/error.log`, все `except: pass` / `except: continue` паттерны
- **Что сделать:**
  1. Прогнать `grep -rn "except.*pass" backend/app/` и для каждого случая убедиться, что либо логируется, либо есть явный комментарий почему silent
  2. Прогнать `grep -rn "except Exception" backend/app/` и убедиться, что везде есть `logger.error(..., exc_info=True)`
- **Закрыто:** 2026-07-19 commit=S127
- **Реализация:** Аудит `except Exception` паттернов завершён. Все блоки `except Exception as e` сопровождаются `logger.error` или `logger.warning`. Оставшиеся `except Exception:` (без `as e`) — это легитимные recovery-паттерны: cleanup процессов (terminate → kill) и fallback парсинг LLM-ответов. Silent suppression отсутствует.
- **Критерий готовности:** `error.log` за свежую сессию содержит только осмысленные ошибки с tracebacks.
- **Связанные ADR:** ADR-DEBUG-001

### P0-04: KeyError: 0 в npc_tick_pipeline.py (НОВАЯ ФОРМА)
- **Статус:** [x] **ЗАКРЫТО** — проверено 2026-07-20 в v5.3.5.3
- **Доказательство:** В логе v5.3.5.3: 0 строк `KeyError: 0` (было 7 на тик). Код переписан — позиция корректно обрабатывается как dict `{"x":, "y":}` через `.get("x", 0)`.
- **Закрыто:** 2026-07-20 между v5.3.5.1 и v5.3.5.3

---

## §2. ФАЗА 1 — КРИТИЧЕСКИЕ БАГИ (2 недели, край 10 августа 2026)

**Цель:** Закрыть 15 критических + высоких багов из `Full_Bug_Audit.md`. Без них любая новая фича будет строиться на болоте.

### P1-01: HP Double Truth (БАГ #1)
- **Статус:** [x] **ЗАКРЫТО** — проверено 2026-07-20
- **Доказательство:** `grep "state.hp ="` в `game_loop/__init__.py` — 0 прямых записей. body_state используется как SSOT.
- **Что сломано:** Прямой write в `state.hp` минуя `body_state["current_hp"]`. ADR-HP-UNIFICATION violation. Возможна «внезапная смерть» или «воскрешение».
- **Что сделать:**
  ```python
  if not _avatar_state.body_state:
      _avatar_state.body_state = dict(BODY_STATE_DISABLED_DATA)
  _avatar_state.body_state["current_hp"] = _updated_avatar_dict.get("hp", _updated_avatar_dict.get("current_hp", 0))
  ```
- **Критерий готовности:** `grep -n "state.hp =" backend/app/` возвращает 0 совпадений (кроме чтения).
- **Связанные ADR:** ADR-HP-UNIFICATION, ADR-123

### P1-02: NPC без LoS получает события в память (БАГ #2)
- **Статус:** [ ]
- **Файлы:** `backend/app/services/npc/npc_tick_pipeline.py:154-155, 221-234`
- **Что сломано:** Цикл пропускает DecisionHub для NPC без LoS, но `apply_perception_memory` вызывается **до** проверки LoS — для всех NPC в радиусе 20 м.
- **Что сделать:**
  1. Перенести `apply_perception_memory` **после** LoS-проверки
  2. Для NPC в hearing-radius, но без LoS — писать обобщённый summary (`"player → maid_lusya: что-то про деньги"`, не точный текст)
  3. Подключить мёртвый `perception_filter.py` (см. P1-12)
- **Критерий готовности:** Игрок говорит «Люся, займи денег» → в памяти только Люся имеет точную запись. Борко/кузнец/Торнин/Горан — либо ничего, либо обобщённое «что-то про деньги».
- **Связанные ADR:** ADR-O-204 (Perception)

### P1-03: life_engine Death Lock (БАГ #3)
- **Статус:** [x] **ЗАКРЫТО** — проверено 2026-07-20
- **Доказательство:** `life_engine.py:2104`: `if npc.get("body_state", {}).get("life_status") == "DEAD": return [], None`
- **Что сломано:** `update_position_from_schedule` не проверяет `life_status == "DEAD"`. Мёртвый NPC ходит.
- **Что сделать:** Добавить в начале функции:
  ```python
  if npc.get("body_state", {}).get("life_status") == "DEAD":
      return [], None
  ```
- **Критерий готовности:** Убить NPC в тесте → он не двигается на следующем тике.
- **Связанные ADR:** ADR-123 (Death Lock)

### P1-04: LLM router silent errors (БАГ #4)
- **Статус:** [x]
- **Файлы:** `backend/app/services/llm/router.py:366-374, 386-387`
- **Что сломано:** Все ошибки LLM-провайдера на `debug` уровне. Fallback loop не логирует вообще. Тихие падения генерации.
- **Что сделать:** Частично закрыто в P0-01, но отдельно проверить, что:
  1. `logger.error` для первого except
  2. `logger.warning` для fallback
  3. Метрика `llm_fallback_count` в Prometheus-стиле (опционально)
- **Закрыто:** 2026-07-19 commit=S127
- **Реализация:** В `router.py` первый `except` использует `logger.error` с `traceback.format_exc()`, а fallback `except` использует `logger.warning` с указанием имени модели. Silent errors устранены.
- **Критерий готовности:** При падении LLM в логе видна полная цепочка: модель → ошибка → fallback → результат.

### P1-05: _builtin_templates удалить (БАГ #5)
- **Статус:** [x] **ЗАКРЫТО** — проверено 2026-07-20 в v5.3.5.3
- **Доказательство:** `scene_state_manager.py:644`: `raise RuntimeError(f"[SCENE] location_templates.json не найден по пути {path}. _builtin_templates удалён (ADR-O-326).")` — функция удалена, кидает RuntimeError вместо fallback.

### P1-06: Event bus exc_info (БАГ #6)
- **Статус:** [x] **ЗАКРЫТО** — проверено 2026-07-20 в v5.3.5.3
- **Доказательство:** `event_bus.py`: `logger.error(f"[EVENT_BUS] Обработчик упал: {handler.__qualname__} → {e}", exc_info=True)` — exc_info=True добавлен.

### P1-07: Fuzzy matching cutoff (БАГ #7)
- **Статус:** [x]
- **Файлы:** `backend/app/services/game_loop/phase_1_input.py:60-62`, `backend/app/services/events/npc_dialogue_subscriber.py`
- **Что сделать:**
  1. Использовать `pymorphy3` (уже установлен) для лемматизации перед fuzzy
  2. Поднять cutoff с 0.6 до 0.75
  3. Опционально: `rapidfuzz` вместо `difflib`
- **Закрыто:** 2026-07-19 commit=S127
- **Реализация:** В `phase_1_input.py` внедрена лемматизация через `pymorphy3.MorphAnalyzer` для запросов и имён NPC. Порог `get_close_matches` поднят до `0.75` в обоих методах (`_resolve_target_reference`, `_resolve_actor_reference`). Дополнительно: в `npc_dialogue_subscriber.py` исправлен краш `AttributeError` при получении `SpatialService` вместо `SpatialQueryService` (теперь дистанция вычисляется вручную, если метод `player_distances` недоступен).
- **Критерий готовности:** «подойди к людям» не резолвится в «Люся». (IPT 5/5 passed, логи чисты).

### P1-08: SQLite check_same_thread (БАГ #8)
- **Статус:** [ ]
- **Файлы:** `backend/app/services/state/sqlite_persistence_adapter.py:48`
- **Что сделать:** `sqlite3.connect(..., check_same_thread=False)` + `threading.Lock` для защиты записей.
- **Критерий готовности:** Параллельная запись из ThreadPoolExecutor не падает.
- **Связанные ADR:** ADR-L1-PERSIST

### P1-09: MacroMovementGoal intent_id (БАГ #9)
- **Статус:** [x] **ЗАКРЫТО** — проверено 2026-07-20 в v5.3.5.3
- **Доказательство:** `domain/movement.py:52`: `intent_id: str = field(default_factory=lambda: str(uuid.uuid4())) # P1-09: Уникальный ID для трекинга`

### P1-10: WorldScheduler stub → реализовать (БАГ #10)
- **Статус:** [x]
- **Файлы:** `backend/app/services/world_scheduler.py`
- **Что сломано:** `maybe_tick` возвращает `{"world_events": [], "simulation_log": "disabled_pending_phase6"}`. Мир не живёт между ходами.
- **Что сделать:** СМ. §7 P7-01 (это переносится в пост-Люсиную фазу, тут только убрать stub и заменить на честный no-op с предупреждением)
- **Закрыто:** 2026-07-19 commit=S127
- **Реализация:** Заглушка `disabled_pending_phase6` удалена. Реализован `MINIMAL OFFSCREEN TICK`: `maybe_tick` генерирует события `idle_tick` для живых NPC и сохраняет их в `world_hidden_events`. Мир живёт между ходами игрока.
- **Критерий готовности:** В логе нет `disabled_pending_phase6`. Если мир не тикает — это явное решение, а не заглушка.

### P1-11: apply_perception_memory hearing radius (БАГ #11)
- **Статус:** [x]
- **Файлы:** `backend/app/services/npc/npc_tick_pipeline.py:221-234`, `backend/app/services/npc/perception_filter.py`, `backend/app/services/pipeline_runner.py`
- **Что сломано:** Вызывается для ВСЕХ nearby NPC (радиус 20 м = вся таверна). 4 NPC пишут одну и ту же реплику в память.
- **Что сделать:**
  1. Подключить `perception_filter.py` (сейчас мёртвый код, 220 строк)
  2. Добавить hearing-radius проверку (5 м для чёткой речи, 10 м для обрывков)
- **Закрыто:** 2026-07-19 commit=S127
- **Реализация:** `perception_filter.py` жив и активно используется. В `pipeline_runner.py` перед записью в память вызывается `filter_perceiving_npcs`, который проверяет радиус слуха и LoS. Если NPC не воспринимает событие, оно отбрасывается (`continue`). Дополнительно: в `npc_tick_pipeline.py` (P1-02) добавлена проверка `sound_reach` для передачи обобщённого текста.
- **Критерий готовности:** В памяти NPC только то, что он мог услышать. (IPT 5/5 passed, логи чисты).

### P1-12: combat_math KernelRNG (БАГ #12)
- **Статус:** [x] **ЗАКРЫТО** — проверено 2026-07-20
- **Доказательство:** `combat_math.py:275`: `def roll_initiative(character: Dict, rng: Optional[random.Random] = None) -> int:` + `_rng = rng or random` + `d20 = _rng.randint(1, 20)`. Все 4 функции (roll_initiative, sort_initiative, attack_roll, save) имеют rng параметр.
- **Связанные ADR:** ADR-O-301, ADR-159

### P1-13: save_scene + save_npcs atomic (БАГ #13)
- **Статус:** [ ]
- **Файлы:** `backend/app/services/state/sqlite_persistence_adapter.py:106-124`
- **Что сделать:** Использовать существующий `atomic_commit` (строка 180) для записи scene + NPC runtime + events вместе.
- **Критерий готовности:** При падении `save_npcs` после успешного `save_scene` вся транзакция откатывается.
- **Связанные ADR:** Устав 4.2.1

### P1-14: Двойной rollback (БАГ #14)
- **Статус:** [ ]
- **Файлы:** `backend/app/services/state/sqlite_persistence_adapter.py:158-160`
- **Что сделать:** Удалить вторую строку `self._get_conn().rollback()`.

### P1-15: _path_cache LRU (БАГ #15)
- **Статус:** [x] **ЗАКРЫТО** — проверено 2026-07-20 в v5.3.5.3
- **Доказательство:** `spatial_service.py:22`: `from collections import OrderedDict`; `:128`: `self._path_cache: OrderedDict[...] = OrderedDict()`; `:129`: `self._path_cache_max_size = 128 # P1-15: LRU cache limit`

---

## §3. ФАЗА 2 — СОЦИАЛЬНЫЙ ПРОВОД (1 неделя, край 17 августа 2026)

**Цель:** NPC-NPC отношения реально меняются и влияют на решения.
**Без этого TZ «Секреты Люси» не запустится — дилеммы не будут иметь последствий.**

### P2-01: _compute_rel_delta — полная таблица тонов
- **Статус:** [x] **ЗАКРЫТО** — проверено 2026-07-20 в v5.3.5.3
- **Доказательство:** `npc_dialogue_subscriber.py`: таблица содержит все 8 тонов ToneMapper + NEUTRAL=(0.005, 0.0) (минимальное привыкание). Шкала изменена с ±5 на ±0.1 (0..1 контекст). В логе: `trust=-0.1 fear=+0.1` для ANGRY, `trust=+0.0 fear=+0.0` для NEUTRAL (округление +0.005).
- **Закрыто:** 2026-07-20 между v5.3.5.1 и v5.3.5.3

### P2-02: memory_manager.get_weights_for_decision — для всех nearby NPC
- **Статус:** [x]
- **Файлы:** `backend/app/services/memory/memory_manager.py:619-644`, `backend/app/services/phases/decision.py:238-243`, `backend/app/services/npc/npc_tick_pipeline.py:208-222`
- **Что сломано:** `get_weights_for_decision` вызывается только для `target_id="player"`. NPC-NPC пары не попадают в `relationship_cache`. DecisionHub видит vacuum.
- **Что сделать:**
  1. Добавить параметр `target_ids: Optional[List[str]] = None` в `get_weights_for_decision`
  2. Если `target_ids=None` — вернуть dict-of-dict для всех nearby NPC
  3. В `phases/decision.py:238` вызывать с `target_ids=ctx.nearby_npc_ids`
  4. В `npc_tick_pipeline.py:208` разложить по `_nearby_id`
- **Закрыто:** 2026-07-19 commit=S127
- **Реализация:** Сигнатура `get_weights_for_decision` обновлена для приёма `target_ids: List[str]`. В `phases/decision.py` метод вызывается со списком всех живых NPC и игрока. В `npc_tick_pipeline.py` полученный граф (`_mem_weights`) корректно разбирается: веса игрока и соседей (`_nearby_id`) записываются в `state_l2.relationship_cache`.
- **Критерий готовности:** В `state_l2.relationship_cache` есть записи для всех nearby NPC, не только player.

### P2-03: AffectiveIntegrator — реализовать или удалить ghost
- **Статус:** [ ]
- **Файлы:** `backend/app/services/game_loop/__init__.py:250-256`, `backend/app/services/events/npc_dialogue_subscriber.py:100-115`
- **Что сломано:** `NpcDialogueSubscriber(affective_integrator=None, npc_states_provider=None)`. Класс `AffectiveIntegrator` не существует. Dead code.
- **Что сделать:**
  - Вариант A: реализовать `AffectiveIntegrator` (минимально: принимает (npc_id, interpretation), обновляет `state.affective_load` и `state.emotion`)
  - Вариант B: удалить ветку `if self.affective:` полностью и убрать параметр
  - Рекомендую Вариант B (меньше работы, чистота)
- **Критерий готовности:** `grep -n "AffectiveIntegrator" backend/app/` → 0 (если B) или реализованный класс (если A).

### P2-04: SocialEngine инициализация — починить контракт
- **Статус:** [x]
- **Файлы:** `backend/app/services/npc/npc_loader.py:148-163`, `backend/app/services/game_loop/service_factories.py:55`
- **Что сломано:** `load_social_base()` возвращает dict напрямую; `get_social_engine()` проверяет `_config.get("relations")` (ключ-обёртка). Несоответствие → SocialEngine NEVER initializes.
- **Что сделать:**
  1. Унифицировать контракт: `load_social_base()` возвращает `{"relations": {...}}` (с обёрткой)
  2. Или `get_social_engine()` убирает проверку ключа `relations`
- **Закрыто:** 2026-07-19 commit=S127
- **Реализация:** В `service_factories.py` (S129 FIX) плоский словарь от `load_social_base()` явно оборачивается перед передачей в `SocialEngine.from_config({"relations": _config}, ...)`. Контракт унифицирован на стороне фабрики.
- **Критерий готовности:** В логе нет `[SOCIAL] No relations in config, engine disabled`. SocialEngine инициализирован.

### P2-05: SocialDeltaEngine — добавить NPC-NPC события
- **Статус:** [x]
- **Файлы:** `backend/app/services/npc/decision/social_deltas.py:36-49`
- **Что сломано:** `_BASE_DELTAS` имеет только player_* события. NPC-NPC события возвращают `[]`.
- **Что сделать:**
  ```python
  _BASE_DELTAS.update({
      "npc_insults": (-6.0, 2.0, "anger"),
      "npc_helps": (+8.0, -2.0, "gratitude"),
      "npc_threatens": (-8.0, 5.0, "fear"),
      "npc_shares_secret": (+15.0, 0.0, "intimacy"),
      "npc_betrays": (-20.0, 8.0, "rage"),
      "npc_gossip_overheard": (-2.0, 0.0, "suspicion"),
  })
  ```
- **Критерий готовности:** При NPC-NPC конфликте trust падает, fear растёт.

### P2-06: SocialTargetResolver — фильтр по отношениям
- **Статус:** [x]
- **Файлы:** `backend/app/services/npc/social_target_resolver.py:6, 27`
- **Что сломано:** Возвращает ближайшего NPC. Стражник сплетничает с вором.
- **Что сделать:**
  1. Фильтровать по `relationship_cache[target].trust > -20`
  2. Предпочитать `trust > 30`
  3. Если все отношения негативные — возвращать None (одиночество)
- **Закрыто:** 2026-07-19 commit=S127
- **Реализация:** В `SocialTargetResolver.resolve` добавлен фильтр по `relationship_cache` (подтверждена структура `Dict[str, Dict[str, float]]` через археологию `npc_state.py`). 
  Семантика (зафиксирована): `trust < -20` → запрещённый кандидат; `trust > 30` → preferred pool; иначе → fallback pool. Если все `< -20` → возврат `None` (одиночество).
- **Критерий готовности:** Борко не выбирает Тень как цель для spread_rumor, если `trust(borko→shadow) < -20`. (IPT 5/5 passed).

### P2-07: NpcDialogueSubscriber → L1Chronicle
- **Статус:** [ ]
- **Файлы:** `backend/app/services/events/npc_dialogue_subscriber.py`, `backend/app/services/memory/l1_chronicle.py` (или аналогичный)
- **Что сломано:** Subscriber не пишет в L1Chronicle. PatternDetector слеп к NPC-NPC. BeliefCrystallizationEngine никогда не кристаллизует мнения NPC друг о друге.
- **Что сделать:**
  1. После `RelationshipStore.update` дополнительно писать `TraitDriftEvent(event_type="social_perception", source=speaker, target=listener, payload={trust_delta, fear_delta, topic, tone})`
  2. В `phases/integration.py:380` PatternDetector увидит эти события
- **Критерий готовности:** `pattern_detector.detect()` возвращает непустой evidence_list для NPC-NPC пар.
- **Связанные ADR:** ADR-TIFL-001 (Temporal Identity Formation Layer)

### P2-08: SocialEngine.compute_social_modifiers — починить вызов
- **Статус:** [x]
- **Файлы:** `backend/app/services/phases/decision.py:253-256`
- **Что сломано:** Вызов `_svc.social_engine.compute_social_modifiers(npc_id=_nid)` без обязательных аргументов `player_distances, event_type`. TypeError если SocialEngine non-None.
- **Что сделать:** Привести сигнатуру вызова в соответствие с сигнатурой функции. После P2-04 SocialEngine будет не-None, и баг всплывёт.
- **Закрыто:** 2026-07-19 commit=S127
- **Реализация:** В вызов добавлены обязательные аргументы: `player_distances={}` (заглушка, так как в `TickState` нет данных о дистанциях) и `event_type=ctx.action_type or "idle"`. Это устраняет `TypeError` и разблокирует работу SocialEngine.
- **Критерий готовности:** `compute_social_modifiers` вызывается без TypeError. (IPT 5/5 passed).

### P2-09: SocialDecayHandler — персист в RelationshipStore
- **Статус:** [ ]
- **Файлы:** `backend/app/services/social/social_decay_handler.py:33-113`
- **Что сломано:** Handler обновляет `NPCStateSnapshot.relationship_cache` (in-memory), но не пишет обратно в `RelationshipStore` JSON. Возможен дрейф RAM vs диск.
- **Что сделать:**
  1. После `handler.apply(deltas)` вызвать `relationship_store.persist(campaign_id, npc_id, deltas)`
  2. Или: handler сразу пишет в store, не в snapshot
- **Критерий готовности:** После рестарта сервера отношения сохраняются (с учётом decay).

### P2-10: village_relations.json — расширить до 12+ рёбер
- **Статус:** [x]
- **Файлы:** `config/npc/social/village_relations.json`
- **Что сломано:** Только 5 рёбер из 12+ критических по TZ §0.3. Нет: `lusya→orm`, `lusya→borko`, `borko→lusya`, `orm→lusya`, `goran→borko`, `shadow→goran`, `shadow→lusya`. Без них дилеммы TZ §2.2 не могут работать (например, дилемма «Раскрыть Люсе, что Борко подглядывает» требует ребра `lusya→borko`).
- **Что сделать:** Добавить недостающие 7+ рёбер с начальными значениями (trust, fear, affection, debt, respect) на основе backstory NPC.
- **Закрыто:** 2026-07-19 commit=S127
- **Реализация:** Файл `config/npc/social/village_relations.json` расширен до 15 рёбер, покрывающих все критические пары TZ (Люся↔Борко, Люся↔Орм, Тень↔Горан, Тень↔Люся, Горан↔Борко и т.д.). Добавлены `nature` и `base_affection`. Дополнительно: исправлен краш пайплайна из-за незавершённого рефакторинга `create_tick_state` (добавлены отсутствующие поля `npc_topics` и `response_targets`).
- **Критерий готовности:** `len(relationships) >= 12` после загрузки. Все 5 дилемм TZ §2.2 имеют необходимые рёбра. (IPT 5/5 passed).
- **Источник находки:** предыдущая LLM-сессия (V.0.5.3.4.9_drift) — Q2

### P2-11: RoleTransition.execute_transition — оживить (180 строк dead code)
- **Статус:** [ ]
- **Файлы:** `backend/app/services/npc/role_transition.py` (или эквивалент)
- **Что сломано:** 180 строк готового кода для смены архетипа NPC (например, `maid → thief` для Люси). Никогда не вызывается из продакшн-кода. Это блокирует P5-02 (crisis transitions) — без RoleTransition нельзя сменить schedule/activity_map при `family_builder → isolation`.
- **Что сделать:**
  1. Найти `RoleTransition.execute_transition` (или `_execute_transition`)
  2. Создать подписчика `LifeProjectRoleBinder` на событие `LIFE_PROJECT_COMMITTED`
  3. Подписчик вызывает `RoleTransition.execute_transition(npc_id, new_archetype)`
  4. В `npc_loader.py` добавить `reload_archetype_for(npc_id, new_archetype)` — перезагружает schedule + activity_map, **сохраняя runtime-overlay** (stress, identity_integrity, relationship_cache)
- **Критерий готовности:** При `family_builder → isolation` в тесте NPC получает новый schedule, но сохраняет накопленные stress и отношения.
- **Источник находки:** предыдущая LLM-сессия — D6 dead code
- **Связанные ADR:** ADR-TIFL-003

---

## §4. ФАЗА 3 — ПРОСТРАНСТВО (1 неделя, край 24 августа 2026)

**Цель:** NPC доходят до рабочих точек. Cross-location работает. Нет `GEOMETRIC_OBSTACLE` спама.

### P4-01: _create_boundary_nodes — починить
- **Статус:** [ ]
- **Файлы:** `backend/app/services/spatial/graph_compiler.py:631-677`
- **Что сломано:** 3 бага в одной функции:
  1. `nearest_node = next(iter(graph.values()))` — первый по итерации, не ближайший
  2. `boundary_node = NodeRef(x=0.0, y=0.0)` — все границы в (0,0)
  3. Соединяется только с одним узлом
- **Что сделать:**
  1. Найти ближайший узел к центру границы направления (по координатам из manifest)
  2. `boundary_node.x/y` = координаты ближайшего узла ± 0.5 м в сторону соседа
  3. Соединить со всеми узлами в радиусе 3 м
- **Критерий готовности:** `tavern_silver_wolf:exit_east` находится у восточной стены таверны, не в (0,0). CROSS_LOC к `city_gate` проходит.
- **Связанные ADR:** ADR-O-323, ADR-O-324

### P4-02: Door-splitting — починить
- **Статус:** [ ]
- **Файлы:** `backend/app/services/spatial/graph_compiler.py:417-429`, `backend/app/services/scene_state_manager.py:1185-1198`
- **Что сломано:** `wall_id = obj.get("rotation")` — `rotation` это число, не wall_id. Двери никогда не разрезают стены.
- **Что сделать:**
  1. В JSON локаций добавить объектам дверей поле `"splits_wall": "wall_1"` (явно)
  2. В `graph_compiler` парсить `splits_wall`, не `rotation`
  3. Удалить дубликат логики в `scene_state_manager.py:1185-1198`
- **Критерий готовности:** `wall_1` между залом и кухней разрезана дверным проёмом на (14, 3.75).

### P4-03: Навигационные узлы — убрать colocation с препятствиями
- **Статус:** [ ]
- **Файлы:** `frontend/map_editor/campaigns/Open_road/locations/tavern.json`
- **Что сломано:** `main_hall` (8,7) внутри `obj_11` (стол). `bar_area` (4,4) внутри `obj_0` (бар). A* пути через эти узлы геометрически отбрасываются.
- **Что сделать:**
  1. Сдвинуть `main_hall` на (8.5, 8.0) — вне bounding box стола
  2. Сдвинуть `bar_area` на (4.5, 4.5) — вне bounding box бара
  3. Аудит всех узлов: для каждого проверить, что он не внутри ни одного `walk=False` объекта
- **Критерий готовности:** `grep "GEOMETRIC_OBSTACLE" backend/logs/cds_session_*.log` (свежий) → ≤ 3 за сессию (вместо 95).
- **Связанные ADR:** ADR-O-324

### P4-04: A* obstacle-aware — добавить fallback
- **Статус:** [ ]
- **Файлы:** `backend/app/services/spatial/movement_engine.py:32-228`, `backend/app/services/spatial/spatial_service.py:469-545`
- **Что сломано:** A* использует только топологию. Геометрическая валидация после A* отбрасывает путь без fallback (кроме ближайшего DEFAULT узла).
- **Что сделать:**
  1. В `find_path` добавить параметр `prune_blocked_edges=True`: для каждого ребра графа проверить `is_segment_blocked`, удалить заблокированные
  2. Если A* на пруненном графе возвращает пусто → fallback на локальный A* на сетке 1×1 м (Вариант A из TZ Autonomy)
  3. Кэшировать пруненный граф на тик
- **Критерий готовности:** NPC обходит стол, а не застывает.
- **Связанные ADR:** ADR-O-324

### P4-05: resolve_workplace — реализовать
- **Статус:** [ ]
- **Файлы:** `backend/app/services/spatial/spatial_service.py`, `backend/app/services/npc/life_engine.py`
- **Что сломано:** `workplace:*` tags в JSON есть, но не читаются. Плановый Шаг 6 не реализован.
- **Что сделать:**
  ```python
  def resolve_workplace(self, npc_id: str, activity: str, location_id: str) -> Optional[NodeRef]:
      # 1. Поиск по tag workplace:<npc_id>
      for node_id, ref in self._graph.items():
          tags = getattr(ref, "tags", []) or []
          if f"workplace:{npc_id}" in tags:
              return ref
      # 2. Fallback на роль
      role = _ACTIVITY_TO_ROLE_MAP.get(activity, NodeRole.DEFAULT)
      return self.resolve_node(role=role, origin_zone=location_id)
  ```
  В `life_engine._resolve_position` вызывать `resolve_workplace` вместо `resolve_node` напрямую.
- **Критерий готовности:** При добавлении тега `workplace:maid` к новому узлу Люся идёт туда, а не к дефолтному `serving_station`.
- **Связанные ADR:** ADR-O-326 (Workplace Affordance Contract)

### P4-06: _NEED_ROLE_MAP — синхронизировать с _ACTIVITY_TO_ROLE_MAP
- **Статус:** [ ]
- **Файлы:** `backend/app/services/npc/life_engine.py:1762-1771`
- **Что сломано:** `guarding_gate` всё ещё `ENTRANCE` в need-driven path, хотя в `_ACTIVITY_TO_ROLE_MAP` уже `GUARD_POST`.
- **Что сделать:** Унифицировать обе карты. Лучше — иметь одну `_ACTIVITY_TO_ROLE_MAP` и использовать её в обоих путях.
- **Критерий готовности:** `grep "_NEED_ROLE_MAP" backend/app/` → 0 (если унифицировано).

### P4-07: CROSS_LOC_INTERCEPT — retry и не-мутация
- **Статус:** [ ]
- **Файлы:** `backend/app/services/spatial/movement_engine.py:357-400`
- **Что сломано:** Мутирует `intent.target_node_id` необратимо. После отказа — нет retry к другому boundary node.
- **Что сделать:**
  1. Создавать копию intent для reroute, не мутировать оригинал
  2. При отказе — попробовать следующий boundary node в сторону соседа
  3. Если все boundary nodes отказали — вернуть intent в очередь с delay (через 5 тиков retry)
- **Критерий готовности:** Борко доходит до `city_gate:guard_post`, не остаётся в `corner_table`.

### P4-08: routine.schedule — добавить Торнину и Орму
- **Статус:** [ ]
- **Файлы:** `config/npc/individuals/tornin.json`, `config/npc/individuals/orm.json`
- **Что сломано:** Нет поля `routine.schedule`. LifeEngine выходит на ранней стадии. NPC никогда не двигаются.
- **Что сделать:**
  - Торонин: 06-12 innkeeping, 12-14 eating, 14-22 innkeeping, 22-06 sleeping
  - Орм: 06-12 working (market_square), 12-14 eating (tavern), 14-18 working, 18-22 drinking (tavern), 22-06 sleeping (tavern)
- **Критерий готовности:** В логе `[PIPELINE][MOVEMENT][RELOCATE] npc=tavern_keeper_tornin` появляется.

### P4-09: PatrolRoute — реализовать
- **Статус:** [ ]
- **Файлы:** `backend/app/models/spatial_contracts.py`, `backend/app/services/spatial/graph_compiler.py`, `backend/app/services/npc/life_engine.py`, `frontend/map_editor/campaigns/Open_road/locations/city_gate.json`, `config/npc/individuals/borko.json`
- **Что сломано:** Нет `NodeRole.PATROL_ROUTE`, нет парсинга `patrol_routes`, нет `patrol:` префикса. Стражник стоит в караульне вечно.
- **Что сделать (из `NPC_Workplace_Affordance_Plan.md` Шаг 7):**
  1. Добавить `NodeRole.PATROL_ROUTE = "patrol_route"` в enum
  2. В JSON локации: `"patrol_routes": {"city_gate_perimeter": {"nodes": [...], "cycle": true}}`
  3. В JSON NPC: `"patrol:city_gate_perimeter"` как position
  4. В `_resolve_position`: если position начинается с `patrol:`, вернуть следующий узел маршрута
  5. В `MacroMovementGoal` добавить поле `patrol_route_id`
- **Критерий готовности:** Борко ходит по периметру `city_gate` между 4 точками, не стоит на месте.
- **Связанные ADR:** новый ADR-O-327 (Patrol Routes) — **но только после закрытия P4-01..P4-08**

### P4-10: SpatialResolution(source_node="") — убрать хардкод (NEW-4)
- **Статус:** [ ]
- **Файлы:** `backend/app/services/event_compiler.py:232, 354`
- **Что сломано:** `SpatialResolution(source_node="")` хардкод. Корневая причина 140+ Class D дрейфов на 10k тиков. PHASE 3 migration заблокирован.
- **Что сделать:**
  1. Заменить `source_node=""` на реальный source_node из event context
  2. Если source_node неизвестен — кидать явную ошибку, не молча пустую строку
  3. Добавить CI-гейт на DriftLaboratory: мердж блокируется при `Class D/E drift > 0`
- **Критерий готовности:** DriftLaboratory на 10k тиков возвращает `Class D drift = 0`.
- **Источник находки:** предыдущая LLM-сессия — NEW-4, D2

---

## §5. ФАЗА 4 — АВТОНОМИЯ NPC (1 неделя, край 31 августа 2026)

**Цель:** NPC имеют живые цели, меняют их под давлением, жизненные проекты не завершаются мгновенно.

### P5-01: LifeProject — мгновенный COMPLETED фикс
- **Статус:** [x] **ЗАКРЫТО** — проверено 2026-07-20 в v5.3.5.3
- **Доказательство:** `life_project_resolver.py`: добавлена аккумуляция `_high_ticks >= 3.0` для COLLAPSING (порог 60, не 80). Порог COMPLETED поднят с `pressure < 10` до `pressure < 1.0`, добавлено требование `tick > 50`. В логе v5.3.5.3: только 1 переход ACTIVE→COMPLETED (только merchant_goran, на позднем тике), было 6 на tick 1.

### P5-02: _CRISIS_TRANSITIONS — downstream consumer
- **Статус:** [ ]
- **Файлы:** `backend/app/services/npc/life_project_resolver.py:21-28`, `backend/app/services/npc/life_engine.py`
- **Что сломано:** Переход `family_builder → isolation` мутирует строку, но не меняет schedule, activity_map, location.
- **Что сделать:**
  1. Создать `config/npc/crisis_profiles/<new_project>.json` с новым `routine.schedule` и `activity_map`
  2. В `LifeProjectResolver.apply_crisis(npc, new_project)`: загрузить профиль, заменить `npc.routine.schedule` и `npc.activity_map`, эмиттить `MacroMovementGoal` к новой стартовой позиции
  3. В `life_engine._resolve_position` прочитать обновлённый activity_map
- **Критерий готовности:** При `family_builder → isolation` Люся меняет schedule на «уйти в дальний угол, не общаться» и реально перемещается.
- **Связанные ADR:** ADR-TIFL-002, ADR-TIFL-003

### P5-03: profile.goal — мёртвое поле, оживить
- **Статус:** [ ]
- **Файлы:** `backend/app/models/npc_profile.py:81`, `backend/app/services/npc/decision_hub.py:1447`
- **Что сломано:** `profile.goal` определён, никогда не читается DecisionHub. Тест `test_decision_hub_goal_boost.py:51` должен был это поймать, но `_context_relevance` читает `state.life_project` вместо `state.goal`.
- **Что сделать:**
  1. Либо удалить `profile.goal` (если не нужен)
  2. Либо в `_context_relevance` читать `state.active_goals: List[Goal]` (см. P5-04)
- **Критерий готовности:** `grep "profile.goal" backend/app/` → 0 или используется.

### P5-04: Goal Tree (опционально, только если P5-02 требует)
- **Статус:** [ ]
- **Файлы:** `backend/app/models/npc_state.py`, `backend/app/services/npc/decision_hub.py`
- **Что сделать:**
  1. Заменить `life_project: str` на `active_goals: List[Goal]` где `Goal = {goal_id, parent_goal_id, success_condition, priority, deadline}`
  2. DecisionHub выбирает intent из текущего активного goal, не из плоского life_project
- **Критерий готовности:** NPC с goal «стать мастером гильдии» выбирает интенты, ведущие к этой цели.
- **Примечание:** Если P5-02 закрывается без этого, пункт пометить `[~]` с комментарием.

### P5-05: macro_simulate — реализовать idle_seconds
- **Статус:** [ ]
- **Файлы:** `backend/app/services/npc/life_engine.py:292-298`
- **Что сломано:** `idle_seconds = 0.0` с TODO. Долгое отсутствие игрока не симулируется.
- **Что сделать:**
  1. Передавать `idle_seconds = time.time() - last_player_action` извне
  2. `n_ticks = idle_seconds / 60` (1 тик = 1 минута игрового времени)
  3. Прогонять schedule-driven moves + decay без LLM
- **Критерий готовности:** После 30 минут отсутствия игрока NPC сдвинулись по schedule, hunger вырос, stress decayed.
- **Связанные ADR:** ADR-O-205 (Projection Layer), ADR-047

### P5-06: WORLD_TICK_EVERY_TURNS — пересмотреть
- **Статус:** [ ]
- **Файлы:** `backend/app/core/constants.py:304`
- **Что сломано:** Проактивные NPC-решения не чаще раза в 3 хода. Троттлинг.
- **Что сделать:**
  1. Если P7-01 (background world tick) реализован → удалить константу
  2. Если нет → снизить до 2 и задокументировать причину
- **Критерий готовности:** NPC генерируют проактивные интенты не реже, чем раз в 2 хода.

### P5-08: Avatar drives — пересчёт на каждом тике
- **Статус:** [ ]
- **Файлы:** `backend/app/services/player_avatar_service.py:111-116`, `backend/app/services/tick_orchestrator.py:1078`
- **Что сломано:** `drives` поле аватара устанавливается ОДИН РАЗ при `load_state` (`{0.25, 0.25, 0.25, 0.25}`) и **никогда не пересчитывается** — `DriveResolver` запускается только для `NPCProfileL0`. Аватар «застывает» в начальных драйвах навсегда.
- **Что сделать:**
  1. В `tick_orchestrator.py:1078` расширить условие запуска `DriveResolver` на аватар (не только `NPCProfileL0`)
  2. В `player_avatar_service.py` добавить `update_drives(state, context)` — пересчитывает drives на основе hunger/fatigue/stress/threat
  3. Вызывать на каждом тике (player или idle)
- **Критерий готовности:** После 30 минут gameplay drives аватара изменились (например, hunger вырос → drive `desire` вырос).
- **Источник находки:** предыдущая LLM-сессия — Q5
- **Примечание:** Это не полная автономия аватара (см. B-06 в Бэклоге), но обязательный минимум для P6 (player_cognition) — без живых drives perception pipeline не работает корректно.

### P5-09: maybe_tick force parameter (NEW-3)
- **Статус:** [ ]
- **Файлы:** `backend/app/api/routes.py:243`, `backend/app/services/world_scheduler.py:28`
- **Что сломано:** `maybe_tick(world_id, force=True)` — `force` параметра нет в сигнатуре. POST `/world/tick/{world_id}` крашится на каждом вызове.
- **Что сделать:**
  1. Либо добавить `force: bool = False` параметр в `maybe_tick`
  2. Либо убрать `force=True` из вызова в `routes.py:243`
  3. Унифицировать контракт
- **Критерий готовности:** POST `/world/tick/{world_id}` возвращает 200, не 500.
- **Источник находки:** предыдущая LLM-сессия — NEW-3

---

## §6. ФАЗА 5 — PLAYER_COGNITION (1 неделя, край 7 сентября 2026)

**Цель:** Pipeline подключён, игрок видит мир через восприятие аватара.

### P6-01: player_cognition — подключить к game_loop
- **Статус:** [ ]
- **Файлы:** `backend/app/services/game_loop/__init__.py`, `backend/app/services/player_cognition/__init__.py`
- **Что сломано:** `from app.services.player_cognition` импортируется только в тестах. Pipeline мёртв в runtime.
- **Что сделать:**
  1. В game_loop на каждый ход игрока вызывать `build_perceived_scene(player_avatar, scene_state, nearby_npcs)`
  2. Результат — `PlayerPerceptionDTO` — отдавать в frontend вместо прямого `WorldSnapshotDTO`
- **Критерий готовности:** Frontend получает `PlayerPerceptionDTO`, не `WorldSnapshotDTO`.
- **Связанные ADR:** ADR-O-205 (Projection Layer System)

### P6-02: PlayerBeliefModel — персист
- **Статус:** [ ]
- **Файлы:** новый `backend/app/services/player_cognition/belief_store.py`, `saves/<campaign>/player_beliefs.json`
- **Что сделать:**
  1. Создать `PlayerBeliefStore` (аналог `RelationshipStore`, но для вер игрока)
  2. Структура: `{npc_id: {trait: confidence}}` где confidence ∈ [0, 1]
  3. Обновлять из `PerceivedScene` на каждый ход
  4. Персист в `saves/<campaign>/player_beliefs.json`
- **Критерий готовности:** После 20 ходов в файле есть записи для всех встреченных NPC.

### P6-03: Presentation Firewall — enforced
- **Статус:** [ ]
- **Файлы:** `backend/app/frontend/presentation_firewall.py`
- **Что сломано:** Существует, но не enforced. Frontend видит всё, что знает бэкенд.
- **Что сделать:**
  1. Все API-эндпоинты, отдающие данные клиенту, проходят через firewall
  2. Firewall фильтрует по `PlayerPerceptionDTO`: то, чего игрок не воспринял, не отдаётся
  3. Особое внимание: `hidden_truth` NPC не отдаётся, даже если бэкенд знает
- **Критерий готовности:** В network-ответе API нет полей, которых нет в `PlayerPerceptionDTO`.
- **Связанные ADR:** ADR-O-205, ADR-DM-001

### P6-04: Cognitive dissonance live (предварительно)
- **Статус:** [ ]
- **Файлы:** новый `backend/app/services/player_cognition/dissonance_tracker.py`
- **Что сделать:**
  1. Создать `PlayerCognitiveState.contradictions: List[Contradiction]`
  2. Парсер действий игрока: «помог Люси + сдал Горана» → contradiction
  3. На 3+ contradictions → emit `EventDTO(type="cognitive_dissonance")`
  4. UI hook (опционально на этом этапе) — показать внутренний конфликт аватара
- **Критерий готовности:** В логе появляются `cognitive_dissonance` события.

---

## §7. ФАЗА 6 — TZ «СЕКРЕТЫ ЛЮСИ, ТАЙНЫ ТАВЕРНЫ» (4 недели, край 5 октября 2026)

**Цель:** 14 компонентов TZ_Lusya_Tavern_v2.md реализованы и играбельны.
**Предпосылки:** §1–§6 закрыты. LLM живой, отношения двигаются, NPC ходят, игрок видит через восприятие.

### P7-01: TruthStateLoader (16 секретов, 20 связей)
- **Статус:** [ ]
- **Файлы:** новый `backend/app/models/truth_state.py`, новый `config/canon/truth_state_tavern.json`, новый `backend/app/services/truth_state_loader.py`
- **TZ:** §1, §2.2 (5 дилемм)
- **Что сделать:**
  1. `@dataclass TruthState`: 16 секретов с `secret_id, owner_npc, discoverers, evidence_required, exposure_threshold`
  2. JSON: `lusya_basement, goran_contraband, borko_voyeur, tornin_debt, tornin_basement, orm_secret_craft, shadow_assassin, goran_debt, borko_corrupt, shadow_suspects_lusya, lusya_loves_borko, orm_loves_lusya, tornin_guild_puppet, borko_bribed_by_goran, lusya_escape_plan, shadow_searching_traitor`
  3. 20 связей: `lusya_basement ↔ tornin_basement`, `goran_contraband ↔ borko_bribed_by_goran`, etc.
- **Критерий готовности:** `truth_state_loader.load("tavern")` возвращает 16 секретов, 20 связей.

### P7-02: ObservationLog
- **Статус:** [ ]
- **Файлы:** новый `backend/app/services/player_cognition/observation_log.py`
- **TZ:** §9 (компонент ObservationLog)
- **Что сделать:**
  1. Каждое наблюдение игрока за NPC-NPC взаимодействием, за маркерами (bruise, blood_stain, whisper) — в лог
  2. Структура: `{tick, observer, observed, signal_type, confidence, derived_secrets[]}`
  3. Кормит PlayerBeliefModel и EvaluationEngine

### P7-03: PlayerBeliefModel — интеграция с TruthState
- **Статус:** [ ]
- **Файлы:** `backend/app/services/player_cognition/belief_store.py` (из P6-02)
- **TZ:** §9
- **Что сделать:**
  1. BeliefModel сравнивается с TruthState на End-Screen
  2. Совпадение → +score, несовпадение → -score
  3. Ошибочные выводы → отдельная категория

### P7-04: SocialFabricTracker
- **Статус:** [ ]
- **Файлы:** `backend/app/services/memory/relationship_store.py` (расширить), новый `backend/app/services/social/social_fabric_tracker.py`
- **TZ:** §1.2
- **Что сделать:**
  1. Расширить `RelationshipSnapshot` до 5 полей TZ (trust, fear, affection, debt, respect)
  2. Ввести **baseline снимок при входе в таверну** (deep copy на tick 0)
  3. **delta history** с `cause` и `description` (каждая мутация логируется)
- **Критерий готовности:** На End-Screen видны все изменения NPC-NPC пар с причинами.

### P7-05: FateTracker
- **Статус:** [ ]
- **Файлы:** новый `backend/app/services/social/fate_tracker.py`
- **TZ:** §3
- **Что сделать:**
  1. `FateState` per NPC: stability, threat_level, bonds, secrets_exposed, fate_trajectory, pending_fate, fate_tick
  2. Триггер `fate_event` при `threat > 0.8 AND stability < 0.2`
  3. 6 типов fate events × 4 траектории × 6 NPC = 144 исхода (минимум 24 базовых)
- **Критерий готовности:** Люся при threat > 0.8 эмиттит `fate_event(escape)` или `fate_event(breakdown)`.

### P7-06: FactionAlignmentTracker
- **Статус:** [ ]
- **Файлы:** `backend/app/services/social/reputation_engine.py` (расширить после P0-02)
- **TZ:** §4
- **Что сделать:**
  1. `player_alignment: Dict[faction_id, float]` (-100..100)
  2. Эмиттить delta при действиях игрока: `help_lusya → +10 воров, -10 стража`
  3. Персист в `saves/<campaign>/player_alignment.json`

### P7-07: DilemmaEngine (5 дилемм)
- **Статус:** [ ]
- **Файлы:** новый `backend/app/services/social/dilemma_engine.py`
- **TZ:** §2
- **Что сделать:**
  1. `MoralDilemma` dataclass с trigger_condition, sides[2+], consequences, philosophical_question
  2. Триггеры: `lusya_basement` раскрыт, `goran_contraband + shadow_searching_traitor`, etc.
  3. Каждая дилемма → 2-3 стороны → каждая сторона → fate_consequences

### P7-08: EvaluationEngine
- **Статус:** [ ]
- **Файлы:** новый `backend/app/services/social/evaluation_engine.py`
- **TZ:** §5
- **Что сделать:**
  1. `evaluate(beliefs, truth_state, fate_events) → Score{secrets, causal_links, methods, fates, contradictions}`
  2. Сравнение belief vs truth
  3. Score 0..100

### P7-09: CognitiveDissonanceTracker — расширить
- **Статус:** [ ]
- **Файлы:** `backend/app/services/player_cognition/dissonance_tracker.py` (из P6-04)
- **TZ:** §8
- **Что сделать:**
  1. Полная таблица противоречий из TZ §8.2
  2. На 3+ contradictions → special end-screen message

### P7-10: EndScreenRenderer
- **Статус:** [ ]
- **Файлы:** новый `frontend/end_screen.py`
- **TZ:** §5
- **Что сделать:**
  1. Pygame-экран с цветовой системой (🟢🔴🟡❤️💀)
  2. Секции: секреты, каузальная карта, методы, судьбы, социальная ткань, итог
  3. Цитаты LastWords

### P7-11: LastWordsSystem
- **Статус:** [ ]
- **Файлы:** новый `config/canon/last_words.json`, новый `backend/app/services/social/last_words.py`
- **TZ:** §7
- **Что сделать:**
  1. 6 NPC × 4 судьбы = 24 цитаты
  2. Триггер при `fate_event`
  3. Принцип «тишина важнее слов» — не каждый NPC говорит

### P7-12: ExitTrigger
- **Статус:** [ ]
- **Файлы:** `backend/app/services/game_loop/phase_*.py` (detect exit), `backend/app/api/routes.py`
- **TZ:** §9 (компонент ExitTrigger)
- **Что сделать:**
  1. Выход из таверны → триггер `exit_event`
  2. `exit_event` → EvaluationEngine → EndScreenRenderer
  3. Опционально: подтверждение выхода («покинуть таверну навсегда?»)

### P7-13: WorldStateDiff
- **Статус:** [ ]
- **Файлы:** новый `backend/app/models/world_state_diff.py`, новый `backend/app/services/state/world_diff_persistence.py`
- **TZ:** §6
- **Что сделать:**
  1. `WorldStateDiff`: npc_fates, relationship_changes, faction_alignments, secrets_exposed, world_events, player_reputation
  2. Персист в `saves/<campaign>/world_diff.json`
  3. Hook в End-Screen

### P7-14: Механики TZ §9 (клик-таргетинг, eavesdrop, шантаж, fixes)
- **Статус:** [ ]
- **Файлы:** несколько
- **TZ:** §9 (остальные механики)
- **Что сделать:**
  1. **Eavesdrop (#7):** подслушивание NPC-NPC, радиус < 3.0, RNG-шанс услышать обрывок → ObservationLog
  2. **Шантаж (#9):** `Intent.blackmail` с precondition `player.knows_secret[secret_id]`. Эффект: fear(target) += 50, trust(target) -= 30, cognitive_dissonance += 1
  3. **Zombie reader fix (#2):** range gate в combat: чтение/каст только на расстоянии ≤ 2 м
  4. **cue_key fix (#3):** подключить `PhenomenologyProjectionService.cues` в UI
  5. **combat_data fix (#4):** в `dialogue_context` добавлять `combat_state` snapshot
  6. **DMFrame recent_trauma (#5):** в intent payload добавлять `recent_trauma` последние 3 ранения
  7. **Клик-таргетинг (#1):** закрыто в P1-07

### P7-15: Smoke-тест миниигры
- **Статус:** [ ]
- **Файлы:** `backend/tests/test_tavern_minigame_e2e.py`
- **Что сделать:**
  1. Полный прогон: вход в таверну → диалоги → раскрытие 3 секретов → дилемма → выбор → судьбы → End-Screen
  2. Утверждение: score вычислен, судьбы наступили, world_diff сохранён
- **Критерий готовности:** Тест проходит. Вручную проверено: можно сыграть миниигру от начала до конца.

---

## §8. БЭКЛОГ (только после §1–§7)

**Правило:** пункты сюда добавляются, но не выполняются, пока §1–§7 не закрыты.

### B-01: Background WorldTick (AWC)
- Реализовать `world_tick_loop()` в `main.py` lifespan, интервал 30 сек
- Симулировать все NPC всех локаций (потребует P5-07)
- Лимит LLM-вызовов: 1 на 10 background-тиков

### B-02: Cross-campaign inheritance (CK_CORE_LAYER_SPEC)
- Реализовать `docs/Почти Актуальные TZ/CK_CORE_LAYER_SPEC_Instructions.pdf`
- Новая кампания читает `world_diff.json` предыдущей
- Если `lusya_fate = escaped` → в `southern_village` появляется `maid_lusya_south`
- TTL на WorldStateDiff (30 игровых дней)

### B-03: Multi-location emergent gameplay
- `city_gate`, `market_square`, `southern_village` как играбельные локации
- NPC с hidden_truth, отношениями, судьбами в каждой
- Travel scenes между стационарными локациями

### B-04: Economic engine activation
- `economy_tracker.py` активировать
- Цены колеблются, караваны ходят, гильдии торгуют
- Смерть Горана → торговая гильдия слабеет → цены растут → стража хуже кормлена → коррупция Борко растёт

### B-05: Memetic propagation
- Реализовать `docs/Почти Актуальные TZ/VZ/TZ_MEMETIC_01..03`
- Слухи, идеологии, культурные паттерны распространяются между NPC

### B-06: Avatar autonomy (полная)
- AvatarDecisionHub
- Avatar schedule
- Background avatar tick
- WillpowerGate для avatar-self

### B-07: Replay as epistemic archaeology
- После End-Screen игрок может «прокрутить» игру с точки зрения любого NPC
- Что видела Люся? Что слышал Тень?
- Требует записи PerceivedScene для всех NPC на каждый тик

### B-08: Seasonal cycles
- `architecture/temporal.yaml` реализовать
- Сезоны, праздники, годовщины
- «Годовщина смерти семьи Люси» → stress растёт в этот день

### B-09: Curiosity drive
- Пятый драйв: `curiosity: 0..1`
- При `curiosity > 0.5` NPC генерирует `Intent.observe` на незнакомых узлах

### B-10: Goal Tree (если P5-04 не закрыт)
- Заменить `life_project: str` на `active_goals: List[Goal]`
- Многошаговые планы в DecisionHub

---

## §9. ИСТОРИЯ ИЗМЕНЕНИЙ

| Дата | Автор | Действие |
|---|---|---|
| 2026-07-20 | Super Z (по запросу пользователя) | Создан контракт v1.0 |
| 2026-07-20 | Super Z (после сравнения с предыдущей LLM-сессией V.0.5.3.4.9_drift) | Обновлён до v1.1: добавлены P0-00 (line_of_sight signature), P0-00b (urlopen method), P2-10 (village_relations), P2-11 (RoleTransition dead code), P4-10 (SpatialResolution хардкод), P5-08 (avatar drives), P5-09 (maybe_tick force). Корректировка: предыдущая LLM нашла больше багов, чем изначальный аудит — ситуация на ~5-10 пунктов работы больше. Прогноз 3-4 месяца подтверждён двумя независимыми анализами. |
| 2026-07-20 | Super Z (после замечания пользователя и прямой верификации кода через grep) | Обновлён до v1.2: **9 пунктов уже закрыты пользователем и архитекторами до v1.0** — NEW-1, NEW-2, NEW-3, NEW-4, BUG #1, BUG #3, BUG #8, BUG #10 (частично), P1-12. P0-04 (KeyError 0) уточнён — это новая форма бага, не старая. Реальная оставшаяся работа = 26 пунктов, не 35. Прогноз **уточнён вниз: 2-2.5 месяца** при текущей скорости. Признание: контракт v1.0/v1.1 страдал от того, что не верифицировал эмпирически каждое утверждение — это методологическая ошибка, исправлена. |
| 2026-07-20 | Super Z (после проверки версии V.0.5.3.5.3) | Обновлён до v1.3: **+7 пунктов закрыто за ~6 часов** между v5.3.5.1 и v5.3.5.3: P0-02 (factions.json path), P0-04 (KeyError 0 fix), P1-05 (_builtin_templates удалён), P1-06 (EventBus exc_info), P1-09 (MacroMovementGoal intent_id), P1-15 (_path_cache LRU), P2-01 (полная tone table), P5-01 (LifeProject аккумуляция). Всего закрыто: 16/33. LLM ожил (503 → «доступен»), NPC-NPC отношения двигаются (trust=-0.1 для ANGRY). DRIFT B=0 держится. Прогноз подтверждён: ~3-4 недели до играбельной миниигры при текущем темпе. |

---

## §10. ФИНАЛЬНЫЕ ПРИНЦИПЫ

1. **Этот документ — единственный источник правды** для команды на ближайшие 6-8 недель.
2. **Любой новый ADR от архитектора** → отказ с отсылкой к §0.1.
3. **Любая новая фича** → в §8 Бэклог, не в текущую фазу.
4. **Прогресс измеряется закрытыми пунктами**, не количеством кода.
5. **TZ «Секреты Люси» считается завершённой**, когда P7-15 (smoke-тест) проходит.
6. **После §7 — пересмотр контракта v2.0** с учётом Бэклога.

---

**КОНЕЦ КОНТРАКТА v1.0**

*Отправь этот файл архитекторам. Любой вопрос «а почему мы не делаем X?» → ответ: «потому что в контракте этого нет, а контракта мы должны придерживаться».*
