# ADR-131 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-131` [STANDARD] **IMPACT**
# ADR-131 Impact Audit: Трёхосевая Модель Напряжения + NDA Engine

**Дата:** 09.06.2026
**Спринт:** S75→S76
**Тип:** ONTOLOGY (ADR-O) — изменение семантики нарративного слоя
**Статус:** Утверждён к реализации

---

## 1. Постановка проблемы

Система имеет три несинхронизированных источника "напряжённости", каждый из которых отвечает на свой вопрос:

| Ось | Источник | Вопрос | Тип времени |
|-----|----------|--------|-------------|
| ST (State Tension) | `affective_load` NPC | Что реально происходит с миром? | Интеграл (∫) |
| ET (Event Tension) | `stress_delta + fear_delta` из DecisionResult | Что случилось прямо сейчас? | Производная (Δ) |
| NE (Narrative Entropy) | `AvatarPresentationAssembler` (pain/coherence/noise) | Как это должно ощущаться? | Статистический шум (σ) |

Текущее состояние: DM читает **только ET** через `_compute_tension()`. Это создаёт split-brain:

- NPC спокойно (`affective_load=0.0`), DM пишет "Напряжение растёт быстро — близко к кульминации"
- NPC напуган (`affective_load=0.8`), DM пишет "Сцена спокойная"
- Игрок в шоке (coherence=0.3), DM не учитывает искажение восприятия

---

## 2. Решение: Двухуровневая архитектура

### Уровень 1: TensionSynthesizer (физика)

Вычисляет три оси независимо. Никакого смешивания координатных систем.

```python
@dataclass(frozen=True)
class ThreeAxisTension:
    state_tension: float      # ST: mean(affective_load) — интеграл
    event_tension: float      # ET: sum(stress_delta + fear_delta) / 0.5 — производная
    narrative_entropy: float  # NE: 1.0 - cognitive_coherence — шум восприятия
    
    # Доминирующая ось — какая реальность управляет сценой
    dominant_axis: Literal["ST", "ET", "NE"]
    
    # Финальная напряжение сцены — после арбитража NDA
    composite: float
    
    # Мета: какие оси были подавлены
    suppression: Dict[str, float]
```

### Уровень 2: NDA Engine (онтология)

Арбитр, решающий **какая ось становится правдой сцены**. Не агрегатор, а селектор.

```python
@dataclass
class NDAResolution:
    """Результат арбитража реальностей."""
    dominant_axis: Literal["ST", "ET", "NE"]
    amplification: Dict[str, float]   # ось → множитель усиления
    suppression: Dict[str, float]     # ось → множитель подавления
    composite: float                  # финальное напряжение
    rationale: str                    # для CDS диагностики
```

Режимная логика NDA:

| Ситуация | dominant_axis | ST | ET | NE | composite |
|----------|--------------|----|----|----|----|
| Боевой всплеск | ET | frozen | ×1.5 | suppressed | ET × 1.5 |
| Психологический ужас | ST | ×1.0 | ~0 | amplified | ST + NE × 0.3 |
| Пустота / ожидание | NE | ~0 | ~0 | ×1.0 | NE × 0.5 |
| Стабильный страх | ST | ×1.0 | ~0 | ~0 | ST |
| Раненый игрок в тишине | ST+NE | ×1.0 | ~0 | ×0.5 | ST + NE × 0.2 |

---

## 3. Инварианты (КАТЕГОРИЧЕСКИЕ)

### Инвариант 1: ST — Якорь Реальности

```
IF ST ≥ 0.6 AND composite < 0.3 → АРХИТЕКТУРНЫЙ БАГ
```

Мир реально напряжён → DM не может описывать спокойствие, даже если нет событий и игрок спокоен.

### Инвариант 2: NE — Потолок Искажения

```
IF ST < 0.1 AND ET < 0.1 THEN NE_composite_cap = 0.4
```

Чистое искажение восприятия не создаёт реальную напряжённость выше 0.4. Игроку кажется, но мир объективно спокоен.

