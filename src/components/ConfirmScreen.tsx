import { useEffect, useState } from "react";
import { useApp } from "../store/AppContext";
import BuildStepper from "./BuildStepper";
import type { IndustryKey } from "../types";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

interface IndustryOption {
  key: IndustryKey;
  label: string;
}

export default function ConfirmScreen() {
  const { preview, analyzing, analyzeError, lastUrl, analyzeUrl, confirmBuild, cancelPreview } =
    useApp();

  const [url, setUrl] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [industry, setIndustry] = useState<IndustryKey>("generic_services");
  const [editingUrl, setEditingUrl] = useState(false);
  const [industryOptions, setIndustryOptions] = useState<IndustryOption[]>([]);

  // The full industry taxonomy lives on the backend; fetch it for the dropdown.
  useEffect(() => {
    let active = true;
    fetch(`${API_BASE}/api/industries`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (active && data?.industries) setIndustryOptions(data.industries);
      })
      .catch(() => {
        /* dropdown falls back to the detected industry below */
      });
    return () => {
      active = false;
    };
  }, []);

  // Sync local editable fields whenever a fresh analysis arrives.
  useEffect(() => {
    if (!preview) return;
    setUrl(preview.websiteUrl);
    setCompanyName(preview.companyName);
    setIndustry(preview.detection.industry);
    setEditingUrl(false);
  }, [preview]);

  // --- Loading: actively crawling the real site ---
  if (analyzing && !preview) {
    return (
      <div className="confirm-screen">
        <div className="confirm-box">
          <div className="confirm-checking">
            <span className="spinner" />
            <span>Visiting {lastUrl || "the website"} and reading its pages…</span>
          </div>
        </div>
      </div>
    );
  }

  // --- Error: the real fetch failed (unreachable / blocked / not HTML) ---
  if (analyzeError && !preview) {
    return (
      <div className="confirm-screen">
        <div className="confirm-box">
          <span className="eyebrow">
            <span
              className="dot"
              style={{ width: 7, height: 7, borderRadius: 99, background: "var(--red)" }}
            />
            Couldn’t scan that site
          </span>
          <h2>Let’s try a different URL</h2>
          <p className="confirm-error">{analyzeError}</p>
          <div className="confirm-field">
            <label>Website</label>
            <div className="confirm-url-edit">
              <input
                value={url || lastUrl}
                autoFocus
                onChange={(e) => setUrl(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && url.trim() && void analyzeUrl(url.trim())}
                placeholder="https://stripe.com"
              />
              <button
                className="btn btn-primary"
                onClick={() => void analyzeUrl((url || lastUrl).trim())}
                disabled={!(url || lastUrl).trim()}
              >
                Re-check
              </button>
            </div>
            <p className="confirm-hint">
              Some sites block automated visits or require a different address (e.g.{" "}
              <code>cib.com</code> → <code>cibeg.com</code>).
            </p>
          </div>
          <div className="confirm-actions">
            <button className="btn btn-ghost" onClick={cancelPreview}>
              ← Start over
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!preview) return null;

  const { detection } = preview;
  const { usedSearch, crawlFailed, llm } = preview.scan;
  const confidencePct = Math.round(detection.confidence * 100);

  const sourceLabel = crawlFailed
    ? "We couldn’t open the site directly, so we gathered this from web search"
    : usedSearch
      ? "We read the live site and enriched it with web search"
      : "We read the real website";
  const llmLabel =
    llm?.enabled && llm.provider
      ? `${llm.provider === "sovereigneg" ? "SovereignEG" : llm.provider} · ${llm.model}`
      : null;
  const lowConfidence = detection.industry === "generic_services" || detection.confidence < 0.6;

  // Always include the detected industry so the current value renders even
  // before (or if) the backend list loads.
  const options: IndustryOption[] = industryOptions.length
    ? industryOptions
    : [{ key: detection.industry, label: detection.label }];

  const recheck = () => {
    const value = url.trim();
    if (value) void analyzeUrl(value);
  };

  const confirm = () => {
    confirmBuild({ websiteUrl: url.trim(), companyName: companyName.trim(), industry });
  };

  return (
    <div className="confirm-screen">
      <div className="confirm-box">
        <BuildStepper current={2} />
        <span className="eyebrow">
          <span
            className="dot"
            style={{
              width: 7,
              height: 7,
              borderRadius: 99,
              background: crawlFailed ? "var(--amber)" : "var(--green)",
            }}
          />
          Build phase · Step 2 of 4 — {sourceLabel}
        </span>
        <h2>
          Before we build, is this <span className="gradient-text">right?</span>
        </h2>
        <p className="muted">
          Review what we understood and correct anything. Nothing is generated until you confirm
          below.
        </p>

        {(llmLabel || usedSearch) && (
          <div className="confirm-provenance">
            {llmLabel && <span className="prov-tag">🧠 {llmLabel}</span>}
            {usedSearch && <span className="prov-tag">🔎 SearXNG</span>}
          </div>
        )}

        {preview.scan.siteSummary && (
          <div className="confirm-quote">“{preview.scan.siteSummary}”</div>
        )}

        <div className="confirm-field">
          <label>Website</label>
          {editingUrl ? (
            <div className="confirm-url-edit">
              <input
                value={url}
                autoFocus
                onChange={(e) => setUrl(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && recheck()}
                placeholder="https://cibeg.com"
              />
              <button className="btn btn-primary" onClick={recheck} disabled={!url.trim() || analyzing}>
                {analyzing ? "Checking…" : "Re-check"}
              </button>
            </div>
          ) : (
            <div className="confirm-value-row">
              <span className="confirm-url">{url}</span>
              <button className="btn btn-ghost" onClick={() => setEditingUrl(true)}>
                Edit URL
              </button>
            </div>
          )}
          <p className="confirm-hint">
            Wrong address? Edit it (e.g. <code>cib.com</code> → <code>cibeg.com</code>) and re-check.
          </p>
        </div>

        <div className="confirm-field">
          <label>Company name (from the site)</label>
          <input
            className="confirm-input"
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
            placeholder="Company name"
          />
        </div>

        <div className="confirm-field">
          <label>Detected industry</label>
          <div className="confirm-value-row">
            <select
              className="confirm-input"
              value={industry}
              onChange={(e) => setIndustry(e.target.value as IndustryKey)}
            >
              {options.map((o) => (
                <option key={o.key} value={o.key}>
                  {o.label}
                </option>
              ))}
            </select>
            <span className={`confidence-badge ${lowConfidence ? "low" : "high"}`}>
              {confidencePct}% confidence
            </span>
          </div>
          {lowConfidence && (
            <p className="confirm-hint warn">
              ⚠ Low confidence — please double-check the industry above.
            </p>
          )}
          {detection.matchedKeywords.length > 0 && (
            <p className="confirm-hint">
              Signals found on the site: {detection.matchedKeywords.slice(0, 6).join(", ")}
            </p>
          )}
        </div>

        <div className="confirm-field">
          <label>Real pages we indexed ({preview.scan.knowledgeBase.pagesIndexed})</label>
          <div className="confirm-pages">
            {preview.scan.knowledgeBase.pages.map((p) => (
              <a
                className="confirm-page"
                key={p.url}
                href={p.url}
                target="_blank"
                rel="noreferrer"
                title={p.url}
              >
                {p.title}
              </a>
            ))}
          </div>
        </div>

        <div className="confirm-actions">
          <button className="btn btn-ghost" onClick={cancelPreview}>
            ← Start over
          </button>
          <button className="btn btn-primary" onClick={confirm} disabled={!url.trim() || !companyName.trim()}>
            Confirm & generate stack →
          </button>
        </div>
      </div>
    </div>
  );
}
