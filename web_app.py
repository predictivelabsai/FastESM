"""FastESM — an open-source Enterprise Service Management platform built with FastHTML.

ESM = ITSM extended across every department. A server-side, HTMX-driven app with
a **service catalog** (browse-and-request webshop), **request orchestration**
(approval → fulfilment workflow with SLA timers), **RBAC** role views
(Employee / Agent / Manager / Admin), a **knowledge base**, a config-driven
**form & workflow designer**, dashboards (Plotly), and a grounded AI assistant.

Part of the FastGov suite. Digital-sovereignty by design: EU-hostable, MIT,
your data stays in your SQLite file. No lock-in.

Run:
    python web_app.py            # http://localhost:5015

Login: admin@fastesm.example / FastESM2026$  (override via .env)
"""
from __future__ import annotations

import os
import json
import secrets
import uuid
import logging

from dotenv import load_dotenv
load_dotenv()

from fasthtml.common import (
    fast_app, serve, Div, H1, H2, P, A, Form, Input, Button, NotStr, Span,
    RedirectResponse, Script, Style, Link, Title,
)
from starlette.responses import StreamingResponse, Response
from starlette.responses import JSONResponse

import db
from web.layout import page, LAYOUT_CSS
from web import views, ai
from web.landing import landing_page
from web.developer import developer_page
from web import account_auth, google_auth
from web.api import api

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger("fastesm")

VALID_EMAIL = os.getenv("FASTESM_ADMIN_EMAIL", "admin@fastesm.example")
VALID_PASSWORD = os.getenv("FASTESM_ADMIN_PASSWORD", "FastESM2026$")
ENV_LABEL = os.getenv("FASTESM_ENV_LABEL", "FastESM")
SECRET = os.getenv("FASTESM_SECRET", secrets.token_hex(32))
PORT = int(os.getenv("FASTESM_PORT", "5015"))

PLOTLY_HEAD = Script(src="https://cdn.plot.ly/plotly-2.35.2.min.js")

app, rt = fast_app(live=False, pico=False, secret_key=SECRET, hdrs=[Style(LAYOUT_CSS)])
app.mount("/api", api)


@rt("/swagger.json", methods=["GET"])
def swagger_schema():
    return JSONResponse(api.openapi())


@rt("/developers", methods=["GET"])
def developers():
    return developer_page()


account_auth.register_fasthtml_routes(rt, app_name="FastESM", session_key="user", success_path="/role-select")


def _user(session):
    return session.get("user")


def _role(session):
    return session.get("role", "Admin")


def _thread(session):
    if "thread" not in session:
        session["thread"] = uuid.uuid4().hex
    return session["thread"]


def _guard(session, active, builder, extra_head=None):
    if not _user(session):
        return RedirectResponse("/login", status_code=303)
    if not session.get("role"):
        return RedirectResponse("/role-select", status_code=303)
    content = builder() if callable(builder) else builder
    if not isinstance(content, tuple):
        content = (content,)
    return page(active, ENV_LABEL, _user(session), _role(session), _thread(session),
                *content, extra_head=extra_head)


def _current_employee_id(session):
    """Demo helper: in the Employee lens, act as a seeded employee."""
    eid = session.get("employee_id")
    if not eid:
        emp = db.first_user("Employee")
        eid = emp["id"] if emp else None
        session["employee_id"] = eid
    return eid


# --- auth -------------------------------------------------------------------

def _login_card(error="", email=""):
    return Title("FastESM — Sign in"), Style(LAYOUT_CSS), Div(
        Form(H1("FastESM"), P("Enterprise Service Management — sign in"),
             Input(name="email", type="email", placeholder="Email", value=email, required=True),
             Input(name="password", type="password", placeholder="Password", required=True),
             P(error, cls="error") if error else None,
             Button("Sign in", cls="btn primary", type="submit"),
             P(NotStr("Demo: <code>admin@fastesm.example</code> / <code>FastESM2026$</code>"), cls="hint"),
             method="post", action="/login", cls="login-card"), cls="login-wrap")


