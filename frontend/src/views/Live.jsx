import { useEffect, useState } from "react";
import { Globe, Zap } from "lucide-react";
import { Glass, Btn, Chip, KillSwitch, StateChip, inr } from "../ui.jsx";

export default function Live({ p, a, busy, setView, role, presenter }) {
  const [childState, setChildState] = useState(null);

  useEffect(() => {
    const onMsg = (e) => { if (e.data?.type === "synera:state") setChildState(e.data.state); };
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, []);

  if (!p) {
    return (
      <Glass className="mx-auto max-w-xl p-10 text-center">
        <p className="mb-4 text-violet-200/80">
          {role === "freelancer" ? "Load the ready-made gym project to see the split-screen lock in action." : "No project to preview yet."}
        </p>
        {role === "freelancer" && <Btn onClick={a.seed} disabled={busy}><Zap size={16} /> Quick demo</Btn>}
      </Glass>
    );
  }

  const paid = !!p.paid;
  const signed = !!p.agreement.client_signed_at;
  const canPay = !paid && p.status === "submitted" && signed && (role === "client" || presenter);

  return (
    <div className="grid gap-5 lg:grid-cols-5">
      <div className="space-y-5 lg:col-span-2">
        <Glass className="p-5">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-bold">{role === "freelancer" ? "Freelancer command center" : "Delivery status"}</h2>
            <StateChip state={p.drm_state} />
          </div>
          <div className="mb-4 rounded-xl bg-white/5 p-4">
            <div className="text-xs text-violet-300/70">{p.contract.title} · {p.invoice.number}</div>
            <div className="text-3xl font-extrabold">{inr(paid ? p.money.grand_total : p.money.balance_due)}</div>
            <div className="text-xs text-violet-300/60">{paid ? "paid in full" : p.money.advance_paid ? `balance after ${inr(p.money.advance_paid)} advance` : "balance due"}</div>
          </div>
          {role === "freelancer" ? (
            <KillSwitch p={p} a={a} busy={busy} />
          ) : (
            <p className="text-sm text-violet-200/70">
              {paid ? "Paid. The preview is unlocked and the source is available for download."
                : p.drm_state === "KILLED" ? "The freelancer has locked this preview until the invoice is settled."
                : "This is the hosted preview of your delivery. It shows an unpaid watermark until you settle the invoice."}
            </p>
          )}
        </Glass>

        <Glass className="p-5">
          <h3 className="mb-2 font-bold">{presenter && role === "freelancer" ? "Play the client" : "Settle the invoice"}</h3>
          <p className="mb-3 text-sm text-violet-200/70">Pay through the sandbox checkout. The preview on the right unlocks on its own, the source becomes downloadable, and the proof card is minted.</p>
          <Btn variant="success" className="w-full" disabled={busy || !canPay} onClick={a.startPay}>
            {paid ? "Settled" : `Pay ${inr(p.money.balance_due)} (sandbox checkout)`}
          </Btn>
          {!paid && p.status !== "submitted" && <p className="mt-2 text-xs text-amber-300">The delivery must be audited and submitted to the client first.</p>}
          {!paid && p.status === "submitted" && !signed && <p className="mt-2 text-xs text-amber-300">The client must sign the agreement before paying.</p>}
          {!paid && p.status === "submitted" && role === "freelancer" && !presenter && (
            <p className="mt-2 text-xs text-violet-300/70">Only the client can pay. Log in as the client, or use presenter mode on the login page.</p>
          )}
          {paid && <Btn variant="ghost" className="mt-3 w-full" onClick={() => setView("folio")}>See the minted folio card</Btn>}
        </Glass>
      </div>

      <Glass className="overflow-hidden lg:col-span-3">
        <div className="flex items-center gap-2 border-b border-white/10 bg-black/20 px-4 py-2.5">
          <div className="flex gap-1.5"><i className="h-2.5 w-2.5 rounded-full bg-rose-400/80" /><i className="h-2.5 w-2.5 rounded-full bg-amber-400/80" /><i className="h-2.5 w-2.5 rounded-full bg-emerald-400/80" /></div>
          <div className="mx-2 flex flex-1 items-center gap-2 rounded-lg bg-white/5 px-3 py-1 text-xs text-violet-200/70"><Globe size={12} /> client-preview.synera.app/{p.id}</div>
          {childState && <Chip tone={{ PREVIEW: "amber", KILLED: "rose", UNLOCKED: "emerald" }[childState]}>live: {childState}</Chip>}
        </div>
        {p.preview_url ? (
          <iframe key={p.id + p.preview_url} title="Protected client app" src={p.preview_url}
            sandbox="allow-scripts allow-forms allow-popups allow-modals" className="h-[640px] w-full bg-white" />
        ) : (
          <div className="grid h-[640px] place-items-center p-8 text-center text-sm text-violet-200/70">
            {p.has_deliverable || role === "freelancer"
              ? (p.preview?.files ? "No index.html was found in the uploaded zip, so there is nothing to preview. Upload the built site with index.html at the top." : "Upload and audit a deliverable (a zip with index.html) and the client's locked preview appears here.")
              : "The freelancer has not submitted a delivery yet."}
          </div>
        )}
      </Glass>
    </div>
  );
}
