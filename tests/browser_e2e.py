import asyncio, secrets
from playwright.async_api import async_playwright
OUT="/tmp/synera_shots"
tag=secrets.token_hex(3); FE=f"fl{tag}@t.io"; CE=f"cl{tag}@t.io"
async def register(pg, role, email):
    await pg.goto("http://localhost:8000/"); await pg.click("text=Get started")
    await pg.click(f"text=I'm a {role}")
    await pg.fill("input[placeholder*='name' i]", role.title()+" "+tag)
    await pg.fill("input[type=email]", email); await pg.fill("input[type=password]","password123")
    await pg.click("button[type=submit]"); await pg.wait_for_timeout(1200)
async def pay(pg, label):
    await pg.click("text=Use success UPI"); await pg.click(f".fixed button:text-matches('^Pay ₹')"); await pg.wait_for_selector("text=Payment verified",timeout=8000); await pg.wait_for_timeout(2000)
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); errs=[]
        F=await (await b.new_context(viewport={"width":1440,"height":900})).new_page()
        C=await (await b.new_context(viewport={"width":1440,"height":900})).new_page()
        for pg in (F,C): pg.on("pageerror",lambda e:errs.append(str(e)))
        await register(F,"freelancer",FE); await F.screenshot(path=f"{OUT}/e1_new_dash.png")
        await F.click("button:has-text('Projects')"); await F.wait_for_timeout(500)
        await F.fill("textarea","Need a website for a clinic with online appointment booking and doctor listing. Client agreed final price.")
        await F.fill("input[type=email]",CE); await F.fill("input[placeholder*='120000']","73000")
        await F.click("text=Analyse brief and build the plan"); await F.wait_for_selector("text=Build plan",timeout=10000); await F.wait_for_timeout(600)
        await F.screenshot(path=f"{OUT}/e2_plan.png",full_page=True)
        print("plan ok; price shown:", await F.locator("text=Where the ₹73,000 goes").count())
        # client
        await register(C,"client",CE); await C.wait_for_selector("text=Agreement"); 
        await C.click("text=Accept and sign"); await C.wait_for_selector("text=Signed by"); 
        await C.click("text=Pay advance"); await pay(C,"adv")
        await C.wait_for_selector("text=secured before delivery"); await C.screenshot(path=f"{OUT}/e3_client_funded.png",full_page=True)
        print("advance paid via UI")
        # freelancer audits with sample + submits
        await F.reload(); await F.wait_for_timeout(1500); await F.click("button:has-text('Projects')")
        await F.click("text=Use sample (gym site)"); await F.wait_for_timeout(1500)
        await F.click("text=Submit to client for review"); await F.wait_for_timeout(1500)
        await C.reload(); await C.wait_for_selector("text=Accept and pay",timeout=8000)
        await C.screenshot(path=f"{OUT}/e4_client_review.png")
        await C.click("text=Accept and pay"); await pay(C,"final")
        await C.wait_for_selector("text=Delivery proof minted",timeout=10000)
        print("final paid via UI + proof minted")
        await F.click("button:has-text('Dashboard')"); await F.wait_for_timeout(2500)
        await F.screenshot(path=f"{OUT}/e5_dash_after.png",full_page=True)
        print("earned shown:", await F.locator("text=₹73,000").count()>0)
        # upgrade flow
        await F.click("button:has-text('Plan')"); await F.wait_for_timeout(800)
        await F.click("text=Upgrade to Pro >> nth=-1"); 
        await F.wait_for_selector("text=Synera Pro"); await pay(F,"sub")
        await F.wait_for_selector("text=Billing history",timeout=8000)
        await F.screenshot(path=f"{OUT}/e6_pro.png",full_page=True)
        print("subscription upgraded via UI")
        print("errors:",errs)
        await b.close()
asyncio.run(main())
