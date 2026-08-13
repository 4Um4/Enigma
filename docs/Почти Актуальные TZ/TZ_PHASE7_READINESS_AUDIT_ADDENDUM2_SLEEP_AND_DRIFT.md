# ТЗ — АУДИТ ГОТОВНОСТИ К ЭПОХЕ 7 (Post-Sleep & Drift Fixes)

**Версия:** 3.0 · 2026-08-13
**Назначение:** Обновлённый аудит после массовых фиксов багов сна и дрейфа A-класса. Документ очищен от решённых проблем (BUG-SLEEP-***, BUG-DRIFT-005..012) и сосредоточен исключительно на оставшихся блокерах перехода к Эпохе 7 (Фаза 2→3).

**Заключение:** ❌ Код **НЕ ГОТОВ** к переходу на Эпоху 7. Гейты Фазы 1→2 всё ещё блокированы инфраструктурой (LLM cache, ADR-Net, DRI). 4 из 4 гейтов Фазы 2→3 провалены с 0% готовности.

---

## 1. ВЕРДИКТ ПО ГОТОВНОСТИ К ЭПОХЕ 7

| Гейт | Статус | Готовность | Главный блокер |
|------|--------|------------|----------------|
| Фаза 0 → 1 | ⚠️ Частично | ~90% | Требуется 3-я сессия SHI=100%; canary green не подтверждён |
| Фаза 1 → 2 | ⚠️ Слабо | ~40% | LLM cache hit = 0%; ADR-Net MVI не обучена; формальный DRI-модуль отсутствует |
| **Фаза 2 → 3 (ЦЕЛЬ)** | ❌ **НЕ ГОТОВ** | **0%** | **4 из 4 гейтов провалены**: ProphecyEngine, §19 PerceptualKernel, BeliefMerger, ToM 4D + BELIEVES — все отсутствуют |

---

## 2. СТАТИЧЕСКИЙ АНАЛИЗ — ОСТАВШИЕСЯ НАХОДКИ

### 2.1 Скрытые exception-обработчики (21 "swallow-and-return-None")

Эти `try/except` блоки маскируют ошибки, возвращая None вместо re-raise:

| Файл | Line | Влияние |
|------|------|---------|
| `game_loop/__init__.py` | 413, 1470 | World-diff/state-load failures выглядят как "no diff exists" |
| `provider_manager.py` | 280, 322 | LLM provider failures выглядят как "no provider available" |
| `reduction.py` | 206, 216 | Phase output = None → "Ничего не произошло" |
| `replay_store.py` | 108, 225 | Deserialization errors → None → false drift reports |
| `router.py` | 421 | `_get_or_create_provider` возвращает None на любую ошибку |
| `perception_projector.py` | 57 | Perception failures silent |
| `reputation_engine.py` | 115 | Reputation updates lost |
| `dialogue_executor.py` | 235-237 | **BUG-NEW-DLG-004**: masks ALL LLM exceptions as empty text |

### 2.2 Неиспользуемые импорты и Dead code

- 124 неиспользуемых импорта в `backend/app` (требуется `ruff check --select F401`).
- `TickOutput` class (`game_loop/tick_context.py:70-78`) — empty `pass` body, never instantiated.
- `_TRAUMA_SCAR_RATE` constant (`affective_integrator.py:17`) — defined, never used.
- 108 TODO/FIXME/XXX/HACK markers в backend/app.

### 2.3 Type annotations & Architecture

- ~1,157 использований `Any` в backend/app — heavy "lazy typing" pattern.
- `diagnostics/report_renderer.py:123` вызывает `self._dna.save(snap)`. Нарушает принцип "diagnostics don't write state".

---

## 3. ФАЗА 1→2 — СТАТУС ГЕЙТОВ

| Гейт | Статус | Доказательство |
|------|--------|----------------|
| IPT coverage >80% | ⚠️ PARTIAL | 39 инвариантов. Нужно добавить §19/§18 контракты. |
| Replay exact-match 100 ticks | ✅ PASS | `replay_compare` показал 0 дрейфа (A/B/C/D/E = 0). |
| LLM P50 <2.5s | ✅ PASS | 0.6–1.3с. |
| LLM cache hit ≥35% | ❌ FAIL | 0% (only prompt_hash). No BGE-small-ru + FAISS semantic cache. |
| DRI green ×5 sessions | ❌ FAIL | Формального DRI-модуля `diagnostics/dri*.py` нет. LAST_SESSION DRI=100% — это LLM response rate. |
| ADR-Net MVI trained | ❌ FAIL | `adr_net/` имеет только parser/conflict_detector. Нет NN model. |

---

## 4. ФАЗА 2→3 (ЭПОХА 7) — СТАТУС ГЕЙТОВ (ЦЕЛЬ)

| Гейт | Статус | Доказательство |
|------|--------|----------------|
| Prophecy Causality Law green (ADR-O-330) | ❌ NOT IMPLEMENTED | Glob `**/prophecy*` = 0 файлов. Нет `backend/app/cognition/prophecy_engine.py`. |
| Vertical Slice «Секреты Люси» playable | ❌ NOT BUILT | Только `Open_road` campaign существует. |
| ToM-метрика: NPC models beliefs of 2+ others | ❌ NOT IMPLEMENTED | Существующий `belief_crystallization_engine.py` — это Epoch-3 fear-trust движок, NOT 4D + BELIEVES. |
| §19 surprise metric measured | ❌ NOT IMPLEMENTED | Существующий `PerceptualKernel` — OLD motor kernel. §19 spec файл не существует. |

### 4.1 Файлы, которые должны существовать, но отсутствуют

