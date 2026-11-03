# BUTTERFLY-01_IMPLEMENTATION_GUIDE.md

**Версия:** 2.0 (R2) · **Дата:** 2026-11-03 · **Базис:** ENIGMA v0.5.4.5.3 (baseline `d78f0a4`) + BUTTERFLY-01 (`ce7c225`→`1a8dee8`) + R2 (`de0abe5`)
**Автор:** рой BUTTERFLY-01 / корректировка R2 (исследование production-кода выполнено до единой строки изменений)

---

## 0. Что это за документ

Пошаговая инструкция для программиста, который **не участвовал в исследовании**.
Цель — замкнуть кор-механику ENIGMA на первом доказательном эксперименте:

> Игрок говорит Люсе: «Трактирщик свинья и жлоб». Проходит игровое время.
> Люся **сама** решает, рассказать ли Торнину. Если рассказывает — только через
> реальный игровой разговор. Позже игрок просит Торнина: «Продай мне пиво» —
> и Торнин отвечает, исходя из того, что он **действительно узнал**.

Каждый этап: что строим → что трогаем → что трогать **запрещено** → движение
данных → тесты до/после → критерий завершения.

### Главные правила (наследуются из ТЗ)

1. Никаких параллельных систем: ни второго хранилища истины, ни сценарного
   механизма слухов, ни заглушек вместо симуляции.
2. Ни одной заранее написанной реакции NPC. Мы **открываем возможность**,
   решение принимает DecisionHub + LLM на реальном состоянии NPC.
3. LLM получает только тот контекст, который положен соответствующему NPC
   (его собственная память, его собственные убеждения, его собственные отношения).
4. Малые изолированные шаги, тесты до/после, коммит на каждый шаг.

### Условные обозначения

- **[ПРОВОДКА]** — изменение существующего вызова/подписки без новой механики.
- **[МЕХАНИКА]** — новая игровая функция в существующем домене.
- **[ФИКС ЦЕЛОСТНОСТИ]** — устранение утечки знания без основания.

---

## 1. Архитектурная карта существующих механизмов (что нашли)

Все пути проверены чтением кода и трассировкой вызовов (не по документации).

### 1.1 Путь реплики игрока (production, работает)

```
frontend/text_input.py → POST /api/game/action (backend/app/api/routes.py:939)
  → GameLoop.run_turn (services/game_loop/game_loop.py:1572)
    → TurnPipeline.execute (game_loop/turn_pipeline.py:740)
      ├─ run_dm_phase (game_loop/dm_phase.py:43)
      │    ├─ extract_player_target (spatial/player_target_pipeline.py:45)
      │    │    «трактирщик» → role-keyword → tavern_keeper_tornin
      │    └─ DMRouter._classify_action (action/dm_router.py:237)
      │         «свинья» ∈ data/insults_ru.json + короткая фраза ≤4 слов → "player_insults"
      ├─ IntentCompressor.compress (input/intent_compressor.py:474)
      ├─ publish_classified_player_event (game_loop/phase_1_input.py:510)
      │    → EventDTO(type="player_insults", target=tornin, radius=10.0, intensity=0.65)
      └─ run_npc_orchestration → TickOrchestrator → NpcTickPipeline
```

### 1.2 Эпистемический контур (production, работает)

- **EventBus** (sync) → `ClaimEventSubscriber` (`services/events/claim_event_subscriber.py`)
  подписан на `COMMUNICATION_CLAIM`, `NPC_SPOKE`, `PLAYER_SPOKE` (game_loop.py:619–627).
- Мембрана слуха: `distance ≤ event.radius` + `PerceptualKernel.can_observe`
  (models/npc_state.py:645) → `BeliefRevisionEngine.revise` → `EpistemicStore.upsert`.
- `EpistemicStore` персистится в `scene_state["epistemic_records"]` каждый тик
  (tick_orchestrator.py:822) и восстанавливается при загрузке (game_loop.py:602).
- `EpistemicContextResolver` → `trigger_proposition` **только для `_THREAT_PREDICATES`
  = (STOLE, ATTACKED)** (epistemic_context_resolver.py:25) → DecisionHub S197
  (`decision_hub.py:1925–1951`: warn → target = subject_id пропозиции).
- Reliability: `TrustBasedReliabilityProvider` — trust наблюдателя к источнику /100;
  неизвестная пара → prior 0.5; прямое наблюдение → 0.9.

### 1.3 Автономное общение NPC (production, работает)

- Idle-тик (`POST /api/game/idle_tick`, `GameLoop.idle_tick` game_loop.py:1153) тикает
  **все** локации; на idle каждый NPC получает `EventContext(WORLD_TICK)` →
  проактивные интенты разрешены: `TALK`, `SPREAD_RUMOR`, … (decision_hub.py:73–86).
- `DecisionHub._build_communication` → `CommunicationIntent(proposition=trigger_proposition)`
  → Фаза 6 `post_decision.py:28` → `QueuedTask` → `TaskScheduler.execute_pending`
  → `DialogueExecutor` (canonical, LLM) / `NpcConversation` (ambient, шаблоны)
  → `DialogueMaterializer` → `NPC_SPOKE` + (если есть proposition) `COMMUNICATION_CLAIM`
  → `ClaimEventSubscriber` → убеждения слушателей в радиусе речи.
- ADR-O-342 «STM Hard Contract»: без общей истории диалога intent понижается
  до `approach` (post_decision.py:124–136; task_scheduler.py:683; dialogue_executor.py:409).
  Исключения сегодня: `greeting`, `approach`, `warn`, `intimidate`.
- SocialTargetResolver: цель ≤5 м + LoS + trust (npc/social_target_resolver.py).

### 1.4 Торговля (обновлено R2; детали — Часть II)

- **Единый механизм (R2):** заказ (Transaction, `work_orders.py`) → settlement
  (`settle_order`) для ИГРОКА и NPC; сток — из хранилища ПРЕДПРИЯТИЯ
  (`establishments` в scene_state) либо, вне заведения, из личного стока продавца.
- Игрок: `player_purchase.py` — тонкий адаптер ввода намерения (лексикон
  «пиво/эль» → заказ той же фабрикой `create_order_direct` → тот же settlement).
- NPC: NEED→DESIRE→TRADE-интент → `create_order_from_trade_intent` → SERVE →
  `settle_order` (флаг `WORK_ENABLED` гейтит только давление желаний NPC).
- Права: персонал (`can_serve`/`can_manage_stock` — назначения, не id-проверки)
  обслуживает и распоряжается запасами; посетители (игрок и NPC) — заказывают.
- Выручка заведения → казна предприятия (`treasury.gold`), не личный кошелёк.

### 1.5 Время и расписание

- `scene_state["game_time_seconds"]`, +60 сек/тик; idle-тики, `POST /api/game/skip_time`
  → `TimeSkipExecutor` (останавливается на значимых событиях).
- Люся: tavern, 06:00–21:00 working (kitchen); Торнин: tavern, 06:00–22:00 working
  (behind_bar). kitchen↔behind_bar ≈ **12.8 м** — дальше радиуса оскорбления (10 м),
  ближе «штатного» звукового гейта памяти (жёстко 15 м — см. Этап 7).

### 1.6 Отношения (SSOT, работает)

`config/npc/social/village_relations.json`: tornin→lusya trust 30 («знает о шпионаже,
но молчит»), lusya→tornin trust 40; lusya→borko 60/80 и т.д. Хранилище:
`RelationshipStore` (−100..100), единая точка записи `RelationshipWriteGate`.

---

## 2. Перечень разрывов (почему бабочка сегодня не летает)

