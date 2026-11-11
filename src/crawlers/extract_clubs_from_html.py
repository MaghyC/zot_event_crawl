#!/usr/bin/env python3
"""
Extract ALL UCI clubs from the ZotSpot HTML file.
The clubs are in select_filter2 dropdown options.
"""

import re
import json
import os
from dataclasses import dataclass, asdict
from typing import List, Dict

# Get the project root directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_RAW = os.path.join(PROJECT_ROOT, 'data', 'raw')
DATA_CLUBS = os.path.join(PROJECT_ROOT, 'data', 'clubs')

@dataclass
class ZotSpotClub:
    id: str
    name: str
    # Additional fields we'll enrich later
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

def extract_clubs_from_html(html_path: str) -> List[ZotSpotClub]:
    """Extract club data from the HTML dropdown."""
    with open(html_path, 'r') as f:
        html = f.read()

    # Find select_filter2 section
    start = html.find('id="select_filter2"')
    if start == -1:
        print("Could not find select_filter2")
        return []

    # Find the closing </select>
    end = html.find('</select>', start)
    if end == -1:
        print("Could not find closing </select>")
        return []

    select_html = html[start:end]

    # Extract all <option value="...">Name</option>
    pattern = r'<option value="([^"]*)"[^>]*>([^<]+)</option>'
    matches = re.findall(pattern, select_html)

    clubs = []
    for value, name in matches:
        # Skip disabled/separator options
        if not value or value.strip() == "":
            continue
        if "────────" in name:
            continue

        club = ZotSpotClub(
            id=value,
            name=name.strip(),
            raw_html=f'<option value="{value}">{name}</option>'
        )
        clubs.append(club)

    return clubs

def main():
    html_path = os.path.join(DATA_RAW, 'zotspot.uci.edu.html')
    clubs = extract_clubs_from_html(html_path)

    print(f"Found {len(clubs)} clubs")

    # Save to JSON
    output_path = os.path.join(DATA_CLUBS, 'zotspot_clubs_from_html.json')
    with open(output_path, 'w') as f:
        json.dump([asdict(c) for c in clubs], f, indent=2, ensure_ascii=False)

    print(f"Saved to {output_path}")

    # Print first 20
    for club in clubs[:20]:
        print(f"  {club.id}: {club.name}")

    # Also generate Instagram handles file (using login as fallback)
    handles = {club.id: club.name.lower().replace(' ', '').replace('&', '').replace('.', '').replace("'", '').replace('-', '') for club in clubs}
    handles_path = os.path.join(DATA_CLUBS, 'club_instagram_handles_from_html.json')
    with open(handles_path, 'w') as f:
        json.dump(handles, f, indent=2)
    print(f"Generated {len(handles)} Instagram handles to {handles_path}")

if __name__ == "__main__":
    main()