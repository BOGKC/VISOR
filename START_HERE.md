# Connect Suggests – Customer Approves · Nordic opening-hours simulator v1.1

Since AI Hackathon 2026 × Fonecta · 6–8 Nov 2026, Turku. **All data is synthetic.** No real businesses, customers or Fonecta data.

## Try it in 60 seconds

```bash
python examples/quickstart.py                       # full 5-step loop for Kahvila Aurora, Christmas Eve
python examples/quickstart.py SE-D0008 2026-12-24   # a Swedish café
python examples/quickstart.py FI-D0004 2026-12-24   # a store inside a shopping centre
```

17 demo businesses with ready storylines: `docs/DEMO_SCENARIOS.md`.

Python 3.9+, standard library only. `pip install pandas pyarrow` only if you want the analytics file.

## The scenario

Today is **Friday 6 Nov 2026**. You see everything Connect knows up to 5 Nov. Your system covers **3,000 Connect customers** in Finland, Sweden and Norway (33 business types, 28 cities, 15 shopping centres). For every business and every special day from **7 Nov 2026 to 6 Jan 2027**, decide:

| Action | When |
|---|---|
| `SUGGEST` + hours | what Google shows will be wrong → send the owner a ready-made suggestion |
| `NO_ACTION` | what Google shows is already right → stay quiet |
| `FLAG` | needs a human (e.g. the business looks closed for good) |

Then build the loop around it: **detect → suggest → contact → owner approves / edits / declines (no login) → write back via the Yext API → confirm where the new hours show.**

**Why it matters: findability.** Wrong hours send customers to a closed door, and they also cost visibility. A business with missing or outdated hours can drop out of "open now" searches, and search demand peaks around holidays, exactly when hours are most likely to be wrong. Use `analytics_daily.parquet` to decide which suggestions matter most; the scorer reports how many at-risk search views your suggestions protect.

## What's inside

| Folder / file | What | Real-world counterpart |
|---|---|---|
| `data/entities.json` | 3,032 businesses and shopping centres: address, category, regular hours, holiday hours already entered | Yext Knowledge Graph *Entities: List* |
| `data/holiday_hours_history.jsonl` | Every exception hour entered since 2024, with timestamp and source (owner, Connect suggestion, support) | Connect audit log |
| `data/regular_hours_history.jsonl` | Published regular-hours versions (incl. seasonal closures) | Connect audit log |
| `data/publisher_suggestions.json` | Edits proposed by Google/Apple/Bing users ("closed on 26 Dec") – some right, many wrong | Yext *Publisher Suggestions* |
| `data/reviews.json` | 60k reviews in fi / sv / nb / en, some mention closed doors or wrong hours | Yext *Reviews: List* |
| `data/analytics_daily.parquet` | Daily searches, views, calls, actions per business (2024 → 3 Nov 2026) | Yext *Analytics Reports* |
| `data/listings.json` | Which publishers each business is live on + typical update speed | Yext *Listings* |
| `data/peer_benchmarks.csv` | What similar businesses (same type, country, city size) entered on each holiday – anonymised, ≥10 per cell | Connect's own data |
| `data/pilot_decision_log_2025.csv` | 3,031 suggestions sent in a 2025 pilot and what owners did (accept / edit / reject / no reply, response time, channel) | Learning data |
| `data/customer_contacts.csv` | Preferred channel, language, contact window, standing permission, opt-outs (fake emails/phones) | CRM |
| `data/calendar_special_days.csv` | FI/SE/NO public holidays, eves, observances, commercial days 2024–2027 | Holiday APIs |
| `data/school_breaks.csv`, `local_events.json`, `weather_daily.csv` (+10-day forecast), `weather_normals.csv`, `cities.csv` | Context signals | Municipality calendars, LinkedEvents, FMI/SMHI/MET |
| `labels/` | Answers for **dev** businesses (25%) incl. full history | – |
| `evaluation/` | Target rows + scorer | – |
| `mock_api/` | Local Yext API mock + owner simulator | Yext sandbox |
| `examples/` | Yext client, baseline, quickstart | – |
| `docs/` | Data dictionary, demo storylines, live-source guide, README template, assumptions | – |

## Mock Yext API

