import { useState } from "react";
import { useApp } from "../../store/AppContext";

export default function ApiWidgetTab() {
  const { project } = useApp();
  const [copied, setCopied] = useState<string | null>(null);
  if (!project) return null;

  const copy = (text: string, id: string) => {
    void navigator.clipboard?.writeText(text);
    setCopied(id);
    setTimeout(() => setCopied(null), 1500);
  };

  const curl = `curl https://api.stacklaunch.ai/v1/chat \\
  -H "Authorization: Bearer ${project.apiKey}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "project": "${project.id}",
    "message": "What are the top customer issues this week?",
    "sources": ["website", "crm", "erp", "ticketing"]
  }'`;

  const widget = `<script
  src="https://cdn.stacklaunch.ai/widget.js"
  data-project="${project.id}"
  data-key="${project.apiKey}"
  data-accent="#6d8bff">
</script>`;

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>API & Widget</h1>
          <div className="desc">
            One API key routes through the model gateway to every governed source. Drop the widget
            on any site to ship the assistant.
          </div>
        </div>
      </div>

      <div className="grid grid-3" style={{ marginBottom: 24 }}>
        <div className="stat">
          <div className="label">🔑 API key</div>
          <div className="value" style={{ fontSize: 14 }}>
            <span className="mono">{project.apiKey.slice(0, 22)}…</span>
          </div>
          <button
            className="btn"
            style={{ marginTop: 10, fontSize: 12, padding: "6px 12px" }}
            onClick={() => copy(project.apiKey, "key")}
          >
            {copied === "key" ? "Copied ✓" : "Copy key"}
          </button>
        </div>
        <div className="stat">
          <div className="label">⚡ Model gateway</div>
          <div className="value" style={{ fontSize: 18 }}>
            Active
          </div>
          <div className="hint">Routing across website + 3 connectors</div>
        </div>
        <div className="stat">
          <div className="label">🧩 Widget</div>
          <div className="value" style={{ fontSize: 18 }}>
            Ready
          </div>
          <div className="hint">Embeddable on any page</div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 20 }}>
        <div className="section-title">
          REST API
          <button
            className="btn"
            style={{ marginLeft: "auto", fontSize: 12, padding: "6px 12px" }}
            onClick={() => copy(curl, "curl")}
          >
            {copied === "curl" ? "Copied ✓" : "Copy"}
          </button>
        </div>
        <div className="code-block">{curl}</div>
      </div>

      <div className="card">
        <div className="section-title">
          Embeddable widget
          <button
            className="btn"
            style={{ marginLeft: "auto", fontSize: 12, padding: "6px 12px" }}
            onClick={() => copy(widget, "widget")}
          >
            {copied === "widget" ? "Copied ✓" : "Copy"}
          </button>
        </div>
        <div className="code-block">{widget}</div>
      </div>
    </div>
  );
}
