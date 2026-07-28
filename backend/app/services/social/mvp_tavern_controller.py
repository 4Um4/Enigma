"""
Файл: backend/app/services/social/mvp_tavern_controller.py
Назначение: Единая точка доступа к эпистемическим и социальным системам MVP.
Зависимости: Все созданные нами P7-компоненты.
"""

from pathlib import Path
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)
from app.services.truth_state_loader import TruthStateLoader
from app.models.truth_state import TruthState
from app.services.player_cognition.observation_log import ObservationLog
from app.services.player_cognition.player_belief_model import PlayerBeliefModel
from app.services.player_cognition.action_consequence_compiler import ActionConsequenceCompiler
from app.services.player_cognition.cognitive_dissonance_tracker import CognitiveDissonanceTracker
from app.services.social.social_fabric_tracker import SocialFabricTracker
from app.services.social.fate_tracker import FateTracker
from app.services.social.faction_alignment_tracker import FactionAlignmentTracker
from app.services.social.dilemma_engine import DilemmaEngine
from app.services.social.evaluation_engine import EvaluationEngine
from app.services.social.last_words_system import LastWordsSystem
from app.services.social.end_screen_builder import EndScreenDataBuilder
from app.services.social.exit_trigger import ExitTrigger
from app.services.state.world_diff_builder import WorldDiffBuilder

