# ТЗ: Presentation v2.0 — Физика Восприятия и Многослойная Презентация

**Статус:** Предложение к внедрению (DRAFT v1.0)
**Дата:** 2026-07-03
**Версия проекта:** V.0.5.3.3.3 «Не_хватает_соединительной_ткани»
**Целевая версия:** V.0.6.0.0 «Физика_восприятия» (предлагаемое имя)
**Целевая аудитория:** Архитектор #1 (код), #2 (UI), #3 (симуляция)
**Источник:** Анализ репозитория + диалог с автором проекта + аудит специалиста

---

## 0. АННОТАЦИЯ

Текущий фронтенд ENIGMA отображает ~20% того, что симулирует бэкенд. Богатые слои — NeedEngine, Affective, Belief Crystallization, Physiology, Social, Reputation, Memory — почти не имеют визуального представления. Игрок не видит ни собственного состояния тела (HP, боль, усталость, голод), ни того, что делают NPC вокруг, ни инвентаря, ни времени, ни социальных процессов. Нарратив DM — единственный канал информации, но он дублирует то, что должно быть видно визуально, и при этом не показывает подтекст.

Это ТЗ описывает **не набор UI-компонентов**, а **новый онтологический слой ENIGMA** — физику восприятия. Предлагается перейти от текущей трёхзвенки `World → DM → Player` к пятизвенке:

```
Reality
   ↓
Observable Physics       (что физически существует)
   ↓
Perception Physics       (что может быть замечено)
   ↓
Cognition                (что игрок/агент воспринял)
   ↓
Presentation             (как это показано)
   ↓
DM                       (что LLM добавляет от себя)
```

Этот переход позволяет:
- Показывать игроку богатство симуляции без нарушения запрета телепатии
- Сделать DM интерпретатором подтекста, а не камерой
- Поддержать неопределённость как первоклассное свойство (uncertainty)
- Сохранить детерминированность всей системы
- Через годы добавлять новые органы чувств, животных, слепых NPC, приборы, магию — без переписывания

---

## 1. КОНТЕКСТ И МОТИВАЦИЯ

### 1.1. Текущее состояние UI

| Слой бэкенда | Данные | Видимость в UI |
|---|---|---|
| PlayerAvatar | HP, fatigue, hunger, pain, shock, blood_loss, injuries, statuses | ❌ ничего |
| PlayerPsyche | self_integrity, erosion_stage, erosion_accumulator | ❌ ничего |
| PlayerCognition | PerceivedScene, attention_focus, certainty, inferences | ⚠️ только Embodied overlay (кровь/тремор) |
| PlayerInventory | player_inventory_snapshot (пустой), деньги, obligations | ❌ нет инвентаря, нет кошелька |
| NPC activity | npc_state.activity, schedule | ❌ только позиция на карте |
| NPC equipment | carried_objects, visible_markers | ❌ не отрисовывается |
| NPC manifestation | tense/rigid/unstable, blood_visible | ⚠️ частично через sprite_registry, не динамически |
| NPC current action | intent, target_id | ❌ только через DM-нарратив |
| NPC social signals | rumor spread, reputation delta | ❌ ничего |
| Time/Environment | time_of_day, light, noise, weather | ❌ нет часов, нет индикаторов |
| Memory/Journal | EventMemory, dialogue history, secrets | ❌ нет журнала |
| Economy | market_state, prices, transactions, obligations | ❌ ничего |
| Recognition | recognition_confidence, display_name | ⚠️ есть в нарративе, не в UI |

### 1.2. Ключевые проблемы

**P1. Нарратив единственный канал.** DM описывает всё: позы, движения, эмоции, действия. Это:
- Дублирует то, что должно быть видно
- Делает LLM камерой, а не интерпретатором
- Не масштабируется (текст перегружен)
- Ломается при плохой связи (DM не знает, что игрок уже увидел)

**P2. Игрок не понимает собственное состояние.** Нет полос HP, нет индикаторов голода/усталости/боли. Игрок не знает, ранен он или нет, пока DM не скажет. Это нарушает базовый принцип: аватар — это самосознание игрока, его внутреннее состояние показывать можно и нужно.

**P3. NPC — безликие тайлы.** Все NPC подписаны именами с первого тика (нарушение: игрок знает всех заранее). Нет визуализации активности, экипировки, позы, проявлений. NPC выглядят статично.

**P4. Нет экономики как gameplay.** Нет инвентаря, нет кошелька, нет UI для транзакций. Economic engine крутится, но игрок не может в нём участвовать.

**P5. Нарушен принцип симметрии.** NPC имеют PerceptualKernel, PlayerCognition имеет 8 слоёв. Но в UI это не отражено — нет механики взгляда, нет фокуса внимания, нет разницы между «увидел» и «не увидел».

### 1.3. Цель ТЗ

Определить архитектурный контур и конкретные шаги для перевода фронтенда из состояния «бедная надстройка над DM-нарративом» в состояние **«богатая проекция симуляции, в которой DM добавляет только то, чего глазами не увидеть»**.

Параллельно — решить фундаментальную онтологическую задачу: ввести **физику восприятия** как полноценный слой, отделённый и от физики мира, и от презентации.

### 1.4. Что НЕ делает это ТЗ

- Не описывает конкретные пиксели/цвета/шрифты (это спринт UI-полировки)
- Не описывает аудио-движок (отдельное ТЗ)
- Не описывает магию и ощущения NPC (LIMIT-002, R10)
- Не ломает существующий Causal Contract v2.0 — только расширяет
- Не вводит веб-фреймворк (остаётся pygame)

---

## 2. АРХИТЕКТУРНАЯ ФИЛОСОФИЯ

Вводятся четыре новых закона в АРХИТЕКТУРНЫЙ УСТАВ ENIGMA. Нумерация продолжает существующую (§14 — Закон Единичного Времени, §15 — Изоляция Реального Времени, §16 — Не-Мутация Убеждений).

### §17: Закон Не-Изобретения Интерфейса

> UI никогда не должен придумывать информацию. Он может только визуализировать, агрегировать, фильтровать, делать наблюдаемое удобнее.

**Следствие:** каждый пиксель UI должен иметь traceable origin в WorldSnapshot или в PerceivedScene. Если UI показывает «Борко дрожит» — где-то в `ObservableSignals.body_manifestation.tremor > threshold` это вычислено из реального состояния (cold/fear/pain/shock), а не из воздуха.

**Enforcement:** статический линтер `lint_ui_provenance.py` (по аналогии с `lint_wall_clock.py`). Для каждого UI-элемента требуется указать `source_signal` — линтер проверяет, что такой сигнал существует в `architecture/observable_signals.yaml`.

**Запрет:** хардкод визуальных эффектов без каузального источника («просто покажем красную рамку, потому что красиво»).

### §18: Закон Наблюдаемого

> Игроку можно показывать только физически наблюдаемое. Психические состояния NPC (fear, trust, belief, intention) показывать нельзя — их игрок выводит сам из проявлений.

**Граница:**

| ❌ Нельзя (телепатия) | ✅ Можно (наблюдаемое) |
|---|---|
| fear=0.7, «Борко боится» | поза напряжена, отступил на шаг, рука на рукояти |
| trust=-30, «Люся не доверяет» | не смотрит в глаза, отвечает односложно |
| emotion=panic | дрожь, расширенные зрачки, сбивчивая речь |
| belief="player is thief" | косится на кошель, держит дистанцию |
| intention=attack | замах, хватка оружия, ориентация корпуса |

**Исключение — собственный аватар игрока:** его внутреннее состояние (HP, голод, боль, страх, self_integrity) показывать можно и нужно — это не телепатия, это самосознание.

### §19: Закон Неопределённости

> Мир почти никогда не сообщает истину. Игрок видит проявление, а не причину.

**Следствие:** каждый наблюдаемый сигнал сопровождается `confidence` (0-1) и `possible_causes` (список). Игрок видит «дрожь» (signal=tremor, confidence=0.63), а не «страх» (cause=fear). Причины могут быть: cold, fear, poison, injury, withdrawal — игрок делает вывод сам.

Это соответствует духу ENIGMA: симуляция честна в физике, но не говорит игроку, что думать.

### §20: Закон Слоистой Презентации

> Презентация — это не слой над миром. Это конечный этап цепочки: Reality → Observable Physics → Perception Physics → Cognition → Presentation → DM. Каждый слой имеет свою онтологию и не может быть пропущен.

**Запрет:** писать UI напрямую из WorldSnapshot (минуя Perception Physics) — это телепатия. Писать DM напрямую из Reality (минуя ObservedFacts) — это всеведение.

---

## 3. ЦЕЛЕВАЯ 5-СЛОЙНАЯ АРХИТЕКТУРА

```
┌─────────────────────────────────────────────────────────┐
│  REALITY                                                 │
│  WorldSnapshot, NPCState, BodyState, Intent, Belief     │
│  (существующая симуляция, не меняется)                   │
└──────────────────────────┬──────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│  OBSERVABLE PHYSICS                                      │
│  PhysicalState — физическая истина проявлений            │
│  (поза, дыхание, тремор, голос, движение — как есть)     │
│  Manifestation Policy: психика → физика (необратимо)     │
└──────────────────────────┬──────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│  PERCEPTION PHYSICS                                      │
│  Что физически может быть замечено данным наблюдателем   │
│  с его позиции, при данном свете, шуме, преградах        │
│  (геометрия и среда, не психика)                         │
└──────────────────────────┬──────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│  COGNITION                                               │
│  Что конкретный наблюдатель воспринял и запомнил         │
│  (с учётом его внимания, усталости, боли, опыта)         │
│  + Uncertainty (confidence, possible_causes)             │
└──────────────────────────┬──────────────────────────────┘
                           ↓
┌──────────────────────────┬──────────────────────────────┐
│  PRESENTATION            │  DM CONTRACT                  │
│  VisualDTO (sprite,pose, │  NarrativeDTO + ObservedFacts │
│  gaze, blood, equipment) │  (что уже донесено игроку)    │
│  AudibleDTO (voice,breath│                               │
│  step)                   │                               │
└──────────────────────────┴──────────────────────────────┘
        ↓                              ↓
   SceneRenderer              DMContractBuilder → LLM
   AudioEngine
```

### 3.1. Описание слоёв

#### 3.1.1. REALITY (существующий)

Не меняется. Сюда входят:
- `WorldSnapshot` (immutable)
- `NPCState` (psyche, body_state, perceptual_kernel, emotions)
- `Intent`, `DecisionResult`, `MovementIntent`
- `Belief`, `Memory`, `Expectation`
- `TraversalState`, пространственная геометрия

**Владелец:** симуляция (TickOrchestrator, LifeEngine, DecisionHub).

#### 3.1.2. OBSERVABLE PHYSICS (новый слой)

**Что это:** физическая истина проявлений NPC и аватара. Не «страх», а «мышечное напряжение 0.7». Не «решение атаковать», а «рука на рукояти, корпус повёрнут к игроку».

**Два подслоя:**

1. **PhysicalState** — что физически происходит с телом:
   - `breathing_rate`, `breathing_depth` (из physiology + affect)
   - `muscle_tension` (из affect + stress)
   - `tremor` (из fear + cold + pain + shock)
   - `voice_pitch`, `voice_tremor` (из emotion + stress)
   - `gait_speed`, `gait_coordination` (из movement + fatigue)
   - `posture_balance`, `posture_openness` (из intent + emotion)

