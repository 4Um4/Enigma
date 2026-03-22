# ENIGMA — Дорожная карта реализации
### Версия 5.1 | Март 2026 | Актуальная

> **Что изменилось vs v5.0:**
> Отражён реальный прогресс за март 2026.
> Фазы 3A, S, M — завершены. Gemma-3-12B основная модель.
> Добавлен S.4.1 как ближайший шаг.

---

## РЕАЛЬНОЕ СОСТОЯНИЕ ПРОЕКТА (Март 2026)

```
ЗАВЕРШЕНО:
✅ start_enigma.bat — полный запуск
✅ Gemma-3-12B-IT-Q4_K_M — основная модель, все агенты, ctx=2048, ngl=33
✅ FastAPI, SSE Streaming, Frontend
✅ ActionClassifier, PhysicsValidator, CombatMath, SandboxHandler
✅ orchestrator.py — NPC блок + SceneState + recent_session
✅ dm_agent.py — SceneState первым блоком, npc_actions, фильтр Gemma токенов
✅ npc_agent.py — _resolve_active_npcs, JSON парсинг, _strip_stop_tokens
✅ npc_cognition.py — _get_physical_state(), физические факты
✅ major_npcs.json — 5 NPC с психологией, gender, description
✅ mass_npc_templates.json — 10 шаблонов
✅ scene_state_manager.py — SceneStateManager, 7 методов
✅ scene_change.py — SceneChange, ChangeType (10 типов), ChangeValidator
✅ location_templates.json — 5 локаций с time_variants
✅ routes_stream.py — SceneState + recent_session
✅ Promt_AI.json — на русском, подключён к dm_agent
✅ config.py, router.py — gemma_12b первая для всех

НЕ РЕАЛИЗОВАНО:
⚠️  S.4.1: SandboxHandler не генерирует SceneChange (действия не меняют SceneState)
⚠️  LifeEngine, KarmaEngine, SocialMobility, NPCAutoGenerator (фаза 3B)
⚠️  MemoryWeighting, RumorNetwork, BeliefSystem (фаза 3C)
⚠️  PyGame UI (фаза UI)
⚠️  Мультиплеер (фаза 5)
⚠️  Создание персонажа через DM (фаза 6)
⚠️  RAG по PDF (фаза 10)
```

---

## ЗАВЕРШЁННЫЕ ФАЗЫ

| Фаза | Ключевой результат |
|------|-------------------|
| 0 | Стабильный запуск |
| 1 | SSE стриминг токенов |
| 2 | ActionClassifier, PhysicsValidator, CombatMath, SandboxHandler |
| 3A | NPC психология, физические состояния, JSON парсинг |
| S | SceneStateManager, SceneChange, location_templates |
| M | Gemma-3-12B вместо 5 слабых 7B |

---

## ФАЗА S.4.1 — SANDBOX → SCENESTATE (СЛЕДУЮЩИЙ ШАГ)
### Срок: 2–3 дня | Приоритет: ВЫСОКИЙ

SceneStateManager работает, но действия игрока не попадают в SceneState.
Украл свечи? SceneState не знает. Сломал стол? SceneState не знает.

**Файл:** `backend/app/services/game/sandbox_handler.py`

- [ ] Добавить `scene_changes: list = []` в `SandboxResult`
- [ ] Для 10 типов действий генерировать SceneChange при success=True:
  - STEAL → OBJECT_REMOVE цели + INVENTORY add игроку
  - BREAK/DESTROY → OBJECT_STATE target = "damaged"/"broken"
  - LOCKPICK (успех) → OBJECT_STATE door = "open"
  - CAPTURE → NPC_STATE target = "captured"
  - BRIBERY → INVENTORY remove gold
  - INTIMIDATE → NPC_POSITION activity = "retreating"
  - POISON → NPC_STATE target += "poisoned"
  - ENVIRONMENTAL → EFFECT_ADD "fire_on_{target}"
- [ ] В `orchestrator._run_python_engines()`: применять scene_changes через
  `self.scene_manager.apply_changes()`
- [ ] Тест: украсть свечи → следующий ход DM описывает темноту

