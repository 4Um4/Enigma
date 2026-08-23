# ADR-O-363 Impact Audit
> Детальный аудит ОДНОГО ADR. Единый атлас: `docs/ADR (Architecture Decision Records).md`
> Сессия: S215 | Спринт: Stage 2A / S203.1 (shadow)

## Changed Domains
- Поведенческое владение (новый домен): commitment-слой между Intent и Traversal.
- Движение: зеркала материализации (ProjectionEngine primary + SSM fallback — dual-rail,
  ADR-O-204) / завершения (TES) / обходов (movement_engine cross-loc);
  fail-fast build_traversal_dict (Н-49).
- Snapshot: world_snapshot.active_commitments (deepcopy-заморозка владения).
- Persistance: +3 ключа scene_state (round-trip через Foundation Freeze — blob-сериализация
  обоих адаптеров подтверждена археологией; whitelist-гипотеза H-K отвергнута).

## Downstream Consumers
- S203.2 (арбитр): реестр как вход COMMIT/CONTINUE/REJECT; telemetry REJECT;
  миграция has_active_commitment (npc_tick_pipeline:470) на проекцию реестра.
- S203.3/4: interrupt-интерфейсы исполнителей; легализация обходов (Н-46a);
  TaskState-дубль (Н-42, координация с ADR-O-364 taboo на TaskState.FAILED);
  CANCELLED-продюсер (Н-45).
- S203-E (social): producer-side диалогового churn (Н-56; queue-side закрыт ADR-O-364).
- Replay/DriftLab: ключи едут в atomic_commit; ID-формула детерминирована.

## Runtime Impact
- +3 dict в scene_state (active + bounded history ≤10/NPC + ordinals).
- +1 deepcopy в build_snapshot; зеркала O(1)/событие; sweep O(active).
- Замер: A/B DriftLab — поведенческий diff=0 (латентность в шуме измерения).

## Sandbox Tests
- tests/test_action_commitment.py — 22 (FSM-матрица, ID, ordinal, cap, cause-гигиена,
  JSON round-trip, no-op флага, CANCELLED из активных фаз).
- tests/test_commitment_ssm_integration.py — 3 (born-materialization, ADR-130.1 guard,
  суперсессия осиротевшего с parent-цепочкой).
- tests/sandbox/commitment_baseline.py — измерительный прибор (200 тиков, production-контур).
- Гейты: IPT 44/44; pytest 25/25; A/B (AB=0; ON/OFF — только жизненный цикл llama-server).
- BASELINE v2 (200 тиков, tavern, 6 NPC): terminals=42 (COMPLETED 38 / INTERRUPTED 4);
  SUPERSEDED=4 (~9%); actives=2; switch_rate=0.035. Causes: proactive-social 27 (64%),
  schedule 8 (19%), need 7 (17%), random 0. Ключ: churn-источник — проактивные
  социальные интенты DecisionHub; DLG_QUEUE OVERFLOW 288/20 (Н-56) в том же прогоне
  (queue-side — ADR-O-364; producer-side — S203.2/S203-E).

## Rollback
- COMMITMENT_REGISTRY_ENABLED = False — полный no-op (все mirror_*/sweep выходят до
  мутации; доказано тестом и A/B).
- Реестр аддитивен: ни один прод-потребитель не читает его до S203.2.
- Н-49 fail-fast: единственный поведенческий фикс; откат не рекомендуется
  (возвращает класс silent-PENDING).

## As-Is карта владения traversal (вход S203.3)
| Операция | Факт |
|---|---|
| Proposal | MovementEngine (ADR-O-323) |
| CREATE (born-MOVING) | dual-rail: ProjectionEngine (primary, shadow-rail первым) / SSM.apply_change (fallback) |
| PENDING→MOVING | внутри build_traversal_dict, атомарно (PENDING виртуален, Н-50) |
| Продвижение | TraversalExecutionSystem.advance |
| MOVING→COMPLETED | TES (FSM) + самоудаление записи |
| MOVING→CANCELLED | продюсера НЕТ (обходы: engine pop Н-46a; SSM перезапись MOVING невозможна — внешний guard) |
| Удаление записи | 3 писателя: TES, SSM-GC, MovementEngine-bypass |
