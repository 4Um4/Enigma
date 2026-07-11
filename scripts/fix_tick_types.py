import re

filepath = "backend/app/domain/tick.py"
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Заменяем голые dict и list в аннотациях на параметризованные
# Простая замена: ": dict" -> ": Dict[str, Any]", ": list" -> ": List[Any]"
content = content.replace(": dict,", ": Dict[str, Any],")
content = content.replace(": list,", ": List[Any],")
content = content.replace("Optional[dict]", "Optional[Dict[str, Any]]")
content = content.replace("Optional[list]", "Optional[List[Any]]")

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
    
print("tick.py fixed!")