# backend/tests/sandbox/e0_t2b2_live_autonomous_dialogue.py
"""T2b-2: Live Autonomous Dialogue Test — one live run with real LLM on :8181."""
import sys, os, time, requests
sys.stdout.reconfigure(encoding='utf-8')

# Step 1: Ensure LLM via direct broker /ensure (120s timeout — bypasses ensure_llm 10s limit)
print('[T2b-2] Ensuring LLM via broker :8182...')
_pid = os.getpid()
try:
    import psutil; _ct = psutil.Process(_pid).create_time()
except ImportError:
    _ct = time.time()

_url = 'http://localhost:8181'
try:
    _r = requests.post('http://localhost:8182/ensure', json={
        'label': 't2b-2-live', 'pid': _pid, 'process_create_time': _ct, 'pinned': False,
    }, timeout=120)
    if _r.status_code == 200:
        _url = _r.json().get('url', _url)
        print(f'[T2b-2] Broker lease: {_r.json().get("lease_id", "?")[:8]}... url={_url}')
    else:
        print(f'[T2b-2] /ensure {_r.status_code}: {_r.text[:200]}')
except Exception as _e:
    print(f'[T2b-2] /ensure failed: {_e} — direct :8181 fallback')

# Step 2: Verify health
_r = requests.get(f'{_url}/health', timeout=15)
print(f'[T2b-2] LLM health: {_r.status_code} {_r.text[:100]}')
if _r.status_code != 200:
    print('[T2b-2] FATAL: LLM not available'); sys.exit(1)

# Step 3: Capture NPC_SPOKE
_captured = []
def _capture(event):
    try:
        _t = getattr(event, 'type', '')
        _t = _t if isinstance(_t, str) else getattr(_t, 'value', str(_t))
        if _t == 'npc_spoke':
            _ev = {'source': getattr(event, 'source', ''), 'target_id': '', 'text': '', 'topic': '', 'intent_type': ''}
            if hasattr(event, 'payload'):
                _p = event.payload if isinstance(event.payload, dict) else {}
                _ev['target_id'] = _p.get('target_id', '')
                _ev['text'] = _p.get('text', '')
                _ev['topic'] = _p.get('topic', '')
                _ev['intent_type'] = _p.get('intent_type', '')
            _captured.append(_ev)
            print(f'[NPC_SPOKE] {_ev["source"]} -> {_ev["target_id"]}: {_ev["text"][:120]}')
    except Exception:
        pass

# Step 4: Build harness (production game loop)
print('[T2b-2] Building harness...')
from tests.gameplay.harness import TavernGameplayHarness
_h = TavernGameplayHarness(seed=42)
_h.new_game()

# Step 5: Subscribe to NPC_SPOKE
from app.services.events.event_bus import get_event_bus
from app.services.events.event_types import EventType
_bus = get_event_bus()
_bus.subscribe(EventType.NPC_SPOKE, _capture)

# Step 6: Run ticks (up to 15, stop after first NPC_SPOKE)
print('[T2b-2] Running ticks...')
_last_tick = 0
for _i in range(15):
    _last_tick = _i + 1
    try:
        _h.advance_ticks(1)
        _ns = _h.counters.npc_spoke
        _de = _h.counters.decision_events
        _ebt = dict(list(_h.counters.events_by_type.items())[:6])
        print(f'[T2b-2] Tick {_last_tick}: npc_spoke={_ns} decisions={_de} captured={len(_captured)} events={_ebt}')
        if _captured:
            print('[T2b-2] NPC_SPOKE captured — stopping.'); break
    except Exception as e:
        print(f'[T2b-2] Tick {_last_tick} ERROR: {e}')
        import traceback; traceback.print_exc(); break

# Step 7: Report
print(f'\n=== T2b-2 RESULT ===')
print(f'Ticks run: {_last_tick}')
print(f'NPC_SPOKE captured: {len(_captured)}')
print(f'Counters: npc_spoke={_h.counters.npc_spoke} decision_events={_h.counters.decision_events}')
print(f'Events by type: {_h.counters.events_by_type}')
for _idx, _ev in enumerate(_captured):
    print(f'\n--- NPC_SPOKE #{_idx+1} ---')
    print(f'speaker:     {_ev["source"]}')
    print(f'audience:    {_ev["target_id"]}')
    print(f'topic:       {_ev["topic"]}')
    print(f'intent_type: {_ev["intent_type"]}')
    print(f'text:        {_ev["text"]}')

# Step 8: Cleanup
_h.dispose()
print('\n[T2b-2] Done.')
