import os
import re

def fix_future_import(filepath: str) -> bool:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    original = content
    lines = content.split('\n')
    
    # Ищем строку с __future__
    future_line_idx = -1
    for i, line in enumerate(lines):
        if line.strip().startswith("from __future__ import"):
            future_line_idx = i
            break
            
    if future_line_idx > 0:
        # Удаляем её со старого места
        future_line = lines.pop(future_line_idx)
        
        # Ищем, куда её вставить. Она должна быть после docstring, но до остальных импортов.
        # Простейший способ: вставить в самую первую строку (строго после # -*- coding -*- если есть).
        # Но безопаснее вставить после первого блока комментариев/docstring.
        
        insert_idx = 0
        # Пропускаем shebang и coding
        while insert_idx < len(lines) and (lines[insert_idx].startswith('#!') or lines[insert_idx].startswith('# -*-') or lines[insert_idx].startswith('# pylint')):
            insert_idx += 1
            
        # Если первый элемент - тройная кавычка (docstring)
        if insert_idx < len(lines) and lines[insert_idx].strip().startswith('"""'):
            # Ищем закрывающую тройную кавычку
            for i in range(insert_idx + 1, len(lines)):
                if '"""' in lines[i]:
                    insert_idx = i + 1
                    break
                    
        lines.insert(insert_idx, future_line)
        content = '\n'.join(lines)
        
        if content != original:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
            
    return False

count = 0
for root, _, files in os.walk("backend/app"):
    if "__pycache__" in root:
        continue
    for file in files:
        if file.endswith(".py"):
            filepath = os.path.join(root, file)
            if fix_future_import(filepath):
                count += 1
                print(f"Fixed future import: {filepath}")

print(f"Total files fixed: {count}")