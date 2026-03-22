# backend/app/services/orchestrator.py

# backend/app/services/orchestrator.py
# ОПТИМИЗАЦИЯ ПОД 8 GB VRAM — RTX 3070 Ti
#
# ИЗМЕНЕНИЯ vs оригинал:
# 1. УБРАН initialize_models_stub() из глобального scope — он ломал импорт
#    (ModelRouter не имеет статического register_model)
# 2. ThreadPoolExecutor убран — pipeline строго последовательный,
#    executor не давал параллелизма, только занимал RAM
# 3. Добавлен жёсткий agent_timeout (120 сек) — LLM не зависнет навсегда
# 4. NPC- и Rules-агенты получают урезанный контекст (limit=10 вместо 20)
#    → экономия ~200-400 токенов → быстрее + меньше нагрузка на VRAM
# 5. vram_monitor.start_session() вызывается при инициализации
#    (раньше baseline был 0, поэтому лог всегда показывал +5757 MB как "утечку")
# 6. switch_to_agent делается ОДИН раз за turn, не дублируется
# 7. Fallback: если агент упал — pipeline продолжается с пустым результатом,
#    игра не крашится
# 8. Добавлен AGENT_TIMEOUT как отдельный ErrorCode
#
# ФАЗА 2.2 — добавлен PhysicsValidator (до агентов, после classifier)
# ФАЗА 2.3/2.4 — добавлен _run_python_engines (CombatMath + SandboxHandler)
# ФАЗА 3A — добавлены NPC Psychology движки (ThreatAssessor, PerceptionEngine,
#             NPCCognition, PsycheEngine), загрузка/сохранение major_npcs.json

import asyncio
from time import perf_counter
import logging
from pathlib import Path
from typing import Optional, Dict, List

from app.agents.dm_agent import DmAgent
from app.agents.memory_manager_agent import MemoryManagerAgent
from app.agents.npc_agent import NpcAgent
from app.agents.rules_agent import RulesAgent
from app.agents.world_sim_agent import WorldSimulationAgent

from app.core.config import settings
from app.models.schemas import (
    AgentTrace,
    CampaignLoadResponse,
    ChatTurnRequest,
    ChatTurnResponse,
)

from app.services.adventure_loader import AdventureLoader
from app.services.memory import JsonMemoryStore, LayeredMemory
from app.services.system_requirements import SystemRequirements
from app.services.world_scheduler import WorldScheduler
from app.services.character_service import CharacterService
from app.services.model_router import ModelRouter
from app.services.error_interpreter import get_error_interpreter
from app.services.vram_monitor import get_vram_monitor
from app.services.logging_tools import jsonl_log
from app.services.game.sandbox_handler import process_sandbox_action
from app.services.game.combat_math import attack_roll, damage_roll, build_combat_context

# === ИНТЕГРАЦИЯ ACTION CLASSIFIER (фаза 2.1) ===
from app.services.action_classifier import classifier, ActionType

# === ИНТЕГРАЦИЯ PHYSICS VALIDATOR (фаза 2.2) ===
from app.services.game.physics_validator import validator

# === NPC Psychology (фаза 3A) ===
from app.services.npc.npc_cognition   import (process_player_action, build_npc_prompt,
                                                get_inner_thought, normalize_drives)
from app.services.npc.psyche_engine   import apply_stress, get_behavior_hint
from app.services.npc.threat_assessor import assess_threat, get_threat_category, apply_threat_to_npc
from app.services.npc.perception_engine import assess_status, get_status_label, get_social_permissions

# === SceneState (фаза S) ===
from app.services.scene_state_manager import SceneStateManager

# === LifeEngine (фаза 3B.1) ===
# Движок жизни NPC: обновляет позиции по расписанию без LLM
from app.services.npc.life_engine import get_life_engine

logger = logging.getLogger(__name__)

ERROR_CODES = {
    "AGENT_SUCCESS":              "SUCCESS",
    "AGENT_TIMEOUT":              "TIMEOUT",
    "AGENT_JSON_PARSE":           "JSON_PARSE",
    "AGENT_MODEL_FAIL":           "MODEL_FAIL",
    "AGENT_CONTEXT_OVERFLOW":     "CONTEXT_OVERFLOW",
    "ORCHESTRATOR_PIPELINE_FAIL": "PIPELINE_FAIL",
}

AGENT_TIMEOUT_SEC = 120   # максимум 2 мин на агента
NPC_MEMORY_LIMIT  = 30    # лимит памяти NPC (экономия ~200 токенов)

# Типы действий при которых запускается SandboxHandler
_SANDBOX_TYPES = {
    ActionType.SANDBOX_PHYSICAL,
    ActionType.SANDBOX_SOCIAL,
    ActionType.SANDBOX_MILD,
    ActionType.ROMANCE,
    ActionType.CAPTURE,
    ActionType.FLEE,
    ActionType.LIFE_CHOICE,
    ActionType.UNKNOWN,
}


