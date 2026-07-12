import os

filepath = "backend/app/services/state/persistence_port.py"
if os.path.exists(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Жестко удаляем все вхождения U+FEFF (BOM) из всего текста
    content = content.replace("\ufeff", "")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print("BOM completely removed!")
else:
    print("File not found!")
