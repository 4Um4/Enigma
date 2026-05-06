
---
ADR-001: Изоляция мутаций через Phase8Result и Delta Buffer (05.05.2026 22:25)
Статус: Принято
Контекст
Обработчики Фазы 8 (Social, Perception) имели два пути влияния на состояние: возврат DTO и прямая мутация общих объектов (shared_context, all_npcs_raw). Это приводило к побочным эффектам, состоянию гонки и невозможности формальной синхронизации perception ∪ social. Фронтенд нарушал Устав §1.1, импортируя backend-классы для конвертации DTO.

Решение
Подписчики Фазы 8 возвращают только Phase8Result. Прямая мутация shared_context и all_npcs_raw запрещена.
Интенсивность событий агрегируется через max(), а не суммируется или обрывается (break).
Конвертация DTO→dict происходит на границе слоев (в GameLoop), фронтенд работает только с примитивными dict.
Оркестратор собирает deltas в delta_buffer и применяет через StateApplicator единственной транзакцией.
Последствия
Предсказуемость: нет скрытых мутаций. Оркестратор видит все изменения через буфер.
Безопасность: инфляция слухов исключена (max агрегация).
Заменимость: фронтенд отвязан от структур backend.
Требуется строгая дисциплина: любой новый обработчик должен возвращать дельты, а не писать в стейт.
---
ADR-002: Time-driven vs Event-driven разделение и единый мутатор (27.04.26)
Статус: Принято
Контекст
Social отношения (trust, affection) и репутация фракций стагнировали между player-взаимодействиями — idle path не обновлял эти подсистемы. Фаза 8 пропускала обработку в idle path из-за guard if ctx.shared_context is None: continue. StateApplicator хардкодил target = state.intent_target or "player" для trust/fear, что не подходило для social decay (NPC→NPC дрейф). ReputationEngine мутировал состояние через apply_deltas(List[dict]), минуя единый мутатор.

Решение

Фаза 0.5 (time-driven) отделена от Фазы 8 (event-driven). Фаза 0.5 выполняется ВСЕГДА (idle + player path) — время не останавливается. Фаза 8 обрабатывает только если есть events (if not events: continue).
StateDeltas расширена явной маршрутизацией: intent_target (NPC→Player), social_target (NPC→NPC), faction_id (фракции). post_init валидация: один тип таргета в дельте, reputation_delta только с faction_id, trust/fear несовместимы с faction_id. # LOCKED v1 — новые домены через отдельный рефакторинг.
IdleTickHandler Protocol: чистая функция, принимает List[NPCStateSnapshot] (READ-ONLY проекция), возвращает List[StateDeltas]. Handlers изолированы от сырого all_npcs_raw.
ReputationEngine.compute_decay() — чистая функция, возвращает List[StateDeltas] с faction_id. apply_deltas() — единственная точка мутации, вызывается только из StateApplicator._apply_faction_delta().
Closing drift: если |base - current| < EPSILON → drift = base - current. Гарантирует достижение равновесия без микро-осцилляций.
Оркестратор собирает idle-дельты в delta_buffer → aggregate_deltas() (группировка по npc_id+target с суммированием) → StateApplicator.apply_batch() в Фазе 10. Никаких прямых мутаций all_npcs_raw.
Последствия

Детерминированная симуляция: decay не зависит от активности игрока
Единый мутатор: StateApplicator.apply_batch() — единственная точка применения всех дельт
Семантическая изоляция: reputation_delta ≠ trust_delta, faction_id ≠ social_target
Тестируемость: handlers — чистые функции, легко мокать
StateDeltas растёт (TODO v2: split на BaseDelta + SocialDelta/FactionDelta/EmotionDelta)
apply_batch() требует dict→NPCState→_apply_deltas→dict мост (тонкий, без бизнес-логики)
aggregate_deltas() — примитивная дедупликация, порядок source может теряться при слиянии
---
ADR-003: Детерминизм тестового покрытия и изоляция от I/O (Текущая дата)
Статус: Принято
Контекст
После внедрения ADR-001 и ADR-002 тестовое покрытие оказалось сломано: 1) Фабрики DTO не передавали обязательный npc_id в StateDeltas, что ломало маршрутизацию дельт в оркестраторе. 2) Юнит-тесты когнитивного пайплайна (test_player_cognition_pipeline.py) зависели от чтения campaign_state.json с диска (Fragile Test), что вызывало pytest.skip на чистых сборках и нарушало предсказуемость. 3) Наличие мертвых тестов, отключенных через @pytest.mark.skip("BROKEN"), маскировало удаление сущностей (load_graph, build_verbalization_context) и нарушало Устав §10.

