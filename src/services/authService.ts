// Persona authentication. The user signs in as a business persona (Customer,
// Accountant, CFO, CEO); the backend mints a scoped API key that is sent as
// X-API-Key on every request so RBAC is enforced server-side. Permissions are
// also kept client-side to adapt the UI (show/hide tabs, gate actions).

import type { ClearanceLevel, OrgStructure } from "../types";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export type AdminTier = "system" | "department" | "group" | "member" | "external";

// A selectable org seat, as returned by GET /api/login/seats.
export interface SeatOption {
  id: string;
  tier: AdminTier;
  department: string | null;
  group: string | null;
  label: string;
  clearance: ClearanceLevel;
}

// What the client sends to POST /api/login to claim a seat.
export interface SeatLogin {
  tier: AdminTier;
  department?: string | null;
  group?: string | null;
  workspaceId?: string | null;
}

export interface AuthSession {
  apiKey: string;
  role: string; // the seat label (e.g. "Finance · Department Head")
  label: string;
  description: string;
  permissions: string[];
  clearance: ClearanceLevel;
  adminTier: AdminTier;
  department: string | null;
  group: string | null;
}

// In-memory only (intentionally NOT persisted): every fresh load starts at the
// login screen, and the workspace is re-selected after signing in.
let _session: AuthSession | null = null;

export function getAuth(): AuthSession | null {
  return _session;
}

function saveAuth(session: AuthSession | null) {
  _session = session;
}

// Headers helper used by every API call so the persona's key always travels.
export function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const headers: Record<string, string> = { ...(extra ?? {}) };
  if (_session?.apiKey) headers["X-API-Key"] = _session.apiKey;
  return headers;
}

// Permission check mirroring the backend's wildcard rules:
//   "*" grants everything; "read:all" grants any "read:*".
export function hasPermission(required: string, session = _session): boolean {
  if (!session) return false;
  const [rAction] = required.split(":");
  return session.permissions.some((g) => {
    if (g === "*" || g === required) return true;
    const [gAction, gRest] = g.split(":");
    return gRest === "all" && gAction === rAction;
  });
}

// True if the persona satisfies ANY of the supplied permissions.
export function hasAny(required: string[], session = _session): boolean {
  return required.length === 0 || required.some((r) => hasPermission(r, session));
}

// The org chart + selectable seats for a workspace (or a generic default before
// any workspace is chosen, e.g. when provisioning a new stack).
export async function fetchSeats(
  workspaceId?: string | null,
): Promise<{ org: OrgStructure; seats: SeatOption[] } | null> {
  try {
    const q = workspaceId ? `?workspaceId=${encodeURIComponent(workspaceId)}` : "";
    const resp = await fetch(`${API_BASE}/api/login/seats${q}`);
    if (!resp.ok) return null;
    return (await resp.json()) as { org: OrgStructure; seats: SeatOption[] };
  } catch {
    return null;
  }
}

export async function login(seat: SeatLogin): Promise<AuthSession | null> {
  try {
    const resp = await fetch(`${API_BASE}/api/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tier: seat.tier,
        department: seat.department ?? null,
        group: seat.group ?? null,
        workspaceId: seat.workspaceId ?? null,
      }),
    });
    if (!resp.ok) return null;
    const data = (await resp.json()) as AuthSession;
    saveAuth(data);
    return data;
  } catch {
    return null;
  }
}

export function logout() {
  saveAuth(null);
}
