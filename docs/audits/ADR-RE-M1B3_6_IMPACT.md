# ADR-RE-M1b.3.6 Impact Audit (S318)
> Stub-аудит долговой зачистки (прецедент S315 ADR-NET-PARSER-V2). Единый атлас: docs/ADR (Architecture Decision Records).md.
## Changed Domains
- RE-01 decision-readers: удалены мёртвые пути чтения отношений (S135-статик AgentAction._get_rel_value; дубликат DecisionHub._compute_risk + _THREAT_MARKER_VALUES; Scalar-ветка social_deltas._get_rel_value). Контракт Precedence сжат: Graph > Vacuum (плоских прод-писателей не существует — grep-доказательство).
## Downstream Consumers
- M1b.3.7 греп-страж allowlist (вход = читатель-карта S318); risk.compute_objective_risk — единственный risk-источник (прод-вызов DecisionHub._score_components).
## Runtime Impact
- Нулевой: F5 R001 behavior-neutral (артефакт = baseline; A/B/C/A2, 30×ok); удаление dead-веток, live-пути не изменены.
## Sandbox Tests
- tests/sandbox/micro/test_flee_collapse_fix.py 8/8 (миграция на канон compute_objective_risk); tests/micro/test_gap1_bias_differential.py 3/3; RE-сьют 205; IPT 50/50.
## Rollback
- git revert 9c282746: три удаления независимы, конфликтов смежности нет.