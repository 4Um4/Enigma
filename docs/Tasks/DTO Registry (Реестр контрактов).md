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
- **`IntentParametersDTO`** (`domain/intent.py`): Строгий контракт. `semantic_action`, `target_reference`, `target_id`, `physical_force`, `emotional_charge`, `social_pressure`. **ADR-083:** `semantic_action` — приоритетный источник для `will.py` и `affect.py`. Чтение `intent.action` без fallback на `parameters.semantic_action` = Silent Crash. **ADR-125:** `target_id` — DEPRECATED. Фактически мёртв. Истина идёт через `PlayerTargetExtractor` + `intent.target`. Оставлен как диагностический маркер расхождения алгоритмов.

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Контракт §2.1, §3.2):**
- ❌ **Слепота Fuzzy Matching (Rule 14):** Удаление поля `name` из `npc_positions` запрещено. Без `name` Слой 2 слеп.
- ❌ **Silent Fallback:** Если `target_ref` не резолвится, действие обязано стать `UNCERTAINTY`, а не подменяться на `OBSERVE`.
- ❌ **Легаси-ключи:** Использование старых ключей `attack_target` вместо `player_attacks` / `player_threatens` ломает Трубу Давления.
- ❌ **Чтение intent.action без fallback:** Обращение к `intent.action` в `will.py`/`affect.py` без fallback на `parameters.semantic_action` — Silent Crash (ADR-083).
- ❌ **Мёртвый Вектор Эмоций (ADR-088):** Возврат дефолтного `EmotionalVector()` (aggression=0.0) из `IntentCompressor` для `ActionType.ATTACK` запрещён.
- ❌ **Подмена Campaign ID (ADR-089):** Использование `location_id` (комната) в качестве `campaign_id` (мир) при создании `_TickContext` запрещено. Это убивает `SpatialService`.
- ❌ **Target ID Blindness (Rule 58, ADR-130):** `_context_relevance()` ОБЯЗАН проверять `EventContext.payload["target_id"]` как fallback при `EventContext.target_id is None`. `dm_scene_builder` не пробрасывает target_id в EventContext.target_id, но `dm_phase.py` записывает его в payload. Без fallback `is_targeted = (event.target_id is None or ...)` даёт True для ВСЕХ NPC в зоне — незваные NPC подходят к игроку (G2).

---

## 2. ВОЛЯ И ДАВЛЕНИЕ (Will & Pressure)
**Поток:** Параметры намерения → Вектор давления → Искажение аффектом → Вычисление сопротивления.

**Актуальные DTO:**
- **`IntentPressureProfile`** (`models/will.py`): Вектор давления на психику (violence, humiliation, self_risk, moral_violation, identity_deviation).
- **`AmplifiedPressureProfile`** (`models/will.py`): Давление, искаженное `ResponseBias`.
- **`WillResponseDTO`** (`models/will.py`): Результат WillpowerGate. `WillState` (COMPLY→CONDITIONED), `resistance`, `identity_damage`, `counter_offer`, `embodied_vector`. **ADR-086:** `counter_offer_text` (через `get_embodied_impulse_text()`) — человекочитаемый импульс для инфекции поля ввода. Верифицировано: `'Замереть...'` при `embodied_vector=freeze`.
- **`IntentResolution`** (`models/will.py`): Транзитный DTO Фазы 1. Содержит финальный вердикт по воле.
- **`CommunicationIntent`** (`domain/communication.py`): Единый источник истины для ответа NPC. Обязателен непустой `topic`. **GAP8 FIX:** Добавлены `semantic_action: Optional[str] = None` и `target_id: Optional[str] = None` для проброса семантики директив в `NPC_SPOKE` EventDTO (без этого NPC-to-NPC Social Physics мертва).

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Контракт §4.2, ADR-O-139):**
- ❌ **Решение без происхождения (Rule 6):** Создание `MovementIntent` без `pressure_sources` запрещено.
- ❌ **Double Invocation (Rule 8):** WillpowerGate вызывается ОДИН раз за цикл. Фаза 1 только переводит семантику.
- ❌ **Обход Резолвера (§2.1):** Хардкод давления (напр. `stress += 20`) в обход `IntentPressureResolver` запрещен.
- ❌ **Fallback без тела (Rule 92, ADR-O-139):** Создание NPC dict без `body_state` в `DirectiveInterpretationSubscriber` запрещено. Убит `{"social_stats": {"fear_of_player": 0.1}}` — создавал логических призраков. NPIC: нет тела = нет когнитивной интерпретации.
- ❌ **Somatic Gate после парсинга (Rule 93, ADR-O-139):** Проверка `shock > 0.7` ПОСЛЕ семантического парсинга директивы запрещена. Тело определяет *доступность* интерпретации, а не модулирует результат. Каузальный порядок: `Body → Somatic Gate → Semantic Parsing → Legitimacy → Action`.
- ❌ **Skip без Sentinel (Rule 94, ADR-O-139):** `if not body_state: return []` без инъекции `BODY_STATE_DISABLED` запрещён. Вызывает State Starvation Collapse при холодном старте. Normalization Gate в `tick_orchestrator.py` обязан заполнить `BODY_STATE_DISABLED` перед использованием `ctx.all_npcs_raw`.

---

## 3. ПРИЧИННОСТЬ И ВОСПРИЯТИЕ (CFRM & Perception)
**Поток:** Факт реальности → Возмущение поля → Проекция наблюдателем → Психологическое давление.

