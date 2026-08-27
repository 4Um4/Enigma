# -*- coding: utf-8 -*-
"""REGRESSION :: аудит v0.5.3.9.0, пакет быстрых побед (№1-5, 11, 15, 22).
Запуск: python -X utf8 backend/tests/test_audit_quick_wins.py
"""
import ast
import inspect
import re
import sys
import traceback
from pathlib import Path


def _find_root():
    p = Path(__file__).resolve()
    for cand in [p] + list(p.parents):
        if (cand / "backend" / "app" / "__init__.py").exists():
            return cand
    raise SystemExit("Не найден корень репозитория (backend/app/__init__.py)")


ROOT = _find_root()
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

RD = BACKEND / "app" / "api" / "routes_debug.py"
CT = BACKEND / "app" / "services" / "npc" / "npc_tick_contracts.py"
ORCH = BACKEND / "app" / "services" / "game_loop" / "npc_orchestration.py"
GL = BACKEND / "app" / "services" / "game_loop" / "__init__.py"
APIF = ROOT / "frontend" / "api_client.py"
GSCR = ROOT / "frontend" / "game_screen.py"
LAUN = ROOT / "game_launcher.py"
EH = ROOT / "frontend" / "map_editor" / "core" / "event_handler.py"
EC = ROOT / "frontend" / "map_editor" / "editor_core.py"
MAIN = BACKEND / "app" / "main.py"


def src(p):
    return p.read_text(encoding="utf-8", errors="replace")


# ---------- T1 (№1): битый импорт удалён, request пробрасывается ----------
def test_t1_reset_relationships():
    tree = ast.parse(src(RD))
    mods = [
        n.module
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and n.module
    ]
    assert not any(m.startswith("app.core.game_loop") for m in mods), mods
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == "reset_campaign_relationships"
    )
    names = [a.arg for a in fn.args.args]
    assert "request" in names and "campaign_id" in names, names


# ---------- T2 (№2a): поле контракта существует, getattr шва жив ----------
def test_t2_contract_field():
    from dataclasses import fields
    from app.services.npc.npc_tick_contracts import NpcTickServices
    f = {x.name for x in fields(NpcTickServices)}
    assert "crystallized_belief_store" in f, f
    dummy = object()
    svc = NpcTickServices(dummy, dummy, dummy, dummy, {})
    assert getattr(svc, "crystallized_belief_store", None) is None
    mark = object()
    svc2 = NpcTickServices(dummy, dummy, dummy, dummy, {}, crystallized_belief_store=mark)
    assert svc2.crystallized_belief_store is mark


# ---------- T3 (№2b+№3): проводка в оркестрации и обоих idle-путях ----------
def test_t3_wiring():
    assert "crystallized_belief_store=_cryst_store" in src(ORCH)
    t = src(GL)
    assert len(re.findall(r"npc_services=_npc_svc", t)) == 2, "ожидается ровно 2 точки проброса"
    from app.services.tick_orchestrator import TickOrchestrator
    from app.services.world.time_skip_executor import TimeSkipExecutor
    assert "npc_services" in inspect.signature(TickOrchestrator.execute).parameters
    assert "npc_services" in inspect.signature(TimeSkipExecutor.skip).parameters


# ---------- T4 (№4): мёртвый API continuity исчез полностью ----------
def test_t4_continuity_api_removed():
    assert "set_continuity_mode" not in src(APIF)


# ---------- T5 (№22/#5): порт уважается, отказ экрана больше не молчаливый ----------
def test_t5_gateway_and_refusal():
    fab = src(APIF)
    assert "ENIGMA_BACKEND_URL" in fab and "http://127.0.0.1:8000" in fab
    la = src(LAUN)
    assert len(re.findall(r"create_game_gateway\(base_url=_BACKEND_URL\)", la)) == 2
    assert len(re.findall(r'setdefault\("ENIGMA_BACKEND_URL"', la)) == 2
    gs = src(GSCR)
    assert "Отказ запуска экрана" in gs and "[!]" in gs


# ---------- T6 (№1, функциональный): эндпоинт 200, request реально дошёл ----------
def test_t6_endpoint_functional():
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
    except Exception:
        print("SKIP: fastapi/TestClient недоступен")
        return
    import app.api.routes_debug as rd
    import app.services.game_loop_accessor as acc

    got = {}

    def fake_accessor(request):
        got["request"] = request

        class L:  # memory_manager=None -> ветка честного {'status':'error'}
            memory_manager = None
        return L()

    orig = acc.get_game_loop
    acc.get_game_loop = fake_accessor
    try:
        appf = FastAPI()
        appf.include_router(rd.router)
        paths = [getattr(r, "path", "") for r in appf.routes]
        target = next((p for p in paths if "reset-relationships" in p), None)
        assert target, f"маршрут reset-relationships не смонтирован; есть: {paths}"
        resp = TestClient(appf).post(target.replace("{campaign_id}", "t6"))
    finally:
        acc.get_game_loop = orig
    assert resp.status_code == 200, (resp.status_code, resp.text[:200])
    body = resp.json()
    assert body["status"] == "error" and "GameLoop" in body["message"], body
    assert got["request"] is not None  # request дошёл до аксессора — суть фикса №1


# ---------- T7 (№15): единый масштаб редактора ----------
def _scale_inventory(path):
    """Все присваивания SCALE в файле: (строка, вид, значение). Обход всего дерева."""
    tree = ast.parse(src(path))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "SCALE" for t in node.targets
        ):
            found.append((node.lineno, "Assign", getattr(node.value, "value", "<сложное>")))
        elif isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "SCALE":
            v = getattr(node.value, "value", "<без значения>") if node.value else "<только аннотация>"
            found.append((node.lineno, "AnnAssign", v))
        elif isinstance(node, ast.AugAssign) and getattr(node.target, "id", "") == "SCALE":
            found.append((node.lineno, "AugAssign(!!)", "<read-modify-write>"))
    return found


# ---------- T7 (№15 ОТЗЫВАЕТСЯ): канон масштабов — handler=20, core=40 ----------
# Правка 20->40 из аудита эмпирически ухудшила перетаскивание (объект отстаёт),
# откатена владельцем. Тест теперь охраняет рабочий канон от случайных изменений.
def test_t7_single_scale():
    inv_eh, inv_ec = _scale_inventory(EH), _scale_inventory(EC)
    assert inv_eh and {v for _, _, v in inv_eh} == {20}, f"event_handler.py SCALE: {inv_eh}"
    assert inv_ec and {v for _, _, v in inv_ec} == {40}, f"editor_core.py SCALE: {inv_ec}"
    assert len(inv_eh) == 1, f"лишние присваивания SCALE в event_handler: {inv_eh}"


# ---------- T8 (№11): баннер старта честный ----------
def test_t8_vram_banner_honest():
    m = src(MAIN)
    assert "ЗАГЛУШКА" in m
    assert not re.search(r"✓ ErrorInterpreter \+ VRAMMonitor", m)


_ALL = [v for k, v in sorted(globals().items()) if k.startswith("test_")]


def main():
    npass = nfail = 0
    for fn in _ALL:
        name = fn.__name__
        try:
            fn()
            print(f"[PASS] {name}")
            npass += 1
        except AssertionError as e:
            print(f"[FAIL] {name}: {e}")
            nfail += 1
        except Exception as e:
            print(f"[FAIL] {name}: {type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}")
            nfail += 1
    print(f"ИТОГО: PASS={npass} FAIL={nfail}")
    sys.exit(1 if nfail else 0)


if __name__ == "__main__":
    main()