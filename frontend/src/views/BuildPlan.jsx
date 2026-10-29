import { useState } from "react";
import { ListChecks, Lightbulb, AlertTriangle, HelpCircle, Layers, FolderTree, CheckCircle2, Circle, ChevronDown } from "lucide-react";
import { Glass, Chip, inr } from "../ui.jsx";

function Bullets({ icon: Icon, title, items, tone }) {
  if (!items?.length) return null;
  return (
    <div className="rounded-xl bg-white/5 p-3">
      <h4 className={`mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider ${tone}`}><Icon size={13} /> {title}</h4>
      <ul className="space-y-1.5 text-sm text-violet-100/85">
        {items.map((x, i) => <li key={i} className="flex gap-2"><span className="text-violet-400">•</span><span>{x}</span></li>)}
      </ul>
    </div>
  );
}

export default function BuildPlan({ p }) {
  const plan = p?.plan;
  const ev = p?.plan_eval;
  const [open, setOpen] = useState(0);
  if (!plan) return null;
  const checks = plan.phases.flatMap((ph) => ph.tasks.filter((t) => t.criterion_ids?.length));
  const done = checks.filter((t) => t.status === "done").length;

  return (
    <Glass className="p-5">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h3 className="flex items-center gap-2 font-bold"><ListChecks size={18} className="text-violet-300" /> Build plan</h3>
        <Chip tone={plan.source === "gemini" ? "emerald" : "amber"}>{plan.source === "gemini" ? "AI-planned" : "Template plan"}</Chip>
        <Chip tone="slate">~{plan.total_hours} hours</Chip>
        {ev && <Chip tone={done === checks.length ? "emerald" : "amber"}>{done}/{checks.length} checks passing</Chip>}
      </div>
      <p className="mb-4 text-sm text-violet-200/80">{plan.overview}</p>

      <div className="mb-4 space-y-2">
        {plan.phases.map((ph, i) => (
          <div key={i} className="rounded-xl bg-white/5">
            <button className="flex w-full items-center gap-3 p-3 text-left" onClick={() => setOpen(open === i ? -1 : i)}>
              <span className="grid h-6 w-6 place-items-center rounded-full bg-violet-500/30 text-xs font-bold">{i + 1}</span>
              <span className="flex-1">
                <span className="block text-sm font-semibold">{ph.name}</span>
                <span className="block text-xs text-violet-300/70">{ph.goal}</span>
              </span>
              <span className="text-right text-xs text-violet-300/80">{ph.est_hours}h<br />{inr(ph.amount_inr)}</span>
              <ChevronDown size={16} className={`transition ${open === i ? "rotate-180" : ""}`} />
            </button>
            {open === i && (
              <div className="space-y-1.5 px-3 pb-3">
                {ph.tasks.map((t, j) => {
                  const isCheck = t.criterion_ids?.length;
                  const ok = t.status === "done";
                  return (
                    <div key={j} className="flex items-start gap-2 text-sm">
                      {isCheck ? (ok ? <CheckCircle2 size={15} className="mt-0.5 text-emerald-400" /> : <Circle size={15} className={`mt-0.5 ${ev ? "text-amber-400" : "text-violet-400/60"}`} />)
                        : <Circle size={15} className="mt-0.5 text-violet-400/40" />}
                      <span className={isCheck ? "font-medium text-violet-100" : "text-violet-100/80"}>
                        {t.title}
                        {t.detail && <span className="block text-xs text-violet-300/60">{t.detail}</span>}
                      </span>
                    </div>
                  );
                })}
                {ph.tip && <p className="mt-2 rounded-lg bg-amber-400/10 p-2 text-xs text-amber-200"><Lightbulb size={12} className="mr-1 inline" />{ph.tip}</p>}
              </div>
            )}
          </div>
        ))}
      </div>

      {ev && ev.next_fixes.length > 0 && (
        <div className="mb-4 rounded-xl border border-amber-400/30 bg-amber-400/10 p-3">
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-amber-200">Evaluation: fix these next</h4>
          <ul className="space-y-1 text-sm text-amber-100">
            {ev.next_fixes.map((f, i) => <li key={i}>• <b>{f.phase}</b>: {f.task}</li>)}
          </ul>
        </div>
      )}
      {ev && ev.next_fixes.length === 0 && <div className="mb-4 rounded-xl bg-emerald-400/10 p-3 text-sm text-emerald-200">Evaluation: every planned check passes. Ready to submit.</div>}

      <div className="grid gap-3 md:grid-cols-2">
        <Bullets icon={HelpCircle} title="Ask the client first" items={plan.clarify} tone="text-sky-300" />
        <Bullets icon={Lightbulb} title="Suggestions" items={plan.suggestions} tone="text-emerald-300" />
        <Bullets icon={AlertTriangle} title="Risks" items={plan.risks} tone="text-amber-300" />
        <Bullets icon={FolderTree} title="Suggested files" items={plan.file_structure} tone="text-violet-300" />
      </div>
      <div className="mt-3 rounded-xl bg-white/5 p-3">
        <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-violet-300"><Layers size={13} /> Recommended stack</h4>
        <div className="grid gap-2 sm:grid-cols-2">
          {plan.stack.map((s, i) => (
            <div key={i} className="text-sm"><b>{s.layer}:</b> {s.choice}<span className="block text-xs text-violet-300/60">{s.why}</span></div>
          ))}
        </div>
      </div>
    </Glass>
  );
}
