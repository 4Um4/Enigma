# C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\agents\dm_agent.py
# -*- coding: utf-8 -*-
"""
DM Agent - Dungeon Master Narrative Layer

Uses capability-based routing to automatically select the best model.
Includes Phase 1 error handling + VRAM logging.
"""

from typing import Optional, List, Dict, Generator
from pathlib import Path
from app.models.schemas import PlayerAction
from app.services.llm import ModelRouter, get_router
from app.services.llm.provider import GenerationParams
from app.services.error_interpreter import get_error_interpreter
from app.services.vram_monitor import get_vram_monitor
from app.core.config import settings
import json


# ──────────────────────────────────────────────────────────────────────────────
# Стоп-токены ChatML (Qwen2.5): при появлении в стриме — немедленно останавливаем.
# <|im_start|> — самый опасный: вызывает генерацию текста промпта целиком.
# ──────────────────────────────────────────────────────────────────────────────
_STOP_TOKENS = [
    "<|file_separator|>",
    "<|end_of_turn|>",
    "<end_of_turn>",
    "<|im_end|>",
    "</|im_end|>",
    "<|im_start|>",      # главный виновник утечки промпта
    "</|im_start|>",
    "</s>",
    "<|endoftext|>",
    "<|file_end|>",
    "<|file_sep|>",
]


def _strip_stop_tokens(text: str) -> str:
    """Убирает стоп-токены из строки. Обрезает по первому вхождению."""
    for token in _STOP_TOKENS:
        idx = text.find(token)
        if idx != -1:
            text = text[:idx]
    return text.strip()


def _has_stop_token(text: str) -> bool:
    return any(st in text for st in _STOP_TOKENS)


# ──────────────────────────────────────────────────────────────────────────────
# Фаза S: вспомогательная функция — SceneState → текст для DM промпта
# Дублирует логику SceneStateManager.get_scene_description() чтобы избежать
# циклического импорта. dm_agent не должен зависеть от scene_state_manager.
# ──────────────────────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────────────────────
# ПАТЧ для dm_agent.py — ФАЗА S.0
# Заменить функцию _build_scene_description() целиком.
#
# Изменения:
#   - Добавлен блок ПРОСТРАНСТВЕННЫЙ КОНТЕКСТ ИГРОКА
#   - Добавлен блок ПРАВИЛА РЕАКЦИЙ NPC
#   - _build_scene_description теперь делегирует в SceneStateManager
#     (убираем дублирование логики)
# ──────────────────────────────────────────────────────────────────────────────

def _build_scene_description(scene_state: dict) -> str:
    """
    Преобразует SceneState в текстовый блок для DM промпта.

    S.0: делегирует в SceneStateManager.get_scene_description() —
    там уже реализован полный блок включая player_target и правила реакций.

    Fallback: встроенная упрощённая версия если импорт недоступен.
    """
    if not scene_state:
        return ""

    # Пробуем использовать SceneStateManager — там полная S.0 логика
    try:
        from app.services.scene_state_manager import SceneStateManager
        return SceneStateManager.get_scene_description(scene_state)
    except Exception:
        pass

    # ── Fallback: упрощённая версия (совместимость) ───────────────────────────
    location_name = scene_state.get("location_name", scene_state.get("location_id", "?"))
    env           = scene_state.get("environment", {})
    objects       = scene_state.get("objects", {})
    npc_positions = scene_state.get("npc_positions", {})
    effects       = scene_state.get("active_effects", [])
    time_of_day   = env.get("time_of_day", "?")
    light         = env.get("light_level", "")
    noise         = env.get("noise_level", "")

    light_desc = {
        "dark": "темно", "very_dim": "почти темно", "dim": "тускло",
        "bright": "светло", "natural": "дневной свет",
    }.get(light, light)

    noise_desc = {
        "silent": "тихо", "low": "тихий фон",
        "moderate": "умеренный шум", "high": "шумно",
    }.get(noise, noise)

    state_map = {
        "intact": "цел", "damaged": "повреждён", "broken": "сломан",
        "lit": "горит", "unlit": "не горит", "burning": "горит",
        "open": "открыт", "closed_unlocked": "закрыт", "closed_locked": "заперт",
        "full": "полный", "empty": "пустой", "flowing": "течёт",
    }

    lines = [
        f"СОСТОЯНИЕ СЦЕНЫ — {location_name} | {time_of_day} | {light_desc} | {noise_desc}",
    ]

    if objects:
        parts = []
        for obj_id, obj in objects.items():
            name  = obj.get("name", obj_id)
            state = state_map.get(obj.get("state", ""), obj.get("state", ""))
            count = obj.get("count")
            cnt   = f"({count})" if count and count > 1 else ""
            parts.append(f"{name}{cnt}: {state}" if state else name)
        lines.append("Объекты: " + "; ".join(parts))

    if npc_positions:
        npc_parts = []
        for npc_id, pos in npc_positions.items():
            if pos.get("state") == "dead":
                continue
            p = pos.get("position", "")
            a = pos.get("activity", "")
            v = "" if pos.get("visible", True) else "(скрыт)"
            npc_parts.append(f"{npc_id} {v}: {p}, {a}".strip())
        if npc_parts:
            lines.append("NPC: " + "; ".join(npc_parts))

    if effects:
        lines.append("Эффекты: " + ", ".join(str(e) for e in effects))

    # S.0: player_target даже в fallback
    target_name = scene_state.get("player_target_npc_name")
    target_id   = scene_state.get("player_target_npc")
    player_pos  = scene_state.get("player_position")
    if player_pos:
        lines.append(f"Позиция игрока: {player_pos}")
    if target_name or target_id:
        name_str = target_name or target_id
        lines.append(f"Игрок обращается к: {name_str}")
        lines.append(
            f"ПРАВИЛО: только {name_str} отвечает игроку. Остальные NPC молчат."
        )

    lines.append("Упоминай ТОЛЬКО объекты и NPC из этого списка.")
    return "\n".join(lines)


