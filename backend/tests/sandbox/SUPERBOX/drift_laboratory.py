"""
ENIGMA Drift Laboratory — Каузальная стресс-машина (ADR-O-201 ФАЗА 2.5)

Запуск:
  cd backend
  python -m tests.sandbox.SUPERBOX.run drift mass_traversal
  python -m tests.sandbox.SUPERBOX.run drift save_load_storm
  python -m tests.sandbox.SUPERBOX.run drift chunk_migration
  python -m tests.sandbox.SUPERBOX.run drift long_horizon

Принцип: Тот же код, что и production runtime. Не копия.
Использует реальный TickOrchestrator с реальными сервисами.

path: backend/tests/sandbox/SUPERBOX/drift_laboratory.py
Назначение: Стресс-тестирование Dual Rail pipeline (ADR-O-201)
Зависимости: app.services.tick_orchestrator, app.services.scene_state_manager, matplotlib (опционально)
Основные сущности: DriftConfig, DriftResult, DriftLaboratory, DriftReporter
"""
from __future__ import annotations

import csv
import json
import sys
import os
import time
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# SUPERBOX — добавляем backend/ в path (на 2 уровня выше)
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


# ─── Конфигурация ───────────────────────────────────────────────────────

@dataclass
class DriftConfig:
    """Настройки drift-эксперимента."""
    campaign_id: str = "Open_road"
    location_id: str = "tavern_silver_wolf"

    # Режимы
    mass_traversal_ticks: int = 10_000       # ~30 NPC × 10000 = 300k comparisons
    save_load_storm_ticks: int = 5_000       # save/load каждые 50 тиков
    chunk_migration_ticks: int = 10_000       # boundary transitions
    long_horizon_ticks: int = 100_000         # idle drift

    # Интервал сбора статистики
    snapshot_interval: int = 1_000

    # save/load storm
    save_load_interval: int = 50

    # replay determinism
    replay_determinism_ticks: int = 10_000     # 2 × 10k тиков с одинаковым seed

    # projection parity (CSSE Stage 2)
    projection_parity_ticks: int = 10_000      # 10k тиков dual-reality sync

    # idle simulation stability
    idle_stability_ticks: int = 1000           # 1000 тиков для проверки циклов расписания


@dataclass
class DriftSnapshot:
    """Срез drift-статистики в момент времени."""
    tick: int
    total_comparisons: int
    drift_A: int = 0   # Cosmetic
    drift_B: int = 0   # Projection
    drift_C: int = 0   # Topological
    drift_D: int = 0   # Causal
    drift_E: int = 0   # Ontological
    elapsed_seconds: float = 0.0


@dataclass
class DriftResult:
    """Полный результат эксперимента."""
    mode: str
    config: DriftConfig
    snapshots: List[DriftSnapshot] = field(default_factory=list)
    final_stats: Dict[str, int] = field(default_factory=dict)

    @property
    def total_comparisons(self) -> int:
        return self.snapshots[-1].total_comparisons if self.snapshots else 0

    @property
    def has_structural_drift(self) -> bool:
        """True если обнаружен Class C/D/E drift."""
        return any(s.drift_C > 0 or s.drift_D > 0 or s.drift_E > 0 for s in self.snapshots)

    @property
    def phase3_ready(self) -> bool:
        """True если можно переходить к ФАЗЕ 3 (0 C/D/E + ≥100k comparisons)."""
        if self.total_comparisons < 100_000:
            return False
        return not self.has_structural_drift


# ─── Ядро лаборатории ──────────────────────────────────────────────────

# ─── Константы Replay Determinism ────────────────────────────────────
_REPLAY_SEED = 54321
_EXCLUDE_FROM_SCENE_HASH = frozenset({
    "last_save_real_time",   # time.time() — temporal entropy
    "_version",              # монотонный счётчик
    "campaign_id",           # добавляется при чтении, не часть мира
    "snapshot_tick",         # удаляется при чтении, но на всякий случай
})

# ─── RCOC: RNG Consumption Order Contract ────────────────────────────
# Архитектурный принцип, не код. Формализован через Replay Determinism.
#
# RCOC-1: При одинаковом seed мир обязан воспроизводиться бит-в-бит.
# RCOC-2: Любое изменение RNG consumption trace должно быть
#          осознанным ADR-изменением.
# RCOC-3: Replay determinism имеет больший приоритет,
#          чем совпадение количества RNG вызовов.
#
# Инструмент верификации: _mode_replay_determinism (Mode E).
# Доказательство: REPLAY_DETERMINISM_REPORT (hash MATCH при seed=54321).
# ─────────────────────────────────────────────────────────────────────