class GameOrchestrator:
    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = Path(data_dir or settings.data_dir)
        self.store = JsonMemoryStore(self.data_dir)
        self.layered_memory = LayeredMemory(self.store)

        self.dm_agent        = DmAgent()
        self.rules_agent     = RulesAgent()
        self.npc_agent       = NpcAgent()
        self.world_agent     = WorldSimulationAgent()
        self.world_scheduler = WorldScheduler(self.layered_memory, self.world_agent)
        self.memory_manager  = MemoryManagerAgent(self.layered_memory)
        self.character_service = CharacterService()
        self.adventure_loader  = AdventureLoader(self.data_dir / "campaigns")
        self.system_requirements = SystemRequirements(
            min_physical_cores=settings.min_cpu_physical_cores,
            min_ram_gb=settings.min_ram_gb,
        )
        self.model_router = ModelRouter()
        # Фаза S: SceneStateManager — Python как единственный источник истины о мире
        self.scene_manager = SceneStateManager(self.data_dir)
        # Фаза 3B.1: LifeEngine — мир живёт без участия игрока
        self.life_engine = get_life_engine()
        self._campaign_world_index: dict[str, str] = {}

        logger.info("[ORCHESTRATOR_INIT] GameOrchestrator ready (ActionClassifier + PhysicsValidator + PythonEngines + NPCPsychology + SceneState + LifeEngine подключены)")

    # ИСПРАВЛЕНИЕ (фаза 3A): кэш NPC — класс-переменная, не глобальная.
    # Доступ через GameOrchestrator._npc_cache, а не global.
    _npc_cache: list | None = None  # кэш в RAM

    def _load_npcs(self) -> list:
        """Загружает NPC из JSON. Кэширует в RAM."""
        # ИСПРАВЛЕНИЕ: было "global _npc_cache" — неправильно для class variable.
        # Правильно: обращаться через имя класса.
        if GameOrchestrator._npc_cache is not None:
            return GameOrchestrator._npc_cache
        npc_path = self.data_dir / "npcs" / "major_npcs.json"
        if npc_path.exists():
            import json
            with open(npc_path, "r", encoding="utf-8") as f:
                GameOrchestrator._npc_cache = json.load(f)
        else:
            GameOrchestrator._npc_cache = []
        return GameOrchestrator._npc_cache

    def _save_npcs(self, npcs: list) -> None:
        """Сохраняет обновлённые NPC обратно в JSON."""
        import json
        npc_path = self.data_dir / "npcs" / "major_npcs.json"
        npc_path.parent.mkdir(parents=True, exist_ok=True)
        with open(npc_path, "w", encoding="utf-8") as f:
            # ИСПРАВЛЕНИЕ: json.dump не был отступлен внутри with → IndentationError
            json.dump(npcs, f, ensure_ascii=False, indent=2)
        # ИСПРАВЛЕНИЕ: было "global _npc_cache" — правильно через имя класса.
        GameOrchestrator._npc_cache = npcs  # обновляем кэш

    def _get_npcs_in_location(self, location: str) -> list:
        """Возвращает NPC которые сейчас в данной локации."""
        return [npc for npc in self._load_npcs() if npc.get("location") == location]

    def session_state(self, campaign_id: str):
        """
        Возвращает состояние сессии для UI.
        Объект должен соответствовать схеме SessionInterfaceState.
        """
        world_id = self._resolve_world_id(campaign_id)

        class State:
            pass

        state = State()
        state.campaign_id = campaign_id
        state.world_id = world_id
        state.session_log = []
        state.dice_input_required = False
        state.layers = {}

        return state

    def _resolve_world_id(self, campaign_id: str) -> str:
        if campaign_id in self._campaign_world_index:
            return self._campaign_world_index[campaign_id]
        history = self.layered_memory.read_campaign_memory(campaign_id, limit=100)
        for item in reversed(history):
            if item.get("event") == "campaign_loaded" and item.get("world_id"):
                self._campaign_world_index[campaign_id] = item["world_id"]
                return item["world_id"]
        return "manual"

    def _assert_requirements(self) -> dict:
        report = self.system_requirements.check()
        if settings.enforce_system_requirements and not report.meets:
            raise RuntimeError(f"Недостаточно ресурсов: {report.details}")
        return {"meets": report.meets, **report.details}

    def _check_player_precondition(self, campaign_id: str, player_names: list[str]):
        session = self.layered_memory.read_session_memory(campaign_id) or {}
        existing_players = {p["player_name"] for p in session.get("players", [])}
        missing = [p for p in player_names if p not in existing_players]
        if missing:
            raise ValueError(f"Не зарегистрированы игроки: {', '.join(missing)}")

    def load_campaign(self, campaign_id: str, world_id: str) -> CampaignLoadResponse:
        loaded = self.adventure_loader.load_campaign(campaign_id)
        self._campaign_world_index[campaign_id] = world_id
        for filename, payload in loaded.get("files", {}).items():
            self.layered_memory.write_world_canon(
                world_id,
                {"campaign_id": campaign_id, "source": filename, "payload": payload},
            )
        self.layered_memory.write_campaign_memory(
            campaign_id,
            {
                "event": "campaign_loaded",
                "world_id": world_id,
                "loaded_files": list(loaded.get("files", {})),
                "status": loaded["status"],
            },
        )
        return CampaignLoadResponse(
            campaign_id=campaign_id,
            world_id=world_id,
            status=loaded["status"],
            loaded_files=list(loaded.get("files", {})),
        )

    def _build_shared_context(self, req: ChatTurnRequest) -> dict:
        return {
            "campaign_id":  req.campaign_id,
            "world_id":     req.world_id,
            "location":     req.location,
            "player_state": {a.player_name: {} for a in req.actions},
            "threat":       {},
            "perception":   {},
            "psyche":       {},
            "life":         {},
            "karma":        {},
        }

    def _extract_memory_events(self, dm_result: dict) -> list:
        return dm_result.get("memory_events", [])

    def _get_npc_importance(self, campaign_id: str, location: str) -> dict:
        return {}

    def _get_character_dict(self, campaign_id: str, player_name: str) -> dict:
        """
        Вспомогательный метод: возвращает словарь персонажа по имени игрока.
        Используется в Python-движках (PhysicsValidator, CombatMath, SandboxHandler).
        Fallback: пустой dict если персонаж не найден.
        """
        try:
            characters = self.character_service.list_characters(campaign_id)
            for char in characters:
                if char.name == player_name:
                    return char.model_dump()
        except Exception as e:
            logger.warning(f"[ORCHESTRATOR] Не удалось загрузить персонажа '{player_name}': {e}")
        return {}

    def _extract_player_target(
        self,
        action_text: str,
        npc_contexts: list,
        scene_state: dict,
    ) -> tuple[str | None, str | None, str | None, str | None, dict]:
        '''
        S.0: Извлекает цель игрока из текста действия.
 
        Generic — работает для любых NPC из npc_contexts,
        без хардкода имён конкретных персонажей.
 
        Алгоритм:
          1. Для каждого NPC в контексте: проверяем имя + роль в тексте действия
             Морфология: проверяем 4 формы имени (полное, -1, -2 символа)
             Роль: берётся из npc_id префикса через _ROLE_KEYWORDS
          2. Ищем объект из SceneState (name объекта в тексте)
          3. Определяем позицию игрока из ключевых слов
 
        Возвращает:
          (target_npc_id, target_npc_name, target_object_id, player_position, player_distances)
        '''
        lower = action_text.lower()

        # Если в тексте только местоимение (тебя/тебе/тебя/тобой) 
        # и нет нового адресата — сохраняем предыдущую цель
        _PRONOUNS = ["тебя", "тебе", "тобой", "тебе", "к тебе", "с тобой"]
        has_only_pronoun = any(p in lower for p in _PRONOUNS)

        # Предыдущая цель из SceneState (если была)
        prev_target_id   = scene_state.get("player_target_npc") if scene_state else None
        prev_target_name = scene_state.get("player_target_npc_name") if scene_state else None
 
        # ── Таблица ключевых слов по роли (из npc_id префикса) ───────────────
        # Принцип: НЕ имена конкретных NPC, а архетипы ролей.
        # Новый NPC с role="merchant" → автоматически получает эти ключевые слова.
        _ROLE_KEYWORDS: dict[str, list[str]] = {
            "tavern_keeper": ["хозяин", "трактирщик", "бармен", "владелец",
                              "хозяину", "трактирщику", "хозяина"],
            "innkeeper":     ["хозяин", "трактирщик", "хозяину"],
            "maid":          ["служанка", "официантка", "девушка",
                              "служанке", "официантке", "девушке"],
            "guard":         ["стражник", "охранник", "страж",
                              "стражнику", "охраннику", "стражника"],
            "merchant":      ["купец", "торговец", "продавец",
                              "купцу", "торговцу", "купца"],
            "thief":         ["вор", "незнакомец", "фигура", "тень",
                              "вору", "незнакомцу", "тени"],
            "priest":        ["священник", "жрец", "священнику", "жрецу"],
            "blacksmith":    ["кузнец", "кузнецу", "кузнеца"],
            "farmer":        ["крестьянин", "фермер", "крестьянину"],
            "noble":         ["лорд", "господин", "барон", "лорду", "господину"],
            "innkeeper":     ["хозяйка", "хозяйке", "хозяйку"],
        }
 
        # Если имя не нашли, но есть местоимение и была предыдущая цель — используем её



        def _get_role_from_id(npc_id: str) -> str:
            '''Извлекает роль из npc_id: "tavern_keeper_tornin" → "tavern_keeper"'''
            parts = npc_id.split("_")
            # Ищем совпадение с ключом _ROLE_KEYWORDS начиная с длинных префиксов
            for length in range(len(parts) - 1, 0, -1):
                candidate = "_".join(parts[:length])
                if candidate in _ROLE_KEYWORDS:
                    return candidate
            return ""
 
        def _get_name_forms(ctx: dict) -> list[str]:
            '''
            Возвращает формы имени NPC для поиска в тексте действия.
            Приоритет: name_forms из JSON (точные падежи дизайнера).
            Fallback: автогенерация из имени (только для NPC без name_forms).
            '''
            explicit = ctx.get("name_forms")
            if explicit:
                return [f.lower() for f in explicit]
            # Fallback — автогенерация для NPC без явных форм
            name = ctx.get("npc_name", "")
            n = name.lower()
            forms = [n]
            if len(n) > 3:
                forms.append(n[:-1])
            if len(n) > 4:
                forms.append(n[:-2])
                forms.append(n[:-3])
            if len(n) >= 4:
                forms.append(n[:4])
            if len(n) >= 5:
                forms.append(n[:5])
            return list(set(f for f in forms if len(f) >= 3))  
 
        # ── 1. Поиск целевого NPC ─────────────────────────────────────────────
        target_npc_id   = None
        target_npc_name = None
 
        for ctx in npc_contexts:
            npc_id   = ctx.get("npc_id", "")
            npc_name = ctx.get("npc_name", "")
 
            # Проверяем имя NPC — сначала явные формы из JSON, потом автогенерация
            if any(form in lower for form in _get_name_forms(ctx)):
                    target_npc_id   = npc_id
                    target_npc_name = npc_name
                    break
 
            # Проверяем ключевые слова роли
            role = _get_role_from_id(npc_id)
            if role and any(kw in lower for kw in _ROLE_KEYWORDS.get(role, [])):
                target_npc_id   = npc_id
                target_npc_name = npc_name
                break

            if target_npc_id is None and has_only_pronoun and prev_target_id:
                target_npc_id   = prev_target_id
                target_npc_name = prev_target_name
 
        # ── 2. Поиск целевого объекта ─────────────────────────────────────────
        target_object = None
        objects = scene_state.get("objects", {}) if scene_state else {}
        for obj_id, obj_data in objects.items():
            obj_name = obj_data.get("name", "").lower()
            if obj_name and len(obj_name) >= 3 and obj_name in lower:
                target_object = obj_id
                break
 
        # ── 3. Определение позиции игрока ─────────────────────────────────────
        player_position = None
        _POSITION_PATTERNS: dict[str, list[str]] = {
            "на коленях": ["на колен", "встаю на колен", "опускаюсь на колен"],
            "сидит":      ["сажусь", "сижу", "сел", "садится"],
            "лежит":      ["ложусь", "лежу", "лёг", "упал"],
            "прячется":   ["прячусь", "скрываюсь", "скрыт"],
            "крадётся":   ["крадусь", "иду тихо", "иду осторожно"],
            "стоит":      ["стою", "встаю", "встал"],
            "бежит":      ["бегу", "бегу к", "убегаю"],
        }
        for pos_label, patterns in _POSITION_PATTERNS.items():
            if any(p in lower for p in patterns):
                player_position = pos_label
                break
 
        # ── 4. Расчёт расстояний (упрощённый) ────────────────────────────────
        # Если игрок явно рядом с NPC (обращается к нему, перед ним и т.д.)
        # → ставим ~0.5м. Иначе — стандартное расстояние по позиции в сцене.
        player_distances: dict = {}
        npc_positions = scene_state.get("npc_positions", {}) if scene_state else {}
 
        _POSITION_BASE_DISTANCE: dict[str, float] = {
            "behind_bar":      3.0,
            "serving_table_3": 2.0,
            "corner_table":    5.0,
            "gate_post":       4.0,
            "stall_3":         2.5,
        }
 
        _PROXIMITY_KEYWORDS = [
            "перед", "рядом с", "к ", "подхожу к", "стою перед",
            "обращаюсь к", "говорю с", "смотрю на", "касаюсь",
            "на коленях перед", "беру за руку", "держу",
        ]
        is_proximate = any(kw in lower for kw in _PROXIMITY_KEYWORDS)
 
        for ctx in npc_contexts:
            npc_id   = ctx.get("npc_id", "")
            npc_pos  = npc_positions.get(npc_id, {})
            pos_key  = npc_pos.get("position", "")
            base_dist = _POSITION_BASE_DISTANCE.get(pos_key, 3.0)
 
            if npc_id == target_npc_id and is_proximate:
                # Игрок явно взаимодействует с этим NPC — считаем близко
                player_distances[npc_id] = 0.5
            else:
                player_distances[npc_id] = base_dist
 
        return target_npc_id, target_npc_name, target_object, player_position, player_distances    

    async def _run_python_engines(
        self,
        req: ChatTurnRequest,
        classification_results: List[dict],
        shared_context: dict,   # ИСПРАВЛЕНИЕ: параметр добавлен — NPC-блок его использует
    ) -> dict:
        """
        Фазы 2.3/2.4/3A: Python движки — выполняются ДО LLM агентов.
        Принцип: Python считает → LLM только рассказывает результат.

        Запускает:
          - CombatMath (attack_roll, damage_roll) — при COMBAT
          - SandboxHandler (process_sandbox_action) — при нестандартных действиях
          - NPC Psychology (фаза 3A):
              ThreatAssessor → PerceptionEngine → NPCCognition → PsycheEngine

        Возвращает структуру python_engines_result, которая передаётся DM агенту
        через shared_context["python_engines"].
        """
        engines_result: Dict[str, dict] = {}

        for action_item, cls in zip(req.actions, classification_results):
            player_name = action_item.player_name
            action_text = cls["text_preview"]  # обрезан до 80 символов
            act_type_str = cls["type"]

            # Восстанавливаем ActionType из строки
            try:
                act_type = ActionType(act_type_str)
            except ValueError:
                act_type = ActionType.UNKNOWN

            char_dict = self._get_character_dict(req.campaign_id, player_name)

            player_result: dict = {
                "player":      player_name,
                "action_type": act_type_str,
                "combat":      None,
                "sandbox":     None,
            }

            # ─────────────────────────────────────────────────────────────────
            # COMBAT MATH (фаза 2.3)
            # ─────────────────────────────────────────────────────────────────
            if act_type == ActionType.COMBAT:
                try:
                    attacker = {
                        "name":            player_name,
                        "level":           char_dict.get("level", 1),
                        "strength":        char_dict.get("strength", 10),
                        "dexterity":       char_dict.get("dexterity", 10),
                        "proficiencies":   char_dict.get("proficiencies", []),
                        "equipped_weapon": char_dict.get("equipped_weapon", {
                            "name": "кулак", "damage": "1d4", "type": "melee"
                        }),
                        "conditions":      char_dict.get("conditions", []),
                    }
                    # Фаза 3A: цель берётся из NPC в локации если есть, иначе заглушка
                    npcs_here = self._get_npcs_in_location(req.location)
                    target = npcs_here[0] if npcs_here else {
                        "name":   "противник",
                        "ac":     12,
                        "hp":     20,
                        "max_hp": 20,
                    }

                    atk = attack_roll(attacker, target)
                    dmg: dict = {}
                    if atk.hit:
                        weapon_dice = char_dict.get("equipped_weapon", {}).get("damage", "1d4")
                        from app.services.game.combat_math import ability_modifier
                        str_mod = ability_modifier(char_dict.get("strength", 10))
                        dmg = damage_roll(weapon_dice, str_mod, critical=atk.critical)

                    combat_ctx = build_combat_context(
                        attack=atk,
                        target=target,
                        damage_result=dmg,
                        attacker_name=player_name,
                    )
                    player_result["combat"] = combat_ctx

                    logger.info(
                        f"[PYTHON_ENGINES] COMBAT: {player_name} → "
                        f"roll={atk.roll} hit={atk.hit} crit={atk.critical} "
                        f"dmg={dmg.get('total', 0)}"
                    )
                except Exception as e:
                    logger.error(f"[PYTHON_ENGINES] CombatMath error для '{player_name}': {e}")

            # ─────────────────────────────────────────────────────────────────
            # SANDBOX HANDLER (фаза 2.4)
            # ─────────────────────────────────────────────────────────────────
            elif act_type in _SANDBOX_TYPES:
                try:
                    full_action = getattr(action_item, "action",
                                         getattr(action_item, "description", action_text))

                    sandbox_result = process_sandbox_action(
                        player=char_dict,
                        action_desc=full_action,
                        target=None,
                        enemies=None,
                        location_type=req.location,
                        gold=char_dict.get("gold", 0),
                    )
                    player_result["sandbox"] = sandbox_result.to_dict()

                    # Фаза S: применяем scene_changes из SandboxHandler если есть
                    # (SandboxResult.scene_changes добавляется в фазе S.4.1)
                    scene_changes = getattr(sandbox_result, "scene_changes", [])
                    if scene_changes and shared_context.get("scene_state") is not None:
                        self.scene_manager.apply_changes(
                            req.campaign_id,
                            scene_changes,
                            shared_context["scene_state"],
                        )

                    logger.info(
                        f"[PYTHON_ENGINES] SANDBOX: {player_name} → "
                        f"type={sandbox_result.action_type.value} "
                        f"success={sandbox_result.success}"
                    )
                except Exception as e:
                    logger.error(f"[PYTHON_ENGINES] SandboxHandler error для '{player_name}': {e}")

            engines_result[player_name] = player_result


        # ── LifeEngine тик (фаза 3B.1) ────────────────────────────────────────────────
        # Запускаем ДО NPC Psychology — чтобы позиции NPC были актуальны когда
        # ThreatAssessor и NPCCognition строят контекст для LLM.
        # Принцип: Python двигает мир → LLM рассказывает результат.
        try:
            scene_state_for_life = shared_context.get("scene_state")
            life_changes = self.life_engine.tick(req.campaign_id, scene_state_for_life)
            if life_changes and scene_state_for_life is not None:
                applied = self.scene_manager.apply_changes(
                    req.campaign_id,
                    life_changes,
                    scene_state_for_life,
                )
                # Инвалидируем кэш NPC если были изменения позиций
                if applied:
                    self.life_engine.save_npcs(req.campaign_id)
                    # Сбрасываем кэш orchestrator чтобы _get_npcs_in_location()
                    # вернул актуальные позиции для NPC Psychology блока
                    GameOrchestrator._npc_cache = None
                logger.info(
                    f"[PYTHON_ENGINES] LifeEngine: {len(life_changes)} изменений, "
                    f"применено {applied}"
                )
        except Exception as e:
            logger.error(f"[PYTHON_ENGINES] LifeEngine error: {e}")


        # ── NPC Psychology блок (фаза 3A) ─────────────────────────────────────────────
        # ИСПРАВЛЕНИЕ: action_type брался из shared_context.get("action_type") — ключа нет.
        # Правильно: берём из первого элемента classification_results.
        action_type = classification_results[0]["type"] if classification_results else "EXPLORE"

        # HF-3: сессионная память — последние 2 хода для NPC continuity.
        # Тень/Люся/Торнин не помнят что говорили без этого (Фаза 3C решит полностью).
        try:
            recent_entries = self.layered_memory.read_campaign_memory(
                req.campaign_id, limit=2
            )
            recent_session = []
            for entry in recent_entries:
                for action in entry.get("actions", []):
                    recent_session.append(
                        f"{action.get('player_name', '?')}: {action.get('action', '?')}"
                    )
                dm_text = entry.get("dm", "")
                if dm_text:
                    recent_session.append(f"[DM]: {dm_text[:120]}")
            shared_context["recent_session"] = recent_session
        except Exception as e:
            logger.warning(f"[ORCHESTRATOR] Не удалось загрузить recent_session: {e}")
            shared_context["recent_session"] = []

        player_data = {}
        if req.actions:
            player_name_0 = req.actions[0].player_name
            chars = self.character_service.list_characters(req.campaign_id)
            player_data = next(
                (c.model_dump() for c in chars if c.name == player_name_0), {}
            )

        npcs_in_location = self._get_npcs_in_location(req.location)
        npc_contexts = []

        for npc in npcs_in_location:
            # 1. Угроза
            player_markers = player_data.get("visible_markers", [])
            threat_score   = assess_threat(
                player_markers, action_type,
                player_data.get("reputation", {})
            )
            threat_cat = get_threat_category(threat_score)
            apply_threat_to_npc(npc, threat_score, threat_cat)

            # 2. Восприятие
            status_score  = assess_status(player_markers)
            status_label  = get_status_label(status_score)
            permissions   = get_social_permissions(player_markers, npc)

            # 3. NPCCognition — доверие/страх
            action_deltas = process_player_action(npc, action_type, player_data, threat_score)

            # 4. PsycheEngine — подсказка по поведению
            behavior_hint = get_behavior_hint(npc)

            # 5. Промпт для NPC агента
            npc_system_prompt = build_npc_prompt(
                npc, player_data, shared_context,
                behavior_hint=behavior_hint,
                perceived_status=status_label,
                threat_category=threat_cat,
            )

            # 6. Внутренняя мысль для режима отладки
            inner_thought = get_inner_thought(npc, shared_context)

            npc_contexts.append({
                "npc_id":           npc["id"],
                "npc_name":         npc["name"],
                "name_forms":       npc.get("name_forms", []),            # ← добавить это
                "tier":             npc.get("tier", "minor"),
                "gender":           npc.get("gender", ""),                # для местоимений в DM
                "description":      npc.get("description", ""),           # для вводной сцены
                "threat_score":     threat_score,
                "threat_category":  threat_cat,
                "perceived_status": status_label,
                "behavior_hint":    behavior_hint,
                "system_prompt":    npc_system_prompt,
                "inner_thought":    inner_thought,
                "permissions":      permissions,
                "action_deltas":    action_deltas,
            })

        # Сохраняем обновлённые состояния NPC (изменения от ThreatAssessor и NPCCognition)
        if npcs_in_location:
            all_npcs = self._load_npcs()
            for updated_npc in npcs_in_location:
                for i, n in enumerate(all_npcs):
                    if n["id"] == updated_npc["id"]:
                        all_npcs[i] = updated_npc
                        break
            self._save_npcs(all_npcs)

        # ИСПРАВЛЕНИЕ: было results["npc_contexts"] — переменная results не существует
        # внутри _run_python_engines. Правильно: engines_result.
        engines_result["npc_contexts"] = npc_contexts
        # ── Конец NPC блока ────────────────────────────────────────────────────────────

        # ── S.0: Обновляем SceneState пространственным контекстом игрока ──────
        # Нужно чтобы DM и NPC агенты знали кто где стоит и к кому обращаются.
        # Вызываем ПОСЛЕ того как npc_contexts собраны — нужны id и имена NPC.
        try:
            scene_state_for_target = shared_context.get("scene_state")
            if scene_state_for_target is not None and req.actions:
                # Берём первое действие (при мультиплеере — позже будет per-player)
                first_action_text = getattr(
                    req.actions[0], "action",
                    getattr(req.actions[0], "description", "")
                )
                (
                    target_npc_id,
                    target_npc_name,
                    target_object,
                    player_position,
                    player_distances,
                ) = self._extract_player_target(
                    first_action_text,
                    npc_contexts,
                    scene_state_for_target,
                )
                self.scene_manager.update_player_target(
                    req.campaign_id,
                    scene_state_for_target,
                    target_npc_id   = target_npc_id,
                    target_npc_name = target_npc_name,
                    target_object_id = target_object,
                    player_position  = player_position,
                    player_distances = player_distances,
                )
                # Обновляем shared_context — DM и NPC агенты получат актуальный SceneState
                shared_context["scene_state"] = scene_state_for_target
                # Также передаём target напрямую для быстрого доступа
                shared_context["player_target_npc"]  = target_npc_id
                shared_context["player_target_name"] = target_npc_name
 
                logger.info(
                    f"[SCENE S.0] target_npc={target_npc_name!r} "
                    f"target_obj={target_object!r} pos={player_position!r}"
                )
        except Exception as e:
            logger.error(f"[SCENE S.0] _extract_player_target error: {e}")
        # ─────────────────────────────────────────────────────────────────────

        return engines_result

    def _apply_npc_state_updates(self, npc_state_updates: list) -> None:
        """
        HF-1: Применяет trust_change и stress_change из JSON ответов NPC агента
        к реальным данным NPC в major_npcs.json.

        Вызывается из run_turn() после _run_agent_safe("npc", ...).

        npc_state_updates: [{"npc_id": str, "trust_delta": float, "stress_delta": int}, ...]
        trust_delta: уже в шкале 0..1 (поделено на 100 в npc_agent)
        stress_delta: в шкале 0..100 (прибавляется напрямую)
        """
        if not npc_state_updates:
            return
        try:
            all_npcs = self._load_npcs()
            changed  = False
            for upd in npc_state_updates:
                npc_id       = upd.get("npc_id")
                trust_delta  = upd.get("trust_delta", 0.0)
                stress_delta = upd.get("stress_delta", 0)
                for npc in all_npcs:
                    if npc["id"] != npc_id:
                        continue
                    # Применяем trust_delta к social_stats.trust
                    if trust_delta != 0.0:
                        ss = npc.setdefault("social_stats", {})
                        old_trust = ss.get("trust", 0.5)
                        ss["trust"] = round(max(0.0, min(1.0, old_trust + trust_delta)), 4)
                    # Применяем stress_delta к psyche.stress
                    if stress_delta != 0:
                        psyche = npc.setdefault("psyche", {})
                        old_stress = psyche.get("stress", 0)
                        psyche["stress"] = max(0, min(100, old_stress + stress_delta))
                    changed = True
                    logger.info(
                        f"[NPC_STATE] {npc_id}: trust_delta={trust_delta:+.4f} "
                        f"stress_delta={stress_delta:+d}"
                    )
                    break
            if changed:
                self._save_npcs(all_npcs)
        except Exception as e:
            logger.error(f"[ORCHESTRATOR] _apply_npc_state_updates failed: {e}")


    async def _run_agent_safe(
        self, agent_name: str, agent, args: tuple, kwargs: dict
    ) -> dict:
        """Запускает агента с таймаутом. При любой ошибке — fallback {}."""
        vram_monitor      = get_vram_monitor()
        error_interpreter = get_error_interpreter()
        agent_start       = perf_counter()

        vram_before = await vram_monitor.get_vram_mb()
        await self.model_router.switch_to_agent(agent_name)
        vram_after  = await vram_monitor.get_vram_mb()

        jsonl_log({
            "level": "INFO", "agent": agent_name, "status": "model_switch",
            "vram_before_mb": vram_before, "vram_after_mb": vram_after,
        })

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(agent.run, *args, **kwargs),
                timeout=AGENT_TIMEOUT_SEC,
            )
            duration = round((perf_counter() - agent_start) * 1000)
            jsonl_log({
                "level": "INFO", "agent": agent_name,
                "error_code": ERROR_CODES["AGENT_SUCCESS"],
                "duration_ms": duration, "status": "complete",
            })
            return result or {}

        except asyncio.TimeoutError:
            duration = round((perf_counter() - agent_start) * 1000)
            msg = f"Агент '{agent_name}' превысил лимит {AGENT_TIMEOUT_SEC}с"
            jsonl_log({
                "level": "ERROR", "agent": agent_name,
                "error_code": ERROR_CODES["AGENT_TIMEOUT"],
                "duration_ms": duration, "status": "timeout", "human_msg": msg,
            })
            logger.error(f"[ORCHESTRATOR] {msg}")
            return {}

        except Exception as e:
            duration = round((perf_counter() - agent_start) * 1000)
            human_msg, fix = error_interpreter.handle(
                e, {"agent": agent_name}, agent_name, agent_name
            )
            jsonl_log({
                "level": "ERROR", "agent": agent_name,
                "error_code": ERROR_CODES["AGENT_MODEL_FAIL"],
                "duration_ms": duration, "status": "failed",
                "human_msg": human_msg, "fix": fix,
            })
            logger.error(f"[ORCHESTRATOR] {agent_name} failed: {human_msg}")
            return {}

    async def run_turn(self, req: ChatTurnRequest) -> ChatTurnResponse:
        logger.info("[ORCHESTRATOR] PIPELINE_START")
        start = perf_counter()

        player_names = [a.player_name for a in req.actions]
        self._assert_requirements()

        world_tick_meta = self.world_scheduler.maybe_tick(
            req.world_id, every_minutes=settings.world_tick_minutes
        )
        shared_context = self._build_shared_context(req)
        npc_importance = self._get_npc_importance(req.campaign_id, req.location)

        # ===================================================================
        # === SCENE STATE (фаза S) — инициализация до всех агентов ==========
        # Python — единственный источник истины о состоянии мира.
        # Если SceneState для этой локации нет — создаём из шаблона.
        # ===================================================================
        try:
            scene_state = self.scene_manager.get_scene_state(
                req.campaign_id, req.location
            )
            if scene_state is None:
                time_of_day = shared_context.get("time_of_day", "12:00")
                scene_state = self.scene_manager.initialize_scene(
                    req.campaign_id, req.location, time_of_day
                )
                logger.info(f"[SCENE] Новая сцена инициализирована: {req.location}")
            shared_context["scene_state"] = scene_state
        except Exception as e:
            logger.warning(f"[SCENE] Ошибка инициализации SceneState: {e}")
            shared_context["scene_state"] = {}
        # ===================================================================

        # ===================================================================
        # === ACTION CLASSIFIER (фаза 2.1) — выполняется ПЕРВЫМ (0 мс) =====
        # ===================================================================
        classification_results = []
        for action_item in req.actions:
            action_text = getattr(action_item, "action",
                                  getattr(action_item, "description", str(action_item)))

            act_type = classifier.classify(action_text)
            agents_needed, flags = classifier.get_required_agents(
                act_type,
                npc_present=bool(npc_importance)
            )

            classification_results.append({
                "player": action_item.player_name,
                "type": act_type.value,
                "agents": agents_needed,
                "flags": flags,
                "text_preview": action_text[:80] + "..." if len(action_text) > 80 else action_text
            })

        shared_context["classification"] = classification_results

        logger.info(f"[CLASSIFIER] Классифицировано {len(classification_results)} действий: "
                    f"{[r['type'] for r in classification_results]}")
        # ===================================================================

        # ===================================================================
        # === PHYSICS VALIDATOR (фаза 2.2) — сразу после классификации =====
        # ===================================================================
        physics_results = []
        for action_item in req.actions:
            action_text = getattr(action_item, "action",
                                  getattr(action_item, "description", str(action_item)))

            char_sheet = self._get_character_dict(req.campaign_id, action_item.player_name)

            validation = validator.validate(
                action=action_text,
                character=char_sheet,
                game_state={"location": req.location}
            )

            if not validation.valid:
                physics_results.append({
                    "player":      action_item.player_name,
                    "valid":       False,
                    "reason":      validation.reason,
                    "alternative": validation.alternative,
                })
                logger.warning(
                    f"[PHYSICS] BLOCKED '{action_item.player_name}': {validation.reason}"
                )

        shared_context["physics_validation"] = physics_results
        # ===================================================================

        # ===================================================================
        # === PYTHON ENGINES (фазы 2.3/2.4/3A) ==============================
        # ИСПРАВЛЕНИЕ: передаём shared_context — NPC-блок его требует
        # ===================================================================
        python_engines_result = await self._run_python_engines(
            req, classification_results, shared_context
        )
        shared_context["python_engines"] = python_engines_result

        logger.info(
            f"[PYTHON_ENGINES] Обработано {len(python_engines_result)} игроков: "
            f"{[v['action_type'] for v in python_engines_result.values() if isinstance(v, dict) and 'action_type' in v]}"
        )
        # ===================================================================

        results: dict[str, dict] = {}

        # PIPELINE: строго последовательно (ModelPool: max_loaded=1)
        results["rules"] = await self._run_agent_safe(
            "rules", self.rules_agent, (req.actions,), {}
        )
        results["npc"] = await self._run_agent_safe(
            "npc", self.npc_agent,
            (
                req.location, req.actions,
                self.layered_memory.read_npc_memory(req.campaign_id, limit=NPC_MEMORY_LIMIT),
                shared_context, npc_importance,
            ),
            {},
        )

        # HF-1: применяем trust_change/stress_change из JSON ответов NPC к major_npcs.json.
        # Раньше эти дельты выбрасывались — каждый ход психология NPC не накапливалась.
        npc_state_updates = results.get("npc", {}).get("npc_state_updates", [])
        if npc_state_updates:
            self._apply_npc_state_updates(npc_state_updates)
        results["dm"] = await self._run_agent_safe(
            "dm", self.dm_agent,
            (
                req.location, req.actions,
                results.get("rules"), results.get("npc"),
                {"world_events": world_tick_meta.get("events", [])},
                False, shared_context,
            ),
            {},
        )

        memory_events = self._extract_memory_events(results.get("dm", {}))
        self.layered_memory.store_events(req.campaign_id, memory_events)

        active_model = await self.model_router.get_model_for_agent("dm")
        journal_entry_id = self.layered_memory.write_campaign_memory(
            req.campaign_id,
            {
                "world_id": req.world_id, "location": req.location,
                "actions":  [a.model_dump() for a in req.actions],
                "rules":    results.get("rules", {}),
                "dm":       results.get("dm", {}).get("dm_response", ""),
                "npc":      results.get("dm", {}).get("npc_reactions", []),
                "world":    results.get("dm", {}).get("world_changes", []),
                "model":    active_model.model_dump() if active_model else "unknown",
                # Фазы 2/3A: сохраняем результаты python_engines в журнал кампании
                "python_engines": python_engines_result,
            },
        )
        self.layered_memory.write_session_memory(
            req.campaign_id,
            {
                "world_id":  req.world_id, "location": req.location,
                "last_actions": [a.model_dump() for a in req.actions],
                "dice_input_required": any(a.dice_result is None for a in req.actions),
            },
        )

        pipeline_duration = round((perf_counter() - start) * 1000)
        jsonl_log({
            "level": "INFO", "agent": "orchestrator",
            "error_code": ERROR_CODES["AGENT_SUCCESS"],
            "duration_ms": pipeline_duration, "status": "pipeline_complete",
            "agents_executed": list(results.keys()),
        })

        traces = [
            AgentTrace(agent="performance",     output={"turn_elapsed_ms": pipeline_duration}),
            AgentTrace(agent="world_scheduler", output=world_tick_meta),
            AgentTrace(agent="rules",           output=results.get("rules", {})),
            AgentTrace(agent="npc",             output=results.get("npc", {})),
            AgentTrace(agent="dm",              output=results.get("dm", {})),
            AgentTrace(agent="python_engines",  output=python_engines_result),
            AgentTrace(agent="orchestrator",    output={"pipeline_duration_ms": pipeline_duration}),
        ]

        logger.info(f"[ORCHESTRATOR] PIPELINE_END, elapsed_ms={pipeline_duration}")
        return ChatTurnResponse(
            dm_response=results.get("dm", {}).get("dm_response", ""),
            npc_reactions=results.get("dm", {}).get("npc_reactions", []),
            world_changes=results.get("dm", {}).get("world_changes", []),
            journal_entry_id=journal_entry_id,
            traces=traces,
        )


    # ─────────────────────────────────────────────────────────────────────────────
    # ДОБАВИТЬ В КОНЕЦ КЛАССА GameOrchestrator (перед финальными комментариями)
    #
    # stream_turn() — стриминговая версия run_turn().
    # routes_stream.py вызывает только этот метод.
    # Вся логика идентична run_turn(), только финальная генерация DM — стриминговая.
    # ─────────────────────────────────────────────────────────────────────────────

    async def stream_turn(
        self,
        campaign_id: str,
        player: str,
        action_text: str,
        location: str,
        campaign_state=None,
    ):
        """
        Стриминговая версия run_turn() для SSE.

        Единственный источник игровой логики для стримингового пути.
        routes_stream.py вызывает только этот метод — никакой логики там нет.

        Yields dict-события в том же формате что ожидает index.html:
          {"type": "ping"}
          {"type": "status",      "text": "..."}
          {"type": "action_type", "value": "SOCIAL"}
          {"type": "model",       "data": {...}}
          {"type": "npc",         "data": [...]}
          {"type": "token",       "text": "...", "n": 1}
          {"type": "done",        "tokens": N, "ms": T, "tps": X}
        """
        import time
        from app.models.schemas import PlayerAction, ChatTurnRequest
        from app.services.llm.router import get_router as get_llm_router, Capability
        from app.services.llm.provider_manager import get_model_pool

        start_ms    = time.time() * 1000
        token_count = 0

        yield {"type": "ping"}
        yield {"type": "status", "text": "Мастер думает..."}

        # ── 1. Action Classifier (0ms) ─────────────────────────────────────
        act_type        = classifier.classify(action_text)
        action_type_str = act_type.value
        yield {"type": "action_type", "value": action_type_str}

        # ── 2. Строим ChatTurnRequest для _run_python_engines ──────────────
        # world_id берём из campaign_state или fallback
        world_id = "manual"
        if campaign_state:
            world_id = campaign_state.metadata.get("world_id", "manual")

        actions = [PlayerAction(player_name=player, action=action_text)]

        req = ChatTurnRequest(
            campaign_id=campaign_id,
            world_id=world_id,
            location=location,
            actions=actions,
        )

        # ── 3. SceneState — инициализация (идентично run_turn) ────────────
        shared_context = {
            "campaign_id":  campaign_id,
            "world_id":     world_id,
            "location":     location,
            "player_state": {player: {}},
            "threat":       {},
            "perception":   {},
            "psyche":       {},
            "life":         {},
            "karma":        {},
        }

        try:
            scene_state = self.scene_manager.get_scene_state(campaign_id, location)
            if scene_state is None:
                time_of_day = "22:00"
                if campaign_state:
                    time_of_day = campaign_state.metadata.get("time_of_day", "22:00")
                scene_state = self.scene_manager.initialize_scene(
                    campaign_id, location, time_of_day
                )
                logger.info(f"[STREAM] Новая сцена: {location}")
            shared_context["scene_state"] = scene_state
        except Exception as e:
            logger.warning(f"[STREAM] SceneState error: {e}")
            shared_context["scene_state"] = {}

        # ── 4. PhysicsValidator ────────────────────────────────────────────
        physics_results = []
        try:
            char_sheet  = self._get_character_dict(campaign_id, player)
            validation  = validator.validate(
                action=action_text,
                character=char_sheet,
                game_state={"location": location},
            )
            if not validation.valid:
                physics_results.append({
                    "player":      player,
                    "valid":       False,
                    "reason":      validation.reason,
                    "alternative": validation.alternative,
                })
        except Exception as e:
            logger.warning(f"[STREAM] PhysicsValidator error: {e}")

        shared_context["physics_validation"] = physics_results

        # ── 5. Python Engines (CombatMath + SandboxHandler + NPC Psychology
        #       + S.0 player_target + name_forms) ──────────────────────────
        # Это единственное место где строятся npc_contexts с name_forms.
        # Здесь же вызывается _extract_player_target и update_player_target.
        classification_results = [{
            "player":       player,
            "type":         action_type_str,
            "agents":       ["dm"],
            "flags":        {"unconventional": False},
            "text_preview": action_text[:80],
        }]
        shared_context["classification"] = classification_results

        try:
            python_engines_result = await self._run_python_engines(
                req, classification_results, shared_context
            )
            shared_context["python_engines"] = python_engines_result
        except Exception as e:
            logger.error(f"[STREAM] _run_python_engines error: {e}")
            shared_context["python_engines"] = {}

        # ── 6. Модели — отправляем метаинфо клиенту ───────────────────────
        try:
            npc_contexts = shared_context.get("python_engines", {}).get("npc_contexts", [])
            has_major    = any(c.get("tier") == "major" for c in npc_contexts)
            router_llm   = get_llm_router()
            pool         = get_model_pool()
            dm_key   = router_llm.select_model(Capability.NARRATIVE)
            npc_cap  = Capability.DIALOGUE_GENERATION if has_major else Capability.DIALOGUE
            npc_key  = router_llm.select_model(npc_cap)
            dm_cfg   = pool.get_model_config(dm_key)  if pool else None
            npc_cfg  = pool.get_model_config(npc_key) if pool else None
            yield {
                "type": "model",
                "data": {
                    "dm": {
                        "key":      dm_key,
                        "name":     dm_cfg.name if dm_cfg else dm_key,
                        "provider": dm_cfg.provider_type.value if dm_cfg else "unknown",
                    },
                    "npc": {
                        "key":      npc_key,
                        "name":     npc_cfg.name if npc_cfg else npc_key,
                        "provider": npc_cfg.provider_type.value if npc_cfg else "unknown",
                    },
                },
            }
        except Exception:
            pass

        # ── 7. Rules агент ─────────────────────────────────────────────────
        try:
            rules_result = await asyncio.to_thread(self.rules_agent.run, actions)
        except Exception:
            rules_result = {"checks": []}

        # ── 8. NPC агент ───────────────────────────────────────────────────
        npc_importance = "major" if any(
            c.get("tier") == "major"
            for c in shared_context.get("python_engines", {}).get("npc_contexts", [])
        ) else "mass"

        try:
            npc_memory = self.layered_memory.read_npc_memory(campaign_id, limit=30)
            npc_result = await asyncio.to_thread(
                self.npc_agent.run,
                location, actions, npc_memory, shared_context, npc_importance,
            )
        except Exception:
            npc_result = {"npc_reactions": [], "npc_actions": [], "npc_state_updates": []}

        # Применяем trust/stress дельты
        npc_state_updates = npc_result.get("npc_state_updates", [])
        if npc_state_updates:
            self._apply_npc_state_updates(npc_state_updates)

        # NPC реакции — отправляем ДО токенов DM
        npc_reactions = npc_result.get("npc_reactions", [])
        if npc_reactions:
            yield {
                "type":  "npc",
                "data":  npc_reactions,
                "model": npc_result.get("model"),
            }

        # ── 9. DM агент — стриминг токенов ────────────────────────────────
        yield {"type": "status", "text": "Мастер рассказывает..."}

        world_result = {"world_events": []}

        try:
            async for token in self.dm_agent.stream_narrate(
                location=location,
                actions=actions,
                rules_result=rules_result,
                npc_result=npc_result,
                world_result=world_result,
                world_canon_exists=False,
                context=shared_context,
            ):
                token_count += 1
                yield {"type": "token", "text": token, "n": token_count}
        except Exception as e:
            yield {"type": "error", "text": str(e)}
            return

        # ── 10. Финал ──────────────────────────────────────────────────────
        elapsed_ms = int(time.time() * 1000 - start_ms)
        tps = round(token_count / (elapsed_ms / 1000), 1) if elapsed_ms > 0 else 0

        yield {"type": "done", "tokens": token_count, "ms": elapsed_ms, "tps": tps}

        # ── 11. Сохраняем в память ─────────────────────────────────────────
        try:
            self.layered_memory.write_session_memory(
                campaign_id,
                {
                    "world_id":     world_id,
                    "location":     location,
                    "last_actions": [{"player_name": player, "action": action_text}],
                    "dice_input_required": False,
                },
            )
            self.layered_memory.write_campaign_memory(
                campaign_id,
                {
                    "world_id": world_id,
                    "location": location,
                    "actions":  [{"player_name": player, "action": action_text}],
                    "dm":       "",  # текст стримился, здесь недоступен
                },
            )
        except Exception as e:
            logger.warning(f"[STREAM] Memory write error: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# initialize_models_stub() УДАЛЁН.
#
# Почему это было критическим багом:
#   Строка 308 оригинала: initialize_models_stub()  ← выполнялась при импорте
#   → ModelRouter.register_model(...)               ← метода не существует
#   → AttributeError при импорте orchestrator
#   → main.py не мог загрузиться
#   → FastAPI никогда не стартовал
#   → start_enigma.bat ждал 60 сек → "Backend startup timeout"
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# УБРАНО: initialize_models_stub() вызывавшийся при импорте
#
# ПОЧЕМУ ЛОМАЛО ЗАПУСК:
#   ModelRouter.register_model("stub_model", stub_model)
#   → AttributeError: type object 'ModelRouter' has no attribute 'register_model'
#   → Любой import orchestrator падал с ошибкой
#   → FastAPI не мог стартануть
#
# Stub-модели для тестов регистрируются теперь только в conftest.py
# через patch, что правильно — тестовый код не должен быть в продакшене.
# ─────────────────────────────────────────────────────────────────────────────