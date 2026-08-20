# ADR-301 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-301` [STANDARD] **IMPACT**
# ADR-301 Impact Audit: Semantic Index Layer (v2 — актуализировано после S81)

> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`
> **Актуализация:** S81 починил координатную истину и добавил passability — это меняет контекст внедрения ADR-301.

---

## 1. Changed Domains

- **spatial** (graph_compiler, spatial_service, SpatialDataLoader)
- **npc/movement** (life_engine, npc_tick_pipeline, MovementEngine)
- **decision** (selection policy, utility scoring)
- **object semantics** (SLEEP_LOCI, SHELTER, WORK_STATION — новый домен, зафиксирован в ТЗ §15)

### Что изменил S81 в этих доменах:

| Домен | До S81 | После S81 |
|-------|--------|-----------|
| spatial | local_position для коллизий, стены без проёмов | World coordinates SSOT, стены с проёмами, passability.walk |
| npc/movement | NPC позиция = string | NPC позиция = world coordinates (после ADR-301: SemanticIndex → NodeRef → world_xy) |
| object semantics | type = decoration для всего | type + passability + blocks_los (data-driven) |

---

## 2. Downstream Consumers

### 2.1 Первичные (точки внедрения)

| Потребитель | Роль | Статус |
|-------------|------|--------|
| `LifeEngine._resolve_position()` | Единственная точка замены string→SemanticIndex | ⚠️ Ожидает реализации |
| `GraphCompiler.compile_graph()` | Расширение до 5 элементов (role_index) | ⚠️ Ожидает реализации |
| `SpatialService` | Добавление `_role_index` | ⚠️ Ожидает реализации |

### 2.2 Вторичные (потребляют результат)

| Потребитель | Что читает | Изменение после S81 |
|-------------|------------|---------------------|
| `MovementEngine` | NodeRef из SemanticIndex | NodeRef должен быть в world coordinates |
| `SpatialDataLoader` | obstacles с passability | SemanticIndex может классифицировать по passability, а не только type |
| `ContextResolver` | WorldViewContext | SemanticIndex enriches context с role-информацией |
| `LifeEngine._arousal_gate` | SLEEP_LOCI для wake logic | Сейчас хардкод → SemanticIndex |

### 2.3 Критическое ограничение (ТЗ §15)

> Любой код, который ищет "где NPC может спать", ДОЛЖЕН идти через один метод. Один. Не десять.

До ADR-301 — этот метод = простая эвристика (поиск type ∈ SLEEP_LOCI).
После ADR-301 — этот метод = `SemanticIndex.resolve_candidates("sleep", npc_state)`.

**Замена ОДНОГО метода, не десяти хардкодов.**

---

## 3. Architecture: Три разделённых слоя

### 3.1 SemanticIndex (classify + resolve)

```python
class SemanticIndex:
    """Read-only индекс. Классифицирует строки и предоставляет кандидатов."""
    
    # Зафиксированные семантические роли (ТЗ §15)
    SLEEP_LOCI = {"bed", "tent", "straw_bed", "sleeping_mat", "cot"}
    SHELTER = {"tent", "hut", "cave"}  # укрытие от погоды
    WORK_STATION = {"bar", "anvil", "forge", "stove"}  # рабочее место
    SEATING = {"chair", "stool", "bench"}  # сиденье
    
    def classify(self, type_string: str) -> set[NodeRole]:
        """Строка → набор ролей. Один объект может иметь несколько ролей."""
        roles = set()
        if type_string in self.SLEEP_LOCI:
            roles.add(NodeRole.SLEEP)
        if type_string in self.SHELTER:
            roles.add(NodeRole.SHELTER)
        if type_string in self.WORK_STATION:
            roles.add(NodeRole.WORK)
        if type_string in self.SEATING:
            roles.add(NodeRole.SEAT)
        # passability.walk = True → NodeRole.PASSAGE
        # blocks_los = False → NodeRole.TRANSPARENT
        return roles
    
    def resolve_candidates(self, role: NodeRole, npc_state, context) -> list[str]:
        """Роль + контекст → список node_id кандидатов."""
        ...
```

### 3.2 Candidate Scoring (детерминированный)

```python
def score_candidates(candidates, npc_state, context) -> list[tuple[str, float]]:
    """Контекстный скоринг: близость + владение + доступность."""
    scores = []
    for node_id in candidates:
        score = 0.0
        score += proximity_bonus(node_id, npc_state.position)
        score += ownership_bonus(node_id, npc_state.npc_id)  # кровать Торнина
        score += availability_bonus(node_id)  # занят ли другой NPC
        scores.append((node_id, score))
    return sorted(scores, key=lambda x: -x[1])
```

### 3.3 Selection Policy (явно параметризованная)

```python
class SelectionPolicy:
    strict_max: bool = True      # Всегда лучший кандидат
    anti_flap: float = 0.1      # Минимальная дельта для смены цели
    diverse: bool = False        # Разнообразие при равных счётах
    max_distance: float = 50.0  # Максимальная дистанция рассмотрения
