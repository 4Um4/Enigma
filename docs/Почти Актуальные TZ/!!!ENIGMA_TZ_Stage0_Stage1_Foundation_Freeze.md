# ENIGMA — Техническое Задание для LLM-архитектора

**Документ:** Foundation Freeze (Stage 0) + Causal Spine (Stage 1)
**Версия исходника:** Enigma V.0.5.3.8.3 (version.txt: `0.5.3.8.3`)
**Статус:** Исполняемый контракт. Нарушение любого пункта = архитектурный баг, а не стилистическое отклонение.
**Аудитория:** LLM-архитектор (не человек). Документ машинно-читаем: каждое требование сформулировано как проверяемый предикат, каждая ссылка на код — в форме `file:line`.

---

## §0. Pre-amble — Контекст для LLM-архитектора

### 0.1 Назначение и авторитет документа

Этот документ — исполняемый контракт между заказчиком и LLM-архитектором. Ключевые слова **MUST / MUST NOT / SHALL / SHALL NOT / REQUIRED / FORBIDDEN / SHOULD / SHOULD NOT** используются в смысле RFC 2119.

**Контракт чтения.** LLM-архитектор перед началом любой работы обязан:

1. Прочитать `docs/АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md` целиком (747 строк).
2. Прочитать `architecture/state.yaml` и `architecture/pipeline.yaml` целиком.
3. Грепнуть `git log --oneline | head -50` для понимания недавнего дрейфа.
4. Сверить каждый планируемый шаг с §1 (Stop-list) — если шаг противоречит хотя бы одному FORBIDDEN, шаг запрещён.

**Контракт записи.** Каждое изменение кода в Stage 0 или Stage 1 MUST сопровождаться:

- Ссылкой на пункт этого ТЗ (`§N.M`).
- Ссылкой на ADR (если применимо).
- Тестом, проверяющим инвариант из `§N.DoD`.

### 0.2 Нотация и формат ссылок

| Формат | Значение |
|---|---|
| `path/to/file.py:LN` | Одна строка |
| `path/to/file.py:LN-LM` | Диапазон строк |
| `path/to/file.py:LN,LP,LQ` | Несколько конкретных строк |
| `Устав §X.Y` | Ссылка на `docs/АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md` |
| `ADR-NNN` | Ссылка на `docs/audits/ADR-NNN_*.md` |
| `§N.M` | Ссылка на раздел этого ТЗ |

Severity-теги: `[CRITICAL]` (нарушение ломает compile/runtime/каузальность), `[HIGH]` (нарушение накапливает долг), `[MEDIUM]` (стилистическое отклонение).

BDD-сценарии оформлены как `GIVEN / WHEN / THEN` с машино-проверяемыми предикатами.

### 0.3 Manifest критических нарушений

Обнаружено 4 нарушения, каждое блокирует Stage 1. До устранения **всех четырёх** любое наращивание психики увеличивает стоимость будущей переделки экспоненциально (см. §0.5).

#### Нарушение M1. Compile error: отсутствие модуля `action_semantic_resolver` `[CRITICAL]`

**Лог:** `backend/logs/error.log` (timestamp `2026-08-17 21:31:11`).

```text
File "...backend\app\services\game_loop\__init__.py", line 1869, in _execute_dm_and_intent_resolution
    _target_pos = scene_state.get("npc_positions", {}).get(_target_id, {}).get("position", "")
ModuleNotFoundError: No module named 'app.services.player_cognition.action_semantic_resolver'
```

**Файл:** `backend/app/services/game_loop/__init__.py:1869`.
**Симптом:** Любое действие игрока через `api/routes.py:797 game_action` → `game_loop.run_turn` → `_run_pipeline` (`__init__.py:2155`) → `_init_pipeline_context` → `_execute_dm_and_intent_resolution` (`__init__.py:1869`) падает с `ModuleNotFoundError`.
**Реальность:** В каталоге `backend/app/services/player_cognition/` присутствуют 16 модулей (`action_consequence_compiler.py`, `attention_layer.py`, `cognitive_dissonance_tracker.py`, `cognitive_distortion.py`, `interpretation_layer.py`, `legacy_bridge.py`, `memory_layer.py`, `npc_confession_parser.py`, `observation_log.py`, `perception_layer.py`, `pipeline.py`, `player_belief_model.py`, `recognition_layer.py`, `spatial_layer.py`, `types.py`, `uncertainty_layer.py`). Файла `action_semantic_resolver.py` нет. Это либо забытый рефакторинг (модуль переименован), либо несозданная зависимость.
**Запрет:** Stage 0 не считается завершённым, пока этот import не резолвится.

#### Нарушение M2. Двойная истина состояния (State Double Truth) `[CRITICAL]`

**Архитектурный YAML сам признаёт это:** `architecture/state.yaml:72-78`:

```yaml
- source: NPCLoader
  target: NPCState
  rule: "REQUIRED: _apply_runtime_overlay must include affective_load, emotion,
         emotion_delta, body_state, perceptual_kernel, narrative_cache in whitelist
         (Invariant 1, ADR-118)"
  condition: "Without these keys in _RUNTIME_TOP_LEVEL_KEYS, computed state is
              overwritten by static config on every disk read → DOUBLE TRUTH"
  code_ref: "npc/npc_loader.py:_RUNTIME_TOP_LEVEL_KEYS"
  adr_ref: "ADR-118"
  severity: CRITICAL
```

**Механизм двойной истины:**

- Истина #1: `tick_ctx.all_npcs_raw` — legacy dict (см. `services/game_loop/phase_2_world_tick.py:43, 122, 143, 176`).
- Истина #2: `NPCState` dataclass (`models/npc_state.py:564`).
- Синхронизация: `load_l2_state_from_runtime_dict(_n)` (dict → dataclass) и `NPCState.write_to_legacy(state, _wt_npc_raw)` (dataclass → dict) — `phase_2_world_tick.py:54, 129, 138, 153, 160`.
- Заплатка ADR-118: whitelist `_RUNTIME_TOP_LEVEL_KEYS` (`services/npc/npc_loader.py:280-311`) — это список полей, которые «должны пережить merge». Каждое новое runtime-поле, не добавленное в whitelist, **молча теряется** при следующем чтении с диска.

**Whitelist (`npc_loader.py:280-311`)** — сам по себе симптом болезни:

```python
_RUNTIME_TOP_LEVEL_KEYS = frozenset(
    {
        "social_stats", "location", "location_id", "position", "hp", "max_hp",
        "current_role", "role_history", "conditions", "wounds",
        "threat_accumulator", "posture", "temporary_drives", "causal_ledger",
        "affective_memory", "social_input_ema",
        # ADR-117: Вычисленные runtime-поля, которые должны переживать merge
        # Без этого affective_load=0.0 и emotion=MISSING после каждого чтения с диска
        "affective_load", "emotion", "emotion_delta",
        # ADR-101, ADR-109: Физиология и восприятие — не должны сбрасываться при merge
        "body_state", "perceptual_kernel",
        # L2 память — без этого narrative_cache теряется
        "narrative_cache",
        # ETKE-IK: Контур непрерывного движения
        "drive_vector",
    }
)
```

**Комментарий в коде признаёт проблему:** `npc_state.py:791-793`:

```python
# P1 ARCH: relationship_cache — эфемерный read-cache. НЕ сериализуется.
# SSOT = RelationshipStore. Персистенция кэша = DOUBLE TRUTH.
```

**Запрет:** Расширение `_RUNTIME_TOP_LEVEL_KEYS` как способ «починить потерю поля» — это закрепление болезни, а не лечение. Stage 0 MUST упразднить whitelist вместе с самим паттерном dict↔dataclass roundtrip в runtime.

#### Нарушение M3. Параллельный WorldTick-путь `[CRITICAL]`

**Файл:** `backend/app/services/game_loop/phase_2_world_tick.py` (271 строка).
**Симптом:** Функция `tick_world_proactive()` мутирует `tick_ctx.all_npcs_raw` (legacy dict) напрямую через `NPCState.write_to_legacy()` — в обход канонического пути `StateApplicator.apply_deltas_and_commit → PersistencePort.atomic_commit → SQLite`.

**Конкретные строки-нарушители:**

```python
# phase_2_world_tick.py:111-161 (excerpt)
_wt_applicator = StateApplicator(relationship_store=memory_relationship_store)

# 1. Recovery для ВСЕХ major NPC
for _pid, _, _ in _proactive_npc_data:
    _wt_npc_raw = next(... for _n in tick_ctx.all_npcs_raw ...)
    if not _wt_npc_raw:
        continue
    _wt_state = load_l2_state_from_runtime_dict(_wt_npc_raw)         # dict → NPCState
    _wt_state = _wt_applicator.apply_tick_recovery(_wt_state, ...)   # mutate NPCState
    NPCState.write_to_legacy(_wt_state, _wt_npc_raw)                 # NPCState → dict  ← ПАРАЛЛЕЛЬНЫЙ WRITE
    tick_ctx.wt_dirty = True

# 2. Deltas от конкретных proactive решений
for _pd in _tick_result.decisions:
    _wt_npc_raw = next(... for _n in tick_ctx.all_npcs_raw ...)
    _wt_state = load_l2_state_from_runtime_dict(_wt_npc_raw)
    _wt_state = _wt_applicator.apply_deltas_only(_wt_state, _pd.deltas)
    NPCState.write_to_legacy(_wt_state, _wt_npc_raw)                 # ← ПАРАЛЛЕЛЬНЫЙ WRITE
    tick_ctx.wt_dirty = True
```

**Дополнительно — прямая мутация avatar'а (`phase_2_world_tick.py:243-248`):**

```python
# S150 FIX: Если в сделке участвует игрок, обновляем его avatar_state напрямую
_avatar = getattr(shared_context, "avatar_state", None)
if _avatar and _avatar.body_state:
    for _delta in _wt_economy_deltas:
        if _delta.npc_id == "player" and isinstance(_delta.payload, EconomicPayload):
            _money_delta = float(_delta.payload.money_delta or 0.0)
            _avatar.body_state["money"] = float(_avatar.body_state.get("money", 0.0)) + _money_delta
```

Это прямой обход `StateApplicator`: `_delta` уже проходит через `apply_batch` (строка 234), но player-счет пишется отдельной inline-мутацией.

**Архитектурное нарушение:** `architecture/pipeline.yaml` объявляет `StateApplicator → DeltaBuffer → PersistencePort` единственным write-pipeline. `phase_2_world_tick.py` — отдельный write-pipeline, замыкающийся на `tick_ctx.wt_dirty` и сохраняемый через `_save_npcs()` в конце тика. Это и есть «параллельный WorldTick-путь», упомянутый заказчиком.

**Запрет:** `phase_2_world_tick.py` MUST быть упразднён (или полностью переписан как publisher `List[EventDTO]` в EventBus — см. `Устав §2.1.2`). Любая новая система, копирующая его паттерн, запрещена.

