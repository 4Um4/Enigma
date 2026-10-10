"""path: /frontend/chronicle_editor/chronicle_app.py
Назначение: ЕДИНОЕ ядро редактора хроник (вердикт владельца «один редактор —
            два входа»): 3 панели + мышь + клавиши + строка подсказок.
            Входы: (1) F7 в Map Editor — тонкая обёртка editor_screen.py;
            (2) Shift+F7 из меню (Шаг 4); (3) автономный запуск
            ChronicleEditorApp. Встраиваемое ядро берёт surface и API извне;
            выход — флаг exit_requested (каждый вход решает сам, куда выйти).
Зависимости: pygame, api_client.HttpClient, chronicle_editor.api.ChronicleApi
Основные сущности: ChronicleEditorCore (embeddable), ChronicleEditorApp"""

from __future__ import annotations

from pathlib import Path

import pygame
from api_client import HttpClient

from chronicle_editor.api import ChronicleApi

_BG = (18, 18, 23)
_TEXT = (220, 220, 220)
_ACCENT = (180, 160, 90)
_PANEL = (28, 28, 36)
_HINT1 = "Enter: читать целиком · мышь/↑↓: персонаж · клик: выбрать · TAB: лента⇄история · F1/F2: понять · C: вопрос · 1-4: ответ"
_HINT2 = "F9: утвердить как правду · F4: чистый черновик · Ctrl+O: загрузить историю · Ctrl+S: сводка убеждений · ESC: выход"


_OPTION_BY_KEY = {
    pygame.K_1: "SELECT_EXISTING_NPC",
    pygame.K_2: "CREATE_NEW_NPC",
    pygame.K_3: "UNKNOWN_PERSON",
    pygame.K_4: "LEAVE_WHITE_SPOT",
}

# Отображение типов записей по-русски (машино-контракт не меняется —
# только отрисовка; «не понять ленту» — вердикт владельца).
_KIND_RU = {
    "EVENT": "Событие",
    "RELATIONSHIP": "Отношение",
    "EFFECT": "Последствие",
    "BELIEF_SEED": "Убеждение",
    "TRAIT_SEED": "Черта",
    "KNOWLEDGE_LINK": "Знание",
    "OBSERVATION": "Наблюдение",
    "LOCATION": "Место",
    "PORTRET": "Портрет",
    "DESIRE_SEED": "Мечта",
}


