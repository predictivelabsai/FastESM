"""FastESM AI assistant — slash-commands + grounded multi-provider chat.

Slash-commands resolve locally against SQLite (no API key). Free-form chat is
streamed from a configurable provider and grounded with a live snapshot of the
service-management queue so answers reflect the actual requests, SLAs and
approvals. Degrades gracefully to slash-commands when no API key is set.
"""
from __future__ import annotations

import json
import os

import db

PROVIDER = os.getenv("MODEL_PROVIDER", "xai")
MODEL = os.getenv("MODEL_NAME", "grok-4-1-fast-reasoning")


def snapshot() -> str:
    k = db.kpis()
    by_status = {r["k"]: r["n"] for r in db.counts_by("status")}
    by_dept = db.counts_by_department()
    lines = [
        "CURRENT SERVICE-MANAGEMENT SNAPSHOT (synthetic demo data):",
        f"- Open requests: {k['open']} ({k['unassigned']} unassigned). "
        f"Pending approval: {k['pending_approval']}. SLA at risk (breached/overdue): {k['breached']}.",
        f"- Fulfilled today: {k['fulfilled_today']}. Avg first response: {k['avg_first_response']} min. CSAT: {k['csat']}%.",
        "Requests by status: " + ", ".join(f"{s} {by_status.get(s,0)}" for s in db.REQUEST_STATUSES),
        "Requests by department: " + ", ".join(f"{d['k']} {d['n']}" for d in by_dept),
    ]
    open_q = ",".join("?" * len(db.OPEN_STATUSES))
    opens = db.rows(f"""SELECT r.*, s.name service FROM requests r
                        LEFT JOIN services s ON s.id=r.service_id
                        WHERE r.status IN ({open_q})""", tuple(db.OPEN_STATUSES))
    breached = [t for t in opens if db.sla_state(t)["breached"]]
    if breached:
        lines.append("Examples of SLA-breached open requests: " +
                     "; ".join(f"{t['ref']} {t['title'][:38]} ({t['priority']})" for t in breached[:6]))
    return "\n".join(lines)


SYSTEM_PROMPT = """You are the FastESM assistant, embedded in an open-source Enterprise Service Management platform.
Help employees find and request services, and help agents & managers triage requests, watch SLAs, clear approvals,
balance load across departments (IT, HR, Facilities, Finance …), and draft replies.
Be concise and practical; use Markdown (short tables, bold figures) when it helps.
All data is synthetic demo data — never claim it is real. Base answers on the SNAPSHOT below;
if something isn't in it, say so plainly rather than inventing."""