#### Нарушение M4. Двойная истина убеждений (Belief Multi-Writer) `[CRITICAL]`

**Архитектурный контракт:** `models/npc_state.py:614-617`:

```python
# R7: Эпистемический слой — что NPC считает истиной о мире.
# WRITE: только BeliefTransitionEngine.
# READ: DecisionHub.compute() через beliefs.as_modifiers().
beliefs: "BeliefState" = field(default_factory=BeliefState)
```

**Декларация владельца:** `services/npc/belief_transition_engine.py:7` (docstring):

```python
"""Единственный владелец записи в NPCState.beliefs."""
```

**Реальность:** Греп `\.beliefs\.` по `backend/app/services/` показывает, что `state.beliefs.update()` и схожие writers присутствуют в **минимум 11 файлах**:

| Файл | Строка | Операция |
|---|---|---|
| `services/npc/belief_transition_engine.py` | 153, 190 | `state.beliefs.update(...)` — единственный легальный |
| `services/player_cognition/action_consequence_compiler.py` | 66, 104 | `self._beliefs.update_from_evidence(obs, ev)` |
| `services/player_cognition/npc_confession_parser.py` | 108 | `self._beliefs.update_from_evidence(obs, ev)` |
| `services/execution/dialogue_executor.py` | (multiple) | пишет в beliefs |
| `services/social/mvp_tavern_controller.py` | (multiple) | пишет в beliefs |
| `services/integration/world_snapshot_builder.py` | (multiple) | читает/пишет beliefs |
| `services/phases/integration.py` | (multiple) | пишет в beliefs |
| `services/phases/affective.py` | (multiple) | пишет в beliefs |
| `services/npc/npc_tick_pipeline.py` | (multiple) | пишет в beliefs |
| `services/tick_orchestrator.py` | (multiple) | пишет в beliefs |
| `api/routes.py` | (multiple) | пишет в beliefs |

**Архитектурный нюанс (требует верификации LLM-архитектором):** В `action_consequence_compiler.py` и `npc_confession_parser.py` объект `self._beliefs` может оказаться не `NPCState.beliefs` (убеждения NPC), а `PlayerBeliefModel` (убеждения игрока о NPC) — это другой SSOT. Stage 0 MUST разделить `BeliefState` (NPC) от `PlayerBeliefModel` (player) и для каждого зафиксировать ровно одного писателя.

**Запрет:** Любой writer в `NPCState.beliefs` вне `BeliefTransitionEngine.commit(evidence)` запрещён.

### 0.4 Сводка Устава (§ENIGMA-001..§006, §S72)

Устав `docs/АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md` уже содержит догмы, которые в текущем коде систематически нарушаются. LLM-архитектор не имеет права вводить новые ADR, противоречащие Уставу, без явного ADR-обоснования.

| § | Название | Что требует | Где нарушается сейчас |
|---|---|---|---|
| §001 | Приоритет причинной глубости | Изменение валидно, если увеличивает количество/длину причинных структур (memory, trust, debt, belief, etc.) | `_RUNTIME_TOP_LEVEL_KEYS` whitelist — добавляет поле без создания причинной структуры |
| §002 | Two-Domain Rule | Новый примитив вводится только после 2 независимых багов, доказывающих общую онтологическую проблему | `phase_2_world_tick.py` вводит `wt_dirty`-path без обоснования |
| §003 | Epistemic Projection | `UNKNOWN ≠ NEUTRAL(0.0)`. Отсутствие данных = отсутствие валидной проекции в графе памяти агента | `npc_loader.py:280` whitelist забывает поле → оно становится 0.0/MISSING вместо UNKNOWN |
| §004 | Epistemic Damping | Vacuum = локальный разрыв вывода, не глобальное свойство мира. Запрещена конвертация Vacuum в аккумуляторы состояния | `affective_load=0.0` после disk-read (ADR-117 признание в комментарии) |
| §005 | Referential Closure | `Intent` — чистая проекция, никто не может дополнить его после создания | `phase_2_world_tick.py` модифицирует NPC state вне Intent-pipeline |
| §006 | Intent Completeness | Если `target_id` отсутствует, это "Unresolved Reference", а не "нет цели" | `_execute_dm_and_intent_resolution` (`game_loop/__init__.py:1869`) допускает пустой `_target_id` |
| §S72 | Relativistic Perception | Движок производит только сырые сигналы; смысл рождается в взаимодействии личности и сигнала | `dominant_emotion_hint` из движка (запрещено п.5 §S72) — проверить presence |
| §2.1.1 | EventDTO-only | `EventBus.publish()` принимает только `EventDTO` | `phase_2_world_tick.py` пишет напрямую в `tick_ctx.all_npcs_raw` без публикации EventDTO |
| §2.1.2 | WorldTickEngine EventDTO-only | `WorldTickEngine` возвращает `List[EventDTO]`, не `List[dict]` | `phase_2_world_tick.py:95-104` получает `compute_proactive_decisions` — проверить возвращаемый тип |
| §4.2.1 | atomic_commit required | Все saves — через `atomic_commit`. Three separate JSON files = desync bug | `_save_npcs()` legacy path (вызывается из `phase_2_world_tick.py` через `wt_dirty`) |
| §4.2.2 | JSON as runtime truth FORBIDDEN | JSON = fallback/snapshot, SQLite = primary | Проверить runtime-call `JsonPersistenceAdapter` (см. §1.3) |

### 0.5 Аргумент стоимости откладывания (экспоненциальный долг)

LLM-архитектору важно понимать, **почему** Stage 0 нельзя отложить ради новой фичи. Формула:

```
Cost(fix_after_N_features_added) ≈ Cost(fix_now) × 2^N
```

**Механизмы экспоненциального роста долга:**

1. **Whitelist-налог.** Каждое новое runtime-поле в `NPCState`, добавленное до упразднения `_RUNTIME_TOP_LEVEL_KEYS`, **обязано** быть добавлено в whitelist (`npc_loader.py:280-311`) — иначе оно молча обнуляется при disk-read. Если в Stage 0 добавлены 20 новых полей психики (эмоции, self-model, мотивация), упразднение whitelist'а превратится в миграцию 20 полей с риском регрессии на каждом.

2. **Multi-writer beliefs-налог.** Каждая новая belief-источника (например, «NPC выводит убеждение о смене ролей», «NPC выводит убеждение о фракции») добавляет нового writer'а в `state.beliefs`. Если до Stage 0 добавить 5 новых источников, миграция на `BeliefTransitionEngine.commit(evidence)` превратится в 5+11 = 16 callsites вместо текущих 11.

3. **Параллельный-path клонирование.** `phase_2_world_tick.py` — это работающий пример «как мимо канонического pipeline писать state». Любая новая система, читающая его как референс, скопирует bypass-паттерн. После 2-3 копий Stage 0 превратится в考古发掘.

4. **Compile error-блокатор.** Пока `action_semantic_resolver` не резолвится, **любое** действие игрока падает. Любая новая фича, тестируемая через player action, не может быть валидирована.

**Вывод.** Stage 0 — это НЕ рефакторинг ради чистоты. Это foreclosure — закрытие закладки, которая удорожает каждый следующий шаг. Откладывание Stage 0 ради новой фичи равносильно покупке фичи в кредит под 100% годущих.

---

## §1. STAGE 0 — Architectural Foundation Freeze

### 1.1 Цель и критерий выхода стадии

**Цель.** Сделать так, чтобы больше не было двух истин. А именно:

1. Зафиксировать единственный `NPCState` runtime.
2. Legacy JSON оставить только как persistence representation (serde только в момент save/load).
3. Разделить слои: L0 Profile / L1 Identity / L2 State / R4 Context.
4. Убрать дублирующие writers.
5. Назначить ровно одного SSOT-писателя для каждого домена: epistemic, social, economic.
6. Запретить новым системам добавлять поля прямо в `NPCState` без domain ownership.
7. Убрать параллельный WorldTick-путь.
8. Закрыть compile error M1.

**Что Stage 0 НЕ делает (явный запрет):**

- НЕ писать политику секса.
- НЕ писать культуру.
- НЕ писать новые эмоции (расширение `EmotionTag`).
- НЕ писать self-model.
- НЕ писать сложную мотивацию поверх существующей.
- НЕ вводить новые фундаментальные примитивы без §ENIGMA-002 (Two-Domain Rule).

**Критерий выхода (булев предикат):**

```
∀ field F ∈ NPCState: ∃! file S : S является единственным writer'ом для F.
```

Иными словами: на вопрос «где лежит единственная истина этого свойства?» можно ответить **одним файлом/сервисом**. Если ответ содержит слово «ну вообще есть ещё вот этот cache...» или «а ещё мы пишем его вот тут для скорости...» — Stage 0 не закончен.

### 1.2 Stop-list Stage 0 (явные запреты)

Сводный список FORBIDDEN-паттернов для Stage 0. Каждый паттерн помечен ссылкой на Устав/ADR и примером нарушения в текущем коде.

| # | Паттерн | Запрет | Нарушение сейчас |
|---|---|---|---|
| F1 | Прямой write в `NPCState` вне `StateApplicator` | FORBIDDEN (Устав §1.3, `npc_state.py:5-9`) | `phase_2_world_tick.py:138, 160` — `NPCState.write_to_legacy` вызывается вне `StateApplicator.apply_*` |
| F2 | JSON как runtime truth | FORBIDDEN (Устав §4.2.2, `architecture/state.yaml:53-58`) | Проверить: `JsonPersistenceAdapter` runtime-call-sites |
| F3 | Новое поле в `NPCState` без domain ownership | FORBIDDEN (Устав §1.3) | Любое расширение `_RUNTIME_TOP_LEVEL_KEYS` |
| F4 | Параллельный tick-path мимо `TickOrchestrator` | FORBIDDEN (Устав §3) | `phase_2_world_tick.py` целиком |
| F5 | Multi-writer beliefs вне `BeliefTransitionEngine` | FORBIDDEN (`npc_state.py:614-617`) | 11+ файлов, см. §0.3 M4 |
| F6 | Персистенция эфемерных кэшей (relationship_cache, narrative_cache) | FORBIDDEN (`npc_state.py:791-793`, P1 ARCH FIX) | Проверить: сериализация `relationship_cache` в `write_to_legacy` (должна отсутствовать) |
| F7 | Прямая мутация `scene_state` мимо `SceneChange`/`ThickSceneChange` | FORBIDDEN (ADR-TZ04-5, `architecture/state.yaml:93-102`) | `services/scene_state_manager.py:apply_change` (6 мутаций, см. constraint в `state.yaml:86-92`) |
| F8 | Прямая мутация `_avatar.body_state` мимо `StateApplicator` | FORBIDDEN | `phase_2_world_tick.py:243-248` — `_avatar.body_state["money"] = ...` |
| F9 | Bypass `atomic_commit` (три отдельных JSON файла) | FORBIDDEN (Устав §4.2.1) | `_save_npcs()` legacy path |
| F10 | Расширение `_RUNTIME_TOP_LEVEL_KEYS` как fix двойной истины | FORBIDDEN (этот документ §0.3 M2) | Текущее состояние: `npc_loader.py:280-311` |

