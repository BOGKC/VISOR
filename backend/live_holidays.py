"""Live holiday calendar: Nager.Date public-holiday API (free, no API key, MIT licensed).

    GET https://date.nager.at/api/v3/PublicHolidays/{year}/{countryCode}

Visor cross-checks every public holiday in the season against the live calendar, so a moved or newly added
holiday is caught without anyone updating a file. If the API is down, Visor keeps working on the bundled
calendar (calendar_special_days.csv) and says so ("source": "fallback").
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

BASE = os.environ.get("HOLIDAY_API_BASE", "https://date.nager.at/api/v3").rstrip("/")
TTL = 12 * 3600            # holidays don't change by the minute; re-check twice a day
TIMEOUT = 4
_cache: dict = {}          # (country, year) -> (fetched_at, list | None)


def fetch(country: str, year: int):
    """Public holidays for one country and year, or None if the API can't be reached."""
    key = (country, year)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < (TTL if hit[1] is not None else 300):
        return hit[1]
    try:
        req = urllib.request.Request(f"{BASE}/PublicHolidays/{year}/{country}",
                                     headers={"Accept": "application/json", "User-Agent": "visor-connect-demo"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
        rows = [{"date": h["date"], "name": h.get("name") or h.get("localName"), "local_name": h.get("localName"),
                 "nationwide": bool(h.get("global", True)), "types": h.get("types") or []}
                for h in data if isinstance(h, dict) and h.get("date")]
    except Exception:
        rows = None
    _cache[key] = (time.time(), rows)
    return rows


def season(country: str, start: str, end: str):
    """Live public holidays between start and end (ISO dates, inclusive). None if unreachable."""
    out = []
    for y in range(int(start[:4]), int(end[:4]) + 1):
        rows = fetch(country, y)
        if rows is None:
            return None
        out += [r for r in rows if start <= r["date"] <= end and r["nationwide"]]
    return sorted(out, key=lambda r: r["date"])


def compare(country: str, start: str, end: str, bundled: dict, known: set | None = None):
    """bundled: {date: english name} of official public holidays in our calendar for this country/season.
    known: every special day our calendar has (eves included), so only truly unknown holidays count as new."""
    known = set(known or ()) | set(bundled)
    live = season(country, start, end)
    if live is None:
        return {"country": country, "source": "fallback", "provider": "Nager.Date",
                "note": "Live calendar unreachable, using the bundled calendar", "confirmed": [], "missing_live": [],
                "new_in_live": [], "checked": len(bundled)}
    live_dates = {r["date"]: r for r in live}
    return {"country": country, "source": "live", "provider": "Nager.Date",
            "confirmed": sorted(d for d in bundled if d in live_dates),
            "missing_live": sorted(d for d in bundled if d not in live_dates),     # in our file, not in the live API
            "new_in_live": [r for r in live if r["date"] not in known],          # holidays our file doesn't know
            "checked": len(bundled), "live": live}
