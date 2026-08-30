"""
path: /project/backend/app/services/social/v2_relationship_backend.py
Назначение: V2RelationshipBackend — единственный runtime-носитель пяти
    скаляров отношений после cutover (ADR-O-371 / M1b.4; вердикт Мастера:
    «один субстрат — один хозяин»; RAM-GO: «RAM — runtime authority,
    сцена — persistence projection»):
      - внешний интерфейс = legacy RelationshipStore (update/get_pair/
        get_all/get_all_for_source/reset_campaign) — все существующие
        инъекции и гейт работают без единой правки вызовов;
      - RAM-dict (self._directed_ram) — RUNTIME AUTHORITY: рабочий
        носитель, переживает пред-сценовое состояние (инварианты IPT,
        direct-API, boot — паритет-контракт легаси, IPT-инцидент
        friend==enemy=50); НЕ кэш (кэш = копия истины; RAM = сама истина);
      - scene_state["relationship_state"]["directed"] — PERSISTENCE
        PROJECTION: sync_into() на update + подъём (hydrate) при bind;
        disk-on-update ЗАПРЕЩЁН (Foundation Freeze: диск — только
        atomic_commit_all Фазы 10);
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
from typing import Any, Callable, Dict, Optional

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
    """RAM-authoritative бэкенд пяти скаляров. Interface == legacy store.

    Инварианты RAM-GO (вердикт Мастера): (1) один runtime owner — RAM;
    сцена — проекция; после bind читается ТОЛЬКО RAM (hydrate однократен);
    (2) никакого disk-on-update; (3) sync_into идемпотентен.
    """

    def __init__(
        self,
        scene_state_provider: Optional[Callable[[], Dict[str, Any]]] = None,
        campaign_id: Optional[str] = None,
    ) -> None:
        """RAM-GO: _directed_ram — runtime authority (см. класс-докстринг).
        scene_state_provider — vestigial (удержан до доказательства
        pre-scene-теста; после — кандидат на удаление M1b.5): сцена нужна
        только как sync-цель проекции, доступная после bind.
        late-bind: конструирование без кампании легально (GameLoop строится
        до известности campaign_id); первый осмысленный API-вызов
        привязывает (см. _ensure_lazy_bind)."""
        self._scene_state_provider = scene_state_provider
        self._campaign_id = campaign_id
        self._directed_ram: Dict[str, Dict[str, float]] = {}

    def bind(self, campaign_id: str, scene_state: Optional[Dict[str, Any]] = None) -> None:
        """Закрепление кампании (однократно; повторный bind той же кампании —
        идемпотент; чужой — громкий отказ, не тихая подмена).

        RAM-GO hydrate: при переданной сцене и ПУСТОМ RAM — подъём directed
        из сцены (загрузка сохранения: сцена → RAM, не параллельное чтение).
        Пред-сценовые записи RAM-носителя (IPT-контракт) НЕ затираются:
        hydrate только наполняет пустой, pre-scene values приоритетны
        (они были записаны раньше сцены)."""
        if self._campaign_id is None:
            self._campaign_id = campaign_id
            if isinstance(scene_state, dict):
                _rs = scene_state.get(_KEY_ROOT)
                _d = _rs.get(_KEY_DIRECTED) if isinstance(_rs, dict) else None
                if isinstance(_d, dict) and _d and not self._directed_ram:
                    self._directed_ram = {k: dict(v) for k, v in _d.items()}
                    logger.info(f"[V2_REL] bind: hydrate из сцены ({len(_d)} пар)")
            logger.info(f"[V2_REL] bind: campaign={campaign_id}")
        elif self._campaign_id != campaign_id:
            raise ValueError(
                f"V2RelationshipBackend уже привязан к '{self._campaign_id}', "
                f"запрошен bind('{campaign_id}') — смена кампании инстансом "
                f"запрещена (создавайте новый адаптер на кампанию)"
            )

    def _ensure_lazy_bind(self, campaign_id: str) -> None:
        """Lazy-привязка: непривязанный адаптер + осмысленный вызов → bind.
        RAM-GO: сцена НЕ требуется (RAM-носитель жив без сцены — именно
        это закрыло IPT-инцидент: update до первого тика обязан работать)."""
        if self._campaign_id is None and campaign_id:
            self.bind(campaign_id)

    # ── внутренняя навигация: RAM = runtime authority ──

    def _directed(self, create: bool = False) -> Dict[str, Dict[str, float]]:
        """RAM-носитель (runtime authority). create-параметр сохранён для
        сигнатурной совместимости; RAM существует всегда — ленивая
        инициализация сцены более не нужна (сцена — проекция, не истина)."""
        return self._directed_ram

    def _campaign_guard(self, campaign_id: str) -> bool:
        """Легаси-семантика: один инстанс — одна кампания. Непривязанный
        адаптер → lazy-bind (RAM не требует сцены)."""
        if self._campaign_id is None:
            self._ensure_lazy_bind(campaign_id)
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
        # RAM-GO: немедленная проекция в живую сцену (если есть) — сцена
        # актуальна для Фазы 10 без отдельного sync-вызова; идемпотентна
        # (полная замена ключа пары); disk-on-update ЗАПРЕЩЁН.
        self.sync_into_scene()

    def sync_into_scene(self) -> None:
        """RAM → сцена-проекция (если провайдер жив и сцена непуста).
        Идемпотентен: directed := копия RAM (полная замена, не merge).
        RAM-GO инвариант 3: sync∘sync == sync."""
        _scene = self._scene_state_provider() if self._scene_state_provider else None
        if not isinstance(_scene, dict) or not _scene:
            return
        _rs = _scene.setdefault(_KEY_ROOT, {})
        if isinstance(_rs, dict):
            _rs[_KEY_DIRECTED] = {k: dict(v) for k, v in self._directed_ram.items()}

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
        count = len(self._directed_ram)
        self._directed_ram = {}  # RAM-authority: сброс носителя
        self.sync_into_scene()   # проекция сброса в живую сцену
        if count:
            logger.info(f"[V2_REL] reset_campaign: сброшено {count} пар ({campaign_id})")
        return count
