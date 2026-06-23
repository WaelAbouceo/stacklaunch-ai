"""Industry configuration (ported from the former frontend data/industries.ts).

This is the single source of truth for industry taxonomy, demo-data shaping,
and suggested questions. The frontend no longer holds any of this.
"""

from __future__ import annotations

EGYPT_CITIES = [
    "Cairo", "Giza", "Alexandria", "Hurghada", "Luxor",
    "Aswan", "Mansoura", "Tanta", "Port Said", "Sharm El Sheikh",
]

INDUSTRIES: dict[str, dict] = {
    "transport": {
        "label": "Transport / Intercity Bus",
        "keywords": [
            "bus", "buses", "route", "routes", "booking", "book a trip",
            "passenger", "passengers", "station", "schedule", "departure",
            "fleet", "trip", "intercity", "travel", "ticket",
        ],
        "crm_segments": [
            "Frequent Passenger", "Business Traveler", "Student",
            "Family Traveler", "Occasional Passenger",
        ],
        "erp_entities": [
            {"entity_type": "route", "names": [
                "Cairo - Hurghada", "Cairo - Alexandria", "Cairo - Luxor",
                "Cairo - Aswan", "Cairo - Sharm El Sheikh",
                "Alexandria - Marsa Matrouh", "Giza - Fayoum", "Cairo - Port Said",
            ]},
            {"entity_type": "bus", "names": [
                "Mercedes Travego #11", "Scania Touring #04", "MAN Lion's Coach #19",
                "Volvo 9700 #22", "Mercedes Tourismo #08",
            ]},
            {"entity_type": "trip", "names": [
                "Morning Express", "Night Sleeper", "Afternoon Direct",
                "Weekend Premium", "Dawn Economy",
            ]},
            {"entity_type": "station", "names": [
                "Cairo Gateway", "Alexandria Moharam Bek", "Hurghada Terminal", "Aswan Central",
            ]},
            {"entity_type": "maintenance", "names": [
                "Engine Overhaul", "Tire Replacement", "AC Service", "Brake Inspection",
            ]},
        ],
        "ticket_categories": [
            "Refund", "Delay", "Seat Issue", "Lost Item",
            "Booking Problem", "App Issue", "Driver Complaint",
        ],
        "suggested_questions": [
            "What are the top passenger complaints this week?",
            "Which route has the highest complaint rate?",
            "Which routes have high revenue but poor sentiment?",
            "Which customers are at risk of churn?",
            "Create an action plan for improving the worst-performing route.",
        ],
        "business_description": (
            "an intercity bus and passenger transport operator offering online booking, "
            "scheduled routes, and onboard services across Egypt"
        ),
    },
    "banking": {
        "label": "Banking / Financial Services",
        "keywords": [
            "loan", "loans", "card", "credit card", "account", "branch",
            "banking", "deposit", "savings", "mortgage", "interest rate",
            "atm", "kyc", "transfer", "wallet",
        ],
        "crm_segments": ["Retail Banking", "Premium", "SME", "Youth", "Payroll"],
        "erp_entities": [
            {"entity_type": "branch", "names": [
                "Downtown Cairo Branch", "Maadi Branch", "Nasr City Branch",
                "Alexandria Stanley Branch", "Heliopolis Branch", "Zamalek Branch",
            ]},
            {"entity_type": "product", "names": [
                "Personal Loan", "Credit Card Platinum", "Savings Account",
                "Auto Loan", "Home Mortgage", "Payroll Account",
            ]},
            {"entity_type": "service_request", "names": [
                "Card Replacement", "Limit Increase", "Statement Request", "Cheque Book",
            ]},
            {"entity_type": "campaign", "names": [
                "Summer Loan Offer", "Cashback Q2", "Youth Account Drive",
            ]},
            {"entity_type": "operational_kpi", "names": [
                "Onboarding Time", "Branch NPS", "Loan Approval Rate", "Dispute Resolution",
            ]},
        ],
        "ticket_categories": [
            "Card Issue", "Account Access", "Loan Inquiry",
            "KYC Pending", "Transaction Dispute", "Mobile Banking",
        ],
        "suggested_questions": [
            "What are the top customer complaints by product?",
            "Which customer segment has the most unresolved tickets?",
            "Which branches show high service issues?",
            "Summarize KYC-related support trends.",
            "Create a customer experience improvement plan.",
        ],
        "business_description": (
            "a retail and commercial bank offering accounts, cards, loans, and digital "
            "banking services across multiple branches in Egypt"
        ),
    },
    "retail": {
        "label": "Retail / E-commerce",
        "keywords": [
            "order", "orders", "product", "products", "delivery", "cart",
            "inventory", "shop", "store", "checkout", "shipping", "return",
            "discount", "sku", "warehouse",
        ],
        "crm_segments": [
            "High Value Shopper", "Discount Seeker", "New Customer",
            "Loyal Customer", "At Risk",
        ],
        "erp_entities": [
            {"entity_type": "product", "names": [
                "Wireless Earbuds Pro", "Smart Watch X", "Cotton T-Shirt Pack",
                "Air Fryer 5L", "Running Shoes", 'LED Monitor 27"',
            ]},
            {"entity_type": "warehouse", "names": [
                "Cairo Central DC", "Alexandria Hub", "Giza Fulfillment", "Upper Egypt Depot",
            ]},
            {"entity_type": "supplier", "names": [
                "TechSource Ltd", "FashionLine Co", "HomeGoods Supply", "SportsGear Intl",
            ]},
            {"entity_type": "order_batch", "names": [
                "Flash Sale Batch", "Weekend Orders", "Ramadan Campaign", "Back to School",
            ]},
            {"entity_type": "inventory", "names": [
                "Electronics Stock", "Apparel Stock", "Home Stock",
            ]},
        ],
        "ticket_categories": [
            "Return", "Delivery Delay", "Payment Issue",
            "Product Complaint", "Warranty", "Missing Item",
        ],
        "suggested_questions": [
            "Which products have the most support tickets?",
            "Which customers are high-value but unhappy?",
            "What inventory issues are affecting customer experience?",
            "What are the top reasons for returns?",
            "Create a 7-day action plan to reduce delivery complaints.",
        ],
        "business_description": (
            "an e-commerce and retail company selling products online with delivery, "
            "returns, and loyalty programs across Egypt"
        ),
    },
    "healthcare": {
        "label": "Healthcare / Clinics",
        "keywords": [
            "doctor", "doctors", "clinic", "clinics", "appointment", "patient",
            "patients", "hospital", "medical", "health", "specialist", "lab",
            "insurance", "treatment", "diagnosis",
        ],
        "crm_segments": [
            "Patient", "Family Account", "Corporate Account",
            "Insurance Patient", "Follow-up Required",
        ],
        "erp_entities": [
            {"entity_type": "clinic", "names": [
                "Cardiology Clinic", "Dermatology Clinic", "Pediatrics Clinic",
                "Orthopedics Clinic", "Dental Clinic",
            ]},
            {"entity_type": "department", "names": [
                "Radiology", "Laboratory", "Emergency", "Outpatient", "Pharmacy",
            ]},
            {"entity_type": "doctor_schedule", "names": [
                "Dr. Sara Morning Shift", "Dr. Omar Evening Shift", "Dr. Mona Weekend",
            ]},
            {"entity_type": "insurance_provider", "names": [
                "MedNet", "Allianz Care", "AXA Health", "GlobeMed",
            ]},
            {"entity_type": "billing", "names": [
                "Consultation Billing", "Lab Billing", "Procedure Billing",
            ]},
        ],
        "ticket_categories": [
            "Appointment", "Insurance Issue", "Lab Result",
            "Billing Question", "Doctor Availability", "Complaint",
        ],
        "suggested_questions": [
            "What are the top appointment-related issues?",
            "Which departments have the most complaints?",
            "What insurance issues are affecting patients?",
            "Which patients require urgent follow-up?",
            "Create a patient experience improvement plan.",
        ],
        "business_description": (
            "a healthcare provider operating clinics and departments with appointment "
            "booking, insurance handling, and lab services"
        ),
    },
    "real_estate": {
        "label": "Real Estate / Property",
        "keywords": [
            "property", "properties", "apartment", "villa", "real estate",
            "compound", "listing", "rent", "buy", "developer", "unit",
            "mortgage", "broker",
        ],
        "crm_segments": [
            "Investor", "First-time Buyer", "Tenant", "Corporate Client", "VIP Buyer",
        ],
        "erp_entities": [
            {"entity_type": "project", "names": [
                "Palm Hills Compound", "New Cairo Towers", "Sheikh Zayed Villas", "Marina Resort",
            ]},
            {"entity_type": "unit", "names": [
                "Apartment A-12", "Villa V-04", "Townhouse T-07", "Studio S-21",
            ]},
            {"entity_type": "listing", "names": [
                "3BR Apartment", "Standalone Villa", "Office Space",
            ]},
            {"entity_type": "agent", "names": [
                "Sales Team North", "Sales Team South", "Leasing Team",
            ]},
            {"entity_type": "operational_kpi", "names": [
                "Lead Conversion", "Unit Turnover", "Occupancy",
            ]},
        ],
        "ticket_categories": [
            "Viewing Request", "Payment Issue", "Maintenance",
            "Contract Question", "Complaint", "Handover Delay",
        ],
        "suggested_questions": [
            "Which projects generate the most complaints?",
            "Which customer segments are most active?",
            "What are the top reasons leads drop off?",
            "Which units have high revenue but poor sentiment?",
            "Create a customer experience improvement plan.",
        ],
        "business_description": (
            "a real estate developer and broker offering residential and commercial "
            "properties for sale and rent"
        ),
    },
    "telecom": {
        "label": "Telecom / Mobile Operator",
        "keywords": [
            "mobile", "telecom", "data plan", "sim", "network", "coverage",
            "roaming", "minutes", "bundle", "internet", "fiber", "recharge", "broadband",
        ],
        "crm_segments": ["Postpaid", "Prepaid", "Enterprise", "Youth", "Home Internet"],
        "erp_entities": [
            {"entity_type": "plan", "names": [
                "Unlimited 5G", "Family Bundle", "Data Booster", "Home Fiber 100",
            ]},
            {"entity_type": "tower", "names": [
                "Cairo East Tower", "Giza West Tower", "Alexandria Coast Tower",
            ]},
            {"entity_type": "service_request", "names": [
                "SIM Swap", "Plan Upgrade", "Number Port",
            ]},
            {"entity_type": "campaign", "names": [
                "Double Data Promo", "Weekend Free Minutes",
            ]},
            {"entity_type": "operational_kpi", "names": [
                "Network Uptime", "Activation Time", "Churn Rate",
            ]},
        ],
        "ticket_categories": [
            "Network Issue", "Billing Dispute", "Plan Change",
            "SIM Issue", "Roaming", "Internet Speed",
        ],
        "suggested_questions": [
            "What are the top network-related complaints?",
            "Which plans generate the most billing disputes?",
            "Which customer segment is at highest churn risk?",
            "Where are coverage issues concentrated?",
            "Create a customer experience improvement plan.",
        ],
        "business_description": (
            "a telecommunications operator providing mobile plans, home internet, "
            "and connectivity services"
        ),
    },
    "education": {
        "label": "Education / Training",
        "keywords": [
            "course", "courses", "student", "students", "enroll", "tuition",
            "school", "university", "academy", "training", "class", "lecture",
            "curriculum", "exam",
        ],
        "crm_segments": [
            "Prospective Student", "Enrolled Student", "Alumni",
            "Corporate Trainee", "Parent",
        ],
        "erp_entities": [
            {"entity_type": "program", "names": [
                "Data Science Diploma", "MBA Track", "English Bootcamp", "Coding Academy",
            ]},
            {"entity_type": "course", "names": [
                "Intro to Python", "Financial Accounting", "Digital Marketing",
            ]},
            {"entity_type": "campus", "names": [
                "Cairo Campus", "Alexandria Campus", "Online Campus",
            ]},
            {"entity_type": "instructor", "names": [
                "Faculty Group A", "Faculty Group B", "Guest Lecturers",
            ]},
            {"entity_type": "operational_kpi", "names": [
                "Enrollment Rate", "Completion Rate", "Satisfaction",
            ]},
        ],
        "ticket_categories": [
            "Enrollment", "Payment Issue", "Schedule Conflict",
            "Course Content", "Certificate", "Complaint",
        ],
        "suggested_questions": [
            "What are the top enrollment-related issues?",
            "Which programs have the most complaints?",
            "Which students are at risk of dropping out?",
            "What payment issues are most common?",
            "Create a student experience improvement plan.",
        ],
        "business_description": (
            "an education and training provider offering programs, courses, and "
            "certifications across multiple campuses"
        ),
    },
    "hospitality": {
        "label": "Hospitality / Hotels",
        "keywords": [
            "hotel", "resort", "reservation", "room", "booking", "stay", "guest",
            "check-in", "spa", "restaurant", "suite", "vacation", "accommodation",
        ],
        "crm_segments": [
            "Leisure Guest", "Business Guest", "VIP Member", "Group Booking", "Repeat Guest",
        ],
        "erp_entities": [
            {"entity_type": "property", "names": [
                "Red Sea Resort", "Cairo City Hotel", "Nile View Hotel", "Desert Lodge",
            ]},
            {"entity_type": "room_type", "names": [
                "Deluxe Sea View", "Standard Room", "Family Suite", "Executive Suite",
            ]},
            {"entity_type": "outlet", "names": [
                "Main Restaurant", "Rooftop Bar", "Spa", "Conference Hall",
            ]},
            {"entity_type": "campaign", "names": [
                "Summer Getaway", "Weekend Escape", "Honeymoon Package",
            ]},
            {"entity_type": "operational_kpi", "names": [
                "Occupancy Rate", "ADR", "Guest Satisfaction",
            ]},
        ],
        "ticket_categories": [
            "Reservation", "Room Issue", "Billing",
            "Service Complaint", "Amenity Request", "Cancellation",
        ],
        "suggested_questions": [
            "What are the top guest complaints this week?",
            "Which properties have high revenue but poor sentiment?",
            "Which guest segments are most valuable?",
            "What service issues are most common?",
            "Create a guest experience improvement plan.",
        ],
        "business_description": (
            "a hospitality group operating hotels and resorts with reservations, "
            "dining, and guest services"
        ),
    },
    "insurance": {
        "label": "Insurance",
        "keywords": [
            "insurance", "policy", "claim", "premium", "coverage", "underwriting",
            "life insurance", "health insurance", "motor", "renewal",
            "beneficiary", "actuary",
        ],
        "crm_segments": ["Individual", "Corporate", "SME", "High Net Worth", "Renewal Due"],
        "erp_entities": [
            {"entity_type": "policy", "names": [
                "Motor Comprehensive", "Health Family", "Life Term", "Travel Plan", "Home Cover",
            ]},
            {"entity_type": "claim_pool", "names": [
                "Motor Claims", "Health Claims", "Property Claims",
            ]},
            {"entity_type": "channel", "names": [
                "Direct Sales", "Broker Network", "Bancassurance",
            ]},
            {"entity_type": "campaign", "names": [
                "Renewal Drive", "Health Awareness", "Motor Bundle",
            ]},
            {"entity_type": "operational_kpi", "names": [
                "Claim Settlement Time", "Renewal Rate", "Loss Ratio",
            ]},
        ],
        "ticket_categories": [
            "Claim Status", "Policy Change", "Premium Payment",
            "Renewal", "Coverage Question", "Complaint",
        ],
        "suggested_questions": [
            "What are the top claim-related complaints?",
            "Which policy types generate the most tickets?",
            "Which customers are due for renewal and at risk?",
            "Where are claim delays concentrated?",
            "Create a customer experience improvement plan.",
        ],
        "business_description": (
            "an insurance provider offering motor, health, life, and property policies "
            "with claims and renewal services"
        ),
    },
    "technology": {
        "label": "Technology / Software & AI Services",
        "keywords": [
            "software", "saas", "platform", "cloud", "developer", "subscription",
            "artificial intelligence", "machine learning", "automation", "integration",
            "analytics", "dashboard", "open source", "data platform", "deployment",
        ],
        "crm_segments": ["Free Tier", "Pro", "Team", "Enterprise", "Developer"],
        "erp_entities": [
            {"entity_type": "plan", "names": [
                "Starter", "Pro", "Team", "Enterprise",
            ]},
            {"entity_type": "product", "names": [
                "Analytics Module", "API Gateway", "AI Assistant Add-on",
                "Automation Workflows", "Data Connectors",
            ]},
            {"entity_type": "service", "names": [
                "Professional Services", "Premium Support", "Onboarding & Training",
            ]},
            {"entity_type": "campaign", "names": [
                "Free Trial Drive", "Annual Upgrade Offer",
            ]},
            {"entity_type": "operational_kpi", "names": [
                "Uptime", "Net Revenue Retention", "Churn Rate",
            ]},
        ],
        "ticket_categories": [
            "Bug Report", "Billing", "API Issue", "Feature Request",
            "Integration Help", "Login / Access", "Performance",
        ],
        "suggested_questions": [
            "What are the most common bug reports this week?",
            "Which plans have the highest churn risk?",
            "Which features generate the most support tickets?",
            "Which enterprise customers are at risk of churn?",
            "Create a plan to reduce API-related support tickets.",
        ],
        "business_description": (
            "a technology company providing software, SaaS products, and AI-powered "
            "services to businesses and developers"
        ),
    },
    "generic_services": {
        "label": "General Services",
        "keywords": [],
        "crm_segments": ["New Customer", "Returning Customer", "Premium", "Corporate", "At Risk"],
        "erp_entities": [
            {"entity_type": "service", "names": [
                "Consulting", "Maintenance", "Installation", "Support Plan",
            ]},
            {"entity_type": "branch", "names": [
                "Cairo Office", "Alexandria Office", "Giza Office",
            ]},
            {"entity_type": "project", "names": [
                "Client Project A", "Client Project B", "Client Project C",
            ]},
            {"entity_type": "campaign", "names": ["Spring Promo", "Referral Program"]},
            {"entity_type": "operational_kpi", "names": [
                "Response Time", "CSAT", "Utilization",
            ]},
        ],
        "ticket_categories": [
            "General Inquiry", "Billing", "Service Request",
            "Complaint", "Technical Issue", "Feedback",
        ],
        "suggested_questions": [
            "What does this company do?",
            "What are the top customer issues?",
            "What customer segments are most active?",
            "Which operational area needs attention?",
            "Create a 7-day action plan.",
        ],
        "business_description": (
            "a services company offering professional solutions and customer support "
            "to its clients"
        ),
    },
}

