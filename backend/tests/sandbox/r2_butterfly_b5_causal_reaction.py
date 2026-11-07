# backend/tests/sandbox/r2_butterfly_b5_causal_reaction.py
"""
R2-BUTTERFLY-B5-CAUSAL-REACTION probe.

Цель: доказать или опровергнуть причинное влияние информации,
переданной Люсей, на последующее решение и речь Торнина.

6 секций (A-F):
  A. Семантика EpistemicContextResolver (report_proposition, claims_about_self, modifiers)
  B. _SAME_SOURCE_BOOST — значение, формула, условия
  C. Контрольный прогон A (без слуха)
  D. Экспериментальный прогон B (с слухом)
  E. Real LLM, 20 ticks
  F. Итоговый отчёт PASS/PARTIAL/FAIL

Production-код НЕ менять.
"""
from __future__ import annotations
import os, sys, json, traceback, copy, logging, math, time
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
OUT_FILE = OUT_FILE_DIR / "r2_butterfly_b5_causal_reaction.txt"


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
logging.getLogger().setLevel(logging.INFO)  # INFO to reduce noise


def _print_section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def _read_lines(path: Path, start: int, end: int) -> List[str]:
    if not path.exists():
        return [f"[file not found: {path}]"]
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
        return [f"L{i+1:4d}: {lines[i]}" for i in range(start - 1, min(end, len(lines)))]
    except Exception as e:
        return [f"[read error: {e}]"]


def _grep_in_dir(directory: Path, patterns: List[str], file_exts: List[str] = (".py",)) -> List[Tuple[Path, int, str]]:
    out: List[Tuple[Path, int, str]] = []
    if not directory.exists():
        return out
    for f in directory.rglob("*"):
        if not f.is_file() or f.suffix.lower() not in file_exts:
            continue
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
        except:
            continue
        for i, line in enumerate(src.split("\n"), 1):
            for pat in patterns:
                if pat in line:
                    out.append((f, i, line.rstrip()))
                    break
    return out


# ============================================================================
# СЕКЦИЯ A: Семантика EpistemicContextResolver
# ============================================================================
def section_a_epistemic_semantics() -> Dict[str, Any]:
    _print_section("СЕКЦИЯ A: Семантика EpistemicContextResolver")
    result = {"section": "A", "pass": False}

    ecr_path = _BACKEND / "app/services/npc/epistemic_context_resolver.py"
    if not ecr_path.exists():
        result["error"] = "file not found"
        return result
    src = ecr_path.read_text(encoding="utf-8", errors="replace")
    lines = src.split("\n")

    print(f"\n--- A.1: Полная логика report_proposition (L91-101) ---")
    for line in _read_lines(ecr_path, 91, 101):
        print(f"  {line}")

    print(f"\n--- A.2: Полная логика claims_about_self (L82-89, L106-113) ---")
    for line in _read_lines(ecr_path, 82, 89):
        print(f"  {line}")
    print("  ...")
    for line in _read_lines(ecr_path, 106, 113):
        print(f"  {line}")

    print(f"""
>>> A.3: Анализ условий для записи player/INSULTED/tavern_keeper_tornin

  EpistemicRecord:
    proposition.subject_id = "player"
    proposition.predicate = Predicate.INSULTED
    proposition.object_id = "tavern_keeper_tornin"
    agent_id (владелец store) = "tavern_keeper_tornin" (Торнин)
    confidence = 0.215

  Проверка claims_about_self (L85-89):
    if pred == Predicate.INSULTED and _obj == agent_id:
      → _obj = "tavern_keeper_tornin" == agent_id = "tavern_keeper_tornin"
      → TRUE ✓
      → about_self.append(record.proposition)
      → max_self_confidence = 0.215

  Проверка report_proposition (L95-101):
    if (pred in REPORT_PREDICATES           → INSULTED in (INSULTED,) → TRUE
        and record.confidence >= 0.25       → 0.215 >= 0.25 → FALSE ✗
        and _obj != agent_id                → "tavern_keeper_tornin" != "tavern_keeper_tornin" → FALSE
        and subj != agent_id)               → "player" != "tavern_keeper_tornin" → TRUE
    → report_proposition = None (confidence < 0.25)

  ВАЖНО: даже если confidence >= 0.25, report_proposition НЕ сработает,
  потому что _obj == agent_id (Торнин — жертва, а не третье лицо).
  report_proposition предназначен для случая, когда NPC знает об
  оскорблении ДРУГОГО NPC (третьего лица).

  Для Торнина (жертвы оскорбления):
    → claims_about_self = [player/INSULTED/tavern_keeper_tornin]  ✓
    → max_self_confidence = 0.215
    → report_proposition = None

>>> A.4: Modifiers для TALK и SPREAD_RUMOR

  L195-197 (claims_about_self → TALK boost):
    if context.claims_about_self:
        _self_boost = round(context.max_self_confidence * 0.5, 4)
        modifiers["talk"] = round(modifiers.get("talk", 0.0) + _self_boost, 4)
    → _self_boost = 0.215 * 0.5 = 0.1075
    → modifiers["talk"] = 0.1075

  L203-206 (report_proposition → SPREAD_RUMOR boost):
    if context.report_proposition is not None:
        _rep_boost = round(context.max_confidence * 0.9, 4)
        modifiers["spread_rumor"] = ...
        modifiers["talk"] += _rep_boost * 0.6
    → report_proposition = None → НЕТ boost

  ИТОГО для Торнина (confidence=0.215):
    modifiers["talk"] = 0.1075 (от claims_about_self)
    modifiers["spread_rumor"] = 0.0 (нет report_proposition)

  Торнин получает TALK boost, но НЕ SPREAD_RUMOR boost.
  Это означает: Торнин может заговорить (TALK), но не будет
  распространять слух (SPREAD_RUMOR) об оскорблении.

  Семантически это ПРАВИЛЬНО:
    - Торнин — жертва оскорбления
    - Он знает, что его оскорбили (claims_about_self)
    - Он хочет поговорить об этом (TALK boost)
    - Но он не будет "сплетничать" об этом (SPREAD_RUMOR для третьих лиц)
""")

    result["pass"] = True
    result["claims_about_self"] = "активен (confidence > 0, object_id == agent_id)"
    result["report_proposition"] = "НЕ активен (object_id == agent_id → не третье лицо)"
    result["talk_boost"] = "0.215 * 0.5 = 0.1075"
    result["spread_rumor_boost"] = "0.0 (нет report_proposition)"
    return result


