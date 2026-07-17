"""FastESM data layer — SQLite, Enterprise Service Management.

FastESM extends the FastHelpdesk ticket/SLA model into cross-department ESM.
Core entities: departments, users (with RBAC roles), a **service catalog**
(catalog items with config-driven JSON request forms + per-service SLA and an
optional approval step), **service requests** (the ESM "ticket"/order with an
approval → fulfilment workflow), request comments, an audit trail, and a
knowledge base. SLA response/resolution targets are computed against the clock
so the demo shows live "due in" and "breached" timers.

All data is synthetic (see seed.py). No PII.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = os.getenv("FASTESM_DB") or str(Path(__file__).parent / "fastesm.sqlite")

# The demo's "now" — kept fixed so live SLA timers are deterministic.
NOW = datetime(2026, 7, 16, 12, 0, 0)
TODAY = NOW.strftime("%Y-%m-%d")

# Request lifecycle: Submitted → (Pending Approval → Approved) → In Progress → Fulfilled.
REQUEST_STATUSES = ["Submitted", "Pending Approval", "Approved", "In Progress",
                    "Fulfilled", "Rejected", "Cancelled"]
OPEN_STATUSES = ["Submitted", "Pending Approval", "Approved", "In Progress"]
CLOSED_STATUSES = ["Fulfilled", "Rejected", "Cancelled"]

PRIORITIES = ["Urgent", "High", "Medium", "Low"]
AGENT_AVAILABILITY = ["Available", "Busy", "Away"]
ARTICLE_STATUSES = ["Published", "Draft", "Archived"]

# RBAC roles. Post-login the operator picks a lens; nav + actions adapt.
ROLES = ["Employee", "Agent", "Manager", "Admin"]

# SLA response targets (minutes) by priority. Resolution comes from the
# catalog service's own sla_hours (per-item SLA), with a priority fallback.
SLA_RESPONSE = {"Urgent": 30, "High": 60, "Medium": 4 * 60, "Low": 8 * 60}
SLA_RESOLUTION_FALLBACK = {"Urgent": 4 * 60, "High": 8 * 60, "Medium": 24 * 60, "Low": 72 * 60}


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def cursor():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def db_exists() -> bool:
    p = Path(DB_PATH)
    return p.exists() and p.stat().st_size > 0


def rows(sql, params=()):
    with cursor() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def one(sql, params=()):
    with cursor() as conn:
        r = conn.execute(sql, params).fetchone()
        return dict(r) if r else None


def scalar(sql, params=()):
    with cursor() as conn:
        r = conn.execute(sql, params).fetchone()
        return r[0] if r else None


SCHEMA = """
CREATE TABLE IF NOT EXISTS departments (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    icon          TEXT
);
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    email         TEXT UNIQUE,
    department_id INTEGER REFERENCES departments(id),
    role          TEXT NOT NULL DEFAULT 'Employee',   -- Employee | Agent | Manager | Admin
    availability  TEXT NOT NULL DEFAULT 'Available',
    is_active     INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS services (
    id                INTEGER PRIMARY KEY,
    name              TEXT NOT NULL,
    department_id     INTEGER REFERENCES departments(id),
    category          TEXT,
    description       TEXT,
    icon              TEXT,
    sla_hours         INTEGER NOT NULL DEFAULT 24,
    requires_approval INTEGER NOT NULL DEFAULT 0,
    form_schema       TEXT NOT NULL DEFAULT '{"fields":[]}',  -- JSON form definition
    is_active         INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS requests (
    id                  INTEGER PRIMARY KEY,
    ref                 TEXT,
    title               TEXT NOT NULL,
    service_id          INTEGER REFERENCES services(id),
    department_id       INTEGER REFERENCES departments(id),
    requester_id        INTEGER REFERENCES users(id),
    assignee_id         INTEGER REFERENCES users(id),
    approver_id         INTEGER REFERENCES users(id),
    status              TEXT NOT NULL,
    priority            TEXT NOT NULL,
    form_data           TEXT,          -- JSON of submitted catalog form
    created             TEXT NOT NULL,
    response_by         TEXT,          -- SLA first-response deadline
    resolution_by       TEXT,          -- SLA fulfilment deadline (per-service)
    first_responded_on  TEXT,
    approved_on         TEXT,
    resolved_on         TEXT,          -- fulfilled / rejected / cancelled time
    feedback_rating     INTEGER        -- 1..5, after fulfilment
);
CREATE TABLE IF NOT EXISTS request_messages (
    id            INTEGER PRIMARY KEY,
    request_id    INTEGER NOT NULL REFERENCES requests(id),
    sender        TEXT NOT NULL,       -- 'requester' | 'agent' | 'note'
    author        TEXT,
    body          TEXT NOT NULL,
    created       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS request_activity (
    id            INTEGER PRIMARY KEY,
    request_id    INTEGER NOT NULL REFERENCES requests(id),
    action        TEXT NOT NULL,
    actor         TEXT,
    created       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS article_categories (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    icon          TEXT
);
CREATE TABLE IF NOT EXISTS articles (
    id            INTEGER PRIMARY KEY,
    title         TEXT NOT NULL,
    category_id   INTEGER REFERENCES article_categories(id),
    department_id INTEGER REFERENCES departments(id),
    content       TEXT,
    author        TEXT,
    status        TEXT NOT NULL DEFAULT 'Published',
    views         INTEGER NOT NULL DEFAULT 0,
    published_on  TEXT
);
CREATE TABLE IF NOT EXISTS chat_messages (
    id            INTEGER PRIMARY KEY,
    thread_id     TEXT NOT NULL,
    role          TEXT NOT NULL,
    content       TEXT NOT NULL,
    created       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_req_status ON requests(status);
CREATE INDEX IF NOT EXISTS idx_req_assignee ON requests(assignee_id);
CREATE INDEX IF NOT EXISTS idx_req_dept ON requests(department_id);
CREATE INDEX IF NOT EXISTS idx_msg_req ON request_messages(request_id);
CREATE INDEX IF NOT EXISTS idx_act_req ON request_activity(request_id);
"""


def init_schema():
    with cursor() as conn:
        conn.executescript(SCHEMA)


# --- SLA helpers ------------------------------------------------------------

def _parse(ts: str | None):
    if not ts:
        return None
    try:
        return datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _now() -> datetime:
    return NOW


def sla_state(req: dict, now: datetime | None = None) -> dict:
    """Return SLA badge info: {'label','tone','breached'} for a request."""
    now = now or NOW
    if req["status"] in CLOSED_STATUSES:
        res_by = _parse(req.get("resolution_by"))
        resolved = _parse(req.get("resolved_on"))
        if req["status"] == "Fulfilled" and res_by and resolved and resolved > res_by:
            return {"label": "SLA breached", "tone": "breach", "breached": True}
        if req["status"] == "Fulfilled":
            return {"label": "Within SLA", "tone": "ok", "breached": False}
        return {"label": req["status"], "tone": "neutral", "breached": False}
    # open: which target is live?
    if not req.get("first_responded_on"):
        target, kind = _parse(req.get("response_by")), "response"
    else:
        target, kind = _parse(req.get("resolution_by")), "fulfilment"
    if not target:
        return {"label": "No SLA", "tone": "neutral", "breached": False}
    delta = target - now
    mins = int(delta.total_seconds() // 60)
    if mins < 0:
        return {"label": f"{kind.title()} overdue {_fmt(-mins)}", "tone": "breach", "breached": True}
    tone = "warn" if mins < 120 else "ok"
    return {"label": f"{kind.title()} due in {_fmt(mins)}", "tone": tone, "breached": False}


def _fmt(mins: int) -> str:
    if mins >= 1440:
        return f"{mins // 1440}d"
    if mins >= 60:
        return f"{mins // 60}h"
    return f"{mins}m"


# --- aggregate reads --------------------------------------------------------

def kpis() -> dict:
    open_q = ",".join("?" * len(OPEN_STATUSES))
    open_reqs = rows(f"SELECT * FROM requests WHERE status IN ({open_q})", tuple(OPEN_STATUSES))
    breached = sum(1 for t in open_reqs if sla_state(t)["breached"])
    frts = [_parse(t["first_responded_on"]) and
            (_parse(t["first_responded_on"]) - _parse(t["created"])).total_seconds() / 60
            for t in rows("SELECT created, first_responded_on FROM requests WHERE first_responded_on IS NOT NULL")]
    frts = [m for m in frts if m]
    return {
        "open": len(open_reqs),
        "breached": breached,
        "pending_approval": scalar("SELECT COUNT(*) FROM requests WHERE status='Pending Approval'") or 0,
        "unassigned": scalar(f"SELECT COUNT(*) FROM requests WHERE assignee_id IS NULL AND status IN ({open_q})",
                             tuple(OPEN_STATUSES)) or 0,
        "fulfilled_today": scalar("SELECT COUNT(*) FROM requests WHERE status='Fulfilled' AND resolved_on >= ?",
                                  (TODAY,)) or 0,
        "avg_first_response": round(sum(frts) / len(frts)) if frts else 0,
        "total": scalar("SELECT COUNT(*) FROM requests") or 0,
        "csat": _csat(),
    }


def _csat() -> int:
    r = rows("SELECT feedback_rating FROM requests WHERE feedback_rating IS NOT NULL")
    if not r:
        return 0
    good = sum(1 for x in r if x["feedback_rating"] >= 4)
    return round(100 * good / len(r))


def counts_by(col: str) -> list[dict]:
    return rows(f"SELECT {col} k, COUNT(*) n FROM requests GROUP BY {col}")


def counts_by_department() -> list[dict]:
    return rows("""SELECT d.name k, COUNT(r.id) n FROM departments d
                   LEFT JOIN requests r ON r.department_id=d.id
                   GROUP BY d.id ORDER BY n DESC""")


# --- services (catalog) -----------------------------------------------------

def services(active_only=True) -> list[dict]:
    clause = "WHERE s.is_active=1" if active_only else ""
    return rows(f"""SELECT s.*, d.name department, d.icon dept_icon FROM services s
                    LEFT JOIN departments d ON d.id=s.department_id
                    {clause} ORDER BY d.name, s.name""")


def service(sid: int):
    return one("""SELECT s.*, d.name department, d.icon dept_icon FROM services s
                  LEFT JOIN departments d ON d.id=s.department_id WHERE s.id=?""", (sid,))


def service_schema(sid: int) -> dict:
    s = service(sid)
    if not s:
        return {"fields": []}
    try:
        return json.loads(s["form_schema"] or '{"fields":[]}')
    except json.JSONDecodeError:
        return {"fields": []}


def update_service_schema(sid: int, schema_json: str, requires_approval=None, sla_hours=None) -> bool:
    try:
        parsed = json.loads(schema_json)
        assert isinstance(parsed.get("fields"), list)
    except (json.JSONDecodeError, AssertionError):
        return False
    sets, params = ["form_schema=?"], [json.dumps(parsed)]
    if requires_approval is not None:
        sets.append("requires_approval=?")
        params.append(1 if requires_approval else 0)
    if sla_hours is not None:
        sets.append("sla_hours=?")
        params.append(int(sla_hours))
    params.append(sid)
    with cursor() as conn:
        conn.execute(f"UPDATE services SET {','.join(sets)} WHERE id=?", params)
    return True


# --- requests ---------------------------------------------------------------

def request(rid: int):
    return one(
        """SELECT r.*, s.name service, s.icon service_icon, d.name department, d.icon dept_icon,
                  u.name requester, u.email requester_email,
                  a.name assignee, ap.name approver
           FROM requests r
           LEFT JOIN services s ON s.id=r.service_id
           LEFT JOIN departments d ON d.id=r.department_id
           LEFT JOIN users u ON u.id=r.requester_id
           LEFT JOIN users a ON a.id=r.assignee_id
           LEFT JOIN users ap ON ap.id=r.approver_id
           WHERE r.id=?""", (rid,))


def request_form_data(req: dict) -> dict:
    try:
        return json.loads(req.get("form_data") or "{}")
    except json.JSONDecodeError:
        return {}


def messages_for(rid: int):
    return rows("SELECT * FROM request_messages WHERE request_id=? ORDER BY created", (rid,))


def activity_for(rid: int):
    return rows("SELECT * FROM request_activity WHERE request_id=? ORDER BY created DESC", (rid,))


def users(role: str | None = None) -> list[dict]:
    clause, params = ("WHERE u.is_active=1", ())
    if role:
        clause += " AND u.role=?"
        params = (role,)
    return rows(f"""SELECT u.id, u.name, u.role, u.availability, d.name department
                    FROM users u LEFT JOIN departments d ON d.id=u.department_id
                    {clause} ORDER BY u.name""", params)


def agents() -> list[dict]:
    return rows("""SELECT u.id, u.name, d.name department FROM users u
                   LEFT JOIN departments d ON d.id=u.department_id
                   WHERE u.is_active=1 AND u.role IN ('Agent','Manager','Admin') ORDER BY u.name""")


def first_user(role: str):
    return one("SELECT * FROM users WHERE role=? AND is_active=1 ORDER BY id LIMIT 1", (role,))


def departments() -> list[dict]:
    return rows("SELECT * FROM departments ORDER BY name")


def next_ref() -> str:
    n = (scalar("SELECT COUNT(*) FROM requests") or 0) + 1
    return f"REQ-{n:05d}"


def create_request(service_id: int, requester_id: int | None, priority: str,
                   form_data: dict, title: str | None = None) -> int | None:
    svc = service(service_id)
    if not svc:
        return None
    priority = priority if priority in PRIORITIES else "Medium"
    created = NOW
    resp_target = SLA_RESPONSE.get(priority, 4 * 60)
    res_minutes = (svc["sla_hours"] or 24) * 60
    response_by = created + timedelta(minutes=resp_target)
    resolution_by = created + timedelta(minutes=res_minutes)
    status = "Pending Approval" if svc["requires_approval"] else "In Progress"
    title = title or svc["name"]
    ref = next_ref()
    with cursor() as conn:
        cur = conn.execute(
            """INSERT INTO requests
               (ref,title,service_id,department_id,requester_id,assignee_id,approver_id,status,priority,
                form_data,created,response_by,resolution_by)
               VALUES (?,?,?,?,?,NULL,NULL,?,?,?,?,?,?)""",
            (ref, title, service_id, svc["department_id"], requester_id, status, priority,
             json.dumps(form_data), created.strftime("%Y-%m-%d %H:%M:%S"),
             response_by.strftime("%Y-%m-%d %H:%M:%S"), resolution_by.strftime("%Y-%m-%d %H:%M:%S")))
        rid = cur.lastrowid
        conn.execute("INSERT INTO request_activity(request_id,action,actor,created) VALUES(?,?,?,?)",
                     (rid, f"Request raised via catalog — <strong>{svc['name']}</strong>",
                      "Requester", created.strftime("%Y-%m-%d %H:%M:%S")))
        if svc["requires_approval"]:
            conn.execute("INSERT INTO request_activity(request_id,action,actor,created) VALUES(?,?,?,?)",
                         (rid, "Routed for manager approval", "Workflow",
                          created.strftime("%Y-%m-%d %H:%M:%S")))
    return rid


# --- write operations (transactional) ---------------------------------------

def _log(rid, action, actor="Agent"):
    with cursor() as conn:
        conn.execute("INSERT INTO request_activity(request_id,action,actor,created) VALUES(?,?,?,datetime('now'))",
                     (rid, action, actor))


def add_message(rid: int, sender: str, body: str, author: str = "Agent"):
    """sender: 'agent' (reply) | 'note' (internal) | 'requester'."""
    if not body.strip():
        return
    with cursor() as conn:
        conn.execute("INSERT INTO request_messages(request_id,sender,author,body,created) "
                     "VALUES(?,?,?,?,datetime('now'))", (rid, sender, author, body.strip()))
        if sender == "agent":
            r = conn.execute("SELECT first_responded_on FROM requests WHERE id=?", (rid,)).fetchone()
            if r and not r[0]:
                conn.execute("UPDATE requests SET first_responded_on=datetime('now') WHERE id=?", (rid,))
    _log(rid, "Reply sent" if sender == "agent" else "Internal note added")


def set_request_field(rid: int, field: str, value: str):
    allowed = {"status": REQUEST_STATUSES, "priority": PRIORITIES}
    if field not in allowed or value not in allowed[field]:
        return False
    closed = ", resolved_on=datetime('now')" if (field == "status" and value in CLOSED_STATUSES) else ""
    with cursor() as conn:
        conn.execute(f"UPDATE requests SET {field}=?{closed} WHERE id=?", (value, rid))
    _log(rid, f"{field.replace('_',' ').title()} changed to <strong>{value}</strong>")
    return True


def assign_agent(rid: int, agent_id):
    with cursor() as conn:
        if agent_id:
            a = conn.execute("SELECT name FROM users WHERE id=?", (agent_id,)).fetchone()
            conn.execute("UPDATE requests SET assignee_id=? WHERE id=?", (agent_id, rid))
            msg = f"Assigned to <strong>{a[0] if a else 'agent'}</strong>"
        else:
            conn.execute("UPDATE requests SET assignee_id=NULL WHERE id=?", (rid,))
            msg = "Unassigned"
    _log(rid, msg)


def approve_request(rid: int, approver_id: int | None = None):
    with cursor() as conn:
        conn.execute("UPDATE requests SET status='Approved', approved_on=datetime('now'), approver_id=? WHERE id=?",
                     (approver_id, rid))
    _log(rid, "✅ <strong>Approved</strong> — moving to fulfilment", actor="Manager")


def reject_request(rid: int, approver_id: int | None = None):
    with cursor() as conn:
        conn.execute("UPDATE requests SET status='Rejected', resolved_on=datetime('now'), approver_id=? WHERE id=?",
                     (approver_id, rid))
    _log(rid, "⛔ <strong>Rejected</strong> by approver", actor="Manager")


def requests_for_requester(requester_id: int):
    return rows("""SELECT r.*, s.name service, s.icon service_icon, d.name department
                   FROM requests r
                   LEFT JOIN services s ON s.id=r.service_id
                   LEFT JOIN departments d ON d.id=r.department_id
                   WHERE r.requester_id=? ORDER BY r.created DESC""", (requester_id,))