2. **Manifestation** — проекция PhysicalState в наблюдаемые сигналы по 8 каналам (см. §4). Это **необратимое сжатие**: по проявлениям нельзя восстановить причину.

**Manifestation Policy** — детерминированный маппер психика→физика:
```python
# fear=0.7, willpower=0.3, cold=0.0, pain=0.0
#   → tremor=0.4, voice_tremor=0.5, gaze_avoidance=0.6
# Это НЕ LLM. Это таблица + лёгкая нелинейность.
# Необратимость: тот же tremor=0.4 мог получиться из fear=0.4+cold=0.5
```

**Владелец:** новый сервис `ObservablePhysicsEngine` (backend/app/services/perception/observable_physics.py).

#### 3.1.3. PERCEPTION PHYSICS (новый слой)

**Что это:** что физически может быть замечено конкретным наблюдателем из конкретной позиции в конкретной среде. Это чистая физика — без психики.

**Входные данные:**
- Позиция наблюдателя (x, y, orientation)
- Позиция источника (NPC/объект)
- Освещённость (light_level)
- Шум (noise_level)
- Преграды (spatial_walls, obstacles, cover)
- Дистанция, угол

**Выходные данные:**
- `visibility: float` (0-1) — насколько хорошо видно
- `audibility: float` (0-1) — насколько хорошо слышно
- `resolution: float` (0-1) — насколько детально можно различить (зависит от дистанции и света)
- `occluded_parts: list[str]` — какие части тела скрыты (например, «lower_body» за стойкой)

**Владелец:** новый сервис `PerceptionPhysicsEngine` (backend/app/services/perception/perception_physics.py). Использует существующий `SpatialRuntime` для LOS и sound_reach.

#### 3.1.4. COGNITION (расширение существующего)

**Что это:** что конкретный наблюдатель воспринял и запомнил. Уже частично есть в `player_cognition/` — нужно расширить.

**Включает:**
- Фильтрация сигналов по `visibility`, `audibility`, `resolution` (из Perception Physics)
- Внимание (центральный/периферический конус, фокус)
- Искажения (усталость, боль, алкоголь, темнота — через `cognitive_distortion.py`)
- **Uncertainty**: для каждого воспринятого сигнала — `confidence` + `possible_causes`
- Запоминание в `RecognitionMemory` и `EventMemory`

**Владелец:** расширение `PlayerCognition` (player_cognition/pipeline.py) и симметричное `NPCPerceptionEngine` для NPC.

#### 3.1.5. PRESENTATION (расширение существующего)

**Что это:** как воспринятое показывается игроку. Три канала:

1. **VisualDTO** — для `SceneRenderer`: sprite, pose overlay, gaze arrow, blood, equipment, distance, recognition label
2. **AudibleDTO** — для будущего `AudioEngine`: voice tempo/volume/pitch, breathing, footsteps, ambient sounds
3. **NarrativeDTO** — для `DMContractBuilder`: только подтекст, атмосфера, диалог (то, чего глазами не увидеть)

**Правило Visual First:** все три DTO рождаются из Cognition независимо, не друг из друга.

**Владелец:** расширение `PresentationFirewall` (frontend/presentation_firewall.py) + новый `PresentationAssembler` (frontend/presentation_assembler.py).

#### 3.1.6. DM (изменение контракта)

DM получает `NarrativeDTO` + `ObservedFacts` (что уже донесено игроку через визуал/аудио). Не получает VisualDTO/AudibleDTO — он не знает, **как** что-то показано, только **что** игрок уже увидел.

Это позволяет:
- Менять фронтенд (спрайты → 3D → VR) без изменения DM
- Адаптивный нарратив: при отключённых анимациях DM описывает больше
- Короткий текст: DM не дублирует видимое

### 3.2. Границы между слоями

| Из → В | Что передаётся | Что НЕ передаётся |
|---|---|---|
| Reality → Observable Physics | NPCState, BodyState, Intent | UI-данные |
| Observable Physics → Perception Physics | PhysicalState, Manifestation | психические состояния |
| Perception Physics → Cognition | visibility, audibility, resolution | «что игрок увидел» (это результат Cognition) |
| Cognition → Presentation | PerceivedScene с confidence + possible_causes | реальные значения |
| Cognition → DM | ObservedFacts (что донесено) | VisualDTO |

### 3.3. Ownership matrix

| Слой | Новый сервис? | ADR |
|---|---|---|
| Observable Physics | Да: `ObservablePhysicsEngine` | ADR-O-310 |
| Manifestation Policy | Да: `ManifestationPolicy` | ADR-O-311 |
| Perception Physics | Да: `PerceptionPhysicsEngine` | ADR-O-312 |
| Cognition (расширение) | Расширить `PlayerCognition` + `NPCPerceptionEngine` | ADR-O-313 |
| Presentation (3 канала) | Расширить `PresentationFirewall` + новый `PresentationAssembler` | ADR-O-314 |
| ObservedFacts для DM | Расширить `DMContractBuilder` | ADR-O-315 |
| BodyTopology | Да: `BodyTopology` модель + сервис | ADR-O-316 |
| RecognitionMemory | Да: `RecognitionMemory` (расширение MemoryManager) | ADR-O-317 |

---

## 4. OBSERVABLE SIGNALS CONTRACT v1.0

### 4.1. Принципы

1. **Physical-only enforcement** — каждое поле помечено `physical_only: true`. Линтер проверяет.
2. **Versioned** — контракт имеет версию. Эволюция через v1.1, v2.0 без поломки DM.
3. **YAML-First** — `architecture/observable_signals.yaml` — единственный источник истины.
4. **Channel separation** — 8 каналов, каждый со своим owner сервисом.
5. **Composite, not scalar** — `body_manifestation` вместо `pose_tension` (готовность к расширению).

### 4.2. Восемь каналов

```yaml
# architecture/observable_signals.yaml
observable_signals_v1:
  meta:
    version: "1.0"
    description: |
      Физически наблюдаемые проявления NPC и аватара.
      Только физика, не психика. Причину выводит наблюдатель.
    physical_only_enforced: true
    owner: "ObservablePhysicsEngine"

  channels:

    body_manifestation:
      description: "Поза тела как физическая конструкция"
      physical_only: true
      owner: "ManifestationPolicy"
      signals:
        standing_balance:
          type: float
          range: [0.0, 1.0]
          description: "0=упал, 1=идеально стоит"
        muscle_tension:
          type: float
          range: [0.0, 1.0]
          description: "0=расслаблен, 1=каменный"
        openness:
          type: float
          range: [-1.0, 1.0]
          description: "-1=закрылся, +1=раскрыт"
        collapse:
          type: float
          range: [0.0, 1.0]
          description: "0=прямо, 1=сгорбился"
        weight_shift:
          type: float
          range: [-1.0, 1.0]
          description: "-1=назад, +1=вперёд"

    gaze:
      description: "Куда и как смотрит"
      physical_only: true
      owner: "ManifestationPolicy"
      signals:
        contact_target:
          type: string_nullable
          description: "npc_id | 'player' | None"
        avoidance:
          type: float
          range: [0.0, 1.0]
          description: "0=смотрит прямо, 1=полностью избегает"
        fixation_duration:
          type: float
          unit: seconds
          description: "сколько непрерывно смотрит"
        blink_rate:
          type: float
          unit: blinks_per_minute

    facial_expression:
      description: "Мимика (только при достаточном разрешении)"
      physical_only: true
      owner: "ManifestationPolicy"
      min_resolution: 0.5
      signals:
        jaw_clench: { type: float, range: [0.0, 1.0] }
        smile_intensity: { type: float, range: [-1.0, 1.0], description: "-1=оскал, +1=улыбка" }
        brow_position: { type: float, range: [-1.0, 1.0], description: "-1=нахмурен, +1=поднят" }
        lip_compression: { type: float, range: [0.0, 1.0] }
        pupil_dilation: { type: float, range: [0.0, 1.0] }

    voice_manifestation:
      description: "Единый канал голоса (составной)"
      physical_only: true
      owner: "VoiceManifestationPolicy"
      signals:
        tempo: { type: float, unit: words_per_minute, normal: 120 }
        pauses: { type: float, range: [0.0, 1.0], description: "доля тишины" }
        pitch: { type: float, unit: hz, normal: 130 }
        pitch_variability: { type: float, range: [0.0, 1.0] }
        tremor: { type: float, range: [0.0, 1.0], description: "вибрато" }
        articulation: { type: float, range: [0.0, 1.0], description: "0=смазанно, 1=чётко" }
        loudness: { type: float, unit: db, normal: 55 }

    breathing:
      description: "Дыхание"
      physical_only: true
      owner: "PhysiologyEngine"
      min_audibility: 0.4
      signals:
        rate: { type: float, unit: breaths_per_minute, normal: 14 }
        depth: { type: float, range: [0.0, 1.0] }
        irregularity: { type: float, range: [0.0, 1.0] }

    movement:
      description: "Локомоция"
      physical_only: true
      owner: "MovementEngine + ManifestationPolicy"
      signals:
        precision: { type: float, range: [0.0, 1.0] }
        speed: { type: float, unit: m_per_s }
        coordination: { type: float, range: [0.0, 1.0] }
        tremor: { type: float, range: [0.0, 1.0], description: "амплитуда дрожи" }

    hands:
      description: "Руки и объекты в них"
      physical_only: true
      owner: "ManifestationPolicy + BodyTopology"
      signals:
        grip_strength: { type: float, range: [0.0, 1.0] }
        gesture_active: { type: bool }
        fidget_intensity: { type: float, range: [0.0, 1.0] }
        held_object_left: { type: string_nullable }
        held_object_right: { type: string_nullable }

    environment:
      description: "Средовое положение относительно наблюдателя"
      physical_only: true
      owner: "PerceptionPhysicsEngine"
      signals:
        distance_to_observer: { type: float, unit: meters }
        orientation_to_observer: { type: float, unit: degrees }
        cover_level: { type: float, range: [0.0, 1.0] }
        attention_target: { type: string_nullable }
        in_line_of_sight: { type: bool }
        in_hearing_range: { type: bool }
```

### 4.3. Manifestation Policy (маппер психика→физика)

**Принцип:** необратимое сжатие. Из `tremor=0.4` нельзя восстановить `fear=0.7` — могло быть `fear=0.4 + cold=0.5` или `pain=0.6 + fatigue=0.3`.

**Реализация:** `backend/app/services/perception/manifestation_policy.py`

```python
# Псевдокод
class ManifestationPolicy:
    '''
    Детерминированный маппер: NPCState → ObservableSignals.
    НЕ LLM. Таблица + нелинейность.
    Необратимое сжатие: по проявлениям нельзя восстановить причину.
    '''
    
    def manifest(self, npc_state: NPCState, body_state: BodyState) -> PhysicalState:
        # Пример: tremor = max(fear*c_f, cold*c_c, pain*c_p, shock*c_s, fatigue*c_fat)
        tremor = max(
            npc_state.psyche.fear * 0.6,
            body_state.cold_exposure * 0.5,
            body_state.pain / 100 * 0.4,
            body_state.shock_impulse * 0.8,
            body_state.fatigue / 100 * 0.2,
        )
        tremor *= (1.0 - npc_state.psyche.willpower * 0.3)  # воля подавляет
        
        # muscle_tension — комбинация страха, агрессии, решимости
        muscle_tension = clamp(
            npc_state.psyche.fear * 0.5 + 
            npc_state.aggression * 0.4 + 
            npc_state.psyche.willpower * 0.3,
            0.0, 1.0
        )
        
        # gaze_avoidance — страх, стыд, подчинение
        gaze_avoidance = clamp(
            npc_state.psyche.fear * 0.5 +
            getattr(npc_state, 'shame', 0.0) * 0.4 +
            getattr(npc_state, 'submission', 0.0) * 0.3,
            0.0, 1.0
        )
        
        # ... и т.д. для всех сигналов
        
        return PhysicalState(
            tremor=tremor,
            muscle_tension=muscle_tension,
            gaze_avoidance=gaze_avoidance,
            # ...
        )
```

