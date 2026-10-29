import { useEffect, useState } from "react";
import { Eye, Lock, Unlock } from "lucide-react";

export const inr = (n) => "₹" + Number(n || 0).toLocaleString("en-IN");

export function fmtLeft(s) {
  if (s <= 0) return "Expired";
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
  const p = (n) => String(n).padStart(2, "0");
  return `${d > 0 ? d + "d " : ""}${p(h)}:${p(m)}:${p(x)}`;
}

export function useCountdown(secs) {
  const [left, setLeft] = useState(secs || 0);
  useEffect(() => {
    setLeft(secs || 0);
    const t = setInterval(() => setLeft((l) => Math.max(0, l - 1)), 1000);
    return () => clearInterval(t);
  }, [secs]);
  return left;
}

export function Glass({ className = "", children }) {
  return <div className={`glass ${className}`}>{children}</div>;
}

const VARIANTS = {
  primary: "bg-white hover:bg-zinc-200 text-black",
  ghost: "bg-white/5 hover:bg-white/10 text-violet-100 border border-white/15",
  danger: "bg-rose-500/90 hover:bg-rose-400 text-white",
  success: "bg-emerald-400 hover:bg-emerald-300 text-emerald-950",
};

export function Btn({ variant = "primary", className = "", ...p }) {
  return (
    <button
      {...p}
      className={`inline-flex items-center justify-center gap-2 rounded-full px-5 py-2.5 text-sm font-semibold transition disabled:opacity-40 disabled:cursor-not-allowed ${VARIANTS[variant]} ${className}`}
    />
  );
}

const TONES = {
  violet: "bg-white/10 text-violet-100 border-white/15",
  emerald: "bg-emerald-400/15 text-emerald-200 border-emerald-300/20",
  amber: "bg-amber-400/15 text-amber-200 border-amber-300/20",
  rose: "bg-rose-400/15 text-rose-200 border-rose-300/20",
  slate: "bg-white/5 text-slate-300 border-white/10",
};

export function Chip({ tone = "violet", children, className = "" }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium ${TONES[tone]} ${className}`}>
      {children}
    </span>
  );
}

export function StateChip({ state }) {
  const tone = { PREVIEW: "amber", KILLED: "rose", UNLOCKED: "emerald" }[state] || "slate";
  const label = { PREVIEW: "Preview (unpaid)", KILLED: "Hard locked", UNLOCKED: "Unlocked (paid)" }[state] || "No project";
  return <Chip tone={tone}><span className="h-1.5 w-1.5 rounded-full bg-current" />{label}</Chip>;
}

export function Ring({ score, size = 120 }) {
  const r = 46, c = 2 * Math.PI * r, off = c * (1 - score / 100);
  const color = score >= 90 ? "#34d399" : score >= 60 ? "#fbbf24" : "#fb7185";
  return (
    <svg width={size} height={size} viewBox="0 0 110 110">
      <circle cx="55" cy="55" r={r} fill="none" stroke="rgba(255,255,255,.1)" strokeWidth="9" />
      <circle cx="55" cy="55" r={r} fill="none" stroke={color} strokeWidth="9" strokeLinecap="round"
        strokeDasharray={c} strokeDashoffset={off} transform="rotate(-90 55 55)" style={{ transition: "stroke-dashoffset .8s" }} />
      <text x="55" y="61" textAnchor="middle" fontSize="24" fontWeight="800" fill="#fff">{score}%</text>
    </svg>
  );
}

export function KillSwitch({ p, a, busy }) {
  const left = useCountdown(p?.seconds_remaining ?? 0);
  const paid = !!p?.paid;
  const st = p?.drm_state;
  const opts = [["PREVIEW", "Preview", Eye], ["KILLED", "Hard lock", Lock]];
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-1.5 rounded-xl bg-black/25 p-1.5">
        {opts.map(([key, label, Icon]) => (
          <button key={key} disabled={!p || paid || busy} onClick={() => a.setDrm(key)}
            className={`flex items-center justify-center gap-1.5 rounded-lg px-2 py-2 text-xs font-semibold transition disabled:opacity-40 ${
              st === key ? (key === "KILLED" ? "bg-rose-500 text-white" : "bg-amber-400 text-amber-950") : "text-violet-200 hover:bg-white/10"}`}>
            <Icon size={14} /> {label}
          </button>
        ))}
        <div title="Only reachable through payment settlement"
          className={`flex items-center justify-center gap-1.5 rounded-lg px-2 py-2 text-xs font-semibold ${st === "UNLOCKED" ? "bg-emerald-400 text-emerald-950" : "text-slate-500"}`}>
          <Unlock size={14} /> Unlocked
        </div>
      </div>
      <div className="flex items-center justify-between text-xs text-violet-300/80">
        <span>Auto-lock in</span>
        <span className={`font-mono text-sm ${left <= 0 && !paid ? "text-rose-300" : "text-violet-100"}`}>{paid ? "Settled" : fmtLeft(left)}</span>
      </div>
      <Btn variant="ghost" className="w-full" disabled={!p || paid || busy} onClick={a.expire}>
        Simulate deadline expiry (auto-lock)
      </Btn>
    </div>
  );
}
