# ADR-O-361 Impact Audit
> Детальный аудит одного ADR. Единый атлас: `docs/ADR (Architecture Decision Records).md`
> Статус: ACTIVE | Сессия: S213 (номер сверен по хвосту MUTATIONS.md)

## Changed Domains
Прямых изменений доменов нет (ядро не трогается). Калибруются значениями:
trust, fear, memory, belief, decision, identity.

## Downstream Consumers
- Все потребители `app.core.constants` с from-import биндингами
  (decision_hub.py:27-43) — патчатся identity-сканом overlay.
- TickOrchestrator — только через существующий контракт interventions.
- EventBus — подписка ObservabilityTap (Закон 5.3, синхронно).
- dna_metrics.py — аддитивное расширение DNASnapshot (M2).
- Persistence — только эфемерные temp-копии кампании; схемы БД не меняются.

## Runtime Impact
- Вход/выход overlay: O(атрибуты загруженных модулей), раз на эксперимент;
  verify — O(патчей). ObservabilityTap: O(1)/событие, кольцевой буфер.
- Ядро: ноль накладных расходов вне эксперимента.

## Sandbox Tests
- `test_m0_config_overlay.py` (9) — граница overlay; `test_m0_presets.py` (16) —
  валидатор + контрольные пресеты; `test_m0_materializer.py` (9) — redirect/
  patch/restore на реальном config/npc; `test_m0_runner.py` (3) — smoke
  конвейера + replay-ядро + restore настроек; `test_m0_metrics.py` (8) — метрики;
  `test_m0_acceptance.py` (5) — AC-001…004 + зонный отчёт; `test_m0_superbox.py`
  (1) — AC-005 baseline-delta (pre-existing красный SUPERBOX-014 → skip
  с диагнозом, чужая зона). Итог: 51 passed / 1 skipped / IPT 44/44.

## Session S213 Closeout
- RESOLVED в M0: DEBT-INTENT-SOURCE (датчики diversity/loop/responsiveness
  переведены на канал ТЗ 14.2 IntentEventAdapter через ObservabilityTap;
  писателя npc["intent"] в снапшоте загрузчика не существует); канал
  «SQLite not initialized» (post-dispose страгглеры — final_quiesce).
- Зонное открытие: idle → MANNEQUIN ∀ пресетов; условие ENIGMA = события.

## Rollback
Удалить `backend/app/services/calibration/`, `backend/tests/calibration_lab/`,
`config/calibration/`, `architecture/calibration.yaml` → `python build_graph.py`.
Ядро не модифицировано. W-IR (расширение personality-адаптера) — отдельный
реверт со своим round-trip тестом.

## Связанные ADR / долги
- ADR-O-360 (S207): DIRECT_OBSERVATION_RELIABILITY — калибруемый параметр
  (пресеты, жёсткое ограничение < 1.0).
- Урок S207 (DEBT-R5): silent except в путях патча = тихая смерть ядра.
- DEBT-R1 (radius 999.0), DEBT-R6 (изоляция SUPERBOX) — учитывать в Tap
  и superbox_adapter.
- Базлайн-риски IPT: R-SOC (shared_context missing → social deltas skipped),
  R-L1 (L1Chronicle persist 'bad parameter' в harness), NEI=0 — расследовать
  до шагов Runner/метрик.