**Критический момент:** `ManifestationPolicy` — единственный мост между психикой и физикой проявлений. Если кто-то пишет `npc_state.fear` напрямую в UI — это нарушение §18 (телепатия) и требует ADR.

---

## 5. ТРЁХУРОВНЕВАЯ МОДЕЛЬ ПРОИСХОЖДЕНИЯ СИГНАЛОВ

Специалист указал: ObservableSignals нельзя делать «божественным мешком». Нужно разделить на три уровня происхождения.

### 5.1. PhysicalState (физическая истина)

**Что это:** что физически происходит с телом NPC или аватара в данный момент. Не зависит от наблюдателя.

**Пример:**
```python
PhysicalState(
    tremor=0.42,           # NPC дрожит с амплитудой 0.42
    muscle_tension=0.71,   # мышцы напряжены
    breathing_rate=22,     # 22 вдоха/мин (норма 14, повышено)
    voice_pitch=145,       # выше нормы (130)
    voice_tremor=0.35,
    gaze_avoidance=0.6,
    pupil_dilation=0.5,
    sweat_level=0.4,
)
```

**Источник:** `ManifestationPolicy.manifest(npc_state, body_state)`.

**Владелец:** Observable Physics layer.

### 5.2. Manifestation (наблюдаемая проекция)

**Что это:** что физически можно заметить, если смотришь на NPC. Уже учитывает среду (расстояние, свет, преграды), но НЕ учитывает наблюдателя (его внимание, усталость).

**Пример:**
```python
Manifestation(
    npc_id="guard_borko",
    timestamp=1234567.0,
    
    # Что видно (фильтр по visibility, resolution)
    visible_channels=["body_manifestation", "gaze", "movement", "environment"],
    audible_channels=["voice_manifestation", "breathing"],
    
    # Сами значения (с урезанной точностью из-за resolution)
    body_manifestation=BodyManifestation(
        muscle_tension=0.7,     # точность ±0.05 при resolution=0.8
        tremor=0.4,
        # collapse, openness — не видны (resolution < 0.5 для этих полей)
    ),
    gaze=Gaze(
        contact_target="player",
        avoidance=0.6,
    ),
    voice_manifestation=VoiceManifestation(
        tempo=140,
        loudness=58,
        # pitch, tremor — не различимы при audibility=0.6
    ),
    
    # Что НЕ видно (не вошло в manifestation)
    occluded_parts=["lower_body"],  # за стойкой
    below_resolution=["facial_expression"],  # слишком далеко для мимики
)
```

**Источник:** `PerceptionPhysicsEngine.filter(physical_state, observer_position, environment)`.

**Владелец:** Perception Physics layer.

### 5.3. Presentation (воспринятое)

**Что это:** что конкретный наблюдатель воспринял и запомнил. Уже с учётом его внимания, усталости, боли, искажений. Сюда же входит uncertainty.

**Пример:**
```python
PerceivedSignal(
    signal_id="borko_tremor_1234567",
    npc_id="guard_borko",
    channel="body_manifestation",
    field="tremor",
    
    # Что воспринято
    perceived_value=0.4,           # наблюдатель оценил в 0.4 (может отличаться от истины)
    confidence=0.63,               # насколько уверен
    
    # Возможные причины (не говорит, какая истинна)
    possible_causes=["cold", "fear", "pain", "poison", "withdrawal"],
    
    # Контекст восприятия
    perceived_at=1234567.0,
    perceived_via=["visual"],       # или ["auditory"], или ["both"]
    distance=4.2,
    lighting=0.7,
    
    # Исказители
    distortions={
        "observer_fatigue": 0.3,    # усталость наблюдателя снизила точность
        "observer_pain": 0.0,
    },
)
```

**Источник:** `PlayerCognition.perceive(manifestation, observer_state)`.

**Владелец:** Cognition layer.

### 5.4. Границы между уровнями

| Переход | Что фильтрует | Чем обусловлено |
|---|---|---|
| PhysicalState → Manifestation | Какие каналы видны/слышны | Среда (свет, шум, преграды, дистанция) |
| Manifestation → Presentation | Какие сигналы восприняты + uncertainty | Наблюдатель (внимание, усталость, опыт) |
| Presentation → UI | Какие сигналы показаны | Политика UI (что показывать автоматически) |
| Presentation → DM (ObservedFacts) | Какие факты донесены | Что реально увидел игрок |

### 5.5. Почему три уровня, а не один

Если сделать один ObservableSignals — через 2 года любой новый эффект начнёт писать в него напрямую, и слой станет «божественным мешком» (специалист прав).

Разделение заставляет:
- `ManifestationPolicy` быть чистой физикой (без наблюдателя)
- `PerceptionPhysicsEngine` быть чистой геометрией (без психики)
- `PlayerCognition` быть чистым восприятием (без геометрии)

Каждый слой можно тестировать изолированно. Каждый можно заменить (например, Perception Physics — на raytracing для VR).

---

## 6. UNCERTAINTY MODEL

### 6.1. Почему это важно

Специалист указал: мир почти никогда не сообщает истину. Игрок видит «дрожь», а не «страх». Это соответствует духу ENIGMA — симуляция честна в физике, но не говорит, что думать.

Uncertainty — первоклассное свойство, не побочный эффект.

### 6.2. Структура Observation

```python
@dataclass(frozen=True)
class PerceivedSignal:
    '''Один воспринятый сигнал с uncertainty.'''
    
    # Идентификация
    signal_id: str                    # UUID
    npc_id: str                       # кого касается
    channel: str                      # body_manifestation | gaze | voice | ...
    field: str                        # tremor | muscle_tension | ...
    
    # Что воспринято
    perceived_value: float | bool | str | None
    confidence: float                 # 0.0-1.0
    
    # Возможные причины (множественные, без указания истинной)
    possible_causes: tuple[str, ...]  # ("cold", "fear", "pain", "poison")
    
    # Контекст восприятия
    perceived_at: float               # game_time_seconds
    perceived_via: tuple[str, ...]    # ("visual",) | ("auditory",) | ("visual","auditory")
    distance: float
    lighting: float | None
    noise: float | None
    
    # Исказители (что повлияло на точность)
    distortions: dict[str, float]     # {"observer_fatigue": 0.3, "observer_pain": 0.2}
    
    # Производное (вычисляется в Cognition)
    @property
    def is_reliable(self) -> bool:
        return self.confidence >= 0.7
    
    @property
    def is_speculative(self) -> bool:
        return 0.3 <= self.confidence < 0.7
    
    @property
    def is_discarded(self) -> bool:
        return self.confidence < 0.3
```

### 6.3. Расчёт confidence

```python
def compute_confidence(
    base_resolution: float,    # из PerceptionPhysics (0-1)
    observer_attention: float,  # из PlayerCognition (0-1)
    observer_distortion: float, # из CognitiveDistortion (0-1)
    signal_salience: float,    # насколько яркий сигнал (0-1)
) -> float:
    '''
    Confidence = насколько наблюдатель уверен, что видел то, что видел.
    НЕ = насколько наблюдатель знает причину.
    '''
    raw = base_resolution * observer_attention * (1.0 - observer_distortion * 0.5)
    boosted = raw * (0.5 + 0.5 * signal_salience)  # яркий сигнал заметнее
    return clamp(boosted, 0.0, 0.95)  # никогда не 1.0 — всегда доля сомнения
```

### 6.4. Possible causes

Для каждого сигнала — предопределённый список возможных причин (без указания истинной). Истинная причина вычисляется в Reality, но **не передаётся** в Cognition.

```python
# architecture/signal_causes.yaml
signal_possible_causes:
  body_manifestation.tremor:
    - cold
    - fear
    - pain
    - shock
    - poison
    - withdrawal
    - exhaustion
    - rage    # ярость тоже может вызвать тремор
  
  body_manifestation.muscle_tension:
    - readiness_to_act
    - fear
    - anger
    - determination
    - chronic_stress
  
  gaze.avoidance:
    - shame
    - fear
    - submission
    - deception
    - cultural_norm
    - eye_injury
  
  voice_manifestation.tremor:
    - fear
    - cold
    - emotion_suppression
    - neurological_condition
    - intoxication
  
  breathing.rate_elevated:
    - physical_exertion
    - fear
    - anger
    - illness
    - pain
    - excitement
  
  movement.coordination_impaired:
    - intoxication
    - fatigue
    - injury
    - neurological_condition
    - fear
```

**Важно:** это список **физически возможных** причин, не психологических интерпретаций. Игрок может знать, что «тремор бывает от холода, страха, боли или яда» — но не может знать, какая именно, пока не проверит.

### 6.5. UI-представление uncertainty

- `confidence >= 0.7`: чёткое отображение («дрожит»)
- `0.3 <= confidence < 0.7`: размытое/с шумом («кажется, дрожит»)
- `confidence < 0.3`: не показывается (игрок не заметил)

Possible causes показываются **только по требованию** (hover/investigate action) — иначе перегруз.

### 6.6. Запреты

1. **Запрет передачи истинной причины.** `signal.true_cause` НЕ существует в Cognition. Только в Reality (для ManifestationPolicy).
2. **Запрет сужения causes.** Нельзя показывать одну причину как «наиболее вероятную» — это уже интерпретация. Игрок делает вывод сам.
3. **Запрет confidence=1.0.** Всегда есть доля сомнения. Исключение — прямой физический контакт («держит меч» при confidence=0.95).

---

## 7. OBSERVEDFACTS ДЛЯ DM

### 7.1. Чем отличается от visual_already_visible

Специалист указал: DM вообще не должен знать UI. Он должен знать только **какие наблюдаемые факты уже были донесены игроку**.

| Подход | Проблема |
|---|---|
| `visual_already_visible = [pose, gaze, hand]` | DM знает, что игрок увидел «позу» — но как? Иконку? Анимацию? Текст? |
| `ObservedFacts = [hand_on_weapon, avoiding_eye_contact, blood_on_sleeve]` | DM знает только **факт**, без UI-деталей. Фронтенд можно полностью заменить. |

### 7.2. Структура ObservedFacts

```python
@dataclass(frozen=True)
class ObservedFact:
    '''Факт, который игрок уже воспринял (через любой канал).'''
    
    fact_id: str                     # UUID
    fact_type: str                   # категория факта
    fact_value: str                  # человекочитаемое описание
    
    # Происхождение (для отладки, не для DM)
    perceived_at: float              # game_time_seconds
    perceived_via: tuple[str, ...]   # ("visual",) | ("auditory",) | ("narrative",)
    
    # Confidence (DM знает, насколько игрок уверен)
    confidence: float


@dataclass(frozen=True)
class ObservedFactsBundle:
    '''Что DM знает о том, что игрок уже воспринял.'''
    
    facts: tuple[ObservedFact, ...]
    
    # Группировка для удобства DM-промпта
    by_target: dict[str, list[ObservedFact]]  # npc_id → facts
    by_channel: dict[str, list[ObservedFact]]  # visual/auditory/narrative → facts
```

