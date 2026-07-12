"""
Test script for multimodel LLM system.
Run BEFORE starting the main application.
"""

import sys
import urllib.request
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]  # backend/
sys.path.insert(0, str(ROOT_DIR))


try:
    from app.services.llm import Capability, get_router, initialize_router
except ImportError as e:
    print(f"[ERROR] Failed to import LLM components: {e}")
    print("Please check that the new architecture is correctly installed.")
    print("Make sure backend/__init__.py and backend/app/__init__.py exist.")
    sys.exit(1)


def test_multimodel():
    """Test multimodel LLM system using ModelRouter."""
    print("=" * 50)
    print("   Enigma Multimodel LLM Test")
    print("=" * 50)
    print()

    # Read dynamic port from runtime_ports.json
    try:
        from data.runtime_ports import load_ports

        ports = load_ports()
        llm_port = ports.get("llm_port", 8080)
    except Exception as e:
        print(
            f"[WARN] Could not read ports, using 8080: {str(e).encode('utf-8', errors='replace').decode('utf-8', errors='ignore')}"
        )
        llm_port = 8080

    server_url = f"http://127.0.0.1:{llm_port}"

    # Try multiple llama.cpp endpoints
    endpoints = ["/v1/models", "/metrics", "/health"]
    server_ok = False
    for endpoint in endpoints:
        try:
            test_url = server_url + endpoint
            print(f"Testing {test_url}...")
            with urllib.request.urlopen(test_url, timeout=3) as resp:
                response_data = resp.read().decode("utf-8", errors="ignore")

                server_ok = True
                break
        except Exception as e:
            print(f"  {endpoint}: {e}")
            continue

    if not server_ok:
        LLAMA_BAT = str(ROOT_DIR / "backend" / "run_llama_server_multi.bat")
        print(f"   Run: {LLAMA_BAT}")
        print(f"   Try manual: curl {server_url}/v1/models")
        pytest.skip(f"LLaMA server not available at {server_url}")
    else:
        print(f"[OK] LLaMA Server running at {server_url}")

    # Инициализируем роутер
    try:
        initialize_router()
        router = get_router()
        print("[OK] ModelRouter initialized")
    except Exception as e:
        print(f"[ERROR] Failed to initialize router: {e}")
        pytest.skip("ModelRouter initialization failed")

    # Список агентов (соответствует DEFAULT_AGENT_CAPABILITY_MAP)
    agents = ["dm", "npc", "rules", "world", "memory"]

    prompts = {
        "dm": "Skazhi odnu frazu ot imeni travnitschika",
        "npc": "Skazhi chto-nibud vorchlivoe ot imeni starogo gnoma",
        "rules": "Nužén li brosok d20 dlya: popytka vzlamat zamok otvertkoy?",
        "world": "Sgeneriruy odno kratkoe sobytie v fantazi gorode",
        "memory": "What happened in the last scene?",
    }

    print("\n" + "=" * 50)
    print("   Testing Agents")
    print("=" * 50)

    for agent_name in agents:
        print(f"\n[{agent_name.upper()}] Testing:")
        prompt = prompts.get(agent_name, "Hello")
        try:
            # Используем правильный метод request_for_agent
            response = router.request_for_agent(
                agent_name=agent_name,
                prompt=prompt,
                # Можно передать параметры генерации, если нужно
                # params=GenerationParams(max_tokens=50)
            )
            print(
                f"   Response: {response[:200].encode('utf-8', errors='replace').decode('utf-8', errors='ignore')}..."
            )
        except Exception as e:
            print(f"   Error: {e}")

    print("\n" + "=" * 50)
    print("   Test Complete!")
    print("=" * 50)


if __name__ == "__main__":
    test_multimodel()
