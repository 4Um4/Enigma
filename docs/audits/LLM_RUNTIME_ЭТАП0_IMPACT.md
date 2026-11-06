# LLM Runtime Unification — Этап 0 (Кровоостанавливающий) Impact Audit

> **Связанный закон:** Устав §19 (LAW OF SINGULAR LLM RUNTIME AUTHORITY), §7.21–7.22
> **Связанный протокол:** РЕЖИМ РАБОТЫ.md §3.13 (СОЗДАНИЕ НОВОГО LLM-ТЕСТА)
> **База:** ПРОПОЗАЛ docs/architecture/LLM_RUNTIME_UNIFICATION_PROPOSAL.md §7 Этап 0
> **Статус:** GREEN. Критерий Этапа 0 выполнен.

## Что сделано

Этап 0 (кровоостанавливающий) — удаление разрушительных практик управления llama-server: kill-by-name, kill-by-port без проверки владения. Production-код game_launcher.py изменён (диагностическая функция). Тестовые файлы и probe-скрипты — runbook/импорт/kill neutralized.

## Коммиты

| Коммит | Файлы | Суть |
|---|---|---|
| `354a8b9` | 4 .md | Устав §19 + РЕЖИМ §3.13 + Правила §8 + реестр (док-задача) |
| `01a18c1f` | 2 phenomenology | Runbook → llm_server_manager; port 8080 → settings |
| (earlier) | start_dev.ps1 | Удаление (тройной мёртвый: config.json absent + kill-ALL + deleted run_terminal_dm) |
| `88dab765` | game_launcher.py | _kill_zombies → diagnostic-only (no taskkill /IM, no taskkill /T /PID) |
| `be03ac85` | test_run_turn_e2e.py | Dead import → server_lifecycle; async adaptation |
| `28540912` | 4 probe scripts | kill_llama_server(s)() → no-op; taskkill one-liners → pass/comment |

## Затронутые законы

| Закон | Влияние |
|---|---|
| Устав §19 | Реализован Этап 0: kill-by-name устранён, ownership-aware остановка — будущий Host (Этап 3+) |
| Устав §7.21 | Запрет собственного спавна/kill — выполнен |
| Устав §7.22 | Запрет kill по имени/порту — выполнен (taskkill /IM, Stop-Process -Name устранены) |
| РЕЖИМ §3.13 | Протокол создания LLM-теста — задокументирован |
| ADR-O-425 (D61) | Не затронут — game_launcher D61-контур сохранён |

## D4 Transitional Exception

test_run_turn_e2e.py — тест вызывает server_lifecycle.restart_llama_server() / kill_llama_server() напрямую. Тест всё ещё владеет lifecycle сервера — временное исключение (D4, вердикт Мастера).

- kill_llama_server() убивает только started_by_us — если сервер был уже жив (reuse), kill — no-op. Соответствует §19.
- Миграция на Host/Broker — Этап 3+.
- Не распространять паттерн на новые тесты.

## IPT

- Post-change: 52 passed / 2 CRITICAL (pre-existing, НЕ в Этап 0 файлах)
  - INV-RE-CACHE-ALLOWLIST: npc_loader.py (+3 сайта вне ценза ADR-O-415) — релей владельцу RE
  - INV-SILENT-FAILURE: dialogue_executor.py:390 — релей владельцу CCH/DLG
- Регрессии от Этап 0: 0 новых CRITICAL
- pytest collection: 29 tests, 0 errors

## Anti-Race

- Pathspec-only коммиты
- Параллельная P5-A сессия активна — не тронута
- Foreign WIP: guard_borko.json, _hybrid_diagnostic*.py, _quick_test.py, p5a_step_22_spies.py, commit_msg_*.txt — не staged

## Что НЕ сделано (намеренно)

- В1–В6 (§9 ПРОПОЗАЛ) — отложены
- KILLER_SPIRIT (ghost_reaper) — сохранён (трёхусловная identity-проверка; В1 — Этап 2)
- K1/K2/K3 (atexit/restart/stop) — Не трогаем (Этап 1–2)
- Миграция probe-скриптов на llm_server_manager — Этап 1+
- Линтер lint_llm_runtime.py + INV-LLM-SSOT-SPAWN — Этап 6

## Откат

git revert 28540912 be03ac85 88dab765 01a18c1f
+ восстановление start_dev.ps1: git checkout <SHA>^ -- backend/start_dev.ps1

## Эскалации

- docs/АРХИТЕКТУРНЫЙ_УСТАВ_изменения.md — удалён в working tree (Q7). В git-истории (354a8b9). Восстановление — после подтверждения.
- INV-RE-CACHE-ALLOWLIST — релей владельцу ADR-O-415
- INV-SILENT-FAILURE dialogue_executor.py:390 — релей владельцу CCH/DLG