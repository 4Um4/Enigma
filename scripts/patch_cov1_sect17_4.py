path = "docs/ENIGMA_ROADMAP_v4_11_WPS.md"
with open(path, "rb") as f:
    raw = f.read()
has_bom = raw[:3] == b"\xef\xbb\xbf"
text = raw.decode("utf-8-sig" if has_bom else "utf-8")
old = "pinned ADR-O-351 \u0437\u0430\u0449\u0438\u0449\u0435\u043d\u044b \u0412\u0421\u0415\u0413\u0414\u0410. **S1 \u043f\u043e\u043b\u043d\u0430\u044f \u043f\u0443\u0431\u043b\u0438\u043a\u0430\u0446\u0438\u044f:** \u0428\u0430\u0433 1+4+5 \u2014 \u0440\u0435\u043b\u0435\u0439 \u0432\u0435\u0442\u0432\u0438 \u0410 \u0434\u043b\u044f event_memories (NL-1/MEM-1) \u0447\u0435\u0440\u0435\u0437 register_migrations."
new = old + " **\u0413\u0435\u0439\u0442:** COV-GC-01/02 \u2014 \u0437\u0430\u043a\u0440\u044b\u0442 \u043f\u043e\u043b\u043d\u043e\u0441\u0442\u044c\u044e."
count = text.count(old)
print(f"Pre-check matches: {count}")
if count == 1:
    text = text.replace(old, new)
    with open(path, "wb") as f:
        if has_bom:
            f.write(b"\xef\xbb\xbf")
        f.write(text.encode("utf-8"))
    print(f"PATCH APPLIED (BOM={has_bom})")
else:
    print("ABORT: not unique or missing")