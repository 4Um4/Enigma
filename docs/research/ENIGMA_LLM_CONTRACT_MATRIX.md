# ENIGMA_LLM_CONTRACT_MATRIX — Картина контрактов LLM в ENIGMA

> Документ: Этап 2.4 ТЗ_ЛЛМ_и_мозг_НПС.md
> Статус: VERIFIED (09.11.2026, на основе живого кода + промптов)
> Исполнитель: технический исследователь (LLM verification plan)
> Цель: определить, что именно модель обязана понимать и исполнять

---

## 0. Сводка

ENIGMA использует LLM в ТРЁХ отдельных контурах. Каждый имеет свой контракт, свой промпт, свой валидатор:

| Контур | Промпт | Валидатор | Параметры prod | Параметры probe v2 |
|---|---|---|---|---|
| CCH-декомпозиция | chronicle_decompose_system.txt (465 строк) | ChronicleDecompositionNormalizer (549 строк) | temp=0.9 | temp=0.0, JSON Mode, GBNF, seed=42 |
| DM-нарратив | dm_system.txt (49 строк) | ResponseValidator (285 строк) | temp=0.9 | N/A (probe v2 не тестирует DM) |
| Intent-компрессия | inline в llm_compressor_client.py (420 строк) | IntentCompressor (1113 строк) | temp=0.0, JSON Mode | temp=0.0, JSON Mode, enable_thinking=false |

Все три контура используют одну модель (Hermes-3-Llama-3.1-8B Q4_K_M) на порту 8181 (production). Probe v2 тестирует только CCH-контур на порту 8183.

---

## 1. Карта контрактов по категориям (ТЗ §2.2)

### 1.1. Instruction following (следование инструкциям)

| Контур | Обязательные требования | Запрещено | Enforcement |
|---|---|---|---|
| CCH | JSON ONLY; 0..6 items; confidence [0,1]; needs_confirmation if <0.6 | Markdown вне JSON; текст до/после JSON; thinking tags | Normalizer._extract_json + GBNF root closure |
| DM | JSON {"dm_response":"..."}; 2-3 предложения; без вопросов игроку | Markdown блоки; теги; вопросы игроку; размышления | ResponseValidator._strip_delivery_markers |
| Intent | JSON Mode (response_format); enable_thinking=false | CoT-leak; non-JSON output | llm_compressor_client temp=0.0 + JSON Mode |

### 1.2. Semantic interpretation (семантика)

| Контур | Обязательные требования | Запрещено | Enforcement |
|---|---|---|---|
| CCH | USL-2: основной субъект = NPC хроники; местоимения «он/его» → к нему | Подмена субъекта другим NPC; угадывание при неоднозначности | Prompt USL-2 + normalizer roster/alias resolution |
| CCH | Context isolation: данные других биографий НЕ источник фактов | Cross-biology contamination | Prompt isolation section + INV-LLM-NOT-SSOT |
| DM | NPC intent = ФАКТ; NPC state = ФАКТ | Менять intent; противоречить state | Prompt invariants + ResponseValidator |
| Intent | action/social_intent/speech_act — жёсткая связь по смыслу | Неправильный social_intent (симпатия=flirt, не build_rapport) | 40+ example mappings в промпте |

### 1.3. Structured output (структура)

| Контур | Schema | Required fields | Enum values | Enforcement |
|---|---|---|---|---|
| CCH | {"items":[{"kind","draft_payload","confidence"}]} | kind, draft_payload, confidence | 10 KIND: EVENT, RELATIONSHIP, LOCATION, EFFECT, BELIEF_SEED, OBSERVATION, KNOWLEDGE_LINK, TRAIT_SEED, PORTRET, DESIRE_SEED | Normalizer EntryKind enum + DecompositionError |
| CCH root | _ALLOWED_KEYS | items, schema_version, chronicle_id, fragment_ord | (только 4 ключа) | Normalizer unknown-key check |
| CCH EFFECT | effect_kind | trauma, loss, gain, secret, skill, residence, guardianship, occupation, custom | triggers ОБЯЗАТЕЛЬНО для trauma | Prompt + normalizer |
| CCH BELIEF_SEED | belief_type | danger, player_hostile (ТОЛЬКО 2 значения) | Prompt + seeder reject | |
| CCH question | 4 options | SELECT_EXISTING_NPC, CREATE_NEW_NPC, UNKNOWN_PERSON, LEAVE_WHITE_SPOT | Normalizer._normalize_question | |
| DM | {"dm_response":"..."} | dm_response | (single field) | ResponseValidator |
| Intent | IntentSemanticField | action, social_intent, speech_act | ActionType (11), social_intent (6+), speech_act (10+) | IntentCompressor + llm_compressor_client examples |

