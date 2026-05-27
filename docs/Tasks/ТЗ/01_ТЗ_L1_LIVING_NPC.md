# ТЗ: L1 ЖИВОЙ АГЕНТ — ФУНДАМЕНТ ВОСПРИЯТИЯ И ИНЕРЦИИ

**Проект:** ENIGMA Engine v0.5.5.0+  
**Спринт:** R4 (параллель с Spatial System) / R7 (приоритет после R4)  
**Архитектурное решение:** ADR-031 (WillpowerGate), ADR-037 (Affective Resonance)  
**Статус:** Исходная спецификация. Реализация в очереди.  
**Философия:** Агент — это не набор плоских статов, а инерционная физико-когнитивная система. Личность **сопротивляется** изменениям.

---

## 1. ЦЕЛЬ И МЕСТО В АРХИТЕКТУРЕ

### 1.1. Что это делает

L1 (Perception Layer Level 1) — это **ядро состояния агента**. Вводит концепт `LivingNPC` как замену плоским `Dict[str, float]` статам.

Без L1 невозможно:
- Строить восприятие (каждое событие пробивает фильтр инерции)
- Вычислять архетипы (социальный и боевой профили)
- Реализовать давление (инерция личности гасит импульсы)
- Интегрировать аффект (без базовых черт нет резонанса с травмами)

### 1.2. Связь с CAUSAL_CONTRACT

**CAUSAL_CONTRACT § 7.1:** *"Личность сопротивляется изменениям. Запрещена моментальная мутация статов."*

L1 реализует эту инерцию через `apply_delta()`:

```python
new_value = (old_value * core.rigidity) + (delta * (1 - core.rigidity))
```

Где `core.rigidity` — базовая ригидность личности (обычно 0.9). Это гарантирует, что разовое событие не ломает психику, но хроническое давление накапливается.

### 1.3. Позиция в цепочке компонентов

```
L1 (Living Inertia) ← опора
├─→ L0 (Perception) — читает состояние для фильтрации впечатлений
├─→ L2 (Behavior) — читает архетип для принятия решений
└─→ Affective System — использует core.rigidity для модификации давления
```

---

## 2. КЛЮЧЕВЫЕ СУЩНОСТИ

### 2.1. IdentityCore — Неизменяемый фундамент

Генерируется один раз при рождении NPC. **Frozen dataclass** — не меняется в runtime.

```python
from dataclasses import dataclass
from typing import Dict

@dataclass(frozen=True)
class IdentityCore:
    """
    Фундаментальные черты личности. 
    Крайне трудно поддаются изменению. Определяют форму сосуда психики.
    """
    
    # === БАЗОВЫЕ ПРЕДРАСПОЛОЖЕННОСТИ (0.0 - 1.0) ===
    # Вероятность, что агент предпочтет насилие в конфликте
    base_aggression: float = 0.3
    
    # Готовность доверять незнакомцам при первом контакте
    base_trust: float = 0.5
    
    # Базовый уровень тревожности (реактивность на угрозы)
    base_fear: float = 0.4
    
    # Склонность исследовать неизведанное, задавать вопросы
    base_curiosity: float = 0.3
    
    # === СОЦИАЛЬНАЯ КОНФИГУРАЦИЯ ===
    # Потребность в стае, обществе (0.0 = солитер, 1.0 = социот)
    social_drive: float = 0.5
    
    # Склонность подчинять других (0.0 = раб, 1.0 = тиран)
    dominance_bias: float = 0.2
    
    # Склонность подчиняться правилам и авторитетам
    compliance_bias: float = 0.6
    
    # === МЕТА-ПАРАМЕТРЫ (Инерция) ===
    # Как быстро личность адаптируется к давлению
    # 0.0 = истерик (каждое событие = перелом)
    # 1.0 = камень (ничего не трогает)
    # Типичное значение: 0.9 (трудно сломать, но возможно)
    rigidity: float = 0.9
    
    # Скорость возврата к базовым значениям в покое (per tick)
    # Пример: fear=0.8 → если нет угрозы → fear -= recovery_rate
    recovery_rate: float = 0.1
    
    # === СПЕЦИАЛЬНЫЕ МОДИФИКАТОРЫ ===
    # Мультипликатор для инверсных событий
    # (если base_fear=0.3, то шок от близости смерти будет меньше, чем у трусливого)
    resilience_multiplier: float = 1.0
```

