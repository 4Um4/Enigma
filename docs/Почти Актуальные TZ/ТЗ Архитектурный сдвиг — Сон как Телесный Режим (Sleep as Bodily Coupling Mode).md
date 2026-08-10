# ТЗ: Архитектурный сдвиг — Сон как Телесный Режим (Sleep as Bodily Coupling Mode)

**Статус:** Архитектурное предложение (P0.5 → P1)
**Цель:** Преобразовать сон из скриптового состояния в эмерджентное свойство телесной архитектуры агента, управляемое через `CouplingMode`.

## 1. Философский фундамент (Ontology Shift)

Сон не является действием (`Intent.SLEEP`). Сон — это **снижение активной связанности с внешним миром**, при котором внутренние модели (память, вера, аффект) получают относительное доминирование над восприятием. 

Сон генерирует переживаемые сигналы (`Dream Signals`), которые проходят через стандартный эпистемический конвейер, создавая риск эпистемических ошибок и эмоциональных остатков.

## 2. План реализации (Пошаговые задачи)

### Шаг 1: Расширение `BodyState` (The Foundation)
**Файлы:** `backend/app/domain/body.py`, `backend/app/services/state/npc_state.py`
1. Добавить в `BodyState` две новые непрерывные оси:
   - `sleep_pressure` (0.0 - 1.0): Накопленная биологическая необходимость сна (растет со временем бодрствования, снижается во сне).
   - `arousal` (0.0 - 1.0): Текущий уровень физиологического возбуждения (взлетает от стимулов, падает в покое).
2. Убрать хардкод-флаг `is_sleeping` (если есть), заменив его на вычисляемое свойство `coupling_mode`.

### Шаг 2: Внедрение `CouplingMode` (The Topology Shift)
**Файлы:** `backend/app/domain/body.py`, `backend/app/services/perception/perceptual_kernel.py`
1. Ввести `CouplingMode` (Enum): `FULL_WAKE`, `DROWSY`, `SLEEP`, `DEEP_SLEEP`, `REM`.
2. Создать таблицу коэффициентов связи (Coupling Matrix):
   - `external_vision_mult`, `external_hearing_mult`, `motor_output_mult`, `memory_activation_mult`, `imagination_mult`.
3. Модифицировать `PerceptualKernel`: при обработке `Reality Events` умножать силу сигнала на `external_mult` текущего `CouplingMode`. 
4. Если `CouplingMode` == `SLEEP`/`REM`, `PerceptualKernel` переходит в режим слабой связи (сигналы искажаются или игнорируются).

### Шаг 3: P0.5 — `ActiveCommitment` & Routine FSM (Починка текущего бага)
**Файлы:** `backend/app/services/npc/life_engine.py`, `backend/app/services/npc/decision_hub.py`
1. Внедрить `ActiveCommitment` слой между `DecisionHub` и `MovementEngine`.
2. `DecisionHub` получает информацию о `ActiveCommitment` через `decision_ctx.compression.constraints`.
3. Если есть активный транзит (commitment), `DecisionHub` обнуляет feasibility (`<= 0.0`) для конкурирующих движений (`AMBUSH`, `BLOCK_PATH`), оставляя только `EMERGENCY` (flee, combat).
4. `RoutineEngine` переводит NPC в состояние `TRAVELLING_TO_SLEEP` при высоком `sleep_pressure` или по расписанию. В этом состоянии `Intent.GO_TO_SLEEP` блокирует обычный decision competition.

### Шаг 4: `DreamGenerationService` (The Internal Simulation)
**Файлы:** `backend/app/services/perception/dream_generation_service.py` (Новый)
1. Когда `CouplingMode` == `REM` или `SLEEP`, запускать `DreamGenerationService`.
2. Сервис собирает данные: `L1Chronicle` (недавние неразрешенные события) + `AffectiveLoad` (страх, долг) + `CrystallizedBelief`.
3. На основе этих данных генерирует `DreamSignal` (DTO, аналогичный `PerceptionEvent`).
4. `DreamSignal` инжектируется в `Epistemic Pipeline` (через `PhenomenologyProjectionService`).
5. `TruthState` такого сигнала отмечается как `DREAM` (эпистемологическая граница).

