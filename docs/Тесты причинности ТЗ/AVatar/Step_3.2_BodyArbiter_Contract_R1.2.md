# STEP 3.2 R1.2 — BODY ARBITER CONTRACT (MASTER CORRECTIONS C8-C11)

**Статус:** DESIGN REPORT R1.2 (READ-ONLY, no code changes)
**Дата:** 2026-11-08
**Основание:** R1.1 + Master corrections C8-C11

---

## §1. C8 — Resistance Resolver: поведение не предопределено

### 1.1. Исправления

1. **Удалены все `_CALIBRATION_*` пороги** из исполняемого алгоритма. Четыре оси (`desire_strength`, `willingness_to_resist`, `decision_to_struggle`, `physical_capability`) вычисляются, но **не сравниваются с порогами** в коде. Они — входные данные для будущей калибровки, не правила.
2. **Hardcoded willpower не используется**. Источник — `NPCState.psyche` (существующее поле), но без числовых сравнений.
3. **NEGOTIATE не поведение по умолчанию**. Нет default branch.
4. **Отсутствие переговоров — полноценный исход**. `NO_DIALOGUE` — Avatar не пытается договориться, просто действует или уступает.
5. **Поведение определяется существующей личностью**, не второй психологической системой.

### 1.2. Обновлённый контракт Resistance Resolver

```python
class ResistanceBehavior(Enum):
    """Тип поведения Avatar при сопротивлении.
    
    НЕ предопределён алгоритмом. Выбор поведения — отдельная
    ответственность, калибруемая через существующие характеристики.
    """
    RESIST_PHYSICAL = "resist_physical"  # Физическое сопротивление
    YIELD = "yield"                       # Уступка
    NEGOTIATE = "negotiate"              # Переговоры (Avatar просит/угрожает)
    SELF_HARM = "self_harm"              # Самоповреждение
    ESCALATE = "escalate"                # Эскалация к борьбе за контроль
    NO_DIALOGUE = "no_dialogue"          # Avatar не вступает в диалог, действует молча


@dataclass(frozen=True)
class ResistanceAssessment:
    """Оценка сопротивления — четыре независимые оси.
    
    Значения вычисляются из существующих полей NPCState/Desire.
    НЕ сравниваются с порогами в коде. Передаются в калибровку.
    """
    desire_strength: float        # Из Desire.urgency
    willingness_to_resist: float   # Из psyche (willpower) + body_state (stress, fatigue)
    decision_to_struggle: float    # Из identity_integrity + история REJECTED
    physical_capability: float     # Из body_state (fatigue, pain, shock, sleep)


@dataclass(frozen=True)
class ResistanceOutcome:
    """Исход сопротивления. НЕ содержит победителя.
    
    Победитель определяется отдельным режимом C (борьба за контроль).
    В режиме B outcome определяет тип поведения, не победителя.
    """
    behavior: ResistanceBehavior
    avatar_intent_id: str
    player_intent_id: str
    assessment: ResistanceAssessment
    reason: str
    tick: int
```

### 1.3. Процесс выбора поведения (не алгоритм)

Resistance Resolver **не вычисляет** поведение по формуле. Он:
1. Вычисляет 4 оси оценки (из существующих полей)
2. Передаёт оценку в **BehaviorSelector** (отдельная ответственность)
3. BehaviorSelector определяет тип поведения на основе **калибровочной таблицы** (Calibration Lab, будущий шаг)
4. Пока калибровка не проведена — BehaviorSelector возвращает `None` (поведение не определено)