| Файл | roadmap § | Статус |
|------|-----------|--------|
| `backend/app/cognition/belief_merger.py` | §2.2 | ❌ MISSING |
| `backend/app/cognition/prophecy_engine.py` | §2.4 | ❌ MISSING |
| `backend/app/perception/perceptual_kernel.py` (§19-spec) | §2.3 | ❌ MISSING |
| `backend/app/llm/audit_log.py` | §2.6 | ❌ MISSING |
| `diagnostics/dri*.py` (formal DRI module) | §2.5 | ❌ MISSING |
| ADR-Net trained NN model file | §1.4 | ❌ MISSING |
| LLM Semantic Cache (BGE-small-ru + FAISS) | §1.6 | ❌ MISSING |
| Vertical Slice campaign `Секреты Люси` | §2.5 | ❌ MISSING |

---

## 5. КАТАЛОГ ОСТАВШИХСЯ БАГОВ С ПРИОРИТЕТАМИ

### 5.1 P0 — Critical (блокирует Фазу 0→1)

| # | ID | Файл | Описание | Effort |
|---|-----|------|----------|--------|
| 1 | BUG-CORE-001/002/003 | (см. Addendum 1) | Топ-3 блокера из предыдущих аудитов | ~17 ч |

### 5.2 P1 — High (блокирует Фазу 1→2)

| # | ID | Файл | Описание | Effort |
|---|-----|------|----------|--------|
| 2 | BUG-NEW-DLG-004 | `dialogue_executor.py:235-237` | LLM error masking — `except Exception: return ""` | 2 ч |
| 3 | 21 swallow-and-return-None | (см. §2.1) | Скрытые exception-обработчики | 8 ч |
| 4 | LLM cache hit = 0% | (новый, §1.6) | Semantic cache BGE-small-ru + FAISS | 32 ч |
| 5 | ADR-Net MVI | (новый, §1.4) | Обучить NN model | 48 ч |
| 6 | Formal DRI module | (новый, §2.5) | `diagnostics/dri*.py` | 8 ч |
| 7 | Audit Log LLM | (новый, §2.6) | `backend/app/llm/audit_log.py` | 6 ч |
| 8 | IPT coverage extension | (новый, §1.1) | Добавить §19/§18 инварианты | 8 ч |
| 9 | Replay_determinism finish | (новый) | Догнать 2×10k тиков | 4 ч |

**Суммарно P1:** ~116 ч

### 5.3 P2 — Medium (блокирует Фазу 2→3 = Эпоху 7)

| # | ID | Файл | Описание | Effort |
|---|-----|------|----------|--------|
| 10 | BeliefMerger | новый `cognition/belief_merger.py` | Roadmap §2.2 — source-weighted merge | 32 ч |
| 11 | §19 PerceptualKernel | новый `perception/perceptual_kernel.py` | Roadmap §2.3 — `surprise = -log P(x_t|z_{t-1})` | 48 ч |
| 12 | ProphecyEngine | новый `cognition/prophecy_engine.py` | Roadmap §2.4 + ADR-O-330 | 40 ч |
| 13 | ToM 4D + BELIEVES | расширение `belief_crystallization_engine.py` | Roadmap §2.1 — `CrystallizedBelief` + second-order BELIEVES | 48 ч |
| 14 | Vertical Slice campaign | новый `data/campaigns/lucy_secrets/` | Roadmap §2.5 — demo «Секреты Люси» | 24 ч |

**Суммарно P2:** ~192 ч

### 5.4 P3 — Low (post-Phase 7)

| # | ID | Описание | Effort |
|---|-----|----------|--------|
| 15 | 124 неиспользуемых импорта | `ruff check --select F401 backend/` | 2 ч |
| 16 | 108 TODO/FIXME markers | Аудит и закрытие | 8 ч |
| 17 | Dead code (TickOutput, _TRAUMA_SCAR_RATE) | Удаление | 2 ч |
| 18 | Type annotations (1157 `Any`) | Refactor | 16 ч |
| 19 | Diagnostics writing state | Refactor в MetricsExporter | 8 ч |

**Суммарно P3:** ~36 ч

### 5.5 Итоговая оценка

| Приоритет | Сумма часов |
|-----------|-------------|
| P0 (Critical) | ~17 ч |
| P1 (High) | ~116 ч |
| P2 (Medium, Phase 7) | ~192 ч |
| P3 (Low) | ~36 ч |
| **ИТОГО до Эпохи 7 (P0+P1+P2):** | **~325 ч** |

---

## 6. КРАТКИЕ РЕКОМЕНДАЦИИ ПО ДАЛЬНЕЙШЕМУ ТЕСТИРОВАНИЮ

1. **Перед переходом на Фазу 2 (Эпоха 7)**:
   - Прогнать `long_horizon` (100 000 тиков) — целевой порог ФАЗЫ 3.
   - Прогнать `chunk_migration` (10 000 тиков с boundary transitions).
   - 3 сессии подряд с SHI=100% (гейт Фазы 0→1).
   - canary `test_full_playthrough.py` green.
2. **Метрики для CI dashboard** (добавить в `diagnostics/dna_metrics.py`):
   - `REPLAY_MATCH_RATE` — % совпадающих тиков в replay_compare (должно быть 100%).
   - `SCHED_PERSISTENCE_RATIO` — % тиков с `prev != ''` (должно быть 100%).

---

*Аудит завершён. Все баги сна и дрейфа A-класса из предыдущих аддендумов успешно закрыты. Оставшийся долг — инфраструктура LLM/ADR-Net и реализация когнитивного ядра Эпохи 7.*
```

Скопируй этот текст и замени им содержимое `TZ_PHASE7_READINESS_AUDIT_ADDENDUM2_SLEEP_AND_DRIFT.md`. Теперь этот документ чётко отражает текущее состояние проекта без шума от уже решённых проблем!