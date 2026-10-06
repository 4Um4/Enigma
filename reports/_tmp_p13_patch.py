fp = r"backend/app/services/events/rules_subscriber.py"
raw = open(fp, "rb").read()
bom = raw[:3] == b"\xef\xbb\xbf"
text = raw.decode("utf-8-sig")
nl = "\r\n" if "\r\n" in text else "\n"

def sub_once(t, old, new, tag):
    if t.count(old) != 1:
        raise SystemExit("STOP: anchor %s count=%d" % (tag, t.count(old)))
    return t.replace(old, new, 1)

text = sub_once(text, "import hashlib\nimport logging", "import logging", "hashlib-import")
text = sub_once(
    text,
    "from __future__ import annotations\n\nimport logging",
    "from __future__ import annotations\n\nimport logging\n\nfrom app.services.npc.kernel_rng import KernelRNG",
    "krng-import",
)
old_roll = """            # Детерминированный бросок d20 (seed from event id + tick)
            _event_id = getattr(event, \"id\", \"\") or str(event.get(\"id\", \"\"))  # noqa: ENIGMA002
            _tick = snapshot.get(\"tick_number\", 0)
            _seed = (
                int(hashlib.sha256(f\"{_event_id}:{_tick}\".encode()).hexdigest(), 16)
                % 20
                + 1
            )
            roll = _seed"""
new_roll = """            # П-13/вердикт-2 Мастера: дегенеративная соль f(tick) устранена —
            # roll детерминирован и привязан к субъекту/контексту действия
            # (KernelRNG ADR-O-301: tick + actor + salt[action,target]).
            # Характеристики в бросок НЕ входят (будущий боевой resolver —
            # отдельная система по вердикту Мастера, здесь не проектируется).
            _event_id = getattr(event, \"id\", \"\") or str(event.get(\"id\", \"\"))  # noqa: ENIGMA002
            _tick = snapshot.get(\"tick_number\", 0)
            _actor_id = getattr(event, \"source\", \"\") or \"unknown\"
            roll = KernelRNG(
                tick=int(_tick or 0),
                npc_id=_actor_id,
                salt=f\"rules:{event_type}:{target_id}\",
            ).randint(1, 20)"""
text = sub_once(text, old_roll, new_roll, "roll-block")
old_checks = """        return RulesDelta(
            target_id=target_id,
            action_type=\"SANDBOX_SOCIAL\",
            success=True,
            checks=[{\"type\": \"persuasion\", \"dc\": 14, \"roll\": 15, \"success\": True}],
            money_delta=money_delta,
        )"""
new_checks = """        # П-13/вердикт-3 Мастера: фальшивая d20-метадата удалена — социальный
        # успех = результат детерминированного разрешения (semantic gate выше),
        # без подмены броском. Случайность в социальные действия не вводится.
        return RulesDelta(
            target_id=target_id,
            action_type=\"SANDBOX_SOCIAL\",
            success=True,
            money_delta=money_delta,
        )"""
text = sub_once(text, old_checks, new_checks, "social-checks")
open(fp, "w", encoding=("utf-8-sig" if bom else "utf-8"), newline="").write(text)
print("rules_subscriber: 4 замены OK")
