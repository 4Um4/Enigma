# ADR-TIFL-003 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-TIFL-003` [STANDARD] **IMPACT**
# ADR-TIFL-003 Impact Audit: Identity Constraint Layer (ICL) & Thermodynamic Crystallization

> Этот файл — детальный аудит внедрения геометрии устойчивых Я-конфигураций (аттракторов) и починки type-domain mismatch.
> Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- **npc/identity** (Введение матрицы связности `DRIVE_COUPLING` и силы внутренней релаксации).
- **causality/pipeline** (Воскрешение мёртвого кода `break_progress_engine` и подключение его к idle-тикам).
- **core/runtime** (Временное введение неявного полиморфизма `isinstance(dict | NPCState)` для совместимости слоёв).

## Downstream Consumers
- `break_progress_engine.py` — Изменён статус с `DEPRECATED` на `ACTIVE`. Добавлена матрица `DRIVE_COUPLING`. Функция `compute_continuous_drift` дополнена блоком "Внутренняя релаксация" и адаптирована для приёма как `NPCState`, так и `dict`.
- `tick_orchestrator.py` — Внедрён вызов `_run_affective_pipeline` в idle-путь (после `_phase_9_integration`). Без этого Котёл не работал в 99% времени.
- `apply_drives_mutation` — Адаптирована для работы со словарями `npc_raw`.

## Runtime Impact
- **RAM:** ~100 байт на NPC (хранение матрицы связности).
- **Tick Latency:** +0.5ms (вычисление тензора напряжения и градиента релаксации на каждом тике).
- **Determinism:** Сохраняется при фиксированном `DRIVE_COUPLING` (Fixed Topology).
- **Behavior:** Фундаментальный сдвиг. Личности перестали быть текучей массой и начали "кристаллизоваться" в архетипы. Конфликтующие драйвы (Страх + Контроль) создают напряжение, которое толкает личность к одному из полюсов. Появилась инерция идентичности.

## Sandbox Tests
- `test_high_tension_drives_relaxation.py` — Состояние `{fear: 0.5, control: 0.5}` со временем спонтанно дрейфует к одному из полюсов, даже без внешних ошибок.
- `test_archetype_stability.py` — Состояние `{fear: 0.1, control: 0.8}` устойчиво к слабым ошибкам по страху; внутренняя релаксация возвращает личность к аттрактору.
- `test_pipeline_resurrection.py` — `_run_affective_pipeline` вызывается в idle-тиках. `prediction_error` > 0.

## Rollback
1. Удалить матрицу `DRIVE_COUPLING` и блок "Внутренняя релаксация" из `compute_continuous_drift`.
2. Удалить вызов `_run_affective_pipeline` из idle-пути в `tick_orchestrator.py`.
3. Вернуть `break_progress_engine.py` статус `DEPRECATED`.
4. Удалить `isinstance` проверки из `compute_continuous_drift` и `apply_drives_mutation`.

## Key ADR Content

### Проблема
1. **Мёртвый Котёл:** Аффективный пайплайн не вызывался в idle-тиках. `prediction_error` всегда был `0.0`. TIFL не получал топлива.
2. **Отсутствие Формы:** ICDF (TIFL-002) давал текучесть, но не давал устойчивости. Личность могла бесконечно дрейфовать, не становясь "кем-то".
3. **Type-Domain Mismatch:** `TickOrchestrator` работает с `dict` (`npc_raw`), а `break_progress_engine` ожидал `NPCState`. Прямая передача вела к `AttributeError`.

### Решение
1. **Воскрешение Контура:** Внедрён вызов Котла в idle-путь.
2. **Identity Constraint Layer (ICL):** Введена фиксированная топология психики (`DRIVE_COUPLING`). Антагонистичные драйвы создают внутреннее напряжение. Сила релаксации (градиентный спуск по энергии напряжения) толкает личность к аттракторам (архетипам).
3. **Dual-Type Patch:** Функции TIFL научились понимать как объекты, так и словари через `isinstance`. Это временный протез.

### Каузальные запреты (инварианты)
1. **Закон Непрерывности Котла:** `_run_affective_pipeline` ОБЯЗАН вызываться в каждом тике. Удаление этого вызова из idle-пути — архитектурное преступление, замораживающее эволюцию личности.
2. **Фиксированная Топология:** Матрица `DRIVE_COUPLING` едина для всех NPC. Это законы физики психики, а не индивидуальные черты. Запрещено делать её адаптивной без веских runtime-доказательств (Устав §ENIGMA-002).
3. **Технический Долг (CNSRL):** Использование `isinstance(dict | NPCState)` — это узаконенный архитекурный хак. Следующий ADR (Canonical State Unification Layer) обязан устранить эту дуальность.


Files: N/A
