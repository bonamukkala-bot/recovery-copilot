# Recovery Copilot

**An autonomous agent that detects failing Razorpay payments and wins the revenue back.**

Built for the **Razorpay Buildathon 2026 — Track 3: AI Revenue Recovery**

| | |
|---|---|
| **Live demo** | recovery-copilot.vercel.app |
| **API docs** | recovery-copilot-b43o.onrender.com/docs |
| **Repository** | github.com/bonamukkala-bot/recovery-copilot |
| **Author** | Bonamukkala Charan Reddy |
| **Deadline** | September 5, 2026 |

---

## What It Does

Recovery Copilot watches Razorpay payments fail in real time, figures out *why* each one failed, and automatically tries to win the money back — via SMS, WhatsApp, or a flagged voice-call escalation — while logging an auditable trail of every decision it makes.

Most "AI revenue recovery" demos are a generic chatbot wrapper. This is a bounded, explainable, governed pipeline: every recovery action is logged with a plain-English reason *before* it fires, high-value actions require human approval, and any customer who opts out is permanently suppressed with no override.

## Problem It Solves

Merchants lose recoverable revenue because there is no system that:

1. Detects a payment failure the moment it happens
2. Correctly diagnoses *why* it failed
3. Runs the right recovery action for that specific failure type — not a generic "please retry" sent to everyone

## Architecture

```
                          RAZORPAY WEBHOOK
                    (payment.failed / payment.captured)
                                 |
                                 v
                    FastAPI Webhook Endpoint
                    (HMAC-SHA256 signature check)
                                 |
                    invalid -----+----- valid
                       |                  |
                  400 Rejected      Branch by event_type
                                          |
                    +---------------------+---------------------+
                    |                                           |
              payment.failed                           payment.captured
                    |                                           |
        Rule-Based Classifier                     Match pending event
         (error_code / keywords)                    by order_id
                    |                                           |
         matched ---+--- no match                  Mark outcome_status
            |               |                          = "recovered"
    Failure Type    LLM Fallback (Groq)                        |
            |         gpt-oss-120b                             |
            |               |                                  |
            |     classified --- still unclear                 |
            |          |               |                       |
            +----------+       failure_type: null               |
                    |           (flagged for review)            |
                    v                   |                       |
         Decision Engine                |                       |
      (deterministic policy             |                       |
       table: type + amount             |                       |
          -> channel)                   |                       |
                    |                   |                       |
       opted out ---+--- not opted out  |                       |
            |               |           |                       |
       Suppressed    amount >= 2000?    |                       |
       (no action)     |         |      |                       |
                      yes        no     |                       |
                       |          |     |                       |
              pending_approval  Dispatcher                      |
              (held for human   (simulated SMS /                |
               approve/reject)   WhatsApp / voice)               |
                       |          |     |                       |
                  Approved -------+     |                       |
                       |                |                       |
                       v                v                       v
                +-----------------------------------------------+
                |          SUPABASE  "events"  TABLE             |
                |   (full audit trail: classification, decision, |
                |    dispatch, approval, outcome — every field)  |
                +-----------------------------------------------+
                       |                          |
                  GET /events                GET /metrics
                       |                          |
                       +------------+-------------+
                                    |
                                    v
                     React Dashboard (Vercel)
              stat tiles + event ledger + audit-trail detail view
```

## Failure -> Recovery Mapping

| Failure Type | Root Cause | Recovery Action |
|---|---|---|
| `card_declined` | Bank decline, risk rule, insufficient funds | SMS with alternate payment link |
| `upi_collect_expired` | Customer didn't approve UPI request in time | WhatsApp nudge with fresh collect request |
| `bank_timeout` | Transient network / gateway failure | Auto-retry + SMS confirmation |
| High-value + unclear cause | Amount >= Rs. 2000, no confident classification | Flagged for voice-call escalation, human-approved |
| Unclassified, low value | Rules and LLM both inconclusive | Flagged for manual review, no automated action |

## Core Capabilities

