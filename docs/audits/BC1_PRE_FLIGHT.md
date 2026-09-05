
# BC-1 PRE-FLIGHT — досье-проект контура EXPERIENCE → CONCLUSION

> Статус: ДО КОДА (runtime не тронут). Сессия: S243 (AG1).
> Мандат: Roadmap v3.6, Фаза 1.5, BC-1 = semantic leap (лестница §2a, B0-CLOSED).
> Дисциплина: законы до решений — развилки F1/F2/F3 (§12) закрываются вердиктом
> владельца ДО кода. Фальсификатор слоя: «NPC меняет будущее поведение без
> флага поведения» (никаких avoid_shadow()).

## 1. Границы BC-1 (терминологическая лестница)

BC-1 = значимый опыт порождает **вывод о причине/агенте/паттерне** — не только
память + скаляр trust/fear. НЕ входит: обобщение повторов (BC-4), ревизия по
противоречию (BC-9 дорожного регистра), передача вывода (BC-5/6), потребление
в решении (BC-3 — через Expectation BC-2). BC-1 строит СЛОЙ ВЫВОДА, не поведение.

## 2. Археологическая карта (факты S243, файл:строки)

| Слой | Файл:строки | Факт |
|---|---|---|
| Источник опыта | mod/npc/experience_trace.py (:14 TraceSource, :22 ExperienceTrace, :69 trace_id) | provenance первого класса: actor ≠ owner; source_id + TraceSource; TESTIMONY — отдельный trace_id (BC-5, не трогаем) |
| Семантический прецедент | mod/npc/memory_crystal.py (:15, :52-53, :68-111, :120) | confidence ≠ retrieval_strength; распад ТОЛЬКО confidence (exp, мультипликативно); припоминание +0.1 доступности БЕЗ уверенности; идентичность = триплет + происхождение (без confidence) |
| Гейт-прецедент | svc/memory/delta_gate.py (:17, :26-30, :35, :53+) | WHITELIST: поле → (lo, hi, consumer); validate = whitelist → кламп → идемпотентность (trace_id, field); apply = consumer_dispatch по ИМЕЮЩЕМУСЯ каналу + публикация EXPERIENCE_DELTA_COMMITTED; Gate = аудит, НЕ писатель (вердикт AG1-04, :56-60); идемпотентность _applied{(trace_id, field)} |
| Сырьё дельты | dom/state_delta_proposal.py (:19-31) | frozen: trace_id, field, value: float (СКАЛЯР ТОЛЬКО), rationale (аудит, не игра), source (mechanical|llm), causal_parent (event.id) |
| Хранилище-прецедент | svc/npc/epistemic_store.py (:14-64) | per-agent RAM (SQLite-хвост удалён S213/DEBT-L1-SQLITE) + round-trip to_dict/from_dict; write-path факт: tick_orchestrator:691 → scene_state["epistemic_records"] |
| Персистенция-прецедент | svc/memory/sqlite_store.py:333-388 | save_crystal/load_crystals — образец save/load_conclusions |
| Событие-прецедент | svc/events/event_types.py:55; delta_gate.py (apply) | EXPERIENCE_DELTA_COMMITTED: EventDTO.create, persistence_level="working", payload {trace_id, causal_parent, field, value, consumer, source} — observation only (Закон XI) |
| Первый потребитель | svc/npc/expectation_store.py:25 | см. §7 — граница контура (BC-2) |
| Методология приёмки | SUPERBOX/scenarios/causal_state_test.py + 30 epistemic_* | A/B/C/D-группы, метрика argmax/содержимое стора (НЕ intent), D-группа = замок |

## 3. Anti-Bond (Р17-П1) — до кода

| Слой | Вход → Выход | Чего НЕ делает |
|---|---|---|
| MemoryCrystal | единичный след → триплет-воспоминание + confidence | не обобщает; не правило; не адресует прогноз |
| EpistemicStore | ClaimEvent → EpistemicRecord | только testimony/observation ЧУЖИХ утверждений; confidence = trust-функция источника, не повторяемость своего опыта |
| CrystallizedBelief (L2.5) | L1 → PatternDetector → trait+weight | линза идентичности, не пропозиция об агенте; не evidence-адресуем |
| PerceptualKernel (B0) | дельты → скаляры | механика, не семантика |
| ExpectationStore | дельты → EMA reward/threat | числовой прогноз, без вывода-правила и evidence-цепочки |

