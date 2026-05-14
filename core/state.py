from __future__ import annotations
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable

from core.models import Product

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen (
    sku        TEXT PRIMARY KEY,
    supplier   TEXT NOT NULL,
    name       TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen  TEXT NOT NULL,
    in_stock   INTEGER NOT NULL
);
"""


def connect(db_path: str | Path = "seen.sqlite") -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    return conn


def diff_and_record(conn: sqlite3.Connection, products: Iterable[Product]) -> list[Product]:
    """Return only products whose SKU has never been seen. Updates DB state."""
    now = datetime.utcnow().isoformat(timespec="seconds")
    products = list(products)

    if not products:
        return []

    existing = {row[0] for row in conn.execute(
        "SELECT sku FROM seen WHERE sku IN (%s)" % ",".join("?" * len(products)),
        [p.sku for p in products],
    )}

    new = [p for p in products if p.sku not in existing]

    # Insert new
    conn.executemany(
        "INSERT INTO seen (sku, supplier, name, first_seen, last_seen, in_stock) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [(p.sku, p.supplier, p.name, now, now, int(p.in_stock)) for p in new],
    )
    # Update last_seen on already-known SKUs (handy for debugging)
    conn.executemany(
        "UPDATE seen SET last_seen = ?, in_stock = ? WHERE sku = ?",
        [(now, int(p.in_stock), p.sku) for p in products if p.sku in existing],
    )
    conn.commit()
    return new
