# ТЗ для следующей сессии — Lumimaid non-determinism + multi-run methodology

> Updated: 2026-11-14 v4
> PREV: v3 (2026-11-10) — Lumimaid migration + benchmark
> CURRENT SESSION: S424 (ветвь Б, 2026-11-13/14)

---

## Контекст для преемника

### Кто я и что сделал

S424, ветвь Б. Закрывал ТЗ-v3 priorities 1-3. Сделал SSOT-замыкание benchmark промптов к production-файлам, wired GBNF grammar в benchmark adapter, создал fewshot-файл, добавил checks в ResponseValidator. 2 коммита: `ad706efb` (S424), `a0de49ea` (S424-2).

### Главная находка сессии — benchmark НЕ воспроизводим

**Контролируемый эксперимент:** ssot_v1 vs ssot_v1_repeat — ОДИНАКОВАЯ конфигурация (no grammar, no fewshot, тот же benchmark, тот же сервер Lumimaid :8181, temperature=0.0, seed=42).

| Метрика | ssot_v1 (1st run) | ssot_v1_repeat (2nd run) | Δ |
|---|---|---|---|
| DLG | 0.2656 | 0.6562 | +0.39 |
| GATE_JSON | false (9 invalid) | true (0 invalid) | FLIP |
| criticals | 11 | 2 | -9 |
| composite | 20.45 | 57.46 | +37 |
| SOC | 0.825 | 0.700 | -0.125 |
| ID | 0.6389 | 0.4167 | -0.22 |

**Те же 9 DM-задач**, которые в 1-м прогоне дали plain text (json_invalid), во 2-м дали валидный JSON — БЕЗ любого изменения кода. Lumimaid генерит то `{`, то plain text — **первый токен non-deterministic**, несмотря на temperature=0.0 и seed=42.

### Что это значит

1. **Все single-run сравнения в этой сессии — частично noise.** Я сравнивал ssot_v1 (criticals=11) vs ssot_v2_grammar (criticals=2) и атрибутировал grammar. Но ssot_v1_repeat показывает criticals=2 БЕЗ grammar. Часть "улучшения" — noise.

2. **Grammar — единственный детерминированный рычаг.** Без grammar JSON-output — coin flip. С grammar — гарантированно 0 invalid на каждом прогоне. Grammar убирает variance, не добавляет.

3. **SOC "regression" был noise.** SOC использует SYSTEM_ANALYST (не CCH). Fewshot не влияет на SOC. Вариация 0.825→0.4875→0.7 — Lumimaid non-determinism.

4. **Модель NOT READY.** Non-determinism — фундаментальная проблема. NPC то отвечает в JSON, то plain text; то соблюдает dossier, то ломает character — на одинаковых входах.

---

## Что ЧИТАТЬ преемнику (обязательно, в порядке)

### 1. Архитектура и режим работы

| Файл | Что | Зачем |
|---|---|---|
| `РЕЖИМ РАБОТЫ.md` | META CODE ARCHITECT protocol | Пошаговая работа, БЫЛО/СТАЛО формат, Anti-Race §11, Окно тишины §3.12 |
| `Правила Фикса БАГОВ.md` | Bug fix protocol | Археология §3.6, Runtime Data Archaeology §VIII.5, тестовый инструментарий |
| `docs/ЗАВЕЩАНИЕ_АРХИТЕКТОРОВ.md` | 17 писем от предыдущих агентов | Уроки, предупреждения, незадокументированное. Читать ВСЕ письма — каждое содержит формулу |

### 2. Археология проекта

