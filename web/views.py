"""Center-pane page renderers for FastESM."""
from __future__ import annotations

import json

from fasthtml.common import (
    Div, H1, H3, H4, P, Span, A, Table, Thead, Tbody, Tr, Th, Td, Ul, Li,
    Strong, NotStr, Form, Input, Button, Textarea, Select, Option, Script, Label,
)

import db
from web.layout import kpi_card


def _pill(text, kind=""):
    return Span(text, cls="pill " + (kind or str(text)).lower().replace(" ", "").replace("/", ""))


def _sla(t):
    s = db.sla_state(t)
    return Span(s["label"], cls=f"sla {s['tone']}")


def _title(title, sub="", *actions):
    return Div(Div(H1(title), P(sub, cls="sub") if sub else None),
               Div(*actions) if actions else None, cls="page-title")


def _ago(ts):
    return (ts or "")[:16]


# ---------- dashboard -------------------------------------------------------

def dashboard():
    k = db.kpis()
    by_status = {r["k"]: r["n"] for r in db.counts_by("status")}
    by_dept = db.counts_by_department()

    # Plotly figure data (rendered client-side from CDN).
    status_labels = [s for s in db.REQUEST_STATUSES if by_status.get(s)]
    status_values = [by_status.get(s, 0) for s in status_labels]
    status_colors = {"Submitted": "#3b82f6", "Pending Approval": "#f59e0b", "Approved": "#6366f1",
                     "In Progress": "#06b6d4", "Fulfilled": "#059669", "Rejected": "#e11d48",
                     "Cancelled": "#94a3b8"}
    donut = {
        "data": [{"type": "pie", "hole": 0.55, "labels": status_labels, "values": status_values,
                  "marker": {"colors": [status_colors.get(s, "#6366f1") for s in status_labels]},
                  "textinfo": "label+percent", "textposition": "outside"}],
        "layout": {"margin": {"t": 10, "b": 10, "l": 10, "r": 10}, "height": 300, "showlegend": False,
                   "paper_bgcolor": "rgba(0,0,0,0)", "font": {"family": "system-ui", "size": 12}},
    }
    dept_bar = {
        "data": [{"type": "bar", "x": [d["k"] for d in by_dept], "y": [d["n"] for d in by_dept],
                  "marker": {"color": "#4f46e5"}}],
        "layout": {"margin": {"t": 10, "b": 60, "l": 40, "r": 10}, "height": 300,
                   "paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)",
                   "font": {"family": "system-ui", "size": 12}, "yaxis": {"gridcolor": "#eceef8"}},
    }
    charts_js = Script(NotStr(
        f"function _mkCharts(){{if(!window.Plotly){{setTimeout(_mkCharts,120);return;}}"
        f"Plotly.newPlot('chart-status',{json.dumps(donut['data'])},{json.dumps(donut['layout'])},"
        f"{{displayModeBar:false,responsive:true}});"
        f"Plotly.newPlot('chart-dept',{json.dumps(dept_bar['data'])},{json.dumps(dept_bar['layout'])},"
        f"{{displayModeBar:false,responsive:true}});}}_mkCharts();"))

    # SLA-risk worklist
    open_q = ",".join("?" * len(db.OPEN_STATUSES))
    open_reqs = db.rows(
        f"""SELECT r.*, s.name service, d.name department, a.name assignee FROM requests r
            LEFT JOIN services s ON s.id=r.service_id
            LEFT JOIN departments d ON d.id=r.department_id
            LEFT JOIN users a ON a.id=r.assignee_id
            WHERE r.status IN ({open_q})""", tuple(db.OPEN_STATUSES))
    risk = [t for t in open_reqs if db.sla_state(t)["breached"] or db.sla_state(t)["tone"] == "warn"]
    risk.sort(key=lambda t: not db.sla_state(t)["breached"])
    risk = risk[:8]
    risk_tbl = Table(
        Thead(Tr(Th("Ref"), Th("Request"), Th("Department"), Th("Priority"), Th("SLA"), Th("Owner"))),
        Tbody(*[Tr(Td(A(t["ref"], href=f"/requests/{t['id']}")),
                   Td(A(t["title"][:40], href=f"/requests/{t['id']}")),
                   Td(t["department"] or "—"), Td(_pill(t["priority"])), Td(_sla(t)),
                   Td(t["assignee"] or Span("Unassigned", style="color:var(--breach);")))
                for t in risk] or [Tr(Td("No SLA risks 🎉", colspan="6"))]), cls="tbl")

    return (
        _title("Service Management Dashboard", "Live SLA & cross-department workload — fully synthetic demo data."),
        Div(kpi_card("Open requests", k["open"], f"{k['unassigned']} unassigned"),
            kpi_card("Pending approval", k["pending_approval"], "awaiting a manager", tone="warn"),
            kpi_card("SLA at risk", k["breached"], "breached / overdue", tone="breach"),
            kpi_card("Fulfilled today", k["fulfilled_today"], f"CSAT {k['csat']}%", tone="ok"),
            cls="kpi-grid"),
        Div(Div(Div(H3("Requests by status"), cls="card-header"), Div(id="chart-status"), cls="card"),
            Div(Div(H3("Requests by department"), cls="card-header"), Div(id="chart-dept"), cls="card"),
            cls="grid-2"),
        Div(Div(H3("SLA at risk — act now"), cls="card-header"), risk_tbl, cls="card"),
        charts_js,
    )


