# BUTTERFLY-01 + COGNITIVE-CONTINUITY-01 — Актуализированный гайд v3

**Дата:** 2026-11-04  
**База:** `a01a89eb` на `V.0.5.4.5.3_Полшага_1`  
**Предыдущая версия:** BUTTERFLY-01_IMPLEMENTATION_GUIDE.md v2.0 (73KB)  
**Этот документ:** актуализация — что сделано, что осталось, барная стойка, полный цикл

---

## 0. Полный жизненный цикл

```
Игрок оскорбляет Торнина (опыт)
  → PLAYER_INSULTS event (восприятие)
    → ClaimEventSubscriber → EpistemicRecord(INSULTED) с provenance (память)
      → EpistemicContextResolver → report_proposition (убеждение)
        → to_modifiers → spread_rumor boost (поведение)
          → DecisionHub → target=жертва, proposition fallback (решение)
            → post_decision → cold-start клейм delivery (доставка)
              → DialogueExecutor → cognition block + claim block → LLM (речь)
                → NPC_SPOKE → ClaimEventSubscriber → новый EpistemicRecord у слушателя
                  → цикл повторяется для следующего NPC
```

**Барная стойка** (отдельное направление, не начато):
```
Посетитель (игрок/NPC) заказывает → барная стойка (объект обслуживания)
  → хранилище предприятия (запасы) → списание → выдача товара
    → оплата → казна предприятия → единый механизм для игрока и NPC
```

## 1. Что реализовано (13 коммитов)

| SHA | Этап | Статус | Что |
|-----|------|--------|-----|
| `5091636f` | S1 | ✅ | Predicate.INSULTED + provenance (source_type, original_source_id) |
| `76305cb2` | S2 | ✅ | PLAYER_INSULTS → Proposition(INSULTED) + подписка |
| `a323f3d5` | S2-fix | ✅ | lambda **kw (регрессия) |
| `526a2c0a` | S3 | ✅ | Report channel: REPORT_PREDICATES + report_proposition |
| `015864ae` | S4 | ✅ | DecisionHub: report targeting (жертва) + proposition fallback |
| `fabd3ebc` | S5 | ✅ | ADR-O-342: cold-start клейм (proposition-exception) |
| `6f947e30` | S6 | ✅ | DialogueExecutor: LLM routing + claim block |
| `e476afc9` | S7 | ✅ | Sound gate = SSOT action_perception_radius |
| `6ba096a5` | — | ✅ | Provenance multi-hop fix (original_source_id через посредника) |
| `541c5c49` | CC-core | ✅ | CognitionContextResolver: EpistemicStore + name resolution |
| `9865661b` | 1.4 | ✅ | Connect cognition to DialogueExecutor (все пути речи) |
| `23f2e016` | — | ✅ | Fix _proposition in _generate_with_router + dict handling |
| `a01a89eb` | — | ✅ | Claim block name resolution (IDs → game names) |

IPT: 54/0/0 на каждом коммите.

## 2. Production-path доказательство

DialogueExecutor.execute() → _generate_with_router → LLM (Hermes-3):
- EpistemicStore: `player insulted tavern_keeper_tornin` (testimony, conf=0.5)
- Cognition block: beliefs + provenance + resolved names
- Claim block: `[Факт, которым ты делишься]: Игрок оскорбил Торнина`
- LLM: "я слышал, что игрок оскорбил Торнина. Такое не стоит делать."

## 3. Что НЕ сделано

### 3.1. Full game loop integration (критический пробел)
- TickOrchestrator→DecisionHub→post_decision→DialogueExecutor НЕ тестировался end-to-end
- Unit-тесты подтверждают логику, но не production поведение
- Нужно: SUPERBOX harness или test с GameLoop.run_turn + idle_tick

### 3.2. Барная стойка и экономика таверны (не начато)

**Игровая модель (от Мастера):**
- Таверна — предприятие с владельцем и персоналом
- Барная стойка — объект обслуживания, через который посетители заказывают и получают товары
- У стойки есть запасы (или связанное хранилище)
- Внутренняя сторона стойки и запасы доступны персоналу по ролям
- Посетители (игрок и NPC) могут делать заказы
- NPC самостоятельно инициируют заказы исходя из потребностей
- Игрок и NPC используют один механизм заказа, оплаты, списания, выдачи
- Все изменения проходят через существующий Transaction SSOT
- Смена владельца не уничтожает стойку, запасы и услуги

**Археология (existing):**
- `work_orders.py` — create_order_direct, settle_order, fail_order (предсуществует)
- `rules_subscriber.py` — имитация покупки (−5G без товара) — заменить
- `EconomicProfile` — gold, goods, stock_for_sale
- `GOODS_PRICES` — SSOT-цены

