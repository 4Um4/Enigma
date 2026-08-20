# ADR-O-146 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-O-146` [STANDARD] **IMPACT**
# ADR-O-146 Impact Audit: Personality Math Layer (Causal Geometry of Character)
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- DOM-02 (Will, Pressure & Decision) — SocialDeltaEngine заменяет инлайн _compute_deltas
- DOM-02 — perceive_risk() заменяет self._compute_risk()
- DOM-09 (Social & Affective Architecture) — RelationshipResponseProfile модулирует социальные дельты

## Downstream Consumers
- DecisionHub._score_components — использует perceive_risk() вместо self._compute_risk()
- DecisionHub._compute_deltas — делегирует SocialDeltaEngine.process()
- StateApplicator — применяет SOCIAL дельты (формат не изменился)
- _relationship_modifier — не затронут (читает relationship_cache как раньше)
- _context_relevance — не затронут (уже использует drives_base)

## Runtime Impact
- RAM: +3KB (5 новых модулей ~480 строк, profile создается per-call, GC сразу)
- Tick Latency: +0.02ms (profile construction + perceive_risk call)
- Distribution shift: при нейтральных drives (0.25) результат идентичен старому коду
- При не-нейтральных drives: дельты модулированы, риск модулирован

## Bug Fixes
- player_threatens: два последовательных блока перезаписывали друг друга → объединено в _BASE_DELTAS (-11.0, +6.5)

## New Files
| Файл | Назначение |
|------|-----------|
| decision/profile_math.py | Аттрактор + нелинейность + нормализация |
| decision/relationship_profile.py | Модуляция соц. дельт личностью |
| decision/social_deltas.py | P1: Фабрика социальных следов |
| decision/risk_profile.py | Модуляция восприятия риска |
| decision/risk.py | P2: Объективный риск + perceive_risk() |

## Sandbox Tests
- `tests/sandbox/micro/test_social_delta_personalization.py` (20 тестов)
  - TestDriveMultiplier (3): инвариант 0.25→1.0, аттрактор, нелинейность
  - TestProfileFromDrives (4): нейтральность, coward, brave, zealot
  - TestSocialDeltaNeutrality (4): обратная совместимость при neutral drives
  - TestSocialDeltaPersonalization (4): coward/zealot/brave/desire
  - TestThreatensBugFix (2): объединённый блок
  - TestModulationFunctions (3): граничные случаи

## Key Invariants
1. drive=0.25 → multiplier=1.0 (обратная совместимость)
2. Симплекс: 93% free range (аттрактор не душит разнообразие)
3. desire НЕ входит в RiskPerceptionProfile (риск ≠ готовность рисковать)
4. fear и control — независимые модификаторы (не ratio-модель)
5. profile_math — единственный источник drive_multiplier (изоляция доменов)

## Rollback
1. В decision_hub.py: заменить `perceive_risk(event, state, personality.drives_base)` на `self._compute_risk(event, state)`
2. В decision_hub.py: заменить `self._social_delta_engine.process(...)` на оригинальное тело _compute_deltas
3. Удалить 5 файлов в decision/
4. Удалить `from app.services.npc.decision.social_deltas import SocialDeltaEngine`
5. Удалить `from app.services.npc.decision.risk import perceive_risk`

## Technical Debt
- R2-P3: Physical State Personalization (HP/bleeding/stunned — плоские числа)
- R2-P4: DecisionHub Decomposition (1574 строки → пакет модулей)
- R2-TODO: Замена ratio-модели на независимые модификаторы (fear=0.6 + control=0.6 = neutral — параноик-тактик неразличим)
- R2-TODO: Замена линейной модели на S-кривую (экстремумы упираются в clamp)
- Identity Drift System: характер статичен во времени, нет пороговых переломов


Files: N/A
