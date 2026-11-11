# ZotSpot Events Crawler

A polite, authenticated crawler for ZotSpot (UC Irvine's CampusGroups platform) events.

## Features

- **Authenticated API access** - Uses JWT + CSRF tokens from your browser session (optional - API is public!)
- **Polite crawling** - Rate limiting (2s default), exponential backoff, jitter, retry logic
- **Pagination support** - Automatic pagination matching webpage behavior (limit=40)
- **Filtering** - Filter by group, category, search terms, date ranges
- **Safety limits** - Max pages limit (default 15) to prevent accidental overload
- **Resume capability** - Save progress after each page, resume on interrupt

## Quick Start

### 1. Get Authentication Tokens (Optional - API is Public!)

The events list API is publicly accessible. Auth only needed for:
- Private event locations
- RSVP status
- User-specific data

If you need auth:
1. Log into https://zotspot.uci.edu/events in your browser
2. Open DevTools (F12) → Console
3. Paste the contents of `browser_auth_extractor.js` and press Enter
4. **Copy the JSON output** (between `=== COPY FROM HERE ===` and `=== TO HERE ===`)
5. Save as `auth.json`

### 2. Convert Auth Data (if using auth)

```bash
python3 extract_auth.py auth.json
# Creates auth_crawler.json with only needed credentials
```

### 3. Crawl Events

```bash
# Get ALL events (upcoming + past) - RECOMMENDED
python3 zotspot_crawler.py --all-events --output events.json

# Match exact webpage behavior (includes filter4 params)
python3 zotspot_crawler.py --web-filters --output events.json

# Only upcoming events (default, faster)
python3 zotspot_crawler.py --output events.json

# With resume capability (survives interrupts!)
python3 zotspot_crawler.py --all-events --output events.json --resume crawl_progress.json

# Search for specific events
python3 zotspot_crawler.py --search "workshop" --output events.json

# Filter by group (filter2 = group ID, e.g., DNA+ = 71416)
python3 zotspot_crawler.py --filter-group 71416 --output events.json

# With detail pages for first 10 events (slow!)
python3 zotspot_crawler.py --all-events --fetch-details 10 --output events.json

# Custom pagination
python3 zotspot_crawler.py --max-pages 20 --limit 40 --delay 3.0 --output all_events.json
```

### 4. Clean Up

```bash
# DELETE sensitive auth files when done
rm auth.json auth_crawler.json
```

## Command Options

| Option | Description | Default |
|--------|-------------|---------|
| `--cookies` | Path to cookies JSON file (optional) | - |
| `--jwt` | JWT token directly | - |
| `--csrf` | CSRF token directly | - |
| `--output` | Output JSON file | `zotspot_events.json` |
| `--limit` | Events per page | 40 |
| `--max-pages` | Maximum pages to crawl | 15 |
| `--search` | Search query | "" |
| `--filter-group` | Group ID (filter2) | - |
| `--filter-category` | Category ID (filter3) | - |
| `--delay` | Base delay between requests (seconds) | 2.0 |
| `--max-delay` | Max backoff delay (seconds) | 60.0 |
| `--timeout` | Request timeout (seconds) | 30 |
| `--fetch-details [N]` | Fetch detail pages for N events (0=all) | 0 |
| `--all-events` | Include past events (not just upcoming) | False |
| `--web-filters` | Use web-like filters (filter4_contains=OR) | False |
| `--resume FILE` | Resume file path for interrupted crawls | - |

## Output Format

Events are saved as JSON array with this structure:

```json
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
  "image_url": "https://zotspot.uci.edu/upload/uci/2026/...",
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
}
```

## Polite Crawling Details

The crawler implements several politeness measures:

1. **Rate Limiting**: Minimum 2 seconds between requests (configurable)
2. **Jitter**: ±10% random variation to avoid thundering herd
3. **Exponential Backoff**: On 429/5xx errors, waits 2s, 4s, 8s... up to 60s
4. **Retry-After Header**: Respects server's `Retry-After` header if present
5. **Max Pages**: Default 15 page limit prevents accidental deep crawls
6. **Timeouts**: 30 second request timeout (configurable)

## Resume Capability

Use `--resume crawl_progress.json` to survive network interruptions:

```bash
# Start crawl with resume file
python3 zotspot_crawler.py --all-events --output events.json --resume crawl_progress.json

# If interrupted (Ctrl+C, network error), just run the SAME command again
python3 zotspot_crawler.py --all-events --output events.json --resume crawl_progress.json
# Continues from where it left off!
```

The progress file:
- Saves after each page
- Stores events, current page, range_start, total count
- Auto-deletes on successful completion
- Uses atomic writes (tmp file + rename) to prevent corruption

## Security Notes

- **NEVER commit auth files** - They're in `.gitignore`
- Auth files contain session cookies and JWT tokens - treat like passwords
- Delete `auth.json` and `auth_crawler.json` after crawling
- The JWT contains your user ID and expires ~30 days

## Files

| File | Purpose |
|------|---------|
| `zotspot_crawler.py` | Main crawler |
| `extract_auth.py` | Converts browser auth to crawler format |
| `browser_auth_extractor.js` | Run in browser console to get auth |
| `.gitignore` | Protects sensitive files |

## Requirements

```bash
pip install requests
```

## License

For educational/research use only. Respect ZotSpot's Terms of Service and robots.txt.