class MvpTavernController:
    """Фасад, объединяющий все системы миниигры для GameLoop."""
    
    def __init__(self, canon_path: Path, event_bus: Optional[Any] = None) -> None:
        self._canon_path = canon_path
        self._event_bus = event_bus
        
        # Инициализация базовых трекеров
        self.truth_state: Optional[TruthState] = None
        self.observation_log = ObservationLog()
        self.belief_model = PlayerBeliefModel()
        self.social_fabric = SocialFabricTracker()
        self.fate_tracker = FateTracker()
        self.faction_tracker = FactionAlignmentTracker()
        self.dilemma_engine = DilemmaEngine()
        self.cognitive_dissonance = CognitiveDissonanceTracker()
        
        # Сервисы
        self.evaluation_engine = EvaluationEngine()
        self.last_words_system = LastWordsSystem()
        self.end_screen_builder = EndScreenDataBuilder()
        self.exit_trigger = ExitTrigger()
        self.world_diff_builder = WorldDiffBuilder()
        
        # Компилятор последствий (связывает трекеры вместе)
        # truth_state и faction_tracker передаются как None, они установятся в init_campaign
        self.action_compiler = ActionConsequenceCompiler(
            observation_log=self.observation_log,
            belief_model=self.belief_model,
            social_fabric=self.social_fabric,
            truth_state=None,
            faction_tracker=self.faction_tracker
        )

        # WIRING ASSERTIONS — ловит M-03..M-10, N2
        assert self.observation_log is not None, "ObservationLog must init"
        assert self.belief_model is not None, "PlayerBeliefModel must init"
        assert self.social_fabric is not None, "SocialFabricTracker must init"
        assert self.fate_tracker is not None, "FateTracker must init"
        assert self.faction_tracker is not None, "FactionAlignmentTracker must init"
        assert self.dilemma_engine is not None, "DilemmaEngine must init"

        # Event subscription — ловит N2 (TICK_COMPLETED не существует)
        if self._event_bus is not None:
            try:
                from app.services.events.event_types import EventType
                self._event_bus.subscribe(EventType.TICK_COMPLETED, self.on_tick_completed)
            except (KeyError, AttributeError) as e:
                raise RuntimeError(
                    f"Cannot subscribe to TICK_COMPLETED: {e}. "
                    "Check event_types.py — EventType enum may be missing this value."
                ) from e

    def init_campaign(self, campaign_id: str) -> None:
        """Загрузка канона и сброс состояния для новой кампании."""
        # Загружаем каноническую истину
        self.truth_state = TruthStateLoader.load(self._canon_path)
        TruthStateLoader.validate(self.truth_state)
        
        # M-02/M-12 FIX: Инжектируем загруженный truth_state в action_compiler
        self.action_compiler._truth = self.truth_state
        
        # N11 FIX: Pre-seed фракций из factions.json
        import json
        from app.core.config import BASE_DIR
        factions_path = BASE_DIR / "config" / "world" / "factions.json"
        try:
            with open(factions_path, "r", encoding="utf-8") as f:
                factions_data = json.load(f)
            for faction_id, faction_data in factions_data.get("factions", {}).items():
                base_rep = float(faction_data.get("base_reputation", 0.0))
                self.faction_tracker.set_initial(faction_id, alignment=base_rep, known=True)
        except FileNotFoundError:
            logger.error(f"Factions config not found at {factions_path}. Skipping pre-seeding.")

    def on_tick_completed(self, event: Any) -> None:
        """M-03 FIX: Обновление трекеров по событию TICK_COMPLETED."""
        ctx = event.payload.get("snapshot")
        if not ctx:
            logger.warning("[MVP_TICK_SUBSCRIBER] TICK_COMPLETED event missing 'snapshot' in payload.")
            return
        # FateTracker: обновляем стабильность и угрозу
        for npc in ctx.all_npcs_raw:
            npc_id = npc.get("id", npc.get("npc_id"))
            if not npc_id: continue
            stability = 1.0 - (float(npc.get("stress", 0)) / 100.0)
            threat = float(npc.get("perceptual_kernel", {}).get("threat_gradient", 0.0))
            self.fate_tracker.update_state(npc_id, stability, threat)
            
        # DilemmaEngine: проверяем триггеры
        if self.truth_state:
            discovered = list(getattr(self.truth_state, "discovered_secrets", set()))
            self.dilemma_engine.check_triggers(discovered)
            
        # SocialFabric: устанавливаем baseline на первом тике
        if ctx.tick_number == 1:
            self._set_social_fabric_baseline(ctx.all_npcs_raw)

    def _set_social_fabric_baseline(self, all_npcs_raw: List[Dict[str, Any]]) -> None:
        """Инициализация базовых отношений для SocialFabricTracker."""
        from app.models.social_fabric import RelationshipSnapshot
        for i, n1 in enumerate(all_npcs_raw):
            for n2 in all_npcs_raw[i+1:]:
                id1 = n1.get("id", n1.get("npc_id"))
                id2 = n2.get("id", n2.get("npc_id"))
                if not id1 or not id2: continue
                # Мокаем baseline (0.0 trust, 0.0 fear)
                snap = RelationshipSnapshot(source_id=id1, target_id=id2, trust=0.0, fear=0.0, affection=0.0, debt=0.0, respect=0.0)
                self.social_fabric.set_baseline(id1, id2, snap)
                self.social_fabric.set_baseline(id2, id1, snap)
        
    def check_exit(self, scene_state: Dict[str, Any]) -> bool:
        """Проверяет, покинул ли игрок локацию."""
        return self.exit_trigger.check_exit(scene_state)

    def build_end_screen(self):
        """Собирает данные для финального экрана."""
        if not self.truth_state:
            raise RuntimeError("TruthState not loaded")
            
        evaluation = self.evaluation_engine.evaluate(
            truth=self.truth_state,
            beliefs=self.belief_model,
            observations=self.observation_log
        )
        
        return self.end_screen_builder.build(
            evaluation=evaluation,
            contradictions=self.cognitive_dissonance.get_all_contradictions(),
            fate_tracker=self.fate_tracker,
            last_words_system=self.last_words_system,
            social_fabric=self.social_fabric
        )

    def build_world_diff(self):
        """Собирает WorldStateDiff для передачи в следующую кампанию."""
        if not self.truth_state:
            raise RuntimeError("TruthState not loaded")
            
        return self.world_diff_builder.build(
            truth_state=self.truth_state,
            fate_tracker=self.fate_tracker,
            faction_tracker=self.faction_tracker,
            social_fabric=self.social_fabric,
            beliefs=self.belief_model
        )

    def serialize_end_screen(self) -> Dict[str, Any]:
        """V8-MVP-3 FIX: Сериализует EndScreenData и трекеры в dict для API."""
        end_screen = self.build_end_screen()
        ev = end_screen.evaluation
        
        _npc_fates_data = [
            {
                "npc_id": f.npc_id,
                "fate_outcome": f.fate_outcome,
                "last_word": {
                    "npc_id": f.last_word.npc_id,
                    "quote": f.last_word.quote,
                    "tone": f.last_word.tone.value
                } if f.last_word else None
            } for f in end_screen.npc_fates
        ]
        
        _contradictions_data = [
            {
                "contradiction_id": c.contradiction_id,
                "description": c.description,
                "emotional_weight": c.emotional_weight
            } for c in end_screen.contradictions
        ]

        _faction_alignments = {}
        for fa in self.faction_tracker.get_all():
            _faction_alignments[fa.faction_id] = {
                "alignment": fa.alignment,
                "known_to_faction": fa.known_to_faction
            }

        _social_fabric_deltas = []
        for d in self.social_fabric.get_all_deltas():
            _social_fabric_deltas.append({
                "tick": d.tick,
                "source_id": d.source_id,
                "target_id": d.target_id,
                "trust_delta": d.trust_delta,
                "fear_delta": d.fear_delta,
                "cause": d.cause
            })
        
        return {
            "exited": True,
            "score": ev.score,
            "secrets_total": ev.secrets_total,
            "secrets_identified": ev.secrets_identified,
            "secrets_misidentified": ev.secrets_misidentified,
            "secrets_missed": ev.secrets_missed,
            "methods_used": ev.methods_used,
            "npc_fates": _npc_fates_data,
            "contradictions": _contradictions_data,
            "faction_alignments": _faction_alignments,
            "social_fabric_deltas": _social_fabric_deltas,
        }