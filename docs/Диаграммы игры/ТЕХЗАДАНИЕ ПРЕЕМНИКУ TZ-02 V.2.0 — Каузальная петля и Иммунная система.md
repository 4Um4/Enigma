# ТЕХЗАДАНИЕ ПРЕЕМНИКУ: TZ-02 V.2.0 — Каузальная петля и Иммунная система

Приветствую, следующий архитектор. Перед тобой контекст, очищенный от мёртвого кода и двойных истин. TZ-02 выполнено, но в процессе реализации была вскрыта критическая нестыковка между ТЗ и реальной онтологией (ADR-O-208 / ADR-O-211). 

Читай внимательно: многие пункты оригинального ТЗ-02 **отменены или изменены** для сохранения целостности системы.

## 1. ЧТО БЫЛО СДЕЛАНО (Завершённые контуры)

### Часть A: Исполняемость пайплайна (Шаги 1-6)
*   **BUG-001 (Шаг 1):** Каузальная труба воли открыта. Директивные `perception`-поля (`aggression_inhibition_delta`, `compliance_bias_delta` и др.) вынесены из-под доменного шлюза `if domain == DeltaDomain.PERCEPTION:`. Теперь приказы игрока (через `DeltaDomain.IDENTITY`) корректно деформируют `PerceptualKernel`.
*   **ImportError/NameError (Шаги 2-5):** Устранены все критические падения в мутаторах и резолверах. Удалены вызовы несуществующей `apply_drives_mutation`. `ResolutionEngine` и `build_verbalization_context` теперь корректно получают L3-проекцию (`effective_drives` / `state_for_llm`).
*   **L0 → L3 (Шаг 6):** `InterpretationEngine` переведён на чтение `drives_runtime` (L3) вместо `drives_base` (L0). NPC интерпретирует мир на основе текущей деформации, а не стартового профиля.

### Часть B: Архитектурные подключения (Шаги 7-9, 11-12)
*   **Шаг 7 (BreakProgressEngine):** Движок слома воли подключён к `_phase_5_decision` (до DecisionHub). `WillState.BROKEN` теперь достижим. Состояния воли фиксируются в `L1Chronicle`.
*   **Шаг 8 (BehaviorMask):** Маски (`COLLAPSE`, `FAKE_SUBMISSION`, `BETRAYAL`) назначаются на основе состояния NPC перед DecisionHub. Введён как гистерезисный (квазистабильный) социальный слой.
*   **Шаг 9 (L1Chronicle SQLite):** `L1Chronicle` стал персистентным. Внедрена схема `l1_chronicle_events`. Зависимость `store` проброшена от `build_game_loop` до `L1Chronicle`. История идентичности переживает рестарт.
*   **Шаг 11 (Memory Promotion):** Контур памяти замкнут с соблюдением инварианта: *"Memory cannot generate new identity without causal input"*. `compress_narrative_cache` (структурное сжатие) работает в idle. `check_identity_promotion` (L2.5 кристаллизация) работает **только** при наличии `phase_2_events` (запрет на фантомный дрейф личности).
*   **Шаг 12 (DOUBLE TRUTH HP):** Устранена двойная истина HP. Канонический источник — `body_state["current_hp"]`. Устаревший `state.hp` оставлен как deprecated-проекция и синхронизируется с `body_state` при уроне.

### Бонус: Иммунная система (Causal Invariant Checker)
*   Создана директория `backend/tests/sandbox/invariants/`.
*   Тест `test_cross_layer_consistency.py` защищает систему от будущих регрессий (проверка консистентности HP и эфемерности L3).

---

## 2. КРИТИЧЕСКИЕ АРХИТЕКТУРНЫЕ ОТМЕНЫ (Не пытайтесь вернуть)

*   **Шаг 10 ОТМЕНЁН (ADR-O-208 / ADR-O-211):** Применение `ctx.drives_updates` и `ctx.strain_updates` к `state.drives_runtime` **ЗАПРЕЩЕНО**. 
    *   *Причина:* `CalibrationEngine` переведён в pass-through режим. Мутация скалярных драйвов минуя Belief Layer (L2.5) приводит к накоплению шума (Test C). L3 проекция строго эфемерна и пересчитывается каждый тик из L0 + L1. `drives_runtime` должен оставаться замороженным в L0 seed.
*   **Канонический контракт `TraitDriftEvent`:** ТЗ-02 содержало устаревшие поля (`npc_id`, `trait`, `delta`, `source`, `tick`). Канонический контракт (ADR-O-305A) использует: `tick_id`, `target_id`, `source_id`, `effect_value`, `observation_weight`, `event_type`. Все эмиттеры событий (травмы, слом воли) переписаны под канонический контракт.

---

## 3. ЧТО ОСТАЛОСЬ СДЕЛАТЬ (Отложенные задачи)

Перед тобой 3 сферы, требующие архитектурного аудита. Они не были частью TZ-02 из-за высокого риска, но теперь, когда пайплайн стабилен, готовы к исследованию.

