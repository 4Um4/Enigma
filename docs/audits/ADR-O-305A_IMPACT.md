# ADR-O-305A Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-O-305A` [STANDARD] **IMPACT**
# ADR-O-305A Impact Audit: Evidence Semantics
> Этот файл — детальный аудит контракта L1 → L1.5. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## 1. Контракт DTO (Вход: L1)

```python
@dataclass(frozen=True)
class TraitDriftEvent:
    tick_id: int
    target_id: str          # NPC, испытывающий давление
    source_id: str          # Источник давления (обязательно, не None)
    effect_value: float     # Нормализованный направленный вектор (-1.0 до 1.0). Знак назначает создатель события.
    event_type: str         # Provenance only (physical_damage, social_aid). НЕ ИСПОЛЬЗУЕТСЯ в формулах.
    observation_weight: float # Вес наблюдения (0.0 до 1.0). Учитывает мембраны (расстояние, видимость).
```

## 2. Контракт DTO (Выход: L1.5)

```python
@dataclass(frozen=True)
class EvidenceOfPersistence:
    target_id: str
    source_id: str
    cumulative_effect: float
    frequency_per_tick: float
    behavior_variance: float
    last_seen_tick: int
```

## 3. Математическая Семантика

Все формулы применяются к списку `TraitDriftEvent` для конкретной пары `(target_id, source_id)` внутри скользящего окна `OBSERVATION_WINDOW`.

### 3.1 `cumulative_effect` (Кумулятивный эффект)
Взвешенная сумма воздействий.
`cumulative_effect = Σ (event.effect_value * event.observation_weight)`

### 3.2 `frequency_per_tick` (Плотность событий)
`frequency_per_tick = event_count / OBSERVATION_WINDOW`

### 3.3 Шумоподавление (Window-Invariant Noise Filter)
Фильтрация шума не зависит от размера окна. Используется абсолютный порог количества событий.
`if event_count < MIN_EVENTS_FOR_PERSISTENCE (e.g., 5): return None`

### 3.4 `behavior_variance` (Нестабильность источника)
Метрика осцилляции вектора воздействия. Вычисляется как доля смен знака (`sign_flip_ratio`).
1. `signs = [sign(e.effect_value) for e in events]`
2. `flips = sum(1 for i in range(1, len(signs)) if signs[i] != signs[i-1])`
3. `behavior_variance = flips / max(1, len(events) - 1)`

## 4. Статистические Инварианты (Архитектурные Защиты)

1. `PatternDetector` детерминирован.
2. `PatternDetector` не читает `personality` / `drives`.
3. `PatternDetector` не читает `beliefs`.
4. `PatternDetector` не читает `emotions`.
5. `PatternDetector` не использует `event_type` в математических формулах (только как метаданные).
6. `PatternDetector` зависит только от: `source_id`, `tick_id`, `effect_value`, `observation_weight`.

## 5. Downstream Consumers
- `BeliefCrystallizationEngine` (L2.5) — единственный легитимный потребитель `EvidenceOfPersistence`. Engine применяет формулу Асимметричной Травмы (ADR-O-307), используя `behavior_variance` как триггер пересмотра убеждения.

## 6. Sandbox Tests Plan (8 Контрактов)
1. **Noise Filtering:** Событий меньше `MIN_EVENTS` → Evidence не генерируется.
2. **Persistence Detection:** `event_count` >= `MIN_EVENTS` → Evidence генерируется.
3. **Behavior Variance (Relative):** Чередование +/- даёт `variance` строго выше, чем только +/-.
4. **L1 Append-Only Independence:** Попытка записи в L1 из Detector → Краш.
5. **Source Isolation:** `source_id=None` → Игнор/Краш. Запрет скалярного страха.
6. **Psychological Purity:** В DTO `EvidenceOfPersistence` нет полей `trait/emotion`.
7. **Personality Independence:** Разные `drives` у NPC → идентичный Evidence.
8. **Temporal Stability:** Перемешивание порядка событий в окне → идентичный `cumulative_effect` и `variance`.

## 7. Rollback
Удалить класс `PatternDetector` и DTO `EvidenceOfPersistence`. L1 Chronicle остаётся без агрегатора, Belief Engine отключается.


Files: N/A