class ChronicleEditorCore:
    """Embeddable ядро редактора. Экран (surface) и API приходят извне:
    один и тот же код живёт в F7-режиме карт и в автономном окне.
    Выход — флаг exit_requested; владелец цикла решает, куда выйти."""

    def __init__(self, api: ChronicleApi, campaign: str) -> None:
        self._api = api
        self._campaign = campaign
        self._font = pygame.font.SysFont("consolas", 16)
        self._font_big = pygame.font.SysFont("consolas", 22, bold=True)
        self._roster: list = []
        self._npcs: list[str] = []
        self._npc_idx = 0
        self._doc: dict | None = None
        self._items: list = []
        self._frag_ord = 0
        self._current_q: dict | None = None
        self._status = "Готов."
        self.exit_requested = False
        self._view_history = False  # TAB: ЛЕНТА (разборы) ⇄ ИСТОРИЯ (пункты автора)
        self._detail: tuple | None = None  # Enter: чтение выбранного ЦЕЛИКОМ
        self._load_roster()

    # ── Данные ────────────────────────────────────────────────────────────

    def _load_roster(self) -> None:
        # C0.5: список NPC — ТОЛЬКО с сервера (второй источник истины устранён).
        self._roster = self._api.list_roster(self._campaign)
        self._npcs = [r["npc_id"] for r in self._roster]
        self._npc_idx = 0
        if not self._npcs:
            self._doc = None
            self._items = []
            self._status = "Ростер пуст: сервер недоступен или персонажи не найдены"
            return
        self._reload()

    def _reload(self) -> None:
        if not self._npcs:
            return
        npc = self._npcs[self._npc_idx]
        self._doc = self._api.get_draft(self._campaign, npc)
        self._items = []
        self._status = f"{npc}: {'draft загружен' if self._doc else 'черновика нет'}"

    # ── Ввод (клавиатура + мышь; UX-вердикт: редактор обязан понимать мышь) ─

    def handle_event(self, event: pygame.event.Event) -> None:
        if self._detail is not None:
            if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                self._detail = None
            return
        if event.type == pygame.KEYDOWN:
            self._on_key(event.key)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._on_click(event.pos)

    def _on_key(self, key: int) -> None:
        if key == pygame.K_ESCAPE:
            self.exit_requested = True
        elif key == pygame.K_DOWN:
            self._npc_idx = (self._npc_idx + 1) % len(self._npcs)
            self._reload()
        elif key == pygame.K_UP:
            self._npc_idx = (self._npc_idx - 1) % len(self._npcs)
            self._reload()
        elif key == pygame.K_F1:
            self._decompose_ordinal(self._frag_ord if not self._view_history else self._frag_index_by_number(self._frag_ord + 1) - 1 if False else self._frag_ord)
        elif key == pygame.K_F2:
            self._decompose_ordinal(self._frag_ord + 1)
        elif key == pygame.K_F9:
            self._canonize()
        elif key == pygame.K_s and pygame.key.get_pressed()[pygame.K_LCTRL]:
            self._export_beliefs()
        elif key == pygame.K_o and pygame.key.get_pressed()[pygame.K_LCTRL]:
            self._import_history()
        elif key == pygame.K_F4:
            self._new_clean_draft()
        elif key == pygame.K_TAB:
            self._view_history = not self._view_history
            self._status = "ИСТОРИЯ (твой текст)" if self._view_history else "ЛЕНТА (разборы)"
        elif key == pygame.K_RETURN:
            self._open_detail()
        elif key == pygame.K_c:
            self._current_q = self._next_open_question()
            self._status = (
                f"Вопрос в карточке: {self._current_q.get('question_id')}"
                if self._current_q
                else "Открытых вопросов нет"
            )
        elif key in _OPTION_BY_KEY:
            if self._current_q is None:
                self._status = "Сначала C — взять открытый вопрос"
                return
            self._resolve_current_question(_OPTION_BY_KEY[key])

    def _on_click(self, pos) -> None:
        x, y = pos
        if 20 <= x <= 260 and 100 <= y <= 100 + len(self._npcs) * 26:
            self._npc_idx = (y - 100) // 26
            self._reload()
        elif 300 <= x <= 520 and 100 <= y <= 100 + 24 * 22:
            self._frag_ord = (y - 100) // 22
            if self._view_history:
                frs = self._history_fragments()
                num = frs[self._frag_ord][0] if self._frag_ord < len(frs) else None
                self._status = f"Пункт {num if num is not None else self._frag_ord + 1} выбран (Enter — читать, F1 — понять)"
            else:
                self._status = f"Выбран фрагмент #{self._frag_ord} (F1 — понять)"
        elif 300 <= x <= 520 and 700 <= y <= 730:
            self._decompose_ordinal(self._frag_ord)
        elif 900 <= x <= 1120 and 700 <= y <= 730:
            self._canonize()

    # ── Действия ──────────────────────────────────────────────────────────

    def _export_beliefs(self) -> None:
        """C2: Ctrl+S → «Сохранить как…» (tkinter: имя+папка+формат md/json
        на выбор автора) → содержимое от сервера → запись. Решений о
        содержимом фронт не принимает (Закон 1.1/16.1 — только транспорт)."""
        from tkinter import filedialog

        fmt = "json" if self._ask_format() else "md"
        data = self._api.export_beliefs(self._campaign, fmt)
        if not data or data.get("status") != "OK":
            self._status = "Экспорт недоступен (сервер?)"
            return
        path = filedialog.asksaveasfilename(
            title="Сохранить сводку убеждений",
            defaultextension=f".{fmt}",
            filetypes=[(fmt.upper(), f"*.{fmt}"), ("Все файлы", "*.*")],
            initialfile=f"belief_summary_{self._campaign}.{fmt}",
        )
        if not path:
            self._status = "Экспорт отменён"
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(data.get("text", ""))
        self._status = f"Сводка сохранена: {path} ({data.get('count', 0)} записей)"

    def _import_history(self) -> None:
        """Ctrl+O «Загрузить историю…» (вердикт Мастера): файл .md/.txt →
        авторский текст ДОПИСЫВАЕТСЯ к author_text черновика текущего NPC
        (append-only по абзацам, FR-1.5: декомпозиция обратима, слово автора
        не теряется) → draft PUT через существующий канал. Файл читает фронт,
        сервер контракта файла не знает (Закон 1.1)."""
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            title="Загрузить историю персонажа",
            filetypes=[("История (.md/.txt)", "*.md *.txt"), ("Все файлы", "*.*")],
        )
        if not path:
            self._status = "Загрузка отменена"
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read().strip()
        except (OSError, UnicodeDecodeError) as e:
            self._status = f"Файл не читается: {e}"
            return
        if not text:
            self._status = "Файл пуст"
            return
        doc = dict(self._doc or {"npc_ref": self._npcs[self._npc_idx], "entries": [], "canonical": False})
        old = str(doc.get("author_text", "") or "")
        if old and text[:200] in old:
            # Урок склейки: тот же файл грузится повторно → дубликаты пунктов.
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            replace = messagebox.askyesno(
                "Текст уже содержит эти пункты",
                "Заменить текст целиком на загружаемый?\n"
                "(«Нет» = дописать — может создать дубли)",
                parent=root,
            )
            root.destroy()
            if replace:
                doc["author_text"] = text
                old = ""
            else:
                self._status = "Дописано (осторожно: возможны дубли пунктов)"
                doc["author_text"] = old + "\n\n" + text
        else:
            doc["author_text"] = (old + ("\n\n" if old else "") + text) if old else text
        doc.setdefault("chronicle_id", doc["npc_ref"])
        doc.setdefault("schema_version", 1)
        if self._api.save_draft(self._campaign, self._npcs[self._npc_idx], doc):
            self._status = f"История загружена из {Path(path).name} ({len(text)} знаков) — F1 по пунктам"
            self._reload()
        else:
            self._status = "PUT черновика не прошёл (сервер?)"

    def _new_clean_draft(self) -> None:
        """F4: чистый черновик (урок Люси: старые прогоны смешались с новым
        текстом). Бэкап author_text в <npc>.bak.txt рядом — слово автора
        не теряется (FR-1.5); подтверждение — обязательное."""
        from tkinter import messagebox

        npc = self._npcs[self._npc_idx]
        import tkinter as tk

        tk_root = tk.Tk()
        tk_root.withdraw()
        ok = messagebox.askyesno(
            "Чистый черновик",
            f"Обнулить черновик {npc}? (текст сохранится в бэкап-файл)",
            parent=tk_root,
        )
        tk_root.destroy()
        if not ok:
            return
        old_text = str((self._doc or {}).get("author_text", "") or "")
        if old_text:
            from pathlib import Path as _P

            _bak = _P("saves") / self._campaign / "chronicle_drafts" / f"{npc}.bak.txt"
            _bak.parent.mkdir(parents=True, exist_ok=True)
            _bak.write_text(old_text, encoding="utf-8")
        doc = {
            "chronicle_id": npc,
            "npc_ref": npc,
            "author_text": "",
            "entries": [],
            "canonical": False,
            "schema_version": 1,
        }
        if self._api.save_draft(self._campaign, npc, doc):
            self._status = f"Чистый черновик (бэкап: {npc}.bak.txt) — Ctrl+O: загрузить историю"
            self._reload()
        else:
            self._status = "PUT не прошёл (сервер?)"

    def _ask_format(self) -> bool:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        answer = messagebox.askyesno(
            "Формат файла", "Сохранить в JSON? («Нет» = Markdown)", parent=root
        )
        root.destroy()
        return answer

    @staticmethod
    def _split_fragments(author_text: str) -> list:
        """Фрагменты = нумерованные пункты «1.» … «N.» (формат Мастера,
        Люся.md). Нет ни одного номера → fallback на пустые строки (старый
        формат черновиков). Пункт без номера в нумерованном тексте —
        сохранён как хвост предыдущего (абзац того же пункта)."""
        import re

        numbered = re.findall(r"(?m)^(\d+)\.\s", author_text)
        if not numbered:
            return [f for f in author_text.split("\n\n") if f.strip()]
        parts = re.split(r"(?m)^(?=\d+\.\s)", author_text)
        return [p.strip() for p in parts if p.strip()]

    def _decompose_ordinal(self, ord_: int) -> None:
        """FR-2.x для произвольного фрагмента (клик по ленте / F1/F2)."""
        npc = self._npcs[self._npc_idx]
        frags = self._split_fragments((self._doc or {}).get("author_text", ""))
        if not frags:
            self._status = "author_text пуст — черновик без текста"
            return
        if ord_ >= len(frags):
            self._status = f"Фрагмента #{ord_} нет (всего {len(frags)})"
            return
        self._frag_ord = ord_
        _frs = self._history_fragments()
        _label = f"пункт {_frs[ord_][0]}" if self._view_history and ord_ < len(_frs) and _frs[ord_][0] is not None else f"фрагмент №{ord_}"
        self._status = f"Разбор {_label}... (LLM, до 60 с)"
        self.draw(pygame.display.get_surface())
        pygame.display.flip()
        res = self._api.decompose(self._campaign, npc, ord_, frags[ord_])
        if res.get("status") == "OK":
            self._items = list(res.get("items", []))
            self._status = f"{_label}: понял {len(self._items)} записей"
        else:
            self._status = f"НЕ разобрано: {res.get('error', '')[:80]}"

    def _resolve_current_question(self, option: str) -> None:
        """FR-3.1: карточка 4-опций. LEAVE_WHITE_SPOT — всегда доступен (П3);
        SELECT_EXISTING_NPC берёт значение из списка NPC (слева), CREATE_NEW_NPC
        и UNKNOWN_PERSON — имя-хинт из вопроса; полный ввод — позже (Шаг E)."""
        q = self._current_q
        if q is None:
            self._status = "Нет открытого вопроса"
            return
        value = None
        if option == "SELECT_EXISTING_NPC":
            value = self._npcs[self._npc_idx]
        elif option == "CREATE_NEW_NPC":
            value = f"npc_{q.get('question_id', 'new')}"
        elif option == "UNKNOWN_PERSON":
            value = q.get("target_span", "") or "unknown_person"
        ok = self._api.resolve_question(
            self._campaign, self._npcs[self._npc_idx], q.get("question_id", ""), option, value
        )
        self._status = (
            f"Резолюция [{option}{': ' + value if value else ''}] — {'OK' if ok else 'ОШИБКА PUT'}"
        )
        self._current_q = None
        self._reload()

    def _canonize(self) -> None:
        """FR-10.x (T-CCH-04): канонизация; 422 → русский блок с fix_hint."""
        npc = self._npcs[self._npc_idx]
        res = self._api.canonize(self._campaign, npc)
        if res.get("status") == "OK":
            self._status = f"КАНОНИЗИРОВАНО (v{res.get('canonical_version')})"
        else:
            self._status = f"БЛОК (Save=Contract): {res.get('detail', '')[:110]}"

    def _next_open_question(self):
        """Навигатор вопросов: первый открытый вопрос draft-документа."""
        for e in (self._doc or {}).get("entries") or []:
            for q in e.get("open_questions") or []:
                return q
        return None

    # ── Человекочитаемые подписи (пустые строки ленты — дефект: у каждого
    #    типа записи своё поле текста, лента читала только summary) ────────

    @staticmethod
    def _kind_ru(kind: str) -> str:
        return _KIND_RU.get(kind, kind)

    @staticmethod
    def _entry_text(e: dict) -> str:
        p = e.get("payload", {}) or {}
        k = e.get("kind", "")
        if k in ("BELIEF_SEED", "DESIRE_SEED", "PORTRET"):
            return str(p.get("statement", ""))
        if k == "TRAIT_SEED":
            return f"{p.get('trait', '')}: {p.get('evidence', '')}"
        if k == "KNOWLEDGE_LINK":
            return f"узнал(а) в {p.get('learned_age', '?')} лет — {p.get('about_hint', '')}"
        return str(p.get("summary", ""))

    def _history_fragments(self) -> list:
        """Пункты истории с АВТОРСКОЙ нумерацией: [(номер, текст)]. Возвращает
        [(None, абзац)] для текста без номеров. Урок Люси: «фрагмент №11» —
        говно-нумерация; автор мыслит СВОИМИ номерами."""
        import re

        text = str((self._doc or {}).get("author_text", "") or "")
        marks = re.findall(r"(?m)^(\d+)\.\s", text)
        if not marks:
            return [(None, p.strip()) for p in text.split("\n\n") if p.strip()]
        parts = re.split(r"(?m)^(?=\d+\.\s)", text)
        out = []
        for p in parts:
            p = p.strip()
            if not p:
                continue
            m = re.match(r"^(\d+)\.\s*", p)
            if m:
                # «1. 1.» лечится здесь: номер — метка строки, из текста
                # фрагмента вырезается (урок скринов Мастера)
                out.append((int(m.group(1)), p[m.end():].strip()))
            else:
                out.append((None, p))
        return out

    def _frag_index_by_number(self, num: int) -> int:
        """Индекс фрагмента (для _decompose_ordinal) по авторскому номеру."""
        for i, (n, _t) in enumerate(self._history_fragments()):
            if n == num:
                return i
        return num

    @staticmethod
    def _wrap(text: str, width: int) -> list:
        import textwrap

        return textwrap.wrap(str(text), width=width) or [""]

    def _open_detail(self) -> None:
        """Enter: читать выбранное ЦЕЛИКОМ (вердикт «всё обрезано — как
        выбирать?»). История — пункт; лента — запись. Любая клавиша — назад."""
        if self._view_history:
            frs = self._history_fragments()
            if self._frag_ord < len(frs):
                num, txt = frs[self._frag_ord]
                self._detail = (f"Пункт {num}" if num is not None else "Фрагмент", txt)
        elif self._doc:
            entries = self._doc.get("entries") or []
            if self._frag_ord < len(entries):
                e = entries[self._frag_ord]
                age = e.get("historical_age")
                self._detail = (
                    f"{self._kind_ru(e.get('kind',''))} [{age if age is not None else '?'}]",
                    self._entry_text(e),
                )

    # ── Отрисовка ─────────────────────────────────────────────────────────

    def draw(self, surface) -> None:
        """Рисует в ЧУЖОЙ surface (F7 рисует в экран карт; автономный вход —
        в свой). pygame.display.flip() — забота владельца цикла, не ядра."""
        surface.fill(_BG)
        # Левая панель: список NPC (со статусом хроники)
        pygame.draw.rect(surface, _PANEL, (10, 90, 250, len(self._npcs) * 26 + 20))
        surface.blit(self._font_big.render("ХРОНИКИ", True, _ACCENT), (20, 55))
        for i, npc in enumerate(self._npcs):
            color = _ACCENT if i == self._npc_idx else _TEXT
            surface.blit(self._font.render(npc, True, color), (20, 100 + i * 26))
        # Центр: ЛЕНТА (разборы) ⇄ ИСТОРИЯ (пункты автора) — TAB
        pygame.draw.rect(surface, _PANEL, (270, 90, 620, 560))
        mode_title = "ИСТОРИЯ (твой текст — TAB: лента)" if self._view_history else "ЛЕНТА (разборы — TAB: история)"
        surface.blit(self._font_big.render(mode_title, True, _ACCENT), (280, 55))
        if self._view_history:
            for i, (num, txt) in enumerate(self._history_fragments()[:25]):
                label = f"{num}." if num is not None else "·"
                color = _ACCENT if i == self._frag_ord else _TEXT
                surface.blit(self._font.render(f"{label} {txt[:58]}", True, color), (280, 100 + i * 22))
        elif self._doc:
            for i, e in enumerate((self._doc.get("entries") or [])[:25]):
                age = e.get("historical_age")
                marker = f"[{age}]" if age is not None else "[?]"
                line = f"{marker} {self._kind_ru(e.get('kind',''))}: {self._entry_text(e)[:60]}"
                surface.blit(self._font.render(line, True, _TEXT), (280, 100 + i * 22))
        # Правая панель: Разбор
        pygame.draw.rect(surface, _PANEL, (900, 90, 370, 560))
        surface.blit(self._font_big.render("ЧТО ПОНЯЛ ENIGMA", True, _ACCENT), (910, 55))
        _ry = 100
        for item in self._items[:22]:
            q = " ?" if item.get("needs_confirmation") else ""
            dp = item.get("draft_payload", {}) or {}
            txt = str(dp.get("summary") or dp.get("statement") or dp.get("trait") or "")
            color = _ACCENT if q else _TEXT
            surface.blit(
                self._font.render(f"{self._kind_ru(item.get('kind',''))}{q}:", True, color),
                (910, _ry),
            )
            for _ln in self._wrap(txt, 34)[:6]:
                _ry += 20
                if _ry > 640:
                    break
                surface.blit(self._font.render(_ln, True, _TEXT), (910, _ry))
            _ry += 26
            if _ry > 645:
                surface.blit(self._font.render("…", True, (120, 120, 120)), (910, _ry))
                break
        # Кнопки
        pygame.draw.rect(surface, _PANEL, (300, 690, 220, 30))
        surface.blit(self._font.render("F1: Понять выбранное", True, _ACCENT), (310, 696))
        pygame.draw.rect(surface, _PANEL, (900, 690, 220, 30))
        surface.blit(self._font.render("F9: Утвердить как правду", True, _ACCENT), (910, 696))
        # Нижняя зона: статус → вопрос → подсказка (2 строки, без обрезки)
        surface.blit(self._font.render(self._status[:130], True, _TEXT), (20, 726))
        q = self._current_q or self._next_open_question()
        if q:
            qline = (
                f"❓ {q.get('target_span','')[:48]} — кто это?  "
                "1:из списка · 2:новый · 3:массовка · 4:белое пятно (C — взять)"
            )
            surface.blit(self._font.render(qline[:150], True, _ACCENT), (20, 746))
        else:
            surface.blit(
                self._font.render(
                    "Вопросов нет. F9 утверждает историю как правду персонажа.",
                    True,
                    (150, 150, 150),
                ),
                (20, 746),
            )
        surface.blit(self._font.render(_HINT1, True, (110, 110, 110)), (20, 766))
        surface.blit(self._font.render(_HINT2, True, (110, 110, 110)), (20, 782))
        if self._detail is not None:
            title, txt = self._detail
            surface.fill((12, 12, 16))
            surface.blit(self._font_big.render(title, True, _ACCENT), (30, 30))
            _dy = 70
            for _ln in self._wrap(txt, 110):
                surface.blit(self._font.render(_ln, True, _TEXT), (30, _dy))
                _dy += 22
                if _dy > 750:
                    surface.blit(
                        self._font.render("… (дальше — в файле истории)", True, (120, 120, 120)),
                        (30, _dy),
                    )
                    break
            surface.blit(
                self._font.render("любая клавиша / клик — назад", True, (110, 110, 110)),
                (30, 782),
            )


class ChronicleEditorApp:
    """Автономный вход: своё окно + цикл поверх ядра."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000") -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((1280, 800), pygame.RESIZABLE)
        pygame.display.set_caption("ENIGMA — Редактор хроник")
        # Кампания: селектор — Шаг 2; пока дефолт silver_wolf.
        self._core = ChronicleEditorCore(ChronicleApi(HttpClient(base_url)), "silver_wolf")

    def run(self) -> None:
        clock = pygame.time.Clock()
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                else:
                    self._core.handle_event(event)
            if self._core.exit_requested:
                running = False
            self._core.draw(self.screen)
            pygame.display.flip()
            clock.tick(30)
        # pygame.quit() НЕ вызывается (прецедент EditorCore, game_launcher:525):
        # при запуске из меню (Shift+F7) он ронял pygame-контекст всего
        # приложения — «Esc вылетает». Окно закрывает владелец цикла
        # (_init_menu_display пересоздаёт дисплей).


def main() -> None:
    ChronicleEditorApp().run()


if __name__ == "__main__":
    main()
