"""Generate a fully synthetic FastESM database (deterministic, no PII).

Builds an enterprise with four service-owning departments (IT, HR, Facilities,
Finance), a role-based workforce (Employee / Agent / Manager / Admin), a service
catalog of config-driven request forms, and a live queue of service requests
flowing through approval and fulfilment with SLA timers.
"""
from __future__ import annotations

import json
import random
from datetime import timedelta

import db

RNG = random.Random(20260716)
NOW = db.NOW


def _dt(mins_ago: float) -> str:
    return (NOW - timedelta(minutes=mins_ago)).strftime("%Y-%m-%d %H:%M:%S")


DEPARTMENTS = [("IT", "💻"), ("HR", "👥"), ("Facilities", "🏢"), ("Finance", "💶")]

# People: (name, role, department). Employees raise requests; Agents fulfil;
# Managers approve; Admin configures.
PEOPLE = [
    ("Sanne de Vries", "Manager", "IT"),
    ("Tom Becker", "Agent", "IT"),
    ("Lena Sokolova", "Agent", "IT"),
    ("Ravi Menon", "Manager", "HR"),
    ("Aisha Bello", "Agent", "HR"),
    ("Marco Bianchi", "Manager", "Facilities"),
    ("Kenji Watanabe", "Agent", "Facilities"),
    ("Sara Lindholm", "Manager", "Finance"),
    ("Diego Ramos", "Agent", "Finance"),
    ("Priya Nair", "Admin", "IT"),
    # employees (requesters)
    ("Alex Cooper", "Employee", "IT"),
    ("Sam Patel", "Employee", "HR"),
    ("Jordan Nguyen", "Employee", "Facilities"),
    ("Robin Garcia", "Employee", "Finance"),
    ("Casey Schmidt", "Employee", "IT"),
    ("Morgan Khan", "Employee", "HR"),
    ("Riley Rossi", "Employee", "Facilities"),
    ("Jamie Larsen", "Employee", "Finance"),
]

