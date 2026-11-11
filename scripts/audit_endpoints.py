"""Check that every API call in the frontend reaches a real backend route.

Backend routes come from the live FastAPI app (OpenAPI table), so quoting
style and router prefixes cannot cause false reports. Frontend calls are
collected from every .js/.jsx file under frontend/src: req(...), fetch(...)
and api-path string literals. `${...}` expressions match one or more path
segments; `{param}` in a backend route matches one segment. Methods are
checked when the call states one ({ method: 'POST' }); otherwise GET.

Exit code 1 when any call has no matching route+method.
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"

# Helpers in api.js that prepend a base path to their argument.
PREFIX_HELPERS = {"mixerRequest": "/mixer", "obsRequest": "/obs"}
CALL = re.compile(r"\b(req|fetch|mixerRequest|obsRequest)\(\s*(`[^`]*`|'[^']*'|\"[^\"]*\")([^)]*)")
METHOD = re.compile(r"method:\s*['\"](GET|POST|PUT|PATCH|DELETE)['\"]", re.I)


def backend_routes() -> list[tuple[str, set[str]]]:
    sys.path.insert(0, str(ROOT / "backend"))
    from app.main import create_app
    app = create_app(runtime_root=Path(tempfile.mkdtemp(prefix="dandy_audit_")), recover_jobs=False)
    return [(path, {m.upper() for m in ops}) for path, ops in app.openapi()["paths"].items()]


def frontend_calls() -> list[tuple[str, str, str]]:
    calls = []
    for file in sorted(FRONTEND.rglob("*.js*")):
        text = file.read_text(encoding="utf-8")
        for match in CALL.finditer(text):
            helper, literal, rest = match.groups()
            path = literal[1:-1].split("?")[0]
            if helper in PREFIX_HELPERS:
                path = PREFIX_HELPERS[helper] + path
            if helper == "fetch":
                if not path.startswith("/api/"):
                    continue
                path = path[len("/api"):]
            if not path.startswith(("/", "${")):
                continue
            method = METHOD.search(rest)
            line = text[:match.start()].count("\n") + 1
            calls.append((path, (method.group(1).upper() if method else "GET"), f"{file.relative_to(ROOT)}:{line}"))
    return calls


def matches(call: str, route: str) -> bool:
    route = route[len("/api"):] if route.startswith("/api/") else route
    concrete = re.sub(r"\{[^/}]+\}", "X", route)
    pattern = "".join("[^?#]+" if part.startswith("${") else re.escape(part)
                      for part in re.split(r"(\$\{[^}]*\})", call))
    return re.fullmatch(pattern, concrete) is not None


def main() -> int:
    routes = backend_routes()
    calls = frontend_calls()
    problems = []
    for path, method, where in calls:
        candidates = [methods for route, methods in routes if matches(path, route)]
        if not candidates:
            problems.append(f"NO ROUTE      {method:6} {path}   ({where})")
        elif method not in set().union(*candidates):
            problems.append(f"WRONG METHOD  {method:6} {path}   ({where}); route allows {sorted(set().union(*candidates))}")
    print(f"backend_paths={len(routes)} frontend_calls={len(calls)} problems={len(problems)}")
    print("\n".join(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
