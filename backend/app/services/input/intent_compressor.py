"""
Файл: backend/app/services/input/intent_compressor.py
Назначение: Извлечение IntentSemanticField из сырого текста. Fast Path (детерминированный) + Slow Path (LLM).
Зависимости: domain.intent_profile, services.input.llm_compressor_client
Основные сущности: IntentCompressor

TODO: В будущем IntentCompressor может быть расширен для поддержки более сложных схем извлечения, таких как использование нескольких моделей (например, специализированные модели для разных типов интентов), адаптивные стратегии промптинга (например, уточняющие вопросы при высокой неопределенности) и более богатые семантические поля (например, социальные интенты, скрытые мотивы). Но для MVP достаточно базового компрессора с детерминированным Fast Path и LLM Slow Path.

"""

import logging
import re
from typing import Any, Dict, Optional, cast

from app.domain.epistemology import Predicate, Proposition, SocialIntent, SpeechAct
from app.domain.intent_profile import (
    ActionType,
    ConfidenceVector,
    EmotionalVector,
    IntentSemanticField,
    SemanticAmbiguity,
    TargetZone,
)
from app.domain.subject_ref import SubjectKind, SubjectRef
from app.services.input.llm_compressor_client import LLMCompressorClient
from app.services.memory.dialogue_session import DialogueSession

logger = logging.getLogger(__name__)

try:
    import pymorphy3

    MORPH = pymorphy3.MorphAnalyzer()
    PYMORPHY_AVAILABLE = True
except ImportError:
    MORPH = None
    PYMORPHY_AVAILABLE = False

# Словари лемм для детерминированного матчера (оба вида глаголов)
_ACTION_LEMMAS = {
    # M1/P3 (ТЗ «Таверна тайн»): ASK-контур fast-path — чистый вопрос не
    # должен умирать в UNCERTAIN при недоступном LLM. Леммы — индикаторы
    # вопроса (I4: НЕ триггерные фразы — совпадение даёт QUESTION-акт,
    # предмет отдельной осью SubjectRef).
    ActionType.DIALOGUE: {
        "спросить",
        "расспросить",
        "выспросить",
        "рассказ",  # корень: расскажи/рассказать (pymorphy-нормали не всегда сходятся)
        "рассказать",
        "рассказывать",
        "поведать",
        "спроси",
        "знать",  # «ты знаешь…»
        "знаешь",
        "известно",
        "видеть",  # «ты видел…»
        "видел",
        "слышать",
        "слышал",
        "услышать",
        "услышал",
        "почему",
        "зачем",
        "кто",
        "что",  # осторожно: пересечение с бытовой речью — см. _ASK_WEAK-гейт ниже
    },
    ActionType.MOVE: {
        "пойти",
        "идти",
        "подойти",
        "подходить",
        "перейти",
        "переходить",
        "бежать",
        "бегать",
        "шагнуть",
        "шагать",
        "приблизиться",
        "приближаться",
        "сопровождать",
        "сопровождай",
        "следовать",
        "следуй",
        "выйти",
        "выходить",
        "покинуть",
        "войти",
        "входить",
        "отойди",
        "отступить",
        "отступай",
        "посторониться",
        "посторонись",
    },
    ActionType.OBSERVE: {
        "осмотреть",
        "осматривать",
        "изучить",
        "изучать",
        "посмотреть",
        "смотреть",
        "оглядеть",
        "оглядывать",
        "увидеть",
        "видеть",
        "заметить",
        "замечать",
        "рассмотреть",
        "рассматривать",
    },
    ActionType.INTERACT: {
        "взять",
        "брать",
        "открыть",
        "открывать",
        "использовать",
        "пользоваться",
        "положить",
        "класть",
        "отдать",
        "передать",
        "поднять",
        "поднимать",
    },
    ActionType.ATTACK: {
        "бить",
        "выбить",
        "побить",
        "избить",
        "отбить",
        "пробить",
        "разбить",
        "забить",
        "добить",
        "отколотить",
        "наказать",
        "прикончить",
        "замахнуться",
        "ударить",
        "ударять",
        "атаковать",
        "врезать",
        "убить",
        "убивать",
        "поразить",
        "поражать",
        "рубить",
        "колоть",
        "расправиться",
        "калечить",
        "покалечить",
        "искалечить",
        "укусить",
        "кусать",
        "откусить",
        "откусывать",
        "покусать",
        "отгрызть",
        "грызть",
        "цапнуть",
        "расцарапать",
        "царапать",
        "душить",
        "задушить",
        "толкнуть",
        "толкать",
        "пнуть",
        "пинать",
        "плевать",
        "оплевать",
        "стукнуть",
        "шлёпнуть",
        "дать",
        "заехать",
        "вмазать",
    },
    ActionType.THREATEN: {
        "угрожать",
        "пригрозить",
        "пугать",
        "напугать",
        "запугивать",
        "запугать",
        "шантажировать",
        "пристрастить",
        "устрашить",
        "устрашать",
    },
    ActionType.PERSUADE: {
        "уговаривать",
        "уговорить",
        "убеждать",
        "убедить",
        "просить",
        "попросить",
        "умолять",
    },
}

