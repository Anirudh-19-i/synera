import { useState } from "react";
import { ShieldCheck, Briefcase, UserRound, FileCheck2, Lock, Fingerprint, Loader2 } from "lucide-react";
import { api, setSession, setActive } from "./api.js";
import { Btn, Glass } from "./ui.jsx";

const DEMO = {
  freelancer: { email: "freelancer@synera.demo", password: "demo1234" },
  client: { email: "client@synera.demo", password: "demo1234" },
};

export default function Auth({ onAuthed, initialMode = "login", onBack }) {
  const [mode, setMode] = useState(initialMode);
  const [role, setRole] = useState("freelancer");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function go(fn) {
    setBusy(true);
    setErr("");
    try { await fn(); onAuthed(); } catch (e) { setErr(e.message); } finally { setBusy(false); }
  }

  const submit = (e) => {
    e.preventDefault();
    go(async () => {
      const body = mode === "login" ? { email, password } : { name, email, password, role };
      const r = await api(`/api/auth/${mode === "login" ? "login" : "register"}`, { method: "POST", json: body, as: "__none" });
      setSession(r.user.role, r);
    });
  };

  const demo = (which) => go(async () => {
    if (which === "both") {
      const fr = await api("/api/auth/login", { method: "POST", json: DEMO.freelancer, as: "__none" });
      const cl = await api("/api/auth/login", { method: "POST", json: DEMO.client, as: "__none" });
      setSession("client", cl, false);
      setSession("freelancer", fr, true);
      setActive("freelancer");
    } else {
      const r = await api("/api/auth/login", { method: "POST", json: DEMO[which], as: "__none" });
      setSession(which, r);
    }
  });

  const input = "w-full px-3.5 py-3 text-sm";

  return (
    <div className="mx-auto grid min-h-screen max-w-6xl items-center gap-10 px-5 py-10 lg:grid-cols-2">
      <div>
        {onBack && <button onClick={onBack} className="mb-6 text-sm text-violet-300/70 hover:text-white">← Back to home</button>}
        <div className="mb-6 flex items-center gap-3">
          <div className="grid h-12 w-12 place-items-center rounded-2xl bg-white text-black">
            <ShieldCheck size={26} />
          </div>
          <div className="text-2xl font-extrabold tracking-tight">Synera</div>
        </div>
        <h1 className="text-4xl font-extrabold leading-tight tracking-tight md:text-5xl">
          Get paid for work that is <span className="text-white underline decoration-white/30 underline-offset-8">provably done.</span>
        </h1>
        <p className="mt-4 max-w-md text-violet-200/70">
          Freelancers turn a client chat into a contract and cost split. The code is checked against every requirement, the client sees exactly what they are paying for, and payment unlocks the delivery.
        </p>
        <div className="mt-8 grid max-w-md gap-3 text-sm">
          {[[FileCheck2, "Requirement-by-requirement verification with file and line proof"], [Lock, "Preview stays locked until escrow is settled"], [Fingerprint, "Every paid delivery becomes a verifiable portfolio card"]].map(([Icon, t]) => (
            <div key={t} className="flex items-center gap-3 text-violet-100/80"><Icon size={16} className="shrink-0 text-violet-300" />{t}</div>
          ))}
        </div>
      </div>

      <Glass className="p-7">
        <div className="mb-5 grid grid-cols-2 gap-1.5 rounded-xl bg-black/25 p-1.5">
          {[["login", "Log in"], ["register", "Create account"]].map(([k, l]) => (
            <button key={k} onClick={() => { setMode(k); setErr(""); }}
              className={`rounded-lg py-2 text-sm font-semibold ${mode === k ? "bg-white text-black" : "text-violet-200 hover:bg-white/10"}`}>{l}</button>
          ))}
        </div>

        <form onSubmit={submit} className="space-y-3">
          {mode === "register" && (
            <>
              <div className="grid grid-cols-2 gap-2">
                {[["freelancer", "I'm a freelancer", Briefcase], ["client", "I'm a client", UserRound]].map(([k, l, Icon]) => (
                  <button type="button" key={k} onClick={() => setRole(k)}
                    className={`flex items-center justify-center gap-2 rounded-xl border px-3 py-3 text-sm font-semibold ${role === k ? "border-white bg-white/10 text-white" : "border-white/10 text-violet-200 hover:bg-white/5"}`}>
                    <Icon size={16} /> {l}
                  </button>
                ))}
              </div>
              <input className={input} placeholder={role === "client" ? "Business or full name" : "Full name"} value={name} onChange={(e) => setName(e.target.value)} required />
            </>
          )}
          <input className={input} type="email" placeholder="Email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <input className={input} type="password" placeholder={mode === "register" ? "Password (8+ characters)" : "Password"}
            autoComplete={mode === "login" ? "current-password" : "new-password"} value={password} onChange={(e) => setPassword(e.target.value)} required minLength={mode === "register" ? 8 : 1} />
          {err && <div className="rounded-lg border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">{err}</div>}
          <Btn className="w-full" disabled={busy} type="submit">
            {busy ? <Loader2 size={16} className="animate-spin" /> : mode === "login" ? "Log in" : "Create account"}
          </Btn>
        </form>

        <div className="mt-6 border-t border-white/10 pt-5">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-violet-300/70">Try the demo</div>
          <div className="grid gap-2 sm:grid-cols-2">
            <Btn variant="ghost" disabled={busy} onClick={() => demo("freelancer")}>Demo freelancer</Btn>
            <Btn variant="ghost" disabled={busy} onClick={() => demo("client")}>Demo client</Btn>
          </div>
          <Btn className="mt-2 w-full" disabled={busy} onClick={() => demo("both")}>Presenter mode: both roles side by side</Btn>
          <p className="mt-2 text-[11px] text-violet-300/60">Demo logins: freelancer@synera.demo and client@synera.demo, password demo1234.</p>
        </div>
      </Glass>
    </div>
  );
}
