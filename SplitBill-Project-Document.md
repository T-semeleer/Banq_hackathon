# SPLITBILL — Bunq Receipt Splitting Application

**Architecture, Task Breakdown & Implementation Guide**

**Team:** Terrence (AI Engineer) | Adam (Full-Stack) | Pepijn (Engineering/OCR) | Noah (Business) **Timeline:** 12-Hour Hackathon Sprint **Date:** April 2026

---

## 1\. Project overview

SplitBill is a standalone web application that automates receipt splitting using AI. A user takes a photo of a receipt and records a voice memo describing who ordered what. The system extracts items and prices via OCR, transcribes the audio via Whisper, and uses Claude Opus to match items to people. It then generates individual bunq.me payment links and produces a shareable URL where everyone can see the split, view the receipt, and track payment status. No user accounts or login required.

### Core user flow

1. User pays a group bill at a restaurant  
2. Opens SplitBill website, takes a photo of the receipt  
3. Records a voice memo: "I had the burger, Sarah had the salad, Tom had pasta and a beer"  
4. AI processes both inputs, extracts items \+ prices, matches items to people  
5. User reviews the split on the website, adjusts if needed  
6. System creates individual bunq.me payment links for each person  
7. User shares the unique SplitBill URL in the group chat  
8. Friends open the link, pick their name, pay via bunq.me, status updates live

---

## 2\. System architecture

### Tech stack

| Layer | Technology |
| :---- | :---- |
| Frontend | Single-page HTML/JS — served by Flask (`src/templates/index.html`) |
| Backend API | Flask (`src/app.py`) — unified server on port 5000 |
| OCR | AWS Textract (`src/ocr.py`) — `AnalyzeExpense` via S3 |
| Audio transcription | OpenAI Whisper API (`src/audio.py`) + Claude Haiku quality check |
| LLM matching | Claude Sonnet (`src/matcher.py`) — OCR + transcript → split JSON |
| Payments | Bunq API (`src/bunq.py`) — bunq.me tabs + request-inquiry simulation |
| Reconciliation | Custom (`src/reconciler.py`) — matches incoming transactions to people |
| File storage | AWS S3 (receipt images) |
| Tikkie simulation | bunq sandbox (`scripts/simulate_tikkie_payment.py`) |

### Architecture layers

The system has four main layers that communicate via REST APIs:

#### Layer 1: Capture layer (frontend)

A simple mobile-first web page with two actions: (1) capture or upload a receipt photo, and (2) record a voice memo. Both files are uploaded to the backend via a single API call. The frontend then shows a loading state while AI processes the inputs. Technology: Next.js with React, using the browser's MediaDevices API for camera and microphone access. The page is designed mobile-first since users will typically be at a restaurant.

#### Layer 2: AI processing pipeline (backend)

This is the brain of the system. It runs two parallel processing tracks that converge into a single LLM call:

- **OCR track:** Receipt image is sent to AWS Textract, which returns structured text with line items and prices. Textract is the recommended choice because it's a managed AWS service (no setup, no GPU), handles receipts well, and you already have AWS credentials.  
- **Audio track:** Voice recording is sent to OpenAI's Whisper API for transcription. We recommend the API over self-hosting because it's faster to integrate (one API call), cheaper for a hackathon, and requires zero infrastructure. The transcript is then sent to Claude for a quality check to verify it contains usable information about who ordered what. Needs agent to check output\!  
- **LLM fusion:** Both outputs (OCR text \+ audio transcript) are sent to Claude Opus in a single prompt. Claude matches receipt items to people mentioned in the audio, calculates each person's share, and outputs structured JSON. The prompt should instruct Claude to handle edge cases like shared items, tax/tip splitting, and items that can't be matched.

#### Layer 3: Payment layer (Bunq API)

For each person in the JSON output, the system creates a bunq.me tab via the Bunq API. The bunq.me tab endpoint (`POST /user/{userID}/monetary-account/{monetaryAccountID}/bunqme-tab`) creates a shareable payment link that anyone can pay via bunq, iDEAL, or SOFORT. Each tab includes the amount owed, a description of items, and a redirect URL back to the SplitBill page. The system stores the tab IDs and polls `bunqme-tab-result-response` to check payment status.

