import { useEffect, useState } from "react";
import { useApp } from "../store/AppContext";
import { fetchSeats, type AdminTier } from "../services/authService";
import type { ClearanceLevel, OrgDepartment } from "../types";
import { tierMeta, clearanceColor } from "../personas";
import logo from "../assets/logo.png";

// The layers a StackLaunch project provisions — shown on the brand panel so a
// technical viewer sees the whole architecture before signing in.
const STACK_LAYERS: { icon: string; name: string; detail: string }[] = [
  { icon: "📚", name: "Website Knowledge Base", detail: "Crawled, chunked & BM25-indexed with citations" },
  { icon: "🔌", name: "CRM · ERP · Ticketing", detail: "Governed connectors with structured query" },
  { icon: "✦", name: "Agentic RAG Assistant", detail: "Multi-tool, supervised reasoning loop" },
  { icon: "🏛", name: "Org-aware RBAC", detail: "Departments · clearance levels · scoped keys" },
  { icon: "🛡", name: "Audit + Guardrails", detail: "Hash-chained log · PII redaction · injection defense" },
  { icon: "📈", name: "Observability", detail: "Token, cost & latency telemetry" },
];

const ORG_WIDE: { tier: AdminTier; clearance: ClearanceLevel }[] = [
  { tier: "system", clearance: "restricted" },
  { tier: "external", clearance: "public" },
];

const DEPT_TIERS: { tier: AdminTier; clearance: ClearanceLevel; label: string }[] = [
  { tier: "department", clearance: "restricted", label: "Department Head" },
  { tier: "group", clearance: "confidential", label: "Group Lead" },
  { tier: "member", clearance: "internal", label: "Staff" },
];