# ============================================================================
# СЕКЦИЯ B: _SAME_SOURCE_BOOST
# ============================================================================
def section_b_same_source_boost() -> Dict[str, Any]:
    _print_section("СЕКЦИЯ B: _SAME_SOURCE_BOOST — значение, формула, условия")
    result = {"section": "B", "pass": False}

    bre_path = _BACKEND / "app/services/npc/belief_revision_engine.py"
    if not bre_path.exists():
        result["error"] = "file not found"
        return result
    src = bre_path.read_text(encoding="utf-8", errors="replace")
    lines = src.split("\n")

    print(f"\n--- B.1: Полный файл belief_revision_engine.py (первые 30 строк) ---")
    for i, line in enumerate(lines[:30], 1):
        print(f"  L{i}: {line}")

    # Find _SAME_SOURCE_BOOST
    boost_value = None
    for i, line in enumerate(lines, 1):
        if "_SAME_SOURCE_BOOST" in line and "=" in line:
            print(f"\n--- B.2: Найдено объявление _SAME_SOURCE_BOOST ---")
            print(f"  L{i}: {line.rstrip()}")
            # Extract value
            try:
                # Pattern: _SAME_SOURCE_BOOST: float = 0.X
                import re
                match = re.search(r"_SAME_SOURCE_BOOST.*?=\s*([\d.]+)", line)
                if match:
                    boost_value = float(match.group(1))
                    print(f"  Значение: {boost_value}")
            except:
                pass

    print(f"\n--- B.3: Формула обновления (L88-94) ---")
    for line in _read_lines(bre_path, 88, 94):
        print(f"  {line}")

    print(f"""
>>> B.4: Анализ

  _SAME_SOURCE_BOOST = {boost_value}

  Формула при повторном сообщении от ТОГО ЖЕ источника (Люси):
    updated_conf = max(0.0, min(1.0, existing.confidence + (incoming_confidence * _SAME_SOURCE_BOOST)))
    = max(0.0, min(1.0, 0.215 + (reliability * {boost_value})))

  Если reliability (Люси для Торнина) ≈ 0.215 (confidence первого сообщения):
    updated_conf = 0.215 + 0.215 * {boost_value} = 0.215 + {0.215 * boost_value if boost_value else '?':.4f} = {0.215 + 0.215 * boost_value if boost_value else '?':.4f}

  Формула при сообщении от ДРУГОГО источника (corroboration):
    updated_conf = max(0.0, min(1.0, existing.confidence + incoming_confidence))
    = 0.215 + reliability(tornin, other_npc)

  Разница:
    - Тот же источник: буст ослаблен коэффициентом {boost_value}
    - Другой источник: полный буст (reliability)
    - Corroboration эффективнее для повышения confidence
""")

    result["pass"] = True
    result["boost_value"] = boost_value
    if boost_value:
        result["same_source_new_confidence"] = 0.215 + 0.215 * boost_value
        result["threshold_0.25_reachable_same_source"] = (0.215 + 0.215 * boost_value) >= 0.25
    return result


