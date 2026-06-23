// Core domain types for StackLaunch AI

export type IndustryKey =
  | "transport"
  | "banking"
  | "retail"
  | "healthcare"
  | "real_estate"
  | "telecom"
  | "education"
  | "hospitality"
  | "insurance"
  | "technology"
  | "generic_services";

export type Channel = "WhatsApp" | "Phone" | "Email" | "Web";

export type CRMStatus = "active" | "at_risk" | "inactive";

export interface CRMRecord {
  customerId: string;
  name: string;
  segment: string;
  city: string;
  email: string;
  phone: string;
  lifetimeValueEgp: number;
  lastInteraction: string;
  preferredChannel: Channel;
  status: CRMStatus;
}

export interface ERPRecord {
  recordId: string;
  entityType: string;
  name: string;
  revenueEgp: number;
  costEgp: number;
  marginPercent: number;
  utilizationPercent: number;
  period: string;
}

export type TicketPriority = "Low" | "Medium" | "High" | "Critical";
export type TicketStatus = "Open" | "Pending" | "Resolved" | "Escalated";
export type Sentiment = "positive" | "neutral" | "negative";
export type SlaStatus = "within_sla" | "at_risk" | "breached";

export interface TicketRecord {
  ticketId: string;
  customerId: string;
  category: string;
  priority: TicketPriority;
  status: TicketStatus;
  createdAt: string;
  channel: Channel;
  summary: string;
  sentiment: Sentiment;
  slaStatus: SlaStatus;
  // Helper: which ERP entity (route/branch/product...) this ticket is linked to.
  linkedEntity?: string;
}

export interface ConnectorBase {
  id: string;
  name: string;
  datasetType: string;
  status: "Demo Connected";
  recordCount: number;
  lastSync: string;
  access: "Governed";
  piiMasking: boolean;
  // Owning department + baseline data classification (enterprise RBAC).
  department?: string | null;
  classification?: ClearanceLevel;
}

export interface CRMConnector extends ConnectorBase {
  records: CRMRecord[];
}

export interface ERPConnector extends ConnectorBase {
  records: ERPRecord[];
}

export interface TicketingConnector extends ConnectorBase {
  records: TicketRecord[];
}

export interface KnowledgePage {
  url: string;
  title: string;
  summary: string;
  topics: string[];
  // Longer real text extracted from the page, used for retrieval-based answers.
  content?: string;
}

export interface KnowledgeBase {
  pagesIndexed: number;
  pages: KnowledgePage[];
}

export interface AuditEvent {
  id: string;
  type:
    | "industry_detected"
    | "website_scanned"
    | "knowledge_base_built"
    | "mock_crm_generated"
    | "mock_erp_generated"
    | "mock_ticketing_generated"
    | "connector_query_executed"
    | "pii_masking_applied"
    | "cross_source_insight_generated"
    | "guardrail_triggered"
    | "assistant_answered";
  message: string;
  actor: string;
  timestamp: string;
}

export interface Observability {
  websiteScans: number;
  knowledgeQueries: number;
  connectorQueries: number;
  crmQueries: number;
  erpQueries: number;
  ticketingQueries: number;
  crossSourceAnswers: number;
  piiMaskingEvents: number;
  guardrailBlocks: number;
  totalAssistantAnswers: number;
}

export interface Guardrail {
  id: string;
  title: string;
  description: string;
  status: "active";
}

export interface Role {
  name: string;
  description: string;
  permissions: string[];
}

export type SourceType =
  | "Website Knowledge"
  | "CRM Demo Dataset"
  | "ERP Demo Dataset"
  | "Ticketing Demo Dataset"
  | "Approved Web Source";

// --- Precomputed analytics (computed entirely on the backend) ---

export interface CountItem {
  label: string;
  count: number;
  percent: number;
}

export interface ErpEntitySummary {
  name: string;
  entityType: string;
  revenueEgp: number;
  marginPercent: number;
  utilizationPercent: number;
}

export interface EntityComplaint {
  entity: string;
  complaints: number;
  negative: number;
  revenueEgp?: number | null;
  marginPercent?: number | null;
  complaintRate: number;
}

export interface TicketSummary {
  total: number;
  byCategory: CountItem[];
  bySentiment: CountItem[];
  bySlaStatus: CountItem[];
  byPriority: CountItem[];
  byStatus: CountItem[];
  byChannel: CountItem[];
  openOrEscalated: number;
  negativeRate: number;
  slaBreachRate: number;
  recentWeekCount: number;
  topCategory: CountItem | null;
}

export interface CRMSummary {
  total: number;
  bySegment: CountItem[];
  byStatus: CountItem[];
  byCity: CountItem[];
  byChannel: CountItem[];
  atRiskCount: number;
  atRiskHighValue: { customerId: string; segment: string; city: string; lifetimeValueEgp: number }[];
  avgLifetimeValue: number;
  totalLifetimeValue: number;
}

export interface ERPSummary {
  total: number;
  byEntityType: CountItem[];
  topRevenue: ErpEntitySummary[];
  lowestMargin: ErpEntitySummary[];
  lowestUtilization: ErpEntitySummary[];
  totalRevenueEgp: number;
  totalCostEgp: number;
  avgMarginPercent: number;
}

export interface CrossSourceSummary {
  tickets: TicketSummary;
  crm: CRMSummary;
  erp: ERPSummary;
  complaintsByEntity: EntityComplaint[];
  highRevenuePoorSentiment: EntityComplaint[];
}

export interface Project {
  id: string;
  websiteUrl: string;
  companyName: string;
  // Real description scraped from the site (meta description / first paragraph).
  siteSummary?: string;
  industry: IndustryKey;
  industryLabel: string;
  industryConfidence: number;
  createdAt: string;
  apiKey: string;
  knowledgeBase: KnowledgeBase;
  connectors: {
    crm: CRMConnector;
    erp: ERPConnector;
    ticketing: TicketingConnector;
  };
  audit: AuditEvent[];
  observability: Observability;
  guardrails: Guardrail[];
  roles: Role[];
  // Precomputed on the backend so the dashboard renders without any client logic.
  analytics: CrossSourceSummary;
  // Industry-tailored demo questions, chosen by the backend.
  suggestedQuestions: string[];
  // Present when the LLM grounded the synthetic datasets in the real site.
  dataProfile?: DataProfile | null;
  // Industry-derived org chart + data classification (enterprise RBAC).
  orgStructure?: OrgStructure | null;
}

export type ClearanceLevel = "public" | "internal" | "confidential" | "restricted";

export interface OrgDepartment {
  name: string;
  groups: string[];
}

export interface DataDomain {
  department: string | null;
  classification: ClearanceLevel;
}

export interface OrgStructure {
  industry: string;
  clearanceLevels: ClearanceLevel[];
  departments: OrgDepartment[];
  dataDomains: Record<string, DataDomain>;
}

export interface DataProfile {
  currency: string;
  segments: string[];
  cities: string[];
  products: { entity_type: string; name: string }[];
  ticket_categories: string[];
  scale: { ltv?: [number, number]; monthly_revenue?: [number, number] };
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: SourceType[];
  computedFrom?: string[];
  guardrailNote?: string;
  timestamp: string;
  // Live agent trace: which tools/specialists ran to produce this answer.
  activity?: string[];
  mode?: string;
}