**Остаток (уникальная работа Conclusion):** вывод-правило об агенте/причине/паттерне,
derived из МНОЖЕСТВА собственных ExperienceTrace, evidence-адресуемый (event_ids → L1),
confidence как функция повторяемости/опровержений (асимметрия x6 — прецедент L2.5),
потребляемый Expectation (BC-2) для смены прогноза. Ни один слой этот
инференционный шаг не выполняет.

## 4. Контракт триплета (draft)

- `subject`: str — npc_id / pattern-key (для BC-2 маппится на source_id)
- `predicate`: Enum — ЗАКРЫТЫЙ реестр; старт: IS_DANGEROUS, IS_RELIABLE
  (вертикаль приёмки); расширение = мини-ADR (класс O-349)
- `object`: str — npc_id / location_id / pattern-key
- `confidence`: float [0..1] — уверенность ≠ truth
- `evidence`: List[str] — event_ids (L1-адресуемость)
- `source`: TraceSource — BC-1 = DIRECT_EXPERIENCE; TESTIMONY зарезервирован (BC-5)

Хранение: ConclusionStore per-agent RAM + round-trip через
scene_state["conclusions"] → Фаза 10 atomic_commit_all (прецедент EpistemicStore
S193; write-path: tick_orchestrator:691). Собственная SQLite-таблица ЗАПРЕЩЕНА
(вердикт владельца; анти-паттерн ExpectationStore). Append-only, НЕТ DELETE;
retention = confidence-decay по образцу MemoryCrystal.decayed
(только мультипликативный распад уверенности, знание не удаляется);
идентичность записи = триплет + происхождение.

## 5. Тропа записи — F2 закрыта фактом

Факт: StateDeltaProposal.value — float; rationale — не payload; WHITELIST-клампы
скалярные; динамические ключи запрещены (закрытые реестры). Триплет НЕ проходит
через существующий E2.0-контракт без расширения. Варианты (§12-F2):
- (а1) расширение E2.0: payload в StateDeltaProposal + сигнатура consumer_dispatch;
- (б) ConclusionGate ПО ОБРАЗЦУ DeltaGate: собственный ConclusionProposal
  (триплет + confidence + evidence + trace_id + causal_parent), закрытый
  predicate-реестр, кламп confidence [0..1], идемпотентность
  (trace_id, subject, predicate) — перенос AG1-INV-TRACE-ONCE:
  один event.id → один trace → ≤1 conclusion-дельты на (subject, predicate).

Контракт гейта (дословно, delta_gate.py): «Gate — аудит и трассировка причинного
изменения, НЕ второй писатель… применение ПО ИМЕЮЩЕМУСЯ каналу потребителя».
Для Conclusion канала нет → BC-1 создаёт канал (ConclusionStore.apply — единственный
write-path, прецедент apply_belief_delta), гейт валидирует и диспатчит.

## 6. Конвейер (эскиз)

    Фаза 9 (только при phase_2_events — прецедент L14/Фаза 9)
      → ConclusionEngine (pure): новые ExperienceTrace owner'а + существующие conclusions
      → ConclusionProposal → гейт (validate: реестр → кламп → идемпотентность)
      → ConclusionStore.apply (единственный write-path; provenance + causal_parent)
      → событие-трасса (observation only, Закон XI)
      → [ГРАНИЦА BC-1] ExpectationStore — reader-контракт BC-2 (мост не строится)

## 7. ExpectationStore — фактическое состояние (риски BC-2, не фиксы BC-1)

- Факт пути: svc/npc/expectation_store.py:25 — атлас L6 / DTO Registry указывают
  svc/memory/ — DOC-DRIFT (патч в BC-2-сессии; §13.5: прав код).
