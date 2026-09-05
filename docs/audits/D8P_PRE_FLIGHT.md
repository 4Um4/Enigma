# D8P PRE-FLIGHT — досье-проект intelligence queue (production-форма ADR-O-377 / DEBT-RE-D2A)

> Статус: ДО КОДА (runtime не тронут). Сессия: AG1-D8p (номер = max+1 по хвосту
> MUTATIONS в момент записи; кандидат S249 — хвост живой, три серии активны).
> Мандат двойной (консенсус): ТЗ-вход S238 §IV (executor-поток + commitment-outbox,
> прецедент `drain_commitment_outbox`) ≡ DEBT-RE-D2A forensic-соседа (TaskScheduler
> FIFO → LLM → Proposal → DeltaGate; STALE по tick; REBASE отложен §ENIGMA-002).
> Дисциплина: законы до решений — Q1–Q5 (§12) закрываются вердиктом владельца ДО кода.
> Фальсификаторы слоя: (F-время) ядро живо по wall-clock, пока интеллект думает —
> `wait 20` ≤ 10с в живой uvicorn БЕЗ отцепления экстрактора; (F-семантика) поздний
> смысл применяется только пока актуален — STALE никогда не применяется, тем более молча.

## 1. Границы слоя (терминологическая лестница)

- **≠ ADR-O-364/O-343:** генерация реплик УЖЕ декуплирована от тика (DialogueQueue →
  ThreadPoolExecutor(max_workers=1) → Timer-abort). D8p генерацию не трогает.
- **≠ RE-D2 guard (router):** containment — громкий отказ loop-вызовов. Дедлок
  невозможен, но player-семантика деградирует (пустой DialogueUpdate). D8p = слой
  НАД guard'ом: loop-поток перестаёт звать LLM by construction.
- **≠ cockpit-форма (O-377):** измерительный класс-патч на время wait. Не production.
- **≠ ADR-O-365 outbox:** терминальные зеркала ВЛАДЕНИЯ (исходы задач), sync-дренаж
  в двух точках. Рельс-прецедент; содержимое — исходы, не смысл.
- **= D8p:** производство ИНТЕРПРЕТАЦИИ — разрыв сцепки «LLM-интерпретация ↔
  поток/время публикатора события» + позднее применение через stale-гейт.

## 2. Археологическая карта (факты, файл:строки)

### 2.1. Три контекста исполнения экстракции

| # | Публикатор NPC_SPOKE | Поток | Экстракция сегодня | Следствие |
|---|---|---|---|---|
| 1 | DialogueMaterializer ← `_process_tasks_async` | pool-worker (max_workers=1) | работает (worker-ветка роутера) | занимает единственный воркер 3.3–4.3с; сериализация с генерацией |
| 2 | `working_memory_tick` ← `run_turn` (async) | **event loop** | guard → RuntimeError → S198/AG1-D2 → **пустой DialogueUpdate** | семантическая потеря player-пути (досье RE-D2 §4b) |
| 3 | fast-path S216 ← `execute_pending` sync | тик-стек (threadpool / loop) | как (1) или (2) по потоку | wall-clock вклад в тик — эмпирика Шага 2 |

### 2.2. Ключевые структуры

| Узел | Файл:строки | Факт |
|---|---|---|
| Router | svc/llm/router.py:465 | 3 пути: worker-ветка (:548+, `_worker_lock`+`_request_in_progress` :171/:548-557/:610, abort-stuck) · без петли → `asyncio.run` · loop → RE-D2 guard (:617+, `coro.close()`+RuntimeError). Сериализация ВСЕХ worker-LLM между собой |
| Пул задач | task_scheduler.py:64/:258 | ThreadPoolExecutor(max_workers=1); submit неблокирующий |
| Outbox-рельс | task_scheduler.py:75/:85/:92; game_loop:1334/:1589 | thread-safe append; sync-дренаж 2 точки |
| Диалоговая очередь | dialogue_queue.py:54-111 | backpressure: ambient DROP / canonical PRESERVE-evict |
| Исполнитель реплик | dialogue_executor.py:101-129/:253 | Timer-abort (O-364); request_for_agent max_tokens=100 |
| Подписки NPC_SPOKE | game_loop:419/:420/:424/:463 | NpcDialogue(+extractor) · DialogueMemory · EcoTracker · ClaimEvent — sync-fanout в потоке публикатора |
| Инъекция экстрактора | game_loop:382-383 | DialogueUpdateExtractor(router=dm_agent.router) → NpcDialogueSubscriber |
| Экстракция | npc_dialogue_subscriber.py:131 | extract(stm_before, text, speaker) → DialogueUpdate |
| Куда пишет LLM | npc_dialogue_subscriber._process_canonical | ТОЛЬКО MemoryManager session API (intent/topic/claims/questions). RelationshipStore+L1 — tone-based, LLM-независимы. Психику не трогает |
| Деградация | dialogue_update_extractor.py:33/:72-74 | sync request_for_agent(agent="dialogue_extractor", max_tokens=200, json); отказ → empty DialogueUpdate |
| Player-продюсер | game_loop:1510 → working_memory_tick:29 | publish NPC_SPOKE на loop-потоке; сам LLM не зовёт; FT-3-гвард жив |
| Пейсинг | speech_scheduler.py:23 | 2.0с wall-clock, infrastructure (§15.2-легально) |
| Cockpit | terminal_cockpit.py:180 | класс-патч extract→None на wait; finally-restore |

