# Recovery Copilot

**The AI teammate that never lets a failed payment become lost revenue.**

Built for the **Razorpay Buildathon 2026 — Track 3: AI Revenue Recovery**

| | |
|---|---|
| **Live App** | https://recovery-copilot.vercel.app |
| **API Docs (Swagger)** | https://recovery-copilot-b43o.onrender.com/docs |
| **Repository** | https://github.com/bonamukkala-bot/recovery-copilot |
| **Author** | Bonamukkala Charan Reddy |
| **Submission Deadline** | September 5, 2026 |

---

## The Problem

Every day, a meaningful slice of Razorpay payments fail — a bank declines a card, a UPI collect request times out, a network hiccup interrupts a transaction. For most businesses, that failure is a dead end. Nobody notices, nobody follows up, and the customer quietly forgets. That's not a technical failure — it's silent, invisible revenue loss happening at scale, every single day.

Recovery Copilot exists to close that gap: an autonomous agent that watches every payment failure the instant it happens, understands *why* it failed, and takes the exact right recovery action for that specific failure — safely, transparently, and with a human always able to step in before anything risky fires.

## What Makes This Different

Most "AI revenue recovery" submissions are a thin chatbot wrapper bolted onto a webhook. Recovery Copilot is built as a **governed, explainable pipeline**, not a black box:

- Every recovery action is logged with a plain-English reason *before* it ever fires
- High-value actions are held for human approval — the system cannot silently spend money or contact a customer above a threshold on its own
- A customer who opts out is **permanently and unconditionally suppressed** — no override path exists
- The system is hardened against the failure modes that break real production systems: duplicate webhook deliveries, race conditions from simultaneous customer actions, and an AI provider going down mid-flow — none of these can crash the pipeline or cause a bad outcome

## How It Works

1. **A payment fails.** Razorpay sends a webhook; the signature is verified with HMAC-SHA256 before anything else touches the payload.
2. **The system diagnoses why.** A fast rule-based classifier catches the common cases instantly (card declined, UPI expired, bank timeout). Anything ambiguous falls back to an LLM (Groq) — and if the LLM itself fails or times out, the event is flagged for human review rather than guessed at.
3. **A decision engine picks the right recovery channel.** A deterministic policy table — not another opaque AI call — maps failure type and amount to a channel: SMS, WhatsApp, or an escalated voice-call flag for high-value cases.
4. **High-value or risky actions wait for a human.** Anything above the approval threshold sits in a review queue until explicitly approved or rejected through an authenticated endpoint.
5. **Dispatch happens — with two independent final checks.** Right before anything is sent, the system re-checks the customer's opt-out status and how recently they were last contacted, regardless of what happened earlier in the pipeline.
6. **Every step is written to an append-only audit log.** Classification, decision, dispatch outcome, approvals, and rejections all land in a ledger that is never overwritten — a real answer to "why did the system do this," not a reconstruction.
7. **Recovery is confirmed, not assumed.** The system listens for `payment.captured` and matches it back to the original failure by order ID, marking the case genuinely recovered.

## Architecture

