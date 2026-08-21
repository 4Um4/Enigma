"""
SUPERBOX-AVATAR-SYNC (S208, P0 closure): ownership аватара восстановлен.

Доказывает:
  [T1] Новый аватар (default-ветка): money=48, БЕЗ ArchitecturalViolationError.
       (Бывшая мёртвая ветка — падала с Stage 0 Task 0.4.)
  [T2] ИСХОДНЫЙ P0-ТРИГГЕР: сохранение БЕЗ body_state → load_state не падает,
       body_state={money: 48}. (Старый код: _state.body_state = {} → violation.)
  [T3] Write-back (бывший game_loop:1777): full-sync + hp-ветка + disabled-ветка
       через AvatarStateApplicator — без violation, значения корректны.
  [T4] Реакции (бывший phase_6 object.__setattr__): stress/emotion через
       applicator, границы [0,100] соблюдаются.
  [T5] Save/load round-trip: money и current_hp переживают цикл.

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/avatar_ownership_sync_test.py
"""
import json
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

from app.models.npc_state import NPCState
from app.services.avatar_state_applicator import AvatarStateApplicator
from app.services.player_avatar_service import PlayerAvatarService

CAMP, HERO = "ownership_test", "hero"


def main() -> int:
    print("=" * 64)
    print("SUPERBOX-AVATAR-SYNC: ownership аватара (S208 / P0)")
    print("=" * 64)
    ok = True
    root = Path(tempfile.mkdtemp(prefix="avatar_own_"))

    # ── T1: default-ветка (новый аватар) ────────────────────────────
    svc = PlayerAvatarService(root=str(root))
    s = svc.load_state(CAMP, HERO)
    t1 = s.body_state.get("money") == 48
    print(f"[T1] Новый аватар: money={s.body_state.get('money')} — "
          f"{'✅' if t1 else '❌'} (default-ветка жива, без violation)")
    ok = ok and t1

    # ── T2: исходный P0-триггер (сохранение без body_state) ────────
    broken_root = root / "broken"
    broken_root.mkdir()
    (broken_root / CAMP).mkdir()
    (broken_root / CAMP / "player_avatar.json").write_text(
        json.dumps({"state": {"npc_id": HERO, "stress": 0.1}}, ensure_ascii=False),
        encoding="utf-8",
    )
    svc2 = PlayerAvatarService(root=str(broken_root))
    try:
        s2 = svc2.load_state(CAMP, HERO)
        t2 = s2.body_state.get("money") == 48
        print(f"[T2] Сохранение без body_state: load OK, money="
              f"{s2.body_state.get('money')} — {'✅' if t2 else '❌'} (исходный P0 закрыт)")
        ok = ok and t2
    except Exception as e:
        print(f"[T2] ❌ P0-триггер жив: {type(e).__name__}: {e}")
        ok = False

    # ── T3: write-back через applicator ─────────────────────────────
    AvatarStateApplicator.apply_pipeline_result(s, {"body_state": {"current_hp": 5.0, "money": 48}})
    t3a = s.body_state["current_hp"] == 5.0
    AvatarStateApplicator.apply_pipeline_result(s, {"hp": 7})
    t3b = s.body_state["current_hp"] == 7
    # DISABLED-ветка (body_state falsy → BODY_STATE_DISABLED_DATA). Вход
    # воспроизводим ТОЛЬКО через свежий аватар с пустым body_state —
    # прямой write {} из теста сам был бы violation (guard прав для всех).
    _fresh = NPCState(npc_id="fresh_hero")  # body_state = {} (default_factory)
    AvatarStateApplicator.apply_pipeline_result(_fresh, {"hp": 3})
    t3c = (_fresh.body_state["current_hp"] == 3
           and "shock_impulse" in _fresh.body_state)
    print(f"[T3] Write-back: full-sync={t3a}, hp={t3b}, disabled={t3c} — "
          f"{'✅' if (t3a and t3b and t3c) else '❌'}")
    ok = ok and t3a and t3b and t3c

    # ── T4: реакции через applicator (бывший object.__setattr__) ────
    from app.models.npc_state import EmotionTag
    AvatarStateApplicator.apply_reaction(s, stress_delta=+200.0)   # clamp 100
    t4a = s.stress == 100.0
    AvatarStateApplicator.apply_reaction(s, stress_delta=-300.0, emotion=EmotionTag.NEUTRAL)
    t4b = s.stress == 0.0 and s.emotion == EmotionTag.NEUTRAL
    print(f"[T4] Реакции: clamp-верх={t4a}, clamp-низ+emotion={t4b} — "
          f"{'✅' if (t4a and t4b) else '❌'} (object.__setattr__ мёртв)")
    ok = ok and t4a and t4b

    # ── T5: save/load round-trip ────────────────────────────────────
    # Артефакт-строки удалены; ассерт синхронизирован с реальным состоянием s:
    # T3b оставил current_hp=7 (DISABLED-ветка ушла на _fresh), T4 — stress=0.
    svc.save_state(CAMP, s)
    s3 = svc.load_state(CAMP, HERO)
    t5 = (s3.body_state.get("current_hp") == 7.0
          and s3.body_state.get("money") == 48
          and s3.stress == 0.0)
    print(f"[T5] Round-trip: hp={s3.body_state.get('current_hp')}, "
          f"money={s3.body_state.get('money')}, stress={s3.stress} — "
          f"{'✅' if t5 else '❌'}")
    ok = ok and t5

    print("=" * 64)
    print("🎉 AVATAR OWNERSHIP ВОССТАНОВЛЕН — P0 ЗАКРЫТ" if ok else "❌ ТЕСТ С ОШИБКАМИ")
    print("=" * 64)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())