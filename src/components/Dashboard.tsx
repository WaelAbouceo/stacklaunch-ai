import { useState } from "react";
import { useApp } from "../store/AppContext";
import logo from "../assets/logo.png";
import RoleSwitcher from "./RoleSwitcher";
import OverviewTab from "./tabs/OverviewTab";
import KnowledgeBaseTab from "./tabs/KnowledgeBaseTab";
import ConnectorsTab from "./tabs/ConnectorsTab";
import AssistantTab from "./tabs/AssistantTab";
import GovernanceTab from "./tabs/GovernanceTab";
import ApiWidgetTab from "./tabs/ApiWidgetTab";
import SovereignStackTab from "./tabs/SovereignStackTab";

export type TabId =
  | "overview"
  | "knowledge"
  | "connectors"
  | "assistant"
  | "stack"
  | "governance"
  | "api";

const NAV: {
  section?: string;
  id: TabId;
  label: string;
  icon: string;
  perm?: string[];
}[] = [
  { id: "overview", label: "Overview", icon: "▦", perm: ["read:connectors:aggregated"] },
  { id: "assistant", label: "AI Assistant", icon: "✦", perm: ["use:assistant"] },
  { section: "Data", id: "knowledge", label: "Knowledge Base", icon: "📚", perm: ["read:knowledge"] },
  { id: "connectors", label: "Data Connectors", icon: "🔌", perm: ["read:connectors:aggregated"] },
  { section: "Governance", id: "stack", label: "Sovereign Stack", icon: "🏛" },
  { id: "governance", label: "Governance", icon: "🛡", perm: ["view:audit"] },
  { id: "api", label: "API & Widget", icon: "⚡", perm: ["manage:connectors"] },
];

export default function Dashboard() {
  const { project, reset, auth, logout, can, closeWorkspace } = useApp();
  const visibleNav = NAV.filter((item) => !item.perm || can(...item.perm));
  const [tab, setTab] = useState<TabId | null>(null);
  if (!project) return null;
  // Land on the first tab this persona is allowed to see (Customers, who can't see
  // aggregated data, start on the Assistant rather than a restricted Overview).
  const fallback: TabId = visibleNav[0]?.id ?? "assistant";
  const activeTab: TabId = tab && visibleNav.some((n) => n.id === tab) ? tab : fallback;

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <img className="brand-logo-img" src={logo} alt="StackLaunch AI logo" />
          <div>
            <div className="brand-name">StackLaunch AI</div>
            <div className="faint" style={{ fontSize: 11 }}>
              Enterprise AI layer
            </div>
          </div>
        </div>

        {visibleNav.map((item) => (
          <div key={item.id}>
            {item.section && <div className="nav-section">{item.section}</div>}
            <button
              className={`nav-item ${tab === item.id ? "active" : ""}`}
              onClick={() => setTab(item.id)}
            >
              <span className="ico">{item.icon}</span>
              {item.label}
            </button>
          </div>
        ))}

        <div className="sidebar-foot">
          {auth && (
            <div className="user-card">
              <div className="user-card-top">
                <div className="user-avatar">{(auth.role || "?").slice(0, 1)}</div>
                <div className="user-meta">
                  <div className="user-role">{auth.role}</div>
                  <div className="faint" style={{ fontSize: 11 }}>
                    Scoped key active
                  </div>
                </div>
              </div>
              <RoleSwitcher />
              <button className="user-switch" onClick={logout}>
                ⇄ Switch account
              </button>
            </div>
          )}
          <div className="card" style={{ padding: 12 }}>
            <div className="faint" style={{ fontSize: 11, marginBottom: 4 }}>
              CONNECTED SITE
            </div>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 2 }}>
              {project.companyName}
            </div>
            <div className="faint mono" style={{ fontSize: 11, wordBreak: "break-all" }}>
              {project.websiteUrl}
            </div>
            <span className="badge brand" style={{ marginTop: 10 }}>
              {project.industryLabel}
            </span>
            <button
              className="btn"
              style={{ width: "100%", marginTop: 12, justifyContent: "center", fontSize: 13 }}
              onClick={closeWorkspace}
            >
              ⇄ Switch workspace
            </button>
            {can("manage:connectors", "write:all") && (
              <button
                className="btn"
                style={{ width: "100%", marginTop: 8, justifyContent: "center", fontSize: 13 }}
                onClick={reset}
              >
                ＋ Build another stack
              </button>
            )}
          </div>
        </div>
      </aside>

      <main className="main">
        {activeTab === "overview" && <OverviewTab onNavigate={setTab} />}
        {activeTab === "assistant" && <AssistantTab />}
        {activeTab === "knowledge" && <KnowledgeBaseTab />}
        {activeTab === "connectors" && <ConnectorsTab />}
        {activeTab === "stack" && <SovereignStackTab />}
        {activeTab === "governance" && <GovernanceTab />}
        {activeTab === "api" && <ApiWidgetTab />}
      </main>
    </div>
  );
}
