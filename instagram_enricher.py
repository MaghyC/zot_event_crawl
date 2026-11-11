#!/usr/bin/env python3
"""
Instagram Enrichment Module for ZotSpot Events
Adds Instagram data to existing events.json

⚠️ WARNING: Instagram scraping is fragile and may violate ToS.
Use responsibly. Consider official APIs where possible.
"""

import json
import time
import re
import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from urllib.parse import quote
import logging

logger = logging.getLogger(__name__)

try:
    import instaloader
    INSTALOADER_AVAILABLE = True
except ImportError:
    INSTALOADER_AVAILABLE = False
    logger.warning("instaloader not installed. Run: pip install instaloader")

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


@dataclass
class InstagramPost:
    """Instagram post data"""
    shortcode: str
    url: str
    caption: str
    timestamp: str
    likes: int
    comments: int
    is_video: bool
    image_url: str
    hashtags: List[str]
    mentions: List[str]
    location: Optional[str]


@dataclass
class ClubInstagram:
    """Club's Instagram info"""
    username: str
    profile_url: str
    bio: str
    follower_count: int
    verified: bool
    recent_posts: List[InstagramPost]


class InstagramEnricher:
    """Enrich ZotSpot events with Instagram data"""

    def __init__(self, session_file: Optional[str] = None,
                 use_selenium: bool = False,
                 rate_limit: float = 5.0):
        """
        Initialize enricher.

        Args:
            session_file: Path to Instagram session file (instaloader)
            use_selenium: Use Selenium instead of instaloader
            rate_limit: Minimum seconds between requests
        """
        self.session_file = session_file
        self.use_selenium = use_selenium
        self.rate_limit = rate_limit
        self._last_request = 0
        self.loader = None
        self.driver = None

        if INSTALOADER_AVAILABLE and not use_selenium:
            self.loader = instaloader.Instaloader(
                download_pictures=False,
                download_videos=False,
                download_geotags=False,
                download_comments=False,
                save_metadata=False,
                compress_json=False
            )
            if session_file and os.path.exists(session_file):
                self.loader.load_session_from_file(session_file)

    def _rate_limit(self):
        """Enforce minimum delay between requests"""
        elapsed = time.time() - self._last_request
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self._last_request = time.time()

    def get_club_instagram(self, username: str) -> Optional[ClubInstagram]:
        """Get club's Instagram profile and recent posts"""
        if not username:
            return None

        self._rate_limit()

        try:
            if self.loader:
                profile = instaloader.Profile.from_username(self.loader.context, username)

                # Get recent posts (max 10)
                posts = []
                for i, post in enumerate(profile.get_posts()):
                    if i >= 10:
                        break
                    posts.append(InstagramPost(
                        shortcode=post.shortcode,
                        url=f"https://instagram.com/p/{post.shortcode}/",
                        caption=post.caption or "",
                        timestamp=post.date_utc.isoformat() if post.date_utc else "",
                        likes=post.likes,
                        comments=post.comments,
                        is_video=post.is_video,
                        image_url=post.url,
                        hashtags=self._extract_hashtags(post.caption or ""),
                        mentions=self._extract_mentions(post.caption or ""),
                        location=post.location.name if post.location else None
                    ))

                return ClubInstagram(
                    username=profile.username,
                    profile_url=f"https://instagram.com/{profile.username}/",
                    bio=profile.biography or "",
                    follower_count=profile.followers,
                    verified=profile.is_verified,
                    recent_posts=posts
                )
        except Exception as e:
            logger.warning(f"Failed to get Instagram for {username}: {e}")

        return None

    def _extract_hashtags(self, text: str) -> List[str]:
        return re.findall(r'#(\w+)', text)

    def _extract_mentions(self, text: str) -> List[str]:
        return re.findall(r'@(\w+)', text)

    def find_event_posts(self, club_ig: ClubInstagram,
                         event_title: str, event_date: str) -> List[InstagramPost]:
        """Find Instagram posts related to a specific event"""
        matches = []
        event_keywords = self._event_to_keywords(event_title)

        for post in club_ig.recent_posts:
            score = self._match_score(post, event_keywords, event_date)
            if score > 0.5:  # Threshold
                matches.append((score, post))

        matches.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in matches]

    def _event_to_keywords(self, title: str) -> List[str]:
        """Extract search keywords from event title"""
        # Remove common words, keep meaningful ones
        stopwords = {'the', 'a', 'an', 'and', 'or', 'at', 'in', 'on', 'for', 'to', 'of', 'with', 'by'}
        words = re.findall(r'\w+', title.lower())
        return [w for w in words if w not in stopwords and len(w) > 2]

    def _match_score(self, post: InstagramPost, keywords: List[str], event_date: str) -> float:
        """Score how well a post matches an event"""
        score = 0.0
        caption_lower = post.caption.lower()

        # Keyword matching
        for kw in keywords:
            if kw in caption_lower:
                score += 1.0

        # Hashtag matching
        for tag in post.hashtags:
            if tag.lower() in keywords:
                score += 0.5

        # Date proximity (if parseable)
        # TODO: implement date comparison

        return score / max(len(keywords), 1)


