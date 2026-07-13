import InfoTip from "./ui/InfoTip";

interface Driver {
  feature: string;
  impact: number;
}

interface PredictionCardProps {
  probability: number | null;
  isChurn: boolean | null;
  isLoading: boolean;
  drivers?: Driver[];
}

function getRiskTier(probability: number) {
  if (probability < 0.35) return { label: "Low", className: "bg-success/10 text-success" };
  if (probability < 0.65) return { label: "Medium", className: "bg-warning/10 text-warning" };
  return { label: "High", className: "bg-copper/10 text-copper" };
}

function getActionHints(drivers: Driver[] = []) {
  const riskDrivers = drivers.filter((d) => d.impact > 0).slice(0, 3).map((d) => d.feature);
  const hints: string[] = [];

  if (riskDrivers.includes("IsMonthToMonth") || riskDrivers.includes("Contract")) {
    hints.push("Recommend moving to annual contract with small loyalty incentive.");
  }
  if (riskDrivers.includes("TechSupport") || riskDrivers.includes("TechIssueRisk")) {
    hints.push("Offer discounted tech support bundle for first 3 months.");
  }
  if (riskDrivers.includes("PaymentRisk") || riskDrivers.includes("PaymentMethod")) {
    hints.push("Encourage autopay migration with billing credits.");
  }
  if (hints.length === 0) {
    hints.push("Keep monitoring this profile; current risk drivers are balanced.");
  }

  return hints.slice(0, 2);
}

export default function PredictionCard({ probability, isChurn, isLoading, drivers }: PredictionCardProps) {
  const normalized = probability ?? 0;
  const percent = normalized * 100;
  const tier = getRiskTier(normalized);
  const circumference = 2 * Math.PI * 54;
  const dashoffset = circumference - (percent / 100) * circumference;
  const hints = getActionHints(drivers);

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="rounded-2xl border border-border bg-surface p-6">
          <div className="shimmer h-5 w-36 rounded" />
          <div className="mt-4 shimmer h-36 w-36 rounded-full" />
          <div className="mt-5 shimmer h-4 w-full rounded" />
          <div className="mt-2 shimmer h-4 w-5/6 rounded" />
        </div>
        <div className="rounded-2xl border border-border bg-surface p-6">
          <div className="shimmer h-5 w-28 rounded" />
          <div className="mt-4 shimmer h-9 w-40 rounded-lg" />
          <div className="mt-5 shimmer h-4 w-full rounded" />
          <div className="mt-2 shimmer h-4 w-11/12 rounded" />
          <div className="mt-2 shimmer h-4 w-9/12 rounded" />
        </div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <div className="fade-stagger rounded-2xl border border-border bg-surface p-6 shadow-[0_14px_28px_rgba(31,42,42,0.08)]">
        <p className="text-xs uppercase tracking-[0.14em] text-muted">
          Prediction Confidence
          <InfoTip content="The ring visualizes churn probability from 0 to 100%. It is the model score before converting to a final churn label." />
        </p>
        <div className="mt-4 flex items-center gap-5">
          <div className="relative flex h-34 w-34 items-center justify-center">
            <svg className="h-34 w-34 -rotate-90" viewBox="0 0 120 120">
              <circle cx="60" cy="60" r="54" fill="none" stroke="#d7e1e0" strokeWidth="8" />
              <circle
                cx="60"
                cy="60"
                r="54"
                fill="none"
                stroke="#0f766e"
                strokeWidth="8"
                strokeLinecap="round"
                strokeDasharray={circumference}
                strokeDashoffset={dashoffset}
                style={{ transition: "stroke-dashoffset 260ms ease-out" }}
              />
            </svg>
            <div className="absolute text-center">
              <p className="text-3xl font-bold text-ink">{percent.toFixed(1)}%</p>
              <p className="text-xs text-muted">churn risk</p>
            </div>
          </div>
          <div>
            <span className={`rounded-full px-3 py-1 text-xs font-semibold ${tier.className}`}>
              {tier.label} Risk
            </span>
            <p className="mt-3 text-lg font-semibold text-ink">
              {isChurn === null ? "No prediction yet" : isChurn ? "Likely to Churn" : "Likely to Stay"}
            </p>
            <p className="mt-2 text-sm text-muted">
              Confidence ring reflects the model score after feature engineering and calibration thresholding.
            </p>
          </div>
        </div>
      </div>

      <div className="fade-stagger rounded-2xl border border-border bg-surface p-6 shadow-[0_14px_28px_rgba(31,42,42,0.08)]" style={{ animationDelay: "70ms" }}>
        <p className="text-xs uppercase tracking-[0.14em] text-muted">
          Action Suggestions
          <InfoTip content="These suggestions are generated from the strongest positive churn drivers identified in the latest explanation." />
        </p>
        <div className="mt-3 rounded-xl border border-accent/20 bg-accent-soft/45 p-4">
          <p className="text-sm font-semibold text-ink">Recommended next step</p>
          <ul className="mt-2 space-y-2 text-sm text-muted">
            {hints.map((hint) => (
              <li key={hint} className="flex gap-2">
                <span className="mt-1 h-1.5 w-1.5 rounded-full bg-accent" />
                <span>{hint}</span>
              </li>
            ))}
          </ul>
        </div>
        <p className="mt-4 text-xs text-muted">
          Tip: run What-if simulation after changing contract, support, or payment method to quantify risk reduction.
        </p>
      </div>
    </div>
  );
}
