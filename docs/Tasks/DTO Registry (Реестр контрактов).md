Ты абсолютно прав. Моя прошлая версия была структурно лучше плоского списка, но она не стала **исполняемым законом**. Я внедрил все 17 пунктов жестких ограничений (HARD CONSTRAINTS), онтологические постулаты и принципы Каузального Контракта v2.0 напрямую в Реестр DTO. 

Теперь это не просто справочник типов, а **Контрольный Список Допуска DTO к Рантайму**. Если DTO или правило его использования нарушает постулат из Контракта — система не должна это пропустить.

---

# DTO Registry — Каузальный Атлас Контрактов ENIGMA
**Основание:** CAUSAL CONTRACT v2.0 (2026-05-21)

> **Формат:** Домен пайплайна → Поток данных → Актуальные DTO → 🚫 КАУЗАЛЬНЫЕ ЗАПРЕТЫ (HARD CONSTRAINTS).
> ИИ-ассистенту: Нарушение правила из блока 🚫 = архитектурный баг, равносильный крашу пайплайна.

---

## 0. ФИЛОСОФИЯ КОНТРАКТОВ (L0-L1-L2)
Все DTO в системе подчиняются трехуровневой архитектуре восприятия:
- **L0 (PERCEPTION):** Мир → Восприятие. Никакой телепатии. Игрок и NPC получают информацию симметрично через `PerceptualKernel` / `ProjectionPolicy`.
- **L1 (BODY):** Инерция личности. Любая мутация стана должна подчиняться формуле: `new_value = (old_value * core.rigidity) + (delta * (1 - core.rigidity))`. Моментальные скачки = баг.
- **L2 (BEHAVIOR):** `DecisionHub` — единственный источник решений. Давление искривляет utility, но не приказывает.

---

## 1. ВВОД И СЖАТИЕ (Input & Intent Compression)
**Поток:** Сырой текст → Семантическое поле → Строгие параметры намерения.

**Актуальные DTO:**
- **`IntentSemanticField`** (`domain/intent_profile.py`): Вероятностное поле. `ActionType` (включая `UNCERTAIN`), `TargetZone`, `SemanticAmbiguity`, `EmotionalVector`, `ConfidenceVector`.
- **`IntentParametersDTO`** (`domain/intent.py`): Строгий контракт. `semantic_action`, `target_reference`, `target_id`, `physical_force`, `emotional_charge`, `social_pressure`.

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Контракт §2.1, §3.2):**
- ❌ **Слепота Fuzzy Matching (Rule 14):** Удаление поля `name` из `npc_positions` запрещено. Без `name` Слой 2 слеп.
- ❌ **Silent Fallback:** Если `target_ref` не резолвится, действие обязано стать `UNCERTAINTY`, а не подменяться на `OBSERVE`.
- ❌ **Легаси-ключи:** Использование старых ключей `attack_target` вместо `player_attacks` / `player_threatens` ломает Трубу Давления.

---

## 2. ВОЛЯ И ДАВЛЕНИЕ (Will & Pressure)
**Поток:** Параметры намерения → Вектор давления → Искажение аффектом → Вычисление сопротивления.

**Актуальные DTO:**
- **`IntentPressureProfile`** (`models/will.py`): Вектор давления на психику (violence, humiliation, self_risk, moral_violation, identity_deviation).
- **`AmplifiedPressureProfile`** (`models/will.py`): Давление, искаженное `ResponseBias`.
- **`WillResponseDTO`** (`models/will.py`): Результат WillpowerGate. `WillState` (COMPLY→CONDITIONED), `resistance`, `identity_damage`, `counter_offer`, `embodied_vector`.
- **`IntentResolution`** (`models/will.py`): Транзитный DTO Фазы 1. Содержит финальный вердикт по воле.

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Контракт §4.2):**
- ❌ **Решение без происхождения (Rule 6):** Создание `MovementIntent` без `pressure_sources` запрещено.
- ❌ **Double Invocation (Rule 8):** WillpowerGate вызывается ОДИН раз за цикл. Фаза 1 только переводит семантику.
- ❌ **Обход Резолвера (§2.1):** Хардкод давления (напр. `stress += 20`) в обход `IntentPressureResolver` запрещен.

---

