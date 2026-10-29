import { useEffect, useState } from "react";
import { TrendingUp, Clock, Hammer, AlertOctagon, Download, Users, Calculator, SearchCheck, Plus, Gauge } from "lucide-react";
import { api, downloadFile } from "../api.js";
import { Glass, Btn, Chip, inr } from "../ui.jsx";
import { ProjectStatus } from "../cost.jsx";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function Kpi({ icon: Icon, label, value, sub, light }) {
  return (
    <div className={light ? "paper p-5" : "glass p-5"}>
      <div className={`mb-4 flex items-center justify-between text-xs font-semibold uppercase tracking-wider ${light ? "muted" : "text-violet-300/70"}`}>
        {label}<Icon size={16} />
      </div>
      <div className="text-3xl font-extrabold tracking-tight">{value}</div>
      {sub && <div className={`mt-1 text-xs ${light ? "muted" : "text-violet-300/60"}`}>{sub}</div>}
    </div>
  );
}

function Bars({ data }) {
  const max = Math.max(1, ...data.map((d) => d.earned_inr));
  return (
    <div className="flex items-end gap-3" style={{ height: 176 }}>
      {data.map((d) => {
        const h = d.earned_inr ? Math.max(8, Math.round((d.earned_inr / max) * 120)) : 4;
        return (
          <div key={d.month} className="flex flex-1 flex-col items-center justify-end gap-2">
            <span className="text-[10px] text-violet-300/70">{d.earned_inr ? inr(d.earned_inr) : ""}</span>
            <div className={`w-full max-w-[56px] rounded-t-xl ${d.earned_inr ? "bg-white" : "bg-white/10"}`} style={{ height: h }} title={`${d.month}: ${inr(d.earned_inr)}`} />
            <span className="text-[11px] text-violet-300/70">{MONTHS[+d.month.slice(5) - 1]}</span>
          </div>
        );
      })}
    </div>
  );
}

const METHODS = [
  ["Domestic UPI / bank transfer", 0, 0],
  ["Specialist transfer service", 1.0, 0],
  ["Bank wire (SWIFT)", 3.0, 1000],
  ["Wallet-style platform", 5.0, 0],
];

function Estimator() {
  const [amount, setAmount] = useState(500);
  const [cur, setCur] = useState("USD");
  const [rate, setRate] = useState(85);
  const [mi, setMi] = useState(2);
  const gross = Math.round(amount * (cur === "INR" ? 1 : rate));
  const [, pct, flat] = METHODS[mi];
  const fee = Math.round(gross * pct / 100) + flat;
  return (
    <Glass className="p-5">
      <h3 className="mb-1 flex items-center gap-2 font-bold"><Calculator size={18} className="text-violet-300" /> Overseas payout estimator</h3>
      <p className="mb-3 text-xs text-violet-300/70">Rough planning numbers. Fee presets are assumptions, so check your provider's current rates and enter today's exchange rate.</p>
      <div className="grid grid-cols-3 gap-2">
        <input type="number" value={amount} onChange={(e) => setAmount(+e.target.value)} className="col-span-2 px-3 py-2 text-sm" />
        <select value={cur} onChange={(e) => setCur(e.target.value)} className="field px-2 py-2 text-sm">{["USD", "EUR", "GBP", "AED", "INR"].map((c) => <option key={c} className="bg-zinc-900">{c}</option>)}</select>
        {cur !== "INR" && <label className="col-span-3 flex items-center gap-2 text-xs text-violet-300/80">₹ per {cur}<input type="number" value={rate} onChange={(e) => setRate(+e.target.value)} className="w-24 px-2 py-1.5 text-sm" /></label>}
      </div>
      <select value={mi} onChange={(e) => setMi(+e.target.value)} className="field mt-2 w-full px-3 py-2 text-sm">
        {METHODS.map((m, i) => <option key={m[0]} value={i} className="bg-zinc-900">{m[0]} (~{m[1]}%{m[2] ? ` + ₹${m[2]}` : ""})</option>)}
      </select>
      <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
        <div className="rounded-xl bg-white/5 p-2"><div className="text-base font-bold">{inr(gross)}</div>Before fees</div>
        <div className="rounded-xl bg-white/5 p-2"><div className="text-base font-bold text-amber-300">−{inr(fee)}</div>Fees</div>
        <div className="rounded-xl bg-white p-2 text-black"><div className="text-base font-bold">{inr(gross - fee)}</div>You receive</div>
      </div>
      <p className="mt-2 text-[11px] text-violet-300/60">Quote overseas clients enough to cover the fees: add {inr(fee)} to the price.</p>
    </Glass>
  );
}

