# RC8 Determinism RCA — S313→S314 (Understanding Track)

> Статус: CLOSED (расследование) — тёплый протокол принят; RC8 A/B проведён валидно; few-shot удалён; unspecified-дефект закрыт. Канонизация provenance — OPEN (следующий эксперимент, §8).
> Формат: хроника + установленные факты. Причины не атрибутируются сверх доказанного.

## 1. Исходный факт (S313, канон)

**Current inference path demonstrated non-reproducible canonical output despite temperature=0 + fixed seed.**

Контекст: для валидного A/B промптов требовался детерминированный sampling path; det-check (два прогона corpus, Compare-Object) ходил GREEN→RED на идентичном состоянии → semantic experiment STOP.

## 2. Инструментализация (S314, вердикт Мастера III.1)

- `[DET-ENV]` — отпечаток инстанса в каждом прогоне: SPAWN (pid+cmd+model) / REUSE (identity NOT verified, model id, owner_pid).
- `[DET-TRACE]` (env ENIGMA_DET_TRACE=1, default OFF) — prompt_md5/seed/resp_md5 на каждый запрос; хэш сырого ответа ДО парсинга.
- `ENIGMA_DET_KEEP_SERVER=1` — тёплые пары (corpus не убивает сервер; teardown по PID порта).
- `ENIGMA_RC8_STATE` — A/B-переключатель (после вердикта: default = baseline без few-shot; 'B' = легаси).
- Замки: test_det_instrumentation 3/3, test_rc8_ab_state 2/2. Коммит: 8d1124ff.

## 3. Матрица детерминизма (все прогоны валидны по отпечатку)

| замер | топология | corpus (90 фраз) |
|---|---|---|
| M1-p1 | cold SPAWN ×2 | RED 22/90 |
| M1-p2 | cold SPAWN ×2 | GREEN 0 |
| M1-p3 | cold SPAWN ×2 | RED 2/90 |
| M1-p4 | staggered (2 инстанса) | GREEN 0 |
| M2-p1..p3 | один тёплый PID ×2 | GREEN 0/90 ×3 |

Установленное: холодные пары инстансов флакают (0–24% промптов; входы байт-идентичны во всех замерах — дивергенция ниже нашего слоя); один тёплый инстанс — полная воспроизводимость corpus-данных. Warmup «привет» систематически бимодален (fresh vs warm — два стабильных ответа), отбрасывается по дизайну: абсорбирует самый шумный первый запрос. Канонический факт S313 остаётся в силе для cold-инстансов.

## 4. Экспериментальный протокол (вердикт Мастера)

**Warm same-instance protocol provides reproducibility sufficient for semantic A/B experiments; cold-instance reproducibility is not guaranteed.**

spawn → warmup → STATE-A → STATE-B → teardown; соло-окно (§3.12); валидность = отпечатки (A=SPAWN pid X, B=REUSE тот же X); det-check = тёплая пара; RED → STOP. Контрбаланс (A→B и B→A) обязателен: **observed order-dependent degradation under the current warm inference protocol** — второй по порядку прогон систематически хуже по метрикам качества (плейсхолдеры, потери актов), причина не установлена; счётчики канонических типов порядко-устойчивы.

## 5. RC8 A/B — результат и вердикт

Дизайн: единственная переменная — 3 few-shot строки ASK_PROVENANCE/QUESTION (контракт типа в обоих состояниях; замок диффа = ровно 3 строки). Пары A→B и B→A + 7 внешних production-прогонов.

- STATE-B (few-shot присутствует, бывший production): **0/27 ASK_PROVENANCE в 9 независимых прогонах**.
- STATE-A (few-shot удалён): 3/27 и 2/27 (оба порядка); стабильные попадания: «Вам кто-то рассказал, как меня зовут?» (чистая IND-формулировка, вне few-shot) и «Кто ей об этом рассказал?» (пограничная).

Вердикт (формулировка Мастера): текущий production prompt не эмитил ASK_PROVENANCE на 27 provenance probes; удаление трёх RC8 few-shot строк восстановило слабую, но воспроизводимую спонтанную canonicalization на части независимого корпуса; сами few-shot строки имеют доказанный отрицательный эффект.

Решение (V.1): строки удалены из production; ENIGMA_RC8_STATE='B' — легаси-переключатель для воспроизведения. Новых примеров не добавлять до следующего эксперимента.

## 6. unspecified-дефект нашего pipeline (V.3, закрыт)

Феномен: 19–29 фраз из 90 в det-замерах несли topic="unspecified" при нулевых вхождениях в сырых ответах модели. Локализация: intent_compressor.py, `_enrich` / `_recover_acts`, паттерн `_ro or "unspecified"` — плейсхолдер при speech_act=question без requested_outcome. Деформация измерительного сигнала собственным pipeline; фиктивный topic протекал и в DM-промпт («вопрос (тема: unspecified)»).

Фикс: акт без topic (честное UNKNOWN, §ENIGMA-003); provenance синтеза — source_fields; corpus-печать помечает recovery-акты «*». Замки: test_recovery_no_placeholder 3/3; fixture выровнен.

Валидация живым прогоном (rc8_baseline_v2.txt): unspecified=0 (везде), recovery-акты помечены (61), ASK_PROV=3, RECOVERY=35, полная сводка.

## 7. Baseline v2

reports/rc8_baseline_v2.txt — production-промпт без few-shot и без заглушек: ASK_PROVENANCE 3/27, unspecified 0. Точка отсчёта следующего canonicalization-эксперимента.

## 8. Открытое (следующий шаг)

1. **Канонизация provenance — OPEN:** следующий эксперимент проверяет КЛАССЫ (PROVENANCE vs ORDINARY vs SOCIAL/THIRD-PERSON QUESTION) на независимых формулировках, не конкретные предложения — под тёплым контрбалансированным протоколом.
2. RC3 (challenge-канонизация; корпус готов), RC4–RC7 — backlog.
3. IV.3 hygiene (отдельный пакет): identity-blind REUSE в production-спавнерах llm_manager — перенести fingerprint-принцип [DET-ENV].
4. IV.4 (defer): payload компрессора не самоописан (top_k/top_p/repeat_penalty — серверные дефолты) — provider-independence долг.
5. M3 (конкуренция) — закрыт: соло-окно обязательно в протоколе; атрибуция не нужна для выбора протокола.

## 9. Артефакты

reports/det_m1_p1..p4_*, det_m2_p1..p3_*, rc8_ab_*, rc8_ba_*, rc8_baseline_v2.txt; коммиты: 8d1124ff (инструментализация), RC8-verdict (удаление few-shot), V.3-unspecified.

