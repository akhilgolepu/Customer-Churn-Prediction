import { useState } from "react";

interface FormState {
  MonthlyCharges: number;
  tenure: number;
  TotalCharges: number;
  SeniorCitizen: boolean;
  Contract: string;
  InternetService: string;
  PaymentMethod: string;
}

interface ChurnFormProps {
  onChange: (data: FormState) => void;
  onSubmit: (data: FormState) => void;
  isPredicting: boolean;
}

export default function ChurnForm({ isPredicting }: ChurnFormProps) {
  const [form, setForm] = useState<FormState>({
    MonthlyCharges: 50,
    tenure: 12,
    TotalCharges: 600,
    SeniorCitizen: false,
    Contract: "Month-to-month",
    InternetService: "DSL",
    PaymentMethod: "Electronic check",
  });

  const update = (key: keyof FormState, value: any) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    console.log("Form submitted:", form);
    alert("Submitted! (Stub) \nCheck console for payload.");
  };

  const isValid  = 
    form.MonthlyCharges >= 0 &&
    form.tenure >= 0 &&
    form.TotalCharges >= 0;
    form.Contract &&
    form.InternetService &&
    form.PaymentMethod;

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      {/* Billing & Tenure */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 rounded-md">
        <div className="rounded-md">
          <label className="block text-sm font-medium text-ink">
            Monthly Charges
            <span
              title="Average monthly billing amount for the customer"
              className="ml-1 cursor-help text-steel"
            >
              ⓘ
            </span>
          </label>
          <input
            type="number"
            value={form.MonthlyCharges}
            onChange={(e) => update("MonthlyCharges", Number(e.target.value))}
            className="mt-1 w-full rounded-lg border border-sand px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel"
            min={0}
            step={0.01}
          />
        </div>
        <div className="rounded-md">
          <label className="block text-sm font-medium text-ink">Tenure (months)</label>
          <input
            type="number"
            value={form.tenure}
            onChange={(e) => update("tenure", Number(e.target.value))}
            className="mt-1 w-full rounded-lg border border-sand px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel"
            min={0}
          />
        </div>
        <div className="rounded-md">
          <label className="block text-sm font-medium text-ink">Total Charges</label>
          <input
            type="number"
            value={form.TotalCharges}
            onChange={(e) => update("TotalCharges", Number(e.target.value))}
            className="mt-1 w-full rounded-lg border border-sand px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel"
            min={0}
            step={0.01}
          />
        </div>
      </div>

      {/* Customer */}
      <div className="flex items-center gap-2 rounded-md">
        <input
          id="SeniorCitizen"
          type="checkbox"
          checked={form.SeniorCitizen}
          onChange={(e) => update("SeniorCitizen", e.target.checked)}
          className="h-4 w-4"
        />
        <label htmlFor="SeniorCitizen" className="text-sm text-steel">Senior Citizen</label>
      </div>

      {/* Service & Contract */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 rounded-md">
        <div className="rounded-md">
          <label className="block text-sm font-medium text-ink">Contract</label>
          <select
            value={form.Contract}
            onChange={(e) => update("Contract", e.target.value)}
            className="mt-1 w-full rounded-lg border border-sand px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel"
          >
            <option>Month-to-month</option>
            <option>One year</option>
            <option>Two year</option>
          </select>
        </div>
        <div className="rounded-md">
          <label className="block text-sm font-medium text-ink">Internet Service</label>
          <select
            value={form.InternetService}
            onChange={(e) => update("InternetService", e.target.value)}
            className="mt-1 w-full rounded-lg border border-sand px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel"
          >
            <option>DSL</option>
            <option>Fiber optic</option>
            <option>No</option>
          </select>
        </div>
        <div className="rounded-md">
          <label className="block text-sm font-medium text-ink">Payment Method</label>
          <select
            value={form.PaymentMethod}
            onChange={(e) => update("PaymentMethod", e.target.value)}
            className="mt-1 w-full rounded-lg border border-sand px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel"
          >
            <option>Electronic check</option>
            <option>Mailed check</option>
            <option>Bank transfer (automatic)</option>
            <option>Credit card (automatic)</option>
          </select>
        </div>
      </div>

      <button
        type="submit"
        disabled={!isValid}
        className={`mt-2 inline-flex items-center rounded-lg bg-steel px-4 py-2 text-paper hover:bg-ink
          ${
            isPredicting
              ? "bg-steel hover:bg-int"
              : "bg-sand cursor-not-allowed"
          }`}
      >
        {isPredicting ? "Predicting, Please wait" : "Predict Churn"}
      </button>
    </form>
  );
}
