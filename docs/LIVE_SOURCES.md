# Swapping a dataset file for a live source (bonus)

Every file in `data/` stands in for something Connect could read in production. To earn the bonus, replace at least one file with a live source and report what you learned: coverage, quality, gaps.

| Dataset file | Live source to try | Notes |
|---|---|---|
| `entities.json`, `holiday_hours_history.jsonl` | Your team's **Yext sandbox** – Knowledge Graph *Entities* (`hours`, `holidayHours`) | Same API as the mock, but the sandbox businesses have **no exception-hour history**. Use the mock for detection and the sandbox to demo the write path. |
| `reviews.json`, `publisher_suggestions.json`, `listings.json`, `analytics_daily.parquet` | Yext sandbox: *Reviews*, *Listings › Publisher Suggestions*, *Listings*, *Analytics Reports* | Expect little or no data on test businesses. Keep the mock as a fallback. |
| `calendar_special_days.csv` | Nager.Date API (`date.nager.at/api/v3/PublicHolidays/{year}/{FI,SE,NO}`) or the Python package `holidays` | Public holidays only: add eves, observances and commercial days yourself. |
| `school_breaks.csv` | Municipal school-calendar pages (e.g. city websites, Skolverket links, kommune sites) | No common Nordic API. Real dates differ by municipality. |
| `local_events.json` | Helsinki **LinkedEvents** (`api.hel.fi/linkedevents/v1/`, CC BY 4.0) | Helsinki region only. The JSON-LD shape is close to our file. |
| `weather_daily.csv` | FMI open data (`opendata.fmi.fi`), SMHI open data (`opendata.smhi.se`), MET Norway Locationforecast (`api.met.no`) | MET Norway requires an identifying `User-Agent` header. |
| `cities.csv`, business details | Open business registers: PRH / YTJ (`avoindata.prh.fi`), Brønnøysund (`data.brreg.no`) | Registry data has addresses and industry codes, not opening hours. |
| Shopping-centre hours in `entities.json` | The centres' own websites | Usually published 4–8 weeks before Christmas. |

Check each source's terms of use. No personal data. Keep keys out of your repository.