| Файл | Что |
|---|---|
| `docs/ARCHITECTURE_FLOW_GENERATED.md` | Топология проекта (генерируется из architecture/*.yaml через build_graph.py) |
| `docs/ENIGMA_ROADMAP_v4_12_WPS.md` | Roadmap (единственный файл маски ENIGMA_ROADMAP*.md) |
| `docs/MUTATIONS.md` | Журнал сессий. **Моя запись: S424 (lines ~624-690)**. Читать полностью (не Select-Object -Last!) |
| `docs/ADR (Architecture Decision Records).md` | ADR-атлас |

### 3. Ключевые файлы моей сессии

| Что | Путь | Что changed |
|---|---|---|
| Benchmark | `backend/tests/LLM Benchmark/ENIGMA_LLM_COMPREHENSIVE_BENCHMARK.py` | SYSTEM_CCH/DM → read_text (SSOT); GBNF_CCH/DM wired в _params_for + adapter |
| probe_v2 | `backend/tests/LLM Benchmark/probe_v2_cch_canonize.py` | --system-prompt-file; run_test signature; _prompt_path logic |
| Fewshot file | `backend/prompts/chronicle_decompose_system_fewshot.txt` | 4 BIO examples (FS-1..FS-4) |
| ResponseValidator | `backend/app/services/verbalization/response_validator.py` | question_to_player + player_action_result checks (ACTIVE); addressee check (AVAILABLE, not wired) |
| DM prompt | `backend/prompts/dm_system.txt` | Production DM prompt (SSOT с benchmark) |
| CCH prompt | `backend/prompts/chronicle_decompose_system.txt` | Production CCH prompt (465 строк, SSOT с benchmark) |

### 4. Benchmark reports (мои прогоны)

| Файл | Конфигурация | composite | BIO | CMP |
|---|---|---|---|---|
| `reports/benchmark_lumimaid_ssot_v1.json` | no grammar, no fewshot (1st run) | 20.45 | 0.6627 | 0.375 |
| `reports/benchmark_lumimaid_fewshot_v1.json` | no grammar, fewshot | 12.76 | 0.8116 | 0.375 |
| `reports/benchmark_lumimaid_ssot_v2_grammar.json` | grammar, no fewshot | 62.15 | 0.7544 | 0.4875 |
| `reports/benchmark_lumimaid_fewshot_v2_grammar.json` | grammar + fewshot | 61.08 | 0.8116 | 0.4625 |
| `reports/benchmark_lumimaid_ssot_v1_repeat.json` | **SAME as ssot_v1, 2nd run** | 57.46 | 0.6865 | 0.3625 |

**Ключевой файл для изучения:** `benchmark_lumimaid_ssot_v1_repeat.json` — доказательство non-determinism. Сравни с `benchmark_lumimaid_ssot_v1.json` — та же конфигурация, разные результаты.

---

## Задачи следующей сессии

### ПРИОРИТЕТ 0 — Multi-run methodology (BLOCKING)

**Проблема:** Single-run benchmark замеры не воспроизводимы. Lumimaid non-deterministic на уровне первого токена (JSON vs plain text — coin flip).

**Задача:** Внедрить multi-run averaging в benchmark.

**Шаги:**
1. Добавить `--runs N` аргумент в `ENIGMA_LLM_COMPREHENSIVE_BENCHMARK.py` (N=3 минимум)
2. Прогонять каждую конфигурацию N раз, усреднять module scores + criticals
3. Выводить mean ± stddev для каждого модуля
4. Сравнивать конфигурации только по averaged scores (не single-run)

**Контракт:** если stddev по BIO > 0.05 между прогонами одной конфигурации — результат не валиден, нужен больше прогонов.

**Файл:** `backend/tests/LLM Benchmark/ENIGMA_LLM_COMPREHENSIVE_BENCHMARK.py` (main() + run_benchmark())

### ПРИОРИТЕТ 1 — Оценить реальный effect grammar vs noise

**Проблема:** В моей сессии grammar дал GATE_JSON: true (0 invalid) в обоих прогонах. Но без grammar — 1st run: 9 invalid, 2nd run: 0 invalid. Grammar убирает variance — но какой РЕАЛЬНЫЙ effect поверх noise?

**Задача:** Multi-run A/B тест (3+ прогона каждой):
- Config A: no grammar (production prompt)
- Config B: grammar (production prompt)
- Сравнить averaged scores + stddev

**Ожидание:** grammar даёт детерминированный GATE_JSON: true, но остальные метрики (BIO, SOC, DLG) могут быть в рамках noise. Если так — grammar единственный стабильный рычаг, остальное noise.

### ПРИОРИТЕТ 2 — Deterministic inference setup

**Проблема:** Lumimaid non-deterministic даже при temp=0.0, seed=42. Причина — GPU parallelism (batch processing, KV cache state, thermal throttling).

**Задача:** Исследовать deterministic inference options:
1. `--batch-size 1` в llama-server (no parallel token processing)
2. `--cont-batching` disabled (no context reuse between requests)
3. CPU fallback для воспроизводимости (медленно, но детерминированно)
4. `--no-mmap` (avoid memory-mapped file non-determinism)

**Файл:** llama-server spawn config (через `ensure_llm` / Host broker). Изучить `architecture/LLM_RUNTIME_UNIFICATION_PROPOSAL.md` §6-8.

**Контракт:** если batch-size=1 даёт воспроизводимость (3 прогона → stddev < 0.02) — это production config. Если нет — модель фундаментально non-deterministic, нужен Qwen3.5-9B migration.

### ПРИОРИТЕТ 3 — ResponseValidator addressee wiring (TZ-v3 priority 3 continuation)

**Проблема:** Я добавил `addressee` parameter в `ResponseValidator.validate()` и `_addressee_present()` метод. Но НЕ wired в production — `dm_agent.py` не передаёт addressee.

**Причина:** `context.get("player_target_id")` возвращает NPC ID (например "tavern_keeper_ustin"), не display name ("Устин"). Передача ID → false positive (ID не в text → wrong_addressee fallback на каждый валидный ответ).

**Задача:** Wire addressee через ID→name resolution.

**Археология:**
1. `backend/app/agents/dm_agent.py` lines 254-265 — уже есть `_target_name` resolution (DMFrame → _npc_id_to_display → fallback). Изучить как `_target_name` разрешается.
2. Сохранить `self._last_target_name = _target_name` в `_build_contract` (после resolution)
3. В `narrate()` передать `addressee=self._last_target_name` в `validator.validate()`

**Файл:** `backend/app/agents/dm_agent.py` (narrate + _build_contract), `backend/app/services/verbalization/response_validator.py`

### ПРИОРИТЕТ 4 — Model migration evaluation (если non-determinism не решается)

**Проблема:** Lumimaid-v0.2-8B non-deterministic на фундаментальном уровне. Если priority 2 (deterministic inference) не помогает — модель нужно менять.

**Задача:** Оценить Qwen3.5-9B (или альтернативы) на:
1. Воспроизводимость (multi-run stddev)
2. BIO/CMP/SOC scores (с grammar)
3. VRAM fit (RTX 3070 Ti 8GB — Qwen3.5-9B Q4 ~5.5GB, должно поместиться)
4. Latency (приемлемо для real-time gameplay?)

**Файл:** `Models LLM/` (новый .gguf), `backend/app/core/config.py` (model path), `backend/app/services/llm/` (provider)

**Контракт:** migration только если (a) воспроизводимость лучше Lumimaid И (b) BIO+CMP+SOC ≥ Lumimaid averaged scores.

---

## Что НЕ делать

1. **Не объявлять модель READY** на single-run замерах. Multi-run averaging обязателен.
2. **Не сравнивать конфигурации по single-run.** Только averaged scores с stddev.
3. **Не trust своим изменениям без controlled re-run.** Моя сессия показала: то что кажется "улучшением" может быть noise.
4. **Не amend коммиты.** (РЕЖИМ §11, прецедент S318). Терминальный коммит по pathspec: `git commit -F <tempfile> -- <files>`.
5. **Не трогай foreign WIP.** Parallel sessions активны (S425 A-branch). `git status --short` перед каждым коммитом, pathspec только свои файлы.

---

## Anti-Race предупреждения

- **Parallel sessions:** S425 (A-branch, A3 INFRA) упал между моими S424 и S424-2. Branch `V.0.5.4.6.4_ЛЛМ_4` содержит interleaved commits двух сессий. Master разводит при merge.
- **Session ID:** max в MUTATIONS = S425 (parallel). Твоя сессия = S426 (перепроверить перед записью: `Select-String -Path docs/MUTATIONS.md -Pattern "^## S"`)
- **IPT baseline:** 55/0/0 на момент закрытия S424 (foreign INV-FLAG-REGISTRY BC2_ENABLED был fixed parallel session между запусками)
- **`scripts/doc_patch_s424.py` и `scripts/doc_patch_s425.py`** — untracked, НЕ мои. Не трогать.

---

## Формулы наследуются

«Builder is what is built» (S340). «Молчаливое принятие — ложь с процентами» (S349). «Дошла ли цифра до того, кто решает?» (S350). «Исходные байты — единственная правда» (S354). «Старт не притворяется» (S358). «Replay не обязан удалять» (S360). «Готовность НЕ равна масс-флип» (S362). «Гипотеза без археологии — вежливая ложь» (S373). «Unit-тест зелёный ≠ сервер работает» (S379).

**Добавляю свои:**

- **О non-determinism:** single-run benchmark замер — не измерение, а лотерея. Если модель non-deterministic при temp=0.0 — ты измеряешь noise, не signal. Multi-run averaging — единственный способ получить signal.
- **О grammar vs noise:** grammar не "улучшает" JSON-output — он его детерминирует. Без grammar модель может выдать JSON случайно. С grammar — всегда. Разница между "случайно валидный" и "гарантированно валидный" — это разница между "иногда работает" и "надёжно".
- **О trade-off иллюзии:** если metric A выросла а B упала на single-run — не делай вывод о trade-off. Сначала проверь: это trade-off или noise? Controlled re-run (та же конфигурация, другой прогон) — единственный тест.
- **О SSOT-замыкании:** benchmark и production должны читать один файл промпта. Если benchmark использует inline дистиллят (27 строк) а production — полный файл (465 строк) — ты тестируешь не production, а свою карикатуру на него.

---

## Ключевые файлы (полная карта)

| Что | Путь |
|---|---|
| Production model | `Models LLM/Lumimaid-v0.2-8B-Q4_K_M-imat.gguf` |
| Config | `backend/app/core/config.py` (ctx_size=16384) |
| Benchmark | `backend/tests/LLM Benchmark/ENIGMA_LLM_COMPREHENSIVE_BENCHMARK.py` |
| Benchmark reports | `reports/benchmark_lumimaid_*.json` (5 файлов) |
| CCH probe | `backend/tests/LLM Benchmark/probe_v2_cch_canonize.py` |
| GBNF DM | `config/dm_response.gbnf` |
| GBNF CCH | `config/chronicle_decompose.gbnf` |
| CCH prompt (production) | `backend/prompts/chronicle_decompose_system.txt` |
| CCH prompt (fewshot, experiment) | `backend/prompts/chronicle_decompose_system_fewshot.txt` |
| DM prompt (production) | `backend/prompts/dm_system.txt` |
| ResponseValidator | `backend/app/services/verbalization/response_validator.py` |
| DM agent | `backend/app/agents/dm_agent.py` (narrate() line 810, validate() call line 896) |
| LLM Runtime | `docs/architecture/LLM_RUNTIME_UNIFICATION_PROPOSAL.md` |
| Предыдущее ТЗ | `docs/Почти Актуальные TZ/ТЗ_NEXT_SESSION_LLM.md` (v3) |
| Это ТЗ | `docs/Почти Актуальные TZ/ТЗ_NEXT_SESSION_LLM_v4.md` |

---

> Преемник. Я оставляю тебе не победу, а проблему. Модель не готова, и главная причина — не промпт, не grammar, не fewshot. Главная причина — модель non-deterministic. Все "улучшения" в моей сессии были частично noise. Grammar — единственный детерминированный рычаг. Остальное — лотерея.
>
> Не верь моим числам. Прогони сам. Multi-run. Усредни. Только тогда ты увидишь signal сквозь noise.
>
> Мир не обязан быть детерминированным. Но если ты измеряешь его single-run — ты измеряешь случайность, не систему.
