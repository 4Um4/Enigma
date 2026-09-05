# ADR-O-381 Impact Audit — Conclusion Layer (BC-1, dormant)

> Детальный аудит ОДНОГО ADR. Единый атлас: docs/ADR (Architecture Decision Records).md (DOM-06&09, L14.6).
> Статус: ACTIVE — реализована S247 (слои: dom/conclusions, conclusion_engine/gate/runtime, conclusion_store; проводки orchestrator: init-ensure, wrapper Фазы 9, pre-commit проекция, restore при ON; EventType CONCLUSION_FORMED). Приёмка bc1_conclusion_test 6/6 GREEN; гейты: IPT 45/45, замки 45/45, ruff clean, B0-parity (Люся точный, Горан seed=0). PRE-FLIGHT: вердикты F1a/F2б/F2c/F3а + NO-VACUUM (S243, docs/audits/BC1_PRE_FLIGHT.md §13).

## Решение
Новый авторизованный переход состояния EXPERIENCE → CONCLUSION: триплет (subject/predicate/object) + confidence [0..1] + evidence[event_ids] + source=DIRECT_EXPERIENCE. Тропа: Фаза 9 (при phase_2_events) → ConclusionEngine (pure) → ConclusionGate (по образу DeltaGate: закрытый predicate-реестр — старт ОДИН предикат IS_DANGEROUS; кламп; идемпотентность) → ConclusionStore.apply (единственный write-path) → CONCLUSION_FORMED (observation-only, Закон XI). Слой dormant: BC1_ENABLED default OFF = no-op; мост CONCLUSION→EXPECTATION закрыт до BC-2.

## Инварианты (вердикты владельца)
- NO-VACUUM: без новых EXPERIENCE_DELTA → ноль CONCLUSION_FORMED → ноль записей. Вход ConclusionEngine — новые дельты/трейсы тика, НЕ текущее состояние.
- AG1-INV-TRACE-ONCE (перенос): один event.id → один trace → ≤1 conclusion-дельты на (subject, predicate).
- INV-BC1-NOOP: флаг OFF → тик байтово идентичен.
- INV-CONCLUSION-GATE: write в ConclusionStore вне гейта → ArchitecturalViolationError.
- INV-CONCLUSION-BOUNDARY: conclusion не пишет в Expectation/PK/beliefs/RelationshipStore/DecisionHub.

## Changed Domains
- Memory/EMRL (E1-источник → новый слой вывода); Epistemic — граница, не consumer в BC-1; персистенция scene_state (+1 ключ «conclusions», round-trip по S193-паттерну).

## Downstream Consumers
- BC-2 ExpectationStore: reader-контракт по (owner, subject) — мост строится В BC-2, здесь закрыт.
- BC-5 testimony: TESTIMONY-ветка source зарезервирована, НЕ реализуется в BC-1.
- ObservabilityTap / Chronicaler: CONCLUSION_FORMED — observation only.

## Runtime Impact (прогноз)
Pure engine + RAM-store + один scene_state-ключ; cap conclusions/NPC; retention = confidence-decay по образцу MemoryCrystal.decayed (только мультипликативный распад уверенности, знание не удаляется). RAM ~KBs/NPC; latency ~0. Dormant (OFF) — нулевой эффект (красный инвариант M1a-класса).

## Sandbox Tests
- tests/sandbox/SUPERBOX/scenarios/bc1_conclusion_test.py (план, §9 досье): A (опыт → conclusion; метрика = store-контент + события, НЕ intent — урок H2/S243) / B (NO-VACUUM, тройной контроль: 0 событий, 0 write-вызовов, пустой store) / C (авторизованная conclusion-дельта без события; concordance с A) / D (мимо гейта → ArchitecturalViolationError; в guard-исключения НЕ вносить) + рестарт round-trip (прецедент SUPERBOX-009) + dormant no-op. B1-фальсификатор: полный прод-путь (урок №9 досье S243).
- Гейты: замки 45/45 + IPT 45/45 до/после; обе серии causal_state_test побайтово (BC-1 не трогает B0-канал).

## Rollback
BC1_ENABLED=OFF → no-op. Полное удаление слоя: домен-контракты + гейт + стор + engine + проводки Фазы 9/pre-commit + EventType-член + scene_state-ключ. Внешних потребителей нет (dormant) — откат бесследен.

## Оговорки / известные риски
- Находка №11: epistemic read-path хардкодит локацию (game_loop:448 get_scene_state(_campaign_id, "tavern") при GC-00-локации tavern_silver_wolf). Восстановление ConclusionStore НЕ наследует хардкод: ключ читается из сцены оркестратора или явно; при невозможности в скоупе BC-1 — осознанный долг, погашение в BC-2. Чужой epistemic read-path не чинится (зона параллельной серии).
- Дубль-проекция API-ответа — по прецеденту game_loop:1248 (final_scene_state).
- Doc-drift атласа L6 / DTO Registry по expectation_store (указан svc/memory/, факт svc/npc/expectation_store.py:25) — санация в BC-2-сессии, не здесь.
- FT-1 (адресация реплики) закрыт соседней сессией S245 (npc_id direct match) — сценарий A опирается на живую адресацию.
