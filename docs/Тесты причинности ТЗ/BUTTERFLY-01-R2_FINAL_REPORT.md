# BUTTERFLY-01-R2 — ФИНАЛЬНЫЙ ОТЧЁТ РОЯ

**Задача:** устранение асимметрии игрок/NPC — от сценария для игрока к универсальным механикам открытого мира.
**Дата:** 2026-11-03 · **Объект аудита:** коммиты BUTTERFLY-01 `ce7c225`, `6dff104`, `b7f930f`, `1a8dee8` + production-код · **Коммиты R2:** `de0abe5` (код) → `00efbd3` (гайд)
**Статусы:** 🟢 подтверждено реальным вызовом/тестом/прогоном · ⚠️ частично · 🔴 отсутствует · 🧠 требует архитектурного решения

---

## 1. Архитектурное сравнение Player и NPC

| Контур | Игрок | NPC | Один механизм? |
|---|---|---|---|
| Источник намерения | текст (лексикон мира) | потребности/характер/цели (desire → DecisionHub) | — (различие легально: только источник) |
| Рождение заказа | `create_order_direct` через адаптер `player_purchase.py` (turn_pipeline.py:214) | `create_order_from_trade_intent` (post_decision.py:110) из уже выбранного TRADE-интента | 🟢 ДА — одна фабрика записи (`work_orders.py`), Transaction PROPOSED в scene_state |
| Исполнение | `settle_order` синхронно (жизненный цикл заказа в одном вызове — игрок ждёт у стойки) | `settle_order` через SERVE-деятельность (асинхронно, activity_lifecycle_service.py:253) | 🟢 ДА — один settlement: валидация→атомарный обмен→казна/доход→события |
| Источник стока | хранилище предприятия (продавец-персонал) или личный сток продавца | тот же резолвер `resolve_establishment_sale` | 🟢 ДА |
| Финансы | платёж из `EconomicProfile.gold` покупателя → **казна предприятия** | то же | 🟢 ДА |
| Права на запасы | посетитель: только заказывать | персонал: can_serve/can_manage_stock по назначению; посетитель-NPC: только заказывать | 🟢 ДА (роли, не статус «игрок/NPC») |
| Восприятие речи | полноправный наблюдатель мембраны (S199), знание — не EpistemicStore | EpistemicStore + provenance | ⚠️ игрок участвует в той же системе восприятия; хранилище знаний игрока — другая плоскость (avatar/клиент) 🧠 |
| Передача информации | речь → события → мембрана (тот же канал) | report-канал + мембрана | 🟢 ДА (тесты D/E) |
| Реакция на оскорбление | получает последствия через отношение NPC | DecisionHub S197/эпистемика | 🟢 |

Ключевой факт аудита: **до R2** существовали два независимых исполнения покупки
(игрок: собственная логика в `player_purchase.py`; NPC: WORK-вертикаль, флаг OFF),
и запас юридически принадлежал трактирщику лично. **После R2** оба субъекта
входят в одну фабрику заказа и один settlement.

## 2. Анализ player_purchase.py (было → стало)

**Было (v1, BUTTERFLY-01):** НЕ адаптер — полная торговая бизнес-логика:
лексикон → резолв продавца → валидация → атомарный обмен `stock_for_sale`/
`goods`/`gold` → `record_income` → TRADE-событие. Параллельная реализация
контракта L-W3/L-W4 `settle_order` (два места истины об исполнении сделки).

**Стало (v2, R2):** тонкий Player Intent Adapter:
1. распознавание намерения в тексте (лексикон «пиво/эль» — адаптерная забота
   ввода, NPC-намерения уже семантичны);
2. выбор контрагента: персонал заведения с can_serve (target-приоритет) →
   дежурный персонал хранилища (роль-ранг→id, детерминизм) → названная цель →
   архетипный fallback личных продавцов;
3. рождение заказа **той же фабрикой**, что у NPC — `create_order_direct`;
4. исполнение **тем же settlement'ом** — `settle_order` (shop `via_establishment`
   фиксируется в заказе);
5. TRADE-событие; честные отказы (`no_seller`/`no_gold`/`no_stock:<good>`)
   с отключением money-имитации RulesSubscriber (контракт сохранён).

Строк торговой логики (обмен/цены/доход) в модуле — ноль. Доказательство
единства: тест `test_a_player_orders_beer_via_bar` проходит через
`create_order_direct`+`settle_order` и видит `via_establishment="tavern"`;
тест v1 `test_purchase_success_ssot_mutations` (личная продажа вне заведения)
проходит БЕЗ изменений контрактаSuccess-пути — та же функция теперь исполняет
сделку тем же settlement'ом.

