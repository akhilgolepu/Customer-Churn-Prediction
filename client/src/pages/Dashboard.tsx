import { useEffect, useMemo, useState } from "react";
import Section from "../components/ui/Section";
import ChurnForm from "../components/ChurnForm";
import PredictionCard from "../components/PredictionCard";
import Charts from "../components/Charts";
import KPI from "../components/ui/KPI";
import InfoTip from "../components/ui/InfoTip";
import type { Prediction } from "../types/prediction";
import { explainChurn, getRecommendations, predictChurn, submitFeedback, submitOutcome } from "../services/api";
import type { FormState } from "../types/formState";
import { useToast } from "../components/ui/ToastProvider";
import { trackEvent } from "../services/analytics";

type Role = "admin" | "analyst" | "viewer";

interface DashboardProps {
  role: Role;
  teamName: string;
}

interface Driver {
  feature: string;
  value: string | number;
  impact: number;
}

interface RecommendationResult {
  prediction_id: string;
  probability: number;
  risk_tier: string;
  actions: Array<{ key: string; label: string; rationale: string; expected_impact_score: number; confidence: number; estimated_cost: number; impact_per_budget: number }>;
  selected_actions: Array<{ key: string; label: string; rationale: string; expected_impact_score: number; confidence: number; estimated_cost: number; impact_per_budget: number }>;
  total_selected_cost: number;
  total_expected_impact: number;
}

interface Scenario {
  id: string;
  name: string;
  notes: string;
  comments: string[];
  form: FormState;
  prediction: Prediction;
  createdAt: number;
}

const DRIVER_GROUPS: Record<string, "Pricing" | "Contract" | "Support" | "Engagement" | "Billing" | "Profile"> = {
  MonthlyCharges: "Pricing",
  TotalCharges: "Pricing",
  Contract: "Contract",
  IsMonthToMonth: "Contract",
  TechSupport: "Support",
  TechIssueRisk: "Support",
  OnlineSecurity: "Support",
  PaymentRisk: "Billing",
  PaymentMethod: "Billing",
  tenure: "Engagement",
  EngagementScore: "Engagement",
  SeniorCitizen: "Profile",
  Partner: "Profile",
};

const FIELD_LABELS: Partial<Record<keyof FormState, string>> = {
  MonthlyCharges: "Monthly Charges",
  tenure: "Tenure",
  TotalCharges: "Total Charges",
  Contract: "Contract",
  PaymentMethod: "Payment Method",
  TechSupport: "Tech Support",
  OnlineSecurity: "Online Security",
  InternetService: "Internet Service",
};

function inferRiskBand(probability: number | null) {
  if (probability === null) return "No score";
  if (probability < 0.35) return "Low";
  if (probability < 0.65) return "Medium";
  return "High";
}