### 2.3. Ключевое сужение (Q3)

LLM-интерпретация диалога = один вызов; его результат входит в state ТОЛЬКО через
домен MemoryManager (session). DeltaGate WHITELIST = psyche-скаляры
(threat_gradient/danger_belief) — dialogue-семантика через него не проходит без
расширения (= красный флаг №1: цензус потребителей + мини-ADR).

## 3. Anti-Bond (Р17-П1)

| Слой | Выполняет | НЕ выполняет |
|---|---|---|
| TaskScheduler+пул (O-343/364) | декупляция ГЕНЕРАЦИИ от тика; очередь+backpressure+таймаут | декупляцию ИНТЕРПРЕТАЦИИ от потока публикатора; позднее применение экстракции |
| DialogueQueue | backpressure материализации реплик | ничего про смысл |
| O-365 outbox | relay терминалов ВЛАДЕНИЯ в sync-точки | relay семантических LLM-результатов; stale-семантику содержания |
| RE-D2 guard | громкий отказ loop-LLM | работоспособность player-семантики |
| Cockpit | измерение без шлагбаума | production |
| R4A-воркеры | изолированные суммаризации | dialogue-экстракцию |

**Остаток (уникальная работа intelligence queue):**
1. Thread-декупляция интерпретации от публикатора — player-путь восстанавливается
   семантически без LLM-в-петле (guard становится недостижим);
2. Позднее применение смысла со stale-гейтом — инверсия зомби-round-trip: результат
   применяется ПОСЛЕ ухода ждущего, но валидированно — не выбрасывается и не втихую;
3. Наблюдаемое отбрасывание протухшего (табу O-377: «не молча»);
4. Единая FIFO-дисциплина интеллекта (см. Q4) без второй точки сериализации LLM.

Two-Domain (§ENIGMA-002): локальное лекарство доказанного бага (LLM в потоке
публикатора ×3 контекста — RE-D2-класс). REBASE/генерализация примитивов отложена
(вердикт D2A-соседа; подтверждено при archaeology).

## 4. Доктрина Мастера (реестр видения)

Источник-вербатим: регистрация DEBT-RE-D2A (MUTATIONS S248:964) + ТЗ AG1-D8p §II:
**три скорости** (быстрый мир никогда не ждёт медленного интеллекта) ·
**FOCUS TIME ≠ PAUSE TIME** · **Class A/B/C** · **право перебивания**.
Полный текст классов A/B/C — у владельца (в досье — вход Q4). Для v1: перебивание =
STALE-discard (наблюдаемое), не kill живой задачи.

## 5. Контракт очереди (draft; финал = §12)

- `IntelligenceTask`: event_id (NPC_SPOKE UUID), campaign_id, speaker, listener,
  text, stm_before, parent_tick; task_id детерминированный H(...) (uuid4 запрещён).
- Enqueue: подписчик → thread-safe non-blocking → немедленный возврат; STM-ход
  пишется сразу (intent="dialogue" placeholder — существующая семантика деградации).
- Исполнение: диспетч (Q4) → extract (worker-поток) → DialogueUpdate → stale-гейт
  → применение через MemoryManager session API (Q3) → наблюдаемая трасса.
- Идемпотентность: `_enqueued{event_id}` / `_applied{event_id}` (Q5).
- Флаг `D8P_ENABLED` default OFF = байт-идентичное поведение (прецеденты
  W3_G2_ENABLED/BC1_ENABLED).

