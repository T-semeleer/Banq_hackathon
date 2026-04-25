# Banq — Intelligent Bill Splitting for bunq

AI-powered group expense splitting built on the bunq banking API. Scan a receipt, record who ordered what, split the bill with Claude, send real payment requests, and get a monthly summary that reflects what you *actually* spent — not what temporarily passed through your account on behalf of others.

---

## How it works

1. **Scan** a receipt with your camera or upload an image → AWS Textract extracts line items
2. **Record** a voice memo describing who ordered what → AWS Transcribe + Claude matches speech to items
3. **Split** — Claude assigns items, distributes tax/tip proportionally, handles shared dishes
4. **Request** — generates real bunq.me payment links per person
5. **Reconcile** — detects incoming Tikkies in your bunq history automatically via `SPLIT|TXN` tags
6. **Summarize** — monthly overview shows true net personal spend per category, with reimbursements netted out

---

## Prerequisites

- Python 3.11+
- A **bunq sandbox account** and API key — [create one at bunq.com/en/developer](https://www.bunq.com/en/developer)
- An **Anthropic API key** — [console.anthropic.com](https://console.anthropic.com)
- An **OpenAI API key** (Whisper for voice transcription)
- **AWS credentials** with Textract + S3 access *(optional — OCR is disabled if absent, manual paste still works)*

---

## Setup

### 1. Clone & install dependencies

```bash
git clone https://github.com/T-semeleer/Banq_hackathon.git
cd Banq_hackathon

pip install flask anthropic openai python-dotenv boto3 requests cryptography
```

### 2. Configure environment variables

Create a `.env` file in the project root:

```env
# Required
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
BUNQ_API_KEY=sandbox_...

# Optional — enables receipt OCR (app works without it via manual paste)
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_SESSION_TOKEN=...         # only if using temporary STS credentials
AWS_DEFAULT_REGION=eu-west-1
S3_BUCKET=your-bucket-name
```

> **bunq API key**: In the bunq developer portal, create a sandbox app and copy the API key. The app will auto-create a bunq context (`bunq_context.json`) on first run.

### 3. Run

```bash
python src/app.py
```

Open [http://localhost:8080](http://localhost:8080)

---

## Demo mode

The app ships with a demo seeder that populates your bunq sandbox with realistic transactions (groceries, transport, restaurant, utilities) so you can explore the monthly summary without real bank data.

Click **"Setup Demo"** in the app, or call the endpoint directly:

```bash
curl -X POST http://localhost:8080/api/demo/setup
```

Then use **Load Summary** in Step 6 to see the categorized monthly overview.

---

## Project structure

```
src/
├── app.py              # Flask backend — all API routes
├── matcher.py          # Claude bill-splitting logic
├── summarizer.py       # Monthly expense netting (SPLIT|TXN parsing)
├── bunq_insights.py    # Tapix category API + sandbox overlay
├── reconciler.py       # Tikkie reconciliation against bunq history
├── bunq.py             # bunq.me payment link creation
├── ocr.py              # AWS Textract receipt OCR
├── audio.py            # AWS Transcribe voice transcription
├── demo_seeder.py      # Sandbox demo data seeder
├── category_store.py   # Local category assignment store
└── templates/
    └── index.html      # Frontend (vanilla JS, bunq dark UI)

hackathon_toolkit-main/ # bunq SDK / BunqClient wrapper
footnotes.json          # Persisted reconciliation data (auto-created)
```

---

## Key design: the `SPLIT|TXN` tag

When a payment request is created, the description embeds:

```
SPLIT|TXN{expense_id}|{person_name}|{amount}
```

When that Tikkie lands in your bunq account, `summarizer.py` detects this tag and automatically links the reimbursement to its originating expense — no manual reconciliation, no external database. The relationship travels with the money itself.

---

## Environment notes

- The app runs on port `8080` by default. Override with `PORT=5000 python src/app.py`
- `bunq_context.json` is auto-created on first run and stores your bunq session. Delete it to force a fresh session.
- `footnotes.json` persists reconciliation results across server restarts.
- AWS temporary credentials (STS/`ASIA` prefix) expire after a few hours — refresh them in `.env` as needed.

---

## Built with

| | |
|---|---|
| **bunq API** | Payments, account history, Tapix categorization, sandbox simulation |
| **Claude Sonnet 4.6** | Receipt-to-split AI reasoning |
| **AWS Textract** | Receipt OCR |
| **AWS Transcribe** | Voice-to-text |
| **Flask** | Python backend |
| **Vanilla JS** | Frontend, bunq dark-mode design language |
