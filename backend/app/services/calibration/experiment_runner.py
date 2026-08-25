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

    # === M1: Интерактивный API для Pygame UI (ADR-O-361) ===
    def start(self, config: ExperimentConfig) -> str:
        """Запускает интерактивную сессию: изоляция, сборка GameLoop, overlay.
        Возвращает experiment_id. GameLoop хранится в self._active_game_loop."""
        if overlay_active():
            raise ExperimentError("overlay активен — вложенные эксперименты запрещены")
        if hasattr(self, "_active_game_loop") and self._active_game_loop:
            raise ExperimentError("Сессия уже активна. Используйте stop() перед новым start().")

        self._active_config = config
        self._active_preset = load_preset(config.preset_path)
        
        from app.services.events.event_bus import get_event_bus
        get_event_bus().clear()

        self._orig_saves = settings.saves_dir
        self._orig_env = settings.environment
        self._orig_data_dir = Path(settings.data_dir)
        self._model_cfg = settings.available_models.get("qwen_7b")
        self._orig_provider = getattr(self._model_cfg, "provider_type", None) if self._model_cfg else None

        self._temp_root = Path(tempfile.mkdtemp(prefix="calib_exp_"))
        self._experiment_id = f"calib_{uuid.uuid4().hex[:12]}"
        self._sessions_root = _sessions_dir(config)
        self._sessions_snap = _snapshot_dir(self._sessions_root)
        self._invalidate_ram_caches()

        settings.saves_dir = str(self._temp_root)
        settings.environment = "development"
        if self._model_cfg is not None:
            self._model_cfg.provider_type = ProviderType.MOCK

        # materialize_preset и overlay_constants держат контекст открытыми
        self._preset_ctx = materialize_preset(self._active_preset)
        self._preset_ctx.__enter__()
        
        self._active_game_loop = build_game_loop(data_dir=self._orig_data_dir)
        # M1: зеркалирует P-MVP-1 из new_game. Без init_campaign у
        # action_compiler отсутствует _campaign_id — P2-мост в
        # RelationshipStore (SSOT) мёртв: дельты trust исчезают молча
        # в guard `if self._relationship_store and self._campaign_id`.
        _mvp_ctrl = getattr(self._active_game_loop, "mvp_controller", None)
        if _mvp_ctrl is not None:
            _mvp_ctrl.init_campaign(config.campaign_id)
        self._active_tap = ObservabilityTap()
        self._active_metrics = build_metrics_bundle()
        self._active_tap.attach()
        
        self._overlay_ctx = overlay_constants(
            self._active_preset.constants, require_loaded=_REQUIRE_LOADED
        )
        self._overlay_ctx.__enter__()

        self._statuses = []
        self._npc_captures = []
        self._rel_captures = []
        self._events_per_tick = []
        self._ticks_executed = 0

        return self._experiment_id

    def step(self, ticks: int = 1) -> Dict[str, Any]:
        """Выполняет N тиков и возвращает текущее состояние NPC (LiveStateDTO)."""
        if not hasattr(self, "_active_game_loop") or not self._active_game_loop:
            raise ExperimentError("Сессия не запущена. Вызовите start() сначала.")

        config = self._active_config
        game_loop = self._active_game_loop
        engine = game_loop._get_life_engine()  # noqa: ENIGMA002

        # M1/Sprint 1: Временная инъекция события для проверки динамики Trust
        _test_intervention = None
        if self._ticks_executed == 10:
            from app.contracts.interventions import InterventionEvent
            # M1: ядро не парсит текст (L4.1) — семантика передаётся
            # структурированно, как это делает IntentCompressor на DM-пути.
            # Контракт _process_player_action: semantic_action + target_reference
            # (guard) + target_id (резолв цели). Фабрика прокидывает kwargs в payload.
            _test_intervention = InterventionEvent.from_player_action(
                action_text="помочь",
                player_name="player",
                tick=self._ticks_executed,
                target_id="maid_lusya",
                semantic_action="HELP",
                target_reference="maid_lusya",
            )
            logger.info("[CALIB_TEST_INJECT] Внедрено событие: помощь Люсе на тике 10")

        for _ in range(ticks):
            interventions = [_test_intervention] if _test_intervention and self._ticks_executed == 10 else []
            tick_result = game_loop.idle_tick(config.campaign_id, interventions=interventions)
            self._statuses.append(str(tick_result.get("status", "unknown")))
            self._settle_async_dialogue_layer(game_loop, config)
            
            self._npc_captures.append(copy.deepcopy(engine.get_npc_states(config.campaign_id)))
            self._rel_captures.append(game_loop.memory_manager.get_relationships(config.campaign_id))
            
            tick_records = self._active_tap.take_tick_records()
            self._events_per_tick.append(len(tick_records))
            self._active_metrics.update(
                tick=len(self._npc_captures) - 1,
                state_snapshot={
                    n.get("id", n.get("npc_id", "?")): n for n in self._npc_captures[-1]
                },
                event={"count": len(tick_records), "records": tick_records},
            )
            self._ticks_executed += 1

        # Возвращаем текущее состояние NPC (последний capture)
        return {
            "tick": self._ticks_executed,
            "npcs": self._npc_captures[-1] if self._npc_captures else [],
            "relationships": self._rel_captures[-1] if self._rel_captures else {},
        }

    def stop(self) -> ExperimentResult:
        """Завершает сессию: quiesce, вычисление метрик, очистка ресурсов."""
        if not hasattr(self, "_active_game_loop") or not self._active_game_loop:
            raise ExperimentError("Сессия не запущена.")

        game_loop = self._active_game_loop
        config = self._active_config
        tap = self._active_tap

        self._final_quiesce(game_loop, tap)
        metrics = self._active_metrics.compute_all()
        
        final_raw = self._npc_captures[-1] if self._npc_captures else []
        final_by_id = {
            n.get("id", n.get("npc_id", "unknown")): n for n in final_raw
        }
        nan_count = sum(_count_nan(n) for n in final_raw)
        
        l1_event_count = 0
        chron = getattr(game_loop._tick_orch, "l1_chronicle", None)  # noqa: ENIGMA002
        if chron is not None:
            for npc_id in final_by_id:
                l1_event_count += len(chron.query_raw(npc_id))

        # Закрытие контекстов overlay и preset
        self._overlay_ctx.__exit__(None, None, None)
        self._preset_ctx.__exit__(None, None, None)

        try:
            tap.detach()
        except Exception as exc:
            logger.warning("[CALIB_RUNNER] tap detach: %s", exc)
        self._dispose(game_loop)

        # Восстановление настроек
        settings.saves_dir = self._orig_saves
        settings.environment = self._orig_env
        if self._model_cfg is not None and self._orig_provider is not None:
            self._model_cfg.provider_type = self._orig_provider
        _restore_dir(self._sessions_root, self._sessions_snap)
        shutil.rmtree(self._temp_root, ignore_errors=True)

        result = ExperimentResult(
            experiment_id=self._experiment_id,
            config=config,
            preset_id=self._active_preset.preset_id,
            ticks_executed=self._ticks_executed,
            statuses=self._statuses,
            npc_captures=self._npc_captures,
            rel_captures=self._rel_captures,
            final_npc_state=final_by_id,
            nan_count=nan_count,
            l1_event_count=l1_event_count,
            events_per_tick=self._events_per_tick,
            metrics=metrics,
        )
        
        # Очистка атрибутов состояния
        del self._active_game_loop
        del self._active_config
        del self._active_preset
        del self._overlay_ctx
        del self._preset_ctx

        return result

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