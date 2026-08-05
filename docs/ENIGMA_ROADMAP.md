# ENIGMA — Дорожная карта преемника

**Версия документа:** 1.0 · 2026-08-05
**Адресат:** LLM-преемник на V.0.5.3.7.0
**Назначение:** Пошаговый план — что делать, в каком порядке, что читать, что формулировать самому.
**Принцип документа:** компактный, без воды; галочки `[ ]` — для трекинга; путь к файлу — для каждого шага.

---

## 0. Контекст: где мы сейчас

**Текущая эпоха:** **Эпоха 6 — Stabilization & Infrastructure** (переходная).
**Версия кода:** V.0.5.3.7.0 · `version.txt` = `0.5.3.6.10` (desync — баг).
**Главный ТЗ:** `ENIGMA_TZ_V0.5.3.7.0.md` — это **defect-fix документ**, не feature roadmap. В нём **57 активных дефектов**: 15 Critical / 13 High / 16 Medium / 13 Low.

### 5 player-visible симптомов (топ-приоритет на сейчас)

| # | Симптом | Bug ID |
|---|---------|--------|
| 1 | NPC молчит, не отвечает игроку | `REGRESSION-CORE-001` |
| 2 | MVP popup не показывается | `NEW-MVP-001` |
| 3 | Игрок не двигается на координатах (0,0) | `NEW-CORE-001` |
| 4 | Continue flow race condition | `NEW-CORE-002` |
| 5 | LLM error masking (router глушит исключения) | `NEW-DLG-004` |

### 3 unresolved TODOs из последней DM-сессии (S62)

- **#6** NPC position = `"bed"` вместо текущего node (stale schedule → визуальная телепортация)
- **#7** `movement_intents` не доходят до `DMFrame` → DM-агент не видит, что NPC что-то делает (false negative)
- **#8** `all_npcs_raw_snapshot` периодически пропадает (`_anr=NONE` на некоторых тиках)

### 5 архитектурных истин (усвоить перед любым шагом)

1. **Truth = Snapshot + Chronicle.** State эфемерен, Identity — append-only. Это асимметричная онтология, не баг.
2. **Time & Physics — одно.** Разрешаются только в Causal Kernel.
3. **No Event Sourcing for State, но yes for Identity.** State — snapshot, Identity — L1Chronicle (SQLite append-only).
4. **Symptom ≠ Cause.** Чини pipeline node, не UI. UI-симптом = проекция поломки ниже по стеку.
5. **Vacuum = local rupture, not global zero.** Unknown ≠ Neutral 0.0. Отсутствие факта ≠ нулевая уверенность.

### Принципы работы

- Один фикс → один коммит → один тест. Не пачками.
- CI-гейты обязательны. `ruff` + `pytest backend/tests/IPT.py` перед коммитом.
- Observability **never mutates**. Диагностика читает, не пишет.
- DNA-метрики могут врать — перепроверяй через `backend/data/logs/scene_changes_*.jsonl`.
- `MockProvider` в production-пути запрещён.
- `random.*` и `time.time()` в kernel-слое запрещены → только `KernelRNG(tick, npc_id, salt)`.

Вот последовательность файлов ТЗ к исполнению (только шапки):

