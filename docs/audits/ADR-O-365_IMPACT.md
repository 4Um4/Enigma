# ADR-O-365 Impact Audit
> Детальный аудит ОДНОГО ADR. Единый атлас: `docs/ADR (Architecture Decision Records).md`.
> Спринт-владелец: S203.4 (Stage 2A). Вердикты Мастера: D-1…D-9.

## Changed Domains
- Поведенческое владение (task/windup/sleep исполнители → единый реестр)
- Арбитраж (INTERRUPT-вердикт, приоритетная политика, INCUMBENT_PROTECTED)
- Commitment-контракт (priority, priority_policy_version, blocked_since_tick, fail_reason)
- Persistence Н-40 (RAM-структуры оркестратора → scene_state)
- Гигиена Н-42 (удаление мёртвого дубля domain/tasks.py)

## Downstream Consumers
- npc_tick_pipeline (has_behavioral_owner — проекция; поведение меняется только при mirrors ON)
- TaskScheduler / DialogueQueue / SpeechScheduler (точки терминальных зеркал, outbox)
- SleepLifecycleService / CouplingResolver (liveness-сигнал reconciliation; сами не пишут реестр)
- ADR-O-364-зона (task_scheduler/dialogue_queue/dialogue_executor): границы развёдены —
  queue-side priority/persistence остаётся их зоной; coordination-note приложена
- WorldSnapshotBuilder (active_commitments заморозка — новые поля проходят deepcopy)
- ReplayRecorder (новые поля сериализуются; priority вне ID)

## Runtime Impact
- RAM: +6 полей на commitment (history cap 10/NPC) → < 1 KB/NPC
- CPU: policy O(1)/кандидат; sleep-reconciliation O(N)/тик; дренаж O(outbox); бюджет гейтится p95 +≤10%
- Latency терминалов task: ≤1 idle-цикл (outbox-дренаж) — покрывается grace=25

## Sandbox Tests
- Юнит: приоритетная политика (пороги, взаимный INTERRUPT невозможен — скаляр),
  non-supersede, terminal-mapping, BLOCKED-timeout, projection-инвариант D-9, round-trip §12
- A/B 200 тиков двухстадийный (Stage A / Stage B), зонды print() по Часть VIII.5
- Повтор SUPERBOX-ACTION-INTEGRITY: Y6 закрыт (сон = executor 'sleep' С commitment)

## Rollback
- S203.4_OWNERSHIP_MIRRORS=OFF ∧ S203.4_ARBITER_INTERRUPT=OFF → байтовая идентичность текущему
- Каждый флаг откатывается независимо; константы/поля инертны без флагов
- Удаление dom/tasks.py: git revert (ноль ссылок — риска нет)
- Дренаж outbox: пустой outbox = no-op