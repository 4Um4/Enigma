"""path: /project/reports/p0_rb_env.py

Назначение: P0-3b (SR-1, GO Мастера): заморозка окружения R-b — exact
    версии пакетов, identity (revision-hash) модели, размер на диске,
    CPU latency, детерминизм эмбеддинга. Модель запинена ДО любого
    separation-замера: paraphrase-multilingual-MiniLM-L12-v2, БЕЗ model
    shopping (вердикт: не разделяется — R-b закрыт вместе с ней).
    Сеть — только install-time (P0-3a); замер офлайн (политика Q-3 п.5:
    без скачиваний/подгрузок модели в измерительном прогоне).
Зависимости: sentence_transformers + torch (greenfield, P0-3a),
    huggingface_hub, numpy, stdlib. app/ не импортируется;
    production-эффект нулевой.
Основные сущности: _MODEL_ID, _REPO_ID, _PROBE_PHRASES (representatives
    семей для latency — НЕ separation-замер), main().
Запуск: python reports/p0_rb_env.py (модель уже в HF-кэше; запуск
    командой с HF_HUB_OFFLINE=1 — доказательство офлайн-режима).
"""

import time
from pathlib import Path

import numpy

_MODEL_ID = "paraphrase-multilingual-MiniLM-L12-v2"
_REPO_ID = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Пробные фразы для latency: representatives трёх семей (два PROV+-
# промаха baseline, ID+, чистые EMPTY) — честная нагрузка CPU.
_PROBE_PHRASES = (
    "Кто тебя просветил насчёт моего имени?",
    "Кто тебе проинформировал о моём имени?",
    "Кто ты?",
    "Привет, я Мю. А кто ты?",
    "Кто тебе сказал, что я Мю?",
    "Откуда ты знаешь, что меня зовут Мю?",
    "Ты помнишь моё имя?",
    "Быть добру! Привет! Здоровеньки булы!",
    "Пнуть под зад",
    "Что у вас можно купить?",
)


def main() -> None:
    import sentence_transformers
    import torch
    import transformers
    from huggingface_hub import snapshot_download

    print("=== P0-3b: R-b ENVIRONMENT FREEZE (модель запинена, без shopping) ===")
    print(f"model: {_REPO_ID}")
    print(f"sentence-transformers=={sentence_transformers.__version__}")
    print(f"torch=={torch.__version__} (cuda_available={torch.cuda.is_available()}; "
          "CPU = целевой режим, VRAM занят llama-server)")
    print(f"transformers=={transformers.__version__}")
    print(f"numpy=={numpy.__version__}")

    # Offline-резолв снапшота: локальный кэш, сеть не нужна (Q-3 п.5).
    snap = Path(snapshot_download(repo_id=_REPO_ID, local_files_only=True))
    revision = snap.name
    size_mb = round(
        sum(f.stat().st_size for f in snap.rglob("*") if f.is_file()) / 1e6, 1
    )
    print(f"revision: {revision}")
    print(f"model_size: {size_mb} MB (snapshot: {snap})")

    model = sentence_transformers.SentenceTransformer(_MODEL_ID)
    dim = model.get_sentence_embedding_dimension()
    print(f"embedding_dim: {dim}")

    # Latency: холодный + тёплый (3x) прогон 10 фраз, CPU.
    phrases = list(_PROBE_PHRASES)
    t0 = time.perf_counter()
    model.encode(phrases)
    cold_ms = (time.perf_counter() - t0) * 1000.0 / len(phrases)
    t0 = time.perf_counter()
    for _ in range(3):
        model.encode(phrases)
    warm_ms = (time.perf_counter() - t0) * 1000.0 / (3 * len(phrases))
    print(f"latency_cold: {cold_ms:.1f} ms/фраза | latency_warm: {warm_ms:.1f} ms/фраза (CPU)")

    # Детерминизм: одинаковый вход -> идентичный вектор (нет сэмплирования).
    v1 = model.encode(["Кто ты?"])[0]
    v2 = model.encode(["Кто ты?"])[0]
    max_diff = float(numpy.max(numpy.abs(v1 - v2)))
    print(f"determinism: max_abs_diff={max_diff:.2e} (ожидание 0.0)")

    print(
        f"ИТОГО P0-3b: model={_MODEL_ID} rev={revision[:12]} size={size_mb}MB "
        f"dim={dim} warm={warm_ms:.1f}ms/фраза det={max_diff:.2e}"
    )


if __name__ == "__main__":
    main()
