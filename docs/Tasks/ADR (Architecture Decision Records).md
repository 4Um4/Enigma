
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
EventBuffer (CFRM — ADR-0016)
Временный causal input stream для редукции. НЕ лог, НЕ история, НЕ хранилище.
Структура:
physical_events: List[PhysicalEvent] (HitOccurred, MovementCompleted, ShockImpulseGenerated)
cognitive_events: List[CognitiveEvent] (FearEmergence, AttentionShift, IntentFormation)
social_events: List[SocialEvent] (InformationTransferred, RumorFormed, TrustUpdated)

ClusterGraph (CFRM — ADR-0016)
Пространственная декомпозиция мира. Единственная структура мира. НЕ содержит состояния, содержит связи.
Структура:
clusters: Dict[ClusterID, ClusterDef]
ClusterDef: { seed_cells, members, boundary_cells, version }
Обновление: инкрементальное (дрейф), только при пересечении NPC границ ячеек.

MembraneField (CFRM — ADR-0016)
Функция ослабления причинности при переносе событий между кластерами.
Сигнатура: membrane(event, distance, context) -> attenuation_factor
Ограничение: Membrane evaluation scope == local cluster neighborhood only.

PerceptualKernel (CFRM — ADR-0016)
Модель восприятия NPC. NPC НЕ хранит мир, хранит затухающие причинные впечатления.
Структура:
last_observed_event_ids: Set[UUID]
decay_model: Dict[EventSignature, float] (TTL-веса)
belief_weights: Dict[ClusterID, float] (уверенность в локальных истинах)
Формула миграции: new_perception = merge(old_perception * decay_factor, cluster_local_truth * visibility_projection)

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
ADR-009: Narrative Beat Pipeline, Speaker Extraction и UI Layer Separation (09.05.2026 15:49) Статус: ПринятоКонтекстБэкенд присылал dm_response одной строкой, а фронтенд жестко привязывал её к speaker="Система", что разрушало нарративную идентичность. Системные логи (движение, ошибки) и реплики NPC конкурировали за одно пространство, превращая UI в IRC-чат. Фильтр эха LLM ломал реплики NPC при коротких вводах игрока ("да" блокировало "рада"). Отсутствовала визуальная экспрессия для DeliveryType (SHOUT, WHISPER) и RecognitionLevel.

Решение

Извлечение спикера: dm_response разбивается на строки. Фронтенд формирует known_names из scene_state["npc_positions"]. Если строка начинается с известного имени NPC + разделитель (: , -), имя извлекается как speaker, остаток как text. Иначе speaker="Система".
Разделение слоев: message_log хранит ТОЛЬКО NarrativeBeat (Cinematic Layer). Создан system_log для сырых строк (Log Layer — полупрозрачный лог в углу экрана).
Починка эха: в фильтре SequenceMatcher для npc_reactions добавлен флаг is_short_input (len < 10). Подстроковая проверка (in) отключена для коротких фраз, предотвращая глушение NPC.
Визуальная экспрессия: DeliveryType определяется по маркерам текста (скобки, звездочки, капс). Рендерер применяет стили через цвет текста, рамку и толщину линий (SHOUT=красный 3px, WHISPER=серый 1px, INTERNAL=синий 1px). Шрифты НЕ уменьшаются для сохранения читаемости.
Bubble Lifetime: NarrativeBeat получает creation_tick. Пузыри TRANSIENT живут 5 секунд, затем растворяются 2 секунды (fade out через BLEND_RGBA_MULT). Растворившиеся пузыри удаляются из message_log.
ПоследствияCinematic Layer свободен от системного шума.Реплики NPC ассоциированы с конкретными именами.Исключено ложное глушение NPC эхо-фильтром.Ограничение: извлечение спикера эвристическое и зависит от того, что LLM начинает ответ с имени NPC.Ограничение: визуально WHISPER отличается только цветом/рамкой, а не кеглем (ради читаемости).
---
ADR-0010: Physiology Domain и Impact Propagation Engine (09.05.2026 15:49)  КонтекстТребовалась система расчёта урона для боёвки. Изначальный дизайн предполагал CombatResolver с RPG-абстракциями (Hit Roll, AC, "режим боя") и CombatPayload. Мастер Тай выявил критические архитектурные угрозы: 1) Бой — не отдельная система, а режим давления на ВСЕ системы (физиология, эмоции, социум). 2) combat_state скроет в себе всю физиологию (голод, болезнь, усталость), нарушив SRP. 3) body_part спровоцирует catalog of organs (micromanagement entropy). 4) HP как основа убьёт симуляцию (человек может умереть без потери HP от шока или крови). 5) CombatResolver, пишущий эмоции (if pain > 80: emotion.panic += 30), приведёт к domain leakage и god-object.

