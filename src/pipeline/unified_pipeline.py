#!/usr/bin/env python3
"""
Unified UCI Events Pipeline
Fetches events from multiple sources, normalizes, deduplicates, outputs unified JSON.

Sources:
1. ZotSpot (CampusGroups) - Student clubs/orgs
2. Instagram - Club social media posts
3. UCI Department calendars - Academic events, speakers, courses
4. UCI Calendar feeds - Official university events
5. Mailing list archives - Newsletter events
"""

import json
import time
import re
import hashlib
import os
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse
import logging
from collections import defaultdict
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

try:
    import requests
    from bs4 import BeautifulSoup
    import icalendar
    import dateutil.parser
    EXTRAS_AVAILABLE = True
except ImportError:
    EXTRAS_AVAILABLE = False
    logger.warning("Extra deps not installed: pip install beautifulsoup4 icalendar python-dateutil")


# ============================================================
# DATA MODELS
# ============================================================

@dataclass
class UnifiedEvent:
    """Normalized event from any source"""
    # Core identifiers
    id: str                          # Source-specific ID
    source: str                      # "zotspot", "instagram", "ics_calendar", "bio_calendar", etc.
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


# ============================================================
# SOURCE ADAPTERS (Base + Implementations)
# ============================================================

class SourceAdapter:
    """Base class for event sources"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.source_name = config.get("name", "unknown")

    def fetch(self) -> List[UnifiedEvent]:
        """Fetch and normalize events from this source"""
        raise NotImplementedError

    def _make_event(self, **kwargs) -> UnifiedEvent:
        """Helper to create UnifiedEvent with defaults"""
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
        }
        defaults.update(kwargs)

        # Compute dedup key
        event = UnifiedEvent(**defaults)
        event.dedup_key = self._compute_dedup_key(event)
        return event

    def _compute_dedup_key(self, event: UnifiedEvent) -> str:
        """Generate fuzzy deduplication key"""
        # Normalize title
        title_norm = re.sub(r'[^\w\s]', '', event.title.lower())
        title_norm = re.sub(r'\s+', ' ', title_norm).strip()

        # Normalize date (just date part)
        date_part = ""
        if event.start_datetime:
            try:
                dt = dateutil.parser.parse(event.start_datetime)
                date_part = dt.strftime("%Y%m%d")
            except:
                pass

        # Organizer
        org_norm = re.sub(r'[^\w]', '', event.organizer_name.lower())

        # Combine
        key = f"{title_norm}|{date_part}|{org_norm}"
        return hashlib.md5(key.encode()).hexdigest()[:16]


class ZotSpotAdapter(SourceAdapter):
    """ZotSpot (CampusGroups) events - already implemented"""

    def fetch(self) -> List[UnifiedEvent]:
        # Import and use existing crawler
        from zotspot_crawler import ZotSpotCrawler

        crawler = ZotSpotCrawler(
            base_delay=self.config.get("delay", 2.0),
            max_pages=self.config.get("max_pages", 15)
        )

        raw_events = crawler.crawl_all_events(
            limit_per_page=40,
            include_all_events=self.config.get("all_events", True),
            use_web_filters=self.config.get("web_filters", False)
        )

        events = []
        for re in raw_events:
            raw = re.raw_data
            parsed = raw.get("_parsed", {})

            # Parse dates
            start_dt = self._parse_zotspot_date(raw.get("p4", ""), parsed.get("timezone", ""))

            events.append(self._make_event(
                id=re.id,
                source_url=re.url,
                title=re.title,
                description=re.description,
                start_datetime=start_dt,
                location=re.location,
                location_type=self._infer_location_type(re.location),
                organizer_name=re.group_name,
                organizer_id=re.group_id,
                organizer_type="club",
                organizer_url=f"https://zotspot.uci.edu/group/{parsed.get('club_login', '')}",
                categories=[re.category] if re.category else [],
                tags=self._extract_tags(raw.get("p22", "")),
                audience="students",
                image_url=re.image_url,
                flyer_url=re.image_url,
                rsvp_required=re.rsvp_required,
                rsvp_url=re.url,
                cost=parsed.get("event_price", "Free"),
                raw_data=raw
            ))

        logger.info(f"ZotSpot: fetched {len(events)} events")
        return events

    def _parse_zotspot_date(self, date_html: str, timezone: str) -> Optional[str]:
        """Extract datetime from ZotSpot HTML date string"""
        # <p>Mon, Jun 28, 2021 12:00 AM &ndash; </p><p>Sat, Jan 1, 2028 10:00 AM</p>
        match = re.search(r'(\w{3}, \w{3} \d{1,2}, \d{4} \d{1,2}:\d{2} [AP]M)', date_html)
        if match:
            try:
                dt = dateutil.parser.parse(match.group(1))
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
        return [t for t in tags if t not in ["List all events filtered by"]]


class ICalAdapter(SourceAdapter):
    """Generic iCal/ICS calendar feed adapter"""

    def fetch(self) -> List[UnifiedEvent]:
        url = self.config.get("url")
        if not url:
            return []

        try:
            resp = requests.get(url, timeout=30)
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

            start_dt = dtstart.dt.isoformat() if dtstart and hasattr(dtstart.dt, 'isoformat') else None
            end_dt = dtend.dt.isoformat() if dtend and hasattr(dtend.dt, 'isoformat') else None

            # Extract categories
            categories = []
            for cat in component.get("CATEGORIES", []):
                categories.extend(str(cat).split(","))

            events.append(self._make_event(
                id=uid,
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

    def _infer_location_type(self, location: str) -> str:
        loc = location.lower()
        if any(kw in loc for kw in ["zoom", "virtual", "online", "youtube", "livestream", "webex", "teams"]):
            return "virtual"
        if "hybrid" in loc:
            return "hybrid"
        if location.strip():
            return "physical"
        return "tbd"


class WebScraperAdapter(SourceAdapter):
    """Generic web scraper for department event pages"""

    def fetch(self) -> List[UnifiedEvent]:
        url = self.config.get("url")
        list_selector = self.config.get("list_selector", ".event, .event-item, article")
        title_selector = self.config.get("title_selector", "h2, h3, .title")
        date_selector = self.config.get("date_selector", ".date, .event-date, time")
        location_selector = self.config.get("location_selector", ".location, .venue")
        link_selector = self.config.get("link_selector", "a")

        if not url:
            return []

        try:
            resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
        except Exception as e:
            logger.error(f"Failed to scrape {url}: {e}")
            return []

        events = []
        for item in soup.select(list_selector):
            try:
                title_elem = item.select_one(title_selector)
                title = title_elem.get_text(strip=True) if title_elem else ""

                if not title or len(title) < 5:
                    continue

                date_elem = item.select_one(date_selector)
                date_text = date_elem.get_text(strip=True) if date_elem else ""
                start_dt = self._parse_date(date_text)

                location_elem = item.select_one(location_selector)
                location = location_elem.get_text(strip=True) if location_elem else ""

                link_elem = item.select_one(link_selector)
                link = link_elem.get('href', '') if link_elem else ""
                if link and not link.startswith('http'):
                    link = urljoin(url, link)

                desc = item.get_text(strip=True)[:500]

                events.append(self._make_event(
                    id=hashlib.md5((title + date_text).encode()).hexdigest()[:12],
                    source_url=link or url,
                    title=title,
                    description=desc,
                    start_datetime=start_dt,
                    location=location,
                    location_type=self._infer_location_type(location),
                    organizer_name=self.config.get("organizer_name", ""),
                    organizer_id=self.config.get("organizer_id", ""),
                    organizer_type=self.config.get("organizer_type", "department"),
                    organizer_url=self.config.get("organizer_url", ""),
                    categories=self.config.get("default_categories", []),
                    audience=self.config.get("audience", "public"),
                    raw_data={"source_url": url}
                ))
            except Exception as e:
                logger.debug(f"Failed to parse event item: {e}")

        logger.info(f"WebScraper ({self.source_name}): fetched {len(events)} events")
        return events

    def _parse_date(self, text: str) -> Optional[str]:
        """Parse various date formats"""
        if not text:
            return None
        try:
            # Try common formats
            for fmt in ["%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%Y-%m-%d",
                        "%A, %B %d, %Y", "%B %d, %Y %I:%M %p"]:
                try:
                    return datetime.strptime(text.strip(), fmt).isoformat()
                except:
                    pass
            # Fallback to dateutil
            dt = dateutil.parser.parse(text, fuzzy=True)
            return dt.isoformat()
        except:
            return None

    def _infer_location_type(self, location: str) -> str:
        return ICalAdapter._infer_location_type(self, location)


class InstagramAdapter(SourceAdapter):
    """Instagram enrichment - adds to existing events"""

    def fetch(self) -> List[UnifiedEvent]:
        # This doesn't fetch new events, enriches existing
        # Implemented separately in instagram_enricher.py
        return []


# ============================================================
# DEDUPLICATION ENGINE
# ============================================================

class Deduplicator:
    """Deduplicate events across sources using multiple strategies"""

    def __init__(self, similarity_threshold: float = 0.85):
        self.threshold = similarity_threshold

    def deduplicate(self, events: List[UnifiedEvent]) -> List[UnifiedEvent]:
        """Remove duplicates, merging data from multiple sources"""
        if not events:
            return []

        # Group by dedup_key first (exact matches)
        by_key = defaultdict(list)
        for e in events:
            by_key[e.dedup_key].append(e)

        merged = []
        for key, group in by_key.items():
            if len(group) == 1:
                merged.append(group[0])
            else:
                merged.append(self._merge_group(group))

        # Second pass: fuzzy matching for near-duplicates
        # (different sources may have slightly different keys)
        merged = self._fuzzy_dedupe(merged)

        logger.info(f"Deduplication: {len(events)} -> {len(merged)} events")
        return merged

    def _merge_group(self, events: List[UnifiedEvent]) -> UnifiedEvent:
        """Merge multiple events for same entity"""
        # Use the most complete event as base
        base = max(events, key=lambda e: len(e.description) + len(e.location))

        # Merge fields
        all_sources = set(e.source for e in events)
        all_urls = set(e.source_url for e in events if e.source_url)
        all_categories = set()
        all_tags = set()

        for e in events:
            all_categories.update(e.categories)
            all_tags.update(e.tags)

        # Prefer non-empty values
        for field_name in ['description', 'location', 'image_url', 'flyer_url', 'rsvp_url', 'cost']:
            for e in events:
                val = getattr(e, field_name, "")
                if val and not getattr(base, field_name, ""):
                    setattr(base, field_name, val)

        # Update metadata
        base.raw_data["merged_from"] = list(all_sources)
        base.raw_data["all_source_urls"] = list(all_urls)
        base.categories = list(all_categories)
        base.tags = list(all_tags)
        base.last_updated = datetime.now().isoformat()

        return base

    def _fuzzy_dedupe(self, events: List[UnifiedEvent]) -> List[UnifiedEvent]:
        """Fuzzy match remaining events"""
        # Simple approach: compare titles + dates
        # For production, use more sophisticated matching
        result = []
        seen = set()

        for e in events:
            # Create a fuzzy signature
            sig = self._fuzzy_signature(e)
            if sig in seen:
                continue

            # Check against existing
            is_dup = False
            for existing in result:
                if self._is_similar(e, existing):
                    is_dup = True
                    # Merge
                    merged = self._merge_group([existing, e])
                    result.remove(existing)
                    result.append(merged)
                    break

            if not is_dup:
                result.append(e)
                seen.add(sig)

        return result

    def _fuzzy_signature(self, event: UnifiedEvent) -> str:
        """Quick signature for initial grouping"""
        title_words = set(re.findall(r'\w+', event.title.lower()))
        title_words -= {'the', 'a', 'an', 'and', 'or', 'at', 'in', 'on', 'for', 'to', 'of', 'with', 'by', 'uci', 'uc', 'irvine'}
        date_part = ""
        if event.start_datetime:
            try:
                date_part = dateutil.parser.parse(event.start_datetime).strftime("%Y%m%d")
            except:
                pass
        return f"{date_part}|{' '.join(sorted(title_words)[:5])}"

    def _is_similar(self, e1: UnifiedEvent, e2: UnifiedEvent) -> bool:
        """Check if two events are similar enough to be duplicates"""
        # Title similarity
        title_sim = SequenceMatcher(None, e1.title.lower(), e2.title.lower()).ratio()

        # Date match
        date_match = False
        if e1.start_datetime and e2.start_datetime:
            try:
                d1 = dateutil.parser.parse(e1.start_datetime).date()
                d2 = dateutil.parser.parse(e2.start_datetime).date()
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

    def __init__(self, config_path: Optional[str] = None):
        self.adapters = []
        self.deduplicator = Deduplicator()

        if config_path and os.path.exists(config_path):
            with open(config_path) as f:
                self.config = json.load(f)
        else:
            self.config = self._default_config()

    def _default_config(self) -> Dict[str, Any]:
        return {
            "sources": {
                "zotspot": {
                    "enabled": True,
                    "delay": 2.0,
                    "max_pages": 15,
                    "all_events": True,
                    "web_filters": False
                },
                "ics_calendars": {
                    "enabled": True,
                    "calendars": [
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
                    ]
                },
                "web_calendars": {
                    "enabled": True,
                    "scrapers": [
                        {"name": "uci_events", "url": "https://events.uci.edu/", "organizer_name": "UCI Events", "organizer_id": "uci_events", "organizer_type": "admin", "organizer_url": "https://events.uci.edu", "list_selector": ".event-item, .event, article.event", "title_selector": "h3, .event-title, h2", "date_selector": ".event-date, .date, time", "location_selector": ".event-location, .location, .venue", "default_categories": ["university", "speaker", "public"], "audience": "public"},
                        {"name": "uci_today", "url": "https://today.uci.edu/events", "organizer_name": "UCI Today", "organizer_id": "uci_today", "organizer_type": "admin", "organizer_url": "https://today.uci.edu", "list_selector": ".post-item, article", "title_selector": "h2, h3, .entry-title", "date_selector": ".post-date, time", "location_selector": ".location", "default_categories": ["news", "announcement", "speaker"], "audience": "public"},
                    ]
                }
            }
        }

    def add_adapter(self, adapter: SourceAdapter):
        self.adapters.append(adapter)

    def run(self) -> List[UnifiedEvent]:
        """Run full pipeline"""
        all_events = []

        # Fetch from all adapters
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
        """Save events to JSON"""
        data = [asdict(e) for e in events]
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved {len(events)} events to {output_path}")

    def load_and_enrich_instagram(self, events_file: str, handles_file: str, output_file: str):
        """Run Instagram enrichment on existing events"""
        from instagram_enricher import enrich_events_with_instagram

        with open(handles_file) as f:
            handles = json.load(f)

        enrich_events_with_instagram(
            events_file=events_file,
            club_handles=handles,
            output_file=output_file
        )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Unified UCI Events Pipeline")
    parser.add_argument("--config", help="Config JSON file")
    parser.add_argument("--output", default="unified_events.json", help="Output file")
    parser.add_argument("--only-source", help="Only run specific source (zotspot, ics, web)")
    parser.add_argument("--enrich-instagram", action="store_true", help="Run Instagram enrichment after")
    parser.add_argument("--handles", default="club_instagram_handles.json", help="Instagram handles file")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    pipeline = UnifiedEventsPipeline(args.config)

    # Initialize adapters based on config
    if not args.only_source or args.only_source == "zotspot":
        pipeline.add_adapter(ZotSpotAdapter(pipeline.config["sources"]["zotspot"]))

    if not args.only_source or args.only_source == "ics":
        for cal_config in pipeline.config["sources"]["ics_calendars"].get("calendars", []):
            pipeline.add_adapter(ICalAdapter(cal_config))

    if not args.only_source or args.only_source == "web":
        for scraper_config in pipeline.config["sources"]["web_calendars"].get("scrapers", []):
            pipeline.add_adapter(WebScraperAdapter(scraper_config))

    # Run pipeline
    events = pipeline.run()
    pipeline.save(events, args.output)

    # Instagram enrichment
    if args.enrich_instagram:
        logger.info("Running Instagram enrichment...")
        pipeline.load_and_enrich_instagram(
            events_file=args.output,
            handles_file=args.handles,
            output_file=args.output.replace('.json', '_enriched.json')
        )

    print(f"\nDone! {len(events)} unique events saved to {args.output}")


if __name__ == "__main__":
    main()