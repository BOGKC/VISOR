#!/usr/bin/env python3
"""Engine v2: rules first, then a learned model for everything the rules can't cover.

    pip install scikit-learn numpy
    python engine/model.py                 # 2026: writes predictions_2026.csv + engine/decisions_2026.csv
    python engine/model.py --season 2025   # honest back-test (trains only on data before 6 Nov 2025)

Why: ~40% of needed changes have no usable history. The model learns, from Connect's own
truth history (dev businesses, other entities only: grouped cross-validation), how a business
with this segment, city size, regular hours, weekday, shopping-centre status and entry habits
behaves on each special day. It predicts a probability for "closed" and for the most common
open patterns (relative to the business's own regular hours), and we only send a suggestion
when its expected score is clearly positive. Rule-based suggestions (shopping centre, last
year, two years ago) are kept, but vetoed when the model is confident they get open/closed wrong.

Runtime (backend) does not need scikit-learn: it reads engine/decisions_2026.csv.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import GroupKFold

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
from engine import Engine, enc, dec, day_str, DAYS  # noqa: E402

LEAD_DAYS = 45            # training rows are featurised as if seen 45 days before the date
TOP_CODES = 25


def mins(t):
    return int(t[:2]) * 60 + int(t[3:])


def state(h):
    return "closed" if h == "closed" else "open"


def near(a, b, tol=30):
    if a == "closed" or b == "closed":
        return a == b
    ia, ib = a.split(","), b.split(",")
    return abs(mins(ia[0][:5]) - mins(ib[0][:5])) <= tol and abs(mins(ia[-1][-5:]) - mins(ib[-1][-5:])) <= tol


def points(sugg, truth, shown):
    """The scorer's points for SUGGEST `sugg` when truth/shown are as given (evaluation/evaluate.py)."""
    if truth == shown:                                   # no change needed
        if sugg == shown:
            return -0.1
        return -1.0 if state(sugg) != state(shown) else -0.5
    if sugg == truth:
        return 1.0
    if state(sugg) != state(truth):
        return -1.0
    return 0.6 if near(sugg, truth) else 0.2


class Featuriser:
    def __init__(self, eng: Engine):
        self.e = eng
        self.cal_meta = {(r["country"], r["date"]): r for r in eng.cal}
        self.entries = defaultdict(list)          # eid -> [(entered_at, date, closed?)]
        for (eid, d), rows in eng.hol.items():
            for r in rows:
                self.entries[eid].append((r["entered_at"], d, bool(r["holidayHours"].get("isClosed"))))
        self.cats = {k: {} for k in ("country", "segment", "tier", "key", "dtype", "last", "last2", "mall")}

    def cat(self, name, v):
        m = self.cats[name]
        if v not in m:
            m[v] = len(m)
        return m[v]

    def prev_entry(self, eid, country, key, d, as_of, back):
        prev = [x for x in self.e.dates_by_key[(country, key)] if cycle(x) == cycle(d) - back]
        for p in prev:
            v = self.e.entry(eid, p, as_of)
            if v is not None:
                return v
        return None

    def row(self, eid, d: date, key: str, as_of: date, reg: str):
        ent = self.e.ents[eid]
        c = ent["meta"]["countryCode"]
        tier = self.e.tiers.get(ent["address"]["city"], "?")
        seg = ent["c_segment"]
        meta = self.cal_meta.get((c, d.isoformat()), {})
        b = self.e.bench.get((c, tier, seg, key)) or self.e.bench.get((c, "town", seg, key)) or {}
        f = lambda k: float(b[k]) if b.get(k) not in (None, "") else np.nan  # noqa: E731
        last = self.prev_entry(eid, c, key, d, as_of, 1)
        last2 = self.prev_entry(eid, c, key, d, as_of, 2)
        rel = lambda v: "none" if v is None else ("closed" if v == "closed" else ("reg" if v in ("REGULAR", reg) else "special"))  # noqa: E731
        mall = ent.get("c_shoppingCenterEntityId")
        mv = self.e.entry(mall, d, as_of) if mall else None
        cutoff = as_of.isoformat()
        yr_ago = (as_of - timedelta(days=400)).isoformat()
        hist = [x for x in self.entries[eid] if yr_ago <= x[0] < cutoff]
        ro = reg != "closed"
        o = mins(reg.split(",")[0][:5]) if ro else np.nan
        cl = mins(reg.split(",")[-1][-5:]) if ro else np.nan
        if ro and cl <= o:
            cl += 1440
        wk = [day_str(self.e.ents[eid]["hours"].get(dd)) for dd in DAYS]
        return [
            self.cat("country", c), self.cat("segment", seg), self.cat("tier", tier), self.cat("key", key),
            self.cat("dtype", meta.get("day_type", key)), self.cat("last", rel(last)), self.cat("last2", rel(last2)),
            self.cat("mall", "none" if not mall else rel(mv)),
            d.weekday(), int(meta.get("official_public_holiday") or 0), int(ro), o, cl, (cl - o) if ro else np.nan,
            sum(1 for x in wk if x == "closed"),
            len(hist), (sum(x[2] for x in hist) / len(hist)) if hist else np.nan,
            f("share_no_exception_entered"), f("share_entered_closed"), f("share_entered_special_hours"),
            f("closed_share_among_entered"),
            (mins(b["median_close_special"]) if b.get("median_close_special") else np.nan),
        ]


N_CAT = 8


def cycle(d):
    return d.year if d.month >= 2 else d.year - 1


