# LLM Runtime Unification — Этап 3 (Host Broker MVP + Step 6A IPT Migration) Impact Audit

> **Связанный закон:** Устав §19 (LAW OF SINGULAR LLM RUNTIME AUTHORITY), §7.21–7.22
> **Связанный протокол:** РЕЖИМ РАБОТЫ.md §3.13 (СОЗДАНИЕ НОВОГО LLM-ТЕСТА)
> **База:** ПРОПОЗАЛ docs/architecture/LLM_RUNTIME_UNIFICATION_PROPOSAL.md §7 Этап 3
> **Статус:** GREEN. Критерий Этапа 3 выполнен. Milestone закрыт: lease isolation + crash recovery + multiplexing доказаны.

## Исходная проблема

Этапы 1–2 дали spawn-lock и ownership-aware kill, но lifecycle всё ещё управлялся **каждым потребителем независимо**:

- Тесты/launcher/main.py сами спавнили llama-server через `acquire_llama_server_lock` + `_spawn_llama_server`.
- atexit каждого процесса регистрировал свой `kill_llama_server` — race между consumer'ами при shutdown.
- Нет lease contract — невозможно отличить «мой lease» от «чужой lease».
- Crash клиента без `release_lease` оставлял orphaned llama-server без владельца.

Принцип Мастера: «идентификация процесса ≠ владение процессом» — нужен **единый распорядитель** LLM-инфраструктуры (Host broker на `:8182`), не очередной скрипт запуска.

## Что сделано

### 3.1 Host broker MVP — `backend/app/services/llm/runtime/host.py`

FastAPI broker на `settings.llm_host_port` (default 8182). Control-plane only (data идёт напрямую client → llama-server:8181).

Endpoints: `GET /health`, `POST /ensure` (guarantees llama-server запущен + spawn если мёртв), `POST /heartbeat` (TTL refresh), `POST /release` (отпускает lease, НЕ kill сервер), `GET /status` (leases list).

Lifespan: shutdown НЕ kill llama-server (вердикт Мастера — сервер переживает управляющий процесс). Stale-lease cleanup каждые 10s (lease TTL 60s / pinned 300s, heartbeat 15s). Adopted server (`spawned_by_us=False`) — never killed.

### 3.2 SDK — `backend/app/services/llm/runtime/client.py`

`ensure_llm(label: str, pinned: bool = False) -> str` — возвращает llama-server URL. Кидает RuntimeError если Host unavailable AND legacy fallback disabled.

`release_lease()` — POST /release + stop heartbeat thread.

Discovery flow: `_check_host_health()` → если Host мёртв, spawn через `subprocess.Popen([sys.executable, "-m", "uvicorn", ...])` with `silent_subprocess_kwargs()` → `_wait_host_ready()` → POST `/ensure` → heartbeat thread (15s) → `atexit.register(release_lease)`.

`ENIGMA_LLM_HOST=off` → legacy `scripts.llm_server_manager` fallback (осознанный opt-out). Авария Host → RuntimeError (NO fallback to legacy).

### 3.3 pytest fixture — `backend/tests/conftest.py`

Session-scoped, NOT autouse. Тесты opting-in: `def test_x(llm_runtime): ...`.

### 3.4 Silent subprocess helper — `backend/app/services/llm/runtime/_proc.py`

SSOT для скрытия spawn'ов на Windows: `silent_subprocess_kwargs()` возвращает `CREATE_NO_WINDOW + STARTUPINFO(SW_HIDE)` на Windows, `{}` на Linux/macOS.

**Intentionally does NOT use `DETACHED_PROCESS`**: Microsoft forbids combining it with `CREATE_NEW_PROCESS_GROUP` (client.py merges helper with `CREATE_NEW_PROCESS_GROUP` for Ctrl-Break lifecycle). Conflict caused Windows to allocate new console — exactly the visible window we suppress.

Coverage (5 файлов): `scripts/llm_server_manager.py`, `backend/app/services/llm/runtime/client.py`, `backend/app/services/llm/server_lifecycle.py` (`_spawn_llama_server` — covers host.py /ensure, main.py startup, routes.py restart), `game_launcher.py`.