def _table(headers, rows_):
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows_:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def handle_command(text: str):
    if not text.startswith("/"):
        return None
    parts = text[1:].split()
    cmd = parts[0].lower() if parts else ""
    arg = " ".join(parts[1:])

    if cmd in ("help", "?"):
        return ("**FastESM shortcuts**\n\n"
                "- `/sla` — open requests breaching or near SLA\n"
                "- `/approvals` — requests awaiting approval\n"
                "- `/requests [status]` — request queue\n"
                "- `/priority <Urgent|High|Medium|Low>` — by priority\n"
                "- `/catalog [query]` — service catalog items\n"
                "- `/departments` — backlog by department\n"
                "- `/kb [query]` — knowledge-base articles\n"
                "- `/kpi` — headline numbers\n\nOr ask a question in plain English.")

    if cmd == "kpi":
        k = db.kpis()
        return _table(["Metric", "Value"], [
            ["Open requests", k["open"]], ["Pending approval", k["pending_approval"]],
            ["Unassigned", k["unassigned"]], ["SLA at risk", k["breached"]],
            ["Fulfilled today", k["fulfilled_today"]],
            ["Avg first response (min)", k["avg_first_response"]], ["CSAT", f"{k['csat']}%"]])

    if cmd == "sla":
        open_q = ",".join("?" * len(db.OPEN_STATUSES))
        opens = db.rows(
            f"""SELECT r.*, d.name department FROM requests r
                LEFT JOIN departments d ON d.id=r.department_id
                WHERE r.status IN ({open_q})""", tuple(db.OPEN_STATUSES))
        risk = [(t, db.sla_state(t)) for t in opens]
        risk = [(t, s) for t, s in risk if s["breached"] or s["tone"] == "warn"]
        risk.sort(key=lambda x: not x[1]["breached"])
        if not risk:
            return "No requests are breaching or near SLA. 🎉"
        return "**SLA at risk**\n\n" + _table(
            ["Ref", "Request", "Dept", "Priority", "SLA"],
            [[t["ref"], t["title"][:34], t["department"], t["priority"], s["label"]] for t, s in risk[:12]])

    if cmd == "approvals":
        rows_ = db.rows(
            """SELECT r.ref, r.title, r.priority, d.name department, u.name requester FROM requests r
               LEFT JOIN departments d ON d.id=r.department_id
               LEFT JOIN users u ON u.id=r.requester_id
               WHERE r.status='Pending Approval' ORDER BY r.created LIMIT 15""")
        if not rows_:
            return "Nothing awaiting approval. 🎉"
        return "**Pending approval**\n\n" + _table(
            ["Ref", "Request", "Dept", "Requester", "Priority"],
            [[r["ref"], r["title"][:32], r["department"], r["requester"], r["priority"]] for r in rows_])

    if cmd == "requests":
        if arg:
            rows_ = db.rows(
                """SELECT r.ref,r.title,r.priority,r.status,d.name department FROM requests r
                   LEFT JOIN departments d ON d.id=r.department_id WHERE r.status LIKE ?
                   ORDER BY r.created DESC LIMIT 15""", (f"%{arg}%",))
        else:
            open_q = ",".join("?" * len(db.OPEN_STATUSES))
            rows_ = db.rows(
                f"""SELECT r.ref,r.title,r.priority,r.status,d.name department FROM requests r
                    LEFT JOIN departments d ON d.id=r.department_id WHERE r.status IN ({open_q})
                    ORDER BY r.created DESC LIMIT 15""", tuple(db.OPEN_STATUSES))
        if not rows_:
            return "No requests found."
        return _table(["Ref", "Request", "Dept", "Priority", "Status"],
                      [[r["ref"], r["title"][:32], r["department"], r["priority"], r["status"]] for r in rows_])

    if cmd == "priority":
        pri = arg.title() or "Urgent"
        rows_ = db.rows(
            """SELECT r.ref,r.title,r.status,d.name department FROM requests r
               LEFT JOIN departments d ON d.id=r.department_id
               WHERE r.priority=? AND r.status IN ('Submitted','Pending Approval','Approved','In Progress')
               ORDER BY r.created DESC LIMIT 15""", (pri,))
        if not rows_:
            return f"No open {pri} requests."
        return f"**Open {pri} requests**\n\n" + _table(
            ["Ref", "Request", "Dept", "Status"],
            [[r["ref"], r["title"][:34], r["department"], r["status"]] for r in rows_])

    if cmd == "catalog":
        if arg:
            extra, params = "AND (s.name LIKE ? OR s.description LIKE ?)", (f"%{arg}%", f"%{arg}%")
        else:
            extra, params = "", ()
        rows_ = db.rows(
            f"""SELECT s.name, d.name department, s.sla_hours, s.requires_approval FROM services s
                LEFT JOIN departments d ON d.id=s.department_id
                WHERE s.is_active=1 {extra} ORDER BY d.name, s.name LIMIT 20""", params)
        if not rows_:
            return "No matching catalog services."
        return "**Service catalog**\n\n" + _table(
            ["Service", "Department", "SLA", "Approval"],
            [[r["name"], r["department"], f"{r['sla_hours']}h", "Yes" if r["requires_approval"] else "No"] for r in rows_])

    if cmd == "departments":
        rows_ = db.counts_by_department()
        return "**Backlog by department**\n\n" + _table(
            ["Department", "Requests"], [[r["k"], r["n"]] for r in rows_])

    if cmd == "kb":
        clause, params = ("WHERE title LIKE ?", (f"%{arg}%",)) if arg else ("", ())
        rows_ = db.rows(f"SELECT title,views FROM articles {clause} ORDER BY views DESC LIMIT 12", params)
        if not rows_:
            return "No articles found."
        return "**Knowledge base**\n\n" + _table(["Article", "Views"], [[r["title"], f"{r['views']:,}"] for r in rows_])

    return f"Unknown command `/{cmd}`. Try `/help`."


