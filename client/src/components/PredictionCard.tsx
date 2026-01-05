interface PredictionCardProps {
  probability: number | null;
  isChurn: boolean | null;
  isLoading: boolean;
}

export default function PredictionCard({
  probability,
  isChurn,
  isLoading,
}: PredictionCardProps) {
  return (
    <div className="rounded-md">
      <div className="grid grid-cols-2 gap-4 rounded-md">
        <div className="rounded-xl border border-sand p-4">
          <p className="text-sm text-steel">Churn Probability</p>
          <p className="mt-1 text-2xl font-bold text-ink">
            {probability !== null 
              ? `${(probability * 100).toFixed(1)}%` 
              : "—"}
          </p>
        </div>

        {/* Prediction Result Card */}
        <div 
          className={`rounded-xl border p-4 transition
              ${
                isChurn === null
                  ? "border-sand bg-paper"
                  : isChurn
                  ? "bg-red-300 border-red-50"
                  : "bg-green-300 border-green-50"
              }`}
          >
          
          <p className="text-sm text-steel">Status</p>

          {isLoading && (
            <p className="mt-4 text-ink">Predicting, Please wait...</p>
          )}
          
          <p className="mt-1 text-2xl font-bold text-ink">
            {isChurn === null
              ? "No prediction yet"
              : isChurn
              ? "Likely to Churn"
              : "Unlikely to Churn"
            }
          </p>
          
          {/* Helper text(only when null) */}
          {isChurn === null && (
            <p className="mt-4 text-sm text-taupe">
              Fill the form and click <strong>Predict Churn</strong> to see results.  
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
