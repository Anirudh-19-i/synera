import { useEffect, useState } from "react";
import {
  ShieldCheck, ArrowRight, FileSignature, Wallet, RefreshCw, Lock, Fingerprint, BellRing, Archive, SearchCheck, Calculator, FileCheck2, Sparkles, LayoutDashboard,
} from "lucide-react";
import { api } from "./api.js";
import { Btn, Glass } from "./ui.jsx";
import { PricingCards } from "./Pricing.jsx";
import { PaymentCheck } from "./views/Dashboard.jsx";

const PROBLEMS = [
  [BellRing, "Payment delays", "A review window, an automatic late fee, reminders that escalate, and a preview that locks itself.", "Live"],
  [Lock, "Client refuses to pay", "An advance before you submit. The preview stays locked and the source is released only after payment.", "Live"],
  [RefreshCw, "Unpaid extra work", "Revision rounds are capped in the agreement. Anything beyond is quoted and added to the invoice.", "Live"],
  [FileCheck2, "Disputes over quality", "Acceptance criteria are written up front. The audit shows each one found in the code, with file and line.", "Live"],
  [Archive, "Clients who ghost", "Silence past the review window counts as acceptance. Send a final notice and export a sealed evidence pack.", "Live"],
  [Wallet, "No leverage after delivery", "Clients review a hosted, watermarked preview. Handover happens at payment, not before.", "Live"],
  [SearchCheck, "Fake payment screenshots", "Only gateway-signed payments count. Anyone can check a payment reference on the public page.", "Live"],
  [Calculator, "Overseas fees and FX", "Estimate what lands in your account and price the fees in. Real multi-currency payouts are on the roadmap.", "Estimator"],
  [Archive, "Chargebacks", "Signed agreement, audit, receipts and timeline in one sealed pack you can hand to a provider.", "Live"],
  [FileSignature, "No written agreement", "Synera turns your brief into a 10-clause agreement, hashes it and gets the client's signature.", "Live"],
  [Sparkles, "Small amounts not worth chasing", "Self-serve notices and evidence, so recovery costs minutes instead of a lawyer. Not legal advice.", "Live"],
  [LayoutDashboard, "Platform limits and fees", "Take clients from WhatsApp or email. Flat plan, no marketplace commission.", "Live"],
];

const STEPS = [
  ["01", "Paste the brief and the agreed price", "Take the offer from any channel. Synera reads it, asks what is missing and plans the work."],
  ["02", "Get the plan and the budget split", "Phases, hours, risks and a budget divided by what the money is actually spent on."],
  ["03", "Client signs and pays the advance", "Terms, revisions and review window are in writing before you start."],
  ["04", "Deliver, verify, get paid", "Upload the work, the audit proves each requirement, the client pays and the source unlocks."],
];

