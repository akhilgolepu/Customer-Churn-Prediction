import type { FormState } from "../types/formState";
import { trackEvent } from "./analytics";

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";
const SLOW_CALL_MS = 1200;
let accessToken = "";

function getAuthHeaders(): Record<string, string> {
    if (!accessToken) return {};
    return { Authorization: `Bearer ${accessToken}` };
}

export function setAccessToken(token: string) {
    accessToken = token;
}

export function clearAccessToken() {
    accessToken = "";
}

export function getAccessToken() {
    return accessToken;
}

async function handleJsonResponse<T>(res: Response, path: string, errorPrefix: string): Promise<T> {
    if (!res.ok) {
        const detail = await res.text().catch(() => "Unknown error");
        trackEvent("api_error", { path, status: res.status, detail });
        window.dispatchEvent(new CustomEvent("app:api-error", { detail: { path, status: res.status, detail } }));
        throw new Error(`${errorPrefix} (${res.status}): ${detail}`);
    }
    return await res.json() as T;
}

async function timedRequest<T>(path: string, errorPrefix: string, requestFn: () => Promise<Response>): Promise<T> {
    const startedAt = performance.now();
    window.dispatchEvent(new CustomEvent("app:api-start", { detail: { path } }));
    try {
        const res = await requestFn();
        const elapsedMs = Math.round(performance.now() - startedAt);
        if (elapsedMs >= SLOW_CALL_MS) {
            trackEvent("api_slow", { path, elapsedMs });
            window.dispatchEvent(new CustomEvent("app:api-slow", { detail: { path, elapsedMs } }));
        }
        return await handleJsonResponse<T>(res, path, errorPrefix);
    } finally {
        window.dispatchEvent(new CustomEvent("app:api-end", { detail: { path } }));
    }
}

export async function loginWithRole(role: "admin" | "analyst" | "viewer") {
    const passwordByRole: Record<typeof role, string> = {
        admin: "admin123",
        analyst: "analyst123",
        viewer: "viewer123",
    };

    const path = "/api/v1/auth/login";
    const tokens = await timedRequest<{ access_token: string; refresh_token: string; token_type: string }>(
        path,
        "Login failed",
        () => fetch(`${BASE_URL}${path}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username: role, password: passwordByRole[role] }),
        }),
    );
    setAccessToken(tokens.access_token);
    return tokens;
}

async function postJson<T>(path: string, formData: FormState, errorPrefix: string): Promise<T> {
    return timedRequest<T>(path, errorPrefix, () => fetch(`${BASE_URL}${path}`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...getAuthHeaders(),
            },
            body: JSON.stringify(formData),
        }));
}

export async function predictChurn(formData: FormState) {
    return await postJson<{ predictionId: string; probability: number; isChurn: boolean; shadowProbability?: number }>(
        "/api/v1/predictions/predict",
        formData,
        "Prediction failed",
    );
}

export async function explainChurn(formData: FormState) {
    return await postJson<{ top_drivers: Array<{ feature: string; value: string | number; impact: number }> }>(
        "/api/v1/predictions/explain",
        formData,
        "Explanation failed",
    );
}

export async function getMonitoringSnapshot() {
    const path = "/api/v1/system/monitoring";
    return timedRequest<{
        input_drift: Array<{ metric: string; baseline: number; recent: number; delta: number; threshold: number; alert: boolean }>;
        prediction_drift: { metric: string; baseline: number; recent: number; delta: number; threshold: number; alert: boolean };
        performance: { samples: number; accuracy: number; precision: number; recall: number };
        alerts: string[];
    }>(path, "Monitoring fetch failed", () => fetch(`${BASE_URL}${path}`, { headers: { ...getAuthHeaders() } }));
}

export async function getModelRegistry() {
    const path = "/api/v1/models";
    return timedRequest<{
        active_model_id: string;
        shadow_model_id: string | null;
        versions: Array<{ id: string; version: string; status: string; artifact_path: string; metrics: Record<string, number>; created_at: number }>;
    }>(path, "Model registry fetch failed", () => fetch(`${BASE_URL}${path}`, { headers: { ...getAuthHeaders() } }));
}

export async function promoteModel(candidateModelId: string) {
    const path = "/api/v1/models/promote";
    return timedRequest<{ message: string; active_model_id: string; shadow_model_id: string | null }>(
        path,
        "Model promote failed",
        () => fetch(`${BASE_URL}${path}`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...getAuthHeaders() },
            body: JSON.stringify({ candidate_model_id: candidateModelId }),
        }),
    );
}

export async function rollbackModel(targetModelId?: string) {
    const path = "/api/v1/models/rollback";
    return timedRequest<{ message: string; active_model_id: string; shadow_model_id: string | null }>(
        path,
        "Model rollback failed",
        () => fetch(`${BASE_URL}${path}`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...getAuthHeaders() },
            body: JSON.stringify({ target_model_id: targetModelId ?? null }),
        }),
    );
}

export async function startShadowModel(candidateModelId: string) {
    const path = "/api/v1/models/shadow";
    return timedRequest<{ message: string; active_model_id: string; shadow_model_id: string | null }>(
        path,
        "Shadow setup failed",
        () => fetch(`${BASE_URL}${path}`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...getAuthHeaders() },
            body: JSON.stringify({ candidate_model_id: candidateModelId }),
        }),
    );
}

export async function getRecommendations(customer: FormState, budget: number) {
    const path = "/api/v1/predictions/recommend";
    return timedRequest<{
        prediction_id: string;
        probability: number;
        risk_tier: string;
        actions: Array<{ key: string; label: string; rationale: string; expected_impact_score: number; confidence: number; estimated_cost: number; impact_per_budget: number }>;
        selected_actions: Array<{ key: string; label: string; rationale: string; expected_impact_score: number; confidence: number; estimated_cost: number; impact_per_budget: number }>;
        total_selected_cost: number;
        total_expected_impact: number;
    }>(path, "Recommendation failed", () => fetch(`${BASE_URL}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({ customer, budget }),
    }));
}

