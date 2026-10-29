"""Preview, agreement integrity and title/AI-error tests. Run with the server up on :8000."""
import io, json, secrets, sys, urllib.request as u, urllib.error, zipfile
sys.path.insert(0, "backend")
B = "http://localhost:8000"; fails = []
def call(p, m="GET", b=None, t=None, raw=False, files=None):
    data, hdr = (json.dumps(b).encode() if b is not None else None), {"content-type": "application/json"}
    if t: hdr["authorization"] = "Bearer " + t
    if files:
        bd = "----x" + secrets.token_hex(4); hdr["content-type"] = "multipart/form-data; boundary=" + bd
        data = (f'--{bd}\r\nContent-Disposition: form-data; name="file"; filename="d.zip"\r\nContent-Type: application/zip\r\n\r\n').encode() + files + f"\r\n--{bd}--\r\n".encode()
    try:
        r = u.urlopen(u.Request(B + p, method=m, data=data, headers=hdr)); d = r.read(); return r.status, (d.decode() if raw else json.loads(d)), r.headers
    except urllib.error.HTTPError as e:
        d = e.read()
        try: return e.code, json.loads(d), e.headers
        except Exception: return e.code, d.decode(), e.headers
def check(n, c):
    print(("PASS  " if c else "FAIL  ") + n)
    if not c: fails.append(n)
def login(e): return call("/api/auth/login", "POST", {"email": e, "password": "demo1234"})[1]["token"]
F, C = login("freelancer@synera.demo"), login("client@synera.demo")
call("/api/demo/reset", "POST", None, F)

def zipof(files):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for k, v in files.items(): z.writestr(k, v)
    return b.getvalue()

site = zipof({"clinic/index.html": "<!doctype html><html><body><h1>City Clinic</h1><form><input type=date></form><ul><li>Doctor Rao</li></ul><p>Privacy notice and consent</p><script src='app.js'></script></body></html>",
              "clinic/app.js": "document.title='ok'", "clinic/.env": "SECRET_KEY=abcdef1234567890", "clinic/run.py": "print(1)"})
s, p, _ = call("/api/scope", "POST", {"chat": "need a website under 80k for a hospital", "force_fallback": True, "price_inr": 80000, "advance_pct": 0, "delivery_days": 10}, F)
check("title keeps 'for a hospital'", p["contract"]["title"] == "Website for a hospital")
ag = call(f"/api/projects/{p['id']}/agreement", t=F)[1]
check("agreement has 12 clauses + integrity ok", len(ag["clauses"]) == 12 and ag["integrity_ok"])
txt = " ".join(c["title"] + " " + c["text"] for c in ag["clauses"])
check("agreement states delivery days", "within 10 days" in txt)
check("agreement lists per-feature allocation", "Booking flow" in txt and "Doctors and services listing" in txt)
check("agreement no longer pastes raw chat", "under 80k" not in txt)
check("agreement has cancellation + governing law", "Cancellation" in txt and "laws of India" in txt)
check("polled project payload omits clauses", "clauses" not in call(f"/api/projects/{p['id']}", t=F)[1]["agreement"])
check("no preview before upload", call(f"/api/projects/{p['id']}", t=F)[1]["preview_url"] is None)

s, d, _ = call(f"/api/audit/{p['id']}", "POST", None, F, files=site)
check("audit of uploaded clinic site: all 3 found", s == 200 and d["audit"]["score"] == 100)
check("audit flags the .env", len(d["audit"]["security_warnings"]) >= 1)
url = d["preview_url"]; check("freelancer gets a preview url", bool(url) and url.startswith("/preview/"))
s, html, h = call(url, raw=True)
check("preview serves the real uploaded page", s == 200 and "City Clinic" in html)
check("lock script injected with project id", f'data-project="{p["id"]}"' in html and html.count("synera-drm.js") == 1)
check("preview is CSP-sandboxed (isolated origin)", "sandbox" in (h.get("content-security-policy") or "") and "allow-same-origin" not in (h.get("content-security-policy") or ""))
check("preview serves assets", call(url + "app.js", raw=True)[0] == 200)
check(".env is not served", call(url + ".env", raw=True)[0] == 404)
check("python source is not served", call(url + "run.py", raw=True)[0] == 404)
check("path traversal blocked", call(url + "../../data.json", raw=True)[0] == 404 and call(url.replace(p["id"], p["id"]) + "%2e%2e/%2e%2e/data.json", raw=True)[0] == 404)
check("wrong token rejected", call(f"/preview/{p['id']}/deadbeef/", raw=True)[0] == 404)
cv = call(f"/api/projects/{p['id']}", t=C)[1]
check("client cannot see preview url before submit", cv["preview_url"] is None)
call(f"/api/projects/{p['id']}/sign", "POST", None, C)
call(f"/api/projects/{p['id']}/submit", "POST", None, F)
cv = call(f"/api/projects/{p['id']}", t=C)[1]
check("client gets preview url after submit", cv["preview_url"] == url)
check("signed-by records the client's name", "<client@synera.demo>" in cv["agreement"]["client_signed_by"] and cv["client_name"] == "IronPulse Fitness")
check("DRM state readable cross-origin", call(f"/api/drm/{p['id']}")[2].get("access-control-allow-origin") == "*")

# zip without index.html -> no preview, no crash
s, d, _ = call(f"/api/scope", "POST", {"chat": "Need a site", "force_fallback": True, "price_inr": 5000, "advance_pct": 0}, F)
s, d, _ = call(f"/api/audit/{d['id']}", "POST", None, F, files=zipof({"readme.txt": "hi"}))
check("zip without index.html: audit ok, no preview", s == 200 and d["preview_url"] is None and d["preview"]["ok"] is False)
s, d, _ = call(f"/api/audit/{d['id']}", "POST", None, F, files=b"not a zip")
check("corrupt zip rejected cleanly (no 500)", s in (400, 422))

import main
check("title: 'I need an app' -> App", main.derive_title("I need an app") == "App")
check("title: strips budget", main.derive_title("Need a modern gym landing page with BMI, budget ₹15,000") == "Modern gym landing page")
check("friendly AI error: invalid key", "rejected the API key" in main.short_err(Exception("400 INVALID_ARGUMENT API key not valid")))
check("friendly AI error: credits", "credits are used up" in main.short_err(Exception("402 RESOURCE_EXHAUSTED prepayment credits are depleted")))
print("\n" + ("ALL V4 CHECKS PASSED" if not fails else f"FAILED ({len(fails)}): {fails}"))
