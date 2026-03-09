#!/usr/bin/env python3
"""Delete duplicate bat files."""
import pathlib

backend = pathlib.Path(r"c:\DDD\Codex\VSC_Enigma\Enigma\backend")

# Files to delete
to_delete = [
    "start_llama_server.bat",
    "run_llama_server.bat",
    "start_dm_terminal.bat",
    "run_game.bat",
    "temp.bat",
    "llama_server_test.bat",
    "cleanup_bat.py",
    "run_cleanup.bat",
]

for f in to_delete:
    p = backend / f
    if p.exists():
        p.unlink()
        print(f"Deleted: {f}")
    else:
        print(f"Not found: {f}")

print("Done!")