Решение

Домен переименован: DeltaDomain.PHYSIOLOGY вместо COMBAT. Бой, голод, падения, болезни — единый класс процессов.
Данные разделены: body_profile (статика: max_hp, abilities) + body_state (рантайм: current_hp, pain, fatigue, blood_loss, consciousness, injuries, modifiers).
InjuryDTO использует target_zone вместо body_part и семантические теги. Разделены structural_damage (разрушение тканей) и functional_loss (потеря функции). HP — производная абстракция (макро-LOD), центр модели — Functional Capacity.
Создан Impact Propagation Engine (Pure Function). Использует Contact Resolution Model (уклонение зависит от боли/усталости, а не RNG Hit Roll). Возвращает ТОЛЬКО Physiology-дельты. Никаких эмоций напрямую — только shock_impulse как сигнал для ReactionSubscriber (No Domain Leakage).
В NPCStateSnapshot effective values НЕ хранятся. Только base_abilities и modifiers (разделение предотвращает modifier stacking desync hell).
ПоследствияПоложительные: Насилие встроено в симуляцию мира органично. Удар порождает каскад: тело → боль → шок-сигнал → страх → социальная паника. Нет отдельного "режима боя". Травмы масштабируемы (от пореза до ампутации) без изменения архитектуры.Отрицательные: Требуется обновление конфигов NPC (добавление body_profile). Требуется разработка CombatSubscriber в Фазе 8 для вызова Impact Engine. Отсутствие микро-позиционирования (LocalSteeringIntent) визуально снижает эффект попадания.
---
ADR-010: Time Control System и Абсолютное время (09.05.26)Статус: Принято (Реализация заблокирована багами)КонтекстДля тестирования social decay требовалось ускорение времени. Время в idle-тиках не продвигалось (нарушение ADR-002). Фронтенд конструировал время из parse_hhmm, теряя дни и годы. Скачки времени при старте из-за TICK_CATCHUP.

РешениеФронтенд делит интервал idle_tick на _time_scale (1, 4, 10, 50).Бэкенд продвигает время в Фазе 0.5 на GAME_TICK_INTERVAL_SECONDS (900 сек).Единый источник истины: game_time_seconds (абсолютное время). Хранится в scene_state, передается через WorldSnapshotDTO.Фронтенд использует оптимистичный рендеринг при ходьбе, но синхронизируется с бэкендом.Убран принудительный 1 тик в TICK_CATCHUP (max(1, ...) -> ...).

ПоследствияПоложительные: Архитектура времени становится детерминированной. Дни и годы больше не теряются. Ускорение позволяет тестировать симуляцию.Отрицательные: Требуется строгая типизация Path/str для рантайм-путей. Необходим импорт DELTA_POLICY_REGISTRY.
---
---
ADR-0011: Force Merge — world_snapshot в DirectGameGateway (NPC Position Delivery)

Статус: Принято

Контекст
DirectGameGateway.send_action() создавал GameActionResponse БЕЗ полей world_snapshot и npc_positions. После player action микропозиции NPC (micro-snap от DecisionHub → MovementEngine → SceneChange → apply_changes) применялись к scene_state в npc_orchestration.py, но фронтенд получал только dm_text и npc_reactions. Результат: [TRACE][ACTION_RESP] has_ws=False, фронтенд рисовал NPC по старым координатам до следующего idle_tick.

Решение
1. TurnResult дополнен полями world_snapshot и npc_positions.
2. GameLoopBridge.turn() после _collect() строит world_snapshot из актуального scene_state через loop.scene_manager.get_scene_state().
3. DirectGameGateway.send_action() передаёт result.world_snapshot и result.npc_positions в GameActionResponse.

Последствия
Положительные: Фронтенд видит актуальные позиции NPC сразу после player action (has_ws=True). Micro-snap координаты доходят до рендерера.
Отрицательные: get_scene_state() — дополнительный I/O в критическом пути. World_snapshot строится дважды (в npc_orchestration и в bridge). Требуется кэширование при оптимизации.