- Схема: (npc_id, source_id) → expected_reward / expected_threat / confidence;
  EMA LR=0.3 (S-93, Free Energy Principle).
- ПЕРСИСТЕНЦИЯ ВНЕ atomic_commit-контура: db_path="memory.db" (ОТНОСИТЕЛЬНЫЙ
  путь по умолчанию), собственная CREATE TABLE, RAM-кэш, try/except-подавление
  (B5-FIX «silent failure suppressed»). Docstring заявляет «строго через
  StateApplicator» — writer-цензус НЕ верифицирован (археология BC-2).
- Мост BC-2 (проект): conclusion(subject, IS_DANGEROUS, confidence) →
  expected_threat по source_id=subject. BC-1 обязан только: conclusions
  извлекаются по (owner, subject) — reader-контракт.

## 8. PRE-FLIGHT ADR (чеклист заполнен; номер финализируется в код-сессии max+1)

1. Тип: ONTOLOGY (кандидат ADR-O-381).
2. Домены: memory (источник E1), epistemic (граница); decision — опосредованно (BC-2/3).
3. Downstream: ExpectationStore (BC-2, reader), testimony (BC-5), ObservabilityTap
   (read-only). Two-Domain (§ENIGMA-002): потребители заявлены каноном лестницы;
   runtime-баги возникнут при BC-2/BC-5 без Conclusion — фиксируется в ADR как
   осознанное отклонение по мандату.
4. Бюджет: pure engine + RAM-store + один scene_state-ключ; НИКАКОЙ собственной
таблицы (вердикт владельца: SQLite ❌); cap conclusions/NPC; RAM ~KBs; latency ~0.
5. Rollback: флаг BC1_ENABLED default OFF = полный no-op (прецедент
   W3_G2_ENABLED); удаление таблицы бесследно.
6. Регрессия: tests/sandbox/SUPERBOX/scenarios/bc1_conclusion_test.py (§9).

## 9. Сценарий приёмки (по прецеденту causal_state_test)

- A: адресный опыт (угроза) → conclusion(subject=player, IS_DANGEROUS,
  confidence>0, evidence=event_ids). МЕТРИКА = содержимое ConclusionStore +
  трасса события (НЕ intent — урок H2/S243).
- B: контроль без опыта → conclusions пусты.
- C: авторизованная conclusion-дельта БЕЗ события → тот же вывод
  (state-канал; concordance с A).
- D: запись мимо гейта → ArchitecturalViolationError (D НЕ вносится в
  guard-исключения — замок экзамена, урок S243).
- + рестарт → conclusions персистентны (round-trip).
- B1-фальсификатор: полный прод-путь, без прямой инъекции (урок №9 досье S243).

## 10. Кандидаты IPT-инвариантов

- INV-CONCLUSION-GATE: write в ConclusionStore вне гейта → violation.
- INV-TRACE-ONCE-CONCLUSION: один event.id → ≤1 conclusion-дельты (subject, predicate).
- INV-CONCLUSION-BOUNDARY: conclusion не пишет в Expectation/PK/beliefs/RelationshipStore.
- При дормант-F3: INV-BC1-NOOP (флаг OFF → тик байтово идентичен).

## 11. Табу (черновик ADR)

❌ conclusion как флаг поведения (avoid_*/mechanism-флаги); ❌ фразы/текст в триплете;
❌ расширение predicate-реестра без мини-ADR; ❌ write в ExpectationStore/PK/beliefs/
RelationshipStore/DecisionHub; ❌ запись мимо гейта; ❌ глобальный store; ❌ DELETE
(append-only + decay); ❌ confidence = truth; ❌ TESTIMONY-ветка в BC-1 (BC-5);
❌ D-группа сценария в guard-исключения.

## 12. Открытые развилки — ВЕРДИКТ ВЛАДЕЛЬЦА ДО КОДА

- **F1 точка эмита:** (а) Фаза 9 при phase_2_events [рекомендация: выводы не рождаются
  в idle-вакууме; прецедент L14/BeliefCrystallizationEngine] / (б) подписчик
  EXPERIENCE_DELTA_COMMITTED (S115-точка) — меньше фазовой инвазии, но вывод
  из дельт, а не из опыта.
