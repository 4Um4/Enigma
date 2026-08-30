# backend/app/services/action/player_target_extractor.py

# Текущая реализация в PlayerTargetExtractor очень упрощённая: она устанавливает 0.5 только для целевого NPC при наличии ключевых слов близости, для всех остальных – 3.0, без учёта реальной сцены.
# Для более реалистичной модели нужно использовать координаты из scene_state и обновлять их через LifeEngine или другие движки

# === PLAYER TARGET EXTRACTOR (S.0) ===
# Извлекает цель игрока из текста действия.
# Работает полностью generic — без хардкода имён NPC.
# Использует name_forms из JSON + ролевые ключевые слова из npc_id.
"""
Цель: определить, к кому обращается игрок в своём действии, и какие объекты он может иметь в виду.
Подход:
1. Ищем прямые упоминания NPC по name_forms (приоритет).
2. Если нет прямых упоминаний, ищем ролевые ключевые слова (например, "хозяин" → tavern_keeper).
3. Если есть местоимения (например, "говорю ему") и предыдущая цель в scene_state, используем её (sticky target).
4. Пытаемся разрешить объекты через ObjectResolver.
5. Определяем позицию игрока (на коленях, сидит, стоит и т.д.) по ключевым фразам.
6. Вычисляем расстояния до NPC: приоритет — реальные координаты из scene_state, fallback — лингвистический прокси (ключевые слова близости).
Результат: (target_npc_id, target_npc_name, target_object_id, player_position, player_distances)

TODO: расширить список ролевых ключевых слов и позиций, добавить поддержку множественных целей, улучшить обработку местоимений через лемматизацию глаголов обращения.
TODO: интегрировать с LifeEngine для получения реальных координат NPC и игрока, а также для обновления sticky target на основе диалогов и взаимодействий.
"""

import logging
from typing import Dict, List, Optional, Tuple

from app.services.spatial.spatial_runtime import euclidean_distance

logger = logging.getLogger(__name__)


