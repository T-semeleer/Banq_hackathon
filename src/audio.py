import os
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Literal

from openai import OpenAI
import anthropic

AudioQuality = Literal["GOOD", "PARTIAL", "POOR"]


@dataclass
class ValidationResult:
    quality: AudioQuality
    feedback: str
    suggestions: str | None = None


@dataclass
class AudioResult:
    transcript: str
    validation: ValidationResult


def transcribe(audio_path: Path | str) -> str:
    """Send audio file to OpenAI Whisper and return transcript text."""
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    with open(audio_path, "rb") as f:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language="en",
        )
    return response.text


def validate(transcript: str) -> ValidationResult:
    """Use Claude Haiku to check if transcript clearly describes who ordered what."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[
            {
                "role": "user",
                "content": (
                    "You are evaluating a voice memo for a restaurant bill splitting app.\n"
                    "The memo should clearly state who ordered which items from the receipt.\n\n"
                    f'Transcript: "{transcript}"\n\n'
                    "Rate the transcript:\n"
                    "- GOOD: clearly assigns items to people "
                    '(e.g. "I had the burger, Sarah had the salad")\n'
                    "- PARTIAL: some assignments are clear but others are missing or vague\n"
                    "- POOR: unusable — silent, inaudible, no order info, or completely off-topic\n\n"
                    "Reply ONLY with valid JSON, no extra text:\n"
                    '{"quality": "GOOD"|"PARTIAL"|"POOR", '
                    '"feedback": "one sentence explanation", '
                    '"suggestions": "what to re-record, or null if GOOD"}'
                ),
            }
        ],
    )

    data = json.loads(response.content[0].text)
    return ValidationResult(
        quality=data["quality"],
        feedback=data["feedback"],
        suggestions=data.get("suggestions"),
    )


def process_audio(audio_path: Path | str) -> AudioResult:
    """Full pipeline: transcribe audio then validate the transcript."""
    transcript = transcribe(audio_path)
    validation = validate(transcript)
    return AudioResult(transcript=transcript, validation=validation)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python audio.py <path-to-audio-file>")
        sys.exit(1)

    from dotenv import load_dotenv
    load_dotenv()

    result = process_audio(sys.argv[1])
    print(f"Transcript : {result.transcript}")
    print(f"Quality    : {result.validation.quality}")
    print(f"Feedback   : {result.validation.feedback}")
    if result.validation.suggestions:
        print(f"Suggestions: {result.validation.suggestions}")
