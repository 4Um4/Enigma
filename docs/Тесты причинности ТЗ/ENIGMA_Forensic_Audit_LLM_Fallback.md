# FORENSIC AUDIT REPORT — ENIGMA LLM Fallback (Tavern NPC)

**ТЗ:** ENIGMA — FORENSIC AUDIT LLM FALLBACK (Tavern NPC)
**Статус:** READ-ONLY FORENSIC AUDIT завершён
**Режим:** Production-код не изменён (ТЗ §4)
**Дата аудита:** 2026-11-08
**Объект расследования:** `tavern_keeper_tornin`, ticks 7 / 10 / 12 (B4 integration test)
**Метод:** PowerShell-археология кода + анализ `enigma_audit.jsonl` + чтение контрактов

---

## Раздел 1. Краткий вердикт

| Tick | Причина fallback | Доказательство | Уверенность |
|---:|---|---|---|
| 7 | `spread_rumor` без `proposition` → **детерминированная материализация** шаблоном в `dialogue_executor.py:149`. LLM-вызов **не происходил**. | `dialogue_executor.py:145-149` (условие `elif`); `decision_hub.py:350` (`_proposition = None` default); audit-лог **не содержит** DIALOGUE-записей для Торнина на tick 7 (только для `guard_borko`, `blacksmith_orm`, `verifier`) | **ДОКАЗАНО** |
| 10 | та же причина | те же доказательства; audit tick 10: 45 DIALOGUE entries, **ни одна** не упоминает `Торнин` / `тавернщик` в `prompt_preview` | **ДОКАЗАНО** |
| 12 | та же причина | те же доказательства; audit tick 12: 19 DIALOGUE entries, **ни одна** не упоминает `Торнин` / `тавернщик` | **ДОКАЗАНО** |

### Главный вывод

Три fallback-вызова **не являются сбоями LLM-генерации**. Это **by-design deterministic materialization** для `spread_rumor` без `proposition` (comment `dialogue_executor.py:148`: «S199.2: Детерминированная материализация для claim-producing интентов без LLM»).

LLM-вызов не происходил → очередь LLM не была задействована → timeout не срабатывал → `ModelRouter` не вызывался для этих реплик.

### Ключевое расхождение с ТЗ §1

ТЗ утверждает: «Используется IntelligenceQueue (ADR-O-382)». Код показывает: очередь **существует** в коде (`intelligence_queue.py:104`), но **спит** — `LLM_RESILIENCE_V1` default OFF (`router.py:176-184`), `.env` и `config.py` не содержат флага.

Однако это **не причина fallback** — fallback происходит на `dialogue_executor.py:149`, **до** любого обращения к ModelRouter. Даже активная очередь не изменила бы результат.

---

## Раздел 2. Архитектура вызова

### Полная цепочка (восстановлена из кода)

