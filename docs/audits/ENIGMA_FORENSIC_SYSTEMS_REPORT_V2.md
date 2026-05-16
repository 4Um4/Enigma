# ENIGMA Forensic Systems Report v2

Дата анализа: **2026-05-14**  
Покрытие истории: `2026-03-06` -> `2026-05-14`  
Источник данных: `git` (`origin/*`, commit graph), `docs/Tasks/*`, `docs/audits/*`, `README evolution`, `runtime domains`.

---

## 1. ARCHITECTURAL EVOLUTION MAP

### 1.1 Критический параметр решения
Критический параметр: **кто владеет правом изменять реальность**.

Траектория:
1. `GameLoop-centric control` -> 2. `TickOrchestrator phase sovereignty` -> 3. `StateDeltas v2 domain authority` -> 4. `CFRM local causality authority` -> 5. `Sandbox governance authority`.

### 1.2 Сценарии при минимальном смещении входных данных
- Если `authority` уходит обратно в императивные сервисы: система деградирует в script-driven runtime.
- Если `authority` остается в фазах+контрактах: сложность нарастает, но сохраняется объяснимость.
- Если `authority` смещается только в UI/LLM: causal ядро обнуляется до имитации.

### 1.3 Что может перевернуть итоговый вывод
- Возврат bypass-паттернов (`direct mutation`, `scene_state as truth`, `direct SceneChange as command`).
- Срыв дисциплины ADR/DTO (архитектурная амнезия).
- Перегрузка симуляции фичами без causal instrumentation.

### 1.4 Альтернативы с вероятностями
- `Contract-first continuation`: **78%** устойчивого роста.
- `Feature-first acceleration`: **44%** (быстрый прогресс, высокий риск drift).
- `Hybrid with strict gates`: **86%** (оптимум: скорость + доказуемость).

### 1.5 Краткий глубокий вывод
ENIGMA уже эволюционировала из "игрового backend" в **distributed causal runtime**, где право на изменение мира все больше централизуется в формальных протоколах, а не в конкретных функциях.

### Карта порождения систем
- `Baseline Loop` породил `TickOrchestrator`.
- `TickOrchestrator` породил `phase sovereignty` и `delta_buffer`.
- `delta_buffer` породил `StateDeltas v2 + DRSL`.
- `DRSL + Physiology` породили `Layered Reduction`.
- `Layered Reduction` породила `CFRM (field disturbances + local solver)`.
- `CFRM + Will` породили `DecisionContext geometry`.
- `Decision geometry` породила `Causal Observatory` (sandbox/system/stress/phenomenology).

### ADR как точки невозврата
- `ADR-013`: typed domain deltas.
- `ADR-015`: physiology as cross-domain pressure.
- `ADR-025`: CFRM ontology switch.
- `ADR-031`: will as cumulative strain, not binary gate.
- `ADR-043`: directive -> pressure, not direct command.
- `ADR-047`: observed causality, anti-retro-simulation.
- `ADR-048`: single spatial authority.
- `ADR-049`: decision topology deformation.
- `ADR-050`: causality observability as first-class asset.
- `ADR-051` (через impact/task документы): de-godification of LifeEngine.

### Ветки, менявшие направление
- `V.0.5.0.3` (detached): ранний R4 spatial jump (концептуально важен, но не mainline).
- `V.0.5.2.1_Пора_сломать_DecisionHub`: осознанный демонтаж старой decision-логики.
- `V.0.5.2.9_СМЕНИЛ_подход`: явный методологический разворот.
- `V.0.5.3.0.1_НОВАЯ_РЕАЛЬНОСТЬ_1`: онтологический старт CFRM-фазы.
- `V.0.5.3.0.4+_ПЕСОЧНИЦЫ_*`: переход к governance-through-observability.

---

## 2. COGNITIVE ENGINEERING PROFILE

### 2.1 Критический параметр решения
Параметр: **тип инженерного мышления** — feature-centric vs ontology-centric.

