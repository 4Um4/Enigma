# ТЗ: Лаборатория калибровки психики ENIGMA

**Версия документа:** `2.0` (актуализация после M1-ядра, сессии S220–S222, Вариант B)
**Статус реализации:** M0 ЗАВЕРШЁН (S213) + M1-ЯДРО ЗАВЕРШЕНО (S220–S222): Intervention Routing (ADR-O-367), ScenarioPlayer, нативные графики Pygame. UI = полноэкранный режим Map Editor (F5), исключение из §1.1 — ADR-O-368. 62 теста лаборатории. Ключевое открытие M0 — 0.3; ключевые решения M1 — Addendum M1 (раздел 0.4).`
**Целевая версия ENIGMA:** `0.5.3.8.x` и выше (текущий релиз — `0.5.3.8.3`)
**Статус:** `IMPLEMENTATION-READY`
**Связанные артефакты:** `backend/tests/sandbox/SUPERBOX/`, `backend/tests/sandbox/calibration/`, `config/canon/truth_state_tavern.json`, `config/npc/individuals/lusya.json`
**Кодовый префикс путей:** все пути в документе указаны относительно корня репозитория `Enigma-V.0.5.3.8.3_-/`.

---

## 0. Главная задача

Нам нужен единый интерактивный тестовый стенд для калибровки всех параметров, влияющих на психику и поведение NPC в ENIGMA.

Это **не** обычный unit-тест.
Это **не** просто проверка отсутствия `NaN`.
Это **не** просто parameter sweep.

Нам нужен **Psychology Calibration Laboratory** — инструмент, позволяющий человеку без глубокого знания внутренней математики ENIGMA двигать параметры слайдерами, запускать одну и ту же ситуацию и наблюдать, как меняется NPC.

### 0.1. Главная цель калибровки

> Найти такую область параметров ENIGMA, при которой NPC остаются причинно связанными и узнаваемыми, но становятся яркими, быстро изменяющимися, непредсказуемыми и трагикомедийными.

Нас сейчас **не** интересует максимальный бытовой реализм.
Нас интересует:

```text
causal coherence
    + emotional expressiveness
    + rapid character evolution
    + player-visible consequences
