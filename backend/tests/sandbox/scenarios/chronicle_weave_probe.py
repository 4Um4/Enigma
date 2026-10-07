"""CCH-2.5 приёмочный проб: плетение авторских хроник (ADR-O-422).

Корпус Мастера (Люся + Торнин, verbatim) → декомпозиция живым LLM →
ConsistencyService.check → отчёт. Гейт: механизм сверки (финал склеек — автор, CCH-3):
ручного списка архитектора. Черновики сохраняются в saves/silver_wolf/chronicle_drafts/.
Итог-строка: 'Итог: GREEN=N RED=M' (§3.12).
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from app.core.config import BASE_DIR, settings
from app.domain.chronicle import (
    ChronicleDocument,
    ChronicleEntry,
    EntityRef,
    EntityRefKind,
    EntryProvenance,
    make_entry_id,
)
from app.services.chronicle.biography_decomposer import BiographyDecomposer
from app.services.chronicle.chronicle_store import ChronicleStore
from app.services.chronicle.consistency_service import (
    K_CONTRADICTION,
    K_GAP,
    K_INFO,
    K_MERGE_CANDIDATE,
    K_QUESTION,
    CanonicalRegistry,
    ConsistencyService,
)

CAMPAIGN = "silver_wolf"
GAME_START_AGES = {"maid_lusya": 14, "tavern_keeper_tornin": 45}

# ── Авторский корпус (verbatim Мастера; сегментация по строкам смысла) ──────

FRAGMENTS: dict[str, list[str]] = {
    "maid_lusya": [
        "В возрасте 5 лет семью убили бандиты",
        (
            "Примерно в тоже время её подобрала Гильдия воров. Их отношение к ней нельзя "
            "назвать доброжелательными, но так как они единственные кто вообще хоть как-то "
            "ей помогал много отношения она и не знала. так прошло ещё 4 года её жизни."
        ),
        "В возрасте 9 лет не отправили к Торнину в Трактир, навязав её ему.",
        (
            "Торнин относился к ней как к неудобной работнице, которую ещё и надо было "
            "кормить, и прекрасно осознавал, что её приставили к нему не просто так…"
        ),
        "Торнин ударил её за разбитую кружку",
        "После этого регулярно после того как Торнин напивался он избивал её переодически",
        (
            "Она помнит что Гильдия отправила её следить за тайным ходом в таверне и за "
            "Торнином, и это успокаивает её, даже при том что её не защищают от избиений "
            "трактирщиком."
        ),
        (
            "В 11 лет она впервые была изнасилована кузнецом Ормом, под угрозами и денежной "
            "оплатой кузнец потребовал хранить этот факт в секрете от всех, за его хорошее "
            "отношение к ней."
        ),
        (
            "Примерно в 12 лет стражник Борко остался в туалете на кухне и застал сцену "
            "секса Рома и Люси, но не остановил кузнеца, а открыл в себе наклонности "
            "наблюдения и мастурбации за насилием. Люся не знает об этом пункте."
        ),
        (
            "Из-за пристального внимания к ней со стороны стражника Борко вне контекста "
            "насилия, Люся восприняла как искренню доброжелательность по отношению к себе. "
            "Борко был относительно молод и красив по сравнению с окружающими, а также его "
            "высокое социальное положение позволило Люсе влюбиться в него. Так что с 12 лет "
            "она влюблена в стражника."
        ),
        (
            "Сейчас к моменту игры ей 14, и единственное о чем она мечтает это сбежать от "
            "всех проблем на юг, но не решается на это потому что понимает что Гильдия с её "
            "связями быстро найдет её и \"накажет\" за такие выходки."
        ),
        (
            "Так что от части её второй план выслужиться перед гильдией и попасть в лучшие "
            "условия, она даже предполагает что таверну могут доверить ей после смерти Торнина"
        ),
        (
            "И сейчас когда с недавнего времени постоянным посетителем таверны стал агент "
            "гильдии воров Тень, который сказал ей что он здесь ради \"большого дела\" в "
            "котором возможно она будет задействована, заставляет её думать о том что это "
            "может стать её возможностью улучшить свою текущую жизнь. И она меньше думает о "
            "побеге и больше ждёт приказа от гильдии, она готова на всё ради этого шанса, но "
            "надеется что это не навредит её возлюбленному стражнику Борко."
        ),
        (
            "К моменту игры она совершенно не помнит кем были её родители и были ли у неё "
            "иные родственники, она даже не помнит откуда она. Про жизнь в подземных "
            "убежищах гильдии воров она помнит смутно, но оценивает что тогда хотя её жизнь "
            "была и менее насыщена и более пуста, но при этом она была менее болезненна, так "
            "что текущий этап её жизни она ощущает как миссию дарованную ей организацией "
            "через которую она должна доказать свою полезность, чтобы ей предоставили лучшие "
            "условия существования."
        ),
    ],
    "tavern_keeper_tornin": [
        "Хозяин таверны",
        "Бывший солдат, был отстранён от службы из-за травмы ноги - прихрамывать на левую ногу",
        "На момент игры ему уже 45 лет.",
        (
            "В 28 лет получил травму ноги упав вместе с лестницей у крепостной стены при "
            "штурме крепости"
        ),
        (
            "Тогда же из-за старого разговора с товарищами решил купить таверну - они шутили "
            "во время службы что приходили бы к нему выпить в ней."
        ),
        (
            "Но уже два года спустя он понял что таверна не приносила ему достаточного дохода "
            "на её содержание, и после этого он связался с гильдией воров."
        ),
        (
            "Они выделили ему неприличную сумму денег за договоренность построить подземный "
            "лаз в его трактире и его молчание об этом"
        ),
        (
            "До 32 лет всё шло относительно хорошо, но старые его сослуживцы постепенно "
            "перестали к нему приходить. Новые дружественные связи он не завел, не считая "
            "собственных посетителей."
        ),
        (
            "В то же время Гильдия развернула ситуацию на 180°, ему стали угрожать и "
            "контролировать его жизнь, и начали требовать вернуть с процентами всё то что "
            "когда то дали ему, а в ином случае его просто убьют."
        ),
        (
            "Вся эта ситуация привела к его алкоголизму, Торнин всё больше начал спиваться и "
            "это ещё больше отпугнуло посетителей от его Трактира, постепенно его мечта "
            "стала пользоваться статусом притона и злачного места, куда лучше нормальным "
            "людям не заходить."
        ),
        (
            "В 40 лет Гильдия отправила к нему служанку Люсю, ему велели позаботиться о "
            "девочке, предоставить кров и работу, раз он не может в полной мере выплачивать "
            "свои долги"
        ),
        (
            "Но с приходом девочки это ещё сильнее ударило по его финансам, и понимание что "
            "скорее всего её прислали следить за тем не припрятал ли он чего от гильдии его "
            "отношение к ней было крайне недоброжелательным."
        ),
        (
            "Стресс доканал его однажды в пьяной драке не далеко от таверны он получил шрам "
            "на щеке и убил двоих зарезав кухонным ножом. После этого когда он вернулся в "
            "таверну, он увидел что Люся разбила кружку - он посчитал это недобрым знаком и "
            "что скоро стража придет за ним и жизнь его будет кончена. Он не просто избил "
            "Люсю, в этот вечер, но и долго пинал её ногами, а потом выкинул на ее кровать "
            "как мешок с картофелем и сам вырубился на своей кровати"
        ),
        (
            "На следующий день ничего не произошло, как будто ничего и не было, только Люся "
            "ещё неделю не вставала с кровати."
        ),
        (
            "Гильдия сказала что его долг теперь возрос ещё больше, и что если девочка умрёт "
            "это будет считаться нападением на саму гильдию с его стороны. Торнин неделю сам "
            "кормил и выхаживал, он понимал что Гильдия надавила на стражу, а значит его "
            "жизнь ещё меньше стала принадлежать ему."
        ),
        "Год назад до событий игры Торнин попросил кузнеца Лома выковать ему тайно полуторный меч.",
        (
            "Торнин на грани, он собирается убить Люсю так как видит на данный момент времени "
            "её как источник его бед, а вместе с ней как можно большее число членов гильдии "
            "прежде чем его самого убьют."
        ),
        (
            "Но где-то внутри себя он понимает что это самообман, и даже когда меч будет "
            "выкован он побоится воспользоваться им, уйти он не может и ему остаётся только "
            "работать, пить и выплачивать долги. Но теперь этот меч стал его новой проблемой "
            "если им не воспользоваться то нужно как-то избавиться и от него, ведь понятно "
            "что если Гильдия выяснит что заказ на меч от Торнина - то от него незамедлительно "
            "избавятся."
        ),
        (
            "С Ормом они старые собутыльники и товарищи, но доверия Они не стоит. Все "
            "остальные для него клиенты. А Борко продажный стражник который ещё более "
            "подозрительный чем Люся, но вне контекста Гильдии воров, каждый несёт свою роль "
            "и поэтому при возникновении драк или спорных случаев, Торнин сразу же обращается "
            "к Борко, тем более они оба связаны с гильдией"
        ),
    ],
}


def _llm_alive() -> bool:
    import urllib.error
    import urllib.request

    try:
        urllib.request.urlopen(settings.llama_cpp_server_url.replace("/v1", "") + "/health", timeout=3)
        return True
    except (urllib.error.URLError, OSError):
        return False


def _ensure_llm() -> bool:
    """Паттерн chronicle_decompose_probe: сервер поднимается в ЭТОМ процессе."""
    if _llm_alive():
        return True
    _probe = Path(__file__).resolve()
    repo_root = None
    for cand in _probe.parents:
        if (cand / "scripts" / "llm_server_manager.py").is_file():
            repo_root = cand
            break
    if repo_root is None:
        print("[RED] корень репо не найден")
        return False
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from scripts.llm_server_manager import start_llama_server

    print("[LLM_MANAGER] health refused → поднимаю сервер менеджером проекта...")
    return bool(start_llama_server())


def build_registry() -> CanonicalRegistry:
    """Снимок канона: production-лоадер для архетипов/имён + файл секретов."""
    alias: dict[str, str] = {}
    archetype: dict[str, str] = {}
    try:
        from app.services.npc.npc_loader import load_npcs_merged

        npcs = load_npcs_merged()
        for raw in npcs:
            npc_id = str(raw["id"])
            archetype[npc_id] = str(raw.get("_archetype") or raw.get("archetype") or "commoner")
            forms = [str(raw.get("name") or "")]
            nf = raw.get("name_forms")
            if isinstance(nf, list):
                forms.extend(str(x) for x in nf)
            elif isinstance(nf, dict):
                forms.extend(str(v) for v in nf.values())
            for f in forms:
                if f.strip():
                    alias[f.strip().lower()] = npc_id
    except Exception as e:  # L4: причина видима; фолбэк на сырые файлы
        print(f"[WARN] load_npcs_merged недоступен ({e}) — читаю individuals напрямую")
        for path in sorted((BASE_DIR / "config" / "npc" / "individuals").glob("*.json")):
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
            npc_id = str(raw["id"])
            archetype[npc_id] = str(raw.get("_archetype") or raw.get("archetype") or "commoner")
            forms = [str(raw.get("name") or "")]
            nf = raw.get("name_forms")
            if isinstance(nf, list):
                forms.extend(str(x) for x in nf)
            for f in forms:
                if f.strip():
                    alias[f.strip().lower()] = npc_id

    secret_known: dict[str, frozenset] = {}
    ts_path = BASE_DIR / "config" / "canon" / "truth_state_tavern.json"
    if ts_path.is_file():
        ts = json.loads(ts_path.read_text(encoding="utf-8-sig"))
        for s in ts.get("secrets", []):
            holders = set(s.get("initial_holders") or []) | set(s.get("participants") or [])
            secret_known[str(s.get("secret_id"))] = frozenset(holders)

    reg = CanonicalRegistry(alias_to_npc=alias, archetype_of=archetype, secret_known_by=secret_known)
    print(f"[REGISTRY] alias={len(alias)} archetype={archetype}")
    return reg


def main() -> int:
    green = red = 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal green, red
        if cond:
            green += 1
            print(f"[GREEN] {name}")
        else:
            red += 1
            print(f"[RED] {name} :: {detail}")

    if not _ensure_llm():
        print("Итог: GREEN=0 RED=1")
        return 1
    from app.services.llm.router import initialize_router

    initialize_router()
    print("[PROBE] ModelPool инициализирован (initialize_router, прод-прецедент)")

    registry = build_registry()
    decomposer = BiographyDecomposer()
    store = ChronicleStore(
        canonical_dir=BASE_DIR / "config" / "npc" / "chronicles",
        drafts_root=BASE_DIR / "saves",
    )

    docs = []
    frag_stats = {"ok": 0, "fail": 0}
    for npc, frags in FRAGMENTS.items():
        cid = f"chronicle_{npc}"
        entries = []
        for i, frag in enumerate(frags):
            anchors = BiographyDecomposer.extract_age_anchors(frag)
            res = asyncio.run(decomposer.decompose(cid, i, frag))
            kinds = ",".join(it.kind.value for it in res.items) if res.ok else "-"
            mark = "ok" if res.ok else f"FAIL:{(res.error or '')[:80]}"
            print(f"[FRAG {npc} {i + 1}/{len(frags)}] anchors={anchors} {mark} items=[{kinds}]")
            frag_stats["ok" if res.ok else "fail"] += 1
            if not res.ok:
                continue
            for k, item in enumerate(res.items):
                raw_age = item.draft_payload.get("age")
                age = raw_age if isinstance(raw_age, int) else (anchors[0] if anchors else None)
                hint = (
                    item.draft_payload.get("target_hint")
                    or item.draft_payload.get("observed_hint")
                    or item.draft_payload.get("name_hint")
                )
                obj = None
                if isinstance(hint, str) and hint.strip():
                    h = hint.strip()
                    # Мусор-hint'ы LLM (местоимения/абстракции) не становятся
                    # сущностями — вопрос канонизации им не нужен (калибровка S336)
                    if not any(w in h.lower() for w in ("она ", "он ", "улучшение", "таверн")):
                        obj = EntityRef(ref_kind=EntityRefKind.UNKNOWN_PERSON, name_hint=h)
                entries.append(
                    ChronicleEntry(
                        entry_id=make_entry_id(cid, i, k),
                        kind=item.kind,
                        subject_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id=npc),
                        historical_age=age,
                        object_id=obj,
                        payload=dict(item.draft_payload),
                        provenance=EntryProvenance.LLM_DRAFT,
                        confidence=item.confidence,
                        open_questions=(item.question,) if item.question is not None else (),
                        ordinal=len(entries),
                    )
                )
        doc = ChronicleDocument(
            chronicle_id=cid,
            npc_ref=npc,
            author_text="\n\n".join(frags),
            entries=tuple(entries),
            game_start_age=GAME_START_AGES.get(npc),
        )
        docs.append(doc)
        print(f"[DOC] {npc}: entries={len(doc.entries)}")

    for doc in docs:
        path = store.save_draft(doc, CAMPAIGN)
        print(f"[DRAFT] сохранён: {path}")

    rep = ConsistencyService().check(docs, registry)
    by_kind: dict[str, list] = {}
    for f in rep.findings:
        by_kind.setdefault(f.kind, []).append(f)
    for kind in (K_CONTRADICTION, K_MERGE_CANDIDATE, K_GAP, K_QUESTION, K_INFO):
        for f in by_kind.get(kind, []):
            print(f"  [{kind}/{f.level}] {f.message}")

    # ── Гейт: ручной список архитектора должен воспроизвестись системой ──────
    # ── Гейт CCH-2.5 финал (S336, вердикт Мастера: вариант A): проверяем
    # МЕХАНИЗМ, не конкретные пары. Кросс-кандидаты у со-локальных хроник
    # («его хроника почти вся про Люсю») легально многочисленны — дедуп/
    # приоритизация и финал склейки = карточки автора в CCH-3 (ADR-O-422:
    # финал склейки — всегда автор). Высокосигнальный маркер: кандидат с
    # ролью guard — доказательство матчинга вторичных участников (не
    # субъектный шум «Люся↔Люся», убитый self-ref-фильтром).
    cross = [f for f in by_kind.get(K_MERGE_CANDIDATE, []) if f.level == "cross"]
    check("cross_candidates_alive>=1", len(cross) >= 1, f"фактически {len(cross)}")
    check(
        "guard_role_candidate (вторичные участники матчатся)",
        any("guard" in f.payload.get("shared_roles", []) for f in cross),
        f"роли={sorted({r for f in cross for r in f.payload.get('shared_roles', [])})}",
    )
    check(
        "fragments_preserved_33",
        frag_stats["ok"] >= 33 and frag_stats["fail"] == 0,
        f"ok={frag_stats['ok']} fail={frag_stats['fail']}",
    )
    check(
        "questions_surfaced>=1",
        len(by_kind.get(K_QUESTION, [])) >= 1,
        f"фактически {len(by_kind.get(K_QUESTION, []))}",
    )
    all_msgs = " || ".join(f.message for f in rep.findings)
    check(
        "info_resolves_tornin_orm_borko",
        all(x in all_msgs for x in ("tavern_keeper_tornin", "blacksmith_orm", "guard_borko")),
        "резолюции известных имён не предложены",
    )
    lusya_gaps = [f for f in by_kind.get(K_GAP, []) if any(r[0] == "maid_lusya" for r in f.doc_refs)]
    check("lusya_gap_windows>=3", len(lusya_gaps) >= 3, f"фактически {len(lusya_gaps)}")
    check(
        "no_contradiction (убеждение без источника легально)",
        len(by_kind.get(K_CONTRADICTION, [])) == 0,
        "лишние CONTRADICTION",
    )

    print(
        "\n[NOTES] Редакторские решения (вне автоматики, к CCH-3): "
        "фрагмент Люси «...Люся не знает об этом пункте» — мировой факт, при канонизации "
        "уходит в хронику Борко/мировой слой, НЕ в её память; «Торнин прекрасно осознавал…» "
        "— его внутреннее состояние, место в его хронике; канон-пополнение: Торнин "
        "Серебряная Луна (фамилия), таверна «Серебряный Волк»."
    )
    print(f"Итог: GREEN={green} RED={red}")
    return 0 if red == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())