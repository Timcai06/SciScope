import type { ChatResponse, DashboardOverview } from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_SCISCOPE_API_BASE ?? "http://localhost:8000";

export async function fetchDashboardOverview(): Promise<DashboardOverview> {
  const response = await fetch(`${API_BASE}/api/dashboard/overview`, { cache: "no-store" });

  if (!response.ok) {
    throw new Error("Failed to load dashboard overview");
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
    throw new Error("Failed to ask SciScope");
  }

  return response.json();
}