| # | Разрыв | Где | Следствие для эксперимента |
|---|--------|-----|---------------------------|
| G1 | Событие `player_insults` **не подписано** на ClaimEventSubscriber; пропозиция об оскорблении не рождается | game_loop.py:627, claim_event_subscriber.py:89 | У Люси нет передаваемого убеждения — распространять нечего |
| G2 | В реестре `Predicate` нет оскорбления; `trigger_proposition` живёт только для STOLE/ATTACKED | domain/epistemology.py:17–33, epistemic_context_resolver.py:25 | Канал S197 не может нести «игрок оскорбил Торнина» |
| G3 | С197-таргетинг warns в `subject_id` — для оскорбления сообщить нужно **жертве** (object_id) | decision_hub.py:1925–1951 | Люся «предупреждала бы» самого игрока |
| G4 | ADR-O-342: два NPC без общей истории **никогда** не начинают содержательный диалог (бесконечный approach-loop) | post_decision.py:124–136 | Люся не может впервые рассказать Торнину |
| G5 | `spread_rumor` материализуется шаблоном `[spread_rumor] X -> Y: topic` без LLM и без содержания клейма | intent_profiles.py:16, dialogue_executor.py:140–142 | Реплика не несёт смысла; нарушение «реальной генерации» |
| G6 | Промпт NPC-исполнителя не содержит пропозициональных убеждений из EpistemicStore — реакция Торнина не может опираться на услышанное | dialogue_executor.py:360–466 | Уровень 2 эксперимента недостижим |
| G7 | Звуковой гейт памяти вне LoS — жёсткие 15 м, радиус события (SSOT) игнорируется | npc_tick_pipeline.py:207 | Торнин «запоминает» оскорбление на 12.8 м, не слыша его — утечка |
| G8 | Покупка игрока — имитация (−5G без товара, продавец не получает ничего) | rules_subscriber.py:224–240 | «Продай мне пиво» не проходит через экономику |
| G9 | «жлоб» отсутствует в `data/insults_ru.json` (есть «свинья») | data/insults_ru.json | Часть формулировок не классифицируется как оскорбление |
| G10 | Provenance: `source_id` перезаписывается свежим спикером; «видел сам / слышал / рассказали» не персистится | belief_revision_engine.py:92, epistemic_store.py:47–66 | Цепочка происхождения не доказывается в отчёте |

---

## 3. ЭТАПЫ РЕАЛИЗАЦИИ

> Каждый этап = один коммит. Перед этапом: прогнать «тесты до».
> После: «тесты после» + регрессия. Имена тестов — фактические файлы.

---

### ЭТАП 1. `Predicate.INSULTED` + доказуемое происхождение убеждения

**Игровая функция:** мир различает «кто-то что-то утверждал» и «кто-то кого-то
оскорбил»; каждое убеждение несёт происхождение (сам видел / слышал / сказали).

**Текущая архитектура:** `Predicate` — закрытый реестр (STOLE/ATTACKED/HELPED/
ASSERTS/EXITS_TO/NAME); каждое расширение — отдельной ревизией (прецеденты
комментариев EXITS_TO, NAME). `EpistemicRecord` — frozen dataclass с provenance
полями `source_id`/`source_claim_id`. `BeliefRevisionEngine.revise` при обновлении
перезаписывает `source_id` свежим спикером (G10). Прецедент канала:
`ObservationSubscriber` передаёт `reliability_context={"source_type": "direct_observation"}`.

**Файлы:**

1. `backend/app/domain/epistemology.py`
   - В `Predicate` добавить `INSULTED = "insulted"` (комментарий-ревизия по
     образцу NAME: «BUTTERFLY-01: subject оскорбил object; subject — оскорбитель,
     object — жертва»).
   - В `EpistemicRecord` добавить два поля **с дефолтами** (обратная совместимость
     всех keyword-конструкторов): `source_type: str = ""` (`""`|`"testimony"`|`"direct_observation"`)
     и `original_source_id: str = ""` (первичный источник цепочки).
2. `backend/app/services/npc/belief_revision_engine.py`
   - В ветке **новой** записи: `source_type = (reliability_context or {}).get("source_type", "testimony")`,
     `original_source_id = claim.speaker_id`.
   - В ветке **обновления**: `original_source_id` **сохраняется** от прежней записи
     (если пуст — заполнить текущим спикером); `source_type` прежней записи
     сохраняется, если не пуст.
3. `backend/app/services/events/claim_event_subscriber.py`
   - В `on_claim_event` при вызове `self._engine.revise(...)` передать
     `reliability_context={"source_type": "testimony"}` (канал речи).
4. `backend/app/services/npc/epistemic_store.py`
   - `to_dict`/`from_dict`: добавить сериализацию новых полей
     (`item.get("source_type", "")`, `item.get("original_source_id", "")`).

**Что НЕ менять:** формулу reliability, порог `CONFIDENCE_THRESHOLD`, S188-инварианты,
остальные предикаты.

**Движение данных:**
```
Люся слышит игрока:  EpistemicRecord(lusya, (player, INSULTED, tornin),
                     source=player, source_type="testimony", original_source="player")
Торнин слышит Люсю:  EpistemicRecord(tornin, (player, INSULTED, tornin),
                     source=lusya, source_type="testimony", original_source="player")
```

**Тесты до:** `backend/tests/micro/test_claim_bridge_chain.py`, `test_utterance_identity_chain.py` — зелёные.
**Тесты после:** те же + новый `backend/tests/micro/test_butterfly_insult_proposition.py` (кейсы 1–2 из Этапа 2 — сериализация и происхождение).
**Регрессия:** `pytest backend/tests/micro -k "epistem or claim or belief"` — без новых падений.
**Критерий завершения:** round-trip `to_dict→from_dict` сохраняет `source_type` и
`original_source_id`; повторный клейм от другого спикера не затирает `original_source_id`.

---

### ЭТАП 2. Оскорбление → пропозиция (замыкание G1)

**Игровая функция:** услышавшее оскорбление NPC получает структурированное
убеждение «player оскорбил ⟨жертва⟩» — с мембраной слуха (радиус события).

**Текущая архитектура:** `publish_classified_player_event` публикует
`EventDTO(type="player_insults", target_id=жертва, radius=10.0)`.
`ClaimEventSubscriber` подписан только на `PLAYER_SPOKE` (game_loop.py:627);
`on_player_spoke` строит пропозиции только из DM-векторов ACCUSE/THREATEN/HELP.

**Файлы:**

1. `backend/app/services/events/claim_event_subscriber.py` — в `on_player_spoke`
   **перед** free-ASSERT веткой (USL-1.4) добавить ветку оскорбления:
   ```python
   _evt_type = str(getattr(event, "type", "") or "")
   _action_type = str(payload.get("action_type", "") or "")
   if "player_insults" in (_evt_type, _action_type):
       _victim = payload.get("target_id") or ""
       if _victim:
           # BUTTERFLY-01: игрок оскорбил жертву (subject=игрок, object=жертва).
           _new_payload = dict(payload)
           _new_payload["proposition"] = {
               "subject_id": getattr(event, "source", "player"),
               "predicate": Predicate.INSULTED.value,
               "object_id": _victim,
               "polarity": True,
           }
           _new_payload.setdefault("claim_id", f"player-claim-{event.id}")
           _new_payload.setdefault("speech_act", "insult")
           self.on_claim_event(dataclasses.replace(event, payload=_new_payload))
       return
   ```
   (Ровно тот же паттерн, что ACCUSE/THREATEN ветки :134–143.)