### 3.5 Step 6A: IPT migration — `backend/tests/IPT.py`

Шапка IPT.py переведена на Host broker SDK: `from scripts.llm_server_manager import start_llama_server, kill_llama_server` → `from app.services.llm.runtime.client import ensure_llm`. `start_llama_server() + atexit.register(kill_llama_server)` → `ensure_llm(label="IPT")`. `release_lease` регистрируется ВНУТРИ SDK — НЕ дублируется. `catch (ModuleNotFoundError, OSError)` → `catch Exception` (Host SDK кидает RuntimeError — старый узкий catch упускал). Финальный ghost_reaper safety net оставлен без изменений.

### 3.6 Cleanup regression (Step 6A follow-up)

`architecture/flags.yaml` — registered `ENIGMA_LLM_HOST` (ROLLOUT-ON, effective_default="on"). `backend/app/services/execution/dialogue_executor.py:388-391` — L4 fix (`except Exception:` → `except Exception as e: print(...)`).

## Коммиты

| Коммит | Файлы | Суть |
|---|---|---|
| `c01799ca` | `backend/app/services/llm/runtime/host.py` (новый), `backend/app/core/config.py` | Host broker MVP: FastAPI endpoints, lifespan (shutdown НЕ kill), stale-lease cleanup; `settings.llm_host_port: int = 8182` (SSOT) |
| `0ed3d8aa` | `backend/app/services/llm/runtime/client.py` (новый) | SDK: `ensure_llm(label, pinned) -> str`, `release_lease()`, heartbeat thread, atexit, `ENIGMA_LLM_HOST=off` legacy fallback |
| `95fe4ec2` | `backend/tests/conftest.py` | `llm_runtime` fixture (session-scoped, NOT autouse) |
| `53f7c2d4` | `scripts/probe_cch_decompose.py`, `scripts/probe_model.py`, `backend/app/services/llm/runtime/host.py`, `backend/app/services/llm/runtime/client.py` | Regressions: probe scripts syntax (orphaned except/empty try), silent failures L4 (`except Exception:` → `except Exception as e: print(...)`) |
| `19664c9a` | `scripts/llm_server_manager.py`, `backend/app/services/llm/runtime/client.py` | silent_subprocess_kwargs v1 (CREATE_NO_WINDOW + DETACHED_PROCESS + STARTUPINFO) |
| `c560623c` | `backend/app/services/llm/runtime/_proc.py` (новый), `backend/app/services/llm/server_lifecycle.py`, `game_launcher.py` | silent_subprocess_kwargs v2 SSOT — removed DETACHED_PROCESS (Microsoft conflict with CREATE_NEW_PROCESS_GROUP); coverage: server_lifecycle._spawn_llama_server + game_launcher |
| `3281ead3` | `backend/tests/IPT.py` | Step 6A: шапка IPT.py → `ensure_llm(label="IPT")`; catch расширен до Exception; финальный reaper комментарий обновлён |
| `96fd9047` | `architecture/flags.yaml`, `backend/app/services/execution/dialogue_executor.py` | Cleanup: ENIGMA_LLM_HOST registered (ROLLOUT-ON); dialogue_executor.py L4 fix |

## Контракт ДО и ПОСЛЕ

### ДО

Каждый consumer сам управляет lifecycle: launcher → `acquire_lock` → `_spawn_llama_server` → `atexit(kill_llama_server)`. Race: два consumer'a одновременно → дубль на порт (Этап 1 partial-mitigation). Crash consumer без release → orphaned llama-server без владельца. Kill в atexit одного consumer'a → убивает сервер для других (Этап 2 partial-mitigation через `_has_active_clients`).

### ПОСЛЕ

Единый распорядитель: Host broker `:8182`. Consumer → `ensure_llm(label)` → POST /ensure → Host spawns/reuses llama-server. Consumer → `atexit(release_lease)` → POST /release → lease released (server НЕ kill).

