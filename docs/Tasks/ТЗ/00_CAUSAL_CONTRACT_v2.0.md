# CAUSAL CONTRACT v2.0: Архитектурные Законы ENIGMA

**Статус:** Исполняемый закон. Нарушение = архитектурный баг.  
**Область применения:** Все компоненты бэкенда и фронтенда.  
**Последнее обновление:** 2026-05-21

---

## 1. ФИЛОСОФИЯ

ENIGMA — это **единая каузальная система**, где игрок и NPC подчиняются одной онтологии. Нет читов, телепатии или нарушений причинно-следственной цепи. Симуляция честна.

### 1.1. Трёх-уровневая архитектура восприятия

```
L0 (PERCEPTION) — Мир → Восприятие → NPC/Игрок
L1 (BODY) — Живой агент (LivingNPC) с инерцией личности
L2 (BEHAVIOR) — Решения на основе давления и архетипа
```

**Закон:** Нельзя передать Игроку информацию, которую NPC не мог бы получить через `PerceptualKernel`. Симметрия абсолютна.

---

## 2. ОНТОЛОГИЧЕСКИЕ ПОСТУЛАТЫ

### 2.1. Единые источники истины

| Домен | Источник | Читается через | Запрет |
|-------|----------|-----------------|--------|
| **Пространство** | `SpatialService` (из `location_templates.json` / editor JSON) | `SpatialService.get_node()` | Чтение позиции из `scene_state["player_distances"]` |
| **Имена NPC** | `scene_state["npc_positions"][npc_id].name` | `_npc_id_to_display()` + Fuzzy Matching (Слой 2) | Отсутствие поля `name` → слепота резолвера |
| **Локация NPC** | `npc_state.location_id` (поле `location_id` авторитетно) | Любой читатель, но не `location` (legacy) | Чтение легасси-поля `location` |
| **Траектория движения** | `TraversalState` (от `MovementEngine`) | `SpatialService` → `DecisionHub` → `TraversalState` | Телепортация без `TraversalState`. Чтение `local_target_xy` в `MacroMovementGoal` (LOD1) |
| **Давление на личность** | `IntentPressureProfile` (от `IntentPressureResolver`) | `WillpowerGate` → `AmplifiedPressureProfile` | Хардкод давления. Обход `IntentPressureResolver` |
| **Эмоции** | `EmotionPayload` (от `AffectiveIntegrator` после фазового перехода) | `StateApplicator` → `NPCState.emotions` | Прямая генерация эмоций из событий. Обход аккумулятора |

### 2.2. Движение = Результат, не Команда

**SceneChange — это projection свершившегося, а не триггер.**

Истинная физика:
```
Intent → IntentParametersDTO → IntentPressureResolver 
  → WillpowerGate (проверка конфликта) 
  → DecisionHub (фаза 5, принятие решения)
  → MovementEngine (фаза 7)
  → TraversalState (фаза 8)
  → WorldSnapshotBuilder (фаза 9, immutable projection)
  → API → Frontend
```

**Запрет:** `scene_manager.apply_changes()` из подписчика событий. SceneChange — это только адаптер для фронтенда.

### 2.3. TraversalState отделен от Личности

`TraversalState` живет в `WorldRuntimeState.active_traversals`, **НЕ** в `NPCState`. Это данные о физическом движении, не о психике.

**Структура:**
```python
@dataclass
class TraversalState:
    npc_id: str
    source_node: str
    target_node: str
    waypoints: List[Tuple[float, float]]
    progress: float  # 0.0-1.0, интерполируется фронтендом
    speed: float     # nodes/tick
    created_tick: int
```

---

## 3. ДОПУСТИМЫЙ ПОТОК РЕАЛЬНОСТИ (Per-Tick Cascade)

### Фаза 1: Семантическая Компрессия (Player Intent)
```
Text Input → pymorphy3/LLM → IntentSemanticField 
  (MOVE, ATTACK, TALK; target_ref="тень", "борко", "мужик")
```

### Фаза 2: Target Resolution (Fuzzy Match)
```
IntentSemanticField.target_ref → Fuzzy Match in scene_state["npc_positions"] 
  → target_id="thief_shadow" 
  → IntentParametersDTO (полный контракт, строго типизирован)
```

**Ключевой запрет:** Если `target_ref` не резолвится → **UNCERTAINTY**, не OBSERVE.

