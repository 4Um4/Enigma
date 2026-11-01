# Live audit: blacksmith_orm

- Pipeline: HTTP → uvicorn → qwen_7b (temperature=0.9)
- Campaign: silver_wolf_audit_live (изолированная, оригиналы не тронуты)
- Total fragments: 22 (включая шапку)
- Real points: 21
- Total items produced: 57
- Zero-items points: 0
- HTTP failures: 0
- Coverage warnings (critical topic + 0 items): 0

## Per-point breakdown

| point | frag | chars | items | kinds | warn |
|-------|------|-------|-------|-------|------|
| HDR | 0 | 16+ | 1 | TRAIT_SEED |  |
| #1 | 1 | 53+ | 2 | EVENT, EVENT |  |
| #2 | 2 | 57+ | 2 | TRAIT_SEED, TRAIT_SEED |  |
| #3 | 3 | 88+ | 1 | RELATIONSHIP |  |
| #4 | 4 | 120+ | 4 | EVENT, RELATIONSHIP, RELATIONSHIP, TRAIT_SEED |  |
| #5 | 5 | 120+ | 3 | RELATIONSHIP, PORTRET, BELIEF_SEED |  |
| #6 | 6 | 82+ | 1 | EVENT |  |
| #7 | 7 | 120+ | 2 | EVENT, PORTRET |  |
| #8 | 8 | 120+ | 2 | PORTRET, RELATIONSHIP |  |
| #9 | 9 | 120+ | 2 | PORTRET, RELATIONSHIP |  |
| #10 | 10 | 120+ | 2 | RELATIONSHIP, TRAIT_SEED |  |
| #11 | 11 | 120+ | 1 | RELATIONSHIP |  |
| #12 | 12 | 120+ | 4 | PORTRET, TRAIT_SEED, RELATIONSHIP, EVENT |  |
| #13 | 13 | 120+ | 1 | PORTRET |  |
| #14 | 14 | 120+ | 2 | DESIRE_SEED, PORTRET |  |
| #15 | 15 | 120+ | 2 | PORTRET, BELIEF_SEED |  |
| #16 | 16 | 120+ | 8 | EVENT, PORTRET, EVENT, RELATIONSHIP, EVENT, RELATIONSHIP, PORTRET, DESIRE_SEED |  |
| #17 | 17 | 120+ | 3 | RELATIONSHIP, PORTRET, TRAIT_SEED |  |
| #18 | 18 | 120+ | 2 | PORTRET, TRAIT_SEED |  |
| #19 | 19 | 120+ | 4 | RELATIONSHIP, TRAIT_SEED, TRAIT_SEED, PORTRET |  |
| #20 | 20 | 120+ | 2 | PORTRET, RELATIONSHIP |  |
| #21 | 21 | 120+ | 6 | TRAIT_SEED, TRAIT_SEED, TRAIT_SEED, TRAIT_SEED, TRAIT_SEED, EVENT |  |