@rt("/login")
def get(session):
    if _user(session):
        return RedirectResponse("/", status_code=303)
    return _login_card()


@rt("/login")
def post(session, email: str = "", password: str = ""):
    if email.strip().lower() == VALID_EMAIL.lower() and password == VALID_PASSWORD:
        session["user"] = email.strip().lower()
        session.pop("role", None)
        return RedirectResponse("/role-select", status_code=303)
    return _login_card("Invalid email or password.", email)



@rt("/auth/google")
def google_start(session, request):
    if not google_auth.enabled():
        return RedirectResponse("/login?error=Google+sign-in+is+not+configured", status_code=303)
    state = google_auth.new_state()
    session["google_oauth_state"] = state
    return RedirectResponse(google_auth.authorize_url(request, state), status_code=303)


@rt("/auth/google/callback")
def google_callback(session, request, code: str = "", state: str = "", error: str = ""):
    if error or not code or state != session.pop("google_oauth_state", None):
        return RedirectResponse("/login?error=Google+sign-in+failed", status_code=303)
    identity = google_auth.exchange(request, code)
    if not identity:
        return RedirectResponse("/login?error=Google+account+is+not+authorised", status_code=303)
    account_auth.accounts.link_google(identity["email"], identity["name"])
    session["user"] = identity["email"]
    return RedirectResponse("/role-select", status_code=303)


@rt("/logout")
def get(session):
    session.pop("user", None)
    session.pop("role", None)
    return RedirectResponse("/login", status_code=303)


# --- RBAC role selection (post-login) ---------------------------------------

ROLE_BLURB = {
    "Employee": ("🧑‍💻", "Browse the service catalog, raise requests and track your orders."),
    "Agent": ("🛠️", "Work the request queue, respond and fulfil across your department."),
    "Manager": ("✅", "Approve or reject requests and watch team SLAs & workload."),
    "Admin": ("⚙️", "Configure services, forms & workflows and see everything."),
}


@rt("/role-select")
def get(session):
    if not _user(session):
        return RedirectResponse("/login", status_code=303)
    tiles = []
    for r in db.ROLES:
        ic, blurb = ROLE_BLURB[r]
        tiles.append(A(Div(ic, cls="ic"), Div(r, cls="rn"), Div(blurb, cls="rd"),
                       href=f"/role/{r}", cls="role-tile"))
    return (Title("FastESM — Choose your role"), Style(LAYOUT_CSS),
            Div(H2("Choose your role", style="margin:0;font-size:24px;"),
                P("FastESM adapts to who you are — pick a lens to continue. You can switch anytime from the top bar.",
                  style="color:var(--text-mute);margin:0 0 4px;max-width:520px;text-align:center;"),
                Div(*tiles, cls="role-pick-grid"),
                cls="role-pick-wrap"))


@rt("/role/{role}")
def get(session, role: str):
    if not _user(session):
        return RedirectResponse("/login", status_code=303)
    if role in db.ROLES:
        session["role"] = role
    dest = "/catalog" if role == "Employee" else "/"
    return RedirectResponse(dest, status_code=303)


# --- dashboard --------------------------------------------------------------

@rt("/")
def get(session):
    if not _user(session):
        return landing_page()
    if _user(session) and _role(session) == "Employee":
        return RedirectResponse("/catalog", status_code=303)
    return _guard(session, "dashboard", views.dashboard, extra_head=PLOTLY_HEAD)


# --- service catalog --------------------------------------------------------

@rt("/catalog")
def get(session):
    return _guard(session, "catalog", views.catalog_list)


@rt("/catalog/{sid}")
def get(session, sid: int):
    return _guard(session, "catalog", lambda: views.catalog_request_form(sid))