### 2.2 Сценарии
- Ontology-centric (текущий): каждая фича проходит через причинные контракты.
- Mixed-mode: локальные победы, глобальная нестабильность.
- Feature-centric: быстрый UX-рост, разрушение causal coherence.

### 2.3 Что может перевернуть вывод
- Снятие фазовых запретов.
- Отказ от песочниц как критерия истины.
- Накопление "legacy exemptions".

### 2.4 Альтернативы с вероятностями
- Сохранение ontology-first профиля: **82%**.
- Смещение к tactical patching: **55%**.
- Возврат к monolith improvisation: **28%**.

### 2.5 Вывод
Архитектор ENIGMA мыслит как **causal systems engineer**, не как gameplay scripter.

#### Доминирующие паттерны
- Contract-first (`DTO`, `StateDeltas`, `ADR`).
- Layered reduction (по фазам и доменам).
- Deobjectification (event -> field disturbance).
- Governance by artifacts (ADR/MUTATIONS/audits/sandbox).

#### Повторяющиеся мотивы
- "Единый источник истины" в каждом домене.
- "Запрет bypass" как основной закон роста.
- "LLM = voice, Python = logic" как инвариант.

#### Механизмы борьбы с хаосом
- Устав (`АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA`).
- ADR + IMPACT audits.
- MUTATIONS + DTO Registry.
- Causal Sandbox (phenomenology/system/stress).

#### Зоны системного напряжения
- Macro vs Micro locomotion (`LocalSteeringIntent` gap).
- Scheduler vs Pressure conflict.
- Legacy adapter debt (v2 -> v1 collapse).
- Governance lag: `ADR-051` присутствует в audits/tasks, но отсутствует в основном ADR-реестре.

---

## 3. ENTROPY ANALYSIS

### 3.1 Критический параметр
**Entropy Δ (norm)** + `Stabilization Pressure` в связке.

### 3.2 Сценарии
- Рост complexity полезен, если параллельно растёт stabilization.
- Drift, если complexity растёт без governance/test pressure.
- Сопротивление развития, если refactor pressure высокий, а architectural shift низкий.

### 3.3 Что переворачивает вывод
- Неверная калибровка метрик на snapshot-коммиты.
- Массовый артефактный churn (логи/ассеты) без фильтрации.

### 3.4 Альтернативы с вероятностями
- Complexity as asset (E5-E7): **74%**.
- Complexity as drag (E1/E2 части веток): **61%**.
- Mixed entropy cycles: **88%** (реальный текущий режим).

### 3.5 Вывод
ENIGMA демонстрирует **циклическую энтропию**: резкие всплески сложности, затем фазы стабилизации через governance/sandbox.

#### Где complexity росла полезно
- `E5 -> E7`: Typed domains -> CFRM -> Observatory.
- Высокие ветки по качеству: `V.0.5.3.0.3`, `V.0.5.3.0.6`, `V.0.5.3.0.5`.

#### Где возникал architectural drift
- Ранние snapshot-heavy участки (`E1/E2`) с низкой governance density.
- Высокий churn при низком shift (`V.0.5.0.5`, часть `V.0.5.2.1-2.3`).

#### Домены, которые переписывались чаще всего
По touch/churn:
- `backend/app/services/npc` (174 touches, churn ~14839).
- `backend/app/services/llm` (54 touches, churn ~5825).
- `backend/app/services/game_loop` + `game_loop.py` (54 touches, churn ~9272 суммарно).
- `backend/app/services/memory` (55 touches, churn ~3078).
- `backend/app/services/spatial` + `scene_state_manager` (39+ touches, churn >4600 суммарно).

#### Где система сопротивлялась развитию
- Пространственный микролод (`ADR-019` признан как gap).
- Конфликт между расписанием и когнитивным давлением.
- Миграция legacy payload-мостов.

---

## 4. TEMPORAL DEVELOPMENT PHASES (by ontology, not versions)

