"""
Файл: backend/tests/test_p7_11_last_words.py
Назначение: Проверка подбора цитат.

Запуск: cd backend; python -m pytest tests/test_p7_11_last_words.py -v -s; cd ..
"""

import pytest
from app.models.fate import FateOutcome
from app.models.last_words import LastWordTone
from app.models.social_fabric import RelationshipSnapshot
from app.services.social.last_words_system import LastWordsSystem
from app.services.social.social_fabric_tracker import SocialFabricTracker


class TestP711LastWords:
    """P7-11: Тесты системы последних слов."""

    @pytest.fixture
    def fabric(self) -> SocialFabricTracker:
        f = SocialFabricTracker()
        f.set_baseline("maid_lusya", "player", RelationshipSnapshot(
            source_id="maid_lusya", target_id="player", trust=80.0, fear=0.0, affection=0.0, debt=0.0, respect=0.0
        ))
        return f

    def test_no_quote_for_unknown_fate(self, fabric):
        """Нет цитаты, если судьба не определена."""
        system = LastWordsSystem()
        assert system.get_last_word("maid_lusya", None, fabric) is None

    def test_quote_matches_fate(self, fabric):
        """Цитата соответствует судьбе."""
        system = LastWordsSystem()
        lw = system.get_last_word("maid_lusya", FateOutcome.ESCAPE, fabric)
        assert lw is not None
        assert "Спасибо" in lw.quote

    def test_tone_reflects_relationship(self, fabric):
        """Тон отражает отношение к игроку."""
        system = LastWordsSystem()
        lw = system.get_last_word("maid_lusya", FateOutcome.ESCAPE, fabric)
        assert lw.tone == LastWordTone.GRATEFUL # trust=80 -> grateful

    def test_broken_tone_for_low_trust(self):
        """Тон broken при низком доверии."""
        fabric = SocialFabricTracker()
        fabric.set_baseline("maid_lusya", "player", RelationshipSnapshot(
            source_id="maid_lusya", target_id="player", trust=-50.0, fear=0.0, affection=0.0, debt=0.0, respect=0.0
        ))
        system = LastWordsSystem()
        lw = system.get_last_word("maid_lusya", FateOutcome.BROKEN, fabric)
        assert lw.tone == LastWordTone.BROKEN