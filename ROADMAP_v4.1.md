# ENIGMA — Дорожная карта реализации
### Версия 4.1 | Март 2026 | Актуальная

---

## 📍 РЕАЛЬНОЕ СОСТОЯНИЕ ПРОЕКТА (проверено по коду)

```
✅ start_enigma.bat — полный запуск (LLM + Backend + Frontend)
✅ llama-server — Qwen3.5-9B, GPU_LAYERS=33, --n-predict 800
✅ FastAPI — стартует, /api/health отвечает
✅ JSONL логи — структурированы, ротация по дням
✅ VRAM Monitor — baseline fix, get_vram_budget(), is_safe_to_load()
✅ Error Interpreter — singleton, анализ LLM-ошибок, fix-рекомендации
✅ SSE Streaming — llama_cpp_provider.stream_tokens(), dm_agent.stream_narrate(), routes_stream.py
✅ Frontend Streaming — getReader(), fallback POST, счётчик tok/s, прогресс-бар, состояния
✅ Action Classifier — все 14 ActionType, приоритеты, get_required_agents()
✅ Physics Validator — правила мира, bypass через заклинания/способности
✅ Combat Math — полный D&D 5e: атака, урон, крит, инициатива, смерть, сетка, навыки, спасброски
✅ Sandbox Handler — 23 обработчика + TOP-100 нестандартных действий
✅ orchestrator.py — _run_python_engines() (Combat + Sandbox), PhysicsValidator, ActionClassifier
✅ dm_agent.py — читает python_engines контекст, формирует повествование
✅ context_builder.py — динамический сборщик контекста для LLM
✅ memory.py — LayeredMemory, JsonMemoryStore, JSONL backend с кэшем
✅ world_scheduler.py — WorldScheduler.maybe_tick() (базовый, вызывает world_agent.tick())
✅ model_router.py — ModelRouter, ModelPool, lazy loading, VRAM-aware priority

⚠️  campaign_state.json — current_location всё ещё "unknown" (не исправлено!)
⚠️  major_npcs.json — НЕ СУЩЕСТВУЕТ (заглушка {"name":"противник","ac":12} в orchestrator)
⚠️  NPC-движки (npc/) — папка НЕ СУЩЕСТВУЕТ (ThreatAssessor, PsycheEngine и др. не созданы)
⚠️  LifeEngine, KarmaEngine, SocialMobility, NPCGenerator — НЕ СУЩЕСТВУЮТ
⚠️  Мультиплеер — НЕ РЕАЛИЗОВАН (TurnManager отсутствует)
⚠️  Создание персонажа через DM-диалог — НЕ РЕАЛИЗОВАНО
⚠️  .exe файл — НЕ ГОТОВ (только заготовки в build/)
⚠️  RAG по PDF — базовые заготовки (pdf_drop_importer.py, knowledge_ingest.py), не работает
```

---

# ═══════════════════════════════════════════════════
# ФАЗА 0 — СТАБИЛИЗАЦИЯ (ПОЧТИ ГОТОВО)
# ═══════════════════════════════════════════════════

✅ start_llm.bat — GPU_LAYERS=33, --n-predict 800 — **СДЕЛАНО**
✅ llama_cpp_provider.py — max_tokens 800 — **СДЕЛАНО**
✅ dm_agent.py — читает context["python_engines"] — **СДЕЛАНО**

**Осталось:**
- [ ] `data/campaigns/demo-campaign/campaign_state.json` — исправить `"current_location": "unknown"` на реальное стартовое место (например `"tavern_silver_wolf"`)
- [ ] Убедиться что campaign_state_service.py возвращает current_location в ответах API

---

# ═══════════════════════════════════════════════════
# ФАЗА 1 — STREAMING И UI ✅ ГОТОВО
# ═══════════════════════════════════════════════════

**Всё реализовано:**
- `llama_cpp_provider.py` — `stream_complete()` + `stream_tokens()` (Generator)
- `dm_agent.py` — `stream_narrate()` (async generator)
- `routes_stream.py` — `POST /api/game/action/stream` (SSE формат: status → token → npc → done)
- `index.html` — `getReader()`, fallback POST, состояния (idle/thinking/streaming/done), tok/s счётчик, прогресс-бар

---

# ═══════════════════════════════════════════════════
# ФАЗА 2 — ACTION CLASSIFIER И PYTHON ДВИЖКИ ✅ ГОТОВО
# ═══════════════════════════════════════════════════

