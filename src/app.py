from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, render_template, request

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "land_cruiser.sqlite3"
app = Flask(__name__, template_folder=str(TEMPLATE_DIR))
REQUEST_COUNT = 0

SAMPLE_RECORDS: list[dict[str, Any]] = [
    {"external_id": "1001", "model_name": "Land Cruiser", "model_year": 1981},
    {"external_id": "1002", "model_name": "Land Cruiser", "model_year": 1982},
    {"external_id": "1003", "model_name": "Land Cruiser", "model_year": 1983},
    {"external_id": "1004", "model_name": "Land Cruiser", "model_year": 1984},
    {"external_id": "1005", "model_name": "Land Cruiser", "model_year": 1985},
    {"external_id": "1006", "model_name": "Land Cruiser", "model_year": 1986},
    {"external_id": "1007", "model_name": "Land Cruiser", "model_year": 1987},
    {"external_id": "1008", "model_name": "Land Cruiser LX", "model_year": 1987},
    {"external_id": "1009", "model_name": "Land Cruiser", "model_year": 1988},
    {"external_id": "1010", "model_name": "Land Cruiser", "model_year": 1989},
    {"external_id": "1011", "model_name": "Land Cruiser", "model_year": 1990},
]

def normalize_user_input(raw: str) -> str:
    return raw.strip()


def parse_int(raw: str | None) -> int | None:
    if not raw:
        return None
    value = raw.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def get_db_path() -> Path:
    configured = os.getenv("INVENTORY_DB_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return DEFAULT_DB_PATH


def get_connection() -> sqlite3.Connection:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema_and_seed() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                make_name TEXT NOT NULL,
                model_name TEXT NOT NULL,
                model_year INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                UNIQUE(source, external_id, model_year)
            );
            """
        )
        count = conn.execute("SELECT COUNT(*) FROM raw_inventory").fetchone()[0]
        if count > 0:
            return

        now = datetime.now(timezone.utc).isoformat()
        payload = []
        for row in SAMPLE_RECORDS:
            payload.append(
                (
                    "SEED_DEMO",
                    row["external_id"],
                    "TOYOTA",
                    row["model_name"],
                    row["model_year"],
                    json.dumps(row, ensure_ascii=True),
                    now,
                )
            )
        conn.executemany(
            """
            INSERT OR IGNORE INTO raw_inventory
            (source, external_id, make_name, model_name, model_year, payload_json, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            payload,
        )
        conn.commit()


def fetch_inventory_rows(
    min_year: int | None = None,
    max_year: int | None = None,
    model_contains: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    ensure_schema_and_seed()

    where: list[str] = []
    params: list[Any] = []
    if min_year is not None:
        where.append("model_year >= ?")
        params.append(min_year)
    if max_year is not None:
        where.append("model_year <= ?")
        params.append(max_year)
    if model_contains:
        where.append("UPPER(model_name) LIKE ?")
        params.append(f"%{model_contains.upper()}%")

    sql = """
        SELECT id, source, external_id, make_name, model_name, model_year, fetched_at
        FROM raw_inventory
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY model_year ASC, model_name ASC LIMIT ?"
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def summarize_inventory(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "total_records": 0,
            "distinct_years": 0,
            "year_start": None,
            "year_end": None,
        }
    years = sorted({int(row["model_year"]) for row in rows})
    return {
        "total_records": len(rows),
        "distinct_years": len(years),
        "year_start": years[0],
        "year_end": years[-1],
    }


def render_dashboard(echoed_text: str | None = None) -> str:
    min_year = parse_int(request.args.get("min_year"))
    max_year = parse_int(request.args.get("max_year"))
    model_contains = request.args.get("model_contains", "").strip()
    rows = fetch_inventory_rows(min_year=min_year, max_year=max_year, model_contains=model_contains)
    summary = summarize_inventory(rows)

    return render_template(
        "index.html",
        echoed_text=echoed_text,
        rows=rows,
        summary=summary,
        filters={
            "min_year": min_year if min_year is not None else "",
            "max_year": max_year if max_year is not None else "",
            "model_contains": model_contains,
        },
    )


@app.before_request
def count_requests() -> None:
    global REQUEST_COUNT
    REQUEST_COUNT += 1


@app.route("/", methods=["GET"])
def index() -> str:
    return render_dashboard()


@app.route('/echo', methods=['POST'])
def echo() -> str:
    user_input = normalize_user_input(request.form.get('user_input', ''))
    return render_dashboard(echoed_text=user_input)


@app.route("/api/v1/inventory", methods=["GET"])
def api_inventory() -> Response:
    min_year = parse_int(request.args.get("min_year"))
    max_year = parse_int(request.args.get("max_year"))
    model_contains = request.args.get("model_contains", "").strip()
    rows = fetch_inventory_rows(min_year=min_year, max_year=max_year, model_contains=model_contains)
    return jsonify({"count": len(rows), "items": rows})


@app.route("/api/v1/summary", methods=["GET"])
def api_summary() -> Response:
    min_year = parse_int(request.args.get("min_year"))
    max_year = parse_int(request.args.get("max_year"))
    model_contains = request.args.get("model_contains", "").strip()
    rows = fetch_inventory_rows(min_year=min_year, max_year=max_year, model_contains=model_contains)
    summary = summarize_inventory(rows)
    summary["request_count"] = REQUEST_COUNT
    return jsonify(summary)


@app.route('/health', methods=['GET'])
def health() -> tuple[dict[str, Any], int]:
    try:
        ensure_schema_and_seed()
        with get_connection() as conn:
            conn.execute("SELECT 1")
        return jsonify(
            {
                "status": "ok",
                "database": "ok",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            }
        ), 200
    except sqlite3.Error as exc:
        return jsonify({"status": "degraded", "database": "error", "error": str(exc)}), 503


@app.route("/metrics", methods=["GET"])
def metrics() -> Response:
    summary = summarize_inventory(fetch_inventory_rows(limit=1000))
    lines = [
        "# HELP app_requests_total Total HTTP requests handled by the app",
        "# TYPE app_requests_total counter",
        f"app_requests_total {REQUEST_COUNT}",
        "# HELP inventory_records_total Total inventory records visible to the app",
        "# TYPE inventory_records_total gauge",
        f"inventory_records_total {summary['total_records']}",
    ]
    return Response("\n".join(lines) + "\n", mimetype="text/plain; version=0.0.4")


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