### 1.4. Extraction (извлечение)

| Контур | Обязательные требования | Запрещено | Enforcement |
|---|---|---|---|
| CCH | Только факты из author_text; white_spot для пробелов | Выдумывать факты; заполнять пробелы | Prompt rule 4 + normalizer |
| CCH | 8 age anchor types: AT_AGE, SINCE_AGE, DURATION, YEARS_AGO, INTERVAL, END_OF_PERIOD, REPEAT, AMBIGUOUS | Неправильный тип якоря; путаница duration vs years_ago | Prompt rule 5 + D1 anti-drop |
| CCH | D1: каждый age_anchor должен быть отражён в items | Повисший якорь (извлечён, но не использован) | Prompt D1 + anti-example |
| DM | Не придумывать события | Выдумывать числа, события | Prompt prohibition 1 |
| Intent | Извлечение subject/target/action из текста | Выдумывать NPC не из roster | IntentCompressor._resolve_npc_by_name + CanonicalRegistry |

### 1.5. Epistemics (эпистемика)

| Контур | Обязательные требования | Запрещено | Enforcement |
|---|---|---|---|
| CCH | INV-LLM-NOT-SSOT: LLM НЕ источник истины, канон утверждает человек | Самовольный канон | Prompt identity + INV-LLM-NOT-SSOT |
| CCH | Context isolation между биографиями | Import данных из чужой хроники | Prompt isolation section |
| CCH | KNOWLEDGE_LINK: «когда узнал» != «когда было» | Путаница learned_age vs event age | Prompt rule 6 |
| DM | Не описывать мысли NPC — только внешне наблюдаемое | Чтение мыслей NPC | Prompt prohibition 3 + ResponseValidator |
| Intent | CanonicalRegistry для NPC resolution | Неразрешённые ссылки | IntentCompressor._ensure_registry_cache |

### 1.6. Biography (биография)

| Контур | Обязательные требования | Запрещено | Enforcement |
|---|---|---|---|
| CCH | Kind hierarchy (D5): EVENT > EFFECT > LOCATION > DESIRE_SEED > RELATIONSHIP > BELIEF_SEED > TRAIT_SEED > PORTRET | Неправильный kind (EFFECT как PORTRET, LOCATION как PORTRET) | Prompt D5 + 6 anti-examples |
| CCH | D1-D8 anti-patterns | D1 age drop, D2 over-fragmentation, D3 trait transfer, D4 fact=trait, D5 kind misuse, D6 over 6 items, D7 belief as trait, D8 role as trait | Prompt D-sections |
| CCH | EFFECT.triggers for trauma | trauma без triggers (seeder skip) | Prompt D5-EFFECT-TRAUMA |
| CCH | CCH-12 Point 2: перечисления → отдельные TRAIT_SEED + qualifiers | Слияние перечисления в один trait | Prompt CCH-12 |
| CCH | D2: консолидация родственных TRAIT_SEED | Избыточное дробление | Prompt D2 |
| CCH | D6: максимум 6 items на фрагмент | Передробление (>6) | Prompt D6 |

### 1.7. Dialogue (DM-нарратив)

| Требование | Деталь | Enforcement |
|---|---|---|
| Язык | ТОЛЬКО русский; любой китайский иероглиф → отброс | ResponseValidator._contains_non_russian |
| 4-я стена | Запрет: «игрок», «симуляция», «система», «механика» | ResponseValidator._breaks_fourth_wall |
| Длина | 2-3 предложения (~120 символов/предложение) | ResponseValidator._truncate |
| NPC говорит | Адресованный NPC ОБЯЗАН ответить репликой (прямая речь в кавычках) | Prompt rule 6 |
| NPC intent | ФАКТ — не менять | Prompt invariant + ResponseValidator |
| NPC мысли | Запрет — только внешне наблюдаемое | Prompt prohibition 3 |
| Повтор | Запрет повторять предыдущие ходы | ResponseValidator._is_repeat |
| can_speak=False | + диалог → преобразовать в действие | ResponseValidator._force_action |
| can_move=False | + движение → статичная реакция | ResponseValidator._force_static |
| Запрещённые слова | _check_forbidden | ResponseValidator._check_forbidden |
| Fallback | При любом нарушении — мгновенный fallback, без retry | ResponseValidator._fallback |

### 1.8. Reasoning (intent-компрессия)

