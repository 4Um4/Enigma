import sqlite3

conn = sqlite3.connect("saves/enigma_runtime.db")
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print([r[0] for r in cur.fetchall()])
cur.execute("SELECT key FROM scene_runtime LIMIT 5")
try:
    print([r[0] for r in cur.fetchall()])
except Exception as e:
    print("no scene_runtime:", e)
conn.close()
