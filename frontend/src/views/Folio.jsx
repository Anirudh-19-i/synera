import { useEffect, useState } from "react";
import { BadgeCheck, Copy, Check, ExternalLink } from "lucide-react";
import { api } from "../api.js";
import { Glass, Btn, Chip, inr } from "../ui.jsx";

function CopyHash({ hash }) {
  const [ok, setOk] = useState(false);
  return (
    <button onClick={() => { navigator.clipboard?.writeText(hash); setOk(true); setTimeout(() => setOk(false), 1500); }}
      className="flex w-full items-center gap-2 rounded-lg bg-black/30 px-3 py-2 text-left font-mono text-[11px] text-emerald-300 hover:bg-black/40">
      <span className="flex-1 break-all">{hash.slice(0, 20)}…{hash.slice(-8)}</span>
      {ok ? <Check size={14} /> : <Copy size={14} />}
    </button>
  );
}

export default function Folio({ folioId, mint }) {
  const [data, setData] = useState(null);

  useEffect(() => {
    if (!folioId) return undefined;
    const load = () => api(`/api/folio/${folioId}`).then(setData).catch(() => {});
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [folioId, mint?.hash]);

  if (!folioId) return <Glass className="mx-auto max-w-xl p-10 text-center text-violet-200/70">Select a project to see its freelancer's folio.</Glass>;

  const cards = data?.cards || [];

  return (
    <div className="mx-auto max-w-5xl">
      <Glass className="mb-5 flex flex-wrap items-center gap-5 p-6">
        <div className="grid h-16 w-16 place-items-center rounded-2xl bg-white text-black text-2xl font-extrabold">
          {(data?.freelancer_name || "F")[0]}
        </div>
        <div className="flex-1">
          <h2 className="text-2xl font-extrabold">{data?.freelancer_name || "Freelancer"}</h2>
          <p className="text-sm text-violet-200/70">Public proof-of-work portfolio. Every card below was paid, audited and hashed.</p>
        </div>
        <div className="flex gap-6 text-center">
          <div><div className="text-2xl font-extrabold">{data?.stats.verified_deliveries ?? 0}</div><div className="text-xs text-violet-300/70">Verified deliveries</div></div>
          <div><div className="text-2xl font-extrabold">{data?.stats.avg_score ?? 0}%</div><div className="text-xs text-violet-300/70">Avg spec score</div></div>
        </div>
      </Glass>

      {cards.length === 0 ? (
        <Glass className="p-10 text-center text-violet-200/70">No verified deliveries yet. When a client settles an invoice, the card is minted here automatically.</Glass>
      ) : (
        <div className="grid gap-5 md:grid-cols-2">
          {cards.map((c) => (
            <Glass key={c.hash} className="p-5">
              <div className="mb-2 flex items-center justify-between">
                <Chip tone="emerald"><BadgeCheck size={13} /> Verified paid delivery</Chip>
                <span className="text-xs text-violet-300/60">{new Date(c.timestamp).toLocaleDateString("en-IN")}</span>
              </div>
              <h3 className="text-lg font-bold">{c.title}</h3>
              <p className="mb-3 text-sm text-violet-200/70">{c.summary}</p>
              <div className="mb-3 flex flex-wrap gap-1.5">{c.stack_tags.map((t) => <Chip key={t} tone="slate">{t}</Chip>)}</div>
              <div className="mb-3 grid grid-cols-3 gap-2 text-center text-xs">
                <div className="rounded-lg bg-white/5 p-2"><div className="text-base font-bold">{c.score}%</div>Spec score</div>
                <div className="rounded-lg bg-white/5 p-2"><div className="text-base font-bold">{c.criteria_passed}</div>Criteria</div>
                <div className="rounded-lg bg-white/5 p-2"><div className="text-base font-bold">{inr(c.invoice_total_inr)}</div>Paid</div>
              </div>
              <CopyHash hash={c.hash} />
              <a href={`/verify/${c.hash}`} target="_blank" rel="noreferrer" className="mt-2 block">
                <Btn variant="ghost" className="w-full"><ExternalLink size={14} /> Verify independently</Btn>
              </a>
            </Glass>
          ))}
        </div>
      )}
    </div>
  );
}
