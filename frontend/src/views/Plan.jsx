import { useEffect, useState } from "react";
import { Receipt } from "lucide-react";
import { api } from "../api.js";
import { Glass, Btn, Chip, inr } from "../ui.jsx";
import { PricingCards } from "../Pricing.jsx";

export default function Plan({ a, onSubscribed }) {
  const [s, setS] = useState(null);
  const [err, setErr] = useState("");
  const load = () => api("/api/subscription", { as: "freelancer" }).then(setS).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);
  useEffect(() => { if (onSubscribed) onSubscribed.current = load; });
  if (!s) return <Glass className="mx-auto max-w-xl p-10 text-center text-violet-200/70">{err || "Loading…"}</Glass>;
  const choose = (plan, yearly) => { if (plan === "pro") a.subscribe(yearly ? "yearly" : "monthly"); };
  return (
    <div className="space-y-6">
      <div className="text-center">
        <span className="pill">Plan</span>
        <h2 className="mt-3 text-4xl font-extrabold">Simple pricing for freelancers</h2>
        <p className="mx-auto mt-2 max-w-xl text-sm text-violet-200/70">Clients never pay to use Synera. You keep what you earn: no marketplace commission, just a flat plan.</p>
      </div>
      <Glass className="flex flex-wrap items-center justify-between gap-3 p-5">
        <div>
          <div className="text-xs uppercase tracking-wider text-violet-300/60">Current plan</div>
          <div className="text-2xl font-extrabold">{s.name} {s.cancelled && <Chip tone="amber">ends {new Date(s.renews * 1000).toLocaleDateString("en-IN")}</Chip>}</div>
          {s.renews && !s.cancelled && <div className="text-xs text-violet-300/70">Renews on {new Date(s.renews * 1000).toLocaleDateString("en-IN")} (sandbox: nothing is charged automatically)</div>}
        </div>
        {s.plan === "pro" && !s.cancelled && <Btn variant="ghost" onClick={async () => { setS(await api("/api/subscription/cancel", { method: "POST", as: "freelancer" })); }}>Cancel at period end</Btn>}
      </Glass>
      <PricingCards plans={s.plans} current={s.plan} cta="Upgrade to Pro" onChoose={choose} />
      {s.billing.length > 0 && (
        <Glass className="p-5">
          <h3 className="mb-3 flex items-center gap-2 font-bold"><Receipt size={18} className="text-violet-300" /> Billing history</h3>
          {s.billing.map((b) => (
            <div key={b.payment_id} className="flex justify-between border-t border-white/10 py-2 text-sm first:border-0">
              <span>{new Date(b.at).toLocaleDateString("en-IN")} · Pro {b.billing}</span><span className="font-mono text-xs text-violet-300/60">{b.payment_id}</span><b>{inr(b.amount_inr)}</b>
            </div>
          ))}
        </Glass>
      )}
    </div>
  );
}
