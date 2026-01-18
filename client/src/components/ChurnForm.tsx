import { useMemo, useState } from "react";
import type { FormState } from "../types/formState";
import Toggle from "./ui/Toggle";

interface ChurnFormProps {
  onSubmit: (data: FormState) => void;
  onSimulate: (data: FormState) => void;
  isPredicting: boolean;
  isSimulating: boolean;
  canSimulate: boolean;
}

export default function ChurnForm({
  onSubmit,
  onSimulate,
  isPredicting,
  isSimulating,
  canSimulate,
}: ChurnFormProps) {
  const [form, setForm] = useState<FormState>({
    MonthlyCharges: 70,
    tenure: 12,
    TotalCharges: 840,
    SeniorCitizen: 0,

    Partner: "No",
    Dependents: "No",

    PhoneService: "Yes",
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

  const disabled = isPredicting || isSimulating;

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(form);
  };

  const internetDisabled = useMemo(() => form.InternetService === "No", [form.InternetService]);

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* ================= NUMERIC INPUTS ================= */}
      <div className="rounded-xl border border-sand p-4">
        <h3 className="text-xs font-semibold text-ink uppercase tracking-wide mb-3">
          Billing & Tenure
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Monthly Charges */}
          <div>
            <label className="block text-sm font-medium text-ink">
              Monthly Charges{" "}
              <span title="Average monthly billing amount" className="ml-1 cursor-help text-steel">
                ⓘ
              </span>
            </label>
            <input
              type="number"
              disabled={disabled}
              value={form.MonthlyCharges}
              onChange={(e) => set("MonthlyCharges", Number(e.target.value))}
              className="mt-1 w-full rounded-lg border border-sand px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel disabled:opacity-50 disabled:cursor-not-allowed"
            />
          </div>

          {/* Tenure */}
          <div>
            <label className="block text-sm font-medium text-ink">
              Tenure (months){" "}
              <span title="How long the customer has stayed" className="ml-1 cursor-help text-steel">
                ⓘ
              </span>
            </label>
            <input
              type="number"
              disabled={disabled}
              value={form.tenure}
              onChange={(e) => set("tenure", Number(e.target.value))}
              className="mt-1 w-full rounded-lg border border-sand px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel disabled:opacity-50 disabled:cursor-not-allowed"
            />
          </div>

          {/* Total Charges */}
          <div className="sm:col-span-2">
            <label className="block text-sm font-medium text-ink">
              Total Charges{" "}
              <span title="Total billed amount so far" className="ml-1 cursor-help text-steel">
                ⓘ
              </span>
            </label>
            <input
              type="number"
              disabled={disabled}
              value={form.TotalCharges}
              onChange={(e) => set("TotalCharges", Number(e.target.value))}
              className="mt-1 w-full rounded-lg border border-sand px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel disabled:opacity-50 disabled:cursor-not-allowed"
            />
          </div>
        </div>
      </div>

      {/* ================= CUSTOMER INFO ================= */}
      <div className="rounded-xl border border-sand p-4">
        <h3 className="text-xs font-semibold text-ink uppercase tracking-wide mb-3">
          Customer Info
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Senior Citizen */}
          <div>
            <label className="block text-sm font-medium text-ink">Senior Citizen</label>
            <select
              value={form.SeniorCitizen}
              disabled={disabled}
              onChange={(e) => set("SeniorCitizen", Number(e.target.value))}
              className="mt-1 w-full rounded-lg border border-sand px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <option value={0}>No</option>
              <option value={1}>Yes</option>
            </select>
          </div>

          {/* Partner */}
          <div>
            <label className="block text-sm font-medium text-ink">Partner</label>
            <select
              value={form.Partner}
              disabled={disabled}
              onChange={(e) => set("Partner", e.target.value)}
              className="mt-1 w-full rounded-lg border border-sand px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <option>No</option>
              <option>Yes</option>
            </select>
          </div>

          {/* Dependents */}
          <div className="sm:col-span-2">
            <label className="block text-sm font-medium text-ink">Dependents</label>
            <select
              value={form.Dependents}
              disabled={disabled}
              onChange={(e) => set("Dependents", e.target.value)}
              className="mt-1 w-full rounded-lg border border-sand px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <option>No</option>
              <option>Yes</option>
            </select>
          </div>
        </div>
      </div>

      {/* ================= CONNECTIVITY ================= */}
      <div className="rounded-xl border border-sand p-4">
        <h3 className="text-xs font-semibold text-ink uppercase tracking-wide mb-3">
          Connectivity
        </h3>

        <div className="grid grid-cols-1 gap-5">
          {/* Phone Service */}
          <div>
            <label className="block text-sm font-medium text-ink mb-2">Phone Service</label>

            <div className="flex gap-2">
              {["Yes", "No"].map((option) => (
                <button
                  key={option}
                  type="button"
                  disabled={disabled}
                  onClick={() => {
                    set("PhoneService", option);
                    if (option === "No") set("MultipleLines", "No phone service");
                    else if (form.MultipleLines === "No phone service") set("MultipleLines", "No");
                  }}
                  className={`flex-1 py-2 px-4 rounded-lg border text-sm font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed
                    ${
                      form.PhoneService === option
                        ? "bg-steel text-paper border-steel"
                        : "bg-paper text-steel border-sand hover:border-steel"
                    }`}
                >
                  {option}
                </button>
              ))}
            </div>

            {form.PhoneService === "Yes" && (
              <div className="mt-3">
                <Toggle
                  label="Multiple Lines"
                  disabled={disabled}
                  checked={form.MultipleLines === "Yes"}
                  onChange={(checked) => set("MultipleLines", checked ? "Yes" : "No")}
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
                  disabled={disabled}
                  onClick={() => {
                    set("InternetService", option);

                    const internetKeys: (keyof FormState)[] = [
                      "OnlineSecurity",
                      "OnlineBackup",
                      "DeviceProtection",
                      "TechSupport",
                      "StreamingTV",
                      "StreamingMovies",
                    ];

                    if (option === "No") {
                      internetKeys.forEach((k) => set(k, "No internet service"));
                    } else {
                      internetKeys.forEach((k) => {
                        if (form[k] === "No internet service") set(k, "No");
                      });
                    }
                  }}
                  className={`py-2 px-2 rounded-lg border text-sm font-medium transition-all text-center disabled:opacity-50 disabled:cursor-not-allowed
                    ${
                      form.InternetService === option
                        ? "bg-steel text-paper border-steel"
                        : "bg-paper text-steel border-sand hover:border-steel"
                    }`}
                >
                  {option === "Fiber optic" ? "Fiber" : option}
                </button>
              ))}
            </div>
          </div>

          {/* Internet Add-ons */}
          <div className={`${internetDisabled ? "opacity-40 pointer-events-none" : ""}`}>
            <h3 className="text-xs font-semibold text-ink uppercase tracking-wide mt-2 mb-3">
              Internet Add-ons
            </h3>

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
                  disabled={disabled || internetDisabled}
                  checked={form[key as keyof FormState] === "Yes"}
                  onChange={(checked) => set(key as keyof FormState, checked ? "Yes" : "No")}
                />
              ))}
            </div>

            {internetDisabled && (
              <p className="mt-2 text-xs text-taupe">
                Internet Add-ons are disabled because Internet Service is set to <strong>No</strong>.
              </p>
            )}
          </div>
        </div>
      </div>

      {/* ================= CONTRACT & PAYMENT ================= */}
      <div className="rounded-xl border border-sand p-4">
        <h3 className="text-xs font-semibold text-ink uppercase tracking-wide mb-3">
          Contract & Payment
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Contract */}
          <div>
            <label className="block text-sm font-medium text-ink">Contract</label>
            <select
              value={form.Contract}
              disabled={disabled}
              onChange={(e) => set("Contract", e.target.value)}
              className="mt-1 w-full rounded-lg border border-sand px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <option>Month-to-month</option>
              <option>One year</option>
              <option>Two year</option>
            </select>
          </div>

          {/* Paperless Billing */}
          <div>
            <label className="block text-sm font-medium text-ink">Paperless Billing</label>
            <select
              value={form.PaperlessBilling}
              disabled={disabled}
              onChange={(e) => set("PaperlessBilling", e.target.value)}
              className="mt-1 w-full rounded-lg border border-sand px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <option>Yes</option>
              <option>No</option>
            </select>
          </div>

          {/* Payment Method */}
          <div className="sm:col-span-2">
            <label className="block text-sm font-medium text-ink">Payment Method</label>
            <select
              value={form.PaymentMethod}
              disabled={disabled}
              onChange={(e) => set("PaymentMethod", e.target.value)}
              className="mt-1 w-full rounded-lg border border-sand px-3 py-2 focus:outline-none focus:ring-2 focus:ring-steel disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <option>Electronic check</option>
              <option>Mailed check</option>
              <option>Bank transfer (automatic)</option>
              <option>Credit card (automatic)</option>
            </select>
          </div>
        </div>
      </div>

      {/* ================= ACTION BUTTONS ================= */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <button
          type="submit"
          disabled={disabled}
          className={`inline-flex items-center justify-center rounded-lg px-4 py-2 text-paper transition-all duration-300 ease-out
            ${isPredicting ? "bg-sand cursor-not-allowed" : "bg-steel hover:bg-ink"}
          `}
        >
          {isPredicting ? "Predicting..." : "Predict Churn"}
        </button>

        <button
          type="button"
          disabled={!canSimulate || isSimulating}
          onClick={() => onSimulate(form)}
          className="inline-flex items-center justify-center rounded-lg border border-sand px-4 py-2 font-semibold text-ink hover:border-steel transition disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isSimulating ? "Simulating..." : "What-if Simulate"}
        </button>
      </div>
    </form>
  );
}