**Что создать:**
- `establishment.py` — слой предприятия: владелец, treasury, storage, service_points, staff
- `config/world/establishments.json` — семена таверны
- Player path: тонкий адаптер (не отдельная экономика) → общий create_order → settle_order
- NPC path: NEED→DESIRE→TRADE → create_order_from_trade_intent → SERVE → settle_order
- Барная стойка = service_point с storage_id, served_goods, revenue_to

**Не создавать:**
- player_purchase.py как самостоятельную экономику
- Отдельные логики для игрока и NPC
- Поставщиков, производство, закупки (пока)

### 3.3. CC-01…CC-09 статус

| CC | Статус | Ограничение |
|----|--------|-------------|
| CC-01 | ⚠️ | Не после игрового времени |
| CC-02 | ⚠️ | Через direct revise(), не through membrane |
| CC-03 | ⚠️ | НЕ через full game loop |
| CC-04 | ❌ | Нет теста с idle ticks |
| CC-05 | ❌ | DMFrame не верифицирован с LLM |
| CC-06 | ⚠️ | Не через SQLite save/load |
| CC-07 | ⚠️ | Не в full game loop |
| CC-08 | ⚠️ | Противоречия не протестированы |
| CC-09 | ❌ | StateDelta/ReactionSubscriber не исследованы |

### 3.4. Прочее
- Lexicon «жлоб» — не добавлен в insults_ru.json
- task_scheduler L688 — proposition-exception не добавлен (defensive)
- Противоречивые сведения (polarity=False) — не протестированы
- Save/load production cycle — не тестировался

## 4. Архитектурные решения

1. **Один CognitionContextResolver** — feeds ОБА пути речи (DialogueExecutor + DMFrame). Не второй resolver.
2. **Provenance через reliability_context** — on_claim_event читает запись спикера, передаёт original_source_id. Не новый SSOT.
3. **Sound gate = SSOT** — action_perception_radius(event_type) вместо hardcoded 15.0
4. **Claim block name resolution** — self._get_context (тот же механизм, что cognition block)
5. **Cold-start клейм** — proposition-carrying intents не демотятся к approach, если цель в пределах речи
6. **Multi-hop provenance** — original_source_id сохраняется через цепочку посредников

## 5. Точка продолжения

**Приоритет 1: Full game loop integration**
- Использовать SUPERBOX npc_sandbox или drift_laboratory (GameLoop.idle_tick)
- Сценарий: player action → idle ticks → EpistemicStore → NPC decisions → LLM speech
- Отрицательный: NPC вне радиуса → не знает

**Приоритет 2: Барная стойка**
- Археология work_orders.py, create_order, settle_order
- establishment.py + config/world/establishments.json
- Единый механизм для игрока и NPC
- Барная стойка = service_point

**Приоритет 3: CC-09**
- Археология StateDelta, ReactionSubscriber, CrystallizedBelief
- Проверить: NPC может объяснить изменение доверия/страха

**Приоритет 4: Противоречия и save/load**

## 6. Файлы

**Production (14 файлов):** epistemology.py, belief_revision_engine.py, epistemic_store.py, epistemic_context_resolver.py, cognition_context.py, decision_hub.py, npc_tick_pipeline.py, claim_event_subscriber.py, post_decision.py, dialogue_executor.py, game_loop.py, task_scheduler.py, pipeline_runner.py, causality_manifest.py

**Тесты (6 новых + 1 изменённый):** test_butterfly_insult_proposition.py, test_butterfly_report_channel.py, test_butterfly_report_targeting.py, test_butterfly_cold_start.py, test_butterfly_provenance_chain.py, test_cognition_context_cc.py, test_player_speech_claim.py

---

*Этот документ актуализирует BUTTERFLY-01_IMPLEMENTATION_GUIDE.md v2.0.  
Оригинальный гайд сохраняет историческую ценность (детальные Этапы 1-10).  
Этот документ — фактический статус и план продолжения.*
'@

    $guidePath = "docs/Тесты причинности ТЗ/BUTTERFLY-01_GUIDE_UPDATE_v3.md"
    [System.IO.File]::WriteAllText($guidePath, $guide, [System.Text.UTF8Encoding]::new($false))
    Write-Output "Гайд v3 создан: $guidePath ($((Get-Item $guidePath).Length) bytes)"

    Write-Output "`n=== Проверка COGNITIVE-CONTINUITY-01.md ==="
    Write-Output "  Отчёт корректен — это мой фактический отчёт направления"
    Write-Output "  13 коммитов, CC-01…CC-09 честный статус, точка продолжения"

    Write-Output "`n=== Все файлы в docs/Тесты причинности ТЗ/ ==="
    Get-ChildItem "docs/Тесты причинности ТЗ" | ForEach-Object { Write-Output "  $($_.Name) ($($_.Length) bytes)" }
}
```