## 6. Конвейер (эскиз)

    NPC_SPOKE (публикатор: loop | pool-worker | тик-стек)
      → NpcDialogueSubscriber._process_canonical
      → [ON]  enqueue IntelligenceTask (non-blocking) + STM-ход (placeholder)
              → executor (Q4) → extractor.extract (worker-поток; guard недостижим)
              → stale-гейт (parent_tick-возраст + liveness акторов)
                  → FRESH: session-enrichment (MemoryManager API) + трасса APPLIED
                  → STALE: discard + лог/метрика STALE (наблюдаемо)
      → [OFF] сегодняшнее поведение дословно

## 7. Риски/оговорки

- **Router-сериализация** (факт §2.2): выделенный executor не даёт параллелизма,
  даёт abort-конкуренцию (зона соседа) → кандидат Q4(а): диспетч на существующий пул.
- **Гонка обогащения:** session API мутирует после appended-хода; индексы вопросов
  стабильны (append-mostly); stale-гейт режет основную массу; остаток — калибровка.
- **Зона соседа:** router.py не трогается; только координация.
- **wait 20:** вкладчики — sync-подписчики на threadpool-тике, pacing 2с, пул-
  сериализация; краснота = факт замера (§9), не предположение.

## 8. PRE-FLIGHT ADR-чеклист (номер = max+1 атласа В МОМЕНТ записи; кандидат O-382)

1. Тип: ONTOLOGY. 2. Домены: memory (session-enrichment), llm-execution (декупляция),
game_loop (проводка). 3. Downstream: MemoryManager sessions; владельцы O-364/O-365 —
координация. 4. Бюджет: RAM ~KBs (очередь + 2 множества идентификаторов); latency:
тик −(3.3–4.3с sync-экстракции), +enqueue ≈ 0. 5. Rollback: D8P_ENABLED=OFF = no-op.
6. Регрессия: §9.

## 9. Сценарий приёмки

**Шаг 2 — замер ДО (красный baseline обязателен):** живой uvicorn + живой
llama-server (поднимает владелец; CONFIG-DEBT: config ищет несуществующий
Q5_K_M.gguf, фактически грузился Q5 4.36 GiB — label/путь рассинхрон, эскалация,
не мой фикс). Кокпит `new` → `wait 20` **без отцепления экстрактора**
(измерительный env-флаг в cockpit, test-zone, обратимо; добавляется в prep-Шага 2)
→ wall-clock. Красные-кандидаты: **R1** wall-clock > 10с; **R2** player-семантика
(пустой DialogueUpdate на loop-пути) — уже доказан (S248-досье). Если R1 замерится
зелёным — эскалация владельцу: критерий не ослабляю сам (красный флаг №7).
«Почти зелёного» не существует.

**Шаг 4 — ПОСЛЕ:** тот же сценарий; метрика = wall-clock + исполненные/применённые/
отброшенные задачи (НЕ впечатление). Гейты: IPT 45/45 + замки 45/45 +
causal_state_test parity (Люся 0.800/0.272/0.777; A−C=0.023; Горан C−B flee≈+0.33;
seed=0 при дрожи) + bc1 6/6 + ruff.

## 10. Кандидаты IPT-инвариантов

- INV-D8P-NOOP: OFF → тик байтово идентичен.
- INV-LLM-LOOP-EXILE: при ON — request_for_agent из loop-потока = 0 (guard
  недостижим by construction).
- INV-D8P-TRACE-ONCE: один event.id → ≤1 применённого DialogueUpdate.
- INV-D8P-STALE-OBSERVABLE: каждый discard = лог + счётчик.

## 11. Табу (черновик ADR)

❌ `future.result` на event-loop-потоке; ❌ применение STALE; ❌ тихий discard;
❌ расширение DeltaGate.WHITELIST без цензуса потребителей + мини-ADR; ❌ priority(int)
как causal-класс; ❌ правка router.py/гварда соседа; ❌ вторая точка сериализации LLM
в обход router; ❌ применение мимо MemoryManager session API; ❌ ON по умолчанию;
❌ «просто увеличить таймаут» (противоположность мандата).

## 13. Вердикты владельца — ФИНАЛ (до кода; §5–§6-эскизы финализируются этим параграфом)

- **Q1a**: ONLY `DialogueUpdateExtractor.extract` (подписчик). Один фактический
  LLM-вызов = источник проблемы; три контекста (§2.1) — пути одного вызова. R4A и
  генерация не трогаются (лечить соседний механизм без доказанного дефекта
  запрещено). **Scope D8P = extraction decoupling only.**