class DriftLaboratory:
    """
    Каузальная стресс-машина.

    Использует РЕАЛЬНЫЙ TickOrchestrator с РЕАЛЬНЫМИ сервисами.
    Dual Rail встроен по определению — _apply_with_shadow_observation
    вызывается при каждом spatial change.
    """

    def __init__(self, config: DriftConfig) -> None:
        self.config = config
        self._orchestrator = None
        self._scene_manager = None
        self._scene_state: dict = {}
        self._persistence_path: Optional[Path] = None
        # Execution Boundary Lock
        self._active_override: bool = False
        self._original_saves_dir: Optional[str] = None
        self._original_data_dir: Optional[str] = None

    def run(self, mode: str) -> DriftResult:
        """Запускает эксперимент в заданном режиме."""
        print(f"\n{'='*60}")
        print(f"DRIFT LABORATORY — Mode: {mode}")
        print(f"{'='*60}")

        result = DriftResult(mode=mode, config=self.config)

        try:
            self._setup()

            mode_map = {
                "mass_traversal": self._mode_mass_traversal,
                "save_load_storm": self._mode_save_load_storm,
                "chunk_migration": self._mode_chunk_migration,
                "long_horizon": self._mode_long_horizon,
                "replay_determinism": self._mode_replay_determinism,
                "projection_parity": self._mode_projection_parity,
                "idle_simulation_stability": self._mode_idle_simulation_stability,
            }

            runner = mode_map.get(mode)
            if runner is None:
                print(f"Неизвестный режим: {mode}")
                print(f"Доступные: {', '.join(mode_map.keys())}")
                return result

            runner(result)

        finally:
            self._teardown()

        return result

    # ─── Setup / Teardown ────────────────────────────────────────────

    def _setup(self) -> None:
        """Собирает РЕАЛЬНЫЙ сервисный стек через build_game_loop.

        Execution Boundary Lock: настройки изолируются через
        try/finally с гарантированным restore даже при exception.
        Повторный _setup() без _teardown() запрещён.
        """
        # Guard: повторная инициализация без teardown
        if self._active_override:
            raise RuntimeError("[DRIFT_LAB] _setup() вызван без _teardown() — утечка конфигурации")

        from app.services.game_loop_builder import build_game_loop
        from app.core.config import settings

        # Сохраняем оригинальные настройки (restore при любом исходе)
        self._original_saves_dir = settings.saves_dir
        self._original_data_dir = getattr(settings, 'data_dir', None)

        # Создаём временную директорию для persistence (не мусорим в saves/)
        self._temp_dir = tempfile.mkdtemp(prefix="drift_lab_")
        temp_path = Path(self._temp_dir)

        # Копируем editor JSON (SpatialService нужен для графа)
        _project_root = Path(__file__).resolve().parents[3]
        data_src = _project_root / "frontend" / "map_editor" / "campaigns" / self.config.campaign_id
        data_dst = temp_path / "data" / self.config.campaign_id
        if data_src.exists():
            data_dst.mkdir(parents=True, exist_ok=True)
            for loc_dir in data_src.iterdir():
                if loc_dir.is_dir():
                    dst_loc = data_dst / "locations" / loc_dir.name
                    dst_loc.mkdir(parents=True, exist_ok=True)
                    for f in loc_dir.iterdir():
                        if f.is_file():
                            shutil.copy2(f, dst_loc / f.name)

        # Копируем NPC config (npc_loader читает из data/campaigns)
        npc_src = _project_root / "backend" / "data" / "campaigns" / self.config.campaign_id
        npc_dst = temp_path / "campaigns" / self.config.campaign_id
        if npc_src.exists():
            npc_dst.mkdir(parents=True, exist_ok=True)
            for f in npc_src.iterdir():
                if f.is_file():
                    shutil.copy2(f, npc_dst / f.name)

        # Копируем saves (runtime state + player avatar)
        saves_src = _project_root / "saves"
        saves_dst = temp_path / "saves"
        if saves_src.exists():
            shutil.copytree(saves_src, saves_dst, dirs_exist_ok=True)

        # Изолируем конфигурацию — override settings
        settings.saves_dir = str(saves_dst)
        self._active_override = True  # Lock

        try:
            # Собираем РЕАЛЬНЫЙ GameLoop (как при startup)
            self._game_loop = build_game_loop(data_dir=temp_path / "data")

            # Доступ к внутреннему TickOrchestrator для чтения drift_stats
            self._orchestrator = self._game_loop._tick_orch

            print(f"[DRIFT_LAB] GameLoop built via build_game_loop()")
            print(f"[DRIFT_LAB] Temp dir: {self._temp_dir}")
            print(f"[DRIFT_LAB] Saves dir: {settings.saves_dir}")

            # Инициализируем доступ к scene_manager/scene_state (нужны для save_load_storm)
            self._scene_manager = self._game_loop.scene_manager
            self._scene_state = self._scene_manager.get_scene_state(
                self.config.campaign_id,
                self.config.location_id,
            ) or {}
        except Exception:
            # При любой ошибке — восстанавливаем настройки
            self._restore_settings()
            raise

    def _teardown(self) -> None:
        """Очищает временные файлы и восстанавливает настройки.

        Гарантированный restore даже при exception.
        SQLite соединения закрываются ДО удаления файлов.
        """
        # 1. Восстанавливаем настройки ВСЕГДА
        self._restore_settings()

        # 2. Закрываем SQLite соединения (иначе Windows не удалит файл)
        self._close_sqlite_connections()

        # 3. Удаляем временную директорию
        if hasattr(self, '_temp_dir') and os.path.exists(self._temp_dir):
            try:
                shutil.rmtree(self._temp_dir)
                print(f"[DRIFT_LAB] Temp dir cleaned: {self._temp_dir}")
            except Exception as e:
                print(f"[DRIFT_LAB] Warning: не удалось удалить {self._temp_dir}: {e}")
                # На Windows файл может быть ещё занят — пробуем ещё раз через 1с
                time.sleep(1.0)
                try:
                    shutil.rmtree(self._temp_dir)
                    print(f"[DRIFT_LAB] Temp dir cleaned (retry): {self._temp_dir}")
                except Exception:
                    print(f"[DRIFT_LAB] Temp dir сохранён для ручной очистки: {self._temp_dir}")

    def _restore_settings(self) -> None:
        """Восстанавливает оригинальные настройки. Безопасен при повторном вызове."""
        if not self._active_override:
            return

        from app.core.config import settings

        if hasattr(self, '_original_saves_dir'):
            settings.saves_dir = self._original_saves_dir
        if hasattr(self, '_original_data_dir') and self._original_data_dir:
            settings.data_dir = self._original_data_dir

        self._active_override = False  # Unlock
        print(f"[DRIFT_LAB] Settings restored: saves_dir={settings.saves_dir}")

    def _close_sqlite_connections(self) -> None:
        """Закрывает все ресурсы через GameLoop.dispose() + LifeEngine singleton reset.
        
        Порядок критичен:
        1. Flush LifeEngine (persistence ещё открыт) → данные не теряются
        2. GameLoop.dispose() (закрывает ОБА SQLite: enigma_runtime.db + enigma_memory.db)
        3. reset_life_engine() (обнуляет singleton, cache уже пуст → flush no-op)
        
        До фикса: self._game_loop._persistence не существует (GameLoop хранит
        persistence внутри scene_manager), enigma_memory.db никогда не закрывался
        → WinError 32 на Windows.
        """
        # 1. Flush LifeEngine cache пока persistence ещё открыт
        try:
            from app.services.npc.life_engine import get_life_engine
            engine = get_life_engine()
            engine.cleanup_all_campaigns()
        except Exception as e:
            print(f"[DRIFT_LAB] Warning: LifeEngine flush error: {e}")
        
        # 2. GameLoop.dispose() — закрывает ОБА SQLite connections
        if hasattr(self, '_game_loop') and self._game_loop is not None:
            try:
                self._game_loop.dispose()
            except Exception as e:
                print(f"[DRIFT_LAB] Warning: GameLoop.dispose() error: {e}")
        
        # 3. Сбрасываем глобальный синглтон LifeEngine
        # Cache уже пуст от cleanup_all_campaigns(), повторный flush в shutdown — no-op
        try:
            from app.services.npc.life_engine import reset_life_engine
            reset_life_engine()
            print(f"[DRIFT_LAB] LifeEngine singleton reset")
        except Exception as e:
            print(f"[DRIFT_LAB] Warning: LifeEngine reset error: {e}")

    # ─── Сбор статистики ─────────────────────────────────────────────

    def _collect_drift_snapshot(self, tick: int, start_time: float) -> DriftSnapshot:
        """Читает _drift_stats из TickOrchestrator."""
        stats = self._orchestrator._drift_stats
        return DriftSnapshot(
            tick=tick,
            total_comparisons=stats.get("total_comparisons", 0),
            drift_A=stats.get("drift_A", 0),
            drift_B=stats.get("drift_B", 0),
            drift_C=stats.get("drift_C", 0),
            drift_D=stats.get("drift_D", 0),
            drift_E=stats.get("drift_E", 0),
            elapsed_seconds=time.time() - start_time,
        )

    def _run_idle_ticks(self, count: int, result: DriftResult) -> None:
        """Запускает idle тики через реальный GameLoop.idle_tick().
        
        Не использует get_game_loop() — он требует FastAPI Request,
        которого нет в контексте DriftLab. Прямой вызов через
        self._game_loop — тот же production путь.
        """
        start = time.time()
        last_snapshot = 0

        for tick in range(1, count + 1):
            self._run_idle_tick_direct()

            # Периодический срез
            if tick - last_snapshot >= self.config.snapshot_interval:
                snap = self._collect_drift_snapshot(tick, start)
                result.snapshots.append(snap)
                last_snapshot = tick
                self._print_progress(tick, count, snap)

        # Финальный срез
        if not result.snapshots or result.snapshots[-1].tick != count:
            snap = self._collect_drift_snapshot(count, start)
            result.snapshots.append(snap)

        result.final_stats = dict(self._orchestrator._drift_stats)

    def _run_idle_tick_direct(self) -> None:
        """Запускает РЕАЛЬНЫЙ idle tick через GameLoop.idle_tick().

        Это тот же путь, что и production runtime:
        ensure_scene_initialized → tick++ → SpatialService.build →
        TickOrchestrator.execute(dm_ctx=None) → 10 фаз →
        _apply_with_shadow_observation → drift_stats накопление.

        Инвариант: тот же код, что и production runtime. Не копия.
        """
        try:
            result = self._game_loop.idle_tick(self.config.campaign_id)
            # result — dict с world_snapshot, npc_positions, etc.   
        except Exception as e:
            # Логируем но не крашим — лаборатория должна работать дальше
            print(f"  [DRIFT_LAB] idle_tick error: {type(e).__name__}: {e}")

    # ─── Режимы экспериментов ───────────────────────────────────────

    def _mode_mass_traversal(self, result: DriftResult) -> None:
        """
        Mode A: Mass Traversal
        30 NPC × 10000 тиков = ~300k comparisons.
        Проверяет: topology, boundary, traversal drift.
        """
        print(f"\n--- MODE A: Mass Traversal ({self.config.mass_traversal_ticks} ticks) ---")
        self._run_idle_ticks(self.config.mass_traversal_ticks, result)

    def _mode_save_load_storm(self, result: DriftResult) -> None:
        """
        Mode B: Save/Load Storm
        Каждые N тиков: save → load → verify.
        Проверяет: rehydration, persistence, graph consistency.
        
        S84→S85: Полный pipeline round-trip — scene_state + NPC dicts.
        До фикса тестировался только scene_state, NPC dicts (body_state,
        affective_load, emotion) никогда не попадали в round-trip.
        Это означало: SOMATIC_VETO body_state missing — необнаруживаем.
        """
        print(f"\n--- MODE B: Save/Load Storm ({self.config.save_load_storm_ticks} ticks, interval={self.config.save_load_interval}) ---")

        start = time.time()
        last_snapshot = 0
        _sl_stats = {"saves": 0, "loads": 0, "npc_drifts": 0, "npc_lost": 0, "body_state_drifts": 0}

        for tick in range(1, self.config.save_load_storm_ticks + 1):
            self._run_idle_tick_direct()

            # Save/Load цикл — полный pipeline (scene_state + NPC dicts)
            if tick % self.config.save_load_interval == 0:
                try:
                    # Актуализируем scene_state перед сохранением
                    if not self._scene_state:
                        self._scene_state = self._scene_manager.get_scene_state(
                            self.config.campaign_id,
                            self.config.location_id,
                        ) or {}

                    # SNAPSHOT: NPC dicts до сохранения (глубокая копия для верификации)
                    import copy
                    _engine = self._game_loop._get_life_engine()
                    _npc_before = []
                    if _engine:
                        _raw = _engine.get_npc_states(self.config.campaign_id)
                        _npc_before = copy.deepcopy(_raw)

                    # COMMIT: полный persistence path (как Phase 10 в production)
                    # До фикса: save_scene_state() — только scene_state, NPC dicts не сохранялись
                    self._scene_manager.commit(
                        campaign_id=self.config.campaign_id,
                        scene_state=self._scene_state,
                        npc_dicts=_npc_before if _npc_before else None,
                    )
                    _sl_stats["saves"] += 1

                    # LOAD: полный round-trip — scene_state + NPC dicts
                    _loaded_scene = self._scene_manager.get_scene_state(
                        self.config.campaign_id,
                        self.config.location_id,
                    )
                    _persistence = getattr(self._scene_manager, '_persistence', None)
                    _loaded_npcs = None
                    if _persistence:
                        _loaded_npcs = _persistence.load_npc_runtime(self.config.campaign_id)
                    _sl_stats["loads"] += 1

                    if _loaded_scene:
                        self._scene_state = _loaded_scene

                    # Обновляем LifeEngine cache загруженными данными
                    # Без этого следующий тик использует stale cache, не загруженные данные
                    if _loaded_npcs and _engine:
                        _engine.update_cache(self.config.campaign_id, _loaded_npcs)

                    # VERIFY: сравниваем NPC dicts до и после round-trip
                    if _npc_before and _loaded_npcs is not None:
                        _drifts, _lost, _bs_drifts = self._verify_npc_roundtrip(
                            _npc_before, _loaded_npcs, tick
                        )
                        _sl_stats["npc_drifts"] += _drifts
                        _sl_stats["npc_lost"] += _lost
                        _sl_stats["body_state_drifts"] += _bs_drifts
                    elif _npc_before and _loaded_npcs is None:
                        print(f"  [SAVE_LOAD][WARNING] load_npc_runtime=None at tick {tick} — NPC data NOT persisted")

                except Exception as e:
                    print(f"  [SAVE_LOAD] Error at tick {tick}: {e}")

            # Периодический срез
            if tick - last_snapshot >= self.config.snapshot_interval:
                snap = self._collect_drift_snapshot(tick, start)
                result.snapshots.append(snap)
                last_snapshot = tick
                self._print_progress(tick, self.config.save_load_storm_ticks, snap)

        # Финальный срез + save/load статистика
        snap = self._collect_drift_snapshot(self.config.save_load_storm_ticks, start)
        result.snapshots.append(snap)
        result.final_stats = dict(self._orchestrator._drift_stats)
        result.final_stats["save_load"] = _sl_stats
        print(f"\n--- SAVE/LOAD SUMMARY ---")
        print(f"  saves={_sl_stats['saves']} loads={_sl_stats['loads']}")
        print(f"  npc_drifts={_sl_stats['npc_drifts']} npc_lost={_sl_stats['npc_lost']}")
        print(f"  body_state_drifts={_sl_stats['body_state_drifts']}")

    def _verify_npc_roundtrip(self, before: list[dict], after: list[dict], tick: int) -> tuple[int, int, int]:
        """Верификация NPC dicts после save→load round-trip.

        Сравнивает критические поля: body_state, affective_load, emotion,
        perceptual_kernel. Возвращает (drifts, lost, body_state_drifts).

        Зачем: до S85 save_load_storm не проверял NPC dicts вообще.
        SOMATIC_VETO body_state missing был необнаружим.
        """
        _critical_fields = ["body_state", "affective_load", "emotion", "emotion_delta", "perceptual_kernel"]

        _before_by_id = {n.get("npc_id", n.get("id", "?")): n for n in before}
        _after_by_id = {n.get("npc_id", n.get("id", "?")): n for n in after}

        _drifts = 0
        _lost = 0
        _bs_drifts = 0

        for npc_id in _before_by_id:
            if npc_id not in _after_by_id:
                _lost += 1
                print(f"  [VERIFY][FATAL] NPC '{npc_id}' LOST after save/load at tick {tick}")
                continue

            _b = _before_by_id[npc_id]
            _a = _after_by_id[npc_id]

            for field in _critical_fields:
                _bv = _b.get(field)
                _av = _a.get(field)
                if _bv != _av:
                    _drifts += 1
                    if field == "body_state":
                        _bs_drifts += 1
                        # Диагностика: откуда body_state после загрузки
                        _src_after = "EMPTY"
                        if _av and _av.get("disabled"):
                            _src_after = "DISABLED"
                        elif _av and _av.get("life_status") == "ALIVE":
                            _src_after = "HEALTHY"
                        elif _av:
                            _src_after = f"CUSTOM(keys={list(_av.keys())[:5]})"
                        # Откуда был ДО сохранения
                        _src_before = "EMPTY"
                        if _bv and _bv.get("disabled"):
                            _src_before = "DISABLED"
                        elif _bv and _bv.get("life_status") == "ALIVE":
                            _src_before = "HEALTHY"
                        elif _bv:
                            _src_before = f"CUSTOM(keys={list(_bv.keys())[:5]})"
                        print(
                            f"  [VERIFY][BODY_STATE] NPC '{npc_id}' tick={tick}: "
                            f"before={_src_before} → after={_src_after}"
                        )
                    else:
                        print(
                            f"  [VERIFY][DRIFT] NPC '{npc_id}' field='{field}' tick={tick}: "
                            f"before={repr(_bv)[:60]} → after={repr(_av)[:60]}"
                        )

        # Первый save/load цикл — полная диагностика body_state для каждого NPC
        if tick <= self.config.save_load_interval:
            print(f"  [BODY_STATE_SOURCE] === First cycle diagnostic (tick={tick}) ===")
            for npc_id, npc in _after_by_id.items():
                _bs = npc.get("body_state")
                _src = "EMPTY"
                if _bs and _bs.get("disabled"):
                    _src = "DISABLED (sentinel — NPIC active)"
                elif _bs and _bs.get("life_status") == "ALIVE":
                    _src = "HEALTHY"
                elif _bs:
                    _src = f"keys={sorted(_bs.keys())}"
                print(f"  [BODY_STATE_SOURCE] NPC '{npc_id}': {_src}")

        return _drifts, _lost, _bs_drifts

    def _mode_chunk_migration(self, result: DriftResult) -> None:
        """
        Mode C: Chunk Migration
        NPC постоянно пересекают границы чанков.
        Проверяет: boundary drift.
        """
        print(f"\n--- MODE C: Chunk Migration ({self.config.chunk_migration_ticks} ticks) ---")
        self._run_idle_ticks(self.config.chunk_migration_ticks, result)

    def _mode_long_horizon(self, result: DriftResult) -> None:
        """
        Mode D: Long Horizon
        100k тиков idle.
        Проверяет: накопление ошибок, memory leaks, drift accumulation.
        """
        print(f"\n--- MODE D: Long Horizon ({self.config.long_horizon_ticks} ticks) ---")
        self._run_idle_ticks(self.config.long_horizon_ticks, result)

    # ─── Mode E: Replay Determinism ────────────────────────────────

    @staticmethod
    def _canonical_hash(scene_state: dict, npc_dicts: list) -> str:
        """Вычисляет детерминированный SHA256 хеш состояния мира.

        Исключает temporal и diagnostic поля, не влияющие на физику мира.
        sort_keys=True гарантирует порядок независимо от dict insertion order.
        """
        import hashlib
        import copy as _copy

        cleaned = _copy.deepcopy(scene_state)
        for key in _EXCLUDE_FROM_SCENE_HASH:
            cleaned.pop(key, None)

        # NPC dicts — сортируем по npc_id для детерминированного порядка
        sorted_npcs = sorted(
            npc_dicts,
            key=lambda n: n.get("npc_id", n.get("id", ""))
        )

        combined = {"scene": cleaned, "npcs": sorted_npcs}
        canonical_json = json.dumps(
            combined, sort_keys=True, ensure_ascii=False, default=str
        )
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    def _diagnose_mismatch(
        self, scene_a: dict, npcs_a: list, scene_b: dict, npcs_b: list
    ) -> None:
        """Локализует первое расхождение между двумя прогонами."""
        print(f"\n  [REPLAY] Диагностика расхождения:")

        # Сравниваем NPC dicts
        npcs_a_map = {n.get("npc_id", n.get("id", "")): n for n in npcs_a}
        npcs_b_map = {n.get("npc_id", n.get("id", "")): n for n in npcs_b}

        for npc_id in sorted(set(list(npcs_a_map.keys()) + list(npcs_b_map.keys()))):
            a = npcs_a_map.get(npc_id)
            b = npcs_b_map.get(npc_id)
            if a is None:
                print(f"     NPC '{npc_id}': MISSING in Run A")
                continue
            if b is None:
                print(f"     NPC '{npc_id}': MISSING in Run B")
                continue
            all_keys = sorted(set(list(a.keys()) + list(b.keys())))
            for key in all_keys:
                va = a.get(key)
                vb = b.get(key)
                if va != vb:
                    va_s = str(va)[:100]
                    vb_s = str(vb)[:100]
                    print(f"     NPC '{npc_id}' [{key}]: A={va_s}")
                    print(f"                         B={vb_s}")

        # Сравниваем scene_state ключи верхнего уровня
        for key in sorted(set(list(scene_a.keys()) + list(scene_b.keys()))):
            if key in _EXCLUDE_FROM_SCENE_HASH:
                continue
            va = scene_a.get(key)
            vb = scene_b.get(key)
            if va != vb:
                va_s = str(va)[:100]
                vb_s = str(vb)[:100]
                print(f"     scene['{key}']: A={va_s}")
                print(f"                     B={vb_s}")

    def _mode_replay_determinism(self, result: DriftResult) -> None:
        """Mode E: Replay Determinism Audit

        Два полных прогона с одинаковым random.seed().
        Цель: доказать или опровергнуть, что мир воспроизводим
        при контролируемой энтропии.

        Если MATCH → Baseline Determinism Verified (артефакт перед ФАЗОЙ 3).
        Если MISMATCH → скрытый источник энтропии (time, uuid, dict ordering).

        Протокол:
        1. random.seed(REPLAY_SEED) → Run A (N ticks) → hash → teardown
        2. random.seed(REPLAY_SEED) → setup → Run B (N ticks) → hash
        3. MATCH или MISMATCH с диагностикой
        """
        import random
        ticks = self.config.replay_determinism_ticks

        print(f"\n--- MODE E: Replay Determinism Audit (2 × {ticks} ticks) ---")
        print(f"  [REPLAY] Seed: {_REPLAY_SEED}")
        print(f"  [REPLAY] Исключены из хеша: {sorted(_EXCLUDE_FROM_SCENE_HASH)}")

        # ── RUN A ──────────────────────────────────────────────────
        print(f"\n  [REPLAY] === RUN A ===")
        random.seed(_REPLAY_SEED)

        for tick in range(1, ticks + 1):
            self._run_idle_tick_direct()
            if tick % 2_000 == 0:
                print(f"  [REPLAY] Run A: tick {tick}/{ticks}")

        # Захватываем canonical snapshot A
        scene_a = self._scene_manager.get_scene_state(
            self.config.campaign_id, self.config.location_id
        ) or {}
        _engine_a = self._game_loop._get_life_engine()
        npcs_a = _engine_a.get_npc_states(self.config.campaign_id) if _engine_a else []
        hash_a = self._canonical_hash(scene_a, npcs_a)
        drift_a = dict(self._orchestrator._drift_stats)
        print(f"  [REPLAY] Run A complete: hash={hash_a[:16]}... npcs={len(npcs_a)}")
        print(f"  [REPLAY] Run A drift: C={drift_a.get('drift_C',0)} D={drift_a.get('drift_D',0)} E={drift_a.get('drift_E',0)}")

        # ── TEARDOWN + RE-SETUP ────────────────────────────────────
        print(f"\n  [REPLAY] Teardown Run A...")
        self._teardown()

        print(f"  [REPLAY] Setup Run B...")
        self._setup()

        # ── RUN B ──────────────────────────────────────────────────
        print(f"\n  [REPLAY] === RUN B ===")
        random.seed(_REPLAY_SEED)

        for tick in range(1, ticks + 1):
            self._run_idle_tick_direct()
            if tick % 2_000 == 0:
                print(f"  [REPLAY] Run B: tick {tick}/{ticks}")

        # Захватываем canonical snapshot B
        scene_b = self._scene_manager.get_scene_state(
            self.config.campaign_id, self.config.location_id
        ) or {}
        _engine_b = self._game_loop._get_life_engine()
        npcs_b = _engine_b.get_npc_states(self.config.campaign_id) if _engine_b else []
        hash_b = self._canonical_hash(scene_b, npcs_b)
        drift_b = dict(self._orchestrator._drift_stats)
        print(f"  [REPLAY] Run B complete: hash={hash_b[:16]}... npcs={len(npcs_b)}")
        print(f"  [REPLAY] Run B drift: C={drift_b.get('drift_C',0)} D={drift_b.get('drift_D',0)} E={drift_b.get('drift_E',0)}")

        # ── VERDICT ────────────────────────────────────────────────
        result.final_stats = {
            "replay_seed": _REPLAY_SEED,
            "replay_ticks": ticks,
            "hash_a": hash_a,
            "hash_b": hash_b,
            "replay_verdict": "MATCH" if hash_a == hash_b else "MISMATCH",
        }

        if hash_a == hash_b:
            print(f"\n  ✅ REPLAY DETERMINISM: MATCH")
            print(f"     hash={hash_a}")
            print(f"     World is deterministic under controlled entropy (seed={_REPLAY_SEED})")
        else:
            print(f"\n  🔴 REPLAY DETERMINISM: MISMATCH")
            print(f"     Hash A: {hash_a}")
            print(f"     Hash B: {hash_b}")
            print(f"     Hidden entropy source detected — investigation required")
            self._diagnose_mismatch(scene_a, npcs_a, scene_b, npcs_b)

    # ─── Mode G: Projection Parity (CSSE Stage 2) ────────────────

    def _compare_spatial_fields(
        self, legacy: dict, projected: dict, thick_changes: list = None
    ) -> list:
        """Сравнивает ТОЛЬКО пространственные поля двух состояний.

        ProjectionEngine обрабатывает только spatial changes.
        Сравнение ограничено NPC, у которых были ThickSceneChange
        в текущем тике. Остальные NPC не в юрисдикции ProjectionEngine.

        Три категории ожидаемых расхождений:
        1. Jitter (A-drift): SHA256 vs random.uniform — допустимо
        2. from_node: EventCompiler vs legacy ghost recovery — ожидаемо
        3. Traversal interpolation: legacy interpolates, projection нет — ожидаемо
        """
        diffs = []

        # Определяем NPC, которые ProjectionEngine обрабатывал в этом тике
        affected_npcs = set()
        if thick_changes:
            for tc in thick_changes:
                if hasattr(tc, 'target') and tc.is_spatial:
                    affected_npcs.add(tc.target)

        # 1. npc_positions — только affected NPC, только spatial fields
        legacy_pos = legacy.get("npc_positions", {})
        projected_pos = projected.get("npc_positions", {})
        spatial_fields = {"position", "local_position", "location", "location_id"}

        _JITTER_EPSILON = 1.0  # SHA256 jitter vs random.uniform tolerance

        for npc_id in sorted(affected_npcs):
            lp = legacy_pos.get(npc_id, {})
            pp = projected_pos.get(npc_id, {})
            for field in spatial_fields:
                lv = lp.get(field)
                pv = pp.get(field)
                if lv != pv:
                    # Jitter tolerance: local_position with coordinate-level epsilon
                    if field == "local_position" and isinstance(lv, dict) and isinstance(pv, dict):
                        dx = abs(lv.get("x", 0) - pv.get("x", 0))
                        dy = abs(lv.get("y", 0) - pv.get("y", 0))
                        if dx <= _JITTER_EPSILON and dy <= _JITTER_EPSILON:
                            continue  # Expected A-drift (deterministic jitter)
                    diffs.append(("npc_positions", npc_id, field, lv, pv))

        # 2. active_traversals — только affected NPC
        legacy_trav = legacy.get("active_traversals", {})
        projected_trav = projected.get("active_traversals", {})

        for npc_id in sorted(affected_npcs):
            lt = legacy_trav.get(npc_id)
            pt = projected_trav.get(npc_id)
            if lt != pt:
                diffs.append(("active_traversals", npc_id, None, lt, pt))

        return diffs

    def _mode_projection_parity(self, result: DriftResult) -> None:
        """Mode G: Projection Parity Audit — CSSE Stage 2.

        Dual-reality synchronizer: shadow state = first class entity.
        Сравнивает legacy pipeline output vs ProjectionEngine output.

        Поток на тик:
        1. Сохраняем pre_tick state
        2. Запускаем legacy tick (apply_changes)
        3. Собираем ThickSceneChanges от EventCompiler
        4. Проецируем через ProjectionEngine → shadow state
        5. Сравниваем spatial fields: legacy vs shadow

        НЕ влияет на real state. ProjectionEngine пишет только в shadow buffer.
        """
        import copy
        from app.services.projection_engine import ProjectionEngine

        ticks = self.config.projection_parity_ticks
        projection = ProjectionEngine()

        print(f"\n--- MODE G: Projection Parity Audit ({ticks} ticks) ---")
        print(f"  [PARITY] Principle: shadow state = first class entity")
        print(f"  [PARITY] Comparing: legacy pipeline vs ProjectionEngine")
        print(f"  [PARITY] Fields: position, local_position, location, active_traversals")
        print(f"  [PARITY] Non-spatial fields EXCLUDED (not ProjectionEngine jurisdiction)")

        parity_stats = {
            "ticks": 0,
            "spatial_match": 0,
            "spatial_mismatch": 0,
            "total_field_diffs": 0,
            "mismatches": [],
        }
        max_mismatches_stored = 50

        for tick in range(1, ticks + 1):
            # 1. Сохраняем pre_tick state (до любых мутаций)
            pre_tick = copy.deepcopy(self._scene_state)

            # 2. Очищаем буфер ThickSceneChange
            self._orchestrator.collect_thick_changes()

            # 3. Запускаем legacy tick (AUTHORITATIVE)
            self._run_idle_tick_direct()

            # 4. Актуализируем scene_state (game_loop может создать новый dict)
            self._scene_state = self._scene_manager.get_scene_state(
                self.config.campaign_id,
                self.config.location_id,
            ) or {}

            # 5. Собираем ThickSceneChanges от EventCompiler
            thick_changes = self._orchestrator.collect_thick_changes()

            # 6. Проецируем через ProjectionEngine → shadow state
            shadow_state = projection.project(pre_tick, thick_changes)

            # 7. Сравниваем spatial fields (только affected NPC)
            legacy_state = self._scene_state
            diffs = self._compare_spatial_fields(legacy_state, shadow_state, thick_changes)

            parity_stats["ticks"] += 1
            if not diffs:
                parity_stats["spatial_match"] += 1
            else:
                parity_stats["spatial_mismatch"] += 1
                parity_stats["total_field_diffs"] += len(diffs)
                if len(parity_stats["mismatches"]) < max_mismatches_stored:
                    parity_stats["mismatches"].append({
                        "tick": tick,
                        "thick_count": len(thick_changes),
                        "diff_count": len(diffs),
                        "diffs": diffs[:10],
                    })

            if tick % 2_000 == 0:
                match_rate = parity_stats["spatial_match"] / parity_stats["ticks"] * 100
                print(
                    f"  [PARITY] tick {tick}/{ticks}: "
                    f"match={parity_stats['spatial_match']} "
                    f"mismatch={parity_stats['spatial_mismatch']} "
                    f"rate={match_rate:.1f}% "
                    f"thick_changes={len(thick_changes)}"
                )

        # Финальный вердикт
        total = parity_stats["ticks"]
        match = parity_stats["spatial_match"]
        mismatch = parity_stats["spatial_mismatch"]
        rate = match / total * 100 if total > 0 else 0

        result.final_stats = {
            "parity_ticks": total,
            "parity_match": match,
            "parity_mismatch": mismatch,
            "parity_rate": round(rate, 2),
            "parity_field_diffs": parity_stats["total_field_diffs"],
            "parity_verdict": "MATCH" if mismatch == 0 else "MISMATCH",
        }

        print(f"\n  [PARITY] Final Results:")
        print(f"     Ticks:           {total}")
        print(f"     Match:           {match} ({rate:.1f}%)")
        print(f"     Mismatch:        {mismatch}")
        print(f"     Total field diffs: {parity_stats['total_field_diffs']}")

        if mismatch == 0:
            print(f"\n  ✅ PROJECTION PARITY: MATCH")
            print(f"     ProjectionEngine produces identical spatial state to legacy")
            print(f"     CSSE Stage 2 verified — shadow reality = legacy reality")
            print(f"     ProjectionEngine can replace legacy as single writer")
        else:
            print(f"\n  🔴 PROJECTION PARITY: MISMATCH")
            print(f"     {mismatch} ticks with spatial field divergence")
            print(f"     {parity_stats['total_field_diffs']} total field differences")
            print(f"     First mismatches:")
            for m in parity_stats["mismatches"][:5]:
                print(f"       tick={m['tick']} thick_changes={m['thick_count']} diffs={m['diff_count']}")
                for d in m["diffs"][:3]:
                    category, npc_id, field, lv, pv = d
                    lv_s = str(lv)[:80]
                    pv_s = str(pv)[:80]
                    print(f"         [{category}] npc={npc_id} field={field}")
                    print(f"           legacy:   {lv_s}")
                    print(f"           projected: {pv_s}")

    # ─── Mode H: Idle Simulation Stability ─────────────────────────

    def _mode_idle_simulation_stability(self, result: DriftResult) -> None:
        """
        Mode H: Idle Simulation Stability
        Проверяет: живое поведение NPC, цикличность расписания, утечки active_traversals.
        Метрики: ACTIVITY_CHANGES, TRAVERSALS_CREATED, TRAVERSALS_FINISHED, UNIQUE_NODES_VISITED, ACTIVE_TRAVERSAL_LEAK, SCHEDULE_CYCLE_OK.
        """
        print(f"\n--- MODE H: Idle Simulation Stability ({self.config.idle_stability_ticks} ticks) ---")
        
        stats = {
            "ticks": 0,
            "activity_changes": 0,
            "traversals_created": 0,
            "traversals_finished": 0,
            "unique_nodes_visited": set(),
            "max_active_traversals": 0,
            "schedule_cycle_ok": False,
            "active_traversal_leak": False,
        }
        
        # История активностей для проверки цикличности
        npc_activity_history = {} # npc_id -> set of activities
        
        _engine = self._game_loop._get_life_engine()
        
        start = time.time()
        
        for tick in range(1, self.config.idle_stability_ticks + 1):
            # Снимок ДО тика
            _npcs_before = _engine.get_npc_states(self.config.campaign_id) if _engine else []
            _travs_before = set(self._scene_state.get("active_traversals", {}).keys())
            
            # Тик
            self._run_idle_tick_direct()
            
            # Актуализируем scene_state
            self._scene_state = self._scene_manager.get_scene_state(
                self.config.campaign_id, self.config.location_id
            ) or {}
            _npcs_after = _engine.get_npc_states(self.config.campaign_id) if _engine else []
            _travs_after = set(self._scene_state.get("active_traversals", {}).keys())
            
            # Метрики
            stats["ticks"] += 1
            
            # 1. Traversals
            created = _travs_after - _travs_before
            finished = _travs_before - _travs_after
            stats["traversals_created"] += len(created)
            stats["traversals_finished"] += len(finished)
            
            current_trav_count = len(_travs_after)
            if current_trav_count > stats["max_active_traversals"]:
                stats["max_active_traversals"] = current_trav_count
                
            # Утечка: если активных транзитов больше, чем NPC, и они не заканчиваются
            if current_trav_count > len(_npcs_after) + 5: # допустимая погрешность
                stats["active_traversal_leak"] = True
            
            # 2. Activities & Positions
            _npcs_after_map = {n.get("id"): n for n in _npcs_after}
            _pos_map_after = self._scene_state.get("npc_positions", {})
            for npc_id, npc in _npcs_after_map.items():
                activity = npc.get("routine", {}).get("current", "")
                pos = _pos_map_after.get(npc_id, {}).get("position", "")
                
                if pos:
                    stats["unique_nodes_visited"].add((npc_id, pos))
                    
                if npc_id in npc_activity_history:
                    if activity and activity in npc_activity_history[npc_id]:
                        stats["schedule_cycle_ok"] = True
                    npc_activity_history[npc_id].add(activity)
                else:
                    npc_activity_history[npc_id] = {activity}
                    
            # 3. Activity Changes (грубый подсчет по разнице)
            _npcs_before_map = {n.get("id"): n for n in _npcs_before}
            for npc_id, npc in _npcs_after_map.items():
                act_before = _npcs_before_map.get(npc_id, {}).get("routine", {}).get("current", "")
                act_after = npc.get("routine", {}).get("current", "")
                if act_before != act_after and act_after != "":
                    stats["activity_changes"] += 1
            
            # Периодический save/load для проверки персистенции
            if tick % 100 == 0:
                try:
                    self._scene_manager.commit(
                        campaign_id=self.config.campaign_id,
                        scene_state=self._scene_state,
                        npc_dicts=_npcs_after,
                    )
                    _persistence = getattr(self._scene_manager, '_persistence', None)
                    _loaded = _persistence.load_npc_runtime(self.config.campaign_id) if _persistence else None
                    if _loaded and _engine:
                        _engine.update_cache(self.config.campaign_id, _loaded)
                except Exception as e:
                    print(f"  [STABILITY] Save/Load error at tick {tick}: {e}")
                    
            if tick % 200 == 0:
                print(f"  [STABILITY] tick {tick}/{self.config.idle_stability_ticks}: travs={len(_travs_after)} changes={stats['activity_changes']} visited={len(stats['unique_nodes_visited'])}")
                
        result.final_stats = {
            "ACTIVITY_CHANGES": stats["activity_changes"],
            "TRAVERSALS_CREATED": stats["traversals_created"],
            "TRAVERSALS_FINISHED": stats["traversals_finished"],
            "UNIQUE_NODES_VISITED": len(stats["unique_nodes_visited"]),
            "MAX_ACTIVE_TRAVERSALS": stats["max_active_traversals"],
            "ACTIVE_TRAVERSAL_LEAK": "YES" if stats["active_traversal_leak"] else "NO",
            "SCHEDULE_CYCLE_OK": "YES" if stats["schedule_cycle_ok"] else "NO",
        }
        
        print(f"\n--- IDLE SIMULATION STABILITY SUMMARY ---")
        for k, v in result.final_stats.items():
            print(f"  {k}: {v}")
            
        if stats["activity_changes"] == 0:
            print(f"\n  ⚠️ WARNING: Activity changes = 0. Внутриигровое время (game_time) не продвигается в idle_tick.")

    # ─── Mode F: RNG Consumption Order Contract Audit ──────────────

    def _mode_rng_consumption_audit(self, result: DriftResult) -> None:
        """Mode F: RNG Consumption Order Contract Audit

        RCOC (RNG Consumption Order Contract) — верификация инварианта:
        порядок потребления энтропии детерминирован и воспроизводим.

        Аксиома: world = seed + ordered_random_consumption_trace

        Два прогона с одинаковым seed и инструментированным RNG.
        Сравнивает:
        - random.getstate() — авторитетное доказательство идентичности потребления
        - call counts — документация объёма потребления

        Если MATCH → RCOC invariant verified → порядок потребления = физический закон.
        Если MISMATCH → скрытая энтропия → investigation required before ФАЗА 3.
        """
        ticks = self.config.replay_determinism_ticks

        print(f"\n--- MODE F: RNG Consumption Order Contract Audit ---")
        print(f"  [RCOC] Seed: {_REPLAY_SEED}")
        print(f"  [RCOC] Ticks per run: {ticks}")
        print(f"  [RCOC] Verification: random.getstate() + call counting")
        print(f"  [RCOC] Axiom: world = seed + ordered_random_consumption_trace")

        # ── RUN A ────────────────────────────────────────────────────
        print(f"\n  [RCOC] === RUN A ===")
        _orig_inst_a = random._inst
        _counter_a = _RNGCounter(_REPLAY_SEED)
        random._inst = _counter_a

        for tick in range(1, ticks + 1):
            self._run_idle_tick_direct()
            if tick % 2_000 == 0:
                print(f"  [RCOC] Run A: tick {tick}/{ticks} rng_calls={_counter_a.total_calls}")

        state_a = random.getstate()
        calls_a = _counter_a.total_calls
        random_calls_a = _counter_a.random_calls
        bits_calls_a = _counter_a.getrandbits_calls
        random._inst = _orig_inst_a

        print(f"  [RCOC] Run A complete:")
        print(f"     random() calls:       {random_calls_a}")
        print(f"     getrandbits() calls:  {bits_calls_a}")
        print(f"     Total:                {calls_a}")
        print(f"     Per tick:             {calls_a / ticks:.1f}")

        # ── TEARDOWN + RE-SETUP ──────────────────────────────────────
        print(f"\n  [RCOC] Teardown Run A...")
        self._teardown()
        print(f"  [RCOC] Setup Run B...")
        self._setup()

        # ── RUN B ────────────────────────────────────────────────────
        print(f"\n  [RCOC] === RUN B ===")
        _orig_inst_b = random._inst
        _counter_b = _RNGCounter(_REPLAY_SEED)
        random._inst = _counter_b

        for tick in range(1, ticks + 1):
            self._run_idle_tick_direct()
            if tick % 2_000 == 0:
                print(f"  [RCOC] Run B: tick {tick}/{ticks} rng_calls={_counter_b.total_calls}")

        state_b = random.getstate()
        calls_b = _counter_b.total_calls
        random_calls_b = _counter_b.random_calls
        bits_calls_b = _counter_b.getrandbits_calls
        random._inst = _orig_inst_b

        print(f"  [RCOC] Run B complete:")
        print(f"     random() calls:       {random_calls_b}")
        print(f"     getrandbits() calls:  {bits_calls_b}")
        print(f"     Total:                {calls_b}")
        print(f"     Per tick:             {calls_b / ticks:.1f}")

        # ── VERDICT ──────────────────────────────────────────────────
        # getstate() = (version, tuple_of_internal_state, pos)
        # Если состояния совпадают → потреблена одинаковая последовательность энтропии
        # Это авторитетное доказательство RCOC инварианта
        state_match = state_a == state_b
        calls_match = calls_a == calls_b
        verdict = "MATCH" if (state_match and calls_match) else "MISMATCH"

        import hashlib
        def _state_hash(state):
            return hashlib.sha256(str(state).encode()).hexdigest()

        hash_a = _state_hash(state_a)
        hash_b = _state_hash(state_b)

        result.final_stats = {
            "rcoc_seed": _REPLAY_SEED,
            "rcoc_ticks": ticks,
            "rcoc_calls_a": calls_a,
            "rcoc_calls_b": calls_b,
            "rcoc_random_calls_a": random_calls_a,
            "rcoc_random_calls_b": random_calls_b,
            "rcoc_bits_calls_a": bits_calls_a,
            "rcoc_bits_calls_b": bits_calls_b,
            "rcoc_state_hash_a": hash_a,
            "rcoc_state_hash_b": hash_b,
            "rcoc_verdict": verdict,
        }

        if verdict == "MATCH":
            print(f"\n  ✅ RCOC INVARIANT: MATCH")
            print(f"     RNG state hash:  {hash_a[:32]}...")
            print(f"     Total consumption: {calls_a} calls ({calls_a / ticks:.1f}/tick)")
            print(f"     Entropy consumption order is deterministic and reproducible")
            print(f"     RCOC = verified physical law of the system")
            print(f"")
            print(f"     IMPLICATION: any change to RNG call order between")
            print(f"     LifeEngine / MovementEngine / SceneManager / etc.")
            print(f"     will break this invariant and must be detected.")
        else:
            print(f"\n  🔴 RCOC INVARIANT: MISMATCH")
            if not calls_match:
                print(f"     Call count: A={calls_a} B={calls_b} (diff={calls_b - calls_a})")
            if not state_match:
                print(f"     State hash A: {hash_a[:32]}...")
                print(f"     State hash B: {hash_b[:32]}...")
                print(f"     Hidden entropy source or order violation detected")
            print(f"     Investigation required before ФАЗА 3")

    # ─── Прогресс ───────────────────────────────────────────────────

    def _print_progress(self, tick: int, total: int, snap: DriftSnapshot) -> None:
        """Выводит прогресс эксперимента."""
        pct = tick / total * 100
        # Флаг структурного drift
        drift_flag = ""
        if snap.drift_C > 0:
            drift_flag = f" ⚠️ C={snap.drift_C}"
        if snap.drift_D > 0:
            drift_flag += f" 🔴 D={snap.drift_D}"
        if snap.drift_E > 0:
            drift_flag += f" 💀 E={snap.drift_E}"

        print(
            f"  tick={tick:>7} ({pct:5.1f}%) | "
            f"comparisons={snap.total_comparisons:>8} | "
            f"A={snap.drift_A} B={snap.drift_B}{drift_flag} | "
            f"{snap.elapsed_seconds:.1f}s"
        )


