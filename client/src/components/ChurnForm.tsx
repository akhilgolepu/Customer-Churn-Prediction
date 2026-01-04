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

export default function ChurnForm({ isPredicting, onSubmit, onChange }: ChurnFormProps) {
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
    setForm((prev) => { 
      const updated = { ...prev, [key]: value };
      onChange(updated);
      return updated;
    });
  };

  const isValid  = 
    form.MonthlyCharges >= 0 &&
    form.tenure >= 0 &&
    form.TotalCharges >= 0;
    Boolean(form.Contract) &&
    Boolean(form.InternetService) &&
    Boolean(form.PaymentMethod);

  return (
    <form onSubmit={(e) => {
      e.preventDefault();
      onSubmit(form);
    }}>

      {/* Billing & Tenure */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-ink uppercase tracking-wide">Billing & Tenure</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">

          {/* Monthly Charges */}
        </div>
        <label className="block text-sm font-medium text-ink">
          Montly Charges
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
        
        {/* Total Charges */}
        <div>
        <label className="block text-sm font-medium text-ink">
          Total Charges
          <span
              title="Total billing amount for the customer"
              className="ml-1 cursor-help text-steel"
            >
              ⓘ
          </span>
        </label>
        <input
          type="number"
          value={form.TotalCharges}
          onChange={(e) => update("TotalCharges", Number(e.target.value))}
          className="mt-1 w-full rounded-lg border border-sand px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel"
          min={0}
          step={0.01}
        />
        </div>
        
        {/* Tenure */}
        <div>
        <label className="block text-sm font-medium text-ink">
          Tenure (months)
          <span
              title="Total billing amount for the customer"
              className="ml-1 cursor-help text-steel"
            >
              ⓘ
          </span>
        </label>
        <input
          type="number"
          value={form.tenure}
          onChange={(e) => update("tenure", Number(e.target.value))}
          className="mt-1 w-full rounded-lg border border-sand px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel"
          min={0}
          step={0.01}
        />
        </div>
      </div>


      {/* Contract & Payment */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-ink uppercase tracking-wide my-4">Contract & Payment</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">

          {/* Contracts */}
          <div>
            <label className="block text-sm font-medium text-ink">Contract</label>
            <select
              value={form.Contract}
              onChange={(e) => update("Contract", e.target.value)}
              className="mt-1 w-full rounded-lg border border-sand px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel"
            >
              <option value="">Select Contract</option>
              <option value="Month-to-month">Month-to-month</option>
              <option value="One year">One year</option>
              <option value="Two year">Two year</option>
            </select>
          </div>

          {/* Payment Method */}
          <div className="rounded-md">
            <label className="block text-sm font-medium text-ink">Payment Method</label>
            <select
              value={form.PaymentMethod}
              onChange={(e) => update("PaymentMethod", e.target.value)}
              className="mt-1 w-full rounded-lg border border-sand px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel"
            >
              <option value="">Select Payment Method</option>
              <option value="Electronic check">Electronic check</option>
              <option value="Mailed check">Mailed check</option>
              <option value="Bank transfer (automatic)">Bank transfer (automatic)</option>
              <option value="Credit card (automatic)">Credit card (automatic)</option>
            </select>
          </div>
        </div>
      </div>
    
      {/* Services Subscribed */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-ink uppercase tracking-wide my-4">Services Subscribed</h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Internet Service */}
          <div>
            <label className="block text-sm font-medium text-ink">Internet Service</label>
            <select
              value={form.InternetService}
              onChange={(e) => update("InternetService", e.target.value)}
              className="mt-1 w-full rounded-lg border border-sand px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel"
            >
              <option value="">Select Internet Service</option>
              <option value="DSL">DSL</option>
              <option value="Fiber optic">Fiber optic</option>
              <option value="No">No</option>
            </select>
          </div>
        </div>
      </div>

      {/* Add-ons & Support */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-ink uppercase tracking-wide my-4">Add-ons & Support</h3>

        <p className="text-sm text-steel">No add-ons or support options available for input.</p>
      </div>
      

      {/* Customer Profile */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-ink uppercase tracking-wide my-4">Customer Profile</h3>

        <div className="flex items-center gap-2">
          <input
            id="SeniorCitizen"
            type="checkbox"
            checked={form.SeniorCitizen}
            onChange={(e) => update("SeniorCitizen", e.target.checked)}
            className="h-4 w-4"
          />
        </div>
        <label htmlFor="SeniorCitizen" className="text-sm text-steel">Senior Citizen</label>
      </div>

      <button
        type="submit"
        disabled={!isValid}
        className={`mt-2 inline-flex items-center rounded-lg bg-steel px-4 py-2 text-paper hover:bg-ink
          ${
            isPredicting
            ? "bg-sand cursor-not-allowed"
            : "bg-steel hover:bg-int"
          }`}
      >
        {isPredicting ? "Predicting, Please wait" : "Predict Churn"}
      </button>
    </form>
  );
}
