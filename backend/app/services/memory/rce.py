"""
RCE — Reality Commit Extractor.

Детерминированный экстрактор речевых событий из DM-нарратива.
Ни один LLM-выход не считается состоянием мира, пока не прошёл RCE-коммит.

Контракт:
  Вход: dm_text (str), target_npc_id, all_npcs_raw
  Выход: List[str] в формате "NPC_NAME: speech text"
         (совместим с write_npc_reactions_to_memory)
"""

import re
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Паттерны речи: «текст», "текст", „текст“
def _normalize_quotes(text: str) -> str:
    """Нормализует все варианты кавычек к ASCII " для упрощения парсинга.
    
    LLM может генерировать любой тип кавычек:
    - ASCII " (U+0022)
    - Unicode left/right "" (U+201C/U+201D)  
    - German low " (U+201E)
    - Русские «» оставляем — у них свой паттерн
    """
    text = text.replace('\u201c', '"').replace('\u201d', '"')  # "" → "
    text = text.replace('\u201e', '"')                          # „ → "
    # «» не трогаем — у них отдельный паттерн
    return text


_SPEECH_PATTERNS = [
    re.compile(r'«([^»]{1,300})»'),               # Русские кавычки «...» (не нормализуются)
    re.compile(r'"([^"]{1,300})"'),                # Любые двойные кавычки (после нормализации)
]

# Минимальная длина осмысленной речи (отсекает междометия-артефакты)
_MIN_SPEECH_LEN = 3


def extract_speech_events(
    dm_text: str,
    target_npc_id: Optional[str] = None,
    all_npcs_raw: Optional[list] = None,
    player_name: Optional[str] = None,
) -> List[str]:
    """Извлекает события речи из DM-нарратива.

    Возвращает список в формате "NPC_NAME: speech text",
    совместимом с write_npc_reactions_to_memory.

    Стратегия speaker binding (по приоритету):
      1. Явная атрибуция — имя NPC перед речью в том же предложении
      2. Fallback: target NPC (к кому обратился игрок)
      3. Fallback: первое совпадение имени NPC в предложении перед речью
    """
    if not dm_text:
        return []
    dm_text = _normalize_quotes(dm_text)

    # Строим маппинг имя → npc_id и npc_id → имя
    name_to_id, id_to_name = _build_name_maps(all_npcs_raw)

    # Резолвим имя target NPC
    target_npc_name: Optional[str] = None
    if target_npc_id and target_npc_id in id_to_name:
        target_npc_name = id_to_name[target_npc_id]

    # Шаг 1: Извлекаем все цитаты речи с контекстом
    speeches = _extract_all_speeches(dm_text)
    # НЕ делаем ранний return — fallback обработает случай без кавычек

    # Шаг 2: Speaker binding для каждой цитаты
    reactions = []
    for speech in speeches:
        speaker_name = _resolve_speaker(
            context_before=speech["context_before"],
            target_npc_name=target_npc_name,
            name_to_id=name_to_id,
            id_to_name=id_to_name,
            player_name=player_name,
        )
        if speaker_name:
            reactions.append(f"{speaker_name}: {speech['text']}")

    if reactions:
        logger.debug(f"[RCE] {len(reactions)} speech event(s) → STM: {reactions[:3]}")
    elif target_npc_name and dm_text and len(dm_text) < 500:
        # Fallback: DM ответил без кавычек, но есть target NPC —
        # считаем весь текст речью NPC (лучше потеря, чем амнезия)
        reactions = [f"{target_npc_name}: {dm_text.strip()[:200]}"]
        print(f"[RCE_FALLBACK] no quotes, assigning {len(dm_text)} chars to {target_npc_name}")

    return reactions


