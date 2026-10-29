import { useCallback, useEffect, useState } from "react";
import { FileText, Image as ImageIcon, Printer, Send, Copy, Check, ShieldCheck, Building2 } from "lucide-react";
import { api, downloadFile, getSessions } from "../api.js";
import { Glass, Btn, Chip, inr } from "../ui.jsx";

const TONE = { PAID: "emerald", "PARTIALLY PAID": "amber", DUE: "violet", OVERDUE: "rose", DRAFT: "slate" };
const FIELDS = [
  ["business_name", "Business or studio name", "Optional"],
  ["address", "Address", "Shown on every invoice"],
  ["phone", "Phone", "+91 …"],
  ["upi_id", "UPI ID", "name@bank"],
  ["gstin", "GSTIN", "Leave blank if not registered"],
  ["pan", "PAN", "Optional"],
];

function Billing({ role, onSaved }) {
  const [b, setB] = useState(null);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  useEffect(() => { api("/api/profile/business", { as: role }).then(setB).catch((e) => setErr(e.message)); }, [role]);
  async function save() {
    setErr(""); setMsg("");
    try { setB(await api("/api/profile/business", { method: "PUT", json: b, as: role })); setMsg("Saved. New downloads use these details."); onSaved && onSaved(); } catch (e) { setErr(e.message); }
  }
  if (!b) return null;
  return (
    <Glass className="p-6">
      <h3 className="mb-1 flex items-center gap-2 font-bold"><Building2 size={18} /> Your billing details</h3>
      <p className="mb-4 text-xs text-violet-300/70">These appear in the “From” block. A GSTIN is optional. Without one, the invoice says you are not registered under GST and charges none.</p>
      <div className="grid gap-3 sm:grid-cols-2">
        {FIELDS.map(([k, label, ph]) => (
          <label key={k} className="block text-xs text-violet-300/80">{label}
            <input value={b[k] || ""} placeholder={ph} onChange={(e) => setB({ ...b, [k]: e.target.value })}
              className="mt-1 w-full rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-white/50" />
          </label>
        ))}
        <label className="block text-xs text-violet-300/80 sm:col-span-2">Note printed under the terms
          <input value={b.note || ""} placeholder="e.g. Thank you for your business" onChange={(e) => setB({ ...b, note: e.target.value })}
            className="mt-1 w-full rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm text-white outline-none focus:border-white/50" />
        </label>
      </div>
      <div className="mt-4 flex items-center gap-3">
        <Btn onClick={save}>Save details</Btn>
        {msg && <span className="text-xs text-emerald-300">{msg}</span>}
        {err && <span className="text-xs text-rose-300">{err}</span>}
      </div>
    </Glass>
  );
}

