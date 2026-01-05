import { useState } from "react";
import Section from "../components/ui/Section";
import ChurnForm from "../components/ChurnForm";
import PredictionCard from "../components/PredictionCard";
import Charts from "../components/Charts";
import { Prediction } from "../types/prediction";
import { FormState } from "../types/formState";

const CHURN_THRESHOLD = 0.5;

export default function Dashboard() {
  const [currentPrediction, setCurrentPrediction] = useState<Prediction | null>(null);

  const [formData, setFormData] = useState<FormState | null>(null);

  const [predictions, setPredictions] = useState<Prediction[]>([]);

  const [isPredicting, setIsPredicting] = useState(false);

  const handlePredict = (data: FormState) => {
    // Predicting starts
    setIsPredicting(true);
    console.log("Predicting with data:", data); // Optional: log the data to show it's being received

    // API call
    setTimeout(() => {
      const probability = Number(
        (Math.random() * 0.8 + 0.1).toFixed(3)
      );

      const isChurn = probability >= CHURN_THRESHOLD;

      const prediction: Prediction = {
        probability,
        isChurn,
        timestamp: Date.now(),
      };
      setPredictions(prev => [...prev, prediction]);
      setCurrentPrediction(prediction);
      setIsPredicting(false);
    }, 1000);
  };

  const onFormChange = (newFormData) => {
    setFormData(newFormData);
  }

  return (
    
    <div className="flex flex-col bg-paper rounded-md">
      {/* ================= HEADER ================= */}
      <header className="bg-paper border-b border-sand">
        <div className="px-6 py-4 rounded-md text-center">
          <h1 className="text-3xl font-bold text-ink">Customer Churn Prediction</h1>
          <p className="text-steel">Predict whether a customer is likely to churn</p>
        </div>
      </header>

      <div className="px-6 py-6">
        <Section className="rounded-md">
          <h2 className="text-lg font-semibold mb-2 text-ink text-center">Project & Model Overview</h2>
          <p className="text-steel text-center">Add your project and model description here.</p>
        </Section>
      </div>

      {/* ================= MAIN CONTENT ================= */}
      <main className="flex-1 px-6 pb-6 w-full">
        {/* Grid Layout */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 rounded-md">
          {/* LEFT: Input Form */}
          <div className="md:col-span-1 rounded-md">
            <Section className="h-full">
              <h2 className="text-lg font-semibold mb-4 text-ink text-center">Customer Details</h2>
              <ChurnForm onChange={onFormChange}
                onSubmit={handlePredict}
                isPredicting={isPredicting}
              />
            </Section>
          </div>

          {/* RIGHT: Prediction (TOP) + Charts (BOTTOM) */}
          <div className="md:col-span-2 grid grid-rows-1 md:grid-rows-2 gap-6 rounded-md">
            {/* Prediction Result - TOP RIGHT */}
            <Section>
              <h2 className="text-lg font-semibold mb-4 text-ink text-center">Prediction Result</h2>
              <PredictionCard 
                probability={currentPrediction ? currentPrediction.probability : null}
                isChurn={currentPrediction ? currentPrediction.isChurn : null}
                isLoading={isPredicting}
              />
            </Section>

            {/* Charts & Insights - BOTTOM RIGHT */}
            <Section>
              <h2 className="text-lg font-semibold mb-4 text-ink text-center">Charts & Insights</h2>
              <Charts predictions={predictions} />
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

