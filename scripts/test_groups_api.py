import requests
import re

url = 'https://zotspot.uci.edu/mobile_ws/v17/mobile_groups_list'
params = {'range': '0', 'limit': '50', '_': '1234567890'}
headers = {'Accept': 'application/json', 'Referer': 'https://zotspot.uci.edu/club_signup?group_type=9999', 'X-Requested-With': 'XMLHttpRequest', 'User-Agent': 'Mozilla/5.0'}
r = requests.get(url, params=params, headers=headers)
print(f'Status: {r.status_code}')
print(f'Response: {r.text[:500]}')