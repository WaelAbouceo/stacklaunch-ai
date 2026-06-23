import { useApp } from "../store/AppContext";
import BuildStepper from "./BuildStepper";
import AccountChip from "./AccountChip";

export default function StackReady() {
  const { project, enterWorkspace, reset } = useApp();
  if (!project) return null;

  const kb = project.knowledgeBase.pagesIndexed;
  const crm = project.connectors.crm.recordCount;
  const erp = project.connectors.erp.recordCount;
  const tickets = project.connectors.ticketing.recordCount;

  const summary = [
    { icon: "📚", label: "Knowledge base", value: `${kb} pages indexed` },
    { icon: "👥", label: "CRM connector", value: `${crm.toLocaleString()} records` },
    { icon: "🏭", label: "ERP connector", value: `${erp.toLocaleString()} records` },
    { icon: "🎫", label: "Ticketing connector", value: `${tickets.toLocaleString()} records` },
    { icon: "🛡", label: "Guardrails", value: `${project.guardrails.length} policies active` },
    { icon: "🔑", label: "RBAC", value: `${project.roles.length} roles configured` },
  ];

  return (
    <div className="confirm-screen">
      <div className="confirm-box ready-box">
        <AccountChip />
        <BuildStepper current={4} />

        <div className="ready-check">✓</div>
        <h2>
          Your stack is <span className="gradient-text">ready</span>
        </h2>
        <p className="muted">
          The governed AI stack for <strong>{project.companyName}</strong> ({project.industryLabel})
          has been built. Review what was generated, then step into the workspace to try it.
        </p>

        <div className="ready-grid">
          {summary.map((s) => (
            <div className="ready-item" key={s.label}>
              <div className="ready-item-icon">{s.icon}</div>
              <div>
                <div className="ready-item-value">{s.value}</div>
                <div className="ready-item-label">{s.label}</div>
              </div>
            </div>
          ))}
        </div>

        {project.dataProfile && project.dataProfile.products.length > 0 && (
          <div className="ready-note">
            ✨ Datasets were <strong>grounded in {project.companyName}'s real offerings</strong> —
            CRM segments, ERP records, and tickets reference{" "}
            {project.dataProfile.products
              .slice(0, 4)
              .map((p) => p.name)
              .join(", ")}
            {project.dataProfile.products.length > 4 ? " and more" : ""}.
          </div>
        )}

        <div className="ready-note">
          Next: the <strong>Try the stack</strong> workspace gives you the overview,
          AI assistant, connectors, and governance — all scoped to your role.
        </div>

        <div className="confirm-actions">
          <button className="btn btn-ghost" onClick={reset}>
            ← Build another
          </button>
          <button className="btn btn-primary" onClick={enterWorkspace}>
            Try the stack →
          </button>
        </div>
      </div>
    </div>
  );
}
