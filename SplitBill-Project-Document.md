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
| Frontend | Next.js (React) — deployed on Vercel or AWS Amplify |
| Backend API | Next.js API routes or AWS Lambda (Python) |
| OCR | AWS Textract (managed, no setup needed) |
| Audio transcription | OpenAI Whisper API (recommended — fast, cheap, no infra) |
| LLM | Claude Opus via Anthropic API |
| Payments | Bunq API (bunq.me tabs \+ request-inquiry) |
| Database | DynamoDB (AWS) or simple JSON in S3 |
| File storage | AWS S3 (receipt images) |
| Hosting | Vercel (frontend) \+ AWS Lambda (AI pipeline) |

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

Recommended approach: Use the OpenAI Whisper API (`api.openai.com/v1/audio/transcriptions`). It accepts audio files up to 25MB and returns text in seconds. Cost is $0.006/minute, negligible for a hackathon. After transcription, send the text to Claude with a prompt like: "Evaluate this transcription for usability. Does it clearly describe who ordered which items? Rate: GOOD (clear assignments), PARTIAL (some assignments clear), or POOR (unusable). If POOR, suggest what the user should re-record." This quality check prevents bad data from entering the matching pipeline.

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
| 1 | Audio recording \+ Whisper API integration | **P0** | 2-3h | None — START FIRST |
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

splitbill/

├── app/                        \# Next.js app directory

│   ├── page.tsx                \# Landing/capture page

│   ├── s/\[id\]/page.tsx         \# Shared split view

│   └── api/                    \# API routes

│       ├── upload/             \# Receipt \+ audio upload

│       ├── process/            \# Trigger AI pipeline

│       ├── split/\[id\]/         \# Get/update split data

│       └── payment/            \# Bunq payment endpoints

├── lib/                        \# Shared utilities

│   ├── bunq.ts                 \# Bunq API wrapper

│   ├── ocr.ts                  \# Textract integration

│   ├── audio.ts                \# Whisper integration

│   ├── llm.ts                  \# Claude Opus prompts

│   └── db.ts                   \# DynamoDB/S3 data layer

├── components/                 \# React components

├── public/                     \# Static assets

├── .env.local                  \# API keys (NEVER commit)

├── .gitignore

└── README.md

### Environment variables needed (.env.local)

BUNQ\_API\_KEY=your\_sandbox\_key

BUNQ\_RSA\_PRIVATE\_KEY=your\_private\_key

AWS\_ACCESS\_KEY\_ID=your\_aws\_key

AWS\_SECRET\_ACCESS\_KEY=your\_aws\_secret

AWS\_REGION=eu-west-1

OPENAI\_API\_KEY=your\_openai\_key

ANTHROPIC\_API\_KEY=your\_anthropic\_key

S3\_BUCKET=splitbill-receipts

---

## 10\. Fallback plan

If any component fails during the hackathon, here are the fallbacks to keep the demo running:

- **Bunq API fails:** Generate iDEAL payment links or simple bank transfer instructions with pre-filled IBAN \+ amount. The core AI splitting still works.  
- **Textract fails:** Use a manual item entry form as fallback. Or use Claude's vision capability to read the receipt image directly (slower but no Textract dependency).  
- **Whisper fails:** Let users type who had what in a text field. The Claude prompt just gets text input instead of a transcript.  
- **Claude matching is wrong:** The website has a manual adjust feature. Users can reassign items and fix splits before sending payment links.

