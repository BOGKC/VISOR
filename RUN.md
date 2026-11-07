# Run Visor

Drop `engine/`, `backend/`, `.env.example`, `.gitignore` and this file into the root of the Fonecta challenge package.

```bash
pip install fastapi uvicorn
python engine/engine.py                         # writes predictions_2026.csv (scored file)
python evaluation/evaluate.py --predictions predictions_2026.csv
uvicorn backend.app:app --port 8000             # API on http://localhost:8000 (docs at /docs)
```

Sandbox: copy `.env.example` to `.env`, fill in your key and entity ID, then
`set -a; source .env; set +a` before starting uvicorn. Writes for FI-D0001 are mirrored to the sandbox.

## API (the five steps)
| Step | Call |
|---|---|
| 1–3 Detect, suggest, contact | `POST /api/run/{entity_id}` → message text + no-login link token |
| Decide page data | `GET /api/m/{token}` |
| 4–5 Decide + apply | `POST /api/m/{token}/decide` `{"decisions":[{"date":"2026-12-24","action":"approve"}]}` (approve / edit + hours / decline) |
| Owner simulator (demo) | `POST /api/m/{token}/simulate` |
| Standing permission | `POST /api/standing/{entity_id}` `{"granted": true}` |
| What it learned | `GET /api/memory/{entity_id}` |
| Sandbox read-back | `GET /api/sandbox` |
| Reset demo | `POST /api/reset` |

## Deploy (Render, free)
1. Push the repo to GitHub (check `git status` shows no `.env`).
2. render.com → New → Blueprint → pick the repo. It reads `render.yaml`.
3. Paste your Yext sandbox key and entity ID when Render asks. They stay in Render, not in the repo.
4. Wait for the deploy (first build ~3 min, start ~30 s). Open the `onrender.com` link.

Free plan sleeps after 15 min without visitors and takes ~1 min to wake up: open the link yourself before judging. Demo data resets on each restart.

## Live data source: holiday calendar

Visor checks the season's public holidays against the free Nager.Date API (`https://date.nager.at/api/v3`, no API key needed, so there's nothing to leak). It's cached for 12 hours. If the API can't be reached, Visor keeps working on the bundled `calendar_special_days.csv` and the console says "bundled calendar".

- `GET /api/live/holidays/FI` (or SE, NO): our calendar vs the live one (confirmed, missing, new holidays)
- The Detect step shows "holidays live ✓ 6/6", each suggestion gets a LIVE ✓ tag, and the dashboard shows the check per country.