@rt("/catalog/{sid}/request")
async def post(session, sid: int, request):
    if not _user(session):
        return RedirectResponse("/login", status_code=303)
    form = await request.form()
    priority = form.get("priority", "Medium")
    form_data = {k[2:]: v for k, v in form.items() if k.startswith("f_")}
    requester_id = _current_employee_id(session)
    rid = db.create_request(sid, requester_id, priority, form_data)
    if not rid:
        return RedirectResponse("/catalog", status_code=303)
    return RedirectResponse(f"/requests/{rid}", status_code=303)


# --- requests ---------------------------------------------------------------

@rt("/requests")
def get(session, status: str = "Open", department: str = "All", q: str = ""):
    return _guard(session, "requests", lambda: views.requests_list(status, department, q))


@rt("/requests/{rid}")
def get(session, rid: int):
    return _guard(session, "requests", lambda: views.request_detail(rid))


def _rfrag(session, rid):
    if not _user(session):
        return Response("Unauthorized", status_code=401)
    return views.request_main(rid)


@rt("/requests/{rid}/message")
def post(session, rid: int, body: str = "", sender: str = "agent"):
    db.add_message(rid, "note" if sender == "note" else "agent", body)
    return _rfrag(session, rid)


@rt("/requests/{rid}/field")
def post(session, rid: int, field: str = "", status: str = "", priority: str = ""):
    val = {"status": status, "priority": priority}.get(field, "")
    db.set_request_field(rid, field, val)
    return _rfrag(session, rid)


@rt("/requests/{rid}/assign")
def post(session, rid: int, agent_id: str = ""):
    db.assign_agent(rid, int(agent_id) if agent_id else None)
    return _rfrag(session, rid)


def _decision_dest(session, rid):
    # Managers act from the Approvals board; return there, else the request detail.
    return "/approvals" if _role(session) == "Manager" else f"/requests/{rid}"


@rt("/requests/{rid}/approve")
def post(session, rid: int):
    if not _user(session):
        return RedirectResponse("/login", status_code=303)
    mgr = db.first_user("Manager")
    db.approve_request(rid, mgr["id"] if mgr else None)
    return RedirectResponse(_decision_dest(session, rid), status_code=303)


@rt("/requests/{rid}/reject")
def post(session, rid: int):
    if not _user(session):
        return RedirectResponse("/login", status_code=303)
    mgr = db.first_user("Manager")
    db.reject_request(rid, mgr["id"] if mgr else None)
    return RedirectResponse(_decision_dest(session, rid), status_code=303)


@rt("/my-requests")
def get(session):
    return _guard(session, "myrequests", lambda: views.my_requests(_current_employee_id(session)))


# --- approvals --------------------------------------------------------------

@rt("/approvals")
def get(session):
    return _guard(session, "approvals", views.approvals_view)


# --- knowledge base ---------------------------------------------------------

@rt("/kb")
def get(session, q: str = ""):
    return _guard(session, "kb", lambda: views.kb_list(q))


# --- people & departments (admin) -------------------------------------------

@rt("/people")
def get(session):
    return _guard(session, "people", views.people_list)


# --- form & workflow designer (admin) ---------------------------------------

@rt("/designer")
def get(session):
    return _guard(session, "designer", views.designer_list)


@rt("/designer/{sid}")
def get(session, sid: int, saved: int = 0):
    return _guard(session, "designer", lambda: views.designer_edit(sid, saved=bool(saved)))


@rt("/designer/{sid}")
def post(session, sid: int, form_schema: str = "", sla_hours: str = "", requires_approval: str = ""):
    if not _user(session):
        return RedirectResponse("/login", status_code=303)
    ok = db.update_service_schema(
        sid, form_schema,
        requires_approval=(requires_approval == "1"),
        sla_hours=int(sla_hours) if sla_hours.strip().isdigit() else None)
    if not ok:
        return _guard(session, "designer",
                      lambda: views.designer_edit(sid, error="Invalid JSON — needs a top-level \"fields\" list."))
    return RedirectResponse(f"/designer/{sid}?saved=1", status_code=303)


