"""End-to-End Verification Tests for Synchronized Voice Capabilities and ElevenLabs TTS Integration.

Tests cover:
1. Explicit voice requests produce playable audio with intended answers.
2. The agent accurately answers "Can you reply in audio?" without false denials.
3. Text-only requests follow the user's output preference (audio_url is None).
4. Manglish / Malayalam speech uses verified supported approach with clean_for_speech.
5. ElevenLabs failure produces a clear text fallback and reports generation_failed honestly.
6. Each request produces only one audio response (no duplicate generation).
7. Conversation history records the transcript, audio_url, and actual audio_status.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure customer-agent is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import pytest
from fastapi.testclient import TestClient

from app import app, call_horus, capability_registry, tts_handler
from media.tts_handler import TTSHandler, clean_for_speech, detect_voice_intent
import db


@pytest.fixture
def temp_db(monkeypatch):
    """Use an isolated temporary SQLite database for each test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = Path(tf.name)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    db.init_db(db_path=db_path)
    yield db_path
    if db_path.exists():
        db_path.unlink(missing_ok=True)


@pytest.fixture
def test_client():
    return TestClient(app)


# ==============================================================================
# TEST 1: Explicit voice requests produce playable audio with intended answer
# ==============================================================================
def test_explicit_voice_request_produces_audio(temp_db):
    """Voice requests such as 'voice aayi parayu' or 'read this aloud' produce audio."""
    session_id = "test-session-voice-explicit"
    mock_audio_bytes = b"ID3\x04\x00\x00\x00fake-mp3-bytes-for-testing"

    with patch.object(TTSHandler, "is_configured", property(lambda self: True)), \
         patch.object(tts_handler, "synthesize_speech", return_value=(mock_audio_bytes, "audio/mpeg")) as mock_synth, \
         patch("app.get_client") as mock_client_getter:

        mock_anthropic = MagicMock()
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Octapus provides AI automation, web development, and digital marketing."
        mock_response.content = [text_block]
        mock_anthropic.messages.create.return_value = mock_response
        mock_client_getter.return_value = mock_anthropic

        resp = call_horus(
            session_id=session_id,
            user_message="voice aayi parayu, what are your services?",
        )

        assert "Octapus provides AI automation" in str(resp)
        assert resp.audio_url is not None
        assert resp.audio_url.startswith("data:audio/mpeg;base64,")
        assert resp.audio_status == "delivered"
        # Exactly one TTS synthesis call made
        assert mock_synth.call_count == 1

        # Check DB persistence
        history = db.get_session_messages_full(session_id, db_path=temp_db)
        assistant_msgs = [m for m in history if m["role"] == "assistant"]
        assert len(assistant_msgs) == 1
        assert assistant_msgs[0]["audio_status"] == "delivered"
        assert assistant_msgs[0]["audio_url"].startswith("data:audio/mpeg;base64,")


# ==============================================================================
# TEST 2: Agent accurately answers "Can you reply in audio?" without false denial
# ==============================================================================
def test_agent_accurately_answers_voice_capability_inquiry(temp_db):
    """Agent is informed via runtime capabilities that speech is operational and affirms it."""
    session_id = "test-session-capability-check"

    # Verify that capability registry contains speech generation info
    cap_block = capability_registry.get_system_prompt_capabilities_block()
    assert "Speech Generation (Text-to-Speech): FULLY OPERATIONAL via ElevenLabs integration." in cap_block
    assert "NEVER deny your voice capabilities or say 'I cannot generate audio'" in cap_block

    with patch.object(TTSHandler, "is_configured", property(lambda self: True)), \
         patch.object(tts_handler, "synthesize_speech", return_value=(b"fake-audio", "audio/mpeg")), \
         patch("app.get_client") as mock_client_getter:

        mock_anthropic = MagicMock()
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Yes, I can send voice replies and speak with you! Athe, enikku voice aayi reply tharaan kazhiyum."
        mock_response.content = [text_block]
        mock_anthropic.messages.create.return_value = mock_response
        mock_client_getter.return_value = mock_anthropic

        resp = call_horus(
            session_id=session_id,
            user_message="Can you reply in audio?",
        )

        # Agent confirms capability warmly
        assert "cannot generate audio" not in str(resp).lower()
        assert "yes" in str(resp).lower() or "voice" in str(resp).lower()
        assert resp.audio_status == "delivered"
        assert resp.audio_url is not None


