import { useApp } from "../../store/AppContext";
import { Stat } from "../ui";
import { deptInScope, canSeeFinancials, REDACTED } from "../../access";
import type { TabId } from "../Dashboard";

export default function OverviewTab({ onNavigate }: { onNavigate: (t: TabId) => void }) {
  const { project, auth } = useApp();
  if (!project) return null;
  const s = project.analytics;
  const fin = canSeeFinancials(auth);
  const conn = project.connectors;
  const seeCrm = deptInScope(auth, conn.crm.department);
  const seeErp = deptInScope(auth, conn.erp.department);
  const seeTickets = deptInScope(auth, conn.ticketing.department);
  const deptCount = project.orgStructure?.departments.length ?? 0;

  const stackLayers = [
    { name: "Website Knowledge Base", detail: "Crawled & indexed" },
    { name: "CRM Connector", detail: conn.crm.department ?? "Demo Connected" },
    { name: "ERP Connector", detail: conn.erp.department ?? "Demo Connected" },
    { name: "Ticketing Connector", detail: conn.ticketing.department ?? "Demo Connected" },
    { name: "RAG Assistant", detail: "Cross-source reasoning" },
    { name: "Model Gateway", detail: "Single API key" },
    {
      name: "Org-aware RBAC",
      detail: deptCount ? `${deptCount} departments · 4 clearance levels` : "Scoped access",
    },
    { name: "Audit Logs", detail: "Hash-chained stream" },
    { name: "Observability", detail: "Live metrics" },
    { name: "Guardrails", detail: "PII · injection · scope" },
    { name: "Embeddable Widget", detail: "Ready to deploy" },
  ];

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>
            {project.companyName}{" "}
            <span className="muted" style={{ fontSize: 18, fontWeight: 500 }}>
              · {project.industryLabel}
            </span>
          </h1>
          <div className="desc">
            Governed enterprise AI stack generated from {project.websiteUrl} · industry confidence{" "}
            {Math.round(project.industryConfidence * 100)}%
          </div>
        </div>
        <button className="btn btn-primary" onClick={() => onNavigate("assistant")}>
          Open Assistant →
        </button>
      </div>

      <div className="card" style={{ marginBottom: 24, background: "linear-gradient(135deg, rgba(109,139,255,0.08), rgba(139,92,246,0.05))" }}>
        <p style={{ margin: 0, fontSize: 16, lineHeight: 1.6 }}>
          We entered your website URL. In minutes, StackLaunch generated your first{" "}
          <strong>governed AI stack</strong> — website knowledge, CRM, ERP and ticketing connectors,
          one API key, model routing, RBAC, audit, observability, guardrails, and a widget.
          <br />
          <span className="muted" style={{ fontSize: 14 }}>
            This is not a chatbot. This is the first working version of your enterprise AI operating layer.
          </span>
        </p>
      </div>

      <div className="grid grid-4" style={{ marginBottom: 24 }}>
        <Stat label="Pages indexed" value={project.knowledgeBase.pagesIndexed} icon="📄" hint="Website knowledge base" />
        <Stat
          label="CRM customers"
          value={seeCrm ? s.crm.total : REDACTED}
          icon="👥"
          hint={seeCrm ? `${s.crm.atRiskCount} at risk` : `Restricted · ${conn.crm.department}`}
        />
        <Stat
          label="ERP records"
          value={seeErp ? s.erp.total : REDACTED}
          icon="🏭"
          hint={
            !seeErp
              ? `Restricted · ${conn.erp.department}`
              : fin
                ? `avg margin ${s.erp.avgMarginPercent}%`
                : "margin restricted"
          }
        />
        <Stat
          label="Support tickets"
          value={seeTickets ? s.tickets.total : REDACTED}
          icon="🎫"
          hint={seeTickets ? `${s.tickets.negativeRate}% negative` : `Restricted · ${conn.ticketing.department}`}
        />
      </div>

      <div className="grid grid-2">
        <div className="card">
          <div className="section-title">Stack components</div>
          <div style={{ display: "grid", gap: 9 }}>
            {stackLayers.map((l) => (
              <div
                key={l.name}
                style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13.5 }}
              >
                <span className="badge green dot" style={{ padding: "2px 7px" }}>
                  ready
                </span>
                <span style={{ fontWeight: 550 }}>{l.name}</span>
                <span className="faint" style={{ marginLeft: "auto", fontSize: 12 }}>
                  {l.detail}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div style={{ display: "grid", gap: 16, alignContent: "start" }}>
          <div className="card">
            <div className="section-title">Top support issues</div>
            {seeTickets ? (
              <div style={{ display: "grid", gap: 8 }}>
                {s.tickets.byCategory.slice(0, 5).map((c) => (
                  <div key={c.label} style={{ display: "flex", justifyContent: "space-between", fontSize: 13.5 }}>
                    <span className="muted">{c.label}</span>
                    <span style={{ fontWeight: 600 }}>
                      {c.count} <span className="faint">({c.percent}%)</span>
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="muted" style={{ fontSize: 13, margin: 0 }}>
                🔒 Ticketing data is restricted to {conn.ticketing.department}.
              </p>
            )}
          </div>
          <div className="card" style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
            <button className="btn" onClick={() => onNavigate("connectors")} style={{ flex: 1 }}>
              🔌 View connectors
            </button>
            <button className="btn" onClick={() => onNavigate("governance")} style={{ flex: 1 }}>
              🛡 Governance
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
