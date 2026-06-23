import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { AuditEvent, ChatMessage, Observability, Project } from "../types";
import {
  analyzeWebsite,
  buildProject,
  type BuildConfirmation,
  type BuildProgress,
  type WebsiteAnalysis,
} from "../services/projectService";
import {
  askAssistant,
  askOrchestrator,
  streamAgent,
  type AgentEvent,
  type AssistantMode,
} from "../services/assistantApi";
import {
  getAuth,
  hasAny,
  login as loginRequest,
  logout as logoutRequest,
  type AuthSession,
  type SeatLogin,
} from "../services/authService";
import {
  listWorkspaces,
  getWorkspace,
  deleteWorkspace as deleteWorkspaceRequest,
  type WorkspaceSummary,
} from "../services/workspaceApi";

interface AppState {
  auth: AuthSession | null;
  sessionId: string;
  login: (seat: SeatLogin) => Promise<boolean>;
  switchSeat: (seat: SeatLogin) => Promise<boolean>;
  logout: () => void;
  can: (...permissions: string[]) => boolean;
  project: Project | null;
  building: boolean;
  buildSteps: BuildProgress[];
  analyzing: boolean;
  preview: WebsiteAnalysis | null;
  analyzeError: string | null;
  lastUrl: string;
  messages: ChatMessage[];
  thinking: boolean;
  liveActivity: string[];
  mode: AssistantMode;
  maskNames: boolean;
  justBuilt: boolean;
  enterWorkspace: () => void;
  workspaces: WorkspaceSummary[];
  newBuild: boolean;
  loadWorkspaces: () => Promise<void>;
  openWorkspace: (id: string) => Promise<boolean>;
  deleteWorkspace: (id: string) => Promise<void>;
  startNewBuild: () => void;
  closeWorkspace: () => void;
  analyzeUrl: (url: string) => Promise<void>;
  confirmBuild: (confirmation: BuildConfirmation) => Promise<void>;
  cancelPreview: () => void;
  ask: (question: string) => Promise<void>;
  setMode: (m: AssistantMode) => void;
  reset: () => void;
  setMaskNames: (v: boolean) => void;
  toggleConnectorMasking: (connector: "crm" | "erp" | "ticketing") => void;
}