- **Q2б**: скользящее окно N тиков, старт **N=3** — calibration constant, НЕ
  архитектурная истина (не канонизировать число как закон):
  `STALE = (current_tick - parent_tick > D8P_MAX_AGE_TICKS) OR session отсутствует
  OR required actor invalid/dead/out-of-world`. Строго `>` (не `>=`): окно из трёх
  тиков = три допустимых возраста.
- **Q3б**: **MemoryManager time-bridge, безоговорочно.** Intelligence Queue →
  DialogueUpdate → STALE/validity gate → MemoryManager session API. **DeltaGate НЕ
  расширяется 🔒.** Формула «LLM → Proposal → DeltaGate» — верная доктринальная
  интуиция, не соответствующая фактической топологии этого домена:
  psyche/causal state → DeltaGate; session dialogue semantics → MemoryManager.
  Искусственный мост между доменами запрещён. **D8P — time bridge, а не новый
  state authority:** LLM не получает права писать состояние; существующий
  легальный владелец домена решает, как интерпретация входит в session memory.
- **Q4а**: существующий max_workers=1 пул. **D8P не создаёт второй LLM execution
  domain** — intelligence-очередь = логическая очередь задач, не источник
  параллелизма: multiple producers → Intelligence FIFO → existing TaskScheduler
  executor → Router serialization. **FIFO; v1 без retry** (порядок повторных /
  starvation / stale-during-retry / конкуренция с generation / observability
  attempt-vs-task — отдельная политика, не часть лечения RE-D2). **Class A/B/C
  наследуется из доктрины, не изобретается**: operational mapping v1 — A = task
  сохраняется как значимый intelligence work; B = canonical intelligence work по
  существующему правилу; C = ambient / не создаёт extraction task. ЗАПРЕТ:
  фиксировать `A = player-origin` как архитектурный закон до дословного
  канонического классификатора (происхождение события ≠ каузальная значимость —
  не обязательно одна ось).
- **Q5**: идемпотентность целиком: `one event.id → at most one IntelligenceTask →
  at most one applied DialogueUpdate`. Lifecycle наблюдаемых состояний различать
  явно: `ENQUEUED / EXECUTED / APPLIED / STALE_DISCARDED / FAILED`. `≤1 applied` —
  инвариант состояния; факт исполнения worker-задачи — отдельная наблюдаемая
  история (forensic различает: не запускалось / запускалось-stale /
  запускалось-упало / запускалось-применилось). Lifecycle IntelligenceTask —
  собственный реестр очереди, НЕ TaskState диалоговых задач (O-364-taboo не
  затрагивается).

### 13.1 Git-инцидент 6ad6e819 — вердикт (а)

История НЕ переписывается («git-история = геологический разрез, не
отредактированная биография»). Хвост W-track (B1.4-RECEIVER в game_loop) уехал в
моём S247-коммите; routes-половина соседей осталась в рабочем дереве нетронутой.
Модель: 6ad6e819 → attribution → documented coordination anchor → current
ownership state. Координационный якорь W-track входит в мою MUTATIONS-запись при
закрытии сессии (S249-кандидат) и в док-кадр Roadmap.

### 13.2 Baseline — две независимые оси

`R1 (TIME FAILURE)` — wall-clock `wait 20`: если <10с — **не опровергает D8P**,
опровергает только гипотезу «в данном сценарии блокировка уже превышает порог».
`R2 (SEMANTIC FAILURE)` — loop-thread → синхронная LLM-попытка → runtime
failure/semantic degradation — **уже исторически красный (S248)**. D8P существует
прежде всего для устранения архитектурной сцепки, порождающей R2 и потенциально
R1. Обе оси фиксируются в замере ДО.

### 13.3 Итоговый поток (владелец, вербатим)

    NPC_SPOKE → fast world → placeholder memory immediately → IntelligenceTask
    → existing single execution rail → LLM interpretation → STALE validation
    → existing MemoryManager authority

Не новый интеллект-движок. Не новый state owner. Не новый executor. Только разрыв
неправильной временной связи между моментом события и моментом интерпретации.

### 13.4 Порядок фронтов (разрешение владельца)

мини-ADR (номер max+1 по свежему чтению атласа; O-382 — кандидат) → IMPACT
(четыре границы: router.py NO TOUCH / DeltaGate NO TOUCH / MemoryManager legal
application authority / TaskScheduler pool existing execution rail) → красный
baseline (R1+R2) → **код D8P — только после этого, не раньше.**