---
ADR-0012: Защита micro-position от затирания macro-relocation

Статус: Принято

Контекст
MovementEngine.process_intents() генерировал SceneChange(field="position", value=target_node_id) даже когда NPC уже находился в целевом узле (from_node_id == target_node_id). SceneStateManager резолвил это в center node (8.0, 7.0), уничтожая micro-position (10.57, 3.04). Результат: NPC «прыгал» в центр комнаты после каждого tick.

Решение
Добавлен guard: если intent.from_node_id == intent.target_node_id — пропускаем macro SceneChange, micro-position сохраняется. Это корректно, потому что micro-snap обрабатывается отдельной веткой (local_target_xy → SceneChange(field="local_position")).

Последствия
Положительные: Micro-position не затирается. NPC остаются near-player после approach.
Отрицательные: NPC всё ещё телепортируются (нет continuous movement). Требуется TraversalState для настоящей навигации.

---
ADR-0013: Architectural Gap — State Relocation vs Continuous Spatial Simulation

Статус: Принято (диагноз, реализация в следующем спринте)

Контекст
Текущая система движения — «state relocation с косметическим x/y». NPC мгновенно меняют позицию через Intent → SceneChange → APPLY_LOCAL_POSITION. Нет: persistent movement state, traversal progression, temporal interpolation, occupancy, velocity model, spatial slots. Результат: телепортация, «center-room syndrome», race conditions, неправильный actor selection, delayed relocation after tick.

Решение (ROADMAP, не реализовано)
Этап 1: Ввести TraversalState (npc_id, path, current_index, speed, started_at, target_node, locomotion).
Этап 2: Отделить SceneChange (topology mutation) от MovementStep (locomotion).
Этап 3: Intent.APPROACH → path request → traversal start, а не APPLY_LOCAL_POSITION.
Этап 4: Spatial slots внутри Interest Zones (fireplace → 4 слота, bar → 3 слота).
Этап 5: speed * delta_time — continuous position integration.
Этап 6: Frontend interpolation: render_position != logical_position.

Последствия
Без TraversalState: NPC будут телепортироваться бесконечно — это не баг, а класс архитектуры.
С TraversalState: переход от turn-based symbolic simulation к continuous spatial simulation — крупнейший архитектурный скачок в проекте.
---
---
ADR-0011: Domain Reduction Semantics Layer (DRSL) (09.05.2026 22:41)
Статус: Принято
Контекст
_aggregate_deltas использовал универсальный редьюсер (_merge_payloads) для всех доменов. Это смешивало коммутативные (social) и некоммутативные (physiology) эффекты. Physiology дельты терялись при агрегации через last-write-wins (return p2). Мастер Тай выявил: система не различает бухгалтерию мира (Σ) и физику мира (интеграл с памятью).

Решение
Введён ReductionPolicy enum: ADDITIVE (Σ), BOUNDED_ADDITIVE (Σ + clamp), OVERWRITE (last-write-wins), PHYSICS_COMPOSITE (S_t = F(S_{t-1}, impacts)).
DELTA_POLICY_REGISTRY: конституция мира — каждый домен знает свой закон редукции.
_aggregate_deltas разделён на два потока: PHYSICS_COMPOSITE обходит merge (инъекции энергии передаются как есть), алгебраические домены редуцируются по политикам.
Мастер Тай: не "починили merge", а ввели онтологическое разделение типов реальностей.

Последствия
Physiology-дельты больше не теряются при агрегации.
Каждый новый домен обязан объявить свою политику в DELTA_POLICY_REGISTRY.
PHYSICS_COMPOSITE означает: тело не складывается, оно эволюционирует. Редукция — задача ImpactEngine/StateApplicator, не агрегатора.
---
ADR-0012: CombatSubscriber — мост EventDTO → ImpactEngine (09.05.2026 22:41)
Статус: Принято
Контекст
ImpactEngine существовал, но никто не вызывал его из пайплайна. События PLAYER_ATTACKS обрабатывались ReactionSubscriber (эмоции), но не порождали физических последствий.

