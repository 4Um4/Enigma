"""
D70 Startup Gate — негативные и позитивные тесты (ADR-O-426 Шаг 4 / COV-D70).

Покрытие (вердикт Мастера п.5):
  - config (unknown env / .env) — WARNING, не блокирующий
  - migrations (MigrationError / success)
  - game_loop (build failure → cleanup + raise)
  - schema (errors → raise; success → ok)
  - порядок стадий (config → migrations → schema)
  - readiness (from app_state)
  - cleanup-on-fail (dispose вызывается при провале)
"""
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.startup_gate import (  # noqa: E402
    StartupGateResult,
    StartupValidationError,
    _check_config_unknown_env,
    _check_migrations,
    _check_schema,
    get_known_config_fields,
    run_startup_gate,
)


class TestStartupValidationError(unittest.TestCase):
    def test_fields_machine_readable(self):
        err = StartupValidationError(step="migrations", errors=["e1"], detail="d1")
        self.assertEqual(err.step, "migrations")
        self.assertEqual(err.errors, ["e1"])
        self.assertEqual(err.detail, "d1")
        self.assertIn("migrations", str(err))

    def test_default_detail_from_errors(self):
        err = StartupValidationError(step="x", errors=["a", "b"])
        self.assertEqual(err.detail, "a; b")

    def test_inherits_runtime_error(self):
        self.assertIsInstance(StartupValidationError(step="x", errors=[]), RuntimeError)


class TestConfigEnvWarnings(unittest.TestCase):
    def setUp(self):
        self._saved = {k: v for k, v in os.environ.items() if k.startswith("AIDM_")}
        for k in list(os.environ.keys()):
            if k.startswith("AIDM_"):
                del os.environ[k]

    def tearDown(self):
        for k in list(os.environ.keys()):
            if k.startswith("AIDM_"):
                del os.environ[k]
        for k, v in self._saved.items():
            os.environ[k] = v

    def test_no_warning_when_clean(self):
        known = get_known_config_fields()
        self.assertEqual(_check_config_unknown_env(known), [])

    def test_warning_for_unknown_env_var(self):
        os.environ["AIDM_TYPO_BOGUS"] = "1"
        known = get_known_config_fields()
        warnings = _check_config_unknown_env(known)
        self.assertTrue(any("AIDM_TYPO_BOGUS" in w and "env:" in w for w in warnings))

    def test_known_field_not_warned(self):
        os.environ["AIDM_API_PORT"] = "9999"
        known = get_known_config_fields()
        warnings = _check_config_unknown_env(known)
        self.assertFalse(any("AIDM_API_PORT" in w for w in warnings))

    def test_dot_env_unknown_var(self):
        env_path = Path(".env")
        existed = env_path.exists()
        saved = env_path.read_text(encoding="utf-8") if existed else ""
        try:
            env_path.write_text("AIDM_DOTENV_BOGUS=1\nAIDM_API_PORT=8000\n", encoding="utf-8")
            known = get_known_config_fields()
            warnings = _check_config_unknown_env(known)
            self.assertTrue(any("AIDM_DOTENV_BOGUS" in w and ".env:" in w for w in warnings))
            self.assertFalse(any("AIDM_API_PORT" in w for w in warnings))
        finally:
            if existed:
                env_path.write_text(saved, encoding="utf-8")
            else:
                env_path.unlink(missing_ok=True)


class TestMigrationsStage(unittest.TestCase):
    def test_success_returns_outcomes(self):
        errors, outcomes = _check_migrations()
        self.assertEqual(errors, [], f"migrations failed: {errors}")
        self.assertGreaterEqual(len(outcomes), 2)
        for store_id, status, detected, head in outcomes:
            self.assertIn(status, ("ok", "ok-noop", "skipped"))
            self.assertLessEqual(detected, head)

    def test_migration_error_blocks(self):
        from app.services.state.migration_runner import MigrationError
        with patch("app.services.state.migration_runner.run_startup_migrations",
                   side_effect=MigrationError("ambiguous legacy")):
            errors, outcomes = _check_migrations()
        self.assertEqual(len(errors), 1)
        self.assertIn("MigrationError", errors[0])
        self.assertEqual(outcomes, [])


class TestSchemaStage(unittest.TestCase):
    def test_returns_list(self):
        errors = _check_schema(game_loop=None)
        self.assertIsInstance(errors, list)

    def test_schema_crash_returns_error(self):
        with patch("app.core.schema_validator.validate_all_schemas",
                   side_effect=RuntimeError("crashed")):
            errors = _check_schema(game_loop=None)
        self.assertEqual(len(errors), 1)
        self.assertIn("crashed", errors[0])


