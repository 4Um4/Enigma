# ADR-O-423 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

ADR-O-423 [STANDARD] **IMPACT** (S341; CCH-4 — Chronicle Seeder)

## Changed Domains
- authoring: chronicle_seeder (pure translator, вне тик-пайплайна)
- npc loading: npc_loader — new-game-гейт + 4 функции-обвязки (_chronicle_seed_memories_for, _apply_chronicle_seed_to_dict, _enrich_with_chronicle_relations, приоритет в ветке памяти)
- enforcement: ценз ADR-O-415 (npc_loader 8→12, +chronicle_seeder.py=1; 20 файлов / 57 сайтов)
- НЕ затронуты: тик-пайплайн, EventBus, RelationshipStateStore/V2-бэкенд, StateApplicator, цензусы BeliefState/NPCState (расширений нет)

## Downstream Consumers
- Сеялка получает согласованный канон (карточки CCH-3 разрешены до seed — ADR-O-422)
- V2-подъёмник (v2_relationship_backend.bootstrap_from_npc_dicts) поднимает chronicle-связи из enrichment-формата без изменений (числа из valence; chronicle_origin отфильтровывается контрактом _LEGACY_SCALARS)
- decay_affective_imprints (idle_services) затухает seed-импринты: decay_rate=0 → вечные (контракт носителя)
- Character Calibration (будущий ADR): TRAIT_SEED ждёт его как единственного писателя стартовых черт
- Сводка убеждений (CCH-4-экспорт): unknown-type BELIEF_SEED остаются в каноне — экспорт собирает их для вердикта владельца

## Runtime Impact
- RAM: канон-кэш (mtime-инвалидация) — единовременно ~размер канонов; загрузчик при new-game — O(записей)
- Tick Latency: 0 (сеялка вне тика; new-game-гейт = один dict.get на NPC при резюме)
- Детерминизм: seed без wall-clock/random; T-CCH-05-микро (два прогона ==)

## Sandbox Tests
- backend/tests/micro/test_chronicle_cch4_seed.py — 12/12: детерминизм ×2; Марк-изоляция (знание в хронике владельца, day знающего, hidden_from player); future-age SeederError; SENTINEL_DAY; trauma без triggers → нет импринта; trauma с triggers → ровно поля AffectiveImprint(**imp) без лишних; реестр BeliefType закрыт; valence→числа+chronicle_origin; гейт new-game сеет / resume закрыт / без канона legacy цел
- Ценз: python scripts/lint_relationship_cache_allowlist.py (57/20 GREEN)
- Границы: T-CCH-07 (резонанс «звон кружки» → avoidance) — интеграционный, на живой кампании с авторскими triggers; T-CCH-08 (Debugger) — этап E

## Rollback
- git revert коммита; ценз-запись откатывается тем же коммитом (замена не независима)
- Каноны config/npc/chronicles/ сегодня отсутствуют (пусто) → откат бесследен
- Legacy-путь не изменён (тест legacy-intact) → откат = возврат к байт-идентичному поведению при отсутствии канонов
