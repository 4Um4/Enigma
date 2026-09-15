# ADR-O-391 Impact Audit

> Детальный аудит ОДНОГО ADR. Единый атлас: `docs/ADR (Architecture Decision Records).md`.
> Сессия: S256. Статус: ACTIVE (приёмка GREEN: юнит 17/17, SUPERBOX work_vertical_test W1–W5, IPT 45/45).
> Провенанс (§11.1.1): ADR заявлен как O-389; номер оказался двойной заявкой — атлас (:517) и
> IMPACT-путь заняты параллельной сессией GC-INTERRUPT (S257). WORK перенумерован в O-391:
> 20 код-сайтов и S256-запись обновлены. Первичный WORK-IMPACT по пути ADR-O-389_IMPACT.md
> был затёрт файлом параллельной сессии — восстановлен здесь полностью (финальная редакция).

## Суть
Замыкание разрыва «Intent.TRADE — выбор есть, исполнителя нет» минимальной сделкой
goran→ale→tornin на живом экономическом субстрате. Захороненный контур AUDIT #6
(TransactionEngine/TradeResolver/MarketState/Traveller/EconomicIntent) НЕ воскрешается.

## Changed Domains
- Экономика: Transaction (ORDER = запись по статусам PROPOSED→ACCEPTED→COMPLETED/FAILED),
  EconomicProfile (gold/goods/stock_for_sale — SSOT через service_factories),
  EconomyTracker.record_income (контракт «при каждой транзакции» замкнут впервые).
- Деятельности: ActivityType.SERVE + SERVE_SPEC; SERVE-ветка BODY_ACTION без предмета
  (CONSUME-путь не тронут); терминал SERVE = точка расчёта (settlement-хук).
- Желания: _NEED_TO_DESIRE += thirst→(ale, person).
- Решения: канал «давление желания → TRADE» в пайплайне (WORK-gated;
  urgency × WORK_TRADE_PRESSURE_K, K=1.0 — якорь шкалы: прецедент DecisionHub desire×1.5,
  канал ниже прецедента; эмпирика: K=0.5 проигрывал OFFER_JOB активной фазы — K_min
  задокументирован GREEN-прогоном; linearность: разные urgency → разное давление).
- Фазы: 6 (INTENT→ORDER: маршрутизация к продавцу предмета, дедуп открытого заказа),
  0 (work-pass: SERVE-материализация).

## Законы среза (L-W1..L-W7)
L-W1 ORDER=экономика(Transaction), SERVE=поведение(Activity) — онтологии не смешивать.
L-W2 DecisionHub не тронут: выбирает; сделку проводит пайплайн (execution-слой).
L-W3 Обмен атомарен: валидация ДО мутаций; FAILED не меняет мир.
L-W4 INV-WORK-PERSIST: мутации только SSOT-профили; deepcopy-слой тика read-only
     (ловушка S-143 pipeline_runner закрыта конструктивно — тест W2).
L-W5 WORK_ENABLED default OFF = no causal footprint: ни заказа, ни SERVE, ни economic
     writes, ни WORK-outcome; выбор TRADE не подавляется (OFF выключает исполнение
     вертикали, не DecisionHub).
L-W6 Transaction терминален однократно (повторный settle = no-op).
L-W7 Захороненный контур не воскресает; второй pipeline запрещён; якорь
     tick_orchestrator:904 не тронут.

## Downstream Consumers
- service_factories._economic_profiles (SSOT; читал DecisionHub-контур, пишет settlement;
  DI-проводка _economic_profiles_getter по паттерну P1.1f set_social_engine_factory).
- EconomyTracker (scene_init daily-проверка — теперь получает реальные record_income;
  проводка _economy_tracker тем же паттерном).
- ACTIVITY_OUTCOME на шине (наблюдаемость; подписчиков в backend ноль — проводка в
  память = LIFE INTEGRATION, R4).
- _NEED_TO_DESIRE / ACTIVITY_CATALOG (расширены; legacy_need_suppressed для thirst=False —
  легаси-движение не подавляется).

## Runtime Impact
- RAM: work_orders в scene_state (bounded, cap 32, выталкиваются только терминальные).
- Latency: work-pass O(orders) в Фазе 0; канал давления O(desires)/NPC в Фазе 5 —
  микросекунды; OFF = ноль вычислений (обе ветки гейтовы, call-time читатели).

## Sandbox Tests
- backend/tests/test_work_orders.py — 17 (рождение/гейты/маршрутизация/дедуп/атомарность/
  идемпотентность/гашение давления/OFF).
- backend/tests/sandbox/SUPERBOX/scenarios/work_vertical_test.py — W1 сделка+income;
  W2 переживает тик; W3 атомарный FAILED (before==after); W4 OFF = no causal footprint;
  W5 повторяемость (механизм, не сценарий).
- Регресс: eat_vertical_test — байт-идентичен до/после (E6–E9 предсуществующие;
  вердикт reverse-эксперимента с WORK OFF); IPT 45/45.

## Rollback
1. Мгновенный: WORK_ENABLED="" (default) — вертикаль нем, поведение байт-идентично базе.
2. Файловый: backup_s256/ (9 файлов сессии) — восстановить поверх.
3. Перенумерация: ADR-O-389→O-391 — комментарии/доки; поведение не затрагивает.

## Калибровочные заметки (не баги — решения будущих срезов)
1. Pressure-канал накрывает ЛЮБОЙ рыночный subject желания (food=1.0 у Люсьи/Торнина
   даёт trade-модификатор 1.0; ордеров нет — food никто не продаёт; наблюдаемо).
2. _try_onset подбирает serve-желания любому NPC с urgency≥0.5 к любому предмету каталога.
3. SocialTargetResolver адресует TRADE к социальному соседу, не к продавцу — маршрутизация
   ордера компенсирует; единый резолвер «кто продаёт» — кандидат SOCIAL.
4. Дерево: S254/PROTECT/O-386 в этом дереве отсутствуют (git-факт) — реестр честен.