**Всё реализовано:**
- `action_classifier.py` — 14 ActionType, словари слов, приоритеты, `get_required_agents()`
- `physics_validator.py` — PhysicsValidator, правила мира, bypass через заклинания
- `combat_math.py` — полный D&D 5e: `attack_roll()`, `damage_roll()`, `skill_check()`, `saving_throw()`, `death_saving_throw()`, `CombatGrid`, `build_combat_context()`
- `sandbox_handler.py` — 23 обработчика (flee, capture, romance, intimidate, bribery...) + TOP-100
- `orchestrator.py` — `_run_python_engines()` интегрирован, передаёт результаты в DM-агента

---

# ═══════════════════════════════════════════════════
# ФАЗА 3A — NPC CORE PSYCHOLOGY ← ТЕКУЩАЯ ЗАДАЧА
# Срок: 2 недели | Приоритет: КРИТИЧЕСКИЙ
# ═══════════════════════════════════════════════════

> **Здесь остановились.** Папка `backend/app/services/npc/` не существует.
> Нужно создать с нуля. Это сердце проекта.

**Принцип:** Python считает психологию NPC (<50ms) → LLM только озвучивает результат.

---

## 3A.0. Данные NPC (ПЕРВЫЙ ШАГ — без него всё остальное бессмысленно)

**Создать:** `backend/data/npcs/major_npcs.json`

Минимальная структура для старта:

```json
[{
  "id": "tavern_keeper_tornin",
  "name": "Торнин Серебряная Луна",
  "tier": "major",
  "status_profile": {"freedom": 75, "wealth": 40, "power": 20, "title": "Хозяин таверны"},
  "visible_markers": ["apron", "keys", "heavy_build"],
  "hidden_truth": ["former_soldier", "owes_debt_to_thieves_guild"],
  "drives": {"control": 0.50, "significance": 0.25, "fear": 0.15, "desire": 0.10},
  "psyche": {"willpower": 65, "stress": 20, "breakpoint": 80,
              "loyalty_true": 60, "loyalty_fake": 60, "state": "free", "trauma_flags": []},
  "social_stats": {"trust": 0.60, "affection": 0.50, "fear_of_player": 0.05, "debt": 0},
  "relationships": {"player_default": 50},
  "routine": {"current": "cleaning_tables", "mood": "neutral", "interrupted": false,
               "schedule": {"06:00-22:00": "working", "22:00-06:00": "sleeping"}},
  "recent_events": [],
  "memory_trace": [],
  "flags": {"has_gold": true, "knows_secret": false, "is_dead": false},
  "location": "tavern_silver_wolf",
  "hp": 40, "max_hp": 40,
  "combat_stats": {"ac": 12, "attack_bonus": 2, "damage": "1d4+1"}
}]
```

- [ ] Создать `major_npcs.json` с 5 NPC: Торнин, Борко (стражник), Люся (служанка), Горан (купец), безымянный вор
- [ ] Создать `mass_npc_templates.json` — 10 шаблонов (горожанин, стражник, крестьянин, пьяный, монах, торговец, нищий, солдат, служанка, ребёнок)

---

## 3A.1. NPCCognition — 4 драйва + сборщик промпта

**Создать:** `backend/app/services/npc/npc_cognition.py`
**Создать:** `backend/app/services/npc/__init__.py`

```
4 драйва (сумма = 1.0):
control      → структурированно, планирует, контроль над ситуацией
significance → упоминает статус, обижается на неуважение
fear         → осторожен, задаёт уточняющие вопросы
desire       → любопытен, торгуется, готов рисковать
```

- [ ] `normalize_drives(drives: dict) -> dict` — нормализовать к сумме 1.0
- [ ] `get_dominant_drive(drives: dict) -> str` — ключ с макс. значением
- [ ] `get_speech_style(dominant_drive: str) -> str` — строка-подсказка для промпта
- [ ] `process_player_action(npc, action, player, threat_level) -> dict` — обновить trust/fear
- [ ] `build_npc_prompt(npc, player, context) -> str` — итоговый system prompt для NPC LLM
- [ ] `get_inner_thought(npc, context) -> str` — для Debug Mode (F12)

**Тест:** `backend/tests/test_npc_cognition.py`

---

## 3A.2. PsycheEngine — стресс и психологические состояния

**Создать:** `backend/app/services/npc/psyche_engine.py`

```
Состояния (state):
free       → нормальное
coerced    → под давлением, держится
broken     → воля сломлена (stress > breakpoint)
deceptive  → притворяется, планирует предательство
loyal      → искренняя преданность
```