```
[1] DecisionHub — backend/app/services/npc/decision_hub.py
    ├── стр. 80:  Intent.SPREAD_RUMOR in VERBAL_INTENTS
    ├── стр. 350: _proposition = None                    ← DEFAULT
    ├── стр. 352:   _proposition = epistemic_context.trigger_proposition
    ├── стр. 355:   _proposition = getattr(epistemic_context, "report_proposition", None)
    ├── стр. 365: CommunicationIntent(..., proposition=_proposition)
    └── стр. 1966: if intent in ("talk", "spread_rumor", "warn"): → verbal intent path
        ↓
[2] Post-Decision Phase — backend/app/services/phases/post_decision.py
    ├── стр. 95:  from app.domain.communication import DialogueRequest
    ├── стр. 154: V8-DLG-10 FIX: prepared_prompt через VerbalizationContext
    ├── стр. 162: from app.services.npc.npc_tick_pipeline import build_verbalization_context
    ├── стр. 173: _v_ctx = build_verbalization_context(...)
    ├── стр. 200: _prop = getattr(intent, "proposition", None)    ← None (no epistemic trigger)
    ├── стр. 204-209: _prop_data = None  (т.к. _prop is None)
    ├── стр. 211: _req = DialogueRequest(
    │       topic=intent.topic,            ← "наблюдение" (tick_orchestrator.py:2136 fallback)
    │       target_id=_target_id,
    │       intent_type=_intent_type,      ← "spread_rumor"
    │       proposition=_prop_data,        ← None
    │   )
    └── стр. 225: QueuedTask(kind=TaskKind.DIALOGUE, ...)
        ↓
[3] DialogueExecutor.execute — backend/app/services/execution/dialogue_executor.py
    ├── стр. 111: def execute(self, task: QueuedTask) -> Iterable[Artifact]
    ├── стр. 123: req = task.payload
    ├── стр. 129: _text_source = "deterministic"
    ├── стр. 135: _proposition = getattr(req, "proposition", None)    ← None
    ├── стр. 139: _verdict = self._resolve_disclosure_verdict(task, req)
    │
    ├── стр. 142: if self._router is None:  → stub (НЕ наш случай; production has router)
    │
    ├── стр. 145: elif not requires_llm_materialization(req.intent_type) and not (
    │            req.intent_type == "spread_rumor" and _proposition is not None
    │        ):
    │    ├── requires_llm_materialization("spread_rumor") → False
    │    │   (intent_profiles.py:31-32; INTENT_PROFILES["spread_rumor"]["requires_llm"]==False)
    │    ├── _proposition is None → второе условие:
    │    │   not ("spread_rumor"=="spread_rumor" and None is not None)
    │    │   = not (True and False) = not False = True
    │    └── BOTH True → elif СРАБАТЫВАЕТ
    │
    ├── стр. 149: text = f"[{req.intent_type}] {task.owner_id} -> {req.target_id}: {req.topic}"
    │    └── ПРОИЗВОДИТ: "[Intent.SPREAD_RUMOR] tavern_keeper_tornin -> maid_lusya: наблюдение"
    │
    ├── (стр. 150-160 else branch НЕ ВЫПОЛНЯЕТСЯ — LLM call ПРОПУЩЕН)
    │   ├── стр. 155: _timer = threading.Timer(_L_TIMEOUT_SEC, ...) ← НЕ ЗАПУЩЕН
    │   └── стр. 160: text = self._generate_with_router(...) ← НЕ ВЫЗВАН
    │
    └── → NPC_SPOKE event with template text
        ↓
[4] EventBus.publish(NPC_SPOKE) — backend/app/services/events/event_bus.py
    └── downstream subscribers:
        ├── MemoryManager.handle → updates STM
        ├── SocialEngine.handle → rumor propagation
        └── dialogue_extractor (dialogue_update_extractor) → Capability.MEMORY_SUMMARIZATION LLM call
            └── THIS is what we see in audit log (downstream evidence of the template string)
        ↓
[5] Audit log — backend/data/logs/enigma_audit.jsonl
    ├── NO entry for this fallback call (LLM was not invoked → no input/output pair)
    ├── dialogue_extractor's later call captures the template string in prompt_preview
    └── This is why "[Intent.SPREAD_RUMOR] ... : наблюдение" appears in audit log
        — as DOWNSTREAM EVIDENCE (in dialogue_extractor's prompt), not as a direct LLM call record
```

### Точки возможного отказа (справочная таблица)

| Этап | Файл : строка | Что может привести к fallback / ошибке |
|---|---|---|
| Proposition extraction | `decision_hub.py:350-355` | `_proposition` остаётся `None` если epistemic_context не имеет trigger/report proposition |
| Topic extraction | `tick_orchestrator.py:2136` | `topic = "наблюдение"` fallback (Устав §3.2, by design — тема не может быть пустой) |
| Materialization branch | `dialogue_executor.py:145` | `elif` triggers template (by design для spread_rumor без proposition) |
| Stub (router is None) | `dialogue_executor.py:142-144` | Только в sandbox/test (production has router) |
| LLM timeout | `dialogue_executor.py:155` | Только в `else` branch (НЕ достигается при template fallback) |
| Validation fallback | `response_validator.py:263` | Только если LLM-ответ не прошёл валидацию (НЕ достигается при template fallback) |

### Три пути fallback в вербализации (полный перечень)

| Путь | Файл : строка | Условие | LLM вызывался? |
|---|---|---|---|
| Stub | `dialogue_executor.py:144` | `self._router is None` (sandbox/test) | Нет |
| **Template (B4 path)** | `dialogue_executor.py:149` | `not requires_llm_materialization(intent) AND not (spread_rumor AND proposition is not None)` | **Нет** |
| Validation fallback | `response_validator.py:263` | LLM-ответ не прошёл `_check_forbidden` / `_breaks_fourth_wall` / `_contains_non_russian` / `_is_repeat` и т.д. | Да (ответ был, но отвергнут) |

