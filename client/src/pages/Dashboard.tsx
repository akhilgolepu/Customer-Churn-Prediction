import { useState } from "react";
import Section from "../components/ui/Section";
import ChurnForm from "../components/ChurnForm";
import PredictionCard from "../components/PredictionCard";
import Charts from "../components/Charts";
import type { Prediction } from "../types/prediction";
import { predictChurn, explainChurn } from "../services/api";
import type { FormState } from "../types/formState";

export default function Dashboard() {
  const [currentPrediction, setCurrentPrediction] = useState<Prediction | null>(null);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [drivers, setDrivers] = useState<any[]>([]);

  const [basePrediction, setBasePrediction] = useState<Prediction | null>(null);
  const [simPrediction, setSimPrediction] = useState<Prediction | null>(null);
  const [simDrivers, setSimDrivers] = useState<any[]>([]);

  const [baseForm, setBaseForm] = useState<FormState | null>(null);

  const [isPredicting, setIsPredicting] = useState(false);
  const [isSimulating, setIsSimulating] = useState(false);

  const handlePredict = async (formData: FormState) => {
    try {
      setIsPredicting(true);

      const explainResponse = await explainChurn(formData);
      setDrivers(explainResponse.top_drivers || []);

      const response = await predictChurn(formData);

      const prediction: Prediction = {
        probability: response.probability,
        isChurn: response.isChurn,
        timestamp: Date.now(),
      };

      setPredictions((prev) => [...prev, prediction]);
      setCurrentPrediction(prediction);

      setBaseForm(formData);
      setBasePrediction(prediction);

      setSimPrediction(null);
      setSimDrivers([]);
    } catch (error) {
      console.error("Prediction failed:", error);
      alert("Prediction failed. Please check the backend connection.");
    } finally {
      setIsPredicting(false);
    }
  };

  const handleSimulate = async (formData: FormState) => {
    try {
      setIsSimulating(true);

      const exp = await explainChurn(formData);
      const res = await predictChurn(formData);

      setSimPrediction({
        probability: res.probability,
        isChurn: res.isChurn,
        timestamp: Date.now(),
      });

      setSimDrivers(exp.top_drivers || []);
    } catch (error) {
      console.error("Simulation failed:", error);
      alert("Simulation failed. Please check the backend connection.");
    } finally {
      setIsSimulating(false);
    }
  };

  return (
    <div className="flex flex-col bg-paper rounded-md">
      {/* ================= HEADER ================= */}
      <header className="bg-paper border-b border-sand">
        <div className="px-6 py-4 rounded-md text-center">
          <h1 className="text-3xl font-bold text-ink">Customer Churn Prediction</h1>
          <p className="text-steel">Predict whether a customer is likely to churn</p>
        </div>
      </header>

      {/* ================= OVERVIEW ================= */}
      <div className="px-6 py-6">
        <Section className="rounded-xl border border-sand bg-paper p-6 shadow-sm">
          {/* Title */}
          <div className="text-center">
            <h2 className="text-lg font-semibold text-ink">Project & Model Overview</h2>

            <p className="mt-2 text-steel text-sm max-w-4xl mx-auto leading-relaxed">
              End-to-end <span className="font-semibold text-ink">Customer Churn Prediction</span> system powered by{" "}
              <span className="font-semibold text-ink">CatBoost</span>, with{" "}
              <span className="font-semibold text-ink">SHAP explainability</span> and{" "}
              <span className="font-semibold text-ink">What-if simulation</span> for business decision-making.
            </p>

            <p className="mt-1 text-xs text-taupe">
              Backend recreates engineered features (TenureGroup, TotalServices, risk flags) exactly as training for full parity.
            </p>
          </div>

          {/* Tech badges */}
          <div className="mt-4 flex flex-wrap justify-center gap-2">
            {[
              "React + TypeScript",
              "TailwindCSS",
              "FastAPI REST API",
              "CatBoost Classifier",
              "SHAP Top Drivers",
              "Recharts Analytics",
            ].map((tag) => (
              <span
                key={tag}
                className="px-3 py-1 rounded-full border border-sand text-xs text-steel bg-paper"
              >
                {tag}
              </span>
            ))}
          </div>

          {/* Key points in 2-column grid (cleaner than paragraphs) */}
          <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4 text-sm text-steel leading-relaxed">
            <div>
              <p className="font-semibold text-ink">Frontend Input Layer</p>
              <p className="mt-1">
                Collects only business-friendly customer inputs. Complex engineered features are not exposed to the user.
              </p>
            </div>

            <div>
              <p className="font-semibold text-ink">Backend Feature Engineering</p>
              <p className="mt-1">
                Rebuilds training-time features like <span className="font-semibold text-ink">TotalServices</span>,{" "}
                <span className="font-semibold text-ink">TenureGroup</span>, and risk indicators to prevent mismatches.
              </p>
            </div>

            <div>
              <p className="font-semibold text-ink">Prediction Engine (CatBoost)</p>
              <p className="mt-1">
                Outputs churn probability + churn label using threshold logic. Handles categorical features natively.
              </p>
            </div>

            <div>
              <p className="font-semibold text-ink">Explainability (SHAP)</p>
              <p className="mt-1">
                Shows top drivers behind each prediction.{" "}
                <span className="font-semibold text-ink">Green</span> lowers churn risk,{" "}
                <span className="font-semibold text-ink">Red</span> increases churn risk.
              </p>
            </div>

            <div>
              <p className="font-semibold text-ink">What-if Simulator</p>
              <p className="mt-1">
                Compare Base vs Simulated prediction and view Δ change to test retention strategies instantly.
              </p>
            </div>

            <div>
              <p className="font-semibold text-ink">Analytics & Insights</p>
              <p className="mt-1">
                Tracks prediction history with trends, risk distribution, high-risk counts, and KPIs for monitoring.
              </p>
            </div>
          </div>

          {/* System flow (lighter styling so it doesn't feel like a separate section) */}
          <div className="mt-6 rounded-xl border border-sand/60 bg-paper px-5 py-4">
            <p className="text-xs font-semibold tracking-wide text-taupe uppercase text-center">
              System Flow
            </p>

            <div className="mt-3 flex flex-wrap justify-center items-center gap-3 text-sm text-steel ">
              <span className="px-3 py-1 rounded-lg border border-sand bg-paper transition transform hover:-translate-y-0.5 hover:shadow-md">
                UI Form
                <span className="block text-xs text-taupe">Customer Inputs</span>
              </span>

              <span className="text-taupe">→</span>

              <span className="px-3 py-1 rounded-lg border border-sand bg-paper transition transform hover:-translate-y-0.5 hover:shadow-md">
                FastAPI
                <span className="block text-xs text-taupe">Validation + Features</span>
              </span>

              <span className="text-taupe">→</span>

              <span className="px-3 py-1 rounded-lg border border-sand bg-paper transition transform hover:-translate-y-0.5 hover:shadow-md">
                CatBoost + SHAP
                <span className="block text-xs text-taupe">Predict + Explain</span>
              </span>
            </div>

            <p className="mt-4 text-xs text-taupe text-center">
              Quick test: try{" "}
              <span className="font-semibold text-ink">Month-to-month</span> +{" "}
              <span className="font-semibold text-ink">Fiber</span> +{" "}
              <span className="font-semibold text-ink">Electronic check</span>{" "}
              to observe higher churn risk.
            </p>
          </div>
        </Section>
      </div>

      {/* ================= MAIN CONTENT ================= */}
      <main className="flex-1 px-6 pb-6 w-full">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 rounded-md">
          {/* LEFT: Input Form */}
          <div className="md:col-span-1 rounded-md">
            <Section className="h-full">
              <h2 className="text-lg font-semibold mb-4 text-ink text-center">
                Customer Details
              </h2>

              <ChurnForm
                onSubmit={handlePredict}
                onSimulate={handleSimulate}
                isPredicting={isPredicting}
                isSimulating={isSimulating}
                canSimulate={!!baseForm}
              />
            </Section>
          </div>

          {/* RIGHT */}
          <div className="md:col-span-2 flex flex-col gap-6 rounded-md">
            {/* Prediction Result */}
            <Section>
              <h2 className="text-lg font-semibold mb-4 text-ink text-center">
                Prediction Result
              </h2>

              <PredictionCard
                probability={currentPrediction?.probability ?? null}
                isChurn={currentPrediction?.isChurn ?? null}
                isLoading={isPredicting}
              />

              {/* What-if Comparison */}
              {basePrediction && (
                <div className="mt-4 rounded-xl border border-sand p-4 transition transform hover:-translate-y-0.5 hover:shadow-md">
                  <p className="text-sm font-semibold text-ink mb-2">What-if Comparison</p>

                  <div className="grid grid-cols-3 gap-4 text-sm">
                    <div>
                      <p className="text-xs text-steel">Base</p>
                      <p className="font-semibold text-ink">
                        {(basePrediction.probability * 100).toFixed(1)}%
                      </p>
                    </div>

                    <div>
                      <p className="text-xs text-steel">Simulated</p>
                      <p className="font-semibold text-ink">
                        {simPrediction ? `${(simPrediction.probability * 100).toFixed(1)}%` : "—"}
                      </p>
                    </div>

                    <div>
                      <p className="text-xs text-steel">Δ Change</p>
                      <p className="font-semibold text-ink">
                        {simPrediction
                          ? `${((simPrediction.probability - basePrediction.probability) * 100).toFixed(1)}%`
                          : "—"}
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </Section>

            {/* Charts */}
            <Section>
              <h2 className="text-lg font-semibold mb-4 text-ink text-center">
                Charts & Insights
              </h2>

              <Charts
                predictions={predictions}
                drivers={drivers}
                simDrivers={simDrivers}
              />
            </Section>
          </div>
        </div>
      </main>

      {/* ================= FOOTER ================= */}
      <footer className="bg-paper border-t border-sand">
        <div className="px-6 py-4 text-center text-sm text-taupe rounded-md">
          © 2025 Customer Churn Prediction Dashboard
        </div>
      </footer>
    </div>
  );
}
