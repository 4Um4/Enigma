# 🗺️ ENIGMA ROADMAP v2.0
# Дорожная карта развития локальной AI-D&D системы
# На основе: README.md + README_Последняя версия.md + Диалог разработки
# Дата: Март 2026 | Прогресс: 65% → Цель: 95%

# ============================================================================
# 📊 ТЕКУЩЕЕ СОСТОЯНИЕ (AUDIT)
# ============================================================================

STATUS:
  Core_Infrastructure:      ✅ 100%  (FastAPI, Llama.cpp, CUDA, ModelPool)
  Multi_Agent_Pipeline:     ✅ 85%   (5 агентов, lazy loading, health checks)
  Memory_System:            ✅ 70%   (JSONL 3 слоя, retrieval=20, нет RAG)
  Game_Mechanics:           ❌ 25%   (Базовый combat, нет spells/conditions)
  UI_UX:                    ❌ 40%   (Базовый HTML, нет streaming/WS)
  Data_Persistence:         ❌ 30%   (Только JSONL, нет SQLite/VectorDB)
  Reputation_System:        ❌ 0%    (Новая фича из диалога)
  Error_Interpretation:     ❌ 0%    (Новая фича из диалога)

HARDWARE_LIMITS:
  GPU: RTX 3070 Ti (8GB VRAM) → Макс 1 модель в VRAM одновременно
  CPU: i7-9700F (8 ядер)
  RAM: 16 GB
  CONSTRAINT: Lazy loading обязателен, VRAM-семафор критичен

# ============================================================================
# 🎯 ПРИОРИТЕТЫ (P0-P3)
# ============================================================================

P0: КРИТИЧНО (Без этого нельзя релизить)
  - Стабильность ModelPool (утечки VRAM)
  - Базовый UI с чатом
  - Error Interpreter для разработки

P1: ВАЖНО (Улучшает UX значительно)
  - Streaming токенов
  - Reputation System Этап 1
  - SQLite для состояния игры

P2: ЖЕЛАТЕЛЬНО (Глубина геймплея)
  - Vector DB для памяти
  - Полные правила D&D 5e
  - Desktop UI (Tauri/Electron)

P3: ОПЦИОНАЛЬНО (Future features)
  - Мультиплеер
  - Генерация карт
  - Голосовой ввод

# ============================================================================
# 📅 ФАЗА 1: СТАБИЛЬНОСТЬ + ERROR INTERPRETER (2-3 недели)
# ============================================================================