- [ ] `apply_stress(npc, amount) -> dict` — stress += amount, проверить breakpoint
- [ ] `recover_stress(npc, ticks_safe) -> None` — -5/тик в безопасности, -15 во сне
- [ ] `resolve_coercion(npc, action_type, intensity) -> dict`:
  - action_type: "threat" | "bribe" | "charm" | "torture"
  - outcome: "submit" | "resist" | "accept_bribe" | "broken"
- [ ] `check_loyalty_break(npc) -> bool` — при state=broken и loyalty_true < -50
- [ ] `get_behavior_hint(npc) -> str` — строка для промпта:
  - broken + fear → "говорит дрожащим голосом, соглашается на всё"
  - deceptive + control → "спокоен снаружи, ищет возможность предать"
  - loyal + significance → "горд что помогает"
  - free + desire → "открыт, любопытен, торгуется"

**Тест:** `backend/tests/test_psyche_engine.py`

---

## 3A.3. ThreatAssessor — оценка угрозы от игрока

**Создать:** `backend/app/services/npc/threat_assessor.py`

- [ ] `assess_threat(player_markers, action_type, reputation) -> int` (0–100):
  - heavy_armor: +20, weapon_melee: +20, weapon_ranged: +15
  - combat_stance: +10, threatening_words: +30, known_kill: +20
  - friendly_posture: -20, unarmed: -10
  - репутация "cruel" → базовый уровень +10
- [ ] `get_threat_category(score) -> str` → LOW | MEDIUM | HIGH | CRITICAL
- [ ] HIGH: `apply_stress(npc, 20-40)`, `fear_of_player += 0.15`
- [ ] CRITICAL: проверить `breakpoint` → возможный слом

---

## 3A.4. PerceptionEngine — как NPC воспринимает игрока

**Создать:** `backend/app/services/npc/perception_engine.py`

- [ ] `assess_status(visible_markers) -> int` (0–100):
  - royal_crown: +50, noble_clothes: +30, guild_badge: +20, heavy_armor: +10
  - rags: -30, chains: -50, slave_collar: -60
- [ ] `get_status_label(score) -> str` → "нищий" | "простолюдин" | "уважаемый" | "благородный" | "правитель"
- [ ] `get_social_permissions(player_status, npc) -> list[str]`:
  - "demand", "threaten", "negotiate", "beg", "charm", "trade"
  - Раб НЕ может требовать — только просить
  - Дворянин может приказывать простолюдину

---

## 3A.5. Интеграция NPC движков в Orchestrator

**Файл:** `backend/app/services/orchestrator.py`

Расширить `_run_python_engines()` — добавить NPC-блок:

- [ ] Загружать NPC из `major_npcs.json` (кэшировать в RAM)
- [ ] Для каждого затронутого NPC в локации:
  1. `ThreatAssessor.assess_threat()` → threat_level
  2. `PerceptionEngine.assess_status()` → perceived_status
  3. `NPCCognition.process_player_action()` → изменения trust/fear
  4. `PsycheEngine.apply_stress()` → state, behavior_hint
  5. `NPCCognition.build_npc_prompt()` → system prompt для NPC агента
  6. `NPCCognition.get_inner_thought()` → для Debug Mode
- [ ] Заменить заглушку `{"name":"противник","ac":12}` на реальные NPC из `major_npcs.json`
- [ ] Сохранять обновлённое состояние NPC обратно в JSON после каждого хода

**Цели по производительности:**

| Движок | Цель |
|--------|------|
| ThreatAssessor | < 10ms |
| PerceptionEngine | < 15ms |
| PsycheEngine | < 10ms |
| NPCCognition.build_prompt | < 5ms |
| Итого NPC engines | < 50ms |

---

# ═══════════════════════════════════════════════════
# ФАЗА 3B — ЖИВОЙ МИР
# Срок: 2 недели | Приоритет: ВЫСОКИЙ
# ═══════════════════════════════════════════════════

> После 3A. NPC живут даже когда игрок не смотрит.

---

## 3B.1. LifeEngine — расписание и рутина

**Создать:** `backend/app/services/npc/life_engine.py`

```
Tier:
Major  → полная симуляция каждый тик
Minor  → расписание + случайные события
Mass   → только флаги, без симуляции
```

- [ ] `tick(world_state) -> None` — обновить Minor NPC в активных локациях + 10% рандомных
- [ ] `update_routine(npc, current_time) -> None` — сравнить с расписанием, сменить активность
- [ ] `get_activity_description(npc) -> str` — "Торнин протирает кружки за стойкой"
- [ ] `check_random_events(npc) -> None` — 5% шанс на тик:
  - Спор с другим NPC (-доверие между ними)
  - Потеря/находка предмета (±wealth)
  - Болезнь (stress +20 на N тиков)
  - Хорошая новость (stress -15)