### 1.3 Task 0.1 — Исправить compile error `action_semantic_resolver` `[CRITICAL]`

**BDD-сценарий:**

```text
GIVEN файл backend/app/services/game_loop/__init__.py:1869 содержит импорт
       app.services.player_cognition.action_semantic_resolver
  AND каталог backend/app/services/player_cognition/ не содержит action_semantic_resolver.py
  AND лог backend/logs/error.log содержит ModuleNotFoundError для этого модуля

WHEN игрок вызывает любое действие через api/routes.py:797 game_action

THEN pipeline падает в _execute_dm_and_intent_resolution
  AND _target_pos не вычисляется
  AND исключение ModuleNotFoundError пробрасывается до api/routes.py
```

**Контракт решения.** LLM-архитектор SHALL выбрать одну из двух веток после грепа реальных callsites:

**Ветка A (модуль был переименован).** Если `action_semantic_resolver` использовался как класс/функция, и его функциональность уже реализована под другим именем в `services/player_cognition/` (например, в `interpretation_layer.py` или `legacy_bridge.py`):

1. `grep -rn "ActionSemanticResolver\|action_semantic_resolver" backend/app/ --include="*.py"` — найти все callsites.
2. Определить, какой существующий модуль покрывает контракт `ActionSemanticResolver` (например, mapping action → semantic consequence).
3. Обновить импорт в `game_loop/__init__.py:1869` на корректный модуль.
4. Запустить `pytest backend/tests/test_game_loop_pipeline.py backend/tests/test_player_cognition_pipeline.py` — должны проходить.

**Ветка B (модуль должен быть создан).** Если `ActionSemanticResolver` — это новый контракт, не реализованный нигде:

1. Создать `services/player_cognition/action_semantic_resolver.py` с явным контрактом (docstring + type hints).
2. Контракт: `ActionSemanticResolver.resolve(intent: IntentDTO, scene_state: dict) -> SemanticConsequence` (точная сигнатура — LLM-архитектор выведет из callsite в `__init__.py:1869`).
3. Тест: `backend/tests/test_player_cognition_pipeline.py` должен получить `test_action_semantic_resolver.py`.
4. Включить в `services/player_cognition/__init__.py` export.

**Критерий выхода:**

- `python -c "import app.services.player_cognition.action_semantic_resolver"` — `exit code 0`.
- `pytest backend/tests/test_game_loop_pipeline.py::test_run_turn_e2e` — PASS.
- В `backend/logs/error.log` нет `ModuleNotFoundError` после прогона 100 player actions.

### 1.4 Task 0.2 — Зафиксировать единственный `NPCState` runtime `[CRITICAL]`

**BDD-сценарий:**

```text
GIVEN services/npc/npc_loader.py:280-311 содержит _RUNTIME_TOP_LEVEL_KEYS whitelist
  AND NPCState.write_to_legacy (models/npc_state.py:796) мутирует npc_dict
  AND load_l2_state_from_runtime_dict (npc_loader.py) строит NPCState из npc_dict
  AND эти две функции вызываются в цикле каждый тик (phase_2_world_tick.py:129-138, 153-160)

WHEN любая система пишет новое runtime-поле F в NPCState
  AND F не добавлено в _RUNTIME_TOP_LEVEL_KEYS

THEN при следующем disk-read → merge → NPCState.from_legacy
  поле F обнуляется (affective_load=0.0, emotion=MISSING, narrative_cache=())
  AND §ENIGMA-003 нарушено: UNKNOWN конвертировано в NEUTRAL(0.0)
```

**Контракт решения.**

1. **Упразднить `_RUNTIME_TOP_LEVEL_KEYS`** (`npc_loader.py:280-311`). Целевое состояние: `load_l2_state_from_runtime_dict` и `_apply_runtime_overlay` либо удалены, либо переведены в разряд «serialization-only» — вызываются только в момент `load_npcs_merged()` (холодный старт) и `atomic_commit` (сохранение).

2. **Зафиксировать `NPCState` как единственный runtime truth.** Все runtime-чтения идут через `NPCStateRepository.get(npc_id) -> NPCState` (новый или усиленный интерфейс; LLM-архитектор проверяет, существует ли он, иначе создаёт в `services/npc/state_repository.py`).

3. **Упразднить `NPCState.write_to_legacy`** как runtime-операцию. Метод либо удаляется, либо переименовывается в `NPCState.to_persistence_dict()` и используется **только** внутри `SqlitePersistenceAdapter.atomic_commit`.

4. **Мигрировать callsites** (после `grep -rn "NPCState.write_to_legacy\|load_l2_state_from_runtime_dict" backend/app/ --include="*.py"`):
   - `phase_2_world_tick.py:129, 138, 153, 160` — упразднить (см. Task 0.10).
   - `services/game_loop/__init__.py` (найти callsites) — мигрировать на `StateApplicator.apply_deltas_and_commit`.
   - `services/npc/life_engine.py` (если есть) — мигрировать.
   - Любой callsite вне persistence layer — FORBIDDEN после Stage 0.

5. **Запретить `tick_ctx.all_npcs_raw` как runtime-truth.** Это поле должно остаться **только** как persistence-loaded snapshot, из которого на старте тика строится `Dict[str, NPCState]`, и в который на конце тика пишется обратно через `atomic_commit`. Прямые mutations `tick_ctx.all_npcs_raw[n].field = ...` — FORBIDDEN.

**Критерий выхода (предикаты):**

- `grep -rn "_RUNTIME_TOP_LEVEL_KEYS" backend/app/ --include="*.py"` → 0 hits (или только комментарий об упразднении).
- `grep -rn "NPCState.write_to_legacy" backend/app/ --include="*.py"` → 0 hits вне `services/state/`.
- `grep -rn "load_l2_state_from_runtime_dict" backend/app/services/ --include="*.py"` → 0 hits вне `services/state/` и `services/npc/npc_loader.py` (где определяется).
- Тест `backend/tests/test_tz3_contract_repair.py` — PASS.
- Новый тест `test_npc_state_runtime_single_truth.py`: после 100 тиков `npc_state.affective_load`, `emotion`, `narrative_cache`, `body_state` не сбрасываются к дефолтам.

### 1.5 Task 0.3 — Legacy JSON = только persistence representation `[HIGH]`

**BDD-сценарий:**

```text
GIVEN architecture/state.yaml:53-58 декларирует "FORBIDDEN: JSON as runtime truth"
  AND services/state/json_persistence_adapter.py существует как fallback

WHEN любая система вызывает JsonPersistenceAdapter.save_scene / save_npcs в runtime

THEN это нарушение Устава §4.2.2
  AND данные теряют транзакционность → corruption risk
```

**Контракт решения.**

1. `SqlitePersistenceAdapter` (`services/state/sqlite_persistence_adapter.py`) — единственный primary runtime-truth.
2. `JsonPersistenceAdapter` — fallback только при отсутствии SQLite (исключительная ситуация, логируется `[WARNING]`).
3. `PersistencePort.atomic_commit` (`services/state/persistence_port.py`) — единственный write-path (Устав §4.2.1).
4. Все callsites `JsonPersistenceAdapter` вне `__init__.py` регистрации — FORBIDDEN.
5. `grep -rn "JsonPersistenceAdapter" backend/app/services/ --include="*.py"` → только `services/state/__init__.py` и фабрика в `services/state/persistence_factory.py` (или эквивалент).

**Критерий выхода:**

- `grep -rn "JsonPersistenceAdapter" backend/app/services/ --include="*.py"` → только фабричный файл.
- Тест `backend/tests/test_persistence_port.py` — PASS.
- В runtime логах нет `[INFO]/[WARNING]` о fallback на JSON при нормальном ходе симуляции.

### 1.6 Task 0.4 — Разделение слоёв L0 / L1 / L2 / R4 `[HIGH]`

**BDD-сценарий:**

```text
GIVEN models/npc_state.py:1-14 декларирует write-контракт:
  L0 NPCPersonality    — write: NEVER (frozen dataclass)
  L1 NPCIdentityL1     — write: ONLY ResonanceEngine
  L2 NPCState          — write: ONLY StateApplicator
  EventMemory          — write: ONLY MemoryManager

WHEN любая система пишет в поле L0/L1/L2 вне владельца

THEN это нарушение контракта
  AND нарушается Устав §1.3 (services общаются через DTO/EventBus, не через прямые мутации)
```

**Ownership-таблица (контракт):**

| Слой | Тип | Writer | Reader (примерно) |
|---|---|---|---|
| L0 | `NPCPersonality` (frozen dataclass) | NEVER | `DecisionHub`, `DriveResolver` |
| L1 | `NPCIdentityL1` | `ResonanceEngine` только | `DecisionHub`, `VerbalizationContext` |
| L2 | `NPCState` | `StateApplicator` только | `DecisionHub` (read), `VerbalizationContext` (read via DTO) |
| Memory | `EventMemory` | `MemoryManager` только | `DecisionHub`, `VerbalizationContext` |
| R4 | `ContextBuilder` (read-only projection) | N/A (projection only) | `TickOrchestrator` |
| Beliefs | `BeliefState` (внутри `NPCState`) | `BeliefTransitionEngine` → `StateApplicator` | `DecisionHub` через `beliefs.as_modifiers()` |
| Relationships | `RelationshipStore` | `StateApplicator.update_relationships()` | `DecisionHub`, `OpportunityEngine` |

**Контракт решения.**

1. Ввести runtime assertion в `NPCState.__setattr__` (или в `__post_init__`-style hook) — если writer не `StateApplicator`, поднять `ArchitecturalViolationError`.
2. Для каждого поля `NPCState` добавить `# WRITE: only StateApplicator.<method>` комментарий (если ещё нет).
3. Ввести `@write_only(StateApplicator)` decorator для `NPCState` (или mro-трюк через `__set_name__`).

**Критерий выхода:**

- `grep -rn "state\.[a-z_]+ *= *" backend/app/services/ --include="*.py"` → только `services/npc/state_applicator.py`.
- Тест `test_npc_state_r6.py` — PASS.
- Новый тест `test_npc_state_write_violation.py`: попытка `state.stress = 50` из произвольного модуля поднимает `ArchitecturalViolationError`.

### 1.7 Task 0.5 — Убрать дублирующие writers beliefs `[CRITICAL]`

**BDD-сценарий:**

