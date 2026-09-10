"""
path: /project/backend/tests/micro/test_self_talk_sentinel.py
Назначение: Р-А — SELF_TALK_SENTINEL (внешне слышимое бормотание) не создаёт
    агентных последствий фантома (STM / отношения / L1), но сохраняет канал
    подслушивания игрока (journal). Контроль: реальный адресат обрабатывается.
Зависимости: app.domain.communication, app.services.events.npc_dialogue_subscriber
Основные сущности: спай-двойники сторов, три теста Р-А

Запуск: cd backend; python -m pytest tests/micro/test_self_talk_sentinel.py -v; cd ..
"""

from types import SimpleNamespace

from app.domain.communication import SELF_TALK_SENTINEL
from app.services.events.npc_dialogue_subscriber import NpcDialogueSubscriber


class _SpyRelationships:
    def __init__(self):
        self.calls = []

    def update(self, **kwargs):
        self.calls.append(kwargs)


class _SpyMemory:
    def __init__(self):
        self.turns = []

    def add_dialogue_turn(self, **kwargs):
        self.turns.append(kwargs)


class _SpyChronicle:
    def __init__(self):
        self.commits = []

    def commit_tick_buffer(self, events, tick):
        self.commits.append((list(events), tick))


class _SpyAvatar:
    def __init__(self):
        self.journal = []

    def append_journal(self, **kwargs):
        self.journal.append(kwargs)


def _make_subscriber(rel, mem, chronicle, avatar):
    return NpcDialogueSubscriber(
        memory_manager=mem,
        relationship_store=rel,
        avatar_service=avatar,
        spatial_query_provider=lambda: SimpleNamespace(
            player_distances=lambda ids: {"thief_shadow": 2.0}
        ),
        campaign_id_provider=lambda: "test_campaign",
        l1_chronicle=chronicle,
        tick_provider=lambda: 7,
    )


def _evt(target_id: str) -> dict:
    # dict-форма — официальный тестовый контракт подписчика
    return {
        "source": "thief_shadow",
        "payload": {
            "target_id": target_id,
            "text": "Опять этот проклятый замок...",
            "tone": "ANGRY",
            "topic": "self",
        },
    }


def test_self_talk_no_phantom_agent_processing():
    rel, mem, chron, avatar = _SpyRelationships(), _SpyMemory(), _SpyChronicle(), _SpyAvatar()
    sub = _make_subscriber(rel, mem, chron, avatar)

    sub.on_npc_spoke(_evt(SELF_TALK_SENTINEL))

    assert rel.calls == [], "Р-А: фантом не должен получать рёбра отношений"
    assert mem.turns == [], "Р-А: фантом не должен получать STM-сессию"
    assert chron.commits == [], "Р-А: фантом не должен попадать в L1Chronicle"


def test_self_talk_player_still_overhears():
    rel, mem, chron, avatar = _SpyRelationships(), _SpyMemory(), _SpyChronicle(), _SpyAvatar()
    sub = _make_subscriber(rel, mem, chron, avatar)

    sub.on_npc_spoke(_evt(SELF_TALK_SENTINEL))

    # Экстернализованный солилоквий: игрок на дистанции 2.0 (< 8.0) подслушивает
    assert len(avatar.journal) == 1, "Р-А: бормотание остаётся слышимым (journal-only)"


def test_real_listener_control_path_intact():
    rel, mem, chron, avatar = _SpyRelationships(), _SpyMemory(), _SpyChronicle(), _SpyAvatar()
    sub = _make_subscriber(rel, mem, chron, avatar)

    sub.on_npc_spoke(_evt("guard_borko"))

    # Контроль: реальный адресат — полная обработка (STM + rel + L1)
    assert len(mem.turns) == 1
    assert len(rel.calls) == 1
    assert rel.calls[0]["source"] == "guard_borko"
    assert rel.calls[0]["target"] == "thief_shadow"
    assert len(chron.commits) == 1


def _dto_evt(target_id: str, visibility: str, radius: float):
    # Р-Б2: реальные EventDTO — единственный честный путь проверки мембраны
    # (dict-события по контракту fail-open). Фабрика, не конструктор (§13.4).
    from app.domain.events import EventDTO

    return EventDTO.create(
        event_type="npc_spoke",
        source="thief_shadow",
        payload={
            "target_id": target_id,
            "text": "Ты слышал про золото?",
            "tone": "ANGRY",
            "topic": "gold",
        },
        visibility=visibility,
        radius=radius,
        persistence_level="working",
    )


def _make_sub_with_distance(dist: float, rel, mem, chron, avatar):
    # Р-Б2: spatial-query с distance + позициями (мембрана включается только
    # при наличии позиции адресата — S198-паритет)
    return NpcDialogueSubscriber(
        memory_manager=mem,
        relationship_store=rel,
        avatar_service=avatar,
        spatial_query_provider=lambda: SimpleNamespace(
            player_distances=lambda ids: {"thief_shadow": 2.0},
            distance=lambda a, b: dist,
            _npc_positions={"thief_shadow": {}, "guard_borko": {}},
        ),
        campaign_id_provider=lambda: "test_campaign",
        l1_chronicle=chron,
        tick_provider=lambda: 7,
    )


def test_membrane_filters_far_public_listener():
    # Public radius=10, дистанция 25 → телепатия rel-трубы закрыта: агентной обработки нет
    rel, mem, chron, avatar = _SpyRelationships(), _SpyMemory(), _SpyChronicle(), _SpyAvatar()
    sub = _make_sub_with_distance(25.0, rel, mem, chron, avatar)

    sub.on_npc_spoke(_dto_evt("guard_borko", "public", 10.0))

    assert mem.turns == [], "Р-Б2: адресат вне радиуса не получает STM"
    assert rel.calls == [], "Р-Б2: адресат вне радиуса не получает rel-дельт"
    assert chron.commits == [], "Р-Б2: адресат вне радиуса не попадает в L1"


