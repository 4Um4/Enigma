"""
path: backend/tests/sandbox/SUPERBOX/scenarios/smoke_goran_alpha.py
Назначение: SMOKE-GORAN (α-M) — Causal Observability Probe (Motivated Environment).
    Измерение вероятности возникновения причинной цепочки:
    STEAL → OBSERVATION → BELIEF → COMMUNICATION → PROPAGATION.
    Режим α-M: принудительная установка will_state="deceptive" для thief_shadow
    через легальный кэш LifeEngine, чтобы моделировать мотивацию без инъекции событий.
Зависимости: app.services.events.event_bus, game_loop_builder, logging
Основные сущности: CausalState, QueueLogHandler, run_smoke, analyze_results
"""
import sys
import tempfile
import logging
from pathlib import Path
from collections import defaultdict

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings

# Изоляция saves и включение MockProvider ДО импорта сервисов
settings.saves_dir = tempfile.mkdtemp(prefix="smoke_goran_alpha_")
settings.environment = "development"  # Разрешает MockProvider для ambient LLM-вызовов

from app.services.events.event_bus import get_event_bus
from app.services.events.event_types import EventType
from app.services.game_loop_builder import build_game_loop

CAMPAIGN = "Open_road"
N_TICKS = 500
THIEF_ID = "thief_shadow"

class CausalState:
    """Хранилище для шпиона."""
    events = []
    ambient_dropped = 0
    canonical_dropped = 0
    canonical_overflows = 0

SPY = CausalState()

def _spy_handler(event):
    SPY.events.append(event)

class QueueLogHandler(logging.Handler):
    """Перехват логов для счётчиков потерь (022, 027, 038)."""
    def emit(self, record):
        msg = self.format(record)
        if "[DLG_QUEUE] OVERFLOW: Dropped canonical" in msg:
            SPY.canonical_dropped += 1
        elif "[DLG_QUEUE] OVERFLOW: Dropped ambient" in msg:
            SPY.ambient_dropped += 1
        elif "[DLG_QUEUE] OVERFLOW CRITICAL" in msg:
            SPY.canonical_overflows += 1

def run_smoke():
    logging.basicConfig(level=logging.INFO)
    _logger = logging.getLogger()
    _handler = QueueLogHandler()
    _handler.setLevel(logging.WARNING)
    _logger.addHandler(_handler)

    bus = get_event_bus()
    for et in EventType:
        bus.subscribe(et, _spy_handler)

    # α-M (Motivated Environment): Monkey-patch OpportunityEngine
    # Чтобы изолировать тест каузальной цепочки от сложности генерации мотивации (WillpowerGate/BreakProgress),
    # мы заставляем OpportunityEngine всегда разрешать скрытые действия с максимальным score.
    from app.services.economy.opportunity_engine import OpportunityEngine, OpportunityResult
    
    @staticmethod
    def _patched_calculate(ctx, will_state):
        return OpportunityResult(
            score=1.0,
            hidden_action_allowed=True,
            unlocked_intents=frozenset(["steal"]),
            score_trace={"reason": "smoke_test_forced"}
        )
    
    OpportunityEngine.calculate = _patched_calculate
    print("--- SMOKE-GORAN ALPHA-M: OpportunityEngine patched (forced STEAL availability) ---")

    game_loop = build_game_loop(data_dir=BACKEND_ROOT.parent / "data")

    print(f"--- SMOKE-GORAN ALPHA: Running {N_TICKS} ticks ---")
    for i in range(N_TICKS):
        game_loop.idle_tick(CAMPAIGN)

    print("--- SMOKE-GORAN ALPHA: Analyzing results ---")
    analyze_results(game_loop)

def _get_event_type(e):
    t = e.type
    if hasattr(t, 'value'):
        return t.value
    return t

def _get_prop_data(prop):
    """Безопасное извлечение данных из Proposition."""
    if not prop: return None, None, None
    pred = getattr(prop, "predicate", None)
    pred_val = pred.value if pred else getattr(prop, "predicate", "")
    return getattr(prop, "subject_id", None), str(pred_val).upper(), getattr(prop, "object_id", None)