2. `backend/app/services/game_loop/game_loop.py` — `_register_epistemic_core`,
   после строки `_bus.subscribe(EventType.PLAYER_SPOKE, ...)` добавить:
   `_bus.subscribe(EventType.PLAYER_INSULTS, _subscriber.on_player_spoke)` **[ПРОВОДКА]**
   — мембрана `on_claim_event` (distance ≤ radius 10 м + can_observe) уже универсальна.

**Что НЕ менять:** мембрану слушателей, Proposition-guard, sanity_membrane,
остальные подписки, реакционные дельты (stress/trust от ReactionSubscriber).

**Движение данных:**
```
«Трактирщик свинья и жлоб» (игрок на кухне, Люся рядом, Торнин за стойкой 12.8 м)
→ EventDTO(player_insults, target=tavern_keeper_tornin, radius=10)
→ ClaimEventSubscriber: слушатели = {maid_lusya}  (Торнин дальше 10 м — не слышит)
→ EpistemicStore: (maid_lusya, (player, INSULTED, tavern_keeper_tornin), conf≈0.5)
```

**Тесты до:** `pytest backend/tests/micro -k "claim"` — зелёные.
**Тесты после:** новый `backend/tests/micro/test_butterfly_insult_proposition.py`:
1. игрок+Люся в радиусе, Торнин за 12 м → у Люси есть убеждение INSULTED, у Торнина нет;
2. `to_dict→from_dict` сохраняет запись;
3. оскорбление без target_id → нет записи (guard);
4. повторное оскорбление → та же запись, confidence растёт (same-source boost).
**Регрессия:** `pytest backend/tests/micro -k "claim or player_spoke"`.
**Критерий завершения:** у слышащего NPC появляется ровно одна запись
`(player, INSULTED, victim)`; у дальнего NPC — ничего.

---

### ЭТАП 3. Report-канал эпистемического резолвера (замыкание G2)

**Игровая функция:** NPC, знающий об оскорблении третьего лица, имеет
когнитивно-релевантный канал «сообщить заинтересованной стороне» — с весами,
а не сценарием. NPC, оскорблённый сам, попадает в существующий канал
самореферентности (салиентность собственного разговора).

**Текущая архитектура:** `EpistemicContextResolver.resolve` собирает
threats/allies/violations/trigger (только `_THREAT_PREDICATES`) и `claims_about_self`
(subject == agent). `EpistemicContext` — frozen dataclass; расширение полями
с дефолтами обратно совместимо.

**Файл:** `backend/app/services/npc/epistemic_context_resolver.py`

1. Реестр и калибровка (по образцу GATE-TRIGGER-01):
   ```python
   # BUTTERFLY-01: report-канал — знание об оскорблении третьего лица.
   # Отдельный порог (не CONFIDENCE_THRESHOLD): report — салиентность,
   # а не угроза; слышанное через цепочку свидетельств дешевеет
   # (trust×100/100). Калибровочный кандидат, меняется отдельной ревизией.
   REPORT_PREDICATES = (Predicate.INSULTED,)
   REPORT_CONFIDENCE_THRESHOLD = 0.25
   ```
2. В `resolve()`: в цикле по записям:
   - если `pred == INSULTED and object_id == agent_id` → записать в `about_self`
     (тот же канал GC-RELEVANCE-01, max_self_conf) и `continue`;
   - если `pred in REPORT_PREDICATES and conf ≥ REPORT_CONFIDENCE_THRESHOLD
     и object_id != agent_id и subject_id != agent_id` → трекер
     `_report_prop`/`_report_conf` (максимум уверенности).
3. В конструктор `EpistemicContext(...)` передать `report_proposition=_report_prop`
   (новое поле `report_proposition: Optional[Proposition] = None` в domain/epistemology.py).
4. `to_modifiers()`: если `context.report_proposition`:
   ```python
   _rep_boost = round(context.max_confidence * 0.9, 4)
   modifiers["spread_rumor"] = round(modifiers.get("spread_rumor", 0.0) + _rep_boost, 4)
   modifiers["talk"] = round(modifiers.get("talk", 0.0) + _rep_boost * 0.6, 4)
   ```
   (spread_rumor сильнее talk: сплетня — его естественная форма; weights —
   калибровочные кандидаты. Модификаторы аддитивные; итоговый выбор — DecisionHub.)

**Что НЕ менять:** `_THREAT_PREDICATES`, threat/ally-логику, `CONFIDENCE_THRESHOLD`,
формулу self-boost, сигнатуру `resolve`.

**Движение данных:** `EpistemicStore(lusya)` → resolve → `EpistemicContext(report_proposition=(player,INSULTED,tornin), max_confidence=0.5)` → modifiers `{spread_rumor:+0.45, talk:+0.27}`.

**Тесты до:** `pytest backend/tests -k "epistemic_context"`.
**Тесты после:** новый `backend/tests/micro/test_butterfly_report_channel.py`:
1. у Люси report_proposition == (player, INSULTED, tornin), модификаторы содержат spread_rumor;
2. у Торнина (object==self) — report_proposition is None, но claims_about_self растёт talk-модификатор;
3. запись ниже 0.25 не даёт report;
4. STOLE-записи не попадают в report (разделение каналов сохранено).
**Регрессия:** `pytest backend/tests -k "epistemic"`.
**Критерий завершения:** существующие эпистемические тесты зелёные; новые кейсы проходят.

---

### ЭТАП 4. DecisionHub: таргетинг «сообщить жертве» + перенос пропозиции (замыкание G3)

**Игровая функция:** NPC, решивший поделиться report-знанием, идёт говорить
именно с жертвой оскорбления, а не с оскорбителем; CommunicationIntent несёт
пропозицию (каузальная провенансность S197 расширяется на report-канал).

**Текущая архитектура:** `_resolve_target` (decision_hub.py:1914+): warn →
subject_id trigger-пропозиции (гвард sanity_membrane.can_address); затем явная
цель → причинный адресат → Bridge 7 → SocialTargetResolver. `_build_communication`
ставит `proposition=trigger_proposition`.

**Файл:** `backend/app/services/npc/decision_hub.py`

1. В `_resolve_target` — рядом с warn-веткой (тот же стиль, тот же гвард):
   ```python
   # BUTTERFLY-01: report-канал — «сообщить жертве».
   # Для INSULTED-пропозиции заинтересованная сторона — object_id (жертва),
   # не subject_id (оскорбитель). Интенты: talk/spread_rumor/warn.
   if intent in ("talk", "spread_rumor", "warn"):
       _rep = getattr(epistemic_context, "report_proposition", None) if epistemic_context else None
       if _rep is not None:
           _stakeholder = str(_rep.object_id or "")
           if (_stakeholder and _stakeholder != state.npc_id
                   and can_address(state.npc_id, _stakeholder)):
               logger.info(f"[EPISTEMIC_REPORT_TARGET] npc={state.npc_id} intent={intent} target={_stakeholder}")
               return _stakeholder
   ```
   (импорт `can_address` — локальный, по прецеденту warn-ветки).
2. В `_build_communication` заменить выбор пропозиции:
   ```python
   _proposition = None
   if epistemic_context and hasattr(epistemic_context, 'trigger_proposition'):
       _proposition = epistemic_context.trigger_proposition
   # BUTTERFLY-01: report-пропозиция — фолбэк, trigger (угроза) приоритетен.
   if _proposition is None and epistemic_context is not None:
       _proposition = getattr(epistemic_context, "report_proposition", None)
   ```

**Что НЕ менять:** PROACTIVE_INTENTS, формулы скоринга, SocialTargetResolver,
warn-таргетинг по subject, `_get_rel_value`, прочие ветки `_resolve_target`.