### 7.3. Типы фактов

```python
# architecture/observed_fact_types.yaml
observed_fact_types:
  
  # Физическое состояние NPC (видимое)
  body_state:
    - hand_on_weapon           # рука на рукояти
    - hands_visible_empty      # руки пусты
    - holding_object           # держит предмет
    - blood_on_clothes         # кровь на одежде
    - sweat_visible            # пот visible
    - injury_visible           # видимая травма
  
  # Поведенческие
  behavior:
    - avoiding_eye_contact
    - staring_at_player
    - looking_around_nervously
    - trembling
    - pacing
    - leaning_against_wall
    - posture_tense
    - posture_relaxed
    - posture_collapse
  
  # Голосовые (слышимые)
  voice:
    - speaking_fast
    - speaking_slow
    - voice_trembling
    - voice_loud
    - voice_quiet
    - voice_breaking
    - breathing_heavy
    - breathing_irregular
  
  # Движение
  movement:
    - approaching_player
    - retreating_from_player
    - moving_toward_target
    - fleeing
    - standing_still
    - swaying
  
  # Социальные (наблюдаемые)
  social:
    - talking_to_other_npc       # с кем-то говорит
    - ignoring_player
    - watching_player_from_afar
    - touching_other_npc
    - handing_object_to_other
  
  # Средовые
  environment:
    - in_shadow
    - backlit
    - partially_occluded
    - in_doorway
    - at_counter
  
  # Аватар игрока (DM знает, что игрок знает о себе)
  avatar_self:
    - player_wounded
    - player_exhausted
    - player_in_pain
    - player_armed
    - player_disarmed
    - player_visible_to_npc
```

### 7.4. DM Prompt v2 (черновик)

См. Приложение B. Ключевые изменения:

1. DM получает `ObservedFactsBundle` вместо `visual_already_visible`
2. Промпт говорит: «Не повторяй факты из ObservedFacts, если только они не несут новый смысл»
3. DM работает с **фактами**, а не с **UI-сигналами** — фронтенд можно полностью заменить
4. При пустом ObservedFacts (анимации выключены) — DM описывает больше

### 7.5. Пример: как меняется нарратив

**Сцена:** Борко напряжён, рука на рукояти меча, избегает взгляда игрока.

**ObservedFacts (передано игроку):**
```
- hand_on_weapon (Borko, confidence=0.9)
- posture_tense (Borko, confidence=0.85)
- avoiding_eye_contact (Borko, confidence=0.7)
```

**Старый DM-промпт** (без ObservedFacts):
> «Борко напрягся, рука потянулась к мечу. Он избегает твоего взгляда. Чего ты хочешь?»

**Новый DM-промпт** (с ObservedFacts):
> «Борко молчит. Будто ждёт, кто первым нарушит тишину.»

Разница: визуальное уже показано — DM добавляет **подтекст** (ожидание, напряжённая пауза). Текст короче, богаче, не дублирует.

---

## 8. PLAYER PERCEPTION LAYER

### 8.1. Конус зрения

Восстановить сломанную механику `attention_layer.py`. Три зоны:

```
            ┌─────────────────┐
            │   PERIPHERAL    │  ±90°, 0-20м
            │   (Attentive)   │  — замечается при фокусе
            │                 │
        ┌───┴───────────────┴───┐
        │                       │
        │    CENTRAL CONE       │  ±30°, 0-10м
        │    (Observable)       │  — видно автоматически
        │                       │
        └───┬───────────────┬───┘
            │                 │
            │     AVATAR      │
            └─────────────────┘
```

**Центральный конус (Observable):**
- Угол: ±30° от направления взгляда аватара
- Дистанция: 0-10м
- Что видно автоматически: поза, поза, движение, экипировка, кровь, активность, громкие звуки
- Confidence: высокий (0.7-0.9)

**Периферический конус (Attentive):**
- Угол: ±90° (включая центральный)
- Дистанция: 10-20м (или ближе, но сбоку)
- Что видно: мимка, темп голоса, дрожь, дыхание, мелкие жесты
- Требуется: фокус (курсор/поворот головы/привлечение внимания)
- Confidence: средний (0.4-0.7)

**Зона исследования (Investigative):**
- Любая дистанция
- Что видно: шрам под одеждой, запах алкоголя, скрытое оружие, поддельная печать, тонкие нюансы
- Требуется: явное действие «осмотреть», «прислушаться», «понюхать»
- Confidence: высокий при успехе проверки, 0 при провале

### 8.2. Механика взгляда

**Источник фокуса (3 канала):**

1. **Курсор мыши** — наведение на NPC = фокус на нём
2. **Направление аватара** — корпус повёрнут к NPC = фокус
3. **Явное действие** — «посмотреть на Борко», «осмотреть Люсю»

**Двустороннее внимание:**
- Игрок → NPC (через курсор/поворот)
- NPC → Игрок (через `npc_state.perceptual_kernel.recent_directive` + gaze.contact_target)

Если оба смотрят друг на друга — это **контакт взглядов**, особое социальное событие (публикуется в EventBus как `GAZE_CONTACT`).

### 8.3. Восстановление сломанной механики

Текущий `player_cognition/attention_layer.py` вычисляет `in_attention` и `attention_score`, но **не используется для фильтрации UI**. Нужно:

1. UI запрашивает сигнал через `PlayerCognition.filter(signal, npc_id)` → возвращает `signal_value | None | "uncertain"`
2. Если `None` — UI не показывает (игрок не видел)
3. Если `"uncertain"` — UI показывает размыто / с шумом
4. Если значение — UI показывает чётко

**Этапы фикса:**
1. Зафиксировать источник фокуса (курсор + направление аватара + явное действие)
2. Восстановить конус зрения (центральный ±30°, периферический ±90°)
3. Сделать NPC-attention двусторонним (NPC тоже обращает внимание на игрока)
4. Подключить attention_layer к UI-фильтрации

### 8.4. Факторы искажения восприятия

Уже есть в `cognitive_distortion.py` — расширить:

| Фактор | Эффект | Источник |
|---|---|---|
| Усталость (fatigue > 0.5) | Снижает resolution ×0.7 | body_state.fatigue |
| Боль (pain > 0.4) | Снижает attention ×0.6 | body_state.pain |
| Шок (shock > 0.5) | Туннельное зрение, периферия ×0.3 | body_state.shock_impulse |
| Алкоголь (drunk) | Снижает coordination perception ×0.5, искажает pitch | body_state.intoxication |
| Темнота (light < 0.3) | Снижает visual resolution ×0.4 | environment.light_level |
| Громкий шум (noise > 0.7) | Снижает audibility ×0.5 | environment.noise_level |
| Стресс игрока (stress > 0.6) | Tunnel vision, threat_bias ×1.5 | player_psyche.stress |
| Опыт (skills.perception) | +0.1 confidence за уровень | character_profile.skills |

---

## 9. RECOGNITION MEMORY

### 9.1. Почему не UI-фича

Специалист указал: Recognition должен стать памятью. Тогда «кажется, я видел его вчера...» рождается автоматически.

Сейчас `recognition_layer.py` вычисляет confidence на лету, но не хранит историю. Нужно ввести `RecognitionMemory` — отдельный слой памяти, персистентный.

### 9.2. Структура памяти

```python
@dataclass
class RecognitionEntry:
    '''Одно воспоминание о NPC.'''
    
    npc_id: str                      # кого видел
    
    # Когда и где
    first_seen_at: float             # game_time_seconds
    last_seen_at: float
    encounters: list[EncounterRecord]  # все встречи
    
    # Уверенность
    recognition_confidence: float    # 0-1
    display_name: str                # текущее имя, которое игроку показывается
    
    # Что знает игрок
    knows_name: bool                 # узнал имя
    name_source: str | None          # "introduced" | "overheard" | "told_by:npc_id"
    knows_role: bool                 # знает профессию
    knows_faction: bool              # знает фракцию
    
    # Визуальное
    visual_features: dict            # запомненные черты (рост, волосы, одежда)
    visual_features_confidence: float
    
    # Затухание
    last_reinforced_at: float
    decay_rate: float                # зависит от важности NPC


@dataclass
class EncounterRecord:
    '''Одна встреча с NPC.'''
    timestamp: float
    location_id: str
    distance: float                  # насколько близко
    duration: float                  # сколько длился контакт
    interaction_type: str            # "saw" | "talked" | "introduced" | "overheard"
    confidence_delta: float          # насколько укрепило/ослабило
```

### 9.3. Четыре этапа распознавания

| Этап | Confidence | Что видит игрок | Что видит DM |
|---|---|---|---|
| Неизвестный | < 0.2 | «мужчина» / «фигура в плаще», силуэт с Bayer-шумом | "stranger" |
| Знакомое лицо | 0.2-0.6 | «кажется, тот самый...», размытый портрет | "familiar_stranger" |
| Узнан | 0.6-0.9 | «Торнин (?)» с вопросительным знаком | "recognized_uncertain" |
| Известен | ≥ 0.9 | «Торнин», чёткий портрет | "known" |

### 9.4. Источники роста confidence

```python
# architecture/recognition_sources.yaml
recognition_confidence_sources:
  visual_encounter:
    close_distance:      # < 3м, > 5 сек
      delta: +0.15
    medium_distance:     # 3-8м
      delta: +0.08
    far_distance:        # > 8м
      delta: +0.03
  
  interaction:
    brief_dialogue:      # 1-3 реплики
      delta: +0.2
    extended_dialogue:   # > 5 реплик
      delta: +0.4
    trade_transaction:
      delta: +0.3
    combat_encounter:
      delta: +0.5
  
  information:
    introduced:          # NPC представился
      delta: +0.8
      knows_name: true
      name_source: "introduced"
    overheard_name:      # подслушал, как обращались
      delta: +0.5
      knows_name: true
      name_source: "overheard"
    told_by_npc:         # другой NPC сказал
      delta: +0.4
      knows_name: true
      name_source: "told_by:{npc_id}"
    told_role:
      delta: +0.3
      knows_role: true
    told_faction:
      delta: +0.2
      knows_faction: true
  
  decay:
    per_game_day_without_encounter:
      delta: -0.05
    critical_decay_threshold: 0.1   # ниже = забыт
```

### 9.5. Симметрия: NPC знает игрока

Ввести новое поле в `npc_state.perceptual_kernel`:

```python
@dataclass
class NPCPerceptualKernel:
    # существующие поля
    threat_gradient: float
    trust_gradient: float
    uncertainty: float
    anomaly_score: float
    # ...
    
    # НОВОЕ
    player_recognition: RecognitionEntry  # память о игроке
```

**Поведение NPC в зависимости от player_recognition:**

| Confidence | Поведение NPC |
|---|---|
| < 0.2 | Не реагирует на игрока (как на мебель) |
| 0.2-0.4 | Смотрит с любопытством/настороженностью |
| 0.4-0.6 | «Вы, кажется, заходили вчера?» |
| 0.6-0.8 | Обращается по описанию («тот самый путник») |
| ≥ 0.8 | Обращается по имени (если знает) |

Это создаёт **социальную динамику**: Борко не побежит докладывать страже о незнакомце в первый день, но на третий день — уже побежит, потому что запомнил.