```bash
python mock_api/server.py          # http://localhost:8787
curl "http://localhost:8787/v2/accounts/me/entities/FI-D0001?api_key=demo&v=20261101"
```

| Method | Path | Notes |
|---|---|---|
| GET | `/v2/accounts/me/entities` | `limit`≤50, `pageToken`, `filter={"meta.countryCode":{"$eq":"FI"}}` |
| GET / PUT | `/v2/accounts/me/entities/{id}` | PUT `{"hours": {...}}` – validated like Yext; send the full hours object |
| GET | `/v2/accounts/me/reviews` | `locationIds`, `minPublisherDate`, `limit`≤100, `offset` |
| GET | `/v2/accounts/me/listings/publishersuggestions` | `locationIds`, `statuses` |
| GET | `/v2/accounts/me/listings/listings` | after a PUT: `expectedLiveBy` per publisher (step 5 confirmation) |
| POST | `/v2/accounts/me/analytics/reports` | `{"metrics":[…],"dimensions":["DAYS","ENTITY_IDS"],"filters":{…}}` |
| POST | `/sim/v1/owner-response` | `{"entityId","date","proposedHours","channel"}` → ACCEPTED / EDITED / REJECTED / NO_RESPONSE (dev + demo businesses) |
| POST | `/mock/reset` | undo your writes |

**Switching to your Yext sandbox:** code written against the mock works with the sandbox by changing the base URL. `examples/yext_client.py` reads `YEXT_BASE_URL` and `YEXT_API_KEY`: set `YEXT_BASE_URL=https://sbx-api.yextapis.com` and the key Fonecta gives your team. Note: the sandbox has the same API but not the same data – its test businesses have no exception-hour history, so use the mock for detection and the sandbox to demo the write path. Never commit keys.

## Scoring (objective part of "suggestion quality")

```bash
python examples/baseline.py && python evaluation/evaluate.py --predictions outputs/baseline_predictions_2026.csv
```

Predictions: `entity_id,date,action,hours[,confidence]`, rows from `evaluation/targets_2026.csv`. Exact right hours +1, close (±30 min) +0.6, wrong open/closed state −1, needless message −0.1…−0.5 (full rules in `evaluation/evaluate.py`). Organisers score the hidden **test** split. The score ignores contact preferences – your demo should still respect opt-outs and standing permissions.

| Baseline (copy last year → shopping centre → peers) | Score | Exact precision | Recall | Harmful |
|---|---|---|---|---|
| dev, 2026 season | 54.5 | 0.90 | 0.59 | 224 |
| dev, 2025 back-test | 53.2 | 0.90 | 0.58 | 249 |

About 40% of needed changes have no usable history – that is where reviews, peers, the pilot log, events and weather earn points. For the no-history case, start with `FI-D0017` Kahvila Kipinä (new customer: no exception history, no previous decisions).

## Submitting

Submit in the Since AI app by the event deadline (see the event guide). Fill in `docs/README_TEMPLATE.md` as your repository README – it covers everything below.

- **Working demo** of the five steps – live or as a 2–3 minute video, plus a short pitch deck.
- **Code repository** with a README: how to run it, data sources used, third-party libraries and licences.
- In the README, name the **3–5 data sources that matter most** for your solution, where Connect would get them in production, and what you tried that didn't work.
- Include your **final customer messages as text**.
- Show how your solution behaves for a **customer with no history / no previous actions**.
- **Bonus:** replace at least one dataset file with a live source and tell us what you learned – coverage, quality, gaps (`docs/LIVE_SOURCES.md`).
- **Optional, for the score:** `predictions_2026.csv` in the repository root – same columns as above, one row per action for rows of `evaluation/targets_2026.csv` (rows you leave out count as `NO_ACTION`). Organisers score the **test** rows; keep your dev rows in the file and check it with `python evaluation/evaluate.py --predictions predictions_2026.csv`.

## Rules

- Synthetic data only; do not upload anything real. Fonecta's sandbox credentials stay out of repos and videos.
- Back-test honestly: when you simulate 6 Nov 2025, use only rows with timestamps before it.
- List third-party code/data and licences in your README. No GPL/AGPL components without Fonecta's written approval.

Licence: code MIT, data CC BY 4.0, © 2026 Since AI ry. Questions: the Fonecta channel on the Since AI Discord.