## 3. Схема общей торговой механики

```
намерение → адаптер ввода → create_order_direct (Transaction PROPOSED, scene_state)
   → settle_order:
       resolve_establishment_sale(scene, seller, goods)     ← предприятие?
         ДА:  валидация по storage.goods → storage_withdraw (can_serve)
              buyer.gold −p → establishment.treasury +p → via_establishment
         НЕТ: валидация по seller.stock_for_sale (личная продажа торговца)
              buyer.gold −p → seller.gold +p
       buyer.goods +qty   ← покупатель: игрок ИЛИ NPC, без различий
       COMPLETED/FAILED   → ACTIVITY_OUTCOME обеим сторонам (+record_income)
   → TRADE-событие (адаптер игрока; NPC-путь — через SERVE-конвертер)
```

Гейт `WORK_ENABLED` остался ТОЛЬКО на рождении заказов из давления желаний NPC
(поведенческий флаг рантайма, L-W5). `settle_order`/`fail_order` гейтятся
существованием заказа — терминал доступен всегда, когда заказ существует.
Фикс по ходу R2: коллизия детерминированного id повторной сделки в одном тике
перезаписывала терминальную запись реестра (потеря причинной цепочки) —
введён детерминированный суффикс `#k` (create_order_direct).

## 4. Схема барной стойки и её свойств

`scene_state["establishments"]["tavern"]` (сид: `config/world/establishments.json`):

```
establishment "tavern" (Трактир — предприятие)
  owner_id: "tavern_keeper_tornin"        ← смена владельца = правка данных
  treasury: {"gold": 12.0}                 ← финансы предприятия
  storage:  {"storage_id": "tavern_storage",
             "goods": {"ale": 6.0, "food": 4.0}}   ← Хранилище: учёт количеств
  service_points: [{"service_point_id": "bar_counter",   ← Барная стойка
                     "label": "Барная стойка",
                     "storage_id": "tavern_storage",     ← связь с хранилищем
                     "served_goods": ["ale", "food"],
                     "revenue_to": "tavern"}]
  staff: {"tavern_keeper_tornin": {role: manager, can_serve: T, can_manage_stock: T},
          "maid_lusya":        {role: server,  can_serve: T, can_manage_stock: F}}
```

Свойства MVP (R2 §3.1): хранение 🟢, учёт количества/состава 🟢, выдача 🟢
(storage_withdraw), пополнение 🟢 (storage_deposit, can_manage_stock),
проверка наличия 🟢 (storage_stock), атомарное списание при заказе 🟢
(валидация ДО мутации, L-W3-паттерн), определение доступных операций 🟢
(served_goods/can_serve/can_manage_stock), ограничение доступа 🟢, взаимодействие
с NPC и игроком 🟢. Резервирование как отдельная операция не введено —
атомарность достигается validate-then-mutate в одном settlement-вызове 🟢.

🧠 Сознательно НЕ сделано: спец-класс «барная стойка»; WorldObject-архетип `bar`
(реестр спавнера закрыт, W2 substrate-only — мини-ADR в Части III). Свойства
встроены в общую систему: предприятия живут в scene_state по прецеденту
work_orders, сид — авторские данные по прецеденту factions.json.

## 5. Схема прав доступа

Разделение прав R2 §3.2 — через общие назначения, без id-проверок:

| Право | manager (Торнин) | server (Люся) | посетитель (игрок, Боро, Орм, …) |
|---|---|---|---|
| заказать/получить товар | — | — | 🟢 любой субъект |
| обслуживать заказ (выдавать) | 🟢 can_serve | 🟢 can_serve | 🔴 not_authorized |
| списать под заказ | 🟢 (в settlement) | 🟢 (в settlement) | 🔴 not_authorized |
| видеть/изменять запасы (пополнять) | 🟢 can_manage_stock | 🔴 not_authorized | 🔴 not_authorized |
| назначать персонал / сменить владельца | (данные конфига предприятия — правки seeds/сейва, не кода) | | |

Проверки живут в `establishment.can_serve/can_manage_stock/storage_withdraw/
storage_deposit` (defense-in-depth: settlement проверяет право ещё раз при
списании). Тест F: посетитель-NPC и игрок получают `not_authorized`; Люся
(server) не пополняет; Торнин (manager) пополняет. Новый NPC завтра получает
возможности через запись в `staff`/создание назначения — без нового файла
`new_npc_purchase.py` 🟢 (критерий §11 R2).

