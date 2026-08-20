# ADR-123 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-123` [STANDARD] **VITAL STATE INJURY BRIDGE**
# ADR-123: Vital State Evaluator & Injury-Physiology Bridge

## Статус: ПРИНЯТ

## Контекст

Смерть в ENIGMA реализовалась через `if hp <= 0: status = "dead"` (combat_math.py:271).
Это нарушает §ENIGMA-001: уничтожает причинные цепочки в момент удара.

InjuryDTO создавались ImpactEngine с `critical_effects=("bleeding",)`, но **никто не читал
injuries обратно**. Injuries — мёртвые данные. Разрыв причинности:

```
ImpactEngine → InjuryDTO → [ПРОВАЛ] → BodyState
```

## Решение

### 1. Vital State Evaluator (domain/vital_state.py)

Три независимые оси оценки организма:

| Ось | Функция | Возвращает |
|-----|---------|-----------|
| Жизнь | `evaluate_vital_state(body_state)` | `LifeStatus.ALIVE` / `DEAD` |
| Сознание | `is_conscious(body_state)` | `bool` |
| Дееспособность | `is_capable(body_state)` | `bool` |

Смешивание осей в один enum — архитектурная ошибка (NPC может быть ALIVE + UNCONSCIOUS + INCAPACITATED).

**Переходный слой:** Смерть только от кровопотери (единственный существующий процесс).
Фантомная онтология (brain_integrity, heart_function) **запрещена** до появления причинного источника.

### 2. InjuryProcessor (services/combat/injury_processor.py)

Мост Injury → Physiology. Свойства ран вместо строковых флагов:

```
Старый путь (запрещён):
    if "bleeding" in critical_effects:
        blood_loss_delta = severity * RATE

Новый путь:
    bleeding_rate = structural_damage * zone_rate * damage_type_modifier
```

Физическая реальность раны (зона, тип, глубина) определяет эффект, не строковый тег.

### 3. Интеграция в пайплайн

- InjuryProcessor зарегистрирован как IdleTickHandler перед DecayHandler
- StateApplicator записывает `body_state["life_status"]` после PHYSIOLOGY domain
- DecisionHub блокирует DEAD/UNCONSCIOUS через guard в начале compute()

## Причинная цепочка (итог)

```
Impact → Injury → InjuryProcessor(+blood_loss/tick) → DeltaBuffer
→ StateApplicator → body_state["life_status"] → DecisionHub guard
```

Динамика с DecayHandler (свёртывание):
- Тяжёлая рана: кровотечение >> свёртывание → смерть
- Средняя рана: кровотечение ≈ свёртывание → стабильная кровопотеря
- Лёгкая рана: кровотечение << свёртывание → восстановление

## Последствия

### Положительные
- Смерть = процесс, не событие. Между ударом и смертью — окно для спасения
- Injury становится причиной с длительностью (каждый тик производит эффект)
- Увеличивается количество долгоживущих причинных цепочек (§ENIGMA-001)

### Риски
- `_BLOOD_LOSS_FATAL = 0.9` — переходный порог. Когда появятся другие процессы
  (удушье, отравление), evaluator должен учитывать их
- `life_status` вычисляется только после PHYSIOLOGY domain. TODO: перенести в
  end-of-tick reconciliation phase

## Архитектурные запреты

- ❌ `hp <= 0` как источник смерти
- ❌ `shock_impulse >= 0.95` как источник смерти (шок — сигнал, не процесс)
- ❌ `brain_integrity`, `heart_function`, `respiration` без причинного источника
- ❌ `"dead"` в `body_state["statuses"]` (DOUBLE TRUTH с life_status)
- ❌ InjuryProcessor читает строковые флаги из critical_effects

## Файлы

| Файл | Изменение |
|------|-----------|
| `domain/vital_state.py` | Создан |
| `services/combat/injury_processor.py` | Создан |
| `services/game_loop/__init__.py` | +2 строки (регистрация InjuryProcessor) |
| `services/npc/state_applicator.py` | +импорт, +8 строк (life_status evaluation) |
| `services/npc/decision_hub.py` | +импорт, +14 строк (vital state guard) |
| `services/game/combat_math.py` | МЁРТВЫЙ КОД (apply_damage не вызывается) |

## Smoke Tests

- `evaluate_vital_state()` — ALIVE/DEAD переходы
- `is_conscious()` — порог сознания
- `is_capable()` — порог дееспособности
- `InjuryProcessor.handle()` — кровотечение из ран
- `_compute_bleeding_rate()` — зональные/типовые модификаторы
- DecisionHub guard — DEAD/UNCONSCIOUS → IDLE


Files: N/A
