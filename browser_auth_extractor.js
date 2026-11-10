/**
 * ZotSpot Auth Extractor - Run in Browser Console
 *
 * INSTRUCTIONS:
 * 1. Go to https://zotspot.uci.edu/events (must be logged in)
 * 2. Open DevTools (F12) → Console tab
 * 3. Paste this ENTIRE script and press Enter
 * 4. COPY the JSON output from console (starts with {, ends with })
 * 5. Save as auth.json file
 */

(function() {
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

    // Get CSRF token
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
    const lsToken = localStorage.getItem('token') || localStorage.getItem('jwt') || localStorage.getItem('access_token');
    if (lsToken) result.jwtToken = lsToken;

    // Output to console - COPY THIS MANUALLY
    console.log('=== COPY THE JSON BELOW ===');
    console.log(JSON.stringify(result, null, 2));
    console.log('=== END COPY ===');

    // Also store in global variable for easy access
    window.ZOTSPOT_AUTH = result;
    console.log('Also saved to window.ZOTSPOT_AUTH - you can run: copy(JSON.stringify(window.ZOTSPOT_AUTH, null, 2))');
})();