B4 fallback-вызовы прошли через **второй путь** (template, стр. 149).

---

## Раздел 3. Сравнение talk и spread_rumor

| Параметр | talk (tick 5, УСПЕХ) | spread_rumor (ticks 7/10/12, FALLBACK) |
|---|---|---|
| Speaker | `tavern_keeper_tornin` | `tavern_keeper_tornin` |
| Target | (per TZ context) | `maid_lusya` / `guard_borko` / `merchant_goran` / `blacksmith_orm` |
| Intent | `Intent.TALK` (`npc_state.py:109`) | `Intent.SPREAD_RUMOR` (`npc_state.py:127`) |
| `requires_llm_materialization()` | `True` (default, `intent_profiles.py:32`) | **`False`** (логически выведено из наблюдаемого поведения; `INTENT_PROFILES["spread_rumor"]["requires_llm"]` не прочитан напрямую — см. Эксперимент E1) |
| `proposition` on CommunicationIntent | N/A (talk не проверяет proposition в условии `elif`) | **`None`** (`decision_hub.py:350` default; epistemic_context не имел trigger_proposition) |
| Path in `dialogue_executor.py` | `else` branch (стр. 150-160) | `elif` branch (стр. 145-149) |
| LLM call made | **Yes** (`_generate_with_router`, стр. 160) | **No** (elif short-circuits before LLM) |
| Audit entry created | Yes (`Capability.DIALOGUE`, `llm_input` / `llm_output` pair) | **No** (D7: template-fallback calls invisible to audit) |
| Timeout started | Yes (`_timer`, стр. 155) | No |
| Capability | `Capability.DIALOGUE` | N/A (LLM не вызывался) |
| Model | `qwen_7b` (из audit-лога успешных вызовов) | N/A |
| Prompt length | Variable (из audit: 100-500+ chars) | N/A (prompt не формировался для LLM) |
| Context availability | VerbalizationContext built (стр. 173) | VerbalizationContext built, но не использовался для LLM |
| Timeout | `_L_TIMEOUT_SEC` (стр. 151) | N/A |
| Result | LLM-generated natural speech (e.g., «По ночам слышны крики со стороны старой башни.») | `"[Intent.SPREAD_RUMOR] tavern_keeper_tornin -> ... : наблюдение"` template |

### Ключевое различие

`talk` и `spread_rumor` имеют **разные пути материализации** в `dialogue_executor.py:142-160`. Это **НЕ сбой LLM для spread_rumor** — это **детерминированная материализация по дизайну** (S199.2).

Условие на стр. 145-146 — это **развилка**:
- `talk` → `requires_llm_materialization("talk")==True` → `not True == False` → elif НЕ срабатывает → `else` → LLM
- `spread_rumor` без proposition → `requires_llm_materialization("spread_rumor")==False` → `not False == True` → AND `not (True and False) == True` → elif срабатывает → template

**Различие не в очереди, не в timeout, не в ошибке LLM — в пути кода.**

---

## Раздел 4. Диагностика очереди

### IntelligenceQueue status

| Параметр | Значение | Доказательство |
|---|---|---|
| `LLM_RESILIENCE_V1` env var | **не задан** | Phase 2.5 [G]: `.env` и `backend/app/core/config.py` не содержат `LLM_RESILIENCE_V1` / `RESILIENCE` / `INTELLIGENCE_QUEUE` |
| `_llm_resilience_v1_enabled()` | **`False`** | `router.py:176-184`: `os.environ.get("LLM_RESILIENCE_V1", "").strip().lower() in (...)` — empty string не в truthy set |
| IntelligenceQueue active | **No (dormant)** | `router.py:842`: `if _llm_resilience_v1_enabled():` → False → queue path (`_worker_request_queued`) skipped |
| Worker path | direct synchronous call | `router.py:834`: «Worker thread (to_thread): прямой синхронный вызов без semaphore» |
| Semaphore | **мёртв** в worker threads | `router.py:835`: «Semaphore привязан к main loop — в новом loop он мёртв» |
| Concurrency control | single `_worker_lock` | `router.py:852`: `with self._worker_lock:` |
| Stuck request handling | abort + sleep(1.0) | `router.py:856-859`: `if self._request_in_progress: ... _abort_generation() ... time.sleep(1.0)` |

