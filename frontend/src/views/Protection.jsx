import { useState } from "react";
import {
  FileSignature, Wallet, RefreshCw, Hourglass, BellRing, Archive, History, CheckCircle2, Circle, Copy, Check, MessageCircle, Mail, Lock, AlertTriangle,
} from "lucide-react";
import { api, downloadFile } from "../api.js";
import { Glass, Btn, Chip, inr, useCountdown, fmtLeft } from "../ui.jsx";

const when = (iso) => new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const EVENT = {
  project_created: "Project created", agreement_signed: "Agreement signed", advance_paid: "Advance paid", audit_run: "Audit run",
  submitted: "Submitted to client", changes_requested: "Changes requested", quote_set: "Extra work quoted", reminder_sent: "Reminder sent",
  paid: "Paid in full", review_window_expired: "Review window ended", evidence_exported: "Evidence exported",
};

function Row({ ok, children }) {
  return (
    <div className="flex items-start gap-2 text-sm">
      {ok ? <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-emerald-400" /> : <Circle size={16} className="mt-0.5 shrink-0 text-violet-400/60" />}
      <span className={ok ? "text-violet-100" : "text-violet-200/70"}>{children}</span>
    </div>
  );
}

function Agreement({ p, role, a }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState(null);
  const ag = p.agreement;
  async function toggle() {
    if (!open && !data) setData(await api(`/api/projects/${p.id}/agreement`, { as: role }));
    setOpen(!open);
  }
  return (
    <div>
      <div className="space-y-1.5">
        <Row ok>Freelancer signed {when(ag.freelancer_signed_at)}</Row>
        <Row ok={!!ag.client_signed_at}>{ag.client_signed_at ? `Signed by ${ag.client_signed_by || "client"} · ${when(ag.client_signed_at)}` : "Waiting for the client to sign"}</Row>
        <p className="pl-6 font-mono text-[10px] text-violet-300/50">sha256 {ag.sha256.slice(0, 32)}…</p>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Btn variant="ghost" onClick={toggle}>{open ? "Hide agreement" : "Read agreement"}</Btn>
        <Btn variant="ghost" onClick={() => downloadFile(`/api/projects/${p.id}/agreement?format=html`, role, `agreement_${p.invoice.number}.html`)}>Download</Btn>
        {role === "client" && !ag.client_signed_at && <Btn onClick={a.sign}>Accept and sign</Btn>}
      </div>
      {open && data && (
        <div className="mt-3 max-h-80 space-y-3 overflow-y-auto rounded-xl bg-black/30 p-4 text-sm">
          <div className={`text-xs ${data.integrity_ok ? "text-emerald-300" : "text-rose-300"}`}>{data.integrity_ok ? "Hash verified: this text is unchanged since the project was created." : "Warning: the stored text does not match its hash."}</div>
          {data.clauses.map((c) => (
            <div key={c.title}><div className="font-semibold text-violet-100">{c.title}</div><p className="whitespace-pre-line text-violet-200/70">{c.text}</p></div>
          ))}
        </div>
      )}
    </div>
  );
}

function Money({ p }) {
  const m = p.money;
  const line = (k, v, tone = "") => (
    <div className={`flex justify-between text-sm ${tone}`}><span className="text-violet-200/70">{k}</span><span className="font-semibold">{v}</span></div>
  );
  return (
    <div className="space-y-1.5 rounded-xl bg-white/5 p-3">
      {line("Agreed price", inr(m.base))}
      {m.extras > 0 && line("Extra work (quoted)", "+ " + inr(m.extras))}
      {m.late_fee > 0 && line("Late fee", "+ " + inr(m.late_fee), "text-amber-300")}
      {m.advance_paid > 0 && line("Advance paid", "− " + inr(m.advance_paid), "text-emerald-300")}
      <div className="flex justify-between border-t border-white/10 pt-1.5 text-base font-bold"><span>{p.paid ? "Paid in full" : "Balance due"}</span><span>{inr(p.paid ? m.grand_total : m.balance_due)}</span></div>
    </div>
  );
}

export default function Protection({ p, role, a, busy, plan }) {
  const [quote, setQuote] = useState("");
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState(null);
  const [err, setErr] = useState("");
  const [copied, setCopied] = useState(false);
  const left = useCountdown(p?.review?.seconds_remaining ?? 0);
  if (!p) return null;
  const t = p.terms, rv = p.revisions, isF = role === "freelancer";
  const needAdv = t.advance_inr > 0;
  const signed = !!p.agreement.client_signed_at;
  const submitted = p.status === "submitted";

  const guard = async (fn) => { setErr(""); try { await fn(); } catch (e) { setErr(e.message); } };

  return (
    <div className="space-y-5">
      <Glass className="p-5">
        <h3 className="mb-3 flex items-center gap-2 font-bold"><FileSignature size={18} className="text-violet-300" /> Agreement</h3>
        <Agreement p={p} role={role} a={a} />
      </Glass>

      <Glass className="p-5">
        <h3 className="mb-3 flex items-center gap-2 font-bold"><Wallet size={18} className="text-violet-300" /> Payment schedule</h3>
        <div className="mb-3 space-y-1.5">
          {needAdv ? (
            <Row ok={p.funded}>Advance {t.advance_pct}% · {inr(t.advance_inr)} {p.funded ? "secured before delivery" : "due before the freelancer submits"}</Row>
          ) : <Row ok>No advance on this project</Row>}
          <Row ok={!!p.paid}>Balance on acceptance · {inr(p.money.base + p.money.extras - (needAdv ? t.advance_inr : 0))}{p.money.late_fee ? ` + ${inr(p.money.late_fee)} late fee` : ""}</Row>
        </div>
        <Money p={p} />
        {role === "client" && needAdv && !p.funded && !p.paid && (
          signed ? <Btn className="mt-3 w-full" onClick={a.payAdvance}>Pay advance {inr(t.advance_inr)}</Btn>
                 : <p className="mt-3 text-xs text-amber-200">Sign the agreement to unlock the advance payment.</p>
        )}
        {isF && needAdv && !p.funded && <p className="mt-3 text-xs text-amber-200">You can build and audit now. Submitting to the client unlocks after their advance is paid.</p>}
        <p className="mt-3 text-[11px] text-violet-300/60">Sandbox gateway. Only gateway-signed payments count. A payment screenshot is not proof.</p>
      </Glass>

      <Glass className="p-5">
        <h3 className="mb-3 flex items-center gap-2 font-bold"><RefreshCw size={18} className="text-violet-300" /> Revisions and extra work</h3>
        <div className="mb-3 flex items-center gap-3">
          <div className="flex gap-1">
            {Array.from({ length: Math.max(rv.included, rv.used) }).map((_, i) => (
              <span key={i} className={`h-2.5 w-8 rounded-full ${i < rv.used ? (i >= rv.included ? "bg-amber-400" : "bg-white") : "bg-white/15"}`} />
            ))}
          </div>
          <span className="text-xs text-violet-200/70">{rv.used} used · {rv.included} included</span>
        </div>
        {rv.log.map((r, i) => (
          <div key={i} className="mb-1.5 rounded-lg bg-white/5 p-2 text-xs text-violet-100/80">
            <span className="text-violet-300/60">{when(r.at)}</span> {r.message}
            {r.billable && <Chip tone="amber" className="ml-2">{r.fee_inr == null ? "needs quote" : r.fee_inr ? `extra ${inr(r.fee_inr)}` : "waived"}</Chip>}
          </div>
        ))}
        {isF && p.pending_quote && (
          <div className="mt-3 rounded-xl border border-amber-400/30 bg-amber-400/10 p-3">
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-amber-100"><AlertTriangle size={15} /> This request is beyond your included revisions</div>
            <div className="grid gap-2 sm:grid-cols-2">
              <input type="number" min={0} placeholder="Fee in ₹ (0 to waive)" value={quote} onChange={(e) => setQuote(e.target.value)} className="px-3 py-2 text-sm" />
              <input type="text" placeholder="What it covers" value={note} onChange={(e) => setNote(e.target.value)} className="px-3 py-2 text-sm" />
            </div>
            <Btn className="mt-2 w-full" disabled={busy || quote === ""} onClick={() => guard(() => a.quote(+quote, note))}>Send quote to client</Btn>
          </div>
        )}
        {p.extras.map((x) => <div key={x.id} className="mt-2 flex justify-between rounded-lg bg-white/5 p-2 text-xs"><span>{x.label}</span><b>{inr(x.amount_inr)}</b></div>)}
        {role === "client" && <p className="mt-3 text-[11px] text-violet-300/60">Extra rounds are quoted by the freelancer and shown here before you pay. Nothing is added without a quote.</p>}
      </Glass>

      {submitted && (
        <Glass className="p-5">
          <h3 className="mb-3 flex items-center gap-2 font-bold"><Hourglass size={18} className="text-violet-300" /> Review window</h3>
          {p.review.expired ? (
            <div className="rounded-xl border border-amber-400/30 bg-amber-400/10 p-3 text-sm text-amber-100">
              The {p.review.days}-day review window has ended. Under clause 6 the delivery is treated as accepted.
              {p.money.late_fee > 0 && ` A late fee of ${inr(p.money.late_fee)} has been added.`}
            </div>
          ) : (
            <div className="flex items-center justify-between rounded-xl bg-white/5 p-3">
              <span className="text-sm text-violet-200/80">Time left to approve or request changes</span>
              <span className="font-mono text-lg">{fmtLeft(left)}</span>
            </div>
          )}
          {isF && (
            <div className="mt-3">
              <Btn variant="ghost" className="w-full" disabled={busy} onClick={() => guard(async () => setMsg(await a.remind()))}>
                <BellRing size={15} /> {p.reminders.length === 0 ? "Send payment reminder" : p.reminders.length === 1 ? "Send firm reminder" : "Generate final notice"}
              </Btn>
              {msg && (
                <div className="mt-3 rounded-xl bg-black/30 p-3">
                  <div className="mb-1 flex items-center gap-2 text-xs"><Chip tone={msg.level === 3 ? "rose" : msg.level === 2 ? "amber" : "slate"}>Level {msg.level}</Chip><b>{msg.subject}</b></div>
                  <p className="text-sm text-violet-100/85">{msg.body}</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <a href={msg.whatsapp_url} target="_blank" rel="noreferrer"><Btn variant="ghost"><MessageCircle size={14} /> WhatsApp</Btn></a>
                    <a href={msg.mailto_url}><Btn variant="ghost"><Mail size={14} /> Email</Btn></a>
                    <Btn variant="ghost" onClick={() => { navigator.clipboard?.writeText(msg.body); setCopied(true); setTimeout(() => setCopied(false), 1500); }}>
                      {copied ? <Check size={14} /> : <Copy size={14} />} Copy
                    </Btn>
                  </div>
                </div>
              )}
            </div>
          )}
        </Glass>
      )}

      {isF && (
        <Glass className="p-5">
          <h3 className="mb-1 flex items-center gap-2 font-bold"><Archive size={18} className="text-violet-300" /> Evidence pack {plan !== "pro" && <Chip tone="amber"><Lock size={11} /> Pro</Chip>}</h3>
          <p className="mb-3 text-xs text-violet-300/70">Agreement, audit with file and line proof, payments and timeline, sealed with a SHA-256. Use it for a dispute, a chargeback or a small-claims notice.</p>
          <div className="flex gap-2">
            <Btn variant="ghost" className="flex-1" onClick={() => guard(() => downloadFile(`/api/projects/${p.id}/evidence?format=html`, "freelancer", `evidence_${p.invoice.number}.html`))}>Download (HTML)</Btn>
            <Btn variant="ghost" className="flex-1" onClick={() => guard(() => downloadFile(`/api/projects/${p.id}/evidence`, "freelancer", `evidence_${p.invoice.number}.json`))}>JSON</Btn>
          </div>
        </Glass>
      )}

      {err && <div className="rounded-xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{err}</div>}

      <Glass className="p-5">
        <h3 className="mb-3 flex items-center gap-2 font-bold"><History size={18} className="text-violet-300" /> Timeline</h3>
        <ol className="space-y-2 border-l border-white/10 pl-4">
          {[...p.timeline].reverse().map((e, i) => (
            <li key={i} className="relative text-sm">
              <span className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-white/60" />
              <span className="font-semibold text-violet-100">{EVENT[e.event] || e.event}</span>
              <span className="text-violet-300/60"> · {e.actor} · {when(e.at)}</span>
              {e.detail && <div className="text-xs text-violet-200/60">{e.detail}</div>}
            </li>
          ))}
        </ol>
      </Glass>
    </div>
  );
}
