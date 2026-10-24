# -*- coding: utf-8 -*-
# S367 patcher 1/3 v2: CRLF normalization + diagnostic on SKIP.
import io
import sys

PATH = "backend/app/services/chronicle/biography_decomposer.py"

with io.open(PATH, "r", encoding="utf-8", newline="") as f:
    raw = f.read()

eol = "\r\n" if "\r\n" in raw else "\n"
print("detected eol: %s" % ("CRLF" if eol == "\r\n" else "LF"))
src = raw.replace("\r\n", "\n")  # normalize to LF for matching

def apply_replace(src, old, new, label):
    n = src.count(old)
    if n == 0:
        anchor = old[:30].replace("\n", "\\n")
        idx = src.find(old[:30])
        if idx >= 0:
            line = src[:idx].count("\n") + 1
            print("  %s: SKIP — anchor found at line %d, full block mismatch (eol?)" % (label, line))
        else:
            print("  %s: SKIP — anchor '%s' NOT found" % (label, anchor))
        return src
    if n > 1:
        sys.exit("FATAL %s: %d hits, expected 1" % (label, n))
    src = src.replace(old, new, 1)
    print("  %s: OK (%d -> %d chars)" % (label, len(old), len(new)))
    return src

src = apply_replace(src,
    "from typing import Any, Final, List, Optional",
    "from typing import Any, Dict, Final, List, Optional",
    "#1 imports")

src = apply_replace(src,
    "logger = logging.getLogger(__name__)\n\n# Детерминированный препарсинг",
    "logger = logging.getLogger(__name__)\n\n\ndef _default_roster_provider() -> Dict[str, str]:\n"
    '    """S367: lazy default roster source — npc_loader.get_display_names.\n'
    "    Единственный источник истины; per-call fetch (config правится вне тик-сессии).\n"
    "    Ленивый импорт (цикл-безопасно).\"\"\"\n"
    "    from app.services.npc.npc_loader import get_display_names\n"
    "    return get_display_names()\n"
    "\n\n# Детерминированный препарсинг",
    "#2 _default_roster_provider")

src = apply_replace(src,
    "    def __init__(self, router: Optional[Any] = None) -> None:\n"
    "        # Router инъекцией (тестируемость); ленивая загрузка — как у DM.\n"
    "        self._router = router\n"
    "        self._system_prompt: Optional[str] = None",
    "    def __init__(\n"
    "        self,\n"
    "        router: Optional[Any] = None,\n"
    "        roster_provider: Optional[Any] = None,\n"
    "    ) -> None:\n"
    "        # Router инъекцией (тестируемость); ленивая загрузка — как у DM.\n"
    "        # S367: roster_provider — callable () -> Dict[str, str]; None -> lazy\n"
    "        # get_display_names (единственный источник истины, npc_loader).\n"
    "        self._router = router\n"
    "        self._system_prompt: Optional[str] = None\n"
    "        self._roster_provider = roster_provider",
    "#3 __init__")

src = apply_replace(src,
    '    def build_user_prompt(self, fragment: str, age_anchors: List[int]) -> str:\n'
    '        """Детерминированный user-промпт (переиспользуется тестами).\n'
    '        S365: hint «не найдено» не протекает в prompt — иначе LLM повторяет\n'
    '        его в summary (урок guard_borko: «Возрастных якорей не найдено. В 24\n'
    '        застал…» попало в summary как CoT-утечка)."""\n'
    '        if age_anchors:\n'
    '            hints = f"Возрастные якоря фрагмента: {age_anchors}.\\n\\n"\n'
    '        else:\n'
    '            hints = ""\n'
    '        return f"{hints}ФРАГМЕНТ:\\n{fragment.strip()}"',
    '    def build_user_prompt(\n'
    '        self,\n'
    '        fragment: str,\n'
    '        age_anchors: List[int],\n'
    '        roster: Optional[Dict[str, str]] = None,\n'
    '    ) -> str:\n'
    '        """Детерминированный user-промпт (переиспользуется тестами).\n'
    '        S365: hint «не найдено» не протекает в prompt — иначе LLM повторяет\n'
    '        его в summary (урок guard_borko: «Возрастных якорей не найдено. В 24\n'
    '        застал…» попало в summary как CoT-утечка).\n'
    '        S367: roster (опц.) — снимок известных NPC (id->display_name) из\n'
    '        npc_loader.get_display_names. roster=None -> блок отсутствует\n'
    '        (backward-compat: s365 test_cot_leak_blocked вызывает с 2 аргументами)."""\n'
    '        if age_anchors:\n'
    '            hints = f"Возрастные якоря фрагмента: {age_anchors}.\\n\\n"\n'
    '        else:\n'
    '            hints = ""\n'
    '        if roster:\n'
    '            names = ", ".join(sorted(str(v) for v in roster.values() if isinstance(v, str)))\n'
    '            roster_block = (\n'
    '                "ИЗВЕСТНЫЕ NPC (roster): " + names + ".\\n"\n'
    '                "Если target_hint не сопоставляется ОДНОЗНАЧНО ни с одним именем выше — "\n'
    '                "задай ClarificationQuestion (SELECT_EXISTING_NPC/CREATE_NEW_NPC/"\n'
    '                "UNKNOWN_PERSON/LEAVE_WHITE_SPOT).\\n\\n"\n'
    '            )\n'
    '        else:\n'
    '            roster_block = ""\n'
    '        return f"{hints}{roster_block}ФРАГМЕНТ:\\n{fragment.strip()}"',
    "#4 build_user_prompt")

src = apply_replace(src,
    "        anchors = self.extract_age_anchors(fragment)\n"
    "        user_prompt = self.build_user_prompt(fragment, anchors)\n"
    "        from app.services.llm.router import ModelRouter  # ленивый (цикл-безопасно)",
    "        anchors = self.extract_age_anchors(fragment)\n"
    "        roster = (self._roster_provider or _default_roster_provider)()\n"
    "        user_prompt = self.build_user_prompt(fragment, anchors, roster)\n"
    "        from app.services.llm.router import ModelRouter  # ленивый (цикл-безопасно)",
    "#5 decompose fetch+pass")

src = apply_replace(src,
    "                items = ChronicleDecompositionNormalizer.normalize(\n"
    "                    raw, chronicle_id=chronicle_id, fragment_ord=fragment_ord\n"
    "                )",
    "                items = ChronicleDecompositionNormalizer.normalize(\n"
    "                    raw, chronicle_id=chronicle_id, fragment_ord=fragment_ord, roster=roster\n"
    "                )",
    "#6 normalize call")

out = src.replace("\n", eol)
with io.open(PATH, "w", encoding="utf-8", newline="") as f:
    f.write(out)
print("decomposer: DONE (eol preserved: %s)" % ("CRLF" if eol == "\r\n" else "LF"))
