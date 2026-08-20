# ADR-TIFL-001 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-TIFL-001` [STANDARD] **Temporal Identity Formation Layer**
### ADR-PRE-FLIGHT CHECKLIST: ADR-TIFL-001 (Temporal Identity Formation Layer)

**1. Тип АДР:** ONTOLOGY (ADR-O). Переход от символьной мутации личности к непрерывной каузальной адаптации.

**2. Затронутые домены:**
*   `npc/identity` (Внедрение непрерывного дрейфа `drives_base`)
*   `causality/pipeline` (Проброс `prediction_error` и `dominant_drive` в движок мутации)

**3. Связанные потребители (Downstream):**
*   `break_progress_engine.py` — Добавление функции `compute_continuous_drift`.
*   `tick_orchestrator.py` — Точка вычисления дрейфа на основе `prediction_error`.
*   `DecisionHub` — Будет читать уже обновлённые `drives_base` на следующем тике.

**4. Бюджет ресурсов:**
*   **RAM:** 0.
*   **Tick Latency:** +0.1ms (вычисление микродельт).
*   **Behavior:** Кардинальное изменение. NPC, постоянно сталкивающийся с угрозами, будет постепенно становиться параноиком (`fear_drive` растёт), даже если ни разу не получил острый шок ("will_broken").

**5. Откат:** Удалить вызов `compute_continuous_drift` из `tick_orchestrator`.

**6. Регрессия:**
*   `test_prediction_error_causes_fear_drift.py` — NPC с высоким `prediction_error` по оси Threat получает микроприрост `fear_drive` каждый тик.
*   `test_identity_rigidity_blocks_drift.py` — Высокий `identity_rigidity` (много травм) делает микродрейф близким к нулю.
*   `test_redirect_reinforces_drive.py` — Победивший драйв (например, Контроль) получает микроусиление от успеха (отрицательный `prediction_error`).

---

### ХИРУРГИЧЕСКИЕ РАЗРЕЗЫ ADR-TIFL-001

#### РАЗРЕЗ 1: Контур Хронического Дрейфа (Новая математика)

Мы не трогаем `TRAUMA_TOPOLOGY`. Мы добавляем функцию непрерывной адаптации. Если мир постоянно бьёт по ожиданиям, личность подстраивается.

Файл: backend/app/services/npc/break_progress_engine.py

БЫЛО (конец файла):
```python
    # Ренормализация (Закон Сохранения Я)
    total = sum(state.drives_base.values())
    if total > 0:
        state.drives_base = {k: v / total for k, v in state.drives_base.items()}
```

СТАЛО (добавляем в конец):
```python
    # Ренормализация (Закон Сохранения Я)
    total = sum(state.drives_base.values())
    if total > 0:
        state.drives_base = {k: v / total for k, v in state.drives_base.items()}


def compute_continuous_drift(state: 'NPCState', prediction_error: float, dominant_drive: str) -> Dict[str, float]:
    """
    ADR-TIFL-001: Контур Хронического Дрейфа.
    Непрерывная адаптация личности к ошибкам модели мира.
    Если мир постоянно неожидан на оси X, драйв, отвечающий за ось X, растёт.
    Успех (отсутствие ошибки) слегка снижает драйв (привыкание).
    """
    if not dominant_drive or dominant_drive == "neutral" or prediction_error < 0.01:
        return {}

    # Пластичность (из инверсии rigidity). Травмированные личности адаптируются медленнее.
    rigidity = 0.5 
    if hasattr(state, 'psyche'):
        if isinstance(state.psyche, dict):
            rigidity = state.psyche.get("identity_rigidity", 0.5)
        elif hasattr(state.psyche, 'identity_rigidity'):
            rigidity = state.psyche.identity_rigidity
            
    plasticity = max(0.1, 1.0 - rigidity)
    
    # Скорость обучения (очень медленная, это фоновый процесс)
    LEARNING_RATE = 0.005 
    
    drifts = {}
    for drive in state.drives_base.keys():
        if drive == dominant_drive:
            # Ошибка усиливает доминантный драйв (мир требует внимания к этой оси)
            drifts[drive] = prediction_error * LEARNING_RATE * plasticity
        else:
            # Привыкание: если ошибки нет, драйв слегка снижается (энтропия внимания)
            drifts[drive] = -0.0005 * plasticity 
            
    return drifts
```

#### РАЗРЕЗ 2: Подключение телеметрии (TickOrchestrator)

Теперь мы должны вызвать `compute_continuous_drift` в тот момент, когда у нас есть `prediction_error` и `dominant_drive` (которые мы спасли в ADR-O-205). Мы применяем дрейф напрямую к стейту, как фоновый процесс.

Файл: backend/app/services/tick_orchestrator.py
*(Вставка идёт сразу после вычисления `prediction_error = delta` и `dominant_drive`)*

БЫЛО:
```python
            delta = pk_load - prev_memory  # Ошибка предсказания (Surprise)
```

СТАЛО:
```python
            delta = pk_load - prev_memory  # Ошибка предсказания (Surprise)
            
            # ADR-TIFL-001: Temporal Identity Formation.
            # Непрерывный дрейф личности на основе ошибки модели мира.
            _abs_error = abs(delta)
            if _abs_error > 0.05 and entity_id != "player":
                from app.services.npc.break_progress_engine import compute_continuous_drift, apply_drives_mutation
                _drifts = compute_continuous_drift(
                    state=npc_raw, # Передаём текущий стейт
                    prediction_error=_abs_error,
                    dominant_drive=_dominant_drive # Из ADR-O-205
                )
                if _drifts:
                    # Применяем микромутацию. Она будет закоммичена в Phase 10.
                    apply_drives_mutation(npc_raw, _drifts)
```

---

### ИТОГ: Замыкание контура Эволюции

1.  **CPA** дал нам чистый `prediction_error`.
2.  **PLS** дал нам `dominant_drive` (причину).
3.  **TIFL** связывает их с `drives_base`.


Files: N/A
