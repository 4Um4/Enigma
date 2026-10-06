# ADR-O-421 Impact Audit — Idle Event Projection (LC-IMPL-1)

> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- Наблюдаемость/презентация: read-only проекция idle-событий `{cause, target, value}` (канал «мир → игрок»).
- Ядро idle-канала: только return-слой `game_loop.idle_tick` (tap-окно вокруг `_tick_orch.execute`, try/finally).

## Downstream Consumers
- FE-телеграф `frontend/game_screen.py:1328–1351` — мёртв (ждёт `cause=="idle_pressure"`); оживление и выравнивание фильтра = **LC-IMPL-3**, НЕ эта сессия.
- `routes.py` idle_tick — passthrough без правок (ключ 'events' выровнан K2/S328).
- DTO Registry: +`IdleEventProjection` (§11).
- Замок K2 `test_fe_events_channel_no_deltas.py` — эволюционирован синхронно (StateDeltas-запрет бессрочно).
- Платформенный блокер: движений-домен S330 (event_compiler drop / SSM) не пропускает TAKE-терминал → eat-вертикаль RED (артефакт reports/eat_vertical_recheck.txt); LC-GC-01 митигирован timeout-терминалом (публикуется `_publish_outcome` безусловно). Эскалация Мастеру.

## Runtime Impact
- RAM ~0 (tap живёт только внутри вызова idle_tick); latency — подписка/отписка + pure-map по событиям тика (микросекунды); I/O нет.
- OFF (env=0): `"events": []` — канал пуст, поведение байт-идентично прежнему (SUPERBOX Control).

## Sandbox Tests
- MICRO `backend/tests/micro/test_idle_event_projection.py` ×18: полнота словаря (enum == map ∪ EXCLUDED), скоуп v1, флаг default ON + override, экстракторы fail-loud, мембрана близко/далеко/LOS, whisper-адресат, private-запрет, Vacuum (игрок отсутствует → тишина), read-only (deepcopy), детерминизм, форма-3-поля, деградация наблюдателя (не крах тика), tap-окно (захват/демонтаж без утечки).
- SUPERBOX `lc_gc01_world_speaks_test` GREEN 3/3 (§3.12: PROCESS EXIT=0 + маркер + артефакт reports/lc_gc01_world_speaks.txt): Control OFF — шина activity_outcome жива, канал пуст; Treatment ON — {cause,target,value} (Торнин `eat:fail`), read-only A/B (fingerprint Control≡Treatment при 90/90), утечка-детектор; Negative — закрытые нужды → тишина.
- IPT 51/51 после каждого кодового коммита (A–D).

## Rollback
- Полный: env `IDLE_EVENTS_PROJECTION_ENABLED=0` (канал пуст, поведение прежнее).
- Удаление: wiring (3 встройки idle_tick) + модуль + домен + 2 тест-файла + сценарий; следов в ядре (TickOrchestrator/Фазы) нет.