def analyze_results(game_loop):
    events = SPY.events
    thefts = [e for e in events if _get_event_type(e) == EventType.THEFT.value]
    claims = [e for e in events if _get_event_type(e) == EventType.COMMUNICATION_CLAIM.value]

    # M1: Crime
    total_thefts = len(thefts)
    thefts_per_tick = total_thefts / N_TICKS

    # M2 & M3: Observation & Epistemic conversion
    witnessed_thefts = 0
    witnesses_with_belief = 0
    epistemic_store = getattr(game_loop._tick_orch, "_epistemic_store", None)

    for t in thefts:
        thief_id = t.source
        payload = t.payload or {}
        obj_id = payload.get("target_id", "unknown")
        tick_t = t.tick

        witness_found = False
        belief_confirmed = False
        
        for c in claims:
            c_payload = c.payload or {}
            prop = c_payload.get("proposition")
            if not prop:
                prop = c_payload
            
            subj, pred_str, obj = _get_prop_data(prop)
            
            if pred_str == "STOLE" and subj == thief_id and obj == obj_id:
                if c.tick >= tick_t and c.tick <= tick_t + 5:
                    witness_id = c.source or c_payload.get("speaker_id")
                    witness_found = True
                    
                    if epistemic_store and witness_id:
                        try:
                            recs = epistemic_store.get_all_for_agent(witness_id)
                            for rec in recs:
                                if str(rec.proposition.predicate.value).upper() == "STOLE" and rec.proposition.subject_id == thief_id:
                                    belief_confirmed = True
                                    break
                        except Exception:
                            pass
                    break
        
        if witness_found:
            witnessed_thefts += 1
            if belief_confirmed:
                witnesses_with_belief += 1

    witness_rate = (witnessed_thefts / total_thefts) if total_thefts > 0 else 0.0
    belief_conversion_rate = (witnesses_with_belief / witnessed_thefts) if witnessed_thefts > 0 else 0.0

    # M4: Causal integrity (FAIL if canonical_dropped > 0)
    canonical_dropped = SPY.canonical_dropped
    canonical_loss_rate = canonical_dropped  # ambient drop is normal, overflow is critical

    # M5: Propagation
    stole_claims = []
    listeners = set()
    for c in claims:
        c_payload = c.payload or {}
        prop = c_payload.get("proposition")
        if not prop: prop = c_payload
        _, pred_str, _ = _get_prop_data(prop)
        if pred_str == "STOLE":
            stole_claims.append(c)
            listeners.add(c.source or c_payload.get("speaker_id"))
            
    propagation_rate = (len(listeners) / len(stole_claims)) if len(stole_claims) > 0 else 0.0

    # M6: Emergent outcomes
    fate_tracker = getattr(game_loop.mvp_controller, "fate_tracker", None)
    fate_outcomes = defaultdict(int)
    if fate_tracker:
        for ev in getattr(fate_tracker, "_events", []):
            fate_outcomes[ev.event_type.value] += 1

    print("\n" + "="*40)
    print(" SMOKE-GORAN ALPHA-M REPORT")
    print("="*40)
    print(f"Ticks simulated: {N_TICKS}")
    print("\n[1] CRIME")
    print(f"  Total thefts: {total_thefts}")
    print(f"  Thefts per tick: {thefts_per_tick:.4f}")
    
    print("\n[2] OBSERVATION")
    print(f"  Thefts with witness: {witnessed_thefts}")
    print(f"  Witness rate: {witness_rate:.2%}")
    
    print("\n[3] EPISTEMIC CONVERSION")
    print(f"  Witnesses with belief: {witnesses_with_belief}")
    print(f"  Belief conversion rate: {belief_conversion_rate:.2%}")
    
    print("\n[4] CAUSAL INTEGRITY (FAIL if canonical_dropped > 0)")
    print(f"  Ambient dropped (expected): {SPY.ambient_dropped}")
    print(f"  Canonical dropped (CRITICAL): {canonical_dropped}")
    print(f"  Canonical overflows (WARNING): {SPY.canonical_overflows}")
    print(f"  Canonical loss rate: {canonical_loss_rate}")
    
    print("\n[5] PROPAGATION")
    print(f"  STOLE claims: {len(stole_claims)}")
    print(f"  Unique listeners: {len(listeners)}")
    print(f"  Propagation rate: {propagation_rate:.2f}")
    
    print("\n[6] EMERGENT OUTCOMES (Secondary)")
    for k, v in fate_outcomes.items():
        print(f"  {k}: {v}")
        
    print("="*40)
    if canonical_loss_rate > 0:
        print(" VERDICT: RED (Canonical loss detected)")
    elif total_thefts == 0:
        print(" VERDICT: YELLOW (No emergent crime even with motivation)")
    elif witness_rate < 0.1 or belief_conversion_rate < 0.5:
        print(" VERDICT: YELLOW (Chain breaking at observation/belief)")
    else:
        print(" VERDICT: GREEN (Causal chain emerges)")
    print("="*40)

    # --- 027.1 ARCHAEOLOGY: ANALYZE STUCK CANONICAL TASKS ---
    print("\n" + "="*40)
    print(" 027.1 ARCHAEOLOGY: QUEUE SATURATION SHAPE")
    print("="*40)
    queue = getattr(game_loop._task_scheduler, "_dialogue_queue", None)
    if queue and hasattr(queue, '_heap'):
        heap = queue._heap
        print(f"Total tasks stuck in heap: {len(heap)}")
        
        from collections import Counter
        task_keys = Counter()
        
        for item in heap:
            # Извлекаем данные из payload задачи
            task_dict = item.payload.get("task_dict", {})
            speaker = item.payload.get("speaker_id", "unknown")
            intent = task_dict.get("payload", {}).get("intent_type", "unknown")
            
            prop = task_dict.get("payload", {}).get("proposition")
            prop_str = "no_prop"
            if prop:
                # Если prop - это объект, пытаемся вытащить поля
                subj = getattr(prop, "subject_id", "?")
                pred = getattr(prop, "predicate", "?")
                if hasattr(pred, "value"): pred = pred.value
                obj = getattr(prop, "object_id", "?")
                prop_str = f"{subj}_{pred}_{obj}"
            
            task_keys[(speaker, intent, prop_str)] += 1
            
        print("Distribution of stuck canonical tasks (Speaker, Intent, Proposition):")
        for k, v in task_keys.most_common(15):
            print(f"  {v:>4}x | Speaker: {k[0]:<20} | Intent: {k[1]:<15} | Prop: {k[2]}")
    else:
        print("DialogueQueue not found.")
    print("="*40)

if __name__ == "__main__":
    run_smoke()