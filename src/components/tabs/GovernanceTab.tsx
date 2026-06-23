import { useState } from "react";
import { useApp } from "../../store/AppContext";
import { Stat } from "../ui";
import type { ClearanceLevel, Observability } from "../../types";
import { runEvals, type JudgedEvalReport } from "../../services/assistantApi";

type Sub = "org" | "guardrails" | "rbac" | "audit" | "observability" | "evals";

function pct(n?: number) {
  return n === undefined ? "—" : `${Math.round(n * 100)}%`;
}

// Color + ordinal per classification, shared by the org chart and domain legend.
const CLASSIFICATION_META: Record<ClearanceLevel, { color: string; rank: number }> = {
  public: { color: "#34d399", rank: 0 },
  internal: { color: "#6d8bff", rank: 1 },
  confidential: { color: "#f59e0b", rank: 2 },
  restricted: { color: "#f87171", rank: 3 },
};

const DOMAIN_LABELS: Record<string, string> = {
  crm: "CRM · Customers",
  erp: "ERP · Operations & Finance",
  ticketing: "Ticketing · Support",
  knowledge: "Knowledge Base",
};

function EvalsPanel() {
  const [report, setReport] = useState<JudgedEvalReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (judge: boolean) => {
    setLoading(true);
    setError(null);
    const r = await runEvals(judge);
    setLoading(false);
    if (!r) {
      setError("Could not run evals. Make sure the backend is running.");
      return;
    }
    setReport(r);
  };

  return (
    <div className="card">
      <div className="section-title">
        Evaluation harness
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <button className="btn" onClick={() => run(false)} disabled={loading}>
            Run deterministic
          </button>
          <button className="btn btn-primary" onClick={() => run(true)} disabled={loading}>
            {loading ? "Running…" : "Run LLM-judged"}
          </button>
        </div>
      </div>

      {error && <div className="login-error">{error}</div>}

      {!report && !error && (
        <p className="muted" style={{ fontSize: 13.5 }}>
          Run the golden-set evaluation. Deterministic checks verify expected
          signals and refusals; the LLM-judged pass adds groundedness, relevance,
          and PII-safety scoring per case.
        </p>
      )}

      {report && (
        <>
          <div className="validation-stats" style={{ marginBottom: 16 }}>
            <div className="vstat">
              <div className="vstat-num">
                {report.passed}/{report.total}
              </div>
              <div className="vstat-label">Deterministic passed</div>
            </div>
            {report.judge?.available ? (
              <>
                <div className="vstat">
                  <div className="vstat-num">
                    {report.judge.passed}/{report.judge.judged}
                  </div>
                  <div className="vstat-label">Judge passed</div>
                </div>
                <div className="vstat">
                  <div className="vstat-num">{pct(report.judge.avgGroundedness)}</div>
                  <div className="vstat-label">Avg groundedness</div>
                </div>
                <div className="vstat">
                  <div className="vstat-num">{pct(report.judge.avgRelevance)}</div>
                  <div className="vstat-label">Avg relevance</div>
                </div>
              </>
            ) : (
              <div className="vstat">
                <div className="vstat-num">—</div>
                <div className="vstat-label">Judge: no LLM</div>
              </div>
            )}
          </div>

          <div className="validation-turns">
            {report.cases.map((c, i) => (
              <div className="vturn" key={i}>
                <div className="vturn-head">
                  <span className={`vbadge ${c.passed ? "pass" : "fail"}`}>
                    {c.passed ? "PASS" : "FAIL"}
                  </span>
                  <span className="vturn-q">{c.question}</span>
                </div>
                {c.judge?.available && (
                  <div className="vturn-scores">
                    <span>grounded {pct(c.judge.groundedness)}</span>
                    <span>relevant {pct(c.judge.relevance)}</span>
                    <span className={c.judge.verdict === "pass" ? "" : "danger"}>
                      judge {c.judge.verdict}
                    </span>
                  </div>
                )}
                {c.judge?.rationale && (
                  <div className="vturn-rationale">{c.judge.rationale}</div>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

const OBS_FIELDS: { key: keyof Observability; label: string; icon: string }[] = [
  { key: "totalAssistantAnswers", label: "Assistant answers", icon: "✦" },
  { key: "connectorQueries", label: "Connector queries", icon: "🔌" },
  { key: "crmQueries", label: "CRM queries", icon: "👥" },
  { key: "erpQueries", label: "ERP queries", icon: "🏭" },
  { key: "ticketingQueries", label: "Ticketing queries", icon: "🎫" },
  { key: "knowledgeQueries", label: "Knowledge queries", icon: "📚" },
  { key: "crossSourceAnswers", label: "Cross-source answers", icon: "🔗" },
  { key: "piiMaskingEvents", label: "PII masking events", icon: "🛡" },
  { key: "guardrailBlocks", label: "Guardrail blocks", icon: "⛔" },
  { key: "websiteScans", label: "Website scans", icon: "🌐" },
];

function ClassBadge({ level }: { level: ClearanceLevel }) {
  const meta = CLASSIFICATION_META[level];
  return (
    <span
      className="class-badge"
      style={{
        color: meta.color,
        borderColor: `color-mix(in srgb, ${meta.color} 45%, transparent)`,
        background: `color-mix(in srgb, ${meta.color} 12%, transparent)`,
      }}
    >
      {level}
    </span>
  );
}

function OrgPanel({ org }: { org: import("../../types").OrgStructure | null }) {
  if (!org) {
    return (
      <div className="card">
        <p className="muted" style={{ fontSize: 13.5, margin: 0 }}>
          No org structure on this workspace yet. Provision a new stack to generate an
          industry-derived organization chart with data classification.
        </p>
      </div>
    );
  }

  // Reverse-index: which data domains each department owns, for the chart.
  const domainsByDept = new Map<string, { key: string; level: ClearanceLevel }[]>();
  Object.entries(org.dataDomains).forEach(([key, d]) => {
    if (!d.department) return;
    const list = domainsByDept.get(d.department) ?? [];
    list.push({ key, level: d.classification });
    domainsByDept.set(d.department, list);
  });

  return (
    <div style={{ display: "grid", gap: 18 }}>
      <div className="card">
        <div className="section-title">
          Data classification
          <span className="faint" style={{ marginLeft: "auto", fontSize: 12 }}>
            Access requires clearance ≥ classification
          </span>
        </div>
        <div className="class-legend">
          {org.clearanceLevels.map((lvl) => (
            <div className="class-legend-item" key={lvl}>
              <ClassBadge level={lvl} />
            </div>
          ))}
        </div>
        <div className="domain-grid">
          {Object.entries(org.dataDomains).map(([key, d]) => (
            <div className="domain-row" key={key}>
              <span className="domain-name">{DOMAIN_LABELS[key] ?? key}</span>
              <span className="faint" style={{ fontSize: 12.5 }}>
                {d.department ?? "Org-wide"}
              </span>
              <ClassBadge level={d.classification} />
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="section-title">
          Organization
          <span className="badge brand" style={{ marginLeft: "auto" }}>
            {org.departments.length} departments
          </span>
        </div>
        <div className="org-grid">
          {org.departments.map((dept) => (
            <div className="org-dept" key={dept.name}>
              <div className="org-dept-head">
                <span className="org-dept-name">{dept.name}</span>
                <div className="org-dept-domains">
                  {(domainsByDept.get(dept.name) ?? []).map((d) => (
                    <ClassBadge key={d.key} level={d.level} />
                  ))}
                </div>
              </div>
              <div className="org-groups">
                {dept.groups.map((g) => (
                  <span className="org-group" key={g}>
                    {g}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function GovernanceTab() {
  const { project } = useApp();
  const [sub, setSub] = useState<Sub>("org");
  if (!project) return null;

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Governance</h1>
          <div className="desc">
            RBAC, audit logging, observability, and guardrails applied across every connector and
            assistant answer.
          </div>
        </div>
        <span className="badge green dot">All policies active</span>
      </div>

      <div className="subtabs">
        {(
          [
            ["org", "Organization"],
            ["guardrails", "Guardrails"],
            ["rbac", "RBAC"],
            ["audit", "Audit Logs"],
            ["observability", "Observability"],
            ["evals", "Evals"],
          ] as [Sub, string][]
        ).map(([id, label]) => (
          <button key={id} className={`subtab ${sub === id ? "active" : ""}`} onClick={() => setSub(id)}>
            {label}
          </button>
        ))}
      </div>

      {sub === "org" && (
        <OrgPanel org={project.orgStructure ?? null} />
      )}

      {sub === "guardrails" && (
        <div className="grid grid-2">
          {project.guardrails.map((g) => (
            <div className="list-card" key={g.id}>
              <div className="lc-icon">🛡</div>
              <div>
                <h4>{g.title}</h4>
                <p>{g.description}</p>
                <span className="badge green dot" style={{ marginTop: 8 }}>
                  {g.status}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {sub === "rbac" && (
        <div className="grid grid-2">
          {project.roles.map((r) => (
            <div className="card" key={r.name}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
                <strong style={{ fontSize: 15 }}>{r.name}</strong>
                <span className="badge brand" style={{ marginLeft: "auto" }}>
                  {r.permissions.length} permissions
                </span>
              </div>
              <p className="muted" style={{ fontSize: 13.5, margin: "0 0 12px" }}>
                {r.description}
              </p>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {r.permissions.map((p) => (
                  <span key={p} className="perm-tag">
                    {p}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {sub === "audit" && (
        <div className="card">
          <div className="section-title">
            Audit event stream
            <span className="badge" style={{ marginLeft: "auto" }}>
              {project.audit.length} events
            </span>
          </div>
          <div className="timeline">
            {[...project.audit]
              .reverse()
              .map((e) => (
                <div className="tl-item" key={e.id}>
                  <span className="tl-tag">{e.type}</span>
                  <div className="tl-body">
                    <div className="tl-msg">{e.message}</div>
                    <div className="tl-time">
                      {e.actor} · {new Date(e.timestamp).toLocaleString()}
                    </div>
                  </div>
                </div>
              ))}
          </div>
        </div>
      )}

      {sub === "observability" && (
        <div className="grid grid-4">
          {OBS_FIELDS.map((f) => (
            <Stat
              key={f.key}
              icon={f.icon}
              label={f.label}
              value={project.observability[f.key] ?? 0}
            />
          ))}
        </div>
      )}

      {sub === "evals" && <EvalsPanel />}
    </div>
  );
}
