import { useEffect, useState } from "react";
import {
  fetchSovereignty,
  fetchHealth,
  type SovereigntyPosture,
  type HealthInfo,
} from "../../services/sovereigntyApi";

// The architecture is defined in code (the backend layer packages). This view
// renders those layers as a stack and overlays the *live* sovereignty posture
// pulled from /api/sovereignty, so the demo shows the running stack, not a picture.
interface Layer {
  key: string;
  name: string;
  role: string;
  ref: string; // mapping to the sovereign reference architecture
  color: string;
  modules: string[];
  overlay?: (p: SovereigntyPosture, h: HealthInfo | null) => string[];
  dashed?: boolean;
}

const LAYERS: Layer[] = [
  {
    key: "api",
    name: "api",
    role: "Interface · Sovereign perimeter / gatekeeper",
    ref: "≈ Reference L2 · Platform",
    color: "#38bdf8",
    modules: ["app.py (FastAPI)", "auth + RBAC at edge", "rate limiting", "lifespan sovereignty check"],
    overlay: (p) => [
      p.controls.requireAuth ? "Auth: API key required" : "Auth: open (demo mode)",
      `Rate limit: enforced`,
    ],
  },
  {
    key: "agentic",
    name: "agentic",
    role: "Reasoning · AI services",
    ref: "≈ Reference L1 · Application",
    color: "#a78bfa",
    modules: ["agent", "orchestrator", "tools", "assistant", "retrieval", "briefing"],
    overlay: (p, h) => [
      `Model: ${h?.llm?.model ?? p.llm.model ?? "heuristic fallback"}`,
      `Tool allowlists: per-seat (RBAC)`,
    ],
  },
  {
    key: "evaluation",
    name: "evaluation",
    role: "Assurance overlay",
    ref: "＋ Beyond reference (assurance)",
    color: "#c084fc",
    modules: ["judge", "evals", "convvalidate"],
    dashed: true,
  },
  {
    key: "data",
    name: "data",
    role: "Knowledge · RAG + connectors",
    ref: "≈ Reference L3 · Knowledge",
    color: "#34d399",
    modules: ["scanner", "search", "datagen", "database", "analytics", "industries", "appstore", "projectbuilder"],
    overlay: (_p, h) => [
      `Retrieval: ACL-filtered (clearance + department)`,
      `Search: SearXNG${h ? (h.searxng ? " · online" : " · offline") : ""}`,
    ],
  },
  {
    key: "governance",
    name: "governance",
    role: "Trust & control · Compliance backbone (cross-cutting)",
    ref: "≈ Reference L6 · Governance",
    color: "#f87171",
    modules: ["rbac", "orgmodel", "security", "sovereignty", "pii", "guardrails", "auditstore", "compliance", "audit_events"],
    overlay: (p) => [
      p.controls.rbac ? "RBAC: enforced" : "RBAC: off",
      p.controls.piiRedaction ? "PII redaction: on" : "PII: off",
      p.controls.auditHmacSigned ? "Audit: hash-chained + HMAC" : "Audit: hash-chained",
    ],
  },
  {
    key: "core",
    name: "core",
    role: "Foundation · On-prem / sovereign inference",
    ref: "≈ Reference L4 · Model",
    color: "#f59e0b",
    modules: ["config", "llm", "telemetry", "rng"],
    overlay: (p, h) => [
      `LLM: ${h?.llm?.provider ?? p.llm.provider ?? "none"} · ${p.llm.host ?? "—"}`,
      p.llm.residency.label,
    ],
  },
];

function Pill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={`sv-pill ${ok ? "sv-pill-ok" : "sv-pill-warn"}`}>
      <span className="sv-dot" />
      {label}
    </span>
  );
}

