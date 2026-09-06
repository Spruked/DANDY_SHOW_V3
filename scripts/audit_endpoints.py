from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_API_DIR = ROOT / "backend" / "app" / "api"
FRONTEND_API_FILE = ROOT / "frontend" / "src" / "lib" / "api.js"
FRONTEND_STUDIO_FILE = ROOT / "frontend" / "src" / "components" / "StudioTab.jsx"


def collect_backend_routes() -> set[str]:
    routes: set[str] = set()
    for path in BACKEND_API_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r'@router\.(?:get|post|put|patch|delete)\("([^"]+)"', text):
            route = m.group(1)
            routes.add(route)
            routes.add(f"/api{route}")
    return routes


def normalize_frontend_path(path: str) -> str:
    path = path.split("?")[0]
    for token, repl in {
        "${encodeURIComponent(id)}": "{id}",
        "${encodeURIComponent(episodeId)}": "{episodeId}",
        "${encodeURIComponent(assetId)}": "{assetId}",
        "${encodeURIComponent(adId)}": "{adId}",
        "${encodeURIComponent(exportId)}": "{exportId}",
    }.items():
        path = path.replace(token, repl)
    return path


def collect_frontend_routes() -> set[str]:
    used: set[str] = set()

    api_text = FRONTEND_API_FILE.read_text(encoding="utf-8")
    req_patterns = [
        r"req\(f?`([^`]+)`",
        r"req\('([^']+)'",
        r'req\("([^"]+)"',
    ]
    for pattern in req_patterns:
        for m in re.finditer(pattern, api_text):
            route = normalize_frontend_path(m.group(1))
            if route.startswith("/"):
                used.add(f"/api{route}")

    studio_text = FRONTEND_STUDIO_FILE.read_text(encoding="utf-8")
    if "obsRequest('/status')" in studio_text:
        used.update(
            {
                "/api/obs/status",
                "/api/obs/scenes",
                "/api/obs/scene",
                "/api/obs/stream/toggle",
                "/api/obs/record/toggle",
            }
        )

    return used


def route_match(path: str, route: str) -> bool:
    path_parts = path.strip("/").split("/")
    route_parts = route.strip("/").split("/")
    if len(path_parts) != len(route_parts):
        return False
    for lhs, rhs in zip(path_parts, route_parts):
        if rhs.startswith("{") and rhs.endswith("}"):
            continue
        if lhs != rhs:
            return False
    return True


def main() -> int:
    backend = collect_backend_routes()
    frontend = collect_frontend_routes()
    missing = sorted(p for p in frontend if not any(route_match(p, r) for r in backend))

    print(f"frontend_routes={len(frontend)}")
    print(f"backend_routes={len(backend)}")
    print(f"unmatched_routes={len(missing)}")
    for route in missing:
        print(route)

    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
