# ADR-O-416 Impact Audit (S320, RE-01 GC-11)
`ADR-O-416` [ONTO] **GC-11 L3-gate — RED=находка: event→V2 доказан живьём, поведенческий ноль = RE-D2 выборка 5**
Files: backend/tests/sandbox/lab_r003_gc11_causal_delta.py, backend/tests/sandbox/lab_r003_diff_analysis.py, docs/audits/ADR-O-416_IMPACT.md
> L3-gate «event → V2-RAM non-zero delta → следующий выбор NPC сдвинут» — исполнен живым harness; RED = находка (прецедент GC-09B). Атлас: docs/ADR (Architecture Decision Records).md.

## Что доказано (живой протокол reports/lab_r003_gc11_results.json)
- L1 ✅: HELP(player→merchant_goran) через production-мост (ScenarioPlayer → idle_tick(interventions) → _process_player_action → ActionConsequenceCompiler HELP-ветка → RelationshipWriteGate → V2-RAM) даёт store delta trust 0→20.0 / fear −10 на тике 5; контроль (тот же MOVE-only сценарий без HELP) — 0.0. Санити: тики 1–4 A≡B; детерминизм B≡B2 (полные мировые таймлайны).
- L3 ❌: полный dict merchant_goran идентичен A/B все 30 тиков (post-hoc дифф lab_r003_diff_analysis.py) — RE-D2-класс нулевой игровой реальности подтверждён живым прогоном (выборка 5 Consumer Gap: после RE-D2-отношений, GC-09B-тела, NL-D9-energy, RE-D9-BehaviorMask).

## Анатомия разрыва (3 шва, адреса точные)
- S1 Dual-Reader Divergence: V2 потребляется двумя неэквивалентными каналами. (а) pipeline-канал жив: memory_weights_map ← memory_manager._relationships (Т ОТ ЖЕ инстанс, что game_loop._rel_store: game_loop.py:148/268, memory_manager.py:88) → state_l2.relationship_cache (TZ-10) → bias/BehaviorMask-читатели видят дельту. (б) raw-dict-канал слеп: directive_interpretation_subscriber:107/132 читает npc_dict["relationship_cache"], который gate-путь НЕ гидратирует (гидратацию делает только StateApplicator.update_relationships; WriteGate.apply её не выполняет — relationship_write_gate.py:62-107).
- S2 Threshold Inertia: все пороги читателей отрицательные/экстремальные: bias trust < −30.0 (constants.py:61), BehaviorMask fear>60∧trust<0 / trust<−50 (phases/decision.py:205-222; выход — мёртвый канал RE-D9). HELP +20/−10 не пересекает ни одного. BLACKMAIL = −30 мимо строгого <, требует secret_id.
- S3 Silent-World: 30 idle-тиков — все интенты exploration/routine/shelter; нет player-направленного выбора, выражающего trust-дифференциал в utility.

## Следствие для очереди
- M2/D (RelationshipEventSemantics) получил точную цель: write-путь события + ПОТРЕБИТЕЛИ; сжатие разрыва S1 = либо re-гидратация raw-dict после gate-записей (кандидат: единый store→raw re-projection), либо перевод raw-dict-читателей на store-канал (миграция, класс M1b.3.7-allowlist-сжатия).
- Директивный подписчик = второй источник потребления отношений (raw dict) — кандидат в allowlist-пересмотр (ценз, не самовольная правка).

## Sandbox Tests
- backend/tests/sandbox/lab_r003_gc11_causal_delta.py (A/B/B2, Закон XI: ноль monkey-patch; приватные атрибуты — прецедент _apply_initial_social) + config/calibration/scenarios/gc11_move_only.yaml, gc11_help_move.yaml + backend/tests/sandbox/lab_r003_diff_analysis.py (post-hoc дифф).

## Rollback
- Лаборатория/сценарии автономны; удаление файлов ничего в рантайме не меняет (behavior-neutral).

## Границы
- GAP-1C / GAP-4 / RE-D9 / α-design-question не решались. L2-канал state_l2 доказан КОДОМ (тот же инстанс + TZ-10 + безусловная гидратация M1b.3.4), рантайм-зондом не подтверждён — помечено честно.