export default function Dashboard({ role, teamName }: DashboardProps) {
  const { pushToast } = useToast();
  const [currentPrediction, setCurrentPrediction] = useState<Prediction | null>(() => {
    try {
      const stored = localStorage.getItem("churn_current_prediction");
      return stored ? (JSON.parse(stored) as Prediction) : null;
    } catch {
      return null;
    }
  });
  const [predictions, setPredictions] = useState<Prediction[]>(() => {
    try {
      const stored = localStorage.getItem("churn_predictions");
      return stored ? (JSON.parse(stored) as Prediction[]) : [];
    } catch {
      return [];
    }
  });

  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [simDrivers, setSimDrivers] = useState<Driver[]>([]);

  const [baseForm, setBaseForm] = useState<FormState | null>(null);
  const [simForm, setSimForm] = useState<FormState | null>(null);
  const [basePrediction, setBasePrediction] = useState<Prediction | null>(null);
  const [simPrediction, setSimPrediction] = useState<Prediction | null>(null);

  const [isPredicting, setIsPredicting] = useState(false);
  const [isSimulating, setIsSimulating] = useState(false);
  const [isRecommending, setIsRecommending] = useState(false);
  const [showHowItWorks, setShowHowItWorks] = useState(false);
  const [formSeed, setFormSeed] = useState<FormState | null>(null);
  const [recommendationBudget, setRecommendationBudget] = useState(120);
  const [recommendationResult, setRecommendationResult] = useState<RecommendationResult | null>(null);
  const [feedbackComment, setFeedbackComment] = useState("");
  const [outcomeNotes, setOutcomeNotes] = useState("");

  const [scenarioName, setScenarioName] = useState("");
  const [scenarioNotes, setScenarioNotes] = useState("");
  const [newCommentByScenario, setNewCommentByScenario] = useState<Record<string, string>>({});
  const [selectedScenarioIds, setSelectedScenarioIds] = useState<string[]>([]);

  const scenariosStorageKey = `churn_team_scenarios_${teamName}`;
  const [scenarios, setScenarios] = useState<Scenario[]>(() => {
    try {
      const raw = localStorage.getItem(`churn_team_scenarios_${teamName}`);
      return raw ? (JSON.parse(raw) as Scenario[]) : [];
    } catch {
      return [];
    }
  });

  const isReadOnly = role === "viewer";

  useEffect(() => {
    localStorage.setItem("churn_predictions", JSON.stringify(predictions));
  }, [predictions]);

  useEffect(() => {
    if (currentPrediction) {
      localStorage.setItem("churn_current_prediction", JSON.stringify(currentPrediction));
    }
  }, [currentPrediction]);

  useEffect(() => {
    localStorage.setItem(scenariosStorageKey, JSON.stringify(scenarios));
  }, [scenarios, scenariosStorageKey]);

  const handlePredict = async (formData: FormState) => {
    if (isReadOnly) {
      pushToast({ title: "Read-only role", description: "Viewer cannot create new predictions.", variant: "info" });
      return;
    }

    try {
      setIsPredicting(true);
      trackEvent("predict_requested", { role, team: teamName });
      const [explainResponse, response] = await Promise.all([explainChurn(formData), predictChurn(formData)]);

      const prediction: Prediction = {
        predictionId: response.predictionId,
        probability: response.probability,
        isChurn: response.isChurn,
        shadowProbability: response.shadowProbability,
        timestamp: Date.now(),
      };

      setDrivers(explainResponse.top_drivers || []);
      setPredictions((prev) => [...prev, prediction]);
      setCurrentPrediction(prediction);
      setBaseForm(formData);
      setBasePrediction(prediction);
      setSimPrediction(null);
      setSimForm(null);
      setSimDrivers([]);
      pushToast({ title: "Prediction complete", description: `Risk ${(prediction.probability * 100).toFixed(1)}%`, variant: "success" });
    } catch (error) {
      console.error("Prediction failed:", error);
      pushToast({ title: "Prediction failed", description: "Please verify backend availability.", variant: "error" });
    } finally {
      setIsPredicting(false);
    }
  };

  const handleSimulate = async (formData: FormState) => {
    if (isReadOnly) {
      pushToast({ title: "Read-only role", description: "Viewer cannot run simulations.", variant: "info" });
      return;
    }

    try {
      setIsSimulating(true);
      trackEvent("simulate_requested", { role, team: teamName });
      const [exp, res] = await Promise.all([explainChurn(formData), predictChurn(formData)]);

      setSimPrediction({
        predictionId: res.predictionId,
        probability: res.probability,
        isChurn: res.isChurn,
        shadowProbability: res.shadowProbability,
        timestamp: Date.now(),
      });
      setSimForm(formData);
      setSimDrivers(exp.top_drivers || []);
      pushToast({ title: "Simulation complete", description: `Simulated risk ${(res.probability * 100).toFixed(1)}%`, variant: "success" });
    } catch (error) {
      console.error("Simulation failed:", error);
      pushToast({ title: "Simulation failed", description: "Please verify backend availability.", variant: "error" });
    } finally {
      setIsSimulating(false);
    }
  };

  const handleSaveScenario = () => {
    if (!baseForm || !basePrediction) {
      pushToast({ title: "No baseline to save", description: "Run a prediction first.", variant: "info" });
      return;
    }
    if (isReadOnly) {
      pushToast({ title: "Read-only role", description: "Viewer cannot save scenarios.", variant: "info" });
      return;
    }

    const name = scenarioName.trim() || `Scenario ${scenarios.length + 1}`;
    const scenario: Scenario = {
      id: `${Date.now()}-${Math.floor(Math.random() * 1000)}`,
      name,
      notes: scenarioNotes.trim(),
      comments: [],
      form: baseForm,
      prediction: basePrediction,
      createdAt: Date.now(),
    };
    setScenarios((prev) => [scenario, ...prev]);
    setScenarioName("");
    setScenarioNotes("");
    trackEvent("scenario_saved", { role, team: teamName });
    pushToast({ title: "Scenario saved", description: `${name} added to team workspace.`, variant: "success" });
  };

  const addScenarioComment = (scenarioId: string) => {
    const comment = (newCommentByScenario[scenarioId] || "").trim();
    if (!comment) return;
    if (isReadOnly) {
      pushToast({ title: "Read-only role", description: "Viewer cannot add comments.", variant: "info" });
      return;
    }

    setScenarios((prev) => prev.map((item) => {
      if (item.id !== scenarioId) return item;
      return { ...item, comments: [...item.comments, comment] };
    }));

    setNewCommentByScenario((prev) => ({ ...prev, [scenarioId]: "" }));
    pushToast({ title: "Comment added", variant: "success" });
  };

  const applyScenarioToForm = (scenario: Scenario) => {
    setFormSeed(scenario.form);
    setBaseForm(scenario.form);
    setBasePrediction(scenario.prediction);
    setCurrentPrediction(scenario.prediction);
    trackEvent("scenario_loaded", { role, team: teamName });
    pushToast({ title: "Scenario loaded", description: `${scenario.name} loaded into form.`, variant: "info" });
  };

  const avgProb = predictions.length
    ? predictions.reduce((sum, p) => sum + p.probability, 0) / predictions.length
    : 0;
  const recent = predictions.slice(-5);
  const previous = predictions.slice(-10, -5);
  const recentAvg = recent.length ? recent.reduce((sum, p) => sum + p.probability, 0) / recent.length : avgProb;
  const previousAvg = previous.length
    ? previous.reduce((sum, p) => sum + p.probability, 0) / previous.length
    : avgProb;
  const trendDelta = (recentAvg - previousAvg) * 100;

  const changedFields = useMemo(() => {
    if (!baseForm || !simForm) return [];

    return Object.keys(baseForm)
      .filter((key) => baseForm[key as keyof FormState] !== simForm[key as keyof FormState])
      .slice(0, 5)
      .map((key) => {
        const typed = key as keyof FormState;
        return {
          key,
          label: FIELD_LABELS[typed] || key,
          from: String(baseForm[typed]),
          to: String(simForm[typed]),
        };
      });
  }, [baseForm, simForm]);

  const simDelta = simPrediction && basePrediction
    ? (simPrediction.probability - basePrediction.probability) * 100
    : null;

  const groupedDrivers = useMemo(() => {
    const groups = new Map<string, number>();
    drivers.forEach((driver) => {
      const group = DRIVER_GROUPS[driver.feature] || "Engagement";
      const current = groups.get(group) || 0;
      groups.set(group, current + driver.impact);
    });
    return Array.from(groups.entries())
      .map(([group, totalImpact]) => ({ group, totalImpact }))
      .sort((a, b) => Math.abs(b.totalImpact) - Math.abs(a.totalImpact));
  }, [drivers]);

  const rankedActions = useMemo(() => {
    const baseActions = [
      { key: "contract", label: "Promote annual contract migration", dependsOn: ["Contract", "IsMonthToMonth"], factor: 0.18 },
      { key: "support", label: "Provide proactive support bundle", dependsOn: ["TechSupport", "TechIssueRisk", "OnlineSecurity"], factor: 0.14 },
      { key: "billing", label: "Incentivize autopay and billing stabilization", dependsOn: ["PaymentRisk", "PaymentMethod"], factor: 0.11 },
      { key: "pricing", label: "Offer price relief or loyalty discount", dependsOn: ["MonthlyCharges", "TotalCharges"], factor: 0.09 },
    ];

    const positiveDrivers = drivers.filter((driver) => driver.impact > 0);
    return baseActions
      .map((action) => {
        const signal = positiveDrivers
          .filter((driver) => action.dependsOn.includes(driver.feature))
          .reduce((sum, driver) => sum + driver.impact, 0);
        return {
          ...action,
          estimatedReduction: Math.max(0, Math.min(25, signal * 100 * action.factor)),
        };
      })
      .filter((action) => action.estimatedReduction > 0)
      .sort((a, b) => b.estimatedReduction - a.estimatedReduction);
  }, [drivers]);

  const whyChanged = useMemo(() => {
    if (!simPrediction || !basePrediction) return null;
    const direction = simDelta !== null && simDelta < 0 ? "decreased" : "increased";
    const topChanged = changedFields.slice(0, 3).map((item) => item.label).join(", ");
    const keySimDriver = simDrivers.find((driver) => driver.impact > 0)?.feature;
    const keyBaseDriver = drivers.find((driver) => driver.impact > 0)?.feature;
    return {
      direction,
      reason: topChanged || "input profile changes",
      dominantDriver: keySimDriver || keyBaseDriver || "balanced features",
    };
  }, [basePrediction, changedFields, drivers, simDelta, simDrivers, simPrediction]);

  const comparedScenarios = scenarios.filter((scenario) => selectedScenarioIds.includes(scenario.id));

  const handleRecommend = async () => {
    if (!baseForm) {
      pushToast({ title: "No baseline profile", description: "Run a baseline prediction first.", variant: "info" });
      return;
    }
    if (isReadOnly) {
      pushToast({ title: "Read-only role", description: "Viewer cannot request recommendations.", variant: "info" });
      return;
    }

    try {
      setIsRecommending(true);
      const result = await getRecommendations(baseForm, recommendationBudget);
      setRecommendationResult(result);
      pushToast({ title: "Recommendations ready", description: `Selected ${result.selected_actions.length} actions within budget.`, variant: "success" });
    } catch (error) {
      console.error(error);
      pushToast({ title: "Recommendation failed", description: "Could not fetch recommendation plan.", variant: "error" });
    } finally {
      setIsRecommending(false);
    }
  };

  const handleFeedbackSubmit = async (useful: boolean) => {
    if (!currentPrediction?.predictionId) {
      pushToast({ title: "No prediction selected", description: "Run a prediction first.", variant: "info" });
      return;
    }
    try {
      await submitFeedback(currentPrediction.predictionId, useful, feedbackComment || undefined);
      setFeedbackComment("");
      pushToast({ title: "Feedback saved", description: useful ? "Marked as useful." : "Marked as not useful.", variant: "success" });
    } catch (error) {
      console.error(error);
      pushToast({ title: "Feedback failed", description: "Could not submit feedback.", variant: "error" });
    }
  };

  const handleOutcomeSubmit = async (actualChurn: boolean) => {
    if (!currentPrediction?.predictionId) {
      pushToast({ title: "No prediction selected", description: "Run a prediction first.", variant: "info" });
      return;
    }
    try {
      await submitOutcome(currentPrediction.predictionId, actualChurn, outcomeNotes || undefined);
      setOutcomeNotes("");
      pushToast({ title: "Outcome saved", description: `Recorded actual outcome: ${actualChurn ? "churn" : "retained"}.`, variant: "success" });
    } catch (error) {
      console.error(error);
      pushToast({ title: "Outcome failed", description: "Could not submit outcome.", variant: "error" });
    }
  };

  return (
    <div className="min-h-screen bg-base px-4 py-6 text-ink md:px-6 lg:px-8">
      <div className="mx-auto max-w-[1320px] space-y-6">
        <header className="fade-stagger rounded-3xl border border-border bg-surface/90 p-6 shadow-[0_15px_40px_rgba(31,42,42,0.08)] backdrop-blur-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-muted">Teal + Copper ML Studio</p>
              <h1 className="mt-1 text-4xl font-extrabold md:text-5xl">Customer Churn Intelligence</h1>
              <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted md:text-base">
                Predict churn, explain top risk drivers, and run What-if simulations with model-aligned feature engineering.
              </p>
              {isReadOnly && (
                <p className="mt-2 inline-flex rounded-full border border-border bg-base px-3 py-1 text-xs font-semibold text-muted">
                  Viewer mode: read-only access
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={() => {
                setShowHowItWorks(true);
                trackEvent("modal_opened", { modal: "how_prediction_works", role });
              }}
              className="rounded-xl border border-border bg-surface px-4 py-2 text-sm font-semibold text-ink transition hover:border-accent"
            >
              How prediction is calculated
            </button>
          </div>

          <div className="mt-5 grid gap-4 md:grid-cols-4">
            <KPI title="Profiles Scored" value={predictions.length} />
            <KPI title="Avg Churn Risk" value={avgProb * 100} suffix="%" delta={trendDelta} />
            <KPI title="Current Risk Band" value={inferRiskBand(currentPrediction?.probability ?? null)} />
            <KPI title="Likely Churn" value={predictions.filter((p) => p.isChurn).length} />
          </div>
        </header>

        <div className="fade-stagger rounded-2xl border border-border bg-accent-soft/45 px-4 py-3 text-sm text-ink" style={{ animationDelay: "90ms" }}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-4">
              <p>
                <span className="font-semibold">Model:</span> CatBoost + SHAP
                <InfoTip content="CatBoost predicts churn probability; SHAP explains which input features most influenced that prediction." />
              </p>
              <p><span className="font-semibold">Last trained:</span> Mar 2026</p>
              <p><span className="font-semibold">Dataset:</span> 7,043 records</p>
              <p>
                <span className="font-semibold">Validation:</span> AUC 0.84 / F1 0.73
                <InfoTip content="AUC measures ranking quality across thresholds. F1 balances precision and recall for churn detection." />
              </p>
            </div>
            <span className="rounded-full bg-surface px-3 py-1 text-xs font-semibold text-accent">Production-style simulation panel</span>
          </div>
        </div>

        <main className="grid gap-6 lg:grid-cols-12">
          <aside className="fade-stagger lg:col-span-4" style={{ animationDelay: "130ms" }}>
            <div className="lg:sticky lg:top-5">
              <Section>
                <h2 className="text-xl font-bold">Customer Inputs</h2>
                <p className="mt-1 text-sm text-muted">Adjust the profile and run prediction or simulation.</p>
                <div className="mt-4">
                  <ChurnForm
                    onSubmit={handlePredict}
                    onSimulate={handleSimulate}
                    isPredicting={isPredicting}
                    isSimulating={isSimulating}
                    canSimulate={!!baseForm}
                    readOnly={isReadOnly}
                    initialForm={formSeed}
                    onFormChange={setBaseForm}
                  />
                </div>
              </Section>
            </div>
          </aside>

          <section className="fade-stagger space-y-6 lg:col-span-8" style={{ animationDelay: "170ms" }}>
            <Section>
              <h2 className="text-2xl font-bold">
                Decision Panel
                <InfoTip content="This panel combines the raw probability score, final risk tier, and practical next-step suggestions." />
              </h2>
              <p className="mb-4 mt-1 text-sm text-muted">Live result canvas with confidence and recommended interventions.</p>
              <PredictionCard
                probability={currentPrediction?.probability ?? null}
                isChurn={currentPrediction?.isChurn ?? null}
                isLoading={isPredicting}
                drivers={drivers}
              />

              {currentPrediction?.shadowProbability !== undefined && (
                <div className="mt-3 rounded-xl border border-border bg-surface p-3 text-sm text-muted">
                  Shadow model score: {(currentPrediction.shadowProbability * 100).toFixed(1)}% (for A/B shadow comparison)
                </div>
              )}

              {basePrediction && (
                <div className="mt-5 rounded-2xl border border-border bg-base/65 p-4">
                  <p className="text-xs uppercase tracking-[0.13em] text-muted">
                    What-if compare mode
                    <InfoTip content="Baseline is the latest real prediction. Simulated is the result after you tweak fields to test retention ideas." />
                  </p>

                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    <div className="rounded-xl border border-border bg-surface p-4">
                      <p className="text-xs text-muted">Baseline</p>
                      <p className="mt-1 text-2xl font-bold text-ink">{(basePrediction.probability * 100).toFixed(1)}%</p>
                      <span className="rounded-full bg-accent-soft px-2 py-1 text-xs font-semibold text-accent">
                        {inferRiskBand(basePrediction.probability)} risk
                      </span>
                    </div>

                    <div className="rounded-xl border border-border bg-surface p-4 transition-all duration-200">
                      <p className="text-xs text-muted">Simulated</p>
                      <p className="mt-1 text-2xl font-bold text-ink">
                        {simPrediction ? `${(simPrediction.probability * 100).toFixed(1)}%` : "Waiting..."}
                      </p>
                      <div className="flex items-center gap-2">
                        <span className="rounded-full bg-accent-soft px-2 py-1 text-xs font-semibold text-accent">
                          {simPrediction ? `${inferRiskBand(simPrediction.probability)} risk` : "Run simulation"}
                        </span>
                        {simDelta !== null && (
                          <span
                            className={`rounded-full px-2 py-1 text-xs font-semibold transition-all duration-200 ${
                              simDelta < 0 ? "bg-success/10 text-success" : "bg-copper/10 text-copper"
                            }`}
                          >
                            {simDelta < 0 ? "Risk reduced" : "Risk increased"} {simDelta > 0 ? "+" : ""}{simDelta.toFixed(1)}%
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {changedFields.length > 0 && (
                    <div className="mt-4">
                      <p className="mb-2 text-xs uppercase tracking-[0.13em] text-muted">Changed inputs</p>
                      <div className="flex flex-wrap gap-2">
                        {changedFields.map((item) => (
                          <span key={item.key} className="rounded-full border border-border bg-surface px-3 py-1 text-xs text-ink">
                            {item.label}: {item.from} {"->"} {item.to}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {simDelta !== null && (
                    <p className="mt-3 text-sm text-muted">
                      Impact summary: {simDelta < 0 ? "Risk reduced" : "Risk increased"} by {Math.abs(simDelta).toFixed(1)} percentage points.
                    </p>
                  )}

                  {whyChanged && (
                    <div className="mt-3 rounded-xl border border-border bg-surface p-3 text-sm text-muted">
                      <p className="font-semibold text-ink">Why this changed</p>
                      <p className="mt-1">
                        Risk {whyChanged.direction} mainly because of {whyChanged.reason}. Dominant signal now: {whyChanged.dominantDriver}.
                      </p>
                    </div>
                  )}
                </div>
              )}

              <div className="mt-5 rounded-2xl border border-border bg-base/65 p-4">
                <p className="text-xs uppercase tracking-[0.13em] text-muted">Scenario workflows</p>
                <div className="mt-3 grid gap-3 md:grid-cols-[1fr_auto]">
                  <div>
                    <input
                      value={scenarioName}
                      onChange={(event) => setScenarioName(event.target.value)}
                      placeholder='Scenario name (e.g. "Baseline SMB Fiber cohort")'
                      className="w-full rounded-xl border border-border bg-surface px-3 py-2 text-sm focus:border-accent focus:outline-none"
                    />
                    <textarea
                      value={scenarioNotes}
                      onChange={(event) => setScenarioNotes(event.target.value)}
                      rows={2}
                      placeholder="Notes for team collaboration"
                      className="mt-2 w-full rounded-xl border border-border bg-surface px-3 py-2 text-sm focus:border-accent focus:outline-none"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={handleSaveScenario}
                    disabled={isReadOnly}
                    className="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-border"
                  >
                    Save scenario
                  </button>
                </div>

                <div className="mt-4 grid gap-3 lg:grid-cols-2">
                  {scenarios.slice(0, 6).map((scenario) => {
                    const selected = selectedScenarioIds.includes(scenario.id);
                    return (
                      <div key={scenario.id} className="rounded-xl border border-border bg-surface p-3">
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <p className="font-semibold text-ink">{scenario.name}</p>
                            <p className="text-xs text-muted">{new Date(scenario.createdAt).toLocaleString()}</p>
                          </div>
                          <div className="flex gap-2">
                            <button
                              type="button"
                              onClick={() => applyScenarioToForm(scenario)}
                              className="rounded-lg border border-border px-2 py-1 text-xs font-semibold"
                            >
                              Load
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setSelectedScenarioIds((prev) => {
                                  if (prev.includes(scenario.id)) return prev.filter((id) => id !== scenario.id);
                                  const next = [...prev, scenario.id].slice(-3);
                                  trackEvent("scenario_compared", { selected: next.length, role });
                                  return next;
                                });
                              }}
                              className={`rounded-lg border px-2 py-1 text-xs font-semibold ${selected ? "border-accent bg-accent-soft text-accent" : "border-border"}`}
                            >
                              {selected ? "Selected" : "Compare"}
                            </button>
                          </div>
                        </div>

                        {scenario.notes && <p className="mt-2 text-xs text-muted">{scenario.notes}</p>}

                        <div className="mt-2 text-xs text-muted">
                          Risk {(scenario.prediction.probability * 100).toFixed(1)}% · {scenario.prediction.isChurn ? "Likely churn" : "Likely stay"}
                        </div>

                        <div className="mt-2">
                          <input
                            value={newCommentByScenario[scenario.id] || ""}
                            onChange={(event) => setNewCommentByScenario((prev) => ({ ...prev, [scenario.id]: event.target.value }))}
                            placeholder="Add comment"
                            disabled={isReadOnly}
                            className="w-full rounded-lg border border-border bg-base px-2 py-1 text-xs focus:border-accent focus:outline-none disabled:opacity-50"
                          />
                          <button
                            type="button"
                            onClick={() => addScenarioComment(scenario.id)}
                            disabled={isReadOnly}
                            className="mt-2 rounded-lg border border-border px-2 py-1 text-xs font-semibold disabled:opacity-50"
                          >
                            Comment
                          </button>
                          {scenario.comments.length > 0 && (
                            <ul className="mt-2 space-y-1 text-xs text-muted">
                              {scenario.comments.slice(-2).map((comment, idx) => (
                                <li key={`${scenario.id}-${idx}`}>• {comment}</li>
                              ))}
                            </ul>
                          )}
                        </div>
                      </div>
                    );
                  })}
                  {scenarios.length === 0 && (
                    <p className="rounded-xl border border-border bg-surface p-3 text-sm text-muted">No saved scenarios for {teamName} yet.</p>
                  )}
                </div>

                {comparedScenarios.length > 0 && (
                  <div className="mt-4 rounded-xl border border-border bg-surface p-3">
                    <p className="text-xs uppercase tracking-[0.12em] text-muted">Side-by-side comparison</p>
                    <div className="mt-2 grid gap-2 md:grid-cols-3">
                      {comparedScenarios.map((scenario) => (
                        <div key={scenario.id} className="rounded-lg border border-border bg-base p-2 text-sm">
                          <p className="font-semibold text-ink">{scenario.name}</p>
                          <p className="text-xs text-muted">Risk {(scenario.prediction.probability * 100).toFixed(1)}%</p>
                          <p className="text-xs text-muted">{scenario.prediction.isChurn ? "Likely churn" : "Likely stay"}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <div className="mt-5 grid gap-4 md:grid-cols-2">
                <div className="rounded-2xl border border-border bg-base/65 p-4">
                  <p className="text-xs uppercase tracking-[0.13em] text-muted">Driver groups</p>
                  <div className="mt-2 space-y-2">
                    {groupedDrivers.map((entry) => (
                      <div key={entry.group} className="flex items-center justify-between rounded-lg border border-border bg-surface px-3 py-2 text-sm">
                        <span>{entry.group}</span>
                        <span className={entry.totalImpact >= 0 ? "text-copper" : "text-success"}>
                          {entry.totalImpact >= 0 ? "+" : ""}{entry.totalImpact.toFixed(2)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="rounded-2xl border border-border bg-base/65 p-4">
                  <p className="text-xs uppercase tracking-[0.13em] text-muted">Suggested actions ranked by expected reduction</p>
                  <div className="mt-2 space-y-2">
                    {rankedActions.map((action) => (
                      <div key={action.key} className="rounded-lg border border-border bg-surface px-3 py-2 text-sm">
                        <p className="font-semibold text-ink">{action.label}</p>
                        <p className="text-xs text-muted">Estimated risk reduction: {action.estimatedReduction.toFixed(1)} pts</p>
                      </div>
                    ))}
                    {rankedActions.length === 0 && <p className="text-sm text-muted">No actionable uplift candidates yet.</p>}
                  </div>
                </div>
              </div>

              <div className="mt-5 grid gap-4 md:grid-cols-2">
                <div className="rounded-2xl border border-border bg-base/65 p-4">
                  <p className="text-xs uppercase tracking-[0.13em] text-muted">Retention recommendation engine</p>
                  <div className="mt-3">
                    <label className="text-xs text-muted">Budget ({recommendationBudget.toFixed(0)})</label>
                    <input
                      type="range"
                      min={20}
                      max={300}
                      step={10}
                      value={recommendationBudget}
                      onChange={(event) => setRecommendationBudget(Number(event.target.value))}
                      className="mt-2 w-full"
                    />
                    <button
                      type="button"
                      onClick={handleRecommend}
                      disabled={isReadOnly || isRecommending || !baseForm}
                      className="mt-3 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-border"
                    >
                      {isRecommending ? "Running..." : "Get recommendations"}
                    </button>
                  </div>
                  {recommendationResult && (
                    <div className="mt-3 space-y-2 text-sm">
                      <p className="text-muted">
                        Selected cost {recommendationResult.total_selected_cost.toFixed(2)} / expected impact {recommendationResult.total_expected_impact.toFixed(2)}
                      </p>
                      {recommendationResult.selected_actions.map((item) => (
                        <div key={item.key} className="rounded-lg border border-border bg-surface px-3 py-2">
                          <p className="font-semibold text-ink">{item.label}</p>
                          <p className="text-xs text-muted">Confidence {(item.confidence * 100).toFixed(0)}% · Cost {item.estimated_cost}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="rounded-2xl border border-border bg-base/65 p-4">
                  <p className="text-xs uppercase tracking-[0.13em] text-muted">Human-in-the-loop feedback</p>
                  <textarea
                    value={feedbackComment}
                    onChange={(event) => setFeedbackComment(event.target.value)}
                    rows={2}
                    placeholder="Optional comment"
                    className="mt-2 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm focus:border-accent focus:outline-none"
                  />
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button type="button" onClick={() => handleFeedbackSubmit(true)} className="rounded-lg border border-success/40 bg-success/10 px-3 py-1 text-xs font-semibold text-success">Useful</button>
                    <button type="button" onClick={() => handleFeedbackSubmit(false)} className="rounded-lg border border-copper/40 bg-copper/10 px-3 py-1 text-xs font-semibold text-copper">Not useful</button>
                  </div>
                  <textarea
                    value={outcomeNotes}
                    onChange={(event) => setOutcomeNotes(event.target.value)}
                    rows={2}
                    placeholder="Outcome notes"
                    className="mt-3 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm focus:border-accent focus:outline-none"
                  />
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button type="button" onClick={() => handleOutcomeSubmit(true)} className="rounded-lg border border-copper/40 bg-copper/10 px-3 py-1 text-xs font-semibold text-copper">Actual churn</button>
                    <button type="button" onClick={() => handleOutcomeSubmit(false)} className="rounded-lg border border-success/40 bg-success/10 px-3 py-1 text-xs font-semibold text-success">Actual retained</button>
                  </div>
                </div>
              </div>
            </Section>

            <Section>
              <h2 className="text-2xl font-bold">
                Executive Insights
                <InfoTip content="Charts summarize trend, concentration of risk, and top model drivers to support quick business decisions." />
              </h2>
              <p className="mb-4 mt-1 text-sm text-muted">Trend, distribution, and driver analysis optimized for quick interpretation.</p>
              <Charts predictions={predictions} drivers={drivers} simDrivers={simDrivers} />
            </Section>
          </section>
        </main>
      </div>

      {showHowItWorks && (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-ink/55 px-4">
          <div className="w-full max-w-xl rounded-2xl border border-border bg-surface p-6 shadow-2xl">
            <div className="flex items-start justify-between">
              <h3 className="text-2xl font-bold">How prediction is calculated</h3>
              <button
                type="button"
                onClick={() => setShowHowItWorks(false)}
                className="rounded-lg border border-border px-2 py-1 text-sm text-muted"
              >
                Close
              </button>
            </div>
            <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-muted">
              <li>Raw form fields are validated and transformed into engineered features.</li>
              <li>CatBoost generates a churn probability score from 0 to 1.</li>
              <li>Threshold logic maps that score to Likely to Churn or Likely to Stay.</li>
              <li>SHAP ranks the strongest feature contributions for explainability.</li>
            </ol>
            <p className="mt-3 text-xs text-muted">All simulations use the same pipeline, so baseline and simulated outputs are directly comparable.</p>
          </div>
        </div>
      )}
    </div>
  );
}