**IMPORTANT:** Bunq API requires RSA key signing for all requests. This is the most complex integration and should start immediately.

#### Layer 4: Shared website (frontend)

Each bill split gets a unique URL (e.g., `splitbill.app/s/abc123`). This page shows: the original receipt image, a list of all people and their items with prices, each person's bunq.me payment link, and real-time payment status (paid/pending). Users can adjust their share or add new people. The page requires no login. The receipt image is stored in S3 and served via CloudFront or directly.

---

## 3\. Bunq API integration (CRITICAL PATH)

This is the highest-priority and most complex part of the project. Bunq's API requires multiple setup steps before you can make any calls. **Start this FIRST.**

### Setup steps

1. **Get API key:** Create a sandbox API key via the Bunq developer portal or the app. Use sandbox environment (`public-api.sandbox.bunq.com`).  
2. **Generate RSA keypair:** Bunq requires RSA-signed requests. Generate a 2048-bit RSA key pair. Register your public key via `POST /v1/installation`.  
3. **Register device:** `POST /v1/device-server` with your API key and a description.  
4. **Create session:** `POST /v1/session-server` to get a session token. Use this token in all subsequent requests as `X-Bunq-Client-Authentication` header.  
5. **Get monetary account:** `GET /v1/user/{userId}/monetary-account` to find the account ID for receiving payments.  
6. **Create bunq.me tab:** `POST /v1/user/{userId}/monetary-account/{accountId}/bunqme-tab` with amount and description. The response gives you the shareable bunq.me link.

### Key endpoints

| Endpoint | Purpose | Method |
| :---- | :---- | :---- |
| `/bunqme-tab` | Create shareable payment link with amount \+ description | POST |
| `/bunqme-tab/{id}` | Get tab details including `bunqme-tab-share-url` | GET |
| `/bunqme-tab-result-response` | Check if payment has been made | GET |
| `/request-inquiry` | Alternative: direct payment request to email/phone/IBAN | POST |

**Recommendation:** Use bunq.me tabs as the primary payment method. They generate shareable links that anyone can pay via bunq, iDEAL, or SOFORT without needing a bunq account. Use `request-inquiry` as a fallback for known bunq users. The bunq.me link format supports adding `?amount={amount}&description={description}` as URL parameters for pre-filled payment details.

---

## 4\. AI pipeline specification

### OCR pipeline

Use AWS Textract's `AnalyzeExpense` API, which is specifically designed for receipts and invoices. It returns structured data with line items, prices, tax, total, and vendor information. The flow: (1) Upload receipt image to S3, (2) Call `textract.analyze_expense()` with the S3 reference, (3) Parse the response into a clean list of `{item_name, price}` objects. Textract handles rotated images, handwritten text, and various receipt formats. For the hackathon, the synchronous API (`analyze_expense`) is fine since receipts are single-page.

### Audio pipeline

**Implemented.** Python/Flask service in `audio/` running on port 5050.

**Test page:** `http://localhost:5050/audio-test` — record audio in-browser, send to Whisper, edit the transcript manually.

**Routes:**
- `GET /audio-test` — recording UI (MediaRecorder API, start/stop, audio preview)
- `POST /api/transcribe` — receives multipart audio blob, calls `whisper-1`, returns `{ transcript: "..." }`

**Key implementation details:**
- Browser records as `audio/webm;codecs=opus`; backend strips the codec suffix before sending to Whisper (OpenAI rejects codec-qualified MIME types)
- File passed to Whisper as a named tuple `("recording.webm", file, "audio/webm")` so the SDK sets the correct Content-Type
- Empty recordings are rejected with a 400 before hitting the API
- Max upload size: 25 MB (Whisper limit)
- Config: `audio/.env` with `OPENAI_API_KEY` (see `audio/.env.example`)

**Run locally:**
```bash
cd audio && python3 app.py
```

**Built:** After transcription, the text is validated by Claude Haiku (`src/audio.py validate()`) — rated GOOD / PARTIAL / POOR. The quality check is wired into the unified app via `src/app.py /api/transcribe`. See `docs/audio-pipeline.md` for full API docs.