```text
GIVEN BeliefState (models/npc/beliefs.py:45) — owned by BeliefTransitionEngine
  AND state.beliefs.update() вызывается из 11+ файлов (см. §0.3 M4)

WHEN любая система кроме BeliefTransitionEngine пишет в state.beliefs

THEN это multi-writer violation (Устав §1.3, npc_state.py:614-617)
```

**Контракт решения.**

1. Греп: `grep -rn "\.beliefs\.\|beliefs\.update\|beliefs\.set" backend/app/services/ --include="*.py"` → полный список callsites.
2. Для каждого callsite — мигрировать на `BeliefTransitionEngine.commit(evidence: Evidence) -> BeliefDelta` API.
3. `StateApplicator` применяет `BeliefDelta` к `state.beliefs` — единственный физический write.
4. Разделить `NPCState.beliefs` (NPC's beliefs about world) от `PlayerBeliefModel` (player's beliefs about NPCs). LLM-архитектор MUST верифицировать, что `self._beliefs` в `action_consequence_compiler.py:66, 104` и `npc_confession_parser.py:108` — это `PlayerBeliefModel`, а не `NPCState.beliefs`. Если это так — оставить их в покое, но убедиться, что `PlayerBeliefModel` имеет ровно одного владельца (вероятно, `PlayerCognitionPipeline`).
5. Ввести assertion в `BeliefState.update`: `if caller not in (BeliefTransitionEngine, StateApplicator): raise`.

**Таблица миграции callsites (после grep):**

| Файл | Текущий вызов | Целевой API |
|---|---|---|
| `services/npc/belief_transition_engine.py:153, 190` | `state.beliefs.update(...)` (легальный) | Оставить, но обернуть в `commit(evidence)` |
| `services/execution/dialogue_executor.py` | (выяснить по grep) | `BeliefTransitionEngine.commit(Evidence(source=dialogue))` |
| `services/social/mvp_tavern_controller.py` | (выяснить) | `BeliefTransitionEngine.commit(Evidence(source=social))` |
| `services/integration/world_snapshot_builder.py` | (выяснить — может быть read-only) | Проверить; если read — оставить |
| `services/phases/integration.py` | (выяснить) | `BeliefTransitionEngine.commit(Evidence(source=phase))` |
| `services/phases/affective.py` | (выяснить) | `BeliefTransitionEngine.commit(Evidence(source=affective))` |
| `services/npc/npc_tick_pipeline.py` | (выяснить) | `BeliefTransitionEngine.commit(Evidence(source=tick))` |
| `services/tick_orchestrator.py` | (выяснить) | `BeliefTransitionEngine.commit(Evidence(source=orchestrator))` |
| `api/routes.py` | (выяснить — должно быть read-only через DTO) | Запретить прямой write; только через BeliefTransitionEngine из сервиса |

**Критерий выхода:**

- `grep -rn "state\.beliefs\.\(update\|set\|clear\)" backend/app/services/ --include="*.py"` → 0 hits вне `belief_transition_engine.py`.
- `grep -rn "\.beliefs\." backend/app/api/ --include="*.py"` → 0 hits (api не должен трогать beliefs напрямую).
- Тест `backend/tests/sandbox/system/test_t06_belief_pipeline.py` — PASS.
- Новый тест `test_belief_single_writer.py`: попытка `state.beliefs.update(...)` из `dialogue_executor.py` поднимает `ArchitecturalViolationError`.

### 1.8 Task 0.6 — SSOT Epistemic (BeliefState) `[CRITICAL]`

**BDD-сценарий:**

```text
GIVEN BeliefTransitionEngine (services/npc/belief_transition_engine.py:7)
       декларирует себя "Единственный владелец записи в NPCState.beliefs"
  AND BeliefTransitionEngine.commit(evidence) — единственный write-API

WHEN observation O воспринято NPC N (PerceptualKernel → MemoryManager → BeliefInference)
  AND BeliefInference производит Evidence E

THEN BeliefTransitionEngine.commit(E) генерирует BeliefDelta D
  AND StateApplicator.apply(D) модифицирует state.beliefs
  AND CausalLedger.append({field=beliefs, cause=E, delta=D, tick=t})
```

**Контракт решения.**

1. `BeliefTransitionEngine` API:
   ```python
   class BeliefTransitionEngine:
       def commit(self, evidence: Evidence) -> BeliefDelta:
           """Единственный write-path в NPCState.beliefs.
           
           Evidence = (source_event_id, observation, memory_ref, inferred_belief_type, confidence).
           Возвращает BeliefDelta, который StateApplicator применяет к state.beliefs.
           """
   ```
2. `Evidence` — frozen dataclass с provenance (`source_event_id`, `tick`, `npc_id`).
3. `BeliefDelta` — frozen dataclass с `(belief_type, old_value, new_value, evidence_ref)`.
4. `StateApplicator.apply_belief_delta(state, delta)` — единственная физическая мутация `state.beliefs`.

**Критерий выхода:**

- Все writers из §1.7 таблицы мигрируют на `BeliefTransitionEngine.commit(Evidence)`.
- `Evidence` имеет `source_event_id` — пригодно для causal chain в Stage 1.
- Тест `backend/tests/sandbox/SUPERBOX/scenarios/epistemic_player_belief_test.py` — PASS.
- Тест `backend/tests/sandbox/SUPERBOX/scenarios/epistemic_second_order_attribution_test.py` — PASS.

### 1.9 Task 0.7 — SSOT Social (RelationshipStore) `[HIGH]`

**BDD-сценарий:**

```text
GIVEN NPCState.relationship_cache (models/npc_state.py:714) — эфемерный read-cache
  AND npc_state.py:791-793 прямо говорит: "SSOT = RelationshipStore.
       Персистенция кэша = DOUBLE TRUTH"
  AND write_to_legacy НЕ пишет relationship_cache (P1 ARCH FIX, npc_state.py:841-843)

WHEN StateApplicator.apply_deltas_only(state, delta) получает DeltaDomain SOCIAL
  AND delta изменяет trust/fear/debt

THEN StateApplicator обязан:
  1. Обновить RelationshipStore (SSOT)
  2. Обновить state.relationship_cache (read-cache projection) — синхронно
  3. Не персистировать relationship_cache отдельно (FORBIDDEN)
```

**Контракт решения.**

1. `RelationshipStore` (через `MemoryRelationshipStore`) — единственный SSOT для trust/fear/debt.
2. `StateApplicator.update_relationships(npc_id, target_id, trust_delta, fear_delta, debt_delta)` — единственный write-API.
3. `state.relationship_cache` — read-only projection из `RelationshipStore`, обновляется в `StateApplicator` синхронно с `RelationshipStore.update()`.
4. `grep -rn "relationship_cache\[" backend/app/ --include="*.py"` → только `services/npc/state_applicator.py` и `services/npc/npc_loader.py` (init при spawn).

**Критерий выхода:**

- `grep -rn "relationship_cache\[" backend/app/services/ --include="*.py"` → только `state_applicator.py`.
- Тест `backend/tests/sandbox/persistence/test_relationship_cache_not_persisted.py` — PASS.
- Тест `backend/tests/test_npc_social_enrichment.py` — PASS.

### 1.10 Task 0.8 — SSOT Economic (money / gold) `[CRITICAL]`

**BDD-сценарий:**

```text
GIVEN phase_2_world_tick.py:243-248 мутирует _avatar.body_state["money"] напрямую:
  _avatar.body_state["money"] = float(_avatar.body_state.get("money", 0.0)) + _money_delta
  AND _delta уже применён через StateApplicator.apply_batch (строка 234)

WHEN TradeResolver.resolve_tick() возвращает List[TradeResult]
  AND TradeResult = {buyer_id, seller_id, price, goods}

THEN для каждого TradeResult MUST:
  1. Создать StateDeltas(domain=ECONOMY, payload=EconomicPayload(money_delta=-price, goods_delta=goods))
     для buyer_id
  2. Создать StateDeltas(domain=ECONOMY, payload=EconomicPayload(money_delta=+price, goods_delta=None))
     для seller_id
  3. Если npc_id == "player" — игрок обрабатывается как avatar NPC
  4. StateApplicator.apply_batch([deltas], all_npcs, campaign_id) — единственный write-path
  5. _avatar.body_state["money"] НЕ мутируется напрямую (FORBIDDEN)
```

**Контракт решения.**

1. Игрок — это `avatar NPC` с `npc_id = "player"`. `StateApplicator.apply_batch` обрабатывает его наравне с NPC.
2. В `StateApplicator.apply_batch` добавить ветку: `if delta.npc_id == "player": apply_to_avatar(avatar_state, delta)`.
3. Удалить `phase_2_world_tick.py:243-248` inline-мутацию.
4. Ввести assertion в `AvatarState.__setattr__` для `body_state["money"]` — если writer не `StateApplicator`, поднять `ArchitecturalViolationError`.

**Критерий выхода:**

- `grep -rn "_avatar\.body_state\[" backend/app/ --include="*.py"` → только `services/npc/state_applicator.py`.
- Тест `backend/tests/sandbox/persistence/test_player_body_state_survives_save_load.py` — PASS.
- Новый тест `test_economy_ssot_player_money.py`: после 10 торговых тиков `_avatar.body_state["money"]` совпадает с `EconomyProfile["player"].gold` с точностью до эпсилон.

### 1.11 Task 0.9 — Ban прямых writes в NPCState (domain ownership) `[HIGH]`

**BDD-сценарий:**

```text
GIVEN models/npc_state.py:5-9 docstring:
  L0 NPCPersonality   — write: NEVER (frozen dataclass)
  L1 NPCIdentityL1    — write: ONLY ResonanceEngine
  L2 NPCState         — write: ONLY StateApplicator
  EventMemory         — write: ONLY MemoryManager

WHEN любая система напрямую пишет state.field = value (не через StateApplicator.apply_*)

THEN это нарушение write-контракта
```

**Контракт решения.**

1. В `NPCState.__setattr__` (или в `__post_init__`) добавить guard:
   ```python
   _WRITERS = {  # module → allowed fields
       "app.services.npc.state_applicator": {"*"},  # все поля
       "app.services.npc.belief_transition_engine": {"beliefs"},  # только beliefs (через commit)
       "app.services.memory.memory_manager": {"narrative_cache", "affective_imprints"},
       "app.services.npc.resonance_engine": set(),  # L1, не L2
   }
   ```
2. При попытке `state.field = value` из модуля вне whitelist — `raise ArchitecturalViolationError(field, writer_module)`.
3. В `StateApplicator` все `apply_*`-методы идут через внутренний `_set(state, field, value)`-helper, который обходит guard (через `__setattr__`-bypass или `object.__setattr__`).

**Domain ownership-таблица (для §1.6 assertions):**

