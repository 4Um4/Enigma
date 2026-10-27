import json, urllib.request

def smoke_test():
    body = json.dumps({
        "messages": [
            {"role": "system", "content": "You are a helpful assistant. Reply in JSON: {\"reply\":\"hello\"}"},
            {"role": "user", "content": "Say hello in Russian"}
        ],
        "max_tokens": 100,
        "temperature": 0.0,
        "response_format": {"type": "json_object"}
    }).encode("utf-8")
    req = urllib.request.Request(
        "http://localhost:8181/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        model = data.get("model", "unknown")
        return f"OK\nRESPONSE: {content[:300]}\nMODEL: {model}"
    except Exception as e:
        return f"FAIL\nERROR: {e}"

print(smoke_test())
