"""Owner messages. Facts (dates, hours, reasons) come only from the engine; templates only arrange them.

build_message(...) returns the text for every channel plus the structured items the decide page shows.
An optional LLM pass may reword the intro sentence, but never the hours lines (see llm_polish).
"""
from __future__ import annotations

from datetime import date

WD = {"fi": ["maanantaina", "tiistaina", "keskiviikkona", "torstaina", "perjantaina", "lauantaina", "sunnuntaina"],
      "sv": ["måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"],
      "nb": ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"],
      "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]}

T = {
    "en": {
        "autoN": "As you asked, we updated {n} holiday hours automatically:",
        "hi": "Hi {name}!", "closed": "closed", "open": "open {h}",
        "LAST_YEAR": "Last year you were {last} that day, but no special hours are set for this year.",
        "TWO_YEARS_AGO": "In {year} you were {last} that day, and no special hours are set for this year.",
        "SHOPPING_CENTRE": "{mall} is {mall_h} that day, but no special hours are set for you.",
        "PEERS_LEARNED": "Most businesses like yours nearby are {state} that day, and no special hours are set for you.",
        "shows": "So Google now shows {shown}.",
        "one": "{day} is on {wd} {dm}.",
        "sug1": "We suggest: {dm} {sug}",
        "many": "{n} upcoming holidays may show the wrong opening hours on Google:",
        "line": "{day} {dm}: Google shows {shown} → suggest {sug}",
        "cta": "Approve, suggest other hours or say no thanks (no login): {link}",
        "subject1": "{day}: are your opening hours right?",
        "subjectN": "{n} holidays: check your opening hours",
        "auto": "As you asked, we updated your holiday hours automatically: {day} {dm} {sug}. Want it changed? {link}",
        "done": "Done! Your new hours are being published.",
    },
    "fi": {
        "autoN": "Kuten sovittiin, päivitimme {n} poikkeusaukioloa automaattisesti:",
        "hi": "Hei {name}!", "closed": "kiinni", "open": "auki klo {h}",
        "LAST_YEAR": "Viime vuonna olitte {last}, mutta tälle vuodelle poikkeusaikoja ei ole vielä merkitty.",
        "TWO_YEARS_AGO": "Vuonna {year} olitte {last}, eikä tälle vuodelle ole merkitty poikkeusaikoja.",
        "SHOPPING_CENTRE": "{mall} on silloin {mall_h}, mutta teille ei ole merkitty poikkeusaikoja.",
        "PEERS_LEARNED": "Useimmat vastaavat yritykset alueellanne ovat silloin {state}, eikä teille ole merkitty poikkeusaikoja.",
        "shows": "Siksi Google näyttää nyt: {shown}.",
        "one": "{day} on {wd} {dm}",
        "sug1": "Ehdotamme: {dm} {sug}",
        "many": "{n} tulevan pyhäpäivän aukioloajat voivat näkyä Googlessa väärin:",
        "line": "{day} {dm}: Google näyttää {shown} → ehdotus {sug}",
        "cta": "Hyväksy, ehdota muuta tai ohita (ei kirjautumista): {link}",
        "subject1": "{day}: ovatko aukioloaikanne oikein?",
        "subjectN": "{n} pyhäpäivää: tarkista aukioloaikasi",
        "auto": "Kuten sovittiin, päivitimme poikkeusaukiolon automaattisesti: {day} {dm} {sug}. Muutetaanko? {link}",
        "done": "Valmis! Uudet aukioloajat julkaistaan.",
    },
    "sv": {
        "autoN": "Som överenskommet uppdaterade vi {n} helgtider automatiskt:",
        "hi": "Hej {name}!", "closed": "stängt", "open": "öppet {h}",
        "LAST_YEAR": "Förra året hade ni {last}, men inga avvikande tider är inlagda i år.",
        "TWO_YEARS_AGO": "År {year} hade ni {last}, och inga avvikande tider är inlagda i år.",
        "SHOPPING_CENTRE": "{mall} har då {mall_h}, men inga avvikande tider är inlagda för er.",
        "PEERS_LEARNED": "De flesta liknande företag i området har {state} då, och inga avvikande tider är inlagda för er.",
        "shows": "Därför visar Google nu: {shown}.",
        "one": "{day} infaller {wd} {dm}.",
        "sug1": "Vi föreslår: {dm} {sug}",
        "many": "{n} kommande helgdagar kan visa fel öppettider på Google:",
        "line": "{day} {dm}: Google visar {shown} → förslag {sug}",
        "cta": "Godkänn, föreslå annat eller tacka nej (ingen inloggning): {link}",
        "subject1": "{day}: stämmer era öppettider?",
        "subjectN": "{n} helgdagar: kolla era öppettider",
        "auto": "Som överenskommet uppdaterade vi era helgtider automatiskt: {day} {dm} {sug}. Vill ni ändra? {link}",
        "done": "Klart! De nya tiderna publiceras.",
    },
    "nb": {
        "autoN": "Som avtalt oppdaterte vi {n} helligdagstider automatisk:",
        "hi": "Hei {name}!", "closed": "stengt", "open": "åpent {h}",
        "LAST_YEAR": "I fjor hadde dere {last}, men ingen avvikende åpningstider er lagt inn i år.",
        "TWO_YEARS_AGO": "I {year} hadde dere {last}, og ingen avvikende tider er lagt inn i år.",
        "SHOPPING_CENTRE": "{mall} har da {mall_h}, men ingen avvikende tider er lagt inn for dere.",
        "PEERS_LEARNED": "De fleste lignende bedrifter i området har {state} da, og ingen avvikende tider er lagt inn for dere.",
        "shows": "Derfor viser Google nå: {shown}.",
        "one": "{day} er {wd} {dm}",
        "sug1": "Vi foreslår: {dm} {sug}",
        "many": "{n} kommende helligdager kan vise feil åpningstider på Google:",
        "line": "{day} {dm}: Google viser {shown} → forslag {sug}",
        "cta": "Godkjenn, foreslå annet eller si nei takk (ingen innlogging): {link}",
        "subject1": "{day}: stemmer åpningstidene?",
        "subjectN": "{n} helligdager: sjekk åpningstidene",
        "auto": "Som avtalt oppdaterte vi helligdagstidene automatisk: {day} {dm} {sug}. Vil dere endre? {link}",
        "done": "Ferdig! De nye tidene publiseres.",
    },
}


SIGN = {"en": "— Visor, for Fonecta Connect", "fi": "— Visor, Fonecta Connect", "sv": "— Visor, Hitta Connect", "nb": "— Visor, Connect"}


def lang_of(lang: str) -> str:
    return lang if lang in T else "en"


def nice(h: str) -> str:
    def t(x):
        hh, mm = x.split(":")
        return str(int(hh)) + ("" if mm == "00" else "." + mm)
    return ", ".join("–".join(t(x) for x in iv.split("-")) for iv in h.split(","))


def state(h: str, lang: str) -> str:
    t = T[lang]
    return t["closed"] if h == "closed" else t["open"].format(h=nice(h))


MON_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def dm(d: date, lang: str) -> str:
    if lang == "en":
        return f"{d.day} {MON_EN[d.month - 1]}"
    return f"{d.day}/{d.month}" if lang == "sv" else f"{d.day}.{d.month}."


def reason(item: dict, lang: str) -> str:
    t, b, ev = T[lang], item.get("basis"), item.get("evidence")
    if b in ("LAST_YEAR", "TWO_YEARS_AGO"):
        last = item["suggested"] if ev[1] == "REGULAR" else ev[1]
        return t[b].format(last=state(last, lang), year=ev[0][:4])
    if b == "SHOPPING_CENTRE":
        return t[b].format(mall=ev, mall_h=state(item["suggested"], lang))
    if b == "PEERS_LEARNED":
        return t[b].format(state=state(item["suggested"], lang))
    return ""


def build_message(lang: str, name: str, items: list[dict], link: str, auto_applied: bool = False) -> dict:
    """items: [{date (date), day_name, shown, suggested, basis, evidence}] sorted by date."""
    lang = lang_of(lang)
    t = T[lang]
    for it in items:
        it["reason"] = reason(it, lang)
        it["shown_text"] = state(it["shown"], lang)
        it["suggested_text"] = state(it["suggested"], lang)
        it["date_text"] = dm(it["date"], lang)
    first = items[0]
    if auto_applied and len(items) > 1:
        lines = [t["hi"].format(name=name), t["autoN"].format(n=len(items))]
        lines += [f"• {i['day_name']} {i['date_text']}: {i['suggested_text']}" for i in items]
        lines.append(t["cta"].format(link=link))
        return {"lang": lang, "subject": t["subjectN"].format(n=len(items)), "text": "\n".join(lines),
                "sms": f"{lines[0]} {lines[1]} {lines[-1]}"}
    if auto_applied:
        body = t["auto"].format(day=first["day_name"], dm=first["date_text"], sug=first["suggested_text"], link=link)
        return {"lang": lang, "subject": t["subject1"].format(day=first["day_name"]),
                "text": f"{t['hi'].format(name=name)}\n{body}", "sms": body}
    if len(items) == 1:
        intro = (f"{t['one'].format(day=first['day_name'], wd=WD[lang][first['date'].weekday()], dm=first['date_text'])} "
                 f"{first['reason']} {t['shows'].format(shown=first['shown_text'])}")
        lines = [t["hi"].format(name=name), intro, t["sug1"].format(dm=first["date_text"], sug=first["suggested_text"]),
                 t["cta"].format(link=link)]
        subject = t["subject1"].format(day=first["day_name"])
    else:
        lines = [t["hi"].format(name=name), t["many"].format(n=len(items))]
        lines += ["• " + t["line"].format(day=i["day_name"], dm=i["date_text"], shown=i["shown_text"],
                                          sug=i["suggested_text"]) for i in items]
        lines.append(t["cta"].format(link=link))
        subject = t["subjectN"].format(n=len(items))
    lines.append(SIGN[lang])
    text = "\n".join(lines)
    sms = "\n".join(lines[:-1]) if len(items) == 1 else None
    sms = sms if len(items) == 1 else f"{t['hi'].format(name=name)} {t['many'].format(n=len(items)).rstrip(':')}. {t['cta'].format(link=link)}"
    return {"lang": lang, "subject": subject, "text": text, "sms": sms}
