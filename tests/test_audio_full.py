"""
Comprehensive tests for src/audio.py.
Covers validate(), process_audio(), and error handling.
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

os.environ.setdefault("ANTHROPIC_API_KEY", "test-dummy-key")
os.environ.setdefault("OPENAI_API_KEY",    "test-dummy-key")

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from audio import AudioResult, ValidationResult, process_audio, validate  # noqa: E402


# ── helpers ───────────────────────────────────────────────────────────────────

def _mock_anthropic(quality: str, feedback: str, suggestions: str | None) -> MagicMock:
    payload = {"quality": quality, "feedback": feedback, "suggestions": suggestions}
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps(payload))]
    client = MagicMock()
    client.messages.create.return_value = msg
    return client


def _mock_openai(transcript: str) -> MagicMock:
    client = MagicMock()
    client.audio.transcriptions.create.return_value = MagicMock(text=transcript)
    return client


# ── validate ──────────────────────────────────────────────────────────────────

def test_validate_good_quality():
    mock = _mock_anthropic("GOOD", "Clear item assignments.", None)
    with patch("audio.anthropic.Anthropic", return_value=mock):
        result = validate("I had the burger, Sarah had the salad.")
    assert isinstance(result, ValidationResult)
    assert result.quality == "GOOD"
    assert result.feedback == "Clear item assignments."
    assert result.suggestions is None


def test_validate_partial_quality():
    mock = _mock_anthropic("PARTIAL", "Some assignments missing.", "Clarify who had dessert.")
    with patch("audio.anthropic.Anthropic", return_value=mock):
        result = validate("I had the main, not sure about the rest.")
    assert result.quality == "PARTIAL"
    assert result.suggestions == "Clarify who had dessert."


def test_validate_poor_quality():
    mock = _mock_anthropic("POOR", "No order information.", "Re-record describing who ordered what.")
    with patch("audio.anthropic.Anthropic", return_value=mock):
        result = validate("...")
    assert result.quality == "POOR"
    assert result.suggestions is not None


def test_validate_uses_haiku_model():
    mock = _mock_anthropic("GOOD", "Fine.", None)
    with patch("audio.anthropic.Anthropic", return_value=mock):
        validate("some transcript")
    call_kwargs = mock.messages.create.call_args[1]
    assert "haiku" in call_kwargs["model"].lower()


def test_validate_passes_transcript_in_prompt():
    mock = _mock_anthropic("GOOD", "Fine.", None)
    with patch("audio.anthropic.Anthropic", return_value=mock):
        validate("UNIQUE_MARKER_IN_TRANSCRIPT")
    content = mock.messages.create.call_args[1]["messages"][0]["content"]
    assert "UNIQUE_MARKER_IN_TRANSCRIPT" in content


def test_validate_invalid_json_raises():
    msg = MagicMock()
    msg.content = [MagicMock(text="not json")]
    client = MagicMock()
    client.messages.create.return_value = msg
    with patch("audio.anthropic.Anthropic", return_value=client):
        with pytest.raises(json.JSONDecodeError):
            validate("some transcript")


# ── process_audio ─────────────────────────────────────────────────────────────

def test_process_audio_returns_audio_result(tmp_path):
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"fake audio data")

    mock_oai = _mock_openai("I had the chicken, Bob had the pasta.")
    mock_anth = _mock_anthropic("GOOD", "Clear.", None)

    with patch("audio.OpenAI", return_value=mock_oai), \
         patch("audio.anthropic.Anthropic", return_value=mock_anth):
        result = process_audio(audio_file)

    assert isinstance(result, AudioResult)
    assert result.transcript == "I had the chicken, Bob had the pasta."
    assert result.validation.quality == "GOOD"


def test_process_audio_transcript_flows_to_validate(tmp_path):
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"x")

    mock_oai = _mock_openai("UNIQUE_TRANSCRIPT_42")
    mock_anth = _mock_anthropic("GOOD", "Fine.", None)

    with patch("audio.OpenAI", return_value=mock_oai), \
         patch("audio.anthropic.Anthropic", return_value=mock_anth):
        result = process_audio(audio_file)

    # The transcript from Whisper should be passed to validate()
    anth_content = mock_anth.messages.create.call_args[1]["messages"][0]["content"]
    assert "UNIQUE_TRANSCRIPT_42" in anth_content


def test_process_audio_accepts_string_path(tmp_path):
    audio_file = tmp_path / "test.mp3"
    audio_file.write_bytes(b"fake audio")

    mock_oai = _mock_openai("transcript text")
    mock_anth = _mock_anthropic("PARTIAL", "Some missing.", "Re-record.")

    with patch("audio.OpenAI", return_value=mock_oai), \
         patch("audio.anthropic.Anthropic", return_value=mock_anth):
        result = process_audio(str(audio_file))

    assert isinstance(result, AudioResult)


def test_process_audio_poor_quality_propagated(tmp_path):
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"x")

    mock_oai = _mock_openai("")
    mock_anth = _mock_anthropic("POOR", "Silent recording.", "Please re-record.")

    with patch("audio.OpenAI", return_value=mock_oai), \
         patch("audio.anthropic.Anthropic", return_value=mock_anth):
        result = process_audio(audio_file)

    assert result.validation.quality == "POOR"
    assert result.validation.suggestions is not None