### Инвариант 3: ET — Затухающий Всплеск

```
ET всегда затухает за 1 тик. ET не имеет памяти.
```

Без подкрепления от ST событийная напряженность исчезает.

### Инвариант 4: NDA — Не Может Создавать Реальность

```
NDA НЕ имеет права генерировать tension из ничего.
composite > 0.0 возможен ТОЛЬКО если хотя бы одна ось > 0.0.
```

---

## 4. Формулы

### TensionSynthesizer (Уровень 1)

```python
def compute_three_axis(npcs, decisions, avatar_state) -> ThreeAxisTension:
    # ST: честный интеграл аффекта (уже существует, честно затухает после S75)
    _npc_loads = [n.get('affective_load', 0.0) for n in npcs if n.get('npc_id') != 'player']
    ST = sum(_npc_loads) / len(_npc_loads) if _npc_loads else 0.0
    
    # ET: мгновенные дельты (текущая формула, сохраняется)
    raw_stress = sum(abs(collapse(d.deltas).stress_delta) for d in decisions)
    raw_fear = sum(abs(collapse(d.deltas).fear_delta) for d in decisions)
    ET = min(1.0, (raw_stress + raw_fear) / 0.5)
    
    # NE: искажение восприятия игрока (из AvatarStateDTO)
    NE = 1.0 - getattr(avatar_state, 'cognitive_coherence', 1.0)
    
    return ThreeAxisTension(ST=ST, ET=ET, NE=NE, ...)
```

### NDA Engine (Уровень 2)

```python
def resolve(tension: ThreeAxisTension) -> NDAResolution:
    ST, ET, NE = tension.state_tension, tension.event_tension, tension.narrative_entropy
    
    # Режимная логика: кто доминирует
    if ET > 0.6 and ET > ST * 2:
        # Боевой всплеск: событие подавляет интеграл
        return NDAResolution(
            dominant_axis="ET",
            amplification={"ET": 1.5},
            suppression={"ST": 0.5, "NE": 0.3},
            composite=min(1.0, ET * 1.5),
            rationale="event_spike"
        )
    
    if ST > 0.3:
        # Стабильный страх: интеграл — якорь
        _ne_contrib = NE * 0.3 if NE > 0.2 else 0.0
        return NDAResolution(
            dominant_axis="ST",
            amplification={"ST": 1.0, "NE": 0.3 if NE > 0.2 else 0.0},
            suppression={"ET": 0.5},
            composite=min(1.0, ST + _ne_contrib),
            rationale="state_anchored"
        )
    
    if NE > 0.3 and ST < 0.1 and ET < 0.1:
        # Пустота с искажением: потолок 0.4
        return NDAResolution(
            dominant_axis="NE",
            amplification={"NE": 0.5},
            suppression={"ST": 1.0, "ET": 1.0},
            composite=min(0.4, NE * 0.5),
            rationale="perception_only_capped"
        )
    
    # По умолчанию: взвешенная сумма
    composite = 0.5 * ST + 0.3 * ET + 0.2 * NE
    return NDAResolution(
        dominant_axis="ST" if ST >= max(ET, NE) else ("ET" if ET >= NE else "NE"),
        amplification={},
        suppression={},
        composite=min(1.0, composite),
        rationale="weighted_default"
    )
```

---

## 5. Изменённые домены

- [ ] Вербализация (DM контракт, SceneOutcomeBuilder)
- [ ] Аффект (проброс affective_load в вербализацию)
- [ ] Презентация (AvatarPresentationAssembler → NE)

## 6. Downstream потребители

- `SceneOutcomeBuilder._compute_tension()` — текущий единственный источник, будет заменён
- `SceneOutcomeBuilder._interpret_tension()` — получит composite вместо raw ET
- `DMAgent._build_contract()` — получит расширенный TensionOutcome
- `SceneContinuity.update_tension()` — получит composite как delta

