`ADR-O-446` [STANDARD] **IMPACT**
Files: backend/app/domain/epistemology.py, backend/app/services/npc/epistemic_store.py, backend/app/services/npc/epistemic_context_resolver.py, backend/app/services/npc/decision_hub.py
# ADR-O-446 Impact Audit — Recursive Belief Attribution & Theory-of-Mind Channel Separation
> Детальный аудит ОДНОГО ADR. Единый атлас: `docs/ADR (Architecture Decision Records).md`
> Родительский закон: L14.1 Epistemic Core Law (ADR-O-354, O-355, S188). Прецедент разделения канала: ADR-O-390.
> Коммиты: 4e45cc95 (EPISTEMIC-005-06, модель данных), bcf55957 (EPISTEMIC-005-07, интеграция).
> Граница этапа: инфраструктура представления чужих убеждений. Социальное рассуждение на их основе — НЕ реализовано (EPISTEMIC-005-08).

## Changed Domains
- Epistemic Core: `AttributedBelief` (рекурсивный узел), `EpistemicRecord.attribution_chain`, ключ `EpistemicStore`.
- Epistemic Projection: `BeliefSummary.is_attributed`, `EpistemicContext.attributed_beliefs`, маршрутизация в `EpistemicContextResolver.resolve`.
- Decision: только defense-in-depth фильтр в target-aware scoring. Контракт модификаторов не изменён.
- НЕ затронуты: `BeliefState` (L216 / ADR-O-380 write-guard), `RelationshipStore`, правила распространения слухов, `BeliefRevisionEngine`.

## Решение (семантика)
- `Proposition` остаётся атомарным утверждением о мире. Социальная семантика в него не добавлялась.
- `AttributedBelief(holder_id, content: Proposition | AttributedBelief)` — рекурсивная атрибуция произвольной глубины.
- `EpistemicRecord.agent_id` — корневой наблюдатель (владелец представления).
- `EpistemicRecord.proposition` — атомарное СОДЕРЖАНИЕ записи, не обязательно собственное убеждение агента.
- `attribution_chain is None` => собственное убеждение агента в `proposition`.
- `attribution_chain is not None` => агент моделирует, что цепочка `holder_id` придерживается `proposition`.
- Потребитель не вправе трактовать запись как прямое убеждение без явной проверки `attribution_chain`.
- Разделение состояний сохранено: Assertion (`ClaimEvent`) != Receiving != Belief Modeling (`EpistemicRecord`). Низкий `confidence` не подменяет знание о факте высказывания.

## Инварианты и защиты
- Согласованность: атомарный хвост цепочки ОБЯЗАН равняться `proposition`; расхождение -> `ValueError` в `EpistemicRecord.__post_init__` (fail-fast, не молчаливая коррекция).
- Структурные циклы: обход итеративный, `visited` по `id()` объекта -> `ValueError`. Проверка в `_get_atomic_content`, `to_dict`, `_compute_chain_signature`.
- Повторение `holder_id` в цепочке РАЗРЕШЕНО (A->B->B->X валидно). Семантического запрета нет.
- Глубина: семантического лимита НЕТ. Сериализация/десериализация итеративные (без рекурсии Python), лимит 10 уровней из черновика удалён.
- Тип content валидируется в `AttributedBelief.__post_init__` (`TypeError` при постороннем типе).

## Обратная совместимость
- Порядок позиционных полей `EpistemicRecord` не изменён: `attribution_chain` добавлен ПОСЛЕ всех defaulted-полей (`source_type`, `original_source_id`, `seen_claim_ids`).
- Все реальные конструкторы используют именованные аргументы: `tick_orchestrator.py:949`, `tick_orchestrator.py:1243`, `belief_revision_engine.py:76`, `belief_revision_engine.py:124`, `epistemic_store.py:119`. `dataclasses.replace` / `copy` над `EpistemicRecord` не обнаружено.
- Ключ сериализации `proposition` сохранён; `attribution_chain` пишется только когда не None. Старые записи без ключа загружаются с `attribution_chain=None`.
- `EpistemicStore.from_dict` сохраняет legacy-fallback ветку восстановления записи.
- `BeliefSummary.is_attributed` и `EpistemicContext.attributed_beliefs` добавлены с дефолтами в конец dataclass.

