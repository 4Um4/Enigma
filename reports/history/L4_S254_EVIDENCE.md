# L4 S254 — полевое доказательство ADR-O-383 (Embodied Constraint)

Режим (приказ Мастера 2026-09-11): fresh / cockpit / flags OFF / LLM ON / ускорители OFF /
runtime-патчи запрещены / git запрещён — всё локально.

## База (верифицирована ДО git-бана)
- Рабочее дерево: потомок Потребности_1 (merge-base b702d4fc exit=0).
- Наследие S248–S250: 9/9 IN-HEAD (723c1a61, cbdb0927, 11058fe0, 650f3645, 339c5dec,
  42c587b1, a6708f46, b72a6eac, a0cc0d42).
- Baseline: IPT 45/45; gameplay 11/11.

## Пре-стейдж (факты)
- Пороги ADR-O-383 целы: pressure_translator.py:17-18 (0.8/0.1), /100.0 (:95-97).
- Флаги соседей default OFF: D8P_ENABLED / DESIRES_ENABLED / ACTIVITY_LIFECYCLE_ENABLED.
- Формула износа: body_engine.py:50-51 (0.25*load*mod - 0.10*(1-load); сон *SLEEP_RECOVERY).
- Горизонт: ~1040 тиков от свежего базлайна; wait 20 = 4.16с -> ~3.7 мин чистых.

## Находки
- L4-F1 [DEBT, тело/персистентность]: body_state NPC отсутствует во всей дисковой
  персистентности (сцена: 0 маркеров; memory.db — домен памяти). npc_loader инъецирует
  BODY_STATE_HEALTHY (:336-337, :362-363, :384). Restart/new = сброс fatigue. RAM-накопление
  внутри процесса живо (S249 A: 25 тиков). ПРОТОКОЛ: никаких restart/new после старта сессии.
- L4-F2 [чужая зона RE]: new_game -> RelationshipStore reset failed '_cache'
  (V2RelationshipBackend). Риск чистоты базлайна ноги (г). Эскалация после L4.
- L4-F3 [инструмент]: кокпит 'день' показал тик 0 при scene-tick=20. Открытый пункт.
- L4-F4 [шум]: [FLEE_NAV] guard_borko not found xN; [COMMITMENT][SWEEP] vanished=1;
  [CONFIG] qwen_7b -> Q5_K_M path не найден (CONFIG-DEBT; сервер жив).
- Реплей-канал кокпита: не подтверждён.

## Решения
- MUTATIONS не коммитить (приказ); git-бан (приказ 2026-09-11); doc-вставки отложены.
- Канал сэмплинга тела: только ин-процесс (санкция на read-only 'body' запрошена).

## Критерии закрытия (ратифицированы)
(а) natural crossing; (б) causal contour BODY->translator->decision; (в) изменение feasible
action space (A->B или A->BLOCKED — оба валидны); (г) player-observable.
Частичный вердикт легитимен: L4-BODY/DECISION GREEN, GAMEPLAY EDGE OPEN.

## Блок 2 (2026-09-11, после git-бана)
- Живых python-процессов нет — окно симуляции чисто (Q3: процессы; файловая
  активность соседей без git неверифицируема — слово Мастера).
- L4-F5 [канал]: кокпит НЕ пишет реплей — после new+wait 20 (тики 1-20) новой
  session-строки в replay.db нет (последняя f0ef074d, 2026-09-10). Контур (б):
  stdout + scene_changes.jsonl + observables (форма санкционирована Мастером).
- Поведенческий канал сцены: scene_kv коммитится каждым тиком (tick,
  npc_positions: activity/in_transit/позиции), читается cross-process;
  activity populated и при флагах OFF (maid=serving_tables, orm=Обедает
  в общем зале — расписание).
- Ин-процесс паттерн тела: game_loop._resolve_npcs_snapshot(CAMPAIGN) ->
  LifeEngine-кэш; read_body: nested body_state | плоская idle-проекция.
- L4-F1 финализирован: npc_loader runtime-overlay (npc_runtime.json) существует
  как механизм, писателя тела нет — тело только RAM.
- Инструмент L4: Route B (%TEMP%-раннер на game_loop_builder, ноль правок репо)
  рекомендован; Route A (патч body в кокпит) — альтернатива по слову Мастера.

## Блок 3 (2026-09-11): инструмент L4 выбран
- Инструмент: TavernGameplayHarness (§5a.2, наша зона) как база %TEMP%-раннера;
  ноль правок репо. Production-тики idle_tick; player-нога run_turn (REST);
  temp-saves изоляция (реальные saves/sessions защищены); dispose = полный
  рестор (settings/sessions).
- gc09a-паттерн (advance_ticks + read_body) = протокол Phase 0/Main; seed 42
  (тот же, что S249) — сравнимость с 0.075/тик.
- Пейсинг: батчи с класс-detach экстрактора (cockpit-семантика ADR-O-377
  partial), detach снимается на player-ходах (LLM жив для ноги (г)).
- Поведенческий контур: GameplayCounters (event-тап) + scene_changes.jsonl.

## Phase 0 — run 1 (2026-09-11T19:10) — ДОКЛАД цифрами
- Канал тела жив ин-процесс (harness.read_body): 6/6 NPC читаются каждый батч.
- maid_lusya: fatigue 0.375 -> 3.125 (тики 5->65), Δ/тик +0.0458 avg; батчево:
  b1 +0.075/тик (serving_tables), b2 +0.0015/тик (socializing — activity-пауза,
  energy восстановился 97.5->98.86), b3 +0.061/тик. ИЗНОС LOAD-МОДУЛИРОВАН
  activity — модель подтверждена runtime'ом.
- guard_borko: +0.0750/тик ровно (guarding_gate) — число S249 дословно;
  energy −0.1/тик ровно => energy-порог (raw 10) ~тик 900, РАНЬШЕ усталостного
  (~тик 1067) — второй естественный вектор кроссинга ADR-O-383.
- Контроли: orm/goran/tornin/thief ≈ 0 (еда/сон) — рост НЕ system-wide,
  индивидуальный f(load). Требование контроля (Мастер) выполнено и дало диагноз.
- Формула сходится: implied load borko = 0.5 в точности (0.35L − 0.10).
- Горизонт maid ≈ 1677 тиков (crossing ~тик 1742); потолок Main v1 = 1400 —
  ИНСТРУМЕНТАЛЬНЫЙ блокер (go в v1 = maid NOT-CROSSED впустую). Решение: stop,
  v2 (MAX_B=200; кроссинг-скан всех NPC по обеим осям; stall 10/25), перезапуск.
