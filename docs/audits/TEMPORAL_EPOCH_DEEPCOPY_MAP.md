# TEMPORAL EPOCH DEEPCOPY MAP
> S266 · Этап 1 · Карта горячих deepcopy-сайтов для миграции на Epoch/Overlay.
> Каждый сайт классифицирован по A-E: (A) temporal isolation необходима,
> (B) защита от legacy direct mutation, (C) избыточен из-за DeltaBuffer,
> (D) projection/debug/test, (E) рудимент.
> Источник вербатимов: S265-S266 сессии (все строки прочитаны с диска).

## Сайт 1 — pipeline_runner.py:59-80 (build_tick_state) — ГЛАВНЫЙ

**Файл:** `backend/app/services/pipeline_runner.py`
**Строки:** 59-80 (9 deepcopy в одном вызове)
**Частота:** 1×/тик × 1 вызов

| # | Что копируется | Зачем (S-143 FIX) | Кто читает | Кто пишет | Класс |
|---|---|---|---|---|---|
| 1 | `ctx.scene_state` | TickState mutation | NpcTickPipeline.run() (все NPC) | Никто напрямую — дельты через TickMutation | **C** — избыточен |
| 2 | `alive_npcs` | То же | Pipeline loop, DecisionHub через state_l2 | `_npc_dict_for_write` (уже отдельная копия!) | **C** — дубль |
| 3 | `ctx.all_npcs_raw` (nearby_npcs) | То же | SocialTargetResolver | Никто | **E** — рудимент |
| 4 | `memory_weights_map` | S-143 | DecisionHub compute | Никто (read-only) | **C** |
| 5 | `narrative_cache_map` | S-143 | VerbalizationContext | Никто | **C** |
| 6 | `social_modifiers_map` | S-143 | DecisionHub | Никто | **C** |
| 7 | `reputation_modifiers_map` | S-143 | DecisionHub | Никто | **C** |
| 8 | `economic_profiles_map` | S-143 | DecisionHub, compute_economy | Никто (read-only) | **C** |
| 9 | `crystallized_beliefs_map` | S-143 | DecisionHub | Никто | **C** |
| 10 | `identity_traits_map` | S-143 | DecisionHub | Никто | **C** |

**Вердикт:** 10 копий, из них **0 класса A** — все защищают от S-143 (исторический фикс до эпохи DeltaBuffer). NpcTickPipeline.run() — pure reducer (ADR-TZ10-1, доказано INV-хешем: before==after на 99% тиков). Мутации идут через `_npc_dict_for_write` (Сайты 2-4) и `TickMutation` → `StateApplicator`.

**Epoch-замена:** `scene_state=WorldView(epoch)` — ноль копий; `alive_npcs`/`nearby_npcs` — ссылка на frozen list; maps — frozen (проекция, не состояние).

---

## Сайт 2 — npc_tick_pipeline.py:243 (per-NPC сцена для tick_conditions)

**Строка:** `scene_state=copy.deepcopy(state.scene_state)` внутри цикла по NPC
**Частота:** 6×/тик (по NPC)
**Зачем:** tick_conditions читает сцену, боясь мутации от других NPC
**Кто пишет:** НИКТО в этом контексте — tick_conditions — чистый читатель
**Класс:** **C** — Сайта 1 уже скопировал сцену! Это копия копии.

**Epoch-замена:** удалить — передать `state.scene_state` напрямую (уже isolated Сайтом 1 → после Epoch — WorldView).

---

## Сайт 3 — npc_tick_pipeline.py:170, 225, 230 (load_l2 + resolve_physical_attack)

**Строки:**
- `:170` — `copy.deepcopy(dict(npc))` для state_l2
- `:225` — `_npc_dict_for_write = copy.deepcopy(dict(_npc_profile))` — ЕДИНСТВЕННЫЙ ЛЕГАЛЬНЫЙ ПИСАТЕЛЬ
- `:230` — state_l2 (уже удалён двойной в S265)

**Частота:** 6×/тик × 2
**Зачем:** `:170` — легаси (state_l2 теперь из `_npc_dict_for_write`); `:225` — ИЗОЛЯЦИЯ ПИСАТЕЛЯ (NPC мутирует свой словарь, мир не видит)
**Класс:** `:170` — **E** (рудимент, state_l2 перезаписывается на :225); `:225` — **A** (необходим: это КАНАЛ мутации NPC)

**Epoch-замена:** `:170` удалить (мёртвый код); `:225` заменить на `TickOverlay(npc_id)` — пишет в delta, читает epoch.

---

