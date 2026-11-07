# Visor · for Fonecta Connect

**Visor spots wrong holiday hours before your customers do, texts the owner, and one tap fixes them everywhere. No login.**

Fonecta's "Connect Suggests – Customer Approves" challenge, Since AI hackathon 2026. Solo entry by Rami Gaily.

The name comes from *advisor*, and a visor is a shield: it takes the hit before it reaches the business.

| | |
|---|---|
| **Live app** | https://visor-56r7.onrender.com (free Render plan: the first load after a quiet spell takes up to a minute) |
| **Demo video** | 2:17. A real screen recording of the app, with narration and English subtitles |
| **Score** | **62.6** on Fonecta's scorer, dev split 2026 (baseline 54.5), and **58.0** on the 2025 back-test (baseline 53.2) |
| **Yext sandbox** | Verified live: approved hours are written to Fonecta's sandbox (entity `SinceAI11`) and read back |
| **Live data source** | Nager.Date public-holiday API, cross-checked against the season calendar |

---

## Run it

```bash
pip install -r requirements-deploy.txt     # fastapi + uvicorn, nothing else at runtime
uvicorn backend.app:app --port 8000        # open http://localhost:8000
```

- **Console** (`/`): Fonecta's view and the demo. Pick a business and watch the five steps run, with the owner's phone on the right.
- **Owner page** (`/m/{token}`): the no-login page the text message links to.
- **Engine:** `pip install scikit-learn numpy`, then `python engine/model.py` (about 10 minutes) rewrites `predictions_2026.csv`. Check it with `python evaluation/evaluate.py --predictions predictions_2026.csv`. Add `--season 2025` for the honest back-test, which writes `outputs/predictions_2025_v2.csv`. `python engine/engine.py` runs the rules layer alone.
- **Settings:** optional, all in `.env.example`.
  - `YEXT_SANDBOX_KEY` and `YEXT_SANDBOX_ENTITY_ID` turn on writes to the real Yext sandbox. They go in `.env` locally or in Render's environment settings, never in the repo.
  - `DEFAULT_VIEW=clean` hides the judge-only controls.
  - `LINK_TTL_DAYS` sets how long owner links last.
- **Deploy:** Render Blueprint (`render.yaml`). Push to GitHub, then New → Blueprint, and paste the two sandbox values when Render asks. More detail in [RUN.md](RUN.md).
- **Console views:** **Demo** shows the extra controls for judges (reset, owner simulator, language toggle). **Clean** shows the product as Fonecta would ship it. Add `?view=clean` to the URL to open in Clean.

## The five steps

| Step | What happens | Where in the code |
|---|---|---|
| **1 · Detect** | Every upcoming special day is checked against what Google will show (regular hours plus any holiday hours in Yext). The season's public holidays are cross-checked live with Nager.Date. | `backend/app.py` `detect()`, `engine/engine.py`, `backend/live_holidays.py` |
| **2 · Suggest** | **Rules first:** the owner's own last year, then two years ago, then the shopping centre's hours, then what similar businesses actually did (relative to this owner's regular hours). Each rule comes with a one-line reason. **Then a learned model** (gradient boosting, trained only on other businesses' history) fills the dates the rules can't cover, choosing the hours with the best expected score. It also vetoes a rule it's confident gets open/closed wrong. If evidence is weak, Visor stays quiet. Closed-for-good signals are flagged to a human instead. | `engine/engine.py` `Engine.explain()`, `engine/model.py` |
| **3 · Contact** | One message per owner covering all dates, on their preferred channel (SMS, email, WhatsApp or app push, as stored in Connect) and in their language (fi, sv, nb, en), with a private link. Owners who opted out get nothing. | `backend/messages.py`, `POST /api/run/{entity_id}` |
| **4 · Decide (no login)** | The link opens a phone page: **Approve**, **Suggest other** (own hours plus an optional note) or **No thanks**, per date or all at once. The owner can change their mind from the same link until it expires. | `backend/static/m.html`, `POST /api/m/{token}/decide` |
| **5 · Apply + confirm** | Approved or edited hours are written to Yext right away (and mirrored to the real sandbox). The owner sees where they'll appear and how fast: Google ~2 min, Finder.fi ~10 min, Bing ~1 day, Apple Maps ~2 days… | `backend/app.py` `apply_hours()`, `sandbox_write()` |