**Актуальные DTO:**
- **`FieldDisturbance`** (`models/cfrm.py`): Возмущение поля. Оси: кинетика, акустика, материя, поведение. Имеет `semantic_seed`.
- **`PerceivedPhenomenon`** (`models/cfrm.py`): Субъективный феномен. `perceived_archetype`, `mutation_stage`, `distortion_nature`.
- **`PsychologicalPressure`** (`models/cfrm.py`): Выход солвера. Векторы давления, включая `directive_obedience`.
- **`PerceptualKernel`** (`models/npc_state.py`): Субъективная модель NPC (L1 — Поле Причин). 10 полей: `threat_gradient`, `trust_gradient`, `uncertainty`, `anomaly_score`, `last_hostile_direction`, `dominant_emotion`, `aggression_inhibition`, `initiative_suppression`, `compliance_bias`, `recent_directive`. **ADR-115:** Обязательная сериализация/десериализация в `write_to_legacy` / `from_legacy`. Без этого DOUBLE TRUTH — восприятие сбрасывается в 0.0 каждый тик, guards "мёртвые", эмоции не накапливаются. **Rule 38 / ADR-138:** Поля `threat_gradient`, `uncertainty`, `anomaly_score` ОБЯЗАНЫ затухать в idle-тиках (Фаза 0.5). Без этого Фаза 9 вечно реконструирует страх из устаревшего PK. `affective_load` — персистентный интеграл (L0), релаксирующий к `target_load` с гистерезисом. Обязательная сериализация.

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Контракт §1.1, §4.2, §4.3, §138):**
- ❌ **Давление из пустоты (Rule 7):** Получение давления через мембрану с `attenuation=0.0` запрещено.
- ❌ **Повторное вычисление в восприятии (Rule 12):** `PerceptualAttentionService` читает ТОЛЬКО `PerceptionEvent.salience`, чтение `StateDeltas.fear_delta` запрещено.
- ❌ **Телепатия (Rule 11, §1.1):** Передача Игроку информации, которую NPC не мог получить через `PerceptualKernel`, запрещена.
- ❌ **Perception & Social Serialization (Rule 31, ADR-115/121/138):** `write_to_legacy` / `from_legacy` сериализует `perceptual_kernel` и `affective_load`. `relationship_cache` больше НЕ сериализуется (SSOT = RelationshipStore, ADR-121). `affective_load` — персистентный интеграл (L0), ОБЯЗАТЕЛЬНО сериализуется (ADR-138). Производной является только `target_load` (L2).
- ❌ **Runtime Overlay Integrity (Rule 33, ADR-118):** `_apply_runtime_overlay` в `npc_loader.py` мержит ТОЛЬКО ключи из `_RUNTIME_TOP_LEVEL_KEYS` и `_RUNTIME_PSYCHE_KEYS`. Отсутствие `affective_load`, `emotion`, `emotion_delta`, `body_state`, `perceptual_kernel`, `narrative_cache` в белых списках = затирание вычисленного состояния статикой при каждом чтении с диска. **Текущий whitelist:** `_RUNTIME_TOP_LEVEL_KEYS = frozenset({"social_stats", "location", "hp", "max_hp", "current_role", "role_history", "conditions", "wounds", "threat_accumulator", "posture", "temporary_drives", "causal_ledger", "affective_load", "emotion", "emotion_delta", "body_state", "perceptual_kernel", "narrative_cache"})`.
- ❌ **Leaky Integrator / Perpetual Fear (Rule 84/85, ADR-138):** Использование интегратора с утечкой (`load + incoming - recovery`) для `affective_load` ЗАПРЕЩЕНО. Только Асимметричный Аттрактор (Гистерезис). Хранение `threat_gradient` навсегда без idle-decay ЗАПРЕЩЕНО.
- ❌ **Affective Boot (Rule 86, ADR-138):** Подтягивание `affective_load` до порога `emotion_tag` (Anti-DOUBLE TRUTH bootstrap) ЗАПРЕЩЕНО. Положительная обратная связь порождает "вечный двигатель страха".

---

## 4. РЕШЕНИЯ И ДВИЖЕНИЕ (Decision & Locomotion)
**Поток:** Восприятие + Давление → Контекст → Искривление Utility → Интент → Транзит.