PHASE_1:
  name: "Фундамент и отладка"
  priority: P0
  estimated_weeks: 3

  TASKS:
    - id: F1-T01
      name: "Error Interpreter Service"
      description: |
        Сервис перехвата и интерпретации ошибок LLM/агентов.
        Превращает технические ошибки в понятные сообщения для разработчика.
      files_to_create:
        - backend/services/error_interpreter.py
        - backend/tests/test_error_interpreter.py
      acceptance_criteria:
        - "Перехватывает 5 типов ошибок (timeout, OOM, context_overflow, model_fail, json_parse)"
        - "Генерирует human-readable отчет в лог"
        - "Предлагает fix-рекомендации (например: 'Уменьши context на 500 токенов')"
      priority: P0
      effort_hours: 8

    - id: F1-T02
      name: "VRAM Leak Detector"
      description: |
        Мониторинг утечек памяти в ModelPool.
        Интеграция с nvidia-smi через subprocess.
      files_to_create:
        - backend/services/vram_monitor.py
        - backend/app/api/routes_debug.py
      acceptance_criteria:
        - "Логгирует VRAM до/after каждой загрузки модели"
        - "Алерт если утечка >100MB за сессию"
        - "Endpoint GET /debug/vram"
      priority: P0
      effort_hours: 6

    - id: F1-T03
      name: "Agent Health Dashboard"
      description: |
        Страница в UI со статусом всех 5 агентов.
        Показывает: модель, VRAM, last_response_time, error_count.
      files_to_create:
        - frontend/ui/debug.html
        - backend/app/api/routes_debug.py (extend)
      acceptance_criteria:
        - "Обновление каждые 5 сек (polling)"
        - "Визуальные индикаторы (зеленый/желтый/красный)"
        - "Кнопка 'Restart Agent' для каждого"
      priority: P0
      effort_hours: 10

    - id: F1-T04
      name: "Logging Structured JSON"
      description: |
        Переход с print() на structlog с JSON-выводом.
        Упрощает парсинг логов для Error Interpreter.
      files_to_modify:
        - backend/app/main.py
        - backend/app/services/llm/*.py
      acceptance_criteria:
        - "Все логи в формате JSONL"
        - "Поля: timestamp, level, agent, model, duration, error_code"
        - "Лог-файл: data/logs/enigma_{date}.jsonl"
      priority: P0
      effort_hours: 4

# ============================================================================
# 📅 ФАЗА 2: UI/UX + STREAMING (3-4 недели)
# ============================================================================

PHASE_2:
  name: "Пользовательский интерфейс"
  priority: P0
  estimated_weeks: 4

  TASKS:
    - id: F2-T01
      name: "Token Streaming (SSE)"
      description: |
        Потоковая передача токенов от llama.cpp к фронтенду.
        Использовать llama-cpp-python stream + FastAPI SSE.
      files_to_create:
        - backend/app/api/routes_stream.py
        - backend/services/llm/streaming_provider.py
      files_to_modify:
        - backend/app/agents/dm_agent.py
        - frontend/ui/index.html
      acceptance_criteria:
        - "Первый токен <500ms"
        - "Плавное обновление в чате (typewriter effect)"
        - "Fallback на batch mode если SSE fail"
      priority: P0
      effort_hours: 16
      technical_notes: |
        ⚠️ Критично: Не блокировать Event Loop!
        Использовать asyncio.Queue для передачи токенов.

    - id: F2-T02
      name: "Desktop UI (Tauri)"
      description: |
        Отказ от браузера в пользу нативного desktop-приложения.
        Tauri легче Electron, интегрируется с Rust-бэкендом.
      files_to_create:
        - desktop-ui/ (новый репозиторий или папка)
        - desktop-ui/src-tauri/
        - desktop-ui/src/
      acceptance_criteria:
        - "Окно с чатом, панелью игроков, логом событий"
        - "Системный трей с быстрыми командами"
        - "Горячие клавиши (F12 - debug, F5 - reroll)"
      priority: P1
      effort_hours: 40
      recommendation: |
        🧠 GENIUS IDEA: Использовать Tauri v2 с Rust-плагином для 
        прямого доступа к nvidia-smi без subprocess. Это даст 
        реальный мониторинг VRAM из UI.

    - id: F2-T03
      name: "Player Panel (HP, Inventory, Stats)"
      description: |
        Визуальная панель состояния персонажа.
        Редактируемые поля (игрок может править HP вручную).
      files_to_create:
        - frontend/ui/components/player_panel.html
        - backend/app/api/routes_characters.py (extend)
      acceptance_criteria:
        - "Отображение: HP, AC, Initiative, Conditions"
        - "Кнопки: +HP, -HP, Add Condition"
        - "Автосохранение в campaign_state.json"
      priority: P1
      effort_hours: 12

    - id: F2-T04
      name: "Chat History with Search"
      description: |
        Поиск по истории чата (по ключевым словам, датам, NPC).
      files_to_create:
        - frontend/ui/components/chat_search.js
        - backend/app/services/memory.py (extend search)
      acceptance_criteria:
        - "Поиск по тексту сообщений"
        - "Фильтр по: player, npc, dm, system"
        - "Подсветка найденных совпадений"
      priority: P2
      effort_hours: 8

# ============================================================================
# 📅 ФАЗА 3: REPUTATION SYSTEM (2-3 недели)
# ============================================================================

PHASE_3:
  name: "Система репутации и NPC"
  priority: P1
  estimated_weeks: 3

  TASKS:
    - id: F3-T01
      name: "Reputation Engine (Stage 1)"
      description: |
        Базовая система: глобальная репутация (-100..+100) + 3-5 NPC с доверием.
        Чистый Python (без LLM) для скорости <50ms.
      files_to_create:
        - backend/services/reputation_engine.py
        - backend/tests/test_reputation_perf.py
        - data/campaigns/{id}/reputation_state.json
      acceptance_criteria:
        - "test_reputation_perf.py: elapsed < 0.05s на 100 итераций"
        - "Жёсткие правила в rules_agent для обновления"
        - "Сохранение в JSON после каждого хода"
      priority: P1
      effort_hours: 10
      code_snippet: |
        # backend/services/reputation_engine.py
        class ReputationEngine:
            def evaluate(self, action, context) -> dict:
                # Детерминированная логика, НЕ LLM
                if action.type == "theft":
                    return {"global_rep": -5, "faction_rep": {"thieves_guild": +10}}
                # ...

    - id: F3-T02
      name: "Faction Reputation (Stage 2)"
      description: |
        Фракционная репутация (гильдия, церковь, город).
        Влияние на диалоги NPC (выбор реплик).
      files_to_create:
        - backend/services/faction_manager.py
        - data/campaigns/{id}/factions.json
      acceptance_criteria:
        - "Минимум 3 фракции с независимыми значениями"
        - "NPC проверяет faction_rep перед генерацией ответа"
        - "Цепные реакции: репутация у одной влияет на другую"
      priority: P1
      effort_hours: 14

    - id: F3-T03
      name: "NPC Traits System (Stage 3)"
      description: |
        Многомерные черты характера (храбрость, жадность, лояльность).
        Динамические цели NPC на основе черт.
      files_to_create:
        - backend/services/npc_traits.py
        - backend/app/agents/npc_agent.py (extend)
      acceptance_criteria:
        - "5+ черт у каждого Major NPC"
        - "Если 'жадность' > 7 → попытается обмануть (LLM-нюанс)"
        - "Опциональный LLM-нюанс через лёгкую модель (3-4B)"
      priority: P2
      effort_hours: 18
      technical_notes: |
        🧠 GENIUS IDEA: Использовать модель 3B (Phi-3-mini) для 
        быстрой оценки намерений NPC, пока 7B пишет текст. 
        Это уложится в VRAM-лимиты (3B ≈ 2GB).

    - id: F3-T04
      name: "Reputation UI Widget"
      description: |
        Виджет в UI для игрока: текущая репутация, отношения с фракциями.
      files_to_create:
        - frontend/ui/components/reputation_widget.html
      acceptance_criteria:
        - "Визуальные бары (-100..+100)"
        - "Цветовая индикация (красный/желтый/зеленый)"
        - "Тультип с описанием эффектов"
      priority: P2
      effort_hours: 6

# ============================================================================
# 📅 ФАЗА 4: DATA INFRASTRUCTURE (3-4 недели)
# ============================================================================

PHASE_4:
  name: "Хранение данных и RAG"
  priority: P1
  estimated_weeks: 4

  TASKS:
    - id: F4-T01
      name: "SQLite Migration for Game State"
      description: |
        Перенос структурированных данных (HP, инвентарь, квесты) из JSONL в SQLite.
        JSONL остаётся для нарратива и логов.
      files_to_create:
        - backend/services/database.py
        - backend/models/db_schemas.py
        - backend/tests/test_database.py
      files_to_modify:
        - backend/app/api/routes_characters.py
        - backend/app/services/memory.py
      acceptance_criteria:
        - "Таблицы: players, items, quests, factions, reputation"
        - "Миграция существующих данных из JSONL"
        - "API endpoint для прямого SQL-запроса (debug)"
      priority: P1
      effort_hours: 20
      technical_notes: |
        ⚠️ Критично: Использовать asyncio aiosqlite для неблокирующего доступа.

    - id: F4-T02
      name: "Vector DB (FAISS/Chroma)"
      description: |
        Векторный поиск для долгосрочной памяти и лора.
        Offline-first RAG: эмбеддинги генерируются при установке.
      files_to_create:
        - backend/services/vector_store.py
        - backend/services/embedding_generator.py
      files_to_modify:
        - backend/app/services/memory.py
        - backend/app/agents/memory_manager_agent.py
      acceptance_criteria:
        - "Импорт 7 PDF книг с генерацией эмбеддингов"
        - "Семантический поиск по лору (retrieval=50)"
        - "Кэш эмбеддингов в data/embeddings/"
      priority: P2
      effort_hours: 24
      recommendation: |
        🧠 GENIUS IDEA: Использовать all-MiniLM-L6-v2 (80MB) для 
        локальных эмбеддингов. Не требует GPU, работает на CPU 
        за <100ms на документ.

    - id: F4-T03
      name: "Memory Compressor Agent"
      description: |
        Агент, создающий сжатые воспоминания каждые ~10 ходов.
        Освобождает контекст для важных сцен.
      files_to_create:
        - backend/app/agents/compressor_agent.py
      files_to_modify:
        - backend/app/services/orchestrator.py
      acceptance_criteria:
        - "Автоматический запуск после 10 player turns"
        - "Создание summary в campaign_memory.jsonl"
        - "Очистка старых сообщений из session_memory"
      priority: P2
      effort_hours: 12

    - id: F4-T04
      name: "Snapshot System"
      description: |
        Снимки состояния мира (локации, NPC, таймеры) для отката.
      files_to_create:
        - backend/services/snapshot_manager.py
      acceptance_criteria:
        - "Команда /snapshot save <name>"
        - "Команда /snapshot load <name>"
        - "Автоснимок каждые 30 мин"
      priority: P3
      effort_hours: 10

# ============================================================================
# 📅 ФАЗА 5: GAME MECHANICS DEEP (4-5 недель)
# ============================================================================

PHASE_5:
  name: "Полные правила D&D 5e"
  priority: P2
  estimated_weeks: 5

  TASKS:
    - id: F5-T01
      name: "Full Rules Engine"
      description: |
        Валидация всех действий по правилам D&D 5e.
        Skill checks, saving throws, conditions.
      files_to_create:
        - backend/services/rules_engine.py
        - backend/data/rules/spells.json
        - backend/data/rules/conditions.json
      files_to_modify:
        - backend/app/agents/rules_agent.py
      acceptance_criteria:
        - "Валидация 50+ заклинаний"
        - "10+ условий (blinded, poisoned, stunned...)"
        - "Автоматические saving throws"
      priority: P2
      effort_hours: 30

    - id: F5-T02
      name: "Combat System 2.0"
      description: |
        Расширенный бой: действия, бонусные действия, реакции.
      files_to_create:
        - backend/services/combat_tracker.py
      files_to_modify:
        - backend/app/api/routes_combat.py
      acceptance_criteria:
        - "Инициатива с учётом модификаторов"
        - "Трекер действий (action/bonus/reaction)"
        - "Визуализация в UI (combat panel)"
      priority: P2
      effort_hours: 20

    - id: F5-T03
      name: "Dynamic Context Budgeting"
      description: |
        Распределение токенов: больше для важных сцен, меньше для рутины.
      files_to_create:
        - backend/services/context_budget.py
      files_to_modify:
        - backend/app/services/context_builder.py
      acceptance_criteria:
        - "Босс-файт: context=4096"
        - "Диалог в таверне: context=2048"
        - "Автосжатие при превышении лимита"
      priority: P2
      effort_hours: 14

# ============================================================================
# 🧠 GENIUS IDEAS (Инновации для проекта)
# ============================================================================

GENIUS_FEATURES:
  - name: "LLM Self-Debug Mode"
    description: |
      При ошибке LLM автоматически запрашивает у другой модели 
      (например, Rules Agent) диагностику проблемы.
    implementation:
      - "При json_parse_error → отправить ответ в rules_agent"
      - "rules_agent анализирует и предлагает fix"
      - "Автоматическая повторная генерация с corrected prompt"
    effort_hours: 12
    priority: P2

  - name: "VRAM-Aware Model Switching"
    description: |
      Умное переключение моделей на основе доступной VRAM.
      Если VRAM < 2GB → автоматически выгружает неактивные модели.
    implementation:
      - "vram_monitor.py →实时追踪 VRAM"
      - "ModelPool.get_model_async() проверяет доступную память"
      - "Приоритет: DM > Rules > NPC > World"
    effort_hours: 10
    priority: P1

  - name: "Player Memory Editor"
    description: |
      Игрок может просматривать и редактировать «известные факты».
      Прозрачность системы памяти.
    implementation:
      - "Endpoint GET /api/memory/facts"
      - "Endpoint POST /api/memory/facts/{id}/edit"
      - "UI: список фактов с кнопками edit/delete"
    effort_hours: 8
    priority: P2

  - name: "Offline-First RAG Cache"
    description: |
      Эмбеддинги правил, лора, предметов генерируются при установке.
      Поиск — полностью локальный, без сети.
    implementation:
      - "При первом запуске: генерация эмбеддингов 7 PDF"
      - "Кэш в data/embeddings/*.bin"
      - "FAISS индекс загружается в RAM при старте"
    effort_hours: 16
    priority: P1

# ============================================================================
# 📈 МЕТРИКИ УСПЕХА (KPI)
# ============================================================================

SUCCESS_METRICS:
  Performance:
    - "First token latency: <500ms (streaming)"
    - "Reputation update: <50ms (test_reputation_perf.py)"
    - "Model switch: <3s (lazy loading)"
    - "Vector search: <200ms (FAISS)"

  Stability:
    - "VRAM leak: <100MB за 10 часов сессии"
    - "Agent fail rate: <1% (fallback работает)"
    - "Test coverage: >85% (сейчас 80%)"

  UX:
    - "UI load time: <2s"
    - "Chat scroll: 60fps (no lag)"
    - "Error messages: 100% human-readable"

# ============================================================================
# 🚀 БЫСТРЫЙ СТАРТ (Следующие 7 дней)
# ============================================================================

WEEK_1_SPRINT:
  Day_1_2:
    - "F1-T01: Error Interpreter (базовая версия)"
    - "F1-T04: Structured JSON Logging"
  Day_3_4:
    - "F1-T02: VRAM Leak Detector"
    - "F1-T03: Agent Health Dashboard (базовый)"
  Day_5_6:
    - "F3-T01: Reputation Engine Stage 1"
    - "F3-T01: test_reputation_perf.py"
  Day_7:
    - "Тестирование, багфикс, документация"

# ============================================================================
# 📝 ЗАКЛЮЧЕНИЕ
# ============================================================================

SUMMARY:
  current_progress: "65%"
  target_progress: "95%"
  estimated_total_weeks: "19-23 недели (5 месяцев)"
  critical_path: "Phase 1 (Stability) → Phase 2 (UI) → Phase 3 (Reputation)"
  
  key_risks:
    - "VRAM-лимиты (8GB) могут не позволить Streaming + Vector DB одновременно"
    - "SQLite миграция может сломать существующие кампании"
    - "Tauri UI требует изучения Rust (кривая обучения)"
  
  mitigation:
    - "Приоритет: Streaming > Vector DB (отложить RAG если VRAM не хватает)"
    - "Бэкап всех JSONL перед миграцией на SQLite"
    - "Начать с HTML/JS UI, Tauri отложить на Phase 2.5"

  final_note: |
    🎯 Главная цель: Сделать локальную AI-D&D систему, которая работает 
    БЕЗ интернета, БЕЗ облака, с ПОЛНЫМ контролем над данными.
    
    💡 Ключевое преимущество перед конкурентами: 
    Прозрачность (игрок видит и правит память) + 
    Производительность (VRAM-aware оптимизации) + 
    Глубина (репутация, фракции, traits NPC).

# END OF ROADMAP


addition:
ФАЗА 3.5: PERSONALITY DEPTH (2 недели)
PHASE_3_5:
  name: "Enneagram Traits + Inner Thoughts"
  priority: P1
  tasks:
    - id: F3.5-T01
      name: "Enneagram Trait Engine"
      files: [backend/services/npc_traits.py, backend/tests/test_enneagram.py]
      acceptance: "18 personality profiles, stress/security lines, evolution logic"
      
    - id: F3.5-T02
      name: "Inner Thought Logging"
      files: [backend/app/agents/npc_agent.py, frontend/ui/components/thought_bubble.js]
      acceptance: "Каждый NPC response включает inner_thought, UI toggle для показа"
      
    - id: F3.5-T03
      name: "Natural Language Trait Parser (с guardrails)"
      files: [backend/app/api/routes_npcs.py, backend/services/trait_validator.py]
      acceptance: "Промпт → структурированные черты, валидация, понятные ошибки"

ФАЗА 4.5: WORLD AUTONOMY (2 недели)
PHASE_4_5:
  name: "Autonomous World Simulation"
  priority: P2
  tasks:
    - id: F4.5-T01
      name: "Activate World Scheduler"
      files: [backend/services/world_scheduler.py]
      acceptance: "Фоновые тики каждые 15 мин, Major NPC принимают автономные решения"
      
    - id: F4.5-T02
      name: "Karma Chain Reactions"
      files: [backend/services/karma_engine.py]
      acceptance: "Действие → прямое + косвенное + отложенное последствие"
      
    - id: F4.5-T03
      name: "Image-to-Text Knowledge Import"
      files: [backend/services/pdf_drop_importer.py]
      acceptance: "Загрузка изображения → текстовое описание → факт мира"

addition:
# ============================================================================
# 📅 ФАЗА 3.5: PERSONALITY DEPTH (inZOI-inspired) (2 недели)
# ============================================================================

PHASE_3_5:
  name: "Enneagram Traits + Inner Thoughts"
  priority: P1
  estimated_weeks: 2

  TASKS:
    - id: F3.5-T01
      name: "Enneagram Trait Engine"
      description: |
        Структурированная система личности NPC на основе 9 типов эннеаграммы.
        Эволюция черт под стрессом/безопасностью (линии эннеаграммы).
      files_to_create:
        - backend/services/npc_traits.py
        - backend/data/enneagram_types.json
        - backend/tests/test_enneagram.py
      acceptance_criteria:
        - "18 personality profiles (9 типов × 2 крыла)"
        - "Стресс/безопасность линии (type 6→3 under stress)"
        - "Эволюция черт со временем (tracking changes)"
      priority: P1
      effort_hours: 14
      code_snippet: |
        # backend/services/npc_traits.py
        ENNEAGRAM_TYPES = {
            1: {"name": "Perfectionist", "core_motivation": "to be right", "fear": "corruption"},
            2: {"name": "Helper", "core_motivation": "to be loved", "fear": "unworthiness"},
            # ... 3-9
        }
        
        class NPCTraitEngine:
            def evaluate_decision(self, context: dict) -> dict:
                # Возвращает: action, confidence, inner_thought
                pass

    - id: F3.5-T02
      name: "Inner Thought Logging"
      description: |
        Каждый NPC генерирует "внутреннюю мысль" перед публичным ответом.
        Игрок может увидеть через UI (по умолчанию скрыто).
      files_to_create:
        - backend/app/agents/npc_agent.py (extend)
        - frontend/ui/components/thought_bubble.js
      files_to_modify:
        - backend/app/api/routes_stream.py
      acceptance_criteria:
        - "Каждый NPC response включает inner_thought"
        - "UI toggle для показа/скрытия мыслей"
        - "Сохранение в session_memory для отладки"
      priority: P1
      effort_hours: 10
      technical_notes: |
        🧠 GENIUS IDEA: Не требует доп. LLM-запроса!
        inner_thought генерируется в том же запросе,
        просто парсится отдельно от public_response.

    - id: F3.5-T03
      name: "Natural Language Trait Parser (с guardrails)"
      description: |
        Игрок может создать NPC через текстовый промпт.
        Система валидирует и структурирует черты.
      files_to_create:
        - backend/app/api/routes_npcs.py
        - backend/services/trait_validator.py
      acceptance_criteria:
        - "Промпт → структурированные черты (JSON)"
        - "Валидация диапазонов (0-10 для каждой черты)"
        - "Понятные ошибки при невозможных запросах"
      priority: P2
      effort_hours: 8
      recommendation: |
        ⚠️ Критично: Чётко сообщать игроку о границах системы.
        "Этот персонаж использует 7B модель. Сложные запросы могут упрощаться."

    - id: F3.5-T04
      name: "Thought Bubble UI Widget"
      description: |
        Визуальный компонент для отображения мыслей NPC.
        Гибрид inZOI + Enigma прозрачности.
      files_to_create:
        - frontend/ui/components/thought_bubble.html
        - frontend/ui/components/thought_bubble.css
      acceptance_criteria:
        - "Наведение на NPC → показывает мысль"
        - "Кнопка '🔍 Почему?' → цепочка решения"
        - "Цветовая индикация эмоций (красный=гнев, синий=грусть)"
      priority: P2
      effort_hours: 6

# ============================================================================
# 📅 ФАЗА 4.5: WORLD AUTONOMY (inZOI-inspired) (2 недели)
# ============================================================================

PHASE_4_5:
  name: "Autonomous World Simulation"
  priority: P2
  estimated_weeks: 2

  TASKS:
    - id: F4.5-T01
      name: "Activate World Scheduler"
      description: |
        Запуск фоновой симуляции мира каждые 15 мин или 10 ходов.
        Major NPC принимают автономные решения.
      files_to_create:
        - backend/services/world_scheduler.py (activate)
        - backend/tests/test_world_scheduler.py
      files_to_modify:
        - backend/app/agents/world_sim_agent.py
        - backend/app/services/orchestrator.py
      acceptance_criteria:
        - "Фоновые тики каждые 15 мин реального времени"
        - "Major NPC с активными целями действуют автономно"
        - "Фоновые события: погода, экономика, слухи"
      priority: P2
      effort_hours: 16
      technical_notes: |
        ⚠️ Критично: Не блокировать основной геймплей!
        Использовать asyncio.create_task() для фоновых задач.

    - id: F4.5-T02
      name: "Karma Chain Reactions Engine"
      description: |
        Действия игрока имеют прямые + косвенные + отложенные последствия.
        Мир "помнит" и реагирует долгосрочно.
      files_to_create:
        - backend/services/karma_engine.py
        - backend/tests/test_karma_engine.py
      acceptance_criteria:
        - "Прямое последствие: репутация -10 за предательство"
        - "Косвенное: союзники фракции тоже теряют доверие"
        - "Отложенное: месть через 3 дня (world_tick trigger)"
      priority: P1
      effort_hours: 14
      code_snippet: |
        # backend/services/karma_engine.py
        class KarmaEngine:
            def process_action(self, action: dict, actor: str) -> list[Consequence]:
                consequences = []
                # Прямое последствие
                consequences.append(Consequence(target=action["target"], type="reputation_change", value=-10))
                # Цепная реакция: фракция → союзники → враги
                if action["target_faction"]:
                    allies = self._get_allies(action["target_faction"])
                    for ally in allies:
                        consequences.append(Consequence(target=ally, type="indirect_reputation", value=-3))
                # Отложенное последствие
                if action["severity"] > 7:
                    consequences.append(Consequence(target=action["target"], type="delayed_event", delay_ticks=3, event="revenge_attempt"))
                return consequences

    - id: F4.5-T03
      name: "Image-to-Text Knowledge Import"
      description: |
        Игрок загружает скетч локации → ИИ создаёт текстовое описание.
        НЕ генерация 3D, а описание для лора (легче для 8GB VRAM).
      files_to_create:
        - backend/services/image_importer.py
        - backend/app/api/routes_import.py (extend)
      acceptance_criteria:
        - "Загрузка изображения (PNG/JPG)"
        - "Малая модель (3-4B) описывает: объекты, атмосфера, зацепки"
        - "Сохранение как факт мира с тегом 'visual_reference'"
      priority: P3
      effort_hours: 10
      recommendation: |
        🧠 GENIUS IDEA: Использовать Phi-3-mini (3.8B) для описания.
        ≈2GB VRAM, работает на CPU за <5 сек на изображение.

    - id: F4.5-T04
      name: "World Event Log UI"
      description: |
        Панель фоновых событий мира (что произошло пока игрок спал).
      files_to_create:
        - frontend/ui/components/world_events.html
        - frontend/ui/components/world_events.js
      acceptance_criteria:
        - "Список событий за последние 24 часа игрового времени"
        - "Фильтр по: combat, social, exploration, random"
        - "Клик на событие → детали в чате"
      priority: P2
      effort_hours: 8

# ============================================================================
# 🧠 GENIUS IDEAS 2.0 (Дополнительные инновации)
# ============================================================================

GENIUS_FEATURES_EXTENDED:
  - name: "LLM Self-Debug Mode"
    description: |
      При ошибке LLM автоматически запрашивает у другой модели 
      (например, Rules Agent) диагностику проблемы.
    implementation:
      - "При json_parse_error → отправить ответ в rules_agent"
      - "rules_agent анализирует и предлагает fix"
      - "Автоматическая повторная генерация с corrected prompt"
    effort_hours: 12
    priority: P2
    files:
      - backend/services/self_debug.py
      - backend/tests/test_self_debug.py

  - name: "VRAM-Aware Model Switching"
    description: |
      Умное переключение моделей на основе доступной VRAM.
      Если VRAM < 2GB → автоматически выгружает неактивные модели.
    implementation:
      - "vram_monitor.py →实时追踪 VRAM"
      - "ModelPool.get_model_async() проверяет доступную память"
      - "Приоритет: DM > Rules > NPC > World"
    effort_hours: 10
    priority: P1
    files:
      - backend/services/vram_monitor.py (extend)
      - backend/services/model_pool.py (extend)

  - name: "Player Memory Editor"
    description: |
      Игрок может просматривать и редактировать «известные факты».
      Прозрачность системы памяти — ключевое преимущество перед конкурентами.
    implementation:
      - "Endpoint GET /api/memory/facts"
      - "Endpoint POST /api/memory/facts/{id}/edit"
      - "UI: список фактов с кнопками edit/delete"
    effort_hours: 8
    priority: P2
    files:
      - backend/app/api/routes_memory.py
      - frontend/ui/components/memory_editor.html

  - name: "Offline-First RAG Cache"
    description: |
      Эмбеддинги правил, лора, предметов генерируются при установке.
      Поиск — полностью локальный, без сети.
    implementation:
      - "При первом запуске: генерация эмбеддингов 7 PDF"
      - "Кэш в data/embeddings/*.bin"
      - "FAISS индекс загружается в RAM при старте"
    effort_hours: 16
    priority: P1
    files:
      - backend/services/embedding_generator.py
      - backend/services/vector_store.py

  - name: "🧠 Error Interpreter UI (Новое!)"
    description: |
      Визуальная панель ошибок в UI (не только в логах).
      Игрок/разработчик видит проблемы игры в реальном времени.
    implementation:
      - "WebSocket push ошибок в UI"
      - "Категоризация: critical, warning, info"
      - "Кнопка 'Auto-Fix' для некоторых ошибок"
    effort_hours: 10
    priority: P0
    files:
      - frontend/ui/components/error_console.html
      - backend/app/api/routes_debug.py (extend)
    technical_notes: |
      ⚠️ Критично для разработки! Позволяет видеть ошибки
      внутри игры, а не только в терминале/логах.

  - name: "🧠 Agent Connectivity Graph (Новое!)"
    description: |
      Визуализация связей между агентами в реальном времени.
      Показывает какой агент кому передаёт данные.
    implementation:
      - "Endpoint GET /debug/agent_graph"
      - "D3.js визуализация в UI"
      - "Анимация потоков данных между агентами"
    effort_hours: 12
    priority: P2
    files:
      - frontend/ui/components/agent_graph.html
      - backend/app/api/routes_debug.py (extend)
    recommendation: |
      💡 Помогает понять "мозг" системы. Разработчик видит
      как данные текут через Orchestrator → Agents → Memory.

  - name: "🧠 Context Budget Visualizer (Новое!)"
    description: |
      Показывает распределение токенов контекста в реальном времени.
      Игрок видит сколько токенов на что тратится.
    implementation:
      - "Endpoint GET /debug/context_budget"
      - "Pie chart: system/world/memory/dialogue/rules"
      - "Предупреждение при >90% использования"
    effort_hours: 8
    priority: P2
    files:
      - frontend/ui/components/context_budget.html
      - backend/app/services/context_builder.py (extend)

# ============================================================================
# 📈 ОБНОВЛЁННЫЕ МЕТРИКИ УСПЕХА (KPI)
# ============================================================================

SUCCESS_METRICS_UPDATED:
  Performance:
    - "First token latency: <500ms (streaming)"
    - "Reputation update: <50ms (test_reputation_perf.py)"
    - "Model switch: <3s (lazy loading)"
    - "Vector search: <200ms (FAISS)"
    - "Inner thought generation: +0ms (same request)"
    - "World tick: <1s (background, non-blocking)"

  Stability:
    - "VRAM leak: <100MB за 10 часов сессии"
    - "Agent fail rate: <1% (fallback работает)"
    - "Test coverage: >85% (сейчас 80%)"
    - "Error interpreter: 100% ошибок логируются"

  UX:
    - "UI load time: <2s"
    - "Chat scroll: 60fps (no lag)"
    - "Error messages: 100% human-readable"
    - "Thought bubble: <100ms to display"
    - "Memory editor: real-time sync"

  Gameplay Depth:
    - "NPC traits: 5+ per Major NPC"
    - "Factions: 3+ independent reputation tracks"
    - "Karma chains: 3+ consequence types"
    - "World events: 5+ background events per session"

# ============================================================================
# 🔄 ОБНОВЛЁННЫЙ ROADMAP SUMMARY
# ============================================================================

SUMMARY_UPDATED:
  current_progress: "65%"
  target_progress: "95%"
  estimated_total_weeks: "23-27 недель (6 месяцев)"
  critical_path: "Phase 1 (Stability) → Phase 2 (UI) → Phase 3 (Reputation) → Phase 3.5 (Personality)"
  
  phase_breakdown:
    Phase_1: "2-3 недели (Stability + Error Interpreter)"
    Phase_2: "3-4 недели (UI + Streaming)"
    Phase_3: "2-3 недели (Reputation System)"
    Phase_3_5: "2 недели (Personality + Inner Thoughts)"
    Phase_4: "3-4 недели (Data Infrastructure)"
    Phase_4_5: "2 недели (World Autonomy)"
    Phase_5: "4-5 недель (Full D&D 5e Rules)"

  key_risks:
    - "VRAM-лимиты (8GB) могут не позволить Streaming + Vector DB одновременно"
    - "SQLite миграция может сломать существующие кампании"
    - "Tauri UI требует изучения Rust (кривая обучения)"
    - "World Scheduler может конфликтовать с основным геймплеем"
  
  mitigation:
    - "Приоритет: Streaming > Vector DB (отложить RAG если VRAM не хватает)"
    - "Бэкап всех JSONL перед миграцией на SQLite"
    - "Начать с HTML/JS UI, Tauri отложить на Phase 2.5"
    - "World Scheduler запускать только в безопасные моменты (rest, travel)"

  competitive_advantages:
    - "🏆 Прозрачность: игрок видит мысли NPC, память, ошибки"
    - "🏆 Производительность: VRAM-aware оптимизации для 8GB"
    - "🏆 Глубина: репутация, фракции, traits, karma chains"
    - "🏆 Оффлайн: 100% локально, без облака, без интернета"
    - "🏆 Контроль: игрок правит память, факты, состояние"

  inZOI_comparison:
    - "✅ Enigma мощнее в мульти-агентной архитектуре (5 vs 1)"
    - "✅ Enigma прозрачнее (игрок видит 'кухню' ИИ)"
    - "✅ Enigma работает на слабее железе (8GB vs NVIDIA NVIGI)"
    - "🔄 Взять из inZOI: Enneagram, Inner Thoughts, Karma Chains"
    - "🚫 Не брать: 3D Printer, облачные зависимости"

# ============================================================================
# 🚀 ОБНОВЛЁННЫЙ БЫСТРЫЙ СТАРТ (Следующие 14 дней)
# ============================================================================

WEEK_1_2_SPRINT:
  Week_1:
    Day_1_2:
      - "F1-T01: Error Interpreter (базовая версия)"
      - "F1-T04: Structured JSON Logging"
    Day_3_4:
      - "F1-T02: VRAM Leak Detector"
      - "F1-T03: Agent Health Dashboard (базовый)"
      - "🧠 NEW: Error Interpreter UI (базовый)"
    Day_5_6:
      - "F3-T01: Reputation Engine Stage 1"
      - "F3-T01: test_reputation_perf.py"
    Day_7:
      - "Тестирование, багфикс, документация"

  Week_2:
    Day_8_9:
      - "F2-T01: Token Streaming (SSE) - базовый"
      - "F2-T03: Player Panel (HP, Inventory)"
    Day_10_11:
      - "F3.5-T01: Enneagram Trait Engine"
      - "F3.5-T02: Inner Thought Logging"
    Day_12_13:
      - "F3.5-T04: Thought Bubble UI Widget"
      - "🧠 NEW: Agent Connectivity Graph (базовый)"
    Day_14:
      - "Тестирование, демо, сбор фидбека"

# ============================================================================
# 📋 CHECKLIST ДЛЯ РАЗРАБОТЧИКА
# ============================================================================

DEVELOPER_CHECKLIST:
  Before_Each_Session:
    - [ ] "nvidia-smi — проверить VRAM (<6GB свободно)"
    - [ ] "backend/start_enigma.bat — запустить сервер"
    - [ ] "GET /api/health — проверить все агенты"
    - [ ] "data/logs/ — проверить вчерашние логи"

  After_Each_Task:
    - [ ] "pytest backend/tests/test_*.py — пройти тесты"
    - [ ] "nvidia-smi — проверить утечки VRAM"
    - [ ] "data/logs/enigma_{date}.jsonl — логи записались"
    - [ ] "README.md — обновить прогресс"

  Before_Commit:
    - [ ] "python -m compileall backend/app — синтаксис"
    - [ ] "pytest -q — все тесты зелёные"
    - [ ] "VRAM leak <100MB за сессию"
    - [ ] "Error interpreter — ошибки логируются"

  Weekly_Review:
    - [ ] "Прогресс по roadmap (%)"
    - [ ] "Тесты покрытие (>85%)"
    - [ ] "VRAM стабильность (<100MB утечка)"
    - [ ] "UX метрики (first token <500ms)"
    - [ ] "Бэкап data/campaigns/"

# ============================================================================
# 🎯 ФИНАЛЬНАЯ ЦЕЛЬ
# ============================================================================

FINAL_VISION:
  statement: |
    🎯 Создать локальную AI-D&D систему, которая работает 
    БЕЗ интернета, БЕЗ облака, с ПОЛНЫМ контролем над данными.
    
  player_experience: |
    👤 Игрок видит чат с потоковой печатью токенов
    👤 Видит панель персонажа (HP, инвентарь, репутация)
    👤 Может посмотреть мысли NPC (кнопка "🧠")
    👤 Может редактировать известные факты (память)
    👤 Видит ошибки игры в понятном формате (не код)
    👤 Видит как агенты связаны между собой (граф)
    
  developer_experience: |
    🛠 Разработчик видит все логи в JSONL формате
    🛠 Error Interpreter предлагает fix-рекомендации
    🛠 VRAM Monitor алертит об утечках
    🛠 Agent Health Dashboard показывает статус 5 агентов
    🛠 Тесты покрывают >85% кода
    
  technical_excellence: |
    ⚡ First token <500ms (streaming)
    ⚡ Reputation update <50ms (pure Python)
    ⚡ Model switch <3s (lazy loading)
    ⚡ VRAM leak <100MB за 10 часов
    ⚡ 100% offline (no cloud dependencies)

# ============================================================================
# END OF ENIGMA ROADMAP v2.0
# ============================================================================





# 🧠 ENIGMA NPC ARCHITECTURE v4.0 — ПОЛНАЯ КОНСОЛИДИРОВАННАЯ СПЕЦИФИКАЦИЯ
## Все системы NPC в одном документе

На основе всего диалога + README Enigma + 4 Драйва + Psyche Engine + Life Sim + Social Mobility + Threat Assessment + Emergent Status

---

## 📋 1. ПОЛНАЯ СТРУКТУРА JSON NPC

```json
{
  "id": "farmer_grom_01",
  "name": "Гром",
  "tier": "minor",
  
  "status_profile": {
    "freedom": 50,
    "wealth": 10,
    "power": 5,
    "title": "Крестьянин",
    "faction_rank": {}
  },
  
  "visible_markers": ["tunic", "hoe", "calloused_hands"],
  "hidden_truth": ["former_soldier"],
  
  "drives": {
    "control": 0.60,
    "significance": 0.10,
    "fear": 0.25,
    "desire": 0.05
  },
  
  "psyche": {
    "willpower": 45,
    "stress": 30,
    "breakpoint": 85,
    "loyalty_true": 50,
    "loyalty_fake": 50,
    "state": "free",
    "trauma_flags": []
  },
  
  "social_stats": {
    "trust": 0.50,
    "affection": 0.40,
    "fear_of_player": 0.10,
    "debt": 0
  },
  
  "relationships": {
    "player_aria": 50,
    "wife_elena": 80,
    "merchant_grok": -20,
    "guild_thieves": -50
  },
  
  "routine": {
    "current": "plowing",
    "mood": "neutral",
    "interrupted": false,
    "next_task": "feed_children",
    "schedule": {
      "06:00-18:00": "working",
      "18:00-22:00": "family_time",
      "22:00-06:00": "sleeping"
    }
  },
  
  "recent_events": [
    {"tick": 104, "event": "tax_collector_taken_coins", "impact": "anger"},
    {"tick": 108, "event": "child_broke_tool", "impact": "frustration"}
  ],
  
  "history": [],
  
  "flags": {
    "has_gold": false,
    "knows_secret": false,
    "usurper": false,
    "owed_debt": false
  },
  
  "memory_trace": [],
  
  "location": "village_fields"
}
```

---

## 📊 2. ТАБЛИЦА ВСЕХ ПОЛЕЙ (ПОЛНЫЙ СПРАВОЧНИК)

### Базовые поля
| Поле | Тип | Диапазон | Описание |
|------|-----|----------|----------|
| `id` | string | уникальный | Внутренний идентификатор |
| `name` | string | любой | Отображаемое имя |
| `tier` | string | `major`/`minor`/`mass` | Уровень важности (влияет на модель) |
| `location` | string | ID локации | Где находится NPC сейчас |

### Status Profile (Динамический статус — БЕЗ жёстких ролей)
| Поле | Тип | Диапазон | Описание |
|------|-----|----------|----------|
| `freedom` | int | 0-100 | 0=раб, 50=гражданин, 100=дворянин |
| `wealth` | int | 0-100 | 0=нищий, 100=король |
| `power` | int | 0-100 | Влияние/Сила/Вооружение |
| `title` | string | любой | Динамический заголовок (генерируется) |
| `faction_rank` | object | {} | Ранги во фракциях |

### Visible Markers (Видимые атрибуты — влияют на восприятие)
| Пример | Влияние |
|--------|---------|
| `slave_collar` | -50 к статусу в восприятии |
| `royal_crown` | +50 к статусу в восприятии |
| `heavy_armor` | +20 к угрозе |
| `rags` | -20 к статусу |
| `weapon_melee` | +20 к угрозе |
| `chains` | -40 к статусу, нельзя действовать |

### Hidden Truth (Скрытая информация — игрок не видит)
| Пример | Влияние |
|--------|---------|
| `former_noble` | +10 к реальной силе (если всплывёт) |
| `knows_secret` | Рычаг давления для игрока |
| `slave_collar` (скрыт) | Риск разоблачения при проверке |

### 4 Драйва (Сумма = 1.0) — ЯДРО ЛИЧНОСТИ
| Драйв | Диапазон | Влияние на поведение | Пример речи |
|-------|----------|---------------------|-------------|
| `control` | 0.0-1.0 | Порядок, план, риск-аверсия | «Давай по порядку», «Нужен план» |
| `significance` | 0.0-1.0 | Статус, признание, слава | «Я важен», «Это ниже моего достоинства» |
| `fear` | 0.0-1.0 | Выживание, осторожность | «Осторожно», «А если...», «Может не надо?» |
| `desire` | 0.0-1.0 | Азарт, любопытство, риск | «Интересно!», «А что если?», «Рискнём!» |

**Доминирующий драйв** (get_dominant) определяет стиль речи NPC.

### Psyche Engine (Скрытые статы — ПСИХОЛОГИЯ)
| Поле | Тип | Диапазон | Описание |
|------|-----|----------|----------|
| `willpower` | int | 0-100 | Сопротивление давлению (угрозы, пытки) |
| `stress` | int | 0-100 | Текущий уровень стресса (накапливается) |
| `breakpoint` | int | 0-100 | Порог слома воли |
| `loyalty_true` | int | -100–+100 | Истинное отношение (скрыто от игрока) |
| `loyalty_fake` | int | -100–+100 | Что показывает игроку (если врёт) |
| `state` | string | См. ниже | Текущее психологическое состояние |
| `trauma_flags` | array | список | Травмы, влияющие на будущее |

**Состояния (state):**
- `free` — свободен, действует по своей воле
- `coerced` — принуждён, но сопротивляется
- `broken` — воля сломлена, подчиняется из страха
- `loyal` — добровольно предан игроку
- `deceptive` — притворяется, готовит предательство

### Social Stats (Отношения к игроку)
| Поле | Тип | Диапазон | Описание |
|------|-----|----------|----------|
| `trust` | float | 0.0-1.0 | Доверие к игроку |
| `affection` | float | 0.0-1.0 | Симпатия/любовь |
| `fear_of_player` | float | 0.0-1.0 | Страх перед игроком |
| `debt` | int | 0+ | Долг (золотом или услугами) |

### Relationships (Репутация — сеть связей)
| Ключ | Диапазон | Описание |
|------|----------|----------|
| `player_*` | -100–+100 | Личная репутация у конкретного игрока |
| `npc_*` | -100–+100 | Отношение к другим NPC (если встречались) |
| `faction_*` | -100–+100 | Репутация у фракций |

### Routine (Повседневная жизнь — Life Engine)
| Поле | Тип | Описание |
|------|-----|----------|
| `current` | string | Текущее занятие |
| `mood` | string | `tired`/`neutral`/`angry`/`happy` |
| `interrupted` | bool | Отвлёк ли игрок от дела |
| `next_task` | string | Следующая задача по расписанию |
| `schedule` | object | Расписание по времени |

### Recent Events (Память событий — последние 10)
```json
{"tick": 104, "event": "tax_collector_taken_coins", "impact": "anger"}
```
**Типы impact:** `anger`, `fear`, `joy`, `sadness`, `frustration`, `relief`

### History (История трансформации — для Social Mobility)
```json
{"event": "funded_coup", "date": "2026-03-15"},
{"event": "coronation", "date": "2026-03-20"}
```

### Flags (Флаги состояния)
| Флаг | Тип | Описание |
|------|-----|----------|
| `has_gold` | bool | Есть ли золото |
| `knows_secret` | bool | Знает ли секрет игрока |
| `usurper` | bool | Захватил ли власть незаконно |
| `owed_debt` | bool | Должен ли кому-то |

---

## ⚙️ 3. PYTHON КОД — ВСЕ СЕРВИСЫ

### 3.1 DriveVector (4 Драйва)
```python
# backend/services/npc_cognition.py
from dataclasses import dataclass, field
from typing import Dict

@dataclass
class DriveVector:
    control: float = 0.35
    significance: float = 0.25
    fear: float = 0.15
    desire: float = 0.25

    def normalize(self):
        """Сумма всегда 1.0, чтобы не было перекосов"""
        total = self.control + self.significance + self.fear + self.desire
        if total > 0:
            self.control /= total
            self.significance /= total
            self.fear /= total
            self.desire /= total

    def get_dominant(self) -> str:
        """Возвращает доминирующий драйв для промта (экономия токенов)"""
        drives = {
            "контролирует ситуацию": self.control,
            "ищет славы": self.significance,
            "боится угрозы": self.fear,
            "жаждет приключений": self.desire
        }
        return max(drives, key=drives.get)
```

### 3.2 NPCEvolution (Изменение драйвов от событий)
```python
# backend/services/npc_evolution.py
class NPCEvolution:
    def apply_event(self, npc: NPC, event_type: str, intensity: float):
        """
        intensity: 0.0 - 1.0 (сила события)
        """
        if event_type == 'trauma':
            npc.drives.fear += intensity * 0.1
            npc.drives.desire -= intensity * 0.05
        elif event_type == 'triumph':
            npc.drives.significance += intensity * 0.1
            npc.drives.fear -= intensity * 0.05
        elif event_type == 'betrayal':
            npc.drives.control += intensity * 0.1
            npc.drives.significance -= intensity * 0.05
        elif event_type == 'discovery':
            npc.drives.desire += intensity * 0.1
            npc.drives.control -= intensity * 0.05
        
        npc.drives.normalize()
        npc.save()
```

### 3.3 ThreatAssessor (Оценка угрозы — Python, не LLM)
```python
# backend/services/threat_assessor.py
class ThreatAssessor:
    def calculate_threat(self, player, npc):
        base_threat = 0
        
        # 1. Проверка экипировки (Жёсткая логика)
        if 'heavy_armor' in player.visible_markers:
            base_threat += 30
        if 'weapon_melee' in player.visible_markers:
            base_threat += 20
        if player.combat_mode == True:
            base_threat += 50
            
        # 2. Проверка действия
        if player.action == 'grab_hair':
            base_threat += 40
        if player.action == 'threaten':
            base_threat += 30
            
        # 3. Учёт репутации
        base_threat -= npc.relationships.get('player', 0) // 2
        
        return min(100, base_threat)
```

### 3.4 PsycheEngine (Принуждение, стресс, слом)
```python
# backend/services/psyche_engine.py
class PsycheEngine:
    def resolve_coercion(self, npc, action_type, intensity):
        """
        action_type: 'threat', 'bribe', 'charm', 'torture'
        intensity: 0-100 (сила воздействия)
        """
        # 1. Проверка на мгновенный слом
        if npc.psyche['stress'] + intensity > npc.psyche['breakpoint']:
            npc.psyche['state'] = 'broken'
            npc.psyche['loyalty_true'] = -100
            npc.psyche['stress'] = 100
            return {'outcome': 'submit', 'emotion': 'terror'}
        
        # 2. Проверка на обман (если жадность высокая)
        if action_type == 'bribe' and npc.drives['desire'] > 0.7:
            if self.check_greed_success(npc, intensity):
                npc.psyche['loyalty_fake'] = 80
                npc.psyche['state'] = 'deceptive'
                return {'outcome': 'accept_bribe', 'emotion': 'greedy'}
        
        # 3. Сопротивление
        if npc.psyche['willpower'] > intensity:
            npc.psyche['stress'] += intensity // 2
            return {'outcome': 'resist', 'emotion': 'defiant'}
        
        return {'outcome': 'submit', 'emotion': 'reluctant'}
    
    def tick_stress(self, npc, hours_passed):
        """Стресс спадает со временем в безопасности"""
        if npc.psyche['state'] == 'free':
            npc.psyche['stress'] = max(0, npc.psyche['stress'] - hours_passed * 2)
```

### 3.5 PerceptionEngine (Как NPC видит игрока — Emergent Status)
```python
# backend/services/perception_engine.py
class PerceptionEngine:
    def assess_target(self, observer, target):
        """
        observer: NPC (кто смотрит)
        target: Player (на кого смотрят)
        """
        perception_score = 0
        
        # 1. Видимые маркеры (критично!)
        if "slave_collar" in target.visible_markers:
            perception_score -= 50
        if "royal_crown" in target.visible_markers:
            perception_score += 50
        if "rags" in target.visible_markers:
            perception_score -= 20
        if "heavy_armor" in target.visible_markers:
            perception_score += 20
            
        # 2. Контекст локации
        location = observer.location
        if location == "throne_room" and "royal_crown" not in target.visible_markers:
            perception_score -= 30
            
        # 3. Известная репутация
        rep = target.relationships.get(observer.id, 0)
        perception_score += rep // 2
        
        return {
            "perceived_status": "low" if perception_score < 20 else "high",
            "threat_level": "high" if perception_score > 70 else "low",
            "social_permission": self._get_permission(perception_score)
        }
    
    def _get_permission(self, score):
        """Что разрешено делать с целью berdasarkan статуса"""
        if score < 10:
            return ["insult", "push", "ignore", "buy"]
        elif score < 50:
            return ["talk", "trade", "threaten"]
        else:
            return ["bow", "serve", "listen"]
```

### 3.6 LifeEngine (Фоновая симуляция)
```python
# backend/services/life_engine.py
class LifeEngine:
    def tick(self, world_state):
        for npc in world_state.get_active_npcs():
            if npc.tier == 'minor':
                self._update_routine(npc)
                self._check_random_events(npc)
    
    def _update_routine(self, npc):
        current_hour = world_state.get_game_time().hour
        if 8 <= current_hour < 18:
            npc.routine['current'] = 'working'
            npc.routine['mood'] = 'tired' if npc.hours_worked > 6 else 'neutral'
        elif 18 <= current_hour < 22:
            npc.routine['current'] = 'family_time'
            npc.routine['mood'] = 'relaxed'
        else:
            npc.routine['current'] = 'sleeping'
    
    def _check_random_events(self, npc):
        if random.random() < 0.05:
            event = random.choice(['child_sick', 'crop_pest', 'tax_collector'])
            npc.recent_events.append({
                'event': event, 
                'tick': world_state.tick,
                'impact': self._get_impact(event)
            })
            npc.recent_events = npc.recent_events[-10:]
```

### 3.7 SocialMobility (Динамическая смена ролей)
```python
# backend/services/social_mobility.py
class SocialMobility:
    def check_role_change(self, npc, player_action):
        conditions = {
            'slave_to_free': {
                'freedom_required': 50,
                'markers_remove': ['slave_collar', 'chains'],
                'new_title': 'Вольный гражданин'
            },
            'commoner_to_noble': {
                'wealth_required': 80,
                'power_required': 60,
                'markers_add': ['noble_robes'],
                'new_title': 'Лорд'
            }
        }
        
        for condition_name, requirements in conditions.items():
            if self._check_all(npc, player_action, requirements):
                self._apply_transformation(npc, requirements)
                self._log_history(npc, condition_name)
                return True
        return False
    
    def _apply_transformation(self, npc, requirements):
        npc.status_profile['title'] = requirements['new_title']
        if 'markers_remove' in requirements:
            for m in requirements['markers_remove']:
                if m in npc.visible_markers:
                    npc.visible_markers.remove(m)
        if 'markers_add' in requirements:
            npc.visible_markers.extend(requirements['markers_add'])
```

### 3.8 KarmaEngine (Цепные реакции репутации)
```python
# backend/services/karma_engine.py
class KarmaEngine:
    def process_action(self, action, actor):
        consequences = []
        
        consequences.append(Consequence(
            target=action['target'],
            type='reputation_change',
            value=-10 if action['type'] == 'betrayal' else +5
        ))
        
        if action.get('target_faction'):
            allies = self._get_allies(action['target_faction'])
            for ally in allies:
                consequences.append(Consequence(
                    target=ally,
                    type='indirect_reputation',
                    value=-3
                ))
        
        if action.get('severity', 0) > 7:
            consequences.append(Consequence(
                target=action['target'],
                type='delayed_event',
                trigger='world_tick',
                delay_ticks=3,
                event='revenge_attempt'
            ))
        
        return consequences
```

---

## 🧩 4. ИНТЕГРАЦИЯ С LLM (ПРОМТ)

```python
# backend/app/agents/npc_agent.py
def build_npc_prompt(npc, player):
    dominant_drive = npc.drives.get_dominant()
    perception = PerceptionEngine.assess_target(npc, player)
    threat_level = ThreatAssessor.calculate_threat(player, npc)
    
    true_feeling = 'искренние чувства'
    if npc.psyche['state'] == 'deceptive':
        true_feeling = 'ненависть (скрыта)'
    elif npc.psyche['state'] == 'broken':
        true_feeling = 'ужас и покорность'
    
    system_prompt = f"""
Ты {npc.name}, {npc.status_profile['title']}.
Твоё состояние: {dominant_drive}.
Настроение: {npc.routine['mood']}.
Занятие: {npc.routine['current']} (прервано: {npc.routine['interrupted']}).
Восприятие игрока: {perception['perceived_status']}.
Разрешённые действия: {perception['social_permission']}.
Угроза от игрока: {'ВЫСОКАЯ' if threat_level > 50 else 'НИЗКАЯ'} (доспехи={('heavy_armor' in player.visible_markers)}).
Отношение к игроку: {true_feeling}.
Последние события: {[e['event'] for e in npc.recent_events[-3:]]}.

Твоя задача: Ответить игроку, оставаясь в角色.
- Если ты занят — прояви нетерпение.
- Если состояние 'broken' — подчиняйся, но с дрожью в голосе.
- Если состояние 'deceptive' — ври убедительно.
- Если угроза ВЫСОКАЯ — учитывай страх.
- Если восприятие 'low' — ты можешь игнорировать или оскорблять.
Не упоминай цифры или драйвы.
"""
    return system_prompt
```

### Inner Thought (для прозрачности)
```python
inner_thought = f"""
[Внутренняя мысль {npc.name}]
Драйв: {dominant_drive}
Стресс: {npc.psyche['stress']}/100
Истинная лояльность: {npc.psyche['loyalty_true']}
Восприятие игрока: {perception['perceived_status']}
План: {'подчиниться и ждать шанса' if npc.psyche['state'] == 'broken' else 'действовать по ситуации'}
"""
```

---

## 🔄 5. ПОЛНЫЙ ЦИКЛ ВЗАИМОДЕЙСТВИЯ

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. ИГРОК ДЕЙСТВУЕТ                                              │
│    /action threaten "Говори где золото!"                        │
│    visible_markers: ["heavy_armor", "sword"]                    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. THREAT ASSESSOR (Python, <50ms)                              │
│    armor=30 + weapon=20 + action=30 = 80 threat                 │
│    → fear_of_player += 0.2                                      │
│    → stress += 40                                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. PERCEPTION ENGINE (Python, <50ms)                            │
│    visible_markers проверяются                                  │
│    → perceived_status: "low" (если раб) / "high" (если лорд)    │
│    → social_permission: ["insult"] / ["bow"]                    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. PSYCHE ENGINE (Python, <50ms)                                │
│    stress(60) + intensity(80) = 140 > breakpoint(90)            │
│    → STATE: 'broken'                                            │
│    → loyalty_true: -100                                         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. LLM NPC AGENT (получает результат)                           │
│    Prompt: "Состояние: broken, Угроза: ВЫСОКАЯ, Восприятие: ..."│
│    → Генерирует: "Х-хорошо... в сарае, под сеном..."            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. СОХРАНЕНИЕ В JSON                                            │
│    - psyche.state = 'broken'                                    │
│    - recent_events.append('threatened_by_player')               │
│    - social_stats.fear_of_player = 0.3                          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 7. KARMA ENGINE (цепная реакция)                                │
│    - reputation['cruel'] += 10                                  │
│    - Если отпустит → через 3 тика: revenge_attempt              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 8. LIFE ENGINE (фон, каждые 15 мин)                             │
│    - Обновляет routine (время дня)                              │
│    - Проверяет random_events (5% шанс)                          │
│    - Снижает stress если в безопасности                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📈 6. ТАБЛИЦА ПРИМЕРОВ ПОВЕДЕНИЯ

| Драйв | Стресс | Статус | Восприятие | Действие игрока | Реакция NPC |
|-------|--------|--------|------------|-----------------|-------------|
| Control 0.7 | 20 | 50 | high | Угроза | «Давай обсудим это разумно» |
| Fear 0.8 | 50 | 50 | high | Угроза | «Пожалуйста, не надо!» |
| Desire 0.7 | 30 | 50 | high | Взятка | «Сколько предлагаешь?» |
| Any | 85 | 50 | high | Угроза | «Ладно... но это не закончится хорошо» |
| Any | 95+ | 50 | high | Угроза | «Я всё скажу! Только не бейте!» |
| Any | 40 | 0 | low | Приказ | «Пошёл ты, раб!» (игнорирует) |
| Any | 40 | 100 | high | Приказ | «Слушаюсь, господин!» |

---

## 🎯 7. ИТОГОВАЯ АРХИТЕКТУРА

```
┌─────────────────────────────────────────────────────────────────┐
│                        NPC JSON (файл)                          │
│  drives + psyche + social_stats + status_profile + markers      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    PYTHON SERVICES (логика)                     │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────────┐ │
│  │NPCEvolution │ │PsycheEngine │ │LifeEngine   │ │KarmaEngine│ │
│  │(драйвы)     │ │(стресс/слом)│ │(рутина)     │ │(репутация)│ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └───────────┘ │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐               │
│  │Threat       │ │Perception   │ │Social       │               │
│  │Assessor     │ │Engine       │ │Mobility     │               │
│  │(угроза)     │ │(восприятие) │ │(роли)       │               │
│  └─────────────┘ └─────────────┘ └─────────────┘               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    LLM AGENT (интерпретация)                    │
│  Получает цифры → Генерирует текст + inner_thought              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    UI / ИГРОК                                   │
│  Видит текст, может включить "Показать мысль"                   │
│  НЕ видит цифры (кроме Debug Mode)                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## ✅ 8. CHECKLIST ДЛЯ РАЗРАБОТКИ

- [ ] **Создать `backend/services/npc_cognition.py`** (4 Драйва + normalize)
- [ ] **Создать `backend/services/psyche_engine.py`** (Willpower, Stress, Breakpoint)
- [ ] **Создать `backend/services/threat_assessor.py`** (Оценка угрозы экипировки)
- [ ] **Создать `backend/services/perception_engine.py`** (Видимые маркеры, статус)
- [ ] **Создать `backend/services/life_engine.py`** (Routine, Mood, Random Events)
- [ ] **Создать `backend/services/karma_engine.py`** (Chain Reactions)
- [ ] **Создать `backend/services/social_mobility.py`** (Dynamic Role Change)
- [ ] **Обновить `backend/app/agents/npc_agent.py`** (Промт с цифрами)
- [ ] **Обновить JSON схему NPC** (Все поля из раздела 1)
- [ ] **Добавить тесты** (`test_psyche_engine.py`, `test_drives.py`, `test_threat.py`)
- [ ] **Добавить UI toggle** ("Показать мысль NPC")
- [ ] **Добавить Debug Mode** (Видеть все цифры в инспекторе)

---

## 🏁 ФИНАЛЬНЫЙ ПРИНЦИП

> **Цифры в коде → LLM интерпретирует → Игрок видит текст**
> 
> NPC умный не потому что думает 24/7, а потому что **помнит свою жизнь** и **реагирует через систему драйвов**.
> 
> **НЕТ жёстких ролей** — статус = видимые маркеры + контекст + репутация.
> 
> **LLM не считает** — LLM драматизирует результат вычислений Python.
> 
> **Угроза считается в Python** (доспехи, меч, действие) → **LLM получает готовую оценку** → **Игрок видит реалистичную реакцию**.

Это делает мир живым без нагрузки на VRAM, потому что симуляция происходит только в момент записи в JSON, а не в реальном времени для каждого NPC.






📋 РЕАЛЬНЫЙ ПЛАЙПЛИН: ОТ API К ИГРЕ
🟢 ФАЗА 1: ИГРОВОЙ ЦИКЛ (1-2 недели)
Цель: Один полный ход игры от ввода до результата
Игрок вводит → Парсинг → Rules Check → DM Response → UI Update → Memory Save
Что доделать:
Задача
Файл
Статус
Парсинг действий игрока (естественный язык → структурировано)
backend/app/services/parser.py
❌ 0%
Валидация действий по правилам D&D 5e
backend/app/agents/rules_agent.py
⚠️ 25%
Синхронизация агентов (чтобы Rules → DM → Memory шли по порядку)
backend/app/services/orchestrator.py
⚠️ 75%
Сохранение состояния после каждого хода
backend/app/services/memory.py
✅ 100%
Критерий готовности: Игрок пишет "Атакую гоблина мечом" → система понимает → проверяет правила → генерирует ответ → сохраняет в память.

🟡 ФАЗА 2: ВИЗУАЛЬНЫЙ ИНТЕРФЕЙС (2-3 недели)
Цель: Игрок видит что происходит, не только читает текст
Минимальный UI:
┌─────────────────────────────────────────────────────┐
│  Enigma DM — Затерянные Рудники Фанделвера         │
├─────────────────────────────────────────────────────┤
│  [КАРТА]          │  [ЧАТ]                          │
│  🗺️ Миникарта    │  DM: Вы видите гоблина...       │
│  📍 Локация       │  Вы: Атакую мечом!              │
│                   │  DM: Бросок атаки: 15 (попал!)  │
├───────────────────┴─────────────────────────────────┤
│  [ПЕРСОНАЖ] Ария | Эльф | Плут | Ур.3               │
│  ❤️ HP: 18/24   |  🎒 Инвентарь |  ⚔️ Атака: +5   │
├─────────────────────────────────────────────────────┤
│  [Ввод действия...]                    [Отправить]  │
└─────────────────────────────────────────────────────┘

Что доделать:
Задача
Файл
Статус
Веб-интерфейс с чатом
frontend/ui/index.html
⚠️ 40%
Панель персонажа (HP, инвентарь)
frontend/ui/character_panel.html
❌ 0%
Отображение локации
frontend/ui/location_view.html
❌ 0%
WebSocket для live-обновлений
backend/app/api/websocket.py
❌ 0%
Критерий готовности: Игрок видит свой HP, локацию, и чат обновляется без перезагрузки.

🟠 ФАЗА 3: ПРАВИЛА D&D 5e ПОЛНЫЕ (3-4 недели)
Цель: Система понимает и применяет правила, а не просто генерирует текст
Что доделать:
Задача
Файл
Статус
Броски характеристик (d20 + mod vs DC)
backend/app/services/rules_engine.py
❌ 0%
Система заклинаний (ячейки, компоненты)
backend/app/services/spell_system.py
❌ 0%
Состояния (отравлен, парализован, и т.д.)
backend/app/models/conditions.py
❌ 0%
Боевая система (инициатива, ходы, действия)
backend/app/services/combat.py
⚠️ 50%
Инвентарь и оборудование
backend/app/services/inventory.py
❌ 0%
Критерий готовности: Игрок может провести полноценный бой с использованием заклинаний, способностей и правил.


🔴 ФАЗА 4: КОНТЕКСТ ПРИКЛЮЧЕНИЯ (2-3 недели)
Цель: Модель знает "Затерянные Рудники Фанделвера" и использует этот контекст
Что доделать:
Задача
Файл
Статус
Векторная БД для RAG (Chroma/FAISS)
backend/app/services/vector_db.py
❌ 0%
Индексация PDF приключения
backend/app/services/pdf_indexer.py
⚠️ 50%
Поиск контекста по запросу игрока
backend/app/services/context_retriever.py
❌ 0%
Привязка локаций/NPC к приключению
backend/app/services/campaign_loader.py
⚠️ 60%
Критерий готовности: Когда игрок спрашивает "Кто такой Гандрен?", система находит ответ в PDF, а не выдумывает.

# 1. Исправить orchestrator.py чтобы агенты работали последовательно
# 2. Добавить парсинг действий игрока (natural language → structured)
# 3. Тест: один полный ход через curl

# 4. Заменить index.html на рабочий чат с историей
# 5. Добавить панель персонажа (HP, имя, класс)
# 6. Тест: игрок видит ответ DM в браузере

# 7. Подключить RAG по PDF "Затерянные Рудники"
# 8. Тест: модель знает Гандрена, Фандалин, Чёрного Паука
# 9. Первая полноценная сессия

Что для  важнее прямо сейчас? - Стабильный игровой цикл (ход → ответ → память)