# ==============================================================================
# TEST 3: Text-only requests follow output preference (no audio generated)
# ==============================================================================
def test_text_only_request_follows_preference(temp_db):
    """A standard text inquiry without voice keywords produces text only."""
    session_id = "test-session-text-only"

    with patch.object(TTSHandler, "is_configured", property(lambda self: True)), \
         patch.object(tts_handler, "synthesize_speech") as mock_synth, \
         patch("app.get_client") as mock_client_getter:

        mock_anthropic = MagicMock()
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Octapus is located in Dubai, UAE. You can reach us at info@octapus.ae."
        mock_response.content = [text_block]
        mock_anthropic.messages.create.return_value = mock_response
        mock_client_getter.return_value = mock_anthropic

        resp = call_horus(
            session_id=session_id,
            user_message="Where is Octapus located and what is your email?",
        )

        assert "Dubai" in str(resp)
        assert resp.audio_url is None
        assert resp.audio_status == "none"
        # Zero TTS calls made for text-only inquiry
        assert mock_synth.call_count == 0

        # DB record reflects 'none'
        history = db.get_session_messages_full(session_id, db_path=temp_db)
        assistant_msgs = [m for m in history if m["role"] == "assistant"]
        assert len(assistant_msgs) == 1
        assert assistant_msgs[0]["audio_status"] == "none"
        assert assistant_msgs[0]["audio_url"] is None


# ==============================================================================
# TEST 4: Manglish and Malayalam speech formatting via clean_for_speech
# ==============================================================================
def test_manglish_speech_sanitization_and_intent():
    """Verify intent detection and text sanitization for Manglish and Malayalam."""
    # Intent recognition on variations (including authentic Malayalam slang triggers)
    assert detect_voice_intent("voice aayi parayu")
    assert detect_voice_intent("audio ayakk")
    assert detect_voice_intent("read this aloud please")
    assert detect_voice_intent("reply in voice")
    assert detect_voice_intent("Sheri, audio-il parayu")
    assert detect_voice_intent("ഓഡിയോ അയക്കൂ")
    assert detect_voice_intent("oru voice note tharu bro")
    assert detect_voice_intent("voice note ayakk machane")
    assert detect_voice_intent("audio-il parayoo aliya")
    assert detect_voice_intent("വോയ്സ് നോട്ട് അയക്ക്")

    # False triggers avoided
    assert not detect_voice_intent("What is the price of your web package?")
    assert not detect_voice_intent("Does your company provide support?")
    assert not detect_voice_intent("We should talk about our project next week")

    # clean_for_speech strips internal tags, markdown links, code, emojis, and accidental denials
    raw = (
        "[From Verified Management (971525919933)]: **Sheri**, sughamaano? 🔥 "
        "Visit [our website](https://octapus.ae). 🚀 "
        "```print('code')``` "
        "I cannot generate audio. We are ready to help."
    )
    cleaned = clean_for_speech(raw)
    assert "[From Verified Management" not in cleaned
    assert "**" not in cleaned
    assert "https://" not in cleaned
    assert "our website" in cleaned
    assert "```" not in cleaned
    assert "🔥" not in cleaned
    assert "🚀" not in cleaned
    assert "cannot generate audio" not in cleaned
    assert "Sheri, sughamaano?" in cleaned