```python
class ResistanceResolver:
    def resolve_resistance(
        self,
        player_intent: Dict[str, Any],
        avatar_intent: Dict[str, Any],
        body_state: Dict[str, Any],
        psyche: Dict[str, Any],
        identity_integrity: float,
        rejected_count: int,
        tick: int,
    ) -> Optional[ResistanceOutcome]:
        """Разрешает обычное сопротивление.
        
        Возвращает None если поведение не определено (калибровка не проведена).
        Возвращает ResistanceOutcome если поведение определено.
        НЕ выбирает победителя.
        """
        assessment = ResistanceAssessment(
            desire_strength=float(avatar_intent.get("urgency", 0.0)),
            willingness_to_resist=float(psyche.get("willpower", 50.0)),
            decision_to_struggle=identity_integrity,
            physical_capability=self._assess_capability(body_state),
        )
        
        behavior = self._behavior_selector.select(assessment)
        if behavior is None:
            return None  # Не определено — калибровка требуется
        
        return ResistanceOutcome(
            behavior=behavior,
            avatar_intent_id=avatar_intent.get("intent_id", ""),
            player_intent_id=player_intent.get("intent_id", ""),
            assessment=assessment,
            reason=f"behavior={behavior.value}",
            tick=tick,
        )
```

**Поведение не предопределено.** Пока `_behavior_selector` не откалиброван — сопротивление не разрешается (fail-closed). Это не блокер для BodyArbiter (гейт авторизации работает без Resistance Resolver), но блокер для материализации Avatar поведения.

---

## §2. C9 — DerivedPhysicalIntent: причинная идентичность и путь исполнения

### 2.1. Контракт DerivedPhysicalIntent (уточнённый)

```python
@dataclass(frozen=True)
class DerivedPhysicalIntent:
    """Производное физическое намерение от Resistance Outcome.
    
    Связь с исходным Avatar Intent сохраняется через source_intent_id.
    Владелец — UUID-A (Avatar consciousness). Тело — UUID-B (общее).
    """
    derived_id: str               # Детерминированный ID (next_intent_identity)
    source_intent_id: str         # intent_id породившего Avatar Intent
    owner: str                    # UUID-A (Avatar consciousness)
    body_id: str                  # UUID-B (shared body)
    derived_action: str           # "self_harm" / "resist_physical" / "redirect_movement"
    physical_effect: str          # "body_damage" / "movement_redirect" / "none"
    formed_tick: int
```

### 2.2. Путь исполнения (требующий проверки)

Master C9.3: «Не считать NPC MovementEngine готовым путём для Avatar без проверки».
Master C9.4: «Не считать прямой вызов StateApplicator доказательством корректного физического повреждения».

**Что нужно проверить (implementation, read-only first):**

| Эффект | Существующий путь | Что проверить |
|--------|------------------|--------------|
| `body_damage` (SELF_HARM) | `StateApplicator.apply_batch()` с `PhysiologyPayload` | Принимает ли StateApplicator прямой вызов от Avatar? Или требует EventBus event → CombatSubscriber → ImpactEngine? |
| `movement_redirect` (RESIST_PHYSICAL) | `MovementEngine` через NPC tick pipeline | MovementEngine исключает Avatar (npc_tick_pipeline:1666 `if npc_id == "player": return None`). Avatar не может использовать NPC movement path. |

### 2.3. Найденные неизвестные

| # | Вопрос | Статус |
|---|--------|--------|
| U5 | Avatar Intent execution path — как Avatar Intent становится физическим действием | UNVERIFIED — требует отдельного исследования (не в R1.2 scope) |
| U7 | Принимает ли StateApplicator прямой вызов для Avatar body damage? | UNVERIFIED — требует чтения StateApplicator whitelist |
| U8 | Как Avatar может инициировать movement, если MovementEngine исключает npc_id="player"? | UNVERIFIED — требует исследования FIX-PLAYER-AGENCY контекста |

**Решение:** DerivedPhysicalIntent **не исполняется** до разрешения U7-U8. В плане реализации (C11) — сначала read-only проверка существующих путей, затем предложение расширения (если нужно), затем реализация.

### 2.4. Обычное сопротивление не означает победу

Master C9.7: «Обычное сопротивление не должно автоматически означать победу Avatar или Player.»

Resistance Outcome определяет **тип поведения**, не победителя:
- `RESIST_PHYSICAL` — Avatar пытается физически сопротивляться. Это **не значит**, что Avatar победил. BodyArbiter авторизует Avatar Intent (если поведение определено), но Player Intent не отклоняется автоматически.
- `YIELD` — Avatar уступает. BodyArbiter авторизует Player Intent, Avatar Intent отклоняется.
- `NEGOTIATE` — оба откладываются (DEFERRED).
- `NO_DIALOGUE` — Avatar действует молча, без переговоров.

