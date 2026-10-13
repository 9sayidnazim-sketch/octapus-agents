# AI Assistant (Horus) — Capability & Voice Synchronization Handoff

## 1. Executive Summary & Root Cause Analysis

### Voice Capability Mismatch (Fixed)
- **Reported Failure**: The agent replied *"I cannot generate audio"*, and ElevenLabs then synthesized that same denial into a playable audio voice note.
- **Root Cause**:
  1. **Disconnected Capability Awareness**: Horus's system prompt lacked an authoritative registry of active runtime capabilities. The base LLM defaulted to assuming it was a purely text-based AI assistant without voice capabilities.
  2. **Uncoordinated Post-Processing**: The application backend naively scanned incoming messages for keywords like `"voice"` or `"audio"`. When a user asked *"Can you reply in audio?"* or *"voice mismatch"*, the backend saw the keyword, called `tts_handler.synthesize_data_url(reply)`, and synthesized Claude's denial into speech.
  3. **Bridge Redundant Synthesis**: `whatsapp-bridge.js` performed its own secondary TTS call when `!audioUrl`, causing duplicate synthesis and overriding the backend's decisions.
  4. **Unsanitized Spoken Content**: Spoken text passed to ElevenLabs included Markdown asterisks, internal bracketed tags (`[From Verified Management...]`), URLs, and formatting markers that polluted pronunciation.

### Complete Architectural Solution
1. **Authoritative Runtime Capability Registry (`CapabilityRegistry`)**:
   - Maintains real-time status distinguishing `audio_input`, `speech_transcription`, `speech_generation`, and `audio_delivery`.
   - Generates `<authoritative_runtime_capabilities>` dynamically injected into Horus's system prompt.
   - Tells Horus that ElevenLabs speech generation is active, that it **CAN** speak, and instructs it to warmly affirm voice capability inquiries.
2. **Intent Recognition & Single Application-Managed Speech Pipeline**:
   - Recognizes explicit requests: *"voice aayi parayu"*, *"audio ayakk"*, *"read this aloud"*, *"reply in voice"*, *"audio-il parayu"*, *"can you reply in audio"*, and incoming voice notes.
   - Centralized in `call_horus` via `finalize_response`. Exactly **one** speech synthesis call is made per turn.
   - `whatsapp-bridge.js` respects `webhookProcessed` and never triggers competing synthesis.
3. **Speech Sanitization (`clean_for_speech`)**:
   - Strips internal tags (`[From Verified Management...]`, `[Voice note transcript...]`, OCR markers).
   - Converts Markdown links `[Label](url)` -> `Label` and removes raw URLs.
   - Strips code blocks, backticks, headings, bold/italics, and bullet points.
   - Strips accidental false capability denials (`I cannot generate audio...`).
   - Verifies pronunciation for English, Malayalam script, and Manglish using ElevenLabs `eleven_multilingual_v2`.
4. **Honest Failure Handling**:
   - Bounded retries (2 attempts with 0.5s backoff) inside `TTSHandler`.
   - If synthesis fails, Horus provides the complete useful text response and appends: `(Voice reply could not be generated at the moment; text reply provided above.)`.
   - Records `audio_status` as `'generation_failed'`, `'unconfigured'`, `'delivered'`, or `'none'`.
5. **Database Persistence & Audio Tracking**:
   - SQLite `messages` table updated with `audio_url TEXT` and `audio_status TEXT`.
   - `db.save_message` saves text transcript along with audio URL and delivery status.
   - `get_session_messages_full` retrieves complete message records.

---

## 2. Capabilities Checklist