| Поле | Единственный writer-метод |
|---|---|
| `stress` | `StateApplicator.apply_tick_recovery` |
| `affective_load` | `StateApplicator._apply_affective_deltas` (создать, если нет) |
| `body_state` (включая `current_hp`) | `StateApplicator.apply_physical` |
| `beliefs` | `BeliefTransitionEngine.commit` → `StateApplicator.apply_belief_delta` |
| `relationship_cache` | `StateApplicator.update_relationships` |
| `narrative_cache` | `MemoryManager.append_event_memory` → `StateApplicator.apply_memory_delta` |
| `intent`, `intent_target` | `DecisionHub` → `StateApplicator._apply_intent` (state_applicator.py:506) |
| `temporary_drives` | `StateApplicator._apply_deltas` (через `DeltaDomain.PSYCHE`) |
| `trauma_markers` | `StateApplicator._apply_trauma_and_traits` (state_applicator.py:1094) |
| `trait_activation` | `StateApplicator._apply_trait_decay` (state_applicator.py:1136) |

**Критерий выхода:**

- `grep -rn "state\.[a-z_]\+ *=" backend/app/services/ --include="*.py" | grep -v state_applicator.py` → 0 hits.
- Тест `backend/tests/test_npc_state_r6.py` — PASS.
- Новый тест `test_npc_state_write_guard.py`: `state.stress = 50` из `api/routes.py` поднимает `ArchitecturalViolationError`.

### 1.12 Task 0.10 — Убрать параллельный WorldTick-путь `[CRITICAL]`

**BDD-сценарий:**

```text
GIVEN services/game_loop/phase_2_world_tick.py:138, 160 вызывает
       NPCState.write_to_legacy(_wt_state, _wt_npc_raw) — отдельный write-path
  AND tick_ctx.wt_dirty = True сигнализирует о необходимости _save_npcs() в конце тика

WHEN phase_2_world_tick отрабатывает proactive decisions, recovery, need_engine.tick,
     trade_resolver.resolve_tick, economy_tracker

THEN все mutations применяются ВНЕ StateApplicator → atomic_commit pipeline
  AND канонический pipeline не знает об этих изменениях
  AND replay не способен их воспроизвести (нет provenance в CausalLedger)
```

**Контракт решения.**

1. **Упразднить `phase_2_world_tick.py`** как отдельный phase-файл.
2. `WorldTickEngine.compute_proactive_decisions()` — переориентировать на публикацию `List[EventDTO]` в `EventBus` (Устав §2.1.2: «WorldTickEngine не возвращает List[dict]. Он создаёт List[EventDTO] и публикует каждый через EventBus»).
3. Все effects (recovery, need_engine.tick, trade_resolver) — конвертировать в `StateDeltas` и применять через `StateApplicator.apply_deltas_and_commit`.
4. `EconomyTracker.check_daily_needs` — оставить как observer, но writes идут через `StateDeltas`.
5. `NeedEngine.tick` — оставить как producer `StateDeltas(domain=ECONOMY, payload=NeedDelta)`.
6. `TradeResolver.resolve_tick` — producer `List[StateDeltas]`, applies через `StateApplicator.apply_batch`.
7. `_avatar.body_state["money"]` inline-мутация (строки 243-248) — удалить (см. Task 0.8).

**Альтернативный вариант (если LLM-архитектор сочтёт, что `phase_2_world_tick.py` должен остаться как организующая функция):** оставить файл, но:
- Все writes идут через `StateApplicator.apply_deltas_and_commit`.
- Никаких `NPCState.write_to_legacy` calls.
- Никаких `tick_ctx.wt_dirty` флагов.
- Все decisions публикуются как `List[EventDTO]`.

**Критерий выхода:**

- `grep -rn "NPCState.write_to_legacy" backend/app/services/game_loop/ --include="*.py"` → 0 hits.
- `grep -rn "tick_ctx.wt_dirty\|wt_dirty" backend/app/ --include="*.py"` → 0 hits.
- Тест `backend/tests/test_tick_orchestrator_full_loop.py` — PASS.
- Тест `backend/tests/sandbox/test_tick_orchestrator_full_loop.py` — PASS.
- Новый тест `test_no_parallel_world_tick.py`: состояние NPC после 100 тиков с `phase_2_world_tick` идентично состоянию без него (для тех же inputs).

### 1.13 Stage 0 — Definition of Done (Invariants + Tests)

**Инварианты (runtime-предикаты):**

| # | Предикат | Проверка |
|---|---|---|
| I0.1 | `∀ field F ∈ NPCState: ∃! writer S` | Греп-верификация + runtime assertion в `__setattr__` |
| I0.2 | `_RUNTIME_TOP_LEVEL_KEYS` упразднён или пуст | `grep -rn "_RUNTIME_TOP_LEVEL_KEYS" backend/app/ --include="*.py"` → 0 hits |
| I0.3 | `NPCState.write_to_legacy` не вызывается в runtime | `grep -rn "write_to_legacy" backend/app/services/ --include="*.py"` → 0 hits вне `services/state/` |
| I0.4 | `state.beliefs.update` только в `BeliefTransitionEngine` | `grep -rn "state\.beliefs\.\(update\|set\)" backend/app/services/ --include="*.py"` → 0 hits вне `belief_transition_engine.py` |
| I0.5 | `phase_2_world_tick.py` упразднён или пуст | Файл либо удалён, либо не содержит `NPCState.write_to_legacy` и `tick_ctx.wt_dirty` |
| I0.6 | Compile error M1 устранён | `python -c "import app.services.player_cognition.action_semantic_resolver"` → exit 0 |
| I0.7 | `JsonPersistenceAdapter` не вызывается в runtime | `grep -rn "JsonPersistenceAdapter" backend/app/services/ --include="*.py"` → только фабричный файл |
| I0.8 | `NPCStateAdapter` — единственный roundtrip bridge, в persistence layer | `grep -rn "NPCStateAdapter" backend/app/ --include="*.py"` → только `services/state/` и `models/npc_state.py:968` |
| I0.9 | Прямых writes в `NPCState` вне `StateApplicator` нет | Runtime assertion поднимает `ArchitecturalViolationError` |
| I0.10 | `_avatar.body_state` не мутируется напрямую | `grep -rn "_avatar\.body_state\[" backend/app/ --include="*.py"` → 0 hits вне `state_applicator.py` |

**Тесты (BDD-сценарии, должны PASS):**

| Тест | Что проверяет |
|---|---|
| `backend/tests/test_tz3_contract_repair.py` | Контракт L0/L1/L2 после ремонта |
| `backend/tests/test_persistence_port.py` | `atomic_commit` контракт |
| `backend/tests/test_npc_state_r6.py` | NPCState write-guards |
| `backend/tests/sandbox/persistence/test_relationship_cache_not_persisted.py` | `relationship_cache` не персистится |
| `backend/tests/sandbox/persistence/test_crystallized_belief_persistence.py` | Beliefs персистятся корректно |
| `backend/tests/sandbox/persistence/test_player_body_state_survives_save_load.py` | Avatar body_state выживает save/load |
| `backend/tests/sandbox/system/test_t06_belief_pipeline.py` | Belief pipeline end-to-end |
| Новый `test_stage0_invariants.py` | Все I0.* инварианты |
| Новый `test_npc_state_runtime_single_truth.py` | После 100 тиков fields не обнуляются |
| Новый `test_belief_single_writer.py` | Belief writers только через `BeliefTransitionEngine.commit` |
| Новый `test_no_parallel_world_tick.py` | Нет `wt_dirty` path |
| Новый `test_economy_ssot_player_money.py` | `_avatar.body_state["money"]` = `EconomyProfile["player"].gold` |
| Новый `test_compile_error_resolved.py` | `action_semantic_resolver` импортируется |

---

## §2. STAGE 1 — Causal Spine

### 2.1 Цель и критерий выхода стадии

**Цель.** Событие должно проходить через мир непрерывной причинной цепью:

```
WORLD
  ↓
EVENT
  ↓
OBSERVATION
  ↓
MEMORY
  ↓
BELIEF
  ↓
DECISION
  ↓
ACTION
  ↓
STATE DELTA
  ↓
WORLD
```

**Что Stage 1 доделывает:**

1. Deterministic replay.
2. Provenance.
3. Snapshots.
4. Causal ledger.
5. Event visibility.
6. Action execution.
7. Persistence (atomic_commit).

**Критерий выхода (предикат):**

```
Создать 1 NPC. Прогнать 10 000 тиков.
Взять любое изменение state delta (например: trust = -31).
Получить полную причинную цепочку:
  1. Какое событие вызвало изменение?
  2. Кто его воспринял?
  3. Как (через какой PerceptualKernel → Observation)?
  4. Что запомнил (MemoryManager → EventMemory)?
  5. Что вывел (BeliefTransitionEngine → BeliefDelta)?
  6. Что решил (DecisionHub → Intent)?
  7. Что сделал (ActionExecutor → EventDTO)?
  8. Какое изменение состояния получил мир (StateDelta)?

Если любая из 8 ссылок отсутствует — Stage 1 не закончен.
```

Пока этой цепочки нет, **строить сложную психику запрещено** (§0.5 — стоимость переделки растёт экспоненциально).

### 2.2 Stop-list Stage 1

| # | Паттерн | Запрет | Нарушение сейчас |
|---|---|---|---|
| F1.1 | Любой RNG кроме `KernelRNG` в kernel layer | FORBIDDEN (ADR-O-301) | Проверить `grep -rn "random\.uniform\|random\.random\|random\.randint\|random\.choice" backend/app/services/ --include="*.py"` вне `services/kernel_rng.py` |
| F1.2 | Прямой доступ к `scene_state` из `ProjectionEngine` | FORBIDDEN (ADR-O-201) | `services/scene_state_manager.py:apply_change` — 6 мутаций (`architecture/state.yaml:86-92`) |
| F1.3 | Mutation `TickContext` вне фаз | FORBIDDEN (Устав §3) | `phase_2_world_tick.py` — мутирует `tick_ctx.wt_dirty` вне фазового контракта |
| F1.4 | Публикация events мимо `EventBus` | FORBIDDEN (Устав §2.1.1) | `phase_2_world_tick.py:105` — `shared_context.world_tick_result = _tick_result` вместо `EventBus.publish(EventDTO)` |
| F1.5 | Non-deterministic время в pipeline | FORBIDDEN | `grep -rn "datetime\.now\|time\.time()" backend/app/services/ --include="*.py"` вне logging |
| F1.6 | Persistence без `atomic_commit` | FORBIDDEN (Устав §4.2.1) | `_save_npcs()` legacy path |
| F1.7 | Snapshot с live references | FORBIDDEN (ADR-O-201) | Проверить `TickOrchestrator._init_pipeline_context` |
| F1.8 | Action execution без `CausalLedger` entry | FORBIDDEN (§2.5 Task 1.4) | Любой `apply_*` без записи в `causal_ledger` |
| F1.9 | Replay без causal ledger | FORBIDDEN | Replay должен читать `CausalLedger` и применять дельты, а не «переигрывать» системы |

