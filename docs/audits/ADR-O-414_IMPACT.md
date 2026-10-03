# ADR-O-414 Impact Audit — INV-CONSUMER-GAP / Causal Anatomy (Stage 1)
> Детальный аудит ОДНОГО ADR. Единый атлас: docs/ADR (Architecture Decision Records).md

## Changed Domains
- observability/IPT (новый контур Слой 1); models — data-модуль Stage 2 (causality_manifest, вне пути тика). Runtime симуляции байт-идентичен.

## Downstream Consumers
- IPT 49→50 (INV-CONSUMER-GAP-ORPHAN, линтер-инвариант — лимит 15 симуляционных не расходуется).
- RE-фронт: Слой 3 = proof GC-11 (§0.2/§2.1/§9.3 v4.2). Body-фронт: D-MOM (§5.1), NL-D9 (§7.7).
- Реестры roadmap §7.8 (CG-D-01..14, B1); все будущие фичи — декларация проводки обязательна (Stage 2).

## Runtime Impact
- Нулевой на симуляцию. Линтер: AST 416 файлов / ~81k строк ≈ секунды/коммит. Манифест: ~KBs RAM. Харнесс: вне IPT (по diff схем/манифеста и релиз-гейт).

## Sandbox Tests
- docs/audits/INV-CONSUMER-GAP_EXAM.md: E1/E3/D2 RED→GREEN ×6 прогонов (E3 — различение Store/Load; D2 — двойная защита реестра).
- Stage 3: gc11-тест (PerturbationHarness → TavernGameplayHarness adapter).

## Rollback
- revert: scripts/lint_consumer_gap.py, scripts/consumer_gap_debts.py, IPT-дельта (49/49), два audit-файла. Внешних потребителей нет — бесследно.

## Известные границы Слоя 1 (несущие, не баги)
- Writers через dict-mutation/append/методы объектов/**-unpacking/позиционные payload-конструкторы невидимы → CG-D-B1-аннотации; точность добирает манифест Stage 2.
- Коллизии имён дают недодетект (безопасное направление: «damage_type» на PhysicalOutcome погасил injury_dto.damage_type).
- Carrier-gap: payload → сериализация → dict-ключ (functional_loss читается vital_state:198 по дикту injuries) — статическая связка носителей невидима.
- BOM×11 файлов (PEP 263-легально для импорта) — читается линтером через utf-8-sig; находка отчёта, чужие файлы не чинились.

## Смежные долги (не чинились, зона владельцев)
- AUD-D4 (4 wildcard-писателя _ALLOWED_WRITERS), NL-D9 (State Consumer Gap выборка 3 — consumer-фронт), D-MOM (P3, Sleep/Decision).

## Мандат Мастера (S317)
- Направление: Causal Anatomy / Organ Integrity. Stage 2 = расширяемый semantic manifest (KNOWN_ORGANS: perception/memory/relationship/emotion/desire/body/experience/provenance/role/knowledge; KNOWN_TERMINALS: decision/belief/emotion/desire/relationship/diagnostic/projection/persistence + археология). Census последовательно расширяется на десятку (RELATIONSHIP/DESIRE/KNOWLEDGE — первые). Пайплайн органа: DISCOVER→CLASSIFY→MANIFEST→SCAN→PERTURBATION→VERDICT. Стрелки organ↔organ не утверждаются заранее — доказываются пертурбацией. Правила: находка ≠ фикс; state ≠ живой орган; metadata ≠ причинность.