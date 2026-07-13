export type AnalyticsEventName =
  | "auth_login"
  | "auth_logout"
  | "role_changed"
  | "predict_requested"
  | "simulate_requested"
  | "scenario_saved"
  | "scenario_loaded"
  | "scenario_compared"
  | "feedback_submitted"
  | "modal_opened"
  | "command_palette_opened"
  | "command_executed"
  | "api_error"
  | "api_slow";

interface AnalyticsEvent {
  name: AnalyticsEventName;
  timestamp: number;
  payload?: Record<string, string | number | boolean | null>;
}

const STORAGE_KEY = "churn_ui_analytics_events";
const MAX_EVENTS = 250;

function readEvents(): AnalyticsEvent[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as AnalyticsEvent[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeEvents(events: AnalyticsEvent[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(events.slice(-MAX_EVENTS)));
}

export function trackEvent(name: AnalyticsEventName, payload?: Record<string, string | number | boolean | null>) {
  const events = readEvents();
  events.push({ name, payload, timestamp: Date.now() });
  writeEvents(events);
}

export function getEventCount(name: AnalyticsEventName): number {
  return readEvents().filter((event) => event.name === name).length;
}

export function getRecentEvents(limit = 30): AnalyticsEvent[] {
  return readEvents().slice(-limit).reverse();
}