## 6. Схема автономного заказа NPC

```
physiology/needs (SSOT needs-слой; thirst→ale, hunger→food — desire_generator)
  → desire(subject, urgency)                    (Фаза 0; urgency ≥ 0.5)
  → trade pressure (npc_tick_pipeline.py:411, WORK_TRADE_PRESSURE_K)
  → DecisionHub: сам выбирает intent            (давление искривляет utility,
                                                 не приказывает — L-W2)
  → CommunicationIntent(trade) → Фаза 6 (post_decision.py:110)
  → create_order_from_trade_intent: выбор продавца — персонал хранилища
    предприятия ПЕРВЫМ, затем личные продавцы (детерминизм, дедуп открытого заказа)
  → run_work_orders_pass (simulation.py:82): SERVE-деятельность продавца
    на сцене заказа (S266-W5: продавец должен быть там телом)
  → SERVE-терминал (activity_lifecycle_service.py:253) → settle_order
```

Подтверждение реальным прогоном (тест B, чистый процесс): Боро — посетитель,
НЕ персонал, ни одной строки кода с его именем — заказ `wo_2_guard_borko_
tavern_keeper_tornin_ale` рождён на тике 2 из жажды 0.8, SERVE Торнина на
тике 3, COMPLETED: хранилище ale 6→5, казна +0.01, эль у Боро. Законный
не-исход тоже зафиксирован: в другом прогоне DecisionHub выбрал общение вместо
покупки — NPC не принуждается 🟢.

## 7. Схема социальной передачи информации (универсальность)

Один канал для всех источников: событие речи → мембрана слуха
(`ClaimEventSubscriber.on_claim_event`: радиус+can_observe, S199 игрок —
полноправный наблюдатель) → `BeliefRevisionEngine.revise` (reliability =
trust(слушатель→источник-рта); provenance: source_id/source_type=
testimony/chain_original_source из записи спикера) → `EpistemicStore` →
report-канал `EpistemicContextResolver` (по предикатам, порог 0.25) →
DecisionHub (talk/spread_rumor/warn → object_id).

Проверено производственными функциями (новый `test_universal_social_symmetry.py`):
- D: NPC₀ →(речь)→ NPC₃-свидетель →(его решение)→ NPC₄: у NPC₄
  original_source=NPC₀ (не ретранслятор) 🟢;
- E: NPC → NPC информация об игроке: вера об игроке, original_source=player,
  цепочка продолжается 🟢;
- слов игрока — особого веса нет (reliability не знает «игрок») 🟢;
- особого правила «слухи только NPC→NPC» нет (маршрут *→NPC→NPC→* общий) 🟢.

Маршрут Player→NPC→NPC (Ц) уже был доказан живым LLM-прогоном BUTTERFLY-01
(1a8dee8: Люся → Торнин, 28 вызовов production-пути).

## 8. Перечень исправленных Python-файлов

| Файл | Тип | Изменение R2 |
|---|---|---|
| `backend/app/services/economy/establishment.py` | НОВЫЙ | слой предприятия: сущности, права, операции хранилища/казны, сидирование, резолвер продажи |
| `backend/app/services/economy/work_orders.py` | МЕХАНИКА | единый settlement (хранилище предприятия/казна), снятие гейта с терминалов, `_sellers_for_good` (персонал первым), универсальная фабрика `create_order_direct`, фикс коллизии id |
| `backend/app/services/economy/player_purchase.py` | ПЕРЕПИСАН | торговая логика удалена; тонкий адаптер ввода намерения игрока → общий механизм |
| `backend/app/services/game_loop/turn_pipeline.py` | ПРОВОДКА | передача `scene_state` в адаптер (строка + комментарий) |
| `backend/app/services/scene_state/scene_factory.py` | ПРОВОДКА | сидирование предприятий на новых сценах (идемпотентно) |
| `backend/app/services/game_loop/scene_init.py` | ПРОВОДКА | самовосстановление предприятий на загруженных сейвах |
| `config/world/establishments.json` | ДАННЫЕ (новые) | авторские семена трактира (хранилище/стойка/персонал/казна) |

Не тронуты (проверено `git diff d78f0a4..HEAD --stat`): DM-агент, вербализация,
RelationshipStore/WriteGate, эпистемический контур BUTTERFLY-01 — работающая
причинная цепочка сохранена (butterfly-набор 51 passed).