**Актуальные DTO:**
- **`EditorLocationJSON`** (Data Contract): Источник пространственной истины от Map Editor. Формат: `{"rooms": [{"id": str, "name": str, "x": float, "y": float, "width": float, "height": float, "polygon": list}], "passages": [{"from": str, "to": str}]}`. **ADR-073:** Поле `rooms` парсится как массив (list) объектов. Если `passages` пуст, `graph_compiler` выводит связи автоматически через `Adjacency Inference` (пересечение bounding box).
- **`DecisionContext`** (`domain/decision_context.py`): `UtilityFieldDeformation`, `ActionSpaceCompression`. Формируется из `PerceptualKernel` + `body_state` строго в сервисном слое. **GAP3 FIX:** `body_state` инжектируется для Соматического Вето (`pain > 0.8` блокирует FLEE, `shock > 0.7` блокирует ATTACK, `blood_loss > 0.6` ограничивает физические действия).
- **`EventContext`** (`services/npc/decision_hub.py`): Контекст события для DecisionHub. Поля: `actor_id`, `event_type`, `intensity`, `distance`, `witness_count`, `location`, `day`, `target_id: Optional[str]`, `visible_threat_markers: List[str]`, `target_routine: str`, `scene_flags: Set[str]`, `scene_facts: List[str]`, `payload: Dict[str, Any]`. **GAP10 FIX:** `target_id` — без этого DecisionHub даёт бонус APPROACH всем NPC в зоне. **S64 FIX:** `payload` — проброс `semantic_action`, `target_id`, `target_reference` из `IntentParametersDTO` через PAYLOAD_INJECT. Без payload PHYSICS_OF_POWER (ADR-036) не активируется. **ADR-121:** `relationship_cache` = строго вложенный `{"target_id": {"trust": 0-100, "fear": 0-100}}`. Эфемерный read-кэш из RelationshipStore. Потребители нормализуют 0-100 → 0-1. **S69 ONTOLOGY MERGE:** Чтение `relationship_cache` внутри DecisionHub унифицировано через `_get_rel_value` (Precedence Contract: Graph > Scalar > Vacuum). Прямое чтение ключей запрещено. **S69 ONTOLOGY MERGE:** Чтение `relationship_cache` внутри DecisionHub унифицировано через `_get_rel_value` (Precedence Contract: Graph > Scalar > Vacuum). Прямое чтение ключей запрещено.
- **`IntentDomain`** (`domain/movement.py`): Enum онтологических доменов намерений. `SURVIVAL` (угроза, бегство, оборона), `SOCIAL` (взаимодействие, подход, разговор), `ROUTINE` (расписание, работа, сон, рутина), `EXPLORATION` (исследование, случайные события). **ADR-O-137:** Viability mask проекция PerceptualKernel → IntentDomain → допустимое пространство генерации. SURVIVAL ⟂ ROUTINE (ортогональные оси — наличие SURVIVAL давления исключает ROUTINE из генерации).
- **`MacroMovementGoal` / `LocalSteeringGoal`** (`domain/movement.py`): `MacroMovementGoal` (LOD1) — навигация по графу, содержит `target_node_id`, `from_node_id`, `target_local_xy` (ADR-069), `domain: IntentDomain = IntentDomain.ROUTINE` (ДОЛГ 4.3 — онтологический домен намерения, определяет viability), `processed` (bool, инвариант единого владения ADR-066), `processor` (str|None, идентификатор обработчика). `LocalSteeringGoal` (LOD0) — микро-рулежка, содержит `local_target_xy`, `processed`, `processor`. `MovementIntent` — легаси-алиас для `MacroMovementGoal`. Повторная обработка интента с `processed=True` вызывает `RuntimeError`.
- **`TraversalState`** (`models/`): Физическое состояние перемещения. `source_node`, `target_node`, `waypoints`, `progress` (0.0-1.0), `speed`, `created_tick`.
- **`SceneChange`**: Проекция свершившегося для фронтенда. Содержит `target_local_xy` (ADR-065) и `from_node_id` для корректного расчета точки старта транзита.

### 4.5 DRF & CAUSAL FIELD (Dynamic Recompression Field)

**Поток:** Причинные претензии → Scoped контекст → Шина → Скоринг overlay → Модуляция приоритета интентов → Drain (observer).

**Актуальные DTO:**
- **`DRFBus`** (`services/tick_orchestrator.py`): Instance-level singleton оркестратора. Единственная шина причинных напряжений тика. Переживает `execute()` + `execute_player_finalize()`. Методы: `emit(claim: dict)`, `drain() → list[dict]`. Сброс через `stream.clear()` на начало `execute()`. **ADR-134:** Запрещено создание через `default_factory=DRFBus` в `_TickContext` — split-brain при двух контекстах.
- **`DRFExecutionContext`** (`services/tick_orchestrator.py`): Scoped causal ledger. Dataclass: `tick_id: int`, `npc_id: Optional[str]`, `bus: Any` (DRFBus). Методы: `for_npc(npc_id) → DRFExecutionContext` (создаёт scoped копию с тем же bus), `emit(claim)` (авто-привязка `npc_id` + `tick_id`), `drain() → list[dict]` (делегирует bus). **ADR-136:** Pipeline получает `drf_ctx`, а не голый `drf_bus`. Claim наследует `npc_id` из контекста, устраняя ручное заполнение `target_npc`.
- **`CausalClaim`** (dict contract): Причинная претензия в шину. Обязательные поля: `source` (str: "reactive_cognition" | "life_engine_routine"), `pressure_type` (str: "SURVIVAL" | "SOCIAL" | "ROUTINE"), `energy` (float: 0.0–1.0, сила давления), `vector` (str: "flee" | "approach" | "schedule:working" и т.д.), `target_node` (str|None). Авто-привязываемые поля (через `DRFExecutionContext.emit()`): `target_npc` (str, из `npc_id` контекста если отсутствует), `npc_id` (str, из контекста), `tick_id` (int, из контекста). Опциональные: `half_life` (float, тиков до затухания).
- **`_DRF_PRESSURE_WEIGHTS`** (dict constant): Веса типов давления для аддитивного скоринга. `SURVIVAL=0.15`, `SOCIAL=0.10`, `ROUTINE=0.02`. **ADR-135:** SURVIVAL имеет 7.5× больший вес чем ROUTINE — поле давлений, а не ярлык.
- **`_DRF_ALIGNED`** / **`_DRF_MISALIGNED`** (float constants): Множители alignment при скоринге. `1.0` (claim vector ∈ intent reason), `0.3` (частичное давление).

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Контракт §5, ADR-134/135/136):**
- ❌ **Split-Brain Bus (Rule 73, ADR-134):** `DRFBus` через `default_factory=DRFBus` в `_TickContext` запрещён — создаёт независимую шину при втором контексте. Только `self._drf_bus` оркестратора.
- ❌ **Monkey-Patch Injection (Rule 74, ADR-134):** Инъекция шины через `func.drf_bus = bus` запрещена — нарушает причинную прозрачность (Python scoping).
- ❌ **Missing Idle Drain (Rule 75, ADR-134):** `_phase_10_persistence` без DRF drain — idle claims теряются навсегда.
- ❌ **Bare Bus in Pipeline (Rule 76, ADR-136):** Передача голого `drf_bus` в pipeline вместо `drf_ctx` — потеря scoped identity (`npc=?`).
- ❌ **Player Path Without Overlay (Rule 77, ADR-135):** DRF overlay только в idle path запрещён — player path обходит арбитраж (две разные физики мира).
- ❌ **Viability via _drf_killed (Rule 78, ДОЛГ 4.3):** Viability veto через `_drf_killed` флаг или `priority=0` в MovementEngine — скрытый скоринг вместо viability. Конфликт мотиваций решается ДО генерации интента.
- ❌ **String-based Viability (Rule 79, ДОЛГ 4.3):** Viability veto через парсинг строк (`"schedule" in reason`) — ломается при смене имён. Только через типизированные IntentDomain.
- ❌ **Clamp Override (Rule 80, ADR-135):** `max(priority, N)` при шкале 0.0–1.0 — уничтожение шкалы. Только аддитивный скоринг `priority += bonus`.
- ❌ **Post-Generation Filtering (Rule 87, ADR-O-137):** Фильтрация кандидатов ПОСЛЕ генерации вместо pre-generation gate — ROUTINE уже мутирует `routine["current"]` и создаёт SceneChange до фильтрации. Viability gate должен стоять ДО вызовов генераторов.
- ❌ **Domain-less MovementIntent (Rule 88, ADR-O-137):** `MovementIntent` без поля `domain` — viability mask не может работать, онтологическая неполнота.

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
- ❌ **Scoping Trap (Rule 32, ADR-116):** Использование переменных из локальной области другой функции (Python scoping trap) — `NameError` глотается `try/except` → тихая потеря интента. Все константы (например, `PRIORITY_*`) должны импортироваться на уровне модуля или передаваться явно.
- ❌ **Schedule Override Reactive Movement (Rule 57, ADR-130):** `update_routine()` НЕ имеет права мутировать `routine["current"]` или создавать schedule intent, если NPC имеет активный traversal со статусом MOVING. Traversal = commitment, schedule = suggestion. Проверка `scene_state.active_traversals[npc_id].status` ОБЯЗАТЕЛЬНА. Без этого schedule перезаписывает reactive movement каждый idle tick (G1). `update_routine()` должен получать `scene_state` через `_simulate_major/minor()`.