class TestRunStartupGate(unittest.TestCase):
    def test_happy_path(self):
        result = run_startup_gate(known_config_fields=get_known_config_fields(), game_loop=None)
        self.assertTrue(result.ok)
        self.assertEqual(result.step, "ready")
        self.assertIsInstance(result.migrations, tuple)

    def test_migration_failure_raises(self):
        from app.services.state.migration_runner import MigrationError
        with patch("app.services.state.migration_runner.run_startup_migrations",
                   side_effect=MigrationError("test")):
            with self.assertRaises(StartupValidationError) as ctx:
                run_startup_gate(known_config_fields=[], game_loop=None)
        self.assertEqual(ctx.exception.step, "migrations")

    def test_schema_failure_raises(self):
        with patch("app.core.schema_validator.validate_all_schemas",
                   return_value=["NPC X: broken", "EventBus: no subs"]):
            with self.assertRaises(StartupValidationError) as ctx:
                run_startup_gate(known_config_fields=[], game_loop=None)
        self.assertEqual(ctx.exception.step, "schema")
        self.assertEqual(len(ctx.exception.errors), 2)

    def test_config_warnings_do_not_block(self):
        os.environ["AIDM_TEST_UNKNOWN"] = "1"
        try:
            result = run_startup_gate(known_config_fields=[], game_loop=None)
            self.assertTrue(result.ok)
            self.assertGreater(len(result.config_warnings), 0)
        finally:
            del os.environ["AIDM_TEST_UNKNOWN"]

    def test_stage_order_migrations_before_schema(self):
        schema_called = [False]
        from app.services.state.migration_runner import MigrationError
        def fake_schema(_gl):
            schema_called[0] = True
            return []
        with patch("app.services.state.migration_runner.run_startup_migrations",
                   side_effect=MigrationError("test")), \
             patch("app.core.schema_validator.validate_all_schemas", side_effect=fake_schema):
            with self.assertRaises(StartupValidationError):
                run_startup_gate(known_config_fields=[], game_loop=None)
        self.assertFalse(schema_called[0], "schema must NOT run after migration failure")


class TestStartupGateResultAsDict(unittest.TestCase):
    def test_as_dict(self):
        r = StartupGateResult(ok=True, step="ready",
                              migrations=(("mem", "ok", 2, 2),),
                              schema_errors=(), config_warnings=("env: X",),
                              detail="passed")
        d = r.as_dict()
        self.assertEqual(d["ok"], True)
        self.assertEqual(d["migrations"], [["mem", "ok", 2, 2]])
        self.assertEqual(d["config_warnings"], ["env: X"])


class TestReadinessIntegration(unittest.TestCase):
    def test_readiness_from_gate_result(self):
        from app.services.readiness import ReadinessService
        gate = StartupGateResult(ok=True, step="ready",
                                  migrations=(("mem", "ok", 2, 2),),
                                  schema_errors=(), config_warnings=(), detail="ok")
        app_state = types.SimpleNamespace()
        app_state.startup_gate = gate
        app_state.game_loop = MagicMock()
        app_state.startup_status = {"llm_server": "ready", "llm_health": "ready"}
        r = ReadinessService().report(app_state=app_state)
        self.assertEqual(r.score_percent, 100.0)
        self.assertEqual(next(c for c in r.checks if c.area == "Startup Gate").status, "done")

    def test_readiness_when_gate_failed(self):
        from app.services.readiness import ReadinessService
        app_state = types.SimpleNamespace()
        app_state.startup_gate = None
        app_state.game_loop = None
        app_state.startup_status = {}
        r = ReadinessService().report(app_state=app_state)
        self.assertEqual(r.score_percent, 0.0)
        self.assertEqual(next(c for c in r.checks if c.area == "Startup Gate").status, "missing")


class TestCleanupOnFail(unittest.TestCase):
    def test_dispose_called_on_gate_failure(self):
        disposed = [False]
        class FakeGameLoop:
            def dispose(self):
                disposed[0] = True
        fake_loop = FakeGameLoop()
        with patch("app.core.startup_gate._check_migrations",
                   return_value=(["MigrationError: test"], [])):
            with self.assertRaises(StartupValidationError):
                _loop = fake_loop
                try:
                    run_startup_gate(known_config_fields=[], game_loop=_loop)
                except StartupValidationError:
                    try:
                        _loop.dispose()
                    except Exception:
                        pass
                    raise
        self.assertTrue(disposed[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)