export default function Landing({ onLogin, onSignup, onDemo }) {
  const [plans, setPlans] = useState(null);
  useEffect(() => { api("/api/plans").then(setPlans).catch(() => {}); }, []);
  const jump = (id) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });

  return (
    <div className="mx-auto max-w-6xl px-5 pb-20">
      <header className="sticky top-3 z-20 mx-auto mt-3 flex max-w-3xl items-center justify-between rounded-full border border-white/15 bg-black/60 py-2 pl-5 pr-2 backdrop-blur-xl">
        <div className="flex items-center gap-2 font-extrabold tracking-tight"><span className="grid h-7 w-7 place-items-center rounded-lg bg-white text-black"><ShieldCheck size={16} /></span>Synera</div>
        <nav className="hidden gap-5 text-sm text-violet-200/80 sm:flex">
          {[["problems", "Problems"], ["how", "How it works"], ["pricing", "Pricing"]].map(([id, l]) => <button key={id} onClick={() => jump(id)} className="hover:text-white">{l}</button>)}
        </nav>
        <div className="flex gap-1.5"><Btn variant="ghost" className="!px-4 !py-2" onClick={onLogin}>Log in</Btn><Btn className="!px-4 !py-2" onClick={onSignup}>Get started</Btn></div>
      </header>

      <section className="px-2 pb-16 pt-20 text-center">
        <span className="pill">Built for freelancers · Prompt-to-payment</span>
        <h1 className="mx-auto mt-6 max-w-4xl text-5xl font-extrabold leading-[1.02] md:text-7xl">Finish the work.<br />Get paid for it.</h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg text-violet-200/70">
          You got an offer on WhatsApp. Paste the brief and the agreed price. Synera plans the build, splits the budget, gets the client's signature and advance, verifies your delivery and locks the handover until you are paid.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Btn className="!px-7 !py-3.5 text-base" onClick={onSignup}>Start free <ArrowRight size={16} /></Btn>
          <Btn variant="ghost" className="!px-7 !py-3.5 text-base" onClick={onDemo}>Try the live demo</Btn>
        </div>
        <p className="mt-4 text-xs text-violet-300/60">Free for 2 active projects. Clients never pay to use it. Payments run on a sandbox gateway in this demo.</p>

        <div className="mx-auto mt-14 grid max-w-4xl gap-4 text-left sm:grid-cols-3">
          <div className="paper p-5"><div className="muted text-xs font-semibold uppercase tracking-wider">Example · brief in</div><div className="mt-3 text-sm">“Need a banking website, final price ₹1,20,000.”</div></div>
          <Glass className="p-5"><div className="text-xs font-semibold uppercase tracking-wider text-violet-300/70">Example · plan out</div><div className="mt-3 text-sm text-violet-100/85">6 phases · 41 hours · login, transfers, OTP · budget split by effort</div></Glass>
          <Glass className="p-5"><div className="text-xs font-semibold uppercase tracking-wider text-violet-300/70">Example · money in</div><div className="mt-3 text-sm text-violet-100/85">₹36,000 advance secured. Balance released on verified delivery.</div></Glass>
        </div>
      </section>

      <section id="problems" className="scroll-mt-24 py-14">
        <div className="mb-8 text-center"><span className="pill">The problem</span><h2 className="mt-3 text-4xl font-extrabold">Twelve ways freelancers lose money. One place that stops them.</h2></div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {PROBLEMS.map(([Icon, t, d, tag], i) => (
            <Glass key={t} className="p-5">
              <div className="mb-4 flex items-center justify-between"><span className="grid h-10 w-10 place-items-center rounded-xl bg-white/10"><Icon size={18} /></span><span className="pill">{String(i + 1).padStart(2, "0")} · {tag}</span></div>
              <h3 className="font-bold">{t}</h3><p className="mt-1.5 text-sm text-violet-200/70">{d}</p>
            </Glass>
          ))}
        </div>
      </section>

      <section id="how" className="scroll-mt-24 py-14">
        <div className="mb-8 text-center"><span className="pill">How it works</span><h2 className="mt-3 text-4xl font-extrabold">From WhatsApp offer to money in the bank</h2></div>
        <div className="grid gap-4 md:grid-cols-4">
          {STEPS.map(([n, t, d]) => (
            <Glass key={n} className="p-5"><div className="text-3xl font-extrabold text-violet-400/60">{n}</div><h3 className="mt-6 font-bold">{t}</h3><p className="mt-1.5 text-sm text-violet-200/70">{d}</p></Glass>
          ))}
        </div>
        <div className="paper mt-5 grid items-center gap-6 p-7 md:grid-cols-2">
          <div><span className="muted text-xs font-semibold uppercase tracking-wider">Proof, not promises</span><h3 className="mt-2 text-2xl font-extrabold">Every paid delivery becomes a verifiable portfolio card.</h3>
            <p className="muted mt-2 text-sm">Hash-chained, anonymized, and re-checkable by anyone at a public link. Your track record becomes evidence.</p></div>
          <div className="rounded-2xl bg-black p-4 font-mono text-[11px] leading-relaxed text-emerald-300"><Fingerprint size={16} className="mb-2 text-white" />sha256(freelancer | project | score | receipt | zip | prev) → 9f2c…a41e<br />chain: GENESIS → 9f2c…a41e → c7d1…02bb</div>
        </div>
      </section>

      <section className="py-10"><div className="mx-auto max-w-xl"><PaymentCheck /></div></section>

      <section id="pricing" className="scroll-mt-24 py-14">
        <div className="mb-8 text-center"><span className="pill">Pricing</span><h2 className="mt-3 text-4xl font-extrabold">One flat plan. No commission on your work.</h2></div>
        <PricingCards plans={plans} onChoose={(p) => (p === "free" ? onSignup() : onSignup())} />
      </section>

      <section className="py-10">
        <Glass className="p-6 text-sm text-violet-200/75">
          <h3 className="mb-2 font-bold text-white">What is real and what is not</h3>
          <ul className="list-disc space-y-1 pl-5">
            <li>The audit is static analysis: it proves each requirement exists in the code with file and line. It does not run the app.</li>
            <li>Payments use a sandbox gateway with the same order, signature and verify flow as a live provider. No real money moves in this demo. Holding client money for real needs a licensed payment partner.</li>
            <li>The preview lock is a deterrent for a Synera-hosted preview, not a security boundary. The source is what stays withheld.</li>
            <li>Agreements and notices are templates, not legal advice.</li>
          </ul>
        </Glass>
      </section>

      <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-white/10 pt-6 text-xs text-violet-300/60">
        <span>© Synera · Built for freelancers</span>
        <span>Public proof of work · /verify/&lt;hash&gt;</span>
      </footer>
    </div>
  );
}
