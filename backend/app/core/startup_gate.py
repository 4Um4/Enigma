"""
ENIGMA Startup Gate (ADR-O-426, Шаг 4 / D70, COV-D70):
единая блокирующая конъюнкция старта.

Старт обязан либо доехать до живого мира, либо громко отказать
с машиночитаемой причиной — старт не притворяется. Та же грань
честности, что D59 (сейв) и D60 (сброс): «старт не притворяется».

Порядок стадий (вердикт Мастера):
  config → migrations → build_game_loop → schema validation → publish ready → yield

Шаг 4 wiring (вердикт В3): MigrationRunner.run_startup_migrations
вызывается здесь production startup'ом — единственный путь миграций
в рантайме (Шаг 1 / S1 контракт: А подключает миграции поверх раннера,
сам раннер не редактируется).

Стампинг живых БД (первичная классификация COV-1) — отдельный протокол
(IMPACT ADR-O-426 §7, 8 условий); обычный запуск не обходит dry-run /
отчёт / явное подтверждение. Здесь — только применение миграций к
БД, уже прошедшим первичную классификацию.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────
# Машиночитаемая ошибка старта (контракт В7, как CampaignResetError у D60)
# ──────────────────────────────────────────────────────────────────


class StartupValidationError(RuntimeError):
    """Старт-гейт упал — сервер не имеет права принимать соединения.

    Поля машиночитаемы (контракт В7 / ADR-O-426):
      step:   config | migrations | game_loop | schema
      errors: List[str] — детальный список причин
      detail: str — человекочитаемое summary

    lifespan ловит и передаёт в uvicorn как fatal (raise до yield) —
    uvicorn завершается с ненулевым exit code.
    """

    def __init__(
        self,
        *,
        step: str,
        errors: List[str],
        detail: Optional[str] = None,
    ) -> None:
        self.step = step
        self.errors = list(errors)
        self.detail = detail or "; ".join(self.errors)
        super().__init__(
            f"[startup_gate:{step}] {self.detail} ({len(self.errors)} error(s))"
        )


# ──────────────────────────────────────────────────────────────────
# Результат старт-гейта (передаётся в app.state для readiness API)
# ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class StartupGateResult:
    """Машиночитаемый отчёт старт-гейта (для /api/readiness и логов)."""

    ok: bool
    # "config" | "migrations" | "game_loop" | "schema" | "ready" | "failed"
    step: str
    # tuple[(store_id, status, detected, head), ...]
    migrations: Tuple[Tuple[str, str, int, int], ...] = ()
    schema_errors: Tuple[str, ...] = ()
    # Unknown AIDM_ env vars (WARNING, не блокирующий — вердикт В1)
    config_warnings: Tuple[str, ...] = ()
    detail: str = ""

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "step": self.step,
            "migrations": [list(m) for m in self.migrations],
            "schema_errors": list(self.schema_errors),
            "config_warnings": list(self.config_warnings),
            "detail": self.detail,
        }


# ──────────────────────────────────────────────────────────────────
# Стадии гейта (чистые функции; side-effects — в lifespan)
# ──────────────────────────────────────────────────────────────────


def _check_config_unknown_env(known_fields: List[str]) -> List[str]:
    """В1 (вердикт Мастера): AIDM_* env vars не из Settings — WARNING.

    Pydantic extra='ignore' глотает их молча; мы логируем отдельно,
    читая os.environ и .env (если есть). НЕ блокирует старт —
    неизвестные legacy-переменные могут существовать в старых .env.
    Блокирующими являются только ошибки значений обязательных настроек
    (Pydantic ловит их сам через валидаторы полей).
    """
    warnings: List[str] = []
    known_upper = {f.upper() for f in known_fields}

    # 1. os.environ — процесс
    # Известные имена полей хранятся БЕЗ префикса (API_PORT, не AIDM_API_PORT);
    # срезаем префикс перед сравнением.
    for key in sorted(os.environ.keys()):
        if key.startswith("AIDM_") and key[5:].upper() not in known_upper:
            warnings.append(f"env: {key} (unknown AIDM_ variable)")

    # 2. .env file (если есть в CWD)
    env_path = Path(".env")
    if env_path.exists():
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                key = line.split("=", 1)[0].strip()
                if key.startswith("AIDM_") and key[5:].upper() not in known_upper:
                    warnings.append(f".env: {key} (unknown AIDM_ variable)")
        except OSError as e:
            warnings.append(f".env: read error: {e}")

    return warnings


def _check_migrations() -> Tuple[List[str], List[Tuple[str, str, int, int]]]:
    """Стадия migrations (Шаг 4 wiring, вердикт В3): единый путь
    применения миграций — run_startup_migrations через старт-гейт.

    Возвращает (errors, outcomes_summary).
    MigrationError → блокирующий (неоднозначное легаси / даунгрейд /
    разрыв цепочки / отказ верификации).
    """
    errors: List[str] = []
    outcomes: List[Tuple[str, str, int, int]] = []
    try:
        from app.services.state.migration_runner import (
            MigrationError,
            run_startup_migrations,
        )

        results = run_startup_migrations(make_backup=True)
        for r in results:
            outcomes.append(
                (r.store_id, r.status, r.detected_version, r.head_version)
            )
            # status ∈ {"ok", "ok-noop", "skipped", "dry-run"} — иначе блок
            if r.status not in ("ok", "ok-noop", "skipped"):
                errors.append(
                    f"migration {r.store_id}: unexpected status '{r.status}'"
                )
    except MigrationError as e:
        errors.append(f"MigrationError: {e}")
    except Exception as e:
        errors.append(f"migrations crashed: {type(e).__name__}: {e}")
    return errors, outcomes


def _check_schema(game_loop: Any) -> List[str]:
    """Стадия schema: validate_all_schemas возвращает List[str] (errors).

    Рефактор schema_validator (D70): функция больше не логирует как
    non-blocking warning и не имеет встроенного решения; решение
    принимает старт-гейт.
    """
    try:
        from app.core.schema_validator import validate_all_schemas

        return list(validate_all_schemas(game_loop))
    except Exception as e:
        # L4 (no silent failure): логируем краш валидации — старт-гейт
        # должен различать «валидация нашла ошибки» (возвращаемым списком)
        # и «валидация сама упала» (этой веткой).
        logger.error("[STARTUP_GATE:schema] validation crashed: %s", e, exc_info=True)
        return [f"schema validation crashed: {type(e).__name__}: {e}"]


# ──────────────────────────────────────────────────────────────────
# Единый гейт
# ──────────────────────────────────────────────────────────────────


def run_startup_gate(
    *,
    known_config_fields: List[str],
    game_loop: Any,
) -> StartupGateResult:
    """Единый блокирующий гейт старта.

    Вызывается из lifespan ПОСЛЕ build_game_loop (schema validation
    требует game_loop — вердикт Мастера уточнение 1).

    Стадии: config (warnings) → migrations (blocking) → schema (blocking).

    Любой блокирующий отказ → StartupValidationError; lifespan ловит и
    переводит в uvicorn fatal (raise до yield, ненулевой exit).

    Возвращает StartupGateResult для app.state (readiness API).
    """
    # 1. config — unknown env vars (WARNING, не блокирующий — вердикт В1)
    config_warnings = _check_config_unknown_env(known_config_fields)
    if config_warnings:
        for w in config_warnings:
            logger.warning(f"[STARTUP_GATE:config] {w}")

    # 2. migrations — блокирующий
    mig_errors, mig_outcomes = _check_migrations()
    if mig_errors:
        raise StartupValidationError(
            step="migrations",
            errors=mig_errors,
            detail="; ".join(mig_errors),
        )

    # 3. schema — блокирующий
    schema_errors = _check_schema(game_loop)
    if schema_errors:
        raise StartupValidationError(
            step="schema",
            errors=schema_errors,
            detail="; ".join(schema_errors),
        )

    return StartupGateResult(
        ok=True,
        step="ready",
        migrations=tuple(mig_outcomes),
        schema_errors=(),
        config_warnings=tuple(config_warnings),
        detail="startup gate passed",
    )


def get_known_config_fields() -> List[str]:
    """Имена полей Settings (верхний регистр = AIDM_ env vars).

    Используется старт-гейтом для отличия легитимных env vars
    от unknown. Берётся из Settings class annotations.
    """
    from app.core.config import Settings

    fields: List[str] = []
    for name in Settings.model_fields.keys():
        fields.append(name)
    # ModelConfig fields тоже AIDM_-доступны (env_prefix общий)
    from app.core.config import ModelConfig

    for name in ModelConfig.model_fields.keys():
        fields.append(name)
    return fields
