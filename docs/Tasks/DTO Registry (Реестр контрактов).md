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
- **`IntentSemanticField`** (`domain/intent_profile.py`): Вероятностное поле. `ActionType` (включая `UNCERTAIN`), `TargetZone`, `SemanticAmbiguity`, `EmotionalVector`, `ConfidenceVector`. **ADR-088:** `EmotionalVector` больше не возвращается нулевым из `IntentCompressor._fast_path_parse`. Для `ATTACK` инжектится `aggression=0.8`, для `THREATEN` — `aggression=0.5, fear=0.3`.
- **`IntentParametersDTO`** (`domain/intent.py`): Строгий контракт. `semantic_action`, `target_reference`, `target_id`, `physical_force`, `emotional_charge`, `social_pressure`. **ADR-083:** `semantic_action` — приоритетный источник для `will.py` и `affect.py`. Чтение `intent.action` без fallback на `parameters.semantic_action` = Silent Crash.

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Контракт §2.1, §3.2):**
- ❌ **Слепота Fuzzy Matching (Rule 14):** Удаление поля `name` из `npc_positions` запрещено. Без `name` Слой 2 слеп.
- ❌ **Silent Fallback:** Если `target_ref` не резолвится, действие обязано стать `UNCERTAINTY`, а не подменяться на `OBSERVE`.
- ❌ **Легаси-ключи:** Использование старых ключей `attack_target` вместо `player_attacks` / `player_threatens` ломает Трубу Давления.
- ❌ **Чтение intent.action без fallback:** Обращение к `intent.action` в `will.py`/`affect.py` без fallback на `parameters.semantic_action` — Silent Crash (ADR-083).
- ❌ **Мёртвый Вектор Эмоций (ADR-088):** Возврат дефолтного `EmotionalVector()` (aggression=0.0) из `IntentCompressor` для `ActionType.ATTACK` запрещён.
- ❌ **Подмена Campaign ID (ADR-089):** Использование `location_id` (комната) в качестве `campaign_id` (мир) при создании `_TickContext` запрещено. Это убивает `SpatialService`.

---

## 2. ВОЛЯ И ДАВЛЕНИЕ (Will & Pressure)
**Поток:** Параметры намерения → Вектор давления → Искажение аффектом → Вычисление сопротивления.

