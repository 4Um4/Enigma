import os

filepath = "backend/app/services/perception/fact_extractor.py"
if os.path.exists(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Заменяем signal.field_name на signal.field
    content = content.replace("signal.field_name", "signal.field")
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed fact_extractor.py!")
else:
    print("File not found!")