# ADR-O-435-R5.1 — AVATAR AGENCY & BODY ACTION ARBITRATION

**Основание:** ADR-O-435-R1–R5 (заключение Мастера: вердикт B — ограниченный архитектурный этап R5.1)
**Статус:** ARCHITECTURE DESIGN — read-only проектирование, без изменений кода
**Сессия:** S399 (Ветвь Б «Мир и платформа»)
**Базлайн:** V.0.5.4.5.0_Спать_хочу, HEAD 755a1c27
**Связанные законы:** §ENIGMA-001 (Приоритет причинной глубины), §ENIGMA-002 (Two-Domain Rule), §10.2 (Тело — Gate of Perception), ADR-O-344 (WorldTick Temporal Ownership), ADR-O-407 (Player Turn Commitment Time Gate), INV-PLAYER-AUTHORSHIP, ADR-O-310 (Windup Execution Gate), ADR-O-410 (Interrupt Reasons), ADR-O-139 (Body = L1, drives_runtime Single Write Authority)

---

## §1. EXECUTIVE VERDICT

**Классификация выводов:** `VERIFIED` (доказано кодом), `PARTIALLY VERIFIED` (часть доказана, часть требует домысливания), `PROPOSED` (новое проектирование без кодовой опоры), `UNVERIFIED` (гипотеза), `REJECTED` (опровергнуто кодом).

### 1.1. Постановка

R5 установил два фундаментальных разрыва:

1. **Avatar Initiative** — Avatar не имеет собственного механизма формирования намерений. WillpowerGate (`will.py:135-215`) — реактивный контур сопротивления давлению Player, не источник автономной инициативы. DecisionHub (`decision_hub.py:395`) заблокирован для Avatar инвариантом INV-PLAYER-AUTHORSHIP (`decision_hub.py:327`).
2. **Body Action Arbitration** — нет явного арбитража двух независимых намерений через одно тело. Неявная сериализация через порядок фаз TickOrchestrator работает, пока Player = единственный автор действий Avatar. При появлении Avatar Initiative она ломается.

### 1.2. Вердикт

**R5.1 = B (готов к отдельному утверждению перед реализацией).**

Архитектурный контракт замкнут:
- Avatar Initiative спроектирована как **отдельный движок `AvatarInitiativeEngine`** (не DecisionHub, не WillpowerGate) — `PROPOSED`.
- Body Arbitration спроектирован как **новый компонент `BodyArbiter`** на границе Фазы 5/6 — `PROPOSED`.
- Существующие инварианты сохранены: INV-PLAYER-AUTHORSHIP (`VERIFIED`), ADR-O-344 единственность TickOrchestrator (`VERIFIED`), ADR-O-407 time-gate (`VERIFIED`), ADR-O-310 Windup FSM (`VERIFIED`), §10.2 Body как Gate of Perception (`VERIFIED`).
- Контракт `AvatarIntention` добавлен как **параллельный тип**, не унификация существующих `CommunicationIntent / MovementIntent / PlayerAction / DecisionResult` (`PROPOSED`, обоснование §ENIGMA-002 Two-Domain Rule).
- Расширение `ControlSource` enum одним значением `AVATAR_INITIATIVE` (`PROPOSED`), без изменения существующих `PLAYER_INPUT / NPC_DECISION / SCRIPTED_SYSTEM / COMBAT_CONTROLLER`.

### 1.3. Что НЕ утверждается этим документом

- Не утверждается production-реализация. Код не меняется. Дождаться вердикта Мастера.
- Не предписывается вид UI для индикации Avatar-инициативы — это отдельный трек (прецедент ADR-O-435 standalone UI).
- Не определяется характер, ценности, биография, желания конкретного Avatar — это геймдизайнерская прерогатива (§12 спецификации R5.1).
- Не проектируется механика воскрешения / переселения — открытый вопрос Геймдизайнеру (§16-Q3).
- Не унифицируются существующие намерения в единый `Intention` тип — это нарушило бы §ENIGMA-002 без доказательства двумя доменами.

### 1.4. Принципиальная формула

> Сознания независимы. Намерения независимы. Тело общее. Мир един.
>
> Player → PlayerIntention → BodyArbiter → Execution → World
> Avatar → AvatarIntention → BodyArbiter → Execution → World
> Body = NPCState(npc_id="player"), единственный физический исполнитель
> World = TickOrchestrator.execute(), единственный владелец времени (ADR-O-344)

---

## §2. АРХЕОЛОГИЯ СУЩЕСТВУЮЩЕГО КОНТУРА

### 2.1. Идентичности (VERIFIED)

Три идентичности, сегодня неразличимые на уровне кода:

| Слой | Идентичность | Хранилище | Где хардкод |
|---|---|---|---|
| Player (сознание игрока) | `PlayerSession.player_name` | `schemas.py:PlayerSession` | `interventions.py:14` `source="player"` (factory) |
| Avatar (сознание персонажа) | `CharacterProfile.character_id` (приравнен к `player_name`) | `character.py:CharacterProfile` | `player_avatar_service.py:230` `CharacterProfile(character_id=player_name)` (fallback) |
| Body (физическое тело) | `NPCState.npc_id = "player"` | `npc_state.py` | `turn_pipeline.py:229-230` `_avatar_dict["npc_id"]="player"; _avatar_dict["id"]="player"` |

**Value coupling (VERIFIED):** `player_avatar_service.py:138` — `if data.get("state", {}).get("npc_id") != player_name: return None`. Имя игрока = идентификатор тела. Нарушение §ENIGMA-002 (не доказано, что Player и Avatar — одна сущность).

**Миграции (PARTIALLY VERIFIED):** `player_avatar_service.py:281` `CharacterProfile(character_id=sheet.name)` — миграция корректно использует `sheet.name`, не `player_name`. Это означает, что в миграционном пути разделение существует, но в runtime fallback оно утрачено.

### 2.2. Физическое тело (VERIFIED)

`NPCState` (npc_state.py:388-1359) — единая структура для всех NPC, включая Avatar. Поля Avatar = Body:

- `drives_base: Dict[str, float]` — L1 seed, frozen после spawn (control, significance, fear, desire)
- `drives_runtime: Dict[str, float]` — ADR-139 Single Write Authority, mutation runtime
- `temporary_drives: List[TemporaryDrive]`
- `will_state: WillState = WillState.FREE`
- `pressure_resistance: float = 0.0` (clamp 0-100)
- `identity_integrity: float = 1.0` (clamp 0-1)
- `behavior_mask: BehaviorMaskState` (R6.2 — внешний паттерн поверх will_state)
- `trauma_markers: Set[str]`
- `life_project: str = "survival"`, `life_project_state` (FSM ACTIVE/COLLAPSING/LOST/SEARCHING/COMMITTED)
- `affective_imprints: Tuple[AffectiveImprint, ...]`
- `current_role: str`
- `intent: Intent`, `intent_target`, `intent_formed_at`, `intent_duration`, `intent_progress_ticks`, `last_intent_change` (intent persistence между тиками — npc_state.py:854-859, 1025-1030)

`ADR-WRITE-GUARD`: приватные поля имеют per-module write authority (npc_state.py:686-699 — explicit registry). Запись из неразрешённого модуля → `ArchitecturalViolationError`.

### 2.3. Existing Avatar resistance path (VERIFIED)

Контур `Phase 1 → WillpowerGate → publish_player_intent / WILL_CONFLICT` (input.py, will.py):

```text
InterventionEvent(source="player", payload={text, player_name})
    ↓
Phase 1 (input.py:_phase_1_input)
    ↓
player_dict = next(n for n in ctx.all_npcs_raw if n.get("npc_id")=="player")  # value coupling
    ↓
resolve_intent_pressure(intent) → IntentPressureProfile  # SSOT давления
    ↓
scan_affective_resonance(intent, None, None, imprints) → resonance
    ↓
distort_pressure(pressure, resonance, psyche) → distorted_pressure
    ↓
compute_willpower(distorted_pressure, psyche) → WillResponseDTO(state, resistance, fear_delta,
                                                                  stress_delta, identity_damage,
                                                                  counter_offer, embodied_vector,
                                                                  social_signal, crowd_threat)
    ↓
WillState routing:
  COMPLY/RELUCTANT/CONDITIONED → publish_player_intent(ctx, intent)  # Avatar подчиняется
                                 + DeltaBuffer(IDENTITY: identity_integrity_delta=-damage)
                                 + DeltaBuffer(WILL: WillConflictPayload)
  RESIST/REFUSE/BROKEN/PANICKED/DISSOCIATING → блокировка действия
                                                + publish WILL_CONFLICT event
                                                + shared_context[counter_offer_text]
```

**WillpowerGate = реактивное сопротивление давлению Player, не автономная инициатива Avatar.** Это контур типа 2 (filter/gate), не контур типа 1 (generator). `_generate_counter_offer` (will.py:241-297) создаёт `IntentDTO`, но он **не доходит** до `CommunicationIntent` — попадает только в `shared_context` и фронтенд (`game_screen.py:1995-2034` Resistance Medium).

### 2.4. NPC Decision Pipeline (VERIFIED)

NPC путь для сравнения с тем, чего у Avatar нет:

```text
Phase 4: Pre-Decision → TopicExtractor → npc_topics[npc_id]
    ↓
Phase 5: Decision → assemble_preloaded_data(ctx, alive_npcs)
    ↓
DecisionHub.compute(state, personality, event, effective_drives, scene_state,
                    opportunity_ctx, identity, eco_modifiers, social_modifiers,
                    reputation_modifiers, drive_modifiers, contract_modifiers,
                    npc_memory_modifiers, epistemic_modifiers, reflex_constraints,
                    topic, decision_ctx, spatial_query, all_npc_ids,
                    pending_response_target, relationship_store, campaign_id,
                    epistemic_context, causal_modifiers, causal_addressee,
                    cognition_modifiers) → DecisionResult(intent, intent_target, score, ...)
    ↓
Vital State Guard: evaluate_vital_state(_body) → если dead/unconscious: IDLE, score=0
    ↓
NpcTickPipeline: _route_intent_by_type → CommunicationIntent / MovementIntent
    ↓
Phase 6: IntentEventAdapter.to_event(intent) → EventDTO.create(source=intent.speaker)
    ↓
Phase 7: Windup Execution Gate (ADR-O-310) — attack/steal → ActionWindup FSM
    ↓
Phase 8: Layered Reduction (drain + handle)
    ↓
Phase 9: Integration
    ↓
Phase 10: Persistence (atomic commit)
```

**INV-PLAYER-AUTHORSHIP (VERIFIED):** `decision_hub.py:326-331`:
```python
from app.domain.control_source import ControlSource, resolve_control_source
if resolve_control_source(npc_id) is not ControlSource.NPC_DECISION:
    raise ArchitecturalViolationError(
        f"[INV-PLAYER-AUTHORSHIP] speaker={npc_id!r}: авторский "
        f"{resolve_control_source(npc_id).value}), intent={intent_value!r} отклонён"
    )
```

Дополнительные уровни защиты (VERIFIED):
- `npc_tick_pipeline.py:1084,1089` — attack-factory (уровень 2)
- `npc_tick_pipeline.py:1240,1253` — детектор на границе (уровень 3)

`ControlSource` enum (control_source.py): `PLAYER_INPUT / NPC_DECISION / SCRIPTED_SYSTEM / COMBAT_CONTROLLER`. `_PLAYER_ACTORS = frozenset({"player"})` — единственная точка различения Player. `resolve_control_source(actor_id) → PLAYER_INPUT if "player" else NPC_DECISION`. **Нет значения AVATAR_INITIATIVE.**

### 2.5. Коммуникационный контур и Provenance (VERIFIED)

`IntentEventAdapter._INTENT_EVENT_MAP` (intent_event_adapter.py) — детерминированный мост `talk→NPC_SPOKE`, `attack→ACTOR_ATTACKS`, `trade→TRADE`, etc. Единственная легальная точка `CommunicationIntent → EventDTO` (Устав §3.3).

`EventDTO.create(source=intent.speaker)` — `speaker` становится `EventDTO.source`. Это означает, что **подписчики видят говорящего как source**, не владельца тела.

`ClaimEventSubscriber.on_npc_spoke` (claim_event_subscriber.py): `speaker_id = event.source`. Маппинг `intent_type → Proposition`:
- `accuse → Proposition(subject_id=target_id, predicate=STOLE, object_id="unknown")`
- `praise → Proposition(subject_id=target_id, predicate=HELPED)`
- `intimidate/attack → Proposition(subject_id=speaker_id, predicate=ATTACKED, object_id=target_id)`

`ClaimEventSubscriber.on_player_spoke`: `speaker = getattr(event, "source", "player")` — fallback на литерал `"player"` (claim_event_subscriber.py:108).

`dialogue_memory_subscriber`: `speaker = payload.npc_id or event.source`, `listener = payload.target_id (default "player")`, `affected_npcs = {speaker, listener}`, **skip if npc_id in ("all", "player")** — Player не пишет в narrative_cache.

### 2.6. Epistemic Store (VERIFIED)

`EpistemicStore` keyed by `(agent_id, proposition)` — `record.agent_id` идентифицирует субъекта-владельца убеждения. `BeliefRevisionEngine.revise(listener_id, claim, ...)` создаёт `EpistemicRecord(agent_id=listener_id)` — агент-наблюдатель владеет убеждением. `EpistemicContextResolver.resolve(agent_id)` фильтрует по `agent_id`.

**Avatar сегодня не имеет agent_id в EpistemicStore** — Player владеет убеждениями как `agent_id="player"`. Двойной истины нет (один store, разные agent_id), но добавление Avatar потребует отдельного `agent_id` значения.

### 2.7. Time & Body Action Execution (VERIFIED)

**TickOrchestrator (tick_orchestrator.py:489 `execute`)** — единственный владелец времени (ADR-O-344). Фазовый порядок (tick_orchestrator.py:1033-1117):

| Фаза | Что делает | Кто мутирует Body |
|---|---|---|
| 0 | Simulation (LifeEngine) | physiology, position |
| 0.5 | Time-Driven Decay | drives decay, affordances |
| 0.6 | Sleep Lifecycle | sleep state |
| 0.75 | Traversal Lifecycle | movement execution |
| 1 | NPIC Normalize | — |
| 1.1 | Input Merge | InterventionEvent intake |
| 1 (input) | WillpowerGate (для player intent) | Avatar resistance (state mutation) |
| 2 | EventBus Primary | spatial events publication |
| 3 | Memory Phase | NPC memory writes |
| 4 | Pre-Decision (TopicExtractor) | — |
| 5 | Decision (NPC) | NPC intent formation, movement intents |
| 6 | Post-Decision (IntentEventAdapter, WindupWriteGate) | windup registry mutation |
| 7 | Windup Resolution (Execution Gate) | terminal commitment mutation |
| 8 | Layered Reduction (drain + handle) | event subscription effects |
| 9 | Integration (CFRM, Belief Crystallization) | belief, snapshot |
| 9.1 | Affective Pipeline | affective integration |
| 10 | Persistence (atomic commit) | WORLD TRUTH |

**Aтомарность сегодня (VERIFIED через implicit serialization):**
- TickOrchestrator.execute() — single-threaded вызов
- Phase 1 player intent мутирует Avatar state через WillpowerGate (state_applicator применяет дельты)
- Phase 5 NPC intent formation — DecisionHub.compute для каждого NPC
- Phase 7 windup execution — terminal transitions
- Phase 10 atomic commit — единая точка персистентности

**Что НЕ доказано неявной сериализацией:**
- Два намерения одного и того же Body, сформированные в разных фазах (Phase 1 Player + Phase 4 Avatar), могут быть физически несовместимы, но порядок фаз не даёт арбитража — он даёт только последовательность.
- `player_turn_in_flight` (game_loop.py:1179) останавливает idle_tick на время хода Player. Это НЕ arbitration — это time-gate. Внутри одного тика с Player input и Avatar initiative параллельно не существует сегодня.

### 2.8. Action Commitment FSM (VERIFIED)

`action_commitment.py`: статусы `PROPOSED / COMMITTED / EXECUTING / BLOCKED / COMPLETED / FAILED / INTERRUPTED / EXPIRED / CANCELLED`.

Допустимые переходы:
- `PROPOSED → {COMMITTED, CANCELLED}`
- `COMMITTED → {EXECUTING, BLOCKED, CANCELLED, EXPIRED, INTERRUPTED}`
- `EXECUTING → {COMPLETED, FAILED, BLOCKED, INTERRUPTED, EXPIRED, CANCELLED}`
- `BLOCKED → {EXECUTING, FAILED, EXPIRED, INTERRUPTED, CANCELLED}`
- Terminal: `COMPLETED / FAILED / INTERRUPTED / EXPIRED / CANCELLED` (без исходящих)

`build_commitment_id(tick, npc_id, action, ordinal)` — детерминированный идентификатор. `INTERRUPTED` требует `interrupt_reason`, `FAILED` требует `fail_reason` — нет причины = architectural violation.

`ActionWindup` (action_windup.py + ADR-O-310): `actor_id, action_type, started_tick, duration_ticks, status`. WindupRegistry персистится в `scene_state["windup_registry"]`. `WindupWriteGate` (post_decision.py:300) перехватывает `attack/steal` intents перед материализацией — создаёт windup с `PENDING` статусом, выполнение в Phase 7.

### 2.9. Player Turn Lifecycle (VERIFIED)

`game_loop.py`:
- `_player_turn_in_flight: set[str]` (ADR-O-407)
- `run_turn(req)`: `_player_turn_in_flight.add(req.campaign_id)` в `try`, очистка в `finally`
- `idle_tick(campaign_id)`: если `campaign_id in _player_turn_in_flight` → skip `execute()` (мир не тикает)
- NPC-NPC диалоги продолжаются через `TaskScheduler` в `run_turn` (ADR-O-313) — НЕ паузятся

`TaskScheduler` (task_scheduler.py):
- `_task_outbox` (worker→main thread drain, ADR-O-399)
- `_commitment_outbox` (terminal mirror, ADR-O-365 D-2)
- `ThreadPoolExecutor(max_workers=1)` (ADR-O-343 serialization)
- `execute_pending(scene_state, campaign_id)` → `drain_task_worker_outbox + drain_commitment_outbox`
- Worker only computes; observable effects в drain (main thread, deterministic)

### 2.10. Player Action Path (VERIFIED)

`PlayerAction` (player_action.py:24) → `InterventionEvent.from_player_action(action_text, player_name, tick)` → `InterventionEvent(source="player", payload={text, player_name, ...})` → Phase 1 input → `publish_player_intent` → `EventDTO.create(source="player", event_type=PLAYER_INTERACTS/PLAYER_ATTACKS/...)`.

`publish_player_intent` (input.py):
```python
_evt_map = {"attack": PLAYER_ATTACKS, "player_attacks": PLAYER_ATTACKS}
_resolved_type = _evt_map.get(_act, EventType.PLAYER_INTERACTS)
get_event_bus().publish(EventDTO.create(
    event_type=_resolved_type.value,
    source="player",  # HARDCODED
    payload={action, target, target_id, target_reference, semantic_action}
))
```

**Source = `"player"` — hardcoded literal.** Это означает, что подписчики не различают «Player сказал» и «Avatar сказал» — оба источника сегодня идентичны. NPC видят Avatar как Player через `event.source`.

### 2.11. CharacterFilter (VERIFIED)

`character_filter.py:CharacterFilter`:
- `THRESHOLD_ACCEPT=0.3, THRESHOLD_MODIFY=0.6, THRESHOLD_RESIST=0.9`
- `compute_resistance(profile, event_type, intensity) → FilterResult(outcome, resistance, action_modifier, erosion_applied, hesitation_tags, modified_description)`
- `outcome ∈ {ACCEPT, MODIFY, RESIST, REFUSE}` по `value_conflict × integrity_modifier`
- `integrity_modifier = 0.5 + 0.5 * profile.self_integrity` (eroded персонаж сопротивляется слабее)
- `CharacterProfile.resist_ticks` — история RESIST-действий, накапливающая эрозию (character.py:201-208)

`CharacterFilter` — это **фильтр действий игрока**, не источник Avatar-инициативы. Сегодня вызывается только из player-action pipeline.

### 2.12. Карта исполнения Body — сводная таблица

