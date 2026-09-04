# Ship Tracker

A live map of ships, built from open AIS radio broadcasts.

Every large vessel continuously broadcasts its identity, position, speed and
heading so that ships do not collide. Those broadcasts are unencrypted, and
several agencies publish them for free. This project listens to them, records
the history that nobody else is storing, and turns it into two things people
cannot easily get today: **how congested a port is**, and **how much CO₂ a
voyage burned**.

Built by two people over three weekends. See [docs/ROLES.md](docs/ROLES.md)
for who owns what.

---

## Quickstart

You need Docker and Python 3.10+.

```bash
git clone <your-repo-url>
cd ship-tracker

cp .env.example .env          # then open .env and set a real password

docker compose up -d db       # starts Postgres/TimescaleDB, applies schema.sql

python -m venv .venv && source .venv/bin/activate
pip install -r ingest/requirements.txt

python ingest/collector.py    # leave this running
```

Within a minute you should see lines like:

```
[19:42:07]  1183 ships seen,  1183 new rows,     1183 total
[19:43:08]  1185 ships seen,   412 new rows,     1595 total
```

The second number dropping is correct and expected — most ships have not moved
since the last poll, so the database rejects the duplicate.

Check it landed:

```bash
docker exec -it ais_db psql -U ais -d shiptracker \
  -c "SELECT count(*), min(ts), max(ts) FROM vessel_positions;"
```

---

## Data source

[Digitraffic](https://www.digitraffic.fi/en/marine-traffic/) — Finnish
Transport Infrastructure Agency open data. No API key, no registration.
Covers Finnish waters and the Gulf of Finland.

[AISStream.io](https://aisstream.io/documentation) gets added in Weekend 1 for
global coverage. It needs a free key, and it has no SLA and does not replay
missed events — if the consumer dies, that data is gone. Which is exactly why
the reconnection logic matters.

---

## Layout

```
schema.sql          The contract. Both tables. Do not change alone.
docker-compose.yml  Engine Room owns this.
ingest/             Engine Room owns this.
analysis/           Bridge owns this.
```

## The one rule

`schema.sql` is shared. Changing it breaks the other person's work without
them touching anything. Tell them before you open the pull request.
