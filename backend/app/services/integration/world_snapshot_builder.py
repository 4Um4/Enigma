from __future__ import annotations

# backend/app/services/integration/world_snapshot_builder.py
# Назначение: Собирает WorldSnapshotDTO из финального состояния тика.
# Чистый маппер: Dict[str, Any] → DTO. Не лезет в NPCState, DecisionHub, MemoryManager.
# Читает только scene_state dict и мета-данные тика.
# Зависимости: app.domain.snapshot, typing
import logging

logger = logging.getLogger(__name__)

from typing import Any, Dict, List, Optional, Tuple

from app.domain.presentation import EmbodiedStatusDTO
from app.domain.snapshot import (
    ActivePerception,
    AvatarStateDTO,
    ManifestationDTO,
    NPCPositionDTO,
    PeripheralCueDTO,
    PlayerPerceptionDTO,
    VisibleEventDTO,
    WorldSnapshotDTO,
)
from app.models.economy import EconomicProfile
from app.services.economy.need_presentation_mapper import NeedPresentationMapper
from app.services.integration.avatar_status_builder import AvatarStatusBuilder


class WorldSnapshotBuilder:
    """Маппер: scene_state dict → WorldSnapshotDTO.

    Не имеет побочных эффектов. Не вызывает логику.
    Только агрегирует то, что уже вычислено другими фазами.
    """

    def build(
        self,
        scene_state: Dict,
        tick: int,
        last_event_id: Optional[str] = None,
        avatar_state: Optional["AvatarStateDTO"] = None,  # ADR-035
        all_npcs_raw: Optional[List[Dict]] = None,  # ADR-037: Для вычисления среды
        player_perception: Optional[
            "PlayerPerceptionDTO"
        ] = None,  # ТЗ EMBODIED UI PERCEPTION
        recent_dialogues: Optional[List[Dict]] = None,  # ADR-O-313: Для Speech Bubbles
        player_body_topology: Optional[Dict] = None,  # ТЗ Presentation v2.0: Инвентарь
        visual_dto: Optional[Dict] = None,  # ТЗ Presentation v2.0: Канал визуальной презентации
        audible_dto: Optional[Dict] = None,  # ТЗ Presentation v2.0: Канал аудио презентации
        eco_profile: Optional[EconomicProfile] = None,  # S151: Профиль игрока для EmbodiedStatusDTO
    ) -> WorldSnapshotDTO:
        """Собирает снимок из финального состояния тика.

        Args:
            scene_state: Dict[str, Any] из SceneStateManager.get_scene_state()
            tick: номер текущего тика
            last_event_id: ID последнего обработанного события (опционально)
        """
        if not scene_state:
            return self._empty_snapshot(tick, recent_dialogues)

        npc_positions = self._extract_npc_positions(scene_state)

        # INV-DEF: Проверка инвариантов WorldSnapshot
        from app.errors import SimulationIntegrityError

        for npc_id, npc_data in npc_positions.items():
            if not (
                getattr(npc_data, "name", None)
                or getattr(npc_data, "display_name", None)
            ):
                raise SimulationIntegrityError(
                    invariant_id="INV-NPC-NAME",
                    message=f"NPC {npc_id} не имеет поля name. Fuzzy matching ослепнет.",
                    suspect_files=[
                        "backend/app/services/scene_state_manager.py",
                        "backend/app/services/npc/npc_loader.py",
                    ],
                    file=__file__,
                    line=44,
                )
        visible_events = self._extract_visible_events(scene_state)
        player_pos = self._extract_player_position(scene_state)
        self.avatar_state = avatar_state  # Проброс проекции в DTO
        location_id = scene_state.get("location_id", "")
        environment = scene_state.get("environment", {})
        version = tick

        # ADR-037: Вычисление средового давления на основе психики NPC в сцене
        ambient_phenomenology = self._compute_ambient_phenomenology(all_npcs_raw)

        result = WorldSnapshotDTO(
            tick=tick,
            version=version,
            last_event_id=last_event_id,
            player_position=player_pos,
            npc_positions=npc_positions,
            avatar_state=self.avatar_state,  # ADR-035: Внедрение феноменологической проекции
            ambient_phenomenology=ambient_phenomenology,  # ADR-037: Средовое давление
            recent_dialogues=recent_dialogues or [],  # ADR-O-313: Проброс кэша реплик
            player_perception=self._convert_perception(
                player_perception, tick=tick
            ),  # ТЗ EMBODIED UI: domain → API DTO конвертация
            player_body_topology=player_body_topology,  # ТЗ Presentation v2.0
            visual_dto=visual_dto,  # ТЗ Presentation v2.0
            embodied_status=self._build_embodied_status(eco_profile, player_body_topology),  # S151
            audible_dto=audible_dto,  # ТЗ Presentation v2.0
            visible_events=visible_events,
            available_actions=self._extract_available_actions(scene_state),
            location_id=location_id,
            weather=environment.get("weather_inside", "unknown"),
            time_of_day=environment.get("time_of_day", "day"),
            game_time_seconds=scene_state.get("game_time_seconds", 0),
            active_traversals=self._extract_active_traversals(scene_state),
        )

        # INV-DEF: Проверка инвариантов WorldSnapshot
        _at = result.active_traversals
        if not isinstance(_at, dict):
            from app.errors import SimulationIntegrityError

            raise SimulationIntegrityError(
                invariant_id="INV-TRAV-DICT",
                message=(
                    f"active_traversals имеет тип {type(_at).__name__}, ожидался dict. "
                    f"Frontend упадёт на isinstance(traversals, list) в game_screen.py."
                ),
                suspect_files=[
                    "backend/app/services/integration/world_snapshot_builder.py:_extract_active_traversals",
                    "backend/app/domain/snapshot.py:WorldSnapshotDTO.active_traversals",
                ],
                file=__file__,
                line=89,
            )

        return result

    # Маппинг cue_key → hover_text (наблюдение, не диагноз — Правило X: телепатия запрещена)
    _CUE_TEXT_MAP = {
        "FROZEN": "Замер на месте",
        "TENSE_POSTURE": "Напряжённая поза",
        "SWAYING": "Покачивается",
        "UNEVEN_STANCE": "Неустойчивая стойка",
        "ABRUPT_STOP": "Резко остановился",
        "FREQUENT_PAUSES": "Часто останавливается",
        "BLOOD_VISIBLE": "Кровь на одежде",
        "PAIN_REACTION": "Держится за рану",
    }

    _ATM_TEXT_MAP = {
        "ATMOSPHERE_THICK_TENSION": "Напряжение висит в воздухе",
        "ATMOSPHERE_UNEASY": "Обстановка тревожная",
    }

    def _convert_perception(
        self, domain_perception, tick: int = 0
    ) -> Optional[PlayerPerceptionDTO]:
        """Конвертация domain PlayerPerceptionDTO → API PlayerPerceptionDTO.

        Domain DTO (embodied_trace) кладёт cue-дикты в active_perceptions.
        API DTO (snapshot) разделяет на peripheral_cues (PeripheralCueDTO) и
        active_perceptions (ActivePerception с text/intensity).
        Без конвертации asdict() сериализует domain DTO, и фронтенд
        не находит ключ 'peripheral_cues'.
        """
        if domain_perception is None:
            return None

        # Если уже API DTO — пропускаем (isinstance не сработает при одинаковых именах,
        # проверяем по наличию поля peripheral_cues)
        if hasattr(domain_perception, "peripheral_cues"):
            return domain_perception

        peripheral_cues = []
        active_perceptions = []

        # Cue-дикты с npc_id → PeripheralCueDTO (Слой 1: периферия)
        for cue in getattr(domain_perception, "active_perceptions", []):
            if isinstance(cue, dict) and "npc_id" in cue:
                cue_key = cue.get("cue_key", "UNKNOWN")
                peripheral_cues.append(
                    PeripheralCueDTO(
                        npc_id=cue["npc_id"],
                        cue_key=cue_key,  # A3-FIX: renamed from cue_type
                        hover_text=self._CUE_TEXT_MAP.get(cue_key, cue_key),
                    )
                )

        # Атмосфера → ActivePerception (Слой 2: фоновая температура)
        atm_key = getattr(domain_perception, "atmosphere_key", None)
        atm_intensity = getattr(domain_perception, "atmosphere_intensity", 0.0)
        if atm_key:
            active_perceptions.append(
                ActivePerception(
                    text=self._ATM_TEXT_MAP.get(atm_key, atm_key),
                    intensity=atm_intensity,
                    decay_rate=-0.05,
                    created_tick=tick,
                )
            )

        # ADR-MANIFEST: Конвертируем domain manifestations → API ManifestationDTO
        _api_manifestations = []
        _domain_manifests = getattr(domain_perception, "manifestations", {})
        if _domain_manifests:
            for _nid, _tags in _domain_manifests.items():
                _api_manifestations.append(
                    ManifestationDTO(npc_id=_nid, tags=list(_tags))
                )

        return PlayerPerceptionDTO(
            active_perceptions=active_perceptions,
            peripheral_cues=peripheral_cues,
            manifestations=_api_manifestations,
            embodied_traces=getattr(domain_perception, "embodied_traces", []),
            observed_facts=getattr(domain_perception, "observed_facts", []),
        )

    def _extract_npc_positions(self, scene_state: Dict) -> Dict[str, NPCPositionDTO]:
        """Вытаскивает позиции NPC из scene_state['npc_positions'].
        БАГ I FIX: Фильтрует NPC по текущей локации — NPC в других локациях не отрисовываются.
        A2-FIX: Возвращает Dict[str, NPCPositionDTO] напрямую, не List."""
        result: Dict[str, NPCPositionDTO] = {}
        npc_positions = scene_state.get("npc_positions", {})
        current_location = scene_state.get("location_id", "")
        logger.info(
            f"[TRACE][SNAPSHOT_BUILD] npc_count={len(npc_positions)} keys={list(npc_positions.keys())[:5]} location={current_location}"
        )

        for npc_id, data in npc_positions.items():
            # ADR-048: player читается через _extract_player_position,
            # в npc_positions он не нужен — иначе фронтенд рисует его как NPC
            if npc_id == "player":
                continue
            if not data.get("visible", True):
                continue
            # БАГ I FIX: NPC в другой локации не отрисовываются в текущей
            # ADR-048: location_id — авторитетный источник. "location" — легаси-мусор от переходов.
            npc_loc = data.get("location_id") or data.get("location", "")
            if npc_loc and current_location and npc_loc != current_location:
                continue

            local = data.get("local_position", {})
            logger.info(
                f"[TRACE][SNAPSHOT] "
                f"npc={npc_id} "
                f"x={local.get('x') or 0.0} "
                f"y={local.get('y') or 0.0}"
            )
            # ADR-O-319: RecognitionMemory projection.
            # Читаем confidence из scene_state (персистится в SQLite).
            _recog_map = scene_state.get("player_recognition", {})
            _recog_data = _recog_map.get(npc_id, {})
            _confidence = float(_recog_data.get("confidence", 0.0))
            _real_name = data.get("name", npc_id)

            _display_name = "Незнакомец"
            print(f"[SNAPSHOT_RECOG] npc={npc_id} confidence={_confidence} recog_map_keys={list(_recog_map.keys())}")
            logger.debug(f"[SNAPSHOT_RECOG] npc={npc_id} confidence={_confidence} recog_map_keys={list(_recog_map.keys())}")
            if _confidence >= 0.9:
                _display_name = _real_name
            elif _confidence >= 0.6:
                _display_name = f"{_real_name} (?)"
            elif _confidence >= 0.2:
                _display_name = "Знакомое лицо"

            result[npc_id] = NPCPositionDTO(
                npc_id=npc_id,
                # S132.1: Передаем local_position с x, y, z
                local_position={"x": local.get("x", 0.0), "y": local.get("y", 0.0), "z": local.get("z", 0.0)},
                location_id=data.get("location_id", ""),
                facing=data.get("facing", "south"),
                body_heading=data.get("body_heading", 1.5708),
                activity=data.get("activity", "idle"),
                name=_real_name,
                display_name=_display_name,
                recognition_confidence=_confidence,
                initiative_suppression=data.get("initiative_suppression", 0.0),
                velocity=data.get("velocity", (0.0, 0.0)),
                exertion_level=data.get("exertion_level", 0.0),
            )

        return result

    def _extract_visible_events(self, scene_state: Dict) -> List[VisibleEventDTO]:
        """Вытаскивает видимые события.

        TODO: когда EventDTO будет интегрирован в scene_state,
        фильтровать по visibility и радиусу от игрока.
        """
        # Пока событий в scene_state нет — пустой список
        return []

    def _build_embodied_status(
        self,
        eco_profile: Optional[EconomicProfile],
        topology: Optional[Dict[str, Any]],
    ) -> Optional[EmbodiedStatusDTO]:
        """S151: Сборка DTO воплощённого статуса для UI."""
        if not eco_profile:
            return None
        _mapper = NeedPresentationMapper()
        _builder = AvatarStatusBuilder(_mapper)
        return _builder.build(eco_profile, topology)

    def _extract_player_position(self, scene_state: Dict) -> Tuple[float, float]:
        """Вытаскивает координаты игрока."""
        # ADR-048: Игрок читается из единого словаря npc_positions
        spatial = scene_state.get("npc_positions", {}).get("player", {})
        local = spatial.get("local_position", {})
        return (local.get("x", 0.0), local.get("y", 0.0))

    def _extract_active_traversals(self, scene_state: Dict) -> Dict[str, Any]:
        """Проецирует active_traversals из scene_state для фронтенда (ADR-019, CEI-2).
        SnapshotBuilder НЕ мутирует scene_state. Только чистая проекция.
        Возвращает Dict[npc_id, traversal_data] — синхронно с scene_state форматом.
        CEI-2 FIX: сохраняет ПОЛНЫЙ path_waypoints (без 2-point collapse)."""
        traversals = scene_state.get("active_traversals", {})
        result = {}

        for npc_id, trav in traversals.items():
            if (
                trav.get("status") == "MOVING"
                and len(trav.get("path_waypoints", [])) >= 2
            ):
                # CEI-2: Сохраняем ПОЛНЫЙ маршрут (intermediate nodes не теряются)
                wp = trav.get("path_waypoints", [])
                # Нормализация: гарантируем [[x,y], [x,y], ...]
                normalized_wp = []
                for pt in wp:
                    if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                        normalized_wp.append([float(pt[0]), float(pt[1])])
                    elif isinstance(pt, dict):
                        normalized_wp.append(
                            [float(pt.get("x", 0)), float(pt.get("y", 0))]
                        )

                if len(normalized_wp) >= 2:
                    result[npc_id] = {
                        "npc_id": npc_id,
                        "status": "MOVING",
                        "from_node": trav.get("from_node", ""),
                        "target_node": trav.get("target_node", ""),
                        "path_waypoints": normalized_wp,
                        "current_waypoint_idx": trav.get("current_waypoint_idx", 0),
                        "started_tick": trav.get("started_tick", 0),
                        "duration_ticks": trav.get("duration_ticks", 1),
                        "speed": trav.get("speed", 2.0),
                        "locomotion": trav.get("locomotion", "WALK"),
                    }
        return result

    def _compute_ambient_phenomenology(
        self, all_npcs_raw: Optional[List[Dict]]
    ) -> Optional[Dict[str, float]]:
        """Вычисляет феноменологическое давление среды на основе стресса и страха NPC (ADR-037)."""
        if not all_npcs_raw:
            return None

        total_stress, total_fear, count = 0.0, 0.0, 0
        for npc in all_npcs_raw:
            if npc.get("npc_id") == "player":
                continue
            psyche = npc.get("psyche", {})
            total_stress += float(psyche.get("stress", 0.0))
            total_fear += float(psyche.get("fear", 0.0))
            count += 1

        if count == 0:
            return None

        # Эмоциональная температура: от -1 (ледяное спокойствие) до 1 (паника/агрессия)
        avg_neg_emotion = (total_stress + total_fear) / (2 * count)
        emotional_temperature = (avg_neg_emotion * 2) - 1.0

        # Давление скопления: количество NPC нормализованное
        proximity_compression = min(1.0, count / 5.0)  # 5 NPC = максимальное давление

        return {
            "emotional_temperature": max(-1.0, min(1.0, emotional_temperature)),
            "proximity_compression": proximity_compression,
            "directional_pressure_bias": [
                0.0,
                0.0,
            ],  # Заглушка: вычисление вектора требует координат
        }

    def _extract_available_actions(self, scene_state: Dict) -> List[str]:
        """Доступные действия на основе контекста.

        TODO: вычислять из ближайших объектов, NPC, инвентаря.
        """
        return ["look", "move", "talk"]

    def _empty_snapshot(
        self, tick: int, recent_dialogues: Optional[List[Dict]] = None
    ) -> WorldSnapshotDTO:
        """Пустой снимок когда scene_state не загружен."""
        result = WorldSnapshotDTO(
            tick=tick,
            version=0,
            last_event_id=None,
            player_position=(0.0, 0.0),
            # A2-FIX: empty default changed from list to dict
            npc_positions={},
            visible_events=[],
            available_actions=["look", "move"],
            location_id="",
            weather="unknown",
            time_of_day="day",
            game_time_seconds=0,
            recent_dialogues=recent_dialogues or [],  # ADR-O-313: Проброс кэша реплик
        )
