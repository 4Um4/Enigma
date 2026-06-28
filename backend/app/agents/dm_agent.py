# C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\agents\dm_agent.py
# -*- coding: utf-8 -*-
"""
DM Agent - Dungeon Master Narrative Layer

Uses capability-based routing to automatically select the best model.
Includes Phase 1 error handling + VRAM logging.
"""

import json
import asyncio
import threading
from typing import Optional, List, Dict

from app.models.schemas import PlayerAction
from app.services.llm import ModelRouter, get_router
from app.services.llm.provider import GenerationParams
from app.core.config import settings
from app.services.logging_tools import jsonl_log
from app.services.verbalization.prompt_loader import load_system_prompt
from app.services.scene_state_manager import SceneStateManager

# ───────────────────────────────────────────────────────────────────────────────
# Стоп-токены ChatML (Qwen2.5)
# ───────────────────────────────────────────────────────────────────────────────
_STOP_TOKENS = [
    "<|file_separator|>",
    "<|end_of_turn|>",
    "<end_of_turn>",
    "<|im_end|>",
    "</|im_end|>",
    "<|im_start|>",
    "</|im_start|>",
    "</s>",
    "<|endoftext|>",
    "<|file_end|>",
    "<|file_sep|>",
    "<|end|>",
    "<|user|>",
    "<|assistant|>"
]

# Константы для хардкода
MSG_NOTHING_HAPPENED = "Ничего не произошло."
MSG_ALREADY_SAID = "УЖЕ БЫЛО СКАЗАНО"
MSG_REACTION_RULE = "ПРАВИЛО РЕАКЦИЙ"
MSG_MAX_REPLIES = "Максимум 3 реплики"

def _strip_stop_tokens(text: str) -> str:
    """Убирает стоп-токены из строки. Обрезает по первому вхождению."""
    for token in _STOP_TOKENS:
        idx = text.find(token)
        if idx != -1:
            text = text[:idx]
    return text.strip()