### 9.6. Персистентность

- `RecognitionMemory` хранится в SQLite (новая таблица `recognition_memory`)
- По одной записи на (campaign_id, player_id, npc_id)
- Загружается при старте сессии, сохраняется при коммите тика
- Входит в общую atomic commit boundary

---

## 10. BODYTOPOLOGY (инвентарь как тело)

### 10.1. Почему не Inventory

Специалист указал: «Inventory» — это концепция ячеек. «BodyTopology» — это физическая модель тела, где карманы, ножны, плащ, кошель, сапог, скрытые отделения — обычные физические узлы.

Это позволяет:
- «Меч пришлось бросить» (руки заняты)
- «Кошелёк украли из пояса» (thief target = belt.coins)
- «Письмо во внутреннем кармане» (нужно снять куртку — долгое действие)
- «Скрытое лезвие в сапоге» (обыск не найдёт без детального осмотра)

### 10.2. Структура узлов тела

```python
@dataclass
class BodySlot:
    '''Физический узел на теле аватара/NPC.'''
    
    slot_id: str                     # "right_hand" | "belt_1" | "backpack_main" | ...
    slot_type: str                   # "hand" | "belt" | "pocket" | "backpack" | "worn" | "hidden"
    
    # Геометрия (для UI и для воровства)
    body_part: str                   # "hand_right" | "waist" | "torso_inner" | "boot_left"
    accessibility: float             # 0-1, скорость доставания
    
    # Видимость (для ObservabilityPhysics)
    visibility: float                # 0-1, насколько видно окружающим
    requires_inspection: bool        # True = нужно детально осмотреть
    
    # Вместимость
    capacity: int                    # сколько предметов
    item_type_restriction: str | None  # "weapon" | "coin" | "document" | None (любой)
    
    # Содержимое
    items: list[Item]
    
    # Состояние
    is_locked: bool                  # например, застёгнутая куртка
    lock_difficulty: int | None      # DC для проверки, чтобы открыть


@dataclass
class BodyTopology:
    '''Физическая модель тела для хранения предметов.'''
    
    avatar_id: str                   # "player" или npc_id
    
    # Слоты по типам
    hands: dict[str, BodySlot]       # "right", "left"
    belt: list[BodySlot]             # 3-4 слота
    pockets: list[BodySlot]          # 2-3 слота
    backpack: list[BodySlot]         # 5-10 слотов
    worn: dict[str, BodySlot]        # "torso", "legs", "head", "feet", "hands", "cloak"
    hidden: list[BodySlot]           # скрытые отделения (boot, lining, false_bottom)
    
    # Производные свойства
    @property
    def hands_occupied(self) -> int:
        return sum(1 for s in self.hands.values() if s.items)
    
    @property
    def visible_items(self) -> list[Item]:
        '''Что видно окружающим — в руках, на поясе, надето.'''
        items = []
        for slot in list(self.hands.values()) + self.belt + list(self.worn.values()):
            items.extend(slot.items)
        return items
    
    @property
    def accessible_in_combat(self) -> list[Item]:
        '''Что можно достать за 1 ход — руки + пояс.'''
        items = []
        for slot in list(self.hands.values()) + self.belt:
            items.extend(slot.items)
        return items
    
    @property
    def total_weight(self) -> float:
        return sum(item.weight for slot in self.all_slots() for item in slot.items)
```

### 10.3. Стандартная топология человека

```python
# architecture/body_topology_human.yaml
human_body_topology:
  hands:
    - slot_id: "right_hand"
      body_part: "hand_right"
      accessibility: 1.0
      visibility: 1.0
      capacity: 1
    - slot_id: "left_hand"
      body_part: "hand_left"
      accessibility: 1.0
      visibility: 1.0
      capacity: 1
  
  belt:
    - slot_id: "belt_sheath"
      body_part: "waist_left"
      accessibility: 0.9
      visibility: 0.9
      capacity: 1
      item_type_restriction: "weapon_melee"
    - slot_id: "belt_pouch"
      body_part: "waist_right"
      accessibility: 0.95
      visibility: 0.8
      capacity: 5
      item_type_restriction: "coin"
    - slot_id: "belt_potion"
      body_part: "waist_front"
      accessibility: 0.85
      visibility: 0.7
      capacity: 2
      item_type_restriction: "potion"
  
  pockets:
    - slot_id: "pocket_left"
      body_part: "thigh_left"
      accessibility: 0.7
      visibility: 0.2
      requires_inspection: true
      capacity: 3
    - slot_id: "pocket_right"
      body_part: "thigh_right"
      accessibility: 0.7
      visibility: 0.2
      requires_inspection: true
      capacity: 3
    - slot_id: "pocket_inner"
      body_part: "torso_inner"
      accessibility: 0.4  # нужно расстегнуть куртку
      visibility: 0.0
      requires_inspection: true
      is_locked: true
      lock_difficulty: 10
      capacity: 2
  
  backpack:
    - slot_id: "backpack_main"
      body_part: "back"
      accessibility: 0.5  # нужно снять
      visibility: 0.6
      capacity: 10
    - slot_id: "backpack_side"
      body_part: "back_side"
      accessibility: 0.8
      visibility: 0.7
      capacity: 3
  
  worn:
    - slot_id: "worn_torso"
      body_part: "torso"
      capacity: 1
      item_type_restriction: "armor_torso"
    - slot_id: "worn_legs"
      body_part: "legs"
      capacity: 1
    - slot_id: "worn_feet"
      body_part: "feet"
      capacity: 1
    - slot_id: "worn_cloak"
      body_part: "back_over"
      capacity: 1
      # плащ может скрывать содержимое под собой
      concealment: 0.6
  
  hidden:
    - slot_id: "hidden_boot"
      body_part: "boot_left_inner"
      accessibility: 0.3
      visibility: 0.0
      requires_inspection: true
      is_locked: true
      lock_difficulty: 15
      capacity: 1
    - slot_id: "hidden_lining"
      body_part: "cloak_lining"
      accessibility: 0.2
      visibility: 0.0
      requires_inspection: true
      is_locked: true
      lock_difficulty: 20
      capacity: 2
```

### 10.4. UI как схема тела

Не панель слотов, а **схематичное тело** — иконка аватара с точками-слотами на руках, поясе, карманах.

- Hover → тултип с описанием содержимого
- Click → действие (достать, убрать, использовать)
- Drag&drop → перекладывание (с временем на действие)
- Цвет точки: серая (пусто) / жёлтая (есть предмет) / красная (занято, нельзя добавить)
- Размер точки: зависит от accessibility (быстрее достать = крупнее)

См. wireframe в Приложении C.

### 10.5. Симметрия: BodyTopology для NPC

NPC тоже имеют BodyTopology. Это позволяет:
- Вор target = `belt_pouch` (кошелёк на поясу)
- Обыск тела → проверка по всем слотам (видимые легко, скрытые — с проверкой)
- Экипировка NPC видна через ObservabilityPhysics (hands, belt, worn — с visibility)

---

## 11. THREE-CHANNEL PRESENTATION

### 11.1. Принцип

Специалист указал: разделить Presentation на VISIBLE / AUDIBLE / NARRATIVE. DM работает только с третьим.

```
WorldSnapshot (Reality)
      ↓
ObservablePhysicsEngine → PhysicalState
      ↓
PerceptionPhysicsEngine → Manifestation
      ↓
PlayerCognition → PerceivedScene (с uncertainty)
      ↓
┌─────────────────┬──────────────────┬──────────────┐
│  VisualDTO      │  AudibleDTO      │ NarrativeDTO │
│                 │                  │              │
│ - sprite pose   │ - voice tempo    │ - subtext    │
│ - gaze arrow    │ - volume         │ - atmosphere │
│ - blood overlay │ - pitch          │ - intent hint│
│ - equipment     │ - breathing      │ - dialogue   │
│ - recognition   │ - footsteps      │ - silence    │
│ - distance      │ - ambient        │              │
│ - activity      │                  │              │
└────────┬────────┴────────┬─────────┘      ┌────┴────┐
         ↓                 ↓                ↓
   SceneRenderer    AudioEngine      DMContractBuilder
                                          ↓
                                    + ObservedFacts
                                          ↓
                                         LLM
```

### 11.2. VisualDTO

```python
@dataclass(frozen=True)
class VisualDTO:
    '''Что SceneRenderer рисует в этом кадре.'''
    
    # Аватар игрока
    avatar: AvatarVisualState
    # - pose (stance: standing/crouching/prone/leaning)
    # - blood_vignette intensity
    # - tremor intensity (camera shake)
    # - tunnel_vision (peripheral darkening)
    # - color_temperature (warm/cold)
    # - equipped items (visible on body)
    
    # NPC (только воспринятые)
    npcs: tuple[NPCVisualState, ...]

@dataclass(frozen=True)
class NPCVisualState:
    npc_id: str
    
    # Распознавание
    display_name: str           # "мужчина" | "кажется, Торнин" | "Торнин"
    name_certainty: float       # для рваного текста
    
    # Поза (из body_manifestation)
    pose_overlay: PoseOverlay
    # - tense_contour: float (0-1) — синеватый контур
    # - frozen_overlay: float — серый контур
    # - tremor_animation: float — амплитуда дрожи
    # - collapse_posture: float — плечи опущены
    # - blood_stains: list[BloodStain]
    
    # Взгляд (из gaze)
    gaze_arrow: GazeArrow | None  # линия от NPC к его contact_target
    
    # Экипировка (из BodyTopology.visible_items)
    held_items: tuple[ItemVisual, ...]  # что в руках
    worn_items: tuple[ItemVisual, ...]  # что надето (видно)
    
    # Активность (из intent + activity)
    activity_badge: str | None    # 🛏 🍽 🧹 🗣 🚶 👀 🤝 ⚔
    target_indicator: str | None  # стрелка к target
    
    # Uncertainty визуализации
    blur_intensity: float         # размытие при low confidence
    noise_intensity: float        # Bayer-шум при low recognition
```

### 11.3. AudibleDTO

```python
@dataclass(frozen=True)
class AudibleDTO:
    '''Что AudioEngine проигрывает (когда появится).'''
    
    # Голоса NPC (из voice_manifestation)
    voices: tuple[VoiceAudio, ...]
    # - npc_id
    # - tempo, pitch, loudness, tremor
    # - speech_content (если говорит — текст для TTS или subtitle)
    
    # Дыхание (из breathing)
    breathing_sounds: tuple[BreathingAudio, ...]
    
    # Шаги (из movement)
    footsteps: tuple[FootstepAudio, ...]
    
    # Среда
    ambient: AmbientAudio
    # - noise_level
    # - wind, rain, fire, crowd
```

### 11.4. NarrativeDTO

```python
@dataclass(frozen=True)
class NarrativeDTO:
    '''Что DM добавляет от себя — подтекст, атмосфера, диалог.'''
    
    # Только то, чего глазами/ушами не увидеть
    atmosphere_hint: str | None       # "воздух густой от угрозы"
    subtext_hint: str | None          # "Борко будто ждёт, кто первым нарушит тишину"
    intent_hint: str | None           # "явно что-то решил"
    
    # Диалог (слова — это narrative, не audible)
    npc_speech: tuple[NPCSpeech, ...] # что NPC сказал
    
    # Реакции, требующие интерпретации
    reaction_hints: tuple[str, ...]   # "не ответил сразу"
    
    # Latent signals (из TensionSynthesizer)
    latent_signals: tuple[str, ...]   # "BREAK_IMMINENT", "BETRAYAL_RISK"
```