- Реплей 1642->1642 (L4-F5 консистентно). Пайплайн 7 агентов (player-аватар —
  субстрат ноги (г)). NPC_SPOKE=32, NPC_MOVED=42 за 65 тиков. Пейс 0.09с/тик.
- L4-F6 [кавиат/долг Н-56]: DLG_QUEUE OVERFLOW ~3-5 ambient-дропов/тик —
  счётчики речи модулируются backpressure; контур (б)/(в) — на траектории,
  activity-ярлыках, звёздах кроссинга и ногах, не на сырых счётчиках речи.
- АВТО-GO v2: maid Δ/тик > 0.02; нет [FAIL]/[ANOMALY]; горизонт <= 3800.

## Run L4 v2 авто-сводка (2026-09-11T19:31:44)
- maid crossing (окно): НЕТ
- все crossings: {}
- maid fatigue: 0.375 -> 0.0 (тики 5.0 -> 588.0), Δ/тик -0.0006
- evidence: l4_s254_samples.jsonl, l4_s254_run_console.txt

## Run v2 MAIN (2026-09-11T19:21-19:31) — честный исход, L4 OPEN
- Maid: ОТРИЦАТЕЛЬНЫЙ РЕЗУЛЬТАТ (научный, не сбой): activity serving_tables ->
  socializing (расписание); точка безубыточности L=0.286 (0.35L-0.10) — окна
  socializing стирают fatigue (−0.1/тик) быстрее, чем serving копит (+0.075).
  Порог 80 недостижим для maid в этом распорядке ВЕРОЯТНО ВООБЩЕ (суточный
  баланс <= 0). Вклад в CALIBRATION_CANDIDATE ADR-O-383: порог достижим только
  архетипами с непрерывной нагрузкой. Предсказание '~1040 тиков' опровергнуто
  полем (предполагало непрерывность нагрузки).
- Borko: живой монотонный кандидат — fatigue +0.0750/тик и energy −0.1000/тик
  ЛИНЕЙНО через все 588 тиков (residual ~0 по данным сэмплов). Проекции:
  energy<10 ~тик 903 (первый ADR-O-383-порог, симметрично валидный:
  _ENERGY_LOW_CANDIDATE в том же chronic-veto), fatigue>=80 ~тик 1071.
- L4-F7 [инструмент, мой просчёт]: stall-правило привязано к единственному
  TARGET (maid) — честный стоп на M26 остановил прогон с живым кандидатом
  (borko) за ~315 тиков до его порога. v3-правило: стоп только если НИ У ОДНОГО
  наблюдаемого NPC нет живой траектории к любому порогу.
- L4-F5 РЕТРАГИРОВАН: реплей ПИШЕТ harness-сессии (09db403b: 591 tick_snapshots;
  run1 479dacd7: 65) — флаш при dispose объясняет прошлую слепоту. Per-tick
  decision-контур (tick_mutation с интентами) доступен пост-фактум — носитель
  критерия (б) при будущем crossing.
- Нога 'ПОСЛЕ crossing' run v2 = НЕВЕРНАЯ МЕТКА (crossing не случился; второй
  базлайн на тике 588). 'Устала немного' при fatigue=0/energy=100 — LLM-комплаенс
  на наводящий вопрос, НЕ телесное состояние; в (г) НЕ заявляется (отрицательный
  контроль: вербальный аромат != body state).
- Попутно: maid hydration=0.0 (ось вне V1 — наблюдение); сессия 18:54 ticks=0
  (неатрибутированная — на заметку); social_action 0->1 в ноге (тривиум).
- Вердикт: (а) НЕТ -> L4 OPEN. Развилка Мастеру: v3 TARGET=guard_borko
  (единственный естественный маршрут к crossing; ~1100 тиков, ~4 мин).

## Блок v3 (2026-09-11): решение Мастера — «Можно Борко, можно Тень»; выбран Борко
- TARGET=guard_borko: измеренная монотонная траектория (fatigue +0.0747/тик,
  energy −0.0996/тик, residual ≤0.18, n=30; проекции energy<10 ~тик 904,
  fatigue≥80 ~тик 1071). thief_shadow спит (накопление 0 по построению) —
  в WATCH; all-NPC сканер ловит её звёздами бесплатно.
- Риск-фактор (из анализа run2): maid eating-окно восстановило energy до 100
  (тик 88); у borko eating-окна не было 588 тиков. Stall v3 ГЛОБАЛЬНЫЙ (закрытие
  L4-F7): стоп только если НИКТО не прогрессирует 25 батчей.
- Окно наблюдения v3 dual-axis: после первого TARGET-crossing — до второй оси
  +2 батча (кап 12) — захват ОБЕИХ порогов ADR-O-383.
- Пост-ранн экстрактор реплея (критерий (б)): BEFORE = вся история до crossing,
  AFTER = crossing..+300; интенты из tick_mutation (repr) по спикерам.

## Run L4 v3 авто-сводка (2026-09-11T20:04:47)
- TARGET=guard_borko; crossing (окно): тик 908 оси energy,fatigue
- все crossings: {"enr:guard_borko": 908, "fat:guard_borko": 1088}
- guard_borko fatigue: 0.375 -> 81.37500000000165 (тики 5.0 -> 1088.0), Δ/тик +0.0748
- evidence: l4_s254_samples.jsonl, l4_s254_run_console.txt

## Run v3 MAIN — экстрактор реплея (2026-09-11, сессия b829f0f5, 1091 тиков)
- (а) GREEN обе оси: energy 9.5<10 @ тик 908; fatigue >=80 @ ~тик 1067-1068
  (сэмпл 80.1; точный тик — по ★-строке консоли). Естественно, без инъекций.
- Интент-профиль TARGET через окно: BEFORE {CALL_FOR_HELP x1, TALK x1} за 907
  тиков (~0.002/тик) -> AFTER {WARN x2} за 183 (~0.011/тик, x5). ЧЕСТНАЯ
  ОГОВОРКА: WARN НЕ входит в capped-набор V1 (FLEE/ATTACK/APPROACH/MANIPULATE)
  — эмерджентность коррелирует с окном истощения, но атрибуция телу НЕ
  доказана (n=2; конфаунды: эпистемика/расписание/player-окно).
