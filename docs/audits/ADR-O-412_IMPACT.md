`ADR-O-412` [STANDARD] **IMPACT**
# ADR-O-412 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- economy / game_loop (только service_factories.py — tradable-проекция)

## Downstream Consumers
- `svc/economy/work_orders.py` (create_order_from_trade_intent читает stock_for_sale; settle_order: атомарный обмен) — потребитель, НЕ правлен; до ADR контур был мёртв (сток пуст у всех) — теперь活的 при наличии tradable-предметов в carried_objects архетипа
- `svc/npc/causal_slice_hunger.py` (capability-скан has_good) — косвенно обогащён: stock ≠ goods-семантика не тронута
- Зонды класса w5_probe (ручная инжекция stock_for_sale["ale"]=5.0) — легальность не меняется, но SSOT-путь теперь основной
- ADR-Net по файлу: связей в атласе не было (пустой impact — файл вне существующих зон)

## Runtime Impact
- RAM: +1 dict comprehension на построение профилей (микроскопический, однократно при ленивой инициализации)
- Latency: ноль в тике (построение профилей вне горячего пути)
- Детерминизм: фильтр по GOODS_PRICES — константа, сортировки не нужны (порядок словаря не влияет на потребителей)

## Sandbox Tests
- reports/f1a_probe.txt (прогон 1: F1a-факт, пустые стоки — ДО патча)
- reports/f1a_probe2.txt (прогон 2: GATE-F1B точный None-путь — ДО патча)
- reports/f1g_probe.txt / f1g_probe2.txt (первый живой ORDER + двойная правда голода)
- reports/f1b1_transfer.txt (6/6 приёмочных фактов β-Stage 1)
- reports/f1_clean.txt (чистый прогон после снятия DIAG — петля идентична ×3)
- IPT 49/49 до и после всех изменений

## Rollback
- Удалить tradable-блок (:129-142 service_factories.py) — stock_for_sale снова пуст у всех, поведение байт-в-байт прежнее (контур TRADE→ORDER честно молчит, как до ADR)
- DIAG-вставки сняты полностью (проверено Select-String: ноль следов)

## Ключевые факты (production-доказательства)
- β-Stage 1 (физическая передача) закрыт ВЕРИФИКАЦИЕЙ без единой правки settle: код work_orders:386-394 уже реализовал обмен (Iron River); недостающим звеном был только источник стока (наш ADR)
- Приёмка: V1 сток 1→0 у продавца; V2 goods 0→1 у покупателя; V3 количество 1.0 ровно; V4 gold 6.90→6.87 / 41.20→41.23 синхронно с COMPLETED; V5 no_stock:food для второго покупателя (wo_7, wo_10); V6 body_hunger не тронут settlement'ом (приказ Мастера соблюдён)
- Зарегистрированные швы (НЕ этот ADR): β-Stage 2 (goods→EAT→body_state), ресток, F1a-семантика S264-гейта (положительный факт: TRADE score=1.206 убит activity-гейтом, тик 12 прогона 1), goods-vs-stock Торнина (food:1 остаётся в личных goods после продажи)