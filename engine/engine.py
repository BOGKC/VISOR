#!/usr/bin/env python3
"""Suggestion engine v1: baseline signals + learned peer priors for businesses with no history.

    python engine/engine.py                    # 2026 season -> predictions_2026.csv
    python engine/engine.py --season 2025      # honest back-test (only data before 6 Nov 2025)

Order of evidence (first confident one wins):
  1. Closed-for-good signals            -> FLAG
  2. Shopping centre's published hours  -> SUGGEST mall hours
  3. Owner's own entry last year        -> SUGGEST same (two years ago as fallback)
  4. Learned prior from similar businesses (dev truth history, self excluded)
     expressed relative to each business's own regular hours, so "closes 3h early"
     transfers between cafés with different opening times.
Only SUGGEST when the candidate differs from what Google shows now.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "examples"))
from baseline import Baseline, DAYS, day_str, cycle  # noqa: E402


def enc(truth: str, reg: str):
    if truth == "closed":
        return ("C",)
    if truth == reg:
        return ("R",)
    if reg != "closed" and "," not in truth and "," not in reg:
        ts, te = truth.split("-")
        rs, re_ = reg.split("-")
        if ts == rs:
            return ("E", te)          # same opening, different closing time
        if te == re_:
            return ("S", ts)          # different opening, same closing time
    return ("A", truth)               # absolute hours


def dec(code, reg: str):
    k = code[0]
    if k == "C":
        return "closed"
    if k == "R":
        return reg
    if k == "A":
        return code[1]
    if reg == "closed" or "," in reg:
        return None
    rs, re_ = reg.split("-")
    return f"{rs}-{code[1]}" if k == "E" else f"{code[1]}-{re_}"


class Engine(Baseline):
    def __init__(self, season, share_t=0.75, closed_t=0.8, min_n=8):
        super().__init__(season)
        self.share_t, self.closed_t, self.min_n = share_t, closed_t, min_n
        self._build_priors()

    def regular_at(self, eid, d: date):
        cands = [r for r in self.reg[eid] if r["effective_from"] == "before-2024" or r["effective_from"] <= d.isoformat()]
        if not cands:
            return self.regular(eid, d)
        best = max(cands, key=lambda r: "0000" if r["effective_from"] == "before-2024" else r["effective_from"])
        return day_str(best["hours"][DAYS[d.weekday()]])

    def _groups(self, eid, key):
        e = self.ents[eid]
        c, seg = e["meta"]["countryCode"], e["c_segment"]
        tier = self.tiers.get(e["address"]["city"], "?")
        return [(c, seg, tier, key), (c, seg, key)]

    def _build_priors(self):
        self.prior = defaultdict(Counter)
        self.own = defaultdict(Counter)
        path = os.path.join(ROOT, "labels", "dev_truth_history.csv")
        for r in csv.DictReader(open(path, encoding="utf-8")):
            d = date.fromisoformat(r["date"])
            if d >= self.snap or r["entity_id"] not in self.ents:
                continue
            code = enc(r["truth_hours"], self.regular_at(r["entity_id"], d))
            for g in self._groups(r["entity_id"], r["day_key"]):
                self.prior[g][code] += 1
                self.own[(g, r["entity_id"])][code] += 1

    def learned(self, eid, d: date, key: str):
        reg = self.regular(eid, d)
        for g in self._groups(eid, key):
            cnt = self.prior.get(g, Counter()) - self.own.get((g, eid), Counter())
            n = sum(cnt.values())
            if n < self.min_n:
                continue
            closed_share = cnt[("C",)] / n
            if closed_share >= self.closed_t:
                return "closed", closed_share, g
            open_cnt = Counter({k: v for k, v in cnt.items() if k != ("C",)})
            if closed_share > 1 - self.closed_t:   # open/closed is a coin flip: don't guess
                return None, closed_share, g
            code, v = open_cnt.most_common(1)[0]
            share = v / max(1, sum(open_cnt.values()))
            if share >= self.share_t:
                h = dec(code, reg)
                if h:
                    return h, share * (1 - closed_share), g
            return None, share, g
        return None, 0.0, None

    def explain(self, eid, d: date, key: str):
        ent = self.ents[eid]
        if eid in self.closed_signal and not ent.get("closed"):
            return "FLAG", "", "CLOSED_SIGNALS", 0.8, "reviews or map edits say the business has closed for good"
        shown = self.displayed(eid, d)
        cand = basis = ev = None
        conf = 0.0
        mall = ent.get("c_shoppingCenterEntityId")
        if mall:
            m = self.entry(mall, d, self.snap)
            if m and m != "REGULAR":
                cand, basis, ev, conf = m, "SHOPPING_CENTRE", self.ents[mall]["name"], 0.9
        if cand is None:
            for back in (1, 2):
                prev = [x for x in self.dates_by_key[(ent["meta"]["countryCode"], key)] if cycle(x) == cycle(d) - back]
                for p in prev:
                    last = self.entry(eid, p, self.snap)
                    if last is not None:
                        cand = self.regular(eid, d) if last == "REGULAR" else last
                        basis, ev, conf = ("LAST_YEAR" if back == 1 else "TWO_YEARS_AGO"), (p.isoformat(), last), 0.9 - 0.15 * (back - 1)
                if cand is not None:
                    break
        if cand is None:
            h, s, g = self.learned(eid, d, key)
            if h:
                cand, basis, ev, conf = h, "PEERS_LEARNED", (g, round(s, 2)), round(s, 2)
        if cand and cand != shown:
            return "SUGGEST", cand, basis, conf, ev
        return "NO_ACTION", "", basis, conf, ev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026, choices=[2025, 2026])
    ap.add_argument("--out", default=None)
    ap.add_argument("--share", type=float, default=0.75)
    ap.add_argument("--closed", type=float, default=0.8)
    ap.add_argument("--min-n", type=int, default=8)
    a = ap.parse_args()
    eng = Engine(a.season, a.share, a.closed, a.min_n)
    tf = os.path.join(ROOT, "evaluation", "targets_2026.csv" if a.season == 2026 else "targets_2025_backtest.csv")
    out = a.out or os.path.join(ROOT, "predictions_2026.csv" if a.season == 2026 else "outputs/predictions_2025.csv")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    n = 0
    with open(tf, encoding="utf-8") as f, open(out, "w", newline="", encoding="utf-8") as g:
        w = csv.writer(g)
        w.writerow(["entity_id", "date", "action", "hours", "confidence"])
        for r in csv.DictReader(f):
            act, h, _, conf, _ = eng.explain(r["entity_id"], date.fromisoformat(r["date"]), r["day_key"])
            if act != "NO_ACTION":
                w.writerow([r["entity_id"], r["date"], act, h, conf])
                n += 1
    print(f"wrote {n} actions -> {out}")


if __name__ == "__main__":
    main()