## 3. ПРИЧИННОСТЬ И ВОСПРИЯТИЕ (CFRM & Perception)
**Поток:** Факт реальности → Возмущение поля → Проекция наблюдателем → Психологическое давление.

**Актуальные DTO:**
- **`FieldDisturbance`** (`models/cfrm.py`): Возмущение поля. Оси: кинетика, акустика, материя, поведение. Имеет `semantic_seed`.
- **`PerceivedPhenomenon`** (`models/cfrm.py`): Субъективный феномен. `perceived_archetype`, `mutation_stage`, `distortion_nature`.
- **`PsychologicalPressure`** (`models/cfrm.py`): Выход солвера. Векторы давления, включая `directive_obedience`.
- **`PerceptualKernel`** (`models/npc_state.py`): Субъективная модель NPC. `threat`, `trust`, `uncertainty`, `anomaly`, `compliance_bias`, `initiative_suppression`, `recent_directive`.

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Контракт §1.1, §4.2, §4.3):**
- ❌ **Давление из пустоты (Rule 7):** Получение давления через мембрану с `attenuation=0.0` запрещено.
- ❌ **Повторное вычисление в восприятии (Rule 12):** `PerceptualAttentionService` читает ТОЛЬКО `PerceptionEvent.salience`, чтение `StateDeltas.fear_delta` запрещено.
- ❌ **Телепатия (Rule 11, §1.1):** Передача Игроку информации, которую NPC не мог получить через `PerceptualKernel`, запрещена.

---

## 4. РЕШЕНИЯ И ДВИЖЕНИЕ (Decision & Locomotion)
**Поток:** Восприятие + Давление → Контекст → Искривление Utility → Интент → Транзит.

**Актуальные DTO:**
- **`DecisionContext`** (`domain/decision_context.py`): `UtilityFieldDeformation`, `ActionSpaceCompression`. Формируется из `PerceptualKernel` строго в сервисном слое.
- **`MacroMovementGoal` / `LocalSteeringGoal`** (`domain/movement.py`): `MacroMovementGoal` (LOD1) — навигация по графу, содержит `target_node_id`, `from_node_id`, `target_local_xy` (ADR-065, точные координаты цели внутри узла). `LocalSteeringGoal` (LOD0) — микро-рулежка, содержит `local_target_xy`. `MovementIntent` — легаси-алиас для `MacroMovementGoal`.
- **`TraversalState`** (`models/`): Физическое состояние перемещения. `source_node`, `target_node`, `waypoints`, `progress` (0.0-1.0), `speed`, `created_tick`.
- **`SceneChange`**: Проекция свершившегося для фронтенда. Содержит `target_local_xy` (ADR-065) и `from_node_id` для корректного расчета точки старта транзита.

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Контракт §2.2, §2.3, §4.1):**
- ❌ **SceneChange как триггер (Rule 4, §2.2):** Вызов `scene_manager.apply_changes()` из подписчика событий запрещен. SceneChange — только адаптер.
- ❌ **Смешение LOD (Rule 5):** Использование `LocalSteeringGoal` для макро-маршрутизации или `MacroMovementGoal` для микро-рулежки запрещено. Исключение ADR-065: `MacroMovementGoal.target_local_xy` разрешен для указания точных координат цели внутри узла назначения (подход к игроку), но не для микро-уклонений.
- ❌ **Прямая мутация позиции (Rule 1):** `npc["position"] = ...` запрещено.
- ❌ **Неавторитетный источник (Rule 2):** Чтение позиции из `scene_state["player_spatial"]` запрещено. Авторитетный источник позиции игрока — `npc_positions.player` (куда `_update_player_position` записывает координаты от фронтенда). `player_spatial` — мёртвый источник (запись запрещена ADR-048 Phase 3), использовать только как fallback при отсутствии `npc_positions.player.local_position`.
- ❌ **Телепортация Игрока (Rule 3):** Обход задержек для Игрока (`if target == player: bypass latency`) запрещен. Игрок подвержен мембранам.

---

## 5. ФИЗИОЛОГИЯ И БОЙ (Physiology & Combat)
**Поток:** Контакт → Урон → Боль → Шок-импульс.

