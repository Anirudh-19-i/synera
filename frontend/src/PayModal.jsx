import { useEffect, useState } from "react";
import { X, Smartphone, CreditCard, CheckCircle2, ShieldCheck, Loader2 } from "lucide-react";
import { api } from "./api.js";
import { Btn, Chip, Glass, inr } from "./ui.jsx";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// flow: { title, amount, label, orderPath, orderBody, checkoutPath, verifyPath, as }.
// Defaults to paying a project's final balance as the client.
export default function PayModal({ p, flow, onClose, onPaid }) {
  const f = flow || {
    title: "SyneraPay checkout", amount: p.money.balance_due, label: `Invoice ${p.invoice.number}`,
    orderPath: `/api/pay/${p.id}/order`, orderBody: { kind: "final" }, checkoutPath: `/api/pay/${p.id}/checkout`,
    verifyPath: `/api/pay/${p.id}/verify`, as: "client",
  };
  const [order, setOrder] = useState(null);
  const [tab, setTab] = useState("upi");
  const [vpa, setVpa] = useState("");
  const [card, setCard] = useState("");
  const [expiry, setExpiry] = useState("");
  const [cvv, setCvv] = useState("");
  const [step, setStep] = useState("form"); // form | processing | success
  const [err, setErr] = useState("");

  useEffect(() => {
    api(f.orderPath, { method: "POST", json: f.orderBody, as: f.as }).then(setOrder).catch((e) => setErr(e.message));
  }, [f.orderPath]); // eslint-disable-line

  async function pay() {
    setErr("");
    setStep("processing");
    try {
      await sleep(900);
      const signed = await api(f.checkoutPath, {
        method: "POST", as: f.as,
        json: { order_id: order.order_id, method: tab, vpa, card_number: card, expiry, cvv },
      });
      const done = await api(f.verifyPath, { method: "POST", json: signed, as: f.as });
      setStep("success");
      await sleep(1300);
      onPaid(done);
    } catch (e) {
      setErr(e.message);
      setStep("form");
    }
  }

  const input = "w-full px-3 py-2.5 text-sm";
  const hint = "rounded-md bg-white/5 px-2 py-1 text-[11px] text-violet-200 hover:bg-white/10";

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4 backdrop-blur-sm">
      <Glass className="w-full max-w-md bg-[#0d0d0f]! p-6">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldCheck size={18} className="text-violet-300" />
            <h3 className="text-lg font-bold">{f.title}</h3>
            <Chip tone="amber">Sandbox</Chip>
          </div>
          {step !== "processing" && <button onClick={onClose} className="text-violet-300 hover:text-white"><X size={18} /></button>}
        </div>

        {step === "success" ? (
          <div className="py-8 text-center">
            <CheckCircle2 size={48} className="mx-auto mb-3 text-emerald-400" />
            <div className="text-lg font-bold">Payment verified</div>
            <p className="mt-1 text-sm text-violet-200/70">Signature checked.</p>
          </div>
        ) : (
          <>
            <div className="mb-1 text-3xl font-extrabold">{inr(f.amount)}</div>
            <p className="mb-4 text-xs text-violet-300/70">
              {f.label}{order ? ` · ${order.order_id}` : ""}. Sandbox gateway: no real money moves.
            </p>

            <div className="mb-4 grid grid-cols-2 gap-1.5 rounded-xl bg-black/25 p-1.5">
              {[["upi", "UPI", Smartphone], ["card", "Card", CreditCard]].map(([k, label, Icon]) => (
                <button key={k} onClick={() => { setTab(k); setErr(""); }}
                  className={`flex items-center justify-center gap-1.5 rounded-lg py-2 text-sm font-semibold ${tab === k ? "bg-white text-black" : "text-violet-200 hover:bg-white/10"}`}>
                  <Icon size={15} /> {label}
                </button>
              ))}
            </div>

            {tab === "upi" ? (
              <div className="space-y-2">
                <input className={input} placeholder="UPI ID" value={vpa} onChange={(e) => setVpa(e.target.value)} />
                <div className="flex gap-2">
                  <button className={hint} onClick={() => setVpa("success@razorpay")}>Use success UPI</button>
                  <button className={hint} onClick={() => setVpa("failure@razorpay")}>Use failure UPI</button>
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <input className={input} placeholder="Card number" inputMode="numeric" value={card} onChange={(e) => setCard(e.target.value)} />
                <div className="grid grid-cols-2 gap-2">
                  <input className={input} placeholder="MM/YY" value={expiry} onChange={(e) => setExpiry(e.target.value)} />
                  <input className={input} placeholder="CVV" type="password" value={cvv} onChange={(e) => setCvv(e.target.value)} />
                </div>
                <div className="flex gap-2">
                  <button className={hint} onClick={() => { setCard("4111 1111 1111 1111"); setExpiry("12/30"); setCvv("123"); }}>Use success card</button>
                  <button className={hint} onClick={() => { setCard("4000 0000 0000 0002"); setExpiry("12/30"); setCvv("123"); }}>Use decline card</button>
                </div>
              </div>
            )}

            {err && <div className="mt-3 rounded-lg border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">{err}</div>}

            <Btn variant="success" className="mt-4 w-full" disabled={!order || step === "processing"} onClick={pay}>
              {step === "processing" ? <><Loader2 size={16} className="animate-spin" /> Processing…</> : `Pay ${inr(f.amount)}`}
            </Btn>
            <p className="mt-3 text-center text-[11px] text-violet-300/60">Order → checkout → HMAC-signed confirmation → server verifies before unlocking.</p>
          </>
        )}
      </Glass>
    </div>
  );
}