### 4.1 Критический параметр
Смена **онтологии**, а не номера версии.

### 4.2 Сценарии
- Фазы как эволюция законов реальности.
- Фазы как накопление фич.

### 4.3 Что может перевернуть вывод
- Если считать по тегам/версиям без causal-doc context.

### 4.4 Альтернативы с вероятностями
- Ontology-phase slicing корректен: **89%**.
- Version-phase slicing достаточен: **32%**.

### 4.5 Вывод
История ENIGMA делится на 7 эпох:

1. `E1_Proto-Loop` (2026-03-15 -> 2026-04-02): рождение базового цикла.
2. `E2_Runtime-Resuscitation` (2026-04-04 -> 2026-04-25): оживление runtime и декомпозиция сервисов.
3. `E3_Orchestrator-Surgery` (2026-04-26 -> 2026-04-30): фазовый суверенитет.
4. `E4_Decision-Refactor` (2026-05-01 -> 2026-05-02): разлом старого DecisionHub.
5. `E5_Typed-Narrative-Temporal` (2026-05-03 -> 2026-05-08): типизация дельт, narrative, время как физика.
6. `E6_CFRM-Birth` (2026-05-10 -> 2026-05-12): локальная причинность и феноменология.
7. `E7_Observatory-Governance` (2026-05-12 -> 2026-05-14): измеримость причинности как режим разработки.

---

## 5. GRAVITY COMMITS

### 5.1 Критический параметр
Коммиты, после которых downstream-архитектура перестала быть прежней.

### 5.2 Сценарии
- Gravity через добавление новой подсистемы.
- Gravity через смену права мутации.
- Gravity через смену epistemology (как доказывается истина).

### 5.3 Что может перевернуть вывод
- Если оценивать только объём строк, а не тип зависимости.

### 5.4 Альтернативы с вероятностями
- Текущий shortlist покрывает ядро сдвигов: **84%**.
- Есть скрытые gravity-points в docs-only коммитах: **46%**.

### 5.5 Вывод
Ключевые gravity commits:
- `d17cc33` (2026-03-15): first working loop baseline.
- `4a14628` (2026-03-19): NPC psychology core.
- `52574b7` (2026-04-07, detached): R4 spatial runtime prototype.
- `daf3054` (2026-04-26): large GameLoop/Spatial overhaul.
- `75373bd` (2026-04-30): phased orchestrator modularization.
- `ecf0e68` (2026-05-02): tick orchestrator + NPC pipeline refactor.
- `11e17af` (2026-05-08): explicit approach switch.
- `e4ddc7b` (2026-05-10): "Новая реальность" (physiology + CFRM jump).
- `6fdc50b` (2026-05-12): sandbox-heavy CFRM consolidation.
- `7818e88` (2026-05-14): observatory/governance hardening.

---

## 6. VELOCITY QUALITY ANALYSIS

### 6.1 Критический параметр
Не скорость кода, а **Sustainable Architectural Velocity**.

### 6.2 Сценарии
- Высокая скорость + низкая стабилизация = technical acceleration debt.
- Средняя скорость + высокая стабилизация = устойчивый рост ценности.

### 6.3 Что может перевернуть вывод
- Неполный учёт скрытых тестов/локальных артефактов.
- Искажение из-за snapshot-коммитов с крупными бинарными/данными.

### 6.4 Альтернативы с вероятностями
- Late-epoch quality acceleration устойчива: **77%**.
- Это временный пик перед регрессией: **41%**.

### 6.5 Вывод
По `QualityIndex` и `SustainableVelocity/h` лучший период: **E6-E7**.

Факты:
- `E7` имеет наивысшее среднее качество (`~71.58`) и стабилизацию (`~82`).
- `V.0.5.3.0.6` даёт верхний уровень `Stabilization=100`, `QualityIndex=81.80`, `SustainableVelocity=3.66/h`.
- `E4` имеет аномально высокую скорость (короткие интервалы), но низкую стабилизацию (`~6.75`), значит это **быстрый, но хрупкий прирост**.