### ПРИОРИТЕТ 1: Внедрение Pattern Detector (L1.5 → L2.5)
*   **Проблема:** `L1Chronicle` теперь накапливает канонические `TraitDriftEvent`, но `DriveResolver` игнорирует их (строка 42: `pass`). L3 проекция всегда равна L0.
*   **Задача:** Спроектировать `PatternDetector` (ADR-O-305), который будет группировать L1 события по `source_id` и генерировать `EvidenceOfPersistence`. На основе этих свидетельств `BeliefCrystallizationEngine` должен кристаллизовать убеждения и легитимно мутировать `drives_runtime` (L0 → L0 + Beliefs).
*   **Инструмент:** Изучить `backend/app/services/npc/pattern_detector.py` и связать его с `L1Chronicle.query_raw()`.

### ПРИОРИТЕТ 2: Аудит Affective Pipeline (Пункт C4 из ТЗ-02)
*   **Проблема:** `PressureDerivation.derive_affective_pressure` подозревается в мёртвом коде (ADR-O-206 не подключён).
*   **Задача:** Провести археологию `affective_pipeline.py` и `pressure_derivation.py`. Проверить, действительно ли контур `PerceptualKernel → AffectivePressure → EmotionResolution` замкнут, или эмоции генерируются в обход (DOUBLE TRUTH).

### ПРИОРИТЕТ 3: Двойная экономика (Пункт C3 из ТЗ-02)
*   **Проблема:** Разделение cognitive vs physiological экономики не проверено в рантайме. `hunger` может расти от тиков, а не от `elapsed_seconds`.
*   **Задача:** Аудит `life_engine.py` на предмет использования `game_time_delta_seconds` в расчётах потребностей.

---

## 4. НАПУТСТВИЕ

Система перешла от статической модели к непрерывно эволюционирующей. У тебя есть Иммунная система (инварианты) и персистентный слой причинности (L1Chronicle). 

Не нарушай ADR-O-208 (L3 эфемерна) и ADR-O-211 (нет мутации скаляров без убеждений). Если хочешь внедрить мутацию драйвов — сначала построй Belief Layer. 

Да пребудет с тобой Микроскоп Реальности.


# 🏁 СЕССИЯ S89 ЗАВЕРШЕНА. TZ-09 ЗАКРЫТ.

Контракт выполнен. Архитектурный долг TZ-08A (раздвоение мира) полностью погашен.

### 📊 Итоги Сессии S89
1. **Единый Каузальный Канал:** `run_npc_pipeline` и `tick_decisions` схлопнуты в `NpcTickPipeline.run()`. Ветвление `if ctx.interventions and any(i.source == "player")` уничтожено.
2. **Causal Snapshot:** Введён `TickState` — глубоко иммутабельный снимок состояния мира, защищённый от мутаций на границе сборки через `frozen()`.
3. **Pure Result:** Введён `TickMutation` — чистый результат работы редюсера, содержащий только дельты и намерения.
4. **Orchestrator = Assembler + Committer:** `TickOrchestrator._phase_5_decision` теперь собирает снимок, вызывает редюсер и применяет мутации.
5. **Верификация:** 15-тиковый прогон `DriftLaboratory` подтвердил стабильность (rate 1.4/tick, 0 крашей, полный lifecycle транзитов).

### ⚠️ Временный Технический Долг
`NpcTickPipeline.run()` временно принимает `svc: Any` для доступа к `MemoryManager` и `StateApplicator`. Это нарушает инвариант "Pure Deterministic Reducer", но было необходимо для миграции без переписывания всего домена памяти за один шаг.

---

### 📜 ТЗ-10: Pure Reducer Completion & Svc Strangulation (Преемнику)

**Статус:** PROPOSED
**Приоритет:** HIGH
**Основание:** Сессия S89 успешно завершила структурный коллапс TZ-09. Однако `NpcTickPipeline.run()` всё ещё принимает `svc: Any` (NpcTickServices) для доступа к `MemoryManager` и `StateApplicator`. Это нарушает инвариант "Pure Deterministic Reducer".

#### 🎯 Цель
Полностью устранить зависимость `NpcTickPipeline` от `svc` (I/O и сервисов). Сделать метод `run(state: TickState) -> TickMutation` математически чистой функцией.

#### 📐 План Миграции
1. **Pre-fetch в Orchestrator:** `TickOrchestrator` (Assembler) должен загружать ВСЕ необходимые данные из `MemoryManager` (narrative_cache, identity_traits, weights) и упаковывать их в `TickState` ДО вызова `run()`.
2. **Post-apply в Orchestrator:** `TickOrchestrator` (Committer) должен принимать `TickMutation.npc_deltas` и применять их через `StateApplicator` и `MemoryManager` ПОСЛЕ вызова `run()`.
3. **Удаление `svc`:** Убрать параметр `svc` из сигнатуры `NpcTickPipeline.run()`. Внутри `run()` оставить только вычисления (DecisionHub, InterpretationEngine, Physical Resolution).
4. **Тестирование:** Запуск `DriftLaboratory` на 50 тиков. Проверка invariant: `NpcTickPipeline` не делает I/O операций.

#### 🚫 Критические Запреты
- ❌ Вызов `svc.memory_manager.load_narrative_from_sqlite()` внутри `run()`.
- ❌ Вызов `svc.memory_manager.get_weights_for_decision()` внутри `run()`.
- ❌ Вызов `StateApplicator.apply()` внутри `run()` (должен быть в Committer).

---
*Подпись предыдущей сессии:* Каузальный канал унифицирован. TickState заморожен. Не размораживай.