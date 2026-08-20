# ADR-O-204 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-O-204` [STANDARD] **PHASE3 PRECONDITIONS**
# ADR-O-204

<!-- ADR-O-204 -->
> **СТАТУС:** Phase 0 🔴
>
> **Реальное состояние:** Код существует, но не активен.
>
> **План ремонта:** TBD.
>
> **Аудит:** 2026-06-19 (см. ADR_STATUS_MATRIX.md): Phase 3 Preconditions — Causal Kernel Surgery

> **Тип:** ONTO (Онтологический сдвиг — предусловия)
> **Статус:** VERIFIED
> **Сессия:** S86
> **Связанные ADR:** ADR-O-201 (Causal Kernel Architecture)

---

## 0. НАЗНАЧЕНИЕ

Этот документ фиксирует доказанное состояние системы
перед онтологической хирургией (ФАЗА 3 ADR-O-201).

Цель: после ФАЗЫ 3 иметь возможность честно сказать:

```text
Мы меняли ровно одну онтологическую вещь.
```

Если после ФАЗЫ 3 D не исчезнет — поиск резко сузится,
потому что предусловия зафиксированы.

---

## 1. ДОКАЗАННЫЕ ИНВАРИАНТЫ

### 1.1 Entity Birth Contract ✅

NPC ВСЕГДА рождается с `body_state` и `npc_id`.
4 точки входа закрыты.
SOMATIC_VETO = 0 за 99,062 comparisons.

**Артефакт:** ADR-O-201 §16 Entity Birth Contract

### 1.2 Replay Determinism ✅

```
Seed:     54321
Ticks:    2 × 10,000
Hash A:   d55c88bd563d7373eb9de59f83c3674a8eb5a6198ec85bc85a4501e51295561c
Hash B:   d55c88bd563d7373eb9de59f83c3674a8eb5a6198ec85bc85a4501e51295561c
Verdict:  MATCH
```

Мир воспроизводим бит-в-бит при контролируемой энтропии.

**Артефакт:** DriftLab Mode E (replay_determinism)

### 1.3 Topological Convergence (C=0) ✅

Оба pipeline видят один и тот же топологический мир.
0 топологических расхождений за 99,062 comparisons.

### 1.4 Ontological Integrity (E=0) ✅

Ни один NPC не теряется между pipeline.
0 онтологических расхождений за 99,062 comparisons.

### 1.5 Causal Drift Deterministic (D=100%) ✅

D=100% — не шум, не баг измерения.
Детерминированный след единственного онтологического расхождения.
D совпадает между Run A и Run B (19842 в обоих прогонах).

### 1.6 RCOC Defined ✅

RNG Consumption Order Contract формализован:

- RCOC-1: seed → идентичный мир (бит-в-бит)
- RCOC-2: изменение consumption trace = ADR-изменение
- RCOC-3: Replay determinism > call count matching

---

## 2. ЕДИНСТВЕННОЕ ОНТОЛОГИЧЕСКОЕ РАСХОЖДЕНИЕ

```text
Rule 120: Traversal creation inside apply_changes
```

Legacy создаёт traversals внутри reducer (Мутация #4).
Legacy мутирует status напрямую (Мутация #6).
EventCompiler не делает ни того, ни другого.

Это единственная точка, где расходятся реальности.
D=100% при C=0 и E=0 — это сигнатура двух физик рождения сущностей.

---

## 3. ЧТО БУДЕТ ИЗМЕНЕНО В ФАЗЕ 3

Ровно одна онтологическая вещь:

```text
Entity Birth Authority для traversals
    FROM: apply_changes (imperative, runtime mutation)
    TO:   EventCompiler (declarative, pre-compiled contract)
```

Concretely:

| Мутация | Было | Станет |
|---------|------|--------|
| #4 Traversal creation | `apply_change` создаёт `traversal_dict` | `EventCompiler` создаёт `TraversalContract(status="NEW")` |
| #6 Status mutation | `trav["status"] = "COMPLETED"` до apply | `EventCompiler` создаёт `TraversalContract(status="COMPLETED")` |

После ФАЗЫ 3:

```text
apply_changes = чистая проекция
state[t+1] = state[t] ⊕ ThickSceneChange[]
Ноль вычислений. Ноль рождения сущностей.
```

---

## 4. ЧТО НЕ БУДЕТ ИЗМЕНЕНО

- Entity Birth Contract (4 точки входа NPC) — нетронут
- SpatialService — frozen reference, нетронут
- DecisionHub — нетронут
- LifeEngine — нетронут
- Replay Determinism seed — нетронут
- DriftLab teardown order — нетронут
- Все Rules 117-137 — нетронуты (кроме 120, который ФАЗА 3 закрывает)

---

## 5. КРИТЕРИЙ УСПЕХА ФАЗЫ 3

```text
C = 0  (топологическое схождение — не должно ухудшиться)
D = 0  (целевая метрика — устранение расхождения)
E = 0  (онтологическая целостность — не должна ухудшиться)
```

За 100,000+ comparisons.

---

## 6. КРИТЕРИЙ ОТКАТА

Если после ФАЗЫ 3:
- C > 0 — откат (топология сломана)
- E > 0 — откат (сущности теряются)
- D > 0 но < 100% — расследование (новый источник drift)

Откат = `git checkout` на коммит перед ФАЗОЙ 3.

---

## 7. АРТЕФАКТЫ ВЕРИФИКАЦИИ

| Артефакт | Значение |
|----------|----------|
| Replay hash (seed=54321) | d55c88bd563d7373eb9de59f83c3674a8eb5a6198ec85bc85a4501e51295561c |
| Drift C (99k comparisons) | 0 |
| Drift E (99k comparisons) | 0 |
| Drift D (99k comparisons) | 100% (ожидаемый) |
| Tests passed | 78 causal/dual_rail/event_compiler |
| SOMATIC_VETO | 0 за 99k comparisons |

---

*Версия: 1.0*
*Сессия: S86*
*Статус: VERIFIED — ФАЗА 3 ready*


Files: N/A
