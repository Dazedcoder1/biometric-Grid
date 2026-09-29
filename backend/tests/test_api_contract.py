"""
Every endpoint the frontend calls must exist on the backend.

This is the test that would have caught the whole class of bug this file was
written after. The Org Admin screens called eight endpoints that had never been
implemented — settings, activity, leave rejection, four device routes and
fingerprint assignment — and nothing anywhere failed until a person opened the
page. A missing route is not a crash, a failed import or a type error; it is a
404 at runtime, in one role, on one screen, and only for whoever happens to
look. Several had been shipping broken for a long time.

It parses both sides rather than starting a server: the point is to fail in CI
before anything is deployed, and a route table is static information.

Two failure modes it catches:
  * a frontend call with no matching route  (the 404 above)
  * a frontend call whose method is wrong   (405, which reads like a bug in
    the request rather than a mismatch)
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
BACKEND = REPO / "backend"
API_JS = REPO / "frontend" / "src" / "services" / "api.js"

pytestmark = pytest.mark.skipif(
    not API_JS.exists(), reason="frontend not present in this checkout"
)


# ─── backend: the mounted route table ────────────────────────────────────────

ROUTE = re.compile(r'@router\.(get|post|patch|put|delete)\(\s*["\']([^"\']*)["\']')
INCLUDE = re.compile(r"app\.include_router\(\s*(\w+)\s*,\s*prefix=([^,)]+)")
IMPORT = re.compile(
    r"from\s+(app\.api\.routes\.[\w.]+)\s+import\s+router\s+as\s+(\w+)"
)


def _normalise(path: str) -> str:
    """`/employees/{employee_id}` and `/employees/{id}` are the same route."""
    return re.sub(r"\{[^}]+\}", "{}", path).rstrip("/") or "/"


def backend_routes() -> set[tuple[str, str]]:
    main = (BACKEND / "app" / "main.py").read_text(encoding="utf-8")
    prefixes = dict(re.findall(r'(\w*_?PREFIX)\s*=\s*"([^"]+)"', main))
    alias_to_file = {
        alias: BACKEND / (module.replace(".", "/") + ".py")
        for module, alias in IMPORT.findall(main)
    }

    def resolve(raw: str) -> str:
        raw = raw.strip()
        if raw.startswith('f"'):
            raw = raw[2:].rstrip('"')
        raw = raw.strip('"')
        for name, value in prefixes.items():
            raw = raw.replace("{" + name + "}", value).replace(name, value)
        return raw

    routes: set[tuple[str, str]] = set()
    for alias, raw_prefix in INCLUDE.findall(main):
        source = alias_to_file.get(alias)
        if source is None or not source.exists():
            continue
        prefix = resolve(raw_prefix)
        for method, path in ROUTE.findall(source.read_text(encoding="utf-8")):
            routes.add((method.upper(), _normalise(prefix.rstrip("/") + path)))

    # Routers mounted without a `prefix=` keyword.
    for relative, prefix in [("auth/__init__.py", "/api/auth"),
                             ("super_admin/tenants.py", "/api/super")]:
        source = BACKEND / "app" / "api" / "routes" / relative
        if source.exists():
            for method, path in ROUTE.findall(source.read_text(encoding="utf-8")):
                routes.add((method.upper(), _normalise(prefix + path)))
    return routes


# ─── frontend: every call api.js makes ───────────────────────────────────────

CALL = re.compile(
    r"""(?:apiRequest|fetch)\(\s*(?:`|')((?:[^`'\\]|\\.)*)(?:`|')(.*?)(?:\n\s{0,4}\}|\),)""",
    re.S,
)


def _strip_templates(raw: str) -> str:
    """
    Reduce a template literal to the path FastAPI would have to match.

    The rule that separates a path parameter from an appended query string is
    the preceding character: a path parameter is always its own segment and so
    always follows a '/'. Anything else is glued onto the end of a segment and
    is therefore building a query —

        `/api/tenant/employees/${id}`          -> /api/tenant/employees/{}
        `/api/tenant/tasks${taskQuery(f)}`     -> /api/tenant/tasks
        `/api/tenant/attendance/date/${d}${p}` -> /api/tenant/attendance/date/{}

    Guessing from the expression's contents instead (looking for a '?', or for
    a variable called `params`) misses every helper that builds the query
    somewhere else, which is most of them here.
    """
    out, i = [], 0
    while i < len(raw):
        if raw.startswith("${", i):
            depth, j = 1, i + 2
            while j < len(raw) and depth:
                if raw[j] == "{":
                    depth += 1
                elif raw[j] == "}":
                    depth -= 1
                j += 1
            is_path_param = bool(out) and out[-1] == "/"
            out.append("{}" if is_path_param else "")
            i = j
        else:
            out.append(raw[i])
            i += 1
    return "".join(out).split("?")[0].rstrip("/") or "/"


def frontend_calls() -> dict[tuple[str, str], str]:
    source = API_JS.read_text(encoding="utf-8")
    calls: dict[tuple[str, str], str] = {}
    for raw, tail in CALL.findall(source):
        path = _strip_templates(raw)
        if not path.startswith("/api/"):
            continue
        method = (re.search(r"method:\s*'(\w+)'", tail) or [None, "GET"])[1]
        calls[(method.upper(), path)] = raw
    return calls


# ─── the tests ───────────────────────────────────────────────────────────────


def test_scanners_find_something():
    """Guard the guard. A regex matching nothing would make this always pass."""
    routes, calls = backend_routes(), frontend_calls()
    assert len(routes) > 80, f"only parsed {len(routes)} backend routes"
    assert len(calls) > 50, f"only parsed {len(calls)} frontend calls"
    assert ("GET", "/api/settings") in routes
    assert ("GET", "/api/org/dashboard") in routes


def test_every_frontend_call_has_a_backend_route():
    routes = backend_routes()
    missing = sorted(
        f"{method} {path}"
        for (method, path) in frontend_calls()
        if (method, path) not in routes
    )
    assert not missing, (
        "api.js calls endpoints with no route on the backend. These 404 at "
        "runtime, in whichever role opens that screen:\n  "
        + "\n  ".join(missing)
    )


def test_no_frontend_call_uses_the_wrong_method():
    """
    A path that exists under a different method returns 405, which reads as a
    malformed request rather than a mismatch between the two sides.
    """
    routes = backend_routes()
    paths = {path for _, path in routes}
    wrong = []
    for method, path in frontend_calls():
        if (method, path) in routes:
            continue
        if path in paths:
            allowed = sorted(m for m, p in routes if p == path)
            wrong.append(f"{method} {path} — backend allows {', '.join(allowed)}")
    assert not wrong, "Method mismatches:\n  " + "\n  ".join(wrong)