---

## 5. ФИЗИОЛОГИЯ И БОЙ (Physiology & Combat)
**Поток:** Контакт → Урон → Боль → Шок-импульс.

**Актуальные DTO:**
- **`InjuryDTO`** (`models/delta_payloads.py`): `damage_type`, `target_zone`, `structural_damage` (0-1.0), `functional_loss` (0-1.0), `critical_effects` (tuple). Выход `ImpactEngine`. **ADR-123:** `critical_effects` — информационные теги, НЕ источник логики. Bleeding rate выводится из свойств раны (зона, тип, глубина), не из строковых флагов.
- **`PhysiologyPayload`** (`models/delta_payloads.py`): `hp_delta`, `pain_delta`, `blood_loss_delta`, `fatigue_delta`, `shock_impulse`, `add_injuries`, `add_statuses`, `remove_statuses`. Выход `ImpactEngine`. **Критично:** `shock_impulse > 0.5` теперь инжектится мгновенно (T+0) через Когнитивный Оверлей (ADR-081). **ADR-084:** Все поля с `_delta` суффиксом требуют явного извлечения в `state_applicator.py` перед использованием. Использование без extraction = `NameError`. **ADR-099:** `asdict` обязателен на уровне модуля `state_applicator.py` — без него `add_injuries` крашит ВСЮ дельту. **ADR-102:** `shock_impulse` применяется к `body_state["shock_impulse"]` (аддитивно с потолком 1.0). **ADR-109:** `shock_impulse` поддерживает отрицательные дельты (decay) — условие применения `!= 0.0`, а не `> 0.0`. `PhysiologyDecayHandler` генерирует отрицательный `shock_impulse` через `SHOCK_DECAY_LAMBDA=0.08`. **ADR-122:** `affective_load` убран из payload — вычисляется на лету из active causes.
- **`LifeStatus`** (`domain/vital_state.py`): Enum `ALIVE` / `DEAD`. Переходный вариант — смерть только от кровопотери. **ADR-123:** ЕДИНСТВЕННЫЙ источник истины о жизни/смерти. Фантомная онтология (brain_integrity, heart_function) запрещена до появления причинного источника. Три оси: `evaluate_vital_state()` → LifeStatus, `is_conscious()` → bool, `is_capable()` → bool.
- **`BODY_STATE_DISABLED`** (`models/npc_state.py`): Константа sentinel. Используется когда `body_state` отсутствует в NPC dict. Значения: `disabled=True, shock_impulse=1.0, pain=100.0, blood_loss=1.0, consciousness=0.0, current_hp=0, fatigue=100.0`. **NPIC (ADR-O-139):** Отсутствие данных ≠ нейтральное состояние (§ENIGMA-003). Агент без тела = инертная материя, не логический призрак.

