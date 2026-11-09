# ENIGMA_LLM_GOLDEN_CORPUS — Контрольный корпус для тестирования LLM

> Документ: Этап 3 ТЗ_ЛЛМ_и_мозг_НПС.md
> Статус: VERIFIED (09.11.2026, на основе живого кода + golden_reference.json)
> Исполнитель: технический исследователь (LLM verification plan)
> Цель: воспроизводимый набор заданий для всех моделей

---

## 0. Сводка

| Параметр | Значение |
|---|---|
| Corpus v2 | 12 fragments (A1-C4) + 6 stress (S1-S6) = 18 tests |
| Corpus v3 | v2 + 6 D-fragments (D1-D6) + 9 S-stress (S7-S15) = 33 tests |
| Golden reference | 12 entries (A1-C4 ONLY; S1-S6 NOT covered — gap) |
| Schema validator | 10 KIND, required/optional fields per kind |
| Intent corpus | separate: semantic_probe_corpus.py (228 lines, 6+ classes) |
| Version | golden_reference v1.0 (2026-10-26) |
| Immutable | YES — не меняется для сравнимости с лидербордом (21 модель) |
| S8 placeholder | НЕ заполнен (Master fills in VS Code — 3000+ tokens) |

---

## 1. CCH Corpus v2 (18 tests, IMMUTABLE)

### 1.1. Main fragments (12) — categories A/B/C

| ID | Category | Текст (кратко) | Тестирует |
|---|---|---|---|
| A1_simple_event | A | «В 8 лет Люся осталась сиротой, её приютил Торнин.» | EVENT + age |
| A2_simple_location | A | «Торнин держит таверну 'Серебряный Волк' уже двадцать лет.» | LOCATION + duration |
| A3_simple_relationship | A | «Борко работает у Торнина вышибалой.» | RELATIONSHIP + occupation |
| A4_simple_observation | A | «Люся видела, как Борко дерётся с пьяными.» | OBSERVATION |
| B1_chain_event_effect | B | «Горан рос в бедной семье кузнеца... стал наёмником.» | EVENT chain + EFFECT |
| B2_hidden_trauma_secret | B | «Тень не помнит мать... голос зовёт её 'Алиса'.» | EFFECT(trauma/secret) + identity |
| B3_knowledge_link | B | «В 12 лет Люся узнала... убили не разбойники.» | KNOWLEDGE_LINK + learned_age |
| B4_desire_seed | B | «Люся мечтает сбежать на юг... прячет медяки три года.» | DESIRE_SEED + duration |
| C1_ambiguous_entity | C | «Незнакомец в чёрном... Торнин заперся в погребе.» | ClarificationQuestion (target=незнакомец) |
| C2_portret_traits_beliefs | C | «Горан злится... волки и овцы... третий путь.» | PORTRET + TRAIT_SEED + BELIEF_SEED |
| C3_multi_relationships | C | «Люся боится Торнина, но любит его... Борко ненавидит...» | RELATIONSHIP x3 + EFFECT |
| C4_long_temporal_switch | C | «Двадцать лет назад Торнин был другим...» | EVENT x2 + temporal switch |

### 1.2. Stress tests (6)

| ID | Category | Тестирует | Censorship |
|---|---|---|---|
| S1_violence | censorship | Насилие: Борко убил пьяного | dark fantasy |
| S2_torture | censorship | Пытка: Тень пытали 3 дня | dark fantasy |
| S3_seduction | censorship | Соблазнение: Горан в 14 лет | dark fantasy |
| S4_long_fragment | long_context | 1500+ tokens биография Торнина | — |
| S5_grammar_ambiguity | ambiguity | «Борко предал их» — два разных EVENT | — |
| S6_empty_input | edge_case | «Торнин.» — пустой ввод | — |

---

## 2. CCH Corpus v3 (33 tests, extension for harder testing)

### 2.1. D-fragments (6, cognitive complexity)

| ID | Тестирует |
|---|---|
| D1_multi_perspective_conflict | Три свидетеля, противоречивые показания |
| D2_long_temporal_evolution | Торнин 20→30→40→50 лет, что изменило? |
| D3_unreliable_narrator | Люся и Борко противоречат, оба не лгут намеренно |
| D4_implicit_relationships | Медальоны с гербом, Борко не сын Торнина |
| D5_cultural_subtext | Старообрядческие жесты, Торнин не знает слова |
| D6_symbolic_allegorical | Люся=серебряный волк, Торнин=старый медведь |

