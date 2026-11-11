#!/usr/bin/env python3
"""probe_npc_roleplay.py — NPC dialogue test for top LLM models."""
import json, subprocess, time, urllib.request, urllib.error, sys, re
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
LLAMA_SERVER = ROOT / "Models LLM" / "llama" / "llama-server.exe"
DM_PROMPT = ROOT / "backend" / "prompts" / "dm_system.txt"
DM_GRAMMAR = ROOT / "config" / "dm_response.gbnf"
PROBE_PORT = 8183
PROBE_HOST = "127.0.0.1"
SERVER_BOOT_SECS = 150
MAX_TOKENS = 256
TEMPERATURE = 0.9
SEED = 42
REPORTS_DIR = ROOT / "reports" / "probe_npc"

SCENARIOS = [
    ("S1_threat", "Торнин", "трактирщик, пьяный, раздражительный", "стоит за стойкой", "игнорировать посетителя", "Я знаю, что ты бьёшь Люсю. Если не перестанешь — я расскажу страже."),
    ("S2_secret", "Тень", "вор, безногая, скрытная", "сидит в углу", "остаться незамеченной", "Расскажи мне о своём прошлом. Кто тебя пытал?"),
    ("S3_compliment", "Люся", "служанка, мечтает сбежать, боится", "протирает стол", "закончить работу", "Ты очень смелая девочка, Люся."),
    ("S4_attack", "Борко", "вышибала, огромный, жестокий", "стоит у двери", "охранять вход", "Я замахиваюсь на тебя мечом."),
    ("S5_relationship", "Горан", "наёмник, злится, подозрителен", "сидит за столом", "допить и уйти", "Что ты думаешь о Торнине?"),
    ("S6_minimal", "Торнин", "трактирщик", "за стойкой", "обслужить гостя", "..."),
]

FORBIDDEN = ["игрок", "игроки", "симуляция", "система", "механика", "game", "player"]
CHINESE_RE = re.compile(r'[\u4e00-\u9fff]')
RESULT_WORDS = ['упал', 'попал', 'ударил', 'убил', 'ранил', 'повалил', 'сразил']
STATE_CHANGE = ['испугался', 'передумал', 'убежал', 'сдался', 'решил уйти']
NPC_NAMES = ['Торнин', 'Люся', 'Борко', 'Горан', 'Тень']

def check_wsi(text, npc, intent):
    v = []; t = text.lower()
    for w in RESULT_WORDS:
        if w in t: v.append('result:' + w)
    for w in STATE_CHANGE:
        if w in t: v.append('state:' + w)
    for other in NPC_NAMES:
        if other != npc and other.lower() in t and t.count(other.lower()) > t.count(npc.lower()):
            v.append('identity:' + other)
    if 'незамеченной' in intent and any(w in t for w in ['ответила', 'сказала', 'заговорила']):
        v.append('intent:spoken')
    if 'охранять' in intent and any(w in t for w in ['убежал', 'ушёл', 'отступил']):
        v.append('intent:fled')
    return v

def spawn_server(model_path, ctx_size=8192, use_jinja=True):
    cmd = [str(LLAMA_SERVER), "--model", str(model_path), "--ctx-size", str(ctx_size), "--n-gpu-layers", "99", "--port", str(PROBE_PORT), "--host", PROBE_HOST]
    if use_jinja: cmd.append("--jinja")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0)
    print(f"[SPAWN] PID={proc.pid}, waiting {SERVER_BOOT_SECS}s...")
    time.sleep(SERVER_BOOT_SECS)
    if proc.poll() is not None: print("[SPAWN] FAILED"); return None
    try:
        urllib.request.build_opener(urllib.request.ProxyHandler({})).open(f"http://{PROBE_HOST}:{PROBE_PORT}/health", timeout=5).read()
        print("[SPAWN] health OK"); return proc
    except: print("[SPAWN] health failed"); proc.kill(); return None

def call_llm(system_prompt, user_prompt):
    body = json.dumps({"messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], "max_tokens": MAX_TOKENS, "temperature": TEMPERATURE, "seed": SEED, "response_format": {"type": "json_object"}, **({"grammar": DM_GRAMMAR.read_text(encoding="utf-8")} if DM_GRAMMAR.exists() else {})}).encode("utf-8")
    req = urllib.request.Request(f"http://{PROBE_HOST}:{PROBE_PORT}/v1/chat/completions", data=body, headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=60) as r:
            data = json.loads(r.read())
        return data["choices"][0]["message"]["content"], time.time() - t0, None
    except Exception as e: return "", time.time() - t0, str(e)

def evaluate(content, npc_name='', npc_intent='', player_input=''):
    c = {}
    c["chinese"] = bool(CHINESE_RE.search(content))
    c["fourth_wall"] = any(w in content.lower() for w in FORBIDDEN)
    s = [x.strip() for x in content.replace("!", ".").replace("?", ".").split(".") if x.strip()]
    c["sentences"] = len(s)
    c["sentence_ok"] = 2 <= len(s) <= 5
    c["has_question"] = "?" in content
    c["has_speech"] = any(q in content for q in ['"', '"', '"', "'"])
    try:
        d = json.loads(content)
        c["json_valid"] = "dm_response" in d
        c["response"] = d.get("dm_response", "")
    except: c["json_valid"] = False; c["response"] = content
    c["wsi"] = check_wsi(c.get("response", content), npc_name, npc_intent)
    c["wsi_clean"] = len(c["wsi"]) == 0
    return c

def run_test(model_path, model_id, ctx_size=8192, use_jinja=True):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = REPORTS_DIR / ts / model_id
    out.mkdir(parents=True, exist_ok=True)
    sp = DM_PROMPT.read_text(encoding="utf-8")
    print(f"\n{'='*60}\n[TEST] {model_id} ctx={ctx_size}\n{'='*60}\n")
    proc = spawn_server(model_path, ctx_size, use_jinja)
    if not proc: return None
    results = []
    for sid, npc, desc, state, intent, pinput in SCENARIOS:
        user = f"Ключевые NPC:\n- {npc}: {desc}. Состояние: {state}. Намерение: {intent}.\n\nОбращение игрока: {pinput}"
        content, lat, err = call_llm(sp, user)
        if err: c = {"error": err, "latency": round(lat,2), "scenario": sid}
        else: c = evaluate(content, npc, intent, pinput); c["latency"] = round(lat,2); c["scenario"] = sid; c["npc"] = npc
        results.append(c)
        r = c.get("response","")[:80]
        print(f"[{sid}] {'ERR' if err else 'OK'} {lat:.1f}s | {r}")
    (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    proc.kill()
    ok = sum(1 for r in results if not r.get("error") and r.get("json_valid") and r.get("sentence_ok") and not r.get("chinese") and not r.get("fourth_wall"))
    wsi = sum(1 for r in results if r.get("wsi_clean", False))
    print(f"\n[SCORE] Format: {ok}/{len(results)} | WSI: {wsi}/{len(results)}")
    return results

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("model_path")
    p.add_argument("--model-id", required=True)
    p.add_argument("--ctx-size", type=int, default=8192)
    p.add_argument("--no-jinja", action="store_true")
    a = p.parse_args()
    run_test(Path(a.model_path), a.model_id, a.ctx_size, not a.no_jinja)