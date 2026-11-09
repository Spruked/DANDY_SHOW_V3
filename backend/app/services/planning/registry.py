from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ...core.paths import PROJECT_ROOT

ROOT = PROJECT_ROOT / "brands"
DB_PATH = ROOT / "registry.sqlite3"


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", str(value).strip().lower()).strip("-")
    if not result:
        raise ValueError("Name must contain letters or numbers")
    return result[:80]


def _db() -> sqlite3.Connection:
    ROOT.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript("""
      CREATE TABLE IF NOT EXISTS businesses (
        slug TEXT PRIMARY KEY, name TEXT NOT NULL, brief_path TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS products (
        business_slug TEXT NOT NULL, slug TEXT NOT NULL, name TEXT NOT NULL,
        product_path TEXT NOT NULL, updated_at TEXT NOT NULL,
        PRIMARY KEY (business_slug, slug),
        FOREIGN KEY (business_slug) REFERENCES businesses(slug)
      );
    """)
    return db


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def list_businesses() -> list[dict]:
    with _db() as db:
        rows = db.execute("SELECT b.*, COUNT(p.slug) product_count FROM businesses b LEFT JOIN products p ON p.business_slug=b.slug GROUP BY b.slug ORDER BY b.name").fetchall()
    return [dict(row) for row in rows]


def list_products(business_slug: str) -> list[dict]:
    with _db() as db:
        rows = db.execute("SELECT * FROM products WHERE business_slug=? ORDER BY name", (business_slug,)).fetchall()
    return [dict(row) for row in rows]


def create_business(name: str, brief: str = "", tone: str = "") -> dict:
    slug = _slug(name)
    now = datetime.now(timezone.utc).isoformat()
    folder = ROOT / slug
    folder.mkdir(parents=True, exist_ok=False)
    _write_json(folder / "business.json", {"name": name.strip(), "slug": slug, "tone": tone, "created_at": now})
    (folder / "brief.md").write_text(brief, encoding="utf-8")
    (folder / "assets").mkdir()
    with _db() as db:
        db.execute("INSERT INTO businesses VALUES (?, ?, ?, ?, ?)", (slug, name.strip(), str(folder / "brief.md"), now, now))
    return {"slug": slug, "name": name.strip(), "tone": tone, "product_count": 0}


def create_product(business_slug: str, name: str, brief: str = "", claims: list[str] | None = None,
                   offer: dict | None = None, links: list[str] | None = None, tone: str = "") -> dict:
    business = ROOT / _slug(business_slug)
    if not business.is_dir():
        raise ValueError("Business not found")
    slug = _slug(name)
    folder = business / "products" / slug
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "assets").mkdir(parents=True)
    (folder / "brief.md").write_text(brief, encoding="utf-8")
    _write_json(folder / "claims.json", {"approved_claims": claims or []})
    _write_json(folder / "offer.json", offer or {})
    _write_json(folder / "links.json", {"links": links or []})
    _write_json(folder / "product.json", {"name": name.strip(), "slug": slug, "tone": tone})
    now = datetime.now(timezone.utc).isoformat()
    with _db() as db:
        db.execute("INSERT INTO products VALUES (?, ?, ?, ?, ?)", (business.name, slug, name.strip(), str(folder), now))
    return {"business_slug": business.name, "slug": slug, "name": name.strip(), "tone": tone}


def get_product(business_slug: str, product_slug: str) -> dict:
    folder = ROOT / _slug(business_slug) / "products" / _slug(product_slug)
    if not folder.is_dir():
        raise ValueError("Product not found")
    def read_json(name):
        path = folder / name
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return {"business_slug": folder.parents[1].name, "slug": folder.name,
            "business": json.loads((folder.parents[1] / "business.json").read_text(encoding="utf-8")),
            "product": read_json("product.json"), "brief": (folder / "brief.md").read_text(encoding="utf-8"),
            "claims": read_json("claims.json"), "offer": read_json("offer.json"), "links": read_json("links.json")}
