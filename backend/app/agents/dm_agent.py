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
                try:
                    from app.services.scene.scene_state_manager import SceneStateManager
                    _scene_block = SceneStateManager.get_scene_description(_scene_state) + "\n\n"
                except Exception:
                    pass
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
        
        # Блок 2.4: STM — последние реплики диалога (из WorkingMemory через game_loop)
        _recent_speech = (context or {}).get("npc_recent_speech", [])
        print(f"[STM_INJECT] npc_recent_speech={_recent_speech}")
        if _recent_speech:
            builder.add_npc_stm("\n".join(_recent_speech))
        
        # Блок 2.5: L2 память NPC — recalled_facts (Этап 4)
        _recalled = (context or {}).get("npc_recalled_memory", [])
        if _recalled:
            _mem_lines = []
            for _entry in _recalled:
                _npc_name = _entry.get("npc_name", "NPC")
                for _f in _entry.get("facts", []):
                    if not _f.summary:
                        continue
                    if _f.importance > 0.7:
                        _qualifier = "хорошо помнит"
                    elif _f.importance > 0.4:
                        _qualifier = "кажется, помнит"
                    else:
                        _qualifier = "смутно припоминает"
                    # Этап 8: текстуализация по игровому времени
                    _game_ts = (context or {}).get("game_time_seconds", 0)
                    if _game_ts:
                        from app.core.constants import SECONDS_PER_DAY
                        _days_ago = (_game_ts // SECONDS_PER_DAY) - _f.day
                        if _days_ago < 1:
                            _tq = "только что"
                        elif _days_ago < 7:
                            _tq = "на днях"
                        elif _days_ago < 30:
                            _tq = f"{_days_ago} дн. назад"
                        else:
                            _tq = "давно"
                        _mem_lines.append(f"- {_npc_name} {_qualifier} ({_tq}): {_f.summary}")
                    else:
                        _mem_lines.append(f"- {_npc_name} {_qualifier}: {_f.summary}")
            if _mem_lines:
                builder.add_npc_l2_memory("\n".join(_mem_lines[:5]))
        
        # Блок 2.5b: Подавленные секреты — "ты помнишь, но молчишь" (Этап 5.5)
        _suppressed = (context or {}).get("npc_suppressed_secrets", [])
        if _suppressed:
            _secret_lines = []
            for _entry in _suppressed:
                _npc_name = _entry.get("npc_name", "NPC")
                _count = _entry.get("count", 0)
                if _count > 0:
                    _secret_lines.append(f"- {_npc_name} явно что-то скрывает ({_count} тайн)")
            if _secret_lines:
                builder.add_custom_block("Скрытое", "\n".join(_secret_lines[:3]))

        # Блок 2.5c: Накопленные черты NPC — "ты осторожен с незнакомцами" (Этап 10)
        _identity = (context or {}).get("npc_identity_traits", [])
        if _identity:
            _trait_lines = []
            for _entry in _identity:
                _npc_name = _entry.get("npc_name", "NPC")
                _traits = _entry.get("traits", {})
                if _traits:
                    _desc = ", ".join(f"{k} ({v:.0%})" for k, v in _traits.items())
                    _trait_lines.append(f"- {_npc_name}: {_desc}")
            if _trait_lines:
                builder.add_custom_block("Накопленные черты", "\n".join(_trait_lines[:5]))

        # Блок 2.6: Кому обращается игрок — без этого DM не знает что NPC должен отвечать
        if context:
            # Явный таргет из текста всегда приоритетнее sticky
            _target_id = context.get("player_target_id", "")
            if _target_id:
                # Обновляем sticky только для явного таргета, не для fallback
                self._last_target_id = _target_id
                _target_name = _target_id
                # Имя берём из DMFrame (NpcOutcome.name заполняется из real_state)
                if _dm_frame:
                    for _npc in _dm_frame.focus_npcs + _dm_frame.background_npcs:
                        if _npc.npc_id == _target_id and _npc.name and _npc.npc_id != _npc.name:
                            _target_name = _npc.name
                            break
                builder.add_custom_block(
                    "Обращение игрока",
                    f"Игрок обращается напрямую к {_target_name}. Этот NPC должен отреагировать — ответить словами или действием. Остальные NPC реагируют как наблюдатели."
                )
        
        # Блок 3: Сцена — для диалога пропускаем (объекты не релевантны)
        if not _is_light_dialog:
            scene_block = ""
            if context:
                scene_state = context.get("scene_state", {})
                if scene_state:
                    try:
                        scene_block = SceneStateManager.get_scene_description(scene_state) + "\n\n"
                    except Exception as e:
                        jsonl_log({"level": "ERROR", "agent": "dm_agent", "error": f"Scene build error: {e}"})
            builder.add_scene(scene_block, location)
        
        # Блок 4: Состояние игрока — для диалога только если есть раны/состояния
        player_state_block = ""
        _skip_player_state = _is_light_dialog
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
        return "Ты — Мастер Подземелий D&D 5e. Отвечай на русском. 2-3 предложения. Не говори за игрока."

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
            params=GenerationParams(max_tokens=220),
        )

        # 1. Парсим JSON → dict (до валидации!)
        if isinstance(raw, str):
            try:
                result = json.loads(raw)
            except Exception:
                jsonl_log({"level": "WARN", "agent": "dm_agent", "error": "JSON parse failed", "raw_preview": raw[:300]})
                return self._fallback_narrate()
        else:
            result = raw if isinstance(raw, dict) else {"dm_response": str(raw)}

        # 2. Валидация — только текст dm_response, не сырой JSON
        dm_text = result.get("dm_response", "")
        from app.services.verbalization.response_validator import ResponseValidator
        validator = ResponseValidator(contract)
        validation = validator.validate(dm_text)

        if validation.is_fallback:
            jsonl_log({"level": "WARN", "agent": "dm_agent", "violation": validation.violation, "fallback_text": validation.text})
            result["dm_response"] = validation.text

        return result

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
                params=GenerationParams(max_tokens=220),
            )
            if isinstance(result, dict):
                yield result.get("dm_response", "")
            else:
                yield str(result)
            return

        q: asyncio.Queue[str | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _producer():
            buffer = ""
            tail_len = max(len(st) for st in _STOP_TOKENS)
            try:
                for token in provider.stream_tokens(
                    prompt=prompt,
                    params=GenerationParams(max_tokens=220),
                    system_prompt=system_prompt,
                ):
                    if not token:
                        continue
                    buffer += token

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

    def _build_intro_prompt(self, location: str, context: dict) -> str:
        """Промпт для вводного описания сцены в начале сессии."""
        scene_block = ""
        if context:
            scene_state = context.get("scene_state", {})
            if scene_state:
                try:
                    scene_block = SceneStateManager.get_scene_description(scene_state) + "\n\n"
                except Exception:
                    pass

        return f"""{scene_block}Текущая локация: {location}
        
Ты — Мастер игры. Начинается новая игровая сессия. Игроки только что вошли в сцену.

Напиши атмосферное вводное описание локации от второго лица ("ты видишь...", "ты чувствуешь...").
Упомяни только объекты и NPC из блока СОСТОЯНИЕ СЦЕНЫ выше.
Создай настроение — время суток, освещение, звуки, запахи.
Максимум 3-4 предложения. Без вопросов в конце.
"""

    def _fallback_narrate(self) -> Dict:
        return {
            "dm_response": MSG_NOTHING_HAPPENED,
            "npc_reactions": [],
            "world_changes": [],
        }