# ENIGMA — MVP КОНТРАКТ v3.0

**Дата:** 2026-07-25
**Версия кода:** V.0.5.3.5.8
**Цель:** Играбельная миниигра «Секреты Люси» — вход в таверну → диалоги → раскрытие секретов → дилемма → судьбы → End-Screen.
**Принцип:** Только незакрытые пункты. Закрытые — удалены.

---

## §0. ЧТО УЖЕ РАБОТАЕТ (не трогать)

- LLM: qwen_7b, «доступен», 200 OK
- NPC-NPC диалоги: 23 за сессию, trust=-6.0..-8.0 для ANGRY
- Topics: 5+ (наблюдение, встреча, власть, безопасность, желания)
- LLM получает: voice_profile, backstory, author_notes, crystallized_beliefs
- ResponseValidator: CJK/кириллица/4-я стена — подключён
- L-01..L-05: все закрыты (args swap, validator, voice, system prompt, target_name)
- T-01, T-02, T-04, T-07: закрыты
- Bridge 3: PLAYER_SPOKE в _THREAT_TYPES
- S-03: Goran schedule добавлен
- Movement: 139 RELOCATE, 0 WALL_CLEARANCE_BLOCKED, 0 GAP_TOO_WIDE
- Spatial: 17 nodes, 18 edges, boundary=east/south connected
- Content Policy: 4 оси (profanity, sexual, violence, taboo)
- Drift B: 0
- TICK_CRASH: 0
- TZ Люси: 13 models + 12 services + truth_state_tavern.json СОЗДАНЫ (нужно подключить)

---

## §1. ЧТО МЕШАЕТ MVP (9 пунктов, ~10 часов)

### S-01: Boundary nodes на стенах (КРИТИЧНО — Борко не выходит)
- **Статус:** [ ]
- **Файл:** `services/spatial/graph_compiler.py:_create_boundary_nodes`
- **Что сломано:** `exit_east` создаётся на `(18, 6)`. `wall_5` проходит по `x=18, y=2-7`. Boundary node стоит **на стене**. Любой путь к exit_east пересекает wall_5 → A_STAR_FAILED × 100. Борко делает 63 попытки, ни одна не успешна.
- **Fix:** Сдвинуть boundary node на 1м внутрь локации:
  ```python
  # Было: "east": (_ox + _w, _oy + _h / 2.0)
  # Должно быть: "east": (_ox + _w - 1.0, _oy + _h / 2.0)
  # Аналогично для south: (_ox + _w / 2.0, _oy + 1.0)
  ```
- **Критерий:** Borko доходит до exit_east → меняет локацию на city_gate. В логе `A_STAR_FAILED` → 0 для borko.

### S-02: wall_id на дверях в tavern.json (КРИТИЧНО — стены сплошные)
- **Статус:** [ ]
- **Файл:** `frontend/map_editor/campaigns/Open_road/locations/tavern.json`
- **Что сломано:** Код `graph_compiler.py` читает `wall_id = obj.get("wall_id")` (P4-02 fix), но в `tavern.json` у дверного объекта **нет поля `wall_id`**. Стены не разрезаются проёмами.
- **Fix:** Найти дверной объект в tavern.json и добавить `"wall_id": "wall_1"` (или ID стены, которую дверь разрезает).
- **Критерий:** В логе 0 `SPATIAL_VALIDATION` errors для edges к exit_east/exit_south/kitchen.

### S-03: Graph recompilation + NPC position validation после редактирования карты (КРИТИЧНО — движение мебели ломает игру)
- **Статус:** [ ]
- **Файлы:** `services/spatial/spatial_service.py`, `services/scene_state_manager.py`
- **Что сломано:** Когда ты двигаешь мебель в редакторе карт и сохраняешь:
  1. `tavern.json` обновляется
  2. `graph_compiler` перекомпилирует граф
  3. **Но** `_path_cache` не очищается → A* использует старые пути
  4. **И** NPC позиции в SQLite остаются старыми → NPC может оказаться внутри передвинутого стола
  5. NPC стоит внутри препятствия → A* не может найти путь → NPC заморожен → игра деградирует
- **Fix (3 изменения):**
  1. В `SpatialService.__init__` (или при перекомпиляции графа) — обязательно `self._path_cache.clear()`
  2. В `scene_state_manager._enrich_local_positions` — после загрузки позиций NPC, проверить каждую: если NPC внутри `walk=False` объекта → переместить на ближайший nav node
  3. В `scene_state_manager.get_scene_state_uncached` — после `_enrich_spatial_data`, вызвать `_path_cache.clear()` на SpatialService