# Service catalog: (name, dept, category, icon, sla_hours, requires_approval, form schema).
SERVICES = [
    ("New laptop / hardware", "IT", "Hardware", "💻", 48, True, {"fields": [
        {"name": "device_type", "label": "Device type", "type": "select",
         "options": ["Laptop", "Desktop", "Tablet", "Monitor"], "required": True},
        {"name": "os", "label": "Operating system", "type": "select",
         "options": ["Linux", "Windows", "macOS"], "required": True},
        {"name": "justification", "label": "Business justification", "type": "textarea", "required": True,
         "hint": "Why is this needed? Manager approval is required."},
        {"name": "needed_by", "label": "Needed by", "type": "date"},
    ]}),
    ("Software / license access", "IT", "Access", "🔑", 8, False, {"fields": [
        {"name": "application", "label": "Application", "type": "text", "required": True,
         "placeholder": "e.g. Figma, Jira, Adobe CC"},
        {"name": "access_level", "label": "Access level", "type": "select",
         "options": ["Viewer", "Editor", "Admin"], "required": True},
        {"name": "reason", "label": "Reason", "type": "textarea"},
    ]}),
    ("Password / account reset", "IT", "Support", "🔒", 4, False, {"fields": [
        {"name": "system", "label": "Which system?", "type": "text", "required": True},
        {"name": "urgent", "label": "Blocking your work now?", "type": "select",
         "options": ["Yes", "No"], "required": True},
    ]}),
    ("Onboard a new hire", "HR", "People ops", "🧑‍💼", 72, True, {"fields": [
        {"name": "hire_name", "label": "New hire full name", "type": "text", "required": True},
        {"name": "start_date", "label": "Start date", "type": "date", "required": True},
        {"name": "team", "label": "Team", "type": "text", "required": True},
        {"name": "equipment", "label": "Equipment needed", "type": "textarea",
         "hint": "Laptop, phone, access cards…"},
    ]}),
    ("Time off / leave request", "HR", "People ops", "🏖️", 24, True, {"fields": [
        {"name": "leave_type", "label": "Leave type", "type": "select",
         "options": ["Annual leave", "Sick leave", "Parental", "Unpaid"], "required": True},
        {"name": "from_date", "label": "From", "type": "date", "required": True},
        {"name": "to_date", "label": "To", "type": "date", "required": True},
    ]}),
    ("Update payroll details", "HR", "Payroll", "📝", 48, False, {"fields": [
        {"name": "change_type", "label": "What changed?", "type": "select",
         "options": ["Bank account", "Address", "Tax details"], "required": True},
        {"name": "notes", "label": "Notes", "type": "textarea"},
    ]}),
    ("Desk / room booking", "Facilities", "Workplace", "🪑", 8, False, {"fields": [
        {"name": "space_type", "label": "Space", "type": "select",
         "options": ["Desk", "Meeting room", "Parking spot"], "required": True},
        {"name": "date", "label": "Date", "type": "date", "required": True},
        {"name": "duration", "label": "Duration", "type": "text", "placeholder": "e.g. full day"},
    ]}),
    ("Report a building issue", "Facilities", "Maintenance", "🔧", 12, False, {"fields": [
        {"name": "location", "label": "Location", "type": "text", "required": True,
         "placeholder": "Floor / room"},
        {"name": "issue", "label": "Describe the issue", "type": "textarea", "required": True},
        {"name": "severity", "label": "Severity", "type": "select",
         "options": ["Low", "Medium", "High"], "required": True},
    ]}),
    ("Access card / building pass", "Facilities", "Security", "🪪", 24, True, {"fields": [
        {"name": "pass_type", "label": "Pass type", "type": "select",
         "options": ["Standard", "After-hours", "Server room"], "required": True},
        {"name": "reason", "label": "Reason", "type": "textarea", "required": True},
    ]}),
    ("Expense reimbursement", "Finance", "Expenses", "🧾", 72, True, {"fields": [
        {"name": "amount", "label": "Amount (EUR)", "type": "number", "required": True},
        {"name": "category", "label": "Category", "type": "select",
         "options": ["Travel", "Meals", "Equipment", "Training", "Other"], "required": True},
        {"name": "description", "label": "Description", "type": "textarea", "required": True},
    ]}),
    ("Purchase order request", "Finance", "Procurement", "🛒", 96, True, {"fields": [
        {"name": "vendor", "label": "Vendor", "type": "text", "required": True},
        {"name": "amount", "label": "Estimated amount (EUR)", "type": "number", "required": True},
        {"name": "justification", "label": "Justification", "type": "textarea", "required": True},
    ]}),
    ("Corporate card request", "Finance", "Cards", "💳", 120, True, {"fields": [
        {"name": "limit", "label": "Requested monthly limit (EUR)", "type": "number", "required": True},
        {"name": "reason", "label": "Reason", "type": "textarea", "required": True},
    ]}),
]

REQUEST_TITLES = {
    "New laptop / hardware": ["Laptop for new starter", "Replacement laptop — screen cracked",
                              "Second monitor for home office", "Upgrade to developer laptop"],
    "Software / license access": ["Figma editor seat", "Jira admin access", "Adobe CC license",
                                  "Access to analytics dashboard"],
    "Password / account reset": ["Locked out of VPN", "Reset SSO password", "Cannot access email"],
    "Onboard a new hire": ["Onboard backend engineer", "Onboard finance analyst", "Onboard marketing lead"],
    "Time off / leave request": ["Annual leave — August", "Sick leave", "Parental leave planning"],
    "Update payroll details": ["New bank account", "Address change", "Update tax details"],
    "Desk / room booking": ["Book meeting room Thursday", "Desk for visiting colleague", "Parking for the week"],
    "Report a building issue": ["AC not working on 3rd floor", "Broken chair", "Leaking tap in kitchen"],
    "Access card / building pass": ["After-hours access", "Replacement building pass", "Server room access"],
    "Expense reimbursement": ["Client dinner reimbursement", "Conference travel", "Training course fee"],
    "Purchase order request": ["PO for monitors", "PO for SaaS renewal", "PO for office supplies"],
    "Corporate card request": ["Corporate card for travel", "Card limit increase"],
}