| Источник намерения | Точка входа | Что исполняет Body | Что видит мир |
|---|---|---|---|
| Player (через `run_turn` REST) | `Phase 1 Input` | `publish_player_intent` → `EventDTO(source="player")` | PLAYER_ATTACKS/PLAYER_INTERACTS event |
| Player (WillpowerGate resist) | `Phase 1 Input` | блок + counter_offer в shared_context | WILL_CONFLICT event (no body action) |
| NPC (через `DecisionHub`) | `Phase 5 Decision` | `DecisionResult.intent` → `StateApplicator` | NPC_SPOKE / ACTOR_ATTACKS / etc. |
| NPC (Windup) | `Phase 7 Windup` | `ActionWindup` completion → `IntentEventAdapter` | terminal events |
| NPC-NPC async (TaskScheduler) | `execute_pending` drain | `_process_tasks_async` → materializer | NPC_SPOKE events in drain |
| Combat Controller | `Phase 8 Subscriber` | `CombatSubscriber` → `ImpactEngine` | damage events |
| Traversal System | `Phase 0.75` | `process_traversals` | NPC_MOVED events |
| **Avatar (autonomous)** | **ОТСУТСТВУЕТ** | — | — |

**Главный вывод археологии:** Avatar как автономный субъект намерения **не существует в коде**. Существуют: реактивное сопротивление (WillpowerGate), фильтрация (CharacterFilter), тело (NPCState с `npc_id="player"`), профиль (CharacterProfile приравнен к player_name). Полноценного когнитивного контура «восприятие → интерпретация → желание → намерение → предложение» — нет.

---

## §3. AVATAR INITIATIVE CONTRACT

### 3.1. Архитектурный выбор (PROPOSED)

**Рекомендуемый вариант: BDI-подобная модель с гибридным переиспользованием существующих когнитивных механизмов ENIGMA.**

Альтернативы рассмотрены в §11. Здесь — контракт выбранного варианта.

**Принцип:** Avatar Initiative = отдельный движок `AvatarInitiativeEngine`, не использующий `DecisionHub.compute` (это нарушило бы INV-PLAYER-AUTHORSHIP), но переиспользующий:
- `DriveResolver.resolve_drives` — для effective drives (read-only projection)
- `EpistemicStore` и `EpistemicContextResolver` — для beliefs (с `agent_id="avatar:{character_id}"`)
- `MemoryManager` (npc_id="player") — для episodic memory (тело имеет одну память, но owner тегируется)
- `affective_integrator.integrate_affective_pressure` — для affect updates
- `BeliefCrystallizationEngine.crystallize` — для belief formation
- `scan_affective_resonance` / `distort_pressure` — для perception distortion

**Что НЕ переиспользуется:**
- `DecisionHub.compute` — заблокирован INV-PLAYER-AUTHORSHIP (`decision_hub.py:327`)
- `WillpowerGate.compute_willpower` — это реактивный контур сопротивления давлению, не генератор намерений. WillpowerGate остаётся в своей роли для player input, но не используется для Avatar Initiative.
- `CharacterFilter.compute_resistance` — это фильтр действий Player, не источник Avatar-инициативы.

### 3.2. Причинная диаграмма (PROPOSED)

```text
SUBJECTIVE STATE (NPCState + CharacterProfile)
    │
    │  drives_runtime, will_state, identity_integrity, trauma_markers,
    │  affective_imprints, life_project + life_project_state,
    │  values (ValueSet), self_integrity, social_constraints,
    │  behavior_mask
    ↓
PERCEPTION (Perceptual Kernel — read-only from scene_state)
    │
    │  PerceivedEntity[], affective_resonance scan,
    │  spatial_query, EventMemory reads
    ↓
INTERPRETATION (AffectiveIntegrator + EpistemicContextResolver)
    │
    │  distorted_pressure (если есть source давления),
    │  belief_context = resolve(agent_id="avatar:{character_id}"),
    │  memory_context = recall(npc_id="player", partner_id=*)
    ↓
DESIRE FORMATION (DesireSynthesizer)
    │
    │  desire_vector = f(drives, beliefs, memory, values, opportunities)
    │  desire = {target, kind, urgency, valence, addressee}
    │  НЕ ИСПОЛЬЗУЕТ пороги типа "if fear > 0.8: retreat"
    │  ИСПОЛЬЗУЕТ формулу: score = drive_weight × belief_alignment ×
    │                       opportunity_match × value_compat ×
    │                       (1 - satiation_inhibition)
    ↓
INTENTION FORMATION (IntentionSynthesizer)
    │
    │  candidates = generate_candidates(desire, scene_state, capabilities)
    │  intention = select(candidates, prior_commitments, life_project,
    │                     social_constraints, behavior_mask)
    │  intention = {kind, target, action_class, parameters, source_id}
    ↓
INTENTION PROPOSAL (Output)
    │
    │  AvatarIntention (новый контракт, §4) → BodyArbiter (§6)
    │  НЕ публикует EventDTO напрямую. НЕ вызывает publish_player_intent.
    │  НЕ мутирует NPCState. Только формирует и предлагает.
```

### 3.3. Контракт формирования желания (PROPOSED)

```python
@dataclass(frozen=True)
class AvatarDesire:
    """Желание = внутреннее влечение к состоянию, без обязательства действовать."""
    desire_id: str  # детерминированный: tick:character_id:target:kind:ordinal
    formed_at_tick: int
    source_id: str  # всегда character_id Avatar, не "player"
    target: Optional[str]  # npc_id / object_id / "player" / None
    kind: DesireKind  # AFFILIATE / AVOID / ACQUIRE / DEFEND / EXPLORE / EXPRESS / WITHDRAW
    urgency: float  # 0.0–1.0, вычисляется из drive × opportunity
    valence: float  # -1.0..1.0, approach vs avoidance
    addressee: Optional[str]  # кому адресовано (если социальное)
    drive_origin: Tuple[str, float]  # какой drive породил, с весом
    value_alignment: float  # 0.0–1.0, насколько совместимо с values
    satiation_level: float  # 0.0–1.0, насколько потребность уже удовлетворена
    # Запрещено: action_type, action_parameters — это уже намерение, не желание
```

**Формула score (детерминированная, без хардкод-порогов):**

```text
desire_score = drive_weight × belief_alignment × opportunity_match ×
               value_compat × (1 - satiation_inhibition) × behavior_mask_modifier
```

Где:
- `drive_weight` = `EffectiveDrives.get(drive_key)` из `DriveResolver.resolve_drives`
- `belief_alignment` = `EpistemicContextResolver.get_confidence_for_subject(agent_id, target)` для релевантной proposition
- `opportunity_match` = функция от `spatial_query` (расстояние, видимость) + `OpportunityContext` (если доступно)
- `value_compat` = `profile.values.conflict_score(value_set_for_kind)` (mirror of CharacterFilter logic, but for desire kind)
- `satiation_inhibition` = `1 - (current_satiation / max_satiation)` — если drive удовлетворён, желание слабее
- `behavior_mask_modifier` = `BehaviorMask` effect (R6.2 — внешний паттерн поверх will_state)

**Запрет (явный):** никаких `if fear > 0.8: retreat()`. Fear модулирует `drive_weight["fear"]` в формуле, не переключает поведение по порогу.

### 3.4. Контракт формирования намерения (PROPOSED)

```python
@dataclass(frozen=True)
class AvatarIntentionCandidate:
    """Кандидат на намерение — до отбора."""
    candidate_id: str
    desire_id: str  # какой desire породил
    action_class: ActionClass  # SPEAK / MOVE / INTERACT_OBJECT / DEFEND / FLEE / OBSERVE / REFUSE_PLAYER
    target: Optional[str]
    parameters: Dict[str, Any]  # специфика действия (не исполняемый контракт)
    feasibility: float  # 0.0–1.0, физическая допустимость
    commitment_cost: float  # оценка ресурса времени (ticks)
    conflicts_with: List[str]  # candidate_ids, с которыми несовместим
```

```python
@dataclass(frozen=True)
class AvatarIntention:
    """Сформированное намерение Avatar. Передаётся в BodyArbiter."""
    intention_id: str  # детерминированный: tick:character_id:ordinal
    formed_at_tick: int
    source_id: str  # character_id Avatar (НЕ "player")
    body_id: str  # "player" — тело, через которое исполняется
    desire_id: Optional[str]  # provenance к желанию
    action_class: ActionClass
    target: Optional[str]
    parameters: Dict[str, Any]
    priority: float  # 0.0–1.0
    supersedes: Optional[str]  # intention_id, который заменяет (если есть)
    # Семантика КЛАССА действий, не специфика исполнения.
    # "SPEAK" ≠ CommunicationIntent; CommunicationIntent — один из возможных
    #   materialisations SPEAK intention.
    # "MOVE" ≠ MovementIntent; MovementIntent — материализация.
```

**Классы действий (PROPOSED):**

```python
class ActionClass(str, Enum):
    SPEAK = "speak"          # речевое действие (→ CommunicationIntent при авторизации)
    MOVE = "move"            # двигательное (→ MovementIntent при авторизации)
    INTERACT_OBJECT = "interact_object"  # манипуляция объектом
    DEFEND = "defend"        # защитная реакция (на входящее воздействие)
    FLEE = "flee"            # избегание
    OBSERVE = "observe"      # наблюдение без действия
    REFUSE_PLAYER = "refuse_player"  # отказ выполнять команду Player
    SEEK_CONTACT = "seek_contact"  # инициатива общения (mirror NPC APPROACH)
    # Универсальность: каждый класс → разная материализация,
    # но контракт намерения един.
```

**Не объединять** `AvatarIntention` с `CommunicationIntent / MovementIntent / PlayerAction / DecisionResult`. Унификация нарушает §ENIGMA-002 (Two-Domain Rule): разные домены (speech, movement, player input, NPC decision) сегодня страдают от разных проблем; единый `Intention` примитив не доказан двумя доменами. Avatar Initiative — третий домен, и его контракт живёт отдельно.

### 3.5. Состояния намерения и переходы (PROPOSED)

```text
FORMED
   ↓ (AvatarInitiativeEngine emit)
PROPOSED
   ↓ (BodyArbiter receive)
CONFLICT_CHECK
   ↓
{AUTHORIZED, REJECTED, DEFERRED}
   ↓ (если AUTHORIZED)
EXECUTING
   ↓
{COMPLETED, FAILED, INTERRUPTED, EXPIRED}
```

Transition table (PROPOSED):

| From | To | Условие | Кто исполняет |
|---|---|---|---|
| FORMED | PROPOSED | желание отобрано как намерение | AvatarInitiativeEngine |
| PROPOSED | CONFLICT_CHECK | попадание в BodyArbiter | BodyArbiter |
| CONFLICT_CHECK | AUTHORIZED | нет конфликта ИЛИ конфликт разрешён в пользу Avatar | BodyArbiter |
| CONFLICT_CHECK | REJECTED | физически невозможно ИЛИ вытеснен Player с более высоким приоритетом | BodyArbiter |
| CONFLICT_CHECK | DEFERRED | временно невозможно (Windup pending, Body stunned), отложить на N ticks | BodyArbiter |
| AUTHORIZED | EXECUTING | фаза исполнения | StateApplicator |
| EXECUTING | COMPLETED | успешная материализация | StateApplicator |
| EXECUTING | FAILED | условие не выполнено (fail_reason обязателен) | StateApplicator |
| EXECUTING | INTERRUPTED | внешнее событие (interrupt_reason обязателен) | StateApplicator |
| EXECUTING | EXPIRED | истёк commitment_cost без завершения | StateApplicator |
| AUTHORIZED | CANCELLED | Avatar отозвал (до EXECUTING) | AvatarInitiativeEngine (revocation) |

**Reuse (VERIFIED):** переходы `EXECUTING → terminal` уже описаны в `ActionCommitment` FSM (action_commitment.py:28-55). `AvatarIntention` наследует терминальную семантику, но **не использует ActionCommitment как storage** — у Avatar свой registry, потому что `ActionCommitment.build_commitment_id(tick, npc_id, action, ordinal)` принимает `npc_id`, а у Avatar намерение не принадлежит NPC.

### 3.6. Отзыв, изменение, замена намерения (PROPOSED)

**Отзыв (revocation):**
- Avatar может отозвать намерение в состоянии `PROPOSED / AUTHORIZED (до EXECUTING)`.
- Отзыв создаёт `AvatarIntentionRevoked` event, который BodyArbiter обрабатывает в следующем тике.
- `supersedes` поле: новое намерение может явно указать заменяемое. BodyArbiter атомарно отменяет старое и принимает новое.

**Замена (replacement):**
- Если Avatar формирует новое намерение с `supersedes=old_intention_id`, BodyArbiter:
  1. Проверяет, что old_intention находится в `PROPOSED / AUTHORIZED` (не в `EXECUTING`)
  2. Переводит old в `CANCELLED` с `interrupt_reason="superseded_by:{new_id}"`
  3. Принимает new как PROPOSED → CONFLICT_CHECK → ...

**Изменение (modification):**
- Запрещено. Намерение immutable (`@dataclass(frozen=True)`). Изменение = отзыв + новое намерение с `supersedes`.

**Несовместимость (incompatibility):**
- `AvatarIntentionCandidate.conflicts_with` — список других candidate_ids, с которыми физически несовместимо (определяется в IntentionSynthesizer по `ActionClass × target × parameters`).
- BodyArbiter использует `conflicts_with` для построения графа конфликта при арбитраже (§6).

**Устаревание (staleness):**
- Намерение, не попавшее в BodyArbiter в течение `intent_stale_ticks` (PROPOSED: 1 tick), переходит в `EXPIRED`.
- Это защищает от очереди неисполнимых предложений.

### 3.7. Связь с памятью и убеждениями (PROPOSED)

**Memory (VERIFIED архитектура + PROPOSED extension):**
- `MemoryManager` сегодня keyed by `npc_id` + `partner_id`. Avatar memory → `npc_id="player"` (тело).
- Новое поле `owner_id` в `EventMemory` (PROPOSED) — кто владеет воспоминанием. По умолчанию `owner_id = npc_id`. Для Avatar-инициированных воспоминаний `owner_id = character_id`.
- Это позволяет разделять: «Avatar помнит, что Player приказал атаковать» (owner=avatar) vs «Тело получило урон» (owner=body, shared).

**Beliefs (VERIFIED + PROPOSED extension):**
- `EpistemicStore` keyed by `(agent_id, proposition)`.
- Avatar beliefs: `agent_id = "avatar:{character_id}"` (PROPOSED формат).
- Player beliefs: `agent_id = "player:{player_name}"` (PROPOSED формат).
- Текущий код использует `agent_id = "player"` без различения — это работает, пока есть один субъект. Добавление Avatar требует явного agent_id.
- `BeliefRevisionEngine.revise(listener_id, claim, ...)` уже принимает `listener_id` — достаточно передавать `"avatar:{character_id}"` для Avatar-наблюдений.

### 3.8. Переиспользуемые механизмы (VERIFIED)

| Механизм | Файл | Что переиспользуется |
|---|---|---|
| `EffectiveDrives` | `npc_state.py` (class), `drive_resolver.py` | Read-only projection из drives_runtime + temporary_drives |
| `DriveResolver.resolve_drives` | `drive_resolver.py:24` | L3 computation |
| `EpistemicStore` | `epistemic_store.py` | Belief storage keyed by agent_id (extension) |
| `EpistemicContextResolver.resolve(agent_id)` | `epistemic_context_resolver.py:52` | Avatar belief context |
| `BeliefRevisionEngine.revise` | `belief_revision_engine.py` | Avatar belief update from claims |
| `BeliefCrystallizationEngine.crystallize` | `belief_crystallization_engine.py:35` | Avatar belief formation from observations |
| `affective_integrator.integrate_affective_pressure` | `affective_integrator.py:27` | Avatar affect updates |
| `scan_affective_resonance` / `distort_pressure` | `affect.py` | Avatar perception distortion |
| `MemoryManager` (read path) | `memory_manager.py` | Avatar episodic memory recall |
| `BehaviorMaskState` | `behavior_mask.py` | Avatar behavioral mask overlay |
| `CharacterProfile.values` / `self_integrity` / `social_constraints` | `character.py` | Avatar value system (existing) |
| `ActionCommitment FSM` (transition rules) | `action_commitment.py:28-55` | Terminal semantics for AvatarIntention |
| `evaluate_vital_state(_body)` | `vital_state.py` (via DecisionHub) | Body alive/conscious check |
| `WindupRegistry` pattern | `action_windup.py` + `post_decision.py` | Pattern for AvatarIntentionRegistry |
| `KernelRNG` | `kernel_rng.py` | Determinism (если нужен RNG в selection) |

### 3.9. Недостающие ответственности (PROPOSED)

| Компонент | Зона ответственности | Новый или расширение |
|---|---|---|
| `AvatarInitiativeEngine` | Полный цикл субъектность → намерение | НОВЫЙ |
| `DesireSynthesizer` | drive × belief × value → desire | НОВЫЙ |
| `IntentionSynthesizer` | desire × feasibility × prior → intention candidate | НОВЫЙ |
| `AvatarIntentionRegistry` | Хранение intentions в scene_state, FSM transitions | НОВЫЙ (mirror WindupRegistry) |
| `BodyArbiter` | Арбитраж Player/Avatar/System intentions → AuthorizedExecutions | НОВЫЙ (см. §6) |
| `ControlSource.AVATAR_INITIATIVE` | Новое значение enum | РАСШИРЕНИЕ control_source.py |
| `EventMemory.owner_id` | Владелец воспоминания | РАСШИРЕНИЕ memory models |
| `EpistemicRecord.agent_id` формат | `"avatar:{character_id}"` / `"player:{player_name}"` | РАСШИРЕНИЕ (миграция существующих `"player"` → `"player:{name}"`) |
| `AvatarIntention → materialization` | Авторизованное намерение → CommunicationIntent / MovementIntent | НОВЫЙ adapter (parallel to IntentEventAdapter) |

### 3.10. Рекомендуемая архитектура (PROPOSED)

```text
[Phase 1.5 — NEW: Avatar Initiative]
    │  между Phase 1 (Input Merge / WillpowerGate) и Phase 2 (EventBus)
    │  Если player_turn in flight → Avatar Initiative пропускается
    │  (внутри хода игрока Avatar не формирует автономных намерений —
    │   стык с ADR-O-407; обоснование §6.4)
    ↓
AvatarInitiativeEngine.compute(
    avatar_state=NPCState(npc_id="player"),
    avatar_profile=CharacterProfile(character_id=avatar_character_id),
    effective_drives=DriveResolver.resolve_drives(...),
    epistemic_context=EpistemicContextResolver.resolve("avatar:{character_id}"),
    memory_context=MemoryManager.recent(npc_id="player", owner_id="avatar:{character_id}"),
    scene_state=ctx.scene_state,
    spatial_query=ctx.spatial_query
) → Tuple[AvatarIntention, ...]
    ↓
AvatarIntentionRegistry.persist(ctx.scene_state, intentions)
    ↓
[Phase 5 — existing: NPC Decision — UNCHANGED]
    ↓
[Phase 5.5 — NEW: Body Arbitration]
    │  после Phase 5 (NPC decisions готовы), до Phase 6 (IntentEventAdapter)
    ↓
BodyArbiter.resolve(
    player_intent = ctx.player_intent,  # из Phase 1 (если был)
    avatar_intentions = AvatarIntentionRegistry.pending(ctx.scene_state),
    npc_decisions = ctx.npc_decisions,  # из Phase 5
    system_intentions = ctx.system_intentions,  # traversals, combat, etc.
    body_states = ctx.body_states  # NPCState per body_id
) → AuthorizedExecutions[]
    ↓
AuthorizedExecutions → existing materialization paths
    (CommunicationIntent / MovementIntent / StateApplicator deltas)
    ↓
[Phase 6 — existing: IntentEventAdapter + WindupWriteGate — UNCHANGED]
    ↓
[Phase 7-10 — existing — UNCHANGED]
```

**Ключевая инвариантность:** TickOrchestrator фазовый порядок расширяется вставкой новых фаз 1.5 и 5.5, но **существующие фазы не модифицируются**. ADR-O-344 (единственный владелец времени) сохранён.

---

## §4. INTENTION CONTRACT

### 4.1. Существующие типы намерений (VERIFIED)

Сегодня в коде сосуществуют 4 independent контракта:

| Тип | Файл | Создатель | Что описывает | Куда передаётся |
|---|---|---|---|---|
| `InterventionEvent` | `contracts/interventions.py:14` | `InterventionEvent.from_player_action` | Внешнее вмешательство (source + payload + tick) | Phase 1 input |
| `PlayerAction` | `models/player_action.py:24` | REST API / DM Router | Намерение игрока (action_id, semantic_action, target_id) | InterventionEvent factory → Phase 1 |
| `CommunicationIntent` | `domain/communication.py` | `DecisionHub.compute` (после TopicExtractor) | Речевое намерение NPC (speaker, audience, topic, intent_type, exposure, proposition) | IntentEventAdapter → EventDTO |
| `DecisionResult` | `decision_hub.py:119` | `DecisionHub.compute` | NPC solution (intent: Intent enum, intent_target, score, scores_trace, deltas) | StateApplicator + NpcTickPipeline |
| `MovementIntent` | `domain/movement.py` | `NpcTickPipeline._route_intent_by_type` | Двигательное намерение (actor_id, target_actor_id) | MovementEngine |
| `ActionWindup` | `domain/action_windup.py` | `WindupWriteGate` (Phase 6) | Windowed-действие (attack, steal) с длительностью | WindupRegistry → Phase 7 Execution Gate |

**Наблюдение:** Каждый тип создавался для своего pipeline и свою задачу решает. `InterventionEvent` — generic transport. `PlayerAction` — player-side. `CommunicationIntent` — NPC speech. `DecisionResult` — NPC decision. `MovementIntent` — spatial. `ActionWindup` — execution gating.

### 4.2. Семантические уровни (PROPOSED)

R5.1 спецификация требует разделить 7 понятий. Их映射 на код today:

| Понятие | Определение (R5.1) | Сегодня в коде | AvatarIntention mapping |
|---|---|---|---|
| **Desire** | Субъект хочет определённого состояния | — (отсутствует) | `AvatarDesire` (§3.3) |
| **Intention** | Субъект решил стремиться к результату | `DecisionResult.intent` (NPC), `PlayerAction.action` (Player) | `AvatarIntention` (§3.4) |
| **Proposal** | Намерение предложено для исполнения | `CommunicationIntent` (после DecisionHub), `PlayerAction` (после Phase 1 normalize) | `AvatarIntention` в состоянии `PROPOSED` (§3.5) |
| **Commitment** | Субъект сохраняет намерение во времени | `ActionWindup` (только attack/steal), `ActionCommitment` (FSM storage) | `AvatarIntentionRegistry` entry with state ≥ PROPOSED |
| **Authorization** | Намерение допущено к исполнению | `WindupWriteGate` (attack/steal gating) + неявная фазовая сериализация | `BodyArbiter.resolve → AUTHORIZED` (§6) |
| **Execution** | Физическое действие выполняется | `StateApplicator.apply_deltas` (NPC), `process_traversals` (movement), `ImpactEngine` (combat) | Materialization в Phase 6/7 |
| **Outcome** | Фактическое последствие | EventDTO publication, world mutations | EventDTO publication (через materialization) |

**Эти состояния НЕ взаимозаменяемы.** Спецификация R5.1 §3.1 требует: «не считать эти состояния взаимозаменяемыми». Контракт `AvatarIntention` сохраняет все 7 состояний как явные transition stages, не коллапсирует их.

### 4.3. Контракт AvatarIntention — структура (PROPOSED)

```python
@dataclass(frozen=True)
class AvatarIntention:
    """Сформированное намерение Avatar. Передаётся в BodyArbiter.

    НЕ является CommunicationIntent. НЕ является PlayerAction.
    НЕ является DecisionResult. Это отдельный контракт.

    Семантика:
    - source_id = Avatar (character_id) — субъект намерения
    - body_id = "player" (NPCState.npc_id) — физический исполнитель
    - action_class = универсальный класс действия (не специфика)
    - parameters = специфика (после AUTHORIZATION → материализация)
    """
    intention_id: str  # детерминированный: f"{tick}:{character_id}:{ordinal}"
    formed_at_tick: int
    source_id: str  # character_id Avatar
    body_id: str  # всегда "player" (для MVP single-avatar)
    desire_id: Optional[str]  # provenance к желанию
    action_class: ActionClass
    target: Optional[str]  # npc_id / object_id / "player" / None
    parameters: Dict[str, Any]  # специфика после авторизации
    priority: float  # 0.0–1.0
    supersedes: Optional[str]  # intention_id заменяемого
    # Запрещено в намерении:
    # - event_type (это для EventDTO, не намерения)
    # - speaker / audience (это для CommunicationIntent)
    # - movement_target_node (это для MovementIntent)
    # ВСЁ это появляется в материализации, не в намерении.
```

### 4.4. Владелец намерения (PROPOSED)

R5.1 §3.2 требует: каждое намерение должно сохранять:
- кто сформировал → `source_id` (character_id Avatar)
- к какому субъекту относится → `source_id` (тот же — Avatar)
- через какое тело предполагается исполнение → `body_id` ("player")
- какого результата субъект добивается → `action_class + target + parameters`
- какие ограничения исполнения существуют → не в намерении; в `feasibility` candidate (§3.4) и в `BodyArbiter` решении (§6)
- какое намерение оно заменяет или продолжает → `supersedes` (или None)
- в каком состоянии находится → внешнее поле в `AvatarIntentionRegistry`, не в намерении (intention is immutable frozen)

**Provenance discipline:** намерение не должно нести внешней метаинформации. `desire_id` — это provenance chain (intention ← desire ← drive + belief). Кто вызвал `AvatarInitiativeEngine.compute` — это контекст вызова, не поле намерения.

### 4.5. Не плодить сущности (PROPOSED)

R5.1 §3.2: «не создавать поля только ради полноты таблицы».

**Минимальный набор** `AvatarIntention`:
- Идентификация: `intention_id, formed_at_tick, source_id, body_id`
- Пролонгация: `desire_id, supersedes`
- Содержание: `action_class, target, parameters, priority`

**Семь полей.** Не больше. Остальное — в registry (state machine), в materialization (event_type, speaker, audience), в arbiter (feasibility, conflicts).

### 4.6. Отказ от унификации (PROPOSED, обоснование §ENIGMA-002)

**Унификация существующих 4 типов в единый `Intention` НЕ предлагается.**

Обоснование по Two-Domain Rule:
1. **Два домена страдают от одной онтологической проблемы?** Сегодня у каждого типа своя проблема: `CommunicationIntent` не имеет target_id (GAP8 FIX добавил, но consumer-side patchy), `PlayerAction` не несёт exposure, `DecisionResult` не сериализуется как намерение, `InterventionEvent` слишком generic. Это РАЗНЫЕ проблемы, не одна.
2. **Локальное лекарство для доказанного бага** — каждый тип имеет свой фикс в своём pipeline.
3. **Второй домен подтверждён?** Нет. Введение универсального `Intention` было бы гипотезой «пригодится потом».

**Решение:** `AvatarIntention` — отдельный контракт, параллельный существующим. Если в будущем появится второй домен, требующий унификации с `AvatarIntention`, тогда ADR на универсальный `Intention` будет доказан двумя доменами.

### 4.7. Event identity и idempotency (PROPOSED)

`AvatarIntention.intention_id` — детерминированный: `f"{tick}:{character_id}:{ordinal}"`.

- Один tick + один Avatar + один ordinal → один intention_id
- Если Avatar формирует то же желание повторно в том же тике → тот же intention_id (idempotency)
- Между тиками: ordinal инкрементируется (новое намерение)
- `AvatarIntentionRegistry` хранит `intention_id → state` mapping
- Replay: deterministic от `(tick, character_id, ordinal)` (no random, no wall-clock — ADR-O-351 preserved)

---

## §5. INTENTION LIFECYCLE

### 5.1. Формальная машина состояний (PROPOSED)

```text
       ┌─────────┐
       │ FORMED  │  (AvatarInitiativeEngine emit)
       └────┬────┘
            │ PROPOSED transition (insert into Registry)
            ↓
       ┌──────────┐
       │ PROPOSED │  (Registry entry, awaiting BodyArbiter)
       └────┬─────┘
            │ BodyArbiter pickup
            ↓
       ┌───────────────┐
       │ CONFLICT_CHECK │  (BodyArbiter resolving)
       └────┬──────────┘
            │
   ┌────────┼─────────┬───────────┐
   ↓        ↓         ↓           ↓
┌─────────┐ ┌──────────┐ ┌─────────┐ ┌──────────┐
│AUTHORED │ │ REJECTED │ │ DEFERRED│ │ CANCELLED│
└────┬────┘ └──────────┘ └────┬────┘ └──────────┘
     │                       │ (wait N ticks)
     ↓                       ↓
┌──────────┐            back to
│EXECUTING │            PROPOSED
└────┬─────┘
     │
     ├──────────┬───────────┬───────────┐
     ↓          ↓           ↓           ↓
┌──────────┐┌────────┐┌───────────┐┌─────────┐
│COMPLETED ││ FAILED ││INTERRUPTED││ EXPIRED │
└──────────┘└────────┘└───────────┘└─────────┘
```

### 5.2. Операции над жизненным циклом (PROPOSED)

| Операция | Из | В | Триггер | Кто |
|---|---|---|---|---|
| **propose** | FORMED | PROPOSED | AvatarInitiativeEngine insert into Registry | AvatarInitiativeEngine |
| **pickup** | PROPOSED | CONFLICT_CHECK | BodyArbiter.scan_pending | BodyArbiter |
| **authorize** | CONFLICT_CHECK | AUTHORIZED | нет конфликта ИЛИ разрешён в пользу Avatar | BodyArbiter |
| **reject** | CONFLICT_CHECK | REJECTED | физически невозможно ИЛИ вытеснен Player | BodyArbiter |
| **defer** | CONFLICT_CHECK | DEFERRED | временно невозможно, отложить на N ticks | BodyArbiter |
| **requeue** | DEFERRED | PROPOSED | истёк wait N (или условие стало возможным) | BodyArbiter |
| **cancel** | PROPOSED / AUTHORIZED | CANCELLED | Avatar отозвал (через supersedes) | AvatarInitiativeEngine |
| **start_exec** | AUTHORIZED | EXECUTING | материализация инициирована | StateApplicator |
| **complete** | EXECUTING | COMPLETED | успешная материализация | StateApplicator |
| **fail** | EXECUTING | FAILED | условие не выполнено (fail_reason обязателен) | StateApplicator |
| **interrupt** | EXECUTING | INTERRUPTED | внешнее событие (interrupt_reason обязателен) | StateApplicator |
| **expire** | EXECUTING / DEFERRED | EXPIRED | истёк commitment_cost / wait_N | BodyArbiter / StateApplicator |

### 5.3. Отмена и замена (PROPOSED)

**Cancel (явный отзыв Avatar):**
- Только Avatar может инициировать cancel (через формирование нового намерения с `supersedes`, либо через явный `AvatarIntentionRevoked` event).
- BodyArbiter не отменяет — он только reject/defer.
- StateApplicator не отменяет — он только interrupt.

**Supersede (замена):**
- new.intention_id ≠ old.intention_id
- new.supersedes = old.intention_id
- BodyArbiter при обработке new: проверяет old.state ∈ {PROPOSED, AUTHORIZED} (не EXECUTING)
- Переводит old в CANCELLED с `interrupt_reason=f"superseded_by:{new.intention_id}"`
- Если old в DEFERRED → cancel + new идет в обычный CONFLICT_CHECK
- Если old в EXECUTING → supersede запрещён, new становится независимым (если конфликтует — попадёт в REJECTED)

### 5.4. Несовместимость (PROPOSED)

Два `AvatarIntention` несовместимы, если:
- Один и тот же `body_id`
- И `(action_class, target, parameters)` пересекаются по физическому ресурсу

Таблица несовместимости (PROPOSED — стартовая, расширяется по мере реализации):

| A \ B | SPEAK | MOVE | INTERACT_OBJECT | DEFEND | FLEE | OBSERVE | REFUSE_PLAYER | SEEK_CONTACT |
|---|---|---|---|---|---|---|---|---|
| SPEAK | — | ✅ compatible | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ |
| MOVE | ✅ | — | ❌ | ✅ | ❌ (разные направления) | ✅ | ✅ | ✅ |
| INTERACT_OBJECT | ❌ | ❌ | — (если разные targets → ✅) | ❌ | ❌ | ✅ | ❌ | ❌ |
| DEFEND | ❌ | ✅ | ❌ | — | ❌ | ✅ | ✅ | ❌ |
| FLEE | ❌ | ❌ (если target разный) | ❌ | ❌ | — (если target разный → ✅) | ✅ | ✅ | ❌ |
| OBSERVE | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ | ✅ |
| REFUSE_PLAYER | ❌ | ✅ | ❌ | ✅ | ✅ | ✅ | — | ✅ |
| SEEK_CONTACT | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ | — (если target разный → ✅) |

**Совместимые намерения могут быть исполнены одновременно** (Body может идти и говорить).

**Несовместимые** — BodyArbiter выбирает одно по приоритету + физической допустимости + commitment стоимости.

### 5.5. Устаревание (PROPOSED)

- `intent_stale_ticks = 1` — намерение, не попавшее в BodyArbiter в течение 1 tick после FORMED → EXPIRED.
- DEFERRED с истекшим wait_N → EXPIRED (если условие так и не стало возможным).
- AUTHORIZED, не перешедшее в EXECUTING в течение `authorized_timeout_ticks` (PROPOSED: 2 ticks) → EXPIRED.

### 5.6. Неисполненное намерение — след в памяти (PROPOSED)

R5.1 §3.3: «неисполненное намерение не должно бесследно исчезать, если оно продолжает иметь значение для субъекта».

**Правило:** При переходе в `REJECTED / EXPIRED / INTERRUPTED` — AvatarInitiativeEngine получает callback с результатом. Это влияет на:
- **DesireSynthesizer:** усиление/ослабление drive_origin при следующих вычислениях (если отклонено физически — понижается `opportunity_match`; если вытеснено Player — повышается `valence` avoidance).
- **Memory:** `EventMemory` с `owner_id="avatar:{character_id}"` и типом `intention_outcome` — Avatar помнит, что хотел и не смог.
- **Belief:** `EpistemicRecord` для propositions о себе («я не смог защитить X» → `belief(subject_id=avatar, predicate=FAILED_TO, object_id=X)`).
- **Affective:** `affective_integrator.integrate_affective_pressure` — rejected intention создаёт внутреннее давление (frustration, shame, fear в зависимости от контекста).

**Условие «продолжает иметь значение»** (PROPOSED): intention.priority ≥ 0.5 И outcome ∈ {REJECTED, INTERRUPTED, EXPIRED} И desire_id не superseded. Если priority < 0.5 — следа нет (мелкое желание, от которого отказался).

---

## §6. BODY ACTION ARBITRATION CONTRACT

### 6.1. Археология существующего исполнения (VERIFIED)

Полный путь Player Input → WORLD TRUTH:

```text
Player Input
    → POST /chat_turn (REST API)
    → GameLoop.run_turn(req) [game_loop.py]
    → _player_turn_in_flight.add(campaign_id)  [ADR-O-407 time gate]
    → TurnPipeline.execute(actions, ...) [turn_pipeline.py]
    → DM Router / PlayerTargetExtractor
    → InterventionEvent(source="player", payload={...}) [contracts/interventions.py:14]
    → TickOrchestrator.execute(interventions=[...])
        ├─ Phase 1: _phase_1_input
        │   ├─ resolve_intent_pressure(intent) → IntentPressureProfile
        │   ├─ scan_affective_resonance(intent, ...) → resonance
        │   ├─ distort_pressure(pressure, resonance, psyche) → distorted_pressure
        │   ├─ compute_willpower(distorted_pressure, psyche) → WillResponseDTO
        │   └─ if COMPLY/RELUCTANT/CONDITIONED:
        │         publish_player_intent(ctx, intent)
        │             → EventDTO.create(source="player", event_type=PLAYER_INTERACTS/ATTACKS)
        │             → bus.publish(EventDTO)
        │       else (RESIST/REFUSE/BROKEN):
        │             → DeltaBuffer.append(WILL_CONFLICT)
        │             → shared_context[counter_offer_text]
        ├─ Phase 2: EventBus primary (spatial events)
        ├─ Phase 5: NPC DecisionHub.compute (NPC могут реагировать на Player event)
        ├─ Phase 6: IntentEventAdapter (NPC CommunicationIntent → EventDTO)
        ├─ Phase 7: Windup Execution Gate (attack/steal terminal handling)
        ├─ Phase 8: Layered Reduction (drain + handle subscribers)
        │       └─ CombatSubscriber → ImpactEngine (физический урон)
        │       └─ ClaimEventSubscriber → EpistemicStore
        │       └─ dialogue_memory_subscriber → narrative_cache
        ├─ Phase 9: Integration (CFRM, Belief Crystallization)
        ├─ Phase 9.1: Affective Pipeline
        └─ Phase 10: Atomic Commit (WORLD TRUTH)
    → _player_turn_in_flight.discard(campaign_id)  [finally block]
```

**Другие пути, способные изменять Body:**
- **NPC автономные действия:** Phase 5 → StateApplicator (intent → NPCState changes: position, intent, will_state, etc.). Если `intent_target="player"` → воздействие на Avatar Body через события (ACTOR_ATTACKS, NPC_SPOKE).
- **Боевые действия:** Phase 8 CombatSubscriber → ImpactEngine → NPCState.body_state mutation (HP, injuries).
- **Movement:** Phase 0.75 process_traversals → NPCState position updates (включая Avatar, если у Avatar есть активный traversal).
- **Защитные реакции:** через WillpowerGate (counter_offer) — не физическое действие, только UI/hint.
- **Асинхронные результаты:** TaskScheduler.execute_pending → drain_task_worker_outbox → materializer → EventDTO publication. NPC-NPC диалоги материализуются во время player_turn_in_flight (не паузятся, ADR-O-313).
- **Системные эффекты:** Phase 0.5 idle services (decay), Phase 0.6 sleep lifecycle.
- **Внешние контроллеры:** Phase 1 input принимает任意 source (CK successor, world_scheduler, etc.) — InterventionEvent generic.
- **Прямые изменения NPCState:** только через StateApplicator с writes из разрешённых модулей (ADR-WRITE-GUARD).

### 6.2. Проверка атомарности (VERIFIED + PROPOSED)

**Утверждение:** «Один Body может исполнить только одно несовместимое физическое действие в пределах одного tick».

**Доказательство VERIFIED:**
- TickOrchestrator.execute() — single-threaded
- Phase 1 player intent → один InterventionEvent → один PlayerAction → один publish_player_intent → один EventDTO
- Phase 5 NPC per-id DecisionHub.compute — one DecisionResult per NPC per tick (вызывается один раз для каждого NPC в NpcTickPipeline.run)
- Phase 6 IntentEventAdapter — один EventDTO per CommunicationIntent
- Phase 7 Windup Execution Gate — terminal transitions для windup'ов (один переход per windup per tick)
- Phase 10 atomic commit — единая точка персистентности

**Что НЕ доказано неявной сериализацией (PROPOSED gap):**
1. Где начинается физическое исполнение? — Phase 1 (player intent mutation via StateApplicator) И Phase 5 (NPC decision mutation) И Phase 7 (windup execution) И Phase 8 (subscriber effects). Это **4 независимые точки**, не одна.
2. Где оно считается принятым? — Когда EventDTO опубликован в bus (Phase 1/6) ИЛИ когда StateApplicator применил deltas. **Нет единой точки acceptance.**
3. Где оно становится необратимым? — Phase 10 atomic commit. **До Phase 10 всё reverseable** (если delta_buffer ещё не слит).
4. Какие компоненты могут его обойти? — TaskScheduler.execute_pending (drain outside phases), прямые NPCState writes из разрешённых модулей (ADR-WRITE-GUARD список).
5. Сколько независимых исполнителей могут изменить Body? — StateApplicator (главный), ImpactEngine (combat), MovementEngine (traversal), direct writes from allowed modules. **Min 4 исполнителя.**
6. Возможны ли два конфликтующих воздействия в разных фазах? — Да. Пример: Phase 1 Player приказывает атаковать NPC X → EventDTO published. Phase 5 NPC Y (с intent_target=player) решает атаковать Avatar → EventDTO published. **Оба EventDTO — WORLD TRUTH** (после Phase 10). Это не конфликт — это причинная цепочка (Player атакует X, Y атакует Avatar).
7. Как обрабатываются составные действия? — Windup FSM (ActionWindup с длительностью) — attack имеет windup duration, за это время может быть INTERRUPTED.