# Плоский словарь всех лемм действий, чтобы не принять слово "удар" за цель
_ACTION_LEMMAS_FLAT = set(lemma for s in _ACTION_LEMMAS.values() for lemma in s)

# №7-a/zone_raw: синонимы зон из живых ответов LLM + нормализатор для Reconciler
# (консолидация с _safe_enum — косметика после исследования)
_ZONE_SYNONYMS = {
    "EYES": "HEAD", "EYE": "HEAD",
    "EYE_LEFT": "HEAD", "EYE_RIGHT": "HEAD",
    "NOSE": "HEAD",
}


def normalize_zone(val: Any) -> Optional[TargetZone]:
    """Строка → TargetZone (с синонимами); UNDEFINED/пусто/неизвестно → None."""
    if not val:
        return None
    _v = str(val).upper()
    if _v == "UNDEFINED":
        return None
    _v = _ZONE_SYNONYMS.get(_v, _v)
    try:
        return TargetZone(_v)
    except ValueError as _z_err:
        logger.debug(f"[RECONCILE] zone {_v!r} не нормализуется: {_z_err}")
        return None

_INTENSITY_LEMMAS = {
    # ИСПРАВЛЕНО: убраны 'весь' (местоимение — 'весь день' давало false positive
    # high intensity) и 'дурь' (существительное — 'дурь прошла' давало false positive).
    # Добавлены реальные маркеры высокой интенсивности.
    "high": {
        "резко",
        "сильно",
        "мощно",
        "яростно",
        "немедленно",
        "живо",
        "приказываю",
        "быстро",
        "исступлённо",
        "неистово",
        "бешено",
        "стремительно",
        "мгновенно",
        "беспощадно",
    },
    "low": {
        "осторожно",
        "медленно",
        "тихо",
        "аккуратно",
        "слегка",
        "немного",
        "плавно",
        "мягко",
    },
}


# ── M1/P3: предметная ось вопроса (SubjectRef; коррекция Мастера) ──────────

_ASK_STRONG = {
    "спросить", "расспросить", "выспросить", "спроси",
    "почему", "зачем", "известно",
}
_ASK_MEDIUM = {
    "рассказ", "рассказать", "рассказывать", "поведать", "знать", "знаешь",
    "видеть", "видел", "слышать", "слышал", "услышать", "услышал",
}
# «кто/что» — слабые: бытовая речь («что наливаю?») тоже их содержит;
#QUESTION требует сильный/средний индикатор ИЛИ вопросительный знак.
_QUESTION_MARK = "?"


def _is_question(lemmas: set, raw_text: str) -> bool:
    """N1-гейт: чистое действие («наливаю пиво») не QUESTION. Сильные
    индикаторы достаточны; слабые (кто/что) — только при '?' в тексте."""
    if not lemmas.isdisjoint(_ASK_STRONG):
        return True
    if not lemmas.isdisjoint(_ASK_MEDIUM):
        return True
    return _QUESTION_MARK in raw_text and (
        "кто" in lemmas or "что" in lemmas
    )


