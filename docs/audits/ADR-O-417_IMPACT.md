`ADR-O-417` [ONTO] **RE-M1b Relationship Cycle — Write Gate, V2 RAM-authoritative Cutover, M1b.5 Sanitation**
Files: backend/app/services/social/relationship_write_gate.py, backend/app/services/social/v2_relationship_backend.py, backend/app/services/social/relationship_state_store.py, backend/app/services/memory/relationship_store.py, backend/app/services/memory/memory_manager.py, backend/app/services/npc/state_applicator.py, backend/tests/test_relationship_state_store.py
# ADR-O-417 Impact Audit
> Детальный аудит ОДНОГО ADR (ретро-регистрация RE-M1b-цикла + M1b.5 санация S322). Единый атлас: docs/ADR (Architecture Decision Records).md
> **Ретро-регистрация:** работы S231–S246 в коммитах ссылались на «ADR-O-371 (M1b-контекст)» — документационный дрейф-алиас; канон O-371 = W1 Spatial Topology (S230). Исторические ссылки не переписываются (прецедент O-400/O-413, Устав 11.1.1).

## Changed Domains
- **RE (Relationship Engine):** RelationshipWriteGate (D2-инвариант «ALL RELATIONSHIP STATE WRITES → ONE GATE → STORE»; whitelist 5 скаляров {trust, fear, debt, respect, attraction}; NaN/тип-валидация; cause-провенанс; routing-слой без собственного состояния); V2RelationshipBackend (M1b.4.2 cutover: RAM-authoritative — один runtime owner RAM, сцена = persistence-проекция, disk-on-update запрещён, sync идемпотентен); миграционный адаптер legacy JSON → scene_state.directed (M1b.1, идемпотентный); lazy-bootstrap (M1b.3.2, npc_provider, existing-RAM-wins).
- **M1b.5 санация (S322):** npc_state_helpers.py удалён целиком (обе функции; 0 импортов/0 вызовов; до-Stage-0 онтология — прямая запись social_stats.trust мимо StateApplicator); corrupt-ветка legacy _load → fail-loud ContractValidationError (было: except→тихий {} — Vacuum-материализация §ENIGMA-003); мёртвый фасад MemoryManager.update_relationship (0 prod-вызовов) + сирота _relationship_write_gate удалены.

## Downstream Consumers
- Писатели (backend-агностичны через Gate): StateApplicator.update_relationships (SOCIAL-маршрут), NpcDialogueSubscriber, RulesSubscriber, SocialSubscriber, ActionConsequenceCompiler, SocialDecayHandler (через Applicator).
- Читатели: DecisionHub (get_all_for_source), MemoryManager.get_weights_for_decision, routes.py (get_pair), experiment_runner (get_relationships), End-Screen (get_all).
- Legacy RelationshipStore: M1b.1-фолбэк + тест-фикстуры; полный removal = фаза K (removal-test Ступени 2).

## Runtime Impact
- Tick latency: 0 (удалён только мёртвый код; V2-путь не изменён).
- RAM: легаси-инстанс создаётся в MemoryManager.__init__ (M1b.1-совместимость) — кандидат сжатия после фазы K.
- Поведение тика байт-идентично; TestMemoryManagerGateParity удалён — gate-покрытие живёт в TestWriteGateD3Parity (прямой whitelist/NaN-контракт гейта).

## Sandbox Tests
- backend/tests/test_relationship_state_store.py — полный цикл: WriteGate D3-паритет + whitelist; Applicator/SocialSubscriber/Decay gate-паритеты; V2 D3-паритет; Cutover Lifecycle; RAM Authority (pre-scene + location-change); Single Writer Invariant (греп-страж); corrupt fail-loud + missing-file Vacuum (S322).
- backend/tests/IPT.py — INV-RE-CACHE-ALLOWLIST (O-415), INV-EPISTEMIC-TRUST-MONOTONICITY.
- Smoke §3.9 corrupt→ContractValidationError канонизирован регресс-тестом (f97208b9).

## Rollback
- M1b.5-коммиты S322 (71384bba, ec67f730, f97208b9, 942df582, d34a0b53, Р4 scene_init — pathspec): git revert каждого независим.
- Cutover M1b.4.2: поединочно не откатывается; откат = смена backend'а гейта на legacy (интерфейс совместим by design — заложено M1b.2).

## Поглощённые долги / попутные (S322)
- AUD-D5 закрыт: (б) fail-loud; (а) TTL — §15.2-легальный cache-TTL вне прод-пути (фаза K); (в) вне прод-пути.
- scene_state_provider v2 признан НЕСУЩИМ (sync-тракт RAM→persistence-проекция; тест-enforced location_change); doc-drift-маркеры «vestigial» сняты (v2-docstring + scene_init).
- TECH_DEBT_NOTE: Pylance/mypy тест-фикстур (pre-existing; pyproject tests.* exclusion unused); Pylance Protocol-narrow в MemoryManager.reset_campaign_state (hasattr-гварды, runtime-safe).
