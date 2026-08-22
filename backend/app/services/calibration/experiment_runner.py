"""
path: backend/app/services/calibration/experiment_runner.py
Назначение: Headless-прогон эксперимента калибровки на РЕАЛЬНОМ конвейере
    (ADR-O-361): чистый старт (пустой temp-saves → штатный путь «новая
    игра» загрузчика), материализованный пресет, offline-LLM (MockProvider,
    B4-FIX: environment='development'), overlay констант, N idle-тиков с
    post-commit captures, NaN-скан, счётчик L1-событий, dispose-каскад
    DriftLab. Replay-детерминизм — два независимых прогона, структурное
    сравнение.
    seed НЕ входит в ядро (KernelRNG(tick, npc_id, salt), ADR-O-301) —
    поле зарезервировано для сценарного слоя (M0-6/M1).
    wall-clock — только experiment_id-метаданные (§15.2).
Зависимости: app.core.config, game_loop_builder, preset_io,
    preset_materializer, config_overlay, llm.provider.ProviderType.
Основные сущности: ExperimentError, ExperimentConfig, ExperimentResult,
    ReplayResult, ExperimentRunner.
"""
from __future__ import annotations

import copy
import logging
import math
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.core.config import settings
from app.services.calibration.config_overlay import overlay_active, overlay_constants
from app.services.calibration.preset_io import Preset, load_preset
from app.services.calibration.preset_materializer import materialize_preset
from app.services.game_loop_builder import build_game_loop
from app.services.llm.provider import ProviderType

logger = logging.getLogger(__name__)

# Потребители констант, обязанные быть загружены до overlay (громкий FAIL
# при сборке раньше overlay). Минимальный гарантированный набор;
# остальные биндинги ловит identity-скан overlay.
_REQUIRE_LOADED: Tuple[str, ...] = ("app.services.npc.decision_hub",)


class ExperimentError(RuntimeError):
    """Громкий отказ эксперимента (L4): вложенность, битый пресет,
    падение конвейера."""


@dataclass(frozen=True)
class ExperimentConfig:
    preset_path: str
    campaign_id: str = "Open_road"
    duration_ticks: int = 150
    # Зарезервировано для сценарного слоя (M0-6/M1). Ядро детерминировано
    # KernelRNG(tick, npc_id, salt) и от seed не зависит (ADR-O-301).
    seed: int = 7331


@dataclass
class ExperimentResult:
    experiment_id: str
    config: ExperimentConfig
    preset_id: str
    ticks_executed: int
    statuses: List[str] = field(default_factory=list)
    npc_captures: List[List[Dict[str, Any]]] = field(default_factory=list)
    rel_captures: List[Dict[str, Any]] = field(default_factory=list)
    final_npc_state: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    nan_count: int = 0
    l1_event_count: int = 0


@dataclass(frozen=True)
class ReplayResult:
    deterministic: bool
    diff_fields: Tuple[str, ...]