REQ_MSG = [
    "Hi, could you help with this? It's slowing me down.",
    "Please let me know if you need anything else from me.",
    "This is a bit time-sensitive — thanks in advance!",
    "Happy to provide more detail if useful.",
    "Following up on my request from earlier this week.",
]
AGENT_MSG = [
    "Thanks — I've picked this up and will process it shortly.",
    "This needs manager approval first; I've routed it accordingly.",
    "All set on our side. Could you confirm it's working for you?",
    "I've ordered this; expect delivery within the SLA window.",
    "Approved and fulfilled — closing this out. Let me know if anything's off.",
]
NOTE_MSG = [
    "Internal: within budget, no extra approval needed.",
    "Internal: check stock before ordering.",
    "Internal: flagged for finance review.",
]

ARTICLES = [
    ("How to request a new laptop", "Getting equipment", "IT"),
    ("Resetting your password & SSO", "Accounts & access", "IT"),
    ("Requesting software licenses", "Accounts & access", "IT"),
    ("Booking desks and meeting rooms", "Workplace", "Facilities"),
    ("Reporting a building or maintenance issue", "Workplace", "Facilities"),
    ("Getting an access card or building pass", "Workplace", "Facilities"),
    ("Booking time off and leave policy", "People & pay", "HR"),
    ("Onboarding checklist for managers", "People & pay", "HR"),
    ("Updating your payroll details", "People & pay", "HR"),
    ("Submitting an expense claim", "Money & procurement", "Finance"),
    ("Raising a purchase order", "Money & procurement", "Finance"),
    ("Corporate card policy", "Money & procurement", "Finance"),
    ("What is a service catalog?", "Using FastESM", None),
    ("Understanding SLAs and approvals", "Using FastESM", None),
]


def _pick_priority(service_name):
    if "Password" in service_name or "issue" in service_name:
        return RNG.choices(["Urgent", "High", "Medium"], weights=[3, 3, 2])[0]
    return RNG.choices(db.PRIORITIES, weights=[1, 2, 4, 2])[0]


def _fake_form(schema):
    out = {}
    for f in schema.get("fields", []):
        t = f.get("type", "text")
        if t == "select":
            out[f["name"]] = RNG.choice(f.get("options", ["N/A"]))
        elif t == "number":
            out[f["name"]] = RNG.choice([50, 120, 350, 900, 1500])
        elif t == "date":
            out[f["name"]] = (NOW + timedelta(days=RNG.randint(2, 30))).strftime("%Y-%m-%d")
        elif t == "textarea":
            out[f["name"]] = RNG.choice([
                "Needed to keep the team unblocked.",
                "Standard request as per policy.",
                "Approved verbally by my manager last week."])
        else:
            out[f["name"]] = "Provided by requester"
    return out


