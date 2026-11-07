"""ME-2.1 Step F: CatalogPanel — asset catalog UI for Map Editor.

Toggle with F3. Shows search, category filter, card list, preview.
Selecting a blueprint sets selected_object_type + tool=TOOL_OBJECT.
Uses AssetStore + CatalogIndex + ResourceValidator (Steps A-D).

NOT a second storage — reads from AssetStore via CatalogIndex.
Does NOT mix NPC catalog with object catalog.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pygame
from assets.asset_store import AssetStore
from assets.catalog_index import CatalogIndex
from assets.resource_validator import ResourceValidator, ValidationResult


class CatalogPanel:
    """Asset catalog panel for browsing and selecting blueprints."""

    def __init__(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        assets_dir: Path,
        pixels_dir: Path,
    ) -> None:
        self.rect = pygame.Rect(x, y, w, h)
        self._assets_dir = Path(assets_dir)
        self._pixels_dir = Path(pixels_dir)
        self.active = False

        # Data layers
        self._store: Optional[AssetStore] = None
        self._index: Optional[CatalogIndex] = None
        self._validator: Optional[ResourceValidator] = None

        # UI state
        self._search_query = ""
        self._search_active = False
        self._selected_category: Optional[str] = None
        self._scroll_offset = 0
        self._selected_bp_id: Optional[str] = None
        self._validation: Optional[ValidationResult] = None
        self._filtered_ids: list[str] = []
        self._card_rects: list[tuple[str, pygame.Rect]] = []

        # Layout
        pad = 6
        self._search_rect = pygame.Rect(pad, pad, w - pad * 2 - 20, 22)
        self._close_rect = pygame.Rect(w - 20 - pad, pad, 20, 22)
        cat_y = pad + 22 + pad
        self._cat_rects: list[tuple[str, pygame.Rect]] = []
        self._cat_y = cat_y
        self._list_y = cat_y + 24 + pad
        self._list_h = h - self._list_y - 120
        self._preview_y = self._list_y + self._list_h + pad

        # Colors
        self._bg = (30, 30, 40)
        self._border = (60, 60, 80)
        self._card_bg = (40, 40, 55)
        self._card_sel = (60, 80, 120)
        self._card_hover = (50, 50, 65)
        self._text = (200, 200, 220)
        self._text_dim = (120, 120, 140)
        self._text_error = (220, 80, 80)
        self._text_warn = (220, 180, 80)
        self._text_ok = (80, 200, 80)
        self._input_bg = (20, 20, 30)
        self._btn_bg = (50, 50, 70)
        self._btn_hover = (70, 70, 100)

        # Russian category display names
        self._category_ru = {
            "furniture": "Меб",
            "wall_object": "Стн",
            "transition": "Пер",
            "nature": "Прд",
            "interactive": "Инт",
            "decoration": "Дкр",
        }

        # Callbacks (set by editor)
        self.on_select: Optional[callable] = None  # callback(bp_id: str)
        self.on_place: Optional[callable] = None  # callback(bp_id: str)
        # ME-2.1-G-3: double-click → open inspector (read-only)
        self.on_inspect: Optional[callable] = None  # callback(bp_id: str)
        self._last_click_bp_id: Optional[str] = None
        self._last_click_time: float = 0.0

    def load(self) -> None:
        """Load AssetStore + CatalogIndex + Validator without activating UI.

        Idempotent — safe to call multiple times. Used by EditorCore.__init__
        to ensure store is available for BlueprintEditor before user opens
        catalog via F3.
        """
        if self._store is not None:
            return  # already loaded
        self._store = AssetStore(self._assets_dir)
        self._store.load()
        self._index = CatalogIndex(self._store)
        self._validator = ResourceValidator(self._pixels_dir)

        # ME-2.1 Foundation fix: activate AssetStore as source of truth
        from data_manager import refresh_object_presets
        from sprite_registry import refresh_entity_sprite_map

        refresh_object_presets(self._store)
        refresh_entity_sprite_map()

    def open(self) -> None:
        """Activate catalog panel for display (F3). Loads data if not yet loaded."""
        self.load()  # idempotent — load if not yet loaded
        self.active = True
        self._search_query = ""
        self._selected_category = None
        self._scroll_offset = 0
        self._selected_bp_id = None
        self._validation = None
        self._update_filtered()
        self._update_category_rects()

    def close(self) -> None:
        """Close catalog."""
        self.active = False
        self._search_active = False

    @property
    def store(self):
        """AssetStore (для переиспользования в BlueprintEditor)."""
        return self._store

    @property
    def validator(self):
        """ResourceValidator (для переиспользования в BlueprintEditor)."""
        return self._validator

    @property
    def selected_bp_id(self) -> Optional[str]:
        """Выбранный blueprint_id (для F4 — открыть inspector выбранного)."""
        return self._selected_bp_id

    @property
    def catalog_index(self):
        """CatalogIndex (для переиспользования в BlueprintInspectorPanel G-5)."""
        return self._index

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle event. Returns True if consumed (editor should stop)."""
        if not self.active:
            return False

        mx, my = pygame.mouse.get_pos()
        rx, ry = self.rect.x, self.rect.y

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.close()
                return True
            if self._search_active:
                if event.key == pygame.K_BACKSPACE:
                    self._search_query = self._search_query[:-1]
                    self._update_filtered()
                    return True
                if event.key == pygame.K_RETURN:
                    self._search_active = False
                    return True
                if event.unicode and event.unicode.isprintable():
                    self._search_query += event.unicode
                    self._update_filtered()
                    return True
            if event.key == pygame.K_F3:
                self.close()
                return True

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                # Close button (absolute)
                close_abs = self._close_rect.move(rx, ry)
                if close_abs.collidepoint(mx, my):
                    self.close()
                    return True
                # Search bar (absolute)
                search_abs = self._search_rect.move(rx, ry)
                if search_abs.collidepoint(mx, my):
                    self._search_active = True
                    return True
                else:
                    self._search_active = False
                # "All" button (absolute)
                all_abs = pygame.Rect(rx + 6, ry + self._cat_y, 30, 20)
                if all_abs.collidepoint(mx, my):
                    self._selected_category = None
                    self._update_filtered()
                    return True
                # Category buttons (absolute — compute positions matching draw)
                cx = rx + 40  # matches draw: rx+6 + 34
                for cat, rect in self._cat_rects:
                    cat_abs = pygame.Rect(cx, ry + self._cat_y, rect.w, rect.h)
                    if cat_abs.collidepoint(mx, my):
                        self._selected_category = None if self._selected_category == cat else cat
                        self._update_filtered()
                        return True
                    cx += rect.w + 3
                # Cards (already absolute — use mx,my directly)
                for bp_id, rect in self._card_rects:
                    if rect.collidepoint(mx, my):
                        # ME-2.1-G-3: double-click detection → on_inspect
                        import time

                        now = time.monotonic()
                        if self._last_click_bp_id == bp_id and (now - self._last_click_time) < 0.4:
                            # Double-click → open inspector
                            if self.on_inspect:
                                self.on_inspect(bp_id)
                            self._last_click_bp_id = None
                            self._last_click_time = 0.0
                        else:
                            # Single-click → select (existing behaviour)
                            self._select_blueprint(bp_id)
                            self._last_click_bp_id = bp_id
                            self._last_click_time = now
                        return True
                # Place button (absolute — matches draw position)
                place_abs = pygame.Rect(rx + 6, ry + self._preview_y + 92, self.rect.w - 12, 24)
                if place_abs.collidepoint(mx, my):
                    if self._selected_bp_id and self._validation and self._validation.can_place:
                        if self.on_place:
                            self.on_place(self._selected_bp_id)
                        self.close()
                        return True

            elif event.button == 4:  # Scroll up
                self._scroll_offset = max(0, self._scroll_offset - 3)
                return True
            elif event.button == 5:  # Scroll down
                self._scroll_offset += 3
                return True

        return False

    def draw(self, screen: pygame.Surface, font, font_small, font_bold) -> None:
        """Draw catalog panel."""
        if not self.active:
            return

        # Panel background
        pygame.draw.rect(screen, self._bg, self.rect)
        pygame.draw.rect(screen, self._border, self.rect, 1)

        rx = self.rect.x
        ry = self.rect.y

        # Search bar
        search_rect = self._search_rect.move(rx, ry)
        pygame.draw.rect(screen, self._input_bg, search_rect)
        pygame.draw.rect(screen, self._border, search_rect, 1)
        search_text = self._search_query
        if self._search_active:
            search_text += "|"
        label = font_small.render(f"🔍 {search_text}", True, self._text)
        screen.blit(label, (search_rect.x + 4, search_rect.y + 4))

        # Close button
        close_rect = self._close_rect.move(rx, ry)
        pygame.draw.rect(screen, self._btn_bg, close_rect)
        pygame.draw.rect(screen, self._border, close_rect, 1)
        close_label = font_small.render("✕", True, self._text)
        screen.blit(close_label, (close_rect.x + 6, close_rect.y + 4))

        # Category buttons
        cx = rx + 6
        cy = ry + self._cat_y
        # "All" button
        all_rect = pygame.Rect(cx, cy, 30, 20)
        color = self._card_sel if self._selected_category is None else self._btn_bg
        pygame.draw.rect(screen, color, all_rect)
        pygame.draw.rect(screen, self._border, all_rect, 1)
        all_label = font_small.render("Все", True, self._text)
        screen.blit(all_label, (all_rect.x + 4, all_rect.y + 3))

        cx += 34
        for cat, rect in self._cat_rects:
            r = rect.move(rx, ry)
            r.x = cx
            r.y = cy
            color = self._card_sel if self._selected_category == cat else self._btn_bg
            pygame.draw.rect(screen, color, r)
            pygame.draw.rect(screen, self._border, r, 1)
            short = self._category_ru.get(cat, cat[:4])
            cat_label = font_small.render(short, True, self._text)
            screen.blit(cat_label, (r.x + 3, r.y + 3))
            cx += r.w + 3

        # Card list
        self._card_rects = []
        list_y = ry + self._list_y
        card_h = 22
        max_cards = self._list_h // card_h

        visible_ids = self._filtered_ids[self._scroll_offset : self._scroll_offset + max_cards]

        for i, bp_id in enumerate(visible_ids):
            card_y = list_y + i * card_h
            card_rect = pygame.Rect(rx + 4, card_y, self.rect.w - 8, card_h - 2)
            self._card_rects.append((bp_id, card_rect))

            is_selected = bp_id == self._selected_bp_id
            color = self._card_sel if is_selected else self._card_bg
            pygame.draw.rect(screen, color, card_rect)

            preview = self._index.get_preview(bp_id) if self._index else None
            if preview:
                label_text = preview.get("label", bp_id)
                card_label = font_small.render(label_text, True, self._text)
                screen.blit(card_label, (card_rect.x + 4, card_rect.y + 3))

                cat_text = self._category_ru.get(preview.get("category", ""), preview.get("category", ""))
                cat_label = font_small.render(cat_text, True, self._text_dim)
                screen.blit(cat_label, (card_rect.right - cat_label.get_width() - 4, card_rect.y + 3))

        # Scroll indicator
        if len(self._filtered_ids) > max_cards:
            scroll_text = font_small.render(
                f"({self._scroll_offset + 1}-{min(self._scroll_offset + max_cards, len(self._filtered_ids))}"
                f"/{len(self._filtered_ids)})",
                True,
                self._text_dim,
            )
            screen.blit(scroll_text, (rx + 4, list_y + self._list_h - 16))

        # Preview area
        pv_y = ry + self._preview_y
        pygame.draw.line(screen, self._border, (rx + 4, pv_y), (rx + self.rect.w - 4, pv_y))

        if self._selected_bp_id and self._index:
            preview = self._index.get_preview(self._selected_bp_id)
            if preview:
                # Label
                lbl = font_bold.render(preview.get("label", ""), True, self._text)
                screen.blit(lbl, (rx + 6, pv_y + 4))

                # Validation status
                if self._validation:
                    if self._validation.can_place:
                        status = "✅ Готов к размещению"
                        status_color = self._text_ok
                    else:
                        status = "❌ Нельзя разместить"
                        status_color = self._text_error
                    status_label = font_small.render(status, True, status_color)
                    screen.blit(status_label, (rx + 6, pv_y + 24))

                    # Show errors/warnings
                    issue_y = pv_y + 40
                    for issue in self._validation.issues[:3]:
                        if issue.level == "error":
                            prefix = "❌"
                            color = self._text_error
                        elif issue.level == "warning":
                            prefix = "⚠"
                            color = self._text_warn
                        else:
                            prefix = "ℹ"
                            color = self._text_dim
                        issue_text = font_small.render(f"{prefix} {issue.message[:40]}", True, color)
                        screen.blit(issue_text, (rx + 6, issue_y))
                        issue_y += 14

                # Category + tags
                cat_str = self._category_ru.get(preview.get("category", ""), preview.get("category", ""))
                tags_str = ", ".join(preview.get("tags", [])[:4])
                cat_label = font_small.render(f"Кат: {cat_str}", True, self._text_dim)
                screen.blit(cat_label, (rx + 6, pv_y + 60))
                tags_label = font_small.render(f"Теги: {tags_str}", True, self._text_dim)
                screen.blit(tags_label, (rx + 6, pv_y + 74))

                # Place button
                place_rect = pygame.Rect(rx + 6, pv_y + 92, self.rect.w - 12, 24)
                can = self._validation and self._validation.can_place
                color = self._btn_hover if can else (40, 40, 40)
                pygame.draw.rect(screen, color, place_rect)
                pygame.draw.rect(screen, self._border, place_rect, 1)
                place_text = "→ Разместить на карте" if can else "Нельзя разместить"
                place_label = font.render(place_text, True, self._text if can else self._text_dim)
                screen.blit(
                    place_label,
                    (place_rect.x + 8, place_rect.y + 4),
                )

        # Footer
        count_text = font_small.render(
            f"{self._index.count if self._index else 0} ассетов",
            True,
            self._text_dim,
        )
        screen.blit(count_text, (rx + 4, self.rect.bottom - 16))

    def _update_filtered(self) -> None:
        """Rebuild filtered blueprint list."""
        if not self._index:
            self._filtered_ids = []
            return
        if self._search_query:
            searched = set(self._index.search(self._search_query))
        else:
            searched = set(self._index.list_all())
        if self._selected_category:
            filtered = set(self._index.filter(category=self._selected_category))
            self._filtered_ids = sorted(searched & filtered)
        else:
            self._filtered_ids = sorted(searched)
        self._scroll_offset = 0

    def _update_category_rects(self) -> None:
        """Build category button rects with Russian labels."""
        self._cat_rects = []
        if not self._index:
            return
        x = 40  # after "Все" button
        for cat in self._index.list_categories():
            w = 32  # fixed width, fits 6 buttons + "Все" in 250px
            self._cat_rects.append((cat, pygame.Rect(0, 0, w, 20)))
            x += w + 3

    def _select_blueprint(self, bp_id: str) -> None:
        """Select a blueprint and validate it."""
        self._selected_bp_id = bp_id
        if self._store and self._validator:
            record = self._store.get_blueprint(bp_id)
            if record and record.data:
                self._validation = self._validator.validate_blueprint(record.data)
            else:
                self._validation = None
        if self.on_select:
            self.on_select(bp_id)
