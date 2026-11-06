# Run it

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
