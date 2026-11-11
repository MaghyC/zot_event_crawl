import requests
import re

# Try different possible endpoints
endpoints = [
    'mobile_groups_list',
    'mobile_group_list',
    'groups_list',
    'group_list',
    'mobile_groups',
    'mobile_group',
    'club_list',
    'clubs_list',
    'organization_list'
]

for ep in endpoints:
    url = f'https://zotspot.uci.edu/mobile_ws/v17/{ep}'
    params = {'range': '0', 'limit': '50', '_': '1234567890'}
    headers = {'Accept': 'application/json', 'Referer': 'https://zotspot.uci.edu/club_signup?group_type=9999', 'X-Requested-With': 'XMLHttpRequest', 'User-Agent': 'Mozilla/5.0'}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=5)
        if r.status_code != 404:
            print(f'{ep}: Status {r.status_code}')
            if r.status_code == 200:
                print(f'  Response: {r.text[:200]}')
    except:
        pass