### Данные о времени (latency)

| Метрика | Значение | Статус |
|---|---|---|
| Queue wait time | N/A | Очередь не использовалась (LLM_RESILIENCE_V1 OFF) |
| Generation time | **НЕИЗВЕСТНО** | D1: `latency: 0.0` на всех audit-записях — поле не заполняется |
| Total latency | **НЕИЗВЕСТНО** | D1 блокирует измерение |
| Concurrent LLM requests | **НЕИЗВЕСТНО** | Audit не записывает конкурентность |
| Number of competitive calls | **НЕИЗВЕСТНО** | D2: `npc_id="npc"` (generic) — невозможно отследить конкретного NPC |

### Распределение DIALOGUE entries по тикам (B4 range)

Из Phase 3 [F] (`enigma_audit.jsonl`, `Capability.DIALOGUE`):

| Tick | DIALOGUE entries | Примечание |
|---:|---:|---|
| 5 | 77 | B4 tick 5 (talk success per TZ) — includes LLM calls for guard_borko, blacksmith_orm, verifier, possibly Торнин's talk |
| 7 | 31 | B4 tick 7 (spread_rumor fallback) — **NONE mention Торнин** |
| 10 | 45 | B4 tick 10 (spread_rumor fallback) — **NONE mention Торнин** |
| 12 | 19 | B4 tick 12 (spread_rumor fallback) — **NONE mention Торнин** |

Entries на ticks 7/10/12 существуют (для других NPC), но **ни одна** не упоминает `Торнин` / `тавернщик` в `prompt_preview`. Это **прямое доказательство**: LLM-вызовы для Торнина на этих тиках не происходили.

### Заключение по очереди

**Очередь НЕ ПРИЧАСТНА к fallback.** Fallback происходит на `dialogue_executor.py:149`, **до** любого обращения к ModelRouter. Даже если бы `LLM_RESILIENCE_V1=ON`, это не изменило бы результат — LLM-вызов просто не происходит.

Постулат ТЗ §1 «Используется IntelligenceQueue (ADR-O-382)» **не подтверждается кодом** для production-конфигурации по умолчанию. Очередь определена (`intelligence_queue.py:104`), wired в `game_loop.py:485-488`, но **не активируется** без env-флага. Это **отдельный дефект конфигурации**, не причина B4 fallback.

---

## Раздел 5. Причина fallback

### ДОКАЗАНО (прямым кодом / логами)

| # | Утверждение | Доказательство |
|---|---|---|
| **P1** | Fallback template `[Intent.SPREAD_RUMOR] ... -> ... : наблюдение` emit'ится из `dialogue_executor.py:149` | Прямой код: `text = f"[{req.intent_type}] {task.owner_id} -> {req.target_id}: {req.topic}"` |
| **P2** | Условие активации: `not requires_llm_materialization("spread_rumor") AND not (spread_rumor AND proposition is not None)` | `dialogue_executor.py:145-146` |
| **P3** | `requires_llm_materialization("spread_rumor") == False` | **Логически необходимо**: fallback произошёл (audit-лог содержит template string в downstream dialogue_extractor prompt) → `elif` сработал → условие `True` → `requires_llm_materialization` должно быть `False`. Функция: `intent_profiles.py:31-32` — `return bool(INTENT_PROFILES.get(intent_type, {}).get("requires_llm", True))`. Прямое чтение `INTENT_PROFILES` dict не выполнено (см. Эксперимент E1), но логическая необходимость однозначна. |
| **P4** | `proposition == None` для B4 spread_rumor вызовов | `decision_hub.py:350` — `_proposition = None` default; устанавливается только из `epistemic_context.trigger_proposition` (стр. 352) или `report_proposition` (стр. 355). Если epistemic_context не имеет trigger/report proposition → `_proposition` остаётся `None`. |
| **P5** | LLM-вызов НЕ происходил для B4 spread_rumor | Phase 3 [E]: audit-лог ticks 5-15, `Capability.DIALOGUE` entries — для `guard_borko`, `blacksmith_orm`, `verifier`, **но НЕ для Торнина**. Если бы LLM-вызов произошёл, была бы создана audit-запись с `"Ты — тавернщик Торнин"` в `prompt_preview`. |
| **P6** | IntelligenceQueue не использовалась | `LLM_RESILIENCE_V1` OFF в `.env` и `config.py` (Phase 2.5 [G]); `router.py:842` — queue path skipped |
| **P7** | `talk` (tick 5) прошёл через LLM | Phase 3 [F]: audit tick 5 — 77 DIALOGUE entries; TZ подтверждает LLM-generated speech. `requires_llm_materialization("talk")` default `True` → `else` branch → LLM call. |

