import { useState } from "react";
import { useApp } from "../store/AppContext";
import type { AdminTier } from "../services/authService";
import { tierMeta, clearanceColor } from "../personas";

const TIERS: { tier: AdminTier; label: string; needsDept: boolean }[] = [
  { tier: "system", label: "System Admin", needsDept: false },
  { tier: "department", label: "Dept Head", needsDept: true },
  { tier: "group", label: "Group Lead", needsDept: true },
  { tier: "member", label: "Staff", needsDept: true },
  { tier: "external", label: "External", needsDept: false },
];

// In-workspace seat switcher. Flipping a seat (department × tier) re-mints the
// scoped API key without leaving the workspace, so RBAC — tabs, data scope,
// clearance, tool access — re-applies live. The core governance demo move.
export default function RoleSwitcher() {
  const { auth, project, switchSeat } = useApp();
  const departments = project?.orgStructure?.departments ?? [];
  const [dept, setDept] = useState<string>(
    auth?.department ?? departments[0]?.name ?? "",
  );
  const [pending, setPending] = useState<string | null>(null);

  if (!auth) return null;

  const pick = async (tier: AdminTier, needsDept: boolean) => {
    if (pending) return;
    const department = needsDept ? dept || departments[0]?.name : null;
    if (needsDept && !department) return;
    setPending(tier);
    await switchSeat({ tier, department, workspaceId: project?.id });
    setPending(null);
  };

  const meta = tierMeta(auth.adminTier);

  return (
    <div className="role-switcher">
      <div className="role-switcher-head">Viewing as</div>
      <div className="seat-current" style={{ ["--accent" as string]: meta.accent }}>
        <span className="seat-current-ico">{meta.icon}</span>
        <span className="seat-current-label">{auth.role}</span>
        <span
          className="class-badge"
          style={{
            color: clearanceColor(auth.clearance),
            borderColor: `color-mix(in srgb, ${clearanceColor(auth.clearance)} 45%, transparent)`,
            background: `color-mix(in srgb, ${clearanceColor(auth.clearance)} 12%, transparent)`,
          }}
        >
          {auth.clearance}
        </span>
      </div>

      {departments.length > 0 && (
        <select
          className="seat-dept"
          value={dept}
          onChange={(e) => setDept(e.target.value)}
          disabled={pending !== null}
          aria-label="Department"
        >
          {departments.map((d) => (
            <option key={d.name} value={d.name}>
              {d.name}
            </option>
          ))}
        </select>
      )}

      <div className="seat-tiers">
        {TIERS.map((t) => {
          const active =
            auth.adminTier === t.tier &&
            (!t.needsDept || auth.department === dept);
          const busy = pending === t.tier;
          const m = tierMeta(t.tier);
          return (
            <button
              key={t.tier}
              className={`seat-chip${active ? " active" : ""}`}
              style={{ ["--accent" as string]: m.accent }}
              onClick={() => pick(t.tier, t.needsDept)}
              disabled={pending !== null}
              title={m.summary}
            >
              <span className="seat-chip-ico">{busy ? "…" : m.icon}</span>
              <span className="seat-chip-name">{t.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
