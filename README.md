# Synera

A subscription workspace for freelancers who take work from anywhere (WhatsApp, email, a call) and want to be sure they get paid for it. Paste the brief and the agreed price, and Synera plans the build, splits the budget, gets a signed agreement and an advance from the client, verifies the delivery against every requirement, and keeps the handover locked until payment clears.

## The twelve problems and what handles each

| Freelancer problem | What Synera does |
|---|---|
| Payment delays | Review window, automatic late fee (default 2% a week, capped at 10%), escalating reminders (WhatsApp / email / copy), preview that auto-locks |
| Client refuses to pay | Advance before the freelancer submits; hosted preview stays watermarked and locks; source is released only on payment |
| Unpaid extra work | Free revision rounds are set in the agreement. A request beyond them needs a freelancer quote, which is added to the invoice and shown to the client before paying |
| Subjective disputes | Acceptance criteria are written first. The audit shows each one found in the code with file and line proof, and a per-requirement verdict for the client |
| Client ghosting | Silence past the review window counts as acceptance (clause 6). Final-notice generator and a sealed evidence pack |
| No leverage after delivery | Client reviews a hosted preview. Handover is tied to payment |
| Fake payment screenshots | Only gateway-signed payments count (HMAC verified server-side). Public payment-reference check |
| International fees and FX | Payout estimator (assumption-based). Real multi-currency payouts are roadmap |
| Chargebacks | Signed agreement, audit, receipts and timeline in one sealed evidence pack |
| No written agreement | A 10-clause agreement is generated from the brief, hashed (SHA-256) and signed by both sides |
| Recovering small amounts | Self-serve notice and evidence pack. Not legal advice |
| Platform limits and fees | Flat plan, no marketplace commission, clients never pay to use it |

## Product tour

- **Landing page** with the problem map, how it works, pricing and an honest "what is real" section.
- **Dashboard** (freelancer): earnings received, awaiting, in progress and overdue; six-month chart; a record of every project with price, received, outstanding, audit score and days-to-pay; client reliability; payout estimator; payment-reference check; CSV export (Pro).
- **Projects**: paste the brief, final price and terms. The model analyses the text and returns a contract, acceptance criteria, a budget split by what the money is spent on, and a phased build plan (tasks, hours, stack, risks, suggestions, questions to ask the client). After the audit, the plan ticks off passing checks and lists what to fix next.
- **Hosted preview**: upload the built site as a zip with `index.html` at the top. Synera unpacks it (static files only; server code and `.env` are never served) and serves it in an isolated, sandboxed frame with the unpaid watermark and the lock. The client sees it only after you submit.
- **Client portal**: signs the agreement, pays the advance, sees the verdict, requests changes or accepts and pays.
- **Invoices**: every project gets an invoice (itemised from the budget split, extras, late fee, payments with gateway references). Download as PDF, PNG image or print page. A QR code and link open a public verification page that confirms status and payments, and flags a copy that no longer matches the record. Freelancers set billing details (GSTIN and PAN optional; without a GSTIN the invoice says no GST is charged). Set `PUBLIC_URL` when deployed so the QR points at your domain.
- **Plan**: Starter (free, 2 active projects) and Pro (Rs 499 a month or Rs 4,790 a year, unlimited projects, final notice, evidence pack, CSV). Sandbox checkout.
- **Public folio**: every paid delivery is minted as a hash-chained card anyone can verify at `/verify/<hash>`.

## Run it locally

```bash
cd backend
pip install -r requirements.txt
```
Windows: `copy .env.example .env`  (Mac/Linux: `cp .env.example .env`), then open `.env` and set `GEMINI_API_KEY` (optional; the offline template and audit work without it).
```bash
uvicorn main:app --port 8000
```
Open http://localhost:8000 (a production build of the UI is included). For frontend development: `cd frontend && npm install && npm run dev` (http://localhost:5173, proxies to :8000). Rebuild with `npm run build`.

The AI status banner in Projects shows whether Gemini is connected and why not if it is offline. Models are tried in order, so a retired model name does not break the app.

## Deploy

