# UCI Events Pipeline - Restructured Project

## Directory Structure

```
Assignment2-ai_innovation/
├── src/                    # Source code
│   ├── crawlers/           # Data crawlers
│   │   ├── zotspot_crawler.py      # Main ZotSpot events crawler (polite, resumable)
│   │   ├── club_crawler.py         # Club directory API crawler (experimental)
│   │   ├── extract_clubs_from_html.py  # Extract 1010 clubs from HTML
│   │   └── extract_auth.py         # Browser auth extractor helper
│   ├── enrichers/          # Data enrichment
│   │   └── instagram_enricher.py   # Instagram enrichment (experimental)
│   └── pipeline/           # Unified pipeline
│       ├── unified_pipeline.py     # Original pipeline
│       └── unified_pipeline_final.py  # Complete pipeline with deduplication
├── data/                   # Data files (gitignored large files)
│   ├── clubs/              # Club data
│   │   ├── zotspot_clubs_from_html.json      # 1010 clubs from HTML
│   │   ├── club_instagram_handles_from_html.json  # Instagram handles
│   │   └── club_instagram_handles.json       # Manual handles
│   ├── output/             # Crawler outputs
│   │   ├── unified_events.json      # 295 deduplicated events (main output)
│   │   ├── events.json              # Raw ZotSpot events
│   │   └── test_events.json         # Test outputs
│   └── raw/                # Raw source files
│       └── zotspot.uci.edu.html         # Saved HTML page
├── docs/                   # Documentation
│   └── README.md           # This file
├── scripts/                # Utility/analysis scripts
│   ├── browser_auth_extractor.js      # Run in browser console
│   ├── analyze_*.py                   # API analysis scripts
│   └── test_*.py                      # API test scripts
├── tests/                  # Test files (empty)
├── requirements.txt        # Python dependencies
└── .gitignore              # Protects sensitive data
```

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the Unified Pipeline (Recommended)
```bash
# From project root
python3 src/pipeline/unified_pipeline_final.py --output data/output/unified_events.json
```
This fetches ZotSpot events (383), deduplicates to 295 unique events, and saves to `data/output/unified_events.json`.

### 3. Just ZotSpot Events
```bash
# All events (upcoming + past)
python3 src/crawlers/zotspot_crawler.py --all-events --output data/output/events.json --resume data/output/crawl_progress.json

# Quick test (1 page)
python3 src/crawlers/zotspot_crawler.py --max-pages 1 --output data/output/test.json
```

### 4. Extract Clubs from HTML
```bash
python3 src/crawlers/extract_clubs_from_html.py
```
Outputs to `data/clubs/zotspot_clubs_from_html.json` (1010 clubs) and `data/clubs/club_instagram_handles_from_html.json`.

### 5. Get Authentication (Optional)
```bash
# 1. Go to https://zotspot.uci.edu/events in browser (logged in)
# 2. F12 → Console → Paste scripts/browser_auth_extractor.js → Enter
# 3. Copy JSON output → Save as auth.json
# 4. Run: python3 src/crawlers/extract_auth.py auth.json
# 5. Use with crawler: python3 src/crawlers/zotspot_crawler.py --cookies auth_crawler.json
```

## Key Features

| Feature | Implementation |
|---------|----------------|
| **Polite crawling** | 2s delay, exponential backoff, jitter, retry logic |
| **Resume capability** | `--resume` survives interrupts |
| **Pagination** | Matches webpage (limit=40, range increments by 40) |
| **All events** | `--all-events` omits filter1 for past+upcoming |
| **Deduplication** | Exact key + fuzzy matching (title + date + organizer) |
| **Club enrichment** | 1010 clubs from HTML dropdown |

## Output Format (unified_events.json)

```json
{
  "id": "1948699",
  "source": "zotspot",
  "source_url": "https://zotspot.uci.edu/rsvp_boot?id=1948699",
  "title": "Anime Club Weekly Group Watch",
  "description": "Welcome to the Anime Club...",
  "start_datetime": "2026-10-01T19:00:00",
  "end_datetime": null,
  "timezone": "America/Los_Angeles",
  "location": "SSPA 1100",
  "location_type": "physical",
  "organizer_name": "Cal Animage Epsilon",
  "organizer_id": "33476",
  "organizer_type": "club",
  "organizer_url": "https://zotspot.uci.edu/group/animeclubcae",
  "categories": ["Social"],
  "tags": ["Social", "Media", "Movie", "Anime"],
  "audience": "students",
  "image_url": "https://zotspot.uci.edu/upload/...",
  "flyer_url": "https://zotspot.uci.edu/upload/...",
  "rsvp_required": true,
  "rsvp_url": "https://zotspot.uci.edu/rsvp_boot?id=1948699",
  "cost": "FREE",
  "raw_data": { ... }
}
```

## Data Sources

| Source | Status | Events |
|--------|--------|--------|
| ZotSpot (CampusGroups) | ✅ Working | 383 → 295 deduped |
| UCI Department ICS calendars | ⚠️ Mostly 404/403 | 0 |
| Club directory | ✅ Extracted | 1010 clubs |

## Requirements

```
requests>=2.31.0
instaloader>=4.10.0
icalendar>=7.3.0
beautifulsoup4>=4.15.0
python-dateutil>=2.8.2
```

## Legal/Ethical

- For educational/research use only
- Respect ZotSpot's Terms of Service
- Default 2s delay is polite to servers
- Delete auth files after use
- Don't redistribute private event data