---

## ФАЗА 3B — ЖИВОЙ МИР
### Срок: 2 недели | Приоритет: ВЫСОКИЙ | После S.4.1

LifeEngine двигает NPC по расписанию и пишет SceneChange в SceneState.
Торнин уйдёт спать в 22:00. Рынок откроется в 09:00.
Мир живёт без участия игрока — каждые 15 минут (WorldScheduler тик).

### 3B.1 — LifeEngine

**Создать:** `backend/app/services/npc/life_engine.py`

```
Tier:
Major → полная симуляция каждый тик
Minor → расписание + случайные события раз в 3 тика
Mass  → только флаги присутствия (0ms)
```

- [ ] `tick(campaign_id) -> list[SceneChange]`
- [ ] `update_routine(npc, current_time) -> SceneChange` — позиция по расписанию
- [ ] `get_activity_description(npc) -> str`
- [ ] `check_random_events(npc) -> list[SceneChange]` — 5% шанс
- [ ] `recover_stress_tick(npc) -> None` — -5/тик безопасности, -15 сон
- [ ] Интеграция: `world_scheduler.maybe_tick()` → `LifeEngine.tick()` → `apply_changes()`

### 3B.2 — KarmaEngine

**Создать:** `backend/app/services/npc/karma_engine.py`

- [ ] `update_reputation(player, action_type, outcome)`
- [ ] "hero" → trust +0.05 всем NPC; "cruel" → fear +0.10
- [ ] `schedule_delayed_event(trigger, delay_ticks, event_type)`

### 3B.3 — SocialMobility

**Создать:** `backend/app/services/npc/social_mobility.py`

- [ ] Захват → NPC state="coerced", SceneChange добавляет "chains"
- [ ] Освобождение → убирает "chains"

### 3B.4 — NPCAutoGenerator

**Создать:** `backend/app/services/npc/npc_generator.py`

- [ ] Lazy generation из mass_npc_templates.json (файл уже есть)
- [ ] Сохранение в `data/npcs/generated/`

### Критерии готовности 3B

```
[ ] Торнин уходит спать в 22:00 — SceneState фиксирует
[ ] Игрок приходит в 23:00 — DM сообщает что Торнина нет
[ ] Рынок закрыт ночью — SceneState merchant_stalls state="closed"
[ ] Mass NPC создаются при первом контакте
[ ] test_life_engine.py, test_karma_engine.py — зелёные
```

---

## ФАЗА UI — ПЕРЕХОД НА PYGAME
### Срок: 2–3 недели | Параллельно с 3B

index.html не разделяет каналы — JSON торчит в реакциях.
PyGame: DM нарратив и NPC речь в отдельных панелях.

### Архитектура

```
Enigma/ui/
├── launcher.py       ← точка входа
├── game_window.py    ← главное окно
├── api_client.py     ← SSE клиент
└── panels/
    ├── narrative.py  ← DM нарратив (стриминг)
    ├── dialogue.py   ← NPC [Имя] "речь"
    ← status.py      ← локация | время | HP
    ├── input.py      ← ввод + Enter
    └── debug.py      ← F12: NPC trust/stress/inner_thought
```

### Layout

```
┌─────────────────────────────────────────────────────┐
│ ENIGMA          Таверна «Серебряный Волк» | 22:00   │
├──────────────────────────┬──────────────────────────┤
│  DM НАРРАТИВ             │  ДИАЛОГИ NPC             │
│  (стриминг)              │  [Торнин] "Деньги..."    │
│                          │  [Люся]   "Что угодно?"  │
├──────────────────────────┴──────────────────────────┤
│  > Ваше действие...                      [▶ Ответ] │
└─────────────────────────────────────────────────────┘
```

### Шаги

- [ ] `pip install pygame`
- [ ] `ui/launcher.py`, `ui/api_client.py`
- [ ] 5 панелей
- [ ] `routes_stream.py`: добавить `type: "npc"` события и `scene_state` в `done`
- [ ] `start_enigma.bat` → launcher.py вместо браузера
- [ ] index.html оставить как fallback