- **Критерий:** После редактирования карты (движение мебели) и запуска игры: NPC не застревают, время течёт, диалоги работают.

### S-04: A_STAR_FAILED — 719 за сессию (КРИТИЧНО — NPC массово застревают)
- **Статус:** [ ]
- **Файл:** `services/spatial/spatial_service.py:find_path`
- **Что сломано:** 719 A_STAR_FAILED за сессию. Затронуты ВСЕ NPC: tornin (187), orm (181), shadow (115), borko (100), goran (88), player (24), lusya (24). Это не только boundary nodes — это **внутренние пути** тоже. NPC не могут ходить по таверне.
- **Причина:** После движения мебели в редакторе, граф перекомпилировался, но `_path_cache` не очищен + узлы могут быть внутри препятствий.
- **Fix:** S-03 (cache clear + position validation). После S-03 — проверить что A_STAR_FAILED < 10 за сессию.
- **Критерий:** A_STAR_FAILED < 10 за 150 тиков.

### H-01: L1Chronicle — tick_id как float, SQLite ожидает int (КРИТИЧНО — beliefs не персистятся)
- **Статус:** [ ]
- **Файлы:** `services/events/npc_dialogue_subscriber.py`, `domain/events.py:EventDTO`
- **Что сломано:** `event.timestamp` = `time.time()` (float, например `1784975968.96`). `TraitDriftEvent.tick_id: int`. Но `tick = getattr(event, "timestamp", 0)` передаёт **float** как `tick_id`. SQLite колонка `tick_id INTEGER`. SQLite **не может** вставить float в INTEGER колонку → `"not an error"` (SQLite exception).
- **Доказательство из лога:** `[L1_CHRONICLE] CRITICAL: failed to persist event TraitDriftEvent(tick_id=1784975968.9583666...)`: `not an error`. `tick_id` — float, не int.
- **Fix:** В `npc_dialogue_subscriber.py`: `tick_id=int(tick)` (привести к int). Или использовать `scene_state["tick"]` (номер тика) вместо `event.timestamp` (wall-clock time).
- **Критерий:** 0 `L1_CHRONICLE.*CRITICAL` в логе. NPC-NPC beliefs кристаллизуются и персистятся.

### H-02: CharacterSheet не имеет effective_hp (ВЫСОКО — avatar loading падает)
- **Статус:** [ ]
- **Файлы:** `services/game_loop/__init__.py`, `models/schemas.py:CharacterSheet`
- **Что сломано:** `avatar_to_prompt(_avatar_state)` вызывает `state.effective_hp`. Но если `_avatar_state` — `CharacterSheet` (не `NPCState`), у него **нет** `effective_hp`. `CharacterSheet` имеет `hp: int` (deprecated). При dead avatar → `avatar_to_prompt` падает → `[AVATAR] ошибка загрузки`.
- **Доказательство из лога:** `[AVATAR] ошибка загрузки: 'CharacterSheet' object has no attribute 'effective_hp'` — каждую сессию.
- **Fix:** В `avatar_to_prompt` — проверить тип: если `CharacterSheet` → использовать `state.hp`, если `NPCState` → `state.effective_hp`. Или: убедиться что `load_state` всегда возвращает `NPCState`, не `CharacterSheet`.
- **Критерий:** 0 `AVATAR.*ошибка` в логе.

### H-03: abort_generation — HTTP 404 (СРЕДНЕ — 8 silent failures за сессию)
- **Статус:** [ ]
- **Файл:** `services/llm/llama_cpp_provider.py:abort_generation`
- **Что сломано:** `abort_generation` посылает POST на `{server_url}/abort`. llama-server возвращает 404 — endpoint `/abort` не существует. 8 silent failures за сессию.
- **Fix:** Проверить API llama-server. Возможно endpoint называется `/stop` или `/cancel`. Или — убрать `abort_generation` если не используется (проверить callers).
- **Критерий:** 0 `B5-FIX` в логе.

### T-05: Topic continuity — NPC продолжает тему
- **Статус:** [ ]
- **Файлы:** `services/tick_orchestrator.py:_phase_4_pre_decision`, `models/npc_state.py`
- **Что сделать:** Добавить `last_topic: str` и `last_topic_tick: int` в NPCState. В `_phase_4_pre_decision`: если `last_topic` был < 5 тиков назад и tone != ANGRY — продолжить тему.
- **Критерий:** NPC говорит на одну тему 3-5 тиков подряд.