### Фаза 3: Intent Pressure Resolution
```
IntentParametersDTO (semantic_action, target_id, physical_force)
  → IntentPressureResolver
  → IntentPressureProfile (violence, humiliation, self_risk, moral_violation)
```

**Критический фикс:** Распознавание ключей `player_attacks`, `player_threatens`, а не старых `attack_target`.

### Фаза 4: Affective Resonance & Distortion
```
IntentPressureProfile + AffectiveImprints (память травм)
  → scan_affective_resonance() → ResonanceProfile
  → distort_pressure() → AmplifiedPressureProfile (через ResponseBias)
```

### Фаза 5: WillpowerGate (Cumulative Strain Model)
```
AmplifiedPressureProfile + NPCState.psyche
  → resistance = pressure.identity_deviation * psyche.identity_rigidity + ...
  → WillResponseDTO (state, resistance, identity_damage, counter_offer)
  → Шкала деградации: COMPLY → RELUCTANT → DISTRESSED → PANICKED → CONDITIONED
```

### Фаза 6-8: Каузальное замыкание (Combat, Movement, Resolution)
```
IntentResolution → EventBus (WILL_CONFLICT, PLAYER_ATTACKED)
  → CombatSubscriber → ImpactEngine → PhysiologyPayload (shock_impulse)
  → ReactionSubscriber → StateApplicator
  → PerceptionPayload (threat_gradient_delta, uncertainty_delta)
  → NPCState.perceptual_kernel
```

### Фаза 9: Affective Integration (Аккумулятор аффекта)
```
PerceptionPayload (threat_gradient) → AffectiveIntegrator 
  → accumulate affective_load over time
  → if affective_load > personal_threshold 
    → EmotionTransition 
    → EmotionPayload (паника, страх, подчинение)
  → StateApplicator → NPCState.emotions
```

**Закон:** Эмоции не генерируются из одного события. Они рождаются из интеграла угрозы по времени (ADR-049).

### Фаза 10: Восприятие Игрока (Embodied Perception)
```
Simulation Truth (CFRM, Deltas)
  → PhenomenologyProjectionService (Генерация PerceptionEvent)
  → PerceptualAttentionService (Диафрагма: бюджет, затухание)
  → PlayerPerceptionDTO (Транспорт для фронтенда)
  → Frontend Renderer (Симметричная линза игрока)
```

---

## 4. ЗАПРЕТЫ (HARD CONSTRAINTS)

### 4.1. Запреты на Движение

1. **Прямая мутация позиции:** `npc["position"] = ...` ❌
2. **Чтение позиции из неавторитетного источника:** `scene_state["player_spatial"]` ❌ → используй `SpatialQueryService`
3. **Телепортация Игрока:** `if target == player: bypass latency` ❌ → Игрок подвержен мембранам, как и NPC
4. **SceneChange как триггер:** `scene_manager.apply_changes()` из подписчика ❌ → только адаптер для фронтенда
5. **LOD0/LOD1 Corruption:** Передача `local_target_xy` в `MacroMovementGoal` или `target_node_id` в `LocalSteeringGoal` ❌ → физики разделены

### 4.2. Запреты на Волю и Давление

6. **Решение без происхождения:** `MovementIntent` без `pressure_sources` ❌
7. **Давление без видимости:** Получение давления через мембрану с `attenuation=0.0` ❌
8. **Double Invocation:** WillpowerGate вызывается ОДИН раз за цикл ❌ → Фаза 1 только переводит семантику
9. **Domain Leakage:** `CombatSubscriber` пишет в Emotion ❌ → только `PhysiologyPayload`
10. **Голый вызов Директивы:** `DirectiveInterpretationSubscriber().handle()` без инъекции `all_npcs_raw` ❌ → `ObediencePressure=0.00` = мертва Каузальная Труба

### 4.3. Запреты на Восприятие и UI

11. **Телепатия в UI:** Передача Игроку информации о внутренних состояниях NPC ❌ → только внешние наблюдения ("замер", "дрожит")
12. **Повторное вычисление в восприятии:** `PerceptualAttentionService` читает `StateDeltas.fear_delta` ❌ → только `PerceptionEvent.salience`
13. **Лаг в ввод:** `perceptual_latency` для задержки ввода ❌ → только визуальный `desync` (шлейфы, инерция камеры)
14. **Слепота Fuzzy Matching:** Удаление поля `name` из `npc_positions` ❌ → `name` обязателен для резолва цели
15. **Краш сериализации:** Использование `asdict()` на границе API без проверки типа ❌ → только `Pydantic`/`Dataclass`

