"""
path: /frontend/ui_workbench/windows/debug_window.py
Назначение: CCH-4 Character Debugger — окно Workbench layer 4 (read-only).
    «СЕЙЧАС» из runtime NPCState (causal_ledger, body_state, stress, will_state,
    life_project_state, intent), «ИСТОЧНИКИ» из канон-хроники (entries,
    white_spots, npc_beliefs, cause_candidates). 4 состояния данных: KNOWN /
    NOT_AUTHORED / NOT_LOADED / INIT_ERROR. Read-only (запрет 10 ADR-O-420);
    изоляция от HUD — не входит в WorldSnapshotDTO (запрет 7 ADR-O-420).
Зависимости: ui_workbench.manifests, pygame (для K_F11)
Основные сущности: DEBUG_MANIFEST, draw_debug_window
"""
import pygame
from ui_workbench.manifests import InputBinding, WindowManifest, WindowState

DEBUG_MANIFEST = WindowManifest(
    window_id="character_debugger",
    title="Character Debugger",
    layer=4,  # UI Doctrine layer 4 — метаинформация/отладка (CCH-4 FR-9.x)
    data_source="character_debug",  # GET /chronicle/{campaign}/{npc}/debug
    default_state=WindowState.HIDDEN,
    anchor="top_left",
    offset=(24, 60),
    size_policy=(0.42, 0.78),
    min_size=(500, 360),
    max_size=(980, 1100),
    z_order=12,
    binding=InputBinding(hotkey=pygame.K_F11, click_title_collapse=True),
)


def _state_color(state: str) -> tuple[int, int, int]:
    """Цвет 4-х состояний данных (дополнение Мастера 2026-10-25)."""
    return {
        "KNOWN": (130, 200, 130),
        "NOT_AUTHORED": (200, 180, 100),
        "NOT_LOADED": (180, 130, 200),
        "INIT_ERROR": (220, 80, 80),
    }.get(state, (200, 200, 200))