- **F2 тропа записи:** (а1) расширение E2.0-контракта (payload + сигнатура
  consumer_dispatch) — единый гейт, один EXPERIENCE_DELTA_COMMITTED; минус:
  хирургия frozen-контракта / (б) ConclusionGate по образцу DeltaGate
  [рекомендация: нулевая хирургия E2.0, закрытые реестры, изоляция скоупа].
  **F2c** (при б): событие — новый CONCLUSION_FORMED / переиспользование
  EXPERIENCE_DELTA_COMMITTED (field="conclusion").
- **F3 статус слоя:** (а) дормант-субстрат M1a-класса: красный инвариант
  «тик байтово идентичен», мост — BC-2 следующей сессией [рекомендация:
  скоуп-дисциплина] / (б) минимальный reader-мост в ExpectationStore сразу
  (снимает W0-риск, расширяет скоуп).

## 13. Вердикты владельца — ФИНАЛ (S243, до кода)

- **F1a**: точка эмита — Фаза 9 при phase_2_events. Conclusion — часть
  причинного прохождения события, не побочный эффект idle; временная
  семантика: observation/event → processing → conclusion.
- **F2б**: ConclusionGate ПО ОБРАЗЦУ DeltaGate. Conclusion — новый
  авторизованный переход состояния → собственный write boundary и
  собственная проверяемая мембрана. E2.0 frozen-контракт не расширяется.
- **F2c**: НОВОЕ событие CONCLUSION_FORMED. Трасса семантически ≠ delta:
  EXPERIENCE_DELTA_COMMITTED ≠ CONCLUSION_FORMED.
- **F3а**: dormant M1a-класс (красный инвариант «тик байтово идентичен»).
  Expectation — BC-2: CONCLUSION ──X──> EXPECTATION — переход закрыт.
- **P=BC-1**: AG1-D8p отложен отдельным фронтом (не параллелим — гонка
  владельцев/ADR исключена, причинная граница эксперимента не размывается).

### 13.1 Жёсткий инвариант BC-1 (владелец, вербатим)

> **BC-1 не имеет права создавать conclusion из отсутствия нового опыта.**

Отрицательный контроль (B-группа сценария §9, усилен):

    no new EXPERIENCE_DELTA → no CONCLUSION_FORMED → no conclusion write

Иначе — генератор «выводов из текущего состояния» = тот idle-вакуум, от
которого F1a защищает. Кандидат IPT-инварианта: INV-BC1-NO-VACUUM.
Архитектурное следствие: вход ConclusionEngine — новые дельты/трейсы
тика, НЕ текущее состояние.

### 13.2 Целевая форма потока (владелец)

    OBSERVATION / EXPERIENCE
              │ ▼
    EXPERIENCE_DELTA_COMMITTED
              │ ▼
           Phase 9
              │ ▼
        ConclusionGate
              │ ▼
       CONCLUSION_FORMED
              │ ▼
      conclusion state

### 13.3 Гейт входа BC-1 (порядок строгий, до кода)

1. mini-ADR (номер = max+1 по фактическому атласу В МОМЕНТ записи);
2. вердикты зафиксированы (эта секция);
3. археология Phase 9 + существующего event flow;
4. SSOT для conclusion определён;
5. только затем bc1_conclusion_test.py;
6. causal A/B/C/D по дисциплине causal_state_test;
7. IPT + locks до/после;
8. production commit — только после GREEN.

### 13.4 Процессный статус (вердикт владельца, S243)

- §13.3 п.1–4: архитектурное решение одобрено (F1a/F2б/F2c=new/F3а/
  SSOT-А-как-цель/BC1_ENABLED=False/NO-VACUUM/Conclusion→Expectation
  закрыто до BC-2/SQLite-Store запрещён/avoid_* запрещены).
