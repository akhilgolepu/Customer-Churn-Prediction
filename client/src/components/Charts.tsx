import type { Prediction } from "../types/prediction";
import KPI from "./ui/KPI";
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
} from "recharts";

interface Driver {
  feature: string;
  value: any;
  impact: number;
}

interface ChartsProps {
  predictions: Prediction[];
  drivers: Driver[];
  simDrivers?: Driver[];
}

export default function Charts({ predictions, drivers, simDrivers }: ChartsProps) {
  const totalPredictions = predictions.length;
  const churnCount = predictions.filter(p => p.isChurn).length;
  const churnRate = totalPredictions > 0 ? (churnCount / totalPredictions) * 100 : 0;
  const avgProbability = 
      totalPredictions > 0
          ? predictions.reduce((sum, p) => sum + p.probability, 0) / totalPredictions
          : 0;

  //Line Chart data (probability trend)
  const trendData = predictions.map((p, index) => ({
    index: index + 1,
    probability: Number((p.probability * 100).toFixed(2)),
  }));

  //Bar Chart data (Risk Distribution)
  const riskBuckets = [
    { label: "0-20%", count: 0 },
    { label: "20-40%", count: 0 },
    { label: "40-60%", count: 0 },
    { label: "60-80%", count: 0 },
    { label: "80-100%", count: 0 },
  ];
  
  predictions.forEach(p => {
    if (p.probability < 0.2) riskBuckets[0].count++;
    else if (p.probability < 0.4) riskBuckets[1].count++;
    else if (p.probability < 0.6) riskBuckets[2].count++;
    else if (p.probability < 0.8) riskBuckets[3].count++;
    else riskBuckets[4].count++;
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
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6 ">
        <KPI title="Total Predictions" value={totalPredictions} />
        <KPI title="Churn Rate" value={`${churnRate.toFixed(1)}%`} />
        <KPI title="Avg. Churn Probability" value={`${(avgProbability * 100).toFixed(1)}%`} />
        <KPI title="High-Risk Customers (>=70%)" value={highRiskCustomers} />
      </div>

      {/* Churn Probability Trend */}
      <div className="rounded-xl border border-sand p-4 mb-6">
        <p className="text-sm font-semibold text-steel mb-2">Churn Probability Trend</p>

        <ResponsiveContainer width="100%" height={250}>
          <LineChart data={trendData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="index" />
            <YAxis domain={[0, 100]} tickFormatter={(v: number) => `${v}%`} />
            <Tooltip formatter={(v) => typeof v === 'number' ? `${v}%` : ''} />
            <Legend />
            <Line 
              type="monotone" 
              dataKey="probability" 
              stroke="#4b5563" 
              strokeWidth={2}
              dot={{ r: 3 }} 
              isAnimationActive  
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Risk Distribution */}
      <div className="rounded-xl border border-sand p-4 mb-6">
        <p className="text-sm font-semibold text-steel mb-2">Risk Distribution</p>
        <ResponsiveContainer width="100%" height={250}>
          <BarChart data={riskBuckets}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="label" />
            <YAxis allowDecimals={false} />
            <Tooltip />
            <Legend />
            <Bar 
              dataKey="count"
              fill="#9CA3AF"
              isAnimationActive  
            />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Top Drivers */}
      <div className="rounded-xl border border-sand p-4 mb-6">
        <p className="text-sm font-semibold text-steel mb-2">Top Drivers</p>
        {drivers.map(d => (
          <div key={d.feature} className="flex justify-between text-sm">
            <span>{d.feature}</span>
            <span className={d.impact > 0 ? "text-red-600" : "text-green-600"}>
              {(d.impact).toFixed(2)}
            </span>
          </div>
        ))}
      </div>

      {/* Simulated Drivers */}
      {simDrivers && simDrivers.length > 0 && (
        <div className="rounded-xl border border-sand p-4">
          <p className="text-sm font-semibold text-steel mb-2">Top Drivers (Simulated)</p>
          {simDrivers.map(d => (
            <div key={d.feature} className="flex justify-between text-sm">
              <span>{d.feature}</span>
              <span className={d.impact > 0 ? "text-red-600" : "text-green-600"}>
                {(d.impact).toFixed(2)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
