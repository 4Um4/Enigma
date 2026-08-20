import os
import re

audits_dir = "docs/audits"
files_regex = re.compile(r"Files:\s*(.+)")

count = 0
for f in os.listdir(audits_dir):
    if f.endswith(".md"):
        path = os.path.join(audits_dir, f)
        with open(path, "r", encoding="utf-8") as file:
            content = file.read()
        
        if not files_regex.search(content):
            # Добавляем Files: N/A в конец файла
            with open(path, "a", encoding="utf-8") as file:
                file.write("\n\nFiles: N/A\n")
            count += 1

print(f"Обновлено файлов: {count}")