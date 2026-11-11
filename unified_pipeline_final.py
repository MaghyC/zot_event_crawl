#!/usr/bin/env python3
"""
Unified UCI Events Pipeline - Complete Version
Combines events from:
1. ZotSpot (CampusGroups) - student clubs/orgs
2. UCI Department ICS calendars - academic events, speakers, courses
3. Deduplicates across all sources

Uses clubs from extracted HTML (1010 clubs) to enrich events.
"""

import json
import time
import re
import hashlib
import os
import requests
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse
import logging
from collections import defaultdict
from difflib import SequenceMatcher
import icalendar

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ============================================================
# DATA MODELS
# ============================================================

@dataclass
class UnifiedEvent:
    """Normalized event from any source"""
    # Core identifiers
    id: str                          # Source-specific ID
    source: str                      # "zotspot", "ics_calendar", "uci_events", etc.
    source_url: str                  # Original URL

    # Event details
    title: str
    description: str
    start_datetime: Optional[str]    # ISO format
    end_datetime: Optional[str]      # ISO format
    timezone: str                    # e.g., "America/Los_Angeles"
    location: str                    # Venue name/address
    location_type: str               # "physical", "virtual", "hybrid", "tbd"

    # Organization
    organizer_name: str
    organizer_id: str                # Source-specific org ID
    organizer_type: str              # "club", "department", "center", "institute", "admin"
    organizer_url: str

    # Categorization
    categories: List[str]            # ["speaker", "workshop", "course", "social", "meeting"]
    tags: List[str]                  # Free-form tags
    audience: str                    # "students", "faculty", "public", "graduates"

    # Media
    image_url: str
    flyer_url: str

    # Registration
    rsvp_required: bool
    rsvp_url: str
    rsvp_deadline: Optional[str]
    cost: str                        # "Free", "$10", "Donation"

    # Metadata
    first_seen: str                  # ISO timestamp
    last_updated: str                # ISO timestamp
    raw_data: Dict[str, Any]         # Source-specific raw data

    # Deduplication
    dedup_key: str = ""              # Computed fuzzy match key


@dataclass
class ZotSpotClub:
    """UCI Club/Organization from ZotSpot"""
    id: str
    name: str
    category: str = ""
    description: str = ""
    member_count: int = 0
    logo_url: str = ""
    website: str = ""
    email: str = ""
    instagram: str = ""
    facebook: str = ""
    twitter: str = ""
    linkedin: str = ""
    youtube: str = ""
    discord: str = ""
    is_active: bool = True
    raw_html: str = ""


# ============================================================
# SOURCE ADAPTERS
# ============================================================

