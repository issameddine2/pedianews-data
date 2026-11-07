#!/usr/bin/env python3
"""Weekly updater for events.json.

For every page in sources.json: download it, let Claude extract the congresses it lists,
validate each entry strictly, merge into events.json. Nothing is accepted unless:
  - the event URL is on one of the source's allowed official domains,
  - dates are plausible (future, max 14 days long, within 3 years),
  - topics and region come from the fixed lists the app understands.
Events are never deleted just because a page failed to load; they expire after they end.
"""
import datetime as dt
import json
import os
import re
import sys
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVENTS_PATH = os.path.join(ROOT, "events.json")
SOURCES_PATH = os.path.join(ROOT, "sources.json")
MODEL = os.environ.get("EVENTS_MODEL", "claude-haiku-5-5")

TOPICS = ["Neonatology", "Infection & Vaccines", "Neurodevelopment", "Respiratory & Allergy", "Nutrition & Endocrine", "Mental Health", "Heart & Oncology"]
REGIONS = ["Americas", "Europe", "Japan", "Korea", "China", "Rest of Asia", "Middle East & Africa", "Oceania"]

PROMPT = """You extract paediatrics congress data from a web page.
Page URL: {url}
Organiser: {organizer}
Today: {today}

Return ONLY a JSON array, one object per upcoming congress or meeting listed on the page, with exactly these keys:
id (lowercase-hyphen slug of the name), name, organizer, city (string, "" if unknown),
region (one of {regions}), start (YYYY-MM-DD or null), end (YYYY-MM-DD or null),
timingNote (string or null; only when there are no exact dates), summary (one factual English sentence, max 30 words),
topics (array, values only from {topics}; use all seven for general paediatrics congresses),
url (absolute URL of that event taken from the page; the page URL if there is no specific link).

Rules: use only facts stated on the page. Never guess dates; if unclear set start and end to null.
Skip events that ended before today. Output nothing except the JSON array.

PAGE TEXT:
{text}
"""


class TextExtractor(HTMLParser):
    def __init__(self, base):
        super().__init__()
        self.base, self.parts, self.skip, self.href = base, [], 0, None

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        if tag == "a":
            href = dict(attrs).get("href")
            self.href = urljoin(self.base, href) if href else None

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.skip:
            self.skip -= 1
        if tag == "a" and self.href:
            self.parts.append(f" [{self.href}] ")
            self.href = None

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(data.strip())


def fetch_text(url, limit=60000):
    req = Request(url, headers={"User-Agent": "PediaNewsEventsBot/1.0 (+personal project)"})
    with urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", errors="replace")
    ex = TextExtractor(url)
    ex.feed(html)
    return re.sub(r"\s+", " ", " ".join(ex.parts))[:limit]


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def parse_json_array(text):
    a, b = text.find("["), text.rfind("]")
    if a < 0 or b < a:
        raise ValueError("no JSON array in model output")
    return json.loads(text[a:b + 1])


def parse_day(s):
    return dt.date.fromisoformat(s) if s else None


def host_ok(url, allowed):
    p = urlparse(url)
    host = (p.hostname or "").lower().removeprefix("www.")
    return p.scheme == "https" and any(host == d or host.endswith("." + d) for d in allowed)


def validate(ev, allowed, today):
    """Return a clean event dict or None."""
    try:
        name = str(ev["name"]).strip()
        organizer = str(ev["organizer"]).strip()
        url = str(ev["url"]).strip()
        if not name or len(name) > 120 or not organizer or not host_ok(url, allowed):
            return None
        region = ev.get("region")
        if region not in REGIONS:
            return None
        start, end = parse_day(ev.get("start")), parse_day(ev.get("end"))
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
            note = str(ev.get("timingNote") or "Check website")[:120]
        topics = [t for t in (ev.get("topics") or []) if t in TOPICS]
        return {
            "id": slugify(name),
            "name": name,
            "organizer": organizer,
            "city": str(ev.get("city") or "")[:80],
            "region": region,
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
            "timingNote": note,
            "summary": str(ev.get("summary") or "")[:300],
            "topics": topics,
            "url": url,
        }
    except (KeyError, ValueError, TypeError):
        return None


def norm_url(u):
    return u.lower().removeprefix("https://").removeprefix("www.").rstrip("/")


def same_event(a, b):
    return a["id"] == b["id"] or (
        a["start"] and a["start"] == b["start"] and norm_url(a["url"]) == norm_url(b["url"]))


def merge(existing, fresh, today, log):
    result = list(existing)
    for f in fresh:
        for i, e in enumerate(result):
            if same_event(e, f):
                # an undated fresh entry never overwrites an event that already has dates
                if e["start"] and not f["start"]:
                    break
                if e != f:
                    log.append(f"CHANGED {f['name']}: {e['start']}..{e['end']} -> {f['start']}..{f['end']}")
                result[i] = {**f, "id": e["id"]}
                break
        else:
            result.append(f)
            log.append(f"NEW {f['name']} ({f['start']}..{f['end']})")
    cutoff = today - dt.timedelta(days=30)
    kept = []
    for e in result:
        last = parse_day(e["end"] or e["start"])
        if last and last < cutoff:
            log.append(f"EXPIRED {e['name']}")
        else:
            kept.append(e)
    kept.sort(key=lambda e: (e["start"] is None, e["start"] or "", e["name"]))
    return kept


def main():
    import anthropic  # pip install anthropic; reads ANTHROPIC_API_KEY
    client = anthropic.Anthropic()
    today = dt.date.today()

    feed = json.load(open(EVENTS_PATH, encoding="utf-8")) if os.path.exists(EVENTS_PATH) else {"events": []}
    existing = feed.get("events", [])
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
                    regions=REGIONS, topics=TOPICS, text=text)}])
            raw = parse_json_array("".join(b.text for b in msg.content if b.type == "text"))
            ok = [v for v in (validate(e, src["allowed_domains"], today) for e in raw) if v]
            log.append(f"OK {src['name']}: {len(ok)} of {len(raw)} events accepted")
            fresh += ok
        except Exception as exc:  # one broken source must not stop the others
            log.append(f"ERROR {src['name']}: {exc}")

    if not fresh:
        print("\n".join(log))
        print("No valid events found; events.json left unchanged.")
        return 0

    merged = merge(existing, fresh, today, log)
    if merged != existing:
        feed = {"updated": today.isoformat(), "events": merged}
        with open(EVENTS_PATH, "w", encoding="utf-8") as f:
            json.dump(feed, f, ensure_ascii=False, indent=2)
            f.write("\n")
    print("\n".join(log))
    return 0


if __name__ == "__main__":
    sys.exit(main())
