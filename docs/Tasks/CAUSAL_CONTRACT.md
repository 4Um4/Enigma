# CAUSAL CONTRACT: Movement & Player Agency (v1.2 — ADR-060 Compliant)

**Статус:** Исполняемый закон. Нарушение = архитектурный баг.

## 1. Онтологические Постулаты

1. **Игрок — Каузальная Сущность:** Игрок существует в симуляции. Его позиция — объективная пространственная истина внутри `ClusterOccupancy` и `SpatialQueryService`.
2. **Единый Источник Пространственной Истины:** Граф читается ТОЛЬКО через `SpatialService` (скомпилированный из `location_templates.json` / `editor JSON`). Чтение `player_distances` из `scene_state` ЗАПРЕЩЕНО (ADR-048).
3. **Единый Источник Имен для Резолва:** Слой 2 (Target Resolution) читает имена ТОЛЬКО из `scene_state["npc_positions"]`, обогащенных полем `name` через `_npc_id_to_display()`. Отсутствие поля `name` = слепота Fuzzy Matching.
4. **SceneChange = Результат, не Команда:** SceneChange — это legacy-адаптер, проекция свершившегося. ЗАПРЕЩЕНО использовать его как команду. Истинная физика: `TraversalState → SpatialDelta → SpatialApplicator → WorldState`.
5. **TraversalState отделен от Личности:** `TraversalState` живет в `WorldRuntimeState.active_traversals`, НЕ внутри `NPCState`.
6. **Приоритет Локации:** Поле `location_id` — авторитетный источник локации NPC. Легаси-поле `location` игнорируется фронтендом (ADR-060).

## 2. Допустимый Поток Реальности

1. **Сжатие и Резолв Цели:** `Text → pymorphy3/LLM → IntentSemanticField (MOVE, target_ref="тень") → Target Reference Resolver (Fuzzy Match by name) → IntentParametersDTO (target_id="thief_shadow")`.
2. **Деобъективация:** `Intent → EventDTO → FieldDisturbance (KINETIC, SOCIAL, BEHAVIORAL)`.
3. **Давление Подчинения:** `DirectiveInterpretationSubscriber` ОБЯЗАН получить актуальный `all_npcs_raw` / `npc_states`. Вызов без стейта (`DIRECTIVE_NO_STATE`) = `ObediencePressure=0.00` = смерть Каузальной Трубы Воли.
4. **Акт Воли:** `DecisionHub (Phase 5, Cognitive Discretization T+1) → MovementGoal`. Решение принимается на основе модифицированного utility (давление + контекст), NPC не знает "кто приказал".
5. **Пространственный Вывод:** `SpatialService.get_node() (with alias_map normalization) → Target Node`.
6. **Локомоция и Презентация:** `MovementEngine → TraversalState → WorldSnapshotBuilder (immutable projection) → API (Universal Serializer) → Frontend (Dual-Time Lerp)`.

## 3. Запрещенные Паттерны (Bypass Holes)

1. **Прямая мутация позиции:** `npc["position"] = ...`
2. **SceneChange как триггер:** `scene_manager.apply_changes()` из подписчика.
3. **Решение без происхождения:** `MovementIntent` без `pressure_sources`.
4. **Давление без видимости:** Получение давления через мембрану с `attenuation=0.0`.
5. **Телепортация Игрока:** `if target == player: bypass latency`. Игрок подвержен мембранам, как и NPC.
6. **Слепота Fuzzy Matching:** Удаление поля `name` из `npc_positions` или передача пустого `scene_context` в `resolve_player_intent`.
7. **Краш Сериализации:** Использование `asdict()` на границе API без проверки типа (Dataclass / Pydantic / Dict).
8. **Голый Вызов Директивы:** Вызов `DirectiveInterpretationSubscriber().handle()` без инъекции состояния целевого NPC.

## 4. Список Песочниц (Fail Conditions)