export function PaymentCheck() {
  const [id, setId] = useState("");
  const [res, setRes] = useState(null);
  return (
    <Glass className="p-5">
      <h3 className="mb-1 flex items-center gap-2 font-bold"><SearchCheck size={18} className="text-violet-300" /> Check a payment reference</h3>
      <p className="mb-3 text-xs text-violet-300/70">A screenshot proves nothing. Paste the payment ID the client received and Synera tells you whether the gateway really settled it.</p>
      <div className="flex gap-2">
        <input type="text" value={id} onChange={(e) => setId(e.target.value)} placeholder="pay_xxxxxxxxxxxxxx" className="flex-1 px-3 py-2 text-sm" />
        <Btn disabled={id.trim().length < 6} onClick={async () => setRes(await api(`/api/payments/verify/${encodeURIComponent(id.trim())}`))}>Check</Btn>
      </div>
      {res && (
        <div className={`mt-3 rounded-xl border p-3 text-sm ${res.verified ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-100" : "border-rose-400/30 bg-rose-500/10 text-rose-100"}`}>
          {res.verified ? `Verified: ${inr(res.amount_inr)} ${res.kind}${res.invoice_number ? " for " + res.invoice_number : ""}.` : res.message}
        </div>
      )}
    </Glass>
  );
}

