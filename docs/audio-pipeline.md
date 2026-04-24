# Audio Pipeline — SplitBill

## Overview

The audio pipeline converts a voice memo (recorded at the restaurant) into a validated transcript that the LLM matching step can use to assign receipt items to people.

**Two-step flow:**
1. **Transcribe** — OpenAI Whisper converts the audio file to text
2. **Validate** — Claude Haiku checks whether the transcript is usable

---

## File

```
src/audio.py
```

---

## Dependencies

```bash
pip install openai anthropic python-dotenv
```

---

## Environment Variables

Add to `.env` (never commit this file):

```
OPENAI_API_KEY=sk-proj-...
ANTHROPIC_API_KEY=sk-ant-...
```

---

## Public API

### `transcribe(audio_path) -> str`

Sends an audio file to OpenAI Whisper and returns the raw transcript text.

| Parameter | Type | Description |
|---|---|---|
| `audio_path` | `Path \| str` | Path to audio file (MP3, MP4, M4A, WAV, WebM — max 25 MB) |

**Returns:** transcript string

---

### `validate(transcript) -> ValidationResult`

Sends the transcript to Claude Haiku to assess whether it clearly describes who ordered what.

| Parameter | Type | Description |
|---|---|---|
| `transcript` | `str` | Raw transcript text |

**Returns:** `ValidationResult`

```python
@dataclass
class ValidationResult:
    quality: Literal["GOOD", "PARTIAL", "POOR"]
    feedback: str         # one-sentence explanation
    suggestions: str | None  # what to re-record, None if GOOD
```

| Quality | Meaning |
|---|---|
| `GOOD` | Clearly assigns items to people — safe to pass to LLM matching |
| `PARTIAL` | Some assignments clear, others vague — proceed with caution |
| `POOR` | Unusable — prompt user to re-record |

---

### `process_audio(audio_path) -> AudioResult`

Runs the full pipeline (transcribe → validate) in one call.

**Returns:** `AudioResult`

```python
@dataclass
class AudioResult:
    transcript: str
    validation: ValidationResult
```

---

## CLI Usage (testing)

```bash
cd Banq_hackathon
python src/audio.py path/to/recording.mp3
```

Example output:

```
Transcript : I had the burger, Sarah had the caesar salad, and Tom got the pasta and a beer
Quality    : GOOD
Feedback   : Clearly assigns all items to named individuals
```

---

## Integration Points

### Backend API route (to be built by Adam)

```python
from src.audio import process_audio

# Inside the POST /api/upload handler:
result = process_audio(saved_audio_path)

if result.validation.quality == "POOR":
    return {"error": "re-record", "suggestions": result.validation.suggestions}

# Pass to LLM matching step
run_llm_matching(ocr_items, transcript=result.transcript)
```

### LLM matching (Terrence — Claude Opus prompt)

The `result.transcript` string feeds directly into the Claude Opus prompt alongside the OCR items. No further preprocessing needed for GOOD/PARTIAL quality.

---

## Fallback

If Whisper fails or the user has no microphone, the `validate()` function can be called directly with a manually typed description — the rest of the pipeline is identical.

```python
from src.audio import validate

result = validate("I had the chicken, Noah had the fries")
```

---

## Supported Audio Formats

| Format | Notes |
|---|---|
| MP3 | Default browser recording format on most mobile browsers |
| MP4 / M4A | iOS Safari default |
| WebM | Chrome/Firefox default via MediaRecorder API |
| WAV | Uncompressed, larger files |

Max file size: **25 MB** (Whisper API limit)

---

## Cost

| Step | Model | Cost |
|---|---|---|
| Transcription | Whisper (`whisper-1`) | ~$0.006 / minute |
| Validation | Claude Haiku | ~$0.0004 per call |

For a typical 30-second voice memo: **< $0.01 total**

---

## Status

| Component | Status |
|---|---|
| Whisper transcription | Done |
| Claude Haiku validation | Done |
| Backend API route integration | Pending (Adam) |
| Browser audio recording UI | Pending (Noah / Adam) |
| LLM matching integration | Pending (Terrence) |
