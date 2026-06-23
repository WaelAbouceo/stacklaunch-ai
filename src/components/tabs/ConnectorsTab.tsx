import { useState } from "react";
import { useApp } from "../../store/AppContext";
import { maskCRMRecord } from "../../services/piiMaskingService";
import { clearanceColor } from "../../personas";
import { deptInScope, canSeeFinancials, REDACTED } from "../../access";
import type { ConnectorBase } from "../../types";

const CONNECTOR_ICON: Record<string, string> = {
  crm: "👥",
  erp: "🏭",
  ticketing: "🎫",
};

function ConnectorCard({
  connector,
  onToggleMask,
  restricted = false,
}: {
  connector: ConnectorBase;
  onToggleMask?: () => void;
  restricted?: boolean;
}) {
  return (
    <div className={`connector-card${restricted ? " is-restricted" : ""}`}>
      <div className="connector-top">
        <div className="connector-icon">{restricted ? "🔒" : CONNECTOR_ICON[connector.id]}</div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 650, fontSize: 15 }}>{connector.name}</div>
          <div className="faint" style={{ fontSize: 12.5 }}>
            {connector.datasetType}
          </div>
        </div>
        {restricted ? (
          <span className="badge" title="Outside your department scope">Restricted</span>
        ) : (
          <span className="badge green dot">Demo Connected</span>
        )}
      </div>

      {(connector.department || connector.classification) && (
        <div className="connector-domain">
          {connector.department && (
            <span className="domain-owner">🏛 {connector.department}</span>
          )}
          {connector.classification && (
            <span
              className="class-badge"
              style={{
                color: clearanceColor(connector.classification),
                borderColor: `color-mix(in srgb, ${clearanceColor(connector.classification)} 45%, transparent)`,
                background: `color-mix(in srgb, ${clearanceColor(connector.classification)} 12%, transparent)`,
              }}
            >
              {connector.classification}
            </span>
          )}
        </div>
      )}

      <div className="connector-meta">
        <div className="kv">
          <div className="k">Records</div>
          <div className="v">{connector.recordCount.toLocaleString()}</div>
        </div>
        <div className="kv">
          <div className="k">Last sync</div>
          <div className="v">{connector.lastSync}</div>
        </div>
        <div className="kv">
          <div className="k">Access</div>
          <div className="v">
            <span className="badge brand" style={{ fontSize: 11 }}>
              {connector.access}
            </span>
          </div>
        </div>
        <div className="kv">
          <div className="k">PII Masking</div>
          <div className="v">
            {connector.id === "crm" ? (
              <span
                className="badge green"
                style={{ fontSize: 11, cursor: onToggleMask ? "pointer" : "default" }}
              >
                {connector.piiMasking ? "Active" : "Off"}
              </span>
            ) : (
              <span className="faint" style={{ fontSize: 12 }}>
                Not applicable
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ConnectorsTab() {
  const { project, auth, maskNames, setMaskNames } = useApp();
  const [view, setView] = useState<"crm" | "erp" | "ticketing">("crm");
  if (!project) return null;

  const { crm, erp, ticketing } = project.connectors;
  const order = ["crm", "erp", "ticketing"] as const;
  const inScope = (k: (typeof order)[number]) =>
    deptInScope(auth, project.connectors[k].department);
  const fin = canSeeFinancials(auth);
  // The selected view must be one the seat is allowed to drill into.
  const scoped = order.filter(inScope);
  const effView = inScope(view) ? view : scoped[0];

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Data Connectors</h1>
          <div className="desc">
            Industry-specific {project.industryLabel} datasets, generated and connected as governed
            demo sources. Records are scoped to your department; financial fields require
            Confidential clearance.
          </div>
        </div>
        <span className="badge green dot">{scoped.length}/3 in your scope</span>
      </div>

      <div className="grid grid-3" style={{ marginBottom: 28 }}>
        <ConnectorCard connector={crm} restricted={!inScope("crm")} />
        <ConnectorCard connector={erp} restricted={!inScope("erp")} />
        <ConnectorCard connector={ticketing} restricted={!inScope("ticketing")} />
      </div>

      <div className="toolbar">
        <div className="subtabs" style={{ marginBottom: 0, border: "none" }}>
          {order.map((v) => {
            const locked = !inScope(v);
            return (
              <button
                key={v}
                className={`subtab ${effView === v ? "active" : ""}`}
                onClick={() => !locked && setView(v)}
                disabled={locked}
                title={locked ? `Restricted to ${project.connectors[v].department}` : undefined}
              >
                {locked ? "🔒 " : ""}
                {project.connectors[v].name}
              </button>
            );
          })}
        </div>
        <div className="spacer" />
        {effView === "crm" && (
          <button
            className="btn"
            style={{ fontSize: 13 }}
            onClick={() => setMaskNames(!maskNames)}
          >
            <span className={`toggle ${maskNames ? "on" : ""}`} />
            Mask names
          </button>
        )}
        <span className="badge">Preview · first 12 rows</span>
      </div>

      {!effView && (
        <div className="card" style={{ textAlign: "center", padding: 28 }}>
          <p className="muted" style={{ margin: 0 }}>
            🔒 No connector is in your department scope. Use the Assistant for governed,
            scoped insights, or sign in with a seat in the owning department.
          </p>
        </div>
      )}

      {effView === "crm" && (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Customer ID</th>
                <th>Name</th>
                <th>Segment</th>
                <th>City</th>
                <th>Email</th>
                <th>Phone</th>
                <th>LTV (EGP)</th>
                <th>Channel</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {crm.records.slice(0, 12).map((r) => {
                const m = maskCRMRecord(r, { maskNames });
                return (
                  <tr key={r.customerId}>
                    <td className="mono">{m.customerId}</td>
                    <td>{m.name}</td>
                    <td>{m.segment}</td>
                    <td>{m.city}</td>
                    <td className="mono faint">{m.email}</td>
                    <td className="mono faint">{m.phone}</td>
                    <td>{fin ? r.lifetimeValueEgp.toLocaleString() : REDACTED}</td>
                    <td>{r.preferredChannel}</td>
                    <td>
                      <StatusBadge status={r.status} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {effView === "erp" && (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Record ID</th>
                <th>Entity Type</th>
                <th>Name</th>
                <th>Revenue (EGP)</th>
                <th>Cost (EGP)</th>
                <th>Margin %</th>
                <th>Utilization %</th>
                <th>Period</th>
              </tr>
            </thead>
            <tbody>
              {erp.records.slice(0, 12).map((r) => (
                <tr key={r.recordId}>
                  <td className="mono">{r.recordId}</td>
                  <td>
                    <span className="perm-tag">{r.entityType}</span>
                  </td>
                  <td>{r.name}</td>
                  <td>{fin ? r.revenueEgp.toLocaleString() : REDACTED}</td>
                  <td>{fin ? r.costEgp.toLocaleString() : REDACTED}</td>
                  <td style={{ color: fin && r.marginPercent < 10 ? "var(--red)" : "var(--green)" }}>
                    {fin ? `${r.marginPercent}%` : REDACTED}
                  </td>
                  <td>{r.utilizationPercent}%</td>
                  <td className="faint">{r.period}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {effView === "ticketing" && (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Ticket ID</th>
                <th>Customer</th>
                <th>Category</th>
                <th>Priority</th>
                <th>Status</th>
                <th>Sentiment</th>
                <th>SLA</th>
                <th>Channel</th>
                <th>Summary</th>
              </tr>
            </thead>
            <tbody>
              {ticketing.records.slice(0, 12).map((r) => (
                <tr key={r.ticketId}>
                  <td className="mono">{r.ticketId}</td>
                  <td className="mono faint">{r.customerId}</td>
                  <td>{r.category}</td>
                  <td>
                    <PriorityBadge priority={r.priority} />
                  </td>
                  <td>{r.status}</td>
                  <td>
                    <SentimentBadge sentiment={r.sentiment} />
                  </td>
                  <td>
                    <SlaBadge sla={r.slaStatus} />
                  </td>
                  <td>{r.channel}</td>
                  <td className="faint" style={{ whiteSpace: "normal", minWidth: 220 }}>
                    {r.summary}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = { active: "green", at_risk: "amber", inactive: "" };
  return <span className={`badge ${map[status] ?? ""}`}>{status.replace("_", " ")}</span>;
}
function PriorityBadge({ priority }: { priority: string }) {
  const map: Record<string, string> = { Low: "", Medium: "brand", High: "amber", Critical: "red" };
  return <span className={`badge ${map[priority] ?? ""}`}>{priority}</span>;
}
function SentimentBadge({ sentiment }: { sentiment: string }) {
  const map: Record<string, string> = { positive: "green", neutral: "", negative: "red" };
  return <span className={`badge ${map[sentiment] ?? ""}`}>{sentiment}</span>;
}
function SlaBadge({ sla }: { sla: string }) {
  const map: Record<string, string> = { within_sla: "green", at_risk: "amber", breached: "red" };
  return <span className={`badge ${map[sla] ?? ""}`}>{sla.replace(/_/g, " ")}</span>;
}
