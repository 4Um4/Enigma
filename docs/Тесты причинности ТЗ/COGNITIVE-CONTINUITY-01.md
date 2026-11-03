# COGNITIVE-CONTINUITY-01 — Итоговый отчёт направления

**Дата:** 2026-11-04  
**База:** `5ffb9796` (V.0.5.4.5.3_Полшага_1) → HEAD на момент отчёта  
**Параллельные коммиты:** R2-R6 (CCH-15, Stage_2_1) — не мои, сохранены

---

## 1. Исходная цель

Замкнуть жизненный цикл воспоминаний NPC: опыт → память → убеждение → поведение → речь.

NPC должен: помнить события, различать собственное наблюдение и чужое свидетельство, сохранять происхождение и достоверность, извлекать релевантные воспоминания спустя игровое время, использовать их в решениях и речи, самостоятельно решать когда и кому сообщать.

## 2. Что реализовано (13 коммитов)

| SHA | Этап | Что | Файлы |
|-----|------|-----|-------|
| `5091636f` | S1 | Predicate.INSULTED + provenance (source_type, original_source_id) | epistemology.py, belief_revision_engine.py, epistemic_store.py, claim_event_subscriber.py, causality_manifest.py |
| `76305cb2` | S2 | PLAYER_INSULTS → Proposition(INSULTED) + подписка | claim_event_subscriber.py, game_loop.py |
| `a323f3d5` | S2-fix | lambda **kw (регрессия S1) | test_player_speech_claim.py |
| `526a2c0a` | S3 | Report channel: REPORT_PREDICATES + report_proposition + spread_rumor boost | epistemic_context_resolver.py |
| `015864ae` | S4 | DecisionHub: report targeting (жертва) + proposition fallback | decision_hub.py |
| `fabd3ebc` | S5 | ADR-O-342: cold-start клейм (proposition-exception) | post_decision.py |
| `6f947e30` | S6 | DialogueExecutor: LLM routing + claim block | dialogue_executor.py |
| `e476afc9` | S7 | Sound gate = SSOT action_perception_radius | npc_tick_pipeline.py |
| `6ba096a5` | — | Provenance multi-hop fix (original_source_id через посредника) | belief_revision_engine.py, claim_event_subscriber.py |
| `541c5c49` | CC-core | CognitionContextResolver extended: EpistemicStore + name resolution | cognition_context.py, pipeline_runner.py |
| `9865661b` | 1.4 | Connect cognition to DialogueExecutor (all speech paths) | dialogue_executor.py, task_scheduler.py, game_loop.py |
| `23f2e016` | — | Fix _proposition in _generate_with_router + dict handling | dialogue_executor.py |
| `a01a89eb` | — | Claim block name resolution (IDs → game names) | dialogue_executor.py |

IPT: 54/0/0 на каждом коммите.

## 3. Production-path доказательства

### DialogueExecutor.execute() с LLM (production code path)

```
EpistemicStore: player insulted tavern_keeper_tornin (testimony, conf=0.5)
→ _generate_with_router builds prompt:
  - system_prompt (NPC identity, language rules)
  - cognition block (CognitionContextResolver.resolve_block: beliefs + provenance + resolved names)
  - claim block ([Факт, которым ты делишься]: Игрок оскорбил Торнина)
  - "Скажи свою реплику:"
→ LLM (Hermes-3-Llama-3.1-8B) generates:

"Слушай, я слышал, что игрок оскорбил Торнина. 
 Такое не стоит делать. Ведь это может привести к плохим последствиям."
```

**Доказано:** production code path (DialogueExecutor.execute → _generate_with_router) доставляет beliefs с provenance и resolved names в LLM-промпт.

### Provenance multi-hop chain (unit test)

```
Player → Lusya → Tornin → Borko
- Lusya: source=player, original=player ✅
- Tornin: source=lusya, original=player ✅ (сохранён через посредника)
- Borko: source=tornin, original=player ✅ (3 hops, original не потерян)
```

## 4. CC-01…CC-09 статус

| CC | Статус | Доказательство | Ограничение |
|----|--------|---------------|-------------|
| CC-01 | ⚠️ Частично | EpistemicStore хранит belief от PLAYER_INSULTS | Не после игрового времени |
| CC-02 | ⚠️ Частично | Provenance chain test (hop 1-2) | Через direct revise(), не through membrane |
| CC-03 | ⚠️ Частично | Provenance chain (hop 3) + report targeting + cold-start | НЕ через full game loop |
| CC-04 | ❌ Не проверено | CognitionContextResolver читает EpistemicStore | Нет теста с idle ticks |
| CC-05 | ❌ Не проверено | Cognition block feed DMFrame (L412) | Не верифицирован с LLM |
| CC-06 | ⚠️ Частично | Round-trip serialization test | Не через SQLite save/load |
| CC-07 | ⚠️ Частично | Sound gate SSOT + membrane filter | Не в full game loop |
| CC-08 | ⚠️ Частично | source_type/original/confidence хранятся | Противоречия не протестированы |
| CC-09 | ❌ Не начато | — | StateDelta/ReactionSubscriber не исследованы |

