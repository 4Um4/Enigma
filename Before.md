Итоговая таблица архитектурных решений (финальная):
  #Решение1NPCState — источник истины2Intent хранится в NPCState3Event-trigger + редкий idle тик4Enum + фильтр доступности5RelationshipStore + кэш в NPCState6emotion_base + Σ(delta × decay)7Risk из контекста (свидетели, дистанция, сила)8Радиус → Perception (два фильтра)9DecisionHub = read-only. StateApplicator = write-only10LifeEngine = фоновый тик11intent + emotion + fact-hint ≤ 100 токенов12±10% randomness, seed per-session13Цель: 10–30 NPC, запас до 5014Старт: только R1.1



Memory reinforcement — принимаю концепцию, но реализацию отклоняю.
Проблема: мутируешь EventMemory внутри цикла — но EventMemory frozen. Правильно: ResonanceEngine создаёт новые объекты с повышенным importance, не мутирует существующие.
InternalVoice (Disco Elysium) — принимаю как R5.3.
Голоса в голове NPC из чисел — это архитектурно чистое решение. "Паранойя" при suspicious > 0.6 генерирует строку для debug/F12 и может стать частью emotional_nuance.
WorldLegend (Dwarf Fortress) — принимаю как R6.
Требует NPC-NPC EventBus — ещё не реализован.
NPCScheme (CK3) — принимаю как R6.
Требует Goal Layer. Правильная очерёдность: сначала R5 полностью, потом R6.
ResonanceEngine — принимаю как R5.4.
Паттерн-детектор поверх EventMemory. Правильная архитектура — читает, не мутирует.


Потенциал.md — приоритетная таблица систем для wow-эффекта. Память (100%) — закрыта. Энергетический слой (95%) — частично закрыт через stress/willpower. Вероятностная судьба (85%) — это R7. Скрытые цели (85%) — R10.
Из предложений: calculate_clarity из PerceptionFilter — берём в R5.3. ResonancePattern — R5.4. Thought Cabinet, Legends, Schemes — R10.

Обновлённая дорожная карта:
R1 ✅  Memory Core
R2 ✅  Decision Core
R3 ✅  Verbalization Layer
R4 ✅  Calibration + Coordinates

R6 — BREAK SYSTEM (Слом.md)
  R6.1  NPCState +: resentment, dependency, identity_integrity
  R6.2  BehaviorMask: FAKE_SUBMISSION, BETRAYAL, COLLAPSE
         (расширение WillState, не замена)
  R6.3  OpportunityEngine: когда сломленный NPC действует
  R6.4  BreakProgressEngine: давление → трещины → слом
         (процесс, не бинарное переключение)

R7 — RESOLUTION LAYER (DICE.md)
  R7.1  expected_success → DecisionResult (заготовка есть)
  R7.2  ResolutionEngine: roll + bias → final_value
         bias = stat_mod + context_mod + npc_state_mod
  R7.3  OutcomeMapping: 6 уровней градиента (не hit/miss)
  R7.4  gap = actual - expected → источник traits и травм
  R7.5  Anti-exploit: штраф за повторные броски,
         diminishing returns на однотипные действия

R8 — CHARACTER CONSTRAINT (player layer)
  R8.1  CharacterProfile: traits, willpower, conflicts
  R8.2  ConstraintEngine: affinity = f(traits, intent)
         soft resistance, не hard lock
  R8.3  Stress cost при отклонении от характера

R9 — SOCIAL NETWORKS
  R9.1  NPC↔NPC RelationshipMatrix (не только player↔NPC)
  R9.2  Rumor propagation: события распространяются между NPC
  R9.3  Reputation system: репутация игрока в регионе

R10 — DEEP SYSTEMS (будущее)
  R10.1  NPC meta-learning (адаптация к паттернам игрока)
  R10.2  Contextual modifiers (время суток, погода, шум)
  R10.3  World Legends (географическая память событий)
  R10.4  NPC Schemes (долгосрочные планы, риск раскрытия)
  R10.5  Thought Cabinet (активные мысли → модификаторы DecisionHub)

R11 — OPTIMIZATION
  R11.1  Async IO
  R11.2  Batching LLM (30+ NPC)
  R11.3  lru_cache для _score_one


  Запустил:
bashpython -m pytest tests/test_event_memory.py tests/test_perception_filter.py -v --tb=short
После зелёного — R5.3: ImportanceEngine обновление + L3 Identity. Нужен файл importance_engine.py.


R5.2✅ Закрытclarity/confidence → verbalization prompt (тесты test_fresh_memory_shows_event_type и test_abstract_memory_obscures_event проходят)
Что дальше (следующий логичный шаг):
R5.3 — L3 Identity
Ключевые вещи, которые нужно сделать:
calculate_clarity() в PerceptionFilter (уже частично есть в тестах test_perception_filter.py)
Обновление ImportanceEngine — чтобы он учитывал не только базовые правила, но и контекст (emotional_intensity, identity_impact)
Механизм формирования L3 traits из повторяющихся паттернов (пока только заглушка to_identity_weight)
Интеграция новых traits обратно в NPCState.active_traits и DecisionHub
Итог по R5.3:
Что мы уже сделали (закрыто):
✅ calculate_clarity() — существует в perception_filter.py и используется.
✅ Обновили importance_engine.py — теперь score_event() принимает clarity, stress, emotion_tag.
✅ Добавили create_event_memory() в MemoryManager — правильный способ создания EventMemory с реальным восприятием.
✅ Подключили вызов create_event_memory() в python_engines.py (в R2.5 блоке).
✅ EventMemory.to_identity_weight() уже существует (заглушка).

Вывод: Основная инфраструктура R5.3 готова и работает.
Что ещё не сделано в R5.3 (осталось):
Механизм автоматического формирования L3 traits из to_identity_weight()
(сейчас метод существует, но никто его не вызывает).
Накопление этих traits в NPCState.active_traits.
Передача новых traits в DecisionHub (чтобы они влияли на решения NPC).

Следующий логичный шаг — R5.4 (ResonanceEngine / L3 Identity accumulation)
Это будет включать:

Вызов to_identity_weight() при переходе памяти в ABSTRACT или при вытеснении из кэша.
Накопление traits в NPCState.active_traits.
Использование этих traits в DecisionHub.score().

apply_decay() в WorkingMemory — decay есть, но ABSTRACT-переход не детектируется
run_decay_if_needed() в MemoryManager — дублирует decay-логику WorkingMemory, не возвращает trait deltas

Что отсутствует:
Детекция перехода → ABSTRACT в WorkingMemory.apply_decay()
Возврат identity weights через run_decay_if_needed()
Применение этих weights к NPCState.active_traits в python_engines.py

18/18. R5.3 закрыт.
R5.1 ✅  EventMemory (clarity, confidence, lifecycle, decay)
R5.2 ✅  clarity/confidence → verbalization prompt
R5.3 ✅  L3 Identity: trait accumulation из ABSTRACT-переходов
         + decay asymmetry (angry=0.03, happy=0.07)
R5.4 ✅?  ResonanceEngine
R5.5 ✅  Personality Modulation

§6Reinforcement через связи (тот же actor, тот же тип) R5.4
§10if Σ related_events > threshold: create_trait() R5.4
 Отдельный шаг.
Emotional Trajectory, Escalation, Failed Pattern — R5.5/R5.6. 

Следующий шаг — BREAK SYSTEM (Слом.md)
  R6.1  NPCState +: resentment, dependency, identity_integrity