# ==============================================================================
# TEST 5: ElevenLabs failure produces clear fallback and honest reporting
# ==============================================================================
def test_elevenlabs_failure_produces_clear_fallback(temp_db):
    """When ElevenLabs fails, provide full text response + brief failure note."""
    session_id = "test-session-tts-failure"

    # Simulate ElevenLabs synthesis failure (returning None after bounded retries)
    with patch.object(TTSHandler, "is_configured", property(lambda self: True)), \
         patch.object(tts_handler, "synthesize_speech", return_value=None), \
         patch("app.get_client") as mock_client_getter:

        mock_anthropic = MagicMock()
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Our working hours are Monday to Friday, 9:00 AM to 6:00 PM GST."
        mock_response.content = [text_block]
        mock_anthropic.messages.create.return_value = mock_response
        mock_client_getter.return_value = mock_anthropic

        resp = call_horus(
            session_id=session_id,
            user_message="reply in voice, what are your working hours?",
        )

        # Useful answer is preserved
        assert "9:00 AM to 6:00 PM" in str(resp)
        # Clear failure notice is appended
        assert "Voice reply could not be generated at the moment" in str(resp)
        # Audio URL is None
        assert resp.audio_url is None
        assert resp.audio_status == "generation_failed"

        # Database records failure status honestly
        history = db.get_session_messages_full(session_id, db_path=temp_db)
        assistant_msgs = [m for m in history if m["role"] == "assistant"]
        assert len(assistant_msgs) == 1
        assert assistant_msgs[0]["audio_status"] == "generation_failed"
        assert assistant_msgs[0]["audio_url"] is None


# ==============================================================================
# TEST 6: Exactly one audio response per request (prevent duplicate synthesis)
# ==============================================================================
def test_single_audio_orchestration_prevents_duplicate_synthesis(temp_db, test_client):
    """Web /chat endpoint triggers exactly one synthesis call per request."""
    with patch.object(TTSHandler, "is_configured", property(lambda self: True)), \
         patch.object(tts_handler, "synthesize_speech", return_value=(b"single-audio-bytes", "audio/mpeg")) as mock_synth, \
         patch("app.get_client") as mock_client_getter:

        mock_anthropic = MagicMock()
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Sheri, audio aayi parayaam."
        mock_response.content = [text_block]
        mock_anthropic.messages.create.return_value = mock_response
        mock_client_getter.return_value = mock_anthropic

        resp = test_client.post(
            "/chat",
            json={
                "message": "voice aayi parayu, how are you?",
                "session_id": "sess-single-audio",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["reply"] == "Sheri, audio aayi parayaam."
        assert data["audio_url"] is not None
        assert data["audio_url"].startswith("data:audio/mpeg;base64,")

        # Crucial check: Exactly ONE synthesis call occurred across the entire flow
        assert mock_synth.call_count == 1


# ==============================================================================
# TEST 7: Conversation history records transcript and actual audio status
# ==============================================================================
def test_conversation_history_records_transcript_and_status(temp_db):
    """Verify SQLite records transcript and status for multiple consecutive turns."""
    session_id = "test-session-multi-turn-history"

    with patch.object(TTSHandler, "is_configured", property(lambda self: True)), \
         patch.object(tts_handler, "synthesize_speech", return_value=(b"audio", "audio/mpeg")), \
         patch("app.get_client") as mock_client_getter:

        mock_anthropic = MagicMock()
        mock_client_getter.return_value = mock_anthropic

        # Turn 1: Text only
        mock_response_1 = MagicMock(stop_reason="end_turn", content=[MagicMock(type="text", text="Answer 1")])
        mock_anthropic.messages.create.return_value = mock_response_1
        call_horus(session_id=session_id, user_message="Question 1 (text)")

        # Turn 2: Voice request
        mock_response_2 = MagicMock(stop_reason="end_turn", content=[MagicMock(type="text", text="Answer 2")])
        mock_anthropic.messages.create.return_value = mock_response_2
        call_horus(session_id=session_id, user_message="Question 2, voice aayi parayu")

    history = db.get_session_messages_full(session_id, db_path=temp_db)
    assert len(history) == 4  # 2 user + 2 assistant messages

    # Verify Turn 1 assistant message
    turn1_assistant = history[1]
    assert turn1_assistant["role"] == "assistant"
    assert turn1_assistant["content"] == "Answer 1"
    assert turn1_assistant["audio_status"] == "none"
    assert turn1_assistant["audio_url"] is None

    # Verify Turn 2 assistant message
    turn2_assistant = history[3]
    assert turn2_assistant["role"] == "assistant"
    assert turn2_assistant["content"] == "Answer 2"
    assert turn2_assistant["audio_status"] == "delivered"
    assert turn2_assistant["audio_url"].startswith("data:audio/mpeg;base64,")