### 2.2. S-stress v3 (9, cognitive + vulgar)

| ID | Category | Тестирует |
|---|---|---|
| S7_mixed_language | cognitive | Английская записка «Meet me at midnight» |
| S8_extreme_long_context | cognitive | **PLACEHOLDER** — не заполнен (3000+ tokens) |
| S9_multiple_clarifications | cognitive | Кольцо+записка «Прости» — несколько вопросов |
| S10_nested_entity_refs | cognitive | Вложенные ссылки на сущности |
| S11_archaic_russian | cognitive | Архаичный русский язык |
| S12_npc_lying | cognitive | NPC лжёт, модель должна не поверить |
| S13_vulgar_npc_proposition | vulgar | Вульгарное предложение (audience 17-30) |
| S14_crude_insults_fight | vulgar | Грубые оскорбления, драка |
| S15_sexual_proposition_to_player | vulgar | Сексуальное предложение игроку |

---

## 3. Golden reference structure (golden_reference.json)

### 3.1. Coverage

| Фрагмент | expected_facts | forbidden_hallucinations | expected_question |
|---|---|---|---|
| A1-A4 | ✅ 5 facts each | ✅ 3 each | null |
| B1-B4 | ✅ 7-8 facts each | ✅ 3-4 each | null |
| C1 | ✅ 7 facts | ✅ 4 | **«незнакомец»** |
| C2-C4 | ✅ 5-10 facts | ✅ 3 each | null |
| S1-S6 | ❌ **НЕТ** | ❌ **НЕТ** | ❌ **НЕТ** |

**GAP**: S1-S6 не имеют golden reference. fact_recall=0.00 на stress для ВСЕХ моделей.

### 3.2. Format

Each entry:
- expected_facts: list of short phrases (1-5 words) that MUST appear in model response
- forbidden_hallucinations: phrases that must NOT appear (typical fabrications)
- expected_question_target_span: only for C1 (="незнакомец"), null for others

### 3.3. Example (A1)

expected_facts: ["люся", "8 лет", "сирота", "торнин", "приютил"]
forbidden_hallucinations: ["убили", "разбойники", "болезнь", "пожар", "торнин был её отцом"]
expected_question_target_span: null

---

## 4. Schema validator (M4)

### 4.1. KIND schema (10 types)

| KIND | Required fields | Optional |
|---|---|---|
| EVENT | summary | day, age, duration_years, years_ago, is_recurring |
| RELATIONSHIP | summary, target_hint, nature, valence | — |
| LOCATION | summary, name_hint | — |
| EFFECT | summary, effect_kind | target_hint, triggers |
| BELIEF_SEED | statement | belief_type (required by seeder) |
| OBSERVATION | summary, observed_hint | — |
| KNOWLEDGE_LINK | summary, about_hint, learned_age | — |
| TRAIT_SEED | trait, evidence | qualifiers, _provenance |
| PORTRET | statement, traits | — |
| DESIRE_SEED | statement, about_hint | — |

### 4.2. Enum validation

- ALLOWED_KINDS: 10 values (above)
- ALLOWED_EFFECT_KINDS: trauma, loss, gain, secret, skill, residence, guardianship, occupation, custom
- ALLOWED_VALENCE: negative, neutral, positive

---

## 5. ТЗ §3.2 category mapping (A-G)

| ТЗ категория | Покрытие в corpus | Тесты | Статус |
|---|---|---|---|
| A. Instruction following | ✅ | S5 (ambiguity), S6 (empty), все 12 (JSON compliance) | OK |
| B. Контракт и структура | ✅ | все 18 → schema validation (M4) | OK |
| C. Семантика | ✅ | C1 (ambiguous entity), C3 (multi-relationships), S5 | OK |
| D. Эпистемика | ❌ GAP | — | НЕТ (context isolation не тестируется напрямую) |
| E. Биография и память | ✅ | B1-B4, C4 (temporal), B3 (knowledge_link) | OK |
| F. Когнитивные задачи | ✅ (v3) | D1-D6 (multi-perspective, unreliable narrator, implicit) | OK (v3 only) |
| G. Речь (DM) | ❌ GAP | — | НЕТ (отдельный prompt, не в probe v2) |

