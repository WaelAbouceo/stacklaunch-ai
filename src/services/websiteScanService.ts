import type { IndustryKey, KnowledgeBase } from "../types";
import { authHeaders } from "./authService";

export interface ScanResult {
  websiteUrl: string;
  companyName: string;
  // Real description scraped from the site (or LLM-written from real content).
  siteSummary: string;
  // Real concatenated page text, fed to the industry detector when no LLM.
  scannedText: string;
  knowledgeBase: KnowledgeBase;
  // LLM classification from the backend (present when an LLM is configured).
  industry?: IndustryKey;
  industryLabel?: string;
  industryConfidence?: number;
  industryTopics?: string[];
  // Whether the SearXNG fallback was used / the direct crawl failed.
  usedSearch?: boolean;
  crawlFailed?: boolean;
  // Which LLM (if any) the backend used.
  llm?: { enabled: boolean; provider: string | null; model: string | null };
}

// Base URL for the scan API. Empty by default so the Vite dev proxy (/api ->
// localhost:8000) handles it; override with VITE_API_BASE in production.
const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export class ScanError extends Error {}

// Call the backend to actually fetch + parse the requested website. Everything
// in the result is real content scraped from the live site.
export async function scanWebsite(input: string): Promise<ScanResult> {
  const url = (input ?? "").trim();
  if (!url) throw new ScanError("Please enter a website URL.");

  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}/api/scan`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ url }),
    });
  } catch {
    throw new ScanError(
      "Can't reach the scan service. Make sure the backend is running (uvicorn on port 8000).",
    );
  }

  if (!resp.ok) {
    let detail = `Scan failed (HTTP ${resp.status}).`;
    try {
      const data = await resp.json();
      if (data?.detail) detail = String(data.detail);
    } catch {
      /* keep default detail */
    }
    throw new ScanError(detail);
  }

  const data = await resp.json();
  return {
    websiteUrl: data.websiteUrl,
    companyName: data.companyName,
    siteSummary: data.siteSummary ?? "",
    scannedText: data.scannedText ?? "",
    knowledgeBase: {
      pagesIndexed: data.knowledgeBase?.pagesIndexed ?? 0,
      pages: data.knowledgeBase?.pages ?? [],
    },
    industry: data.industry,
    industryLabel: data.industryLabel,
    industryConfidence: data.industryConfidence,
    industryTopics: data.industryTopics,
    usedSearch: data.usedSearch,
    crawlFailed: data.crawlFailed,
    llm: data.llm,
  };
}
