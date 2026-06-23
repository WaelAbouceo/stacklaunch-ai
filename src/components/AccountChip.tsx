import { useApp } from "../store/AppContext";

// A compact "signed in as X · Switch account" control for the build-phase
// screens, so the user can switch personas without entering the workspace.
export default function AccountChip() {
  const { auth, logout } = useApp();
  if (!auth) return null;
  return (
    <div className="account-chip">
      <span className="faint">Signed in as</span>
      <span className="account-role">{auth.role}</span>
      <button className="account-switch" onClick={logout}>
        ⇄ Switch account
      </button>
    </div>
  );
}