# ─── Репортер ──────────────────────────────────────────────────────────

class DriftReporter:
    """Генерирует CSV, графики и Markdown-отчёт из DriftResult.
    
    Весь вывод — на русском языке для интерпретации создателем системы.
    Файлы сохраняются в SUPERBOX/reports/.
    """

    # Русские названия классов drift для графиков и отчётов
    _CLASS_NAMES = {
        "A": "Косметический (A)",
        "B": "Проекционный (B)",
        "C": "Топологический (C)",
        "D": "Каузальный (D)",
        "E": "Онтологический (E)",
    }
    _CLASS_COLORS = {
        "A": "#2ecc71",   # зелёный — ожидаем, не критично
        "B": "#f39c12",   # оранжевый — внимание
        "C": "#e74c3c",   # красный — ошибка
        "D": "#8e44ad",   # фиолетовый — критично
        "E": "#2c3e50",   # чёрный — фатально
    }
    _CLASS_VERDICTS = {
        "A": "Ожидаемо (детерминированный jitter)",
        "B": "Допустимо (погрешность проекции)",
        "C": "ОШИБКА — разные узлы графа",
        "D": "КРИТИЧНО — разные причинные цепочки",
        "E": "ФАТАЛЬНО — NPC существует только в одном pipeline",
    }

    def __init__(self, result: DriftResult) -> None:
        self.result = result

    # ─── Консольный отчёт ───────────────────────────────────────────

    def print_summary(self) -> None:
        """Выводит итоговый отчёт в консоль — полностью на русском."""
        r = self.result
        print(f"\n{'='*70}")
        print(f"  ЛАБОРАТОРИЯ ДРЕЙФА — Результаты: {r.mode}")
        print(f"{'='*70}")

        # Основные показатели
        print(f"\n  Всего сравнений (comparisons): {r.total_comparisons:,}")
        print(f"  Целевой порог ФАЗЫ 3:          100 000")
        print(f"  Порог пройден:                  {'ДА ✅' if r.total_comparisons >= 100_000 else 'НЕТ ❌'}")

        # Структурный drift
        has_structural = r.has_structural_drift
        print(f"\n  Структурный дрейф (C/D/E):      {'ОБНАРУЖЕН ⚠️' if has_structural else 'НЕТ ✅'}")
        print(f"  Готовность к ФАЗЕ 3:            {'ДА ✅' if r.phase3_ready else 'НЕТ ❌'}")

        if not r.snapshots:
            return

        last = r.snapshots[-1]

        # Абсолютные числа
        print(f"\n  ┌─────────────────────────────────────────────────────┐")
        print(f"  │  Распределение дрейфа (абсолютные числа)            │")
        print(f"  ├─────────────────────────────────────────────────────┤")
        print(f"  │  A — Косметический:     {last.drift_A:>10,}                    │")
        print(f"  │  B — Проекционный:      {last.drift_B:>10,}                    │")
        print(f"  │  C — Топологический:    {last.drift_C:>10,}                    │")
        print(f"  │  D — Каузальный:        {last.drift_D:>10,}                    │")
        print(f"  │  E — Онтологический:    {last.drift_E:>10,}                    │")
        print(f"  └─────────────────────────────────────────────────────┘")

        # Проценты (drift rate)
        if last.total_comparisons > 0:
            print(f"\n  ┌─────────────────────────────────────────────────────┐")
            print(f"  │  Частота дрейфа (drift rate)                       │")
            print(f"  ├─────────────────────────────────────────────────────┤")
            for cls in ["A", "B", "C", "D", "E"]:
                count = getattr(last, f"drift_{cls}")
                rate = count / last.total_comparisons * 100
                name = self._CLASS_NAMES[cls].split("(")[0].strip()
                print(f"  │  {cls} — {name:<14}: {rate:>10.4f}%                   │")
            print(f"  └─────────────────────────────────────────────────────┘")

        # Вердикт по каждому классу
        print(f"\n  Интерпретация:")
        for cls in ["A", "B", "C", "D", "E"]:
            count = getattr(last, f"drift_{cls}")
            icon = "✅" if count == 0 else ("⚠️" if cls in ("A", "B") else "🔴")
            print(f"    {icon} Класс {cls}: {self._CLASS_VERDICTS[cls]}")
            if count > 0:
                name = self._CLASS_NAMES[cls]
                print(f"       → Обнаружено {count:,} случаев ({name})")

        # Время
        elapsed = last.elapsed_seconds
        if elapsed < 60:
            time_str = f"{elapsed:.1f} сек"
        elif elapsed < 3600:
            time_str = f"{elapsed/60:.1f} мин"
        else:
            time_str = f"{elapsed/3600:.2f} час"
        print(f"\n  Время эксперимента: {time_str}")

        # Скорость
        if elapsed > 0:
            cps = last.total_comparisons / elapsed
            tps = r.snapshots[-1].tick / elapsed if r.snapshots else 0
            print(f"  Скорость: {cps:,.0f} сравнений/сек, {tps:,.1f} тиков/сек")

    # ─── CSV ────────────────────────────────────────────────────────

    def save_csv(self, path: str = "drift_results.csv") -> None:
        """Сохраняет snapshots в CSV с русскими заголовками."""
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Тик",
                "Всего_сравнений",
                "Дрейф_A_Косметический",
                "Дрейф_B_Проекционный",
                "Дрейф_C_Топологический",
                "Дрейф_D_Каузальный",
                "Дрейф_E_Онтологический",
                "Секунд_прошло",
            ])
            for s in self.result.snapshots:
                writer.writerow([
                    s.tick,
                    s.total_comparisons,
                    s.drift_A,
                    s.drift_B,
                    s.drift_C,
                    s.drift_D,
                    s.drift_E,
                    f"{s.elapsed_seconds:.2f}",
                ])
        print(f"  📊 CSV сохранён: {path}")

    # ─── Markdown-отчёт ────────────────────────────────────────────

    def save_markdown(self, path: str = "drift_report.md") -> None:
        """Генерирует человекочитаемый Markdown-отчёт на русском."""
        r = self.result
        last = r.snapshots[-1] if r.snapshots else None
        if last is None:
            return

        lines = []
        lines.append(f"# Лаборатория Дрейфа — Отчёт")
        lines.append(f"")
        lines.append(f"**Режим:** {r.mode}")
        lines.append(f"**Дата:** {time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**Конфигурация:** campaign_id={r.config.campaign_id}, location_id={r.config.location_id}")
        lines.append(f"")

        # Сводка
        lines.append(f"## Сводка")
        lines.append(f"")
        lines.append(f"| Показатель | Значение |")
        lines.append(f"|---|---|")
        lines.append(f"| Всего сравнений | {r.total_comparisons:,} |")
        lines.append(f"| Порог ФАЗЫ 3 (100k) | {'ПРОЙДЕН ✅' if r.total_comparisons >= 100_000 else 'НЕ ПРОЙДЕН ❌'} |")
        lines.append(f"| Структурный дрейф (C/D/E) | {'ОБНАРУЖЕН ⚠️' if r.has_structural_drift else 'НЕТ ✅'} |")
        lines.append(f"| Готовность к ФАЗЕ 3 | {'ДА ✅' if r.phase3_ready else 'НЕТ ❌'} |")
        elapsed = last.elapsed_seconds
        if elapsed < 60:
            time_str = f"{elapsed:.1f} сек"
        elif elapsed < 3600:
            time_str = f"{elapsed/60:.1f} мин"
        else:
            time_str = f"{elapsed/3600:.2f} час"
        lines.append(f"| Время эксперимента | {time_str} |")
        lines.append(f"")

        # Распределение дрейфа
        lines.append(f"## Распределение дрейфа")
        lines.append(f"")
        lines.append(f"| Класс | Название | Кол-во | Частота | Вердикт |")
        lines.append(f"|---|---|---|---|---|")
        for cls in ["A", "B", "C", "D", "E"]:
            count = getattr(last, f"drift_{cls}")
            rate = f"{count/last.total_comparisons*100:.4f}%" if last.total_comparisons > 0 else "N/A"
            name = self._CLASS_NAMES[cls]
            verdict = self._CLASS_VERDICTS[cls]
            lines.append(f"| {cls} | {name} | {count:,} | {rate} | {verdict} |")
        lines.append(f"")

        # Динамика по срезам
        if len(r.snapshots) > 1:
            lines.append(f"## Динамика по срезам")
            lines.append(f"")
            lines.append(f"| Тик | Сравнений | A | B | C | D | E | Время (сек) |")
            lines.append(f"|---|---|---|---|---|---|---|---|")
            for s in r.snapshots:
                lines.append(
                    f"| {s.tick:,} | {s.total_comparisons:,} | {s.drift_A} | {s.drift_B} "
                    f"| {s.drift_C} | {s.drift_D} | {s.drift_E} | {s.elapsed_seconds:.1f} |"
                )
            lines.append(f"")

        # Интерпретация
        lines.append(f"## Интерпретация")
        lines.append(f"")
        lines.append(f"**Что измеряется:** Расхождение между двумя pipeline вычисления позиции NPC.")
        lines.append(f"- **Legacy pipeline** (apply_changes) — текущий авторитетный путь, содержит 6 мутаций")
        lines.append(f"- **Shadow pipeline** (EventCompiler) — целевой ФАЗЫ 3, чистая функция")
        lines.append(f"")
        lines.append(f"**Классы дрейфа:**")
        lines.append(f"- **A (Косметический):** Разница < 0.5 единиц координат. Ожидаема из-за детерминированного jitter")
        lines.append(f"- **B (Проекционный):** Тот же узел графа, но разные координаты. Допустимая погрешность")
        lines.append(f"- **C (Топологический):** Разные узлы графа. ОШИБКА — pipeline расходятся в навигации")
        lines.append(f"- **D (Каузальный):** Разные причинные цепочки (boundary, transition). КРИТИЧНО")
        lines.append(f"- **E (Онтологический):** NPC существует только в одном pipeline. ФАТАЛЬНО")
        lines.append(f"")

        if r.phase3_ready:
            lines.append(f"## ✅ ВЕРДИКТ: ФАЗА 3 ГОТОВА")
            lines.append(f"")
            lines.append(f"Накоплено {r.total_comparisons:,} сравнений без структурного дрейфа.")
            lines.append(f"Можно переключать apply_changes на потребление ThickSceneChange.")
        elif r.has_structural_drift:
            lines.append(f"## 🔴 ВЕРДИКТ: СТРУКТУРНЫЙ ДРЕЙФ ОБНАРУЖЕН")
            lines.append(f"")
            lines.append(f"Требуется расследование Class C/D/E drift перед переходом к ФАЗЕ 3.")
            for cls in ["C", "D", "E"]:
                count = getattr(last, f"drift_{cls}")
                if count > 0:
                    lines.append(f"- **Класс {cls}:** {count:,} случаев — {self._CLASS_VERDICTS[cls]}")
        else:
            lines.append(f"## ⏳ ВЕРДИКТ: НЕДОСТАТОЧНО ДАННЫХ")
            lines.append(f"")
            lines.append(f"Сравнений: {r.total_comparisons:,} / 100 000 необходимых.")
            lines.append(f"Структурный дрейф не обнаружен, но выборка мала для статистической значимости.")

        lines.append(f"")
        lines.append(f"---")
        lines.append(f"*Авто-сгенерировано Лабораторией Дрейфа ENIGMA*")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"  📝 Markdown-отчёт сохранён: {path}")

    # ─── Графики ────────────────────────────────────────────────────

    def plot_charts(self, path_prefix: str = "drift_chart") -> None:
        """Рисует 3 графика на русском через matplotlib."""
        try:
            import matplotlib
            matplotlib.use("Agg")  # без GUI
            import matplotlib.pyplot as plt
        except ImportError:
            print("  ⚠️ matplotlib не установлен — графики пропущены")
            print("     Установка: pip install matplotlib")
            return

        if not self.result.snapshots:
            print("  ⚠️ Нет данных для графиков")
            return

        ticks = [s.tick for s in self.result.snapshots]
        comparisons = [s.total_comparisons for s in self.result.snapshots]

        # ── График 1: Покрытие сравнений ──────────────────────────
        fig, ax = plt.subplots(figsize=(14, 6))
        ax.plot(ticks, comparisons, label="Всего сравнений", color="#3498db", linewidth=2.5)
        ax.axhline(y=100_000, color="#27ae60", linestyle="--", linewidth=1.5,
                    label="Порог ФАЗЫ 3 (100 000)")
        ax.fill_between(ticks, 0, comparisons, alpha=0.1, color="#3498db")
        ax.set_xlabel("Тик", fontsize=12)
        ax.set_ylabel("Количество сравнений", fontsize=12)
        ax.set_title(f"Покрытие сравнений — режим: {self.result.mode}", fontsize=14, fontweight="bold")
        ax.legend(fontsize=11)
        ax.grid(True, alpha=0.3)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{int(x):,}"))
        fig.tight_layout()
        fig.savefig(f"{path_prefix}_покрытие.png", dpi=150)
        plt.close(fig)

        # ── График 2: Классы дрейфа (абсолютные числа) ────────────
        fig, ax = plt.subplots(figsize=(14, 6))
        any_data = False
        for cls in ["A", "B", "C", "D", "E"]:
            values = [getattr(s, f"drift_{cls}") for s in self.result.snapshots]
            if any(v > 0 for v in values):
                any_data = True
                name = self._CLASS_NAMES[cls]
                ax.plot(ticks, values, label=name, color=self._CLASS_COLORS[cls], linewidth=2)
        if not any_data:
            # Нет дрейфа — показываем нулевую линию (ASCII — DejaVu Sans не содержит Unicode emoji)
            ax.axhline(y=0, color="#2ecc71", linewidth=2, label="Дрейф отсутствует")
        ax.set_xlabel("Тик", fontsize=12)
        ax.set_ylabel("Количество случаев", fontsize=12)
        ax.set_title(f"Классы дрейфа — режим: {self.result.mode}", fontsize=14, fontweight="bold")
        ax.legend(fontsize=10, loc="upper left")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(f"{path_prefix}_классы.png", dpi=150)
        plt.close(fig)

        # ── График 3: Частота дрейфа (проценты) ───────────────────
        fig, ax = plt.subplots(figsize=(14, 6))
        any_rate = False
        for cls in ["A", "B", "C", "D", "E"]:
            rates = []
            for s in self.result.snapshots:
                if s.total_comparisons > 0:
                    rates.append(getattr(s, f"drift_{cls}") / s.total_comparisons * 100)
                else:
                    rates.append(0.0)
            if any(v > 0 for v in rates):
                any_rate = True
                name = self._CLASS_NAMES[cls]
                ax.plot(ticks, rates, label=name, color=self._CLASS_COLORS[cls], linewidth=2)
        if not any_rate:
            ax.axhline(y=0, color="#2ecc71", linewidth=2, label="Дрейф отсутствует")
        ax.set_xlabel("Тик", fontsize=12)
        ax.set_ylabel("Частота дрейфа (%)", fontsize=12)
        ax.set_title(f"Частота дрейфа по классам — режим: {self.result.mode}", fontsize=14, fontweight="bold")
        ax.legend(fontsize=10, loc="upper left")
        ax.grid(True, alpha=0.3)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.3f}%"))
        fig.tight_layout()
        fig.savefig(f"{path_prefix}_частота.png", dpi=150)
        plt.close(fig)

        print(f"  📈 Графики сохранены: {path_prefix}_*.png (3 файла)")