- **`NPCState.body_state`** (`models/npc_state.py`): Dict — рантайм контейнер ВСЕЙ физиологии. Ключи: `current_hp`, `pain` (0-100), `fatigue` (0-100), `blood_loss` (0-1.0), `consciousness` (0-1.0), `shock_impulse` (0-1.0), `injuries` (list), `modifiers` (dict), `statuses` (list), **`life_status` (str: "ALIVE"/"DEAD", ADR-123/127)**. **ADR-100/127:** `write_to_legacy` и `from_legacy` обязаны сериализовать/десериализовать `body_state` — без этого физиология теряется между тиками. `if state.body_state:` ЗАПРЕЩЕНО — только `is not None` (Rule 44, ADR-127). **ADR-O-139:** Проверка `_body.get("disabled")` в `DirectiveInterpretationSubscriber` блокирует когнитивную интерпретацию для sentinel состояния.
- **`NPCStateSnapshot`** (`models/idle_tick.py`): READ-ONLY проекция NPC для idle-обработчиков (TypedDict). Поля: `npc_id`, `stress`, `relationship_cache`, `base_values`, `faction_affiliations`, `hp`, `max_hp`, `pain` (0-100), `fatigue` (0-100), `blood_loss` (0-1.0), `consciousness` (0-1.0), **`shock_impulse` (0-1.0)**, **`life_status` (str: "ALIVE"/"DEAD", ADR-127)**, `injuries_by_zone`, `base_abilities`, `modifiers`, `statuses`. **ADR-109:** `shock_impulse` добавлен — без него `PhysiologyDecayHandler` не мог затухать шок. **ADR-127:** `life_status` добавлен — без него decay handler не мог проверить смерть → реинкарнация.
- **`NPCState.relationship_cache`** (`models/npc_state.py`): Dict — Local Social Projection Layer (S69). Эфемерный read-кэш социальных весов для текущего тика. Заполняется на начале тика из `RelationshipStore` через `npc_tick_pipeline`. Масштаб хранения: 0-100. Потребители нормализуют 0-100 → 0-1 на границе чтения. **ADR-121:** Персистенция внутри `NPCState` ЗАПРЕЩЕНА. SSOT = `RelationshipStore`. Формат: вложенный `{"target_id": {"fear": 50.0, "trust": 20.0}}`. **S69:** Кэш расширен с Star Schema (`player`-only) до Partial Social Graph (`player` + `nearby_npcs`). Асимметрия восприятия (наличие A в кэше B не гарантирует наличие B в кэше A) является архитектурной фичой (The Fool).

🚫 **КАУЗАЛЬНЫЕ ЗАПРЕТЫ (Контракт §4.2):**
- ❌ **Domain Leakage (Rule 9):** `CombatSubscriber` пишет ТОЛЬКО `PhysiologyPayload`. Прямая генерация эмоций из боя запрещена. Эмоции рождаются позже из `shock_impulse`.
- ❌ **Rule X Violation (Rule 26, ADR-101):** `BehaviorManifestationService` читает эмоции (psyche.fear/stress) вместо физиологии (body_state.pain/blood_loss/shock_impulse) — нарушение Правила X (CAUSAL_CONTRACT §7). Моторные следы вычисляются ТОЛЬКО из тела.
- ❌ **body_state Serialization Gap (Rule 27, ADR-100):** `write_to_legacy` / `from_legacy` без сериализации `body_state` — физиология теряется между тиками. Обязательная запись/чтение `body_state` в оба метода.
- ❌ **Shock Immortality (Rule 28, ADR-109):** `shock_impulse` без decay в `PhysiologyDecayHandler` = перманентный шок. Обязателен `SHOCK_DECAY_LAMBDA` и передача `shock_impulse` в `NPCStateSnapshot`.
- ❌ **Shock Delta Block (Rule 29, ADR-109):** `StateApplicator` проверяет `shock_impulse > 0.0` вместо `!= 0.0` — блокирует отрицательные дельты decay.
- ❌ **HP Death (Rule 38, ADR-123):** `hp <= 0` как источник смерти запрещён. Единственный владелец — `evaluate_vital_state()`. `combat_math.apply_damage` — мёртвый код.
- ❌ **Shock Death (Rule 39, ADR-123):** `shock_impulse` как источник смерти запрещён. Шок — сигнал, не процесс. Убивает только кровопотеря (переходно).
- ❌ **Phantom Ontology (Rule 40, ADR-123):** `brain_integrity`, `heart_function`, `respiration` в body_state запрещены без причинного источника. ImpactEngine пока не производит повреждения органов.
- ❌ **Dead Double Truth (Rule 41, ADR-123):** Запись `"dead"` в `body_state["statuses"]` запрещена. `body_state["life_status"]` — единственная истина.
- ❌ **String Flag Logic (Rule 42, ADR-123):** Чтение `"bleeding"` из `InjuryDTO.critical_effects` как источник логики в InjuryProcessor запрещено. Bleeding rate выводится из свойств раны: `structural_damage * zone_rate * damage_type_modifier`.
- ❌ **Broken Recovery Path (Rule 52, ADR-128):** LifeEngine `_load_npcs()` при cache miss без чтения SQLite (`persistence.load_npc_runtime()`) — runtime state (injuries, blood_loss, affective_load) теряется после TTL/LRU eviction. Обязательна трёхуровневая иерархия: RAM → SQLite → static config.
- ❌ **Empty vs None Ambiguity (Rule 53, ADR-128):** `load_npc_runtime()` возвращает `[]` — нельзя отличить пустую кампанию от отсутствующей. Проверка `if runtime_npcs:` неправильная (пустая кампания = fallback в static = реинкарнация NPC). Только `if runtime_npcs is not None:`.
- ❌ **Player Body State Serialization Gap (Rule 54, ADR-128):** `PlayerAvatarService._state_to_dict()` без `body_state`, `affective_load`, `perceptual_kernel` — player injuries теряются при каждой загрузке. AvatarService сериализует wounds/conditions (legacy identity layer), но игнорирует body_state (runtime simulation truth).
- ❌ **Player Body State Hydration Gap (Rule 55, ADR-128):** `PlayerAvatarService._state_from_dict()` без `body_state`/`affective_load`/`perceptual_kernel` — аватар сбрасывается в NEUTRAL/0.0 при каждой загрузке. Обязательное восстановление: `body_state=dict(data.get("body_state", {}))`, `affective_load=float(data.get("affective_load", 0.0))`, `perceptual_kernel=_pk_from_dict(data.get("perceptual_kernel", {}))`.
- ❌ **Dual Injury Ontology (Rule 56, ADR-128):** wounds/conditions (legacy identity layer) ≠ body_state.injuries (runtime simulation truth). body_state = SSOT. wounds/conditions = legacy projection (оставлены для совместимости, не источник истины). Запрещено читать wounds как источник физиологического состояния.
- ❌ **Player Action Without Life Status Check (Rule 59, ADR-131):** Обработка player action в `game_loop.run_turn()` без проверки `_avatar_state.body_state["life_status"]` запрещена. Мёртвый игрок не может действовать. Action Eligibility Gate стоит ДО `lock_for_tick`.
- ❌ **Static Player Combat Snapshot (Rule 60, ADR-132):** `_make_player_snapshot()` без чтения `player_dict.body_state` из `ctx.all_npcs_raw` запрещена. Возврат захардкоженного бессмертного снапшота (hp=100, pain=0) = нарушение симметрии физики симуляции.
- ❌ **DM Narration Without Life Status (Rule 62, ADR-140):** DM narration без проверки `player_state.life_status` запрещена. DM описывающий мёртвого игрока как живого = каузальный обман.
- ❌ **avatar_to_prompt Without life_status (Rule 65, ADR-140):** `avatar_to_prompt()` без поля `life_status` запрещён. DM слеп к смерти без этого поля в pdata.
- ❌ **Death Guard Without DM Call (Rule 66, ADR-140):** Death Guard без вызова DM (возврат хардкод-строки) запрещён. DM обязан интерпретировать смерть как нарративное событие. Fallback только при Exception.