---

## 7. ENIGMA GLOBAL EVOLUTION TABLE v2

### 7.1 Критический параметр
Единая метрическая таблица, синхронизированная с реальным `git`.

### 7.2 Сценарии
- Таблица как аналитический прибор (выполнено).
- Таблица как narrative summary без верификации (устаревший режим).

### 7.3 Что может перевернуть вывод
- Несогласованность между ветками и реальными timestamps.
- Игнор detached-направлений.

### 7.4 Альтернативы с вероятностями
- Текущая v2 пригодна для governance: **85%**.
- Нужен следующий шаг с отделением code-churn от data-churn: **69%**.

### 7.5 Вывод
Таблица **полностью пересобрана** в файле:
- `docs/INFO/ENIGMA_global_table.md`

Сделано:
- реальный timestamp каждой вехи,
- реальный diff между соседними milestone-коммитами,
- поля: `Semantic Impact`, `Arch Shift`, `Entropy Δ (norm)`, `Stabilization Pressure`, `Causality Depth`, `Governance Density`, `Refactor Severity`, `Quality Index`, `Sustainable Velocity/h`,
- явный флаг `Lineage` (`mainline`/`detached`).

---

## 8. README EVOLUTION

### 8.1 Критический параметр
README должен отражать онтологию проекта, а не только запуск/фичи.

### 8.2 Сценарии
- README как launch guide (старый режим).
- README как инженерная хроника (новый режим).

### 8.3 Что может перевернуть вывод
- Возврат README к feature-list без causal timeline.

### 8.4 Альтернативы с вероятностями
- Хроникальный формат поддержит стратегическую целостность: **81%**.
- Чисто технический формат ускорит онбординг, но ослабит архитектурную память: **52%**.

### 8.5 Вывод
`README.md` переписан как **хроника рождения distributed reality simulation**:
- эпохи по датам,
- точки невозврата (ADR landmarks),
- линия эволюции authority,
- текущее стратегическое напряжение.

---

## 9. FINAL REPORT (meta)

### 9.1 Что за тип проекта развивается
ENIGMA развивается как **causal-runtime platform for subjective simulation**, а не как content-heavy RPG.

### 9.2 Насколько он нетипичен
Очень нетипичен:
- базовая траектория не `feature -> polish`, а `ontology -> causality -> perception -> governance`.
- документация используется как runtime-governance контур, а не постфактум описание.

### 9.3 Какие инженерные идеи уже сформированы
- Phase sovereignty (оркестратор как процессуальный суверен).
- Domain-typed mutation algebra (DRSL).
- Observed causality (anti-retro simulation).
- Decision topology deformation (pressure -> geometry -> choice).
- Causal observability as mandatory QA.

### 9.4 Какие риски могут уничтожить проект
1. Возврат bypass-мутаций ради скорости.
2. Разрыв между governance docs и фактическим кодом (уже видимый по ADR-051 в основном реестре).
3. Переусложнение presentation без укрепления causal core.
4. Накопление legacy adapters без полного выжигания.

### 9.5 Что является настоящим ядром
Настоящее ядро ENIGMA: **право мира изменяться только через формализованную причинность**.

Если это ядро сохранено, проект может масштабироваться в полноценную distributed reality simulation.
Если оно размывается, ENIGMA превратится в сложный интерфейс вокруг обычной скриптовой RPG.

---

## Appendix: Forensic Notes

- Mainline ancestry содержит почти все `origin/V.*` вехи; исключение: `V.0.5.0.3` (detached, 2 commits).
- Ещё одно detached-направление (`origin/codex/-dd-5e-wfnkj8`) не входит в `origin/V.*`, но подтверждает ранний альтернативный вектор (packaging-first).
- `README` изменялся 31 раз, что делает его ключевым маркером смены проектной самоидентификации.
