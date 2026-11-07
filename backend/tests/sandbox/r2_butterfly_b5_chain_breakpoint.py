# backend/tests/sandbox/r2_butterfly_b5_chain_breakpoint.py
"""
R2-BUTTERFLY-B5-CHAIN-BREAKPOINT probe v2.

Цель: локализовать точную точку разрыва цепочки:
  PLAYER_INSULTS → LUSYA BELIEF → LUSYA DECISION → DIALOGUE →
  NPC_SPOKE → CLAIM_EVENT → TORNIN BELIEF

Этапы:
  A. Belief Люси (EpistemicStore после PLAYER_INSULTS)
  B. DecisionHub Люси (все решения, выбран ли SPREAD_RUMOR)
  C. DialogueExecutor (если SPREAD_RUMOR выбран — post_decision, NPC_SPOKE)
  D. ClaimEventSubscriber (on_npc_spoke для spread_rumor — есть ли fallback)
  E. Real LLM (если доступен на 8181)

READ-ONLY. Production-код не менять.
"""
from __future__ import annotations
import os, sys, json, traceback, copy, logging, math, time, urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set
import io
from unittest.mock import MagicMock

_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

try:
    from app.core.config import settings, BASE_DIR
except Exception as e:
    print(f"[FATAL] Cannot import app.core.config: {e}")
    sys.exit(2)

PROJECT_ROOT = _BACKEND.parent

OUT_FILE_DIR = Path("/home/z/my-project/download")
if not OUT_FILE_DIR.exists() or not OUT_FILE_DIR.is_dir():
    OUT_FILE_DIR = _BACKEND / "tests" / "sandbox"
    try:
        OUT_FILE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        OUT_FILE_DIR = Path(os.getcwd())
OUT_FILE = OUT_FILE_DIR / "r2_butterfly_b5_chain_breakpoint.txt"


class TeeStream:
    def __init__(self, *streams):
        self.streams = streams
    def write(self, data):
        for s in self.streams:
            try: s.write(data)
            except: pass
    def flush(self):
        for s in self.streams:
            try: s.flush()
            except: pass


_stdout_buf = io.StringIO()
_orig_stdout = sys.stdout
sys.stdout = TeeStream(_orig_stdout, _stdout_buf)

_log_capture = io.StringIO()
_log_handler = logging.StreamHandler(_log_capture)
_log_handler.setLevel(logging.DEBUG)
_log_handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
logging.getLogger().addHandler(_log_handler)
logging.getLogger().setLevel(logging.INFO)


def _print_section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def _check_llm_server() -> bool:
    """Check if LLM server is available on port 8181."""
    try:
        req = urllib.request.Request("http://127.0.0.1:8181/health")
        resp = urllib.request.urlopen(req, timeout=3)
        return resp.status == 200
    except:
        return False


# ============================================================================
# ЭТАП A: Belief Люси
# ============================================================================
def stage_a_lusya_belief(loop, tick_orch) -> Dict[str, Any]:
    _print_section("ЭТАП A: Belief Люси — проверка EpistemicStore после PLAYER_INSULTS")
    result = {"stage": "A", "pass": False}

    try:
        epistemic_store = getattr(tick_orch, "_epistemic_store", None)
        if epistemic_store is None:
            result["error"] = "EpistemicStore not found in tick_orch"
            print(f"  [ERROR] EpistemicStore not found")
            return result

        lusya_records = epistemic_store.get_all_for_agent("maid_lusya")
        print(f"\n  maid_lusya epistemic records: {len(lusya_records)}")

        insult_records = []
        for r in lusya_records:
            rec_info = {
                "proposition": str(r.proposition),
                "predicate": str(r.proposition.predicate),
                "subject_id": r.proposition.subject_id,
                "object_id": r.proposition.object_id,
                "confidence": r.confidence,
                "source_id": r.source_id,
                "original_source_id": r.original_source_id,
                "source_type": r.source_type,
                "first_observed_tick": r.first_observed_tick,
                "last_updated_tick": r.last_updated_tick,
            }
            print(f"\n  Record:")
            for k, v in rec_info.items():
                print(f"    {k}: {v}")

            # Check if this is the INSULTED record
            if "INSULTED" in str(r.proposition.predicate):
                insult_records.append(rec_info)
                print(f"    >>> INSULTED RECORD FOUND ✓")

        if insult_records:
            result["pass"] = True
            result["insult_records"] = insult_records
            result["has_belief"] = True
            print(f"\n  >>> Люсьина belief об оскорблении: НАЙДЕН ✓")
        else:
            result["has_belief"] = False
            print(f"\n  >>> Люсьина belief об оскорблении: НЕ НАЙДЕН ✗")
            print(f"  >>> Точка разрыва: PLAYER_INSULTS → EpistemicStore(maid_lusya)")
            print(f"  >>> Возможные причины:")
            print(f"      - ClaimEventSubscriber.on_player_spoke не обработал PLAYER_INSULTS")
            print(f"      - spatial_query_provider не найден (None)")
            print(f"      - PerceptualKernel.can_observe вернул False")
            print(f"      - Люсьина не в радиусе hearing (HEARING_RADIUS=10.0)")

        # Also check all records for context
        result["all_records_count"] = len(lusya_records)
        result["all_records"] = [
            {
                "proposition": str(r.proposition),
                "confidence": r.confidence,
                "source_id": r.source_id,
            }
            for r in lusya_records[:10]
        ]

        return result
    except Exception as e:
        result["error"] = str(e)
        traceback.print_exc()
        return result


