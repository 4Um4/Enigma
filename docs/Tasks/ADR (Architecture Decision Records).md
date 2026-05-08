
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
ADR-005: NPC-to-NPC Social Relations Enrichment при загрузке (27.05.26)
Статус: Принято
Контекст
_build_npc_snapshots() маппил только player-facing данные из social_stats (trust, fear_of_player). NPC-to-NPC связи из village_relations.json (base_trust, base_affection, nature) НЕ попадали в NPC dict. SocialDecayHandler не мог считать дрейф для NPC→NPC отношений — relationship_cache содержал только entry "player". Функция load_social_base() существовала, но никто не вызывал её для обогащения NPC dict.

Решение
Создана _enrich_with_social_relations() — обогащает каждый NPC dict данными из village_relations.json.
Вызывается в load_npcs_merged() ПОСЛЕ мержа static + runtime, во всех 3 return-путях.
Шкала: village_relations использует 0-1, SocialDecayHandler ожидает 0-100. Конвертация base_trust * 100.
Формат обогащения: relationship_cache[target_npc_id] = {trust, fear, base_trust, nature}, base_values[target_npc_id] = base_trust * 100.
Не перезаписывает существующие записи (runtime мог мутировать).
Критический фикс _build_npc_snapshots(): после обогащения relationship_cache уже вложенный → старый код брал «как есть» и ПРОПУСКАЛ player entry из social_stats. Исправлено: shallow copy + гарантированное добавление player entry. Аналогично для base_values — player из loyalty_true.
Последствия
SocialDecayHandler теперь производит NPC→NPC дрейф (раньше — только player-facing).
Player drift НЕ ломается при наличии NPC→NPC записей (гарантированный player entry).
village_relations.json — единственный источник NPC→NPC базовых связей. Runtime мутации идут через delta_buffer.
Ограничение: enrichment мутирует NPC dicts in-place. Это допустимо только потому что вызывается один раз при загрузке.
---
ADR-004: Синхронизация all_npcs_raw в idle-пути TickOrchestrator (05.05.2026)
Статус: Принято
Контекст
При внедрении ADR-002 (единый мутатор) и ADR-001 (Phase8Result) выявилась рассинхронизация в idle-пути TickOrchestrator. Фаза 0 заполняла ctx.npc_states из LifeEngine, но ctx.all_npcs_raw (используемый StateApplicator.apply_batch() в Фазе 10) оставался пустым списком по умолчанию. Это приводило к потере дельт: StateApplicator применял стресс/доверие к пустому списку, а Фаза 10 сохраняла неизмененный ctx.npc_states. Сквозной дым-тест выявил этот баг.

Решение
В _phase_0_simulation после получения npc_states из LifeEngine добавлена явная синхронизация: ctx.all_npcs_raw = ctx.npc_states. Это гарантирует, что единый мутатор работает с актуальным стейтом, а Фаза 10 сохраняет уже мутированный словарь.

Последствия
Целостность данных: Дельты из Фазы 8 (Perception, Reaction, Social) теперь корректно применяются в idle-тиках и сохраняются на диск.
Единая истина: ctx.npc_states и ctx.all_npcs_raw в idle-пути ссылаются на один и тот же объект в памяти, устраняя дрейф.
Побочный эффект: Изменения в ctx.all_npcs_raw через StateApplicator мутируют ctx.npc_states напрямую. Это приемлемо, так как Фаза 9 читает scene_state, а Фаза 10 делает коммит после мутаций.
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
ADR-0007: Инъекция примитивов вместо объектов в InterpretationEngine (Текущая дата)
Статус: Принято
Контекст
InterpretationEngine падал с ошибкой 'NPCState' object has no attribute 'personality', так как профиль L0 передавался неявно или ожидался внутри state. Это нарушало Закон 1.2 (доменные модели не знают о сервисах) и приводило к хрупким связям.
Решение
Вместо передачи всего объекта profile_l0 (или добавления personality в NPCState), в метод compute() добавлен аргумент drives_base: Dict[str, float]. InterpretationEngine получает только те данные, которые ему нужны для работы, и не знает о структуре NPCPersonality.
Последствия

Снижение связности (Law of Demeter).
Устранение краша пайплайна.
Рост количества аргументов в методах (potential parameter bloat), требует контроля.
---
ADR-0008: Макро-зоны SpatialService vs Микро-зоны Archetypes
Статус: Принято
Контекст
SpatialService v1.2 собирает граф локации из Editor JSON, который оперирует макро-зонами (main_hall, bar_area — 7 узлов на локацию). Конфиги NPC (archetypes) и старый scene_state используют микро-зоны (serving_table_3, gate_post, bed — десятки узлов). При поиске пути MovementEngine не находит микро-зону в макро-графе и отменяет движение. NPC парализованы.
Решение

