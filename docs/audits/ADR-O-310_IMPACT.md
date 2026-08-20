# ADR-O-310 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-O-310` [STANDARD] **IMPACT**
# ADR-O-310 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: docs/ADR (Architecture Decision Records).md

## Changed Domains
- Decision & Locomotion (Windup добавляет задержку между решением и исполнением атаки)
- Time (Windup измеряется в тиках, не в реальном времени — §14 Law of Singular Time)

## Downstream Consumers
- `TickOrchestrator._phase_6_intent_conversion` — WindupWriteGate перехватывает ATTACK, создаёт `ActionWindup` вместо немедленной публикации EventDTO
- `TickOrchestrator._phase_7_windup_resolution` — Execution Gate: проверяет завершённые windups, публикует отложенные EventDTO
- `TickOrchestrator._pending_intents` — хранит оригинальные интенты, привязанные через `held_intent_id` (ADR-310.1)
- `intent_event_adapter.py` — не затронут напрямую (работает с уже выпущенными EventDTO)

## Runtime Impact
- **RAM:** `Dict[Tuple[str, str], List[ActionWindup]]` на уровне TickOrchestrator. Незначительно — один windup ≈ 200 байт, типичное количество < 10
- **Latency:** +1 итерация по `_windup_registry` в Фазе 7. O(windups_count), пренебрежимо
- **Determinism:** Windup использует `tick_number` из TickContext (не wall-clock), соблюдая §14

## Sandbox Tests
- Фаза 0 — документальная гигиена, runtime-тесты не требуются
- Будущий тест: `test_windup_delays_attack_by_n_ticks` (верификация что EventDTO не публикуется в Фазе 6 при windup)

## Rollback
1. Удалить `_windup_registry`, `_pending_intents` из `TickOrchestrator.__init__`
2. Удалить `_phase_7_windup_resolution` вызов из `_run_core_phases`
3. Удалить WindupWriteGate блок из `_phase_6_intent_conversion` (строки ~1680-1730)
4. ATTACK EventDTO будут публиковаться немедленно в Фазе 6 (старое поведение)



Files: N/A