def build():
    db.init_schema()
    with db.cursor() as conn:
        for t in ("chat_messages", "request_activity", "request_messages", "requests",
                  "articles", "article_categories", "services", "users", "departments"):
            conn.execute(f"DELETE FROM {t}")
        conn.executemany("INSERT INTO departments(name,icon) VALUES (?,?)", DEPARTMENTS)
        dept_ids = {r["name"]: r["id"] for r in conn.execute("SELECT id,name FROM departments").fetchall()}

    # people
    users = []
    for nm, role, dept in PEOPLE:
        email = nm.lower().replace(" ", ".") + "@fastesm.example"
        users.append((nm, email, dept_ids[dept], role, RNG.choice(db.AGENT_AVAILABILITY), 1))
    with db.cursor() as conn:
        conn.executemany(
            "INSERT INTO users(name,email,department_id,role,availability,is_active) VALUES (?,?,?,?,?,?)", users)
        urows = conn.execute("SELECT id,name,role,department_id FROM users").fetchall()
    employees = [u for u in urows if u["role"] == "Employee"]
    agents_by_dept = {}
    managers_by_dept = {}
    for u in urows:
        if u["role"] == "Agent":
            agents_by_dept.setdefault(u["department_id"], []).append(u)
        elif u["role"] == "Manager":
            managers_by_dept.setdefault(u["department_id"], []).append(u)

    # services (catalog)
    svc_tuples = []
    for name, dept, cat, icon, sla, appr, schema in SERVICES:
        svc_tuples.append((name, dept_ids[dept], cat, _svc_desc(name), icon, sla, 1 if appr else 0,
                           json.dumps(schema), 1))
    with db.cursor() as conn:
        conn.executemany(
            """INSERT INTO services(name,department_id,category,description,icon,sla_hours,requires_approval,form_schema,is_active)
               VALUES (?,?,?,?,?,?,?,?,?)""", svc_tuples)
        srows = conn.execute("SELECT id,name,department_id,sla_hours,requires_approval FROM services").fetchall()
    svc_by_name = {s["name"]: s for s in srows}

    # knowledge base
    cats = sorted({c for _, c, _ in ARTICLES})
    with db.cursor() as conn:
        conn.executemany("INSERT INTO article_categories(name,icon) VALUES (?,?)", [(c, "📘") for c in cats])
        cat_ids = {r["name"]: r["id"] for r in conn.execute("SELECT id,name FROM article_categories").fetchall()}
        arts = [(title, cat_ids[cat], dept_ids.get(dept) if dept else None,
                 f"## {title}\n\nThis article explains **{title.lower()}** step by step. It is synthetic demo "
                 "content for FastESM.\n\n1. Open the Service Catalog.\n2. Pick the matching service.\n"
                 "3. Fill in the form and submit — you'll get a request reference to track.",
                 RNG.choice([p[0] for p in PEOPLE]), "Published", RNG.randint(30, 5000),
                 _dt(RNG.randint(10000, 300000)))
                for title, cat, dept in ARTICLES]
        conn.executemany(
            """INSERT INTO articles(title,category_id,department_id,content,author,status,views,published_on)
               VALUES (?,?,?,?,?,?,?,?)""", arts)

    # requests (the live queue)
    status_weights = [("Submitted", 8), ("Pending Approval", 10), ("Approved", 6),
                      ("In Progress", 16), ("Fulfilled", 34), ("Rejected", 4), ("Cancelled", 4)]
    statuses = [s for s, w in status_weights for _ in range(w)]
    reqs, n = [], 64
    for i in range(n):
        svc_name = RNG.choice(list(REQUEST_TITLES))
        svc = svc_by_name[svc_name]
        title = RNG.choice(REQUEST_TITLES[svc_name])
        requester = RNG.choice(employees)
        status = RNG.choice(statuses)
        # a Pending-Approval status only makes sense for approval services
        if status == "Pending Approval" and not svc["requires_approval"]:
            status = "In Progress"
        pri = _pick_priority(svc_name)
        if status in db.OPEN_STATUSES:
            created_min = RNG.randint(20, 4000)
        else:
            created_min = RNG.randint(120, 22000)
        resp_target = db.SLA_RESPONSE[pri]
        res_minutes = svc["sla_hours"] * 60
        created = NOW - timedelta(minutes=created_min)
        response_by = created + timedelta(minutes=resp_target)
        resolution_by = created + timedelta(minutes=res_minutes)

        first_resp = None
        if status not in ("Submitted", "Pending Approval") or RNG.random() < 0.4:
            lateness = RNG.choice([0.3, 0.6, 0.9, 1.2, 1.8])
            first_resp = created + timedelta(minutes=resp_target * lateness)

        approved_on = None
        approver_id = None
        if svc["requires_approval"] and status in ("Approved", "In Progress", "Fulfilled"):
            approved_on = created + timedelta(minutes=RNG.randint(60, 800))
            mgrs = managers_by_dept.get(svc["department_id"], [])
            approver_id = RNG.choice(mgrs)["id"] if mgrs else None

        resolved = None
        rating = None
        if status in db.CLOSED_STATUSES:
            lateness = RNG.choice([0.4, 0.7, 1.0, 1.1, 1.6])
            resolved = created + timedelta(minutes=res_minutes * lateness)
            if resolved > NOW:
                resolved = NOW - timedelta(minutes=RNG.randint(10, 2000))
            elif RNG.random() < 0.4:
                resolved = NOW - timedelta(minutes=RNG.randint(30, 700))
            if status == "Fulfilled":
                rating = RNG.choices([5, 4, 3, 2, 1], weights=[40, 30, 15, 8, 7])[0]

        # assignee: unassigned only while brand-new; else a dept agent
        assignee_id = None
        if status not in ("Submitted", "Pending Approval") or RNG.random() > 0.5:
            ags = agents_by_dept.get(svc["department_id"], [])
            if ags:
                assignee_id = RNG.choice(ags)["id"]

        form_data = _fake_form(json.loads(
            db.one("SELECT form_schema FROM services WHERE id=?", (svc["id"],))["form_schema"]))

        reqs.append((
            f"REQ-{i+1:05d}", title, svc["id"], svc["department_id"], requester["id"],
            assignee_id, approver_id, status, pri, json.dumps(form_data),
            created.strftime("%Y-%m-%d %H:%M:%S"),
            response_by.strftime("%Y-%m-%d %H:%M:%S"),
            resolution_by.strftime("%Y-%m-%d %H:%M:%S"),
            first_resp.strftime("%Y-%m-%d %H:%M:%S") if first_resp else None,
            approved_on.strftime("%Y-%m-%d %H:%M:%S") if approved_on else None,
            resolved.strftime("%Y-%m-%d %H:%M:%S") if resolved else None,
            rating,
        ))
    with db.cursor() as conn:
        conn.executemany(
            """INSERT INTO requests
               (ref,title,service_id,department_id,requester_id,assignee_id,approver_id,status,priority,
                form_data,created,response_by,resolution_by,first_responded_on,approved_on,resolved_on,feedback_rating)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", reqs)
        rrows = conn.execute(
            "SELECT id,created,first_responded_on,approved_on,resolved_on,status FROM requests").fetchall()

    # conversation + activity
    msgs, acts = [], []
    for t in rrows:
        msgs.append((t["id"], "requester", "Requester", RNG.choice(REQ_MSG), t["created"]))
        acts.append((t["id"], "Request raised via catalog", "Requester", t["created"]))
        if t["approved_on"]:
            acts.append((t["id"], "✅ Approved by manager", "Manager", t["approved_on"]))
        if t["first_responded_on"]:
            msgs.append((t["id"], "agent", "Agent", RNG.choice(AGENT_MSG), t["first_responded_on"]))
            acts.append((t["id"], "First response sent", "Agent", t["first_responded_on"]))
            if RNG.random() < 0.45:
                msgs.append((t["id"], "note", "Agent", RNG.choice(NOTE_MSG), t["first_responded_on"]))
        if t["resolved_on"]:
            msgs.append((t["id"], "agent", "Agent", RNG.choice(AGENT_MSG), t["resolved_on"]))
            acts.append((t["id"], f"Marked {t['status']}", "Agent", t["resolved_on"]))
    with db.cursor() as conn:
        conn.executemany(
            "INSERT INTO request_messages(request_id,sender,author,body,created) VALUES (?,?,?,?,?)", msgs)
        conn.executemany(
            "INSERT INTO request_activity(request_id,action,actor,created) VALUES (?,?,?,?)", acts)

    print(f"FastESM seeded → {db.DB_PATH}")
    print(f"  {len(DEPARTMENTS)} departments · {len(users)} people · {len(SERVICES)} catalog services · "
          f"{n} requests · {len(arts)} KB articles · {len(msgs)} messages")


def _svc_desc(name: str) -> str:
    return {
        "New laptop / hardware": "Order a laptop, desktop, monitor or other IT hardware. Needs manager approval.",
        "Software / license access": "Request access to an application or a software license seat.",
        "Password / account reset": "Locked out or need a password reset? Fast-tracked support.",
        "Onboard a new hire": "Kick off onboarding for a new team member — accounts, equipment and access.",
        "Time off / leave request": "Book annual, sick, parental or unpaid leave. Routed to your manager.",
        "Update payroll details": "Change your bank account, address or tax details on file.",
        "Desk / room booking": "Reserve a desk, meeting room or parking spot.",
        "Report a building issue": "Report a maintenance or facilities problem in the building.",
        "Access card / building pass": "Request a building pass or upgraded access. Needs approval.",
        "Expense reimbursement": "Claim back an approved business expense. Routed for sign-off.",
        "Purchase order request": "Raise a purchase order for goods or services. Needs approval.",
        "Corporate card request": "Request a corporate card or a limit change. Needs approval.",
    }.get(name, "A catalog service.")


if __name__ == "__main__":
    build()
