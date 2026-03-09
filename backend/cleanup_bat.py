import os

# Files to delete
files_to_delete = [
    'start_llama_server.bat',
    'run_llama_server.bat', 
    'start_dm_terminal.bat',
    'run_game.bat',
    'temp.bat',
    'llama_server_test.bat'
]

backend_dir = r'c:\DDD\Codex\VSC_Enigma\Enigma\backend'

for f in files_to_delete:
    path = os.path.join(backend_dir, f)
    if os.path.exists(path):
        os.remove(path)
        print(f"Deleted: {f}")
    else:
        print(f"Not found: {f}")

print("Done!")