# M1/P3: предлоги с ГРАНИЦЕЙ СЛОВА — «о» внутри «что/кто» не предлог
# (зонд-урок 2026-09-12: «Что ты знаешь о Люсе?» матчило «о » в «что »
# -> ложный NP «ты знаешь о»; 3/4 красных имели этот единый корень).
_SUBJECT_PREPOSITIONS = (" о ", " об ", " про ", " насчёт ", " насчет ")


def _extract_np_after_preposition(text: str) -> str | None:
    """NP-группа (до 3 токенов) после предлога предмета; lowercase; без
    пунктуации-хвоста. Word-boundary: предлог обязан стоять между
    пробелами. Best-effort: None = нет предлога (не ошибка)."""
    lowered = " " + text.lower().strip() + " "
    for prep in _SUBJECT_PREPOSITIONS:
        idx = lowered.find(prep)
        if idx >= 0:
            tail = lowered[idx + len(prep):].strip()
            tail = tail.rstrip("?!.,;:").strip()
            tokens = tail.split()[:3]
            return " ".join(tokens) if tokens else None
    return None


def extract_subject(raw_text: str) -> SubjectRef:
    """M1/P3: предмет вопроса → SubjectRef. Резолв: NPC (name_forms
    прецедент) → канон-тема → event-NP → UNKNOWN. Детерминировано;
    нерезолв сохраняет hint (N2). Не решает knows/reveals (P4/P5)."""
    np = _extract_np_after_preposition(raw_text)
    if not np:
        # «почему Горан нервничает?» — без предлога: первый токен после
        # слабого индикатора; fallback: вся строка как hint
        return SubjectRef(kind=SubjectKind.UNKNOWN, subject_id=None,
                          subject_hint=raw_text.strip()[:60] or None)

    # 1) NPC-резолв по канон-словарю имён (детерминированный реестр)
    _hit = _resolve_npc_by_name(np)
    if _hit is not None:
        return SubjectRef(kind=SubjectKind.NPC, subject_id=_hit, subject_hint=np)

    # 2) Канон-тема: topics-словарь секретов (тема ≠ discovery)
    _topic = _resolve_canon_topic(np)
    if _topic is not None:
        return SubjectRef(kind=SubjectKind.CANON_TOPIC, subject_id=_topic,
                          subject_hint=np)

    # 3) Событие/сущность: NP сохраняется как hint (без онтологии событий)
    return SubjectRef(kind=SubjectKind.EVENT, subject_id=None, subject_hint=np)


_M1_NPC_NAMES: dict[str, str] | None = None


def _npc_display_names() -> dict[str, str]:
    """M1/P3 (Мастер: движок не знает имён; entity -> языковые формы):
    ленивый реестр {npc_id: name} ИЗ ДАННЫХ МИРА (individuals/*.json,
    поле "name"). Новый NPC-контент -> имя доступно языку автоматически;
    в коде — ноль имён. Поколенчески устойчиво (Generation-0 слеп)."""
    global _M1_NPC_NAMES
    if _M1_NPC_NAMES is not None:
        return _M1_NPC_NAMES
    _names: dict[str, str] = {}
    try:
        import json as _json

        from app.services.npc.npc_loader import _CONFIG_NPC_ROOT

        for _f in (_CONFIG_NPC_ROOT / "individuals").glob("*.json"):
            try:
                _d = _json.loads(_f.read_text(encoding="utf-8-sig"))
            except Exception as _je:  # повреждённый JSON наблюдаем (L4), не молчит
                print(
                    f"[M1_P3] NPC name registry: skip {_f.name}: {_je}",
                    file=__import__("sys").stderr,
                )
                continue
            _nid = _d.get("id")
            _nm = _d.get("name")
            if _nid and _nm:
                _names[_nid] = str(_nm)
    except Exception as _e:  # noqa: ENIGMA001
        # F821-фикс: модуль без logger; тихий fallback в пустой реестр —
        # резолв деградирует до UNKNOWN (легален по N2), без шума в import-слой
        import sys as _sys

        print(f"[M1_P3] NPC name registry degraded: {_e}", file=_sys.stderr)
    _M1_NPC_NAMES = _names
    return _names


