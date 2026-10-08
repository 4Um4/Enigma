"""
Файл: frontend/chronicle_editor/editor_core.py
Назначение: MVP-контур редактора (Слой MVP ТЗ §5): список NPC | лента draft | Разбор.
            Стиль/шрифты — прецедент game_menu (самодостаточность); 7 режимов — итерации C/D/E.
Зависимости: pygame, frontend.chronicle_editor.api
"""
from __future__ import annotations

import pygame
from api_client import HttpClient

from chronicle_editor.api import ChronicleApi

CAMPAIGN = "silver_wolf"
_BG = (18, 18, 23)
_TEXT = (220, 220, 220)
_ACCENT = (180, 160, 90)
_PANEL = (28, 28, 36)


class ChronicleEditorApp:
    """Автономное приложение. MVP: 3 области, один режим, decompose-кнопка."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000") -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((1280, 800), pygame.RESIZABLE)
        pygame.display.set_caption("ENIGMA — Редактор хроник")
        self._font = pygame.font.SysFont("consolas", 16)
        self._font_big = pygame.font.SysFont("consolas", 22, bold=True)
        self._api = ChronicleApi(HttpClient(base_url))
        self._npcs = ["maid_lusya", "tavern_keeper_tornin", "guard_borko", "blacksmith_orm", "thief_shadow", "merchant_goran"]
        self._npc_idx = 0
        self._doc: dict | None = None
        self._items: list = []
        self._frag_ord: int = 0
        self._status = "Готов. F1 — разобрать первый фрагмент черновика (MVP:Ord-0)."
        self._running = True
        self._reload()

    def _reload(self) -> None:
        npc = self._npcs[self._npc_idx]
        self._doc = self._api.get_draft(CAMPAIGN, npc)
        self._items = []
        self._status = f"{npc}: {'draft загружен' if self._doc else 'черновика нет'}"

    def run(self) -> None:
        clock = pygame.time.Clock()
        while self._running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._running = False
                elif event.type == pygame.KEYDOWN:
                    self._on_key(event.key)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self._on_click(event.pos)
            self._draw()
            clock.tick(30)
        pygame.quit()

    def _on_key(self, key: int) -> None:
        if key == pygame.K_ESCAPE:
            self._running = False
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

    def _on_click(self, pos) -> None:
        x, y = pos
        if 20 <= x <= 260 and 100 <= y <= 100 + len(self._npcs) * 26:
            self._npc_idx = (y - 100) // 26
            self._reload()
        elif 300 <= x <= 520 and 100 <= y <= 100 + 24 * 22:
            # Клик по ленте = выбор фрагмента-порядка для разбора (Шаг C)
            self._frag_ord = (y - 100) // 22
            self._status = f"Выбран фрагмент #{self._frag_ord} (F1 — разобрать)"
        elif 300 <= x <= 520 and 700 <= y <= 730:
            self._decompose_ordinal(self._frag_ord)
        elif 900 <= x <= 1120 and 700 <= y <= 730:
            self._canonize()

    def _decompose_first_fragment(self) -> None:
        self._decompose_ordinal(self._frag_ord)

    def _decompose_ordinal(self, ord_: int) -> None:
        """FR-2.x для произвольного фрагмента (Шаг C: клик по ленте/клавиши)."""
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
        self._draw()
        res = self._api.decompose(CAMPAIGN, npc, ord_, frags[ord_])
        if res.get("status") == "OK":
            self._items = list(res.get("items", []))
            self._status = f"Разбор #{ord_}: {len(self._items)} items"
        else:
            self._status = f"НЕ разобрано: {res.get('error', '')[:80]}"

    def _canonize(self) -> None:
        """FR-10.x (T-CCH-04): канонизация; 422 → русский блок с fix_hint."""
        npc = self._npcs[self._npc_idx]
        res = self._api.canonize(CAMPAIGN, npc)
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

    def _draw(self) -> None:
        self.screen.fill(_BG)
        # Левая панель: список NPC
        pygame.draw.rect(self.screen, _PANEL, (10, 90, 250, len(self._npcs) * 26 + 20))
        self.screen.blit(self._font_big.render("ХРОНИКИ", True, _ACCENT), (20, 55))
        for i, npc in enumerate(self._npcs):
            color = _ACCENT if i == self._npc_idx else _TEXT
            self.screen.blit(self._font.render(npc, True, color), (20, 100 + i * 26))
        # Центр: лента entries
        pygame.draw.rect(self.screen, _PANEL, (270, 90, 620, 560))
        self.screen.blit(self._font_big.render("ЛЕНТА (draft)", True, _ACCENT), (280, 55))
        if self._doc:
            for i, e in enumerate((self._doc.get("entries") or [])[:24]):
                age = e.get("historical_age")
                marker = f"[{age}]" if age is not None else "[?]"
                line = f"{marker} {e.get('kind','')}: {str(e.get('payload', {}).get('summary', ''))[:70]}"
                self.screen.blit(self._font.render(line, True, _TEXT), (280, 100 + i * 22))
        # Правая панель: Разбор
        pygame.draw.rect(self.screen, _PANEL, (900, 90, 370, 560))
        self.screen.blit(self._font_big.render("РАЗБОР ENIGMA", True, _ACCENT), (910, 55))
        for i, item in enumerate(self._items[:22]):
            q = " ?" if item.get("needs_confirmation") else ""
            line = f"{item.get('kind','')}{q} {item.get('confidence', 0):.2f}"
            self.screen.blit(self._font.render(line, True, _TEXT), (910, 100 + i * 22))
        # Статусная строка + кнопки (Шаг C: разбор Ord + канонизация)
        pygame.draw.rect(self.screen, _PANEL, (300, 700, 220, 30))
        self.screen.blit(self._font.render(f"F1: Разобрать #{self._frag_ord}", True, _ACCENT), (310, 706))
        pygame.draw.rect(self.screen, _PANEL, (900, 700, 220, 30))
        self.screen.blit(self._font.render("F9: Принять как канон", True, _ACCENT), (910, 706))
        q = self._next_open_question()
        qline = f"? {q.get('question_id','')}: {q.get('target_span','')[:60]}" if q else ""
        self.screen.blit(self._font.render(qline, True, _ACCENT), (910, 735))
        self.screen.blit(self._font.render(self._status[:120], True, _TEXT), (20, 770))
        pygame.display.flip()


def main() -> None:
    ChronicleEditorApp().run()


if __name__ == "__main__":
    main()
