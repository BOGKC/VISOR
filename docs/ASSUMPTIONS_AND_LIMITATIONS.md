# Assumptions and limitations

**Synthetic by design.** No Fonecta, Yext, customer or market data was used or calibrated against. Business names, addresses, reviews, owners and numbers are generated. Any resemblance to a real business is coincidental.

**What is real**
- Public-holiday calendars for FI, SE and NO (checked against the open-source `holidays` package), plus the usual eves, observances and commercial days.
- City names and approximate coordinates.
- Yext API shapes for entities, hours, holiday hours, reviews, publisher suggestions and analytics metric names (from docs.yext.com). Listings output is simplified.

**What is modelled**
- Each business has a hidden habit per holiday (closed, shorter, longer, regular, follows the shopping centre, snow-dependent, seasonal), repeated from year to year with some change, and correlated across holidays and with business type and country.
- Owners differ in how often and how early they enter exceptions, how quickly they reply, and which channel works.
- Wrong listings produce weak signals: complaint reviews, Google user edits, extra phone calls in analytics. Noise is included on purpose: wrong user edits, misleading reviews, data gaps.
- About 6% of businesses changed their regular hours (half never updated the listing); about 1.5% closed for good.

**Approximations**
- School breaks are country-level approximations; real dates vary by municipality.
- Events (arena nights, Christmas markets, light festivals) and weather are synthetic but plausible.
- Publisher IDs for Nordic directories and AI assistants are labels for the simulator, not Yext IDs.
- Norway is treated as a pilot market (Connect is launching there).
- Only opening hours are modelled. Other suggestion types (seasonal closure, outdated regular hours, closed-for-good) appear as signals and in the labels, not as scored targets.

**Not provided**
- No message delivery (e-mail/SMS/WhatsApp) – build or mock your own.
- The owner simulator is a statistical stand-in, not real customer behaviour.
