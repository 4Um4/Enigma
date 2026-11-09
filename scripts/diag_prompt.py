import json, urllib.request, urllib.error

with open("backend/prompts/chronicle_decompose_system.txt", "r", encoding="utf-8") as f:
    sp = f.read()

print(f"System prompt: {len(sp)} chars, {sp.count(chr(10))} lines")

body = json.dumps({
    "messages": [
        {"role": "system", "content": sp},
        {"role": "user", "content": "Say hello"}
    ],
    "max_tokens": 50,
    "temperature": 0.0,
    "seed": 42
}).encode("utf-8")

print(f"Request body: {len(body)} bytes")

req = urllib.request.Request(
    "http://127.0.0.1:8183/v1/chat/completions",
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST",
)

try:
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
        print("OK:", data["choices"][0]["message"]["content"][:200])
except urllib.error.HTTPError as e:
    print(f"FAIL: HTTP {e.code}")
    resp = e.read().decode("utf-8", errors="replace")[:500]
    print(f"Response: {resp}")
except Exception as e:
    print(f"FAIL: {e}")