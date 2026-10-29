"""Invoice feature checks. Run against a live server: python tests/api_suite_5.py"""
import json, sys, urllib.request, urllib.error
B = "http://localhost:8000"
bad = []
def call(path, method="GET", data=None, tok=None, raw=False):
    h = {"content-type": "application/json"}
    if tok: h["authorization"] = "Bearer " + tok
    r = urllib.request.Request(B + path, method=method, headers=h, data=json.dumps(data).encode() if data is not None else None)
    try:
        resp = urllib.request.urlopen(r)
        b = resp.read()
        return resp.status, (b if raw else json.loads(b)), resp.headers
    except urllib.error.HTTPError as e:
        b = e.read()
        try: return e.code, json.loads(b), e.headers
        except Exception: return e.code, b, e.headers
def check(name, ok, info=""):
    print(("ok   " if ok else "FAIL ") + name, "" if ok else info)
    if not ok: bad.append(name)
login = lambda e: call("/api/auth/login", "POST", {"email": e, "password": "demo1234"})[1]["token"]
F, C = login("freelancer@synera.demo"), login("client@synera.demo")
call("/api/demo/reset", "POST", tok=F)
import io, zipfile
def zipof(files):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for k, v in files.items(): z.writestr(k, v)
    return b.getvalue()
def upload(pid, data):
    import secrets
    bd = "----x" + secrets.token_hex(4)
    body = (f'--{bd}\r\nContent-Disposition: form-data; name="file"; filename="d.zip"\r\nContent-Type: application/zip\r\n\r\n').encode() + data + f"\r\n--{bd}--\r\n".encode()
    r = urllib.request.Request(B + f"/api/audit/{pid}", method="POST", data=body, headers={"authorization": "Bearer " + F, "content-type": "multipart/form-data; boundary=" + bd})
    return urllib.request.urlopen(r).status
site = zipof({"a/index.html": "<!doctype html><html><body><h1>Shop</h1><form><input type=date></form></body></html>"})
def mk(chat, price):
    s, p, _ = call("/api/scope", "POST", {"chat": chat, "force_fallback": True, "price_inr": price, "advance_pct": 20, "client_email": "client@synera.demo"}, F)
    assert s == 200, p
    return p
def advance(pid):
    call(f"/api/projects/{pid}/sign", "POST", None, C)
    o = call(f"/api/pay/{pid}/order", "POST", {"kind": "advance"}, C)[1]
    sg = call(f"/api/pay/{pid}/checkout", "POST", {"order_id": o["order_id"], "method": "upi", "vpa": "success@razorpay"}, C)[1]
    call(f"/api/pay/{pid}/verify", "POST", sg, C)
draft = mk("need a gym website under 30k", 30000)
sub = mk("need a clinic website under 20k", 20000); advance(sub["id"]); upload(sub["id"], site); call(f"/api/projects/{sub['id']}/submit", "POST", None, F)
paid = mk("need a salon website under 12k", 12000); advance(paid["id"]); upload(paid["id"], site); call(f"/api/projects/{paid['id']}/submit", "POST", None, F)
o = call(f"/api/pay/{paid['id']}/order", "POST", {"kind": "final"}, C)[1]
sg = call(f"/api/pay/{paid['id']}/checkout", "POST", {"order_id": o["order_id"], "method": "upi", "vpa": "success@razorpay"}, C)[1]
call(f"/api/pay/{paid['id']}/verify", "POST", sg, C)

# billing profile validation
check("bad gstin rejected", call("/api/profile/business", "PUT", {"gstin": "123"}, F)[0] == 400)
check("bad pan rejected", call("/api/profile/business", "PUT", {"pan": "12"}, F)[0] == 400)
check("bad upi rejected", call("/api/profile/business", "PUT", {"upi_id": "nope"}, F)[0] == 400)
check("client cannot set billing", call("/api/profile/business", "PUT", {}, C)[0] == 403)
s, b, _ = call("/api/profile/business", "PUT", {"business_name": "Demo Studio", "gstin": "36abcde1234f1z5", "pan": "abcde1234f", "upi_id": "demo@okaxis"}, F)
check("valid details saved + uppercased", s == 200 and b["gstin"] == "36ABCDE1234F1Z5" and b["pan"] == "ABCDE1234F", b)

