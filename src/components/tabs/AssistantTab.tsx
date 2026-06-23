import { useEffect, useRef, useState, Fragment } from "react";
import { useApp } from "../../store/AppContext";
import { SourceBadge } from "../ui";
import { tierMeta, clearanceColor } from "../../personas";
import { validateConversation, type ValidationReport } from "../../services/assistantApi";

function renderContent(text: string) {
  // Light formatting: **bold** and [label](url) links; newlines via pre-wrap.
  const parts = text.split(/(\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/g);
  return parts.map((p, i) => {
    if (p.startsWith("**") && p.endsWith("**")) {
      return <strong key={i}>{p.slice(2, -2)}</strong>;
    }
    const link = p.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (link) {
      return (
        <a key={i} href={link[2]} target="_blank" rel="noreferrer">
          {link[1]}
        </a>
      );
    }
    return <Fragment key={i}>{p}</Fragment>;
  });
}

const MODES = [
  { id: "agent", label: "Agent", hint: "Tool-calling agent (live)" },
  { id: "multi", label: "Multi-agent", hint: "Supervisor + specialists" },
  { id: "single", label: "Fast", hint: "Single-shot answer" },
] as const;

function pct(n?: number) {
  return n === undefined ? "—" : `${Math.round(n * 100)}%`;
}

function ValidationPanel({
  report,
  onClose,
}: {
  report: ValidationReport;
  onClose: () => void;
}) {
  const s = report.summary;
  return (
    <div className="validation-panel">
      <div className="validation-head">
        <div>
          <div className="validation-title">🔍 LLM-judged conversation validation</div>
          <div className="faint" style={{ fontSize: 12 }}>
            Each assistant turn graded against the data it was allowed to use.
          </div>
        </div>
        <button className="user-logout" onClick={onClose} title="Dismiss">
          ✕
        </button>
      </div>

      {!s.available ? (
        <div className="faint" style={{ fontSize: 13 }}>
          {s.reason === "no_assistant_turns"
            ? "No assistant turns in this session yet — ask a question first."
            : s.reason === "llm_unavailable"
              ? "No LLM is configured, so groundedness can't be graded (the deterministic PII gate still ran)."
              : "Validation unavailable for this session."}
        </div>
      ) : (
        <>
          <div className="validation-stats">
            <div className="vstat">
              <div className="vstat-num">
                {s.passed}/{s.judged}
              </div>
              <div className="vstat-label">Turns passed</div>
            </div>
            <div className="vstat">
              <div className="vstat-num">{pct(s.avgGroundedness)}</div>
              <div className="vstat-label">Avg groundedness</div>
            </div>
            <div className="vstat">
              <div className="vstat-num">{pct(s.avgRelevance)}</div>
              <div className="vstat-label">Avg relevance</div>
            </div>
            <div className="vstat">
              <div className={`vstat-num ${s.piiLeaks ? "danger" : ""}`}>{s.piiLeaks ?? 0}</div>
              <div className="vstat-label">PII leaks</div>
            </div>
          </div>

          <div className="validation-turns">
            {report.turns.map((t, i) => {
              const j = t.judge;
              const verdict = j.available ? j.verdict : "n/a";
              return (
                <div className="vturn" key={i}>
                  <div className="vturn-head">
                    <span className={`vbadge ${verdict}`}>{verdict?.toUpperCase()}</span>
                    <span className="vturn-q">{t.question || "(opening turn)"}</span>
                  </div>
                  {j.available && (
                    <div className="vturn-scores">
                      <span>grounded {pct(j.groundedness)}</span>
                      <span>relevant {pct(j.relevance)}</span>
                      <span className={j.piiLeak ? "danger" : ""}>
                        {j.piiLeak ? "PII leak" : "PII safe"}
                      </span>
                    </div>
                  )}
                  {j.rationale && <div className="vturn-rationale">{j.rationale}</div>}
                  {j.unsupportedClaims && j.unsupportedClaims.length > 0 && (
                    <div className="vturn-claims">
                      Unsupported: {j.unsupportedClaims.join("; ")}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

export default function AssistantTab() {
  const { project, messages, ask, thinking, liveActivity, mode, setMode, can, sessionId, auth } =
    useApp();
  const [input, setInput] = useState("");
  const [validating, setValidating] = useState(false);
  const [report, setReport] = useState<ValidationReport | null>(null);
  const [reportError, setReportError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, thinking, liveActivity]);

  if (!project) return null;
  const suggestions = project.suggestedQuestions;
  const canValidate = can("view:audit");

  const runValidation = async () => {
    setValidating(true);
    setReportError(null);
    const r = await validateConversation(sessionId);
    setValidating(false);
    if (!r) {
      setReportError("Validation failed. Make sure the backend is running.");
      return;
    }
    setReport(r);
  };

  const send = (q: string) => {
    const value = q.trim();
    if (!value || thinking) return;
    void ask(value);
    setInput("");
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>AI Assistant</h1>
          <div className="desc">
            Grounded in website knowledge + CRM, ERP & ticketing connectors. Structured questions are
            computed from connector summaries — raw records never leave the governance layer.
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div className="mode-switch" role="tablist" aria-label="Assistant mode">
            {MODES.map((m) => (
              <button
                key={m.id}
                role="tab"
                aria-selected={mode === m.id}
                title={m.hint}
                className={`mode-btn ${mode === m.id ? "active" : ""}`}
                onClick={() => setMode(m.id)}
                disabled={thinking}
              >
                {m.label}
              </button>
            ))}
          </div>
          {canValidate && (
            <button
              className="btn"
              style={{ fontSize: 12.5 }}
              onClick={runValidation}
              disabled={validating || messages.length === 0}
              title="Grade each assistant turn with the LLM judge"
            >
              {validating ? "Validating…" : "🔍 Validate conversation"}
            </button>
          )}
          <span className="badge green dot">PII Masking: Active</span>
        </div>
      </div>

      {auth && (
        <div
          className="persona-banner"
          style={{ ["--accent" as string]: tierMeta(auth.adminTier).accent }}
        >
          <span className="persona-banner-ico">{tierMeta(auth.adminTier).icon}</span>
          <span>
            Viewing as <strong>{auth.role}</strong>
            {auth.department ? ` · ${auth.department}` : ""}
          </span>
          <span
            className="class-badge"
            style={{
              color: clearanceColor(auth.clearance),
              borderColor: `color-mix(in srgb, ${clearanceColor(auth.clearance)} 45%, transparent)`,
              background: `color-mix(in srgb, ${clearanceColor(auth.clearance)} 12%, transparent)`,
            }}
          >
            {auth.clearance} clearance
          </span>
          <span className="persona-banner-hint">
            Switch seat in the sidebar to see RBAC re-scope this conversation live.
          </span>
        </div>
      )}

      {reportError && <div className="login-error" style={{ marginBottom: 14 }}>{reportError}</div>}
      {report && <ValidationPanel report={report} onClose={() => setReport(null)} />}

      <div className="chat">
        <div className="chat-main">
          <div className="chat-scroll" ref={scrollRef}>
            {messages.length === 0 && (
              <div className="empty-chat">
                <div style={{ fontSize: 34, marginBottom: 10 }}>✦</div>
                <div style={{ fontSize: 15, color: "var(--text)", fontWeight: 600, marginBottom: 6 }}>
                  Ask about {project.companyName}
                </div>
                <p style={{ fontSize: 13.5 }}>
                  Try a suggested question on the right, or ask about customers, operations, support
                  trends, or an action plan.
                </p>
              </div>
            )}
            {messages.map((m) => (
              <div className={`msg ${m.role}`} key={m.id}>
                <div className="msg-avatar">{m.role === "assistant" ? "✦" : "🙂"}</div>
                <div className="bubble">
                  {m.activity && m.activity.length > 0 && (
                    <div className="agent-trace">
                      <div className="agent-trace-head">
                        {m.mode === "multi" ? "Specialists" : "Agent steps"}
                      </div>
                      {m.activity.map((a, i) => (
                        <div className="agent-trace-line" key={i}>
                          {a}
                        </div>
                      ))}
                    </div>
                  )}
                  <div>{renderContent(m.content)}</div>
                  {m.computedFrom && m.computedFrom.length > 0 && (
                    <div className="computed">
                      ⚙ Computed from: {m.computedFrom.join(" · ")}
                    </div>
                  )}
                  {m.guardrailNote && (
                    <div className="guardrail-note">
                      <span>🛡</span>
                      <span>{m.guardrailNote}</span>
                    </div>
                  )}
                  {m.sources && m.sources.length > 0 && (
                    <div className="sources-row">
                      <div className="sources-label">Sources used</div>
                      {m.sources.map((s) => (
                        <SourceBadge key={s} source={s} />
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {thinking && (
              <div className="msg assistant">
                <div className="msg-avatar">✦</div>
                <div className="bubble">
                  <div className="thinking-row">
                    <span className="spinner" />
                    <span>
                      {mode === "multi"
                        ? "Coordinating specialists…"
                        : mode === "agent"
                          ? "Reasoning & calling tools…"
                          : "Reading knowledge & data…"}
                    </span>
                  </div>
                  {liveActivity.length > 0 && (
                    <div className="agent-trace live">
                      {liveActivity.map((a, i) => (
                        <div className="agent-trace-line" key={i}>
                          {a}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
          <div className="chat-input">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send(input)}
              placeholder={thinking ? "Thinking…" : `Ask about ${project.companyName}…`}
              disabled={thinking}
            />
            <button
              className="btn btn-primary"
              onClick={() => send(input)}
              disabled={!input.trim() || thinking}
            >
              Send
            </button>
          </div>
        </div>

        <div className="suggest-panel">
          <div className="section-title" style={{ fontSize: 13 }}>
            Suggested for {project.industryLabel}
          </div>
          {suggestions.map((q) => (
            <button key={q} className="suggest-q" onClick={() => send(q)}>
              {q}
            </button>
          ))}
          <div className="section-title" style={{ fontSize: 13, marginTop: 18 }}>
            Cross-source
          </div>
          {[
            "What is the relationship between complaints and revenue?",
            "Which operational area needs attention?",
            "Create a 7-day action plan.",
          ].map((q) => (
            <button key={q} className="suggest-q" onClick={() => send(q)}>
              {q}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