def draw_debug_window(
    surface: pygame.Surface,
    rect: pygame.Rect,
    state: WindowState,
    data: dict | None,
    font_title,
    font_body,
    font_small,
    colors: dict,
) -> None:
    """Read-only render Character Debugger. Точки: СЕЙЧАС / ИСТОЧНИКИ / СОСТОЯНИЯ.

    data — JSON ответ GET /chronicle/{campaign}/{npc}/debug:
        {
          "campaign_id": str, "npc_id": str,
          "now": {...} | None,
          "sources": {...} | None,
          "states": {"runtime": str, "chronicle": str}
        }
    """
    # Фон
    surface.fill(colors.get("surface_panel", (26, 26, 36)), rect)
    pygame.draw.rect(surface, colors.get("border", (70, 70, 90)), rect, 1)

    pad = 12
    y = rect.top + pad

    # Заголовок
    title = font_title.render(
        f"Character Debugger — {data.get('npc_id', '?') if data else 'нет данных'}",
        True,
        colors.get("text_primary", (222, 222, 232)),
    )
    surface.blit(title, (rect.left + pad, y))
    y += title.get_height() + 6

    # Подзаголовок с кампанией
    if data:
        sub = font_small.render(
            f"campaign: {data.get('campaign_id', '?')}",
            True,
            colors.get("text_muted", (150, 150, 165)),
        )
        surface.blit(sub, (rect.left + pad, y))
        y += sub.get_height() + 8

    if not data:
        msg = font_body.render(
            "Нет данных — откройте NPC в редакторе хроники или подождите загрузки",
            True,
            colors.get("text_muted", (150, 150, 165)),
        )
        surface.blit(msg, (rect.left + pad, y))
        return

    # ── СОСТОЯНИЯ (4 индикатора) ────────────────────────────────────────────
    states = data.get("states", {})
    for label, key in (("Runtime", "runtime"), ("Хроника", "chronicle")):
        s = states.get(key, "NOT_LOADED")
        color = _state_color(s)
        badge = font_small.render(f"{label}: {s}", True, color)
        surface.blit(badge, (rect.left + pad, y))
        y += badge.get_height() + 4
    y += 6

    # ── СЕЙЧАС (runtime) ────────────────────────────────────────────────────
    now = data.get("now")
    section = font_body.render("▾ СЕЙЧАС", True, colors.get("accent", (200, 160, 80)))
    surface.blit(section, (rect.left + pad, y))
    y += section.get_height() + 4

    if now is None:
        none_msg = font_small.render(
            "Runtime NPCState не загружен (NOT_LOADED/INIT_ERROR)",
            True,
            colors.get("text_muted", (150, 150, 165)),
        )
        surface.blit(none_msg, (rect.left + pad + 8, y))
        y += none_msg.get_height() + 8
    else:
        # Краткая сводка
        for label, value in (
            ("Имя", now.get("name", "?")),
            ("Роль", now.get("current_role", "?")),
            ("Stress", f"{now.get('stress', 0.0):.2f}"),
            ("Will", now.get("will_state", "?")),
            ("AffectiveLoad", f"{now.get('affective_load', 0.0):.2f}"),
            ("LifeProject", now.get("life_project_state", "?")),
            ("Intent", now.get("intent") or "—"),
            ("IntentTarget", now.get("intent_target") or "—"),
            ("Ledger size", str(now.get("ledger_size", 0))),
        ):
            line = font_small.render(
                f"{label:14}: {value}",
                True,
                colors.get("text_primary", (222, 222, 232)),
            )
            surface.blit(line, (rect.left + pad + 8, y))
            y += line.get_height() + 2
        # Drives_base (контроль/значимость/страх/желание)
        drives = now.get("drives_base", {})
        if drives:
            line = font_small.render(
                f"drives_base    : {dict(drives)}",
                True,
                colors.get("text_muted", (150, 150, 165)),
            )
            surface.blit(line, (rect.left + pad + 8, y))
            y += line.get_height() + 2
        # Body state (краткая сводка)
        bs = now.get("body_state") or {}
        if isinstance(bs, dict) and not bs.get("disabled"):
            hp = bs.get("current_hp", "?")
            pain = bs.get("pain", 0)
            fatigue = bs.get("fatigue", 0)
            line = font_small.render(
                f"body_state     : hp={hp} pain={pain:.1f} fatigue={fatigue:.1f}",
                True,
                colors.get("text_muted", (150, 150, 165)),
            )
            surface.blit(line, (rect.left + pad + 8, y))
            y += line.get_height() + 4
        # Causal ledger (последние 5)
        ledger = now.get("causal_ledger_last_20", [])
        if ledger:
            line = font_small.render(
                f"causal_ledger (последние {min(5, len(ledger))} из {len(ledger)}):",
                True,
                colors.get("text_muted", (150, 150, 165)),
            )
            surface.blit(line, (rect.left + pad + 8, y))
            y += line.get_height() + 2
            for entry in ledger[-5:]:
                tick = entry.get("tick", "?")
                field = entry.get("field", "?")
                cause_id = entry.get("cause", {}).get("source_event_id", "—")
                line = font_small.render(
                    f"  tick={tick} {field} ← {cause_id[:12]}",
                    True,
                    colors.get("text_muted", (150, 150, 165)),
                )
                surface.blit(line, (rect.left + pad + 12, y))
                y += line.get_height() + 1
        y += 8

    # ── ИСТОЧНИКИ (канон-хроника) ───────────────────────────────────────────
    sources = data.get("sources")
    section2 = font_body.render("▾ ИСТОЧНИКИ (канон)", True, colors.get("accent", (200, 160, 80)))
    surface.blit(section2, (rect.left + pad, y))
    y += section2.get_height() + 4

    if sources is None:
        none_msg = font_small.render(
            "Канон-хроника отсутствует (NOT_AUTHORED)",
            True,
            colors.get("text_muted", (150, 150, 165)),
        )
        surface.blit(none_msg, (rect.left + pad + 8, y))
        return

    line = font_small.render(
        f"chronicle_id   : {sources.get('chronicle_id', '?')}",
        True,
        colors.get("text_primary", (222, 222, 232)),
    )
    surface.blit(line, (rect.left + pad + 8, y))
    y += line.get_height() + 2

    line = font_small.render(
        f"canonical_v    : {sources.get('canonical_version', '?')}",
        True,
        colors.get("text_primary", (222, 222, 232)),
    )
    surface.blit(line, (rect.left + pad + 8, y))
    y += line.get_height() + 2

    line = font_small.render(
        f"game_start_age : {sources.get('game_start_age', '—')}",
        True,
        colors.get("text_primary", (222, 222, 232)),
    )
    surface.blit(line, (rect.left + pad + 8, y))
    y += line.get_height() + 4

    entries = sources.get("entries", [])
    line = font_small.render(
        f"entries        : {len(entries)}",
        True,
        colors.get("text_primary", (222, 222, 232)),
    )
    surface.blit(line, (rect.left + pad + 8, y))
    y += line.get_height() + 2

    ws_list = sources.get("white_spots", [])
    line = font_small.render(
        f"white_spots    : {len(ws_list)}",
        True,
        colors.get("text_primary", (222, 222, 232)),
    )
    surface.blit(line, (rect.left + pad + 8, y))
    y += line.get_height() + 2

    line = font_small.render(
        f"npc_beliefs    : {sources.get('npc_beliefs_count', 0)}",
        True,
        colors.get("text_primary", (222, 222, 232)),
    )
    surface.blit(line, (rect.left + pad + 8, y))
    y += line.get_height() + 2

    line = font_small.render(
        f"cause_cand     : {sources.get('cause_candidates_count', 0)}",
        True,
        colors.get("text_primary", (222, 222, 232)),
    )
    surface.blit(line, (rect.left + pad + 8, y))
    y += line.get_height() + 4

    # Последние 8 entries (kind + subject_hint)
    if entries:
        line = font_small.render(
            f"последние {min(8, len(entries))} записей:",
            True,
            colors.get("text_muted", (150, 150, 165)),
        )
        surface.blit(line, (rect.left + pad + 8, y))
        y += line.get_height() + 2
        for e in entries[-8:]:
            subj = e.get("subject_id") or {}
            hint = subj.get("name_hint") or subj.get("npc_id") or subj.get("white_spot_id") or "—"
            kind = e.get("kind_value", e.get("kind", "?"))
            age = e.get("historical_age")
            age_str = f" age={age}" if age is not None else ""
            line = font_small.render(
                f"  [{kind}]{age_str} subj={hint}",
                True,
                colors.get("text_muted", (150, 150, 165)),
            )
            surface.blit(line, (rect.left + pad + 12, y))
            y += line.get_height() + 1

    # White spots
    if ws_list:
        y += 4
        line = font_small.render(
            f"white_spots ({len(ws_list)}):",
            True,
            colors.get("text_muted", (150, 150, 165)),
        )
        surface.blit(line, (rect.left + pad + 8, y))
        y += line.get_height() + 2
        for ws in ws_list[:5]:
            ws_id = ws.get("white_spot_id", "?")
            label = ws.get("label", "?")
            rstate = ws.get("resolution_state", "?")
            line = font_small.render(
                f"  [{rstate}] {ws_id} «{label}»",
                True,
                colors.get("text_muted", (150, 150, 165)),
            )
            surface.blit(line, (rect.left + pad + 12, y))
            y += line.get_height() + 1
