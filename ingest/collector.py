"""
The crude collector. Run this TONIGHT.

It is deliberately simple: ask Digitraffic for every ship's position once a
minute, write what comes back into Postgres, repeat forever.

It is not good code. It does not need to be. Its only job is to make sure
that by the time you start building properly, you already have days of
history sitting in a database. History cannot be created retroactively.

Weekend 1 replaces this with a proper streaming service. Until then, this
runs in a terminal (or better, on a cheap server) and quietly does its job.

    python ingest/collector.py
"""

import os
import sys
import time
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

load_dotenv()

# Digitraffic is Finnish open data: no API key, no registration, no limits
# worth worrying about. That is why we start here rather than with AISStream.
LOCATIONS_URL = "https://meri.digitraffic.fi/api/ais/v1/locations"
VESSELS_URL = "https://meri.digitraffic.fi/api/ais/v1/vessels"

# They ask API users to identify themselves. Be a polite citizen.
HEADERS = {
    "Accept": "application/json",
    "Digitraffic-User": "student-project/ship-tracker",
}

POSITION_INTERVAL = 60          # seconds between position polls (polite, and plenty)
METADATA_INTERVAL = 30 * 60   # ship names change rarely; poll them less often


def connect():
    """Open a database connection using the values in .env."""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        user=os.getenv("POSTGRES_USER", "ais"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        dbname=os.getenv("POSTGRES_DB", "shiptracker"),
    )


def parse_positions(payload):
    """
    Digitraffic returns GeoJSON. One 'feature' per ship, shaped like this:

        {"mmsi": 259545000,
         "geometry": {"coordinates": [19.03, 58.68], "type": "Point"},
         "properties": {"sog": 10.2, "cog": 207, "heading": 207,
                        "navStat": 0, "timestampExternal": 1587929638085}}

    Note coordinates are [longitude, latitude] — that order catches everyone
    out at least once. Also note timestampExternal is in MILLIseconds.
    """
    rows = []
    for feature in payload.get("features", []):
        props = feature.get("properties", {}) or {}
        coords = (feature.get("geometry") or {}).get("coordinates") or []

        mmsi = feature.get("mmsi") or props.get("mmsi")
        ms = props.get("timestampExternal")
        if mmsi is None or ms is None or len(coords) < 2:
            continue  # incomplete message, skip it rather than crash

        rows.append((
            int(mmsi),
            datetime.fromtimestamp(ms / 1000, tz=timezone.utc),
            coords[1],              # latitude
            coords[0],              # longitude
            props.get("sog"),
            props.get("cog"),
            props.get("heading"),
            props.get("navStat"),
            "digitraffic",
        ))
    return rows


def save_positions(conn, rows):
    """
    Insert everything at once. ON CONFLICT DO NOTHING is our deduplication:
    the primary key is (mmsi, ts), so a position we already have is simply
    ignored. No Python logic needed — let the database do the work.
    """
    if not rows:
        return 0
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """INSERT INTO vessel_positions
               (mmsi, ts, lat, lon, sog, cog, heading, nav_status, source)
               VALUES %s ON CONFLICT (mmsi, ts) DO NOTHING""",
            rows,
        )
        inserted = cur.rowcount
    conn.commit()
    return inserted


def save_vessels(conn):
    """Ship names and sizes. Overwrite what we had — this is current truth."""
    resp = requests.get(VESSELS_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    rows = []
    now = datetime.now(timezone.utc)
    for v in resp.json():
        if v.get("mmsi") is None:
            continue
        # refA/refB are distances from the antenna to bow/stern; together
        # they give the ship's length. Same idea for refC/refD and width.
        a, b = v.get("refA") or 0, v.get("refB") or 0
        c, d = v.get("refC") or 0, v.get("refD") or 0
        rows.append((
            int(v["mmsi"]),
            (v.get("name") or "").strip() or None,
            (v.get("callSign") or "").strip() or None,
            v.get("imo"),
            v.get("shipType"),
            (a + b) or None,
            (c + d) or None,
            v.get("draught"),
            (v.get("destination") or "").strip() or None,
            str(v.get("eta")) if v.get("eta") is not None else None,
            now,
        ))

    if not rows:
        return 0
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """INSERT INTO vessels
               (mmsi, name, call_sign, imo, ship_type, length_m, width_m,
                draught_m, destination, eta, updated_at)
               VALUES %s
               ON CONFLICT (mmsi) DO UPDATE SET
                   name = EXCLUDED.name,
                   call_sign = EXCLUDED.call_sign,
                   imo = EXCLUDED.imo,
                   ship_type = EXCLUDED.ship_type,
                   length_m = EXCLUDED.length_m,
                   width_m = EXCLUDED.width_m,
                   draught_m = EXCLUDED.draught_m,
                   destination = EXCLUDED.destination,
                   eta = EXCLUDED.eta,
                   updated_at = EXCLUDED.updated_at""",
            rows,
        )
    conn.commit()
    return len(rows)


def log(message):
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


def main():
    try:
        conn = connect()
    except Exception as exc:
        log(f"cannot reach the database: {exc}")
        log("is it running? try:  docker compose up -d db")
        sys.exit(1)

    log("collector started — leave this running")
    total = 0
    last_metadata = 0.0
    backoff = 5  # seconds to wait after a failure, doubling each time

    while True:
        try:
            resp = requests.get(LOCATIONS_URL, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            rows = parse_positions(resp.json())
            new = save_positions(conn, rows)
            total += new
            log(f"{len(rows):>5} ships seen, {new:>5} new rows, {total:>8} total")

            if time.time() - last_metadata > METADATA_INTERVAL:
                count = save_vessels(conn)
                last_metadata = time.time()
                log(f"refreshed metadata for {count} vessels")

            backoff = 5  # success, reset the penalty
            time.sleep(POSITION_INTERVAL)

        except KeyboardInterrupt:
            log(f"stopped by you — {total} rows collected this run")
            break

        except Exception as exc:
            # Never die. The feed will go down, your wifi will drop, the
            # database will hiccup. Wait a bit longer each time, up to 5 min,
            # so we do not hammer a service that is already struggling.
            log(f"error: {exc} — retrying in {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)
            try:
                conn.rollback()
            except Exception:
                conn = connect()

    conn.close()


if __name__ == "__main__":
    main()
