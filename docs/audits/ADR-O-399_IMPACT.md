# ADR-O-399 Impact Audit
> Сессия: S270 | Дата: 2026-09-20

## Changed Domains
- TaskScheduler (worker boundary): 5 сайтов из _process_tasks_async → outbox
- DialogueQueue: task_id uuid4 → детерминированный ordering key
- idle_tick: +1 безусловный drain-вызов (рядом с drain_commitment_outbox)

## Downstream Consumers
- Подписчики EventBus (Claim/Observation/Social/Memory): исполнение переносится
  из worker-thread в main-thread на drain boundary — семантика подписчиков
  не меняется, меняется поток и момент (граница тика вместо arrival).
- EpistemicStore / RelationshipStore: тайминг записи детерминизирован.
- EconomyTracker.record_talk: вызов перенесён в drain, значения те же.
- SpeechScheduler: reset_context применяется на границе — pacing-окно
  может сдвинуться на 1 тик для failed-задач (fix-намеренное, реплики-лотерея
  25/3/0/0 S262 сужается).
- WorldSnapshot/канон-хеш: порядок recent_dialogues в тиках с гонкой
  изменится на детерминированный — это fix, не регрессия; база старых
  replay-хешей с гонками невоспроизводима и так (MISMATCH).

## Runtime Impact
- Прогноз: нейтрально. Drain = O(batch), batch = задачи завершившиеся за тик.
- RAM: outbox живёт ≤1 тик (буфер недоставленных артефактов).

## Sandbox Tests
- tests/test_worker_outbox_determinism.py (controlled-latency A/B — главный)
- tests/test_l1_chronicle_archive_idempotency.py (не задет)
- DriftLab Mode E: 2500/3000 бисекция → 10k×2

## Rollback
- git revert одной зоны: task_scheduler (outbox+drain), dialogue_queue (одна строка),
  game_loop (один вызов). Воркеры возвращают прямые эффекты; риск — только
  возврат MISMATCH, данных нет.