def _has_stop_token(text: str) -> bool:
    return any(st in text for st in _STOP_TOKENS)

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
        except Exception as e:
            import traceback
            print(f"[DM_AGENT_CRASH] {type(e).__name__}: {e}")
            traceback.print_exc()
            jsonl_log({"level": "ERROR", "agent": "dm_agent", "error": str(e)})
            return self._fallback_narrate()

    @staticmethod
    def _has_real_check_flag(rules_result: Dict) -> bool:
        """Есть ли реальный бросок (не автоуспех)."""
        if not rules_result:
            return False
        for c in rules_result.get("checks", []):
            if c.get("result") not in ("Нет проверок", None, ""):
                if "автоматический" not in str(c.get("result", "")).lower():
                    return True
            if c.get("instruction"):
                return True
        return False

    def _build_contract(
        self,
        location: str,
        actions_str: str,
        rules_result: Dict,
        npc_result: Dict,
        world_result: Dict,
        context: Optional[Dict] = None,
    ) -> "DMContract":
        """Строит DMContract через DMContractBuilder."""
        from app.services.verbalization.dm_contract_builder import DMContractBuilder
        from app.core.config import settings
        
        builder = DMContractBuilder(
            hardcore_mode=getattr(settings, "hardcore_mode", False),
            max_sentences=3,
        )
        
        # Intro для первой сессии — атмосферное описание вместо пустого промпта
        _is_session_start = context.get("session_start", False) if context else False
        if _is_session_start:
            _scene_block = ""
            _scene_state = context.get("scene_state", {}) if context else {}
            if _scene_state:
                # ИСПРАВЛЕНО: путь импорта. Реальный модуль — app.services.scene_state_manager
                # (без '.scene.' в середине). Убран try/except: pass — он маскировал
                # ModuleNotFoundError, и вводная сцена всегда была пустой.
                from app.services.scene_state_manager import SceneStateManager
                _scene_block = SceneStateManager.get_scene_description(_scene_state) + "\n\n"
            builder.add_custom_block("ВВОДНАЯ СЦЕНА", 
                f"{_scene_block}Текущая локация: {(context or {}).get('location_id', 'таверна')}\n\n"
                "Напиши атмосферное описание от второго лица ('ты видишь...'). 2-3 предложения. Без вопросов."
            )
            # После intro — стандартные блоки (DMFrame, таргет и т.д.)
        
        # Определяем тип действия — для диалога пропускаем шумные блоки
        _action_type = ""
        if rules_result:
            for _c in rules_result.get("checks", []):
                _action_type = _c.get("action_type", "")
                break
        _is_light_dialog = (
            _action_type in ("SANDBOX_MILD", "SANDBOX_MEDIUM")
            and not self._has_real_check_flag(rules_result)
        )
        
        # Блок 1: Действия игрока — всегда первый
        builder.add_player_action(actions_str)
        
        # Блок 2: DMFrame или legacy npc_reactions
        _dm_frame_block = ""
        _dm_frame = npc_result.get("dm_frame") if npc_result else None
        if _dm_frame is not None:
            from app.services.verbalization.scene_outcome_builder import SceneOutcomeBuilder
            _dm_frame_block = SceneOutcomeBuilder().to_dm_prompt_block(_dm_frame)
        
        npc_reactions = npc_result.get("npc_reactions", []) if npc_result else []
        npc_actions = npc_result.get("npc_actions", []) if npc_result else []
        
        if _dm_frame_block:
            builder.add_dm_frame(_dm_frame_block)
        elif npc_reactions:
            _r3_header = "Что NPC уже сказали игроку (КОНТЕКСТ — не повторяй это, используй для согласованности своего описания):\n"
            npc_str = "\n".join(f"- {r}" for r in npc_reactions)
            builder.add_dm_frame(_r3_header + npc_str)
            if npc_actions:
                builder.add_custom_block("Физические действия NPC", "\n".join(f"- {a}" for a in npc_actions))
        
        # Блок 2.3b: Физические перемещения NPC (из PipelineContext)
        # Инвариант 2: Обязательная проекция намерения.
        # LLM НЕ имеет права описывать движение NPC, которого нет в этом списке.
        _npc_moves = npc_result.get("npc_movement_summary", []) if npc_result else []
        if _npc_moves:
            builder.add_custom_block(
                "Действия NPC (факт — отражай в повествовании)",
                "\n".join(f"- {m}" for m in _npc_moves)
            )
        else:
            # Инвариант 2: Явный запрет галлюцинации движения
            builder.add_custom_block(
                "Действия NPC (факт — отражай в повествовании)",
                "Никто из NPC не перемещается. ЗАПРЕЩЕНО описывать приближение, отход или любое изменение позиции NPC."
            )
        
        # Блок 2.4: STM — последние реплики диалога (из WorkingMemory через game_loop)
        _recent_speech = (context or {}).get("npc_recent_speech", [])
        print(f"[STM_INJECT] npc_recent_speech={_recent_speech}")
        if _recent_speech:
            builder.add_npc_stm("\n".join(_recent_speech))
        
        # Epistemic Boundary: Ментальные объекты NPC (L2 память, секреты, черты) 
        # скрыты от DM-агента. DM описывает только то, что физически проявлено.

        # Блок 2.6: Кому обращается игрок — без этого DM не знает что NPC должен отвечать
        if context:
            # Явный таргет из текста всегда приоритетнее sticky
            _target_id = context.get("player_target_id", "")
            if _target_id:
                # Обновляем sticky только для явного таргета, не для fallback
                self._last_target_id = _target_id
                # ADR-O-148: Каноническое имя NPC — единый источник истины.
                # DM НИКОГДА не должен видеть npc_id ("maid_lusya") — только display_name ("Люся").
                # Приоритет: DMFrame → _npc_id_to_display (config cache) → эвристика
                _target_name = _target_id  # абсолютный fallback
                # 1. Попытка из DMFrame (NpcOutcome.name из runtime state)
                if _dm_frame:
                    for _npc in _dm_frame.focus_npcs + _dm_frame.background_npcs:
                        if _npc.npc_id == _target_id and _npc.name and _npc.npc_id != _npc.name:
                            _target_name = _npc.name
                            break
                # 2. Если DMFrame не дал имени — используем канонический резолвер
                if _target_name == _target_id:
                    from app.services.scene_state_manager import _npc_id_to_display
                    _resolved = _npc_id_to_display(_target_id)
                    if _resolved != _target_id:
                        _target_name = _resolved
                builder.add_custom_block(
                    "Обращение игрока",
                    f"Игрок обращается напрямую к {_target_name}. {_target_name} ОБЯЗАН ответить — реплика в кавычках. Это диалог, NPC говорит. Остальные NPC — наблюдатели (могут отреагировать мимикой или жестом, но молчат)."
                )
        
        # Блок 3: Сцена — ADR-DM-001: ВСЕГДА минимум (локация + кто рядом)
        # Full mode: полная сцена с объектами. Light mode: только локация + присутствующие NPC.
        scene_block = ""
        if context:
            scene_state = context.get("scene_state", {})
            if scene_state:
                if not _is_light_dialog:
                    # Полная сцена (объекты, мебель, атмосфера)
                    try:
                        scene_block = SceneStateManager.get_scene_description(scene_state) + "\n\n"
                    except Exception as e:
                        jsonl_log({"level": "ERROR", "agent": "dm_agent", "error": f"Scene build error: {e}"})
                else:
                    # Минимальная сцена для диалога — кто в комнате
                    _npc_pos = scene_state.get("npc_positions", {})
                    _present = []
                    for _nid, _ndata in _npc_pos.items():
                        if _nid == "player":
                            continue
                        _nname = _ndata.get("name", _nid) if isinstance(_ndata, dict) else _nid
                        _activity = _ndata.get("activity", "") if isinstance(_ndata, dict) else ""
                        _act_str = f" ({_activity})" if _activity else ""
                        _present.append(f"{_nname}{_act_str}")
                    if _present:
                        scene_block = f"В помещении: {', '.join(_present)}.\n\n"
        builder.add_scene(scene_block, location)
        
        # Блок 4: Состояние игрока — ВСЕГДА если есть раны/стресс, skip только если полностью спокойный
        player_state_block = ""
        _skip_player_state = False  # ADR-DM-001: никогда не пропускать автоматически
        if context and context.get("player_state"):
            _lines = []
            for pname, pdata in context["player_state"].items():
                if not pdata or not isinstance(pdata, dict):
                    continue
                _stress_val = pdata.get("stress", 0)
                if _stress_val > 1.0:
                    _stress_word = "в напряжении" if _stress_val >= 60 else ("нервничает" if _stress_val >= 30 else "спокоен")
                else:
                    _stress_word = "в напряжении" if _stress_val >= 0.6 else ("нервничает" if _stress_val >= 0.3 else "спокоен")
                _lines.append(f"- {pname}: {_stress_word}, эмоция: {pdata.get('emotion', 'neutral')}")
                # P3: DM видит смерть как факт из player_state, не вычисляет
                if pdata.get("life_status") == "DEAD":
                    _lines.append(f"  МЁРТВ — смерть необратима")
                wounds = pdata.get("wounds")
                if wounds and wounds != "нет":
                    wounds_str = ", ".join(wounds) if isinstance(wounds, list) else str(wounds)
                    _lines.append(f"  травмы: {wounds_str}")
                conditions = pdata.get("conditions")
                if conditions and conditions != "нет":
                    cond_str = ", ".join(conditions) if isinstance(conditions, list) else str(conditions)
                    _lines.append(f"  состояния: {cond_str}")
                if pdata.get("posture") and pdata["posture"] != "standing":
                    _lines.append(f"  поза: {pdata['posture']}")
                if pdata.get("will_state") and pdata["will_state"] != "free":
                    _lines.append(f"  воля: {pdata['will_state']}")
                _integrity = pdata.get("identity_integrity", 1.0)
                if isinstance(_integrity, (int, float)) and _integrity < 0.8:
                    _lines.append(f"  целостность личности снижена — ДЕГРАДАЦИЯ")
            if _lines:
                # Для диалога пропускаем если только "спокоен" без ран
                if _skip_player_state and len(_lines) <= 1 and "спокоен" in _lines[0]:
                    player_state_block = ""
                else:
                    player_state_block = "Состояние игрока (факт — отражай в повествовании):\n" + "\n".join(_lines)
        builder.add_player_state(player_state_block)
        
        # P3: Death Scene — DM narrates смерть как проекция замороженного state
        # DM НЕ вычисляет смерть — life_status читается из player_state (проекция S75)
        _is_player_dead = False
        if context and context.get("player_state"):
            for _dp_name, _dp_data in context["player_state"].items():
                if isinstance(_dp_data, dict) and _dp_data.get("life_status") == "DEAD":
                    _is_player_dead = True
                    break
        if _is_player_dead:
            builder.add_custom_block(
                "СМЕРТЬ ИГРОКА",
                "Игрок мёртв. Это необратимо. Опиши момент смерти — последний вздох, угасание сознания, "
                "реакцию окружающего мира и свидетелей. Не предлагай вариантов воскрешения. "
                "Мир продолжает жить — NPC реагируют на произошедшее. "
                "Тон: трагический, финальный. Максимум 4 предложения."
            )
        
        # Блок 4.5: Наблюдаемые симптомы NPC (The Fool: только видимые следы, не внутренние состояния)
        # ADR-DM-001: Симптомы — ВСЕГДА. DM описывает что видит игрок, даже в диалоге.
        if context:
            _perception = getattr(context, 'player_perception', None) if hasattr(context, 'player_perception') else (context.get('player_perception') if isinstance(context, dict) else None)
            _traces = []
            if isinstance(_perception, dict):
                _traces = _perception.get('embodied_traces', [])
            elif _perception and hasattr(_perception, 'embodied_traces'):
                _traces = _perception.embodied_traces
            if _traces:
                _obs_lines = []
                for _t in _traces:
                    if isinstance(_t, dict):
                        _npc_name = _t.get('npc_name', _t.get('npc_id', '???'))
                        # Собираем наблюдаемые моторные симптомы (не эмоции!)
                        _symptoms = []
                        if _t.get('is_shaking'): _symptoms.append("явно дрожит")
                        if _t.get('is_frozen'): _symptoms.append("замер на месте")
                        if _t.get('locomotion_instability', 0) > 0.2: _symptoms.append("покачивается")
                        if _t.get('posture_rigidity', 0) > 0.3: _symptoms.append("напряжённая поза")
                        if _t.get('locomotion_instability', 0) > 0.7: _symptoms.append("шатается")
                        if _symptoms:
                            _obs_lines.append(f"- {_npc_name}: {', '.join(_symptoms)}")
                if _obs_lines:
                    builder.add_custom_block("Наблюдаемые симптомы NPC (видимые — отражай в повествовании)", "\n".join(_obs_lines))
        
        # Блок 4.7: Контекст NPC (роль, описание — для правдоподобного нарратива)
        # ADR-DM-001: NPC онтология — ВСЕГДА в промпте. Без этого DM не знает КТО перед ним.
        _anr = getattr(context, 'all_npcs_raw_snapshot', None) if context else None
        if _anr is None and isinstance(context, dict):
            _anr = context.get('all_npcs_raw_snapshot')
        if _anr:
            _npc_ctx_lines = []
            for _npc in _anr:
                if not isinstance(_npc, dict):
                    continue
                _nid = _npc.get("npc_id") or _npc.get("id", "")
                if _nid == "player":
                    continue
                _desc = _npc.get("description", "")
                _title = ""
                _sp = _npc.get("status_profile")
                if isinstance(_sp, dict):
                    _title = _sp.get("title", "")
                _name = _npc.get("name", _nid)
                if _desc or _title:
                    _role_str = f"{_title}: " if _title else ""
                    _line = f"- {_name}: {_role_str}{_desc}"
                else:
                    _line = f"- {_name}"
                # SHI-FIX VOICE: добавляем voice_profile (стиль речи) и author_notes (режиссёрская)
                _voice = _npc.get("voice_profile", "")
                _author = _npc.get("author_notes", "")
                if _voice:
                    _line += f"\n  Голос: {_voice}"
                if _author and getattr(settings, "hardcore_mode", False):
                    _line += f"\n  Режиссёрская: {_author}"
                _npc_ctx_lines.append(_line)
            if _npc_ctx_lines:
                builder.add_custom_block("Контекст NPC (кто они и как говорят — используй для правдоподобия)", "\n".join(_npc_ctx_lines))
        
        # Блок 5: Проверки — для диалога пропускаем автоуспех
        if not _is_light_dialog:
            checks = rules_result.get("checks", []) if rules_result else []
            _has_real_check = any(
                c.get('result') not in ('Нет проверок', None, '')
                and 'провал' not in str(c.get('result', '')).lower()
                or c.get('instruction')
                for c in checks
            ) if checks else False
            rules_str = (
                "\n".join(
                    f"- {c.get('player', 'Unknown')}: {c.get('result', c.get('instruction', ''))}"
                    for c in checks
                )
                if _has_real_check else ""
            )
            builder.add_rules(rules_str)
        
        # Блок 6: Изменения мира — для диалога только если кто-то пришёл
        _arrivals = (context or {}).get("npc_arrivals", [])
        if not _is_light_dialog or _arrivals:
            world_changes = world_result.get("world_events", []) if world_result else []
            if _arrivals:
                world_changes = list(world_changes) + [
                    f"В локацию вошёл NPC: {npc_id} — опиши его появление" for npc_id in _arrivals
                ]
            world_str = "\n".join(f"- {w}" for w in world_changes) if world_changes else ""
            if world_str:
                builder.add_world_changes(world_str)
        
        # Блок 7: Continuity
        continuity_block = ""
        if context:
            _cont = context.get("scene_continuity")
            if _cont and hasattr(_cont, "to_prompt_block"):
                continuity_block = _cont.to_prompt_block() + "\n\n"
        builder.add_continuity(continuity_block)
        
        # Блок 8: Guardrail — для 7B нельзя показывать предыдущий текст (модель его повторяет)
        # Вместо этого — краткий флаг без содержимого
        guardrail = ""
        if context:
            recent = context.get("recent_memory", [])
            _meaningful = [e for e in recent[-5:] if MSG_NOTHING_HAPPENED not in str(e)]
            if _meaningful:
                guardrail = "ЗАПРЕЩЕНО: повторять предыдущий ответ дословно или по смыслу. Опиши НОВУЮ реакцию."
        builder.add_guardrail(guardrail)
        
        # Блок 9: Физические ограничения + Python движки — только для не-диалогов
        if context and not _is_light_dialog:
            physics_warnings = ""
            if context.get("physics_validation"):
                invalid = [v for v in context["physics_validation"] if not v.get("valid")]
                if invalid:
                    physics_warnings = "Физические/логические ограничения сцены (ОБЯЗАТЕЛЬНО учитывай):\n"
                    for v in invalid:
                        physics_warnings += (
                            f"- Игрок пытался: {v.get('reason', 'неизвестно')}. "
                            f"Это невозможно потому что: {v.get('explanation', 'нарушение законов физики/логики игры')}. "
                            f"Предложи альтернативу: {v.get('alternative', 'другое действие')}\n"
                        )
                    physics_warnings += "\nТы обязан уважать эти ограничения и не допускать нарушения физики/логики.\n"
            builder.add_custom_block("Физические ограничения", physics_warnings)
            
            # Результаты вычислений — добавляем только если есть реальные данные
            _has_engine_data = False
            python_engines_block = ""
            if context.get("python_engines"):
                engines = context.get("python_engines")
                if isinstance(engines, dict) and engines:
                    for player_name, data in engines.items():
                        if not isinstance(data, dict):
                            continue
                        _player_block = ""
                        if data.get("combat"):
                            c = data["combat"]
                            _player_block += (
                                f"- Атака: бросок {c.get('roll_str', '?')}, "
                                f"попадание: {'да' if c.get('hit') else 'нет'}, "
                                f"крит: {'да' if c.get('critical') else 'нет'}, "
                                f"урон: {c.get('damage_total', 0)} ({c.get('damage_str', '?')})\n"
                            )
                        if data.get("sandbox"):
                            s = data["sandbox"]
                            success_str = "УСПЕХ" if s.get("success") else "ПРОВАЛ"
                            cons = s.get("consequences", {})
                            cons_str = ", ".join(f"{k}={v}" for k, v in cons.items()) if cons else "нет последствий"
                            _player_block += (
                                f"- {success_str}: {s.get('action_type', '?')}. {cons_str}.\n"
                            )
                        if _player_block:
                            _has_engine_data = True
                            python_engines_block += f"Игрок {player_name}:\n{_player_block}"
            if _has_engine_data and not _is_light_dialog:
                builder.add_custom_block("Результаты проверок", python_engines_block)
        
        # Блок 5.5: Combat Outcome (физические последствия для DM)
        _combat_data = {}
        if context:
            _combat_data = getattr(context, 'combat_data', None) or (context.get('combat_data', {}) if isinstance(context, dict) else {})
        if _combat_data and not _is_light_dialog:
            _combat_lines = []
            for _npc_id, _cd in _combat_data.items():
                # Промах по расстоянию
                if _cd.get("miss"):
                    _combat_lines.append(f"- {_npc_id}: НЕ ДОСТИГНУТ — слишком далеко ({_cd.get('distance', '?')}м, достать можно до {_cd.get('max_range', '?')}м)")
                    continue
                _hit_parts = []
                if _cd.get("pain_delta", 0) > 0:
                    _hit_parts.append(f"боль +{_cd['pain_delta']:.0f}")
                if _cd.get("shock_impulse", 0) > 0:
                    _hit_parts.append(f"шок {_cd['shock_impulse']:.2f}")
                if _cd.get("blood_loss_delta", 0) > 0:
                    _hit_parts.append(f"кровопотеря +{_cd['blood_loss_delta']:.2f}")
                for _inj in _cd.get("injuries", []):
                    _hit_parts.append(f"травма: {_inj.get('zone', '?')} ({_inj.get('severity', '?')}, {_inj.get('damage_type', '?')})")
                if _hit_parts:
                    _combat_lines.append(f"- {_npc_id}: {', '.join(_hit_parts)}")
            if _combat_lines:
                builder.add_custom_block("Последствия атаки (факт — отражай в повествовании)", "\n".join(_combat_lines))
            
            scene_events_block = ""
            if context.get("scene_state", {}).get("scene_events"):
                try:
                    scene_events_block = SceneStateManager.get_scene_events_block(
                        context["scene_state"]
                    )
                except Exception as e:
                    jsonl_log({"level": "ERROR", "agent": "dm_agent", "error": f"Scene events error: {e}"})
            builder.add_custom_block("События сцены", scene_events_block)
            
            reaction_block = ""
            if not _is_light_dialog and context.get("reaction_order"):
                reaction_order = context["reaction_order"]
                forced = context.get("forced_first_speaker")
                if reaction_order:
                    reaction_block = f"{MSG_REACTION_RULE} (Python рассчитал — обязательно соблюдай):\n"
                    if forced:
                        forced_npc = next((r for r in reaction_order if r.get("npc_id") == forced), None)
                        forced_name = forced_npc.get("npc_name", forced) if forced_npc else forced
                        reaction_block += f"- {forced_name} РЕАГИРУЕТ ПЕРВЫМ — он не может промолчать.\n"
                    for r in reaction_order:
                        threshold = r.get("threshold", "")
                        triggers = ", ".join(r.get("triggers", []))
                        if threshold == "must_react":
                            label = "обязан вмешаться"
                        elif threshold == "will_react":
                            label = "реагирует"
                        else:
                            label = "замечает"
                        reaction_block += (
                            f"- {r.get('npc_name', 'Unknown')}: {label}"
                            + (f" (причина: {triggers})" if triggers else "")
                            + "\n"
                        )
                    reaction_block += f"{MSG_MAX_REPLIES} NPC за ход. Остальные NPC молчат.\n"
            builder.add_custom_block("Очередность реакций", reaction_block)
        
        # Финальная директива — для 7B последний блок имеет наибольший вес
        _final_lines = [f"Игрок: {actions_str.strip()}"]
        if _target_id:
            _final_lines.append(f"Опиши реакцию {_target_name}. Не описывай перемещение — NPC уже рядом.")
        builder.add_custom_block("РЕАКЦИЯ", "\n".join(_final_lines))
        
        # Строим контракт с внешним system_prompt
        system_prompt = self._get_system_prompt(is_r3_direct=(_dm_frame is not None))
        return builder.build(system_prompt=system_prompt)

    def _build_prompt(
        self,
        location: str,
        actions_str: str,
        rules_result: Dict,
        npc_result: Dict,
        world_result: Dict,
        context: Optional[Dict] = None,
    ) -> str:
        """Обёртка для совместимости — делегирует на _build_contract."""
        contract = self._build_contract(
            location, actions_str, rules_result, npc_result,
            world_result, context,
        )
        # Диагностика: первый раз печатаем полный промпт
        if not getattr(self, '_prompt_printed', False):
            print(f"[DM_CONTRACT]\nsystem: {contract.system_prompt[:200]}...\nuser: {contract.user_prompt[:1200]}...\n[/DM_CONTRACT]")
            self._prompt_printed = True
        return contract.user_prompt

    def _get_system_prompt(self, is_r3_direct: bool = False) -> str:
        """Загружает системный промпт из файла. Fallback — минимальный."""
        try:
            file_prompt = load_system_prompt(settings.system_prompt_file)
            if file_prompt and len(file_prompt) > 20:
                return file_prompt
        except Exception:
            pass
        
        # Fallback — только если файл промпта отсутствует
        return "Ты — Мастер Подземелий D&D 5e. Отвечай ТОЛЬКО по-русски. НЕ ПИШИ по-китайски (中文). 2-3 предложения. Не говори за игрока."

    @staticmethod
    def _as_dict(ctx) -> dict:
        """PipelineContext → dict. Совместимость с legacy .get()/[] в _build_contract."""
        if ctx is None:
            return {}
        if isinstance(ctx, dict):
            return ctx
        from dataclasses import asdict
        return asdict(ctx)

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
        context = self._as_dict(context)
        actions_str = (
            "\n".join(f"{a.player_name}: {a.action}" for a in actions)
            if actions else "Нет действий"
        )

        # Строим контракт (содержит system + user prompt)
        contract = self._build_contract(
            location, actions_str, rules_result, npc_result,
            world_result, context,
        )
        
        # Диагностика: конец промпта (для 7B последний блок = самый влиятельный)
        _sys_words = len(contract.system_prompt.split())
        _usr_words = len(contract.user_prompt.split())
        print(f"[DM_CONTRACT] id={contract.contract_id} sys_tokens~{_sys_words} user_tokens~{_usr_words}")
        print(f"[DM_CONTRACT] user (last 800 chars):\n...{contract.user_prompt[-800:]}\n[/DM_CONTRACT]")
        
        if not contract.user_prompt.strip():
            # Контракт пустой — не отправляем в LLM, сразу fallback
            jsonl_log({"level": "ERROR", "agent": "dm_agent", "error": "Empty contract", "action": actions_str})
            return self._fallback_narrate()

        raw = self.router.request_for_agent(
            agent_name="dm",
            prompt=contract.user_prompt,
            system_prompt=contract.system_prompt,
            params=GenerationParams(max_tokens=settings.dm_max_tokens),
        )

        # A3-FIX: Вынесено в DMResponseNormalizer (DM Output Contract Layer).
        from app.services.verbalization.dm_response_normalizer import DMResponseNormalizer
        dm_output = DMResponseNormalizer.normalize(raw)
        dm_text = dm_output.dm_text

        # FIX-3: Убрано `dm_text = result.get("dm_response", "")` —
        # result здесь не существует (DMResponseNormalizer возвращает DMOutput, не dict).
        # Это вызывало NameError → пустой dm_text → валидатор fallback → "Ничего не произошло".
        # dm_text уже установлен из dm_output.dm_text выше.

        # 2. Валидация — только текст dm_response, не сырой JSON
        from app.services.verbalization.response_validator import ResponseValidator
        validator = ResponseValidator(contract)
        # A4-FIX: передаём recent_text для проверки повторов.
        _recent = self._get_last_dm_response()
        validation = validator.validate(dm_text, recent_text=_recent)

        if validation.is_fallback and validation.violation == "non_russian":
            # ADR-O-147: CJK Retry — модель сгенерировала китайский.
            # Вместо слепого fallback — повторяем запрос с усиленным языковым якорем.
            _RUSSIAN_REINFORCE = (
                "\n\n!!! ВНИМАНИЕ: Твой предыдущий ответ содержал китайские иероглифы. "
                "Это КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО. Пиши ТОЛЬКО по-русски. "
                "Каждое слово — русское. Ни одного китайского символа. !!!\n"
            )
            _reinforced_system = contract.system_prompt + _RUSSIAN_REINFORCE
            jsonl_log({"level": "WARN", "agent": "dm_agent", "event": "cjk_retry_1", "original_preview": dm_text[:100]})

            raw_retry = self.router.request_for_agent(
                agent_name="dm",
                prompt=contract.user_prompt,
                system_prompt=_reinforced_system,
                params=GenerationParams(max_tokens=settings.dm_max_tokens),
            )
            if isinstance(raw_retry, str):
                try:
                    _result_retry = json.loads(raw_retry)
                    # json.loads может вернуть str/int/list — оборачиваем в dict
                    if not isinstance(_result_retry, dict):
                        _result_retry = {"dm_response": str(_result_retry).strip()}
                except Exception:
                    _result_retry = {"dm_response": raw_retry.strip()}
            else:
                _result_retry = raw_retry if isinstance(raw_retry, dict) else {"dm_response": str(raw_retry)}

            dm_text = _result_retry.get("dm_response", "")
            # A4-FIX: передаём recent_text для проверки повторов.
            _recent = self._get_last_dm_response()
            validation = validator.validate(dm_text, recent_text=_recent)

        if validation.is_fallback:
            jsonl_log({"level": "WARN", "agent": "dm_agent", "violation": validation.violation, "fallback_text": validation.text})
            dm_text = validation.text

        # FIX-4: Гарантируем, что возвращаем dict с dm_response.
        # result может не существовать, если не было CJK retry.
        return {"dm_response": dm_text}

    def _get_last_dm_response(self) -> Optional[str]:
        """Возвращает последний DM-ответ из истории (safe access)."""
        mem_mgr = getattr(self, "_memory_manager", None)
        if not mem_mgr:
            return None
        try:
            journal = mem_mgr.get_recent_dm_responses(limit=1)
            if journal:
                return journal[0]
        except Exception as e:
            logger.warning(f"[DM_AGENT] could not get recent DM response: {e}")
        return None

    async def stream_narrate(self, location, actions, rules_result, npc_result,
                             world_result, world_canon_exists, context=None,
                             is_session_start=False):
        """
        Async streaming генерация для SSE роута.
        Загружает модель через ModelPool.get_model_async(), затем стримит токены.
        """
        context = self._as_dict(context)
        actions_str = (
            "\n".join(f"{a.player_name}: {a.action}" for a in actions)
            if actions else "Нет действий"
        )
        
        # Контракт всегда — intro через флаг в контексте, не отдельный промпт
        if is_session_start and context:
            context["session_start"] = True
        prompt = self._build_prompt(
            location, actions_str, rules_result, npc_result,
            world_result, context,
        )
            
        system_prompt = self._get_system_prompt(is_r3_direct=(npc_result.get('dm_frame') is not None))

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
                params=GenerationParams(max_tokens=settings.dm_max_tokens),
            )
            if isinstance(result, dict):
                yield result.get("dm_response", "")
            else:
                yield str(result)
            return

        # Router observability: streaming проходит ЧЕРЕЗ Router, не в обход (ADR-147)
        _router = self.router
        _stream_ctx = _router.notify_stream_start("dm_narrative", "narrative")
        _total_chars = [0]  # mutable counter для closure (thread-safe via GIL)

        q: asyncio.Queue[str | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _producer():
            buffer = ""
            tail_len = max(len(st) for st in _STOP_TOKENS)
            try:
                for token in provider.stream_tokens(
                    prompt=prompt,
                    params=GenerationParams(max_tokens=settings.dm_max_tokens),
                    system_prompt=system_prompt,
                ):
                    if not token:
                        continue
                    buffer += token
                    _total_chars[0] += len(token)

                    if _has_stop_token(buffer):
                        clean = _strip_stop_tokens(buffer)
                        if clean and not loop.is_closed():
                            asyncio.run_coroutine_threadsafe(q.put(clean), loop)
                        if not loop.is_closed():
                            asyncio.run_coroutine_threadsafe(q.put(None), loop)
                        return

                    if len(buffer) > tail_len:
                        to_send = buffer[:-tail_len]
                        buffer  = buffer[-tail_len:]
                        if to_send and not loop.is_closed():
                            asyncio.run_coroutine_threadsafe(q.put(to_send), loop)

                if buffer and not loop.is_closed():
                    clean = _strip_stop_tokens(buffer)
                    if clean:
                        asyncio.run_coroutine_threadsafe(q.put(clean), loop)

            except Exception as e:
                if not loop.is_closed():
                    asyncio.run_coroutine_threadsafe(q.put(f"\n[Ошибка стриминга: {e}]"), loop)
            finally:
                # Router observability: streaming завершён (ADR-147)
                if _stream_ctx is not None:
                    try:
                        _router.notify_stream_end(_stream_ctx, _total_chars[0])
                    except Exception:
                        pass
                if not loop.is_closed():
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

    def _fallback_narrate(self) -> Dict:
        return {
            "dm_response": MSG_NOTHING_HAPPENED,
            "npc_reactions": [],
            "world_changes": [],
        }