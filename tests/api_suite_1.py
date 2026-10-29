"""v2 API tests: auth, permissions, dynamic cost split, delivery verdict, changes flow, payments."""
import io
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile

B = "http://localhost:8000"
fails = []


def call(path, method="GET", body=None, token=None, files=None):
    headers = {}
    data = None
    if files:
        boundary = "----pl" + uuid.uuid4().hex
        parts = []
        for name, (fname, content) in files.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{fname}"\r\n'
                         f'Content-Type: application/zip\r\n\r\n'.encode() + content + b"\r\n")
        data = b"".join(parts) + f"--{boundary}--\r\n".encode()
        headers["content-type"] = f"multipart/form-data; boundary={boundary}"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["content-type"] = "application/json"
    if token:
        headers["authorization"] = f"Bearer {token}"
    req = urllib.request.Request(B + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def check(name, cond, extra=""):
    print(("PASS  " if cond else "FAIL  ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


for _ in range(30):
    try:
        call("/api/health")
        break
    except Exception:
        time.sleep(0.5)

# ---------------- auth ----------------
s, d = call("/api/projects")
check("unauthenticated request rejected (401)", s == 401)
s, d = call("/api/auth/login", "POST", {"email": "freelancer@synera.demo", "password": "wrongpass"})
check("wrong password rejected (401)", s == 401, d.get("detail", ""))
s, fl = call("/api/auth/login", "POST", {"email": "freelancer@synera.demo", "password": "demo1234"})
check("demo freelancer login", s == 200 and fl["user"]["role"] == "freelancer")
s, cl = call("/api/auth/login", "POST", {"email": "client@synera.demo", "password": "demo1234"})
check("demo client login", s == 200 and cl["user"]["role"] == "client")
FT, CT = fl["token"], cl["token"]
s, me = call("/api/auth/me", token=CT)
check("/me returns the client", me["email"] == "client@synera.demo" and "pw" not in me)

tag = uuid.uuid4().hex[:6]
s, f2 = call("/api/auth/register", "POST", {"name": "Other Dev", "email": f"dev{tag}@x.io", "password": "longenough1", "role": "freelancer"})
check("register new freelancer", s == 200)
s, d = call("/api/auth/register", "POST", {"name": "Other Dev", "email": f"dev{tag}@x.io", "password": "longenough1", "role": "freelancer"})
check("duplicate email rejected (409)", s == 409)
s, d = call("/api/auth/register", "POST", {"name": "X Y", "email": "bad-email", "password": "longenough1", "role": "client"})
check("invalid email rejected (400)", s == 400)
s, d = call("/api/auth/register", "POST", {"name": "X Y", "email": f"a{tag}@x.io", "password": "short", "role": "client"})
check("short password rejected (422)", s == 422)
s, c2 = call("/api/auth/register", "POST", {"name": "Other Client", "email": f"cl{tag}@x.io", "password": "longenough1", "role": "client"})
check("register new client", s == 200)
F2, C2 = f2["token"], c2["token"]

call("/api/demo/reset", "POST", token=FT)
# ---------------- scope + dynamic cost split ----------------
s, d = call("/api/scope", "POST", {"chat": "Need a gym site with BMI calculator and dark mode, budget ₹10,000"}, token=CT)
check("client cannot create a project (403)", s == 403)

s, p1 = call("/api/scope", "POST", {"chat": "Need a modern gym landing page with BMI calculator, dark mode, and WhatsApp lead button, budget ₹15,000", "force_fallback": True, "advance_pct": 0}, token=FT)
call(f"/api/projects/{p1['id']}/sign", "POST", token=CT)
check("freelancer creates project", s == 200 and p1["status"] == "scoped")
bd = p1["breakdown"]
check("cost split sums exactly to budget", sum(i["amount"] for i in bd) == 15000, str(sum(i["amount"] for i in bd)))
check("cost split has design, features, qa, handover", {i["kind"] for i in bd} == {"design", "feature", "qa", "handover"})
check("milestones derived from split and sum to budget", sum(m["amount_inr"] for m in p1["contract"]["milestones"]) == 15000)
bmi = next(i for i in bd if i["label"] == "BMI calculator"); wa = next(i for i in bd if i["label"].startswith("WhatsApp"))
check("heavier feature costs more (BMI > WhatsApp)", bmi["amount"] > wa["amount"], f'{bmi["amount"]} vs {wa["amount"]}')

s, p2 = call("/api/scope", "POST", {"chat": "Build a store with user login, payment checkout and dark mode, budget 40k", "force_fallback": True, "advance_pct": 0, "client_email": f"cl{tag}@x.io"}, token=FT)
check("budget '40k' parsed", p2["invoice"]["total_inr"] == 40000)
pay_item = next(i for i in p2["breakdown"] if i["label"] == "Payments")
dark_item = next(i for i in p2["breakdown"] if i["label"] == "Dark mode")
check("split is dynamic: payments dominate", pay_item["amount"] > 2 * dark_item["amount"], f'{pay_item["amount"]} vs {dark_item["amount"]}')
check("split differs by scope (different feature sets)", [i["label"] for i in bd] != [i["label"] for i in p2["breakdown"]])
check("second split sums to 40000", sum(i["amount"] for i in p2["breakdown"]) == 40000)
PID1, PID2 = p1["id"], p2["id"]

# ---------------- access control ----------------
s, d = call(f"/api/projects/{PID1}", token=F2)
check("other freelancer cannot see project (404)", s == 404)
s, d = call(f"/api/projects/{PID1}", token=C2)
check("other client cannot see project (404)", s == 404)
s, d = call(f"/api/projects/{PID2}", token=CT)
check("demo client cannot see another client's project (404)", s == 404)
s, lst = call("/api/projects", token=FT)
check("freelancer lists only own projects", {p["id"] for p in lst} == {PID1, PID2})
s, lst = call("/api/projects", token=CT)
check("client lists only own projects", PID1 in {p["id"] for p in lst} and PID2 not in {p["id"] for p in lst})

# ---------------- audit, visibility, verdict ----------------
s, d = call(f"/api/audit/{PID1}?use_sample=true", "POST", token=CT)
check("client cannot upload/audit (403)", s == 403)
s, d = call(f"/api/audit/{PID1}?use_sample=true", "POST", token=F2)
check("other freelancer cannot audit (404)", s == 404)
s, a1 = call(f"/api/audit/{PID1}?use_sample=true", "POST", token=FT)
check("freelancer audits sample: all criteria found", s == 200 and a1["audit"]["score"] == 100 and a1["status"] == "audited")
check("value delivered = full budget when all met", a1["audit"]["value_delivered_inr"] == 15000)
check("verdict satisfied", a1["audit"]["verdict"]["level"] == "satisfied", a1["audit"]["verdict"]["headline"])
s, cv = call(f"/api/projects/{PID1}", token=CT)
check("client cannot see audit before submission", cv["audit"] is None)
s, d = call(f"/api/pay/{PID1}/order", "POST", token=CT)
check("client cannot pay before submission (409)", s == 409)
s, sub = call(f"/api/projects/{PID1}/submit", "POST", token=FT)
check("freelancer submits", s == 200 and sub["status"] == "submitted")
s, cv = call(f"/api/projects/{PID1}", token=CT)
check("client sees audit after submission", cv["audit"] and cv["audit"]["verdict"]["level"] == "satisfied")

# partially delivered zip with a leaked .env
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.writestr("index.html", '<!doctype html><form id="bmi-form"></form><script>function calculateBMI(h,w){return w/(h*h)}</script>')
    z.writestr(".env", "GEMINI_API_KEY=AIzaSyA1234567890abcdefghijklmnopqrstuvw\n")
s, bad = call(f"/api/audit/{PID1}", "POST", token=FT, files={"file": ("bad.zip", buf.getvalue())})
au = bad["audit"]
check("incomplete delivery scores below 100", s == 200 and au["score"] < 100, au["badge"])
check("verdict is not 'satisfied'", au["verdict"]["level"] in ("partial", "not_met"), au["verdict"]["headline"])
check("verdict lists the missing requirements", len(au["verdict"]["missing"]) == au["total"] - au["passed"] and au["verdict"]["missing"])
check("value delivered below budget", au["value_delivered_inr"] < 15000, str(au["value_delivered_inr"]))
check("BMI feature met, dark mode missing",
      {r["label"]: r["status"] for r in au["cost_rows"] if r["kind"] == "feature"}.get("BMI calculator") == "met"
      and {r["label"]: r["status"] for r in au["cost_rows"] if r["kind"] == "feature"}.get("Dark mode") == "missing")
check(".env flagged and handover budget withheld", au["security_warnings"] and next(r for r in au["cost_rows"] if r["kind"] == "handover")["earned"] == 0)
check("re-audit returns status to 'audited' (client view hidden again)", bad["status"] == "audited")

# ---------------- request changes flow ----------------
s, d = call(f"/api/projects/{PID1}/request-changes", "POST", {"message": "Dark mode is missing"}, token=CT)
check("cannot request changes on unsubmitted work (409)", s == 409)
call(f"/api/audit/{PID1}?use_sample=true", "POST", token=FT)
call(f"/api/projects/{PID1}/submit", "POST", token=FT)
s, rc = call(f"/api/projects/{PID1}/request-changes", "POST", {"message": "Please also add a pricing section"}, token=CT)
check("client requests changes", s == 200 and rc["status"] == "changes_requested" and rc["feedback"]["message"])
s, d = call(f"/api/pay/{PID1}/order", "POST", token=CT)
check("payment blocked while changes are requested (409)", s == 409)
s, fv = call(f"/api/projects/{PID1}", token=FT)
check("freelancer sees the client's feedback", fv["feedback"]["message"].startswith("Please also"))
call(f"/api/projects/{PID1}/submit", "POST", token=FT)

# ---------------- DRM permissions ----------------
s, d = call(f"/api/drm/{PID1}", "POST", {"state": "KILLED"}, token=CT)
check("client cannot flip the kill-switch (403)", s == 403)
s, d = call(f"/api/drm/{PID1}", "POST", {"state": "KILLED"}, token=F2)
check("other freelancer cannot flip the kill-switch (404)", s == 404)
s, d = call(f"/api/drm/{PID1}", "POST", {"state": "KILLED"}, token=FT)
check("owner flips the kill-switch", s == 200 and d["drm_state"] == "KILLED")
s, pub = call(f"/api/drm/{PID1}")
check("DRM state is publicly readable (needed by the preview script)", s == 200 and pub["state"] == "KILLED")
call(f"/api/drm/{PID1}", "POST", {"state": "PREVIEW"}, token=FT)

# ---------------- payments ----------------
s, d = call(f"/api/pay/{PID1}/order", "POST", token=FT)
check("freelancer cannot pay (403)", s == 403)
s, d = call(f"/api/pay/{PID1}/order", "POST", token=C2)
check("other client cannot pay (404)", s == 404)
s, d = call(f"/api/pay/{PID1}/settle", "POST", {}, token=CT)
check("direct settle blocked (403)", s == 403)
s, o = call(f"/api/pay/{PID1}/order", "POST", token=CT)
check("client creates order", s == 200 and o["amount_paise"] == 1500000)
s, d = call(f"/api/pay/{PID1}/checkout", "POST", {"order_id": o["order_id"], "method": "upi", "vpa": "failure@razorpay"}, token=CT)
check("failure UPI declined (402)", s == 402)
s, signed = call(f"/api/pay/{PID1}/checkout", "POST", {"order_id": o["order_id"], "method": "upi", "vpa": "success@razorpay"}, token=CT)
check("success UPI returns signed payment", s == 200 and len(signed["signature"]) == 64)
s, d = call(f"/api/pay/{PID1}/verify", "POST", dict(signed, signature="a" * 64), token=CT)
check("forged signature rejected (400)", s == 400)
s, d = call(f"/api/download/{PID1}", token=CT)
check("download blocked before payment (402)", s == 402)
s, done = call(f"/api/pay/{PID1}/verify", "POST", signed, token=CT)
check("valid signature settles, unlocks, mints", s == 200 and done["project"]["drm_state"] == "UNLOCKED" and done["mint"]["hash"])
check("status is paid", done["project"]["status"] == "paid")
s, z = call(f"/api/download/{PID1}", token=CT)
check("client downloads source after payment", s == 200 and z[:2] == b"PK")
s, d = call(f"/api/download/{PID1}", token=FT)
check("freelancer cannot use the client download (403)", s == 403)
s, d = call(f"/api/drm/{PID1}", "POST", {"state": "KILLED"}, token=FT)
check("kill-switch permanently disarmed after payment (409)", s == 409)
s, v = call(f"/api/verify/{done['mint']['hash']}")
check("minted hash verifies publicly", v["valid"] is True)
s, f = call("/api/folio/fr_demo")
check("folio lists the card, stats update", f["stats"]["verified_deliveries"] >= 1 and f["cards"][0]["value_delivered_inr"] == 15000)

# ---------------- logout ----------------
call("/api/auth/logout", "POST", token=F2)
s, d = call("/api/auth/me", token=F2)
check("logged-out token no longer works (401)", s == 401)

print("\nALL V2 CHECKS PASSED" if not fails else f"\nFAILED ({len(fails)}): {fails}")
sys.exit(1 if fails else 0)
