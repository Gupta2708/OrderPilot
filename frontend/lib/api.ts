import type { RunDetail, RunState, RunSummary, Supervisor } from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      cache: "no-store",
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, "Cannot reach the API. Is the backend running on port 8000?");
  }

  if (!response.ok) {
    throw new ApiError(response.status, await readError(response));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      // FastAPI validation errors.
      return detail
        .map((item: { loc?: unknown[]; msg?: string }) => {
          const field = Array.isArray(item.loc) ? item.loc.slice(1).join(".") : "";
          return field ? `${field}: ${item.msg}` : item.msg;
        })
        .join("; ");
    }
  } catch {
    // fall through
  }
  return `Request failed with status ${response.status}`;
}

export const api = {
  listSupervisors: () => request<Supervisor[]>("/api/supervisors"),

  createSupervisor: (payload: {
    name: string;
    base_instruction: string;
    allowed_actions: string[];
    wake_aggressiveness: string;
    default_wake_minutes: number;
    max_age_minutes: number;
  }) =>
    request<Supervisor>("/api/supervisors", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  listRuns: () => request<RunSummary[]>("/api/runs"),

  getRun: (runId: string) => request<RunDetail>(`/api/runs/${runId}`),

  getRunState: (runId: string) => request<RunState>(`/api/runs/${runId}/state`),

  createRun: (payload: {
    order_id: string;
    supervisor_id: string;
    order_context: Record<string, unknown>;
    initial_instructions: string[];
  }) =>
    request<RunSummary>("/api/runs", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  sendEvent: (runId: string, type: string, payload: Record<string, unknown> = {}) =>
    request<{ event_id: string }>(`/api/runs/${runId}/events`, {
      method: "POST",
      body: JSON.stringify({ type, payload }),
    }),

  addInstruction: (runId: string, instruction: string) =>
    request<{ run_id: string }>(`/api/runs/${runId}/instructions`, {
      method: "POST",
      body: JSON.stringify({ instruction }),
    }),

  pause: (runId: string) => request(`/api/runs/${runId}/pause`, { method: "POST" }),

  resume: (runId: string) => request(`/api/runs/${runId}/resume`, { method: "POST" }),

  terminate: (runId: string, reason: string) =>
    request(`/api/runs/${runId}/terminate`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
};