- Контроли: orm/goran/tornin темп стабилен (изменение НЕ системное); maid
  замолчала (0 интентов в AFTER) при СВЕЖЕМ теле (fatigue 0/energy 100) —
  интент-эмиссия меняется и без тела: прямой контр-аргумент поспешной
  атрибуции. player тоже отсутствует в AFTER-окне (вопрос к хвосту консоли).
- activity TARGET: guarding_gate константен через оба crossing — activity-
  уровень не сдвинулся.
- Механический тест (б)/(в) pending: scores_trace_map (S190) — capped-intent
  scores Борко до/после 908; зонд установлен (l4_scores.py, %TEMP%).
- Вердикт НЕ вынесен: ждём (1) хвост консоли (финальный отчёт + обе ноги =
  критерий (г)), (2) scores-зонд.

## Run v3 — scores-зонд (сессия b829f0f5; ticks 700/950/1080 из scores_trace_map)
- Борко capped-оси: flee 0.0665/-0.0563/0.0216; attack -0.54/-0.60/-0.48;
  approach 0.0417/0.0179/0.0418 — ВСЕ неконкурентны всегда; доминанты
  block_path 0.40->0.44 / ambush 0.35->0.46 (uncapped). Cap не биндится
  по селекции (не по механизму). approach не дрогнул -> семантика трейса
  (pre/post cap; min-vs-multiply) — вопрос археологии, без неё «cap виден»
  НЕ заявляется.
- WARN x2 при стабильном warn-score (0.178->0.173): маржинальная эмиссия,
  n=2, uncapped, атрибуция телу недоказана (контроль maid: замолчала со
  свежим телом).
- movement через оба crossing продолжается (proactive_block_path/ambush,
  ROUTINE-домен, uncapped); guarding_gate константен.
- ГЛАВНАЯ ДОБЫЧА [CALIBRATION_CANDIDATE ADR-O-383]: capped-набор V1 ∩
  intent-экология таверны ~ пусто (доминанты CHANGE_ROLE/OFFER_JOB/
  REQUEST_SERVICE/SPREAD_RUMOR/CALL_FOR_HELP/WARN/TALK/block_path/ambush —
  uncapped). Хронический veto механически корректен (оракул 2/2; прод-
  проводка), но поведенчески ЛАТЕНТЕН в этом сценарии — ударил бы только
  в threat/combat-контексте. Поведенческое выражение истощения =
  rest-seeking/Needs-Activity (ветка Потребности / новый MVP ТЗ).
- Черновик вердикта: (а) GREEN обе оси (908/1088); (б) механизм GREEN
  (композиция: естественный crossing + прод-translator + оракул), полевое
  срабатывание не наблюдалось (capped-регион неконкурентен); (в) пространство
  изменилось, выбор инвариантен (нет A->B/A->BLOCKED: A никогда не выбиралось);
  (г) pending ДО-нога (ПОСЛЕ-нога мультисигнальна при fatigue 81/energy 0,
  включая ненаводящий вопрос; контроль v2 требует прямого сравнения).
- Траектория: L4-BODY/DECISION GREEN, GAMEPLAY EDGE OPEN (категория Мастера).

## Run v3 — ДО-нога + археология cap (2026-09-11)
- ДО-нога v3-Борко восстановлена (runlog append: :479; v2-maid :139 — бонус-
  контроль). Состояние ДО-ноги: fatigue≈4.9/energy≈93.5 (свежее тело).
- Факт (г) [ОТРИЦАТЕЛЬНЫЙ КОНТРОЛЬ x2]: лексика усталости в ОБЕИХ ногах Борко
  («устало взглянул… зевнув» при fatigue≈5); maid v2 «Устала немного» при
  fatigue 0. Вербальный фенотип = персона-управляемый. Пост-crossing градации
  (лежать бы тихонечко / не поднимая головы / снова придется стоять) — без
  атрибуции телу; DM читает observed_state/embodied_traces (L16), не fatigue.
  Кандидат-канал: exertion_level в world_snapshot.npc_positions —
  неверифицирован. (г) = OPEN.
- Факт (б) [ПОДОЗРЕНИЕ, до подтверждения]: translator пишет chronic cap 0.3
  (min); decision_hub ФАЗА 1 потребляет ТОЛЬКО <=0.0 (деление), ФАЗА 2 применяет
  только deformation — потребителя 0.3 в хабе НЕ ВИДНО. Прод-корроборация:
  approach 0.0417->0.0179->0.0418 сквозь оба crossing (кап активен с 908
  непрерывно) — сигнатуры x0.3 нет; колебания = шум uncapped-осей.
  Жёсткие нули enforced (NPIC full-veto, pain/shock/blood_loss/commitment).
  Если подтверждится: L4-F8 [DEBT-кандидат] chronic soft-cap без потребителя;
  semantics «существенно затруднено» не реализована вниз по потоку; точка
  фикса — ФАЗА 2 (scores x feasibility для 0<f<1) — НЕ сейчас, очередь
  решает Мастер. Объясняет полевую латентность глубже экологии интентов:
  даже конкурентный capped-интент не был бы тронут.
- Промежуточная рамка: (а) GREEN обе оси (908/1088); (б) BODY->translator
  GREEN (прод, естественно), translator->scores/selection — подозрение
  отсутствия для soft-cap (0.0 работает); (в) эффективное пространство выбора
  не изменилось (обе причины: неконкурентность + unconsumed cap);
  (г) OPEN (двойной отрицательный контроль).
- Ждём: греп потребителей constraints + чтение gc09b-оракула (что доказывает
  GREEN 2/2) + availability-гейт.

## L4-F8 подтверждён + кейс-мисматч + замороженное противоречие (2026-09-11)
- L4-F8 ПОДТВЕРЖДЁН (греп backend/app): единственный потребитель
  ActionSpaceCompression.constraints — decision_hub:565 (ФАЗА 1), потребляет
  ТОЛЬКО <=0.0. Потребителя 0<feasibility<1 не существует нигде. Chronic
  soft-cap 0.3 (+ blood_loss 0.3) без исполнителя.
- НОВЫЙ СЛОЙ [подозрение, проба 5]: кейс-мисматч. Ключи constraints верхние
  ("FLEE"), ключи scores строчные ('flee', прод-трейш; Intent вероятно
  str-enum — HP-слой scores[Intent.FLEE] работает). Если да — ФАЗА 1
  (intent_str in scores) не матчит НИЧЕГО: мертвы ВСЕ constraints, включая
  жёсткие нули (NPIC full-veto, pain/shock, S189 commitment-нули).
  Корроборация прогона: flee/attack/approach в scores Борко при fatigue~81/
  energy=0 (t1080); orm/goran эмитят проактивные интенты при in_transit=True.
