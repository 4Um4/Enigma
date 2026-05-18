# CAUSAL CONTRACT: Movement & Player Agency (v1.1)

**Статус:** Исполняемый закон. Нарушение = архитектурный баг.

## 1. Онтологические Постулаты

1. **Игрок — Каузальная Сущность:** Игрок существует в симуляции. Его позиция — объективная пространственная истина внутри `ClusterOccupancy`.
2. **Единый Источник Истины:** Позиция читается ТОЛЬКО из `ClusterOccupancy`. `scene_state` и `npc_positions` — вторичные проекции (DTO).
3. **SceneChange = Результат, не Команда:** SceneChange — это legacy-адаптер, проекция свершившегося. ЗАПРЕЩЕНО использовать его как команду. Истинная физика: `TraversalState → SpatialDelta → SpatialApplicator → WorldState`.
4. **TraversalState отделен от Личности:** `TraversalState` живет в `WorldRuntimeState.active_traversals`, НЕ внутри `NPCState`.

## 2. Допустимый Поток Реальности

1. **Сжатие:** `Text → IntentSemanticField (MOVE, target_ref, social_pressure)`.
2. **Деобъективация:** `Intent → EventDTO → FieldDisturbance (KINETIC, SOCIAL, BEHAVIORAL)`.
3. **Давление:** `FieldDisturbance → ReactionSubscriber → PsychologicalPressure (score modifier)`. Давление ≠ Команда. Давление = Изменение utility landscape.
4. **Акт Воли:** `DecisionHub (Phase 5) → MovementGoal (desired_proximity, target_entity)`. Решение принимается на основе модифицированного utility, NPC не знает "кто приказал".
5. **Пространственный Вывод:** `SpatialReasoner → Target Node (based on MovementGoal)`.
6. **Локомоция:** `MovementEngine → TraversalState (WorldRuntimeState) → SpatialDelta → State Mutation`.

## 3. Запрещенные Паттерны (Bypass Holes)

1. **Прямая мутация позиции:** `npc["position"] = ...`
2. **SceneChange как триггер:** `scene_manager.apply_changes()` из подписчика.
3. **Решение без происхождения:** `MovementIntent` без `pressure_sources`.
4. **Давление без видимости:** Получение давления через мембрану с `attenuation=0.0`.
5. **Телепортация Игрока:** `if target == player: bypass latency`. Игрок подвержен мембранам, как и NPC.

## 4. Список Песочниц (Fail Conditions)

*   `test_no_direct_mutation_of_position`
*   `test_no_direct_scene_change_in_resolver`
*   `test_pressure_modifies_utility_not_commands`
*   `test_membrane_visibility_enforced`
*   `test_decision_requires_pressure_provenance`

## 5. Принцип Наблюдаемости (CDS Observability)

**Наблюдение не создает причинность.** Causal Diagnostic System (CDS) и `reports/LAST_SESSION.md` являются проекцией свершившегося. 
1. **Запрет обратной связи:** Данные из отчетов CDS запрещено парсить и использовать в runtime симуляции для принятия решений.
2. **Чистота наблюдателя:** Падение CDS не должно прерывать каузальный поток игры. CDS работает в `try/except` и отдельном потоке.
3. **Каузальные разрывы:** Если CDS обнаруживает разрыв (например, Intent создан, Traversal нет), он фиксирует это для LLM-архитектора, но не инжектит фиксы автоматически.`
```