### 2.3 Task 1.1 — Deterministic Replay `[CRITICAL]`

**BDD-сценарий:**

```text
GIVEN KernelRNG (services/pipeline_runner.py / models/pipeline_context.py)
       bound to (tick, npc_id, salt) (ADR-O-301)
  AND TickContext содержит rng_factory для deterministic creation per NPC
  AND architecture/pipeline.yaml:36-44 описывает KernelRNG

WHEN replay запускается от snapshot + input events

THEN state[t] точно совпадает с исходным
  AND дрейф_replay_determinism.csv показывает 0 diffs
```

**Контракт решения.**

1. **Любой RNG в pipeline = `KernelRNG.next()`** (`architecture/pipeline.yaml:36-44`).
2. `KernelRNG` bound to `(tick, npc_id, salt)` — детерминирован при равных входах.
3. **FORBIDDEN** в kernel layer:
   - `random.uniform`, `random.random`, `random.randint`, `random.choice` (использовать `KernelRNG.next_uniform()`, etc.)
   - `datetime.now()` (использовать `tick_num`)
   - `os.urandom()`, `secrets.token_hex()`
   - LLM вызовы без кэша (кэш по `(tick, npc_id, prompt_hash)`)
4. **LLM determinism:** `services/llm/` — кэш результатов LLM по хэшу промпта + tick + npc_id. На replay — чтение из кэша, не повторный запрос к llama-server.
5. **Греп-верификация:**
   ```bash
   grep -rn "random\.uniform\|random\.random\|random\.randint\|random\.choice\|datetime\.now\|time\.time" \
     backend/app/services/ --include="*.py" \
     | grep -v "kernel_rng\|logging\|debug"
   ```
   → 0 hits в kernel layer.

**Критерий выхода:**

- Replay 10 000 тиков: 0 diffs в `backend/tests/sandbox/SUPERBOX/reports/дрейф_replay_determinism.csv`.
- Тест `backend/tests/sandbox/SUPERBOX/causal_validation.py` — PASS.
- Тест `backend/tests/sandbox/runtime/deterministic_clock.py` — PASS.
- Тест `backend/tests/test_tick_orchestrator_full_loop.py` — PASS.

### 2.4 Task 1.2 — Provenance (passports of state changes) `[CRITICAL]`

**BDD-сценарий:**

```text
GIVEN любое изменение state.field = X через StateApplicator
WHEN StateApplicator.apply(...) вызывается

THEN CausalEntry{
       tick: int,
       npc_id: str,
       field: str,
       old_value: Any,
       new_value: Any,
       source_event_id: UUID | None,
       source_action_id: UUID | None,
       cause: Cause
     } добавляется в causal_ledger (npc_state.py:725)
  AND CausalEntry не может быть удалён (append-only)
  AND без provenance state change не валиден (§ENIGMA-005 Referential Closure)
```

**Контракт решения.**

1. `Cause` — frozen dataclass:
   ```python
   @dataclass(frozen=True)
   class Cause:
       source_event_id: UUID | None  # EventDTO, инициировавший изменение
       source_action_id: UUID | None  # Action ID, если изменение — следствие action
       source_belief_id: UUID | None  # Belief inference, если изменение — belief delta
       source_memory_id: UUID | None  # Memory, повлиявший на решение
       trigger_chain: tuple[UUID, ...]  # Цепочка причин (для second-order beliefs)
   ```
2. `StateApplicator.apply(state, deltas, cause: Cause)` — `cause` обязательный параметр (после Stage 1).
3. `CausalEntry` (см. `models/psychological.py` — `CausalEntry` уже существует, `npc_state.py:725` использует).
4. `causal_ledger` — ring-buffer, последние N = 1000 entries per NPC (настраиваемо).

**Критерий выхода:**

- `grep -rn "StateApplicator.apply(" backend/app/ --include="*.py"` → все callsites передают `cause`.
- Тест `backend/tests/sandbox/micro/test_causal_kernel.py` — PASS.
- Тест `backend/tests/sandbox/system/test_causal_closure.py` — PASS.
- Новый тест `test_provenance_required.py`: `StateApplicator.apply(state, deltas)` без `cause` → `MissingProvenanceError`.

### 2.5 Task 1.3 — Snapshots (frozen WorldSnapshot per tick) `[CRITICAL]`

**BDD-сценарий:**

```text
GIVEN architecture/state.yaml:125-131 (SnapshotState ownership):
  "ADR-O-201: Frozen copy of all state needed for event compilation.
   Must include boundary_map, spatial_graph, rng_seed.
   No references to live objects — deep copy required.
   Violation of immutability = non-deterministic replay."

WHEN start of tick

THEN WorldSnapshot создан как deep copy:
  - scene_state
  - spatial_graph
  - boundary_map
  - rng_seed
  - all_npcs_raw (или Dict[str, NPCState] после Stage 0)
  AND snapshot — immutable (frozen dataclass)
  AND sole consumer = EventCompiler
```

**Контракт решения.**

1. `WorldSnapshot` — `@dataclass(frozen=True)` с полями: `tick: int`, `scene_state: MappingProxyType`, `spatial_graph: FrozenGraph`, `boundary_map: FrozenBoundaryMap`, `rng_seed: int`, `npcs: MappingProxyType[str, NPCState]`.
2. `TickOrchestrator._create_snapshot() -> WorldSnapshot` — единственный producer.
3. `EventCompiler.compile(snapshot: WorldSnapshot, events: List[EventDTO]) -> List[ThickSceneChange]` — единственный consumer.
4. Deep copy через `copy.deepcopy` или через сериализацию-десериализацию (если быстрее).
5. **FORBIDDEN:** любые live references на mutable объекты в snapshot.

**Критерий выхода:**

- `grep -rn "WorldSnapshot" backend/app/ --include="*.py"` → определяется в `models/pipeline_context.py` или `models/world_snapshot.py`, используется в `services/pipeline_runner.py` и `services/events/event_compiler.py`.
- Тест `backend/tests/sandbox/runtime/causal_trace.py` — PASS.
- Тест `backend/tests/sandbox/SUPERBOX/scenarios/epistemic_runtime_closure_test.py` — PASS.
- Новый тест `test_snapshot_immutability.py`: попытка `snapshot.scene_state["x"] = "y"` → `TypeError: cannot assign to frozen dataclass` или `MappingProxyType` raises.

### 2.6 Task 1.4 — Causal Ledger (queryable chain) `[CRITICAL]`

**BDD-сценарий:**

```text
GIVEN causal_ledger (models/npc_state.py:722-725) хранит последние N CausalEntry
WHEN state mutation применяется через StateApplicator

THEN CausalEntry appended с provenance (Task 1.2)
  AND CausalLedger.query(field=npc.beliefs.trust, tick_range=(t1, t2))
       возвращает List[CausalEntry] — полную причинную цепочку
  AND по любому state delta можно построить chain:
       source_event → observation → memory → belief → decision → action → state_delta
```

**Контракт решения.**

1. `CausalLedger.append(entry: CausalEntry)` — append-only, ring-buffer.
2. `CausalLedger.query(field: str, tick_range: tuple[int, int] | None) -> list[CausalEntry]` — фильтрация по полю и/или диапазону тиков.
3. `CausalLedger.trace(state_delta_id: UUID) -> CausalChain` — построение полной цепочки из 8 шагов (см. §2.1).
4. `CausalChain` — frozen dataclass с 8 опциональными ссылками: `source_event`, `observation`, `memory`, `belief`, `decision`, `action`, `state_delta`, `world_change`.

**Критерий выхода:**

- Тест: создать NPC, прогнать 100 тиков, запросить `CausalLedger.query(field="trust", tick_range=(50, 100))` — возвращает непустой список.
- Тест: `CausalLedger.trace(state_delta_id)` возвращает цепочку с ≥4 из 8 шагов (полные 8 — после Stage 1 полного завершения).
- Тест `backend/tests/sandbox/SUPERBOX/scenarios/epistemic_causal_test.py` — PASS.

### 2.7 Task 1.5 — Event Visibility `[HIGH]`

**BDD-сценарий:**

```text
GIVEN EventDTO (Устав §2.1) с visibility ∈ {public, private, whisper}
  AND EventDTO.radius: float — физический радиус
  AND §ENIGMA-S72: движок производит только сырые сигналы

WHEN event published via EventBus

THEN только агенты в зоне видимости получают Observation
  AND PerceptualKernel (npc_state.py:630) — единственный фильтр:
       EventDTO → Observation (если в радиусе + visibility позволяет) → Memory → Belief
  AND телепатия запрещена (§ENIGMA-S72)
```

**Контракт решения.**

1. `EventBus.publish(event: EventDTO)` → рассылает `Observation` только тем NPC, у которых `PerceptualKernel.can_observe(event)` == True.
2. `PerceptualKernel.can_observe(event)` — проверяет:
   - Расстояние от NPC до event.source ≤ event.radius
   - visibility: `public` — все; `private` — только source; `whisper` — только source + audience list
   - Физические препятствия (line-of-sight через `boundary_map`)
3. `MemoryManager.observe(observation)` — единственный write-path в `EventMemory`.

**Критерий выхода:**

- Тест `backend/tests/sandbox/micro/test_no_telepathy_in_ui.py` — PASS.
- Тест `backend/tests/sandbox/micro/test_telepathy_epistemic_barrier.py` — PASS.
- Тест `backend/tests/sandbox/micro/test_recognition_and_eavesdrop.py` — PASS.
- Тест `backend/tests/sandbox/SUPERBOX/scenarios/epistemic_observation_divergence_test.py` — PASS.

### 2.8 Task 1.6 — Action Execution `[CRITICAL]`

**BDD-сценарий:**

```text
GIVEN DecisionHub возвращает Intent
WHEN IntentEventAdapter конвертирует Intent → EventDTO → EventBus.publish

THEN action executor (services/execution/dialogue_executor.py, etc.)
       применяет effects через StateApplicator
  AND эффекты имеют provenance (Task 1.2)
  AND никаких effects applied outside EventDTO pipeline (FORBIDDEN)
```

**Контракт решения.**

1. `IntentEventAdapter.adapt(intent: Intent) -> EventDTO` — единственная конверсия.
2. `EventBus.publish(event)` → `EventCompiler` → `ThickSceneChange[]` → `ProjectionEngine.apply` → `SceneState`.
3. `ActionExecutor.execute(action: Action) -> StateDeltas` — все эффекты как `StateDeltas`, применяются через `StateApplicator.apply_deltas_and_commit`.
4. **Устав §2.1.2:** `WorldTickEngine` возвращает `List[EventDTO]`, не `List[dict]`. После Task 0.10 `phase_2_world_tick.py` упразднён — эта обязанность переходит к `TickOrchestrator.ФАЗА_3.4` (Agenda Loop).