**Актуальные DTO:**
- **`IntentPressureProfile`** (`models/will.py`): Вектор давления на психику (violence, humiliation, self_risk, moral_violation, identity_deviation).
- **`AmplifiedPressureProfile`** (`models/will.py`): Давление, искаженное `ResponseBias`.
- **`WillResponseDTO`** (`models/will.py`): Результат WillpowerGate. `WillState` (COMPLY→CONDITIONED), `resistance`, `identity_damage`, `counter_offer`, `embodied_vector`. **ADR-086:** `counter_offer_text` (через `get_embodied_impulse_text()`) — человекочитаемый импульс для инфекции поля ввода. Верифицировано: `'Замереть...'` при `embodied_vector=freeze`.
- **`IntentResolution`** (`models/will.py`): Транзитный DTO Фазы 1. Содержит финальный вердикт по воле.
- **`CommunicationIntent`** (`domain/communication.py`): Единый источник истины для ответа NPC. Обязателен непустой `topic`. **GAP8 FIX:** Добавлены `semantic_action: Optional[str] = None` и `target_id: Optional[str] = None` для проброса семантики директив в `NPC_SPOKE` EventDTO (без этого NPC-to-NPC Social Physics мертва).

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
- **`EditorLocationJSON`** (Data Contract): Источник пространственной истины от Map Editor. Формат: `{"rooms": [{"id": str, "name": str, "x": float, "y": float, "width": float, "height": float, "polygon": list}], "passages": [{"from": str, "to": str}]}`. **ADR-073:** Поле `rooms` парсится как массив (list) объектов. Если `passages` пуст, `graph_compiler` выводит связи автоматически через `Adjacency Inference` (пересечение bounding box).
- **`DecisionContext`** (`domain/decision_context.py`): `UtilityFieldDeformation`, `ActionSpaceCompression`. Формируется из `PerceptualKernel` + `body_state` строго в сервисном слое. **GAP3 FIX:** `body_state` инжектируется для Соматического Вето (`pain > 0.8` блокирует FLEE, `shock > 0.7` блокирует ATTACK, `blood_loss > 0.6` ограничивает физические действия).
- **`EventContext`** (`services/npc/decision_hub.py`): Контекст события для DecisionHub. Содержит `actor_id`, `event_type`, `intensity`. **GAP10 FIX:** Добавлено `target_id: Optional[str] = None` — без этого DecisionHub даёт бонус APPROACH всем NPC в зоне, а не только целевому.
- **`MacroMovementGoal` / `LocalSteeringGoal`** (`domain/movement.py`): `MacroMovementGoal` (LOD1) — навигация по графу, содержит `target_node_id`, `from_node_id`, `target_local_xy` (ADR-069, точные координаты цели внутри узла, пробрасывается через `_resolve_reactive_movement` → `SceneChange` → `scene_state_manager`), `processed` (bool, инвариант единого владения ADR-066), `processor` (str|None, идентификатор обработчика). `LocalSteeringGoal` (LOD0) — микро-рулежка, содержит `local_target_xy`, `processed`, `processor`. `MovementIntent` — легаси-алиас для `MacroMovementGoal`. Повторная обработка интента с `processed=True` вызывает `RuntimeError`.
- **`TraversalState`** (`models/`): Физическое состояние перемещения. `source_node`, `target_node`, `waypoints`, `progress` (0.0-1.0), `speed`, `created_tick`.
- **`SceneChange`**: Проекция свершившегося для фронтенда. Содержит `target_local_xy` (ADR-065) и `from_node_id` для корректного расчета точки старта транзита.

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Контракт §2.2, §2.3, §4.1):**
- ❌ **SceneChange как триггер (Rule 4, §2.2):** Вызов `scene_manager.apply_changes()` из подписчика событий запрещен. SceneChange — только адаптер.
- ❌ **Смешение LOD (Rule 5):** Использование `LocalSteeringGoal` для макро-маршрутизации или `MacroMovementGoal` для микро-рулежки запрещено. Исключение ADR-069: `MacroMovementGoal.target_local_xy` разрешен для указания точных координат цели внутри узла назначения (подход к игроку), но не для микро-уклонений.
- ❌ **Прямая мутация позиции (Rule 1):** `npc["position"] = ...` запрещено.
- ❌ **Неавторитетный источник (Rule 2):** Чтение позиции из `scene_state["player_spatial"]` запрещено. Авторитетный источник позиции игрока — `npc_positions.player` (куда `_update_player_position` записывает координаты от фронтенда). `player_spatial` — мёртвый источник (запись запрещена ADR-048 Phase 3), использовать только как fallback при отсутствии `npc_positions.player.local_position`.
- ❌ **Телепортация Игрока (Rule 3):** Обход задержек для Игрока (`if target == player: bypass latency`) запрещен. Игрок подвержен мембранам.
- ❌ **Двойной исполнитель (Rule 18, ADR-066):** Вызов `process_intents()` или `apply_changes()` из `npc_orchestration.py` запрещен. Единственный владелец — `TickOrchestrator`. Повторная обработка `MovementIntent` с `processed=True` = `RuntimeError`.
- ❌ **Потеря target_local_xy (Rule 19, ADR-069):** Создание `MacroMovementGoal` без проброса `target_local_xy` при `reactive:approach` запрещено. Координаты цели (позиция игрока) обязаны пройти через весь пайплайн до `SceneChange.target_local_xy`.
- ❌ **Enrichment перетирает пайплайн (Rule 20, ADR-072):** `_enrich_local_positions` перетирает `local_position`, установленный пайплайном (micro_snap, collision_avoidance), запрещено. LOD0 guard: если позиция валидна — пропуск.
- ❌ **Ручная простановка passages (ADR-073):** Зависимость компиляции графа от ручной простановки `passages` при наличии полигонов комнат запрещена. Компилятор обязан выводить топологию через смежность (Adjacency Inference).