def _count_nan(obj: Any) -> int:
    """Рекурсивный NaN-скан по финальным NPC-диктам (ADR-O-207 spirit)."""
    if isinstance(obj, float):
        return 1 if math.isnan(obj) else 0
    if isinstance(obj, dict):
        return sum(_count_nan(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return sum(_count_nan(v) for v in obj)
    return 0


class ExperimentRunner:
    """Один эксперимент = один прогон. Параллельность — только процессы."""

    def run(self, config: ExperimentConfig) -> ExperimentResult:
        if overlay_active():
            raise ExperimentError(
                "overlay активен — вложенные эксперименты запрещены (ADR-O-361)"
            )
        preset: Preset = load_preset(config.preset_path)

        # ── Изоляция настроек (restore в finally при любом исходе) ──
        _orig_saves = settings.saves_dir
        _orig_env = settings.environment
        _orig_data_dir = Path(settings.data_dir)
        _model_cfg = settings.available_models.get("qwen_7b")
        _orig_provider = getattr(_model_cfg, "provider_type", None) if _model_cfg else None

        # ПУСТОЙ temp-saves = чистый старт: runtime_path не существует →
        # load_npcs_merged возвращает static (штатный путь «новая игра»).
        # S210: калибровочная песочница = прогон С ЧИСТОГО СТАРТА (temp-saves,
        # MOCK, throwaway GameLoop), НЕ ретро-симуляция живой кампании (Rule 25
        # касается нагона пропущенного ИГРОВОГО времени). Формализовано в
        # INV-NO-RETRO-SIM whitelist по маркеру файла.
        temp_root = Path(tempfile.mkdtemp(prefix="calib_exp_"))
        experiment_id = f"calib_{uuid.uuid4().hex[:12]}"
        try:
            settings.saves_dir = str(temp_root)
            settings.environment = "development"
            if _model_cfg is not None:
                _model_cfg.provider_type = ProviderType.MOCK

            with materialize_preset(preset):
                game_loop = build_game_loop(data_dir=_orig_data_dir)
                try:
                    with overlay_constants(
                        preset.constants, require_loaded=_REQUIRE_LOADED
                    ):
                        statuses: List[str] = []
                        npc_captures: List[List[Dict[str, Any]]] = []
                        rel_captures: List[Dict[str, Any]] = []
                        # DriftLab-паттерн доступа (публичного API нет)
                        engine = game_loop._get_life_engine()  # noqa: ENIGMA002
                        for _ in range(config.duration_ticks):
                            tick_result = game_loop.idle_tick(config.campaign_id)
                            statuses.append(str(tick_result.get("status", "unknown")))
                            npc_captures.append(
                                copy.deepcopy(
                                    engine.get_npc_states(config.campaign_id)
                                )
                            )
                            rel_captures.append(
                                game_loop.memory_manager.get_relationships(
                                    config.campaign_id
                                )
                            )
                        final_raw = npc_captures[-1] if npc_captures else []
                        final_by_id = {
                            n.get("id", n.get("npc_id", "unknown")): n
                            for n in final_raw
                        }
                        nan_count = sum(_count_nan(n) for n in final_raw)
                        l1_event_count = 0
                        chron = getattr(game_loop._tick_orch, "l1_chronicle", None)  # noqa: ENIGMA002
                        if chron is not None:
                            for npc_id in final_by_id:
                                l1_event_count += len(chron.query_raw(npc_id))
                finally:
                    self._dispose(game_loop)
        finally:
            settings.saves_dir = _orig_saves
            settings.environment = _orig_env
            if _model_cfg is not None and _orig_provider is not None:
                _model_cfg.provider_type = _orig_provider
            shutil.rmtree(temp_root, ignore_errors=True)

        return ExperimentResult(
            experiment_id=experiment_id,
            config=config,
            preset_id=preset.preset_id,
            ticks_executed=config.duration_ticks,
            statuses=statuses,
            npc_captures=npc_captures,
            rel_captures=rel_captures,
            final_npc_state=final_by_id,
            nan_count=nan_count,
            l1_event_count=l1_event_count,
        )

    def replay_determinism(self, config: ExperimentConfig) -> ReplayResult:
        """Два независимых прогона, структурное сравнение (M0-AC-004).

        Между прогонами — event_bus.clear(): глобальная шина singleton, и
        подписки первого GameLoop (не отписанные dispose) дали бы двойную
        доставку во втором прогоне. clear() — тестовая гигиена шины
        (наш контур и есть тестовая инфраструкция).
        """
        run_1 = self.run(config)
        from app.services.events.event_bus import get_event_bus

        get_event_bus().clear()
        run_2 = self.run(config)

        diff: List[str] = []
        if run_1.preset_id != run_2.preset_id:
            diff.append("preset_id")
        if run_1.statuses != run_2.statuses:
            diff.append("statuses")
        if run_1.nan_count != run_2.nan_count:
            diff.append("nan_count")
        if run_1.l1_event_count != run_2.l1_event_count:
            diff.append("l1_event_count")
        if run_1.final_npc_state != run_2.final_npc_state:
            diff.append("final_npc_state")
        if run_1.rel_captures != run_2.rel_captures:
            diff.append("rel_captures")
        if run_1.npc_captures != run_2.npc_captures:
            diff.append("npc_captures")
        return ReplayResult(deterministic=not diff, diff_fields=tuple(diff))

    @staticmethod
    def _dispose(game_loop: Any) -> None:
        """DriftLab-порядок: flush LifeEngine → dispose (оба SQLite) →
        reset singleton. Ошибка шага логируется (не silent), но не
        роняет restore настроек."""
        from app.services.npc.life_engine import get_life_engine, reset_life_engine

        try:
            get_life_engine().cleanup_all_campaigns()
        except Exception as exc:
            logger.warning("[CALIB_RUNNER] LifeEngine flush error: %s", exc)
        try:
            game_loop.dispose()
        except Exception as exc:
            logger.warning("[CALIB_RUNNER] GameLoop.dispose error: %s", exc)
        try:
            reset_life_engine()
        except Exception as exc:
            logger.warning("[CALIB_RUNNER] LifeEngine reset error: %s", exc)