"""
ENIGMA Readiness Service (ADR-O-426 D70 / COV-D70 refactor).

Рефактор D70: убран устаревший хардкод про Electron/Tauri/векторные БД
(COV-D70: «readiness.py — устаревший хардкод-отчёт»). Отчёт отражает
реальное состояние startup gate и интеграций.

Контракт (сохранён от S176 test_readiness_report_structure):
  ReadinessReport: score_percent (float), checks (>=5), summary, next_steps
  ReadinessCheck: area, status ∈ {done, partial, missing}, details

Семантика статусов (вердикт В2):
  - done:    обязательное ядро готово / опциональная интеграция живёт
  - partial: опциональная интеграция деградировала (не блокирует ядро)
  - missing: обязательное ядро НЕ готово

score_percent: 100 если обязательное ядро ok; 0 если ядро не готово.
Опциональные partial не делают score 0 — только блокирующие ядро отказы.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.models.schemas import ReadinessCheck, ReadinessReport

logger = logging.getLogger(__name__)


class ReadinessService:
    """Реальный readiness-отчёт из app.state.startup_gate + startup_status.

    Не имеет собственного состояния — принимает `app_state` (FastAPI
    app.state) в report() и читает атрибуты, опубликованные lifespan.
    Совместим с legacy-вызовом `ReadinessService().report()` (без
    аргумента) — возвращает minimal-отчёт, отражающий что ядро не готово
    (lifespan не запущен или провалился).
    """

    def report(self, app_state: Optional[Any] = None) -> ReadinessReport:
        """Строит отчёт из app.state.

        Аргументы:
            app_state: FastAPI app.state (publishes startup_gate,
                startup_status, game_loop). None — fallback minimal.
        """
        checks: list[ReadinessCheck] = []
        core_ok = True  # обязательное ядро

        # ── Обязательное ядро ─────────────────────────────────────
        # 1. Startup Gate
        gate_result = getattr(app_state, "startup_gate", None) if app_state else None
        if gate_result is None:
            checks.append(
                ReadinessCheck(
                    area="Startup Gate",
                    status="missing",
                    details="Lifespan не запущен или startup-gейт провалился (см. логи).",
                )
            )
            core_ok = False
        elif gate_result.ok:
            mig_count = len(gate_result.migrations)
            warn_count = len(gate_result.config_warnings)
            checks.append(
                ReadinessCheck(
                    area="Startup Gate",
                    status="done",
                    details=f"Config → migrations ({mig_count}) → schema passed"
                    + (f"; {warn_count} unknown AIDM_ env warning(s)" if warn_count else ""),
                )
            )
        else:
            checks.append(
                ReadinessCheck(
                    area="Startup Gate",
                    status="missing",
                    details=f"step={gate_result.step}: {gate_result.detail}",
                )
            )
            core_ok = False

        # 2. Game Loop
        game_loop = getattr(app_state, "game_loop", None) if app_state else None
        if game_loop is not None:
            checks.append(
                ReadinessCheck(
                    area="Game Loop",
                    status="done",
                    details="GameLoop инициализирован в app.state",
                )
            )
        else:
            checks.append(
                ReadinessCheck(
                    area="Game Loop",
                    status="missing",
                    details="GameLoop не инициализирован — endpoints будут 500/RuntimeError",
                )
            )
            core_ok = False

        # ── Опциональные интеграции (degradation = partial, не блок) ──
        # Вердикт В2: ядро = только Startup Gate + Game Loop.
        # LLM Router / Pool / Server / VRAM — опциональные; их деградация
        # не делает score=0 (смешивание запрещено). Только обязательное
        # ядро определяет readiness сервера обслуживать запросы.
        startup_status = getattr(app_state, "startup_status", {}) if app_state else {}

        # 3. LLM Router
        llm_router_ok = self._is_router_initialized()
        checks.append(
            ReadinessCheck(
                area="LLM Router",
                status="done" if llm_router_ok else "partial",
                details="Router initialized" if llm_router_ok else "initialize_router() не отработал (degraded)",
            )
        )

        # 4. Model Pool
        pool_count = self._model_pool_count()
        checks.append(
            ReadinessCheck(
                area="Model Pool",
                status="done" if pool_count > 0 else "partial",
                details=f"{pool_count} model(s) registered",
            )
        )

        # 5. LLM Server (llama-server)
        llm_server_status = startup_status.get("llm_server", "unknown")
        llm_health_status = startup_status.get("llm_health", "unknown")
        if llm_server_status == "ready" and llm_health_status == "ready":
            checks.append(
                ReadinessCheck(
                    area="LLM Server",
                    status="done",
                    details="llama-server запущен и health=ready",
                )
            )
        elif llm_server_status in ("starting", "skipped") or llm_health_status == "checking":
            checks.append(
                ReadinessCheck(
                    area="LLM Server",
                    status="partial",
                    details=f"llama-server: {llm_server_status}, health: {llm_health_status}",
                )
            )
        else:
            checks.append(
                ReadinessCheck(
                    area="LLM Server",
                    status="partial",
                    details=f"offline: server={llm_server_status}, health={llm_health_status}",
                )
            )

        # 6. VRAM Monitor (заглушка S142 — известный долг)
        checks.append(
            ReadinessCheck(
                area="VRAM Monitor",
                status="partial",
                details="Телеметрия нулевая (заглушка S142); наблюдение не критично",
            )
        )

        # ── Score & summary ──────────────────────────────────────
        # score: 100 если обязательное ядро ok; 0 если что-то из ядра не готово.
        # Опциональные partial не делают score 0 — они про деградацию фич,
        # не про неготовность сервера обслуживать запросы.
        score = 100.0 if core_ok else 0.0

        if core_ok:
            summary = "Обязательное ядро готово; опциональные интеграции могут деградировать."
        else:
            summary = "Обязательное ядро НЕ готово — сервер не должен обслуживать запросы."

        # next_steps — живые подсказки из реального состояния
        next_steps: list[str] = []
        if gate_result is not None and gate_result.config_warnings:
            next_steps.append(
                "Проверить .env / env vars: найдены неизвестные AIDM_-переменные (см. логи)."
            )
        if llm_server_status != "ready":
            next_steps.append(
                "LLM server не готов — убедиться что llama-server запущен или URL настроен."
            )
        if not llm_router_ok or pool_count == 0:
            next_steps.append(
                "LLM Router/Pool деградированы — проверь initialize_router() / ModelPool init."
            )

        return ReadinessReport(
            score_percent=score,
            summary=summary,
            checks=checks,
            next_steps=next_steps,
        )

    @staticmethod
    def _is_router_initialized() -> bool:
        """LLM Router инициализирован? (не падает если модуль ещё не загружен)."""
        try:
            from app.services.llm.router import get_router

            r = get_router()
            return r is not None
        except Exception as e:
            # L4 (no silent failure): логируем — readiness не должен молчать
            # о причине деградации. Не блокирующий: опциональная интеграция.
            logger.debug("[READINESS] LLM Router probe failed: %s", e)
            return False

    @staticmethod
    def _model_pool_count() -> int:
        """Сколько моделей зарегистрировано в пуле."""
        try:
            from app.services.llm.provider_manager import get_model_pool

            pool = get_model_pool()
            # pool.models: Dict[str, Any]
            models = getattr(pool, "models", {})
            return len(models) if models else 0
        except Exception as e:
            logger.debug("[READINESS] Model Pool probe failed: %s", e)
            return 0
