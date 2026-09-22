"""
DEGOD ITER3: презентационные проекции scene_state (перенос из scene_state_manager.py).
Назначение: презентационные проекции scene_state для DM-промптов (описание сцены, контекст-блок NPC, блок событий). DEGOD ITER3: байт-в-байт перенос из scene_state_manager.py.
Зависимости: app.services.spatial.spatial_runtime, app.services.scene.salience_engine (лениво), app.services.scene_state.npc_display_name
Основные сущности: get_scene_description, build_npc_context_block, get_scene_events_block
"""

import logging

from app.services.scene_state.npc_display_name import _npc_id_to_display
from app.services.spatial.spatial_runtime import euclidean_distance

logger = logging.getLogger(__name__)


def get_scene_events_block(scene_state: dict) -> str:
    """R2.2.8: блок "уже произошло" для DM промпта. Canonical-aware."""
    events = scene_state.get("scene_events", [])
    if not events:
        return ""

    event_labels = {
        "drop": "упал/уронили",
        "break": "сломан/разбит",
        "take": "подобран/взят",
        "use": "используется",
        "light": "зажжён",
        "extinguish": "потушен",
    }

    lines = ["СОБЫТИЯ УЖЕ ПРОИЗОШЛИ В ЭТОЙ СЦЕНЕ (не повторять):"]
    seen: set[tuple] = set()

    for evt in events[-10:]:
        etype = evt.get("event_type", evt.get("type", ""))
        canonical = evt.get("canonical", evt.get("object_name", "").lower())
        actor = evt.get("actor", "")
        key = (etype, canonical)
        if key in seen:
            continue
        seen.add(key)

        label = event_labels.get(etype, etype)
        obj_name = evt.get("object_name", canonical)
        tick = evt.get("tick", "?")
        actor_str = f" ({actor.split('_')[-1]})" if actor else ""
        lines.append(f"- {obj_name} — {label}{actor_str} [ход {tick}]")

    return "\n".join(lines) if len(lines) > 1 else ""


def build_npc_context_block(
    scene_state: dict,
    npc_id: str,
    npc_name: str,
    spatial_service=None,
) -> str:
    """
    Строит пространственный блок для промпта конкретного NPC.

    NPC должен знать:
      - Где сейчас стоит игрок и на каком расстоянии
      - К нему ли обращается игрок или к кому-то другому
      - Если не к нему — NPC молчит

    Принцип: без этого блока модель галлюцинирует положение персонажей.
    Работает для любого NPC — имена и id из аргументов, не хардкод.
    """
    if not scene_state:
        return ""

    # ── Собственная позиция NPC ───────────────────────────────────────────
    npc_positions = scene_state.get("npc_positions", {})
    own_pos = npc_positions.get(npc_id, {})
    pos_text = own_pos.get("position", "")
    act_text = own_pos.get("activity", "")

    # SpatialService v1.2 динамически резолвит лейблы узлов
    pos_label = (
        spatial_service.get_node_label(pos_text) if spatial_service else pos_text
    )

    _activity_map = {
        "cleaning_tables": "убираешься",
        "serving_tables": "обслуживаешь зал",
        "observing": "наблюдаешь",
        "guarding_gate": "несёшь стражу",
        "sleeping": "спишь",
        "haggling": "торгуешься",
    }
    act_label = _activity_map.get(act_text, act_text)
    own_desc = ", ".join(p for p in [pos_label, act_label] if p)

    # ── Позиция и расстояние игрока (ADR-048: вычисление из npc_positions) ──
    player_pos = scene_state.get("player_position") or "рядом"
    _player_data = scene_state.get("npc_positions", {}).get("player", {})
    _npc_data = scene_state.get("npc_positions", {}).get(npc_id, {})
    distance_m = euclidean_distance(_player_data, _npc_data)
    dist_str = f"~{distance_m:.1f} м" if distance_m < 999.0 else "неизвестно"

    lines = [
        "ТВОЁ ПОЛОЖЕНИЕ В СЦЕНЕ:",
        f"- Ты: {own_desc or 'в локации'}",
        f"- Игрок: {player_pos}, расстояние до тебя: {dist_str}",
    ]

    # ── Кому обращается игрок ─────────────────────────────────────────────
    target_id = scene_state.get("player_target_npc")
    target_name = scene_state.get("player_target_npc_name")
    target_obj = scene_state.get("player_target_object")

    is_addressed = target_id == npc_id

    if is_addressed:
        lines.append(f"- ИГРОК ОБРАЩАЕТСЯ ИМЕННО К ТЕБЕ ({npc_name}) — отвечай.")
        if target_obj:
            lines.append(f"- Игрок взаимодействует с объектом: {target_obj}")
    elif target_id:
        # Игрок обращается к другому конкретному NPC
        lines.append(
            f"- Игрок обращается к {target_name or target_id}, НЕ к тебе. "
            f"Ты МОЛЧИШЬ — не говори ничего вслух."
        )
    else:
        # Нет явного адресата
        lines.append("- Игрок не обращается ни к кому конкретно.")

    # ── Предупреждение о физическом присутствии ───────────────────────────
    if distance_m is not None and distance_m < 1.5:
        lines.append(
            "ВАЖНО: Игрок физически рядом с тобой (< 1.5 м). "
            "Ты НЕ МОЖЕШЬ одновременно находиться в другом месте сцены."
        )

    return "\n".join(lines)


