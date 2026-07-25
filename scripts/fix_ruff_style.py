import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

replacements = [
    (
        "backend/app/core/content_policy.py",
        """    if preset:
        if preset == "off": return ContentPolicy.preset_off()
        if preset == "moderate": return ContentPolicy.preset_moderate()
        if preset == "explicit": return ContentPolicy.preset_explicit()
""",
        """    if preset:
        if preset == "off":
            return ContentPolicy.preset_off()
        if preset == "moderate":
            return ContentPolicy.preset_moderate()
        if preset == "explicit":
            return ContentPolicy.preset_explicit()
"""
    ),
    (
        "backend/app/domain/memetic/voice_archetype.py",
        """class VoiceArchetype:
    \"\"\"Родной язык NPC. Canon-level.
    
    Загружается из config/canon/voice_archetypes/<archetype>.yaml.
    Один архетип на много NPC (noble, thief, maid, ...).
""",
        """class VoiceArchetype:
    \"\"\"Родной язык NPC. Canon-level.

    Загружается из config/canon/voice_archetypes/<archetype>.yaml.
    Один архетип на много NPC (noble, thief, maid, ...).
"""
    ),
    (
        "backend/app/domain/traversal_schema.py",
        """class TraversalProposal:
    \"\"\"Causal artifact: immutable proposal for physical movement.
    
    ADR-O-323: Created exclusively by MovementPlanner. Contains all
    validated data needed for materialization. Includes topology_version
""",
        """class TraversalProposal:
    \"\"\"Causal artifact: immutable proposal for physical movement.

    ADR-O-323: Created exclusively by MovementPlanner. Contains all
    validated data needed for materialization. Includes topology_version
"""
    ),
    (
        "backend/app/domain/traversal_schema.py",
        """class MovementPlanResult:
    \"\"\"Result of MovementPlanner planning attempt.
    
    If ACCEPTED, contains valid TraversalProposal.
    If REJECTED, contains reason. REJECTED proposals must NOT
""",
        """class MovementPlanResult:
    \"\"\"Result of MovementPlanner planning attempt.

    If ACCEPTED, contains valid TraversalProposal.
    If REJECTED, contains reason. REJECTED proposals must NOT
"""
    ),
    (
        "backend/app/domain/traversal_schema.py",
        """def build_traversal_dict(proposal: \"TraversalProposal\") -> Dict[str, Any]:
    \"\"\"Механический материализатор TraversalProposal в runtime dict.
    
    ADR-O-323: Не вычисляет семантику пути. Только сериализует авторизованный proposal.
    Единственный разрешённый способ создания traversal_dict.
""",
        """def build_traversal_dict(proposal: \"TraversalProposal\") -> Dict[str, Any]:
    \"\"\"Механический материализатор TraversalProposal в runtime dict.

    ADR-O-323: Не вычисляет семантику пути. Только сериализует авторизованный proposal.
    Единственный разрешённый способ создания traversal_dict.
"""
    ),
    (
        "backend/app/services/event_compiler.py",
        """    ) -> Tuple[bool, str]:
        \"\"\"ADR-O-323: Независимая валидация инвариантов TraversalProposal.
        
        Проверяет:
        1. Совпадение source/target с запрошенными
""",
        """    ) -> Tuple[bool, str]:
        \"\"\"ADR-O-323: Независимая валидация инвариантов TraversalProposal.

        Проверяет:
        1. Совпадение source/target с запрошенными
"""
    ),
    (
        "backend/app/services/execution/dialogue_queue.py",
        """class DialogueQueue:
    \"\"\"Единая очередь LLM-вызовов с приоритетами.
    
    Один LLM-вызов за раз (single-threaded). Все canonical/eavesdrop/DM
    запросы идут через эту очередь.
    
    Приоритеты (0-15):
        15 = crisis_anger (NPC в гневе, может атаковать)
""",
        """class DialogueQueue:
    \"\"\"Единая очередь LLM-вызовов с приоритетами.

    Один LLM-вызов за раз (single-threaded). Все canonical/eavesdrop/DM
    запросы идут через эту очередь.

    Приоритеты (0-15):
        15 = crisis_anger (NPC в гневе, может атаковать)
"""
    ),
    (
        "backend/app/services/memetic/linguistic_integrity_calculator.py",
        """class LinguisticIntegrityCalculator:
    \"\"\"Вычисляет linguistic_integrity для NPC.
    
    Формула: willpower * class_factor * age_factor * identity_attachment
    \"\"\"
""",
        """class LinguisticIntegrityCalculator:
    \"\"\"Вычисляет linguistic_integrity для NPC.

    Формула: willpower * class_factor * age_factor * identity_attachment
    \"\"\"
"""
    ),
    (
        "backend/app/services/memetic/linguistic_integrity_calculator.py",
        """    def _age_factor(self, age: int) -> float:
        \"\"\"Критический период по Леннбергу + подростковый пик по Лабову.
        
        0-2:    0.05 (не говорит)
        2-7:    0.1  (критический период, всё впитывает)
        7-12:   0.3  (раннее детство)
        12-15:  0.2  (подростковый пик — язык сверстников,
                      НО absorption_x1.5, не integrity)
        15-25:  0.5  (молодой взрослый)
        25-50:  0.8  (устойчивый взрослый)
        50+:    0.95 (язык застыл)
        
        ВАЖНО: age_factor для INTEGRITY (сопротивление) — обратно
        пропорционален пластичности. Чем младше, тем ниже integrity.
        \"\"\"
        if age < 2: return 0.05
        if age < 7: return 0.1
        if age < 12: return 0.3
        if age < 15: return 0.2
        if age < 25: return 0.5
        if age < 50: return 0.8
        return 0.95
""",
        """    def _age_factor(self, age: int) -> float:
        \"\"\"Критический период по Леннбергу + подростковый пик по Лабову.

        0-2:    0.05 (не говорит)
        2-7:    0.1  (критический период, всё впитывает)
        7-12:   0.3  (раннее детство)
        12-15:  0.2  (подростковый пик — язык сверстников,
                      НО absorption_x1.5, не integrity)
        15-25:  0.5  (молодой взрослый)
        25-50:  0.8  (устойчивый взрослый)
        50+:    0.95 (язык застыл)

        ВАЖНО: age_factor для INTEGRITY (сопротивление) — обратно
        пропорционален пластичности. Чем младше, тем ниже integrity.
        \"\"\"
        if age < 2:
            return 0.05
        if age < 7:
            return 0.1
        if age < 12:
            return 0.3
        if age < 15:
            return 0.2
        if age < 25:
            return 0.5
        if age < 50:
            return 0.8
        return 0.95
"""
    ),
    (
        "backend/app/services/npc/decision/social_deltas.py",
        """def get_base_delta(event_type: str) -> Tuple[float, float, str]:
    \"\"\"Возвращает базовые дельты для указанного типа события.
    
    Используется NpcDialogueSubscriber для NPC-NPC взаимодействий,
    чтобы избежать прямого доступа к приватному _BASE_DELTAS и сохранить SSOT.
""",
        """def get_base_delta(event_type: str) -> Tuple[float, float, str]:
    \"\"\"Возвращает базовые дельты для указанного типа события.

    Используется NpcDialogueSubscriber для NPC-NPC взаимодействий,
    чтобы избежать прямого доступа к приватному _BASE_DELTAS и сохранить SSOT.
"""
    ),
    (
        "backend/app/services/npc/npc_loader.py",
        """def reload_archetype_for(npc_dict: Dict[str, Any], new_archetype: str) -> Dict[str, Any]:
    \"\"\"Перезагружает schedule + activity_map из нового архетипа, сохраняя runtime-overlay (P2-11).
    
    ADR-TIFL-003: При кризисе идентичности NPC может сменить архетип.
    Эта функция перезагружает статические данные (schedule, activity_map) из нового архетипа,
""",
        """def reload_archetype_for(npc_dict: Dict[str, Any], new_archetype: str) -> Dict[str, Any]:
    \"\"\"Перезагружает schedule + activity_map из нового архетипа, сохраняя runtime-overlay (P2-11).

    ADR-TIFL-003: При кризисе идентичности NPC может сменить архетип.
    Эта функция перезагружает статические данные (schedule, activity_map) из нового архетипа,
"""
    ),
    (
        "backend/app/services/perception/behavior_manifestation_service.py",
        """        constraints = []
        for w in wounds:
            if not isinstance(w, dict): continue
            part = str(w.get(\"body_part\", \"\")).lower()
            sev = str(w.get(\"severity\", \"\")).lower()

            region = self._REGION_MAP.get(part)
            if not region: continue

            severity = self._SEVERITY_MAP.get(sev, 0.0)
            if severity == 0.0: continue

            function = self._FUNCTION_MAP.get(region, \"UNKNOWN\")
""",
        """        constraints = []
        for w in wounds:
            if not isinstance(w, dict):
                continue
            part = str(w.get(\"body_part\", \"\")).lower()
            sev = str(w.get(\"severity\", \"\")).lower()

            region = self._REGION_MAP.get(part)
            if not region:
                continue

            severity = self._SEVERITY_MAP.get(sev, 0.0)
            if severity == 0.0:
                continue

            function = self._FUNCTION_MAP.get(region, \"UNKNOWN\")
"""
    ),
    (
        "backend/app/services/player_cognition/action_consequence_compiler.py",
        """class ActionConsequenceCompiler:
    \"\"\"Единая точка распространения последствий действия игрока.
    
    Связывает изолированные трекеры в единую каузальную цепь:
    PlayerAction -> Observation -> Belief -> SocialFabric -> Faction
""",
        """class ActionConsequenceCompiler:
    \"\"\"Единая точка распространения последствий действия игрока.

    Связывает изолированные трекеры в единую каузальную цепь:
    PlayerAction -> Observation -> Belief -> SocialFabric -> Faction
"""
    ),
    (
        "backend/app/services/spatial/geometry_kernel.py",
        """    l2 = _dist_sq(s1, s2)
    if l2 == 0: return _dist_sq(p, s1)
    t = max(0, min(1, ((p[0] - s1[0]) * (s2[0] - s1[0]) + (p[1] - s1[1]) * (s2[1] - s1[1])) / l2))
""",
        """    l2 = _dist_sq(s1, s2)
    if l2 == 0:
        return _dist_sq(p, s1)
    t = max(0, min(1, ((p[0] - s1[0]) * (s2[0] - s1[0]) + (p[1] - s1[1]) * (s2[1] - s1[1])) / l2))
"""
    ),
    (
        "backend/app/services/spatial/geometry_kernel.py",
        """    if abs(o1) <= EPSILON and _on_segment(a1, a2, b1): return True
    if abs(o2) <= EPSILON and _on_segment(a1, a2, b2): return True
    if abs(o3) <= EPSILON and _on_segment(b1, b2, a1): return True
    if abs(o4) <= EPSILON and _on_segment(b1, b2, a2): return True
""",
        """    if abs(o1) <= EPSILON and _on_segment(a1, a2, b1):
        return True
    if abs(o2) <= EPSILON and _on_segment(a1, a2, b2):
        return True
    if abs(o3) <= EPSILON and _on_segment(b1, b2, a1):
        return True
    if abs(o4) <= EPSILON and _on_segment(b1, b2, a2):
        return True
"""
    ),
    (
        "backend/app/services/spatial/geometry_kernel.py",
        """    if segments_intersect(s1p1, s1p2, s2p1, s2p2): return 0.0
    return min(
        point_to_segment_dist_sq(s1p1, s2p1, s2p2),
""",
        """    if segments_intersect(s1p1, s1p2, s2p1, s2p2):
        return 0.0
    return min(
        point_to_segment_dist_sq(s1p1, s2p1, s2p2),
"""
    ),
    (
        "backend/app/services/spatial/geometry_kernel.py",
        """    if point_in_rect(p1, rx, ry, rw, rh): return 0.0
    if point_in_rect(p2, rx, ry, rw, rh): return 0.0
""",
        """    if point_in_rect(p1, rx, ry, rw, rh):
        return 0.0
    if point_in_rect(p2, rx, ry, rw, rh):
        return 0.0
"""
    ),
    (
        "backend/app/services/spatial/graph_compiler.py",
        """        from_node = graph.get(from_id)
        if not from_node: continue

        # S137.1: Собираем заблокированные рёбра, чтобы удалить их из графа.
""",
        """        from_node = graph.get(from_id)
        if not from_node:
            continue

        # S137.1: Собираем заблокированные рёбра, чтобы удалить их из графа.
"""
    ),
    (
        "backend/app/services/spatial/graph_compiler.py",
        """            to_node = graph.get(to_id)
            if not to_node: continue

            is_blocked = False
""",
        """            to_node = graph.get(to_id)
            if not to_node:
                continue

            is_blocked = False
"""
    ),
    (
        "backend/app/services/spatial/graph_compiler.py",
        """    if _segments_intersect(x1, y1, x2, y2, rx, ry, rx + rw, ry): return True
    if _segments_intersect(x1, y1, x2, y2, rx + rw, ry, rx + rw, ry + rh): return True
    if _segments_intersect(x1, y1, x2, y2, rx, ry + rh, rx + rw, ry + rh): return True
    if _segments_intersect(x1, y1, x2, y2, rx, ry, rx, ry + rh): return True
    return False
""",
        """    if _segments_intersect(x1, y1, x2, y2, rx, ry, rx + rw, ry):
        return True
    if _segments_intersect(x1, y1, x2, y2, rx + rw, ry, rx + rw, ry + rh):
        return True
    if _segments_intersect(x1, y1, x2, y2, rx, ry + rh, rx + rw, ry + rh):
        return True
    if _segments_intersect(x1, y1, x2, y2, rx, ry, rx, ry + rh):
        return True
    return False
"""
    ),
    (
        "backend/app/services/spatial/graph_compiler.py",
        """def _extract_affordance_objects(editor_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    \"\"\"Извлекает физические объекты с аффордансами из editor JSON.
    
    ADR-O-330: Кровать — это физический объект, а не навигационный узел.
    Возвращает список словарей с координатами и типами аффордансов.
""",
        """def _extract_affordance_objects(editor_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    \"\"\"Извлекает физические объекты с аффордансами из editor JSON.

    ADR-O-330: Кровать — это физический объект, а не навигационный узел.
    Возвращает список словарей с координатами и типами аффордансов.
"""
    ),
    (
        "backend/app/services/spatial/graph_compiler.py",
        """def _build_spatial_data(editor_data: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    \"\"\"Извлекает spatial_walls и spatial_obstacles из editor JSON.
    
    ADR-O-324: Перенесено из SceneStateManager для обеспечения Single Spatial Authority.
    SpatialService теперь владеет геометрией стен и может валидировать сегменты пути.
""",
        """def _build_spatial_data(editor_data: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    \"\"\"Извлекает spatial_walls и spatial_obstacles из editor JSON.

    ADR-O-324: Перенесено из SceneStateManager для обеспечения Single Spatial Authority.
    SpatialService теперь владеет геометрией стен и может валидировать сегменты пути.
"""
    ),
    (
        "backend/app/services/spatial/graph_compiler.py",
        """    \"\"\"Загружает JSON-файл локации.
    
    Поиск: search_dirs (если переданы) -> campaign_dir/locations -> campaign_dir.
    Сопоставление: по имени файла (location_id.json) или по полю location_id/id внутри JSON.
""",
        """    \"\"\"Загружает JSON-файл локации.

    Поиск: search_dirs (если переданы) -> campaign_dir/locations -> campaign_dir.
    Сопоставление: по имени файла (location_id.json) или по полю location_id/id внутри JSON.
"""
    ),
    (
        "backend/app/services/spatial/spatial_service.py",
        """    def is_segment_blocked(self, ax: float, ay: float, bx: float, by: float) -> bool:
        \"\"\"Проверяет, пересекает ли отрезок AB любую стену или непроходимое препятствие.
        
        ADR-O-324: Единственный метод для геометрической валидации сегментов пути.
        Используется MovementPlanner для проверки каждого отрезка маршрута.
""",
        """    def is_segment_blocked(self, ax: float, ay: float, bx: float, by: float) -> bool:
        \"\"\"Проверяет, пересекает ли отрезок AB любую стену или непроходимое препятствие.

        ADR-O-324: Единственный метод для геометрической валидации сегментов пути.
        Используется MovementPlanner для проверки каждого отрезка маршрута.
"""
    ),
    (
        "backend/app/services/spatial/spatial_service.py",
        """        \"\"\"Ищет физический объект с нужным аффордансом.
        
        ADR-O-330: Кровать — это объект, а не узел графа.
        Метод находит объект, берёт его XY и возвращает ближайший
        навигационный узел как точку маршрута (Interaction Point).
        \"\"\"
""",
        """        \"\"\"Ищет физический объект с нужным аффордансом.

        ADR-O-330: Кровать — это объект, а не узел графа.
        Метод находит объект, берёт его XY и возвращает ближайший
        навигационный узел как точку маршрута (Interaction Point).
        \"\"\"
"""
    ),
    (
        "backend/app/services/spatial/transition_topology_solver.py",
        """            if segments_intersect(src, tgt, c1, c2):
                denom = (c2[1]-c1[1])*(tgt[0]-src[0]) - (c2[0]-c1[0])*(tgt[1]-src[1])
                if abs(denom) < 1e-9: continue
                ua = ((c2[0]-c1[0])*(src[1]-c1[1]) - (c2[1]-c1[1])*(src[0]-c1[0])) / denom
""",
        """            if segments_intersect(src, tgt, c1, c2):
                denom = (c2[1]-c1[1])*(tgt[0]-src[0]) - (c2[0]-c1[0])*(tgt[1]-src[1])
                if abs(denom) < 1e-9:
                    continue
                ua = ((c2[0]-c1[0])*(src[1]-c1[1]) - (c2[1]-c1[1])*(src[0]-c1[0])) / denom
"""
    ),
    (
        "backend/app/services/spatial/traversal_transition_kernel.py",
        """class TraversalTransitionKernel:
    \"\"\"Оценивает возможность локального перехода для конкретного тела.
    
    В отличие от TraversabilityEvaluator (который оценивает прямую проходимость WALK),
    этот kernel оценивает сложные переходы (JUMP, CLIMB), требующие изменения режима движения.
""",
        """class TraversalTransitionKernel:
    \"\"\"Оценивает возможность локального перехода для конкретного тела.

    В отличие от TraversabilityEvaluator (который оценивает прямую проходимость WALK),
    этот kernel оценивает сложные переходы (JUMP, CLIMB), требующие изменения режима движения.
"""
    ),
    (
        "backend/app/services/verbalization/dm_contract_builder.py",
        """                system += \"\\n\\nТОН/РЕЖИМ: MATURE.\\n\"
                if self._policy.profanity_level >= 1: system += \"Разрешена лёгкая ругань.\\n\"
                if self._policy.violence_level >= 1: system += \"Разрешено физиологичное насилие.\\n\"
                if self._policy.sexual_content_level >= 1: system += \"Разрешены намёки.\\n\"
""",
        """                system += \"\\n\\nТОН/РЕЖИМ: MATURE.\\n\"
                if self._policy.profanity_level >= 1:
                    system += \"Разрешена лёгкая ругань.\\n\"
                if self._policy.violence_level >= 1:
                    system += \"Разрешено физиологичное насилие.\\n\"
                if self._policy.sexual_content_level >= 1:
                    system += \"Разрешены намёки.\\n\"
"""
    ),
    (
        "backend/tests/test_phase1_validation.py",
        """Зависимости: pytest, json, os
Запуск:
\"\"\"
""",
        """Зависимости: pytest, json, os
Запуск:
\"\"\"
"""
    ),
]

def apply_fixes():
    for rel_path, old_text, new_text in replacements:
        file_path = ROOT / rel_path
        if not file_path.exists():
            print(f"[WARN] File not found: {file_path}")
            continue
        
        content = file_path.read_text(encoding="utf-8")
        if old_text in content:
            content = content.replace(old_text, new_text)
            file_path.write_text(content, encoding="utf-8")
            print(f"[FIXED] {rel_path}")
        else:
            print(f"[SKIP] {rel_path} (pattern not found)")

if __name__ == "__main__":
    apply_fixes()
    print("Done.")