OS port binding mutex (8182) → single Host instance guaranteed. Lease contract (uuid, PID+create_time, TTL 60s/pinned 300s, heartbeat 15s). Adopted server (`spawned_by_us=False`) — never killed. Host shutdown → server stays alive (вердикт Мастера).

Lease state machine: `acquire` (POST /ensure → returns `{lease_id, url}`; Host spawns llama if dead) → `heartbeat` (every 15s → POST /heartbeat, TTL refresh) → `release` (POST /release graceful OR TTL expiry для crashed consumer, stale-lease cleanup каждые 10s). `pinned` lease — TTL 300s.

## Затронутые законы

| Закон | Влияние |
|---|---|
| Устав §19 | Реализован: единый распорядитель LLM-инфраструктуры (Host broker `:8182`). Consumers acquire/release lease, не владеют lifecycle. |
| Устав §7.21 | Запрет собственного спавна — выполнен (consumers не спавнят, только Host broker) |
| Устав §7.22 | Запрет kill по имени/порту — выполнен (consumers не kill, только release lease) |
| РЕЖИМ §3.13 | Протокол создания LLM-теста — применяется (IPT мигрирован на SDK) |
| ADR-O-425 (D61) | Не затронут — D61-контур сохранён |
| `ENIGMA_LLM_HOST` flag | Зарегистрирован в `architecture/flags.yaml` (ROLLOUT-ON, `96fd9047`) |

## Тесты и фактические результаты

### Two-Client Crash Isolation Test (2026-11-07, до hide window fix)

| Шаг | Тест | Результат |
|---|---|---|
| S1 | Start clients A+B | both lease acquired (different uuids) |
| S2 | Verify | `leases=2, llama=1` — один llama-server, два lease ✅ |
| S3 | Crash A (no release) | A killed, no release_lease |
| S4 | B survives | `B_lease=PASS, llama=PASS, host=PASS` ✅ |
| S5 | Wait 65s for A TTL | TTL expiry |
| S6 | Cleanup | `A_expired=PASS, B_alive=PASS, llama=PASS` ✅ |
| S7-8 | B repeated ensure | `reuse=PASS (same=True), no_duplicate=PASS` ✅ |
| Cleanup | Host/llama PID before==after | `Host PID 14352→14352 same=True`, `llama PID 21528→21528 same=True` ✅ |

Подтверждено: crash одного клиента (без `release_lease`) НЕ убивает сервер и НЕ ломает второго клиента. TTL (60s) корректно очищает lease мёртвого клиента. Host broker и llama-server **переживают shutdown обоих клиентов**.

### SDK Recovery из нулевого состояния

Доказано: оба процесса мертвы → `ensure_llm()` → Host spawn → `/ensure` → llama-server spawn → lease acquired → release_lease → lease released (server остаётся живым).

### Window-trap test (hide window fix verification)

100ms polling during `ensure_llm()` + 8s hold: **ZERO new processes with `MainWindowHandle != 0`**. Host broker PID = normal python.exe, port 8182 owned by python (was orphaned conhost PID 400 from conflict-spawn before fix).

### IPT post-migration (Step 6A + cleanup)

`[LLM_SDK] lease acquired: <uuid> (label=IPT, url=http://localhost:8181)` → IPT runs → `[KILLER_SPIRIT] SPARE pid=15212 llama-server.exe: живой владелец pid=18900` → `[LLM_SDK] lease released: <uuid>`. ИТОГО: 53 passed / 0 skipped / 1 failed (1 CRITICAL).

- Baseline: 52 passed / 2 CRITICAL (RE-CACHE-ALLOWLIST + FLAG-REGISTRY, pre-existing)
- Post-Step 6A: 53 passed / 1 CRITICAL — **+1 passed, -1 CRITICAL** vs baseline
- Закрытые regression'ы: INV-FLAG-REGISTRY (через `ENIGMA_LLM_HOST` в flags.yaml), INV-SILENT-FAILURE (через dialogue_executor L4 fix)
- Оставшийся CRITICAL: INV-RE-CACHE-ALLOWLIST (npc_loader.py, pre-existing, NPC-related, не от LLM Runtime Unification)

