"""
Файл: backend/app/services/social/end_screen_builder.py
Назначение: Сборка данных для финального экрана.
Зависимости: typing, app.models., app.services.
"""

import logging
from typing import Any, List

logger = logging.getLogger(__name__)

from app.models.cognitive_dissonance import Contradiction
from app.models.end_screen import EndScreenData, NpcFateScreenData
from app.models.evaluation import EvaluationResult
from app.services.social.end_screen_narrator import EndScreenNarrator
from app.services.social.fate_tracker import FateTracker
from app.services.social.last_words_system import LastWordsSystem
from app.services.social.social_fabric_tracker import SocialFabricTracker


class EndScreenDataBuilder:
    def build(
        self,
        evaluation: EvaluationResult,
        contradictions: List[Contradiction],
        fate_tracker: FateTracker,
        last_words_system: LastWordsSystem,
        social_fabric: SocialFabricTracker,
        relationship_store: Any = None,
        campaign_id: str = "",
        name_resolver: Any = None,  # Callable[[str], str] | None — End-Screen имена (S292)
    ) -> EndScreenData:

        npc_fates_data: List[NpcFateScreenData] = []
        fate_texts: List[str] = []
        relationship_texts: List[str] = []

        # S292 (End-Screen имена): display-name для нарратива. Резолвер
        # инжектится controller'ом (статический SSOT config/npc). Fail-open:
        # нет резолвера/имени — npc_id как есть (прежнее поведение).
        def _dn(npc_id: str) -> str:
            if name_resolver is None:
                return npc_id
            try:
                return name_resolver(npc_id) or npc_id
            except Exception as _dn_err:
                # L4: fail-open с логом — резолв имени не может ронять финал.
                logger.debug(f"[END_SCREEN] name_resolver failed for {npc_id!r}: {_dn_err}")
                return npc_id

        for fate_state in fate_tracker.get_all_states():
            _disp = _dn(fate_state.npc_id)
            fate_texts.append(EndScreenNarrator.narrate_fate(_disp, fate_state))
            if fate_state.resolved_fate:
                last_word = last_words_system.get_last_word(
                    npc_id=fate_state.npc_id,
                    fate=fate_state.resolved_fate,
                    social_fabric=social_fabric
                )
                npc_fates_data.append(NpcFateScreenData(
                    npc_id=fate_state.npc_id,
                    fate_outcome=fate_state.resolved_fate.value,
                    last_word=last_word
                ))

        # 8.1 FIX: Генерация текста для социального графа
        if relationship_store and campaign_id:
            all_rels = relationship_store.get_all(campaign_id)
            for src_tgt, vals in all_rels.items():
                if "→" not in src_tgt: continue
                src, tgt = src_tgt.split("→", 1)
                trust = float(vals.get("trust", 0.0))
                fear = float(vals.get("fear", 0.0))
                # Чтобы не захламлять экран, пропускаем нейтральные
                if abs(trust) < 10.0 and fear < 10.0: continue
                relationship_texts.append(
                    EndScreenNarrator.narrate_relationship(_dn(src), _dn(tgt), trust, fear)
                )

        return EndScreenData(
            evaluation=evaluation,
            npc_fates=npc_fates_data,
            contradictions=contradictions,
            verdict_text=EndScreenNarrator.narrate_verdict(evaluation.score if hasattr(evaluation, "score") else 0),
            fate_texts=fate_texts,
            relationship_texts=relationship_texts
        )
