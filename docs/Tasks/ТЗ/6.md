## ТЗ-08: CalibrationEngine — выход из pass-through

**Статус:** ❌ МЁРТВЫЙ | **Критичность:** HIGH | **Волна:** 2

---

### Суть проблемы одной строкой

CalibrationEngine вызывается каждый тик, но делает **ничего** — возвращает входные данные без изменений. L3 projection NPC скачет от тика к тику, strain не накапливается, психологические срывы невозможны.

---

### Что происходит сейчас

**Файл:** `backend/app/services/npc/calibration_engine.py` строка ~65

```python
# СЕЙЧАС (мёртвый):
def stabilize(self, l3_raw: Dict[str, float], strain_memory: Dict) -> Tuple[Dict, Dict]:
    # Pass-through: вернуть как есть
    return l3_raw, {}  # ← l3_raw без изменений, strain_memory всегда пустой
```

**Файл:** `backend/app/services/npc/npc_tick_pipeline.py`

```python
# Вызывается каждый тик — тратит CPU, не производит эффекта:
l3_stable, strain = self.calibration_engine.stabilize(l3_raw, strain_memory)
# l3_stable == l3_raw  (идентично)
# strain == {}          (всегда пусто)
```

**Что ломается:**

| Проблема | Почему |
|----------|--------|
| L3 projection скачет тик к тику | Нет сглаживания — каждый тик recalculates с нуля |
| Нет накопления strain | stress_memory всегда пустой — нет "напряжения" |
| Психологический срыв невозможен | BreakProgressEngine не получает strain как источник pressure |
| identity.yaml нарушен | DEPRECATED_FOR_SCALARS без replacement |
| CPU тратится впустую | stabilize() вызывается, но это no-op |

---

### Как должна работать калибровка

```
Тик N-1:  l3_raw = {fear: 0.3, control: 0.7}
Тик N:    l3_raw = {fear: 0.8, control: 0.4}  ← внешнее событие (нападение)

Без калибровки:
  l3_stable = {fear: 0.8, control: 0.4}  ← скачок на 0.5 за один тик

С калибровкой (EMA, alpha=0.3):
  l3_stable = {fear: 0.45, control: 0.61}  ← плавный переход
  strain = {fear: 0.35}  ← большое отклонение = накопление strain

Если strain.fear > 0.8:
  → CalibrationStrainEvent → BreakProgressEngine
  → NPC более уязвим к срыву
```

---

### Пошаговый план исправления

#### Шаг 1: Заменить pass-through на Exponential Moving Average

**Файл:** `backend/app/services/npc/calibration_engine.py`

```python
class CalibrationEngine:
    """Стабилизация L3 projection через EMA + накопление strain"""
    
    def __init__(self, alpha: float = 0.3, strain_threshold: float = 0.15):
        self.alpha = alpha              # скорость адаптации (0.3 = умеренная)
        self.strain_threshold = strain_threshold  # порог для накопления strain
        self._previous_l3: Dict[str, float] = {}  # предыдущий стабильный L3

    def stabilize(
        self,
        l3_raw: Dict[str, float],
        strain_memory: Dict[str, float],
    ) -> Tuple[Dict[str, float], Dict[str, float]]:
        """
        EMA сглаживание + strain accumulation.
        
        Инвариант: l3_stable меняется плавно (не скачет).
        Если l3_raw отклоняется от l3_stable > threshold — strain растёт.
        """
        l3_stable = {}
        new_strain = dict(strain_memory)  # копия текущего strain
        
        for drive_name, raw_value in l3_raw.items():
            prev_stable = self._previous_l3.get(drive_name, raw_value)
            
            # EMA: плавное сглаживание
            stable_value = self.alpha * raw_value + (1 - self.alpha) * prev_stable
            l3_stable[drive_name] = round(stable_value, 4)
            
            # Strain: измеряем отклонение
            deviation = abs(raw_value - prev_stable)
            if deviation > self.strain_threshold:
                # Накапливаем strain
                current_strain = new_strain.get(drive_name, 0.0)
                new_strain[drive_name] = round(
                    current_strain + deviation * 0.5, 4
                )
            else:
                # Затухание strain (медленное)
                current_strain = new_strain.get(drive_name, 0.0)
                new_strain[drive_name] = round(current_strain * 0.9, 4)
                if new_strain[drive_name] < 0.01:
                    del new_strain[drive_name]  # очистить мелкий strain
        
        # Сохранить для следующего тика
        self._previous_l3 = dict(l3_stable)
        
        return l3_stable, new_strain
```

---

#### Шаг 2: Передавать strain в BreakProgressEngine

**Файл:** `backend/app/services/npc/break_progress_engine.py`

```python
# СЕЙЧАС: pressure вычисляется только из fear, stress, social_pressure
def calculate(self, npc_state, ...):
    pressure = (
        npc_state.fear * 0.4 +
        npc_state.stress * 0.3 +
        social_pressure * 0.3
    )
    # strain НЕ учтён

# ИСПРАВИТЬ: добавить strain как множитель уязвимости
def calculate(self, npc_state, strain_memory: Dict[str, float] = None, ...):
    base_pressure = (
        npc_state.fear * 0.4 +
        npc_state.stress * 0.3 +
        social_pressure * 0.3
    )
    
    # Strain увеличивает уязвимость к срыву
    total_strain = sum(strain_memory.values()) if strain_memory else 0.0
    vulnerability_multiplier = 1.0 + total_strain * 0.5  # strain=1.0 → x1.5
    
    pressure = base_pressure * vulnerability_multiplier
    
    # Если strain критический — сигнал к срыву
    if total_strain > 2.0:
        self._emit_strain_crisis_event(npc_state.npc_id, total_strain)
    
    return pressure
```