export default function Dashboard({ a, setView, setPid, plan, busy }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    const load = () => api("/api/dashboard", { as: "freelancer" }).then(setD).catch((e) => setErr(e.message));
    load();
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, []);
  if (!d) return <Glass className="mx-auto max-w-xl p-10 text-center text-violet-200/70">{err || "Loading your dashboard…"}</Glass>;
  const T = d.totals, pl = d.plan;
  const open = (id) => { setPid(id); setView("workspace"); };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <span className="pill">Overview</span>
          <h2 className="mt-2 text-3xl font-extrabold">Your freelance business</h2>
        </div>
        <div className="flex gap-2">
          <Btn variant="ghost" onClick={() => downloadFile("/api/dashboard/export.csv", "freelancer", "synera_earnings.csv").catch((e) => setErr(e.message))}><Download size={15} /> CSV {plan !== "pro" && "(Pro)"}</Btn>
          <Btn onClick={() => setView("workspace")}><Plus size={15} /> New project</Btn>
        </div>
      </div>
      {err && <div className="rounded-xl border border-amber-400/30 bg-amber-400/10 px-4 py-2 text-sm text-amber-100">{err}</div>}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi light icon={TrendingUp} label="Earned" value={inr(T.earned_inr)} sub={`${T.completed} of ${T.projects} projects paid`} />
        <Kpi icon={Clock} label="Awaiting payment" value={inr(T.awaiting_inr)} sub="Submitted, client reviewing" />
        <Kpi icon={Hammer} label="In progress" value={inr(T.in_progress_inr)} sub={`${T.active} active project${T.active === 1 ? "" : "s"}`} />
        <Kpi icon={AlertOctagon} label="Overdue" value={inr(T.overdue_inr)} sub={T.overdue_inr ? "Review window ended" : "Nothing overdue"} />
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <Glass className="p-5 lg:col-span-2">
          <div className="mb-4 flex items-center justify-between"><h3 className="font-bold">Money received, last 6 months</h3><Chip tone="slate">{T.avg_score != null ? `Avg spec score ${T.avg_score}%` : "No audits yet"}</Chip></div>
          <Bars data={d.monthly} />
        </Glass>
        <Glass className="p-5">
          <h3 className="mb-3 flex items-center gap-2 font-bold"><Gauge size={18} className="text-violet-300" /> Your plan</h3>
          <div className="text-2xl font-extrabold">{pl.name}</div>
          <p className="mb-3 text-xs text-violet-300/70">{pl.limit ? `${pl.active_projects} of ${pl.limit} active projects used` : `${pl.active_projects} active projects, no limit`}</p>
          {pl.limit && <div className="mb-3 h-2 overflow-hidden rounded-full bg-white/10"><div className="h-full bg-white" style={{ width: `${Math.min(100, (pl.active_projects / pl.limit) * 100)}%` }} /></div>}
          <Btn variant={pl.id === "pro" ? "ghost" : "primary"} className="w-full" onClick={() => setView("plan")}>{pl.id === "pro" ? "Manage plan" : "Upgrade to Pro"}</Btn>
        </Glass>
      </div>

      <Glass className="overflow-hidden p-0">
        <div className="flex items-center justify-between p-5 pb-3"><h3 className="font-bold">Project records</h3><span className="text-xs text-violet-300/60">Every project, what it paid, and where it stands</span></div>
        {d.projects.length === 0 ? <p className="p-8 text-center text-sm text-violet-200/70">No projects yet. Paste a client brief in Projects to start.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wider text-violet-300/60"><tr>
                {["Project", "Client", "Status", "Price", "Received", "Outstanding", "Score", "Days to pay"].map((h) => <th key={h} className="px-5 py-2 font-medium">{h}</th>)}
              </tr></thead>
              <tbody>
                {d.projects.map((r) => (
                  <tr key={r.id} onClick={() => open(r.id)} className="cursor-pointer border-t border-white/10 hover:bg-white/5">
                    <td className="px-5 py-3"><div className="font-semibold">{r.title}</div><div className="font-mono text-[11px] text-violet-300/50">{r.invoice}</div></td>
                    <td className="px-5 py-3">{r.client}</td>
                    <td className="px-5 py-3"><ProjectStatus status={r.status} />{r.overdue && <Chip tone="rose" className="ml-1">overdue</Chip>}</td>
                    <td className="px-5 py-3">{inr(r.total_inr)}{r.extras_inr ? <span className="text-[11px] text-violet-300/60"> (+extras)</span> : null}</td>
                    <td className="px-5 py-3 text-emerald-300">{inr(r.received_inr)}</td>
                    <td className="px-5 py-3">{r.outstanding_inr ? inr(r.outstanding_inr) : "—"}</td>
                    <td className="px-5 py-3">{r.score != null ? r.score + "%" : "—"}</td>
                    <td className="px-5 py-3">{r.days_to_pay != null ? r.days_to_pay + "d" : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Glass>

      <div className="grid gap-5 lg:grid-cols-3">
        <Glass className="p-5">
          <h3 className="mb-3 flex items-center gap-2 font-bold"><Users size={18} className="text-violet-300" /> Clients</h3>
          {d.clients.length === 0 ? <p className="text-sm text-violet-200/60">Clients appear once you create a project.</p> : (
            <div className="space-y-2">
              {d.clients.map((c) => (
                <div key={c.email} className="rounded-xl bg-white/5 p-3 text-sm">
                  <div className="flex items-center justify-between"><b>{c.client}</b><Chip tone={c.label === "Overdue" ? "rose" : c.label === "Pays promptly" ? "emerald" : "slate"}>{c.label}</Chip></div>
                  <div className="text-xs text-violet-300/70">{c.projects} project(s) · {inr(c.total_paid_inr)} paid{c.avg_days_to_pay != null ? ` · avg ${c.avg_days_to_pay}d to pay` : ""}</div>
                </div>
              ))}
            </div>
          )}
        </Glass>
        <Estimator />
        <PaymentCheck />
      </div>
    </div>
  );
}