Решение:
Строгое соблюдение контракта DTO: npc_id сделан обязательным аргументом во всех тестовых фабриках make_deltas(). Тест, не указавший npc_id, падает (TypeError), а не проходит с невалидным состоянием.
Устранение Fragile Tests: хрупкие фикстуры, зависящие от I/O (real_scene_state), заменены на детерминированные синтетические фабрики (_make_rich_scene()), генерирующие состояние в памяти.
Полная зачистка мертвого кода: удалены файлы и классы, тестирующие удаленные сущности. Динамические pytest.skip("BROKEN...") признаны архитектурным нарушением и заменены удалением теста.
Приведение координат к fallback-графу: local_position в тестах SpatialService приведены в соответствие с логикой вычисления дистанций без реального графа.
Последствия
100% детерминированность тестового набора (0 FAILED, 0 illegitimate SKIPPED).
Тесты можно запускать на любой машине без подготовки данных кампаний.
ИИ-ассистенты получают четкий сигнал: старый код удален, новые контракты (npc_id) обязательны к исполнению.
---
ADR-003: Phase 8 Handlers — Memory, Scene, Reaction (27.05.26)
Статус: Принято
Контекст
Диаграмма Фазы 8 предписывает 4 обработчика: memory, social, scene, reaction. Существовали только perception + social. Требовалось решение по каждому.

Решение

Memory handler — НЕ НУЖЕН как Phase8Handler
Обоснование:
Фаза 3 (MemoryProcessor.apply()) записывает факты в память ДО принятия решения (Phase 5).
Это гарантирует актуальность state для DecisionHub (Устав §3.1, §7.7).
Если memory обработка будет в Фазе 8 — NPC уже принял решение на устаревшем state.
NPC-реплики (Phase 6→7→EventBus) обрабатываются в Phase 3 СЛЕДУЮЩЕГО тика.
Memory "drain" эффекты (травма от воспоминаний) — это Reaction-домен, не Memory.
Scene handler — НЕ НУЖЕН как Phase8Handler
Обоснование:
OBJECT_DESTROYED уже в _PERCEPTION_EVENT_TYPES — восприятие обрабатывается.
ReactionSubscriber покрывает эмоциональные реакции на смену сцены.
SceneStateManager.commit() в Фазе 10 — единственная точка записи состояния сцены.
Смена локации/разрушение объекта — SceneChange → EventDTO → шина → perception/reaction.
Добавление SceneSubscriber создаст дублирование.
Reaction handler — НУЖЕН, создан ReactionSubscriber
Обоснование:
PerceptionSubscriber определяет КТО видит, SocialSubscriber — слухи,
но никто не производит ПРЯМЫЕ эмоциональные дельты для наблюдателей.
NPC видит атаку → стресс/страх растут, доверие падает,
но без полного decision-цикла (Phase 5) и без LLM.
Порядок: perception → reaction → social
(perception фильтрует, reaction считает дельты, social распространяет слухи)
Последствия
Фаза 8 имеет 3 обработчика (perception, reaction, social) вместо 4 из диаграммы.
Диаграмма обновлена. Memory и Scene НЕ будут добавлены без нового ADR.
---
ADR-004: NPC Data Mapping для Idle Handlers (27.05.26)
Статус: Принято
Контекст
_build_npc_snapshots() читал ключ relationship_cache из NPC dict, но этот ключ не существует. NPC dict хранит социальные данные в social_stats (плоский формат: {trust, fear_of_player, debt}) — это player-facing только. NPC-to-NPC связи хранятся отдельно в village_relations.json. Результат: SocialDecayHandler всегда получал пустой кэш → нулевой social decay для всех NPC.

Решение
_build_npc_snapshots() выполняет маппинг при проекции:

social_stats.trust → relationship_cache["player"]["trust"] (0-100)
social_stats.fear_of_player → relationship_cache["player"]["fear"]
social_stats.debt → relationship_cache["player"]["debt"]
psyche.loyalty_true → base_values["player"] (базовое доверие для drift-расчёта)
status_profile.faction_rank.keys → faction_affiliations
Если relationship_cache уже во вложенном формате — используется как есть
Плоский кэш {trust: val} автоматически конвертируется
Последствия
SocialDecayHandler теперь корректно вычисляет дрейф trust к базовому значению.
Ограничение: NPC-to-NPC связи из village_relations.json пока НЕ попадают в snapshot.
Требуется отдельная задача: _enrich_with_social_relations() при загрузке NPC.
---
ADR-0006: Централизация пространственных данных и удаление глобальных мостов
Статус
Принято (реализовано частично, заблокировано багами E2E)

Контекст
В системе существовало несколько источников истины для пространственных данных: глобальный словарь _connections_data в graph_compiler.py, кэш _graphs в MovementEngine, и прямые вызовы LocationGraph.find_path(). Это приводило к рассинхронизации, дублированию логики и невозможности полноценно использовать оверлеи (блокировки, толпа) при поиске пути. Также фронтенд незаконно обращался к бэкенду напрямую через _gateway._bridge, минуя API-слой.

Решение
Удалить глобальный мост _connections_data. compile_graph теперь возвращает связи явным кортежем, которые сразу забирает SpatialService.
Удалить кэш _graphs и _get_graph из MovementEngine. Единственным источником пути теперь является SpatialService.find_path().
Удалить denormalize_id при записи в TransitTracker. Внутри системы используются только канонические ID.
Оборвать прямые вызовы фронтенда к бэкенду. Бэкенд обогащает scene_state стенами перед отправкой, а фронтенд сам собирает PerceivedScene из легальных данных.
Последствия
Положительные: Единая точка входа для навигации, учет оверлеев, соблюдение Архитектурного Устава.Отрицательные: Требуется строгий DI SpatialService во все ветки тика (и в player, и в idle), иначе NPC теряют способность двигаться. Требуется починка interpretation_engine для корректного доступа к драйвам.
---

---