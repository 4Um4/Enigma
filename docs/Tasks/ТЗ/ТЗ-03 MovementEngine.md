## ТЗ-03: MovementEngine — ранения теряются между тиками

**Статус:** ⚠️ РАБОТАЕТ С БАГОМ | **Критичность:** HIGH | **Волна:** 1 (1-2 часа)

---

### Суть проблемы одной строкой

NPC получает рану в бою → ранение записывается в `body_state.injuries_by_zone` → **на следующем тике раны нет**, остаётся только `blood_loss`. PhysiologyDecayHandler логирует `[DECAY_INJURY_LOST]` как предупреждение, но ничего не делает.

---

### Что ломается

Без injuries:
- **Хронические раны не генерируют боль** — `InjuryProcessor` не находит injuries → нет `pain_delta`
- **Затухание боли неправильное** — `PhysiologyDecayHandler` не может корректно затухать боль от конкретных ран
- **Исцеление невозможно** — нельзя вылечить рану, которой нет
- **Статус "unconscious" некорректен** — боль от ран не суммируется, NPC не теряет сознание
- **Смертельная спираль наоборот** — blood_loss растёт, а источник (рана) потерян

---

### Пошаговая диагностика: ГДЕ теряются injuries

Нужно найти точку потери. Для этого — проверить каждый этап round-trip:

```
InjuryProcessor пишет в body_state
    ↓ проверить: injuries_by_zone заполнен?
StateApplicator.apply() применяет дельты
    ↓ проверить: injuries_by_zone на месте?
_state_to_dict() сериализует NPCState
    ↓ проверить: injuries включены в dict?
JsonPersistenceAdapter сохраняет на диск
    ↓ проверить: JSON содержит injuries?
JsonPersistenceAdapter загружает с диска
    ↓ проверить: injuries десериализованы?
NPCState создаётся из загруженных данных
    ↓ проверить: injuries_by_zone заполнен?
```

**Как проверить — добавить diagnostic logging:**

```python
# Временный diagnostic: добавить в 5 точках и запустить бой

# ТОЧКА 1: После InjuryProcessor (impact_engine.py)
result.injuries_by_zone = applied_injuries
logger.info(f"[DIAG-1] injuries after combat: {result.injuries_by_zone}")

# ТОЧКА 2: После StateApplicator.apply() (state_applicator.py)
logger.info(f"[DIAG-2] injuries after apply: {state.body_state.get('injuries_by_zone')}")

# ТОЧКА 3: В _state_to_dict() (player_avatar_service.py или аналог)
logger.info(f"[DIAG-3] injuries in serialized dict: {state_dict.get('body_state', {}).get('injuries_by_zone')}")

# ТОЧКА 4: После JSON save (json_persistence_adapter.py)
with open(path) as f:
    saved = json.load(f)
logger.info(f"[DIAG-4] injuries in saved JSON: {saved.get('body_state', {}).get('injuries_by_zone')}")

# ТОЧКА 5: После JSON load, перед созданием NPCState
logger.info(f"[DIAG-5] injuries after load: {loaded_body_state.get('injuries_by_zone')}")
```

Запустить бой, сделать 2 тика, посмотреть какой DIAG-N первый покажет пустой `injuries_by_zone`. Это и есть точка потери.

---

### Наиболее вероятные причины и фиксы

#### Причина А: `injuries_by_zone` содержит объекты, которые не сериализуются

```python
# ТИПИЧНАЯ ПРОБЛЕМА: injuries — это сложные объекты, не примитивы
injuries_by_zone = {
    "head": [Injury(type="laceration", severity=0.7, chronic=True, pain_rate=0.3)],
    "torso": [Injury(type="bruise", severity=0.3, chronic=False, pain_rate=0.1)],
}

# При json.dumps() → TypeError: Object of type Injury is not JSON serializable
# Если есть fallback или try/except — injuries просто пропускаются молча
```

**Фикс — явная сериализация Injury:**
```python
# В _state_to_dict() или аналогичном методе сериализации:

def _serialize_body_state(body_state: BodyState) -> dict:
    result = {
        "pain": body_state.pain,
        "fatigue": body_state.fatigue,
        "blood_loss": body_state.blood_loss,
        "shock_impulse": body_state.shock_impulse,
        "current_hp": body_state.current_hp,
        "max_hp": body_state.max_hp,
        "life_status": body_state.life_status,
        "disabled": body_state.disabled,
    }
    
    # ЯВНАЯ сериализация injuries_by_zone
    injuries_serialized = {}
    for zone, injuries in body_state.injuries_by_zone.items():
        injuries_serialized[zone] = [
            {
                "type": inj.type,
                "severity": inj.severity,
                "chronic": inj.chronic,
                "pain_rate": inj.pain_rate,
                "source": inj.source,
                "tick_created": inj.tick_created,
            }
            for inj in injuries
        ]
    result["injuries_by_zone"] = injuries_serialized
    
    return result
```

#### Причина Б: `_state_to_dict()` не включает `injuries_by_zone` вообще

```python
# ТИПИЧНАЯ ПРОБЛЕМА: метод сериализации перечисляет поля явно и забыл injuries
def _state_to_dict(self) -> dict:
    return {
        "npc_id": self.npc_id,
        "pain": self.body_state.pain,
        "fatigue": self.body_state.fatigue,
        "blood_loss": self.body_state.blood_loss,
        # ← injuries_by_zone ОТСУТСТВУЕТ!
        "emotion": self.emotion,
        ...
    }
```

