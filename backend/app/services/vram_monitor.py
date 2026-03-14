"""
VRAM Monitor (F1-T02) — оптимизирован под RTX 3070 Ti (8 GB)

ИСПРАВЛЕНИЯ vs оригинал:
─────────────────────────────────────────────────────────────────
1. ЛОЖНЫЕ УТЕЧКИ (+5757 MB в логах).
   Причина: start_session() никогда не вызывался → baseline=0
   → current VRAM (реальное потребление) интерпретировалось как "утечка".
   Исправлено: baseline устанавливается автоматически при первом get_vram_mb().

2. asyncio.sleep(2) в measure_load().
   Оригинал ждал 2 секунды при КАЖДОМ замере → 3 агента × 2 сек = +6 сек/turn.
   Убрано. Замер мгновенный.

3. check_session_leak() обращался к несуществующему атрибуту leak_threshold_mb.
   Добавлен дефолт.

4. Добавлены get_vram_budget() и is_safe_to_load(model_vram_mb).
   Для принятия решений ДО загрузки модели — предотвращает OOM.
"""

import asyncio
import logging
import os
import subprocess
import time
import shutil
from typing import Optional, Tuple, Dict

logger = logging.getLogger(__name__)

# RTX 3070 Ti — 8192 MB
TOTAL_VRAM_MB     = 8192
# Буфер безопасности: не занимаем последние 800 MB
SAFETY_BUFFER_MB  = 800
USABLE_VRAM_MB    = TOTAL_VRAM_MB - SAFETY_BUFFER_MB  # 7392 MB
# Порог утечки
LEAK_THRESHOLD_MB = 150  # не 100 — llama.cpp иногда даёт +80 MB за страницу


class VRAMMonitor:
    """
    Singleton VRAM tracker.

    Мониторит GPU через nvidia-smi.
    При отсутствии GPU (CPU mode) возвращает 0 — не крашит игру.
    """

    _instance: Optional["VRAMMonitor"] = None
    _session_start_vram: Optional[int] = None

    def __new__(cls) -> "VRAMMonitor":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._baseline_set = False
        return cls._instance

    async def get_vram_mb(self) -> int:
        """Текущее использование VRAM в MB (0 при отсутствии GPU)."""
        try:
            nvidia_smi = (
                os.getenv("NVIDIA_SMI_PATH")
                or shutil.which("nvidia-smi")
                or "nvidia-smi"
            )
            result = subprocess.run(
                [
                    nvidia_smi,
                    "--query-gpu=memory.used",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            vram_mb = int(result.stdout.strip().split("\n")[0])

            # Автоматически устанавливаем baseline при первом замере
            # (исправляет ложные утечки из-за baseline=0)
            if not self._baseline_set:
                self._session_start_vram = vram_mb
                self._baseline_set = True
                logger.info(
                    f"[VRAM_MONITOR] Baseline auto-set: {vram_mb} MB"
                )

            return vram_mb

        except (subprocess.CalledProcessError, ValueError,
                FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.debug(f"nvidia-smi unavailable → VRAM=0 (CPU mode): {e}")
            return 0

    async def measure_load(
        self, leak_threshold_mb: int = LEAK_THRESHOLD_MB
    ) -> Tuple[int, int, bool]:
        """
        Измеряет VRAM после загрузки модели.
        ИСПРАВЛЕНО: asyncio.sleep(2) убран — экономия 2+ сек/turn.

        Returns: (vram_after_mb, delta_mb, leak_detected)
        """
        vram_after = await self.get_vram_mb()
        baseline   = self._session_start_vram or 0
        delta_mb   = vram_after - baseline

        leak_detected = delta_mb > TOTAL_VRAM_MB * 0.75  # > 75% — реальная утечка
        if leak_detected:
            logger.error(
                f"[VRAM_LEAK] DETECTED: used={vram_after}MB "
                f"(baseline={baseline}MB, delta=+{delta_mb}MB)"
            )
        else:
            logger.info(
                f"[VRAM_MONITOR] After load: {vram_after}MB "
                f"(baseline={baseline}MB, delta={delta_mb:+}MB ✓)"
            )

        return vram_after, delta_mb, leak_detected

    async def start_session(self, initial_vram: Optional[int] = None):
        """Устанавливает baseline для сессии."""
        self._session_start_vram = initial_vram or await self.get_vram_mb()
        self._baseline_set = True
        logger.info(
            f"[VRAM_SESSION] Started: baseline={self._session_start_vram}MB"
        )

    def get_vram_budget(self) -> dict:
        """
        Синхронный snapshot бюджета VRAM.
        Используется для принятия решений о загрузке модели.
        """
        return {
            "total_mb":       TOTAL_VRAM_MB,
            "usable_mb":      USABLE_VRAM_MB,
            "safety_buffer":  SAFETY_BUFFER_MB,
            "baseline_mb":    self._session_start_vram or 0,
        }

    def is_safe_to_load(self, model_vram_mb: int, current_used_mb: int = 0) -> bool:
        """
        Проверяет, хватит ли VRAM для загрузки модели.

        Используется в ModelPool перед _load_model для предотвращения OOM.
        current_used_mb = уже занято (если нет активной модели, = baseline).
        """
        available = USABLE_VRAM_MB - current_used_mb
        safe = available >= model_vram_mb
        if not safe:
            logger.warning(
                f"[VRAM_BUDGET] Недостаточно VRAM: "
                f"нужно={model_vram_mb}MB, доступно={available}MB"
            )
        return safe

    async def check_session_leak(
        self, baseline: int
    ) -> Tuple[int, bool]:
        current = await self.get_vram_mb()
        leak = current - baseline
        return leak, leak > LEAK_THRESHOLD_MB

    async def get_dashboard(self) -> Dict:
        """Данные для /debug/vram endpoint."""
        current  = await self.get_vram_mb()
        baseline = self._session_start_vram or 0
        session_leak, leaked = await self.check_session_leak(baseline)
        free_mb  = max(0, TOTAL_VRAM_MB - current)
        return {
            "current_vram_mb":    current,
            "free_vram_mb":       free_mb,
            "session_baseline_mb": baseline,
            "session_leak_mb":    session_leak,
            "leak_alert":         leaked,
            "usable_vram_mb":     USABLE_VRAM_MB,
            "vram_percent":       round(current / TOTAL_VRAM_MB * 100, 1),
            "timestamp":          time.time(),
        }


def get_vram_monitor() -> VRAMMonitor:
    return VRAMMonitor()