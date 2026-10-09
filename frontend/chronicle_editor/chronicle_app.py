"""
path: /frontend/chronicle_editor/chronicle_app.py
Назначение: ЕДИНОЕ ядро редактора хроник (вердикт владельца «один редактор —
            два входа»): 3 панели + мышь + клавиши + строка подсказок.
            Входы: (1) F7 в Map Editor — тонкая обёртка editor_screen.py;
            (2) Shift+F7 из меню (Шаг 4); (3) автономный запуск
            ChronicleEditorApp. Встраиваемое ядро берёт surface и API извне;
            выход — флаг exit_requested (каждый вход решает сам, куда выйти).
Зависимости: pygame, api_client.HttpClient, chronicle_editor.api.ChronicleApi
Основные сущности: ChronicleEditorCore (embeddable), ChronicleEditorApp
"""
from __future__ import annotations

import pygame
from api_client import HttpClient

from chronicle_editor.api import ChronicleApi

_BG = (18, 18, 23)
_TEXT = (220, 220, 220)
_ACCENT = (180, 160, 90)
_PANEL = (28, 28, 36)
_HINT = "↑↓/мышь: список · клик ленты: фрагмент · F1/F2: разбор · C: вопрос · 1-4: ответ · F9: канон · Ctrl+S: сводка · ESC: выход"

_OPTION_BY_KEY = {
    pygame.K_1: "SELECT_EXISTING_NPC",
    pygame.K_2: "CREATE_NEW_NPC",
    pygame.K_3: "UNKNOWN_PERSON",
    pygame.K_4: "LEAVE_WHITE_SPOT",
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
            self._decompose_ordinal(self._frag_ord)
        elif key == pygame.K_F2:
            self._decompose_ordinal(self._frag_ord + 1)
        elif key == pygame.K_F9:
            self._canonize()
        elif key == pygame.K_s and pygame.key.get_pressed()[pygame.K_LCTRL]:
            self._export_beliefs()
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
            self._status = f"Выбран фрагмент #{self._frag_ord} (F1 — разобрать)"
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

    def _decompose_ordinal(self, ord_: int) -> None:
        """FR-2.x для произвольного фрагмента (клик по ленте / F1/F2)."""
        npc = self._npcs[self._npc_idx]
        frags = [f for f in (self._doc or {}).get("author_text", "").split("\n\n") if f.strip()]
        if not frags:
            self._status = "author_text пуст — черновик без текста"
            return
        if ord_ >= len(frags):
            self._status = f"Фрагмента #{ord_} нет (всего {len(frags)})"
            return
        self._frag_ord = ord_
        self._status = f"Разбор #{ord_}... (LLM, до 60 с)"
        self.draw(pygame.display.get_surface())
        pygame.display.flip()
        res = self._api.decompose(self._campaign, npc, ord_, frags[ord_])
        if res.get("status") == "OK":
            self._items = list(res.get("items", []))
            self._status = f"Разбор #{ord_}: {len(self._items)} items"
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
        # Центр: лента entries
        pygame.draw.rect(surface, _PANEL, (270, 90, 620, 560))
        surface.blit(self._font_big.render("ЛЕНТА (draft)", True, _ACCENT), (280, 55))
        if self._doc:
            for i, e in enumerate((self._doc.get("entries") or [])[:24]):
                age = e.get("historical_age")
                marker = f"[{age}]" if age is not None else "[?]"
                line = f"{marker} {e.get('kind','')}: {str(e.get('payload', {}).get('summary', ''))[:70]}"
                surface.blit(self._font.render(line, True, _TEXT), (280, 100 + i * 22))
        # Правая панель: Разбор
        pygame.draw.rect(surface, _PANEL, (900, 90, 370, 560))
        surface.blit(self._font_big.render("РАЗБОР ENIGMA", True, _ACCENT), (910, 55))
        for i, item in enumerate(self._items[:22]):
            q = " ?" if item.get("needs_confirmation") else ""
            line = f"{item.get('kind','')}{q} {item.get('confidence', 0):.2f}"
            surface.blit(self._font.render(line, True, _TEXT), (910, 100 + i * 22))
        # Кнопки
        pygame.draw.rect(surface, _PANEL, (300, 700, 220, 30))
        surface.blit(self._font.render(f"F1: Разобрать #{self._frag_ord}", True, _ACCENT), (310, 706))
        pygame.draw.rect(surface, _PANEL, (900, 700, 220, 30))
        surface.blit(self._font.render("F9: Принять как канон", True, _ACCENT), (910, 706))
        q = self._current_q or self._next_open_question()
        if q:
            qline = f"? {q.get('question_id','')}: {q.get('target_span','')[:44]}"
            hint = "1:NPC 2:Новый 3:Массовка 4:Пятно (C — взять)"
            surface.blit(self._font.render(qline, True, _ACCENT), (910, 735))
            surface.blit(self._font.render(hint, True, _TEXT), (910, 752))
        else:
            surface.blit(self._font.render("Открытых вопросов нет", True, _TEXT), (910, 735))
        # Подсказка клавиш (UX-дефект «я не знал про стрелочки» закрыт)
        surface.blit(self._font.render(_HINT[:150], True, (150, 150, 150)), (20, 752))
        surface.blit(self._font.render(self._status[:120], True, _TEXT), (20, 770))


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
        pygame.quit()


def main() -> None:
    ChronicleEditorApp().run()


if __name__ == "__main__":
    main()