class SourceAdapter:
    """Base class for event sources"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.source_name = config.get("name", "unknown")

    def fetch(self) -> List[UnifiedEvent]:
        raise NotImplementedError

    def _make_event(self, **kwargs) -> UnifiedEvent:
        now = datetime.now().isoformat()
        defaults = {
            "source": self.source_name,
            "first_seen": now,
            "last_updated": now,
            "raw_data": {},
            "timezone": "America/Los_Angeles",
            "location_type": "tbd",
            "categories": [],
            "tags": [],
            "audience": "public",
            "cost": "Free",
            "rsvp_required": False,
            "rsvp_url": "",
            "rsvp_deadline": None,
            "image_url": "",
            "flyer_url": "",
            "end_datetime": None,
        }
        defaults.update(kwargs)

        event = UnifiedEvent(**defaults)
        event.dedup_key = self._compute_dedup_key(event)
        return event

    def _compute_dedup_key(self, event: UnifiedEvent) -> str:
        """Generate fuzzy deduplication key"""
        title_norm = re.sub(r'[^\w\s]', '', event.title.lower())
        title_norm = re.sub(r'\s+', ' ', title_norm).strip()

        date_part = ""
        if event.start_datetime:
            try:
                dt = datetime.fromisoformat(event.start_datetime.replace('Z', '+00:00'))
                date_part = dt.strftime("%Y%m%d")
            except:
                pass

        org_norm = re.sub(r'[^\w]', '', event.organizer_name.lower())

        key = f"{title_norm}|{date_part}|{org_norm}"
        return hashlib.md5(key.encode()).hexdigest()[:16]


class ZotSpotEventsAdapter(SourceAdapter):
    """ZotSpot (CampusGroups) events"""

    def __init__(self, config: Dict[str, Any], clubs: Dict[str, ZotSpotClub]):
        super().__init__(config)
        self.clubs = clubs
        self.base_delay = config.get("delay", 2.0)
        self.max_delay = config.get("max_delay", 60.0)
        self._last_request = 0
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://zotspot.uci.edu/events",
        })

    def _polite_request(self, url: str, max_retries: int = 3) -> requests.Response:
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

    def _build_api_url(self, range_start: int, limit: int, include_all: bool) -> str:
        params = {
            "range": str(range_start),
            "limit": str(limit),
            "_": str(int(time.time() * 1000))
        }
        if not include_all:
            params["filter1"] = ""  # Upcoming only
        query = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())
        return f"https://zotspot.uci.edu/mobile_ws/v17/mobile_events_list?{query}"

    def fetch(self) -> List[UnifiedEvent]:
        events = []
        range_start = 0
        limit = 40
        page = 0
        max_pages = self.config.get("max_pages", 15)
        include_all = self.config.get("include_all_events", True)

        while page < max_pages:
            url = self._build_api_url(range_start, limit, include_all)
            logger.info(f"ZotSpot: Fetching page {page + 1} (range={range_start})")

            response = self._polite_request(url)
            data = response.json()

            if not data:
                break

            page_events = []
            total_count = 0
            for item in data:
                if item.get("listingSeparator") == "true" or item.get("p0") == "true":
                    continue
                if "counter" in item:
                    try:
                        total_count = int(item["counter"])
                    except:
                        pass
                if "counter" in item and "eventId" not in item.get("fields", ""):
                    continue

                event = self._parse_event(item)
                if event:
                    page_events.append(event)

            if not page_events:
                break

            events.extend(page_events)
            logger.info(f"ZotSpot: Page {page + 1}: Got {len(page_events)} events (total: {len(events)}/{total_count})")

            if total_count > 0 and len(events) >= total_count:
                break

            range_start += limit
            page += 1

        logger.info(f"ZotSpot: Total {len(events)} events")
        return events

    def _parse_event(self, item: Dict[str, Any]) -> Optional[UnifiedEvent]:
        try:
            fields = item.get("fields", "").split(",")
            field_values = {}
            for i, field_name in enumerate(fields):
                key = f"p{i}"
                if key in item:
                    field_values[field_name] = item[key]

            # Get club info
            group_id = str(field_values.get("clubId", ""))
            club = self.clubs.get(group_id, ZotSpotClub(id=group_id, name=field_values.get("clubName", "")))

            # Parse dates
            start_dt = self._parse_zotspot_date(field_values.get("eventDates", ""), field_values.get("eventTimezone", ""))

            # Build URL
            event_url = field_values.get("eventUrl", "")
            if event_url and not event_url.startswith("http"):
                event_url = f"https://zotspot.uci.edu{event_url}"

            image_url = field_values.get("eventPicture", "")
            if image_url and not image_url.startswith("http"):
                image_url = f"https://zotspot.uci.edu{image_url}"

            return self._make_event(
                id=str(item.get("id", field_values.get("eventId", ""))),
                source_url=event_url,
                title=field_values.get("eventName", ""),
                description=field_values.get("eventFlyerDescription", field_values.get("eventPhotoDescription", "")),
                start_datetime=start_dt,
                location=field_values.get("eventLocation", ""),
                location_type=self._infer_location_type(field_values.get("eventLocation", "")),
                organizer_name=field_values.get("clubName", club.name),
                organizer_id=group_id,
                organizer_type="club",
                organizer_url=f"https://zotspot.uci.edu/group/{field_values.get('clubLogin', '')}",
                categories=[field_values.get("eventCategory", "")] if field_values.get("eventCategory") else [],
                tags=self._extract_tags(field_values.get("eventTags", "")),
                audience="students",
                image_url=image_url,
                flyer_url=image_url,
                rsvp_required=field_values.get("eventButtonLabel", "").lower() in ("register", "rsvp"),
                rsvp_url=event_url,
                cost=field_values.get("eventPriceRange", "Free"),
                raw_data=item
            )
        except Exception as e:
            logger.warning(f"Failed to parse ZotSpot event: {e}")
            return None

    def _parse_zotspot_date(self, date_html: str, timezone: str) -> Optional[str]:
        match = re.search(r'(\w{3}, \w{3} \d{1,2}, \d{4} \d{1,2}:\d{2} [AP]M)', date_html)
        if match:
            try:
                dt = datetime.strptime(match.group(1), "%a, %b %d, %Y %I:%M %p")
                return dt.isoformat()
            except:
                pass
        return None

    def _infer_location_type(self, location: str) -> str:
        loc = location.lower()
        if "private location" in loc or "sign in" in loc:
            return "tbd"
        if any(kw in loc for kw in ["zoom", "virtual", "online", "youtube", "livestream"]):
            return "virtual"
        if "hybrid" in loc:
            return "hybrid"
        return "physical"

    def _extract_tags(self, tags_html: str) -> List[str]:
        tags = re.findall(r'aria-label="([^"]+)"', tags_html)
        return [t for t in tags if not t.startswith("List all events filtered by")]


class ICalAdapter(SourceAdapter):
    """ICS Calendar feed adapter for UCI departments"""

    def fetch(self) -> List[UnifiedEvent]:
        url = self.config.get("url")
        if not url:
            return []

        try:
            resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            cal = icalendar.Calendar.from_ical(resp.text)
        except Exception as e:
            logger.error(f"Failed to fetch ICS from {url}: {e}")
            return []

        events = []
        for component in cal.walk():
            if component.name != "VEVENT":
                continue

            uid = str(component.get("UID", ""))
            summary = str(component.get("SUMMARY", ""))
            description = str(component.get("DESCRIPTION", ""))
            location = str(component.get("LOCATION", ""))
            url_prop = str(component.get("URL", ""))

            dtstart = component.get("DTSTART")
            dtend = component.get("DTEND")

            start_dt = self._parse_dt(dtstart)
            end_dt = self._parse_dt(dtend)

            # Extract categories
            categories = []
            for cat in component.get("CATEGORIES", []):
                categories.extend(str(cat).split(","))
            if not categories:
                categories = self.config.get("default_categories", [])

            events.append(self._make_event(
                id=uid or hashlib.md5((summary + (start_dt or "")).encode()).hexdigest()[:12],
                source_url=url_prop or url,
                title=summary,
                description=description,
                start_datetime=start_dt,
                end_datetime=end_dt,
                location=location,
                location_type=self._infer_location_type(location),
                organizer_name=self.config.get("organizer_name", "UCI Department"),
                organizer_id=self.config.get("organizer_id", ""),
                organizer_type=self.config.get("organizer_type", "department"),
                organizer_url=self.config.get("organizer_url", ""),
                categories=categories,
                audience=self.config.get("audience", "public"),
                cost="Free",
                raw_data={"ical_uid": uid, "source_url": url}
            ))

        logger.info(f"ICAL ({self.source_name}): fetched {len(events)} events")
        return events

    def _parse_dt(self, dtprop) -> Optional[str]:
        if not dtprop:
            return None
        try:
            dt = dtprop.dt
            if hasattr(dt, 'isoformat'):
                return dt.isoformat()
            if isinstance(dt, str):
                return dt
        except:
            pass
        return None

    def _infer_location_type(self, location: str) -> str:
        loc = location.lower()
        if any(kw in loc for kw in ["zoom", "virtual", "online", "youtube", "livestream", "webex", "teams"]):
            return "virtual"
        if "hybrid" in loc:
            return "hybrid"
        if location.strip():
            return "physical"
        return "tbd"


# ============================================================
# DEDUPLICATION ENGINE
# ============================================================

class Deduplicator:
    """Deduplicate events across sources"""

    def __init__(self, similarity_threshold: float = 0.85):
        self.threshold = similarity_threshold

    def deduplicate(self, events: List[UnifiedEvent]) -> List[UnifiedEvent]:
        if not events:
            return []

        # Group by dedup_key (exact matches)
        by_key = defaultdict(list)
        for e in events:
            by_key[e.dedup_key].append(e)

        merged = []
        for key, group in by_key.items():
            if len(group) == 1:
                merged.append(group[0])
            else:
                merged.append(self._merge_group(group))

        # Second pass: fuzzy matching
        merged = self._fuzzy_dedupe(merged)

        logger.info(f"Deduplication: {len(events)} -> {len(merged)} events")
        return merged

    def _merge_group(self, events: List[UnifiedEvent]) -> UnifiedEvent:
        # Use most complete event as base
        base = max(events, key=lambda e: len(e.description) + len(e.location))

        all_sources = set(e.source for e in events)
        all_urls = set(e.source_url for e in events if e.source_url)
        all_categories = set()
        all_tags = set()

        for e in events:
            all_categories.update(e.categories)
            all_tags.update(e.tags)

        # Prefer non-empty values
        for field_name in ['description', 'location', 'image_url', 'flyer_url', 'rsvp_url', 'cost', 'end_datetime']:
            for e in events:
                val = getattr(e, field_name, "")
                if val and not getattr(base, field_name, ""):
                    setattr(base, field_name, val)

        base.raw_data["merged_from"] = list(all_sources)
        base.raw_data["all_source_urls"] = list(all_urls)
        base.categories = list(all_categories)
        base.tags = list(all_tags)
        base.last_updated = datetime.now().isoformat()

        return base

    def _fuzzy_dedupe(self, events: List[UnifiedEvent]) -> List[UnifiedEvent]:
        result = []
        seen = set()

        for e in events:
            sig = self._fuzzy_signature(e)
            if sig in seen:
                continue

            is_dup = False
            for existing in result:
                if self._is_similar(e, existing):
                    is_dup = True
                    merged = self._merge_group([existing, e])
                    result.remove(existing)
                    result.append(merged)
                    break

            if not is_dup:
                result.append(e)
                seen.add(sig)

        return result

    def _fuzzy_signature(self, event: UnifiedEvent) -> str:
        title_words = set(re.findall(r'\w+', event.title.lower()))
        title_words -= {'the', 'a', 'an', 'and', 'or', 'at', 'in', 'on', 'for', 'to', 'of', 'with', 'by', 'uci', 'uc', 'irvine', 'event', 'meeting', 'workshop', 'seminar', 'speaker', 'series'}
        date_part = ""
        if event.start_datetime:
            try:
                date_part = datetime.fromisoformat(event.start_datetime.replace('Z', '+00:00')).strftime("%Y%m%d")
            except:
                pass
        return f"{date_part}|{' '.join(sorted(title_words)[:5])}"

    def _is_similar(self, e1: UnifiedEvent, e2: UnifiedEvent) -> bool:
        # Title similarity
        title_sim = SequenceMatcher(None, e1.title.lower(), e2.title.lower()).ratio()

        # Date match
        date_match = False
        if e1.start_datetime and e2.start_datetime:
            try:
                d1 = datetime.fromisoformat(e1.start_datetime.replace('Z', '+00:00')).date()
                d2 = datetime.fromisoformat(e2.start_datetime.replace('Z', '+00:00')).date()
                date_match = d1 == d2
            except:
                pass

        # Organizer similarity
        org_sim = SequenceMatcher(None, e1.organizer_name.lower(), e2.organizer_name.lower()).ratio()

        # Combined score
        score = (title_sim * 0.5) + (0.3 if date_match else 0) + (org_sim * 0.2)

        return score >= self.threshold


# ============================================================
# MAIN PIPELINE
# ============================================================

class UnifiedEventsPipeline:
    """Main pipeline orchestrator"""

    def __init__(self, clubs_file: str = "zotspot_clubs_from_html.json"):
        # Load clubs
        self.clubs = self._load_clubs(clubs_file)
        self.adapters = []
        self.deduplicator = Deduplicator()
        self._init_adapters()

    def _load_clubs(self, clubs_file: str) -> Dict[str, ZotSpotClub]:
        clubs = {}
        try:
            with open(clubs_file) as f:
                data = json.load(f)
            for item in data:
                club = ZotSpotClub(**item)
                clubs[club.id] = club
            logger.info(f"Loaded {len(clubs)} clubs from {clubs_file}")
        except Exception as e:
            logger.warning(f"Could not load clubs: {e}")
        return clubs

    def _init_adapters(self):
        # ZotSpot Events
        self.adapters.append(ZotSpotEventsAdapter({
            "name": "zotspot",
            "delay": 2.0,
            "max_delay": 60.0,
            "max_pages": 15,
            "include_all_events": True
        }, self.clubs))

        # UCI Department ICS Calendars
        ics_calendars = [
            {"name": "ics_calendar", "url": "https://www.ics.uci.edu/events.ics", "organizer_name": "ICS", "organizer_id": "ics", "organizer_type": "department", "organizer_url": "https://www.ics.uci.edu", "audience": "students", "default_categories": ["academic", "speaker", "colloquium"]},
            {"name": "engineering_calendar", "url": "https://engineering.uci.edu/events.ics", "organizer_name": "Engineering", "organizer_id": "eng", "organizer_type": "department", "organizer_url": "https://engineering.uci.edu", "audience": "students", "default_categories": ["academic", "speaker", "workshop"]},
            {"name": "bio_calendar", "url": "https://www.bio.uci.edu/events.ics", "organizer_name": "BioSci", "organizer_id": "bio", "organizer_type": "department", "organizer_url": "https://www.bio.uci.edu", "audience": "students", "default_categories": ["academic", "seminar", "speaker"]},
            {"name": "physical_sci_calendar", "url": "https://www.ps.uci.edu/events.ics", "organizer_name": "Physical Sciences", "organizer_id": "ps", "organizer_type": "department", "organizer_url": "https://www.ps.uci.edu", "audience": "students", "default_categories": ["academic", "speaker"]},
            {"name": "social_sci_calendar", "url": "https://socialsciences.uci.edu/events.ics", "organizer_name": "Social Sciences", "organizer_id": "socsci", "organizer_type": "department", "organizer_url": "https://socialsciences.uci.edu", "audience": "students", "default_categories": ["academic", "speaker", "colloquium"]},
            {"name": "humanities_calendar", "url": "https://humanities.uci.edu/events.ics", "organizer_name": "Humanities", "organizer_id": "hum", "organizer_type": "department", "organizer_url": "https://humanities.uci.edu", "audience": "students", "default_categories": ["academic", "lecture", "speaker"]},
            {"name": "arts_calendar", "url": "https://arts.uci.edu/events.ics", "organizer_name": "Arts", "organizer_id": "arts", "organizer_type": "department", "organizer_url": "https://arts.uci.edu", "audience": "public", "default_categories": ["arts", "exhibition", "performance"]},
            {"name": "merage_calendar", "url": "https://merage.uci.edu/events.ics", "organizer_name": "Merage School of Business", "organizer_id": "merage", "organizer_type": "department", "organizer_url": "https://merage.uci.edu", "audience": "students", "default_categories": ["business", "speaker", "networking"]},
            {"name": "law_calendar", "url": "https://law.uci.edu/events.ics", "organizer_name": "Law", "organizer_id": "law", "organizer_type": "department", "organizer_url": "https://law.uci.edu", "audience": "students", "default_categories": ["legal", "speaker", "symposium"]},
            {"name": "medicine_calendar", "url": "https://medicine.uci.edu/events.ics", "organizer_name": "Medicine", "organizer_id": "med", "organizer_type": "department", "organizer_url": "https://medicine.uci.edu", "audience": "students", "default_categories": ["medical", "grand rounds", "speaker"]},
            {"name": "nursing_calendar", "url": "https://nursing.uci.edu/events.ics", "organizer_name": "Nursing", "organizer_id": "nursing", "organizer_type": "department", "organizer_url": "https://nursing.uci.edu", "audience": "students", "default_categories": ["health", "speaker", "workshop"]},
            {"name": "pharmacy_calendar", "url": "https://pharmacy.uci.edu/events.ics", "organizer_name": "Pharmacy", "organizer_id": "pharm", "organizer_type": "department", "organizer_url": "https://pharmacy.uci.edu", "audience": "students", "default_categories": ["pharmaceutical", "speaker"]},
            {"name": "public_health_calendar", "url": "https://publichealth.uci.edu/events.ics", "organizer_name": "Public Health", "organizer_id": "ph", "organizer_type": "department", "organizer_url": "https://publichealth.uci.edu", "audience": "students", "default_categories": ["health", "speaker", "seminar"]},
            {"name": "education_calendar", "url": "https://education.uci.edu/events.ics", "organizer_name": "Education", "organizer_id": "edu", "organizer_type": "department", "organizer_url": "https://education.uci.edu", "audience": "students", "default_categories": ["education", "speaker", "workshop"]},
            {"name": "social_ecology_calendar", "url": "https://socialecology.uci.edu/events.ics", "organizer_name": "Social Ecology", "organizer_id": "se", "organizer_type": "department", "organizer_url": "https://socialecology.uci.edu", "audience": "students", "default_categories": ["academic", "speaker", "research"]},
        ]

        for cal_config in ics_calendars:
            self.adapters.append(ICalAdapter(cal_config))

    def run(self) -> List[UnifiedEvent]:
        all_events = []

        for adapter in self.adapters:
            try:
                logger.info(f"Fetching from {adapter.source_name}...")
                events = adapter.fetch()
                all_events.extend(events)
            except Exception as e:
                logger.error(f"Adapter {adapter.source_name} failed: {e}")

        # Deduplicate
        logger.info(f"Total events before dedup: {len(all_events)}")
        unique_events = self.deduplicator.deduplicate(all_events)
        logger.info(f"Total events after dedup: {len(unique_events)}")

        return unique_events

    def save(self, events: List[UnifiedEvent], output_path: str):
        data = [asdict(e) for e in events]
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved {len(events)} events to {output_path}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Unified UCI Events Pipeline")
    parser.add_argument("--clubs", default="zotspot_clubs_from_html.json", help="Clubs JSON file")
    parser.add_argument("--output", default="unified_events.json", help="Output file")

    args = parser.parse_args()

    pipeline = UnifiedEventsPipeline(args.clubs)
    events = pipeline.run()
    pipeline.save(events, args.output)

    print(f"\nDone! {len(events)} unique events saved to {args.output}")

    # Print summary by source
    by_source = defaultdict(int)
    for e in events:
        by_source[e.source] += 1
    print("\nBy source:")
    for src, count in sorted(by_source.items()):
        print(f"  {src}: {count}")


if __name__ == "__main__":
    main()