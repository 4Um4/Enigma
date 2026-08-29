# ADR-O-371 Impact Audit
> Детальный аудит ОДНОГО ADR. Единый атлас: docs/ADR (Architecture Decision Records).md

## Changed Domains
- WORLD (новый домен, architecture/world.yaml): семантическая объектная топология
- Persistence: НЕТ изменений — subtree едет внутри scene_state (atomic_commit_all/load_scene_at как есть)
- Snapshot: WorldSnapshot +1 поле (deepcopy, default None — конец dataclass, прецедент S215)

## Downstream Consumers
- Сегодня: НОЛЬ runtime-потребителей (substrate-only, доктрина M1a — верифицировано grep)
- Будущие (контрактные): W2 AffordanceResolver (read), W3 transition_object + causal writer
  (write — тогда же caller-guard по образцу M1a _ALLOWED_WRITERS), EventCompiler (snapshot read)
- Фронтенд: НЕ подключён (W7 PresentationProjector)

## Runtime Impact
- Tick latency: ~0 (deepcopy {} при отсутствии объектов в build_snapshot)
- RAM: 0 до первого spawn; диск: +1 top-level ключ scene_state только при наличии объектов
- Поведение тика: байтово идентично (INV-TICK/COMMIT/EVENT-CARDINALITY зелёные, 44→45)

## Sandbox Tests
- backend/tests/test_world_object_topology.py — 30 тестов: domain-контракт (12),
  store-операции (14), DoD-персистенция через реальный SqlitePersistenceAdapter (2),
  snapshot-мост (2)
- backend/tests/IPT.py — INV-WORLD-OBJECT-TOPOLOGY (45/45): часть 1 live-сцена
  (условная, включится сама при W3-спавнере), часть 2 smoke контракта
- GORAN β regression — по протоколу handoff (результат в записи MUTATIONS)

## Rollback
- Полный git revert: 2 новых файла + 2 перезаписанных/патченных + тесты + IPT-строки + yaml.
  Runtime-вызовов нет — откат не требует миграции. Сейвы с ключом world_objects
  остаются загружаемыми (ключ игнорируется старым кодом — безвреден).

## Поглощённые долги / попутные
- Закрыт залоговый долг S215: dead imports (time/uuid4/field) + несортированный
  импорт-блок world_snapshot.py (ruff I001+3×F401, diff 13+/4−)
- Новый чужой долг DEBT-IPT-RUFF: 24 pre-existing нарушения в IPT.py, включая
  F821 os undefined (:1129, error-путь INV-HP-SSOT — NameError при срабатывании)
- Зафиксирован doc-drift: §3.8 «max 15 инвариантов» vs фактические 45