Решение
Создан CombatSubscriber (Phase8Handler). Мост, не система.
Подписка: PLAYER_ATTACKS, PLAYER_ATTACKED, COMBAT.
Извлекает ImpactIntentDTO из EventDTO.payload.
Строит снапшоты (NPCStateSnapshot) для атакующего и защищающегося. Игрок получает идеальный fallback-снапшот.
Вызывает resolve_physical_impact() (pure function).
Возвращает Phase8Result(deltas=physiology_deltas).
Порядок Фазы 8: perception → reaction → social → combat (насилие после социальных реакций).

Последствия
Боевые события теперь порождают Physiology-дельты через delta_buffer.
CombatSubscriber НЕ генерирует эмоции (No Domain Leakage). shock_impulse — сигнал для ReactionSubscriber.
При отсутствии target_id событие пропускается.
---
ADR-0013: PhysiologyDecayHandler — Leaky Integrator для Фазы 0.5 (09.05.2026)
Статус: Принято
Контекст
Боль, усталость и кровопотеря не затухали между тиками — применения PhysiologyPayload было достаточно для записи, но не для симуляции восстановления. Мастер Тай: тело — инерционная система с памятью, S_t = S_{t-1} * exp(-lambda * dt).

Решение
Создан PhysiologyDecayHandler (IdleTickHandler).
Leaky Integrator: боль (λ=0.05), усталость (λ=0.03), кровопотеря (λ=0.01) экспоненциально затухают.
Сознание восстанавливается обратно пропорционально боли.
Closing drift: остатки < EPSILON обнуляются напрямую (без микро-осцилляций).
Фазовые переходы (emergent states): pain > 50 → stagger, consciousness < 0.1 → unconscious. Не пороги, а устойчивость траектории.
NPCStateSnapshot расширен полем statuses для отслеживания текущих статусов.

Последствия
Физиологические параметры теперь инерционны — боль затухает, усталость восстанавливается, кровопотеря медленно снижается.
NPC естественным образом выходят из stagger/unconscious при восстановлении.
Фаза 0.5 теперь обрабатывает ВСЕ инерционные системы (social drift + physiology decay).
---
ADR-0011: Embodied Traversal — Отвязка Внимания от Кинематики (09.05.2026 22:45) Статус: ПринятоКонтекстДля реализации ТЗ (игрок — синяя стрелочка, разворачивается по движению) был применен кинематический подход: facing_angle = math.atan2(dy, dx). Мастер Тай выявил критическую архитектурную угрозу: слияние движения и взгляда (кинематическая редукция) убьёт симуляцию на этапе NPC AI. NPC должен уметь пятиться от страха, глядя на угрозу, или стоять спиной. Также _MoveState становился god-структурой, смешивая навигацию, кинетику и эмбодимент.

РешениеОнтологический разрыв _MoveState на 3 природных домена:

Навигация (Куда идём): target_npc_id, path, path_index.
Кинетика (Как движемся): cooldown, walk_distance_accumulated.
Эмбодимент (Куда смотрим): facing_angle, facing_mode.
Введен facing_mode: "VELOCITY" (взгляд по вектору скорости), "LOOK_TARGET" (взгляд прикован к объекту интереса), "FREE" (зафиксирован/отвлечен).При движении по пути к NPC, facing_angle вычисляется как угол от позиции агента к target_npc_id, а не к следующей точке path_index. Это исключает "боковое/заднее" зрение при обходе препятствий.

ПоследствияПоложительные: Взгляд стал намеренным. Архитектура готова к внедрению Attention System (gaze/focus/awareness layer) для NPC. Рендер корректно работает с любым углом.Отрицательные: Рост сложности _MoveState (что потребует в будущем выделения в отдельный EmbodiedTraversalState). Требуется разработка сглаживания поворота (lerp по facing_angle), иначе при смене целей будет резкий "щелчок" направления.
---
ADR-0015: Event-Sourced World Transition и Temporal Isolation (09.05.2026 22:54) Статус: ПринятоКонтекстТекущий конвейер использует ctx.scene_state как мутирующий живой словарь. Вызов apply_changes(ctx.scene_state) в Фазе 0 (LifeEngine) позволяет Фазам 3-8 (Perception, Decision) видеть частично изменённое "будущее". Это нарушает причинность: NPC реагируют из будущего, LLM генерирует текст на основе несогласованного мира. Попытка внедрить deepcopy на старт тика признана архитектурной ловушкой (O(N) bottleneck, двойная истина, лечение симптома).