### T-06: Beliefs → DecisionHub для NPC-NPC пар
- **Статус:** [ ]
- **Файлы:** `services/npc/decision_hub.py`, `services/npc/crystallized_belief_modifier_resolver.py`
- **Что сделать:** В `DecisionHub.compute` — для каждого candidate target запросить `crystallized_belief_store.get_beliefs(npc_id)` и применить modifiers. При `fear_belief > 0.7` → FLEE. При `trust_belief > 0.7` → TALK/HELP.
- **Критерий:** NPC с fear_belief=0.8 выбирает FLEE от источника страха.

---

### Порядок закрытия §1

1. **S-01** (5 мин) — boundary nodes внутрь → Борко выходит
2. **S-02** (5 мин) — wall_id на дверях → стены разрезаны
3. **H-01** (10 мин) — tick_id=int(tick) → beliefs персистятся
4. **H-02** (15 мин) — avatar_to_prompt type check → avatar не падает
5. **H-03** (15 мин) — abort endpoint fix → 0 silent failures
6. **S-03** (2 ч) — graph recompilation + NPC validation → мебель не ломает игру
7. **S-04** (проверка) — после S-03: A_STAR_FAILED < 10
8. **T-06** (2 ч) — beliefs → DecisionHub
9. **T-05** (1 ч) — topic continuity

**После §1: фундамент полностью замкнут. 0 критических ошибок в логе. Можно подключать TZ Люси.**

---

## §2. ПОДКЛЮЧЕНИЕ TZ ЛЮСИ (5-7 дней)

Модели (13 файлов) и сервисы (12 файлов) **уже созданы**. Нужно их **подключить** к game_loop.

### P1: truth_state_loader → game_loop
- **Файл:** `services/truth_state_loader.py` (создан), `config/canon/truth_state_tavern.json` (создан)
- **Что сделать:** Загружать TruthState при старте кампании. Хранить в `scene_state["truth_state"]`.
- **Критерий:** При старте игры 16 секретов загружены. Игрок может раскрывать через диалоги/наблюдения.

### P2: observation_log → player_cognition
- **Файл:** `services/player_cognition/observation_log.py` (создан)
- **Что сделать:** При каждом действии игрока (диалог, подслушивание, наблюдение) — записывать в ObservationLog.
- **Критерий:** После 10 минут игры в ObservationLog есть 5+ записей.

### P3: player_belief_model → game_loop
- **Файл:** `services/player_cognition/player_belief_model.py` (создан), `models/player_belief.py` (создан)
- **Что сделать:** Обновлять PlayerBeliefModel из ObservationLog. Хранить beliefs игрока о NPC.
- **Критерий:** Игрок говорит «Борко подглядывает» → belief_player(BORKO_IS_VOYEUR) = 0.7.

### P4: social_fabric_tracker → RelationshipStore
- **Файл:** `services/social/social_fabric_tracker.py` (создан), `models/social_fabric.py` (создан)
- **Что сделать:** При входе в таверну — baseline снимок. Каждый тик — delta history.
- **Критерий:** На End-Screen видны все изменения NPC-NPC пар с причинами.

### P5: fate_tracker → game_loop
- **Файл:** `services/social/fate_tracker.py` (создан), `models/fate.py` (создан)
- **Что сделать:** Каждый тик вычислять stability/threat_level для каждого NPC. При threat > 0.8 AND stability < 0.2 → fate_event.
- **Критерий:** Люся при длительном давлении → fate_event(escape) или fate_event(breakdown).

### P6: faction_alignment_tracker → ReputationEngine
- **Файл:** `services/social/faction_alignment_tracker.py` (создан), `models/faction.py` (создан)
- **Что сделать:** Отслеживать player_alignment per faction. Delta при действиях.
- **Критерий:** Help_lusya → +10 воров, -10 стража.

### P7: dilemma_engine → game_loop
- **Файл:** `services/social/dilemma_engine.py` (создан), `models/dilemma.py` (создан)
- **Что сделать:** Проверять trigger conditions каждый тик. При активации — показать выбор игроку.
- **Критерий:** Игрок раскрывает lusya_basement → дилемма «сдать или молчать».

### P8: evaluation_engine → exit_trigger
- **Файл:** `services/social/evaluation_engine.py` (создан), `models/evaluation.py` (создан)
- **Что сделать:** При выходе из таверны — оценить beliefs vs truth, судьбы, методы.
- **Критерий:** Score 0-100 вычислен.

### P9: cognitive_dissonance_tracker → player actions
- **Файл:** `services/player_cognition/cognitive_dissonance_tracker.py` (создан), `models/cognitive_dissonance.py` (создан)
- **Что сделать:** Отслеживать противоречия в действиях игрока.
- **Критерий:** 3+ противоречия → special end-screen message.