- ПРОТИВОРЕЧИЕ (вердикт L4 ЗАМОРОЖЕН): GC09B-full зелёный (assert _b != _a)
  — видимым кодом A обязан == B (ФАЗА 1 мертва, ФАЗА 2 одинакова).
  (альфа) невидимый body/stress-потребитель в хабе — греп/оракул-xray;
  (бета) оракул зелёный через артефакт — тогда зелёный гейт ADR-O-383
  измеряет не то, S250-приёмка требует ревизии.
- Пробы: -s прогон оракула; oracle-xray (полный diff трейсов); fatigue-греп;
  сигнатура _apply_physiology_deltas; Intent-кейс.

## Run v3 — oracle-xray чтение (2026-09-11)
- Оракул воспроизведён точно (A=WARN, B=OBSERVE; детерминизм межпроцессный).
- Translator-ребро жив в оракул-контексте: ctxB={FLEE/ATTACK/APPROACH/
  MANIPULATE:0.3}, ctxA={} — дословно.
- CONSTRAINTS-ПУТЬ ИСКЛЮЧЁН как механизм разницы A->B, трижды: (1) изменились
  ключи ВНЕ constraints (observe 0.0857->0.2216, idle 0.1417->0.2054, trade/
  help/warn/report/intimidate); (2) ни multiply (flee был бы 0.033, факт
  0.0814), ни min (все значения <0.3/отрицательные — не тронулись бы) не дают
  наблюдаемого; (3) греп: ноль fatigue/energy-читателей в decision_hub.py
  (единственное чтение тела — :444 NPIC-veto; :1601+ energy = affective_load).
- Остались кандидаты: (R) per-call RNG-поток (оракул: ДВА compute на ОДНОМ
  хабе — позиция 2 отличается от 1 независимо от тела) или (H) скрытый
  state-путь (напр. availability ниже :948 меняет число кандидатов).
- СТРУКТУРНЫЙ ДЕФЕКТ оракула: НЕТ A/A-контроля (та же дисциплина, что Мастер
  требовал в Phase 0). При (R) тест зелёный на шуме и прошёл бы с B:=A —
  вакуус-пасс; S250-приёмка «V1 GREEN 2/2» оказалась бы независимой от
  ADR-O-383.
- Полевая корроборация (R): approach Борко инвариантен сквозь оба crossing
  (~шум) — консистентно со state-независимым скорингом по fatigue/energy.
- LLM-retry-шум выводов = teardown-класс (сервер остановлен dispose раннера),
  атрибутирован заново; не блокер.
- Решающий зонд установлен: (1) same-hub A,A; (2) fresh-hub A vs B
  (позиционный контроль); (3) order-swap B,A; (+) Intent-кейс; (+) rng-греп.

## ФИНАЛЬНЫЙ ВЕРДИКТ L4 (2026-09-11, 20:5x) — противоречие разрешено
- Решающий зонд: (1) SAME-hub A,A — ДРЕЙФ ЕСТЬ (trace#1 != trace#2 при
  идентичном состоянии; та же пара значений, что A/B оракула);
  (2) FRESH-hub A vs B — БАЙТ-ИДЕНТИЧНЫ (fatigue 0.22 vs 90.2, energy 99.7
  vs 9.7); (3) order-swap B,A — паттерн следует ПОЗИЦИИ, не состоянию.
  ГИПОТЕЗА (R) ПОДТВЕРЖДЕНА; (H) скрытого state-канала — НЕТ.
- Механизм в коде: decision_hub.py:1037 noise = rng.uniform(±SCORE_NOISE_
  RANGE) на каждый intent (:1052, «±10% рандом» :261); оракул: DecisionHub(
  seed=0) легаси random.Random, два compute — второй на позиции-2 потока;
  маржа WARN(0.1939) vs OBSERVE(0.0857) < размаха шума -> флип = артефакт.
- Intent-кейс: Intent.FLEE=='flee' True; =='FLEE' False -> L4-F9
  подтверждён: ФАЗА 1 (decision_hub:565) не матчит НИЧЕГО; мертвы ВСЕ
  constraints (NPIC full-veto/pain/shock/blood_loss/S189 commitment-нули).
- ВЕРДИКТ: (а) GREEN обе оси (908/1088; контроли индивидуальны; maid v2 =
  недостижимый порог, калибровочный вклад); (б) BODY->translator GREEN,
  translator->scores/selection ОТСУТСТВУЕТ (F8 soft-cap без потребителя;
  F9 кейс-мисматч; оракул зелёный на RNG-шуме = vacuous pass — S250 «V1
  GREEN 2/2» независим от ADR-O-383, ревизия оракула + §5d-строки S250
  обязательна); (в) пространство выбора не изменилось (неконкурентность
  ∩ мёртвый consumer; WARN x2 без атрибуции); (г) OPEN (двойной
  отрицательный контроль; L16: DM не читает fatigue).
- ФОРМА ЗАКРЫТИЯ: L4-BODY/TRANSLATOR GREEN, ENFORCEMENT GAP TOTAL (F8+F9),
  GAMEPLAY EDGE OPEN. Клетка L4 — OPEN до рантайм-фронта (решение очереди —
  Мастер). ADR-O-383 испытан полем полностью; полевой эксперимент поймал
  разрыв, который юнит-зелёный не мог поймать структурно (гипотеза-класс
  «зелёный гейт измеряет не то»).
- Уроки сессии: (U1) %TEMP%-зонд с path-инъекцией и A/A-контролем = метод
  ревизии любых A/B-гейтов (предложить канону как стандартный приём);
  (U2) cd backend + python -c: путь НЕ наследуется — всегда path-инъекция
  в скрипте; (U3) runlog append-режим сохраняет ДО-ноги нескольких прогонов
  в одном файле — источник «контрольных» ног v2/v3.

════════ ИТОГОВАЯ СВОДКА L4 / S254 ════════
АРТЕФАКТЫ: l4_s254_samples_run1/2/3.jsonl; l4_s254_run_console.txt (4 прогона);
  replay-сессии 479dacd7 (65т), 09db403b (591т), b829f0f5 (1091т); дневник
  (этот файл, 17 блоков). Ноль правок репо; ноль git; всё локально.
