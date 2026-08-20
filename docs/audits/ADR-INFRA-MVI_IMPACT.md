# ADR-INFRA-MVI Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-INFRA-MVI` [STANDARD] **IMPACT**
# ADR-INFRA-MVI Impact Audit
> Этот файл — детальный аудит завершения Minimum Viable Infrastructure (MVI) из ТЗ ENIGMA_TZ_INFRASTRUCTURE.

## Changed Domains
- Testing (PBT)
- Observability (Causal Probes)
- Persistence/Replay (LLM Cache, Replay wiring)
- Tooling (ADR-Net Visualizer)

## Downstream Consumers
- ModelRouter: теперь использует ReplayStore для кэширования LLM-вызовов.
- ProbeRunner: ProbeContext расширен 	ick_mutation, effective_drives_map, хешами TickState.
- API Routes: добавлен /api/probes/dashboard.
- ADR CLI: добавлена команда isualize.

## Runtime Impact
- RAM: ProbeAlertManager хранит deque(maxlen=100) в памяти ( insignificat overhead).
- CPU/IO: TemporalIsolationProbe хеширует TickState (JSON dumps) каждый тик. Если latency вырастет, можно вынести в passive режим.

## Sandbox Tests
- ackend/tests/pbt/properties/test_inv_causal_provenance.py (PBT)
- ackend/tests/IPT.py (30/30 passed)

## Rollback
- Удалить wiring в game_loop/__init__.py и eplay_recorder.py.
- Вернуть CausalProvenanceProbe, HistoricalConstraintProbe, TemporalIsolationProbe к заглушкам.
- Удалить alidators.py, llm_cache.py, probe_alerts.py, dr_visualizer.py.



Files: N/A