### P10: end_screen_builder → frontend
- **Файл:** `services/social/end_screen_builder.py` (создан), `models/end_screen.py` (создан), `frontend/end_screen.py` (новый)
- **Что сделать:** При exit_trigger → end_screen_builder собирает данные → frontend рендерит.
- **Критерий:** Игрок видит судьбы, секреты, социальную ткань, итог.

### P11: last_words_system → fate_tracker
- **Файл:** `services/social/last_words_system.py` (создан), `models/last_words.py` (создан)
- **Что сделать:** При fate_event — выбрать цитату.
- **Критерий:** «Спасибо. Я никогда не забуду.» — Люся, escaped.

### P12: exit_trigger → game_loop
- **Файл:** `services/social/exit_trigger.py` (создан)
- **Что сделать:** При выходе из таверны → trigger evaluation → end_screen.
- **Критерий:** Выход → End-Screen.

### P13: world_diff_builder → persistence
- **Файл:** `services/state/world_diff_builder.py` (создан), `models/world_state_diff.py` (создан)
- **Что сделать:** Сохранить diff для следующей сессии.
- **Критерий:** `saves/<campaign>/world_diff.json` существует после End-Screen.

### P14: Механики (eavesdrop, blackmail)
- **Что сделать:** Eavesdrop (радиус < 3м, RNG шанс услышать), Blackmail (Intent.BLACKMAIL с precondition).
- **Критерий:** Игрок подслушивает разговор Тени и Борко.

### P15: Smoke-тест
- **Что сделать:** Полный прогон: вход → диалоги → раскрытие 3 секретов → дилемма → выбор → судьбы → End-Screen.
- **Критерий:** Тест проходит. Можно играть от начала до конца.

---

### Порядок подключения §2

```
День 1: P1 (truth_state) + P2 (observation_log) + P3 (player_belief)
День 2: P4 (social_fabric) + P5 (fate_tracker) + P6 (faction_alignment)
День 3: P7 (dilemma_engine) + P14 (eavesdrop + blackmail)
День 4: P8 (evaluation) + P9 (cognitive_dissonance) + P11 (last_words)
День 5: P10 (end_screen) + P12 (exit_trigger) + P13 (world_diff)
День 6-7: P15 (smoke-тест) + bugfix
```

---

## §3. РЕДАКТОР КАРТ — ДОРАБОТКА (после MVP, но S-03 критичен сейчас)

### ME-01: Добавление/удаление узлов (после MVP)
- **Файл:** `frontend/map_editor/editor_core.py`
- **Что сделать:** Add node (клик + Enter), Delete node (选中 + Delete), редактор connections.
- **Статус:** Узлы уже можно **двигать** (drag&drop работает). Добавление/удаление — нет.

### ME-02: Симуляция движения в редакторе (после MVP)
- **Что сделать:** Кнопка "Test Simulation" → запуск 100 тиков → показать застревания.
- **Статус:** Не реализовано.

### ME-03: Валидация графа при сохранении (после MVP)
- **Что сделать:** При сохранении карты — проверять: все узлы вне стен/мебели, все рёбра не пересекают стены, все boundary nodes доступны.
- **Статус:** Не реализовано. SPATIAL_VALIDATION в бэкенде есть, но в редакторе — нет.

---

## §4. БЭКЛОГ (после MVP)

- B-06: Theory of Other
- B-07: Replay as epistemic archaeology
- B-08: WorldChronicle — Birth/Death/Aging/Succession
- B-09: Memetic Transmission Domain
- B-10: Content Policy Integration (per-NPC)
- B-11: Curiosity drive
- B-12: Goal Tree
- B-13: Abstract Reasoning Layer
- B-14: Inference Engine & Theory of Mind
- B-15: BodySchema — per-NPC геометрия тела

---

## §5. ПРИНЦИПЫ

1. Не строить параллельную архитектуру.
2. Не дублировать существующие компоненты.
3. LLM не принимает решения. Backend определяет meaning, LLM рендерит language.
4. §14 (единичное время), §15 (изоляция wall-clock), §16 (beliefs не мутируют L0) — ненарушаемы.
5. L-01..L-05 — костыли для MVP. B-09 (Memetic) + B-10 (Content Policy) — правильное решение. Костыли заменяются после MVP.
6. TZ_MEMETIC_03 Patch List (12 патчей, 8 новых файлов) — готов к реализации.
7. После §2 — пересмотр контракта v4.0.