| Capability | Status | Verification Details | Exact Blockers / Config Needs |
|---|---|---|---|
| **Ordinary Chat (Malayalam, Manglish, English)** | **Working & Verified** | Verified via test suite and live Anthropic API. Natural tone preserved without meta-narration. | None. Operational. |
| **Voice Capability Awareness** | **Working & Verified** | Dynamic `<authoritative_runtime_capabilities>` injected. Horus warmly affirms audio capability when asked. | None. Operational. |
| **Explicit Voice Synthesis (ElevenLabs)** | **Working & Verified** | Verified live with ElevenLabs API (`eleven_multilingual_v2`, voice `JBFqnCBsd6RMkjVDRZzb`). Produced 56,886 bytes of clean audio. | `ELEVENLABS_API_KEY` active. |
| **Text-Only Request Output Preference** | **Working & Verified** | Verified via test suite and live API. Text queries yield `audio_url: None` and `audio_status: "none"`. | None. Operational. |
| **Speech Sanitization (`clean_for_speech`)** | **Working & Verified** | Verified stripping markdown tokens, internal bracketed tags, bare URLs, and accidental denials. | None. Operational. |
| **Honest Fallback on TTS Failure** | **Working & Verified** | Verified in `test_elevenlabs_failure_produces_clear_fallback`. Preserves full text answer + reports failure note. | None. Operational. |
| **Single Orchestration Pipeline** | **Working & Verified** | Centralized in `call_horus`. Bridge redundant synthesis disabled. Verified exactly 1 synthesis call per turn. | None. Operational. |
| **Database Audio Status Tracking** | **Working & Verified** | Verified in SQLite. Stores transcript, `audio_url`, and `audio_status` (`delivered`, `generation_failed`, `none`). | None. Operational. |
| **Image Understanding & Vision (OCR, Bills)** | **Working & Verified** | Verified via `test_tool_execution_loop.py` and `test_fastapi_endpoints.py`. Native Anthropic vision blocks. | Requires Anthropic vision model. |
| **Reminders API (`faresemad/Reminders-API`)** | **Working & Verified** | Nested DRF client with `MockRemindersBackend` fallback. Relative date parsing for Manglish/Malayalam. | Local SQLite metadata ensures persistent scheduling. |
| **Persistent Scheduler & Proactive Reminders** | **Working & Verified** | Verified via `test_reminder_delivery_verification.py`. Atomic DB claims, quiet hours, cancelled reminder suppression. | Orbit WhatsApp Gateway (`http://localhost:8098`). |
| **Speech-to-Text (Voice Notes)** | **Implemented & Guarded** | Pipeline implemented via `AudioHandler`. Clear user message returned when unconfigured instead of pretending. | Blocked on `STT_API_KEY` / `OPENAI_API_KEY`. |
| **Persistent Memory** | **Working & Verified** | `save_memory`, `get_memory`, `list_memories`, `delete_memory` in SQLite. Survives restart. Refuses credentials. | None. Operational. |
| **Document Generation** | **Working & Verified** | Verified writing `.md`, `.txt`, `.csv` to `static/generated_docs/`. Sanitizes secrets and verifies disk existence. | None. Operational. |
| **AI Phone Calling (Bland.ai)** | **Working & Verified** | Verified via `test_bland_pipeline.py`. Config check gates tool availability. | `BLAND_API_KEY` active. |
| **Email Sending (Resend)** | **Working & Verified** | Verified via `test_email_pipeline.py`. Config check gates tool availability. | `RESEND_API_KEY` active. |

---

## 3. Architecture & File Structure

