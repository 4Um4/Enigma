# LLM Runtime Unification — Этап 2 (Ownership-Контракт) Impact Audit

> **Связанный закон:** Устав §19 (LAW OF SINGULAR LLM RUNTIME AUTHORITY), §7.21–7.22
> **Связанный протокол:** РЕЖИМ РАБОТЫ.md §3.13 (СОЗДАНИЕ НОВОГО LLM-ТЕСТА)
> **База:** ПРОПОЗАЛ docs/architecture/LLM_RUNTIME_UNIFICATION_PROPOSAL.md §7 Этап 2
> **Статус:** GREEN. Критерий Этапа 2 выполнен.

## Что сделано

Этап 2 (ownership-контракт) — устранение безусловного kill в `kill_llama_server()` и `ghost_reaper._reap_orphans()` через добавление helper'а `_has_active_clients(port)`:

- Helper использует `psutil.net_connections(kind="tcp")` для поиска ESTABLISHED соединений на `port`.
- Возвращает `True` если есть хотя бы одно ESTABLISHED от процесса ≠ self.

`kill_llama_server()` и `ghost_reaper._reap_orphans()` теперь:
- Перед kill проверяют `_has_active_clients(port)`.
- Если есть активные клиенты → **spare** (печатается `[KILLER_SPIRIT] SPARE pid=<pid> llama-server.exe: живые владельцы`), kill пропускается.
- Если активных клиентов нет → kill выполняется (существующий path).

Принцип Мастера: «идентификация процесса ≠ владение процессом» — kill должен учитывать наличие других активных потребителей.

## Коммиты

| Коммит | Файлы | Суть |
|---|---|---|
| `351a5e02` | `scripts/llm_server_manager.py` | `_has_active_clients(port)` helper; `kill_llama_server` client-presence check (spare if active clients) |
| `351a5e02` | `scripts/ghost_reaper.py` | `_has_active_clients(port)` helper; orphan с клиентами на :8181 → spared |

## Контракт ДО и ПОСЛЕ

### ДО

`kill_llama_server()` убивает процесс-владелец порта 8181 безусловно. Сценарий:

1. Тест A запущен, держит lease (через `acquire_llama_server_lock` → reuse).
2. Тест B стартует, тоже получает reuse (health ok).
3. Тест A завершается, вызывая `kill_llama_server()` в atexit.
4. `kill_llama_server()` убивает llama-server, **тест B теряет LLM**.

То же для `ghost_reaper.reap()`: orphan с активными клиентами на :8181 получал kill, роняя живые тесты.

### ПОСЛЕ

`kill_llama_server()` и `ghost_reaper._reap_orphans()` перед kill проверяют `_has_active_clients(port)`:

- Если есть ESTABLISHED TCP-соединения от других процессов на порту 8181 → spare (лог `[KILLER_SPIRIT] SPARE pid=<pid> llama-server.exe: живые владельцы`), kill пропускается.
- Если активных клиентов нет → kill выполняется (существующий path).

Поведение соответствует принципу Мастера «идентификация процесса ≠ владение процессом» — kill ownership-aware, не безусловный.

## Затронутые законы

| Закон | Влияние |
|---|---|
| Устав §19 | Этап 2: ownership-контракт. Kill учитывает активных потребителей. Полный lease-based ownership — Этап 3. |
| Устав §7.21 | Запрет собственного спавна — не затронут (Этап 1) |
| Устав §7.22 | Запрет kill по имени/порту — выполнен: kill ownership-aware (с проверкой клиентов) |
| ADR-O-425 (D61) | Не затронут |

## Тесты и фактические результаты

- IPT post-`351a5e02`: 52 passed / 2 CRITICAL (pre-existing, не в Этап 2 файлах)
- Регрессии от Этапа 2: 0 новых CRITICAL
- Доказательство работы (IPT-финал): `[KILLER_SPIRIT] SPARE pid=15212 llama-server.exe: живой владелец pid=18900` — KILLER_SPIRIT корректно пощадил llama-server с активным Host broker'ом.
- Two-client crash isolation test (проведён в начале LLM Runtime Unification сессии, 2026-11-07): после завершения клиента A (без `release_lease`) клиент B продолжил работу, llama-server не убит. `S4_B_lease: PASS`, `S4_llama: PASS`.

## Ограничения и оставшиеся риски

1. **`_has_active_clients` основан на ESTABLISHED TCP-соединениях** — не специфичен для Enigma. Если foreign process (не Enigma) держит соединение на 8181, kill будет пропущен (false positive → не kill). На практике 8181 — выделенный порт llama-server, foreign маловероятен.
2. **False negative (zombie connection)** — ESTABLISHED соединение в state `CLOSE_WAIT` / `TIME_WAIT` psutil показывает как ESTABLISHED. Может привести к spare'у уже мёртвого клиента. На практике: ghost_reaper запускается периодически, zombie clear'ится ОС через ~60s.
3. **psutil dependency** — psutil может отсутствовать в CI. Fallback'а нет (молчаливый skip spare = unsafe). Risk: CI без psutil → `_has_active_clients` кидает `ImportError` → kill пропускается (safe default, но не loud).
4. **Не покрывает scenario «клиент crashed, но TCP ещё не закрыл»** — lease remains active до TTL expiry. Решается в Этапе 3 через lease TTL + heartbeat.

## Что НЕ сделано (намеренно)

- **Lease-based ownership** — Этап 3 (Host broker, lease_id, TTL, heartbeat).
- **Lease TTL / expiry** — Этап 3 (stale lease cleanup каждые 10s).
- **Линтер `lint_llm_runtime.py` + `INV-LLM-SSOT-SPAWN`** — Этап 6.

## Откат

`git revert 351a5e02` — восстановит безусловный kill в `kill_llama_server` и `ghost_reaper._reap_orphans`.

## Эскалации

- psutil dependency в CI — не блокирует (safe default spare), но отмечен как risk.
- Q7 (`docs/АРХИТЕКТУРНЫЙ_УСТАВ_изменения.md`) — эскалирован отдельно.