export async function submitFeedback(predictionId: string, useful: boolean, comment?: string) {
    const path = "/api/v1/predictions/feedback";
    return timedRequest<{ total_feedback: number; useful_count: number; not_useful_count: number; useful_ratio: number; outcomes_recorded: number }>(
        path,
        "Feedback submit failed",
        () => fetch(`${BASE_URL}${path}`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...getAuthHeaders() },
            body: JSON.stringify({ prediction_id: predictionId, useful, comment: comment ?? null }),
        }),
    );
}

export async function submitOutcome(predictionId: string, actualChurn: boolean, notes?: string) {
    const path = "/api/v1/predictions/outcome";
    return timedRequest<{ total_feedback: number; useful_count: number; not_useful_count: number; useful_ratio: number; outcomes_recorded: number }>(
        path,
        "Outcome submit failed",
        () => fetch(`${BASE_URL}${path}`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...getAuthHeaders() },
            body: JSON.stringify({ prediction_id: predictionId, actual_churn: actualChurn, notes: notes ?? null }),
        }),
    );
}

export async function getFeedbackSummary() {
    const path = "/api/v1/predictions/feedback/summary";
    return timedRequest<{ total_feedback: number; useful_count: number; not_useful_count: number; useful_ratio: number; outcomes_recorded: number }>(
        path,
        "Feedback summary fetch failed",
        () => fetch(`${BASE_URL}${path}`, { headers: { ...getAuthHeaders() } }),
    );
}

export async function uploadBatchScore(file: File) {
    const path = "/api/v1/jobs/batch-score";
    const form = new FormData();
    form.append("file", file);

    return timedRequest<{ job: { id: string; status: string; job_type: string } }>(
        path,
        "Batch upload failed",
        () => fetch(`${BASE_URL}${path}`, {
            method: "POST",
            headers: { ...getAuthHeaders() },
            body: form,
        }),
    );
}

export async function getJob(jobId: string) {
    const path = `/api/v1/jobs/${jobId}`;
    return timedRequest<{ job: { id: string; status: string; result?: { rows?: number } } }>(
        path,
        "Job fetch failed",
        () => fetch(`${BASE_URL}${path}`, { headers: { ...getAuthHeaders() } }),
    );
}

export async function downloadBatchReport(jobId: string) {
    const path = `/api/v1/jobs/${jobId}/download`;
    const startedAt = performance.now();
    window.dispatchEvent(new CustomEvent("app:api-start", { detail: { path } }));
    try {
        const res = await fetch(`${BASE_URL}${path}`, { headers: { ...getAuthHeaders() } });
        const elapsedMs = Math.round(performance.now() - startedAt);
        if (elapsedMs >= SLOW_CALL_MS) {
            trackEvent("api_slow", { path, elapsedMs });
            window.dispatchEvent(new CustomEvent("app:api-slow", { detail: { path, elapsedMs } }));
        }
        if (!res.ok) {
            const detail = await res.text().catch(() => "Unknown error");
            trackEvent("api_error", { path, status: res.status, detail });
            throw new Error(`Download failed (${res.status}): ${detail}`);
        }
        return await res.text();
    } finally {
        window.dispatchEvent(new CustomEvent("app:api-end", { detail: { path } }));
    }
}