## Сайт 4 — npc_tick_pipeline.py:750, 763, 815 (per-NPC сцена для интерпретации/вербализации)

**Частота:** до 6×/тик × 3
**Зачем:** InterpretationEngine, VerbalizationContext, build_verbalization_context читают сцену
**Кто пишет:** Никто — чистые читатели
**Класс:** **C** × 3 — копии копии копии

**Epoch-замена:** WorldView(Epoch) — ноль копий.

---

## Сайт 5 — scene_state_manager.py:1636-1638 (commit)

**Строки:**
```python
self._tick_scenes[_loc_id] = copy.deepcopy(scene_state)
self._last_committed_npcs = copy.deepcopy(npc_dicts or [])
```
**Частота:** 1×/тик
**Зачем:** SSM — SSOT state_t-1; WorldProjectionBuffer читает committed
**Класс:** **A** — НЕОБХОДИМ (это и есть граница эпохи!)

**Epoch-замена:** `self._epoch = Epoch(scene_state, epoch_id)` — не копия, а ЗАКРЕПЛЕНИЕ: вход становится immutable, вызывающий больше не трогает (move-semantics). Deepcopy здесь защищал от ПОСЛЕДУЮЩЕЙ мутации scene_state после commit — Epoch решает это by construction.

---

## Сайт 6 — scene_state_manager.py:328 (commit_tick_result)

**Частота:** 1×/тик
**Зачем:** дубль Сайта 5 (commit вызывается дважды: Phase 10 + unlock_tick)
**Класс:** **E** — рудимент (одна из двух копий лишняя — INV-COMMIT-CARDINALITY уже поймал это)

---

## Сайт 7 — tick_orchestrator.py:404 (create_tick_context × 2 → 1 после S265-фикса)

**Строка:** `input_snapshot = copy.deepcopy(scene_state)` в create_tick_context
**Частота:** 1×/тик (после time-ctx фикса)
**Зачем:** S83.1 «Tick = Pure Function Evaluation. Freeze input snapshot»
**Класс:** **A** — ТЕОРЕТИЧЕСКИ правилен (это и есть Epoch-граница!), но реализован как deepcopy вместо immutability

**Epoch-замена:** `input_snapshot = epoch.view()` — снапшот = ссылка на уже-immutable epoch.

---

## Сводная таблица

| Сайт | Файл | Копий/тик | Класс | Действие |
|---|---|---|---|---|
| 1 | pipeline_runner:59-80 | 10 | C×10 | Удалить все → WorldView |
| 2 | npc_tick_pipeline:243 | 6 | C | Удалить → передать scene_state |
| 3a | npc_tick_pipeline:170 | 6 | E | Удалить (мёртвый) |
| 3b | npc_tick_pipeline:225 | 6 | **A** | TickOverlay (единственный писатель) |
| 4 | npc_tick_pipeline:750,763,815 | до 18 | C×3 | Удалить → WorldView |
| 5 | scene_state_manager:1636 | 1 | **A** | Epoch (move, не copy) |
| 6 | scene_state_manager:328 | 1 | E | Удалить (дубль) |
| 7 | tick_orchestrator:404 | 1 | **A** | epoch.view() (ссылка) |
| **ИТОГО** | | **~35-49** | 3A, 32C/E, 12C | |

**Из ~35-49 копий/тик: только 3 — класс A (необходимы), 1 — писатель (3b), остальные — избыточны или рудимент.**

---

## Миграционный порядок (по горячности)

```text
PR-1: Сайт 1 (10 копий, ~30% стоимости) → WorldView + frozen maps
PR-2: Сайт 4 (до 18 копий, ~25%) → WorldView для интерпретации
PR-3: Сайт 2 (6 копий, ~10%) → прямая передача
PR-4: Сайты 5+6+7 (3 копии, ~8%) → Epoch-граница + move-semantics
PR-5: Сайт 3b (6 копий, ~8%) → TickOverlay
PR-6: Сайт 3a (6 копий, мёртвый) → удалить
```

Каждый PR: `Contract D + IPT + INV-TEMPORAL-ISOLATION + EAT/WORK/SOCIAL + benchmark`.

---

## Что доказывает INV-хеш (уже работающий)

На 99% тиков: `hash(TickState) BEFORE == hash(TickState) AFTER` pipeline.
Это означает: **редьюсер уже не мутирует вход.** 32 из 35 копий защищают от угрозы, которой нет. S-143-фикс был написан, когда pipeline МУТИРОВАЛ (ADR-O-346: «StateApplicator удалён из Pipeline»). После ADR-O-346 deepcopy стал бронёй против призрака.