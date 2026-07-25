# ENIGMA — КОНТРАКТ ЗАМЫКАНИЯ v2.0

**Дата:** 2026-07-23
**Версия кода:** V.0.5.3.5.6
**Принцип:** Только незакрытые пункты. Закрытые — удалены.

---

## §0. ПРАВИЛА

1. **Запрет новых ADR** до закрытия всех пунктов.
2. **Запрет новых фич.** Только замыкание.
3. **Порядок строгий.** Фазы последовательно.
4. **Критерий готовности:** pytest green + логи чистые + пункт помечен `[x]`.

---

## §1. ОСТАЛОСЬ ДО TZ ЛЮСИ (15 пунктов, ~16 часов)

### T-03: STM персистентность
- **Статус:** [ ]
- **Файлы:** `services/memory/dialogue_session.py`, `services/memory/memory_manager.py`
- **Что сделать:** Персистить `DialogueSession` в SQLite (последние 5 реплик per NPC). При загрузке — восстанавливать.
- **Критерий:** После рестарта NPC помнит последние 3-5 реплик.

### T-04: npc_npc_context — заполнить
- **Статус:** [ ]
- **Файлы:** `services/verbalization/verbalization_context.py` (поле есть, не заполняется), `services/execution/dialogue_executor.py`
- **Что сделать:** В `dialogue_executor.py` — запрашивать `memory_manager.recall(target_tags=(target_id,))` и заполнять `npc_npc_context`.
- **Критерий:** NPC_A говорит NPC_B: «Ты опять здесь? Вчера ты уже приходил.»

### T-05: Topic continuity — last_topic
- **Статус:** [ ]
- **Файлы:** `services/tick_orchestrator.py:_phase_4_pre_decision`, `models/npc_state.py`
- **Что сделать:** Хранить `last_topic` + `last_topic_tick` в NPCState. Если < 5 тиков назад и tone != ANGRY — продолжить тему.
- **Критерий:** NPC говорит на одну тему 3-5 тиков подряд.

### T-06: Beliefs → DecisionHub для NPC-NPC
- **Статус:** [ ]
- **Файлы:** `services/npc/decision_hub.py`, `services/npc/crystallized_belief_modifier_resolver.py`
- **Что сделать:** В `DecisionHub.compute` — для каждого candidate target, запросить `crystallized_belief_store.get_beliefs(npc_id)` и применить modifiers.
- **Критерий:** При `fear_belief > 0.7` NPC выбирает FLEE. При `trust_belief > 0.7` — TALK/HELP.

### T-07: Player phrases → topic
- **Статус:** [ ]
- **Файлы:** `services/npc/topic_extractor.py`
- **Что сделать:** Добавить `_PHRASE_TO_TOPIC` mapping ("как дела" → "самочувствие", и т.д.).
- **Критерий:** Игрок говорит «Люся, как дела?» → topic='самочувствие'.

### Bridge 3: PLAYER_SPOKE → _THREAT_TYPES
- **Статус:** [ ]
- **Файлы:** `services/npc/belief_transition_engine.py`
- **Что сделать:** Добавить `PLAYER_SPOKE` в `_THREAT_TYPES`. Когда игрок раскрывает секрет → NPC формирует DANGER belief.
- **Критерий:** Игрок говорит Люсе «Борко подглядывает» → Lusya forms belief DANGER.

### S-01: Прописать wall_id на дверях в tavern.json (КРИТИЧНО)
- **Статус:** [ ]
- **Файлы:** `frontend/map_editor/campaigns/Open_road/locations/tavern.json`
- **Что сломано:** P4-02 исправил код (`wall_id = obj.get("wall_id")`), но в `tavern.json` у дверного объекта **нет поля `wall_id`**. Стены не разрезаются проёмами → сплошные → NPC не может пройти к exit_east/exit_south. **177 WALL_CLEARANCE_BLOCKED** за сессию.
- **Fix:** Найти дверной объект (obj_32 или obj_door_kitchen) и добавить `"wall_id": "wall_1"`. Это **одна строка** в JSON.
- **Критерий:** В логе 0 `SPATIAL_VALIDATION` errors для edges к exit_east/exit_south. NPC проходит через дверной проём.

### S-02: Boundary nodes не за стенами
- **Статус:** [ ]
- **Файлы:** `frontend/map_editor/campaigns/Open_road/locations/tavern.json`, `services/spatial/graph_compiler.py:_create_boundary_nodes`
- **Что сломано:** `exit_east` на (18, 6) — **на** стене `wall_5` (x=18, y=2-7). NPC не может достичь boundary node потому что стена блокирует. Boundary node должен быть **в дверном проёме** или **внутри локации у двери**, не на глухой стене.
- **Fix:** Сдвинуть `exit_east`/`exit_south` координаты в `_create_boundary_nodes` так, чтобы они были **внутри** локации (на 1м от стены), не **на** стене. Или — поместить boundary node на ближайший nav node у двери.
- **Критерий:** NPC достигает exit_east/exit_south без WALL_CLEARANCE_BLOCKED.

