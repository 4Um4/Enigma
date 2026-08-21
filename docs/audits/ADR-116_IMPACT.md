# ADR-116 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-116` [STANDARD] **IMPACT**
# ADR-116 Impact Audit: Emotion Pipeline Integrity (emotion: 0.0 Fix)

## Changed Domains
- Emotion (EmotionTag, _emotion_from_str, EmotionPayload)
- Serialization (from_legacy, write_to_legacy, load_l2_state_from_runtime_dict)
- Affective (affective_load, PerceptualKernel, emotion_transition)
- Reaction (ReactionSubscriber emotion from stress)

## Downstream Consumers
- DecisionHub._emotion_modifier() — читает state.emotion для utility deformation
- VerbalizationContext — использует emotion для LLM prompt
- WorldSnapshotBuilder — не читает emotion напрямую (Rule X)
- PhenomenologyProjectionService — НЕ читает emotion (ADR-112, Rule X)

## Runtime Impact
- RAM: +0 (5 полей уже существовали в NPCState, просто не заполнялись)
- Tick Latency: +0.1ms (добавлены _emotion_from_str и _pk_from_dict в loader)
- VRAM: 0

## Sandbox Tests
- test_npc_state_roundtrip — from_legacy → write_to_legacy → from_legacy round-trip
- Smoke-test: load_l2_state_from_runtime_dict с emotion=fearful → NPCState.emotion=FEARFUL
- Smoke-test: panic → FEARFUL маппинг
- Smoke-test: default neutral
- Smoke-test: write_to_legacy round-trip
- Runtime: CDS лог подтверждает emotion=fearful/suspicious между тиками

## Rollback
1. Удалить 5 полей из load_l2_state_from_runtime_dict() конструктора
2. Удалить emotion/emotion_delta из write_to_legacy/from_legacy
3. Убрать _emotion_from_str() конвертацию в StateApplicator
4. Убрать sustaining check в _run_affective_pipeline
5. Убрать stress→emotion пороги в ReactionSubscriber
6. Вернуть perceiving_ids is not None проверку

## Files Changed
| File | Change | Lines |
|------|--------|-------|
| npc_state.py | write_to_legacy: +emotion, +emotion_delta | 708-711 |
| npc_state.py | from_legacy: +emotion, +emotion_delta via _emotion_from_str | 800-803 |
| npc_state.py | +_emotion_from_str() хелпер | 739-757 |
| npc_loader.py | load_l2_state_from_runtime_dict: +5 полей | 520-524 |
| npc_loader.py | +import _emotion_from_str, _pk_from_dict | 18 |
| state_applicator.py | _emotion_from_str() конвертация в _apply_deltas | 461-466 |
| tick_orchestrator.py | psyche path: drives instead of drives_base | ~1834 |
| tick_orchestrator.py | sustaining emotion check | ~1864-1877 |
| reaction_subscriber.py | perceiving_ids fallback | if perceiving_list: |
| reaction_subscriber.py | stress→emotion thresholds | stress_delta>=15→fear, >=8→anxious |
| game_loop/__init__.py | удалён дублирующий update_cache | 229-233 |
