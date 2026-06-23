import { authHeaders } from "./authService";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export interface SovereigntyPosture {
  dataRegion: string;
  strict: boolean;
  llm: {
    provider: string | null;
    model: string | null;
    host: string | null;
    residency: { code: string; label: string };
  };
  search: { engine: string; host: string | null };
  egress: {
    scanSsrfGuard: boolean;
    allowPrivateScan: boolean;
    externalLlmAllowed: boolean;
    knownExternalHosts: string[];
  };
  dataAtRest: { store: string; appDb: string; auditDb: string };
  controls: {
    auditHashChained: boolean;
    auditHmacSigned: boolean;
    piiRedaction: boolean;
    promptInjectionDefense: boolean;
    rbac: boolean;
    requireAuth: boolean;
  };
}

export interface HealthInfo {
  status: string;
  llm: { enabled: boolean; provider: string | null; model: string | null; host: string | null };
  searxng: boolean;
}

export async function fetchSovereignty(): Promise<SovereigntyPosture | null> {
  try {
    const resp = await fetch(`${API_BASE}/api/sovereignty`, { headers: authHeaders() });
    if (!resp.ok) return null;
    return (await resp.json()) as SovereigntyPosture;
  } catch {
    return null;
  }
}

export async function fetchHealth(): Promise<HealthInfo | null> {
  try {
    const resp = await fetch(`${API_BASE}/api/health`, { headers: authHeaders() });
    if (!resp.ok) return null;
    return (await resp.json()) as HealthInfo;
  } catch {
    return null;
  }
}
