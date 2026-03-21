import { useEffect, useMemo, useState } from "react";
import Section from "../components/ui/Section";
import ChurnForm from "../components/ChurnForm";
import PredictionCard from "../components/PredictionCard";
import Charts from "../components/Charts";
import KPI from "../components/ui/KPI";
import InfoTip from "../components/ui/InfoTip";
import type { Prediction } from "../types/prediction";
import { predictChurn, explainChurn } from "../services/api";
import type { FormState } from "../types/formState";

interface Driver {
  feature: string;
  value: string | number;
  impact: number;
}

const FIELD_LABELS: Partial<Record<keyof FormState, string>> = {
  MonthlyCharges: "Monthly Charges",
  tenure: "Tenure",
  TotalCharges: "Total Charges",
  Contract: "Contract",
  PaymentMethod: "Payment Method",
  TechSupport: "Tech Support",
  OnlineSecurity: "Online Security",
  InternetService: "Internet Service",
};

function inferRiskBand(probability: number | null) {
  if (probability === null) return "No score";
  if (probability < 0.35) return "Low";
  if (probability < 0.65) return "Medium";
  return "High";
}

export default function Dashboard() {
  const [currentPrediction, setCurrentPrediction] = useState<Prediction | null>(() => {
    try {
      const stored = localStorage.getItem("churn_current_prediction");
      return stored ? (JSON.parse(stored) as Prediction) : null;
    } catch {
      return null;
    }
  });
  const [predictions, setPredictions] = useState<Prediction[]>(() => {
    try {
      const stored = localStorage.getItem("churn_predictions");
      return stored ? (JSON.parse(stored) as Prediction[]) : [];
    } catch {
      return [];
    }
  });

  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [simDrivers, setSimDrivers] = useState<Driver[]>([]);

  const [baseForm, setBaseForm] = useState<FormState | null>(null);
  const [simForm, setSimForm] = useState<FormState | null>(null);
  const [basePrediction, setBasePrediction] = useState<Prediction | null>(null);
  const [simPrediction, setSimPrediction] = useState<Prediction | null>(null);

  const [isPredicting, setIsPredicting] = useState(false);
  const [isSimulating, setIsSimulating] = useState(false);
  const [showHowItWorks, setShowHowItWorks] = useState(false);

  useEffect(() => {
    localStorage.setItem("churn_predictions", JSON.stringify(predictions));
  }, [predictions]);

  useEffect(() => {
    if (currentPrediction) {
      localStorage.setItem("churn_current_prediction", JSON.stringify(currentPrediction));
    }
  }, [currentPrediction]);

  const handlePredict = async (formData: FormState) => {
    try {
      setIsPredicting(true);
      const [explainResponse, response] = await Promise.all([explainChurn(formData), predictChurn(formData)]);

      const prediction: Prediction = {
        probability: response.probability,
        isChurn: response.isChurn,
        timestamp: Date.now(),
      };

      setDrivers(explainResponse.top_drivers || []);
      setPredictions((prev) => [...prev, prediction]);
      setCurrentPrediction(prediction);
      setBaseForm(formData);
      setBasePrediction(prediction);
      setSimPrediction(null);
      setSimForm(null);
      setSimDrivers([]);
    } catch (error) {
      console.error("Prediction failed:", error);
      alert("Prediction failed. Please verify backend availability.");
    } finally {
      setIsPredicting(false);
    }
  };

  const handleSimulate = async (formData: FormState) => {
    try {
      setIsSimulating(true);
      const [exp, res] = await Promise.all([explainChurn(formData), predictChurn(formData)]);

      setSimPrediction({
        probability: res.probability,
        isChurn: res.isChurn,
        timestamp: Date.now(),
      });
      setSimForm(formData);
      setSimDrivers(exp.top_drivers || []);
    } catch (error) {
      console.error("Simulation failed:", error);
      alert("Simulation failed. Please verify backend availability.");
    } finally {
      setIsSimulating(false);
    }
  };

  const avgProb = predictions.length
    ? predictions.reduce((sum, p) => sum + p.probability, 0) / predictions.length
    : 0;
  const recent = predictions.slice(-5);
  const previous = predictions.slice(-10, -5);
  const recentAvg = recent.length ? recent.reduce((sum, p) => sum + p.probability, 0) / recent.length : avgProb;
  const previousAvg = previous.length
    ? previous.reduce((sum, p) => sum + p.probability, 0) / previous.length
    : avgProb;
  const trendDelta = (recentAvg - previousAvg) * 100;

  const changedFields = useMemo(() => {
    if (!baseForm || !simForm) return [];

    return Object.keys(baseForm)
      .filter((key) => baseForm[key as keyof FormState] !== simForm[key as keyof FormState])
      .slice(0, 5)
      .map((key) => {
        const typed = key as keyof FormState;
        return {
          key,
          label: FIELD_LABELS[typed] || key,
          from: String(baseForm[typed]),
          to: String(simForm[typed]),
        };
      });
  }, [baseForm, simForm]);

  const simDelta = simPrediction && basePrediction
    ? (simPrediction.probability - basePrediction.probability) * 100
    : null;

  return (
    <div className="min-h-screen bg-base px-4 py-6 text-ink md:px-6 lg:px-8">
      <div className="mx-auto max-w-[1320px] space-y-6">
        <header className="fade-stagger rounded-3xl border border-border bg-surface/90 p-6 shadow-[0_15px_40px_rgba(31,42,42,0.08)] backdrop-blur-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-muted">Teal + Copper ML Studio</p>
              <h1 className="mt-1 text-4xl font-extrabold md:text-5xl">Customer Churn Intelligence</h1>
              <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted md:text-base">
                Predict churn, explain top risk drivers, and run What-if simulations with model-aligned feature engineering.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setShowHowItWorks(true)}
              className="rounded-xl border border-border bg-surface px-4 py-2 text-sm font-semibold text-ink transition hover:border-accent"
            >
              How prediction is calculated
            </button>
          </div>

          <div className="mt-5 grid gap-4 md:grid-cols-4">
            <KPI title="Profiles Scored" value={predictions.length} />
            <KPI title="Avg Churn Risk" value={avgProb * 100} suffix="%" delta={trendDelta} />
            <KPI title="Current Risk Band" value={inferRiskBand(currentPrediction?.probability ?? null)} />
            <KPI title="Likely Churn" value={predictions.filter((p) => p.isChurn).length} />
          </div>
        </header>

        <div className="fade-stagger rounded-2xl border border-border bg-accent-soft/45 px-4 py-3 text-sm text-ink" style={{ animationDelay: "90ms" }}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-4">
              <p>
                <span className="font-semibold">Model:</span> CatBoost + SHAP
                <InfoTip content="CatBoost predicts churn probability; SHAP explains which input features most influenced that prediction." />
              </p>
              <p><span className="font-semibold">Last trained:</span> Mar 2026</p>
              <p><span className="font-semibold">Dataset:</span> 7,043 records</p>
              <p>
                <span className="font-semibold">Validation:</span> AUC 0.84 / F1 0.73
                <InfoTip content="AUC measures ranking quality across thresholds. F1 balances precision and recall for churn detection." />
              </p>
            </div>
            <span className="rounded-full bg-surface px-3 py-1 text-xs font-semibold text-accent">Production-style simulation panel</span>
          </div>
        </div>

        <main className="grid gap-6 lg:grid-cols-12">
          <aside className="fade-stagger lg:col-span-4" style={{ animationDelay: "130ms" }}>
            <div className="lg:sticky lg:top-5">
              <Section>
                <h2 className="text-xl font-bold">Customer Inputs</h2>
                <p className="mt-1 text-sm text-muted">Adjust the profile and run prediction or simulation.</p>
                <div className="mt-4">
                  <ChurnForm
                    onSubmit={handlePredict}
                    onSimulate={handleSimulate}
                    isPredicting={isPredicting}
                    isSimulating={isSimulating}
                    canSimulate={!!baseForm}
                  />
                </div>
              </Section>
            </div>
          </aside>

          <section className="fade-stagger space-y-6 lg:col-span-8" style={{ animationDelay: "170ms" }}>
            <Section>
              <h2 className="text-2xl font-bold">
                Decision Panel
                <InfoTip content="This panel combines the raw probability score, final risk tier, and practical next-step suggestions." />
              </h2>
              <p className="mb-4 mt-1 text-sm text-muted">Live result canvas with confidence and recommended interventions.</p>
              <PredictionCard
                probability={currentPrediction?.probability ?? null}
                isChurn={currentPrediction?.isChurn ?? null}
                isLoading={isPredicting}
                drivers={drivers}
              />

              {basePrediction && (
                <div className="mt-5 rounded-2xl border border-border bg-base/65 p-4">
                  <p className="text-xs uppercase tracking-[0.13em] text-muted">
                    What-if compare mode
                    <InfoTip content="Baseline is the latest real prediction. Simulated is the result after you tweak fields to test retention ideas." />
                  </p>

                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    <div className="rounded-xl border border-border bg-surface p-4">
                      <p className="text-xs text-muted">Baseline</p>
                      <p className="mt-1 text-2xl font-bold text-ink">{(basePrediction.probability * 100).toFixed(1)}%</p>
                      <span className="rounded-full bg-accent-soft px-2 py-1 text-xs font-semibold text-accent">
                        {inferRiskBand(basePrediction.probability)} risk
                      </span>
                    </div>

                    <div className="rounded-xl border border-border bg-surface p-4 transition-all duration-200">
                      <p className="text-xs text-muted">Simulated</p>
                      <p className="mt-1 text-2xl font-bold text-ink">
                        {simPrediction ? `${(simPrediction.probability * 100).toFixed(1)}%` : "Waiting..."}
                      </p>
                      <div className="flex items-center gap-2">
                        <span className="rounded-full bg-accent-soft px-2 py-1 text-xs font-semibold text-accent">
                          {simPrediction ? `${inferRiskBand(simPrediction.probability)} risk` : "Run simulation"}
                        </span>
                        {simDelta !== null && (
                          <span
                            className={`rounded-full px-2 py-1 text-xs font-semibold transition-all duration-200 ${
                              simDelta < 0 ? "bg-success/10 text-success" : "bg-copper/10 text-copper"
                            }`}
                          >
                            {simDelta < 0 ? "Risk reduced" : "Risk increased"} {simDelta > 0 ? "+" : ""}{simDelta.toFixed(1)}%
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {changedFields.length > 0 && (
                    <div className="mt-4">
                      <p className="mb-2 text-xs uppercase tracking-[0.13em] text-muted">Changed inputs</p>
                      <div className="flex flex-wrap gap-2">
                        {changedFields.map((item) => (
                          <span key={item.key} className="rounded-full border border-border bg-surface px-3 py-1 text-xs text-ink">
                            {item.label}: {item.from} {"->"} {item.to}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {simDelta !== null && (
                    <p className="mt-3 text-sm text-muted">
                      Impact summary: {simDelta < 0 ? "Risk reduced" : "Risk increased"} by {Math.abs(simDelta).toFixed(1)} percentage points.
                    </p>
                  )}
                </div>
              )}
            </Section>

            <Section>
              <h2 className="text-2xl font-bold">
                Executive Insights
                <InfoTip content="Charts summarize trend, concentration of risk, and top model drivers to support quick business decisions." />
              </h2>
              <p className="mb-4 mt-1 text-sm text-muted">Trend, distribution, and driver analysis optimized for quick interpretation.</p>
              <Charts predictions={predictions} drivers={drivers} simDrivers={simDrivers} />
            </Section>
          </section>
        </main>
      </div>

      {showHowItWorks && (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-ink/55 px-4">
          <div className="w-full max-w-xl rounded-2xl border border-border bg-surface p-6 shadow-2xl">
            <div className="flex items-start justify-between">
              <h3 className="text-2xl font-bold">How prediction is calculated</h3>
              <button
                type="button"
                onClick={() => setShowHowItWorks(false)}
                className="rounded-lg border border-border px-2 py-1 text-sm text-muted"
              >
                Close
              </button>
            </div>
            <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-muted">
              <li>Raw form fields are validated and transformed into engineered features.</li>
              <li>CatBoost generates a churn probability score from 0 to 1.</li>
              <li>Threshold logic maps that score to Likely to Churn or Likely to Stay.</li>
              <li>SHAP ranks the strongest feature contributions for explainability.</li>
            </ol>
            <p className="mt-3 text-xs text-muted">All simulations use the same pipeline, so baseline and simulated outputs are directly comparable.</p>
          </div>
        </div>
      )}
    </div>
  );
}
