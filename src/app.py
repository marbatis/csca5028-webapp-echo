from __future__ import annotations

import json
import os
import re
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import requests
from flask import Flask, Response, jsonify, render_template, request

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "land_cruiser.sqlite3"
app = Flask(__name__, template_folder=str(TEMPLATE_DIR))
REQUEST_COUNT = 0
DEFAULT_PROJECT_YEAR = 1987
SEED_YEAR_START = DEFAULT_PROJECT_YEAR
SEED_YEAR_END = DEFAULT_PROJECT_YEAR
REQUEST_HEADERS = {"User-Agent": "csca5028-land-cruiser-finder-web/1.0"}
SOURCE_NHTSA_VPIC = "NHTSA_vPIC_MODELS"
SOURCE_NHTSA_RECALLS = "NHTSA_RECALLS"
SOURCE_FUEL_ECONOMY = "FUEL_ECONOMY_MENU"
SOURCE_BAT_LISTINGS = "BAT_LISTINGS"
SOURCE_CLASSICCARS_LISTINGS = "CLASSICCARS_LISTINGS"
SOURCE_DEMO_MARKETPLACE = "DEMO_MARKETPLACE"
MARKETPLACE_SOURCES = {SOURCE_BAT_LISTINGS, SOURCE_CLASSICCARS_LISTINGS, SOURCE_DEMO_MARKETPLACE}
VPIC_URL_TEMPLATE = (
    "https://vpic.nhtsa.dot.gov/api/vehicles/"
    "GetModelsForMakeYear/make/toyota/modelyear/{year}?format=json"
)
RECALLS_URL_TEMPLATE = (
    "https://api.nhtsa.gov/recalls/recallsByVehicle?"
    "make=TOYOTA&model=LAND%20CRUISER&modelYear={year}"
)
FUEL_MODEL_MENU_TEMPLATE = (
    "https://www.fueleconomy.gov/ws/rest/vehicle/menu/model?year={year}&make=Toyota"
)
BAT_AUCTIONS_SEARCH_TEMPLATE = "https://bringatrailer.com/auctions/?search={year}+toyota+land+cruiser"
CLASSICCARS_SEARCH_TEMPLATE = "https://www.classiccars.com/listings/find/{year}/toyota/land-cruiser"
CLASSICCARS_BASE_URL = "https://www.classiccars.com"

BAT_LISTING_PATTERN = re.compile(
    r'"title":"(?P<title>[^"]+)","url":"(?P<url>https:[\\\/]+bringatrailer\.com[\\\/]+listing[\\\/]+[^"]+)"'
    r'.*?"year":"(?P<year>[0-9]{4})","id":(?P<id>[0-9]+)',
    re.S,
)
CLASSICCARS_JSONLD_PATTERN = re.compile(
    r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>',
    re.S,
)

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


def decode_json_escaped(value: str) -> str:
    try:
        return unescape(json.loads(f'"{value}"'))
    except Exception:
        return unescape(value)


def source_display_name(source: str) -> str:
    labels = {
        SOURCE_BAT_LISTINGS: "Bring a Trailer",
        SOURCE_CLASSICCARS_LISTINGS: "ClassicCars.com",
        SOURCE_NHTSA_RECALLS: "NHTSA Recalls",
        SOURCE_NHTSA_VPIC: "NHTSA vPIC",
        SOURCE_FUEL_ECONOMY: "FuelEconomy.gov",
        SOURCE_DEMO_MARKETPLACE: "Demo Marketplace",
    }
    return labels.get(source, source)


def get_project_year() -> int:
    raw = os.getenv("PROJECT_YEAR", str(DEFAULT_PROJECT_YEAR)).strip()
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_PROJECT_YEAR