### LLM matching prompt

The core Claude Opus prompt should take two inputs and produce one structured output:

- **Input 1 (OCR):** List of receipt line items with prices extracted from Textract.  
- **Input 2 (Audio):** Transcript of voice recording describing who ordered what.  
- **Output:** JSON array of person objects, each containing: `name` (string), `items` (array of `{name, price}`), `subtotal` (number), `share_of_tax` (number), `share_of_tip` (number), `total_owed` (number).

The prompt must instruct Claude to: (1) handle shared items by splitting cost equally among sharers, (2) distribute tax proportionally based on subtotal, (3) distribute tip proportionally or as specified in audio, (4) flag items it can't confidently match, (5) include unmatched items in a separate "unassigned" category for manual review.

---

## 5\. Data model

Each bill split is stored as a single JSON document in DynamoDB (or S3 for simplicity). The document ID is the unique URL slug (e.g., "abc123").

{

  "id": "abc123",

  "created\_at": "2026-04-24T12:00:00Z",

  "receipt\_image\_url": "s3://splitbill-receipts/abc123.jpg",

  "receipt\_items": \[

    { "name": "Grilled Chicken", "price": 14.50 },

    { "name": "Caesar Salad", "price": 11.00 }

  \],

  "audio\_transcript": "I had the chicken, Sarah had the salad...",

  "people": \[

    {

      "name": "You",

      "items": \[{ "name": "Grilled Chicken", "price": 14.50 }\],

      "subtotal": 14.50,

      "tax\_share": 1.31,

      "tip\_share": 2.18,

      "total\_owed": 17.99,

      "bunqme\_url": "https://bunq.me/splitbill/...",

      "payment\_status": "pending"

    }

  \],

  "total": 25.50,

  "tax": 2.30,

  "tip": 3.83,

  "status": "review"

}

---

## 6\. Task breakdown by team member

12-hour sprint. Tasks are ordered by priority and dependency. The Bunq integration is the critical path and must start immediately because it has the most unknowns and setup overhead.

### Terrence (AI Engineer — Lead)

| \# | Task | Priority | Hours | Dependencies |
| :---- | :---- | :---- | :---- | :---- |
| 1 | Bunq API setup \+ authentication | **P0 — CRITICAL** | 3-4h | None — START FIRST |
| 2 | Create bunq.me tab endpoint | **P0** | 2h | Task 1 |
| 3 | Payment status polling | P1 | 1-2h | Task 2 |
| 4 | Claude Opus prompt engineering | P1 | 2h | OCR \+ Audio ready |
| 5 | Integration testing end-to-end | P1 | 1-2h | All tasks |

*Terrence owns the Bunq integration since it's the hardest piece with the most unknowns (RSA signing, sandbox quirks, API rate limits). He also writes the core Claude prompt since he understands AI best.*

### Adam (Full-Stack Developer)

| \# | Task | Priority | Hours | Dependencies |
| :---- | :---- | :---- | :---- | :---- |
| 1 | Audio recording \+ Whisper API integration | **P0 ✅ DONE** | 2-3h | — |
| 2 | Audio quality check with Claude | P1 | 1h | Task 1 |
| 3 | Backend API routes (upload, process, status) | **P0** | 2-3h | None |
| 4 | Shared website page (split view, receipt, status) | P1 | 2-3h | Backend APIs |
| 5 | Adjust shares / add people feature | P2 | 1-2h | Task 4 |

*Adam handles the full audio pipeline (recording UI \+ Whisper \+ quality check) and builds the backend API layer \+ shared website. He can work in parallel with Terrence and Pepijn from the start.*

### Pepijn (Engineering / OCR)

| \# | Task | Priority | Hours | Dependencies |
| :---- | :---- | :---- | :---- | :---- |
| 1 | AWS Textract OCR integration | **P0** | 3-4h | AWS credentials |
| 2 | Receipt parsing \+ item extraction logic | **P0** | 2h | Task 1 |
| 3 | S3 image upload \+ storage | P1 | 1h | AWS credentials |
| 4 | Receipt image display on website | P2 | 1-2h | Task 3 \+ frontend |
| 5 | Testing with real receipts | P1 | 1-2h | Task 2 |