Архетипы NPC должны ссылаться только на валидные узлы макро-графа (main_hall вместо serving_table_3).
MovementEngine должен иметь fallback: если текущий узел NPC (from_node) не найден в графе, он принудительно сбрасывается на entrance или main_hall данной локации, чтобы разблокировать поиск пути.
Последствия
NPC regained mobility.
Потеря микро-позиционирования (NPC стоят "где-то в main_hall" вместо конкретного стола).
Требуется обновление всех archetype JSON.
Требуется механизм резолва микро-зон в макро-зоны в будущем (например, алиасы в графе).
---
ADR-007: Переход на Narrative Beat System (Cinematic Presentation Layer)Статус: Принято (Частичная реализация)КонтекстПлоский message_log выводил реплики игроков, NPC и системные сообщения одинаковым шрифтом в нижней части экрана. Это нарушало ТЗ (п.1, п.3) и видение Мастера Тай: UI ощущался как IRC-чат, а не как живая сцена. Отсутствовала поддержка уровней знания NPC и типов подачи (крик/шепот).РешениеВнедрен NarrativeBeat как единая единица текста в UI. Введены DeliveryType (NORMAL, SHOUT, WHISPER и т.д.) и RecognitionLevel (UNKNOWN_MALE, KNOWN_NAME). Создан NarrativeRenderer для отрисовки авто-расширяющихся пузырей. Текст игрока вынесен в отдельный пузырь справа (Shift+Enter поддерживает многострочность). Эхо LLM фильтруется нечетким поиском (SequenceMatcher) построчно.ПоследствияПоложительные: UI стал динамическим, текст не обрезается, исчезло дублирование ввода.Отрицательные: Бэкенд пока не разделяет dm_response на конкретных NPC, из-за чего весь нарратив выводится от лица "Система". Требуется парсинг или изменение контракта бэкенда. Анимации (SHAKE, FADE) пока не реализованы.
---
ADR-0009: Смягчение стража мутации position и открытие границы Macro/Micro Space (08.05.2026 22:21) Статус: ПринятоКонтекстMovementEngine генерировал SceneChange(field="position") для обновления семантической локации NPC, но SceneStateManager содержал архитектурный страж (RuntimeError), который блокировал любую прямую мутацию position, требуя использовать только local_position. Это приводило к полной остановке пайплайна движения.

После снятия стража выявилась более глубокая проблема: DecisionHub принимал решение approach (подойти), но если NPC и игрок находились в одной макро-зоне (например, main_hall), система считала, что NPC уже рядом (macro distance = 0), и отменяла движение. Визуально же NPC мог стоять на другом конце зала. Попытка использовать MovementIntent (предназначенный для макро-перемещений) для микро-позиционирования (смещение на 2 метра внутри зоны) привела к крашу и архитектурной лжи (target_node_id == from_node_id).

Решение

Страж мутации position смягчён: RuntimeError заменён на debug log. SceneChange(field="position") теперь разрешён и атомарно резолвится в local_position (x,y) через SpatialService (реализация ADR-0008).
Восстановлены контракты возврата в LifeEngine: check_random_events и update_routine теперь всегда возвращают кортеж (changes, intent), устраняя краши распаковки.
Категорически запрещено использовать MovementIntent для микро-перемещений внутри одной макро-зоны. MovementIntent — это Macro Traversal (переход между узлами графа).
Для визуального сближения внутри зоны (Local Steering) требуется отдельная сущность — LocalSteeringIntent, которая будет работать с координатами (x,y) напрямую, не затрагивая семантический граф.
ПоследствияПоложительные: Пайплайн макро-движения полностью разблокирован. NPC корректно перемещаются между macro-зонами (main_hall, bar_area, entrance). Контракты данных восстановлены.Отрицательные: Визуальное микро-перемещение (подойти к игроку на 1 метр внутри main_hall) пока НЕ РЕАЛИЗОВАНО. NPC будут телепортироваться в центр макро-зоны, но не будут плавно "подходить" к игроку. Требуется разработка LocalSteeringLayer в следующем спринте.
---
ADR-007: StateDeltas v2 — Domain-Tagged Typed Payloads (08.05.2026 22:21)
Статус: Принято
Контекст
StateDeltas v1 был плоским dataclass. Добавление новых доменов (combat, physiology, spatial) как новых полей приводило к раздуванию god-object и нарушению SRP. Смешанные дельты (например, stress + trust в одной дельте от ReactionSubscriber) размывали доменные границы. Контракт DTO LOCKED v1 блокировал добавление боёвки и физиологии.

Решение
Введён enum DeltaDomain (SOCIAL, EMOTION, REPUTATION, IDENTITY, COMBAT, PHYSIOLOGY, SPATIAL).
Каждый домен имеет свой frozen dataclass payload (SocialPayload, EmotionPayload и т.д.).
StateDeltas расширена полями domain, target, payload. Валидация в post_init: тип payload должен соответствовать domain.
Реакции и социальная пропагация разделены на отдельные доменные дельты (EMOTION + SOCIAL вместо одной смешанной).
StateApplicator читает данные из payload с фолбэком на v1 поля для обратной совместимости.
DecisionHub пока оставлен на v1 (domain=None), так как его миграция требует изменения контракта DecisionResult.deltas с StateDeltas на List[StateDeltas].

Последствия
Типобезопасность: IDE видит поля payload, опечатка вызывает TypeError.
Расширяемость: новый домен = новый Enum + payload class + регистрация в map.
Обратная совместимость: v1 поля продолжают работать, пока потребители не мигрированы.
Инвариант: одна дельта = один домен. Смешанные дельты запрещены.
---