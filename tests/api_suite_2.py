import json, urllib.request as u, urllib.error, secrets, io, zipfile, time
B="http://localhost:8000"
fails=[]
def call(p,m="GET",b=None,t=None,raw=False):
    r=u.Request(B+p,method=m,data=json.dumps(b).encode() if b is not None else None,headers={"content-type":"application/json",**({"authorization":"Bearer "+t} if t else {})})
    try:
        resp=u.urlopen(r); d=resp.read()
        return resp.status,(d.decode() if raw else json.loads(d))
    except urllib.error.HTTPError as e:
        d=e.read()
        try: return e.code,json.loads(d)
        except Exception: return e.code,d.decode()
def check(n,c):
    print(("PASS  " if c else "FAIL  ")+n)
    if not c: fails.append(n)
def login(e,pw="demo1234"):
    s,d=call("/api/auth/login","POST",{"email":e,"password":pw}); return d["token"]
def reg(role):
    e=f"{role}{secrets.token_hex(3)}@t.io"; s,d=call("/api/auth/register","POST",{"name":role.title()+" T","email":e,"password":"password123","role":role}); return e,d["token"]

F=login("freelancer@synera.demo"); C=login("client@synera.demo")
call("/api/demo/reset","POST",None,F)

# --- scope with explicit final price + terms
s,p=call("/api/scope","POST",{"chat":"Need a website for a banking application","force_fallback":True,"price_inr":120000,"advance_pct":30,"revisions_included":1,"review_days":3},F)
check("scope ok", s==200)
check("final price overrides parsing", p["contract"]["total_inr"]==120000 and p["money"]["base"]==120000)
check("breakdown sums to price", sum(x["amount"] for x in p["breakdown"])==120000)
check("advance computed 30%", p["terms"]["advance_inr"]==36000)
check("agreement hash + freelancer signed", len(p["agreement"]["sha256"])==64 and p["agreement"]["freelancer_signed_at"] and not p["agreement"]["client_signed_at"])
pid=p["id"]
# agreement readable by both, clauses
s,a=call(f"/api/projects/{pid}/agreement",t=C); check("client reads agreement (12 clauses)", s==200 and len(a["clauses"])==12)
s,h=call(f"/api/projects/{pid}/agreement?format=html",t=F,raw=True); check("agreement html", s==200 and "Freelance Agreement" in h)

# --- payment before signing blocked
s,d=call(f"/api/pay/{pid}/order","POST",{"kind":"advance"},C); check("cannot pay before signing (409)", s==409)
s,d=call(f"/api/projects/{pid}/sign","POST",None,F); check("freelancer cannot sign for client (403)", s==403)
s,d=call(f"/api/projects/{pid}/sign","POST",None,C); check("client signs", s==200 and d["agreement"]["client_signed_at"])

# --- audit, submit blocked until advance
s,d=call(f"/api/audit/{pid}?use_sample=true","POST",None,F); check("audit ok", s==200)
s,d=call(f"/api/projects/{pid}/submit","POST",None,F); check("submit blocked until advance paid (409)", s==409 and "advance" in str(d))

def pay(pid,kind,tok=C,vpa="success@razorpay"):
    s,o=call(f"/api/pay/{pid}/order","POST",{"kind":kind},tok)
    if s!=200: return s,o
    s,sg=call(f"/api/pay/{pid}/checkout","POST",{"order_id":o["order_id"],"method":"upi","vpa":vpa},tok)
    if s!=200: return s,sg
    s,r=call(f"/api/pay/{pid}/verify","POST",sg,tok); r["_pay"]=sg["payment_id"]; return s,r
s,d=call(f"/api/pay/{pid}/order","POST",{"kind":"advance"},C); o=d
s,d=call(f"/api/pay/{pid}/checkout","POST",{"order_id":o["order_id"],"method":"upi","vpa":"failure@razorpay"},C); check("declined advance (402)", s==402)
s,r=pay(pid,"advance"); check("advance paid, project funded", s==200 and r["project"]["funded"] and r["project"]["money"]["advance_paid"]==36000)
advpay=r["_pay"]
s,d=call(f"/api/payments/verify/{advpay}"); check("payment reference verifies publicly", d["verified"] and d["amount_inr"]==36000)
s,d=call("/api/payments/verify/pay_fake123"); check("fake payment reference rejected", d["verified"] is False)
s,d=call(f"/api/pay/{pid}/order","POST",{"kind":"advance"},C); check("advance can't be paid twice (409)", s==409)
s,d=call(f"/api/pay/{pid}/order","POST",{"kind":"final"},C); check("final blocked before submit (409)", s==409)

s,d=call(f"/api/projects/{pid}/submit","POST",None,F); check("submit ok after advance", s==200 and d["review"]["seconds_remaining"]>0)
# --- revisions: 1 included, 2nd is billable
s,d=call(f"/api/projects/{pid}/request-changes","POST",{"message":"Please change the logo"},C); check("1st revision included", s==200 and not d["feedback"]["billable"])
s,d=call(f"/api/projects/{pid}/submit","POST",None,F); check("resubmit ok", s==200)
s,d=call(f"/api/projects/{pid}/request-changes","POST",{"message":"Also add a chatbot and 5 new pages"},C); check("2nd revision billable", s==200 and d["feedback"]["billable"])
s,d=call(f"/api/projects/{pid}/submit","POST",None,F); check("resubmit blocked until quote (409)", s==409)
s,d=call(f"/api/projects/{pid}/change-quote","POST",{"fee_inr":8000,"note":"chatbot"},C); check("client cannot quote (403)", s==403)
s,d=call(f"/api/projects/{pid}/change-quote","POST",{"fee_inr":8000,"note":"chatbot"},F); check("freelancer quotes extra", s==200 and d["money"]["extras"]==8000)
s,d=call(f"/api/projects/{pid}/submit","POST",None,F); check("resubmit ok after quote", s==200)
cv=call(f"/api/projects/{pid}",t=C)[1]
check("client sees extras + balance", cv["money"]["grand_total"]==128000 and cv["money"]["balance_due"]==92000)
check("timeline records events", len(cv["timeline"])>=8)