### ВЫСОКАЯ ВЕРОЯТНОСТЬ

| # | Утверждение | Доказательство |
|---|---|---|
| **H1** | B4 spread_rumor вызовы не имели epistemic trigger (поэтому `proposition == None`) | P4 + P5: `proposition=None` (нет epistemic trigger) → template fallback → нет audit entry. Косвенное подтверждение: audit-лог не содержит DIALOGUE entries для Торнина на ticks 7/10/12. |

### ГИПОТЕЗА

| # | Утверждение | Missing |
|---|---|---|
| **H2** | `INTENT_PROFILES["spread_rumor"]["requires_llm"]` явно установлен в `False` | Прямое чтение dict не выполнено. Логически выведено из P1-P3. **Эксперимент E1** подтвердит. |
| **H3** | Epistemic triggers для spread_rumor в B4 не были сгенерированы из-за отсутствия соответствующих events/perceptions | Не проверялось. Требует анализа `epistemic_context_resolver.py` для B4 ticks. |

### НЕИЗВЕСТНО

| # | Утверждение | Причина |
|---|---|---|
| **U1** | Реальная latency LLM-вызовов в B4 | D1: `latency: 0.0` на всех audit-записях |
| **U2** | Были ли конкурентные LLM-вызовы, которые могли бы перегрузить llama-server | Audit не записывает конкурентность; D1 блокирует timeline reconstruction |
| **U3** | Точное значение `INTENT_PROFILES["spread_rumor"]` | Прямое чтение не выполнено (H2). Эксперимент E1 закроет. |
| **U4** | Содержал ли epistemic_context для Торнина какие-либо trigger_proposition на B4 ticks 7/10/12 | Audit не записывает epistemic_context; требует instrumentation |

### Реестр дефектов наблюдаемости

| D# | Дефект | Доказательство | Влияние на расследование |
|---|---|---|---|
| **D1** | `latency: 0.0` на всех audit-записях | Phase 1 pasted tail: все ~200 строк имеют `"latency": 0.0` | Блокирует измерение времени ожидания/генерации (Раздел 4) |
| **D2** | `npc_id` для DIALOGUE entries = `"npc"` (generic), не speaker ID | Phase 2 [D]: `npc=npc` на всех DIALOGUE entries | Блокирует связывание audit-записи с конкретным NPC |
| **D3** | `intent_before` / `intent_after` NEVER populated | Phase 1 [F]: 0 записей с `SPREAD_RUMOR`; в хвосте все `null` | Блокирует фильтрацию audit по intent |
| **D4** | `llm_output` entries не содержат `capability` | Phase 1 [D]: `17352 llm_output\|` (пусто после `\|`) | Блокирует сопоставление input/output по capability |
| **D6** | `npc_id="npc"` specifically for `Capability.DIALOGUE` | Phase 2 [D] | Подтверждает D2 для speech gen |
| **D7** | Template-fallback calls (`dialogue_executor.py:149`) НЕ создают audit entries | By design: LLM не вызывается → нет input/output пары → нет audit entry | Fallback-вызовы **невидимы** в audit. Не баг аудита, а следствие архитектуры материализации. |

**D5 (tick_id not populated) — ОПРОВЕРГНУТО:** Phase 3 [F] показал корректное заполнение `tick_id` (распределение 0-500+).

### Главный принцип (из ТЗ §7)

> «Мы не хотим заставить Торнина говорить красивее или чаще. Мы хотим, чтобы существующий механизм генерации речи надёжно работал для разных намерений NPC.»

**Техническое препятствие найдено:** `spread_rumor` без `proposition` **по дизайну** не использует LLM. Это не сбой — это архитектурное решение S199.2. Но оно означает, что `spread_rumor` без epistemic trigger **не может** производить естественную речь — только детерминированный шаблон.

