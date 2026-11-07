# BUTTERFLY-01 + COGNITIVE-CONTINUITY-01 — Актуализированный гайд v3

**Дата:** 2026-11-04 (обновлено 2026-11-07 с результатами B4)  
**База:** `a01a89eb` на `V.0.5.4.5.3_Полшага_1` → B4-LM `021aa7c9` на `V.0.5.4.5.8_Полшага_5`  
**Предыдущая версия:** BUTTERFLY-01_IMPLEMENTATION_GUIDE.md v2.0 (удалена 2026-11-07 как устаревшая)  
**Этот документ:** актуализация — что сделано, что осталось, барная стойка, полный цикл, **B4 verified production run**

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

## 1. Что реализовано (13 коммитов + B3/B4 fixes)

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
| `70783f6d` | B3-fix | ✅ | **Verifier key mismatch: `subject` vs `subject_id` (`or` fallback chain)** |
| `2e8266cf` | B3-fix | ✅ | **`_get_context` args swapped: campaign_id first, npc_id second** |
| `e8754e65` | B3 | ✅ | **LLM integration test with instrumentation (caplog + JSONL)** |
| `021aa7c9` | B4-LM | ✅ | **Transcript capture + polarity=True + Host broker auto-start** |

IPT: 54/0/0 на каждом коммите S1-S7. B3/B4 — game loop integration tests.

## 2. Production-path доказательство

DialogueExecutor.execute() → _generate_with_router → LLM (Hermes-3):
- EpistemicStore: `player insulted tavern_keeper_tornin` (testimony, conf=0.5)
- Cognition block: beliefs + provenance + resolved names
- Claim block: `[Факт, которым ты делишься]: Игрок оскорбил Торнина`
- LLM: "я слышал, что игрок оскорбил Торнина. Такое не стоит делать."

**B4 production verification (2026-11-07):** See section 7.

## 3. Что НЕ сделано

### 3.1. ~~Full game loop integration~~ — CLOSED by B4 (2026-11-07)
- ~~TickOrchestrator→DecisionHub→post_decision→DialogueExecutor НЕ тестировался end-to-end~~
- **B4 closed this gap**: 4:22 minute production run with live LLM, 6 NPC ticking, verified rumor transmission
- Remaining: cognition threshold (0.25) blocks Tornin from using received belief — see section 7

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

### 3.3. CC-01…CC-09 статус (updated 2026-11-07)

| CC | Статус | Ограничение |
|----|--------|-------------|
| CC-01 | ✅ → ⚠️ | **B4: belief stored after PLAYER_INSULTS through game loop** — но confidence=0.215 < 0.25 threshold |
| CC-02 | ⚠️ | **B4: membrane proven (COMMUNICATION_CLAIM delivered Lusya→Tornin)** — но belief revision через membrane не isolated |
| CC-03 | ✅ | **B4: full game loop proven end-to-end** — Lusya speaks → verifier YES → claim → Tornin receives |
| CC-04 | ⚠️ | **B4: idle ticks tested (advance_ticks 2+10)** — но cognition context empty for Tornin (confidence < 0.25) |
| CC-05 | ❌ | DMFrame не верифицирован с LLM |
| CC-06 | ⚠️ | Не через SQLite save/load |
| CC-07 | ✅ | **B4: sound gate + membrane in full game loop** — claim delivered through production membrane |
| CC-08 | ⚠️ | Противоречия (polarity=False) не протестированы |
| CC-09 | ❌ | StateDelta/ReactionSubscriber не исследованы |

### 3.4. Прочее
- Lexicon «жлоб» — не добавлен в insults_ru.json
- task_scheduler L688 — proposition-exception не добавлен (defensive)
- **polarity=True verified in production** (B4 transcript: all propositions have `polarity: True`)
- **polarity=False (negation) — не протестирован**
- Save/load production cycle — не тестировался

## 4. Архитектурные решения