**Победитель определяется только в режиме C (борьба за контроль).** Режим B — это поведение Avatar, не решение конфликта.

---

## §3. C10 — Идемпотентность конкретного эффекта

### 3.1. Проблема пустого effect_status

Если `effect_status` отсутствует в lifecycle entry (старый save, или новый intent без эффектов), `_is_effect_executed` возвращает False. Это **правильно** — эффект не исполнен.

Но: для намерений, у которых эффект неприменим (например, `PLAYER_ATTACKED` для dialogue action), `effect_status` не должен содержать этот ключ. Проверка `_is_effect_executed(intent_id, "input_merge_attack")` для dialogue intent возвращает False — эффект не исполнен, и не должен исполняться.

### 3.2. Поведение при аварийном завершении

| Сценарий | Что происходит | Защита |
|----------|---------------|--------|
| Эффект исполнен (STM written), статус не записан | При replay эффект повторится | `_mark_effect_executed` вызывается **после** успешного исполнения, в том же tick. Если tick упал после STM write но до mark — replay повторит STM write (дубликат в памяти) |
| Статус записан, эффект не исполнен | При replay эффект пропускается | `_is_effect_executed` проверяется **до** исполнения. Если статус EXECUTED — пропуск. Это безопасно для идемпотентных эффектов (EventBus publish), но **небезопасно** для неидемпотентных (STM write — дубликат) |

### 3.3. Идемпотентность по получателям

| Эффект | Получатель | Идемпотентный? | Защита |
|--------|-----------|---------------|--------|
| M1: STM write | `MemoryManager.add_dialogue_turn` | ❌ Дубликат | Проверять `effect_status["stm_write"]` ДО вызова |
| M2: L1 write | `L1Chronicle.commit_tick_buffer` | ⚠ L1 append-only — дубликат записи | Проверять `effect_status["l1_write"]` ДО вызова |
| M3: SOCIAL_ACTION | `EventBus.publish` | ⚠ Subscribers могут не быть идемпотентными | Проверять `effect_status["social_action"]` ДО вызова |
| M4: classified publish | `EventBus.publish` | ⚠ То же | Проверять `effect_status["classified_publish"]` ДО вызова |
| M5: INPUT_MERGE | `EventBus.publish` | ⚠ CombatSubscriber → ImpactEngine → damage | Проверять `effect_status["input_merge_attack"]` ДО вызова |

### 3.4. Различение начала, завершения и ошибки

```python
class EffectState(Enum):
    NOT_STARTED = "not_started"     # Эффект не начинался
    IN_PROGRESS = "in_progress"     # Эффект начат (для многотиковых)
    COMPLETED = "completed"         # Эффект завершён успешно
    FAILED = "failed"               # Эффект упал
    NOT_APPLICABLE = "not_applicable"  # Эффект неприменим к этому намерению
```

```python
effect_status = {
    "stm_write": "not_started",
    "l1_write": "not_started",
    "social_action": "not_applicable",  # Для attack action — SOCIAL_ACTION есть, но не для dialogue
    "classified_publish": "not_started",
    "input_merge_attack": "not_applicable",  # Для dialogue action
}
```

### 3.5. Save/load round-trip

`effect_status` — dict в `intent_lifecycle` entry. `intent_lifecycle` persisted через `atomic_commit` (Foundation Freeze, ADR-FOUNDATION-FREEZE). deepcopy round-trip сохраняет dict (проверено `test_avatar_desires_survive_round_trip`).

**Доказательство:** `intent_lifecycle` уже survived save/load (Step 3.1 test `test_avatar_intent_survives_save_load`). `effect_status` — дополнительный dict внутри entry, survives через тот же механизм.

---

## §4. C11 — Семантика событий и временные состояния

### 4.1. Разделение состояний

