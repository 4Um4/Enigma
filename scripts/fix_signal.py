import os

filepath = "backend/app/services/perception/perception_physics_engine.py"
if os.path.exists(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Заменяем field_name=field на field=field
    content = content.replace("field_name=field,", "field=field,")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print("Fixed perception_physics_engine.py!")
else:
    print("File not found!")
