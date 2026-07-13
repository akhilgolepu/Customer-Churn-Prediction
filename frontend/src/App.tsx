import { useEffect, useMemo, useState } from "react";
import Dashboard from "./pages/Dashboard";
import CommandPalette, { type CommandItem } from "./components/ui/CommandPalette";
import FeedbackWidget from "./components/ui/FeedbackWidget";
import { ToastProvider, useToast } from "./components/ui/ToastProvider";
import {
  clearAccessToken,
  downloadBatchReport,
  getJob,
  getModelRegistry,
  getMonitoringSnapshot,
  loginWithRole,
  promoteModel,
  rollbackModel,
  startShadowModel,
  submitFeedback,
  uploadBatchScore,
} from "./services/api";
import { getEventCount, getRecentEvents, trackEvent } from "./services/analytics";

type Role = "admin" | "analyst" | "viewer";
type ViewMode = "workspace" | "admin";

interface SessionUser {
  name: string;
  team: string;
  role: Role;
}

const USER_STORAGE_KEY = "churn_user_session";

function readStoredUser(): SessionUser | null {
  try {
    const raw = localStorage.getItem(USER_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as SessionUser;
  } catch {
    return null;
  }
}

function AppShell() {
  const { pushToast } = useToast();
  const [user, setUser] = useState<SessionUser | null>(() => readStoredUser());
  const [pendingApiCalls, setPendingApiCalls] = useState(0);
  const [viewMode, setViewMode] = useState<ViewMode>("workspace");
  const [monitoringAlerts, setMonitoringAlerts] = useState<string[]>([]);
  const [registry, setRegistry] = useState<{
    active_model_id: string;
    shadow_model_id: string | null;
    versions: Array<{ id: string; version: string; status: string; artifact_path: string; metrics: Record<string, number>; created_at: number }>;
  } | null>(null);
  const [batchFile, setBatchFile] = useState<File | null>(null);
  const [batchJobId, setBatchJobId] = useState("");
  const [batchJobStatus, setBatchJobStatus] = useState("");

  const [loginName, setLoginName] = useState(user?.name ?? "");
  const [loginTeam, setLoginTeam] = useState(user?.team ?? "Growth Ops");
  const [loginRole, setLoginRole] = useState<Role>(user?.role ?? "analyst");

  const refreshAdminData = async () => {
    try {
      const [monitoring, models] = await Promise.all([getMonitoringSnapshot(), getModelRegistry()]);
      setMonitoringAlerts(monitoring.alerts || []);
      setRegistry(models);
    } catch (error) {
      console.error(error);
    }
  };

  useEffect(() => {
    if (!user) return;
    localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
  }, [user]);

  useEffect(() => {
    if (!user) return;
    if (user.role !== "admin") return;
    void refreshAdminData();
  }, [user]);

  useEffect(() => {
    const onStart = () => setPendingApiCalls((prev) => prev + 1);
    const onEnd = () => setPendingApiCalls((prev) => Math.max(0, prev - 1));
    const onSlow = (event: Event) => {
      const detail = (event as CustomEvent<{ path: string; elapsedMs: number }>).detail;
      pushToast({
        variant: "info",
        title: "Slow API call detected",
        description: `${detail.path} took ${detail.elapsedMs}ms`,
      });
    };
    const onError = (event: Event) => {
      const detail = (event as CustomEvent<{ path: string; status: number }>).detail;
      pushToast({
        variant: "error",
        title: "API error",
        description: `${detail.path} failed with status ${detail.status}`,
      });
    };

    window.addEventListener("app:api-start", onStart);
    window.addEventListener("app:api-end", onEnd);
    window.addEventListener("app:api-slow", onSlow as EventListener);
    window.addEventListener("app:api-error", onError as EventListener);

    return () => {
      window.removeEventListener("app:api-start", onStart);
      window.removeEventListener("app:api-end", onEnd);
      window.removeEventListener("app:api-slow", onSlow as EventListener);
      window.removeEventListener("app:api-error", onError as EventListener);
    };
  }, [pushToast]);

  const metrics = useMemo(() => {
    return {
      predictions: getEventCount("predict_requested"),
      simulations: getEventCount("simulate_requested"),
      savedScenarios: getEventCount("scenario_saved"),
      apiErrors: getEventCount("api_error"),
      slowCalls: getEventCount("api_slow"),
      feedbacks: getEventCount("feedback_submitted"),
    };
  }, [user, viewMode, pendingApiCalls]);

  const commands = useMemo<CommandItem[]>(() => {
    const base: CommandItem[] = [
      {
        id: "go-workspace",
        label: "Go to Workspace",
        hint: "View predictions and scenarios",
        action: () => {
          trackEvent("command_executed", { command: "go-workspace" });
          setViewMode("workspace");
        },
      },
      {
        id: "switch-analyst",
        label: "Switch role: Analyst",
        action: () => {
          if (!user) return;
          setUser({ ...user, role: "analyst" });
          trackEvent("role_changed", { role: "analyst" });
          pushToast({ title: "Role switched", description: "You are now Analyst.", variant: "info" });
          void loginWithRole("analyst").catch(() => {
            pushToast({ title: "Session refresh failed", description: "Could not refresh analyst token.", variant: "error" });
          });
        },
      },
      {
        id: "switch-viewer",
        label: "Switch role: Viewer",
        action: () => {
          if (!user) return;
          setUser({ ...user, role: "viewer" });
          trackEvent("role_changed", { role: "viewer" });
          pushToast({ title: "Role switched", description: "You are now Viewer (read-only).", variant: "info" });
          void loginWithRole("viewer").catch(() => {
            pushToast({ title: "Session refresh failed", description: "Could not refresh viewer token.", variant: "error" });
          });
        },
      },
      {
        id: "logout",
        label: "Sign out",
        action: () => {
          setUser(null);
          localStorage.removeItem(USER_STORAGE_KEY);
          clearAccessToken();
          trackEvent("auth_logout");
        },
      },
    ];

    if (user?.role === "admin") {
      base.unshift({
        id: "go-admin",
        label: "Go to Admin Console",
        hint: "Metrics, drift and retraining",
        action: () => {
          trackEvent("command_executed", { command: "go-admin" });
          setViewMode("admin");
        },
      });
    }

    return base;
  }, [pushToast, user]);

  if (!user) {
    return (
      <div className="min-h-screen bg-base px-4 py-8 text-ink md:px-8">
        <div className="mx-auto max-w-lg rounded-3xl border border-border bg-surface p-6 shadow-[0_18px_40px_rgba(31,42,42,0.08)]">
          <p className="text-xs uppercase tracking-[0.16em] text-muted">Team Workspace Sign In</p>
          <h1 className="mt-1 text-3xl font-extrabold">Churn Intelligence</h1>
          <p className="mt-2 text-sm text-muted">Select your role to unlock the appropriate workflow.</p>

          <div className="mt-5 space-y-4">
            <div>
              <label htmlFor="name" className="text-sm font-semibold">Name</label>
              <input
                id="name"
                value={loginName}
                onChange={(event) => setLoginName(event.target.value)}
                className="mt-1 w-full rounded-xl border border-border bg-base px-3 py-2 text-sm focus:border-accent focus:outline-none"
              />
            </div>
            <div>
              <label htmlFor="team" className="text-sm font-semibold">Team</label>
              <input
                id="team"
                value={loginTeam}
                onChange={(event) => setLoginTeam(event.target.value)}
                className="mt-1 w-full rounded-xl border border-border bg-base px-3 py-2 text-sm focus:border-accent focus:outline-none"
              />
            </div>
            <div>
              <label htmlFor="role" className="text-sm font-semibold">Role</label>
              <select
                id="role"
                value={loginRole}
                onChange={(event) => setLoginRole(event.target.value as Role)}
                className="mt-1 w-full rounded-xl border border-border bg-base px-3 py-2 text-sm focus:border-accent focus:outline-none"
              >
                <option value="admin">Admin</option>
                <option value="analyst">Analyst</option>
                <option value="viewer">Viewer</option>
              </select>
            </div>
            <button
              type="button"
              onClick={() => {
                const name = loginName.trim() || "Team Member";
                const team = loginTeam.trim() || "Growth Ops";
                const nextUser: SessionUser = { name, team, role: loginRole };
                loginWithRole(loginRole)
                  .then(() => {
                    setUser(nextUser);
                    trackEvent("auth_login", { role: loginRole, team });
                    pushToast({ title: "Signed in", description: `Welcome ${name}.`, variant: "success" });
                  })
                  .catch((error) => {
                    console.error(error);
                    pushToast({ title: "Sign-in failed", description: "Could not obtain backend token.", variant: "error" });
                  });
              }}
              className="w-full rounded-xl bg-accent px-4 py-3 font-semibold text-white"
            >
              Enter workspace
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-base text-ink">
      {pendingApiCalls > 0 && (
        <div className="fixed inset-x-0 top-0 z-50 h-1 overflow-hidden bg-accent-soft">
          <div className="h-full w-1/3 animate-pulse bg-accent" />
        </div>
      )}

      <header className="sticky top-0 z-20 border-b border-border bg-surface/95 px-4 py-3 backdrop-blur md:px-8">
        <div className="mx-auto flex max-w-[1320px] flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-[0.14em] text-muted">Customer Churn Predictor</p>
            <p className="text-sm font-semibold">{user.team} · {user.name}</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-accent-soft px-3 py-1 text-xs font-semibold text-accent">{user.role}</span>
            <select
              value={user.role}
              onChange={(event) => {
                const nextRole = event.target.value as Role;
                setUser({ ...user, role: nextRole });
                trackEvent("role_changed", { role: nextRole });
                if (viewMode === "admin" && nextRole !== "admin") setViewMode("workspace");
                pushToast({ title: "Role switched", description: `Now acting as ${nextRole}.`, variant: "info" });
                loginWithRole(nextRole).catch(() => {
                  pushToast({ title: "Session refresh failed", description: "Could not refresh role token.", variant: "error" });
                });
              }}
              className="rounded-lg border border-border bg-surface px-2 py-1.5 text-sm"
              aria-label="Switch role"
            >
              <option value="admin">Admin</option>
              <option value="analyst">Analyst</option>
              <option value="viewer">Viewer</option>
            </select>
            <button
              type="button"
              onClick={() => setViewMode("workspace")}
              className={`rounded-lg px-3 py-1.5 text-sm font-semibold ${viewMode === "workspace" ? "bg-accent text-white" : "border border-border bg-surface text-ink"}`}
            >
              Workspace
            </button>
            <button
              type="button"
              disabled={user.role !== "admin"}
              onClick={() => setViewMode("admin")}
              className={`rounded-lg px-3 py-1.5 text-sm font-semibold ${
                viewMode === "admin" ? "bg-accent text-white" : "border border-border bg-surface text-ink"
              } disabled:cursor-not-allowed disabled:opacity-45`}
            >
              Admin
            </button>
            <button
              type="button"
              onClick={() => {
                setUser(null);
                localStorage.removeItem(USER_STORAGE_KEY);
                clearAccessToken();
                trackEvent("auth_logout");
              }}
              className="rounded-lg border border-border bg-surface px-3 py-1.5 text-sm font-semibold"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      {viewMode === "admin" && user.role === "admin" ? (
        <main className="mx-auto max-w-[1320px] space-y-6 px-4 py-6 md:px-8">
          <section className="rounded-2xl border border-border bg-surface p-5">
            <p className="text-xs uppercase tracking-[0.13em] text-muted">Admin Console</p>
            <h2 className="mt-1 text-2xl font-bold">Model operations and drift control</h2>
            <p className="mt-2 text-sm text-muted">Monitor UI activity, API behavior, and trigger operational controls.</p>

            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <StatCard label="Prediction requests" value={metrics.predictions} />
              <StatCard label="Simulation requests" value={metrics.simulations} />
              <StatCard label="Saved scenarios" value={metrics.savedScenarios} />
              <StatCard label="Slow API calls" value={metrics.slowCalls} />
              <StatCard label="API errors" value={metrics.apiErrors} />
              <StatCard label="Feedback items" value={metrics.feedbacks} />
            </div>

            <div className="mt-5 grid gap-3 md:grid-cols-3">
              <button
                type="button"
                onClick={() => {
                  refreshAdminData()
                    .then(() => pushToast({ title: "Monitoring refreshed", description: "Fetched latest drift/performance snapshot.", variant: "success" }))
                    .catch(() => pushToast({ title: "Refresh failed", description: "Could not fetch monitoring snapshot.", variant: "error" }));
                }}
                className="rounded-xl border border-border bg-surface px-4 py-3 text-sm font-semibold"
              >
                Refresh monitoring
              </button>
              <button
                type="button"
                onClick={() => {
                  const candidate = registry?.versions.find((item) => item.status === "candidate");
                  if (!candidate) {
                    pushToast({ title: "No candidate model", description: "Register a challenger before promoting.", variant: "info" });
                    return;
                  }
                  promoteModel(candidate.id)
                    .then((result) => {
                      pushToast({ title: "Model promoted", description: result.message, variant: "success" });
                      return refreshAdminData();
                    })
                    .catch(() => pushToast({ title: "Promote failed", description: "Could not promote model.", variant: "error" }));
                }}
                className="rounded-xl border border-border bg-surface px-4 py-3 text-sm font-semibold"
              >
                Promote candidate
              </button>
              <button
                type="button"
                onClick={() => {
                  rollbackModel()
                    .then((result) => {
                      pushToast({ title: "Rollback complete", description: result.message, variant: "success" });
                      return refreshAdminData();
                    })
                    .catch(() => pushToast({ title: "Rollback failed", description: "No archived model was available.", variant: "error" }));
                }}
                className="rounded-xl border border-border bg-surface px-4 py-3 text-sm font-semibold"
              >
                Rollback active model
              </button>
            </div>

            <div className="mt-5 rounded-xl border border-border bg-base p-4">
              <p className="text-xs uppercase tracking-[0.12em] text-muted">Batch prediction and report download</p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <input
                  type="file"
                  accept=".csv"
                  onChange={(event) => setBatchFile(event.target.files?.[0] ?? null)}
                  className="text-sm"
                />
                <button
                  type="button"
                  onClick={() => {
                    if (!batchFile) {
                      pushToast({ title: "Select a CSV", description: "Choose a file first.", variant: "info" });
                      return;
                    }
                    uploadBatchScore(batchFile)
                      .then((result) => {
                        setBatchJobId(result.job.id);
                        setBatchJobStatus(result.job.status);
                        pushToast({ title: "Batch job queued", description: `Job ${result.job.id.slice(0, 8)} created.`, variant: "success" });
                      })
                      .catch(() => pushToast({ title: "Batch upload failed", description: "Could not create batch job.", variant: "error" }));
                  }}
                  className="rounded border border-border px-3 py-1 text-sm"
                >
                  Upload + score
                </button>
                <button
                  type="button"
                  disabled={!batchJobId}
                  onClick={() => {
                    if (!batchJobId) return;
                    getJob(batchJobId)
                      .then((result) => {
                        setBatchJobStatus(result.job.status);
                        pushToast({ title: "Job refreshed", description: `Status: ${result.job.status}`, variant: "info" });
                      })
                      .catch(() => pushToast({ title: "Job lookup failed", description: "Could not fetch job status.", variant: "error" }));
                  }}
                  className="rounded border border-border px-3 py-1 text-sm disabled:opacity-50"
                >
                  Refresh status
                </button>
                <button
                  type="button"
                  disabled={!batchJobId || batchJobStatus !== "completed"}
                  onClick={() => {
                    if (!batchJobId) return;
                    downloadBatchReport(batchJobId)
                      .then((csv) => {
                        const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
                        const url = URL.createObjectURL(blob);
                        const anchor = document.createElement("a");
                        anchor.href = url;
                        anchor.download = `batch-report-${batchJobId}.csv`;
                        anchor.click();
                        URL.revokeObjectURL(url);
                        pushToast({ title: "Report downloaded", description: "CSV report downloaded successfully.", variant: "success" });
                      })
                      .catch(() => pushToast({ title: "Download failed", description: "Batch report is not ready yet.", variant: "error" }));
                  }}
                  className="rounded border border-border px-3 py-1 text-sm disabled:opacity-50"
                >
                  Download report
                </button>
              </div>
              {batchJobId && (
                <p className="mt-2 text-xs text-muted">Job {batchJobId} · status: {batchJobStatus || "unknown"}</p>
              )}
            </div>

            {registry && (
              <div className="mt-5 rounded-xl border border-border bg-base p-4">
                <p className="text-xs uppercase tracking-[0.12em] text-muted">Model registry</p>
                <div className="mt-2 space-y-2">
                  {registry.versions.map((item) => (
                    <div key={item.id} className="rounded-lg border border-border bg-surface px-3 py-2 text-sm">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="font-semibold text-ink">{item.version}</p>
                          <p className="text-xs text-muted">{item.id.slice(0, 8)} · {item.status}</p>
                        </div>
                        <div className="flex items-center gap-2">
                          {item.status === "candidate" && (
                            <button
                              type="button"
                              onClick={() => {
                                startShadowModel(item.id)
                                  .then((result) => {
                                    pushToast({ title: "Shadow enabled", description: result.message, variant: "success" });
                                    return refreshAdminData();
                                  })
                                  .catch(() => pushToast({ title: "Shadow failed", description: "Could not enable shadow model.", variant: "error" }));
                              }}
                              className="rounded border border-border px-2 py-1 text-xs"
                            >
                              Shadow
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {monitoringAlerts.length > 0 && (
              <div className="mt-4 rounded-xl border border-copper/30 bg-copper/10 p-4">
                <p className="text-sm font-semibold text-copper">Monitoring alerts</p>
                <ul className="mt-2 space-y-1 text-xs text-copper">
                  {monitoringAlerts.map((alert, idx) => <li key={`${alert}-${idx}`}>- {alert}</li>)}
                </ul>
              </div>
            )}
          </section>

          <section className="rounded-2xl border border-border bg-surface p-5">
            <h3 className="text-lg font-bold">Recent telemetry</h3>
            <div className="mt-3 space-y-2 text-sm">
              {getRecentEvents(16).map((event, index) => (
                <div key={`${event.name}-${event.timestamp}-${index}`} className="rounded-lg border border-border bg-base px-3 py-2">
                  <p className="font-semibold text-ink">{event.name}</p>
                  <p className="text-xs text-muted">{new Date(event.timestamp).toLocaleString()}</p>
                </div>
              ))}
            </div>
          </section>
        </main>
      ) : (
        <Dashboard role={user.role} teamName={user.team} />
      )}

      <CommandPalette
        commands={commands}
        onOpenChange={(open) => {
          if (open) trackEvent("command_palette_opened", { role: user.role });
        }}
        onExecute={(commandId) => {
          trackEvent("command_executed", { command: commandId, role: user.role });
        }}
      />
      <FeedbackWidget
        onSubmit={(message) => {
          trackEvent("feedback_submitted", { length: message.length, role: user.role });
          if (!user || !user.role) {
            pushToast({ title: "Feedback failed", description: "No active session.", variant: "error" });
            return;
          }
          submitFeedback("ui-workspace", true, message)
            .then(() => pushToast({ title: "Feedback sent", description: "Thanks for helping improve the workflow.", variant: "success" }))
            .catch(() => pushToast({ title: "Feedback failed", description: "Could not send feedback to backend.", variant: "error" }));
        }}
      />
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-border bg-base px-4 py-3">
      <p className="text-xs uppercase tracking-[0.12em] text-muted">{label}</p>
      <p className="mt-1 text-2xl font-bold text-ink">{value}</p>
    </div>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <AppShell />
    </ToastProvider>
  );
}