- Q5: CLOSED ✅ — round-trip подтверждён дословным чтением production-точек
  (game_loop:447-453; tick_orchestrator:688-691; терминал SSM:555);
  SSOT-А = GO (финальный вердикт) — см. §14.1. Code gate: OPEN —
  порядок §13.3 п.5–8. BC-1-код = сессия S244 (S243 закрыта MUTATIONS-
  записью; подготовка досье/вердиктов — S243).
- ADR-O-381 = КАНДИДАТ; номер финализируется max+1 по фактическому
  атласу в момент записи (правило: номер только из факта, не из памяти).
- Predicate-реестр: минимальный вертикальный срез — ОДИН предикат
  IS_DANGEROUS (эксперимент доказывает механизм, не онтологию;
  IS_RELIABLE вычеркнут владельцем из стартового набора).
- Санация досье: «SQLite» в §2/§4/§8 устранено (противоречило факту Q4
  и вердикту); персистенция — Фаза 10 atomic_commit (не «Фаза 40»).

### 14. Q5-археология round-trip (факты grep + дословное чтение)

- Write-path: tick_orchestrator.py:691 `ctx.scene_state["epistemic_records"]
  = self._epistemic_store.to_dict()`; дубль-проекция game_loop:1248 →
  final_scene_state.
- Read-path: game_loop:449 `_epistemic_data = _scene.get("epistemic_records", [])`
  → :450 реконструкция (EpistemicStore.from_dict — подтверждается дословным
  чтением ниже).
- Терминал: scene_state_manager:555 atomic_commit_all (единственный write-path,
  Устав §4.2.1).
- Замки-прецеденты INV-CONCLUSION-ROUNDTRIP: epistemic_persistence_test.py:135;
  epistemic_production_test.py:64/168.

### 14.1 Q5-вердикт: SSOT-А = GO (дословные факты)

- Read (production): game_loop:447-453 — восстановление стора при построении
  GameLoop; write (production): tick_orchestrator:688-691 — S193-комментарий
  «перед коммитом», далее final_snapshot → SSM:555 atomic_commit_all; замок
  SUPERBOX-009 (:129-144).
- Скелет BC-1: `_conclusion_store` на TickOrchestrator; восстановление при
  build_game_loop (рядом с :449); pre-commit проекция (рядом с :691); Фаза 9 —
  через deps/ctx; дубль-проекция API-ответа — прецедент game_loop:1248.

### 14.2 (дайджест код-археологии; вставка перед 14.2)
Точки код-сессии: (1) L2.5-регион Фазы 9 (integration.py:393-436): NOT phase_2_events → skip; ConclusionEngine встанет в else-ветку :396, до WorldSnapshotBuilder, паттерном L1.5; (2) Phase9IntegrationDeps frozen (:19-33) — ConclusionStore в deps НЕ вносится; инъекция оркестратором (прецедент set_epistemic_services :271-274); (3) флаг BC1_ENABLED — по образцу W3_G2_ENABLED (settings/env-булево, чтение в продюсере+оркестраторе); (4) NO-VACUUM-канал: ctx-поле experience_delta_events: List[EventDTO] — заполняется коллектором EXPERIENCE_DELTA_COMMITTED текущего тика (гейт stateless per-subscriber — журнал не переносим); вход ConclusionEngine = события, НЕ состояние; (5) S245/FT-1 закрыта: сценарий A адресует угрозу Люсе живым прод-путём (npc_id direct match); (6) _TickContext — dto.py:75, полям места хватает; (7) два Э2.0-паттерна proposal-трасс: target-id (reaction:252) и witness-id (reaction:364) — оба собираются коллектором.

### 14.2 Находка №11 (риск — оговорка mini-ADR)

Read-path EpistemicStore хардкодит локацию: game_loop:448
`get_scene_state(_campaign_id, "tavern")` при фактической GC-00-локации
`tavern_silver_wolf` (досье №6). Восстановление ConclusionStore НЕ наследует
хардкод вслепую: ключ читается из сцены, которую видит orchestrator, или
через явный API; при невозможности в скоупе BC-1 — осознанный долг с
погашением в BC-2. Чужой epistemic read-path не чинится.