**Движение данных:** idle-тик → Люся: scores{spread_rumor: базовые+0.45} → winner spread_rumor → target=tavern_keeper_tornin → `CommunicationIntent(intent_type="spread_rumor", target_id=tornin, proposition=(player,INSULTED,tornin))`.

**Тесты до:** `pytest backend/tests -k "decision_hub or s197 or targeting"`.
**Тесты после:** новый `backend/tests/micro/test_butterfly_report_targeting.py`:
1. Люся + report_proposition → `_resolve_target("spread_rumor", ...)` == tornin;
2. Торнин (report у него None) → прежнее поведение;
3. `_build_communication` несёт report-пропозицию;
4. object==self → цель не выбирается (гвард).
**Регрессия:** `pytest backend/tests -k "decision"`.
**Критерий завершения:** CommunicationIntent Люси адресован Торнину и несёт пропозицию оскорбления.

---

### ЭТАП 5. Cold-start доставки клейма (замыкание G4)

**Игровая функция:** NPC может **впервые** сообщить другому NPC содержательный
факт: клейм самодостаточен (пропозиция = содержание), общая история диалога не
нужна. Если цель далеко — NPC сначала подходит (существующее approach-движение).

**Текущая архитектура:** ADR-O-342 STM Hard Contract в трёх местах:
post_decision.py:124–136 (понижение intent→approach), task_scheduler.py:683–690
(понижение при резолве цели), dialogue_executor.py:406–413 (понижение при
генерации). Исключения: greeting/approach/warn/intimidate. `spread_rumor`
сейчас понижается ВСЕГДА при пустом STM → бесконечный approach-loop.

**Файлы:**

1. `backend/app/services/phases/post_decision.py` (главная точка, ~:126):
   ```python
   _CLAIM_PRODUCING_INTENTS = {"warn", "intimidate"}
   _PROP_CARRY = getattr(intent, "proposition", None) is not None
   if (not _stm_check and _intent_type not in ("greeting", "approach")
           and _intent_type not in _CLAIM_PRODUCING_INTENTS
           and not (_PROP_CARRY and _prop_target_in_reach(ctx, intent.speaker, _target_id))):
       ... demote to approach ...
   ```
   Новый приватный хелпер в том же файле:
   ```python
   def _prop_target_in_reach(ctx, speaker_id: str, target_id: str) -> bool:
       """BUTTERFLY-01: клейм доставляем, если адресат в пределах речи
       (SSOT exposure 'normal' = 6.0 м, domain/communication.py) и в той же
       локации. Иначе — approach: NPC сначала подходит (существующее движение)."""
   ```
   Реализация: позиции из `ctx.scene_state["npc_positions"]`; оба в одной
   локации (`position`-строка до «:») и евклидова дистанция `local_position` ≤ 6.0.
   Любая ошибка/отсутствие данных → False (fail-closed → approach).
2. `backend/app/services/execution/dialogue_executor.py` (~:409): в hard-contract
   условие добавить `and not getattr(req, "proposition", None)` — исполнителю
   тоже разрешаем клейм без STM (симметрично пост-решению).
3. `backend/app/services/game_loop/task_scheduler.py` (~:688): то же условие в
   ветке резолва цели — `and not getattr(task.payload, "proposition", None)`.

**Что НЕ менять:** сам контракт ADR-O-342 для talk без пропозиции; понижение
в approach; SleepGuard; речевой пейсинг SpeechScheduler.

**Движение данных:**
```
Тик N:   Люся (кухня) → spread_rumor+prop, Торнин 12.8 м > 6 → approach (движение к стойке)
Тик N+k: Люся ≤6 м от Торнина → spread_rumor+prop НЕ понижается → DialogueExecutor
```

**Тесты до:** `pytest backend/tests -k "post_decision or stm or o342"`.
**Тесты после:** новый `backend/tests/micro/test_butterfly_cold_start.py`:
1. пропозиция + цель в 6 м → intent сохраняется;
2. пропозиция + цель в 12 м → approach;
3. talk без пропозиции, пустой STM → approach (прежнее поведение);
4. warn → прежнее поведение.
**Регрессия:** `pytest backend/tests -k "post_decision or dialogue_executor"`.
**Критерий завершения:** клейм-интент не понижается рядом с адресатом и понижается вдали.

---

### ЭТАП 6. Вербализация клейма + эпистемический грунтинг ответа (замыкание G5, G6)

**Игровая функция:** (а) рассказ NPC — реальная LLM-реплика, передающая клейм
своими словами; (б) реакция NPC на игрока строится на его действительных
пропозициональных убеждениях — LLM видит ровно то, что NPC знает, и сама
выбирает форму реакции (не scripted).

**Текущая архитектура:** `DialogueExecutor.execute`: `spread_rumor` →
`requires_llm_materialization == False` → шаблон. `_generate_with_router`
включает: имя/натуру/голос, crystallized beliefs (T-02), npc_npc_context (T-04),
STM-пару. Пропозициональные убеждения (EpistemicStore) в промпт не попадают.
Диалог-исполнитель конструируется в `TaskScheduler.__init__` (task_scheduler.py:61)
и лениво в `game_loop._get_task_scheduler` (game_loop.py:2216); late-binding
прецедент — `set_epistemic_wiring` (task_scheduler.py:151).

**Файлы:**

1. `backend/app/services/execution/dialogue_executor.py`:
   - `__init__(..., epistemic_store: Any = None)` + `self._epistemic_store`;
     в `set_epistemic_wiring` добавить параметр `epistemic_store: Any = None`
     (late-binding, back-compat).
   - В `execute()`, ветку детерминированной материализации:
     ```python
     elif not requires_llm_materialization(req.intent_type) and not (
         req.intent_type == "spread_rumor" and _proposition is not None
     ):
     ```
     → клейм-сплетня идёт через LLM (остальные claim-интенты — как раньше).
   - В `_generate_with_router` два новых блока:
     **(а) Вербализация передаваемого клейма** (если `req.proposition`):
     ```python
     _prop_block = _verbalize_proposition(req.proposition, ctx, _target_ctx)
     # "[Факт, которым ты делишься]: Игрок оскорбил Торнина.
     #  Передай его собеседнику своими словами."
     ```
     **(б) Эпистемический грунтинг получателя** (если `self._epistemic_store`):
     топ-3 записи владельца (conf ≥ `REPORT_CONFIDENCE_THRESHOLD`, predicate !=
     EXITS_TO, относящиеся к target или к самому NPC: `subject_id == target_id
     or object_id == owner or object_id == target_id`), каждая строкой
     `«{verbalized}»` + provenance-суффикс из record:
     - `source_type == "direct_observation"` → «(ты видел это сам)»;
     - `source_type == "testimony"` → «(тебе сообщил(а) {имя source})», и если
       `original_source_id` не пуст и ≠ source → «, исходный источник — {имя}».
     Блок: `"[То, что ты знаешь]: ...\n"` — перед `Скажи свою реплику:`.
     Хелпер `_verbalize_proposition(prop_data, ctx, target_ctx)`: словарь
     предикат→формула («оскорбил», «украл», «напал», «помог», «утверждал»);
     имена через `self._get_context(campaign_id, id).get("name", id)`;
     ASSERTS рендерить как «говорил: "…"»; любую ошибку глотать в "" (fail-open).
   - ВАЖНО: грунт — **чтение** чужого Store по владельцу задачи; записи не
     выдумываются и не фильтруются «в нужную сторону», кроме порога и релевантности.
2. `backend/app/services/game_loop/task_scheduler.py`:
   - `__init__(..., epistemic_store: Any = None)` → проброс в DialogueExecutor.
