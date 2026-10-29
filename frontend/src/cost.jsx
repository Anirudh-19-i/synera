import { Chip, inr } from "./ui.jsx";

const COLORS = ["#ffffff", "#c9c9d1", "#9a9aa6", "#e6e6ea", "#767683", "#b4b4be", "#5a5a66", "#d8d8de"];
const ST = {
  met: ["emerald", "Delivered"],
  partial: ["amber", "Partly delivered"],
  missing: ["rose", "Not found"],
  assumed: ["slate", "Scales with features"],
  attention: ["rose", "Needs attention"],
};

// Where the budget goes. With an audit, each line also shows what was verified in the delivered code.
export function CostSplit({ items, total, audit }) {
  const rows = audit ? audit.cost_rows : items;
  const pct = audit ? Math.round((100 * audit.value_delivered_inr) / Math.max(total, 1)) : 0;
  return (
    <div>
      <div className="mb-4 flex h-3 w-full overflow-hidden rounded-full bg-white/10">
        {rows.map((r, i) => (
          <div key={r.id} title={`${r.label}: ${inr(r.amount)}`}
            style={{ width: `${(r.amount / Math.max(total, 1)) * 100}%`, background: COLORS[i % COLORS.length] }} />
        ))}
      </div>
      <div className="space-y-2">
        {rows.map((r, i) => (
          <div key={r.id} className="rounded-xl bg-white/5 p-3">
            <div className="flex items-start gap-3">
              <span className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: COLORS[i % COLORS.length] }} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2 text-sm font-semibold">
                  {r.label}
                  {audit && <Chip tone={ST[r.status][0]}>{ST[r.status][1]}</Chip>}
                </div>
                <p className="text-xs text-violet-200/60">{audit ? r.note : r.why}</p>
              </div>
              <div className="shrink-0 text-right">
                <div className="text-sm font-bold">{inr(r.amount)}</div>
                <div className="text-[11px] text-violet-300/60">{r.pct}%</div>
                {audit && r.status !== "met" && r.status !== "assumed" && (
                  <div className="text-[11px] text-emerald-300/80">verified {inr(r.earned)}</div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
      {audit && (
        <div className="mt-4 rounded-xl bg-white/5 p-3">
          <div className="mb-1.5 flex justify-between text-sm">
            <span className="text-violet-200/80">Value verified in the delivered code</span>
            <span className="font-bold">{inr(audit.value_delivered_inr)} of {inr(total)}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-white/10">
            <div className={`h-full ${pct >= 90 ? "bg-emerald-400" : pct >= 60 ? "bg-amber-400" : "bg-rose-400"}`} style={{ width: `${pct}%` }} />
          </div>
        </div>
      )}
    </div>
  );
}

const STATUS = {
  scoped: ["slate", "Scoped"],
  audited: ["violet", "Audited, not yet submitted"],
  submitted: ["amber", "Awaiting client review"],
  changes_requested: ["rose", "Changes requested"],
  paid: ["emerald", "Paid and delivered"],
};

export function ProjectStatus({ status }) {
  const [tone, label] = STATUS[status] || STATUS.scoped;
  return <Chip tone={tone}>{label}</Chip>;
}

export function Stepper({ status }) {
  const steps = [["scoped", "Scoped"], ["audited", "Audited"], ["submitted", "Submitted"], ["paid", "Paid"]];
  const idx = { scoped: 0, audited: 1, submitted: 2, changes_requested: 2, paid: 3 }[status] ?? 0;
  return (
    <div className="flex items-center">
      {steps.map(([k, label], i) => (
        <div key={k} className="flex flex-1 items-center last:flex-none">
          <div className="flex flex-col items-center gap-1">
            <div className={`grid h-6 w-6 place-items-center rounded-full text-[11px] font-bold ${
              i < idx ? "bg-emerald-400 text-emerald-950" : i === idx ? (status === "changes_requested" ? "bg-rose-400 text-rose-950" : "bg-white text-black") : "bg-white/10 text-violet-300/60"}`}>
              {i < idx ? "✓" : i + 1}
            </div>
            <span className="text-[10px] text-violet-300/70">{label}</span>
          </div>
          {i < steps.length - 1 && <div className={`mx-1 mb-4 h-px flex-1 ${i < idx ? "bg-emerald-400/60" : "bg-white/10"}`} />}
        </div>
      ))}
    </div>
  );
}
