from __future__ import annotations

# backend/app/services/player_avatar_service.py
"""
PlayerAvatarService — живой аватар персонажа игрока.

Назначение: Единый сервис живого аватара игрока — объединяет CharacterSheet (статика) + CharacterProfile (психология) + NPCState (живое состояние)
Зависимости: app.models.schemas, app.models.character, app.models.npc_state, app.models.physical
Основные сущности: PlayerAvatarService

Архитектура:
- Avatar = NPCState (живое состояние) + CharacterSheet (статика) + CharacterProfile (психология)
- NPCState переиспользуется как есть — те же эмоции, стресс, раны, условия
- Отличие от NPC: intent не рассчитывается DecisionHub, а определяется действием игрока
- Хранение: player_avatar.json в папке кампании (единый файл, три слоя)

Будущие расширения (возраст, пол, магия, навыки, профессия) — в CharacterSheet.
Никакой надстройки над базой — один JSON, три слоя.
"""


import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from app.models.behavior_mask import BehaviorMaskState
from app.models.character import CharacterProfile
from app.models.npc_state import (
    EmotionTag,
    NPCState,
    WillState,
    _emotion_from_str,
    _pk_from_dict,
)
from app.models.physical import Condition, Wound
from app.models.schemas import CharacterSheet

logger = logging.getLogger(__name__)


