"""
Test script for multimodel LLM system.
Run BEFORE starting the main application.
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.llm_manager import LlmManager


def test_multimodel():
    """Test multimodel LLM system."""
    print("=" * 50)
    print("   Enigma Multimodel LLM Test")
    print("=" * 50)
    print()
    
    # Check if server is running
    import urllib.request
    server_url = "http://127.0.0.1:8080"
    try:
        with urllib.request.urlopen(server_url + "/health", timeout=2) as resp:
            print(f"[OK] LLaMA Server running at {server_url}")
    except Exception as e:
        print(f"[ERROR] LLaMA Server NOT running at {server_url}")
        print(f"   Run: backend\\run_llama_server_multi.bat")
        print(f"   Error: {e}")
        return False
    
    llm = LlmManager()
    
    # List available models
    print("\nAvailable models:")
    agents = llm.list_agents_and_models()
    for agent, model in agents.items():
        path = llm.get_model_path(agent)
        model_name = path.split('\\')[-1] if path else 'N/A'
        print(f"   {agent:10} -> {model} ({model_name})")
    
    print("\n" + "=" * 50)
    print("   Testing Agents")
    print("=" * 50)
    
    # Test DM agent
    print("\n[DM] Testing (Qwen2.5-7B):")
    try:
        response = llm.run_for_agent("dm", "Skazhi odnu frazu ot imeni travnitschika", max_tokens=50)
        print(f"   Response: {response[:200]}...")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test NPC agent
    print("\n[NPC] Testing (YandexGPT):")
    try:
        response = llm.run_for_agent("npc", "Skazhi chto-nibud vorchlivoe ot imeni starogo gnoma", max_tokens=50)
        print(f"   Response: {response[:200]}...")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test Rules agent
    print("\n[Rules] Testing (Saiga):")
    try:
        response = llm.run_for_agent("rules", "Nužen li brotok d20 dlya: popytka vzlamat zamok otvertkoy?", max_tokens=100)
        print(f"   Response: {response[:200]}...")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test World agent
    print("\n[World] Testing (Qwen3.5-9B):")
    try:
        response = llm.run_for_agent("world", "Sgeneriruy odno kratkoe sobytie v fantazi gorode", max_tokens=50)
        print(f"   Response: {response[:200]}...")
    except Exception as e:
        print(f"   Error: {e}")
    
    print("\n" + "=" * 50)
    print("   Test Complete!")
    print("=" * 50)
    print("\nNext: Run main app and use API:")
    print("   POST /api/game/turn")
    
    return True


if __name__ == "__main__":
    test_multimodel()

