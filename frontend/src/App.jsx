import { useCallback, useEffect, useRef, useState } from "react";
import { ShieldCheck, RotateCcw, Zap, LogOut } from "lucide-react";
import { api, getActive, getSessions, setActive, dropSession } from "./api.js";
import { Btn, Chip, StateChip } from "./ui.jsx";
import Auth from "./Auth.jsx";
import Landing from "./Landing.jsx";
import Freelancer from "./views/Freelancer.jsx";
import Client from "./views/Client.jsx";
import Live from "./views/Live.jsx";
import Folio from "./views/Folio.jsx";
import Dashboard from "./views/Dashboard.jsx";
import Plan from "./views/Plan.jsx";
import Invoice from "./views/Invoice.jsx";
import PayModal from "./PayModal.jsx";

const TABS = {
  freelancer: [["dashboard", "Dashboard"], ["workspace", "Projects"], ["invoice", "Invoices"], ["live", "Live preview"], ["folio", "Public folio"], ["plan", "Plan"]],
  client: [["review", "Review & pay"], ["invoice", "Invoices"], ["live", "Preview"], ["folio", "Freelancer folio"]],
};

export default function App() {
  const [, bump] = useState(0);
  const [screen, setScreen] = useState("landing"); // landing | login | register
  const [view, setView] = useState(null);
  const [pid, setPid] = useState(null);
  const [list, setList] = useState([]);
  const [mint, setMint] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [pay, setPay] = useState(null); // PayModal flow
  const [plan, setPlan] = useState("free");
  const reloadPlan = useRef(null);
  const [demo, setDemo] = useState(true);
  useEffect(() => { fetch("/api/health").then((r) => r.json()).then((h) => setDemo(h.demo !== false)).catch(() => {}); }, []);

  const sessions = getSessions();
  const role = getActive();
  const user = role ? sessions[role]?.user : null;
  const presenter = !!(sessions.freelancer && sessions.client);
  const tab = view || (role === "client" ? "review" : "dashboard");
  const p = list.find((x) => x.id === pid) || null;

  useEffect(() => {
    const h = () => bump((n) => n + 1);
    window.addEventListener("pl-auth", h);
    return () => window.removeEventListener("pl-auth", h);
  }, []);

  const run = useCallback(async (fn) => {
    setBusy(true);
    setErr("");
    try { return await fn(); } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }, []);

  const refresh = useCallback(async () => {
    try {
      const l = await api("/api/projects");
      setList(l);
      setPid((cur) => (cur && l.some((x) => x.id === cur) ? cur : l[0]?.id || null));
      if (getActive() === "freelancer") api("/api/subscription", { as: "freelancer" }).then((s) => setPlan(s.plan)).catch(() => {});
    } catch { /* 401 is handled by api() */ }
  }, []);

  useEffect(() => {
    if (!role) { setList([]); setPid(null); return undefined; }
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, [role, refresh]);

  useEffect(() => {
    if (p?.mint_hash && mint?.hash !== p.mint_hash) {
      api(`/api/verify/${p.mint_hash}`).then((r) => setMint(r.card)).catch(() => {});
    }
    if (!p?.mint_hash) setMint(null);
  }, [p?.mint_hash]); // eslint-disable-line

  if (!role || !user) {
    if (screen === "landing") {
      return <Landing onLogin={() => setScreen("login")} onSignup={() => setScreen("register")} onDemo={() => setScreen("login")} />;
    }
    return <Auth initialMode={screen} onBack={() => setScreen("landing")} onAuthed={() => { setView(null); bump((n) => n + 1); }} />;
  }

  const switchRole = (r) => { setActive(r); setView(null); setPay(null); bump((n) => n + 1); };
  const logout = async () => {
    await api("/api/auth/logout", { method: "POST" }).catch(() => {});
    dropSession(role);
    setView(null); setPid(null); setList([]); setScreen("landing");
    bump((n) => n + 1);
  };

  const as = (r) => ({ as: r });
  const post = (path, r, json) => api(path, { method: "POST", json, ...as(r) });
  const a = {
    scope: (f) => run(async () => {
      const d = await post("/api/scope", "freelancer", {
        chat: f.chat, client_email: f.clientEmail, grace_period_hours: f.grace, price_inr: f.price || null,
        advance_pct: f.advance, revisions_included: f.revisions, review_days: f.reviewDays, late_fee_pct_per_week: f.lateFee, delivery_days: f.deliveryDays,
      });
      await refresh(); setPid(d.id);
    }),
    audit: (file) => run(async () => { const f = new FormData(); f.append("file", file); await api(`/api/audit/${p.id}`, { method: "POST", form: f, ...as("freelancer") }); await refresh(); }),
    auditSample: () => run(async () => { await api(`/api/audit/${p.id}?use_sample=true`, { method: "POST", ...as("freelancer") }); await refresh(); }),
    submit: () => run(async () => { await post(`/api/projects/${p.id}/submit`, "freelancer"); await refresh(); }),
    setDrm: (state) => run(async () => { await post(`/api/drm/${p.id}`, "freelancer", { state }); await refresh(); }),
    expire: () => run(async () => { await post(`/api/demo/${p.id}/expire`, "freelancer"); await refresh(); }),
    expireReview: () => run(async () => { await post(`/api/demo/${p.id}/review-expire`, "freelancer"); await refresh(); }),
    requestChanges: (message) => run(async () => { await post(`/api/projects/${p.id}/request-changes`, "client", { message }); await refresh(); return true; }),
    sign: () => run(async () => { await post(`/api/projects/${p.id}/sign`, "client"); await refresh(); }),
    quote: async (fee, note) => { await post(`/api/projects/${p.id}/change-quote`, "freelancer", { fee_inr: fee, note }); await refresh(); },
    remind: async () => { const m = await post(`/api/projects/${p.id}/remind`, "freelancer"); await refresh(); return m; },
    startPay: () => setPay({ kind: "final" }),
    payAdvance: () => setPay({
      kind: "advance",
      flow: { title: "Pay advance", amount: p.terms.advance_inr, label: `Advance for ${p.invoice.number}`, orderPath: `/api/pay/${p.id}/order`, orderBody: { kind: "advance" },
              checkoutPath: `/api/pay/${p.id}/checkout`, verifyPath: `/api/pay/${p.id}/verify`, as: "client" },
    }),
    subscribe: (billing) => run(async () => {
      const amount = billing === "yearly" ? 4790 : 499;
      setPay({ kind: "subscription", flow: { title: "Synera Pro", amount, label: `Pro, billed ${billing}`, orderPath: "/api/subscription/order", orderBody: { plan: "pro", billing },
              checkoutPath: "/api/subscription/checkout", verifyPath: "/api/subscription/verify", as: "freelancer" } });
    }),
    seed: () => run(async () => {
      const d = await post("/api/demo/seed", "freelancer");
      await refresh(); setPid(d.id); setView("workspace");
    }),
    reset: () => run(async () => { await post("/api/demo/reset", "freelancer"); setPid(null); setMint(null); await refresh(); }),
  };

  const folioId = role === "client" ? p?.freelancer_id : user.id;
  const props = { p, a, busy, mint, setView, setPid, role, user, presenter, folioId, plan, list, onSubscribed: reloadPlan };

  return (
    <div className="mx-auto max-w-7xl px-4 pb-16 pt-5">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-white text-black"><ShieldCheck size={22} /></div>
          <div>
            <h1 className="text-lg font-extrabold leading-tight tracking-tight">Synera</h1>
            <p className="text-xs text-violet-300/70">{role === "client" ? "Client portal" : "Freelancer workspace"}</p>
          </div>
        </div>

        <nav className="glass flex flex-wrap gap-1 !rounded-full p-1.5">
          {TABS[role].map(([k, label]) => (
            <button key={k} onClick={() => setView(k)}
              className={`rounded-full px-3.5 py-2 text-sm font-semibold transition ${tab === k ? "bg-white text-black" : "text-violet-200 hover:bg-white/10"}`}>
              {label}
            </button>
          ))}
        </nav>

        <div className="flex flex-wrap items-center gap-2">
          {presenter && (
            <div className="glass flex gap-1 !rounded-full p-1" title="Presenter mode: one browser, both accounts">
              {["freelancer", "client"].map((r) => (
                <button key={r} onClick={() => switchRole(r)}
                  className={`rounded-full px-2.5 py-1.5 text-xs font-semibold capitalize ${role === r ? "bg-white text-black" : "text-violet-200 hover:bg-white/10"}`}>{r}</button>
              ))}
            </div>
          )}
          {list.length > 1 && (
            <select value={pid || ""} onChange={(e) => setPid(e.target.value)}
              className="glass max-w-[210px] !rounded-full bg-transparent px-3 py-2 text-sm text-violet-100 outline-none">
              {list.map((x) => <option key={x.id} value={x.id} className="bg-zinc-900">{x.contract.title} · {x.invoice.number}</option>)}
            </select>
          )}
          {p && tab !== "dashboard" && tab !== "plan" && <StateChip state={p.drm_state} />}
          {role === "freelancer" && (
            <>
              <Chip tone={plan === "pro" ? "emerald" : "slate"}>{plan === "pro" ? "Pro" : "Starter"}</Chip>
              {demo && <Btn variant="ghost" onClick={a.seed} disabled={busy}><Zap size={15} /> Quick demo</Btn>}
              {demo && <Btn variant="ghost" onClick={a.reset} disabled={busy} title="Remove my projects"><RotateCcw size={15} /></Btn>}
            </>
          )}
          <div className="glass flex items-center gap-2 !rounded-full py-1.5 pl-4 pr-1.5">
            <div className="leading-tight">
              <div className="text-xs font-semibold">{user.name}</div>
              <div className="text-[10px] capitalize text-violet-300/70">{user.role}</div>
            </div>
            <button onClick={logout} title="Log out" className="grid h-8 w-8 place-items-center rounded-full text-violet-200 hover:bg-white/10"><LogOut size={15} /></button>
          </div>
        </div>
      </header>

      {err && <div className="mb-4 rounded-xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{err}</div>}

      {tab === "dashboard" && <Dashboard {...props} />}
      {tab === "workspace" && <Freelancer {...props} />}
      {tab === "review" && <Client {...props} />}
      {tab === "live" && <Live {...props} />}
      {tab === "folio" && <Folio {...props} />}
      {tab === "plan" && <Plan {...props} />}
      {tab === "invoice" && <Invoice {...props} />}

      {pay && (p || pay.kind === "subscription") && (
        <PayModal p={p} flow={pay.flow} onClose={() => setPay(null)}
          onPaid={async (r) => {
            if (pay.kind === "final") setMint(r.mint);
            setPay(null);
            await refresh();
            if (pay.kind === "subscription") reloadPlan.current?.();
          }} />
      )}
    </div>
  );
}