---

## ФАЗА 3C — СОЦИАЛЬНАЯ СЕТЬ И ПАМЯТЬ
### Срок: 2 недели | После 3B

- [ ] `memory_weight.py` — MemoryWeighting, decay, relevance
- [ ] `rumor_network.py` — слухи по радиусу, искажение
- [ ] BeliefSystem — убеждения NPC, триггеры манипуляции
- [ ] InconsistencyDetector — NPC не может быть в двух местах

---

## ФАЗА 3D — ПРОДВИНУТЫЕ ВЗАИМОДЕЙСТВИЯ
### Срок: 2–3 недели | После 3A–3C

- [ ] ActionLayerEngine — 4 уровня (PHYSICAL / SOCIAL / LOGICAL / METAPHYSICAL)
- [ ] ShockEngine — когнитивный диссонанс
- [ ] DriveMatcher — триггеры манипуляции через drives

---

## ФАЗА 5 — МУЛЬТИПЛЕЕР
### Срок: 2 недели

- [ ] `turn_manager.py` — очередь 1–8 игроков
- [ ] В PyGame: чья очередь, кнопка передать ход

---

## ФАЗА 6 — СОЗДАНИЕ ПЕРСОНАЖА
### Срок: 1 неделя

- [ ] `character_creation.py` — диалог DM: раса → класс → предыстория → характеристики
- [ ] SceneState создаётся после выбора стартовой локации

---

## ФАЗА 7 — СИСТЕМА ПАМЯТИ
### Срок: 2 недели

- [ ] `memory_manager.py` — бюджет токенов < 4096
- [ ] Суммаризация через Gemma-12B
- [ ] `knowledge_base.py` — ChromaDB / FAISS

---

## ФАЗА 4.5 — ЭПИЗОДИЧЕСКАЯ КАМПАНИЯ
### Срок: 3 недели | После 3A–3C и 7

- [ ] mission_state_manager, context_archiver, downtime_engine, foreshadowing_system

---

## ФАЗЫ 8–12 (низкий приоритет)

| Фаза | Название | Срок |
|------|----------|------|
| 8 | Аналитика | 1 нед |
| 9 | World Simulator расширение | 1.5 нед |
| 10 | RAG по PDF | 2 нед |
| 11 | Дистрибуция (.exe/PyGame) | 2 нед |
| 12 | Полные правила D&D | 3–4 нед |

---

## ИТОГОВЫЙ ПЛАН

| Фаза | Срок | Статус |
|------|------|--------|
| 0–M | — | ✅ ГОТОВО |
| S.4.1 | 2–3 дня | ⬅️ СЛЕДУЮЩИЙ |
| 3B | 2 нед | ❌ |
| UI | 2–3 нед (параллельно) | ❌ |
| 3C | 2 нед | ❌ |
| 3D | 2–3 нед | ❌ |
| 5 | 2 нед | ❌ |
| 6 | 1 нед | ❌ |
| 7 | 2 нед | ⚠️ частично |
| 4.5 | 3 нед | ❌ |
| 8–12 | — | ❌/⚠️ |

**До играбельной v1.0 (S.4.1 + 3B + UI):** ~5–6 недель
**До v1.0 полной (3A–3C + UI + 5 + 6 + 7):** ~3.5 месяца
**До релиза:** ~7 месяцев

---

## ПРИНЦИПЫ (финальные)

1. Python считает, LLM рассказывает
2. Python — единственный источник истины о мире
3. LLM предлагает изменения (SceneChange), Python утверждает
4. max_loaded = 1 — одна модель в VRAM
5. Нет запрещённых действий — есть последствия в SceneState
6. JSON файлы = источник истины
7. Мир живёт — LifeEngine меняет SceneState без LLM
8. Честность бросков — все кубики в JSONL
9. Windows 11 + русский — тестировать на железе
10. Контекст < 4096 токенов всегда

---

**Документ:** ENIGMA ROADMAP v5.1
**Обновлено:** Март 2026
**Следующий шаг:** Фаза S.4.1 — SandboxHandler генерирует SceneChange