---

## Раздел 6. Предложения по исправлению

**Не реализовано (ТЗ §4: «Не реализовывай предложения»).** Три варианта, упорядоченные по риску регрессии.

### Вариант 1: Добавить observability для template-fallback вызовов (НИЗКИЙ риск)

**Затрагиваемые файлы:**
- `backend/app/services/execution/dialogue_executor.py` (around line 149)
- Модуль audit-логирования (где определяется схема audit entry)

**Что меняется:** При выборе template fallback (стр. 149), писать audit entry:
```python
# (концептуальный набросок, НЕ патч)
{
    "level": "INFO",
    "agent": "template_fallback",
    "tick_id": <current_tick>,
    "npc_id": task.owner_id,          # speaker ID, не generic "npc"
    "intent_type": req.intent_type,
    "target_id": req.target_id,
    "topic": req.topic,
    "reason": "no_proposition" if req.intent_type == "spread_rumor" else "requires_llm_false",
    "latency": 0.0,
    "cache_hit": false
}
```

**Риск регрессии:** НИЗКИЙ. Только добавляет логирование, не меняет поведение. Не трогает production path.

**Тесты:**
- `test_audit_logs_template_fallback` — проверить, что fallback-вызовы теперь видны в audit
- `IPT.py` — убедиться, что новый audit entry type не ломает существующие инварианты
- `lint_silent_failures.py` — проверить, что нет нового silent failure

**Проверка результата:** После B4-подобного прогона, `enigma_audit.jsonl` должен содержать записи `agent=template_fallback` для ticks 7/10/12 с `npc_id=tavern_keeper_tornin`. Будущие расследования смогут напрямую идентифицировать fallback-вызовы без косвенных выводов.

### Вариант 2: Обеспечить epistemic_context всегда предоставляет proposition для spread_rumor (СРЕДНИЙ риск)

**Затрагиваемые файлы:**
- `backend/app/services/npc/epistemic_context_resolver.py` (стр. 139, 144, 200-205)
- Возможно `backend/app/services/npc/decision_hub.py:350-365`

**Что меняется:** Когда DecisionHub выбирает `spread_rumor`, `epistemic_context_resolver` должен гарантировать непустой `trigger_proposition` — производный от последнего значимого perception / memory event NPC.

**Риск регрессии:** СРЕДНИЙ. Меняется upstream предусловие, а не downstream материализация.
- Нужно определить, откуда брать proposition, если нет явного epistemic trigger
- Риск галлюцинированных propositions (если брать из слабого сигнала)
- Устав §ENIGMA-006: «target_reference для контекстного вывода» — proposition должен быть обоснован
- Устав §ENIGMA-003: «UNKNOWN ≠ NEUTRAL(0.0)» — нельзя фабриковать proposition из ничего

**Тесты:**
- `test_epistemic_context_resolver_spread_rumor_always_has_proposition`
- `test_decision_hub_spread_rumor_proposition_not_none`
- `test_dialogue_executor_spread_rumor_goes_to_llm_branch` (стр. 150-160 instead of 145-149)
- Семантический тест: propositions должны быть обоснованы (не галлюцинированы) — `verifier` LLM call
- `IPT.py` — INV-DIALOGUE-PIPELINE, INV-EPISTEMIC-TRUST-MONOTONICITY

**Проверка результата:** B4-подобный сценарий, проверить что:
- `enigma_audit.jsonl` содержит `Capability.DIALOGUE` entries с `Торнин` / `тавернщик` в `prompt_preview` для ticks 7/10/12
- NPC_SPOKE events содержат LLM-generated text, не template

### Вариант 3: Сделать spread_rumor всегда требующим LLM (ВЫСОКИЙ риск)

**Затрагиваемые файлы:**
- `backend/app/domain/intent_profiles.py` (`INTENT_PROFILES` dict)

**Что меняется:** Установить `INTENT_PROFILES["spread_rumor"]["requires_llm"] = True`.

