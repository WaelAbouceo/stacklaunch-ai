"""Role-based access control.

Turns the previously-inert `governance.DEFAULT_ROLES` into enforced policy. Each
role maps to a set of permission strings (e.g. ``read:connectors:aggregated``).
Tools and endpoints declare the permission(s) they need; `has_any` decides access,
honouring ``*`` and ``<action>:all`` wildcards (so Owner's ``read:all`` grants any
``read:*``).
"""

from __future__ import annotations

from governance import audit_events as governance

# role name -> permission set
ROLE_PERMISSIONS: dict[str, set[str]] = {
    r["name"]: set(r["permissions"]) for r in governance.DEFAULT_ROLES
}

DEFAULT_ROLE = "Owner"
ALL_PERMISSIONS = {"*"}

# Owner is full-access: grant a true wildcard so it satisfies every permission
# (its declared read:all/write:all wildcards only cover read:*/write:* actions).
if DEFAULT_ROLE in ROLE_PERMISSIONS:
    ROLE_PERMISSIONS[DEFAULT_ROLE].add("*")


def permissions_for(role: str | None) -> set[str]:
    if not role:
        return set()
    return set(ROLE_PERMISSIONS.get(role, set()))


def _matches(granted: str, required: str) -> bool:
    if granted == "*" or granted == required:
        return True
    # Wildcard at the action level: "read:all" grants "read:<anything>".
    g_action, _, g_rest = granted.partition(":")
    r_action, _, _ = required.partition(":")
    return g_rest == "all" and g_action == r_action


def has_permission(granted: set[str], required: str) -> bool:
    return any(_matches(g, required) for g in granted)


def has_any(granted: set[str], required_options: list[str]) -> bool:
    """True if the principal holds any one of the acceptable permissions."""
    if not required_options:
        return True
    return any(has_permission(granted, req) for req in required_options)
