import type { AuthSession } from "./services/authService";
import type { ClearanceLevel } from "./types";

// Client-side mirror of the backend's orgmodel scope rules (orgmodel.py). The
// server remains the source of truth and re-enforces everything on the agent and
// API; this keeps the data tabs visually consistent with what the active seat is
// actually allowed to see, so the UI never shows data the assistant would refuse.

const RANK: Record<ClearanceLevel, number> = {
  public: 0,
  internal: 1,
  confidential: 2,
  restricted: 3,
};

export function deptInScope(
  auth: AuthSession | null,
  ownerDepartment?: string | null,
): boolean {
  if (!ownerDepartment) return true; // public / org-wide resource
  if (!auth) return false;
  if (auth.adminTier === "system") return true; // cross-department
  if (!auth.department) return true; // legacy / full-access principal
  return auth.department === ownerDepartment;
}

// Financial figures (revenue, margin, lifetime value) require Confidential+.
export function canSeeFinancials(auth: AuthSession | null): boolean {
  if (!auth) return false;
  return (RANK[auth.clearance] ?? 0) >= RANK.confidential;
}

export const REDACTED = "🔒";