**Риск регрессии:** ВЫСОКИЙ. `spread_rumor` без proposition сейчас детерминирован — это может быть осознанным дизайном (S199.2). Принудительный LLM-вызов для каждого spread_rumor:
- Увеличит нагрузку на llama-server в ~N раз (N = число spread_rumor событий за тик)
- Может вызвать timeout-каскады при конкурентных вызовах (особенно с `LLM_RESILIENCE_V1 OFF`)
- Изменит семантику: `spread_rumor` без proposition сейчас — это «признак намерения», а не «высказывание»
- Может нарушить Устав §7.20: «LLM в TickOrchestrator / DecisionHub» — нужно убедиться, что LLM вызов остаётся в `dialogue_executor` (Phase 6 post_decision), не мигрирует в Phase 5

**Тесты:**
- `test_dialogue_executor_spread_rumor_no_proposition_uses_llm`
- `test_dialogue_executor_spread_rumor_with_proposition` — регрессия существующего поведения
- Нагрузочный тест: 10 NPC × 5 spread_rumor/tick → проверить latency
- `IPT.py` — INV-DIALOGUE-PIPELINE, INV-LLM-EXILE
- A/B тест: B4-подобный сценарий до/после изменения

**Проверка результата:** Запустить B4-подобный сценарий, убедиться что `[Intent.SPREAD_RUMOR] ... : наблюдение` больше не появляется в репликах NPC.

### Рекомендация

**Вариант 1 (observability)** — наименьший риск, наибольшая польза для будущих расследований. Должен быть реализован **до** Вариантов 2/3, чтобы любые изменения в материализации можно было отслеживать.

**Вариант 2 (epistemic proposition)** — архитектурно более правильный: `spread_rumor` должен иметь что распространять (proposition). Но требует решения Мастера: откуда брать proposition, если нет явного epistemic trigger.

**Вариант 3 (всегда LLM)** — наиболее инвазивный, меняет семантику. Не рекомендуется без отдельного ADR и вердикта Мастера.

**Решение о реализации — после отдельного решения Мастера (ТЗ §4 п.7: «Исправлять fallback до установления причины» — причина установлена, теперь решение за Мастером).**

---

## Раздел 7. Следующий диагностический эксперимент

### Эксперимент E1: Прямое чтение INTENT_PROFILES dict (READ-ONLY, риск: NONE)

**Цель:** Подтвердить H2 / P3 — `INTENT_PROFILES["spread_rumor"]["requires_llm"] == False`.

