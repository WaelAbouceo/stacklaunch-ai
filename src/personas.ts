import type { AdminTier } from "./services/authService";
import type { ClearanceLevel } from "./types";

// Visual metadata per admin tier (icon, accent, one-line summary), shared by the
// login seat picker and the in-workspace seat switcher. Concrete permissions and
// clearance always come from the backend so the UI never drifts from real policy.
export type TierMeta = { icon: string; accent: string; summary: string };

export const TIER_META: Record<AdminTier, TierMeta> = {
  system: { icon: "👑", accent: "#8b5cf6", summary: "Platform-wide admin · all departments & data" },
  department: { icon: "🏛", accent: "#f59e0b", summary: "Department head · full dept data, audit & provisioning" },
  group: { icon: "👥", accent: "#6d8bff", summary: "Group lead · aggregated dept data up to Confidential" },
  member: { icon: "🙂", accent: "#34d399", summary: "Staff · aggregated dept insights up to Internal" },
  external: { icon: "🌐", accent: "#9aa4b2", summary: "External user · public assistant & knowledge base" },
};

export const DEFAULT_TIER_META: TierMeta = {
  icon: "👤",
  accent: "var(--brand)",
  summary: "",
};

export function tierMeta(tier: string): TierMeta {
  return TIER_META[tier as AdminTier] ?? DEFAULT_TIER_META;
}

// Color per data-classification level (matches the Governance org chart legend).
export const CLEARANCE_META: Record<ClearanceLevel, { color: string; rank: number }> = {
  public: { color: "#34d399", rank: 0 },
  internal: { color: "#6d8bff", rank: 1 },
  confidential: { color: "#f59e0b", rank: 2 },
  restricted: { color: "#f87171", rank: 3 },
};

export function clearanceColor(level: string): string {
  return CLEARANCE_META[level as ClearanceLevel]?.color ?? "var(--brand)";
}