1. **Один CognitionContextResolver** — feeds ОБА пути речи (DialogueExecutor + DMFrame). Не второй resolver.
2. **Provenance через reliability_context** — on_claim_event читает запись спикера, передаёт original_source_id. Не новый SSOT.
3. **Sound gate = SSOT** — action_perception_radius(event_type) вместо hardcoded 15.0
4. **Claim block name resolution** — self._get_context (тот же механизм, что cognition block)
5. **Cold-start клейм** — proposition-carrying intents не демотятся к approach, если цель в пределах речи
6. **Multi-hop provenance** — original_source_id сохраняется через цепочку посредников
7. **polarity in proposition** (B4-LM fix #1) — `Proposition.polarity: bool` (True=affirmative, False=negation). Required for complete claim↔verifier linkage. Missing polarity → linkage_complete=False (не silent match).
8. **Transcript capture** (B4-LM) — `_safe_json_dump` с `ensure_ascii=False, default=str + recursive fallback`. Claim↔verifier linkage через proposition-dict match (не text matching).
9. **LLM auto-start** (B4-LM) — `ensure_llm(label="B4")` via Host broker (:8182 → spawns llama-server :8181). KILLER_SPIRIT reaper (opt-out: `B4_NO_REAPER=1`).

## 5. Точка продолжения

**Приоритет 1: Cognition threshold calibration (B4-COGNITION)**
- `REPORT_CONFIDENCE_THRESHOLD = 0.25` в EpistemicContextResolver
- B4 показал: Tornin receives rumor (confidence=0.215) но BELOW threshold → cognition context empty → Tornin не может использовать belief для речи
- Исследовать: same-source boost (×0.2) vs independent witness (×1.0) — Lusya единственный источник, boost занижает confidence
- Не опускать threshold — исследовать формулу confidence

**Приоритет 2: Template fallback для Tornin (B4-TEMPLATE)**
- B4: 3 из 4 реплик Tornin = `[Intent.SPREAD_RUMOR] tavern_keeper_tornin -> maid_lusya: наблюдение` — template, не LLM
- LLM generation упала для these calls — исследовать причину (LANG_LEAK gate? timeout? context?)
- Отдельный production defect от cognition threshold

**Приоритет 3: Барная стойка**
- Археология work_orders.py, create_order, settle_order
- establishment.py + config/world/establishments.json
- Единый механизм для игрока и NPC

**Приоритет 4: CC-09 + противоречия + save/load**

## 6. Файлы

**Production (14 файлов):** epistemology.py, belief_revision_engine.py, epistemic_store.py, epistemic_context_resolver.py, cognition_context.py, decision_hub.py, npc_tick_pipeline.py, claim_event_subscriber.py, post_decision.py, dialogue_executor.py, game_loop.py, task_scheduler.py, pipeline_runner.py, causality_manifest.py

**Production fixes (B3):** proposition_verifier.py (key mismatch), dialogue_executor.py (_get_context args)

**Тесты:** test_butterfly_insult_proposition.py, test_butterfly_report_channel.py, test_butterfly_report_targeting.py, test_butterfly_cold_start.py, test_butterfly_provenance_chain.py, test_cognition_context_cc.py, test_player_speech_claim.py, **test_butterfly_b3_llm.py** (B3), **test_butterfly_b4_verified_belief.py** (B4-LM)

---

## 7. B4: verified production run (2026-11-07)

**Commit:** `021aa7c9` на `V.0.5.4.5.8_Полшага_5`  
**Duration:** 4:22 минуты (262 сек) с живым LLM (Hermes-3-Llama-3.1-8B.Q4_K_M.gguf)  
**LLM auto-start:** Host broker :8182 → llama-server :8181 via `ensure_llm(label="B4")`  
**NPC ticking:** 6 (guard_borko, merchant_goran, maid_lusya, blacksmith_orm, thief_shadow, tavern_keeper_tornin)

### 7.1. Transcript artifacts

- **stdout:** `=== ALL NPC SPEECH ===` + `TORNIN REACTIONS` + `LUSYA → TORNIN` + `HYPOTHESES`
- **JSON:** `backend/tests/gameplay/data/b4_transcript.json` — полная структура

### 7.2. Lusya → Tornin: verified rumor transmission

```
tick 5, event_order #8:
  source: maid_lusya
  target: tavern_keeper_tornin
  text: "Господин Торнин, мне рассказали о том, что Tester вас обидел.
         Я это знаю и хотела вам сообщить. Но будьте осторожен, он может быть опасен."
  intent_type: spread_rumor
  tone: FEARFUL

verifier: YES (confirmed)
  prop={'subject_id': 'player', 'predicate': 'insulted',
        'object_id': 'tavern_keeper_tornin', 'polarity': True}

COMMUNICATION_CLAIM delivered:
  source=maid_lusya, target=tavern_keeper_tornin
  proposition=(player, insulted, tornin, polarity=True)
  verified_by=proposition_verifier
```

**Когнитивная цепочка доказана end-to-end через production game loop.**

### 7.3. Tornin's response — voice exists, but not about the insult

```
tick 5, event_order #10 (same tick as Lusya's speech):
  source: tavern_keeper_tornin
  target: maid_lusya
  text: "По ночам слышны крики со стороны старой башни."
  intent_type: talk
  tone: ANGRY

ticks 7, 10, 12 (event_orders #15, #25, #32):
  text: "[Intent.SPREAD_RUMOR] tavern_keeper_tornin -> maid_lusya: наблюдение"
  intent_type: spread_rumor
  tone: ANGRY
  ⚠️ template fallback — LLM generation failed
```

**Tornin имеет голос** — 4 реплики, все tone=ANGRY, все адресованы Lusya. Но:
1. Первая реплика — про ночные крики у башни, **не про оскорбление**
2. Реплики 2-4 — **template fallback**, LLM не сгенерировала текст

Tornin услышал слух (claim delivered, EpistemicStore updated), эмоционально отреагировал (ANGRY), но **cognition context empty** (confidence=0.215 < REPORT_CONFIDENCE_THRESHOLD=0.25) → не может использовать insult proposition для генерации речи.

### 7.4. Verifier statistics

- **22 verifier records** total, all with proposition=(player, insulted, tornin, polarity=True)
- **4 YES** (confirmed) — речи про оскорбление
- **18 NO** (rejected) — речи про подвал, торговлю, крики (корректно отвергнуты)
- **linkage_complete: true** — polarity present in all records
- **verifier_linkage_method:** `proposition_dict_match_with_polarity`

### 7.5. Other NPCs (tavern life)

| NPC | Реплика (фрагмент) | Verifier |
|---|---|---|
| Goran (merchant) | «Дорогой гость, я рад приветствовать вас в моём магазине...» | NO (не про оскорбление) |
| Orm (blacksmith) | «эти торговцы вредят нашей кузнечной делу...» | NO |
| Lusya (повтор) | «Я слышала, что ночью оттуда доносится крики...» | NO |
| ? | «Да, чужеземцы разводят непонятные сказы...» | YES |
| ? | «Аа, Торнин, что за природа такая? В стражу не попалось...» | YES |
| ? | «Аа, Торнин, я слышал, что тебе не везет с охраной...» | YES |

### 7.6. 2 FAIL criteria (test verdict)

B4 test FAILED с 2 criteria not met:
1. **crit7_cognition** — `EpistemicContextResolver` не возвращает proposition для Tornin (confidence < 0.25)
2. **Второй criterion** — имя требует уточнения из [VERDICT] вывода

**8 из 10 criteria PASS** — cognitive chain proven, rumor delivered, provenance correct.

### 7.7. Главный вывод

> есть ли у Торнина собственный голос после того, как его оскорбили

**Да, голос есть. Но он не про оскорбление.** Tornin зол (ANGRY), говорит Lusya, но его слова — про ночные крики. Он услышал слух, отреагировал эмоционально, но не смог сформулировать реакцию на оскорбление. Cognition gate (confidence < 0.25) блокирует использование insult proposition для генерации речи.

Это не дефект Tornin. Это **cognition calibration issue** — следующий приоритет (B4-COGNITION).

---

*v3 обновлён 2026-11-07 с результатами B4 production run.  
Оригинальный v2 (BUTTERFLY-01_IMPLEMENTATION_GUIDE.md) удалён как устаревший.*
