#!/usr/bin/env python3
"""Weekly updater for fortbildungen.json (German training offers: congresses, courses, webinars).

Same method and safeguards as update_events.py: download each page in sources_fortbildungen.json, let Claude extract
the offers, validate strictly, merge. An entry is only accepted if its URL is on an allowed official domain, dates are
plausible (future, at most 14 days long, within 3 years) and the format comes from the fixed list. Entries are never
deleted because a page failed to load; they expire 30 days after they end. Undated ongoing offers are kept.
CME points are deliberately NOT extracted: they are set by the organiser and the Aerztekammer.
"""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from update_events import fetch_text, parse_json_array, parse_day, host_ok, slugify  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "fortbildungen.json")
SOURCES_PATH = os.path.join(ROOT, "sources_fortbildungen.json")
MODEL = os.environ.get("EVENTS_MODEL", "claude-haiku-5-5")
FORMATS = ["Congress", "Course", "Online", "On demand", "Exam"]

PROMPT = """You extract continuing-education offers for physicians (Fortbildungen) from a German web page.
Page URL: {url}
Organiser (use this unless the page names a different organising body for that offer): {organizer}
Today: {today}

Return ONLY a JSON array, one object per upcoming congress, course, webinar or exam listed on the page, with exactly these keys:
id (lowercase-hyphen slug of the title), title, organizer, city (string, "" if online or unknown),
format (one of {formats}), start (YYYY-MM-DD or null), end (YYYY-MM-DD or null),
note (string or null; only when there are no exact dates), summary (one factual English sentence, max 30 words),
url (absolute URL of that offer taken from the page; the page URL if there is no specific link).

Rules: use only facts stated on the page. Never guess dates; if unclear set start and end to null.
Do not mention CME points. Skip offers that ended before today. Output nothing except the JSON array.

PAGE TEXT:
{text}
"""


def validate(it, allowed, today):
    try:
        title = str(it["title"]).strip()
        organizer = str(it["organizer"]).strip()
        url = str(it["url"]).strip()
        if not title or len(title) > 140 or not organizer or not host_ok(url, allowed):
            return None
        fmt = it.get("format")
        if fmt not in FORMATS:
            return None
        start, end = parse_day(it.get("start")), parse_day(it.get("end"))
        if start and not end:
            end = start
        if end and not start:
            return None
        note = None
        if start:
            if start > end or (end - start).days > 14:
                return None
            if end < today or start > today + dt.timedelta(days=3 * 365):
                return None
        else:
            note = str(it.get("note") or "See website for dates")[:120]
        return {
            "id": slugify(title),
            "title": title,
            "organizer": organizer,
            "city": str(it.get("city") or "")[:80],
            "format": fmt,
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
            "note": note,
            "summary": str(it.get("summary") or "")[:300],
            "url": url,
        }
    except (KeyError, ValueError, TypeError):
        return None


def merge(existing, fresh, today, log):
    result = list(existing)
    for f in fresh:
        for i, e in enumerate(result):
            if e["id"] == f["id"]:
                if e["start"] and not f["start"]:
                    break  # an undated entry never overwrites one that has dates
                if e != f:
                    log.append(f"CHANGED {f['title']}: {e['start']}..{e['end']} -> {f['start']}..{f['end']}")
                result[i] = f
                break
        else:
            result.append(f)
            log.append(f"NEW {f['title']} ({f['start']}..{f['end']})")
    cutoff = today - dt.timedelta(days=30)
    kept = []
    for e in result:
        last = parse_day(e["end"] or e["start"])
        if last and last < cutoff:
            log.append(f"EXPIRED {e['title']}")
        else:
            kept.append(e)
    kept.sort(key=lambda e: (e["start"] is None, e["start"] or "", e["title"]))
    return kept


def main():
    import anthropic
    client = anthropic.Anthropic()
    today = dt.date.today()
    feed = json.load(open(PATH, encoding="utf-8")) if os.path.exists(PATH) else {"items": []}
    existing = feed.get("items", [])
    sources = json.load(open(SOURCES_PATH, encoding="utf-8"))

    fresh, log = [], []
    for src in sources:
        try:
            text = fetch_text(src["url"])
            if len(text) < 200:
                log.append(f"SKIP {src['name']}: page has too little text (probably needs JavaScript)")
                continue
            msg = client.messages.create(
                model=MODEL, max_tokens=16000,
                messages=[{"role": "user", "content": PROMPT.format(
                    url=src["url"], organizer=src["organizer"], today=today.isoformat(),
                    formats=FORMATS, text=text)}])
            raw = parse_json_array("".join(b.text for b in msg.content if b.type == "text"))
            ok = [v for v in (validate(e, src["allowed_domains"], today) for e in raw) if v]
            log.append(f"OK {src['name']}: {len(ok)} of {len(raw)} offers accepted")
            fresh += ok
        except Exception as exc:
            log.append(f"ERROR {src['name']}: {exc}")

    print("\n".join(log))
    if not fresh:
        print("No valid offers found; fortbildungen.json left unchanged.")
        return 0
    merged = merge(existing, fresh, today, log)
    if merged != existing:
        with open(PATH, "w", encoding="utf-8") as f:
            json.dump({"updated": today.isoformat(), "items": merged}, f, ensure_ascii=False, indent=2)
            f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
