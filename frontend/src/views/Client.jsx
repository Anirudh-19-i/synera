import { useState } from "react";
import { CheckCircle2, XCircle, AlertTriangle, ExternalLink, Download, Fingerprint, ShieldCheck, ShieldAlert, ShieldX, MessageSquare, Hourglass } from "lucide-react";
import { downloadFile } from "../api.js";
import { Glass, Btn, Chip, Ring, StateChip, inr } from "../ui.jsx";
import { CostSplit, ProjectStatus } from "../cost.jsx";
import Protection from "./Protection.jsx";

const VERDICT = {
  satisfied: { Icon: ShieldCheck, box: "border-emerald-400/30 bg-emerald-400/10", ico: "text-emerald-300" },
  partial: { Icon: ShieldAlert, box: "border-amber-400/30 bg-amber-400/10", ico: "text-amber-300" },
  not_met: { Icon: ShieldX, box: "border-rose-400/30 bg-rose-500/10", ico: "text-rose-300" },
};

function Empty() {
  return (
    <Glass className="mx-auto max-w-xl p-10 text-center">
      <p className="text-violet-200/80">No projects shared with you yet. When a freelancer creates a project for your email address, it appears here.</p>
    </Glass>
  );
}

export default function Client({ p, a, busy, mint, setView }) {
  const [note, setNote] = useState("");
  const [asking, setAsking] = useState(false);
  const [dlErr, setDlErr] = useState("");
  if (!p) return <Empty />;

  const au = p.audit;
  const paid = !!p.paid;
  const total = p.invoice.total_inr;
  const m = p.money;
  const signed = !!p.agreement.client_signed_at;
  const rv = p.revisions;

  // Before the freelancer submits, the client only sees the agreed scope and cost split.
  if (!au) {
    return (
      <div className="grid gap-5 lg:grid-cols-5">
        <Glass className="p-5 lg:col-span-3">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <h2 className="text-xl font-bold">{p.contract.title}</h2>
            <ProjectStatus status={p.status} />
          </div>
          <p className="mb-4 text-sm text-violet-200/70">From {p.freelancer_name}. {p.contract.summary}</p>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-violet-300/70">What you asked for</h3>
          <div className="space-y-2">
            {p.contract.criteria.map((x) => (
              <div key={x.id} className="flex gap-2 rounded-xl bg-white/5 p-3 text-sm"><span className="font-mono text-xs text-violet-300">{x.id}</span>{x.description}</div>
            ))}
          </div>
          <div className="mt-4 flex items-center gap-2 rounded-xl bg-white/5 p-3 text-sm text-violet-200/80">
            <Hourglass size={16} /> Work in progress. You will see the verification report once the freelancer submits.
          </div>
        </Glass>
        <div className="space-y-5 lg:col-span-2">
          <Glass className="p-5">
            <h3 className="mb-1 font-bold">How your {inr(total)} is allocated</h3>
            <p className="mb-4 text-xs text-violet-300/70">Nothing is released until you review and pay.</p>
            <CostSplit items={p.breakdown} total={total} />
          </Glass>
          <Protection p={p} role="client" a={a} busy={busy} />
        </div>
      </div>
    );
  }

  const v = au.verdict;
  const { Icon, box, ico } = VERDICT[v.level];
  const canAct = p.status === "submitted" && !paid;

  return (
    <div className="space-y-5">
      <Glass className={`border p-5 ${box}`}>
        <div className="flex flex-wrap items-start gap-4">
          <Icon size={38} className={ico} />
          <div className="min-w-0 flex-1">
            <div className="text-xs font-semibold uppercase tracking-wider text-violet-200/60">Did the freelancer deliver what you asked for?</div>
            <h2 className="text-2xl font-extrabold">{v.headline}</h2>
            <p className="mt-1 text-sm text-violet-100/80">{v.detail}</p>
            {v.missing.length > 0 && (
              <ul className="mt-2 list-disc pl-5 text-sm text-violet-100/90">{v.missing.map((m) => <li key={m}>{m}</li>)}</ul>
            )}
            {v.flags.map((f) => (
              <div key={f} className="mt-2 flex items-center gap-2 text-sm text-amber-200"><AlertTriangle size={15} /> {f}</div>
            ))}
          </div>
          <div className="text-right">
            <div className="text-xs text-violet-200/60">Verified in the code</div>
            <div className="text-2xl font-extrabold">{inr(au.value_delivered_inr)}</div>
            <div className="text-xs text-violet-200/60">of {inr(total)}</div>
          </div>
        </div>
      </Glass>

      <div className="grid gap-5 lg:grid-cols-5">
        <div className="space-y-5 lg:col-span-3">
          <Glass className="p-5">
            <div className="flex flex-wrap items-center gap-5">
              <Ring score={au.score} />
              <div className="flex-1">
                <Chip tone={au.score >= 90 ? "emerald" : "amber"}>{au.badge}</Chip>
                <h3 className="mt-2 text-lg font-bold">{p.contract.title}</h3>
                <p className="text-sm text-violet-200/70">{au.passed} of {au.total} agreed requirements were found in the delivered source.</p>
                <p className="mt-1 text-xs text-violet-300/60">Static analysis: confirms each requirement exists in the code, with file and line proof. It does not run the app.</p>
                <p className="mt-1 font-mono text-[11px] text-violet-300/50">zip sha256 {au.zip_sha256.slice(0, 24)}…</p>
              </div>
            </div>
          </Glass>

          <Glass className="p-5">
            <h3 className="mb-3 font-bold">Requirement by requirement</h3>
            <div className="space-y-2.5">
              {au.results.map((r) => (
                <div key={r.id} className="rounded-xl bg-white/5 p-3">
                  <div className="flex items-start gap-2.5">
                    {r.passed ? <CheckCircle2 size={18} className="mt-0.5 shrink-0 text-emerald-400" /> : <XCircle size={18} className="mt-0.5 shrink-0 text-rose-400" />}
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2 text-sm font-semibold">
                        <span className="font-mono text-xs text-violet-300">{r.id}</span> {r.description}
                        {r.method === "ai-grounded" && <Chip tone="violet">AI, evidence verified</Chip>}
                      </div>
                      {r.passed ? (
                        <>
                          <div className="mt-1 font-mono text-xs text-emerald-300">{r.file}:{r.line}</div>
                          <pre className="mt-1 overflow-x-auto rounded-lg bg-black/30 p-2 text-[11px] text-violet-100/80">{r.snippet}</pre>
                        </>
                      ) : (
                        <p className="mt-1 text-xs text-rose-300/90">{r.note}</p>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            {au.security_warnings.length > 0 && (
              <div className="mt-4 rounded-xl border border-amber-400/30 bg-amber-400/10 p-3 text-sm text-amber-200">
                <div className="mb-1 flex items-center gap-2 font-semibold"><AlertTriangle size={16} /> Security warnings in the deliverable</div>
                {au.security_warnings.map((w, i) => (
                  <div key={i} className="font-mono text-xs">{w.type}: {w.file}{w.line ? `:${w.line}` : ""}</div>
                ))}
              </div>
            )}
          </Glass>

          <Glass className="p-5">
            <h3 className="mb-1 font-bold">What your money is paying for</h3>
            <p className="mb-4 text-xs text-violet-300/70">Each line shows its share of the budget and how much of it is backed by the delivered code.</p>
            <CostSplit items={p.breakdown} total={total} audit={au} />
          </Glass>
        </div>

        <div className="space-y-5 lg:col-span-2">
          <Glass className="p-5">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="font-bold">Your decision</h3>
              <StateChip state={p.drm_state} />
            </div>
            <div className="rounded-xl bg-white/5 p-4">
              <div className="text-xs text-violet-300/70">{p.invoice.number}</div>
              <div className="text-3xl font-extrabold">{inr(paid ? m.grand_total : m.balance_due)}</div>
              <div className="text-xs text-violet-300/60">{paid ? "paid in full" : m.advance_paid ? `balance after ${inr(m.advance_paid)} advance` : "balance due"}{m.extras ? ` · includes ${inr(m.extras)} extra work` : ""}{m.late_fee ? ` · includes ${inr(m.late_fee)} late fee` : ""}</div>
            </div>
            {p.preview_url ? (
              <a href={p.preview_url} target="_blank" rel="noreferrer" className="mt-3 block">
                <Btn variant="ghost" className="w-full"><ExternalLink size={15} /> Open protected preview</Btn>
              </a>
            ) : <p className="mt-3 text-xs text-violet-300/60">No previewable site in this delivery.</p>}

            {p.status === "changes_requested" && p.feedback && (
              <div className="mt-3 flex gap-2 rounded-xl border border-rose-400/30 bg-rose-500/10 p-3 text-sm text-rose-100">
                <MessageSquare size={16} className="mt-0.5 shrink-0" />
                <div><div className="font-semibold">You asked for changes</div><p className="text-rose-100/80">{p.feedback.message}</p><p className="mt-1 text-xs text-rose-100/60">Waiting for the freelancer to resubmit.</p></div>
              </div>
            )}

            {!paid && v.level !== "satisfied" && canAct && (
              <p className="mt-3 text-xs text-amber-200">Some requirements were not found. Consider requesting changes before you pay.</p>
            )}

            {!paid && (
              <>
                {!signed && <p className="mt-3 text-xs text-amber-200">Sign the agreement (below) before you pay.</p>}
                <Btn variant="success" className="mt-3 w-full" disabled={busy || !canAct || !signed} onClick={a.startPay}>
                  {canAct ? `Accept and pay ${inr(m.balance_due)}` : "Payment unavailable until resubmitted"}
                </Btn>
                {canAct && !asking && <Btn variant="ghost" className="mt-2 w-full" onClick={() => setAsking(true)}>Request changes</Btn>}
                {canAct && asking && (
                  <div className="mt-2 space-y-2">
                    <p className="text-xs text-violet-300/70">{rv.used < rv.included ? `This is revision ${rv.used + 1} of ${rv.included} included.` : "You have used all included revisions. The freelancer will quote this extra work and you will see the price before paying."}</p>
                    <textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} className="w-full resize-none p-3 text-sm" placeholder="What is missing or wrong?" />
                    <div className="flex gap-2">
                      <Btn variant="ghost" className="flex-1" onClick={() => setAsking(false)}>Cancel</Btn>
                      <Btn className="flex-1" disabled={busy || note.trim().length < 3}
                        onClick={async () => { const ok = await a.requestChanges(note); if (ok) { setNote(""); setAsking(false); } }}>Send to freelancer</Btn>
                    </div>
                  </div>
                )}
              </>
            )}

            {paid && (
              <>
                <Btn variant="success" className="mt-3 w-full"
                  onClick={() => downloadFile(`/api/download/${p.id}`, "client", `${p.contract.title.replace(/\s+/g, "_")}_source.zip`).catch((e) => setDlErr(e.message))}>
                  <Download size={16} /> Download source (.zip)
                </Btn>
                {dlErr && <p className="mt-2 text-xs text-rose-300">{dlErr}</p>}
              </>
            )}
          </Glass>

          <Protection p={p} role="client" a={a} busy={busy} />

          {paid && mint && (
            <Glass className="p-5">
              <h3 className="mb-2 flex items-center gap-2 font-bold"><Fingerprint size={18} className="text-emerald-300" /> Delivery proof minted</h3>
              <p className="mb-2 text-xs text-violet-200/70">Receipt {p.paid.receipt}. Added, anonymized, to {p.freelancer_name}'s public folio.</p>
              <div className="break-all rounded-xl bg-black/30 p-3 font-mono text-[11px] text-emerald-300">{mint.hash}</div>
              <div className="mt-3 flex gap-2">
                <a href={`/verify/${mint.hash}`} target="_blank" rel="noreferrer" className="flex-1"><Btn variant="ghost" className="w-full">Verify hash</Btn></a>
                <Btn className="flex-1" onClick={() => setView("folio")}>View folio</Btn>
              </div>
            </Glass>
          )}
        </div>
      </div>
    </div>
  );
}
