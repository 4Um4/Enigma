from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from app.core.config import settings


class LlamaCppAdapter:
    """Thin subprocess adapter for local llama.cpp executable."""

    _KNOWN_BINARIES = (
        "llama",
        "llama.exe",
        "main",
        "main.exe",
        "llama-cli",
        "llama-cli.exe",
    )

    def resolve_executable(self) -> str:
        configured = os.getenv("LLAMA_CPP_EXECUTABLE") or settings.llama_cpp_executable
        if configured:
            candidate = Path(configured).expanduser()
            if candidate.exists():
                return str(candidate)

        for name in self._KNOWN_BINARIES:
            found = shutil.which(name)
            if found:
                return found

        raise RuntimeError(
            "llama.cpp executable not found. Set LLAMA_CPP_EXECUTABLE or add llama/main to PATH."
        )

    def resolve_model_path(self) -> str:
        configured = os.getenv("LLAMA_TEST_MODEL") or os.getenv("LLAMA_CPP_MODEL") or settings.llama_cpp_model_path
        if not configured:
            raise RuntimeError("GGUF model path is not configured. Set LLAMA_TEST_MODEL or LLAMA_CPP_MODEL.")

        candidate = Path(configured).expanduser()
        if not candidate.exists():
            raise RuntimeError(f"GGUF model file does not exist: {candidate}")
        return str(candidate)

    def run_prompt(self, prompt: str, max_tokens: int | None = None) -> str:
        executable = self.resolve_executable()
        model_path = self.resolve_model_path()

        token_limit = max_tokens if max_tokens is not None else settings.llama_cpp_max_tokens

        cmd = [
            executable,
            "-m",
            model_path,
            "-p",
            prompt,
            "-n",
            str(token_limit),
        ]

        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=settings.llama_cpp_timeout_sec,
        )
        output = completed.stdout.strip()
        if output:
            return output
        return completed.stderr.strip()