## Ограничения и оставшиеся риски

1. **Legacy consumers остаются** (НЕ полная миграция):
   - `backend/tests/sandbox/SUPERBOX/scenarios/*` — множество файлов использует `from scripts.llm_server_manager import start_llama_server, kill_llama_server`
   - `backend/tests/sandbox/phenomenology/*`, `backend/tests/sandbox/scenarios/chronicle_decompose_probe.py`, `chronicle_weave_probe.py`
   - `backend/tests/sandbox/system/test_epistemology_pipeline.py`, `test_homeostatic_dialogue_stability.py` — own Popen llama-server spawn
   - `scripts/butterfly_l4_real_llm.py`, `scripts/det_holder.py`, `scripts/redecompose_all_npc.py`, `reports/p0_ra_classifier.py`
   - Миграция legacy consumers — Этап 4.

2. **`ENIGMA_LLM_HOST=off` opt-out** — legacy fallback оставлен осознанно (переходный период). Авария Host → RuntimeError (NO auto-fallback).

3. **Host broker на `:8182` — single point of failure** (но recovery из нулевого состояния доказан: если Host мёртв, `ensure_llm` spawn'ит его заново).

4. **Foreign service detection: 30s timeout** — SDK правильно обнаружил foreign, но ждёт полный timeout. Follow-up optimization: HTTPError → immediate RuntimeError.

5. **D4 transitional exception**: `backend/tests/sandbox/micro/test_run_turn_e2e.py` всё ещё владеет lifecycle через `server_lifecycle.restart_llama_server()` / `kill_llama_server()` напрямую. Не распространять паттерн.

6. **`docs/АРХИТЕКТУРНЫЙ_УСТАВ_изменения.md`** — удалён в working tree (Q7). В git-истории (`354a8b9`). Восстановление — после подтверждения.

7. **`backend/tests/gameplay/run_p5a_full.py:702` SyntaxError** — pre-existing (не от LLM Runtime Unification), pre-commit hook warning. Чужой WIP P5-A — не трогаем без согласования с владельцем.

8. **`backend/tests/gameplay/test_butterfly_full_game_loop.py` +88 строк docstrings** — incidental WIP leak, попал в коммит `c560623c` через pathspec. Не критично (только docstrings, не функциональность).

## Что НЕ сделано (намеренно)

- **В1–В6 (§9 ПРОПОЗАЛ)** — отложены для Этапа 4+.
- **Полная миграция legacy consumers** — Этап 4 (sandbox probes, drift_laboratory, chronicle_decompose_probe и др.).
- **Линтер `lint_llm_runtime.py` + `INV-LLM-SSOT-SPAWN`** — Этап 6.
- **Foreign service optimization** (HTTPError → immediate RuntimeError) — follow-up.
- **Q7 восстановление `docs/АРХИТЕКТУРНЫЙ_УСТАВ_изменения.md`** — после подтверждения.
- **`run_p5a_full.py:702` SyntaxError fix** — чужой WIP, не трогаем.

## Откат

Полный rollback Этапа 3: `git revert 96fd9047 3281ead3 c560623c 19664c9a 53f7c2d4 95fe4ec2 0ed3d8aa c01799ca` — восстановит каждый consumer сам spawn'ит llama-server через `acquire_lock + _spawn_llama_server`.

Partial rollback (только Step 6A IPT migration): `git revert 96fd9047 3281ead3` — восстановит IPT шапку: `from scripts.llm_server_manager + start_llama_server + atexit(kill_llama_server)`.

## Эскалации

- **Legacy consumers миграция** — Этап 4 (отдельный трек).
- **Foreign service 30s timeout** — follow-up (HTTPError → immediate RuntimeError).
- **Q7 (`docs/АРХИТЕКТУРНЫЙ_УСТАВ_изменения.md`)** — восстановление после подтверждения.
- **`run_p5a_full.py:702` SyntaxError** — релей владельцу P5-A WIP.
- **INV-RE-CACHE-ALLOWLIST (npc_loader.py)** — pre-existing, релей владельцу ADR-O-415.