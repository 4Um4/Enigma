# ADR-O-372 Impact Audit
> Детальный аудит ОДНОГО ADR. Единый атлас: docs/ADR (Architecture Decision Records).md

## Changed Domains
- WORLD: W2 — деривация affordances над W1-субстратом (read-only)
- EMBODIMENT: read-only вход (BodyStateView; оси — делегация vital_state, ADR-123)
- Тик: НЕ затронут (0 runtime-вызовов, grep-доказано)

## Downstream Consumers
- Сегодня: НОЛЬ runtime-потребителей (substrate-only, доктрина M1a)
- Будущие (контрактные): W3 transition_object (ревалидация precondition-кортежей —
  единственный вход гейтов; тогда же первый writer + caller-guard M1a-паттерн),
  W4 CapabilityEvaluator (grip-предикаты + расширение view энергией/гидратацией/
  питанием), CommitmentArbiter (ТЗ §23.4)
- Фронтенд: НЕ подключён (W7)

## Runtime Impact
- Tick latency: 0 (0 вызовов; grep: единственные вхождения AffordanceResolver —
  сами W2-файлы)
- RAM: ~10 КБ статических таблиц на импорте; Persistence: 0
- Поведение тика: байтово идентично (IPT 45/45 до == после; W1 30/30)

## Sandbox Tests
- backend/tests/test_affordance_resolver.py — 24 теста: замыкание реестров (5),
  таблица v1 + В10-правка (7), body-гейты/DISABLED-сентинел (4), смежность и
  краевые (2), purity/детерминизм/W3-ревалидация (5), регрессия
  enum-distinctness (1)
- backend/tests/test_world_object_topology.py — 30/30 (регрессия W1)
- backend/tests/IPT.py — 45/45 (новых инвариантов нет, вердикт В7)
- GORAN β: не запускался — 0 runtime-импортов вне W2-зоны (в отличие от W1,
  трогавшей build_snapshot); байт-идентичность by construction; по запросу

## Rollback
- git revert: 2 новых файла + 2 коррекции + 1 константа + тесты + ADR/IMPACT/
  yaml + build_graph.py перегенерация. Ноль миграции: нет персистенции,
  нет runtime-вызовов, сейвы не затронуты.

## Инциденты сессии
- Stranded-декоратор: однострочный якорь патча перед декорированным классом
  оставил @dataclass(frozen=True) над WorldActionType (enum) → zero-field
  dataclass __eq__ (всегда True) и __hash__ (константа) → множества членов
  схлопывались: set-equality тесты ложно зелёные, distinctness-тесты ложно
  красные. Поймано структурным тестом (линтеры класс не ловят). Урок
  протокола: якорь вставки перед декорированным классом — МИНИМУМ ДВЕ строки
  (декоратор + заголовок). Регрессионный гвард
  test_world_action_type_members_distinct добавлен.

## Поглощённые долги / попутные
- W0-остаток semantic_action.py (0 потребителей с S226) оживлён и канонизирован
  (STAND → STAND_UP); нулевой потребитель закрыт W2
- Закрыты ПАРАЛЛЕЛЬНОЙ сессией (верифицировано здесь, не мной): DEBT-IPT-RUFF
  (ruff IPT.py: All checks passed — вся санация 24 нарушений, вкл. F821 os);
  НАБЛ-1 eco-stress ([ECO] через StateApplicator.apply_deltas_only — их
  smoke_phase0_fix.log)
- Зафиксирован DEBT-W-AUDIT: docs/AUDIT_W_TRACK_COUPLINGS.md (ТЗ §18.3,
  обязательный deliverable Stage 2.5) отсутствует; S226 декларировала
  W-track Audit — сверка записи S226 на закрытии не проводилась (чужая зона)
- Race-наблюдение: транзиентный 44/45 (1 CRITICAL) в присутствии активной
  параллельной сессии; не воспроизведён 3× зелёными прогонами; класс —
  «снимок движущейся цели» (файлы в полупатченном виде между их командами)