**Пример инициализации:**
```python
# Крепкий охранник
core_guard = IdentityCore(
    base_aggression=0.7, base_trust=0.3, base_fear=0.2,
    dominance_bias=0.6, compliance_bias=0.4, rigidity=0.95
)

# Пугливая служанка
core_maid = IdentityCore(
    base_aggression=0.1, base_trust=0.7, base_fear=0.8,
    dominance_bias=0.1, compliance_bias=0.8, rigidity=0.85
)
```

### 2.2. DriveSystem — Конфликтующие потребности

**Изменяется в runtime** в зависимости от среды и физиологии. Текущее мотивационное напряжение.

```python
@dataclass
class DriveSystem:
    """
    Текущие мотивационные векторы агента.
    Изменяются через apply_delta() с инерцией core.rigidity.
    Диапазон: 0.0 - 1.0
    """
    
    # === ПЕРВИЧНЫЕ (ФИЗИОЛОГИЯ) ===
    # Угроза жизни (0.0 = безопасно, 1.0 = паника смерти)
    survival: float = 0.1
    
    # Голод (0.0 = сыт, 1.0 = умирает от голода)
    satiety: float = 0.2
    
    # Усталость (0.0 = бодр, 1.0 = валится с ног)
    rest: float = 0.1
    
    # === ВТОРИЧНЫЕ (СОЦИУМ И ВОЛЯ) ===
    # Потребность в контакте, принадлежности к группе
    social: float = 0.2
    
    # Потребность в свободе действий (растет при давлении)
    # Это т.н. "autonomy deficit" — чем больше давления, тем выше желание вырваться
    autonomy: float = 0.1
    
    # === ПРОИЗВОДНАЯ (ВЫЧИСЛЯЕТСЯ) ===
    # Общий уровень стресса (итоговое напряжение)
    # stress = (survival + (satiety + rest) / 2 + autonomy) / 3
    stress: float = 0.0
    
    def get_dominant_drive(self) -> str:
        """Возвращает имя самого напряженного драйва."""
        drives = {
            "survival": self.survival,
            "satiety": self.satiety,
            "rest": self.rest,
            "social": self.social,
            "autonomy": self.autonomy,
        }
        return max(drives, key=drives.get)
    
    def compute_stress(self) -> float:
        """Вычисляет итоговый стресс на основе конфликта драйвов."""
        # Физиологический стресс
        phys = (self.survival + self.satiety + self.rest) / 3
        # Социальный стресс
        soc = (1.0 - self.social) * 0.3  # недостаток общения
        # Волевой стресс
        vol = self.autonomy * 0.4  # давление на волю
        return min(1.0, phys + soc + vol)
```

### 2.3. BodySchema — Динамическое тело

Тело — это не просто `speed=2.0`, это **фильтр реальности** и генератор кинематики. Меняется под давлением среды (морфологический дрейф).

```python
@dataclass
class BodySchema:
    """
    Динамическое физическое и когнитивное состояние тела агента.
    Травмы меняют восприятие. Стресс меняет возможности.
    """
    
    # === ФИЗИЧЕСКИЕ ЛИМИТЫ ===
    max_velocity: float = 4.0          # Максимальная скорость (nodes/tick)
    vault_capability: float = 0.8      # Способность перепрыгивать препятствия (0.0-1.0)
    climb_capability: float = 0.8      # Способность лазить
    concealment_volume: float = 0.8    # Насколько компактно может спрятаться
    
    # === КОГНИТИВНЫЕ МОДИФИКАТОРЫ (Травмы искажают восприятие) ===
    # При панике: tunnel_vision_factor растет → видит только угрозу → пропускает аффордансы
    tunnel_vision_factor: float = 0.0  # 0.0 = норма, 1.0 = полная паника
    
    # Болевой порог (0.0-1.0). Если боль выше → глушит социальные драйвы
    pain_threshold: float = 0.5
    
    # === РЕСУРСЫ (для магии/способностей) ===
    mana_channel: float = 0.0          # -1.0 (тьма) до 1.0 (свет)
    mana_capacity: float = 0.0
```