## 7. Runtime Impact

- RAM: +0 (без новых аккумуляторов)
- Latency: +0.1ms на тик (одно вычисление mean из 5-10 NPC)
- LLM prompt: +0 (composite заменяет текущий ET, размер тот же)

## 8. Sandbox Tests

- `test_tension_synthesizer_three_axis` — ST/ET/NE вычисляются независимо
- `test_nda_st_anchored` — ST ≥ 0.6 → composite ≥ 0.3 (Инвариант 1)
- `test_nda_ne_capped` — ST < 0.1, ET < 0.1, NE = 1.0 → composite ≤ 0.4 (Инвариант 2)
- `test_nda_et_decays` — ET = 1.0 на тике N → ET = 0.0 на тике N+1 без подкрепления
- `test_nda_no_creation_ex_nihilo` — все оси = 0.0 → composite = 0.0 (Инвариант 4)
- `test_nda_event_spike_mode` — ET > 0.6 AND ET > ST*2 → ET доминирует
- `test_nda_state_anchored_mode` — ST > 0.3 → ST доминирует
- `test_split_brain_fixed` — affective_load=0.0, stress_delta=0.5 → composite отражает реальность

## 9. Rollback

1. Feature flag: `THREE_AXIS_TENSION = False` → откат к текущему `_compute_tension`
2. Удалить `tension_synthesizer.py` и `nda_engine.py`
3. `SceneOutcomeBuilder._compute_tension` возвращается к текущей формуле

## 10. Миграция (пошаговая)

### Шаг 1: TensionSynthesizer (без NDA)

- Создать `services/verbalization/tension_synthesizer.py`
- `_compute_tension` делегирует в `TensionSynthesizer`
- `TensionOutcome` расширяется: +`state_tension`, +`event_tension`, +`narrative_entropy`
- composite = взвешенная сумма (0.5 ST + 0.3 ET + 0.2 NE)
- Feature flag: `THREE_AXIS_TENSION = True`

### Шаг 2: NDA Engine

- Создать `services/verbalization/nda_engine.py`
- Заменить взвешенную сумму на режимную логику NDA
- Добавить `suppression` и `amplification` в TensionOutcome
- Feature flag: `NDA_ENGINE = True`

### Шаг 3: Диагностика

- `[TENSION_SYNTH]` тег логов: ST=.. ET=.. NE=.. composite=.. dominant=..
- CDS паттерн: `tension_split_brain` — composite расходится с affective_load

---

*Версия: 1.0*
*Дата: 2026-06-09*
*Автор: Architecture Session S75*
```

---

## Файл 2: Запись в ADR Registry

```
### ADR-131: Трёхосевая Модель Напряжения + NDA Engine (ONTOLOGY)

**Дата:** 2026-06-09
**Спринт:** S75→S76
**Тип:** ADR-O (Ontology)
**Статус:** Утверждён к реализации

**Проблема:** DM читает только мгновенные дельты (ET) для вычисления "напряжения сцены", полностью игнорируя интеграл аффекта (ST) и искажение восприятия игрока (NE). Результат: split-brain — NPC спокойно, DM пишет "напряжение растёт".

**Решение:** Двухуровневая архитектура:
1. **TensionSynthesizer** — вычисляет три оси независимо (ST/ET/NE)
2. **NDA Engine** — арбитр, решающий какая ось становится правдой сцены через режимную логику (не агрегацию)

**Инварианты:**
- ST ≥ 0.6 → composite ≥ 0.3 (якорь реальности)
- NE без ST/ET → composite ≤ 0.4 (потолок искажения)
- ET затухает за 1 тик (нет памяти)
- NDA не создаёт tension из ничего

**Изменённые домены:** Вербализация, Аффект, Презентация
**Feature flags:** `THREE_AXIS_TENSION`, `NDA_ENGINE`
**Откат:** Флаги в False → возврат к `_compute_tension`
**Аудит:** `docs/audits/ADR-131_IMPACT.md`
