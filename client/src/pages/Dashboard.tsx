import { useState } from "react";
import Section from "../components/ui/Section";
import ChurnForm from "../components/ChurnForm";
import PredictionCard from "../components/PredictionCard";
import Charts from "../components/Charts";

export default function Dashboard() {
  const [formData, setFormData] = useState<FormState | null>(null);
  
  const [predictions, setPredictions] = useState<Prediction[]>([]);

  const [isPredicting, setIsPredicting] = useState(false);

  const handlePredict = (newPrediction: Prediction) => {
    // Predicting starts
    setPredictions(prev => [...prev, newPrediction]);

    // API call
    setTimeout(() => {
      setPredictions(prev => [...prev, newPrediction]);
      //Predicting ends here
      setIsPredicting(false);
    }, 1000);
  };

  const onFormChange = (newFormData) => {
    setFormData(newFormData);
    setCurrentPrediction(null);
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

      <Section className="mx-6 my-4 p-4 rounded-md">
        <h2 className="text-lg font-semibold mb-2 text-ink text-center">Project & Model Overview</h2>
        <p className="text-steel text-center">Add your project and model description here.</p>
      </Section>

      {/* ================= MAIN CONTENT ================= */}
      <main className="flex-1 px-6 py-6 w-full">
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
              <PredictionCard />
            </Section>

            {/* Charts & Insights - BOTTOM RIGHT */}
            <Section>
              <h2 className="text-lg font-semibold mb-4 text-ink text-center">Charts & Insights</h2>
              <Charts />
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

