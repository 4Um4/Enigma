# ADR-O-379 Impact Audit — PerceptualKernel Write Guard (L8.2)

> Детальный аудит ОДНОГО ADR. Единый атлас: docs/ADR (Architecture Decision Records).md (DOM-03, L8.2).
> Сессия: S243 (AG1). Runtime-часть в истории (параллельная серия, full-save); настоящий файл — документальное закрытие по мандату 11.4.

## Решение
PerceptualKernel.__setattr__ — caller-based write-guard субъективного состояния восприятия (паттерн ADR-WRITE-GUARD / NPCState). Прямые присваивания PK-полей вне цензуса → ArchitecturalViolationError("perceptual_kernel.<field>", <caller>).

## Whitelist (дословно из кода, npc_state.py:591-603)
| Модуль | Поля | Основание |
|---|---|---|
| app.models.npc_state | * | self: dataclass __init__ + _pk_from_dict (round-trip) |
| app.services.npc.state_applicator | * | ЕДИНСТВЕННЫЙ prod-писатель: применение perception-дельт/директив, клампы [0..1] (state_applicator.py:1186-1236) |
| tests.sandbox.SUPERBOX.npc_sandbox | * | тест-исключение (цензус E2.0-c) |
| tests.sandbox.system.test_t06_belief_pipeline | * | тест-исключение (цензус E2.0-c) |
| sandbox.stress.test_authority_erosion | * | стресс-тест давления в ядре (вариант __name__ без префикса) |
| tests.sandbox.stress.test_authority_erosion | * | то же, канонический путь |

ЗАПРЕЩЕНО к внесению: causal_state_test — его D2-атака обязана поднимать ArchitecturalViolationError (замок экзамена B0).

## Changed Domains
- Восприятие (PK-поля: threat_gradient, trust_gradient, uncertainty, anomaly_score, aggression_inhibition, compliance_bias, initiative_suppression, recent_directive).
- Закрывает DEBT-R9 (dict-содержимое NPCState не охранялось) для PerceptualKernel-слоя.

## Provenance
Экзамен B0 (E2.0-c), D2-атака: pk.threat_gradient = 0.8 мимо DeltaGate/StateApplicator проходила молча → канал state→decision был бы нефальсифицируем. Guard = замок экзамена. История: дубль __setattr__ (двойное применение патча, латентное затенение) устранён до терминального коммита; цензус расширен authority_erosion (оба варианта __name__) — расширение документировано в S243.

## Downstream Consumers
- Writers (цензус): только перечисленные.
- Readers (не затронуты): DecisionHub (risk_penalty = threat×risk×0.9; escape_salience = threat×0.8 → FLEE×1.6 для робких; threat>0.5 → is_provoked), AffectiveIntegrator, проекции manifestation/verbalization.
- Персистенция: _pk_from_dict / round-trip не менялись.

## Runtime Impact
~0 (один dict-lookup + сравнение caller-строки на setattr; PK-поля пишутся 1-2 раза/тик/NPC). IPT 45/45, замки 45/45, обе серии causal_state_test побайтово идентичны baseline.

## Sandbox Tests
- backend/tests/sandbox/SUPERBOX/scenarios/causal_state_test.py — D-группа: D2_pk_field → REJECTED (мембрана цела); серии: Горан (A красный by-design — H1-ландшафт), maid_lusya (A/B/C/D GREEN).
- backend/tests/test_phase_a_memory_fixes.py — 45/45.

## Rollback
Удалить guard: вырезать _PK_ALLOWED_WRITERS + __setattr__ из класса PerceptualKernel (mod/npc_state.py). Состояние мира и схема персистенции не менялись — откат бесследен; урок остаётся в MUTATIONS S243.

## Урок
D-группа = замок экзамена: диагностический сценарий НИКОГДА не вносится в тест-исключения guard'а — иначе критерий нелегального входа мёртв и канал state→decision нефальсифицируем (методологическое ядро B0).