# ---------- service catalog (webshop) ---------------------------------------

def catalog_list():
    svcs = db.services()
    by_dept = {}
    for s in svcs:
        by_dept.setdefault(s["department"] or "Other", []).append(s)
    blocks = []
    for dept in sorted(by_dept):
        cards = []
        for s in by_dept[dept]:
            approval = Span("Approval required", cls="svc-tag") if s["requires_approval"] else Span("Auto-fulfil", cls="svc-tag")
            cards.append(Div(
                Div(s["icon"] or "🧩", cls="svc-icon"),
                H4(s["name"]),
                Div(s["description"] or "", cls="desc"),
                Div(Span(f"SLA {s['sla_hours']}h", cls="svc-tag"), approval,
                    Span(s["category"] or "", cls="svc-tag") if s["category"] else None, cls="svc-meta"),
                A("Request this →", href=f"/catalog/{s['id']}", cls="btn primary sm", style="margin-top:4px;"),
                cls="svc-card"))
        blocks.append(Div(Div(H3(f"{by_dept[dept][0]['dept_icon'] or ''} {dept}"), cls="card-header"),
                          Div(*cards, cls="catalog-grid"), cls="card"))
    return (_title("Service Catalog", f"{len(svcs)} services across {len(by_dept)} departments — browse and request."),
            Div(NotStr("A single front door for <strong>every</strong> department. Employees browse services like a "
                       "webshop; each request flows through approval and fulfilment with its own SLA."), cls="callout"),
            *blocks)


def _render_field(field):
    name = "f_" + field["name"]
    ftype = field.get("type", "text")
    req = field.get("required", False)
    label = Label(field.get("label", field["name"]),
                  Span(" *", cls="req") if req else None)
    if ftype == "textarea":
        ctl = Textarea(field.get("default", ""), name=name, required=req,
                       placeholder=field.get("placeholder", ""))
    elif ftype == "select":
        ctl = Select(*[Option(o, value=o) for o in field.get("options", [])], name=name, required=req)
    else:
        ctl = Input(name=name, type=ftype, required=req, placeholder=field.get("placeholder", ""))
    hint = P(field["hint"], cls="hint") if field.get("hint") else None
    return Div(label, ctl, hint, cls="form-field")


def catalog_request_form(sid):
    s = db.service(sid)
    if not s:
        return _title("Service not found"), P("No such catalog item.")
    schema = db.service_schema(sid)
    fields = [_render_field(f) for f in schema.get("fields", [])]
    pri = Div(Label("Priority"),
              Select(*[Option(p, value=p, selected=(p == "Medium")) for p in db.PRIORITIES], name="priority"),
              cls="form-field")
    form = Form(*fields, pri,
                Div(Button("Submit request", cls="btn primary", type="submit"),
                    A("Cancel", href="/catalog", cls="btn"), style="display:flex;gap:8px;margin-top:6px;"),
                method="post", action=f"/catalog/{sid}/request")
    meta = Div(Span(f"Department: {s['department']}", cls="svc-tag"),
               Span(f"SLA {s['sla_hours']}h", cls="svc-tag"),
               Span("Approval required" if s["requires_approval"] else "Auto-fulfil", cls="svc-tag"),
               cls="svc-meta", style="margin-bottom:12px;")
    return (_title(f"{s['icon'] or ''} {s['name']}", s["description"] or "",
                   A("← Catalog", href="/catalog", cls="btn")),
            Div(meta,
                P("This form is rendered from the service's JSON schema — no code. "
                  "Admins edit it in the Form & Workflow Designer.", cls="sub", style="margin-bottom:14px;"),
                form, cls="card", style="max-width:640px;"))


