import { Prediction } from "../types/prediction";
import KPI from "./ui/KPI";

interface ChartsProps {
  predictions: Prediction[];
}

export default function Charts({ predictions }: ChartsProps) {
  const totalPredictions = predictions.length;
  const churnCount = predictions.filter(p => p.isChurn).length;
  const safeCount = totalPredictions - churnCount;
  const CHURN_THRESHOLD = 0.5;
  const churnRate = totalPredictions > 0 ? (churnCount / totalPredictions) * 100 : 0;
  const probabilities = predictions.map(p => p.probability);
  const avgProbability = 
      totalPredictions > 0
          ? predictions.reduce((sum, p) => sum + p.probability, 0) / totalPredictions
          : 0;
  const buckets = [0, 0, 0, 0, 0];
  predictions.forEach(p => {
    if (p.probability < 0.2) buckets[0]++;
    else if (p.probability < 0.4) buckets[1]++;
    else if (p.probability < 0.6) buckets[2]++;
    else if (p.probability < 0.8) buckets[3]++;
    else buckets[4]++;
  });

  const highRiskCustomers = 
    predictions.filter(p => p.probability >= 0.7).length;  

  if (predictions.length === 0) {
    return (
      <div className="text-sm text-steel">
        No predictions made yet. Run a prediction to see charts and insights.
      </div>
    );
  }

  return (
    <div>
      {/* KPIs Section */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <KPI title="Total Predictions" value={totalPredictions} />
        <KPI title="Churn Rate" value={`${churnRate.toFixed(1)}%`} />
        <KPI title="Avg. Churn Probability" value={`${(avgProbability * 100).toFixed(1)}%`} />
        <KPI title="High-Risk Customers (>=70%)" value={highRiskCustomers} />
      </div>

      {/* Churn Probability Trend */}
      <div className="rounded-xl border border-sand p-4 mb-6">
        <p className="text-sm font-semibold text-steel mb-2">Churn Probability Trend</p>

        <div className="flex items-end gap-2 h-32">
          {probabilities.map((prob, i) => (
            <div
              key={i}
              className="flex-1 rounded bg-steel transition-all duration-500 ease-out"
              style={{ height: `${prob * 100}%` }}
              title={`Prediction ${i + 1}: ${(prob*100).toFixed(1)}%`}
            />
          ))}
        </div>
      </div>

      {/* Risk Distribution */}
      <div className="rounded-xl border border-sand p-4">
        <p className="text-sm font-semibold text-steel mb-2">Risk Distribution</p>
        <div className="grid grid-cols-5 gap-2 h-24 items-end">
          {buckets.map((count, i) => (
            <div key={i} className="text-center">
              <div
                className="mx-auto w-8 rounded bg-taupe transition-all duration-500 ease-out"
                style={{ height: `${count * 20} px` }}
              />
              <p className="text-xs text-steel mt-1">
                {i * 20}-{i * 20 + 20}%
              </p>
            </div>))}
        </div>
      </div>



      <div className="text-sm text-steel">
        Total predictions: {totalPredictions}
      </div>
      <div className="text-sm text-steel">
        Churned customers: {churnCount}
      </div>

      <div className="mt-4 p-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 rounded-md">
          <div className="rounded-xl border border-sand p-4">
            <p className="text-sm text-steel">Top Drivers (demo)</p>
            <ul className="mt-2 space-y-1 text-sm text-ink">
              <li>Contract: Month-to-month</li>
              <li>InternetService: Fiber optic</li>
              <li>PaymentMethod: Electronic check</li>
            </ul>
          </div>

          <div className="rounded-xl border border-sand p-4">
            <p className="text-sm text-steel">Charges Distribution (demo)</p>
            <div className="mt-2 h-24 bg-gradient-to-r from-sand to-taupe rounded" />
          </div>

          <div className="rounded-xl border border-sand p-4">
            <p className="text-sm text-steel">Tenure Breakdown (demo)</p>
            <div className="mt-2 grid grid-cols-5 gap-2">
              {["0-6","6-12","12-24","24-48","48+"].map((label, i) => (
                <div key={label} className="text-center rounded-md">
                  <div className="mx-auto w-6 rounded bg-steel" style={{ height: `${20 + i * 8}px` }} />
                  <span className="mt-1 block text-xs text-taupe">{label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