3. `backend/app/services/game_loop/game_loop.py` (`_get_task_scheduler` ~:2216):
   передать `epistemic_store=getattr(self._tick_orch, "_epistemic_store", None)`
   **[ПРОВОДКА]** (store инжектируется оркестратору в `_register_epistemic_core`
   до первого хода).

**Что НЕ менять:** DM-агента и его запреты (ADR L16), disclosure-контур P7-A,
LANG_LEAK, ResponseValidator, max_tokens, порядок блоков промпта.

**Движение данных (реакция Торнина):**
```
EpistemicStore(tornin): (player, INSULTED, tornin, source=lusya, orig=player, conf≈0.3)
→ prompt: "[То, что ты знаешь]: Игрок оскорбил тебя (тебе сообщила Люся, исходный источник — Игрок)."
→ LLM → свободная реплика: обида/шутка/игнор — решает модель.
```

**Тесты до:** `pytest backend/tests -k "dialogue_executor or disclosure"`.
**Тесты после:** новый `backend/tests/micro/test_butterfly_executor_grounding.py`
(LLM-роутер заглушается фейком, фиксирующим промпт):
1. spread_rumor с пропозицией уходит в LLM-ветку (не шаблон), промпт содержит факт;
2. talk с пропозицией не понижается (Этап 5) и содержит клейм;
3. грунт содержит запись и provenance-суффиксы (testimony + direct_observation);
4. грунт НЕ содержит записи ниже порога и EXITS_TO;
5. без epistemic_store — промпт как раньше (back-compat).
**Регрессия:** `pytest backend/tests -k "executor or dialogue"`.
**Критерий завершения:** промпт исполнителя содержит клейм и его происхождение;
шаблонная материализация spread_rumor с клеймом не используется.

---

### ЭТАП 7. Перцепционная целостность: звук-гейт памяти = SSOT радиус (замыкание G7)

**Игровая функция:** NPC вне LoS запоминает событие игрока, только если оно
физически «долетает» — громкость события задаётся SSOT-таблицей перцепционных
радиусов, а не жёсткой константой.

**Текущая архитектура:** `NpcTickPipeline.run` (npc_tick_pipeline.py:185–215):
NPC без LoS, но «в звуке» (`sound_reach(15.0, ...) >= dist`), пишет память о
событии. 15.0 — жёсткая константа; у события есть SSOT радиус
(`ACTION_PERCEPTION_RADIUS`: player_insults=10.0, dialogue=6.0, …,
domain/constants.py:33–49). На карте таверны kitchen↔behind_bar ≈ 12.8 м —
Торнин «запоминал» оскорбление, не слыша его (ложное знание).

**Файл:** `backend/app/services/npc/npc_tick_pipeline.py` (~:207):
```python
from app.domain.constants import action_perception_radius
_sound_base = action_perception_radius(
    str(getattr(state.hub_event, "event_type", "") or "")
)
_has_sound = sound_reach(_sound_base, state.scene_state) >= _dist_to_player
```
(Резолвер возвращает 15.0 для неизвестных типов — поведение для них не меняется.)

**Что НЕ менять:** LOS-ветку (полный пайплайн), саму таблицу радиусов,
`apply_perception_memory`, `sound_reach`.

**Тесты до:** `pytest backend/tests -k "npc_tick or perception"`.
**Тесты после:** новый `backend/tests/micro/test_butterfly_sound_gate.py`:
1. player_insults, дистанция 12.8 м, вне LoS → памяти НЕТ;
2. та же сцена, дистанция 8 м → память есть;
3. неизвестный тип события → прежнее поведение (15 м).
**Регрессия:** `pytest backend/tests -k "npc_tick_pipeline or sound"`.
**Критерий завершения:** дальний NPC не получает память об оскорблении.

---

### ЭТАП 8. Реальная покупка пива игроком (замыкание G8)

**Игровая функция:** «Продай мне пиво» проходит через существующую экономику:
SSOT-профили (`EconomicProfile.gold/goods/stock_for_sale`), SSOT-цены
(`GOODS_PRICES`), атомарный обмен (тот же контракт L-W3/L-W4, что
`settle_order`), событие TRADE, доход продавца через `EconomyTracker`.

**Текущая архитектура:** распознавание покупки УЖЕ есть — `RulesSubscriber`
(`_TRADE_ACTIONS` содержит «пиво», fallback на архетип трактирщика :115–131).
Исполнение — имитация (−5G в `body_state.money`, без товара). WORK-вертикаль
умеет настоящий settle, но только для NPC-покупателей и флагово.

**Файлы:**

1. **Новый** `backend/app/services/economy/player_purchase.py` — единственная
   роль: синхронная покупка игрока через SSOT-экономику (переиспользует
   `GOODS_PRICES`, модель `Transaction`, паттерн атомарности `settle_order`):
   - `_GOOD_LEXICON = {"пиво": "ale", "пива": "ale", "пивом": "ale", "эль": "ale", "эля": "ale"}`
     — семантический мост «слово игрока → SSOT-товар» (зерно будущего USL-словаря).
   - `@dataclass(frozen=True) PurchaseOutcome: handled, success, good, seller_id, payment, fail_reason, order_id`.
   - `try_execute_player_purchase(*, raw_input, target_id, all_npcs_raw, campaign_id, profiles, economy_tracker, event_bus, tick) -> Optional[PurchaseOutcome]`
     - вернуть `None`, если в тексте нет товара из лексикона (не наша забота);
     - продавец: `target_id`, если у него есть товар; иначе fallback на архетип
       tavern_keeper/merchant (зеркало rules_subscriber.py:115–131);
     - валидация ДО мутаций: stock ≥ 1, gold ≥ price ( иначе handled+fail_reason
       — честный отказ, события не публикуются);
     - атомарно: `seller.stock_for_sale[good] −= 1`, `player.goods[good] += 1`,
       `player.gold −= price`, `seller.gold += price`;
     - `Transaction(PURCHASE, COMPLETED, ...)` в возвращаемый outcome;
     - `economy_tracker.record_income(seller, price)`;
     - `event_bus.publish(EventDTO(event_type="trade", source="player",
       payload={buyer, seller, goods, payment, order_id}))` — наблюдаемость.
   - Детерминизм: без RNG, id заказа `pp_{tick}_{buyer}_{seller}_{good}`.
2. `backend/app/services/game_loop/turn_pipeline.py` (`_finalize_pipeline_and_build_dm_frame`,
   перед `RulesSubscriber().handle(...)`, внутри ветки RESOLVED):
   ```python
   from app.services.economy.player_purchase import try_execute_player_purchase
   _purchase = try_execute_player_purchase(
       raw_input=..., target_id=shared_context.player_target_id,
       all_npcs_raw=_ctx.all_npcs_raw, campaign_id=campaign_id,
       profiles=self._svc.get_or_create_economic_profiles(campaign_id),
       economy_tracker=self._svc.economy_tracker,
       event_bus=get_event_bus(), tick=shared_context.current_tick or 0)
   if _purchase is not None:
       _rules_snapshot["trade_handled"] = True   # имитация в RulesSubscriber отключается
   ```
3. `backend/app/services/events/rules_subscriber.py` — в `_handle_social` начало:
   ```python
   if snapshot.get("trade_handled"):
       _semantic_action = "INTERACT"   # покупку обработала SSOT-экономика
   ```
   (деньги списываются один раз; социальные эвристики комплиментов не тронуты).
4. `config/npc/archetypes/tavern_keeper.json` — `"carried_objects"` добавить
   `"ale"` (после "food"). Проекция `stock_for_sale` подхватит автоматически
   (service_factories.py:118–142, `is_physical_object("ale")` — проверить тестом).
   **Это игровые данные, не код** — геймдизайнер может откатить/изменить количество.

