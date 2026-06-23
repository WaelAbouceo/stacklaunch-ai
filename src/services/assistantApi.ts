import type {
  AuditEvent,
  Observability,
  Project,
  SourceType,
} from "../types";
import { authHeaders } from "./authService";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

const JSON_HEADERS = () => authHeaders({ "Content-Type": "application/json" });

export type AssistantMode = "agent" | "multi" | "single";

// A live event emitted by the streaming agent (tool-calling) endpoint.
export interface AgentEvent {
  type:
    | "step"
    | "tool_call"
    | "tool_result"
    | "delegate"
    | "delegate_result"
    | "supervisor_step"
    | "final"
    | "error";
  name?: string;
  specialist?: string;
  question?: string;
  arguments?: Record<string, unknown>;
  step?: number;
  message?: string;
  [k: string]: unknown;
}

// The full assistant result, computed entirely on the backend (tool calls,
// governance metadata, grounded answer, audit + metrics).
export interface AskResponse {
  content: string;
  sources: SourceType[];
  computedFrom: string[];
  guardrailNote?: string | null;
  observabilityDelta: Partial<Observability>;
  auditEvents: AuditEvent[];
  usedSearch: boolean;
  toolsUsed?: string[];
  specialistsUsed?: string[];
  mode?: string;
}

function normalize(data: Record<string, unknown>): AskResponse | null {
  if (!data?.content) return null;
  return {
    content: String(data.content),
    sources: (data.sources ?? []) as SourceType[],
    computedFrom: (data.computedFrom ?? []) as string[],
    guardrailNote: (data.guardrailNote ?? null) as string | null,
    observabilityDelta: (data.observabilityDelta ?? {}) as Partial<Observability>,
    auditEvents: (data.auditEvents ?? []) as AuditEvent[],
    usedSearch: Boolean(data.usedSearch),
    toolsUsed: (data.toolsUsed ?? []) as string[],
    specialistsUsed: (data.specialistsUsed ?? []) as string[],
    mode: data.mode as string | undefined,
  };
}

// Single-shot deterministic+LLM pipeline (original endpoint).
export async function askAssistant(
  question: string,
  project: Project,
): Promise<AskResponse | null> {
  try {
    const resp = await fetch(`${API_BASE}/api/ask`, {
      method: "POST",
      headers: JSON_HEADERS(),
      body: JSON.stringify({ question, project, allowSearch: true }),
    });
    if (!resp.ok) return null;
    return normalize(await resp.json());
  } catch {
    return null;
  }
}

// Multi-agent orchestrator (supervisor + specialists). JSON response.
export async function askOrchestrator(
  question: string,
  project: Project,
  sessionId?: string,
): Promise<AskResponse | null> {
  try {
    const resp = await fetch(`${API_BASE}/api/orchestrate`, {
      method: "POST",
      headers: JSON_HEADERS(),
      body: JSON.stringify({ question, project, allowSearch: true, sessionId }),
    });
    if (!resp.ok) return null;
    return normalize(await resp.json());
  } catch {
    return null;
  }
}

// Streaming tool-calling agent. Invokes onEvent for each SSE event and resolves
// with the final assembled result (from the `final` event).
export async function streamAgent(
  question: string,
  project: Project,
  onEvent: (event: AgentEvent) => void,
  sessionId?: string,
): Promise<AskResponse | null> {
  let final: AskResponse | null = null;
  try {
    const resp = await fetch(`${API_BASE}/api/agent/stream`, {
      method: "POST",
      headers: JSON_HEADERS(),
      body: JSON.stringify({ question, project, allowSearch: true, sessionId }),
    });
    if (!resp.ok || !resp.body) return null;

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split("\n\n");
      buffer = chunks.pop() ?? "";
      for (const chunk of chunks) {
        const line = chunk.split("\n").find((l) => l.startsWith("data:"));
        if (!line) continue;
        try {
          const event = JSON.parse(line.slice(5).trim()) as AgentEvent;
          onEvent(event);
          if (event.type === "final") final = normalize(event as Record<string, unknown>);
        } catch {
          /* ignore malformed event */
        }
      }
    }
    return final;
  } catch {
    return final;
  }
}

// --- LLM-as-judge validation ------------------------------------------------

export interface TurnGrade {
  available: boolean;
  verdict?: "pass" | "fail";
  groundedness?: number;
  relevance?: number;
  safetyPass?: boolean;
  piiLeak?: boolean;
  refusalCorrect?: boolean | null;
  unsupportedClaims?: string[];
  rationale?: string;
  reason?: string;
}

export interface ValidationReport {
  sessionId: string;
  projectId?: string | null;
  turnsValidated: number;
  turns: { question: string; answerPreview: string; judge: TurnGrade }[];
  summary: {
    available: boolean;
    judged?: number;
    total?: number;
    passed?: number;
    passRate?: number;
    avgGroundedness?: number;
    avgRelevance?: number;
    piiLeaks?: number;
    reason?: string;
  };
}

// Validate a stored conversation with the LLM judge (per-turn grounding/safety).
export async function validateConversation(
  sessionId: string,
): Promise<ValidationReport | null> {
  try {
    const resp = await fetch(
      `${API_BASE}/api/conversations/${encodeURIComponent(sessionId)}/validate`,
      { method: "POST", headers: JSON_HEADERS() },
    );
    if (!resp.ok) return null;
    return (await resp.json()) as ValidationReport;
  } catch {
    return null;
  }
}

export interface JudgedEvalReport {
  passed: number;
  total: number;
  passRate: number;
  cases: {
    question: string;
    passed: boolean;
    grounded: boolean;
    refused: boolean;
    expectedRefusal: boolean;
    intent: string;
    judge?: TurnGrade;
  }[];
  judge?: {
    available: boolean;
    judged?: number;
    passed?: number;
    passRate?: number;
    avgGroundedness?: number;
    avgRelevance?: number;
    piiLeaks?: number;
    reason?: string;
  };
}

// Run the golden-set evals, optionally with the LLM-as-judge quality pass.
export async function runEvals(judge = false): Promise<JudgedEvalReport | null> {
  try {
    const resp = await fetch(`${API_BASE}/api/evals${judge ? "?judge=true" : ""}`, {
      headers: authHeaders(),
    });
    if (!resp.ok) return null;
    return (await resp.json()) as JudgedEvalReport;
  } catch {
    return null;
  }
}

// --- Executive briefing + Next Best Actions ---------------------------------

export interface Kpi {
  label: string;
  value: string;
  sub?: string;
  tone: "neutral" | "positive" | "warning" | "danger";
}

export interface NextBestAction {
  id: string;
  title: string;
  severity: "high" | "medium" | "low";
  metric: string;
  rationale: string;
  suggestedPrompt: string;
  sources: SourceType[];
}

export interface Briefing {
  role: string;
  company: string;
  hasData: boolean;
  narrative: string;
  siteSummary?: string;
  kpis: Kpi[];
  actions: NextBestAction[];
  suggestedQuestions: string[];
}

export async function fetchBriefing(project: Project): Promise<Briefing | null> {
  try {
    const resp = await fetch(`${API_BASE}/api/briefing`, {
      method: "POST",
      headers: JSON_HEADERS(),
      body: JSON.stringify({ project }),
    });
    if (!resp.ok) return null;
    return (await resp.json()) as Briefing;
  } catch {
    return null;
  }
}