# ---------- requests --------------------------------------------------------

def requests_list(status="Open", department="All", q=""):
    seg = Div(*[A(s, href=f"/requests?status={s}", cls="active" if status == s else "")
                for s in ["Open", "All", *db.REQUEST_STATUSES]], cls="seg")
    depts = db.departments()

    where, params = [], []
    if status == "Open":
        where.append(f"r.status IN ({','.join('?'*len(db.OPEN_STATUSES))})")
        params += db.OPEN_STATUSES
    elif status != "All":
        where.append("r.status=?")
        params.append(status)
    if department != "All":
        where.append("d.name=?")
        params.append(department)
    if q:
        where.append("(r.title LIKE ? OR r.ref LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    reqs = db.rows(
        f"""SELECT r.*, s.name service, d.name department, u.name requester, a.name assignee
            FROM requests r
            LEFT JOIN services s ON s.id=r.service_id
            LEFT JOIN departments d ON d.id=r.department_id
            LEFT JOIN users u ON u.id=r.requester_id
            LEFT JOIN users a ON a.id=r.assignee_id
            {clause} ORDER BY r.created DESC LIMIT 200""", tuple(params))

    dept_seg = Div(Span("Dept: ", style="color:var(--text-mute);font-size:12px;align-self:center;"),
                   *[A(d, href=f"/requests?status={status}&department={d}",
                       cls="active" if department == d else "")
                     for d in ["All", *[x["name"] for x in depts]]], cls="seg")

    tbl = Table(
        Thead(Tr(Th("Ref"), Th("Request"), Th("Department"), Th("Requester"), Th("Priority"),
                 Th("Status"), Th("SLA"), Th("Owner"))),
        Tbody(*[Tr(
            Td(A(t["ref"], href=f"/requests/{t['id']}")),
            Td(A(t["title"][:42], href=f"/requests/{t['id']}")),
            Td(t["department"] or "—"), Td(t["requester"] or "—"), Td(_pill(t["priority"])),
            Td(_pill(t["status"])), Td(_sla(t)),
            Td(t["assignee"] or Span("—", style="color:var(--breach);")),
        ) for t in reqs] or [Tr(Td("No requests match.", colspan="8"))]), cls="tbl")

    search = Form(Input(type="search", name="q", value=q, placeholder="Search requests…"),
                  Input(type="hidden", name="status", value=status), cls="toolbar", method="get", action="/requests")
    return _title("Request Queue", f"{len(reqs)} shown"), seg, dept_seg, search, Div(tbl, cls="card")


def _select(name, options, current, rid, field):
    return Select(*[Option(o, value=o, selected=(o == current)) for o in options],
                  name=name, cls="mini-select",
                  **{"hx-post": f"/requests/{rid}/field", "hx-vals": f'{{"field":"{field}"}}',
                     "hx-target": "#request-main", "hx-swap": "innerHTML", "hx-trigger": "change"})