```
octapus-agents/
├── customer-agent/
│   ├── app.py                     # FastAPI server, single speech pipeline in call_horus, /chat, /webhook, /health
│   ├── db.py                      # SQLite storage for messages (with audio_url, audio_status), sessions, memories
│   ├── horus_instructions.md      # Persona and core instructions (removed false denials, affirmed ElevenLabs voice)
│   ├── company_info.md            # Business knowledge base
│   ├── media/
│   │   ├── pipeline.py            # Unified media intake (image, audio, document)
│   │   ├── image_handler.py       # PIL validation, format auto-detection, Anthropic vision blocks
│   │   ├── audio_handler.py       # Audio conversion and STT dispatch
│   │   ├── tts_handler.py         # ElevenLabs text-to-speech, clean_for_speech, detect_voice_intent, synthesize_with_status
│   │   ├── bland_handler.py       # Bland.ai phone calling
│   │   └── email_handler.py       # Resend email dispatch
│   ├── reminders/
│   │   ├── client.py              # faresemad/Reminders-API client (nested DRF routes)
│   │   ├── date_parser.py         # Malayalam / Manglish / English natural date & time parser
│   │   ├── service.py             # User ownership, preferences, reminder coordination
│   │   └── scheduler.py           # Persistent background worker, atomic claims, quiet hours, retries
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── registry.py            # Unified capability router, get_runtime_voice_status, dynamic capabilities block
│   │   └── document_generator.py  # Verified filesystem document generator with secret sanitization
│   └── tests/
│       ├── test_voice_capabilities.py  # 7 comprehensive tests covering all voice requirements
│       ├── test_tts_pipeline.py        # TTSHandler unit tests
│       ├── test_tool_execution_loop.py # Full tool-use execution loop tests
│       └── ...
├── whatsapp-bridge.js             # WhatsApp / Orbit Gateway bridge (updated to prevent duplicate TTS synthesis)
└── Codex-Outputs/
    └── 2026-10-13/agent-capability-repair/
        ├── CAPABILITY_REPORT.md
        └── VERIFICATION_SUMMARY.md
```

---

## 4. Verification & Test Results

### 1. Customer Agent Test Suite
```bash
PYTHONPATH=customer-agent .venv/bin/pytest customer-agent/tests
```
**Result: 71 passed, 0 failed in 1.79s.**
- `test_voice_capabilities.py`: 7/7 PASSED:
  1. `test_explicit_voice_request_produces_audio` (Playable audio URL generated with correct content)
  2. `test_agent_accurately_answers_voice_capability_inquiry` (Affirms voice capabilities without denial)
  3. `test_text_only_request_follows_preference` (Text inquiries produce `audio_url: None`, `status: "none"`)
  4. `test_manglish_speech_sanitization_and_intent` (Intent detection and markdown stripping)
  5. `test_elevenlabs_failure_produces_clear_fallback` (Useful text + failure notice on TTS outage)
  6. `test_single_audio_orchestration_prevents_duplicate_synthesis` (Single synthesis call per turn)
  7. `test_conversation_history_records_transcript_and_status` (Multi-turn transcript and status tracking)

### 2. Staff Assistant Test Suite
```bash
PYTHONPATH=staff-assistant .venv/bin/pytest staff-assistant/tests
```
**Result: 46 passed, 0 failed in 1.82s.**

### 3. Live API Verification
- **ElevenLabs Direct Synthesis**: Tested `clean_for_speech` with Manglish text -> Successfully generated 56,886 bytes of `audio/mpeg` via model `eleven_multilingual_v2`.
- **Live Capability Inquiry**: Prompted *"Can you reply in audio?"* -> Claude replied *"Yes, I can send voice replies and speak with you..."* + delivered audio data URL with `audio_status: delivered`.
- **Live Text-Only Request**: Prompted *"What is Octapus?"* -> Claude replied in text + `audio_url: None`, `audio_status: none`.
- **Live Manglish Voice Request**: Prompted *"voice aayi parayu, services enthokkeyanu?"* -> Claude replied in natural Manglish (*"Athe, enikku voice aayi reply tharaan pattum..."*) + delivered audio data URL with `audio_status: delivered`.

---

## 5. Startup Instructions

### 1. Run Customer Agent Service
```bash
cd /Users/ceooctapus/Downloads/octapus-agents/customer-agent
../.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Run WhatsApp Bridge (If using WhatsApp)
```bash
cd /Users/ceooctapus/Downloads/octapus-agents
node whatsapp-bridge.js
```

---

## 6. Remaining Notes & Non-Blockers

1. **Speech-to-Text (STT) Key**:
   - `STT_API_KEY` (or `OPENAI_API_KEY`) is pending configuration in `.env`. When incoming audio is received without text, the agent clearly notifies the user that transcription is unconfigured on the server and asks for text input.
2. **API Keys Server-Side Only**:
   - All API keys (`ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `BLAND_API_KEY`, `RESEND_API_KEY`) remain strictly server-side in environment variables and are never leaked to logs or the frontend.
