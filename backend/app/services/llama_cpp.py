from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from app.core.config import settings

# Windows command line limit ~8191 chars. Long prompts must go via file.
_WIN_CMD_LINE_LIMIT = 8000


def _run_via_server(
    prompt: str,
    max_tokens: int,
    server_url: str,
    timeout_sec: int,
    temperature: float = 0.7,
    top_p: float = 0.9,
    repeat_penalty: float = 1.1,
    n_keep: int = 512,
) -> str:
    """
    Otpravlyaet prompt v llama-server (model uzhe v pamyati - otvet za sekundu).
    """
    url = server_url.rstrip("/") + "/completion"
    
    # Rasshirennye stop-tokeny dlya predotvrasheniya s'ezda s roli DM
    stop_tokens = [
        "</system>", "</user>", "<user>", "<assistant>", 
        "<|im_end|>", "<|end_of_text|>",
        "Igrok:", "Vy:", "Personazh:",
        "\nIgrok", "\nVy:", "\nPersonazh:",
    ]
    
    # Parametry generacii dlya strogoy rolevoy igry
    generation_params = {
        "prompt": prompt,
        "n_predict": max_tokens,
        "stream": False,
        "stop": stop_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "repeat_penalty": repeat_penalty,
        "n_keep": n_keep,
    }
    
    data = json.dumps(generation_params).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Ne udalos podklyuchitsya k llama-server ({server_url}). "
            "Zapustite llama-server v otdelnom terminale, naprimer:\n"
            "  llama-server -m model.gguf -c 2048\n"
        ) from e
    
    content = body.get("content", "")
    return content.strip()


def _load_model_via_server(server_url: str, model_path: str, model_name: str) -> bool:
    """
    Zagruzhaet model v llama-server cherez API /model.json.
    """
    url = server_url.rstrip("/") + "/model.json"
    
    data = json.dumps({
        "model": model_path
    }).encode("utf-8")
    
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status == 200
    except urllib.error.URLError:
        return False


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

    def resolve_model_path(self, model_key: str | None = None) -> str:
        """
        Razreshit put k modeli.
        """
        if model_key:
            from app.services.model_router import ModelRouter
            router = ModelRouter()
            path = router.get_model_path(model_key)
            if path:
                return path
        
        # Fallback
        configured = os.getenv("LLAMA_TEST_MODEL") or os.getenv("LLAMA_CPP_MODEL") or settings.llama_cpp_model_path
        if not configured:
            raise RuntimeError("GGUF model path is not configured. Set LLAMA_TEST_MODEL or LLAMA_CPP_MODEL.")

        candidate = Path(configured).expanduser()
        if not candidate.exists():
            raise RuntimeError(f"GGUF model file does not exist: {candidate}")
        return str(candidate)

    def run_prompt_with_params(
        self,
        prompt: str,
        max_tokens: int | None = None,
        temperature: float = 0.7,
        top_p: float = 0.9,
        repeat_penalty: float = 1.1,
        n_keep: int = 512,
    ) -> str:
        """
        Zapustit generaciyu s ukazannymi parametrami.
        """
        server_url = os.getenv("LLAMA_CPP_SERVER_URL") or getattr(
            settings, "llama_cpp_server_url", None
        )
        
        if server_url:
            token_limit = max_tokens if max_tokens is not None else settings.llama_cpp_max_tokens
            return _run_via_server(
                prompt,
                max_tokens=token_limit,
                server_url=server_url,
                timeout_sec=settings.llama_cpp_timeout_sec,
                temperature=temperature,
                top_p=top_p,
                repeat_penalty=repeat_penalty,
                n_keep=n_keep,
            )

        # Fallback: zapusk cherez komandnuyu stroku
        return self._run_cli(prompt, max_tokens, temperature, top_p, repeat_penalty)

    def run_prompt(self, prompt: str, max_tokens: int | None = None) -> str:
        """Standartnyy zapusk prompta (obratnaya sovmestimost)."""
        return self.run_prompt_with_params(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=settings.llama_cpp_temperature,
            top_p=settings.llama_cpp_top_p,
            repeat_penalty=settings.llama_cpp_repeat_penalty,
            n_keep=settings.llama_cpp_n_keep,
        )

    def _run_cli(
        self,
        prompt: str,
        max_tokens: int | None = None,
        temperature: float = 0.7,
        top_p: float = 0.9,
        repeat_penalty: float = 1.1,
    ) -> str:
        """Zapusk cherez CLI (bez servera)."""
        executable = self.resolve_executable()
        model_path = self.resolve_model_path()

        token_limit = max_tokens if max_tokens is not None else settings.llama_cpp_max_tokens

        # Windows has ~8191 char command line limit. Use -f (file) for long prompts.
        use_file = len(prompt) > _WIN_CMD_LINE_LIMIT
        cmd: list[str] = [
            executable,
            "-m", model_path,
            "-n", str(token_limit),
            "--temp", str(temperature),
            "--top-p", str(top_p),
            "--repeat-penalty", str(repeat_penalty),
        ]

        if use_file:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".txt",
                delete=False,
                encoding="utf-8",
                errors="replace",
            ) as f:
                f.write(prompt)
                tmp_path = f.name
            try:
                cmd.extend(["-f", tmp_path])
                completed = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=True,
                    timeout=settings.llama_cpp_timeout_sec,
                )
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
        else:
            cmd.extend(["-p", prompt])
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
                timeout=settings.llama_cpp_timeout_sec,
            )

        output = completed.stdout.strip()
        if output:
            return output
        return completed.stderr.strip()

    def get_server_url(self) -> str:
        """Poluchit URL llama-server."""
        return os.getenv("LLAMA_CPP_SERVER_URL") or settings.llama_cpp_server_url

