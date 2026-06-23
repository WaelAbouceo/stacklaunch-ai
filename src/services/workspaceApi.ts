import type { Project } from "../types";
import { authHeaders } from "./authService";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

// Summary row for a saved stack (as returned by GET /api/projects).
export interface WorkspaceSummary {
  id: string;
  company: string;
  industry: string;
  website: string;
  created_at: number;
}

export async function listWorkspaces(): Promise<WorkspaceSummary[]> {
  try {
    const resp = await fetch(`${API_BASE}/api/projects`, { headers: authHeaders() });
    if (!resp.ok) return [];
    const data = await resp.json();
    return (data.projects ?? []) as WorkspaceSummary[];
  } catch {
    return [];
  }
}

export async function getWorkspace(id: string): Promise<Project | null> {
  try {
    const resp = await fetch(`${API_BASE}/api/projects/${encodeURIComponent(id)}`, {
      headers: authHeaders(),
    });
    if (!resp.ok) return null;
    return (await resp.json()) as Project;
  } catch {
    return null;
  }
}

export async function deleteWorkspace(id: string): Promise<boolean> {
  try {
    const resp = await fetch(`${API_BASE}/api/projects/${encodeURIComponent(id)}`, {
      method: "DELETE",
      headers: authHeaders(),
    });
    return resp.ok;
  } catch {
    return false;
  }
}
