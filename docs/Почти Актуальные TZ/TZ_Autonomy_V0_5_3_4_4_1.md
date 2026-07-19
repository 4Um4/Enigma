# ТЗ: Автономный мир и починка каузальной топологии (Снимок после S125)

**Проект:** Enigma V.0.5.3.4.4
**Цель:** Устранить рассинхронизацию Shadow/Leggy пайплайнов (Rule 120 Drift) и починить локальный обход препятствий (NO_DETOUR). Обогатить Sims-слой индивидуальными фразами NPC.
**Дата:** 18 июля 2026 г.
**Базируется на:** IPT 5/5 passed, Pytest 844 passed. Логах `cds_backend.log`, где виден спам `GEOMETRIC_OBSTACLE_NO_DETOUR` и `[DRIFT][D] field=traversal_exists`.

---

## 0. Постановка задачи

Предыдущее ТЗ (6 блокеров автономии) полностью выполнено. Мир живёт, NPC двигаются и разговаривают. 
Однако логи выявили два новых архитектурных долга, которые убивают погружение:
1. **NPC застревают у стен.** `MovementPlanner` возвращает `GEOMETRIC_OBSTACLE_NO_DETOUR`, если прямая линия пересекает `spatial_obstacles`. NPC застывает навсегда.
2. **Rule 120 Drift.** `SceneStateManager` (Legacy) создаёт `TraversalState` напрямую, в то время как `MovementPlanner` уже является авторизованным автором. Shadow-пайплайн видит расхождение.
3. **Sims-слой статичен.** `NpcConversation` использует один список из 142 фраз для всех NPC. Кузнец говорит те же фразы, что и трактирщик.

---

## 1. Карта задач

| # | Задача | Файл | Симптом | Время фикса |
|---|---|---|---|---|
| 1 | Rule 120 Drift Elimination | `scene_state_manager.py`, `event_compiler.py` | `[DRIFT][D] field=traversal_exists` | 2-3 часа |
| 2 | Geometric Obstacle Detour | `movement_engine.py` (или `movement_planner.py`) | `GEOMETRIC_OBSTACLE_NO_DETOUR` | 3-4 часа |
| 3 | Sims-слой обогащение | `npc_conversation.py` | Кузнец говорит о козах | 1-2 часа |

---

## 2. Задача 1 — Rule 120 Drift Elimination

### 2.1. Что происходит

В S121 был внедрён `MovementPlanner` (ADR-O-323) как единственный автор `TraversalProposal`. 
Однако `SceneStateManager.apply_change` (Legacy) всё ещё вычисляет путь через `math.hypot` и создаёт `TraversalState` напрямую, игнорируя `proposal`. 
Из-за этого Shadow-пайплайн (`EventCompiler`) фиксирует дрейф: один пайплайн создал транзит, а другой — нет.

### 2.2. Патч

1. **Перевести `SceneStateManager` в режим read-only мутатора.**
   - Удалить хардкод `math.hypot` и `find_path` из `apply_change`.
   - SSM должен применять `TraversalProposal` от `MovementPlanner`, а не вычислять геометрию сам.
2. **Синхронизировать `EventCompiler`.**
   - Убедиться, что Shadow-пайплайн читает тот же `proposal` и не генерирует фантомные `TraversalContract(status="COMPLETED")`.

### 2.3. Контрольная точка

- В логах `cds_backend.log` нет `[DRIFT][D] field=traversal_exists` за 5 минут idle.
- `drift_B = 0` в DriftLaboratory (200 тиков).

---

## 3. Задача 2 — Geometric Obstacle Detour

### 3.1. Что происходит

`MovementPlanner` проверяет прямую линию между `source_xy` и `target_xy` на пересечение с `spatial_obstacles`. Если есть пересечение — он возвращает `GEOMETRIC_OBSTACLE_NO_DETOUR` и NPC останавливается.

### 3.2. Патч

Реализовать локальный pathfinding (обход препятствий):
1. **Вариант A (A* на сетке):** Разбить пол локации на сетку 1x1 метр. Искать путь A* с учётом `spatial_obstacles`.
2. **Вариант B (Fallback на ближайший свободный узел):** Если прямая линия заблокирована, искать ближайший узел графа (`NodeRole.DEFAULT`), до которого прямая линия свободна, и строить путь через него.
3. **Вариант C (RVO - Reciprocal Velocity Obstacles):** Для динамических препятствий (другие NPC).