*Pepijn focuses entirely on the OCR pipeline. AWS Textract is a managed service so setup is straightforward, but parsing receipt data into clean item/price pairs requires careful work. He should test with multiple receipt formats early.*

### Noah (Business / Support)

| \# | Task | Priority | Hours | Dependencies |
| :---- | :---- | :---- | :---- | :---- |
| 1 | Capture page UI (photo \+ audio buttons) | **P0** | 3-4h | None — START FIRST |
| 2 | Landing page / homepage | P2 | 1-2h | None |
| 3 | Collect test receipts \+ audio samples | **P0** | Ongoing | None |
| 4 | Pitch deck / demo preparation | P1 | 2h | Working MVP |
| 5 | README \+ GitHub documentation | P1 | 1h | Architecture finalized |

*Noah builds the initial capture UI (the first screen users see), manages test data collection, and prepares the business side. The capture page can be a simple HTML/React page with two buttons — he doesn't need deep React knowledge for this. He should coordinate with Adam on UI consistency.*

---

## 7\. Priority matrix and critical considerations

### What to tackle first (in order)

1. **Bunq API auth \+ sandbox setup (Terrence):** This is the single biggest risk. RSA signing, sandbox registration, and session management can take hours to get right. If this doesn't work, the whole payment flow fails. Start immediately and don't context-switch until authentication works.  
2. **OCR pipeline (Pepijn):** Second priority. Without receipt data, there's nothing to split. AWS Textract is a managed service so it should be faster to set up than Bunq, but parsing receipt output into clean data is non-trivial.  
3. **Audio pipeline (Adam):** Third priority. The Whisper API is simple to call, but the quality check and transcript parsing add complexity. Adam can also build backend routes in parallel.  
4. **Frontend capture page (Noah):** Start simultaneously. Even a basic HTML form with file upload buttons is enough to unblock testing.

### Things to keep in mind

- **Bunq sandbox has quirks:** The sandbox auto-accepts payments under €500. Use `sugardaddy@bunq.com` as a test counterparty. Don't assume production behavior matches sandbox.  
- **Receipt quality varies wildly:** Crumpled receipts, poor lighting, handwritten items. Test with bad photos early. Have a fallback for manual item entry.  
- **Audio descriptions are messy:** People say "I had the, uh, the chicken thing" not "I ordered the Grilled Chicken at €14.50". The Claude prompt needs to handle fuzzy matching between audio descriptions and receipt item names.  
- **Tax and tip splitting:** European receipts often include BTW (VAT) built into item prices. The system needs to handle both tax-inclusive and tax-exclusive receipts. Tip splitting should be proportional by default.  
- **Mobile-first:** Users will be at a restaurant on their phone. Camera/microphone access requires HTTPS. Test on real phones, not just desktop browsers.  
- **CORS and API keys:** Never expose Bunq API keys, AWS credentials, or Anthropic API keys in frontend code. All sensitive API calls go through your backend.  
- **MVP mindset:** In 12 hours, cut scope aggressively. If Bunq integration is too complex, fall back to generating generic payment request links or iDEAL links. If Textract is slow, start with a hardcoded receipt and demo the flow end-to-end.

---

## 8\. 12-hour sprint timeline

| Time | Terrence | Adam | Pepijn | Noah |
| :---- | :---- | :---- | :---- | :---- |
| Hour 0-1 | Bunq API docs \+ RSA key setup | Project scaffold (Next.js) | AWS Textract setup | Capture page UI |
| Hour 1-3 | Bunq auth: installation \+ device \+ session | Audio recording UI \+ Whisper API | OCR pipeline: image to items | Capture page \+ test receipts |
| Hour 3-5 | Bunq.me tab creation \+ testing | Backend API routes | Receipt parsing \+ edge cases | Collect more test data |
| Hour 5-7 | Payment status polling | Claude prompt for item matching | S3 upload \+ image serving | Landing page |
| Hour 7-9 | Claude matching prompt | Shared website page | Receipt display on site | Help with frontend |
| Hour 9-11 | End-to-end integration | Adjust shares feature | Testing \+ bug fixes | Pitch deck prep |
| Hour 11-12 | Bug fixes \+ demo prep | Polish \+ bug fixes | Final testing | README \+ demo |

