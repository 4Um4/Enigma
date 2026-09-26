# ADR-O-406 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- agentness/agency — новая ось `ControlSource` (PLAYER_INPUT / NPC_DECISION / SCRIPTED_SYSTEM / COMBAT_CONTROLLER); единственная точка знания 'player'-строки — `domain/control_source.py`
- communication — гварды creation-time на обеих фабриках CommunicationIntent
- tick pipeline (Фаза 5) — фильтр decision population по ControlSource
- player epistemics (косвенно) — устранён ghost-источник ложных claim'ов и ложных записей памяти NPC

## Downstream Consumers
| Потребитель | Эффект | Статус |
|---|---|---|
| dialogue_executor / dialogue_materializer | задачи owner_id="player" больше не рождаются → NPC_SPOKE(source="player") = 0 | регресс S292 |
| dialogue_memory_subscriber | память NPC больше не отравляется ghost-репликами игрока | upstream мёртв |
| claim_event_subscriber | эпистемика NPC больше не ревизируется несуществующими репликами | upstream мёртв |
| npc_dialogue_subscriber (S290-гард) | источник мёртв; гард остаётся страховкой до нормализации RCE-пути | tech-debt F2 |
| post_decision (Фаза 6) | communication_intents от player не приходят | регресс S292 |
| PLAYER_SPOKE / phase_1_input | авторский канал игрока НЕ затронут | регресс: журнал self вербатим |
| RelationshipStore | rel-update от ghost-спикера прекращаются | регресс |
| M17 recognition | ghost-ключи от player-спикера прекращаются; display-name дефект RCE остаётся | F2 |

## Runtime Impact
- RAM: +~1 KB (enum + frozenset в domain)
- Tick latency: пренебрежимо (O(1) resolve_control_source на актора в фильтре + гварды)
- Семантика уровня 0 (вердикт Мастера): player исключён из `_alive_npcs` — автономные дельты/память/L1/idle_pressure аватара больше не порождаются тиком; психика аватара живёт на player-input pipeline (ADR-TZ08-1) + AvatarStateApplicator (S208; DEBT-R10 → активная онтология). Player остаётся в мире: позиции, восприятие NPC, цели, события, Фаза 1.

## Sandbox Tests
- `backend/tests/IPT.py::INV-PLAYER-AUTHORSHIP` — статическая защита 4 якорей (CRITICAL): удаление любого слоя = красный
- Регресс S292 (runtime): player_in_decisions=0 за ~124 тика; reactive audience='player' подтверждён (thief_shadow TRADE → 'player heard thief_shadow'); attack-реакции NPC живы после провокации; NPC-NPC диалоги живы
- SUPERBOX-сценарий для COMBAT_CONTROLLER — будущая сессия (бой)

## Rollback
1. Вернуть ветку `== "player"` в фильтр `_alive_npcs` (tick_orchestrator)
2. Удалить гвард из `_build_communication` (decision_hub)
3. Восстановить безусловную attack-фабрику (убрать else-структуру)
4. Удалить детектор перед `return TickMutation` (npc_tick_pipeline)
5. Удалить `inv_player_authorship` (тело + регистрация) из IPT
Поведение возвращается к pre-F1 (S290-гард журнала сохраняется). Файл control_source.py можно оставить — без потребителей неактивен.

## Archaeology (S292)
- Симптом → причина: ghost-реплика («Тень — это как зеркало…») = LLM-перефраз ввода игрока через DialogueExecutor; механизм: player ∈ `_alive_npcs` (tick_orchestrator:2092, специальная ветка) без гварда авторства
- Зонд `[DIAG_AUTHORSHIP]` (3 точки, снят): tick=2 — `[INTENT] speaker='player' audience='thief_shadow' intent=CHANGE_ROLE` — канал (a) подтверждён рантаймом
- Эскалации в F2: RCE display-name вместо npc_id (M17-confirmed мимо → «Незнакомец»); двойной калькулятор дистанции до игрока (eavesdrop 999.0 vs membrane валид → реплика Тени не в журнале); узел графа как слушатель (`tavern:exit_south heard` + rel update на дверь); нулевые rel update в диалогах; солилокви → журнал как overheard; doc-drift S118-комментария (post_decision:97); S290-гард + `[DIAG-LLM]` print — реестр снятия F2

## Topology (yaml-first, РЕЖИМ РАБОТЫ §3.1)
- authority.yaml: node `ControlSource` (nodes) + constraint CRITICAL `FORBIDDEN: AutonomousAuthorship` (constraints) добавлены; `python build_graph.py` перегенерирован. code_ref нашей записи — метод-уровень (дрейфо-устойчивый).
- TECH_DEBT (вне зоны F1): line-refs decision_hub.py в authority.yaml дрейфнули ДО F1 на сотни строк (yaml `:966-994` → факт `def _emotion_modifier` :1570; yaml `:1039-1049` → факт `def _context_relevance` :1431; refs relationship_cache (`:789, :935`) дословно не находятся). Массовая ревизия line-refs authority.yaml = отдельная задача (предположительная причина — рефакторинги после написания yaml; validate_doc_refs.py покрывает только .md, yaml-refs вне CI).
- Инцидент ремонта (S292, чужая зона): `world.yaml` был невалиден (build_graph ParserError :38/:67) — W3/W4-merge (ADR-O-376) вставил 4 узла внутрь constraint-последовательности и продублировал top-level `edges:`/`constraints:` (last-wins PyYAML = тихая потеря W1/W2-топологии). Ремонт: секции слиты (nodes 4→8, edges 3→10, constraints 6→10), ноль потерь контента, семантика verbatim. Попутное наблюдение W-зоне: description «Runtime-writers: 0» стух с появлением Spawner — их зона.

## ⑤-следование (rel update, S292-вердикт: канал НЕ баг)
- Цепь тона жива end-to-end; NEUTRAL=(0.005,0) — дизайн; RCE получил явный provenance `tone_provenance="rce_default_unmeasured"`.
- ⑤-AFFECT (новая сессия): production-эмоция интентов всегда «нейтрально» — `state.emotion.value` (decision_hub :868/:2062) не отражает Affective Pipeline (Фаза 9.1 → эмоция → интент). Вход: верифицировать EmotionTransition → NPCState.emotion → DecisionHub.
- ⑤-B (новая сессия): WARN-интенты с целью-узлом графа воспроизводятся каждый тик (non-actor skip ~60/мин = симптом liveness-дыры в _resolve_target/post_decision для не-акторных целей); парные NPC_SPOKE-публикации (Δ~12мс) — проверить дедуп.

## F3 (БАГ-1, S292): lifecycle-контракт топологии
- INV-SNAPSHOT-TOPOLOGY поймал load/idle-путь рождения сцены (game_loop:1122 прямая initialize_scene мимо ensure) ДО проды — гейт отработал по назначению; фиксы: heal в ensure + 2 обёртки прямых фабрик + birth-точка reset_campaign. Четыре точки рождения, один источник, идемпотентно.
- БАГ-4 (зарегистрирован Мастером): «Продолжить» доступна после завершения кампании выходом через boundary → загрузка в чужую локацию. Предварительный домен: campaign_lifecycle.load_campaign/session-state + FE-грейтинг кнопки. Слот: сразу после F3.