# backend/tests/test_topic_extractor_phrases.py
"""
cd C:\\DDD\\Codex\\VSC_Enigma\\Enigma\backend
python -m pytest tests/test_topic_extractor_phrases.py -v
"""

import pytest
from app.services.npc.topic_extractor import extract_topic


def test_t07_phrase_how_are_you():
    topic = extract_topic(event_type="player_interacts", raw_input="Люся, как дела?")
    assert topic == "самочувствие", f"Ожидалось 'самочувствие', получено '{topic}'"

def test_t07_phrase_who_are_you():
    topic = extract_topic(event_type="player_interacts", raw_input="расскажи о себе")
    assert topic == "биография", f"Ожидалось 'биография', получено '{topic}'"

def test_t07_keyword_still_works():
    topic = extract_topic(event_type="player_interacts", raw_input="хочу купить меч")
    assert topic == "торговля", f"Ожидалось 'торговля', получено '{topic}'"

def test_t07_fallback_to_observation():
    topic = extract_topic(event_type="player_interacts", raw_input="ыыы")
    assert topic == "разговор", f"Ожидалось 'разговор', получено '{topic}'"