**Фикс — добавить injuries_by_zone в сериализацию:**
```python
def _state_to_dict(self) -> dict:
    return {
        "npc_id": self.npc_id,
        "pain": self.body_state.pain,
        "fatigue": self.body_state.fatigue,
        "blood_loss": self.body_state.blood_loss,
        "shock_impulse": self.body_state.shock_impulse,
        "current_hp": self.body_state.current_hp,
        "max_hp": self.body_state.max_hp,
        "life_status": self.body_state.life_status,
        "injuries_by_zone": self._serialize_injuries(),  # ← ДОБАВИТЬ
        "emotion": self.emotion,
        ...
    }
```

#### Причина В: `StateApplicator.apply()` затирает injuries при частичном обновлении

```python
# ТИПИЧНАЯ ПРОБЛЕМА: StateApplicator заменяет весь body_state
# вместо merge, теряя injuries
def apply(self, state: NPCState, delta: StateDelta):
    if delta.field == "body_state":
        state.body_state = delta.new_value  # ← ПОЛНАЯ ЗАМЕНА, injuries потеряны!
```

**Фикс — merge вместо замены:**
```python
def apply(self, state: NPCState, delta: StateDelta):
    if delta.field == "body_state":
        # MERGE: обновить только изменённые поля, сохранить injuries
        current = state.body_state
        for key, value in delta.new_value.items():
            if key == "injuries_by_zone":
                # MERGE injuries, не заменять
                if value:  # если дельта содержит injuries — добавить
                    for zone, new_injuries in value.items():
                        existing = current.get("injuries_by_zone", {}).get(zone, [])
                        current["injuries_by_zone"][zone] = existing + new_injuries
            else:
                current[key] = value
        # injuries_by_zone сохранён
```

---

### Как десериализовать injuries обратно

```python
def _deserialize_body_state(data: dict) -> BodyState:
    injuries_by_zone = {}
    raw_injuries = data.get("injuries_by_zone", {})
    for zone, inj_list in raw_injuries.items():
        injuries_by_zone[zone] = [
            Injury(
                type=inj["type"],
                severity=inj["severity"],
                chronic=inj.get("chronic", False),
                pain_rate=inj.get("pain_rate", 0.0),
                source=inj.get("source", "unknown"),
                tick_created=inj.get("tick_created", 0),
            )
            for inj in inj_list
        ]
    
    return BodyState(
        pain=data["pain"],
        fatigue=data["fatigue"],
        blood_loss=data["blood_loss"],
        shock_impulse=data.get("shock_impulse", 0.0),
        current_hp=data.get("current_hp", 100),
        max_hp=data.get("max_hp", 100),
        life_status=data.get("life_status", "ALIVE"),
        injuries_by_zone=injuries_by_zone,  # ← НЕ ПУСТОЙ!
    )
```

---

### Round-trip тест (обязательный)

```python
# Создать в backend/tests/test_injury_persistence.py

import pytest

def test_injury_survives_round_trip():
    """Ранение должно пережить сериализацию + десериализацию"""
    # 1. Создать NPC с раной
    npc = create_test_npc()
    npc.body_state.injuries_by_zone["head"] = [
        Injury(type="laceration", severity=0.7, chronic=True, pain_rate=0.3)
    ]
    npc.body_state.blood_loss = 0.2
    
    # 2. Сериализовать
    data = npc_state_to_dict(npc)
    
    # 3. Проверить: injuries в dict?
    assert "injuries_by_zone" in data["body_state"]
    assert len(data["body_state"]["injuries_by_zone"]["head"]) == 1
    assert data["body_state"]["injuries_by_zone"]["head"][0]["type"] == "laceration"
    
    # 4. Десериализовать
    npc_restored = npc_state_from_dict(data)
    
    # 5. Проверить: injuries на месте?
    assert len(npc_restored.body_state.injuries_by_zone["head"]) == 1
    assert npc_restored.body_state.injuries_by_zone["head"][0].type == "laceration"
    assert npc_restored.body_state.injuries_by_zone["head"][0].severity == 0.7
    assert npc_restored.body_state.injuries_by_zone["head"][0].chronic == True

def test_injury_not_lost_after_tick():
    """Ранение должно пережить полный цикл тика"""
    # ... полный end-to-end тест с GameLoop
```

---

### Порядок исправления

| # | Шаг | Время |
|---|-----|-------|
| 1 | Добавить DIAG-логирование в 5 точках | 10 мин |
| 2 | Запустить бой, найти точку потери | 15 мин |
| 3 | Исправить сериализацию injuries_by_zone | 30 мин |
| 4 | Исправить десериализацию injuries_by_zone | 20 мин |
| 5 | Проверить StateApplicator merge-логику | 15 мин |
| 6 | Написать round-trip тест | 15 мин |
| 7 | Убрать DIAG-логирование | 5 мин |

**Итого:** ~1.5 часа, если причина А или Б (скорее всего). До 2 часов, если причина В.

---

Давать следующее? Это **ТЗ-06: WorldSnapshot — отсутствует boundary_map** (начало Волны 2).