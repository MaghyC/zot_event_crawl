# ZotSpot Events Crawler

A polite, authenticated crawler for ZotSpot (UC Irvine's CampusGroups platform) events.

## What This Is For

This tool **downloads all events from ZotSpot** (https://zotspot.uci.edu/events) and saves them as a structured JSON file. Use it for:

- **Research/Analysis** - Study campus event patterns, club activity, attendance trends
- **Personal Calendar** - Import events into your calendar app
- **Club Management** - Track other clubs' events for collaboration
- **Data Journalism** - Analyze campus life data
- **Archive** - Preserve event history before it's removed

## Quick Start (3 Steps)

### Step 1: Open Terminal in Project Folder

**macOS/Linux:**
```bash
cd ~/Downloads/Assignment2-ai_innovation
```

**Windows (PowerShell):**
```powershell
cd C:\Users\YourName\Downloads\Assignment2-ai_innovation
```

**VS Code:** Open the folder `Assignment2-ai_innovation` → Terminal → New Terminal

### Step 2: Install Requirements (One Time)

```bash
pip install requests
```

### Step 3: Run the Crawler

**Option A: Get ALL events (recommended - gets past + upcoming)**
```bash
python3 zotspot_crawler.py --all-events --output events.json --resume crawl_progress.json
```

**Option B: Match exactly what you see on the webpage**
```bash
python3 zotspot_crawler.py --web-filters --output events.json --resume crawl_progress.json
```

**Option C: Quick test (first page only)**
```bash
python3 zotspot_crawler.py --max-pages 1 --output test.json
```

## Understanding the Command

| Part | Meaning |
|------|---------|
| `python3 zotspot_crawler.py` | Runs the crawler script |
| `--all-events` | **Include past events** (default is upcoming only) |
| `--web-filters` | Use same filters as the website (filter4_contains=OR) |
| `--output events.json` | **Save results to this file** |
| `--resume crawl_progress.json` | **Survives interruptions** - saves progress each page |

## What Happens When You Run It

```
2026-11-10 20:43:56,395 - INFO - Fetching page (range=0, limit=40)
2026-11-10 20:43:57,264 - INFO - Page 1: Got 34 events (total: 34/430)
2026-11-10 20:43:57,285 - INFO - Fetching page (range=40, limit=40)
2026-11-10 20:43:58,587 - INFO - Page 2: Got 31 events (total: 65/430)
...
2026-11-10 20:44:18,307 - INFO - No more events found
2026-11-10 20:44:18,465 - INFO - Saved 383 events to events.json

Crawled 383 events
  - Sad Girls Club at UCI (...) - Womxn's Center for Success
    URL: https://zotspot.uci.edu/rsvp_boot?id=1063256
  ...
```

- **Shows progress** page by page
- **Saves automatically** to `events.json`
- **Resumes if interrupted** (Ctrl+C, network error) - just run same command again!

## Where Is the Output?

**File: `events.json`** in the same folder where you ran the command.

```bash
ls -la events.json
# -rw-r--r--  1 user  staff  1234567 Nov 10 20:44 events.json
```

## What the Output Means

Open `events.json` - it's a **JSON array** of event objects:

```json
[
  {
    "id": "1948699",
    "title": "Anime Club Weekly Group Watch",
    "description": "Welcome to the Anime Club @ UCI! ...",
    "start_date": "<p>Thu, Oct 1, 2026 7:00 PM – </p><p>Thu, Jun 3, 2027 10:00 PM</p>",
    "end_date": "",
    "location": "SSPA 1100",
    "group_name": "Cal Animage Epsilon",
    "group_id": "33476",
    "category": "Social",
    "url": "https://zotspot.uci.edu/rsvp_boot?id=1948699",
    "image_url": "https://zotspot.uci.edu/upload/uci/2026/...png",
    "rsvp_required": true,
    "raw_data": {
      "_parsed": {
        "event_url": "https://zotspot.uci.edu/rsvp_boot?id=1948699",
        "event_url_logo": "https://zotspot.uci.edu/rsvp_boot?id=1948699&rel=logo",
        "decoded_uid": "uci:Event:1948699",
        "club_login": "animeclubcae",
        "event_price": "FREE",
        "timezone": "PDT (GMT-7)"
      }
    }
  },
  ...
]
```

### Field Meanings

| Field | What It Is |
|-------|------------|
| `id` | ZotSpot event ID (use for detail page URL) |
| `title` | Event name |
| `description` | Full description (HTML format from ZotSpot) |
| `start_date` | Start date/time (HTML format, includes timezone) |
| `end_date` | End date/time (usually empty, included in start_date) |
| `location` | Venue (may say "Private Location (sign in to display)") |
| `group_name` | Club/organization name |
| `group_id` | Club ID (use with `--filter-group`) |
| `category` | Event type (Social, Meeting, Workshop, etc.) |
| `url` | **Direct link to event page** on ZotSpot |
| `image_url` | Event banner/logo image |
| `rsvp_required` | True if "Register" button shown |
| `raw_data._parsed.decoded_uid` | CampusGroups internal ID (`uci:Event:1948699`) |
| `raw_data._parsed.club_login` | Club's URL slug (`animeclubcae`) |

## How to Use the Output

### View in Terminal
```bash
# Pretty print first 3 events
python3 -c "
import json
with open('events.json') as f: events = json.load(f)
for e in events[:3]:
    print(f'{e[\"title\"]} | {e[\"group_name\"]} | {e[\"start_date\"][:50]}...')
    print(f'  → {e[\"url\"]}')
    print()
"
```

### Convert to CSV (for Excel)
```bash
python3 -c "
import json, csv
with open('events.json') as f: events = json.load(f)
with open('events.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['Title', 'Group', 'Category', 'Start Date', 'Location', 'URL', 'RSVP Required'])
    for e in events:
        w.writerow([e['title'], e['group_name'], e['category'], e['start_date'], e['location'], e['url'], e['rsvp_required']])
print('Saved to events.csv')
"
```

### Filter by Club
```bash
# Find all events by a specific club (e.g., DNA+ group_id=71416)
python3 -c "
import json
with open('events.json') as f: events = json.load(f)
dna = [e for e in events if e['group_id'] == '71416']
for e in dna:
    print(f'{e[\"title\"]} - {e[\"start_date\"]}')
"
```

### Find Events Needing Auth
```bash
python3 -c "
import json
with open('events.json') as f: events = json.load(f)
private = [e for e in events if 'private' in e['location'].lower() or 'sign in' in e['location'].lower()]
print(f'Events with private locations: {len(private)}')
for e in private[:5]:
    print(f'  - {e[\"title\"]}: {e[\"location\"]}')
"
```

## If Crawl Gets Interrupted

**Just run the exact same command again!**

```bash
# This resumes from where it left off
python3 zotspot_crawler.py --all-events --output events.json --resume crawl_progress.json
```

The `--resume` file:
- Saves progress after **each page**
- Stores events collected so far
- Auto-deletes when crawl completes successfully

## Authentication (Optional)

The **events list is public** - you don't need login for basic data.

Only needed for:
- Exact private locations ("Private Location (sign in to display)")
- RSVP status (whether YOU are registered)
- User-specific filters ("My Upcoming Events")

**If you need auth:**
1. Go to https://zotspot.uci.edu/events in browser (logged in)
2. F12 → Console → Paste `browser_auth_extractor.js` → Enter
3. Copy JSON output → Save as `auth.json`
4. Run: `python3 extract_auth.py auth.json`
5. Crawl with: `python3 zotspot_crawler.py --cookies auth_crawler.json --all-events --output events.json`

## Common Commands Cheat Sheet

```bash
# All events, resume on interrupt (BEST)
python3 zotspot_crawler.py --all-events --output events.json --resume crawl_progress.json

# Quick test (1 page)
python3 zotspot_crawler.py --max-pages 1 --output test.json

# Only upcoming (faster, default)
python3 zotspot_crawler.py --output upcoming.json

# Match webpage exactly
python3 zotspot_crawler.py --web-filters --output web_events.json

# Filter by club (DNA+ = 71416)
python3 zotspot_crawler.py --filter-group 71416 --output dna_events.json

# Search for workshops
python3 zotspot_crawler.py --search "workshop" --output workshops.json

# With detail pages for first 5 events (SLOW)
python3 zotspot_crawler.py --all-events --fetch-details 5 --output detailed.json

# Slower, more polite (3 second delay)
python3 zotspot_crawler.py --all-events --delay 3.0 --output events.json
```

## Files in This Project

| File | Purpose |
|------|---------|
| `zotspot_crawler.py` | **Main crawler** - run this |
| `extract_auth.py` | Converts browser auth to crawler format |
| `browser_auth_extractor.js` | **Run in browser console** to get auth tokens |
| `requirements.txt` | Python dependencies (`requests`) |
| `.gitignore` | Protects auth files, outputs, progress files |
| `README.md` | This file |

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError: requests` | Run `pip install requests` |
| `Permission denied` | Use `python3` not `python` on macOS/Linux |
| Crawl stops at 42 events | Use `--all-events` flag |
| Network error / timeout | Use `--resume crawl_progress.json` and re-run |
| Want more events | Increase `--max-pages 20` |
| Output too large | Use `--max-pages 5` for testing |

## Legal/Ethical

- **For educational/research use only**
- Respect ZotSpot's Terms of Service
- Don't overload the server (default 2s delay is polite)
- Delete auth files after use
- Don't redistribute private event data

## License

MIT License - Use responsibly for research/education.