- [ ] Хранить `recent_events` — последние 10, старые удалять
- [ ] `recover_stress_tick(npc) -> None` — -5/тик в безопасности, -15 во сне

**Интегрировать в** `world_scheduler.py` — расширить `maybe_tick()` чтобы вызывал `LifeEngine.tick()`

**Производительность:** CPU only, < 5% нагрузки, 0 VRAM.

---

## 3B.2. KarmaEngine — репутация и цепные реакции

**Создать:** `backend/app/services/npc/karma_engine.py`

```python
# Репутационные теги игрока в characters.json:
player.reputation = {
    "hero": 0,       # помощь, спасение
    "cruel": 0,      # убийства мирных
    "generous": 0,   # пожертвования
    "betrayer": 0,   # предательства
    "wise": 0        # решение конфликтов миром
}
player.faction_rep = {
    "стража_города": 0,
    "гильдия_воров": 0,
    "храм": 0
}
```

- [ ] `update_reputation(player, action_type, outcome) -> None`:
  - убийство мирного → cruel += 10
  - помощь в беде → hero += 5
  - щедрое пожертвование → generous += 10
  - предательство → betrayer += 15
- [ ] `get_reputation_summary(player) -> list[str]` — топ-3 активных тега
- [ ] Репутация "hero" → все NPC: trust baseline +0.05
- [ ] Репутация "cruel" → все NPC: fear_of_player baseline +0.10
- [ ] `schedule_delayed_event(trigger, delay_ticks, event_type) -> None`:
  - Угроза получена → через 5 тиков стражники ищут игрока
  - NPC сломан → через 10 тиков revenge_attempt
  - Помог деревне → через 3 тика положительный слух
- [ ] LifeEngine проверяет scheduled_events каждый тик

---

## 3B.3. SocialMobility — динамические роли NPC

**Создать:** `backend/app/services/npc/social_mobility.py`

- [ ] `check_role_change(npc, event) -> bool` — проверить условия смены роли
- [ ] Транзиции:
  - Захваченный: state="coerced", visible_markers += ["chains"]
  - Освобождённый: state="free", markers -= ["chains", "slave_collar"]
  - Разорился: wealth → 5, title = "Нищий"
  - Победил угрозу: power += 20, title = "Уважаемый"
- [ ] `update_title(npc) -> None` — автообновление на основе freedom + wealth + power
- [ ] `apply_coercion_pressure(npc, pressure_type) -> None`:
  - Виды: "threats", "torture", "isolation", "starvation"
  - stress += pressure_value
  - stress > breakpoint → state = "broken", loyalty_fake = +50, loyalty_true = -100

---

## 3B.4. NPCAutoGenerator — ленивая генерация NPC при первом контакте

**Создать:** `backend/app/services/npc/npc_generator.py`

```
Принцип Lazy Generation:
1. Игрок входит → шаблоны Mass NPC (0 VRAM, только флаги)
2. Игрок взаимодействует → генерируется полный JSON (drives, психология)
3. JSON сохраняется в data/npcs/generated/ (память навсегда)
```

- [ ] Шаблоны ролей (farmer, guard, merchant, priest, innkeeper, beggar, monk, soldier):
  - drives_preset, routine_schedule, common_beliefs, visible_markers
- [ ] `generate_npc(npc_id, role, location, culture, tier) -> dict` — полный NPC JSON
- [ ] Культурные модификаторы: peasant_village (fear +0.1), capital_city (significance +0.15)
- [ ] Случайные вариации ±10% от шаблона (для разнообразия)
- [ ] Кэш в RAM — не читать JSON каждый ход

---

# ═══════════════════════════════════════════════════
# ФАЗА 3C — СОЦИАЛЬНАЯ СЕТЬ И ПАМЯТЬ
# Срок: 2 недели | Приоритет: СРЕДНИЙ
# ═══════════════════════════════════════════════════

> После 3B. NPC слышат слухи, память выцветает, есть убеждения.

---

## 3C.1. MemoryWeighting — взвешивание и выцветание памяти NPC

**Создать:** `backend/app/services/npc/memory_weight.py`

```
Принцип выцветания:
Травма (вес 90+)          → не забывается никогда
Важное событие (50–89)    → -1/тик (медленно)
Обычное (< 50)            → -5/тик (быстро)
Вес = 0                   → удалить из memory_trace
```

Формат записи в memory_trace:
```json
{"event": "player_threatened_me", "weight": 85, "tick_added": 104, "emotional_charge": "fear"}
```