---

#### Шаг 3: Подключить strain в npc_tick_pipeline

**Файл:** `backend/app/services/npc/npc_tick_pipeline.py`

```python
# СЕЙЧАС (сломано):
l3_stable, strain = self.calibration_engine.stabilize(l3_raw, strain_memory)
# strain всегда {} — никуда не передаётся

# ИСПРАВИТЬ: передать strain в BreakProgressEngine
l3_stable, strain_memory = self.calibration_engine.stabilize(l3_raw, strain_memory)

# Сохранить strain на NPCState для следующего тика
npc_state.strain_memory = strain_memory

# Передать в BreakProgressEngine
if hasattr(npc_state, 'will_state_override') and npc_state.will_state_override != WillState.BROKEN:
    break_result = self.break_progress_engine.calculate(
        npc_state=npc_state,
        strain_memory=strain_memory,  # ← НОВОЕ
    )
```

---

#### Шаг 4: Добавить strain_memory в NPCState

**Файл:** `backend/app/models/npc_state.py`

```python
@dataclass
class NPCState:
    # ... существующие поля ...
    
    # НОВОЕ: память напряжения калибровки
    strain_memory: Dict[str, float] = field(default_factory=dict)
```

---

#### Шаг 5: Генерировать CalibrationStrainEvent

```python
# В calibration_engine.py или отдельном файле:

class CalibrationStrainEvent:
    """Событие: strain драйва превысил критический порог"""
    npc_id: str
    drive_name: str
    strain_value: float
    total_strain: float

# В stabilize():
if new_strain.get(drive_name, 0) > 0.8:
    self.event_bus.publish(CalibrationStrainEvent(
        npc_id=npc_id,
        drive_name=drive_name,
        strain_value=new_strain[drive_name],
        total_strain=sum(new_strain.values()),
    ))
```

**Подписчики события:**
- `BreakProgressEngine` — увеличить vulnerability
- `DM Agent` — описать признаки напряжения в нарративе
- `SceneEventEmitter` — показать визуальные признаки (дрожь, пот и т.д.)

---

#### Шаг 6: Добавить путь восстановления из WillState.BROKEN

**Файл:** `backend/app/services/npc/break_progress_engine.py`

```python
# СЕЙЧАС: нет выхода из BROKEN — спираль смерти
# ЕСЛИ will_state == BROKEN → pressure продолжает расти → identity_integrity → 0

# ИСПРАВИТЬ: добавить recovery logic
def calculate(self, npc_state, strain_memory=None, ...):
    pressure = base_pressure * vulnerability_multiplier
    
    if npc_state.will_state_override == WillState.BROKEN:
        # Сломанный NPC не накапливает NEW pressure, но медленно восстанавливается
        recovery_rate = 0.02  # медленное восстановление
        
        if npc_state.identity_integrity < 1.0:
            npc_state.identity_integrity += recovery_rate
        
        # Strain затухает быстрее для сломанного NPC (катарсис)
        if strain_memory:
            for key in strain_memory:
                strain_memory[key] *= 0.8  # быстрое затухание
        
        # Условие восстановления
        if npc_state.identity_integrity > 0.3 and total_strain < 0.5:
            npc_state.will_state_override = WillState.RECOVERING  # новый статус
            # Через N тиков RECOVERING → норма
        
        return 0.0  # нет давления пока сломан
```

---

#### Шаг 7: Обновить identity.yaml

```yaml
# ЗАМЕНИТЬ:
#   CalibrationEngine: DEPRECATED_FOR_SCALARS
# НА:

CalibrationEngine:
  status: ACTIVE
  adr: ADR-O-800
  code_ref: calibration_engine.py
  algorithm: Exponential Moving Average (alpha=0.3)
  strain:
    description: "Накопление отклонений l3_raw от l3_stable"
    threshold: 0.15          # порог для начала накопления
    decay_rate: 0.9          # затухание за тик
    crisis_threshold: 0.8    # порог для CalibrationStrainEvent
    vulnerability_factor: 0.5 # множитель для BreakProgressEngine
  invariant: |
    l3_stable изменяется плавно (EMA)
    strain накапливается при резких отклонениях
    высокий strain увеличивает уязвимость к срыву
    WillState.BROKEN имеет путь восстановления
```

---

### Настройки alpha — когда менять

| alpha | Поведение | Когда использовать |
|-------|-----------|-------------------|
| 0.1 | Очень медленная адаптация | NPC с высокой ригидностью (старые, консервативные) |
| 0.3 | Умеренная адаптация | **По умолчанию** для большинства NPC |
| 0.5 | Быстрая адаптация | NPC с низкой ригидностью (дети, нестабильные) |
| 0.8 | Почти без сглаживания | NPC в состоянии паники (короткий период) |

```python
# Можно брать alpha из архетипа:
alpha = npc_state.identity_rigidity_to_alpha()
# identity_rigidity=0.9 → alpha=0.1 (медленно меняется)
# identity_rigidity=0.2 → alpha=0.5 (быстро меняется)
```

---

### Порядок исправления

| # | Шаг | Время |
|---|-----|-------|
| 1 | EMA в CalibrationEngine.stabilize() | 30 мин |
| 2 | strain_memory в NPCState | 5 мин |
| 3 | Передача strain в BreakProgressEngine | 20 мин |
| 4 | CalibrationStrainEvent | 20 мин |
| 5 | Recovery path из WillState.BROKEN | 30 мин |
| 6 | Обновить identity.yaml | 10 мин |
| 7 | Тесты | 30 мин |

**Итого:** ~2.5 часа

---

Давать следующее? Это **ТЗ-02: SpatialRegistry — кросс-локационная навигация** (зависит от ТЗ-06, начало Волны 3).