**Актуальные DTO:**
- **`InjuryDTO`**: Анатомическая модель (target_zone, теги).
- **`PhysiologyPayload`** (`models/delta_payloads.py`): `hp`, `pain`, `blood_loss`, `shock_impulse`. Выход `ImpactEngine`.

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Контракт §4.2):**
- ❌ **Domain Leakage (Rule 9):** `CombatSubscriber` пишет ТОЛЬКО `PhysiologyPayload`. Прямая генерация эмоций из боя запрещена. Эмоции рождаются позже из `shock_impulse`.

---

## 6. МУТАЦИЯ И ЭМОЦИИ (State Mutation & Affective Integration)
**Поток:** Все изменения → Буфер → Агрегация → Интеграл Аффекта → Эмоция.

**Актуальные DTO:**
- **`DeltaDomain`** (`models/state_delta.py`): `PHYSIOLOGY`, `EMOTION`, `SOCIAL`, `PERCEPTION`, `IDENTITY`, `SPATIAL`.
- **`PerceptionPayload`** (`models/delta_payloads.py`): `threat_gradient_delta`, `uncertainty_delta`, `anomaly_score_delta`. Обновляет `PerceptualKernel`.
- **`EmotionPayload`** (`models/delta_payloads.py`): Порождается **только** после фазового перехода в Аффект-Интеграторе (Фаза 9).
- **`IdentityPayload`** (`models/delta_payloads.py`): `compliance_bias_delta`, `initiative_suppression_delta`, `recent_directive_data`.

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Контракт §2.1, §3.9, §4.2, §4.4):**
- ❌ **Прямая генерация эмоций (§2.1, §3.9):** Эмоции не генерируются из одного события. Они рождаются из интеграла угрозы по времени. Обход `AffectiveIntegrator` запрещен.
- ❌ **Голый вызов Директивы (Rule 10):** `DirectiveInterpretationSubscriber().handle()` без инъекции `all_npcs_raw` запрещен (иначе `ObediencePressure=0.00`).
- ❌ **Ретро-симуляция (Rule 16):** `TICK_CATCHUP` с циклом `LifeEngine.tick()` запрещен. Только `reconcile_state(elapsed_seconds)`.

---

## 7. ПРЕЗЕНТАЦИЯ И UI (Presentation & Frontend)
**Поток:** Runtime Истина → Феноменологическая Проекция → Фронтенд.

**Актуальные DTO:**
- **`WorldSnapshotDTO`** (`domain/snapshot.py`): `npc_positions`, `active_traversals`, `avatar_state`, `ambient_phenomenology`.
- **`NPCPositionDTO`** (`domain/snapshot.py`): Позиция + `initiative_suppression` + Траектория (`waypoints`, `progress`, `speed`).
- **`AvatarStateDTO`** (`domain/snapshot.py`): Непрерывные скаляры: `perceptual_stability`, `cognitive_coherence`, `sensory_noise`.
- **`PlayerPerceptionDTO`**: Транспорт для Фазы 10 (Симметричная линза игрока).

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Контракт §4.3, §4.4):**
- ❌ **Телепатия в UI (Rule 11):** Передача Игроку внутренних состояний NPC (HP, fear) запрещена. Только наблюдаемые симптомы ("дрожит").
- ❌ **Лаг в вводе (Rule 13):** Использование `perceptual_latency` для задержки ввода игрока запрещено. Допускается только визуальный `desync` (шлейфы, инерция камеры).
- ❌ **Краш сериализации (Rule 15):** Использование `asdict()` на границе API без Pydantic/Dataclass валидации запрещено.
- ❌ **Кэш-фантомы (Rule 17):** Не очищен `__pycache__` после рефакторинга DTO = запрещенный запуск.

---

### Список Песочниц (Fail Conditions)
Каждый запрет из этого реестра должен быть покрыт тестом:
- `test_no_direct_mutation_of_position` (Rule 1)
- `test_no_direct_scene_change_in_resolver` (Rule 4)
- `test_pressure_modifies_utility_not_commands` (Rule 6 / L2)
- `test_membrane_visibility_enforced` (Rule 7)
- `test_decision_requires_pressure_provenance` (Rule 6)
- `test_target_resolution_requires_name_in_npc_positions` (Rule 14)
- `test_directive_subscriber_requires_npc_state` (Rule 10)
- `test_no_telepathy_in_ui_observation` (Rule 11)
- `test_willpower_gate_single_invocation_per_tick` (Rule 8)
- `test_affective_load_accumulation_over_time` (§3.9)
- `test_living_npc_inertia_preserved` (L1 Formula)