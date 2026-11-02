# Live audit: blacksmith_orm

- Pipeline: HTTP → uvicorn → qwen_7b (temperature=0.9)
- Campaign: silver_wolf_audit_live (изолированная, оригиналы не тронуты)
- Total fragments: 22 (включая шапку)
- Real points: 21
- Total items produced: 62
- Zero-items points: 0
- HTTP failures: 0
- Coverage warnings (critical topic + 0 items): 0

## Per-point breakdown

| point | frag | chars | items | kinds | warn |
|-------|------|-------|-------|-------|------|
| HDR | 0 | 16+ | 1 | TRAIT_SEED |  |
| #1 | 1 | 53+ | 1 | EVENT |  |
| #2 | 2 | 57+ | 2 | TRAIT_SEED, TRAIT_SEED |  |
| #3 | 3 | 88+ | 1 | RELATIONSHIP |  |
| #4 | 4 | 120+ | 6 | EVENT, RELATIONSHIP, EVENT, RELATIONSHIP, RELATIONSHIP, EVENT |  |
| #5 | 5 | 120+ | 3 | TRAIT_SEED, RELATIONSHIP, EVENT |  |
| #6 | 6 | 82+ | 1 | EVENT |  |
| #7 | 7 | 120+ | 2 | EVENT, TRAIT_SEED |  |
| #8 | 8 | 120+ | 2 | PORTRET, RELATIONSHIP |  |
| #9 | 9 | 120+ | 2 | PORTRET, RELATIONSHIP |  |
| #10 | 10 | 120+ | 2 | RELATIONSHIP, TRAIT_SEED |  |
| #11 | 11 | 120+ | 1 | RELATIONSHIP |  |
| #12 | 12 | 120+ | 6 | TRAIT_SEED, EVENT, TRAIT_SEED, TRAIT_SEED, TRAIT_SEED, PORTRET |  |
| #13 | 13 | 120+ | 1 | PORTRET |  |
| #14 | 14 | 120+ | 2 | DESIRE_SEED, TRAIT_SEED |  |
| #15 | 15 | 120+ | 1 | PORTRET |  |
| #16 | 16 | 120+ | 6 | EVENT, RELATIONSHIP, EVENT, EVENT, EFFECT, PORTRET |  |
| #17 | 17 | 120+ | 7 | RELATIONSHIP, PORTRET, TRAIT_SEED, PORTRET, TRAIT_SEED, RELATIONSHIP, TRAIT_SEED |  |
| #18 | 18 | 120+ | 4 | LOCATION, RELATIONSHIP, PORTRET, DESIRE_SEED |  |
| #19 | 19 | 120+ | 6 | RELATIONSHIP, TRAIT_SEED, TRAIT_SEED, RELATIONSHIP, TRAIT_SEED, RELATIONSHIP |  |
| #20 | 20 | 120+ | 2 | PORTRET, RELATIONSHIP |  |
| #21 | 21 | 120+ | 3 | EFFECT, TRAIT_SEED, TRAIT_SEED |  |