import type {
  ChatResponse,
  DashboardOverview,
  GraphResponse,
  RecommendResponse,
  SearchResponse,
  TrendsResponse
} from "@/types";

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

export async function searchPapers(query: string): Promise<SearchResponse> {
  const response = await fetch(`${API_BASE}/api/search?q=${encodeURIComponent(query)}`, {
    cache: "no-store"
  });

  if (!response.ok) {
    throw await readError(response, "Failed to search papers");
  }

  return response.json();
}

export async function fetchTrends(keyword?: string): Promise<TrendsResponse> {
  const suffix = keyword ? `?keyword=${encodeURIComponent(keyword)}` : "";
  const response = await fetch(`${API_BASE}/api/trends${suffix}`, { cache: "no-store" });

  if (!response.ok) {
    throw await readError(response, "Failed to load trends");
  }

  return response.json();
}

export async function fetchRecommendations(paperId: string): Promise<RecommendResponse> {
  const response = await fetch(`${API_BASE}/api/recommend?paper_id=${encodeURIComponent(paperId)}`, {
    cache: "no-store"
  });

  if (!response.ok) {
    throw await readError(response, "Failed to load recommendations");
  }

  return response.json();
}

export async function fetchGraph(type: string, center?: string): Promise<GraphResponse> {
  const params = new URLSearchParams({ type });
  if (center) {
    params.set("center", center);
  }
  const response = await fetch(`${API_BASE}/api/graph?${params.toString()}`, { cache: "no-store" });

  if (!response.ok) {
    throw await readError(response, "Failed to load graph");
  }

  return response.json();
}