---

## 6. МУТАЦИЯ И ЭМОЦИИ (State Mutation & Affective Integration)
**Поток:** Все изменения → Буфер → Агрегация → Интеграл Аффекта → Эмоция.

**Актуальные DTO:**
- **`DeltaDomain`** (`models/state_delta.py`): `PHYSIOLOGY`, `EMOTION`, `SOCIAL`, `PERCEPTION`, `IDENTITY`, `SPATIAL`.
- **`PerceptionPayload`** (`models/delta_payloads.py`): `threat_gradient_delta`, `uncertainty_delta`, `anomaly_score_delta`. Обновляет `PerceptualKernel`. **ADR-122:** Также генерируется `PhysiologyDecayHandler` для decay угрозы/неопределённости (emergency bandage до реализации Gen 3 `perceive_world()`).
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
- **`PlayerPerceptionDTO`** (`domain/snapshot.py`): Контейнер наблюдений игрока (Фаза 9). Содержит `embodied_traces` (List: `npc_id`, `is_frozen`, `is_shaking`, `locomotion_instability`, `micro_pause_density`, `action_interruption`), `peripheral_cues` (List: `npc_id`, `cue_type`, `hover_text`), `atmosphere_key` (str | None: ATMOSPHERE_THICK_TENSION / ATMOSPHERE_UNEASY), `atmosphere_intensity` (float 0-1). **ADR-112:** Проецируется ТОЛЬКО из `body_state` (pain/blood_loss/shock_impulse/fatigue). Чтение `stress_delta`/`psyche_state` ЗАПРЕЩЕНО (Semantic Inflation). Атмосфера из доли NPC с моторными симптомами. Cue keys: TENSE_POSTURE, SWAYING, UNEVEN_STANCE, ABRUPT_STOP, FREQUENT_PAUSES, WINCING, HOLDING_SIDE, BLEEDING, STAGGERED.
- **`EmbodiedTraceDTO`** (`domain/embodied_trace.py`): Наблюдаемые моторные и физические паттерны NPC. Поля: `npc_id`, `locomotion_instability` (0-1, дрожь/пошатывание от pain>10/shock>0.3), `posture_rigidity` (0-1, замер от pain>20/shock>0.5), `gaze_break_rate` (0-1), `action_interruption` (0-1, прерванное действие от shock>0.5), `micro_pause_density` (0-1, микро-остановки от blood_loss>0.05/fatigue>30), `is_frozen`, `is_shaking`. **ADR-112:** Вычисляется в `BehaviorManifestationService` ТОЛЬКО из `body_state` (Правило X). Чтение `stress_delta`/`psyche_state` ЗАПРЕЩЕНО (Semantic Inflation — все NPC дрожали одинаково).
- **`PerceivedEntity`** (Frontend `game_screen.py`): Доменная модель рендерера. Содержит `is_frozen`, `is_shaking`, `instability` (моторные следы), `perception_cues` (наблюдения для тултипов). Маппится из `PlayerPerceptionDTO` по `npc_id`.
- **`GameActionResponse`** (`frontend/api_client.py`): `dm_response`, `npc_reactions`, `world_changes`, `world_snapshot`, **`will_conflict_data`** (dict | None, проброс ADR-041/068).
- **`player_dict` (в all_npcs_raw)**: Обязан содержать инъецированные `body_state` (dict: pain, blood_loss, consciousness, **injuries**, shock_impulse) и `psyche` (dict: stress, fear, willpower) для корректной работы `AvatarPresentationAssembler` (ADR-068). **ADR-128:** `body_state` теперь переживает save/load через `PlayerAvatarService` — injuries, blood_loss, pain, shock_impulse персистируются между сессиями.
- **`PlayerAvatarService._state_to_dict()` / `_state_from_dict()`** (`services/player_avatar_service.py`): Сериализация/десериализация NPCState аватара. **ADR-128:** Обязательные поля: `body_state` (dict — injuries, blood_loss, pain, shock_impulse, fatigue, consciousness, statuses), `affective_load` (float), `perceptual_kernel` (dict — 10 полей PerceptualKernel, через `_pk_from_dict`). Без этого аватар теряет физиологию и аффект при каждой загрузке. Legacy-поля `wounds` и `conditions` сохранены для совместимости, но НЕ являются источником истины (body_state = SSOT).
- **`PipelineContext`** (`models/pipeline_context.py`): Строготипизированный контекст пайплайна. **S57:** Добавлено поле `player_perception` (Any, default=None) — Фаза 9: `embodied_traces`, `peripheral_cues`. Запись из `tick_orchestrator.py:712`, чтение DM-агентом.
- **`spatial_obstacles`** (dict внутри `scene_state`): Препятствия и мебель из editor JSON. **ADR-102:** Добавлено поле `type` (str: "bar", "table", "chair", "decoration" и т.д.) — пробрасывается из editor JSON через `scene_state_manager._build_spatial_data()` на фронтенд для рендера спрайтов через `sprite_resolver.py`. Ранее фронтенд получал заглушки-прямоугольники.
- **`scene_state`** (dict): Состояние локации. **ADR-102:** Добавлено поле `campaign_id` (str) — инжектируется в `get_scene_state()` для работы `SpatialService.build_for_location()`. Без этого SpatialService не может найти editor JSON. **ADR-129:** Type contract enforcement — `scene_state` ВСЕГДА dict. `normalize_scene_state()` в `spatial_runtime.py` гарантирует: list/float/None → пустой dict + `[SCENE_CONTRACT]` warning. `isinstance(scene, dict)` guard в `get_scene_state` и `get_scene_state_uncached` — reject non-dict на выходе из persistence. CEI-2 и CEI-1 используют `is_blocked_by_wall` (только стены), НЕ `is_movement_blocked` (стены+мебель) — мебель не блокирует макро-навигацию.
- **`VerbalizationContext`** (`services/verbalization/verbalization_context.py`): Контекст для LLM-вербализации NPC. **S57:** Добавлено поле `physical_state` (str, default="unharmed") — GAP5 FIX: Витализм, боль и шок перекрывают HP. Заполняется из `StateInterpreter.interpret()`. **S60:** `intent_target` получил дефолт `= None` (ADR-107 — безопасность field order). Дефолт `physical_state` заменён с `"невредим"` на `"unharmed"` (L10n-safe). **S65 (Инвариант 2):** Добавлены поля `is_moving: bool = False` и `movement_intent: str = ""` — LLM не может галлюцинировать движение без подтверждения от MovementEngine. Вычисляется в `npc_tick_pipeline.py` из intent (APPROACH/FLEE/RETREAT/FOLLOW/PATROL) + `can_move`.
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
- ❌ **Semantic Inflation in Manifestation (Rule 28, ADR-112):** `BehaviorManifestationService` и `PhenomenologyProjectionService` читают `stress_delta`/`psyche_state` для моторных искажений и атмосферы. ЗАПРЕЩЕНО. Только `body_state` (pain/shock_impulse/blood_loss/fatigue). Чтение эмоций = все NPC дрожат одинаково.
- ❌ **Fake Narrative Fallback (Rule 29, ADR-113):** При permanent failure LLM возвращать фейковый нарратив ("Твоё сознание мутнеет...") ЗАПРЕЩЕНО. Это каузальное мошенничество (§ENIGMA-001). Допускается только честное системное сообщение `[СИСТЕМА: LLM сервер недоступен]`. Retry + partial recovery (>20 chars) — разрешены.
- ❌ **Missing Role-Based Aliases (Rule 30, ADR-114):** `graph_compiler.py` ОБЯЗАН инжектить role-based legacy aliases (`bed→canonical`, `bar_area→canonical`, `main_hall→canonical`) в `alias_map`. Без этого NPC schedule с legacy-именами получает "node not found" и замирает.
- ❌ **Narrative Movement Hallucination (Rule 34, ADR-119):** LLM описывает движение NPC без подтверждения от MovementEngine — каузальный обман (Инвариант 2). DM контракт ОБЯЗАН содержать либо `npc_movement_summary`, либо явный запрет на описание перемещений.
- ❌ **Pre-Bus Failure Silence (Rule 35, ADR-120):** `logger.debug` для крахов аффективного decay и `print()` для Phase 8 крахов — ЗАПРЕЩЕНЫ. Только `logger.warning` со структурированными тегами `[PIPELINE][CRITICAL]`, `[PHASE8_CRASH]`, `[AFFECT_DECAY]`. CDS должен видеть пред-шинные отказы через `pattern_registry.py` паттерны.
- ❌ **DOUBLE TRUTH in Relationship Cache (Rule 36, ADR-121):** Персистенция `relationship_cache` внутри `NPCState` ЗАПРЕЩЕНА. SSOT = `RelationshipStore`. Плоский формат `{"fear": 0.5}` ЗАПРЕЩЁН — только вложенный `{"target_id": {"fear": 50.0}}` (масштаб 0-100, нормализация к 0-1 на границе потребителя).
- ❌ **Leaky Integrator for Affect (Rule 84, ADR-138):** Использование интегратора с утечкой (`load + incoming - recovery`) для `affective_load` ЗАПРЕЩЕНО. Только Асимметричный Аттрактор (Гистерезис): `new_load = current_load + (target_load - current_load) * adaptation_rate`. `target_load` — производная от активных причин.
- ❌ **Perpetual Threat (Rule 85/38, ADR-138):** Хранение `threat_gradient` / `uncertainty` / `anomaly_score` навсегда без idle-decay в Фазе 0.5 ЗАПРЕЩЕНО. Угроза распадается во времени. Целевая архитектура (Gen 3): `perceive_world()` — recompute из observable world state.
- ❌ **Affective Boot (Rule 86, ADR-138):** Подтягивание `affective_load` до порога `emotion_tag` ЗАПРЕЩЕНО. Положительная обратная связь порождает вечный двигатель страха. Интеграл (L0) и Рефлекс (L2) разделены.