def _build_name_maps(
    all_npcs_raw: Optional[list],
) -> tuple[Dict[str, str], Dict[str, str]]:
    """Строит маппинги имя→id и id→имя из all_npcs_raw. Поддерживает list и dict форматы."""
    name_to_id: Dict[str, str] = {}
    id_to_name: Dict[str, str] = {}
    if all_npcs_raw:
        # Поддерживаем list[dict] (all_npcs_raw) и dict.values() (npc_positions)
        _npc_list = all_npcs_raw if isinstance(all_npcs_raw, list) else list(all_npcs_raw.values())
        for npc in _npc_list:
            if not isinstance(npc, dict):
                continue
            nid = npc.get("npc_id", npc.get("id", ""))
            nname = npc.get("name", "")
            if nid and nname:
                name_to_id[nname.lower()] = nid
                id_to_name[nid] = nname
                # Индексируем по каждому слову имени — DM может использовать любое
                # "Купец Горан" → "купец", "горан" (в русском обычно последнее слово)
                words = nname.lower().split()
                for word in words:
                    if word and word not in name_to_id:
                        name_to_id[word] = nid
    return name_to_id, id_to_name


def _extract_all_speeches(dm_text: str) -> List[dict]:
    """Извлекает все цитаты речи с контекстом перед ними."""
    speeches = []
    seen_positions = set()

    for pattern in _SPEECH_PATTERNS:
        _matches = list(pattern.finditer(dm_text))
        for match in _matches:
            start_pos = match.start()
            if start_pos in seen_positions:
                continue

            speech_text = match.group(1).strip()
            if len(speech_text) < _MIN_SPEECH_LEN:
                continue

            # Контекст перед речью — до 120 символов (1-2 предложения)
            ctx_start = max(0, start_pos - 120)
            context_before = dm_text[ctx_start:start_pos]

            speeches.append({
                "text": speech_text,
                "context_before": context_before,
                "position": start_pos,
            })
            seen_positions.add(start_pos)

    # Сортируем по позиции в тексте
    speeches.sort(key=lambda s: s["position"])
    return speeches


def _resolve_speaker(
    context_before: str,
    target_npc_name: Optional[str],
    name_to_id: Dict[str, str],
    id_to_name: Dict[str, str],
    player_name: Optional[str] = None,
) -> Optional[str]:
    """Определяет, кто произносит речь."""

    # Стратегия 1: Явная атрибуция — имя NPC в последнем предложении перед речью
    # Берём текст после последней точки/восклицания/вопроса
    last_sentence = _last_sentence(context_before)
    if last_sentence:
        found_name = _find_npc_in_text(last_sentence, name_to_id, id_to_name, player_name)
        if found_name:
            return found_name

    # Стратегия 1.5: Поиск во всём контексте перед речью
    if context_before:
        found_name = _find_npc_in_text(context_before, name_to_id, id_to_name, player_name)
        if found_name:
            return found_name

    # Стратегия 2: Fallback на target NPC
    # Если игрок обратился к NPC — речь скорее всего принадлежит этому NPC
    if target_npc_name:
        return target_npc_name

    # Нет спикера — пропускаем (не записываем в STM)
    return None


def _last_sentence(text: str) -> str:
    """Извлекает последнее предложение из текста."""
    # Разделители предложений
    for sep in ['. ', '! ', '? ', '.\n', '!\n', '?\n']:
        idx = text.rfind(sep)
        if idx >= 0:
            return text[idx + len(sep):].strip()
    return text.strip()


def _find_npc_in_text(
    text: str,
    name_to_id: Dict[str, str],
    id_to_name: Dict[str, str],
    player_name: Optional[str] = None,
) -> Optional[str]:
    """Ищет имя NPC в тексте, исключая имя игрока."""
    text_lower = text.lower()

    # Сначала проверяем полные имена (длинные → короткие для приоритета)
    sorted_names = sorted(name_to_id.keys(), key=len, reverse=True)
    for name_key in sorted_names:
        if name_key in text_lower:
            npc_id = name_to_id[name_key]
            resolved_name = id_to_name.get(npc_id, name_key)
            # Исключаем игрока (если его имя совпадает с NPC — маловероятно, но проверяем)
            if player_name and resolved_name.lower() == player_name.lower():
                continue
            return resolved_name

    return None