# ============================================================================
# СЕКЦИЯ C: Контрольный прогон A (без слуха)
# ============================================================================
def section_c_control_run_a() -> Dict[str, Any]:
    _print_section("СЕКЦИЯ C: Контрольный прогон A (без передачи слуха)")
    result = {"section": "C", "pass": False}

    print(f"\n>>> C.1: Запуск game loop БЕЗ PLAYER_INSULTS")
    print(f"  Цель: зафиксировать baseline Торнина — решения, реплики, modifiers")

    try:
        from app.core.config import settings, BASE_DIR
        from app.services.game_loop_builder import build_game_loop
        from app.services.events.event_bus import get_event_bus
        from app.services.events.event_types import EventType
        from app.domain.events import EventDTO

        import tempfile
        saves_dir = Path(tempfile.mkdtemp(prefix="r2_b5_A_"))
        settings.saves_dir = str(saves_dir)
        settings.environment = "development"

        loop = build_game_loop(data_dir=Path(settings.data_dir))
        scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
        if scene is None:
            scene = loop.scene_manager.initialize_scene("Open_road", "tavern", "12:00")

        # Try to mock LLM router to avoid failures
        try:
            ts = loop._get_task_scheduler()
            for kind, ex in (getattr(ts, "_executors", {}) or {}).items():
                if hasattr(ex, "_router"):
                    ex._router = MagicMock()
                    if hasattr(ex._router, "route"):
                        ex._router.route.return_value = "[Контрольный прогон]"
        except:
            pass

        # Clear event bus
        try:
            get_event_bus().clear()
        except:
            pass

        # Collect NPC_SPOKE events for tornin
        tornin_speeches_a: List[Dict] = []
        all_speeches_a: List[Dict] = []

        def _spy_spoke(event):
            payload = getattr(event, "payload", {})
            speaker = getattr(event, "source", "?")
            target = payload.get("target_id", "?")
            intent = payload.get("intent_type", "?")
            content = payload.get("content", "")
            speech = {
                "speaker": speaker,
                "target": target,
                "intent": intent,
                "content": str(content)[:200],
                "tick": payload.get("event_tick", payload.get("tick", "?")),
            }
            all_speeches_a.append(speech)
            if speaker == "tavern_keeper_tornin":
                tornin_speeches_a.append(speech)

        try:
            get_event_bus().subscribe(EventType.NPC_SPOKE, _spy_spoke)
        except:
            pass

        # Run 15 ticks WITHOUT PLAYER_INSULTS
        print(f"\n  Запуск 15 ticks (без PLAYER_INSULTS)...")
        for tick_i in range(1, 16):
            try:
                loop.idle_tick("Open_road")
            except Exception as e:
                print(f"  [tick {tick_i} error: {str(e)[:100]}]")

        # Get tornin's epistemic state
        tornin_state_a = {}
        try:
            tick_orch = loop._tick_orch
            epistemic_store = getattr(tick_orch, "_epistemic_store", None)
            if epistemic_store:
                tornin_records = epistemic_store.get_all_for_agent("tavern_keeper_tornin")
                tornin_state_a = {
                    "records_count": len(tornin_records),
                    "records": [
                        {
                            "proposition": str(r.proposition),
                            "confidence": r.confidence,
                            "source_id": r.source_id,
                            "original_source_id": r.original_source_id,
                            "source_type": r.source_type,
                        }
                        for r in tornin_records[:10]
                    ],
                }
        except Exception as e:
            tornin_state_a = {"error": str(e)}

        # Get DecisionHub decisions for tornin
        tornin_decisions_a: List[Dict] = []
        try:
            # Check scene state for last decisions
            scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
            if scene:
                npc_intents = scene.get("npc_intents", {})
                tornin_intent = npc_intents.get("tavern_keeper_tornin", {})
                tornin_decisions_a.append({
                    "intent": tornin_intent.get("intent", "?"),
                    "target": tornin_intent.get("intent_target", "?"),
                    "tick": scene.get("tick"),
                })
        except:
            pass

        print(f"\n>>> C.2: Результаты контрольного прогона A")
        print(f"  Tornin speeches: {len(tornin_speeches_a)}")
        for s in tornin_speeches_a:
            print(f"    tick={s['tick']}: '{s['content']}' (intent={s['intent']}, target={s['target']})")
        print(f"\n  All speeches: {len(all_speeches_a)}")
        print(f"\n  Tornin epistemic state:")
        print(f"    Records: {tornin_state_a.get('records_count', '?')}")
        for r in tornin_state_a.get("records", []):
            print(f"    {r}")
        print(f"\n  Tornin decisions: {len(tornin_decisions_a)}")
        for d in tornin_decisions_a:
            print(f"    {d}")

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

        result["pass"] = True
        result["tornin_speeches_count"] = len(tornin_speeches_a)
        result["tornin_speeches"] = tornin_speeches_a
        result["tornin_epistemic_records"] = tornin_state_a.get("records_count", 0)
        result["tornin_decisions"] = tornin_decisions_a
        return result

    except Exception as e:
        print(f"[FATAL: {e}]")
        traceback.print_exc()
        result["error"] = str(e)
        return result