- [ ] `add_memory(npc, event, weight, emotional_charge) -> None`
- [ ] `decay_memories(npc, ticks_passed) -> None` — уменьшить веса, удалить нулевые
- [ ] `get_relevant_memories(npc, context_keywords) -> list` — топ-5 по весу + релевантности
- [ ] Использовать в `build_npc_prompt()` — только релевантные воспоминания

---

## 3C.2. RumorNetwork — сеть слухов

**Создать:** `backend/app/services/npc/rumor_network.py`

```
Принцип:
Действие → слух → распространяется по радиусу
Чем дальше NPC → тем слабее и искажённее слух
```

- [ ] `spread_rumor(event, origin_location, intensity) -> None`:
  - radius = intensity / 10 (локации)
  - Для NPC в радиусе: `add_memory(npc, rumor, weight=intensity - distance*5)`
  - intensity < 30 → слух может быть ложным
- [ ] `process_rumor(npc, rumor) -> None` — обновить drives и mood:
  - "дракон атаковал деревню" → fear += 0.05, stress += 20
  - "герой спас детей" → если игрок "hero": trust += 0.1
- [ ] Интегрировать в KarmaEngine — вызывать при значимых действиях игрока

---

## 3C.3. BeliefSystem — убеждения NPC

**Расширение** `major_npcs.json` и шаблонов:

```json
"beliefs": [
  {
    "id": "belief_magic",
    "content": "Магия реальна и опасна",
    "truth_value": true,
    "confidence": 90,
    "emotional_charge": "respect",
    "manipulation_triggers": ["демонстрация_магии", "ритуал"]
  }
]
```

- [ ] `find_exploitable_beliefs(npc, player_action) -> list` — уязвимые убеждения
- [ ] Угроза проклятием работает только если NPC верит в загробную жизнь
- [ ] `shake_belief(npc, belief_id, evidence_strength) -> None` — снизить confidence
- [ ] Добавлять релевантные убеждения в промпт при наличии триггеров

---

## 3C.4. InconsistencyDetector — проверка противоречий

**Создать:** `backend/app/services/npc/inconsistency_detector.py`

- [ ] `check_npc_state(npc, location, world_state) -> list[dict]`:
  - NPC мёртв но должен отвечать → ERROR
  - NPC в тюрьме но диалог на рынке → WARNING
  - NPC знает о смерти союзника → добавить в memory_trace
- [ ] Передавать inconsistencies в промпт DM-агента для коррекции

---

# ═══════════════════════════════════════════════════
# ФАЗА 3D — ПРОДВИНУТЫЕ ВЗАИМОДЕЙСТВИЯ
# Срок: 2–3 недели | Приоритет: СРЕДНИЙ
# Только после 3A–3C
# ═══════════════════════════════════════════════════

## 3D.1. ActionLayerEngine — 4 уровня реальности

**Создать:** `backend/app/services/npc/action_layer_engine.py`

```
PHYSICAL     → бой, перемещение, предметы (DC 15)
SOCIAL       → убеждение, запугивание, обман (DC 12)
LOGICAL      → изменение условий, тегов квеста (DC 18)
METAPHYSICAL → шок, абсурд, перезапись реальности (DC 20 или ниже при шоке)
```

- [ ] `classify_action(action_text, context) -> ActionLayer`
- [ ] `get_layer_difficulty(layer, npc) -> int` — DC с учётом shock_threshold

## 3D.2. ShockEngine — когнитивный диссонанс

**Создать:** `backend/app/services/npc/shock_engine.py`

- [ ] Поле `shock_threshold` в psyche (1–20): 1 = принимает всё, 20 = консерватор
- [ ] `calculate_shock(action_text, context, npc) -> int` (1–20)
- [ ] `apply_shock_effect(npc, shock_level) -> dict`:
  - shock > threshold → cognitive_state = "dissonance", accepts_explanation = True
  - shock > threshold-3 → cognitive_state = "confused"
- [ ] Хаотичные NPC (drives.chaos > 0.3) шокируются меньше

## 3D.3. DriveMatcher — триггеры манипуляции

**Создать:** `backend/app/services/npc/drive_matcher.py`

```json
"drive_triggers": {
  "control":       ["порядок", "план", "правила"],
  "significance":  ["лесть", "статус", "признание"],
  "fear":          ["угроза", "боль", "смерть"],
  "desire":        ["золото", "удовольствие", "азарт"]
}
```

- [ ] `find_triggered_drives(action_text, npc) -> list`
- [ ] `apply_drive_shift(npc, triggered_drive, roll_result) -> dict`:
  - roll 18+ → смена цели + trust +0.3
  - roll 15–17 → смена цели
  - roll 12–14 → частичное влияние + stress +5