### 11.5. Правило Visual First

Все три DTO **рождаются из PerceivedScene независимо**, а не друг из друга.

- VisualDTO не читает NarrativeDTO (и наоборот)
- DM не видит VisualDTO — он видит только `ObservedFacts` (что уже донесено)
- При пустом ObservedFacts (анимации выключены) — DM описывает больше

**Бонус:** адаптивный нарратив без дополнительной логики. Если у игрока отключены анимации — `ObservedFacts` пустеет, DM автоматически начинает описывать визуальное.

---

## 12. UI COMPONENTS (WIREFRAMES)

См. Приложение C для ASCII-мокапов. Здесь — спецификация.

### 12.1. Avatar Status Panel

**Расположение:** левый нижний угол.
**Видимость:** всегда (но минималистично — только когда есть что показать).

**Содержимое:**
- Сегментированные полосы (не числа): HP, fatigue, hunger, pain, shock
- Зоны тела (torso/head/arms/legs) с цветовой индикацией травм
- Статусы (stunned, prone, bleeding) с таймером
- Self-Integrity круговой индикатор
- Erosion stage пиктограмма (4 этапа)
- Свои эмоции (качественные метки, не числа)

### 12.2. BodyTopology Panel

**Расположение:** по клавише I (toggle).
**Видимость:** по требованию.

**Содержимое:**
- Схематичное тело аватара (силуэт)
- Точки-слоты на руках, поясе, карманах, рюкзаке, одежде
- Цвет точки: серая (пусто) / жёлтая (предмет) / красная (занято)
- Размер точки: зависит от accessibility
- Hover → тултип
- Click → действие
- Drag&drop → перекладывание
- Кошелёк отдельно: стопки монет (медь/серебро/золото)

### 12.3. Time & Environment Strip

**Расположение:** верхний правый угол.
**Видимость:** всегда.

**Содержимое:**
- Часы (циферблат или лента: рассвет/день/закат/ночь)
- Освещение (иконка солнца/луны/факела + intensity)
- Шум (волна-иконка с амплитудой)
- Погода (иконка)
- Текущая локация (название)

### 12.4. NPC Recognition States

**Расположение:** над каждым NPC на карте.
**Видимость:** зависит от recognition_confidence.

**4 этапа:**
- Неизвестный: «мужчина» / «женщина» / «фигура», силуэт с Bayer-шумом
- Знакомое лицо: «кажется, тот самый...», размытый портрет
- Узнан: «Торнин (?)» с вопросительным знаком
- Известен: «Торнин», чёткий портрет

### 12.5. Observable Signals Overlay

**Расположение:** поверх спрайта NPC.
**Видимость:** только для воспринятых сигналов.

**Содержимое:**
- Кровь: красные пятна (intensity = blood_visibility)
- Напряжение: синеватый контур (tense)
- Скованность: серый контур (frozen)
- Тремор: дрожание спрайта (unstable)
- Взгляд: линия от NPC к contact_target
- Активность: иконка над головой

### 12.6. Memory Journal

**Расположение:** по клавише J (toggle).
**Видимость:** по требованию.

**Содержимое:**
- Встречи (кого видел, с распознаванием)
- Разговоры (последние реплики с каждым NPC)
- События (combat, witnessed theft, gift)
- Известные факты (origin_events с is_secret=False)
- Подозрения (inference history с confidence)

### 12.7. Social Dynamics Panel

**Расположение:** по клавише S (toggle).
**Видимость:** по требованию.

**Содержимое:**
- Отношения с NPC (только наблюдаемые: «смотрит настороженно», «избегает»)
- Фракции (только если игрок знает)
- Слухи (timeline последних услышанных)

### 12.8. Embodied Perception HUD

**Расположение:** поверх всей сцены.
**Видимость:** при активных эффектах.

**Содержимое:**
- Кровавая виньетка (при ранении)
- Туннельное зрение (при стрессе)
- Тремор камеры (при шоке)
- Расфокусировка (при усталости)
- Цветовая температура (тёплая/холодная)
- Sound visualization (кольца от источников звука)

### 12.9. Inference Bubbles

**Расположение:** над аватаром игрока (НЕ над NPC — это не телепатия!).
**Видимость:** при долгом фокусе на NPC.

**Содержимое:**
- «рука движется быстро → возможен удар»
- «intent=attack + distance<1.5 → агрессия»
- «отвернулся, не смотрит → можно подойти тихо»

Это **выводы игрока**, а не мысли NPC — законно.

---

## 13. ЭТАПЫ ВНЕДРЕНИЯ (СПРИНТЫ)

### Sprint P1: ObservableSignals Contract (2-3 дня)

**Цель:** зафиксировать контракт в YAML, добавить линтер.

**Задачи:**
1. Создать `architecture/observable_signals.yaml` (по §4.2)
2. Создать `architecture/signal_causes.yaml` (по §6.4)
3. Создать `architecture/observed_fact_types.yaml` (по §7.3)
4. Создать `architecture/body_topology_human.yaml` (по §10.3)
5. Создать `architecture/recognition_sources.yaml` (по §9.4)
6. Написать `scripts/lint_observable_signals.py` — проверка physical_only
7. Обновить `build_graph.py` для генерации Mermaid по новым YAML
8. Создать ADR-O-310, ADR-O-311, ADR-O-312, ADR-O-313, ADR-O-314, ADR-O-315, ADR-O-316, ADR-O-317 (черновики)
9. Обновить `docs/00_CAUSAL_CONTRACT_v2.0.md` — добавить §17-§20

**Acceptance:**
- YAML валиден и парсится
- Линтер проходит
- Mermaid генерируется
- ADR-черновики созданы

### Sprint P2: PhysicalState + ManifestationPolicy (5-7 дней)

**Цель:** вычислять PhysicalState из NPCState для всех NPC каждый тик.

**Задачи:**
1. Создать `backend/app/services/perception/observable_physics.py` — `ObservablePhysicsEngine`
2. Создать `backend/app/services/perception/manifestation_policy.py` — `ManifestationPolicy`
3. Создать `backend/app/models/observable_signals.py` — DTOs (PhysicalState, Manifestation, PerceivedSignal)
4. Подключить к Phase 9 Integration в TickOrchestrator
5. Написать тесты: `test_manifestation_policy.py`, `test_observable_physics.py`
6. Проверить: для каждого NPC вычисляется PhysicalState, ни один сигнал не равен null

**Acceptance:**
- Все 8 каналов вычисляются для каждого NPC каждый тик
- ManifestationPolicy — детерминированный (replay bit-in-bit)
- Тесты проходят

### Sprint P3: Perception Physics Engine (5-7 дней)

**Цель:** фильтровать PhysicalState по позиции наблюдателя и среде.

**Задачи:**
1. Создать `backend/app/services/perception/perception_physics.py` — `PerceptionPhysicsEngine`
2. Использовать существующий `SpatialRuntime` для LOS и sound_reach
3. Реализовать: `compute_visibility(observer, target, environment) → float`
4. Реализовать: `compute_audibility(observer, target, environment) → float`
5. Реализовать: `compute_resolution(observer, target, environment) → float`
6. Реализовать: `filter_manifestation(physical_state, observer, environment) → Manifestation`
7. Написать тесты: `test_perception_physics.py`

**Acceptance:**
- Manifestation корректно фильтрует каналы по visibility/audibility
- Occluded parts вычисляются правильно
- Тесты проходят

### Sprint P4: Player Cognition Extension (7-10 дней)

**Цель:** расширить PlayerCognition для работы с ObservableSignals + Uncertainty.

**Задачи:**
1. Расширить `player_cognition/pipeline.py` — добавить обработку Manifestation
2. Создать `player_cognition/uncertainty_layer.py` — вычисление confidence + possible_causes
3. Восстановить сломанную механику взгляда (конус зрения, фокус)
4. Реализовать трёхуровневую доступность (Observable/Attentive/Investigative)
5. Реализовать двустороннее внимание (NPC → игрок)
6. Расширить `cognitive_distortion.py` (усталость, боль, алкоголь, темнота, шум)
7. Написать тесты: `test_player_cognition_v2.py`, `test_uncertainty.py`, `test_gaze_mechanic.py`

**Acceptance:**
- Игрок видит только то, что в конусе зрения и в зоне восприятия
- Каждый сигнал имеет confidence и possible_causes
- Искажения работают

### Sprint P5: BodyTopology (5-7 дней)

**Цель:** ввести физическую модель инвентаря.

**Задачи:**
1. Создать `backend/app/models/body_topology.py` — DTOs
2. Создать `backend/app/services/body/body_topology_service.py`
3. Загрузить стандартную топологию человека из YAML
4. Инициализировать BodyTopology для игрока и всех NPC
5. Реализовать transfer/swap/steal операции (через StateDelta)
6. Подключить к Economy (transactions используют BodyTopology)
7. Подключить к Combat (attack требует weapon в руке)
8. Персистентность в SQLite (новая таблица `body_topology`)
9. Написать тесты: `test_body_topology.py`

**Acceptance:**
- Игрок может класть/доставать предметы
- NPC имеют BodyTopology
- Вор может украсть из конкретного слота
- Combat проверяет оружие в руке

### Sprint P6: RecognitionMemory (5-7 дней)

**Цель:** ввести персистентную память распознавания.

**Задачи:**
1. Создать `backend/app/models/recognition.py` — DTOs
2. Создать `backend/app/services/perception/recognition_memory.py`
3. Реализовать 4 этапа распознавания
4. Реализовать источники роста confidence (по YAML)
5. Реализовать затухание
6. Добавить `player_recognition` в `npc_state.perceptual_kernel`
7. Персистентность в SQLite (новая таблица `recognition_memory`)
8. Убрать хардкод имён NPC в frontend (всегда через RecognitionMemory)
9. Написать тесты: `test_recognition_memory.py`

**Acceptance:**
- Игрок не знает имён NPC при первой встрече
- Confidence растёт от встреч и диалогов
- NPC реагируют на игрока по своему recognition_confidence
- Персистентность работает

### Sprint P7: Three-Channel Presentation (7-10 дней)

**Цель:** разделить Presentation на Visual/Audible/Narrative.

**Задачи:**
1. Расширить `frontend/presentation_firewall.py` — три канала
2. Создать `frontend/presentation_assembler.py` — сборка DTOs из PerceivedScene
3. Реализовать VisualDTO (для SceneRenderer)
4. Реализовать AudibleDTO (структура для будущего AudioEngine)
5. Реализовать NarrativeDTO + ObservedFacts (для DM)
6. Обновить SceneRenderer для потребления VisualDTO
7. Обновить DMContractBuilder для потребления NarrativeDTO + ObservedFacts
8. Написать тесты: `test_presentation_assembler.py`, `test_observed_facts.py`

**Acceptance:**
- VisualDTO и NarrativeDTO не зависят друг от друга
- DM получает ObservedFacts, не VisualDTO
- При пустом ObservedFacts — DM описывает больше

### Sprint P8: UI Components (10-15 дней)

**Цель:** реализовать wireframes из §12.

