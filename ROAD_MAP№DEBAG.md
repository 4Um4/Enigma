```text
================================================================================
                        ENIGMA: ДОРОЖНАЯ КАРТА И АРХИТЕКТУРА (v2.0)
================================================================================

┌──────────────────────────────────────────────────────────────────────────────┐
│                         1. ЧТО УЖЕ СДЕЛАНО                                   │
└──────────────────────────────────────────────────────────────────────────────┘

██ ФАЗА 1 — ЗАКРЫТИЕ КОНТУРА [ЗАВЕРШЕНА]
════════════════════════════════════════════════════════════════════════════════
  ├─ 1.1 Убрать npc_agent из MAJOR сценариев ✅
  ├─ 1.3 Запретить TEXT→ENTITY (NarrativeExtractor.new_objects заблокирован) ✅
  └─ LifeEngine data-driven (activity_map вынесен в JSON) ✅

██ АУДИТ РЕАЛЬНОСТИ (ТЕХНИЧЕСКИЙ ДОЛГ И БАГИ)
════════════════════════════════════════════════════════════════════════════════
  ├─ R5 Resolution: нет бросков для физических действий ❌ [КРИТИЧНО]
  │     Лог: "пытаюсь взять меч" → нет провала, DM описывает попытку
  │     Корень: Router не классифицирует "пытаться" как INTENT_PHYSICAL
  ├─ R8 Break System: жёсткий override намерений ⚠️ [КРИТИЧНО]
  │     Корень: Маска COLLAPSE принудительно ставит IDLE, ломая Utility AI
  ├─ AsyncIO: World Sim Agent error ⚠️ [КРИТИЧНО]
  │     Корень: Semaphore bound to different event loop
  ├─ R4 PerceptionFilter: distance >= 5.0 не фильтрует ❌
  ├─ R2 DecisionHub: player_interacts → intent=flee ❌
  ├─ R8 Stability: не сбрасывается при смене сессии (SESSION_REPLACED) ⚠️
  └─ B.3 Continuity: events дублируются (нет дедупликации) ⚠️


┌──────────────────────────────────────────────────────────────────────────────┐
│             2. ИТЕРАТИВНЫЙ ПЛАН РАЗРАБОТКИ (СТРОГИЙ ПОРЯДОК)                 │
└──────────────────────────────────────────────────────────────────────────────┘
ПРИНЦИП: Каждая итерация завершается рабочим билдом. Никакого кода "в стол".

██ ИТЕРАЦИЯ 1 — ВОССТАНОВЛЕНИЕ ИНВАРИАНТОВ И HOTFIXES [БЛОКИРУЮЩИЙ ПРИОРИТЕТ]
════════════════════════════════════════════════════════════════════════════════
  [DoD - Definition of Done]: 
  - Игра запускается без AsyncIO ошибок.
  - Физические действия игрока обрабатываются кубиками (Rules Agent), а не фантазией LLM.
  - Слом воли NPC работает через веса (DecisionHub), а не через жесткую подмену (override).
  - Сессии сбрасываются чисто, NPC не реагирует на события вне радиуса 15м.

  ├─ 1.1 AsyncIO & Infrastructure Fix
  │     └─ Исправить инициализацию world_sim_agent (привязка к текущему event loop).
  ├─ 1.2 R5 Router & Physical Actions (Защита Инварианта)
  │     ├─ dm_router.py: Жесткое разделение INTENT_VERBAL и INTENT_PHYSICAL.
  │     └─ Интеграция: Любой INTENT_PHYSICAL обязан проходить через rules_agent (бросок кубиков) ДО StateApplicator.
  ├─ 1.3 R8 Break System Refactoring (Возврат к Utility AI)
  │     ├─ Убрать жесткий override (COLLAPSE → IDLE) из behavior_mask.py.
  │     └─ Внедрить mask_modifier: маска умножает веса (напр. FLEE * 3.0, ATTACK * 0.0). DecisionHub сам выбирает действие.
  └─ 1.4 State & Perception Hotfixes
        ├─ perception_filter.py: Добавить жесткий cap distance < 15.0m.
        ├─ emotion_map.json: player_interacts → neutral_tag.
        └─ player_session_service.py: Полный сброс stability и emotion_tag при SESSION_REPLACED.

██ ИТЕРАЦИЯ 2 — ФАЗА 2.0: CHARACTER FILTER (ПОЭТАПНОЕ ВНЕДРЕНИЕ)
════════════════════════════════════════════════════════════════════════════════
  [DoD - Definition of Done]: 
  - Слой CharacterFilter встроен в пайплайн между Router и DecisionHub.
  - NPC способен отказать (REFUSE) игроку на основе своих ценностей (self_integrity), не ломая Data Flow.

  ├─ 2.1 Stub Integration (Pass-through)
  │     ├─ Создать character_filter.py.
  │     ├─ Встроить в пайплайн: PlayerIntent → CharacterFilter → FilteredAction.
  │     └─ На этом этапе фильтр всегда возвращает ACCEPT. Билд работает.
  ├─ 2.2 REFUSE Logic (Базовое сопротивление)
  │     ├─ Добавить проверку self_integrity vs value_conflict.
  │     └─ Если конфликт критический → REFUSE (отказ от выполнения действия игрока).
  └─ 2.3 RESIST & MODIFY Logic (Мягкое сопротивление)
        └─ Реализовать ослабление действий (MODIFY) и добавление последствий (RESIST).

██ ИТЕРАЦИЯ 3 — СЕМАНТИЧЕСКАЯ КОМПРЕССИЯ И ЗАЩИТА ПАМЯТИ
════════════════════════════════════════════════════════════════════════════════
  [DoD - Definition of Done]: 
  - 50+ ходов в одной сессии не приводят к переполнению контекста LLM.
  - Дубликаты событий отсекаются. Старые события сжимаются в summary.

  ├─ 3.1 Event Deduplication
  │     └─ scene_continuity.py: Дедупликация в add_event по (event_type + target).
  ├─ 3.2 Importance Threshold (Фильтр мусора)
  │     └─ Внедрить порог важности: микро-события (почесал нос) не пишутся в L2 Event Memory, если importance < 0.3.
  └─ 3.3 Summary Compression
        ├─ memory_core.py: Динамический working_memory_cap (20 событий).
        └─ При превышении лимита → LLM сжимает старые события в summary_node.

██ ИТЕРАЦИЯ 4 — ФАЗА 3: ПРОАКТИВНОСТЬ (AGENDA LOOP)
════════════════════════════════════════════════════════════════════════════════
  [DoD - Definition of Done]: 
  - NPC инициирует действия (смена позы, реплика), если игрок бездействует.
  - Контекст не засоряется микро-тиками благодаря LOD (Level of Detail).

  ├─ 4.1 World Tick & LOD
  │     ├─ game_loop.py: Глобальный таймер (World Tick).
  │     └─ LOD: Тик обрабатывается полноценно только для NPC в радиусе 5м от игрока.
  ├─ 4.2 Spatial Events
  │     └─ Генерация event_type="proximity_close" и "proximity_leave" на основе изменения дистанции.
  └─ 4.3 Proactive Intents
        └─ Добавить в DecisionHub намерения: IDLE_ANIMATION, WANDER, INITIATE_CONVERSATION.

██ ИТЕРАЦИЯ 5 — ФАЗА 4: СОЦИАЛЬНАЯ ДИНАМИКА И ДАВЛЕНИЕ МИРА
════════════════════════════════════════════════════════════════════════════════
  [DoD - Definition of Done]: 
  - NPC реагируют на действия игрока с другими NPC (ревность, слухи).
  - NPC формируют "Фасады" (Fronts) для защиты от давления.

  ├─ 5.1 Social Graph & Rumors
  │     ├─ social_engine.py: Матрица отношений NPC-NPC.
  │     └─ Распространение слухов (передача summary_node с пониженным Confidence).
  ├─ 5.2 Fronts (Фасады)
  │     └─ Маски, которые NPC носит для мира (зависит от Social Propagation).
  └─ 5.3 Identity Erosion
        └─ Деградация self_integrity при частом использовании RESIST/MODIFY (из Итерации 2).


┌──────────────────────────────────────────────────────────────────────────────┐
│           3. АРХИТЕКТУРА ПРОЕКТА (РЕАЛЬНОСТЬ + ОБНОВЛЕННЫЙ ПЛАН)             │
└──────────────────────────────────────────────────────────────────────────────┘

enigma/
│
├── backend/
│   ├── app/
│   │   ├── main.py                     # FastAPI + startup
│   │   ├── api/                        # ТРАНСПОРТНЫЙ СЛОЙ
│   │   │
│   │   ├── models/                     # ЧИСТЫЕ ДАННЫЕ
│   │   │   ├── npc_state.py            # NPCState (динамика)
│   │   │   ├── decision.py             # Контракт DecisionResult
│   │   │   └── psychological.py        # ✅ DistortionProfile, CausalEntry
│   │   │
│   │   ├── agents/                     # LLM-агенты
│   │   │   ├── dm_agent.py             # Вербализатор
│   │   │   ├── rules_agent.py          # ⚠️ ОБЯЗАТЕЛЕН ДЛЯ ФИЗИКИ (Итерация 1)
│   │   │   └── world_sim_agent.py      # ⚠️ ТРЕБУЕТ ФИКСА ASYNCIO (Итерация 1)
│   │   │
│   │   └── services/                   # ЯДРО ЛОГИКИ
│   │       │
│   │       ├── character/              # 🆕 УРОВЕНЬ 2 — ПЕРСОНАЖ (Итерация 2)
│   │       │   ├── character_filter.py # PlayerIntent → FilteredAction
│   │       │   └── character_profile.py# self_integrity, values
│   │       │
│   │       ├── game_loop.py            # ★ КООРДИНАТОР ТАЙМИНГА (World Tick)
│   │       │
│   │       ├── action/                 # ★★★ DM SYSTEM (Парсинг и Роутинг)
│   │       │   ├── dm_orchestrator.py  
│   │       │   ├── dm_router.py        # ⚠️ ТРЕБУЕТ РАЗДЕЛЕНИЯ VERBAL/PHYSICAL
│   │       │   └── dm_scene_builder.py 
│   │       │
│   │       ├── npc/                    # ЯДРО ИНТЕЛЛЕКТА
│   │       │   ├── decision_hub.py     # [ЦЕНТР] Формула score()
│   │       │   ├── state_applicator.py # [ТОЧКА ЗАПИСИ] CausalLedger
│   │       │   ├── cognitive_distortion.py
│   │       │   ├── perception_filter.py# ⚠️ ТРЕБУЕТ CAP 15m
│   │       │   ├── break_progress_engine.py 
│   │       │   └── behavior_mask.py    # ⚠️ ТРЕБУЕТ ПЕРЕХОДА НА CONSTRAINTS
│   │       │
│   │       ├── resolution/             # МЕХАНИКА ИСХОДОВ
│   │       │   └── action_resolver.py  
│   │       │
│   │       ├── state/                  # УПРАВЛЕНИЕ МИРОМ
│   │       │   └── scene_state_manager.py   
│   │       │
│   │       ├── memory/                 # ПАМЯТЬ И КОМПРЕССИЯ (Итерация 3)
│   │       │   ├── working_memory.py   # ⚠️ ТРЕБУЕТ SUMMARY COMPRESSION
│   │       │   └── relationship_store.py
│   │       │
│   │       ├── verbalization/          # СЛОЙ ГОЛОСА (LLM)
│   │       │   ├── scene_outcome_builder.py 
│   │       │   └── verbal_stance.py    
│   │       │
│   │       └── social/                 # 🆕 СОЦИАЛЬНАЯ ДИНАМИКА (Итерация 5)
│   │           └── social_engine.py    # Слухи, связи NPC-NPC
│   │
│   └── data/                           # PERSISTENCE LAYER
│
└── frontend/                           # UI / UX LAYER


┌──────────────────────────────────────────────────────────────────────────────┐
│                    4. DATA FLOW (ОБНОВЛЕННЫЙ ПАЙПЛАЙН)                       │
└──────────────────────────────────────────────────────────────────────────────┘

RAW INPUT (PlayerIntent)
    │
    ▼
DM SYSTEM (Router)
    │
    ├──► [ЕСЛИ INTENT_PHYSICAL] ──► RULES AGENT (Бросок кубиков) ──► MicroEvents ──┐
    │                                                                              │
    └──► [ЕСЛИ INTENT_VERBAL] ────► CHARACTER FILTER (Итерация 2)                  │
                                        │                                          │
                                        ▼                                          │
                                  FilteredAction ◄─────────────────────────────────┘
                                        │
                                        ▼
                                  PERCEPTION FILTER (Cap 15m)
                                        │
                                        ▼
                                  CognitiveDistortionEngine
                                        │
                                        ▼
                                  DECISIONHUB (PURE SCORER)
                                  (Учитывает mask_modifiers из Break System)
                                        │
                                        ▼
                                  DecisionResult[]
                                        │
                                        ▼
╔══════════════════════════════════════════════════════════════════════════════╗
║  СЛОЙ 1 — ФИЗИЧЕСКАЯ РЕАЛЬНОСТЬ                                              ║
║  StateApplicator (Пишет CausalEntry в CausalLedger)                          ║
╚══════════════════════════════════════════════════════════════════════════════╝
                                        │
                                        ▼
╔══════════════════════════════════════════════════════════════════════════════╗
║  СЛОЙ 2 — СУБЪЕКТИВНАЯ РЕАЛЬНОСТЬ                                            ║
║  _build_psychological_projection() → NpcOutcome.psychological                ║
╚══════════════════════════════════════════════════════════════════════════════╝
                                        │
                                        ▼
                                  DMFrame
                                        │
                                        ▼
                                  LLM (ТОЛЬКО ВЕРБАЛИЗАЦИЯ)
                                        │
                                        ▼
                                  FINAL TEXT


================================================================================

0.1 ГЛАВНЫЙ ПРИНЦИП (НЕПРИКОСНОВЕНЕН)

```
LLM НЕ ПРИНИМАЕТ РЕШЕНИЯ.
LLM НЕ МЕНЯЕТ СОСТОЯНИЕ.
LLM НЕ ВЫДАЁТ ДЕЛЬТЫ.
```

**LLM = слой вербализации.** Получает `intent` (намерение), `emotion` (эмоция строкой) и сжатый контекст (Summary). Возвращает текст. Всё.

**Python = слой интеллекта.** `DecisionHub` считает `score(action)` по числовым весам. Только он решает что произойдет. Физические действия разрешаются через `Rules Agent` (кубики), а не через фантазию LLM.

**ГЛАВНЫЙ ИНВАРИАНТ СИСТЕМЫ:**
```text
Ни LLM, ни persistence не имеют права вводить новые факты.
LLM → только текст, не структура.
Parser → не создаёт сущности.
Commitment → не является фактом, только состоянием.
ХАРДКОД отдельных NPC ЗАПРЕЩЕН!!! Система должна быть масштабируемой.
```
```