def build(season: int):
    eng = Engine(season)
    fz = Featuriser(eng)
    snap = eng.snap
    # ---- training rows: dev truth history strictly before the snapshot
    X, yc, ycode, groups, regs = [], [], [], [], []
    for r in csv.DictReader(open(os.path.join(ROOT, "labels", "dev_truth_history.csv"), encoding="utf-8")):
        d = date.fromisoformat(r["date"])
        if d >= snap or r["entity_id"] not in eng.ents:
            continue
        reg = eng.regular_at(r["entity_id"], d)
        as_of = min(d - timedelta(days=LEAD_DAYS), snap)
        X.append(fz.row(r["entity_id"], d, r["day_key"], as_of, reg))
        code = enc(r["truth_hours"], reg)
        yc.append(int(code == ("C",)))
        ycode.append(code)
        groups.append(r["entity_id"])
        regs.append(reg)
    X = np.array(X, dtype=float)
    yc = np.array(yc)
    open_codes = Counter(c for c in ycode if c != ("C",))
    top = [c for c, _ in open_codes.most_common(TOP_CODES)]
    code_idx = {c: i for i, c in enumerate(top)}
    ycode_i = np.array([code_idx.get(c, len(top)) if c != ("C",) else -1 for c in ycode])
    print(f"training rows: {len(X)} ({yc.mean():.0%} closed), open codes kept: {len(top)}")
    return eng, fz, X, yc, ycode_i, np.array(groups), top


def fit(X, yc, ycode_i):
    cat = list(range(N_CAT))
    m1 = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06, categorical_features=cat, random_state=0)
    m1.fit(X, yc)
    om = ycode_i >= 0
    m2 = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.06, categorical_features=cat, random_state=0)
    m2.fit(X[om], ycode_i[om])
    return m1, m2


def distribution(m1, m2, x, top, reg):
    """Probability over concrete hours strings for one row."""
    pc = m1.predict_proba(x[None])[0][1]
    dist = Counter({"closed": pc})
    po = m2.predict_proba(x[None])[0]
    for cls, p in zip(m2.classes_, po):
        if cls >= len(top):
            continue
        h = dec(top[cls], reg)
        if h:
            dist[h] += (1 - pc) * p
    return dist


def decide(eng: Engine, fz: Featuriser, models, top, eid, d, key, margin, veto):
    """Return (action, hours, basis, confidence)."""
    act, h, basis, conf, ev = eng.explain(eid, d, key)
    if act == "FLAG":
        return act, h, basis, conf
    shown = eng.displayed(eid, d)
    reg = eng.regular(eid, d)
    x = np.array(fz.row(eid, d, key, eng.snap, reg), dtype=float)
    m1, m2 = models
    dist = distribution(m1, m2, x, top, reg)
    pc = dist["closed"]
    if act == "SUGGEST" and basis != "PEERS_LEARNED":
        p_state = pc if h == "closed" else 1 - pc
        if p_state < veto:
            return "NO_ACTION", "", "MODEL_VETO", round(1 - p_state, 2)
        return act, h, basis, conf
    # no rule (or only the peer prior): pick the candidate with the best expected score
    if shown not in dist:
        dist[shown] += 0.0
    cands = set(dist) | ({h} if h else set())
    best, best_ev = None, 0.0
    for c in cands:
        if c == shown:
            continue
        evv = sum(p * points(c, o, shown) for o, p in dist.items())
        if evv > best_ev:
            best, best_ev = c, evv
    if best and best_ev > margin:
        return "SUGGEST", best, "MODEL", round(dist.get(best, 0), 2)
    return "NO_ACTION", "", "MODEL", 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026, choices=[2025, 2026])
    ap.add_argument("--margin", type=float, default=0.15)
    ap.add_argument("--veto", type=float, default=0.25)
    ap.add_argument("--folds", type=int, default=5)
    a = ap.parse_args()
    eng, fz, X, yc, ycode_i, groups, top = build(a.season)
    tf = os.path.join(ROOT, "evaluation", "targets_2026.csv" if a.season == 2026 else "targets_2025_backtest.csv")
    rows = list(csv.DictReader(open(tf, encoding="utf-8")))
    # grouped cross-validation: a dev business is always predicted by a model that never saw its own history
    uniq = np.unique(groups)
    fold_of = {g: i % a.folds for i, g in enumerate(sorted(uniq))}
    fold_models = {}
    for k in range(a.folds):
        tr = np.array([fold_of[g] != k for g in groups])
        fold_models[k] = fit(X[tr], yc[tr], ycode_i[tr])
        print(f"fold {k} trained")
    full = fit(X, yc, ycode_i)
    out = os.path.join(ROOT, "predictions_2026.csv" if a.season == 2026 else "outputs/predictions_2025_v2.csv")
    dec_out = os.path.join(ROOT, "engine", f"decisions_{a.season}.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    n = 0
    with open(out, "w", newline="", encoding="utf-8") as g, open(dec_out, "w", newline="", encoding="utf-8") as g2:
        w, w2 = csv.writer(g), csv.writer(g2)
        w.writerow(["entity_id", "date", "action", "hours", "confidence"])
        w2.writerow(["entity_id", "date", "action", "hours", "basis", "confidence"])
        for r in rows:
            eid, d = r["entity_id"], date.fromisoformat(r["date"])
            models = fold_models[fold_of[eid]] if eid in fold_of else full
            act, h, basis, conf = decide(eng, fz, models, top, eid, d, r["day_key"], a.margin, a.veto)
            w2.writerow([eid, r["date"], act, h, basis, conf])
            if act != "NO_ACTION":
                w.writerow([eid, r["date"], act, h, conf])
                n += 1
    print(f"wrote {n} actions -> {out}")


if __name__ == "__main__":
    main()