---
ADR-0016: Presentation Lerp и Visual Gaze Indicators (10.05.2026 0:40)
Статус: Принято
Контекст
Стрелка игрока мгновенно "щелкает" в новый угол при смене направления, создавая визуальный диссонанс. NPC не имеют визуального маркера внимания, из-за чего игрок не понимает, кто на него смотрит, пока не прочитает текст. Спрайты объектов (стулья, столы) не отображались в игре из-за разрыва между `scene_state` и `PerceivedScene`. Время жизни пузырей (5 сек) было недостаточно для чтения реплик.

Решение
Внедрен экспоненциальный Lerp (10 рад/сек) для визуального угла поворота игрока в `SceneRenderer`. Логика расчета угла (`_MoveState`) не затронута.
Для NPC добавлен индикатор взгляда: желтая линия от края кружка NPC к игроку, если NPC является `attention_focus` или имеет inference "communication".
Починен рендер объектов: добавлен `_draw_obstacles()`, обрабатывающий `spatial_obstacles` из `scene_state`. Для NPC добавлен fallback на спрайт `"person"` при отсутствии точного маппинга.
Увеличено время жизни TRANSIENT-пузырей: 10 секунд жизни + 3 секунды фейд-аут. Добавлены визуальные стили: WHISPER (alpha=200 + тень), SHOUT (микро-вибрация 1px).
Отключено перемещение кликом мыши.

Последствия
Положительные: Визуальная плавность поворота. Читаемость внимания NPC. Объекты и NPC отображаются корректно. Текст не исчезает слишком быстро.
Отрицательные: Индикатор взгляда работает только с доступными данными (focus_id, inferences). Для более сложных паттернов внимания потребуется Attention System на бэкенде.
Решение(Историческое — см. ADR-0016 для актуальной модели)Система переходила к Event-Sourced Architecture. scene_state переставал быть "живым словарём".ПоследствияСуперседировано Causal Field Reduction Model (ADR-0016), которая устранила проблему глобального объекта World и NP-hard упорядочивания через локальные причинные пузыри.
ADR-0016: Causal Field Reduction Model (CFRM) (Сессия 17)
Статус: Принято
Контекст
ADR-0015 пытался сохранить концепцию единого World State, вычисляемого через глобальный Reducer. Это приводило к NP-hard проблеме упорядочивания параллельных событий (кто первый: удар или паника?) и требовало O(n²) вычислений для согласования. delta_buffer был списком императивных инструкций («добавь стресс»), что нарушало причинную замкнутость мира и требовало внешнего «редактора реальности».

Решение
Переход к distributed causal inference system. Глобального объекта World больше не существует в runtime.

Онтологические постулаты CFRM:
1. NPC operate on perceived causality, not actual causality.
2. Snapshot is not world state; Snapshot is belief state derived from CFRM projection.

Core Model: World Evolution is a constrained local reduction over clustered causal fields.
Формула: Snapshot[t] = Reduce(ClusterGraph_local, EventBuffer_local, MembraneField_local).
Три структуры вместо World:
ClusterGraph (пространственная декомпозиция, содержит связи, НЕ содержит состояния).
EventBuffer (временный causal input stream для редукции, атомарные факты, НЕ лог и НЕ инструкции).
MembraneField (функция ослабления причинности при переносе между кластерами).
NPC Model: NPC хранит PerceptualKernel (last_observed_event_ids, decay_model, belief_weights), а НЕ world state. Perception cache — производный слой, пересчитываемый из EventBuffer + MembraneField.
3-фазный оператор редюсера:
Phase 1: Projection (Events → ClusterGraph influence mapping).
Phase 2: Attenuation (MembraneField applies decay over edges).
Phase 3: Reduction (Local state updates per cluster, no global merge).
Жёсткое ограничение: Membrane evaluation scope == local cluster neighborhood only. Запрет на глобальный correlation (иначе O(n²)).
Последствия
Положительные: Линейная масштабируемость (O(cluster_size)). NPC обладают инерцией восприятия. Исключён глобальный пересчёт сцены. Основание для социальной физики (обман мембран).
Отрицательные: Полная замена SceneStateManager на систему кластеров и мембран. Перепись PerceptionSubscriber (fallback на всех NPC заменяется на BFS по Causal Closure). Требует внедрения PerceptualKernel в NPCState.
---

---