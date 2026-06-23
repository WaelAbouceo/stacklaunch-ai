import { useState } from "react";
import { useApp } from "../store/AppContext";
import BuildStepper from "./BuildStepper";
import AccountChip from "./AccountChip";

const EXAMPLES = [
  "gobus.example.com",
  "nilebank.example.com",
  "shopcairo.example.com",
  "medclinic.example.com",
];

const FEATURES = [
  "Website knowledge base",
  "CRM connector",
  "ERP connector",
  "Ticketing connector",
  "RAG assistant",
  "Structured data query",
  "One API key",
  "Model gateway",
  "RBAC",
  "Audit logs",
  "Observability",
  "Guardrails",
  "Web discovery",
  "Embeddable widget",
];

export default function Landing() {
  const { analyzeUrl, can, auth, logout } = useApp();
  const [url, setUrl] = useState("");
  const canProvision = can("manage:connectors", "write:all");

  const submit = () => {
    const value = url.trim();
    if (value) void analyzeUrl(value);
  };

  if (!canProvision) {
    return (
      <div className="landing">
        <div className="landing-inner">
          <span className="eyebrow">
            <span className="dot" style={{ width: 7, height: 7, borderRadius: 99, background: "var(--amber)" }} />
            Signed in as {auth?.role}
          </span>
          <h1>
            No workspace <span className="gradient-text">provisioned yet</span>
          </h1>
          <p className="sub">
            Provisioning a new AI stack is restricted to executive roles (CFO / CEO).
            Ask an administrator to set up your company workspace, or sign in with a
            role that has provisioning rights.
          </p>
          <div className="url-bar" style={{ justifyContent: "center" }}>
            <button className="btn" onClick={logout}>
              ← Switch role
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="landing">
      <div className="landing-inner">
        <AccountChip />
        <BuildStepper current={1} />
        <span className="eyebrow">
          <span className="dot" style={{ width: 7, height: 7, borderRadius: 99, background: "var(--green)" }} />
          Build phase · Step 1 of 4 — Scan a website
        </span>
        <h1>
          Build a <span className="gradient-text">governed AI stack</span>
        </h1>
        <p className="sub">
          Enter a URL to begin. StackLaunch crawls the site, detects the industry, and generates a
          complete enterprise stack — website knowledge, CRM, ERP & ticketing connectors, a RAG
          assistant, and full governance. You'll confirm each step before anything is built.
        </p>

        <div className="url-bar">
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            placeholder="https://gobus.example.com"
            autoFocus
          />
          <button className="btn btn-primary" onClick={submit} disabled={!url.trim()}>
            Check website →
          </button>
        </div>

        <div className="examples">
          {EXAMPLES.map((ex) => (
            <button key={ex} className="chip" onClick={() => setUrl(ex)}>
              {ex}
            </button>
          ))}
        </div>

        <div className="feature-grid">
          {FEATURES.map((f) => (
            <div className="feature-pill" key={f}>
              <span className="dot" />
              {f}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