---

# ═══════════════════════════════════════════════════
# ФАЗА 4 — ВСЕ 6 МОДЕЛЕЙ
# Срок: 1.5 недели | Приоритет: ВЫСОКИЙ
# ═══════════════════════════════════════════════════

> ModelPool и ModelRouter уже есть. Нужно подключить модели по назначению.

- [ ] Проверить что `npc_agent.py` реально использует NPC-7B (не DM-модель)
- [ ] `npc_mass_agent.py` — NPC Mass (IQ4, быстрый) — проверить что не fallback на DM
- [ ] `rules_agent.py` — Saiga 7B — тестировать проверку правил D&D
- [ ] `world_sim_agent.py` — Qwen 7B — тестировать генерацию событий мира
- [ ] `memory_manager_agent.py` — YandexGPT — тестировать суммаризацию на русском
- [ ] VRAM приоритет при давлении: DM > Rules > NPC Major > NPC Mass > World > Memory
- [ ] Логировать каждое переключение модели в JSONL

---

# ═══════════════════════════════════════════════════
# ФАЗА 5 — МУЛЬТИПЛЕЕР 1–8 ИГРОКОВ
# Срок: 2 недели | Приоритет: СРЕДНИЙ
# ═══════════════════════════════════════════════════

**Нового файла нет.** Нужно создать:

**Создать:** `backend/app/services/game/turn_manager.py`

- [ ] Очередь ходов: список активных игроков в сессии
- [ ] `next_turn() -> str` — передать ход, заблокировать ввод остальных
- [ ] Агрегировать одновременные заявки → один групповой ход
- [ ] DM агент получает все заявки вместе → один ответ на всех
- [ ] Если один игрок угрожает NPC → все игроки получают штраф к trust
- [ ] Если один помогает → бонус делится на группу

---

# ═══════════════════════════════════════════════════
# ФАЗА 6 — СОЗДАНИЕ ПЕРСОНАЖА ЧЕРЕЗ DM-ДИАЛОГ
# Срок: 1 неделя | Приоритет: СРЕДНИЙ
# ═══════════════════════════════════════════════════

> character_service.py есть, но DM-диалог для создания не реализован.

**Создать:** `backend/app/services/game/character_creation.py`

- [ ] Пошаговый диалог: раса → класс → предыстория → характеристики → имя
- [ ] Python считает характеристики: 4d6 drop lowest ИЛИ стандартный массив
- [ ] DM агент ведёт диалог, Python записывает в `characters.json`
- [ ] Начальные `visible_markers` по классу: fighter → heavy_armor, rogue → dark_cloak, wizard → robes

---

# ═══════════════════════════════════════════════════
# ФАЗА 7 — СИСТЕМА ПАМЯТИ
# Срок: 2 недели | Приоритет: ВЫСОКИЙ
# ═══════════════════════════════════════════════════

> `memory.py` с LayeredMemory и JsonMemoryStore уже есть. Расширить.

```
Level 1: Immediate  — текущий ход (ephemeral, не сохраняется)
Level 2: Session    — текущая сессия (~50 событий, JSONL)
Level 3: Campaign   — долгосрочная кампания (приоритизированные факты)
Level 4: Knowledge  — правила D&D из PDF (RAG, отдельная фаза)
```

- [ ] `memory_manager.py` — бюджет токенов контекста (всегда < 4096 токенов)
- [ ] Триггер суммаризации: session_memory > 30 событий → запустить memory_manager_agent
- [ ] YandexGPT суммаризирует старые события на русском
- [ ] Сохранять summary в Level 3 с тегом `priority: high`
- [ ] `knowledge_base.py` — ChromaDB / FAISS для PDF (Level 4, поиск < 200ms)

---

# ═══════════════════════════════════════════════════
# ФАЗА 4.5 — ЭПИЗОДИЧЕСКАЯ КАМПАНИЯ
# Срок: 3 недели | Приоритет: СРЕДНИЙ
# После фаз 3A–3C и 7
# ═══════════════════════════════════════════════════

**Создать:**

- [ ] `backend/services/mission_state_manager.py` — жизненный цикл миссий (pending → active → completed → archived)
- [ ] `backend/services/context_archiver.py` — key_facts из завершённых миссий, контекст < 4096 токенов
- [ ] `backend/services/downtime_engine.py` — мир между сессиями: NPC через LifeEngine, фракции по репутации, случайные события
- [ ] `backend/services/foreshadowing_system.py` — крючки из завершённых миссий всплывают в новых (частота 30%)

---