# --- AI + guide -------------------------------------------------------------

@rt("/ai")
def get(session):
    body = (views._title("AI Assistant", "Chat lives in the right rail. Ask in plain English or use slash-commands."),
            Div(NotStr(
                "<div class='card'><h3>What you can ask</h3><ul style='line-height:1.8;'>"
                "<li>“Which requests are breaching SLA right now?”</li>"
                "<li>“What's pending approval?”</li>"
                "<li>“Which department has the biggest backlog?”</li>"
                "<li>“Find knowledge-base articles about onboarding.”</li></ul>"
                "<p style='color:var(--text-mute)'>Slash-commands resolve instantly with no API key: "
                "<code>/sla</code> <code>/approvals</code> <code>/requests</code> <code>/priority</code> "
                "<code>/catalog</code> <code>/departments</code> <code>/kb</code> <code>/kpi</code> "
                "<code>/help</code></p></div>")))
    return _guard(session, "ai", body)


@rt("/guide")
def get(session):
    body = (views._title("User Guide", "How to drive FastESM"), Div(NotStr("""
<div class='card'><h3>Service Catalog</h3><p>The front door for every department. Employees browse services like a
webshop and submit a request via a form <em>rendered from JSON</em> — no code per service.</p></div>
<div class='card'><h3>Requests & workflow</h3><p>Each request flows Submitted → (Pending Approval → Approved) →
In Progress → Fulfilled, with live SLA timers derived from the service's SLA and the priority.</p></div>
<div class='card'><h3>RBAC roles</h3><p>Employee / Agent / Manager / Admin each get their own nav and actions.
Switch lenses from the top bar.</p></div>
<div class='card'><h3>Approvals</h3><p>Services flagged <em>approval required</em> pause on the Manager's Approvals
board until approved or rejected.</p></div>
<div class='card'><h3>Form & Workflow Designer</h3><p>Admins edit a service's JSON form, SLA and approval flag —
the catalog updates instantly. Configuration is data, not code.</p></div>
<div class='card'><h3>Dashboards & AI</h3><p>SLA/workload KPIs with Plotly charts, and an assistant grounded in a
live snapshot of the queue. Slash-commands work with no API key.</p></div>
""")))
    return _guard(session, "guide", body)


@rt("/chat/new")
def get(session):
    session["thread"] = uuid.uuid4().hex
    return P("Ask about requests, SLAs, approvals or the service catalog — or tap a question below.",
             cls="chat-empty-hint")


@rt("/chat/stream")
async def post(session, message: str = "", thread_id: str = ""):
    if not _user(session):
        return Response("Unauthorized", status_code=401)
    message = (message or "").strip()
    if not message:
        return Response("No message", status_code=400)
    tid = thread_id or _thread(session)

    async def gen():
        with db.cursor() as conn:
            conn.execute("INSERT INTO chat_messages(thread_id,role,content,created) VALUES(?,?,?,datetime('now'))",
                         (tid, "user", message))
        full = []
        async for chunk in ai.stream_chat(message):
            if chunk.startswith("data: "):
                try:
                    tok = json.loads(chunk[6:]).get("token")
                    if tok:
                        full.append(tok)
                except Exception:
                    pass
            yield chunk
        with db.cursor() as conn:
            conn.execute("INSERT INTO chat_messages(thread_id,role,content,created) VALUES(?,?,?,datetime('now'))",
                         (tid, "assistant", "".join(full)))

    return StreamingResponse(gen(), media_type="text/event-stream")


def _ensure_db():
    if not db.db_exists():
        logger.info("No database found — seeding synthetic data…")
        import seed
        seed.build()
    else:
        db.init_schema()  # idempotent


_ensure_db()

if __name__ == "__main__":
    logger.info("FastESM on http://localhost:%s  (login %s)", PORT, VALID_EMAIL)
    serve(port=PORT, reload=os.getenv("FASTESM_RELOAD", "0") == "1")
