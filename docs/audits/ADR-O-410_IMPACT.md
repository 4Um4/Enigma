`ADR-O-410` [STANDARD] **IMPACT**
# ADR-O-410 Impact Audit — G3 Object Action Executor (W-track, Этап 1)
> Детальный аудит ОДНОГО ADR. Единый атлас: docs/ADR (Architecture Decision Records).md (STANDALONE).
> Статус: ACTIVE — Этап 1 (исполнительное ядро) GREEN; Этап 2 (живая воля) — отдельный коммит.

## Решение
Вертикаль «intent → исполнитель → мутация мира → событие» замкнута живым
production-контуром. G3-executor — ПЕРВЫЙ легальный runtime-writer
WorldObjectStore.apply_transition (до сего дня writers=0, spawn=bootstrap-only).

## Границы (вердикты Мастера D1–D8 + И-1/В-3)
- Executor НЕ целеполагает: получает готовый STEAL(target_id=wo_*); выбор цели —
  Этап 2 (facts→Opportunity→DecisionHub).
- D4: REJECT → INTERRUPTED(INTERRUPT_G3_OBJECT_REJECT); событие НЕ публикуется —
  «событие = утверждение факта, не намерения».
- D7a: SKIP → passthrough («не утверждает, что действие исполнено; лишь не
  принимает ownership unresolved intent») — honest-zero для steal-целей без
  wo_-identity.
- D5-факт: chair-TAKE NO_OP недостижим (уже-held → NOT_FREE REJECT) —
  дубль-THEFT онтологически невозможен; NO_OP-ветвь = контракт будущих маппингов.
- Б-2 (WillpowerGate на release) — OUT OF SCOPE v1 (нет доказанного кейса).

## Changed Domains
WORLD (первый runtime-writer; Г4-цензус), SIMULATION (Фаза 7 release-ветка),
BEHAVIORAL (reason-константа терминала; зеркала не менялись).

## Downstream Consumers
- Этап 2: compute_object_target_facts (общий канал; TARGETABLE_ARCHETYPES —
  calibration policy v1 chair→TAKE; nearest+lex детерминизм; LLM не выбирает
  объекты мира).
- GC-08: harness.spawn_world_object закрывает capability-гэп роадмапа.
- W5/W6: контейнеры (INSERT/REMOVE), полные W2-кортежи.
- NEED-EXEC-1 (S304): G3 = первый живой образец грамматики INTENT→EXECUTOR→
  MUTATION — прототип для need-интентов и Фазы VI Барсука.

## Runtime Impact
OFF (default): ноль (no-op до вычислений; путь байт-идентичен — доказано
A/B-приёмкой). ON: 1 store.get + 1 apply_transition на релиз windup (мкс);
provenance — structured log. Honest-zero в production (steal-цели без wo_).

## Sandbox Tests
- tests/test_g3_executor.py (9): словарь статусов (SKIP≠PASS); OFF=no-op;
  SKIP×3; PASS-мутация (chair→HELD_BY); REJECT-контейнер; Г4-DENY
  (ArchitecturalViolationError из чужого модуля — замок экзамена).
- tests/sandbox/g3_execution_probe.py: GC-00 A/B OFF/ON — GREEN
  (ON: holder=thief_shadow, THEFT=1; OFF: holder=None, THEFT=1).
- Гейты: IPT 49/49; b1_4 exit=0; ruff clean; W-контур 222/1-pre-existing.

## Инциденты сессии (закрыты)
1. Retro-RED: файлы применены до первого прогона — красный снят изоляцией
   модуля (ImportError-прогон), цикл замкнут документально.
2. Г4-DENY-шторм (19 failed): conftest dual-name (tests.X vs X) — тройное
   правило матча (прецедент PK-guard npc_state:601-603).
3. IPT 48/49: smoke-часть INV-WORLD-OBJECT-TOPOLOGY исполняется как __main__
   — цензус-исключение класса E2.0-c (guard работал правильно).
4. loc-ключ сцены: константа харнесса ≠ фактический ключ (мина S242) —
   резолв из живого post-tick слепка (S242-fix-прецедент).
5. Ruff fix=true автофиксы ×2 — форматные, приёмка повторно GREEN.

## Эскалации (чужие зоны, закон №15)
- test_action_commitment::TestS2B6OnsetTransition::test_eligible_onset_writes_fact
  KeyError 'coupling_profile' — pre-existing (S236-фикстура vs эволюция
  SleepLifecycleService в S246–S304); вне диффа G3; владельцу серии.

## Rollback
W3_G3_ENABLED=OFF → no-op. Полное удаление: g3_executor.py + врезка Фазы 7
(P3–P6) + Г4-строки стора + reason-константа + тесты/проба/harness-метод.
Стор возвращается в состояние «субстрат с 0 callers». Ноль миграций:
PASS-мутации — данные в scene_state (atomic_commit), откат = пересоздание сцены.