# ═══════════════════════════════════════════════════
# ФАЗА 8 — АНАЛИТИКА
# Срок: 1 неделя | Приоритет: НИЗКИЙ
# ═══════════════════════════════════════════════════

- [ ] `backend/app/services/analytics/player_stats.py` — kills, gold, урон, репутация, нестандартные действия
- [ ] `session_summary() -> dict` — итоги сессии
- [ ] Экран итогов в `index.html` после сессии

---

# ═══════════════════════════════════════════════════
# ФАЗА 9 — WORLD SIMULATOR (РАСШИРЕНИЕ)
# Срок: 1.5 недели | Приоритет: СРЕДНИЙ
# ═══════════════════════════════════════════════════

> `world_scheduler.py` и `world_sim_agent.py` существуют, но базовые.

- [ ] Расширить `WorldScheduler.maybe_tick()` — вызывать `LifeEngine.tick()` + `RumorNetwork.spread()`
- [ ] Политические события, торговые маршруты, природные явления через `world_sim_agent`
- [ ] Передача world_events в `RumorNetwork` для распространения слухов

---

# ═══════════════════════════════════════════════════
# ФАЗА 10 — RAG ПО PDF
# Срок: 2 недели | Приоритет: СРЕДНИЙ
# ═══════════════════════════════════════════════════

> `pdf_drop_importer.py` и `knowledge_ingest.py` существуют, но не работают end-to-end.

- [ ] Настроить ChromaDB / FAISS для хранения эмбеддингов D&D 5e книг
- [ ] Генерация при первом запуске, кэш в индексе (не пересчитывать)
- [ ] `knowledge_base.py` — поиск правил (< 200ms, offline-first)
- [ ] Rules агент использует RAG для точных ответов по механике

---

# ═══════════════════════════════════════════════════
# ФАЗА 11 — .EXE ФАЙЛ
# Срок: 2 недели | Приоритет: НИЗКИЙ
# ═══════════════════════════════════════════════════

> build/ существует с заготовками PyInstaller.

- [ ] `launcher.py` — PyInstaller + pywebview
- [ ] Экран загрузки пока llama-server стартует (10–30 сек)
- [ ] `enigma.spec` — backend + frontend, без моделей (слишком большие)
- [ ] Debug Panel F12 — VRAM, агенты, NPC состояния, токены
- [ ] Inner Thought toggle для NPC (только в Debug Mode)

---

# ═══════════════════════════════════════════════════
# ФАЗА 12 — ПОЛНЫЕ ПРАВИЛА D&D 5e
# Срок: 3–4 недели | Приоритет: НИЗКИЙ
# ═══════════════════════════════════════════════════

> `combat_math.py` уже включает навыки и спасброски. Добавить:

- [ ] `spell_system.py` — все заклинания PHB, ячейки, разрешение, концентрация
- [ ] Условия (stunned, paralyzed, poisoned, etc.) — влияние на бой и NPC
- [ ] Длинный/короткий отдых — восстановление ресурсов

---

# ═══════════════════════════════════════════════════
# ВНУТРЕННИЕ СТАНДАРТЫ (параллельно)
# ═══════════════════════════════════════════════════

## A. Кодировка и Windows ✅ (в основном)
- [x] `chcp 65001` в BAT файлах
- [ ] Все новые файлы — `# -*- coding: utf-8 -*-` первой строкой
- [ ] Пути через `Path`, не конкатенацию строк

## B. Логирование ✅ (в основном)
- [x] JSONL с timestamp — реализовано
- [x] Error Interpreter — реализован
- [ ] NPC state changes → JSONL
- [ ] Rotation: старые > 7 дней → удалять

## C. Тестирование

| Тест | После фазы | Статус |
|------|-----------|--------|
| `test_action_classifier.py` | 2 | ❌ нет |
| `test_combat_math.py` | 2 | ❌ нет |
| `test_npc_cognition.py` | 3A | ❌ нет |
| `test_psyche_engine.py` | 3A | ❌ нет |
| `test_life_engine.py` | 3B | ❌ нет |
| `test_karma_engine.py` | 3B | ❌ нет |
| `test_rumor_network.py` | 3C | ❌ нет |
| `test_memory_weight.py` | 3C | ❌ нет |
| `test_turn_manager.py` | 5 | ❌ нет |
| `test_memory_manager.py` | 7 | ❌ нет |

## D. Оптимизация

- [ ] Кэш NPC в RAM — не читать JSON каждый ход
- [ ] Профилировать время каждого NPC-движка
- [ ] Цель: все Python engines < 50ms суммарно
- [ ] VRAM leak < 100MB за 10 часов

---

