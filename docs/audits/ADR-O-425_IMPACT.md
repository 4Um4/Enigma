# ADR-O-425 Impact Audit

ADR-O-425 [STANDARD] **IMPACT**

> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: docs/ADR (Architecture Decision Records).md

## Changed Domains
- Фронтенд-контур доставки LLM: статус-наблюдение, пауза мира, рестарт-флоу (D61)
- Транспорт api_client: per-call таймаут рестарта (30с -> 180с, _LLM_RESTART_TIMEOUT_SEC)
- Бэкенд-пакет COV-2 — серия передатчика (S343-S345): /llm/outage, /api/llm/restart, server_lifecycle, pool backoff (31387976 и др.)

## Downstream Consumers
- game_screen.run() — гейты idle/skip/submit + модалка поглощает кадр (дренаж событий, QUIT пробрасывается)
- _handle_text_input — гвард submit через self._llm_ctrl (ТЗ §3.4-4; единственный call-site run:921, после инициализации)
- UX-FB Тай (44a65f77) — переиспользует D61-модалку для честной деградации LLM-хода (совместимо с доктриной, в main вместе)
- TaskScheduler/worker-путь — не тронуты (очередь D62 за LLM_RESILIENCE_V1)

## Runtime Impact
- +1 daemon-поток (5с poll; generation-счётчик гасит при выходе; повторный run() гасит прошлый watcher)
- Рестарт-воркер — разовый поток на попытку; транспорт держит сокет до 180с (вместо ложного FAILED на 30с)

## Sandbox Tests
- backend/tests/sandbox/SUPERBOX/scenarios/d61_llm_outage_doctrine_test.py — GREEN 32/0, PROCESS EXIT=0 (живой llama-server, kill×3/restart×3; артефакты reports/d61_llm_outage_doctrine.{json,md})
- backend/tests/micro/test_llm_resilience_v1.py — 27/27 (24 бэкенд + T-пауза×3)

## Rollback
- git revert ea5a05d1 6849a9f3 0253d0ef (фронт+smoke; бэкенд-серия COV-2 откатывается отдельно)

## Остатки
- LLM_RESILIENCE_V1 ROLLOUT-PENDING: ON = отдельный вердикт Мастера + повторная приёмка (full pytest + IPT + живой smoke)
- Ручной чеклист Мастера (вне headless): модалка на экране / утечка кликов-ESC через event-loop game_screen / крестик при модалке
- Router-зомби (эскалация S347): детекция смерти llama-server вне in-flight запросов — COV-2-смежный хвост зоны Б
- Dual-stack спавнеров: менеджер --host localhost (стек ::1) vs lifecycle 127.0.0.1 — выравнивание на Мастере
- UX старт-гейта: латентное окно /health при загрузке модели переживается как unconfirmed×2 без модалки (легально по доктрине; вопрос удобства)