```

---

## 4. Семаантика объектов (Ontological Grounding — ТЗ §15)

### 4.1 Зафиксированные назначения

| Локация | Объект | Кол-во | Тип в JSON | Семантическая роль | Потребитель |
|---------|--------|--------|------------|-------------------|-------------|
| city_gate | палатка | 9 | `object.type="tent"` | SLEEP locus (ночевка NPC) | LifeEngine → ADR-301 |
| tavern / кухня | кровать | 2 | `object.type="bed"` | SLEEP locus (Торнин, Люся — по очереди) | LifeEngine → ADR-301 |

### 4.2 Правила SLEEP_LOCI

1. **Вместимость** — один SLEEP locus = один NPC за раз
2. **Владение** — кровать на кухне таверны принадлежит Торнину и Люсе (по очереди). Палатки = публичные
3. **Приоритет** — NPC с домом спит дома. NPC без дома ищет ближайший SLEEP locus
4. **Нет SLEEP locus → нет сна** — NPC не спит на полу. Отсутствие сна накапливает fatigue

---

## 5. Runtime Impact

| Метрика | Значение | Примечание |
|---------|----------|------------|
| RAM: role_index | +~1KB per location | Dict[NodeRole, List[str]] |
| RAM: ownership map | +~0.5KB per location | Dict[str, str] (node_id → npc_id) |
| Tick Latency | +0.1ms per schedule resolution | classify + resolve + score + select |
| Compile time | +0.5ms per location | role_index build при compile_graph |
| VRAM | 0 | Нет визуальных изменений |

---

## 6. Sandbox Tests

### 6.1 Classification Tests

| Тест | Что проверяет |
|------|---------------|
| `test_semantic_index_classify_sleep` | bed, tent → SLEEP |
| `test_semantic_index_classify_multi_role` | tent → SLEEP + SHELTER |
| `test_semantic_index_classify_unknown` | "blah" → empty set |
| `test_semantic_index_classify_passage` | passability.walk=True → PASSAGE |

### 6.2 Resolution Tests

| Тест | Что проверяет |
|------|---------------|
| `test_semantic_index_resolve_candidates` | role → list[node_id] |
| `test_unknown_returns_empty_candidates` | неизвестная роль → [] |
| `test_resolve_candidates_respects_chunk` | только кандидаты в текущем чанке |

### 6.3 Scoring Tests

| Тест | Что проверяет |
|------|---------------|
| `test_candidate_scoring_deterministic` | одинаковый контекст → одинаковый результат |
| `test_candidate_scoring_proximity` | ближний кандидат > дальний |
| `test_candidate_scoring_ownership` | своя кровать > публичная |

### 6.4 Selection Tests

| Тест | Что проверяет |
|------|---------------|
| `test_selection_policy_strict_max` | всегда лучший |
| `test_selection_policy_stable_anti_flap` | не переключается при малой дельте |
| `test_selection_policy_diverse` | разнообразие при равных |
| `test_selection_policy_max_distance` | далеко = не рассматривается |

### 6.5 Integration Tests

| Тест | Что проверяет |
|------|---------------|
| `test_role_index_built_by_compiler` | compile_graph() → 5-й элемент |
| `test_resolve_position_uses_semantic_index` | LifeEngine идёт через SemanticIndex |
| `test_sleep_locus_capacity` | один NPC на кровать |
| `test_sleep_locus_ownership` | Торнин → своя кровать приоритетнее |

---

## 7. Rollback

1. Удалить вызов `resolve_candidates()` из `LifeEngine`
2. Вернуть `target_entry.get("position", "")`
3. `role_index` — опциональный 5-й элемент `compile_graph` (обратная совместимость)
4. Удалить `semantic/` директорию
5. Удалить `ownership_map` из `SpatialService`

---

## 8. При UNKNOWN / пустых кандидатах

Возвращается `None` или `SemanticResolutionFailure`. **НЕ string passthrough.**

`LifeEngine` решает что делать:
- `centroid` текущей комнаты (если schedule требует перемещения)
- текущая позиция (если движение не критично)
- пропустить tick (если нет валидной цели)

---

## 9. 15 каузальных запретов

| # | Запрет | Причина |
|---|--------|---------|
| 127 | String passthrough при неизвестной роли | Молчаливая потеря семантики |
| 128 | Selection без Score | Случайный выбор = недетерминизм |
| 129 | Score без Context | Близость — не единственный фактор |
| 130 | SemanticIndex мутирует state | Индекс — read-only проекция |
| 131 | Классификация по position | Позиция — не роль |
| 132 | Хардкод "палатка = ночлег" в нескольких местах | Один метод — одна точка замены (ТЗ §15.4 #154) |
| 133 | NPC спит на полу без SLEEP locus | Нужен объект-контейнер (ТЗ §15.4 #155) |
| 134 | Два NPC на одной кровати одновременно | Вместимость = 1 (ТЗ §15.4 #156) |
| 135 | Ownership через NPCState | Владение = атрибут объекта, не NPC |
| 136 | resolve_candidates без chunk filter | Кандидаты только в текущем чанке |
| 137 | SemanticIndex как Service (mutable) | Индекс = скомпилированный артефакт |
| 138 | Fuzzy Match вместо classify | Fuzzy = инструмент, не архитектура |
| 139 | Классификация в DecisionHub | Decision = потребитель, не классификатор |
| 140 | role_index в runtime O(N²) | Компиляция — одноразовая |
| 141 | SemanticIndex без ownership map | Нужна привязка кровать→NPC |

---

## 10. Зависимости от S81

| Зависимость | Влияние на ADR-301 |
|-------------|---------------------|
| Coordinate Truth (world SSOT) | NodeRef в world coordinates, не local |
| passability.walk в SpatialDataLoader | classify может использовать passability |
| Center→top-left конверсия | Координаты кандидатов корректны |
| Стены с проёмами | Двери не блокируют pathfinding |
| _draw_entities = pass | Рендер не мешает семантике |

---

*Версия: 2.0*
*Дата: 2026-05-27*
*Актуализация: S81 (Coordinate Truth + Physical World Unification)*


Files: N/A