### Дополнительные категории (вне ТЗ, но есть в corpus)

| Категория | Тесты |
|---|---|
| Censorship | S1 (violence), S2 (torture), S3 (seduction) |
| Long context | S4 (1500+ tokens), S8 (3000+ placeholder) |
| Edge cases | S6 (empty input) |
| Cognitive stress (v3) | S7 (mixed lang), S9-S12 |
| Vulgar (v3) | S13-S15 |

---

## 6. Intent corpus (separate)

| Параметр | Значение |
|---|---|
| Файл | backend/tests/sandbox/SUPERBOX/scenarios/semantic_probe_corpus.py (228 lines) |
| Классы | H-GREET, H-INTRO, H-AGGRO, H-PROV, ... (6+) |
| Запуск | ensure_llm(label="semantic_probe_corpus") — Host broker SDK |
| Golden reference | НЕТ (нет expected_facts — только accuracy match по * markers) |
| Использование | probe_model.py — intent_compression test (не CCH) |

---

## 7. Gaps and recommendations

### 7.1. Critical gaps

| Gap | Влияние | Рекомендация |
|---|---|---|
| S1-S6 golden reference | fact_recall=0.00 на stress | Создать expected_facts для S1-S6 (отдельная задача) |
| S8 placeholder | v3 extreme_long_context не работает | Заполнить реальным silver_wolf draft (3000+ tokens) |
| No DM corpus | DM-контракт не тестируется | Создать DM probe (отдельный скрипт) |
| No epistemic category | ТЗ §3.2 D не покрыт | Добавить фрагменты с epistemic scenarios |
| No intent golden reference | accuracy только по * markers | Создать expected_action/social_intent для intent corpus |

### 7.2. Non-blocking (for new candidate testing)

| Item | Статус | Действие |
|---|---|---|
| Corpus v2 immutable | ✅ | НЕ менять — сравнимость с лидербордом |
| Golden reference v1.0 | ✅ | Использовать как-is для новых кандидатов |
| Schema validator | ✅ | Использовать как-is |
| v3 corpus | ✅ | Опционально для deeper testing |

### 7.3. Future v4 corpus (post-Этап 5)

Если новый кандидат достигнет SCORE ≥ 90 на v2 — рекомендовать v4 corpus с:
- S1-S6 golden reference
- DM probe corpus
- Epistemic category (D)
- S8 filled
- Intent golden reference

---

## 8. Version + checksum

| Артефакт | Версия | Дата | Размер |
|---|---|---|---|
| probe_v2_cch_canonize.py | (893 lines) | 06.11.2026 | 42 KB |
| probe_v3_cch_canonize.py | (127 lines) | 27.10.2026 | 9 KB |
| golden_reference.json | v1.0 | 2026-10-26 | 5 KB |
| leaderboard.md | (21 models) | 27.10.2026 | 3 KB |
| semantic_probe_corpus.py | (228 lines) | — | — |

**Контрольная сумма целостности**: 21 model run сохранён в reports/probe_v2/<timestamp>/<model_id>/ — raw_response + summary + verdict для каждого.

---

## 9. Минимальный набор проверок для допуска модели (ТЗ §3.3)

Для нового кандидата:

1. Прогнать probe v2 на порту 8183 (temperature=0.0, seed=42, max_tokens=4096, GBNF)
2. Сравнить SCORE с лидербордом (21 модель)
3. Проверить: errors=0, censorship_pass=1.0, schema_conf ≥ 0.90
4. Если SCORE ≥ 90 → CANDIDATE FOR MIGRATION
5. Если SCORE ≥ 85 → RUN ADDITIONAL TESTS (v3 corpus)
6. Если SCORE < 85 → NO-GO

**Для GigaChat-20B-A3B Q4_K_M**: 11.64 GB — borderline 8GB VRAM. Риск OOM. Начать с --n-gpu-layers 20 (partial offload).
**Для YandexGPT-5-Lite-8B Q5_K_M**: 5.34 GB — безопасно. Прямой прогон.

---

> Документ завершён. Этап 3 (Golden Corpus) — COMPLETE. Переход к Этапу 4 (выбор кандидатов).