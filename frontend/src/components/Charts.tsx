import type { Prediction } from "../types/prediction";
import KPI from "./ui/KPI";
import InfoTip from "./ui/InfoTip";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ResponsiveContainer,
  BarChart,
  Bar,
  Legend,
  ReferenceDot,
} from "recharts";

interface Driver {
  feature: string;
  value: string | number | boolean;
  impact: number;
}

interface ChartsProps {
  predictions: Prediction[];
  drivers: Driver[];
  simDrivers?: Driver[];
}

export default function Charts({ predictions, drivers, simDrivers }: ChartsProps) {
  const totalPredictions = predictions.length;
  const churnCount = predictions.filter((p) => p.isChurn).length;
  const churnRate = totalPredictions > 0 ? (churnCount / totalPredictions) * 100 : 0;
  const avgProbability = totalPredictions > 0
    ? predictions.reduce((sum, p) => sum + p.probability, 0) / totalPredictions
    : 0;

  const prevWindow = predictions.slice(Math.max(0, predictions.length - 10), Math.max(0, predictions.length - 5));
  const latestWindow = predictions.slice(Math.max(0, predictions.length - 5));
  const avgPrev = prevWindow.length ? prevWindow.reduce((s, p) => s + p.probability, 0) / prevWindow.length : avgProbability;
  const avgLatest = latestWindow.length ? latestWindow.reduce((s, p) => s + p.probability, 0) / latestWindow.length : avgProbability;
  const churnDelta = (avgLatest - avgPrev) * 100;

  const handleExportCSV = () => {
    const rows = [
      ["#", "Probability (%)", "Is Churn", "Timestamp"],
      ...predictions.map((p, i) => [
        i + 1,
        (p.probability * 100).toFixed(1),
        p.isChurn ? "Yes" : "No",
        new Date(p.timestamp).toLocaleString(),
      ]),
    ];
    const csv = rows.map((r) => r.join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "churn_predictions.csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Line chart data (probability trend)
  const trendData = predictions.map((p, index) => ({
    index: index + 1,
    probability: Number((p.probability * 100).toFixed(2)),
  }));

  const spike = trendData.reduce<{ index: number; probability: number } | null>((acc, item) => {
    if (!acc || item.probability > acc.probability) return item;
    return acc;
  }, null);

  // Segmented risk histogram data
  const riskBuckets = [
    { label: "0-20%", count: 0, segment: "Very Low" },
    { label: "20-40%", count: 0, segment: "Low" },
    { label: "40-60%", count: 0, segment: "Watch" },
    { label: "60-80%", count: 0, segment: "Elevated" },
    { label: "80-100%", count: 0, segment: "Critical" },
  ];
  
  predictions.forEach((p) => {
    if (p.probability < 0.2) riskBuckets[0].count++;
    else if (p.probability < 0.4) riskBuckets[1].count++;
    else if (p.probability < 0.6) riskBuckets[2].count++;
    else if (p.probability < 0.8) riskBuckets[3].count++;
    else riskBuckets[4].count++;
  });

  const highRiskCustomers = predictions.filter((p) => p.probability >= 0.7).length;
  const topActionable = drivers.filter((d) => d.impact > 0).slice(0, 3);

  if (predictions.length === 0) {
    return (
      <div className="rounded-2xl border border-border bg-surface p-6 text-sm text-muted">
        <p className="font-semibold text-ink">No analytics yet</p>
        <p className="mt-1">Run your first prediction to unlock trend charts, risk distribution, and driver insights.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Export */}
      <div className="flex justify-end">
        <button
          onClick={handleExportCSV}
          className="inline-flex items-center gap-1 rounded-lg border border-border bg-surface px-3 py-1.5 text-sm text-muted hover:border-accent/40 hover:text-ink transition"
        >
          Export CSV
        </button>
      </div>

      {/* KPIs Section */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <KPI title="Total Predictions" value={totalPredictions} />
        <KPI title="Churn Rate" value={churnRate} suffix="%" delta={churnDelta} />
        <KPI title="Avg. Risk Score" value={avgProbability * 100} suffix="%" />
        <KPI title="High-Risk (>=70%)" value={highRiskCustomers} />
      </div>

      <div className="rounded-2xl border border-border bg-accent-soft/50 p-4">
        <p className="text-xs uppercase tracking-[0.13em] text-muted">
          Top 3 actionable drivers
          <InfoTip content="These are the highest positive-impact factors currently pushing churn risk up, and usually offer the best intervention points." />
        </p>
        <div className="mt-3 grid gap-2 md:grid-cols-3">
          {topActionable.map((driver) => (
            <div key={driver.feature} className="rounded-xl border border-accent/25 bg-surface/80 p-3">
              <p className="text-sm font-semibold text-ink">{driver.feature}</p>
              <p className="text-xs text-muted">Impact +{driver.impact.toFixed(2)} on churn risk</p>
            </div>
          ))}
          {topActionable.length === 0 && (
            <p className="text-sm text-muted">No high-impact risk drivers yet.</p>
          )}
        </div>
      </div>

      {/* Swipeable chart cards on mobile */}
      <div className="-mx-2 overflow-x-auto px-2 md:mx-0 md:overflow-visible md:px-0">
        <div className="flex snap-x gap-4 pb-2 md:grid md:grid-cols-2 md:pb-0">
          <div className="min-w-[88%] snap-start rounded-2xl border border-border bg-surface p-4 md:min-w-0">
            <p className="text-sm font-semibold text-ink">Churn Probability Trend</p>
            <p className="mb-2 text-xs text-muted">Peak point is highlighted for quick anomaly scanning.</p>
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={trendData}>
                <CartesianGrid strokeDasharray="4 4" stroke="#d7e1e0" strokeOpacity={0.65} />
                <XAxis dataKey="index" tick={{ fill: "#5c6b6b", fontSize: 11 }} />
                <YAxis domain={[0, 100]} tickFormatter={(v: number) => `${v}%`} tick={{ fill: "#5c6b6b", fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ borderRadius: 12, borderColor: "#d7e1e0", color: "#1f2a2a" }}
                  formatter={(v) => (typeof v === "number" ? `${v}%` : "")}
                />
                <Legend />
                <Line type="monotone" dataKey="probability" name="Churn probability" stroke="#0f766e" strokeWidth={2.6} dot={{ r: 2.5 }} />
                {spike && (
                  <ReferenceDot
                    x={spike.index}
                    y={spike.probability}
                    r={5}
                    fill="#c2410c"
                    label={{ value: "Spike", position: "top", fill: "#c2410c", fontSize: 11 }}
                  />
                )}
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="min-w-[88%] snap-start rounded-2xl border border-border bg-surface p-4 md:min-w-0">
            <p className="text-sm font-semibold text-ink">
              Segmented Risk Histogram
              <InfoTip content="Each bar shows how many predictions fall in a risk range, grouped into business-friendly severity segments." />
            </p>
            <p className="mb-2 text-xs text-muted">Buckets are labeled by business-friendly severity tiers.</p>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={riskBuckets}>
                <CartesianGrid strokeDasharray="4 4" stroke="#d7e1e0" strokeOpacity={0.65} />
                <XAxis dataKey="label" tick={{ fill: "#5c6b6b", fontSize: 11 }} />
                <YAxis allowDecimals={false} tick={{ fill: "#5c6b6b", fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ borderRadius: 12, borderColor: "#d7e1e0", color: "#1f2a2a" }}
                  formatter={(value, _name, item) => {
                    const safeValue = typeof value === "number" ? value : 0;
                    return [`${safeValue} profiles`, item?.payload?.segment ?? "Segment"];
                  }}
                />
                <Legend />
                <Bar dataKey="count" name="Profiles" fill="#0f766e" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Top Drivers */}
      <div className="rounded-2xl border border-border bg-surface p-4">
        <p className="text-sm font-semibold text-ink">Top Drivers</p>
        <p className="mb-2 text-xs text-muted">Positive values increase churn risk. Negative values are protective.</p>
        {drivers.map((d) => (
          <div key={d.feature} className="mb-1 flex justify-between rounded-lg px-2 py-1 text-sm hover:bg-base/70">
            <span>{d.feature}</span>
            <span className={d.impact > 0 ? "text-copper" : "text-success"}>
              {d.impact > 0 ? "+" : ""}
              {d.impact.toFixed(2)}
            </span>
          </div>
        ))}
      </div>

      {/* Simulated Drivers */}
      {simDrivers && simDrivers.length > 0 && (
        <div className="rounded-2xl border border-border bg-surface p-4">
          <p className="text-sm font-semibold text-ink">Top Drivers (Simulated)</p>
          <p className="mb-2 text-xs text-muted">Use this to compare how adjustments shift key risk signals.</p>
          {simDrivers.map((d) => (
            <div key={d.feature} className="mb-1 flex justify-between rounded-lg px-2 py-1 text-sm hover:bg-base/70">
              <span>{d.feature}</span>
              <span className={d.impact > 0 ? "text-copper" : "text-success"}>
                {d.impact > 0 ? "+" : ""}
                {d.impact.toFixed(2)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