РЕЖИМ: fresh/cockpit-класс harness/flags OFF/LLM ON/без ускорителей (приказ
  Мастера 2026-09-11); санкция v3-TARGET=guard_borko («Можно Борко»).
НАХОДКИ-РЕЕСТР: L4-F1 тело не персистится (restart=new=сброс); L4-F2 new_game
  '_cache' (RE-зона); L4-F3 кокпит 'день' тик 0; L4-F4 шум; L4-F5 реплей
  флашится в dispose (ретракция); L4-F6 DLG_QUEUE-кавиат (Н-56); L4-F7
  инструментальный stall v2; L4-F8 soft-cap без потребителя; L4-F9 кейс-
  мисматч ФАЗА-1 (все constraints мертвы).
ОТКРЫТЫЕ ФРОНТЫ (решение очереди — Мастер): (1) рантайм-фронт ADR-O-383 —
  потребитель constraints + кейс-нормализация + переведённый оракул
  (fresh-hub + A/A + noise-off режим); (2) ревизия §5d-строки S250 и канона
  ADR-O-383 (observation-scope correction оказался вакуусным); (3) maid-
  результат -> CALIBRATION_CANDIDATE (порог достижим только непрерывной
  нагрузкой; rest-seeking = ветка Потребности/MVP ТЗ); (4) эскалации соседям:
  L4-F2 (RE), Н-56-класс; (5) энергетический пол 0 без side-effects —
  наблюдение.
СЛЕДУЮЩИЙ ШАГ (приказ Мастера, в силе): прочитать mvp_secret_tavern_dev_tz_
  p1_p11.md ЦЕЛИКОМ и совместить реальное состояние Needs/Body/Activity с
  тем, что нужно для следующего игрового вертикального среза.

## ПОСЛЕ-L4 ПРИКАЗ МАСТЕРА (2026-09-11, вечер) — ратификация и очередь
- Вердикт S254 ратифицирован. Введён класс архитектурного риска:
  CAUSAL FALSE GREEN (Vacuous Green) — зелёный тест, доказывающий не тот
  механизм, ради которого существует; опаснее красного (красный честен).
  Формальная канонизация в Устав/ADR — после разморозки док-работ.
- Очередь: (1) mvp_secret_tavern_dev_tz_p1_p11.md ЦЕЛИКОМ -> (2) матрица
  MVP x CODE x FIELD (без исправлений и нового кода) -> (3) минимальный
  causal repair (F9 кейс-дефект; F8 consumer; oracle repair: fresh-hub +
  A/A + noise-off + position control) -> (4) DECISION GATE: repair отдельно
  vs EAT как первый runtime-consumer (EAT = кандидат на одновременное
  доказательство BODY) -> EAT -> PROTECT -> WORK -> SOCIAL -> Living
  Trajectory.
- Принцип: не строить этаж деятельности поверх контура без enforcement
  («система существует -> данные существуют -> тест зелёный -> причинности
  нет» — анти-паттерн). Метод S254 (A/A-зонд) — стандарт ревизии A/B-гейтов.
- Гигиена: дубль итоговой сводки выше — удалить при следующей записи.

## ПОСЛЕ-МАТРИЧНЫЙ ПРИКАЗ МАСТЕРА (2026-09-11, ночь) — очередь утверждена
- Порядок: needs-probe (observation only) -> R1 (де-грин GC09B-full,
  контракт: fresh hub + A/A + noise-off + сохранение causal claim; строго
  тестовый слой) -> MVP M1 = П1+П2 ГЛАВНЫЙ ФРОНТ («впервые замкнуть Truth
  -> NPC Knowledge»: TruthState -> initial_holders -> EventMemory(secret_id)
  -> persistence -> canon-sync) -> DECISION GATE после M1 (аудит CANON ->
  HOLDER -> NPC STATE -> MEMORY -> SQLITE -> RELOAD -> SAME KNOWLEDGE, с
  обязательным A/A-контролем) -> вертикали B (речь) / C (discovery) / D
  (финал). R2 — отдельное окно (F9 = semantic wire break, не MVP-блокер).
  EAT — после первого живого игрового контура.
- Рельс IV GAMEPLAY OBSERVABILITY принят в доктрину (последняя миля к
  игроку — тот же класс болезни: player_beliefs computed-not-passed).
- Ветка: Потребности_2 = архитектурный потомок Потребности_1, НЕ
  production equivalence (урок S254).
- M1 затрагивает домен memory (EventMemory) -> ADR-PRE-FLIGHT чеклист
  обязателен перед кодингом (Устав 11.2).
- Immutable evidence при git-бане = файловые снапшоты в reports/history.

## R1 исполнен (2026-09-11): GC09B-full де-грин
- Immutable evidence: reports/history/gc09b_vacuous_green_immutable.txt
  (git-бан: история только файлом).
- Новый контракт: fresh hub x каждый decide + A/A-контроль + noise-off
  (monkeypatch decision_hub.SCORE_NOISE_RANGE=0) + causal claim в усиленной
  форме (B[k] ~ A[k]*0.3 для flee/attack/approach).
- Ожидание исхода: A/A GREEN (прибор детерминирован), causal-ассерт RED —
  назначенный диагноз F8/F9 (fix = R2, не ретушь). Сьют gameplay: 10 GREEN +
  1 RED-диагноз — честное состояние по мандату («красный = диагноз»).

## Needs-probe + R1-исход (2026-09-11, ночь)
- R1 ЗАКРЫТ: gc09a GREEN; gc09b RED-диагноз назначенно (flee A=0.125=B;
  A=IDLE=B under noise-off; A/A GREEN — прибор детерминирован, второго
  RNG-терма нет). Vacuous GREEN ликвидирован; сьют честен.
- Needs-probe: WRITER ЖИВ (legacy substrate confirmed): needs к тику 20;
  динамика индивидуальна (maid hunger сброс по еде 0.32->0.0; tornin рост;
  orm oscillation). Матрица: needs writer=жив, consumers=?
- L4-F10-КАНДИДАТ [Double Truth, EAT-аудит]: needs['fatigue'] (0-1,
  LifeEngine) != body_state['fatigue'] (0-100, BodyEngine) — borko:
  needs-fatigue плоский 0.16 при body +0.075/тик. Desire-рельс читал бы
  ПЕРВЫЙ, ADR-O-383 капит ВТОРОЙ. Коллизия материализуется при EAT-ON.