**Learning:**
- An edit becomes next year's suggestion for that day.
- A "no thanks" means Visor doesn't ask about that day again.
- After two approvals Visor offers **auto-pilot** (standing permission). From then on it applies high-confidence changes itself and still tells the owner what changed.

These live in `memory` and `permissions` in `backend/app.py`.

**Safety of the no-login link:**
- It goes only to the contact Fonecta already has on file.
- It's a long random token tied to one business and those dates.
- It can only approve, edit or decline hours. Closing a business never happens through a link.
- It expires after 21 days or when the last date passes.
- Guessing gets rate-limited, and every decision is logged.

## Suggestion quality

| Fonecta's scorer (`evaluation/evaluate.py`) | Fonecta baseline | Visor v1 (rules only) | **Visor v2 (submitted)** |
|---|---|---|---|
| **Dev split 2026, score 0–100** | 54.5 | 60.7 | **62.6** |
| **2025 back-test** (only data before 6 Nov 2025) | 53.2 | 52.3 | **58.0** |
| Exact-match precision / recall (2026) | 0.901 / 0.590 | 0.875 / 0.666 | 0.873 / **0.683** |
| At-risk search views protected (2026) | 57.2 % | 64.3 % | **66.3 %** |
| Closed-door visits prevented (2026) | 69.2 % | 73.5 % | **76.9 %** |
| Harmful (wrong open/closed) suggestions (2026) | **224** | 284 | 249 |

`predictions_2026.csv` in the repo root is v2's output for every target row (dev and test).

**How v2 stays honest:**
- The model is trained only on truth history from *before* the snapshot date.
- Each dev business is predicted by a model that never saw its own history (grouped 5-fold cross-validation).
- The two safety settings were chosen to work in *both* seasons, not tuned to one. `--margin 0.55` is how much better than doing nothing a model-only suggestion must score. `--veto 0.25` is how confident the model must be to block a rule.

## Data sources that mattered most