# --- review window, late fee, deemed acceptance, reminders
s,d=call(f"/api/demo/{pid}/review-expire","POST",None,F); check("review window expired -> deemed accepted", d["review"]["expired"] and d["money"]["late_fee"]==round(128000*0.02))
s,m1=call(f"/api/projects/{pid}/remind","POST",None,F); check("reminder 1 friendly + whatsapp link", m1["level"]==1 and m1["whatsapp_url"].startswith("https://wa.me/"))
s,m2=call(f"/api/projects/{pid}/remind","POST",None,F); check("reminder 2 firm", m2["level"]==2)
s,m3=call(f"/api/projects/{pid}/remind","POST",None,F); check("final notice for Pro", s==200 and m3["level"]==3 and "deemed accepted" in m3["body"])

# --- evidence pack
s,pk=call(f"/api/projects/{pid}/evidence",t=F); check("evidence pack sealed", s==200 and len(pk["seal_sha256"])==64 and pk["delivery"]["zip_sha256"])
s,h=call(f"/api/projects/{pid}/evidence?format=html",t=F,raw=True); check("evidence html", s==200 and "Evidence pack" in h)
s,d=call(f"/api/projects/{pid}/evidence",t=C); check("client cannot export evidence (403)", s==403)

# --- final payment includes extras + late fee
s,r=pay(pid,"final"); check("final paid", s==200 and r["project"]["paid"])
mm=r["project"]["money"]; check("total = base+extras+late fee, balance 0", mm["grand_total"]==120000+8000+2560 and mm["balance_due"]==0 and mm["received"]==mm["grand_total"])
check("proof minted with grand total", r["mint"]["invoice_total_inr"]==mm["grand_total"])

# --- dashboard
s,db=call("/api/dashboard",t=F); check("dashboard totals", s==200 and db["totals"]["earned_inr"]==130560 and db["totals"]["completed"]==1)
check("dashboard project row", db["projects"][0]["received_inr"]==130560 and db["projects"][0]["days_to_pay"] is not None)
check("monthly chart has 6 months", len(db["monthly"])==6 and sum(x["earned_inr"] for x in db["monthly"])==130560)
check("client record", db["clients"][0]["paid_projects"]==1)
s,csv=call("/api/dashboard/export.csv",t=F,raw=True); check("csv export (Pro)", s==200 and "invoice,project" in csv)
s,d=call("/api/dashboard",t=C); check("client cannot open dashboard (403)", s==403)

# --- free plan limits + subscription
e,T=reg("freelancer")
s,d=call("/api/auth/me",t=T); check("new freelancer is on Starter", d["user"]["plan"]=="free" if "user" in d else d.get("plan")=="free")
for i in range(2): s,_=call("/api/scope","POST",{"chat":f"Need a portfolio site {i}","force_fallback":True,"price_inr":9000},T)
s,d=call("/api/scope","POST",{"chat":"Need a third site","force_fallback":True,"price_inr":9000},T); check("Starter limited to 2 active projects (402)", s==402 and "Pro" in str(d))
pid2=call("/api/projects",t=T)[1][0]["id"]
call(f"/api/audit/{pid2}?use_sample=true","POST",None,T)
s,d=call(f"/api/projects/{pid2}/evidence",t=T); check("evidence pack locked on Starter (402)", s==402)
s,d=call("/api/dashboard/export.csv",t=T); check("csv locked on Starter (402)", s==402)
s,o=call("/api/subscription/order","POST",{"plan":"pro","billing":"monthly"},T); check("subscription order ₹499", o["amount_inr"]==499)
s,d=call("/api/subscription/checkout","POST",{"order_id":o["order_id"],"method":"card","card_number":"4000 0000 0000 0002"},T); check("declined card (402)", s==402)
s,sg=call("/api/subscription/checkout","POST",{"order_id":o["order_id"],"method":"card","card_number":"4111 1111 1111 1111"},T)
bad=dict(sg); bad["signature"]="0"*64
s,d=call("/api/subscription/verify","POST",bad,T); check("forged subscription signature rejected", s==400)
s,d=call("/api/subscription/verify","POST",sg,T); check("upgrade to Pro", s==200 and d["plan"]=="pro" and d["renews"])
s,d=call("/api/scope","POST",{"chat":"Need a third site","force_fallback":True,"price_inr":9000},T); check("Pro: unlimited projects", s==200)
s,d=call(f"/api/projects/{pid2}/evidence",t=T); check("evidence pack unlocked after upgrade", s==200)
s,d=call("/api/subscription/cancel","POST",None,T); check("cancel keeps access until period end", d["plan"]=="pro" and d["cancelled"])
s,o2=call("/api/subscription/order","POST",{"plan":"pro","billing":"monthly"},F)
s,d=call("/api/subscription/checkout","POST",{"order_id":o["order_id"],"method":"upi","vpa":"success@x"},F); check("cannot use another user's order", s==404)
print("\n"+("ALL V3 CHECKS PASSED" if not fails else f"FAILED ({len(fails)}): {fails}"))