### S-03: Добавить schedule Горану
- **Статус:** [ ]
- **Файлы:** `config/npc/individuals/goran.json`
- **Что сломано:** `routine` пустой. LifeEngine не генерирует MacroMovementGoal → Goran стоит навсегда.
- **Fix:**
  ```json
  "routine": {
    "schedule": {
      "08:00-12:00": "working",
      "12:00-14:00": "eating",
      "14:00-18:00": "working",
      "18:00-22:00": "drinking",
      "22:00-08:00": "sleeping"
    }
  },
  "activity_map": {
    "sleeping": {"location": "tavern_silver_wolf", "position": "fireplace", "display": "sleeping"},
    "eating": {"location": "tavern_silver_wolf", "position": "main_hall", "display": "eating"}
  }
  ```
- **Критерий:** Goran двигается по расписанию: работа → еда → выпивка → сон.

### S-04: CROSS_LOC — что происходит после достижения boundary
- **Статус:** [ ]
- **Файлы:** `services/spatial/movement_engine.py`, `services/scene_state_manager.py:1096`
- **Что сломано:** Код для смены локации существует (`scene_state_manager.py:1096` меняет `entry["location_id"] = target_loc`), но NPC **никогда не достигает** boundary node из-за S-01/S-02. После фикса S-01+S-02 нужно проверить что NPC реально переходит в city_gate/market_square.
- **Fix:** После S-01+S-02 — запустить игру, проверить что Borko доходит до exit_east → меняет локацию на city_gate → появляется в city_gate:guard_post.
- **Критерий:** Borko уходит в city_gate на работе (08:00-20:00). Orm уходит в market_square на работе (06:00-12:00, 14:00-18:00).

### L-01: Аргументы context_provider перевёрнуты (УТЕЧКА "open_road")
- **Статус:** [ ]
- **Файлы:** `services/execution/dialogue_executor.py:80`, `services/npc/life_engine.py:get_npc_observed_state`
- **Что сломано:** `get_npc_observed_state(campaign_id, npc_id)` — `campaign_id` ПЕРВЫЙ. `dialogue_executor` вызывает `self._get_context(task.owner_id, task.campaign_id)` — `npc_id` ПЕРВЫЙ. Аргументы **перевёрнуты**. Результат: `get_npc_observed_state("maid_lusya", "Open_road")` — ищет NPC с id="Open_road" → не находит → fallback `{"name": "Open_road"}`. LLM видит имя «Open_road» и использует его в репликах.
- **Fix:** Поменять местами аргументы в вызове: `self._get_context(task.campaign_id, task.owner_id)`.
- **Критерий:** В логе LLM промптов нет «open_road» или campaign_id как имени NPC.

### L-02: ResponseValidator НЕ применяется к диалогам NPC
- **Статус:** [ ]
- **Файлы:** `services/execution/dialogue_executor.py`, `services/verbalization/response_validator.py`
- **Что сломано:** `ResponseValidator` существует, проверяет CJK/кириллицу/4-ю стену. **НО `DialogueExecutor` его НЕ использует.** LLM реплики NPC проходят без валидации → китайские иероглифы, английский текст, упоминание «игрок»/«симуляция».
- **Fix:** В `dialogue_executor._generate_with_router` — после `raw = self._router.request_for_agent(...)` вызвать `ResponseValidator.validate(raw)` и при `is_fallback=True` вернуть fallback.
- **Критерий:** 0 китайских иероглифов в репликах NPC. 0 английских фраз. 0 упоминаний «игрок»/«симуляция».

### L-03: voice_profile, backstory, author_notes НЕ передаются в LLM
- **Статус:** [ ]
- **Файлы:** `services/npc/life_engine.py:get_npc_observed_state`, `services/execution/dialogue_executor.py`
- **Что сломано:** NPC JSON содержит `voice_profile` ("Говоришь тихо, короткими фразами..."), `backstory` ("Три года работает у Торнина..."), `author_notes` ("Никогда не признавайся в связях с гильдией..."). Но `get_npc_observed_state` возвращает только `name` + `description`. LLM не знает **как** говорить, **о чём** говорить, **чего не говорить**. Все NPC звучат одинаково.
- **Fix:** Расширить `get_npc_observed_state` — возвращать `voice_profile`, `backstory`, `author_notes`. В `dialogue_executor` — добавить их в `user_prompt`.
- **Критерий:** Люся говорит тихо, короткими фразами, запинается. Торнин говорит ровно, хрипло. Борко — грубо.