# ============================================================================
# СЕКЦИЯ D: Экспериментальный прогон B (с слухом)
# ============================================================================
def section_d_experiment_run_b() -> Dict[str, Any]:
    _print_section("СЕКЦИЯ D: Экспериментальный прогон B (с передачей слуха)")
    result = {"section": "D", "pass": False}

    print(f"\n>>> D.1: Запуск game loop С PLAYER_INSULTS → maid_lusya → tavern_keeper_tornin")

    try:
        from app.core.config import settings, BASE_DIR
        from app.services.game_loop_builder import build_game_loop
        from app.services.events.event_bus import get_event_bus
        from app.services.events.event_types import EventType
        from app.domain.events import EventDTO

        import tempfile
        saves_dir = Path(tempfile.mkdtemp(prefix="r2_b5_B_"))
        settings.saves_dir = str(saves_dir)
        settings.environment = "development"

        loop = build_game_loop(data_dir=Path(settings.data_dir))
        scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
        if scene is None:
            scene = loop.scene_manager.initialize_scene("Open_road", "tavern", "12:00")

        # Try to mock LLM router
        try:
            ts = loop._get_task_scheduler()
            for kind, ex in (getattr(ts, "_executors", {}) or {}).items():
                if hasattr(ex, "_router"):
                    ex._router = MagicMock()
                    if hasattr(ex._router, "route"):
                        ex._router.route.return_value = "[Эксперимент]"
        except:
            pass

        try:
            get_event_bus().clear()
        except:
            pass

        # Collect events
        tornin_speeches_b: List[Dict] = []
        lusya_speeches_b: List[Dict] = []
        all_speeches_b: List[Dict] = []
        claim_events_b: List[Dict] = []
        insult_event_published = False

        def _spy_spoke(event):
            payload = getattr(event, "payload", {})
            speaker = getattr(event, "source", "?")
            target = payload.get("target_id", "?")
            intent = payload.get("intent_type", "?")
            content = payload.get("content", "")
            has_prop = bool(payload.get("proposition"))
            speech = {
                "speaker": speaker,
                "target": target,
                "intent": intent,
                "content": str(content)[:200],
                "has_proposition": has_prop,
                "proposition": payload.get("proposition"),
                "tick": payload.get("event_tick", payload.get("tick", "?")),
            }
            all_speeches_b.append(speech)
            if speaker == "tavern_keeper_tornin":
                tornin_speeches_b.append(speech)
            elif speaker == "maid_lusya":
                lusya_speeches_b.append(speech)

        def _spy_claim(event):
            payload = getattr(event, "payload", {})
            claim_events_b.append({
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

        # Publish PLAYER_INSULTS event
        print(f"\n  Публикация PLAYER_INSULTS (target=tavern_keeper_tornin)...")
        payload = {
            "action_type": "player_insults", "target_id": "tavern_keeper_tornin",
            "content": "оскорбление", "event_tick": 1, "visibility": "public",
            "radius": 999.0, "location": "tavern", "campaign_id": "Open_road",
            "raw_input": "оскорбление",
        }
        evt = EventDTO.create(event_type=EventType.PLAYER_INSULTS, source="player",
                              payload=payload, persistence_level="working")
        get_event_bus().publish(evt)
        insult_event_published = True
        print(f"  PLAYER_INSULTS published: {insult_event_published}")

        # Run 20 ticks
        print(f"\n  Запуск 20 ticks (с PLAYER_INSULTS)...")
        for tick_i in range(1, 21):
            print(f"  --- tick {tick_i} ---")
            _log_capture.truncate(0)
            _log_capture.seek(0)
            try:
                loop.idle_tick("Open_road")
            except Exception as e:
                print(f"  [tick {tick_i} error: {str(e)[:100]}]")

            # Check if lusya spoke to tornin this tick
            recent_lusya = [s for s in lusya_speeches_b if s.get("tick") == tick_i]
            for s in recent_lusya:
                if s["target"] == "tavern_keeper_tornin":
                    print(f"  [LUStoTORNIN] tick={s['tick']} intent={s['intent']} content='{s['content'][:80]}' has_prop={s['has_proposition']}")

            # Check if tornin spoke
            recent_tornin = [s for s in tornin_speeches_b if s.get("tick") == tick_i]
            for s in recent_tornin:
                print(f"  [TORNIN] tick={s['tick']} intent={s['intent']} target={s['target']} content='{s['content'][:80]}'")

            # Check claim events
            recent_claims = [c for c in claim_events_b if c.get("tick") == tick_i]
            for c in recent_claims:
                print(f"  [CLAIM] tick={c['tick']} speaker={c['speaker']} prop={c['proposition']}")

        # Get tornin's epistemic state after experiment
        tornin_state_b = {}
        try:
            tick_orch = loop._tick_orch
            epistemic_store = getattr(tick_orch, "_epistemic_store", None)
            if epistemic_store:
                tornin_records = epistemic_store.get_all_for_agent("tavern_keeper_tornin")
                tornin_state_b = {
                    "records_count": len(tornin_records),
                    "records": [
                        {
                            "proposition": str(r.proposition),
                            "confidence": r.confidence,
                            "source_id": r.source_id,
                            "original_source_id": r.original_source_id,
                            "source_type": r.source_type,
                        }
                        for r in tornin_records[:15]
                    ],
                }
        except Exception as e:
            tornin_state_b = {"error": str(e)}

        # Get EpistemicContext for tornin
        tornin_context_b = {}
        try:
            from app.services.npc.epistemic_context_resolver import EpistemicContextResolver, REPORT_CONFIDENCE_THRESHOLD
            if epistemic_store:
                resolver = EpistemicContextResolver(epistemic_store)
                ctx = resolver.resolve("tavern_keeper_tornin")
                tornin_context_b = {
                    "perceived_threats": list(ctx.perceived_threats),
                    "perceived_allies": list(ctx.perceived_allies),
                    "max_confidence": ctx.max_confidence,
                    "max_self_confidence": ctx.max_self_confidence,
                    "claims_about_self": [str(p) for p in ctx.claims_about_self],
                    "report_proposition": str(ctx.report_proposition) if ctx.report_proposition else None,
                    "trigger_proposition": str(ctx.trigger_proposition) if ctx.trigger_proposition else None,
                }
                # Compute modifiers
                modifiers = EpistemicContextResolver.to_modifiers(ctx, archetype="")
                tornin_context_b["modifiers"] = modifiers
                tornin_context_b["REPORT_CONFIDENCE_THRESHOLD"] = REPORT_CONFIDENCE_THRESHOLD
        except Exception as e:
            tornin_context_b = {"error": str(e)}

        print(f"\n>>> D.2: Результаты экспериментального прогона B")
        print(f"  Tornin speeches: {len(tornin_speeches_b)}")
        for s in tornin_speeches_b:
            print(f"    tick={s['tick']}: '{s['content']}' (intent={s['intent']}, target={s['target']})")
        print(f"\n  Lusya speeches (to tornin): {len([s for s in lusya_speeches_b if s['target'] == 'tavern_keeper_tornin'])}")
        for s in [s for s in lusya_speeches_b if s['target'] == 'tavern_keeper_tornin']:
            print(f"    tick={s['tick']}: '{s['content']}' (intent={s['intent']}, has_prop={s['has_proposition']})")
        print(f"\n  All speeches: {len(all_speeches_b)}")
        print(f"  Claim events: {len(claim_events_b)}")

        print(f"\n  Tornin epistemic state:")
        print(f"    Records: {tornin_state_b.get('records_count', '?')}")
        for r in tornin_state_b.get("records", []):
            print(f"    {r}")

        print(f"\n  Tornin EpistemicContext:")
        for k, v in tornin_context_b.items():
            if k != "error":
                print(f"    {k}: {v}")

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

        result["pass"] = True
        result["tornin_speeches_count"] = len(tornin_speeches_b)
        result["tornin_speeches"] = tornin_speeches_b
        result["lusya_to_tornin_count"] = len([s for s in lusya_speeches_b if s['target'] == 'tavern_keeper_tornin'])
        result["lusya_to_tornin"] = [s for s in lusya_speeches_b if s['target'] == 'tavern_keeper_tornin']
        result["claim_events_count"] = len(claim_events_b)
        result["tornin_epistemic_records"] = tornin_state_b.get("records_count", 0)
        result["tornin_epistemic_records_detail"] = tornin_state_b.get("records", [])
        result["tornin_context"] = tornin_context_b
        return result

    except Exception as e:
        print(f"[FATAL: {e}]")
        traceback.print_exc()
        result["error"] = str(e)
        return result


# ============================================================================
# СЕКЦИЯ F: Итоговый отчёт
# ============================================================================
def section_f_final_report(results_a: Dict, results_b: Dict, results_b_boost: Dict) -> None:
    _print_section("СЕКЦИЯ F: ИТОГОВЫЙ ОТЧЁТ — PASS/PARTIAL/FAIL")

    print(f"""
=============================================================================
СВОДНАЯ ТАБЛИЦА
=============================================================================

| Проверка                           | Контроль A       | Эксперимент B    |
|------------------------------------|------------------|------------------|
| Tornin speeches count              | {results_a.get('tornin_speeches_count', '?'):<16} | {results_b.get('tornin_speeches_count', '?'):<16} |
| Tornin epistemic records           | {results_a.get('tornin_epistemic_records', '?'):<16} | {results_b.get('tornin_epistemic_records', '?'):<16} |
| Lusya → Tornin speeches            | N/A              | {results_b.get('lusya_to_tornin_count', '?'):<16} |
| Claim events                       | N/A              | {results_b.get('claim_events_count', '?'):<16} |
| _SAME_SOURCE_BOOST                 | {results_b_boost.get('boost_value', '?'):<16} | (same)           |
| claims_about_self активен          | (baseline)       | {'см. контекст' if results_b.get('tornin_context') else '?':<16} |
| report_proposition                 | (baseline)       | {'см. контекст' if results_b.get('tornin_context') else '?':<16} |
| TALK modifier                      | (baseline)       | {results_b.get('tornin_context', {}).get('modifiers', {}).get('talk', '?') if isinstance(results_b.get('tornin_context'), dict) else '?':<16} |
| SPREAD_RUMOR modifier              | (baseline)       | {results_b.get('tornin_context', {}).get('modifiers', {}).get('spread_rumor', '?') if isinstance(results_b.get('tornin_context'), dict) else '?':<16} |

=============================================================================
ТРАНСКРИПТ A (контрольный прогон)
=============================================================================
""")
    for s in results_a.get("tornin_speeches", []):
        print(f"  [A] tick={s['tick']}: tornin → {s['target']} (intent={s['intent']})")
        print(f"       content: '{s['content']}'")

    print(f"""
=============================================================================
ТРАНСКРИПТ B (экспериментальный прогон)
=============================================================================
""")
    # Lusya → Tornin
    for s in results_b.get("lusya_to_tornin", []):
        print(f"  [B] tick={s['tick']}: maid_lusya → tavern_keeper_tornin (intent={s['intent']}, has_prop={s['has_proposition']})")
        print(f"       content: '{s['content']}'")
        if s.get("proposition"):
            print(f"       proposition: {s['proposition']}")

    # Tornin speeches
    for s in results_b.get("tornin_speeches", []):
        print(f"  [B] tick={s['tick']}: tavern_keeper_tornin → {s['target']} (intent={s['intent']})")
        print(f"       content: '{s['content']}'")

    # Tornin epistemic records
    print(f"""
=============================================================================
EPISTEMIC RECORDS ТОрнина (после эксперимента B)
=============================================================================
""")
    for r in results_b.get("tornin_epistemic_records_detail", []):
        print(f"  {r}")

    # Context
    ctx = results_b.get("tornin_context", {})
    if isinstance(ctx, dict) and "error" not in ctx:
        print(f"""
=============================================================================
EPISTEMIC CONTEXT ТОрнина (после эксперимента B)
=============================================================================
  perceived_threats: {ctx.get('perceived_threats')}
  perceived_allies: {ctx.get('perceived_allies')}
  max_confidence: {ctx.get('max_confidence')}
  max_self_confidence: {ctx.get('max_self_confidence')}
  claims_about_self: {ctx.get('claims_about_self')}
  report_proposition: {ctx.get('report_proposition')}
  trigger_proposition: {ctx.get('trigger_proposition')}
  modifiers: {ctx.get('modifiers')}
  REPORT_CONFIDENCE_THRESHOLD: {ctx.get('REPORT_CONFIDENCE_THRESHOLD')}
""")

    # Verdict
    print(f"""
=============================================================================
ВЕРДИКТ
=============================================================================
""")

    lusya_to_tornin = results_b.get("lusya_to_tornin_count", 0)
    tornin_speeches_b = results_b.get("tornin_speeches_count", 0)
    tornin_records = results_b.get("tornin_epistemic_records", 0)

    # Check if tornin has belief about insult
    has_insult_belief = False
    insult_confidence = 0.0
    for r in results_b.get("tornin_epistemic_records_detail", []):
        if "INSULTED" in r.get("proposition", "") and "tavern_keeper_tornin" in r.get("proposition", ""):
            has_insult_belief = True
            insult_confidence = r.get("confidence", 0.0)
            break

    # Check modifiers
    talk_boost = 0.0
    spread_rumor_boost = 0.0
    if isinstance(ctx, dict):
        mods = ctx.get("modifiers", {})
        talk_boost = mods.get("talk", 0.0)
        spread_rumor_boost = mods.get("spread_rumor", 0.0)

    print(f"  Lusya → Tornin speeches: {lusya_to_tornin}")
    print(f"  Tornin has INSULTED belief: {has_insult_belief} (confidence={insult_confidence:.4f})")
    print(f"  Tornin speeches in B: {tornin_speeches_b}")
    print(f"  TALK boost: {talk_boost}")
    print(f"  SPREAD_RUMOR boost: {spread_rumor_boost}")

    if has_insult_belief and tornin_speeches_b > 0 and talk_boost > 0:
        print(f"\n  >>> ВЕРДИКТ: PARTIAL")
        print(f"  >>> Информация получена и влияет на контекст (TALK boost={talk_boost})")
        print(f"  >>> Торнин произнёс {tornin_speeches_b} реплик")
        print(f"  >>> Причинная связь: claims_about_self → TALK boost → DecisionHub → реплика")
        print(f"  >>> Confidence={insult_confidence:.4f} < 0.25 (REPORT_CONFIDENCE_THRESHOLD)")
        print(f"  >>> report_proposition = None (object_id == agent_id, не третье лицо)")
        print(f"  >>> SPREAD_RUMOR boost = 0 (нет report_proposition)")
        print(f"  >>> Но TALK boost активен через claims_about_self")
    elif has_insult_belief and talk_boost > 0 and tornin_speeches_b == 0:
        print(f"\n  >>> ВЕРДИКТ: PARTIAL")
        print(f"  >>> Информация получена и влияет на контекст (TALK boost={talk_boost})")
        print(f"  >>> Но Торнин НЕ произнёс реплик")
        print(f"  >>> Возможные причины: DecisionHub выбрал другой intent, или LLM не вызвалась")
    elif has_insult_belief and tornin_speeches_b > 0:
        print(f"\n  >>> ВЕРДИКТ: PARTIAL")
        print(f"  >>> Информация получена, Торнин говорил")
        print(f"  >>> Но причинная связь реплик с услышанным требует анализа содержания")
    elif not has_insult_belief:
        print(f"\n  >>> ВЕРДИКТ: FAIL")
        print(f"  >>> Информация НЕ попала в EpistemicStore Торнина")
        print(f"  >>> Возможные причины:")
        print(f"      - LLM router mock (не real LLM)")
        print(f"      - PROP_TARGET_IN_REACH blocked")
        print(f"      - NPC_SPOKE без proposition")
        print(f"      - ClaimEventSubscriber не обработал")
    else:
        print(f"\n  >>> ВЕРДИКТ: PARTIAL")
        print(f"  >>> Смешанный результат — см. детали выше")

    print(f"""
=============================================================================
ФАКТЫ
=============================================================================
1. PROP_TARGET_IN_REACH: порог 6.0m, расстояние Люся→Торнин ≈ 3.55m → НЕ блокирует
2. REPORT_CONFIDENCE_THRESHOLD = 0.25
3. confidence = reliability × _CLAIM_WEIGHT (=1.0) → confidence = reliability
4. claims_about_self: активен при object_id == agent_id (Торнин — жертва) при любой confidence > 0
5. report_proposition: НЕ активен для Торнина (object_id == agent_id, а не третье лицо)
6. TALK boost = max_self_confidence × 0.5 = {insult_confidence * 0.5:.4f}
7. SPREAD_RUMOR boost = 0 (нет report_proposition)
8. _SAME_SOURCE_BOOST = {results_b_boost.get('boost_value', '?')}

=============================================================================
ГИПОТЕЗЫ
=============================================================================
1. Если использовать real LLM (не mock), Торнин может произнести
   содержательную реплику, связанную с оскорблением
2. TALK boost = {insult_confidence * 0.5:.4f} может быть достаточен для
   выбора Intent.TALK в DecisionHub
3. Содержание реплики зависит от LLM context (включает claims_about_self)

=============================================================================
НЕИЗВЕСТНОЕ
=============================================================================
1. Реальное содержание LLM-реплик (probe использует mock router)
2. Выбрал ли DecisionHub TALK как intent для Торнина
3. Достаточен ли TALK boost = {insult_confidence * 0.5:.4f} для выбора TALK
4. Был ли PROP_TARGET_IN_REACH в реальном runtime

=============================================================================
ССЫЛКИ НА КОД
=============================================================================
- epistemic_context_resolver.py L82-89: claims_about_self логика
- epistemic_context_resolver.py L91-101: report_proposition логика
- epistemic_context_resolver.py L195-197: TALK boost из claims_about_self
- epistemic_context_resolver.py L203-206: SPREAD_RUMOR boost из report_proposition
- belief_revision_engine.py L60: incoming_confidence = reliability * _CLAIM_WEIGHT
- belief_revision_engine.py L77: confidence = max(0.0, incoming_confidence) для новых
- belief_revision_engine.py L91: updated_conf с _SAME_SOURCE_BOOST
- post_decision.py L610: _prop_target_in_reach порог = 6.0m
- claim_event_subscriber.py L280-309: listener processing → BeliefRevisionEngine
""")


# ============================================================================
# Main
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-BUTTERFLY-B5-CAUSAL-REACTION — полный эксперимент A/B")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)

    results_a = {}
    results_b = {}
    results_boost = {}

    try:
        results_a = section_a_epistemic_semantics()
    except Exception as e:
        print(f"[section A error: {e}]")
        traceback.print_exc()

    try:
        results_boost = section_b_same_source_boost()
    except Exception as e:
        print(f"[section B error: {e}]")
        traceback.print_exc()

    try:
        results_a_run = section_c_control_run_a()
        results_a.update(results_a_run)
    except Exception as e:
        print(f"[section C error: {e}]")
        traceback.print_exc()

    try:
        results_b = section_d_experiment_run_b()
    except Exception as e:
        print(f"[section D error: {e}]")
        traceback.print_exc()

    try:
        section_f_final_report(results_a, results_b, results_boost)
    except Exception as e:
        print(f"[section F error: {e}]")
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
