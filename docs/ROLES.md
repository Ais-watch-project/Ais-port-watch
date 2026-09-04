# Who does what

Two lanes, so neither of us is ever blocked waiting for the other.

| | **Engine Room** | **Bridge** |
|---|---|---|
| Owns | `ingest/`, `docker-compose.yml`, `schema.sql` migrations, CI, deploy | `analysis/`, the model, the dashboard, the writeup |
| Weekend 1 | The listener that never dies: reconnect with backoff, dedupe, Dockerfile | `seed_sample.py` fake data, exploratory analysis, anchorage polygons, congestion query |
| Weekend 2 | Hypertable + indexes, FastAPI read endpoints, full compose, secrets in `.env` | Switch to real data, AIS gap detector, CO₂ estimate, validate against receiver coverage |
| Weekend 3 | pytest, GitHub Actions, public deploy, README architecture diagram | Live map, charts with uncertainty, honest limitations section, demo GIF |

## Why Bridge is not blocked

Bridge builds against `analysis/seed_sample.py` — fake rows in the exact shape
of `schema.sql` — until Engine Room says the real table is populated. Because
the shape is agreed up front, switching over is a one-line change.

## Ground rules

1. **Every file has one owner.** Only `schema.sql` is shared, and it is frozen.
2. **Schema changes get announced before they get merged.**
3. **Branch, pull request, review.** Reviewing the other person's code is how
   you learn the half you did not build.
4. **Ten minutes a day.** What I did, what I am stuck on.
5. **Commit under your own name.** The contribution graph should show two
   real people.

## Before the interviews

Spend an hour where each of you explains the *other* person's half, out loud,
from the code. You will both be asked about the whole system, not your slice.