1. `ENIGMA_TZ_V0.5.3.7.0.md` — главное defect-fix ТЗ (закрыть 57 дефектов)
2. `docs/Почти Актуальные TZ/RemontTZ/ENIGMA_TZ_ISPRAVLENIE.md` — мастер-ТЗ на ремонт
3. `docs/Почти Актуальные TZ/RemontTZ/domain_core.md`
4. `docs/Почти Актуальные TZ/RemontTZ/domain_spatial.md`
5. `docs/Почти Актуальные TZ/RemontTZ/domain_dialogue.md`
6. `docs/Почти Актуальные TZ/RemontTZ/domain_perception.md`
7. `docs/Почти Актуальные TZ/RemontTZ/domain_frontend.md`
8. **Movement Engine — усиление** (нет ТЗ; head_yaw offset, LERP, SC-2..SC-8 probes)
9. **Dialogue Openers** (нет ТЗ; ActionType.DIALOGUE, noun-anchored parsing, multi-intent)
10. `docs/Почти Актуальные TZ/ENIGMA_TZ_INFRASTRUCTURE.md` — PBT, Replay, Causal Probes, ADR-Net
11. `docs/Почти Актуальные TZ/ENIGMA_SELF_HEALING_SYSTEM.md`
12. `docs/Почти Актуальные TZ/ENIGMA_LLM_PIPELINE_TZ_v1.md` — semantic cache, grammar-constrained JSON
13. **DRI-метрика** (нет ТЗ; Dialogue Response Integrity)
14. **Audit Log LLM-вызовов** (нет ТЗ; provenance chain)
15. **Social Belief Layer / ToM** (нет ТЗ; 4D CrystallizedBelief + second-order BELIEVES)
16. **Belief Merger** (нет ТЗ; разрешение конфликтов writer'ов в BeliefState)
17. `docs/Почти Актуальные TZ/VZ/TZ_§19_Predictive_Perception_Dynamics.md` — Prophecy math
18. **Prophecy System** (в ADR-O-330, не отдельным ТЗ) — player asserts future → L2.5 crystallizes
19. **Vertical Slice «Люся и 3 парня»** (нет ТЗ; демо-кампания для проверки Эпохи 7)
20. `docs/Почти Актуальные TZ/VZ/ТЕХЗАДАНИЕ ПРЕЕМНИКУ TZ-02 V.2.0` — WorldChronicle, 3 уровня времени
21. `docs/Почти Актуальные TZ/VZ/TZ_MEMETIC_01_Domain_Spec.md` — Memetic Domain онтология
22. `docs/Почти Актуальные TZ/VZ/TZ_MEMETIC_02_Content_Policy_Integration.md`
23. `docs/Почти Актуальные TZ/VZ/TZ_MEMETIC_03_Patch_List.md` — 12 точек правки + 8 файлов
24. **Factions system** (нет ТЗ; Эпоха 9)
25. **Economy layer** (есть `architecture/economy.yaml`, нет инженерного ТЗ; Эпоха 9)
26. **Politics** (нет ТЗ; Эпоха 9)
27. `docs/Почти Актуальные TZ/VZ/TZ_§18_Resource_Bounded_Epistemic_Selection_Law.md` — формула `U_M = I·R·U − C` (Эпоха 10, **после** Belief Layer)
28. `docs/Почти Актуальные TZ/ENIGMA_MAP_EDITOR_SMART_VALIDATION.md` — BedRegistry, auto-cut стен
29. `docs/Почти Актуальные TZ/VZ/TEXTURES_AND_GEOMETRY_TZ.md` — 2D composite, 128×128 portraits, aging
30. `docs/Почти Актуальные TZ/S1_INPUT_TRACE_IMPLEMENTATION.md` + `INPUT_OBSERVATORY_ROADMAP_S2_S6.md`
31. `docs/Почти Актуальные TZ/ENIGMA_TZ_Female_Targeted_Dark_Fantasy_Layer.pdf` — романтика/драма/gothic
32. `docs/Почти Актуальные TZ/AWC_Process_World_Model_TZ.pdf` — Эпоха 11+, только дизайн

⚠️ **Особая отметка:** IPT-LEM ТЗ в архиве не найден — уточните, существует ли он как отдельный документ.

---

## 1. Что ОБЯЗАТЕЛЬНО прочитать (P0-P5)

> Путь к корню проекта: `/home/z/my-project/work/enigma/Enigma-V.0.5.3.7.0_-_-/`

### P0 — Прямо сейчас, перед любым шагом

- [ ] `upload/ENIGMA_TZ_V0.5.3.7.0.md` (858 строк) — **главный defect-fix ТЗ**. §3 баг-каталог по доменам, §4 приоритетный план фиксов.
- [ ] `docs/ENIGMA_EPOCHS_REPORT.md` (849 строк) — карта Эпох 1-10, где завершено, где мы сейчас, куда идём. **Источник истины по прогрессу.**
- [ ] `reports/LAST_SESSION.md` — последняя сессия: DNA-метрики, что работало, что нет. Movement Traversal = ❌ для всех 6 NPC — главный затык.
- [ ] `reports/SESSION_S62_DM_VISION.md` — 5 решённых вопросов по слепоте DM-агента + 3 TODO.

### P1 — Перед Фазой 0 (стабилизация)

- [ ] `docs/Почти Актуальные TZ/RemontTZ/ENIGMA_TZ_ISPRAVLENIE.md` (1713 строк) — мастер-ТЗ на ремонт.
- [ ] `docs/Почти Актуальные TZ/RemontTZ/domain_core.md` — домен CORE.
- [ ] `docs/Почти Актуальные TZ/RemontTZ/domain_dialogue.md` — домен Dialogue/LLM.
- [ ] `docs/Почти Актуальные TZ/RemontTZ/domain_spatial.md` — домен Spatial/Movement.
- [ ] `docs/Почти Актуальные TZ/RemontTZ/domain_frontend.md` — домен MVP/Frontend.
- [ ] `docs/Почти Актуальные TZ/RemontTZ/domain_perception.md` — домен Perception.

### P2 — Перед Фазами 2-5 (Эпохи 7-10) — папка `VZ/`

- [ ] `docs/Почти Актуальные TZ/VZ/TZ_§19_Predictive_Perception_Dynamics.md` (2835 строк) — математика Prophecy, `z_t = F(z_{t-1}, x_t)`, `surprise = −log P(x_t|z_{t-1})`. **Эпоха 7.**
- [ ] `docs/Почти Актуальные TZ/VZ/TZ_§18_Resource_Bounded_Epistemic_Selection_Law.md` (1542 строки) — формула `U_M = I·R·U − C`. **ВНЕДРЯТЬ НЕЛЬЗЯ до Belief Layer. Эпоха 10.**
- [ ] `docs/Почти Актуальные TZ/VZ/ТЕХЗАДАНИЕ ПРЕЕМНИКУ TZ-02 V.2.0 — Каузальная петля и Иммунная система.md` — WorldChronicle, 3 уровня времени. **Эпоха 8.**
- [ ] `docs/Почти Актуальные TZ/VZ/TZ_MEMETIC_01_Domain_Spec.md` (1994 строки) — Memetic Domain: Concept → Expression → Adoption → Norm → Extinction.
- [ ] `docs/Почти Актуальные TZ/VZ/TZ_MEMETIC_02_Content_Policy_Integration.md` (1770 строк) — клей Memetic ↔ Content Policy, per-NPC ContentProfile.
- [ ] `docs/Почти Актуальные TZ/VZ/TZ_MEMETIC_03_Patch_List.md` (1387 строк) — 12 точек правки + 8 новых файлов. Engineering-мост.
- [ ] `docs/Почти Актуальные TZ/VZ/TEXTURES_AND_GEOMETRY_TZ.md` (539 строк) — 2D composite model, 128×128 portraits, aging. **Post-MVP.**

### P3 — Перед Фазой 1 (Infrastructure)

- [ ] `docs/Почти Актуальные TZ/ENIGMA_TZ_INFRASTRUCTURE.md` (1075 строк) — PBT, Replay System, Causal Probes, ADR-Net. **Главный источник Эпохи 6.**
- [ ] `docs/Почти Актуальные TZ/ENIGMA_SELF_HEALING_SYSTEM.md` (1790 строк) — Self-healing L0-L2.
- [ ] `docs/Почти Актуальные TZ/ENIGMA_LLM_PIPELINE_TZ_v1.md` (4993 строки) — semantic cache (BGE-small-ru + FAISS), grammar-constrained JSON, P50<2.5s.
- [ ] `docs/Почти Актуальные TZ/ENIGMA_TZ_ISPRAVLENIE_1.md` (1165 строк) — предыдущий раунд фиксов.

### P4 — Перед затрагиванием конкретных подсистем

- [ ] `docs/audits/ADR-O-305_*.md`, `ADR-O-306_*.md`, `ADR-O-307_*.md` — **Belief Crystallization Layer** (L2.5).
- [ ] `docs/audits/ADR-O-324_*.md`, `ADR-O-329_*.md`, `ADR-S90.1_*.md`, `ADR-S91_*.md` — **Movement Engine / Traversal**.
- [ ] `docs/audits/ADR-DM-001_IMPACT.md` — DM-agent контракт.
- [ ] `docs/audits/ADR-O-201_*.md` — Causal Kernel Architecture.
- [ ] `docs/audits/ADR-O-205_*.md` — Projection Layer (5-layer perception).
- [ ] `docs/audits/ADR-O-206_Emotional Residue Isolation Protocol.md`.
- [ ] `docs/audits/209-210-211-212_ПОЛНАЯ АРХИТЕКТУРА СОЦИАЛЬНОЙ ФИЗИКИ ENIGMA.md` — master.
- [ ] `docs/audits/ADR-PRE-FLIGHT CHECKLIST.md` — pre-flight перед запуском.

### P5 — По мере надобности (post-MVP)

- [ ] `docs/Почти Актуальные TZ/ENIGMA_TZ_Female_Targeted_Dark_Fantasy_Layer.pdf` (113 стр.) — романтика/драма/gothic, 6 доменов.
- [ ] `docs/Почти Актуальные TZ/AWC_Process_World_Model_TZ.pdf` — Process/WorldGraph/NPCKnowledge. Эпоха 11+, **не реализован**.
- [ ] `docs/Почти Актуальные TZ/ENIGMA_MAP_EDITOR_SMART_VALIDATION.md` — BedRegistry, auto-cut стен.
- [ ] `docs/Почти Актуальные TZ/S1_INPUT_TRACE_IMPLEMENTATION.md` + `INPUT_OBSERVATORY_ROADMAP_S2_S6.md`.

### ⚠️ Особая отметка: IPT-LEM ТЗ

**IPT-LEM ТЗ в архиве НЕ НАЙДЕН.** Поиск по `docs/Почти Актуальные TZ/VZ/` и всей папке `docs/` не дал результата. Ближайший артефакт — `backend/tests/IPT.py` (Invariant Probe Tests, упоминается в `LAST_SESSION.md`). Если пользователь ожидает отдельный документ «IPT-LEM», он либо назван иначе, либо не существует как файл. **Уточнить у пользователя.**

---

## 2. Что НЕТ в ТЗ — сформулировать самому

Эти 6 концептов **отсутствуют как самостоятельные ТЗ** и разбросаны по ADR/коду. Их надо собрать в связные документы и реализовать.

### 2.1 ToM / Social Belief Layer (Theory of Mind)

**Что:** Целевая 4-мерная модель `CrystallizedBelief(subject × target × predicate × polarity)` + second-order predicate `BELIEVES` (NPC верит, что другой NPC верит X).
**Зачем:** Без этого Prophecy (Эпоха 7) и Lineage (Эпоха 8) не работают — они строятся поверх социального моделирования. Текущий `PlayerBeliefModel` ≠ NPC ToM.
**Где править:** `backend/app/cognition/belief_crystallization_engine.py`, `crystallized_belief_store.py`. Референс: ADR-O-305/306/307.
**Когда делать:** На стыке Фазы 1 → Фазы 2 (параллельно с Prophecy).

### 2.2 Belief Merger

**Что:** Разрешение конфликта двух writer'ов в `BeliefState` (NPC сам наблюдал X, но другой NPC сообщил Y). Стратегия: source-weighted merge с учётом доверия к источнику (ToldBy NPC) и recency.
**Зачем:** Без Merger любые мемы (Эпоха 8) и Prophecy (Эпоха 7) будут перезатирать фактологию без конфликта — потеря эпистемической честности.
**Где править:** рядом с `belief_crystallization_engine.py`, новый модуль `belief_merger.py`.
**Когда:** Сразу после 2.1.

### 2.3 Усиление Movement Engine

**Что:** `head_yaw` как offset (NPC смотрит в сторону от направления движения); `PerceptionOrientationSystem` (модуль восприятия зависит от gaze direction); LERP-сглаживание; probes SC-2..SC-8 (Spatial Coherence Field probes, 7 штук).
**Зачем:** Сейчас `Movement Traversal = ❌ для всех 6 NPC` (LAST_SESSION). Без этого NPC визуально телепортируются и не видят игрока.
**Где править:** `local_traversal_planner.py`, `geometry_kernel.py`, `traversability_evaluator.py`, `motion_pipeline.py`. Референс: ADR-O-324, ADR-O-329, ADR-S90.1, ADR-S91.
**Когда:** **Фаза 0** — это критический затык прямо сейчас.

### 2.4 Dialogue Openers

**Что:** `ActionType.DIALOGUE` как first-class action; noun-anchored parsing (NPC открывает диалог упоминая предмет); negation handling; multi-intent (NPC говорит про X и Y одновременно); context-anchored (диалог отталкивается от последнего наблюдения).
**Зачем:** Сейчас NPC молчит (`REGRESSION-CORE-001`). Dialogue Executor валидируется, но openers нет — DM-агент не получает инициативы от NPC.
**Где править:** `backend/app/dialogue/` + `domain_dialogue.md` (RemontTZ). Референс: тесты `test_dialogue_executor_validation.py`, `test_dialogue_context_and_target.py`.
**Когда:** **Фаза 0** — после REGRESSION-CORE-001.

### 2.5 DRI-метрика (Dialogue Response Integrity)

**Что:** Метрика целостности ответа диалога: (1) NPC не противоречит себе в одном тике, (2) NPC не нарушает Epistemic Boundary (не выдаёт hidden state), (3) ответ соответствует выбранному intent, (4) ManifestationDTO tags-consistent с utterance.
**Зачем:** DNA-метрики (SHI/NPI/SCF) не покрывают диалоговый слой — там黑洞. Без DRI регрессии в LLM-ответах невидимы.
**Где править:** новый модуль в `diagnostics/` рядом с `dna_metrics.py`. Подключить в `diagnostics/health_checkers/`.
**Когда:** **Фаза 1** (Infrastructure).

### 2.6 Audit Log LLM-вызовов

**Что:** Provenance chain — для каждого LLM-вызова: `tick_id, npc_id, prompt_hash, response_hash, model, latency, cache_hit, intent_before, intent_after`. Хранится append-only.
**Зачем:** Replay System (Эпоха 6) требует deterministic LLM path. Без audit log нельзя отладить «почему NPC сказал X на тике N». Сейчас видно только через `cds_session_*.log`, что неудобно.
**Где править:** новый `backend/app/llm/audit_log.py` + интеграция в `dm_agent.py` / `dialogue_router.py`.
**Когда:** **Фаза 1** (Infrastructure), параллельно с Replay System.

---

## 3. Граф зависимостей

```
REGRESSION-CORE-001 (task_scheduler)
    ↓ блокирует всё остальное в DOM-CORE
NEW-CORE-001 (movement at 0,0) ─┐
NEW-DLG-004 (LLM masking)  ────┤── Фаза 0 (стабилизация)
NEW-MVP-001 (popup)         ──┘
    ↓
Movement Engine усиление (SC-2..SC-8)
    ↓
Dialogue Openers ───── DRI-метрика ── Audit Log
    ↓                    ↓              ↓
    └──────── Фаза 1: Infrastructure (PBT, Replay, Causal Probes, ADR-Net, Self-Healing, LLM Pipeline v1) ────────┘
                            ↓
                ToM / Social Belief Layer (4D CrystallizedBelief + BELIEVES)
                            ↓
                    Belief Merger
                            ↓
        ┌──────── Фаза 2: Эпоха 7 — Prophecy (§19) + Vertical Slice «Люся и 3 парня» ────────┐
        ↓                                                                                   ↓
        WorldChronicle (TZ-02) ──── 3 уровня времени ──── Memetic Domain (TZ_MEMETIC_01-03)
                            ↓
                ┌─── Фаза 3: Эпоха 8 — Generational Depth ───┐
                ↓                                            ↓
                Factions + Economy + Politics (Эпоха 9)
                            ↓
                Belief Layer MVP complete
                            ↓
                Фаза 5: §18 (U_M = I·R·U − C) — Эпоха 10
                            ↓
                Post-MVP: Female Targeted Layer / Textures / Map Editor Smart Validation / AWC
```

**Жёсткое правило:** §18 внедрять **нельзя** до завершения Belief Layer. §19 внедрять **нельзя** до Prophecy Causality Law (ADR-O-330) green.

---

## 4. ФАЗА 0 — Стабилизация (закрыть 57 дефектов V0.5.3.7.0)

**Цель:** SHI=100%, 0 Critical багов, canary `backend/tests/canary/test_full_playthrough.py` green, Movement Traversal = ✅ для всех NPC.
**Источник ТЗ:** `ENIGMA_TZ_V0.5.3.7.0.md` §3 (баг-каталог) + §4 (приоритетный план).
**Параллельность:** Шаги 0.1-0.5 можно делать параллельно после 0.0; 0.6 и 0.7 — после 0.1.

### Чек-лист

- [ ] **0.0** Фикс version desync: `version.txt` (`0.5.3.6.10`) → `0.5.3.7.0`; проверить `frontend/constants.py`. **Почему сейчас:** без этого любой релиз-артефакт врёт о версии.
- [ ] **0.1** `REGRESSION-CORE-001` — вернуть `task_scheduler` вызов в `tick_orchestrator.execute()`. **Файлы:** `backend/app/core/tick_orchestrator.py`, `backend/app/core/task_scheduler.py`. **Почему первым:** без этого NPC молчит — любой другой фикс невидим.
- [ ] **0.2** `REGRESSION-CORE-002` — `TICK_COMPLETED` payload должен быть JSON-serializable. Проверить `pydantic`-модели в `pipeline_context.py`. **Почему сейчас:** нарушает Epistemic Boundary contract L16.
- [ ] **0.3** `NEW-CORE-001` — игрок не двигается на координатах (0,0). Проверить `SpatialFactory`, `TraversalState`, `MovementIntent`. **Файлы:** `backend/app/spatial/`. **Почему:** player-visible симптом #3.
- [ ] **0.4** `NEW-CORE-002` — Continue flow race condition. Состояние между тиками неконсистентно. **Файлы:** `backend/app/core/tick_orchestrator.py`, `state_applicator.py`, `delta_buffer.py`.
- [ ] **0.5** `NEW-DLG-004` — LLM error masking. `dialogue_router` глушит исключения. **Файлы:** `backend/app/dialogue/dialogue_router.py`. **Почему:** скрывает реальные LLM-провалы.
- [ ] **0.6** `NEW-MVP-001` — MVP popup. **Файлы:** `frontend/` (MvpTavernController), `TruthState`. **Почему:** player-visible симптом #2.
- [ ] **0.7** Усиление Movement Engine (см. §2.3): `head_yaw` offset, LERP, SC-2..SC-8 probes. **Файлы:** `local_traversal_planner.py`, `geometry_kernel.py`, `traversability_evaluator.py`, `motion_pipeline.py`. **Почему:** Movement Traversal ❌ для всех 6 NPC — критический затык.
- [ ] **0.8** DM-VISION TODO #6: NPC position = `"bed"` → брать current node из schedule. **Файлы:** `backend/app/core/calendar.py`, `schedule`-модуль.
- [ ] **0.9** DM-VISION TODO #7: `movement_intents` → `DMFrame`. **Файлы:** `backend/app/dm_agent.py`, `pipeline_context.py`.
- [ ] **0.10** DM-VISION TODO #8: `all_npcs_raw_snapshot` стабилен между тиками. **Файлы:** `pipeline_context.py`, `shared_context.py`.
- [ ] **0.11** `BUG-CORE-013/015/016/017/020-026` — пройти по списку из §3.1 главного ТЗ.
- [ ] **0.12** `NEW-DLG-001..008` + `BUG-DLG-043/044` + `BUG-DLG-CAUSAL-4.7.48/4.7.49` — §3.2 главного ТЗ.
- [ ] **0.13** `NEW-ORIENT-004`, `BUG-FB-029` — §3.4 / §3.3.
- [ ] **0.14** Прогнать `backend/tests/canary/test_full_playthrough.py` — должен быть green.
- [ ] **0.15** Проверить DNA-метрики: SHI=100%, NPI=100%, SCF=1.0, PFI=0%, ADR ≤ порог.

### Гейты для перехода к Фазе 1

- [ ] 0 Critical багов из `ENIGMA_TZ_V0.5.3.7.0.md`
- [ ] canary green
- [ ] SHI=100% на 3 сессиях подряд
- [ ] Movement Traversal = ✅ для ≥5 из 6 NPC

---

## 5. ФАЗА 1 — Завершить Эпоху 6: Infrastructure

**Цель:** Property-Based IPT coverage >80%, Replay System exact-match, Causal Probes live, ADR-Net MVI=48h, Self-Healing L0-L2 активны, LLM Pipeline v1 даёт P50<2.5s и cache hit ≥35%.
**Источник ТЗ:** `docs/Почти Актуальные TZ/ENIGMA_TZ_INFRASTRUCTURE.md`, `ENIGMA_SELF_HEALING_SYSTEM.md`, `ENIGMA_LLM_PIPELINE_TZ_v1.md`.
**Параллельность:** 1.1-1.6 — параллельно.

### Чек-лист

- [ ] **1.1** Property-Based IPT — расширить `backend/tests/IPT.py` гипотезами из Эпох 1-5 контрактов (L1/L2/L16/L17/L18/L20). Использовать `hypothesis`.
- [ ] **1.2** Replay System — `KernelRNG(tick, npc_id, salt)` детерминизм. Сохранить seed-параметры → переиграть тик → сравнить `TickMutation`. **Файлы:** `backend/app/core/kernel_rng.py`, новый `backend/app/replay/`.
- [ ] **1.3** Causal Probes — `diagnostics/causal_observer.py` + новые probe-классы. Цель: автоматический контр-фактический анализ.
- [ ] **1.4** ADR-Net — neural net для классификации ADR-нарушений. MVI (Minimum Viable Implementation) = 48 чел.-часов, full = 158 чел.-часов.
- [ ] **1.5** Self-Healing L0-L2: L0 = event subscribers, L1 = telemetry dashboard, L2 = auto-rollback на регрессию. Источник: `ENIGMA_SELF_HEALING_SYSTEM.md`.
- [ ] **1.6** LLM Pipeline v1: semantic cache на BGE-small-ru + FAISS, grammar-constrained JSON через `pydantic`/`jsonschema`. Цель: P50<2.5s, cache hit ≥35%.
- [ ] **1.7** DRI-метрика (см. §2.5) — новый модуль в `diagnostics/`.
- [ ] **1.8** Audit Log LLM-вызовов (см. §2.6) — `backend/app/llm/audit_log.py`.

### Гейты для перехода к Фазе 2

- [ ] IPT coverage >80%
- [ ] Replay exact-match на 100-tick отрезке
- [ ] LLM P50 <2.5s, cache hit ≥35%
- [ ] DRI-метрика green на 5 тестовых сессиях
- [ ] ADR-Net MVI обучена

---

## 6. ФАЗА 2 — Эпоха 7: Vertical Slice + Prophecy

**Цель:** Vertical slice демо «Люся и 3 парня» играбельно; Prophecy Causality Law (ADR-O-330) green; §19 PerceptualKernel внедрён.
**Источник ТЗ:** `TZ_§19_Predictive_Perception_Dynamics.md`, ADR-O-330 (Prophecy).
**Параллельность:** 2.1+2.2 (Belief Layer) → 2.3 (§19) → 2.4 (Prophecy) → 2.5 (Vertical Slice).

### Чек-лист

- [ ] **2.1** Сформулировать и реализовать **Social Belief Layer (ToM)** — см. §2.1. `CrystallizedBelief(subject × target × predicate × polarity)` + `BELIEVES` second-order. **Файлы:** `backend/app/cognition/belief_crystallization_engine.py`, `crystallized_belief_store.py`.
- [ ] **2.2** Belief Merger — см. §2.2. **Файлы:** новый `backend/app/cognition/belief_merger.py`.
- [ ] **2.3** §19 Predictive Perception — `PerceptualKernel` с `z_t = F(z_{t-1}, x_t)` и `surprise = −log P(x_t|z_{t-1})`. Surprise становится каузальным входом. **Файлы:** `backend/app/perception/perceptual_kernel.py` (новый).
- [ ] **2.4** Prophecy System (ADR-O-330): player *asserts* future → belief crystallizes в L2.5 → confirmation bias → self-fulfilling. **Файлы:** `backend/app/cognition/prophecy_engine.py` (новый).
- [ ] **2.5** Vertical Slice «Люся и 3 парня» — кампания-демо, проверяющая всю связку: Belief + Merger + §19 + Prophecy.

### Гейты для перехода к Фазе 3

- [ ] Prophecy Causality Law green (ADR-O-330)
- [ ] Vertical Slice играбелен от начала до конца
- [ ] ToM-метрика: NPC корректно моделирует убеждения 2+ других NPC
- [ ] §19 surprise-метрика измеряется

---

## 7. ФАЗА 3 — Эпоха 8: Generational Depth

**Цель:** WorldChronicle persistence (4 стадии), Memetic Domain (Concept → Extinction), 3 уровня времени.
**Источник ТЗ:** `ТЕХЗАДАНИЕ ПРЕЕМНИКУ TZ-02 V.2.0`, `TZ_MEMETIC_01/02/03`.
**Параллельность:** 3.1 (WorldChronicle) и 3.3 (Memetic) — параллельно после 3.2.

### Чек-лист

- [ ] **3.1** WorldChronicle — 4 стадии: (1) Birth/Death, (2) Aging, (3) Lineage, (4) Integration. Источник: TZ-02 преемнику.
- [ ] **3.2** 3 уровня времени: `game_time` (tick), `belief_time` (L1Chronicle), `lineage_time` (NEW).
- [ ] **3.3** Memetic Domain — онтология Concept / Expression / Adoption / Norm / Extinction. Источник: `TZ_MEMETIC_01_Domain_Spec.md` (1994 строки).
- [ ] **3.4** Content Policy Integration — per-NPC `ContentProfile` из adopted expressions, `SpeakerVocabulary` в `DMContractBuilder`. Источник: `TZ_MEMETIC_02`.
- [ ] **3.5** TZ_MEMETIC_03 Patch List — 12 точек правки + 8 новых файлов. Пройти по списку.
- [ ] **3.6** Наследуемые убеждения — убеждения родителей кристаллизуются в потомках через Memetic Domain.

### Гейты для перехода к Фазе 4

- [ ] WorldChronicle persistence green (данные выживают reset)
- [ ] Memetic transmission измеряется (Concept → Adoption rate)
- [ ] 3 уровня времени консистентны
- [ ] Lineage: ≥3 поколения NPC live

---

## 8. ФАЗА 4 — Эпоха 9: Full Society

**Цель:** Общество из 50+ NPC стабильно, фракции, экономика, политика.
**Источник ТЗ:** `EPOCHS_REPORT.md` §Epoch 9 design, `architecture/economy.yaml`.
**Параллельность:** все три подсистемы параллельны.

### Чек-лист

- [ ] **4.1** Factions system — группировки, репутация, конфликты.
- [ ] **4.2** Economy layer — `architecture/economy.yaml` → реализация. Торговля, цены, дефицит.
- [ ] **4.3** Politics — властные структуры, решения, влияющие на общество.

### Гейты для перехода к Фазе 5

- [ ] Общество 50+ NPC стабильно 30+ минут без коллапса
- [ ] Все три подсистемы имеют метрики (faction tension, economy velocity, political stability)

---

## 9. ФАЗА 5 — Эпоха 10: §18 Resource-Bounded Epistemic Selection

**Цель:** Формула `U_M = I·R·U − C` активна как закон симуляции. Bounded rationality (Simon/Kahneman).
**Источник ТЗ:** `TZ_§18_Resource_Bounded_Epistemic_Selection_Law.md`.
**ЖЁСТКО:** §18 ВНЕДРЯТЬ НЕЛЬЗЯ до завершения Belief Layer (Фазы 2-3).

### Чек-лист

- [ ] **5.1** Завершить Belief Layer MVP (CrystallizedBelief + Merger + ToM + BELIEVES second-order).
- [ ] **5.2** Внедрить формулу `U_M = I·R·U − C` (Information × Relevance × Utility − Cost) — как universal bound на epistemic действия NPC.
- [ ] **5.3** Bounded rationality: NPC не может рассматривать все гипотезы — выбирает топ-N по `U_M`.
- [ ] **5.4** Измерить: для каждого epistemic действия NPC логируется `U_M` до/после.

### Гейты для перехода к Фазе 6

- [ ] §18 закон активен и измеряется
- [ ] Belief Layer green
- [ ] Bounded rationality: NPC не превышает cognitive budget

---

## 10. ФАЗА 6 — Post-MVP расширения

**Цель:** Дополнительные слои поверх стабильного ядра.
**Источник ТЗ:** соответствующие файлы из `docs/Почти Актуальные TZ/`.

### Чек-лист

- [ ] **6.1** `ENIGMA_TZ_Female_Targeted_Dark_Fantasy_Layer.pdf` (113 стр.) — романтика, драма, gothic, 6 доменов. **Когда:** после Эпохи 8 (нужна глубина NPC).
- [ ] **6.2** `TEXTURES_AND_GEOMETRY_TZ.md` — 2D composite model (head/torso/arms), 128×128 dialogue portraits, aging visual effects. **Когда:** параллельно с Фазой 3 (там lineage → visual aging).
- [ ] **6.3** `ENIGMA_MAP_EDITOR_SMART_VALIDATION.md` — BedRegistry, map editor validator, auto-cut стен. **Когда:** когда угодно, изолированно.
- [ ] **6.4** `AWC_Process_World_Model_TZ.pdf` — Process/WorldGraph/NPCKnowledge. **Эпоха 11+, НЕ реализован** — только дизайн.
- [ ] **6.5** `S1_INPUT_TRACE_IMPLEMENTATION.md` + `INPUT_OBSERVATORY_ROADMAP_S2_S6.md` — observability player input. **Когда:** можно начать в Фазе 1 (Infrastructure).

---

## 11. Гейты и Stop-criteria — сводная таблица

| Переход | Stop-criteria (все должны быть ✅) |
|---------|-----------------------------------|
| **Фаза 0 → 1** | 0 Critical багов · canary green · SHI=100% ×3 сессий · Movement Traversal ✅ ≥5/6 NPC · version.txt синхронизирован |
| **Фаза 1 → 2** | IPT coverage >80% · Replay exact-match 100 тиков · LLM P50<2.5s, cache hit ≥35% · DRI green ×5 сессий · ADR-Net MVI обучена |
| **Фаза 2 → 3** | Prophecy Causality Law green · Vertical Slice играбелен · ToM-метрика green · §19 surprise измеряется |
| **Фаза 3 → 4** | WorldChronicle persistence green · Memetic transmission measured · 3 времени консистентны · ≥3 поколения live |
| **Фаза 4 → 5** | Общество 50+ NPC стабильно 30+ мин · все три подсистемы имеют метрики |
| **Фаза 5 → 6** | §18 закон активен · Belief Layer green · Bounded rationality: NPC не превышает cognitive budget |

### 7 красных флагов — STOP, если заметил

1. **DNA-метрики врут** — SHI=100%, но NPC реально не двигаются. → перепроверить через `backend/data/logs/scene_changes_*.jsonl` и `enigma_*.jsonl`.
2. **`PlayerBeliefModel` принят за NPC ToM** — это разные вещи. ToM требует second-order `BELIEVES`.
3. **`MockProvider` в production-пути** — проверять в `dm_agent.py`, `dialogue_router.py`. Только в тестах.
4. **Observability мутирует state** — `diagnostics/*` должен только читать. Любая запись в `state` из diagnostics = баг.
5. **§18 внедряется до Belief Layer** — критическое архитектурное нарушение. Формула `U_M = I·R·U − C` требует готового Belief Layer.
6. **Version desync повторился** — `version.txt` расходится с `frontend/constants.py` и ТЗ-версией. Проверять перед каждым релизом.
7. **`random.*` или `time.time()` в kernel-слое** — нарушает L2 Runtime Purity Law. Только `KernelRNG(tick, npc_id, salt)`.

---

## 12. Quick recovery — если зашёл в тупик

| Симптом | Что делать |
|---------|------------|
| DNA SHI=100%, но визуально NPC не двигается | Смотреть `backend/data/logs/scene_changes_*.jsonl` + `enigma_*.jsonl`, проверить `MovementIntent` → `TraversalState` в `local_traversal_planner.py` |
| Регрессия появилась, непонятно где | `git bisect` от последнего коммита с SHI=100%; marker — `pytest backend/tests/canary/test_full_playthrough.py` |
| LLM молчит | `backend/logs/cds_session_*.log` + проверить `DecisionHub._context_relevance` в `decision_hub.py:882` (NameError исторически) |
| `movement_traversal ❌` | `local_traversal_planner.py` + `traversability_evaluator.py` + `geometry_kernel.py`; проверить `MovementIntent` |
| IPT падает | `diagnostics/health_checkers/{invariant_health, tick_health, movement_health}.py` — какой из трёх красный |
| `version.txt` разошёлся | `version.txt` + `frontend/constants.py` + `splash.py` синхронизировать вручную |
| LLM error masking | `dialogue_router.py` — убрать `try/except Exception: pass`, заменить на логирование + re-raise |
| `all_npcs_raw_snapshot` пропадает | `pipeline_context.py` + `shared_context.py` — проверить reset между тиками |
| NPC position = `"bed"` вместо node | `backend/app/core/calendar.py` — schedule должен отдавать current node, не спальное место |

### 7 контрольных вопросов для самопроверки

1. Чем `TickState` отличается от `TickMutation`? (Ответ: state = входное неизменяемое, mutation = выходная дельта. Pure function: `run(state) → mutation`.)
2. Почему `random.*` запрещён в kernel-слое? (Ответ: нарушает Replay System — детерминизм.)
3. Что такое Triple Membrane? (Ответ: 3 фильтра на L1Chronicle: Physical (LoS/audibility) + Personality (rigidity/openness) + Social (status/norms).)
4. Чем `EmbodiedTraceDTO` отличается от эмоций? (Ответ: EmbodiedTrace = observable motor manifestations (tense/rigid/trembling); эмоции типа «fearful» запрещены §4.3.23.)
5. Что такое Epistemic Boundary (L16)? (Ответ: NPC не может читать mental state другого NPC; DM-агент читает только `observed_state` + `embodied_traces`.)
6. Почему §18 нельзя внедрять до Belief Layer? (Ответ: `U_M = I·R·U − C` требует готовой кристаллизации убеждений, иначе `I` и `R` не определены.)
7. Что делать, если `Movement Traversal = ❌` для всех NPC? (Ответ: Фаза 0, шаг 0.7 — усиление Movement Engine, SC-2..SC-8 probes.)

---

## 13. Ресурсы и контакты

### Готовые документы (полный список)

| Тип | Путь |
|------|------|
| Главное ТЗ | `upload/ENIGMA_TZ_V0.5.3.7.0.md` |
| Epochs report | `docs/ENIGMA_EPOCHS_REPORT.md` |
| Сессии | `reports/LAST_SESSION.md`, `reports/SESSION_S62_DM_VISION.md`, `reports/history/*.md` (~80 файлов) |
| Repair TZ (Remont) | `docs/Почти Актуальные TZ/RemontTZ/*.md` (6 файлов) |
| VZ (future epochs) | `docs/Почти Актуальные TZ/VZ/*.md` (7 файлов) |
| Infrastructure | `docs/Почти Актуальные TZ/ENIGMA_TZ_INFRASTRUCTURE.md`, `ENIGMA_SELF_HEALING_SYSTEM.md`, `ENIGMA_LLM_PIPELINE_TZ_v1.md` |
| ADRs | `docs/audits/*.md` (107 файлов) |
| Architecture YAML | `architecture/*.yaml` (15+ файлов: identity, memory, perception, physiology, spatial, temporal, ...) |

### Ключевые файлы кода (для runtime-проверок)

| Подсистема | Файл |
|------------|------|
| Tick pipeline | `backend/app/core/tick_orchestrator.py` |
| Task scheduler | `backend/app/core/task_scheduler.py` |
| DecisionHub | `backend/app/cognition/decision_hub.py` |
| DM-agent | `backend/app/dm_agent.py` |
| Pipeline context | `backend/app/core/pipeline_context.py` |
| Belief engine | `backend/app/cognition/belief_crystallization_engine.py` |
| Movement | `backend/app/spatial/local_traversal_planner.py`, `geometry_kernel.py`, `traversability_evaluator.py`, `motion_pipeline.py` |
| Dialogue | `backend/app/dialogue/dialogue_router.py` |
| Diagnostics | `diagnostics/dna_metrics.py`, `causal_observer.py`, `health_checkers/*.py` |
| Kernel RNG | `backend/app/core/kernel_rng.py` |
| Tests (IPT) | `backend/tests/IPT.py` |
| Canary | `backend/tests/canary/test_full_playthrough.py` |
| LLM logs | `backend/logs/cds_session_*.log`, `llama_server.log`, `error.log` |
| Session data | `backend/data/logs/scene_changes_*.jsonl`, `enigma_*.jsonl`, `combat_log.jsonl` |
| DNA history | `reports/dna_history.jsonl` |

### Принципы работы (напоминание)

- Один фикс → один коммит → один тест.
- CI-гейты обязательны (`ruff` + `pytest backend/tests/IPT.py`).
- Observability never mutates.
- `MockProvider` только в тестах.
- `random.*` / `time.time()` — запрещены в kernel-слое.
- Слушать интуицию пользователя — обычно совпадает с `EPOCHS_REPORT.md`.

---

**Документ завершён. Следующий шаг — открыть `ENIGMA_TZ_V0.5.3.7.0.md` §3, начать с REGRESSION-CORE-001.**