**Что НЕ менять:** WORK-вертикаль NPC-заказов, `GOODS_PRICES`, StateApplicator,
`body_state.money` (двойной денежный контур — известный долг, фиксируется
отдельной ревизией; реальная покупка живёт в SSOT `EconomicProfile`).

**Движение данных:**
```
«Продай мне пиво» → player_interacts (RESOLVED) → player_purchase:
  goods: tornin.stock_for_sale{ale:1→0}, player.goods{ale:0→1}
  gold:  player −0.01, tornin +0.01   (SSOT-цена ale=0.01)
→ EventDTO("trade") → RulesSubscriber: trade_handled → money-имитация не срабатывает
→ STM Торнина содержит просьбу игрока (dm_phase:184) → LLM отвечает в контексте.
```

**Тесты до:** `pytest backend/tests -k "rules or trade"` (см. также
`backend/tests/gameplay/test_f1_trade_materialization.py` — не трогаем).
**Тесты после:** новый `backend/tests/gameplay/test_butterfly_player_purchase.py`:
1. успех: сток −1, товар у игрока, золото обеих сторон, событие trade, income;
2. нет стока → handled+fail, мутаций нет;
3. нет золота → handled+fail;
4. без товара-слова в тексте → None (rules живут как раньше);
5. trade_handled отключает money-дельту RulesSubscriber;
6. "ale" попадает в stock_for_sale трактирщика из конфига.
**Регрессия:** `pytest backend/tests/gameplay/test_f1_trade_materialization.py`
и `pytest backend/tests -k "rules_subscriber"`.
**Критерий завершения:** после «Продай мне пиво» у игрока в `goods` есть `ale`,
сток Торнина уменьшился, у Торнина доход, событие trade в журнале.

---

### ЭТАП 9. Лексикон: «жлоб» (замыкание G9)

**Файлы:** `backend/data/insults_ru.json` — добавить корень `"жлоб"` в тот же
массив, где «свинья»/«хам». Если тестовая фикстура
`backend/tests/fixtures/campaign_open_road/insults_ru.json` существует —
зеркально добавить туда же (тесты читают фикстуру, прод — `backend/data`).

**Тесты после:** `backend/tests/micro/test_butterfly_lexicon.py`:
`DMRouter._is_directed_insult("Трактирщик свинья и жлоб")` → True;
`"...жлоб"` в длинной фразе без направленности → по существующим правилам
короткой фразы (задокументировать поведение, ничего не менять в эвристике).
**Критерий завершения:** обе формулировки из сценария классифицируются оскорблением.

---

### ЭТАП 10. Интеграционный прогон BUTTERFLY-01

См. `scripts/butterfly01_experiment.py` (добавляется роем) и раздел 7 ТЗ:
последовательность `new → state → action(подойти к Люсе) → action(оскорбление)
→ idle_tick/skip_time (N ≥ 5 тиков) → проверка epistemic_records →
action(подойти к стойке) → action(«Продай мне пиво») → сбор реплик/состояний`.
LLM — production-путь `ModelRouter → LlamaCppProvider(server)`, сервер
поднимается мостом `scripts/zai_llm_bridge.mjs` (OpenAI-совместимый
`/v1/chat/completions` + `/v1/models` на localhost:8181).

**Критерии успеха** — три уровня из раздела 9 ТЗ; журнал — `BUTTERFLY-01_SESSION_REPORT.md`.

---

## 4. Сводная таблица файлов

| Файл | Тип | Этап |
|---|---|---|
| backend/app/domain/epistemology.py | МЕХАНИКА | 1, 3 |
| backend/app/services/npc/belief_revision_engine.py | МЕХАНИКА | 1 |
| backend/app/services/events/claim_event_subscriber.py | МЕХАНИКА | 1, 2 |
| backend/app/services/npc/epistemic_store.py | МЕХАНИКА | 1 |
| backend/app/services/game_loop/game_loop.py | ПРОВОДКА | 2, 6 |
| backend/app/services/npc/epistemic_context_resolver.py | МЕХАНИКА | 3 |
| backend/app/services/npc/decision_hub.py | МЕХАНИКА | 4 |
| backend/app/services/phases/post_decision.py | МЕХАНИКА | 5 |
| backend/app/services/execution/dialogue_executor.py | МЕХАНИКА | 5, 6 |
| backend/app/services/game_loop/task_scheduler.py | ПРОВОДКА | 5, 6 |
| backend/app/services/npc/npc_tick_pipeline.py | ФИКС ЦЕЛОСТНОСТИ | 7 |
| backend/app/services/economy/player_purchase.py | НОВЫЙ | 8 |
| backend/app/services/game_loop/turn_pipeline.py | ПРОВОДКА | 8 |
| backend/app/services/events/rules_subscriber.py | ПРОВОДКА | 8 |
| config/npc/archetypes/tavern_keeper.json | ДАННЫЕ | 8 |
| backend/data/insults_ru.json (+fixture) | ДАННЫЕ | 9 |
| scripts/butterfly01_experiment.py, scripts/zai_llm_bridge.mjs | ИНСТРУМЕНТ | 10 |

## 5. Что запрещено менять в любом этапе

- `RelationshipStore` и его WriteGate (S188), TruthState, канон.
- Формулы reliability/threshold без отдельной ревизии.
- DM-агента: `lint_epistemic_boundary` (§17) должен продолжать проходить.
- Determinism: ни `random.*`, ни wall-clock в симуляции (§15).
- KernelRNG-протокол, EventBus identity, EventDTO default radius sentinel (ADR-148).
- WORK-вертикаль NPC (ADR-O-391), F1-тест торговли.
- Объём: никаких попутных рефакторингов.

## 6. Риски и откат

Каждый этап — отдельный коммит `BUTTERFLY-01 S<N>: <название>`; откат
`git revert <commit>` изолирован. Наибольший регрессионный риск — Этап 7
(перцепция): если IPT по перцепции падает, откатить S7 и провести эксперимент
с игроком дальше 15 м от Торнина (в таверне таких позиций нет — тогда
зафиксировать архитектурное противоречие в отчёте, не обходить скрытой логикой).

---

# ЧАСТЬ II — R2: УНИВЕРСАЛЬНЫЕ МЕХАНИКИ ОТКРЫТОГО МИРА

**Основание:** SWARM CORRECTION — BUTTERFLY-01-R2 («От сценария для игрока к
универсальным механикам открытого мира»). Аудит коммитов BUTTERFLY-01
(`ce7c225`, `6dff104`, `b7f930f`, `1a8dee8`) + production-путей. Коммит R2:
`de0abe5`.

## R2.0. Главный принцип

**ENIGMA не содержит отдельного набора игровых механик для игрока и отдельного
для NPC.** Различается только источник намерения:

- игрок формирует намерение через собственный ввод (текст, разрешённый в
  лексиконе мира);
- NPC — через потребности, характер, убеждения, цели и обстоятельства
  (desire → DecisionHub → CommunicationIntent).

После формирования намерения оба проходят **один доменный механизм исполнения**
(заказ → settlement). Разрешено два адаптера ввода намерения (Player Intent
Adapter / NPC Intent Adapter) — и запрещены две независимые торговые логики.

Закреплённая формула (вердикт заказчика): **«Предприятие владеет функциями и
ресурсами. Объекты предоставляют физические возможности. NPC получают
полномочия через роли. Намерения исходят от самостоятельных субъектов».**

## R2.1. Ответы аудита: что фактически создал BUTTERFLY-01