function prettyIndustry(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function ClassBadge({ level }: { level: ClearanceLevel }) {
  const c = clearanceColor(level);
  return (
    <span
      className="class-badge"
      style={{
        color: c,
        borderColor: `color-mix(in srgb, ${c} 45%, transparent)`,
        background: `color-mix(in srgb, ${c} 12%, transparent)`,
      }}
    >
      {level}
    </span>
  );
}

type Brand = { id?: string; company?: string; isNew?: boolean };

export default function Login() {
  const { auth, can, login, workspaces, loadWorkspaces, openWorkspace, startNewBuild } = useApp();
  const [step, setStep] = useState<"workspace" | "seat">("workspace");
  const [brand, setBrand] = useState<Brand | null>(null);
  const [departments, setDepartments] = useState<OrgDepartment[]>([]);
  const [dept, setDept] = useState<string>("");
  const [pending, setPending] = useState<string | null>(null);
  const [opening, setOpening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadingWs, setLoadingWs] = useState(true);
  const [loadingSeats, setLoadingSeats] = useState(false);

  useEffect(() => {
    setLoadingWs(true);
    void loadWorkspaces().finally(() => setLoadingWs(false));
  }, [loadWorkspaces]);

  const enterExisting = async (id: string) => {
    setOpening(true);
    setError(null);
    const ok = await openWorkspace(id);
    if (!ok) {
      setError("Couldn't open that workspace. Is the backend running?");
      setOpening(false);
    }
  };

  // Load the workspace's org chart (departments) for the seat picker.
  const loadOrg = async (workspaceId: string | null) => {
    setLoadingSeats(true);
    const data = await fetchSeats(workspaceId);
    setLoadingSeats(false);
    const depts = data?.org?.departments ?? [];
    setDepartments(depts);
    setDept(depts[0]?.name ?? "");
  };

  // Intent: OPEN an existing workspace. If already signed in, go straight in.
  const openBrand = (b: Brand) => {
    setError(null);
    if (auth) {
      void enterExisting(b.id!);
      return;
    }
    setBrand(b);
    setStep("seat");
    void loadOrg(b.id ?? null);
  };

  // Intent: PROVISION a new stack — only a System Administrator can stand one up.
  const provisionNew = () => {
    setError(null);
    if (auth && can("manage:connectors", "write:all")) {
      startNewBuild();
      return;
    }
    setBrand({ isNew: true });
    setStep("seat");
  };

  const chooseSeat = async (tier: AdminTier, department: string | null) => {
    if (pending) return;
    setPending(`${tier}:${department ?? ""}`);
    setError(null);
    const ok = await login({ tier, department, workspaceId: brand?.id ?? null });
    if (!ok) {
      setError("Sign-in failed. Make sure the backend is running (uvicorn on port 8000).");
      setPending(null);
      return;
    }
    if (brand?.isNew) {
      startNewBuild();
    } else if (brand?.id) {
      const ok2 = await openWorkspace(brand.id);
      if (!ok2) {
        setError("Signed in, but couldn't open that workspace.");
        setPending(null);
      }
    }
  };

  const backToWorkspace = () => {
    setStep("workspace");
    setBrand(null);
    setDepartments([]);
    setError(null);
  };

  const SeatCard = ({
    tier,
    clearance,
    department,
    label,
  }: {
    tier: AdminTier;
    clearance: ClearanceLevel;
    department: string | null;
    label?: string;
  }) => {
    const m = tierMeta(tier);
    const busy = pending === `${tier}:${department ?? ""}`;
    return (
      <button
        className={`persona-card${busy ? " is-busy" : ""}`}
        style={{ ["--accent" as string]: m.accent }}
        onClick={() => chooseSeat(tier, department)}
        disabled={pending !== null}
      >
        <div className="persona-icon">{m.icon}</div>
        <div className="persona-name">{label ?? (tier === "system" ? "System Administrator" : "External User")}</div>
        <div className="persona-desc">{m.summary}</div>
        <div className="persona-access">
          <ClassBadge level={clearance} /> clearance
        </div>
        <span className="persona-cta">{busy ? "Signing in…" : "Continue →"}</span>
      </button>
    );
  };

  return (
    <div className="auth">
      <section className="auth-brand">
        <div className="auth-grid" aria-hidden />

        <header className="auth-head">
          <img className="auth-logo" src={logo} alt="StackLaunch AI logo" />
          <div className="auth-word">
            <span className="gradient-text">StackLaunch</span> AI
          </div>
          <span className="auth-eyebrow">
            <span className="login-dot" /> Governed AI for regulated industries
          </span>
        </header>

        <div className="auth-pitch">
          <h2>
            From a URL to a <span className="gradient-text">governed AI stack</span>.
          </h2>
          <p>
            Point StackLaunch at any website and it provisions a complete, org-aware
            enterprise AI layer — not a chatbot. Every layer below is generated, governed,
            and enforced server-side.
          </p>
          <div className="auth-stack">
            {STACK_LAYERS.map((l) => (
              <div className="auth-layer" key={l.name}>
                <span className="auth-layer-ico">{l.icon}</span>
                <div>
                  <div className="auth-layer-name">{l.name}</div>
                  <div className="auth-layer-detail">{l.detail}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <footer className="auth-foot">
          Org-aware RBAC · Data classification · Hash-chained audit · PII redaction · LLM-as-judge evals
        </footer>
      </section>

      <section className="auth-panel">
        <div className="auth-panel-inner">
          <div className="auth-mobile-brand">
            <img src={logo} alt="StackLaunch AI logo" />
            <div className="auth-word">
              <span className="gradient-text">StackLaunch</span> AI
            </div>
          </div>

          <div className="auth-steps">
            <span className={`auth-step ${step === "workspace" ? "active" : "done"}`}>1 · Workspace</span>
            <span className="auth-step-line" />
            <span className={`auth-step ${step === "seat" ? "active" : ""}`}>2 · Seat</span>
          </div>

          {step === "workspace" ? (
            <>
              <div className="auth-panel-head">
                <h1>Where would you like to start?</h1>
                <p>
                  Open one of your governed workspaces, or provision a brand-new stack from a URL.
                  Each workspace is independent — its own knowledge base, connectors, assistant,
                  org chart, and audit trail.
                </p>
              </div>

              {error && <div className="login-error">{error}</div>}

              {loadingWs ? (
                <div className="card">
                  <div className="thinking-row">
                    <span className="spinner" />
                    <span>Loading workspaces…</span>
                  </div>
                </div>
              ) : (
                <div className="intent-groups">
                  {workspaces.length > 0 && (
                    <div className="intent-group">
                      <div className="intent-label">Open a workspace</div>
                      <div className="brand-list">
                        {workspaces.map((w) => (
                          <button
                            key={w.id}
                            className="brand-row"
                            onClick={() => openBrand({ id: w.id, company: w.company })}
                            disabled={opening}
                          >
                            <span className="brand-row-logo">{(w.company || "?").slice(0, 1)}</span>
                            <span className="brand-row-info">
                              <span className="brand-row-name">{w.company}</span>
                              <span className="brand-row-meta">
                                {prettyIndustry(w.industry)} · {w.website}
                              </span>
                            </span>
                            <span className="brand-row-cta">→</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="intent-group">
                    <div className="intent-label">
                      {workspaces.length > 0 ? "Provision a new stack" : "Get started"}
                    </div>
                    {workspaces.length === 0 && (
                      <p className="intent-hint">
                        No workspaces yet — provision your first governed stack from a website URL.
                      </p>
                    )}
                    <div className="brand-list">
                      <button
                        className="brand-row brand-row-add"
                        onClick={provisionNew}
                        disabled={opening}
                      >
                        <span className="brand-row-logo brand-row-plus">＋</span>
                        <span className="brand-row-info">
                          <span className="brand-row-name">Provision a new stack</span>
                          <span className="brand-row-meta">
                            Scan a website → governed stack · System Administrator
                          </span>
                        </span>
                        <span className="brand-row-cta">→</span>
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {auth && (
                <div className="login-foot faint">
                  Signed in as <strong>{auth.role}</strong> — opening a workspace keeps your seat,
                  and you can switch seats anytime once inside.
                </div>
              )}
            </>
          ) : (
            <>
              <button className="auth-back" onClick={backToWorkspace}>
                ← Back
              </button>

              <div className="auth-panel-head">
                <h1>{brand?.isNew ? "Sign in to provision" : "Choose your seat"}</h1>
                <p>
                  {brand?.isNew ? (
                    <>
                      Standing up a new stack is a <strong>System Administrator</strong> action.
                      Once it exists, anyone can sign in with a department seat.
                    </>
                  ) : (
                    <>
                      Continue to <strong>{brand?.company}</strong>. Your seat sets your{" "}
                      <strong>department scope and clearance</strong> — enforced server-side, and
                      switchable anytime inside the workspace.
                    </>
                  )}
                </p>
              </div>

              {error && <div className="login-error">{error}</div>}

              {brand?.isNew ? (
                <div className="persona-grid">
                  <SeatCard tier="system" clearance="restricted" department={null} />
                </div>
              ) : loadingSeats ? (
                <div className="card">
                  <div className="thinking-row">
                    <span className="spinner" />
                    <span>Loading organization…</span>
                  </div>
                </div>
              ) : (
                <>
                  <div className="seat-section-label">Organization-wide</div>
                  <div className="persona-grid">
                    {ORG_WIDE.map((s) => (
                      <SeatCard key={s.tier} tier={s.tier} clearance={s.clearance} department={null} />
                    ))}
                  </div>

                  {departments.length > 0 && (
                    <>
                      <div className="seat-section-label" style={{ marginTop: 18 }}>
                        Sign in within a department
                      </div>
                      <select
                        className="seat-dept seat-dept-lg"
                        value={dept}
                        onChange={(e) => setDept(e.target.value)}
                        disabled={pending !== null}
                        aria-label="Department"
                      >
                        {departments.map((d) => (
                          <option key={d.name} value={d.name}>
                            {d.name}
                          </option>
                        ))}
                      </select>
                      <div className="persona-grid" style={{ marginTop: 12 }}>
                        {DEPT_TIERS.map((s) => (
                          <SeatCard
                            key={s.tier}
                            tier={s.tier}
                            clearance={s.clearance}
                            department={dept}
                            label={s.label}
                          />
                        ))}
                      </div>
                    </>
                  )}
                </>
              )}

              <div className="login-foot faint">
                🔒 Each seat issues a scoped, revocable API key carrying its department and
                clearance. Access is enforced server-side, not in the browser.
              </div>
            </>
          )}
        </div>
      </section>
    </div>
  );
}
