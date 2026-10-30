# Live audit: blacksmith_orm

- Pipeline: HTTP → uvicorn → qwen_7b (temperature=0.9)
- Campaign: silver_wolf_audit_live (изолированная, оригиналы не тронуты)
- Total fragments: 22 (включая шапку)
- Real points: 21
- Total items produced: 54
- Zero-items points: 1
- HTTP failures: 2
- Coverage warnings (critical topic + 0 items): 0

## Per-point breakdown

| point | frag | chars | items | kinds | warn |
|-------|------|-------|-------|-------|------|
| HDR | 0 | 16+ | 0 | — |  |
| #1 | 1 | 53+ | 4 | EVENT, RELATIONSHIP, EFFECT, EFFECT |  |
| #2 | 2 | 57+ | 1 | TRAIT_SEED |  |
| #3 | 3 | 88+ | 3 | RELATIONSHIP, EVENT, PORTRET |  |
| #4 | 4 | 120+ | 5 | EVENT, RELATIONSHIP, RELATIONSHIP, TRAIT_SEED, TRAIT_SEED |  |
| #5 | 5 | 120+ | 4 | PORTRET, EVENT, RELATIONSHIP, EFFECT |  |
| #6 | 6 | 82+ | 1 | EVENT |  |
| #7 | 7 | 120+ | 3 | EVENT, EFFECT, EFFECT |  |
| #8 | 8 | 120+ | 1 | PORTRET |  |
| #9 | 9 | 120+ | 0 | — |  |
| #10 | 10 | 120+ | 2 | RELATIONSHIP, PORTRET |  |
| #11 | 11 | 120+ | 1 | PORTRET |  |
| #12 | 12 | 120+ | 4 | EVENT, BELIEF_SEED, TRAIT_SEED, PORTRET |  |
| #13 | 13 | 120+ | 1 | PORTRET |  |
| #14 | 14 | 120+ | 1 | PORTRET |  |
| #15 | 15 | 120+ | 4 | PORTRET, RELATIONSHIP, RELATIONSHIP, TRAIT_SEED |  |
| #16 | 16 | 120+ | 4 | PORTRET, RELATIONSHIP, EVENT, BELIEF_SEED |  |
| #17 | 17 | 120+ | 5 | PORTRET, RELATIONSHIP, RELATIONSHIP, TRAIT_SEED, TRAIT_SEED |  |
| #18 | 18 | 120+ | 2 | PORTRET, DESIRE_SEED |  |
| #19 | 19 | 120+ | 3 | PORTRET, RELATIONSHIP, RELATIONSHIP |  |
| #20 | 20 | 120+ | 3 | PORTRET, RELATIONSHIP, LOCATION |  |
| #21 | 21 | 120+ | 2 | PORTRET, EVENT |  |