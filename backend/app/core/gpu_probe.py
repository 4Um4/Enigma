"""
Назначение: будет вычислять доступную видеопамять (VRAM) через nvidia-smi и динамически рассчитывать количество слоев -ngl. Бэкенд будет читать этот профиль при запуске.
"""

import subprocess
import json
import os
from pathlib import Path
from typing import Optional

def get_gpu_vram() -> Optional[int]:
    """Запрашивает объем VRAM через nvidia-smi. Возвращает МБ или None."""
    try:
        _creation_flags = 0
        if os.name == 'nt':
            _creation_flags = 0x08000000 # CREATE_NO_WINDOW
            
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, check=True, creationflags=_creation_flags
        )
        # Берем первую видеокарту
        vram_str = result.stdout.strip().split('\n')[0]
        return int(vram_str)
    except Exception:
        return None

def calculate_gpu_layers(vram_mb: Optional[int], model_size_mb: int = 5200, total_layers: int = 28) -> int:
    """
    Рассчитывает количество слоев для GPU.
    Qwen 7B Q5_K_M весит ~5.2 ГБ. Имеет 28 слоев.
    Формула: VRAM / (Размер модели * 1.3) * Слои.
    1.3 - это буфер на KV cache и контекст (8192 токена).
    """
    if vram_mb is None or vram_mb == 0:
        return 0 # CPU fallback
    
    required_vram_for_full = int(model_size_mb * 1.3)
    
    if vram_mb >= required_vram_for_full:
        return 99 # Все слои на GPU
        
    # Частичный оффлоад
    ratio = vram_mb / required_vram_for_full
    ngl = int(total_layers * ratio * 0.8) # 80% от расчета для безопасности
    return max(0, ngl)

def run_probe(config_dir: Path) -> int:
    """Запускает профилирование и сохраняет результат в gpu_profile.json."""
    vram = get_gpu_vram()
    ngl = calculate_gpu_layers(vram)
    
    profile = {
        "gpu_name": "Unknown" if vram is None else "NVIDIA GPU",
        "vram_total_mb": vram if vram else 0,
        "n_gpu_layers": ngl,
        "fallback_to_cpu": vram is None
    }
    
    config_dir.mkdir(parents=True, exist_ok=True)
    profile_path = config_dir / "gpu_profile.json"
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=4)
        
    return ngl

if __name__ == "__main__":
    # Для ручного теста
    _config_dir = Path(__file__).resolve().parents[3] / "config"
    _ngl = run_probe(_config_dir)
    print(f"Calculated ngl: {_ngl}")
    print(f"Profile saved to: {_config_dir / 'gpu_profile.json'}")