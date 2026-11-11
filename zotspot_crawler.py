#!/usr/bin/env python3
"""
ZotSpot Events Crawler
Crawls events from https://zotspot.uci.edu/events using the CampusGroups API.

POLITE CRAWLING:
- Default 2 second delay between requests (configurable)
- Exponential backoff on errors (429, 5xx)
- Jitter to avoid thundering herd
- Respects Retry-After headers
- Configurable max pages to avoid overload
"""

import json
import time
import random
import base64
import requests
import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from urllib.parse import urljoin, urlparse
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


DEFAULT_DELAY = 2.0        # seconds between requests (polite default)
MAX_DELAY = 60.0           # max backoff
DEFAULT_MAX_PAGES = 15     # safety limit (435 events / 40 = ~11 pages)
DEFAULT_TIMEOUT = 30       # request timeout
DEFAULT_LIMIT = 40         # matches webpage pagination
BASE_URL = "https://zotspot.uci.edu"
API_ENDPOINT = "/mobile_ws/v17/mobile_events_list"


def to_absolute_url(url: str, base: str = BASE_URL) -> str:
    """Convert relative URL to absolute URL."""
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("//"):
        return "https:" + url
    return urljoin(base + "/", url.lstrip("/"))


def decode_cg_id(encoded: str) -> Optional[str]:
    """Decode CampusGroups base64 ID (e.g., dWNpOkV2ZW50OjE5NDg3MjU= -> uci:Event:1948725)."""
    try:
        return base64.b64decode(encoded).decode('utf-8')
    except Exception:
        return None


@dataclass
class ZotSpotEvent:
    """Data class for ZotSpot event."""
    id: str
    title: str
    description: str
    start_date: str
    end_date: str
    location: str
    group_name: str
    group_id: str
    category: str
    url: str
    image_url: str
    rsvp_required: bool
    raw_data: Dict[str, Any]


