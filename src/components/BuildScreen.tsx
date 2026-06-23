import { useApp } from "../store/AppContext";
import BuildStepper from "./BuildStepper";

export default function BuildScreen() {
  const { buildSteps } = useApp();
  const lastIndex = buildSteps.length - 1;

  return (
    <div className="build-screen">
      <div className="build-box">
        <BuildStepper current={3} />
        <span className="eyebrow" style={{ marginBottom: 6 }}>
          <span className="dot" style={{ width: 7, height: 7, borderRadius: 99, background: "var(--brand)" }} />
          Build phase · Step 3 of 4 — Generating
        </span>
        <h2>
          Building your <span className="gradient-text">governed AI stack</span>
        </h2>
        <p className="muted">Crawling, detecting the industry, and generating connectors…</p>
        <div className="build-steps">
          {buildSteps.map((s, i) => {
            const done = i < lastIndex;
            return (
              <div className="build-step" key={`${s.step}-${i}`}>
                <span className={`step-check ${done ? "done" : "active"}`}>
                  {done ? "✓" : <span className="spinner" />}
                </span>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>{s.step}</div>
                  <div className="faint" style={{ fontSize: 12.5 }}>
                    {s.detail}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