def enforce_project_year_only() -> bool:
    raw = os.getenv("ENFORCE_PROJECT_YEAR", "1").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def scoped_year_filters(min_year: int | None, max_year: int | None) -> tuple[int | None, int | None]:
    project_year = get_project_year()
    if enforce_project_year_only():
        return project_year, project_year
    if min_year is None and max_year is None:
        return project_year, project_year
    return min_year, max_year


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


def online_seed_enabled() -> bool:
    return os.getenv("ONLINE_SEED_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}


def fetch_seed_records_from_online_sources() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for year in range(SEED_YEAR_START, SEED_YEAR_END + 1):
        try:
            records.extend(fetch_classiccars_listing_records_for_year(year))
        except Exception:
            pass

        try:
            records.extend(fetch_bat_listing_records_for_year(year))
        except Exception:
            pass

        try:
            vpic_response = requests.get(
                VPIC_URL_TEMPLATE.format(year=year),
                timeout=15,
                headers=REQUEST_HEADERS,
            )
            vpic_response.raise_for_status()
            payload = vpic_response.json()
            for row in payload.get("Results", []):
                model_name = str(row.get("Model_Name", "")).strip()
                if "LAND CRUISER" not in model_name.upper():
                    continue
                model_id = str(row.get("Model_ID", "")).strip()
                if not model_id:
                    continue
                records.append(
                    {
                        "source": SOURCE_NHTSA_VPIC,
                        "external_id": model_id,
                        "make_name": str(row.get("Make_Name", "TOYOTA")).strip() or "TOYOTA",
                        "model_name": model_name,
                        "model_year": year,
                        "payload_json": json.dumps(row, ensure_ascii=True),
                    }
                )
        except Exception:
            pass

        try:
            recalls_response = requests.get(
                RECALLS_URL_TEMPLATE.format(year=year),
                timeout=15,
                headers=REQUEST_HEADERS,
            )
            recalls_response.raise_for_status()
            recalls_payload = recalls_response.json()
            for row in recalls_payload.get("results", []):
                campaign = str(row.get("NHTSACampaignNumber", "")).strip()
                if not campaign:
                    continue
                records.append(
                    {
                        "source": SOURCE_NHTSA_RECALLS,
                        "external_id": campaign,
                        "make_name": str(row.get("Make", "TOYOTA")).strip() or "TOYOTA",
                        "model_name": str(row.get("Model", "LAND CRUISER")).strip() or "LAND CRUISER",
                        "model_year": year,
                        "payload_json": json.dumps(row, ensure_ascii=True),
                    }
                )
        except Exception:
            pass

        try:
            fuel_response = requests.get(
                FUEL_MODEL_MENU_TEMPLATE.format(year=year),
                timeout=15,
                headers=REQUEST_HEADERS,
            )
            fuel_response.raise_for_status()
            root = ET.fromstring(fuel_response.text)
            for menu_item in root.findall(".//menuItem"):
                model_name = (menu_item.findtext("text") or "").strip()
                if "CRUISER" not in model_name.upper():
                    continue
                external_id = (menu_item.findtext("value") or model_name).strip()
                if not external_id:
                    continue
                payload = {"text": model_name, "value": external_id, "model_year": year}
                records.append(
                    {
                        "source": SOURCE_FUEL_ECONOMY,
                        "external_id": external_id,
                        "make_name": "TOYOTA",
                        "model_name": model_name,
                        "model_year": year,
                        "payload_json": json.dumps(payload, ensure_ascii=True),
                    }
                )
        except Exception:
            pass
    return records


def fetch_bat_listing_records_for_year(year: int) -> list[dict[str, Any]]:
    response = requests.get(
        BAT_AUCTIONS_SEARCH_TEMPLATE.format(year=year),
        timeout=15,
        headers=REQUEST_HEADERS,
    )
    response.raise_for_status()
    html = response.text
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for match in BAT_LISTING_PATTERN.finditer(html):
        listing_year = int(match.group("year"))
        if listing_year != year:
            continue

        title = decode_json_escaped(match.group("title")).strip()
        if "LAND CRUISER" not in title.upper():
            continue

        listing_id = match.group("id").strip()
        if not listing_id or listing_id in seen_ids:
            continue
        seen_ids.add(listing_id)

        listing_url = match.group("url").replace("\\/", "/").strip()
        payload = {
            "marketplace": "Bring a Trailer",
            "title": title,
            "url": listing_url,
            "year": listing_year,
            "listing_id": listing_id,
        }
        records.append(
            {
                "source": SOURCE_BAT_LISTINGS,
                "external_id": f"BAT-{listing_id}",
                "make_name": "TOYOTA",
                "model_name": title,
                "model_year": listing_year,
                "payload_json": json.dumps(payload, ensure_ascii=True),
            }
        )
    return records


def fetch_classiccars_listing_records_for_year(year: int) -> list[dict[str, Any]]:
    response = requests.get(
        CLASSICCARS_SEARCH_TEMPLATE.format(year=year),
        timeout=15,
        headers=REQUEST_HEADERS,
    )
    response.raise_for_status()
    html = response.text
    blocks = CLASSICCARS_JSONLD_PATTERN.findall(html)
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for block in blocks:
        try:
            payload = json.loads(block)
        except json.JSONDecodeError:
            continue

        model_year_raw = str(payload.get("modelDate", "")).strip()
        if model_year_raw != str(year):
            continue

        manufacturer = str(payload.get("manufacturer", "")).strip().upper()
        model = str(payload.get("model", "")).strip().upper()
        name = str(payload.get("name", "")).strip()
        if "TOYOTA" not in manufacturer or "LAND CRUISER" not in f"{model} {name}".upper():
            continue

        listing_id = str(payload.get("sku", "")).strip()
        if not listing_id or listing_id in seen_ids:
            continue
        seen_ids.add(listing_id)

        offers = payload.get("offers", {})
        listing_url = ""
        if isinstance(offers, dict):
            listing_url = str(offers.get("url", "")).strip()
        if listing_url.startswith("/"):
            listing_url = f"{CLASSICCARS_BASE_URL}{listing_url}"
        if not listing_url:
            continue

        normalized_payload = {
            "marketplace": "ClassicCars.com",
            "title": name,
            "url": listing_url,
            "year": year,
            "listing_id": listing_id,
            "price": offers.get("price") if isinstance(offers, dict) else None,
            "price_currency": offers.get("priceCurrency") if isinstance(offers, dict) else None,
        }
        records.append(
            {
                "source": SOURCE_CLASSICCARS_LISTINGS,
                "external_id": listing_id,
                "make_name": "TOYOTA",
                "model_name": name or "Toyota Land Cruiser",
                "model_year": year,
                "payload_json": json.dumps(normalized_payload, ensure_ascii=True),
            }
        )
    return records


def parse_payload(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("payload_json", "")
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        payload = json.loads(str(raw))
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        return {}


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
        payload: list[tuple[str, str, str, str, int, str, str]] = []

        api_seed_records: list[dict[str, Any]] = []
        if online_seed_enabled():
            api_seed_records = fetch_seed_records_from_online_sources()

        if api_seed_records:
            for row in api_seed_records:
                payload.append(
                    (
                        str(row["source"]),
                        str(row["external_id"]),
                        str(row["make_name"]),
                        str(row["model_name"]),
                        int(row["model_year"]),
                        str(row["payload_json"]),
                        now,
                    )
                )
        else:
            for row in SAMPLE_RECORDS:
                demo_payload = {
                    **row,
                    "marketplace": "Demo Marketplace",
                    "url": f"https://www.classiccars.com/listings/find/{row['model_year']}/toyota/land-cruiser",
                }
                payload.append(
                    (
                        SOURCE_DEMO_MARKETPLACE,
                        row["external_id"],
                        "TOYOTA",
                        row["model_name"],
                        row["model_year"],
                        json.dumps(demo_payload, ensure_ascii=True),
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
    marketplace_only: bool = True,
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
    if marketplace_only:
        source_list = sorted(MARKETPLACE_SOURCES)
        placeholders = ", ".join("?" for _ in source_list)
        where.append(f"source IN ({placeholders})")
        params.extend(source_list)

    sql = """
        SELECT id, source, external_id, make_name, model_name, model_year, payload_json, fetched_at
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


def build_external_detail_url(row: dict[str, Any]) -> str | None:
    source = str(row.get("source", "")).strip()
    external_id = str(row.get("external_id", "")).strip()
    model_year = int(row.get("model_year", 0) or 0)
    model_name = str(row.get("model_name", "")).strip()
    payload = parse_payload(row)

    if source in MARKETPLACE_SOURCES:
        listing_url = str(payload.get("url", "")).strip()
        if listing_url:
            return listing_url

    if source == SOURCE_NHTSA_RECALLS and external_id:
        return f"https://www.nhtsa.gov/recalls?nhtsaId={quote_plus(external_id)}"
    if source in {SOURCE_NHTSA_VPIC, "NHTSA_vPIC"} and model_year:
        return (
            "https://vpic.nhtsa.dot.gov/api/vehicles/"
            f"GetModelsForMakeYear/make/toyota/modelyear/{model_year}?format=json"
        )
    if source == SOURCE_FUEL_ECONOMY and model_year and model_name:
        return (
            "https://www.fueleconomy.gov/feg/PowerSearch.do?action=PowerSearch"
            f"&year1={model_year}&year2={model_year}&make=Toyota&model={quote_plus(model_name)}"
            "&srchtyp=ymm&pageno=1"
        )
    if model_year:
        return (
            "https://vpic.nhtsa.dot.gov/api/vehicles/"
            f"GetModelsForMakeYear/make/toyota/modelyear/{model_year}?format=json"
        )
    return None


def render_dashboard(echoed_text: str | None = None) -> str:
    min_year = parse_int(request.args.get("min_year"))
    max_year = parse_int(request.args.get("max_year"))
    min_year, max_year = scoped_year_filters(min_year, max_year)

    model_contains = request.args.get("model_contains", "").strip()
    rows = fetch_inventory_rows(
        min_year=min_year,
        max_year=max_year,
        model_contains=model_contains,
        marketplace_only=True,
    )
    for row in rows:
        row["external_url"] = build_external_detail_url(row)
        row["source_label"] = source_display_name(str(row.get("source", "")))
        payload = parse_payload(row)
        row["listing_price"] = payload.get("price")
    summary = summarize_inventory(rows)

    return render_template(
        "index.html",
        echoed_text=echoed_text,
        rows=rows,
        summary=summary,
        filters={
            "model_contains": model_contains,
        },
        project_year=min_year if min_year is not None else get_project_year(),
        enforce_project_year=enforce_project_year_only(),
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
    min_year, max_year = scoped_year_filters(min_year, max_year)
    model_contains = request.args.get("model_contains", "").strip()
    rows = fetch_inventory_rows(
        min_year=min_year,
        max_year=max_year,
        model_contains=model_contains,
        marketplace_only=True,
    )
    return jsonify({"count": len(rows), "items": rows})


@app.route("/api/v1/summary", methods=["GET"])
def api_summary() -> Response:
    min_year = parse_int(request.args.get("min_year"))
    max_year = parse_int(request.args.get("max_year"))
    min_year, max_year = scoped_year_filters(min_year, max_year)
    model_contains = request.args.get("model_contains", "").strip()
    rows = fetch_inventory_rows(
        min_year=min_year,
        max_year=max_year,
        model_contains=model_contains,
        marketplace_only=True,
    )
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
    min_year, max_year = scoped_year_filters(None, None)
    summary = summarize_inventory(
        fetch_inventory_rows(min_year=min_year, max_year=max_year, marketplace_only=True, limit=1000)
    )
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