**CDS Diagnostic DTOs (Инвариант 3):**
- **`TickHealthReport`** (`diagnostics/health_checkers/tick_health.py`): Счётчики здоровья тик-пайплайна. **S65:** Добавлены 5 полей пред-шинных отказов: `pipeline_critical_count: int`, `causality_crash_count: int`, `phase8_crash_count: int`, `tick_orch_error_count: int`, `affect_decay_fail_count: int`. Парсятся из логов через `pattern_registry.py` паттерны: `pipeline_critical`, `causality_crash`, `phase8_crash`, `tick_orch_error`, `affect_decay_fail`.
- **`DNASnapshot`** (`diagnostics/dna_metrics.py`): Снимок DNA-метрик. **S65:** Добавлены поля `prebus_failures: int = 0` (сумма 4-х пред-шинных отказов) и `affect_decay_fails: int = 0`. PFI (Pre-Bus Failure Index) = `prebus_failures / total_ticks * 100`.
- **`DNADelta`** (`diagnostics/dna_metrics.py`): Дельта DNA между сессиями. **S65:** Добавлено поле `PFI: Optional[float] = None`.

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
- `test_affective_load_recomputation_from_causes` (Rule 37, ADR-122)
- `test_living_npc_inertia_preserved` (L1 Formula)
- `test_movement_processed_once` (Rule 18, ADR-066)
- `test_target_local_xy_propagated_through_pipeline` (Rule 19, ADR-069)
- `test_enrichment_does_not_overwrite_pipeline_position` (Rule 20, ADR-072)
- `test_bridge_includes_active_traversals` (Rule 21, ADR-071)
- `test_fast_path_emotional_vector_injection` (ADR-088)
- `test_campaign_id_not_replaced_by_location_id` (ADR-089)
- `test_adjacency_inference_without_passages` (ADR-073)
- `test_perceptual_kernel_survives_legacy_roundtrip` (Rule 31, ADR-115)
- `test_no_local_scope_variable_leakage` (Rule 32, ADR-116)
- `test_runtime_overlay_preserves_computed_state` (Rule 33, ADR-118)
- `test_dm_contract_prohibits_movement_hallucination` (Rule 34, ADR-119)
- `test_cds_parses_prebus_failures` (Rule 35, ADR-120)
- `test_relationship_cache_not_persisted_in_legacy` (Rule 36, ADR-121)
- `test_perception_decay_reduces_threat` (Rule 38, ADR-122)
- `test_sqlite_readback_preserves_injuries` (Rule 52, ADR-128)
- `test_empty_campaign_not_confused_with_missing` (Rule 53, ADR-128)
- `test_player_body_state_survives_save_load` (Rule 54/55, ADR-128) ✔ S74
- `test_player_affective_load_survives_save_load` (Rule 55, ADR-128) ✔ (включен в test_player_body_state_survives_save_load)
- `test_player_perceptual_kernel_survives_save_load` (Rule 55, ADR-128) ✔ (включен в test_player_body_state_survives_save_load)
- `test_wounds_not_used_as_physiology_source` (Rule 56, ADR-128) ✔ S74
- `test_movement_lock_blocks_schedule_on_active_traversal` (Rule 57, ADR-130) ✔ S74
- `test_target_id_payload_fallback_prevents_uninvited_approach` (Rule 58, ADR-130) ✔ S74
- `test_drf_bus_instance_level_not_default_factory` (Rule 73, ADR-134)
- `test_drf_no_monkey_patch_injection` (Rule 74, ADR-134)
- `test_drf_idle_path_has_drain` (Rule 75, ADR-134)
- `test_drf_pipeline_receives_execution_context_not_bare_bus` (Rule 76, ADR-136)
- `test_drf_claim_inherits_npc_id_from_context` (ADR-136)
- `test_drf_scoring_overlay_applied_to_player_path` (Rule 77, ADR-135)
- `test_drf_scoring_additive_not_clamp` (Rule 80, ADR-135)
- `test_drf_same_bus_id_across_execute_and_finalize` (ADR-134)
- `test_threatened_npc_no_routine_intent` (ДОЛГ 4.3, ADR-O-137)
- `test_paralyzed_npc_only_survival` (ADR-O-137)
- `test_calm_npc_all_domains_viable` (ADR-O-137)
- `test_threat_exact_threshold` (ADR-O-137)
- `test_schedule_intent_is_routine` (ADR-O-137)
- `test_flee_is_survival` (ADR-O-137)
- `test_avatar_to_prompt_includes_life_status_alive` (Rule 65, ADR-140)
- `test_avatar_to_prompt_includes_life_status_dead` (Rule 65, ADR-140)
- `test_avatar_to_prompt_life_status_fallback_when_no_body_state` (Rule 65, ADR-140)
- `test_dm_contract_dead_player_gets_death_block` (Rule 62, ADR-140)
- `test_dm_contract_alive_player_no_death_block` (Rule 62, ADR-140)
- `test_dm_death_block_only_from_player_state_not_computed` (Rule 62, ADR-140)