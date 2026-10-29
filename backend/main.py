"""Synera backend v2.

Accounts (freelancer / client), scope extraction (Gemini + deterministic fallback),
dynamic cost split, grounded spec audit with a client-facing delivery verdict,
DRM state router for the hosted preview, sandbox payment gateway and the
SHA-256 proof-of-work minter.
"""
import hashlib
import hmac
import html
import io
import json
import logging
import os
import re
import secrets
import shutil
import time
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # optional
    pass

log = logging.getLogger("synera")
logging.basicConfig(level=logging.INFO)

BASE = Path(__file__).parent
STORAGE = Path(os.getenv("DATA_DIR") or (BASE / "storage"))
STATIC_DIR = BASE / "static"
DEMO_CLIENT_DIR = BASE.parent / "client_app"
DATA_FILE = STORAGE / "data.json"
SAMPLE_ZIP = STORAGE / "sample_gym_site.zip"
PREVIEWS = STORAGE / "previews"
for d in (STORAGE, STATIC_DIR):
    d.mkdir(parents=True, exist_ok=True)

def _clean_key(v):
    v = (v or "").strip().strip("\"'").strip()
    return v


_RAW_KEY = _clean_key(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
KEY_IS_PLACEHOLDER = bool(_RAW_KEY) and (_RAW_KEY.lower() in ("your_key_here", "your_api_key", "your-key-here", "changeme", "xxx") or len(_RAW_KEY) < 20)
GEMINI_KEY = None if KEY_IS_PLACEHOLDER else (_RAW_KEY or None)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
ALLOW_MOCK_SETTLE = os.getenv("ALLOW_MOCK_SETTLE") == "1"
ENABLE_DEMO = os.getenv("ENABLE_DEMO", "1") != "0"  # set ENABLE_DEMO=0 in production to remove the demo shortcuts
SCHEMA = 3
SESSION_TTL = 7 * 24 * 3600
PUBLIC_URL = (os.getenv("PUBLIC_URL") or "").rstrip("/")

PLANS = {
    "free": {"name": "Starter", "price_month": 0, "price_year": 0, "max_active": 2, "features": [
        "2 active projects at a time", "AI scope, budget split and build plan", "Signed agreement with revision limits",
        "Spec audit with file and line proof", "Locked client preview and sandbox escrow checkout",
        "Earnings dashboard and project records", "Friendly and firm payment reminders"]},
    "pro": {"name": "Pro", "price_month": 499, "price_year": 4790, "max_active": None, "features": [
        "Unlimited active projects", "Final-notice generator", "Sealed evidence pack for disputes and chargebacks",
        "CSV export for accounts and GST", "Everything in Starter"]},
}

DEMO_PASSWORD = "demo1234"
DEMO_FREELANCER = {"id": "fr_demo", "email": "freelancer@synera.demo", "name": "Demo Freelancer", "role": "freelancer"}
DEMO_CLIENT = {"id": "cl_demo", "email": "client@synera.demo", "name": "IronPulse Fitness", "role": "client"}
DEMO_CHAT = (
    "Need a modern gym landing page with BMI calculator, dark mode, "
    "and WhatsApp lead button, budget ₹15,000"
)

# --------------------------------------------------------------------------
# Persistence (tiny JSON store: plenty for a hackathon demo)
# --------------------------------------------------------------------------
DB: dict = {"schema": SCHEMA, "users": {}, "sessions": {}, "projects": {}, "mints": {}, "orders": {}, "payments": {}}


def save() -> None:
    tmp = DATA_FILE.with_suffix(".tmp")  # write then rename so a crash never leaves a half-written file
    tmp.write_text(json.dumps(DB, indent=2))
    tmp.replace(DATA_FILE)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_pw(password: str, salt: Optional[str] = None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()
    return salt, h


def add_user(uid: str, email: str, name: str, role: str, password: str) -> dict:
    salt, h = hash_pw(password)
    u = {"id": uid, "email": email.lower(), "name": name, "role": role, "salt": salt, "pw": h, "created_at": now_iso(),
         "plan": "free", "plan_renews": 0, "billing": []}
    DB["users"][u["email"]] = u
    return u


def load() -> None:
    if DATA_FILE.exists():
        try:
            DB.update(json.loads(DATA_FILE.read_text()))
        except Exception:
            log.warning("could not read data.json, starting fresh")
    if DB.get("schema") != SCHEMA:  # older demo data: start clean
        for k in ("projects", "mints", "orders", "payments"):
            DB[k] = {}
        DB["schema"] = SCHEMA
    for k in ("users", "sessions", "projects", "mints", "orders", "payments"):
        DB.setdefault(k, {})
    for u in (DEMO_FREELANCER, DEMO_CLIENT):
        if u["email"] not in DB["users"]:
            add_user(u["id"], u["email"], u["name"], u["role"], DEMO_PASSWORD)
    for em in [e for e, u in DB["users"].items() if e.endswith("@prooflock.demo")]:  # accounts from before the rename
        if any(o["id"] == DB["users"][em]["id"] and oe != em for oe, o in DB["users"].items()):
            del DB["users"][em]
        else:
            DB["users"][em.replace("@prooflock.demo", "@synera.demo")] = DB["users"].pop(em)
            DB["users"][em.replace("@prooflock.demo", "@synera.demo")]["email"] = em.replace("@prooflock.demo", "@synera.demo")
    for p in DB["projects"].values():
        if p.get("client_email", "").endswith("@prooflock.demo"):
            p["client_email"] = p["client_email"].replace("@prooflock.demo", "@synera.demo")
    for sess in DB["sessions"].values():
        sess["email"] = sess["email"].replace("@prooflock.demo", "@synera.demo")
    demo = DB["users"][DEMO_FREELANCER["email"]]
    if demo.get("plan") != "pro" or demo.get("plan_renews", 0) < time.time() + 30 * 86400:
        demo["plan"], demo["plan_renews"] = "pro", time.time() + 365 * 86400  # demo account always shows Pro
    for u in DB["users"].values():
        u.setdefault("plan", "free"); u.setdefault("plan_renews", 0); u.setdefault("billing", [])
    save()


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------
class Milestone(BaseModel):
    title: str
    description: str
    amount_inr: int


class Criterion(BaseModel):
    id: str
    description: str
    check_type: str = Field(description="'regex' for code-checkable items, 'ai' for subjective ones")
    pattern: str = Field(description="Case-insensitive Python regex expected in the source; empty for 'ai'")
    file_types: list[str] = Field(description="File extensions to search, e.g. ['html','js','css']")
    feature: str = Field(description="Short name of the feature this criterion belongs to. Criteria of one feature share the name")
    effort_weight: int = Field(description="Relative effort of the whole feature from 1 (trivial) to 10 (large); same for all criteria of one feature")


class ContractDraft(BaseModel):
    title: str
    summary: str
    client_name: str
    stack_tags: list[str]
    total_inr: int
    milestones: list[Milestone]
    criteria: list[Criterion]


class AIVerdict(BaseModel):
    passed: bool
    file: str
    snippet: str = Field(description="ONE line copied verbatim from the file as evidence")
    reason: str


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    email: str = Field(max_length=120)
    password: str = Field(min_length=8, max_length=128)
    role: str


class LoginIn(BaseModel):
    email: str
    password: str


class ScopeIn(BaseModel):
    chat: str = Field(min_length=5, max_length=8000)
    client_email: str = DEMO_CLIENT["email"]
    grace_period_hours: int = Field(default=72, ge=0, le=24 * 60)
    force_fallback: bool = False
    price_inr: Optional[int] = Field(default=None, ge=500, le=10_000_000, description="Final price agreed with the client")
    advance_pct: int = Field(default=30, ge=0, le=70)
    revisions_included: int = Field(default=2, ge=0, le=10)
    review_days: int = Field(default=3, ge=1, le=30)
    late_fee_pct_per_week: int = Field(default=2, ge=0, le=5)
    delivery_days: int = Field(default=7, ge=1, le=180)


class DrmIn(BaseModel):
    state: str


class SettleIn(BaseModel):
    method: str = "upi_mock"


class OrderIn(BaseModel):
    kind: str = "final"


class QuoteIn(BaseModel):
    fee_inr: int = Field(ge=0, le=10_000_000)
    note: str = Field(default="", max_length=300)


class SubOrderIn(BaseModel):
    plan: str = "pro"
    billing: str = "monthly"


class ChangesIn(BaseModel):
    message: str = Field(min_length=3, max_length=1000)


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------
_attempts: dict = {}


def throttle(key: str) -> None:
    now = time.time()
    n, t0 = _attempts.get(key, (0, now))
    if now - t0 > 600:
        n, t0 = 0, now
    if n >= 8:
        raise HTTPException(429, "Too many attempts. Try again in a few minutes.")
    _attempts[key] = (n + 1, t0)


def effective_plan(u: dict) -> str:
    pl = u.get("plan", "free")
    return pl if pl != "free" and time.time() < u.get("plan_renews", 0) else "free"


def require_pro(u: dict, what: str) -> None:
    if effective_plan(u) != "pro":
        raise HTTPException(402, f"{what} is a Pro feature. Upgrade from the Plan tab.")


def public_user(u: dict) -> dict:
    return {"id": u["id"], "email": u["email"], "name": u["name"], "role": u["role"], "plan": effective_plan(u)}


def new_session(u: dict) -> dict:
    tok = secrets.token_urlsafe(32)
    DB["sessions"][tok] = {"email": u["email"], "created": time.time()}
    save()
    return {"token": tok, "user": public_user(u)}


def current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Please log in")
    tok = authorization[7:].strip()
    s = DB["sessions"].get(tok)
    if not s or time.time() - s["created"] > SESSION_TTL:
        DB["sessions"].pop(tok, None)
        raise HTTPException(401, "Session expired. Please log in again")
    u = DB["users"].get(s["email"])
    if not u:
        raise HTTPException(401, "Please log in")
    return u


# --------------------------------------------------------------------------
# Gemini helpers
# --------------------------------------------------------------------------
_client = None


def gemini():
    global _client
    if not GEMINI_KEY:
        return None
    if _client is None:
        try:
            from google import genai

            _client = genai.Client(api_key=GEMINI_KEY)
        except Exception as e:  # SDK missing or bad key
            log.warning("Gemini unavailable: %s", e)
            return None
    return _client


# Model names change quickly (gemini-2.5-flash was retired in Oct 2026), so try the configured model
# first, then current free-tier flash models, and remember whichever one answers.
MODEL_PREFS = [m for m in [os.getenv("GEMINI_MODEL")] if m] + [
    "gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-flash",
]
_working: Optional[str] = None
_GONE = ("404", "not found", "not_found", "no longer available", "is not supported", "unknown model")


def short_err(e: Exception) -> str:
    """Turn a raw Gemini error into one plain sentence that says what to do."""
    raw = " ".join(str(e).split())
    low = raw.lower()
    if "api key not valid" in low or "api_key_invalid" in low or "invalid api key" in low:
        return "Gemini rejected the API key. Check GEMINI_API_KEY in backend/.env (no quotes or spaces), or create a new key in Google AI Studio."
    if "resource_exhausted" in low or "credits are depleted" in low or "quota" in low or "429" in low[:40]:
        return "Gemini quota or credits are used up. Use a key from a free-tier project in Google AI Studio, or try again later."
    if "permission_denied" in low or "403" in low[:40]:
        return "This key is not allowed to use the Gemini API. Create a new key in Google AI Studio."
    if "timed out" in low or "timeout" in low or "connect" in low:
        return "Could not reach Gemini. Check the internet connection."
    log.info("Gemini error: %s", raw[:400])
    return "Gemini returned an error: " + scrub(raw)[:140]


def generate(c, *, contents, config=None):
    """generate_content with automatic fallback across model names (only for 'model gone' errors)."""
    global _working
    order = ([_working] if _working else []) + [m for m in MODEL_PREFS if m != _working]
    last: Optional[Exception] = None
    for m in order:
        try:
            r = c.models.generate_content(model=m, contents=contents, config=config)
            _working = m
            return r
        except Exception as e:
            last = e
            if any(k in str(e).lower() for k in _GONE):
                log.warning("Gemini model %s unavailable, trying next", m)
                continue
            raise
    raise last if last else RuntimeError("No Gemini model available")


_status_cache: dict = {"t": 0.0, "v": None}


def ai_status() -> dict:
    if _status_cache["v"] and time.time() - _status_cache["t"] < 60:
        return _status_cache["v"]
    c = gemini()
    if c is None:
        v = {"configured": False, "ok": False, "model": None, "error": ("GEMINI_API_KEY in backend/.env is still the placeholder. Replace it with your real key from Google AI Studio, then restart the server." if KEY_IS_PLACEHOLDER else "No GEMINI_API_KEY found in backend/.env. Add one to turn the AI on.")}
    else:
        try:
            generate(c, contents="Reply with the single word OK")
            v = {"configured": True, "ok": True, "model": _working, "error": ""}
        except Exception as e:
            v = {"configured": True, "ok": False, "model": None, "error": short_err(e)}
    _status_cache.update(t=time.time(), v=v)
    return v


SCOPE_SYSTEM = """You convert a messy client chat for a freelance web project into a strict contract.
Rules:
- 3 to 5 atomic milestones. Amounts are integer rupees and must sum to total_inr.
- 4 to 8 acceptance criteria. Each must be verifiable by reading source code.
- For code-checkable criteria use check_type 'regex' and a LIBERAL case-insensitive Python regex
  (use alternations covering common implementations: element ids, function names, route strings,
  wa.me links, CSS features). file_types lists extensions such as html, js, jsx, css.
- Use check_type 'ai' with an empty pattern ONLY for subjective items.
- Every criterion belongs to a feature: set 'feature' to a short feature name (two criteria of the same
  feature share the exact name) and 'effort_weight' to the feature's relative effort from 1 to 10
  (same weight for all criteria of one feature). Harder features such as payments or login weigh more
  than a button or a theme toggle.
- total_inr is the client's budget as an integer; estimate sensibly if not stated.
- Never invent features the client did not ask for. client_name: the client's name or 'Client'."""


def normalize(d: ContractDraft) -> ContractDraft:
    if d.total_inr <= 0:
        d.total_inr = sum(m.amount_inr for m in d.milestones) or 10000
    if d.milestones:
        diff = d.total_inr - sum(m.amount_inr for m in d.milestones)
        d.milestones[-1].amount_inr += diff
    for i, c in enumerate(d.criteria, 1):
        c.id = f"AC{i}"
        if c.check_type == "regex":
            try:
                re.compile(c.pattern)
            except re.error:
                c.check_type, c.pattern = "ai", ""
        if not c.file_types:
            c.file_types = ["html", "js", "jsx", "tsx", "css"]
        if not (c.feature or "").strip():
            c.feature = c.description[:40]
        c.effort_weight = min(10, max(1, c.effort_weight or 3))
    return d


def gemini_scope(chat: str) -> Optional[ContractDraft]:
    c = gemini()
    if c is None:
        return None
    from google.genai import types

    resp = generate(
        c,
        contents=f"CLIENT CHAT:\n{chat}",
        config=types.GenerateContentConfig(
            system_instruction=SCOPE_SYSTEM,
            response_mime_type="application/json",
            response_schema=ContractDraft,
            temperature=0.2,
        ),
    )
    return normalize(ContractDraft.model_validate_json(resp.text))


# --------------------------------------------------------------------------
# Dynamic cost split: where the client's budget goes
# --------------------------------------------------------------------------
FIXED = {
    "design": ("Design & layout", 0.15, "Page structure, styling and branding"),
    "qa": ("QA & testing", 0.10, "Device checks, bug fixing and polish"),
    "handover": ("Deployment & handover", 0.05, "Packaging, source handover and notes"),
}


def compute_breakdown(total: int, criteria: list) -> list:
    """Split the budget: fixed shares for design / QA / handover, the rest across the
    requested features in proportion to their effort weight. Whole rupees, sums to total."""
    total = max(int(total), 1)
    feats: dict = {}
    for c in criteria:
        f = feats.setdefault(c["feature"], {"weight": 0, "criteria": []})
        f["weight"] = max(f["weight"], int(c["effort_weight"]))
        f["criteria"].append(c["id"])
    pool = total * (1 - sum(v[1] for v in FIXED.values()))
    wsum = sum(f["weight"] for f in feats.values()) or 1
    raw = [("design", FIXED["design"][0], total * FIXED["design"][1], FIXED["design"][2], [])]
    for name, f in feats.items():
        n = len(f["criteria"])
        raw.append(("feature", name, pool * f["weight"] / wsum,
                    f"{n} acceptance criteri{'on' if n == 1 else 'a'} · effort weight {f['weight']}/10", f["criteria"]))
    raw.append(("qa", FIXED["qa"][0], total * FIXED["qa"][1], FIXED["qa"][2], []))
    raw.append(("handover", FIXED["handover"][0], total * FIXED["handover"][1], FIXED["handover"][2], []))
    amounts = [int(r[2]) for r in raw]
    leftover = total - sum(amounts)
    for i in sorted(range(len(raw)), key=lambda i: raw[i][2] - int(raw[i][2]), reverse=True)[:leftover]:
        amounts[i] += 1
    return [{"id": f"CB{i + 1}", "kind": r[0], "label": r[1], "amount": amounts[i],
             "pct": round(100 * amounts[i] / total, 1), "why": r[3], "criteria": r[4]}
            for i, r in enumerate(raw)]


def milestones_from(items: list) -> list:
    amt = lambda *kinds: sum(i["amount"] for i in items if i["kind"] in kinds)
    names = ", ".join(i["label"] for i in items if i["kind"] == "feature") or "requested features"
    return [
        Milestone(title="Design & structure", description="Page skeleton, styling and branding", amount_inr=amt("design")),
        Milestone(title="Core features", description=f"Client-requested functionality: {names}", amount_inr=amt("feature")),
        Milestone(title="QA & handover", description="Testing, fixes, packaging and source handover", amount_inr=amt("qa", "handover")),
    ]


# --------------------------------------------------------------------------
# Deterministic fallback contract (keeps the demo alive if the API dies)
# --------------------------------------------------------------------------
WEB = ["html", "js", "jsx", "tsx"]
ALL_SRC = ["html", "js", "jsx", "tsx", "css"]

# (keyword regex, feature name, effort weight 1-10, stack tag or None, [(description, pattern, file types)])
FEATURES = [
    (r"bmi", "BMI calculator", 4, None, [
        ("BMI calculator form with height and weight inputs",
         r'''id=["']bmi-form["']|bmi[-_ ]?form|<form[^>]*bmi''', WEB),
        ("BMI value is computed in code",
         r'''function\s+calculate\s*BMI|calculate\s*BMI\s*=|const\s+bmi\s*=''', WEB),
    ]),
    (r"dark\s*mode|dark\s*theme", "Dark mode", 3, None, [
        ("Dark mode toggle control exists",
         r'''theme-toggle|dark-?mode-?toggle|id=["']dark''', WEB),
        ("Dark theme styles are implemented",
         r'''data-theme|prefers-color-scheme|\.dark\b|dark:''', ALL_SRC),
    ]),
    (r"whats\s*app", "WhatsApp lead button", 2, "WhatsApp API", [
        ("WhatsApp lead button links to WhatsApp",
         r'''wa\.me/|api\.whatsapp\.com/send|whatsapp://send''', WEB),
    ]),
    (r"contact|lead\s*form", "Lead form", 3, None, [
        ("Contact or lead form with an email or phone field",
         r'''<form[^>]*(contact|lead)|type=["']?(tel|email)\b''', WEB),
    ]),
    (r"responsive|mobile", "Responsive layout", 3, None, [
        ("Responsive layout using media queries",
         r'''@media|\bsm:|\bmd:|\blg:''', ALL_SRC),
    ]),
    (r"payment|razorpay|upi|checkout", "Payments", 8, "Payments", [
        ("Payment integration present", r'''razorpay|upi:|checkout|stripe''', WEB),
    ]),
    (r"login|sign[\s-]?in|auth|bank|account|portal|member", "User login", 7, "Auth", [
        ("Login form with a masked password field", r'''type=["']?password\b''', WEB),
        ("Login or sign-in flow is implemented", r'''login|sign[-_ ]?in|authenticate|session|token''', WEB),
    ]),
    (r"bank|account|wallet|balance|finance|fintech", "Account dashboard", 6, None, [
        ("Account balance or summary is displayed", r'''balance|account[-_ ]?(summary|overview|number)|dashboard''', WEB),
    ]),
    (r"bank|transaction|statement|ledger|history", "Transaction history", 5, None, [
        ("Transaction list or statement view exists", r'''transactions?|statement|ledger|history''', WEB),
    ]),
    (r"bank|transfer|send\s*money|remit|fund", "Fund transfer", 8, "Payments", [
        ("Transfer form with recipient and amount fields", r'''transfer|recipient|beneficiary|send[-_ ]?money|payee''', WEB),
        ("Transfer amount is validated before submit", r'''amount\s*(<=|>=|<|>|===?)|isNaN\(|parseFloat\(|Number\(|validate\w*\(''', WEB),
    ]),
    (r"bank|secur|otp|2fa|two[\s-]?factor|kyc|fraud", "Security (OTP / verification)", 6, "Security", [
        ("OTP or second-step verification exists", r'''otp|2fa|two[-_ ]?factor|verification[-_ ]?code''', WEB),
    ]),
    (r"kyc|onboard|identity|aadhaar|\bpan\b", "KYC onboarding", 7, None, [
        ("KYC / identity document fields exist", r'''kyc|aadhaar|\bpan\b|id[-_ ]?proof|upload''', WEB),
    ]),
    (r"dashboard|chart|analytic|report|graph", "Charts and reports", 6, None, [
        ("Charts or data visualisation present", r'''chart|<canvas|<svg|d3\.|recharts|plotly''', ALL_SRC),
    ]),
    (r"cart|shop|store|e-?commerce|product|catalog", "Product catalogue and cart", 8, "E-commerce", [
        ("Product listing is rendered", r'''product''', WEB),
        ("Add-to-cart behaviour exists", r'''add[-_ ]?to[-_ ]?cart|cart''', WEB),
    ]),
    (r"book(ing)?\b|appointment|reservation|schedul|clinic|doctor|hospital|salon|restaurant|hotel", "Booking flow", 7, None, [
        ("Booking form with a date or time field", r'''type=["']?(date|time|datetime-local)\b|booking|appointment|reservation''', WEB),
    ]),
    (r"admin|cms|manage\s+content|back\s*office", "Admin panel", 7, None, [
        ("Admin area or management view exists", r'''admin|manage|dashboard''', WEB),
    ]),
    (r"clinic|doctor|hospital|dental|health|patient|medical", "Doctors and services listing", 5, None, [
        ("Doctors, departments or services are listed", r'''doctor|department|service|specialit|treatment''', WEB),
    ]),
    (r"clinic|hospital|patient|medical|health", "Patient records / privacy notice", 4, "Security", [
        ("Privacy notice or consent text for patient data", r'''privacy|consent|confidential|hipaa|data protection''', WEB),
    ]),
    (r"menu|restaurant|cafe|food|order", "Menu / catalogue page", 5, None, [
        ("Menu or item listing with prices", r'''menu|price|₹|rs\.?\s*\d''', WEB),
    ]),
    (r"portfolio|gallery|photograph|showcase", "Gallery / portfolio", 4, None, [
        ("Image gallery or project showcase section", r'''gallery|portfolio|<img|lightbox''', WEB),
    ]),
    (r"notif|alert|reminder", "Notifications", 4, None, [
        ("Notification or alert mechanism exists", r'''notification|alert\(|toast|snackbar''', WEB),
    ]),
    (r"search|filter|sort", "Search and filter", 3, None, [
        ("Search or filter input exists", r'''type=["']?search\b|search|filter''', WEB),
    ]),
    (r"api|backend|back-end|database|server|rest\b", "Backend API", 8, "Backend", [
        ("API routes or request handlers are defined", r'''app\.(get|post|put|delete)\(|@app\.|router\.|fetch\(|axios|express\(''', ALL_SRC + ["py"]),
    ]),
]


BUDGET_PATTERNS = [
    r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*(k|lakhs?|lacs?)?\b",      # ₹15,000 / Rs. 40k
    r"([\d,]+(?:\.\d+)?)\s*(k|lakhs?|lacs?)?\s*(?:rs\b|rupees|inr)",      # 15000 rupees
    r"budget[^\d\n]{0,20}([\d,]+(?:\.\d+)?)\s*(k|lakhs?|lacs?)?\b",       # budget 40k / budget of 25000
    r"(?:under|below|upto|up\s*to|within|max(?:imum)?|around|about|approx\.?|roughly|~)\s*(?:of\s*)?([\d,]+(?:\.\d+)?)\s*(k|lakhs?|lacs?)?\b",
    r"\b(\d[\d,]*(?:\.\d+)?)\s*(k|lakhs?|lacs?)\b",                       # 40k / 1.5 lakh
]


def _amount(num: str, unit: Optional[str]) -> Optional[float]:
    try:
        val = float(num.replace(",", ""))
    except ValueError:
        return None
    unit = (unit or "").lower()
    if unit == "k":
        val *= 1000
    elif unit:
        val *= 100000
    return val


def parse_budget(chat: str) -> int:
    for pat in BUDGET_PATTERNS:
        for m in re.finditer(pat, chat, re.I):
            val = _amount(m.group(1), m.group(2))
            if val is not None and 500 <= val < 10_000_000:
                return int(val)
    # last resort: a bare number such as "website 120000" (skip years and phone-length numbers)
    for m in re.finditer(r"\b(\d{1,3}(?:,\d{2,3})+|\d{4,8})\b", chat):
        raw = m.group(1)
        val = int(raw.replace(",", ""))
        if "," not in raw and 1900 <= val <= 2100:
            continue
        if val >= 1000:
            return val
    return 15000


def derive_title(chat: str) -> str:
    t = chat.strip()
    t = re.sub(r"^\s*(?:hi|hello|hey)?[,!. ]*(?:i\s+)?(?:need|want|require|looking\s+for|would\s+like|build|make|create|develop)"
               r"\s+(?:to\s+(?:build|make|create|develop)\s+)?(?:an|a|the|me|us)?\b\s*", "", t, flags=re.I)
    t = re.split(r"[,.;\n]| - |\bwith\b|\bhaving\b|\bincluding\b|\bthat\b|\bwhich\b", t, maxsplit=1, flags=re.I)[0]
    # remove budget phrases such as "under 80k", "budget of 40000", "for rs 5000", "in 20k"
    t = re.sub(r"\b(?:under|below|upto|up\s+to|within|max(?:imum)?|around|about|approx\.?|budget(?:\s+of)?|for|in|at)\s*(?:rs\.?|inr|₹)?\s*[\d,.]+\s*(?:k|lakhs?|lacs?|rupees|rs)?\b", " ", t, flags=re.I)
    t = re.sub(r"(?:₹|rs\.?|inr)\s*[\d,.]+\s*(?:k|lakhs?|lacs?)?", " ", t, flags=re.I)
    t = re.sub(r"\s+(?:and|or|for|in|at|of|to)\s*$", "", " ".join(t.split()), flags=re.I)
    t = t[:70].strip(" -")
    return (t[:1].upper() + t[1:]) if t else "Web project"


def fallback_contract(chat: str) -> ContractDraft:
    low = chat.lower()
    criteria, tags = [], ["HTML", "CSS", "JavaScript"]
    for kw, feature, weight, tag, items in FEATURES:
        if re.search(kw, low):
            if tag:
                tags.append(tag)
            for desc, pattern, ftypes in items:
                criteria.append(Criterion(id="", description=desc, check_type="regex", pattern=pattern,
                                          file_types=ftypes, feature=feature, effort_weight=weight))
    if not criteria:
        criteria.append(Criterion(id="", description="A working page entry point exists", check_type="regex",
                                  pattern=r"<html|<!doctype html|createRoot|ReactDOM", file_types=WEB,
                                  feature="Core pages", effort_weight=4))
        criteria.append(Criterion(id="", description="Contact details or a contact form are present", check_type="regex",
                                  pattern=r"mailto:|tel:|<form|contact", file_types=WEB,
                                  feature="Contact section", effort_weight=3))
        criteria.append(Criterion(id="", description="Layout is mobile-friendly", check_type="regex",
                                  pattern=r"<meta[^>]*viewport|@media", file_types=ALL_SRC,
                                  feature="Responsive layout", effort_weight=3))
    total = parse_budget(chat)
    title = derive_title(chat)
    draft = normalize(ContractDraft(
        title=title,
        summary=chat.strip()[:400], client_name="Client", stack_tags=tags,
        total_inr=total, milestones=[], criteria=criteria,
    ))
    draft.milestones = milestones_from(compute_breakdown(total, [c.model_dump() for c in draft.criteria]))
    return draft


# --------------------------------------------------------------------------
# Build plan: analyse the chat, give the developer a phased plan + suggestions
# --------------------------------------------------------------------------
class FeatureGuide(BaseModel):
    feature: str = Field(description="Exact feature name from the contract")
    steps: list[str] = Field(description="3-5 concrete build steps, in order, each one short sentence")
    tip: str = Field(description="One practical suggestion or pitfall for this feature")


class StackChoice(BaseModel):
    layer: str
    choice: str
    why: str


class AIPlan(BaseModel):
    overview: str = Field(description="2-3 sentence read of what the client actually wants and the main risk")
    stack: list[StackChoice] = Field(description="3-5 layers e.g. Frontend, Styling, Backend, Hosting")
    file_structure: list[str] = Field(description="Suggested files/folders, one per entry, e.g. 'index.html - entry page'")
    guides: list[FeatureGuide]
    risks: list[str] = Field(description="3-4 delivery risks or scope-creep traps worth raising with the client")
    suggestions: list[str] = Field(description="3-5 improvements that would impress the client without changing the budget much")
    clarify: list[str] = Field(description="2-4 questions the developer should ask the client before starting")


PLAN_SYSTEM = (
    "You are a senior freelance tech lead. Read the client's chat and the agreed contract and give the developer a "
    "practical build plan. Use the exact feature names from the contract in 'guides'. Be concrete and brief, "
    "no filler. Prefer simple stacks the developer can finish within the budget."
)

STEPS = {
    "User login": ["Design the login and sign-up screens", "Hash passwords server-side, never store plain text", "Issue a session or token and guard private pages", "Show clear errors for wrong credentials"],
    "Account dashboard": ["Sketch the data the user must see first (balance, recent activity)", "Build summary cards and a recent-activity list", "Load data from the API, not hard-coded values"],
    "Transaction history": ["Define the transaction record fields", "Render a sortable, paginated list", "Add date and type filters"],
    "Fund transfer": ["Build recipient + amount form with validation", "Re-check amount and balance on the server", "Add a confirmation step before submit", "Return a receipt with a reference id"],
    "Security (OTP / verification)": ["Add a second verification step for sensitive actions", "Rate-limit attempts and expire codes", "Never log OTPs or secrets"],
    "KYC onboarding": ["Create a stepwise onboarding form", "Validate PAN/Aadhaar format client-side", "Store uploads outside the public folder"],
    "Product catalogue and cart": ["Create a product data file or table", "Render the product grid with images and prices", "Build add/remove/quantity cart logic", "Persist the cart across reloads"],
    "Booking flow": ["Define bookable slots", "Build the date/time picker form", "Block double bookings", "Send a confirmation to the user"],
    "Admin panel": ["Protect the admin route", "List and edit the main records", "Log who changed what"],
    "Charts and reports": ["Pick 2-3 charts that answer the client's questions", "Feed them from one data source", "Make them readable on mobile"],
    "Backend API": ["List endpoints before coding", "Validate every input", "Return consistent JSON errors", "Document the routes in the README"],
    "BMI calculator": ["Build height and weight inputs with units", "Compute BMI and show the category", "Handle empty or impossible values"],
    "Dark mode": ["Define colour variables for both themes", "Add a toggle and remember the choice", "Check contrast in both modes"],
    "WhatsApp lead button": ["Create a wa.me link with a prefilled message", "Make it sticky on mobile"],
    "Lead form": ["Build the form with email/phone validation", "Decide where leads go (email, sheet, API)", "Show a thank-you state"],
    "Responsive layout": ["Start mobile-first", "Add breakpoints for tablet and desktop", "Test at 360px and 1280px widths"],
    "Payments": ["Use the provider's hosted checkout", "Verify the payment signature on the server", "Handle failure and retry"],
    "Search and filter": ["Add the search input", "Filter client-side for small data, server-side for large"],
    "Notifications": ["Decide which events notify", "Show non-blocking toasts or emails"],
    "Doctors and services listing": ["List doctors, departments and services with clear names", "Show photo, qualification and timings for each doctor", "Add a call or book button on every card"],
    "Patient records / privacy notice": ["Collect only the patient data you need", "Add a plain-language privacy and consent notice next to every form", "Never log or email medical details in plain text"],
    "Menu / catalogue page": ["Create the item list with names, prices and photos", "Group items into categories", "Make the page readable on a phone"],
    "Gallery / portfolio": ["Collect and compress the images", "Build a responsive grid with a lightbox", "Add alt text to every image"],
    "Contact section": ["Add phone, email and address", "Build a contact form with validation", "Add a map link"],
    "Core pages": ["Create the main pages and navigation", "Write real content, not lorem ipsum", "Add a viewport meta tag"],
}
TIPS = {
    "Fund transfer": "Do all money maths on the server in integer paise and make requests idempotent.",
    "User login": "Add a rate limit on login attempts. Judges and clients both look for it.",
    "Payments": "Use test keys only and never commit them.",
    "Security (OTP / verification)": "A fake OTP is fine for the demo, but label it clearly.",
    "Core pages": "Show the client a clickable prototype before polishing code.",
}
STACK_DEFAULT = [
    {"layer": "Frontend", "choice": "HTML + CSS + vanilla JavaScript (or React + Vite if the app has many screens)", "why": "Fastest to deliver inside a small budget and easy for the client to host."},
    {"layer": "Styling", "choice": "CSS variables with a mobile-first layout", "why": "Gives dark mode and responsiveness almost for free."},
    {"layer": "Backend", "choice": "FastAPI or Express only if the scope needs real data", "why": "Skip it for static brochure sites."},
    {"layer": "Hosting", "choice": "Netlify, Vercel or GitHub Pages", "why": "Free tier, instant previews for the client."},
]


def gemini_plan(chat: str, contract: dict) -> Optional[AIPlan]:
    c = gemini()
    if c is None:
        return None
    from google.genai import types

    feats = sorted({cr["feature"] for cr in contract["criteria"]})
    resp = generate(
        c,
        contents=f"CLIENT CHAT:\n{chat}\n\nCONTRACT TITLE: {contract['title']}\nBUDGET: INR {contract['total_inr']}\nFEATURES: {', '.join(feats)}",
        config=types.GenerateContentConfig(system_instruction=PLAN_SYSTEM, response_mime_type="application/json",
                                           response_schema=AIPlan, temperature=0.3),
    )
    return AIPlan.model_validate_json(resp.text)


def build_plan(chat: str, contract: dict, breakdown: list, ai: Optional[AIPlan]) -> dict:
    """Deterministic backbone (phases, tasks, hours, links to criteria) enriched by AI guidance when available."""
    guides = {g.feature: g for g in ai.guides} if ai else {}
    crit = {cr["id"]: cr for cr in contract["criteria"]}
    phases, hrs = [], lambda w: max(1.0, round(w * 1.5 * 2) / 2)
    for it in breakdown:
        if it["kind"] == "design":
            phases.append({"name": "Set up and design", "goal": "Scaffold the project and agree the look before building features.",
                           "est_hours": 4.0, "amount_inr": it["amount"], "tasks": [
                {"title": "Scaffold the project and folders", "detail": "Create the repo, entry file and README.", "criterion_ids": []},
                {"title": "Define the design system", "detail": "Colours, fonts, spacing, button styles.", "criterion_ids": []},
                {"title": "Share a quick prototype with the client", "detail": "Confirm direction before the expensive work.", "criterion_ids": []}]})
        elif it["kind"] == "feature":
            g = guides.get(it["label"])
            steps = (g.steps if g else None) or STEPS.get(it["label"]) or [f"Build the interface for {it['label']}", "Wire up the logic", "Test the edge cases"]
            tasks = [{"title": st, "detail": "", "criterion_ids": []} for st in steps]
            for cid in it["criteria"]:
                tasks.append({"title": "Done when: " + crit[cid]["description"], "detail": "The audit looks for this in your code.",
                              "criterion_ids": [cid], "check": True})
            weight = max((crit[c]["effort_weight"] for c in it["criteria"]), default=3)
            phases.append({"name": it["label"], "goal": f"Deliver {it['label']} as agreed.", "est_hours": hrs(weight),
                           "amount_inr": it["amount"], "tip": (g.tip if g else None) or TIPS.get(it["label"], ""), "tasks": tasks})
        elif it["kind"] == "qa":
            phases.append({"name": "Test and polish", "goal": "Find problems before the client does.", "est_hours": 3.0, "amount_inr": it["amount"],
                           "tasks": [{"title": "Test on a phone-size and a desktop-size screen", "detail": "", "criterion_ids": []},
                                     {"title": "Click every button and submit every form", "detail": "", "criterion_ids": []},
                                     {"title": "Fix console errors and broken links", "detail": "", "criterion_ids": []}]})
        else:
            phases.append({"name": "Handover", "goal": "Ship a clean zip the client can run.", "est_hours": 1.5, "amount_inr": it["amount"],
                           "tasks": [{"title": "Remove .env files and any API keys", "detail": "The audit blocks the handover share if secrets are found.", "criterion_ids": []},
                                     {"title": "Write a short README (how to run, how to deploy)", "detail": "", "criterion_ids": []},
                                     {"title": "Zip the project, upload it, then submit to the client", "detail": "", "criterion_ids": []}]})
    feats = [p["name"] for p in phases if p.get("tip") is not None]
    return {
        "source": "gemini" if ai else "template",
        "overview": ai.overview if ai else f"The client wants: {contract['title']}. {len(feats)} feature area(s) were detected in the chat and the budget of INR {contract['total_inr']:,} is split by effort.",
        "stack": [s.model_dump() for s in ai.stack] if ai else STACK_DEFAULT,
        "file_structure": ai.file_structure if ai else ["index.html - entry page", "styles.css - theme and layout", "app.js - behaviour", "README.md - how to run"],
        "phases": phases,
        "risks": ai.risks if ai else ["Scope creep: anything not in the acceptance criteria is a change request.", "Unclear content or images from the client can delay the design.", "Late client feedback: agree a review window up front."],
        "suggestions": ai.suggestions if ai else ["Add a short loading and empty state to every screen.", "Add meaningful alt text and labels (accessibility).", "Keep secrets in environment variables, never in the zip."],
        "clarify": ai.clarify if ai else ["Do you have a logo, brand colours and content ready?", "Which devices matter most?", "Who will host the site after handover?"],
        "total_hours": round(sum(p["est_hours"] for p in phases), 1),
    }


def plan_eval(p: dict) -> Optional[dict]:
    """After an audit: how far along is each planned task, and what to fix next."""
    au, plan = p.get("audit"), p.get("plan")
    if not (au and plan):
        return None
    by = {r["id"]: r for r in au["results"]}
    todo = []
    for ph in plan["phases"]:
        for t in ph["tasks"]:
            if t.get("criterion_ids"):
                r = by.get(t["criterion_ids"][0])
                t["status"] = "done" if r and r["passed"] else "todo"
                if t["status"] == "todo":
                    todo.append({"phase": ph["name"], "task": t["title"].replace("Done when: ", ""), "hint": (r or {}).get("note", "")})
    return {"score": au["score"], "next_fixes": todo, "security": au["security_warnings"]}


# --------------------------------------------------------------------------
# Secret scrubber / sanitizer
# --------------------------------------------------------------------------
SECRET_PATTERNS = [
    ("Google API key", r"AIza[0-9A-Za-z_\-]{35}"),
    ("Secret key (sk-...)", r"sk-[A-Za-z0-9_\-]{20,}"),
    ("Razorpay key", r"rzp_(?:test|live)_[A-Za-z0-9]{8,}"),
    ("AWS access key", r"AKIA[0-9A-Z]{16}"),
    ("Private key block", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("Env-style secret", r"(?i)\b[A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|API_KEY)[A-Z0-9_]*\s*=\s*\S+"),
]
PII_PATTERNS = [
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}",
    r"(?:\+91[\s-]?)?[6-9]\d{9}\b",
]


def scrub(text: str) -> str:
    for _, pat in SECRET_PATTERNS:
        text = re.sub(pat, "[REDACTED]", text)
    for pat in PII_PATTERNS:
        text = re.sub(pat, "[REDACTED]", text)
    return text


# --------------------------------------------------------------------------
# Audit engine
# --------------------------------------------------------------------------
TEXT_EXT = {".html", ".htm", ".js", ".jsx", ".ts", ".tsx", ".css", ".json", ".vue", ".svelte", ".py", ".md"}
SKIP_RE = re.compile(r"(^|/)(__MACOSX|node_modules|\.git|dist|build|\.next)(/|$)|\.min\.")
MAX_FILES, MAX_TOTAL, MAX_FILE = 2000, 50 * 1024 * 1024, 1024 * 1024


def read_zip(data: bytes):
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise HTTPException(400, "That is not a valid .zip file")
    infos = zf.infolist()
    if len(infos) > MAX_FILES or sum(i.file_size for i in infos) > MAX_TOTAL:
        raise HTTPException(400, "Archive too large for the demo auditor")
    files, names = {}, []
    for info in infos:
        if info.is_dir() or SKIP_RE.search(info.filename):
            continue
        names.append(info.filename)
        if Path(info.filename).suffix.lower() in TEXT_EXT and info.file_size <= MAX_FILE:
            files[info.filename] = zf.read(info).decode("utf-8", errors="ignore")
    return files, names


def regex_hit(pattern: str, file_types: list, files: dict) -> Optional[dict]:
    try:
        rx = re.compile(pattern, re.I)
    except re.error:
        return None
    exts = {"." + e.lower().lstrip(".") for e in file_types} if file_types else None
    for name, text in files.items():
        if exts and Path(name).suffix.lower() not in exts:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if rx.search(line[:2000]):
                return {"file": name, "line": n, "snippet": line.strip()[:200]}
    return None


def ai_check(desc: str, files: dict) -> Optional[dict]:
    """LLM judges a requirement, but evidence must be quoted and is re-located
    deterministically in the source. Hallucinated evidence is rejected."""
    c = gemini()
    if c is None:
        return None
    try:
        from google.genai import types

        corpus = ""
        for name, text in files.items():
            chunk = f"\n=== FILE: {name} ===\n{text}\n"
            if len(corpus) + len(chunk) > 60000:
                break
            corpus += chunk
        resp = generate(
            c,
            contents=(f"Requirement: {desc}\n\nDoes the code below implement it? If yes, quote ONE exact "
                      f"line copied verbatim from a file as evidence and name that file.\n{corpus}"),
            config=types.GenerateContentConfig(
                response_mime_type="application/json", response_schema=AIVerdict, temperature=0),
        )
        v = AIVerdict.model_validate_json(resp.text)
        if not v.passed:
            return {"passed": False, "reason": v.reason}
        needle = v.snippet.strip()
        for n, line in enumerate(files.get(v.file, "").splitlines(), 1):
            if needle and needle in line:
                return {"passed": True, "file": v.file, "line": n, "snippet": line.strip()[:200], "reason": v.reason}
        return {"passed": False, "reason": "AI evidence could not be located in the source"}
    except Exception as e:
        log.warning("ai_check failed: %s", e)
        return None


def security_scan(files: dict, names: list) -> list:
    warns = []
    for n in names:
        base = n.rsplit("/", 1)[-1]
        if base == ".env" or base.startswith(".env."):
            warns.append({"type": "Environment file included", "file": n, "line": None})
    for name, text in files.items():
        for i, line in enumerate(text.splitlines(), 1):
            for label, pat in SECRET_PATTERNS:
                if re.search(pat, line):
                    warns.append({"type": label, "file": name, "line": i})
    return warns[:15]


def evaluate_delivery(breakdown: list, total: int, results: list, warnings: list) -> dict:
    """Turn criterion results into value delivered (in rupees) and a client-facing verdict."""
    by = {r["id"]: r["passed"] for r in results}
    feat_amt = feat_earned = 0
    for it in breakdown:
        if it["kind"] == "feature":
            ids = it["criteria"]
            feat_amt += it["amount"]
            feat_earned += round(it["amount"] * (sum(1 for i in ids if by.get(i)) / len(ids) if ids else 0))
    ratio = feat_earned / feat_amt if feat_amt else 0
    rows = []
    for it in breakdown:
        if it["kind"] == "feature":
            ids = it["criteria"]
            ok = sum(1 for i in ids if by.get(i))
            r = ok / len(ids) if ids else 0
            rows.append({**it, "earned": round(it["amount"] * r),
                         "status": "met" if r == 1 else "partial" if r > 0 else "missing",
                         "note": f"{ok} of {len(ids)} criteria found in the code"})
        elif it["kind"] == "handover" and warnings:
            rows.append({**it, "earned": 0, "status": "attention",
                         "note": "Deliverable contains secrets or an .env file. Remove them before handover."})
        else:
            rows.append({**it, "earned": round(it["amount"] * ratio), "status": "assumed",
                         "note": "Not directly verifiable by code analysis; counted in proportion to completed features"})
    earned = sum(r["earned"] for r in rows)
    weighted = round(100 * earned / max(total, 1))
    missing = [r["description"] for r in results if not r["passed"]]
    n = len(results)
    if not missing:
        level, headline = "satisfied", "Delivery matches what you asked for"
        detail = f"All {n} agreed requirements were found in the delivered source code."
    elif weighted >= 60:
        level, headline = "partial", f"{len(missing)} of {n} requirements were not found"
        detail = "Most of the agreed work is present, but the items listed below were not found in the delivered code."
    else:
        level, headline = "not_met", "Delivery does not meet the agreed requirements"
        detail = f"{len(missing)} of {n} agreed requirements were not found in the delivered code."
    flags = ["The deliverable contains secrets or an .env file"] if warnings else []
    return {"cost_rows": rows, "value_delivered_inr": earned, "value_total_inr": total, "weighted_score": weighted,
            "verdict": {"level": level, "headline": headline, "detail": detail, "missing": missing, "flags": flags}}


def run_audit(p: dict, data: bytes) -> dict:
    files, names = read_zip(data)
    results = []
    for c in p["contract"]["criteria"]:
        hit, method, note = None, "regex", ""
        if c["check_type"] == "regex" and c["pattern"]:
            hit = regex_hit(c["pattern"], c["file_types"], files)
        if not hit:
            v = ai_check(c["description"], files)
            if v and v.get("passed"):
                hit, method = v, "ai-grounded"
            elif v:
                note = v.get("reason", "")
        results.append({
            "id": c["id"], "feature": c.get("feature", ""), "description": c["description"],
            "passed": bool(hit), "method": method,
            "file": hit["file"] if hit else None, "line": hit["line"] if hit else None,
            "snippet": hit["snippet"] if hit else None,
            "note": note or ("" if hit else "No matching code found"),
        })
    passed = sum(r["passed"] for r in results)
    score = round(100 * passed / (len(results) or 1))
    warnings = security_scan(files, names)
    return {
        "score": score, "passed": passed, "total": len(results),
        "badge": f"{score}% Spec-Presence Verified", "results": results,
        "security_warnings": warnings, "files_scanned": len(files),
        "zip_sha256": hashlib.sha256(data).hexdigest(), "audited_at": now_iso(),
        **evaluate_delivery(p["breakdown"], p["invoice"]["total_inr"], results, warnings),
    }


# --------------------------------------------------------------------------
# Projects, DRM, minter
# --------------------------------------------------------------------------
def create_project(chat: str, user: dict, client_email: str, grace_hours: int, force_fallback: bool = False,
                   terms: Optional[dict] = None, price_inr: Optional[int] = None) -> dict:
    if effective_plan(user) != "pro":
        active = sum(1 for x in DB["projects"].values() if x["freelancer_id"] == user["id"] and not x["paid"])
        if active >= PLANS["free"]["max_active"]:
            raise HTTPException(402, f"The Starter plan allows {PLANS['free']['max_active']} active projects. Finish one or upgrade to Pro.")
    draft, source, ai_error = None, "fallback", ""
    if force_fallback:
        ai_error = "Offline template requested"
    elif gemini() is None:
        ai_error = "GEMINI_API_KEY in backend/.env is still the placeholder" if KEY_IS_PLACEHOLDER else "No GEMINI_API_KEY configured"
    else:
        try:
            draft = gemini_scope(chat + (f"\nFinal agreed price: INR {price_inr}" if price_inr else ""))
            source = "gemini" if draft else "fallback"
        except Exception as e:
            log.warning("Gemini scope failed, using fallback: %s", e)
            ai_error = short_err(e)
            draft = None
    if draft is None:
        draft, source = fallback_contract(chat), "fallback"
    if price_inr:
        draft.total_inr = int(price_inr)
        draft.milestones = milestones_from(compute_breakdown(draft.total_inr, [c.model_dump() for c in draft.criteria]))
    t = {"advance_pct": 30, "revisions_included": 2, "review_days": 3, "late_fee_pct_per_week": 2, "delivery_days": 7, **(terms or {})}
    t["advance_inr"] = round(draft.total_inr * t["advance_pct"] / 100)
    client_email = client_email.strip().lower()
    client_user = DB["users"].get(client_email)
    breakdown = compute_breakdown(draft.total_inr, [c.model_dump() for c in draft.criteria])
    ai_plan = None
    if source == "gemini":
        try:
            ai_plan = gemini_plan(chat, draft.model_dump())
        except Exception as e:
            log.warning("Gemini plan failed, using template plan: %s", e)
    plan = build_plan(chat, draft.model_dump(), breakdown, ai_plan)
    pid = "prj_" + secrets.token_hex(4)
    now = time.time()
    p = {
        "id": pid, "freelancer_id": user["id"], "freelancer_name": user["name"],
        "client_email": client_email,
        "client_name": client_user["name"] if client_user else draft.client_name,
        "chat": chat, "source": source, "contract": draft.model_dump(),
        "ai_model": _working if source == "gemini" else None, "ai_error": ai_error if source == "fallback" else "",
        "breakdown": breakdown, "plan": plan,
        "invoice": {
            "number": f"SY-{datetime.now():%y%m%d}-{pid[-4:].upper()}",
            "total_inr": draft.total_inr, "created_at": now_iso(),
            "grace_period_seconds": grace_hours * 3600, "deadline_ts": now + grace_hours * 3600,
        },
        "status": "scoped", "feedback": None, "terms": t,
        "payments": [], "revisions": {"included": t["revisions_included"], "used": 0, "log": []},
        "extras": [], "pending_quote": False, "timeline": [], "reminders": [], "review_deadline_ts": None, "funded": False,
        "drm_state": "PREVIEW", "audit": None, "paid": None, "mint_hash": None, "zip_file": None, "submitted_at": None,
        "created_ts": now,
    }
    p["agreement"] = {"version": 1, "freelancer_signed_at": now_iso(), "client_signed_at": None, "client_signed_by": None}
    p["agreement"]["clauses"] = [list(c) for c in _build_clauses(p)]
    p["agreement"]["sha256"] = hashlib.sha256(agreement_text(p).encode()).hexdigest()
    log_event(p, "freelancer", "project_created", f"{draft.title} for INR {draft.total_inr:,}")
    DB["projects"][pid] = p
    save()
    return p


def get_project(pid: str) -> dict:
    p = DB["projects"].get(pid)
    if not p:
        raise HTTPException(404, "Unknown project")
    return p


def own_project(pid: str, user: dict, role: Optional[str] = None) -> dict:
    p = get_project(pid)
    if role and user["role"] != role:
        raise HTTPException(403, f"Only {role}s can do this")
    ok = p["freelancer_id"] == user["id"] if user["role"] == "freelancer" else p["client_email"] == user["email"]
    if not ok:
        raise HTTPException(404, "Unknown project")  # 404, not 403: don't reveal other projects exist
    return p


def current_state(p: dict) -> str:
    """Auto-lock when the grace period expires on an unpaid project."""
    if p["drm_state"] == "PREVIEW" and not p["paid"] and time.time() > p["invoice"]["deadline_ts"]:
        p["drm_state"] = "KILLED"
        save()
    return p["drm_state"]



# --------------------------------------------------------------------------
# Money, timeline, agreement, reminders, evidence pack
# --------------------------------------------------------------------------
def log_event(p: dict, actor: str, event: str, detail: str = "") -> None:
    p.setdefault("timeline", []).append({"at": now_iso(), "actor": actor, "event": event, "detail": detail})
    del p["timeline"][:-200]


def late_fee(p: dict) -> int:
    rd = p.get("review_deadline_ts")
    if p["paid"] or p["status"] != "submitted" or not rd or time.time() <= rd:
        return 0
    weeks = int((time.time() - rd) // 604800) + 1
    pct = min(p["terms"]["late_fee_pct_per_week"] * weeks, 10)
    base = p["invoice"]["total_inr"] + sum(e["amount_inr"] for e in p["extras"])
    return round(base * pct / 100)


def money(p: dict) -> dict:
    base = p["invoice"]["total_inr"]
    extras = sum(e["amount_inr"] for e in p["extras"])
    fee = p["paid"].get("late_fee_inr", 0) if p["paid"] else late_fee(p)
    grand = base + extras + fee
    received = sum(x["amount_inr"] for x in p["payments"])
    adv = sum(x["amount_inr"] for x in p["payments"] if x["kind"] == "advance")
    return {"base": base, "extras": extras, "late_fee": fee, "grand_total": grand, "advance_paid": adv,
            "advance_required": p["terms"]["advance_inr"], "received": received, "balance_due": max(0, grand - received)}


def _build_clauses(p: dict) -> list:
    t, c = p["terms"], p["contract"]
    plural = lambda n, w: f"{n} {w}" + ("" if n == 1 else "s")
    ac = "\n".join(f"{x['id']}. {x['description']}" for x in c["criteria"])
    lines = "\n".join(f"- {it['label']}: INR {it['amount']:,}" for it in p["breakdown"])
    adv = (f"{t['advance_pct']}% (INR {t['advance_inr']:,}) is paid by the Client before the Freelancer submits the work, and the balance on acceptance."
           if t["advance_inr"] else "There is no advance. The full price is paid on acceptance.")
    start = "receiving the advance" if t["advance_inr"] else "the Client signing this agreement"
    return [
        ("1. Parties", f"Freelancer: {p['freelancer_name']}. Client: the account holder of {p['client_email']}, who confirms their name when signing."),
        ("2. Project", f"{c['title']}. The Freelancer's brief is kept in the project record. If the brief and this agreement differ, this agreement applies."),
        ("3. Deliverables and acceptance", "The work is complete when each requirement below is present in the delivered source code, as shown by the Synera spec audit "
         "with file and line evidence, or when the Client approves it. The audit checks that each requirement exists in the code. It does not run the application.\n" + ac),
        ("4. Price and payment", f"Agreed price: INR {c['total_inr']:,}. {adv}\nHow the price is allocated:\n{lines}"),
        ("5. Delivery time", f"The Freelancer will submit the work for review within {plural(t.get('delivery_days', 7), 'day')} of {start}. "
         "Time lost waiting for content, feedback or the advance from the Client extends this period."),
        ("6. Revisions and extra work", f"{plural(t['revisions_included'], 'round')} of revisions {'is' if t['revisions_included'] == 1 else 'are'} included. Work beyond the included rounds, "
         "or outside the requirements above, is quoted by the Freelancer first and shown to the Client before payment. Nothing extra is payable without a quote."),
        ("7. Review window and deemed acceptance", f"The Client has {plural(t['review_days'], 'day')} from each submission to approve or request changes. "
         "If the Client does nothing within that window, the delivery is treated as accepted and the balance becomes due."),
        ("8. Late payment", f"After the balance is due, {t['late_fee_pct_per_week']}% of the unpaid amount is added per week or part of a week, capped at 10%."),
        ("9. Delivery and ownership", "The Client may review a Synera-hosted preview. The preview locks if the review window ends unpaid. "
         "Source files and ownership transfer to the Client on payment in full. Until then the Freelancer keeps all rights."),
        ("10. Cancellation", "If either party cancels before the work is submitted, the Freelancer keeps the advance for the work already done. "
         "Any part of the advance that is more than the value of the work done is returned to the Client."),
        ("11. Proof of payment", "Only a Synera gateway-signed payment record counts as payment. A screenshot or forwarded message is not proof of payment. "
         "Anyone can check a payment reference on the public payment-check page."),
        ("12. Disputes and general terms", "Both parties will try to resolve disagreements within 7 days using the audit report and the project timeline. Synera can export a sealed evidence pack. "
         "Changes to this agreement are valid only if recorded in Synera. This agreement is governed by the laws of India. "
         "It is a template and not legal advice. For large projects, get it reviewed by a lawyer."),
    ]


def agreement_clauses(p: dict) -> list:
    snap = (p.get("agreement") or {}).get("clauses")  # the text is frozen when the project is created
    return [tuple(x) for x in snap] if snap else _build_clauses(p)


def agreement_text(p: dict) -> str:
    return "\n\n".join(f"{h}\n{b}" for h, b in agreement_clauses(p))


def agreement_html(p: dict) -> str:
    rows = "".join(f"<h3>{html.escape(h)}</h3><p>{html.escape(b).replace(chr(10), '<br>')}</p>" for h, b in agreement_clauses(p))
    ag = p["agreement"]
    return (f"<!doctype html><meta charset=utf-8><title>Agreement {html.escape(p['invoice']['number'])}</title>"
            "<style>body{font:15px/1.6 system-ui;max-width:760px;margin:40px auto;padding:0 20px;color:#111}h3{margin:22px 0 4px}</style>"
            f"<h1>Freelance Agreement</h1><p>Reference {html.escape(p['invoice']['number'])}</p>{rows}<hr>"
            f"<p>Freelancer ({html.escape(p['freelancer_name'])}) signed: {ag['freelancer_signed_at']}<br>Client ({html.escape(ag.get('client_signed_by') or p['client_email'])}) signed: {ag['client_signed_at'] or 'pending'}<br>"
            f"SHA-256: <code>{ag['sha256']}</code></p>")


def reminder_message(p: dict, level: int, base_url: str) -> dict:
    m, t = money(p), p["terms"]
    link = f"{base_url}/" if base_url else "your Synera dashboard"
    name = p["client_name"].split()[0] if p["client_name"] else "there"
    title, inv = p["contract"]["title"], p["invoice"]["number"]
    if level == 1:
        subj = f"Ready for your review: {title}"
        body = (f"Hi {name}, {title} is ready for your review. You can check the verified delivery and pay the balance of INR {m['balance_due']:,} "
                f"(invoice {inv}) here: {link} (log in with {p['client_email']}). Thank you!")
    elif level == 2:
        subj = f"Reminder: invoice {inv} is awaiting payment"
        body = (f"Hi {name}, following up on invoice {inv} for {title}. The review window in our agreement has ended. "
                f"The balance is INR {m['balance_due']:,}"
                + (f", including a late fee of INR {m['late_fee']:,}" if m["late_fee"] else "")
                + f". Please review and pay here: {link}. If something is missing, tell me what and I will fix it.")
    else:
        subj = f"Final notice: invoice {inv}"
        body = (f"Dear {p['client_name']}, this is a final notice for invoice {inv} ({title}). Under clause 6 of our signed agreement, the delivery is "
                f"deemed accepted and INR {m['balance_due']:,} is due. Please pay within 7 days at {link}. "
                "A sealed evidence pack (agreement, audit with file and line proof, payment and delivery timeline) is available if this has to be escalated "
                "to a platform, a payment provider or a small-claims process.")
    from urllib.parse import quote
    return {"level": level, "subject": subj, "body": body,
            "whatsapp_url": "https://wa.me/?text=" + quote(body),
            "mailto_url": f"mailto:{p['client_email']}?subject={quote(subj)}&body={quote(body)}"}


def evidence_pack(p: dict) -> dict:
    au = p["audit"]
    pack = {
        "generated_at": now_iso(),
        "project": {"id": p["id"], "title": p["contract"]["title"], "invoice_number": p["invoice"]["number"],
                    "freelancer": p["freelancer_name"], "client": p["client_name"], "client_email": p["client_email"]},
        "agreement": {**{k: v for k, v in p["agreement"].items() if k != "clauses"}, "clauses": [{"title": h, "text": b} for h, b in agreement_clauses(p)],
                      "integrity_ok": hashlib.sha256(agreement_text(p).encode()).hexdigest() == p["agreement"]["sha256"]},
        "original_brief": p["chat"], "terms": p["terms"], "money": money(p),
        "payments": p["payments"], "extras": p["extras"], "revisions": p["revisions"],
        "delivery": {"submitted_at": p.get("submitted_at"), "zip_sha256": au["zip_sha256"] if au else None,
                     "audit_score": au["score"] if au else None,
                     "requirements": [{"id": r["id"], "description": r["description"], "found": r["passed"], "file": r["file"], "line": r["line"]}
                                      for r in (au["results"] if au else [])],
                     "security_warnings": au["security_warnings"] if au else []},
        "reminders": [{"at": r["at"], "level": r["level"]} for r in p["reminders"]],
        "timeline": p["timeline"], "proof_hash": p.get("mint_hash"),
    }
    pack["seal_sha256"] = hashlib.sha256(json.dumps(pack, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return pack


def evidence_html(pk: dict) -> str:
    e = html.escape
    req = "".join(f"<li>{'FOUND' if r['found'] else 'NOT FOUND'}: {e(r['description'])} {e(str(r['file'] or ''))}{(':' + str(r['line'])) if r['line'] else ''}</li>"
                  for r in pk["delivery"]["requirements"])
    tl = "".join(f"<li>{e(x['at'])} [{e(x['actor'])}] {e(x['event'])} {e(x['detail'])}</li>" for x in pk["timeline"])
    pay = "".join(f"<li>{e(x['kind'])} INR {x['amount_inr']:,} via {e(x['method'])} ({e(x['payment_id'])}) at {e(x['at'])}</li>" for x in pk["payments"]) or "<li>None yet</li>"
    cl = "".join(f"<h3>{e(c['title'])}</h3><p>{e(c['text']).replace(chr(10), '<br>')}</p>" for c in pk["agreement"]["clauses"])
    m = pk["money"]
    return (f"<!doctype html><meta charset=utf-8><title>Evidence pack</title><style>body{{font:14px/1.55 system-ui;max-width:820px;margin:36px auto;padding:0 18px}}"
            f"code{{word-break:break-all}}</style><h1>Evidence pack: {e(pk['project']['title'])}</h1>"
            f"<p>Invoice {e(pk['project']['invoice_number'])}. Freelancer {e(pk['project']['freelancer'])}. Client {e(pk['project']['client'])} ({e(pk['project']['client_email'])}). Generated {e(pk['generated_at'])}.</p>"
            f"<h2>Money</h2><p>Price INR {m['base']:,}; extras INR {m['extras']:,}; late fee INR {m['late_fee']:,}; received INR {m['received']:,}; balance INR {m['balance_due']:,}.</p>"
            f"<h2>Payments</h2><ul>{pay}</ul><h2>Delivery</h2><p>Zip SHA-256 <code>{e(str(pk['delivery']['zip_sha256']))}</code>. Audit score {pk['delivery']['audit_score']}%.</p><ul>{req}</ul>"
            f"<h2>Agreement</h2><p>Hash <code>{e(pk['agreement']['sha256'])}</code>. Freelancer signed {e(str(pk['agreement']['freelancer_signed_at']))}; client signed {e(str(pk['agreement']['client_signed_at']))}.</p>{cl}"
            f"<h2>Original brief</h2><p>{e(pk['original_brief'])}</p><h2>Timeline</h2><ul>{tl}</ul>"
            f"<hr><p>Seal (SHA-256 of this pack's data): <code>{pk['seal_sha256']}</code><br>This is a record of events, not legal advice.</p>")



# --------------------------------------------------------------------------
# Hosted preview: serve the freelancer's real uploaded site, locked by the DRM script
# --------------------------------------------------------------------------
PREVIEW_EXT = {".html", ".htm", ".css", ".js", ".mjs", ".json", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico",
               ".woff", ".woff2", ".ttf", ".otf", ".txt", ".map", ".webmanifest", ".mp4", ".webm"}
DRM_TAG_RE = re.compile(r"<script[^>]*synera-drm\.js[^>]*>\s*</script>", re.I)


def build_preview(p: dict, data: bytes) -> dict:
    """Unpack the delivery into a static preview folder. Never executes anything; only whitelisted file types are kept."""
    root = PREVIEWS / p["id"]
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    kept = 0
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        names = [i for i in zf.infolist() if not i.is_dir()]
        # if everything sits inside one top-level folder, serve from inside it
        tops = {i.filename.split("/")[0] for i in names if "/" in i.filename}
        loose = [i for i in names if "/" not in i.filename]
        strip = (next(iter(tops)) + "/") if len(tops) == 1 and not loose else ""
        total = 0
        for i in names[:3000]:
            name = i.filename[len(strip):] if strip and i.filename.startswith(strip) else i.filename
            parts = [x for x in name.replace("\\", "/").split("/") if x]
            if not parts or any(x in ("..", ".") or x.startswith(".") or x == "node_modules" for x in parts):
                continue
            if Path(parts[-1]).suffix.lower() not in PREVIEW_EXT or i.file_size > 15 * 1024 * 1024:
                continue
            total += i.file_size
            if total > 60 * 1024 * 1024:
                break
            dest = root.joinpath(*parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(i))
            kept += 1
    except Exception as e:  # corrupt zip
        log.warning("preview build failed: %s", e)
    old = p.get("preview") or {}
    ok = (root / "index.html").exists()
    p["preview"] = {"ok": ok, "files": kept, "token": old.get("token") or secrets.token_hex(12)}
    return p["preview"]


def view(p: dict, role: str = "freelancer") -> dict:
    out = {k: v for k, v in p.items() if k not in ("zip_file", "created_ts", "preview")}
    pv = p.get("preview")
    out["preview"] = {"ok": bool(pv and pv["ok"]), "files": pv["files"] if pv else 0}
    visible = role == "freelancer" or p["status"] in ("submitted", "changes_requested", "paid")
    out["preview_url"] = f"/preview/{p['id']}/{pv['token']}/" if pv and pv["ok"] and visible else None
    out["drm_state"] = current_state(p)
    out["seconds_remaining"] = max(0, int(p["invoice"]["deadline_ts"] - time.time()))
    out["has_deliverable"] = bool(p["zip_file"])
    out["plan_eval"] = plan_eval(p) if role == "freelancer" else None
    out["agreement"] = {k: v for k, v in p["agreement"].items() if k != "clauses"}
    out["money"] = money(p)
    rd = p.get("review_deadline_ts")
    out["review"] = {"days": p["terms"]["review_days"], "seconds_remaining": max(0, int(rd - time.time())) if rd else None,
                     "expired": bool(rd and time.time() > rd and p["status"] == "submitted" and not p["paid"])}
    if role == "client":
        out.pop("plan", None)
    if role == "client" and p["status"] in ("scoped", "audited"):
        out["audit"] = None  # the client only sees verification after the freelancer submits
        out["has_deliverable"] = False
    return out


def hash_fields(f: dict) -> str:
    payload = "|".join([f["freelancer_id"], f["project_id"], str(f["score"]), f["receipt"],
                        f["timestamp"], f["delivery_sha256"], f["prev_hash"]])
    return hashlib.sha256(payload.encode()).hexdigest()


def mint_card(p: dict, receipt: str, ts: str) -> dict:
    prev = "GENESIS"
    mine = [c for c in DB["mints"].values() if c["freelancer_id"] == p["freelancer_id"]]
    if mine:
        prev = max(mine, key=lambda c: c["timestamp"])["hash"]
    fields = {
        "freelancer_id": p["freelancer_id"], "project_id": p["id"], "score": p["audit"]["score"],
        "receipt": receipt, "timestamp": ts, "delivery_sha256": p["audit"]["zip_sha256"], "prev_hash": prev,
    }
    h = hash_fields(fields)
    card = {
        **fields, "hash": h, "freelancer_name": p["freelancer_name"],
        "title": scrub(p["contract"]["title"]), "summary": scrub(p["contract"]["summary"]),
        "stack_tags": [scrub(t) for t in p["contract"]["stack_tags"]],
        "client": "Anonymized client", "invoice_total_inr": money(p)["grand_total"],
        "criteria_passed": f'{p["audit"]["passed"]}/{p["audit"]["total"]}',
        "value_delivered_inr": p["audit"]["value_delivered_inr"],
    }
    DB["mints"][h] = card
    return card


def do_settle(p: dict, method: str, receipt: str, last4: Optional[str] = None) -> dict:
    """Atomically: mark paid, UNLOCK the DRM state, mint the proof card."""
    if p["paid"]:
        return {"project": view(p, "client"), "mint": DB["mints"].get(p["mint_hash"])}
    if not p["audit"]:
        raise HTTPException(409, "Run the spec audit before settlement")
    ts = now_iso()
    m = money(p)
    p["payments"].append({"kind": "final", "amount_inr": m["balance_due"], "payment_id": receipt, "method": method, "last4": last4, "at": ts})
    p["paid"] = {"receipt": receipt, "paid_at": ts, "method": method, "last4": last4, "late_fee_inr": m["late_fee"]}
    log_event(p, "client", "paid", f"INR {m['balance_due']:,} via {method}")
    p["drm_state"] = "UNLOCKED"
    p["status"] = "paid"
    card = mint_card(p, receipt, ts)
    p["mint_hash"] = card["hash"]
    save()
    return {"project": view(p, "client"), "mint": card}


def build_sample_zip() -> None:
    if not DEMO_CLIENT_DIR.exists():
        return
    with zipfile.ZipFile(SAMPLE_ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(DEMO_CLIENT_DIR.iterdir()):
            if f.is_file():
                z.write(f, f.name)


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_: FastAPI):
    load()
    build_sample_zip()
    log.info("Synera ready. Gemini: %s", "on" if GEMINI_KEY else "off (fallback mode)")
    yield


app = FastAPI(title="Synera", version="3.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[PUBLIC_URL] if PUBLIC_URL else ["*"], allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    return resp


@app.get("/api/health")
def health():
    return {"ok": True, "demo": ENABLE_DEMO, "gemini": bool(GEMINI_KEY), "model": _working or (MODEL_PREFS[0] if MODEL_PREFS else None)}


@app.get("/api/ai/status")
def ai_status_endpoint(user: dict = Depends(current_user)):
    """Tells the UI whether Gemini is really connected (and which model answered), or why not."""
    return ai_status()


# ---- auth -----------------------------------------------------------------
@app.post("/api/auth/register")
def register(body: RegisterIn):
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "Enter a valid email address")
    if body.role not in ("freelancer", "client"):
        raise HTTPException(400, "Role must be freelancer or client")
    if email in DB["users"]:
        raise HTTPException(409, "An account with this email already exists")
    prefix = "fr_" if body.role == "freelancer" else "cl_"
    u = add_user(prefix + secrets.token_hex(4), email, body.name.strip(), body.role, body.password)
    return new_session(u)


@app.post("/api/auth/login")
def login(body: LoginIn):
    email = body.email.strip().lower()
    throttle(email)
    u = DB["users"].get(email)
    salt = u["salt"] if u else "00" * 16
    _, h = hash_pw(body.password, salt)
    if not u or not hmac.compare_digest(h, u["pw"]):
        raise HTTPException(401, "Invalid email or password")
    _attempts.pop(email, None)
    return new_session(u)


@app.get("/api/auth/me")
def me(user: dict = Depends(current_user)):
    return public_user(user)


@app.post("/api/auth/logout")
def logout(authorization: Optional[str] = Header(None)):
    if authorization and authorization.lower().startswith("bearer "):
        DB["sessions"].pop(authorization[7:].strip(), None)
        save()
    return {"ok": True}


# ---- projects ---------------------------------------------------------------
@app.post("/api/scope")
def scope(body: ScopeIn, user: dict = Depends(current_user)):
    if user["role"] != "freelancer":
        raise HTTPException(403, "Only freelancers can create projects")
    if not EMAIL_RE.match(body.client_email.strip()):
        raise HTTPException(400, "Enter the client's email address")
    p = create_project(body.chat, user, body.client_email, body.grace_period_hours, body.force_fallback,
                       terms={"advance_pct": body.advance_pct, "revisions_included": body.revisions_included,
                              "review_days": body.review_days, "late_fee_pct_per_week": body.late_fee_pct_per_week,
                              "delivery_days": body.delivery_days},
                       price_inr=body.price_inr)
    return view(p)


@app.get("/api/projects")
def projects(user: dict = Depends(current_user)):
    if user["role"] == "freelancer":
        mine = [p for p in DB["projects"].values() if p["freelancer_id"] == user["id"]]
    else:
        mine = [p for p in DB["projects"].values() if p["client_email"] == user["email"]]
    return [view(p, user["role"]) for p in sorted(mine, key=lambda p: -p["created_ts"])]


@app.get("/api/projects/{pid}")
def project(pid: str, user: dict = Depends(current_user)):
    return view(own_project(pid, user), user["role"])


@app.post("/api/audit/{pid}")
def audit(pid: str, file: Optional[UploadFile] = File(None), use_sample: bool = Query(False),
          user: dict = Depends(current_user)):
    p = own_project(pid, user, "freelancer")
    if p["paid"]:
        raise HTTPException(409, "Project already settled")
    if use_sample:
        if not SAMPLE_ZIP.exists():
            raise HTTPException(500, "Sample deliverable missing")
        data = SAMPLE_ZIP.read_bytes()
    elif file is not None:
        data = file.file.read()
        if len(data) > 25 * 1024 * 1024:
            raise HTTPException(413, "Max 25 MB")
    else:
        raise HTTPException(400, "Upload a .zip or pass use_sample=true")
    p["audit"] = run_audit(p, data)
    p["zip_file"] = f"{pid}.zip"
    (STORAGE / p["zip_file"]).write_bytes(data)
    build_preview(p, data)
    p["status"] = "audited"
    log_event(p, "freelancer", "audit_run", f"score {p['audit']['score']}%, {p['audit']['passed']}/{p['audit']['total']} requirements found")
    save()
    return view(p)


@app.post("/api/projects/{pid}/submit")
def submit(pid: str, user: dict = Depends(current_user)):
    p = own_project(pid, user, "freelancer")
    if p["paid"]:
        raise HTTPException(409, "Project already settled")
    if not p["audit"]:
        raise HTTPException(409, "Run the audit before submitting to the client")
    if p["terms"]["advance_inr"] and not p["funded"]:
        raise HTTPException(409, f"Waiting for the client's advance of INR {p['terms']['advance_inr']:,} before you submit")
    if p.get("pending_quote"):
        raise HTTPException(409, "Quote the client's extra change request before resubmitting")
    p["status"] = "submitted"
    p["feedback"] = None
    p["submitted_at"] = now_iso()
    p["review_deadline_ts"] = time.time() + p["terms"]["review_days"] * 86400
    p["invoice"]["deadline_ts"] = p["review_deadline_ts"]  # preview auto-locks when the review window ends unpaid
    if p["drm_state"] == "KILLED":
        p["drm_state"] = "PREVIEW"
    log_event(p, "freelancer", "submitted", f"review window {p['terms']['review_days']} day(s)")
    save()
    return view(p)


@app.post("/api/projects/{pid}/request-changes")
def request_changes(pid: str, body: ChangesIn, user: dict = Depends(current_user)):
    p = own_project(pid, user, "client")
    if p["paid"]:
        raise HTTPException(409, "Project already settled")
    if p["status"] != "submitted":
        raise HTTPException(409, "There is no submitted delivery to review")
    rv = p["revisions"]
    rv["used"] += 1
    billable = rv["used"] > rv["included"]
    rv["log"].append({"at": now_iso(), "message": body.message.strip(), "billable": billable, "fee_inr": None})
    p["pending_quote"] = billable
    p["status"] = "changes_requested"
    p["review_deadline_ts"] = None
    p["feedback"] = {"message": body.message.strip(), "at": now_iso(), "billable": billable}
    log_event(p, "client", "changes_requested",
              f"revision {rv['used']} of {rv['included']} included" + (" (extra, needs a quote)" if billable else ""))
    save()
    return view(p, "client")


# ---- DRM (the hosted-preview script polls the public GET) --------------------
def demo_guard() -> None:
    if not ENABLE_DEMO:
        raise HTTPException(404, "Demo shortcuts are disabled on this server")


def nocache(content: dict):
    return JSONResponse(content, headers={"Cache-Control": "no-store", "Access-Control-Allow-Origin": "*"})  # public state, readable from the sandboxed preview


@app.get("/api/drm/{pid}")
def drm_get(pid: str):
    p = get_project(pid)
    state = current_state(p)
    inv = p["invoice"]
    msgs = {
        "PREVIEW": "Escrow preview. Settle the invoice to unlock the full delivery.",
        "KILLED": f"Payment of ₹{inv['total_inr']:,} for invoice {inv['number']} is overdue. "
                  "This preview is locked until the invoice is settled.",
        "UNLOCKED": "Paid and settled. Thank you.",
    }
    return nocache({
        "state": state, "message": msgs[state], "amount_inr": inv["total_inr"],
        "invoice_number": inv["number"], "project_title": p["contract"]["title"],
        "seconds_remaining": max(0, int(inv["deadline_ts"] - time.time())),
    })


@app.post("/api/drm/{pid}")
def drm_set(pid: str, body: DrmIn, user: dict = Depends(current_user)):
    p = own_project(pid, user, "freelancer")
    state = body.state.upper()
    if p["paid"]:
        raise HTTPException(409, "Kill-switch permanently disarmed after settlement")
    if state == "UNLOCKED":
        raise HTTPException(400, "UNLOCKED is only reachable through settlement")
    if state not in ("PREVIEW", "KILLED"):
        raise HTTPException(400, "State must be PREVIEW or KILLED")
    if state == "PREVIEW" and time.time() > p["invoice"]["deadline_ts"]:
        p["invoice"]["deadline_ts"] = time.time() + 3600  # re-arming after expiry grants 1h grace
    p["drm_state"] = state
    save()
    return view(p)


# ---- Sandbox payment gateway ------------------------------------------------
# Mirrors Razorpay's order -> checkout -> signature-verify flow. The "gateway" signs
# (order_id|payment_id) with a secret; the merchant side only unlocks after the HMAC
# checks out, so a forged or replayed call cannot settle an invoice. No real money moves.
def gw_secret() -> bytes:
    env = os.getenv("GATEWAY_SECRET")
    if env:
        return env.encode()
    if "gateway_secret" not in DB:
        DB["gateway_secret"] = secrets.token_hex(32)
        save()
    return DB["gateway_secret"].encode()


def gw_sign(order_id: str, payment_id: str) -> str:
    return hmac.new(gw_secret(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()


class CheckoutIn(BaseModel):
    order_id: str
    method: str
    vpa: Optional[str] = None
    card_number: Optional[str] = None
    expiry: Optional[str] = None
    cvv: Optional[str] = None


class VerifyIn(BaseModel):
    order_id: str
    payment_id: str
    signature: str


def gateway_validate(body: "CheckoutIn"):
    """Sandbox instrument check shared by project and subscription payments."""
    method, last4, ok, detail = body.method.lower(), None, False, ""
    if method == "upi":
        vpa = (body.vpa or "").strip().lower()
        if not re.fullmatch(r"[a-z0-9._\-]{2,}@[a-z]{2,}", vpa):
            detail = "Enter a valid UPI ID, for example success@razorpay"
        elif vpa.startswith("failure@"):
            detail = "Payment declined by the bank (sandbox failure UPI ID)"
        elif vpa.startswith("success@"):
            ok = True
        else:
            detail = "Sandbox accepts only success@... or failure@... UPI IDs"
    elif method == "card":
        num = re.sub(r"\D", "", body.card_number or "")
        last4 = num[-4:] or None  # full card numbers are never stored
        if num == "4111111111111111":
            ok = True
        elif num == "4000000000000002":
            detail = "Card declined (sandbox decline card)"
        else:
            detail = "Sandbox accepts test cards 4111 1111 1111 1111 (success) or 4000 0000 0000 0002 (decline)"
    else:
        raise HTTPException(400, "Method must be upi or card")
    if not ok:
        raise HTTPException(402, detail)
    return method, last4


@app.post("/api/pay/{pid}/order")
def pay_order(pid: str, body: OrderIn = OrderIn(), user: dict = Depends(current_user)):
    p = own_project(pid, user, "client")
    if p["paid"]:
        raise HTTPException(409, "Invoice already settled")
    if not p["agreement"]["client_signed_at"]:
        raise HTTPException(409, "Review and sign the agreement before paying")
    m = money(p)
    if body.kind == "advance":
        if not p["terms"]["advance_inr"] or p["funded"]:
            raise HTTPException(409, "No advance is due on this project")
        amount = p["terms"]["advance_inr"]
    else:
        if p["status"] != "submitted":
            raise HTTPException(409, "The freelancer has not submitted a delivery for payment yet")
        amount = m["balance_due"]
    oid = "order_" + secrets.token_hex(7)
    DB["orders"][oid] = {"project_id": pid, "kind": "advance" if body.kind == "advance" else "final", "amount_paise": amount * 100,
                         "currency": "INR", "status": "created", "created_at": now_iso()}
    save()
    return {"order_id": oid, "amount_paise": amount * 100, "amount_inr": amount, "kind": DB["orders"][oid]["kind"],
            "currency": "INR", "invoice_number": p["invoice"]["number"], "sandbox": True}


@app.post("/api/pay/{pid}/checkout")
def pay_checkout(pid: str, body: CheckoutIn, user: dict = Depends(current_user)):
    """Gateway side: validates the (test) instrument and returns a signed payment confirmation."""
    own_project(pid, user, "client")
    order = DB["orders"].get(body.order_id)
    if not order or order["project_id"] != pid:
        raise HTTPException(404, "Unknown order")
    if order["status"] == "paid":
        raise HTTPException(409, "Order already paid")
    method, last4 = gateway_validate(body)
    pay_id = "pay_" + secrets.token_hex(7)
    DB["payments"][pay_id] = {"order_id": body.order_id, "method": method, "last4": last4, "created_at": now_iso()}
    save()
    return {"order_id": body.order_id, "payment_id": pay_id, "signature": gw_sign(body.order_id, pay_id)}


@app.post("/api/pay/{pid}/verify")
def pay_verify(pid: str, body: VerifyIn, user: dict = Depends(current_user)):
    """Merchant side: only a valid gateway signature settles the invoice."""
    p = own_project(pid, user, "client")
    if p["paid"]:
        return {"project": view(p, "client"), "mint": DB["mints"].get(p["mint_hash"])}
    order = DB["orders"].get(body.order_id)
    pay = DB["payments"].get(body.payment_id)
    if not order or order["project_id"] != pid or not pay or pay["order_id"] != body.order_id:
        raise HTTPException(400, "Unknown order or payment")
    if not hmac.compare_digest(gw_sign(body.order_id, body.payment_id), body.signature):
        raise HTTPException(400, "Invalid payment signature")
    if order.get("kind") == "advance":
        if order["status"] != "paid":
            order["status"] = "paid"
            p["payments"].append({"kind": "advance", "amount_inr": order["amount_paise"] // 100, "payment_id": body.payment_id,
                                  "method": pay["method"], "last4": pay.get("last4"), "at": now_iso()})
            p["funded"] = True
            log_event(p, "client", "advance_paid", f"INR {order['amount_paise'] // 100:,} secured before delivery")
            save()
        return {"project": view(p, "client"), "mint": None, "kind": "advance"}
    if order["amount_paise"] // 100 != money(p)["balance_due"]:
        raise HTTPException(409, "The amount due changed. Start the payment again.")
    order["status"] = "paid"
    return do_settle(p, pay["method"], body.payment_id, pay.get("last4"))


@app.post("/api/pay/{pid}/settle")
def settle(pid: str, body: SettleIn = SettleIn(), user: dict = Depends(current_user)):
    """Dev-only shortcut. Disabled unless ALLOW_MOCK_SETTLE=1 so nobody can bypass the gateway."""
    if not ALLOW_MOCK_SETTLE:
        raise HTTPException(403, "Manual settlement is disabled. Pay through the checkout.")
    return do_settle(own_project(pid, user, "client"), body.method, "rcpt_" + secrets.token_hex(6))


@app.get("/api/download/{pid}")
def download(pid: str, user: dict = Depends(current_user)):
    p = own_project(pid, user, "client")
    if p["drm_state"] != "UNLOCKED" or not p["paid"]:
        raise HTTPException(402, "Settle the escrow invoice to download the source")
    f = STORAGE / (p["zip_file"] or "")
    if not f.exists():
        raise HTTPException(404, "No deliverable uploaded")
    return FileResponse(f, filename=f"{p['contract']['title'].replace(' ', '_')}_source.zip",
                        media_type="application/zip")


# ---- public proof-of-work ---------------------------------------------------
@app.get("/api/folio/{freelancer_id}")
def folio(freelancer_id: str):
    cards = sorted((c for c in DB["mints"].values() if c["freelancer_id"] == freelancer_id),
                   key=lambda c: c["timestamp"], reverse=True)
    avg = round(sum(c["score"] for c in cards) / len(cards)) if cards else 0
    name = cards[0]["freelancer_name"] if cards else next(
        (u["name"] for u in DB["users"].values() if u["id"] == freelancer_id), None)
    return {"freelancer_id": freelancer_id, "freelancer_name": name,
            "stats": {"verified_deliveries": len(cards), "avg_score": avg}, "cards": cards}


@app.get("/api/verify/{h}")
def verify(h: str):
    card = DB["mints"].get(h)
    if not card:
        raise HTTPException(404, "No delivery with that hash")
    recomputed = hash_fields(card)
    return {"valid": recomputed == h, "recomputed": recomputed, "card": card}


@app.get("/verify/{h}", response_class=HTMLResponse)
def verify_page(h: str):
    card = DB["mints"].get(h)
    if not card:
        return HTMLResponse("<h1 style='font-family:sans-serif'>No delivery with that hash</h1>", 404)
    ok = hash_fields(card) == h
    e = html.escape
    rows = "".join(f"<tr><td>{e(k)}</td><td><code>{e(str(card[k]))}</code></td></tr>" for k in
                   ("freelancer_id", "project_id", "score", "receipt", "timestamp", "delivery_sha256", "prev_hash"))
    color, label = ("#22c55e", "VALID: hash recomputed and matches") if ok else ("#ef4444", "INVALID: record was altered")
    return HTMLResponse(f"""<!doctype html><meta charset=utf-8><title>Synera verify</title>
<body style="font-family:system-ui;background:#0b0916;color:#ede9fe;max-width:760px;margin:40px auto;padding:0 16px">
<h1>Synera Verified Delivery</h1><h2 style="color:{color}">{label}</h2>
<p><b>{e(card['title'])}</b> by {e(card['freelancer_name'])} · {e(str(card['criteria_passed']))} criteria · {card['score']}% spec-presence verified</p>
<table cellpadding=8 style="border-collapse:collapse;width:100%">{rows}</table>
<p style="word-break:break-all">SHA-256: <code>{e(h)}</code></p></body>""")


# ---- demo helpers (freelancer only) -------------------------------------------
@app.post("/api/demo/seed")
def demo_seed(user: dict = Depends(current_user)):
    demo_guard()
    if user["role"] != "freelancer":
        raise HTTPException(403, "Only freelancers can create projects")
    p = create_project(DEMO_CHAT, user, DEMO_CLIENT["email"], 72, force_fallback=True)
    data = SAMPLE_ZIP.read_bytes()
    p["audit"] = run_audit(p, data)
    p["zip_file"] = f"{p['id']}.zip"
    (STORAGE / p["zip_file"]).write_bytes(data)
    build_preview(p, data)
    ts = now_iso()
    p["agreement"]["client_signed_at"] = ts
    log_event(p, "client", "agreement_signed", "demo data")
    p["payments"].append({"kind": "advance", "amount_inr": p["terms"]["advance_inr"], "payment_id": "pay_demo_" + secrets.token_hex(4),
                          "method": "upi", "last4": None, "at": ts})
    p["funded"] = True
    log_event(p, "client", "advance_paid", f"INR {p['terms']['advance_inr']:,} (demo)")
    log_event(p, "freelancer", "audit_run", f"score {p['audit']['score']}%")
    p["status"] = "submitted"
    p["submitted_at"] = ts
    p["review_deadline_ts"] = time.time() + p["terms"]["review_days"] * 86400
    p["invoice"]["deadline_ts"] = p["review_deadline_ts"]
    log_event(p, "freelancer", "submitted", "demo data")
    save()
    return view(p)


@app.post("/api/demo/{pid}/expire")
def demo_expire(pid: str, user: dict = Depends(current_user)):
    demo_guard()
    p = own_project(pid, user, "freelancer")
    if p["paid"]:
        raise HTTPException(409, "Already settled")
    p["invoice"]["deadline_ts"] = time.time() - 1
    save()
    return view(p)


@app.post("/api/demo/reset")
def demo_reset(user: dict = Depends(current_user)):
    if user["role"] != "freelancer":
        raise HTTPException(403, "Only freelancers can reset demo data")
    demo_guard()
    mine = [pid for pid, p in DB["projects"].items() if p["freelancer_id"] == user["id"]]  # only your own projects
    for pid in mine:
        for h in [h for h, c in DB["mints"].items() if c["project_id"] == pid]:
            del DB["mints"][h]
        for oid in [o for o, x in DB["orders"].items() if x.get("project_id") == pid]:
            for payid in [i for i, pay in DB["payments"].items() if pay["order_id"] == oid]:
                del DB["payments"][payid]
            del DB["orders"][oid]
        del DB["projects"][pid]
        shutil.rmtree(PREVIEWS / pid, ignore_errors=True)
    save()
    return {"ok": True, "removed": len(mine)}



# ---- agreement, quotes, reminders, evidence ---------------------------------
@app.get("/api/projects/{pid}/agreement")
def agreement(pid: str, format: str = Query("json"), user: dict = Depends(current_user)):
    p = own_project(pid, user)
    if format == "html":
        return HTMLResponse(agreement_html(p))
    ok = hashlib.sha256(agreement_text(p).encode()).hexdigest() == p["agreement"]["sha256"]
    return {**{k: v for k, v in p["agreement"].items() if k != "clauses"}, "clauses": [{"title": h, "text": b} for h, b in agreement_clauses(p)],
            "invoice_number": p["invoice"]["number"], "integrity_ok": ok}


@app.post("/api/projects/{pid}/sign")
def sign_agreement(pid: str, user: dict = Depends(current_user)):
    p = own_project(pid, user, "client")
    if not p["agreement"]["client_signed_at"]:
        p["agreement"]["client_signed_at"] = now_iso()
        p["agreement"]["client_signed_by"] = f"{user['name']} <{user['email']}>"
        p["client_name"] = user["name"]
        log_event(p, "client", "agreement_signed", f"{user['name']} accepted agreement {p['agreement']['sha256'][:12]}")
        save()
    return view(p, "client")


@app.post("/api/projects/{pid}/change-quote")
def change_quote(pid: str, body: QuoteIn, user: dict = Depends(current_user)):
    p = own_project(pid, user, "freelancer")
    if not p.get("pending_quote"):
        raise HTTPException(409, "There is no extra change request waiting for a quote")
    n = p["revisions"]["used"]
    entry = p["revisions"]["log"][-1]
    entry["fee_inr"] = body.fee_inr
    if body.fee_inr > 0:
        p["extras"].append({"id": f"X{len(p['extras']) + 1}", "label": f"Extra change request #{n}" + (f": {body.note}" if body.note else ""),
                            "amount_inr": body.fee_inr, "at": now_iso()})
    p["pending_quote"] = False
    log_event(p, "freelancer", "quote_set", f"INR {body.fee_inr:,}" if body.fee_inr else "waived")
    save()
    return view(p)


@app.post("/api/projects/{pid}/remind")
def remind(pid: str, request: Request, user: dict = Depends(current_user)):
    p = own_project(pid, user, "freelancer")
    if p["paid"] or p["status"] != "submitted":
        raise HTTPException(409, "Reminders apply to a submitted, unpaid delivery")
    level = min(len(p["reminders"]) + 1, 3)
    if level == 3:
        require_pro(user, "The final-notice generator")
    base = PUBLIC_URL or str(request.base_url).rstrip("/")
    msg = reminder_message(p, level, base)
    p["reminders"].append({"at": now_iso(), "level": level, "subject": msg["subject"]})
    log_event(p, "freelancer", "reminder_sent", f"level {level}")
    save()
    return msg


@app.get("/api/projects/{pid}/evidence")
def evidence(pid: str, format: str = Query("json"), user: dict = Depends(current_user)):
    p = own_project(pid, user, "freelancer")
    require_pro(user, "The evidence pack")
    log_event(p, "freelancer", "evidence_exported", format)
    save()
    pk = evidence_pack(p)
    if format == "html":
        return HTMLResponse(evidence_html(pk))
    return pk


@app.get("/api/payments/verify/{payment_id}")
def payment_check(payment_id: str):
    """Public: confirm a payment reference is real. A screenshot is never proof."""
    pay = DB["payments"].get(payment_id.strip())
    order = DB["orders"].get(pay["order_id"]) if pay else None
    if not pay or not order or order.get("status") != "paid":
        return {"verified": False, "message": "No settled payment has this reference."}
    inv = None
    if order.get("project_id") and order["project_id"] in DB["projects"]:
        inv = DB["projects"][order["project_id"]]["invoice"]["number"]
    return {"verified": True, "amount_inr": order["amount_paise"] // 100, "kind": order.get("kind", "final"),
            "invoice_number": inv, "method": pay["method"], "paid_at": pay["created_at"],
            "message": "This payment was confirmed by the Synera gateway signature."}


# ---- invoices ---------------------------------------------------------------
class BizIn(BaseModel):
    business_name: str = Field("", max_length=80)
    address: str = Field("", max_length=200)
    phone: str = Field("", max_length=20)
    gstin: str = Field("", max_length=15)
    pan: str = Field("", max_length=10)
    upi_id: str = Field("", max_length=60)
    note: str = Field("", max_length=300)


GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
PAN_RE = re.compile(r"^[A-Z]{5}\d{4}[A-Z]$")


def _fdate(iso_or_ts) -> str:
    try:
        d = datetime.fromtimestamp(iso_or_ts, timezone.utc) if isinstance(iso_or_ts, (int, float)) else datetime.fromisoformat(str(iso_or_ts))
        return (d.astimezone(timezone(timedelta(hours=5, minutes=30)))).strftime("%d %b %Y")
    except Exception:
        return str(iso_or_ts)[:10]


def invoice_status(p: dict) -> str:
    m = money(p)
    if p["paid"] or (m["grand_total"] > 0 and m["balance_due"] == 0 and m["received"] > 0):
        return "PAID"
    rd = p.get("review_deadline_ts")
    if rd and time.time() > rd and p["status"] == "submitted":
        return "OVERDUE"
    if m["received"] > 0:
        return "PARTIALLY PAID"
    if not p["invoice"].get("sent_at") and p["status"] == "scoped":
        return "DRAFT"
    return "DUE"


def invoice_visible_to_client(p: dict) -> bool:
    return bool(p["invoice"].get("sent_at") or p["payments"] or p["status"] in ("submitted", "changes_requested", "paid"))


def invoice_doc(p: dict, base_url: str = "") -> dict:
    m = money(p)
    inv = p["invoice"]
    fu = next((u for u in DB["users"].values() if u["id"] == p["freelancer_id"]), {})
    biz = fu.get("biz") or {}
    client_u = DB["users"].get(p["client_email"])
    items = [{"label": it["label"], "amount": it["amount"]} for it in p["breakdown"]]
    items += [{"label": e["label"], "amount": e["amount_inr"], "note": "Extra"} for e in p["extras"]]
    if m["late_fee"]:
        items.append({"label": f"Late payment fee ({p['terms']['late_fee_pct_per_week']}% per week, max 10%)", "amount": m["late_fee"], "note": "Late fee"})
    status = invoice_status(p)
    rd = p.get("review_deadline_ts")
    due = "Paid " + _fdate(p["paid"]["paid_at"]) if p["paid"] else (_fdate(rd) if rd else "On acceptance")
    issued = _fdate(inv.get("sent_at") or inv["created_at"])
    frm = {"name": p["freelancer_name"], "email": fu.get("email", ""), "business_name": biz.get("business_name", ""),
           "address": biz.get("address", ""), "phone": biz.get("phone", ""), "gstin": biz.get("gstin", ""), "pan": biz.get("pan", ""),
           "upi_id": biz.get("upi_id", "")}
    to = {"name": (client_u or {}).get("name") or p["client_name"] or "Client", "email": p["client_email"]}
    pays = [{"kind": x["kind"], "amount": x["amount_inr"], "ref": x["payment_id"], "method": x["method"].upper() if x.get("method") else "",
             "at": _fdate(x["at"])} for x in p["payments"]]
    t = p["terms"]
    terms = (f"Payable on acceptance of the delivery. The review window is {t['review_days']} day(s); if the client does not respond the delivery is treated as accepted. "
             f"Late payment adds {t['late_fee_pct_per_week']}% per week, capped at 10%. Source files transfer to the client on payment in full. "
             f"Governed by the signed agreement (sha256 {p['agreement']['sha256'][:12]}…)." + (" " + biz["note"] if biz.get("note") else ""))
    totals = [("Subtotal", inr_fmt(m["base"] + m["extras"]), False)]
    if m["late_fee"]:
        totals.append(("Late fee", inr_fmt(m["late_fee"]), False))
    totals += [("Total", inr_fmt(m["grand_total"]), False), ("Received", "-" + inr_fmt(m["received"]), False), ("Balance due", inr_fmt(m["balance_due"]), True)]
    # The hash covers the commercial terms only, so a copy stays verifiable as status and payments change.
    core = {"n": inv["number"], "from": [frm["name"], frm["email"]], "to": to["email"], "items": [[i["label"], i["amount"]] for i in items], "issued": issued}
    h = hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()
    base = PUBLIC_URL or base_url.rstrip("/")
    return {"number": inv["number"], "project_id": p["id"], "project_title": p["contract"]["title"], "status": status, "issued": issued, "due": due,
            "from": frm, "to": to, "items": items, "totals": totals, "payments": pays, "terms": terms, "sent": bool(inv.get("sent_at")),
            "amounts": {"total": m["grand_total"], "received": m["received"], "balance": m["balance_due"]},
            "hash": h, "verify_url": f"{base}/verify/invoice/{inv['number']}?h={h[:16]}",
            "generated": datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%d %b %Y %H:%M IST")}


def inr_fmt(n) -> str:
    return "₹" + format(int(round(n or 0)), ",")


def invoice_html(d: dict) -> str:
    e = html.escape
    rows = "".join(f"<tr><td>{e(i['label'])}</td><td class=r>{inr_fmt(i['amount'])}</td></tr>" for i in d["items"])
    tot = "".join(f"<tr class={'b' if s else ''}><td class=r>{e(k)}</td><td class=r>{e(v)}</td></tr>" for k, v, s in d["totals"])
    pay = "".join(f"<li>{e(x['kind'].title())} {inr_fmt(x['amount'])} on {e(x['at'])} via {e(x['method'])}. Ref <code>{e(x['ref'])}</code></li>" for x in d["payments"]) or "<li>No payment received yet.</li>"
    f, t = d["from"], d["to"]
    gst = f"GSTIN {e(f['gstin'])}" if f["gstin"] else "Not registered under GST. No GST charged."
    pan = f"<br>PAN {e(f['pan'])}" if f["pan"] else ""
    upi = f"<br>UPI {e(f['upi_id'])}" if f["upi_id"] else ""
    return (f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Invoice {e(d['number'])}</title>"
            "<style>body{font:14px/1.5 system-ui,sans-serif;max-width:760px;margin:24px auto;padding:0 16px;color:#111}"
            "header{background:#111;color:#fff;padding:20px 24px;border-radius:12px;display:flex;justify-content:space-between}h1{margin:0;font-size:26px}"
            ".g{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:20px 0}.m{color:#6b7280;font-size:12px;text-transform:uppercase;letter-spacing:.06em}"
            "table{width:100%;border-collapse:collapse}td{padding:8px 10px;border-bottom:1px solid #e5e7eb}.r{text-align:right}.b td{font-weight:700;font-size:16px}"
            ".st{display:inline-block;border:2px solid #111;padding:2px 10px;border-radius:6px;font-weight:700}code{font-size:12px}"
            "@media print{body{margin:0}}</style>"
            f"<header><div><h1>INVOICE</h1>{e(d['number'])}</div><div style=text-align:right><b>{e(f['name'])}</b><br>via Synera</div></header>"
            f"<div class=g><div><div class=m>Billed to</div><b>{e(t['name'])}</b><br>{e(t['email'])}</div>"
            f"<div><div class=m>From</div><b>{e(f['name'])}</b>{('<br>' + e(f['business_name'])) if f['business_name'] else ''}"
            f"{('<br>' + e(f['address'])) if f['address'] else ''}<br>{e(f['email'])}<br>{gst}{pan}{upi}</div></div>"
            f"<p>Project <b>{e(d['project_title'])}</b> · Issued {e(d['issued'])} · Due {e(d['due'])} · <span class=st>{e(d['status'])}</span></p>"
            f"<table><tr><td class=m>Description</td><td class='m r'>Amount</td></tr>{rows}</table><table style='width:55%;margin-left:auto'>{tot}</table>"
            f"<h3>Payments received</h3><ul>{pay}</ul><p class=m>Terms</p><p>{e(d['terms'])}</p>"
            f"<p>Verify this invoice: <a href='{e(d['verify_url'])}'>{e(d['verify_url'])}</a><br><code>hash {d['hash'][:40]}…</code></p>"
            f"<p class=m>Generated by Synera · {e(d['generated'])}</p><script>if(location.search.includes('print'))print()</script>")


def _invoice_access(pid: str, user: dict) -> dict:
    p = own_project(pid, user)
    if user["role"] == "client" and not invoice_visible_to_client(p):
        raise HTTPException(403, "The freelancer has not sent this invoice yet")
    return p


@app.get("/api/profile/business")
def get_biz(user: dict = Depends(current_user)):
    if user["role"] != "freelancer":
        raise HTTPException(403, "Billing details are for freelancers")
    return {"name": user["name"], "email": user["email"], **(user.get("biz") or {})}


@app.put("/api/profile/business")
def set_biz(body: BizIn, user: dict = Depends(current_user)):
    if user["role"] != "freelancer":
        raise HTTPException(403, "Billing details are for freelancers")
    b = {k: v.strip() for k, v in body.model_dump().items()}
    b["gstin"], b["pan"] = b["gstin"].upper(), b["pan"].upper()
    if b["gstin"] and not GSTIN_RE.match(b["gstin"]):
        raise HTTPException(400, "That GSTIN does not look right. It has 15 characters, like 36ABCDE1234F1Z5. Leave it blank if you are not GST-registered.")
    if b["pan"] and not PAN_RE.match(b["pan"]):
        raise HTTPException(400, "That PAN does not look right. It has 10 characters, like ABCDE1234F. You can leave it blank.")
    if b["upi_id"] and not re.match(r"^[\w.\-]{2,}@[A-Za-z]{2,}$", b["upi_id"]):
        raise HTTPException(400, "Enter a UPI ID like name@bank, or leave it blank")
    user["biz"] = b
    save()
    return b


@app.get("/api/projects/{pid}/invoice")
def get_invoice(pid: str, request: Request, user: dict = Depends(current_user)):
    p = _invoice_access(pid, user)
    return invoice_doc(p, str(request.base_url))


@app.get("/api/projects/{pid}/invoice/file")
def invoice_file(pid: str, request: Request, format: str = Query("pdf"), user: dict = Depends(current_user)):
    p = _invoice_access(pid, user)
    d = invoice_doc(p, str(request.base_url))
    import invoicing
    if format == "html":
        return HTMLResponse(invoice_html(d))
    if format == "png":
        return Response(invoicing.render_png(d), media_type="image/png")
    if format == "pdf":
        return Response(invoicing.render_pdf(d), media_type="application/pdf")
    raise HTTPException(400, "Format must be pdf, png or html")


@app.post("/api/projects/{pid}/invoice/send")
def send_invoice(pid: str, request: Request, user: dict = Depends(current_user)):
    p = own_project(pid, user, "freelancer")
    first = not p["invoice"].get("sent_at")
    p["invoice"].setdefault("sent_at", now_iso())
    if first:
        log_event(p, "freelancer", "invoice_sent", p["invoice"]["number"])
    save()
    d = invoice_doc(p, str(request.base_url))
    name = (d["to"]["name"] or "there").split()[0]
    msg = (f"Hi {name}, here is invoice {d['number']} for {d['project_title']}: total {inr_fmt(d['amounts']['total'])}, "
           f"balance due {inr_fmt(d['amounts']['balance'])}. You can view, pay and download it (PDF or image) in your Synera client portal "
           f"with {p['client_email']}. Verify it anytime: {d['verify_url']}")
    return {"ok": True, "message": msg, "invoice": d}


@app.get("/api/invoices")
def list_invoices(request: Request, user: dict = Depends(current_user)):
    """Every invoice the caller may see: the freelancer's own records, or what a client has been sent."""
    rows = []
    for p in DB["projects"].values():
        if user["role"] == "freelancer" and p["freelancer_id"] != user["id"]:
            continue
        if user["role"] == "client" and (p["client_email"] != user["email"] or not invoice_visible_to_client(p)):
            continue
        d = invoice_doc(p, str(request.base_url))
        rows.append({"project_id": p["id"], "number": d["number"], "title": d["project_title"], "party": d["to"]["name"] if user["role"] == "freelancer" else d["from"]["name"],
                     "status": d["status"], "issued": d["issued"], "total": d["amounts"]["total"], "received": d["amounts"]["received"],
                     "balance": d["amounts"]["balance"], "created": p["created_ts"]})
    rows.sort(key=lambda r: -r["created"])
    return rows


def _find_invoice(number: str) -> Optional[dict]:
    return next((p for p in DB["projects"].values() if p["invoice"]["number"] == number.strip().upper()), None)


@app.get("/api/invoices/verify/{number}")
def verify_invoice(number: str, h: str = ""):
    """Public check. Returns only what a payer needs to trust a bill; no email addresses or contract text."""
    p = _find_invoice(number)
    if not p:
        return {"found": False, "message": "No invoice has this number."}
    d = invoice_doc(p)
    matches = bool(h) and d["hash"].startswith(h.lower())
    return {"found": True, "number": d["number"], "status": d["status"], "issued": d["issued"], "issued_by": d["from"]["name"],
            "billed_to": d["to"]["name"], "project": d["project_title"], "total_inr": d["amounts"]["total"], "received_inr": d["amounts"]["received"],
            "balance_inr": d["amounts"]["balance"], "copy_matches": matches if h else None,
            "payments": [{"kind": x["kind"], "amount_inr": x["amount"], "ref": x["ref"], "at": x["at"]} for x in d["payments"]],
            "message": ("This copy matches the invoice on record." if matches else
                        ("This copy was changed or issued before the latest amendment. Use the live figures below." if h else "Invoice found."))}


@app.get("/verify/invoice/{number}")
def verify_invoice_page(number: str, h: str = ""):
    r = verify_invoice(number, h)
    e = html.escape
    if not r["found"]:
        body = f"<h1>Invoice not found</h1><p>{e(r['message'])}</p>"
    else:
        ok = r["copy_matches"]
        badge = {True: ("#16824a", "✓ Genuine copy"), False: ("#b46e0a", "⚠ Copy differs from record"), None: ("#111", "Invoice on record")}[ok]
        pay = "".join(f"<li>{e(x['kind'].title())} ₹{x['amount_inr']:,} on {e(x['at'])}. Ref <code>{e(x['ref'])}</code></li>" for x in r["payments"]) or "<li>No payment yet.</li>"
        body = (f"<div class=b style='background:{badge[0]}'>{badge[1]}</div><h1>{e(r['number'])}</h1><p>{e(r['message'])}</p>"
                f"<table><tr><td>Issued by</td><td><b>{e(r['issued_by'])}</b></td></tr><tr><td>Billed to</td><td>{e(r['billed_to'])}</td></tr>"
                f"<tr><td>Project</td><td>{e(r['project'])}</td></tr><tr><td>Status</td><td><b>{e(r['status'])}</b></td></tr>"
                f"<tr><td>Total</td><td>₹{r['total_inr']:,}</td></tr><tr><td>Received</td><td>₹{r['received_inr']:,}</td></tr>"
                f"<tr><td>Balance</td><td><b>₹{r['balance_inr']:,}</b></td></tr></table><h3>Payments</h3><ul>{pay}</ul>"
                "<p style='color:#6b7280;font-size:12px'>Payment references can be checked at /api/payments/verify/&lt;reference&gt;. A screenshot is never proof.</p>")
    return HTMLResponse("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Verify invoice | Synera</title>"
                        "<style>body{font:15px/1.5 system-ui,sans-serif;max-width:560px;margin:32px auto;padding:0 16px;color:#111}"
                        ".b{color:#fff;padding:8px 14px;border-radius:8px;display:inline-block;font-weight:700}table{width:100%;border-collapse:collapse}"
                        "td{padding:8px 4px;border-bottom:1px solid #e5e7eb}code{font-size:12px}</style>" + body + "<p><b>Synera</b></p>")


# ---- dashboard ---------------------------------------------------------------
def _month(iso: str) -> str:
    return iso[:7]


@app.get("/api/dashboard")
def dashboard(user: dict = Depends(current_user)):
    if user["role"] != "freelancer":
        raise HTTPException(403, "Dashboard is for freelancers")
    mine = sorted((p for p in DB["projects"].values() if p["freelancer_id"] == user["id"]), key=lambda p: -p["created_ts"])
    rows, monthly, clients = [], {}, {}
    earned = awaiting = in_progress = overdue = 0
    scores = []
    for p in mine:
        m = money(p)
        status = p["status"]
        expired = bool(p.get("review_deadline_ts") and time.time() > p["review_deadline_ts"] and status == "submitted" and not p["paid"])
        if p["audit"]:
            scores.append(p["audit"]["score"])
        for x in p["payments"]:
            monthly[_month(x["at"])] = monthly.get(_month(x["at"]), 0) + x["amount_inr"]
        earned += m["received"]
        if not p["paid"]:
            if status == "submitted":
                awaiting += m["balance_due"]
                if expired:
                    overdue += m["balance_due"]
            else:
                in_progress += m["balance_due"]
        days_to_pay = None
        if p["paid"] and p.get("submitted_at"):
            d = datetime.fromisoformat(p["paid"]["paid_at"]) - datetime.fromisoformat(p["submitted_at"])
            days_to_pay = round(d.total_seconds() / 86400, 1)
        rows.append({"id": p["id"], "title": p["contract"]["title"], "client": p["client_name"], "client_email": p["client_email"],
                     "status": status, "invoice": p["invoice"]["number"], "total_inr": m["grand_total"], "received_inr": m["received"],
                     "outstanding_inr": m["balance_due"] if not p["paid"] else 0, "score": p["audit"]["score"] if p["audit"] else None,
                     "created_at": p["invoice"]["created_at"], "paid_at": p["paid"]["paid_at"] if p["paid"] else None,
                     "days_to_pay": days_to_pay, "revisions_used": p["revisions"]["used"], "extras_inr": m["extras"], "overdue": expired,
                     "funded": p["funded"]})
        c = clients.setdefault(p["client_email"], {"client": p["client_name"], "email": p["client_email"], "projects": 0,
                                                    "paid_projects": 0, "total_paid_inr": 0, "days": [], "overdue": 0})
        c["projects"] += 1
        c["total_paid_inr"] += m["received"]
        if p["paid"]:
            c["paid_projects"] += 1
        if days_to_pay is not None:
            c["days"].append(days_to_pay)
        if expired:
            c["overdue"] += 1
    now = datetime.now(timezone.utc)
    months = []
    for i in range(5, -1, -1):
        y, mth = now.year, now.month - i
        while mth <= 0:
            mth += 12; y -= 1
        key = f"{y}-{mth:02d}"
        months.append({"month": key, "earned_inr": monthly.get(key, 0)})
    cl = []
    for c in clients.values():
        avg = round(sum(c["days"]) / len(c["days"]), 1) if c["days"] else None
        label = "Overdue" if c["overdue"] else "Pays promptly" if avg is not None and avg <= 3 else "Pays slowly" if avg is not None else "New client"
        cl.append({k: v for k, v in c.items() if k != "days"} | {"avg_days_to_pay": avg, "label": label})
    plan = effective_plan(user)
    active = sum(1 for p in mine if not p["paid"])
    return {
        "totals": {"earned_inr": earned, "awaiting_inr": awaiting, "in_progress_inr": in_progress, "overdue_inr": overdue,
                   "projects": len(mine), "completed": sum(1 for p in mine if p["paid"]), "active": active,
                   "avg_score": round(sum(scores) / len(scores)) if scores else None},
        "monthly": months, "projects": rows, "clients": sorted(cl, key=lambda c: -c["total_paid_inr"]),
        "plan": {"id": plan, "name": PLANS[plan]["name"], "active_projects": active, "limit": PLANS[plan]["max_active"],
                 "renews": user.get("plan_renews") if plan != "free" else None},
    }


@app.get("/api/dashboard/export.csv")
def dashboard_csv(user: dict = Depends(current_user)):
    if user["role"] != "freelancer":
        raise HTTPException(403, "Freelancers only")
    require_pro(user, "CSV export")
    import csv
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["invoice", "project", "client", "status", "total_inr", "received_inr", "outstanding_inr", "score", "created", "paid_at"])
    for r in dashboard(user)["projects"]:
        w.writerow([r["invoice"], r["title"], r["client"], r["status"], r["total_inr"], r["received_inr"], r["outstanding_inr"],
                    r["score"] if r["score"] is not None else "", r["created_at"], r["paid_at"] or ""])
    return Response(buf.getvalue(), media_type="text/csv", headers={"content-disposition": "attachment; filename=synera_earnings.csv"})


# ---- subscription -------------------------------------------------------------
@app.get("/api/plans")
def plans():
    return PLANS


@app.get("/api/subscription")
def subscription(user: dict = Depends(current_user)):
    pl = effective_plan(user)
    return {"plan": pl, "name": PLANS[pl]["name"], "renews": user.get("plan_renews") if pl != "free" else None,
            "cancelled": bool(user.get("plan_cancelled")), "billing": user.get("billing", [])[-10:], "plans": PLANS}


@app.post("/api/subscription/order")
def sub_order(body: SubOrderIn, user: dict = Depends(current_user)):
    if user["role"] != "freelancer":
        raise HTTPException(403, "Subscriptions are for freelancers")
    if body.plan != "pro" or body.billing not in ("monthly", "yearly"):
        raise HTTPException(400, "Choose the Pro plan, billed monthly or yearly")
    amount = PLANS["pro"]["price_year" if body.billing == "yearly" else "price_month"]
    oid = "order_" + secrets.token_hex(7)
    DB["orders"][oid] = {"kind": "subscription", "user_email": user["email"], "plan": "pro", "billing": body.billing,
                         "amount_paise": amount * 100, "currency": "INR", "status": "created", "created_at": now_iso()}
    save()
    return {"order_id": oid, "amount_paise": amount * 100, "amount_inr": amount, "kind": "subscription", "currency": "INR", "sandbox": True}


@app.post("/api/subscription/checkout")
def sub_checkout(body: CheckoutIn, user: dict = Depends(current_user)):
    order = DB["orders"].get(body.order_id)
    if not order or order.get("kind") != "subscription" or order["user_email"] != user["email"]:
        raise HTTPException(404, "Unknown order")
    if order["status"] == "paid":
        raise HTTPException(409, "Order already paid")
    method, last4 = gateway_validate(body)
    pay_id = "pay_" + secrets.token_hex(7)
    DB["payments"][pay_id] = {"order_id": body.order_id, "method": method, "last4": last4, "created_at": now_iso()}
    save()
    return {"order_id": body.order_id, "payment_id": pay_id, "signature": gw_sign(body.order_id, pay_id)}


@app.post("/api/subscription/verify")
def sub_verify(body: VerifyIn, user: dict = Depends(current_user)):
    order = DB["orders"].get(body.order_id)
    pay = DB["payments"].get(body.payment_id)
    if not order or order.get("kind") != "subscription" or order["user_email"] != user["email"] or not pay or pay["order_id"] != body.order_id:
        raise HTTPException(400, "Unknown order or payment")
    if not hmac.compare_digest(gw_sign(body.order_id, body.payment_id), body.signature):
        raise HTTPException(400, "Invalid payment signature")
    if order["status"] != "paid":
        order["status"] = "paid"
        days = 365 if order["billing"] == "yearly" else 30
        start = max(time.time(), user.get("plan_renews", 0)) if effective_plan(user) == "pro" else time.time()
        user["plan"], user["plan_renews"], user["plan_cancelled"] = "pro", start + days * 86400, False
        user["billing"].append({"at": now_iso(), "plan": "pro", "billing": order["billing"], "amount_inr": order["amount_paise"] // 100,
                                "payment_id": body.payment_id})
        save()
    return subscription(user)


@app.post("/api/subscription/cancel")
def sub_cancel(user: dict = Depends(current_user)):
    if effective_plan(user) == "pro":
        user["plan_cancelled"] = True  # access continues until the paid period ends
        save()
    return subscription(user)


@app.post("/api/demo/{pid}/review-expire")
def demo_review_expire(pid: str, user: dict = Depends(current_user)):
    demo_guard()
    p = own_project(pid, user, "freelancer")
    if p["paid"] or p["status"] != "submitted":
        raise HTTPException(409, "Needs a submitted, unpaid delivery")
    p["review_deadline_ts"] = time.time() - 1
    p["invoice"]["deadline_ts"] = p["review_deadline_ts"]
    log_event(p, "system", "review_window_expired", "demo shortcut")
    save()
    return view(p)



@app.get("/preview/{pid}/{token}/{path:path}")
def preview(pid: str, token: str, path: str = ""):
    """The freelancer's real delivery, wrapped with the lock script. Runs in an isolated origin (CSP sandbox)."""
    p = DB["projects"].get(pid)
    pv = (p or {}).get("preview")
    if not p or not pv or not pv.get("ok") or not hmac.compare_digest(pv["token"], token):
        raise HTTPException(404, "Preview not found")
    root = (PREVIEWS / pid).resolve()
    rel = path or "index.html"
    target = (root / rel).resolve()
    if not target.is_relative_to(root) or not target.is_file() or target.suffix.lower() not in PREVIEW_EXT:
        raise HTTPException(404, "File not found")
    headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
               "Content-Security-Policy": "sandbox allow-scripts allow-forms allow-popups allow-modals"}
    if target.suffix.lower() in (".html", ".htm"):
        text = target.read_text(encoding="utf-8", errors="replace")
        text = DRM_TAG_RE.sub("", text)
        tag = f'<script src="/static/synera-drm.js" data-project="{pid}" async></script>'
        text = re.sub(r"</body\s*>", tag + "</body>", text, count=1, flags=re.I) if re.search(r"</body\s*>", text, re.I) else text + tag
        return HTMLResponse(text, headers=headers)
    return FileResponse(target, headers=headers)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
if DEMO_CLIENT_DIR.exists():
    app.mount("/demo-client", StaticFiles(directory=DEMO_CLIENT_DIR, html=True), name="demo-client")

# Serve the built React app from the same process (run `npm run build` in /frontend). Must stay last.
FRONTEND_DIST = BASE.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