def _resolve_npc_by_name(np: str) -> str | None:
    """NPC-резолв над ДАННЫМИ МИРА (не словарь в коде): generic-стем —
    для имён len>=4 усечение последней буквы («Люся»->«люс» ⊂ «люсе»);
    короткие — полное имя. Плюс npc_id-подстрока (латинская адресация,
    прецедент FT-1 :647). Падеже-устойчиво; детерминировано; без LLM."""
    _low = np.lower()
    for _npc_id, _name in _npc_display_names().items():
        _n = _name.lower().strip()
        if _n and (_n in _low or (len(_n) >= 4 and _n[:-1] in _low)):
            return _npc_id
        if _npc_id.lower() in _low:
            return _npc_id
    return None


def _resolve_canon_topic(np: str) -> str | None:
    """Тема канона: topics-поля секретов. Матч — усечение хвоста NP до
    основы («подвале» содержит «подвал» -> тема «подвал»). Тема — индекс
    предмета, НЕ триггер (I4), НЕ discovery (ASKING != DISCOVERING).
    Первый матч по порядку канона — детерминировано."""
    from app.services.npc import npc_loader as _nl

    _truth = _nl._canon_truth_state()
    if not _truth or not _truth.secrets:
        return None
    _low = np.lower()
    for _sec in _truth.secrets.values():
        for _topic in getattr(_sec, "topics", ()) or ():
            if not _topic:
                continue
            _t = _topic.lower()
            if _t in _low:
                return cast(str, _sec.secret_id)
    return None