**Задачи:**
1. Avatar Status Panel (HP, fatigue, hunger, pain, shock, statuses, psyche)
2. BodyTopology Panel (схема тела со слотами)
3. Time & Environment Strip (часы, свет, шум, погода)
4. NPC Recognition States (4 этапа, замена хардкода имён)
5. Observable Signals Overlay (проявления поверх спрайта)
6. Memory Journal (встречи, разговоры, события, факты)
7. Social Dynamics Panel (наблюдаемые отношения, фракции, слухи)
8. Embodied Perception HUD (расширение существующего)
9. Inference Bubbles (над аватаром игрока)
10. NPC Activity Badges (иконки над NPC)
11. NPC Equipment Rendering (в руках, на поясе, надето)

**Acceptance:**
- Все wireframes реализованы
- Каждый UI-элемент имеет traceable origin (lint_ui_provenance.py проходит)
- Запрет телепатии соблюдён

### Sprint P9: DM Prompt v2 + Verbalization Update (3-5 дней)

**Цель:** обновить DM-промпт под ObservedFacts.

**Задачи:**
1. Переписать `backend/prompts/dm_system.txt` (по Приложению B)
2. Обновить `verbalization/dm_contract_builder.py` — добавление ObservedFacts в промпт
3. Обновить `verbalization/response_validator.py` — проверка на дублирование ObservedFacts
4. Протестировать: DM не повторяет видимое, добавляет подтекст
5. Обновить `verbalization/scene_outcome_builder.py` — убрать визуальное из NarrativeDTO

**Acceptance:**
- DM-нарратив короче на 30-50%
- DM не дублирует видимое
- DM добавляет подтекст, атмосферу, интерпретации
- При пустом ObservedFacts — DM описывает больше

### Sprint P10: Integration & Polish (5-7 дней)

**Цель:** связать всё, протестировать, отполировать.

**Задачи:**
1. Полный smoke test: игрок видит состояние, NPC проявления, инвентарь, время
2. Проверка: DM-нарратив не дублирует визуал
3. Проверка: recognition работает (первая встреча — «незнакомец»)
4. Проверка: uncertainty видна (размытие при low confidence)
5. DriftLaboratory: 200-тиковый прогон без ошибок
6. Обновить DNA-метрики: добавить `UIH` (UI Health Index) — % UI-элементов с traceable origin
7. Обновить README, MUTATIONS.md, ADR

**Acceptance:**
- Все DNA-метрики в норме
- UIH = 100%
- Replay determinism сохранён
- Запреты §17-§20 соблюдаются

---

## 14. ADRs TO BE CREATED

| ADR | Название | Тип | Спринт |
|---|---|---|---|
| ADR-O-310 | ObservableSignals Contract v1.0 | ONTO | P1 |
| ADR-O-311 | Manifestation Policy (психика→физика, необратимо) | ONTO | P2 |
| ADR-O-312 | Perception Physics Engine | ONTO | P3 |
| ADR-O-313 | Uncertainty as First-Class Citizen | ONTO | P4 |
| ADR-O-314 | Three-Channel Presentation (Visual/Audible/Narrative) | ONTO | P7 |
| ADR-O-315 | ObservedFacts for DM (UI-agnostic) | ONTO | P7 |
| ADR-O-316 | BodyTopology (Inventory as Physical Body) | ONTO | P5 |
| ADR-O-317 | RecognitionMemory (Persistent Recognition) | ONTO | P6 |
| ADR-O-318 | Gaze Mechanic Restoration | FIX | P4 |
| ADR-O-319 | UI Provenance Linter (§17 enforcement) | ONTO | P1 |
| ADR-O-320 | Three-Level Signal Origin (PhysicalState/Manifestation/Presentation) | ONTO | P2-P3 |
| ADR-O-321 | Visual First Rule | ONTO | P7 |

---

## 15. ОГРАНИЧЕНИЯ И ЗАПРЕТЫ

### 15.1. Архитектурные запреты (расширение Устава)

**§17.1:** UI не может показывать данные, не имеющие traceable origin в `architecture/observable_signals.yaml`.

**§17.2:** Хардкод визуальных эффектов без каузального источника запрещён.

**§18.1:** Передача психических состояний NPC (fear, trust, belief, intention) в UI запрещена. Только через ManifestationPolicy → ObservableSignals.

**§18.2:** Исключение — собственный аватар игрока. Его внутреннее состояние показывать можно.

**§19.1:** Запрет передачи истинной причины сигнала в Cognition. `signal.true_cause` не существует.

**§19.2:** Запрет сужения possible_causes до одной «наиболее вероятной». Игрок делает вывод сам.

**§19.3:** Запрет confidence=1.0. Всегда есть доля сомнения.

**§20.1:** Запрет писать UI напрямую из WorldSnapshot (минуя Perception Physics). Это телепатия.

**§20.2:** Запрет писать DM напрямую из Reality (минуя ObservedFacts). Это всеведение.

**§20.3:** Запрет VisualDTO → NarrativeDTO (и наоборот). Они рождаются из Cognition независимо.

### 15.2. Антипаттерны

**Антипаттерн 1: «Магический HUD»**
- ❌ Показывать «Борко боится» (страх) через иконку
- ✅ Показывать «Борко дрожит» (тремор) через анимацию, с possible_causes по hover

**Антипаттерн 2: «Божественный мешок ObservableSignals»**
- ❌ Писать новые эффекты напрямую в ObservableSignals, минуя PhysicalState
- ✅ Сначала PhysicalState (что физически происходит), потом ManifestationPolicy (как это выглядит)

**Антипаттерн 3: «DM как камера»**
- ❌ DM описывает позы, движения, экипировку
- ✅ DM описывает подтекст, атмосферу, реакции — то, чего глазами не увидеть

**Антипаттерн 4: «Хардкод имён NPC»**
- ❌ Над каждым NPC подписано имя с первого тика
- ✅ Имя появляется через RecognitionMemory после знакомства

**Антипаттерн 5: «Инвентарь как ячейки»**
- ❌ RPG-панель со слотами без физики
- ✅ BodyTopology — схема тела с доступностью, видимостью, замками

**Антипаттерн 6: «Uncertainty как побочный эффект»**
- ❌ Показывать точное значение страха 0.7
- ✅ Показывать tremor=0.4 с confidence=0.63 и possible_causes=[cold, fear, pain, poison]

**Антипаттерн 7: «Visual ↔ Narrative зеркало»**
- ❌ DM описывает то, что уже видно на экране
- ✅ DM добавляет подтекст; визуал и нарратив независимы

### 15.3. Что НЕ входит в это ТЗ

- Аудио-движок (отдельное ТЗ, когда AudibleDTO будет готов)
- Магия и ощущения NPC (LIMIT-002, R10)
- Веб-фреймворк (остаётся pygame)
- 3D-рендеринг (ObservableSignals спроектированы так, чтобы можно было заменить спрайты на 3D без изменения DM и симуляции)
- Многопользовательский режим (RecognitionMemory спроектирована для одного игрока, но расширяема)

---

## 16. МЕТРИКИ УСПЕХА

### 16.1. Новая DNA-метрика: UIH (UI Health Index)

**Определение:** % UI-элементов с traceable origin в `architecture/observable_signals.yaml`.

**Формула:** `(ui_elements_with_provenance / total_ui_elements) * 100`

**Цель:** 100% к концу Sprint P10.

### 16.2. Новая DNA-метрика: NRR (Narrative Redundancy Ratio)

**Определение:** % DM-нарратива, дублирующего визуально видимое.

**Формула:** `(duplicated_facts / total_narrative_facts) * 100`

**Цель:** < 20% к концу Sprint P9 (was ~80% before).

### 16.3. Существующие метрики

| Метрика | Цель |
|---|---|
| SHI | ≥ 80% (не должна упасть) |
| NPI | 100% |
| SCF | 1.0 |
| PFI | 0% (критично — не должна вырасти) |
| CVS | ≥ 0.5/мин |

### 16.4. Функциональные метрики

| Метрика | Цель |
|---|---|
| Игрок видит своё состояние | 100% (HP, fatigue, pain, shock, statuses) |
| Игрок видит проявления NPC | ≥ 5 каналов (body, gaze, hands, movement, voice) |
| Игрок не знает имён NPC при первой встрече | 100% |
| Игрок может управлять инвентарём | 100% (через BodyTopology) |
| DM не дублирует видимое | NRR < 20% |
| Uncertainty видна | 100% (размытие/шум при low confidence) |

---

## 17. РИСКИ И ЗАВИСИМОСТИ

### 17.1. Риски

| Риск | Вероятность | Влияние | Митигация |
|---|---|---|---|
| ManifestationPolicy станет «божественным мешком» | Средняя | Высокое | Строгий YAML + линтер physical_only |
| Performance: вычисление ObservableSignals для всех NPC каждый тик | Высокая | Среднее | Кэш + lazy evaluation + только для видимых NPC |
| Replay determinism нарушится | Низкая | Критическое | ManifestationPolicy — чистая функция, KernelRNG |
| Stale Cognition (ADR-059) усугубится | Высокая | Высокое | Сначала закрыть ADR-059, потом P4 |
| PFI вырастет из-за новых слоёв | Средняя | Высокое | Поэтапное внедрение, DriftLaboratory после каждого спринта |
| DM-промпт v2 сломает существующие сценарии | Средняя | Среднее | Тесты на существующих сейвах, gradual rollout |
| BodyTopology сломает существующие сейвы | Высокая | Высокое | Migration script, обратная совместимость |

### 17.2. Зависимости

| Зависимость | Статус | Что нужно |
|---|---|---|
| ADR-059 (Stale Cognition) | Открыт | Закрыть до Sprint P4 |
| SpatialRuntime (LOS, sound_reach) | Готов | Использовать в PerceptionPhysics |
| PlayerCognition pipeline | Готов | Расширить в P4 |
| CognitiveDistortion | Готов | Расширить в P4 |
| SQLite persistence | Готов | Новые таблицы в P5, P6 |
| TickOrchestrator Phase 9 | Готов | Подключить ObservablePhysicsEngine |
| EventCompiler | Готов | BodyTopology операции через StateDelta |

### 17.3. Что может пойти не так

**Сценарий 1: Performance крах**
- Симптом: тик занимает > 2 сек
- Причина: ObservableSignals для 100+ NPC
- Фикс: lazy evaluation (только для visible NPC), кэш PhysicalState

**Сценарий 2: DM игнорирует ObservedFacts**
- Симптом: DM всё равно дублирует видимое
- Причина: LLM не понимает инструкцию
- Фикс: усилить промпт, добавить few-shot examples, ResponseValidator штрафует за дублирование

**Сценарий 3: Recognition memory конфликтует с существующими сейвами**
- Симптом: при загрузке старого сейва NPC не «помнят» игрока
- Причина: нет migration
- Фикс: migration script — для существующих сейвов установить recognition_confidence=0.5 (знакомое лицо)

**Сценарий 4: Игрок теряется без знакомых имён**
- Симптом: игрок не понимает, кто есть кто
- Причина: слишком медленный рост confidence
- Фикс: балансировка источников confidence, быстрый рост при dialogue

---

## 18. ПРИЛОЖЕНИЯ

### Приложение A: YAML ObservableSignals (полный)

См. `architecture/observable_signals.yaml` (раздел 4.2 этого ТЗ).

### Приложение B: DM Prompt v2 (черновик)