| Signal | How we used it | Where Connect would get it in production |
|---|---|---|
| `holiday_hours_history.jsonl` (owner's own past holiday entries) | Strongest evidence: last year's entry, or two years ago if last year is missing. Only entries made before the snapshot date are used. | Yext entity history / Connect's audit log of holiday-hour edits |
| Shopping-centre entities (`c_shoppingCenterEntityId` + the centre's `holidayHours`) | Shops inside a centre follow the centre's holiday hours | Connect's own shopping-centre entities in Yext |
| Peer behaviour (`dev_truth_history.csv` + `peer_benchmarks.csv`) | Learned priors per country × city size × segment × day, stored *relative to each business's own regular hours*, so "close 4 hours early" transfers between businesses. Used only with ≥ 8 peers and a clear majority. | Aggregated, anonymised holiday hours that all Connect customers publish |
| `calendar_special_days.csv`, plus Nager.Date live | Which days matter, what they're called in fi/sv/nb/en, and which are official holidays | A public-holiday API (Nager.Date, as in this build) plus Fonecta's own commercial-day calendar |
| `customer_contacts.csv` | Channel, language and opt-out for every message | Connect's customer records |

Reviews and Google user suggestions are used only for the closed-for-good guardrail. That business is flagged to a human and never messaged.

## What we tried that didn't work

- **Rules alone were below the baseline on the 2025 back-test (52.3 vs 53.2).** The peer priors need history, and in 2025 they only had one earlier season to learn from. The learned model fixed this (58.0).
- **Simply lowering the rule thresholds made it worse.** Suggesting "closed" when 55–70 % of similar businesses were closed raised harmful suggestions from 284 to over 400 and lowered both scores. Peers alone aren't reliable enough for that.
- **v2 with its first settings nearly doubled the harmful suggestions (489).** It scored 62.1, but at that rate too many wrong suggestions would reach real owners. Raising the bar for model-only suggestions (margin 0.15 → 0.55) kept the score (62.6) and brought harmful suggestions *below* v1 (249).
- **Not specifically modelled yet:** event nights (bars near big events opening later) and school breaks for family venues. Both are in the data, but there was no time to validate them.
- **The live app's explanations come from the rules layer.** The batch model adds a few extra dates in `predictions_2026.csv` (for example New Year's Day for Kahvila Kipinä) that the live demo doesn't text yet. Wiring the model's suggestions into the messages, with their own wording, is the next step.
- **The Yext sandbox has no exception-hour history and no reviews for the test business,** so detection runs on Fonecta's dataset and the sandbox is used for the write path, as Fonecta recommends.

## Customer with no history (`FI-D0017` Kahvila Kipinä)

No past holiday entries and no shopping centre, so the engine falls back to what **similar businesses nearby actually did** on that day:
- same country, city size and segment, measured relative to Kipinä's own regular hours;
- only with at least 8 peers and a clear majority (≥ 80 % closed, or ≥ 75 % sharing the same open pattern).

In the live app, Kipinä gets **one** suggestion, Christmas Day closed (confidence 0.89). The learned model, which also only learns from *other* businesses, adds **New Year's Day closed** (0.77) in `predictions_2026.csv`. Every other day stays quiet because the evidence isn't strong enough. The message says why: *"Most businesses like yours nearby are closed that day."* Once the owner answers, their answer is used from then on instead of the peers.

## Final customer messages (as text)

Generated by the app (`POST /api/run/{id}`), copied exactly. The links point to the live deployment. These particular tokens were cleared by a demo reset, so run the business in the console to get a working one.

### Finnish, the owner's own language

**FI-D0001 Kahvila Aurora** · channel: SMS · subject: *4 pyhäpäivää: tarkista aukioloaikasi*

```text
Hei Kahvila Aurora!
4 tulevan pyhäpäivän aukioloajat voivat näkyä Googlessa väärin:
• Jouluaatto 24.12.: Google näyttää auki klo 7.30–18 → ehdotus auki klo 7.30–13
• Joulupäivä 25.12.: Google näyttää auki klo 7.30–18 → ehdotus kiinni
• Uudenvuodenpäivä 1.1.: Google näyttää auki klo 7.30–18 → ehdotus kiinni
• Loppiainen 6.1.: Google näyttää auki klo 7.30–18 → ehdotus auki klo 10–16
Hyväksy, ehdota muuta tai ohita (ei kirjautumista): https://visor-56r7.onrender.com/m/7msRRUhKXr3njcksZiTE8A
— Visor, Fonecta Connect
```

SMS version:
```text
Hei Kahvila Aurora! 4 tulevan pyhäpäivän aukioloajat voivat näkyä Googlessa väärin. Hyväksy, ehdota muuta tai ohita (ei kirjautumista): https://visor-56r7.onrender.com/m/7msRRUhKXr3njcksZiTE8A
```

### English (`?lang=en`)

**FI-D0001 Kahvila Aurora** · channel: SMS · subject: *4 holidays: check your opening hours*

```text
Hi Kahvila Aurora!
4 upcoming holidays may show the wrong opening hours on Google:
• Christmas Eve 24 Dec: Google shows open 7.30–18 → suggest open 7.30–13
• Christmas Day 25 Dec: Google shows open 7.30–18 → suggest closed
• New Year's Day 1 Jan: Google shows open 7.30–18 → suggest closed
• Epiphany 6 Jan: Google shows open 7.30–18 → suggest open 10–16
Approve, suggest other hours or say no thanks (no login): https://visor-56r7.onrender.com/m/fkz0z8_nk6gmWlYzq8dirA
— Visor, for Fonecta Connect
```

SMS version:
```text
Hi Kahvila Aurora! 4 upcoming holidays may show the wrong opening hours on Google. Approve, suggest other hours or say no thanks (no login): https://visor-56r7.onrender.com/m/fkz0z8_nk6gmWlYzq8dirA
```

### Swedish

**SE-D0008 Kafé Linnea** · channel: EMAIL · subject: *5 helgdagar: kolla era öppettider*

```text
Hej Kafé Linnea!
5 kommande helgdagar kan visa fel öppettider på Google:
• Lucia 13/12: Google visar öppet 10–17 → förslag öppet 7–18
• Julafton 24/12: Google visar öppet 8–18 → förslag stängt
• Juldagen 25/12: Google visar öppet 8–18 → förslag stängt
• Nyårsdagen 1/1: Google visar öppet 8–18 → förslag stängt
• Trettondedag jul 6/1: Google visar öppet 8–18 → förslag öppet 10–16
Godkänn, föreslå annat eller tacka nej (ingen inloggning): https://visor-56r7.onrender.com/m/rhSH1nc-2KMWk1K8TbRwEQ
— Visor, Hitta Connect
```

### Norwegian

**NO-D0009 Bakeri Fjord** · channel: SMS · subject: *3 helligdager: sjekk åpningstidene*

```text
Hei Bakeri Fjord!
3 kommende helligdager kan vise feil åpningstider på Google:
• Første juledag 25.12.: Google viser åpent 7–18 → forslag stengt
• Nyttårsaften 31.12.: Google viser åpent 7–18 → forslag åpent 7–14
• Første nyttårsdag 1.1.: Google viser åpent 7–18 → forslag stengt
Godkjenn, foreslå annet eller si nei takk (ingen innlogging): https://visor-56r7.onrender.com/m/kPGO86eNtJbklB2mMTqzRw
— Visor, Connect
```

SMS version:
```text
Hei Bakeri Fjord! 3 kommende helligdager kan vise feil åpningstider på Google. Godkjenn, foreslå annet eller si nei takk (ingen innlogging): https://visor-56r7.onrender.com/m/kPGO86eNtJbklB2mMTqzRw
```

### No history (cold start)

**FI-D0017 Kahvila Kipinä, Finnish** · channel: SMS · subject: *Joulupäivä: ovatko aukioloaikanne oikein?*

```text
Hei Kahvila Kipinä!
Joulupäivä on perjantaina 25.12. Useimmat vastaavat yritykset alueellanne ovat silloin kiinni, eikä teille ole merkitty poikkeusaikoja. Siksi Google näyttää nyt: auki klo 8–17.
Ehdotamme: 25.12. kiinni
Hyväksy, ehdota muuta tai ohita (ei kirjautumista): https://visor-56r7.onrender.com/m/7X0uW01gLPhHd0F3nuiGhw
— Visor, Fonecta Connect
```

**FI-D0017 Kahvila Kipinä, English** · channel: SMS · subject: *Christmas Day: are your opening hours right?*

```text
Hi Kahvila Kipinä!
Christmas Day is on Friday 25 Dec. Most businesses like yours nearby are closed that day, and no special hours are set for you. So Google now shows open 8–17.
We suggest: 25 Dec closed
Approve, suggest other hours or say no thanks (no login): https://visor-56r7.onrender.com/m/0yVV3fXNieTLyAqbsjAaNA
— Visor, for Fonecta Connect
```

### Auto-pilot (owner granted standing permission, so this informs instead of asking)

**FI-D0012 Tilitoimisto Otso, Finnish** · channel: EMAIL · subject: *8 pyhäpäivää: tarkista aukioloaikasi*

```text
Hei Tilitoimisto Otso!
Kuten sovittiin, päivitimme 8 poikkeusaukioloa automaattisesti:
• Jouluaatto 24.12.: kiinni
• Joulupäivä 25.12.: kiinni
• Välipäivä 28.12.: kiinni
• Välipäivä 29.12.: kiinni
• Välipäivä 30.12.: kiinni
• Uudenvuodenaatto 31.12.: kiinni
• Uudenvuodenpäivä 1.1.: kiinni
• Loppiainen 6.1.: kiinni
Haluatko muuttaa jotain? (ei kirjautumista): https://visor-56r7.onrender.com/m/pTpVGleyW6hxs63S6dQTHw
— Visor, Fonecta Connect
```

**FI-D0012 Tilitoimisto Otso, English** · channel: EMAIL · subject: *8 holidays: check your opening hours*

```text
Hi Tilitoimisto Otso!
As you asked, we updated 8 holiday hours automatically:
• Christmas Eve 24 Dec: closed
• Christmas Day 25 Dec: closed
• Between Christmas and New Year 28 Dec: closed
• Between Christmas and New Year 29 Dec: closed
• Between Christmas and New Year 30 Dec: closed
• New Year's Eve 31 Dec: closed
• New Year's Day 1 Jan: closed
• Epiphany 6 Jan: closed
Want anything changed? (no login): https://visor-56r7.onrender.com/m/9gTz77ECyQea3NX8zY_LGA
— Visor, for Fonecta Connect
```

### When nothing is sent

- `FI-D0011` Pizzeria Torni: **FLAGGED**. *Sent to a human: signals say the business may have closed for good.*
- `FI-D0013` Hammasklinikka Kallio: **ALL_GOOD**. *Everything Google shows is already right. Staying quiet.*

### Follow-ups after the owner decides (approve / edit / decline)

What the owner sees on the page, in English (all four languages are in `backend/static/m.html`):

| Owner action | Confirmation |
|---|---|
| Approve | *Approved · publishing*, then *Your new hours are on their way. Here's where customers will see them:* Google (Search & Maps) ~2 min · Finder.fi / Fonecta.fi ~10 min · Fonecta Caller ~1 h · Bing ~1 d · Apple Maps ~2 d … |
| Suggest other (10:00–14:00, note "Brunch only") | *Saved your hours · publishing*, plus the same publisher list |
| No thanks | *Skipped · we won't ask about this again* |
| Second approval | *Want us to handle holiday hours automatically? We'll update them for you and always tell you what changed. You can switch this off anytime.* → **Yes, handle it** / **Not now** |

Confirmation text returned with the decision: *"Done! Your new hours are being published."* (fi: *"Valmis! Uudet aukioloajat julkaistaan."*)


## Bonus: live sources

**1 · Public holidays: Nager.Date** (`https://date.nager.at`, free, no API key, cached 12 h). This replaces the public-holiday part of `calendar_special_days.csv`.

- **Coverage:** checked on the live app, all **13 official holidays in the season matched**: FI 6/6, SE 4/4, NO 3/3. None missing, none unexpected.
- **Differences:** Nager.Date treats **Christmas Eve as a public holiday in Sweden and Norway** and **New Year's Eve in Sweden**, while Fonecta's calendar marks them as eves. Both are in our calendar, so they aren't flagged as new.
- **Gaps:** the API has no commercial days (Black Friday), no observances (Father's Day, Lucia), no school breaks and no local events, so the bundled calendar is still needed for those. If the API is unreachable, Visor carries on with the bundled calendar and says so.
- **Where it shows:** the Detect step shows "holidays live ✓ 6/6", suggestions get a LIVE ✓ tag, and the dashboard shows the check per country. Endpoint: `GET /api/live/holidays/{FI|SE|NO}`.

**2 · Yext sandbox (Fonecta's real write path)**

- **Rename:** on start, Visor renames the team's test business (`SinceAI11`, originally "Northern Trail Rentals") to the demo café Kahvila Aurora with its regular hours, as Fonecta allowed.
- **Writes:** every approved or edited date is written to the sandbox with a read-modify-write of the full `hours` object, so other days are never lost.
- **Verified on 7 Nov 2026:** 24 Dec 07:30–13:00 (approved) and 25 Dec 10:00–14:00 (owner's own hours) were written and read back. `GET /api/sandbox` shows the business and a write log.
- **Clean state:** "Reset demo" clears the sandbox holiday hours again.
- **Failure handling:** a failed sandbox call never breaks the owner's decision; it's logged and shown as "sandbox retry needed".

## Third-party code, data and licences

| Component | Licence |
|---|---|
| FastAPI | MIT |
| Uvicorn | BSD-3-Clause |
| Pydantic (via FastAPI) | MIT |
| Geist and Geist Mono fonts (Vercel), served from `backend/static/fonts` | SIL Open Font License 1.1 |
| Fonecta challenge package: `mock_api/`, `examples/`, `evaluation/` | MIT (© 2026 Since AI ry) |
| Challenge data: `data/`, `labels/`, `evaluation/*.csv` | CC BY 4.0, "Connect Suggests simulator, Since AI ry 2026" |
| Nager.Date public-holiday API (called at runtime, no code included) | MIT; free public API |
| Demo video only (not part of the app or this repo): Remotion · Kokoro TTS model + kokoro-onnx · ffmpeg | Remotion License (free for individuals) · Apache-2.0 / MIT · used as a command-line tool, not shipped |
| scikit-learn, NumPy, SciPy, joblib, threadpoolctl (engine v2, offline batch run only, not needed by the web app) | BSD-3-Clause |

No GPL or AGPL components are included.

Synthetic data only. The Yext sandbox key lives only in the deployment's environment settings, never in this repository or the video.