class IntentCompressor:
    """Слой 1: Сжатие языка в IntentSemanticField."""

    def __init__(self, llm_client: LLMCompressorClient):
        self._llm_client = llm_client

    async def compress(
        self, raw_text: str, scene_context: Dict[str, Any], dialogue_session: Optional[DialogueSession] = None
    ) -> IntentSemanticField:
        fast_result = self._fast_path_parse(raw_text, dialogue_session)
        if fast_result is None:
            return await self._slow_path_parse(raw_text, scene_context, dialogue_session)
        # Reconciler v0 (вердикт Мастера): fast-path = предварительное предложение,
        # не вето. Неполный физический акт → LLM enrichment пустых полей.
        if not self._fast_incomplete(fast_result, scene_context):
            return fast_result
        try:
            _llm = await self._llm_client.compress_intent(raw_text, scene_context, dialogue_session)
        except Exception as _e:
            print(f"[RECONCILE] llm EXC {type(_e).__name__}: fast остаётся")
            return fast_result
        if _llm is None:
            print("[RECONCILE] llm None: fast остаётся")
            return fast_result
        return self._enrich(fast_result, _llm, scene_context)

    def _scene_npc_ids(self, scene_context: Any) -> set:
        """Канонические id сцены — проверка резолва сущностей."""
        if not isinstance(scene_context, dict):
            return set()
        return {str(k).lower() for k in scene_context.get("npc_positions", {})}

    def _fast_incomplete(self, fast: IntentSemanticField, scene_context: Any) -> bool:
        """Критерии полноты v0 (вердикт): физическое действие несёт зону,
        proposition (если есть) опирается на резолвнутую сущность."""
        if fast.action not in (ActionType.ATTACK, ActionType.THREATEN, ActionType.STEAL):
            return False
        if fast.target_zone == TargetZone.UNDEFINED and not fast.zone_raw:
            return True
        if fast.proposition is not None:
            _obj = str(fast.proposition.object_id or "").lower()
            if not _obj or _obj not in self._scene_npc_ids(scene_context):
                return True
        return False

    def _enrich(
        self, fast: IntentSemanticField, llm: Dict[str, Any], scene_context: Any
    ) -> IntentSemanticField:
        """Enrichment ТОЛЬКО пустых полей fast; перезапись запрещена (вердикт).
        Конфликты — телеметрия [RECONCILE] CONFLICT (вход SCR/M3), арбитраж —
        следующий уровень."""
        _u: Dict[str, Any] = {}
        _ids = self._scene_npc_ids(scene_context)

        # 1. Зона (доктрина §6: точность зоны = выбор последствий игроком)
        _lz = normalize_zone(llm.get("target_zone"))
        if _lz is not None and fast.target_zone == TargetZone.UNDEFINED and not fast.zone_raw:
            _u["zone_raw"] = str(llm.get("target_zone")).upper()
            _u["target_zone"] = _lz
        # 2. Прочие пустые поля
        if fast.tool_reference is None and llm.get("tool_reference"):
            _u["tool_reference"] = llm["tool_reference"]
        if fast.condition is None and llm.get("condition"):
            _u["condition"] = llm["condition"]
        if fast.addressee is None and llm.get("addressee"):
            _u["addressee"] = llm["addressee"]
        if fast.target is None and llm.get("target"):
            _u["target"] = llm["target"]
        # 3. R4: proposition с нерезолвнутой сущностью. Вход дан критерием
        # полноты вердикта («proposition содержит нерезолвленную сущность»
        # = incomplete). LLM подтверждает → замена; иначе → None.
        if fast.proposition is not None:
            _obj = str(fast.proposition.object_id or "").lower()
            if _obj not in _ids:
                _lp = llm.get("proposition")
                if isinstance(_lp, dict) and _lp.get("subject_id") and _lp.get("object_id"):
                    try:
                        _u["proposition"] = Proposition(
                            subject_id=str(_lp["subject_id"]),
                            predicate=Predicate(str(_lp.get("predicate", "asserts"))),
                            object_id=str(_lp["object_id"]),
                            polarity=bool(_lp.get("polarity", True)),
                        )
                    except ValueError as _p_err:
                        logger.debug(f"[RECONCILE] LLM proposition не парсится: {_p_err}")
                        _u["proposition"] = None
                else:
                    _u["proposition"] = None
                print(f"[RECONCILE] proposition raw-entity {_obj!r} снята/заменена (LLM)")
        # 4. Конфликты — только телеметрия, без перезаписи (v0)
        if fast.target and llm.get("target") and str(llm["target"]).lower() != str(fast.target).lower():
            print(f"[RECONCILE] CONFLICT target: fast={fast.target!r} llm={llm['target']!r} (v0: fast)")
        if _u:
            print(f"[RECONCILE] enriched={sorted(_u)} (пустые поля fast заполнены)")
        return fast.model_copy(update=_u)

    def _lemmatize(self, text: str) -> set:
        """Разбивает текст на токены и приводит к начальной форме (лемме)."""
        if not PYMORPHY_AVAILABLE:
            return set(text.lower().split())
        assert MORPH is not None  # Удовлетворяет Pylance (MORPH не None, если PYMORPHY_AVAILABLE)
        tokens = re.findall(r"[а-яА-ЯёЁa-zA-Z0-9]+", text.lower())
        lemmas = set()
        for token in tokens:
            parsed = MORPH.parse(token)
            if parsed:
                lemmas.add(parsed[0].normal_form)
            else:
                lemmas.add(token)
        return lemmas

    def _fast_path_parse(self, raw_text: str, dialogue_session: Optional[DialogueSession] = None) -> Optional[IntentSemanticField]:
        lemmas = self._lemmatize(raw_text)

        # S200: Context-sensitive Fast Path. Если игрок пишет "продолжай", "ну?", "и?"
        # и есть активная сессия диалога, это CONTINUE. Используем леммы (pymorphy3).
        # R8 (вердикт Мастера): одиночные «и»/«так»/«давать» перехватывали
        # приказы ("Подойди и поговори" → CONTINUE) при живой сессии диалога.
        # Остаются только явные маркеры продолжения.
        _continue_indicators = {"продолжать", "ну"}
        if dialogue_session and not dialogue_session.is_empty and not lemmas.isdisjoint(_continue_indicators):
            return IntentSemanticField(
                action=ActionType.DIALOGUE,
                speech_act=SpeechAct.CONTINUE,
                conversation_continuation="CONTINUE",
                dialogue_thread=dialogue_session.thread_id,
                raw_text=raw_text,
                confidence=ConfidenceVector(action=0.9, parse=1.0, target=0.8, emotion=0.5),
                ambiguity=SemanticAmbiguity.CLEAR,
            )

        matched_action = None
        for action_type, action_lemmas in _ACTION_LEMMAS.items():
            if not lemmas.isdisjoint(action_lemmas):
                matched_action = action_type
                break

        if not matched_action:
            return None

        # M1/P3: ASK-контур. QUESTION-акт + предметная ось SubjectRef.
        # Инварианты Мастера: акт независим от резолва (N2); детерминировано;
        # LLM-independent; ASKING != DISCOVERING (никаких disclosure-решений).
        if matched_action is ActionType.DIALOGUE and _is_question(lemmas, raw_text):
            _subject = extract_subject(raw_text)
            return IntentSemanticField(
                action=ActionType.DIALOGUE,
                speech_act=SpeechAct.QUESTION,
                subject_kind=_subject.kind.value,
                subject_id=_subject.subject_id,
                subject_hint=_subject.subject_hint,
                raw_text=raw_text,
                confidence=ConfidenceVector(action=0.85, parse=0.9, target=0.6, emotion=0.3),
                ambiguity=SemanticAmbiguity.CLEAR,
            )

        physical = 0.4
        emotional = 0.1
        if not lemmas.isdisjoint(_INTENSITY_LEMMAS["high"]):
            physical = 0.9
            emotional = 0.6
        elif not lemmas.isdisjoint(_INTENSITY_LEMMAS["low"]):
            physical = 0.2

        # Извлечение цели: ищем строго существительное (NOUN), игнорируя местоимения (мне/тебя)
        target_ref = None
        if PYMORPHY_AVAILABLE:
            tokens_raw = re.findall(r"[а-яА-ЯёЁa-zA-Z0-9]+", raw_text)
            # Ищем NOUN с конца строки: в русском цель обычно идёт после глагола ("Подойти к Люсе")
            for token in reversed(tokens_raw):
                parsed = MORPH.parse(token.lower())
                # NOUN = существительное. Исключаем глаголы-существительные (например, "удар")
                if (
                    parsed
                    and parsed[0].tag.POS == "NOUN"
                    and parsed[0].normal_form not in _ACTION_LEMMAS_FLAT
                    and parsed[0].normal_form != "раз" # Исключаем "Еще раз!"
                ):
                    target_ref = (
                        token.lower()
                    )  # Нормализуем в нижний регистр для fuzzy matching
                    break

            # GAP11 FIX: Если NOUN не найден, но есть наречия/местоимения 1-го лица -> цель "player"
            if not target_ref:
                _player_indicators = {"сюда", "ко", "мне", "меня", "нас", "нами"}
                if not lemmas.isdisjoint(_player_indicators):
                    target_ref = "player"

        # ADR-035 FIX: Fast Path обязан генерировать вектор эмоций, иначе Труба Воли мертва
        _semantic = EmotionalVector()  # дефолт
        _social_intent = SocialIntent.NEUTRAL

        if matched_action == ActionType.ATTACK:
            _semantic = EmotionalVector(aggression=0.8, confidence=0.8)
            _social_intent = SocialIntent.INTIMIDATE
        elif matched_action == ActionType.THREATEN:
            _semantic = EmotionalVector(aggression=0.5, fear=0.3, confidence=0.7)
            _social_intent = SocialIntent.OBTAIN_COMPLIANCE
        elif matched_action == ActionType.PERSUADE:
            _semantic = EmotionalVector(confidence=0.7)
            _social_intent = SocialIntent.OBTAIN_COOPERATION
        elif matched_action == ActionType.FLIRT:
            _semantic = EmotionalVector(confidence=0.6)
            _social_intent = SocialIntent.FLIRT
        elif matched_action == ActionType.MOVE:
            _semantic = EmotionalVector(confidence=0.6)

        # S202: Генерируем Proposition для ATTACK и THREATEN (атака = факт "X атаковал Y")
        _proposition = None
        if matched_action in (ActionType.ATTACK, ActionType.THREATEN) and target_ref:
            _proposition = Proposition(
                subject_id="player",
                predicate=Predicate.ATTACKED,
                object_id=target_ref,
                polarity=True
            )

        # ADR-O-315: Fast path по умолчанию считает актора игроком ("я"),
        # если в тексте нет явного указания на 3-е лицо ("пусть торнин уйдёт").
        _actor_ref = "player"
        _third_person_indicators = {"он", "она", "оно", "они", "пусть"}

        # S97 FIX: Обработка прямых обращений ("Торнин, отойди к двери")
        # Если текст содержит запятую и первое слово — существительное, это обращение к NPC.
        if "," in raw_text:
            tokens_raw = re.findall(r"[а-яА-ЯёЁa-zA-Z0-9]+", raw_text)
            if tokens_raw:
                first_token = tokens_raw[0]
                if PYMORPHY_AVAILABLE:
                    parsed = MORPH.parse(first_token.lower())
                    if parsed and parsed[0].tag.POS == "NOUN":
                        # Первое слово — имя/существительное, значит актор — этот NPC
                        _actor_ref = first_token.lower()

        if not lemmas.isdisjoint(_third_person_indicators):
            _actor_ref = target_ref if target_ref else _actor_ref

        return IntentSemanticField(
            action=matched_action,
            actor=_actor_ref,
            target=target_ref,
            proposition=_proposition,
            social_intent=_social_intent,
            raw_text=raw_text,
            physical_force=physical,
            emotional_charge=emotional,
            semantic=_semantic,  # ИНЪЕКЦИЯ ЖИВОГО ВЕКТОРА
            confidence=ConfidenceVector(
                action=0.9, parse=1.0, target=0.8 if target_ref else 0.3, emotion=0.5
            ),
            ambiguity=SemanticAmbiguity.PARTIAL,
        )

    async def _slow_path_parse(
        self, raw_text: str, scene_context: Dict[str, Any], dialogue_session: Optional[DialogueSession] = None
    ) -> IntentSemanticField:
        llm_response = await self._llm_client.compress_intent(raw_text, scene_context, dialogue_session)
        # [DIAG-LLM] временный зонд G-исследования: жив ли slow-path и что вернул LLM.
        print(f"[DIAG-LLM] slow-path: {'None (LLM мертва)' if llm_response is None else repr(str(llm_response)[:400])}")

        if llm_response is None:
            # S97 FIX: Fallback если LLM недоступна (502 Bad Gateway) — пытаемся извлечь актора локально
            _fast_result = self._fast_path_parse(raw_text, dialogue_session)
            if _fast_result:
                return _fast_result

            return IntentSemanticField(
                action=ActionType.UNCERTAIN,
                raw_text=raw_text,
                confidence=ConfidenceVector(
                    parse=0.1, target=0.0, emotion=0.0, action=0.1
                ),
                ambiguity=SemanticAmbiguity.AMBIGUOUS,
            )

        try:
            # S199/S200/S203: Fault-tolerant parsing. LLM может возвращать неизвестные значения.
            from enum import Enum
            from typing import Any, Optional, Type, TypeVar
            _E = TypeVar("_E", bound=Enum)

            def _safe_enum(enum_cls: Type[_E], val: Optional[Any], default: Optional[_E] = None) -> Optional[_E]:
                if not val: return default
                if not isinstance(val, str):
                    val = str(val)
                try:
                    return enum_cls(val)
                except ValueError:
                    # Маппинг частых галлюцинаций
                    if enum_cls is ActionType:
                        if val.upper() == "HELP": return ActionType.GIVE  # type: ignore
                        if val.upper() in ("ASSERT", "ASSERTS"): return ActionType.DIALOGUE  # type: ignore
                    if enum_cls is TargetZone:
                        # №7-a (вердикт Мастера): нормализация синонимов частей тела
                        # к ближайшей канонической зоне. EYES→HEAD — сознательная
                        # потеря точности («левый глаз» ≠ «голова»); восстановление
                        # анатомической детализации — будущая модель зон (CognitionContext),
                        # сегодня недостижима (IntentParametersDTO не несёт zone).
                        _tz_syn = {
                            "EYES": "HEAD", "EYE": "HEAD",
                            "EYE_LEFT": "HEAD", "EYE_RIGHT": "HEAD",
                            "NOSE": "HEAD",
                        }
                        if val and str(val).upper() in _tz_syn:
                            return TargetZone[_tz_syn[str(val).upper()]]  # type: ignore
                        return TargetZone.UNDEFINED  # type: ignore
                    if enum_cls is SocialIntent:
                        if val == "clarify": return SocialIntent.NEUTRAL  # type: ignore
                    return default

            _prop_data = llm_response.get("proposition")
            _proposition = None
            if _prop_data and isinstance(_prop_data, dict):
                _pred = _safe_enum(Predicate, _prop_data.get("predicate", "asserts"), Predicate.ASSERTS) or Predicate.ASSERTS
                _proposition = Proposition(
                    subject_id=_prop_data.get("subject_id", ""),
                    predicate=_pred,
                    object_id=_prop_data.get("object_id", ""),
                    polarity=_prop_data.get("polarity", True)
                )

            _speech_act_val = llm_response.get("speech_act")
            _speech_act = _safe_enum(SpeechAct, _speech_act_val) if _speech_act_val else None

            _social_intent_val = llm_response.get("social_intent")
            _social_intent = _safe_enum(SocialIntent, _social_intent_val, SocialIntent.NEUTRAL) if _social_intent_val else None

            _action_val = llm_response.get("action", llm_response.get("action_type", ActionType.UNCERTAIN))
            _action = _safe_enum(ActionType, _action_val, ActionType.UNCERTAIN)

            _tz_val = llm_response.get("target_zone", TargetZone.UNDEFINED.value)
            _target_zone = _safe_enum(TargetZone, _tz_val, TargetZone.UNDEFINED)
            # zone_raw: сырая зона ДО нормализации — латеральность не гибнет
            # Доктрина §7: UNDEFINED = «зоны нет» → None (≠ сырая латеральность)
            _zone_raw = str(_tz_val).upper() if _tz_val and str(_tz_val).upper() != "UNDEFINED" else None

            return IntentSemanticField(
                action=_action,
                actor=llm_response.get("actor", llm_response.get("actor_reference")),
                target=llm_response.get("target", llm_response.get("target_reference")),
                speech_act=_speech_act,
                proposition=_proposition,
                social_intent=_social_intent,
                addressee=llm_response.get("addressee"),
                requested_outcome=llm_response.get("requested_outcome"),
                offered_outcome=llm_response.get("offered_outcome"),
                condition=llm_response.get("condition"),
                conversation_continuation=llm_response.get("conversation_continuation"),
                dialogue_thread=dialogue_session.thread_id if dialogue_session else None,
                target_zone=_target_zone,
                zone_raw=_zone_raw,
                physical_force=float(llm_response.get("physical_force") or 0.5),
                emotional_charge=float(llm_response.get("emotional_charge") or 0.5),
                social_pressure=float(llm_response.get("social_pressure") or 0.0),
                tool_reference=llm_response.get("tool_reference"),
                semantic=EmotionalVector(**(llm_response.get("semantic") or {})),
                raw_text=raw_text,
                confidence=ConfidenceVector(
                    parse=0.8, target=0.6, emotion=0.7, action=0.8
                ),
            )
        except Exception as _parse_err:
            import logging

            _logger = logging.getLogger(__name__)
            _logger.warning(
                f"[INTENT_COMPRESSOR] slow_path_parse failed: "
                f"{type(_parse_err).__name__}: {_parse_err}. "
                f"Raw LLM response: {llm_response}"
            )
            return IntentSemanticField(
                action=ActionType.UNCERTAIN,
                raw_text=raw_text,
                confidence=ConfidenceVector(
                    parse=0.3, target=0.1, emotion=0.1, action=0.3
                ),
                ambiguity=SemanticAmbiguity.AMBIGUOUS,
            )