**Docker** (any host):
```bash
docker build -t synera .
docker run -p 8000:8000 -v synera-data:/data -e GEMINI_API_KEY=... -e PUBLIC_URL=https://your.domain synera
```
**Render**: push the repo and use `render.yaml` (Blueprint). It mounts a persistent disk at `/data`.

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Enables AI scoping, planning and grounded audit. Create a key in Google AI Studio on a free-tier project |
| `GEMINI_MODEL` | Optional. Pin a model, otherwise the first available one is used |
| `PUBLIC_URL` | Public site URL. Used in reminder links and to restrict CORS |
| `DATA_DIR` | Where the JSON store and uploads live (mount a volume here) |
| `ENABLE_DEMO` | Set to `0` in production to remove the demo shortcuts (quick demo, expiry simulators, reset) |
| `GATEWAY_SECRET` | Optional signing secret for the sandbox gateway |

Before real customers: move from the JSON file to Postgres, put the sandbox gateway behind a licensed payment partner (Razorpay Route or a bank-escrow partner) for real fund holding, and add email verification.

## Accounts

Create real freelancer or client accounts on the login page, or use the demo logins (password `demo1234`): `freelancer@synera.demo` (Pro) and `client@synera.demo`. **Presenter mode** logs into both at once with a Freelancer / Client switch. A client sees only projects created for their email.

## Demo script (about 3 minutes)

1. Landing page, then **Try the live demo**, then **Presenter mode**.
2. Freelancer **Projects**: paste a brief, enter the final price, click **Analyse brief and build the plan**. Walk through the plan and the budget split.
3. Switch to **Client**: read and sign the agreement, pay the advance (UPI `success@razorpay`).
4. Switch back: **Use sample deliverable**, **Submit to client**.
5. Client: verdict with file and line proof, **Request changes** twice to show the quoted extra, then **Accept and pay**.
6. Freelancer **Dashboard**: earnings, project record. Click **Simulate review window ending** on another project to show the late fee, reminders and final notice, then the evidence pack.
7. **Plan** tab: upgrade to Pro through the sandbox checkout.

Sandbox test inputs: UPI `success@razorpay` / `failure@razorpay`; cards `4111 1111 1111 1111` (success) and `4000 0000 0000 0002` (decline).

## How it works

- **Grounded audit.** Each criterion carries a regex checked against the delivered zip, so file names and line numbers come from the scanner. Where a regex misses, Gemini may judge it but must quote a line verbatim; the server re-locates it and rejects evidence it cannot find. Secrets and `.env` files are flagged and withhold the handover share.
- **Budget split.** Design (15%), QA (10%) and handover (5%) are fixed. The remaining 70% is split across features by effort weight, in whole rupees that always sum to the price.
- **Payments.** Order, then checkout, then an HMAC-SHA256 signed confirmation, then server-side verification. Advance and final payments, extras and late fees all flow through it. Full card numbers are never stored.
- **Evidence pack.** Agreement, brief, terms, payments, audit evidence, reminders and timeline, sealed with a SHA-256 of the pack.
- **Proof hash.** `SHA-256(freelancer | project | score | receipt | timestamp | zip | prev_hash)` per freelancer chain.
- **Auth.** PBKDF2 passwords, bearer sessions, login throttling, role and ownership checks (404 for other people's projects).

## Honest limitations

- The audit is static analysis: it shows each requirement exists in the code, not that the app behaves correctly.
- Payments are a sandbox. Holding real client money needs a licensed partner; the app already separates order, signature and settlement so that swap is contained.
- The preview shows the client your front-end files, so keep server code and secrets out of the preview zip. The lock is a deterrent for a Synera-hosted preview. Someone holding the source can remove it, which is why the source is withheld until payment.
- Agreements and notices are templates, not legal advice. Deemed acceptance and late fees depend on the contract being enforceable where you live.
- Fee presets in the payout estimator are assumptions. Check your provider's rates.
- Storage is a JSON file with atomic writes: fine for a pilot, not for scale.

## Tests

Start the server, then run `python tests/api_suite_1.py` (63 checks: auth, ownership, cost split, audit, payments, folio) and `python tests/api_suite_2.py` (55 checks: agreement, advance, revisions and quotes, review window, reminders, evidence pack, payment check, subscription, dashboard). `tests/api_suite_3.py` covers the hosted preview (including path-traversal, token and sandbox checks), agreement integrity, titles and AI error messages. `tests/browser_e2e.py` drives the whole UI with Playwright (freelancer and client in separate browsers, advance, delivery, final payment, Pro upgrade).