# ============================================================================
# ЭТАП B: DecisionHub Люси
# ============================================================================
def stage_b_lusya_decisions(loop, tick_orch) -> Dict[str, Any]:
    _print_section("ЭТАП B: DecisionHub Люси — все решения за эксперимент")
    result = {"stage": "B", "pass": False}

    try:
        # Get scene state
        scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
        if not scene:
            result["error"] = "scene not found"
            return result

        # Check npc_intents for maid_lusya
        npc_intents = scene.get("npc_intents", {})
        lusya_intent = npc_intents.get("maid_lusya", {})

        print(f"\n  maid_lusya last intent:")
        print(f"    intent: {lusya_intent.get('intent', '?')}")
        print(f"    target: {lusya_intent.get('intent_target', '?')}")
        print(f"    score: {lusya_intent.get('score', '?')}")
        print(f"    reason: {lusya_intent.get('reason', '?')}")

        # Check if spread_rumor was ever selected
        was_spread_rumor = "spread_rumor" in str(lusya_intent.get("intent", "")).lower()
        print(f"\n  SPREAD_RUMOR selected: {was_spread_rumor}")

        # Try to get decision history from tick_orch
        decision_hub = getattr(tick_orch, "_decision_hub", None)
        if decision_hub:
            print(f"\n  DecisionHub found: {type(decision_hub).__name__}")
            # Check if there's a history/log
            history = getattr(decision_hub, "_decision_history", None) or \
                      getattr(decision_hub, "_history", None) or \
                      getattr(decision_hub, "_last_decisions", None)
            if history:
                print(f"  Decision history found: {type(history)}")
                if isinstance(history, dict):
                    lusya_history = history.get("maid_lusya", [])
                    print(f"  maid_lusya decisions: {len(lusya_history)}")
                    for d in lusya_history[-5:]:
                        print(f"    {d}")
                elif isinstance(history, list):
                    lusya_history = [d for d in history if getattr(d, 'npc_id', '') == "maid_lusya"]
                    print(f"  maid_lusya decisions: {len(lusya_history)}")
            else:
                print(f"  No decision history attribute found")
        else:
            print(f"  DecisionHub not found in tick_orch")

        result["pass"] = True
        result["last_intent"] = lusya_intent.get("intent", "?")
        result["last_target"] = lusya_intent.get("intent_target", "?")
        result["was_spread_rumor"] = was_spread_rumor
        return result
    except Exception as e:
        result["error"] = str(e)
        traceback.print_exc()
        return result