- EAT-аудит-входы: goran-сатурация (needs=1.0 пин, потребитель молчит);
  thief_shadow NO-NEEDS-KEY (сон?). Греп needs-потребителей + _tick_needs
  чтение — отложенные пробы, не блокеры.
- Очередь по приказу: следующий шаг — MVP M1 PRE-FLIGHT (главный фронт).

## M1/P1 Шаг 1: EventMemory.secret_id (2026-09-11, ночь)
- Immutable: reports/history/p1_step1_npc_state_immutable.txt (git-бан).
- Поле Optional[str]=None в Theatre-блоке (frozen, WARA: дефолт — старые
  сейвы/конфиги грузятся без миграции). Сериализация (sqlite_store +
  memory_manager) — Шаг 2 по фактическому коду (в npc_state.py to_dict
  НЕТ — расхождение с ТЗ-якорями 311-313/1045-1048 зафиксировано).
- Гейты: ruff; import-check; gameplay-сьют (ожидание 10 GREEN + 1
  RED-диагноз R1 — назначенный, не регрессия).

## M1/P1 Шаг 1 — гейты (2026-09-12)
- Поле live: secret_id Optional[str]=None (Optional в импортах был).
- ruff: 1 F841 `ss` unused npc_state.py:1172 — ЧУЖОЙ (наша правка ~:239);
  кандидат-происхождение S252-R1 (7b4b4805, from_legacy round-trip fix);
  прецеденция для нашего окна — immutable-снапшот. Развилка Мастеру:
  (а) hygiene-удаление (рекомендовано) / (б) PRE-EXISTING-долг.
  Шаг НЕ закрыт до решения (гейт = барьер).
- gameplay: 10 passed + 1 failed = gc09b R1 RED-диагноз (назначенный
  де-грин), НЕ регрессия Шага 1. R4A = teardown-класс.

## F841 закрыт + археология Шага 2 (2026-09-12)
- F841-контракт исполнен: фикс (удаление только ss-присваивания) применён
  Мастером по санкции (а). Прецедентность: снапшот p1_step1 :1171 (до нашей
  правки) — PRE-EXISTING, candidate neighbor-origin, provenance НЕ
  расследуется (контракт Мастера). Гейт-верификация: ruff npc_state.py.
- sqlite_store карта: schema CREATE IF NOT EXISTS :149-173 (+индексы :177);
  writers save_event_memory :393 / save_event_memories_batch :488
  (INSERT OR REPLACE); reader load_event_memories :457 (SELECT *);
  delete_campaign :555.
- READER-ФАКТ: load_narrative_from_sqlite = EventMemory(**_d) из SELECT *
  -> колонки == kwargs конструктора -> reader-правка НЕ нужна (новые БД:
  колонка придёт сама; старые строки: ключа нет -> дефолт None).
- ALTER-прецедент backend/app = 0 -> Шаг 2 вводит МИГРАЦИОННЫЙ ГВАРД
  (PRAGMA table_info + ALTER ADD COLUMN secret_id) для существующих сейвов
  — первый ALTER-прецедент проекта, зафиксировать в мини-ADR M1.
- Проба INSERT-маппинга промахнулась паттерном (реальная строка INSERT OR
  REPLACE INTO) — переиздана чтением диапазонов :392..456 / :487..548.

## M1/P1 Шаг 2: персистентность secret_id (2026-09-12)
- Immutable: reports/history/p1_step2_sqlite_store_immutable.txt.
- 4 патча: (A) CREATE + secret_id TEXT NULL + idx_event_memories_secret;
  (B) миграционный гвард PRAGMA table_info + ALTER ADD COLUMN (первый
  ALTER-прецедент проекта — для существующих сейвов; CREATE не расширяет
  живые таблицы); (C) writer save_event_memory + d.get("secret_id");
  (D) writer save_event_memories_batch + d.get("secret_id").
- Reader не тронут (EventMemory(**_d) из SELECT * — колонка приходит сама).
- Round-trip-смоук: single/batch/None/old-schema-migration — PASS-ожидание.
- Гейты: ruff sqlite_store / IPT-хвост.

## M1/P1 Шаг 2 — order-фикс индекса (2026-09-12)
- Smoke-прогон #1 поймал дефект МОЕЙ компоновки: idx_event_memories_secret
  стоял ДО миграционного гварда -> на старой БД OperationalError (no such
  column). Новый-DB путь прошёл все ассерты (writers C/D + reader живы).
- Фикс: индекс перенесён ПОСЛЕ гварда (ALTER -> индекс -> commit;
  идемпотентен для новых БД). Урок в мини-ADR M1: DDL-порядок при
  миграционных гвардах — индексы на мигрируемые колонки создаются только
  после ALTER.
- Smoke #2 — ожидание ROUND-TRIP OK (single+batch+None+old-schema).
- IPT 45/45 уже зелёный на пост-патч состоянии (фикс порядка DDL поведения
  не меняет); ruff-гейт повторён после фиксов.

## M1/P1 Шаг 2 — order-фикс индекса (2026-09-12; запись восстановлена)
- Smoke #1 поймал дефект МОЕЙ компоновки: idx_event_memories_secret стоял
  ДО миграционного гварда -> старая БД: OperationalError (no such column).
  Новый-DB путь прошёл все ассерты уже тогда (writers C/D + reader живы).
- Фикс: индекс перенесён ПОСЛЕ гварда. Гварды на диске: PRAGMA :190 ->
  ALTER :194 -> индекс :201. Smoke #2: ROUND-TRIP OK (single+batch+None+
  old-schema-migration). ruff чист; IPT 45/45.
- Урок в мини-ADR M1: при миграционных гвардах индексы на мигрируемые
  колонки создаются ТОЛЬКО после ALTER.
- Гигиена: предыдущий Add-Content взял устаревший $add — блок «Шаг 2»
  оказался в дневнике дважды (дубль выше); этот блок — каноническая
  запись order-фикса.

## M1/P1 Шаг 3a: сеялка+запросы (инертные) (2026-09-12)
- Immutable: reports/history/p1_step3_npc_loader_immutable.txt.
- Новое: _canon_truth_state (ленивый синглтон, прецедент resolver:18;
  отказ=пустой канон, деградация канала); _seed_canon_secret_memories
  (per-NPC инверсия ТЗ-псевдокода — точка гидратации обрабатывает одного
  NPC; дедуп по secret_id; формат=_convert_origin_events-паттерн);
  who_knows/known_secrets (фильтры по полю — не новая система).