**Команда:**
```powershell
& {
    $ErrorActionPreference = "Stop"
    Get-Content "backend/app/domain/intent_profiles.py" |
        Select-Object -Index (0..30) |
        ForEach-Object -Begin {$i=1} -Process {"$i`: $_"; $i++}
}
```

**Ожидаемый результат:** В dict `INTENT_PROFILES` найдётся запись для `"spread_rumor"` с `"requires_llm": False` (или отсутствие ключа `"requires_llm"` при `default True` — но тогда P3 опровергается).

**Если результат иной:**
- Если `"requires_llm": True` или запись отсутствует → P3 (логически выведенное) **опровергается** → причина fallback НЕ в `requires_llm_materialization` → нужно пересмотреть H1/H2 → пересмотреть весь Раздел 5.

**Риск:** NONE (read-only, никаких модификаций, никаких новых LLM-вызовов, никаких B4 повторов).

### Эксперимент E2 (опционально, требует разрешения Мастера): Print-диагностика в dialogue_executor

**Цель:** Подтвердить in-vivo, что B4-подобный прогон действительно проходит через `elif` на стр. 145.

**Метод:** Временный `print()` на `dialogue_executor.py` (вставляется до строки 149):
```python
# Временная диагностика, удалить после подтверждения
print(f"[DIAG_FB] template fallback chosen: intent={req.intent_type} prop={_proposition} npc={task.owner_id} target={req.target_id}")
```

**Требует:**
1. Разрешения Мастера на временную модификацию production-кода (даже временную)
2. Запуска B4-подобного сценария (ТЗ §4 п.8: «Запускать длительный повторный B4 без отдельного разрешения Мастера» — запрещено без разрешения)

**Не запускать без разрешения.**

**Ожидаемый вывод:** `[DIAG_FB] template fallback chosen: intent=spread_rumor prop=None npc=tavern_keeper_tornin target=maid_lusya` (или аналогично) для ticks 7/10/12.

### Эксперимент E3 (опционально, требует разрешения Мастера): Проверить epistemic_context для Торнина на B4 ticks

**Цель:** Подтвердить H1/H3 — epistemic_context для Торнина не имел trigger_proposition на B4 ticks 7/10/12.

**Метод:** Временный `print()` в `decision_hub.py` после строки 355:
```python
print(f"[DIAG_EP] npc={state.npc_id} intent={best_intent} prop={_proposition} trigger={epistemic_context.trigger_proposition} report={getattr(epistemic_context, 'report_proposition', None)}")
```

**Требует:** разрешения Мастера + запуск B4.

**Не запускать без разрешения.**

---

## Приложение A. Файлы и артефакты расследования

| Артефакт | Путь | Назначение |
|---|---|---|
| Audit log (source) | `C:\DDD\Codex\VSC_Enigma\Enigma\backend\data\logs\enigma_audit.jsonl` | LLM call audit trail (57493 entries) |
| Phase 1 discovery log | `C:\DDD\Codex\VSC_Enigma\Enigma\diagnostics\forensic_phase1_focus.log` | Intent enum, fallback emitter search, audit distinct values |
| Phase 2 code map log | `C:\DDD\Codex\VSC_Enigma\Enigma\diagnostics\forensic_phase2_code.log` | verbalization/llm class map, IntelligenceQueue refs, Capability.DIALOGUE entries |
| Phase 2.5 targeted reads log | `C:\DDD\Codex\VSC_Enigma\Enigma\diagnostics\forensic_phase2_5_code.log` | **BREAKTHROUGH**: dialogue_executor.py:145-149 condition, LLM_RESILIENCE_V1 OFF confirmation |
| Phase 3 root cause log | `C:\DDD\Codex\VSC_Enigma\Enigma\diagnostics\forensic_phase3_root_cause.log` | requires_llm_materialization function, proposition assignment, audit tick 5-15 distribution |

---

## Приложение B. Соответствие критериям завершения (ТЗ §6)

- [x] **Найден фактический путь успешной генерации `talk`**: `dialogue_executor.py:150-160` (else branch → `_generate_with_router`)
- [x] **Найден фактический путь трёх `spread_rumor` вызовов**: `dialogue_executor.py:145-149` (elif branch → template)
- [x] **Найден код формирования fallback**: `dialogue_executor.py:149` — `text = f"[{req.intent_type}] {task.owner_id} -> {req.target_id}: {req.topic}"`
- [x] **Установлены все возможные причины перехода на fallback**: 3 пути (stub `:144`, template `:149`, validation `response_validator.py:263`). B4 использовал template path.
- [x] **Выполнено сравнение успешного и неуспешного вызовов**: Раздел 3
- [x] **Причины разделены на доказанные и предполагаемые**: Раздел 5 (ДОКАЗАНО: P1-P7; ВЫСОКАЯ ВЕРОЯТНОСТЬ: H1; ГИПОТЕЗА: H2, H3; НЕИЗВЕСТНО: U1-U4)
- [x] **Предложен минимальный следующий эксперимент**: Раздел 7, Эксперимент E1 (READ-ONLY, риск NONE)
- [x] **Production-код остался неизменным**: READ-ONLY throughout; все команды — `Select-String`, `Get-Content`, `ConvertFrom-Json`; ни одной модификации кода, ни одного нового LLM-вызова, ни одного B4 повтора

---

## Приложение C. Главный принцип (ТЗ §7) — проверка соответствия

> «Мы не хотим заставить Торнина говорить красивее или чаще. Мы хотим, чтобы существующий механизм генерации речи надёжно работал для разных намерений NPC.»

**Соответствие:** Расследование нашло **техническое препятствие**, а не предлагало поведение за NPC.

> «Задача архитектора — найти техническое препятствие, а не придумывать за NPC поведение.»

**Найденное препятствие:** `spread_rumor` без `proposition` детерминированно материализуется шаблоном (S199.2). Это **архитектурное решение**, не сбой. LLM-генерация для `spread_rumor` происходит **только** при наличии `proposition` (исключение на `dialogue_executor.py:146`).

> «Сначала доказательства. Затем техническое решение. Реализация — только после отдельного решения Мастера.»

**Доказательства:** ДОКАЗАНО (P1-P7). **Техническое решение:** предложено 3 варианта (Раздел 6), не реализовано. **Реализация:** ждёт решения Мастера.

---

**Конец отчёта.**