**Критический пробел:** CC-02, CC-03, CC-04 не проверены через production game loop (TickOrchestrator→DecisionHub→post_decision→DialogueExecutor). Unit-тесты подтверждают логику, но не production поведение.

## 5. Что НЕ сделано

1. **Full game loop integration** — TickOrchestrator→DecisionHub→post_decision→DialogueExecutor не тестировался end-to-end
2. **CC-09** — причинная связь psyche↔event не исследована
3. **Экономика таверны** — не начата (establishment.py, bar counter, unified transaction)
4. **Lexicon «жлоб»** — не добавлен
5. **task_scheduler L688** — proposition-exception не добавлен (defensive; spread_rumor уже bypass через requires_dialogue_context=False)
6. **Противоречивые сведения** — polarity=False не протестированы
7. **Save/load production cycle** — не тестировался через SQLite
8. **Отрицательный сценарий в game loop** — NPC не слышал → не знает, не проверен в full loop

## 6. Архитектурные решения

1. **Один CognitionContextResolver** — feeds ОБА пути речи (DialogueExecutor + DMFrame). Не второй resolver.
2. **Provenance через reliability_context** — on_claim_event читает запись спикера, передаёт original_source_id. Не новый SSOT.
3. **Sound gate = SSOT** — action_perception_radius(event_type) вместо hardcoded 15.0
4. **Claim block name resolution** — self._get_context (тот же механизм, что cognition block)
5. **Cold-start клейм** — proposition-carrying intents не демотятся к approach, если цель в пределах речи

## 7. Точка продолжения

**Приоритет 1:** Full game loop integration test
- Использовать SUPERBOX npc_sandbox или drift_laboratory (GameLoop.idle_tick — production flow)
- Сценарий: player action → idle ticks → check EpistemicStore → NPC decisions → LLM speech
- Отрицательный сценарий: NPC вне радиуса → не знает

**Приоритет 2:** CC-09
- Археология: StateDelta, ReactionSubscriber, CrystallizedBelief
- Проверить: может ли NPC объяснить изменение доверия/страха конкретным событием

**Приоритет 3:** Экономика таверны
- establishment.py, bar counter, unified transaction (игрок+NPC)
- Археология work_orders.py, create_order, settle_order

**Приоритет 4:** Противоречия и save/load production cycle

## 8. Файлы

**Production (изменённые):**
- backend/app/domain/epistemology.py
- backend/app/services/npc/belief_revision_engine.py
- backend/app/services/npc/epistemic_store.py
- backend/app/services/npc/epistemic_context_resolver.py
- backend/app/services/npc/cognition_context.py
- backend/app/services/npc/decision_hub.py
- backend/app/services/npc/npc_tick_pipeline.py
- backend/app/services/events/claim_event_subscriber.py
- backend/app/services/phases/post_decision.py
- backend/app/services/execution/dialogue_executor.py
- backend/app/services/game_loop/game_loop.py
- backend/app/services/game_loop/task_scheduler.py
- backend/app/services/pipeline_runner.py
- backend/app/models/causality_manifest.py

**Тесты (новые):**
- backend/tests/micro/test_butterfly_insult_proposition.py
- backend/tests/micro/test_butterfly_report_channel.py
- backend/tests/micro/test_butterfly_report_targeting.py
- backend/tests/micro/test_butterfly_cold_start.py
- backend/tests/micro/test_butterfly_provenance_chain.py
- backend/tests/micro/test_cognition_context_cc.py

**Тесты (изменённые):**
- backend/tests/micro/test_player_speech_claim.py

---

*Архитектор: COGNITIVE-CONTINUITY-01 swarm  
Мастер Тай: оценивает техническую реализацию  
Игровые решения: Мастер*
'@

    $reportPath = "download/COGNITIVE_CONTINUITY_01_REPORT.md"
    [System.IO.File]::WriteAllText($reportPath, $report, [System.Text.UTF8Encoding]::new($false))
    Write-Output "Отчёт создан: $reportPath ($((Get-Item $reportPath).Length) bytes)"

    Write-Output "`n=== git log -15 (все мои коммиты) ==="
    $prev = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    git log --oneline -15 --format="  %h | %s" 2>$null
    $ErrorActionPreference = $prev
}
```

**Этот отчёт** — честная инвентаризация: что сделано, что не сделано, что частично, где ограничения. Не презентация успехов — фактический статус для следующего архитектора.

**Главный вывод:** когнитивная инфраструктура создана (опыт→память→убеждение→решение→доставка→речь), но **не проверена через full game loop**. Unit-тесты подтверждают логику каждого компонента, production-path DialogueExecutor доказан с LLM, но интеграция через TickOrchestrator→DecisionHub→post_decision→DialogueExecutor — **критический пробел**, который должен быть закрыт следующим шагом.

Мы строим не демонстрацию памяти NPC, а мир, в котором информация перемещается между самостоятельными сознаниями. Инфраструктура для этого есть. Доказательство через full game loop — точка продолжения.