| Понятие | Где живёт | Значения |
|---------|----------|----------|
| Намерение | `intent_lifecycle` (lifecycle_state) | ACTIVE / SUPERSEDED / VOIDED |
| Авторизация | `intent_lifecycle` (arbitration_result) | PENDING / AUTHORIZED / REJECTED / DEFERRED |
| Исполнение эффекта | `intent_lifecycle` (effect_status) | NOT_STARTED / IN_PROGRESS / COMPLETED / FAILED / NOT_APPLICABLE |
| Наблюдение | EventBus event (event_type) | PLAYER_SPOKE / PLAYER_ATTACKED / ACTOR_ATTACKS / COMMUNICATION_CLAIM |

### 4.2. SOCIAL_ACTION — что означает

SOCIAL_ACTION — это **сигнал о разрешённой попытке**. Он публикуется **только если** BodyArbiter авторизовал Player Intent.

| Сценарий | SOCIAL_ACTION | Projections |
|----------|--------------|-------------|
| Player атакует, AUTHORIZED | Публикуется (попытка) | ACTOR_ATTACKS, COMMUNICATION_CLAIM — публикуются (как следствие попытки) |
| Player атакует, REJECTED | НЕ публикуется | Projections не создаются |
| Player говорит, AUTHORIZED | Публикуется (попытка) | COMMUNICATION_CLAIM — публикуется |
| Player говорит, REJECTED | НЕ публикуется | Projections не создаются |

**Принцип:** SOCIAL_ACTION не создаётся при заблокированной попытке. Если BodyArbiter отклонил — нет попытки, нет наблюдения, нет факта.

### 4.3. Заблокированная атака vs нанесённый удар

| Состояние | События | Эффекты |
|-----------|--------|---------|
| Заблокированная атака (REJECTED) | НЕТ SOCIAL_ACTION, НЕТ PLAYER_ATTACKED, НЕТ ACTOR_ATTACKS | НЕТ damage, НЕТ STM, НЕТ L1 |
| Нанесённый удар (AUTHORIZED + EXECUTED) | SOCIAL_ACTION (попытка), PLAYER_ATTACKED (исполнение), ACTOR_ATTACKS (projection) | damage (ImpactEngine), STM (если speech), L1 (если dialogue) |

### 4.4. Проверка ACTOR_ATTACKS (до удаления)

**Требуется read-only проверка (implementation C7):**
1. Прочитать `social_action_subscriber.py` — все projections
2. Прочитать `intent_event_adapter.py` — NPC ACTOR_ATTACKS path
3. Прочитать `combat_subscriber.py` — `_COMBAT_EVENT_TYPES`
4. Проверить: NPC attacks (NPC→Player, NPC→NPC) идут через `IntentEventAdapter` (intent_event_adapter.py:25 `"attack": EventType.ACTOR_ATTACKS`), не через SocialActionSubscriber
5. Если NPC path независим — удалить SocialActionSubscriber ACTOR_ATTACKS projection
6. Если NPC path зависит — гейтировать projection авторизацией

### 4.5. Продолжительное действие

Для действий с `duration_ticks > 1` (составные, будущая реализация):

```python
effect_status = {
    "action_phase": "not_started",  # not_started / in_progress / completed / interrupted
    "stm_write": "not_applicable",
    ...
}
```

Пересмотр арбитража на новом тике:
- `arbitration_result` сбрасывается в PENDING (C7)
- `effect_status` НЕ сбрасывается (идемпотентность)
- Если action `in_progress` и новый арбитраж REJECTED → `action_phase = interrupted`

### 4.6. Убраны PLAYER_WINS / Avatar WINS из режима B

Resistance Outcome определяет **поведение Avatar**, не победителя:
- `RESIST_PHYSICAL` — Avatar сопротивляется (Avatar Intent AUTHORIZED, Player Intent — отдельное решение)
- `YIELD` — Avatar уступает (Player Intent AUTHORIZED, Avatar Intent REJECTED)
- `NO_DIALOGUE` — Avatar действует молча

Победитель — только режим C (борьба за контроль, будущий дизайн).

---

## §5. Минимальный план реализации