Рекомендуется начать с **Варианта B** как наименее затратного.

### 3.3. Контрольная точка

- В логах нет спама `GEOMETRIC_OBSTACLE_NO_DETOUR`.
- NPC успешно обходят столы и бочки, не застревая.

---

## 4. Задача 3 — Sims-слой обогащение

### 4.1. Что происходит

В S125 был создан `npc_conversation.py`. Сейчас он использует статический список `_AMBIENT_PHRASES` из 142 фраз. Все NPC говорят одно и то же.

### 4.2. Патч

1. **Подключить `NPCProfileL0`** к `NpcConversation`.
2. Разделить `_AMBIENT_PHRASES` на категории по архетипам/профессиям:
   - `blacksmith`: фразы о железе, заказах, усталости.
   - `merchant`: фразы о ценах, товарах, караванах.
   - `tavern_keeper`: фразы о выпивке, посетителях, уборке.
   - `guard`: фразы о дежурстве, подозрениях, погоде.
3. Локализация — строгий русский.

### 4.3. Контрольная точка

- Кузнец (`blacksmith_orm`) говорит о железе.
- Трактирщик (`tavern_keeper_tornin`) говорит о выпивке.

---

## 5. Архитектурные запреты (Напоминание)

- ❌ **Запрет ретро-симуляции (§14 TЗ Autonomy).** Конкретика генерируется ТОЛЬКО в момент разговора.
- ❌ **Не раскрывать имена автоматически.** Игрок знает имя NPC только если реально его услышал.
- ❌ **HP Double Truth.** Запрещен прямой write в `state.hp`. Только `body_state["current_hp"]`.
- ❌ **Глобальный random.** В ядре и бою используется ТОЛЬКО `KernelRNG` (параметр `rng`).
- ❌ **Неатомарные сохранения.** `save_scene` и `save_npcs` вне `atomic_commit` запрещены.
- ❌ **Телепатия NPC.** Запись в память возможна только после `filter_perceiving_npcs`.

---

## 6. Финальная мысль

Движение должно быть бесшовным (без застреваний), а мир — живым за счет Sims-слоя и динамических реплик, не требующих LLM для каждой фразы.

### ФАЗА 4: ЭМЕРДЖЕНТНЫЙ ЦИКЛ И ДЕФОРМАЦИЯ ИДЕНТИЧНОСТИ (Критично для глубокого AWC)

4. **Социальное Давление на Идентичность.** Файлы `npc_dialogue_subscriber.py`, `break_progress_engine.py`, `belief_transition_engine.py`.
   - **Проблема:** NPC-NPC диалоги обновляют `RelationshipStore` и эмоции, но не генерируют `identity_pressure` для `BreakProgressEngine`. NPC может 100 раз услышать предательство, но его `life_direction` (L2.7) не сломается.
   - **Фикс 1 (Социальный стресс):** В `NpcDialogueSubscriber._process_canonical` при сильно негативном tone (ANGRY, MANIPULATIVE) генерировать `IdentityPressurePayload` и передавать его в `BreakProgressEngine`. Падение доверия ниже определённого порога должно бить по `identity_integrity`.
   - **Фикс 2 (Снятие блокировки L2.5):** Проверить, генерируют ли события `NPC_SPOKE` (с radius < 5.0) `phase_2_events` в Фазе 2. Если нет — `BeliefCrystallizationEngine` (L2.5) никогда не запустится в idle. Диалоги должны создавать `SpatialEvent` (actor=NPC_A, target=NPC_B, type=PROXIMITY_CLOSE/SOCIAL_INTERACT), чтобы кормить L2.5.
   - **Ожидаемый результат:** Если NPC_A систематически оскорбляет NPC_B, `identity_pressure` NPC_B растёт. При достижении стадии `deformation` срабатывает `LifeProjectResolver`, и NPC_B меняет свой `life_direction` (например, становится `isolation` или `revenge`), полностью меняя свои решения в `DecisionHub`.