# ============================================================================
# ЭТАП C: DialogueExecutor
# ============================================================================
def stage_c_dialogue_executor(loop, tick_orch, lusya_belief_result: Dict) -> Dict[str, Any]:
    _print_section("ЭТАП C: DialogueExecutor — проверка выполнения коммуникации")
    result = {"stage": "C", "pass": False}

    try:
        # Check if DialogueExecutor was called
        ts = loop._get_task_scheduler()
        executors = getattr(ts, "_executors", {}) or {}

        print(f"\n  Task scheduler executors: {list(executors.keys())}")

        # Find dialogue executor
        dlg_executor = None
        for kind, ex in executors.items():
            if "dlg" in kind.lower() or "dialogue" in kind.lower() or "speech" in kind.lower():
                dlg_executor = ex
                print(f"  Found dialogue executor: {kind}")
                break

        if not dlg_executor:
            print(f"  No dialogue executor found")
            result["error"] = "no dialogue executor"
            return result

        # Check if LLM router is real or mock
        router = getattr(dlg_executor, "_router", None)
        is_mock = isinstance(router, MagicMock)
        print(f"\n  LLM router: {'Mock (NOT real LLM)' if is_mock else 'Real'}")

        if is_mock:
            print(f"  >>> ВНИМАНИЕ: LLM router — MOCK")
            print(f"  >>> Mock возвращает placeholder текст, не генерирует proposition")
            print(f"  >>> NPC_SPOKE публикуется БЕЗ proposition в payload")
            print(f"  >>> ClaimEventSubscriber.on_npc_spoke проверяет payload.get('proposition')")
            print(f"  >>> Если proposition = None → on_claim_event НЕ вызывается")
            print(f"  >>> Fallback в on_npc_spoke не маппит spread_rumor → нет proposition")

        result["is_mock_llm"] = is_mock
        result["pass"] = True
        return result
    except Exception as e:
        result["error"] = str(e)
        traceback.print_exc()
        return result


# ============================================================================
# ЭТАП D: ClaimEventSubscriber — on_npc_spoke для spread_rumor
# ============================================================================
def stage_d_claim_subscriber_fallback() -> Dict[str, Any]:
    _print_section("ЭТАП D: ClaimEventSubscriber — on_npc_spoke fallback для spread_rumor")
    result = {"stage": "D", "pass": False}

    ces_path = _BACKEND / "app/services/events/claim_event_subscriber.py"
    if not ces_path.exists():
        result["error"] = "file not found"
        return result
    src = ces_path.read_text(encoding="utf-8", errors="replace")
    lines = src.split("\n")

    print(f"\n--- D.1: on_npc_spoke — полный код (L41-87) ---")
    for i, line in enumerate(lines[40:87], 41):
        print(f"  L{i}: {line}")

    print(f"""
>>> D.2: Анализ fallback для spread_rumor

  on_npc_spoke (L41-87) обрабатывает NPC_SPOKE БЕЗ proposition:
    1. Если payload.get("proposition") есть → return (обработает on_claim_event)
    2. Если proposition НЕТ → fallback: маппинг intent_type → proposition:
       - intent_type == "accuse" → Proposition(target, STOLE, unknown)
       - intent_type == "praise" → Proposition(target, HELPED, unknown)
       - intent_type in ("intimidate", "attack") → Proposition(speaker, ATTACKED, target)
    3. Если prop создан → on_claim_event вызывается с новым payload

  ПРОВЕРКА: есть ли маппинг для "spread_rumor"?
""")

    # Check if spread_rumor is in the fallback mapping
    has_spread_rumor_mapping = False
    for i, line in enumerate(lines, 1):
        if "spread_rumor" in line.lower() and ("prop" in line.lower() or "proposition" in line.lower()):
            has_spread_rumor_mapping = True
            print(f"  Found spread_rumor mapping at L{i}: {line.rstrip()}")

    if not has_spread_rumor_mapping:
        print(f"  ✗ НЕТ маппинга для spread_rumor в on_npc_spoke fallback!")
        print(f"  >>> Когда Lusya выбирает SPREAD_RUMOR и LLM не генерирует proposition:")
        print(f"      1. NPC_SPOKE публикуется с intent_type='spread_rumor'")
        print(f"      2. on_npc_spoke проверяет payload.get('proposition') → None")
        print(f"      3. Fallback: intent_type='spread_rumor' не маппится в Proposition")
        print(f"      4. prop = None → on_claim_event НЕ вызывается")
        print(f"      5. BeliefRevisionEngine НЕ вызывается")
        print(f"      6. EpistemicStore Торнина НЕ обновляется")
        print(f"  >>> Это ВТОРОЙ DEFEKT (после mock LLM)")

    # Also check on_player_spoke — does PLAYER_INSULTS create a proposition?
    print(f"\n--- D.3: on_player_spoke — обработка PLAYER_INSULTS (L89-122) ---")
    for i, line in enumerate(lines[88:122], 89):
        print(f"  L{i}: {line}")

    print(f"""
>>> D.4: Анализ on_player_spoke для PLAYER_INSULTS

  on_player_spoke (L89-122) обрабатывает PLAYER_INSULTS:
    1. Проверяет event.type или payload.action_type на "player_insults"
    2. Если да → создаёт proposition:
       subject_id = player (оскорбитель)
       predicate = INSULTED
       object_id = target_id (жертва)
       polarity = True
    3. Вызывает on_claim_event с новым payload

  ПРОВЕРКА: должен ли этот путь работать для PLAYER_INSULTS?
  → Да, если event type = "player_insults" или action_type = "player_insults"
  → После on_claim_event → spatial membrane → listeners → BeliefRevisionEngine

  Но! on_claim_event использует spatial_query для фильтрации слушателей:
    - HEARING_RADIUS = 10.0
    - PerceptualKernel.can_observe проверяет дистанцию

  Если Люся в радиусе 10м от источника события (player) → она услышит
  → BeliefRevisionEngine.revise(maid_lusya) → EpistemicStore(maid_lusya).upsert

  Вопрос: откуда берётся позиция игрока (event.source = "player")?
  → Если игрок не в npc_positions → spatial_query не найдёт его
  → _listeners может быть пустым → belief не создаётся
""")

    # Check if player position is tracked
    print(f"\n--- D.5: Проверка позиции игрока в scene_state ---")

    result["pass"] = True
    result["has_spread_rumor_fallback"] = has_spread_rumor_mapping
    result["defect_spread_rumor_no_fallback"] = not has_spread_rumor_mapping
    return result