### 2.4. ArchetypeLabel — Фазовый переход Личности

Числа (`fear=0.8`) не говорят игроку ничего. Архетип — это **ярлык фазового состояния**, который меняет лексику, микро-выражения и стиль принятия решений.

```python
from enum import Enum
from dataclasses import dataclass

class SocialArchetype(str, Enum):
    """Социальная ось: Как агент взаимодействует с социумом."""
    BROKEN = "BROKEN"           # Полная покорность, избегание контакта
    COWARD = "COWARD"           # Избегает конфликтов, прячется
    CAUTIOUS = "CAUTIOUS"       # Осторожен, но идет на контакт
    NEUTRAL = "NEUTRAL"         # Сбалансирован
    PROTECTIVE = "PROTECTIVE"   # Защищает слабых
    LEADER = "LEADER"           # Берет ответственность

class ViolenceArchetype(str, Enum):
    """Ось насилия: Как агент реагирует на угрозу/боль."""
    VICTIM = "VICTIM"           # Замирает, плачет, сдается
    SURVIVOR = "SURVIVOR"       # Бежит, защищается
    AVENGER = "AVENGER"         # Атакует в ответ
    TYRANT = "TYRANT"           # Атакует превентивно

@dataclass
class ArchetypeLabel:
    """Текущий фазовый профиль агента. Переходы происходят в конце тика."""
    social: SocialArchetype = SocialArchetype.NEUTRAL
    violence: ViolenceArchetype = ViolenceArchetype.SURVIVOR
    
    def update(self, core: IdentityCore, drives: DriveSystem) -> None:
        """
        Логика фазового перехода на основе стресса и базовых черт.
        Вызывается в конце каждого тика.
        """
        # === ОСЬ НАСИЛИЯ ===
        if drives.survival > 0.8 and core.base_aggression < 0.3:
            self.violence = ViolenceArchetype.VICTIM
            # Чем выше страх и ниже агрессия → замирает
        
        elif drives.survival > 0.6 and core.base_aggression > 0.6:
            self.violence = ViolenceArchetype.AVENGER
            # Опасность + агрессия → контратакует
        
        elif core.base_aggression > 0.8 and core.dominance_bias > 0.7:
            self.violence = ViolenceArchetype.TYRANT
            # Агрессивный и доминантный → превентивная атака
        
        else:
            self.violence = ViolenceArchetype.SURVIVOR
            # Базовое состояние
        
        # === СОЦИАЛЬНАЯ ОСЬ ===
        if drives.stress > 0.8 and core.base_fear > 0.7:
            self.social = SocialArchetype.BROKEN
            # Огромный стресс + трусость → полный коллапс
        
        elif drives.survival > 0.6 and core.base_trust < 0.3:
            self.social = SocialArchetype.COWARD
            # Опасность + недоверие → прячется
        
        elif core.dominance_bias > 0.7 and drives.stress < 0.3:
            self.social = SocialArchetype.LEADER
            # Доминантный + спокойный → берет инициативу
        
        elif core.base_fear > 0.6 and drives.social > 0.7:
            self.social = SocialArchetype.PROTECTIVE
            # Труслив, но социален → защищает слабых
        
        else:
            self.social = SocialArchetype.NEUTRAL
            # Сбалансирован
```

### 2.5. LivingNPC — Агрегат состояния

Единый контейнер, заменяющий плоский `Dict[str, float]` или разрозненные поля.