class PlayerTargetExtractor:
    """S.0 — Определение, к кому обращается игрок."""

    # ── Константы ───────────────────────────────────────────────────────────
    _ROLE_KEYWORDS: Dict[str, List[str]] = {
        "tavern_keeper": [
            "хозяин",
            "трактирщик",
            "бармен",
            "владелец",
            "хозяину",
            "трактирщику",
            "хозяина",
            "бармену",
            "к трактирщику",
            "к хозяину",
            "трактирщика",
            "хозяина трактира",
            "бармена",
            "хозяину заведения",
            "трактирщику за стойкой",
            "владельцу таверны",
            "к бармену",
            "обращаюсь к хозяину",
            "говорю хозяину",
            "спрашиваю трактирщика",
            "попрошу бармена",
            "хозяина попросить",
            "трактирщику на ухо",
            "бармену шепчу",
            "владелец таверны",
        ],
        "innkeeper": [
            "хозяин",
            "трактирщик",
            "хозяйка",
            "хозяину",
            "трактирщику",
            "хозяйке",
            "хозяина",
            "хозяйку",
            "к хозяину",
            "к хозяйке",
            "иннкиперу",
            "хозяйке таверны",
            "хозяину постоялого двора",
            "трактирщице",
            "к трактирщице",
            "барменше",
            "к барменше",
            "говорю хозяйке",
            "спрашиваю хозяйку",
            "попрошу хозяина",
            "хозяйку попросить",
        ],
        "maid": [
            "служанка",
            "официантка",
            "служанке",
            "официантке",
            "служанку",
            "официантку",
            "к служанке",
            "к официантке",
            "служанкой",
            "с официанткой",
            "горничная",
            "горничной",
            "к горничной",
            "официантке за столом",
            "служанке в зале",
            "говорю служанке",
            "шепчу официантке",
            "служанку позвать",
        ],
        "guard": [
            "стражник",
            "охранник",
            "страж",
            "стражнику",
            "охраннику",
            "стражу",
            "стражника",
            "охранника",
            "к стражнику",
            "к охраннику",
            "стражем",
            "с стражем",
            "городской страже",
            "страже у ворот",
            "охраннику у двери",
            "стражникам",
            "к стражникам",
            "говорю стражнику",
            "спрашиваю охранника",
            "попрошу стража",
            "стража попросить",
        ],
        "merchant": [
            "купец",
            "торговец",
            "продавец",
            "купцу",
            "торговцу",
            "продавцу",
            "купца",
            "торговца",
            "продавца",
            "к купцу",
            "к торговцу",
            "к продавцу",
            "лавочник",
            "лавочнику",
            "торговцу в лавке",
            "купчиха",
            "купчихе",
            "к купчихе",
            "продавцу товаров",
            "торговцу зельями",
            "говорю купцу",
            "спрашиваю торговца",
        ],
        "thief": [
            "вор",
            "незнакомец",
            "тень",
            "вору",
            "незнакомцу",
            "тени",
            "вора",
            "незнакомца",
            "тень",
            "к вору",
            "к незнакомцу",
            "к тени",
            "воровка",
            "воровке",
            "тени в углу",
            "незнакомке",
            "к воровке",
            "тёмной фигуре",
            "подозрительному типу",
            "вору в капюшоне",
            "говорить с вором",
            "спрашиваю незнакомца",
        ],
        "priest": [
            "священник",
            "жрец",
            "священнику",
            "жрецу",
            "священника",
            "жреца",
            "к священнику",
            "к жрецу",
            "отец",
            "отцу",
            "батюшка",
            "батюшке",
            "жрица",
            "жрице",
            "священнице",
            "к жрице",
            "жрецу у алтаря",
            "священнику в храме",
            "говорю священнику",
            "шепчу жрецу",
            "спрашиваю батюшку",
        ],
        "blacksmith": [
            "кузнец",
            "кузнецу",
            "кузнеца",
            "к кузнецу",
            "мастер",
            "мастеру",
            "кузнечихе",
            "кузнечиха",
            "кузнецу в кузнице",
            "говорю кузнецу",
            "спрашиваю мастера",
            "попрошу кузнеца",
            "кузнеца попросить",
            "мастеру по металлу",
        ],
        "farmer": [
            "крестьянин",
            "фермер",
            "крестьянину",
            "фермеру",
            "крестьянина",
            "фермера",
            "к крестьянину",
            "к фермеру",
            "крестьянка",
            "крестьянке",
            "фермерше",
            "к крестьянке",
            "крестьянину у поля",
            "фермеру в деревне",
            "говорю крестьянину",
            "спрашиваю фермера",
        ],
        "noble": [
            "лорд",
            "господин",
            "барон",
            "лорду",
            "господину",
            "барону",
            "лорда",
            "господина",
            "барона",
            "к лорду",
            "к господину",
            "к барону",
            "леди",
            "леди",
            "госпоже",
            "к леди",
            "баронессе",
            "к баронессе",
            "аристократ",
            "аристократу",
            "благородному",
            "к благородному",
            "господину в плаще",
            "говорю лорду",
            "спрашиваю барона",
        ],
        # ── ДОПОЛНИТЕЛЬНЫЕ РОЛИ (расширение +12 новых) ─────────────────────
        "bartender": ["бармен", "барменша", "бармену", "барменше", "к бармену"],
        "waitress": ["официантка", "официантке", "официантку", "к официантке"],
        "healer": ["целитель", "знахарь", "целительнице", "к целителю", "знахарке"],
        "bard": ["бард", "певец", "барду", "певцу", "к барду"],
        "alchemist": ["алхимик", "алхимику", "алхимика", "к алхимику"],
        "mage": ["маг", "волшебник", "магу", "волшебнику", "к магу"],
        "assassin": ["убийца", "ассасин", "убийце", "к убийце"],
        "child": ["ребёнок", "мальчик", "девочка", "ребёнку", "мальчику", "девочке"],
        "old_man": ["старик", "старуха", "старику", "старухе", "к старику"],
        "soldier": ["солдат", "воин", "солдату", "воину", "к солдату"],
        "beggar": ["нищий", "попрошайка", "нищему", "к нищему"],
        "traveler": ["путник", "странник", "путнику", "страннику", "к путнику"],
    }

    # Нормализация gender из NPC JSON → внутренний формат
    _GENDER_NORM: Dict[str, str] = {
        "женский": "female",
        "мужской": "male",
        "female": "female",
        "male": "male",
    }

    # Дескрипторы: lemma → требуемый gender (None = любой).
    # Мэтчится когда name_forms и role_keywords не сработали.
    # "девушка" → любая женщина, не только служанка.
    _DESCRIPTORS: Dict[str, Optional[str]] = {
        "девушка": "female",
        "женщина": "female",
        "девчонка": "female",
        "мужчина": "male",
        "мужик": "male",
        "парень": "male",
        "старик": "male",
        "старуха": "female",
        "старушка": "female",
        "ребёнок": None,
    }

    _PRONOUNS = [
        "говорю ей",
        "говорю ей,",
        "шепчу ей",
        "шепчу ей,",
        "говорю её",
        "говорю ему",
        "шепчу ему",
        "скажи ей",
        "скажу ей",
        "спрошу её",
        "спрошу его",
        "говорю тебе",
        "говорю тебе,",
        "скажу тебе",
        "говорю вам",
        "скажу вам",
        " ей ",
        " её ",
        " ему ",
        "к ней",
        "к нему",
        "с ней",
        "с ним",
        "для неё",
        "для него",
    ]

    _POSITION_PATTERNS: Dict[str, List[str]] = {
        "на коленях": [
            "на колен",
            "встаю на колен",
            "опускаюсь на колен",
            "стою на коленях",
            "опуститься на колени",
            "на коленях перед",
            "падаю на колени",
            "опустился на колени",
            "встать на колени",
        ],
        "сидит": [
            "сажусь",
            "сижу",
            "сел",
            "садись",
            "присаживаюсь",
            "присел",
            "сижу рядом",
            "усаживаюсь",
            "сижу за столом",
            "присаживаюсь к",
            "сел на стул",
            "сижу на лавке",
        ],
        "лежит": [
            "ложусь",
            "лежу",
            "лёг",
            "ложись",
            "прилёг",
            "лежа",
            "лёжа на полу",
            "ложусь на кровать",
            "лежу рядом",
            "прилечь",
            "разлёгся",
        ],
        "стоит": [
            "стою",
            "встаю",
            "встал",
            "встану",
            "стоя",
            "стоять рядом",
            "встать перед",
            "встаю перед",
            "стою напротив",
            "поднимаюсь",
            "встал на ноги",
        ],
        "бежит": [
            "бегу",
            "убегаю",
            "бегу к",
            "подбегаю",
            "подбежал",
            "бегу к тебе",
            "бежать к",
            "прибегаю",
            "убегаю от",
            "бегу за тобой",
        ],
        # +8 новых позиций (расширение)
        "приседает": [
            "приседаю",
            "присел",
            "на корточках",
            "присесть",
            "сижу на корточках",
        ],
        "наклоняется": [
            "наклоняюсь",
            "наклонился",
            "наклоняюсь к",
            "склоняюсь над",
            "наклониться к",
        ],
        "обнимает": [
            "обнимаю",
            "обнял",
            "обнимаю тебя",
            "в обнимку",
            "прижимаюсь",
            "обнять крепко",
        ],
        "целует": [
            "целую",
            "поцеловал",
            "целую тебя",
            "целую в щёку",
            "целую в губы",
            "поцеловать",
        ],
        "касается": [
            "касаюсь",
            "коснулся",
            "прикасаюсь",
            "трогаю",
            "касаюсь руки",
            "гладить",
        ],
        "шепчет": ["шепчу", "шепнул", "шепчу на ухо", "шептать", "шепотом говорю"],
        "смотрит": [
            "смотрю",
            "посмотрел",
            "смотрю на",
            "глядеть в глаза",
            "уставился на",
        ],
        "танцует": [
            "танцую",
            "танцевал",
            "танцевать с",
            "в танце",
            "приглашаю на танец",
        ],
    }

    _PROXIMITY_KEYWORDS = [
        "перед",
        "рядом с",
        "к ",
        "подхожу к",
        "стою перед",
        "обращаюсь к",
        "говорю с",
        "смотрю на",
        "касаюсь",
        "на коленях перед",
        "беру за руку",
        "держу",
        # +120 новых (итого ~130+) — максимально полный список для точного захвата цели
        "подхожу ближе",
        "подхожу к тебе",
        "подбегаю к",
        "подбегаю к тебе",
        "становлюсь рядом",
        "становлюсь перед",
        "встаю рядом с",
        "встаю перед",
        "иду к",
        "иду к тебе",
        "иду к ней",
        "иду к нему",
        "приближаюсь к",
        "приближаюсь к тебе",
        "подхожу вплотную",
        "вплотную к",
        "рядом с тобой",
        "рядом с ней",
        "рядом с ним",
        "возле",
        "возле тебя",
        "возле неё",
        "возле него",
        "около",
        "около тебя",
        "около неё",
        "напротив",
        "напротив тебя",
        "напротив неё",
        "лицом к",
        "лицом к тебе",
        "глаза в глаза",
        "смотрю прямо на",
        "смотрю в глаза",
        "касаюсь руки",
        "беру за руку",
        "держу за руку",
        "трогаю плечо",
        "кладу руку на плечо",
        "обнимаю за талию",
        "прижимаюсь к",
        "прижимаюсь к тебе",
        "шепчу на ухо",
        "шепчу тебе на ухо",
        "говорю на ухо",
        "говорю ей на ухо",
        "говорю ему на ухо",
        "на ухо",
        "на ушко",
        "вплотную к лицу",
        "почти касаясь",
        "касаясь груди",
        "гладить по волосам",
        "гладить по щеке",
        "целовать в щёку",
        "целовать шею",
        "стоять за спиной",
        "за спиной у",
        "за твоей спиной",
        "следую за",
        "иду следом за",
        "преследую",
        "подкрадываюсь к",
        "подкрадываюсь к тебе",
        "сзади",
        "сзади от тебя",
        "сбоку от",
        "сбоку от тебя",
        "слева от",
        "справа от",
        "на расстоянии",
        "совсем близко",
        "очень близко к",
        "прильнуть к",
        "прильнуть к тебе",
        "взять под руку",
        "взять под локоть",
        "вести за руку",
        "тянуть к себе",
        "притянуть к себе",
        "толкнуть к",
        "прижать к стене",
        "прижать к себе",
        "обхватить руками",
        "заключить в объятия",
        "потянуться к",
        "протянуть руку к",
        "дотронуться до",
        "дотронуться до тебя",
        "обращаюсь напрямую",
        "говорю лично",
        "разговариваю только с",
        "только с тобой",
        "только с ней",
        "только с ним",
        "наедине с",
        "наедине с тобой",
        "наедине с ней",
    ]

    # ── Основной метод ───────────────────────────────────────────────────────
    def extract(
        self,
        action_text: str,
        npc_contexts: List[Dict],
        scene_state: Optional[Dict] = None,
    ) -> Tuple[str | None, str | None, str | None, str | None, Dict]:
        """
        Возвращает:
            (target_npc_id, target_npc_name, target_object_id, player_position, player_distances)
        """
        lower = action_text.lower().strip()

        has_only_pronoun = any(p in lower for p in self._PRONOUNS)
        prev_target_id = scene_state.get("player_target_npc") if scene_state else None  # noqa: ENIGMA001
        prev_target_name = (
            scene_state.get("player_target_npc_name") if scene_state else None  # noqa: ENIGMA001
        )

        target_npc_id = target_npc_name = None
        target_object = None
        player_position = None
        player_distances: Dict[str, float] = {}

        # Pronoun shortcut: игрок использует местоимение И есть предыдущая цель
        # → пропускаем поиск по имени/роли, берём sticky target напрямую.
        # Иначе роль-ключевое слово из контекста фразы перехватит цель ложно.
        if has_only_pronoun and prev_target_id:
            target_npc_id = prev_target_id
            target_npc_name = prev_target_name
            for ctx in npc_contexts:
                npc_id = ctx.get("npc_id", "")
                is_proximate = any(kw in lower for kw in self._PROXIMITY_KEYWORDS)
                player_distances[npc_id] = (
                    0.5 if npc_id == target_npc_id and is_proximate else 3.0
                )
            for pos_label, patterns in self._POSITION_PATTERNS.items():
                if any(p in lower for p in patterns):
                    player_position = pos_label
                    break
            return (
                target_npc_id,
                target_npc_name,
                target_object,
                player_position,
                player_distances,
            )

        # 1. Поиск целевого NPC — собираем ВСЕХ кандидатов, выбираем по позиции в тексте
        # Если упоминаются несколько NPC (например "подойти к Люсе и спросить про Торнина"),
        # главная цель = тот, чьё имя ближе к началу фразы (прямое действие).
        _candidates: List[
            Tuple[int, str, str]
        ] = []  # (позиция_в_тексте, npc_id, npc_name)

        # Лемматизация текста один раз — для descriptor-мэтчинга через pymorphy3
        _lemma_to_word: Dict[str, str] = {}
        try:
            import pymorphy3 as _pm3

            if not hasattr(PlayerTargetExtractor, "_morph_analyzer"):
                PlayerTargetExtractor._morph_analyzer = _pm3.MorphAnalyzer()
            _morph = PlayerTargetExtractor._morph_analyzer
            for _w in lower.split():
                _lemma = _morph.parse(_w)[0].normal_form
                if _lemma not in _lemma_to_word:
                    _lemma_to_word[_lemma] = _w
        except Exception as e:
            logger.warning(f"[B5-FIX] silent failure suppressed: {e}")

        for ctx in npc_contexts:
            npc_id = ctx.get("npc_id", "")
            npc_name = ctx.get("npc_name", "")

            # name_forms (приоритет)
            name_forms = [f.lower() for f in ctx.get("name_forms", [])]
            if name_forms:
                for form in name_forms:
                    pos = lower.find(form)
                    if pos != -1:
                        # Прямое обращение: "Привет, Тень" (после запятой или в начале)
                        # Косвенное упоминание: "относишься к Люсе" (перед именем предлог "к")
                        _prefix = lower[max(0, pos - 4) : pos].strip()
                        _PREPOSITIONS = {
                            "к",
                            "про",
                            "о",
                            "об",
                            "у",
                            "с",
                            "из",
                            "от",
                            "для",
                            "до",
                            "без",
                        }
                        _is_indirect = any(
                            _prefix.endswith(f" {p} ") for p in _PREPOSITIONS
                        )
                        if _is_indirect:
                            continue  # не делаем целем из косвенного упоминания
                        logger.debug(
                            f"[S.0 MATCH] name_form '{form}' at pos {pos} → {npc_id}"
                        )
                        _candidates.append((pos, npc_id, npc_name))
                        break

            # Ролевое ключевое слово (если name_forms не сработали)
            if not any(c[1] == npc_id for c in _candidates):
                role = self._get_role_from_id(npc_id)
                if role and any(
                    f" {kw} " in f" {lower} "
                    or lower.startswith(f"{kw} ")
                    or lower.endswith(f" {kw}")
                    or lower == kw
                    for kw in self._ROLE_KEYWORDS.get(role, [])
                ):
                    matched = [
                        kw for kw in self._ROLE_KEYWORDS.get(role, []) if kw in lower
                    ]
                    pos = lower.find(matched[0]) if matched else 999
                    logger.debug(
                        f"[S.0 MATCH] role_kw {matched!r} at pos {pos} via role={role!r} → {npc_id}"
                    )
                    _candidates.append((pos, npc_id, npc_name))

            # Дескриптор по полу/возрасту (если name_forms и role не сработали)
            if not any(c[1] == npc_id for c in _candidates) and _lemma_to_word:
                npc_gender_raw = ctx.get("gender", "")
                npc_gender = self._GENDER_NORM.get(
                    npc_gender_raw, npc_gender_raw.lower()
                )
                if npc_gender:
                    for desc_lemma, req_gender in self._DESCRIPTORS.items():
                        if req_gender is not None and npc_gender != req_gender:
                            continue
                        if desc_lemma in _lemma_to_word:
                            orig_word = _lemma_to_word[desc_lemma]
                            pos = lower.find(orig_word)
                            logger.debug(
                                f"[S.0 MATCH] descriptor '{orig_word}' (lemma={desc_lemma}) gender={npc_gender} → {npc_id}"
                            )
                            _candidates.append((pos, npc_id, npc_name))
                            break

        # Выбираем кандидата с минимальной позицией (ближе к началу = главная цель)
        if _candidates:
            _candidates.sort(key=lambda x: x[0])  # сортировка по позиции
            target_npc_id = _candidates[0][1]
            target_npc_name = _candidates[0][2]
            logger.debug(
                f"[TARGET] Selected {target_npc_name} ({target_npc_id}) from {len(_candidates)} candidates at pos {_candidates[0][0]}"
            )

        # 2. Поиск объекта в SceneState через ObjectResolver (с морфологией)
        try:
            from app.services.action.object_resolver import resolve_object

            found = resolve_object(action_text, scene_state)
            if found:
                target_object = found
        except Exception:
            # Fallback — простой поиск по имени
            objects = (scene_state or {}).get("objects", {})
            for obj_id, obj_data in objects.items():
                raw_name = obj_data.get("name", "")
                obj_name = raw_name.split("#")[0].strip().lower()
                if obj_name and len(obj_name) >= 3 and obj_name in lower:
                    target_object = obj_id
                    break

        # Sticky target через лемматизацию (pymorphy3)
        # Все формы глаголов обращения сводятся к базовой лемме —
        # не зависим от конкретных словоформ.
        try:
            import pymorphy3 as _pm3

            if not hasattr(PlayerTargetExtractor, "_morph_analyzer"):
                PlayerTargetExtractor._morph_analyzer = _pm3.MorphAnalyzer()
            _morph = PlayerTargetExtractor._morph_analyzer
            _ADDRESS_LEMMAS = {
                "говорить",
                "сказать",
                "спросить",
                "шептать",
                "спрашивать",
                "отвечать",
                "обращаться",
                "просить",
                "попросить",
                "молвить",
                "сообщить",
                "сообщать",
                "заявить",
                "заявлять",
                "шепнуть",
                "произнести",
                "произносить",
                "промолвить",
                "добавить",
                "крикнуть",
                "кричать",
                "позвать",
                "звать",
                "велеть",
                "приказать",
                "предложить",
                "предлагать",
                "уточнить",
            }
            has_address_signal = (
                has_only_pronoun
                or any(kw in lower for kw in self._PROXIMITY_KEYWORDS)
                or any(
                    _morph.parse(w)[0].normal_form in _ADDRESS_LEMMAS
                    for w in lower.split()
                    if w
                )
            )
        except Exception:
            # Fallback если pymorphy3 недоступен
            has_address_signal = has_only_pronoun or any(
                kw in lower for kw in self._PROXIMITY_KEYWORDS
            )

        if (
            target_npc_id is None
            and prev_target_id
            and target_object is None
            and has_address_signal
        ):
            target_npc_id = prev_target_id
            target_npc_name = prev_target_name

        # 3. Позиция игрока
        for pos_label, patterns in self._POSITION_PATTERNS.items():
            if any(p in lower for p in patterns):
                player_position = pos_label
                break

        # 4. Расстояния — приоритет: реальные координаты, fallback: лингвистика
        is_proximate = any(kw in lower for kw in self._PROXIMITY_KEYWORDS)
        for ctx in npc_contexts:
            npc_id = ctx.get("npc_id", "")
            player_distances[npc_id] = self._get_distance(
                npc_id=npc_id,
                is_target=(npc_id == target_npc_id),
                is_proximate=is_proximate,
                scene_state=scene_state,
            )

        # Fallback: нет явного таргета в тексте
        # Но если игрок хочет выйти/войти — не ищем ближайшего NPC, цель уже объект (дверь/выход)
        if target_npc_id is None and player_distances and not target_object:
            try:
                from app.services.spatial.spatial_runtime import sound_reach

                _voice_radius = sound_reach(
                    8.0, scene_state or {}
                )  # голос ≈ 8м базовый
            except Exception:
                _voice_radius = 8.0

            # Fallback 1: продолжение диалога — берём предыдущего таргета если в радиусе слышимости
            if prev_target_id:
                _prev_dist = player_distances.get(prev_target_id)
                if _prev_dist is not None and _prev_dist <= _voice_radius:
                    target_npc_id = prev_target_id
                    target_npc_name = prev_target_name
                    logger.debug(
                        f"[TARGET] Sticky dialog: {target_npc_name} ({target_npc_id}) dist={_prev_dist:.1f}"
                    )

            # Fallback 2: нет предыдущего или он вне зоны — берём ближайшего СЛЫШАЩЕГО NPC
            if target_npc_id is None:
                _audible_candidates = {
                    nid: dist
                    for nid, dist in player_distances.items()
                    if dist <= _voice_radius
                }
                if _audible_candidates:
                    _nearest_id = min(_audible_candidates, key=_audible_candidates.get)
                    _nearest_dist = _audible_candidates[_nearest_id]
                    for ctx in npc_contexts:
                        if ctx.get("npc_id") == _nearest_id:
                            target_npc_id = _nearest_id
                            target_npc_name = ctx.get("npc_name", _nearest_id)
                            logger.debug(
                                f"[TARGET] Fallback nearest audible: {target_npc_name} ({target_npc_id}) dist={_nearest_dist:.1f} voice_range={_voice_radius:.1f}"
                            )
                            break

        return (
            target_npc_id,
            target_npc_name,
            target_object,
            player_position,
            player_distances,
        )

    # ── Вспомогательные методы ───────────────────────────────────────────────
    @staticmethod
    def _get_role_from_id(npc_id: str) -> str:
        """Извлекает роль из npc_id: tavern_keeper_tornin → tavern_keeper"""
        parts = npc_id.split("_")
        for length in range(len(parts) - 1, 0, -1):
            candidate = "_".join(parts[:length])
            if candidate in PlayerTargetExtractor._ROLE_KEYWORDS:
                return candidate
        return ""

    @staticmethod
    def _get_distance(
        npc_id: str,
        is_target: bool,
        is_proximate: bool,
        scene_state: Optional[Dict],
    ) -> float:
        """
        Расчёт дистанции игрок → NPC.
        Приоритет 1: реальные координаты из scene_state (когда LifeEngine их заполнит).
        Приоритет 2: лингвистический прокси (proximity keywords).
        """
        if scene_state:
            npc_data = (scene_state.get("npc_positions") or {}).get(npc_id) or {}
            # ADR-048: Игрок читается из единого словаря npc_positions
            player_data = scene_state.get("npc_positions", {}).get("player", {})
            if npc_data and player_data:
                spatial_distance = euclidean_distance(
                    a=npc_data,
                    b=player_data,
                )
                if spatial_distance < 999.0:
                    return spatial_distance

            # legacy R4.2 fallback for raw XY state
            player_pos = scene_state.get("player_position") or {}
            if isinstance(player_pos, dict):
                px, py = player_pos.get("x"), player_pos.get("y")
            else:
                px, py = None, None
            nx, ny = npc_data.get("x"), npc_data.get("y")
            if px is not None and py is not None and nx is not None and ny is not None:
                import math

                return round(math.dist((px, py), (nx, ny)), 2)

        # Fallback: лингвистический прокси
        return 0.5 if (is_target and is_proximate) else 3.0
