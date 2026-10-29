import { useState, useEffect } from "react";
import { api } from "../api.js";
import { Wand2, Upload, FileCheck2, Sparkles, ArrowRight, Send, MessageSquare, Mail } from "lucide-react";
import { Glass, Btn, Chip, KillSwitch, inr } from "../ui.jsx";
import BuildPlan from "./BuildPlan.jsx";
import Protection from "./Protection.jsx";
import { CostSplit, ProjectStatus, Stepper } from "../cost.jsx";

const DEMO = "Need a modern gym landing page with BMI calculator, dark mode, and WhatsApp lead button, budget ₹15,000";

export default function Freelancer({ p, a, busy, setView, plan }) {
  const [chat, setChat] = useState(DEMO);
  const [clientEmail, setClientEmail] = useState("client@synera.demo");
  const [grace, setGrace] = useState(72);
  const [price, setPrice] = useState("");
  const [advance, setAdvance] = useState(30);
  const [revisions, setRevisions] = useState(2);
  const [reviewDays, setReviewDays] = useState(3);
  const [lateFee, setLateFee] = useState(2);
  const [deliveryDays, setDeliveryDays] = useState(7);
  const [file, setFile] = useState(null);
  const [ai, setAi] = useState(null);
  useEffect(() => { api("/api/ai/status").then(setAi).catch(() => {}); }, []);
  const c = p?.contract;
  const au = p?.audit;
  const needAdvance = !!(p && p.terms.advance_inr && !p.funded);
  const canSubmit = p && au && !p.paid && !needAdvance && !p.pending_quote && (p.status === "audited" || p.status === "changes_requested");

  return (
    <div className="grid gap-5 lg:grid-cols-5">
      <div className="space-y-5 lg:col-span-3">
        {ai && (
          <Glass className="flex items-center gap-2 px-4 py-2 text-xs">
            <Chip tone={ai.ok ? "emerald" : "amber"}>{ai.ok ? "AI connected" : "AI offline"}</Chip>
            <span className="text-violet-200/80">{ai.ok ? ai.model : (ai.configured ? ai.error : "Add GEMINI_API_KEY to backend/.env to enable the AI scoper and auditor. The offline template still works.")}</span>
          </Glass>
        )}
        <Glass className="p-5">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="flex items-center gap-2 font-bold"><Wand2 size={18} className="text-violet-300" /> New project: paste the brief</h2>
            <Chip tone="slate">Problem #61</Chip>
          </div>
          <textarea rows={4} value={chat} onChange={(e) => setChat(e.target.value)}
            className="w-full resize-none p-3 text-sm" placeholder="Paste the offer from WhatsApp, email or a call note. Say what the client wants and what was agreed." />
          <div className="mt-3 grid gap-3 sm:grid-cols-5">
            <label className="flex flex-col gap-1 text-xs text-violet-300/80 sm:col-span-3">
              <span className="flex items-center gap-1"><Mail size={12} /> Client's email (they see the project when they log in)</span>
              <input type="email" value={clientEmail} onChange={(e) => setClientEmail(e.target.value)}
                className="w-full px-3 py-2 text-sm" style={{ background: "rgba(255,255,255,.05)", border: "1px solid rgba(255,255,255,.12)", borderRadius: ".75rem", color: "inherit" }} />
            </label>
            <label className="flex flex-col gap-1 text-xs text-violet-300/80 sm:col-span-2">
              Grace period (hours)
              <input type="number" min={0} value={grace} onChange={(e) => setGrace(+e.target.value)} className="w-full px-3 py-2 text-sm" />
            </label>
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-6">
            <label className="flex flex-col gap-1 text-xs text-violet-300/80 sm:col-span-2">
              Final agreed price (₹)
              <input type="number" min={500} value={price} onChange={(e) => setPrice(e.target.value)} placeholder="e.g. 120000" className="w-full px-3 py-2 text-sm" />
            </label>
            <label className="flex flex-col gap-1 text-xs text-violet-300/80">Advance %<input type="number" min={0} max={70} value={advance} onChange={(e) => setAdvance(+e.target.value)} className="w-full px-3 py-2 text-sm" /></label>
            <label className="flex flex-col gap-1 text-xs text-violet-300/80">Free revisions<input type="number" min={0} max={10} value={revisions} onChange={(e) => setRevisions(+e.target.value)} className="w-full px-3 py-2 text-sm" /></label>
            <label className="flex flex-col gap-1 text-xs text-violet-300/80">Review days<input type="number" min={1} max={30} value={reviewDays} onChange={(e) => setReviewDays(+e.target.value)} className="w-full px-3 py-2 text-sm" /></label>
            <label className="flex flex-col gap-1 text-xs text-violet-300/80">Delivery days<input type="number" min={1} max={180} value={deliveryDays} onChange={(e) => setDeliveryDays(+e.target.value)} className="w-full px-3 py-2 text-sm" /></label>
          </div>
          <p className="mt-2 text-[11px] text-violet-300/60">These become clauses in the agreement your client signs. Late fee: {lateFee}% per week after the review window.</p>
          <Btn className="mt-3 w-full" disabled={busy || chat.trim().length < 5 || !clientEmail.includes("@")}
            onClick={() => a.scope({ chat, grace, clientEmail, price: price ? +price : null, advance, revisions, reviewDays, lateFee, deliveryDays })}>
            <Sparkles size={16} /> {busy ? "Analysing the brief…" : "Analyse brief and build the plan"}
          </Btn>
        </Glass>

        {c && (
          <>
            <Glass className="p-5">
              <div className="mb-1 flex flex-wrap items-center gap-2">
                <h3 className="text-lg font-bold">{c.title}</h3>
                <Chip tone={p.source === "gemini" ? "emerald" : "amber"}>{p.source === "gemini" ? (p.ai_model || "Gemini") : "Offline template"}</Chip>
                {c.stack_tags.map((t) => <Chip key={t} tone="slate">{t}</Chip>)}
              </div>
              {p.source !== "gemini" && p.ai_error && p.ai_error !== "Offline template requested" && <p className="mb-2 text-xs text-amber-300/80">AI not used: {p.ai_error}</p>}
              <p className="mb-1 text-xs text-violet-300/70">For {p.client_name} · {p.client_email}</p>
              <p className="mb-4 text-sm text-violet-200/70">{c.summary}</p>
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-violet-300/70">Milestones</h4>
                  <div className="space-y-2">
                    {c.milestones.map((m, i) => (
                      <div key={i} className="rounded-xl bg-white/5 p-3">
                        <div className="flex justify-between text-sm font-semibold"><span>{i + 1}. {m.title}</span><span>{inr(m.amount_inr)}</span></div>
                        <p className="mt-0.5 text-xs text-violet-200/60">{m.description}</p>
                      </div>
                    ))}
                  </div>
                </div>
                <div>
                  <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-violet-300/70">Acceptance criteria</h4>
                  <div className="space-y-2">
                    {c.criteria.map((x) => (
                      <div key={x.id} className="flex gap-2 rounded-xl bg-white/5 p-3 text-sm">
                        <span className="font-mono text-xs text-violet-300">{x.id}</span>
                        <span className="flex-1 text-violet-100/90">{x.description}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </Glass>

            <BuildPlan p={p} />

            <Glass className="p-5">
              <h3 className="mb-1 font-bold">Where the {inr(p.invoice.total_inr)} goes</h3>
              <p className="mb-4 text-xs text-violet-300/70">Design, QA and handover take fixed shares. The rest is split across the requested features by effort, so it changes with every scope.</p>
              <CostSplit items={p.breakdown} total={p.invoice.total_inr} audit={au} />
            </Glass>
          </>
        )}

        <Glass className="p-5">
          <h2 className="mb-3 flex items-center gap-2 font-bold"><FileCheck2 size={18} className="text-violet-300" /> Deliver and verify</h2>
          <div className="flex flex-wrap items-center gap-3">
            <input type="file" accept=".zip" onChange={(e) => setFile(e.target.files[0])}
              className="text-sm text-violet-200 file:mr-3 file:rounded-lg file:border-0 file:bg-white/10 file:px-3 file:py-2 file:text-sm file:text-violet-100" />
            <Btn disabled={!p || !file || busy || p?.paid} onClick={() => a.audit(file)}><Upload size={16} /> Run audit</Btn>
            <Btn variant="ghost" disabled={!p || busy || p?.paid} onClick={a.auditSample} title="A ready-made gym website, for trying the flow">Use sample (gym site)</Btn>
          </div>
          {au && (
            <div className="mt-4 space-y-3">
              <div className="flex flex-wrap items-center gap-3 rounded-xl bg-white/5 p-3">
                <Chip tone={au.score >= 90 ? "emerald" : "amber"}>{au.badge}</Chip>
                <span className="text-sm text-violet-200/80">{au.passed}/{au.total} criteria · {inr(au.value_delivered_inr)} of {inr(au.value_total_inr)} verified</span>
              </div>
              {au.verdict.level !== "satisfied" && (
                <div className="rounded-xl border border-amber-400/30 bg-amber-400/10 p-3 text-sm text-amber-100">
                  <div className="mb-1 font-semibold">The client will see: {au.verdict.headline}</div>
                  <ul className="list-disc pl-5 text-xs text-amber-100/80">{au.verdict.missing.map((m) => <li key={m}>{m}</li>)}</ul>
                  <p className="mt-1 text-xs text-amber-100/70">Fix these and re-run the audit before submitting.</p>
                </div>
              )}
              {au.security_warnings.length > 0 && (
                <div className="rounded-xl border border-rose-400/30 bg-rose-500/10 p-3 text-xs text-rose-200">
                  Remove secrets / .env files from the zip before handover ({au.security_warnings.length} found). The handover budget is withheld until you do.
                </div>
              )}
              {p.feedback && (
                <div className="flex gap-2 rounded-xl border border-rose-400/30 bg-rose-500/10 p-3 text-sm text-rose-100">
                  <MessageSquare size={16} className="mt-0.5 shrink-0" />
                  <div><div className="font-semibold">The client asked for changes</div><p className="text-rose-100/80">{p.feedback.message}</p></div>
                </div>
              )}
              <Btn variant="success" className="w-full" disabled={!canSubmit || busy} onClick={a.submit}>
                <Send size={16} /> {needAdvance ? "Waiting for the client's advance" : p.pending_quote ? "Quote the extra change first" : p.status === "changes_requested" ? "Resubmit to client" : p.status === "submitted" || p.paid ? "Submitted to client" : "Submit to client for review"}
              </Btn>
            </div>
          )}
        </Glass>
      </div>

      <div className="space-y-5 lg:col-span-2">
        <Glass className="p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-bold">Project status</h2>
            {p && <ProjectStatus status={p.status} />}
          </div>
          {p ? <Stepper status={p.status} /> : <p className="text-sm text-violet-200/60">Create a project to get started.</p>}
        </Glass>

        <Glass className="p-5">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-bold">Escrow and kill-switch</h2>
            <Chip tone="slate">Problem #64</Chip>
          </div>
          {p ? (
            <>
              <div className="mb-4 rounded-xl bg-white/5 p-4">
                <div className="text-xs text-violet-300/70">Invoice {p.invoice.number}</div>
                <div className="text-3xl font-extrabold">{inr(p.money.grand_total)}</div>
              </div>
              <KillSwitch p={p} a={a} busy={busy} />
              {p.status === "submitted" && !p.paid && <Btn variant="ghost" className="mt-2 w-full" disabled={busy} onClick={a.expireReview}>Simulate review window ending</Btn>}
              <Btn variant="ghost" className="mt-3 w-full" onClick={() => setView("live")}>Open live preview <ArrowRight size={14} /></Btn>
            </>
          ) : (
            <p className="text-sm text-violet-200/60">The escrow invoice and hosted-preview lock are created with the contract.</p>
          )}
        </Glass>

        {p && <Protection p={p} role="freelancer" a={a} busy={busy} plan={plan} />}
      </div>
    </div>
  );
}
