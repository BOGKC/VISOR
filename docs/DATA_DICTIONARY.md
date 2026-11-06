# Data dictionary

Times are local (Europe/Helsinki, Stockholm, Oslo). Hours strings use one format everywhere:
`closed` · `09:00-17:00` · `10:00-14:00,17:00-22:00` · `18:00-02:00` (past midnight) · `00:00-23:59` (24 h).

## Entities – `data/entities.json`
Yext *Entities: List* shape: `{"meta":…, "response":{"count", "entities":[…]}}`.

| Field | Meaning |
|---|---|
| `meta.id` | Entity ID. `FI-00123` business, `FI-M001` shopping centre, `FI-D0001` demo storyline |
| `meta.countryCode`, `meta.language` | FI / SE / NO; listing language |
| `name`, `address`, `geocodedCoordinate`, `timezone` | Location |
| `categoryIds` | See `categories.csv` |
| `hours.monday … sunday` | Published regular hours (`openIntervals` or `isClosed`) |
| `hours.holidayHours[]` | Exceptions already entered for dates ≥ 6 Nov 2026: `isClosed`, `isRegularHours` or `openIntervals` |
| `hours.reopenDate` | Seasonal businesses that published a winter break |
| `closed` | Published as permanently closed |
| `c_segment` | Business type (33 types + `shopping_centre`) |
| `c_shoppingCenterEntityId` | The shopping centre the business is in |
| `c_entityRole` | `SHOPPING_CENTRE` for centres |
| `c_connectProduct`, `c_connectCustomerSince` | `Fonecta Connect` (FI), `Hitta Connect` (SE), `Connect (NO pilot)` |

Phones, e-mails and websites are fake (`example.com`, invalid numbers).

## History – `holiday_hours_history.jsonl`, `regular_hours_history.jsonl`
One JSON per line.
- Holiday (special days from Jan 2024; first entries were made in Dec 2023): `entity_id`, `date`, `day_key`, `holidayHours` (Yext item), `entered_at`, `source` = `OWNER_UI` · `CONNECT_SUGGESTION` (2025 pilot) · `FONECTA_SUPPORT` · `API_INTEGRATION` (shopping centres). Several rows for one date = later row wins. An entry entered on or after the date did not help that day.
- Regular: `entity_id`, `effective_from` (`before-2024` or date), `hours` (Yext week object).

## Signals
| File | Fields |
|---|---|
| `publisher_suggestions.json` | Yext shape: `id`, `publisherId`, `locationId`, `dateCreated`, `dateResolved`, `fieldName` (`hours`/`closed`), `status` (WAITING_ON_CUSTOMER, ACCEPTED, REJECTED, EXPIRED), `originalContent`, `suggestedContent` (JSON strings). Roughly half are noise. |
| `reviews.json` | Yext shape: `id`, `locationId`, `rating` 1–5, `content` (fi/sv/nb/en, may be empty), `authorName`, `publisherDate` (epoch ms), `publisherId`, `comments[]` (owner replies). |
| `analytics_daily.parquet` | `date`, `entity_id`, `GOOGLE_SEARCH_QUERIES`, `GOOGLE_SEARCH_VIEWS`, `GOOGLE_MAP_VIEWS`, `GOOGLE_CUSTOMER_ACTIONS`, `GOOGLE_PHONE_CALLS`, `PROFILE_VIEWS`. 2024-01-01 → 2026-11-03 (2-day lag). A few short gaps. |
| `listings.json` | `entityId`, `publisherId`, `publisherName`, `status`, `typicalUpdateSpeedSeconds`, `listingUrl`. Publisher IDs are synthetic labels. |
| `peer_benchmarks.csv` | `country`, `city_tier` (capital, large_city, town, ski_resort), `segment`, `day_key`, `n_entity_days`, `share_no_exception_entered`, `share_entered_closed`, `share_entered_special_hours`, `share_entered_regular`, `closed_share_among_entered`, `median_open_special`, `median_close_special`. Seasons 2023–2025, ~9,000 businesses incl. ones not in this file set. Cells < 10 removed. Note: based on what owners *entered*, so it is biased towards diligent owners. |
| `pilot_decision_log_2025.csv` | `suggestion_id`, `message_id` (one message can bundle several dates), `entity_id`, `date`, `day_key`, `displayed_before`, `suggested_hours`, `basis` (LAST_YEAR_EXCEPTION, SHOPPING_CENTRE_HOURS, PEER_MAJORITY), `channel`, `language`, `sent_at`, `decision`, `final_hours`, `decided_at`, `owner_comment`, `standing_permission_granted`. FI only. |
| `customer_contacts.csv` | `preferred_channel` (EMAIL, SMS, WHATSAPP, APP_PUSH), `preferred_language`, `best_contact_window`, `standing_permission_holidays`, `opted_out_of_suggestions`. |