```

NPC должен вести себя так, чтобы игрок мог подумать:

> «Я только что реально изменил этого человека».

### 0.2. Что уже есть в ENIGMA и что нужно добавить

В репозитории уже существуют:
- `backend/tests/sandbox/SUPERBOX/` — сценарные тесты каузальной инвариантности (25+ файлов);
- `backend/tests/sandbox/calibration/` — скелет sweep-инфраструктуры (`contracts.py`, `isk.py`, `run_sweep.py`);
- `backend/app/services/probes/` — 9 зондов инвариантности;
- `diagnostics/dna_metrics.py` — 25+ метрик (SHI, NPI, BCI и др.);
- `backend/app/services/npc/decision_hub.py` — DecisionHub, чистая функция;
- `backend/app/services/tick_orchestrator.py` — 10-фазный tick orchestrator;
- `config/canon/truth_state_tavern.json` — готовый сценарий «Серебряный Волк» (17 секретов, 20 отношений).

**Существовало на старте M0 — создано в S213** (всё, кроме UI, DRAMATIC SESSION и EnigmaPhaseEngine):
- `backend/app/services/calibration/` (overlay, preset_io, preset_materializer, experiment_runner, observability_tap, metrics/, superbox_adapter);
- метрики M0: `character_change_rate`, `decision_diversity`, `loop_rate`, `event_responsiveness` (источник — IntentEventAdapter через EventBus, см. 14.2); `causal_depth` = честный `None` до подключения источника цепочек (DEBT-CAUSAL-DEPTH, M2);
- W-IR: `personality_from_legacy` читает `psyche.identity_rigidity` — параметр калибруем (ранее всегда 0.5).

**По-прежнему не существует:** режим DRAMATIC SESSION; реализация `EnigmaPhaseEngine` (M3); WOW Density / ZoneClassifier (M2); кнопки игрока в UI, timeline, A/B-режим, сохранение пресета, экспорт (остаток M1 — см. Plan, Addendum B).

**Создано в M1-ядре (S220–S222):** UI Лаборатории — полноэкранный Pygame-режим Map Editor (F5, `lab_screen.py` + `graphs.py`); Intervention Consequence Routing (ADR-O-367); ScenarioPlayer (`scenario_player.py` + дефолтный сценарий `config/calibration/scenarios/trust_probe_v1.yaml`).
- модуля `settings_psychology.py` — все константы живут в `backend/app/core/constants.py`;
- реализации `EnigmaPhaseEngine` — заглушка `pass` в `backend/tests/sandbox/calibration/run_sweep.py:10-12`;
- UI лаборатории калибровки;
- метрик `WOW Density`, `Character Change Rate`, `Decision Diversity` (см. раздел 14);
- режима `DRAMATIC SESSION` 30–50 минут с гибким масштабом времени.

Лаборатория должна стать надстройкой над существующей инфраструктурой, **а не параллельной симуляцией**.

### 0.3. Открытие M0 (S213): судьбы не возникают из вакуума

Зонный прогон 150 тиков × 3 контрольных пресета (idle-среда, offline-mock):

| Пресет | character_change | decision_diversity | loop_rate | Зона (по 16.1) |
|---|---|---|---|---|
| mannequin | 0.0060 | 0.213 | 1.0 | МАНЕКЕН |
| chaos | 0.0066 | 0.217 | 1.0 | МАНЕКЕН |
| enigma_golden | 0.0072 | 0.356 | 1.0 | МАНЕКЕН |

Выводы:
1. Idle-среда без вмешательств классифицирует **любой** пресет как МАНЕКЕН: при ~300 событий за сессию диалоговые дельты нулевые (`social_dialogue:NEUTRAL`, effect_value=0.0). Причинная среда богата событийно, но сама себя не накачивает.
2. Сквозной сигнал пресетов уже различим (golden: diversity +68% против mannequin) — ручки калибровки работают.
3. **Условие существования зоны ENIGMA — событийная накачка** (ScenarioPlayer, раздел 11): поднимается с «удобства» до обязательного условия тестирования зон в M1.
4. Replay-ядро (statuses / nan / final_npc_state / npc_captures) покадрово детерминировано; rel/l1 — асинхронный слой одного подписчика, наблюдается отдельно до quiesce-границы (DEBT-QUIESCE).

---

### 0.4. Достижения M1-ядра (S220–S222, master-актуализация)

**Вариант B (master-решение):** никакого Next.js — Лаборатория живёт внутри Pygame Map Editor (`frontend/map_editor/ui/lab_screen.py`, вход F5), связь — прямые Python-импорты. Исключение из Устава §1.1 — ADR-O-368 (dev-enclave; allowlist `scripts/lint_frontend_isolation.py`; production UI — под запретом по-прежнему).

**Правило M1 (обязательно для всех следующих сессий):**
> Лаборатория — потребитель production causal spine, а не второй production spine. Не переписывать causal architecture ради лаборатории.

1. **Intervention Consequence Routing (S220, ADR-O-367):** вмешательства со структурированной семантикой (`semantic_action` ∈ {HELP, BLACKMAIL, ACCUSE} — ядро текст НЕ парсит, L4.1) маршрутизируются в production write-path `ActionConsequenceCompiler` → `RelationshipStore.update` (SSOT). Runtime-доказательство: HELP Люсе на тике 11 → `trust(maid_lusya→player): None → 20.0, fear → −10.0`; идемпотентность (детерминированный action_id).
2. **ScenarioPlayer (S221):** YAML-таймлайн (`config/calibration/scenarios/*.yaml`; формат: scenario_id/description/seed/events[{tick, action, target, secret_id?}]), строгий валидатор (громкие отказы: неизвестное действие/ключ, tick<1, BLACKMAIL без secret_id). Replay-identity: журнал эмуляций в ExperimentResult (вход/эмуляция/не-испущенные emitted=False) + детерминизм ядра. Граница «не второй оркестратор» — AST-тест.
3. **Нативные графики (S222):** `frontend/map_editor/ui/graphs.py` (LineGraph/BarChart — чистые рендереры, только pygame.draw, русский UI, без эмодзи); правая панель LabScreen: динамика Доверия (−100..100) и Стресса (0..100) выбранного NPC (клик по карточке) + полосы драйвов.

**Остаток M1 (для Приёмника, детально — Plan, Addendum B):** кнопки игрока в UI (маппинг 11.2 валиден, подставлять семантику в payload), timeline (9), A/B-режим (18), сохранение пресета (23), экспорт CSV/JSON, DRAMATIC SESSION-профили (3.2), DEBT-QUIESCE.

**Открытие M1 (важно для M2):** вмешательство HELP — прямое следствие открытия 0.3: судьбы не возникают из вакуума; scripted-накачка через ScenarioPlayer теперь машинно-воспроизводима. Однако социальный idle-контур по-прежнему глух (SOCIAL_SUBSCRIBER: missing relationship_store, каждый тик — runtime-подтверждение DEBT-SOC) — вероятная первопричина остаточной нулевой динамики social_dialogue-дельт в idle.

---

## 1. Почему существующего тестирования недостаточно

Существующие SUPERBOX и изолированные тесты (`backend/tests/sandbox/SUPERBOX/scenarios/`) полезны для проверки инвариантов:

- `epistemic_divergence_test.py` — доказывает, что у двух NPC формируются разные убеждения;
- `epistemic_decision_divergence_test.py` — доказывает, что разные убеждения ведут к разным решениям;
- `epistemic_persistence_test.py` — доказывает, что убеждения выживают save/load;
- `modifier_composition_test.py` — доказывает аддитивность модификаторов;
- `epistemic_membrane_hardening_test.py` — доказывает, что NPC не могут читать мысли напрямую.

Они должны остаться. Но они отвечают на вопрос:

> «Правильно ли работает формула?»

Нам нужен ещё один класс тестов:

> «Как ведёт себя вся система, когда эти формулы соединены вместе?»

Сейчас мы практически не можем увидеть:

- насколько быстро меняется NPC;
- насколько сильно одна эмоция влияет на другую;
- когда NPC начинает зацикливаться;
- когда NPC становится слишком стабильным;
- когда NPC становится хаотичным;
- насколько быстро меняется `trust` (хранится в `backend/app/services/memory/relationship_store.py`);
- насколько быстро меняются beliefs (L2.5 в `crystallized_belief_store.py`);
- насколько сильно perception деформирует decision (через `PerceptualKernel` в `npc_state.py:537-560`);
- насколько быстро формируется конфликт;
- насколько быстро NPC переходит из одного состояния личности в другое (L0→L1→L1.5→L2.5→L3, см. `architecture/identity.yaml`);
- насколько заметны изменения игроку;
- какие комбинации параметров создают интересную драматургию.

Нужен инструмент, который позволит увидеть **всю причинную цепочку** на едином экране.

---

## 2. Главный принцип лаборатории

Лаборатория должна разделять два понятия.

### 2.1. Техническая корректность

NPC не должен:
- ломаться;
- уходить в `NaN`;
- бесконечно повторять одно действие (это уже проверяется `probes/l3_ephemeral_probe.py` и `diagnostics/health_checkers/invariant_health.py` через `INV-NPC-FROZEN`);
- нарушать диапазоны параметров (см. таблицу в Приложении A);
- терять причинность (Invariants I/II/III, см. `architecture/diagnostics.yaml`);
- получать невозможные состояния.

### 2.2. Игровая выразительность

NPC должен:
- реагировать на события;
- менять отношения (`relationship_store`);
- менять убеждения (`crystallized_belief_store`);
- менять стратегию поведения (через `effective_drives` и `intent`);
- демонстрировать последствия прошлых событий (`EventMemory.decayed()`);
- иногда ошибаться (через `DistortionProfile.threat_bias`, `trust_bias`, `salience_bias`);
- иногда переоценивать ситуацию (через `THREAT_AMPLIFICATION_FACTOR = 0.15`);
- иногда делать глупости (через `SCORE_NOISE_RANGE = 0.10` и `REACTIVE_URGENCY_THRESHOLD = 0.8`);
- попадать в противоречия (`cognitive_dissonance.Contradiction`);
- становиться лучше или хуже (`character.self_integrity`);
- создавать цепочки событий (`CausalEntry` в `psychological.py:55-98`).

### 2.3. Идеальный NPC ENIGMA

Идеальный NPC ENIGMA находится между двумя крайностями:

```text
        «манекен»                          «хаос»
        NPC почти не меняется              NPC меняется случайно
        долго держит одно состояние       противоречит самому себе
        редко реагирует                   реагирует на всё
        решения предсказуемы              теряет идентичность
        игрок не замечает динамики        игрок не видит личности
              │                                │
              │      ┌───────────────────┐     │
              │      │   ENIGMA ZONE     │     │
              └─────►│   «живой          │◄────┘
                     │   трагикомический │
                     │   NPC»            │
                     └───────────────────┘
```

Нам нужна зона: **«живой трагикомический NPC»**.

---

## 3. Ключевой временной масштаб

Особое требование:

> Одна игровая сессия MVP ≈ 30–50 минут реального времени.

Поэтому нельзя калибровать NPC только на:
- 1000 тиков;
- 1800 тиков;
- 75 игровых дней.

Это полезно для стресс-тестов (см. `drift_laboratory.py` с `long_horizon_ticks=100_000`), но не для первоначальной настройки игрового опыта.

### 3.1. Режим `DRAMATIC SESSION`

Нужен специальный режим.

Продолжительность:
- 15 минут;
- 30 минут (эталон);
- 45 минут;
- 60 минут.

Основной эталон: **30–50 минут**.

### 3.2. Внутреннее время

В текущем ENIGMA `TICK_REAL_SECONDS = 300` (5 минут = 1 тик, см. `constants.py:178`). Это означает, что 30 минут реального времени = 6 тиков, что **недостаточно** для драматической плотности.

Лаборатория должна позволять конфигурировать:
- `ticks_per_real_minute` — сколько тиков проходит за минуту реального времени;
- `game_seconds_per_tick` — сколько игрового времени симулируется за тик (по умолчанию 300).

**Для драматической сессии 30 минут** рекомендуется профиль:
```yaml
dramatic_session:
  real_minutes: 30
  ticks_per_real_minute: 10    # 300 тиков за сессию
  game_seconds_per_tick: 60    # 1 тик = 1 минута игрового времени
  total_game_minutes: 300      # 5 часов игрового времени
```

### 3.3. Что должно быть видно

Лаборатория должна позволять смотреть:

```text
Tick → событие → восприятие → belief → emotion/pressure → decision → действие → последствия → изменение NPC
```

и видеть этот процесс во времени.

---

## 4. Что должно быть на экране

Интерфейс **полностью на русском языке**.

Не использовать английские названия как основной интерфейс.

Если внутреннее имя параметра важно для разработчика — показывать его вторым текстом меньшим кегом и приглушённым цветом.

Например:

```text
Жёсткость личности
identity_rigidity
```

### 4.1. Запрет на использование английского в основном UI

| Слой | Язык |
|---|---|
| Заголовки панелей | Русский |
| Названия параметров (слайдеров) | Русский + английский вторым текстом |
| Названия метрик | Русский + английский вторым текстом |
| Описания (tooltips) | Русский |
| Кнопки действий | Русский |
| Логи причинных цепочек | Русский |
| Имена NPC | Русские (`Люся`, `Борко`, `Горан`, `Торнин`, `Шэдоу`, `Орм`) |
| Внутренние ID в JSON/CSV | Английский (`maid_lusya`, `guard_borko`) |

### 4.2. Цветовая легенда зон

| Зона | Цвет (HEX) | Семантика |
|---|---|---|
| Манекен | `#8B0000` (тёмно-красный) | NPC почти не меняется |
| Хаос | `#FF4500` (оранжево-красный) | NPC меняется хаотично |
| ENIGMA | `#2E8B57` (зелёный) | Целевая зона |
| Предупреждение | `#FFA500` (оранжевый) | Близко к границе |
| NaN/ошибка | `#FF0000` (алый) | Технический сбой |

---

## 5. Левая панель — параметры NPC

Все параметры должны быть представлены слайдерами.

### 5.1. Минимальный набор слайдеров (с привязкой к реальным параметрам ENIGMA)

> Полная карта реальных параметров → см. **Приложение A**.
> Параметры, помеченные `[PLAN]`, в текущей версии ENIGMA не подключены к DecisionHub и должны отображаться в UI как «Параметр запланирован / ещё не подключён».

#### 5.1.1. Личность

| UI-имя (RU) | Внутреннее имя | Файл:строка | Диапазон | По умолчанию |
|---|---|---|---|---|
| Жёсткость личности | `identity_rigidity` | `models/npc_state.py:376` | `0.0–1.0` | `0.5` |
| Инерция личности | `TRAIT_DECAY_RATE` (обратное) | `core/constants.py:78` | `0.0–0.1` | `0.02` |
| Открытость к изменениям | `[PLAN] core_orientation` | `models/npc_profile.py:90` | enum | `survival` |
| Сила привычки | `INTENT_INERTIA_WEIGHT` | `core/constants.py:74` | `0.0–1.0` | `0.20` |
| Сила идентичности | `identity_attachment` | `models/npc_profile.py:90` | `0.0–1.0` | `1.0` |
| Устойчивость убеждений | `THETA_UP` / `THETA_DOWN` | `core/constants.py:76-77` | `0.0–1.0` | `0.60 / 0.20` |

#### 5.1.2. Восприятие

| UI-имя (RU) | Внутреннее имя | Файл:строка | Диапазон | По умолчанию |
|---|---|---|---|---|
| Чувствительность к угрозе | `PerceptualKernel.threat_gradient` | `models/npc_state.py:538` | `0.0–1.0` | `0.0` |
| Неопределённость | `PerceptualKernel.uncertainty` | `models/npc_state.py:538` | `0.0–1.0` | `0.0` |
| Чувствительность к аномалиям | `PerceptualKernel.anomaly_score` | `models/npc_state.py:540` | `0.0–1.0` | `0.0` |
| Телесная срочность | `PerceptualKernel.somatic_urgency` | `models/npc_state.py:544` | `0.0–1.0` | `0.0` |
| Интенсивность восприятия | `PERCEPTION_RADIUS["minor"]` | `core/constants.py:35` | `1.0–10.0` | `3.0` |
| Порог реакции | `MIN_INTENT_SCORE` | `core/constants.py:86` | `0.0–0.5` | `0.15` |

#### 5.1.3. Отношения

| UI-имя (RU) | Внутреннее имя | Файл:строка | Диапазон | По умолчанию |
|---|---|---|---|---|
| Доверие | `SOCIAL_TRUST_NEUTRAL` (база) | `core/constants.py:347` | `-100…+100` | `0.0` |
| Скорость роста доверия | `[PLAN] trust_growth_rate` | — | `0.0–1.0` | `0.1` |
| Скорость падения доверия | `[PLAN] trust_decay_rate` | — | `0.0–1.0` | `0.3` |
| Чувствительность к предательству | `DISTRUST_STRESS_BOOST` | `core/constants.py:58` | `0.0–30.0` | `8.0` |
| Способность прощать | `[PLAN] forgiveness_rate` | — | `0.0–1.0` | `0.05` |
| Значимость другого NPC | `salience.tier` | `core/constants.py:330` | `0.0–1.0` | `0.15` |

#### 5.1.4. Эмоциональная динамика

| UI-имя (RU) | Внутреннее имя | Файл:строка | Диапазон | По умолчанию |
|---|---|---|---|---|
| Скорость эмоционального изменения | `ETKE_IK_SUBSTEP_DT` | `core/constants.py:214` | `0.01–0.5` | `0.1` |
| Сила эмоциональной реакции | `REACTIVE_URGENCY_THRESHOLD` | `core/constants.py:99` | `0.5–1.0` | `0.8` |
| Скорость затухания эмоций | `AFFECT_DECAY_BASE_RATE` | `core/constants.py:215` | `0.0–0.5` | `0.05` |
| Накопление напряжения | `NPCState.affective_load` | `models/npc_state.py:579` | `0.0–1.5` | `0.0` |
| Порог эмоционального перелома | `NPCState.breakpoint` | `models/npc_state.py:352` | `0.0–100.0` | `65.0` |
| Сила давления | `pressure_resistance` | `models/npc_state.py:599` | `0.0–100.0` | `0.0` |

#### 5.1.5. Решения

| UI-имя (RU) | Внутреннее имя | Файл:строка | Диапазон | По умолчанию |
|---|---|---|---|---|
| Сила текущего желания | `drives_base[drive]` | `models/npc_state.py:344` | `0.0–1.0` (сумма = 1.0) | `control:0.3, significance:0.25, fear:0.2, desire:0.25` |
| Сила прошлого опыта | `intent_inertia` (через `INTENT_INERTIA_MAX_TICKS`) | `core/constants.py:73` | `0–30` тиков | `10` |
| Сила страха | `FEAR_FLEE_THRESHOLD` | `core/constants.py:84` | `0.0–1.0` | `0.65` |
| Сила социальной нормы | `loyalty_base` | `models/npc_state.py:353` | `0.0–100.0` | `30.0` |
| Сила рационального выбора | `COMMITMENT_K` | `core/constants.py:88` | `0.0–5.0` | `2.5` |
| Стоимость ошибки | `SWITCHING_COST_BASE` | `core/constants.py:89` | `0.0–0.5` | `0.05` |
| Склонность к риску | `risk_profile` | `services/npc/decision/risk_profile.py` | enum | `neutral` |

#### 5.1.6. Эпистемика

| UI-имя (RU) | Внутреннее имя | Файл:строка | Диапазон | По умолчанию |
|---|---|---|---|---|
| Скорость формирования убеждения | `BeliefFragment.confidence` (рост) | `models/npc/beliefs.py:18` | `0.0–1.0` | `0.5` |
| Сила нового свидетельства | `EventMemory.confidence` | `models/npc_state.py:222` | `0.0–1.0` | `1.0` |
| Сопротивление новой информации | `THETA_UP` | `core/constants.py:76` | `0.0–1.0` | `0.60` |
| Уверенность | `EpistemicRecord.confidence` | `domain/epistemology.py:38` | `0.0–1.0` | `0.5` |
| Склонность к ошибочному выводу | `DistortionProfile.threat_bias` | `models/psychological.py:30` | `-1.0…+1.0` | `0.0` |
| Скорость пересмотра убеждений | `TRAIT_ACTIVATION_RATE` | `core/constants.py:79` | `0.0–1.0` | `0.15` |
| Любопытство / epistemic drive | `[PLAN] epistemic_drive` | — | `0.0–1.0` | `0.5` |

#### 5.1.7. Память

| UI-имя (RU) | Внутреннее имя | Файл:строка | Диапазон | По умолчанию |
|---|---|---|---|---|
| Скорость забывания | `EventMemory.decay_rate` | `models/npc_state.py:221` | `0.0–1.0` | `0.05` |
| Сила эмоциональной памяти | `AffectiveImprint.reinforcement` | `models/affect.py:25` | `0.0–1.0` | `0.5` |
| Сила памяти о событии | `EventMemory.importance` | `models/npc_state.py:218` | `0.0–1.0` | `0.5` |
| Влияние недавних событий | `recent_failures` | `models/npc_state.py:603` | `int` | `0` |
| Влияние старых событий | `STAGE_DETAILED ≥ 0.55, ABSTRACT ≥ 0.10` | `models/npc_state.py:322-325` | пороги | `0.55 / 0.10` |

### 5.2. Маркировка нереализованных параметров

Если конкретного параметра ещё нет в ENIGMA — лаборатория **НЕ** должна придумывать отдельную фальшивую реализацию.

В таком случае интерфейс должен помечать его:

```text
Любопытство / epistemic_drive
[ПАРАМЕТР ЗАПЛАНИРОВАН — ЕЩЁ НЕ ПОДКЛЮЧЁН]
Слайдер отключён. Влияет на целевую функцию как 0.
```

Полный список запланированных, но не подключённых параметров см. в Приложении A, колонка `[PLAN]`.

---

## 6. Каждый параметр должен иметь человеческое объяснение

При наведении на слайдер человек должен видеть tooltip.

### 6.1. Шаблон tooltip

```text
Жёсткость личности (identity_rigidity)

ЧТО ЭТО ЗНАЧИТ:
Насколько сильно NPC сопротивляется изменению своего характера и поведения.

  "0.0" — NPC легко меняется.
  "1.0" — NPC почти невозможно изменить.

ЕСЛИ УВЕЛИЧИТЬ:
  NPC дольше остаётся прежним.
  Игроку сложнее повлиять на него за одну сессию.

ЕСЛИ УМЕНЬШИТЬ:
  NPC быстрее меняется под воздействием событий.
  Возможна быстрая потеря характера (зона ХАОС).

ИГРОВОЙ ЭФФЕКТ:
  Высокое значение → устойчивый персонаж (зона МАНЕКЕН при >0.9).
  Низкое значение → персонаж может быстро «поплыть» (зона ХАОС при <0.2).

ИСТОЧНИК В КОДЕ:
  models/npc_state.py:376 (NPCPersonality.identity_rigidity)
  Используется в: decision_hub.py:_score_all (через effective_drives)
```

### 6.2. Минимальный объём описания

Каждый tooltip должен содержать не менее **5 пунктов**:
1. Что это значит (1–2 предложения);
2. Значение при `0.0`;
3. Значение при `1.0` (или max);
4. Что будет, если увеличить;
5. Что будет, если уменьшить;
6. Игровой эффект (с указанием зоны);
7. Источник в коде (file:line).

---

## 7. Очень важно: не делать вид, что все параметры независимы

Лаборатория должна показывать **взаимодействия параметров**.

### 7.1. Пример: цепочка «страх + доверие + неопределённость»

Высокий страх сам по себе может быть неинтересен.

Но:

```text
PerceptualKernel.threat_gradient ↑
    + RelationshipStore.trust(player) ↓
    + PerceptualKernel.uncertainty ↑
        ↓
    DistortionProfile.threat_bias > 0
        ↓
    ошибочная интерпретация события
        ↓
    BeliefFragment(PLAYER_HOSTILE, confidence ↑)
        ↓
    DecisionHub.compute(): intent = AVOID / BLOCK_PATH
        ↓
    новое событие: NPC избегает игрока
        ↓
    игрок совершает новое действие → эскалация конфликта
```

Именно такие цепочки нам нужны.

### 7.2. Возможности UI

Поэтому лаборатория должна позволять:
- менять **один** параметр;
- менять **группу** параметров (через пресеты-«наборы»);
- сравнивать результаты (см. раздел 18, A/B-режим).

### 7.3. Набор предустановленных «связок»

UI должен предлагать готовые связки параметров:

| Название связки | Что входит | Эффект |
|---|---|---|
| `ПОДОЗРИТЕЛЬНОСТЬ` | `threat_gradient=0.7`, `trust_bias=-0.3`, `THETA_UP=0.8` | NPC видит угрозы там, где их нет |
| `ПРОЩАЮЩИЙ` | `forgiveness_rate=0.8`, `DISTRUST_STRESS_BOOST=2.0`, `decay_rate=0.2` | NPC быстро возвращается к доверию |
| `ТРАВМИРОВАННЫЙ` | `affective_load=1.0`, `somatic_urgency=0.8`, `reinforcement=0.9` | NPC реагирует на триггеры |
| `ХАОТИЧНЫЙ` | `identity_rigidity=0.1`, `decay_rate=0.5`, `SCORE_NOISE_RANGE=0.3` | NPC меняется случайно |
| `МОНУМЕНТ` | `identity_rigidity=0.95`, `decay_rate=0.001`, `INTENT_INERTIA_WEIGHT=0.8` | NPC почти не меняется |

---

## 8. Главный экран — «Жизнь NPC»

В центре должен находиться один NPC.

Не просто график.

Нужно отображать его текущее состояние **человеческим языком**.

### 8.1. Пример вывода

```text
═══════════════════════════════════════════
  ЛЮСЯ  (maid_lusya)
  Служанка таверны «Серебряный Волк»
═══════════════════════════════════════════

  Сейчас считает игрока:    скорее надёжным
  Настроение:               раздражение
  Главная тревога:          потеря денег
  Последнее убеждение:      «Игрок что-то скрывает»
  Текущее намерение:       избегать разговора
  Уверенность:              63 %

  ── ВНУТРЕННЕЕ СОСТОЯНИЕ ──────────────
  stress:                  42.3 / 100
  affective_load:           0.71 / 1.5
  identity_integrity:       0.84 / 1.0
  pressure_resistance:     18.0 / 100
  willpower:               35 / 100     (current)
  breakpoint:              55 / 100     (threshold)

  ── ОТНОШЕНИЯ ─────────────────────────
  → player:     trust = +12   (нейтрально-положительное)
  → borko:      trust = +34   (дружеское)
  → shadow:     trust = -8    (подозрительное)
  → goran:      trust = +5    (нейтральное)

  ── АКТИВНЫЕ УБЕЖДЕНИЯ (L2.5) ────────
  • DANGER: confidence=0.42  (источник: слух)
  • PLAYER_HOSTILE: confidence=0.18 (источник: distorsion)
  • RUMOR_BANDITS: confidence=0.61  (источник: свидетель)

  ── АКТИВНЫЕ DRIVES ──────────────────
  effective_drives:
    fear:        0.58  ← доминирующий
    desire:      0.21
    control:     0.12
    significance: 0.09
```

### 8.2. Причинная цепочка рядом с NPC

Рядом должна отображаться **причинная цепочка** в реальном времени:

```text
┌── ПРИЧИННАЯ ЦЕПОЧКА ────────────────────────────────┐
│                                                       │
│  [Tick 0142]  Игрок солгал о деньгах                  │
│       ↓                                               │
│  [Tick 0142]  Люся заметила несоответствие            │
│       ↓  (perception_engine → ObservationRelation)    │
│  [Tick 0143]  Уверенность в подозрении  +18 %         │
│       ↓  (belief_transition_engine)                   │
│  [Tick 0143]  Trust(player)  -12                      │
│       ↓  (relationship_store.apply_delta)              │
│  [Tick 0143]  Threat gradient  +0.09                  │
│       ↓  (PerceptualKernel.update)                    │
│  [Tick 0144]  Decision: intent = AVOID_PLAYER         │
│       ↓  (DecisionHub.compute → AgentAction)          │
│  [Tick 0144]  Игрок подошёл снова                     │
│       ↓                                               │
│  [Tick 0145]  Новая реакция: замораживается           │
│                                                       │
└───────────────────────────────────────────────────────┘
```

### 8.3. Источник данных для карточки NPC

Данные берутся напрямую из:
- `backend/app/models/npc_state.py:NPCState` (L2);
- `backend/app/services/memory/relationship_store.py` (trust);
- `backend/app/services/npc/crystallized_belief_store.py` (L2.5 beliefs);
- `backend/app/services/npc/drive_resolver.py` (EffectiveDrives);
- `backend/app/services/npc/perception_engine.py` (PerceptualKernel).

**Запрещено** выводить состояние NPC через LLM. LLM — только текстовая реализация реплик.

---

## 9. Обязательный режим «История изменений»

Нужен `timeline`.

### 9.1. Пример

```text
00:00  Люся нейтральна к игроку                    (trust = 0)
02:10  Игрок помог с работой                        (event: HELP)
04:30  Trust +14                                    (trust = 14)
07:20  Люся услышала слух о ворах                   (event: RUMOR_HEARD)
09:10  Confidence в слухе +23 %                      (belief: RUMOR_BANDITS = 0.23)
12:40  Начала избегать игрока                        (intent: AVOID_PLAYER)
17:30  Игрок подарил предмет                         (event: GIFT)
19:00  Конфликт убеждений                            (cognitive_dissonance.Contradiction)
23:40  Люся пересмотрела отношение                   (belief_revision_engine)
31:20  Trust +27                                     (trust = 41)
36:10  Люся сама инициировала разговор                (proactive intent: TALK)
```

Это чрезвычайно важно.

Мы должны видеть не только:

> «какое сейчас значение trust»

но:

> «почему оно стало таким».

### 9.2. Источник данных timeline

Timeline формируется из:
- `EventDTO` (источник: `EventBus`, фильтр `persistence_level ∈ {session, campaign}`);
- `TraitDriftEvent` (источник: `BreakProgressEngine`, сохраняется в `L1Chronicle`);
- `CausalEntry` (источник: `StateApplicator`, см. `psychological.py:55-98`);
- `BeliefCrystallizationEvent` (источник: `BeliefCrystallizationEngine`);
- `IntentEvent` (источник: `IntentEventAdapter`, фаза 6 тик-оркестратора).

Для каждого события timeline должен показывать:
- `tick` (игровой тик);
- `real_time` (стендовое время);
- `event_type`;
- `actor`;
- `target`;
- `delta` (если есть);
- `causal_parent_id` (ссылка на породившее событие — для построения дерева).

---

## 10. Режим «Наблюдатель»

### 10.1. Кнопки управления

Добавить кнопку:

```text
▶ Запустить
```

После запуска NPC начинает жить.

Должны быть кнопки:

| Кнопка | Действие | Внутренний вызов |
|---|---|---|
| `▶ Запустить` | Старт симуляции | `ExperimentRunner.start()` |
| `⏸ Пауза` | Приостановить тики | `ExperimentRunner.pause()` |
| `⏭ Следующий тик` | Один тик | `ExperimentRunner.step()` |
| `×1` | Реальное время | `runner.set_speed(1)` |
| `×5` | Ускорение ×5 | `runner.set_speed(5)` |
| `×20` | Ускорение ×20 | `runner.set_speed(20)` |
| `×100` | Ускорение ×100 | `runner.set_speed(100)` |
| `↻ Перезапуск` | Пересоздать сессию с тем же seed | `runner.restart(seed=...)` |
| `⟲ Сброс параметров` | Вернуть все слайдеры к default | `ui.reset_sliders()` |

### 10.2. Уведомления о событиях

При каждом **важном** изменении интерфейс должен показывать событие.

Классификатор «важное изменение» см. в разделе 15 (WOW Density).

UI должен подсвечивать карточку NPC вспышкой (200 мс, цвет по типу события).

---

## 11. Режим «Вмешательство игрока»

Это критически важно.

Мы хотим тестировать не только автономную жизнь NPC.

### 11.1. Кнопки событий игрока

```text
┌── ИГРОК ──────────────────┐  ┌── МИР ─────────────────────┐
│  Помог                     │  │  NPC получил травму         │
│  Соврал                    │  │  Друг NPC умер              │
│  Украл                     │  │  Появилась угроза           │
│  Оскорбил                  │  │  NPC узнал секрет           │
│  Похвалил                  │  │  Изменился статус NPC       │
│  Дал подарок               │  │  Появился новый человек     │
│  Предал                    │  │  Слух распространился       │
│  Защитил NPC               │  │  Начался праздник           │
│  Испугал NPC               │  │  Смена погоды               │
│  Рассказал правду          │  │  Приход стражи              │
│  Распространил слух        │  │  NPC назначили на должность │
│  Совершил странный поступок│  │  NPC понизили               │
└────────────────────────────┘  └─────────────────────────────┘
```

### 11.2. Маппинг кнопок → `ActionType` → `Intent`

Каждая кнопка должна вызывать `InterventionEvent.from_player_action(action_text, player_name, tick, **kwargs)` (см. `backend/app/contracts/interventions.py:27`) и скармливать его в `TickOrchestrator.execute(interventions=[...])`.

**M1/S220 (ADR-O-367):** обязательный формат kwargs для действий с последствиями — `semantic_action=<UPPERCASE>`, `target_reference=<npc_id>`, `target_id=<npc_id>` (+ `secret_id` для BLACKMAIL/DIALOGUE). Ядро текст не парсит (L4.1) — text-only payload умирает на guard. Зарегистрированные семантики ядра: HELP, BLACKMAIL, ACCUSE (consequence-ветвь), ATTACK (боевая труба), MOVE, THREATEN, PERSUADE, GIVE (директивы), DIALOGUE. Часть кнопок 11.1 (Соврал/Оскорбил/Похвалил и пр. — speech-act-семантики) потребует мини-ADR на расширение реестра (прецедент ADR-O-362).

Маппинг (часть):

| UI-кнопка (RU) | `ActionType` | `Intent` (после `action_to_intent`) | `secret_id` (если применимо) |
|---|---|---|---|
| Помог | `HELP` | `OFFER_JOB` / `GIVE_ITEM` | — |
| Соврал | `DIALOGUE` (semantic_action=`lie`) | `TALK` + `distortion` | optional |
| Украл | `BLACKMAIL` / steal | `STEAL` (через `action_intent_bridge.py`) | optional |
| Оскорбил | `DIALOGUE` (semantic_action=`insult`) | `TALK` + `SpeechAct.INSULT` | — |
| Похвалил | `DIALOGUE` (semantic_action=`compliment`) | `TALK` + `SpeechAct.COMPLIMENT` | — |
| Дал подарок | `HELP` (kind=`gift`) | `GIVE_ITEM` | — |
| Предал | `DIALOGUE` (semantic_action=`betray`) | `TALK` + `SpeechAct.ACCUSATION` | target_secret |
| Защитил NPC | `HELP` (kind=`protect`) | `DEFEND` | — |
| Испугал NPC | `DIALOGUE` (semantic_action=`threaten`) | `TALK` + `SpeechAct.THREAT` | — |
| Рассказал правду | `DIALOGUE` (semantic_action=`reveal`) | `TALK` + `SpeechAct.ASSERT` | target_secret |

### 11.3. Цепочка после события

После каждого события лаборатория должна показывать:

```text
событие → восприятие → изменение состояния → решение → последствия
```

в виде раскрывающейся панели под кнопкой.

### 11.4. Источник истины

Все вмешательства **обязаны** идти через production-pipeline ENIGMA:

```text
Calibration UI (кнопка) — НЕ РЕАЛИЗОВАНО (остаток M1); для scripted-событий — ScenarioPlayer
    ↓  InterventionEvent.from_player_action(..., semantic_action=..., target_id=...)
Experiment Runner (start/step/stop — РЕАЛИЗОВАНО)
    ↓  interventions=[...] → idle_tick
TickOrchestrator.execute(...) — РЕАЛИЗОВАНО (ADR-O-367: consequence-ветвь → ActionConsequenceCompiler)
    ↓  (10 фаз, включая DecisionHub.compute)
NPC state mutation
    ↓  StateApplicator.atomic_commit()
Persistence (SQLite)
    ↓
Observability (CausalEntry → DNA metrics → UI)
```

Запрещено внедрять кнопки, которые мутируют NPCState напрямую в обход `StateApplicator`.

---

## 12. Главный эксперимент: «Изменение NPC на глазах»

Нужен специальный сценарий.

### 12.1. Начало

NPC имеет исходное состояние.

Например:

> «Люся — осторожная, нейтральная, немного подозрительная» (`identity_rigidity=0.55`, `trust=0`, `DANGER.confidence=0.15`).

Затем игрок совершает последовательность действий.

### 12.2. Контрольные точки

Лаборатория должна показывать **снимки состояния NPC** в фиксированные моменты:

```text
Исходная Люся            (T = 00:00)
    ↓
после 5 минут            (T = 05:00)
    ↓
после 10 минут           (T = 10:00)
    ↓
после 20 минут           (T = 20:00)
    ↓
после 30 минут           (T = 30:00)
    ↓
после 45 минут           (T = 45:00)
```

И человек должен визуально увидеть: **это уже другой NPC**.

Но при этом изменение должно быть **объяснимым**.

### 12.3. Снимок состояния (snapshot card)

Каждый снимок — это карточка, содержащая:

```text
┌── T = 10:00 ─────────────────────────┐
│  ЛЮСЯ                                │
│                                      │
│  Trust(player):   +4   (было 0)      │
│  Настроение:      спокойствие        │
│  Активный drive:   desire 0.42        │
│  Активное belief:  PLAYER_FRIENDLY    │
│                  confidence = 0.21   │
│  Текущий intent:  TALK(player)       │
│                                      │
│  Δ за 10 мин:                        │
│    +4 trust, +0.21 confidence,       │
│    intent: IDLE → TALK                │
│                                      │
│  Метрики:                            │
│    WOW events: 2                     │
│    Character Change: 0.18            │
└──────────────────────────────────────┘
```

### 12.4. Дельта-режим

Опционально: показывать только **изменения** между снимками:

```text
T=10:00 → T=20:00
  trust:        +4 → +27   (Δ +23)
  DANGER.conf:  0.15 → 0.42 (Δ +0.27)
  intent:       TALK → AVOID_PLAYER
  WOW events:   2 → 5 (Δ +3)
```

---

## 13. Целевой эффект

Нам нужен не реализм уровня симулятора человеческой жизни.

Нам нужна **трагикомическая выразительность**.

### 13.1. Примеры целевых цепочек

NPC должен иметь возможность попасть в такие цепочки:

#### Цепочка A: «ложное подозрение → эскалация»

```text
игрок соврал
    → NPC заподозрил (DANGER.conf ↑)
    → NPC неправильно понял (DistortionProfile.threat_bias > 0)
    → начал избегать игрока (intent = AVOID_PLAYER)
    → игрок решил, что NPC его ненавидит (player_action = PROVOKE)
    → стал холоднее (player_self_integrity ↓)
    → NPC получил подтверждение своей теории (belief_revision ↑)
    → конфликт усилился (intent = BLOCK_PATH)
```

#### Цепочка B: «переоценка доверия → катастрофа»

```text
игрок помог
    → NPC начал доверять (trust ↑↑↑)
    → NPC переоценил доверие (trust > SOCIAL_TRUST_HIGH_THRESHOLD = 50)
    → раскрыл секрет (SpeechAct = ASSERT, secret_id revealed)
    → игрок использовал секрет (action_type = BLACKMAIL)
    → доверие рухнуло (trust = -50, DISTRUST_STRESS_BOOST = +8 stress)
    → NPC стал параноиком (THREAT_AMPLIFICATION_FACTOR × resentment)
```

#### Цепочка C: «испуг → ошибка → раскаяние»

```text
NPC испугался (PerceptualKernel.threat_gradient ↑)
    → сделал неправильный вывод (DistortionProfile.threat_bias > 0.3)
    → совершил глупость (intent = FLEE, abandoned_post)
    → получил последствия (REACTIVE_URGENCY_THRESHOLD hit, stress +20)
    → изменил отношение к игроку (trust -15)
    → потом понял, что ошибался (belief_revision_engine пересмотрел)
    → конфликт убеждений (cognitive_dissonance.Contradiction)
    → новый intent: APOLOGIZE
```

**Вот это — материал для ENIGMA.**

### 13.2. Контрольный тест «Цепочка воспроизводима»

Каждая из цепочек A/B/C должна быть воспроизводима при одном и том же `seed` и конфигурации. Если два запуска дают разные цепочки — конфигурация помечается как **нестабильная** (зона ХАОС).

---

## 14. Ввести понятие «Драматическая плотность»

Лаборатория должна измерять **не только** технические ошибки.

Нужны **игровые метрики**.

### 14.1. Минимальный набор метрик

| Метрика | Имя в коде | Формула (кратко) | Целевой диапазон |
|---|---|---|---|
| Character Change Rate | `character_change_rate` | `Δ(state_vector) / N_minutes` | `0.3–0.8` |
| Decision Diversity | `decision_diversity` | `unique(intents) / total_decisions` | `0.4–0.9` |
| Emotional Volatility | `emotional_volatility` | `std(emotion_history)` | `0.15–0.5` |
| Belief Revision Rate | `belief_revision_rate` | `revisions_count / N_ticks` | `0.05–0.3` |
| Relationship Dynamics | `relationship_dynamics` | `Δ(trust) per minute` | `0.5–3.0` |
| Event Responsiveness | `event_responsiveness` | `reactions / events_received` | `0.6–1.0` |
| Causal Depth | `causal_depth` | `mean(len(causal_chain))` | `2.0–6.0` |
| Loop Rate | `loop_rate` | `repeating_intents / total_intents` | `<0.15` |
| Character Stability | `character_stability` | `1 - (Δcore_traits / max_Δ)` | `0.5–0.9` |
| WOW Density | `wow_density` | см. раздел 15 | `0.4–1.2 /min` |

### 14.2. Источники данных для метрик

| Метрика | Источник в коде |
|---|---|
| Character Change Rate | `NPCStateAdapter.write_to_legacy` (snapshot diff) |
| Decision Diversity | `IntentEventAdapter` → EventBus → ObservabilityTap (S213: подтверждено — писателя `npc["intent"]` в снапшоте загрузчика НЕ существует; intent наблюдается только через шину) |
| Loop Rate | `IntentEventAdapter` → ObservabilityTap (межтиковые переходы label) |
| Event Responsiveness | ObservabilityTap: события/тик × смена label (наследует недетерминизм async-слоя — DEBT-QUIESCE; в replay-вердикт не входит) |
| Causal Depth | ИСТОЧНИК ОТСУТСТВУЕТ (S213): у диалоговых TraitDriftEvent нет временной оси для цепочек; проводка CausalEntry не подключена → метрика возвращает честный `None` (DEBT-CAUSAL-DEPTH, M2) |
| Emotional Volatility | `EmotionTransition` (фаза 9.1) |
| Belief Revision Rate | `belief_revision_engine.py` |
| Relationship Dynamics | `relationship_store.py` (log of deltas) |
| Event Responsiveness | `EventBus` + `IntentEventAdapter` |
| Causal Depth | `CausalEntry` в `psychological.py:55-98` |
| Loop Rate | `IntentEventAdapter` + окно в 20 тиков |
| Character Stability | `BreakProgressEngine.TraitDriftEvent` |
| WOW Density | новый агрегатор (см. раздел 15) |

### 14.3. Соответствие существующим метрикам DNA

| Новая метрика | Существующая в `dna_metrics.py` |
|---|---|
| Character Change Rate | частично: CVS (Causal Velocity Score) |
| Decision Diversity | частично: NPI (NPC Pipeline Integrity) |
| Loop Rate | частично: INV-NPC-FROZEN (health_checkers) |
| Character Stability | частично: BPI (Break Progress Index) |

Новые метрики **дополняют** DNA, не заменяют. Должны быть зарегистрированы в `diagnostics/dna_metrics.py` как новые поля `DNASnapshot`.

---

## 15. Главный показатель — WOW Density

Добавить экспериментальный показатель:

### 15.1. Определение

```text
WOW Density = количество значимых, заметных игроку изменений NPC
              за 30 минут симуляции
```

**Не считать** каждое изменение числового параметра.

**Считать только** изменения, которые потенциально видит игрок:

| Событие | Источник в коде |
|---|---|
| NPC изменил отношение | `relationship_store.apply_delta` с `|Δ| ≥ 5` |
| NPC изменил поведение (новый `intent`) | `IntentEventAdapter`, `intent ≠ previous` |
| NPC перестал доверять (`trust < -10`) | `relationship_store` |
| NPC начал доверять (`trust > +20`) | `relationship_store` |
| NPC сменил стратегию (drastic shift в `effective_drives`) | `drive_resolver.py` |
| NPC раскрыл секрет (`secret_id` появился в `EpistemicRecord`) | `epistemic_store.py` |
| NPC совершил ошибку (intent отличен от ожидаемого) | `evaluation.py` |
| NPC изменил убеждение (L2.5 `CrystallizedBelief` revision) | `belief_crystallization_engine.py` |
| NPC инициировал действие (proactive intent) | `DecisionHub.compute`, intent ∈ `{TALK, OFFER_JOB, ...}` |
| NPC начал конфликт (`intent = ATTACK/INSULT`) | `IntentEventAdapter` |
| NPC помирился (`intent = APOLOGY` после конфликта) | `IntentEventAdapter` |
| NPC изменил социальное поведение (front-type change) | `front.py` `FrontType` |

### 15.2. Цель

**не максимальное количество событий**.

Нужно найти плотность событий, при которой игрок чувствует, что **мир живой**.

Эмпирический ориентир:

```text
< 0.2 /min   →  МАНЕКЕН (игроку скучно)
0.4–1.2 /min →  ENIGMA zone (живая драма)
> 2.0 /min   →  ХАОС (игрок не успевает осознать)
```

### 15.3. Реализация

Новый модуль: `backend/app/services/calibration/wow_aggregator.py`.

```python
@dataclass(frozen=True)
class WOWEvent:
    tick: int
    real_time: float
    category: WOWCategory   # RELATIONSHIP/INTENT/BELIEF/SECRET/CONFLICT/...
    delta: float
    description: str
    causal_parent_id: Optional[str]

class WOWAggregator:
    def observe(self, event: WOWEvent) -> None: ...
    def density(self, window_minutes: float = 30.0) -> float: ...
    def events_in_window(self, window_minutes: float) -> List[WOWEvent]: ...
```

Подписывается на `EventBus`. ВНИМАНИЕ (S213): часть топиков таблицы 15.1 не существует в реестре `EventType` (`RelationshipDeltaEvent`, `BeliefCrystallizationEvent`, `SecretRevealedEvent`, `ProactiveIntentEvent`, `NPCErrorEvent`, события FrontType). Фактический реестр (реализован в ObservabilityTap): NPC_SPOKE, NPC_MOVED, NPC_PROXIMITY_CLOSE/LEAVE, NPC_INTERACTS_NPC, SOCIAL_ACTION, COMMUNICATION_CLAIM, OFFER_JOB, SPREAD_RUMOR, WARN, TRADE, THEFT, COMBAT, FATE_EVENT. Условные «пороговые» сигналы (|Δtrust| ≥ 5 и т.п.) в M2 берутся post-commit диффами RelationshipStore, а не подписками.

**M1/S220-подтверждение:** RelationshipStore-диффы уже собираются вExperimentRunner (`rel_captures` per-tick, плоский ключ `"source→target"`, saturation-headroom семантика) — для M2 WOWAggregator это готовый post-commit-источник; |Δtrust|=20 от HELP уже наблюдаем в данных.

---

## 16. Необходимо искать не максимум, а «золотую область»

Лаборатория должна **визуально разделять три зоны**.

### 16.1. Красная зона — МАНЕКЕН

NPC:
- почти не меняется (`character_change_rate < 0.1`);
- долго держит одно состояние (`loop_rate > 0.7`);
- редко реагирует (`event_responsiveness < 0.3`);
- решения предсказуемы (`decision_diversity < 0.2`);
- игрок не замечает причинной динамики (`wow_density < 0.2 /min`).

### 16.2. Красная зона — ХАОС

NPC:
- слишком быстро меняется (`character_change_rate > 0.95`);
- противоречит самому себе (`cognitive_dissonance > 5 /min`);
- забывает прошлые события (`decay_rate > 0.5` + `belief_revision_rate > 0.5`);
- слишком легко меняет мнение (`THETA_UP < 0.1`);
- реагирует на всё (`event_responsiveness = 1.0` всегда);
- превращается в случайный генератор (`SCORE_NOISE_RANGE > 0.25`).

### 16.3. Зелёная зона — ENIGMA

NPC:
- сохраняет характер (`character_stability > 0.5`);
- меняется под воздействием событий (`character_change_rate ∈ [0.3, 0.8]`);
- ошибается (`distortion_events > 0`, но `< loop_rate × 2`);
- учится (`belief_revision_rate > 0.05`);
- меняет отношения (`relationship_dynamics > 0.5 /min`);
- иногда удивляет (`proactive_intent_rate > 0.1`);
- создаёт цепочки последствий (`causal_depth > 2.0`);
- остаётся причинно объяснимым (`causal_coverage > 0.9`).

### 16.4. Классификатор зон

Новый модуль: `backend/app/services/calibration/zone_classifier.py`.

```python
class Zone(Enum):
    MANNEQUIN = "mannequin"
    CHAOS = "chaos"
    ENIGMA = "enigma"
    WARNING = "warning"   # близко к границе
    BROKEN = "broken"     # S213 (требуют тесты M2-AC-004/005 Плана):
                          # nan_count > 0 или invariant_violations > 0 → BROKEN,
                          # НЕ «хаос»: технический сбой ≠ драматическая нестабильность

def classify(metrics: CalibrationMetrics) -> Zone:
    # см. раздел 17.1 (полный алгоритм классификации)
```

---

## 17. Parameter Sweep должен искать именно эту область

Существующий sweep (`backend/tests/sandbox/calibration/run_sweep.py`) необходимо расширить.

Он не должен отвечать только:

> «Есть NaN?»

Он должен вычислять **профиль поведения**.

### 17.1. Пример вывода sweep

```text
================================================================
  SWEEP RESULT — Config #0042
================================================================
  identity_rigidity      = 0.42
  threat_sensitivity     = 0.67
  trust_sensitivity      = 0.81
  memory_decay            = 0.58
  emotional_reactivity   = 0.55
  belief_revision_rate   = 0.33
  ----------------------------------------------------------------
  Character Change       = 0.71   ✓ ENIGMA range
  Decision Diversity     = 0.76   ✓ ENIGMA range
  Belief Revision        = 0.63   ✓ ENIGMA range
  Causal Depth           = 0.82   ✓ ENIGMA range
  Loop Rate              = 0.08   ✓ (< 0.15)
  WOW Density            = 0.74   ✓ ENIGMA range
  Character Stability    = 0.68   ✓ ENIGMA range
  Contradiction Rate     = 0.04   ✓ (< 0.1)
  ----------------------------------------------------------------
  CLASSIFICATION: TRAGICOMEDIC / HIGHLY EXPRESSIVE
  ZONE:           ENIGMA  (confidence 0.87)
  SCORE:          0.79
================================================================
```

### 17.2. Алгоритм классификации зон

```python
def classify(metrics: CalibrationMetrics) -> tuple[Zone, float]:
    # 1. МАНЕКЕН: низкая динамика
    if (metrics.character_change_rate < 0.15
        and metrics.wow_density < 0.2
        and metrics.loop_rate > 0.5):
        return Zone.MANNEQUIN, confidence

    # 2. ХАОС: нестабильность
    if (metrics.character_change_rate > 0.90
        or metrics.contradiction_rate > 0.20
        or metrics.loop_rate < 0.02
        or metrics.causal_coverage < 0.5):
        return Zone.CHAOS, confidence

    # 3. ENIGMA: баланс
    if (0.30 <= metrics.character_change_rate <= 0.80
        and 0.4 <= metrics.wow_density <= 1.2
        and metrics.loop_rate <= 0.15
        and metrics.character_stability >= 0.5
        and metrics.causal_coverage >= 0.9):
        return Zone.ENIGMA, confidence

    return Zone.WARNING, confidence
```

### 17.3. Целевая функция sweep

```text
Score = w1 × CharacterChange
      + w2 × DecisionDiversity
      + w3 × BeliefRevision
      + w4 × CausalDepth
      + w5 × EventResponsiveness
      + w6 × WOWDensity
      + w7 × CharacterStability
      - w8 × LoopRate
      - w9 × ContradictionRate
      - w10 × ChaosPenalty
```

Веса по умолчанию (конфигурируются в `configs/calibration/scoring.yaml`):

```yaml
weights:
  character_change:      1.0
  decision_diversity:    0.8
  belief_revision:       0.8
  causal_depth:          1.2
  event_responsiveness:  0.6
  wow_density:           1.5
  character_stability:  1.0
  loop_rate:             -1.0
  contradiction_rate:    -1.5
  chaos_penalty:         -2.0
```

---

## 18. Нужен A/B режим

Очень важно иметь:

### 18.1. Конфигурация A и Конфигурация B

Обе запускаются на абсолютно **одинаковой последовательности событий**.

Например:

```text
T=0   NPC создан
T=3   игрок помогает
T=7   игрок лжёт
T=10  игрок рассказывает слух
T=15  NPC получает угрозу
T=20  игрок просит помощи
T=25  происходит конфликт
T=30  игрок раскрывает правду
T=40  финальное состояние
```

### 18.2. Что показывает UI

После запуска лаборатория показывает:

```text
                    Конфиг A       Конфиг B
Trust(player):      72 → 51 → 34 → 61    72 → 68 → 64 → 60
WOW events:         7                    2
Character Change:   0.71                 0.18
Decision Diversity: 0.76                 0.31
Loop Rate:          0.08                 0.42
Zone:               ENIGMA               MANNEQUIN

ВЕРДИКТ:
  Конфигурация A создаёт в 3.4 раза больше значимых изменений поведения.
  Рекомендуется сохранить как enigma_mvp_v2.yaml.
```

### 18.3. Параллельный запуск

Реализация — через `ExperimentRunner.run_parallel(configs=[A, B], scenario=scenario, seed=seed)`.

**M1-актуализация (S220–S222):** параллельность в одном процессе ЗАПРЕЩЕНА (ADR-O-361: overlay-вложенность и глобальный identity-патч констант). A/B = последовательные `run()` на общем `scenario_path` (контракт S221 даёт идентичный вход обоим прогонам — «абсолютно одинаковая последовательность событий» п.18.1 выполняется по построению). `run_parallel` из старого плана не реализовывать как threads; если нужен сервисный API — последовательная очередь.

Каждый запуск должен использовать **независимый** экземпляр `LifeEngine` и `SqlitePersistenceAdapter` (путь к БД: `:memory:` или временный файл).

---

## 19. Должен существовать режим «Заморозить всё кроме одного параметра»

Например:

> Изменяем только скорость забывания.

Все остальные параметры фиксированы.

Запустить 30-минутный сценарий.

Сравнить:

```text
Memory Decay = 0.1     →  WOW Density = 0.42, Loop Rate = 0.05
Memory Decay = 0.3     →  WOW Density = 0.71, Loop Rate = 0.08   ← ENIGMA
Memory Decay = 0.5     →  WOW Density = 0.68, Loop Rate = 0.12
Memory Decay = 0.9     →  WOW Density = 0.31, Loop Rate = 0.38   → ХАОС
```

Это позволит понять реальное влияние каждого параметра.

### 19.1. Реализация

Новый режим: `ONE_PARAM_SCAN`.

UI: выбор одного параметра → выбор N значений → запуск N параллельных сессий → вывод графика зависимости метрик от параметра.

---

## 20. Нужен режим автоматического поиска

После ручной настройки:

> «Найти интересные конфигурации»

Система автоматически генерирует множество комбинаций.

Но оптимизировать нужно **не один показатель**.

Целевая функция — из раздела 17.3.

### 20.1. Коэффициенты должны быть конфигурируемыми

Это позволит искать не «математически правильного NPC», а NPC с нужной игровой динамикой.

### 20.2. Алгоритмы поиска

| Алгоритм | Когда применять | Реализация |
|---|---|---|
| Grid Search | Параметров ≤ 3, диапазон узкий | `itertools.product` |
| Random Search | Параметров 4–8, нужно быстро оценить | `numpy.random` |
| Bayesian Optimization | Параметров 4–10, нужно найти оптимум | `scikit-optimize` |
| CMA-ES | Параметров > 8, сложный ландшафт | `cma` library |
| Genetic Algorithm | Нужно найти несколько альтернативных зон | `DEAP` library |

Все запуски **детерминированы** через `KernelRNG` (см. `kernel_rng.py`, ADR-O-301).

### 20.3. Фильтрация результатов

После sweep лаборатория показывает топ-N конфигураций, отсортированных по `Score`:

```text
TOP 5 КОНФИГУРАЦИЙ
────────────────────────────────────────────────
#1  Score=0.79  Zone=ENIGMA   [rigidity=0.42, threat=0.67, ...]
#2  Score=0.77  Zone=ENIGMA   [rigidity=0.45, threat=0.65, ...]
#3  Score=0.74  Zone=ENIGMA   [rigidity=0.40, threat=0.70, ...]
#4  Score=0.71  Zone=WARNING  [rigidity=0.35, threat=0.75, ...]
#5  Score=0.68  Zone=WARNING  [rigidity=0.50, threat=0.60, ...]
```

---

## 21. Очень важный принцип: не оптимизировать WOW Density напрямую

Если просто максимизировать `WOW Density`, система найдёт плохое решение:

> NPC будет менять настроение каждую секунду.

Поэтому нужны **ограничения**.

Например:

```text
WOW Density         ↑
Character Stability ↑
Causal Depth        ↑
Loop Rate           ↓
Contradiction       ↓
Randomness          ↓
```

Нам нужна **не максимальная динамика**.

Нам нужна:

> **динамика при сохранении идентичности**.

### 21.1. Жёсткие ограничения (hard constraints)

Конфигурация **отвергается** (даже при высоком Score), если:

```yaml
hard_constraints:
  - loop_rate >= 0.30         # zацикливание
  - contradiction_rate >= 0.20  # противоречия
  - causal_coverage <= 0.5     # потеря причинности
  - character_stability <= 0.2  # потеря идентичности
  - nan_count > 0              # технический сбой
  - invariant_violations > 0   # нарушение инвариантов SUPERBOX
```

### 21.2. Мягкие предпочтения (soft preferences)

Веса в `Score` (см. раздел 17.3).

---

## 22. Нужна визуальная карта поведения

После sweep строить карту.

### 22.1. Пример карты

```text
X = Identity Rigidity (identity_rigidity, 0.0 → 1.0)
Y = Emotional Reactivity (AFFECT_DECAY_BASE_RATE инверсный, 0.0 → 1.0)
Цвет = WOW Density

                ХАОС
                  ███████████
                ██████████████
              ████████████████
            ████ ЗОЛОТАЯ ████
          ████   ОБЛАСТЬ   ████
        ████                 ████
      ████      ENIGMA         ████
    ███                          ███
  ███      МАНЕКЕН                 ███
███                                ████
```

### 22.2. Реализация

- Библиотека: `matplotlib` (или `plotly` для интерактивности);
- Цветовая карта: `viridis` для метрики, `RdYlGn` для зон;
- Сохранение: PNG + HTML (интерактивный).

### 22.3. Поддерживаемые карты

| Название | X | Y | Цвет |
|---|---|---|---|
| `rigidity_vs_reactivity` | `identity_rigidity` | `1 - AFFECT_DECAY_BASE_RATE` | `wow_density` |
| `memory_vs_belief` | `decay_rate` | `THETA_UP` | `character_change_rate` |
| `trust_vs_threat` | `DISTRUST_STRESS_BOOST` | `THREAT_AMPLIFICATION_FACTOR` | `relationship_dynamics` |
| `fear_vs_inertia` | `FEAR_FLEE_THRESHOLD` | `INTENT_INERTIA_WEIGHT` | `loop_rate` |
| `breakpoint_vs_pressure` | `breakpoint` | `pressure_resistance` | `character_stability` |

Каждая карта должна сохраняться в `download/sweeps/maps/<name>_<timestamp>.png`.

---

## 23. Нужен пресет «ENIGMA MVP»

После калибровки параметры должны сохраняться в отдельный файл.

### 23.1. Формат пресета

Путь:

```text
configs/npc/enigma_mvp_v1.yaml
configs/npc/enigma_mvp_v2.yaml
```

Шаблон:

```yaml
# ENIGMA MVP Calibration Preset
# Сгенерировано: 2026-08-19 14:32:11
# Лабораторией калибровки психики ENIGMA v0.5.3.8.x

meta:
  preset_id: enigma_mvp_v2
  preset_version: "2.0"
  enigma_version: "0.5.3.8.3"
  calibration_date: "2026-08-19T14:32:11+07:00"
  calibrated_by: "calibration_lab"
  scenario: "tavern_silver_wolf"
  scenario_duration_minutes: 45
  seed: 7331
  experiment_id: "exp_20260819_143211_a8f3"

parameters:
  # Личность
  # СХЕМА ФАКТИЧЕСКАЯ (S213; реализовано: config/calibration/test_presets/*.yaml):
  #   meta: {preset_id, description}
  #   constants:     — глобальные константы core/constants.py; применяет
  #                   overlay_constants (identity-патч + verify вход/выход);
  #                   [PLAN]-параметры и значения, нарушающие taboo чужих ADR
  #                   (напр. ADR-O-360: DIRECT_OBSERVATION_RELIABILITY >= 1.0),
  #                   отклоняются громко на загрузке
  #   npc_overrides: — per-NPC параметры (psyche/drives; НЕ константы):
  #                   ключ "*" = все NPC кампании; точечный npc_id
  #                   перекрывает wildcard; drives заменяются целиком (sum=1.0)
  #   seed / scenario / duration_ticks — в ExperimentConfig, не в пресете
  #
  # identity_rigidity — per-NPC поле (psyche), не константа: в пресете живёт
  # в npc_overrides."*".psyche.identity_rigidity (калибруем с W-IR/S213):
  identity_rigidity:           0.42   # → npc_overrides."*".psyche
  trait_decay_rate:            0.018
  intent_inertia_weight:       0.20
  theta_up:                    0.55
  theta_down:                  0.20

  # Восприятие
  threat_amplification_factor: 0.18
  distrust_stress_boost:       9.0

  # Эмоции
  affect_decay_base_rate:      0.06
  reactive_urgency_threshold:  0.78

  # Память
  event_memory_decay_rate:     0.045

  # Решения
  fear_flee_threshold:         0.62
  score_noise_range:           0.08
  switching_cost_base:        0.06

  # ... (полный список — см. Приложение A)

metrics_achieved:
  character_change_rate:       0.71
  decision_diversity:          0.76
  belief_revision_rate:        0.63
  causal_depth:                0.82
  loop_rate:                   0.08
  wow_density:                 0.74
  character_stability:        0.68
  zone:                        ENIGMA
  score:                       0.79

formulas_version:
  decision_hub:                "ADR-DH-007"
  belief_crystallization:      "ADR-O-305"
  affect_pipeline:             "ADR-117"
  break_progress:              "ADR-O-208"

validation:
  superbox_scenarios_passed:
    - epistemic_divergence
    - epistemic_decision_divergence
    - epistemic_persistence
    - modifier_composition
    - modifier_commutativity
  invariant_violations: 0
  nan_count: 0
  replay_deterministic: true
```

### 23.2. Цель пресета

Чтобы спустя месяц можно было воспроизвести:

> «Вот тот самый NPC, который давал правильный эффект».

---

## 24. Все эксперименты должны быть воспроизводимыми

Каждый эксперимент обязан иметь:

```yaml
experiment:
  experiment_id: "exp_20260819_143211_a8f3"
  seed: 7331
  enigma_version: "0.5.3.8.3"
  parameter_configuration: "configs/npc/enigma_mvp_v2.yaml"
  scenario: "tavern_silver_wolf"
  tick_count: 300
  event_sequence:
    - { tick: 0,   event: "NPC_SPAWN",     target: "maid_lusya" }
    - { tick: 18,  event: "PLAYER_HELP",   target: "maid_lusya" }
    - { tick: 42,  event: "PLAYER_LIE",    target: "maid_lusya" }
    # ...
  final_state:
    trust_player: 41
    stress: 28.4
    wow_events: 23
    # ...
  metrics:
    character_change_rate: 0.71
    wow_density: 0.74
    # ...
```

### 24.1. Детерминизм

Если два запуска используют одинаковые:

```text
seed + parameters + scenario + version
```

результат должен быть **идентичным** (битово-точно, за исключением временных меток).

Это уже обеспечивается `KernelRNG` (ADR-O-301), но лаборатория должна:
- explicitly логировать seed;
- explicitly проверять детерминизм (replay test для каждого эксперимента).

### 24.2. Replay-проверка

После каждого эксперимента автоматически запускается `replay_test(seed, params, scenario)`:

```python
def replay_test(seed, params, scenario) -> ReplayResult:
    run_1 = run_experiment(seed, params, scenario)
    run_2 = run_experiment(seed, params, scenario)  # тот же seed!
    diff = state_diff(run_1, run_2)
    return ReplayResult(
        deterministic=(diff == 0),
        diff_count=diff.field_count,
        max_diff=diff.max_delta,
    )
```

Если `deterministic == False` — эксперимент помечается `BROKEN`.

---

## 25. Нужен экспорт

После эксперимента:

| Формат | Содержимое | Назначение |
|---|---|---|
| **JSON** | полное состояние NPC + metrics + experiment_id | machine-readable, для CI |
| **CSV** | числовые данные метрик по тикам | анализ в Excel/Pandas |
| **HTML** | интерактивные графики (Plotly) | просмотр без установки |
| **PNG** | ключевые графики (matplotlib) | для отчётов и презентаций |
| **YAML** | выбранный набор параметров (пресет) | для подключения к ENIGMA |

### 25.1. Структура экспорта

```text
download/experiments/exp_20260819_143211_a8f3/
├── experiment.json         # полный дамп
├── metrics.csv             # числовые ряды по тикам
├── wow_events.csv          # список WOW-событий
├── causal_chains.json      # деревья причинных цепочек
├── graphs/
│   ├── trust_over_time.png
│   ├── belief_confidence.png
│   ├── stress_dynamics.png
│   ├── intent_distribution.png
│   ├── wow_density_heatmap.png
│   └── zone_map.png
├── interactive_report.html # Plotly-дашборд
└── preset.yaml             # параметры → configs/npc/
```

### 25.2. Имена файлов

Все имена файлов должны включать `experiment_id` для однозначной идентификации.

---

## 26. Что НЕ нужно делать

Не превращать этот инструмент в ещё один огромный фреймворк.

- **Не** писать отдельную симуляцию NPC.
- **Не** дублировать `LifeEngine`.
- **Не** создавать альтернативную психологическую модель.
- **Не** вводить новые классы состояний (L0/L1/L1.5/L2.5/L3 уже определены).
- **Не** вводить новые DecisionHub.

Лаборатория должна запускать **настоящий production pipeline ENIGMA**.

Иначе мы будем калибровать игрушечную модель, а не ENIGMA.

### 26.1. Критически важно

```text
Calibration Laboratory
        ↓
реальные сервисы ENIGMA (TickOrchestrator, DecisionHub, LifeEngine)
        ↓
реальный DecisionHub.compute()
        ↓
реальная память (LayeredMemory, CrystallizedBeliefStore)
        ↓
реальная эпистемика (epistemic_store, BeliefTransitionEngine)
        ↓
реальный World State (WorldSnapshot, TruthState)
```

### 26.2. Антипаттерны (запрещено)

- Создание `MockNPCState` или `FakeDecisionHub`;
- Подмена `InterventionEvent` на кастомный класс;
- Прямая запись в `NPCState` без `StateApplicator`;
- Использование `random` вместо `KernelRNG`;
- Сохранение стейта в JSON (только SQLite для runtime).

---

## 27. Архитектурное требование

Разделить систему на четыре слоя:

```text
┌──────────────────────────────────────────────────┐
│  CALIBRATION UI                                  │
│  sliders / graphs / events / timeline            │
│  (Next.js + TypeScript, отдельное веб-приложение)│
└──────────────────┬───────────────────────────────┘
                   ↓  HTTP / SSE
┌──────────────────────────────────────────────────┐
│  EXPERIMENT RUNNER                              │
│  scenario / seed / replay / parallel runs       │
│  (Python, new module: backend/app/services/     │
│   calibration/)                                 │
└──────────────────┬───────────────────────────────┘
                   ↓  direct Python imports
┌──────────────────────────────────────────────────┐
│  ENIGMA ENGINE                                  │
│  TickOrchestrator + DecisionHub + LifeEngine    │
│  + Memory + Epistemic + WorldState               │
│  (existing code, NO modifications to contracts)  │
└──────────────────┬───────────────────────────────┘
                   ↓  EventBus + L1Chronicle + DNA
┌──────────────────────────────────────────────────┐
│  OBSERVABILITY                                  │
│  metrics / causal trace / WOW aggregator        │
│  + Zone Classifier                              │
│  (extends diagnostics/dna_metrics.py)           │
└──────────────────────────────────────────────────┘
```

### 27.1. Слой 1: Calibration UI

- **Стек:** Next.js 16 + TypeScript + Tailwind CSS 4 + shadcn/ui;
- **Бэкенд-коннектор:** REST + SSE к `/api/calibration/*`;
- **Хост:** отдельный порт (например, `:3001`), не конфликтующий с FastAPI (`:8000`) и pygame-фронтендом;
- **Запуск:** `cd calibration_ui && pnpm dev`.

### 27.2. Слой 2: Experiment Runner

- **Стек:** Python 3.11+;
- **Расположение:** `backend/app/services/calibration/`;
- **Зависимости:** `TickOrchestrator`, `LifeEngine`, `MemoryManager` (через `game_loop_builder.py`);
- **API:** новые маршруты в `backend/app/api/calibration_routes.py`.

### 27.3. Слой 3: ENIGMA Engine

- **Существующий код.** Модификации **только** в виде новых параметров-чтения из конфигурации.
- **Запрещено** менять контракты `DecisionHub.compute()` или `TickOrchestrator.execute()`.

### 27.4. Слой 4: Observability

- **Расширение существующего** `diagnostics/dna_metrics.py`;
- **Новые агрегаторы:** в `backend/app/services/calibration/` (WOW, Zone, CausalDepth);
- **Подписка на EventBus** — пассивный слушатель, **не** мутирующий состояние.

---

## 28. Минимальный MVP лаборатории

**Не пытаться сразу реализовать всё.**

### 28.1. Первая версия (M1) должна уметь

> Актуализация S213: предпосылка-ноль — **ScenarioPlayer** (раздел 11). По открытию M0 (раздел 0.3) зонные критерии §30 валидны ТОЛЬКО на scripted-сценарии: idle-среда классифицирует любой пресет как МАНЕКЕН. Пункты ниже дополняются состоянием M0: runner/пресеты/overlay/Tap/5 метрик/детерминизм ядра уже существуют и покрыты тестами (52 шт.).

- [ ] русский интерфейс;
- [ ] минимум 10–15 реальных параметров (из Приложения A);
- [ ] слайдеры;
- [ ] запуск настоящего NPC (через `TickOrchestrator.execute`);
- [ ] 30-минутный сценарий (`tavern_silver_wolf`);
- [ ] пауза;
- [ ] пошаговый тик;
- [ ] ускорение (×1, ×5, ×20, ×100);
- [ ] события игрока (минимум 6 кнопок);
- [ ] timeline (минимум 5 типов событий);
- [ ] изменение trust (отображение в реальном времени);
- [ ] изменение beliefs (L2.5 crystallized);
- [ ] изменение решений (intent);
- [ ] графики (минимум 3: trust, stress, WOW density);
- [ ] A/B сравнение;
- [ ] сохранение конфигурации (YAML);
- [ ] seed (с детерминизмом);
- [ ] экспорт CSV/JSON.

### 28.2. Что **не** входит в M1

- Sweep с автопоиском (это M3);
- Визуальные карты поведения (это M4);
- Auto-search с CMA-ES/Bayesian (это M4);
- Полный набор из 50+ параметров (это M2).

После этого расширять.

---

## 29. Главный тестовый сценарий

Создать стандартный сценарий:

> **«Таверна — 45 минут»**

### 29.1. NPC в сценарии

Уже существует в `config/npc/individuals/`:

| NPC | Архетип | Голос | Секрет |
|---|---|---|---|
| `Люся` (maid_lusya) | maid | `nervous_submissive` | spy_for_thieves_guild |
| `Борко` (guard_borko) | guard | `gruff_veteran` | corruption |
| `Горан` (merchant_goran) | merchant | `cold_professional` | debt_to_guild |
| `Торнин` (tavern_keeper_tornin) | tavern_keeper | `lazy_cynic` | knows_about_basement |
| `Шэдоу` (thief_shadow) | thief | `silent_stoic` | guild_membership |
| `Орм` (blacksmith_orm) | blacksmith | `smiling_hypocrite` | affair_with_maid |

### 29.2. Структура сценария

Игрок входит в таверну.

Каждый NPC получает:
- исходную личность (`config/npc/individuals/*.json`);
- отношения (`config/npc/social/village_relations.json`);
- секрет (`config/canon/truth_state_tavern.json`);
- потребности (`drives_base`);
- несколько убеждений (`origin_events`);
- несколько потенциальных конфликтов (`truth_state.RelationType`).

Затем игрок получает свободу действий.

### 29.3. Формат сценария для лаборатории

Новый файл: `config/scenarios/tavern_silver_wolf_45min.yaml`.

```yaml
scenario:
  id: tavern_silver_wolf_45min
  name: "Таверна «Серебряный Волк» — 45 минут"
  duration_minutes: 45
  ticks_per_minute: 10
  seed_default: 7331

  npcs:
    - id: maid_lusya
    - id: guard_borko
    - id: merchant_goran
    - id: tavern_keeper_tornin
    - id: thief_shadow
    - id: blacksmith_orm

  truth_state: config/canon/truth_state_tavern.json

  scripted_events:
    - { tick: 0,   event: "PLAYER_ENTERS_TAVERN" }
    - { tick: 30,  event: "PLAYER_FREE_TIME_START" }
    # ... далее игрок сам создаёт события
```

Лаборатория должна позволять воспроизводить **одну и ту же последовательность действий** для разных конфигураций психики.

> Статус S213: каталог `config/scenarios/` не существует — сценарий-файл создаётся в M1 вместе со ScenarioPlayer. Контракт вмешательств готов и проверен: `InterventionEvent.from_player_action(action_text, player_name, tick, **kwargs)` → `TickOrchestrator.execute(interventions=[...])` (app/contracts/interventions.py). Ссылки сценария на NPC (`config/npc/individuals/*.json` — 6 шт., включая Люсю) и canon (`config/canon/truth_state_tavern.json`) — верифицированы, существуют.

### 29.4. Запись сценария

UI должен поддерживать:
- **Запись** сценария (запоминает все события игрока);
- **Воспроизведение** сценария (повторяет события с теми же tick-метками);
- **Экспорт** сценария в YAML для обмена между разработчиками.

---

## 30. Финальный критерий успеха

Лаборатория считается успешно реализованной **не тогда**, когда:

> «графики красивые».

И **не тогда**, когда:

> «sweep протестировал 10 000 комбинаций».

### 30.1. Она успешна, когда разработчик может сделать следующее

1. Открыть лабораторию.
2. Выбрать NPC.
3. Увидеть все его параметры на русском.
4. Запустить 45-минутную симуляцию.
5. Вмешиваться событиями игрока.
6. Видеть причинную цепочку поведения.
7. Изменить один параметр.
8. Перезапустить тот же сценарий.
9. Сравнить результат.
10. Найти конфигурацию, при которой NPC становится значительно более выразительным.
11. Сохранить эту конфигурацию как версию ENIGMA.

### 30.2. Количественный критерий

- **3+** конфигурации, классифицированные как `ENIGMA zone`;
- **0** нарушений инвариантов SUPERBOX;
- **0** случаев `NaN`;
- **100 %** детерминизм (replay test проходит);
  — Уточнение S213: 100% детерминизм подтверждён для ЯДРА симуляции (statuses/nan/final_npc_state/npc_captures — покадрово, тесты AC-004); rel/l1-слой асинхронен (материализация диалогов завершается в wall-clock-зависимые моменты) — до quiesce-границы (DEBT-QUIESCE, M1) он наблюдается отдельным полем `rel_captures_deterministic`, не входя в вердикт;
- **WOW Density** в диапазоне `0.4–1.2 /min` для всех `ENIGMA` конфигураций.

---

## 31. Философия калибровки

Главный вопрос лаборатории:

> «Как сделать так, чтобы за короткую игровую сессию игрок увидел историю изменения человека?»

**Не:**

> «Как сделать NPC максимально реалистичным?»

Реализм человеческой психики сам по себе **не** является игровой ценностью.

Для ENIGMA важнее:

```text
причина → изменение → действие → последствие → новое состояние → новая причина
```

Именно этот цикл должен быть **быстрым, заметным и достаточно устойчивым**, чтобы игрок мог его распознать.

NPC не должен быть идеальным человеком.

Он должен быть **системой, которая способна стать персонажем на глазах игрока**.

---

## 32. Итоговая формула цели

Искомая область параметров:

```text
              высокая выразительность
                       ↑
                       │
             ┌─────────┴─────────┐
             │                   │
             │   ENIGMA ZONE     │
             │                   │
             │  причинность      │
             │       +           │
             │  изменчивость     │
             │       +           │
             │  ошибки           │
             │       +           │
             │  память           │
             │       +           │
             │  последствия      │
             │                   │
             └───────────────────┘
                       │
                       ↓
                 идентичность
```

Нам нужна **не точка**, а **устойчивый диапазон** параметров, внутри которого большинство NPC дают интересную динамику.

Именно этот диапазон впоследствии станет психологическим **tuning profile** ENIGMA MVP.

### 32.1. Главный результат лаборатории

> Найти математическую область, в которой NPC перестают быть просто агентами симуляции и начинают производить для игрока драматические события.

### 32.2. Финальный артефакт лаборатории

```text
configs/npc/enigma_mvp_v1.yaml
├── parameters:        (полный набор откалиброванных значений)
├── metrics_achieved:  (целевые метрики)
├── formulas_version:  (версии ADR, чтобы знать, на какой ENIGMA калибровали)
├── validation:        (список пройденных SUPERBOX-сценариев)
└── meta:              (seed, дата, ID эксперимента, версия ENIGMA)
```

Этот файл подключается в `config/user_settings.yaml` и становится **психологическим tuning profile** для всех NPC в MVP-игре.

---

# Приложение A. Карта реальных параметров ENIGMA → UI слайдеры

> Полный список параметров, которые должны быть представлены в UI лаборатории.
> Параметры помечены `[PLAN]`, если они спроектированы, но **не подключены** к `DecisionHub.compute()`.

## A.1. Параметры личности (L0 — `NPCPersonality`)

| UI (RU) | Внутреннее имя | Источник | Диапазон | Default | wired |
|---|---|---|---|---|---|
| Жёсткость личности | `identity_rigidity` | `models/npc_state.py:376` | `0.0–1.0` | `0.5` | ✓ |
| Сила воли | `willpower` | `models/npc_state.py:351` | `0–100` | `50` | ✓ |
| Порог слома | `breakpoint` | `models/npc_state.py:352` | `0–100` | `65` | ✓ |
| Базовая лояльность | `loyalty_base` | `models/npc_state.py:353` | `0–100` | `30` | ✓ |
| Общительность | `gregariousness` | `models/npc_state.py:378` | `0.0–1.0` | `0.5` | ✓ |
| Сила идентичности | `identity_attachment` | `models/npc_profile.py:90` | `0.0–1.0` | `1.0` | [PLAN] |
| Лингвистическая целостность | `linguistic_integrity` | `models/npc_profile.py:50` | `0.0–1.0` | `1.0` | [PLAN] |
| Базовая ориентация | `core_orientation` | `models/npc_profile.py:88` | enum | `survival` | [PLAN] |

## A.2. Параметры восприятия (`PerceptualKernel`)

| UI (RU) | Внутреннее имя | Источник | Диапазон | Default | wired |
|---|---|---|---|---|---|
| Чувствительность к угрозе | `threat_gradient` | `models/npc_state.py:538` | `0.0–1.0` | `0.0` | ✓ |
| Градиент доверия | `trust_gradient` | `models/npc_state.py:539` | `-1.0…+1.0` | `0.0` | ✓ |
| Неопределённость | `uncertainty` | `models/npc_state.py:540` | `0.0–1.0` | `0.0` | ✓ |
| Оценка аномалии | `anomaly_score` | `models/npc_state.py:541` | `0.0–1.0` | `0.0` | ✓ |
| Подавление агрессии | `aggression_inhibition` | `models/npc_state.py:542` | `0.0–1.0` | `0.0` | ✓ |
| Подавление инициативы | `initiative_suppression` | `models/npc_state.py:543` | `0.0–1.0` | `0.0` | ✓ |
| Склонность к подчинению | `compliance_bias` | `models/npc_state.py:544` | `0.0–1.0` | `0.0` | ✓ |
| Телесная срочность | `somatic_urgency` | `models/npc_state.py:545` | `0.0–1.0` | `0.0` | ✓ |

## A.3. Параметры эмоциональной динамики (`NPCState`)

| UI (RU) | Внутреннее имя | Источник | Диапазон | Default | wired |
|---|---|---|---|---|---|
| Стресс | `stress` | `models/npc_state.py:575` | `0–100` | `0.0` | ✓ |
| Аффективная нагрузка | `affective_load` | `models/npc_state.py:579` | `0.0–1.5` | `0.0` | ✓ |
| Аффективная память | `affective_memory` | `models/npc_state.py:581` | `0.0–1.0` | `0.0` | ✓ |
| Социальный вход (EMA) | `social_input_ema` | `models/npc_state.py:584` | `0.0–1.0` | `0.0` | ✓ |
| Обида | `resentment` | `models/npc_state.py:588` | `0–100` | `0.0` | ✓ |
| Зависимость | `dependency` | `models/npc_state.py:592` | `0–100` | `0.0` | ✓ |
| Целостность идентичности | `identity_integrity` | `models/npc_state.py:596` | `0.0–1.0` | `1.0` | ✓ |
| Сопротивление давлению | `pressure_resistance` | `models/npc_state.py:599` | `0–100` | `0.0` | ✓ |
| Дельта эмоции | `emotion_delta` | `models/npc_state.py:691` | `-100…+100` | `0.0` | ✓ |

## A.4. Параметры решений (`constants.py:DECISION_HUB`)

| UI (RU) | Внутреннее имя | Источник | Диапазон | Default | wired |
|---|---|---|---|---|---|
| Шум скоринга | `SCORE_NOISE_RANGE` | `core/constants.py:73` | `0.0–0.5` | `0.10` | ✓ |
| Инерция намерения | `INTENT_INERTIA_WEIGHT` | `core/constants.py:74` | `0.0–1.0` | `0.20` | ✓ |
| Макс. тиков инерции | `INTENT_INERTIA_MAX_TICKS` | `core/constants.py:73` | `0–30` | `10` | ✓ |
| Насыщение намерения | `INTENT_SATURATION_TICKS` | `core/constants.py:75` | `0–20` | `6` | ✓ |
| Затухание намерения | `INTENT_DECAY_RATE` | `core/constants.py:75` | `0.0–0.2` | `0.03` | ✓ |
| Гистерезис вверх | `THETA_UP` | `core/constants.py:76` | `0.0–1.0` | `0.60` | ✓ |
| Гистерезис вниз | `THETA_DOWN` | `core/constants.py:77` | `0.0–1.0` | `0.20` | ✓ |
| Скорость активации трейта | `TRAIT_ACTIVATION_RATE` | `core/constants.py:79` | `0.0–1.0` | `0.15` | ✓ |
| Затухание трейта | `TRAIT_ACTIVATION_DECAY` | `core/constants.py:80` | `0.0–0.2` | `0.03` | ✓ |
| Истощение намерения | `INTENT_EXHAUSTION_RATE` | `core/constants.py:82` | `0.0–0.2` | `0.08` | ✓ |
| Порог бегства от страха | `FEAR_FLEE_THRESHOLD` | `core/constants.py:84` | `0.0–1.0` | `0.65` | ✓ |
| Мин. скоринг | `MIN_INTENT_SCORE` | `core/constants.py:86` | `0.0–0.5` | `0.15` | ✓ |
| Порог провокации | `PROVOCATION_THREAT_THRESHOLD` | `core/constants.py:87` | `0.0–1.0` | `0.30` | ✓ |
| База commitment | `COMMITMENT_BASE_THRESHOLD` | `core/constants.py:88` | `0.0–1.0` | `0.15` | ✓ |
| K commitment | `COMMITMENT_K` | `core/constants.py:88` | `0.0–5.0` | `2.5` | ✓ |
| База стоимости переключения | `SWITCHING_COST_BASE` | `core/constants.py:89` | `0.0–0.5` | `0.05` | ✓ |
| Порог реактивной срочности | `REACTIVE_URGENCY_THRESHOLD` | `core/constants.py:99` | `0.5–1.0` | `0.80` | ✓ |

## A.5. Параметры искажения (`constants.py:DISTORTION`)

| UI (RU) | Внутреннее имя | Источник | Диапазон | Default | wired |
|---|---|---|---|---|---|
| Фактор усиления угрозы | `THREAT_AMPLIFICATION_FACTOR` | `core/constants.py:55` | `0.0–1.0` | `0.15` | ✓ |
| Фактор предвзятости обиды | `RESENTMENT_BIAS_FACTOR` | `core/constants.py:56` | `0.0–1.0` | `0.20` | ✓ |
| Stress-буст от недоверия | `DISTRUST_STRESS_BOOST` | `core/constants.py:58` | `0.0–30.0` | `8.0` | ✓ |
| Порог недоверия | `DISTRUST_STRESS_THRESHOLD` | `core/constants.py:59` | `-100…0` | `-30.0` | ✓ |
| Макс. стресс от искажения | `MAX_DISTORTION_STRESS` | `core/constants.py:62` | `0–100` | `30.0` | ✓ |

## A.6. ПараметрыBREAK_SYSTEM (`constants.py:BREAK_SYSTEM`)

| UI (RU) | Внутреннее имя | Источник | Диапазон | Default | wired |
|---|---|---|---|---|---|
| Стадия: Сопротивление | `BREAK_STAGE_RESISTANCE` | `core/constants.py:368` | `0.0–1.0` | `1.0` | ✓ |
| Стадия: Трещины | `BREAK_STAGE_CRACKS` | `core/constants.py:369` | `0.0–1.0` | `0.8` | ✓ |
| Стадия: Рационализация | `BREAK_STAGE_RATIONALIZATION` | `core/constants.py:370` | `0.0–1.0` | `0.6` | ✓ |
| Стадия: Адаптация | `BREAK_STAGE_ADAPTATION` | `core/constants.py:371` | `0.0–1.0` | `0.4` | ✓ |
| Стадия: Деформация | `BREAK_STAGE_DEFORMATION` | `core/constants.py:372` | `0.0–1.0` | `0.2` | ✓ |
| Порог восстановления | `BREAK_RECOVERY_PRESSURE_THRESHOLD` | `core/constants.py:381` | `0–100` | `10.0` | ✓ |
| База восстановления | `BREAK_RECOVERY_BASE_RATE` | `core/constants.py:382` | `0.0–0.01` | `0.001` | ✓ |

## A.7. Параметры памяти (`EventMemory`)

| UI (RU) | Внутреннее имя | Источник | Диапазон | Default | wired |
|---|---|---|---|---|---|
| Скорость забывания | `decay_rate` | `models/npc_state.py:221` | `0.0–1.0` | `0.05` | ✓ |
| Важность события | `importance` | `models/npc_state.py:218` | `0.0–1.0` | `0.5` | ✓ |
| Уверенность в воспоминании | `confidence` | `models/npc_state.py:219` | `0.0–1.0` | `1.0` | ✓ |
| Доступность | `accessibility` | `models/npc_state.py:220` | `0.0–1.0` | `1.0` | ✓ |
| Порог FRESH | `STAGE_FRESH` | `models/npc_state.py:322` | `0.0–1.0` | `0.80` | ✓ |
| Порог DETAILED | `STAGE_DETAILED` | `models/npc_state.py:323` | `0.0–1.0` | `0.55` | ✓ |
| Порог COMPRESSED | `STAGE_COMPRESSED` | `models/npc_state.py:324` | `0.0–1.0` | `0.30` | ✓ |
| Порог ABSTRACT | `STAGE_ABSTRACT` | `models/npc_state.py:325` | `0.0–1.0` | `0.10` | ✓ |

## A.8. Параметры отношений (`constants.py:SOCIAL_TRUST`)

| UI (RU) | Внутреннее имя | Источник | Диапазон | Default | wired |
|---|---|---|---|---|---|
| Нейтральное доверие | `SOCIAL_TRUST_NEUTRAL` | `core/constants.py:347` | `-100…+100` | `0.0` | ✓ |
| Порог вражды | `SOCIAL_TRUST_HOSTILE_THRESHOLD` | `core/constants.py:348` | `-100…0` | `-50.0` | ✓ |
| Порог высокого доверия | `SOCIAL_TRUST_HIGH_THRESHOLD` | `core/constants.py:349` | `0…+100` | `50.0` | ✓ |
| Скорость роста доверия | `[PLAN] trust_growth_rate` | — | `0.0–1.0` | `0.10` | [PLAN] |
| Скорость падения доверия | `[PLAN] trust_decay_rate` | — | `0.0–1.0` | `0.30` | [PLAN] |
| Способность прощать | `[PLAN] forgiveness_rate` | — | `0.0–1.0` | `0.05` | [PLAN] |

## A.9. Итоговое количество параметров

| Категория | wired | [PLAN] | Всего |
|---|---|---|---|
| Личность (L0) | 5 | 3 | 8 |
| Восприятие | 8 | 0 | 8 |
| Эмоции | 9 | 0 | 9 |
| Решения | 17 | 0 | 17 |
| Искажение | 5 | 0 | 5 |
| BREAK_SYSTEM | 7 | 0 | 7 |
| Память | 8 | 0 | 8 |
| Отношения | 3 | 3 | 6 |
| **Итого** | **62** | **6** | **68** |

**Вывод:** Лаборатория должна предоставить **62 реально работающих** слайдера + **6 запланированных** (отключённых).

---

# Приложение B. Реальные файлы кода для интеграции

## B.1. Файлы для чтения (без модификаций)

| Файл | Назначение |
|---|---|
| `backend/app/services/tick_orchestrator.py` | Главный tick-entry, 10 фаз |
| `backend/app/services/npc/decision_hub.py` | DecisionHub.compute() — формула скоринга |
| `backend/app/services/npc/life_engine.py` | LifeEngine.tick() — макро-симуляция |
| `backend/app/services/npc/state_applicator.py` | Единственный писатель в NPCState |
| `backend/app/services/npc/perception_engine.py` | Сборка PerceptualKernel |
| `backend/app/services/npc/break_progress_engine.py` | TraitDriftEvent |
| `backend/app/services/npc/belief_crystallization_engine.py` | L2.5 beliefs |
| `backend/app/services/npc/crystallized_belief_store.py` | Хранилище L2.5 beliefs |
| `backend/app/services/npc/drive_resolver.py` | EffectiveDrives |
| `backend/app/services/npc/kernel_rng.py` | Детерминированный RNG (ADR-O-301) |
| `backend/app/services/memory/relationship_store.py` | Trust SSOT |
| `backend/app/services/memory/layered_memory.py` | STM → L2 → Campaign |
| `backend/app/services/memory/memory_manager.py` | Единственный писатель в память |
| `backend/app/services/game_loop_builder.py` | Сборка GameLoop из компонент |
| `backend/app/models/npc_state.py` | NPCState + PerceptualKernel + EventMemory |
| `backend/app/models/npc_profile.py` | L0 профиль |
| `backend/app/models/psychological.py` | DistortionProfile + CausalEntry |
| `backend/app/models/affect.py` | AffectiveImprint + ResponseBias |
| `backend/app/models/will.py` | IntentPressureProfile + WillResponseDTO |
| `backend/app/models/front.py` | Front-система (маски) |
| `backend/app/models/cognitive_dissonance.py` | Contradiction |
| `backend/app/domain/epistemology.py` | Proposition + EpistemicRecord |
| `backend/app/domain/events.py` | EventDTO |
| `backend/app/contracts/life_engine.py` | LifeEngineInterface Protocol |
| `backend/app/contracts/interventions.py` | InterventionEvent |
| `backend/app/core/constants.py` | Все константы DECISION_HUB/DISTORTION/BREAK |
| `diagnostics/dna_metrics.py` | DNASnapshot + 25 метрик |
| `diagnostics/causal_observer.py` | Пост-мортем лог-анализатор |
| `config/canon/truth_state_tavern.json` | Сценарий «Серебряный Волк» |
| `config/npc/individuals/lusya.json` | Конфиг NPC (пример) |
| `architecture/pipeline.yaml` | Архитектурный контракт |

## B.2. Файлы для создания (новые)

| Файл | Назначение |
|---|---|
| `backend/app/services/calibration/__init__.py` | Пакет калибровки |
| `backend/app/services/calibration/experiment_runner.py` | ExperimentRunner — оркестратор сессий |
| `backend/app/services/calibration/scenario_player.py` | Воспроизведение сценария по таймлайну |
| `backend/app/services/calibration/config_overlay.py` | Подмена констант `constants.py` на время эксперимента |
| `backend/app/services/calibration/metrics/character_change.py` | Character Change Rate |
| `backend/app/services/calibration/metrics/decision_diversity.py` | Decision Diversity |
| `backend/app/services/calibration/metrics/emotional_volatility.py` | Emotional Volatility |
| `backend/app/services/calibration/metrics/belief_revision_rate.py` | Belief Revision Rate |
| `backend/app/services/calibration/metrics/relationship_dynamics.py` | Relationship Dynamics |
| `backend/app/services/calibration/metrics/event_responsiveness.py` | Event Responsiveness |
| `backend/app/services/calibration/metrics/causal_depth.py` | Causal Depth |
| `backend/app/services/calibration/metrics/loop_rate.py` | Loop Rate |
| `backend/app/services/calibration/metrics/character_stability.py` | Character Stability |
| `backend/app/services/calibration/metrics/wow_aggregator.py` | WOW Density (главное) |
| `backend/app/services/calibration/zone_classifier.py` | Классификатор МАНЕКЕН/ХАОС/ENIGMA |
| `backend/app/services/calibration/sweep/` | Parameter Sweep (grid/random/CMA-ES) |
| `backend/app/services/calibration/sweep/scoring.py` | Целевая функция |
| `backend/app/services/calibration/sweep/phase_engine.py` | Реализация `EnigmaPhaseEngine` (замена stub) |
| `backend/app/services/calibration/ab_runner.py` | A/B сравнение |
| `backend/app/services/calibration/replay_verifier.py` | Детерминизм-проверка |
| `backend/app/services/calibration/preset_io.py` | Чтение/запись YAML-пресетов |
| `backend/app/services/calibration/exporters/json_exporter.py` | Экспорт JSON |
| `backend/app/services/calibration/exporters/csv_exporter.py` | Экспорт CSV |
| `backend/app/services/calibration/exporters/html_exporter.py` | Экспорт HTML |
| `backend/app/services/calibration/exporters/png_exporter.py` | Экспорт PNG-графиков |
| `backend/app/api/calibration_routes.py` | REST API для UI |
| `backend/app/api/calibration_stream.py` | SSE-стрим для live-обновлений |
| `config/scenarios/tavern_silver_wolf_45min.yaml` | Главный сценарий |
| `config/scenarios/tavern_silver_wolf_15min.yaml` | Короткий сценарий |
| `config/scenarios/tavern_silver_wolf_60min.yaml` | Длинный сценарий |
| `configs/calibration/scoring.yaml` | Веса целевой функции sweep |
| `configs/calibration/zone_thresholds.yaml` | Пороги классификации зон |
| `calibration_ui/` | Next.js веб-приложение (UI) |

## B.3. Файлы для расширения (минимальная модификация)

| Файл | Что добавляется |
|---|---|
| `diagnostics/dna_metrics.py` | Новые поля `DNASnapshot`: `wow_density`, `character_change_rate`, `decision_diversity`, `loop_rate`, `zone` |
| `backend/app/api/routes.py` | Подключение `calibration_routes.router` |
| `backend/app/main.py` | В lifespan — инициализация `CalibrationService` |
| `backend/app/core/config.py` | Настройки `CALIBRATION_PORT`, `CALIBRATION_DATA_DIR` |

---

# Приложение C. Существующая инфраструктура SUPERBOX

## C.1. Что уже есть и **переиспользуется**

```text
backend/tests/sandbox/SUPERBOX/
├── run.py                          # CLI dispatcher
├── npc_sandbox.py                  # SandboxConfig, NPCSandbox
├── drift_laboratory.py             # 7 stress-режимов
├── causal_validation.py            # CausalValidator
├── behavior_laboratory.py          # trait_economy_probe
├── player_stress_test.py          # player_stress_test
├── scenarios/                      # 25+ epistemic tests
│   ├── epistemic_divergence_test.py
│   ├── epistemic_decision_divergence_test.py
│   ├── epistemic_persistence_test.py
│   ├── modifier_composition_test.py
│   ├── modifier_commutativity_test.py
│   ├── epistemic_membrane_hardening_test.py
│   └── ... (см. полный список в README §13)
└── reports/                        # дрейф_*.csv,  дрейф_*.log,  дрейф_*.png
```

## C.2. Что уже есть в `backend/tests/sandbox/calibration/` (скелет)

```text
backend/tests/sandbox/calibration/
├── contracts.py        # CausalPressureVector, CausalStateVector
├── isk.py              # PhasePhysicsEngine (ABC), classify_regime_by_isk()
└── run_sweep.py         # build_phase_stability_map()
                        # EnigmaPhaseEngine — pass stub (нужно реализовать)
```

## C.3. probes (9 зондов) — `backend/app/services/probes/probes/`

| Зонд | Что проверяет |
|---|---|
| `historical_constraint_probe.py` | Invariant II: EffectiveDrives consistency |
| `spatial_coherence_probe.py` | SC-1..SC-8: локации, расстояния |
| `traversal_fsm_probe.py` | ADR-TRAV-FSM |
| `causal_provenance_probe.py` | Invariant I: tick_mutation causality |
| `somatic_gate_probe.py` | body_state sanity |
| `mvp_pipeline_probe.py` | MVP controller wiring |
| `temporal_isolation_probe.py` | время только вперёд |
| `death_lock_probe.py` | мёртвые NPC остаются мёртвыми |
| `l3_ephemeral_probe.py` | EffectiveDrives не кешируются |

**Все 9 зондов должны выполняться в каждом эксперименте лаборатории.**

Если хотя бы один зонд падает — эксперимент помечается `BROKEN`.

## C.4. DNA-метрики (25+) — `diagnostics/dna_metrics.py`

Уже есть:
- `SHI` (Simulation Health Index);
- `NPI` (NPC Pipeline Integrity);
- `OBI` (Obedience Breakthrough Index);
- `SCF` (Spatial Coherence Factor);
- `ADR` (Architecture Debt Ratio);
- `CVS` (Causal Velocity Score);
- `BCI` (Belief Crystallization Index);
- `BPI` (Break Progress Index);
- `NEI` (Need Urgency Index);
- `DRI` (Direct Response Integrity);
- `DPI` (Dialogue Pipeline Integrity);
- `PFI` (Pre-Bus Failure Index);
- `INV_V`, `INV_W` (invariant violations/warnings).

**Новые метрики лаборатории** добавляются как новые поля `DNASnapshot` (см. Приложение B.3).

---

# Приложение D. Сценарий приёмки для финального тестирования

> Сценарий проверяет, что лаборатория **правильно находит** варианты конфигураций.

## D.1. Тест-кейс «МАНЕКЕН детектируется»

```yaml
test_id: ACCEPTANCE_001
name: "Лаборатория правильно классифицирует зону МАНЕКЕН"
steps:
  - action: load_preset
    preset: configs/calibration/test_presets/mannequin.yaml
    # identity_rigidity=0.95, decay_rate=0.001, INTENT_INERTIA_WEIGHT=0.8
  - action: run_scenario
    scenario: tavern_silver_wolf_45min
    seed: 7331
  - action: wait_completion
expected:
  zone: MANNEQUIN
  wow_density: "< 0.2"
  loop_rate: "> 0.5"
  character_change_rate: "< 0.15"
  invariant_violations: 0
  nan_count: 0
```

## D.2. Тест-кейс «ХАОС детектируется»

```yaml
test_id: ACCEPTANCE_002
name: "Лаборатория правильно классифицирует зону ХАОС"
steps:
  - action: load_preset
    preset: configs/calibration/test_presets/chaos.yaml
    # identity_rigidity=0.1, decay_rate=0.5, SCORE_NOISE_RANGE=0.3
  - action: run_scenario
    scenario: tavern_silver_wolf_45min
    seed: 7331
  - action: wait_completion
expected:
  zone: CHAOS
  contradiction_rate: "> 0.20"
  causal_coverage: "< 0.5"
  character_stability: "< 0.2"
  invariant_violations: 0    # хаос не должен ломать инварианты
  nan_count: 0
```

## D.3. Тест-кейс «ENIGMA zone детектируется»

```yaml
test_id: ACCEPTANCE_003
name: "Лаборатория правильно классифицирует зону ENIGMA"
steps:
  - action: load_preset
    preset: configs/calibration/test_presets/enigma_golden.yaml
    # identity_rigidity=0.42, threat=0.18, decay_rate=0.045, AFFECT_DECAY_BASE_RATE=0.06
  - action: run_scenario
    scenario: tavern_silver_wolf_45min
    seed: 7331
  - action: wait_completion
expected:
  zone: ENIGMA
  wow_density: "in [0.4, 1.2]"
  character_change_rate: "in [0.3, 0.8]"
  loop_rate: "< 0.15"
  character_stability: ">= 0.5"
  causal_coverage: ">= 0.9"
  invariant_violations: 0
  nan_count: 0
```

## D.4. Тест-кейс «A/B сравнение работает»

```yaml
test_id: ACCEPTANCE_004
name: "A/B режим правильно различает конфигурации"
steps:
  - action: load_ab
    config_a: configs/calibration/test_presets/enigma_golden.yaml
    config_b: configs/calibration/test_presets/mannequin.yaml
  - action: run_parallel
    scenario: tavern_silver_wolf_45min
    seed: 7331
  - action: wait_completion
expected:
  config_a.zone: ENIGMA
  config_b.zone: MANNEQUIN
  wow_density_ratio_a_to_b: "> 2.0"   # A как минимум в 2 раза выразительнее
  replay_deterministic: true
```

## D.5. Тест-кейс «Детерминизм сохраняется»

```yaml
test_id: ACCEPTANCE_005
name: "Один и тот же seed даёт одинаковый результат"
steps:
  - action: run_experiment
    preset: configs/calibration/test_presets/enigma_golden.yaml
    scenario: tavern_silver_wolf_45min
    seed: 7331
    save_run_id: run_1
  - action: run_experiment
    preset: configs/calibration/test_presets/enigma_golden.yaml
    scenario: tavern_silver_wolf_45min
    seed: 7331
    save_run_id: run_2
  - action: compare
    run_1: run_1
    run_2: run_2
expected:
  state_diff_count: 0
  metrics_diff_max: 0.0
```

## D.6. Тест-кейс «Sweep находит золотую область»

```yaml
test_id: ACCEPTANCE_006
name: "Parameter sweep находит хотя бы 3 ENIGMA-конфигурации"
steps:
  - action: run_sweep
    parameters:
      - identity_rigidity: [0.2, 0.4, 0.6, 0.8]
      - threat_amplification_factor: [0.05, 0.15, 0.30]
      - decay_rate: [0.02, 0.05, 0.10, 0.20]
    scenario: tavern_silver_wolf_45min
    seed: 7331
  - action: classify_results
expected:
  total_configs: 48
  enigma_zone_count: ">= 3"
  mannequin_zone_count: ">= 5"
  chaos_zone_count: ">= 5"
  all_configs_nan_free: true
  all_configs_invariant_safe: true
```

## D.7. Тест-кейс «Сохранение пресета»

```yaml
test_id: ACCEPTANCE_007
name: "Найденная конфигурация корректно сохраняется в YAML"
steps:
  - action: find_best_enigma_config
    save_as: configs/npc/enigma_mvp_test.yaml
  - action: reload_preset
    file: configs/npc/enigma_mvp_test.yaml
  - action: run_experiment
    preset: reloaded
    scenario: tavern_silver_wolf_45min
    seed: 7331
expected:
  reloaded_zone: ENIGMA
  reloaded_metrics_match_original: true
  yaml_contains:
    - meta.preset_id
    - meta.enigma_version
    - meta.seed
    - meta.experiment_id
    - parameters
    - metrics_achieved
    - formulas_version
    - validation
```

---

**КОНЕЦ ТЗ.**

> Следующий документ: `План_Разработки_Лаборатории.md` — пошаговый план для архитектора.



ТЗ АКТУАЛЬНЫЙ:
Краткая сводка для Приёмника
Сделано (S220–S222, всё runtime-подтверждено):

S220 / ADR-O-367: Intervention Consequence Routing — структурированная семантика → компилятор → RelationshipStore; trust None→20.0 на scripted-HELP; init_campaign в lab-старте; S116-фоллбэк-фикс; LabScreen читает SSOT (плоский ключ "maid_lusya→player").
S221: ScenarioPlayer (YAML + строгий валидатор + poll-семантика 1-based + журнал replay-identity + гейт «не оркестратор»); дефолт trust_probe_v1.yaml; ExperimentConfig.scenario_path; ExperimentResult.scenario_id/scenario_events; секрет в consequence-ветви.
S222: ui/graphs.py (LineGraph/BarChart); панель динамики в LabScreen; клик-выбор NPC; история per-NPC.
Легализация: ADR-O-368 (dev-enclave + allowlist линтера; INV-FRONTEND-ISOLATION снова зелёный).
Попутная FE-серия: cold-start game_screen, keybindings-резолвер (tab/escape/return были мертвы всегда), TAB-toggle/ESC-приоритет, опечатка end_screen-данных.
Осталось (приоритет Приёмнику — в порядке мастера): кнопки игрока в UI (11.1/11.2, формат payload — Замена 4 файла ТЗ) → timeline (9) → A/B sequential (18) → сохранение пресета (23/3.6.2) → экспорт CSV/JSON → DRAMATIC SESSION-профили (3.2) → затем M2 (WOW Density на готовых rel_captures, ZoneClassifier, DEBT-CAUSAL-DEPTH).

Красные/долги вне зоны: N3 downloader (S217/218); DEBT-LLM-SPAWN; DEBT-ABORT-404 (→O-364); DEBT-INTENT-PASS-THROUGH (геймплей, мастер); DEBT-QUIESCE (+ флак-тест его класса); DEBT-SOC (runtime-подтверждён — вероятно главный кандидат на оживление idle-социума в M2).

Обе вставки применяются как обычные .md-правки (по одной уникальной строке поиска на замену; Addendum B — вставка целиком перед ---, отделяющим раздел 3 от раздела 4; раздел 0.4 — вставка перед ---, отделяющим раздел 0 от раздела 1). Если хотите, могу следующим шагом выдать их же как единые PowerShell-скрипты вставки (Add-Content/замены через .NET) — но по РЕЖИМУ для .md ручная вставка в VS Code надёжнее.