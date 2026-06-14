# ADR-O-207 Impact Audit: Runtime Ontology Collapse Plan (ROCP v1.1)

> Этот файл — детальный аудит перехода к строгой 4+1-слойной онтологии рантайма и уничтожению Dual-Type State.
> Единый атлас всех ADR: `docs\Tasks\ADR (Architecture Decision Records).md`

## Changed Domains
- **core/runtime** (Введение 4+1 слойной модели, уничтожение `isinstance(dict | NPCState)`)
- **causality/pipeline** (Переход к единой точке материализации L1 и чистому редьюсеру L3/L4)
- **npc/identity** (Очистка TIFL от протезов, строгая типизация)
- **persistence** (Разделение Transport и Runtime форматов)

## Downstream Consumers
- `tick_orchestrator.py` — Переписывание цикла на работу с материализованным `NPCState` (L1/L2).
- `state_applicator.py` — Превращение в pure reducer (L3), удаление `from_legacy` внутри.
- `break_progress_engine.py` — Удаление `isinstance`, строгий приём `NPCState`.
- Все потребители `npc_raw` — Перевод на чтение `NPCState`.

## Runtime Impact
- **RAM:** Увеличение на ~10-20% в пике тика (материализация объектов L1). Сборщик мусора освободит память на L4.
- **Tick Latency:** Увеличение на микросекунды (L5 Post-Commit Validation), но выигрыш на устранении ручных `.get()` и полиморфизма.
- **Behavior:** Кардинальное изменение. Устранён риск тихой порчи данных. Система становится детерминированной монадой состояния.

## Rollback
1. Вернуть `from_legacy` в `StateApplicator`.
2. Вернуть `isinstance(dict | NPCState)` в `break_progress_engine`.
3. Вернуть чтение `npc_raw.get(...)` в `TickOrchestrator`.
4. Удалить `OntologyViolationError` и L5 Validation Gate.

## Sandbox Tests
- `test_l1_materialization.py` — Доказательство, что `dict` конвертируется в `NPCState` строго один раз.
- `test_l3_pure_reducer.py` — `StateApplicator` не содержит вызовов `from_legacy` и работает как fold-функция.
- `test_l5_invariant_guard.py` — Нарушение Закона Сохранения Я (`sum(drives) != 1.0`) или выход за границы диапазонов вызывает `OntologyViolationError`.
- `test_tifl_dict_breach.py` — Передача `dict` в `compute_continuous_drift` вызывает `OntologyViolationError`.

## Key ADR Content

### Проблема
Система страдает от Dual-Type State Schizophrenia. `TickOrchestrator` мыслит словарями (`npc_raw`), ядро — объектами (`NPCState`). Граница между ними размазана по времени исполнения, что порождает паразитные `isinstance`, ручные `.get()` и мутации сырого слоя в обход доменной логики. Кроме того, отсутствие инвариантного контроля на выходе позволяет системе самоконсистентно деградировать (например, нарушение Закона Сохранения Я).

### Решение
Переход к **Runtime Ontology Collapse Plan (ROCP v1.1)**.

1. **4+1 Слойная Онтология:**
   - **L0 (Persistence):** `dict` — только транспортный формат.
   - **L1 (Materialization):** Единственная точка конвертации `dict → NPCState`.
   - **L2 (Domain Computation):** Генерация `StateDelta` на основе immutable `NPCState`.
   - **L3 (Reduction):** `NPCState + StateDelta → NPCState'` (pure fold).
   - **L4 (Commit):** `NPCState' → dict` (единственный выход).
   - **L5 (Post-Commit Validation Gate):** Структурная валидация инвариантов модели.

2. **Invariant 5 (State Authority Rule):** В любой момент времени существует ровно один authoritative representation.
3. **Invariant 7 (Post-Commit Validation Gate):** Результат редукции обязан проходить структурную валидацию (целостность графа драйвов, допустимые диапазоны). Нарушение = `OntologyViolationError`.

### Каузальные запреты (инварианты)
1. **Запрет на Dual-Mutation:** Любая мутация вне `StateDelta` → `OntologyViolationError`.
2. **Запрет на L0 в L2:** Передача `dict` в доменный слой → `OntologyViolationError`.
3. **L5 как Термостат:** `StateApplicator` не имеет права нормализовывать или "исправлять" данные. Если инвариант нарушен, L5 убивает тик.
```

---

### ХИРУРГИЧЕСКИЙ ЭТАП 2: АРХЕОЛОГИЯ ДЛЯ L5 (POST-COMMIT VALIDATION GATE)

Прежде чем я спроектирую L5 и перепишу `StateApplicator`, мне нужно вытащить из кода **все существующие инварианты и ограничения**, которые L5 будет охранять. Я не буду гадать.

Прошу запустить диагностический блок:

```powershell
# 1. Поиск всех существующих инвариантов и ограничений в NPCState
Select-String -Path "backend/app/models/npc_state.py" -Pattern "validate|clamp|assert|sum\(|0\.0.*1\.0|Invariant|conservation|0-100|0-1" | Select-Object -Property LineNumber, Line

# 2. Полная картина текущего StateApplicator (контекст редьюсера)
Get-Content backend/app/services/npc/state_applicator.py | Select-Object -Index (815..870)

# 3. Где сейчас живут законы сохранения драйвов (TIFL)
Select-String -Path "backend/app/services/npc/break_progress_engine.py" -Pattern "sum\(|conservation|mass|1\.0|clamp" | Select-Object -Property LineNumber, Line

# 4. Существующие доменные исключения (чтобы добавить OntologyViolationError в нужное место)
Get-ChildItem -Path "backend/app/domain/" -Filter "*.py" -Recurse | Select-String -Pattern "class.*Error|class.*Exception" | Select-Object -Property Path, LineNumber, Line