export default function SovereignStackTab() {
  const [posture, setPosture] = useState<SovereigntyPosture | null>(null);
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    (async () => {
      const [p, h] = await Promise.all([fetchSovereignty(), fetchHealth()]);
      if (!alive) return;
      setPosture(p);
      setHealth(h);
      setLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, []);

  if (loading) {
    return (
      <div className="page">
        <div className="page-head">
          <h1>Sovereign Stack</h1>
        </div>
        <div className="card faint">Reading live posture…</div>
      </div>
    );
  }

  if (!posture) {
    return (
      <div className="page">
        <div className="page-head">
          <h1>Sovereign Stack</h1>
        </div>
        <div className="login-error">Could not read /api/sovereignty. Is the backend running?</div>
      </div>
    );
  }

  const res = posture.llm.residency.code;
  const resTone = res === "external" ? "sv-pill-warn" : "sv-pill-ok";

  return (
    <div className="page">
      <div className="page-head">
        <h1>Sovereign Stack</h1>
        <p className="faint">
          The running architecture, layer by layer — wired to live data-residency &amp; egress posture.
        </p>
      </div>

      {/* Posture summary strip */}
      <div className="sv-summary">
        <div className="sv-summary-item">
          <span className="sv-summary-k">Data region</span>
          <span className="sv-summary-v">{posture.dataRegion}</span>
        </div>
        <div className="sv-summary-item">
          <span className="sv-summary-k">LLM residency</span>
          <span className={`sv-pill ${resTone}`}>
            <span className="sv-dot" />
            {posture.llm.residency.label}
          </span>
        </div>
        <div className="sv-summary-item">
          <span className="sv-summary-k">Mode</span>
          <span className={`sv-pill ${posture.strict ? "sv-pill-ok" : "sv-pill-warn"}`}>
            <span className="sv-dot" />
            {posture.strict ? "Strict sovereignty" : "Standard (demo)"}
          </span>
        </div>
        <div className="sv-summary-item">
          <span className="sv-summary-k">Data at rest</span>
          <span className="sv-summary-v">{posture.dataAtRest.store}</span>
        </div>
      </div>

      {/* The layered stack */}
      <div className="sv-stack">
        {LAYERS.map((l) => (
          <div
            key={l.key}
            className={`sv-band ${l.dashed ? "sv-band-dashed" : ""}`}
            style={{ ["--band" as string]: l.color }}
          >
            <div className="sv-band-rail" />
            <div className="sv-band-main">
              <div className="sv-band-head">
                <span className="sv-band-name">{l.name}</span>
                <span className="sv-band-role">{l.role}</span>
                <span className="sv-band-ref">{l.ref}</span>
              </div>
              <div className="sv-band-modules">
                {l.modules.map((m) => (
                  <span key={m} className="sv-mod">{m}</span>
                ))}
              </div>
              {l.overlay && (
                <div className="sv-band-live">
                  {l.overlay(posture, health).map((t) => (
                    <span key={t} className="sv-live">⬤ {t}</span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Egress boundary + controls */}
      <div className="grid-2" style={{ marginTop: 18 }}>
        <div className="card">
          <div className="section-title">Egress boundary</div>
          <p className="faint" style={{ marginTop: 4 }}>
            Only these outbound paths are sanctioned; everything else stays local.
          </p>
          <div className="sv-egress">
            <div className="sv-egress-row">
              <span>Inference</span>
              <span className="mono">{posture.llm.host ?? "—"}</span>
              <Pill ok={res !== "external"} label={posture.llm.residency.code} />
            </div>
            <div className="sv-egress-row">
              <span>Web search</span>
              <span className="mono">{posture.search.host ?? "—"}</span>
              <Pill ok label={posture.search.engine.replace(/\s*\(.*\)/, "")} />
            </div>
            <div className="sv-egress-row">
              <span>Site scanning</span>
              <span className="mono">user-supplied URLs</span>
              <Pill ok={posture.egress.scanSsrfGuard} label={posture.egress.scanSsrfGuard ? "SSRF guard on" : "unguarded"} />
            </div>
            <div className="sv-egress-row">
              <span>Private targets</span>
              <span className="mono">internal / metadata</span>
              <Pill ok={!posture.egress.allowPrivateScan} label={posture.egress.allowPrivateScan ? "allowed (dev)" : "blocked"} />
            </div>
          </div>
        </div>

        <div className="card">
          <div className="section-title">Sovereign controls</div>
          <p className="faint" style={{ marginTop: 4 }}>
            Cross-cutting guarantees enforced by the governance layer.
          </p>
          <div className="sv-controls">
            <Pill ok={posture.controls.rbac} label="RBAC + clearance" />
            <Pill ok={posture.controls.piiRedaction} label="Deterministic PII redaction" />
            <Pill ok={posture.controls.promptInjectionDefense} label="Prompt-injection defense" />
            <Pill ok={posture.controls.auditHashChained} label="Hash-chained audit" />
            <Pill ok={posture.controls.auditHmacSigned} label="HMAC-signed audit" />
            <Pill ok={!posture.egress.externalLlmAllowed} label={posture.egress.externalLlmAllowed ? "External LLM allowed" : "External LLM blocked"} />
          </div>
        </div>
      </div>
    </div>
  );
}
