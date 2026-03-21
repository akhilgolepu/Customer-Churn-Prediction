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

interface SectionState {
  billing: boolean;
  customer: boolean;
  connectivity: boolean;
  contract: boolean;
}

const DEFAULT_FORM: FormState = {
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
};

function ChipGroup<T extends string | number>({
  label,
  value,
  options,
  onChange,
  disabled,
}: {
  label: string;
  value: T;
  options: readonly T[];
  onChange: (value: T) => void;
  disabled: boolean;
}) {
  return (
    <div>
      <p className="mb-2 text-sm font-medium text-ink">{label}</p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {options.map((option) => (
          <button
            key={String(option)}
            type="button"
            disabled={disabled}
            onClick={() => onChange(option)}
            className={`rounded-xl border px-3 py-2 text-sm font-semibold transition disabled:opacity-45 ${
              value === option
                ? "border-accent bg-accent text-white"
                : "border-border bg-surface text-muted hover:border-accent/40"
            }`}
          >
            {String(option)}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function ChurnForm({ onSubmit, onSimulate, isPredicting, isSimulating, canSimulate }: ChurnFormProps) {
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [showAdvancedBilling, setShowAdvancedBilling] = useState(false);
  const [open, setOpen] = useState<SectionState>({
    billing: true,
    customer: true,
    connectivity: true,
    contract: true,
  });
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({});

  const disabled = isPredicting || isSimulating;

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setErrors((prev) => ({ ...prev, [key]: undefined }));
  };

  const validate = () => {
    const nextErrors: Partial<Record<keyof FormState, string>> = {};

    if (form.MonthlyCharges < 0) nextErrors.MonthlyCharges = "Monthly charges cannot be negative.";
    if (form.tenure < 0) nextErrors.tenure = "Tenure cannot be negative.";
    if (showAdvancedBilling && form.TotalCharges < 0) nextErrors.TotalCharges = "Total charges cannot be negative.";

    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;
    onSubmit(form);
  };

  const handleSimulate = () => {
    if (!validate()) return;
    onSimulate(form);
  };

  const handleReset = () => {
    setForm(DEFAULT_FORM);
    setShowAdvancedBilling(false);
    setErrors({});
  };

  const internetDisabled = useMemo(() => form.InternetService === "No", [form.InternetService]);

  const completion = {
    billing: [form.MonthlyCharges >= 0, form.tenure >= 0, !showAdvancedBilling || form.TotalCharges >= 0].filter(Boolean)
      .length,
    customer: [true, !!form.Partner, !!form.Dependents].filter(Boolean).length,
    connectivity: [!!form.PhoneService, !!form.InternetService, !internetDisabled || !!form.TechSupport].filter(Boolean)
      .length,
    contract: [!!form.Contract, !!form.PaymentMethod, !!form.PaperlessBilling].filter(Boolean).length,
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4 pb-20 md:pb-0">
      <div className="rounded-2xl border border-border bg-surface p-4">
        <button
          type="button"
          onClick={() => setOpen((prev) => ({ ...prev, billing: !prev.billing }))}
          className="flex w-full items-center justify-between"
        >
          <h3 className="text-sm font-semibold uppercase tracking-[0.12em] text-ink">Billing & Tenure</h3>
          <span className="rounded-full bg-accent-soft px-2 py-1 text-xs font-semibold text-accent">{completion.billing}/3</span>
        </button>

        {open.billing && (
          <div className="mt-4 grid gap-4 sm:grid-cols-2 fade-stagger">
            <div>
              <label htmlFor="monthly-charges" className="text-sm font-medium text-ink">Monthly Charges</label>
              <input
                id="monthly-charges"
                type="number"
                min={0}
                disabled={disabled}
                value={form.MonthlyCharges}
                onChange={(e) => set("MonthlyCharges", Number(e.target.value))}
                className="mt-1 w-full rounded-xl border border-border bg-base px-3 py-2 text-ink focus:border-accent focus:outline-none"
              />
              <p className="mt-1 text-xs text-muted">Typical range for churn-prone customers is often 60+.</p>
              {errors.MonthlyCharges && <p className="text-xs text-danger">{errors.MonthlyCharges}</p>}
            </div>

            <div>
              <label htmlFor="tenure" className="text-sm font-medium text-ink">Tenure (months)</label>
              <input
                id="tenure"
                type="number"
                min={0}
                disabled={disabled}
                value={form.tenure}
                onChange={(e) => set("tenure", Number(e.target.value))}
                className="mt-1 w-full rounded-xl border border-border bg-base px-3 py-2 text-ink focus:border-accent focus:outline-none"
              />
              <p className="mt-1 text-xs text-muted">Lower tenure generally correlates with higher churn risk.</p>
              {errors.tenure && <p className="text-xs text-danger">{errors.tenure}</p>}
            </div>

            <div className="sm:col-span-2 rounded-xl border border-border bg-base/70 p-3">
              <button
                type="button"
                disabled={disabled}
                onClick={() => setShowAdvancedBilling((prev) => !prev)}
                className="text-sm font-semibold text-accent"
              >
                {showAdvancedBilling ? "Hide advanced billing details" : "Show advanced billing details"}
              </button>

              {showAdvancedBilling && (
                <div className="mt-3 fade-stagger">
                  <label htmlFor="total-charges" className="text-sm font-medium text-ink">Total Charges</label>
                  <input
                    id="total-charges"
                    type="number"
                    min={0}
                    disabled={disabled}
                    value={form.TotalCharges}
                    onChange={(e) => set("TotalCharges", Number(e.target.value))}
                    className="mt-1 w-full rounded-xl border border-border bg-surface px-3 py-2 text-ink focus:border-accent focus:outline-none"
                  />
                  <p className="mt-1 text-xs text-muted">Use this when you want more precise long-term customer context.</p>
                  {errors.TotalCharges && <p className="text-xs text-danger">{errors.TotalCharges}</p>}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="rounded-2xl border border-border bg-surface p-4">
        <button
          type="button"
          onClick={() => setOpen((prev) => ({ ...prev, customer: !prev.customer }))}
          className="flex w-full items-center justify-between"
        >
          <h3 className="text-sm font-semibold uppercase tracking-[0.12em] text-ink">Customer Profile</h3>
          <span className="rounded-full bg-accent-soft px-2 py-1 text-xs font-semibold text-accent">{completion.customer}/3</span>
        </button>

        {open.customer && (
          <div className="mt-4 grid gap-4 fade-stagger">
            <ChipGroup
              label="Senior Citizen"
              value={form.SeniorCitizen}
              options={[0, 1] as const}
              onChange={(value) => set("SeniorCitizen", value as 0 | 1)}
              disabled={disabled}
            />
            <ChipGroup
              label="Partner"
              value={form.Partner}
              options={["Yes", "No"] as const}
              onChange={(value) => set("Partner", value as "Yes" | "No")}
              disabled={disabled}
            />
            <ChipGroup
              label="Dependents"
              value={form.Dependents}
              options={["Yes", "No"] as const}
              onChange={(value) => set("Dependents", value as "Yes" | "No")}
              disabled={disabled}
            />
          </div>
        )}
      </div>

      <div className="rounded-2xl border border-border bg-surface p-4">
        <button
          type="button"
          onClick={() => setOpen((prev) => ({ ...prev, connectivity: !prev.connectivity }))}
          className="flex w-full items-center justify-between"
        >
          <h3 className="text-sm font-semibold uppercase tracking-[0.12em] text-ink">Connectivity</h3>
          <span className="rounded-full bg-accent-soft px-2 py-1 text-xs font-semibold text-accent">{completion.connectivity}/3</span>
        </button>

        {open.connectivity && (
          <div className="mt-4 space-y-4 fade-stagger">
            <ChipGroup
              label="Phone Service"
              value={form.PhoneService}
              options={["Yes", "No"] as const}
              onChange={(option) => {
                set("PhoneService", option as "Yes" | "No");
                if (option === "No") set("MultipleLines", "No phone service");
                if (option === "Yes" && form.MultipleLines === "No phone service") set("MultipleLines", "No");
              }}
              disabled={disabled}
            />

            {form.PhoneService === "Yes" && (
              <Toggle
                label="Multiple Lines"
                disabled={disabled}
                checked={form.MultipleLines === "Yes"}
                onChange={(checked) => set("MultipleLines", checked ? "Yes" : "No")}
              />
            )}

            <ChipGroup
              label="Internet Service"
              value={form.InternetService}
              options={["No", "DSL", "Fiber optic"] as const}
              onChange={(option) => {
                set("InternetService", option as FormState["InternetService"]);
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
              disabled={disabled}
            />

            <div className={`${internetDisabled ? "opacity-45" : "opacity-100"} transition`}>
              <p className="mb-2 text-sm font-medium text-ink">Internet Add-ons</p>
              <div className="grid gap-2 sm:grid-cols-2">
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
                <p className="mt-2 text-xs text-muted">Select DSL or Fiber to configure add-on behavior.</p>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="rounded-2xl border border-border bg-surface p-4">
        <button
          type="button"
          onClick={() => setOpen((prev) => ({ ...prev, contract: !prev.contract }))}
          className="flex w-full items-center justify-between"
        >
          <h3 className="text-sm font-semibold uppercase tracking-[0.12em] text-ink">Contract & Payment</h3>
          <span className="rounded-full bg-accent-soft px-2 py-1 text-xs font-semibold text-accent">{completion.contract}/3</span>
        </button>

        {open.contract && (
          <div className="mt-4 space-y-4 fade-stagger">
            <ChipGroup
              label="Contract"
              value={form.Contract}
              options={["Month-to-month", "One year", "Two year"] as const}
              onChange={(value) => set("Contract", value as FormState["Contract"])}
              disabled={disabled}
            />

            <ChipGroup
              label="Paperless Billing"
              value={form.PaperlessBilling}
              options={["Yes", "No"] as const}
              onChange={(value) => set("PaperlessBilling", value as "Yes" | "No")}
              disabled={disabled}
            />

            <div>
              <p className="mb-2 text-sm font-medium text-ink">Payment Method</p>
              <select
                value={form.PaymentMethod}
                disabled={disabled}
                onChange={(e) => set("PaymentMethod", e.target.value as FormState["PaymentMethod"])}
                className="w-full rounded-xl border border-border bg-base px-3 py-2 text-sm text-ink focus:border-accent focus:outline-none"
              >
                <option>Electronic check</option>
                <option>Mailed check</option>
                <option>Bank transfer (automatic)</option>
                <option>Credit card (automatic)</option>
              </select>
              <p className="mt-1 text-xs text-muted">Electronic check often appears as a high-risk churn pattern.</p>
            </div>
          </div>
        )}
      </div>

      <div className="hidden grid-cols-3 gap-3 md:grid">
        <button
          type="submit"
          disabled={disabled}
          className="inline-flex items-center justify-center rounded-xl bg-accent px-4 py-3 font-semibold text-white transition hover:bg-accent/90 disabled:bg-border"
        >
          {isPredicting ? "Predicting..." : "Predict Churn"}
        </button>

        <button
          type="button"
          disabled={!canSimulate || isSimulating}
          onClick={handleSimulate}
          className="inline-flex items-center justify-center rounded-xl border border-border bg-surface px-4 py-3 font-semibold text-ink transition hover:border-accent disabled:opacity-50"
        >
          {isSimulating ? "Simulating..." : "What-if Simulate"}
        </button>

        <button
          type="button"
          disabled={disabled}
          onClick={handleReset}
          className="inline-flex items-center justify-center rounded-xl border border-border bg-surface px-4 py-3 font-semibold text-muted transition hover:border-accent hover:text-ink disabled:opacity-50"
        >
          Reset
        </button>
      </div>

      <div className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-surface/95 p-3 backdrop-blur md:hidden">
        <div className="mx-auto flex max-w-5xl gap-2">
          <button
            type="submit"
            disabled={disabled}
            className="flex-1 rounded-xl bg-accent px-3 py-3 text-sm font-semibold text-white disabled:bg-border"
          >
            {isPredicting ? "Predicting..." : "Predict"}
          </button>
          <button
            type="button"
            disabled={!canSimulate || isSimulating}
            onClick={handleSimulate}
            className="flex-1 rounded-xl border border-border bg-surface px-3 py-3 text-sm font-semibold text-ink disabled:opacity-50"
          >
            {isSimulating ? "Sim..." : "Simulate"}
          </button>
        </div>
      </div>
    </form>
  );
}
