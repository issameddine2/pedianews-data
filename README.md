# PediaNews event data

`events.json` is the event list the PediaNews app downloads. A weekly GitHub Action
(`.github/workflows/update-events.yml`) reads the official congress pages in `sources.json`,
lets Claude extract the events, validates them, and commits changes to `events.json`.
The app picks up the new file the next time it opens the Events tab. No app update needed.

## One-time setup
1. Create a **public** GitHub repository named `pedianews-data` and upload everything in this folder (keep the folder structure, including `.github/`).
2. Get an Anthropic API key at console.anthropic.com (this is separate from a claude.ai subscription; each weekly run typically costs a few cents).
3. In the repo: Settings > Secrets and variables > Actions > New repository secret. Name `ANTHROPIC_API_KEY`, value your key.
4. Actions tab > "Update events" > Run workflow once, and check the log. Lines starting with OK, NEW, CHANGED or ERROR show what happened.
5. Open `events.json` on GitHub, click "Raw", and copy the URL. Paste it into `EventStore.remoteURLString` in the app (`Events.swift`).

## Safeguards
- Every event URL must be on an official domain listed for that source (`allowed_domains`).
- Dates must be in the future, at most 14 days long and within 3 years; topics and regions must come from the app's fixed lists.
- Nothing is deleted because a page failed to load. Events expire 30 days after they end.
- Every change is a Git commit, so a wrong update can be reverted in one click.

## Known limits
- The extraction is done by an AI model reading web pages, so occasional errors are possible. Check the `CHANGED` / `NEW` lines in the Actions log now and then, especially for dates.
- Pages that need JavaScript to show their content are skipped (logged as SKIP).
- To follow more organisers, add an entry to `sources.json` (name, page URL, organiser, allowed_domains).

## Fortbildungen (training offers)
`fortbildungen.json` works like `events.json`: `scripts/update_fortbildungen.py` reads the pages in
`sources_fortbildungen.json` (DGKJ first), validates the result and commits changes. It runs in the same weekly workflow.
The DGKJ event calendar (dgkj.de/termine/terminkalender, about 15 pages of 10 events) is read page by page; the DGKJ Repetitorien page is read too.
CME points are never extracted because the organiser and the Aerztekammer decide them. In the app, paste the raw URL
of `fortbildungen.json` into `fortbildungenURL` in `Specialty.swift`.