| # | Этап | Цель | Зависимость |
|---|------|------|-------------|
| C1 | Domain entities | `ArbitrationVerdict`, `ArbitrationResult`, `PhysicalEffectProfile`, `ResistanceAssessment`, `ResistanceOutcome`, `DerivedPhysicalIntent`, `EffectState` | — |
| C2 | BodyArbiter compatibility | `check_compatibility()` — Physical Effect Profile | C1 |
| C3 | BodyArbiter authorization | `authorize()` — записывает AUTHORIZED/REJECTED + effect_status | C2 |
| C4 | Per-effect идемпотентность | `_is_effect_executed`, `_mark_effect_executed`, `EffectState` enum | C3 |
| C5 | Wire BodyArbiter into pipeline | Вызов после Player Intent Identity | C3, C4 |
| C6 | Gate SOCIAL_ACTION | Проверка authorization | C5 |
| C7 | Check ACTOR_ATTACKS consumers | Read-only проверка (§4.4) | C6 |
| C8 | Gate publish_classified + INPUT_MERGE | Заменить dead `action_rejected` | C5 |
| C9 | Move DM Stage E | После BodyArbiter (verify first) | C5 |
| C10 | Resistance Resolver | 4 оси оценки, BehaviorSelector (None пока) | C3 |
| C11 | DerivedPhysicalIntent | Read-only проверка путей (U7-U8), затем реализация | C10 |
| C12 | Remove dead code | `action_rejected`, `publish_player_speech` | C8, C9 |
| C13 | Integration test | Stranger hunger scenario | C6-C11 |

---

## §6. Тесты

| # | Тест | Что доказывает |
|---|------|----------------|
| T1 | `test_no_avatar_intent_no_conflict` | Нет Avatar → NO_CONFLICT |
| T2 | `test_no_player_intent_avatar_authorized` | Нет Player → Avatar AUTHORIZED |
| T3 | `test_compatible_intents_both_authorized` | Move + Talk → BOTH_AUTHORIZED |
| T4 | `test_conflict_intents_deferred` | Move east + Move west → DEFER_BOTH (behavior not determined) |
| T5 | `test_rejected_intent_not_deleted` | REJECTED intent остаётся ACTIVE |
| T6 | `test_authorized_intent_can_execute` | AUTHORIZED → publication проходит |
| T7 | `test_rejected_intent_blocked` | REJECTED → publication не проходит |
| T8 | `test_no_double_execution` | Один intent → одно исполнение (per-effect) |
| T9 | `test_effect_status_survives_save_load` | effect_status persisted |
| T10 | `test_arbitration_reset_on_new_tick` | arbitration_result → PENDING на новом тике |
| T11 | `test_resistance_resolver_returns_none_without_calibration` | BehaviorSelector None → no behavior |
| T12 | `test_resistance_assessment_four_axes` | 4 оси вычисляются из существующих полей |
| T13 | `test_social_action_not_published_when_rejected` | REJECTED → нет SOCIAL_ACTION |
| T14 | `test_actor_attacks_not_published_when_rejected` | REJECTED → нет ACTOR_ATTACKS projection |

---

## §7. Оставшиеся неизвестные

| # | Вопрос | Статус | Когда решается |
|---|--------|--------|---------------|
| U1 | Конкретные пороги BehaviorSelector | CALIBRATION_CANDIDATE | Calibration Lab |
| U2 | Алгоритм режима C (борьба за контроль) | UNVERIFIED | Отдельный будущий дизайн |
| U3 | Зависимость NPC path от ACTOR_ATTACKS projection | UNVERIFIED | Implementation C7 (read-only) |
| U4 | Перемещение DM Stage E — побочные эффекты | PARTIALLY VERIFIED | Implementation C9 |
| U5 | Avatar Intent execution path | UNVERIFIED | Отдельный будущий шаг |
| U6 | effect_status save/load round-trip | VERIFIED (через intent_lifecycle) | Implementation C4 |
| U7 | StateApplicator принимает прямой вызов для Avatar? | UNVERIFIED | Implementation C11 (read-only) |
| U8 | Как Avatar инициирует movement, если MovementEngine исключает npc_id="player"? | UNVERIFIED | Implementation C11 (read-only) |

---

**Готов к рассмотрению Мастером.**

*Production: HOLD. Design report R1.2. Код не меняется до утверждения.*
