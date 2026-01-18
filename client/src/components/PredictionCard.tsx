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
        <div className="rounded-xl border border-sand p-4 transition transform hover:-translate-y-0.5 hover:shadow-md">
          <p className="text-sm text-steel">Churn Probability</p>
          <p className="mt-1 text-2xl font-bold text-ink">
            {probability !== null 
              ? `${(probability * 100).toFixed(1)}%` 
              : "—"}
          </p>
        </div>

        {/* Prediction Result Card */}
        <div 
          className={`rounded-xl border p-4 transition transform hover:-translate-y-0.5 hover:shadow-md
              ${
                isChurn === null
                  ? "border-sand bg-paper"
                  : isChurn
                  ? "bg-red-200 border-red-200 text-red-900"
                  : "bg-green-200 border-green-200 text-green-900"
              }`}
          >
          
          <p className="text-sm text-steel">Status</p>

          {/* Loading State */}
          {isLoading && (
            <p className="mt-1 text-2xl font-bold text-ink">Prediction in process...</p>
          )}

          {/* Idle / Result State */}
          {!isLoading && (
            <>
              <p className="mt-1 text-2xl font-bold text-ink">
                {isChurn === null
                  ? "No prediction yet"
                  : isChurn
                  ? "Likely to Churn"
                  : "Unlikely to Churn"}
              </p>

              {isChurn === null && (
                <p className="mt-2 text-sm text-taupe">
                  Fill the form and click <strong>"Predict"</strong> to see the result.
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
