# ZotSpot Events Crawler

A polite, authenticated crawler for ZotSpot (UC Irvine's CampusGroups platform) events.

## Features

- **Authenticated API access** - Uses JWT + CSRF tokens from your browser session
- **Polite crawling** - Rate limiting (2s default), exponential backoff, jitter, retry logic
- **Pagination support** - Automatic pagination with configurable page size
- **Filtering** - Filter by group, category, search terms, date ranges
- **Safety limits** - Max pages limit (default 10) to prevent accidental overload

## Quick Start

### 1. Get Authentication Tokens

1. Log into https://zotspot.uci.edu/events in your browser
2. Open DevTools (F12) → Console
3. Paste the contents of `browser_auth_extractor.js` and press Enter
4. **Copy the JSON output** (between `=== COPY FROM HERE ===` and `=== TO HERE ===`)
5. Save as `auth.json`

### 2. Convert Auth Data

```bash
python3 extract_auth.py auth.json
# Creates auth_crawler.json with only needed credentials
```

### 3. Crawl Events

```bash
# Basic crawl (max 10 pages, 2s delay)
python3 zotspot_crawler.py --cookies auth_crawler.json --output events.json

# Search for specific events
python3 zotspot_crawler.py --cookies auth_crawler.json --search "workshop" --output events.json

# Filter by group (filter2 = group ID)
python3 zotspot_crawler.py --cookies auth_crawler.json --filter-group 71416 --output events.json

# Crawl more pages with custom delay
python3 zotspot_crawler.py --cookies auth_crawler.json --max-pages 50 --delay 3.0 --output all_events.json
```

### 4. Clean Up

```bash
# DELETE sensitive auth files when done
rm auth.json auth_crawler.json
```

## Command Options

| Option | Description | Default |
|--------|-------------|---------|
| `--cookies` | Path to cookies JSON file | - |
| `--jwt` | JWT token directly | - |
| `--csrf` | CSRF token directly | - |
| `--output` | Output JSON file | `zotspot_events.json` |
| `--limit` | Events per page | 50 |
| `--max-pages` | Maximum pages to crawl | 10 |
| `--search` | Search query | "" |
| `--filter-group` | Group ID (filter2) | - |
| `--filter-category` | Category ID (filter3) | - |
| `--delay` | Base delay between requests (seconds) | 2.0 |
| `--max-delay` | Max backoff delay (seconds) | 60.0 |
| `--timeout` | Request timeout (seconds) | 30 |

## Output Format

Events are saved as JSON array with this structure:

```json
{
  "id": "12345",
  "title": "Event Title",
  "description": "Event description...",
  "start_date": "2024-01-15 18:00:00",
  "end_date": "2024-01-15 20:00:00",
  "location": "Student Center",
  "group_name": "Club Name",
  "group_id": "71416",
  "category": "Workshop",
  "url": "https://zotspot.uci.edu/event/12345",
  "image_url": "https://...",
  "rsvp_required": false,
  "raw_data": { ... }
}
```

## Polite Crawling Details

The crawler implements several politeness measures:

1. **Rate Limiting**: Minimum 2 seconds between requests (configurable)
2. **Jitter**: ±10% random variation to avoid thundering herd
3. **Exponential Backoff**: On 429/5xx errors, waits 2s, 4s, 8s... up to 60s
4. **Retry-After Header**: Respects server's `Retry-After` header if present
5. **Max Pages**: Default 10 page limit prevents accidental deep crawls
6. **Timeouts**: 30 second request timeout (configurable)

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