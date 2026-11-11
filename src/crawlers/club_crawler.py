#!/usr/bin/env python3
"""
ZotSpot Club Directory Crawler
Fetches ALL UCI clubs/organizations from the club directory.
Uses the mobile_groups_list API endpoint (similar to events API).
"""

import json
import time
import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


BASE_URL = "https://zotspot.uci.edu"
GROUPS_API = "/mobile_ws/v17/mobile_groups_list"
DEFAULT_DELAY = 2.0
MAX_DELAY = 60.0


@dataclass
class ZotSpotClub:
    """UCI Club/Organization from ZotSpot"""
    id: str                          # Group ID
    name: str                        # Club name
    login: str                       # URL slug (e.g., "animeclubcae")
    description: str                 # Club description
    category: str                    # Category/Type
    member_count: int                # Number of members
    officer_count: int               # Number of officers
    logo_url: str                    # Logo/image URL
    cover_url: str                   # Cover/banner URL
    website: str                     # External website
    email: str                       # Contact email
    facebook: str                    # Facebook URL
    twitter: str                     # Twitter/X URL
    instagram: str                   # Instagram URL
    linkedin: str                    # LinkedIn URL
    youtube: str                     # YouTube URL
    discord: str                     # Discord URL
    slug: str                        # URL slug
    is_active: bool                  # Active status
    group_type: str                  # Group type ID
    created_date: str                # Creation date
    raw_data: Dict[str, Any]         # Original API response