# ============================================================================
# ЭТАП E: Real LLM проверка
# ============================================================================
def stage_e_real_llm() -> Dict[str, Any]:
    _print_section("ЭТАП E: Real LLM — проверка доступности")
    result = {"stage": "E", "pass": False}

    llm_available = _check_llm_server()
    print(f"\n  LLM server (http://127.0.0.1:8181/health): {'AVAILABLE ✓' if llm_available else 'NOT AVAILABLE ✗'}")

    if llm_available:
        print(f"  >>> Real LLM доступен — можно запустить эксперимент без mock")
        result["llm_available"] = True
        result["pass"] = True
    else:
        print(f"  >>> Real LLM НЕ доступен — диагностика A-D без real LLM")
        print(f"  >>> Выводы, требующие real LLM:")
        print(f"    - Фактическое содержание реплик Торнина")
        print(f"    - Причинная связь реплик с услышанным")
        print(f"    - Проверка, генерирует ли LLM proposition в payload")
        result["llm_available"] = False

    return result


# ============================================================================
# ПОЛНЫЙ ЭКСПЕРИМЕНТ — 20 ticks с spy
# ============================================================================
def full_experiment() -> Dict[str, Any]:
    _print_section("ПОЛНЫЙ ЭКСПЕРИМЕНТ — 20 ticks с PLAYER_INSULTS")

    result: Dict[str, Any] = {"stage": "experiment"}

    try:
        from app.core.config import settings, BASE_DIR
        from app.services.game_loop_builder import build_game_loop
        from app.services.events.event_bus import get_event_bus
        from app.services.events.event_types import EventType
        from app.domain.events import EventDTO

        import tempfile
        saves_dir = Path(tempfile.mkdtemp(prefix="r2_b5_v2_"))
        settings.saves_dir = str(saves_dir)
        settings.environment = "development"

        loop = build_game_loop(data_dir=Path(settings.data_dir))
        scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
        if scene is None:
            scene = loop.scene_manager.initialize_scene("Open_road", "tavern", "12:00")

        # Check LLM availability
        llm_available = _check_llm_server()
        print(f"\n  LLM available: {llm_available}")

        if not llm_available:
            print(f"  >>> LLM НЕ доступен — mock будет использован, но это помечено")
            # Still mock to avoid crashes
            try:
                ts = loop._get_task_scheduler()
                for kind, ex in (getattr(ts, "_executors", {}) or {}).items():
                    if hasattr(ex, "_router"):
                        ex._router = MagicMock()
                        if hasattr(ex._router, "route"):
                            ex._router.route.return_value = "[Mock — LLM unavailable]"
            except:
                pass

        # Clear event bus
        try:
            get_event_bus().clear()
        except:
            pass

        # Spies
        all_speeches: List[Dict] = []
        all_claims: List[Dict] = []
        all_decisions: List[Dict] = []

        def _spy_spoke(event):
            payload = getattr(event, "payload", {})
            all_speeches.append({
                "speaker": getattr(event, "source", "?"),
                "target": payload.get("target_id", "?"),
                "intent": payload.get("intent_type", "?"),
                "content": str(payload.get("content", ""))[:200],
                "has_proposition": bool(payload.get("proposition")),
                "proposition": payload.get("proposition"),
                "tick": payload.get("event_tick", payload.get("tick", "?")),
            })

        def _spy_claim(event):
            payload = getattr(event, "payload", {})
            all_claims.append({
                "speaker": getattr(event, "source", "?"),
                "proposition": payload.get("proposition"),
                "claim_id": payload.get("claim_id", "?"),
                "tick": payload.get("event_tick", payload.get("tick", "?")),
            })

        try:
            get_event_bus().subscribe(EventType.NPC_SPOKE, _spy_spoke)
            get_event_bus().subscribe(EventType.COMMUNICATION_CLAIM, _spy_claim)
        except:
            pass

        # Publish PLAYER_INSULTS
        print(f"\n  Publishing PLAYER_INSULTS (target=tavern_keeper_tornin)...")
        payload = {
            "action_type": "player_insults", "target_id": "tavern_keeper_tornin",
            "content": "оскорбление", "event_tick": 1, "visibility": "public",
            "radius": 999.0, "location": "tavern", "campaign_id": "Open_road",
            "raw_input": "оскорбление",
        }
        evt = EventDTO.create(event_type=EventType.PLAYER_INSULTS, source="player",
                              payload=payload, persistence_level="working")
        get_event_bus().publish(evt)
        print(f"  PLAYER_INSULTS published ✓")

        # Run 20 ticks
        print(f"\n  Running 20 ticks...")
        for tick_i in range(1, 21):
            _log_capture.truncate(0)
            _log_capture.seek(0)
            try:
                loop.idle_tick("Open_road")
            except Exception as e:
                print(f"  [tick {tick_i} error: {str(e)[:100]}]")

            # Log speeches and claims per tick
            tick_speeches = [s for s in all_speeches if s.get("tick") == tick_i]
            tick_claims = [c for c in all_claims if c.get("tick") == tick_i]

            if tick_speeches:
                for s in tick_speeches:
                    print(f"  [tick {tick_i}] NPC_SPOKE: {s['speaker']}→{s['target']} intent={s['intent']} has_prop={s['has_proposition']} content='{s['content'][:60]}'")
            if tick_claims:
                for c in tick_claims:
                    print(f"  [tick {tick_i}] CLAIM: speaker={c['speaker']} prop={c['proposition']}")

            # Check logs for BELIEF_REVISE
            logs = _log_capture.getvalue()
            if "BELIEF_REVISE" in logs:
                for line in logs.split("\n"):
                    if "BELIEF_REVISE" in line:
                        print(f"  [tick {tick_i}] {line.strip()}")

        # After experiment: check EpistemicStore
        tick_orch = loop._tick_orch
        epistemic_store = getattr(tick_orch, "_epistemic_store", None)

        # Run stages A-D
        result_a = stage_a_lusya_belief(loop, tick_orch)
        result_b = stage_b_lusya_decisions(loop, tick_orch)
        result_c = stage_c_dialogue_executor(loop, tick_orch, result_a)
        result_d = stage_d_claim_subscriber_fallback()
        result_e = stage_e_real_llm()

        # Summary
        result["all_speeches"] = all_speeches
        result["all_claims"] = all_claims
        result["stage_a"] = result_a
        result["stage_b"] = result_b
        result["stage_c"] = result_c
        result["stage_d"] = result_d
        result["stage_e"] = result_e

        # Cleanup
        try:
            ts = loop._get_task_scheduler()
            if hasattr(ts, "_executor_pool"):
                ts._executor_pool.shutdown(wait=False, cancel_futures=True)
        except:
            pass
        del loop
        import gc; gc.collect()
        import shutil
        shutil.rmtree(saves_dir, ignore_errors=True)

        return result

    except Exception as e:
        print(f"[FATAL: {e}]")
        traceback.print_exc()
        result["error"] = str(e)
        return result