```
                          RAZORPAY WEBHOOK
                    (payment.failed / payment.captured)
                                 |
                                 v
                    FastAPI Webhook Endpoint
                 (HMAC-SHA256 signature verification)
                                 |
                    invalid -----+----- valid
                       |                  |
                  400 Rejected      Pydantic schema validation
                                          |
                                   Idempotency check
                              (payment_id + event_type,
                            app-level + DB unique constraint)
                                          |
                          duplicate ------+------ new event
                              |                       |
                        200 Ignored          Insert row (pending)
                                                       |
                                              Return 200 immediately
                                                       |
                                        Background task begins
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
    Failure Type    LLM Fallback (Groq)                         |
            |         openai/gpt-oss-120b                       |
            |               |                                  |
            |     classified --- LLM fails/unclear              |
            |          |               |                       |
            +----------+       flagged_for_review               |
                    |           (routed to human review)        |
                    v                   |                       |
         Decision Engine                |                       |
      (deterministic policy             |                       |
       table: type + amount             |                       |
          -> channel)                   |                       |
                    |                   |                       |
       opted out ---+--- not opted out  |                       |
            |               |           |                       |
       Suppressed    amount >= threshold?                       |
       (no action)     |         |      |                       |
                      yes        no     |                       |
                       |          |     |                       |
              pending_approval  Atomic race-guard claim         |
              (held for human   (pending -> processing)         |
               approve/reject)         |     |                  |
                       |         Dispatcher: |                  |
                  Approved       frequency-cap gate,             |
                  (authenticated)  suppression gate (final),     |
                       |            mock/real SMS-WhatsApp-Voice |
                       +----------------+     |                  |
                                        |     |                  |
                                        v     v                  v
                +-----------------------------------------------+
                |          SUPABASE  "events"  TABLE             |
                |     +  append-only  "decision_log"  ledger     |
                |     +  "promises"  (promise-to-pay tracking)   |
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

## Failure → Recovery Mapping

| Failure Type | Root Cause | Recovery Action |
|---|---|---|
| `card_declined` | Bank decline, risk rule, insufficient funds | SMS with alternate payment link |
| `upi_collect_expired` | Customer didn't approve UPI request in time | WhatsApp nudge with fresh collect request |
| `bank_timeout` | Transient network / gateway failure | Auto-retry + SMS confirmation |
| High-value + unclear cause | Amount above threshold, low classifier confidence | Flagged for voice-call escalation, human-approved |
| `flagged_for_review` | Rules and LLM both inconclusive, or LLM provider failure | Routed to manual human review, no automated action |

## Core Capabilities

**Trust & Safety**
- Authenticated approve/reject endpoints — a missing or invalid API key returns 401 before any business logic runs
- Per-customer contact frequency cap, configurable, to prevent spam and protect DND compliance
- Opt-out enforced as the *final* gate inside the dispatcher itself, re-checked independently of earlier decision-making

**Reliability**
- Idempotency enforced two layers deep: an application-level duplicate check plus a hard database unique constraint as a backstop
- Race-condition guard — an atomic `pending → processing → dispatched` state transition ensures a manual retry can never trigger a double-send, even under concurrent requests
- Graceful LLM fallback failure handling — a Groq timeout, rate limit, or auth failure never crashes the pipeline or produces a guessed classification; it's routed to human review instead

**Observability**
- Structured logging at every pipeline stage — classification path, decision reason, dispatch outcome — all greppable and traceable end-to-end
- LLM fallback-rate tracking, so the system's own "keeps cost and latency low" claim is measured, not assumed
- Append-only audit trail (`decision_log`) — a ledger that records what happened, never a row that gets silently rewritten

**Data Integrity**
- Pydantic validation on every incoming webhook payload, layered on top of (not instead of) signature verification — a malformed-but-signed payload fails predictably with a 422, not a crash
- Database-level uniqueness constraint backing the idempotency guarantee

**Architecture & Performance**
- Asynchronous webhook processing — the endpoint acknowledges Razorpay immediately, then classifies/decides/dispatches in the background, decoupling acknowledgment from processing so a slow downstream step can never cause Razorpay to time out and retry
- Deterministic decision engine — a transparent policy table, not another opaque model call, so every recovery choice is explainable on demand

**Outcome Tracking**
- Listens for `payment.captured` and matches it back to the original failure by order ID
- Promise-to-pay tracking — records a commitment window after a recovery contact and confirms whether the customer actually paid within it

**Honest Metrics**
- Recovery rate, contact rate, time-to-recovery, and cost-per-recovery computed from real event data
- Returns `null` (not a fake `0`) when there isn't enough data yet — no cherry-picked or padded numbers

## Tech Stack

| Layer | Choice |
|---|---|
| Backend | Python, FastAPI, deployed on Render |
| Frontend | React 19, Vite, TypeScript, Tailwind CSS 4, deployed on Vercel |
| Database | Supabase (Postgres) |
| Classification fallback | Groq (`openai/gpt-oss-120b`) |
| Payments | Razorpay test-mode APIs + webhooks |
| Messaging (current mode) | Simulated SMS / WhatsApp / voice dispatch, structured as a drop-in swap for live providers |
| Testing | pytest (pure-logic unit tests) + standalone signed-webhook simulation scripts |

## Deployed Links

- **Live Dashboard:** https://recovery-copilot.vercel.app
- **Backend API + Interactive Docs:** https://recovery-copilot-b43o.onrender.com/docs
- **Source Code:** https://github.com/bonamukkala-bot/recovery-copilot

## API Reference

Full interactive docs available live at `/docs` on the deployed backend.

| Method | Route | Description |
|---|---|---|
| `POST` | `/webhook/razorpay` | Receives and verifies Razorpay webhook events; returns immediately, processes asynchronously |
| `GET` | `/events` | Returns the latest events with full classification / decision / dispatch / outcome data |
| `POST` | `/events/{event_id}/approve` | **Authenticated.** Approves a held high-value action, triggers dispatch |
| `POST` | `/events/{event_id}/reject` | **Authenticated.** Rejects a held action; dispatch never fires |
| `POST` | `/opt-out` | Permanently suppresses a customer from future contact |
| `GET` | `/metrics` | Recovery rate, contact rate, avg time-to-recovery, cost-per-recovery, LLM fallback rate |
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
RECOVERY_ADMIN_API_KEY=
CONTACT_COOLDOWN_MINUTES=20
DISPATCH_MODE=mock
PROMISE_WINDOW_HOURS=24
MAX_VOICE_CALLS_PER_SESSION=20
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

The `backend/` folder includes both a formal pytest suite and a set of standalone webhook-simulation scripts:

- `backend/tests/test_classifier.py`, `backend/tests/test_decision_engine.py` — pytest unit tests for the pure, no-I/O classification and decision logic; run with `pytest backend/tests/`
- `test_webhook.py` / `test_webhook_upi.py` — basic failure classification, real signed payloads
- `test_broken_case.py` — a deliberately malformed event, proving the system fails predictably instead of crashing or guessing wrong
- `test_llm_case.py` — an ambiguous case that only the LLM fallback path can classify
- `test_webhook_captured.py` / `test_webhook_orphan_capture.py` / `test_webhook_outcome_fail.py` — outcome-tracking scenarios
- `test_webhook_reject.py`, `approve_event.py`, `reject_event.py` — the human-in-the-loop approval flow
- `generate_batch.py` — generates 55+ realistic synthetic failures across all failure types, satisfying the buildathon's "50+ synthetic failures" success criterion

## Success Criteria Checklist

Per the Track 3 brief:

- [x] 50+ synthetic failed-payment records processed end-to-end
- [x] Every money-related action is explainable, bounded, and gated
- [x] Authentication enforced on every payout-adjacent endpoint
- [x] Idempotency proven at both the application and database level
- [x] Race conditions from concurrent actions provably handled
- [x] AI provider failure degrades gracefully, never crashes or guesses
- [x] One deliberately-broken failure case demonstrated end-to-end, visible in the audit trail
- [x] Honest, reported metrics — no cherry-picked numbers
- [x] Clear opt-out and human-in-the-loop gates, demonstrated live

## Known Limitations / Roadmap

- SMS / WhatsApp / voice dispatch currently run in **mock mode** — the full decision and orchestration logic is real, but the outbound send is simulated with clearly-labeled log output shaped like a real provider response, since production credentials weren't available before the deadline. Swapping in live Meta Cloud API / SMS / Bolna AI + Sarvam credentials is a configuration change, not a rewrite.
- Voice agent (Bolna AI + Sarvam STT/TTS + GPT-4.1-mini) orchestration and budget-capping logic is implemented; the live voice call integration itself is pending real API access.
- Phone number normalization to a single E.164 format, and a webhook replay-window rejection (timestamp-based), are documented here as near-term hardening items rather than implemented yet.
- Phone numbers, payment amounts, and any future call transcripts for Indian customers are treated as personal data under the DPDP Act 2023: this project minimizes stored PII to what's needed for recovery, has a defined (currently manual) retention/deletion path, and enforces opt-out/DND at the dispatch layer as described above.

## Author

**Bonamukkala Charan Reddy**
Razorpay Buildathon 2026 — Track 3