# document content
d = call(f"/api/projects/{paid['id']}/invoice", tok=F)[1]
check("paid invoice status", d["status"] == "PAID" and d["amounts"]["balance"] == 0, d["status"])
check("items sum to total", sum(i["amount"] for i in d["items"]) == d["amounts"]["total"])
check("gstin shown", d["from"]["gstin"] == "36ABCDE1234F1Z5")
check("payments carry refs", len(d["payments"]) >= 1 and all(p["ref"] for p in d["payments"]))
d2 = call(f"/api/projects/{sub['id']}/invoice", tok=F)[1]
check("submitted is DUE or PARTIALLY PAID", d2["status"] in ("DUE", "PARTIALLY PAID"), d2["status"])
check("balance = total - received", d2["amounts"]["balance"] == d2["amounts"]["total"] - d2["amounts"]["received"])

# files
for fmt, magic, ctype in (("pdf", b"%PDF", "application/pdf"), ("png", b"\x89PNG", "image/png"), ("html", b"<!doctype", "text/html")):
    s, body, h = call(f"/api/projects/{paid['id']}/invoice/file?format={fmt}", tok=F, raw=True)
    check(f"{fmt} download", s == 200 and body[:len(magic)].lower() == magic.lower() and ctype in h["content-type"], (s, body[:20]))
check("bad format rejected", call(f"/api/projects/{paid['id']}/invoice/file?format=exe", tok=F)[0] == 400)

# access control
check("client blocked from DRAFT", call(f"/api/projects/{draft['id']}/invoice", tok=C)[0] == 403)
check("client sees submitted", call(f"/api/projects/{sub['id']}/invoice", tok=C)[0] == 200)
check("no token rejected", call(f"/api/projects/{paid['id']}/invoice")[0] == 401)
s, _, _ = call("/api/auth/register", "POST", {"email": "other@x.com", "name": "Other", "role": "client", "password": "demo1234"})
O = login_other = call("/api/auth/login", "POST", {"email": "other@x.com", "password": "demo1234"})[1]["token"]
check("other client gets 404", call(f"/api/projects/{paid['id']}/invoice", tok=O)[0] == 404)
check("client cannot send", call(f"/api/projects/{draft['id']}/invoice/send", "POST", tok=C)[0] == 403)

# send makes it visible
s, r, _ = call(f"/api/projects/{draft['id']}/invoice/send", "POST", tok=F)
check("send ok + message", s == 200 and draft["invoice"]["number"] in r["message"])
check("client sees after send", call(f"/api/projects/{draft['id']}/invoice", tok=C)[0] == 200)
check("client list", all(x["number"] for x in call("/api/invoices", tok=C)[1]) and len(call("/api/invoices", tok=C)[1]) >= 3)
check("other client list empty", call("/api/invoices", tok=O)[1] == [])

# public verification
h = d["verify_url"].split("h=")[1]
v = call(f"/api/invoices/verify/{d['number']}?h={h}")[1]
check("verify genuine copy", v["found"] and v["copy_matches"] is True and v["status"] == "PAID")
check("verify leaks no emails", "@" not in json.dumps(v))
check("verify tampered hash", call(f"/api/invoices/verify/{d['number']}?h=deadbeef")[1]["copy_matches"] is False)
check("verify unknown number", call("/api/invoices/verify/SY-000000-XXXX")[1]["found"] is False)
s, page, _ = call(f"/verify/invoice/{d['number']}?h={h}", raw=True)
check("verify page renders", s == 200 and b"Genuine copy" in page)
s, page, _ = call("/verify/invoice/SY-NOPE", raw=True)
check("verify page unknown", s == 200 and b"not found" in page.lower())
# amending (extra work) must flag an older copy
h_old = call(f"/api/projects/{sub['id']}/invoice", tok=F)[1]["verify_url"].split("h=")[1]
for i in range(3):
    call(f"/api/projects/{sub['id']}/request-changes", "POST", {"message": f"change number {i}"}, C)
    if i < 2: call(f"/api/projects/{sub['id']}/submit", "POST", None, F)
print(call(f"/api/projects/{sub['id']}/change-quote", "POST", {"fee_inr": 2000, "note": "extra page"}, F)[0])
v2 = call(f"/api/invoices/verify/{sub['invoice']['number']}?h={h_old}")[1]
check("amendment flags the older copy", v2["copy_matches"] is False and v2["total_inr"] == 22000, v2)
print("---", "FAILED: " + ", ".join(bad) if bad else "ALL V5 CHECKS PASSED")
sys.exit(1 if bad else 0)