**Вывод (PROPOSED):** «Атомарность» сегодня = следствие single-threaded TickOrchestrator + deterministic phase order. Это **сериализация**, не **арбитраж**. Когда появится Avatar Initiative, будет два независимых источника намерений на один Body (Phase 1 Player + Phase 1.5 Avatar), и фазовая сериализация не даст ответа «кто выиграл» — она даст только «кто первый попал в Phase».

### 6.3. Контракт BodyArbiter (PROPOSED)

```python
class BodyArbiter:
    """Арбитраж независимых намерений через одно физическое тело.

    Получает уже сформированные намерения. НЕ формирует желания/намерения.
    Решает вопрос физической совместимости и допуска.

    INVARIANTS:
    - Один Body → не более одного несовместимого исполнения per tick.
    - Все AUTHORIZED намерения → единственный исполнитель (StateApplicator).
    - REJECTED/DEFERRED намерения → back to AvatarInitiativeEngine (callback).
    - Не обходит INV-PLAYER-AUTHORSHIP (см. §8).
    """

    def resolve(
        self,
        player_intent: Optional[InterventionEvent],  # из Phase 1
        avatar_intentions: Tuple[AvatarIntention, ...],  # из Phase 1.5
        npc_decisions: Dict[str, DecisionResult],  # из Phase 5 (по npc_id)
        system_intentions: Tuple[SystemIntention, ...],  # traversal, combat, etc.
        body_states: Dict[str, NPCState],  # по body_id
        scene_state: Dict[str, Any],
        current_tick: int,
    ) -> AuthorizedExecutions:
        """
        Returns:
            AuthorizedExecutions:
                - body_executions: Dict[body_id, List[AuthorizedExecution]]
                - rejections: List[RejectionRecord]
                - deferrals: List[DeferralRecord]
                - conflicts_logged: List[ConflictRecord]
        """
```

### 6.4. Где в фазовой машине (PROPOSED)

```text
[Phase 1: Input Merge + WillpowerGate]  — UNCHANGED
    │  player_intent обработан (если был), WillpowerGate применил/заблокировал
    ↓
[Phase 1.5: Avatar Initiative]  — NEW
    │  AvatarInitiativeEngine.compute → Tuple[AvatarIntention]
    │  AvatarIntentionRegistry.persist
    │  Если player_turn in flight → пропускается (см. обоснование ниже)
    ↓
[Phase 2-4: EventBus / Memory / Pre-Decision]  — UNCHANGED
    ↓
[Phase 5: NPC Decision]  — UNCHANGED
    │  DecisionHub.compute для каждого NPC (intent_target="player" допустимо)
    ↓
[Phase 5.5: Body Arbitration]  — NEW
    │  BodyArbiter.resolve(player_intent, avatar_intentions, npc_decisions,
    │                       system_intentions, body_states, ...)
    │  → AuthorizedExecutions
    ↓
[Phase 6: Post-Decision + IntentEventAdapter]  — UNCHANGED (extended)
    │  IntentEventAdapter обрабатывает NPC CommunicationIntent (как сегодня)
    │  AvatarIntentionMaterializer (NEW) обрабатывает AuthorizedExecutions для Avatar
    │  → CommunicationIntent (для SPEAK) / MovementIntent (для MOVE) / etc.
    ↓
[Phase 7: Windup Resolution]  — UNCHANGED (extended)
    │  + AvatarIntentionRegistry state transitions AUTHORIZED → EXECUTING → terminal
    ↓
[Phase 8-10]  — UNCHANGED
```

**Почему Phase 1.5 пропускается во время player_turn in flight?**

`ADR-O-407` time-gate: пока ход игрока in-flight, idle_tick не вызывает `execute()` → Phase 0.5 не тикает, world time заморожен.

`run_turn` (player turn) вызывает TurnPipeline.execute, который **не** следует фазовой машине idle_tick. Внутри player turn Avatar Initiative **должна быть заморожена**, потому что:
1. Player подал команду → Body должен исполнить её (с возможным сопротивлением через WillpowerGate).
2. Avatar может抗争 через WillpowerGate (существующий механизм) → если RESIST, действие блокируется, counter_offer в shared_context.
3. Но Avatar не может в этот же tick сформировать автономное намерение — это создало бы двойное действие на Body внутри одного хода.

**Avatar Initiative работает в idle_tick** — когда Player бездействует. Если Player подал ход, Avatar "замолкает" до конца хода (с возможностью RESIST через WillpowerGate, но не возможностью сформировать альтернативное действие).

Это естественно следует из `player_turn_in_flight` time-gate и не требует новых правил.

### 6.5. Совместимость действий (PROPOSED)

`BodyArbiter._physical_compatibility(a, b) → Compatibility`:

```python
class Compatibility(str, Enum):
    COMPATIBLE = "compatible"        # можно одновременно
    SEQUENTIAL = "sequential"        # можно последовательно в одном тике
    INCOMPATIBLE = "incompatible"    # только одно
```

**Правила:**
- COMPATIBLE: SPEAK + MOVE (можно идти и говорить)
- SEQUENTIAL: SPEAK + SPEAK (две реплики — одна за другой, но обе в одном тике через очереди)
- INCOMPATIBLE: ATTACK + FLEE, INTERACT_OBJECT + INTERACT_OBJECT (с другим target), DEFEND + MOVE (только если move — flee; defend + slow move может быть совместимо)

Таблица (расширение §5.4) — используется та же матрица ActionClass × ActionClass.

### 6.6. Правила разрешения конфликтов (PROPOSED)

**Никаких бездоказательных приоритетов** (R5.1 §4.6):
- ❌ Player всегда первый
- ❌ Avatar всегда первый
- ❌ последнее намерение побеждает
- ❌ более сильное желание всегда побеждает
- ❌ движение важнее речи
- ❌ сопротивление всегда блокирует действие

**Механизм (PROPOSED):**

Конфликт между намерениями A и B (оба на body_id=X, INCOMPATIBLE):

```text
resolve_conflict(A, B, body_state) → DecisionResult:
    1. Физическая допустимость:
       - Если A.infeasible (body dead/stunned) → B wins (A → REJECTED)
       - Если B.infeasible → A wins (B → REJECTED)
       - Если оба infeasible → both REJECTED

    2. Active commitments (WindupRegistry):
       - Если A extends active windup → A wins (B → DEFERRED until windup completes)
       - Если B extends active windup → B wins
       - Если оба extend один windup → supersede logic (§5.3)

    3. Willpower balance (если один — Player, другой — Avatar):
       - Это зона WillpowerGate, но WillpowerGate сегодня работает для Player input.
       - EXTENSION: при конфликте Player vs Avatar — Avatar.compute_willpower
         на Player intent (как сегодня), но если WillState ∈ {RESIST, REFUSE, BROKEN},
         Avatar intention REFUSE_PLAYER авторизуется, Player intent → REJECTED.
       - Это сохраняет WillpowerGate в его ответственности (§6.7 ниже).

    4. Commitment cost (если оба физически допустимы, без активных windups, без Player-Avatar конфликта):
       - Меньший commitment_cost выигрывает (быстрее исполнить)
       - При равенстве — больший priority выигрывает
       - При равенстве priority — REJECTED оба, переформировать в следующем тике
         (no coin flip — детерминизм ADR-O-351)

    5. System intentions (traversals, combat) — отдельная зона:
       - Traversal в MOVING состоянии →占据 Body для duration_ticks (ADR-O-350)
       - Combat в EXECUTING → блокирует другие физические действия
       - System intention не конкурирует с Player/Avatar по arbitration table;
         они have priority по факту состояния (FSM terminal status stronger)
```

### 6.7. WillpowerGate — точная зона ответственности (VERIFIED + PROPOSED extension)

**Today (VERIFIED):** WillpowerGate = реактивное сопротивление Avatar давлению Player input.

**R5.1 сохраняет эту ответственность без изменений.** WillpowerGate НЕ становится универсальным арбитром.

**Точное место WillpowerGate в новой архитектуре:**
- WillpowerGate работает в Phase 1 (для player input) — UNCHANGED.
- BodyArbiter в Phase 5.5 не вызывает WillpowerGate — он получает уже разрешённый player_intent (прошедший или заблокированный WillpowerGate).
- Если WillpowerGate заблокировал player intent (RESIST/REFUSE) → в BodyArbiter приходит `player_intent=None` (он не прошёл фазу 1) И optionally `will_response` (для информирования Avatar, что было сопротивление).
- AvatarIntention `action_class=REFUSE_PLAYER` — это Avatar, активно выражающий отказ. BodyArbiter видит REFUSE_PLAYER от Avatar И `player_intent=None` (Player заблокирован WillpowerGate) → REFUSE_PLAYER авторизуется (Avatar выражает отказ физически — например, говорит «нет», или поворачивается спиной).
- Если Player не был заблокирован WillpowerGate (COMPLY) → AvatarIntention REFUSE_PLAYER обычно не формируется (DesireSynthesizer видит `will_state=COMPLY` и не порождает желание отказа).

**WillpowerGate ≠ BodyArbiter:**
- WillpowerGate: «Avatar сопротивляется команде Player» (один вход — player intent, один выход — WillState).
- BodyArbiter: «Два независимых намерения конкурируют за тело» (много входов, много выходов).
- Это разные задачи. Не объединять.

### 6.8. Конфликтные ситуации A-G (PROPOSED)

**A. Совместимые намерения**
Player хочет говорить (SPEAK), Avatar хочет продолжить движение (MOVE).
- BodyArbiter: COMPATIBLE → оба AUTHORIZED.
- Исполнение: одновременно (StateApplicator applies speech delta + movement delta).
- WORLD TRUTH: PLAYER_SPOKE event + NPC_MOVED event (Avatar = NPCState npc_id="player").

**B. Противоположные намерения**
Player хочет атаковать (attack NPC X), Avatar хочет отступить (FLEE от X).
- Player input → Phase 1 → WillpowerGate: Avatar.compute_willpower на player intent.
- WillState ∈ {RESIST, REFUSE, BROKEN} → player_intent REJECTED в Phase 1.
- Avatar Initiative (Phase 1.5, если idle) → формирует AvatarIntention(FLEE, target=X).
- BodyArbiter: только AvatarIntention pending → AUTHORIZE.
- Если Player повторит команду в следующем тике → снова WillpowerGate; если trauma_markers накоплены → stronger resistance.
- **Outcome:** Body выполняет FLEE, не ATTACK.

**C. Avatar сопротивляется Player**
Player хочет атаковать, Avatar не соглашается.
- Похоже на B, но explicitly: Player command продолжает поступать, Avatar инициативы FLEE нет — Avatar только RESIST.
- Phase 1: WillpowerGate блокирует player intent. player_intent=None в BodyArbiter.
- AvatarIntention: нет (Avatar не имеет собственного желания действовать, только не хочет выполнять Player).
- BodyArbiter: нет authorised executions для Body. Body бездействует в этом тике.
- WORLD TRUTH: WILL_CONFLICT event (no body action); shared_context[counter_offer_text].

**D. Player противодействует Avatar**
Avatar хочет отступить (FLEE), Player выдаёт команду двигаться вперёд (MOVE toward threat).
- Если это idle-тик: Phase 1.5 Avatar → AvatarIntention(FLEE). Phase 1 player_intent=None.
- Phase 5.5 BodyArbiter: только AvatarIntention → AUTHORIZE.
- Если Player подаёт InterventionEvent в этом же тике (через run_turn):
  - run_turn активируется → player_turn_in_flight=True → Phase 1.5 Avatar Initiative пропускается (§6.4).
  - Phase 1 player_intent обрабатывается WillpowerGate.
  - Avatar может RESIST через WillpowerGate.
- **Cross-tick scenario:** Avatar начал FLEE в тике N (windup или сразу). В тике N+1 Player подаёт MOVE forward.
  - Active windup for FLEE → BodyArbiter: Player MOVE blocked by active windup (§6.6 rule 2).
  - Player intent → REJECTED с reason "active_windup:{flee_id}".

**E. Два намерения одного субъекта (Avatar)**
Avatar хочет одновременно приблизиться к NPC (SEEK_CONTACT) и избежать контакта (FLEE от того же NPC).
- DesireSynthesizer порождает два желания с противоположным valence.
- IntentionSynthesizer порождает два candidates с `conflicts_with=[other_id]`.
- AvatarInitiativeEngine выбирает по priority + value_alignment (какой drive сильнее).
- BodyArbiter: видит один AvatarIntention (выбранный), второй → EXPIRED (не попал в Registry).
- **Не порождает конфликт в BodyArbiter** — конфликт разрешён внутри Avatar Initiative.

**F. Невозможность исполнения**
Body мёртв, обездвижен, ранен.
- BodyArbiter проверяет `evaluate_vital_state(body_state)` для каждого body_id.
- Если dead/unconscious → все intentions на этот body → REJECTED с reason "body_unavailable:{reason}".
- AvatarIntention → REJECTED callback → AvatarInitiativeEngine получает сигнал (влияет на future desires, memory, beliefs).
- Player intent → REJECTED (если Player попытается что-то сделать мёртвым телом).
- WORLD TRUTH: ничего не происходит с Body (но другие NPC продолжают жить).

**G. Прерывание**
Во время исполнения возникает внешнее событие, меняющее допустимость.
- AvatarIntention AUTHORIZED → EXECUTING (через AvatarIntentionMaterializer).
- В Phase 7/8 возникает событие (например, NPC атакует Avatar, тело получает травму → body_state изменён).
- StateApplicator: проверяет условие исполнения — если больше не выполнимо → INTERRUPTED с `interrupt_reason=f"external:{event_type}:{event_id}"`.
- Если выполнимо частично → COMPLETED с partial outcome note.
- Если завершено до события → COMPLETED (событие не ретро-прерывает).

### 6.9. Защита от двойного исполнения (PROPOSED)

**Гарантия:** каждое `AvatarIntention.intention_id` переходит в EXECUTING не более одного раза.

- `AvatarIntentionRegistry` хранит state per intention_id.
- State machine (§5.1) — переход `AUTHORIZED → EXECUTING` идемпотентный: если уже EXECUTING, повторный вызов start_exec → no-op + warning.
- Materializer проверяет state перед материализацией: если state ≠ AUTHORIZED → отказ.
- После terminal state (COMPLETED/FAILED/INTERRUPTED/EXPIRED) — registry entry frozen, further transitions rejected.

**Reuse pattern:** `ActionWindup.status` FSM (`WindupStatus.PENDING/COMPLETED/INTERRUPTED`) — тот же guard pattern.

### 6.10. Детерминированность (PROPOSED)

R5.1 §4.6: «воспроизводимость сама по себе не объясняет правильность решения». Но **детерминизм — обязательное условие** (ADR-O-351).

- `BodyArbiter.resolve` — pure function от inputs (без RNG, без wall-clock, без thread-local state).
- Если (player_intent, avatar_intentions, npc_decisions, system_intentions, body_states, scene_state, current_tick) → один и тот же AuthorizedExecutions.
- Если необходим выбор между равноправными кандидурами (priority и commitment_cost равны) — REJECTED оба (не coin flip).
- Это может привести к "stall" (оба REJECTED каждый тик) — решение в AvatarInitiativeEngine (adjust desire weights based on prior rejections, §5.6).

---

## §7. BODY EXECUTION CONTRACT

### 7.1. Граница физического исполнения (PROPOSED)

**Граница = Phase 5.5 BodyArbiter.resolve output → Phase 6 materialization input.**

```text
[Phase 5.5] BodyArbiter.resolve → AuthorizedExecutions
    │
    │  AuthorizedExecution = {
    │      body_id: str,
    │      intention: AvatarIntention / PlayerIntent / NPCDecision / SystemIntention,
    │      materialization_kind: MaterializationKind,
    │      execution_id: str  # детерминированный: tick:body_id:ordinal
    │  }
    ↓
[Phase 6] Materialization
    │  По materialization_kind:
    │    - SPEAK → CommunicationIntent (через новый AvatarIntentionMaterializer)
    │    - MOVE → MovementIntent
    │    - INTERACT_OBJECT → ObjectInteraction (существующий контракт)
    │    - DEFEND → DefenseStance delta (через StateApplicator)
    │    - FLEE → MovementIntent (target=furthest_node)
    │    - OBSERVE → no physical effect (только memory write)
    │    - REFUSE_PLAYER → CommunicationIntent (speech "no") + body turn
    │    - SEEK_CONTACT → MovementIntent (target=nearest_node_to_target)
    ↓
[Phase 6 existing] IntentEventAdapter (для CommunicationIntent → EventDTO)
    │  + AvatarIntentionMaterializer (NEW) — для Avatar-authorized
    │  EventDTO.create(source=character_id) — Avatar source, не "player"
    ↓
[Phase 7] Windup Execution Gate
    │  attack/steal → ActionWindup (как сегодня для NPC, но source=Avatar)
    ↓
[Phase 8] Layered Reduction
    │  subscribers обрабатывают EventDTO
    │  CombatSubscriber (для ACTOR_ATTACKS от Avatar) → ImpactEngine на target
    │  ClaimEventSubscriber (для NPC_SPOKE от Avatar) → Proposition(subject_id=avatar_character_id)
    ↓
[Phase 9-10] Integration + Persistence → WORLD TRUTH
```

### 7.2. Materialization contract (PROPOSED)

`AvatarIntentionMaterializer.materialize(execution: AuthorizedExecution) → MaterializationResult`:

```python
@dataclass(frozen=True)
class MaterializationResult:
    """Результат материализации авторизованного намерения."""
    execution_id: str
    communication_intent: Optional[CommunicationIntent]  # для SPEAK
    movement_intent: Optional[MovementIntent]            # для MOVE/FLEE/SEEK_CONTACT
    state_deltas: List[StateDeltas]                      # для DEFEND/OBSERVE/REFUSE_PLAYER
    windup_request: Optional[ActionWindup]               # для ATTACK/STEAL (если Avatar их делает)
```

**Гарантии:**
- Один `execution_id` → один `MaterializationResult`.
- `MaterializationResult` передаётся в существующие pipeline (IntentEventAdapter / MovementEngine / StateApplicator) без модификации этих pipeline.
- `WindupWriteGate` (Phase 6 existing) обрабатывает `windup_request` так же, как для NPC — создаёт ActionWindup entry.

### 7.3. EventDTO source attribution (PROPOSED)

**Сегодня (VERIFIED):** `publish_player_intent` ставит `source="player"` (hardcoded). `IntentEventAdapter` ставит `source=intent.speaker` (npc_id).

