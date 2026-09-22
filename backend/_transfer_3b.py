import subprocess
from pathlib import Path

gl_path = Path("app/services/game_loop/game_loop.py")
lc_path = Path("app/services/game_loop/campaign_lifecycle.py")
gl = gl_path.read_text(encoding="utf-8")
lc = lc_path.read_text(encoding="utf-8")

def extract(text):
    lines = text.splitlines(keepends=True)
    start = next(i for i, l in enumerate(lines) if "def new_game(" in l)
    end = next(i for i in range(start, start + 300) if 'return {"reset": True' in lines[i]) + 1
    return start, end, "".join(lines[start:end])

def transform(body):
    body = body.replace("    def new_game(", "    def reset_campaign(", 1)
    old_block = "        import logging\n        self._current_campaign_id = campaign_id\n\n        logger = logging.getLogger(__name__)\n\n        removed = []"
    assert old_block in body, "A2 ANCHOR"
    body = body.replace(old_block, "        removed = []", 1)
    body = body.replace("self._rel_store.reset_campaign(", "self.rel_store.reset_campaign(", 1)
    body = body.replace("self._load_diff_from_disk(", "self.load_diff_from_disk(", 1)
    preserved = '        # === 8. \u0421\u0411\u0420\u041e\u0421 preserved_tick (\u0438\u043d\u0430\u0447\u0435 scene_init \u0432\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442 \u0441\u0442\u0430\u0440\u044b\u0439) ===\n        if hasattr(self, "_preserved_tick"):\n            self._preserved_tick = None\n\n'
    assert preserved in body, "A5 ANCHOR"
    body = body.replace(preserved, "", 1)
    return body

has_facade = "_campaign_lifecycle.reset_campaign" in gl
if has_facade:
    # фасад уже в game_loop (частичное исполнение 234-го) — старое тело берём из git
    raw = subprocess.run(
        ["git", "show", "666106a9:backend/app/services/game_loop/game_loop.py"],
        capture_output=True, cwd="..",
    ).stdout.decode("utf-8")
    _, _, body = extract(raw)
else:
    start, end, body = extract(gl)

body = transform(body)
assert "reset_campaign_persistence" in body and "_preserved_tick" not in body and "self.rel_store.reset_campaign" in body, "TRANSFORM VERIFY"

anchor = "return source_diff"
idx = lc.rfind(anchor)
assert idx > 0, "LC ANCHOR"
nl = lc.find("\n", idx)
lc = lc[:nl+1] + "\n" + body + lc[nl+1:]
lc_path.write_text(lc, encoding="utf-8")

if not has_facade:
    facade = (
        '    def new_game(\n'
        '        self,\n'
        '        campaign_id: str,\n'
        '        continuity_mode: "WorldContinuityMode" = None,\n'
        '        source_campaign_id: Optional[str] = None\n'
        '    ) -> dict:\n'
        '        """\u0424\u0430\u0441\u0430\u0434 CampaignLifecycle (DEGOD Phase3B). GameLoop-owned:\n'
        '        _current_campaign_id (wiring-\u043b\u044f\u043c\u0431\u0434\u044b) + _preserved_tick (bridge \u043a scene_init)."""\n'
        '        self._current_campaign_id = campaign_id\n'
        '        result = self._campaign_lifecycle.reset_campaign(\n'
        '            campaign_id, continuity_mode, source_campaign_id\n'
        '        )\n'
        '        if hasattr(self, "_preserved_tick"):\n'
        '            self._preserved_tick = None\n'
        '        return result\n\n'
    )
    start, end, _ = extract(gl)
    gl = gl[: gl.find("    def new_game(")] + facade + "".join(gl.splitlines(keepends=True)[end:])
    gl_path.write_text(gl, encoding="utf-8")

print("TRANSFER OK: has_facade_was =", has_facade)