- Активации НЕТ (вызов не вставлен) — поведение не меняется.
- Блокирующее 3b: _restore_narrative_cache (:529) — если роняет secret_id
  при write-back-цикле -> бесконтрольный рост кэша; дочитка обязательна
  (§12 WARA). Ожидание карты: 25 holder-памятей / 17 секретов.

## M1/P1 Шаг 3a: гейты + дочитка 3b (2026-09-12)
- SEED-UNIT OK: maid=5/borko=5/shadow=6/orm=3/goran=3/tornin=3 (total 25);
  who_knows 17/17 == initial_holders; дедуп A/A GREEN; non-holder=0.
- ruff: W291 :280 trailing-whitespace — позиция ВЫШЕ нашей вставки; 
  прецедентность проверяется по immutable-снапшоту (снимок ДО вставки);
  класс = F841-дисциплина (hygiene-fix по санкции / PRE-EXISTING-долг).
  Геометрия вставки требует верификации (блок ~:528 — на 47 строк раньше
  ожидаемого — гипотеза: съеденные пустые строки в here-string-стыке).
- Дочитка 3b: write-back-цепочка npc_state.py:1038-1051 (to-dict) ->
  _restore_narrative_cache -> EventMemory. Restore БЕЗ secret_id =
  WARA-разрыв (restore теряет -> дедуп не видит -> сеялка дублирует ->
  рост кэша по циклу гидратации). Патч 3b включает secret_id в restore.
- Гидратация = per-tick (5 вызовов: pipeline_runner x2, dialogue_memory_
  subscriber, npc_tick_pipeline:170) — активация здесь автоматически
  даёт A/A-стресс-тест ростом (дедуп обязан держать кэш константой).

## M1/P1 Шаг 3b: активация + WARA (2026-09-12)
- W291 :280 = PRE-EXISTING (снапшот :281) — класс F841, патч готов,
  применяется по санкции Мастера (fix/leave).
- Геометрия вставки ЧИСТАЯ: convert :489 -> блок 3a :529-627 -> restore :629.
- Write-back-факт: npc_state.py:1040 {**_item.__dict__} — secret_id пишется
  автоматически (dataclass-поле). WARA-разрыв ровно один: _restore без поля.
- Активация: сеялка поверх всех трёх веток гидратации в
  load_l2_state_from_runtime_dict; дедуп = идемпотентность для per-tick
  вызовов (npc_tick_pipeline:170 и др.).
- Гейты: живой harness (17/17 через реальную гидратацию; A/A-стресс
  кэш-константа; write-back->restore round-trip) + ruff + test_npc_loader
  + IPT.

## M1/P1 Шаг 3b — живой гейт #1 (2026-09-12)
- ЯДРО GREEN: гидратация who_knows 17/17 == initial_holders (реальная
  load_l2_state_from_runtime_dict — сеялка АКТИВИРОВАНА и работает в
  per-tick-точке); A/A повторная гидратация константна; known_secrets
  5/5/3/3/3/6 == карта сеялки; ruff ЧИСТ (W291 закрыт — PRE-EXISTING по
  снапшоту, фикс рукой Мастера, класс F841-прецедента); test_npc_loader
  7/7; IPT 45/45.
- WARA-секция НЕ исполнена — мой баг зонда: to_persistence_dict —
  staticmethod(state, npc_dict), вызван как инстанс-метод (TypeError).
  Продукт не виновен; финальная строка гейта не напечатана — шаг 80%.
- ЧЕСТНАЯ ОГОВОРКА: A/A-стресс скрипта слаб (одни и те же дикты дважды,
  без write-back) — growth-loop не различает. Настоящий тест: зонд v2
  (write_back-симуляция :1040 -> restore -> re-seed -> полная цепь).
- Открытый вопрос: применён ли Патч-1 (secret_id в _restore)? Живой гейт
  не различает; чтение :629+ и зонд v2 закроют.

## M1/P1 Шаг 3b — ЗАКРЫТ: WARA-VERDICT GREEN (2026-09-12)
- Зонд v2: гидратация#1 cache=10/canon_ids=5; write-back 5/5; restore 5/5;
  re-seed 10->10; полная цепь 10->10 — growth-loop НЕТ. WARA GREEN.
- РЕТРАКЦИЯ: «Патч-1 нужен» — ложная тревога. _restore_narrative_cache
  строит EventMemory(**_payload) (полный словарь-пассинг, :645-653) —
  secret_id проходит в конструктор автоматически. Отдельный патч не
  применялся и не нужен; WARA гарантирована дизайном restore (§12-паттерн
  полного пассинга) + write-back __dict__ (npc_state.py:1040).
- Активация сеялки: ветка в load_l2_state_from_runtime_dict поверх всех
  трёх путей кэша; per-tick идемпотентность доказана.
- (Гигиена: прошлый $add не содержал блока 3b-гейтов — восстановленная
  запись выше; дублей нет.)

## M1/P1 Шаг 4: формальный ТЗ-гейт (2026-09-12)
- Новый файл tests/gameplay/test_p1_secret_identity.py (5 тестов):
  (1) 17 ассертов who_knows == initial_holders; (2) holdout + кардинальность
  25; (3) A/A-контроль (метод S254); (4) RELOAD SQLITE->load->SAME KNOWLEDGE
  (гейт Мастера после M1); (5) old-save smoke (None-дефолт + восполнение
  сеялкой).
- Гейты: ruff / file-прогон / IPT-хвост.
- После зелёного: M1/P1 готов к первому настоящему аудиту Мастера
  (CANON -> HOLDER -> NPC STATE -> MEMORY -> SQLITE -> RELOAD -> SAME
  KNOWLEDGE — цепь, требованная Мастером, покрыта тестом 4).

## M1/P1 Шаг 4 — фикс F821 x2 (2026-09-12)
- Мой баг: `h` вместо `harness` в двух тестах (копипаста хелпера-сигнатуры).
  ruff-гейт поймал (2 remaining after autofix); патч выдан; "2 fixed" ruff
  требует верификации импорт-блока.
- Прогон-вывод прошлый обрезан — итоговых строк не видно; повтор полным
  паттерном + повторный прогон файла (ретур-смоук A/A).