## 9. Новые и обновлённые тесты

**Новые:** `backend/tests/gameplay/test_universal_trade.py` (A, B, F — 3 теста,
реальный game_loop, production-функции); `backend/tests/micro/
test_universal_social_symmetry.py` (D, E + S199-наблюдатель — 4 теста,
производственные мембрана/ревизия/резолвер).

**Обновлены под реально расширенные контракты (документировано):**
`test_f1_trade_materialization.py` — контракт «продажа трактирщика в таверне =
сделка предприятия» (сток хранилища, казна; личные сток/золото не движутся;
ресток-инъекция удалена как ненужная); `test_butterfly_player_purchase.py` —
fail-контракт общего settlement (`no_stock:<good>`), публикация честного отказа
каналом ACTIVITY_OUTCOME (как у NPC).

## 10. Регрессионные результаты

| Набор | До R2 | После R2 | Вывод |
|---|---|---|---|
| micro полный (−5 pre-broken файлов) | 852 passed / 10 failed | 846 passed / 4 failed* | 🟢 ноль новых |
| gameplay полный | — | 173 passed / 5 failed* | 🟢 ноль новых |
| butterfly+claim+trade набор | 51 passed | 51 passed | 🟢 цепочка цела |
| F1 trade materialization | 1 passed | 1 passed (контракт предприятия) | 🟢 |
| новые универсальность A–F | — | 7 passed | 🟢 |

*s368_route_integration ×4 и gc05×2/gc11×2/gc27×1 воспроизведены на чистом
baseline-worktree `d78f0a4` (`git worktree`): пред-существующие, к R2 не
относятся. F1 — единственный тест с контрактным обновлением; причина и новый
контракт задокументированы в §9.

Подтверждение реальными вызовами: покупка игрока у стойки (тест A) прошла через
фактические `create_order_direct`+`settle_order` с фиксацией `via_establishment`
и персистентностью через production-writer `save_scene_state`; покупка NPC
(тест B, чистый прогон) — через фактический тик-пайплайн (pressure→intent→
ORDER→SERVE→settle, логи `[WORK] ORDER born/SERVE onset/ORDER completed`).

## 11. Обновлённый BUTTERFLY-01_IMPLEMENTATION_GUIDE.md

Версия 2.0 (коммит `00efbd3`): §1.4 переписан под единый механизм; добавлена
Часть II (R2.0–R2.8): принцип общих механик, ответы аудита, слой предприятия,
единый путь заказа с точками входа и точными файлами, права, автономные
потребности, универсальная социальная передача, тесты A–F, матрица возможностей,
оставшиеся ограничения (🟢/⚠️/🔴/🧠 по каждому пункту). Желаемая архитектура
отдельно помечена от существующей: substrate-only W2, логическая передача
товара, отсутствие ресток-поведения — явные 🔴/🧠, не выданы за реализованное.

## 12. Коммиты и оставшиеся ограничения

```
00efbd3 BUTTERFLY-01-R2: implementation guide v2.0 — Part II universal mechanics
de0abe5 BUTTERFLY-01-R2: universal player/NPC mechanics — establishment layer + unified order execution + universality tests A-F
(основание: c38d7a0 ← 1a8dee8 ← b7f930f ← 6dff104 ← ce7c225 ← d78f0a4)
```

**Оставшиеся ограничения** (полная таблица с решениями — гайд, R2.8):
🧠 `bar` как WorldObject-архетип (W2/W3 — мини-ADR); 🧠 хранилище знаний игрока
(наблюдатель мембраны — да, EpistemicStore — нет); 🔴 физическая материализация
товара и пространственная привязка стойки (после W2/W3); 🔴 автономный ресток
и зарплатный контур казна→персонал; ⚠️ жажда без body-оси (needs-слой);
⚠️ UE-гейт при мёртвом LLM подавляет покупку в пайплайне (контракт S-UE;
с живым LLM путь доказан прогоном BUTTERFLY-01); ⚠️ campaign-keyed кэши между
лупами одного процесса (пред-существующий долг, проявляется в тестах).

**Главный архитектурный критерий (§11 R2):** новый NPC заказывает еду/эль через
существующие механизмы без нового файла — доказано (Боро и Орм, тесты B/F);
новое хранилище получает возможности через общие свойства (операции
establishment-слоя предметно-независимы); игрок участвует в той же системе
формирования знаний (S199 + тесты D/E); действие NPC ⟹ эквивалентная
возможность игрока и наоборот — один settlement, разные адаптеры намерения 🟢.
