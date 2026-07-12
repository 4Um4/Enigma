# ADR-158 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- Infrastructure (Static Analysis)
- Frontend / Backend Code Style

## Downstream Consumers
- CI/CD Pipeline (должен запускать `ruff check .`)
- Разработчики (должны запускать `ruff check . --fix` и `ruff format .`)

## Runtime Impact
- Нет влияния на runtime симуляции.
- Внедрён единый стандарт форматирования (line-length=120) и импортов (isort).
- Исправлены ошибки `E402` (Module level import not at top of file), `F821` (Undefined name), `E741` (Ambiguous variable name), `F841` (Unused local variable).

## Sandbox Tests
- `ruff check frontend/ game_launcher.py` (0 errors)

## Rollback
- Удалить `ruff.toml`.
- Вернуть старые импорты и переменные (если они вызывали ошибки, хотя это маловероятно).