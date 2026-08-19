import os
import re

audits_dir = "docs/audits"
adr_line_regex = re.compile(r"`(ADR-[A-Za-z0-9\-]+)`\s*\[([A-Za-z0-9\-]+)\]\s*\*\*(.+?)\*\*")

for f in os.listdir(audits_dir):
    if f.endswith(".md"):
        path = os.path.join(audits_dir, f)
        with open(path, "r", encoding="utf-8") as file:
            content = file.read()
        
        if not adr_line_regex.search(content):
            base = f.replace(".md", "")
            parts = base.split("_", 1)
            adr_id = parts[0]
            title = parts[1] if len(parts) > 1 else "IMPACT"
            title = title.replace("_", " ")
            
            header = f"# {adr_id} Impact Audit\n> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`\n\n`{adr_id}` [STANDARD] **{title}**\n\n"
            
            with open(path, "w", encoding="utf-8") as file:
                file.write(header + content)
            print(f"Updated: {f}")