**Критерий выхода:**

- `grep -rn "List\[dict\]\|list\[dict\]" backend/app/services/ --include="*.py"` → 0 hits в return-types of `WorldTickEngine`, `ActionExecutor`, etc.
- Тест `backend/tests/sandbox/micro/test_run_turn_e2e.py` — PASS.
- Тест `backend/tests/sandbox/SUPERBOX/scenarios/epistemic_action_causation_test.py` — PASS.
- Тест `backend/tests/sandbox/SUPERBOX/scenarios/epistemic_production_test.py` — PASS.

### 2.9 Task 1.7 — Persistence (atomic_commit) `[CRITICAL]`

**BDD-сценарий:**

```text
GIVEN StateApplicator.apply_deltas_and_commit (services/npc/state_applicator.py:1310)
  AND SqlitePersistenceAdapter.atomic_commit (services/state/sqlite_persistence_adapter.py)
  AND architecture/state.yaml:59-64 (constraint):
    "REQUIRED: atomic_commit for all saves (Устав §4.2.1)
     Three separate JSON files = desync bug. Must commit atomically."

WHEN end of tick

THEN atomic_commit(campaign_id, scene_state, npc_dicts) = single transaction
  AND все changes (scene + npcs + memory + beliefs + economy) сохранены в одной транзакции
  AND если любая часть падает — вся транзакция откатывается (atomic)
```

**Контракт решения.**

1. `PersistencePort.atomic_commit(campaign_id: str, scene_state: dict, npc_states: list[NPCState]) -> None` — единственный write-path в persistence layer.
2. Внутри `atomic_commit`:
   - `BEGIN TRANSACTION`
   - Сохранить `scene_state` в `state_kv` (SQLite)
   - Сохранить `npc_states` (сериализация через `NPCState.to_persistence_dict()`)
   - Сохранить `memory`, `beliefs`, `economy` (если они в отдельных таблицах)
   - `COMMIT` или `ROLLBACK` при ошибке
3. `JsonPersistenceAdapter` — fallback только (Устав §4.2.2).
4. **FORBIDDEN:** `_save_npcs()` legacy path (отдельные JSON файлы).

**Критерий выхода:**

- `grep -rn "_save_npcs\b" backend/app/ --include="*.py"` → 0 hits.
- `grep -rn "atomic_commit" backend/app/services/ --include="*.py"` → `state_applicator.py:1310` (вызов) + `services/state/` (реализация).
- Тест `backend/tests/test_persistence_port.py` — PASS.
- Тест `backend/tests/sandbox/persistence/test_crystallized_belief_persistence.py` — PASS.
- Тест `backend/tests/sandbox/persistence/test_l1_chronicle_archival.py` — PASS.

### 2.10 Stage 1 — Definition of Done (Invariants + Tests)

**Инварианты:**

| # | Предикат | Проверка |
|---|---|---|
| I1.1 | 10 000-tick replay determinism: 0 diffs | `backend/tests/sandbox/SUPERBOX/reports/дрейф_replay_determinism.csv` — 0 rows with `diff > 0` |
| I1.2 | Для любого state delta существует `CausalEntry` с `source_event_id` | `CausalLedger.query()` возвращает непустой список для любого поля после 100 тиков |
| I1.3 | `CausalLedger.query()` возвращает полную цепочку для любого поля | `CausalLedger.trace(state_delta_id)` возвращает ≥4 из 8 шагов (после полного Stage 1 — 8 из 8) |
| I1.4 | `WorldSnapshot` immutable, no live refs | `test_snapshot_immutability.py` — PASS |
| I1.5 | Любой event следует через `EventBus` | `grep -rn "direct.*mutation\|shared_context\.world_tick_result" backend/app/ --include="*.py"` → 0 hits |
| I1.6 | Persistence только через `atomic_commit` | `grep -rn "_save_npcs" backend/app/ --include="*.py"` → 0 hits |
| I1.7 | Любой RNG в kernel layer — `KernelRNG` | `grep -rn "random\.uniform\|random\.random\|datetime\.now" backend/app/services/ --include="*.py" | grep -v kernel_rng\|logging` → 0 hits |
| I1.8 | Provenance обязательный для state change | `StateApplicator.apply` без `cause` → `MissingProvenanceError` |

**Тесты (BDD-сценарии, должны PASS):**

| Тест | Что проверяет |
|---|---|
| `backend/tests/test_tick_orchestrator_full_loop.py` | Полный tick pipeline |
| `backend/tests/sandbox/test_causal_movement.py` | Causal движение |
| `backend/tests/sandbox/micro/test_causal_kernel.py` | CausalKernel |
| `backend/tests/test_world_continuity.py` | World continuity |
| `backend/tests/sandbox/SUPERBOX/scenarios/epistemic_causal_test.py` | Causal chain end-to-end |
| `backend/tests/sandbox/system/test_causal_closure.py` | Causal closure |
| `backend/tests/sandbox/runtime/causal_trace.py` | Causal trace query |
| `backend/tests/sandbox/runtime/deterministic_clock.py` | Deterministic clock |
| `backend/tests/sandbox/SUPERBOX/causal_validation.py` | Causal validation suite |
| `backend/tests/sandbox/SUPERBOX/scenarios/epistemic_runtime_closure_test.py` | Runtime closure |
| Новый `test_stage1_causal_chain_reconstruction.py` | Для `trust=-31` возвращает 8-step chain |
| Новый `test_provenance_required.py` | `StateApplicator.apply` без `cause` → exception |
| Новый `test_snapshot_immutability.py` | Snapshot immutable |
| Новый `test_10k_tick_replay_determinism.py` | 10 000-tick replay: 0 diffs |

**Критерий выхода Stage 1 (булев предикат):**

```
∀ state_delta D applied during simulation:
  ∃ CausalChain C such that
    C.source_event != None
    AND C.observation != None
    AND C.memory != None
    AND C.belief != None
    AND C.decision != None
    AND C.action != None
    AND C.state_delta == D
    AND C.world_change != None

AND 10 000-tick replay produces 0 diffs
AND all I1.* invariants pass
AND all listed tests PASS
```

---

## §3. Сводный Stop-list (консолидированные запреты)

Quick reference для LLM-архитектора. Каждый паттерн — FORBIDDEN.

### 3.1 Stage 0 запреты

| # | Паттерн | Why forbidden | Reference | Нарушение сейчас |
|---|---|---|---|---|
| F0.1 | Прямой write в `NPCState` вне `StateApplicator` | Нарушает ownership L2 | Устав §1.3, `npc_state.py:5-9` | `phase_2_world_tick.py:138, 160` |
| F0.2 | JSON как runtime truth | Нет транзакций → corruption | Устав §4.2.2, `state.yaml:53-58` | `JsonPersistenceAdapter` runtime-call-sites |
| F0.3 | Новое поле в `NPCState` без domain ownership | Ломает §ENIGMA-001 | Устав §1.3 | Любое расширение `_RUNTIME_TOP_LEVEL_KEYS` |
| F0.4 | Параллельный tick-path мимо `TickOrchestrator` | Ломает §ENIGMA-005 | Устав §3 | `phase_2_world_tick.py` целиком |
| F0.5 | Multi-writer beliefs вне `BeliefTransitionEngine` | Ломает SSOT epistemic | `npc_state.py:614-617` | 11+ файлов (см. §0.3 M4) |
| F0.6 | Персистенция эфемерных кэшей (`relationship_cache`, `narrative_cache`) | DOUBLE TRUTH | `npc_state.py:791-793` | Проверить сериализацию |
| F0.7 | Прямая мутация `scene_state` мимо `SceneChange`/`ThickSceneChange` | Ломает ADR-O-201 | `state.yaml:93-102`, ADR-TZ04-5 | `services/scene_state_manager.py:apply_change` (6 мутаций) |
| F0.8 | Прямая мутация `_avatar.body_state` мимо `StateApplicator` | Ломает SSOT economic | — | `phase_2_world_tick.py:243-248` |
| F0.9 | Bypass `atomic_commit` (три отдельных JSON файла) | Desync bug | Устав §4.2.1 | `_save_npcs()` legacy |
| F0.10 | Расширение `_RUNTIME_TOP_LEVEL_KEYS` как fix двойной истины | Закрепляет болезнь | Этот документ §0.3 M2 | `npc_loader.py:280-311` |
| F0.11 | Compile error `ModuleNotFoundError` | Pipeline падает | — | `game_loop/__init__.py:1869` |

### 3.2 Stage 1 запреты

| # | Паттерн | Why forbidden | Reference | Нарушение сейчас |
|---|---|---|---|---|
| F1.1 | Любой RNG кроме `KernelRNG` в kernel layer | Non-deterministic replay | ADR-O-301 | `random.uniform` callsites (grep) |
| F1.2 | Прямой доступ к `scene_state` из `ProjectionEngine` | Ломает pure function | ADR-O-201 | `services/scene_state_manager.py:apply_change` |
| F1.3 | Mutation `TickContext` вне фаз | Ломает причинную цепь | Устав §3 | `phase_2_world_tick.py` — `wt_dirty` |
| F1.4 | Публикация events мимо `EventBus` | Ломает §ENIGMA-005 | Устав §2.1.1 | `phase_2_world_tick.py:105` — `shared_context.world_tick_result = _tick_result` |
| F1.5 | Non-deterministic время в pipeline | Non-deterministic replay | — | `datetime.now` в pipeline (grep) |
| F1.6 | Persistence без `atomic_commit` | Desync bug | Устав §4.2.1 | `_save_npcs()` legacy |
| F1.7 | Snapshot с live references | Non-deterministic replay | ADR-O-201 | Проверить `TickOrchestrator._init_pipeline_context` |
| F1.8 | Action execution без `CausalLedger` entry | Ломает traceability | Этот документ §2.4 | Любой `apply_*` без `cause` |
| F1.9 | Replay без causal ledger | Ломает §ENIGMA-001 | — | Replay должен читать `CausalLedger` |
| F1.10 | LLM вызовы без кэша по `(tick, npc_id, prompt_hash)` | Non-deterministic replay | — | `services/llm/` проверить кэш |

---

## §4. ADR Obligations

LLM-архитектор SHALL обновить следующий ADR-реестр после завершения Stage 0 и Stage 1.

### 4.1 ADR для упразднения (после Stage 0)

| ADR | Статус | Действие |
|---|---|---|
| ADR-118 (`state.yaml:72-78`) | ACTIVE → DEPRECATED | Упразднить после Task 0.2 (`_RUNTIME_TOP_LEVEL_KEYS` удалён) |
| ADR-117 (`state.yaml:65-71`) | ACTIVE → REVISED | `json.dumps` default handler для set — оставить, но контекст упразднённого whitelist'а убрать |