## Context
| File | Fields |
|---|---|
| `calendar_special_days.csv` | `country`, `date`, `weekday`, `day_key`, `day_class`, `day_type` (PUBLIC_HOLIDAY, EVE, OBSERVANCE, COMMERCIAL, BETWEEN_HOLIDAYS), `name_local`, `name_en`, `official_public_holiday` (as in the `holidays` package: FI counts Christmas Eve and Midsummer Eve, SE does not). Real calendars. |
| `school_breaks.csv` | Approximate autumn and Christmas breaks per country (real dates vary by municipality). |
| `local_events.json` | LinkedEvents-like JSON-LD: `name{fi,sv,nb,en}`, `start_time`, `end_time`, `location.position.coordinates [lon,lat]`, `keywords`, `x_expected_attendance`. Synthetic. |
| `weather_daily.csv` | Per city: `tmean_c`, `tmin_c`, `tmax_c`, `precip_mm`, `snow_depth_cm`, `is_forecast` (6–15 Nov 2026 is a noisy forecast). Synthetic. |
| `weather_normals.csv` | Climatology per city and calendar day incl. `p_snow_depth_ge_10cm`. |
| `cities.csv`, `categories.csv`, `splits.csv` | Lookups. `split` = dev / test / demo / reference (shopping centres). |

## Evaluation and labels
| File | Fields |
|---|---|
| `evaluation/targets_2026.csv` | Rows to predict: `entity_id`, `date`, `day_key`, `day_type`, `event_id`, `country`, `split` (dev, test, demo – only test is scored by organisers). Includes arena/festival nights for restaurants and bars within 1 km, and school-break days for family venues and ski rentals. |
| `evaluation/targets_2025_backtest.csv` | Same for 7 Nov 2025 – 6 Jan 2026, dev only, snapshot 6 Nov 2025. |
| `labels/dev_labels_2026.csv`, `dev_labels_2025_backtest.csv` | `truth_hours`, `displayed_hours_at_snapshot`, `needs_action`, `expected_action`, `mismatch_type`, `expected_search_views`. |
| `labels/dev_truth_history.csv` | True hours on every special day 2024 → 5 Nov 2026 for dev businesses (training data). |
| `labels/dev_regular_hours_truth.csv` | True current regular hours, `listing_is_outdated`, `permanently_closed`. |

## day_key values
`XMAS_EVE, XMAS_DAY, BOXING_DAY, DEC23, INTERDAY, NYE, NEW_YEARS_DAY, EPIPHANY_EVE, EPIPHANY, INDEPENDENCE_DAY, FATHERS_DAY, MOTHERS_DAY, LUCIA, BLACK_FRIDAY, ALL_SAINTS, MAUNDY_THURSDAY, GOOD_FRIDAY, EASTER_SATURDAY, EASTER_SUNDAY, EASTER_MONDAY, MAY_EVE, MAY_DAY, ASCENSION, PENTECOST_EVE, PENTECOST, WHIT_MONDAY, NATIONAL_DAY, MIDSUMMER_EVE, MIDSUMMER_DAY, EVENT, SCHOOL_BREAK`
