import json
import sqlite3

conn = sqlite3.connect("saves/enigma_runtime.db")
cur = conn.cursor()
cur.execute("SELECT key, value FROM state_kv WHERE key LIKE ?", ("scene:Open_road:%",))
for k, v in cur.fetchall():
    d = json.loads(v)
    ids = list((d.get("npc_positions") or {}).keys())
    print(k.split(":")[-1], "->", ids)
conn.close()
