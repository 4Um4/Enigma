"""
path: /project/backend/app/services/social/v2_relationship_backend.py
Назначение: V2RelationshipBackend — единственный runtime-носитель пяти
    скаляров отношений после cutover (ADR-O-371 / M1b.4; вердикт Мастера:
    «один субстрат — один хозяин»). Максимально тупой адаптер:
      - внешний интерфейс = legacy RelationshipStore (update/get_pair/
        get_all/get_all_for_source/reset_campaign) — все существующие
        инъекции и гейт работают без единой правки вызовов;
      - scene_state["relationship_state"]["directed"] — ЕДИНСТВЕННОЕ
        хранилище; собственных _cache НЕТ; файловых записей НЕТ; новых
        relationship-семантик НЕТ;
      - write: headroom-сатурация Δ×(100−|v|)/100 + clamp [-100,100]
        ДОСЛОВНО по legacy (не улучшать поведение при адаптации);
      - read: Vacuum (нет пары = {}) + round(4) — legacy-контракт;
      - persistence: НУЛЕВАЯ — subtree живёт в scene_state и уезжает
        на диск существующим atomic_commit_all (Фаза 10, Foundation Freeze).
    Порядок cutover (ратифицирован): load scene_state → migrate legacy →
    atomic persistence → mount V2 → runtime. Legacy JSON после успешной
    миграции — исторический входной формат, не второй runtime-store.
    campaign_id: адаптер привязан к кампании (как и легаси-инстанс);
    scene_state-доступ через provider-лямбду — сцена может пересоздаваться
    (новая локация), лямбда возвращает АКТУАЛЬНЫЙ dict.
Зависимости: typing (чистый сервис; scene_state передаётся провайдером).
Основные сущности: V2RelationshipBackend.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

logger = logging.getLogger(__name__)

# Ключи — те же КОНСТАНТЫ, что в relationship_state_store (§12.1); дублирование
# значений недопустимо — импортируем из канонического модуля
from app.services.social.relationship_state_store import (
    _KEY_DIRECTED,
    _KEY_ROOT,
    _LEGACY_SCALARS,
)


def _clamp(value: float, lo: float = -100.0, hi: float = 100.0) -> float:
    """Legacy-контракт дословно (relationship_store.py)."""
    return max(lo, min(hi, value))


class V2RelationshipBackend:
    """Тупой адаптер над scene_state.directed. Interface == legacy store.

    Не является SSOT сам по себе: истина — scene_state; адаптер — единственный
    легальный runtime-доступ к directed-поддереву для legacy-совместимого API.
    """

    def __init__(
        self,
        scene_state_provider: Callable[[], Dict[str, Any]],
        campaign_id: str,
    ) -> None:
        """scene_state_provider — лямбда, возвращающая АКТУАЛЬНЫЙ scene_state
        dict (сцена пересоздаётся при смене локации — держать старую ссылку
        нельзя, иначе адаптер станет читателем призрака)."""
        if not campaign_id:
            raise ValueError("V2RelationshipBackend: campaign_id обязателен")
        self._scene_state_provider = scene_state_provider
        self._campaign_id = campaign_id

    # ── внутренняя навигация по поддереву ──

    def _directed(self, create: bool = False) -> Dict[str, Dict[str, float]]:
        """Навигация к directed-поддереву. create=True (write-путь): лениво
        создаёт relationship_state.directed по цепочке (паттерн M1a
        apply_need_deltas — иначе update на пустом scene_state писал бы в
        выброшенный локальный dict, тест no_cache поймал ровно это).
        create=False (read): отсутствие = {} без мутации."""
        scene_state = self._scene_state_provider()
        if not isinstance(scene_state, dict):
            return {}
        if create:
            root = scene_state.setdefault(_KEY_ROOT, {})
            if not isinstance(root, dict):
                return {}
            return root.setdefault(_KEY_DIRECTED, {})
        root = scene_state.get(_KEY_ROOT)
        if not isinstance(root, dict):
            return {}
        directed = root.get(_KEY_DIRECTED)
        if not isinstance(directed, dict):
            return {}
        return directed

    def _campaign_guard(self, campaign_id: str) -> bool:
        """Легаси-семантика: один инстанс — одна кампания (адаптер построен
        на кампанию; чужой campaign_id = программная ошибка вызывающего)."""
        return campaign_id == self._campaign_id

    # ── WRITE: headroom + clamp ДОСЛОВНО по legacy ──

    def update(
        self,
        campaign_id: str,
        source: str,
        target: str,
        delta: Dict[str, float],
    ) -> None:
        """Legacy update() дословно: сатурация Δ×(100−|v|)/100, clamp,
        создание пары с prior=0 при отсутствии (Vacuum — про ЧТЕНИЕ;
        легаси-update молча создаёт запись — воспроизводим и это)."""
        if not self._campaign_guard(campaign_id):
            logger.warning(
                "[V2_REL] campaign mismatch: адаптер=%s, вызов=%s — игнор",
                self._campaign_id,
                campaign_id,
            )
            return
        if not source or not target or not delta:
            logger.debug(
                "[V2_REL] update no-op: пустой source/target/delta"
            )
            return
        directed = self._directed(create=True)
        # Путь к паре создаётся лениво — как в легаси (запись впервые)
        key = f"{source}→{target}"
        current = directed.get(key)
        if current is None:
            current = {}
            directed[key] = current
        for attr, change in delta.items():
            if attr not in _LEGACY_SCALARS:
                continue  # легаси-фильтр посторонних ключей — дословно
            try:
                _change = float(change)
            except (TypeError, ValueError) as e:
                # L4: невалидная дельта отфильтрована — наблюдаемо, не молча
                # (легаси-фильтр молчал; v2-контракт: тот же итог, видимый путь)
                logger.debug(f"[V2_REL] update: дельта '{attr}' не число — фильтр: {e}")
                continue
            current_val = float(current.get(attr, 0.0))
            headroom = (100.0 - abs(current_val)) / 100.0
            effective = _change * headroom
            current[attr] = _clamp(current_val + effective)
        # Персистенции здесь НЕТ: scene_state уедет в atomic_commit (Фаза 10)

    # ── READ: Vacuum + round(4) ДОСЛОВНО ──

    def get_pair(
        self,
        campaign_id: str,
        source: str,
        target: str,
    ) -> Dict[str, float]:
        if not self._campaign_guard(campaign_id) or not source or not target:
            return {}
        raw = self._directed().get(f"{source}→{target}")
        if raw is None:
            return {}  # Vacuum: нет записи = нет знания
        return {
            attr: round(float(val), 4)
            for attr, val in raw.items()
            if attr in _LEGACY_SCALARS
        }

    def get(self, campaign_id: str, source: str) -> Dict[str, Any]:
        """Все отношения от source → {target: {scalars}} (legacy get)."""
        if not self._campaign_guard(campaign_id) or not source:
            return {}
        prefix = f"{source}→"
        result: Dict[str, Any] = {}
        for key, raw in self._directed().items():
            if key.startswith(prefix):
                result[key.split("→")[1]] = dict(raw)
        return result

    def get_all(self, campaign_id: str) -> Dict[str, Any]:
        """Весь граф кампании (legacy get_all — для end_screen/memory API)."""
        if not self._campaign_guard(campaign_id):
            return {}
        return {k: dict(v) for k, v in self._directed().items()}

    def get_all_for_source(
        self,
        campaign_id: str,
        source: str,
    ) -> Dict[str, Dict[str, float]]:
        """{target: {trust, fear, debt, respect, attraction}} — нормализованная
        форма DecisionHub (legacy get_all_for_source дословно, включая
        материализацию 0.0 по ВСЕМ ключам для существующих пар)."""
        if not self._campaign_guard(campaign_id) or not source:
            return {}
        prefix = f"{source}→"
        return {
            key.split("→")[1]: {
                attr: float(raw.get(attr, 0.0)) for attr in _LEGACY_SCALARS
            }
            for key, raw in self._directed().items()
            if key.startswith(prefix)
        }

    def reset_campaign(self, campaign_id: str) -> int:
        """new_game: очистка directed-поддерева (замена legacy reset+удаления
        npc_relationships.json). Возвращает число сброшенных пар."""
        if not self._campaign_guard(campaign_id):
            return 0
        scene_state = self._scene_state_provider()
        if not isinstance(scene_state, dict):
            return 0
        root = scene_state.get(_KEY_ROOT)
        if not isinstance(root, dict):
            return 0
        directed = root.get(_KEY_DIRECTED)
        if not isinstance(directed, dict):
            return 0
        count = len(directed)
        root[_KEY_DIRECTED] = {}  # очистка in-place: scene_state — единственный носитель
        if count:
            logger.info(f"[V2_REL] reset_campaign: сброшено {count} пар ({campaign_id})")
        return count
