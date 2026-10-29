import { useState } from "react";
import { Check } from "lucide-react";
import { Btn, inr } from "./ui.jsx";

const AGENCY = ["Shared client workspace", "Team seats", "Custom branding"];

export function PricingCards({ plans, current, onChoose, cta }) {
  const [yearly, setYearly] = useState(false);
  if (!plans) return null;
  const free = plans.free, pro = plans.pro;
  const price = yearly ? pro.price_year : pro.price_month;
  const Card = ({ children, hot }) => <div className={`flex flex-col rounded-3xl border p-6 ${hot ? "border-white/40 bg-white/10" : "border-white/10 bg-white/[0.04]"}`}>{children}</div>;
  const List = ({ items, dim }) => (
    <ul className="mt-5 flex-1 space-y-2.5 text-sm">
      {items.map((f) => <li key={f} className={`flex items-start gap-2.5 ${dim ? "text-violet-300/50" : "text-violet-100/85"}`}><span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-white/10"><Check size={12} /></span>{f}</li>)}
    </ul>
  );
  return (
    <div>
      <div className="mb-6 flex items-center justify-center gap-3 text-sm">
        <span className={yearly ? "text-violet-300/60" : "font-semibold"}>Monthly</span>
        <button aria-label="Toggle yearly billing" onClick={() => setYearly(!yearly)} className={`relative h-6 w-11 rounded-full transition ${yearly ? "bg-white" : "bg-white/20"}`}>
          <span className={`absolute top-1 h-4 w-4 rounded-full transition-all ${yearly ? "left-6 bg-black" : "left-1 bg-white"}`} />
        </button>
        <span className={yearly ? "font-semibold" : "text-violet-300/60"}>Yearly <span className="pill ml-1">save ~20%</span></span>
      </div>
      <div className="grid gap-5 md:grid-cols-3">
        <Card>
          <div className="text-sm text-violet-300/80">{free.name}</div>
          <div className="mt-2 text-4xl font-extrabold">Free</div>
          <div className="text-xs text-violet-300/60">forever</div>
          <List items={free.features} />
          <Btn variant="ghost" className="mt-6" disabled={current === "free" && !!cta} onClick={() => onChoose("free", yearly)}>{current === "free" && cta ? "Current plan" : "Start free"}</Btn>
        </Card>
        <Card hot>
          <div className="flex items-center justify-between text-sm text-violet-200">{pro.name}<span className="pill">Most popular</span></div>
          <div className="mt-2 text-4xl font-extrabold">{inr(price)}<span className="text-lg font-medium text-violet-300/70">/{yearly ? "yr" : "mo"}</span></div>
          <div className="text-xs text-violet-300/60">{yearly ? `${inr(Math.round(price / 12))} a month` : "billed monthly, cancel anytime"}</div>
          <List items={pro.features} />
          <Btn className="mt-6" disabled={current === "pro" && !!cta} onClick={() => onChoose("pro", yearly)}>{current === "pro" && cta ? "Current plan" : cta || "Get Pro"}</Btn>
        </Card>
        <Card>
          <div className="flex items-center justify-between text-sm text-violet-300/80">Agency<span className="pill">Roadmap</span></div>
          <div className="mt-2 text-4xl font-extrabold text-violet-300/70">Soon</div>
          <div className="text-xs text-violet-300/60">for small studios</div>
          <List items={AGENCY} dim />
          <Btn variant="ghost" className="mt-6" disabled>Not available yet</Btn>
        </Card>
      </div>
    </div>
  );
}
