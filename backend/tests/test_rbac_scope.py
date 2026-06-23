"""Department-scope + clearance enforcement (enterprise RBAC, Phase 4)."""

from agentic import agent as agent_module
from data import analytics
from governance import orgmodel
from data import projectbuilder
from agentic import tools as tools_module


def _telecom_project() -> dict:
    scan = {"websiteUrl": "https://t.eg", "knowledgeBase": {"pagesIndexed": 1, "pages": []}, "siteSummary": "s"}
    return projectbuilder.build_project(scan, "Telco", "telecom", 0.9)


def _ctx(project, **scope) -> tools_module.ToolContext:
    summary = analytics.build_cross_source_summary(project["connectors"])
    return tools_module.ToolContext(
        project=project, summary=summary, company="Telco", **scope
    )


# --- Scope predicate ------------------------------------------------------

def test_department_in_scope_rules():
    # System sees everything; a scoped member sees only their own department.
    assert orgmodel.department_in_scope("Finance", "department", "Finance")
    assert not orgmodel.department_in_scope("Finance", "member", "Customer Care")
    assert orgmodel.department_in_scope("Finance", "member", None)  # public resource
    assert orgmodel.department_in_scope("Finance", "system", "Customer Care")  # system override
    assert orgmodel.department_in_scope(None, None, "Finance")  # legacy/anonymous = cross-dept


# --- Tool visibility ------------------------------------------------------

def test_finance_member_sees_only_finance_connector_tools():
    project = _telecom_project()
    ctx = _ctx(project, clearance="internal", admin_tier="member", department="Finance")
    registry = tools_module.build_registry()
    in_scope = {t.name for t in registry if agent_module._connector_in_scope(t, ctx)}
    # ERP belongs to Finance -> visible; CRM (Retail & Sales) and ticketing
    # (Customer Care) belong to other departments -> hidden.
    assert "get_erp_summary" in in_scope
    assert "get_crm_summary" not in in_scope
    assert "get_ticketing_summary" not in in_scope
    # Non-connector tools are always in scope.
    assert "search_knowledge_base" in in_scope


# --- Field-level clearance redaction --------------------------------------

def test_member_clearance_redacts_financials():
    project = _telecom_project()
    by_name = tools_module.registry_by_name(tools_module.build_registry())

    member = _ctx(project, clearance="internal", admin_tier="member", department="Finance")
    erp = tools_module._erp_summary(member, {})
    assert erp.get("totalRevenueEgp") == tools_module._REDACTED
    assert "_clearance" in erp

    head = _ctx(project, clearance="restricted", admin_tier="department", department="Finance")
    erp_head = tools_module._erp_summary(head, {})
    assert isinstance(erp_head.get("totalRevenueEgp"), (int, float))


def test_at_risk_requires_confidential():
    project = _telecom_project()
    member = _ctx(project, clearance="internal", admin_tier="member", department="Retail & Sales")
    out = tools_module._at_risk_customers(member, {})
    assert out.get("error") == "clearance_required"


def test_query_blocks_cross_department_table():
    project = _telecom_project()
    finance_member = _ctx(project, clearance="internal", admin_tier="member", department="Finance")
    # CRM is owned by Retail & Sales -> a Finance member cannot query it.
    out = tools_module._query_internal_data(finance_member, {"query": {"table": "crm"}})
    assert out.get("error") == "department_scope"


def test_cross_source_blocked_for_department_seat_allowed_for_system():
    project = _telecom_project()
    # Even a department HEAD is single-department -> cross-source is denied.
    head = _ctx(project, clearance="restricted", admin_tier="department", department="Finance")
    assert tools_module._cross_source_insights(head, {}).get("error") == "department_scope"
    # System (default ctx) spans departments -> allowed.
    system = _ctx(project)
    assert "complaintsByEntity" in tools_module._cross_source_insights(system, {})


def test_cross_source_tool_hidden_from_department_seat():
    project = _telecom_project()
    ctx = _ctx(project, clearance="restricted", admin_tier="department", department="Finance")
    visible = {t.name for t in tools_module.build_registry()
               if agent_module._connector_in_scope(t, ctx)}
    assert "get_cross_source_insights" not in visible