async def stream_chat(message: str):
    cmd = handle_command(message)
    if cmd is not None:
        yield f"data: {json.dumps({'token': cmd})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"
        return
    system = SYSTEM_PROMPT + "\n\n" + snapshot()
    try:
        async for tok in _provider_stream(system, message):
            yield f"data: {json.dumps({'token': tok})}\n\n"
    except Exception as e:  # noqa: BLE001
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
    yield f"data: {json.dumps({'done': True})}\n\n"


async def _provider_stream(system, message):
    import httpx
    provider, model = PROVIDER, MODEL
    if provider in ("xai", "openai"):
        url = "https://api.x.ai/v1/chat/completions" if provider == "xai" else "https://api.openai.com/v1/chat/completions"
        key = os.getenv("XAI_API_KEY" if provider == "xai" else "OPENAI_API_KEY", "")
        if not key:
            yield _no_key(provider); return
        async with httpx.AsyncClient(timeout=90) as client:
            async with client.stream("POST", url, headers={"Authorization": f"Bearer {key}"},
                                     json={"model": model, "stream": True,
                                           "messages": [{"role": "system", "content": system},
                                                        {"role": "user", "content": message}]}) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        try:
                            tok = json.loads(line[6:])["choices"][0]["delta"].get("content", "")
                            if tok: yield tok
                        except (json.JSONDecodeError, KeyError, IndexError):
                            pass
    elif provider == "anthropic":
        key = os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            yield _no_key(provider); return
        async with httpx.AsyncClient(timeout=90) as client:
            async with client.stream("POST", "https://api.anthropic.com/v1/messages",
                                     headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                                     json={"model": model, "max_tokens": 1500, "stream": True,
                                           "system": system, "messages": [{"role": "user", "content": message}]}) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            ev = json.loads(line[6:])
                            if ev.get("type") == "content_block_delta":
                                tok = ev.get("delta", {}).get("text", "")
                                if tok: yield tok
                        except json.JSONDecodeError:
                            pass
    elif provider == "google":
        key = os.getenv("GOOGLE_API_KEY", "")
        if not key:
            yield _no_key(provider); return
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse&key={key}"
        async with httpx.AsyncClient(timeout=90) as client:
            async with client.stream("POST", url, json={
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": message}]}]}) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            tok = json.loads(line[6:])["candidates"][0]["content"]["parts"][0].get("text", "")
                            if tok: yield tok
                        except (json.JSONDecodeError, KeyError, IndexError):
                            pass
    else:
        yield (f"No LLM provider configured (MODEL_PROVIDER='{provider}'). Set it to xai/openai/anthropic/google "
               "in `.env`. Slash-commands like `/sla` work without a key.")


def _no_key(provider):
    env = {"xai": "XAI_API_KEY", "openai": "OPENAI_API_KEY",
           "anthropic": "ANTHROPIC_API_KEY", "google": "GOOGLE_API_KEY"}[provider]
    return (f"⚠ No **{env}** set, so free-form chat is disabled. Add it to `.env` and restart. "
            "Slash-commands (`/sla`, `/approvals`, `/requests`, `/catalog` …) work without any key.")