### Шаг 5: `Dream Residue` & Пробуждение (The Aftermath)
**Файлы:** `backend/app/services/npc/life_engine.py`, `backend/app/services/state/affective_integrator.py`
1. **Пробуждение:** Внешний стимул (громкий звук, удар) повышает `arousal`. Если `arousal` превышает порог, `CouplingMode` принудительно сменяется на `WAKING` -> `FULL_WAKE`.
2. **Остаток сна:** При пробуждении `DreamSignal` не удаляется полностью. Он конвертируется в `DreamResidue`.
3. `DreamResidue` применяется к `AffectiveIntegrator` как фоновое эмоциональное давление (например, необъяснимый страх или доверие), которое затухает в течение нескольких игровых часов.
4. `BeliefCrystallizationEngine` может воспринимать `DreamResidue` как слабое давление на пересмотр убеждений (если сон был достаточно ярким).


А лучше:
PHASE A — BODY
────────────────────────
BodyState
├── sleep_pressure
├── arousal
└── existing somatic variables


PHASE B — COUPLING
────────────────────────
CouplingResolver
        ↓
CouplingProfile

external coupling
internal simulation coupling
motor coupling
sensory coupling


PHASE C — COMMITMENT
────────────────────────
DecisionHub
        ↓
ActiveCommitment
        ↓
Movement / Action execution

independent from sleep


PHASE D — SLEEP ONSET
────────────────────────
sleep pressure
+
low arousal
+
appropriate environment
        ↓
sleep onset
        ↓
coupling transition


PHASE E — SLEEP PERCEPTION
────────────────────────
external event
        ↓
sleeping body
        ↓
weak sensory incorporation
        ↓
DreamSignal


PHASE F — DREAM RESIDUE
────────────────────────
DreamSignal
        ↓
Memory / Residue
        ↓
Affective pressure


PHASE G — FUTURE
────────────────────────
Memory
Prediction
Belief
Self Model
Theory of Other
        ↓
Dream Simulation


1. **Continuous Coupling > Enum Mode:** Использование непрерывного `CouplingProfile`, вычисляемого из `BodyState`, вместо хардкод-переключателей `if mode == SLEEP` — это единственный способ сохранить эмерджентность. `CouplingMode` будет лишь диагностической меткой для UI/логов.
2. **Медиация тела, а не умножение сигнала:** Разделение "не услышал" и "услышал, но не распознал" — это фундамент для будущей сенсорной депривации и шока. Тело работает как фильтр доступов (ObservationRelation), а не как математический множитель.
3. **`ActiveCommitment` как независимый долг:** Я согласен вынести это в отдельный фикс. Использование `commitment_conflict_penalty` вместо `feasibility = 0` сохраняет агентность и позволяет реализовать Emergency Override.
4. **Сон как телесное событие, а не команда:** `GO_TO_SLEEP` — это лишь обязательство дойти до кровати. Само снижение `external_coupling` и наступление сна — это физиологический результат снижения `arousal` в безопасной зоне.
5. **Sensory Incorporation (P1) вместо Dream Generation (P2):** Это гениально. Позволяет связать внешний мир со сном без написания нарративного ИИ прямо сейчас. Холод/шум искажают восприятие спящего.
6. **`ObservationProvenance`:** Введение этого поля — мощнейшая защита эпистемологии. Сон навсегда останется отделенным от объективной истины канона мира.
7. **`DreamResidue` -> Affect:** Влияние сна на будущее через изменение фона интерпретации (salience/affect), а не через прямую запись в Belief — это истинно феноменологический подход.

---

### Утвержденный план реализации (Исправленный)

Я готов начать работу строго по этому порядку:

**Phase A — `BodyState` Foundation:**
Добавление непрерывных осей `sleep_pressure` и `arousal`.

**Phase B — `CouplingResolver`:**
Создание вычислителя `CouplingProfile` (visual, auditory, motor, etc.) на основе `BodyState`. 

**Phase C — `ActiveCommitment` (Независимый фикс для `guard_borko`):**
Внедрение слоя обязательств в `DecisionHub` через `commitment_conflict_penalty`, чтобы остановить бесконечную генерацию `proactive_ambush` поверх незавершенных транзитов.

**Phase D — Sleep Onset:**
Связывание `RoutineEngine` (`GO_TO_SLEEP`), безопастной зоны и снижения `arousal` для естественного перехода `CouplingProfile` в режим слабой связанности.

**Phase E — Sensory Incorporation:**
Искажение внешних стимулов через призму спящего тела (создание `DreamSignal` с `ObservationProvenance.DREAM`).

**Phase F — `DreamResidue`:**
Конвертация остатков сна в фоновое `AffectiveLoad` / `salience` давление при пробуждении.