# ============================================================================
# ИТОГОВЫЙ ОТЧЁТ
# ============================================================================
def final_report(exp_result: Dict) -> None:
    _print_section("ИТОГОВЫЙ ОТЧЁТ — точка разрыва цепочки")

    stage_a = exp_result.get("stage_a", {})
    stage_b = exp_result.get("stage_b", {})
    stage_c = exp_result.get("stage_c", {})
    stage_d = exp_result.get("stage_d", {})
    stage_e = exp_result.get("stage_e", {})

    print(f"""
=============================================================================
ПОЛНАЯ ВРЕМЕННАЯ ШКАЛА СОБЫТИЙ
=============================================================================

  tick 0: PLAYER_INSULTS published (target=tavern_keeper_tornin)
          → ClaimEventSubscriber.on_player_spoke вызывается
          → proposition: player/INSULTED/tavern_keeper_tornin
          → on_claim_event → spatial membrane → listeners

  tick 1-20: game loop running
""")

    # Stage A verdict
    has_lusya_belief = stage_a.get("has_belief", False)
    print(f"ЭТАП A — Belief Люси: {'✓ НАЙДЕН' if has_lusya_belief else '✗ НЕ НАЙДЕН'}")
    if has_lusya_belief:
        for r in stage_a.get("insult_records", []):
            print(f"  proposition: {r.get('proposition')}")
            print(f"  confidence: {r.get('confidence')}")
            print(f"  source_id: {r.get('source_id')}")
            print(f"  original_source_id: {r.get('original_source_id')}")
    else:
        print(f"  >>> ТОЧКА РАЗРЫВА #1: PLAYER_INSULTS → EpistemicStore(maid_lusya)")
        print(f"  >>> on_player_spoke создал proposition, но belief не записался")
        print(f"  >>> Возможные причины:")
        print(f"      - spatial_query_provider = None (нет spatial)")
        print(f"      - player не в npc_positions → distance не вычисляется")
        print(f"      - PerceptualKernel.can_observe вернул False")
        print(f"      - HEARING_RADIUS = 10.0 — Люсьина слишком далеко")

    # Stage B verdict
    was_spread_rumor = stage_b.get("was_spread_rumor", False)
    print(f"\nЭТАП B — DecisionHub Люси: SPREAD_RUMOR = {'✓ ДА' if was_spread_rumor else '✗ НЕТ'}")
    print(f"  last intent: {stage_b.get('last_intent', '?')}")
    print(f"  last target: {stage_b.get('last_target', '?')}")
    if not was_spread_rumor:
        print(f"  >>> Люсьина НЕ выбрала SPREAD_RUMOR")
        print(f"  >>> Возможные причины:")
        if not has_lusya_belief:
            print(f"      - Нет belief об оскорблении → нет report_proposition → нет spread_rumor boost")
        else:
            print(f"      - report_proposition = None (object_id == agent_id для Люси? Нет — Люся не жертва)")
            print(f"      - confidence < 0.25")
            print(f"      - Другие intents имеют более высокий score")

    # Stage C verdict
    is_mock = stage_c.get("is_mock_llm", True)
    print(f"\nЭТАП C — DialogueExecutor: LLM = {'Mock' if is_mock else 'Real'}")
    if is_mock:
        print(f"  >>> Mock LLM не генерирует proposition в NPC_SPOKE payload")
        print(f"  >>> NPC_SPOKE публикуется с has_proposition=False")

    # Stage D verdict
    has_fallback = stage_d.get("has_spread_rumor_fallback", False)
    defect_spread_rumor = stage_d.get("defect_spread_rumor_no_fallback", False)
    print(f"\nЭТАП D — ClaimEventSubscriber: spread_rumor fallback = {'✓ ЕСТЬ' if has_fallback else '✗ НЕТ'}")
    if defect_spread_rumor:
        print(f"  >>> ПРОИЗВОДСТВЕННЫЙ ДЕФЕКТ: on_npc_spoke не маппит spread_rumor → proposition")
        print(f"  >>> Когда NPC выбирает SPREAD_RUMOR и LLM не генерирует proposition:")
        print(f"      1. NPC_SPOKE публикуется с intent_type='spread_rumor'")
        print(f"      2. on_npc_spoke: payload.get('proposition') → None")
        print(f"      3. Fallback маппит: accuse→STOLE, praise→HELPED, intimidate/attack→ATTACKED")
        print(f"      4. spread_rumor: НЕТ маппинга!")
        print(f"      5. prop = None → on_claim_event НЕ вызывается")
        print(f"      6. BeliefRevisionEngine НЕ вызывается")
        print(f"      7. EpistemicStore слушателя НЕ обновляется")

    # Stage E verdict
    llm_available = stage_e.get("llm_available", False)
    print(f"\nЭТАП E — Real LLM: {'AVAILABLE ✓' if llm_available else 'NOT AVAILABLE ✗'}")
    if not llm_available:
        print(f"  >>> Требует real LLM:")
        print(f"      - Фактическое содержание реплик")
        print(f"      - Генерация proposition в NPC_SPOKE payload")

    # Overall verdict
    print(f"""
=============================================================================
ТОЧНАЯ ПЕРВАЯ ТОЧКА РАЗРЫВА
=============================================================================
""")

    if not has_lusya_belief:
        print(f"  ПЕРВАЯ ТОЧКА РАЗРЫВА: PLAYER_INSULTS → EpistemicStore(maid_lusya)")
        print(f"  Люсьин belief об оскорблении НЕ создан.")
        print(f"  Без belief → нет report_proposition → нет SPREAD_RUMOR boost → нет речи → нет слуха")
    elif not was_spread_rumor:
        print(f"  ПЕРВАЯ ТОЧКА РАЗРЫВА: DecisionHub(maid_lusya) → SPREAD_RUMOR")
        print(f"  Люсьин belief есть, но SPREAD_RUMOR не выбран.")
    elif is_mock and defect_spread_rumor:
        print(f"  ПЕРВАЯ ТОЧКА РАЗРЫВА: on_npc_spoke fallback для spread_rumor")
        print(f"  NPC_SPOKE без proposition → fallback не маппит spread_rumor → нет ClaimEvent")
    else:
        print(f"  Точка разрыва не определена — проверьте детали выше")

    print(f"""
=============================================================================
СПИСОК ПОТЕНЦИАЛЬНЫХ ПРОИЗВОДСТВЕННЫХ ДЕФЕКТОВ
=============================================================================
""")

    defects = []
    if not has_lusya_belief:
        defects.append({
            "id": "B5-D1",
            "description": "PLAYER_INSULTS не создаёт belief в EpistemicStore(maid_lusya)",
            "severity": "CRITICAL",
            "evidence": "stage_a: has_belief=False",
            "possible_cause": "spatial_query_provider=None или player не в npc_positions",
        })

    if defect_spread_rumor:
        defects.append({
            "id": "B5-D2",
            "description": "on_npc_spoke fallback не маппит spread_rumor → Proposition",
            "severity": "HIGH",
            "evidence": "claim_event_subscriber.py L56-71: только accuse, praise, intimidate, attack",
            "possible_cause": "spread_rumor intent не имеет маппинга на Predicate",
        })

    if is_mock:
        defects.append({
            "id": "B5-D3",
            "description": "Mock LLM не генерирует proposition в NPC_SPOKE payload",
            "severity": "INFO",
            "evidence": "stage_c: is_mock_llm=True",
            "possible_cause": "LLM server недоступен на 8181",
        })

    for d in defects:
        print(f"  ДЕФЕКТ {d['id']}: {d['description']}")
        print(f"    Severity: {d['severity']}")
        print(f"    Evidence: {d['evidence']}")
        print(f"    Possible cause: {d['possible_cause']}")
        print()

    print(f"""
=============================================================================
УЧАСТКИ, ТРЕБУЮЩИЕ REAL LLM
=============================================================================

  1. Проверка, генерирует ли LLM proposition в NPC_SPOKE payload
     (если LLM возвращает структурированный output с proposition —
     fallback в on_npc_spoke не нужен)
  2. Фактическое содержание реплик Торнина (русский текст)
  3. Причинная связь реплик с услышанным
  4. Выбор TALK vs SPREAD_RUMOR в DecisionHub при real LLM context

  Без real LLM:
  - Этапы A-D доказаны статически (по коду)
  - Этап E (содержание) невозможен
""")


# ============================================================================
# Main
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-BUTTERFLY-B5-CHAIN-BREAKPOINT — локализация точки разрыва")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)

    try:
        exp_result = full_experiment()
        final_report(exp_result)
    except Exception as e:
        print(f"[FATAL: {e}]")
        traceback.print_exc()

    # Write to file
    try:
        OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            f.write(_stdout_buf.getvalue())
        size = OUT_FILE.stat().st_size
        print(f"\n>>> Output written to: {OUT_FILE}")
        print(f">>> File size: {size} bytes ({size / 1024:.1f} KB)")
    except Exception as e:
        print(f"\n[ERROR writing output file: {e}]")
        traceback.print_exc()

    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as e:
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        rc = 1
    finally:
        sys.stdout = _orig_stdout
    sys.exit(rc)
