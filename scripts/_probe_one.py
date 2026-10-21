import urllib.request, json, time, sys
body = json.dumps({
  "messages": [{"role": "user", "content": "Привет! Кто ты?"}],
  "max_tokens": 50,
  "temperature": 0.0,
  "response_format": {"type": "json_object"},
  "chat_template_kwargs": {"enable_thinking": False}
}).encode("utf-8")
req = urllib.request.Request("http://127.0.0.1:8181/v1/chat/completions",
  data=body, headers={"Content-Type": "application/json"}, method="POST")
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
t0 = time.time()
try:
  with opener.open(req, timeout=120) as r:
    data = json.loads(r.read().decode("utf-8"))
  print("Latency: {:.2f}s".format(time.time() - t0))
  content = data["choices"][0]["message"]["content"]
  print("Content: " + content[:300])
  print("Tokens: " + str(data["usage"]["total_tokens"]))
except Exception as e:
  print("Latency: {:.2f}s (FAILED)".format(time.time() - t0))
  print("Error: " + str(e))
