import type { ChatResponse, DashboardOverview } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_SCISCOPE_API_BASE ?? "http://localhost:8000";

function readBackendMessage(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") {
    return null;
  }

  const record = payload as Record<string, unknown>;
  for (const key of ["detail", "message", "error"]) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) {
      return value;
    }
  }

  return null;
}

async function readError(response: Response, fallback: string): Promise<Error> {
  const status = `${response.status} ${response.statusText}`.trim();
  const prefix = `${fallback} (${status})`;

  try {
    const contentType = response.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      const message = readBackendMessage(await response.json());
      return new Error(message ? `${prefix}: ${message}` : prefix);
    }

    const text = await response.text();
    const message = text.trim();
    return new Error(message ? `${prefix}: ${message}` : prefix);
  } catch {
    return new Error(prefix);
  }
}

export async function fetchDashboardOverview(): Promise<DashboardOverview> {
  const response = await fetch(`${API_BASE}/api/dashboard/overview`, { cache: "no-store" });

  if (!response.ok) {
    throw await readError(response, "Failed to load dashboard overview");
  }

  return response.json();
}

export async function askQuestion(question: string): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question })
  });

  if (!response.ok) {
    throw await readError(response, "Failed to ask SciScope");
  }

  return response.json();
}