def request_main(rid):
    t = db.request(rid)
    if not t:
        return Div(P("No such request."))
    msgs = db.messages_for(rid)
    acts = db.activity_for(rid)
    ags = db.agents()
    fdata = db.request_form_data(t)

    # submitted catalog form data
    form_rows = [Div(Span(kk.replace("_", " ").title(), cls="k"), Span(str(vv)))
                 for kk, vv in fdata.items()] if fdata else [Span("—", cls="k")]

    thread = Div(*[Div(Div(f"{m['author']} · {_ago(m['created'])}", cls="who"),
                       Div(NotStr(m["body"])), cls=f"bubble {m['sender']}") for m in msgs]
                 or [P("No comments yet.", style="color:var(--text-mute);")], cls="thread")

    reply = Form(Textarea("", name="body", id="reply-body",
                          placeholder="Add a comment to the requester…", required=True),
                 Div(Button("↩ Send reply", cls="btn primary", type="submit", name="sender", value="agent"),
                     Button("🔒 Internal note", cls="btn", type="submit", name="sender", value="note"),
                     style="margin-top:8px;display:flex;gap:8px;"),
                 **{"hx-post": f"/requests/{rid}/message", "hx-target": "#request-main", "hx-swap": "innerHTML"},
                 cls="reply-form")

    agent_sel = Select(Option("Unassigned", value="", selected=not t["assignee_id"]),
                       *[Option(a["name"], value=str(a["id"]), selected=(a["id"] == t["assignee_id"])) for a in ags],
                       name="agent_id", cls="mini-select",
                       **{"hx-post": f"/requests/{rid}/assign", "hx-target": "#request-main",
                          "hx-swap": "innerHTML", "hx-trigger": "change"})

    # approval actions when pending
    approval_block = None
    if t["status"] == "Pending Approval":
        approval_block = Div(
            Span("⏳ Awaiting approval", cls="pill pendingapproval"),
            Form(Button("✅ Approve", cls="btn ok sm", type="submit"),
                 method="post", action=f"/requests/{rid}/approve", style="display:inline;"),
            Form(Button("⛔ Reject", cls="btn danger sm", type="submit"),
                 method="post", action=f"/requests/{rid}/reject", style="display:inline;"),
            style="display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap;")

    info = Div(Div(H3("Request"), _sla(t), cls="card-header"),
               approval_block,
               Div(Span("Ref", cls="k"), Span(t["ref"] or f"#{rid}"),
                   Span("Status", cls="k"), _select("status", db.REQUEST_STATUSES, t["status"], rid, "status"),
                   Span("Priority", cls="k"), _select("priority", db.PRIORITIES, t["priority"], rid, "priority"),
                   Span("Service", cls="k"), Span(t["service"] or "—"),
                   Span("Owner", cls="k"), agent_sel,
                   Span("Requester", cls="k"), Span(t["requester"] or "—"),
                   Span("Department", cls="k"), Span(t["department"] or "—"),
                   Span("Raised", cls="k"), Span(_ago(t["created"])),
                   Span("Fulfil by", cls="k"), Span(_ago(t["resolution_by"])),
                   Span("Approver", cls="k"), Span(t["approver"] or "—"),
                   cls="kv"), cls="card")

    form_card = Div(Div(H3("Submitted details"), cls="card-header"),
                    Div(*form_rows, cls="kv"), cls="card")
    timeline = Ul(*[Li(Div(Strong(NotStr(a["action"])), " ",
                           Span(a["actor"] or "", style="color:var(--text-mute);")),
                       Div(_ago(a["created"]), cls="when")) for a in acts] or [Li("No activity.")], cls="timeline")

    return Div(Div(Div(Div(H3("Conversation"), cls="card-header"), thread, reply, cls="card")),
               Div(info, form_card, Div(Div(H3("Activity"), cls="card-header"), timeline, cls="card")),
               cls="detail-grid")


def request_detail(rid):
    t = db.request(rid)
    if not t:
        return _title("Request not found"), P("No such request.")
    return (_title(t["title"], f"{t['ref']} · {t['service'] or ''}",
                   A("← All requests", href="/requests", cls="btn")),
            Div(request_main(rid), id="request-main"))


# ---------- my requests (employee) ------------------------------------------

def my_requests(requester_id):
    reqs = db.requests_for_requester(requester_id)
    who = db.one("SELECT name FROM users WHERE id=?", (requester_id,))
    rows_ = [Tr(Td(A(t["ref"], href=f"/requests/{t['id']}")),
                Td(A(t["title"][:44], href=f"/requests/{t['id']}")),
                Td(f"{t.get('service_icon') or ''} {t['service'] or '—'}"),
                Td(_pill(t["status"])), Td(_sla(t)), Td(_ago(t["created"])))
             for t in reqs]
    tbl = Table(Thead(Tr(Th("Ref"), Th("Request"), Th("Service"), Th("Status"), Th("SLA"), Th("Raised"))),
                Tbody(*rows_ or [Tr(Td("You have no requests yet — browse the catalog.", colspan="6"))]), cls="tbl")
    return (_title("My Requests", f"{who['name'] if who else 'You'} · {len(reqs)} orders",
                   A("＋ New request", href="/catalog", cls="btn primary")),
            Div(tbl, cls="card"))


