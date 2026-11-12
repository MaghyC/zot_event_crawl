#!/usr/bin/env python3
"""
Helper to extract authentication tokens from browser for ZotSpot.
Run this in browser DevTools Console, then save output to JSON file.
"""

# ============================================
# BROWSER CONSOLE SCRIPT - COPY AND PASTE INTO DEVTOOLS
# ============================================

BROWSER_SCRIPT = r'''
(function() {
    // Extract all necessary auth data from ZotSpot
    const result = {
        url: window.location.href,
        timestamp: new Date().toISOString(),
        cookies: {},
        localStorage: {},
        sessionStorage: {},
        cgSession: window.cg?.session || {},
        csrfToken: null,
        jwtToken: null
    };

    // Get cookies
    document.cookie.split(';').forEach(cookie => {
        const [name, ...rest] = cookie.trim().split('=');
        if (name) result.cookies[name] = rest.join('=');
    });

    // Get localStorage
    for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        try {
            result.localStorage[key] = localStorage.getItem(key);
        } catch (e) {
            result.localStorage[key] = '[unreadable]';
        }
    }

    // Get sessionStorage
    for (let i = 0; i < sessionStorage.length; i++) {
        const key = sessionStorage.key(i);
        try {
            result.sessionStorage[key] = sessionStorage.getItem(key);
        } catch (e) {
            result.sessionStorage[key] = '[unreadable]';
        }
    }

    // Get CSRF token from meta tag or window.cg
    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
    if (csrfMeta) {
        result.csrfToken = csrfMeta.content;
    } else if (window.cg?.session?.csrf_token) {
        result.csrfToken = window.cg.session.csrf_token;
    }

    // Get JWT token
    if (window.cg?.session?.jwt) {
        result.jwtToken = window.cg.session.jwt;
    }

    // Also check for token in localStorage
    const lsToken = localStorage.getItem('token') || localStorage.getItem('jwt') || localStorage.getItem('access_token');
    if (lsToken) result.jwtToken = lsToken;

    console.log('=== ZOTSPOT AUTH DATA ===');
    console.log(JSON.stringify(result, null, 2));
    console.log('=== COPY ABOVE JSON TO FILE ===');

    // Also copy to clipboard
    navigator.clipboard.writeText(JSON.stringify(result, null, 2))
        .then(() => console.log('Copied to clipboard!'))
        .catch(() => console.log('Could not copy to clipboard'));
})();
'''

# ============================================
# PYTHON HELPER TO PARSE THE OUTPUT
# ============================================

import json
import sys

def parse_browser_output(json_file: str) -> dict:
    """Parse the browser console output JSON file."""
    with open(json_file) as f:
        data = json.load(f)

    # Extract what we need for the crawler
    cookies = data.get('cookies', {})

    # Get CSRF token
    csrf_token = data.get('csrfToken') or data.get('cgSession', {}).get('csrf_token')

    # Get JWT token
    jwt_token = data.get('jwtToken') or data.get('cgSession', {}).get('jwt')

    return {
        'cookies': cookies,
        'csrf_token': csrf_token,
        'jwt_token': jwt_token,
        'raw': data
    }

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  1. Run this in browser console on zotspot.uci.edu/events:")
        print(BROWSER_SCRIPT)
        print("\n  2. Save output to file (e.g., auth.json)")
        print("  3. Run: python3 extract_auth.py auth.json")
        return

    json_file = sys.argv[1]
    auth_data = parse_browser_output(json_file)

    print(f"Cookies: {len(auth_data['cookies'])} found")
    print(f"CSRF Token: {'Yes' if auth_data['csrf_token'] else 'No'}")
    print(f"JWT Token: {'Yes' if auth_data['jwt_token'] else 'No'}")

    # Save simplified version for crawler
    output_file = json_file.replace('.json', '_crawler.json')
    with open(output_file, 'w') as f:
        json.dump({
            'cookies': auth_data['cookies'],
            'csrf_token': auth_data['csrf_token'],
            'jwt_token': auth_data['jwt_token']
        }, f, indent=2)

    print(f"\nSaved crawler config to: {output_file}")
    print("\nUse with crawler:")
    print(f"  python3 zotspot_crawler.py --cookies {output_file}")

if __name__ == "__main__":
    main()