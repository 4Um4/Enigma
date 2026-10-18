# path: /project/scripts/fix_confirm_canonize_http.py
# Назначение: BLOCK 9 — данные через живой API (ровно тот маршрут, который
# теперь делает F9): GET draft -> LLM_DRAFT -> AUTHOR_CONFIRMED (confidence
# убрать: domain «AUTHOR_* не хранит confidence — канон не гипотеза»; BLOCK 8
# упёрлся именно в это) -> PUT draft -> POST canonize (серверная валидация
# «Save = Contract»: открытые вопросы без selected_option, dangling и пр.).
# Открытые вопросы считаем заранее — единственный ожидаемый повод для 422.
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import BASE_DIR

BASE = "http://127.0.0.1:8000"
CAMPAIGN = "silver_wolf"
DRAFTS = BASE_DIR / "saves" / CAMPAIGN / "chronicle_drafts"
CANON = BASE_DIR / "config" / "npc" / "chronicles"


def call(method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except Exception:
            return exc.code, {"error": str(exc)}


st, data = call("GET", "/api/chronicle/roster/" + CAMPAIGN)
print("backend roster:", st, "(нужно 200)")
if st != 200:
    print("backend не отвечает — подними сервер и прогони этот скрипт заново")
    sys.exit(0)

npcs = sorted(p.stem for p in DRAFTS.glob("*.json"))
print("черновики:", len(npcs), npcs)
for npc in npcs:
    print("=== %s" % npc)
    st, data = call("GET", "/api/chronicle/%s/%s/draft" % (CAMPAIGN, npc))
    if st != 200 or data.get("status") != "OK":
        print("   GET draft:", st, str(data)[:300])
        continue
    doc = data.get("document") or {}
    entries = doc.get("entries") or []
    confirmed = 0
    unresolved = 0
    for e in entries:
        if e.get("provenance") == "LLM_DRAFT":
            e["provenance"] = "AUTHOR_CONFIRMED"
            e.pop("confidence", None)
            confirmed += 1
        for q in e.get("open_questions") or []:
            if not q.get("selected_option"):
                unresolved += 1
    print("   entries=%d | к подтверждению: %d | открытых вопросов без ответа: %d" % (
        len(entries), confirmed, unresolved))
    if confirmed:
        st, data = call("PUT", "/api/chronicle/%s/%s/draft" % (CAMPAIGN, npc), doc)
        print("   PUT draft:", st, str(data)[:220])
        if st != 200:
            print("   -> PUT не прошёл, canonize пропущен (покажи ответ серверу-агенту)")
            continue
    st, data = call("POST", "/api/chronicle/%s/%s/canonize" % (CAMPAIGN, npc),
                    {"campaign_id": CAMPAIGN})
    print("   POST canonize:", st, json.dumps(data, ensure_ascii=False)[:400])

print()
print("--- канон-файлы ПОСЛЕ:")
for p in sorted(CANON.glob("*.json")):
    d = json.loads(p.read_text(encoding="utf-8-sig"))
    ents = d.get("entries") or []
    provs = {}
    for e in ents:
        provs[e.get("provenance")] = provs.get(e.get("provenance"), 0) + 1
    print("  %s: entries=%d %s canonical=%s version=%s" % (
        p.name, len(ents), provs, d.get("canonical"), d.get("canonical_version")))