| Вопрос аудита R2 | Ответ (до R2) | Статус |
|---|---|---|
| `player_purchase.py` — тонкий адаптер? | НЕТ: полная торговая логика (валидация, обмен, доход, событие) — дубликат `settle_order` | 🔴 → исправлено |
| Единый механизм заказа/исполнения? | WORK-вертикаль есть, но: флаг OFF, покупатель только NPC | ⚠️ → исправлено |
| Игрок и NPC через один механизм? | НЕТ: два параллельных исполнения | 🔴 → исправлено |
| Отдельная бизнес-логика покупки игрока? | ДА (player_purchase.py v1) | 🔴 → перенесено в адаптер |
| Отдельная логика покупки NPC? | Общий канал — work_orders, но недоступен игроку | ⚠️ |
| Кто владеет запасом? | NPC лично (`EconomicProfile.stock_for_sale` трактирщика) | 🔴 → исправлено |
| Где хранится товар? | В кэше профилей, вне сцены; «трактира» не существовало | 🔴 → исправлено |
| Кто распоряжается товаром? | Кто угодно, исполнивший settlement от имени продавца — прав не было | 🔴 → исправлено |
| Как товар передаётся? | Прямая мутация dict-полей профиля (логическая) | ⚠️ (остаётся; физическая материализация — Часть III) |
| Может ли любой NPC заказать из потребности? | ДА: thirst→ale / hunger→food → TRADE-интент → ORDER (флаг) | 🟢 |

Проверено трассировкой вызовов, не по названиям файлов и не по тестам:
`turn_pipeline.py:210` (адаптер игрока), `post_decision.py:110` (рождение
заказа NPC), `simulation.py:82` (ORDER→SERVE), `activity_lifecycle_service.py:253`
(SERVE-терминал → `settle_order`), `scene_factory.py` (сид предприятия).

## R2.2. Слой предприятия (новое, `establishment.py`)

Четыре сущности MVP — по формулировке заказчика:

1. **Трактир (establishment)** — предприятие: `owner_id` (смена владельца —
   правка данных, не кода), `treasury.gold` (финансы), `service_points`
   (услуги), `staff` (правила работы). Существует в
   `scene_state["establishments"]` той сцены, где работает (прецедент:
   `work_orders` — dict-ключ сцены, не новое хранилище истины).
2. **Хранилище (storage)** — имущество предприятия: `goods: {товар: количество}`.
   Учёт остатков, атомарное списание/пополнение. НЕ принадлежит личности
   трактирщика; личный `stock_for_sale` продавца остаётся каналом внезаводских
   личных продаж (торговец вне заведения).
3. **Барная стойка (service_point)** — объект обслуживания: `service_point_id`,
   `storage_id` (связь с хранилищем), `served_goods`, `revenue_to`. Принимает
   заказы, определяет точку выдачи.
4. **Персонал (staff)** — назначения `npc_id → {role, can_serve,
   can_manage_stock}`. Полномочия определяются НАЗНАЧЕНИЕМ; проверок
   `if npc_id == "lusya"` в торговой логике нет ни одной.

Права (R2 §3.2) разложены так:

| Право | Кто | Где проверяется |
|---|---|---|
| пользоваться объектом (заказать) | любой присутствующий субъект (игрок и NPC) | `create_order_direct` без ограничений личности |
| видеть внутренние запасы / изменять | `can_manage_stock` | `storage_deposit`, `storage_withdraw` |
| принимать заказ / выдавать | `can_serve` | `resolve_establishment_sale` + `storage_withdraw` |
| получать товар | покупатель заказа | settlement пишет `buyer.goods` |

Сидирование: `config/world/establishments.json` (авторские семена, класс
данных — как `config/world/factions.json`) → `seed_establishments()` —
идемпотентно, «сейв выигрывает»; вызовы: `scene_factory.create_scene_state`
(новые сцены) и `scene_init._load_or_create_scene` (самовосстановление сейвов).

🟠 **Граница честности:** service_point — свойство слоя экономики, а НЕ
WorldObject-архетип: спавн `bar` закрыт реестром v1 спавнера
(`world_object_spawner.py`: «НЕ в реестре: table/bar/stool/bed»), W2-слой
аффорансов — substrate-only (ноль runtime-потребителей). Расширение реестра =
мини-ADR (класс ADR-O-349) — Часть III. Отдельной архитектуры объектов ради
таверны не создавалось.

## R2.3. Единый путь исполнения заказа

```
Потребность/намерение            (игрок: текст→лексикон; NPC: need→desire→DecisionHub)
  → адаптер ввода намерения      (player_purchase.try_execute_player_purchase
                                 | post_decision: intent_type == "trade")
  → ВЫБОР ОБЪЕКТА ОБСЛУЖИВАНИЯ   (establishment.find_for_location + on_duty_servers;
                                  персонал = can_serve; детерминизм роль-ранг→id)
  → ФОРМИРОВАНИЕ ЗАКАЗА          (work_orders.create_order_direct — ЕДИНСТВЕННАЯ
                                  фабрика записи: Transaction PROPOSED в scene_state)
  → ПРОВЕРКА ДОСТУПНОСТИ/ПРАВ    (settle_order: resolve_establishment_sale —
                                  персонал+хранилище, иначе личный сток продавца)
  → ПРОВЕРКА СРЕДСТВ             (buyer.gold < payment → честный FAILED)
  → ИСПОЛНЕНИЕ                   (settle_order: атомарный обмен L-W3/L-W4;
                                  SERVE-деятельность — асинхронная NPC-версия)
  → СПИСАНИЕ ТОВАРА              (storage_withdraw из хранилища предприятия
                                  или личный stock_for_sale вне заведения)
  → ПЕРЕДАЧА ПОКУПАТЕЛЮ          (buyer.goods += qty — игрок ИЛИ NPC)
  → РАСЧЁТ                       (buyer.gold −p; казна предприятия +p ИЛИ кошелёк
                                  продавца +p вне заведения; record_income продавцу)
  → ФИКСАЦИЯ СОБЫТИЙ             (ACTIVITY_OUTCOME обеим сторонам, TRADE-событие,
                                  order в scene_state с via_establishment)
```

Точки входа (точные):
- Игрок: `backend/app/services/economy/player_purchase.py` →
  `try_execute_player_purchase(..., scene_state=…)`; вызов из
  `turn_pipeline.py:214` (передаёт `shared_context.scene_state`).
- NPC (автономно): `backend/app/services/phases/post_decision.py:110` →
  `create_order_from_trade_intent`; материализация `simulation.py:82` →
  `run_work_orders_pass`; терминал `activity_lifecycle_service.py:253` →
  `settle_order`.
- Фабрика/исполнение (общие): `backend/app/services/economy/work_orders.py` →
  `create_order_direct` / `settle_order` / `fail_order`.

Изменения в `work_orders.py` (R2):
1. `settle_order`/`fail_order` больше не гейтятся флагом `WORK_ENABLED` —
   гейт существования заказа (терминал есть только у рождённого заказа);
   флаг остался на рождении заказов из давления желаний NPC (L-W5-семантика
   рантайм-поведения сохранена).
2. Источник стока в settlement: хранилище предприятия (продавец-персонал,
   выручка → казну) или личный сток (вне заведения) — один механизм, два
   законных источника имущества.
3. `_sellers_for_good`: продавец желания — сначала персонал заведения, чьё
   хранилище содержит предмет, затем личные продавцы профилей.
4. `create_order_direct` — универсальная фабрика записи заказа (защита от
   коллизии id повторной сделки в одном тике — найденный тестом Б дефект
   потери записи реестра, суффикс `#k` детерминирован).

