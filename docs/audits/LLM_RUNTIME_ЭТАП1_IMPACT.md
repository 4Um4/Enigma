# LLM Runtime Unification — Этап 1 (Spawn-Lock) Impact Audit

> **Связанный закон:** Устав §19 (LAW OF SINGULAR LLM RUNTIME AUTHORITY), §7.21–7.22
> **Связанный протокол:** РЕЖИМ РАБОТЫ.md §3.13 (СОЗДАНИЕ НОВОГО LLM-ТЕСТА)
> **База:** ПРОПОЗАЛ docs/architecture/LLM_RUNTIME_UNIFICATION_PROPOSAL.md §7 Этап 1
> **Статус:** GREEN. Критерий Этапа 1 выполнен.

## Что сделано

Этап 1 (spawn-lock) — устранение race condition при спавне llama-server через перевод `acquire_llama_server_lock(port, health_url)` на двухлинейный lock:

- **Health-check** — существующий путь через urllib; отвечает 200 → reuse.
- **Bind-probe** — `socket.bind((127.0.0.1, port))` в дополнение; bind удался → порт свободен → spawn легален; bind отказал → порт занят кем-то не отвечающим health → safe-path "spawn" отменяется, возвращается `"port_busy_unknown_owner"`.

Дополнительно:
- `localhost` → `127.0.0.1` во всех health-URL (резолв localhost на части машин добавлял секунды к каждому запросу — наблюдено замерами).
- `gpu_layers` → `effective_gpu_layers` в settings (однозначное имя production-effective значения после override).

## Коммиты

| Коммит | Файлы | Суть |
|---|---|---|
| `fb738628` | `scripts/llm_server_manager.py` | `acquire_llama_server_lock` — двухлинейный lock (health + bind-probe); `localhost`→`127.0.0.1`; `gpu_layers`→`effective_gpu_layers`; S3-флаги canonical |

## Контракт ДО и ПОСЛЕ

### ДО

`acquire_llama_server_lock(port, health_url)` использует только health-check для определения «сервер уже запущен». Не отличает:
- сервер грузится (порт занят, health ещё не отвечает) → lock возвращает "spawn" → дубль на порт
- сервер мёртв, порт свободен → lock корректно возвращает "spawn"

Инцидент 2026-08-30 (задокументирован в docstring `acquire_llama_server_lock`): два llama-server на 8181 → VRAM 96% → 503 на всех NARRATIVE-запросах.

### ПОСЛЕ

`acquire_llama_server_lock(port, health_url)` использует двухлинейный lock:
1. Health-check — если отвечает 200, возвращается `"reuse"`.
2. Bind-probe — если health не отвечает, пробуем `socket.bind((127.0.0.1, port))`. Bind удался → порт свободен → `"spawn"`. Bind отказал → порт занят → `"port_busy_unknown_owner"`.

Семантика вердиктов:
- `"reuse"` — сервер отвечает health, не спавнить.
- `"spawn"` — порт свободен, spawn легален.
- `"port_busy_unknown_owner"` — порт занят кем-то, не отвечающим health (битый процесс / foreign). Spawn отменён — зона `kill_llama_server`/ручного вмешательства.

## Затронутые законы

| Закон | Влияние |
|---|---|
| Устав §19 | Этап 1: spawn-lock предотвращает дубль. Полный ownership — Этап 3 (Host broker). |
| Устав §7.21 | Запрет собственного спавна — выполнен (через canonical lock) |
| Устав §7.22 | Запрет kill по имени/порту — не затронут (это Этап 0/2) |
| ADR-O-425 (D61) | Не затронут |

## Тесты и фактические результаты

- IPT post-`fb738628`: 52 passed / 2 CRITICAL (pre-existing, не в Этап 1 файлах)
  - INV-RE-CACHE-ALLOWLIST: npc_loader.py — pre-existing
  - INV-FLAG-REGISTRY: pre-existing (на момент Этапа 1; закрыт в `96fd9047` через регистрацию `ENIGMA_LLM_HOST`)
- Регрессии от Этапа 1: 0 новых CRITICAL
- Доказательство работы: двухлинейный lock срабатывает на сценарии «health не отвечает + порт занят» — возвращается `"port_busy_unknown_owner"`, spawn не происходит.

## Ограничения и оставшиеся риски

1. **Окно между health-check и bind-probe** — теоретическая race: между двумя вызовами другой процесс может занять порт. На практике окно < 1мс, маловероятно.
2. **`_port_owner_pid` использует psutil → netstat fallback** — psutil может отсутствовать в CI; netstat возвращает `unknown` при сбое. Это honest answer (не выдуманный PID 0).
3. **Lock не предотвращает параллельный spawn из двух процессов одновременно** — если два consumer'а одновременно вызовут `acquire_llama_server_lock` до того, как первый успеет bind. Это ограничение file-less lock; полное решение — Host broker (Этап 3) с OS port binding mutex.
4. **Bind-probe использует `127.0.0.1`** — если сервер биндится на `0.0.0.0` или другой интерфейс, bind-probe на `127.0.0.1` может ложно показать «порт свободен». Текущая конфигурация: llama-server spawn через `--host 127.0.0.1` (выравнивание с провайдерами/лаунчером).

## Что НЕ сделано (намеренно)

- **Полный ownership-контракт** — Этап 2 (`_has_active_clients`, kill_llama_server spare in-use).
- **Host broker** — Этап 3 (lease-based ownership, OS port binding mutex).
- **Линтер `lint_llm_runtime.py` + `INV-LLM-SSOT-SPAWN`** — Этап 6.

## Откат

```bash
git revert fb738628

Восстановит single-line health-check lock, `localhost`, `gpu_layers`.

## Эскалации

- Нет открытых эскалаций по Этапу 1.
- Q7 (`docs/АРХИТЕКТУРНЫЙ_УСТАВ_изменения.md` — удалён в working tree) — эскалирован отдельно, восстановление после подтверждения.
