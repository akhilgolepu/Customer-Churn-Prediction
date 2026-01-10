import { useState } from "react";
import type { FormState } from "../types/formState";
import Toggle from "./ui/Toggle";

interface ChurnFormProps {
  onChange?: (data: FormState) => void;
  onSubmit: (data: FormState) => void;
  isPredicting: boolean;
}

export default function ChurnForm({ onSubmit, isPredicting, onChange }: ChurnFormProps) {
  const [form, setForm] = useState<FormState>({
    MonthlyCharges: 70,
    tenure: 12,
    TotalCharges: 840,
    SeniorCitizen: 0,
    
    Partner: "No",
    Dependents: "No",

    PhoneService: "No",
    MultipleLines: "No",

    InternetService: "Fiber optic",
    OnlineSecurity: "No",
    OnlineBackup: "Yes",
    DeviceProtection: "No",
    TechSupport: "No",

    StreamingTV: "Yes",
    StreamingMovies: "Yes",
    
    Contract: "Month-to-month",
    PaperlessBilling: "Yes",
    PaymentMethod: "Electronic check",
  });

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(form);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">

      {/* Billing & Tenure */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-ink uppercase tracking-wide">Billing & Tenure</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">

          {/* Monthly Charges */}
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
            disabled={isPredicting}
            value={form.MonthlyCharges}
            onChange={(e) => update("MonthlyCharges", Number(e.target.value))}
            placeholder="Monthly Charges"
            className="mt-1 w-full rounded-lg border border-sand px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel disabled:opacity-50 disabled:cursor-not-allowed"
          />

          {/* Tenure */}
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
            disabled={isPredicting}
            value={form.tenure}
            onChange={(e) => update("tenure", Number(e.target.value))}
            className="mt-1 w-full rounded-lg border border-sand px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel disabled:opacity-50 disabled:cursor-not-allowed"
            placeholder="Tenure (months)"
          />
          
          {/* Total Charges */}
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
            disabled={isPredicting}
            value={form.TotalCharges}
            onChange={(e) => update("TotalCharges", Number(e.target.value))}
            placeholder="Total Charges"
            className="mt-1 w-full rounded-lg border border-sand px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel disabled:opacity-50 disabled:cursor-not-allowed"
          />
        </div>
      </div>


      {/* Customer Info */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-ink uppercase tracking-wide my-4">Customer Info</h3>

        {/* Contracts */}
        <label className="block text-sm font-medium text-ink">Senior Citizen</label>
        <select
          value={form.SeniorCitizen}
          disabled={isPredicting}
          onChange={(e) => update("SeniorCitizen", Number(e.target.value))}
          className="mt-1 w-full rounded-lg border border-sand px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <option value={0}>No</option>
          <option value={1}>Yes</option>
        </select>

        {/* Partner */}
        <label className="block text-sm font-medium text-ink">Partner</label>
        <select
          value={form.Partner}
          onChange={(e) => update("Partner", e.target.value)}
          className="mt-1 w-full rounded-lg border border-sand px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <option>Yes</option>
          <option>No</option>
        </select>
        
        {/* Dependents */}
        <label className="block text-sm font-medium text-ink">Dependents</label>
        <select
          value={form.Dependents}
          onChange={(e) => update("Dependents", e.target.value)}
          className="mt-1 w-full rounded-lg border border-sand px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <option>Yes</option>
          <option>No</option>
        </select>
      </div>

      {/* Connectivity & Add-ons */}
      <div className="space-y-6">
        <h3 className="text-sm font-semibold text-ink uppercase tracking-wide my-4">Connectivity</h3>
        
        <div className="grid grid-cols-1 gap-6">
          
          {/* Phone Service */}
          <div>
            <label className="block text-sm font-medium text-ink mb-2">Phone Service</label>
            <div className="flex gap-2">
              {["Yes", "No"].map((option) => (
                <button
                  key={option}
                  type="button"
                  disabled={isPredicting}
                  onClick={() => {
                    update("PhoneService", option);
                    if (option === "No") update("MultipleLines", "No phone service");
                    else if (form.MultipleLines === "No phone service") update("MultipleLines", "No");
                  }}
                  className={`flex-1 py-2 px-4 rounded-lg border text-sm font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed
                    ${form.PhoneService === option 
                      ? "bg-steel text-paper border-steel" 
                      : "bg-paper text-steel border-sand hover:border-steel"
                    }`}
                >
                  {option}
                </button>
              ))}
            </div>
            
            {/* Multiple Lines (Conditional) */}
            {form.PhoneService === "Yes" && (
              <div className="mt-3">
                <Toggle 
                  label="Multiple Lines" 
                  disabled={isPredicting}
                  checked={form.MultipleLines === "Yes"} 
                  onChange={(checked) => update("MultipleLines", checked ? "Yes" : "No")} 
                />
              </div>
            )}
          </div>

          {/* Internet Service */}
          <div>
            <label className="block text-sm font-medium text-ink mb-2">Internet Service</label>
            <div className="grid grid-cols-3 gap-2">
              {["No", "DSL", "Fiber optic"].map((option) => (
                <button
                  key={option}
                  type="button"
                  disabled={isPredicting}
                  onClick={() => {
                    update("InternetService", option);
                    if (option === "No") {
                        ["OnlineSecurity", "OnlineBackup", "DeviceProtection", "TechSupport", "StreamingTV", "StreamingMovies"].forEach(key => {
                            update(key as keyof FormState, "No internet service");
                        });
                    } else {
                        ["OnlineSecurity", "OnlineBackup", "DeviceProtection", "TechSupport", "StreamingTV", "StreamingMovies"].forEach(key => {
                            if (form[key as keyof FormState] === "No internet service") {
                                update(key as keyof FormState, "No");
                            }
                        });
                    }
                  }}
                  className={`py-2 px-2 rounded-lg border text-sm font-medium transition-all text-center disabled:opacity-50 disabled:cursor-not-allowed
                    ${form.InternetService === option 
                      ? "bg-steel text-paper border-steel" 
                      : "bg-paper text-steel border-sand hover:border-steel"
                    }`}
                >
                  {option === "Fiber optic" ? "Fiber" : option}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Internet Add-ons (Conditional) */}
        {form.InternetService !== "No" && (
          <div className="animate-fade-in">
            <h3 className="text-sm font-semibold text-ink uppercase tracking-wide my-4">Internet Add-ons</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {[
                  { key: "OnlineSecurity", label: "Online Security" },
                  { key: "OnlineBackup", label: "Online Backup" },
                  { key: "DeviceProtection", label: "Device Protection" },
                  { key: "TechSupport", label: "Tech Support" },
                  { key: "StreamingTV", label: "Streaming TV" },
                  { key: "StreamingMovies", label: "Streaming Movies" },
                ].map(({ key, label }) => (
                  <Toggle
                    key={key}
                    label={label}
                    disabled={isPredicting}
                    checked={form[key as keyof FormState] === "Yes"}
                    onChange={(checked) => update(key as keyof FormState, checked ? "Yes" : "No")}
                  />
                ))}
            </div>
          </div>
        )}
      </div>

      {/* Contract & Payment */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-ink uppercase tracking-wide my-4">Contract & Payment</h3>

        <label className="block text-sm font-medium text-ink">Contract</label>
        <select
          value={form.Contract}
          disabled={isPredicting}
          onChange={(e) => update("Contract", e.target.value)}
          className="mt-1 w-full rounded-lg border border-sand px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <option>Month-to-month</option>
          <option>One year</option>
          <option>Two year</option>
        </select>

        <label className="block text-sm font-medium text-ink">Paperless Billing</label>
        <select
          value={form.PaperlessBilling}
          disabled={isPredicting}
          onChange={(e) => update("PaperlessBilling", e.target.value)}
          className="mt-1 w-full rounded-lg border border-sand px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <option>Yes</option>
          <option>No</option>
        </select>

        <label className="block text-sm font-medium text-ink">Payment Method</label>
        <select
          value={form.PaymentMethod}
          disabled={isPredicting}
          onChange={(e) => update("PaymentMethod", e.target.value)}
          className="mt-1 w-full rounded-lg border border-sand px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <option>Electronic check</option>
          <option>Mailed check</option>
          <option>Bank transfer (automatic)</option>
          <option>Credit card (automatic)</option>
        </select>
      </div>

      <button
        type="submit"
        className={`mt-2 inline-flex items-center rounded-lg bg-steel px-4 py-2 text-paper hover:bg-ink transition-all duration-300 ease-out
          ${
            isPredicting
            ? "bg-sand cursor-not-allowed"
            : "bg-steel hover:bg-ink"
          }`}
      >
        {isPredicting ? "Predicting, Please wait" : "Predict Churn"}
      </button>
    </form>
  );
}
