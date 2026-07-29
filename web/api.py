"""FastESM public reads and token-gated integration writes."""

import db

from .api_core import Resource, SQLiteBackend, create_sqlite_api

RESOURCES = (
    Resource("services", "services", "Services", "Published enterprise service catalogue entries.", search_fields=("name", "category", "description")),
    Resource("requests", "requests", "Requests", "Enterprise service requests and their workflow state.", write_fields=("title", "service_id", "department_id", "requester_id", "status", "priority", "form_data"), search_fields=("ref", "title", "status", "priority")),
    Resource("knowledge", "articles", "Knowledge articles", "Service knowledge articles.", search_fields=("title", "content", "author", "status")),
    Resource("departments", "departments", "Departments", "Departments that own and fulfil services.", search_fields=("name",)),
)

backend = SQLiteBackend(db.DB_PATH, RESOURCES, initialize=db.init_schema)
api = create_sqlite_api(
    product="FastESM", version="1.0.0",
    description="Open integration access to FastESM services, requests, knowledge, and departments.",
    base_url="https://esm.fastsme.com", backend=backend, resources=RESOURCES,
)
