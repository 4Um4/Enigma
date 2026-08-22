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
- `backend/tests/calibration_lab/test_m0_config_overlay.py` — M0-AC-006,
  регрессия A1 (биндинги decision_hub), вложенность, неизвестная константа,
  require_loaded, отсутствие cross-patch интернированных 0.15, dict-константа.
- Далее: M0-AC-001…005 (пресеты, runner, SUPERBOX под overlay).

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