---

## 5. ФИЗИОЛОГИЯ И БОЙ (Physiology & Combat)
**Поток:** Контакт → Урон → Боль → Шок-импульс.

**Актуальные DTO:**
- **`InjuryDTO`**: Анатомическая модель (target_zone, теги).
- **`PhysiologyPayload`** (`models/delta_payloads.py`): `hp_delta`, `pain_delta`, `blood_loss_delta`, `fatigue_delta`, `shock_impulse`, `add_injuries`, `add_statuses`, `remove_statuses`. Выход `ImpactEngine`. **Критично:** `shock_impulse > 0.5` теперь инжектится мгновенно (T+0) через Когнитивный Оверлей (ADR-081). **ADR-084:** Все поля с `_delta` суффиксом требуют явного извлечения в `state_applicator.py` перед использованием. Использование без extraction = `NameError`. **ADR-099:** `asdict` обязателен на уровне модуля `state_applicator.py` — без него `add_injuries` крашит ВСЮ дельту. **ADR-102:** `shock_impulse` применяется к `body_state["shock_impulse"]` (аддитивно с потолком 1.0). **ADR-109:** `shock_impulse` поддерживает отрицательные дельты (decay) — условие применения `!= 0.0`, а не `> 0.0`. `PhysiologyDecayHandler` генерирует отрицательный `shock_impulse` через `SHOCK_DECAY_LAMBDA=0.08`.
- **`NPCState.body_state`** (`models/npc_state.py`): Dict — рантайм контейнер ВСЕЙ физиологии. Ключи: `current_hp`, `pain` (0-100), `fatigue` (0-100), `blood_loss` (0-1.0), `consciousness` (0-1.0), `shock_impulse` (0-1.0), `injuries` (list), `modifiers` (dict), `statuses` (list). **ADR-100:** `write_to_legacy` и `from_legacy` обязаны сериализовать/десериализовать `body_state` — без этого физиология теряется между тиками.
- **`NPCStateSnapshot`** (`models/idle_tick.py`): READ-ONLY проекция NPC для idle-обработчиков (TypedDict). Поля: `npc_id`, `stress`, `relationship_cache`, `base_values`, `faction_affiliations`, `hp`, `max_hp`, `pain` (0-100), `fatigue` (0-100), `blood_loss` (0-1.0), `consciousness` (0-1.0), **`shock_impulse` (0-1.0)**, `injuries_by_zone`, `base_abilities`, `modifiers`, `statuses`. **ADR-109:** `shock_impulse` добавлен — без него `PhysiologyDecayHandler` не мог затухать шок. Строится в `_build_npc_snapshots()` из `all_npcs_raw` + `body_state`.

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Контракт §4.2):**
- ❌ **Domain Leakage (Rule 9):** `CombatSubscriber` пишет ТОЛЬКО `PhysiologyPayload`. Прямая генерация эмоций из боя запрещена. Эмоции рождаются позже из `shock_impulse`.
- ❌ **Rule X Violation (Rule 26, ADR-101):** `BehaviorManifestationService` читает эмоции (psyche.fear/stress) вместо физиологии (body_state.pain/blood_loss/shock_impulse) — нарушение Правила X (CAUSAL_CONTRACT §7). Моторные следы вычисляются ТОЛЬКО из тела.
- ❌ **body_state Serialization Gap (Rule 27, ADR-100):** `write_to_legacy` / `from_legacy` без сериализации `body_state` — физиология теряется между тиками. Обязательная запись/чтение `body_state` в оба метода.
- ❌ **Shock Immortality (Rule 28, ADR-109):** `shock_impulse` без decay в `PhysiologyDecayHandler` = перманентный шок. Обязателен `SHOCK_DECAY_LAMBDA` и передача `shock_impulse` в `NPCStateSnapshot`.
- ❌ **Shock Delta Block (Rule 29, ADR-109):** `StateApplicator` проверяет `shock_impulse > 0.0` вместо `!= 0.0` — блокирует отрицательные дельты decay.

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
- **`WorldSnapshotDTO`** (`domain/snapshot.py`): `npc_positions`, `active_traversals` (обязателен, ADR-071 — без него фронтенд не интерполирует движение), `avatar_state`, `ambient_phenomenology`.
- **`NPCPositionDTO`** (`domain/snapshot.py`): Позиция + `initiative_suppression` + Траектория (`waypoints`, `progress`, `speed`).
- **`AvatarStateDTO`** (`domain/snapshot.py`): Непрерывные скаляры: `perceptual_stability`, `cognitive_coherence`, `sensory_noise`, `motor_disruption`, `blood_visibility`. Вычисляется из `player_dict.body_state` и `psyche` через `AvatarPresentationAssembler` (ADR-068).
- **`PlayerPerceptionDTO`** (`domain/snapshot.py`): Контейнер наблюдений игрока (Фаза 9). Содержит `embodied_traces` (List: `npc_id`, `is_frozen`, `is_shaking`, `locomotion_instability`, `micro_pause_density`, `action_interruption`) и `peripheral_cues` (List: `npc_id`, `cue_type`, `hover_text`). **ADR-101:** Проецируется из `body_state` (pain/blood_loss/shock_impulse) + `stress_delta`/`psyche_state`, телепатия (fear, trust) запрещена. Cue keys: TENSE_POSTURE, SWAYING, UNEVEN_STANCE, ABRUPT_STOP, FREQUENT_PAUSES, WINCING, HOLDING_SIDE, BLEEDING, STAGGERED.
- **`EmbodiedTraceDTO`** (`domain/embodied_trace.py`): Наблюдаемые моторные и физические паттерны NPC. Поля: `npc_id`, `locomotion_instability` (0-1, дрожь/пошатывание от pain/shock), `posture_rigidity` (0-1, замер от pain/alert), `gaze_break_rate` (0-1), `action_interruption` (0-1, прерванное действие от shock>0.5), `micro_pause_density` (0-1, микро-остановки от blood_loss/fatigue), `is_frozen`, `is_shaking`. **ADR-101:** Вычисляется в `BehaviorManifestationService` из `body_state` (Правило X), НЕ из эмоций.
- **`PerceivedEntity`** (Frontend `game_screen.py`): Доменная модель рендерера. Содержит `is_frozen`, `is_shaking`, `instability` (моторные следы), `perception_cues` (наблюдения для тултипов). Маппится из `PlayerPerceptionDTO` по `npc_id`.
- **`GameActionResponse`** (`frontend/api_client.py`): `dm_response`, `npc_reactions`, `world_changes`, `world_snapshot`, **`will_conflict_data`** (dict | None, проброс ADR-041/068).
- **`player_dict` (в all_npcs_raw)**: Обязан содержать инъецированные `body_state` (dict: pain, blood_loss, consciousness) и `psyche` (dict: stress, fear, willpower) для корректной работы `AvatarPresentationAssembler` (ADR-068).
- **`PipelineContext`** (`models/pipeline_context.py`): Строготипизированный контекст пайплайна. **S57:** Добавлено поле `player_perception` (Any, default=None) — Фаза 9: `embodied_traces`, `peripheral_cues`. Запись из `tick_orchestrator.py:712`, чтение DM-агентом.
- **`spatial_obstacles`** (dict внутри `scene_state`): Препятствия и мебель из editor JSON. **ADR-102:** Добавлено поле `type` (str: "bar", "table", "chair", "decoration" и т.д.) — пробрасывается из editor JSON через `scene_state_manager._build_spatial_data()` на фронтенд для рендера спрайтов через `sprite_resolver.py`. Ранее фронтенд получал заглушки-прямоугольники.
- **`scene_state`** (dict): Состояние локации. **ADR-102:** Добавлено поле `campaign_id` (str) — инжектируется в `get_scene_state()` для работы `SpatialService.build_for_location()`. Без этого SpatialService не может найти editor JSON.
- **`VerbalizationContext`** (`services/verbalization/verbalization_context.py`): Контекст для LLM-вербализации NPC. **S57:** Добавлено поле `physical_state` (str, default="unharmed") — GAP5 FIX: Витализм, боль и шок перекрывают HP. Заполняется из `StateInterpreter.interpret()`. **S60:** `intent_target` получил дефолт `= None` (ADR-107 — безопасность field order). Дефолт `physical_state` заменён с `"невредим"` на `"unharmed"` (L10n-safe).
- **`NPCStateDescription`** (`services/verbalization/state_interpreter.py`): Выход `StateInterpreter.interpret()`. Поля: `name`, `intent`, `emotional_state`, `physical_state`, `posture`, `conditions`, `can_speak`, `can_move`, `gender`. **S60 ДИАГНОСТИКА:** `emotional_state` (из `UrgencyLevel`) — dormant/dead поле, нет runtime-потребителей (ADR-108). `physical_state` — живое, легитимное.

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Контракт §4.3, §4.4):**
- ❌ **Телепатия в UI (Rule 11):** Передача Игроку внутренних состояний NPC (HP, fear) запрещена. Только наблюдаемые симптомы ("дрожит").
- ❌ **Лаг в вводе (Rule 13):** Использование `perceptual_latency` для задержки ввода игрока запрещено. Допускается только визуальный `desync` (шлейфы, инерция камеры).
- ❌ **Краш сериализации (Rule 15):** Использование `asdict()` на границе API без Pydantic/Dataclass валидации запрещено.
- ❌ **Кэш-фантомы (Rule 17):** Не очищен `__pycache__` после рефакторинга DTO = запрещенный запуск.
- ❌ **Обрыв Bridge (Rule 21, ADR-071):** `game_loop_bridge.py` не пробрасывает `active_traversals` в `world_snapshot` = фронтенд слеп к движению. Запрещено строить `world_snapshot` без `active_traversals`.
- ❌ **Затирание Perception (Rule 22, ADR-092):** `game_loop_bridge.py` перезаписывает `result.world_snapshot` целиком, уничтожая `player_perception` от бэкенда. Разрешено только точечное обновление ключей (`result.world_snapshot["npc_positions"] = ...`).
- ❌ **Kernel Leakage в DM (Rule 23, ADR-093):** DM-агент читает внутренние состояния NPC (pain, fear, shock) напрямую вместо `embodied_traces` из `player_perception`. DM описывает наблюдаемые следы, а не причины.
- ❌ **Масштабная несовместимость pain (Rule 24, ADR-094):** `StateApplicator` пишет `pain` в 0-100, а интерпретаторы без нормализации читают 0-1. Обязательна нормализация `pain / 100.0` при чтении из `body_state`.
- ❌ **Нелегализованные поля PipelineContext (Rule 25):** Запись в `shared_context` полей, не объявленных в `PipelineContext` = архитектурное нарушение (Устав §11).
- ❌ **Duplicate Psychological Resolution (Rule 26, ADR-108):** `StateInterpreter` вычисляет `UrgencyLevel` (SCARED/PANIC/BROKEN) из `NPCState.stress` — это дублирует `EmotionTag` от `EmotionResolution`, но без учёта личности. Runtime-потребитель не найден (dormant/dead), но два владельца одной концепции = архитектурный долг.
- ❌ **Semantic Action Before Resolution (Rule 27, ADR-105):** Вызов `publish_classified_player_event` ДО `resolve_player_intent` запрещён — `_semantic_action` всегда `None`, ADR-091 override мёртв.

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
- `test_movement_processed_once` (Rule 18, ADR-066)
- `test_target_local_xy_propagated_through_pipeline` (Rule 19, ADR-069)
- `test_enrichment_does_not_overwrite_pipeline_position` (Rule 20, ADR-072)
- `test_bridge_includes_active_traversals` (Rule 21, ADR-071)
- `test_fast_path_emotional_vector_injection` (ADR-088)
- `test_campaign_id_not_replaced_by_location_id` (ADR-089)
- `test_adjacency_inference_without_passages` (ADR-073)