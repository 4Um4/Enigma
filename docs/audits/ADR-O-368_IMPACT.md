`ADR-O-368` [STANDARD] **IMPACT**
# Impact Audit — ADR-O-368 [ONTO] Calibration Lab Frontend Isolation Exception (Dev Enclave)
> Детальный аудит ОДНОГО ADR. Единый атлас: `docs/ADR (Architecture Decision Records).md`
## Changed Domains
- frontend-isolation (allowlist-исключение), calibration-lab (enclave boundary)
## Downstream Consumers
- scripts/lint_frontend_isolation.py (allowlist), frontend/map_editor/ui/lab_screen.py, backend/tests/IPT.py (INV-FRONTEND-ISOLATION через run_lint)
## Runtime Impact
- нулевой: точечный allowlist в линтере; production UI не затронут
## Sandbox Tests
- backend/tests/IPT.py (INV-FRONTEND-ISOLATION); имя профильного теста — backend/tests/calibration_lab/ (M1-серия S220)
## Rollback
- удаление allowlist-записи lab_screen.py в scripts/lint_frontend_isolation.py
