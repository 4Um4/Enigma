import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.input.llm_compressor_client import LlamaCppCompressorClient

# env-явность: ambient-наследование = источник INVALID; снимаем всё,
# влияющее на сборку промпта
_ENV_FLAGS = (
    "ENIGMA_PROV_B", "ENIGMA_PROV_B2", "ENIGMA_PROV_X2", "ENIGMA_PROV_XCLEAN",
    "ENIGMA_SEM_LIB", "ENIGMA_SEM_LIB_MODULES", "ENIGMA_SEM_ROUTER",
    "ENIGMA_RC8_STATE",
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--module", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    for flag in _ENV_FLAGS:
        os.environ.pop(flag, None)
    os.environ["ENIGMA_SEM_LIB"] = "1"
    os.environ["ENIGMA_SEM_LIB_MODULES"] = args.module
    prompt = LlamaCppCompressorClient()._build_prompts("тест", {})[0]
    out = Path(args.out)
    out.write_text(prompt, encoding="utf-8", newline="")
    print(f"[GEN] module={args.module} bytes={len(prompt.encode('utf-8'))} -> {out}")


if __name__ == "__main__":
    main()