class DmAgent:
    """
    Narrative DM layer with automatic model selection.
    Uses ModelRouter to request "narrative" capability.
    """

    def __init__(self, router: Optional[ModelRouter] = None) -> None:
        self._router = router

    @property
    def router(self) -> ModelRouter:
        if self._router is None:
            self._router = get_router()
        return self._router

    # ──────────────────────────────────────────────────────────────────────────
    # Основной метод (синхронный, для обычных запросов)
    # ──────────────────────────────────────────────────────────────────────────

    def run(
        self,
        location: str,
        actions: List[PlayerAction],
        rules_result: Dict,
        npc_result: Dict,
        world_result: Dict,
        world_canon_exists: bool,
        context: Optional[Dict] = None,
    ) -> Dict:
        """Main run method. SAFE FALLBACK: всегда возвращает dict."""
        try:
            return self.narrate(
                location, actions, rules_result, npc_result,
                world_result, world_canon_exists, context,
            )
        except Exception:
            return self._fallback_narrate(
                location, actions, rules_result, npc_result,
                world_result, world_canon_exists,
            )

    # ──────────────────────────────────────────────────────────────────────────
    # Построение промпта — здесь основные изменения
    # ──────────────────────────────────────────────────────────────────────────

    def _build_prompt(
        self,
        location: str,
        actions: str,
        rules_result: Dict,
        npc_result: Dict,
        world_result: Dict,
        world_canon_exists: bool,
        context: Optional[Dict] = None,
    ) -> str:
        context_str = ""
        if context:
            recent = context.get("recent_memory", [])
            print(f"[DM_CONTEXT_DEBUG] context keys={list(context.keys())[:8]} recent_memory={len(recent) if recent else 0}")
            if recent:
                # Запрет на повтор — LLM воспринимает ограничения строже чем контекст
                context_str = (
                    "УЖЕ БЫЛО СКАЗАНО (ЗАПРЕЩЕНО ПОВТОРЯТЬ дословно или по смыслу):\n"
                    + "\n".join(f"- {e}" for e in recent[-5:])
                    + "\n\nКаждый ответ должен описывать НОВОЕ состояние сцены.\n\n"
                )

        # Фаза S: SceneState — факты о мире. DM получает это первым.
        # Только объекты и NPC из этого блока реально существуют в сцене.
        scene_block = ""
        if context:
            scene_state = context.get("scene_state", {})
            if scene_state:
                try:
                    scene_block = _build_scene_description(scene_state) + "\n\n"
                except Exception:
                    pass

        # B.3/B.4: SceneContinuity — состояние сцены из Python
        continuity_block = ""
        if context:
            _cont = context.get("scene_continuity")
            if _cont:
                print(f"[CONTINUITY_DEBUG] tension={_cont.tension:.3f} flags={_cont.active_flags} events={len(_cont.recent_events)} emotion={_cont.emotional_vector}")
        if context:
            _cont = context.get("scene_continuity")
            if _cont and hasattr(_cont, "to_prompt_block"):
                _cont_block = _cont.to_prompt_block()
                if _cont_block:
                    continuity_block = _cont_block + "\n\n"
                _emotion_line = _cont.to_emotional_line()
                if _emotion_line:
                    continuity_block += _emotion_line + "\n\n"
            # Диагностика: показываем что реально попадёт в промпт
            if continuity_block:
                print(f"[CONTINUITY_FINAL]\n{continuity_block}[/CONTINUITY_FINAL]")
            else:
                print(f"[CONTINUITY_FINAL] EMPTY (tension={_cont.tension if _cont else 'NO_CONT'} flags={_cont.active_flags if _cont else 'NO_CONT'})")

        # DM получает речь NPC как контекст-только-для-чтения —
        # чтобы его описание мира было СОГЛАСОВАНО с тем что NPC уже сказали.
        # Принцип: NPC говорят → DM описывает то что ПОСЛЕ слов NPC.
        # ВАЖНО: DM не пересказывает речь, но знает о ней.
        # R3 Direct Mode: если есть dm_frame → используем SceneOutcomeBuilder
        dm_frame = npc_result.get("dm_frame")
        if dm_frame is not None:
            from app.services.verbalization.scene_outcome_builder import SceneOutcomeBuilder
            _builder = SceneOutcomeBuilder()
            npc_str = _builder.to_dm_prompt_block(dm_frame)
            # Scene Event Layer: DM видит ЧТО произошло в сцене
            _scene_events = (context or {}).get("scene_events", [])
            if _scene_events:
                _event_lines = [f"- [{e.event_type.value}] {e.summary}" for e in _scene_events]
                npc_str += "\n\nСобытия в сцене (все NPC это видят/слышат):\n" + "\n".join(_event_lines)
                print(f"[SCENE_EVENTS_DM] {len(_scene_events)} events injected")
            # Факты сцены — DM видит что УЖЕ произошло (не повторяет, но учитывает)
            _cont = context.get("scene_continuity") if context else None
            if _cont:
                _parts = []
                if _cont.scene_facts:
                    _parts.extend(f"- {f}" for f in _cont.scene_facts[-3:])
                # Флаги — DM знает о бое даже если детали не сохранились
                _important_flags = _cont.active_flags & {"combat_started", "npc_died", "violence"}
                if _important_flags:
                    _flag_labels = {
                        "combat_started": "В сцене идёт бой",
                        "npc_died": "NPC погиб",
                        "violence": "Происходит насилие",
                    }
                    _parts.extend(f"- {_flag_labels.get(f, f)}" for f in _important_flags)
                if _parts:
                    npc_str += "\n\nФАКТЫ СЦЕНЫ (ОБЯЗАТЕЛЬНО учитывай — это уже произошло, NPC это видели):\n" + "\n".join(_parts)
                    print(f"[DM_FACTS_INJECTED] {len(_parts)} items")
                # Прошлые действия игрока — DM знает ЧТО произошло до этого
                _recent_actions = (context or {}).get("recent_actions", [])
                if _recent_actions:
                    npc_str += "\n\nПрошлые действия в сцене:\n" + "\n".join(f"- {a}" for a in _recent_actions[-5:])
            npc_actions_str = ""  # DM описывает действия сам
        else:
            # Legacy: npc_reactions из npc_agent
            npc_reactions = npc_result.get("npc_reactions", [])
            npc_str = (
                "\n".join(f"- {r}" for r in npc_reactions)
                if npc_reactions else ""
            )
            npc_actions = npc_result.get("npc_actions", [])
            npc_actions_str = (
                "\n".join(f"- {a}" for a in npc_actions)
                if npc_actions else ""
            )

        world_changes = world_result.get("world_events", [])
        # Прибытие NPC от LifeEngine — DM должен их анонсировать
        _arrivals = (context or {}).get("npc_arrivals", [])
        if _arrivals:
            world_changes = list(world_changes) + [
                f"В локацию вошёл NPC: {npc_id} — опиши его появление" for npc_id in _arrivals
            ]
        world_str = "\n".join(f"- {w}" for w in world_changes) if world_changes else "Нет изменений мира"

        checks = rules_result.get("checks", [])
        rules_str = (
            "\n".join(
                f"- {c.get('player', 'Unknown')}: {c.get('result', c.get('instruction', ''))}"
                for c in checks
            )
            if checks else "Нет проверок"
        )

        physics_warnings = ""
        python_engines_block = ""
        npc_psychology_block = ""

        if context:
            # ──────────────────────────────
            # Блок physics_validation
            # ──────────────────────────────
            if context.get("physics_validation"):
                invalid = [v for v in context["physics_validation"] if not v["valid"]]
                if invalid:
                    physics_warnings = "Физические/логические ограничения сцены (ОБЯЗАТЕЛЬНО учитывай):\n"
                    for v in invalid:
                        physics_warnings += (
                            f"- Игрок пытался: {v['reason']}. "
                            f"Это невозможно потому что: {v.get('explanation', 'нарушение законов физики/логики игры')}. "
                            f"Предложи альтернативу: {v.get('alternative', 'другое действие')}\n"
                        )
                    physics_warnings += "\nТы обязан уважать эти ограничения и не допускать нарушения физики/логики.\n"

            # ──────────────────────────────
            # Блок python_engines — самый важный
            # ──────────────────────────────
            if context.get("python_engines"):
                engines = context["python_engines"]
                if engines:
                    python_engines_block = "Результаты вычислений и проверок (ОБЯЗАТЕЛЬНО используй эти данные в повествовании):\n"
                    for player_name, data in engines.items():
                        # ИСПРАВЛЕНИЕ: npc_contexts хранится в python_engines в
                        # orchestrator._run_python_engines — это list, не dict.
                        # В stream-роуте python_engines пуст, но для надёжности
                        # пропускаем любые не-dict значения чтобы не было AttributeError.
                        if not isinstance(data, dict):
                            continue
                        python_engines_block += f"Игрок {player_name}:\n"
                        if data.get("combat"):
                            c = data["combat"]
                            python_engines_block += (
                                f"- Атака: бросок {c.get('roll_str', '?')}, "
                                f"попадание: {'да' if c.get('hit') else 'нет'}, "
                                f"крит: {'да' if c.get('critical') else 'нет'}, "
                                f"урон: {c.get('damage_total', 0)} ({c.get('damage_str', '?')})\n"
                            )
                        if data.get("sandbox"):
                            s = data["sandbox"]
                            success_str = "УСПЕХ" if s.get("success") else "ПРОВАЛ"
                            cons = s.get("consequences", {})
                            cons_str = ", ".join(
                                f"{k}={v}" for k, v in cons.items()
                            ) if cons else "нет последствий"
                            python_engines_block += (
                                f"- Действие типа {s.get('action_type', 'неизвестно')}: "
                                f"{success_str}. "
                                f"Последствия: {cons_str}.\n"
                                f"  ВАЖНО: если ПРОВАЛ — действие НЕ удалось физически. "
                                f"Не описывай его как успешное.\n"
                            )
                    python_engines_block += "\nИспользуй эти точные результаты в своём повествовании. Не придумывай другие значения.\n"

            # ──────────────────────────────
            # ФАЗА 3A: Психология NPC
            # ──────────────────────────────
            # npc_contexts хранится на верхнем уровне shared_context (stream-роут)
            # или внутри python_engines["npc_contexts"] (orchestrator).
            # DM получает подсказки о поведении NPC — чтобы повествование
            # совпадало с тем что рассчитали Python-движки.
            npc_ctxs = context.get("npc_contexts") or (
                context.get("python_engines", {}).get("npc_contexts", [])
                if isinstance(context.get("python_engines"), dict) else []
            )
            if npc_ctxs:
                npc_psychology_block = "Психологическое NPC в локации (Python рассчитал):\n"
            if context and context.get("npc_recent_speech"):
                npc_psychology_block += "\nНедавние реакции NPC (что уже произошло):\n"
                npc_psychology_block += "\n".join(f"- {line}" for line in context["npc_recent_speech"])
            if context and context.get("recent_player_actions"):
                npc_psychology_block += "\nНедавние действия в сцене (DM помнит что происходило):\n"
                npc_psychology_block += "\n".join(f"- {line}" for line in context["recent_player_actions"])
                print(f"[PSYCH_ACTIONS] injected {len(context['recent_player_actions'])} actions")
            else:
                print(f"[PSYCH_ACTIONS] MISS context={context is not None} keys={list(context.keys()) if context else 'None'}")
            # R1: контекст NPC — должен быть вне conditional блоков
            for ctx in npc_ctxs:
                name  = ctx.get("npc_name", "NPC")
                hint  = ctx.get("behavior_hint", "")
                pstat = ctx.get("perceived_status", "")
                tcat  = ctx.get("threat_category", "")
                line  = f"- {name}: {hint}"
                if pstat:
                    line += f" | Игрок воспринимается как: {pstat}"
                if tcat:
                    line += f" | Уровень угрозы: {tcat}"
                npc_psychology_block += line + "\n"
            if npc_ctxs:
                npc_psychology_block += "Используй имена NPC из этого списка — не придумывай новые.\n"

                # ──────────────────────────────
        # S.4.2: ReactionPriority — кто реагирует первым
        # ──────────────────────────────
        # ── R2.1: события которые уже произошли — DM не повторяет ────────────
        scene_events_block = ""
        if context:
            scene_state_for_events = context.get("scene_state", {})
            if scene_state_for_events.get("scene_events"):
                try:
                    from app.services.scene_state_manager import SceneStateManager
                    scene_events_block = SceneStateManager.get_scene_events_block(
                        scene_state_for_events
                    ) + "\n\n"
                except Exception:
                    pass

        reaction_block = ""
        if context:
            reaction_order = context.get("reaction_order", [])
            forced = context.get("forced_first_speaker")
            if reaction_order:
                reaction_block = "ПРАВИЛО РЕАКЦИЙ (Python рассчитал — обязательно соблюдай):\n"
                if forced:
                    forced_npc = next(
                        (r for r in reaction_order if r["npc_id"] == forced), None
                    )
                    forced_name = forced_npc["npc_name"] if forced_npc else forced
                    reaction_block += f"- {forced_name} РЕАГИРУЕТ ПЕРВЫМ — он не может промолчать.\n"
                for r in reaction_order:
                    threshold = r.get("threshold", "")
                    triggers  = ", ".join(r.get("triggers", []))
                    if threshold == "must_react":
                        label = "обязан вмешаться"
                    elif threshold == "will_react":
                        label = "реагирует"
                    else:
                        label = "замечает"
                    reaction_block += (
                        f"- {r['npc_name']}: {label}"
                        + (f" (причина: {triggers})" if triggers else "")
                        + "\n"
                    )
                reaction_block += "Максимум 3 реплики NPC за ход. Остальные NPC молчат.\n"

        # R3 Direct Mode: dm_frame есть → NPC ЕЩЁ НЕ говорили → DM озвучивает
        # Legacy путь: dm_frame нет → NPC уже сказали через npc_agent
        _regime_block = ""
        if dm_frame is not None:
            _r3_npc_header = "Реакции и намерения NPC (СГЕНЕРИРУЙ реплики от их имени, соблюдай стиль):\n"
            _r3_rule3 = "Ты ДОЛЖЕН генерировать реплики NPC от их имени (кавычки или двоеточие). Пиши так: Торнин: \"Хм...\" или Люся дрожащим голосом: \"П-пожалуйста...\". Не описывай что они делают — дай им ГОВОРИТЬ."
            # ProjectionLayer: regime как инструкция, не описание
            _regime_lines = []
            for npc in dm_frame.focus_npcs:
                if npc.psychological:
                    p = npc.psychological
                    _regime_lines.append(f"- {npc.npc_id}: режим={p.regime.value}, выраженность={p.intensity:.0%}, стабильность={p.stability:.0%}")
            if _regime_lines:
                _regime_block = "ПСИХОЛОГИЧЕСКИЙ РЕЖИМ NPC (ОБЯЗАТЕЛЬНО учитывай при генерации реплик — это инструкция, не описание):\n"
                _regime_block += "\n".join(_regime_lines) + "\n"
                _regime_block += "Режим определяет тон, длину фраз, уровень агрессии/открытости. НЕ игнорируй.\n\n"
                print(f"[REGIME_BLOCK]\n{_regime_block}[/REGIME_BLOCK]")
        else:
            _r3_npc_header = "Что NPC уже сказали игроку (КОНТЕКСТ — не повторяй это, используй для согласованности своего описания):\n"
            _r3_rule3 = "Реплики NPC уже показаны игроку — НЕ повторяй их, НЕ пересказывай. Описывай мир ПОСЛЕ их слов."

        # Блок состояния игрока — аватар с живой психикой
        player_state_block = ""
        if context and context.get("player_state"):
            for pname, pdata in context["player_state"].items():
                if not pdata:
                    continue
                _lines = [f"- {pname}: HP {pdata.get('hp', '?')}, стресс {pdata.get('stress', 0)}, эмоция: {pdata.get('emotion', 'neutral')}"]
                if pdata.get("wounds") and pdata["wounds"] != "нет":
                    _lines.append(f"  травмы: {pdata['wounds']}")
                if pdata.get("conditions") and pdata["conditions"] != "нет":
                    _lines.append(f"  состояния: {pdata['conditions']}")
                if pdata.get("posture") and pdata["posture"] != "standing":
                    _lines.append(f"  поза: {pdata['posture']}")
                if pdata.get("will_state") and pdata["will_state"] != "free":
                    _lines.append(f"  воля: {pdata['will_state']}")
                _integrity = pdata.get("identity_integrity", 1.0)
                if _integrity < 0.8:
                    _lines.append(f"  целостность личности: {_integrity:.0%} — ДЕГРАДАЦИЯ")
                player_state_block = "Состояние игрока (факт — отражай в повествовании):\n" + "\n".join(_lines) + "\n\n"

        # DEBUG: проверяем что блок попал в промпт
        _psych_debug = f"[PSYCH_DEBUG] len={len(npc_psychology_block)}: {npc_psychology_block[:300] if npc_psychology_block else 'EMPTY'}" if npc_psychology_block else "[PSYCH_DEBUG] EMPTY"
        return f"""{scene_block}Текущая локация: {location}

 {context_str}
 {player_state_block}Действия игроков:
 {actions}

Результаты проверок правил:
{rules_str}

{_r3_npc_header}{npc_str if npc_str else "NPC не говорили ничего"}

{_regime_block}
Физические действия NPC (для описания мира):
{npc_actions_str if npc_actions_str else "NPC не предпринимают видимых физических действий"}

Изменения в мире:
{world_str}

{physics_warnings}
{python_engines_block}
{npc_psychology_block}
{_psych_debug}
{continuity_block}{scene_events_block}{reaction_block}
Продолжи рассказ от лица Dungeon Master. Не говори за игроков.
Опиши мир от второго лица ("ты видишь...", "ты чувствуешь...").

ЖЁСТКИЕ ПРАВИЛА — нарушение недопустимо:
1. ПРОВАЛ броска = действие физически НЕ произошло. Свеча осталась на месте. Дверь не открылась. Запрещено описывать провалившееся действие как успешное или частично успешное.
2. УСПЕХ броска = действие произошло. Опиши конкретный результат. Объект исчез со стола. NPC отреагировал на факт.
3. {_r3_rule3}
4. Используй ТОЛЬКО объекты и NPC из блока "СОСТОЯНИЕ СЦЕНЫ". Если объект не указан — его не существует.
5. Если NPC уже ронял поднос/кружки в этой сцене — он не роняет снова. Найди другую реакцию.
6. Психологическое состояние NPC из блока "Психология" — это факт, не рекомендация. Если NPC в состоянии "fearful" — он ведёт себя как напуганный, не как обычный.
7. Сцена должна РАЗВИВАТЬСЯ. Если игрок несколько раз совершает агрессивные действия — напряжение растёт, обстановка меняется, NPC эскалируют реакции.
8. Максимум 3 предложения. Не задавай вопросов.
"""

    def _get_system_prompt(self, is_r3_direct: bool = False) -> str:
        """
        Загружает системный промпт из Promt_AI.json.
        Fallback: встроенный промпт если файл недоступен.
        """
        tone = ""
        if getattr(settings, "hardcore_mode", False):
            tone = """

ТОН/РЕЖИМ: HARDCORE.
Разрешены: мрачные сцены, жестокость, кровь, смерть, грубость, мат.
Не морализируй, не сглаживай и не "перевоспитывай" игрока.
Действия имеют последствия (социальные и физические), но без цензуры.
"""
        # Пробуем загрузить из файла
        try:
            from app.services.verbalization.prompt_loader import load_system_prompt
            from app.core.config import settings as s
            file_prompt = load_system_prompt(s.system_prompt_file)
            if file_prompt and len(file_prompt) > 20:
                return file_prompt + tone
        except Exception:
            pass

        # Встроенный fallback
        # R3 Direct Mode: DM роль зависит от глобального флага
        # (npc_str недоступен в _get_system_prompt, используем feature flag)
        _r3_dm_role = "DM (ты): описываешь мир И генерируешь реплики NPC (Торнин: \"...\", Люся: \"...\")" if is_r3_direct else "DM (ты): описываешь физический мир, окружение, последствия\n- NPC агент (отдвигает реплики NPC — ты их НЕ повторяешь)"

        return f"""ВАЖНО: Отвечай ТОЛЬКО на Русском языке. Никакого английского или китайского.
ВАЖНО: Не показывай размышления. Только финальный ответ.
ВАЖНО: Никогда не генерируй теги <|im_start|>, <|im_end|>, </|im_end|>, <|file_separator|>.

Ты — Мастер Подземелий D&D 5e. Твоя задача: описывать МИР и его реакцию на действия игрока.

КТО ЧТО ДЕЛАЕТ:
- {_r3_dm_role}

АГЕНТНОСТЬ (КРИТИЧЕСКОЕ ПРАВИЛО):
РАЗРЕШЕНО описывать:
- Реакции NPC (слова, жесты, эмоции)
- Изменения окружения (только если они пришли из блока данных)
- Восприятие игрока ("ты слышишь", "ты видишь")

ЗАПРЕЩЕНО описывать:
- Действия игрока (никогда не пиши "ты опускаешься", "ты бьёшь" — игрок сам это сказал)
- Подтверждение неверифицированных заявлений игрока
  ЕСЛИ игрок говорит "я убил Торнинга" → это ЗАЯВЛЕНИЕ, не факт
  → NPC реагирует на ЗАЯВЛЕНИЕ: "Ты спятил?", "Стража!" — а не "Торнин падает замертво"
- Создание новых фактов (объекты, NPC, события которых нет в данных)

ФАКТЫ (ТИПЫ И ПРАВИЛА):
- Verified: из блока данных (объекты, состояния, расстояния)
- Claimed: сказано игроком ("я убил", "у меня меч")
- Unknown: не подтверждено
ПРАВИЛА: Claimed ≠ Verified — никогда не превращай. NPC реагируют на слова, не на факты.

ПОВЕДЕНИЕ NPC (ЗАДАНО СИСТЕМОЙ):
Для каждого NPC передаётся: stance + tone + urgency.
ТЫ НЕ ВЫБИРАЕШЬ поведение — ТЫ ВЫРАЖАЕШЬ его через текст.
- confront + aggressive → давление, короткие фразы, вызов
- probe + neutral → вопросы, подозрение
- dismiss → игнор или обесценивание
- observe → наблюдение без участия

СОСТОЯНИЕ СЦЕНЫ (ИНЕРЦИЯ):
- tension: 0.0–1.0 — НЕ уменьшается без явной причины из данных
- flags: события которые УЖЕ произошли — не повторяй
- при высоком tension реакции резче, короче

ТВОИ ПРАВИЛА:
- Веди от второго лица: "ты видишь", "ты чувствуешь", "перед тобой"
- Описывай только то что есть в блоке "СОСТОЯНИЕ СЦЕНЫ" — не придумывай объекты
- Объекты в блоке "СОСТОЯНИЕ СЦЕНЫ" уже отфильтрованы Python-движком по важности. Строй нарратив вокруг них — не упоминай другие предметы
- [ACTIVITY] NPC — вычисленное намерение Python (fleeing/fighting/observing). Отыгрывай его литературно, не переопределяй
- Результаты бросков из блока "Результаты вычислений" — закон. ПРОВАЛ = действие не случилось
- NPC реагируют РАЗНООБРАЗНО. Люся не роняет поднос каждый раз. У неё есть другие реакции: замирает, отворачивается, прижимается к стене, шепчет молитву, трясущимися руками протирает стол
- Сцена развивается линейно: каждое агрессивное действие УВЕЛИЧИВАЕТ напряжение. Не сбрасывай его
- Краткость: 3-5 предложений. Без вопросов в конце.
- Согласованность с NPC: если NPC сказал "я молчу" — DM не пишет что NPC кричит{tone}"""

    # ──────────────────────────────────────────────────────────────────────────
    # Синхронная генерация
    # ──────────────────────────────────────────────────────────────────────────

    def narrate(
        self,
        location: str,
        actions: List[PlayerAction],
        rules_result: Dict,
        npc_result: Dict,
        world_result: Dict,
        world_canon_exists: bool,
        context: Optional[Dict] = None,
    ) -> Dict:
        actions_str = (
            "\n".join(f"{a.player_name}: {a.action}" for a in actions)
            if actions else "Нет действий"
        )

        prompt = self._build_prompt(
            location, actions_str, rules_result, npc_result,
            world_result, world_canon_exists, context,
        )

        # sync метод не может await — fallback на синхронный complete()
        result = self.router.request_for_agent(
            agent="dm",
            prompt=prompt,
            system_prompt=self._get_system_prompt(is_r3_direct=(npc_result.get("dm_frame") is not None)),
            params=GenerationParams(max_tokens=220),
        )

        if isinstance(result, str):
            try:
                result = json.loads(result)
            except Exception:
                result = {"dm_response": result, "npc_reactions": [], "world_changes": []}

        return result

    # ──────────────────────────────────────────────────────────────────────────
    # Streaming генерация — для SSE роута
    # ──────────────────────────────────────────────────────────────────────────

    async def stream_narrate(self, location, actions, rules_result, npc_result,
                             world_result, world_canon_exists, context=None,
                             is_session_start=False):
        """
        Async streaming генерация для SSE роута.
        Загружает модель через ModelPool.get_model_async(), затем стримит токены.
        """
        actions_str = (
            "\n".join(f"{a.player_name}: {a.action}" for a in actions)
            if actions else "Нет действий"
        )
        if is_session_start:
            prompt = self._build_intro_prompt(location, context or {})
        else:
            prompt = self._build_prompt(
                location, actions_str, rules_result, npc_result,
                world_result, world_canon_exists, context,
            )
        system_prompt = self._get_system_prompt(is_r3_direct=(npc_result.get("dm_frame") is not None))

        from app.services.logging_tools import jsonl_log
        _prompt_preview = (prompt[:500] + '...') if len(prompt) > 500 else prompt
        _sys_preview = (system_prompt[:200] + '...') if system_prompt and len(system_prompt) > 200 else system_prompt
        jsonl_log({
            "level": "INFO",
            "agent": "llm_input",
            "capability": "narrative",
            "prompt_preview": _prompt_preview,
            "system_prompt": _sys_preview or "",
        })

        provider = await self._get_provider_async("narrative")

        if provider is None or not hasattr(provider, "stream_tokens"):
            result = await self.router.request(
                capability="narrative",
                prompt=prompt,
                system_prompt=system_prompt,
                params=GenerationParams(max_tokens=220),
            )
            if isinstance(result, dict):
                yield result.get("dm_response", "")
            else:
                yield str(result)
            return

        import asyncio
        import threading

        q: asyncio.Queue[str | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _producer():
            token_num = 0
            buffer = ""  # буфер для поимки стоп-токенов разбитых между чанками
            tail_len = max(len(st) for st in _STOP_TOKENS)
            try:
                for token in provider.stream_tokens(
                    prompt=prompt,
                    params=GenerationParams(max_tokens=220),
                    system_prompt=system_prompt,
                ):
                    if not token:
                        continue
                    token_num += 1
                    buffer += token

                    # Проверяем буфер на стоп-токены
                    if _has_stop_token(buffer):
                        # Обрезаем по первому стоп-токену, отправляем чистый остаток
                        clean = _strip_stop_tokens(buffer)
                        if clean:
                            asyncio.run_coroutine_threadsafe(q.put(clean), loop)
                        # Стоп-токен — завершаем стриминг немедленно
                        asyncio.run_coroutine_threadsafe(q.put(None), loop)
                        return

                    # Держим хвост на случай стоп-токена разбитого между чанками
                    if len(buffer) > tail_len:
                        to_send = buffer[:-tail_len]
                        buffer  = buffer[-tail_len:]
                        if to_send and len(to_send) > 24:
                            step = 12
                            for i in range(0, len(to_send), step):
                                asyncio.run_coroutine_threadsafe(q.put(to_send[i:i+step]), loop)
                        elif to_send:
                            asyncio.run_coroutine_threadsafe(q.put(to_send), loop)

                # Конец стрима — отправляем остаток буфера
                if buffer:
                    clean = _strip_stop_tokens(buffer)
                    if clean:
                        asyncio.run_coroutine_threadsafe(q.put(clean), loop)

            except Exception as e:
                asyncio.run_coroutine_threadsafe(q.put(f"\n[Ошибка стриминга: {e}]"), loop)
            finally:
                asyncio.run_coroutine_threadsafe(q.put(None), loop)

        threading.Thread(target=_producer, daemon=True).start()

        while True:
            item = await q.get()
            if item is None:
                break
            yield item

    async def _get_provider_async(self, capability: str):
        from app.services.llm.router import Capability, CAPABILITY_MODEL_PREFERENCES
        from app.services.llm.provider_manager import get_model_pool
    
        capability_obj = Capability(capability) if isinstance(capability, str) else capability
        preferred_keys = CAPABILITY_MODEL_PREFERENCES.get(capability_obj, [])
    
        pool = get_model_pool()
        if pool is None:
            return None
    
        for model_key in preferred_keys:
            if pool.is_model_available(model_key):
                model_provider = await pool.get_model_async(
                    model_key, 
                    agent="dm_narrative",
                    timeout_sec=60
                )
                if model_provider and model_provider.is_available():
                    return model_provider.provider
    
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # Промт начала игры
    # 

    def _build_intro_prompt(self, location: str, context: dict) -> str:
            """Промпт для вводного описания сцены в начале сессии."""
            scene_block = ""
            if context:
                scene_state = context.get("scene_state", {})
                if scene_state:
                    try:
                        scene_block = _build_scene_description(scene_state) + "\n\n"
                    except Exception:
                        pass

            return f"""{scene_block}Текущая локация: {location}
            
Ты — Мастер игры. Начинается новая игровая сессия. Игроки только что вошли в сцену.

Напиши атмосферное вводное описание локации от второго лица ("ты видишь...", "ты чувствуешь...").
Упомяни только объекты и NPC из блока СОСТОЯНИЕ СЦЕНЫ выше.
Создай настроение — время суток, освещение, звуки, запахи.
Максимум 3-4 предложения. Без вопросов в конце.
"""

    # ──────────────────────────────────────────────────────────────────────────
    # Fallback
    # ──────────────────────────────────────────────────────────────────────────

    def _fallback_narrate(
        self,
        location: str,
        actions: List[PlayerAction],
        rules_result: Dict,
        npc_result: Dict,
        world_result: Dict,
        world_canon_exists: bool,
    ) -> Dict:
        return {
            "dm_response": "Ничего не произошло.",
            "npc_reactions": [],
            "world_changes": [],
        }
