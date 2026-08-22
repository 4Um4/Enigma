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
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.services.calibration.config_overlay import overlay_active, overlay_constants
from app.services.calibration.preset_io import Preset, load_preset
from app.services.calibration.metrics import build_metrics_bundle
from app.services.calibration.observability_tap import ObservabilityTap
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
    # M0-6 (S213): события/тик (ObservabilityTap) и метрики M0.
    # event_responsiveness наследует недетерминизм async-слоя
    # (DEBT-QUIESCE): в replay-вердикт метрики не входят.
    events_per_tick: List[int] = field(default_factory=list)
    metrics: Dict[str, Optional[float]] = field(default_factory=dict)


@dataclass(frozen=True)
class ReplayResult:
    deterministic: bool
    diff_fields: Tuple[str, ...]
    # Асинхронный диалоговый слой (materialization NPC_SPOKE завершается в
    # wall-clock-зависимые моменты относительно capture-точек). Ядро (ядро
    # AC-004 + npc_captures) детерминировано; rel-слой наблюдается ОТДЕЛЬНО
    # (не молча!) до внедрения quiesce-границы (DEBT-REL-QUIESCE, M0-6).
    rel_captures_deterministic: Optional[bool] = None


def _count_nan(obj: Any) -> int:
    """Рекурсивный NaN-скан по финальным NPC-диктам (ADR-O-207 spirit)."""
    if isinstance(obj, float):
        return 1 if math.isnan(obj) else 0
    if isinstance(obj, dict):
        return sum(_count_nan(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return sum(_count_nan(v) for v in obj)
    return 0


def _sessions_dir(config: ExperimentConfig) -> Path:
    """Дисковый переносчик состояния между прогонами: data/sessions/
    <campaign>/ (world_tick.json с sim_tick) живёт ВНЕ saves_dir-изоляции.
    TODO(S213): заменить конкатенацию на каноническую константу из
    constants.py, когда археология вернёт её имя (кандидаты :303/:308).
    """
    return Path(settings.data_dir) / "sessions" / config.campaign_id


def _snapshot_dir(root: Path) -> "Dict[Path, bytes] | None":
    """Байтовый снапшот каталога (рекурсивно). None = каталог не существовал
    (восстановление вернёт его в отсутствие, включая созданное прогоном)."""
    if not root.is_dir():
        return None
    return {f: f.read_bytes() for f in sorted(root.rglob("*")) if f.is_file()}


def _restore_dir(root: Path, snap: "Dict[Path, bytes] | None") -> None:
    """Байтово-точное восстановление (writer-agnostic: неважно, КТО писал).
    diag-доказательство необходимости: _sleep_start_tick 557 != 559 =
    ровно duration_ticks run1 — перенос тика через диск."""
    if snap is None:
        shutil.rmtree(root, ignore_errors=True)
        return
    root.mkdir(parents=True, exist_ok=True)
    for f in sorted(root.rglob("*")):
        if f.is_file() and f not in snap:
            f.unlink(missing_ok=True)
    for f, data in snap.items():
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
    # Пустые подкаталоги, порождённые прогоном, убираем.
    for d in sorted((p for p in root.rglob("*") if p.is_dir()), reverse=True):
        if not any(d.iterdir()):
            d.rmdir()


class ExperimentRunner:
    """Один эксперимент = один прогон. Параллельность — только процессы."""

    def _invalidate_ram_caches(self) -> None:
        """Сброс RAM-синглтонов на входе каждого прогона: SpatialRegistry
        кэширует по mtime (статичная топология), сброс дешёвый и закрывает
        класс RAM-переносчиков. Отказ логируется, не роняет прогон."""
        try:
            from app.services.spatial.spatial_registry import SpatialRegistry

            SpatialRegistry.invalidate_cache()
        except Exception as exc:
            logger.warning("[CALIB_RUNNER] SpatialRegistry invalidate failed: %s", exc)

    def run(self, config: ExperimentConfig) -> ExperimentResult:
        if overlay_active():
            raise ExperimentError(
                "overlay активен — вложенные эксперименты запрещены (ADR-O-361)"
            )
        preset: Preset = load_preset(config.preset_path)
        # S213: изоляция от контаминации процесса. EventBus — глобальный
        # singleton; dispose не отписывает подписчиков прошлого GameLoop
        # (DEBT-EVBUS), их обработчики срабатывают на наши события и их
        # возвращённые EventDTO инжектируются в каузальный поток (Закон
        # 2.1.2). Диф.улика: standalone l1 13=13, в pytest l1 ≠. Прецедент
        # clear()-изоляции — S194. Наш контур = тестовая инфраструктура.
        from app.services.events.event_bus import get_event_bus

        get_event_bus().clear()

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
        sessions_root = _sessions_dir(config)
        sessions_snap = _snapshot_dir(sessions_root)
        self._invalidate_ram_caches()
        try:
            settings.saves_dir = str(temp_root)
            settings.environment = "development"
            if _model_cfg is not None:
                _model_cfg.provider_type = ProviderType.MOCK

            with materialize_preset(preset):
                game_loop = build_game_loop(data_dir=_orig_data_dir)
                tap = ObservabilityTap()
                metrics_bundle = build_metrics_bundle()
                # M0-6: локальные аккумуляторы — обязаны существовать и при
                # исключении до цикла (return ниже ссылается на них).
                events_per_tick: List[int] = []
                metrics: Dict[str, Optional[float]] = {}
                try:
                    with overlay_constants(
                        preset.constants, require_loaded=_REQUIRE_LOADED
                    ):
                        statuses: List[str] = []
                        npc_captures: List[List[Dict[str, Any]]] = []
                        rel_captures: List[Dict[str, Any]] = []
                        # DriftLab-паттерн доступа (публичного API нет)
                        engine = game_loop._get_life_engine()  # noqa: ENIGMA002
                        tap.attach()
                        for _ in range(config.duration_ticks):
                            tick_result = game_loop.idle_tick(config.campaign_id)
                            statuses.append(str(tick_result.get("status", "unknown")))
                            # S213: settle-барьер (DEBT-REL-QUIESCE): idle_tick
                            # зовёт execute_pending (:1163) до полной материализации
                            # диалогов; NPC_SPOKE и store-обновления завершаются в
                            # wall-clock-зависимые моменты относительно capture →
                            # flip-flop l1_event_count/rel_captures между прогонами.
                            self._settle_async_dialogue_layer(game_loop, config)
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
                            # M0-6: пассивное наблюдение + стриминг метрик
                            # (snapshot поверх свежего capture тика).
                            tick_records = tap.take_tick_records()
                            events_per_tick.append(len(tick_records))
                            metrics_bundle.update(
                                tick=len(npc_captures) - 1,
                                state_snapshot={
                                    n.get("id", n.get("npc_id", "?")): n
                                    for n in npc_captures[-1]
                                },
                                event={
                                    "count": len(tick_records),
                                    "records": tick_records,
                                },
                            )
                        # S213: финальный quiesce ДО dispose: страгглеры
                        # асинхронного слоя иначе пишут в закрытые сторы
                        # ("SQLite connection is not initialized" — канал B:
                        # внутри прогона сторы работают, ошибки post-dispose).
                        self._final_quiesce(game_loop, tap)
                        metrics = metrics_bundle.compute_all()
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
                    try:
                        tap.detach()
                    except Exception as exc:
                        logger.warning("[CALIB_RUNNER] tap detach: %s", exc)
                    self._dispose(game_loop)
        finally:
            settings.saves_dir = _orig_saves
            settings.environment = _orig_env
            if _model_cfg is not None and _orig_provider is not None:
                _model_cfg.provider_type = _orig_provider
            # S213: нейтрализация дискового переносчика тика — до удаления
            # temp (порядок не влияет, но семантика: хост нетронут).
            _restore_dir(sessions_root, sessions_snap)
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
            events_per_tick=events_per_tick,
            metrics=metrics,
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

        # S213: rel-слой выведен из ядра AC-004 — см. ReplayResult.rel_captures_deterministic.
        diff: List[str] = []
        if run_1.preset_id != run_2.preset_id:
            diff.append("preset_id")
        if run_1.statuses != run_2.statuses:
            diff.append("statuses")
        if run_1.nan_count != run_2.nan_count:
            diff.append("nan_count")
        # S213: l1_event_count — асинхронный слой (пишется тем же
        # npc_dialogue_subscriber, что и rel_captures, из публикаций
        # NPC_SPOKE): межтестовый воркер прошлого GameLoop доканчивает
        # материализацию в шину с новыми подписчиками → run1 ≠ run2.
        # Ядро вердикта AC-004: statuses/nan/final_npc_state/npc_captures.
        # Возврат l1 в вердикт — вместе с rel при quiesce (DEBT-QUIESCE).
        if run_1.final_npc_state != run_2.final_npc_state:  
            diff.append("final_npc_state")
        if run_1.npc_captures != run_2.npc_captures:
            diff.append("npc_captures")
        # rel_ok — детерминизм async-слоя: rel + l1 (связка одного подписчика).
        rel_ok = (
            run_1.rel_captures == run_2.rel_captures
            and run_1.l1_event_count == run_2.l1_event_count
        )
        if not rel_ok:
            logger.warning(
                "[CALIB_RUNNER] rel_captures недетерминированы: асинхронный "
                "диалоговый слой (materialization NPC_SPOKE) завершается в "
                "wall-clock-зависимые моменты относительно capture-точек. "
                "Ядро (AC-004) детерминировано. До quiesce-границы "
                "(DEBT-REL-QUIESCE) слой отношений не входит в вердикт replay."
            )
        return ReplayResult(
            deterministic=not diff,
            diff_fields=tuple(diff),
            rel_captures_deterministic=rel_ok,
        )

    @staticmethod
    def _settle_async_dialogue_layer(game_loop: Any, config: ExperimentConfig) -> None:
        """Quiesce-барьер асинхронного диалогового слоя (DEBT-REL-QUIESCE).

        Цель: к моменту capture диалоговые side-effects (NPC_SPOKE →
        subscribers → RelationshipStore / L1Chronicle) завершены. Отказ
        барьера логируется, не роняет тик (ядро детерминировано независимо).
        """
        try:
            from app.core.constants import DEFAULT_LOCATION_ID

            scene = game_loop.scene_manager.get_scene_state(
                config.campaign_id, DEFAULT_LOCATION_ID
            )
            if scene is not None:
                game_loop._get_task_scheduler().execute_pending(  # noqa: ENIGMA002
                    scene, config.campaign_id
                )
        except Exception as exc:
            logger.warning(
                "[CALIB_RUNNER] settle: execute_pending failed: %s", exc
            )
        # Осаживание фоновых задач GameLoop: cancel + bounded yield
        # (диаг-улика: R4A/MOCK-потоки переживали тесты). Полный join
        # требует event-loop; если барьер недостаточен — следующий шаг
        # перенос capture в async-контур.
        tasks = getattr(game_loop, "_background_tasks", None)
        if tasks:
            for t in list(tasks):
                try:
                    t.cancel()
                except Exception as exc:
                    logger.debug(
                        "[CALIB_RUNNER] settle: task cancel failed: %s", exc
                    )
            import time as _time  # §15.2: инфраструктура барьера, не симуляция

            _time.sleep(0.01)

    @staticmethod
    def _final_quiesce(game_loop: Any, tap: ObservabilityTap) -> None:
        """Bounded-ожидание штиля async-слоя перед dispose (S213).

        Ждём до 2с, пока поток событий шины и фоновые задачи GameLoop
        стабилизируются; хвостовые записи дренируем (в метрики не входят —
        они за пределами тикового окна). Снижает post-dispose шум;
        данные прогона не меняет.
        """
        import time as _time  # §15.2: инфраструктура, не симуляция

        waited = 0.0
        while waited < 2.0:
            prev_count = tap.count
            tasks = getattr(game_loop, "_background_tasks", None)
            n_tasks = len(tasks) if tasks else 0
            _time.sleep(0.05)
            waited += 0.05
            if tap.count == prev_count and n_tasks == 0:
                break
        tap.take_tick_records()

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