# ─── Точка входа ──────────────────────────────────────────────────────

_MODE_NAMES = {
    "mass_traversal": "Массовые переходы (A)",
    "save_load_storm": "Шторм сохранений (B)",
    "chunk_migration": "Миграция чанков (C)",
    "long_horizon": "Длинный горизонт (D)",
    "replay_determinism": "Детерминизм воспроизведения (E)",
    "projection_parity": "Чёткость проекции (G)",
}


def main(mode: str = "long_horizon") -> None:
    mode_name = _MODE_NAMES.get(mode, mode)
    print(f"\n🧪 ЛАБОРАТОРИЯ ДРЕЙФА ENIGMA")
    print(f"   Режим: {mode_name}")
    print(f"   ADR-O-201 ФАЗА 2.5 — наблюдение за дрейфом в runtime")
    print()

    config = DriftConfig()
    lab = DriftLaboratory(config)
    result = lab.run(mode)

    reporter = DriftReporter(result)
    reporter.print_summary()

    # Директория для отчётов
    output_dir = Path(__file__).parent / "reports"
    output_dir.mkdir(exist_ok=True)

    # Сохраняем все форматы отчётов
    print(f"\n  Сохранение отчётов в: {output_dir}")
    reporter.save_csv(str(output_dir / f"дрейф_{mode}.csv"))
    reporter.save_markdown(str(output_dir / f"дрейф_{mode}.md"))
    reporter.plot_charts(str(output_dir / f"дрейф_{mode}"))

    # Вердикт
    _verd = (
        result.final_stats.get("replay_verdict")
        or result.final_stats.get("rcoc_verdict")
        or result.final_stats.get("parity_verdict")
    )
    if _verd:
        # Replay / RCOC / Parity — вердикт уже напечатан в режиме
        sys.exit(0 if _verd == "MATCH" else 1)
    if result.has_structural_drift:
        print(f"\n  🔴 СТРУКТУРНЫЙ ДРЕЙФ ОБНАРУЖЕН — требуется расследование")
        print(f"     Подробности в: {output_dir / f'дрейф_{mode}.md'}")
        sys.exit(1)
    elif result.phase3_ready:
        print(f"\n  ✅ ФАЗА 3 ГОТОВА — структурный дрейф не обнаружен за {result.total_comparisons:,} сравнений")
        print(f"     Отчёт: {output_dir / f'дрейф_{mode}.md'}")
        sys.exit(0)
    else:
        needed = 100_000 - result.total_comparisons
        print(f"\n  ⏳ Недостаточно данных — нужно ещё ~{needed:,} сравнений")
        print(f"     Текущий прогресс: {result.total_comparisons:,} / 100 000")
        sys.exit(0)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "long_horizon"
    main(mode)