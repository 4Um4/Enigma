# ADR-408 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- Epistemic (EpistemicContextResolver: выбор trigger_proposition; EpistemicStore.upsert: удаление мёртвой S292-мембраны)
- Decision (S197 WARN-таргетинг: цель всегда акторный subject угрозного предиката)
- Events (social_action_subscriber: ADR-O-349 — EventType.value вместо сырых строк; поведение байтово идентично)

## Downstream Consumers
- `decision_hub._resolve_target` (S197-ветка, :1995+) — читает trigger_proposition: получает гарантированно STOLE/ATTACKED-цель либо None → фоллбэк-резолв
- `npc_tick_pipeline:626` → `ThreatDesiredChangeProducer.resolve(belief_source=...)` — собственный гейт `predicate in ("ATTACKED", "OPPOSES")` (OPPOSES — мёртвое значение, observation): после фикса belief_source никогда не EXITS_TO; контракт не сужен, расширен
- `to_modifiers` (внутри резолвера) — max_confidence НЕ фильтруется; легаси-S198/диспозиции S211 не тронуты (9 старых тестов зелёные)
- `claim_event_subscriber:179` — гвард can_address остаётся как есть (прозрачен, но безвреден: триггер-фильтр стоит выше по потоку)

## Runtime Impact
- O(1) на запись: одно сравнение кортежа + один float-трекер; RAM-дельта ~0
- Latency: не измерима (0.24s на 12 тестов, включающих путь)
- Удалённый код upsert: −15 строк мёртвой ветки (логирование в недостижимой ветке)

## Sandbox Tests
- `backend/tests/micro/test_self_relevance_gate.py` — 12/12 (9 легаси + 3 GATE-TRIGGER-01)
- IPT: 48/48 (0 CRITICAL)
- SUPERBOX-014: 1 skipped (EPISTEMIC-005 deferred — независимое решение, вердикт Мастера Б)

## Rollback
- `git revert 1e564812` — единый атомарный коммит (5 файлов)
- Частичный откат фильтра: удалить константу _THREAT_PREDICATES и вернуть `_trigger_prop = record.proposition` внутрь max_conf-блока (форма до S296)
- Удаление мёртвой upsert-мембраны необратимо безвредно: ветка была недостижима (доказано статически, поведение идентично)

## Incidents (по протоколу, для истории)
- Первая версия патча содержала дефект индентации (гейт заперт внутри max_conf-условия) — пойман регрессионным тестом `test_helped_higher_conf_does_not_steal_threat_trigger` ДО коммита; исправлен до верификации. Урок: якорь БЫЛО обязан включать хвост метода/блока.
