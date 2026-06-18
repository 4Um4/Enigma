# backend/app/services/spatial/role_resolver.py
# Назначение: Семантический маппинг — выводит NodeRole из label/type/manifest
# Приоритет: manifest_override > editor_type > keyword matching > DEFAULT
# Зависимости: app.models.spatial_contracts.NodeRole
"""
TODO:
- Добавить поддержку editor_tags, когда UI будет их отдавать
- Возможно, расширить словарь ключевых слов для более точного определения ролей
- В будущем: поддержка многоязычных лейблов (сейчас только русский и английский) — может потребоваться более сложная NLP-логика
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

from app.models.spatial_contracts import NodeRole


# ── Ключевые слова для вывода роли из label ──────────────────────────
# Порядок важен: более специфичные роли идут первыми

_ROLE_KEYWORDS: Dict[NodeRole, Set[str]] = {
    NodeRole.ENTRANCE: {
        "вход", "дверь", "entrance", "люк", "ворота", "калитка",
        "главный вход", "парадный",
    },
    NodeRole.TRANSITION: {
        "лестниц", "портал", "transition", "ladder", "trapdoor",
        "лестница", "ступень", "погреб", "подвал", "чердак",
        "переход", "проход",
    },
    NodeRole.BAR: {
        "стойк", "бар", "bar", "трактир", "кабак",
        "за стойкой", "у стойки",
    },
    NodeRole.BED: {
        "кровать", "спальн", "bed", "койка", "лежанк",
        "караульн", "постел", "опочивальн", "палатк",
    },
    NodeRole.TABLE: {
        "стол", "table", "столик",
    },
    NodeRole.WORKBENCH: {
        "верстак", "кузн", "workbench", "наковальн",
        "станк", "токарн", "плавильн",
    },
    NodeRole.MARKET: {
        "рынок", "market", "прилавок", "торг",
        "лавк", "магазин", "лавоч",
    },
}

# ── Editor type → NodeRole (однозначное соответствие) ─────────────────

_EDITOR_TYPE_MAP: Dict[str, NodeRole] = {
    "door": NodeRole.TRANSITION,
    "transition": NodeRole.TRANSITION,
    "ladder": NodeRole.TRANSITION,
    "portal": NodeRole.TRANSITION,
    "trapdoor": NodeRole.TRANSITION,
}


def resolve_role(
    node_label: str,
    editor_type: Optional[str] = None,
    editor_tags: Optional[List[str]] = None,
    manifest_override: Optional[NodeRole] = None,
    node_id: Optional[str] = None,
) -> NodeRole:
    """Выводит NodeRole по приоритетной цепочке.
    
    Приоритет:
    1. manifest_override — явное указание (будущий editor UI)
    2. editor_type — однозначное соответствие (door → TRANSITION)
    3. editor_tags — будущий слой (пока не реализован)
    4. keyword matching по label — эвристика
    5. keyword matching по node_id — fallback эвристика
    6. DEFAULT — если ничего не подошло
    """
    # 1. Явное указание — абсолютный приоритет
    if manifest_override is not None:
        return manifest_override

    # 2. Editor type — однозначное соответствие
    if editor_type and editor_type in _EDITOR_TYPE_MAP:
        return _EDITOR_TYPE_MAP[editor_type]

    # 3. Editor tags — будущий слой (когда editor UI поддержит теги)
    # if editor_tags:
    #     for tag in editor_tags:
    #         role = _TAG_ROLE_MAP.get(tag)
    #         if role:
    #             return role

    # 4. Keyword matching по label
    if node_label:
        label_lower = node_label.lower()
        for role, keywords in _ROLE_KEYWORDS.items():
            if any(kw in label_lower for kw in keywords):
                return role

    # 5. Keyword matching по node_id (fallback)
    #    "corner_table" → TABLE, "bar_area" → BAR, "kitchen" → WORKBENCH
    if node_id:
        nid_lower = node_id.lower()
        _NODE_ID_KEYWORDS: Dict[NodeRole, Set[str]] = {
            NodeRole.BAR: {"bar", "стойк"},
            NodeRole.BED: {"bed", "кровать", "спальн"},
            NodeRole.ENTRANCE: {"entrance", "вход", "door", "gate"},
            NodeRole.TABLE: {"table", "стол"},
            NodeRole.WORKBENCH: {"workbench", "кухн", "kitchen", "кузн"},
            NodeRole.MARKET: {"market", "рынок", "торг", "прилавок", "stall"},
            NodeRole.TRANSITION: {"transition", "ladder", "stairs", "лестниц"},
        }
        for role, keywords in _NODE_ID_KEYWORDS.items():
            if any(kw in nid_lower for kw in keywords):
                return role

    # 6. Fallback
    return NodeRole.DEFAULT