# ADR-O-212 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs\Tasks\ADR (Architecture Decision Records).md`

## Changed Domains
- DOM-02: Will, Pressure & Decision (DecisionHub получает bias от InstitutionLayer)
- DOM-06: Social & Memory (Введены VillageMemoryField, SocialMemoryUpdater, InstitutionLayer)
- DOM-04: Spatial & Locomotion (LifeEngine исполняет патрули на основе InstitutionLayer)

## Downstream Consumers
- **DecisionHub:** Читает `InstitutionLayer.curfew_level` и `patrol_density` для модуляции `effective_risk`.
- **LifeEngine:** Читает `InstitutionLayer.patrol_density` для генерации intents патрулирования у NPC.
- **SocialMemoryUpdater:** Пишет в `VillageMemoryField` при наступлении событий (COMBAT, DEATH).

## Runtime Impact
- **RAM:** Увеличение на ~2-5 KB на локацию (хранение VillageMemoryField и InstitutionLayer state).
- **Latency:** O(1) для SocialMemoryUpdater.ingest. O(1) для InstitutionalInertia фильтра в тике. Нагрузка минимальна.

## Sandbox Tests
- `tests/sandbox/social/test_institutional_inertia.py` — Проверка, что 3 убийства не поднимают `curfew_level` выше 0.2 при `adaptation_rate=0.05`.
- `tests/sandbox/social/test_village_memory_field.py` — Проверка, что `consensus_risk` растёт при `witness_count > 0` и затухает со временем.

## Rollback
1. Деградация инерции: установить `adaptation_rate = 1.0`, `resistance_to_change = 0.0` (мир возвращается к мгновенным реакциям).
2. Отключение социальной памяти: прекратить вызов `SocialMemoryUpdater.ingest()`. InstitutionLayer замёрзнет в текущем состоянии.
3. Полный откат: удалить чтение `InstitutionLayer` из DecisionHub и LifeEngine.