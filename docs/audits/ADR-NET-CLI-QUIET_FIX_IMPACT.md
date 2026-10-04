# ADR-NET-CLI-QUIET [FIX] Impact Audit
`ADR-NET-CLI-QUIET` [FIX] **IMPACT**
> Инфраструктурный фикс CLI (без нового ADR, прецедент ADR-408 [FIX]). Единый атлас: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- adr_net/CLI: видимость результатов (basicConfig INFO в main())

## Downstream Consumers
- разработчик/architect при прогоне adr_cli impact/conflicts/visualize; CI-скрипты, если появятся

## Runtime Impact
- нулевой для симуляции: CLI не входит в tick-контур; меняется только видимость логов при ручном запуске

## Sandbox Tests
- ручной smoke: `cd backend; python -m app.services.adr_net.adr_cli impact --file svc/tick_orchestrator.py` → печатает результат (было «пусто»)

## Rollback
- удалить 2 строки basicConfig в adr_cli.py:main()
