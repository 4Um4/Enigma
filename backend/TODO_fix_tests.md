# TODO: Fix Test Failures
Status: Primary import errors fixed. test_services_fixed.py has 4 additional API mismatches (test code vs impl). test_startup_checks RAM threshold non-fatal. test_error_interpreter fixed to unittest.

## Steps:
- [x] 1. Create this TODO.md
- [x] 2. Fix imports in vram_monitor.py
- [x] 3. Fix psutil path in test_startup_checks.py
- [x] 4. test_error_interpreter converted to unittest (pytest was dev-only)
- [x] 5. Circular import fixed (commented unused orchestrator import in dm_agent)
- [ ] 6. test_services_fixed.py has deeper mismatches - skip or refactor tests
- [ ] 7. Complete task (tests run without NameError/Dict/Path errors)