## M1/P1 Шаг 4 — fixture-прогрев (2026-09-12)
- Диагноз 5/5 RED: inspect_npc -> None до первого тика (LifeEngine-кэш
  пуст после new_game); raw_data=None -> psyche.get падает (:712).
  Продукт не виновен (зонды той же сессии с advance_ticks(3) проходили).
- Фикс: advance_ticks(3) в fixture (гидратация живая, прогревProduction).
- Гейты: ruff + 5/5 ожидание + ретур-смоук.

## M1/P1 Шаг 4 — RELOAD-гейт поймал product-дефект writer'а (2026-09-12)
- Диагноз (debug-зонд): 10 памятей maid -> raw SQL rows: 1. ВСЕ памятей
  имеют sequence_id=0 (origin дефолт + seeder дефолт) -> mem_id
  {npc}_seq_0 для всех -> INSERT OR REPLACE схлопывает батч в одну строку
  (осталась origin с secret_id=None). Гейт Мастера сработал как задуман:
  поймал реальную потерю данных в persistence-слое.
- Ретракция-уточнение: мой smoke #2 прошёл мимо (задавал sequence_id
  руками); enum-гипотеза опровергнута пробой (sqlite адаптирует Enum).
- Доп. находка [канон]: save_event_memory/batch — 0 production-вызовов
  (греп backend/app: только определения) — RELOAD-гейт Мастера испытывает
  мёртвый в production провод (класс «орган без сосуда»; P2/M-нота).
- Фикс-1 (product): mem_id + _{i} (позиция батча) — уникальность PK;
  M1-долг: канонизация id-стратегии event_memories.
- Фикс-2 (тест): round-trip только канон-памятей (предмет гейта).
- Гейты: ruff x2 / 5/5 ожидание / IPT.

## M1/P1 — ЗАКРЫТ ФОРМАЛЬНО (2026-09-12)
- test_p1_secret_identity.py: 5/5 PASSED (every_holder 17/17; holdout+
  cardinality 25; A/A; RELOAD SQLITE->SAME KNOWLEDGE; old-save + seeder
  восполняет). ruff чист (обоих файлов); IPT 45/45.
- По пути закрыто: F821 x2 (мой баг), fixture-прогрев (inspect_npc пуст
  до первого тика), product-дефект writer'а (mem_id PK-коллизия при
  sequence_id=0 у всех -> INSERT OR REPLACE схлопывал батч; фикс: _{i}
  суффикс; M1-долг: канонизация id-стратегии event_memories).
- Канон-мётки: save_event_memory/batch — 0 production-вызовов (мёртвый
  провод, P2/M-нота); seeder работает поверх per-tick гидратации.
- Цепь Мастера (CANON->HOLDER->STATE->MEMORY->SQLITE->RELOAD->SAME
  KNOWLEDGE) покрыта тестом 4; A/A — тестом 3.

## P2-PRE-FLIGHT: инвентаризация (2026-09-12)
- 16 cfg-секретов (is_secret origin), ВСЕ secret_id=None, все содержательно
  мапятся 1:1 на канон (полная карта в сессии). shadow_guild_membership —
  единственный канон-секрет без конфиг-носителя (сеялка закрывает).
- known_by-расхождения vs canon-holders: ОДИН кластер (подвал: shadow
  лишний в обоих basement-секретах, tornin лишний в lusya_basement);
  остальные 14 совпадают дословно.
- ТЗ-вне-канонные секреты (borko «повышение», goran «аудит») на дереве
  НЕ найдены инвентаризацией — подтверждается грепом (проба 1).
- Рассинхроны №2-6 функционально закрыты сеялкой (holder имеет
  EventMemory(secret_id) через seeded). Живая субстанция P2: дубли (16
  origin без id) + чек is_secret->id + кластер №1 + чек-скрипт.
- Q1-рекомендация (Мастеру): маппинг secret_id в 16 конфигов + 1 строка
  в _convert_origin_events (origin-носители авторитетны, сеялка
  fill-the-gaps: 16+9=25, ноль дублей, без string-matching). №1:
  рекомендация «канон прав, known_by=legacy-метадата, не проверять»
  (альтернатива: расширить holders -> 27 + правка test_p1).

## P2-PRE-FLIGHT: пробы закрытия (2026-09-12)
- «Командир обещал повышение» — ЖИВ (borko.json:150) — вне-канонный секрет
  существует на дереве; инвентаризация пропустила (кандидат: не is_secret —
  проверяется чтением). «Аудит гильдии» — НЕ найден (ретракция ТЗ-якоря:
  удалён между срезом ТЗ и Потребности_2).
- load_social_base читает config/npc/social/*.json (НЕ единый
  village_relations.json из ТЗ) — формат: data["relations"] per-файл;
  enrichment: relationship_cache/base_values, шкала 0-1 -> 0-100.
- P2-досье: (i) вне-канонные секреты — реестр out_of_canon_* по факту
  (сейчас 1 подтверждён: borko-повышение); (ii) notes-факты social/*.json —
  是否 эпистемический материал для реестра (проба 2).

## P2-PRE-FLIGHT: досье закрыто (2026-09-12)
- borko «повышение» — is_secret: FALSE (биография, не секрет): вне-канонных
  СЕКРЕТОВ на дереве НОЛЬ (ретракция ретракции; ТЗ-якорь устарел —
  «аудит гильдии» удалён, «повышение» не секрет). out_of_canon-реестр
  НЕ требуется (ПРИ ЛОКАЛЬНОМ решении — см. Q-статус).
- village_relations.json жив в config/npc/social/ (не config/ ТЗ-пути);
  8+ notes-фактов — эпистемический материал («Торнин знает о шпионаже
  Люси», «Люся тайно влюблена в Борко»...). P2-решение по notes: по ТЗ —
  «только наличие, без парсинга» — в чек как наличие-факт, не контент.
- КОНТЕНТ-КАРТА (готова к применению по слову Мастера): 16 cfg-секретов
  -> 16 канон-id (borko: negligence/voyeur/bribe(goran-платит); goran:
  contraband/bribe(подкупает); lusya: basement/shadow_orders/orm_borko/
  borko_crush; orm: craft/tornin_order; shadow: investigation/
  suspects_lusya/first_kill; tornin: debt/basement) + известковый кластер
  (подвал: shadow-осведомлённость в 2 секретах, tornin в lusya_basement).
- ЖДУ решения: Q1 (маппинг secret_id в конфиги — рекомендую) и №1
  (канон-прав без расширения holders — рекомендую).