class PlayerAvatarService:
    """
    Загрузка, сохранение и управление живым состоянием аватара игрока.

    Три слоя данных:
    - sheet: CharacterSheet — статика (HP, AC, stats, inventory, levels...)
    - profile: CharacterProfile — психология (ценности, integrity, npc_trust)
    - state: NPCState — живое состояние (stress, emotion, wounds, conditions)
    """

    def __init__(self, root: str = "saves") -> None:
        self.root = Path(root)
        # ADR-JOURNAL: Буфер последних 100 реплик (RAM SSOT)
        # B1.3-FIX: Привязка журнала к campaign_id (раньше был общий список).
        self._dialog_journals: Dict[str, List[Dict[str, str]]] = {}

    def clear_journal(self, campaign_id: str) -> None:
        """B1.3-FIX: Очистка RAM-кэша журнала при new_game (устранение утечки старых данных)."""
        if campaign_id in self._dialog_journals:
            del self._dialog_journals[campaign_id]

    def _avatar_path(self, campaign_id: str) -> Path:
        return self.root / campaign_id / "player_avatar.json"

    def _ensure_campaign_dir(self, campaign_id: str) -> Path:
        campaign_dir = self.root / campaign_id
        campaign_dir.mkdir(parents=True, exist_ok=True)
        return campaign_dir

    # ── Загрузка ──────────────────────────────────────────────────────

    def load_avatar(self, campaign_id: str, player_name: str) -> Optional[dict]:
        """
        Загружает полный аватар из player_avatar.json.
        Returns dict с ключами 'sheet', 'profile', 'state' или None.
        """
        path = self._avatar_path(campaign_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            # Проверка совпадения имени
            if data.get("state", {}).get("npc_id") != player_name:
                logger.warning(
                    f"[AVATAR] имя не совпадает: "
                    f"{data.get('state', {}).get('npc_id')} != {player_name}"
                )
                return None
            # B1.3-FIX: Загрузка журнала из файла в кэш (если есть)
            if "dialog_journal" in data:
                self._dialog_journals[campaign_id] = data["dialog_journal"]
            return data
        except Exception as e:
            logger.error(f"[AVATAR] ошибка загрузки: {e}")
            return None

    def load_state(self, campaign_id: str, player_name: str) -> NPCState:
        avatar = self.load_avatar(campaign_id, player_name)
        if avatar and avatar.get("state"):
            _state = self._state_from_dict(avatar["state"])
            # SHI-FIX TRADE: гарантируем наличие денег
            if not _state.body_state:
                _state.body_state = {}
            if "money" not in _state.body_state:
                _state.body_state["money"] = 48
            return _state

        _default = NPCState(npc_id=player_name)
        if not _default.body_state:
            _default.body_state = {}
        _default.body_state["money"] = _default.body_state.get("money", 48)
        # SHI-FIX AVATAR: базовая психика для WillpowerGate.
        _default.drives = {
            "control": 0.25,
            "significance": 0.25,
            "fear": 0.25,
            "desire": 0.25,
        }
        _default.psyche = {"willpower": 50, "breakpoint": 70, "loyalty_true": 0}

        # S-93 AVATAR_RESISTANCE: аватар должен сопротивляться действиям, противоречащим его природе
        # (например, "оскорбить бога" для паладина). WillpowerGate вернёт RESIST и сгенерирует stress.
        # Пока заглушка, возвращающая корректный стейт. Полная логика будет в DecisionHub.
        return _default

    def load_sheet(self, campaign_id: str, player_name: str) -> CharacterSheet:
        """Загружает CharacterSheet аватара."""
        avatar = self.load_avatar(campaign_id, player_name)
        if avatar and avatar.get("sheet"):
            try:
                return CharacterSheet.model_validate(avatar["sheet"])
            except Exception as e:
                logger.debug(f"[AVATAR] Ошибка валидации листа персонажа: {e}")
        return CharacterSheet(name=player_name)

    def load_profile(self, campaign_id: str, player_name: str) -> CharacterProfile:
        """Загружает CharacterProfile аватара."""
        avatar = self.load_avatar(campaign_id, player_name)
        if avatar and avatar.get("profile"):
            try:
                return CharacterProfile.from_dict(avatar["profile"])
            except Exception as e:
                logger.debug(f"[AVATAR] Ошибка валидации листа персонажа: {e}")
        return CharacterProfile(character_id=player_name)

    # ── Сохранение ────────────────────────────────────────────────────

    def save_avatar(
        self,
        campaign_id: str,
        sheet: CharacterSheet,
        profile: CharacterProfile,
        state: NPCState,
    ) -> None:
        """Сохраняет полный аватар атомарно."""
        self._ensure_campaign_dir(campaign_id)
        path = self._avatar_path(campaign_id)
        data = {
            "sheet": sheet.model_dump(),
            "profile": profile.to_dict(),
            "state": self._state_to_dict(state),
            # B1.3-FIX: Персистентность журнала (если кэш инициализирован)
            "dialog_journal": self._dialog_journals.get(campaign_id, []),
        }
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.debug(f"[AVATAR] сохранён: {state.npc_id} stress={state.stress:.1f}")

    def save_state(self, campaign_id: str, state: NPCState) -> None:
        """Сохраняет только живое состояние (частое обновление между тиками)."""
        self._ensure_campaign_dir(campaign_id)
        path = self._avatar_path(campaign_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            data = {}
        data["state"] = self._state_to_dict(state)
        # B1.3-FIX: Персистентность журнала при save_state.
        # Сохраняем только если кэш инициализирован, иначе оставляем то, что есть в файле.
        if campaign_id in self._dialog_journals:
            data["dialog_journal"] = self._dialog_journals[campaign_id]
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── Миграция: characters.json → player_avatar.json ───────────────

    def migrate_from_characters_json(
        self, campaign_id: str, sheet: CharacterSheet
    ) -> None:
        """
        Первичная миграция: создаёт player_avatar.json из CharacterSheet.
        Вызывается один раз при первом выборе персонажа.
        """
        if self.load_avatar(campaign_id, sheet.name) is not None:
            return  # Уже мигрирован
        profile = CharacterProfile(character_id=sheet.name)
        state = NPCState(
            npc_id=sheet.name,
            hp=sheet.effective_hp,
            max_hp=sheet.effective_max_hp,
        )
        self.save_avatar(campaign_id, sheet, profile, state)
        logger.info(f"[AVATAR] мигрирован из characters.json: {sheet.name}")

    # ── Сериализация NPCState ─────────────────────────────────────────
    # Только поля, нужные для персистентности.
    # Эфемерные поля НЕ сохраняются: intent*, relationship_cache,
    # narrative_cache, causal_ledger, pressure_accumulator.

    def _state_to_dict(self, state: NPCState) -> dict:
        """NPCState → JSON-совместимый dict."""
        # Conditions: dict[str, Condition] → dict[str, dict]
        conditions = {}
        for k, v in state.conditions.items():
            conditions[k] = {
                "type": v.type,
                "severity": v.severity,
                "duration_ticks": v.duration_ticks,
                "decay_per_tick": v.decay_per_tick,
                "tick": v.tick,
            }

        # Wounds: list[Wound] → list[dict]
        wounds = []
        for w in state.wounds:
            wounds.append(
                {
                    "body_part": w.body_part,
                    "severity": w.severity.value
                    if hasattr(w.severity, "value")
                    else str(w.severity),
                    "damage_type": w.damage_type.value
                    if hasattr(w.damage_type, "value")
                    else str(w.damage_type),
                    "tick": w.tick,
                    "healing_ticks": w.healing_ticks,
                }
            )

        # BehaviorMaskState
        mask = state.behavior_mask
        mask_dict = {
            "mask": mask.mask.value if hasattr(mask.mask, "value") else str(mask.mask),
            "applied_at_day": mask.applied_at_day,
            "intensity": mask.intensity,
        }

        return {
            "npc_id": state.npc_id,
            # Психика
            "stress": state.stress,
            "resentment": state.resentment,
            "dependency": state.dependency,
            "identity_integrity": state.identity_integrity,
            "pressure_resistance": state.pressure_resistance,
            "will_state": state.will_state.value
            if hasattr(state.will_state, "value")
            else str(state.will_state),
            "behavior_mask": mask_dict,
            "trauma_markers": list(state.trauma_markers),
            "current_role": state.current_role,
            # Физика
            "hp": state.effective_hp,
            "max_hp": state.effective_max_hp,
            "conditions": conditions,
            "wounds": wounds,
            "posture": state.posture,
            # ADR-128: body_state — SSOT физиологии (injuries, blood_loss, pain, shock_impulse).
            # Без этого injuries теряются при save_state() — AvatarService сериализует
            # wounds/conditions (legacy), но не body_state (runtime truth).
            "body_state": state.body_state if state.body_state else {},
            # Эмоции
            "emotion": state.emotion.value
            if hasattr(state.emotion, "value")
            else str(state.emotion),
            "emotion_delta": state.emotion_delta,
            "state_modifiers": state.state_modifiers,
            # ADR-128: Runtime-поля, теряющиеся без сериализации.
            # Без affective_load/emotion/perceptual_kernel аватар
            # сбрасывается в NEUTRAL при каждой загрузке.
            "affective_load": state.affective_load,
            "perceptual_kernel": {
                k: v for k, v in state.perceptual_kernel.__dict__.items()
            }
            if state.perceptual_kernel
            else {},
            # ADR-GENDER: Персистенция пола аватара. Без этого поле теряется при save/load.
            "gender": state.gender,
            # B1.3-FIX: Журнал обрабатывается в save_avatar/save_state, здесь ему не место.
        }

    def _state_from_dict(self, data: dict) -> NPCState:
        """dict → NPCState."""
        # Conditions
        conditions = {}
        for k, v in data.get("conditions", {}).items():
            conditions[k] = Condition(
                type=v["type"],
                severity=v.get("severity", 0.0),
                duration_ticks=v.get("duration_ticks", 1),
                decay_per_tick=v.get("decay_per_tick", 0.1),
                tick=v.get("tick", 0),
            )

        # Wounds
        wounds = []
        for w in data.get("wounds", []):
            try:
                wounds.append(
                    Wound(
                        body_part=w["body_part"],
                        severity=w["severity"],
                        damage_type=w["damage_type"],
                        tick=w.get("tick", 0),
                        healing_ticks=w.get("healing_ticks", 0),
                    )
                )
            except Exception:
                logger.warning(f"[AVATAR] пропуск wound: {w}")

        # BehaviorMaskState
        mask_data = data.get("behavior_mask", {})
        try:
            mask = BehaviorMaskState(
                mask=mask_data.get("mask", "NONE"),
                intensity=mask_data.get("intensity", 0.0),
            )
        except Exception:
            mask = BehaviorMaskState()

        return NPCState(
            npc_id=data.get("npc_id", "unknown"),
            stress=float(data.get("stress", 0.0)),
            resentment=float(data.get("resentment", 0.0)),
            dependency=float(data.get("dependency", 0.0)),
            identity_integrity=float(data.get("identity_integrity", 1.0)),
            pressure_resistance=float(data.get("pressure_resistance", 0.0)),
            will_state=WillState(data.get("will_state", "free")),
            behavior_mask=mask,
            trauma_markers=set(data.get("trauma_markers", [])),
            current_role=data.get("current_role", ""),
            hp=int(data.get("hp", 0)),
            max_hp=int(data.get("max_hp", 0)),
            conditions=conditions,
            wounds=wounds,
            posture=data.get("posture", "standing"),
            # ADR-128: body_state — SSOT физиологии. Без этого injuries,
            # blood_loss, pain, shock_impulse теряются при каждой загрузке.
            body_state=dict(data.get("body_state", {})),
            # ADR-128: affective_load — интеграл давления. Без этого
            # эмоциональный pipeline сбрасывается в 0.0 при каждой загрузке.
            affective_load=float(data.get("affective_load", 0.0)),
            emotion=_emotion_from_str(data.get("emotion", "neutral")),
            emotion_delta=float(data.get("emotion_delta", 0.0)),
            state_modifiers=data.get("state_modifiers", {}),
            # ADR-128: perceptual_kernel — субъективная модель восприятия.
            # Без этого threat_gradient/initiative_suppression = 0.0 при каждой загрузке.
            perceptual_kernel=_pk_from_dict(data.get("perceptual_kernel", {})),
            # ADR-GENDER: Восстановление пола аватара из персистенции.
            gender=data.get("gender", "male"),
        )
        # B1.3-FIX: Журнал обрабатывается в load_avatar, здесь ему не место.

    # ── ADR-JOURNAL: Управление очередью реплик ───────────────────
    def append_journal(self, campaign_id: str, speaker: str, text: str):
        """Добавление реплики в журнал. Инвариант J-100 (FIFO)."""
        if not text:
            return
        if campaign_id not in self._dialog_journals:
            self._dialog_journals[campaign_id] = []
        self._dialog_journals[campaign_id].append({"speaker": speaker, "text": text})
        # Ограничение 100 последних высказываний
        if len(self._dialog_journals[campaign_id]) > 100:
            self._dialog_journals[campaign_id] = self._dialog_journals[campaign_id][
                -100:
            ]

    def get_journal(self, campaign_id: str) -> list:
        """Возвращает буфер журнала для проекции во WorldSnapshotDTO (копия, чтобы предотвратить мутацию)."""
        return list(self._dialog_journals.get(campaign_id, []))


# Глобальный экземпляр
player_avatar_service = PlayerAvatarService()