---

## 9\. GitHub repository structure

```
Banq_hackathon/
├── src/                            # Core application code
│   ├── app.py                      # Unified Flask server (port 5000) — all routes
│   ├── matcher.py                  # Claude Sonnet bill splitting (OCR + transcript → JSON)
│   ├── reconciler.py               # Payment reconciliation + footnote JSON
│   ├── bunq.py                     # Bunq.me payment link creation
│   ├── ocr.py                      # AWS Textract receipt OCR
│   ├── audio.py                    # Whisper transcription + Claude Haiku validation
│   └── templates/
│       └── index.html              # Single-page UI (record, split, pay, track)
│
├── scripts/
│   └── simulate_tikkie_payment.py  # CLI: simulate Tikkie repayment in bunq sandbox
│
├── tests/
│   ├── test_ocr_core.py            # OCR parse logic (24 tests, no AWS needed)
│   ├── test_matcher_full.py        # Matcher parsing + Claude prompt (20 tests)
│   ├── test_bunq_functions.py      # inject_links + create_payment_links (14 tests)
│   ├── test_audio_full.py          # validate() + process_audio() (10 tests)
│   ├── test_reconciler.py          # Core reconciler (10 tests)
│   ├── test_reconciler_edge.py     # Edge cases: outgoing txns, large splits (20 tests)
│   ├── test_app_routes.py          # All Flask routes (28 tests)
│   ├── test_simulate.py            # Simulate script (14 tests)
│   ├── test_merge.py               # End-to-end pipeline integration (8 tests)
│   └── test_ocr.py                 # Integration test runner (real receipts, needs AWS)
│
├── docs/
│   ├── audio-pipeline.md           # Audio API reference
│   ├── ocr-pipeline.md             # OCR API reference
│   ├── matcher.md                  # Matcher API reference
│   ├── reconciler.md               # Reconciler API reference
│   ├── app.md                      # Flask route reference
│   ├── bunq-payments.md            # Bunq payment link API reference
│   └── simulate-tikkie.md          # Tikkie simulation CLI reference
│
├── audio/                          # Standalone audio test service (port 5050)
│   └── app.py                      # Original Flask audio-test page
│
├── ocrstuf/                        # Standalone OCR Streamlit app (separate service)
│
├── hackathon_toolkit-main/         # Bunq API Python toolkit + tutorial scripts
│
├── last_split.json                 # Latest split result (written by /api/split)
├── CLAUDE.md                       # AI assistant instructions
└── SplitBill-Project-Document.md  # This file
```

**Run the unified app:**
```bash
python src/app.py    # → http://localhost:5000
```

**Run all tests:**
```bash
python -m pytest tests/    # 156 tests, all pass
```

### Environment variables

| Service | File | Variables |
| :---- | :---- | :---- |
| Audio (Flask) | `audio/.env` | `OPENAI_API_KEY` |
| Future frontend | `.env.local` | `BUNQ_API_KEY`, `BUNQ_RSA_PRIVATE_KEY`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `ANTHROPIC_API_KEY`, `S3_BUCKET` |

Never commit `.env` or `.env.local` — both are in `.gitignore`.

---

## 10\. Fallback plan

If any component fails during the hackathon, here are the fallbacks to keep the demo running:

- **Bunq API fails:** Generate iDEAL payment links or simple bank transfer instructions with pre-filled IBAN \+ amount. The core AI splitting still works.  
- **Textract fails:** Use a manual item entry form as fallback. Or use Claude's vision capability to read the receipt image directly (slower but no Textract dependency).  
- **Whisper fails:** Let users type who had what in a text field. The Claude prompt just gets text input instead of a transcript.  
- **Claude matching is wrong:** The website has a manual adjust feature. Users can reassign items and fix splits before sending payment links.

