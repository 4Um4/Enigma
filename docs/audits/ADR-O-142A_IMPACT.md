# ADR-O-142A Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-O-142A` [STANDARD] **IMPACT**
# ADR-O-142A Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- DOM-02 (Will, Pressure & Decision) — Arousal Gate внутри LifeEngine
- DOM-04 (Spatial & Locomotion) — SceneChange pipeline для activity
- DOM-03 (Perception & Phenomenology) — scene_state.activity влияет на perception_filter

## Downstream Consumers
- `perception_filter._npc_is_conscious()` — читает scene_state.activity, теперь получает корректные данные
- `reaction_priority` — проверяет sleeping/unconscious, теперь NPC корректно переходит в idle
- `attention_layer` / `interpretation_layer` — читают activity для когнитивного pipeline игрока
- `scene_state_manager.apply_changes()` — применяет SceneChange(field="activity")
- `_enrich_local_positions` — читает activity при enrichment

## Runtime Impact
- RAM: +0 (нет новых SSOT)
- Tick Latency: +1 мс на sleeping NPC (вычисление wake_pressure)
- При ~5 sleeping NPC per location: незаметно

## Sandbox Tests
- `tests/sandbox/micro/test_arousal_gate.py` — 17 тестов:
  - TestArousalGateWakeScenarios (3): threat, pain, combined
  - TestArousalGateSleepScenarios (2): no stimuli, low threat
  - TestArousalGateGuardConditions (5): working, idle, initiative_suppression, attention_capture
  - TestArousalGateSceneChanges (4): activity, visible, routine clear, no mutation on sleep
  - TestArousalGateResting (1): resting wakes
  - TestArousalGateBoundary (2): exact equality, initiative_suppression=0.7
  - TestArousalGateMSOC (2): scale normalization, pain+threat vs fatigue

## Rollback
1. Удалить вызовы `self._arousal_gate()` из `_simulate_major` и `_simulate_minor`
2. Удалить метод `_arousal_gate` из LifeEngine
3. Удалить `test_arousal_gate.py`
4. Восстановить `@staticmethod` на `_compute_viability_mask` если был потерян
5. Очистить `__pycache__`

## Architectural Notes
- Arousal Gate = behavior transition gate, НЕ consciousness transition
- "awake" НЕ введён как состояние мира — только transition trigger
- body_state["consciousness"] не затронут (физиологическая ось)
- SceneChange pipeline используется как есть (без изменений)
- ChangeValidator не изменён (уже пропускает NPC_POSITION с любым field)
- apply_change() не изменён (generic setter entry[change.field] = change.value)

## TODO (ADR-O-142B candidate)
Сейчас initiative_suppression, attention_capture, viability_mask — три независимых veto.
В будущем рассмотреть единый Behavioral Inhibition Layer для всех блокировок поведения.
Не проектировать. Не реализовывать. Только якорь.
