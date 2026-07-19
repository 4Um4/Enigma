# backend/app/domain/memetic/voice_archetype.py
"""
Доменный тип VoiceArchetype (Canon).
Загружается из config/canon/voice_archetypes/<archetype>.yaml.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

import yaml

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class VoiceArchetype:
    """Родной язык NPC. Canon-level.
    
    Загружается из config/canon/voice_archetypes/<archetype>.yaml.
    Один архетип на много NPC (noble, thief, maid, ...).
    """
    archetype_id: str                # "noble" / "thief" / "maid" / ...
    culture: str                     # к какой культуре принадлежит по умолчанию
    register: str                    # "formal" / "slang" / "rustic" / ...
    
    # Базовые характеристики речи
    sentence_length: str             # "short" / "medium" / "long"
    vocabulary_richness: float       # 0..1
    metaphor_density: float          # 0..1
    
    # Сопротивление дрейфу
    default_linguistic_integrity: float  # 0..1, базовое сопротивление
    class_factor: float = 1.0        # множитель для целевых классов
    
    # Свободное описание (для LLM)
    voice_profile: str = ""           # "Говоришь тихо, короткими фразами..."
    
    # Канонические Expressions по умолчанию
    default_expressions: Dict[str, str] = field(default_factory=dict)

_CACHE: Dict[str, VoiceArchetype] = {}

# Корень проекта (на 5 уровней выше этого файла: memetic/ -> domain/ -> app/ -> backend/ -> ROOT)
_PROJECT_ROOT = Path(__file__).resolve().parents[4]

def load_voice_archetype(archetype_id: str, canon_dir: Optional[str] = None) -> Optional[VoiceArchetype]:
    """Загружает VoiceArchetype из YAML файла. Кэширует результат."""
    if not archetype_id:
        return None
        
    if archetype_id in _CACHE:
        return _CACHE[archetype_id]
        
    # ADR-O-MEMETIC: Абсолютный путь от корня проекта, чтобы работало из backend/ и из корня
    if canon_dir is None:
        canon_dir = _PROJECT_ROOT / "config" / "canon" / "voice_archetypes"
        
    file_path = Path(canon_dir) / f"{archetype_id}.yaml"
    if not file_path.exists():
        logger.warning(f"[VOICE_ARCHETYPE] File not found: {file_path}")
        return None
        
    try:
        data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
        archetype = VoiceArchetype(
            archetype_id=data.get("archetype_id", archetype_id),
            culture=data.get("culture", "unknown"),
            register=data.get("register", "default"),
            sentence_length=data.get("sentence_length", "medium"),
            vocabulary_richness=float(data.get("vocabulary_richness", 0.5)),
            metaphor_density=float(data.get("metaphor_density", 0.5)),
            default_linguistic_integrity=float(data.get("default_linguistic_integrity", 0.5)),
            class_factor=float(data.get("class_factor", 1.0)),
            voice_profile=data.get("voice_profile", ""),
            default_expressions=data.get("default_expressions", {})
        )
        _CACHE[archetype_id] = archetype
        return archetype
    except Exception as e:
        logger.error(f"[VOICE_ARCHETYPE] Failed to load {file_path}: {e}")
        return None