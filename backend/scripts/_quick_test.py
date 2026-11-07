# -*- coding: utf-8 -*-
import sys, os, time
sys.path.insert(0, "backend")
os.environ.setdefault("D8P_ENABLED", "1")
print("IMPORT START", flush=True)
from app.services.llm.router import initialize_router
print("router imported", flush=True)
initialize_router()
print("router initialized", flush=True)
from tests.gameplay.harness import TavernGameplayHarness
print("harness imported", flush=True)
h = TavernGameplayHarness(seed=42, location="tavern")
print("harness created", flush=True)
h.new_game()
print("new_game done", flush=True)
print("ALL INIT DONE", flush=True)
