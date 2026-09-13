# ADR-O-387 Impact Audit
> Детальный аудит одного ADR. Единый атлас: `docs/ADR (Architecture Decision Records).md`

## Решение
Диалоговая целостность четырёх осей (закрытие GC-DIALOGUE-01, Stage-1):
D1 LIVENESS: терминал «owner DEAD → EXPIRED» канонического ADR-O-365-мэппинга
   доведён до диалогового класса задач в 4 точках диспетчеризации: fast-path
   (синхронная ветка), dequeue (очередь), process_tasks (путь мёртв в
   production — гейт оставлен замком будущего реактирования), worker
   (последняя точка перед executor.execute — покрывает in-flight: задача,
   сабмиченная до смерти, не материализуется; любые будущие dispatch-точки
   закрыты by construction). Fail-open по S198-паритету: провайдер не задан /
   владелец не найден / ошибка → исполнение как раньше (возрастной M-29
   разбирает брошенные). Источник живости — LifeEngine-снапшот
   (_resolve_npcs_snapshot); wiring единственный (game_loop ленивая
   инициализация TaskScheduler).
D2 EXPOSURE AT MATERIALIZATION: EventDTO NPC_SPOKE/COMMUNICATION_CLAIM несут
   radius = exposure_radius(semantic) (Р-В SSOT; ADR-148 в точке материализации;
   сентинел → whisper D4). До фикса материализатор вычислял _speech_radius и
   не использовал — вся production-речь жила на хардкоде 10.0 («loud»),
   мембраны и журнал видели завышенный радиус при зелёной батарее Р-В
   (замки клепали события сами).
D3 PLAYER JOURNAL: порог подслушивания игрока — из event.radius с fail-open
   8.0 (легаси-паритет Р-Б2; dict-контракт тестов не тронут). Private 0 —
   никогда; солилоквий/whisper 3; normal 6; loud 10; shout 15.
D4 TAB PACING: фокус диалога = presentation-режим внимания: интервал опроса
   idle_tick ÷4 (NEAR 500→125 мс, floor 125 = не чаще 8 тик/с), фриз 30с
   удалён. game_time_seconds/тики/RNG/последовательность тиков инвариантны
   (ADR-O-344, §14): FE лишь чаще вызывает idle_tick — реплей-детерминизм
   инвариантен pacing'у by construction.

## Changed Domains
dialogue execution (жизненный цикл задач), speech exposure (материализация),
perception (журнал игрока), presentation (FE-каденс).

## Downstream Consumers
NpcDialogueSubscriber (журнал), ClaimEventSubscriber/EpistemicStore (радиусы
клеймов; Goran-warn слышен в 6 м, не 10), FE GameLoop (пейсинг), GORAN-харнессы
(геометрия игрока откалибрована под SSOT-радиусы: β (8.59, 0.81)), все
потребители EventDTO.radius.

## Runtime Impact
Liveness-гейт: O(N) скан снапшота на задачу на точке диспетчеризации;
провайдер отсутствует → no-op (sandbox/тесты без wiring не изменились).
Материализатор: ноль (значение уже вычислялось). FE: ноль в ядре.
Персистенция: без новых ключей.

## Sandbox Tests
micro 26/26 (liveness 7 + materializer 4 + sentinel 11 + exposure 4);
SUPERBOX gc_dialogue GREEN (D1/D2/D3, 14 пунктов); GORAN β GREEN (10/10 +
CONTROL); GORAN vertical GREEN (13 звеньев — после harness-миграции
S223/Э6 + S225-save + β-freeze; вердикт Мастера: stale-test migration, НЕ
production causal defect); epistemic closure GREEN; bc1 6/6; IPT 45/45.

## Rollback
Гейты: провайдер=None → fail-open = прежнее поведение (по точкам).
Материализатор: возврат radius=10.0 восстановит утечку (замок красный —
не рекомендуется). Журнал: константа 8.0. FE: константы ×4.

## Открытые пункты (честно)
1. DEBT-DLG-LIVENESS-prodpath: production-смерть (VitalState → персистенс →
   reload) не покрыта живым прогоном; гейт доказан через DI-шов провайдера
   (контракт идентичен: провайдер читает тот же LifeEngine-слой).
2. In-flight straggler пула = DEBT-ABORT-404 (S220): гейт-проверка прошла до
   смерти честно; сценарий меряет чистое окно после гейта.
3. DialogueMemorySubscriber: L2-запись speaker+listener без мембраны
   (радиус/дистанция) — телепатия-класс в канале памяти.
4. Живая-сессия пп.1–2 (TAB-пейсинг ≈125 мс в фокусе) — чеклист, прогон за
   Мастером; DM-нарратив при живом llama подтверждён прогонами №144/№163.

## Ретракции
№149: гипотеза «третий dispatcher process_tasks» опровергнута грепом
вызывателей (0 в backend/app) — гейт оставлен как замок мёртвого пути;
урок в протокол: греп вызывателей ДО выдвижения dispatch-теорий.