def enrich_events_with_instagram(events_file: str,
                                  club_handles: Dict[str, str],
                                  output_file: str,
                                  session_file: Optional[str] = None) -> None:
    """
    Enrich events.json with Instagram data.

    Args:
        events_file: Path to events.json from zotspot_crawler
        club_handles: Dict mapping group_id -> instagram username
                      e.g., {"33476": "animeclubcae", "71416": "dna_plu"}
        output_file: Path to save enriched events
        session_file: Instagram session file for auth
    """
    # Load events
    with open(events_file) as f:
        events = json.load(f)

    # Initialize enricher
    enricher = InstagramEnricher(session_file=session_file)

    # Track clubs we've fetched
    club_cache = {}

    for event in events:
        group_id = event.get("group_id", "")
        if group_id in club_handles:
            username = club_handles[group_id]

            # Get club Instagram (cached)
            if username not in club_cache:
                logger.info(f"Fetching Instagram for @{username}...")
                club_cache[username] = enricher.get_club_instagram(username)
                time.sleep(2)  # Extra delay between clubs

            club_ig = club_cache[username]
            if club_ig:
                # Find matching posts
                matches = enricher.find_event_posts(
                    club_ig,
                    event.get("title", ""),
                    event.get("start_date", "")
                )

                # Add to event
                event["instagram"] = {
                    "club_handle": username,
                    "club_profile": club_ig.profile_url,
                    "club_followers": club_ig.follower_count,
                    "matched_posts": [
                        {
                            "url": p.url,
                            "caption": p.caption[:200],
                            "timestamp": p.timestamp,
                            "likes": p.likes,
                            "image_url": p.image_url,
                            "hashtags": p.hashtags,
                            "mentions": p.mentions
                        }
                        for p in matches[:3]  # Top 3 matches
                    ],
                    "enriched_at": time.strftime("%Y-%m-%d %H:%M:%S")
                }

                logger.info(f"  Enriched: {event['title'][:50]}... ({len(matches)} IG matches)")

    # Save enriched events
    with open(output_file, 'w') as f:
        json.dump(events, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved enriched events to {output_file}")


def main():
    """Example usage"""
    import argparse

    parser = argparse.ArgumentParser(description="Enrich ZotSpot events with Instagram data")
    parser.add_argument("--events", required=True, help="Path to events.json from zotspot_crawler")
    parser.add_argument("--handles", required=True, help="JSON file mapping group_id -> instagram username")
    parser.add_argument("--output", default="events_enriched.json", help="Output file")
    parser.add_argument("--session", help="Instagram session file (from instaloader)")
    parser.add_argument("--rate-limit", type=float, default=5.0, help="Seconds between requests")

    args = parser.parse_args()

    # Load club handles
    with open(args.handles) as f:
        club_handles = json.load(f)

    enrich_events_with_instagram(
        events_file=args.events,
        club_handles=club_handles,
        output_file=args.output,
        session_file=args.session
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()