### L-04: DialogueExecutor system_prompt — минимальный, без языковых правил
- **Статус:** [ ]
- **Файлы:** `services/execution/dialogue_executor.py:82-86`
- **Что сломано:** System prompt DialogueExecutor = 3 строки ("Ты — NPC в мире ENIGMA..."). Нет языковых ограничений. DM system prompt (`prompts/dm_system.txt`) — 49 строк с жёсткими правилами («НЕ ПИШИ по-китайски», «только русский»). DialogueExecutor игнорирует всё это.
- **Fix:** Загрузить `dm_system.txt` как базу для DialogueExecutor system_prompt, ИЛИ создать `npc_dialogue_system.txt` с правилами для реплик NPC.
- **Критерий:** LLM получает жёсткие языковые правила для реплик NPC.

### L-05: target_id в промпте как raw ID, не как имя
- **Статус:** [ ]
- **Файлы:** `services/execution/dialogue_executor.py:107`
- **Что сломано:** `user_prompt` содержит `f"Ты обращаешься к: {req.target_id}."` — `target_id` это `"maid_lusya"`, не «Люся». LLM видит «maid_lusya» и может использовать это в реплике. Также beliefs text содержит `req.target_id` вместо имени.
- **Fix:** Конвертировать `target_id` → имя через `get_npc_observed_state(campaign_id, target_id)` или `_npc_id_to_display`.
- **Критерий:** В промпте LLM видит «Ты обращаешься к: Люся», не «maid_lusya».

---

### Порядок закрытия §1

1. **L-01** (5 мин) — args swap → устраняет «open_road» leak
2. **L-02** (30 мин) — ResponseValidator → устраняет китайский/английский
3. **L-04** (30 мин) — system prompt с языковыми правилами
4. **L-05** (15 мин) — target_id → имя
5. **L-03** (1 ч) — voice_profile/backstory/author_notes
6. **T-07** (30 мин) — player phrases → topic
7. **T-04** (2 ч) — npc_npc_context
8. **T-06** (2 ч) — beliefs → DecisionHub
9. **T-05** (1 ч) — topic continuity
10. **T-03** (1 ч) — STM persistence
11. **Bridge 3** (1 день) — PLAYER_SPOKE → beliefs

**После §1: acceptance test 6/11. NPC говорят на чистом русском, с индивидуальным голосом. Можно начинать TZ Люси.**

---

## §2. TZ «СЕКРЕТЫ ЛЮСИ, ТАЙНЫ ТАВЕРНЫ» (15 компонентов, ~2 недели)

### P7-01: TruthStateLoader
- 16 секретов, 20 связей. `config/canon/truth_state_tavern.json` + `services/truth_state_loader.py`.

### P7-02: ObservationLog
- Лог всех наблюдений игрока. `services/player_cognition/observation_log.py`.

### P7-03: PlayerBeliefModel — интеграция с TruthState
- Сравнение belief vs truth на End-Screen.

### P7-04: SocialFabricTracker
- Baseline снимок при входе + delta history. Расширение `RelationshipStore`.

### P7-05: FateTracker
- `FateState` per NPC: stability, threat_level, fate_trajectory. Триггер fate_event при threat > 0.8 AND stability < 0.2.

### P7-06: FactionAlignmentTracker
- `player_alignment: Dict[faction_id, float]` (-100..100). Delta при действиях игрока.

### P7-07: DilemmaEngine
- 5 моральных дилемм. Rule-based, не скрипты. `services/dilemma/dilemma_engine.py`.

### P7-08: EvaluationEngine
- `evaluate(beliefs, truth_state, fate_events) → Score{secrets, causal_links, methods, fates, contradictions}`.

### P7-09: CognitiveDissonanceTracker
- Полная таблица противоречий. На 3+ → special end-screen message.

### P7-10: EndScreenRenderer
- Pygame-экран с цветовой системой, судьбами, цитатами, социальной тканью.

### P7-11: LastWordsSystem
- 6 NPC × 4 судьбы = 24 цитаты. Триггер при fate_event.

### P7-12: ExitTrigger
- Выход из таверны → EvaluationEngine → EndScreen.

### P7-13: WorldStateDiff
- `npc_fates, relationship_changes, faction_alignments, secrets_exposed, world_events`. Персист в `saves/<campaign>/world_diff.json`.

### P7-14: Механики
- Eavesdrop (подслушивание, радиус < 3.0), Blackmail (Intent.blackmail), Zombie reader fix, cue_key fix, combat_data fix, DMFrame recent_trauma.

### P7-15: Smoke-тест
- Полный прогон: вход → диалоги → раскрытие 3 секретов → дилемма → выбор → судьбы → End-Screen.