# ═══════════════════════════════════════════════════
# ИТОГОВЫЙ ПЛАН ПО СРОКАМ
# ═══════════════════════════════════════════════════

| Фаза | Название | Срок | Статус |
|------|----------|------|--------|
| **0** | Стабилизация | — | ✅ 95% (current_location) |
| **1** | Streaming + UI | — | ✅ ГОТОВО |
| **2** | Action Classifier + Python движки | — | ✅ ГОТОВО |
| **3A** | NPC Core Psychology | **2 нед** | ⬅️ ТЕКУЩАЯ ЗАДАЧА |
| **3B** | Living World | **2 нед** | ❌ |
| **3C** | Социальная сеть + память | **2 нед** | ❌ |
| **4** | Все 6 моделей | **1.5 нед** | ⚠️ Частично |
| **5** | Мультиплеер | **2 нед** | ❌ |
| **6** | Создание персонажа | **1 нед** | ❌ |
| **7** | Система памяти | **2 нед** | ⚠️ Частично |
| **3D** | Продвинутые взаимодействия | **2–3 нед** | ❌ |
| **4.5** | Эпизодическая кампания | **3 нед** | ❌ |
| **8** | Аналитика | **1 нед** | ❌ |
| **9** | World Simulator (расширение) | **1.5 нед** | ⚠️ Базово |
| **10** | RAG по PDF | **2 нед** | ⚠️ Заготовки |
| **11** | .EXE файл | **2 нед** | ❌ |
| **12** | Полные правила D&D | **3–4 нед** | ⚠️ Частично |

**До v1.0-playable (0–3B + 4):** ~2.5 месяца
**До полного релиза:** ~6 месяцев

---

## 🏆 v1.0-playable — критерии готовности

```
✅ Игра запускается одним .bat без ошибок
✅ LLM отвечает стримингом, первый токен < 1 сек
✅ Бой считается математически верно (D&D 5e)
✅ Любое действие обрабатывается (SandboxHandler)
[ ] NPC имеют психологию: drives, stress, states (Фаза 3A)
[ ] NPC помнят действия игрока (memory_trace + decay)
[ ] NPC живут по расписанию (LifeEngine, Фаза 3B)
[ ] Репутация имеет последствия (KarmaEngine, Фаза 3B)
[ ] 1–4 игрока могут играть по очереди (Фаза 5)
[ ] Персонаж создаётся через диалог с DM (Фаза 6)
[ ] Смерть не конец игры (DeathHandler)
[ ] Локация и время мира работают корректно (current_location fix)
```

---

## 📌 Принципы которые никогда не нарушаем

1. **Python считает, LLM рассказывает** — ни один LLM не принимает игровых решений
2. **max_loaded = 1** — одна модель в VRAM, строго (8GB аксиома)
3. **Нет запрещённых действий** — есть последствия
4. **JSON файлы = источник истины** — LLM не меняет напрямую
5. **Мир живёт** — NPC движутся без участия игрока
6. **Честность бросков** — все кубики логируются в JSONL
7. **Windows 11 + русский** — тестировать каждую фичу на реальном железе
8. **Контекст < 4096 токенов** — всегда

---

## 🗺️ Схема зависимостей NPC систем (Фаза 3)

```
major_npcs.json + mass_npc_templates.json
             ↓
NPCAutoGenerator ──────────── (3B.4)
             ↓
     ┌───────────────────────────────────────┐
     │           ФАЗА 3A (фундамент)         │
     │                                       │
     │  ThreatAssessor ──→ PsycheEngine      │
     │  PerceptionEngine ──→ NPCCognition    │
     │                         ↓             │
     │              build_npc_prompt()       │
     │              get_inner_thought()      │
     └───────────────────────────────────────┘
                          ↓
              [NPC LLM Agent] ← готовый промпт
                          ↓
                [Ответ NPC игроку]

Параллельно (Фаза 3B, фоном):
LifeEngine ──────── routine, mood, recent_events
KarmaEngine ─────── reputation, delayed_events, faction_rep
RumorNetwork ─────── memory_trace (слухи)
SocialMobility ───── role_change, title_update

Расширение (Фаза 3C):
MemoryWeighting ──── decay, relevance-sorting
BeliefSystem ───────── exploitable beliefs
InconsistencyDetector ── state validation
```

---

**Документ:** ENIGMA ROADMAP v4.1
**Обновлено:** Март 2026 (на основе анализа кода проекта)
**Статус:** Готово к реализации Фазы 3A

> **Следующий шаг:** Создать `backend/app/services/npc/` и `backend/data/npcs/major_npcs.json`
