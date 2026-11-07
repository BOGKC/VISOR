"""Visor backend (Fonecta Connect Suggests challenge): detect → suggest → contact → decide (no login) → apply.

    pip install fastapi uvicorn
    uvicorn backend.app:app --reload --port 8000        # from the repo root

The bundled Yext mock (started in-process) is the brain: detection data, listings, owner simulator.
Set YEXT_SANDBOX_KEY + YEXT_SANDBOX_ENTITY_ID and every write for the SANDBOX_MIRRORS business
(default FI-D0001 Kahvila Aurora) is also written to the team's real Yext sandbox.
"""
from __future__ import annotations

import csv
import json
import os
import re
import secrets
import socket
import sqlite3
import sys
import tempfile
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from http.server import ThreadingHTTPServer

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("engine", "examples", "mock_api", "backend"):
    sys.path.insert(0, os.path.join(ROOT, sub))
os.environ.setdefault("MOCK_QUIET", "1")

from engine import Engine  # noqa: E402
from yext_client import YextClient, owner_response  # noqa: E402
from messages import build_message, T  # noqa: E402
import live_holidays  # noqa: E402

FRONTEND_URL = (os.environ.get("FRONTEND_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "http://localhost:8000").rstrip("/")
DB_PATH = os.environ.get("DB_PATH", os.path.join(ROOT, "backend", "connect.db"))
HOURS_RE = re.compile(r"^(closed|\d{2}:\d{2}-\d{2}:\d{2}(,\d{2}:\d{2}-\d{2}:\d{2})*)$")
AUTO_APPLY_MIN_CONF = 0.85
LINK_TTL_DAYS = int(os.environ.get("LINK_TTL_DAYS", "21"))   # a link stops working after this, or after the last date passes
RATE_LIMIT = int(os.environ.get("RATE_LIMIT_PER_MIN", "60"))   # owner-page requests per IP per minute
SCHOOL_BREAK = {"fi": "Koululaisten loma", "sv": "Skollov", "nb": "Skoleferie", "en": "School holiday"}


# ---------------------------------------------------------------- Yext: mock in-process unless configured
def _start_mock() -> str:
    import server  # mock_api/server.py
    server.STATE_FILE = os.path.join(tempfile.mkdtemp(), "state.json")
    server.STORE = server.Store()
    if os.environ.get("LOW_MEMORY") == "1":       # small hosts (Render free = 512 MB): drop mock data we never read
        server.STORE.reviews, server.STORE.suggestions = [], []
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    srv = ThreadingHTTPServer(("127.0.0.1", port), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.2)
    return f"http://127.0.0.1:{port}"


YEXT_BASE = os.environ.get("MOCK_BASE_URL") or _start_mock()   # mock = detection data, listings, owner simulator
SIM_BASE = YEXT_BASE
yx = YextClient(base_url=YEXT_BASE)


class SandboxClient(YextClient):
    """Real Yext sandbox. Sends the key as api_key query param as well, like Fonecta's example."""
    def _req(self, method, path, params=None, body=None):
        return super()._req(method, path, {**(params or {}), "api_key": self.key}, body)


SANDBOX_KEY = os.environ.get("YEXT_SANDBOX_KEY")
SANDBOX_ENTITY = os.environ.get("YEXT_SANDBOX_ENTITY_ID")
SANDBOX_MIRRORS = os.environ.get("SANDBOX_MIRRORS", "FI-D0001")   # which demo business is mirrored to the sandbox
sbx = SandboxClient(base_url=os.environ.get("YEXT_SANDBOX_BASE", "https://sbx-api.yextapis.com"), api_key=SANDBOX_KEY,
                    v=datetime.now().strftime("%Y%m%d")) if SANDBOX_KEY and SANDBOX_ENTITY else None

# ---------------------------------------------------------------- data loaded once
eng = Engine(2026)
D = lambda *p: os.path.join(ROOT, *p)  # noqa: E731
contacts = {r["entity_id"]: r for r in csv.DictReader(open(D("data", "customer_contacts.csv"), encoding="utf-8"))}
targets = defaultdict(list)
for r in csv.DictReader(open(D("evaluation", "targets_2026.csv"), encoding="utf-8")):
    targets[r["entity_id"]].append(r)
day_names = {(r["country"], r["date"]): r["name_local"] for r in eng.cal}
day_names_en = {(r["country"], r["date"]): r["name_en"] for r in eng.cal}
events = {e["@id"]: e for e in json.load(open(D("data", "local_events.json"), encoding="utf-8"))["data"]}
_all_dates = sorted(r["date"] for rows in targets.values() for r in rows)
SEASON = (_all_dates[0], _all_dates[-1])
OFFICIAL = defaultdict(dict)          # country -> {date: english name} for official public holidays in the season
KNOWN = defaultdict(set)              # country -> every special day in our calendar
for r in eng.cal:
    KNOWN[r["country"]].add(r["date"])
    if str(r.get("official_public_holiday")) == "1" and SEASON[0] <= r["date"] <= SEASON[1]:
        OFFICIAL[r["country"]][r["date"]] = r["name_en"]


def live_calendar(country: str) -> dict:
    """Bonus live data source: cross-check the season's public holidays with the Nager.Date API."""
    return live_holidays.compare(country, SEASON[0], SEASON[1], OFFICIAL.get(country, {}), KNOWN.get(country))


threading.Thread(target=lambda: [live_calendar(c) for c in ("FI", "SE", "NO")], daemon=True).start()  # warm cache
splits = {r["entity_id"]: r["split"] for r in csv.DictReader(open(D("data", "splits.csv"), encoding="utf-8"))}


# ---------------------------------------------------------------- storage (SQLite; swap for Supabase later)
def db():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS messages(token TEXT PRIMARY KEY, entity_id TEXT, created_at TEXT, channel TEXT,
            lang TEXT, subject TEXT, text TEXT, sms TEXT, kind TEXT);
        CREATE TABLE IF NOT EXISTS items(token TEXT, entity_id TEXT, date TEXT, day_key TEXT, day_name TEXT,
            shown TEXT, suggested TEXT, basis TEXT, evidence TEXT, confidence REAL, reason TEXT,
            decision TEXT, final_hours TEXT, decided_at TEXT, PRIMARY KEY(token, date));
        CREATE TABLE IF NOT EXISTS memory(entity_id TEXT, day_key TEXT, kind TEXT, hours TEXT, suggested TEXT, at TEXT);
        CREATE TABLE IF NOT EXISTS permissions(entity_id TEXT PRIMARY KEY, standing INTEGER, at TEXT);
        CREATE TABLE IF NOT EXISTS human_queue(entity_id TEXT, date TEXT, reason TEXT, at TEXT);
        """)
        try:
            c.execute("ALTER TABLE items ADD COLUMN note TEXT")
        except sqlite3.OperationalError:
            pass


init_db()
if os.environ.get("LOW_MEMORY") == "1":
    import gc
    import ctypes
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)   # hand freed memory back to the OS
    except OSError:
        pass
now = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")  # noqa: E731


def has_standing(eid: str) -> bool:
    with db() as c:
        row = c.execute("SELECT standing FROM permissions WHERE entity_id=?", (eid,)).fetchone()
    if row is not None:
        return bool(row["standing"])
    return contacts.get(eid, {}).get("standing_permission_holidays") == "1"


def memory_for(eid: str):
    with db() as c:
        rows = c.execute("SELECT * FROM memory WHERE entity_id=? ORDER BY at", (eid,)).fetchall()
    out = {}
    for r in rows:
        out[r["day_key"]] = dict(r)          # latest decision per holiday wins
    return out


# ---------------------------------------------------------------- 1 DETECT + 2 SUGGEST
def day_name(eid: str, t: dict, lang: str) -> str:
    if t["day_key"] == "EVENT" and t.get("event_id") in events:
        nm = events[t["event_id"]].get("name", {})
        return nm.get(lang) or nm.get("en") or "Event"
    if t["day_key"] == "SCHOOL_BREAK":
        return SCHOOL_BREAK.get(lang, SCHOOL_BREAK["en"])
    if lang == "en":
        return day_names_en.get((t["country"], t["date"]), t["day_key"])
    return day_names.get((t["country"], t["date"]), t["day_key"])


def live_holiday_hours(eid: str) -> dict:
    """What Yext publishes right now (source of truth after our own writes)."""
    try:
        hol = yx.get_entity(eid).get("hours", {}).get("holidayHours", [])
    except Exception:
        return {}
    out = {}
    for h in hol:
        if h.get("isRegularHours"):
            continue
        out[h["date"]] = "closed" if h.get("isClosed") else ",".join(
            f"{i['start']}-{i['end']}" for i in h.get("openIntervals", [])) or "closed"
    return out


def detect(eid: str, lang_override: str | None = None):
    """Run the engine over every upcoming special day. Applies what the owner taught us (learning layer)."""
    ent = eng.ents[eid]
    lang = lang_override or contacts.get(eid, {}).get("preferred_language") or ent["meta"]["language"]
    mem = memory_for(eid)
    live = live_holiday_hours(eid)
    suggestions, flags, quiet = [], [], []
    for t in sorted(targets.get(eid, []), key=lambda r: r["date"]):
        d = date.fromisoformat(t["date"])
        act, h, basis, conf, ev = eng.explain(eid, d, t["day_key"])
        shown = live.get(t["date"]) or eng.displayed(eid, d)
        if t["date"] in live and act == "SUGGEST" and h == shown:
            act = "NO_ACTION"
        m = mem.get(t["day_key"])
        if m and m["kind"] == "DECLINED" and m["suggested"] == h:
            quiet.append({"date": t["date"], "why": "owner declined this before"})
            continue
        if m and m["kind"] == "EDITED" and act != "FLAG":
            h, basis, conf, ev = m["hours"], "YOUR_EDIT", 0.95, m["hours"]
            act = "SUGGEST" if h != shown else "NO_ACTION"
        item = {"date": d, "day_key": t["day_key"], "day_name": day_name(eid, t, lang), "shown": shown,
                "suggested": h, "basis": basis, "evidence": ev, "confidence": conf}
        if act == "FLAG":
            flags.append(item)
        elif act == "SUGGEST":
            suggestions.append(item)
        else:
            quiet.append({"date": t["date"], "why": "Google already shows the right hours" if basis else
                          "not enough evidence to suggest anything"})
    return lang, suggestions, flags, quiet


# ---------------------------------------------------------------- 5 APPLY
def eta(sec: int) -> str:
    return f"~{sec // 60} min" if sec < 3600 else (f"~{sec // 3600} h" if sec < 86400 else f"~{sec // 86400} d")


def apply_hours(eid: str, day: str, hours: str):
    if not HOURS_RE.match(hours):
        raise HTTPException(400, f"Invalid hours {hours!r}")
    yx.set_holiday_hours(eid, day, hours)
    sandbox_write(eid, day, hours)
    live = [l for l in yx.listings([eid])["listings"] if l["status"] == "LIVE"]   # Fonecta: use listings.json
    return [{"publisher": l["publisherName"], "eta": eta(l["typicalUpdateSpeedSeconds"]),
             "seconds": l["typicalUpdateSpeedSeconds"]} for l in sorted(live, key=lambda x: x["typicalUpdateSpeedSeconds"])]


# ---------------------------------------------------------------- real Yext sandbox (Fonecta's test business)
SANDBOX_LOG: list = []      # last writes, newest first: what /api/sandbox and the console show


def _sbx_log(kind: str, ok: bool, detail: str):
    SANDBOX_LOG.insert(0, {"at": now(), "kind": kind, "ok": ok, "detail": detail[:300]})
    del SANDBOX_LOG[20:]


def sandbox_write(eid: str, day: str, hours: str) -> str | None:
    """Mirror an approved change to the real sandbox. Never breaks the owner's decision if Yext hiccups."""
    if not (sbx and eid == SANDBOX_MIRRORS):
        return None
    try:
        sbx.set_holiday_hours(SANDBOX_ENTITY, day, hours)
        _sbx_log("holiday", True, f"{day} → {hours}")
        return "written"
    except Exception as e:          # noqa: BLE001
        _sbx_log("holiday", False, f"{day}: {e}")
        return "failed"


def sandbox_profile():
    """Fonecta's test business doesn't match the dataset, so make it look like the demo business:
    same name, regular week and a short description. Holiday hours are cleared so the demo starts clean."""
    ent = eng.ents[SANDBOX_MIRRORS]
    week = {d: v for d, v in ent.get("hours", {}).items() if d != "holidayHours"}
    sbx._req("PUT", f"entities/{SANDBOX_ENTITY}", body={"name": ent["name"], "hours": {**week, "holidayHours": []}})
    _sbx_log("profile", True, f"renamed to {ent['name']}, regular hours set, holiday hours cleared")
    try:                            # nice to have; not every Yext setup accepts it
        sbx._req("PUT", f"entities/{SANDBOX_ENTITY}", body={
            "description": f"{ent['name']} – demo business for Visor, the Connect Suggests prototype. "
                           "Holiday hours on this listing are written by Visor after the owner approves."})
    except Exception:               # noqa: BLE001
        pass


def _sandbox_setup_bg():
    if sbx and os.environ.get("SANDBOX_SYNC_PROFILE", "1") != "0":
        try:
            sandbox_profile()
        except Exception as e:      # noqa: BLE001
            _sbx_log("profile", False, str(e))


threading.Thread(target=_sandbox_setup_bg, daemon=True).start()


# ---------------------------------------------------------------- API
app = FastAPI(title="Visor · for Fonecta Connect")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
def health():
    return {"ok": True, "mock": YEXT_BASE, "sandbox": bool(sbx), "sandbox_mirrors": SANDBOX_MIRRORS if sbx else None,
            "default_view": "clean" if os.environ.get("DEFAULT_VIEW", "demo").lower() == "clean" else "demo"}


@app.get("/api/sandbox")
def sandbox_entity():
    """Read back the sandbox business to prove the write landed (show this in the video)."""
    if not sbx:
        raise HTTPException(400, "Set YEXT_SANDBOX_KEY and YEXT_SANDBOX_ENTITY_ID")
    try:
        e = sbx.get_entity(SANDBOX_ENTITY)
    except Exception as ex:         # noqa: BLE001
        return {"id": SANDBOX_ENTITY, "reachable": False, "error": str(ex)[:300], "log": SANDBOX_LOG}
    hours = e.get("hours", {})
    return {"id": SANDBOX_ENTITY, "reachable": True, "name": e.get("name"), "mirrors": SANDBOX_MIRRORS,
            "regular": {d: v for d, v in hours.items() if d != "holidayHours"},
            "holidayHours": hours.get("holidayHours", []), "log": SANDBOX_LOG}


@app.post("/api/sandbox/setup")
def sandbox_setup():
    """Re-apply the demo profile to the sandbox business (name, regular hours, no holiday hours)."""
    if not sbx:
        raise HTTPException(400, "Set YEXT_SANDBOX_KEY and YEXT_SANDBOX_ENTITY_ID")
    try:
        sandbox_profile()
    except Exception as e:          # noqa: BLE001
        _sbx_log("profile", False, str(e))
        raise HTTPException(502, f"Yext sandbox said: {e}")
    return sandbox_entity()


@app.get("/api/businesses")
def businesses(demo_only: bool = True):
    out = []
    for eid, e in eng.ents.items():
        if demo_only and splits.get(eid) != "demo":
            continue
        c = contacts.get(eid, {})
        out.append({"id": eid, "name": e["name"], "city": e["address"]["city"], "segment": e.get("c_segment"),
                    "channel": c.get("preferred_channel"), "language": c.get("preferred_language"),
                    "standing_permission": has_standing(eid), "opted_out": c.get("opted_out_of_suggestions") == "1"})
    return sorted(out, key=lambda x: x["id"])


@app.post("/api/run/{eid}")
def run(eid: str, lang: str | None = None):
    """Steps 1–3: detect, suggest, contact. Returns the message that would be sent and the no-login link.
    ?lang=en overrides the owner's language (handy for an English demo video)."""
    if eid not in eng.ents:
        raise HTTPException(404, "Unknown business")
    if lang and lang not in T:
        raise HTTPException(400, "lang must be fi, sv, nb or en")
    ent, c = eng.ents[eid], contacts.get(eid, {})
    lang, sugg, flags, quiet = detect(eid, lang)
    for f in flags:
        with db() as cx:
            cx.execute("INSERT INTO human_queue VALUES(?,?,?,?)", (eid, f["date"].isoformat(), str(f["evidence"]), now()))
    lc = live_calendar(ent["meta"]["countryCode"])
    for s in sugg + flags:
        s["live_confirmed"] = s["date"].isoformat() in lc["confirmed"]
    base = {"live_calendar": {k: lc[k] for k in ("country", "source", "provider", "checked")} |
            {"confirmed": len(lc["confirmed"]), "new_in_live": lc["new_in_live"]},
            "entity_id": eid, "name": ent["name"], "flagged": [{"date": f["date"].isoformat(), "reason": f["evidence"]}
                                                                for f in flags], "quiet": quiet}
    if flags and not sugg:
        return {**base, "status": "FLAGGED", "note": "Sent to a human: signals say the business may have closed for good."}
    if c.get("opted_out_of_suggestions") == "1":
        return {**base, "status": "OPTED_OUT", "note": "Owner opted out of suggestions; nothing sent."}
    if not sugg:
        return {**base, "status": "ALL_GOOD", "note": "Everything Google shows is already right. Staying quiet."}

    token = secrets.token_urlsafe(16)
    link = f"{FRONTEND_URL}/m/{token}"
    auto, ask = [], sugg
    if has_standing(eid):
        auto = [s for s in sugg if s["confidence"] >= AUTO_APPLY_MIN_CONF]
        ask = [s for s in sugg if s["confidence"] < AUTO_APPLY_MIN_CONF]
    applied = []
    for s in auto:
        where = apply_hours(eid, s["date"].isoformat(), s["suggested"])
        applied.append({"date": s["date"].isoformat(), "hours": s["suggested"], "visible_on": where})
    shown_items = auto + ask
    msg = build_message(lang, ent["name"], sorted(shown_items, key=lambda x: x["date"]), link, auto_applied=bool(auto) and not ask)
    kind = "AUTO_APPLIED" if auto and not ask else ("MIXED" if auto else "ASK")
    with db() as cx:
        cx.execute("INSERT INTO messages VALUES(?,?,?,?,?,?,?,?,?)",
                   (token, eid, now(), c.get("preferred_channel", "EMAIL"), msg["lang"], msg["subject"], msg["text"],
                    msg["sms"], kind))
        for s in shown_items:
            is_auto = s in auto
            cx.execute("INSERT INTO items(token,entity_id,date,day_key,day_name,shown,suggested,basis,evidence,confidence,"
                       "reason,decision,final_hours,decided_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (token, eid, s["date"].isoformat(), s["day_key"], s["day_name"], s["shown"], s["suggested"],
                        s["basis"], json.dumps(s["evidence"], ensure_ascii=False, default=str), s["confidence"],
                        s.get("reason", ""), "AUTO_APPLIED" if is_auto else None, s["suggested"] if is_auto else None,
                        now() if is_auto else None))
    return {**base, "status": kind, "token": token, "link": link, "channel": c.get("preferred_channel"),
            "message": msg, "auto_applied": applied, "items": [_item_out(s) for s in shown_items]}


def _item_out(s):
    return {k: (v.isoformat() if isinstance(v, date) else v) for k, v in s.items()
            if k in ("date", "day_key", "day_name", "shown", "suggested", "basis", "confidence", "reason", "live_confirmed",
                     "shown_text", "suggested_text", "date_text")}


@app.get("/api/m/{token}")
def get_message(token: str):
    """What the no-login decide page shows."""
    with db() as c:
        m = load_message(c, token)
        items = [dict(r) for r in c.execute("SELECT * FROM items WHERE token=? ORDER BY date", (token,))]
    ent = eng.ents[m["entity_id"]]
    for it in items:
        it.pop("evidence", None)
    return {"token": token, "entity_id": m["entity_id"], "name": ent["name"], "city": ent["address"]["city"],
            "lang": m["lang"], "subject": m["subject"], "text": m["text"], "kind": m["kind"], "items": items,
            "standing_permission": has_standing(m["entity_id"]),
            "expires_at": _expires(m["created_at"])}


def _expires(created: str) -> str:
    from datetime import timedelta
    return (datetime.fromisoformat(created) + timedelta(days=LINK_TTL_DAYS)).date().isoformat()


def load_message(c, token: str):
    """The link is the key: one business, these dates, valid for LINK_TTL_DAYS and never after the last date."""
    m = c.execute("SELECT * FROM messages WHERE token=?", (token,)).fetchone()
    if not m:
        raise HTTPException(404, "This link has expired or doesn't exist")
    age = datetime.now(timezone.utc) - datetime.fromisoformat(m["created_at"])
    last = c.execute("SELECT MAX(date) FROM items WHERE token=?", (token,)).fetchone()[0]
    if age.days >= LINK_TTL_DAYS or (last and date.fromisoformat(last) < date.today()):
        raise HTTPException(410, "This link has expired")
    return m


class Decision(BaseModel):
    date: str
    action: str          # approve | edit | decline
    hours: str | None = None
    note: str | None = None   # optional message from the owner with "suggest other"


class Decisions(BaseModel):
    decisions: list[Decision]


@app.post("/api/m/{token}/decide")
def decide(token: str, body: Decisions):
    """Step 4 + 5: owner decides each date; approved/edited hours are written to Yext right away."""
    with db() as c:
        m = load_message(c, token)
        items = {r["date"]: dict(r) for r in c.execute("SELECT * FROM items WHERE token=?", (token,))}
    eid, results = m["entity_id"], []
    for d in body.decisions:
        it = items.get(d.date)
        if not it:
            raise HTTPException(400, f"No suggestion for {d.date}")
        act = d.action.lower()
        if act == "approve":
            final, kind = it["suggested"], "APPROVED"
        elif act == "edit":
            final = (d.hours or "").strip().lower()
            if not HOURS_RE.match(final):
                raise HTTPException(400, f"Hours must look like 10:00-15:00 or closed, got {d.hours!r}")
            kind = "EDITED"
        elif act == "decline":
            final, kind = None, "DECLINED"
        else:
            raise HTTPException(400, "action must be approve, edit or decline")
        where = apply_hours(eid, d.date, final) if final else []
        sb = None
        if final and sbx and eid == SANDBOX_MIRRORS and SANDBOX_LOG:
            sb = "written" if SANDBOX_LOG[0]["ok"] else "failed"
        with db() as c:
            c.execute("UPDATE items SET decision=?, final_hours=?, decided_at=?, note=? WHERE token=? AND date=?",
                      (kind, final, now(), (d.note or "")[:280] or None, token, d.date))
            c.execute("INSERT INTO memory VALUES(?,?,?,?,?,?)", (eid, it["day_key"], kind, final, it["suggested"], now()))
        results.append({"date": d.date, "decision": kind, "hours": final, "visible_on": where, "sandbox": sb})
    lang = m["lang"] if m["lang"] in T else "en"
    return {"results": results, "offer_standing_permission": _should_offer_standing(eid),
            "confirmation": T[lang]["done"] if any(r["hours"] for r in results) else None}


def _should_offer_standing(eid: str) -> bool:
    if has_standing(eid):
        return False
    with db() as c:
        n = c.execute("SELECT COUNT(*) FROM memory WHERE entity_id=? AND kind='APPROVED'", (eid,)).fetchone()[0]
    return n >= 2


class Standing(BaseModel):
    granted: bool


@app.post("/api/standing/{eid}")
def set_standing(eid: str, body: Standing):
    with db() as c:
        c.execute("INSERT OR REPLACE INTO permissions VALUES(?,?,?)", (eid, int(body.granted), now()))
    return {"entity_id": eid, "standing_permission": body.granted}


@app.post("/api/m/{token}/simulate")
def simulate(token: str):
    """Demo helper: let Fonecta's owner simulator answer for each pending date."""
    if not SIM_BASE:
        raise HTTPException(400, "Owner simulator only runs against the local mock")
    with db() as c:
        m = load_message(c, token)
        items = [dict(r) for r in c.execute("SELECT * FROM items WHERE token=? AND decision IS NULL", (token,))]
    decisions = []
    for it in items:
        r = owner_response(m["entity_id"], it["date"], it["suggested"], channel=m["channel"], base_url=SIM_BASE)
        if r["decision"] == "ACCEPTED":
            decisions.append(Decision(date=it["date"], action="approve"))
        elif r["decision"] == "EDITED":
            decisions.append(Decision(date=it["date"], action="edit", hours=r["final_hours"]))
        elif r["decision"] == "REJECTED":
            decisions.append(Decision(date=it["date"], action="decline"))
    return decide(token, Decisions(decisions=decisions)) if decisions else {"results": [], "note": "No reply from owner"}


# ---------------------------------------------------------------- guardrails for the public owner links
_hits: dict = defaultdict(list)


@app.middleware("http")
async def rate_limit(request, call_next):
    path = request.url.path
    if path.startswith("/api/m/") or path.startswith("/m/"):
        ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0]
        t = time.time()
        _hits[ip] = [x for x in _hits[ip] if t - x < 60] + [t]
        if len(_hits[ip]) > RATE_LIMIT:
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Too many requests, try again in a minute"}, status_code=429)
    return await call_next(request)