const AppContext = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  // The active workspace is intentionally NOT persisted across reloads. Workspaces
  // live on the backend (listed/opened via the API), so after login the user always
  // lands on the Workspaces picker and explicitly opens one.
  const [project, setProject] = useState<Project | null>(null);
  const [building, setBuilding] = useState(false);
  const [justBuilt, setJustBuilt] = useState(false);
  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([]);
  const [newBuild, setNewBuild] = useState(false);
  const [buildSteps, setBuildSteps] = useState<BuildProgress[]>([]);
  const [analyzing, setAnalyzing] = useState(false);
  const [preview, setPreview] = useState<WebsiteAnalysis | null>(null);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  const [lastUrl, setLastUrl] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [thinking, setThinking] = useState(false);
  const [liveActivity, setLiveActivity] = useState<string[]>([]);
  const [mode, setMode] = useState<AssistantMode>("agent");
  const [maskNames, setMaskNames] = useState(false);
  const [auth, setAuth] = useState<AuthSession | null>(() => getAuth());

  const login = useCallback(async (seat: SeatLogin): Promise<boolean> => {
    const session = await loginRequest(seat);
    if (session) setAuth(session);
    return Boolean(session);
  }, []);

  const can = useCallback(
    (...permissions: string[]) => hasAny(permissions, auth),
    [auth],
  );

  // A per-browser session id so the agent can use conversation memory. It is
  // deliberately rotated whenever the seat changes (see switchSeat) so each seat
  // gets a clean, scoped conversation — privileged turns never bleed into a
  // lower-privilege seat's context.
  const newSessionId = () =>
    `sess-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const [sessionId, setSessionId] = useState<string>(() => {
    try {
      const k = "stacklaunch-session";
      let s = localStorage.getItem(k);
      if (!s) {
        s = newSessionId();
        localStorage.setItem(k, s);
      }
      return s;
    } catch {
      return newSessionId();
    }
  });

  // Switch seat in place: re-mint the scoped API key for the new seat while
  // keeping the active workspace, but start a fresh conversation so the new
  // seat's RBAC scope (tier + department + clearance) is the only thing in play.
  // This makes the governance story a one-tap toggle instead of a full re-login.
  const switchSeat = useCallback(
    async (seat: SeatLogin): Promise<boolean> => {
      const session = await loginRequest(seat);
      if (!session) return false;
      setAuth(session);
      setMessages([]);
      const fresh = newSessionId();
      setSessionId(fresh);
      try {
        localStorage.setItem("stacklaunch-session", fresh);
      } catch {
        /* non-fatal: memory still works for this tab */
      }
      return true;
    },
    [],
  );

  const persist = useCallback((p: Project | null) => {
    setProject(p);
  }, []);

  // Step 1: scan + classify the site, then show the confirmation screen.
  const analyzeUrl = useCallback(async (url: string) => {
    setAnalyzing(true);
    setPreview(null);
    setAnalyzeError(null);
    setLastUrl(url);
    try {
      const result = await analyzeWebsite(url);
      setPreview(result);
    } catch (err) {
      setAnalyzeError(err instanceof Error ? err.message : "Failed to scan the website.");
    } finally {
      setAnalyzing(false);
    }
  }, []);

  const cancelPreview = useCallback(() => {
    setPreview(null);
    setAnalyzing(false);
    setAnalyzeError(null);
  }, []);

  // Step 2: build the full stack from the confirmed (possibly corrected) values.
  // The already-scanned content (preview.scan) is forwarded so the backend builds
  // from it without re-crawling the site.
  const confirmBuild = useCallback(
    async (confirmation: BuildConfirmation) => {
      if (!preview) return;
      const scan = preview.scan;
      setBuilding(true);
      setBuildSteps([]);
      setMessages([]);
      setPreview(null);
      try {
        const built = await buildProject(
          confirmation,
          scan,
          (p) => setBuildSteps((prev) => [...prev, p]),
        );
        persist(built);
        // Don't auto-enter the workspace — show the "Stack ready" confirmation
        // so building and trying the stack stay clearly separated.
        setJustBuilt(true);
      } finally {
        setBuilding(false);
      }
    },
    [persist, preview],
  );

  // Explicit handoff from the build phase into the workspace ("try the stack").
  const enterWorkspace = useCallback(() => setJustBuilt(false), []);

  // --- Multi-workspace: list, open, delete saved stacks ---
  const loadWorkspaces = useCallback(async () => {
    setWorkspaces(await listWorkspaces());
  }, []);

  const openWorkspace = useCallback(
    async (id: string): Promise<boolean> => {
      const full = await getWorkspace(id);
      if (!full) return false;
      persist(full);
      setMessages([]);
      setJustBuilt(false);
      setNewBuild(false);
      return true;
    },
    [persist],
  );

  const deleteWorkspace = useCallback(
    async (id: string) => {
      await deleteWorkspaceRequest(id);
      setWorkspaces((prev) => prev.filter((w) => w.id !== id));
      // If we deleted the active workspace, drop back out of it.
      if (project?.id === id) persist(null);
    },
    [persist, project],
  );

  // Begin building a brand-new stack (skip the workspace picker).
  const startNewBuild = useCallback(() => setNewBuild(true), []);

  // Leave the active workspace and return to the workspace picker.
  const closeWorkspace = useCallback(() => {
    persist(null);
    setMessages([]);
    setJustBuilt(false);
    setNewBuild(false);
  }, [persist]);

  // Reasoning, governance metadata, and metrics are computed on the backend.
  // In "agent" mode we stream the tool-calls live; "multi" uses the supervisor
  // orchestrator; "single" is the original one-shot pipeline.
  const ask = useCallback(
    async (question: string) => {
      if (!project) return;
      const userMsg: ChatMessage = {
        id: `m-${Date.now()}-u`,
        role: "user",
        content: question,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setThinking(true);
      setLiveActivity([]);

      const activity: string[] = [];
      const onEvent = (e: AgentEvent) => {
        let line: string | null = null;
        if (e.type === "tool_call") line = `→ ${e.name}`;
        else if (e.type === "delegate") line = `→ ${e.specialist} · ${e.question ?? ""}`;
        else if (e.type === "tool_result") {
          const res = e.result as { error?: string } | undefined;
          if (res?.error === "permission_denied") line = `⛔ ${e.name} — access denied (role)`;
          else if (res?.error === "department_scope") line = `⛔ ${e.name} — out of department scope`;
          else if (res?.error === "clearance_required") line = `⛔ ${e.name} — clearance too low`;
        }
        if (line) {
          activity.push(line);
          setLiveActivity([...activity]);
        }
      };

      let result =
        mode === "agent"
          ? await streamAgent(question, project, onEvent, sessionId)
          : mode === "multi"
            ? await askOrchestrator(question, project, sessionId)
            : await askAssistant(question, project);
      // Fall back to the one-shot pipeline if the agentic path is unavailable.
      if (!result && mode !== "single") result = await askAssistant(question, project);

      setThinking(false);
      setLiveActivity([]);

      if (!result) {
        const errorMsg: ChatMessage = {
          id: `m-${Date.now()}-a`,
          role: "assistant",
          content:
            "I couldn't reach the assistant service. Make sure the backend is running (uvicorn on port 8000) and try again.",
          timestamp: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, errorMsg]);
        return;
      }

      const traceFromResult =
        result.specialistsUsed?.map((s) => `→ ${s}`) ??
        result.toolsUsed?.map((t) => `→ ${t}`) ??
        [];

      const assistantMsg: ChatMessage = {
        id: `m-${Date.now()}-a`,
        role: "assistant",
        content: result.content,
        sources: result.sources,
        computedFrom: result.computedFrom,
        guardrailNote: result.guardrailNote ?? undefined,
        activity: activity.length ? activity : traceFromResult,
        mode: result.mode,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMsg]);

      const newObs: Observability = { ...project.observability };
      (Object.keys(result.observabilityDelta) as (keyof Observability)[]).forEach((k) => {
        newObs[k] = (newObs[k] ?? 0) + (result.observabilityDelta[k] ?? 0);
      });
      const newAudit: AuditEvent[] = result.auditEvents ?? [];
      persist({
        ...project,
        observability: newObs,
        audit: [...project.audit, ...newAudit],
      });
    },
    [project, persist, mode, sessionId],
  );

  const toggleConnectorMasking = useCallback(
    (connector: "crm" | "erp" | "ticketing") => {
      if (!project) return;
      const c = project.connectors[connector];
      persist({
        ...project,
        connectors: {
          ...project.connectors,
          [connector]: { ...c, piiMasking: !c.piiMasking },
        },
      });
    },
    [project, persist],
  );

  const reset = useCallback(() => {
    persist(null);
    setMessages([]);
    setBuildSteps([]);
    setPreview(null);
    setAnalyzeError(null);
    setJustBuilt(false);
    // "Build another stack" → go straight to the scan step.
    setNewBuild(true);
  }, [persist]);

  const logout = useCallback(() => {
    logoutRequest();
    setAuth(null);
    setMessages([]);
    setJustBuilt(false);
    setNewBuild(false);
    setWorkspaces([]);
  }, []);

  const value = useMemo<AppState>(
    () => ({
      auth,
      sessionId,
      login,
      switchSeat,
      logout,
      can,
      project,
      building,
      buildSteps,
      analyzing,
      preview,
      analyzeError,
      lastUrl,
      messages,
      thinking,
      liveActivity,
      mode,
      maskNames,
      justBuilt,
      enterWorkspace,
      workspaces,
      newBuild,
      loadWorkspaces,
      openWorkspace,
      deleteWorkspace,
      startNewBuild,
      closeWorkspace,
      analyzeUrl,
      confirmBuild,
      cancelPreview,
      ask,
      setMode,
      reset,
      setMaskNames,
      toggleConnectorMasking,
    }),
    [
      auth,
      sessionId,
      login,
      switchSeat,
      logout,
      can,
      project,
      building,
      justBuilt,
      enterWorkspace,
      workspaces,
      newBuild,
      loadWorkspaces,
      openWorkspace,
      deleteWorkspace,
      startNewBuild,
      closeWorkspace,
      buildSteps,
      analyzing,
      preview,
      analyzeError,
      lastUrl,
      messages,
      thinking,
      liveActivity,
      mode,
      maskNames,
      analyzeUrl,
      confirmBuild,
      cancelPreview,
      ask,
      reset,
      toggleConnectorMasking,
    ],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}