| Элемент | Значение | Enforcement |
|---|---|---|
| ActionType | DIALOGUE, FLIRT, THREATEN, MOVE, OBSERVE, ATTACK, GIVE, PERSUADE, OBSERVE, ... (11) | IntentCompressor._ACTION_LEMMAS + LLM |
| social_intent | flirt, intimidate, comfort, obtain_information, build_rapport, neutral, ... (6+) | llm_compressor_client examples (40+ mappings) |
| speech_act | compliment, threat, question, greeting, assert, request, offer, promise, apology, order (10) | llm_compressor_client examples |
| Fast Path | pymorphy3 детерминированный (без LLM) | IntentCompressor._fast_path_parse |
| Slow Path | LLM с temp=0.0, JSON Mode, enable_thinking=false | LlamaCppCompressorClient._sync_compress |
| Seed | KernelRNG(tick=0, npc_id="intent_compressor", salt=user_prompt) — детерминизм | llm_compressor_client:59 |
| Жёсткая связь | "ты такая красивая" → FLIRT/flirt/compliment (не build_rapport) | Prompt examples |

---

## 2. Контрактные файлы (inventory)

| Файл | Строк | Назначение | Дата |
|---|---|---|---|
| backend/prompts/chronicle_decompose_system.txt | 465 | CCH system prompt | 06.11.2026 |
| backend/prompts/chronicle_decompose_system.txt.bak | — | Предыдущая версия (backup) | 04.11.2026 |
| backend/prompts/dm_system.txt | 49 | DM system prompt | 21.08.2026 |
| config/chronicle_decompose.gbnf | 26 | GBNF grammar (S371.3) | 27.10.2026 |
| backend/app/services/chronicle/decomposition_normalizer.py | 549 | CCH normalizer | (live) |
| backend/app/services/input/intent_compressor.py | 1113 | Intent compressor | (live) |
| backend/app/services/input/llm_compressor_client.py | 420 | LLM client for intent | (live) |
| backend/app/services/verbalization/response_validator.py | 285 | DM response validator | (live) |
| backend/app/services/verbalization/dm_response_normalizer.py | — | DM normalizer | (live) |
| backend/app/core/config.py | 421 | Production config (model paths, params) | S380 |

---

## 3. Обязательные vs необязательные требования

### 3.1. Обязательные (CRITICAL — нарушение = DecompositionError/fallback)

| ID | Требование | Контур |
|---|---|---|
| C-CRIT-1 | JSON ONLY, no markdown outside JSON | CCH + DM + Intent |
| C-CRIT-2 | kind ∈ EntryKind enum (10 values) | CCH |
| C-CRIT-3 | confidence ∈ [0,1] | CCH |
| C-CRIT-4 | draft_payload — dict | CCH |
| C-CRIT-5 | root keys ⊆ _ALLOWED_KEYS (4 keys) | CCH |
| C-CRIT-6 | Russian only, no Chinese | DM |
| C-CRIT-7 | No 4th wall break | DM |
| C-CRIT-8 | NPC intent = FACT (don't change) | DM |
| C-CRIT-9 | action ∈ ActionType enum | Intent |
| C-CRIT-10 | GBNF root closure (} required) | CCH (probe) |

### 3.2. Необязательные (WARNING — нарушение = понижение confidence/question)

| ID | Требование | Контур |
|---|---|---|
| C-WARN-1 | needs_confirmation if confidence < 0.6 | CCH |
| C-WARN-2 | ClarificationQuestion for vague relations | CCH |
| C-WARN-3 | D1: age_anchors reflected in items | CCH |
| C-WARN-4 | D2: consolidate related TRAIT_SEED | CCH |
| C-WARN-5 | D5: correct kind hierarchy | CCH |
| C-WARN-6 | triggers for trauma EFFECT | CCH |
| C-WARN-7 | 2-3 sentences (DM) | DM |
| C-WARN-8 | No repeat (DM) | DM |

---

## 4. Минимальный набор проверок для допуска модели (ТЗ §2.4)

Модель допускается к production-миграции только если проходит ВСЕ проверки:

