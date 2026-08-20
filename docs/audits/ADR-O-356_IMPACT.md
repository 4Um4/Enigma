# ADR-O-356 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-O-356` [STANDARD] **IMPACT**
# ADR-O-356 Impact Audit: Sleep as Bodily Coupling Mode (Complete)
> Этот файл — детальный аудит ADR-O-356. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`
> Сессия: S189 (2026-05-21)

## Changed Domains
- **DOM-01 (Foundation):** `body_state` расширен `coupling_profile` и `dream_residue`.
- **DOM-02 (Will & Decision):** `DecisionContext` учитывает `has_active_commitment`.
- **DOM-03 (Perception):** `phases/integration.py` модулирует стимулы через `CouplingProfile`. `EventBus` обрабатывает `DREAM`/`NIGHTMARE`.
- **DOM-05 (Physiology):** `SleepLifecycleService` полностью управляет сном, снами и пробуждением.

## Downstream Consumers
- **DecisionHub:** Читает `constraints` (включая блокировки от `ActiveCommitment`).
- **PerceptualKernel:** Обновляется с учётом модуляции от `CouplingProfile`. Получает `threat_gradient` от `DreamResidue` при пробуждении.
- **AffectiveIntegrator:** Получает повышенный `affective_load` от `DreamResidue` при пробуждении, который естественным образом затухает.
- **TimeSkipExecutor:** Прерывается событиями `DREAM` и `NIGHTMARE`.

## Runtime Impact
- **RAM:** Минимальный. `CouplingProfile` и `dream_residue` — небольшие словари.
- **Latency:** O(1) операции. Замедления тика не зафиксировано (IPT 39/39 green).

## Sandbox Tests
- `backend/tests/IPT.py` (39/39 passed) — подтверждает отсутствие регрессий.

## Rollback
1. Удалить вызовы `_update_coupling_profile`, `_accumulate_arousal_from_stimuli` и `DreamGenerationService.generate` из `sleep_lifecycle_service.py`.
2. Убрать `has_active_commitment` из `pressure_translator.py` и `npc_tick_pipeline.py`.
3. Убрать модуляцию `_cp` в `phases/integration.py`.
4. Убрать конвертацию `dream_residue` в `_check_wake_up`.
5. Удалить файлы `coupling_resolver.py`, `dream_generation_service.py` и DTO `CouplingProfile`/`DreamSignal`.


Files: N/A