# Add the cities pool to every industry.
for _cfg in INDUSTRIES.values():
    _cfg["cities"] = EGYPT_CITIES

FIRST_NAMES = [
    "Ahmed", "Mohamed", "Mahmoud", "Omar", "Youssef", "Khaled", "Hassan",
    "Sara", "Mona", "Nour", "Fatma", "Laila", "Heba", "Dina", "Yara",
    "Karim", "Tarek", "Amr", "Mostafa", "Aya", "Salma", "Reem", "Hany", "Walid",
]

LAST_NAMES = [
    "Hassan", "Ali", "Ibrahim", "Mahmoud", "Saeed", "Fawzy", "Kamel", "Nabil",
    "Shawky", "Ramadan", "Abdelrahman", "ElSayed", "Mansour", "Farouk",
    "Gamal", "Sabry", "Zaki", "Lotfy",
]

VALID_KEYS = list(INDUSTRIES.keys())


def label_for(key: str) -> str:
    return INDUSTRIES.get(key, INDUSTRIES["generic_services"])["label"]


def industry_options() -> list[dict]:
    return [{"key": k, "label": v["label"]} for k, v in INDUSTRIES.items()]


def detect_industry_by_keywords(text: str) -> tuple[str, float]:
    """Fallback keyword classifier used when no LLM is configured."""
    lowered = (text or "").lower()
    best_key = "generic_services"
    best_score = 0
    for key, cfg in INDUSTRIES.items():
        if key == "generic_services":
            continue
        score = sum(lowered.count(kw) for kw in cfg["keywords"])
        if score > best_score:
            best_score = score
            best_key = key
    confidence = 0.4 if best_score == 0 else min(0.95, 0.5 + best_score / 16)
    return best_key, confidence