### 4.2 ADR для усиления (после Stage 0 + Stage 1)

| ADR | Статус | Действие |
|---|---|---|
| ADR-O-201 (Causal Kernel Architecture) | ACTIVE → STRENGTHENED | Добавить: `ProjectionEngine` — pure function, no service calls, no RNG, no pathfinding (см. `state.yaml:86-92`) |
| ADR-O-208 (DRP effective_drives) | ACTIVE → MIGRATED | Перенести `_compute_effective_drives` из `phase_2_world_tick.py:78-93` в `TickOrchestrator.ФАЗА_3.4` |
| ADR-O-301 (KernelRNG) | ACTIVE → STRENGTHENED | Любой RNG в kernel layer = `KernelRNG.next()`. Запретить `random.*`, `datetime.now()` |
| ADR-TZ04-2 (random.uniform → KernelRNG) | ACTIVE → VERIFIED | Проверить, что все callsites мигрировали |
| ADR-HP-UNIFICATION (body_state current_hp) | ACTIVE → CONFIRMED | `body_state["current_hp"]` — canonical. Прямых writes в `state.hp` нет ( поле удалено, см. `npc_state.py:663-665`) |
| ADR-139 (drives_runtime Single Write Authority) | ACTIVE → STRENGTHENED | `state.drives_runtime` — единственный write-path для mutation engine. `npc_dict["drives"]` — projection only (см. `npc_state.py:809-813`) |
| ADR-O-317 (LifeDirection FSM) | ACTIVE | Подтвердить: `life_project_state` ∈ {ACTIVE, COLLAPSING, LOST, SEARCHING, COMMITTED} |
| ADR-O-146 (BODY_STATE_DISABLED immutable sentinel) | ACTIVE → CONFIRMED | `dict()` копия обязательна при присвоении (см. `npc_state.py:54-58`) |

### 4.3 Новые ADR для создания

| ADR | Содержание |
|---|---|
| ADR-FOUNDATION-FREEZE (новый) | Фиксация Stage 0: единственный NPCState runtime, упразднение _RUNTIME_TOP_LEVEL_KEYS, SSOT для epistemic/social/economic |
| ADR-CAUSAL-SPINE (новый) | Фиксация Stage 1: 8-step causal chain, CausalLedger query API, provenance required, 10 000-tick replay determinism |
| ADR-WRITE-GUARD (новый) | Runtime assertion в `NPCState.__setattr__` — writer вне whitelist → `ArchitecturalViolationError` |
| ADR-ACTION-SEMANTIC-RESOLVER (новый) | Контракт `ActionSemanticResolver` (после Task 0.1 — ветка B) |

---

## §5. Risk Register — цена пропуска стадий

| # | Risk | Probability (если пропустить Stage) | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Если писать новую психику до Stage 0 — каждое новое поле требует whitelist update, иначе теряется при merge | HIGH (исторически подтверждено ADR-117/118) | HIGH — тихая потеря данных, debug занимает часы | Stage 0 Task 0.2 упраздняет whitelist |
| R2 | Если оставить `phase_2_world_tick` — каждая новая система будет копировать bypass-паттерн | MEDIUM (уже есть 1 копия — `phase_2_world_tick.py` — и комментарии SLEEP_FIX #4a/#4b там же) | HIGH — экспоненциальное расползание bypass-паттерна | Stage 0 Task 0.10 упраздняет `phase_2_world_tick.py` |
| R3 | Если multi-writer beliefs останется — каждая новая belief-источника умножает рассинхрон | HIGH (11+ writers уже) | HIGH — beliefs рассинхронизированы между системами | Stage 0 Task 0.5 + 0.6 — единственный `BeliefTransitionEngine.commit` |
| R4 | Если пропустить Stage 1 causal chain — debug будет невозможен, будут только симптомы | HIGH (см. `causal_validation.log` — 10 угроз ножом без эффекта на HP/Threat/AffLoad — symptomatic) | CRITICAL — нельзя ответить «почему NPC не отреагировал?» | Stage 1 полностью |
| R5 | Если не убрать `_avatar` прямую мутацию — economy stage будет неконсистентен | HIGH | HIGH — player money drift между `EconomyProfile.gold` и `body_state["money"]` | Stage 0 Task 0.8 |
| R6 | Если оставить compile error `action_semantic_resolver` — любая player action фича не тестируется | CERTAIN (уже падает) | CRITICAL — невозможно валидировать player-side | Stage 0 Task 0.1 — первое, что делается |
| R7 | Если LLM determinism не обеспечен — replay не работает, drift не ловится | MEDIUM | CRITICAL — replay — единственный способ верификации Stage 1 | Stage 1 Task 1.1 |
| R8 | Если `CausalLedger` неполон — traceability невозможна, causal chain обрывается | HIGH (без Task 1.2 — нет provenance) | CRITICAL — нельзя построить 8-step chain | Stage 1 Task 1.2 + 1.4 |
| R9 | Если `WorldSnapshot` имеет live references — non-deterministic replay | MEDIUM (требует верификации) | CRITICAL — replay diff > 0 | Stage 1 Task 1.3 |
| R10 | Если persistence идёт через 3 JSON файла — desync bug | MEDIUM (после Stage 0 упраздняется `_save_npcs`) | HIGH — corruption | Stage 0 Task 0.3 + Stage 1 Task 1.7 |

---

## §6. Порядок выполнения (constraint graph)

Задачи имеют зависимости. LLM-архитектор SHALL выполнять в следующем порядке (или доказать эквивалентность альтернативного порядка):

```
Stage 0:
  Task 0.1 (compile fix)          ← FIRST, ничего нельзя делать пока игра падает
    ↓
  Task 0.2 (single NPCState)      ← фундамент для всех остальных Stage 0 tasks
    ↓
  Task 0.4 (layer separation)     ← зависит от 0.2
  Task 0.9 (write guards)         ← зависит от 0.2, 0.4
    ↓
  Task 0.5 (belief writers)        ← зависит от 0.9
  Task 0.6 (BeliefTransitionEngine SSOT) ← зависит от 0.5
  Task 0.7 (RelationshipStore SSOT)     ← зависит от 0.9
  Task 0.8 (Economy SSOT)         ← зависит от 0.9
    ↓
  Task 0.10 (упразднить phase_2_world_tick) ← зависит от 0.2, 0.6, 0.7, 0.8
    ↓
  Task 0.3 (JSON = persistence only) ← последний в Stage 0 (финальная блокировка legacy)

Stage 1 (после полного завершения Stage 0):
  Task 1.3 (Snapshots)            ← FIRST в Stage 1, фундамент для replay
    ↓
  Task 1.2 (Provenance)           ← зависит от 1.3 (snapshot = input)
    ↓
  Task 1.4 (CausalLedger)         ← зависит от 1.2
  Task 1.1 (Deterministic replay) ← зависит от 1.3, 1.2, 1.4
    ↓
  Task 1.5 (Event visibility)     ← независимо, но требует 1.2 для observation provenance
  Task 1.6 (Action execution)     ← зависит от 1.2, 1.4
  Task 1.7 (atomic_commit)        ← зависит от Stage 0 Task 0.3
    ↓
  Stage 1 DoD: 10 000-tick replay + causal chain reconstruction
```

**Жёсткие запреты на параллелизм:**

- Task 0.1 НЕ может быть параллелен ничему — пока compile error не устранён, любая другая работа unverifiable.
- Task 0.2 НЕ может быть параллелен Task 0.10 — упразднение `phase_2_world_tick.py` требует сначала упразднения dict↔dataclass roundtrip.
- Stage 1 НЕ может начаться до полного завершения Stage 0 (все I0.* invariants pass).

---

## §7. Контракт взаимодействия с заказчиком

LLM-архитектор SHALL:

1. Перед началом каждой задачи — `grep` callsites и `read` указанных файлов для верификации.
2. После каждой задачи — commit с сообщением `Stage 0 Task 0.X: <one-line summary> (refs §1.X)`.
3. При обнаружении противоречия между этим ТЗ и Уставом — Устав выигрывает; LLM-архитектор MUST сообщить о противоречии в PR-описании.
4. При обнаружении, что задача требует введения нового примитива — STOP, применить §ENIGMA-002 (Two-Domain Rule): сначала локальное лекарство для доказанного бага, потом поиск второго домена, только потом генерализация.
5. При обнаружении, что задача требует расширения `NPCState` — STOP, применить §0.5 (стоимость откладывания): каждое новое поле без domain ownership = +1 к будущей стоимости переделки.
6. Любой коммит, ломающий инвариант из §1.13 или §2.10 — откатывается автоматически (CI должен это проверять).

---

## §8. Что НЕ делать (финальный манифест)

Список того, что LLM-архитектор **не имеет права делать** в Stage 0 и Stage 1 (даже если кажется «быстрым фиксом»):

1. ❌ НЕ расширять `_RUNTIME_TOP_LEVEL_KEYS` whitelist для починки потери поля.
2. ❌ НЕ добавлять новый writer в `state.beliefs` вне `BeliefTransitionEngine`.
3. ❌ НЕ вводить новый tick-path мимо `TickOrchestrator`.
4. ❌ НЕ мутировать `tick_ctx.all_npcs_raw` напрямую вне persistence layer.
5. ❌ НЕ мутировать `_avatar.body_state` напрямую вне `StateApplicator`.
6. ❌ НЕ использовать `JsonPersistenceAdapter` в runtime-path.
7. ❌ НЕ использовать `random.*` или `datetime.now()` в kernel layer.
8. ❌ НЕ публиковать events мимо `EventBus` (например, через `shared_context.world_tick_result = ...`).
9. ❌ НЕ применять state changes без `cause: Cause` параметра.
10. ❌ НЕ добавлять новые поля в `NPCState` без:
    - domain ownership (ровно один writer)
    - ADR-обоснования (почему поле нужно именно сейчас, а не в Stage 2)
    - записи в ownership-таблицу (§1.6)
11. ❌ НЕ строить новую психику (эмоции, self-model, мотивация, культура, секс) до завершения Stage 0.
12. ❌ НЕ вводить новые фундаментальные примитивы без §ENIGMA-002 (Two-Domain Rule).
13. ❌ НЕ делать «быстрый фикс» через if/else в обходе уже принятых ADR — это закрепление долга.
14. ❌ НЕ оставлять `# TODO`, `# FIXME`, `# HACK` комментарии в production коде после Stage 0.
15. ❌ НЕ вводить новые cache-поля в `NPCState` без SSOT для оригинальных данных.

---

**Документ закончен.** Stage 0 и Stage 1 описаны. Stop-list консолидирован в §3. ADR obligations — в §4. Риски — в §5. Порядок выполнения — в §6. Манифест «не делать» — в §8.

LLM-архитектор SHALL начать с `Task 0.1` (§1.3) — compile fix. До его устранения любой другой код unverifiable.
