# ADR-O-418 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- RELATIONSHIP: новый `DeltaDomain.RELATIONSHIP` + `NeedDeltaPayload` (ADDITIVE; кламп [0,1] — на apply-стороне стора), policy-реестр + `_DOMAIN_PAYLOAD_MAP`.
- EVENTS: +4 needs-touching EventType (`FLIRT_ACCEPTED/FLIRT_REJECTED/INTIMATE_ENCOUNTER/INTIMATE_REJECTION`); канонический реестр 21 (`RELATIONSHIP_EVENT_REGISTRY`) + `RELATIONSHIP_NEEDS_TOUCHING_EVENTS` в domain-слое.
- STATE-MUTATION: `StateApplicator.apply_relationship_deltas` — единственный путь RE-дельт (per-delta `Cause` из `payload.source_event_id`=UUID; `MissingProvenanceError`/`ArchitecturalViolationError` fail-loud); гвард `apply_batch` против просочившихся RE-дельт.
- ФАЗЫ 8/9/10: `RelationshipEventSemantics` (pure Phase8Handler, dormant за `RELATIONSHIP_EVENTS_ENABLED` default OFF) в кортеже reduction; сплит ДО DRSL-агрегации в обеих flush-точках (Фаза 9 integration.py — primary; Фаза 10 commit_phase — defense-in-depth LOD-пути).

## Downstream Consumers
- Ридеров NeedLevel в рантайме — 0 (первый writer; потребители — фазы G/H, RelationshipModifierResolver M3/K, полигон RE).
- `scene_state["relationship_state"]["needs"]` — новый scene_state-ключ; persistence через существующий atomic_commit_all (Foundation Freeze соблюдён, новых persistence-путей нет).
- Сигнатура `execute_reduction_phase` — обратно совместима (Optional-параметр в конец группы Optional).

## Runtime Impact
- RAM ≈ 0 (payloads живут в тике; события редки). Latency: O(событий) на drain/сплит.
- Флаг OFF: без подписок, drain пуст, ранний выход `_execute_handler` — байт-идентичный тик (CONTROL-группа SUPERBOX доказана).

## Sandbox Tests
- micro: `backend/tests/sandbox/micro/test_re_event_semantics_m2d.py` (12: редукция 4 профилей, registry-guard, UUID-provenance, apply round-trip через Store, payload-map TypeError, флаг-полярность, консистентность профилей).
- SUPERBOX: `backend/tests/sandbox/SUPERBOX/scenarios/re_m2d_needs_test.py` — CONTROL no-op / TREATMENT full-chain (`frustration=0.2` read-back из персистентной сцены). GREEN 2/2.
- Манифест ADR-O-414: 4 поля DEBT→CAUSAL (proof=re_m2d_needs_test); `source_event_id` — DEBT (ридер=[RE_NEEDS]-лог, E4-класс). lint_consumer_gap GREEN (manifest=296).

## Rollback
- Функциональный: флаг OFF (байт-идентичность доказана). Демонтаж по слоям, каждый независим: tests → handler+DI (reduction/tick_orchestrator) → сплиты (integration/commit_phase) → `apply_relationship_deltas` + гвард → enum/payload/реестр → манифест-строки.

## Уроки сессии (в протокол)
1. **Flush-топология:** единственная живая drain-точка полного тика — Фаза 9 (integration.py, DSTC-барьер); flush commit_phase исполняется только на LOD-пути (`if not tick_fully`). Новый домен = сплит во ОБЕИХ точках; регистрация в `DELTA_POLICY_REGISTRY` не защищает — `aggregate_deltas` при merge не переносит payload (silent loss).
2. **Носитель scene_state:** выбор строго по правилу коммита (`is_player_turn` → shared_context.scene_state, иначе ctx.scene_state — симметрия commit_phase). Приоритет по наличию shared_context писал в регидрированную копию, не доходящую до коммита (SPY id-доказательство: written 2465780136320 ≠ tick_scenes 2465849905920).
3. **БЫЛО-якорь** — полная уникальная строка фактического файла (2 инцидента: префикс-совпадение разрушил легитимные локальные импорты → NameError+UnboundLocalError; сфабрикованный якорь = неприменённый фикс).
4. Красные инварианты после TICK_CRASH — сначала проверка «эхо краша» (Фаза 9 оборвалась до WorldSnapshot Assembly → INV-TRAV-DICT/INV-SNAPSHOT-TOPOLOGY), потом эскалация чужой зоны.