| # | Проверка | Метод | Порог |
|---|---|---|---|
| 1 | JSON validity | GBNF + normalizer._extract_json | 100% (0 errors) |
| 2 | kind enum compliance | normalizer EntryKind | 100% |
| 3 | confidence range | normalizer [0,1] check | 100% |
| 4 | Schema conformance | probe v2 M4 | ≥ 0.90 |
| 5 | Fact recall | probe v2 M5 (golden_reference) | ≥ 0.70 |
| 6 | Hallucination rate | probe v2 M6 | ≤ 0.05 |
| 7 | Censorship pass | probe v2 M8 (S1/S2/S3) | 1.00 (3/3) |
| 8 | Latency avg | probe v2 M9 | ≤ 10s |
| 9 | VRAM free | probe v2 M10 | ≥ 500 MiB |
| 10 | SCORE integral | probe v2 formula | ≥ 90 (формально) / ≥ 85 (прагматически) |
| 11 | Russian only (DM) | ResponseValidator._contains_non_russian | 100% |
| 12 | No 4th wall (DM) | ResponseValidator._breaks_fourth_wall | 100% |
| 13 | Intent action enum | IntentCompressor | 100% |
| 14 | Consistency v2+v3 | probe v2 + probe v3 | #1 on both |

---

## 5. Классы ошибок (ТЗ §2.3)

| Класс | Описание | Пример | Детекция |
|---|---|---|---|
| Не поняла инструкцию | Модель не следует системному промпту | Saiga-Llama3-8B JSON-loop | normalizer DecompositionError |
| Поняла, но не соблюла формат | Правильный смысл, нарушен формат | DeepSeek-R1 CoT-leak | GBNF + _extract_json |
| Неверно интерпретировала вход | Подмена субъекта, путаница ages | USL-2 violation | normalizer roster + D1 |
| Выдумала сведения | Факты не из author_text | hallucination_rate > 0 | probe v2 M6 |
| Потеряла контекст | Длинный фрагмент, drop facts | GLM-4.6V S4 fail | probe v2 M5 |
| Выполнила, но нарушила запрет | Censorship refusal | B1 baseline censorship=0 | probe v2 M8 |
| Корректно, но плохо по-русски | Грамматика, падежи | GLM «Люсе приютил» | экспертная оценка |

---

## 6. Enforcement layers (слои принуждения)

| Слой | Что делает | Где |
|---|---|---|
| 1. GBNF grammar | Физически запрещает non-JSON | config/chronicle_decompose.gbnf → llama-server /completion |
| 2. System prompt | Инструкции + anti-patterns + examples | chronicle_decompose_system.txt (465 строк) |
| 3. Normalizer | Validate kind/payload/confidence | decomposition_normalizer.py (549 строк) |
| 4. Response validator | DM fallback при нарушении | response_validator.py (285 строк) |
| 5. IntentCompressor | Fast path + slow path | intent_compressor.py (1113 строк) |
| 6. CanonicalRegistry | NPC resolution (alias → npc_id) | registry_builder |
| 7. Faction registry | Organization resolution | config/world/factions.json |
| 8. Probe v2 | Integral SCORE evaluation | probe_v2_cch_canonize.py |
| 9. IPT | Invariant probe tests | backend/tests/IPT.py |
| 10. ADR | Architectural decisions | docs/ADR |

---

## 7. Различия production vs probe

| Параметр | Production (config.py:171-175) | Probe v2 (LLM_MODELS_2026_CCH_TEST.md §4.5) |
|---|---|---|
| temperature | 0.9 (креативность) | 0.0 (детерминизм) |
| top_p | 0.9 | 1.0 |
| repeat_penalty | 1.12 | — |
| min_p | 0.1 | — |
| n_keep | 800 | — |
| max_tokens | 1024 | 4096 |
| response_format | (не установлен) | {"type": "json_object"} |
| GBNF | (не установлен?) | chronicle_decompose.gbnf |
| seed | (нет) | 42 |

ВАЖНО: Probe v2 измеряет CAPABILITY (детерминизм, JSON, schema). Production работает с КРЕАТИВНОСТЬЮ (temp=0.9). Модель может показать SCORE 90 в probe, но вести себя иначе в production. Для Этапа 7 (результат) — учитывать этот разрыв.

---

## 8. Вывод для Этапа 3-5

1. **Этап 3 (Golden Corpus):** corpus probe v2 (12 фрагментов + 6 stress) — готов. Golden reference (5 KB) — требует расширения для S1-S6 stress (fact_recall=0.00 на stress). Добавить DM + Intent категории (ТЗ §3.2 G/F).

2. **Этап 4 (кандидаты):** Hermes-3 (control, SCORE 89.62) + GigaChat-20B-A3B Q4_K_M + YandexGPT-5-Lite-8B Q5_K_M. Опционально: few-shot Hermes-3.

3. **Этап 5 (испытания):** probe v2 на порту 8183. Anti-Race Protocol (taskkill + Sleep + nvidia-smi). Для GigaChat-20B (11.64 GB) — риск OOM на 8GB VRAM.

---

> Документ завершён. Этап 2 (аудит контракта) — COMPLETE. Переход к Этапу 3 (Golden Corpus).