# ---------- approvals (manager) ---------------------------------------------

def approvals_view():
    pend = db.rows(
        """SELECT r.*, s.name service, d.name department, u.name requester FROM requests r
           LEFT JOIN services s ON s.id=r.service_id
           LEFT JOIN departments d ON d.id=r.department_id
           LEFT JOIN users u ON u.id=r.requester_id
           WHERE r.status='Pending Approval' ORDER BY r.created""")
    rows_ = []
    for t in pend:
        rows_.append(Tr(
            Td(A(t["ref"], href=f"/requests/{t['id']}")),
            Td(A(t["title"][:40], href=f"/requests/{t['id']}")),
            Td(t["department"] or "—"), Td(t["requester"] or "—"), Td(_pill(t["priority"])), Td(_sla(t)),
            Td(Div(Form(Button("✅ Approve", cls="btn ok sm", type="submit"),
                        method="post", action=f"/requests/{t['id']}/approve", style="display:inline;"),
                   Form(Button("⛔ Reject", cls="btn danger sm", type="submit"),
                        method="post", action=f"/requests/{t['id']}/reject", style="display:inline;"),
                   style="display:flex;gap:6px;"))))
    tbl = Table(Thead(Tr(Th("Ref"), Th("Request"), Th("Department"), Th("Requester"),
                        Th("Priority"), Th("SLA"), Th("Decision"))),
                Tbody(*rows_ or [Tr(Td("Nothing awaiting approval — all clear. 🎉", colspan="7"))]), cls="tbl")
    return (_title("Approvals", f"{len(pend)} request(s) awaiting your decision"),
            Div(NotStr("Requests for services flagged <strong>approval required</strong> pause here until a manager "
                       "approves or rejects — the workflow gate before fulfilment."), cls="callout"),
            Div(tbl, cls="card"))


# ---------- knowledge base --------------------------------------------------

def kb_list(q=""):
    clause, params = "", ()
    if q:
        clause = "WHERE a.title LIKE ? OR a.content LIKE ?"
        params = (f"%{q}%", f"%{q}%")
    arts = db.rows(
        f"""SELECT a.*, ac.name category, d.name department FROM articles a
            LEFT JOIN article_categories ac ON ac.id=a.category_id
            LEFT JOIN departments d ON d.id=a.department_id
            {clause} ORDER BY a.views DESC""", params)
    by_cat = {}
    for a in arts:
        by_cat.setdefault(a["category"] or "Other", []).append(a)
    blocks = []
    for cat in sorted(by_cat):
        items = [Div(H4(a["title"]),
                     Div(f"{a['department'] or 'General'} · {a['views']:,} views · by {a['author']}", cls="meta"),
                     cls="kb-card") for a in by_cat[cat]]
        blocks.append(Div(Div(H3(cat), cls="card-header"), *items, cls="card"))
    search = Form(Input(type="search", name="q", value=q, placeholder="Search the knowledge base…"),
                  cls="toolbar", method="get", action="/kb")
    return _title("Knowledge Base", f"{len(arts)} published articles"), search, *blocks


# ---------- people & departments (admin) ------------------------------------

def people_list():
    users = db.rows(
        """SELECT u.*, d.name department,
                  (SELECT COUNT(*) FROM requests r WHERE r.assignee_id=u.id AND r.status IN ('Submitted','Pending Approval','Approved','In Progress')) open_n
           FROM users u LEFT JOIN departments d ON d.id=u.department_id
           WHERE u.is_active=1 ORDER BY u.role, u.name""")
    utbl = Table(Thead(Tr(Th("Name"), Th("Role"), Th("Department"), Th("Availability"), Th("Open assigned"))),
                 Tbody(*[Tr(Td(Strong(u["name"])), Td(_pill(u["role"], "neutral")),
                            Td(u["department"] or "—"), Td(_pill(u["availability"])), Td(str(u["open_n"])))
                         for u in users]), cls="tbl")
    depts = db.rows(
        """SELECT d.*, COUNT(r.id) reqs,
                  SUM(CASE WHEN r.status IN ('Submitted','Pending Approval','Approved','In Progress') THEN 1 ELSE 0 END) open_n
           FROM departments d LEFT JOIN requests r ON r.department_id=d.id
           GROUP BY d.id ORDER BY reqs DESC""")
    dtbl = Table(Thead(Tr(Th("Department"), Th("Total requests"), Th("Open"))),
                 Tbody(*[Tr(Td(f"{d['icon'] or ''} {d['name']}"), Td(str(d["reqs"])),
                            Td(str(d["open_n"] or 0))) for d in depts]), cls="tbl")
    return (_title("People & Departments", f"{len(users)} people across {len(depts)} departments"),
            Div(Div(Div(H3("People (RBAC roles)"), cls="card-header"), utbl, cls="card"),
                Div(Div(H3("Departments"), cls="card-header"), dtbl, cls="card"), cls="grid-2"))