class ClubDirectoryCrawler:
    """Crawler for ZotSpot club directory"""

    def __init__(self, base_delay: float = DEFAULT_DELAY, max_delay: float = MAX_DELAY):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://zotspot.uci.edu/club_signup?group_type=9999",
        })
        self.base_delay = base_delay
        self.max_delay = max_delay
        self._last_request = 0

    def _polite_request(self, url: str, max_retries: int = 3) -> requests.Response:
        """Rate-limited request with exponential backoff"""
        import random

        elapsed = time.time() - self._last_request
        if elapsed < self.base_delay:
            sleep_time = self.base_delay - elapsed
            sleep_time *= (0.9 + random.random() * 0.2)
            time.sleep(sleep_time)

        last_exception = None
        for attempt in range(max_retries):
            try:
                self._last_request = time.time()
                response = self.session.get(url, timeout=30)

                if response.status_code == 429 or 500 <= response.status_code < 600:
                    if attempt < max_retries - 1:
                        wait_time = min(self.base_delay * (2 ** attempt) + random.uniform(0, 1), self.max_delay)
                        logger.warning(f"HTTP {response.status_code} - backing off {wait_time:.1f}s")
                        time.sleep(wait_time)
                        continue
                    else:
                        response.raise_for_status()

                response.raise_for_status()
                return response

            except requests.RequestException as e:
                last_exception = str(e)
                if attempt < max_retries - 1:
                    wait_time = min(self.base_delay * (2 ** attempt) + random.uniform(0, 1), self.max_delay)
                    time.sleep(wait_time)

        raise requests.RequestException(f"Failed after {max_retries} attempts: {last_exception}")

    def _build_api_url(self, range_start: int, limit: int) -> str:
        """Build API URL for groups list"""
        params = {
            "range": str(range_start),
            "limit": str(limit),
            "_": str(int(time.time() * 1000))
        }
        query = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())
        return f"{BASE_URL}{GROUPS_API}?{query}"

    def fetch_clubs_page(self, range_start: int = 0, limit: int = 50) -> List[ZotSpotClub]:
        """Fetch a single page of clubs"""
        url = self._build_api_url(range_start, limit)
        logger.info(f"Fetching clubs page (range={range_start}, limit={limit})")

        response = self._polite_request(url)
        data = response.json()

        if not data:
            return []

        clubs = []
        for item in data:
            # Skip separators/metadata
            if item.get("listingSeparator") == "true" or item.get("p0") == "true":
                continue
            if "counter" in item and "groupId" not in item.get("fields", ""):
                continue

            club = self._parse_club(item)
            if club:
                clubs.append(club)

        return clubs

    def _parse_club(self, item: Dict[str, Any]) -> Optional[ZotSpotClub]:
        """Parse club from API response"""
        try:
            fields = item.get("fields", "").split(",")
            field_values = {}
            for i, field_name in enumerate(fields):
                key = f"p{i}"
                if key in item:
                    field_values[field_name] = item[key]

            # Extract known fields from API response
            # Based on CampusGroups mobile_groups_list structure
            club = ZotSpotClub(
                id=str(item.get("id", field_values.get("groupId", ""))),
                name=field_values.get("groupName", field_values.get("name", "")),
                login=field_values.get("groupLogin", field_values.get("login", "")),
                description=field_values.get("description", field_values.get("groupDescription", "")),
                category=field_values.get("groupType", field_values.get("category", "")),
                member_count=int(field_values.get("memberCount", field_values.get("members", "0")) or 0),
                officer_count=int(field_values.get("officerCount", field_values.get("officers", "0")) or 0),
                logo_url=self._to_absolute(field_values.get("logo", field_values.get("groupLogo", ""))),
                cover_url=self._to_absolute(field_values.get("cover", field_values.get("groupCover", ""))),
                website=field_values.get("website", field_values.get("groupWebsite", "")),
                email=field_values.get("email", field_values.get("groupEmail", "")),
                facebook=field_values.get("facebook", field_values.get("groupFacebook", "")),
                twitter=field_values.get("twitter", field_values.get("groupTwitter", "")),
                instagram=field_values.get("instagram", field_values.get("groupInstagram", "")),
                linkedin=field_values.get("linkedin", field_values.get("groupLinkedIn", "")),
                youtube=field_values.get("youtube", field_values.get("groupYouTube", "")),
                discord=field_values.get("discord", field_values.get("groupDiscord", "")),
                slug=field_values.get("groupLogin", field_values.get("login", "")),
                is_active=field_values.get("isActive", field_values.get("active", "true")).lower() == "true",
                group_type=field_values.get("groupTypeId", field_values.get("type", "")),
                created_date=field_values.get("createdDate", field_values.get("created", "")),
                raw_data=item
            )
            return club
        except Exception as e:
            logger.warning(f"Failed to parse club: {e}")
            return None

    def _to_absolute(self, url: str) -> str:
        if not url:
            return ""
        if url.startswith("http://") or url.startswith("https://"):
            return url
        if url.startswith("//"):
            return "https:" + url
        return f"{BASE_URL}/{url.lstrip('/')}"

    def crawl_all_clubs(self, limit_per_page: int = 50, max_pages: Optional[int] = None) -> List[ZotSpotClub]:
        """Crawl all clubs with pagination"""
        all_clubs = []
        range_start = 0
        page = 0
        total_count = 0

        while True:
            if max_pages and page >= max_pages:
                break

            clubs = self.fetch_clubs_page(range_start, limit_per_page)

            if not clubs:
                logger.info("No more clubs found")
                break

            all_clubs.extend(clubs)

            # Get total from last item's counter
            # (we'd need to track from raw response)

            logger.info(f"Page {page + 1}: Got {len(clubs)} clubs (total: {len(all_clubs)})")

            if len(clubs) < limit_per_page:
                break

            range_start += limit_per_page
            page += 1

        return all_clubs

    def save_clubs(self, clubs: List[ZotSpotClub], filepath: str):
        """Save clubs to JSON"""
        data = [asdict(c) for c in clubs]
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved {len(clubs)} clubs to {filepath}")

    def generate_instagram_handles(self, clubs: List[ZotSpotClub], output_path: str):
        """Generate club_instagram_handles.json from crawled clubs"""
        handles = {}
        for club in clubs:
            if club.instagram:
                # Extract username from URL
                ig = club.instagram
                if "instagram.com/" in ig:
                    username = ig.split("instagram.com/")[-1].strip("/").split("/")[0].split("?")[0]
                else:
                    username = ig.strip("@")
                if username:
                    handles[club.id] = username
            elif club.login:
                # Use login as fallback (often matches Instagram handle)
                handles[club.id] = club.login

        with open(output_path, 'w') as f:
            json.dump(handles, f, indent=2)
        logger.info(f"Generated {len(handles)} Instagram handles to {output_path}")

    def generate_club_lookup(self, clubs: List[ZotSpotClub], output_path: str):
        """Generate comprehensive club lookup dictionary"""
        lookup = {}
        for club in clubs:
            lookup[club.id] = {
                "id": club.id,
                "name": club.name,
                "login": club.login,
                "slug": club.slug,
                "category": club.category,
                "member_count": club.member_count,
                "description": club.description[:200] if club.description else "",
                "website": club.website,
                "email": club.email,
                "social": {
                    "instagram": club.instagram,
                    "facebook": club.facebook,
                    "twitter": club.twitter,
                    "linkedin": club.linkedin,
                    "youtube": club.youtube,
                    "discord": club.discord
                },
                "logo_url": club.logo_url,
                "is_active": club.is_active,
                "group_type": club.group_type
            }

        with open(output_path, 'w') as f:
            json.dump(lookup, f, indent=2, ensure_ascii=False)
        logger.info(f"Generated club lookup with {len(lookup)} clubs to {output_path}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Crawl ZotSpot club directory")
    parser.add_argument("--output", default="zotspot_clubs.json", help="Output file for clubs")
    parser.add_argument("--handles", default="club_instagram_handles.json", help="Instagram handles output")
    parser.add_argument("--lookup", default="club_lookup.json", help="Club lookup output")
    parser.add_argument("--limit", type=int, default=50, help="Clubs per page")
    parser.add_argument("--max-pages", type=int, help="Max pages to crawl")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between requests")

    args = parser.parse_args()

    crawler = ClubDirectoryCrawler(base_delay=args.delay)

    clubs = crawler.crawl_all_clubs(
        limit_per_page=args.limit,
        max_pages=args.max_pages
    )

    crawler.save_clubs(clubs, args.output)
    crawler.generate_instagram_handles(clubs, args.handles)
    crawler.generate_club_lookup(clubs, args.lookup)

    print(f"\nCrawled {len(clubs)} clubs")
    print(f"Clubs saved to: {args.output}")
    print(f"Instagram handles: {args.handles}")
    print(f"Club lookup: {args.lookup}")

    # Print sample
    for club in clubs[:5]:
        print(f"  - {club.name} (ID: {club.id}) - {club.login} - {club.category}")


if __name__ == "__main__":
    main()