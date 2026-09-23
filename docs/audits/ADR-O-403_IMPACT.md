# ADR-O-403 Impact Audit — Campaign Lifecycle Ownership (Phase 3B)
> Атлас: docs/ADR (Architecture Decision Records).md | Ветка: V.0.5.4.1.2_Чистка_истоков
> Коммиты: 5e73199e (Seam1), [Seam2-6], 666106a9 (каркас), ebc6793f (шаг2), fb15b57d (шаг3-final)

## Changed Domains
- Новый владелец: game_loop/campaign_lifecycle.py — «как кампания создаётся/сбрасывается/загружается/мигрирует» (reset_campaign 12 шагов 1-в-1, load_campaign, resolve_world_id, record/get_diff, diff-IO)
- Расформирован campaign_mgmt.py (ITER5): campaign-функции → Lifecycle; assert_requirements/_get_character_dict возвращены в GameLoop (не campaign-домен)
- Seam-волна 3B.0 (6 итераций): SSM.reset_campaign_persistence, RelationshipStore.reset_campaign (+RAM-кэш у владельца — фикс протухшего _load), MemoryManager.reset_campaign_state, TemporalEngine.reset_campaign (+tick=0/unlink у владельца), PlayerAvatarService.reset_campaign (+исправлен DOUBLE TRUTH пути аватара: new_game удалял файл по чужому _saves_dir-пути, настоящий переживал new_game), LifeEngine.clear_runtime_caches
- routes.py: record_campaign_diff — публичный seam вместо прямой записи в _campaign_diffs

## Downstream Consumers
- Поверхность сохранена: GameLoop.new_game/load_campaign/session_state — фасады; routes/harness/тесты не меняли импорты (кроме routes:682-683 seam)
- Double-file bridge _preserved_tick (GameLoop↔scene_init) — задокументирован, остаётся GameLoop-owned

## Runtime Impact
- Поведение неизменно: IPT 45/45 на каждой итерации; этапные реплеи fedafcca MATCH; pytest r4+pipeline 16+1
- game_loop.py: 2902 → 1946 (−33%); campaign_lifecycle.py ~340; campaign_mgmt.py удалён
- Найден и устранён runtime-bug: DOUBLE TRUTH пути player_avatar.json (существовал всегда)

## Sandbox Tests
- функциональный тест reset_campaign (tmp-каталог: нет файла/есть/journal), tests/test_spatial_runtime_r4.py, tests/IPT.py, DriftLab replay_determinism

## Rollback
- git revert fb15b57d + восстановление campaign_mgmt из истории; seam-ы независимы и откатываются по одному

## Taboo
- ❌ game_loop как параметр Lifecycle; ❌ CampaignManager/Services-контейнер; ❌ изменение порядка reset 1→12; ❌ касание EPOCH-FINAL; ❌ session_state/_session_started_campaigns/_current_campaign_id → в Lifecycle (это session/turn-домен GameLoop); ❌ смешение seam- и extraction-коммитов
