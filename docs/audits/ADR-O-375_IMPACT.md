# ADR-O-375 Impact Audit
> Детальный аудит ОДНОГО ADR. Единый атлас: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- Сон: канон state-семейства — body_state["sleep_onset_tick"] (int|None — ФАКТ физиологического сна) + body_state["wake_duration"] (незажатый homeostatic аккумулятор). Единственный писатель обоих — Phase 0.6 (SleepLifecycleService).
- Coupling: двусторонний onset-гейт в CouplingResolver — без факта потолок DROWSY (сон-режимы/×3/sleep-ownership недостижимы); факт жив → сон-семейство переживает decay sleep_pressure. Непрерывные оси S189 не тронуты.
- Динамика бодрствования: sp += 0.005 × (1 + fatigue/100 × FATIGUE_PRESSURE_MOD_COEFF [v1=1.0, на ревью Мастера]); wd += 1 (без clamp).
- Wake: arousal-гейт (не менялся, Q5) ∨ intent-withdrawal (новая ветка); общий эффект _wake_from_sleep.

## Downstream Consumers
- BodyEngine / CommitmentRegistry — код не менялся; сон-физиология ×3 и sleep-зеркало теперь onset-обусловлены через coupling-предикат Phase A (ADR-O-374).
- LifeEngine — legacy writer routine._sleep_start_tick девальвирован (reader мёртв; [S2B6-D3] — удаление санацией).
- W2/W-track (будущее): sleep-affordance-типы (BED → HAMMOCK/GROUND/SHELTER…) подключаются через интерфейс bed_ok, не расширяя домен сна.
- Персистентность: новые ключи body_state — plain dict; WARA round-trip гвард (json).
- tick_orchestrator._phase_0_6 — проводка eligibility (bed_ok/settled); ко-локация W3-shadow-блока (их ADR-O-373 Gate-1) — мерж-точка двух сессий.

## Runtime Impact
- O(1) на NPC/тик: один get_node (bed_ok) + гейт резолвера. Измеренный контроль: drift A–E = 0/0 в обоих A/B-прогонах (Phase A и Phase B), объём 1200/1200 ENGINE-строк.

## Sandbox Tests
- tests/test_action_commitment.py: TestS2B6OnsetGatedCoupling (6) / TestS2B6OnsetEligibility (8) / TestS2B6OnsetTransition (8+1) — вкл. дифференциальный цепной тест (onset → SLEEP → −0.245/+0.76) и WARA round-trip.
- tests/system/test_sleep_routing.py — фикстура несёт факт сна.
- A/B-зонды VIII.5 (200 тиков × 6 NPC, реверсированы тройной верификацией): reports/DIAG_S2B6B_sleep.txt; Phase A: reports/DIAG_S2B6_sleep_baseline.txt, reports/DIAG_S2B6_sleep_after.txt.

## Rollback
- Revert патчей Phase B возвращает routine-ветвление (сон = строка расписания). Гварды (onset-гейт / переход / дифференциальный) упадут первыми — в этом их назначение.
- Диагностические данные reports/DIAG_S2B6* не зависят от отката кода.