class ZotSpotCrawler:
    """Crawler for ZotSpot events."""

    BASE_URL = "https://zotspot.uci.edu"
    API_ENDPOINT = "/mobile_ws/v17/mobile_events_list"
    SERVICE_URL = "https://uci.service.campusgroups.com"

    def __init__(self, session_cookies: Optional[Dict[str, str]] = None,
                 jwt_token: Optional[str] = None,
                 csrf_token: Optional[str] = None,
                 base_delay: float = DEFAULT_DELAY,
                 max_delay: float = MAX_DELAY,
                 max_pages: int = DEFAULT_MAX_PAGES,
                 timeout: int = DEFAULT_TIMEOUT):
        """
        Initialize crawler.

        Args:
            session_cookies: Dict of session cookies (optional - API is public)
            jwt_token: JWT token (optional - API is public)
            csrf_token: CSRF token (optional - API is public)
            base_delay: Base delay between requests in seconds (default 2.0)
            max_delay: Maximum backoff delay in seconds (default 60.0)
            max_pages: Maximum pages to fetch as safety limit (default 10)
            timeout: Request timeout in seconds (default 30)
        """
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://zotspot.uci.edu/events",
        })

        # Optional auth - only needed for private data (RSVP, private locations, etc.)
        if session_cookies:
            self.session.cookies.update(session_cookies)
        if csrf_token:
            self.session.headers["X-CSRF-Token"] = csrf_token
        if jwt_token:
            self.session.headers["Authorization"] = f"Bearer {jwt_token}"

        # Polite crawling config
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.max_pages = max_pages
        self.timeout = timeout
        self._last_request_time = 0

    @classmethod
    def from_browser_storage(cls, storage_json: str) -> "ZotSpotCrawler":
        """
        Create crawler from browser localStorage/sessionStorage JSON.
        Paste the JSON from browser DevTools > Application > LocalStorage.
        """
        data = json.loads(storage_json)
        return cls(
            session_cookies=data.get("cookies"),
            jwt_token=data.get("jwt"),
            csrf_token=data.get("csrf_token")
        )

    def _build_api_url(self, range_start: int = 0, limit: int = 40,
                       filters: Optional[Dict[str, str]] = None,
                       order: str = "", search: str = "",
                       include_all_events: bool = False,
                       use_web_filters: bool = False) -> str:
        """Build the API URL with parameters."""
        params = {
            "range": str(range_start),
            "limit": str(limit),
            "order": order,
            "search_word": search.replace("#", ""),
        }

        if filters:
            for i in range(1, 10):
                key = f"filter{i}"
                if key in filters and filters[key]:
                    params[key] = filters[key]

            # Special filter4 logic
            if "filter4_contains" in filters:
                params["filter4_contains"] = filters["filter4_contains"]
            if "filter4_notcontains" in filters:
                params["filter4_notcontains"] = filters["filter4_notcontains"]

        # If include_all_events is True, DON'T send filter1 (gets all events: upcoming + past)
        # If include_all_events is False (default), send filter1="" to get "Upcoming" only
        if not include_all_events:
            params["filter1"] = ""

        # Use web-like filters if requested (matches browser XHR)
        if use_web_filters:
            params.setdefault("filter4_contains", "OR")
            params.setdefault("filter4_notcontains", "OR")
            if not order:
                params["order"] = "undefined"

        # Add timestamp to prevent caching
        params["_"] = str(int(time.time() * 1000))

        query_string = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())
        return f"{self.BASE_URL}{self.API_ENDPOINT}?{query_string}"

    def _polite_request(self, url: str, max_retries: int = 3) -> requests.Response:
        """
        Make a polite HTTP request with:
        - Rate limiting (minimum delay between requests)
        - Exponential backoff with jitter on retries
        - Retry-After header respect
        - Timeout handling
        """
        # Enforce minimum delay since last request
        elapsed = time.time() - self._last_request_time
        if elapsed < self.base_delay:
            sleep_time = self.base_delay - elapsed
            # Add small jitter (±10%) to avoid thundering herd
            sleep_time *= (0.9 + random.random() * 0.2)
            logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)

        last_exception = None
        for attempt in range(max_retries):
            try:
                self._last_request_time = time.time()
                response = self.session.get(url, timeout=self.timeout)

                # Handle rate limiting (429) and server errors (5xx)
                if response.status_code == 429 or 500 <= response.status_code < 600:
                    if attempt < max_retries - 1:
                        # Check for Retry-After header
                        retry_after = response.headers.get("Retry-After")
                        if retry_after:
                            try:
                                wait_time = min(int(retry_after), self.max_delay)
                            except ValueError:
                                wait_time = self.base_delay * (2 ** attempt)
                        else:
                            # Exponential backoff with jitter
                            wait_time = min(
                                self.base_delay * (2 ** attempt) + random.uniform(0, 1),
                                self.max_delay
                            )

                        logger.warning(
                            f"HTTP {response.status_code} - backing off {wait_time:.1f}s "
                            f"(attempt {attempt + 1}/{max_retries})"
                        )
                        time.sleep(wait_time)
                        continue
                    else:
                        response.raise_for_status()

                # Success
                response.raise_for_status()
                return response

            except requests.Timeout:
                last_exception = "Request timeout"
                logger.warning(f"Timeout (attempt {attempt + 1}/{max_retries})")
            except requests.ConnectionError:
                last_exception = "Connection error"
                logger.warning(f"Connection error (attempt {attempt + 1}/{max_retries})")
            except requests.RequestException as e:
                last_exception = str(e)
                logger.warning(f"Request error: {e} (attempt {attempt + 1}/{max_retries})")

            if attempt < max_retries - 1:
                # Exponential backoff with jitter for network errors
                wait_time = min(
                    self.base_delay * (2 ** attempt) + random.uniform(0, 1),
                    self.max_delay
                )
                logger.debug(f"Retrying in {wait_time:.1f}s...")
                time.sleep(wait_time)

        raise requests.RequestException(f"Failed after {max_retries} attempts: {last_exception}")

    def fetch_events_page(self, range_start: int = 0, limit: int = 40,
                          filters: Optional[Dict[str, str]] = None,
                          order: str = "", search: str = "",
                          include_all_events: bool = False,
                          use_web_filters: bool = False) -> tuple[List[ZotSpotEvent], int]:
        """
        Fetch a single page of events.

        Returns:
            Tuple of (List of ZotSpotEvent objects, total_count from API)
        """
        url = self._build_api_url(range_start, limit, filters, order, search, include_all_events, use_web_filters)
        logger.info(f"Fetching page (range={range_start}, limit={limit})")

        response = self._polite_request(url)

        data = response.json()
        if not data:
            return [], 0

        events = []
        total_count = 0
        for item in data:
            # Get total count from last item
            if "counter" in item:
                try:
                    total_count = int(item["counter"])
                except (ValueError, TypeError):
                    pass

            # Skip separator/header items (listingSeparator="true" or p0="true")
            if item.get("listingSeparator") == "true" or item.get("p0") == "true":
                continue
            # Skip counter metadata (has counter but no actual event fields)
            if "counter" in item and "eventId" not in item.get("fields", ""):
                continue

            event = self._parse_event(item)
            if event:
                events.append(event)

        return events, total_count

    def _parse_event(self, item: Dict[str, Any]) -> Optional[ZotSpotEvent]:
        """Parse raw API response into ZotSpotEvent."""
        try:
            fields = item.get("fields", "").split(",")

            # Extract field values (p0, p1, p2, etc.)
            field_values = {}
            for i, field_name in enumerate(fields):
                key = f"p{i}"
                if key in item:
                    field_values[field_name] = item[key]

            # Convert relative URLs to absolute
            event_url = to_absolute_url(field_values.get("eventUrl", ""))
            event_url_logo = to_absolute_url(field_values.get("eventUrlLogo", ""))
            event_url_title = to_absolute_url(field_values.get("eventUrlTitle", ""))
            event_url_button = to_absolute_url(field_values.get("eventUrlButton", ""))
            event_url_location = to_absolute_url(field_values.get("eventUrlLocation", ""))
            image_url = to_absolute_url(field_values.get("eventPicture", ""))

            # Decode CampusGroups internal ID if present
            event_uid = field_values.get("eventUid", "")
            decoded_uid = decode_cg_id(event_uid) if event_uid else None

            # Map common fields
            event = ZotSpotEvent(
                id=str(item.get("id", field_values.get("eventId", ""))),
                title=field_values.get("eventName", field_values.get("name", "")),
                description=field_values.get("eventFlyerDescription", field_values.get("eventPhotoDescription", "")),
                start_date=field_values.get("eventDates", field_values.get("event_start", "")),
                end_date="",  # Included in eventDates
                location=field_values.get("eventLocation", field_values.get("venue", "")),
                group_name=field_values.get("clubName", field_values.get("organization", "")),
                group_id=str(field_values.get("clubId", field_values.get("organization_id", ""))),
                category=field_values.get("eventCategory", field_values.get("event_type", "")),
                url=event_url,
                image_url=image_url,
                rsvp_required=field_values.get("eventButtonLabel", "").lower() in ("register", "rsvp"),
                raw_data=item
            )
            # Add extra fields to raw_data for reference
            event.raw_data["_parsed"] = {
                "event_url": event_url,
                "event_url_logo": event_url_logo,
                "event_url_title": event_url_title,
                "event_url_button": event_url_button,
                "event_url_location": event_url_location,
                "decoded_uid": decoded_uid,
                "club_login": field_values.get("clubLogin", ""),
                "event_price": field_values.get("eventPriceRange", ""),
                "event_badges": field_values.get("eventBadges", ""),
                "event_tags": field_values.get("eventTags", ""),
                "timezone": field_values.get("eventTimezone", ""),
            }
            return event
        except Exception as e:
            logger.warning(f"Failed to parse event: {e}")
            return None

    def crawl_all_events(self, limit_per_page: int = 40,
                         filters: Optional[Dict[str, str]] = None,
                         order: str = "", search: str = "",
                         max_pages: Optional[int] = None,
                         delay: Optional[float] = None,
                         include_all_events: bool = False,
                         use_web_filters: bool = False,
                         resume_file: Optional[str] = None) -> List[ZotSpotEvent]:
        """
        Crawl all events with pagination.

        Args:
            limit_per_page: Number of events per page (default 40, matches web)
            filters: Dict of filter1-filter9 values
            order: Sort order
            search: Search query
            max_pages: Maximum pages to fetch (None = use instance default)
            delay: Deprecated - use instance base_delay instead
            include_all_events: If True, don't send filter1 (gets all events incl past)
            use_web_filters: If True, use filter4_contains=OR&filter4_notcontains=OR&order=undefined
            resume_file: Path to JSON file to save/load progress for resume capability

        Returns:
            List of all ZotSpotEvent objects
        """
        # Load progress if resume_file exists
        all_events = []
        range_start = 0
        page = 0
        total_count = 0

        if resume_file and os.path.exists(resume_file):
            try:
                with open(resume_file, 'r') as f:
                    progress = json.load(f)
                all_events = [ZotSpotEvent(**e) for e in progress.get('events', [])]
                range_start = progress.get('range_start', 0)
                page = progress.get('page', 0)
                total_count = progress.get('total_count', 0)
                logger.info(f"Resumed from page {page + 1}, range_start={range_start}, {len(all_events)} events loaded")
            except Exception as e:
                logger.warning(f"Could not load resume file: {e}")

        # Use instance max_pages as safety limit if not overridden
        effective_max_pages = max_pages if max_pages is not None else self.max_pages

        while True:
            if page >= effective_max_pages:
                logger.info(f"Reached max pages limit ({effective_max_pages})")
                break

            events, page_total = self.fetch_events_page(
                range_start=range_start,
                limit=limit_per_page,
                filters=filters,
                order=order,
                search=search,
                include_all_events=include_all_events,
                use_web_filters=use_web_filters
            )

            if page_total > 0:
                total_count = page_total

            if not events:
                logger.info("No more events found")
                break

            all_events.extend(events)
            logger.info(f"Page {page + 1}: Got {len(events)} events (total: {len(all_events)}/{total_count})")

            # Save progress
            if resume_file:
                try:
                    progress = {
                        'events': [asdict(e) for e in all_events],
                        'range_start': range_start + limit_per_page,
                        'page': page + 1,
                        'total_count': total_count,
                        'timestamp': time.time()
                    }
                    with open(resume_file + '.tmp', 'w') as f:
                        json.dump(progress, f)
                    os.rename(resume_file + '.tmp', resume_file)
                except Exception as e:
                    logger.warning(f"Could not save progress: {e}")

            # Check if we've fetched all events (using API's counter)
            if len(all_events) >= total_count:
                logger.info(f"Fetched all {total_count} events")
                break

            range_start += limit_per_page
            page += 1

        # Clean up resume file on success
        if resume_file and os.path.exists(resume_file):
            try:
                os.remove(resume_file)
            except:
                pass

        return all_events

    def save_events(self, events: List[ZotSpotEvent], filepath: str):
        """Save events to JSON file."""
        data = [asdict(e) for e in events]
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved {len(events)} events to {filepath}")

    def get_filter_options(self) -> Dict[str, List[Dict[str, str]]]:
        """Fetch available filter options (groups, categories, etc.)."""
        # These are typically in the HTML page - fetch and parse
        url = f"{BASE_URL}/events"
        response = self.session.get(url)
        response.raise_for_status()

        # Parse the HTML to extract filter options
        # This would require BeautifulSoup - left as exercise
        return {}

    def fetch_event_details(self, event_url: str) -> Optional[Dict[str, Any]]:
        """
        Fetch detailed event information from the event page.

        Args:
            event_url: Absolute URL to event (e.g., https://zotspot.uci.edu/rsvp_boot?id=123456)

        Returns:
            Dict with detailed event info, or None if failed
        """
        if not event_url:
            return None

        logger.info(f"Fetching event details: {event_url}")
        try:
            response = self._polite_request(event_url)

            # Parse HTML for details (requires BeautifulSoup)
            # For now, return raw HTML
            return {
                "url": event_url,
                "html": response.text,
                "status": "success"
            }
        except Exception as e:
            logger.warning(f"Failed to fetch event details: {e}")
            return {"url": event_url, "error": str(e), "status": "failed"}

    def crawl_event_details(self, events: List[ZotSpotEvent],
                           max_details: Optional[int] = None) -> List[ZotSpotEvent]:
        """
        Fetch detailed info for each event (optional, slow).

        Args:
            events: List of events to enrich
            max_details: Max number of events to fetch details for (None = all)

        Returns:
            Same events list with enriched raw_data
        """
        count = 0
        for event in events:
            if max_details and count >= max_details:
                break

            if event.url:
                details = self.fetch_event_details(event.url)
                if details:
                    event.raw_data["details"] = details
                count += 1

        logger.info(f"Fetched details for {count} events")
        return events


