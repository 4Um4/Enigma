
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

---