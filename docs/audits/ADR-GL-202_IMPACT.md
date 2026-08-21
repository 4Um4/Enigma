# ADR-GL-202 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-GL-202` [STANDARD] **IMPACT**
# ADR-GL-202 Impact Audit: Generative Constraint Execution Model (GCO)
> Этот файл — детальный аудит онтологического сдвига ENIGMA. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Суть сдвига
Переход от императивной симуляции (TickOrchestrator + DeltaBuffer + DRFBus) к функциональной генерации состояния (Lazy Deterministic State Reconstruction).
Мир больше не "происходит" во времени. Он вычисляется по запросу как локально согласованный срез.

## Формула Системы
```text
State(t + Δ) = GCO(Context, Δ, CausalResidue)
```

## Распределённый контракт (ADR-0 FINAL)
```text
Distributed Reality =
    set of independent GCO evaluators
    + shared Residue Ledger (append-only)
    + context-based routing (Constraint Domains)
    + Causal Lag Field (propagation delay)
```

## Consistency Model (DOM-09): Causal Lag Field (CLF)
Консистентность реальности не мгновенна. Она асимптотична по каузальному расстоянию. Информация распространяется с задержкой, определяемой физикой мира.

### Аксиома
```text
No change is globally immediate.
All changes propagate through causal lag.
```

### Механика
- **Local Writes:** Мгновенны. GCO немедленно фолдит локальный резидуум.
- **Remote Writes:** Задержаны. Инъекции приходят через `CLF(entity, context) → Δvisibility_time`.
- **Read-Your-Own-Write:** Узел видит свои записи мгновенно, чужие — только после CLF.
- **Speculative Execution:** GCO вычисляет вероятное состояние на основе оценок входящих инъекций (слухи, акустика), а при прибытии конверта корректирует реальность.
- **Фаза реальности:** В пути реальность вероятностна. При прибытии инъекции — детерминирована.

### Структуры данных
```python
class ResidueEnvelope:
    patch: ResiduePatch
    source_cd: str
    target_cd: str
    delivery_time: float
```

## Storage Layer: Causal Segment Index (CSI)
Истина системы — это поток мутаций (Residue). Хранение реализовано через Causal Segment Index (CSI).

### Структура CSI
- **Единица хранения:** `ResidueSegment`.
- **Read Path:** `State(t) = fold(Residue[t - Δk : t])`.
- **Δk (Lookback Window):** Динамическая величина, определяемая плотностью ограничений.

## Инварианты системы
1. **I1 — Локальность вычисления:** Любое `GCO.resolve()` выполняется строго внутри Constraint Domain.
2. **I2 — Единственный источник истины:** Residue Ledger (CSI).
3. **I3 — Междушардовое взаимодействие:** Только через `ResidueEnvelope` с учётом CLF.
4. **I4 — Контекст определяет место вычисления:** Маршрутизация по CD.
5. **I5 — Каузальная задержка:** Синхронизация глобального состояния асимптотична.

## Убитые онтологии
1. **Claim / DRFBus** — эфемерный кэш.
2. **CausalWorkItem / Process** — разрушают ленивость.
3. **Field / Constraint Topology** — глобальные предвычисления.
4. **Глобальный Tick / Clock** — время现在是 аргумент вычисления, а не цикл.

## Утверждённая онтология
1. **Constraint Space** — поле запретов.
2. **Causal Residue** — лог мутаций.
3. **GCO** — генерация состояния.
4. **CLF** — скорость света причинности.

## Architecture Layout
- `core/gco/` — генерация состояния + Speculative Execution.
- `core/context/` — сборка среза (CD).
- `core/residue/` — CSI + ResidueEnvelope.
- `core/state/` — кэш.
- `core/constraints/` — физика.
- `core/router/` — маршрутизация по CD.
- `core/clf/` — вычисление задержки распространения причинности.

## Rollback
Откат невозможен.