def test_membrane_whisper_identity_pass():
    # Whisper: identity-гейт адресата — дистанция игнорируется (двое вплотную)
    rel, mem, chron, avatar = _SpyRelationships(), _SpyMemory(), _SpyChronicle(), _SpyAvatar()
    sub = _make_sub_with_distance(25.0, rel, mem, chron, avatar)

    sub.on_npc_spoke(_dto_evt("guard_borko", "whisper", 3.0))

    assert len(mem.turns) == 1, "Р-Б2: whisper-адресат слышит независимо от дистанции"
    assert len(rel.calls) == 1


def test_membrane_near_public_listener_processes():
    # Public radius=10, дистанция 4 → мембрана не перерезает честный контакт
    rel, mem, chron, avatar = _SpyRelationships(), _SpyMemory(), _SpyChronicle(), _SpyAvatar()
    sub = _make_sub_with_distance(4.0, rel, mem, chron, avatar)

    sub.on_npc_spoke(_dto_evt("guard_borko", "public", 10.0))

    assert len(mem.turns) == 1
    assert len(rel.calls) == 1
    assert len(chron.commits) == 1


# ---------------------------------------------------------------------------
# Р-Г (GC-DIALOGUE-01): честный журнал — порог подслушивания из event.radius
# (SpeechExposure SSOT, Р-В), не хардкод 8.0. Замок: фикс без этих проверок
# не переживает регресс батареи.
# ---------------------------------------------------------------------------


def _make_sub_with_player_dist(player_dist: float, rel, mem, chron, avatar):
    # Р-Г: стаб с настраиваемой дистанцией игрока до спикера (спикер в тестах
    # этого файла — thief_shadow); distance/_npc_positions сохранены, чтобы
    # мембрана адресата оставалась в контуре (S198-паритет)
    return NpcDialogueSubscriber(
        memory_manager=mem,
        relationship_store=rel,
        avatar_service=avatar,
        spatial_query_provider=lambda: SimpleNamespace(
            player_distances=lambda ids: {"thief_shadow": player_dist},
            distance=lambda a, b: 25.0,
            _npc_positions={"thief_shadow": {}, "guard_borko": {}},
        ),
        campaign_id_provider=lambda: "test_campaign",
        l1_chronicle=chron,
        tick_provider=lambda: 7,
    )


def test_journal_whisper_radius_gates_eavesdrop():
    # Р-Г: whisper (radius 3.0) с 5.0 м — хардкод 8.0 журналил (баг Р-Г),
    # SSOT запрещает: слышно только вплотную
    rel, mem, chron, avatar = _SpyRelationships(), _SpyMemory(), _SpyChronicle(), _SpyAvatar()
    sub = _make_sub_with_player_dist(5.0, rel, mem, chron, avatar)

    sub.on_npc_spoke(_dto_evt("guard_borko", "whisper", 3.0))

    assert avatar.journal == [], "Р-Г: whisper за пределами 3.0 м не журналируется"


def test_journal_shout_reaches_beyond_legacy_threshold():
    # Р-Г: shout-класс (radius 15.0) с 12.0 м — хардкод резал потолок,
    # SSOT расширяет: крик физически слышим дальше 8.0 м
    rel, mem, chron, avatar = _SpyRelationships(), _SpyMemory(), _SpyChronicle(), _SpyAvatar()
    sub = _make_sub_with_player_dist(12.0, rel, mem, chron, avatar)

    sub.on_npc_spoke(_dto_evt("guard_borko", "public", 15.0))

    assert len(avatar.journal) == 1, "Р-Г: shout слышен на 12.0 м"


def test_journal_private_never_eavesdropped():
    # Р-Г: private (radius 0.0) — внутренняя когниция не экстернализована:
    # даже вплотную (0.5 м) журнал глух
    rel, mem, chron, avatar = _SpyRelationships(), _SpyMemory(), _SpyChronicle(), _SpyAvatar()
    sub = _make_sub_with_player_dist(0.5, rel, mem, chron, avatar)

    sub.on_npc_spoke(_dto_evt("guard_borko", "private", 0.0))

    assert avatar.journal == [], "Р-Г: private не слышим ни на какой дистанции"


def test_journal_radius_999_falls_back_not_scene_wide():
    # Р-Г/D5: 999-дефолт EventDTO.create (ADR-148) не раздувает журнал на всю
    # сцену — валидити-гард уводит на легаси-фоллбек 8.0
    rel, mem, chron, avatar = _SpyRelationships(), _SpyMemory(), _SpyChronicle(), _SpyAvatar()
    sub = _make_sub_with_player_dist(50.0, rel, mem, chron, avatar)

    sub.on_npc_spoke(_dto_evt("guard_borko", "public", 999.0))

    assert avatar.journal == [], "Р-Г: 999 не пробивает журнал (фоллбек 8.0)"


def test_journal_dict_event_fail_open_legacy():
    # Р-Г: dict-событие без radius — fail-open по легаси-порогу 8.0
    # (паритет с Р-Б2: dict-контракт слышит как раньше)
    rel, mem, chron, avatar = _SpyRelationships(), _SpyMemory(), _SpyChronicle(), _SpyAvatar()
    sub = _make_sub_with_player_dist(2.0, rel, mem, chron, avatar)

    sub.on_npc_spoke(_evt("guard_borko"))

    assert len(avatar.journal) == 1, "Р-Г: fail-open — dict-событие слышит по легаси-порогу"