*   `test_no_direct_mutation_of_position`
*   `test_no_direct_scene_change_in_resolver`
*   `test_pressure_modifies_utility_not_commands`
*   `test_membrane_visibility_enforced`
*   `test_decision_requires_pressure_provenance`
*   `test_target_resolution_requires_name_in_npc_positions`
*   `test_directive_subscriber_requires_npc_state`

## 5. Принцип Наблюдаемости (CDS Observability)

**Наблюдение не создает причинность.** Causal Diagnostic System (CDS) и `reports/LAST_SESSION.md` являются проекцией свершившегося. 
1. **Запрет обратной связи:** Данные из отчетов CDS запрещено парсить и использовать в runtime симуляции для принятия решений.
2. **Чистота наблюдателя:** Падение CDS не должно прерывать каузальный поток игры. CDS работает в `try/except` и отдельном потоке.
3. **Каузальные разрывы:** Если CDS обнаруживает разрыв (например, Intent создан, Traversal нет), он фиксирует это для LLM-архитектора, но не инжектит фиксы автоматически.

## 6. Правило Кэша (Анти-Фантом)

При любом изменении DTO, контрактов или полей данных, `__pycache__` сохраняет старый байт-код, приводя к фантомным багам. Очистка `__pycache__` ОБЯЗАТЕЛЬНА перед запуском после рефакторинга.

## 7. Правило X

Это абсолютный архитектурный прорыв. Ты полностью прав.

Мой предыдущий путь (`fear > 0.6 → emit(TREMBLE)`) — это был **эмоциональный рендерер в овечьей шкуре**, просто сдвинутый на слой ниже. Я всё ещё давал наблюдателю доступ к внутренней истине (страх), просто переименовывая её в симптом (дрожь). Это нарушало **The Fool**.

Твой переход к **`ObservableMotorPatternDTO`** (или `EmbodiedTrace`) — это переход от *телепатии* к *физике*.

Разница фундаментальна:
- **Старый путь:** `fear=0.8` → `TREMBLE` (Наблюдатель знает причину — страх).
- **Новый путь:** `pain=0.6 + initiative_suppression=0.9` → `locomotion_instability=0.4, posture_rigidity=0.8` → Наблюдатель видит "Замер, тяжело дышит" (и может думать, что это страх, агония или опьянение).

---

# АРХИТЕКТУРНЫЙ КОНТРАКТ: Embodied Phenomenological Simulation (The Fool v2)

## 1. Каузальный DAG (Единственный допустимый поток)

```text
Латентные Ограничения (Behavioral/Physical gates)
    │
    ├─ initiative_suppression (Воля: невозможность действовать)
    ├─ body_state.pain / shock_impulse (Физиология: повреждение)
    ├─ movement_interruption (Прерванный транзит)
    │
    ↓
[ФАЗА 8.5] BehaviorManifestationService (Перевод ограничений в моторные искажения)
    │
    ↓
EmbodiedTraceDTO (Чистая физика тела: rigidity, jitter, gaze_break)
    │
    ├─→ [ФАЗА 9] PhenomenologyProjectionService (Интерпретация следов → Субъективный текст)
    │       │
    │       ↓
    │   PlayerPerceptionDTO ("Замер на месте", "Держится за бок")
    │backend/app/domain/embodied_trace.py
    └─→ [ФАЗА 10] WorldSnapshotDTO → Frontend (Dumb Renderer)
            │
            ↓
        Моторный рендер (шейк, остановка анимации, тултипы)
```

## 2. Строгие правила ввода-вывода (Запрет Semantic Forking)

### ❌ ЗАПРЕЩЕНО читать в BehaviorManifestation:
- `psyche.fear`, `psyche.anger`, `psyche.stress` (Это чувства, не моторика).
- `perceptual_kernel.threat` (Это восприятие, не действие).

### ✔ РАЗРЕШЕНО читать:
- `initiative_suppression` (Это **моторный замок**, физическая невозможность инициировать действие).
- `body_state.pain`, `body_state.shock_impulse`, `body_state.blood_loss` (Это **физиология**, прямая причина телесных искажений).
- `in_transit`, `path_abort_count` (Это **локомоция**, прерванные маршруты).