### 4.4. Запреты на Ретро-симуляцию и Кэширование

16. **Ретро-симуляция:** `TICK_CATCHUP` с циклом `LifeEngine.tick()` ❌ → только `reconcile_state(elapsed_seconds)` (ADR-047)
17. **Кэш-фантомы:** Не очищен `__pycache__` после рефакторинга DTO ❌ → обязательная очистка перед запуском

### 4.5. Запреты на Время и Пространство

18. **Зависимость времени от игрока:** 
    ❌ tick += 1 внутри player.action()
    ✅ world_clock.advance() перед всем

19. **Ретросимуляция дальних регионов:**
    ❌ for i in range(missed_ticks): npc.tick()
    ✅ compress_state() / expand_state() при смене локации

20. **Прямое редактирование сжатого состояния:**
    ❌ lod_state.compressed["mood"] = 0.5
    ✅ только через StateApplicator

21. **Время как свойство сущности:**
    ❌ npc.birth_time = world_clock.tick (сохраняем абсолютный тик)
    ✅ только производные (age, time_alive, и т.д. как функции WorldClock)

22. **Множественные источники LOD уровня:**
    ❌ NPC сам определяет свой LOD
    ✅ только LODManager определяет LOD для всех

---

## 5. СПИСОК ПЕСОЧНИЦ (Fail Conditions)

Каждый запрет имеет тест:

- `test_no_direct_mutation_of_position`
- `test_no_direct_scene_change_in_resolver`
- `test_pressure_modifies_utility_not_commands`
- `test_membrane_visibility_enforced`
- `test_decision_requires_pressure_provenance`
- `test_target_resolution_requires_name_in_npc_positions`
- `test_directive_subscriber_requires_npc_state`
- `test_no_telepathy_in_ui_observation`
- `test_willpower_gate_single_invocation_per_tick`
- `test_affective_load_accumulation_over_time`
- `test_living_npc_inertia_preserved`

---

## 6. ПРИНЦИП НАБЛЮДАЕМОСТИ (CDS Non-Invasiveness)

**Наблюдение не создает причинность.** CDS и `reports/LAST_SESSION.md` — это проекция свершившегося.

1. **Запрет обратной связи:** Данные из отчётов CDS запрещено парсить и использовать в runtime симуляции.
2. **Чистота наблюдателя:** Падение CDS не должно прерывать каузальный поток. CDS работает в `try/except` и отдельном потоке.
3. **Каузальные разрывы:** Если CDS обнаруживает разрыв (Intent создан, Traversal нет), он фиксирует для LLM-архитектора, но не инжектит фиксы.

---

## 7. АРХИТЕКТУРНАЯ ЦЕЛОСТНОСТЬ: ПРИНЦИПЫ

### 7.1. Инерция личности (от L1)
Личность **сопротивляется** изменениям. Запрещена моментальная мутация статов.

```python
new_value = (old_value * core.rigidity) + (delta * (1 - core.rigidity))
```

### 7.2. Симметрия восприятия (от L0)
Игрок и NPC получают одинаковую информацию через разные `ProjectionPolicy`. Нет привилегий.

### 7.3. Единственность решений (от L2)
`DecisionHub` — единственное место, где NPC принимает решение. Все давление аккумулируется и влияет на utility, но не на сам процесс выбора.

---

## 8. МИГРАЦИЯ ЗНАНИЙ: Из чего взяли этот контракт

- **ADR-031** (WillpowerGate & Hybrid Consciousness)
- **ADR-035** (Semantic Compression)
- **ADR-037** (Affective Distortion)
- **ADR-042** (Target Resolution & Fuzzy Matching)
- **ADR-047** (No Retro-simulation)
- **ADR-048** (Single Spatial Authority)
- **ADR-049** (Affective Accumulation over Time)
- **ADR-058/059** (Dual-Time Ontology)
- **ADR-060** (Movement Ontology Split: LOD0/LOD1)

---

**КЛЮЧЕВАЯ ИДЕЯ:** Это не просто правила. Это **описание одной честной симуляции**, где игрок — не король, а персонаж, подчиняющийся тем же законам, что и NPC.
