#!/usr/bin/env python3
"""
ZotSpot Events Crawler
Crawls events from https://zotspot.uci.edu/events using the CampusGroups API.
"""

import json
import time
import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from urllib.parse import urljoin, urlparse
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


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
                 csrf_token: Optional[str] = None):
        """
        Initialize crawler.

        Args:
            session_cookies: Dict of session cookies (e.g., from browser)
            jwt_token: JWT token from window.cg.session.jwt
            csrf_token: CSRF token from window.cg.session.csrf_token
        """
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://zotspot.uci.edu/events",
        })

        if session_cookies:
            self.session.cookies.update(session_cookies)
        if csrf_token:
            self.session.headers["X-CSRF-Token"] = csrf_token
        if jwt_token:
            self.session.headers["Authorization"] = f"Bearer {jwt_token}"

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

    def _build_api_url(self, range_start: int = 0, limit: int = 50,
                       filters: Optional[Dict[str, str]] = None,
                       order: str = "", search: str = "") -> str:
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

        # Add timestamp to prevent caching
        params["_"] = str(int(time.time() * 1000))

        query_string = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())
        return f"{self.BASE_URL}{self.API_ENDPOINT}?{query_string}"

    def fetch_events_page(self, range_start: int = 0, limit: int = 50,
                          filters: Optional[Dict[str, str]] = None,
                          order: str = "", search: str = "") -> List[ZotSpotEvent]:
        """
        Fetch a single page of events.

        Returns:
            List of ZotSpotEvent objects
        """
        url = self._build_api_url(range_start, limit, filters, order, search)
        logger.info(f"Fetching: {url}")

        response = self.session.get(url, timeout=30)
        response.raise_for_status()

        data = response.json()
        if not data:
            return []

        events = []
        for item in data:
            # Last item may contain counter metadata
            if "counter" in item and "fields" in item:
                continue

            event = self._parse_event(item)
            if event:
                events.append(event)

        return events

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

            # Map common fields (adjust based on actual response)
            event = ZotSpotEvent(
                id=str(item.get("id", field_values.get("id", ""))),
                title=field_values.get("title", field_values.get("name", "")),
                description=field_values.get("description", field_values.get("desc", "")),
                start_date=field_values.get("start_date", field_values.get("event_start", "")),
                end_date=field_values.get("end_date", field_values.get("event_end", "")),
                location=field_values.get("location", field_values.get("venue", "")),
                group_name=field_values.get("group_name", field_values.get("organization", "")),
                group_id=str(field_values.get("group_id", field_values.get("organization_id", ""))),
                category=field_values.get("category", field_values.get("event_type", "")),
                url=field_values.get("url", field_values.get("event_url", "")),
                image_url=field_values.get("image_url", field_values.get("logo", "")),
                rsvp_required=field_values.get("rsvp_required", "false").lower() == "true",
                raw_data=item
            )
            return event
        except Exception as e:
            logger.warning(f"Failed to parse event: {e}")
            return None

    def crawl_all_events(self, limit_per_page: int = 50,
                         filters: Optional[Dict[str, str]] = None,
                         order: str = "", search: str = "",
                         max_pages: Optional[int] = None,
                         delay: float = 1.0) -> List[ZotSpotEvent]:
        """
        Crawl all events with pagination.

        Args:
            limit_per_page: Number of events per page (max 100 typically)
            filters: Dict of filter1-filter9 values
            order: Sort order
            search: Search query
            max_pages: Maximum pages to fetch (None = all)
            delay: Delay between requests in seconds

        Returns:
            List of all ZotSpotEvent objects
        """
        all_events = []
        range_start = 0
        page = 0

        while True:
            if max_pages and page >= max_pages:
                break

            events = self.fetch_events_page(
                range_start=range_start,
                limit=limit_per_page,
                filters=filters,
                order=order,
                search=search
            )

            if not events:
                logger.info("No more events found")
                break

            all_events.extend(events)
            logger.info(f"Page {page + 1}: Got {len(events)} events (total: {len(all_events)})")

            # Check if there are more pages (last item has counter)
            # The API returns counter in the last item of the response
            # We'll just continue until we get fewer than limit_per_page
            if len(events) < limit_per_page:
                break

            range_start += limit_per_page
            page += 1
            time.sleep(delay)

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
        url = f"{self.BASE_URL}/events"
        response = self.session.get(url)
        response.raise_for_status()

        # Parse the HTML to extract filter options
        # This would require BeautifulSoup - left as exercise
        return {}


def main():
    """Example usage."""
    import argparse

    parser = argparse.ArgumentParser(description="Crawl ZotSpot events")
    parser.add_argument("--cookies", help="Path to cookies JSON file")
    parser.add_argument("--jwt", help="JWT token")
    parser.add_argument("--csrf", help="CSRF token")
    parser.add_argument("--output", default="zotspot_events.json", help="Output file")
    parser.add_argument("--limit", type=int, default=50, help="Events per page")
    parser.add_argument("--max-pages", type=int, help="Max pages to crawl")
    parser.add_argument("--search", default="", help="Search query")
    parser.add_argument("--filter-group", help="Filter by group ID (filter2)")
    parser.add_argument("--filter-category", help="Filter by category (filter3)")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests")

    args = parser.parse_args()

    # Load cookies if provided
    cookies = None
    if args.cookies:
        with open(args.cookies) as f:
            cookies = json.load(f)

    # Initialize crawler
    crawler = ZotSpotCrawler(
        session_cookies=cookies,
        jwt_token=args.jwt,
        csrf_token=args.csrf
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
        delay=args.delay
    )

    # Save
    crawler.save_events(events, args.output)

    # Print summary
    print(f"\nCrawled {len(events)} events")
    for event in events[:5]:
        print(f"  - {event.title} ({event.start_date}) - {event.group_name}")


if __name__ == "__main__":
    main()