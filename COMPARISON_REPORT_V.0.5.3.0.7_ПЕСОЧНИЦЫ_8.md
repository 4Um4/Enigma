# Сравнительный отчёт: V.0.5.3.0.6_ПЕСОЧНИЦЫ_3 -> V.0.5.3.0.7_ПЕСОЧНИЦЫ_8

Дата: 14.05.2026  
База: `de2afff` (`V.0.5.3.0.6_ПЕСОЧНИЦЫ_3`)

Границы анализа:
- Учтены изменения дня по коду/данным/архитектурным документам.
- Исключены публикационные артефакты этого шага: `README.md`, текущий отчёт.

## 0. Сводка метрик

| Метрика | Значение |
|---|---:|
| Изменённых файлов | 117 |
| Добавлено строк | 13465 |
| Удалено строк | 559 |
| Чистый прирост | +12806 |
| Новых функций всего | ≥13 (affective: pressure/emotion, spatial query, NPC pipeline, plus новые документы/ADR) |
| Новых runtime-функций | ~3 (новые сервисы/контур: affective+spatial query+интеграция в pipeline) |
| Новых тестовых функций | ≥5 sandbox/scenario тестов + доработки life/persistence/tick loops |
| Проверка новых песочниц | backend: `python -m backend.tests.test_services` → 10 OK, 2 skipped |

Примечание:
- Полный suite (включая sandbox/system/stress/интеграцию “The Fool”) ещё не прогнан полностью; в таблице отражён результат запуска `test_services`.

## 1. Критический параметр решения

Критический параметр: **замкнутость каузального контура через pipeline “pressure/affective → decision_context → decision_hub → snapshot/applicator → пространственный контракт”** без скрытых обходов (bypass).

Что сделано по сути:
- Аффективный контур стал выделенным и “действующим”:
  - добавлены/введены `emotion_resolution.py`, `pressure_derivation.py`
- Давление и контекст связаны с decision-контурами:
  - обновлён `backend/app/services/cfrm/pressure_translator.py`
  - доменные модели и snapshot связи синхронизированы через `DecisionContext` / `snapshot`
- Пространственный контур переведён к более контрактной query-модели:
  - добавлен `backend/app/services/spatial/spatial_query_service.py`
  - согласованы `movement_engine.py`, `world_tick_engine.py`, `tick_orchestrator.py`
- Усилен порядок выполнения в NPC-пайплайне:
  - `decision_hub.py`, `npc_tick_pipeline.py`, `state_applicator.py`, `legacy_delta_adapter.py`
- Добавлены/усилены наблюдаемые sandbox-проверки:
  - affective_pressure / schedule_override / temporal_reconciliation / micro-macro locomotion / schedule locomotion

## 2. Итог дня (что сделано ценного)

- **Аффективность перестала быть “побочным полем”** и стала управляемым входом decision-контура (pressure/эмоции → решение).
- **Spatial стало сервисом-контрактом**: запросы к пространству унифицированы и лучше согласованы с исполнением.
- **NPC decision layer стал устойчивее**: intent → context → decision → apply теперь прозрачнее, что снижает шанс скрытых обходов.
- **Документация и метрики закрепили эволюционную линию**:
  - `docs/audits/ENIGMA_COGNITIVE_ARCHITECTURE_EVOLUTION.md`
  - `docs/INFO/ENIGMA_EVOLUTION_INTELLIGENCE.md`
  - CSV metrics (raw/derived/v2)
  - ADR-Impact серия `docs/audits/ADR-047..ADR-056_IMPACT.md`

## 3. Что может перевернуть итоговый вывод

- Интеграционная связка “The Fool” может выявить edge-cases в связке affective → decision_hub → spatial apply.
- Spatial query контракт требует доводки до полного покрытия perception/apply, чтобы избежать drift между фазами.
- Калибровка порогов (например, `threat_gradient`) и коэффициентов давления/декаев нужна на длинных сценариях/кампаниях.

## 4. Что проверить дальше (next-value)

1. **Прогнать весь backend suite** (включая sandbox/system/stress и persistence/tick loops).
2. **Smoke “The Fool”**: запуск сцен/сценариев, где затрагивается affective/spatial/npc decision pipeline, чтобы подтвердить причинную трассируемость.
3. Довести spatial query контракт до требуемого покрытия и проверить отсутствие drift между Decision/Perception/Snapshot.