export default function Invoice({ p, role, setPid, a }) {
  const [inv, setInv] = useState(null);
  const [img, setImg] = useState(null);
  const [rows, setRows] = useState([]);
  const [sent, setSent] = useState("");
  const [copied, setCopied] = useState("");
  const [err, setErr] = useState("");
  const [rev, setRev] = useState(0);
  const id = p?.id;
  const stamp = p ? `${p.status}|${p.money?.received}|${p.money?.grand_total}|${p.extras?.length}` : "";

  const load = useCallback(async () => {
    if (!id) return;
    setErr("");
    try {
      setInv(await api(`/api/projects/${id}/invoice`, { as: role }));
      const tok = getSessions()[role]?.token;
      const r = await fetch(`/api/projects/${id}/invoice/file?format=png`, { headers: { authorization: `Bearer ${tok}` } });
      if (r.ok) setImg((old) => { if (old) URL.revokeObjectURL(old); return null; }) || r.blob().then((b) => setImg(URL.createObjectURL(b)));
    } catch (e) { setInv(null); setImg(null); setErr(e.message); }
  }, [id, role, stamp, rev]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { api("/api/invoices", { as: role }).then(setRows).catch(() => {}); }, [role, stamp]);

  const dl = (fmt, ext) => downloadFile(`/api/projects/${id}/invoice/file?format=${fmt}`, role, `${inv.number}.${ext}`).catch((e) => setErr(e.message));
  const copy = (k, t) => { navigator.clipboard?.writeText(t); setCopied(k); setTimeout(() => setCopied(""), 1500); };
  async function send() {
    try { const r = await api(`/api/projects/${id}/invoice/send`, { method: "POST", as: role }); setSent(r.message); await load(); } catch (e) { setErr(e.message); }
  }
  const total = rows.reduce((s, r) => s + r.total, 0), recv = rows.reduce((s, r) => s + r.received, 0);

  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_380px]">
      <div className="space-y-5">
        {!p && <Glass className="p-10 text-center text-violet-200/70">{role === "client" ? "No invoices yet. They appear here when your freelancer sends one." : "Create a project first. Its invoice is prepared automatically."}</Glass>}
        {p && (
          <Glass className="p-6">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2"><h3 className="text-lg font-bold">Invoice {inv?.number}</h3>{inv && <Chip tone={TONE[inv.status] || "violet"}>{inv.status}</Chip>}</div>
                <p className="text-xs text-violet-300/70">{p.contract.title}</p>
              </div>
              {inv && (
                <div className="flex flex-wrap gap-2">
                  <Btn variant="ghost" onClick={() => dl("pdf", "pdf")}><FileText size={15} /> PDF</Btn>
                  <Btn variant="ghost" onClick={() => dl("png", "png")}><ImageIcon size={15} /> Image</Btn>
                  <Btn variant="ghost" onClick={async () => { const tok = getSessions()[role]?.token; const r = await fetch(`/api/projects/${id}/invoice/file?format=html`, { headers: { authorization: `Bearer ${tok}` } }); const w = window.open("", "_blank"); if (w) { w.document.write(await r.text()); w.document.close(); setTimeout(() => w.print(), 400); } }}><Printer size={15} /> Print</Btn>
                  {role === "freelancer" && <Btn onClick={send}><Send size={15} /> {inv.sent ? "Resend to client" : "Send to client"}</Btn>}
                </div>
              )}
            </div>
            {err && <p className="mb-3 rounded-lg bg-rose-500/15 p-3 text-sm text-rose-200">{err}</p>}
            {sent && (
              <div className="mb-4 rounded-xl border border-white/15 bg-white/5 p-4 text-sm">
                <p className="mb-2 font-semibold text-emerald-300">Invoice is now visible to {p.client_email} in their portal.</p>
                <p className="text-violet-200/80">{sent}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Btn variant="ghost" onClick={() => copy("m", sent)}>{copied === "m" ? <Check size={14} /> : <Copy size={14} />} Copy message</Btn>
                  <a className="inline-flex items-center rounded-full border border-white/15 bg-white/5 px-5 py-2.5 text-sm font-semibold" target="_blank" rel="noreferrer" href={`https://wa.me/?text=${encodeURIComponent(sent)}`}>WhatsApp</a>
                  <a className="inline-flex items-center rounded-full border border-white/15 bg-white/5 px-5 py-2.5 text-sm font-semibold" href={`mailto:${p.client_email}?subject=${encodeURIComponent("Invoice " + inv.number)}&body=${encodeURIComponent(sent)}`}>Email</a>
                </div>
              </div>
            )}
            {img ? <img src={img} alt={`Invoice ${inv?.number}`} className="mx-auto w-full max-w-[640px] rounded-lg border border-white/15 bg-white shadow-xl" /> : !err && <p className="py-16 text-center text-sm text-violet-300/60">Preparing invoice…</p>}
            {inv && (
              <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-violet-300/70">
                <ShieldCheck size={14} /> Anyone can verify it:
                <a className="underline" href={inv.verify_url} target="_blank" rel="noreferrer">open verification page</a>
                <button onClick={() => copy("v", inv.verify_url)} className="underline">{copied === "v" ? "copied" : "copy link"}</button>
              </div>
            )}
          </Glass>
        )}
        {role === "freelancer" && <Billing role={role} onSaved={() => setRev((n) => n + 1)} />}
      </div>
      <Glass className="h-fit p-5">
        <h3 className="mb-1 font-bold">{role === "client" ? "Your invoices" : "Invoice records"}</h3>
        <p className="mb-3 text-xs text-violet-300/70">{rows.length} invoice{rows.length === 1 ? "" : "s"} · billed {inr(total)} · received {inr(recv)}</p>
        <div className="space-y-2">
          {rows.length === 0 && <p className="text-sm text-violet-300/60">Nothing here yet.</p>}
          {rows.map((r) => (
            <button key={r.number} onClick={() => setPid(r.project_id)}
              className={`w-full rounded-xl border p-3 text-left transition ${r.project_id === id ? "border-white/60 bg-white/10" : "border-white/10 bg-white/[0.03] hover:bg-white/10"}`}>
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-[11px] text-violet-300/70">{r.number}</span><Chip tone={TONE[r.status] || "violet"}>{r.status}</Chip>
              </div>
              <div className="mt-1 text-sm font-semibold">{r.title}</div>
              <div className="flex justify-between text-xs text-violet-300/70"><span>{r.party}</span><span>{inr(r.total)}{r.balance ? ` · due ${inr(r.balance)}` : ""}</span></div>
            </button>
          ))}
        </div>
      </Glass>
    </div>
  );
}
