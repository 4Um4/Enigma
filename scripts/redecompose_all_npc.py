"""S365: авто-пере-декомпозиция + жёсткий контроль модели LLM."""
from __future__ import annotations

import argparse
import atexit
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import requests


def split_fragments(author_text: str) -> list:
    numbered = re.findall(r"(?m)^(\d+)\.\s", author_text)
    if not numbered:
        return [f for f in author_text.split("\n\n") if f.strip()]
    parts = re.split(r"(?m)^(?=\d+\.\s)", author_text)
    return [p.strip() for p in parts if p.strip()]


def canon_path(npc_id: str) -> Path:
    return Path("config/npc/chronicles") / f"{npc_id}.json"


def list_npc_from_canon() -> list:
    d = Path("config/npc/chronicles")
    if not d.exists():
        return []
    return [{"npc_id": p.stem, "chronicle": "canon"} for p in sorted(d.glob("*.json"))]


def kill_llama_servers() -> None:
    """Убить ВСЕ llama-server процессы перед запуском."""
    try:
        result = subprocess.run(
            ["taskkill", "/IM", "llama-server.exe", "/F"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            print("  убиты процессы llama-server")
        else:
            print("  llama-server процессов не найдено (или нет прав)")
    except Exception as e:
        print(f"  taskkill не сработал: {e}")
    time.sleep(3)


def wait_for_llm_health(port: int = 8181, timeout: int = 60) -> bool:
    """Подождать, пока LLM не ответит на /health."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"http://localhost:{port}/health", timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def start_llm_clean() -> bool:
    """Убить старые серверы, запустить Qwen, дождаться готовности."""
    print("  убиваю старые llama-server процессы...")
    kill_llama_servers()
    
    print("  запускаю новый LLM-сервер через менеджер...")
    try:
        from scripts.llm_server_manager import kill_llama_server, start_llama_server
        ok = start_llama_server()
        if not ok:
            print("  Внимание: менеджер не смог запустить LLM")
            return False
        atexit.register(kill_llama_server)
    except (ModuleNotFoundError, OSError) as e:
        print(f"  LLM недоступна: {e}")
        return False
    
    print("  ожидаю готовности LLM (до 60 сек)...")
    if wait_for_llm_health():
        print("  LLM готова")
        return True
    print("  LLM не ответила за 60 сек")
    return False


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", default="http://127.0.0.1:8000/api")
    p.add_argument("--campaign", default="silver_wolf")
    p.add_argument("--npc", help="только указанный NPC")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--skip-decompose", action="store_true")
    p.add_argument("--no-canonize", action="store_true")
    p.add_argument("--no-llm", action="store_true")
    p.add_argument("--sleep", type=float, default=0.5)
    args = p.parse_args()

    base = args.base_url.rstrip("/")
    camp = args.campaign

    if not args.no_llm and not args.dry_run and not args.skip_decompose:
        print("[0] Запуск LLM (жёсткий контроль модели)...")
        start_llm_clean()

    print(f"[1] GET /chronicle/roster/{camp}")
    roster = None
    try:
        r = requests.get(f"{base}/chronicle/roster/{camp}", timeout=10)
        if r.status_code == 200:
            roster = r.json().get("roster", [])
            print(f"  roster: {len(roster)} NPC (из API)")
        else:
            print(f"  roster HTTP {r.status_code}")
    except requests.exceptions.ConnectionError:
        print(f"  бэкенд {base} недоступен.")
        return 2

    if roster is None:
        print(f"  fallback: чтение config/npc/chronicles/")
        roster = list_npc_from_canon()
        print(f"  найдено canon-файлов: {len(roster)}")

    if args.npc:
        roster = [r for r in roster if r["npc_id"] == args.npc]
        print(f"  фильтр --npc: {args.npc} -> {len(roster)}")

    ok_count = 0
    fail_count = 0
    total_frags = 0
    total_items = 0
    total_questions = 0

    for npc in roster:
        npc_id = npc["npc_id"]
        status = npc.get("chronicle", "?")
        print(f"\n[NPC] {npc_id} (статус: {status})")

        if args.skip_decompose:
            print(f"  --skip-decompose: использую существующий draft")
        else:
            cp = canon_path(npc_id)
            if not cp.exists():
                print(f"  ПРОПУСК: канон не найден {cp}")
                continue
            with cp.open("r", encoding="utf-8-sig") as f:
                canon = json.load(f)
            author_text = canon.get("author_text", "")
            if not author_text.strip():
                print(f"  ПРОПУСК: author_text пуст")
                continue
            print(f"  author_text: {len(author_text)} знаков")

            if args.dry_run:
                frags = split_fragments(author_text)
                print(f"  DRY-RUN: {len(frags)} фрагментов")
                continue

            clean_draft = {
                "chronicle_id": npc_id,
                "npc_ref": npc_id,
                "author_text": author_text,
                "entries": [],
                "white_spots": [],
                "canonical": False,
                "canonical_version": 0,
                "schema_version": 1,
            }
            r = requests.put(
                f"{base}/chronicle/{camp}/{npc_id}/draft",
                json=clean_draft,
                timeout=30,
            )
            if r.status_code != 200:
                print(f"  PUT draft: HTTP {r.status_code} {r.text[:200]}")
                fail_count += 1
                continue
            print(f"  чистый draft сохранён")

            frags = split_fragments(author_text)
            print(f"  фрагментов: {len(frags)}")
            for fi, frag in enumerate(frags):
                label = f"[{fi+1}/{len(frags)}]"
                try:
                    r = requests.post(
                        f"{base}/chronicle/{camp}/{npc_id}/decompose",
                        json={
                            "campaign_id": camp,
                            "npc_id": npc_id,
                            "fragment_ord": fi,
                            "fragment": frag,
                        },
                        timeout=180,
                    )
                    if r.status_code == 200:
                        data = r.json()
                        if data.get("status") == "OK":
                            n_items = len(data.get("items", []))
                            n_anchors = len(data.get("age_anchors", []) or [])
                            print(f"    {label} OK - {n_items} items, anchors={n_anchors}")
                            total_frags += 1
                            total_items += n_items
                        else:
                            err = data.get("error", "")[:80]
                            print(f"    {label} NOT_DECOMPOSED: {err}")
                    else:
                        print(f"    {label} HTTP {r.status_code}: {r.text[:80]}")
                except Exception as e:
                    print(f"    {label} EXC: {e}")
                time.sleep(args.sleep)

        r = requests.get(f"{base}/chronicle/{camp}/{npc_id}/draft", timeout=30)
        if r.status_code != 200:
            print(f"  GET draft: HTTP {r.status_code}")
            continue
        doc = r.json().get("document", {})
        entries = doc.get("entries", [])
        open_qs = []
        for e in entries:
            for q in e.get("open_questions", []):
                open_qs.append((e.get("entry_id", ""), q))

        if open_qs:
            print(f"  авто-резолв {len(open_qs)} вопросов -> LEAVE_WHITE_SPOT")
            for entry_id, q in open_qs:
                qid = q.get("question_id", "")
                if not qid:
                    continue
                r = requests.post(
                    f"{base}/chronicle/{camp}/{npc_id}/resolve",
                    json={
                        "campaign_id": camp,
                        "npc_id": npc_id,
                        "question_id": qid,
                        "selected_option": "LEAVE_WHITE_SPOT",
                        "selected_value": None,
                    },
                    timeout=30,
                )
                if r.status_code == 200:
                    total_questions += 1
                else:
                    print(f"    {qid}: HTTP {r.status_code} {r.text[:60]}")

        if args.no_canonize:
            print(f"  --no-canonize: без канонизации")
            ok_count += 1
            continue

        print(f"  POST confirm-author-entries...")
        r = requests.post(
            f"{base}/chronicle/{camp}/{npc_id}/confirm-author-entries",
            json={"campaign_id": camp},
            timeout=30,
        )
        if r.status_code == 200:
            data = r.json()
            print(f"  confirmed: {data}")
        else:
            print(f"  confirm HTTP {r.status_code}: {r.text[:200]}")
            fail_count += 1
            continue

        print(f"  POST canonize...")
        r = requests.post(
            f"{base}/chronicle/{camp}/{npc_id}/canonize",
            json={"campaign_id": camp},
            timeout=30,
        )
        if r.status_code == 200:
            data = r.json()
            ver = data.get("canonical_version", "?")
            print(f"  КАНОН v{ver}")
            ok_count += 1
        else:
            err = r.text[:300]
            print(f"  canonize HTTP {r.status_code}: {err}")
            fail_count += 1

    print(f"\n{'='*60}")
    print(f"ИТОГ: OK={ok_count}, FAIL={fail_count}")
    print(f"      фрагментов: {total_frags}")
    print(f"      items: {total_items}")
    print(f"      авто-резолвов: {total_questions}")
    if args.dry_run:
        print(f"  (DRY-RUN: изменения не записаны)")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