**Proposal:**
- Avatar-authorized execution → `EventDTO.source = character_id` (Avatar's character_id, не "player").
- Это позволяет подписчикам различать:
  - `event.source == "player"` → Player-authored action (through Phase 1 publish_player_intent).
  - `event.source == "{character_id}"` → Avatar-authored action (through Phase 6 AvatarIntentionMaterializer).
  - `event.source == "{npc_id}"` → NPC-authored action (existing path).

**Migration concern:** сегодня `claim_event_subscriber.on_player_spoke` fallback `getattr(event, "source", "player")` (claim_event_subscriber.py:108). Это означает, что если Avatar-authored PLAYER_SPOKE event имеет `source={character_id}`, подписчик не найдёт его в existing player path.

**Решение:** Avatar-authored SPEAK events должны иметь `event_type=NPC_SPOKE` (НЕ PLAYER_SPOKE), потому что Avatar — отдельный субъект, не Player. Зеркало DLG-1 (S388): Speaker Symmetry — Player и NPC имеют симметричные speech-act subscribers. Avatar = третий субъект, его speech acts идут через NPC_SPOKE path с `source=character_id`.

### 7.4. Атомарность исполнения (PROPOSED + VERIFIED)

**Гарантия:** One Body × One tick × One incompatible execution.

- `BodyArbiter.resolve` гарантирует, что для каждого body_id возвращается список AUTHORIZED executions, где все pairwise COMPATIBLE.
- Phase 6 materializer обрабатывает их последовательно (в deterministic order: by execution_id).
- Phase 7 windup gate создаёт windups для windowed actions (attack/steal) — execution_id связан с windup_id.
- Phase 8 subscribers видят EventDTOs в publish order (deterministic по event_identity.py).
- Phase 10 atomic commit — единая точка персистентности. До Phase 10 все изменения в `delta_buffer` и `scene_state` reverseable.

### 7.5. Что может обходить границу (VERIFIED + PROPOSED guard)

**Существующие обходы (VERIFIED):**
- `TaskScheduler.execute_pending` — drain outside phases (NPC-NPC async диалоги). Это не обход — это deterministic boundary (ADR-O-399).
- ADR-WRITE-GUARD разрешённые модули — direct NPCState writes (memory_manager, state_applicator, etc.). Это не обход — это per-field write authority.

**Защита от новых обходов (PROPOSED):**
- AvatarIntention state transitions только через `AvatarIntentionRegistry.transition(intention_id, from_state, to_state, reason)` — единственная точка.
- Body action authorization только через `BodyArbiter.resolve` — единственная точка.
- Если новый код мутирует Avatar Body state в обход этих точек → architectural violation (lint rule + runtime guard).

---

## §8. INV-PLAYER-AUTHORSHIP

### 8.1. Текущий инвариант (VERIFIED)

INV-PLAYER-AUTHORSHIP сегодня — три уровня защиты:

**Уровень 1 — ControlSource enum (control_source.py):**
```python
class ControlSource(str, Enum):
    PLAYER_INPUT = "player_input"
    NPC_DECISION = "npc_decision"
    SCRIPTED_SYSTEM = "scripted_system"
    COMBAT_CONTROLLER = "combat_controller"

_PLAYER_ACTORS = frozenset({"player"})

def resolve_control_source(actor_id: str) -> ControlSource:
    if actor_id in _PLAYER_ACTORS:
        return ControlSource.PLAYER_INPUT
    return ControlSource.NPC_DECISION
```

**Уровень 2 — DecisionHub guard (decision_hub.py:326-331):**
```python
if resolve_control_source(npc_id) is not ControlSource.NPC_DECISION:
    raise ArchitecturalViolationError(
        f"[INV-PLAYER-AUTHORSHIP] speaker={npc_id!r}: авторский "
        f"{resolve_control_source(npc_id).value}), intent={intent_value!r} отклонён"
    )
```

**Уровень 3 — npc_tick_pipeline detectors (npc_tick_pipeline.py:1084, 1089, 1240, 1253):**
- attack-factory guard (уровень 2)
- boundary detector (уровень 3)

### 8.2. Расширение ControlSource (PROPOSED)

Добавить значение `AVATAR_INITIATIVE`:

```python
class ControlSource(str, Enum):
    PLAYER_INPUT = "player_input"
    NPC_DECISION = "npc_decision"
    SCRIPTED_SYSTEM = "scripted_system"
    COMBAT_CONTROLLER = "combat_controller"
    AVATAR_INITIATIVE = "avatar_initiative"  # NEW
```

**Update `resolve_control_source`:**
- Сегодня: `"player" → PLAYER_INPUT`, else → `NPC_DECISION`
- Новое: `"player" → PLAYER_INPUT`, `is_avatar_character(character_id) → AVATAR_INITIATIVE`, else → `NPC_DECISION`
- `is_avatar_character(character_id)` — проверка по AvatarCharacterRegistry (PROPOSED — новый реестр: какие character_id — это Avatar-сознания).

**Без изменения fallback:** `NPC_DECISION` остаётся default. Это гарантирует, что NPC без явного Avatar-маркера остаются NPC. Нет неявного разрешения через fallback в NPC_DECISION.

### 8.3. Что НЕ меняется (VERIFIED — invariant preserved)

**DecisionHub.compute guard остаётся без изменений:**
```python
if resolve_control_source(npc_id) is not ControlSource.NPC_DECISION:
    raise ArchitecturalViolationError(...)
```

Это означает:
- `npc_id="player"` → `resolve_control_source → PLAYER_INPUT` → raise (Avatar Body не проходит через DecisionHub).
- `character_id=avatar_X` (если это Avatar) → `resolve_control_source → AVATAR_INITIATIVE` → raise (Avatar character_id не проходит через DecisionHub).
- `npc_id="tornin"` → `resolve_control_source → NPC_DECISION` → proceed (NPC continues as today).

**AvatarInitiativeEngine.compute** не вызывает `DecisionHub.compute`. Avatar Initiative — полностью отдельный pipeline.

### 8.4. Модель полномочий и границ авторизации (PROPOSED)

| Субъект | Источник намерения | ControlSource | Может авторизовать действие на Body? | Через что |
|---|---|---|---|---|
| Player | Player input (Phase 1) | `PLAYER_INPUT` | Да (через WillpowerGate) | `publish_player_intent` → `BodyArbiter` (player_intent input) |
| Avatar | AvatarInitiativeEngine (Phase 1.5) | `AVATAR_INITIATIVE` | Да (через `BodyArbiter`) | `AvatarIntentionRegistry` → `BodyArbiter` (avatar_intentions input) |
| NPC | DecisionHub.compute (Phase 5) | `NPC_DECISION` | Нет (только для собственного тела) | `DecisionResult` → `StateApplicator` (NPC body, не Avatar Body) |
| System (traversal/combat) | Phases 0.75/8 | `SCRIPTED_SYSTEM` / `COMBAT_CONTROLLER` | Только если Body уже в system FSM | WindupRegistry / TraversalState |

**Avatar ≠ NPC:** Avatar имеет собственный pipeline (AvatarInitiativeEngine), не DecisionHub.
**Avatar ≠ PLAYER_INPUT:** Avatar-authorized action получает `EventDTO.source = character_id`, не `"player"`.
**Физический исполнитель ≠ автор намерения:** Body (npc_id="player") исполняет, но `event.source` указывает на автора (Player или Avatar character_id).

### 8.5. NPC не может выдавать себя за Avatar (PROPOSED guard)

- NPCDecision с `intent_target="player"` — это NPC воздействует на Avatar Body через события (например, NPC атакует Avatar). Это легально и сегодня работает.
- NPCDecision с `intent.speaker="avatar_character_id"` — НЕ легально. DecisionHub guard (`decision_hub.py:327`) проверяет `npc_id`, не `speaker`, но `IntentEventAdapter` (intent_event_adapter.py) ставит `source=intent.speaker`. Если NPC подделает `speaker`, это создаёт событие с неверным source.
- **Защита (PROPOSED):** добавить guard в IntentEventAdapter — если `intent.speaker` matches `is_avatar_character(speaker)`, но `npc_id ≠ speaker` (NPC подделывает), → raise `ArchitecturalViolationError`.
- Это mirror INV-PLAYER-AUTHORSHIP для Avatar: `INV-AVATAR-AUTHORSHIP`.

### 8.6. Avatar не классифицируется как PLAYER_INPUT (PROPOSED)

Сегодня `claim_event_subscriber.on_player_spoke` (claim_event_subscriber.py:108) использует `speaker = getattr(event, "source", "player")` с fallback на `"player"`. Это означает, что Avatar-authored SPEAK events (если `source={character_id}`) НЕ попадут в PLAYER_SPOKE handler.

**Контракт:**
- Avatar-authored SPEAK events должны иметь `event_type=NPC_SPOKE` (НЕ PLAYER_SPOKE). Зеркало DLG-1 (S388 Speaker Symmetry).
- `event.source = character_id` (Avatar identity).
- `claim_event_subscriber.on_npc_spoke` обрабатывает их (через `event.source` — Avatar как «NPC-like» субъект для социального восприятия).
- **Изменение fallback:** `getattr(event, "source", "player")` → `getattr(event, "source", None)` (или оставить `"player"` только для событий без source, что является data integrity issue).

### 8.7. Avatar не классифицируется как NPC_DECISION (PROPOSED)

- AvatarInitiativeEngine не вызывает DecisionHub.compute.
- AvatarIntention не проходит через NpcTickPipeline._route_intent_by_type (npc_tick_pipeline.py).
- AvatarIntention → AvatarIntentionMaterializer → CommunicationIntent / MovementIntent (новый adapter, параллельный IntentEventAdapter).
- CommunicationIntent от Avatar имеет `speaker=character_id`, но создаётся не DecisionHub, а AvatarIntentionMaterializer.
- INV-PLAYER-AUTHORSHIP detector на границе npc_tick_pipeline (level 3, line 1240) не видит Avatar-authorized actions, потому что они идут через отдельный materialization path.

### 8.8. Не возникает неявного разрешения через fallback (PROPOSED)

**Avatar-authored actions НЕ попадают в NPC_DECISION fallback:**
- `resolve_control_source(character_id) → AVATAR_INITIATIVE` (не NPC_DECISION).
- Если кто-то попытается обработать Avatar character_id через NPC-decision pipeline — `DecisionHub.compute` поднимет `ArchitecturalViolationError` (guard line 327).

**Player-authored actions НЕ попадают в AVATAR_INITIATIVE:**
- `resolve_control_source("player") → PLAYER_INPUT` (по `_PLAYER_ACTORS = frozenset({"player"})`).
- Body's npc_id всегда `"player"` (Body identity), но автор намерения определяется по source_id намерения, не по body_id.

### 8.9. Физический исполнитель не становится автоматически автором (PROPOSED — ключевое)

**Случай 1: Player input, WillpowerGate COMPLY, Avatar нет автономной инициативы.**
- Player подаёт ATTACK NPC X.
- Phase 1 WillpowerGate: Avatar.compute_willpower → COMPLY.
- publish_player_intent → EventDTO(source="player", event_type=PLAYER_ATTACKS).
- Body исполняет, но **event.source = "player"** — автор Player, не Body.

**Случай 2: Avatar автономно формирует ATTACK NPC X (idle tick).**
- Phase 1.5 AvatarInitiativeEngine → AvatarIntention(ATTACK, target=X, source_id=character_id).
- Phase 5.5 BodyArbiter → AUTHORIZE.
- Phase 6 AvatarIntentionMaterializer → CommunicationIntent(speaker=character_id, intent_type="attack") → EventDTO(source=character_id, event_type=ACTOR_ATTACKS).
- Body исполняет, но **event.source = character_id** — автор Avatar, не Body.

**Случай 3: Avatar сопротивляется Player (REFUSE_PLAYER).**
- Player подаёт ATTACK NPC X.
- Phase 1 WillpowerGate: Avatar.compute_willpower → RESIST. Player intent blocked.
- Phase 1.5 Avatar Initiative (если idle) → AvatarIntention(REFUSE_PLAYER, target=Player) — Avatar активно отказывается.
- Phase 5.5 BodyArbiter → AUTHORIZE (REFUSE_PLAYER from Avatar).
- Phase 6 Materializer → CommunicationIntent(speaker=character_id, intent_type="warn"/"talk", parameters={refusal=true}) → EventDTO(source=character_id, event_type=NPC_SPOKE).
- Body исполняет (произносит отказ), **event.source = character_id** — автор Avatar.

**Во всех случаях Body = физический исполнитель, но автор — отдельная идентичность.**

---

## §9. BODY LOSS / UNAVAILABILITY

### 9.1. Текущее поведение (VERIFIED)

`DecisionHub.compute` Vital State Guard (decision_hub.py:550+):
```python
_body = getattr(state, "body_state", None) or {}
_life_status = evaluate_vital_state(_body)
if not _life_status.is_conscious:
    return AgentAction(
        decision=DecisionResult(
            npc_id=state.npc_id,
            intent=Intent.IDLE,
            intent_target=None,
            score=0.0,
            scores_trace={"veto": 0.0},
            deltas=[],
        )
    )
```

Это **для NPC**. Для Avatar (NPCState npc_id="player") — сегодня Avatar не проходит через DecisionHub (INV-PLAYER-AUTHORSHIP blocks). Avatar Body state changes (HP, injuries) обрабатываются через:
- `ImpactEngine` (combat damage writes to body_state)
- `InjuryProcessor` (ADR-123)
- `Sleep lifecycle` (Phase 0.6)
- `Time-driven decay` (Phase 0.5)

Если Avatar Body умирает (`evaluate_vital_state → DEAD`), сегодня:
- NPC не могут адресовать действия мёртвому Avatar (через liveness guards в speech/dialogue materialization — ADR-O-365, ADR-O-366).
- Player input на мёртвый Body: Phase 1 input не имеет явного vital-state check для Avatar. Это **gap (PARTIALLY VERIFIED)** — сегодня player может подать команду на мёртвый Body, и она пройдёт через WillpowerGate (Avatar psyche берётся из `player_dict.get("psyche", {})`), но материализация может ничего не сделать (state_applicator обнаружит dead body).

### 9.2. R5 установленный принцип (VERIFIED from R5)

R5: «при смерти Body идентичности Player и Avatar сохраняются, но физические действия становятся невозможны».

Это означает:
- Player consciousness (PlayerSession) — персистит (server-side state, не зависит от Body).
- Avatar consciousness (CharacterProfile + beliefs + memory) — персистит (storage-backed, не зависит от Body).
- Body (NPCState npc_id="player") — может умереть; его поля (HP, body_state) отражают смерть.

### 9.3. Поведение намерений при потере Body (PROPOSED)

| Намерение | Body dead | Body stunned | Body asleep |
|---|---|---|---|
| Player input (ATTACK, MOVE, SPEAK) | REJECTED (BodyArbiter rule 1) | REJECTED | REJECTED (если deep sleep) или DEFERRED (light sleep) |
| AvatarIntention MOVE/FLEE/ATTACK | REJECTED | REJECTED | REJECTED (если deep sleep) или DEFERRED |
| AvatarIntention SPEAK | REJECTED | DEFERRED (stunned → cannot speak coherently) | REJECTED (deep) / DEFERRED (light, dream-like) |
| AvatarIntention OBSERVE | PARTIAL (perception impaired) | PARTIAL | DREAM-like (special path, ADR-O-356) |
| AvatarIntention REFUSE_PLAYER | REJECTED (no physical expression) | REJECTED (can't speak) | REJECTED |
| NPC decisions (intent_target=player) | REJECTED (target unavailable) | Proceed (target conscious but impaired) | Proceed (target asleep, special dialogue path) |

### 9.4. Что продолжается без Body (PROPOSED)

**Avatar consciousness persists:**
- `AvatarInitiativeEngine` может продолжать вычислять желания (desires) — internal state changes не требуют физического исполнения.
- Beliefs update через `BeliefRevisionEngine` (если Avatar воспринимает что-то вокруг мёртвого тела — например, слышит, что говорят над ним).
- Memory writes через `MemoryManager` (если есть что запомнить — например, момент смерти).
- Affective updates через `affective_integrator` (страх смерти, фрустрация).

**Но:** без Body нет физического действия. Avatar может хотеть, но не может действовать.

### 9.5. Что происходит с Player input (PROPOSED)

- Player input подаётся через REST API. Если Body мёртв:
  - Phase 1 input получает InterventionEvent.
  - WillpowerGate: Avatar.compute_willpower на intent. Avatar psyche мёртвого тела может быть `BROKEN/COMPLY` (если травма сломала волю) или `REFUSE` (если Avatar сопротивляется смерти).
  - Phase 5.5 BodyArbiter: `evaluate_vital_state(body_state) → DEAD` → player_intent REJECTED.
  - Response к Player: ChatTurnResponse с информацией «Body мёртв, действие невозможно».

**Геймдизайнерский вопрос (§16-Q3):** что Player должен видеть в UI при мёртвом Body? Сегодня явного ответа нет.

### 9.6. Может ли существовать новый Body (PROPOSED — open)

R5.1 spec §6: «не проектировать новую механику переселения или воскрешения без подтверждения авторского замысла».

**Архитектурная готовность (без реализации):**
- `AvatarCharacterRegistry` может связывать `character_id` с разными `body_id` (но сегодня 1:1 mapping).
- Если в будущем вводится воскрешение/переселение:
  - `CharacterProfile` остаётся (persist).
  - `EpistemicStore` для `agent_id="avatar:{character_id}"` остаётся (persist).
  - `MemoryManager` для `owner_id="avatar:{character_id}"` остаётся.
  - `body_id` меняется на новый NPCState — старые привязки (Windups, ActionCommitments) → CANCELLED с `interrupt_reason="body_lost"`.
  - Новый Body наследует character_id linkage, но не старые физические обязательства.

**Не проектировать дальше** — дождаться отдельного авторского решения по воскрешению/переселению (§16-Q3).

### 9.7. Сохранение связи субъекта с телом при смене носителя (PROPOSED placeholder)

Если/когда механика смены Body будет авторизована:
- `AvatarCharacterRegistry.link(character_id, body_id)` — текущая связь.
- При смене: `unlink(character_id, old_body_id)` + `link(character_id, new_body_id)`.
- `AvatarInitiativeEngine` всегда использует текущий `body_id` из registry (не hardcoded "player").
- `BodyArbiter` всегда использует `character_id` из намерения (не body_id) для attribution.

**Сегодня это stub.** MVP single-avatar: character_id ↔ body_id="player" — 1:1 mapping. Миграция на multi-body — будущий ADR.

---

## §10. ИНТЕГРАЦИОННЫЕ СЦЕНАРИИ

Восемь обязательных сценариев из R5.1 §7. Каждый показан через состояния и причинные переходы.

### 10.1. Сценарий 1: Player бездействует — Avatar самостоятельно формирует и исполняет намерение

**Preconditions:**
- Idle tick (нет player_turn_in_flight).
- Avatar psyche: drives {fear: 0.3, desire: 0.6}, life_project="survival".
- Scene: NPC "merchant_boris" рядом, продаёт еду.
- Avatar beliefs: `("merchant_boris", has_food, ?, conf=0.7)`.
- Avatar values: {survival: high, generosity: medium}.
- Avatar satiation: 0.2 (голоден).

**Causal trace:**
```text
[idle_tick call]
    ↓
Phase 1.5: Avatar Initiative
    AvatarInitiativeEngine.compute(avatar_state, profile, drives, beliefs, memory, ...)
        ↓
    DesireSynthesizer:
        drives.fear=0.3, drives.desire=0.6 (acquire food)
        belief_alignment: merchant has food (0.7)
        opportunity_match: merchant in sight, close (0.9)
        value_compat: survival-aligned (0.8)
        satiation_inhibition: 1 - 0.2 = 0.8 (hungry, no inhibition)
        desire_score = 0.6 × 0.7 × 0.9 × 0.8 × 0.8 = 0.242
        desire = AvatarDesire(kind=ACQUIRE, target="merchant_boris", urgency=0.242)
    ↓
    IntentionSynthesizer:
        candidate: SPEAK to merchant_boris (request food trade)
        feasibility: 0.9 (merchant conscious, in range)
        commitment_cost: 1 (one tick to speak)
        conflicts_with: []
        → AvatarIntention(action_class=SPEAK, target="merchant_boris",
                          parameters={topic="trade_food"}, priority=0.242,
                          source_id="avatar_orm")
    ↓
    AvatarIntentionRegistry.persist (state=PROPOSED)
    ↓
Phase 5: NPC Decision (UNCHANGED)
    merchant_boris: DecisionHub.compute → intent=IDLE или TRADE (если видит Avatar)
    ↓
Phase 5.5: Body Arbitration
    BodyArbiter.resolve(
        player_intent=None,
        avatar_intentions=[AvatarIntention(SPEAK, target=merchant_boris)],
        npc_decisions={merchant_boris: DecisionResult(...)},
        body_states={"player": NPCState(...)},
        ...
    )
    ↓
    Compatibility check: SPEAK alone on body "player" → no conflicts
    Vital state: "player" alive, conscious
    → AuthorizedExecutions = [
        AuthorizedExecution(body_id="player", intention=AvatarIntention(SPEAK),
                            materialization_kind=SPEAK, execution_id="tick:N:avatar_orm:0")
      ]
    ↓
Phase 6: Materialization
    AvatarIntentionMaterializer.materialize(execution) →
        CommunicationIntent(speaker="avatar_orm", audience="merchant_boris",
                            topic="trade_food", intent_type="request_service",
                            exposure_level=whisper)
    ↓
    IntentEventAdapter.to_event(intent) → EventDTO.create(
        event_type=NPC_SPOKE, source="avatar_orm",
        payload={target_id="merchant_boris", intent_type="request_service", ...},
        visibility="whisper"
    )
    ↓
Phase 7-8: subscribers process event
    ClaimEventSubscriber.on_npc_spoke: speaker="avatar_orm", target="merchant_boris"
        → Proposition(speaker_id="avatar_orm", predicate=REQUESTED, object_id="merchant_boris")
        → EpistemicRecord(agent_id="merchant_boris", proposition=...)
    dialogue_memory_subscriber: writes to narrative_cache (npc_id="player", owner_id="avatar_orm")
    ↓
Phase 10: Atomic Commit → WORLD TRUTH
    Event: NPC_SPOKE(source="avatar_orm", target="merchant_boris", ...)
    State delta: merchant_boris.Intent updated (request received)
```

### 10.2. Сценарий 2: Player командует — Avatar принимает команду

**Preconditions:**
- Player turn: Player подаёт "approach merchant_boris and ask about sword".
- Avatar values: {loyalty_to_player: medium, curiosity: high}.

**Causal trace:**
```text
[run_turn call]
    ↓
_player_turn_in_flight.add(campaign_id)  [ADR-O-407]
    ↓
TurnPipeline.execute → InterventionEvent(source="player", payload={...})
    ↓
Phase 1.5: Avatar Initiative → SKIPPED (player_turn in flight, §6.4)
    ↓
Phase 1: Input Merge + WillpowerGate
    intent_pressure = resolve_intent_pressure(intent)
        → identity_deviation=0.1, social_exposure=0.2 (low pressure, friendly command)
    resonance = scan_affective_resonance(intent, ...)
    distorted_pressure = distort_pressure(pressure, resonance, psyche)
    will_response = compute_willpower(distorted_pressure, psyche)
        → state=COMPLY, resistance=0.1
    ↓
    COMPLY branch → publish_player_intent(ctx, intent)
        → EventDTO(source="player", event_type=PLAYER_INTERACTS, payload={...})
    ↓
Phase 5: NPC Decision
    merchant_boris: DecisionHub.compute (видит PLAYER_INTERACTS event)
        → intent=TRADE, intent_target="player"
    ↓
Phase 5.5: Body Arbitration
    BodyArbiter.resolve(
        player_intent=InterventionEvent(source="player", ...),
        avatar_intentions=[],  # Avatar Initiative skipped
        npc_decisions={merchant_boris: DecisionResult(TRADE, target=player)},
        ...
    )
    ↓
    Compatibility: player_intent (MOVE+SPEAK toward merchant) on body "player" → ok
    Avatar intention: none
    → AuthorizedExecutions = [
        AuthorizedExecution(body_id="player", intention=player_intent,
                            materialization_kind=PLAYER_INTERACTS, ...)
      ]
    ↓
Phase 6: Materialization
    player_intent уже опубликован в Phase 1 (publish_player_intent).
    AvatarIntentionMaterializer не вызывается (нет Avatar intentions).
    IntentEventAdapter для NPC CommunicationIntent (merchant_boris TRADE).
    ↓
Phase 10: WORLD TRUTH
    Events: PLAYER_INTERACTS (source="player"), NPC_SPOKE (source="merchant_boris")
```

### 10.3. Сценарий 3: Player и Avatar хотят противоположного

**Preconditions:**
- Idle tick.
- Avatar видит NPC "bandit_raider" с knife, ранее ранил Avatar (trauma_markers={"raider_attack"}).
- Player подаёт "attack bandit_raider" через REST (что активирует run_turn).
- Avatar values: {survival: high, courage: low}, trauma markers повышают fear.

**Causal trace (within run_turn):**
```text
[run_turn call]
    ↓
_player_turn_in_flight.add(campaign_id)
    ↓
InterventionEvent(source="player", action="attack", target="bandit_raider")
    ↓
Phase 1.5: SKIPPED (player_turn in flight)
    ↓
Phase 1: WillpowerGate
    intent_pressure = resolve_intent_pressure(attack intent)
        → violence=0.8, self_risk=0.7 (raider armed)
    psyche = avatar_state.psyche (fear=0.8 due to trauma, aggression=0.2, identity_rigidity=0.5)
    trauma bonus: identity_rigidity + 0.1 (1 trauma) = 0.6
    resistance = 0.8 × 0.6 + 0.7 × 0.8 + ... = high
    → state=REFUSE, resistance=0.85
    ↓
    REFUSE branch → player_intent BLOCKED
        → DeltaBuffer.append(WILL_CONFLICT)
        → shared_context[counter_offer_text="Убежать..."]
    ↓
Phase 5.5: Body Arbitration
    BodyArbiter.resolve(
        player_intent=None,  # blocked by WillpowerGate
        avatar_intentions=[],  # Phase 1.5 skipped
        ...
    )
    → AuthorizedExecutions = [] (no body action this tick)
    ↓
Phase 10: WORLD TRUTH
    Events: WILL_CONFLICT (no body action)
    shared_context has counter_offer for frontend
```

**Cross-tick scenario (Avatar counter-initiative next idle tick):**
```text
[idle_tick next tick, after player_turn completed]
    ↓
Phase 1.5: Avatar Initiative
    AvatarInitiativeEngine.compute:
        drives.fear=0.85 (amplified by trauma)
        desire_score for AVOID (flee bandit_raider):
            0.85 × 0.9 (belief: raider dangerous) × 0.95 (close) × 0.9 (survival-aligned) × 0.9 = 0.59
        desire_score for DEFEND (stand ground):
            0.85 × 0.3 (low self-efficacy belief) × 0.5 (no weapon) × 0.4 (courage low) = 0.051
        → AvatarDesire(kind=AVOID, target="bandit_raider", urgency=0.59)
    IntentionSynthesizer:
        candidate: FLEE from bandit_raider
        feasibility: 0.9 (escape route available)
        → AvatarIntention(action_class=FLEE, target="bandit_raider", priority=0.59)
    ↓
Phase 5.5: BodyArbiter → AUTHORIZE (no conflicts)
Phase 6: Materialization → MovementIntent(actor_id="player", target=furthest_node)
    ↓
Phase 10: WORLD TRUTH
    Events: NPC_MOVED (source="avatar_orm", body="player", target_node=exit)
```

### 10.4. Сценарий 4: Avatar хочет действовать — Player активно противодействует

**Preconditions:**
- Idle tick N: Avatar формирует AvatarIntention(FLEE, target="bandit_raider").
- BodyArbiter authorizes → Avatar начинает FLEE (MovementIntent created).
- Mid-tick (between idle_ticks): Player подаёт "move toward bandit_raider" через run_turn.

**Causal trace:**
```text
[idle_tick N]
    Phase 1.5: AvatarIntention(FLEE) created
    Phase 5.5: BodyArbiter AUTHORIZE
    Phase 6: Materialization → MovementIntent (start traversal)
        → TraversalState(status=PENDING, source=current, target=exit,
                         started_tick=N, duration_ticks=2)
    Phase 10: WORLD TRUTH — traversal started
    ↓
[run_turn called between ticks]
    _player_turn_in_flight.add
    InterventionEvent(source="player", action="move", target="bandit_raider")
    ↓
    Phase 1: WillpowerGate
        intent_pressure: identity_deviation=0.6 (counter to active flee),
                         self_risk=0.7 (toward raider)
        psyche: fear=0.85 (still high), trauma bonus
        resistance: high
        → state=REFUSE
        player_intent BLOCKED
    ↓
    Phase 5.5: BodyArbiter
        player_intent=None (blocked)
        avatar_intentions=[] (Phase 1.5 skipped during run_turn)
        system_intentions=[Traversal(player→exit, status=MOVING)]
        → Traversal in MOVING status → occupies Body (§6.6 rule 5)
        → AuthorizedExecutions = []
    ↓
    Phase 10: WORLD TRUTH — traversal continues, player action blocked
    Response: ChatTurnResponse "Avatar refusing, fleeing instead"
```

### 10.5. Сценарий 5: Оба субъекта формируют совместимые намерения

**Preconditions:**
- Idle tick.
- Player дал команду в предыдущем тике "approach merchant_boris" — Avatar COMPLY, начал APPROACH.
- Сейчас idle tick, traversal завершён, Avatar рядом с merchant.
- Player бездействует (пока думает, что сказать).
- Avatar sees opportunity (merchant has food, Avatar hungry).

**Causal trace:**
```text
[idle_tick]
    Phase 1: player_intent=None (no new intervention)
    ↓
    Phase 1.5: Avatar Initiative
        drives.desire=0.7 (hungry)
        beliefs: merchant has food (conf=0.8)
        opportunities: merchant in range, available
        → AvatarDesire(kind=ACQUIRE, target="merchant_boris")
        → AvatarIntention(action_class=SPEAK, target="merchant_boris",
                          parameters={topic="trade_food"})
    ↓
    Phase 5.5: BodyArbiter
        player_intent=None
        avatar_intentions=[SPEAK]
        → AUTHORIZE SPEAK
    ↓
    Phase 6: Materialization → NPC_SPOKE(source="avatar_orm", target="merchant_boris")
```

**Cross-tick: Player joins with own SPEAK**
```text
[next tick: run_turn called with "ask merchant about sword"]
    _player_turn_in_flight
    ↓
    Phase 1: WillpowerGate
        intent_pressure: identity_deviation=0.1, social_exposure=0.2 (low pressure)
        → COMPLY
    publish_player_intent → EventDTO(source="player", event_type=PLAYER_INTERACTS,
                                      payload={action="ask", target="merchant_boris"})
    ↓
    Phase 5.5: BodyArbiter
        player_intent=InterventionEvent(source="player", action="ask")
        avatar_intentions=[] (Phase 1.5 skipped)
        → AUTHORIZE player_intent
    ↓
    Phase 10: WORLD TRUTH — Player asked about sword, merchant responds
```

**Result:** Avatar spoke first (idle tick), Player spoke second (run_turn). Both events in world truth. Merchant has both in memory.

### 10.6. Сценарий 6: Avatar хочет физически действовать, но Body недоступно

**Preconditions:**
- Avatar Body HP=0 (dead), state=DEAD.
- Idle tick.

**Causal trace:**
```text
[idle_tick]
    Phase 1.5: Avatar Initiative
        AvatarInitiativeEngine.compute:
            avatar_state.body_state=DEAD, but psyche fields intact
            drives.desire=0.6 (still wants food)
            beliefs: merchant has food
            → AvatarDesire(kind=ACQUIRE, target="merchant_boris", urgency=0.242)
        IntentionSynthesizer:
            candidate: SPEAK
            feasibility: 0.0 (body dead, cannot speak)
            → candidate feasibility=0 → not selected
            Alternative candidates:
                OBSERVE: feasibility=0.5 (perception impaired but not zero)
                → AvatarIntention(action_class=OBSERVE, target="merchant_boris",
                                  priority=0.1)
    ↓
    Phase 5.5: BodyArbiter
        evaluate_vital_state(body_state) → DEAD
        → All physical action_class intentions REJECTED with reason "body_unavailable:dead"
        OBSERVE intention: AUTHORIZE (it's not physical action, only perception)
        → AuthorizedExecutions = [
            AuthorizedExecution(body_id="player", intention=OBSERVE,
                                materialization_kind=PERCEPTION_ONLY)
          ]
        Rejections: [SPEAK rejected, reason=body_unavailable:dead]
    ↓
    AvatarInitiativeEngine receives REJECTED callback:
        Memory: write EventMemory(owner_id="avatar_orm", type=intention_outcome,
                                  content="wanted to speak to merchant, body dead")
        Belief: EpistemicRecord(agent_id="avatar_orm",
                                proposition=("avatar_orm", CANNOT_ACT, "merchant_boris"))
        Affective: integrate_affective_pressure(frustration=0.5)
    ↓
Phase 10: WORLD TRUTH — no body action, but Avatar internal state updated
```

### 10.7. Сценарий 7: Во время исполнения возникает внешнее прерывание

**Preconditions:**
- Avatar initiated ATTACK NPC "bandit_raider" (windup PENDING, started_tick=N, duration=2).
- Tick N+1: NPC "bandit_ally" attacks Avatar from behind → ImpactEngine damages Avatar Body.
- Avatar HP drops to 1 (almost dead).

**Causal trace:**
```text
[idle_tick N]
    Phase 1.5: AvatarIntention(ATTACK, target="bandit_raider")
    Phase 5.5: BodyArbiter → AUTHORIZE
    Phase 6: Materialization → ActionWindup(actor_id="player",
                                            action_type="attack",
                                            started_tick=N, duration_ticks=2,
                                            status=PENDING, held_intent=...)
    ↓
[idle_tick N+1]
    Phase 0.75: Traversal lifecycle (movement)
    Phase 1: WillpowerGate (no player input)
    Phase 1.5: Avatar Initiative — Avatar sees new threat (bandit_ally attacking)
        drives.fear=0.95 (HP critical)
        → AvatarDesire(kind=DEFEND, target="bandit_ally", urgency=0.8)
        → AvatarIntention(action_class=DEFEND, target="bandit_ally",
                          supersedes=None)  # cannot supersede EXECUTING windup
    Phase 5: NPC Decision — bandit_ally DecisionHub → ATTACK intent_target="player"
    Phase 5.5: BodyArbiter
        player_intent=None
        avatar_intentions=[DEFEND]
        system_intentions=[Windup(player→bandit_raider, status=PENDING, tick_remaining=1)]
        npc_decisions={bandit_ally: DecisionResult(ATTACK, target="player")}
    ↓
    Conflict resolution:
        - DEFEND vs active ATTACK windup: INCOMPATIBLE
        - Active windup occupies Body (§6.6 rule 2) → DEFEND DEFERRED until windup completes
        - bandit_ally ATTACK on Avatar Body → external event, will process in Phase 8
    → AuthorizedExecutions = [
        AuthorizedExecution(body_id="player", intention=Windup(ATTACK continuation),
                            materialization_kind=WINDUP_CONTINUE)
      ]
    Rejections: []
    Deferrals: [DEFEND deferred until tick N+2]
    ↓
Phase 7: Windup Execution Gate
    windup for player→bandit_raider: tick_remaining=1, not yet complete
    status stays PENDING
    ↓
Phase 8: CombatSubscriber processes bandit_ally ACTOR_ATTACKS event
    ImpactEngine.apply_damage(avatar_body, damage=15)
    avatar_state.body_state.HP = 1 (critical)
    ↓
Phase 9.1: Affective Pipeline
    affective_integrator: panic, fear spike
    ↓
Phase 10: WORLD TRUTH
    Avatar HP=1, trauma_markers updated, DEFEND intention deferred to tick N+2
```

**Tick N+2:**
- Windup completes (status=COMPLETED) → ACTOR_ATTACKS event published (player→bandit_raider).
- DEFEND intention re-queued (was DEFERRED).
- BodyArbiter: DEFEND now AUTHORIZE (windup completed).
- Avatar tries to defend against bandit_ally.

### 10.8. Сценарий 8: Одно намерение создаёт несколько событий-последствий

**Preconditions:**
- Avatar AUTHORIZE AvatarIntention(SPEAK, target="merchant_boris", parameters={intent_type="accuse", topic="stolen_goods"}).
- merchant_boris in crowd of NPCs (3 bystanders in hearing range).

**Causal trace:**
```text
[Phase 6: Materialization]
    AvatarIntentionMaterializer → CommunicationIntent(
        speaker="avatar_orm", audience="merchant_boris",
        topic="stolen_goods", intent_type="accuse",
        exposure_level=normal
    )
    ↓
    IntentEventAdapter.to_event(intent) → EventDTO.create(
        event_type=NPC_SPOKE, source="avatar_orm",
        payload={target_id="merchant_boris", intent_type="accuse",
                 proposition=Proposition(subject_id="merchant_boris",
                                         predicate=STOLE, object_id="unknown")},
        visibility="public", radius=normal_speech_radius
    )
    ↓
[Phase 8: Layered Reduction — subscribers]
    Event published once, but multiple subscribers process it:
    
    1. ClaimEventSubscriber.on_npc_spoke(event):
       speaker="avatar_orm", target="merchant_boris"
       → Proposition(speaker_id="avatar_orm", predicate=ACCUSED, object_id="merchant_boris")
       → BeliefRevisionEngine.revise(listener_id="merchant_boris", claim=..., ...)
       → EpistemicRecord(agent_id="merchant_boris", proposition=("avatar_orm", ACCUSED, "merchant_boris"))
    
    2. perception_filter.filter_perceiving_npcs:
       Returns [merchant_boris, npc_bystander_1, npc_bystander_2, npc_bystander_3]
       (all within radius)
    
    3. For each bystander NPC:
       ClaimEventSubscriber processes (if can_address)
       → EpistemicRecord(agent_id=bystander_N, proposition=("avatar_orm", ACCUSED, "merchant_boris"))
       → Memory write per bystander
    
    4. dialogue_memory_subscriber:
       speaker="avatar_orm", listener="merchant_boris"
       affected_npcs = {avatar_orm, merchant_boris}
       → narrative_cache write for both
    
    5. NpcDialogueSubscriber (S388 symmetry):
       PLAYER_SPOKE not triggered (event_type=NPC_SPOKE, source=avatar_orm)
       NPC_SPOKE handler triggers for relevant NPCs
    
    6. social/propagation.py:
       ACTOR_ATTACKS check: source != "player" (it's "avatar_orm")
       → no special propagation (only player attacks get certain treatment)
       [NOTE: this may need extension — Avatar accusations should propagate
        socially similar to NPC-NPC accusations, not Player-accusations]
    
    7. Affective Pipeline:
       affective_integrator integrates Avatar's own speech (self-emotion update)
       → Avatar emotion state updated (anger, assertiveness)
    
    8. faction_tracker (if Avatar accuses member of faction):
       ActionConsequenceCompiler.process_action — but this is for PlayerAction,
       not AvatarIntention. [GAP: need extension to process AvatarIntention]
       [PROPOSED: extend ActionConsequenceCompiler or create parallel
        AvatarActionConsequenceCompiler]
    ↓
[Phase 9: Integration]
    CFRM P2: LocalCausalSolver processes Avatar's action causally
    → updates relationship_store (avatar_orm ↔ merchant_boris, avatar_orm ↔ bystanders)
    Belief Crystallization: 
    → merchant_boris belief about avatar_orm crystallizes (e.g., "avatar_orm accuses me")
    → bystanders belief: "avatar_orm accused merchant_boris of theft"
    ↓
[Phase 10: WORLD TRUTH — multiple events emitted from one intention]
    Events published:
      1. NPC_SPOKE (source="avatar_orm", target="merchant_boris") — primary speech event
      2. COMMUNICATION_CLAIM (source="avatar_orm", proposition=ACCUSED) — derived claim
    State changes:
      - merchant_boris NPCState: relationship to avatar_orm changed
      - bystanders NPCState: beliefs updated
      - avatar_orm NPCState: emotion updated (anger +0.1)
      - faction_tracker (if applicable): merchant_boris faction -10
      - EpistemicStore: 4 new records (merchant + 3 bystanders)
      - narrative_cache: 2 new entries (speaker + listener)
```

**Key observation:** One AvatarIntention → one CommunicationIntent → one EventDTO → multiple subscriber effects. This is by design (Phase 8 layered reduction). AvatarIntention does not need to know about subscribers — it produces one intention, materialization produces one event, subscribers fan out.

---

## §11. СРАВНЕНИЕ АРХИТЕКТУРНЫХ АЛЬТЕРНАТИВ

### 11.1. Альтернативы для Avatar Initiative

**A. BDI-подобная модель с гибридным переиспользованием (РЕКОМЕНДУЕМАЯ)**

- Описание: явные слои Beliefs → Desires → Intentions, переиспользование DriveResolver / EpistemicStore / affective_integrator, новый DesireSynthesizer + IntentionSynthesizer.
- Соответствие коду: высокое (переиспользует VERIFIED механизмы)
- Выразительность: высокая (разные личности через разные drives/values/profiles)
- Автономная инициатива: да (полный цикл от восприятия к намерению)
- Поддержка разных личностей: да (CharacterProfile-driven)
- Устойчивость к повторению: средняя (зависит от формулы desire_score — при одинаковых inputs → одинаковые outputs; разнообразие через satiation/drift)
- Детерминированность: да (pure functions, ADR-O-351)
- Стоимость вычислений: средняя (1 extra phase per tick, ~5-10ms estimated)
- Сложность сохранения состояния: средняя (AvatarIntentionRegistry — mirror of WindupRegistry pattern)
- Расширяемость: высокая (новые ActionClass values, новые DesireKind values)
- **СТОИМОСТЬ МИГРАЦИИ: низкая** (новый модуль, не трогает существующие)
- **ВЛИЯНИЕ НА PIPELINE: вставка Phase 1.5 (idle tick only)**
- **РИСК ДУБЛИРОВАНИЯ: средний** (DesireSynthesizer может частично дублировать DecisionHub scoring; митигация: явное разделение — DesireSynthesizer для Avatar only, DecisionHub для NPC only)

**B. Extension of DecisionHub for Avatar**

- Описание: добавить ветку `if npc_id == "player" and is_avatar_character(...) → Avatar path` внутри DecisionHub.compute, обходя INV-PLAYER-AUTHORSHIP через специальный marker.
- Соответствие коду: высокое (один движок для всех)
- Выразительность: средняя (DecisionHub заточен под NPC scoring, не Avatar agency)
- Автономная инициатива: ограниченная (нужно строить "desire formation" внутри DecisionHub)
- Поддержка разных личностей: средняя
- Устойчивость к повторению: низкая (если NPC и Avatar разделяют scoring logic, сложно настроить разную динамику)
- Детерминированность: да
- Стоимость вычислений: средняя
- Сложность сохранения состояния: низкая (existing state)
- Расширяемость: низкая (DecisionHub уже 20+ параметров)
- **СТОИМОСТЬ МИГРАЦИИ: высокая** (изменение core DecisionHub, нарушение INV-PLAYER-AUTHORSHIP guard)
- **ВЛИЯНИЕ НА PIPELINE: высокое** (изменение Phase 5)
- **РИСК ДУБЛИРОВАНИЯ: низкий**
- **REJECTED:** нарушает INV-PLAYER-AUTHORSHIP (явный guard line 327); §ENIGMA-001 (увеличивает ли количество устойчивых причинных структур? — нет, только переиспользует существующую)

**C. Scenario-driven Avatar (scripted reactions)**

- Описание: Avatar behaviour как набор scripted reactions (`if fear > 0.8: retreat()`), без формальной модели агентности.
- Соответствие коду: низкое (новый scripting layer)
- Выразительность: низкая (ограничено scripted scenarios)
- Автономная инициатива: нет (только реакции)
- Поддержка разных личностей: низкая (нужен отдельный скрипт под каждую)
- Устойчивость к повторению: низкая (детерминированные scripts → repetitive)
- Детерминированность: да
- Стоимость вычислений: низкая
- Сложность сохранения состояния: низкая
- Расширяемость: низкая (каждая новая реакция = новый script)
- **СТОИМОСТЬ МИГРАЦИИ: низкая**
- **ВЛИЯНИЕ НА PIPELINE: низкое**
- **РИСК ДУБЛИРОВАНИЯ: высокий**
- **REJECTED:** явный запрет в R5.1 §2.4 («не проектировать систему в виде набора фиксированных реакций»)

### 11.2. Альтернативы для Body Action Arbitration

**A. New BodyArbiter component (РЕКОМЕНДУЕМАЯ)**

- Описание: новый компонент `BodyArbiter` в Phase 5.5, принимает все намерения, возвращает AuthorizedExecutions.
- Соответствие коду: среднее (новая фаза, но не меняет существующие)
- Детерминизм: явный (pure function)
- Тестируемость: высокая (отдельный компонент, можно unit-test)
- Сложность: средняя (compatibility table + conflict resolution rules)
- Атомарность: явная (единственная точка authorization)
- **СТОИМОСТЬ МИГРАЦИИ: низкая** (новая фаза, не трогает существующие)
- **ВЛИЯНИЕ НА PIPELINE: вставка Phase 5.5**
- **РИСК ДУБЛИРОВАНИЯ: низкий**

**B. Extension of WindupWriteGate**

- Описание: расширить WindupWriteGate (Phase 6) до полного arbiter — все intentions проходят через windup-like FSM.
- Соответствие коду: высокое (extend existing)
- Детерминизм: да
- Тестируемость: средняя (existing gate tested, extensions need test)
- Сложность: высокая (windup FSM заточен под windowed actions, не arbitrary intentions)
- Атомарность: средняя (gate only on Phase 6, doesn't cover Phase 1 player input)
- **СТОИМОСТЬ МИГРАЦИИ: высокая** (semantic overload of Windup concept)
- **ВЛИЯНИЕ НА PIPELINE: изменение Phase 6**
- **РИСК ДУБЛИРОВАНИЯ: средний**
- **REJECTED:** Windup concept семантически specialised (windowed attack/steal with duration). Применение к arbitrary intentions разрушает single-responsibility.

**C. Phase-order serialization (do nothing)**

- Описание: оставить неявную сериализацию через фазовый порядок.
- Соответствие коду: высокое (no change)
- Детерминизм: да
- Тестируемость: низкая (implicit behavior)
- Сложность: —
- Атомарность: implicit (через single-threaded execute)
- **СТОИМОСТЬ МИГРАЦИИ: 0**
- **ВЛИЯНИЕ НА PIPELINE: 0**
- **РИСК ДУБЛИРОВАНИЯ: 0**
- **REJECTED:** явный запрет в R5.1 §4.2 («не выводить атомарность из единственной точки входа TickOrchestrator»). Не даёт ответа «кто выиграл» при конфликте.

### 11.3. Рекомендуемый итог

- Avatar Initiative → **Альтернатива A** (BDI-подобная с гибридным переиспользованием).
- Body Arbitration → **Альтернатива A** (новый BodyArbiter).

**Критерий выбора (R5.1 §9):** способность поддерживать независимую агентность двух субъектов и единое физическое исполнение. Альтернативы A в обоих случаях максимизируют этот критерий при минимальной стоимости миграции и минимальном риске дублирования.

---

## §12. КАРТА ЗАТРАГИВАЕМЫХ ФАЙЛОВ

### 12.1. Новые файлы (PROPOSED)

| Файл | Назначение |
|---|---|
| `backend/app/domain/avatar_intention.py` | Контракт `AvatarIntention`, `AvatarIntentionCandidate`, `AvatarDesire`, `ActionClass`, `DesireKind`, `AvatarIntentionState` |
| `backend/app/services/avatar/avatar_initiative_engine.py` | `AvatarInitiativeEngine.compute(...)` — полный цикл агентности |
| `backend/app/services/avatar/desire_synthesizer.py` | `DesireSynthesizer` — desire formation (drive × belief × value) |
| `backend/app/services/avatar/intention_synthesizer.py` | `IntentionSynthesizer` — intention candidate selection |
| `backend/app/services/avatar/avatar_intention_registry.py` | `AvatarIntentionRegistry` — state machine, persistence |
| `backend/app/services/avatar/avatar_intention_materializer.py` | `AvatarIntentionMaterializer.materialize(execution) → MaterializationResult` |
| `backend/app/services/avatar/avatar_character_registry.py` | `AvatarCharacterRegistry` — character_id ↔ body_id mapping (1:1 MVP) |
| `backend/app/services/body/body_arbiter.py` | `BodyArbiter.resolve(...)` — арбитраж намерений |
| `backend/app/services/body/compatibility_table.py` | `BodyArbiter._physical_compatibility` data |
| `backend/app/services/phases/avatar_initiative.py` | `run_phase_1_5_avatar_initiative(ctx)` — Phase 1.5 wrapper |
| `backend/app/services/phases/body_arbitration.py` | `run_phase_5_5_body_arbitration(ctx)` — Phase 5.5 wrapper |
| `backend/tests/micro/test_avatar_intention_lifecycle.py` | FSM tests: PROPOSED→AUTHORIZED→EXECUTING→terminal |
| `backend/tests/micro/test_body_arbiter_conflicts.py` | Конфликтные сценарии A-G |
| `backend/tests/micro/test_avatar_authorship_invariant.py` | INV-AVATAR-AUTHORSHIP guard test |

### 12.2. Расширяемые файлы (PROPOSED)

| Файл | Что меняется | Риск |
|---|---|---|
| `backend/app/domain/control_source.py` | Добавить `AVATAR_INITIATIVE` enum value, `is_avatar_character()` helper, `AvatarCharacterRegistry` lookup | низкий — additive |
| `backend/app/services/events/intent_event_adapter.py` | Guard: `intent.speaker` matches `is_avatar_character` → проверка `npc_id == speaker` (INV-AVATAR-AUTHORSHIP) | средний — новый guard, может сломать существующие тесты |
| `backend/app/services/events/claim_event_subscriber.py` | `getattr(event, "source", "player")` fallback → `getattr(event, "source", None)` + явная обработка `source=None` | низкий — edge case |
| `backend/app/services/game_loop/tick_orchestrator.py` | В `_run_core_phases`: вставить `_phase_1_5_avatar_initiative(ctx)` между Phase 1 и Phase 2, `_phase_5_5_body_arbitration(ctx)` между Phase 5 и Phase 6 | средний — фазовая машина расширена, но существующие фазы не изменены |
| `backend/app/services/memory/memory_models.py` | `EventMemory.owner_id` field (default = npc_id) | низкий — additive |
| `backend/app/services/memory/memory_manager.py` | Read path принимает optional `owner_id` filter | низкий |
| `backend/app/domain/epistemology.py` | `EpistemicRecord.agent_id` формат: `"avatar:{character_id}"`, `"player:{player_name}"` (миграция существующих `"player"` → `"player:{name}"`) | ВЫСОКИЙ — миграция данных |
| `backend/app/services/player_avatar_service.py` | Убрать value coupling `npc_id != player_name: return None` (line 138). Использовать `AvatarCharacterRegistry` lookup вместо hardcoded equality | средний — semantic change |
| `backend/app/services/game_loop/turn_pipeline.py` | `_avatar_dict["npc_id"] = "player"; _avatar_dict["id"] = "player"` (line 229-230) — оставить, но через `AvatarCharacterRegistry` | низкий |
| `backend/app/services/phases/post_decision.py` | Windup handling расширяется: обрабатывать `AvatarIntentionRegistry` state transitions AUTHORIZED → EXECUTING → terminal (mirror WindupRegistry) | средний |
| `backend/app/services/events/event_types.py` | Нет новых EventType (NPC_SPOKE переиспользуется для Avatar speech; ACTOR_ATTACKS для Avatar attacks) | 0 |

### 12.3. НЕ трогаемые файлы (VERIFIED — preserved invariants)

| Файл | Почему не трогать |
|---|---|
| `backend/app/services/will.py` | WillpowerGate сохраняет ответственность: реактивное сопротивление Player input. Не становится arbiter. |
| `backend/app/services/npc/decision_hub.py` | INV-PLAYER-AUTHORSHIP guard (line 327) не модифицируется. Avatar не использует DecisionHub. |
| `backend/app/services/npc/npc_tick_pipeline.py` | NPC pipeline не модифицируется. Avatar intentions идут через отдельный path. |
| `backend/app/services/character/character_filter.py` | CharacterFilter остаётся фильтром Player actions, не источником Avatar инициативы. |
| `backend/app/services/game_loop/game_loop.py` (core) | `_player_turn_in_flight` time-gate не трогается. |
| `backend/app/domain/action_windup.py` | Windup concept не перегружается. AvatarIntentionRegistry — отдельный parallel registry. |
| `backend/app/domain/action_commitment.py` | FSM используется как reference, не как storage для AvatarIntentions. |
| `backend/app/services/events/event_identity.py` | Single Writer pattern не трогается. Avatar events получают event_id через тот же mechanism. |

### 12.4. Файлы frontend (PROPOSED — отдельный трек)

UI для отображения Avatar инициативы — отдельный трек (прецедент ADR-O-435 standalone UI). R5.1 НЕ предписывает виджет, но требует:
- Фронтенд должен различать `event.source == "player"` (Player action) vs `event.source == "{character_id}"` (Avatar action) — разные визуальные представления.
- Avatar-authored NPC_SPOKE events → отображаются как речь Avatar (не Player).
- Will_CONFLICT events продолжают отображаться через существующий Resistance Medium.

---

## §13. ПОРЯДОК БУДУЩЕЙ РЕАЛИЗАЦИИ

### 13.1. Этапы (PROPOSED)

Реализация R5.1 — отдельный multi-commit track, не единичный коммит. Рекомендуемый порядок (зависимости → вперёд):

**Этап 0: Подготовка реестров (foundation)**
- `AvatarCharacterRegistry` — character_id ↔ body_id mapping (MVP: 1:1 with `body_id="player"`)
- Миграция `EpistemicRecord.agent_id` формата: `"player"` → `"player:{player_name}"` (миграция данных, осторожно)
- `EventMemory.owner_id` field + migration
- Тесты: storage round-trip, migration idempotency

**Этап 1: Расширение ControlSource**
- `control_source.py`: добавить `AVATAR_INITIATIVE`, `is_avatar_character()` helper
- INV-AVATAR-AUTHORSHIP guard в `IntentEventAdapter`
- Тесты: NPC impersonation rejection, Avatar identification

**Этап 2: Контракты намерений**
- `avatar_intention.py`: `AvatarIntention`, `AvatarIntentionCandidate`, `AvatarDesire`, `ActionClass`, `DesireKind`
- `AvatarIntentionRegistry` — state machine + persistence
- Тесты: FSM transitions, immutability, idempotency

**Этап 3: AvatarInitiativeEngine**
- `desire_synthesizer.py`: формула desire_score
- `intention_synthesizer.py`: candidate selection
- `avatar_initiative_engine.py`: full compute cycle
- Тесты: desire formation от inputs, intention selection, нет hardcoded thresholds

**Этап 4: BodyArbiter**
- `compatibility_table.py`: ActionClass × ActionClass matrix
- `body_arbiter.py`: resolve function, conflict rules A-G
- Тесты: 8 интеграционных сценариев §10

**Этап 5: Materialization**
- `avatar_intention_materializer.py`: ActionClass → CommunicationIntent / MovementIntent
- Расширение `post_decision.py`: AvatarIntentionRegistry state transitions
- Тесты: end-to-end Phase 1.5 → 5.5 → 6 → 7

**Этап 6: Phase integration**
- `phases/avatar_initiative.py`: `run_phase_1_5_avatar_initiative`
- `phases/body_arbitration.py`: `run_phase_5_5_body_arbitration`
- Расширение `tick_orchestrator._run_core_phases`: вставка новых фаз
- Тесты: regression IPT 54/0/0 сохранён, replay determinism

**Этап 7: willpower gate cleanup (gap fix)**
- `claim_event_subscriber.py:108` — fallback cleanup
- `player_avatar_service.py:138` — value coupling removal
- Тесты: existing Player path green

**Этап 8: End-to-end integration**
- 8 интеграционных сценариев §10 как pytest (headless)
- ADR-O-351 replay determinism: full tick replay → same AvatarIntention sequence
- ADR-O-407 time-gate preserved: idle_tick + run_turn separation

### 13.2. Зависимости между этапами

```text
Этап 0 ────┐
           ↓
Этап 1 ────┴─→ Этап 2 ──→ Этап 3 ──┐
                                   ↓
                                  Этап 4 ──→ Этап 5 ──→ Этап 6 ──→ Этап 7 ──→ Этап 8
                                                                              ↑
                                                                              regression gate
```

- Этапы 0 и 1 — independent track, могут идти параллельно.
- Этап 2 требует 0 и 1 (registry + ControlSource).
- Этап 3 требует 2 (контракты намерений).
- Этап 4 требует 2 (контракты) — может идти параллельно с 3.
- Этап 5 требует 3 и 4.
- Этап 6 требует 5.
- Этап 7 — gap-fix, можно делать в любой момент после 0.
- Этап 8 — финальная приёмка.

### 13.3. Минимальный первый коммит (MVP slice)

Если Мастер хочет минимальный первый шаг:
- **Этап 0 + Этап 1 + Этап 2 (без engine)** — контракты и registry готовы, но `AvatarInitiativeEngine.compute` возвращает пустой tuple.
- Это даёт: расширенный ControlSource, фикс value coupling, stub registry. Production behaviour не меняется (нет Avatar intentions).
- Затем Этапы 3-6 — actual Avatar Initiative, manageable commits.

### 13.4. Гейты между этапами

| Переход | Stop-criteria |
|---|---|
| 0 → 1 | `EpistemicRecord.agent_id` миграция зелёная; `EventMemory.owner_id` field added; existing tests green |
| 1 → 2 | `INV-AVATAR-AUTHORSHIP` guard test green; ControlSource enum extended; NPC impersonation rejected |
| 2 → 3 | `AvatarIntentionRegistry` FSM tests green; immutability tests green |
| 3 → 4 | `AvatarInitiativeEngine.compute` produces AvatarIntention from inputs; no hardcoded thresholds (grep `if .* > 0\.[0-9]` в synthesizers → 0 matches) |
| 4 → 5 | 8 интеграционных сценариев §10 (BodyArbiter.resolve) зелёные |
| 5 → 6 | `AvatarIntentionMaterializer` tests green; Phase 7 AvatarIntentionRegistry transitions green |
| 6 → 7 | `_run_core_phases` extended; IPT 54/0/0 preserved; replay determinism green |
| 7 → 8 | WillpowerGate cleanup; value coupling removed; Player path regression green |
| 8 → closed | End-to-end 8 scenarios green; ADR-O-351 replay green; ADR-O-407 preserved; ADR-O-344 preserved; INV-PLAYER-AUTHORSHIP preserved; INV-AVATAR-AUTHORSHIP new guard green |

---

## §14. ИНВАРИАНТЫ

### 14.1. Сохраняемые инварианты (VERIFIED — not violated by R5.1)

| Инвариант | Где | Как сохранён |
|---|---|---|
| **ADR-O-344** WorldTick Temporal Ownership | tick_orchestrator.py | TickOrchestrator остаётся единственным владельцем времени. Новые фазы 1.5 и 5.5 — внутри `_run_core_phases`, не отдельные execute() вызовы. |
| **ADR-O-407** Player Turn Commitment Time Gate | game_loop.py:1179 | `_player_turn_in_flight` не модифицируется. Avatar Initiative пропускается во время player turn (§6.4). |
| **ADR-O-310** Windup Execution Gate | post_decision.py | WindupRegistry не трогается. AvatarIntentionRegistry — отдельный parallel registry, не коллизует с windup. |
| **ADR-O-313** Materialization symmetry | ADR-O-313 | NPC-NPC async dialogue materialization не нарушается. Avatar materialization — extension, не замена. |
| **ADR-O-349** Intent-Event Completeness | IntentEventAdapter | AvatarIntention → CommunicationIntent → EventDTO через `AvatarIntentionMaterializer` → `IntentEventAdapter` (последний не модифицируется по core logic, только guard add). |
| **ADR-O-351** Replay Determinism | event_identity.py | Все intention_id, execution_id — детерминированные (tick:character_id:ordinal). No RNG, no wall-clock. |
| **ADR-O-365** Liveness membrane | claim_event_subscriber | Avatar dead → events to Avatar filtered (existing path). New: BodyArbiter rejects intentions to dead body. |
| **ADR-O-399** Task Worker Outbox | task_scheduler.py | TaskScheduler не трогается. Avatar Initiative — синхронная фаза, не async task. |
| **INV-PLAYER-AUTHORSHIP** | decision_hub.py:327 | Guard не модифицируется. Avatar не использует DecisionHub. |
| **INV-EVENT-CARDINALITY** | event_identity.py | Single Writer pattern сохранён. Avatar events проходят через `next_event_identity`. |
| **INV-TRAV-TERMINALITY** | ADR-O-350 | Traversal FSM не трогается. Avatar MOVE intention → MovementIntent → traversal path. |
| **§ENIGMA-001** Приоритет причинной глубины | — | R5.1 создаёт новые причинные структуры: Avatar beliefs, Avatar memory, Avatar desires, Avatar intentions. Увеличивает длину причинных цепочек (Player ↔ Avatar ↔ NPC). |
| **§ENIGMA-002** Two-Domain Rule | — | Не вводится универсальный `Intention` примитив. `AvatarIntention` — отдельный контракт, не унификация. |
| **§10.2** Body as Gate of Perception | Causal Contract v3.0 §2.4 | Body остаётся единственным способом физического восприятия. Avatar consciousness without Body → только OBSERVE (impaired). |
| **§10.3** Запреты на Волю и Давление | Causal Contract v3.0 | WillpowerGate сохраняет ответственность. BodyArbiter не вмешивается в WillpowerGate. |

### 14.2. Новые инварианты (PROPOSED)

| Инвариант | Определение | Guard |
|---|---|---|
| **INV-AVATAR-AUTHORSHIP** | Avatar-authorized actions имеют `EventDTO.source = character_id`, не `"player"`. NPC не может подделать Avatar authorship. | `IntentEventAdapter` guard: `if is_avatar_character(intent.speaker) and intent.speaker != npc_id: raise` |
| **INV-BODY-ARBITRATION** | Все физические действия на Body проходят через `BodyArbiter.resolve`. Прямые mutation Avatar Body state в обход — architectural violation. | Lint rule + runtime guard on `NPCState(npc_id="player")` writes from unauthorized modules |
| **INV-AVATAR-INTENTION-IMMUTABILITY** | `AvatarIntention` — `@dataclass(frozen=True)`. Изменение намерения = отзыв + новое с `supersedes`. | Python frozen dataclass + tests |
| **INV-INTENTION-DETERMINISM** | `(tick, character_id, ordinal) → intention_id` — pure function. Одинаковые inputs → одинаковый intention_id. | Property-based test |
| **INV-AVATAR-INITIATIVE-NO-THRESHOLDS** | В `DesireSynthesizer` и `IntentionSynthesizer` запрещены `if var > threshold: action()` patterns. Только multiplication of weights. | Lint rule (grep `if .* > 0\.[0-9]+:` в synthesizers → 0 matches) |
| **INV-AVATAR-SEPARATE-FROM-PLAYER-INPUT** | Avatar Initiative пропускается во время `_player_turn_in_flight`. Avatar не формирует автономные намерения внутри хода игрока. | Test: during run_turn, `AvatarIntentionRegistry` не получает новых entries |
| **INV-CONSCIOUSNESS-BODY-SEPARATION** | Avatar consciousness (beliefs, memory, desires) персистит при смерти Body. Body death → physical intentions REJECTED, but beliefs/memory/desires continue. | Test: kill Body → AvatarInitiativeEngine still computes desires, BodyArbiter rejects physical execution |

---

## §15. КРИТЕРИИ ПРИЁМКИ

### 15.1. Критерии закрытия R5.1 (из спецификации §11)

- [x] **Avatar способен формировать намерения без Player command** — PROPOSED контракт `AvatarInitiativeEngine.compute` формирует `AvatarIntention` без player input (Сценарий 1).
- [x] **Формирование намерений не ограничено речью** — `ActionClass` enum: SPEAK / MOVE / INTERACT_OBJECT / DEFEND / FLEE / OBSERVE / REFUSE_PLAYER / SEEK_CONTACT (8 классов).
- [x] **Механизм поддерживает разные личности Avatar** — `CharacterProfile`-driven (values, self_integrity, social_constraints, behavior_mask) + `NPCState.drives_runtime` + `affective_imprints` → разные desire_score → разные intentions.
- [x] **Желание, намерение, предложение и исполнение семантически разделены** — `AvatarDesire` (§3.3), `AvatarIntentionCandidate` (§3.4), `AvatarIntention` (§3.4), `MaterializationResult` (§7.2) — 4 отдельных контракта.
- [x] **Player и Avatar имеют независимые источники намерений** — Phase 1 (Player input) vs Phase 1.5 (Avatar Initiative) — разные фазы, разные engines, разные contracts.
- [x] **Существует общий арбитраж физического исполнения** — `BodyArbiter.resolve` принимает player_intent, avatar_intentions, npc_decisions, system_intentions → единый AuthorizedExecutions.
- [x] **Совместимые намерения могут быть обработаны корректно** — `Compatibility.COMPATIBLE` → оба AUTHORIZED (Сценарий 5).
- [x] **Несовместимые намерения не приводят к двойному исполнению** — `BodyArbiter` выбирает одно; `AvatarIntentionRegistry` state machine идемпотентный (§6.9).
- [x] **WillpowerGate сохраняет свою отдельную ответственность** — остаётся в Phase 1 (реактивное сопротивление Player input), не становится arbiter (§6.7).
- [x] **INV-PLAYER-AUTHORSHIP не нарушен** — `DecisionHub.compute` guard (line 327) не модифицируется (§8.3).
- [x] **Определены правила прерывания и невозможности исполнения** — Сценарий 7 (прерывание), Сценарий 6 (Body недоступно), §5.5 (stale).
- [x] **Определена судьба отклонённых и отложенных намерений** — REJECTED callback → AvatarInitiativeEngine обновляет desires/memory/beliefs (§5.6); DEFERRED → requeue в PROPOSED.
- [x] **Body не становится источником авторства намерения** — `EventDTO.source = source_id` (character_id для Avatar, "player" для Player), не `body_id` (§8.9).
- [x] **WORLD TRUTH остаётся единым** — все execution проходят через Phase 10 atomic commit; единственный Single Writer `event_identity.next_event_identity` (§7.4).
- [x] **Все интеграционные сценарии непротиворечивы** — 8 сценариев §10 показаны через causal traces, без противоречий (PROPOSED — final verification pending implementation).
- [x] **Установлены интерфейсы с Identity, Communication, Ceremony и Memory** — §3.7 (Memory + Beliefs), §8.4 (Identity), §7.3 (Communication), §6.4 (Ceremony / time-gate).
- [x] **Предложен безопасный порядок реализации** — §13: 8 этапов с зависимостями и stop-criteria, MVP slice (Этапы 0-2) без production behavior change.

### 15.2. Финальный вердикт

**R5.1 = B — архитектурный контракт замкнут, готов к отдельному утверждению перед реализацией.**

Все 17 критериев закрытия (§15.1) отмечены как выполненные на уровне проектирования. Каждое утверждение маркировано `VERIFIED` (доказано кодом) или `PROPOSED` (новое проектирование без кодовой опоры, готово к реализации).

**Что требует утверждения Мастера перед реализацией:**
1. **Геймдизайнерские вопросы (§16)** — 3 открытых вопроса требуют авторского решения.
2. **Приоритизация этапов (§13)** — MVP slice (Этапы 0-2) vs полный track (Этапы 0-8).
3. **Migration risk acceptance** — `EpistemicRecord.agent_id` формат migration (ВЫСОКИЙ риск в §12.2).
4. **INV-AVATAR-AUTHORSHIP new guard** — добавление нового инварианта (§14.2).

**После утверждения Мастера:** реализация через этапы §13, с гейтами §13.4 и stop-criteria §15.1.

---

## §16. ОТКРЫТЫЕ ВОПРОСЫ ДЛЯ ГЕЙМДЕЗАЙНЕРА

### 16.1. Q1 — Avatar values и Player loyalty conflict

**Вопрос:** Если Avatar values включают `loyalty_to_player`, а Player приказывает действие, противоречащее другому value Avatar (например, `courage`) — как Avatar должен реагировать?

**Контекст архитектуры:**
- `CharacterProfile.values` (ValueSet) — frozen после создания персонажа, меняются только через крупные события.
- `compute_resistance` (CharacterFilter) сегодня использует `value_conflict_score` — но это для Player actions.
- Avatar Initiative DesireSynthesizer вычисляет `value_compat` для desire kind — но это для Avatar-инициированных желаний.

**Архитектурные опции:**
- **A.** `loyalty_to_player` — override value, всегда доминирует над другими. Player command → Avatar COMPLY (кроме случаев крайнего self-harm).
- **B.** `loyalty_to_player` — один из values, участвует в формуле desire_score на равных. Если `courage` сильнее → Avatar может RESIST.
- **C.** `loyalty_to_player` — модификатор WillpowerGate (понижает resistance к Player commands), но не override.

**Рекомендация Архитектора:** B — `loyalty_to_player` один из values, без override. Это позволяет разным Avatars реагировать по-разному (преданный паладин vs свободный бард).

**Геймдизайнер должен решить:** какой option соответствует авторскому замыслу Avatar consciousness.

### 16.2. Q2 — Avatar Initiative frequency

**Вопрос:** Как часто Avatar должен формировать автономные намерения?

**Контекст архитектуры:**
- R5.1 §2.4 запрещает arbitrary thresholds (`if fear > 0.8`).
- LC-04 (Roadmap §15) запрещает таймеры, кулдауны, интервалы частоты инициатив NPC. Применяется ли это к Avatar?

**Архитектурные опции:**
- **A.** Avatar Initiative вычисляется каждый idle_tick (как NPC DecisionHub). Частота зависит от formula (большинство idle_ticks → нет desires с score > threshold, Avatar «молчит»).
- **B.** Avatar Initiative вычисляется каждый N-th idle_tick (но это violates LC-04).
- **C.** Avatar Initiative triggered by events (перceptual change, NPC approach, time-of-day), не каждый tick.

**Рекомендация Архитектора:** A — каждый idle_tick, частота контролируется formula через `urgency` (низкий urgency → AvatarIntention не формируется, потому что не проходит selection threshold в IntentionSynthesizer).

**Геймдизайнер должен решить:** соответствует ли это авторскому ритму игры. Если Avatar должен «молчать подолгу, потом заговорить» — нужны другие controls (event-driven triggers).

### 16.3. Q3 — Body loss / death / respawn

**Вопрос:** Что происходит с Player experience и Avatar consciousness при смерти Body?

**Контекст архитектуры:**
- §9 описывает: Avatar consciousness persists, physical actions REJECTED.
- Но Player input обрывается — что видит Player? UI frozen? Modak «Body мёртв»?
- Возможна ли смена Body (переселение, воскрешение)? R5.1 §6 явно запрещает проектировать без подтверждения.

**Архитектурные опции для UI:**
- **A.** Modak «Body мёртв» с двумя кнопками (прецедент ADR-O-425 LLM outage doctrine): "Load save" / "Continue as observer" (Avatar видит мир без тела).
- **B.** Автоматический transition в spectator mode — Player может наблюдать, но не действовать.
- **C.** Game over screen.

**Архитектурные опции для resurrection:**
- **A.** Нет воскрешения (permadeath). Body loss = game over.
- **B.** Сохранённый Avatar consciousness может быть привязан к новому Body (новый персонаж с теми же beliefs/memory).
- **C.** Воскрешение того же Body (magical resurrection) — но это требует in-world mechanics.

**Рекомендация Архитектора:** Q3 не имеет рекомендации — это чисто авторский замысел. Архитектура готова к любому варианту (§9.6 placeholder для multi-body), но реализация требует отдельного ADR после Геймдизайнерского решения.

**Геймдизайнер должен решить:**
- UI death experience
- Resurrection / body switch policy
- Если body switch — что сохраняется (beliefs, memory, values, relationships)?

### 16.4. Q4 — Avatar-NPC social propagation parity

**Вопрос:** Avatar-authorized SPEAK events (NPC_SPOKE, source=character_id) — должны ли они обрабатываться симметрично с NPC-authored SPEAK events?

**Контекст архитектуры:**
- §10.8 сценарий 8: Avatar обвиняет NPC, 3 bystanders слышат.
- Сегодня `social/propagation.py:89` проверяет `if _ev.source != "player" and _ev.type in ("ACTOR_ATTACKS", "NPC_INTERACTS_NPC")` — это специальная обработка для player attacks.
- Avatar source (`character_id`) — это не `"player"`, но и не NPC_id. Попадает ли он в propagation rules?

**Архитектурные опции:**
- **A.** Avatar-NPC parity: Avatar attacks/accusations propagate socially так же, как NPC-NPC. Никаких специальных player rules.
- **B.** Avatar-Player parity: Avatar attacks обрабатываются как Player attacks (с hullabaloo, faction response).
- **C.** Avatar — отдельная категория: ни Player parity, ни NPC parity. Своя propagation rules.

**Рекомендация Архитектора:** A — Avatar-NPC parity. Avatar — сознание, взаимодействующее с миром через Body; для мира он выглядит как NPC (отдельный субъект с character_id).

**Геймдизайнер должен решить:** соответствует ли это авторскому замыслу социального восприятия Avatar.

### 16.5. Q5 — Avatar Initiative и sleep

**Вопрос:** Что делает Avatar Initiative во время deep sleep?

**Контекст архитектуры:**
- ADR-O-356 Sleep as Bodily Coupling Mode — сон = эмерджентное свойство телесной архитектуры.
- `CouplingProfile`: `external_vision_mult`, `motor_output_mult` — могут быть 0 во время deep sleep.
- DreamSignal → DreamResidue (affective_load).

**Архитектурные опции:**
- **A.** Avatar Initiative пропускается во время deep sleep (как во время player_turn_in_flight). BodyArbiter REJECT все intentions кроме OBSERVE.
- **B.** Avatar Initiative формирует Dream intentions — OBSERVE с dream-like perception, без physical execution.
- **C.** Avatar Initiative работает обычно, но все intentions → DEFERRED до wake.

**Рекомендация Архитектора:** B — Avatar Initiative формирует Dream intentions. Это соответствует ADR-O-356 (сон = эмерджентное свойство) и §9.4 (Avatar consciousness persists without Body — даже сонный Avatar имеет желания, только не может их исполнить).

**Геймдизайнер должен решить:** что Avatar «видит» во сне — replay прошлых событий? Predictions? Random desires?

### 16.6. Q6 — Avatar memory и Player actions

**Вопрос:** Avatar помнит действия Player через своё тело?

**Контекст архитектуры:**
- `MemoryManager` keyed by `npc_id + partner_id`. Avatar memory → `npc_id="player"` (тело).
- §3.7 PROPOSED: `EventMemory.owner_id` — кто владеет воспоминанием. Avatar-наблюдения → `owner_id=character_id`.

**Сценарий:** Player приказывает «атаковать merchant_boris». Body исполняет (WillpowerGate COMPLY). Кто запоминает?
- Player: это его команда.
- Avatar: это его тело атаковало, но он сопротивлялся или подчинился.
- Body: физический исполнитель.

**Архитектурные опции:**
- **A.** Все три помнят. `EventMemory.owner_id` может быть списком: `[player_name, character_id, "player"]`.
- **B.** Avatar помнит только если WillState ≠ COMPLY. Если COMPLY — это Player's memory, Avatar «не заметил».
- **C.** Avatar всегда помнит (его тело действовало), но с `affective_valence` отражающим WillState.

**Рекомендация Архитектора:** C — Avatar всегда помнит действия своего тела, с affective_valence. Это создаёт причинную цепочку: Player command → Body action → Avatar memory with affective load → future desires influenced.

**Геймдизайнер должен решить:** должен ли Avatar «помнить» подчинение Player как собственное действие (для future desire formation) или как внешнее принуждение (без affective load).

---

## §17. ФИНАЛЬНАЯ ФОРМУЛА

Player и Avatar могут хотеть разного.
Оба могут самостоятельно формировать намерения.
Ни один не владеет телом безусловно.
Тело физически исполняет только допустимое действие.
Мир фиксирует только одно фактическое последствие.

**После выдачи архитектурного документа остановиться. Код не менять. Дождаться утверждения.**

---

## §18. ССЫЛКИ

### 18.1. ADR atlas references
- ADR-O-344 (WorldTick Temporal Ownership) — `docs/ADR (Architecture Decision Records).md` line 323
- ADR-O-407 (Player Turn Commitment Time Gate) — game_loop.py:1179
- ADR-O-310 (Windup Execution Gate) — post_decision.py
- ADR-O-313 (Materialization symmetry)
- ADR-O-349 (Intent-Event Completeness)
- ADR-O-351 (Replay Determinism Infrastructure)
- ADR-O-365 (Liveness membrane)
- ADR-O-399 (Task Worker Outbox)
- ADR-O-421 (v1-словарь)
- ADR-O-432 (LC-IMPL-2 split)
- ADR-O-433 (LC-IMPL-3 Ступени A/B/C)
- ADR-O-435 (LC-GC-01 UI Standalone Track) — S393
- ADR-O-436 (NPC_ADDRESSES_PLAYER Event Type) — S396/S398 IMPLEMENTED

### 18.2. Causal Contract references
- §1.1 Пятиуровневая архитектура восприятия
- §1.2 ФУНДАМЕНТАЛЬНЫЕ ИНВАРИАНТЫ СИМУЛЯЦИИ
- §2.4 Тело — Gate of Perception (ADR-O-139)
- §2.5 Эфемерность L3 (EffectiveDrives)
- §2.7 Identity Stability Kernel (ISK, ADR-O-211)
- §9.1 Tick Cardinality (ADR-O-344)
- §9.5 Intent-Event Completeness (ADR-O-349)
- §10.2 Запреты на Волю и Давление
- §12.4 Каузальная труба диалогов (ADR-O-313)
- §12.5 Dual Rail Execution (ADR-O-201)

### 18.3. ENIGMA Architectural Charter
- §ENIGMA-001 Приоритет Причинной Глубины
- §ENIGMA-002 Правило Двух Доменов

### 18.4. Code archaeology
- `backend/app/domain/control_source.py` — ControlSource enum, `_PLAYER_ACTORS`, `resolve_control_source`
- `backend/app/services/npc/decision_hub.py:327` — INV-PLAYER-AUTHORSHIP guard
- `backend/app/services/npc/decision_hub.py:395` — `DecisionHub.compute` signature (20+ params)
- `backend/app/services/will.py:135-215` — `compute_willpower` reactive resistance
- `backend/app/services/will.py:241-297` — `_generate_counter_offer` (not reaching CommunicationIntent)
- `backend/app/services/character/character_filter.py:123-215` — `compute_resistance` Player action filter
- `backend/app/services/events/intent_event_adapter.py` — `_INTENT_EVENT_MAP`, `to_event(intent)`
- `backend/app/services/events/claim_event_subscriber.py:108` — `speaker = getattr(event, "source", "player")`
- `backend/app/services/phases/input.py` — Phase 1 WillpowerGate call, `player_dict` lookup
- `backend/app/services/phases/post_decision.py` — Phase 6/7 Windup
- `backend/app/services/game_loop/game_loop.py:1179` — `_player_turn_in_flight: set[str]`
- `backend/app/services/game_loop/game_loop.py:1153` — `idle_tick` skip
- `backend/app/services/game_loop/turn_pipeline.py:229-230` — `_avatar_dict["npc_id"] = "player"`
- `backend/app/services/player_avatar_service.py:138` — value coupling `npc_id != player_name`
- `backend/app/services/player_avatar_service.py:230` — `CharacterProfile(character_id=player_name)` fallback
- `backend/app/services/tick_orchestrator.py:489` — `execute()` single-threaded owner
- `backend/app/services/tick_orchestrator.py:1033-1117` — `_run_core_phases` order
- `backend/app/domain/action_commitment.py:28-55` — FSM transitions
- `backend/app/domain/action_windup.py` — `ActionWindup`, `WindupStatus`
- `backend/app/models/npc_state.py:388-1359` — NPCState full contract
- `backend/app/models/npc_state.py:133` — `WillState` enum
- `backend/app/models/npc_state.py:105` — `Intent` enum
- `backend/app/models/character.py` — `CharacterProfile` full contract
- `backend/app/domain/communication.py` — `CommunicationIntent` full contract
- `backend/app/services/npc/npc_tick_pipeline.py:59, 1084, 1089, 1240, 1253` — INV-PLAYER-AUTHORSHIP detectors
- `backend/app/services/game_loop/task_scheduler.py` — `_task_outbox`, `_commitment_outbox`, `execute_pending`
- `backend/app/services/events/event_identity.py` — `next_event_identity` Single Writer
- `backend/app/services/avatar/avatar_initiative_engine.py` — PROPOSED new
- `backend/app/services/body/body_arbiter.py` — PROPOSED new

### 18.5. Session history
- S370 — LC-GC-01 ядро закрыто
- S376 — LC-IMPL-2 ч.1/2 (телеграф до клиента)
- S388 — DLG-1 Speaker Symmetry (NPC-NPC speech-act symmetry, mirror for Avatar-Player)
- S393 — ADR-O-435 LC-GC-01 UI Standalone Track
- S396 — ADR-O-436 NPC_ADDRESSES_PLAYER (PROPOSED)
- S398 — ADR-O-436 RECONCILIATION (IMPLEMENTED, commit 755a1c27)
- S399 — этот документ (R5.1 architectural design)

---

**Document end.** ADR-O-435-R5.1 — ARCHITECTURE DESIGN, статус B (готов к утверждению). Код не менялся. Дождаться вердикта Мастера.


