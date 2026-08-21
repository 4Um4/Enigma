# ADR-147 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-147` [STANDARD] **IMPACT**
# ADR-147 Impact Audit
> LLM Streaming Observability Gate — CDS видит ВСЕ LLM-вызовы

## Root Cause
Streaming path (`dm_agent._stream_response()` → `provider.stream_tokens()`) обходил `ModelRouter` → 0 маркеров `[R4A_POOL]`/`[R4A_WORKER]` → CDS слеп → CVS=0.00.

## Changed Domains
- DOM-08: Observability (CDS)
- DOM-01: Foundation (Router as LLM authority)

## Downstream Consumers
- `DNAComputer._compute_cvs()` — теперь получает llm_calls от streaming path
- `ReportRenderer` — CVS метрика корректна
- `LAST_SESSION.md` — интерпретация CVS отражает реальность

## Files Changed
| Файл | Изменение |
|------|-----------|
| `backend/app/services/llm/router.py` | +2 метода: `notify_stream_start()`, `notify_stream_end()` |
| `backend/app/agents/dm_agent.py` | +3 инъекции: Router gate + char counter + notify_stream_end |
| `diagnostics/pattern_registry.py` | +2 паттерна: `llm_stream_call`, `llm_stream_response` |
| `diagnostics/causal_observer.py` | +2 dispatch блока для streaming маркеров |

## Files Created
| Файл | Назначение |
|------|-----------|
| `backend/tests/sandbox/micro/test_llm_streaming_observability.py` | 11 тестов (Router + Pattern + CDS) |

## Runtime Impact
- RAM: 0 (нет новых долгоживущих объектов)
- Latency: ~0.01ms на LLM-вызов (два `_root_logger.info` вызова)
- Tick: не затронут

## Sandbox Tests
- `test_llm_streaming_observability.py` — 11 тестов
- Регрессия: 205 passed (было 194)

## Rollback
1. Удалить `notify_stream_start/end` вызовы из `dm_agent.py`
2. Удалить 2 метода из `router.py`
3. Удалить 2 паттерна из `pattern_registry.py`
4. Удалить 2 dispatch блока из `causal_observer.py`
5. Удалить `test_llm_streaming_observability.py`

## Architectural Taboo (NEW)
- ❌ LLM-вызов в обход Router (прямой `provider.stream_tokens()` без `notify_stream_start/end`)
- ❌ Новый LLM path без `[R4A_*]` маркера
- ❌ CDS pattern_registry без покрытия нового LLM-маркера
