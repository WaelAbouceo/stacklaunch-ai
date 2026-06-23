import type { IndustryKey, Project } from "../types";
import { scanWebsite, type ScanResult } from "./websiteScanService";
import { authHeaders } from "./authService";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export interface BuildProgress {
  step: string;
  detail: string;
}

// Industry classification as understood from the scan. The backend produces this
// (LLM, or keyword fallback) — the frontend no longer classifies anything.
export interface IndustryDetectionResult {
  industry: IndustryKey;
  label: string;
  confidence: number;
  matchedKeywords: string[];
}

// What we understood about the website, surfaced for user confirmation before
// the full stack is generated. Lets the user catch a wrong URL / industry early.
export interface WebsiteAnalysis {
  websiteUrl: string;
  companyName: string;
  scan: ScanResult;
  detection: IndustryDetectionResult;
}

// User-confirmed (and possibly corrected) understanding used to build the stack.
export interface BuildConfirmation {
  websiteUrl: string;
  companyName: string;
  industry: IndustryKey;
}

function detectionFromScan(scan: ScanResult): IndustryDetectionResult {
  return {
    industry: (scan.industry ?? "generic_services") as IndustryKey,
    label: scan.industryLabel ?? "General Services",
    confidence: scan.industryConfidence ?? 0.5,
    matchedKeywords: scan.industryTopics ?? [],
  };
}

// Lightweight first pass: scan + classify the site on the backend, without
// generating any connectors. Cheap enough to re-run when the user edits the URL.
export async function analyzeWebsite(url: string): Promise<WebsiteAnalysis> {
  const scan = await scanWebsite(url);
  return {
    websiteUrl: scan.websiteUrl,
    companyName: scan.companyName,
    scan,
    detection: detectionFromScan(scan),
  };
}

// Build the full governed stack on the backend from the confirmed analysis. The
// already-scanned content is forwarded so the site isn't crawled again.
export async function buildProject(
  confirmation: BuildConfirmation,
  scan: ScanResult,
  onProgress?: (p: BuildProgress) => void,
): Promise<Project> {
  onProgress?.({ step: "Building knowledge base", detail: `${scan.knowledgeBase.pagesIndexed} real pages indexed` });
  onProgress?.({ step: "Generating connectors", detail: "CRM • ERP • Ticketing datasets" });
  onProgress?.({ step: "Applying governance", detail: "Guardrails • RBAC • audit • observability" });

  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}/api/build`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        websiteUrl: confirmation.websiteUrl,
        companyName: confirmation.companyName,
        industry: confirmation.industry,
        scan,
      }),
    });
  } catch {
    throw new Error(
      "Can't reach the build service. Make sure the backend is running (uvicorn on port 8000).",
    );
  }
  if (!resp.ok) {
    let detail = `Build failed (HTTP ${resp.status}).`;
    try {
      const data = await resp.json();
      if (data?.detail) detail = String(data.detail);
    } catch {
      /* keep default */
    }
    throw new Error(detail);
  }

  const project = (await resp.json()) as Project;
  onProgress?.({ step: "Stack ready", detail: "Governed AI stack generated" });
  return project;
}