```python
@dataclass
class LivingNPC:
    """
    Агрегат состояния живого агента. 
    Не содержит логики, только данные и методы инерции.
    Это L1 восприятия — фундамент всей личности.
    """
    
    npc_id: str                                # Идентификатор
    
    # === ЯДРО (ПОСТОЯННО) ===
    core: IdentityCore = None                  # Инициализируется при создании
    
    # === СОСТОЯНИЯ (ИЗМЕНЯЮТСЯ С ИНЕРЦИЕЙ) ===
    drives: DriveSystem = None
    body: BodySchema = None
    archetype: ArchetypeLabel = None
    
    # === ОТНОШЕНИЯ (временная заглушка, будет в R8) ===
    # Интерфейс: { "player_trust": 0.5, "player_fear": 0.2, ... }
    relationship_cache: Dict[str, float] = None
    
    def __post_init__(self):
        """Инициализация default-объектов."""
        if self.core is None:
            self.core = IdentityCore()
        if self.drives is None:
            self.drives = DriveSystem()
        if self.body is None:
            self.body = BodySchema()
        if self.archetype is None:
            self.archetype = ArchetypeLabel()
        if self.relationship_cache is None:
            self.relationship_cache = {}
    
    def apply_delta(self, domain: str, attribute: str, delta: float) -> None:
        """
        Единая точка входа для изменения состояния.
        Применяет инерцию core.rigidity.
        
        Args:
            domain: "drives", "body", "archetype"
            attribute: "survival", "max_velocity", и т.д.
            delta: величина изменения (может быть отрицательной)
        
        Пример:
            npc.apply_delta("drives", "survival", 0.5)  # +0.5 к выживанию
        """
        # Получить текущее значение
        container = getattr(self, domain)
        if not hasattr(container, attribute):
            raise AttributeError(f"{domain}.{attribute} not found")
        
        current_value = getattr(container, attribute)
        
        # Применить инерцию
        weight = self.core.rigidity
        new_value = (current_value * weight) + (delta * (1 - weight))
        
        # Клэмпинг в [0.0, 1.0] (для большинства атрибутов)
        new_value = max(0.0, min(1.0, new_value))
        
        # Установить новое значение
        setattr(container, attribute, new_value)
        
        # ВАЖНО: Пересчитать производные (stress, archetype)
        self.drives.stress = self.drives.compute_stress()
        self.archetype.update(self.core, self.drives)
    
    def reset_recovery(self) -> None:
        """
        Восстановление в покое (вызывается в фазе idle / between-scenes).
        Драйвы возвращаются к базовым значениям.
        """
        for attr in ["survival", "satiety", "rest", "social", "autonomy"]:
            current = getattr(self.drives, attr)
            # Скорость восстановления определена в core
            if attr == "survival":  # Выживание восстанавливается медленнее
                recovered = current * (1.0 - self.core.recovery_rate * 0.5)
            else:
                recovered = current * (1.0 - self.core.recovery_rate)
            setattr(self.drives, attr, max(0.0, recovered))
        
        # Пересчитать производные
        self.drives.stress = self.drives.compute_stress()
        self.archetype.update(self.core, self.drives)
```

---

## 3. СВЯЗЬ С ДРУГИМИ СЛОЯМИ

### 3.1. L1 → L0 (Perception)

L0 читает состояние L1 для фильтрации впечатлений:

```python
# В PerceptualKernel
perceptual_attenuation = npc.living.archetype.social  # COWARD видит больше угроз
threat_amplification = 1.0 - npc.living.core.base_fear  # Смелый видит угрозы слабее
```

### 3.2. L1 → L2 (Behavior)

L2 читает архетип для принятия решений:

```python
# В DecisionHub
if npc.living.archetype.violence == ViolenceArchetype.TYRANT:
    # Агрессивное стремление подчинять
    utility["attack"] *= 2.0
elif npc.living.archetype.social == SocialArchetype.BROKEN:
    # Избегает всех
    utility["approach"] *= 0.1
```

### 3.3. L1 ← Affective System

Аффект **читает** core.rigidity, чтобы модифицировать давление:

```python
# В AffectiveIntegrator
# Трусливый быстро накапливает страх
affective_load += threat_gradient * (1.0 - npc.living.core.base_fear)

# Стойкий сопротивляется
resistance_factor = npc.living.core.rigidity
```

---

## 4. ПРОЦЕСС ИНТЕГРАЦИИ В КОД

### Шаг 1: Добавить LivingNPC в NPCState

```python
@dataclass
class NPCState:
    npc_id: str
    # ... существующие поля ...
    
    # === НОВОЕ ===
    living: LivingNPC = None  # Инициализируется при создании
```

### Шаг 2: Заменить прямые мутации на apply_delta()

**Было:**
```python
npc.state["fear"] += 0.1
npc_state.fear = 0.8
```