---

## §3. БЭКЛОГ (после MVP)

### B-06: Theory of Other
- `OtherMindModel` per NPC. Что A думает, что B думает. Level 2 max.

### B-07: Replay as epistemic archaeology
- После End-Screen игрок может «прокрутить» игру с точки зрения любого NPC.

### B-08: WorldChronicle — Birth/Death/Aging/Succession (TZ-02 V.2.0)
- `birth_tick`, `death_tick`, `generation` в NPCState.
- Aging: `age_years = (current_tick - birth_tick) / AGE_TICKS_PER_YEAR`. Старение привязано к `game_time_seconds`, НЕ к wall-clock.
- Succession: при смерти NPC наследник получает CrystallizedBelief ×0.5 weight.
- WorldChronicleStore (SQLite, append-only): BIRTH/DEATH/SUCCESSION/MARRIAGE events.
- Запреты: §14 (единичное время), §15 (изоляция wall-clock), §16 (beliefs не мутируют L0).

### B-09: Memetic Transmission Domain (TZ_MEMETIC_01)
- Культурные единицы (мемы): слова, имена, жесты, ритуалы — распространяются между NPC.
- Concept Registry (канон) → Expression Registry (формы) → Speaker Vocabulary (per-NPC adopted).
- Cultural Pressure Accumulator: когда мем «созрел» → Memetic Burst (LLM генерирует форму → валидатор → реестр).
- Player-created memes: игрок вводит слово → оно может распространиться.
- Аналитический drift для time-skip: аппроксимация распространения мемов при перемотке.
- Принцип: LLM — голос, не источник истины. LLM предлагает форму, симуляция решает что приживётся.

### B-10: Content Policy Integration (TZ_MEMETIC_02)
- Per-NPC ContentProfile (4 уровня: глобальный → архетип → adopted → effective).
- Noble не использует воровской жаргон. Вор не говорит как аристократ.
- ResponseValidator фильтрует по per-NPC vocabulary, не глобальным правилам.
- Флаг `memetic_integration_enabled` — включается постепенно, обратно совместима.

### B-11: Curiosity drive
- Пятый драйв. При `curiosity > 0.5` NPC генерирует `Intent.observe`.

### B-12: Goal Tree
- Заменить `life_project: str` на `active_goals: List[Goal]`.

### B-13: Abstract Reasoning Layer
- Conceptual Transfer. 4 операции: Structural Compression, Analogical Retrieval, Schema Mutation, Counterfactual Simulation.

### B-14: Inference Engine & Theory of Mind
- Цикл: OBSERVATION → HYPOTHESIS → PREDICTION → ACTION → NEW EVIDENCE → UPDATE.
- Конкурирующие гипотезы с confidence. Model Refinement. Predictive Models.
- Inference Engine — системный (Python), не LLM.

### B-15: BodySchema — per-NPC геометрия тела
- `BodySchema` dataclass: gender, age_years, race, height, shoulder_width, hip_width, body_fat, head_ratio, limb_length_ratio, parts (Dict[str, BodyPart]).
- `BodyPart`: name, integrity (0-1), functional (bool), wounds, visible_marks.
- `BodyCapabilities` в `domain/traversal.py` вычисляется из `BodySchema`, не хардкожен.
- Per-NPC значения в `config/npc/individuals/*.json` → `body_schema` секция.
- Старение: `apply_aging(body, age_years)` меняет пропорции (рост↓, жир↑, скорость↓).
- Потеря конечностей: `parts["left_arm"].functional = False` → не рисуется, не функционирует.
- Младенцы/дети: `can_walk=False`, `head_ratio=0.28`, `movement_speed=0`.
- **Не для MVP.** Добавить `body_schema` в JSON NPC сейчас (данные готовы), рендеринг — Phase 3.

---

## §4. ПРИНЦИПЫ

1. **Не строить параллельную архитектуру.**
2. **Не дублировать существующие компоненты.**
3. **LLM не принимает решения. Backend определяет meaning, LLM рендерит language.**
4. **Forensic audit имеет приоритет** над новыми фичами.
5. **Прогресс измеряется закрытыми пунктами**, не количеством кода.
6. **После §2 — пересмотр контракта v3.0.**
7. **§14 (единичное время), §15 (изоляция wall-clock), §16 (beliefs не мутируют L0)** — ненарушаемы.
8. **L-01..L-05 — костыли для MVP.** B-09 (Memetic) + B-10 (Content Policy) — правильное решение. Костыли заменяются после MVP.
9. **TZ_MEMETIC_03 Patch List** (12 патчей, 8 новых файлов) — готов к реализации. Не требует дизайна, только исполнения.
