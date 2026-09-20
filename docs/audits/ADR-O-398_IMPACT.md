# ADR-O-398 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`
> Сессия: S269 | Дата: 2026-09-20

## Changed Domains
- **Temporal Epoch (world_epoch.py):** seal-семантика чтения (ReadOnlyDict/ReadOnlyList + кэш на эпоху в WorldView); __deepcopy__→self на immutable-типах (прецедент WorldEpoch/WorldView).
- **GameLoop Lifecycle (game_loop/__init__.py):** dispose() получил обязательный quiesce-шаг (drain собственного ThreadPoolExecutor ДО закрытия SQLite).
- **SSM Commit Boundary (scene_state_manager.py:1726):** ленивый deepcopy npc-снимка (мёртвый потребитель AUDIT #10).
- **DriftLab (SUPERBOX/drift_laboratory.py):** изоляция data_dir (доделывание S268-WIP), порядок сборки vs mock-настройки, fsync-лог-гейт, progress-snapshots, вердикт→CSV/MD, графики, лабораторный quiesce.
- **MockProvider (mock_provider.py):** детерминированный выбор из пулов по hash(prompt) (закрытие DEBT-MOCK S213); модульный _default_endurance_config.

## Downstream Consumers
- **Фазы 0-10 (читатели WorldView):** получают запечатанные контейнеры — вложенная мутация теперь громкий TypeError. Легальные писатели идут через TickOverlay top-level setitem — не задеты (IPT 45/45, DriftLab 10k MATCH).
- **WorldSnapshotBuilder / канон-хеш лаборатории:** deepcopy запечатанных веток стал O(1) на контейнер (C1) — потребители семантически не изменились (листья и раньше не копировались отдельно).
- **get_last_committed_npcs():** контракт сохранён (возвращает независимую копию), момент копирования перенесён с commit на первое чтение (C2). Единственный потребитель WorldProjectionBuffer отключён (AUDIT #10) — при его возврате перф-цена вернётся честно.
- **scene_changes_*.jsonl потребители (диагностика):** канал жив в production; в лаборатории отключён через существующий гейт ENIGMA_DISABLE_FILE_LOGS (C3).
- **Соседняя сессия (кросс-локация):** world_epoch.py — их S266/S268 канон; seal расширяет их модуль, move-semantics и гварды S268 сохранены; координация по канону обязательна при их следующем касании.

## Runtime Impact
- Перф (чистая калибровка, 800×2): 132.4 → 90.2 (детерминизация) → 79.9-90 (seal) → **66.0 мс/тик** (C1+C2+C3) = −50% за сессию. Пара 10k×2 проекция ≈22 мин (факт старого прогона 35.4 мин на 106 мс/тик).
- RAM: нейтрально (шаринг immutable-контейнеров вместо копий — потребление не растёт).
- Причинная нейтральность доказана серией: hash 6875fa94 идентичен на C1→C2→C3; DriftLab 10k×2 MATCH, C/D/E=0, 0 крашей.

## Sandbox Tests
- `backend/tests/test_world_epoch.py` — 7/7 (вкл. новые: test_view_nested_mutation_blocked, test_epoch_npcs_sealed, разграничение зон).
- `backend/tests/IPT.py` — 45/45 (INV-ADR-NET включает O-398; INV-COMMIT-CARDINALITY зелёный после quiesce; INV-TEMPORAL-ISOLATION — сторож разграничения зон).
- DriftLab Mode E: `python -m tests.sandbox.SUPERBOX.run drift replay_determinism` — MATCH + CSV + MD-вердикт + 3 PNG.
- Профили: `reports/s269_profile*.pstats` (baseline/C1/C2/C3 — сравнимы парно).

## Rollback
- C1: удалить __deepcopy__ из ReadOnlyDict/ReadOnlyList (копирование вернётся, перф откатится; риска нет).
- C2: вернуть прямую deepcopy в SSM:1726 (одна строка; риск — только перф).
- C3: убрать setdefault ENIGMA_DISABLE_FILE_LOGS из drift_laboratory (файл-лог вернётся в лабораторию).
- Seal: рекурсивный откат — _sealed-обёртку в WorldView._sealed заменить на прямое чтение; тесты test_view_nested_mutation_blocked/test_epoch_npcs_sealed станут красными ПО ДИЗАЙНУ (это их работа — сигнал, что защита снята).
- Quiesce: удалить шаг 0 из dispose() (вернётся класс DEBT-QUIESCE-шум; риска данным нет).
