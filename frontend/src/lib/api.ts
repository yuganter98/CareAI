const API_BASE = "http://localhost:8000/api/v1";

export async function fetchWithAuth(endpoint: string, options: RequestInit = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...options.headers,
  } as Record<string, string>;

  // When uploading FormData let the browser set the multipart boundary automatically
  if (options.body instanceof FormData) {
    delete headers["Content-Type"];
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
    credentials: "include", // sends httpOnly cookie on every request
  });

  // Session expired or invalid — bounce to login (unless already there)
  if (response.status === 401 || response.status === 403) {
    if (typeof window !== "undefined" && window.location.pathname !== "/login" && window.location.pathname !== "/register") {
      window.location.href = "/login";
    }
    throw new Error("Session expired. Redirecting to login...");
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `API Request failed: ${response.statusText}`);
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}

/**
 * CARE-AI SDK
 * Strictly-typed HTTP wrappers mapping one-to-one with the Phase 1-5 FastAPI Python codebase.
 */
export const CareAI = {
  // --------- AUTH & PROFILE ---------
  login: (credentials: URLSearchParams) => {
    // OAuth2PasswordRequestForm demands classic x-www-form-urlencoded format
    return fetchWithAuth("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: credentials,
    });
  },

  logout: () => {
    return fetchWithAuth("/auth/logout", { method: "POST" });
  },

  getProfile: () => {
    return fetchWithAuth("/users/me", { method: "GET" });
  },

  updateProfile: (data: any) => {
    return fetchWithAuth("/users/me", {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },

  // --------- FILE ORCHESTRATION ---------
  uploadReport: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("file_type", file.type.includes("pdf") ? "pdf" : "image");

    return fetchWithAuth("/reports/upload", {
      method: "POST",
      body: formData,
    });
  },

  getMyReports: () => {
    return fetchWithAuth("/reports/my-reports", { method: "GET" });
  },

  deleteReport: (reportId: string) => {
    return fetchWithAuth(`/reports/${reportId}`, { method: "DELETE" });
  },

  // --------- AGENT OBSERVABILITY ---------
  getAgentLogs: (reportId: string) => {
    return fetchWithAuth(`/agents/logs/${reportId}`, { method: "GET" });
  },

  // --------- AI MULTI-AGENT STATE GRAPH ---------
  processMultiAgentAI: (reportId: string) => {
    return fetchWithAuth("/ai/process-report", {
      method: "POST",
      body: JSON.stringify({ report_id: reportId }),
    });
  },

  queryRAG: (reportId: string, question: string) => {
    return fetchWithAuth("/ai/agent-query", {
      method: "POST",
      body: JSON.stringify({ report_id: reportId, question }),
    });
  },

  // --------- ANALYTICS DASHBOARD ---------
  getChartTrends: () => {
    return fetchWithAuth("/metrics/trends", { method: "GET" });
  },

  getInsights: () => {
    return fetchWithAuth("/ai/health-insights", { method: "GET" });
  },

  // --------- ACTION AGENTS ---------
  getMedications: () => {
    return fetchWithAuth("/medications/list", { method: "GET" });
  },

  addMedication: (data: { medicine_name: string; dosage: string; time: string; start_date: string }) => {
    return fetchWithAuth("/medications/add", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  triggerPanicButton: () => {
    return fetchWithAuth("/emergency/trigger-alert", { method: "POST" });
  },

  // --------- HEALTH COPILOT ---------
  copilotChat: (question: string, history?: { role: string; content: string }[]) => {
    return fetchWithAuth("/ai/copilot-chat", {
      method: "POST",
      body: JSON.stringify({ question, history: history || [] }),
    });
  },
};