**Стало:**
```python
npc.living.apply_delta("drives", "survival", 0.1)
npc.living.apply_delta("drives", "survival", 0.8 - npc.living.drives.survival)
```

### Шаг 3: Вызвать обновление архетипа в TickOrchestrator

```python
# В фазе разрешения состояния (перед принятием решений)
for npc in all_npcs:
    npc.living.archetype.update(npc.living.core, npc.living.drives)
```

### Шаг 4: Инициализация при загрузке сцены

```python
def load_npc_from_archetype(archetype_name: str, npc_id: str) -> LivingNPC:
    """Создает LivingNPC на основе шаблона архетипа."""
    archetype_config = archetypes[archetype_name]  # Из JSON
    core = IdentityCore(
        base_aggression=archetype_config.get("aggression", 0.3),
        base_trust=archetype_config.get("trust", 0.5),
        # ... остальные параметры
    )
    return LivingNPC(npc_id=npc_id, core=core)
```

---

## 5. КРИТЕРИИ ПРИЕМКИ (Песочница)

Создать тест `tests/sandbox/test_living_npc_inertia.py`.

### Сценарий 1: Инерция работает

```python
def test_inertia_damping():
    npc = LivingNPC(npc_id="test_npc", core=IdentityCore(rigidity=0.9))
    
    # Нанесение удара: +0.5 к выживанию
    npc.apply_delta("drives", "survival", 0.5)
    
    # Проверка: инерция погасила импульс
    # Ожидается: 0.1 (базовое) * 0.9 + 0.5 * 0.1 = 0.14
    assert abs(npc.drives.survival - 0.14) < 0.01
    # (не 0.6, как было бы без инерции)
```

### Сценарий 2: Хроническое давление ломает

```python
def test_cumulative_pressure():
    npc = LivingNPC(npc_id="test_npc", core=IdentityCore(rigidity=0.9))
    
    # 10 ударов подряд
    for _ in range(10):
        npc.apply_delta("drives", "survival", 0.2)
    
    # После накопления
    assert npc.drives.survival > 0.5
    assert npc.drives.stress > 0.4
    
    # Архетип изменился
    assert npc.archetype.violence == ViolenceArchetype.VICTIM
```

### Сценарий 3: Восстановление в покое

```python
def test_recovery_at_rest():
    npc = LivingNPC(npc_id="test_npc", core=IdentityCore(recovery_rate=0.1))
    npc.drives.survival = 0.8  # Испугана
    
    npc.reset_recovery()
    
    # Выживание восстановилось (медленнее других)
    assert npc.drives.survival < 0.8
    # recovery_rate * 0.5 для выживания
    expected = 0.8 * (1.0 - 0.1 * 0.5)
    assert abs(npc.drives.survival - expected) < 0.01
```

---

## 6. ИЗВЕСТНЫЕ ГРАНИЦЫ И ОГРАНИЧЕНИЯ

1. **Отношения (R8):** relationship_cache — это заглушка. В спринте R8 будет полноценная система отношений с другими NPC.
2. **Социальная сложность:** Архетипы вычисляются на базе 5 простых драйвов. Для более сложного поведения потребуется расширение DriveSystem.
3. **Магия/Способности:** mana_channel и mana_capacity — заготовка для R10+. Пока не используются.

---

## 7. СПРАВОЧНИК КОМАНД POWERSHELL (для ревью)

```powershell
# Найти текущее состояние NPCState
Get-ChildItem -Path "backend/app/models" -Filter "*.py" -Recurse | 
  Select-String -Pattern "class NPCState"

# Найти прямые мутации fear/trust (что нужно заменить)
Get-ChildItem -Path "backend/app/services" -Filter "*.py" -Recurse | 
  Select-String -Pattern "\.fear\s*=|\.trust\s*=|\[.fear.\]|\.drives\[.*fear"

# Проверить, где вызывается apply_delta (должно быть центральное место)
Get-ChildItem -Path "backend/app" -Filter "*.py" -Recurse | 
  Select-String -Pattern "apply_delta"
```

---

**Напутствие:** Это не просто рефакторинг. Это смена философии. Вместо "агент реагирует" мы говорим "агент сопротивляется". Инерция личности — это святое.