## Downstream Consumers
- `EpistemicContextResolver.resolve` — ВЛАДЕЛЕЦ разделения каналов: записи с непустой цепочкой исключены из `perceived_threats` / `perceived_allies` / `perceived_violations` / `max_confidence` / `trigger_proposition` / `report_proposition` / `claims_about_self`.
- Top-3 считаются НЕЗАВИСИМО: `recent_beliefs` — только прямые, `attributed_beliefs` — только атрибутированные. Атрибуция с высоким confidence не вытесняет прямое убеждение с низким.
- `DecisionHub` — defense-in-depth: в цикле target-aware scoring `if getattr(belief, 'is_attributed', False): continue`. Прямой скоринг не получает чужих убеждений.
- `EpistemicStore.upsert` остаётся ЕДИНСТВЕННОЙ точкой записи (Taboo O-390 «второй writer EpistemicStore» соблюдён). Изменён только ключ: `(agent_id, proposition)` -> `(agent_id, proposition, chain_signature)`, чтобы разные атрибуции одного факта не перезаписывали друг друга.
- `EpistemicContext` не сериализуется (Taboo O-390 соблюдён): `attributed_beliefs` — runtime-only поле.
- `personal_route_resolver` / `exploration_target_resolver` / `tick_orchestrator` EXITS_TO-записи — first-order, поведение не изменилось.

## Runtime Impact
- `resolve()`: тот же O(records) проход + два списка и вторая сортировка Top-3. Пренебрежимо.
- `EpistemicStore`: ключ стал 3-кортежем; сигнатура цепочки — строка `holder_id`, соединённых разделителем (не хэш, коллизий хэширования нет).
- Память: +1 optional-поле на запись; для first-order записей цепочки нет (None).

## Sandbox Tests
- `backend/tests/micro/test_recursive_attribution.py` — 12/12: first-order; глубины 1, 2, 5, 50; round-trip; старый формат; расхождение proposition/цепочки отклонено; повтор holder_id; структурный цикл (fail-fast при конструировании); две записи одного proposition с разными цепочками; регресс Store.
- `backend/tests/micro/test_epistemic_attribution_integration.py` — 8/8: first-order как прежде; атрибуция вне recent_beliefs; сохранение в attributed_beliefs; корректность is_attributed; НЕвытеснение (0.99/0.98/0.97 не вытесняют прямое 0.50); смешанный контекст; атрибутированный ATTACKED conf=0.99 не становится trigger, прямой conf=0.9 становится; legacy Top-3.
- Регресс: `python -m pytest backend/tests/micro/ -k "epistemic or belief or knowledge" -q` -> 52 passed, 1432 deselected (44 прежних + 8 новых, ноль регрессий).
- AST-валидация всех изменённых файлов пройдена.

## Открытые границы / долг (для EPISTEMIC-005-08)
- `EpistemicStore.get(agent_id)` без `proposition` возвращает max-confidence запись БЕЗ фильтра атрибуции — потенциальный канал утечки. Prod-вызовов без proposition не обнаружено (`claim_event_subscriber`, `observation_subscriber` передают proposition). Требует решения при подключении социального слоя.
- Сигнатура цепочки — join по разделителю: `holder_id`, содержащий разделитель, теоретически может дать коллизию ключа. Не хэш, но разделитель не экранирован.
- `seen_claim_ids` растёт неограниченно в рамках записи (предсуществующий долг, зафиксирован в коде).
- Социальное рассуждение на основе `attributed_beliefs` НЕ реализовано: нет правил доверия к чужому мнению, нет намеренного использования мнения для воздействия на третьих лиц. Игровые правила не вводились.

## Проверка привязки (природа hook WARNING)
`.githooks/pre-commit` (core.hooksPath=.githooks), строки 13-21: безусловный `git diff --cached --name-only | grep -E "backend/app/domain|backend/app/dto|backend/app/services"` -> печать `[WARNING] ADR IMPACT AUDIT REQUIRED`. Хук НЕ читает ADR и не имеет условия снятия. Предупреждение — advisory-напоминание, не блокирующее (exit 1 относится только к compile-check). Precedent трактовки: `reports/d60_close.py:161` («ожидаемо ... закрывается этим §10»). Закрытие = наличие настоящего аудита, а не тишина хука.

## Rollback
- Удалить `AttributedBelief`, поле `attribution_chain`, `is_attributed`, `attributed_beliefs`; вернуть ключ Store `(agent_id, proposition)`; снять фильтр в Resolver и guard в DecisionHub.
- Схема персистенции не менялась (ключ `proposition` сохранён, новый ключ опционален) — записи без `attribution_chain` читаются прежним кодом. Откат бесследен для сохранений.