# ---------- form & workflow designer (admin) --------------------------------

def designer_list():
    svcs = db.services(active_only=False)
    rows_ = [Tr(Td(f"{s['icon'] or ''} {s['name']}"), Td(s["department"] or "—"),
                Td(str(len(db.service_schema(s["id"]).get("fields", []))) + " fields"),
                Td(f"{s['sla_hours']}h"),
                Td(_pill("Approval", "pendingapproval") if s["requires_approval"] else _pill("Auto", "ok2")),
                Td(A("Edit form →", href=f"/designer/{s['id']}", cls="btn sm")))
             for s in svcs]
    tbl = Table(Thead(Tr(Th("Service"), Th("Department"), Th("Form"), Th("SLA"), Th("Workflow"), Th(""))),
                Tbody(*rows_), cls="tbl")
    return (_title("Form & Workflow Designer",
                   "Config-driven forms: each catalog service is a JSON form + SLA + approval flag — no redeploy."),
            Div(NotStr("Everything a service exposes — its intake fields, SLA, and whether it needs approval — is "
                       "<strong>data</strong>, not code. Edit the JSON below and the catalog form updates instantly."),
                cls="callout"),
            Div(tbl, cls="card"))


def designer_edit(sid, saved=False, error=""):
    s = db.service(sid)
    if not s:
        return _title("Service not found"), P("No such service.")
    schema = db.service_schema(sid)
    pretty = json.dumps(schema, indent=2)
    banner = None
    if saved:
        banner = Div("✅ Saved — the catalog form now reflects your changes.", cls="callout")
    elif error:
        banner = Div("⛔ " + error, cls="callout", style="border-left-color:var(--breach);color:var(--breach);")

    form = Form(
        Div(Label("Form schema (JSON)"),
            Textarea(pretty, name="form_schema", rows="18",
                     style="width:100%;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px;"
                           "padding:12px;border:1px solid var(--border);border-radius:8px;"),
            cls="form-field"),
        Div(Div(Label("Fulfilment SLA (hours)"),
                Input(name="sla_hours", type="number", value=str(s["sla_hours"]), min="1"), cls="form-field"),
            Div(Label("Requires approval"),
                Select(Option("Yes", value="1", selected=bool(s["requires_approval"])),
                       Option("No", value="0", selected=not s["requires_approval"]), name="requires_approval"),
                cls="form-field"),
            style="display:flex;gap:16px;"),
        Div(Button("Save", cls="btn primary", type="submit"),
            A("← Designer", href="/designer", cls="btn"), style="display:flex;gap:8px;"),
        method="post", action=f"/designer/{sid}")

    help_ = Div(Div(H3("Field reference"), cls="card-header"),
                P(NotStr("Each field: <code>name</code>, <code>label</code>, "
                         "<code>type</code> (<code>text</code>, <code>textarea</code>, <code>select</code>, "
                         "<code>date</code>, <code>number</code>, <code>email</code>), optional "
                         "<code>required</code>, <code>options</code> (for select), <code>placeholder</code>, "
                         "<code>hint</code>."), style="line-height:1.7;font-size:13px;"),
                Div(H4("Live preview"), cls="card-header", style="margin-top:8px;"),
                *[_render_field(f) for f in schema.get("fields", [])], cls="card")

    return (_title(f"Designer — {s['name']}", f"{s['department']} · service #{sid}",
                   A("Open in catalog →", href=f"/catalog/{sid}", cls="btn")),
            banner,
            Div(Div(Div(H3("Edit"), cls="card-header"), form, cls="card"),
                help_, cls="detail-grid"))