def get_scene_description(scene_state: dict) -> str:
    """
    Формирует текстовое описание SceneState для DM промпта.
    DM получает этот блок первым — он описывает ТОЛЬКО то что существует.
    """
    if not scene_state:
        return ""

    lines = ["Текущее состояние сцены (ТОЛЬКО ЭТИ объекты существуют в локации):"]

    # ── Объекты (Salience Engine: фильтрация по важности) ─────────────
    from app.models.scene_mode import determine_scene_mode
    from app.services.scene.salience_engine import SalienceEngine

    _raw_objects = scene_state.get("objects", {})
    _sal_event = scene_state.get("_salience_event_type", "player_interacts")
    _sal_stress = scene_state.get("_salience_max_stress", 0.0)
    _sal_target = scene_state.get("_salience_target_object")

    _filtered = SalienceEngine().get_filtered_objects(
        objects=_raw_objects,
        event_type=_sal_event,
        max_npc_stress=_sal_stress,
        player_target_object=_sal_target,
    )

    _scene_mode = determine_scene_mode(_sal_event, _sal_stress)
    state_map = {
        "intact": "цел",
        "damaged": "повреждён",
        "destroyed": "уничтожен",
        "lit": "горит",
        "unlit": "не горит",
        "burning": "горит",
        "open": "открыт",
        "locked": "заперт",
    }

    # Группируем только отфильтрованные объекты
    groups: dict = {}
    for obj_id, obj in _filtered:
        instance_of = obj.get("instance_of", obj_id)
        if instance_of not in groups:
            groups[instance_of] = {"obj": obj, "ids": [], "states": set()}
        groups[instance_of]["ids"].append(obj_id)
        groups[instance_of]["states"].add(obj.get("state", ""))

    for base_id, group in groups.items():
        obj = group["obj"]
        name = obj.get("name", base_id)
        count = len(group["ids"])
        states = group["states"]

        if len(states) == 1:
            state_str = state_map.get(states.pop(), "")
        else:
            state_str = ", ".join(state_map.get(s, s) for s in states)

        count_str = f" ×{count}" if count > 1 else ""
        lines.append(f"- {name}{count_str}: {state_str}".rstrip(": "))

    # Индикатор режима для отладки
    logger.debug(
        f"[SALIENCE_DEBUG] режим={_scene_mode.value}, объектов_до={len(_raw_objects)}, объектов_после={len(_filtered)}"
    )

    # ── Окружение ─────────────────────────────────────────────────────────
    env = scene_state.get("environment", {})
    if env:
        light_map = {
            "bright": "ярко освещено",
            "dim": "полутёмно",
            "dark": "темно",
            "torchlit": "освещено факелами",
            "natural": "естественный свет",
        }
        noise_map = {
            "silent": "тихо",
            "low": "негромкий шум",
            "moderate": "шумно",
            "loud": "очень шумно",
        }
        light = light_map.get(env.get("light_level", ""), "")
        noise = noise_map.get(env.get("noise_level", ""), "")
        weather = env.get("weather_inside", "")
        env_parts = [p for p in [light, noise, weather] if p]
        if env_parts:
            lines.append(f"Обстановка: {', '.join(env_parts)}")

    # ── Активные эффекты ──────────────────────────────────────────────────
    for effect in scene_state.get("active_effects", []):
        val = effect.get("value", {})
        if isinstance(val, dict) and val.get("type"):
            target = effect.get("target", "")
            lines.append(f"⚠ Эффект: {target} — {val['type']}")

    # ── NPC позиции ───────────────────────────────────────────────────────
    npc_positions = scene_state.get("npc_positions", {})
    if npc_positions:
        lines.append("")
        position_map = {
            "behind_bar": "за стойкой",
            "bar_area": "у стойки",
            "main_hall": "в центре зала",
            "fireplace": "у камина",
            # ADR-0010: corner_table удалена. Микро-зоны не существуют в макро-графе.
            "entrance": "у входа",
            "kitchen": "на кухне",
            "gate_post": "у ворот",
            "stall_3": "у третьего прилавка",
        }
        for npc_id, pos in npc_positions.items():
            if pos.get("state") == "dead":
                continue
            position = position_map.get(
                pos.get("position", ""), pos.get("position", "")
            )
            visible = pos.get("visible", True)
            npc_name = _npc_id_to_display(npc_id)
            hidden_tag = "" if visible else " [скрыт]"
            desc = f"{npc_name}: {position}"
            lines.append(desc + hidden_tag)

    lines.append("NPC которых нет в этом списке — в локации отсутствуют.")

    # ── S.0: пространственный контекст игрока (для DM) ────────────────────
    player_pos = scene_state.get("player_position")
    target_npc_name = scene_state.get("player_target_npc_name")
    target_npc_id = scene_state.get("player_target_npc")
    target_obj = scene_state.get("player_target_object")
    # ADR-048 Phase 3: Вычисляем дистанции из авторитетного словаря npc_positions
    _player_data = scene_state.get("npc_positions", {}).get("player", {})
    distances = {
        nid: euclidean_distance(_player_data, ndata)
        for nid, ndata in scene_state.get("npc_positions", {}).items()
        if nid != "player" and euclidean_distance(_player_data, ndata) < 999.0
    }

    lines.append("")
    lines.append("ПРОСТРАНСТВЕННЫЙ КОНТЕКСТ ИГРОКА:")
    if player_pos:
        lines.append(f"- Позиция игрока: {player_pos}")
    if target_npc_name:
        lines.append(f"- Игрок обращается к: {target_npc_name}")
    elif target_npc_id:
        lines.append(f"- Игрок обращается к: {_npc_id_to_display(target_npc_id)}")
    # else: не показываем ложь "не обращается" — может быть имя в тексте действия
    if target_obj:
        lines.append(f"- Игрок взаимодействует с объектом: {target_obj}")
    if distances:
        # Интерпретация расстояния в слово (инвариант: LLM не видит координаты)
        def _dist_to_word(d: float) -> str:
            if d < 1.0:
                return "вплотную"
            if d < 3.0:
                return "рядом"
            if d < 6.0:
                return "близко"
            return "в нескольких шагах" if d < 10.0 else "далеко"

        dist_parts = [
            f"{_npc_id_to_display(nid)}: {_dist_to_word(dist)}"
            for nid, dist in distances.items()
        ]
        lines.append(f"- Расстояния: {', '.join(dist_parts)}")

    lines.append("")
    lines.append("ПРАВИЛА РЕАКЦИЙ NPC (ОБЯЗАТЕЛЬНО):")
    if target_npc_name:
        lines.append(
            f"1. Игрок обратился к {target_npc_name} — "
            f"ТОЛЬКО {target_npc_name} отвечает. Остальные NPC молчат."
        )
    # else: не показываем ложное правило "не назвал" — имя может быть в тексте действия
    lines.append(
        "2. NPC не может одновременно быть рядом с игроком "
        "И делать что-то в другом месте сцены."
    )
    lines.append(
        "3. Все позиции из блока NPC выше — абсолютная правда. "
        "Не придумывай что NPC переместился если SceneState этого не зафиксировал."
    )

    return "\n".join(lines)