Изменения в `player_purchase.py` (R2): модуль сокращён до адаптера — лексикон
«пиво/эль», выбор контрагента (персонал заведения → названная цель → архетипный
fallback), рождение заказа общей фабрикой, исполнение общим `settle_order`
(жизненный цикл PROPOSED→ACCEPTED→COMPLETED синхронен — игрок ждёт у стойки),
публикация TRADE-события. Торговая логика из модуля удалена полностью.

## R2.4. Автономные потребности NPC (что уже работает)

- Канал давления: `needs.thirst → desire(ale, urgency) → TRADE-давление
  (npc_tick_pipeline.py:411) → DecisionHub сам решает → ORDER → SERVE →
  settlement`. Проверено реальным прогоном: Боро (посетитель, НЕ персонал)
  заказал эль на тике 0–3 и еду на тике 42 — без единой строки кода про
  «Боро» (см. тест B).
- NPC может и НЕ купить: DecisionHub легитимно выбирает другое (общение,
  жалобу) — принуждение запрещено; тест B это фиксирует как законный исход.
- «Не заказывает, потому что нет потребности» — базовое состояние (жажда
  рождается физиологией, не скриптом).

⚠️ Ресток запасов: операция `storage_deposit` есть (can_manage_stock),
автономного поведения пополнения у персонала нет — Часть III.

## R2.5. Универсальная социальная передача (проверка симметрии)

Маршрут Player→NPC→NPC→Player не является специальным: канал один —
мембрана слуха `ClaimEventSubscriber.on_claim_event` (все источники равны;
S199: игрок — полноправный наблюдатель, из слушателей не исключается) →
`BeliefRevisionEngine` (provenance: source/source_type/chain_original_source)
→ report-канал `EpistemicContextResolver` (по предикатам, не по «игроковости»).

Доказано производственными функциями (новый тест
`tests/micro/test_universal_social_symmetry.py`):
- **D:** NPC₀ рассказывает про NPC₁→NPC₂; NPC₃-свидетель получает веру
  (testimony, original_source=NPC₀), сам решает передавать (report_proposition),
  ретранслирует NPC₄ — цепочка сохраняет первоисточник NPC₀ (не ретранслятора).
- **E:** NPC передаёт NPC информацию ОБ ИГРОКЕ — получатель формирует веру
  об игроке (player — легальный subject), original_source=player, цепочка
  продолжается дальше.
- Слова игрока не имеют особого веса: reliability-провайдер не знает «игрок»;
  вес = trust(слушатель→источник-рта)/100 — тот же, что для NPC-источника.

Классы происхождения сохранены: direct_observation (ObservationSubscriber) /
testimony (речь) / интерпретация и предположение — ниже по контуру belief
revision (ADR-O-360). 🧠 direct_observation для прямой речи — будущая ревизия
(наследие BUTTERFLY-01, раздел Е отчёта сессии).

## R2.6. Тесты универсальности (новые)

| Тест | Файл | Что доказывает |
|---|---|---|
| A. Игрок заказывает пиво | `tests/gameplay/test_universal_trade.py` | заказ той же фабрикой; сток из хранилища предприятия; казна +выручка; личное имущество трактирщика не движется; персистентность через production-writer |
| B. NPC заказывает пиво | там же | посетитель НЕ из персонала: need→desire→заказ→settlement тем же механизмом; в чистом процессе — полный автономный выбор DecisionHub (законно-отказной исход не принуждается) |
| C. Игрок передаёт слух | `tests/micro/test_butterfly_*` + реальный прогон BUTTERFLY-01 с LLM (1a8dee8) | цепочка игрок→Люся→Торнин с provenance |
| D. NPC передаёт слух | `tests/micro/test_universal_social_symmetry.py` | NPC→NPC→NPC с сохранением первоисточника, без игрока в маршруте |
| E. NPC передаёт информацию об игроке | там же | вера об игроке у третьего NPC, original_source=player |
| F. Игрок и NPC используют один объект | `tests/gameplay/test_universal_trade.py` | общий сток (−2 без дублирования), общая казна, разграничение прав (посетитель не списывает/не пополняет, официант не пополняет, завхоз пополняет) |

Обновлённые под РЕАЛЬНО расширенные контракты: `test_f1_trade_materialization.py`
(сделка трактирщика в таверне = сделка предприятия: сток хранилища, казна;
личный сток/золото не движутся), `test_butterfly_player_purchase.py`
(fail-контракт общего settlement `no_stock:<good>`; честный отказ публикуется
тем же каналом ACTIVITY_OUTCOME, что у NPC).

Регрессия R2: micro 846 passed / 4 failed (s368×4 — воспроизведены на чистом
baseline-worktree `d78f0a4`); gameplay 173 passed / 5 failed (gc05×2, gc11×2,
gc27×1 — LLM-зависимые, воспроизведены на baseline); butterfly/claim/trade 51
passed; новых падений ноль.

## R2.7. Матрица возможностей (Проверка §5 R2)

| Возможность | Игрок | NPC | Механизм |
|---|---|---|---|
| Заказать еду/напиток | 🟢 (адаптер) | 🟢 (потребность→интент) | `create_order_direct` |
| Получить товар | 🟢 | 🟢 | `settle_order` → `buyer.goods` |
| Использовать доступный объект | 🟢 (стойка: заказ) | 🟢 | service_point + права |
| Общаться с NPC | 🟢 | 🟢 | dialogue/claim-контур |
| Передавать слухи | 🟢 (речь=событие) | 🟢 | report-канал + мембрана |
| Получать информацию | 🟢 (S199 наблюдатель) | 🟢 | EpistemicStore |
| Изменять отношения | 🟢 | 🟢 | SocialEngine/RelationshipStore |
| Реагировать на оскорбления | 🟢 | 🟢 | DecisionHub S197/эпистемика |
| Распоряжаться запасами стойки | 🟢 только персонал | 🟢 только персонал | `can_manage_stock` (роль, не статус) |

Ограничения прав вытекают из свойств мира (назначение ролей предприятием),
а не из статуса «игрок»/«NPC»: посетитель-человек и посетитель-NPC одинаково
не могут списать сток (тест F), персонал-человек и персонал-NPC — одинаково
могут обслуживать.

## R2.8. Оставшиеся ограничения и архитектурные решения

| Пункт | Статус | Решение |
|---|---|---|
| `bar` как WorldObject-архетип (W2-аффорансы, W3-FSM) | 🧠 | мини-ADR на расширение реестра спавнера (ADR-O-349-класс); W2 substrate-only |
| Физическая материализация товара (кружка как WorldObject) | 🔴 | покупки передают товар логически (`goods`); физическая точка выдачи — после W2/W3 |
| Пространственная привязка стойки (заказ только у стойки) | 🔴 | service_point логический; радиус обслуживания — политика при W2-интеграции |
| Автономный ресток персоналом | 🔴 | операция есть; поведение решения — отдельная вертикаль |
| Жажда без body-оси (needs-слой только) | ⚠️ | известный долг physiology; thirst→ale живёт в desire_generator |
| Зарплатный контур персонала (казна → NPC) | 🔴 | record_income — статистика обслуживания; выплат из казны нет |
| DM-канал игроку без эпистемического грунта (L16) | 🧠 | наследие BUTTERFLY-01; ADR-кандидат |
| Global campaign-keyed кэши между лупами одного процесса | ⚠️ | пред-существующий долг; проявляется только в тестах одного процесса |
| UE-гейт при мёртвом LLM (readiness=FAILED) подавляет покупку в пайплайне | ⚠️ | контракт S-UE; при живом LLM путь RESOLVED (доказано прогоном BUTTERFLY-01) |
