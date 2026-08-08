# ADR-CI-MYPY Impact Audit
> Этот файл — детальный аудит фикса CI и mypy --strict compliance.

## Changed Domains
- Infrastructure (CI, mypy config)
- Observability (TaskScheduler error handling)
- Spatial (Typing fixes, null checks)

## Downstream Consumers
- GitHub Actions: теперь запускается из корня.
- TaskScheduler: обрабатывает падения генераторов DialogueExecutor, инкрементирует failed_tasks.
- SpatialService/SceneStateManager: типизированы, защищены от None.

## Runtime Impact
- RAM/CPU: no impact.
- Latency: SpeechScheduler pacing уменьшен до 0.1s (ускоряет материализацию реплик).

## Sandbox Tests
- backend/tests/IPT.py (30/30 passed)

## Rollback
- Удалить mypy.ini, вернуть файлы в architecture/.
- Убрать try/except в task_scheduler.py.
- Вернуть MINIMUM_RESPONSE_LATENCY_SEC = 2.0.