- **Real-time webhook ingestion** — HMAC-SHA256 signature verification on every event
- **Hybrid classifier** — fast rule-based matching first; falls back to an LLM (Groq `openai/gpt-oss-120b`) only for ambiguous cases, keeping cost and latency low
- **Deterministic decision engine** — a plain policy table, not a black-box LLM call, maps `failure_type + amount -> channel`. Every decision writes a human-readable reason before any action fires
- **Human-in-the-loop gate** — any action above Rs. 2000 is held for explicit approval before dispatch
- **Hard opt-out** — a suppressed customer is permanently blocked from further contact, no override, no exceptions
- **Outcome tracking** — listens for `payment.captured` and matches it back to the original failure by `order_id`, marking it recovered
- **Full audit trail** — every event, decision, dispatch, approval, and outcome is stored and viewable per-row on the dashboard
- **Honest metrics** — recovery rate, contact rate, time-to-recovery, and cost-per-recovery computed from real data, with `null` returned (not a fake `0`) when there's nothing to average yet

## Tech Stack

| Layer | Choice |
|---|---|
| Backend | Python, FastAPI, deployed on Render |
| Frontend | React 19, Vite, TypeScript, Tailwind CSS 4, deployed on Vercel |
| Database | Supabase (Postgres) |
| Classification fallback | Groq (`openai/gpt-oss-120b`) |
| Payments | Razorpay test-mode APIs + webhooks |

## API Reference

Full interactive docs available at `/docs` (Swagger UI) on the live backend.

| Method | Route | Description |
|---|---|---|
| `POST` | `/webhook/razorpay` | Receives and verifies Razorpay webhook events |
| `GET` | `/events` | Returns the latest events with full classification / decision / dispatch / outcome data |
| `POST` | `/events/{event_id}/approve` | Approves a held high-value action, triggers dispatch |
| `POST` | `/events/{event_id}/reject` | Rejects a held action; dispatch never fires |
| `POST` | `/opt-out` | Permanently suppresses a customer from future contact |
| `GET` | `/metrics` | Recovery rate, contact rate, avg time-to-recovery, cost-per-recovery |
| `GET` | `/health` | Health check |

## Local Setup

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\Activate.ps1   # Windows PowerShell
pip install -r requirements.txt
```

Create `backend/.env`:

```
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
RAZORPAY_WEBHOOK_SECRET=
SUPABASE_URL=
SUPABASE_KEY=
GROQ_API_KEY=
ENVIRONMENT=development
```

Run:

```bash
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
```

Create `frontend/.env`:

```
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Run:

```bash
npm run dev
```

## Testing

The `backend/` folder includes a full test suite of standalone scripts — no test framework needed, each simulates a real signed Razorpay webhook:

- `test_webhook.py` / `test_webhook_upi.py` — basic failure classification
- `test_broken_case.py` — a deliberately malformed event, proving the system fails gracefully instead of crashing or guessing wrong
- `test_llm_case.py` — an ambiguous case that only the LLM fallback can classify
- `test_webhook_captured.py` / `test_webhook_orphan_capture.py` / `test_webhook_outcome_fail.py` — outcome-tracking scenarios
- `test_webhook_reject.py`, `approve_event.py`, `reject_event.py` — HITL approval flow
- `generate_batch.py` — generates 55+ realistic synthetic failures across all failure types, satisfying the buildathon's "50+ synthetic failures" success criterion

## Success Criteria Checklist

Per the Track 3 brief:

- [x] 50+ synthetic failed-payment records processed end-to-end
- [x] Every money-related action is explainable, bounded, and gated
- [x] One failure case shown handled gracefully, audit trail visible
- [x] Honest, reported metrics — no cherry-picked numbers
- [x] Clear opt-out and human-in-the-loop gates, demonstrated live

## Known Limitations / Roadmap

- SMS / WhatsApp / voice dispatch is currently **simulated** — provider-shaped responses (status, message, reference ID) that are a drop-in swap for Meta Cloud API / Twilio / Bolna AI once live credentials are available
- Voice agent (Bolna AI + Sarvam STT/TTS) not yet implemented
- Live Razorpay account pending bank verification — all testing done against Razorpay's documented webhook payload shapes in test mode

## Author

**Bonamukkala Charan Reddy**
Razorpay Buildathon 2026 — Track 3
