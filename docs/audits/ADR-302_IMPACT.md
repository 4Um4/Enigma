# ADR-302 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-302` [STANDARD] **IMPACT**
# ADR-302 Impact Audit: SIL, DSTC & SEL (Active Inference)

> Этот файл — детальный аудит эволюции ADR-302. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- emotion/affective (SIL isolation, Semantic Echo elimination, **SEL Active Inference добавление**)
- causality/pipeline (DSTC snapshot barrier, S75-FIX removal, **Split-Brain диагностика**)
- perception/interpretation (CIR enforcement, BehaviorManifestationService source switch)

## Downstream Consumers
- `TickOrchestrator` — внедрение `interpretation_snapshot` и `semantic_buffer` в `_TickContext`, удаление 3 досрочных `apply_batch()`, **внедрение математики Active Inference в `_run_affective_pipeline`**
- `StateApplicator` — блокировка записи S-слоя (эмоций/интеграла) в M-слой, за исключением `affective_decay` **и легального клапана `sel_trace_commit`**
- `NPCState` / `NPCStateAdapter` — **добавлено поле `affective_memory: float` (Trace State / Prior)**
- `EmotionPayload` — **расширено полем `affective_memory` для легальной передачи Котла в M-слой**
- `ReactionSubscriber` — лишён права генерации `emotion_tag` (CIR), передаёт только `stress_delta`
- `BehaviorManifestationService` — переключён на чтение T+0 из `semantic_buffer` и физики из `interpretation_snapshot`
- `WorldSnapshotBuilder` / `AvatarPresentationAssembler` — переключены на `interpretation_snapshot` как источник истины в Phase 9

## Runtime Impact
- RAM: +`interpretation_snapshot` (deepcopy 10-20 dict'ов ~ 10-50KB на тик, освобождается в Phase 10), +`semantic_buffer`, **+1 float на NPC (`affective_memory`)**
- Tick Latency: +время `copy.deepcopy` (микросекунды), -3 вызова `apply_batch` (чистый выигрыш или нейтрально), **+1 вычитание для Active Inference (пренебрежимо)**
- No VRAM impact

## Sandbox Tests
- SMOKE TEST PASSED: SIL SCC Invariants OK
- CAUSAL STRESS TEST PASSED: Semantic Echo eliminated, Identity canonical
- DSTC SMOKE TEST PASSED: Snapshot isolation and in-place mutation OK
- DSTC FULL CYCLE VERIFICATION PASSED: Invariant intact, renaming correct
- **SEL MATH TEST PASSED: `test_sel_predictive_affect.py` (3/3 — Инерция, Шок засады, Привыкание)**
- **SEL ROUND-TRIP TEST PASSED: `affective_memory` переживает `write_to_legacy` → `from_legacy`**

## Rollback
1. Удалить `interpretation_snapshot` и `semantic_buffer` из `_TickContext`.
2. Вернуть 3 досрочных вызова `apply_batch()` (S75-FIX) в `tick_orchestrator.py`.
3. Разблокировать запись `emotion_tag` и `affective_load` в `StateApplicator` для всех источников.
4. Вернуть генерацию `emotion_tag` в `ReactionSubscriber`.
5. Вернуть чтение `affective_load` из M-слоя в Phase 9 (восстановит Semantic Echo / Вечный двигатель).
6. **Удалить поле `affective_memory` из `NPCState`, `NPCStateAdapter` и `EmotionPayload`.**
7. **Удалить математику Active Inference из `_run_affective_pipeline` (вернуть `current_load = PK_load`).**

## Key ADR Content

### Проблема
1. **"Вечный двигатель страха" (S → M → S петля):** Affective Pipeline читал `affective_load` из M-слоя и перезаписывал сам себя. (Решено на Этапе 1-2).
2. **"Термометр" (Observation Run O-144):** После изоляции SIL эмоции стали эфемерными. Угроза ушла → `PK_load = 0` → `affective_load = 0`. Стресс не имеет инерции. (Решено на Этапе 3).
3. **"Split-Brain Simulation" (Observation Run O-155):** Аффективный pipeline был подключён внутри `_phase_9_player_integration`, который зависит от `shared_context`. При его отсутствии (или в определённых путях action tick) Pipeline делает ранний `return`. Эмоции отключаются во время действия. (Требует решения на Этапе 3.1).

### Решение
Четыре разделённых архитектурных слоя:
1. **SIL (Semantic Immunity Layer)**: Запрет обратной онтологической мутации S → M внутри тика. Эмоции пишутся в `semantic_buffer` (S-слой) и сливаются в M-слой только в Phase 10.
2. **CIR (Causal Isolation Rule)**: Phase 8 лишена права генерировать эмоции. Phase 9 — единственный генератор S-слоя.
3. **DSTC (Dual-Snapshot Tick Contract)**: Изоляция Phase 9 от M₀ через `interpretation_snapshot`.
4. **SEL (Semantic Echo Layer) / Active Inference**: Замена "Термометра" на "Котёл" (Предиктивное кодирование). Эмоция вычисляется не как сырой сигнал (`PK`), а как ошибка предсказания (`Surprise`). Вводится `affective_memory` (Prior), которая медленно затухает и обучается. Легальный обход SCC через `source="sel_trace_commit"`.

### Точка внедрения
- `_TickContext` — расширение структуры данных.
- `_run_affective_pipeline` — **внедрение математики Active Inference: `delta = PK - memory`, `load = memory + |delta| * gain`**.
- `StateApplicator._apply_deltas` — шлюзование записи S-слоя **и пропуск `sel_trace_commit` для `affective_load` + `affective_memory`**.
- `NPCState` / `NPCStateAdapter` — добавление `affective_memory`.

### При отсутствии эмоций в semantic_buffer
Система читает эмоции из M-слоя (T-1) как fallback. Визуализация корректно деградирует до прошлого состояния.

### Каузальные запреты (инварианты)
1. **SCC**: StateApplicator НЕ пишет S-слой напрямую, **ЗА ИСКЛЮЧЕНИЕМ легального клапана `source="sel_trace_commit"` и `affective_decay`**.
2. **CIR**: Phase 8 НЕ генерирует `emotion_tag`.
3. **Pure Read**: Phase 9 читает NPC ONLY из `interpretation_snapshot`.
4. **Active Inference (замена Semantic Echo Ban)**: Phase 9 читает из M-слоя (через snapshot) `affective_memory` как Prior, но **строго игнорирует `affective_load`** (Posterior). Это даёт инерцию без самопитания.
5. **Identity Preservation**: Замена M₀ на S_intermediate в Phase 10 выполняется строго через срез `[:]`.
6. **SIL Reconciliation Order**: Слияние S → M происходит ДО `scene_manager.commit()`.
7. **Affective Pipeline Sovereignty (НОВЫЙ)**: `_run_affective_pipeline` ОБЯЗАН выполняться безусловно 1 раз за тик. Не имеет права зависеть от DM/`shared_context`. (Нарушение = Split-Brain).


Files: N/A