# ---------------------------------------------------------------- Fonecta-side overview (the dashboard in the video)
_OVERVIEW = None
VIEWS_PROTECTED = 0.643        # share of at-risk search views fixed, measured on the dev split (evaluation/evaluate.py)
DOORS_PREVENTED = 0.735        # share of closed-door visits prevented, same run


def _overview_static():
    global _OVERVIEW
    if _OVERVIEW is None:
        sugg, eids, flagged, per_day = 0, set(), set(), defaultdict(int)
        with open(os.path.join(ROOT, "predictions_2026.csv"), encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["action"] == "SUGGEST":
                    sugg += 1
                    eids.add(r["entity_id"])
                    per_day[r["date"]] += 1
                elif r["action"] == "FLAG":
                    flagged.add(r["entity_id"])
        days = [{"date": d, "count": n} for d, n in sorted(per_day.items()) if n >= 200]
        with open(os.path.join(ROOT, "evaluation", "targets_2026.csv"), encoding="utf-8") as f:
            watched = {r["entity_id"] for r in csv.DictReader(f) if "-D" not in r["entity_id"]}
        _OVERVIEW = {"season": "7 Nov – 6 Jan", "businesses": len(watched), "dates_to_fix": sugg,
                     "owners_to_text": len(eids), "need_a_human": len(flagged),
                     "views_protected": VIEWS_PROTECTED, "doors_prevented": DOORS_PREVENTED, "days": days}
    return _OVERVIEW


DAY_NAMES = {"NYE": "New Year's Eve", "NEW_YEARS_DAY": "New Year's Day", "XMAS_EVE": "Christmas Eve",
             "XMAS_DAY": "Christmas Day", "DEC23": "23 December", "INTERDAY": "the days between", "BOXING_DAY": "Boxing Day", "EPIPHANY": "Epiphany"}


@app.get("/api/overview")
def overview():
    """Season totals from the engine's predictions plus a live feed of what Visor just did."""
    feed = []
    with db() as c:
        for m in c.execute("SELECT m.entity_id, m.created_at, m.kind, COUNT(i.date) n FROM messages m "
                           "JOIN items i ON i.token=m.token GROUP BY m.token ORDER BY m.created_at DESC LIMIT 8"):
            what = (f"auto-pilot applied {m['n']} dates" if m["kind"] == "AUTO_APPLIED"
                    else f"{m['n']} holiday{'s' if m['n'] > 1 else ''} at risk · message sent")
            feed.append({"at": m["created_at"], "entity_id": m["entity_id"], "text": what})
        for h in c.execute("SELECT entity_id, MAX(at) at FROM human_queue GROUP BY entity_id ORDER BY at DESC LIMIT 4"):
            feed.append({"at": h["at"], "entity_id": h["entity_id"], "text": "flagged · signals say closed for good"})
        for d in c.execute("SELECT entity_id, day_key, kind, hours, at FROM memory ORDER BY at DESC LIMIT 8"):
            day = DAY_NAMES.get(d["day_key"], d["day_key"].replace("_", " ").title())
            what = {"APPROVED": f"approved {day}", "EDITED": f"changed {day} to {d['hours']} · remembered",
                    "DECLINED": f"said no thanks to {day} · won't ask again"}.get(d["kind"], d["kind"].lower())
            feed.append({"at": d["at"], "entity_id": d["entity_id"], "text": what})
    feed.sort(key=lambda x: x["at"], reverse=True)
    for x in feed:
        x["name"] = eng.ents[x["entity_id"]]["name"] if x["entity_id"] in eng.ents else x["entity_id"]
    cal = {c: live_calendar(c) for c in ("FI", "SE", "NO")}
    calendar = {"provider": "Nager.Date", "source": "live" if all(v["source"] == "live" for v in cal.values()) else
                ("partial" if any(v["source"] == "live" for v in cal.values()) else "fallback"),
                "countries": {c: {"source": v["source"], "confirmed": len(v["confirmed"]), "checked": v["checked"],
                                  "new_in_live": v["new_in_live"], "missing_live": v["missing_live"]} for c, v in cal.items()}}
    return {**_overview_static(), "feed": feed[:8], "calendar": calendar}


@app.get("/api/live/holidays/{country}")
def live_holidays_for(country: str):
    """The live check itself: our calendar vs Nager.Date for this season."""
    country = country.upper()
    if country not in ("FI", "SE", "NO"):
        raise HTTPException(400, "country must be FI, SE or NO")
    return {"season": {"from": SEASON[0], "to": SEASON[1]}, **live_calendar(country)}


@app.get("/api/memory/{eid}")
def memory(eid: str):
    with db() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM memory WHERE entity_id=? ORDER BY at", (eid,))]
    return {"entity_id": eid, "standing_permission": has_standing(eid), "decisions": rows}


@app.post("/api/reset")
def reset():
    """Undo all writes and forget all decisions (demo reset)."""
    import urllib.request
    try:
        urllib.request.urlopen(urllib.request.Request(f"{YEXT_BASE}/mock/reset", method="POST", data=b"{}"), timeout=10)
    except Exception:
        pass
    with db() as c:
        for t in ("messages", "items", "memory", "permissions", "human_queue"):
            c.execute(f"DELETE FROM {t}")
    threading.Thread(target=_sandbox_setup_bg, daemon=True).start()     # sandbox business back to a clean start
    return {"reset": True}


# ---------------------------------------------------------------- web pages (demo console + no-login decide page)
from fastapi.responses import FileResponse  # noqa: E402

STATIC = os.path.join(ROOT, "backend", "static")


@app.get("/")
def console_page():
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/m/{token}")
def decide_page(token: str):
    return FileResponse(os.path.join(STATIC, "m.html"))


FONTS = os.path.join(STATIC, "fonts")


@app.get("/fonts/{name}")
def font_file(name: str):
    path = os.path.join(FONTS, os.path.basename(name))
    if not os.path.isfile(path):
        raise HTTPException(404, "Not found")
    return FileResponse(path, headers={"Cache-Control": "public, max-age=604800"})


BRAND = os.path.join(ROOT, "brand")


@app.get("/brand/{name}")
def brand_file(name: str):
    path = os.path.join(BRAND, os.path.basename(name))
    if not os.path.isfile(path):
        raise HTTPException(404, "Not found")
    return FileResponse(path)