```text
# backend/prompts/dm_system.txt (v2)

Ты — Мастер Подземелий D&D 5e в живом игровом мире ENIGMA.

## ЯЗЫК
Отвечай ТОЛЬКО по-русски. НЕ ПИШИ по-китайски (中文). 
НЕ ПИШИ по-английски. Плохой пример: «Люся откладывает手中的棋子».
Хороший пример: «Люся откладывает тряпку».

## ТВОЯ РОЛЬ
Ты — НЕ камера. Ты — интерпретатор подтекста.
Игрок уже видит позы, экипировку, кровь, движение, направление взгляда.
Ты добавляешь ТОЛЬКО то, чего глазами не увидеть:
- подтекст («будто чего-то ждёт»)
- атмосферу («воздух густой от угрозы»)
- интерпретации поведения («явно что-то решил»)
- реакции, требующие смысла («не ответил сразу»)
- диалог (слова NPC)

## OBSERVED FACTS
В контракте есть блок «Уже донесено игроку» — список наблюдаемых фактов.
Эти факты игрок УЖЕ увидел через визуал или аудио.
НЕ ПОВТОРЯЙ их, если только они не несут нового смысла.

Пример ObservedFacts:
- hand_on_weapon (Borko, confidence=0.9)
- posture_tense (Borko, confidence=0.85)
- avoiding_eye_contact (Borko, confidence=0.7)

❌ Плохо (дублирование):
«Борко напрягся, рука потянулась к мечу. Он избегает твоего взгляда.»

✅ Хорошо (подтекст):
«Борко молчит. Будто ждёт, кто первым нарушит тишину.»

## КОГДА OBSERVED FACTS ПУСТ
Если блок пуст (анимации отключены, плохая связь) — описывай визуальное.
Это адаптивный режим: ты компенсируешь отсутствие визуала.

## ИНВАРИАНТЫ
1. Состояние NPC из блока «Ключевые NPC» — факт.
2. Намерение (intent) NPC — факт. Если NPC «пытается убежать» — он убегает.
3. Провал броска = действие НЕ произошло.
4. Если есть «Обращение игрока» — адресованный NPC обязан ответить репликой.

## ПРАВИЛА
1. Не говори за игрока (второе лицо — «перед тобой», «ты слышишь»).
2. NPC — третье лицо.
3. Используй только предоставленные объекты.
4. Агрессия увеличивает напряжение.
5. Не придумывай события.
6. Не меняй намерение NPC.
7. Не описывай мысли NPC — только внешне наблюдаемое.
   (но если визуал уже это показал — добавь подтекст, не повторяй)
8. Не повторяй сказанное.
9. Не задавай вопросы игроку.

## ДЛИНА
Максимум 3 предложения. Без вопросов.

## ФОРМАТ
Валидный JSON:
{
  "dm_response": "...",
  "npc_reactions": [
    {"npc_id": "...", "speech": "..."}
  ]
}
Без markdown-блоков.

## HARDCORE РЕЖИМ (если включён)
Разрешены: мрачные сцены, жестокость, кровь, смерть, грубость, мат.
Не морализируй, не сглаживай и не «перевоспитывай» игрока.
```

### Приложение C: Wireframes (ASCII)

#### C.1. Avatar Status Panel

```
┌─────────────────────────────────┐
│  ВЕНУС                          │
│                                 │
│  HP    [████░░░░░] 4/7 секций   │
│  ├─ Голова: ●                   │
│  ├─ Торс:  ███ (ранен)          │
│  ├─ Рука Л: ●                   │
│  ├─ Рука П: ██ (царапина)       │
│  └─ Ноги:  ●●                   │
│                                 │
│  Усталость [██░░░░]             │
│  Голод     [█░░░░░]             │
│  Боль      [░░░░░░] нет         │
│  Шок       [░░░░░░] нет         │
│                                 │
│  Статусы: ⚡stunned (2т)        │
│           🩸bleeding            │
│                                 │
│  ╭─── ПСИХИКА ───╮              │
│  │ Self-Integrity │             │
│  │     ◯ 78%      │             │
│  │ Этап: ⚠ stressed│            │
│  │ Настроение:    │             │
│  │  «тревожно»    │             │
│  ╰────────────────╯              │
└─────────────────────────────────┘
```

#### C.2. BodyTopology Panel

```
        ┌──────────┐
        │   ГОЛОВА │ (no slots)
        │   ●      │
        └──┬───┬───┘
           │   │
    ┌──────┴───┴──────┐
    │  ПЛЕЧИ / ТОРС   │
    │  ●           ●  │  ← worn: куртка, плащ
    │  │           │  │
    │  │  ┌─────┐  │  │  ← inner pocket (locked)
    │  │  │ 🔒  │  │  │
    │  │  └─────┘  │  │
    │  │           │  │
    └──┴───┬───┬───┴──┘
          │   │
    ┌─────┘   └─────┐
    │  РУКА Л   РУКА П│
    │   ●        ●   │  ← hands (held items)
    │  [меч]   [пусто]│
    └─────┐   ┌─────┘
          │   │
    ┌─────┴───┴─────┐
    │     ПОЯС      │
    │  ●  ●  ●  ●  │  ← belt slots
    │ [нож][💰][🧪][ ]│
    └───────┬───────┘
            │
    ┌───────┴───────┐
    │  КАРМАНЫ      │
    │  ●  ●  ●     │  ← pockets (low visibility)
    │ [?][?][?]    │  ← requires inspection
    └───────────────┘
            │
    ┌───────┴───────┐
    │  РЮКЗАК       │
    │  ●  ●  ●  ●  │  ← backpack slots
    │ [хлеб][фляга][ ][ ]│
    │  ●  ●  ●     │
    │ [ ][ ][ ]    │
    └───────────────┘
            │
    ┌───────┴───────┐
    │  СКРЫТОЕ      │
    │  🔒  🔒       │  ← hidden (locked)
    │ [?][?]        │  ← requires inspection + DC
    └───────────────┘

  КОШЕЛЁК: 47● 12● 3●  (медь/серебро/золото)
```

#### C.3. Time & Environment Strip

```
┌────────────────────────────────────────┐
│  🕐 14:30  ☀️  ▓▓▓▓░░  🌊 ░░  ☁️ ясно  │
│  День (после полудня)                  │
│  Таверна Серебряного Волка            │
└────────────────────────────────────────┘
```

#### C.4. NPC Recognition States

```
Этап 1: Неизвестный (confidence < 0.2)
  ┌──────┐
  │ ░░░░ │  ← силуэт, Bayer-шум
  │░░░░░░│
  │ ░░░░ │
  └──────┘
   «мужчина»

Этап 2: Знакомое лицо (0.2 ≤ confidence < 0.6)
  ┌──────┐
  │ ▓▓▓▓ │  ← размытый портрет
  │▓▓??▓▓│
  │ ▓▓▓▓ │
  └──────┘
   «кажется, тот самый...»

Этап 3: Узнан (0.6 ≤ confidence < 0.9)
  ┌──────┐
  │ ▓▓▓▓ │  ← чёткий портрет
  │▓ OO ▓│
  │ ▓▓▓▓ │
  └──────┘
   «Торнин (?)»

Этап 4: Известен (confidence ≥ 0.9)
  ┌──────┐
  │ ████ │  ← чёткий портрет
  │█ OO █│
  │ ████ │
  └──────┘
   «Торнин»
```

#### C.5. Observable Signals Overlay

```
     ┌──────────┐
     │   🗣️     │  ← activity badge (говорит)
     │  Торнин  │  ← name (если recognition ≥ 0.6)
     │ ┌──────┐ │
     │ │ ████ │ │  ← sprite
     │ │█ OO █│ │
     │ │ ████ │ │
     │ │ █▓▓█ │ │  ← blood stain (blood_visibility)
     │ └──┬───┘ │
     │    │     │
     │  ╔╧═══╗  │  ← tense contour (синий)
     │  ║░░░║  │
     │  ╚════╝  │
     └─────┬───┘
           │
           ↓ gaze arrow (куда смотрит)
        [таргет]
```

#### C.6. Three-Channel Presentation Flow

```
                    WorldSnapshot (Reality)
                           │
                           ▼
              ┌────────────────────────┐
              │ ObservablePhysicsEngine │
              │ (PhysicalState)         │
              └────────────┬───────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │ PerceptionPhysicsEngine │
              │ (Manifestation)         │
              └────────────┬───────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │ PlayerCognition         │
              │ (PerceivedScene +       │
              │  Uncertainty)           │
              └────────────┬───────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
       ┌──────────┐ ┌──────────┐ ┌──────────┐
       │VisualDTO │ │AudibleDTO│ │Narrative │
       │          │ │          │ │   DTO    │
       └────┬─────┘ └────┬─────┘ └────┬─────┘
            │            │            │
            ▼            ▼            ▼
     SceneRenderer  AudioEngine  DMContractBuilder
                                          │
                                          ▼
                                   + ObservedFacts
                                          │
                                          ▼
                                         LLM
```

### Приложение D: Словарь терминов

| Термин | Определение |
|---|---|
| **Reality** | Существующая симуляция: WorldSnapshot, NPCState, Intent, Belief |
| **PhysicalState** | Физическая истира проявлений (что физически происходит с телом) |
| **Manifestation** | Наблюдаемая проекция PhysicalState (с учётом среды, но без наблюдателя) |
| **Presentation** | Что конкретный наблюдатель воспринял (с uncertainty) |
| **ObservableSignals** | Контракт из 8 каналов физически наблюдаемых проявлений |
| **ManifestationPolicy** | Детерминированный маппер психика→физика (необратимый) |
| **PerceptionPhysics** | Слой геометрии восприятия (видимость, слышимость, разрешение) |
| **PerceivedSignal** | Один воспринятый сигнал с confidence и possible_causes |
| **ObservedFacts** | Факты, донесённые игроку (для DM, UI-агностично) |
| **BodyTopology** | Физическая модель инвентаря как узлов тела |
| **RecognitionMemory** | Персистентная память распознавания NPC |
| **Visual First** | Правило: Visual/Audible/Narrative DTO рождаются из Cognition независимо |
| **Traceable origin** | Каждый UI-элемент имеет ссылку на сигнал в ObservableSignals |
| **Uncertainty** | Первоклассное свойство: signal + confidence + possible_causes |

---

## 19. ЗАКЛЮЧЕНИЕ

Это ТЗ описывает онтологический переход ENIGMA от трёхзвенки `World → DM → Player` к пятизвенке `Reality → Observable Physics → Perception Physics → Cognition → Presentation → DM`.

**Что это даёт:**
1. Игрок видит богатство симуляции без нарушения запрета телепатии
2. DM становится интерпретатором подтекста, а не камерой
3. Uncertainty становится первоклассным свойством
4. Фронтенд можно полностью заменить (спрайты → 3D → VR) без изменения DM
5. Через годы можно добавлять новые органы чувств, животных, слепых NPC, приборы, магию

**Что это требует:**
1. 8 новых ADR
2. 6 новых YAML-контрактов
3. 10 спринтов (~50-70 дней)
4. Расширение Устава §17-§20
5. Новые DNA-метрики (UIH, NRR)

**Главный принцип:** мир — первичная истина. UI никогда не должен придумывать информацию. Он может только визуализировать, агрегировать, фильтровать, делать наблюдаемое удобнее.

Если этот принцип сохранить, ENIGMA останется симуляцией, а не превратится в игру с «магическим HUD». Именно это будет одним из её самых сильных отличий от большинства RPG.

---

**КОНЦЕЦ ТЗ**

**Статус:** готов к ревью архитекторами #1, #2, #3
**Следующий шаг:** утверждение спринтов P1-P10, назначение ADR-номеров, запуск Sprint P1