def main():
    """Example usage."""
    import argparse

    parser = argparse.ArgumentParser(description="Crawl ZotSpot events (polite crawler)")
    parser.add_argument("--cookies", help="Path to cookies JSON file (optional - API is public)")
    parser.add_argument("--jwt", help="JWT token (optional)")
    parser.add_argument("--csrf", help="CSRF token (optional)")
    parser.add_argument("--output", default="zotspot_events.json", help="Output file")
    parser.add_argument("--limit", type=int, default=40, help="Events per page (default: 40, matches web)")
    parser.add_argument("--max-pages", type=int, help="Max pages to crawl (default: 15)")
    parser.add_argument("--search", default="", help="Search query")
    parser.add_argument("--filter-group", help="Filter by group ID (filter2)")
    parser.add_argument("--filter-category", help="Filter by category (filter3)")
    parser.add_argument("--delay", type=float, default=2.0, help="Base delay between requests in seconds (default: 2.0)")
    parser.add_argument("--max-delay", type=float, default=60.0, help="Max backoff delay in seconds (default: 60.0)")
    parser.add_argument("--timeout", type=int, default=30, help="Request timeout in seconds (default: 30)")
    parser.add_argument("--fetch-details", type=int, metavar="N", nargs="?", const=0, help="Fetch detail pages for N events (0=all, default: 0)")
    parser.add_argument("--all-events", action="store_true", help="Include past events (default: upcoming only)")
    parser.add_argument("--web-filters", action="store_true", help="Use web-like filters (filter4_contains=OR, order=undefined)")
    parser.add_argument("--resume", metavar="FILE", help="Resume file path for interrupted crawls")

    args = parser.parse_args()

    # Load cookies if provided (optional)
    cookies = None
    if args.cookies:
        with open(args.cookies) as f:
            cookies = json.load(f)

    # Initialize crawler with polite settings (auth optional)
    crawler = ZotSpotCrawler(
        session_cookies=cookies,
        jwt_token=args.jwt,
        csrf_token=args.csrf,
        base_delay=args.delay,
        max_delay=args.max_delay,
        max_pages=args.max_pages if args.max_pages else DEFAULT_MAX_PAGES,
        timeout=args.timeout
    )

    # Build filters
    filters = {}
    if args.filter_group:
        filters["filter2"] = args.filter_group  # Group filter
    if args.filter_category:
        filters["filter3"] = args.filter_category  # Category filter

    # Crawl
    events = crawler.crawl_all_events(
        limit_per_page=args.limit,
        filters=filters if filters else None,
        search=args.search,
        max_pages=args.max_pages,
        include_all_events=args.all_events,
        use_web_filters=args.web_filters,
        resume_file=args.resume
    )

    # Optionally fetch detail pages
    if args.fetch_details is not None:
        n = args.fetch_details if args.fetch_details > 0 else None
        logger.info(f"Fetching detail pages for {n if n else 'all'} events...")
        events = crawler.crawl_event_details(events, max_details=n)

    # Save
    crawler.save_events(events, args.output)

    # Print summary
    print(f"\nCrawled {len(events)} events")
    for event in events[:5]:
        print(f"  - {event.title} ({event.start_date}) - {event.group_name}")
        print(f"    URL: {event.url}")


if __name__ == "__main__":
    main()